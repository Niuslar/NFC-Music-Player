"""The music library: every folder that directly contains audio files is an album.

Expected layout is Artist/Album/tracks, but a loose Album/ folder at the root works too.
"""

import re
import wave
from dataclasses import dataclass
from pathlib import Path

AUDIO_EXT = {".flac", ".mp3", ".m4a", ".ogg", ".opus", ".wav", ".aiff", ".aif"}
IMAGE_EXT = {".jpg", ".jpeg", ".png"}
COVER_STEMS = ("cover", "folder", "front")
UNKNOWN_DURATION = 180.0


@dataclass(frozen=True)
class Track:
    path: str  # relative to the music root, posix style
    title: str


@dataclass(frozen=True)
class Album:
    path: str  # relative to the music root, posix style; this is what a card links to
    artist: str
    title: str
    tracks: tuple[Track, ...]
    cover: Path | None


def _visible(p: Path) -> bool:
    # macOS litters exFAT volumes with ._AppleDouble and .DS_Store files.
    return not p.name.startswith(".")


def _track_title(stem: str) -> str:
    cleaned = re.sub(r"^\d+[\s.\-_]+", "", stem).strip()
    return cleaned or stem


def _find_cover(images: list[Path]) -> Path | None:
    for stem in COVER_STEMS:
        for img in images:
            if img.stem.lower() == stem:
                return img
    return images[0] if images else None


class Library:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.albums: list[Album] = []
        self._by_path: dict[str, Album] = {}
        self.rescan()

    def rescan(self) -> None:
        albums = []
        if self.root.is_dir():
            dirs = [self.root] + sorted(d for d in self.root.rglob("*") if d.is_dir() and _visible(d))
            for d in dirs:
                files = sorted((f for f in d.iterdir() if f.is_file() and _visible(f)), key=lambda f: f.name.lower())
                audio = [f for f in files if f.suffix.lower() in AUDIO_EXT]
                if not audio or d == self.root:
                    continue
                images = [f for f in files if f.suffix.lower() in IMAGE_EXT]
                rel = d.relative_to(self.root)
                albums.append(
                    Album(
                        path=rel.as_posix(),
                        artist=rel.parent.name,
                        title=d.name,
                        tracks=tuple(
                            Track(f.relative_to(self.root).as_posix(), _track_title(f.stem)) for f in audio
                        ),
                        cover=_find_cover(images),
                    )
                )
        albums.sort(key=lambda a: (a.artist.lower(), a.title.lower()))
        self.albums = albums
        self._by_path = {a.path: a for a in albums}

    def get(self, path: str) -> Album | None:
        return self._by_path.get(path)

    def duration(self, track: Track) -> float:
        """Track length in seconds. Only the fake player needs this; MPD reports its own."""
        full = self.root / track.path
        try:
            if full.suffix.lower() == ".wav":
                with wave.open(str(full)) as w:
                    return w.getnframes() / w.getframerate()
            import mutagen  # optional

            info = mutagen.File(full)
            return float(info.info.length) if info else UNKNOWN_DURATION
        except Exception:
            return UNKNOWN_DURATION
