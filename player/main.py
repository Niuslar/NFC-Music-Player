"""Entry point.

    python -m player.main --sim                     # browser simulator, silent fake player
    python -m player.main --sim --playback mpd      # simulator driving a real MPD
    python3 -m player.main --music /mnt/music --state /var/lib/nfc-player/state.json --playback mpd   # on the Pi
"""

import argparse
import queue
import subprocess
import time
import traceback
from pathlib import Path

from .app import App, Mode
from .cards import Store
from .events import LibraryChanged
from .library import FileTags, Library
from .playback import FakePlayback, MpdPlayback

# GPIO numbers (BCM). The DAC HAT owns 2, 3, 18, 19, 20 and 21.
PINS = {
    "display_dc": 25,
    "display_rst": 27,
    "display_bl": 13,
    "encoder_a": 5,
    "encoder_b": 6,
    "knob_switch": 26,
    "buttons": {"prev": 4, "play": 17, "next": 16, "back": 12, "power": 24},
}
USB_HELPER = "/usr/local/sbin/nfc-player-usb"
DISPLAY_SPI = (0, 0)  # bus 0, CE0 (GPIO 8)
NFC_SPI = (0, 1)  # bus 0, CE1 (GPIO 7)


def power_off() -> None:
    """Shuts the Pi down. setup.sh lets the player's user run this one command through sudo.

    "Turning off" stays on the screen while the Pi shuts down; system/nfc-player-screen-off
    switches the backlight off at the very end. The power key is also wired to GPIO 3,
    which wakes a Pi that has shut down.
    """
    subprocess.run(["sudo", "-n", "/usr/bin/systemctl", "poweroff"], check=True)


def run(app: App, event_queue: queue.Queue, display, shared=None, clock=time.monotonic, power_off=power_off) -> None:
    turning_off = False
    while True:
        try:
            pending = [event_queue.get(timeout=0.1)]
        except queue.Empty:
            pending = []
        while True:
            try:
                pending.append(event_queue.get_nowait())
            except queue.Empty:
                break
        now = clock()
        try:
            for event in pending:
                app.handle(event, now)
            app.tick(now)
        except Exception as e:  # keep the device alive and say what happened
            traceback.print_exc()
            app.show_error(str(e) or type(e).__name__, now)
        if shared is not None:
            shared.snapshot = app.snapshot()
        display.show(app.render(now))
        if app.mode is Mode.OFF and not turning_off:
            turning_off = True  # once only, and after the "Turning off" screen is up
            try:
                power_off()
            except Exception as e:
                traceback.print_exc()
                print(f"Could not shut down: {e}", flush=True)


def open_spi(bus: int, device: int, speed_hz: int):
    import spidev

    spi = spidev.SpiDev()
    spi.open(bus, device)
    spi.mode = 0
    spi.max_speed_hz = speed_hz
    return spi


def open_display(rotate180: bool):
    from gpiozero import DigitalOutputDevice

    from .hw.st7789 import ST7789

    return ST7789(
        open_spi(*DISPLAY_SPI, 40_000_000),
        dc=DigitalOutputDevice(PINS["display_dc"]),
        rst=DigitalOutputDevice(PINS["display_rst"], initial_value=True),
        bl=DigitalOutputDevice(PINS["display_bl"]),
        rotate180=rotate180,
    )


def open_nfc():
    from .hw.pn532 import PN532

    return PN532(open_spi(*NFC_SPI, 500_000))


def start_hardware(events: queue.Queue, args):
    """Brings up every driver; returns (display, storage)."""
    from .hw.inputs import Buttons, Encoder
    from .hw.pn532 import CardWatcher
    from .hw.usb import UsbMonitor, UsbStorage

    display = open_display(args.rotate == 180)
    CardWatcher(open_nfc(), events).start()
    keep = [  # hold references so the callbacks stay registered
        Encoder(events, PINS["encoder_a"], PINS["encoder_b"], args.encoder, args.encoder_reverse),
        Buttons(events, PINS["knob_switch"], PINS["buttons"]),
    ]
    UsbMonitor(events).start()
    return display, UsbStorage(), keep


def main() -> None:
    p = argparse.ArgumentParser(description="NFC album player")
    p.add_argument("--music", type=Path, default=Path("demo/music"), help="music root folder")
    p.add_argument("--state", type=Path, default=Path("demo/state.json"), help="card links and settings file")
    p.add_argument("--playback", choices=("fake", "mpd"), default="fake")
    p.add_argument("--mpd-port", type=int, default=6600)
    p.add_argument("--sim", action="store_true", help="run the browser simulator instead of real hardware")
    p.add_argument("--port", type=int, default=8137, help="simulator web port")
    p.add_argument("--web-port", type=int, default=8080, help="web remote port; 0 turns it off")
    p.add_argument("--encoder", choices=("pec11", "em14"), default="pec11", help="pec11: clicky (default); em14: smooth optical")
    p.add_argument("--encoder-reverse", action="store_true", help="swap the knob's direction")
    p.add_argument("--rotate", type=int, choices=(0, 180), default=0, help="display orientation")
    args = p.parse_args()

    events: queue.Queue = queue.Queue()
    if args.playback == "mpd":
        playback = MpdPlayback(port=args.mpd_port)
        for attempt in range(30):  # MPD may still be starting at boot
            try:
                playback.rescan()
                break
            except OSError:
                if attempt == 29:
                    raise
                time.sleep(1)
        library = Library(args.music, tags=playback.tags, art=playback.art)  # MPD has already read every tag
    else:
        files = FileTags(args.music)
        library = Library(args.music, tags=files.tags, art=files.art)
        playback = FakePlayback(library)

    if args.sim:
        from .hw.sim import server

        display, storage = server.SimDisplay(), None
        server.start(events, display, args.port)
        print(f"Simulator: http://localhost:{args.port}")
    else:
        display, storage, _keep = start_hardware(events, args)

    from .hw.inputs import VOLUME_STEPS_PER_REV

    steps = 60 if args.sim else VOLUME_STEPS_PER_REV[args.encoder]
    app = App(library, Store(args.state), playback, storage, volume_steps_per_rev=steps)
    print(f"{len(library.albums)} albums, {len(library.artists)} artists and {len(library.lists)} lists in {args.music}", flush=True)

    shared = None
    if args.web_port:
        from .web import server as web

        # On the Pi the drive is read-only until the root helper opens it; the simulator's folder is always writable.
        writer = web.MusicWriter(lambda: events.put(LibraryChanged()), helper=None if args.sim else USB_HELPER)
        shared = web.Shared()
        try:
            web.start(events, shared, library, writer, args.web_port, bind="127.0.0.1" if args.sim else "0.0.0.0")
            app.is_uploading = lambda: writer.busy
            print(f"Web remote on port {args.web_port}", flush=True)
        except OSError as e:
            print(f"Web remote not started: {e}", flush=True)
            shared = None
    try:
        run(app, events, display, shared, power_off=server.power_cycle(display, events) if args.sim else power_off)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
