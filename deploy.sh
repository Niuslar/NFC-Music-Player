#!/bin/sh
# Puts the player on a Pi over SSH, in one of two ways.
#
# From this folder, for development: copies player/, system/ and the project files beside them.
# The case, the guides, the tests and local build output stay on this computer, and anything
# an earlier copy left in ~/nfc-player that is excluded now is removed there. The player's own
# state (card links, lists, settings) is kept in /var/lib/nfc-player and is not touched.
# The service runs the copy in /opt/nfc-player, so a copy sent here is used once it is installed there.
#
# From a release, with --release: DIR holds the three files of a GitHub release
# (nfc-player-X.Y.Z.tar.gz, manifest.json and manifest.json.sig). Their signature is checked here
# with system/allowed_signers before anything is sent. On a player that is already set up, they
# are installed exactly as an update over Wi-Fi would be: checked again on the player, written
# into the copy that is not running, and rolled back if the new version does not start. On a Pi
# that is not set up yet, the release is unpacked into ~/nfc-player-X.Y.Z and system/setup.sh is run.
#
#   ./deploy.sh                                   # to nfcplayer.local, same user name as on this computer
#   ./deploy.sh pi@nfcplayer.local
#   ./deploy.sh --release ~/Downloads/nfc-player-0.3.0
#   ./deploy.sh --release ~/Downloads/nfc-player-0.3.0 pi@nfcplayer.local
set -eu
CALLED_FROM="$(pwd)"
cd "$(dirname "$0")"

usage() {
  echo "Usage: $0 [TARGET]" >&2
  echo "       $0 --release DIR [TARGET]" >&2
  exit 2
}

release() {
  case "$1" in /*) DIR="$1" ;; *) DIR="$CALLED_FROM/$1" ;; esac   # relative to where it was run from
  TARGET="$2"
  [ -d "$DIR" ] || { echo "$DIR is not a folder." >&2; exit 1; }
  for f in manifest.json manifest.json.sig; do
    [ -f "$DIR/$f" ] || { echo "$DIR has no $f. Download all three files of the release." >&2; exit 1; }
  done
  set -- "$DIR"/nfc-player-*.tar.gz
  [ -f "$1" ] || { echo "$DIR has no nfc-player-X.Y.Z.tar.gz. Download all three files of the release." >&2; exit 1; }
  [ $# = 1 ] || { echo "$DIR has more than one nfc-player-*.tar.gz. Keep only the release's own." >&2; exit 1; }
  TARBALL="$1"

  # The same checks the player makes, before anything goes over the network.
  grep -qv '^\s*\(#\|$\)' system/allowed_signers 2>/dev/null \
    || { echo "system/allowed_signers has no release keys, so the release cannot be checked." >&2; exit 1; }
  ssh-keygen -Y verify -f system/allowed_signers -I nfc-player-release -n nfc-player-release \
    -s "$DIR/manifest.json.sig" < "$DIR/manifest.json" >/dev/null 2>&1 \
    || { echo "The release's signature is not valid. Download it again from the project's GitHub Releases page." >&2; exit 1; }
  VERSION="$(python3 -I - "$DIR/manifest.json" "$TARBALL" <<'EOF'
import hashlib, json, os, sys
m = json.load(open(sys.argv[1]))
data = open(sys.argv[2], "rb").read()
if m.get("name") != "nfc-player" or m.get("file") != os.path.basename(sys.argv[2]):
    sys.exit("The manifest is for a different file than " + os.path.basename(sys.argv[2]) + ".")
if len(data) != m.get("size") or hashlib.sha256(data).hexdigest() != m.get("sha256"):
    sys.exit("The tarball does not match the signed manifest. Download it again.")
print(m["version"].lstrip("v"))
EOF
)"
  echo "Release $VERSION: signature and checksum are good"

  if ssh "$TARGET" 'test -x /usr/local/sbin/nfc-player-update'; then
    REMOTE="$(ssh "$TARGET" 'mktemp -d /tmp/nfc-player-release.XXXXXX')"
    scp -q "$TARBALL" "$DIR/manifest.json" "$DIR/manifest.json.sig" "$TARGET:$REMOTE/"
    echo "Copied to $TARGET:$REMOTE; installing"
    ssh -t "$TARGET" "cd $REMOTE && sudo install -d -o nfc-player /var/lib/nfc-player/update \
      && sudo install -o nfc-player -m 644 nfc-player-*.tar.gz manifest.json manifest.json.sig /var/lib/nfc-player/update/ \
      && sudo /usr/local/sbin/nfc-player-update install; status=\$?; rm -rf $REMOTE; exit \$status"
  else
    echo "$TARGET is not set up yet: unpacking into ~/nfc-player-$VERSION and running system/setup.sh"
    scp -q "$TARBALL" "$TARGET:/tmp/"
    NAME="$(basename "$TARBALL")"
    ssh -t "$TARGET" "rm -rf ~/nfc-player-$VERSION && mkdir ~/nfc-player-$VERSION \
      && tar -xzf /tmp/$NAME -C ~/nfc-player-$VERSION && rm /tmp/$NAME \
      && cd ~/nfc-player-$VERSION && sudo system/setup.sh"
  fi
}

case "${1:-}" in
  --release)
    [ $# = 2 ] || [ $# = 3 ] || usage
    release "$2" "${3:-nfcplayer.local}"
    exit 0 ;;
  -*) usage ;;
esac
[ $# -le 1 ] || usage

TARGET="${1:-nfcplayer.local}"
rsync -az --delete --delete-excluded \
  --exclude .git --exclude .venv --exclude __pycache__ --exclude .pytest_cache \
  --exclude .DS_Store --exclude .claude --exclude .github --exclude demo --exclude tests \
  --exclude tools --exclude NFC-Player-Case --exclude docs --exclude index.html --exclude .nojekyll \
  --exclude dist \
  ./ "$TARGET:nfc-player/"
echo "Copied to $TARGET:~/nfc-player"
echo "First time:   ssh $TARGET 'cd nfc-player && sudo system/setup.sh'"
echo "After edits:  ssh $TARGET 'sudo /usr/local/sbin/nfc-player-update install-dir nfc-player && sudo systemctl restart nfc-player'"
