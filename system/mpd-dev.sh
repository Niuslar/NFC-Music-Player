#!/bin/sh
# Runs MPD in the foreground for development on the Mac, serving the demo library.
# Listens on localhost only. Pass --silent to use a null output (no sound).
#
#   system/mpd-dev.sh            # then: python -m player.main --sim --playback mpd
set -eu
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
MUSIC="${MUSIC:-$ROOT/demo/music}"
mkdir -p "$ROOT/demo/mpd"

if [ "${1:-}" = "--silent" ]; then
  TYPE=null NAME=Silent MIXER=null
else
  TYPE=osx NAME=Mac MIXER=software
fi

cat > "$ROOT/demo/mpd/mpd.conf" <<EOF
music_directory "$MUSIC"
db_file "$ROOT/demo/mpd/db"
state_file "$ROOT/demo/mpd/state"
bind_to_address "127.0.0.1"
port "${MPD_PORT:-6600}"
auto_update "no"
audio_output {
  type "$TYPE"
  name "$NAME"
  mixer_type "$MIXER"
}
EOF

exec mpd --no-daemon "$ROOT/demo/mpd/mpd.conf"
