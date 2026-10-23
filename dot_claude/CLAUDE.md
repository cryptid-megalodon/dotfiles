# Global instructions

These apply to every project unless a project-level CLAUDE.md overrides them.

## Working style
- Do what was asked; don't expand scope. Ask before anything hard to reverse.
- Prefer small, reviewable changes. Don't commit or push unless asked.
- Never add Claude as an author or co-author on commits or PRs, and don't
  mention Claude, Claude Code, or AI assistance in commit messages or PR
  descriptions. No `Co-Authored-By`, `Generated with`, or session links.
- Match the surrounding code's style, naming, and comment density.
- When something fails (tests, builds, commands), report the actual output.
- Start every comment or reply you post under my name (PR review replies,
  issue comments, Jira comments) with `[claude:]`, so readers can tell it
  came from Claude and not from me.

## Environment
- Shell: zsh. Editor: nvim. Terminal: ghostty. Prompt: starship.
- Dotfiles are managed with chezmoi from `~/.local/share/chezmoi`
  (https://github.com/cryptid-megalodon/dotfiles). Edit managed files with
  `chezmoi edit <path>`, not by editing `~/...` directly. Before committing or
  pushing there, read `~/.local/share/chezmoi/CLAUDE.md`: that repo commits
  and pushes as my personal GitHub account (`cryptid-megalodon`), not the
  work one.
- Machines are macOS or Debian/Ubuntu. Don't assume GNU coreutils flags on mac.
- Write every time you show me in the machine's local timezone (check with
  `date +%Z`), never UTC, and label the zone (e.g. `2:30 PM EDT`). Convert
  UTC timestamps from logs, APIs, CI, and git before quoting them. Leave
  UTC alone only inside code, configs, or data where the format is required.

## Datadog
- Use the `datadog:datadog` skill (WHOOP marketplace) for everything in
  Datadog; it carries the CLI invocation and read-only wrapper. Don't run bare
  `pup`, and don't use a Datadog MCP server or raw HTTP (`curl`, scripts) to
  Datadog APIs.
- If a request needs a Datadog write (or anything else the skill can't do),
  don't work around it. Tell me to restart with `claude-pup` (a shell function
  that sets `PUP_WRITE_SESSION=1` and disables the datadog plugin), and offer to
  resume the task there.
- Only when `PUP_WRITE_SESSION=1` is set may you run bare `pup`. Even then:
  run reads before writes, show me the exact write command before running it,
  and never print or extract the auth token or hit Datadog APIs with raw HTTP.

## Jira
- Every Jira ticket I create gets the label `ai-quality-team`. `jira create`
  has no label flag, so right after creating, run
  `jira update <KEY> --fields '{"labels":["ai-quality-team"]}'`. This applies
  alongside the create-ticket skill's no-work-type-label rule.
- Every Jira ticket I create also goes in the AI Quality board's active
  sprint. Right after creating it, run `jira sprints --project BOT`, take the
  entry with `"boardId": 9143` and `"state": "active"`, and run
  `jira sprint-add <id> <KEY> --project BOT`. If there isn't exactly one such
  sprint, ask me which to use instead of picking one.
