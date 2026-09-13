# dotfiles

Personal config files, managed with [chezmoi](https://www.chezmoi.io/) so the same setup works across Linux and macOS.

## Setup on a new machine

```sh
sh -c "$(curl -fsLS get.chezmoi.io)" -- init --apply cryptid-megalodon
```

This installs chezmoi, clones this repo, and applies the dotfiles to your home directory.

## Day-to-day

```sh
chezmoi edit ~/.bashrc   # edit a managed file
chezmoi diff             # preview pending changes
chezmoi apply            # apply them
chezmoi cd               # open the source repo to commit/push
```

## Status

Migration to chezmoi is in progress. The files here (`bashrc`, `vimrc`, `tmux.conf`, etc.) are still plain copies from the old Linux-only setup and haven't been converted to chezmoi's source format yet.
