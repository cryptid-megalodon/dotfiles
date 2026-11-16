#!/usr/bin/env bash
# rename-r — rename this Claude session, its tmux session, and (via tmux
# set-titles) the Ghostty tab, in one go. Run from inside Claude's own Bash tool.
set -eu

# macOS has no setsid command; perl's POSIX::setsid does the same job there.
if ! command -v setsid >/dev/null; then
  setsid() { perl -MPOSIX -e 'POSIX::setsid(); exec { $ARGV[0] } @ARGV or die "exec $ARGV[0]: $!\n"' -- "$@"; }
fi

name="$*"
[ -n "$name" ] || { echo "usage: rename-r.sh <name>" >&2; exit 2; }
[ -n "${TMUX_PANE:-}" ] || { echo "not inside tmux; nothing to rename (use /rename)" >&2; exit 1; }

# tmux session names can't contain ':' or '.'.
tname=$(printf '%s' "$name" | tr ':.' '--')

sid=$(tmux display-message -p -t "$TMUX_PANE" '#{session_id}')
tmux rename-session -t "$sid" "$tname"
# The session name becomes the terminal title, which Ghostty shows as the tab title.
tmux set-option -t "$sid" set-titles on
tmux set-option -t "$sid" set-titles-string '#S'
echo "tmux session + tab: $tname"

# /rename is a built-in command, so type it into Claude's own pane once this
# turn has finished. Detached so it outlives the tool call.
pane="$TMUX_PANE"
RENAME_NAME="$name" RENAME_PANE="$pane" setsid bash -c '
  sleep "${RENAME_R_DELAY:-3}"
  tmux send-keys -t "$RENAME_PANE" -l "/rename $RENAME_NAME"
  sleep 0.5
  tmux send-keys -t "$RENAME_PANE" Enter
' >/dev/null 2>&1 < /dev/null &
echo "claude session: /rename queued for ${RENAME_R_DELAY:-3}s from now"
