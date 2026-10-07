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
| `.chezmoiscripts/` | Bootstrap, package install, extensions, Firefox policies, default shell, GNOME terminal shortcut, macOS screenshot location |
| `.chezmoitemplates/` | Shared template fragments (VS Code settings rendered to both OS paths) |
| `dot_zshrc.tmpl`, `dot_tmux.conf` | Shell and tmux |
| `dot_config/` | ghostty, starship, nvim, opencode, VS Code (Linux path) |
| `Library/Application Support/Code/User/` | VS Code (mac path) |
| `dot_claude/` | Global Claude Code instructions and settings |
| `CLAUDE.md` | How coding agents should work in this repo |

## tmux keybindings

The prefix is `C-b` or `C-Space`. `prefix ?` lists every binding; the custom
ones below have notes there too. The `-N` listing shows `C-b` in front of
every key, including the no-prefix ones (their notes say so).

| Keys | Action |
| --- | --- |
| `C-h` / `C-j` / `C-k` / `C-l` | Move to the pane or nvim split left/down/up/right (no prefix; pairs with vim-tmux-navigator in nvim) |
| `prefix h` / `j` / `k` / `l` | Move to the pane left/down/up/right |
| `prefix \|` or `\` or `%` | Split side by side, in the current dir |
| `prefix -` or `_` or `"` | Split top/bottom, in the current dir |
| `prefix c` | New window, in the current dir |
| `Alt-h` / `Alt-j` / `Alt-k` / `Alt-l` | Resize by 5 (no prefix; Ghostty sends Option as Alt on macOS) |
| `prefix H` / `J` / `K` / `L` | Resize by 5; keep tapping to repeat |
| `prefix =` | Balance the current pane and its neighbors |
| `prefix Alt-1`…`Alt-5` | Preset layouts (even-horizontal, even-vertical, main-h, main-v, tiled); Option works as Alt in Ghostty |
| `prefix C-l` | Clear the screen (plain `C-l` now moves panes) |
| `prefix C-k` | Kill to end of line (plain `C-k` now moves panes) |
| `prefix R` | Reload `~/.tmux.conf` |
| `prefix [` | Copy mode: `v` starts a selection, `y` copies to the system clipboard and exits |
| `prefix p` | Paste the most recent buffer |

Also on: mouse (click to focus, drag borders, scroll), windows and panes
numbered from 1, renumbering when a window closes, and 50k lines of history.

## Conventions

- `dot_` prefix ⇒ leading `.` in `$HOME`; `.tmpl` suffix ⇒ Go template with
  `.chezmoi.os` etc. available. See `chezmoi data` for all template variables.
- Scripts: `run_once_*` run once per machine, `run_onchange_*` rerun when their
  rendered content changes (they embed a hash of what they depend on).
  `before`/`after` is relative to writing the dotfiles.
- Neovim plugins are installed by lazy.nvim on first launch, not by chezmoi.
