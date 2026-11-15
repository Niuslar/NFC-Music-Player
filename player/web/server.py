"""Web remote: control playback and upload music from a browser on the same network.

There is no login: anyone on the network can use it. Two checks keep other
web sites from driving it through your browser: requests must name this device
in their Host header, and anything that changes state must carry a custom
header that a cross-site page cannot send.
"""

import io
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .. import events as ev
from ..library import AUDIO_EXT, IMAGE_EXT, Library

PAGE = Path(__file__).parent / "remote.html"
UPLOAD_EXT = AUDIO_EXT | IMAGE_EXT
HEADER = "X-Requested-With"
HEADER_VALUE = "nfc-player"
KEEP_FREE = 64 * 1024 * 1024  # never fill the music drive completely
_BAD_CHARS = re.compile(r'[\x00-\x1f"*:<>?\\|]')  # not allowed in exFAT names
COMMANDS = {"toggle", "next", "prev", "volume", "play_album", "link_card", "unlink_card"}


class UploadError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def safe_relative_path(raw: str) -> Path:
    """Cleans an uploaded file's path; raises UploadError if it must be refused."""
    parts = []
    for part in raw.replace("\\", "/").split("/"):
        part = part.strip()
        if part.startswith("."):  # "..", "." and hidden names are refused, never quietly dropped
            raise UploadError(400, f"'{part}' is not allowed in a path")
        part = _BAD_CHARS.sub("_", part).rstrip(". ")
        if not part:
            continue
        parts.append(part)
    if len(parts) < 2:
        raise UploadError(400, "Files must go inside an album folder")
    if len(parts) > 6 or any(len(p.encode()) > 200 for p in parts):
        raise UploadError(400, "Path is too deep or too long")
    path = Path(*parts)
    if path.suffix.lower() not in UPLOAD_EXT:
        raise UploadError(415, f"{path.suffix or 'This'} files are not music or cover images")
    return path


def _music_files(folder: Path) -> list[Path]:
    return sorted(
        (f for f in folder.iterdir() if f.is_file() and not f.is_symlink() and not f.name.startswith(".")),
        key=lambda f: f.name.lower(),
    )


def list_files(library: Library, album_path: str) -> list[dict]:
    album = library.get(album_path)
    if album is None:
        raise UploadError(404, "No such album")
    try:
        return [
            {"name": f.name, "size": f.stat().st_size, "track": f.suffix.lower() in AUDIO_EXT}
            for f in _music_files(library.root / album.path)
        ]
    except OSError:
        raise UploadError(404, "No such album")


def delete_music(library: Library, writer: "MusicWriter", album_path: str, name: str | None = None) -> int:
    """Deletes one file from an album, or the whole album when name is None. Returns files removed.

    Only albums the library knows about can be touched, and only files directly inside them.
    """
    album = library.get(album_path)
    if album is None:
        raise UploadError(404, "No such album")
    base = library.root.resolve()
    folder = (base / album.path).resolve()
    if base not in folder.parents or not folder.is_dir():
        raise UploadError(404, "No such album")
    if name is None:
        targets = [f for f in folder.iterdir() if f.is_file() or f.is_symlink()]
    else:
        target = folder / str(name)
        if str(name) != target.name or target.name.startswith(".") or target.is_symlink() or not target.is_file():
            raise UploadError(404, "No such file in that album")
        targets = [target]
    writer.begin()
    try:
        for f in targets:
            f.unlink()
        if not any(f.suffix.lower() in AUDIO_EXT for f in _music_files(folder)):
            # Last track gone: the cover and other leftovers go too, so no orphan folder remains.
            leftovers = [f for f in folder.iterdir() if f.is_file() or f.is_symlink()]
            for f in leftovers:
                f.unlink()
            targets += leftovers
        d = folder  # remove the album folder, then the artist folder, once each is empty
        while d != base and not any(d.iterdir()):
            d.rmdir()
            d = d.parent
    finally:
        writer.end()
    return len(targets)


class MusicWriter:
    """Makes the music drive writable while uploads run, read-only again soon after.

    helper is the root script on the Pi; None means the folder is always writable
    (the simulator on the Mac). on_change is called once uploads have settled.
    """

    def __init__(self, on_change, helper: str | None = None, idle_seconds: float = 5.0):
        self.on_change, self.helper, self.idle_seconds = on_change, helper, idle_seconds
        self._lock = threading.Lock()
        self._active = 0
        self._writable = False
        self._timer = None

    def _mount(self, mode: str) -> None:
        if self.helper is None:
            return
        done = subprocess.run(["sudo", "-n", self.helper, mode], capture_output=True, text=True, timeout=60)
        if done.returncode:
            raise OSError(done.stderr.strip() or f"could not switch the music drive to {mode}")

    @property
    def busy(self) -> bool:
        return self._active > 0

    def begin(self) -> None:
        with self._lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None
            if not self._writable:
                self._mount("rw")
                self._writable = True
            self._active += 1

    def end(self) -> None:
        with self._lock:
            self._active -= 1
            if self._active == 0:
                self._timer = threading.Timer(self.idle_seconds, self._settle)
                self._timer.daemon = True
                self._timer.start()

    def _settle(self) -> None:
        with self._lock:
            if self._active:
                return
            self._timer = None
            try:
                self._mount("ro")
            except OSError as e:
                print(f"web: {e}", flush=True)
            self._writable = False
        self.on_change()


class Shared:
    """Latest app snapshot, written by the main loop and read by web threads."""

    snapshot: dict = {"mode": "idle"}


def _host_allowed(host_header: str) -> bool:
    host = host_header.rsplit(":", 1)[0] if not host_header.startswith("[") else host_header.split("]")[0][1:]
    host = host.lower().rstrip(".")
    if host in ("localhost", socket.gethostname().lower()) or host.endswith(".local"):
        return True
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def start(event_queue, shared: Shared, library: Library, writer: MusicWriter, port: int, bind: str = "0.0.0.0"):
    covers: dict[str, bytes] = {}

    class Handler(BaseHTTPRequestHandler):
        timeout = 120
        protocol_version = "HTTP/1.1"

        def _send(self, status: int, body: bytes, ctype: str = "application/json", cache: str = "no-store") -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, data) -> None:
            self._send(status, json.dumps(data).encode())

        def _fail(self, status: int, message: str) -> None:
            self.close_connection = True  # the request body may not have been read
            self._json(status, {"error": message})

        def _guard(self, changes_state: bool) -> bool:
            if not _host_allowed(self.headers.get("Host", "")):
                self._fail(403, "Open this page by the player's own name or address")
                return False
            if changes_state and self.headers.get(HEADER) != HEADER_VALUE:
                self._fail(403, "Missing request header")
                return False
            return True

        def do_GET(self):
            if not self._guard(False):
                return
            url = urlsplit(self.path)
            if url.path == "/":
                self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            elif url.path == "/api/state":
                state = dict(shared.snapshot)
                state["uploading"] = writer.busy
                try:
                    state["free_bytes"] = shutil.disk_usage(library.root).free
                except OSError:
                    state["free_bytes"] = None
                self._json(200, state)
            elif url.path == "/api/albums":
                self._json(
                    200,
                    [{"path": a.path, "title": a.title, "artist": a.artist, "tracks": len(a.tracks)} for a in library.albums],
                )
            elif url.path == "/api/files":
                try:
                    self._json(200, list_files(library, parse_qs(url.query).get("album", [""])[0]))
                except UploadError as e:
                    self._fail(e.status, str(e))
            elif url.path == "/api/cover":
                self._cover(parse_qs(url.query).get("album", [""])[0])
            else:
                self._fail(404, "Not found")

        def _cover(self, album_path: str) -> None:
            album = library.get(album_path)
            if album is None or album.cover is None:
                self._fail(404, "No cover")
                return
            key = f"{album.cover}:{album.cover.stat().st_mtime_ns}"
            if key not in covers:
                from PIL import Image

                img = Image.open(album.cover).convert("RGB")
                img.thumbnail((400, 400))
                buf = io.BytesIO()
                img.save(buf, "JPEG", quality=82)
                if len(covers) > 200:
                    covers.clear()
                covers[key] = buf.getvalue()
            self._send(200, covers[key], "image/jpeg", "max-age=300")

        def do_POST(self):
            if not self._guard(True):
                return
            path = urlsplit(self.path).path
            if path == "/api/delete":
                self._delete()
                return
            if path != "/api/command":
                self._fail(404, "Not found")
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                if length > 4096:
                    raise ValueError
                msg = json.loads(self.rfile.read(length))
                action, value = msg["action"], msg.get("value")
                if action not in COMMANDS:
                    raise ValueError
                if action == "volume":
                    value = int(value)
            except (ValueError, KeyError, TypeError):
                self._fail(400, "Bad command")
                return
            event_queue.put(ev.WebCommand(action, value))
            self._json(200, {"ok": True})

        def _delete(self) -> None:
            try:
                length = int(self.headers.get("Content-Length", 0))
                if length > 4096:
                    raise ValueError
                msg = json.loads(self.rfile.read(length))
                album_path, name = str(msg["album"]), msg.get("file")
            except (ValueError, KeyError, TypeError):
                self._fail(400, "Bad request")
                return
            try:
                if shared.snapshot.get("mode") == "transfer":
                    raise UploadError(409, "The music drive is connected to a computer over USB")
                removed = delete_music(library, writer, album_path, name)
            except UploadError as e:
                self._fail(e.status, str(e))
                return
            except OSError as e:
                self._fail(500, str(e))
                return
            self._json(200, {"ok": True, "removed": removed})

        def do_PUT(self):
            if not self._guard(True):
                return
            url = urlsplit(self.path)
            if url.path != "/api/upload":
                self._fail(404, "Not found")
                return
            try:
                rel = safe_relative_path(parse_qs(url.query).get("path", [""])[0])
                if shared.snapshot.get("mode") == "transfer":
                    raise UploadError(409, "The music drive is connected to a computer over USB")
                try:
                    length = int(self.headers["Content-Length"])
                except (KeyError, TypeError, ValueError):
                    raise UploadError(411, "Upload size missing")
                self._receive(rel, length)
            except UploadError as e:
                self._fail(e.status, str(e))
                return
            except OSError as e:
                self._fail(500, str(e))
                return
            self._json(200, {"ok": True, "path": rel.as_posix()})

        def _receive(self, rel: Path, length: int) -> None:
            root = library.root.resolve()
            dest = (root / rel).resolve()
            if root not in dest.parents:
                raise UploadError(400, "Path leaves the music folder")
            writer.begin()
            temp = dest.with_name(f".{dest.name}.part")  # hidden, so the library ignores it
            try:
                if shutil.disk_usage(root).free - length < KEEP_FREE:
                    raise UploadError(507, "Not enough space on the music drive")
                dest.parent.mkdir(parents=True, exist_ok=True)
                remaining = length
                with open(temp, "wb") as f:
                    while remaining:
                        chunk = self.rfile.read(min(remaining, 1 << 20))
                        if not chunk:
                            raise UploadError(400, "Upload was cut short")
                        f.write(chunk)
                        remaining -= len(chunk)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp, dest)
            finally:
                try:
                    temp.unlink()
                except OSError:
                    pass
                writer.end()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer((bind, port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
