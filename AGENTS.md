# Working in this repo (for coding agents)

This is a [chezmoi](https://www.chezmoi.io/) source directory. Files here are
*not* the live dotfiles; chezmoi renders them into `$HOME`. Read the
[reference](https://www.chezmoi.io/reference/) before inventing conventions.

## Rules

- **Naming is semantic.** `dot_` ⇒ `.`, `private_` ⇒ mode 0600,
  `executable_` ⇒ +x, `.tmpl` ⇒ Go template. Don't rename files without
  understanding the prefix. Target path = source path with prefixes stripped.
- **Templates get `.tmpl`; plain files don't.** Only add `.tmpl` when the file
  actually uses `{{ }}`. Keep OS branching to `.chezmoi.os` (`darwin`/`linux`)
  and machine branching to `.machine` (`personal`/`work`).
- **Anything installed goes in `.chezmoidata/packages.yaml`**, never hard-coded
  in a script. Scripts that depend on it embed a hash comment so `run_onchange_`
  triggers correctly — keep that line when editing them.
- **Scripts must be idempotent** and safe to rerun. Use `set -eu`, check before
  installing, prefer `sudo` per command over running the whole script as root.
- **Shared content lives in `.chezmoitemplates/`** and is rendered with
  `{{ template "name" . }}`. VS Code settings work this way (two OS paths, one
  source). Don't duplicate.
- **Repo-only files** (`README.md`, `AGENTS.md`, …) must be listed in
  `.chezmoiignore` or chezmoi will copy them into `$HOME`.
- **No secrets in the repo.** Use chezmoi's `bitwarden`/`bitwardenFields`
  template functions (gated on `.bitwarden`) or `~/.zshrc.local`.
- **Don't run `chezmoi apply` on the user's machine** unless asked; it runs
  install scripts with `sudo`. Use `chezmoi diff` or a dry run instead.
- **Pushing from a work machine needs an account switch.** There `gh` is
  active as the work account (`blake-wolf`), which can't push this repo, and
  `gh` serves Git only the active account's token. Push with
  `gh auth switch -u cryptid-megalodon && git push; gh auth switch -u blake-wolf`
  so the work account is active again afterward. The repo must authenticate
  through `gh` rather than the keychain; that is per-clone `.git/config`, set
  once with
  `git config credential.helper '' && git config --add credential.helper '!gh auth git-credential'`.

## Verifying changes

Install chezmoi locally without applying anything, then render against a
throwaway destination:

```sh
sh -c "$(curl -fsLS get.chezmoi.io)" -- -b ~/.local/bin      # if not installed
tmp=$(mktemp -d)
printf '[data]\nmachine="personal"\nemail="x@y.z"\nbitwarden=false\n' > "$tmp/chezmoi.toml"
chezmoi --source "$PWD" --destination "$tmp/home" --config "$tmp/chezmoi.toml" \
    apply --dry-run --verbose --exclude scripts
chezmoi --source "$PWD" --config "$tmp/chezmoi.toml" \
    execute-template < .chezmoiscripts/run_onchange_before_10-packages.sh.tmpl
```

Also: `chezmoi doctor`, and `nvim --headless "+Lazy! sync" +qa` for the
Neovim config.
