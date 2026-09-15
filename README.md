# dotfiles

Personal machine config for macOS and Linux (Debian/Ubuntu), managed with
[chezmoi](https://www.chezmoi.io/).

## New machine

```sh
sh -c "$(curl -fsLS get.chezmoi.io)" -- init --apply cryptid-megalodon
```

That installs chezmoi, clones this repo to `~/.local/share/chezmoi`, prompts for
machine type / email / Bitwarden, then applies everything. The run scripts will
ask for `sudo` when installing packages. Afterwards, open a new terminal (the
login shell is switched to zsh).

## Day-to-day

```sh
chezmoi edit ~/.zshrc       # edit a managed file (opens the source in nvim)
chezmoi diff                # preview what apply would change
chezmoi apply               # apply it
chezmoi add ~/.config/foo   # start managing a new file
chezmoi cd                  # cd into the source repo to commit/push
chezmoi update              # pull + apply on another machine
```

To add or remove software, edit `.chezmoidata/packages.yaml` and run
`chezmoi apply`; the package and VS Code extension scripts rerun automatically
when that file changes.

Machine-specific shell bits that shouldn't be in the repo go in `~/.zshrc.local`.

## Layout

| Path | Purpose |
| --- | --- |
| `.chezmoi.toml.tmpl` | First-run prompts (machine type, email, Bitwarden) |
| `.chezmoiignore` | Skips mac-only paths on Linux and vice versa |
| `.chezmoidata/packages.yaml` | Everything that gets installed (brew, apt, snap, VS Code extensions) |
| `.chezmoiscripts/` | Bootstrap, package install, extensions, Firefox policies, default shell, GNOME terminal shortcut |
| `.chezmoitemplates/` | Shared template fragments (VS Code settings rendered to both OS paths) |
| `dot_zshrc.tmpl`, `dot_tmux.conf` | Shell and tmux |
| `dot_config/` | ghostty, starship, nvim, opencode, VS Code (Linux path) |
| `Library/Application Support/Code/User/` | VS Code (mac path) |
| `dot_claude/` | Global Claude Code instructions and settings |
| `AGENTS.md` | How coding agents should work in this repo |

## Conventions

- `dot_` prefix ⇒ leading `.` in `$HOME`; `.tmpl` suffix ⇒ Go template with
  `.chezmoi.os` etc. available. See `chezmoi data` for all template variables.
- Scripts: `run_once_*` run once per machine, `run_onchange_*` rerun when their
  rendered content changes (they embed a hash of what they depend on).
  `before`/`after` is relative to writing the dotfiles.
- Neovim plugins are installed by lazy.nvim on first launch, not by chezmoi.
