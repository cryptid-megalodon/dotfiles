# pr-review (home) changelog

Every change to the skill, its scripts, or its references bumps the version on the
`Skill version` line of `SKILL.md` (the only place it is written) and adds an entry here in the
same commit. Major: a pipeline stage, model, or effort changes, since that can move what reviews
find. Minor: output or workflow changes that leave finding and verifying alone. Patch: wording
only.

The scripts in `scripts/` render from `.chezmoitemplates/pr-review/` in dotfiles and are shared
with the work copy (`wolf-os-poc/dot_claude/skills/pr-review`). A change there bumps both copies'
versions, with an entry in both changelogs.

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
