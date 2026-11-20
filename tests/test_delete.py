"""Deleting music from the web remote."""

import json
import queue
import urllib.error
import urllib.request

import pytest

from player import events as ev
from player.app import App, Mode
from player.cards import Store
from player.demo_library import build
from player.library import Library
from player.playback import FakePlayback
from player.web import server as web

OK = {"X-Requested-With": "nfc-player", "Content-Type": "application/json"}
CARD = "04AA"
LANTERNS = "Ada Hollis/Paper Lanterns"


class Writer:
    """Stands in for MusicWriter and records that writes were bracketed properly."""

    def __init__(self):
        self.open = 0
        self.sessions = 0

    def begin(self):
        self.open += 1
        self.sessions += 1

    def end(self):
        self.open -= 1


@pytest.fixture
def lib(tmp_path):
    music = tmp_path / "music"
    build(music)
    return Library(music), music


def test_list_files_shows_tracks_and_cover_but_not_hidden_files(lib):
    library, music = lib
    (music / LANTERNS / ".DS_Store").write_bytes(b"x")
    files = web.list_files(library, LANTERNS)
    assert [f["name"] for f in files][0] == "01 Lanterns.wav"
    assert {f["name"]: f["track"] for f in files}["cover.jpg"] is False
    assert len(files) == 4 and all(f["size"] > 0 for f in files)
    with pytest.raises(web.UploadError):
        web.list_files(library, "Nope/Nothing")


def test_delete_one_track_keeps_the_album(lib):
    library, music = lib
    w = Writer()
    assert web.delete_music(library, w, LANTERNS, "02 Kite String.wav") == 1
    assert not (music / LANTERNS / "02 Kite String.wav").exists()
    assert (music / LANTERNS / "cover.jpg").exists()
    assert w.open == 0 and w.sessions == 1
    library.rescan()
    assert len(library.get(LANTERNS).tracks) == 2


def test_delete_whole_album_removes_folder_but_not_the_artists_other_albums(lib):
    library, music = lib
    (music / LANTERNS / "._01 Lanterns.wav").write_bytes(b"x")  # macOS debris goes too
    assert web.delete_music(library, Writer(), LANTERNS) == 5
    assert not (music / LANTERNS).exists()
    assert (music / "Ada Hollis" / "Low Tide Signals").is_dir()
    library.rescan()
    assert library.get(LANTERNS) is None and len(library.albums) == 6


def test_deleting_an_artists_only_album_removes_the_artist_folder_too(lib):
    library, music = lib
    web.delete_music(library, Writer(), "Mika Tane/Small Hours")
    assert not (music / "Mika Tane").exists() and music.is_dir()


def test_deleting_the_last_track_removes_the_cover_and_folder(lib):
    library, music = lib
    album = "Loose Album Without Artist"
    web.delete_music(library, Writer(), album, "01 One.wav")
    assert (music / album).is_dir()
    assert web.delete_music(library, Writer(), album, "02 Two.wav") == 2  # the track and the orphaned cover
    assert not (music / album).exists()


@pytest.mark.parametrize(
    "album, name",
    [
        ("Nope/Nothing", None),
        ("../outside", None),
        ("", None),
        (LANTERNS, "../Low Tide Signals/01 Harbour Lights.wav"),
        (LANTERNS, "/etc/hosts"),
        (LANTERNS, ".DS_Store"),
        (LANTERNS, "missing.wav"),
        (LANTERNS, ""),
    ],
)
def test_delete_refuses_anything_outside_a_known_album(lib, album, name):
    library, music = lib
    outside = music.parent / "outside"
    outside.mkdir()
    (outside / "keep.wav").write_bytes(b"x")
    (music / LANTERNS / ".DS_Store").write_bytes(b"x")
    before = sorted(str(p) for p in music.parent.rglob("*"))
    w = Writer()
    with pytest.raises(web.UploadError):
        web.delete_music(library, w, album, name)
    assert sorted(str(p) for p in music.parent.rglob("*")) == before
    assert w.sessions == 0


def test_delete_never_follows_a_symlink_out_of_the_album(lib):
    library, music = lib
    secret = music.parent / "secret.wav"
    secret.write_bytes(b"x")
    (music / LANTERNS / "link.wav").symlink_to(secret)
    with pytest.raises(web.UploadError):
        web.delete_music(library, Writer(), LANTERNS, "link.wav")
    web.delete_music(library, Writer(), LANTERNS)  # whole album: the link is removed, not its target
    assert secret.exists() and not (music / LANTERNS).exists()


def _two_discs(music):
    album = music / "Test Artist" / "Double"
    for disc in ("CD1", "CD2"):
        (album / disc).mkdir(parents=True)
        for name in ("01 a.wav", "02 b.wav"):
            (album / disc / name).write_bytes(b"x")
    (album / "cover.jpg").write_bytes(b"x")
    return "Test Artist/Double"


def test_disc_folders_make_one_album_with_numbered_discs(lib):
    library, music = lib
    key = _two_discs(music)
    library.rescan()
    double = library.get(key)
    assert double.kind == "album" and double.title == "Double" and double.artist == "Test Artist"
    assert [(t.disc, t.path.split("/", 2)[2]) for t in double.tracks] == [
        (1, "CD1/01 a.wav"), (1, "CD1/02 b.wav"), (2, "CD2/01 a.wav"), (2, "CD2/02 b.wav")
    ]
    assert double.cover == music / key / "cover.jpg"
    assert library.get(key + "/CD1") is None and not library.lists


def test_disc_album_files_can_be_listed_and_deleted(lib):
    library, music = lib
    key = _two_discs(music)
    library.rescan()
    assert [f["name"] for f in web.list_files(library, key)] == [
        "cover.jpg", "CD1/01 a.wav", "CD1/02 b.wav", "CD2/01 a.wav", "CD2/02 b.wav"
    ]
    for bad in ("CD3/01 a.wav", "../Double/CD1/01 a.wav", "CD1/../CD2/01 a.wav", "CD1/x/01 a.wav"):
        with pytest.raises(web.UploadError):
            web.delete_music(library, Writer(), key, bad)
    assert web.delete_music(library, Writer(), key, "CD2/01 a.wav") == 1
    assert not (music / key / "CD2" / "01 a.wav").exists() and (music / key / "CD1" / "01 a.wav").exists()
    assert web.delete_music(library, Writer(), key) == 4  # three tracks and the cover
    assert not (music / "Test Artist").exists()


# ---- over HTTP ---------------------------------------------------------------


@pytest.fixture
def site(lib):
    library, music = lib
    events = queue.Queue()
    shared = web.Shared()
    shared.snapshot = {"mode": "idle"}
    writer = web.MusicWriter(lambda: events.put(ev.LibraryChanged()), idle_seconds=0.05)
    server = web.start(events, shared, library, writer, port=0, bind="127.0.0.1")
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def call(method, path, data=None, headers=None):
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(base + path, data=body, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    yield call, events, shared, music
    server.shutdown()
    server.server_close()


def test_delete_over_http(site):
    call, events, shared, music = site
    status, files = call("GET", "/api/files?album=Ada%20Hollis/Paper%20Lanterns")
    assert status == 200 and len(files) == 4
    assert call("POST", "/api/delete", {"album": LANTERNS, "file": "01 Lanterns.wav"})[0] == 403  # no header
    assert (music / LANTERNS / "01 Lanterns.wav").exists()
    assert call("POST", "/api/delete", {"album": LANTERNS, "file": "01 Lanterns.wav"}, OK) == (200, {"ok": True, "removed": 1})
    assert events.get(timeout=2) == ev.LibraryChanged()
    assert call("POST", "/api/delete", {"album": LANTERNS, "file": "01 Lanterns.wav"}, OK)[0] == 404
    assert call("POST", "/api/delete", {"file": "x"}, OK)[0] == 400
    shared.snapshot = {"mode": "transfer"}
    assert call("POST", "/api/delete", {"album": LANTERNS}, OK)[0] == 409
    assert (music / LANTERNS).is_dir()
    shared.snapshot = {"mode": "idle"}
    assert call("POST", "/api/delete", {"album": LANTERNS}, OK)[0] == 200
    assert not (music / LANTERNS).exists()
    assert call("GET", "/api/files?album=Ada%20Hollis/Paper%20Lanterns")[0] == 404


# ---- what the player does when its album disappears ------------------------------


class Clock:
    t = 100.0

    def __call__(self):
        return self.t


@pytest.fixture
def rig(lib):
    library, music = lib
    clock = Clock()
    store = Store(music.parent / "state.json")
    playback = FakePlayback(library, clock)
    app = App(library, store, playback)

    def send(*events, advance=0.0):
        for e in events:
            app.handle(e, clock.t)
        clock.t += advance
        app.tick(clock.t)

    return app, send, store, playback, library


def test_deleting_the_album_playing_from_the_page_stops_it(rig):
    app, send, store, playback, library = rig
    send(ev.WebCommand("play_album", LANTERNS), advance=2.0)
    web.delete_music(library, Writer(), LANTERNS)
    send(ev.LibraryChanged())
    assert app.mode is Mode.IDLE and app.album is None and playback.status().state == "stop"
    assert app.snapshot()["album"] is None


def test_deleting_a_cards_album_leaves_the_card_marked_missing(rig):
    app, send, store, playback, library = rig
    store.link(CARD, LANTERNS)
    send(ev.CardInserted(CARD), advance=2.0)
    web.delete_music(library, Writer(), LANTERNS)
    send(ev.LibraryChanged())
    assert app.mode is Mode.UNLINKED and "missing" in app.note and playback.status().state == "stop"
    assert app.snapshot()["card_album"] == {"key": LANTERNS, "title": None, "kind": None}
    send(ev.WebCommand("link_card", "Mika Tane/Small Hours"))  # and it can be given a new album
    assert app.mode is Mode.PLAYING and store.album_for(CARD) == "Mika Tane/Small Hours"


def test_deleting_one_track_keeps_the_album_playing(rig):
    app, send, store, playback, library = rig
    send(ev.WebCommand("play_album", LANTERNS), advance=2.0)
    web.delete_music(library, Writer(), LANTERNS, "03 An Unreasonably Long Song Title For Testing Wrapping.wav")
    send(ev.LibraryChanged())
    assert app.mode is Mode.PLAYING and len(app.album.tracks) == 2 and app.status.state == "play"
