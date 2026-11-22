---
name: pr-review
description: Review a pull request and draft review comments. On a teammate's PR, drafts comments for the user to post; on the user's own PR, shows what the comments would be, takes the user's apply/skip decisions and answers, and applies them to the branch. Runs parallel Claude and OpenAI finders, then a blind Claude verifier and an OpenAI cross-family verifier, and drafts only what survives. Use when the user asks to review a teammate's PR, self-review their own PR before sending it for human review, draft PR comments, or re-review a PR. For the user's own uncommitted diff, use `/code-review` instead.
---

# PR Review

**Skill version: 3.0.0.** This line is the only place the version is written; `<version>` below
always means this number. Every review records it (step 7) so reviews can be compared across
versions. Any change to this skill, its scripts, or its references bumps it and gets an entry in
`SKILL_DIR/CHANGELOG.md`, in the same commit.

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
at both finding and verifying to break correlated blind spots (much of the code under review is
Claude-written, so Claude alone tends to miss what Claude got wrong), and a hard rule that every
finding names a concrete failure.

Paths below: `SKILL_DIR` is this skill's directory; `JAVA_RULES` is
`~/.claude/plugins/marketplaces/whoop-marketplace/plugins/java/skills/code-review` and
`PY_RULES` is `~/.claude/plugins/marketplaces/whoop-marketplace/plugins/ml/skills/review-pr`
(both auto-updating marketplace clones; no plugin install needed). Review artifacts go in
`~/wolf-os-poc/projects/pr-reviews/<repo>-<n>/`.

## Model configuration

Every stage runs at a fixed model and reasoning level. Effort is spent where a mistake can't be
caught later: everything after the finders only filters, so a bug a correctness finder misses is
gone for good, while a verifier's mistake can still be caught by the other model family or by the
adjudication.

| Stage | Runs as | Model | Effort |
|---|---|---|---|
| Main agent: intent, merge, adjudication, drafting | this session | session model | session effort |
| Correctness finders, Claude (one per chunk) | `Agent` | `fable` (Fable 5.2) | `high` |
| Correctness finders, OpenAI (one per chunk) | `scripts/codex_find.py` | `gpt-6.2-astra` | `high` |
| Conventions finder | `Agent` | `opus` (Opus 5.5) | `medium` |
| Claude verifiers | `Agent` | `opus` (Opus 5.5) | `medium` |
| OpenAI verifier | `scripts/codex_verify.py` | `gpt-6.2-sol` | `medium` |

Pass `model` and `effort` explicitly on every `Agent` call, and `--model`/`--effort` on both
scripts, so neither the session's settings nor the user's Codex config leak in. Both OpenAI
stages run through `codex exec` in a read-only sandbox at the review worktree. The skill can't
set the main agent's level; it only reports it.

**Print the configuration first**, before step 1, so the user knows what the review runs on.
Check `codex --version` and `codex login status`. Take the session effort from `modelSettings` in `~/.claude/settings.json` for the
session's model, which misses a `/effort` change made this session, so say so. Print:

```
pr-review <version> configuration
  Main agent           <session model> · effort <level> (from settings.json)
  Correctness finders  Claude fable · high   |   OpenAI gpt-6.2-astra · high (codex <codex version>)
  Conventions finder   Claude opus · medium
  Verifiers            Claude opus · medium   |   OpenAI gpt-6.2-sol · medium
  OpenAI access        codex logged in via <method>|not logged in
```

Add a warning line for each of these:

- the main agent's effort is below `high`: adjudication is the final call with nothing checking it;
- `codex` is missing or not logged in: the OpenAI finders and verifier will both be skipped;
- `codex` is logged in with ChatGPT rather than an API key: code goes out under the ChatGPT
  plan's data terms, not the API's.

Then continue without waiting; the user interrupts if they want something changed.

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

Dispatch in one message, using `SKILL_DIR/reference/finder-brief.md` as the template, at the
models and efforts in the configuration table:

- **One correctness finder per chunk** — recall-oriented bug hunting in that chunk. For Python,
  include `PY_RULES/logic/SKILL.md` as its checklist.
- **One OpenAI correctness finder per chunk** — the same chunks and the same filled brief,
  byte for byte, so the only difference is the model family. Write each chunk's filled
  correctness brief to `briefs/correctness-<k>.md` in the review directory, then start, in the
  same message as the Claude finders:
  ```bash
  python3 SKILL_DIR/scripts/codex_find.py --root <worktree> \
    --briefs briefs/correctness-*.md --out-dir openai-findings \
    --model gpt-6.2-astra --effort high
  ```
  It runs `codex exec` per chunk in a read-only sandbox at the worktree, with the user's Codex
  config ignored, and writes `openai-findings/correctness-<k>.json`. If `codex` is unavailable or
  a chunk fails, continue with the Claude finders for it and note the gap in the summary.
- **One conventions finder** over the whole diff with the routed rule files from step 3.
- **Contract check** (Java): if the diff changes a public signature, enum value, JSON field, or
  anything in `api-commons`/`java-api-clients`/a shared module, the conventions finder runs the
  org-wide consumer search from `JAVA_RULES/SKILL.md` step 4 and names consumers.

Fill each brief with absolute paths, the intent summary, the already-raised list, and the chunk's
diff. Do not add your own hunches about what is wrong — finders should start unbiased.

## 5. Merge candidates

Collect every candidate into `candidates.json`: `id`, `path`, `line`, `claim`,
`failure_scenario`, `rule` (or null), `finder_severity`, `found_by` (`claude`, `openai`, or
`both`). Drop and merge here:

- duplicates across finders (keep the most concrete failure scenario; when both families found
  it, set `found_by` to `both`);
- anything on the already-raised list, on the Greptile deferral table in `false-positives.md`, or
  in `suppressions.md`;
- anything on lines the PR did not touch, unless the PR causes the breakage elsewhere;
- anything CI catches (compile, type, lint, Spotless);
- candidates with no concrete failure scenario and no rule behind them.

Strip each finder's reasoning: verifiers receive only location, claim, and failure scenario —
never `found_by`, so neither family knows whose finding it is checking.

## 6. Verify (two families, in parallel)

Start both in one message:

- **Claude verifier**: subagents briefed with `SKILL_DIR/reference/verifier-brief.md`, one per
  ≤6 candidates.
- **OpenAI verifier**: same brief, same candidates, via
  ```bash
  python3 SKILL_DIR/scripts/codex_verify.py --root <worktree> --candidates candidates.json \
    --intent intent.md --diff pr.diff --out openai-verdicts.json \
    --model gpt-6.2-sol --effort medium
  ```
  It runs one `codex exec` per candidate, so the OpenAI verifier can read anything, run git, and
  trace callers the way the Claude verifier can. It can run commands that write nothing (a
  one-line `python3 -c`, say), but not a test suite that writes build output, so the empirical
  check below stays with the Claude verifier. A candidate whose run fails comes back as `ERROR`. If `codex` is
  unavailable or can't use the model, say so and continue with the Claude verdicts alone — note the missing family in the
  summary.

**Empirical check.** For a `Blocking` or `Important` candidate whose failure a single unit test can
show, the Claude verifier may write a scratch test in the review worktree, run just that test
(`devkit:java-service` skill for Java; `pytest <file>::<test>` for Python), and delete it. Skip
anything that needs Docker, a full build over a few minutes, or network. One real run outranks
any amount of agreement.

**Adjudicate yourself — never delegate this.** Read the cited code for every disagreement.

| Claude | OpenAI | Outcome |
|---|---|---|
| CONFIRMED | CONFIRMED, or unavailable/`ERROR` | keep |
| REFUTED | unavailable/`ERROR` | drop; if it was `ERROR`, note the missing verdict in the summary |
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
Should fix → `[Important]`, Nit → `[Suggestion]`, plus `[Question]`. Draft at most three
`[Suggestion]`s, and only when nothing above them survived. Every other verified nit goes in the
**Also noticed** section of `review.md` instead — verified, so not noise, but not worth a comment.

Each comment:

- starts `[claude:] [Label]` — the user's global rule for anything posted under their name (a
  self-review posts nothing, so just `[Label]`);
- speaks to the author directly, "we/our" where natural, no preamble, no restating the PR;
- says what breaks, the minimal evidence (a `file:line` chain), and the fix, in one short
  paragraph — a comment needing three paragraphs is two comments or a weak one;
- uses a GitHub ```` ```suggestion ```` block when the fix is a few lines, with `start_line`/`line`
  covering exactly the lines it replaces.

Write `projects/pr-reviews/<repo>-<n>/review.md`. Its first line is
`<!-- pr-review <version> · pass <k> · <head sha> · <local date and time with zone> -->`, which stays
out of anything posted. Then a 1–2 sentence `[claude:]` review body (plus any
finding that can't anchor to a diff line and any skipped files), then each comment under
`path:line`, then a ledger table — `#`, label, one-line claim, found by, status (`drafted`). Show the user
the drafts in the terminal and give the file path.

If any verified nits weren't drafted, end `review.md` with an **Also noticed** section, and omit
it when there are none:

```markdown
<details>
<summary>Also noticed: 2 verified nits, not drafted</summary>

1. `SyncService.java:201` — `MAX_RETRIES` is 3 here but 5 in `RetryConfig.java:18`.
2. `MemberMapper.java:33` — `Optional.get()` unchecked; safe only because `MemberController.java:58` filters nulls.

</details>
```

One line per nit: `path:line` and what's off, with no fix and no suggestion block. Number the
nits separately from the comments. In the terminal, give only the summary line. This section never
goes on GitHub, in the pending review's body or its comments. If the user says "draft nit N",
promote that nit to a full `[Suggestion]` comment and add it to the ledger.

**Run record.** Alongside `review.md`, write `run-<k>.json`, where `k` is the pass: 1 for the
first review, 2 for the first re-review, and so on. This is what later analysis reads, so record
what actually ran, not what the configuration table says should have:

```json
{
  "skill_version": "<version>",
  "pass": 1,
  "started_at": "2026-11-22T15:04:00-05:00",
  "repo": "<repo>", "pr": 123, "head_sha": "<sha>", "since_sha": null,
  "mode": "teammate | self",
  "config": {
    "main": {"model": "<session model id>", "effort": "<level>"},
    "claude_correctness_finder": {"model": "fable", "effort": "high"},
    "openai_correctness_finder": {"model": "gpt-6.2-astra", "effort": "high"},
    "conventions_finder": {"model": "opus", "effort": "medium"},
    "claude_verifier": {"model": "opus", "effort": "medium"},
    "openai_verifier": {"model": "gpt-6.2-sol", "effort": "medium"},
    "codex_version": "<codex version>", "codex_login": "ChatGPT | API key | none"
  },
  "chunks": 3,
  "skipped_files": [],
  "gaps": ["OpenAI finder failed on chunk 2"],
  "findings": [
    {"id": "c4", "found_by": "openai", "finder_severity": "Should fix",
     "dropped_at": null, "drop_reason": null,
     "claude_verdict": "CONFIRMED", "openai_verdict": "REFUTED", "empirical_check": "none",
     "outcome": "drafted", "label": "[Important]", "comment": 2, "status": "drafted"}
  ]
}
```

- `findings` lists **every** candidate the finders returned, including ones merged or dropped,
  so the filter's effect can be measured. `dropped_at` is `merge` or `verify` (or null) and
  `drop_reason` says why (`duplicate of c2`, `already raised`, `CI catches it`, `REFUTED by both`).
  Verdicts are `CONFIRMED`, `REFUTED`, `UNCERTAIN`, `ERROR`, or null if never verified.
  `empirical_check` is `none`, `confirmed`, or `refuted`.
- `outcome` is `drafted`, `question`, `nit` (in Also noticed), or `dropped`; `comment` is its
  number in `review.md` (nits: `"nit 1"`).
- `config.main` is the session's model id and effort as printed at the start; any stage that was
  skipped gets `"model": null` and a line in `gaps`.
- `started_at` is the local time with its offset, from `date +%Y-%m-%dT%H:%M:%S%z`.

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
`[Question]`. They may also pick nits from **Also noticed** ("apply 1, 2 and nits 1, 3"); an
unpicked nit needs no decision. Don't offer to post, and don't ask whether to post or apply:
applying is the only path. Then carry out their reply:

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
any change the answer led to), and set the same `status` on that finding in the `run-<k>.json`
of the pass that produced it. Never rewrite a run file's `skill_version` or `config`: a finding
keeps the version that found it, even when a later version follows it up. When the user drops or skips a draft or an author pushes back for a
valid reason, add a one-line entry to `SKILL_DIR/reference/suppressions.md` saying what not to
flag and why. Leaving an **Also noticed** nit alone is not a dismissal, so add no suppression
for it. If the pushback shows a rule in `JAVA_RULES` or `PY_RULES` is wrong, tell the user
it belongs upstream in `WhoopInc/agentic-tooling-rules` — don't edit the marketplace clone.
