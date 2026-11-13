#!/usr/bin/env python3
"""Cross-family verifier for the pr-review skill.

Sends each candidate finding to an OpenAI model with the shared verifier brief and read-only
tools over the review worktree, and writes one verdict per candidate. Candidates run in
parallel. Stdlib only, so it runs anywhere without a package install.

Requires OPENAI_API_KEY, and the model in PR_REVIEW_OPENAI_MODEL or --model.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

API = "https://api.openai.com/v1"
BRIEF = Path(__file__).resolve().parent.parent / "reference" / "verifier-brief.md"
MAX_READ_LINES = 400
MAX_GREP_LINES = 200
MAX_HUNK_CHARS = 20_000
RETRY_STATUSES = {429, 500, 502, 503, 504}

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "verdict": {"type": "string", "enum": ["CONFIRMED", "REFUTED", "UNCERTAIN"]},
        "evidence": {"type": "string"},
        "unknown": {"type": "string"},
    },
    "required": ["id", "verdict", "evidence", "unknown"],
    "additionalProperties": False,
}


def _tool(name, description, properties):
    return {
        "type": "function",
        "name": name,
        "description": description,
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        },
    }


TOOLS = [
    _tool(
        "read_file",
        f"Read lines of a repo file, numbered. At most {MAX_READ_LINES} lines per call.",
        {
            "path": {"type": "string", "description": "Path relative to the repo root."},
            "start_line": {"type": ["integer", "null"], "description": "1-based; null for 1."},
            "end_line": {"type": ["integer", "null"], "description": "Inclusive; null for start+399."},
        },
    ),
    _tool(
        "grep",
        f"Search tracked files with an extended regex (git grep -n -E). At most {MAX_GREP_LINES} matches.",
        {
            "pattern": {"type": "string"},
            "path": {"type": ["string", "null"], "description": "Limit to this file or directory; null for the whole repo."},
        },
    ),
    _tool(
        "list_dir",
        "List a repo directory's entries.",
        {"path": {"type": "string", "description": "Directory relative to the repo root; '.' for the root."}},
    ),
]


class Repo:
    """Read-only access confined to one directory tree."""

    def __init__(self, root):
        self.root = os.path.realpath(root)

    def _resolve(self, rel):
        full = os.path.realpath(os.path.join(self.root, rel or "."))
        if full != self.root and not full.startswith(self.root + os.sep):
            raise ValueError(f"path escapes the repo: {rel}")
        return full

    def read_file(self, path, start_line, end_line):
        start = max(start_line or 1, 1)
        end = min(end_line or start + MAX_READ_LINES - 1, start + MAX_READ_LINES - 1)
        with open(self._resolve(path), encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        if start > len(lines):
            return f"(file has {len(lines)} lines)"
        body = "".join(f"{i}\t{lines[i - 1]}" for i in range(start, min(end, len(lines)) + 1))
        more = f"\n(file continues to line {len(lines)})" if end < len(lines) else ""
        return body + more

    def grep(self, pattern, path):
        cmd = ["git", "-C", self.root, "grep", "-n", "-I", "-E", "-e", pattern]
        if path:
            self._resolve(path)
            cmd += ["--", path]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if out.returncode > 1:
            return f"grep error: {out.stderr.strip()}"
        lines = out.stdout.splitlines()
        extra = f"\n({len(lines) - MAX_GREP_LINES} more matches not shown)" if len(lines) > MAX_GREP_LINES else ""
        return "\n".join(lines[:MAX_GREP_LINES]) + extra or "(no matches)"

    def list_dir(self, path):
        full = self._resolve(path)
        return "\n".join(e + ("/" if os.path.isdir(os.path.join(full, e)) else "") for e in sorted(os.listdir(full)))

    def call(self, name, raw_args):
        try:
            args = json.loads(raw_args)
            if name == "read_file":
                return self.read_file(args["path"], args.get("start_line"), args.get("end_line"))
            if name == "grep":
                return self.grep(args["pattern"], args.get("path"))
            if name == "list_dir":
                return self.list_dir(args["path"])
            return f"unknown tool: {name}"
        except Exception as e:  # tool errors go back to the model, not up the stack
            return f"error: {e}"


def post(path, payload, key):
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:1000]
            if e.code not in RETRY_STATUSES or attempt == 4:
                raise RuntimeError(f"OpenAI API {e.code}: {body}") from None
        except urllib.error.URLError as e:
            if attempt == 4:
                raise RuntimeError(f"OpenAI API unreachable: {e.reason}") from None
        time.sleep(2 ** attempt * 3)


def load_brief():
    match = re.search(r"```\n(.*?)\n```", BRIEF.read_text(), re.S)
    if not match:
        sys.exit(f"no fenced brief found in {BRIEF}")
    return match.group(1)


def split_diff(diff_text):
    files, current = {}, None
    for line in diff_text.splitlines(keepends=True):
        header = re.match(r"diff --git a/(.+?) b/(.+)$", line.rstrip("\n"))
        if header:
            current = header.group(2)
            files[current] = ""
        if current:
            files[current] += line
    return files


def verify_one(candidate, ctx):
    hunks = ctx["diff"].get(candidate["path"], "(no diff hunks for this path)")[:MAX_HUNK_CHARS]
    user = (
        f"PR intent:\n{ctx['intent']}\n\n"
        f"Claim id: {candidate['id']}\n"
        f"Location: {candidate['path']}:{candidate.get('line')}\n"
        f"Claim: {candidate['claim']}\n"
        f"Failure scenario: {candidate['failure_scenario']}\n\n"
        f"Diff for {candidate['path']}:\n```diff\n{hunks}\n```"
    )
    items = [{"role": "user", "content": user}]
    for turn in range(ctx["max_turns"]):
        payload = {
            "model": ctx["model"],
            "instructions": ctx["brief"],
            "input": items,
            "tools": TOOLS,
            "tool_choice": "auto" if turn < ctx["max_turns"] - 1 else "none",
            "text": {"format": {"type": "json_schema", "name": "verdict", "schema": VERDICT_SCHEMA, "strict": True}},
            "store": False,
            "include": ["reasoning.encrypted_content"],
        }
        if ctx["effort"] != "default":
            payload["reasoning"] = {"effort": ctx["effort"]}
        resp = post("/responses", payload, ctx["key"])
        output = resp.get("output", [])
        calls = [o for o in output if o.get("type") == "function_call"]
        if not calls:
            text = "".join(
                c.get("text", "")
                for o in output if o.get("type") == "message"
                for c in o.get("content", []) if c.get("type") == "output_text"
            )
            verdict = json.loads(text)
            verdict["id"] = candidate["id"]
            return verdict
        items += output
        items += [
            {"type": "function_call_output", "call_id": c["call_id"], "output": ctx["repo"].call(c["name"], c["arguments"])}
            for c in calls
        ]
    raise RuntimeError("no verdict within the turn limit")


def safe_verify(candidate, ctx):
    try:
        return verify_one(candidate, ctx)
    except Exception as e:
        return {"id": candidate["id"], "verdict": "ERROR", "evidence": "", "unknown": str(e)}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", help="review worktree at the PR head")
    p.add_argument("--candidates", help="JSON array of {id, path, line, claim, failure_scenario}")
    p.add_argument("--intent", help="file with the PR intent summary")
    p.add_argument("--diff", help="the PR diff")
    p.add_argument("--out", help="where to write the verdicts JSON array")
    p.add_argument("--model", default=os.environ.get("PR_REVIEW_OPENAI_MODEL"))
    p.add_argument("--effort", default="high", help="reasoning effort, or 'default' to omit")
    p.add_argument("--max-turns", type=int, default=20)
    p.add_argument("--list-models", action="store_true", help="print the model ids this key can use")
    args = p.parse_args()

    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        sys.exit("OPENAI_API_KEY is not set")
    if args.list_models:
        print("\n".join(sorted(m["id"] for m in post("/models", None, key)["data"])))
        return
    missing = [f for f in ("root", "candidates", "intent", "diff", "out") if not getattr(args, f)]
    if missing:
        sys.exit("missing: " + ", ".join("--" + m.replace("_", "-") for m in missing))
    if not args.model:
        sys.exit("set PR_REVIEW_OPENAI_MODEL or pass --model (see --list-models)")

    candidates = json.loads(Path(args.candidates).read_text())
    ctx = {
        "key": key,
        "model": args.model,
        "effort": args.effort,
        "max_turns": args.max_turns,
        "brief": load_brief(),
        "intent": Path(args.intent).read_text(),
        "diff": split_diff(Path(args.diff).read_text()),
        "repo": Repo(args.root),
    }
    with ThreadPoolExecutor(max_workers=min(8, len(candidates)) or 1) as pool:
        verdicts = list(pool.map(lambda c: safe_verify(c, ctx), candidates))
    Path(args.out).write_text(json.dumps(verdicts, indent=2))

    errors = [v for v in verdicts if v["verdict"] == "ERROR"]
    print(f"{len(verdicts) - len(errors)}/{len(verdicts)} verdicts written to {args.out}")
    for v in errors:
        print(f"  {v['id']}: {v['unknown']}", file=sys.stderr)
    sys.exit(1 if errors and len(errors) == len(verdicts) else 0)


if __name__ == "__main__":
    main()
