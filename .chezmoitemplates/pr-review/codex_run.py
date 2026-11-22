"""Shared `codex exec` runner for the pr-review scripts.

Runs one read-only, ephemeral Codex session rooted at the review worktree and returns its final
message parsed against a JSON schema. The user's ~/.codex/config.toml is ignored so its defaults
(model, effort, permissions) can't leak in; auth still comes from CODEX_HOME.
"""

import json
import subprocess
import tempfile
from pathlib import Path


class CodexError(Exception):
    pass


def run_codex(root, model, effort, schema, prompt, timeout):
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
            "-m", model,
            "-c", f"model_reasoning_effort={effort}",
            "--output-schema", str(schema_path),
            "-o", str(last),
            "-",
        ]
        try:
            run = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise CodexError(f"timed out after {timeout}s") from None
        if run.returncode != 0 or not last.exists():
            raise CodexError(f"codex exit {run.returncode}: {run.stderr.strip()[-1000:]}")
        try:
            return json.loads(last.read_text())
        except json.JSONDecodeError as e:
            raise CodexError(f"unparseable output: {e}") from None
