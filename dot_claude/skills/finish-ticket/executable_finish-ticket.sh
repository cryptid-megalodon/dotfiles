#!/usr/bin/env bash
#
# finish-ticket.sh — clean up a ticket's worktrees and local branches after its PRs merge.
#
# Usage: finish-ticket.sh <TICKET> [--apply] [--root DIR]...
#
# Finds every git clone under the roots (default: ~/repos), then every local branch and
# worktree belonging to the ticket: branches containing the ticket key as a token
# (BOT-123-foo, feat-user-bot-123-foo) and worktrees on those branches or at a path named
# after the ticket. Case-insensitive.
#
# A branch is cleaned up only if all of these hold:
#   - it has a merged PR on GitHub
#   - its local tip is exactly that PR's merged head (no unpushed or post-merge commits),
#     which is what makes `git branch -D` safe after a squash merge
#   - its worktree, if any, has no uncommitted or untracked changes
#   - it isn't checked out in the clone's main checkout
# Anything else is reported as SKIP with the reason, and left alone.
#
# Without --apply this is a dry run and changes nothing. With --apply, for each verified
# branch: `git worktree remove` (never --force), then `git branch -D`, then one
# `git fetch --prune origin` per affected clone to drop remote-tracking refs for branches
# GitHub already deleted.
#
# Exit codes:
#   0  dry run finished, or everything planned was applied
#   1  invalid arguments or missing tool (git, gh, jq)
#   2  nothing belonging to the ticket was found
#   3  at least one branch or worktree was skipped or failed; see the SKIP/FAIL lines

set -uo pipefail

usage() { echo "Usage: finish-ticket.sh <TICKET> [--apply] [--root DIR]..." >&2; exit 1; }

ticket="" apply=false roots=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) apply=true; shift ;;
    --root)  [[ $# -ge 2 ]] || usage; roots+=("$2"); shift 2 ;;
    -h|--help) sed -n '2,31p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) usage ;;
    *) [[ -z "$ticket" ]] || usage; ticket="$1"; shift ;;
  esac
done
[[ "$ticket" =~ ^[A-Za-z][A-Za-z0-9]*-[0-9]+$ ]] || { echo "Ticket must look like BOT-123, got '$ticket'" >&2; exit 1; }
[[ ${#roots[@]} -gt 0 ]] || roots=("$HOME/repos")
for tool in git gh jq; do
  command -v "$tool" >/dev/null || { echo "$tool is required" >&2; exit 1; }
done

ticket_lc=$(printf '%s' "$ticket" | tr '[:upper:]' '[:lower:]')
# The ticket key as a whole token, so BOT-12 doesn't match bot-123.
token_re="(^|[-/_])${ticket_lc}([-/_]|$)"

matches_ticket() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | grep -Eq "$token_re"; }

# owner/repo from the origin URL (SSH or HTTPS).
gh_slug() {
  git -C "$1" remote get-url origin 2>/dev/null |
    sed -E 's#^(git@|ssh://git@|https://)github\.com[:/]##; s#\.git$##'
}

found=0 skipped=0
$apply && mode="APPLY" || mode="DRY RUN (pass --apply to clean up)"
echo "finish-ticket $ticket — $mode"

clones=()
for root in "${roots[@]}"; do
  [[ -d "$root" ]] || { echo "Root not found: $root" >&2; continue; }
  while IFS= read -r gitdir; do clones+=("$(dirname "$gitdir")"); done < <(
    find "$root" -maxdepth 6 \( -name node_modules -o -name target -o -name '*-worktrees' \) -prune \
      -o -type d -name .git -print -prune 2>/dev/null
  )
done
[[ ${#clones[@]} -gt 0 ]] || { echo "Nothing found for $ticket: no git clones under ${roots[*]}"; exit 2; }

for clone in "${clones[@]}"; do
  # Worktrees as "path<TAB>branch" (branch empty when detached); the first entry is the main checkout.
  worktrees=$(git -C "$clone" worktree list --porcelain 2>/dev/null | awk '
    /^worktree / { if (p != "") print p "\t" b; p = substr($0, 10); b = "" }
    /^branch /   { b = substr($0, 8); sub("^refs/heads/", "", b) }
    END          { if (p != "") print p "\t" b }')
  main_path=$(printf '%s\n' "$worktrees" | head -1 | cut -f1)

  branches=$(
    git -C "$clone" for-each-ref refs/heads --format='%(refname:short)' |
      while IFS= read -r b; do matches_ticket "$b" && echo "$b"; done
    printf '%s\n' "$worktrees" | tail -n +2 | while IFS=$'\t' read -r p b; do
      [[ -n "$b" ]] && { matches_ticket "$b" || matches_ticket "$(basename "$p")"; } && echo "$b"
    done
  )
  branches=$(printf '%s\n' "$branches" | sed '/^$/d' | sort -u)

  # Detached worktrees named after the ticket have no branch to verify against a PR.
  printf '%s\n' "$worktrees" | tail -n +2 | while IFS=$'\t' read -r p b; do
    [[ -z "$b" ]] && matches_ticket "$(basename "$p")" &&
      echo "  SKIP     $p — detached worktree; no branch to check against a merged PR"
  done | grep . && { skipped=$((skipped + 1)); found=$((found + 1)); }

  [[ -n "$branches" ]] || continue
  slug=$(gh_slug "$clone")
  echo "$clone ($slug)"
  touched=false

  while IFS= read -r branch; do
    found=$((found + 1))
    wt=$(printf '%s\n' "$worktrees" | awk -F'\t' -v b="$branch" '$2 == b { print $1; exit }')
    wt_note=${wt:+ [worktree $wt left in place]}

    if [[ -n "$wt" && "$wt" == "$main_path" ]]; then
      echo "  SKIP     $branch — checked out in the main checkout; switch it to the default branch first"
      skipped=$((skipped + 1)); continue
    fi
    if [[ -z "$slug" ]]; then
      echo "  SKIP     $branch — origin isn't a GitHub remote, can't check for a merged PR${wt_note}"
      skipped=$((skipped + 1)); continue
    fi

    tip=$(git -C "$clone" rev-parse "refs/heads/$branch")
    prs=$(gh pr list -R "$slug" --head "$branch" --state all --limit 20 \
      --json number,state,headRefOid,url 2>/dev/null) || {
      echo "  SKIP     $branch — gh pr list failed (auth or network?)${wt_note}"
      skipped=$((skipped + 1)); continue
    }
    merged=$(printf '%s' "$prs" | jq -r --arg tip "$tip" \
      '[.[] | select(.state == "MERGED" and .headRefOid == $tip)][0] | select(. != null) | "#\(.number) \(.url)"')
    if [[ -z "$merged" ]]; then
      states=$(printf '%s' "$prs" | jq -r '[.[] | "#\(.number) \(.state) head=\(.headRefOid[0:8])"] | join(", ")')
      echo "  SKIP     $branch (tip ${tip:0:8}) — no merged PR with this exact head${states:+; PRs: $states}${wt_note}"
      skipped=$((skipped + 1)); continue
    fi

    if [[ -n "$wt" && -d "$wt" ]]; then
      dirty=$(git -C "$wt" status --porcelain 2>/dev/null)
      if [[ -n "$dirty" ]]; then
        echo "  SKIP     $branch — worktree $wt has uncommitted or untracked changes"
        skipped=$((skipped + 1)); continue
      fi
    fi

    if ! $apply; then
      [[ -n "$wt" ]] && echo "  WOULD    remove worktree $wt"
      echo "  WOULD    delete branch $branch (tip ${tip:0:8} = merged head of PR $merged)"
      continue
    fi

    if [[ -n "$wt" ]]; then
      if [[ -d "$wt" ]]; then
        if ! out=$(git -C "$clone" worktree remove "$wt" 2>&1); then
          echo "  FAIL     $branch — git worktree remove $wt failed; branch kept: $out"
          skipped=$((skipped + 1)); continue
        fi
      else
        git -C "$clone" worktree prune
      fi
      echo "  REMOVED  worktree $wt"
    fi
    if git -C "$clone" branch -D "$branch" >/dev/null 2>&1; then
      echo "  DELETED  branch $branch (was ${tip:0:8}, merged in PR $merged)"
      touched=true
    else
      echo "  FAIL     $branch — git branch -D failed"
      skipped=$((skipped + 1))
    fi
  done <<< "$branches"

  if $apply && $touched; then
    git -C "$clone" fetch --prune --quiet origin 2>/dev/null &&
      echo "  PRUNED   remote-tracking refs for deleted remote branches" ||
      echo "  NOTE     git fetch --prune failed; stale origin/* refs may remain"
  fi
done

if [[ $found -eq 0 ]]; then
  echo "Nothing found for $ticket under: ${roots[*]}"
  exit 2
fi
[[ $skipped -gt 0 ]] && exit 3
exit 0
