#!/usr/bin/env python3
"""Cross-family verifier for the pr-review skill.

Runs one `codex exec` per candidate finding, with the shared verifier brief, in a read-only
sandbox rooted at the review worktree, and writes one verdict per candidate. Candidates run in
parallel. With --usage-out, also writes each candidate's wall time and tokens for record_usage.py.
Stdlib only.

Requires `codex` on PATH and logged in (`codex login status`).
"""

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from codex_run import CodexError, now_local, run_codex, write_usage

BRIEF = Path(__file__).resolve().parent.parent / "reference" / "verifier-brief.md"
MAX_HUNK_CHARS = 20_000

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
    prompt = (
        f"{ctx['brief']}\n\n"
        f"The repository at the PR head is your working directory.\n\n"
        f"PR intent:\n{ctx['intent']}\n\n"
        f"Claim id: {candidate['id']}\n"
        f"Location: {candidate['path']}:{candidate.get('line')}\n"
        f"Claim: {candidate['claim']}\n"
        f"Failure scenario: {candidate['failure_scenario']}\n\n"
        f"Diff for {candidate['path']}:\n```diff\n{hunks}\n```"
    )
    call = {"name": candidate["id"], "wall_seconds": None, "tokens": None, "error": None}
    try:
        verdict, stats = run_codex(ctx["root"], ctx["model"], ctx["effort"], VERDICT_SCHEMA, prompt, ctx["timeout"])
    except CodexError as e:
        call.update(e.stats, error=str(e))
        return {"id": candidate["id"], "verdict": "ERROR", "evidence": "", "unknown": str(e)}, call
    call.update(stats)
    verdict["id"] = candidate["id"]
    return verdict, call


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", required=True, help="review worktree at the PR head")
    p.add_argument("--candidates", required=True, help="JSON array of {id, path, line, claim, failure_scenario}")
    p.add_argument("--intent", required=True, help="file with the PR intent summary")
    p.add_argument("--diff", required=True, help="the PR diff")
    p.add_argument("--out", required=True, help="where to write the verdicts JSON array")
    p.add_argument("--model", required=True)
    p.add_argument("--effort", default="medium", help="model_reasoning_effort for codex")
    p.add_argument("--timeout", type=int, default=900, help="seconds per candidate")
    p.add_argument("--usage-out", help="where to write wall time and tokens per candidate")
    args = p.parse_args()

    candidates = json.loads(Path(args.candidates).read_text())
    ctx = {
        "root": os.path.realpath(args.root),
        "model": args.model,
        "effort": args.effort,
        "timeout": args.timeout,
        "brief": load_brief(),
        "intent": Path(args.intent).read_text(),
        "diff": split_diff(Path(args.diff).read_text()),
    }
    started_at, start = now_local(), time.monotonic()
    with ThreadPoolExecutor(max_workers=min(8, len(candidates)) or 1) as pool:
        results = list(pool.map(lambda c: verify_one(c, ctx), candidates))
    verdicts = [verdict for verdict, _ in results]
    Path(args.out).write_text(json.dumps(verdicts, indent=2))
    if args.usage_out:
        write_usage(args.usage_out, "openai_verifier", args.model, args.effort,
                    started_at, round(time.monotonic() - start, 1), [call for _, call in results])

    errors = [v for v in verdicts if v["verdict"] == "ERROR"]
    print(f"{len(verdicts) - len(errors)}/{len(verdicts)} verdicts written to {args.out}")
    for v in errors:
        print(f"  {v['id']}: {v['unknown']}", file=sys.stderr)
    sys.exit(1 if errors and len(errors) == len(verdicts) else 0)


if __name__ == "__main__":
    main()
