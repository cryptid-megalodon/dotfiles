# pr-review (home) changelog

Every change to the skill, its scripts, or its references bumps the version on the
`Skill version` line of `SKILL.md` (the only place it is written) and adds an entry here in the
same commit. Major: a pipeline stage, model, or effort changes, since that can move what reviews
find. Minor: output or workflow changes that leave finding and verifying alone. Patch: wording
only.

The scripts in `scripts/` render from `.chezmoitemplates/pr-review/` in dotfiles and are shared
with the work copy (`wolf-os-poc/dot_claude/skills/pr-review`). A change there bumps both copies'
versions, with an entry in both changelogs.

## 2.1.0 — 2026-11-24

- Each run record gets a `usage` block: wall time from `started_at`, and tokens per stage for the
  main agent, each Claude subagent and each OpenAI call. `scripts/record_usage.py` writes it from
  the session's transcript and from usage files the OpenAI scripts now write with `--usage-out`.
- The OpenAI scripts run `codex exec --json` to read token counts, and take failure messages from
  its events.
- Agent descriptions start with their stage name, which is how subagents are attributed.
- `started_at` is taken when the configuration is printed.
- Runs before this version have no `usage`. `record_usage.py --session <id> --since <time>
  --until <time>` rebuilds the Claude side from the session's transcript while it still exists
  (Claude Code prunes transcripts after `cleanupPeriodDays`, 30 by default, and `done-r` deletes
  its own session's). The OpenAI side can't be rebuilt: those `codex exec` runs were ephemeral
  and their output was discarded.
- The same change is in the work copy as 3.1.0; the scripts are shared.

## 2.0.0 — 2026-11-22

- OpenAI verifier: `gpt-6.2-sol`, medium (was `gpt-6.1-sol`).

## 1.0.0 — 2026-11-22

- First home version, derived from the work skill at 2.0.0, with the same pipeline, models,
  efforts, nit handling, and run records.
- Reviews any change: a PR (number or URL, any owner), a branch against the default branch, or
  a range of commits. Branches and commits are always reviewed as the user's own change.
- WHOOP specifics replaced:
  - The Jira ticket becomes PR body, linked issues and commit messages, and the user is asked
    when those don't say what the change is for.
  - The Java and Python rule sets become the repo's own convention files and linter configs.
  - The severity file becomes a rubric in the skill.
- Artifacts, worktrees, clones and suppressions live in `~/.local/share/pr-review`, outside the
  skill directory, so a chezmoi update never overwrites learned suppressions.
- The run record adds `skill_copy: "home"` and a `target` object.
