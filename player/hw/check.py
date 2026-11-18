"""Bring-up checks, one part at a time. Stop the player first so the pins are free:

    sudo systemctl stop nfc-player
    python3 -m player.hw.check display     # test picture for 10 s, on the screen chosen in Setup
    python3 -m player.hw.check display --ssd1306   # ...or name the screen: --st7789 / --ssd1306
    python3 -m player.hw.check nfc         # prints card UIDs for 30 s
    python3 -m player.hw.check inputs      # prints knob and button events for 30 s
    python3 -m player.hw.check audio       # lists sound cards, then plays through MPD
    python3 -m player.hw.check usb         # shows what the USB port sees
"""

import queue
import subprocess
import sys
import time

from .. import hwconfig
from ..main import PINS, open_display, open_nfc

HARDWARE_FILE = "/var/lib/nfc-player/hardware.json"


def _config(args) -> dict:
    config = hwconfig.load(HARDWARE_FILE)
    for kind in hwconfig.DISPLAYS:
        if f"--{kind}" in args:
            config["display"] = kind
    return config


def display(args) -> None:
    from ..ui import render, tiny

    config = _config(args)
    ui = tiny if config["display"] == "ssd1306" else render
    open_display(config["display"], "--rotate" in args).show(ui.test_pattern())
    print(f"Screen: {hwconfig.DISPLAYS[config['display']]}")
    print("You should see a border on every edge and 'Screen test' reading left to right.")
    print("Upside down? Run again with --rotate, then choose 'Upside down' on the Setup page.")
    time.sleep(10)


def nfc(args) -> None:
    reader = open_nfc()
    version, revision = reader.begin()
    print(f"PN532 found, firmware {version}.{revision}. Hold a card to the reader...")
    last, end = "", time.monotonic() + 30
    while time.monotonic() < end:
        uid = reader.read_uid() or ""
        if uid != last:
            print(f"card {uid}" if uid else "card removed", flush=True)
            last = uid
        time.sleep(0.2)


def inputs(args) -> None:
    from .inputs import Buttons, Encoder

    events: queue.Queue = queue.Queue()
    kind = "em14" if "--em14" in args else "pec11" if "--pec11" in args else _config(args)["encoder"]
    _keep = (
        Encoder(events, PINS["encoder_a"], PINS["encoder_b"], kind),
        Buttons(events, PINS["knob_switch"], PINS["buttons"]),
    )
    print(f"Encoder type {kind}. Turn the knob (clockwise should be positive), push it, hold it, press each button...")
    if kind == "pec11":
        print("Each click should print about +11 or -11.")
    total, end = 0.0, time.monotonic() + 30
    while time.monotonic() < end:
        try:
            event = events.get(timeout=0.5)
        except queue.Empty:
            continue
        if hasattr(event, "counts"):
            total += event.counts
            print(f"rotate {event.counts:+.0f}   (total {total:+.0f}; one full turn is 256)", flush=True)
        else:
            print(event, flush=True)


def audio(args) -> None:
    from ..library import Library
    from ..playback import MpdPlayback

    print(subprocess.run(["aplay", "-l"], capture_output=True, text=True).stdout)
    albums = Library("/mnt/music").albums
    if not albums:
        print("No albums on the music drive yet, so nothing to play.")
        return
    player = MpdPlayback()
    player.rescan()
    player.set_volume(25)
    player.play_album(albums[0].path)
    print(f"Playing '{albums[0].title}' for 10 s at volume 25...")
    time.sleep(10)
    print(player.status())
    player.stop()


def usb(args) -> None:
    print(subprocess.run(["/usr/local/sbin/nfc-player-usb", "status"], capture_output=True, text=True).stdout)
    print("'configured' means a computer is connected; 'not attached' means none (or a charger).")


CHECKS = {"display": display, "nfc": nfc, "inputs": inputs, "audio": audio, "usb": usb}

if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    if name not in CHECKS:
        sys.exit(__doc__)
    CHECKS[name](sys.argv[2:])
