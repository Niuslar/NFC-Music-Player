#!/bin/sh
# Copies the player to the Pi over SSH: player/, system/ and the project files beside them.
# The case, the guides, the tests and local build output stay on this computer, and anything
# an earlier copy left in ~/nfc-player that is excluded now is removed there. The player's own
# state (card links, lists, settings) is kept in /var/lib/nfc-player and is not touched.
#
#   ./deploy.sh                       # to nfcplayer.local, same user name as on this computer
#   ./deploy.sh pi@nfcplayer.local
set -eu
cd "$(dirname "$0")"
TARGET="${1:-nfcplayer.local}"
rsync -az --delete --delete-excluded \
  --exclude .git --exclude .venv --exclude __pycache__ --exclude .pytest_cache \
  --exclude .DS_Store --exclude .claude --exclude .github --exclude demo --exclude tests \
  --exclude NFC-Player-Case --exclude docs --exclude index.html --exclude .nojekyll \
  ./ "$TARGET:nfc-player/"
echo "Copied to $TARGET:~/nfc-player"
echo "First time:   ssh $TARGET 'cd nfc-player && sudo system/setup.sh'"
echo "After edits:  ssh $TARGET 'sudo systemctl restart nfc-player'"
