"""Web remote: control playback and upload music from a browser on the same network.

There is no login: anyone on the network can use it. Two checks keep other
web sites from driving it through your browser: requests must name this device
in their Host header, and anything that changes state must carry a custom
header that a cross-site page cannot send.

While the player's own Wi-Fi setup network is up, phones on that network get the
Wi-Fi page (/wifi) instead, whatever address they ask for, so they open it by themselves.
Only they can send it a network to join.
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
from .. import hwconfig
from ..library import AUDIO_EXT, IMAGE_EXT, Library
from ..playlists import ListError, Playlists, key_of

PAGE = Path(__file__).parent / "remote.html"
SETUP_PAGE = Path(__file__).parent / "setup.html"
WIFI_PAGE = Path(__file__).parent / "wifi.html"
UPLOAD_EXT = AUDIO_EXT | IMAGE_EXT
HEADER = "X-Requested-With"
HEADER_VALUE = "nfc-player"
KEEP_FREE = 64 * 1024 * 1024  # never fill the music drive completely
_BAD_CHARS = re.compile(r'[\x00-\x1f"*:<>?\\|]')  # not allowed in exFAT names
COMMANDS = {"toggle", "next", "prev", "volume", "seek", "play_album", "play_at", "link_card", "unlink_card"}
LIST_BODY_LIMIT = 1 << 20  # a long list's track paths


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


def _own_files(library: Library, album, folder: Path) -> list[Path]:
    """The files that belong to an album or list: its whole folder, or just its tracks when the folder is shared."""
    if album.whole_folder:
        return _music_files(folder)
    names = {Path(t.path).name for t in album.tracks}
    return [f for f in _music_files(folder) if f.name in names]


def list_files(library: Library, album_path: str) -> list[dict]:
    album = library.get(album_path)
    if album is None or album.folder is None:
        raise UploadError(404, "No such album")
    try:
        return [
            {"name": f.name, "size": f.stat().st_size, "track": f.suffix.lower() in AUDIO_EXT}
            for f in _own_files(library, album, library.root / album.folder)
        ]
    except OSError:
        raise UploadError(404, "No such album")


def delete_music(library: Library, writer: "MusicWriter", album_path: str, name: str | None = None) -> int:
    """Deletes one file from an album, or the whole album when name is None. Returns files removed.

    Only albums and lists the library knows about can be touched, and only files directly
    inside their folder. An album that shares its folder with others loses only its own tracks.
    """
    album = library.get(album_path)
    if album is None or album.folder is None:
        raise UploadError(404, "No such album")
    base = library.root.resolve()
    folder = (base / album.folder).resolve()
    if base not in folder.parents or not folder.is_dir():
        raise UploadError(404, "No such album")
    if name is None and album.whole_folder:
        targets = [f for f in folder.iterdir() if f.is_file() or f.is_symlink()]
    elif name is None:
        targets = _own_files(library, album, folder)
    else:
        target = folder / str(name)
        if str(name) != target.name or target.name.startswith(".") or target.is_symlink() or not target.is_file():
            raise UploadError(404, "No such file in that album")
        if not album.whole_folder and target not in _own_files(library, album, folder):
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


class Setup:
    """What the Setup page shows and changes: the hardware settings, how each part started, and tests."""

    def __init__(self, path: Path, running: dict, overridden=(), hardware=None, inputs=None, dac_test=None, simulator: bool = False):
        self.path, self.running, self.overridden = Path(path), dict(running), list(overridden)
        self.hardware = hardware if hardware is not None else {}
        self.inputs, self.dac_test, self.simulator = inputs, dac_test, simulator
        self._dac_lock = threading.Lock()

    def state(self) -> dict:
        saved = hwconfig.load(self.path)
        pending = [k for k in saved if k not in self.overridden and saved[k] != self.running[k]]
        return {
            "saved": saved,
            "running": self.running,
            "overridden": self.overridden,
            "restart_needed": pending,
            "choices": hwconfig.choices(),
            "hardware": self.hardware,
            "dac_test": self.dac_test is not None,
            "simulator": self.simulator,
        }

    def save(self, raw: dict) -> dict:
        hwconfig.save(self.path, {**hwconfig.load(self.path), **raw})
        return self.state()

    def test_dac(self) -> dict:
        if self.dac_test is None:
            return {"ok": False, "message": "There is no DAC to test here: the simulator and the fake player make no sound."}
        if not self._dac_lock.acquire(blocking=False):
            return {"ok": False, "message": "A test is already playing."}
        try:
            return self.dac_test()
        except Exception as e:
            return {"ok": False, "message": f"The test failed: {e}"}
        finally:
            self._dac_lock.release()


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


def _track_info(t) -> dict:
    return {"path": t.path, "title": t.title, "artist": t.artist, "album": t.album}


def _item_info(a) -> dict:
    return {
        "key": a.key,
        "kind": a.kind,
        "title": a.title,
        "artist": a.artist,
        "tracks": len(a.tracks),
        "albums": a.albums,
        "files": a.folder is not None,
        "playlist": a.is_playlist,
    }


def change_list(playlists: Playlists, library: Library, msg: dict) -> dict:
    """Does one change to the made lists. Returns the list as it is now ({} once deleted)."""
    op, list_id = msg.get("op"), msg.get("id")
    tracks = msg.get("tracks", [])
    if isinstance(tracks, list) and op in ("create", "add") and any(library.track(t) is None for t in tracks if isinstance(t, str)):
        raise ListError("Some of those tracks are no longer in the library")
    if op == "create":
        made = playlists.create(msg.get("name"), tracks)
    elif op == "rename":
        made = playlists.rename(list_id, msg.get("name"))
    elif op == "add":
        made = playlists.add(list_id, tracks)
    elif op == "set":  # reorder or remove; paths already in the list stay allowed even if their file is gone
        made = playlists.set_tracks(list_id, tracks)
    elif op == "delete":
        playlists.delete(list_id)
        return {}
    else:
        raise ListError("Unknown change")
    return {**made, "key": key_of(made["id"])}


def start(event_queue, shared: Shared, library: Library, writer: MusicWriter, port: int, bind: str = "0.0.0.0", setup: Setup | None = None, playlists: Playlists | None = None, wifi=None):
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

        def _setup_visitor(self) -> bool:
            """A phone on the player's Wi-Fi setup network."""
            return wifi is not None and wifi.allows(self.client_address[0])

        def _guard(self, changes_state: bool) -> bool:
            if not _host_allowed(self.headers.get("Host", "")):
                self._fail(403, "Open this page by the player's own name or address")
                return False
            if changes_state and self.headers.get(HEADER) != HEADER_VALUE:
                self._fail(403, "Missing request header")
                return False
            return True

        def do_GET(self):
            url = urlsplit(self.path)
            if self._setup_visitor() and (url.path == "/" or not _host_allowed(self.headers.get("Host", ""))):
                # Phones check for internet by asking another site for a page; every name points here
                # on the setup network, so send them to the Wi-Fi page and they show it at once.
                self.send_response(302)
                self.send_header("Location", f"http://{wifi.address()}/wifi")
                self.send_header("Content-Length", "0")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            if not self._guard(False):
                return
            if url.path == "/wifi" and wifi is not None:
                self._send(200, WIFI_PAGE.read_bytes(), "text/html; charset=utf-8")
            elif url.path == "/api/wifi" and wifi is not None:
                self._json(200, wifi.page_state() if self._setup_visitor() else {"state": "closed", "networks": [], "message": ""})
            elif url.path == "/":
                self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            elif url.path == "/setup" and setup is not None:
                self._send(200, SETUP_PAGE.read_bytes(), "text/html; charset=utf-8")
            elif url.path == "/api/setup" and setup is not None:
                self._json(200, setup.state())
            elif url.path == "/api/inputs" and setup is not None and setup.inputs is not None:
                try:
                    after = int(parse_qs(url.query).get("after", ["0"])[0])
                except ValueError:
                    after = 0
                self._json(200, setup.inputs.since(after))
            elif url.path == "/api/state":
                state = dict(shared.snapshot)
                state["uploading"] = writer.busy
                try:
                    state["free_bytes"] = shutil.disk_usage(library.root).free
                except OSError:
                    state["free_bytes"] = None
                self._json(200, state)
            elif url.path == "/api/library":
                folder_lists = [a for a in library.lists if not a.is_playlist]
                self._json(200, [_item_info(a) for a in library.albums + library.artists + folder_lists + library.playlists])
            elif url.path == "/api/songs":
                self._json(200, [{**_track_info(t), "key": a.key, "index": i} for a in library.albums for i, t in enumerate(a.tracks)])
            elif url.path == "/api/item":
                item = library.get(parse_qs(url.query).get("key", [""])[0])
                if item is None:
                    self._fail(404, "No such album, artist or list")
                else:
                    self._json(200, {**_item_info(item), "items": [_track_info(t) for t in item.tracks]})
            elif url.path == "/api/files":
                try:
                    self._json(200, list_files(library, parse_qs(url.query).get("album", [""])[0]))
                except UploadError as e:
                    self._fail(e.status, str(e))
            elif url.path == "/api/cover":
                query = parse_qs(url.query)
                self._cover(query.get("album", [""])[0], query.get("track", [""])[0])
            else:
                self._fail(404, "Not found")

        def _cover(self, album_key: str, track_path: str) -> None:
            """The cover of one track, or of an album, artist or list (its first track's)."""
            album = library.get(album_key)
            track = library.track(track_path) or (album.tracks[0] if album and album.tracks else None)
            try:
                if track is None:
                    raise OSError
                source = library.art_source(track)
                key = f"{source}:{source.stat().st_mtime_ns}"
                if key not in covers:
                    from PIL import Image

                    data = library.art(track)
                    thumb = b""
                    if data:
                        img = Image.open(io.BytesIO(data)).convert("RGB")
                        img.thumbnail((400, 400))
                        buf = io.BytesIO()
                        img.save(buf, "JPEG", quality=82)
                        thumb = buf.getvalue()
                    if len(covers) > 200:
                        covers.clear()
                    covers[key] = thumb  # empty when there is no cover, so we do not look again
                if not covers[key]:
                    raise OSError
            except Exception:  # no such track, no cover, or not an image
                self._fail(404, "No cover")
                return
            self._send(200, covers[key], "image/jpeg", "max-age=300")

        def do_POST(self):
            if not self._guard(True):
                return
            path = urlsplit(self.path).path
            if path == "/api/wifi" and wifi is not None:
                self._wifi_join()
                return
            if path == "/api/delete":
                self._delete()
                return
            if path in ("/api/setup", "/api/restart", "/api/test") and setup is not None:
                self._setup(path)
                return
            if path == "/api/lists" and playlists is not None:
                self._lists()
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
                elif action == "seek":
                    value = float(value)
                    if value != value or value < 0:  # NaN or negative
                        raise ValueError
                elif action == "play_at":
                    if not isinstance(value, dict) or not isinstance(value.get("key"), str) or type(value.get("index")) is not int:
                        raise ValueError
                    value = {"key": value["key"], "index": value["index"]}
            except (ValueError, KeyError, TypeError):
                self._fail(400, "Bad command")
                return
            event_queue.put(ev.WebCommand(action, value))
            self._json(200, {"ok": True})

        def _body(self, limit: int = 4096) -> dict:
            length = int(self.headers.get("Content-Length", 0))
            if length > limit:
                raise ValueError
            msg = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(msg, dict):
                raise ValueError
            return msg

        def _setup(self, path: str) -> None:
            try:
                msg = self._body()
            except (ValueError, TypeError):
                self._fail(400, "Bad request")
                return
            if path == "/api/setup":
                try:
                    self._json(200, setup.save(msg))
                except ValueError as e:
                    self._fail(400, str(e))
                except OSError as e:
                    self._fail(500, f"Could not save the settings: {e}")
            elif path == "/api/restart":
                event_queue.put(ev.WebCommand("restart"))
                self._json(200, {"ok": True})
            elif msg.get("part") == "screen":
                event_queue.put(ev.WebCommand("test_screen"))
                self._json(200, {"ok": True, "message": "The test picture is on the player's screen for 5 seconds."})
            elif msg.get("part") == "dac":
                self._json(200, setup.test_dac())
            else:
                self._fail(400, "Unknown test")

        def _wifi_join(self) -> None:
            if not self._setup_visitor():
                self._fail(403, "Networks can only be chosen from a phone on the player's setup network, while it is open")
                return
            try:
                msg = self._body()
            except (ValueError, TypeError):
                self._fail(400, "Bad request")
                return
            from ..wifi import WifiError

            try:
                wifi.join(msg.get("ssid"), msg.get("password", ""))
            except WifiError as e:
                self._fail(400, str(e))
                return
            self._json(200, {"ok": True})

        def _lists(self) -> None:
            try:
                msg = self._body(LIST_BODY_LIMIT)
            except (ValueError, TypeError):
                self._fail(400, "Bad request")
                return
            try:
                made = change_list(playlists, library, msg)
            except ListError as e:
                self._fail(400, str(e))
                return
            except OSError as e:
                self._fail(500, f"Could not save the list: {e}")
                return
            event_queue.put(ev.ListsChanged())
            self._json(200, {"ok": True, "list": made})

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
