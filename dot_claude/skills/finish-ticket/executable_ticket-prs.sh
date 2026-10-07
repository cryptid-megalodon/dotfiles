#!/usr/bin/env bash
#
# ticket-prs.sh — list every GitHub PR that belongs to a ticket, across the org.
#
# Usage: ticket-prs.sh <TICKET> [--owner ORG]
#
# Searches GitHub for the ticket key, then keeps only PRs whose title carries the key as a
# whole token ([BOT-123] ..., BOT-123: ...) or whose body links the ticket
# (atlassian.net/browse/BOT-123), so BOT-12 never matches BOT-123 and a PR that merely
# mentions the number is dropped. Prints a JSON array sorted by repo and number:
#
#   [{"repo":"WhoopInc/x","number":12,"title":"...","state":"merged|open|closed",
#     "url":"...","updated_at":"..."}]
#
# Exit codes:
#   0  printed the list (possibly empty)
#   1  invalid arguments, missing tool (gh, jq), or the search failed

set -uo pipefail

usage() { echo "Usage: ticket-prs.sh <TICKET> [--owner ORG]" >&2; exit 1; }

ticket="" owner="WhoopInc"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --owner) [[ $# -ge 2 ]] || usage; owner="$2"; shift 2 ;;
    -h|--help) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) usage ;;
    *) [[ -z "$ticket" ]] || usage; ticket="$1"; shift ;;
  esac
done
[[ "$ticket" =~ ^[A-Za-z][A-Za-z0-9]*-[0-9]+$ ]] || { echo "Ticket must look like BOT-123, got '$ticket'" >&2; exit 1; }
for tool in gh jq; do
  command -v "$tool" >/dev/null || { echo "$tool is required" >&2; exit 1; }
done

results=$(gh search prs "$ticket" --owner "$owner" --limit 100 \
  --json repository,number,title,state,url,updatedAt,body 2>&1) || {
  echo "gh search prs failed: $results" >&2; exit 1
}

printf '%s' "$results" | jq --arg key "$ticket" '
  ("(^|[^A-Za-z0-9])" + $key + "([^0-9]|$)") as $token
  | [ .[]
      | select((.title | test($token; "i")) or ((.body // "") | test("/browse/" + $key + "([^0-9]|$)"; "i")))
      | {repo: .repository.nameWithOwner, number, title, state, url, updated_at: .updatedAt} ]
  | sort_by(.repo, .number)'
