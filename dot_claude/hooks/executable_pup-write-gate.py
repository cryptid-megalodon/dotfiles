#!/usr/bin/env python3
"""PreToolUse(Bash) gate for the Datadog `pup` CLI.

pup authenticates with a token that can write, so read-only is only a
convention. This hook makes every non-read pup command stop for the user's
approval:

- pup reads (list/get/search/query/diff/...) and the plugin's read-only
  wrapper pass through with no decision.
- Anything else pup does asks, with the full command and, for
  `update --file`, pup's own read-only diff against the live resource.
- pup commands it cannot parse (wrapped in `bash -c`, `env`, `xargs`,
  substitutions, ...) ask too, so an unusual spelling never slips past.
- Raw HTTP to Datadog hosts and token extraction are denied outright.

No output and exit 0 means "no opinion"; normal permission rules apply.
"""

import json
import os
import re
import shlex
import subprocess
import sys

READ_VERBS = {
    "list", "get", "search", "query", "diff", "show", "describe", "aggregate",
    "tail", "status", "count", "history", "help", "version", "validate",
}
READ_FLAGS = {"-h", "--help", "-V", "--version"}
AUTH_OK = {"login", "logout", "status", "refresh"}

DD_HOST = re.compile(r"datadoghq\.(com|eu)|ddog-gov\.com", re.I)
RAW_HTTP = re.compile(r"\b(curl|wget|http|https|nc|ncat|python3?|node|ruby|perl)\b", re.I)
TOKEN_LEAK = [
    re.compile(r"\bpup\s+auth\s+(token|export)\b"),
    re.compile(r"security\s+find-generic-password.*(pup|datadog)", re.I),
    re.compile(r"\b(echo|printf|printenv|env)\b[^|;&]*\bDD_(API|APP)_KEY\b"),
    re.compile(r"\$\{?DD_TOKEN\b"),
]
# `pup` as a command word: not part of a path or a longer name like pup-readonly.sh.
PUP_WORD = re.compile(r"(?<![\w./-])pup(?![\w.-])")
WRAPPER = re.compile(r"(^|/)pup-readonly\.sh$")
ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
SEPARATORS = re.compile(r"&&|\|\||[;|\n]")


def decide(decision, reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }}))
    sys.exit(0)


def is_pup(word):
    return word == "pup" or word.endswith("/pup")


def split_segment(segment):
    """Return argv for a simple command, or None if it isn't one."""
    if "$(" in segment or "`" in segment or "<(" in segment:
        return None
    try:
        argv = shlex.split(segment)
    except ValueError:
        return None
    while argv and ENV_ASSIGN.match(argv[0]):
        argv = argv[1:]
    return argv


def verbs_of(args):
    """Subcommand words before the first flag, e.g. ['monitors', 'update']."""
    out = []
    for a in args:
        if a.startswith("-"):
            break
        out.append(a)
    return out


def file_arg(args):
    for i, a in enumerate(args):
        if a in ("--file", "-f") and i + 1 < len(args):
            return args[i + 1]
        if a.startswith("--file="):
            return a.split("=", 1)[1]
    return None


def format_diff(raw):
    """One line per change. Updates are partial, so "removed" may not delete."""
    try:
        changes = json.loads(raw)
        changes = changes.get("data", changes) if isinstance(changes, dict) else changes
    except ValueError:
        return raw.strip()
    lines = []
    for c in changes:
        kind = c.get("change")
        if kind == "removed":
            lines.append(f"  - {c['path']}: {json.dumps(c.get('before'))} (missing or null in file; a partial update may keep it)")
        elif kind == "added":
            lines.append(f"  + {c['path']}: {json.dumps(c.get('after'))}")
        else:
            lines.append(f"  ~ {c['path']}: {json.dumps(c.get('before'))} -> {json.dumps(c.get('after'))}")
    return "\n".join(lines) or "  (no changes)"


def preview(argv):
    """Best-effort read-only preview of what a write would change."""
    args = argv[1:]
    words = verbs_of(args)
    path = file_arg(args)
    if not path:
        return ""
    path = os.path.expanduser(path)
    # `pup <group> update <id> --file F` -> `pup <group> diff <id> F`
    if len(words) >= 3 and words[1] == "update":
        env = dict(os.environ, DD_READ_ONLY="true")
        try:
            r = subprocess.run(
                [argv[0], words[0], "diff", words[2], path, "--no-agent"],
                capture_output=True, text=True, timeout=20, env=env,
            )
            if r.returncode == 0 and r.stdout.strip():
                return "\n\npup diff against the live resource:\n" + format_diff(r.stdout)[:3000]
        except (OSError, subprocess.TimeoutExpired):
            pass
    try:
        with open(path) as f:
            return f"\n\nContents of {path}:\n" + f.read()[:3000]
    except OSError:
        return f"\n\n(could not read {path})"


def classify(argv):
    """Return None for a read, or a reason string for a write."""
    args = argv[1:]
    if not args or any(a in READ_FLAGS for a in args):
        return None
    words = verbs_of(args)
    if words[:1] == ["auth"]:
        return None if words[1:2] and words[1] in AUTH_OK else "pup auth " + " ".join(words[1:])
    if any(w in READ_VERBS for w in words[1:]):
        return None
    return "pup " + " ".join(words) + " is not a known read command"


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return
    cmd = (payload.get("tool_input") or {}).get("command") or ""

    for pattern in TOKEN_LEAK:
        if pattern.search(cmd):
            decide("deny", "Blocked: this would expose the Datadog auth token. "
                           "The token must stay inside pup.")
    if DD_HOST.search(cmd) and RAW_HTTP.search(cmd):
        decide("deny", "Blocked: raw HTTP to Datadog bypasses pup's read-only "
                       "mode. Use pup (reads) or ask the user to run the write.")

    if not PUP_WORD.search(cmd):
        return

    writes = []
    for segment in SEPARATORS.split(cmd):
        if not PUP_WORD.search(segment):
            continue
        argv = split_segment(segment.strip())
        if argv and WRAPPER.search(argv[0]):
            continue  # the read-only wrapper; pup refuses writes there
        if not argv or not is_pup(argv[0]):
            decide("ask", "pup is used in a form this gate can't parse "
                          "(wrapped, substituted, or piped into). Review the "
                          "full command before approving:\n\n" + cmd)
        reason = classify(argv)
        if reason:
            writes.append((argv, reason))

    if writes:
        argv, reason = writes[0]
        decide("ask", f"Datadog write: {reason}.\n\n{shlex.join(argv)}" + preview(argv))


if __name__ == "__main__":
    main()
