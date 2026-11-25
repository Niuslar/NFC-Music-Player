# NFC Album Player

![AI-assisted](https://img.shields.io/badge/development-AI--assisted-brightgreen)
![Code written with](https://img.shields.io/badge/code%20written%20with-Claude%20Code-brightgreen)
![Hardware](https://img.shields.io/badge/hardware%20%26%20design-human--directed-blue)

> **Disclaimer:** the software in this repository was written with an AI coding assistant (Claude Code). The project's idea, hardware choices and design decisions are mine, but I did not hand-write the code, so review it before relying on it.

A tabletop music player where each album is a card. Put a card in the slot and its album plays; take it out and it pauses. It runs on a Raspberry Pi Zero 2 W with a proper DAC, a small screen, a knob and four keys, and keeps a whole music collection on its own SD card. Everything you need to build one is here: the software, the wiring, a 3D-printed case and the circuit board behind its keys.

![Render of the case design: a wood-grain box with a black front and a black back, a stainless power key lit green, four silver keys marked previous, play/pause, next and back, a screen and an aluminium knob, five cards in a tray on the lid and one card standing in a slot](NFC-Player-Case/NFC-Player-Render.png)

*Render of the case design, made from the same model as its printable parts. The case has not been printed yet.*

## Where to start

The **[project site](https://niuslar.github.io/NFC-Music-Player/)** has the full guides:

| Guide | What is in it |
|---|---|
| [User manual](https://niuslar.github.io/NFC-Music-Player/docs/manual/) | Using the player: [controls](https://niuslar.github.io/NFC-Music-Player/docs/manual/#controls), [linking your first card](https://niuslar.github.io/NFC-Music-Player/docs/manual/#first-card), [settings](https://niuslar.github.io/NFC-Music-Player/docs/manual/#settings), [adding music](https://niuslar.github.io/NFC-Music-Player/docs/manual/#music), the [web remote](https://niuslar.github.io/NFC-Music-Player/docs/manual/#remote) and [lists](https://niuslar.github.io/NFC-Music-Player/docs/manual/#lists) |
| [Electronics guide](https://niuslar.github.io/NFC-Music-Player/docs/) | Building it: [parts](https://niuslar.github.io/NFC-Music-Player/docs/#parts), [preparing the Pi](https://niuslar.github.io/NFC-Music-Player/docs/#flash), [wiring](https://niuslar.github.io/NFC-Music-Player/docs/#wiring), [the front board](https://niuslar.github.io/NFC-Music-Player/docs/#board), [backups and updates](https://niuslar.github.io/NFC-Music-Player/docs/#backup) and [troubleshooting](https://niuslar.github.io/NFC-Music-Player/docs/#trouble) |
| [3D printing guide](https://niuslar.github.io/NFC-Music-Player/NFC-Player-Case/NFC-Player-Printing.html) | Printing the case parts |
| [Assembly guide](https://niuslar.github.io/NFC-Music-Player/NFC-Player-Case/NFC-Player-Assembly.html) | Putting the electronics into the case |

The software is on the [Releases page](https://github.com/Niuslar/NFC-Music-Player/releases). To try the player before buying anything, run the [simulator](#try-it-without-any-hardware).

## What it does

- **Cards are albums.** Blank NFC cards are linked to albums on the player itself, and each card remembers where it stopped. A card can also play a whole artist, or a list of songs from different albums.
- **Hi-Fi sound.** A Raspberry Pi DAC Pro gives 3.5 mm and RCA outputs.
- **Screen and controls.** A 2-inch screen shows the cover, track and time. The knob sets the volume and scrolls lists; four keys do previous, play/pause, next and back.
- **Standby and power.** A press of the power key puts the player on standby, and a card or any key wakes it at once. Holding it for 2 seconds turns the player off safely.
- **Music over USB.** Plug the player into a computer and its music appears as a drive called `MUSIC`.
- **Web remote.** From any phone or computer on the same Wi-Fi: browse the library, play from any track, link cards, upload or delete music and make lists.
- **Settings on the device.** Join a new Wi-Fi network from a phone, set a volume limit, delete music, or restart.
- **Signed updates over Wi-Fi.** **Firmware update** in the settings installs the newest release. The player checks its signature first, and goes back to the previous version if the new one does not start.

## Status

The electronics and software are done and tested on a real Pi. The case is designed but not yet printed.

- Tested on the Pi: the DAC, NFC reader, knob, keys, power key and light, USB drive mode, setup and the web remote, with the 0.91-inch OLED as the screen. The 2-inch ST7789 screen and joining a new Wi-Fi network from the settings have so far been tried only in the simulator.
- The case's printable parts, drawings and source files are in [NFC-Player-Case](NFC-Player-Case).

## Hardware

| Part | Used here |
|---|---|
| Computer | Raspberry Pi Zero 2 W |
| DAC | Raspberry Pi DAC Pro |
| Display | 2-inch ST7789 SPI LCD, 320×240 (a 0.91-inch SSD1306 I2C OLED also works) |
| NFC reader | PN532 over SPI, with NTAG215 cards |
| Knob | 24-click rotary encoder with push switch |
| Keys | Five momentary push buttons: four for playback, one for power |
| Power light | An LED on GPIO 22 |

The full parts list and wiring are in the [electronics guide](https://niuslar.github.io/NFC-Music-Player/docs/).

## Installing the software

### 1. Download a release

From the [Releases page](https://github.com/Niuslar/NFC-Music-Player/releases), download the three files of the newest release into one folder:

- `nfc-player-X.Y.Z.tar.gz`: the player itself
- `manifest.json`: its version, size and SHA-256 checksum
- `manifest.json.sig`: the signature of the manifest

Only the manifest is signed. Its checksum covers the tarball, so a good signature and a matching checksum together mean the tarball is the one that was released.

### 2. Check it

Do this at least before the first install. A player trusts the release key that comes with the first release you install on it, and from then on installs only updates signed by that key, so checking that first release by hand is what makes every later update safe. Updates from the settings, or with `deploy.sh`, are checked for you.

You need `ssh-keygen` from OpenSSH 8.1 or newer. It comes with macOS, Linux and Windows 10 and 11. If it says `unknown option -- Y`, update OpenSSH.

**The release key.** Save this line as a file called `allowed_signers` in the folder with the three files. It is the same as [`system/allowed_signers`](system/allowed_signers) in this repository.

```text
nfc-player-release namespaces="nfc-player-release" ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBNG2z/+2mxTZ/x4zmyfVjZgFa+9KMFRH0Z7DfmxEzkWDxFyXM+AXKKXkTZ2dmMEVd2C32r4rEvr9HIM9+Vl88ME= nfc-player release
```

Its fingerprint is `SHA256:7mMUd2P1uHX7o64klaQmtPYpVBFrPNvpwkcIh9UWavA`.

**Check the signature.** From that folder, on macOS or Linux, or in the Windows Command Prompt:

```sh
ssh-keygen -Y verify -f allowed_signers -I nfc-player-release -n nfc-player-release -s manifest.json.sig < manifest.json
```

In Windows PowerShell, which has no `<`, run it through the Command Prompt:

```powershell
cmd /c "ssh-keygen -Y verify -f allowed_signers -I nfc-player-release -n nfc-player-release -s manifest.json.sig < manifest.json"
```

A good release prints `Good "nfc-player-release" signature for nfc-player-release with ECDSA key SHA256:7mMUd2P1uHX7o64klaQmtPYpVBFrPNvpwkcIh9UWavA`. Anything else means: do not install it, and download it again.

**Check the checksum.** Print the tarball's SHA-256 and compare it with `"sha256"` in `manifest.json`:

| System | Command |
|---|---|
| macOS | `shasum -a 256 nfc-player-X.Y.Z.tar.gz` |
| Linux | `sha256sum nfc-player-X.Y.Z.tar.gz` |
| Windows | `certutil -hashfile nfc-player-X.Y.Z.tar.gz SHA256` |

They must be the same.

### 3. Install it on a new Pi

1. Prepare the Pi as in the electronics guide: [flash the SD card](https://niuslar.github.io/NFC-Music-Player/docs/#flash) with Raspberry Pi OS Lite (64-bit), hostname `nfcplayer` and SSH turned on, [boot it](https://niuslar.github.io/NFC-Music-Player/docs/#boot) and [fit the DAC](https://niuslar.github.io/NFC-Music-Player/docs/#dac).
2. From the folder with the release, copy it to the Pi and run setup. Replace `X.Y.Z` with the version, and use `yourname@nfcplayer.local` if your user name on the Pi is not the same as on your computer. The commands are the same on Windows, macOS and Linux.

   ```sh
   scp nfc-player-X.Y.Z.tar.gz nfcplayer.local:/tmp/
   ```

   ```sh
   ssh -t nfcplayer.local 'mkdir ~/nfc-player-X.Y.Z && tar -xzf /tmp/nfc-player-X.Y.Z.tar.gz -C ~/nfc-player-X.Y.Z && cd ~/nfc-player-X.Y.Z && sudo system/setup.sh'
   ```

   Setup installs the packages it needs, turns on SPI, I2C and USB drive mode, creates the music drive, and installs the player into `/opt/nfc-player`. It also installs the release key, which is why the release must be checked first.
3. Reboot when setup asks to:

   ```sh
   ssh nfcplayer.local 'sudo reboot'
   ```

4. Carry on with [wiring and testing](https://niuslar.github.io/NFC-Music-Player/docs/#wiring) in the electronics guide. The web remote's **Setup** page, at `http://nfcplayer.local/setup`, chooses the screen and knob and tests each part.

The `~/nfc-player-X.Y.Z` folder on the Pi is not needed after setup and can be deleted.

### Updating

**Firmware update** in the player's settings installs the newest release over Wi-Fi. That is the usual way.

To install a release from your computer instead, for a player with no internet connection or to choose the version yourself, download the three files and copy them over:

```sh
scp nfc-player-X.Y.Z.tar.gz manifest.json manifest.json.sig nfcplayer.local:/tmp/
```

```sh
ssh -t nfcplayer.local 'sudo install -d -o nfc-player /var/lib/nfc-player/update && sudo install -o nfc-player -m 644 /tmp/nfc-player-*.tar.gz /tmp/manifest.json /tmp/manifest.json.sig /var/lib/nfc-player/update/ && sudo /usr/local/sbin/nfc-player-update install'
```

This goes through the same steps as **Firmware update**: the player checks the signature, keeps the version it is running, and goes back to it if the new one does not start. It installs only a version newer than the one running. Card links, lists, settings and music are kept.

### With `deploy.sh`

If you have a copy of this repository on macOS or Linux, `deploy.sh` does the checks and the install in one step, on a new Pi or one that is already set up. It checks the signature and checksum against `system/allowed_signers` before sending anything:

```sh
./deploy.sh --release path/to/folder-with-the-three-files
```

```sh
./deploy.sh --release path/to/folder-with-the-three-files yourname@nfcplayer.local
```

Without `--release`, `deploy.sh` copies the working copy of the code to the Pi, for development.

## Try it without any hardware

The simulator shows the screen in a browser and stands in for the knob, keys, cards, USB port and Wi-Fi. You need Python 3.11 or newer.

```sh
python3 -m venv .venv
.venv/bin/pip install pillow numpy python-mpd2 pytest qrcode
.venv/bin/python -m player.demo_library demo/music
.venv/bin/python -m player.main --sim
```

On Windows, use `py` in place of `python3` and `.venv\Scripts\` in place of `.venv/bin/`.

Open `http://localhost:8137` for the simulated player and `http://localhost:8080` for the web remote. The demo library is generated tones, and the simulator is silent unless you run it with MPD (`system/mpd-dev.sh`, then add `--playback mpd`). Add `--display ssd1306` for the small OLED layout, and `--music path/to/your/music` for your own albums (install `mutagen` too, to read their tags).

Run the tests with:

```sh
.venv/bin/python -m pytest
```

## How it is put together

- `player/app.py` is the player's behaviour: a state machine fed with events from cards, controls, USB and the web.
- `player/ui/render.py` draws the screens.
- `player/hw/` holds the drivers (screens, NFC reader, knob and keys, USB drive mode), the simulator, and checks for each part.
- `player/web/` is the web remote, the Setup page, and the page a phone uses to give the player a new Wi-Fi network.
- `player/playback.py` talks to [MPD](https://www.musicpd.org/), which decodes and plays the music.
- `player/wifi.py` reads the Wi-Fi signal and runs the setup network for joining a new one.
- `player/update.py` and `system/nfc-player-update` do updates. The player keeps two copies of itself, in `/opt/nfc-player/a` and `b`. An update goes into the one that is not running, and the player goes back to the other if the new version does not start.
- `system/` has the Pi's setup script, services, root helpers and the release key.
- `NFC-Player-Case/` is the 3D-printed case and the front board, all generated from the dimensions in `case.py`. Its [README](NFC-Player-Case/README.md) explains how to rebuild them.
- `docs/` and the root `index.html` are the project site, served by GitHub Pages from the root of this repository (so the empty `.nojekyll` file has to stay).

## Contributing

Fixes and ideas are welcome. [CONTRIBUTING.md](CONTRIBUTING.md) covers the simulator, the tests and changing the case. For a bug or an idea, open an [issue](https://github.com/Niuslar/NFC-Music-Player/issues).

## Security

- **Updates** are installed only if they are signed by a key in `/etc/nfc-player/allowed_signers` on the player, which setup copies from the first release installed. See [Check it](#2-check-it).
- **The web remote has no password.** Anyone on the same network as the player can control it and add or delete music, and that includes an open network such as a café's. Use it on a home network you trust, or turn it off with `--web-port 0` in `system/nfc-player.service`.
- **Joining a new Wi-Fi network** is guarded separately: the page that takes the password works only on the player's own setup network, whose password is made up fresh each time and shown only on the player's screen.
- **The player runs as its own system user**, which can run only the player's own helpers with `sudo`, so a bug in it cannot take over the Pi.
