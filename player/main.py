"""Entry point.

    python -m player.main --sim                     # browser simulator, silent fake player
    python -m player.main --sim --playback mpd      # simulator driving a real MPD
    python3 -m player.main --music /mnt/music --state /var/lib/nfc-player/state.json --playback mpd   # on the Pi
"""

import argparse
import os
import queue
import shutil
import socket
import subprocess
import sys
import time
import traceback
from pathlib import Path

from . import hwconfig
from .app import App, Mode
from .cards import Store
from .events import LibraryChanged
from .library import FileTags, Library
from .playback import FakePlayback, MpdPlayback
from .playlists import Playlists
from .update import HELPER as UPDATE_HELPER, HelperInstaller, NoUpdater, Updater
from .wifi import NetworkManagerBackend, NoWifi, SimBackend, Wifi

# GPIO numbers (BCM). The DAC HAT owns 2, 3, 18, 19, 20 and 21.
# GPIO 22 is the power light. The player never touches it: config.txt switches it on at boot
# (system/setup.sh adds the line) and system/nfc-player-screen-off switches it off at shutdown.
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
I2C_BUS = 1  # GPIO 2 (SDA) and 3 (SCL), shared with the DAC
DISPLAY_SPI = (0, 0)  # bus 0, CE0 (GPIO 8)
NFC_SPI = (0, 1)  # bus 0, CE1 (GPIO 7)
READER_WAIT_SECONDS = 10
# Longest the shutdown waits for "Turning off" to reach the screen. The OLED shares its clock
# line with the power key, so nothing reaches it while the key is still held down.
OFF_SCREEN_WAIT_SECONDS = 5.0


def power_off() -> None:
    """Shuts the Pi down, after the power key was held. setup.sh lets the player's user run this one command through sudo.

    "Turning off" stays on the screen while the Pi shuts down; system/nfc-player-screen-off
    switches the backlight off at the very end. The power key is also wired to GPIO 3,
    which wakes a Pi that has shut down.
    """
    subprocess.run(["sudo", "-n", "/usr/bin/systemctl", "poweroff"], check=True)


def restart() -> None:
    """Starts the player again in the same process, so new hardware settings are read."""
    os.execv(sys.executable, [sys.executable, "-m", "player.main", *sys.argv[1:]])


def run(app: App, event_queue: queue.Queue, display, shared=None, clock=time.monotonic, power_off=power_off, inputs=None, restart=restart) -> None:
    turning_off = False
    off_since = None
    asleep = False  # the screen is switched off for standby
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
        if inputs is not None:
            for event in pending:
                inputs.add(event)  # for the Setup page's tests
        try:
            for event in pending:
                app.handle(event, now)
            app.tick(now)
        except Exception as e:  # keep the device alive and say what happened
            traceback.print_exc()
            app.show_error(str(e) or type(e).__name__, now)
        if shared is not None:
            shared.snapshot = app.snapshot()
            shared.enabled = app.store.web_remote
        if app.screen_off(now):
            if not asleep:  # the OLED may miss it while the power key is still down: try again next time
                asleep = getattr(display, "sleep", lambda: True)() is not False
            continue
        if asleep:
            getattr(display, "wake", lambda: None)()
            asleep = False
        shown = display.show(app.render(now)) is not False  # only the OLED says False, when a frame did not get through
        if app.restart_requested:
            restart()  # "Restarting" is on the screen; normally this does not return
            return
        if app.mode is Mode.OFF and off_since is None:
            off_since = now
        if app.mode is Mode.OFF and not turning_off and (shown or now - off_since >= OFF_SCREEN_WAIT_SECONDS):
            # Once only, and after the "Turning off" screen is up: the shutdown stops this program,
            # so a frame that did not get through would never be sent again.
            turning_off = True
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


class NullDisplay:
    """Stands in for a screen that did not start, so the rest of the player still works."""

    def show(self, image) -> None:
        pass


def open_display(kind: str, rotate180: bool):
    if kind == "ssd1306":
        from .hw.ssd1306 import SSD1306, open_bus

        return SSD1306(open_bus(I2C_BUS), rotate180=rotate180)

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


def _attempt(status: dict, part: str, start):
    """Starts one part; a part that fails is reported on the Setup page instead of stopping the player."""
    try:
        result = start()
        status[part] = "ok"
        return result
    except Exception as e:
        traceback.print_exc()
        status[part] = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
        print(f"{part} did not start: {status[part]}", flush=True)
        return None


def start_hardware(events: queue.Queue, config: dict, status: dict):
    """Brings up every driver but the screen; returns (storage, nfc, keep). status gets each part's result."""
    from .hw.inputs import Buttons, Encoder
    from .hw.pn532 import CardWatcher
    from .hw.usb import UsbMonitor, UsbStorage

    nfc = _attempt(status, "nfc", lambda: CardWatcher(open_nfc(), events))
    if nfc is not None:
        nfc.start()
    keep = [  # hold references so the callbacks stay registered
        _attempt(status, "knob", lambda: Encoder(events, PINS["encoder_a"], PINS["encoder_b"], config["encoder"], config["encoder_reverse"])),
        _attempt(status, "buttons", lambda: Buttons(events, PINS["knob_switch"], PINS["buttons"])),
    ]
    _attempt(status, "usb", lambda: UsbMonitor(events).start())
    return UsbStorage(), nfc, keep


def effective_config(args) -> tuple[dict, dict, list[str]]:
    """(saved, running, overridden): the file's settings, those with command-line options applied, and which options won."""
    saved = hwconfig.load(args.config)
    running, overridden = dict(saved), []
    for key in hwconfig.DEFAULTS:
        value = getattr(args, key)
        if value is not None and value != saved[key]:
            running[key] = value
            overridden.append(key)
    return saved, running, overridden


def main() -> None:
    p = argparse.ArgumentParser(description="NFC album player")
    p.add_argument("--music", type=Path, default=Path("demo/music"), help="music root folder")
    p.add_argument("--state", type=Path, default=Path("demo/state.json"), help="card links and settings file")
    p.add_argument("--playback", choices=("fake", "mpd"), default="fake")
    p.add_argument("--mpd-port", type=int, default=6600)
    p.add_argument("--sim", action="store_true", help="run the browser simulator instead of real hardware")
    p.add_argument("--port", type=int, default=8137, help="simulator web port")
    p.add_argument("--web-port", type=int, default=8080, help="web remote port; 0 turns it off")
    p.add_argument("--config", type=Path, help="hardware settings file (default: hardware.json next to --state)")
    # These four override the settings file, which the web remote's Setup page edits.
    p.add_argument("--display", choices=tuple(hwconfig.DISPLAYS), help="st7789: 2-inch colour LCD; ssd1306: 0.91-inch OLED")
    p.add_argument("--encoder", choices=tuple(hwconfig.ENCODERS), help="pec11: clicky; em14: smooth optical")
    p.add_argument("--encoder-reverse", action="store_const", const=True, help="swap the knob's direction")
    p.add_argument("--rotate", type=int, choices=hwconfig.ROTATIONS, help="display orientation")
    args = p.parse_args()
    if args.config is None:
        args.config = args.state.parent / "hardware.json"
    saved, config, overridden = effective_config(args)
    print(f"Hardware: {config['display']} screen, {config['encoder']} knob" + (f" (from the command line: {', '.join(overridden)})" if overridden else ""), flush=True)

    # The screen comes first, so the boot logo is up while MPD, the library and the reader start.
    from .ui import render, tiny

    ui = tiny if config["display"] == "ssd1306" else render
    events: queue.Queue = queue.Queue()
    status: dict = {}
    if args.sim:
        wifi = Wifi(SimBackend())
    elif shutil.which("nmcli"):
        wifi = Wifi(NetworkManagerBackend())  # the Pi
    else:
        wifi = NoWifi()  # a computer running without the simulator: its Wi-Fi is not the player's to change
    if args.sim:
        from .hw.sim import server

        display = server.SimDisplay()
        server.start(events, display, args.port, wifi=wifi.backend)
        print(f"Simulator: http://localhost:{args.port}")
    else:
        display = _attempt(status, "screen", lambda: open_display(config["display"], config["rotate"] == 180)) or NullDisplay()
    display.show(ui.splash())

    playlists = Playlists(args.state.parent / "lists.json")  # lists made on the web remote, beside the card links
    if args.playback == "mpd":
        from mpd import ConnectionError as MpdConnectionError

        playback = MpdPlayback(port=args.mpd_port)
        for attempt in range(30):  # MPD starts alongside the player at boot, so it may not be up yet
            try:
                playback.rescan()
                break
            except (OSError, MpdConnectionError):
                if attempt == 29:
                    raise
                time.sleep(1)
        library = Library(args.music, tags=playback.tags, art=playback.art, playlists=playlists.all)  # MPD has already read every tag
    else:
        files = FileTags(args.music)
        library = Library(args.music, tags=files.tags, art=files.art, playlists=playlists.all)
        playback = FakePlayback(library)

    if args.sim:
        storage = None
        status = {part: "simulated" for part in ("screen", "nfc", "knob", "buttons", "usb")}
    else:
        storage, nfc, _keep = start_hardware(events, config, status)
        # Keep the logo up until the reader answers, so "Place a card" means a card will work.
        # A reader that never answers is reported on the Setup page; the player starts anyway.
        if nfc is not None and not nfc.ready.wait(READER_WAIT_SECONDS):
            print(f"NFC reader not ready after {READER_WAIT_SECONDS} s; starting without it", flush=True)

    from .hw.inputs import VOLUME_STEPS_PER_REV
    from .hw.selftest import InputLog, dac_test

    steps = 60 if args.sim else VOLUME_STEPS_PER_REV[config["encoder"]]
    if args.sim:  # checks and downloads real releases, with the keys in this folder, but installs nothing
        updater = Updater(allowed_signers=Path(__file__).resolve().parent.parent / "system" / "allowed_signers", workdir=args.state.parent / "update")
    elif Path(UPDATE_HELPER).exists():
        updater = Updater(HelperInstaller())  # the Pi
    else:
        updater = NoUpdater()
    app = App(library, Store(args.state), playback, storage, volume_steps_per_rev=steps, ui=ui, wifi=wifi, updater=updater)
    if isinstance(wifi, Wifi):
        wifi.start(enabled=app.store.wifi)  # switched off in the settings: it stays off after a restart
    inputs = InputLog()
    print(f"{len(library.albums)} albums, {len(library.artists)} artists and {len(library.lists)} lists in {args.music}", flush=True)

    from .web import server as web

    # On the Pi the drive is read-only until the root helper opens it; the simulator's folder is always writable.
    # Uploads and deletes from the web remote and Manage music on the player all go through it.
    writer = web.MusicWriter(lambda: events.put(LibraryChanged()), helper=None if args.sim else USB_HELPER)
    app.delete_music = lambda key, name=None: web.delete_music(library, writer, key, name)
    shared = None
    if args.web_port:
        shared = web.Shared()
        setup = web.Setup(
            path=args.config,
            running=config,
            overridden=overridden,
            hardware=status,
            inputs=inputs,
            dac_test=None if args.sim or args.playback != "mpd" else (lambda: dac_test(args.mpd_port)),
            simulator=args.sim,
        )
        try:
            web.start(events, shared, library, writer, args.web_port, bind="127.0.0.1" if args.sim else "0.0.0.0", setup=setup, playlists=playlists, wifi=wifi if isinstance(wifi, Wifi) else None)
            host = "localhost" if args.sim else f"{socket.gethostname()}.local"
            app.web_address = f"http://{host}" + ("" if args.web_port == 80 else f":{args.web_port}")
            if args.sim:
                wifi.backend.portal_address = f"localhost:{args.web_port}"
            app.is_uploading = lambda: writer.busy
            print(f"Web remote on port {args.web_port}", flush=True)
        except OSError as e:
            print(f"Web remote not started: {e}", flush=True)
            shared = None
    try:
        run(app, events, display, shared, power_off=server.power_cycle(display, events) if args.sim else power_off, inputs=inputs)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
