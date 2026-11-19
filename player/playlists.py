"""Lists made on the web remote: a name and an ordered set of tracks from anywhere in the library.

They live on the data partition next to the card links, not on the music drive, so making
one never needs the drive to be writable and never copies a file. Each list keeps its tracks
as paths; a track whose file is gone is skipped when the list plays, and comes back if the
file does. A card linked to a list keeps working when the list is renamed or reordered.

The web remote's threads change lists; the main loop reads them. Every method takes the lock
and every save is atomic, like the card store.
"""

import json
import os
import secrets
import threading
from pathlib import Path

MAX_NAME = 120
MAX_TRACKS = 5000
MAX_LISTS = 500
KEY_PREFIX = "//list//"


class ListError(ValueError):
    """A request that cannot be done; the message is shown on the web page."""


def key_of(list_id: str) -> str:
    return KEY_PREFIX + list_id


def _clean_name(name) -> str:
    name = " ".join(str(name or "").split())
    if not name:
        raise ListError("A list needs a name")
    if len(name) > MAX_NAME:
        raise ListError(f"Names can be at most {MAX_NAME} characters")
    return name


def _clean_tracks(tracks) -> list[str]:
    if not isinstance(tracks, list) or not all(isinstance(t, str) and t for t in tracks):
        raise ListError("Tracks must be a list of track paths")
    if len(tracks) > MAX_TRACKS:
        raise ListError(f"A list can hold at most {MAX_TRACKS} tracks")
    return list(tracks)


class Playlists:
    def __init__(self, path: Path | None):
        self.path = Path(path) if path is not None else None  # None keeps lists in memory only (tests)
        self._lock = threading.Lock()
        self._lists: list[dict] = []
        if self.path is not None and self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                for raw in data.get("lists", []):
                    self._lists.append({"id": str(raw["id"]), "name": _clean_name(raw["name"]), "tracks": _clean_tracks(raw.get("tracks", []))})
            except (ValueError, KeyError, TypeError, OSError):
                pass  # unreadable file: start empty rather than refuse to boot

    def all(self) -> list[dict]:
        """A copy of every list: [{id, name, tracks}]."""
        with self._lock:
            return [{**p, "tracks": list(p["tracks"])} for p in self._lists]

    def _find(self, list_id) -> dict:
        for p in self._lists:
            if p["id"] == list_id:
                return p
        raise ListError("No such list")

    def create(self, name, tracks=None) -> dict:
        name, tracks = _clean_name(name), _clean_tracks([] if tracks is None else tracks)
        with self._lock:
            if len(self._lists) >= MAX_LISTS:
                raise ListError(f"There can be at most {MAX_LISTS} lists")
            made = {"id": secrets.token_hex(4), "name": name, "tracks": tracks}
            self._lists.append(made)
            self._save()
            return {**made, "tracks": list(tracks)}

    def rename(self, list_id, name) -> dict:
        name = _clean_name(name)
        with self._lock:
            p = self._find(list_id)
            p["name"] = name
            self._save()
            return {**p, "tracks": list(p["tracks"])}

    def set_tracks(self, list_id, tracks) -> dict:
        tracks = _clean_tracks(tracks)
        with self._lock:
            p = self._find(list_id)
            p["tracks"] = tracks
            self._save()
            return {**p, "tracks": list(tracks)}

    def add(self, list_id, tracks) -> dict:
        tracks = _clean_tracks(tracks)
        with self._lock:
            p = self._find(list_id)
            if len(p["tracks"]) + len(tracks) > MAX_TRACKS:
                raise ListError(f"A list can hold at most {MAX_TRACKS} tracks")
            p["tracks"] += tracks
            self._save()
            return {**p, "tracks": list(p["tracks"])}

    def delete(self, list_id) -> None:
        with self._lock:
            self._lists.remove(self._find(list_id))
            self._save()

    def _save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump({"lists": self._lists}, f, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)
