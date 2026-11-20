"""Lists made on the web remote: the store, how the library shows them, the API, and playing them."""

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
from player.playlists import ListError, Playlists, key_of
from player.web import server as web

OK = {"X-Requested-With": "nfc-player", "Content-Type": "application/json"}
CARD = "04AA"
LANTERNS = "Ada Hollis/Paper Lanterns/01 Lanterns.wav"
KITE = "Ada Hollis/Paper Lanterns/02 Kite String.wav"
HOURS = "Mika Tane/Small Hours/01 0300.wav"


# ---- the store ---------------------------------------------------------------


def test_lists_are_saved_and_read_back(tmp_path):
    path = tmp_path / "lists.json"
    store = Playlists(path)
    made = store.create("  Sunday   morning ", [LANTERNS])
    assert made["name"] == "Sunday morning" and made["tracks"] == [LANTERNS]
    store.add(made["id"], [HOURS])
    store.rename(made["id"], "Sundays")
    other = store.create("Empty")
    store.delete(other["id"])
    again = Playlists(path).all()
    assert again == [{"id": made["id"], "name": "Sundays", "tracks": [LANTERNS, HOURS]}]
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize(
    "call",
    [
        lambda s: s.create(""),
        lambda s: s.create("x" * 121),
        lambda s: s.create("Fine", "not a list"),
        lambda s: s.create("Fine", [1, 2]),
        lambda s: s.rename("nope", "Name"),
        lambda s: s.delete("nope"),
    ],
)
def test_bad_changes_are_refused(tmp_path, call):
    with pytest.raises(ListError):
        call(Playlists(tmp_path / "lists.json"))


def test_unreadable_file_starts_empty(tmp_path):
    path = tmp_path / "lists.json"
    path.write_text("{not json")
    assert Playlists(path).all() == []


# ---- the library -------------------------------------------------------------


def test_library_shows_lists_and_skips_missing_tracks(tmp_path):
    music = tmp_path / "music"
    build(music)
    store = Playlists(None)
    full = store.create("Mixed", [HOURS, "Gone/Album/01 Missing.wav", LANTERNS])
    empty = store.create("Nothing yet")
    library = Library(music, playlists=store.all)
    mixed = library.get(key_of(full["id"]))
    assert mixed.kind == "list" and mixed.is_playlist and mixed.folder is None
    assert [t.path for t in mixed.tracks] == [HOURS, LANTERNS] and mixed.albums == 2
    assert mixed in library.lists  # a card can link to it
    assert library.get(key_of(empty["id"])) in library.playlists and library.get(key_of(empty["id"])) not in library.lists

    version = library.version
    store.set_tracks(full["id"], [LANTERNS])
    library.refresh_playlists()
    assert [t.path for t in library.get(key_of(full["id"])).tracks] == [LANTERNS] and library.version == version + 1


# ---- the API -------------------------------------------------------------------


@pytest.fixture
def site(tmp_path):
    music = tmp_path / "music"
    build(music)
    store = Playlists(tmp_path / "lists.json")
    library = Library(music, playlists=store.all)
    events = queue.Queue()
    shared = web.Shared()
    writer = web.MusicWriter(lambda: events.put(ev.LibraryChanged()), idle_seconds=0.05)
    server = web.start(events, shared, library, writer, port=0, bind="127.0.0.1", playlists=store)
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def call(method, path, body=None, headers=OK):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    yield call, events, library, store
    server.shutdown()
    server.server_close()


def test_lists_api_makes_and_changes_lists(site):
    call, events, library, store = site
    status, body = call("POST", "/api/lists", {"op": "create", "name": "Road trip", "tracks": [LANTERNS, KITE]})
    assert status == 200 and body["list"]["name"] == "Road trip"
    key, list_id = body["list"]["key"], body["list"]["id"]
    assert events.get_nowait() == ev.ListsChanged()
    library.refresh_playlists()  # what the main loop does with that event

    items = {i["key"]: i for i in call("GET", "/api/library")[1]}
    assert items[key]["playlist"] and items[key]["tracks"] == 2 and not items[key]["files"]
    item = call("GET", f"/api/item?key={urllib.request.quote(key)}")[1]
    assert [t["path"] for t in item["items"]] == [LANTERNS, KITE] and item["items"][0]["title"] == "Lanterns"

    assert call("POST", "/api/lists", {"op": "add", "id": list_id, "tracks": [HOURS]})[0] == 200
    assert call("POST", "/api/lists", {"op": "set", "id": list_id, "tracks": [HOURS, LANTERNS]})[0] == 200
    assert call("POST", "/api/lists", {"op": "rename", "id": list_id, "name": "Long drive"})[0] == 200
    assert store.all() == [{"id": list_id, "name": "Long drive", "tracks": [HOURS, LANTERNS]}]
    assert call("POST", "/api/lists", {"op": "delete", "id": list_id}) == (200, {"ok": True, "list": {}})
    assert store.all() == []


def test_lists_api_refusals(site):
    call, events, library, store = site
    assert call("POST", "/api/lists", {"op": "create", "name": "x", "tracks": ["No/Such/track.flac"]})[0] == 400
    assert call("POST", "/api/lists", {"op": "create", "name": ""})[0] == 400
    assert call("POST", "/api/lists", {"op": "rename", "id": "nope", "name": "x"})[0] == 400
    assert call("POST", "/api/lists", {"op": "explode"})[0] == 400
    assert call("POST", "/api/lists", {"op": "create", "name": "x"}, {"Content-Type": "application/json"})[0] == 403
    assert store.all() == [] and events.empty()


def test_songs_and_items(site):
    call, events, library, store = site
    songs = call("GET", "/api/songs")[1]
    assert len(songs) == sum(len(a.tracks) for a in library.albums)
    first = next(s for s in songs if s["path"] == KITE)
    assert first == {"path": KITE, "title": "Kite String", "artist": "", "album": "Paper Lanterns", "disc": 0, "key": "Ada Hollis/Paper Lanterns", "index": 1}
    assert call("GET", "/api/item?key=nope")[0] == 404


def test_new_commands_are_checked(site):
    call, events, *_ = site
    post = lambda msg: call("POST", "/api/command", msg)[0]
    assert post({"action": "seek", "value": "12.5"}) == 200
    assert post({"action": "play_at", "value": {"key": "Ada Hollis/Paper Lanterns", "index": 2}}) == 200
    assert [events.get_nowait() for _ in range(2)] == [
        ev.WebCommand("seek", 12.5),
        ev.WebCommand("play_at", {"key": "Ada Hollis/Paper Lanterns", "index": 2}),
    ]
    assert post({"action": "seek", "value": "soon"}) == 400
    assert post({"action": "seek", "value": -3}) == 400
    assert post({"action": "play_at", "value": {"key": "x", "index": "2"}}) == 400
    assert post({"action": "play_at", "value": "x"}) == 400
    assert events.empty()


# ---- playing ---------------------------------------------------------------------


class Clock:
    t = 100.0

    def __call__(self):
        return self.t


@pytest.fixture
def rig(tmp_path):
    music = tmp_path / "music"
    build(music)
    clock = Clock()
    lists = Playlists(None)
    library = Library(music, playlists=lists.all)
    store = Store(tmp_path / "state.json")
    playback = FakePlayback(library, clock)
    app = App(library, store, playback)

    def send(*events, advance=0.0):
        for e in events:
            app.handle(e, clock.t)
        clock.t += advance
        app.tick(clock.t)

    return app, send, clock, store, lists, library


def test_play_at_and_seek(rig):
    app, send, clock, store, lists, library = rig
    send(ev.WebCommand("play_at", {"key": "Ada Hollis/Paper Lanterns", "index": 1}), advance=1.0)
    assert app.remote and app.status.track_index == 1 and app.status.title == "Kite String"
    send(ev.WebCommand("seek", 5.0))
    assert app.status.elapsed == pytest.approx(5.0)
    send(ev.WebCommand("play_at", {"key": "Ada Hollis/Paper Lanterns", "index": 9}))  # out of range: ignored
    assert app.status.track_index == 1


def test_jumping_within_the_cards_album_keeps_it_the_cards(rig):
    app, send, clock, store, lists, library = rig
    store.link(CARD, "Ada Hollis/Paper Lanterns")
    send(ev.CardInserted(CARD))
    send(ev.WebCommand("play_at", {"key": "Ada Hollis/Paper Lanterns", "index": 2}), advance=3.0)
    assert not app.remote and app.status.track_index == 2
    send(ev.CardRemoved())
    assert store.resume_point(CARD) == (2, pytest.approx(3.0, abs=0.01))


def test_a_card_plays_a_made_list_and_follows_its_changes(rig):
    app, send, clock, store, lists, library = rig
    made = lists.create("Mixed", [HOURS, LANTERNS])
    send(ev.ListsChanged())
    key = key_of(made["id"])
    send(ev.CardInserted(CARD))
    assert app.mode is Mode.LINKING
    send(ev.WebCommand("link_card", key))
    assert app.mode is Mode.PLAYING and app.album.title == "Mixed" and app.status.title == "0300"
    lists.rename(made["id"], "Renamed")
    send(ev.ListsChanged())
    assert app.album.title == "Renamed" and store.album_for(CARD) == key
    lists.delete(made["id"])
    send(ev.ListsChanged())
    assert app.mode is Mode.UNLINKED and app.album is None


def test_snapshot_names_everything_a_card_is_linked_to(rig):
    app, send, clock, store, lists, library = rig
    assert app.snapshot()["linked"] == []
    store.link(CARD, "Ada Hollis/Paper Lanterns")
    store.link("04BB", "Ada Hollis/Paper Lanterns")
    store.link("04CC", "//artist//mika tane")
    assert app.snapshot()["linked"] == ["//artist//mika tane", "Ada Hollis/Paper Lanterns"]  # no card in the slot needed
