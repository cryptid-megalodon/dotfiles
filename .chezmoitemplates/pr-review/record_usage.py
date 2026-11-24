#!/usr/bin/env python3
"""Run time and token usage for one pr-review pass.

Reads the Claude Code transcript of the session that ran the review (the main agent's API calls
and every subagent it started) and the files the OpenAI scripts wrote with --usage-out, and
records the result as `usage` in the pass's run-<k>.json. Stdlib only.

Everything the session did from the run record's `started_at` to now counts. Subagents are
assigned to stages by the first of these words in their Agent description: "correctness" ->
claude_correctness_finder, "convention" -> conventions_finder, "verif" -> claude_verifier;
anything else -> other_agents. OpenAI usage comes from openai-finders-usage-<k>.json and
openai-verifier-usage-<k>.json beside the run record.

Tokens have one shape for both model families: `input` is everything sent, cached or not;
`cache_read` and `cache_write` are parts of it; `output` includes reasoning; `reasoning` is the
part of output OpenAI reports as reasoning (null for Claude, which doesn't split it out).

  record_usage.py --run <review dir>/run-<k>.json
      At the end of a pass: writes `usage` into the run record.
  record_usage.py --session <id> --since <time> --until <time> [--run <file>]
      A past window, rebuilt from its transcript: printed, or written into --run as "backfilled".
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from codex_run import add_tokens

STAGES = (
    ("correctness", "claude_correctness_finder"),
    ("convention", "conventions_finder"),
    ("verif", "claude_verifier"),
)
OPENAI_FILES = (
    ("openai_correctness_finder", "openai-finders-usage-{k}.json"),
    ("openai_verifier", "openai-verifier-usage-{k}.json"),
)
ORDER = ("main", "claude_correctness_finder", "openai_correctness_finder", "conventions_finder",
         "claude_verifier", "openai_verifier", "other_agents")


def parse_time(text):
    """ISO 8601 with `Z` or a `-0500`-style offset, which fromisoformat rejects before 3.11."""
    if not text:
        return None
    text = re.sub(r"Z$", "+00:00", text.strip())
    text = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", text)
    moment = datetime.fromisoformat(text)
    return moment if moment.tzinfo else moment.astimezone()


def claude_tokens(usage):
    read = usage.get("cache_read_input_tokens") or 0
    write = usage.get("cache_creation_input_tokens") or 0
    return {
        "input": (usage.get("input_tokens") or 0) + read + write,
        "cache_read": read,
        "cache_write": write,
        "output": usage.get("output_tokens") or 0,
        "reasoning": None,
    }


def read_transcript(path, since, until):
    """API calls inside the window, one per message id, and the window's first and last record times."""
    calls, first, last = {}, None, None
    with open(path) as f:
        for line in f:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            moment = parse_time(record.get("timestamp"))
            if moment is None or not since <= moment <= until:
                continue
            first, last = min(first or moment, moment), max(last or moment, moment)
            message = record.get("message") or {}
            if record.get("type") != "assistant" or not message.get("usage"):
                continue
            if message.get("model") == "<synthetic>":  # Claude Code's local stand-ins, never billed
                continue
            # Claude Code writes one line per content block, each repeating the message's usage.
            calls.setdefault(message.get("id") or record.get("uuid"), message)
    tokens = None
    for message in calls.values():
        tokens = add_tokens(tokens, claude_tokens(message["usage"]))
    models = Counter(m.get("model") for m in calls.values())
    return {
        "model": models.most_common(1)[0][0] if models else None,
        "api_calls": len(calls),
        "tokens": tokens,
        "first": first,
        "last": last,
    }


def seconds(start, end):
    return round((end - start).total_seconds(), 1) if start and end else None


def stage_of(description):
    """The stage whose keyword comes first, so "Verify correctness claims" is a verifier."""
    lowered = (description or "").lower()
    hits = [(lowered.find(word), stage) for word, stage in STAGES if word in lowered]
    return min(hits)[1] if hits else "other_agents"


def claude_stages(session_file, since, until):
    """The main agent's usage, then each subagent with activity in the window, grouped by stage."""
    main = read_transcript(session_file, since, until)
    stages = {"main": {
        "model": main["model"],
        "wall_seconds": seconds(since, until),
        "api_calls": main["api_calls"],
        "tokens": main["tokens"],
    }}
    spans = {}
    for path in sorted((session_file.parent / session_file.stem / "subagents").glob("agent-*.jsonl")):
        run = read_transcript(path, since, until)
        if run["first"] is None:
            continue
        meta_path = path.with_suffix(".meta.json")
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        stage = stage_of(meta.get("description"))
        entry = stages.setdefault(stage, {"wall_seconds": None, "tokens": None, "runs": []})
        entry["runs"].append({
            "name": meta.get("description"),
            "agent_id": path.stem[len("agent-"):],
            "model": run["model"],
            "wall_seconds": seconds(run["first"], run["last"]),
            "api_calls": run["api_calls"],
            "tokens": run["tokens"],
        })
        entry["tokens"] = add_tokens(entry["tokens"], run["tokens"])
        start, end = spans.get(stage, (run["first"], run["last"]))
        spans[stage] = (min(start, run["first"]), max(end, run["last"]))
    for stage, (start, end) in spans.items():
        stages[stage]["wall_seconds"] = seconds(start, end)
    return stages


def openai_stages(run_path, record, gaps):
    stages, config = {}, record.get("config") or {}
    for stage, pattern in OPENAI_FILES:
        if stage in config and config[stage].get("model") is None:
            continue  # skipped this pass; the run record's own gaps say why
        path = run_path.parent / pattern.format(k=record.get("pass"))
        if not path.exists():
            gaps.append(f"{stage}: no {path.name}, so its time and tokens are unknown")
            continue
        usage = json.loads(path.read_text())
        stages[stage] = {
            "wall_seconds": usage["wall_seconds"],
            "tokens": usage["tokens"],
            "runs": [{"model": usage["model"], **call} for call in usage["calls"]],
        }
        for call in usage["calls"]:
            if call["tokens"] is None:
                gaps.append(f"{stage}: no token count for {call['name']} ({call['error'] or 'none reported'})")
    return stages


def short(n):
    if n is None:
        return "?"
    for size, unit in ((1e6, "M"), (1e3, "k")):
        if n >= size:
            return f"{n / size:.{2 if unit == 'M' else 1}f}{unit}"
    return str(n)


def summary_line(usage, k):
    wall = usage["wall_seconds"] or 0
    parts = [f"pr-review pass {k}" if k else "pr-review", f"{int(wall // 60)}m {int(wall % 60):02d}s"]
    for family, label in (("claude", "Claude"), ("openai", "OpenAI")):
        tokens = usage["totals"][family]
        if tokens:
            parts.append(f"{label} {short(tokens['input'])} in ({short(tokens['cache_read'])} cached), "
                         f"{short(tokens['output'])} out")
        else:
            parts.append(f"{label} tokens unknown")
    return " · ".join(parts)


def write_json(path, data):
    """Rewrite a JSON file keeping its existing indent width."""
    lines = path.read_text().splitlines()
    second = lines[1] if len(lines) > 1 else ""
    indent = (len(second) - len(second.lstrip(" "))) or 2
    path.write_text(json.dumps(data, indent=indent, ensure_ascii=False) + "\n")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run", help="the pass's run-<k>.json; usage is written into it")
    p.add_argument("--session", default=os.environ.get("CLAUDE_CODE_SESSION_ID"),
                   help="Claude Code session id (default: $CLAUDE_CODE_SESSION_ID, the current session)")
    p.add_argument("--since", help="window start (default: the run record's started_at)")
    p.add_argument("--until", help="window end (default: now); setting it marks the usage backfilled")
    args = p.parse_args()

    run_path = Path(args.run) if args.run else None
    record = json.loads(run_path.read_text()) if run_path else {}
    since = parse_time(args.since or record.get("started_at"))
    until = parse_time(args.until) if args.until else datetime.now(timezone.utc)
    if since is None:
        sys.exit("no window start: pass --since or a run record with started_at")
    if not args.session:
        sys.exit("no session id: pass --session (CLAUDE_CODE_SESSION_ID is unset)")
    projects = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")) / "projects"
    transcripts = sorted(projects.glob(f"*/{args.session}.jsonl"), key=lambda f: f.stat().st_size)
    if not transcripts:
        sys.exit(f"no transcript for session {args.session} under {projects}")

    gaps = []
    stages = claude_stages(transcripts[-1], since, until)
    if run_path:
        stages.update(openai_stages(run_path, record, gaps))
    else:
        gaps.append("OpenAI stages: not included without --run")
    totals = {"claude": None, "openai": None}
    for stage, entry in stages.items():
        family = "openai" if stage.startswith("openai_") else "claude"
        totals[family] = add_tokens(totals[family], entry["tokens"])
    usage = {
        "source": "backfilled" if args.until else "recorded",
        "session_id": args.session,
        "started_at": since.astimezone().isoformat(timespec="seconds"),
        "ended_at": until.astimezone().isoformat(timespec="seconds"),
        "wall_seconds": seconds(since, until),
        "totals": totals,
        "stages": {stage: stages[stage] for stage in ORDER if stage in stages},
        "gaps": gaps,
    }

    if run_path:
        record["usage"] = usage
        write_json(run_path, record)
    else:
        print(json.dumps(usage, indent=2))
    print(summary_line(usage, record.get("pass")))


if __name__ == "__main__":
    main()
