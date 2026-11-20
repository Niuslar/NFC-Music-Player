"""Manage music: deleting albums, artists, lists and songs from the player's own screen."""

import pytest

from player import events as ev
from player.app import App, Mode, SETTINGS_ITEMS
from player.cards import Store
from player.demo_library import build
from player.knob import COUNTS_PER_REV
from player.library import Library, make_tags
from player.playback import FakePlayback
from player.ui import render, tiny
from player.web import server as web

STEP = round(COUNTS_PER_REV * 15 / 360) + 1  # one list row


class Writer:
    def __init__(self):
        self.sessions = 0

    def begin(self):
        self.sessions += 1

    def end(self):
        pass


@pytest.fixture
def rig(tmp_path):
    music = tmp_path / "music"
    build(music)
    library = Library(music)
    app = App(library, Store(tmp_path / "state.json"), FakePlayback(library))
    writer = Writer()
    app.delete_music = lambda key, name=None: web.delete_music(library, writer, key, name)
    t = [0.0]

    def send(*events):
        for e in events:
            t[0] += 0.5  # slow turns: one row per step, no acceleration
            app.handle(e, t[0])
            app.render(t[0])  # every screen on the way must draw

    def down(n):
        send(*[ev.Rotate(STEP)] * n)

    def open_manage():
        send(ev.Press("knob_long"))
        down(SETTINGS_ITEMS.index("Manage music"))
        send(ev.Press("knob"))
        assert app.mode is Mode.MANAGE

    return app, send, down, open_manage, music, writer


def test_manage_music_lists_the_four_sections(rig):
    app, send, down, open_manage, *_ = rig
    open_manage()
    assert [name for _, name in app._manage_kinds()] == ["Albums", "Artists", "All songs"]  # no lists in the demo: hidden
    (app.library.root / "Mixed").mkdir()
    for album in ("Low Tide Signals", "Paper Lanterns"):  # a folder of two albums is a list
        src = app.library.root / "Ada Hollis" / album
        (app.library.root / "Mixed" / f"{album}.wav").write_bytes(next(src.glob("*.wav")).read_bytes())
    tags = {f"Mixed/{a}.wav": make_tags({"album": a}) for a in ("Low Tide Signals", "Paper Lanterns")}
    app.library = Library(app.library.root, tags=lambda: tags)
    assert [name for _, name in app._manage_kinds()] == ["Albums", "Artists", "Lists", "All songs"]
    down(10)  # past the end: Back
    send(ev.Press("knob"))
    assert app.mode is Mode.SETTINGS and SETTINGS_ITEMS[app.selected] == "Manage music"


def test_keep_it_is_the_default_and_deletes_nothing(rig):
    app, send, down, open_manage, music, writer = rig
    open_manage()
    send(ev.Press("knob"), ev.Press("knob"))  # Albums, the first album
    assert app.mode is Mode.MANAGE_ITEM
    send(ev.Press("knob"))  # Delete whole album
    assert app.mode is Mode.MANAGE_CONFIRM and app.selected == 0
    send(ev.Press("knob"))  # Keep it
    assert app.mode is Mode.MANAGE_ITEM and writer.sessions == 0
    send(ev.Press("knob"), ev.Press("back"))
    assert app.mode is Mode.MANAGE_ITEM and writer.sessions == 0


def test_delete_a_whole_album(rig):
    app, send, down, open_manage, music, writer = rig
    open_manage()
    send(ev.Press("knob"))  # Albums
    titles = [a.title for a in app.library.albums]
    down(titles.index("Paper Lanterns"))
    send(ev.Press("knob"), ev.Press("knob"))  # open it, Delete whole album
    down(1)
    send(ev.Press("knob"))  # Delete this album
    assert not (music / "Ada Hollis" / "Paper Lanterns").exists()
    assert (music / "Ada Hollis" / "Low Tide Signals").exists()
    assert "Paper Lanterns" not in [a.title for a in app.library.albums]
    assert app.mode is Mode.MANAGE_LIST and app.manage_kind == "album"
    assert app.library.albums[app.selected].title == titles[titles.index("Paper Lanterns") + 1]


def test_delete_one_song_from_an_album_stays_on_the_album(rig):
    app, send, down, open_manage, music, writer = rig
    open_manage()
    send(ev.Press("knob"))  # Albums
    titles = [a.title for a in app.library.albums]
    down(titles.index("Slow Rooms"))
    send(ev.Press("knob"))
    down(2)  # past Delete whole album, onto the second song
    send(ev.Press("knob"))
    down(1)
    send(ev.Press("knob"))
    album = music / "Northern Quartet" / "Slow Rooms"
    assert not (album / "02 Room Two.wav").exists() and (album / "01 Room One.wav").exists()
    assert app.mode is Mode.MANAGE_ITEM and len(app.manage_item.tracks) == 4
    assert app._manage_rows()[app.selected].title == "Room Three"


def test_delete_everything_by_an_artist(rig):
    app, send, down, open_manage, music, writer = rig
    open_manage()
    down(1)
    send(ev.Press("knob"))  # Artists
    assert app.manage_kind == "artist"
    down([a.title for a in app.library.artists].index("Ada Hollis"))
    send(ev.Press("knob"), ev.Press("knob"))  # open, Delete all music by this artist
    down(1)
    send(ev.Press("knob"))
    assert not (music / "Ada Hollis").exists()
    assert "Ada Hollis" not in [a.title for a in app.library.artists]
    assert app.mode is Mode.MANAGE_LIST


def test_delete_from_all_songs(rig):
    app, send, down, open_manage, music, writer = rig
    total = sum(len(a.tracks) for a in app.library.albums)
    open_manage()
    down([k for k, _ in app._manage_kinds()].index("song"))
    send(ev.Press("knob"))  # All songs
    first = app._manage_entries()[0]
    send(ev.Press("knob"))  # straight to the question: a song has nothing inside
    assert app.mode is Mode.MANAGE_CONFIRM
    down(1)
    send(ev.Press("knob"))
    assert not (music / first.path).exists()
    assert app.mode is Mode.MANAGE_LIST and len(app._manage_entries()) == total - 1


def test_deleting_the_last_song_leaves_the_album_page(rig):
    app, send, down, open_manage, music, writer = rig
    open_manage()
    send(ev.Press("knob"))  # Albums
    titles = [a.title for a in app.library.albums]
    down(titles.index("Loose Album Without Artist"))
    send(ev.Press("knob"))
    for _ in range(2):  # it has two songs
        down(1)
        send(ev.Press("knob"))
        down(1)
        send(ev.Press("knob"))
    assert not (music / "Loose Album Without Artist").exists()
    assert app.mode is Mode.MANAGE_LIST and app.manage_item is None


def test_a_deletion_on_the_web_remote_updates_the_open_page(rig):
    app, send, down, open_manage, music, writer = rig
    open_manage()
    send(ev.Press("knob"), ev.Press("knob"))  # Albums, the first album
    key = app.manage_item.key
    web.delete_music(app.library, writer, key)
    send(ev.LibraryChanged())
    assert app.mode is Mode.MANAGE_LIST and app.library.get(key) is None


def test_without_a_way_to_delete_it_says_so(rig):
    app, send, down, open_manage, music, writer = rig
    app.delete_music = None
    open_manage()
    send(ev.Press("knob"), ev.Press("knob"), ev.Press("knob"))
    down(1)
    send(ev.Press("knob"))
    assert "not available" in app._error and len(app.library.albums) == 7


@pytest.mark.parametrize("ui", [render, tiny])
def test_manage_screens_draw_on_both_displays(rig, ui):
    app, send, down, open_manage, *_ = rig
    app.ui = ui
    open_manage()
    send(ev.Press("knob"), ev.Press("knob"), ev.Press("knob"))  # down to the question; send() draws each
