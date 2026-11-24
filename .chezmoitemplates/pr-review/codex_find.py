#!/usr/bin/env python3
"""OpenAI correctness finders for the pr-review skill.

Runs one `codex exec` per filled finder brief (one brief per chunk, the same text the Claude
finder for that chunk gets), in a read-only sandbox rooted at the review worktree, and writes each
chunk's candidates as a JSON array named after the brief. Chunks run in parallel. With
--usage-out, also writes each chunk's wall time and tokens for record_usage.py. Stdlib only.

Requires `codex` on PATH and logged in (`codex login status`).
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from codex_run import CodexError, now_local, run_codex, write_usage

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
    call = {"name": brief_path.stem, "wall_seconds": None, "tokens": None, "error": None}
    try:
        result, stats = run_codex(ctx["root"], ctx["model"], ctx["effort"], SCHEMA,
                                  brief_path.read_text() + FORMAT_NOTE, ctx["timeout"])
        call.update(stats)
        candidates = result["candidates"]
    except CodexError as e:
        call.update(e.stats, error=str(e))
        return call
    except KeyError as e:
        call["error"] = f"no {e} in output"
        return call
    (ctx["out_dir"] / f"{brief_path.stem}.json").write_text(json.dumps(candidates, indent=2))
    return call


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", required=True, help="review worktree at the PR head")
    p.add_argument("--briefs", required=True, nargs="+", help="filled finder briefs, one per chunk")
    p.add_argument("--out-dir", required=True, help="where to write <brief-stem>.json per chunk")
    p.add_argument("--model", required=True)
    p.add_argument("--effort", default="high", help="model_reasoning_effort for codex")
    p.add_argument("--timeout", type=int, default=1200, help="seconds per chunk")
    p.add_argument("--usage-out", help="where to write wall time and tokens per chunk")
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
    started_at, start = now_local(), time.monotonic()
    with ThreadPoolExecutor(max_workers=min(5, len(briefs))) as pool:
        calls = list(pool.map(lambda b: find_one(b, ctx), briefs))
    if args.usage_out:
        write_usage(args.usage_out, "openai_correctness_finder", args.model, args.effort,
                    started_at, round(time.monotonic() - start, 1), calls)

    errors = [c for c in calls if c["error"]]
    print(f"{len(calls) - len(errors)}/{len(calls)} chunks written to {out_dir}")
    for c in errors:
        print(f"  {c['name']}: {c['error']}", file=sys.stderr)
    sys.exit(1 if errors and len(errors) == len(calls) else 0)


if __name__ == "__main__":
    main()
