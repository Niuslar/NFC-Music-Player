"""Persistent state on the small data partition: card links, resume positions, volume.

Every save is atomic (write temp, fsync, rename) so a power cut never corrupts it.
"""

import json
import os
from pathlib import Path

DEFAULT_VOLUME = 30


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._cards: dict[str, dict] = {}
        self.volume = DEFAULT_VOLUME
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                self._cards = dict(data.get("cards", {}))
                self.volume = int(data.get("volume", DEFAULT_VOLUME))
            except (ValueError, OSError):
                pass  # unreadable file: start empty rather than refuse to boot

    def album_for(self, uid: str) -> str | None:
        """The library key the card is linked to: an album, an artist or a list."""
        card = self._cards.get(uid)
        return card["album"] if card else None

    def linked_keys(self) -> list[str]:
        """Everything some card is linked to, whether or not that card is in the slot."""
        return sorted({c["album"] for c in self._cards.values()})

    def link(self, uid: str, key: str) -> None:
        self._cards[uid] = {"album": key}  # the field keeps its old name so existing links still load
        self.save()

    def unlink(self, uid: str) -> None:
        if self._cards.pop(uid, None) is not None:
            self.save()

    def resume_point(self, uid: str) -> tuple[int, float]:
        r = self._cards.get(uid, {}).get("resume")
        return (int(r[0]), float(r[1])) if r else (0, 0.0)

    def set_resume(self, uid: str, track: int, elapsed: float) -> None:
        if uid in self._cards:
            self._cards[uid]["resume"] = [track, round(elapsed, 1)]

    def clear_resume(self, uid: str) -> None:
        if uid in self._cards:
            self._cards[uid].pop("resume", None)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump({"cards": self._cards, "volume": self.volume}, f, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)
