"""The player's behaviour: a state machine fed with events, drawn with render().

It never touches hardware; everything arrives as events and leaves through
the playback, store and storage objects it is given.
"""

from enum import Enum, auto

from . import events as ev
from .cards import Store
from .knob import list_scaler, volume_scaler
from .library import KINDS, Item, Library
from .playback import Status
from .ui import render

VOLUME_OVERLAY_SECONDS = 1.5
MISSING = "The music linked to this card is missing."
MENU_ITEMS = ("Link to something else", "Unlink this card", "Close")
KIND_NAMES = {"album": ("Album", "album"), "artist": ("Artist", "artist"), "list": ("List", "list")}


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


class Mode(Enum):
    IDLE = auto()  # no card in the slot
    PLAYING = auto()  # linked card in the slot (playing, paused or finished)
    UNLINKED = auto()  # card in the slot with nothing to play
    LINKING = auto()  # choosing what the card plays: first the kind, then the album, artist or list
    MENU = auto()
    TRANSFER = auto()  # music partition handed to the computer


class NullStorage:
    """Stands in for the USB gadget until the real one exists."""

    def release(self) -> None:
        pass

    def reclaim(self) -> None:
        pass


class App:
    def __init__(self, library: Library, store: Store, playback, storage=None, volume_steps_per_rev: int = 60):
        self.library = library
        self.store = store
        self.playback = playback
        self.storage = storage or NullStorage()
        self.mode = Mode.IDLE
        self.card: str | None = None
        self.album: Item | None = None  # what is playing: an album, an artist or a list
        self.link_kind: str | None = None  # while linking: the kind being browsed, None while choosing the kind
        self.status = Status()
        self.selected = 0
        self.note = ""
        self.usb_offer = False
        self.remote = False  # the album was started from the web remote, not by the card
        self.is_uploading = lambda: False  # replaced by main when the web remote is on
        self._now = 0.0
        self._volume_until = 0.0
        self._error = ""
        self._error_until = 0.0
        self._art_from = None  # which file the cover on screen came from
        self._art: bytes | None = None
        self._vol_knob = volume_scaler(volume_steps_per_rev)
        self._list_knob = list_scaler()
        playback.set_volume(store.volume)

    # ---- events -------------------------------------------------------------

    def handle(self, event, now: float) -> None:
        self._now = now
        if isinstance(event, ev.WebCommand):
            self._web(event.action, event.value)
        elif isinstance(event, ev.LibraryChanged):
            self._refresh_library()
        elif isinstance(event, ev.CardInserted):
            if self.card is not None and self.mode is not Mode.TRANSFER:
                self._leave_card()
            self.card = event.uid
            if self.mode is not Mode.TRANSFER:
                self._enter_card()
        elif isinstance(event, ev.CardRemoved):
            if self.card is not None and self.mode is not Mode.TRANSFER:
                self._leave_card()
            self.card = None
        elif isinstance(event, ev.UsbHost):
            self.usb_offer = event.connected and self.mode is not Mode.TRANSFER
            if not event.connected and self.mode is Mode.TRANSFER:
                self._end_transfer()
        elif isinstance(event, ev.UsbEjected):
            if self.mode is Mode.TRANSFER:
                self._end_transfer()
        elif isinstance(event, ev.Rotate):
            self._rotate(event.counts, now)
        elif isinstance(event, ev.Press):
            self._press(event.button)

    def tick(self, now: float) -> None:
        """Called several times a second to follow what the player is doing."""
        if self.album is None or self.mode is Mode.TRANSFER:
            return
        was_active = self.status.state != "stop"
        self.status = self.playback.status()
        if was_active and self.status.state == "stop" and self.card and not self.remote:
            self.store.clear_resume(self.card)  # album played to the end

    def _rotate(self, counts: int, now: float) -> None:
        if self.mode is Mode.TRANSFER or self.usb_offer:
            return
        if self.mode in (Mode.LINKING, Mode.MENU):
            count = len(self._link_choices()) if self.mode is Mode.LINKING else len(MENU_ITEMS)
            steps = self._list_knob.feed(counts, now)
            self.selected = min(max(self.selected + steps, 0), count - 1)
            return
        self._set_volume(self.store.volume + self._vol_knob.feed(counts, now))

    def _set_volume(self, volume: int) -> None:
        volume = min(max(int(volume), 0), 100)
        if volume != self.store.volume:
            self.store.volume = volume
            self.playback.set_volume(volume)
        self._volume_until = self._now + VOLUME_OVERLAY_SECONDS

    def _web(self, action: str, value) -> None:
        if self.mode is Mode.TRANSFER:
            return
        if action == "volume":
            self._set_volume(value)
        elif action == "play_album":
            album = self.library.get(str(value))
            if album is not None:
                self._play_remote(album)
        elif action == "link_card":
            album = self.library.get(str(value))
            if self.card and album is not None:
                if album == self.album and self.status.state != "stop":
                    self.store.link(self.card, album.key)  # already playing it: adopt without restarting
                    self.remote = False
                else:
                    self._link(album)
        elif action == "unlink_card":
            if self.card and self.store.album_for(self.card):
                self._unlink()
        elif self.album is not None:
            if action == "toggle":
                self._toggle()
            elif action == "next":
                self.playback.next()
            elif action == "prev":
                self.playback.prev()

    def _play_remote(self, album: Item) -> None:
        if self.album is not None and self.card and not self.remote:
            st = self.playback.status()  # keep the card's own place before taking over
            if st.state != "stop":
                self.store.set_resume(self.card, st.track_index, st.elapsed)
                self.store.save()
        self.remote = True
        self._play(album)

    def _refresh_library(self) -> None:
        self._rescan()
        if self.link_kind and not self.library.of(self.link_kind):
            self.link_kind = None
        if self.mode is Mode.LINKING:
            self.selected = min(self.selected, max(len(self._link_choices()) - 1, 0))
        if self.album is None:
            return
        fresh = self.library.get(self.album.key)
        if fresh is not None:
            self.album = fresh  # same thing, possibly with tracks added or removed
            return
        # What was playing has been deleted.
        from_card = self.card is not None and not self.remote
        self.playback.stop()
        self.album, self.status, self.remote = None, Status(), False
        if from_card:
            self.mode, self.note = Mode.UNLINKED, MISSING
        else:
            self.mode = Mode.IDLE

    def _press(self, button: str) -> None:
        if self.mode is Mode.TRANSFER:
            if button == "knob_long":  # manual way out if the eject was not noticed
                self._end_transfer()
            return
        if self.usb_offer:
            if button == "knob" and self.is_uploading():
                self.show_error("An upload from the web page is still running. Try again when it finishes.", self._now)
            elif button == "knob":
                self._start_transfer()
            elif button == "back":
                self.usb_offer = False
            return
        if self.mode is Mode.PLAYING:
            if button in ("knob", "play"):
                self._toggle()
            elif button == "next":
                self.playback.next()
            elif button == "prev":
                self.playback.prev()
            elif button == "knob_long" and self.card and not self.remote:
                self._open_list(Mode.MENU, 0)  # the menu is about the card's link
        elif self.mode is Mode.MENU:
            if button == "knob":
                self._menu_choice(self.selected)
            elif button in ("back", "knob_long"):
                self.mode = Mode.PLAYING
        elif self.mode is Mode.LINKING:
            if button == "knob" and self.link_kind is None:
                self._browse(self._kinds()[self.selected])
            elif button == "knob":
                self._link(self.library.of(self.link_kind)[self.selected])
            elif button == "back" and self.link_kind is not None:
                self._start_linking(self.link_kind)  # back to choosing the kind
            elif button == "back":
                self.mode = Mode.PLAYING if self.album else Mode.UNLINKED
        elif self.mode is Mode.UNLINKED:
            if button == "knob":
                self._start_linking()

    # ---- actions ------------------------------------------------------------

    def _toggle(self) -> None:
        state = self.status.state
        if state == "play":
            self.playback.pause()
        elif state == "pause":
            self.playback.resume()
        else:
            self.playback.play(self.album.tracks)
        self.status = self.playback.status()

    def _open_list(self, mode: Mode, selected: int) -> None:
        self.mode, self.selected = mode, selected
        self._list_knob.reset()

    def _enter_card(self) -> None:
        self.note = ""
        path = self.store.album_for(self.card)
        if path is None:
            self._start_linking()
            return
        album = self.library.get(path)
        if album is None:
            self.mode, self.note = Mode.UNLINKED, MISSING
            return
        track, elapsed = self.store.resume_point(self.card)
        if track >= len(album.tracks):
            track, elapsed = 0, 0.0
        self.remote = False
        self._play(album, track, elapsed)

    def _play(self, album: Item, track: int = 0, elapsed: float = 0.0) -> None:
        self.album = album
        self.playback.play(album.tracks, track, elapsed)
        self.status = self.playback.status()
        self.mode = Mode.PLAYING

    def _leave_card(self) -> None:
        """Card is going away (or transfer is starting): remember the position and pause."""
        if self.album is not None:
            st = self.playback.status()
            if self.remote or self.card is None:
                if st.state != "stop":
                    self.playback.pause()  # not the card's album: nothing to remember
            elif st.state == "stop":
                self.store.clear_resume(self.card)
            else:
                self.store.set_resume(self.card, st.track_index, st.elapsed)
                self.playback.pause()
            self.store.save()  # also persists the volume
        self.album = None
        self.status = Status()
        self.remote = False
        self.mode = Mode.IDLE

    def _kinds(self) -> list[str]:
        """The kinds of thing there is at least one of."""
        return [k for k in KINDS if self.library.of(k)]

    def _link_choices(self) -> list:
        return self._kinds() if self.link_kind is None else self.library.of(self.link_kind)

    def _start_linking(self, kind: str | None = None) -> None:
        """Opens the first linking screen, with kind (or what is playing now) preselected."""
        if not self.library.albums:
            self.mode, self.note = Mode.UNLINKED, "No music yet. Connect to a computer to add some."
            return
        kinds = self._kinds()
        kind = kind or (self.album.kind if self.album else None)
        self.link_kind = None
        self._open_list(Mode.LINKING, kinds.index(kind) if kind in kinds else 0)

    def _browse(self, kind: str) -> None:
        items = self.library.of(kind)
        self.link_kind = kind
        self._open_list(Mode.LINKING, items.index(self.album) if self.album in items else 0)

    def _link(self, album: Item) -> None:
        self.store.link(self.card, album.key)
        self.remote = False
        self._play(album)

    def _menu_choice(self, index: int) -> None:
        if index == 0:
            self._start_linking()
        elif index == 1:
            self._unlink()
        else:
            self.mode = Mode.PLAYING

    def _unlink(self) -> None:
        self.store.unlink(self.card)
        if self.remote:
            return  # something else is playing from the web page; leave it alone
        self.playback.stop()
        self.album, self.status = None, Status()
        self.mode, self.note = Mode.UNLINKED, "Card unlinked."

    def _start_transfer(self) -> None:
        self.usb_offer = False
        self._leave_card()
        self.playback.stop()
        self.storage.release()  # if this fails we stay idle and the error is shown
        self.mode = Mode.TRANSFER

    def _end_transfer(self) -> None:
        self.mode = Mode.IDLE  # set first so a failure below cannot leave us stuck in transfer
        self.storage.reclaim()
        self._rescan()
        if self.card is not None:
            self._enter_card()

    def _rescan(self) -> None:
        self.playback.rescan()  # first: on the Pi the library reads its tags from MPD's database
        self.library.rescan()
        render.forget_covers()
        self._art_from = None

    def _track(self):
        """The track playing now, or the first one when nothing is."""
        album = self.album
        return self.library.track(self.status.path) or (album.tracks[0] if album and album.tracks else None)

    def _details(self) -> tuple[str, str]:
        """The two lines under the track title."""
        album, track = self.album, self._track()
        if album.kind == "list" and track:
            return track.artist or track.album, album.title
        if album.kind == "artist" and track:
            return track.album, album.title
        return album.title, album.artist

    def _cover(self) -> bytes | None:
        track = self._track()
        source = self.library.art_source(track) if track else None
        if source != self._art_from:
            self._art_from = source
            self._art = self.library.art(track) if track else None
        return self._art

    def show_error(self, text: str, now: float, seconds: float = 6.0) -> None:
        self._error, self._error_until = text, now + seconds

    def _card_album(self) -> dict | None:
        path = self.store.album_for(self.card) if self.card else None
        if path is None:
            return None
        album = self.library.get(path)
        return {"key": path, "title": album.title if album else None, "kind": album.kind if album else None}

    def snapshot(self) -> dict:
        """What the web remote shows. Plain data, safe to hand to another thread."""
        st, album = self.status, self.album
        return {
            "mode": self.mode.name.lower(),
            "card": self.card is not None,
            "card_album": self._card_album(),
            "remote": self.remote,
            "volume": self.store.volume,
            "album": {"key": album.key, "title": album.title, "artist": album.artist, "kind": album.kind} if album else None,
            "details": " · ".join(filter(None, self._details())) if album else "",
            "state": st.state if album else "stop",
            "track": st.title,
            "track_path": st.path,
            "track_index": st.track_index,
            "track_count": st.track_count,
            "elapsed": round(st.elapsed, 1),
            "duration": round(st.duration, 1),
            "albums": len(self.library.albums),
            "library": self.library.version,
        }

    # ---- drawing ------------------------------------------------------------

    def render(self, now: float):
        if now < self._error_until:
            return render.message("Something went wrong", self._error)
        if self.mode is Mode.TRANSFER:
            return render.message(
                "Transfer mode",
                "Copy music to the MUSIC drive, then eject it on your computer.\nOr hold the knob when finished.",
            )
        if self.usb_offer:
            return render.message("Connected to a computer", "Push the knob to transfer music.\nBack to keep listening.")
        if self.mode is Mode.IDLE:
            return render.message("Place a card", "to start playing")
        if self.mode is Mode.UNLINKED:
            prompt = "Push the knob to choose what it plays." if self.library.albums else ""
            return render.message("Card not linked", f"{self.note}\n{prompt}".strip())
        if self.mode is Mode.LINKING and self.link_kind is None:
            rows = [(KIND_NAMES[k][0], _count(len(self.library.of(k)), KIND_NAMES[k][1])) for k in self._kinds()]
            return render.list_screen("Link this card to", rows, self.selected)
        if self.mode is Mode.LINKING:
            items = self.library.of(self.link_kind)
            if self.link_kind == "album":
                rows = [(a.title, a.artist) for a in items]
            elif self.link_kind == "artist":
                rows = [(a.title, f"{_count(a.albums, 'album')} · {_count(len(a.tracks), 'track')}") for a in items]
            else:
                rows = [(a.title, _count(len(a.tracks), "track")) for a in items]
            article = "an" if self.link_kind[0] == "a" else "a"
            return render.list_screen(f"Choose {article} {self.link_kind} for this card", rows, self.selected)
        if self.mode is Mode.MENU:
            return render.list_screen(self.album.title, [(item, "") for item in MENU_ITEMS], self.selected)
        volume = self.store.volume if now < self._volume_until else None
        return render.now_playing(self.album.title, self._details(), self._cover(), self.status, volume)
