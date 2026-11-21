# NFC Album Player

![AI-assisted](https://img.shields.io/badge/development-AI--assisted-brightgreen)
![Code written with](https://img.shields.io/badge/code%20written%20with-Claude%20Code-brightgreen)
![Hardware](https://img.shields.io/badge/hardware%20%26%20design-human--directed-blue)

> **Disclaimer:** the software in this repository was written with an AI coding assistant (Claude Code). The project's idea, hardware choices and design decisions are mine, but I did not hand-write the code, so review it before relying on it.

A tabletop music player where each album is a card. Put a card in the slot and its album plays; take it out and it pauses. It is built for a Hi-Fi shelf: a proper DAC, a screen, a knob, and local storage for a whole collection.

![Render of the case design: a wood-grain box with a brass front set inside a thin rim and a black back, a lit power key, four keys marked previous, play/pause, next and back, a screen and a knob, five cards in a tray on the lid and one card standing in a slot](NFC-Player-Case/NFC-Player-Render.png)

*Render of the case design, made from the same model as its printable parts. The case has not been printed yet; the real build is currently parts on a bench.*

**Guides:** the [user manual](https://niuslar.github.io/NFC-Music-Player/docs/manual/), [build guide](https://niuslar.github.io/NFC-Music-Player/docs/) and [assembly guide](https://niuslar.github.io/NFC-Music-Player/NFC-Player-Case/NFC-Player-Assembly.html) are on the [project site](https://niuslar.github.io/NFC-Music-Player/).

## What it does

- **Cards are albums.** Blank NFC cards are linked to albums on the device itself. A card remembers where it stopped. A card can also play a whole artist, or a list: a folder of songs from different albums.
- **Hi-Fi output.** A Raspberry Pi DAC Pro provides 3.5 mm and RCA (white and red) outputs.
- **Screen and controls.** A 2-inch display shows the cover, track and time. A clicky knob sets the volume and scrolls lists; four buttons do previous, play/pause, next and back. A power key turns the player off safely and on again: the screen shows **Turning off** and goes dark once the Pi is off.
- **Music over USB.** Plug the player into a computer and its music appears as a drive called `MUSIC`.
- **Wi-Fi and settings.** An icon in the corner of the screen shows the Wi-Fi signal, struck through when there is none. Hold the knob for a second with no card in for settings: join a new Wi-Fi network, set a volume limit, delete albums, artists, lists or songs, see the web remote's address, or restart the player. To join a network, the player starts its own setup network with a one-time password shown on its screen; a phone joins it and sends the new network's name and password from a page the player serves there.
- **Web remote.** A page served by the player, from any phone or computer on the same Wi-Fi: browse albums, artists and songs, play from any track, seek, link cards, upload or delete music, and make lists of songs from anywhere in the library. Lists are kept beside the card links (`lists.json`), not on the music drive, and a card can play one like an album.

## Hardware

| Part | Used here |
|---|---|
| Computer | Raspberry Pi Zero 2 W |
| DAC | Raspberry Pi DAC Pro |
| Display | 2-inch ST7789 SPI LCD, 320×240 |
| NFC reader | PN532 over SPI, with NTAG215 cards |
| Knob | 24-click rotary encoder with push switch |
| Buttons | Five momentary push buttons: four for playback, one for power |
| Power light | An LED on GPIO 22, lit from early in boot until the Pi has shut down. In the case it is the power key's own light, switched through the front board |

A 0.91-inch 128×32 SSD1306 I2C OLED also works as a stand-in screen, with a compact layout and no cover art. Wire it to 3.3 V, GND, SDA (GPIO 2) and SCL (GPIO 3); it shares that bus with the DAC. Choose the screen and knob on the web remote's **Setup** page (`/setup`), which also tests the screen, DAC, buttons, knob and NFC reader. The settings are saved in `/var/lib/nfc-player/hardware.json` and used after a restart.

The full parts list, wiring diagrams and step-by-step instructions are in the [build guide](https://niuslar.github.io/NFC-Music-Player/docs/).

## Status

The electronics and software are done. The only step left is the case.

- The hardware has been built and tested on a real Pi: the DAC, NFC reader, knob, buttons, power key and light, and USB drive mode, along with setup and the web remote. The screen tested so far is the 0.91-inch SSD1306 OLED; the 2-inch ST7789 SPI display has not yet been tried on the real Pi, only in the simulator.
- The player logic, screens and web remote are also tested without the hardware, using a browser simulator. Joining a new Wi-Fi network from the settings is new and has so far been tried only in the simulator.
- The case is designed but not yet printed and assembled. Its printable parts, drawings and source files are in [NFC-Player-Case](NFC-Player-Case), and the [assembly guide](https://niuslar.github.io/NFC-Music-Player/NFC-Player-Case/NFC-Player-Assembly.html) is on the project site.

## Try it without any hardware

The simulator shows the display and stands in for the knob, buttons, cards, USB port and Wi-Fi.

```sh
python3 -m venv .venv
.venv/bin/pip install pillow numpy python-mpd2 pytest qrcode
.venv/bin/python -m player.demo_library demo/music
.venv/bin/python -m player.main --sim
```

On Windows, use `.venv\Scripts\` in place of `.venv/bin/`.

Add `--display ssd1306` to see the small OLED layout in the simulator.

Add `mutagen` to the `pip install` line if you point the simulator at your own tagged music with `--music`; without it, albums come from folder names only. On the Pi the tags come from MPD and nothing extra is needed.

Then open `http://localhost:8137` for the simulated device and `http://localhost:8080` for the web remote. The demo library is generated sine tones, and the simulator is silent unless you run it against MPD (`system/mpd-dev.sh`, then add `--playback mpd`).

Run the tests with:

```sh
.venv/bin/python -m pytest
```

## How it is put together

- `player/app.py` is the player's behaviour: a state machine fed with events from cards, controls, USB and the web.
- `player/ui/render.py` draws the screens.
- `player/hw/` holds the drivers (display, NFC reader, knob and buttons, USB drive mode), a simulator, and bring-up checks for each part.
- `player/web/` is the web remote, and the page a phone uses to give the player a new Wi-Fi network.
- `player/wifi.py` reads the Wi-Fi signal and runs the setup network for joining a new one, through NetworkManager and a small root helper (`system/nfc-player-wifi`).
- `player/playback.py` talks to [MPD](https://www.musicpd.org/), which does the decoding and audio output.
- `system/` has the Raspberry Pi setup script and service files.
- `NFC-Player-Case/` is the 3D-printed case. Every dimension is in `case.py`; Blender scripts build the STLs, pictures and assembly guide from it. `front-board/board.py` draws the circuit board behind the keys in KiCad from the same numbers, and `front-board/fab/` holds the files to order it.

## A note on the web remote

The web remote has no password. Anyone on the same network can control playback and add or delete music. Use it on a home network you trust, or turn it off with `--web-port 0`.

Joining a new Wi-Fi network is guarded separately: the page that takes a network's password only works while the player's own setup network is open, only for phones on that network, and that network's WPA2 password is made up fresh each time and shown only on the player's screen.
