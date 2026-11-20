#!/bin/sh
# Copies the project from your computer to the Pi over SSH.
#
#   ./deploy.sh                       # to nfcplayer.local, same user name as on this computer
#   ./deploy.sh pi@nfcplayer.local
set -eu
cd "$(dirname "$0")"
TARGET="${1:-nfcplayer.local}"
rsync -az --delete \
  --exclude .venv --exclude demo --exclude __pycache__ --exclude .pytest_cache --exclude .git \
  ./ "$TARGET:nfc-player/"
echo "Copied to $TARGET:~/nfc-player"
echo "First time:   ssh $TARGET 'cd nfc-player && sudo system/setup.sh'"
echo "After edits:  ssh $TARGET 'sudo systemctl restart nfc-player'"
