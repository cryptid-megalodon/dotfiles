# Global instructions

These apply to every project unless a project-level CLAUDE.md overrides them.

## Working style
- Do what was asked; don't expand scope. Ask before anything hard to reverse.
- Prefer small, reviewable changes. Don't commit or push unless asked.
- Match the surrounding code's style, naming, and comment density.
- When something fails (tests, builds, commands), report the actual output.

## Environment
- Shell: zsh. Editor: nvim. Terminal: ghostty. Prompt: starship.
- Dotfiles are managed with chezmoi from `~/.local/share/chezmoi`
  (https://github.com/cryptid-megalodon/dotfiles). Edit managed files with
  `chezmoi edit <path>`, not by editing `~/...` directly.
- Machines are macOS or Debian/Ubuntu. Don't assume GNU coreutils flags on mac.
