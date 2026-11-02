#!/bin/sh
# Clones the personal Claude Code plugins repo, which dot_claude/modify_settings.json
# loads through CLAUDE_CODE_PLUGIN_DIRS. The repo is private and work machines
# keep the work account active in gh, so the clone authenticates as the personal
# account explicitly, and keeps doing so for later pulls and pushes.
# Reruns if this script changes.
set -eu

dest="$HOME/repos/claude-plugins"
url="https://github.com/cryptid-megalodon/claude-plugins.git"
helper='!f() { test "$1" = get && echo username=cryptid-megalodon && echo "password=$(gh auth token -u cryptid-megalodon)"; }; f'

if ! command -v gh >/dev/null 2>&1 || ! gh auth token -u cryptid-megalodon >/dev/null 2>&1; then
    echo "==> gh is not signed in as cryptid-megalodon, skipping claude-plugins clone"
    exit 0
fi

if [ ! -d "$dest/.git" ]; then
    echo "==> Cloning claude-plugins to $dest"
    mkdir -p "$(dirname "$dest")"
    git -c credential.helper= -c credential.helper="$helper" clone "$url" "$dest"
fi

git -C "$dest" config user.email 102880526+cryptid-megalodon@users.noreply.github.com
git -C "$dest" config --replace-all credential.helper ''
git -C "$dest" config --add credential.helper "$helper"
