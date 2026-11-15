"""USB drive mode on the Pi.

The gadget itself is created at boot by system/nfc-player-usb (as root). This
module watches it for a computer connecting or ejecting, and asks that helper
to hand the music image to the computer or take it back.
"""

import subprocess
import threading
import time
from pathlib import Path

from .. import events as ev

HELPER = "/usr/local/sbin/nfc-player-usb"
UDC_ROOT = Path("/sys/class/udc")
LUN_FILE = Path("/sys/kernel/config/usb_gadget/nfcplayer/functions/mass_storage.usb0/lun.0/file")


class UsbStorage:
    def __init__(self, helper: str = HELPER):
        self.helper = helper

    def _run(self, action: str) -> None:
        done = subprocess.run(["sudo", "-n", self.helper, action], capture_output=True, text=True, timeout=180)
        if done.returncode:
            raise OSError(f"USB {action} failed: {done.stderr.strip() or done.stdout.strip()}")

    def release(self) -> None:
        self._run("release")

    def reclaim(self) -> None:
        self._run("reclaim")


def _read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


class UsbMonitor(threading.Thread):
    def __init__(self, event_queue, udc_root: Path = UDC_ROOT, lun_file: Path = LUN_FILE, interval: float = 0.5):
        super().__init__(daemon=True)
        self.queue, self.udc_root, self.lun_file, self.interval = event_queue, udc_root, lun_file, interval
        self._host = False
        self._loaded = False

    def poll(self) -> None:
        states = [_read(p / "state") for p in self.udc_root.glob("*")] if self.udc_root.is_dir() else []
        # "configured" means a computer set the device up; a charger never gets that far.
        # A sleeping computer shows "suspended", which is not a disconnect.
        if "configured" in states:
            host = True
        elif "suspended" in states:
            host = self._host
        else:
            host = False
        if host != self._host:
            self._host = host
            self.queue.put(ev.UsbHost(host))
        loaded = bool(_read(self.lun_file))
        if self._loaded and not loaded and host:
            self.queue.put(ev.UsbEjected())  # the computer ejected the drive
        self._loaded = loaded

    def run(self) -> None:
        while True:
            self.poll()
            time.sleep(self.interval)
