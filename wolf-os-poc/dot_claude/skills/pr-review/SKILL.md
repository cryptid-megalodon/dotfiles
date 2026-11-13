---
name: pr-review
description: Review a pull request and draft review comments. On a teammate's PR, drafts comments for the user to post; on the user's own PR, shows what the comments would be, takes the user's apply/skip decisions and answers, and applies them to the branch. Runs parallel finders, then a blind Claude verifier and an OpenAI cross-family verifier, and drafts only what survives. Use when the user asks to review a teammate's PR, self-review their own PR before sending it for human review, draft PR comments, or re-review a PR. For the user's own uncommitted diff, use `/code-review` instead.
---

# PR Review

Runs in one of two modes, set in step 1 by who wrote the PR:

- **Teammate review** (someone else's PR): drafts comments for the user to edit and post.
  Nothing is published without the user's go-ahead; the most this skill puts on GitHub is a
  **pending** review, which only the user can see until they submit it.
- **Self-review** (the user's own PR, usually before asking for human review): there is no one
  to post to. Show the user the comments a reviewer would leave, have them decide which to apply
  and answer the questions, then make the changes on their branch. Never offer to post, and
  never create a pending review.

The pipeline exists because a single review pass is noisy: developers reject over half of AI review
comments, mostly as false positives, redundant, or out of step with intent and conventions. So:
lean context per finder, a verifier that never sees the finder's reasoning, a second model family
to break correlated blind spots, and a hard rule that every finding names a concrete failure.

Paths below: `SKILL_DIR` is this skill's directory; `JAVA_RULES` is
`~/.claude/plugins/marketplaces/whoop-marketplace/plugins/java/skills/code-review` and
`PY_RULES` is `~/.claude/plugins/marketplaces/whoop-marketplace/plugins/ml/skills/review-pr`
(both auto-updating marketplace clones; no plugin install needed). Review artifacts go in
`~/wolf-os-poc/projects/pr-reviews/<repo>-<n>/`.

## 1. Pin the PR and gather intent

Run these together:

```bash
gh api repos/WhoopInc/<repo>/pulls/<n> --jq '{state,draft,author:.user.login,head:.head.sha,headRef:.head.ref,base:.base.ref,title,body}'
gh pr diff <n> -R WhoopInc/<repo>
gh api repos/WhoopInc/<repo>/pulls/<n>/comments --paginate   # inline threads (Greptile + humans)
gh api repos/WhoopInc/<repo>/pulls/<n>/reviews --paginate
gh api user --jq .login
```

Use `head.sha` from the first call everywhere — `gh pr view --json headRefOid` can be stale.
Stop if the PR is closed, merged, or bot-authored (say why), unless the user named it explicitly.
If `author` equals the user's login, this is a **self-review**: steps 1–6 run unchanged, and
step 7 ends with applying fixes instead of posting. If the user already has a review on this PR
(for a self-review: `projects/pr-reviews/<repo>-<n>/review.md` already exists), this is a
**re-review** — see step 8.

Pull the Jira ticket named in the title or branch (`whoop-atlassian:jira` skill) for its summary
and acceptance criteria. Write a 3–5 sentence **intent summary**: what the change is for, what it
deliberately changes, and what it deliberately leaves alone. Mismatched intent is a top reason
authors reject review comments; every finder and verifier gets this summary.

Digest the existing comments into **already raised**: one line per point Greptile or a human has
made, with its resolution state. Nothing on that list gets drafted again.

## 2. Check out the head

Reviewers need surrounding code at the PR head, not the diff alone. Clone into
`~/wolf-os-poc/repos/<repo>` if missing, then make a detached review worktree (the main checkout
stays on the default branch):

```bash
git -C ~/wolf-os-poc/repos/<repo> fetch origin pull/<n>/head
git -C ~/wolf-os-poc/repos/<repo> worktree add --detach ~/wolf-os-poc/repos/<repo>-worktrees/review-<n> <head-sha>
```

Save the diff to `projects/pr-reviews/<repo>-<n>/pr.diff`.

## 3. Plan the finders

**Chunk the diff.** Review quality falls off sharply past ~150 changed lines per pass, so split
the reviewable diff into chunks of roughly 150–250 changed lines, keeping each source file with
its tests and keeping cohesive changes together. Skip lockfiles, generated code, and vendored
files (but not migrations). Above five chunks, keep the five highest-risk and list every skipped
file in the review summary — never truncate silently.

**Route conventions.** By language:

- **Java**: read `JAVA_RULES/rules/INDEX.md`, match changed paths to its globs, and collect only
  the matching rule files. Always add `JAVA_RULES/reference/severity.md` and
  `JAVA_RULES/reference/false-positives.md`.
- **Python**: `PY_RULES/standards/SKILL.md`, `PY_RULES/testing/SKILL.md`,
  `PY_RULES/maintenance/SKILL.md`. These come from the ML team; apply each rule only where the repo
  already follows that convention (e.g. `WhoopModel`, Poetry, `launch.json`) — the repo wins.
- **Both**: the repo's root `CLAUDE.md` and any in touched directories, plus
  `SKILL_DIR/reference/suppressions.md`.

## 4. Find (parallel subagents)

Dispatch in one message, using `SKILL_DIR/reference/finder-brief.md` as the template:

- **One correctness finder per chunk** — recall-oriented bug hunting in that chunk. For Python,
  include `PY_RULES/logic/SKILL.md` as its checklist.
- **One conventions finder** over the whole diff with the routed rule files from step 3.
- **Contract check** (Java): if the diff changes a public signature, enum value, JSON field, or
  anything in `api-commons`/`java-api-clients`/a shared module, the conventions finder runs the
  org-wide consumer search from `JAVA_RULES/SKILL.md` step 4 and names consumers.

Fill each brief with absolute paths, the intent summary, the already-raised list, and the chunk's
diff. Do not add your own hunches about what is wrong — finders should start unbiased.

## 5. Merge candidates

Collect every candidate into `candidates.json`: `id`, `path`, `line`, `claim`,
`failure_scenario`, `rule` (or null), `finder_severity`. Drop and merge here:

- duplicates across finders (keep the most concrete failure scenario);
- anything on the already-raised list, on the Greptile deferral table in `false-positives.md`, or
  in `suppressions.md`;
- anything on lines the PR did not touch, unless the PR causes the breakage elsewhere;
- anything CI catches (compile, type, lint, Spotless);
- candidates with no concrete failure scenario and no rule behind them.

Strip each finder's reasoning: verifiers receive only location, claim, and failure scenario.

## 6. Verify (two families, in parallel)

Start both in one message:

- **Claude verifier**: subagents briefed with `SKILL_DIR/reference/verifier-brief.md`, one per
  ≤6 candidates.
- **OpenAI verifier**: same brief, same candidates, via
  ```bash
  python3 SKILL_DIR/scripts/cross_verify.py --root <worktree> --candidates candidates.json \
    --intent intent.md --diff pr.diff --out openai-verdicts.json
  ```
  It needs `OPENAI_API_KEY` and `PR_REVIEW_OPENAI_MODEL` in the environment (`--list-models` shows
  what the key can use). Code excerpts go to OpenAI with `store: false`. If the key or model is
  missing, say so and continue with the Claude verdicts alone — note the missing family in the
  summary.

**Empirical check.** For a `Blocking` or `Important` candidate whose failure a single unit test can
show, the Claude verifier may write a scratch test in the review worktree, run just that test
(`devkit:java-service` skill for Java; `pytest <file>::<test>` for Python), and delete it. Skip
anything that needs Docker, a full build over a few minutes, or network. One real run outranks
any amount of agreement.

**Adjudicate yourself — never delegate this.** Read the cited code for every disagreement.

| Claude | OpenAI | Outcome |
|---|---|---|
| CONFIRMED | CONFIRMED or unavailable | keep |
| CONFIRMED | REFUTED | read the refutation's evidence; keep only if it's wrong |
| REFUTED | CONFIRMED | same, in the other direction |
| REFUTED | REFUTED | drop |
| either UNCERTAIN | — | if the unknown is the author's intent, draft a `[Question]`; if it's code behavior, check it yourself or drop |

Never draft a finding as "possible" or "might" — a hedged comment costs the author a read for no
signal. Uncertainty about behavior gets resolved or dropped; only uncertainty about intent becomes
a question.

## 7. Draft

Severity from `JAVA_RULES/reference/severity.md` (it applies to Python too), mapped to WHOOP's
labels from `software-how-to/pull-requests/pr-review-guidelines.md`: Blocking → `[Blocking]`,
Should fix → `[Important]`, Nit → `[Suggestion]`, plus `[Question]`. At most three
`[Suggestion]`s, and only when nothing above them survived.

Each comment:

- starts `[claude:] [Label]` — the user's global rule for anything posted under their name (a
  self-review posts nothing, so just `[Label]`);
- speaks to the author directly, "we/our" where natural, no preamble, no restating the PR;
- says what breaks, the minimal evidence (a `file:line` chain), and the fix, in one short
  paragraph — a comment needing three paragraphs is two comments or a weak one;
- uses a GitHub ```` ```suggestion ```` block when the fix is a few lines, with `start_line`/`line`
  covering exactly the lines it replaces.

Write `projects/pr-reviews/<repo>-<n>/review.md`: a 1–2 sentence `[claude:]` review body (plus any
finding that can't anchor to a diff line and any skipped files), then each comment under
`path:line`, then a ledger table — `#`, label, one-line claim, status (`drafted`). Show the user
the drafts in the terminal and give the file path.

**Teammate review.** Ask whether to create a **pending review** on the PR. On yes:

1. Check each comment's line is on the RIGHT side of a hunk in `pr.diff`; move it to the nearest
   line in the same hunk, or into the review body if it has none.
2. Build `pending-review.json` with `commit_id` (head sha), `body`, and `comments[]` (`path`,
   `line`, `side: "RIGHT"`, optional `start_line`/`start_side`, `body`) — **no `event` field**,
   which is what keeps it pending.
3. `gh api repos/WhoopInc/<repo>/pulls/<n>/reviews --method POST --input pending-review.json`.
   GitHub allows one pending review per user per PR; if one exists, tell the user rather than
   deleting it.

Tell the user it's waiting in the PR's "Files changed" tab to edit and submit.

**Self-review.** In the same message as the drafts, ask the user to decide each comment — apply,
skip, or apply a different fix they describe (e.g. "apply 1 and 3, skip 2") — and to answer each
`[Question]`. Don't offer to post, and don't ask whether to post or apply: applying is the only
path. Then carry out their reply:

1. **Use the branch's worktree.** Find `headRef` in `git -C ~/wolf-os-poc/repos/<repo> worktree
   list`; if no worktree has it, create one per the workspace CLAUDE.md, checking out the
   existing branch. Never edit the detached review worktree. If the branch worktree isn't at the
   reviewed head sha or has uncommitted changes, say so and ask before editing — the findings
   were checked against the pushed head.
2. **Apply.** Make each accepted fix, using the user's version where they gave one. An answer
   confirming the code is intended needs no change; an answer asking for a change gets it; an
   answer that shows a bug without saying how to fix it gets a proposed fix, not a guess.
3. **Hand back.** Run the tests covering the changed code and the repo's formatter, leave the
   changes uncommitted, open them with `code <worktree> <changed files>`, and report what
   changed per comment. Ask before committing or pushing; commits need the `[BOT-XXX]` prefix.

In both modes, remove the review worktree with `git worktree remove` (no `--force`; if it
refuses, report what's left).

## 8. Re-review and feedback

On a re-review, recreate the worktree at the new head and lead the drafts with the status table
from `JAVA_RULES/SKILL.md` ("Re-reviews"), verifying fixes against the code, not commit messages.
Then run steps 3–7 on what changed since the last reviewed sha.

Update the ledger in `review.md` from what actually happened: `posted`, `dropped by user`,
`author fixed`, `author pushed back` (self-review: `applied`, `skipped by user`, `answered`, plus
any change the answer led to). When the user drops or skips a draft or an author pushes back for a
valid reason, add a one-line entry to `SKILL_DIR/reference/suppressions.md` saying what not to
flag and why. If the pushback shows a rule in `JAVA_RULES` or `PY_RULES` is wrong, tell the user
it belongs upstream in `WhoopInc/agentic-tooling-rules` — don't edit the marketplace clone.
