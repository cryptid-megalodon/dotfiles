#!/usr/bin/env python3
"""OpenAI correctness finders for the pr-review skill.

Runs one `codex exec` per filled finder brief (one brief per chunk, the same text the Claude
finder for that chunk gets), in a read-only sandbox rooted at the review worktree, and writes each
chunk's candidates as a JSON array named after the brief. Chunks run in parallel. Stdlib only.

Requires `codex` on PATH and logged in (`codex login status`).
"""

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from codex_run import CodexError, run_codex

CANDIDATE = {
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        "line": {"type": "integer"},
        "claim": {"type": "string"},
        "failure_scenario": {"type": "string"},
        "rule": {"type": ["string", "null"]},
        "severity": {"type": "string", "enum": ["Blocking", "Should fix", "Nit", "Question"]},
    },
    "required": ["path", "line", "claim", "failure_scenario", "rule", "severity"],
    "additionalProperties": False,
}
# Structured output needs an object at the root, so the array is wrapped and unwrapped here.
SCHEMA = {
    "type": "object",
    "properties": {"candidates": {"type": "array", "items": CANDIDATE}},
    "required": ["candidates"],
    "additionalProperties": False,
}
FORMAT_NOTE = (
    "\n\nOutput format: return the JSON array described above wrapped in an object, "
    'as {"candidates": [...]}; use {"candidates": []} if nothing survives.'
)


def find_one(brief_path, ctx):
    try:
        result = run_codex(ctx["root"], ctx["model"], ctx["effort"], SCHEMA,
                           brief_path.read_text() + FORMAT_NOTE, ctx["timeout"])
        candidates = result["candidates"]
    except (CodexError, KeyError) as e:
        return brief_path.name, str(e)
    (ctx["out_dir"] / f"{brief_path.stem}.json").write_text(json.dumps(candidates, indent=2))
    return brief_path.name, None


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", required=True, help="review worktree at the PR head")
    p.add_argument("--briefs", required=True, nargs="+", help="filled finder briefs, one per chunk")
    p.add_argument("--out-dir", required=True, help="where to write <brief-stem>.json per chunk")
    p.add_argument("--model", required=True)
    p.add_argument("--effort", default="high", help="model_reasoning_effort for codex")
    p.add_argument("--timeout", type=int, default=1200, help="seconds per chunk")
    args = p.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ctx = {
        "root": os.path.realpath(args.root),
        "model": args.model,
        "effort": args.effort,
        "timeout": args.timeout,
        "out_dir": out_dir,
    }
    briefs = [Path(b) for b in args.briefs]
    with ThreadPoolExecutor(max_workers=min(5, len(briefs))) as pool:
        results = list(pool.map(lambda b: find_one(b, ctx), briefs))

    errors = [(name, err) for name, err in results if err]
    print(f"{len(results) - len(errors)}/{len(results)} chunks written to {out_dir}")
    for name, err in errors:
        print(f"  {name}: {err}", file=sys.stderr)
    sys.exit(1 if errors and len(errors) == len(results) else 0)


if __name__ == "__main__":
    main()
