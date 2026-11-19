#!/bin/sh
# One-time setup on the Raspberry Pi. Safe to run again.
#
#   cd ~/nfc-player && sudo system/setup.sh            # music drive uses all free space but 3 GB
#   cd ~/nfc-player && sudo MUSIC_GB=100 system/setup.sh
set -eu

[ "$(id -u)" = 0 ] || { echo "Run with sudo." >&2; exit 1; }
RUN_USER="${SUDO_USER:-}"
[ -n "$RUN_USER" ] && [ "$RUN_USER" != root ] || { echo "Run with sudo from your normal user, not as root." >&2; exit 1; }
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG=/boot/firmware/config.txt
IMG=/srv/nfc-player/music.img
REBOOT=0

echo "== Packages"
apt-get update -q
apt-get install -y -q mpd python3-pil python3-numpy python3-spidev python3-gpiozero python3-lgpio python3-mpd exfatprogs fdisk alsa-utils i2c-tools dnsmasq-base python3-qrcode

echo "== Boot configuration ($CONFIG)"
if ! grep -q "^# nfc-player" "$CONFIG"; then
  sed -i 's/^dtparam=audio=on/#dtparam=audio=on/' "$CONFIG"   # built-in audio off; the DAC is the only output
  cat >> "$CONFIG" <<'EOF'

# nfc-player
[all]
dtparam=spi=on
dtoverlay=dwc2,dr_mode=peripheral
EOF
  REBOOT=1
fi
# I2C for the small OLED screen (it shares GPIO 2 and 3 with the DAC). Added separately so older installs get it too.
if ! grep -q "^dtparam=i2c_arm=on" "$CONFIG"; then
  printf '\n# nfc-player: I2C for the OLED screen\n[all]\ndtparam=i2c_arm=on\n' >> "$CONFIG"
  REBOOT=1
fi
# Power light on GPIO 22: the firmware switches it on within a second or two of power,
# long before Linux or the screen is up. system/nfc-player-screen-off switches it off at the end of a shutdown.
if ! grep -q "^gpio=22=" "$CONFIG"; then
  printf '\n# nfc-player: power light on as soon as the Pi starts\n[all]\ngpio=22=op,dh\n' >> "$CONFIG"
  REBOOT=1
fi
echo i2c-dev > /etc/modules-load.d/nfc-player-i2c.conf
modprobe i2c-dev 2>/dev/null || true
usermod -aG spi,gpio,audio,i2c "$RUN_USER"

echo "== Music drive ($IMG)"
mkdir -p /srv/nfc-player /mnt/music /var/lib/nfc-player
chown "$RUN_USER" /var/lib/nfc-player
if [ ! -e "$IMG" ]; then
  FREE_GB=$(df --output=avail -BG /srv/nfc-player | tail -n 1 | tr -dc 0-9)
  SIZE_GB="${MUSIC_GB:-$((FREE_GB - 3))}"
  [ "$SIZE_GB" -ge 1 ] || { echo "Not enough free space for a music drive." >&2; exit 1; }
  echo "Creating a ${SIZE_GB} GB drive"
  fallocate -l "${SIZE_GB}G" "$IMG"
  echo 'start=2048, type=7' | sfdisk -q "$IMG"
  LOOP=$(losetup --find --show --offset 1048576 "$IMG")
  mkfs.exfat -L MUSIC "$LOOP"
  losetup -d "$LOOP"
fi

echo "== USB helper and services"
install -m 755 "$APP_DIR/system/nfc-player-usb" /usr/local/sbin/nfc-player-usb
echo "OWNER=$RUN_USER" > /etc/nfc-player.conf
H=/usr/local/sbin/nfc-player-usb
# The power key shuts the Pi down with systemctl poweroff.
# The Wi-Fi helper joins new networks from the settings menu.
install -m 755 "$APP_DIR/system/nfc-player-wifi" /usr/local/sbin/nfc-player-wifi
W=/usr/local/sbin/nfc-player-wifi
echo "$RUN_USER ALL=(root) NOPASSWD: $H release, $H reclaim, $H rw, $H ro, /usr/bin/systemctl poweroff, $W scan, $W hotspot-up, $W hotspot-down, $W join" > /etc/sudoers.d/nfc-player
chmod 440 /etc/sudoers.d/nfc-player
visudo -cf /etc/sudoers.d/nfc-player >/dev/null
install -m 644 "$APP_DIR/system/nfc-player-usb.service" /etc/systemd/system/
# Turns the screen off at the very end of a shutdown, after the player has stopped.
install -D -m 755 "$APP_DIR/system/nfc-player-screen-off" /usr/lib/systemd/system-shutdown/nfc-player-screen-off
sed -e "s|@USER@|$RUN_USER|g" -e "s|@APP_DIR@|$APP_DIR|g" "$APP_DIR/system/nfc-player.service" > /etc/systemd/system/nfc-player.service

echo "== Wi-Fi setup network"
if ! command -v nmcli >/dev/null 2>&1; then
  echo "NetworkManager (nmcli) was not found, so joining a new network from the player's settings will not work."
  echo "Raspberry Pi OS Bookworm and later use NetworkManager; older releases do not."
fi
# While the setup network is up, every name a phone looks up points at the player,
# so the phone opens the Wi-Fi page by itself. This only applies to that network.
mkdir -p /etc/NetworkManager/dnsmasq-shared.d
echo "address=/#/10.42.0.1" > /etc/NetworkManager/dnsmasq-shared.d/nfc-player.conf

echo "== Audio"
# First sound card that is not HDMI or the built-in headphone output.
CARD=$(awk -F'[][]' '/^ *[0-9]+ \[/ {gsub(/ /, "", $2); if ($2 !~ /^(vc4hdmi|Headphones)/) {print $2; exit}}' /proc/asound/cards 2>/dev/null || true)
if [ -n "$CARD" ]; then
  if amixer -c "$CARD" scontrols 2>/dev/null | grep -q "'Digital'"; then
    MIXER='mixer_type "hardware"
  mixer_device "hw:CARD='"$CARD"'"
  mixer_control "Digital"'
  else
    MIXER='mixer_type "software"'
  fi
  OUTPUT='type "alsa"
  name "DAC"
  device "hw:CARD='"$CARD"'"
  '"$MIXER"
  echo "Sound card: $CARD"
else
  # No DAC: a silent output, so the player and web page still work end to end.
  OUTPUT='type "null"
  name "No DAC yet (silent)"
  mixer_type "null"'
  NO_DAC=1
fi
[ -e /etc/mpd.conf.dist ] || cp /etc/mpd.conf /etc/mpd.conf.dist 2>/dev/null || true
cat > /etc/mpd.conf <<EOF
# Written by nfc-player setup.sh
music_directory "/mnt/music"
playlist_directory "/var/lib/mpd/playlists"
db_file "/var/lib/mpd/tag_cache"
state_file "/var/lib/mpd/state"
user "mpd"
bind_to_address "127.0.0.1"
port "6600"
auto_update "no"
restore_paused "yes"
audio_output {
  $OUTPUT
}
EOF

systemctl daemon-reload
systemctl disable --now mpd.socket 2>/dev/null || true   # MPD should listen on localhost only
systemctl enable nfc-player-usb.service mpd.service nfc-player.service

echo
if [ "$REBOOT" = 1 ]; then
  echo "Done for now. Reboot with: sudo reboot"
else
  systemctl restart nfc-player-usb.service mpd.service nfc-player.service
  echo "All set. The player is running; follow it with: journalctl -u nfc-player -f"
fi
if [ "${NO_DAC:-0}" = 1 ]; then
  echo
  echo "No DAC was found, so playback is silent for now. Everything else works."
  echo "When the DAC is fitted, reboot and run this script again."
  echo "If it is still not found then, add 'dtoverlay=rpi-dacpro' to the end of $CONFIG and reboot."
fi
