#!/usr/bin/env bash
# done-r — finish with this Claude session for good: exit claude, delete its
# session files, kill its tmux session and every process left in it, and let
# the Ghostty tab close (tab-start's outer shell exits when tmux ends).
# Run from inside Claude's own Bash tool; the work happens in a detached worker
# after the turn ends, because claude has to be gone before its files are deleted.
set -u

if [ "${1:-}" != "--worker" ]; then
  [ -n "${TMUX_PANE:-}" ] || { echo "not inside tmux; use /exit" >&2; exit 1; }
  [ -n "${CLAUDE_CODE_SESSION_ID:-}" ] || { echo "no CLAUDE_CODE_SESSION_ID; run this from inside claude" >&2; exit 1; }
  name=$(tmux display-message -p -t "$TMUX_PANE" '#{session_name}')
  DONE_R_PANE="$TMUX_PANE" DONE_R_CID="$CLAUDE_CODE_SESSION_ID" DONE_R_SOCKET="${TMUX%%,*}" \
    setsid "$0" --worker >/dev/null 2>&1 < /dev/null &
  echo "done-r: exiting claude, deleting session ${CLAUDE_CODE_SESSION_ID:0:8}, killing tmux session '$name', closing the tab in ~${DONE_R_DELAY:-3}s"
  exit 0
fi

# ---- worker -----------------------------------------------------------------
pane=$DONE_R_PANE cid=$DONE_R_CID socket=$DONE_R_SOCKET
unset TMUX TMUX_PANE      # so nothing we spawn matches the stray sweep below
sess=$(tmux display-message -p -t "$pane" '#{session_id}') || exit 1
say() { tmux display-message -t "$sess" "done-r: $*" 2>/dev/null; }

sleep "${DONE_R_DELAY:-3}"

# 1. Exit claude, and wait until the pane is back at a shell.
tmux send-keys -t "$pane" -l '/exit'; sleep 0.5; tmux send-keys -t "$pane" Enter
cmd=
for _ in $(seq 40); do
  cmd=$(tmux display-message -p -t "$pane" '#{pane_current_command}')
  case $cmd in zsh|bash|sh|fish) break;; esac
  sleep 0.5
done
case $cmd in zsh|bash|sh|fish) ;; *) say "claude did not exit; nothing deleted"; exit 1;; esac

# 2. Snapshot what's running in the session before it dies: pane processes and
# their descendants, plus anything (even daemonized) still carrying this tmux
# server + pane ids in its environment.
panes=$(tmux list-panes -s -t "$sess" -F '#{pane_id} #{pane_pid}')
descend() { local p; for p in "$@"; do echo "$p"; descend $(pgrep -P "$p" 2>/dev/null); done; }
victims=$(descend $(echo "$panes" | awk '{print $2}'))
if [ -d /proc ]; then
  for e in /proc/[0-9]*/environ; do
    p=${e#/proc/}; p=${p%/environ}
    [ -O "/proc/$p" ] && [ "$p" != "$$" ] || continue
    env=$(tr '\0' '\n' < "$e" 2>/dev/null) || continue
    case $env in *"TMUX=$socket,"*) ;; *) continue;; esac
    for pid_pane in $(echo "$panes" | awk '{print $1}'); do
      printf '%s\n' "$env" | grep -qx "TMUX_PANE=$pid_pane" && victims="$victims $p"
    done
  done
fi
victims=$(printf '%s\n' $victims | grep -vx "$$" | sort -un)

# 3. Delete the claude session's files (claude has exited, so nothing rewrites them).
shopt -s nullglob
pdirs=$(for t in ~/.claude/projects/*/"$cid".jsonl ~/.claude/projects/*/"$cid"; do dirname "$t"; done | sort -u)
rm -rf ~/.claude/projects/*/"$cid".jsonl ~/.claude/projects/*/"$cid" \
       ~/.claude/session-env/"$cid" ~/.claude/file-history/"$cid" \
       ~/.claude/tasks/"$cid" ~/.claude/todos/"$cid"* ~/.claude/debug/"$cid"* \
       /tmp/claude-"$(id -u)"/*/"$cid"
for d in $pdirs; do rmdir "$d" 2>/dev/null; done   # only the project dirs we just emptied
hist=~/.claude/history.jsonl
if [ -f "$hist" ] && grep -qF "$cid" "$hist"; then
  grep -vF "$cid" "$hist" > "$hist.done-r.$$"; chmod 600 "$hist.done-r.$$"; mv "$hist.done-r.$$" "$hist"
fi

# 4. Kill the tmux session (the tab's tmux client exits, then its shell, then the tab),
# then reap whatever ignored the hangup.
tmux kill-session -t "$sess"
sleep 2
for p in $victims; do kill -0 "$p" 2>/dev/null && kill -TERM "$p" 2>/dev/null; done
sleep 3
for p in $victims; do kill -0 "$p" 2>/dev/null && kill -KILL "$p" 2>/dev/null; done
exit 0
