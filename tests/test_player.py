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


PER_ITEM = round(COUNTS_PER_REV * 15 / 360) + 1  # knob counts that move a list by one row


def linked(rig, album_index=0, from_start=False):
    """Insert CARD and link it to an album through the UI."""
    app, send, *_ = rig
    send(ev.CardInserted(CARD), ev.Press("knob"))  # the first screen asks what kind; Album is first
    for _ in range(album_index):
        send(ev.Rotate(PER_ITEM), advance=0.5)
    send(ev.Press("knob"))
    assert app.mode is Mode.LINK_START and app.selected == 0  # carry on where it stopped comes first
    if from_start:
        send(ev.Rotate(PER_ITEM), advance=0.5)
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
    assert store.album_for(CARD) == album.key
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
    store.link(OTHER, app.library.albums[3].key)
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
    send(ev.Press("knob_long"), ev.Rotate(PER_ITEM), advance=0.5)
    send(ev.Rotate(PER_ITEM), ev.Press("knob"))  # "Unlink this card"
    assert app.mode is Mode.UNLINKED and store.album_for(CARD) is None
    assert playback.status().state == "stop"
    send(ev.Press("knob"))
    assert app.mode is Mode.LINKING
    send(ev.Press("back"))
    assert app.mode is Mode.UNLINKED


def test_relink_can_be_cancelled_without_interrupting(rig):
    app, send, *_ = rig
    album = linked(rig, album_index=1)
    send(ev.Press("knob_long"), ev.Press("knob"))  # "Link to something else"
    assert app.mode is Mode.LINKING and app.link_kind is None and app.selected == 0  # on Album, the kind playing
    send(ev.Press("knob"))
    assert app.link_kind == "album" and app.selected == 1  # on the album playing
    send(ev.Press("back"))
    assert app.mode is Mode.LINKING and app.link_kind is None
    send(ev.Press("back"))
    assert app.mode is Mode.PLAYING and app.album == album and app.status.state == "play"


def test_card_linked_to_start_from_the_beginning(rig):
    app, send, clock, store, *_ = rig
    linked(rig, from_start=True)
    assert store.from_start(CARD) and app.status.track_index == 0
    send(ev.Press("next"), advance=7.0)
    send(ev.CardRemoved(), ev.CardInserted(CARD))
    assert (app.status.track_index, app.status.state) == (0, "play") and app.status.elapsed < 0.5
    assert Store(rig[6]).from_start(CARD)  # saved


def test_back_from_the_start_question_returns_to_the_list(rig):
    app, send, clock, store, *_ = rig
    send(ev.CardInserted(CARD), ev.Press("knob"), ev.Rotate(PER_ITEM), advance=0.5)
    send(ev.Press("knob"))
    assert app.mode is Mode.LINK_START and store.album_for(CARD) is None  # nothing linked yet
    send(ev.Press("back"))
    assert app.mode is Mode.LINKING and app.link_kind == "album" and app.selected == 1


def test_menu_toggles_start_from_the_beginning(rig):
    app, send, clock, store, *_ = rig
    linked(rig)
    send(ev.Press("next"), advance=4.0)
    send(ev.Press("knob_long"), ev.Rotate(PER_ITEM), ev.Press("knob"))
    assert app.mode is Mode.MENU and store.from_start(CARD)  # the menu stays open to show it is on
    assert app._menu_rows()[1][2] == "On"
    app.render(clock.t)
    send(ev.Press("back"), ev.CardRemoved(), ev.CardInserted(CARD))
    assert app.status.track_index == 0 and app.status.elapsed < 0.5
    send(ev.Press("knob_long"), ev.Rotate(PER_ITEM), ev.Press("knob"))
    assert not store.from_start(CARD)


def test_cards_on_the_same_album_keep_their_own_choice(rig):
    app, send, clock, store, *_ = rig
    album = linked(rig, from_start=True)
    send(ev.CardRemoved())
    store.link(OTHER, album.key)
    assert store.from_start(CARD) and not store.from_start(OTHER)
    send(ev.CardInserted(OTHER), ev.Press("next"), advance=6.0)
    send(ev.CardRemoved(), ev.CardInserted(OTHER))
    assert app.status.track_index == 1  # OTHER carries on
    send(ev.CardRemoved(), ev.CardInserted(CARD))
    assert app.status.track_index == 0  # CARD starts over


def test_relinking_offers_the_cards_current_choice_and_web_links_keep_it(rig):
    app, send, clock, store, *_ = rig
    linked(rig, from_start=True)
    send(ev.Press("knob_long"), ev.Press("knob"), ev.Press("knob"), ev.Press("knob"))  # something else: an album
    assert app.mode is Mode.LINK_START and app.selected == 1
    send(ev.Press("knob"))
    assert store.from_start(CARD)
    send(ev.WebCommand("link_card", app.library.albums[2].key))
    assert store.album_for(CARD) == app.library.albums[2].key and store.from_start(CARD)


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
    shot()  # linking: choose the kind
    send(ev.Press("back"))
    shot()  # unlinked
    send(ev.Press("knob"), ev.Rotate(11), ev.Press("knob"))
    shot()  # linking: artists
    send(ev.Press("back"), ev.Rotate(-11), ev.Press("knob"))
    shot()  # linking: albums
    send(ev.Press("knob"))
    shot()  # linking: where it starts next time
    send(ev.Press("knob"))
    shot()  # now playing
    send(ev.Rotate(20))
    shot()  # volume overlay
    send(ev.Press("knob_long"))
    shot()  # menu
    send(ev.UsbHost(True))
    shot()  # usb offer
    send(ev.Press("knob"))
    shot()  # transfer
    assert len(seen) == 11


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


# ---- tags, artists and lists ----------------------------------------------

ITUNES = {  # a flat folder of bought songs: two albums and a single, in no useful filename order
    "From iTunes/Heroes.wav": dict(title="Heroes", artist="David Bowie", album="Heroes", albumartist="David Bowie", track="3/10", date="1977"),
    "From iTunes/Beauty and the Beast.wav": dict(title="Beauty and the Beast", artist="David Bowie", album="Heroes", albumartist="David Bowie", track="1", date="1977-10-14"),
    "From iTunes/Sound and Vision.wav": dict(title="Sound and Vision", artist="David Bowie", album="Low", albumartist="David Bowie", track="4", date="1977-01-14"),
    "From iTunes/Speed of Life.wav": dict(title="Speed of Life", artist="David Bowie", album="Low", albumartist="David Bowie", track="1", date="1977-01-14"),
    "From iTunes/Sinnerman.wav": dict(title="Sinnerman", artist="Nina Simone", album="Pastel Blues", track="9"),
    "Soundtrack/01 a.wav": dict(title="Opening", artist="One", album="The Film"),  # one album, several artists
    "Soundtrack/02 b.wav": dict(title="Closing", artist="Two", album="The Film"),
}


@pytest.fixture
def tagged(music, tmp_path):
    from player.library import make_tags

    root = tmp_path / "music"
    tone = (music / "Mika Tane" / "Small Hours" / "01 0300.wav").read_bytes()  # 20 seconds
    for rel in ITUNES:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(tone)
    (root / "Mika Tane" / "Small Hours").mkdir(parents=True)
    (root / "Mika Tane" / "Small Hours" / "01 0300.wav").write_bytes(tone)  # untagged: the folder is the album
    library = Library(root, tags=lambda: {p: make_tags(t) for p, t in ITUNES.items()}, art=lambda path: None)
    clock = Clock()
    store = Store(tmp_path / "state.json")
    playback = FakePlayback(library, clock)
    app = App(library, store, playback)

    def send(*events, advance=0.0):
        for e in events:
            app.handle(e, clock.t)
        clock.t += advance
        app.tick(clock.t)

    return app, send, library, store


def test_flat_folder_splits_into_albums_by_tag(tagged):
    app, send, library, store = tagged
    assert [(a.artist, a.title) for a in library.albums] == [
        ("David Bowie", "Heroes"),
        ("David Bowie", "Low"),
        ("Nina Simone", "Pastel Blues"),
        ("Mika Tane", "Small Hours"),
        ("Various Artists", "The Film"),
    ]
    heroes = library.albums[0]
    assert [t.title for t in heroes.tracks] == ["Beauty and the Beast", "Heroes"]  # track number order
    assert heroes.folder == "From iTunes" and not heroes.whole_folder and heroes.key != "From iTunes"
    assert library.get("Soundtrack").title == "The Film"  # alone in its folder: the folder is still its key


def test_a_list_is_a_folder_with_more_than_one_album(tagged):
    app, send, library, store = tagged
    assert [(l.key, l.albums, len(l.tracks)) for l in library.lists] == [("From iTunes", 3, 5)]
    names = [t.path.split("/")[-1] for t in library.lists[0].tracks]
    assert names == sorted(names, key=str.lower)  # played as the folder is, in filename order
    assert library.get("Soundtrack").kind == "album" and library.get("Mika Tane/Small Hours").kind == "album"


def test_artist_plays_every_album_in_year_order(tagged):
    app, send, library, store = tagged
    assert [a.title for a in library.artists] == ["David Bowie", "Mika Tane", "Nina Simone", "Various Artists"]
    bowie = library.artists[0]
    assert bowie.albums == 2 and bowie.folder is None
    assert [t.title for t in bowie.tracks] == ["Beauty and the Beast", "Heroes", "Speed of Life", "Sound and Vision"]


def test_card_links_to_a_list_from_the_device_and_resumes(tagged):
    app, send, library, store = tagged
    per_item = round(COUNTS_PER_REV * 15 / 360) + 1
    send(ev.CardInserted(CARD))
    send(ev.Rotate(per_item), advance=0.5)
    send(ev.Rotate(per_item), advance=0.5)
    send(ev.Press("knob"))
    assert app.link_kind == "list"
    send(ev.Press("knob"))  # the list
    send(ev.Press("knob"), advance=25.0)  # carry on where it stopped  # the first song is 20 seconds long
    assert store.album_for(CARD) == "From iTunes" and app.album.kind == "list"
    assert app.status.track_index == 1 and app.status.path == "From iTunes/Heroes.wav"
    assert app.snapshot()["details"] == "David Bowie · From iTunes"
    app.render(100.0)
    send(ev.CardRemoved(), ev.CardInserted(CARD))
    assert app.status.track_index == 1 and app.status.elapsed == pytest.approx(5.0, abs=0.01)


def test_card_links_to_an_artist_from_the_web(tagged):
    app, send, library, store = tagged
    bowie = library.artists[0]
    send(ev.CardInserted(CARD), ev.WebCommand("link_card", bowie.key))
    assert store.album_for(CARD) == bowie.key and app.status.track_count == 4
    snap = app.snapshot()
    assert snap["card_album"]["kind"] == "artist" and snap["details"] == "Heroes · David Bowie"
    json.dumps(snap)


def test_folder_link_follows_the_folder_between_album_and_list(tagged):
    app, send, library, store = tagged
    store.link(CARD, "Soundtrack")  # an album today
    extra = library.root / "Soundtrack" / "03 c.wav"
    extra.write_bytes((library.root / "Soundtrack" / "01 a.wav").read_bytes())
    ITUNES["Soundtrack/03 c.wav"] = dict(title="Bonus", artist="Three", album="Another Film")
    try:
        send(ev.LibraryChanged(), ev.CardInserted(CARD))
        assert app.album.kind == "list" and len(app.album.tracks) == 3  # now two albums: the card plays the folder
    finally:
        del ITUNES["Soundtrack/03 c.wav"]


def test_deleting_an_album_from_a_shared_folder_takes_only_its_tracks(tagged):
    from player.web import server as web

    class Writer:
        def begin(self):
            pass

        def end(self):
            pass

    app, send, library, store = tagged
    low = library.albums[1]
    assert [f["name"] for f in web.list_files(library, low.key)] == ["Sound and Vision.wav", "Speed of Life.wav"]
    with pytest.raises(web.UploadError):
        web.delete_music(library, Writer(), low.key, "Heroes.wav")  # another album's file
    with pytest.raises(web.UploadError):
        web.list_files(library, library.artists[0].key)  # an artist has no folder
    assert web.delete_music(library, Writer(), low.key) == 2
    assert sorted(f.name for f in (library.root / "From iTunes").iterdir()) == ["Beauty and the Beast.wav", "Heroes.wav", "Sinnerman.wav"]


# ---- scanning and the track list ----------------------------------------------


def test_fake_playback_seeks_within_the_track(rig):
    app, send, clock, store, playback, *_ = rig
    linked(rig)
    playback.seek(12.5)
    assert playback.status().elapsed == pytest.approx(12.5)
    playback.seek(-5)
    assert playback.status().elapsed == pytest.approx(0)
    playback.pause()
    playback.seek(3)
    assert playback.status().state == "pause" and playback.status().elapsed == pytest.approx(3)


def test_holding_next_fast_forwards_and_runs_into_the_next_track(rig):
    app, send, clock, *_ = rig
    linked(rig)  # first track is 20 s long
    send(ev.Press("next_hold"))
    assert app.status.elapsed == pytest.approx(4.0)  # the first step
    send(advance=0.4)
    send(ev.Press("next_hold"))
    assert app.status.elapsed == pytest.approx(4.4 + 8 * 0.4)  # played on, then 8x for the time held
    assert app.render(clock.t).tobytes() != app.render(clock.t + 5).tobytes()  # "Fast forward" shows, then goes
    for _ in range(5):  # past the end of the 20 s track
        send(advance=0.4)
        send(ev.Press("next_hold"))
    assert app.status.track_index == 1 and app.status.state == "play" and app.status.elapsed < 5


def test_holding_prev_rewinds_to_the_start_of_the_track_but_no_further(rig):
    app, send, clock, *_ = rig
    linked(rig)
    send(ev.Press("next"), advance=10.0)
    send(ev.Press("prev_hold"))
    assert app.status.elapsed == pytest.approx(6.0)
    for _ in range(10):
        send(advance=0.4)
        send(ev.Press("prev_hold"))
    assert (app.status.track_index, app.status.elapsed) == (1, pytest.approx(0, abs=0.5))


def test_scanning_speeds_up_the_longer_it_is_held(rig):
    app, send, clock, *_ = rig
    linked(rig, album_index=5)  # Slow Rooms: five tracks, 20 to 40 s
    send(ev.Press("next"), ev.Press("next"), ev.Press("next"), ev.Press("next"))  # last track, 40 s
    send(ev.Press("next_hold"))
    for _ in range(8):  # 3.2 s held
        send(advance=0.4)
        before = app.status.elapsed
        send(ev.Press("next_hold"))
    assert app.status.elapsed - before == pytest.approx(24 * 0.4, abs=0.01)


def test_back_shows_the_tracks_and_the_knob_picks_one(rig):
    app, send, clock, store, playback, *_ = rig
    linked(rig, album_index=5)  # Slow Rooms: five tracks
    per_item = round(COUNTS_PER_REV * 15 / 360) + 1
    send(ev.Press("next"), advance=2.0)
    send(ev.Press("back"))
    assert app.mode is Mode.TRACKS and app.selected == 1  # the playing track is highlighted
    shown = app.render(clock.t).tobytes()
    send(ev.Rotate(per_item), advance=0.5)
    assert app.selected == 2 and app.status.track_index == 1  # browsing does not change what plays
    assert app.render(clock.t).tobytes() != shown
    send(ev.Press("knob"))
    assert app.mode is Mode.PLAYING and app.status.track_index == 2 and app.status.elapsed < 0.5
    send(ev.Press("back"), ev.Press("back"))  # open and close without choosing
    assert app.mode is Mode.PLAYING and app.status.track_index == 2
    send(ev.Press("play"), ev.Press("back"), ev.Press("knob"))  # choosing the paused track resumes it in place
    assert app.status.state == "play" and app.status.track_index == 2


def test_holding_back_restarts_the_album(rig):
    app, send, clock, *_ = rig
    linked(rig, album_index=5)  # Slow Rooms: five tracks
    send(ev.Press("next"), ev.Press("next"), advance=5.0)
    send(ev.Press("back_long"))
    assert app.mode is Mode.PLAYING
    assert (app.status.state, app.status.track_index) == ("play", 0) and app.status.elapsed < 0.5
    send(ev.Press("next"), ev.Press("play"), ev.Press("back"))  # paused, with the track list open
    send(ev.Press("back_long"))
    assert app.mode is Mode.PLAYING and (app.status.state, app.status.track_index) == ("play", 0)


def test_holding_back_outside_playback_works_as_back(rig):
    app, send, *_ = rig
    linked(rig)
    send(ev.Press("knob_long"))
    assert app.mode is Mode.MENU
    send(ev.Press("back_long"))
    assert app.mode is Mode.PLAYING and app.status.track_index == 0


def test_track_list_works_for_a_list_and_survives_a_rescan(tagged):
    app, send, library, store = tagged
    send(ev.CardInserted(CARD), ev.WebCommand("link_card", "From iTunes"))
    send(ev.Press("back"))
    assert app.mode is Mode.TRACKS
    app.render(100.0)
    send(ev.LibraryChanged())
    assert app.mode is Mode.TRACKS and app.selected < len(app.album.tracks)
    send(ev.CardRemoved())
    assert app.mode is Mode.IDLE


def test_power_key_saves_the_place_and_goes_to_standby(rig):
    app, send, clock, store, playback, storage, state_file = rig
    linked(rig)
    send(ev.Press("next"), advance=5.0)
    send(ev.Press("power"))
    assert app.mode is Mode.STANDBY
    assert playback.status().state == "stop"  # MPD lets go of the DAC
    saved = json.loads(state_file.read_text())
    assert saved["cards"][CARD]["resume"] == [1, pytest.approx(5.0, abs=0.1)]
    assert app.snapshot()["mode"] == "standby"


def test_power_key_wakes_it_and_the_card_carries_on(rig):
    app, send, clock, store, playback, *_ = rig
    linked(rig)
    send(ev.Press("next"), advance=5.0)
    send(ev.Press("power"), advance=60.0)
    send(ev.Press("power"))
    assert app.mode is Mode.PLAYING and playback.status().state == "play"
    assert app.status.track_index == 1 and app.status.elapsed == pytest.approx(5.0, abs=0.1)


def test_a_card_wakes_it_and_plays(rig):
    app, send, clock, store, playback, *_ = rig
    linked(rig)
    send(ev.CardRemoved(), ev.Press("power"))
    assert app.mode is Mode.STANDBY
    send(ev.CardInserted(CARD))
    assert app.mode is Mode.PLAYING and playback.status().state == "play"


def test_taking_the_card_out_in_standby_leaves_it_asleep(rig):
    app, send, *_ = rig
    linked(rig)
    send(ev.Press("power"), ev.CardRemoved())
    assert app.mode is Mode.STANDBY and app.card is None
    send(ev.Press("power"))
    assert app.mode is Mode.IDLE


def test_other_keys_and_the_knob_only_wake_it(rig):
    app, send, clock, store, playback, *_ = rig
    send(ev.Press("power"))
    volume = store.volume
    send(ev.Rotate(PER_ITEM * 4))
    assert app.mode is Mode.IDLE and store.volume == volume  # nothing changed on a dark screen
    send(ev.Press("power"), ev.Press("knob_long"))
    assert app.mode is Mode.IDLE  # not the settings
    linked(rig)
    send(ev.Press("power"), ev.Press("next"))
    assert app.mode is Mode.PLAYING and app.status.track_index == 0  # woke up, did not skip


def test_the_web_remote_wakes_it_and_does_what_it_asked(rig):
    app, send, clock, store, playback, *_ = rig
    send(ev.Press("power"))
    album = app.library.albums[1]
    send(ev.WebCommand("play_album", album.key))
    assert app.mode is Mode.PLAYING and app.album.key == album.key and playback.status().state == "play"


def test_library_changes_in_standby_do_not_wake_it(rig):
    app, send, *_ = rig
    send(ev.Press("power"), ev.LibraryChanged(), ev.ListsChanged(), ev.UsbHost(False))
    assert app.mode is Mode.STANDBY
    send(ev.UsbHost(True))  # plugged into a computer: wakes up to offer a transfer
    assert app.mode is Mode.IDLE and app.usb_offer


def test_holding_power_in_standby_turns_it_off(rig):
    app, send, *_ = rig
    send(ev.Press("power"), ev.Press("power_long"))
    assert app.mode is Mode.OFF


def test_standby_waits_for_the_computer_and_for_uploads(rig):
    app, send, clock, *_ = rig
    send(ev.UsbHost(True), ev.Press("knob"))
    send(ev.Press("power"))
    assert app.mode is Mode.TRANSFER and app._error_until > clock.t
    send(ev.UsbEjected())
    app.is_uploading = lambda: True
    send(ev.Press("power"))
    assert app.mode is Mode.IDLE


def test_run_loop_switches_the_screen_off_in_standby_and_on_again(rig):
    import queue

    from player.main import run

    app, *_ = rig
    events = queue.Queue()
    events.put(ev.Press("power"))
    log = []
    sleeps = iter([False, True])  # the OLED misses the first try while the key is still down

    class Display:
        def show(self, image):
            log.append("show")

        def sleep(self):
            ok = next(sleeps)
            log.append(("sleep", ok))
            return ok

        def wake(self):
            log.append("wake")

    class Stop(BaseException):
        pass

    ticks = iter(range(6))

    def clock():
        try:
            t = next(ticks)
        except StopIteration:
            raise Stop
        if t == 4:
            events.put(ev.Press("power"))
        return 100.0 + t

    with pytest.raises(Stop):
        run(app, events, Display(), clock=clock, power_off=lambda: log.append("power_off"))
    assert log == [("sleep", False), ("sleep", True), "wake", "show"]  # nothing drawn while asleep


def test_holding_power_saves_the_place_stops_and_shows_turning_off(rig, monkeypatch):
    app, send, clock, store, playback, storage, state_file = rig
    linked(rig)
    send(ev.Press("next"), advance=5.0)
    send(ev.Press("power_long"))
    assert app.mode is Mode.OFF
    assert playback.status().state == "stop"
    saved = json.loads(state_file.read_text())
    assert saved["cards"][CARD]["resume"] == [1, pytest.approx(5.0, abs=0.1)]
    shown = []
    monkeypatch.setattr("player.app.render.message", lambda title, body="": shown.append(title))
    app.render(clock.t)
    assert shown == ["Turning off"]
    # Nothing else happens once it is turning off.
    send(ev.CardRemoved(), ev.CardInserted(OTHER), ev.Press("play"), ev.WebCommand("toggle"))
    assert app.mode is Mode.OFF and playback.status().state == "stop"


def test_holding_power_with_nothing_playing(rig):
    app, send, *_ = rig
    send(ev.Press("power_long"))
    assert app.mode is Mode.OFF


def test_holding_power_waits_for_the_computer_to_eject_the_drive(rig):
    app, send, clock, *_ = rig
    send(ev.UsbHost(True), ev.Press("knob"))
    assert app.mode is Mode.TRANSFER
    send(ev.Press("power_long"))
    assert app.mode is Mode.TRANSFER and app._error_until > clock.t


def test_holding_power_waits_for_a_web_upload(rig):
    app, send, *_ = rig
    app.is_uploading = lambda: True
    send(ev.Press("power_long"))
    assert app.mode is Mode.IDLE
    app.is_uploading = lambda: False
    send(ev.Press("power_long"))
    assert app.mode is Mode.OFF


def test_run_loop_shuts_down_once_after_drawing_the_off_screen(rig):
    import queue

    from player.main import run

    app, *_ = rig
    events = queue.Queue()
    events.put(ev.Press("power_long"))
    log = []

    class Display:
        def show(self, image):
            log.append(("show", app.mode))

    class Stop(BaseException):
        pass

    ticks = iter(range(4))

    def clock():
        try:
            return 100.0 + next(ticks)
        except StopIteration:
            raise Stop

    with pytest.raises(Stop):
        run(app, events, Display(), clock=clock, power_off=lambda: log.append("power_off"))
    assert log.index("power_off") == log.index(("show", Mode.OFF)) + 1
    assert log.count("power_off") == 1


def test_shutdown_waits_until_the_off_screen_gets_through(rig):
    """The OLED misses frames while the power key is held: shut down only once one gets through."""
    import queue

    from player.main import run

    app, *_ = rig
    events = queue.Queue()
    events.put(ev.Press("power_long"))
    log = []
    held = iter([True, True, True])  # the first three frames fail, as with the key still down

    class Display:
        def show(self, image):
            ok = not next(held, False)
            log.append(("show", app.mode, ok))
            return ok

    class Stop(BaseException):
        pass

    ticks = iter(range(6))

    def clock():
        try:
            return 100.0 + next(ticks) * 0.1
        except StopIteration:
            raise Stop

    with pytest.raises(Stop):
        run(app, events, Display(), clock=clock, power_off=lambda: log.append("power_off"))
    assert log.index("power_off") == log.index(("show", Mode.OFF, True)) + 1
    assert log.count("power_off") == 1


def test_shutdown_goes_ahead_if_the_screen_never_answers(rig):
    import queue

    from player import main

    app, *_ = rig
    events = queue.Queue()
    events.put(ev.Press("power_long"))
    log = []

    class Display:
        def show(self, image):
            return False

    class Stop(BaseException):
        pass

    ticks = iter(range(10))

    def clock():
        try:
            return 100.0 + next(ticks)
        except StopIteration:
            raise Stop

    with pytest.raises(Stop):
        main.run(app, events, Display(), clock=clock, power_off=lambda: log.append(clock()))
    assert len(log) == 1 and log[0] - 100.0 >= main.OFF_SCREEN_WAIT_SECONDS


def test_boot_logo_fits_each_screen():
    from player.ui import render, tiny

    assert render.splash().size == (render.W, render.H)
    assert tiny.splash().size == (tiny.W, tiny.H)
