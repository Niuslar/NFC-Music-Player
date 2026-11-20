"""The music library: albums, artists and lists, any of which a card can link to.

Albums come from the files' tags, so a flat folder of mixed songs splits into its
real albums. Files without tags fall back to the folder layout: the folder is the
album and its parent is the artist (Artist/Album/tracks, or a loose Album/ at the root).

An album split into disc folders (Album/CD1, Album/CD2, or Disc 1, Disc 2) is one
album: its discs play in order and the web remote shows a heading for each.

A list is a folder whose tracks span more than one album, played as it is in
filename order, or a list made on the web remote (see playlists.py). An artist is
every album by that artist, one after another.
"""

import re
import wave
from dataclasses import dataclass, replace
from pathlib import Path

from .playlists import KEY_PREFIX as PLAYLIST_PREFIX

AUDIO_EXT = {".flac", ".mp3", ".m4a", ".ogg", ".opus", ".wav", ".aiff", ".aif"}
IMAGE_EXT = {".jpg", ".jpeg", ".png"}
COVER_STEMS = ("cover", "folder", "front")
UNKNOWN_DURATION = 180.0
VARIOUS = "Various Artists"
KINDS = ("album", "artist", "list")
DISC_DIR = re.compile(r"^(?:cd|dis[ck])[\s._-]*(\d{1,3})$", re.I)  # CD1, CD 2, Disc 3, disk_4
DISC_SUFFIX = re.compile(r"[\s,:_-]*[(\[]?\s*(?:cd|dis[ck])[\s._-]*\d{1,3}\s*[)\]]?$", re.I)  # "Album (Disc 2)"


@dataclass(frozen=True)
class Tags:
    """What a file says about itself. Empty or zero means the tag is missing."""

    title: str = ""
    artist: str = ""
    album: str = ""
    albumartist: str = ""
    track: int = 0
    disc: int = 0
    year: int = 0


@dataclass(frozen=True)
class Track:
    path: str  # relative to the music root, posix style
    title: str
    artist: str = ""  # the track's own artist, when tagged
    album: str = ""  # title of the album it belongs to
    cover: Path | None = None  # image file in its folder, when that folder is a single album
    disc: int = 0  # disc number, from its disc folder (CD2) or its tags; 0 when unknown


@dataclass(frozen=True)
class Item:
    """Something a card can link to. key is what the card stores.

    An album alone in its folder, and a list, use the folder's path as their key, so
    a card keeps working when a folder grows from one album into several or back.
    """

    kind: str  # album | artist | list
    key: str
    title: str
    artist: str
    tracks: tuple[Track, ...]
    folder: str | None = None  # where its files live; None for an artist
    whole_folder: bool = False  # it owns every file in that folder
    albums: int = 1  # how many albums it spans
    discs: tuple[str, ...] = ()  # disc folders inside folder (CD1, CD2...) that also hold its files

    @property
    def cover(self) -> Path | None:
        return self.tracks[0].cover if self.tracks else None

    @property
    def is_playlist(self) -> bool:
        """Made on the web remote rather than found as a folder: it can be edited there."""
        return self.key.startswith(PLAYLIST_PREFIX)


def _visible(p: Path) -> bool:
    # macOS litters exFAT volumes with ._AppleDouble and .DS_Store files.
    return not p.name.startswith(".")


def _track_title(stem: str) -> str:
    cleaned = re.sub(r"^\d+[\s.\-_]+", "", stem).strip()
    return cleaned or stem


def disc_number(name: str) -> int:
    """The disc a folder holds, from a name like CD2 or Disc 2; 0 for any other folder."""
    m = DISC_DIR.match(name.strip())
    return int(m.group(1)) if m else 0


def _find_cover(images: list[Path]) -> Path | None:
    for stem in COVER_STEMS:
        for img in images:
            if img.stem.lower() == stem:
                return img
    return images[0] if images else None


def _first(value) -> str:
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    return str(value or "").strip()


def _number(value) -> int:
    m = re.match(r"\d+", _first(value))  # "3/12" and "2019-05-01" both start with the number wanted
    return int(m.group()) if m else 0


def make_tags(raw: dict) -> Tags:
    """Builds Tags from a mapping with MPD-style or mutagen-style names."""
    return Tags(
        title=_first(raw.get("title")),
        artist=_first(raw.get("artist")),
        album=_first(raw.get("album")),
        albumartist=_first(raw.get("albumartist")),
        track=_number(raw.get("track") or raw.get("tracknumber")),
        disc=_number(raw.get("disc") or raw.get("discnumber")),
        year=_number(raw.get("date") or raw.get("originaldate")),
    )


class FileTags:
    """Reads tags and embedded covers straight from the files, for when MPD is absent.

    Needs the optional mutagen package; without it every file counts as untagged.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self._seen: dict[str, tuple[tuple, Tags]] = {}  # path -> (size and mtime, tags)

    def tags(self) -> dict[str, Tags]:
        try:
            import mutagen
        except ImportError:
            return {}
        found: dict[str, tuple[tuple, Tags]] = {}
        if self.root.is_dir():
            for f in self.root.rglob("*"):
                if f.suffix.lower() not in AUDIO_EXT or not _visible(f):
                    continue
                rel = f.relative_to(self.root).as_posix()
                try:
                    st = f.stat()
                    stamp = (st.st_size, st.st_mtime_ns)
                    old = self._seen.get(rel)
                    if old and old[0] == stamp:
                        found[rel] = old
                        continue
                    info = mutagen.File(f, easy=True)
                    found[rel] = (stamp, make_tags(dict(info.tags or {})) if info else Tags())
                except Exception:
                    continue  # unreadable file: treat as untagged
        self._seen = found
        return {rel: tags for rel, (_, tags) in found.items()}

    def art(self, path: str) -> bytes | None:
        try:
            import mutagen

            info = mutagen.File(self.root / path)
            if info is None:
                return None
            pictures = getattr(info, "pictures", None)  # FLAC
            if pictures:
                return bytes(pictures[0].data)
            tags = info.tags or {}
            if "covr" in tags and tags["covr"]:  # MP4
                return bytes(tags["covr"][0])
            for name in tags.keys():  # ID3
                if str(name).startswith("APIC"):
                    return bytes(tags[name].data)
        except Exception:
            pass
        return None


class Library:
    """tags() returns {track path: Tags}; art(track path) returns an embedded cover's bytes;
    playlists() returns the lists made on the web remote, [{id, name, tracks}]."""

    def __init__(self, root: Path, tags=None, art=None, playlists=None):
        self.root = Path(root)
        self._read_tags, self._read_art, self._read_playlists = tags, art, playlists
        self.albums: list[Item] = []
        self.artists: list[Item] = []
        self.lists: list[Item] = []  # what a card can link to: folder lists and made lists with tracks
        self.playlists: list[Item] = []  # every made list, empty ones too
        self._folder_lists: list[Item] = []
        self.version = 0  # goes up with every rescan
        self._by_key: dict[str, Item] = {}
        self._tracks: dict[str, Track] = {}
        self._album_of: dict[str, str] = {}
        self._folder_cover: dict[str, Path] = {}
        self.rescan()

    def rescan(self) -> None:
        tags = self._read_tags() if self._read_tags else {}
        albums: list[Item] = []
        lists: list[Item] = []
        years: dict[str, int] = {}
        keys: set[str] = set()
        folder_cover: dict[str, Path] = {}
        if self.root.is_dir():
            # Gather each album folder's audio. A disc folder (CD1, Disc 2) adds its files to its parent.
            homes: dict[Path, dict] = {}
            dirs = sorted(d for d in self.root.rglob("*") if d.is_dir() and _visible(d))
            for d in dirs:
                files = sorted((f for f in d.iterdir() if f.is_file() and _visible(f)), key=lambda f: f.name.lower())
                audio = [f for f in files if f.suffix.lower() in AUDIO_EXT]
                image = _find_cover([f for f in files if f.suffix.lower() in IMAGE_EXT])
                if image and audio:
                    folder_cover[d.relative_to(self.root).as_posix()] = image
                disc = disc_number(d.name) if d.parent != self.root else 0
                home = homes.setdefault(d.parent if disc else d, {"audio": [], "image": None, "discs": []})
                if not disc and image:
                    home["image"] = image  # the album folder's own cover comes first
                if audio:
                    home["audio"] += [(f, disc) for f in audio]
                    if disc:
                        home["discs"].append(d.name)
                        if home["image"] is None:
                            home["image"] = image

            for d, home in homes.items():
                audio = sorted(home["audio"], key=lambda m: (m[1], m[0].name.lower()))
                if not audio:
                    continue
                image = home["image"]
                rel = d.relative_to(self.root)
                folder = rel.as_posix()
                discs = tuple(sorted(home["discs"], key=lambda n: (disc_number(n), n.lower())))
                if image:  # a disc folder without its own picture shows the album's
                    for name in discs:
                        folder_cover.setdefault(f"{folder}/{name}", image)

                groups: dict[tuple, list[tuple[Path, Tags, int]]] = {}
                for f, disc in audio:
                    t = tags.get(f.relative_to(self.root).as_posix()) or Tags()
                    if disc and t.album:  # "Album (Disc 2)" in a disc folder belongs with "Album (Disc 1)"
                        t = replace(t, album=DISC_SUFFIX.sub("", t.album).strip() or t.album)
                    ident = (t.album.casefold(), t.albumartist.casefold()) if t.album else ()
                    groups.setdefault(ident, []).append((f, t, disc or t.disc))
                alone = len(groups) == 1

                made: dict[str, Track] = {}
                for ident, members in groups.items():
                    title = members[0][1].album or d.name
                    artists = {t.artist for _, t, _ in members if t.artist}
                    artist = (
                        members[0][1].albumartist
                        or (artists.pop() if len(artists) == 1 else VARIOUS if artists else rel.parent.name)
                    )
                    if ident:  # tagged: disc and track number decide the order
                        members.sort(key=lambda m: (m[2], m[1].track or 10**6, m[0].name.lower()))
                    tracks = tuple(
                        Track(
                            path=f.relative_to(self.root).as_posix(),
                            title=t.title or _track_title(f.stem),
                            artist=t.artist,
                            album=title,
                            cover=image if alone else None,
                            disc=disc,
                        )
                        for f, t, disc in members
                    )
                    made.update((t.path, t) for t in tracks)
                    key = folder if alone else f"{folder}//{artist}//{title}"
                    while key in keys:
                        key += " (2)"
                    keys.add(key)
                    album_discs = tuple(n for n in discs if any(t.path.startswith(f"{folder}/{n}/") for t in tracks))
                    albums.append(
                        Item("album", key, title, artist, tracks, folder=folder, whole_folder=alone, discs=album_discs)
                    )
                    years[key] = min((t.year for _, t, _ in members if t.year), default=0)
                if not alone:
                    in_order = tuple(made[f.relative_to(self.root).as_posix()] for f, _ in audio)
                    lists.append(
                        Item(
                            "list", folder, d.name, rel.parent.name, in_order, folder,
                            whole_folder=True, albums=len(groups), discs=discs,
                        )
                    )

        albums.sort(key=lambda a: (a.title.casefold(), a.artist.casefold()))  # alphabetical, as the screen lists them
        lists.sort(key=lambda a: a.title.lower())
        by_artist: dict[str, list[Item]] = {}
        for a in albums:
            if a.artist:
                by_artist.setdefault(a.artist.casefold(), []).append(a)
        artists = []
        for name, theirs in by_artist.items():
            theirs.sort(key=lambda a: (years[a.key] or 9999, a.title.lower()))
            tracks = tuple(t for a in theirs for t in a.tracks)
            artists.append(Item("artist", f"//artist//{name}", theirs[0].artist, "", tracks, albums=len(theirs)))
        artists.sort(key=lambda a: a.title.lower())

        self.albums, self.artists, self._folder_lists = albums, artists, lists
        self._tracks = {t.path: t for a in albums for t in a.tracks}
        self._album_of = {t.path: a.key for a in albums for t in a.tracks}
        self._folder_cover = folder_cover
        self.refresh_playlists()

    def refresh_playlists(self) -> None:
        """Rebuilds the made lists from their tracks, without reading the music drive again."""
        made = []
        for raw in self._read_playlists() if self._read_playlists else []:
            tracks = tuple(self._tracks[p] for p in raw["tracks"] if p in self._tracks)  # gone files are skipped
            albums = len({self._album_of.get(t.path) for t in tracks})
            made.append(Item("list", PLAYLIST_PREFIX + raw["id"], raw["name"], "", tracks, albums=albums))
        lists = sorted(self._folder_lists + [p for p in made if p.tracks], key=lambda a: a.title.lower())
        self.lists, self.playlists = lists, made
        self._by_key = {i.key: i for i in self.albums + self.artists + self._folder_lists + made}
        self.version += 1

    def of(self, kind: str) -> list[Item]:
        return {"album": self.albums, "artist": self.artists, "list": self.lists}[kind]

    def get(self, key: str) -> Item | None:
        return self._by_key.get(key)

    def track(self, path: str) -> Track | None:
        return self._tracks.get(path)

    def album_of(self, path: str) -> Item | None:
        """The album a track belongs to."""
        key = self._album_of.get(path)
        return self._by_key.get(key) if key else None

    def albums_by(self, artist: Item) -> list[Item]:
        """Every album an artist item is made of."""
        return [a for a in self.albums if a.artist.casefold() == artist.title.casefold()]

    def art_source(self, track: Track) -> Path:
        """The file a track's cover comes from first: its folder's image, or the track itself."""
        return track.cover or self.root / track.path

    def art(self, track: Track) -> bytes | None:
        """Cover image bytes for a track: its album's image file, else the art embedded in it."""
        try:
            if track.cover is not None:
                return track.cover.read_bytes()
            data = self._read_art(track.path) if self._read_art else None
            if data:
                return data
            shared = self._folder_cover.get(Path(track.path).parent.as_posix())
            return shared.read_bytes() if shared else None
        except Exception:
            return None  # a missing cover must never stop playback or drawing

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
