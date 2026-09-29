---
name: finish-ticket
description: Clean up after a ticket's PRs merge — remove its git worktrees, delete its local branches, and prune stale remote-tracking refs, across every repo under ~/repos. Use when the user says "finish ticket", "clean up BOT-123", "the PR merged, clean up", "remove the worktree", "delete the local branch", or otherwise wants post-merge cleanup for a ticket.
allowed-tools: Bash
---

# Finish Ticket

Post-merge cleanup for the one-worktree-per-ticket layout in `~/repos/CLAUDE.md`
(`~/repos/<repo>-worktrees/<TICKET>`, branch `<TICKET>-<desc>`). The script does the work;
it verifies before it deletes anything, and never forces.

```bash
~/.claude/skills/finish-ticket/finish-ticket.sh <TICKET>            # dry run: show the plan
~/.claude/skills/finish-ticket/finish-ticket.sh <TICKET> --apply    # do it
```

`--root DIR` (repeatable) searches somewhere other than `~/repos`. The default root already
covers clones nested deeper, such as `~/repos/feedback_loop/jc-os-poc/repos/<repo>`.

## Steps

1. **Resolve the ticket key** from the user's message, or from the current branch or worktree
   name. If none is clear, ask; don't guess.
2. **Dry run** and read every line. `WOULD` lines are the plan; `SKIP` lines say why a branch
   or worktree is being left alone.
3. **Apply** when the dry run shows the work the user asked for. Asking to finish or clean up
   the ticket is the go-ahead; the script's checks are what make it safe. Show the user the
   plan first instead if it touches more than they seem to expect (another repo, several
   branches).
4. **Report** what was removed and deleted, and every `SKIP`/`FAIL` with its reason and the
   fix the user can choose (below). Don't act on a skip yourself.

## What the script checks

A branch is cleaned up only if it has a **merged PR whose head is exactly the local tip**, its
worktree (if any) is **clean including untracked files**, and it isn't checked out in the
**main checkout**. The tip check is why `git branch -D` is safe here: after a squash merge the
branch's commits aren't ancestors of the default branch, so `git branch -d` always refuses, but
a tip equal to the PR's merged head means everything on it landed.

For each verified branch it runs `git worktree remove` (never `--force`), then
`git branch -D`, then `git fetch --prune origin` once per clone it touched.

It also checks each clone's `<repo>-worktrees/` for a directory named after the ticket that
git no longer tracks as a worktree, typically empty `target/` build directories left after a
worktree was removed some other way. If it holds only empty directories, it's removed with
`find -type d -empty -delete`, which cannot delete a file. If it holds any file, it's a `SKIP`.

## Skips and what to tell the user

| SKIP reason | Meaning | User's options |
| --- | --- | --- |
| no merged PR with this exact head | PR still open or closed unmerged, never pushed, or local commits after the PR's last push | Merge or push first; or delete it by hand if the work is abandoned |
| uncommitted or untracked changes | The worktree has work that would be lost | Commit/push it, or discard it, then rerun |
| checked out in the main checkout | Can't delete the branch the main checkout is on | `git switch <default>` in the main checkout, then rerun |
| detached worktree | Worktree named after the ticket with no branch | Inspect it; remove by hand if it's stale |
| not a git worktree but holds N file(s) | Leftover directory with real content, possibly unrecovered work | Inspect it; remove by hand only if nothing in it is needed |

Never pass `--force` to `git worktree remove`, delete a skipped branch or directory, or remove the remote
branch on GitHub (GitHub deletes merged PR branches) without the user asking for that specific
thing.

## Exit codes

- `0` dry run done, or everything planned was applied
- `1` bad arguments or missing `git`/`gh`/`jq`
- `2` nothing found for the ticket (already clean, or the key is wrong)
- `3` something was skipped or failed; report the `SKIP`/`FAIL` lines
