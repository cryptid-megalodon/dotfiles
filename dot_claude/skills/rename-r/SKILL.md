---
name: rename-r
description: Rename this Claude session, the tmux session it runs in, and the Ghostty tab — all to one name ("rename recursive"). Use when the user says "rename-r", "rename everything to X", "name this session/tab X", or wants the Claude session, tmux session and terminal tab to share a name. With no name given, propose one from the conversation.
allowed-tools: Bash
---

# rename-r

One name for three things: the Claude session (`/rename`), the tmux session, and the Ghostty tab (which
shows the tmux session name via tmux `set-titles`).

1. Take the name from the user's args. If none was given, propose a short (2–4 word) kebab-case or plain
   name from what this session is about, and ask once before running.
2. Run it:

   ```bash
   ~/.claude/skills/rename-r/rename-r.sh "<name>"
   ```

3. Report the result in one line. Don't run `/rename` yourself — you can't; the script types it into this
   pane a few seconds after the turn, and Claude prints "Session renamed to: …".

Notes:
- tmux session names can't contain `:` or `.`; the script swaps them for `-` for tmux only. Claude's name is
  kept as given.
- Outside tmux the script exits 1 and renames nothing; tell the user to use plain `/rename`.
- `RENAME_R_DELAY=<seconds>` changes the wait before `/rename` is typed (default 3).
