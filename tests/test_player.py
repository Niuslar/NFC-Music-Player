import json

import pytest

from player import events as ev
from player.app import App, Mode
from player.cards import Store
from player.demo_library import build
from player.knob import COUNTS_PER_REV, list_scaler, volume_scaler
from player.library import Library
from player.playback import FakePlayback

CARD, OTHER = "04AA", "04BB"


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


class Storage:
    def __init__(self):
        self.calls = []

    def release(self):
        self.calls.append("release")

    def reclaim(self):
        self.calls.append("reclaim")


@pytest.fixture(scope="session")
def music(tmp_path_factory):
    root = tmp_path_factory.mktemp("music")
    build(root)
    (root / "Ada Hollis" / "Paper Lanterns" / "._01 Lanterns.wav").write_bytes(b"junk")  # macOS debris
    return root


@pytest.fixture
def rig(music, tmp_path):
    clock = Clock()
    library = Library(music)
    store = Store(tmp_path / "state.json")
    playback = FakePlayback(library, clock)
    storage = Storage()
    app = App(library, store, playback, storage)

    def send(*events, advance=0.0):
        for e in events:
            app.handle(e, clock.t)
        clock.t += advance
        app.tick(clock.t)

    return app, send, clock, store, playback, storage, tmp_path / "state.json"


def linked(rig, album_index=0):
    """Insert CARD and link it to an album through the UI."""
    app, send, *_ = rig
    send(ev.CardInserted(CARD))
    per_item = round(COUNTS_PER_REV * 15 / 360) + 1
    for _ in range(album_index):
        send(ev.Rotate(per_item), advance=0.5)
    send(ev.Press("knob"))
    return app.library.albums[album_index]


# ---- library ---------------------------------------------------------------


def test_library_finds_albums_and_ignores_dotfiles(music):
    lib = Library(music)
    assert len(lib.albums) == 7
    lanterns = lib.get("Ada Hollis/Paper Lanterns")
    assert lanterns.artist == "Ada Hollis"
    assert [t.title for t in lanterns.tracks][0] == "Lanterns"
    assert len(lanterns.tracks) == 3
    assert lanterns.cover.name == "cover.jpg"
    assert lib.get("Loose Album Without Artist").artist == ""
    assert lib.duration(lanterns.tracks[0]) == pytest.approx(20, abs=0.1)


# ---- card store ------------------------------------------------------------


def test_store_round_trip_and_corrupt_file(tmp_path):
    path = tmp_path / "s.json"
    s = Store(path)
    s.link(CARD, "A/B")
    s.set_resume(CARD, 2, 41.26)
    s.volume = 55
    s.save()
    again = Store(path)
    assert again.album_for(CARD) == "A/B"
    assert again.resume_point(CARD) == (2, 41.3)
    assert again.volume == 55
    assert not path.with_suffix(".tmp").exists()
    path.write_text("{not json")
    assert Store(path).album_for(CARD) is None


# ---- knob ------------------------------------------------------------------


def test_slow_turn_gives_fine_steps_and_keeps_remainder():
    k = volume_scaler()
    t, steps = 0.0, 0
    for _ in range(COUNTS_PER_REV):  # one full slow revolution, one count at a time
        t += 0.05
        steps += k.feed(1, t)
    assert steps == 60


def test_fast_flick_is_accelerated():
    k = volume_scaler()
    t, steps = 0.0, 0
    for _ in range(8):  # a quarter turn in 0.1 s
        t += 0.0125
        steps += k.feed(8, t)
    assert 25 <= steps <= 45


def test_reversing_responds_immediately():
    k = list_scaler()
    assert k.feed(10, 0.0) == 0  # just short of one item
    assert k.feed(-11, 0.05) == -1


# ---- app -------------------------------------------------------------------


def test_unknown_card_links_then_plays(rig):
    app, send, clock, store, playback, *_ = rig
    send(ev.CardInserted(CARD))
    assert app.mode is Mode.LINKING
    album = linked(rig, album_index=2)
    assert app.mode is Mode.PLAYING
    assert store.album_for(CARD) == album.path
    assert app.status.state == "play" and app.status.title == album.tracks[0].title


def test_remove_pauses_and_reinsert_resumes_position(rig):
    app, send, clock, store, playback, _, state_file = rig
    album = linked(rig)
    send(ev.Press("next"), advance=7.0)
    send(ev.CardRemoved())
    assert app.mode is Mode.IDLE
    assert playback.status().state == "pause"
    assert json.loads(state_file.read_text())["cards"][CARD]["resume"] == [1, 7.0]
    clock.t += 3600
    send(ev.CardInserted(CARD))
    assert app.mode is Mode.PLAYING
    assert (app.status.track_index, app.status.state) == (1, "play")
    assert app.status.elapsed == pytest.approx(7.0, abs=0.01)


def test_swapping_cards_without_removal(rig):
    app, send, clock, store, *_ = rig
    first = linked(rig)
    store.link(OTHER, app.library.albums[3].path)
    send(ev.CardInserted(OTHER), advance=1.0)
    assert app.album == app.library.albums[3]
    assert store.resume_point(CARD) == (0, pytest.approx(0, abs=0.01))
    assert first != app.album


def test_play_pause_and_transport(rig):
    app, send, *_ = rig
    linked(rig)
    send(ev.Press("knob"))
    assert app.status.state == "pause"
    send(ev.Press("play"))
    assert app.status.state == "play"
    send(ev.Press("next"))
    assert app.status.track_index == 1
    send(ev.Press("prev"))  # under 3 s in: go back a track
    assert app.status.track_index == 0
    send(advance=5.0)
    send(ev.Press("prev"))  # over 3 s in: restart the track
    assert app.status.track_index == 0 and app.status.elapsed < 1


def test_album_end_clears_resume_and_can_replay(rig):
    app, send, clock, store, *_ = rig
    album = linked(rig)
    send(advance=10_000)
    assert app.status.state == "stop"
    send(ev.CardRemoved())
    assert store.resume_point(CARD) == (0, 0.0)
    send(ev.CardInserted(CARD))
    send(advance=10_000)
    send(ev.Press("knob"))
    assert app.status.state == "play" and app.status.track_index == 0


def test_volume_knob(rig):
    app, send, clock, store, playback, *_ = rig
    linked(rig)
    start = store.volume
    for _ in range(13):
        send(ev.Rotate(1), advance=0.05)
    assert store.volume == start + 3 and playback.volume == start + 3
    send(ev.Rotate(-100_000))
    assert store.volume == 0
    send(ev.CardRemoved())
    assert Store(rig[6]).volume == 0  # persisted when the card leaves


def test_menu_unlink_and_relink(rig):
    app, send, clock, store, playback, *_ = rig
    linked(rig)
    send(ev.Press("knob_long"))
    assert app.mode is Mode.MENU
    send(ev.Press("back"))
    assert app.mode is Mode.PLAYING
    send(ev.Press("knob_long"), ev.Rotate(11), ev.Press("knob"))  # "Unlink this card"
    assert app.mode is Mode.UNLINKED and store.album_for(CARD) is None
    assert playback.status().state == "stop"
    send(ev.Press("knob"))
    assert app.mode is Mode.LINKING
    send(ev.Press("back"))
    assert app.mode is Mode.UNLINKED


def test_relink_can_be_cancelled_without_interrupting(rig):
    app, send, *_ = rig
    album = linked(rig, album_index=1)
    send(ev.Press("knob_long"), ev.Press("knob"))  # "Link to another album"
    assert app.mode is Mode.LINKING and app.selected == 1
    send(ev.Press("back"))
    assert app.mode is Mode.PLAYING and app.album == album and app.status.state == "play"


def test_missing_album(rig):
    app, send, clock, store, *_ = rig
    store.link(CARD, "Gone/Album")
    send(ev.CardInserted(CARD))
    assert app.mode is Mode.UNLINKED and "missing" in app.note


def test_usb_offer_can_be_dismissed(rig):
    app, send, clock, store, playback, storage, _ = rig
    linked(rig)
    send(ev.UsbHost(True))
    assert app.usb_offer and app.status.state == "play"
    send(ev.Press("play"))  # ignored while the offer is up
    assert app.status.state == "play"
    send(ev.Press("back"))
    assert not app.usb_offer and storage.calls == []


def test_transfer_round_trip(rig):
    app, send, clock, store, playback, storage, _ = rig
    linked(rig)
    send(advance=4.0)
    send(ev.UsbHost(True), ev.Press("knob"))
    assert app.mode is Mode.TRANSFER and storage.calls == ["release"]
    assert playback.status().state == "stop"
    send(ev.Press("knob"), ev.Rotate(50), ev.CardRemoved(), ev.CardInserted(CARD))  # all inert
    assert app.mode is Mode.TRANSFER
    send(ev.UsbEjected())
    assert storage.calls == ["release", "reclaim"]
    assert app.mode is Mode.PLAYING and app.status.elapsed == pytest.approx(4.0, abs=0.01)
    send(ev.UsbHost(True), ev.Press("knob"), ev.CardRemoved(), ev.UsbHost(False))  # unplugged without eject
    assert app.mode is Mode.IDLE and storage.calls[-1] == "reclaim"


def test_every_screen_renders(rig):
    app, send, clock, *_ = rig
    seen = set()

    def shot():
        img = app.render(clock.t)
        assert img.size == (320, 240)
        seen.add(img.tobytes())

    shot()  # idle
    send(ev.CardInserted(CARD))
    shot()  # linking
    send(ev.Press("back"))
    shot()  # unlinked
    send(ev.Press("knob"), ev.Press("knob"))
    shot()  # now playing
    send(ev.Rotate(20))
    shot()  # volume overlay
    send(ev.Press("knob_long"))
    shot()  # menu
    send(ev.UsbHost(True))
    shot()  # usb offer
    send(ev.Press("knob"))
    shot()  # transfer
    assert len(seen) == 8


def test_transfer_can_be_ended_by_holding_the_knob(rig):
    app, send, clock, store, playback, storage, _ = rig
    linked(rig)
    send(ev.UsbHost(True), ev.Press("knob"))
    assert app.mode is Mode.TRANSFER
    send(ev.Press("knob_long"))
    assert app.mode is Mode.PLAYING and storage.calls == ["release", "reclaim"]


def test_failed_release_leaves_player_usable_and_error_is_shown(rig):
    app, send, clock, store, playback, storage, _ = rig
    linked(rig)

    def boom():
        raise OSError("USB release failed: busy")

    storage.release = boom
    app.handle(ev.UsbHost(True), clock.t)
    with pytest.raises(OSError):
        app.handle(ev.Press("knob"), clock.t)
    assert app.mode is Mode.IDLE and not app.usb_offer
    app.show_error("USB release failed: busy", clock.t)
    shown = app.render(clock.t).tobytes()
    assert shown != app.render(clock.t + 60).tobytes()  # error screen times out
    send(ev.CardRemoved(), ev.CardInserted(CARD))
    assert app.mode is Mode.PLAYING
