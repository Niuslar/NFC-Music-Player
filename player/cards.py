"""Persistent state on the small data partition: card links (each with its own choice of starting
from the beginning or where it stopped), resume positions, volume and its limit,
and whether Wi-Fi and the web remote are on.

Every save is atomic (write temp, fsync, rename) so a power cut never corrupts it.
"""

import json
import os
from pathlib import Path

DEFAULT_VOLUME = 30
VOLUME_LIMITS = (100, 90, 80, 70, 60, 50)  # 100 means no limit


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._cards: dict[str, dict] = {}
        self.volume = DEFAULT_VOLUME
        self.max_volume = 100
        self.web_remote = True
        self.wifi = True
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                self._cards = dict(data.get("cards", {}))
                self.volume = int(data.get("volume", DEFAULT_VOLUME))
                limit = data.get("max_volume", 100)
                self.max_volume = limit if limit in VOLUME_LIMITS else 100
                self.web_remote = data.get("web_remote", True) is not False
                self.wifi = data.get("wifi", True) is not False
            except (ValueError, OSError):
                pass  # unreadable file: start empty rather than refuse to boot

    def album_for(self, uid: str) -> str | None:
        """The library key the card is linked to: an album, an artist or a list."""
        card = self._cards.get(uid)
        return card["album"] if card else None

    def linked_keys(self) -> list[str]:
        """Everything some card is linked to, whether or not that card is in the slot."""
        return sorted({c["album"] for c in self._cards.values()})

    def link(self, uid: str, key: str, from_start: bool | None = None) -> None:
        """Links the card to key, forgetting its old place. from_start None keeps the card's current choice."""
        if from_start is None:
            from_start = self.from_start(uid)
        self._cards[uid] = {"album": key}  # the field keeps its old name so existing links still load
        if from_start:
            self._cards[uid]["from_start"] = True
        self.save()

    def from_start(self, uid: str) -> bool:
        """Whether the card always plays from the beginning; by default it carries on where it stopped."""
        return self._cards.get(uid, {}).get("from_start") is True

    def set_from_start(self, uid: str, on: bool) -> None:
        card = self._cards.get(uid)
        if card is None:
            return
        if on:
            card["from_start"] = True
        else:
            card.pop("from_start", None)
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
            json.dump({"cards": self._cards, "volume": self.volume, "max_volume": self.max_volume, "web_remote": self.web_remote, "wifi": self.wifi}, f, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)
