"""Browser simulator: shows the display and stands in for the knob, buttons, cards, headphone jack and USB.

Serves on localhost only. The page polls /frame.png and posts inputs to /event.
"""

import io
import json
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ... import events as ev

PAGE = (Path(__file__).parent / "page.html").read_bytes()


def _to_event(msg: dict):
    kind = msg.get("type")
    if kind == "rotate":
        return ev.Rotate(int(msg["counts"]))
    if kind == "press" and msg.get("button") in ("knob", "knob_long", "prev", "play", "next", "back", "prev_hold", "next_hold"):
        return ev.Press(msg["button"])
    if kind == "card":
        return ev.CardInserted(str(msg["uid"])) if msg.get("uid") else ev.CardRemoved()
    if kind == "jack" and msg.get("action") in ("plug", "unplug"):
        return ev.AudioOutput(msg["action"] == "plug")
    if kind == "usb":
        return {"plug": ev.UsbHost(True), "unplug": ev.UsbHost(False), "eject": ev.UsbEjected()}.get(msg.get("action"))
    return None


class SimDisplay:
    def __init__(self):
        self._lock = threading.Lock()
        self._png = b""
        self._last = None

    def show(self, image) -> None:
        raw = image.tobytes()
        if raw == self._last:
            return
        buf = io.BytesIO()
        image.save(buf, "PNG")
        with self._lock:
            self._png, self._last = buf.getvalue(), raw

    def png(self) -> bytes:
        with self._lock:
            return self._png


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
