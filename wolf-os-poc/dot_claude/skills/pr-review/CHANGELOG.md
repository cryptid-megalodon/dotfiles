# pr-review changelog

Every change to the skill, its scripts, or its references bumps the version on the
`Skill version` line of `SKILL.md` (the only place it is written) and adds an entry here in the
same commit. Major: a pipeline stage, model, or effort changes, since
that can move what reviews find. Minor: output or workflow changes that leave finding and
verifying alone. Patch: wording only.

Reviews made before 2.0.0 have no version recorded and no `run-<k>.json`. Use the `review.md`
date to tell them apart; any with an "Also noticed" section are 1.1.0.

## 2.0.0 — 2026-11-22

- Pinned the model and effort for every stage, printed before the review starts:
  - Claude correctness finders: Fable 5.2, high.
  - OpenAI correctness finders: `gpt-6.2-astra`, high.
  - Conventions finder: Opus 5.5, medium.
  - Claude verifiers: Opus 5.5, medium.
  - OpenAI verifier: `gpt-6.1-sol`, medium.

  Before this, the Claude agents inherited the session's model and effort (Opus 5.5 at medium on
  the machine checked), and the OpenAI verifier ran `$PR_REVIEW_OPENAI_MODEL`, which was
  `gpt-6.1-sol`, at high.
- Added OpenAI correctness finders: one per chunk, with the same brief as the Claude finder, run
  through `codex exec` (`scripts/codex_find.py`).
- Moved the OpenAI verifier from direct API calls with three limited tools
  (`scripts/cross_verify.py`, removed) to `codex exec` in a read-only sandbox
  (`scripts/codex_verify.py`), with full read access and the ability to run commands that write
  nothing.
- Every candidate is tagged `found_by` (`claude`, `openai`, `both`), with a column for it in the
  ledger; verifiers never see the tag.
- The adjudication table now covers an OpenAI `ERROR` or unavailable verdict.
- Each review records its version in `review.md` and a `run-<k>.json` with config, verdicts and
  outcomes for every candidate.

## 1.1.0 — 2026-11-22 (dotfiles `206597f`)

- Verified nits past the three-`[Suggestion]` cap go in a collapsed "Also noticed" section of
  `review.md`, never posted.

## 1.0.0 — dotfiles `370dda2`

- First version managed in dotfiles.
