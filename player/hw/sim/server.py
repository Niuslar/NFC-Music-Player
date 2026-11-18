"""Browser simulator: shows the display and stands in for the knob, buttons, cards and USB.

Serves on localhost only. The page polls /frame.png and posts inputs to /event.
"""

import io
import json
import os
import queue
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ... import events as ev

PAGE = (Path(__file__).parent / "page.html").read_bytes()


def _to_event(msg: dict):
    kind = msg.get("type")
    if kind == "rotate":
        return ev.Rotate(int(msg["counts"]))
    if kind == "press" and msg.get("button") in ("knob", "knob_long", "prev", "play", "next", "back", "back_long", "prev_hold", "next_hold", "power"):
        return ev.Press(msg["button"])
    if kind == "card":
        return ev.CardInserted(str(msg["uid"])) if msg.get("uid") else ev.CardRemoved()
    if kind == "usb":
        return {"plug": ev.UsbHost(True), "unplug": ev.UsbHost(False), "eject": ev.UsbEjected()}.get(msg.get("action"))
    return None


class SimDisplay:
    def __init__(self):
        self._lock = threading.Lock()
        self._png = b""
        self._last = None
        self.size = (320, 240)

    def show(self, image) -> None:
        raw = image.tobytes()
        if raw == self._last:
            return
        buf = io.BytesIO()
        image.save(buf, "PNG")
        with self._lock:
            self._png, self._last, self.size = buf.getvalue(), raw, image.size

    def png(self) -> bytes:
        with self._lock:
            return self._png


def power_cycle(display: SimDisplay, event_queue: queue.Queue, shutdown_seconds: float = 2.0):
    """Stands in for systemctl poweroff: the screen goes dark, and the power key starts the player again."""

    def power_off() -> None:
        from PIL import Image

        time.sleep(shutdown_seconds)  # "Turning off" stays up while the Pi shuts down
        display.show(Image.new("RGB", display.size))
        print("Simulator: off. Press the power key to turn it on.", flush=True)
        while event_queue.get() != ev.Press("power"):
            pass  # a Pi that is off ignores everything else
        print("Simulator: starting again", flush=True)
        os.execv(sys.executable, [sys.executable, "-m", "player.main", *sys.argv[1:]])

    return power_off


def start(event_queue: queue.Queue, display: SimDisplay, port: int = 8137) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, ctype: str, body: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/":
                self._send(200, "text/html; charset=utf-8", PAGE)
            elif path == "/frame.png":
                self._send(200, "image/png", display.png())
            else:
                self._send(404, "text/plain", b"not found")

        def do_POST(self):
            if self.path != "/event":
                self._send(404, "text/plain", b"not found")
                return
            try:
                msg = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                event = _to_event(msg)
            except (ValueError, KeyError, TypeError):
                event = None
            if event is None:
                self._send(400, "text/plain", b"bad event")
                return
            event_queue.put(event)
            self._send(204, "text/plain", b"")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
