"""Shared `codex exec` runner for the pr-review scripts.

Runs one read-only, ephemeral Codex session rooted at the review worktree and returns its final
message parsed against a JSON schema, with the call's wall time and token usage. The user's
~/.codex/config.toml is ignored so its defaults (model, effort, permissions) can't leak in; auth
still comes from CODEX_HOME.

Tokens are normalized to the shape record_usage.py records for both model families: `cache_read`
and `cache_write` are parts of `input`, and `reasoning` is part of `output`.
"""

import json
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path

TOKEN_KEYS = ("input", "cache_read", "cache_write", "output", "reasoning")
# `turn.completed` usage field in `codex exec --json` -> normalized key
CODEX_USAGE = {
    "input_tokens": "input",
    "cached_input_tokens": "cache_read",
    "cache_write_input_tokens": "cache_write",
    "output_tokens": "output",
    "reasoning_output_tokens": "reasoning",
}


class CodexError(Exception):
    def __init__(self, message, stats):
        super().__init__(message)
        self.stats = stats


def add_tokens(total, tokens):
    """Sum normalized token counts; a key stays null only while every addend lacks it."""
    if tokens is None:
        return total
    total = dict(total or dict.fromkeys(TOKEN_KEYS))
    for key in TOKEN_KEYS:
        if tokens.get(key) is not None:
            total[key] = (total[key] or 0) + tokens[key]
    return total


def read_events(stdout):
    """Tokens summed over completed turns, and error messages, from `codex exec --json` output."""
    tokens, errors = None, []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        if kind == "turn.completed":
            usage = event.get("usage") or {}
            tokens = add_tokens(tokens, {CODEX_USAGE[k]: v for k, v in usage.items() if k in CODEX_USAGE})
        elif kind in ("turn.failed", "error"):
            # A failure usually arrives as both events with the same message.
            message = (event.get("error") or {}).get("message") or event.get("message") or kind
            if message not in errors:
                errors.append(message)
    return tokens, errors


def run_codex(root, model, effort, schema, prompt, timeout):
    """Return (parsed final message, stats); stats is {wall_seconds, tokens} and rides on CodexError too."""
    with tempfile.TemporaryDirectory() as tmp:
        schema_path = Path(tmp) / "schema.json"
        schema_path.write_text(json.dumps(schema))
        last = Path(tmp) / "last.json"
        cmd = [
            "codex", "exec",
            "-C", root,
            "-s", "read-only",
            "--ephemeral",
            "--ignore-user-config",
            "--color", "never",
            "--json",
            "-m", model,
            "-c", f"model_reasoning_effort={effort}",
            "--output-schema", str(schema_path),
            "-o", str(last),
            "-",
        ]
        start = time.monotonic()
        try:
            run = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as e:
            out = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
            stats = {"wall_seconds": round(time.monotonic() - start, 1), "tokens": read_events(out)[0]}
            raise CodexError(f"timed out after {timeout}s", stats) from None
        tokens, errors = read_events(run.stdout)
        stats = {"wall_seconds": round(time.monotonic() - start, 1), "tokens": tokens}
        if run.returncode != 0 or not last.exists():
            # With --json, codex reports failures as events on stdout, not on stderr.
            detail = "; ".join(errors) or run.stderr.strip()[-1000:]
            raise CodexError(f"codex exit {run.returncode}: {detail}", stats)
        try:
            return json.loads(last.read_text()), stats
        except json.JSONDecodeError as e:
            raise CodexError(f"unparseable output: {e}", stats) from None


def now_local():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def write_usage(path, stage, model, effort, started_at, wall_seconds, calls):
    """Write one stage's usage file for record_usage.py: totals, then each call's time, tokens, error."""
    tokens = None
    for call in calls:
        tokens = add_tokens(tokens, call["tokens"])
    Path(path).write_text(json.dumps({
        "stage": stage,
        "model": model,
        "effort": effort,
        "started_at": started_at,
        "wall_seconds": wall_seconds,
        "tokens": tokens,
        "calls": calls,
    }, indent=2))
