#!/bin/sh
# Copies the player to the Pi over SSH, for development: player/, system/ and the project files beside them.
# The case, the guides, the tests and local build output stay on this computer, and anything
# an earlier copy left in ~/nfc-player that is excluded now is removed there. The player's own
# state (card links, lists, settings) is kept in /var/lib/nfc-player and is not touched.
# The service runs the copy in /opt/nfc-player, so a copy sent here is used once it is installed there.
# Players out in the world get signed updates over Wi-Fi instead.
#
#   ./deploy.sh                       # to nfcplayer.local, same user name as on this computer
#   ./deploy.sh pi@nfcplayer.local
set -eu
cd "$(dirname "$0")"
TARGET="${1:-nfcplayer.local}"
rsync -az --delete --delete-excluded \
  --exclude .git --exclude .venv --exclude __pycache__ --exclude .pytest_cache \
  --exclude .DS_Store --exclude .claude --exclude .github --exclude demo --exclude tests \
  --exclude tools --exclude NFC-Player-Case --exclude docs --exclude index.html --exclude .nojekyll \
  ./ "$TARGET:nfc-player/"
echo "Copied to $TARGET:~/nfc-player"
echo "First time:   ssh $TARGET 'cd nfc-player && sudo system/setup.sh'"
echo "After edits:  ssh $TARGET 'sudo /usr/local/sbin/nfc-player-update install-dir nfc-player && sudo systemctl restart nfc-player'"
