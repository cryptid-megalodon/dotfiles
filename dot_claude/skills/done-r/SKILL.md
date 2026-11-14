---
name: done-r
description: Finish with this session for good — exit Claude, delete its session files and prompt history, kill the tmux session and every process left in it, and close the Ghostty tab. Use only when the user explicitly says "done-r", "kill it all", "close out this session", or "tear everything down". Destructive and irreversible.
allowed-tools: Bash
disable-model-invocation: true
---

# done-r

Tears down everything `tab-start` set up for this session, leaving no orphans or leftover files.

Run it, then stop — don't start more work, because Claude exits a few seconds after this turn ends:

```bash
~/.claude/skills/done-r/done-r.sh
```

Reply with one line saying what it announced. Nothing to confirm: the user invoked it on purpose, and the
deletion can't be undone.

What the detached worker does, in order:
1. Types `/exit` into this pane and waits for the shell prompt. If Claude doesn't exit, it stops and deletes
   **nothing** (tmux shows "done-r: claude did not exit").
2. Snapshots every process in the tmux session: pane process trees, plus anything daemonized that still carries
   the tmux pane in its environment (Linux; elsewhere the process trees only).
3. Deletes this session's transcript, subagent/tool-result dir, `session-env`, `file-history`, `/tmp/claude-<uid>`
   scratch dir, and its `history.jsonl` lines, then removes the project dir if that left it empty.
4. Kills the tmux session, so tab-start's outer shell exits and the tab closes. Survivors of the hangup get
   SIGTERM, then SIGKILL 3s later.

Outside tmux the script exits 1 and does nothing; use `/exit`. `DONE_R_DELAY=<s>` changes the wait before
`/exit` is typed (default 3). Earlier sessions in the same tmux session (before a `/clear` or `/resume`) keep
their files; only the current session id is deleted.
