"""Web remote: path cleaning, the read-only/writable switch, and the HTTP API end to end."""

import json
import queue
import time
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

OK = {"X-Requested-With": "nfc-player"}
CARD = "04AA"


# ---- upload paths ----------------------------------------------------------


@pytest.mark.parametrize(
    "raw, cleaned",
    [
        ("Nina Simone/Pastel Blues/01 Be My Husband.flac", "Nina Simone/Pastel Blues/01 Be My Husband.flac"),
        ("/Album//cover.JPG", "Album/cover.JPG"),
        ("Album\\02 What: a title?.mp3", "Album/02 What_ a title_.mp3"),
        ("Album. /track.opus", "Album/track.opus"),
    ],
)
def test_paths_are_cleaned(raw, cleaned):
    assert web.safe_relative_path(raw).as_posix() == cleaned


@pytest.mark.parametrize(
    "raw, status",
    [
        ("../etc/passwd.flac", 400),
        ("Album/../../x.flac", 400),
        ("Album/.hidden.flac", 400),
        ("loose.flac", 400),  # must be inside a folder
        ("Album/notes.txt", 415),
        ("Album/run.sh", 415),
        ("a/b/c/d/e/f/g.flac", 400),
        ("", 400),
    ],
)
def test_bad_paths_are_refused(raw, status):
    with pytest.raises(web.UploadError) as e:
        web.safe_relative_path(raw)
    assert e.value.status == status


# ---- writer ----------------------------------------------------------------


def test_writer_opens_once_and_closes_after_uploads_settle():
    calls, changed = [], []
    w = web.MusicWriter(lambda: changed.append(1), idle_seconds=0.05)
    w._mount = calls.append
    w.begin()
    w.begin()
    assert calls == ["rw"] and w.busy
    w.end()
    time.sleep(0.12)
    assert calls == ["rw"] and not changed  # one upload still running
    w.end()
    w.begin()  # a new upload inside the grace period keeps it open
    w.end()
    assert calls == ["rw"]
    time.sleep(0.15)
    assert calls == ["rw", "ro"] and changed == [1] and not w.busy


# ---- HTTP API --------------------------------------------------------------


@pytest.fixture
def site(tmp_path):
    music = tmp_path / "music"
    build(music)
    library = Library(music)
    events = queue.Queue()
    shared = web.Shared()
    shared.snapshot = {"mode": "idle", "albums": len(library.albums)}
    writer = web.MusicWriter(lambda: events.put(ev.LibraryChanged()), idle_seconds=0.05)
    server = web.start(events, shared, library, writer, port=0, bind="127.0.0.1")
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def call(method, path, body=None, headers=None):
        req = urllib.request.Request(base + path, data=body, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.read(), r.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers

    yield call, events, shared, library, music
    server.shutdown()
    server.server_close()


def test_page_state_albums_and_cover(site):
    call, events, shared, library, music = site
    status, body, headers = call("GET", "/")
    assert status == 200 and b"NFC Player" in body
    status, body, _ = call("GET", "/api/state")
    state = json.loads(body)
    assert state["mode"] == "idle" and state["uploading"] is False and state["free_bytes"] > 0
    albums = json.loads(call("GET", "/api/albums")[1])
    assert len(albums) == 7 and {"path", "title", "artist", "tracks"} <= set(albums[0])
    status, body, headers = call("GET", "/api/cover?album=Ada%20Hollis/Paper%20Lanterns")
    assert status == 200 and headers["Content-Type"] == "image/jpeg" and body[:2] == b"\xff\xd8"
    assert call("GET", "/api/cover?album=nope")[0] == 404


def test_commands_become_events(site):
    call, events, *_ = site
    post = lambda msg, h=OK: call("POST", "/api/command", json.dumps(msg).encode(), h)[0]
    assert post({"action": "toggle"}) == 200
    assert post({"action": "volume", "value": "42"}) == 200
    assert post({"action": "play_album", "value": "Mika Tane/Small Hours"}) == 200
    assert [events.get_nowait() for _ in range(3)] == [
        ev.WebCommand("toggle"),
        ev.WebCommand("volume", 42),
        ev.WebCommand("play_album", "Mika Tane/Small Hours"),
    ]
    assert post({"action": "reboot"}) == 400
    assert post({"action": "volume", "value": "loud"}) == 400
    assert events.empty()


def test_other_sites_cannot_drive_it(site):
    call, events, *_ = site
    body = json.dumps({"action": "toggle"}).encode()
    assert call("POST", "/api/command", body)[0] == 403  # no custom header: a cross-site form post
    assert call("POST", "/api/command", body, {**OK, "Host": "evil.example.com"})[0] == 403  # DNS rebinding
    assert call("GET", "/api/state", headers={"Host": "evil.example.com"})[0] == 403
    assert call("PUT", "/api/upload?path=A/B/x.flac", b"data")[0] == 403
    assert call("GET", "/api/state", headers={"Host": "nfcplayer.local"})[0] == 200
    assert events.empty()


def test_upload_lands_and_library_is_told(site):
    call, events, shared, library, music = site
    data = b"fLaC" + bytes(300_000)
    status, body, _ = call("PUT", "/api/upload?path=New%20Artist/First%20LP/01%20Intro.flac", data, OK)
    assert status == 200 and json.loads(body)["path"] == "New Artist/First LP/01 Intro.flac"
    target = music / "New Artist" / "First LP" / "01 Intro.flac"
    assert target.read_bytes() == data
    assert not list(target.parent.glob(".*"))  # no leftover temp file
    assert events.get(timeout=2) == ev.LibraryChanged()
    library.rescan()
    assert library.get("New Artist/First LP").tracks[0].title == "Intro"


def test_upload_refusals(site):
    call, events, shared, library, music = site
    assert call("PUT", "/api/upload?path=../../escape.flac", b"x", OK)[0] == 400
    assert call("PUT", "/api/upload?path=Album/script.py", b"x", OK)[0] == 415
    shared.snapshot = {"mode": "transfer"}
    assert call("PUT", "/api/upload?path=A/B/x.flac", b"x", OK)[0] == 409
    assert not (music / "A").exists() and not (music.parent / "escape.flac").exists()
    assert events.empty()


# ---- app behaviour ---------------------------------------------------------


class Clock:
    t = 100.0

    def __call__(self):
        return self.t


@pytest.fixture
def rig(tmp_path):
    music = tmp_path / "music"
    build(music)
    clock = Clock()
    library = Library(music)
    store = Store(tmp_path / "state.json")
    playback = FakePlayback(library, clock)
    app = App(library, store, playback)

    def send(*events, advance=0.0):
        for e in events:
            app.handle(e, clock.t)
        clock.t += advance
        app.tick(clock.t)

    return app, send, clock, store, playback, library, music


def test_remote_play_without_a_card(rig):
    app, send, clock, store, playback, library, _ = rig
    send(ev.WebCommand("toggle"))  # nothing to toggle yet
    assert app.mode is Mode.IDLE
    send(ev.WebCommand("play_album", "Mika Tane/Small Hours"), advance=2.0)
    snap = app.snapshot()
    assert app.mode is Mode.PLAYING and snap["remote"] and not snap["card"]
    assert snap["album"]["title"] == "Small Hours" and snap["state"] == "play" and snap["elapsed"] == 2.0
    send(ev.WebCommand("next"))
    assert app.status.track_index == 1
    send(ev.WebCommand("toggle"))
    assert app.status.state == "pause"
    send(ev.Press("knob_long"))  # the card menu makes no sense here
    assert app.mode is Mode.PLAYING
    send(ev.WebCommand("volume", 150))
    assert store.volume == 100 and playback.volume == 100
    send(ev.WebCommand("play_album", "No/Such Album"))
    assert app.album.title == "Small Hours"
    json.dumps(app.snapshot())  # must be plain data


def test_remote_play_over_a_card_keeps_the_cards_place(rig):
    app, send, clock, store, playback, library, _ = rig
    store.link(CARD, "Ada Hollis/Low Tide Signals")
    send(ev.CardInserted(CARD))
    send(ev.Press("next"), advance=6.0)
    send(ev.WebCommand("play_album", "Mika Tane/Small Hours"), advance=9.0)
    assert app.remote and store.resume_point(CARD) == (1, pytest.approx(6.0, abs=0.01))
    send(ev.CardRemoved())  # removing the card still pauses, but must not overwrite its place
    assert app.mode is Mode.IDLE and playback.status().state == "pause"
    assert store.resume_point(CARD) == (1, pytest.approx(6.0, abs=0.01))
    send(ev.CardInserted(CARD))
    assert not app.remote and app.album.title == "Low Tide Signals" and app.status.track_index == 1


def test_card_takes_over_from_remote_play(rig):
    app, send, clock, store, *_ = rig
    store.link(CARD, "Ada Hollis/Paper Lanterns")
    send(ev.WebCommand("play_album", "Mika Tane/Small Hours"), advance=3.0)
    send(ev.CardInserted(CARD))
    assert not app.remote and app.album.title == "Paper Lanterns"


def test_library_change_is_picked_up_and_transfer_waits_for_uploads(rig):
    app, send, clock, store, playback, library, music = rig
    new = music / "Fresh" / "Album"
    new.mkdir(parents=True)
    (new / "01 Song.wav").write_bytes((music / "Mika Tane" / "Small Hours" / "01 0300.wav").read_bytes())
    send(ev.LibraryChanged())
    assert library.get("Fresh/Album") is not None and app.snapshot()["albums"] == 8
    app.is_uploading = lambda: True
    send(ev.UsbHost(True), ev.Press("knob"))
    assert app.mode is not Mode.TRANSFER and app.usb_offer
    app.is_uploading = lambda: False
    send(ev.Press("knob"))
    assert app.mode is Mode.TRANSFER
    send(ev.WebCommand("play_album", "Mika Tane/Small Hours"))  # ignored while the computer has the drive
    assert app.mode is Mode.TRANSFER and app.snapshot()["mode"] == "transfer"


def test_link_and_unlink_a_card_from_the_web(rig):
    app, send, clock, store, playback, library, _ = rig
    send(ev.WebCommand("link_card", "Mika Tane/Small Hours"))  # no card in the slot: nothing happens
    assert app.mode is Mode.IDLE and app.snapshot()["card_album"] is None
    send(ev.CardInserted(CARD))
    assert app.mode is Mode.LINKING and app.snapshot()["card"] and app.snapshot()["card_album"] is None
    send(ev.WebCommand("link_card", "No/Such Album"))
    assert store.album_for(CARD) is None
    send(ev.WebCommand("link_card", "Mika Tane/Small Hours"), advance=4.0)
    assert store.album_for(CARD) == "Mika Tane/Small Hours"
    assert app.mode is Mode.PLAYING and not app.remote and app.status.state == "play"
    assert app.snapshot()["card_album"] == {"path": "Mika Tane/Small Hours", "title": "Small Hours"}
    send(ev.CardRemoved(), ev.CardInserted(CARD))  # behaves like any linked card from now on
    assert app.status.elapsed == pytest.approx(4.0, abs=0.01)
    send(ev.WebCommand("unlink_card"))
    assert store.album_for(CARD) is None and app.mode is Mode.UNLINKED and playback.status().state == "stop"


def test_linking_the_album_already_playing_does_not_restart_it(rig):
    app, send, clock, store, playback, *_ = rig
    send(ev.CardInserted(CARD), ev.WebCommand("play_album", "Ada Hollis/Paper Lanterns"), advance=5.0)
    assert app.remote
    send(ev.WebCommand("link_card", "Ada Hollis/Paper Lanterns"))
    assert not app.remote and store.album_for(CARD) == "Ada Hollis/Paper Lanterns"
    assert app.status.elapsed == pytest.approx(5.0, abs=0.01)
    send(ev.WebCommand("play_album", "Mika Tane/Small Hours"), ev.WebCommand("unlink_card"))
    assert store.album_for(CARD) is None and app.album.title == "Small Hours" and app.status.state == "play"
