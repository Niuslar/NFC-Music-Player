"""The player's behaviour: a state machine fed with events, drawn with render().

It never touches hardware; everything arrives as events and leaves through
the playback, store and storage objects it is given.
"""

import shutil
from enum import Enum, auto

from . import events as ev
from . import wifi as wifi_mod
from .cards import VOLUME_LIMITS, Store
from .knob import list_scaler, volume_scaler
from .library import KINDS, Item, Library
from .playback import Status
from .ui import render

VOLUME_OVERLAY_SECONDS = 1.5
# Holding previous or next scans through the track: this many seconds of music per second held,
# speeding up after SCAN_FASTER_AFTER seconds. A pause longer than SCAN_GAP starts a new scan.
SCAN_SPEEDS = (8.0, 24.0)
SCAN_FASTER_AFTER = 3.0
SCAN_FIRST_STEP = 4.0
SCAN_GAP = 1.0
SCAN_LABEL_SECONDS = 0.8
MISSING = "The music linked to this card is missing."
TEST_SCREEN_SECONDS = 5.0
MENU_ITEMS = ("Link to something else", "Always start over", "Unlink this card", "Close")
START_CHOICES = (  # the question after choosing what a card plays: index 1 means always from the beginning
    ("Carry on where it left off", "Picks up at the same song and place"),
    ("Always start over", "Plays from the first song every time"),
)
SETTINGS_ITEMS = ("Wi-Fi", "Volume limit", "Manage music", "About this player", "Restart the player", "Close")
MANAGE_KINDS = (("album", "Albums"), ("artist", "Artists"), ("list", "Lists"), ("song", "All songs"))
WIFI_ITEMS = ("Wi-Fi", "Connect to a new network", "Show web player", "Back")  # only Wi-Fi and Back while it is off
SIGNAL_WORDS = {1: "weak signal", 2: "fair signal", 3: "good signal", 4: "strong signal"}
KIND_NAMES = {"album": ("Album", "album"), "artist": ("Artist", "artist"), "list": ("List", "list")}


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


class Mode(Enum):
    IDLE = auto()  # no card in the slot
    PLAYING = auto()  # linked card in the slot (playing, paused or finished)
    UNLINKED = auto()  # card in the slot with nothing to play
    LINKING = auto()  # choosing what the card plays: first the kind, then the album, artist or list
    LINK_START = auto()  # then whether it carries on where it stopped or always starts from the beginning
    MENU = auto()
    TRACKS = auto()  # the tracks of what is playing, to jump to one
    TRANSFER = auto()  # music partition handed to the computer
    OFF = auto()  # the power key was pressed: everything is saved and the Pi is shutting down
    # Settings, from holding the knob with no card in the slot:
    SETTINGS = auto()
    WIFI = auto()  # the Wi-Fi page: what it is connected to, and joining a new network
    WIFI_SETUP = auto()  # the setup network is up (or starting, or joining): instructions for the phone
    VOLUME_LIMIT = auto()
    ABOUT = auto()
    # Manage music, for deleting without a computer or the web remote:
    MANAGE = auto()  # Albums, Artists, Lists, All songs
    MANAGE_LIST = auto()  # the albums, artists or lists, or every song
    MANAGE_ITEM = auto()  # one album, artist or list: delete all of it, or one of its songs
    MANAGE_CONFIRM = auto()  # "Keep it" or "Delete"


MANAGE_MODES = (Mode.MANAGE, Mode.MANAGE_LIST, Mode.MANAGE_ITEM, Mode.MANAGE_CONFIRM)
SETTINGS_MODES = (Mode.SETTINGS, Mode.WIFI, Mode.WIFI_SETUP, Mode.VOLUME_LIMIT, Mode.ABOUT) + MANAGE_MODES
LIST_MODES = (Mode.LINKING, Mode.LINK_START, Mode.MENU, Mode.TRACKS, Mode.SETTINGS, Mode.WIFI, Mode.VOLUME_LIMIT) + MANAGE_MODES


class NullStorage:
    """Stands in for the USB gadget until the real one exists."""

    def release(self) -> None:
        pass

    def reclaim(self) -> None:
        pass


class App:
    def __init__(self, library: Library, store: Store, playback, storage=None, volume_steps_per_rev: int = 60, ui=render, wifi=None):
        self.ui = ui  # render (the 320x240 colour screen) or ui.tiny (the 128x32 OLED)
        self.library = library
        self.store = store
        self.playback = playback
        self.storage = storage or NullStorage()
        self.wifi = wifi or wifi_mod.NoWifi()
        self.wifi.enabled = store.wifi  # main also switches the radio to match, at start-up
        self.web_address = ""  # where the web remote is, for the About screen; main fills it in
        self._about: list[str] = []
        self.mode = Mode.IDLE
        self.card: str | None = None
        self.album: Item | None = None  # what is playing: an album, an artist or a list
        self.link_kind: str | None = None  # while linking: the kind being browsed, None while choosing the kind
        self._link_to: Item | None = None  # while asking where it starts: what the card is being linked to
        self.status = Status()
        self.selected = 0
        self.note = ""
        self.usb_offer = False
        self.remote = False  # the album was started from the web remote, not by the card
        self.is_uploading = lambda: False  # replaced by main when the web remote is on
        # Deletes an album or list (key), or one of its files (name, relative to its folder); main fills it in.
        self.delete_music = None
        self.manage_kind: str | None = None  # album | artist | list | song, while managing music
        self.manage_item: Item | None = None  # the album, artist or list opened there
        self._confirm: tuple | None = None  # what Delete would remove: ("item", Item) or ("song", Track)
        self._confirm_back = (Mode.MANAGE_LIST, 0)  # where Keep it returns to
        self._entry_at = 0  # where the opened item was in its section's list
        self._now = 0.0
        self._volume_until = 0.0
        self._error = ""
        self._error_until = 0.0
        self._test_until = 0.0
        self.restart_requested = False  # main restarts the player once this is set
        self._art_from = None  # which file the cover on screen came from
        self._art: bytes | None = None
        self._vol_knob = volume_scaler(volume_steps_per_rev)
        self._list_knob = list_scaler()
        self._scan_forward: bool | None = None
        self._scan_start = self._scan_last = -1e9
        playback.set_volume(store.volume)

    # ---- events -------------------------------------------------------------

    def handle(self, event, now: float) -> None:
        self._now = now
        if self.mode is Mode.OFF:
            return  # nothing more happens once the player is turning off
        if isinstance(event, ev.Press) and event.button == "power":
            self._power_off()
        elif isinstance(event, ev.WebCommand) and event.action == "test_screen":
            self._test_until = now + TEST_SCREEN_SECONDS
        elif isinstance(event, ev.WebCommand) and event.action == "restart":
            self._restart()
        elif isinstance(event, ev.WebCommand):
            self._web(event.action, event.value)
        elif isinstance(event, ev.LibraryChanged):
            self._refresh_library()
        elif isinstance(event, ev.ListsChanged):
            self._refresh_library(rescan=False)
        elif isinstance(event, ev.CardInserted):
            self._end_wifi_setup()  # a card always wins over the settings
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
        self.wifi.tick()
        if self.mode is Mode.WIFI_SETUP and self.wifi.state in ("off", "closing"):
            self.mode = Mode.IDLE  # the setup network closed itself after nobody used it
        if self.album is None or self.mode in (Mode.TRANSFER, Mode.OFF):
            return
        was_active = self.status.state != "stop"
        self.status = self.playback.status()
        if was_active and self.status.state == "stop" and self.card and not self.remote:
            self.store.clear_resume(self.card)  # album played to the end

    def _rotate(self, counts: int, now: float) -> None:
        if self.mode in (Mode.TRANSFER, Mode.ABOUT, Mode.WIFI_SETUP) or self.usb_offer:
            return  # nowhere to show the volume on these screens, so do not change it unseen
        if self.mode in LIST_MODES:
            count = {
                Mode.LINKING: lambda: len(self._link_choices()),
                Mode.LINK_START: lambda: len(START_CHOICES),
                Mode.MENU: lambda: len(MENU_ITEMS),
                Mode.TRACKS: lambda: len(self.album.tracks),
                Mode.SETTINGS: lambda: len(SETTINGS_ITEMS),
                Mode.WIFI: lambda: len(self._wifi_items()),
                Mode.VOLUME_LIMIT: lambda: len(VOLUME_LIMITS),
                Mode.MANAGE: lambda: len(self._manage_kinds()) + 1,
                Mode.MANAGE_LIST: lambda: len(self._manage_entries()),
                Mode.MANAGE_ITEM: lambda: len(self._manage_rows()),
                Mode.MANAGE_CONFIRM: lambda: 2,
            }[self.mode]()
            steps = self._list_knob.feed(counts, now)
            self.selected = min(max(self.selected + steps, 0), max(count - 1, 0))
            return
        self._set_volume(self.store.volume + self._vol_knob.feed(counts, now))

    def _set_volume(self, volume: int) -> None:
        volume = min(max(int(volume), 0), self.store.max_volume)
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
        elif action == "play_at":
            album = self.library.get(str(value.get("key"))) if isinstance(value, dict) else None
            index = value.get("index") if album else None
            if album is None or not isinstance(index, int) or not 0 <= index < len(album.tracks):
                return
            if self.album is not None and album.key == self.album.key and self.status.state != "stop":
                self._play_track(index)  # a jump within what is playing keeps the card's claim on it
            else:
                self._play_remote(album, index)
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
            elif action == "seek" and self.status.state != "stop":
                self.playback.seek(min(max(float(value), 0.0), max(self.status.duration - 0.5, 0.0)))
                self.status = self.playback.status()

    def _play_remote(self, album: Item, track: int = 0) -> None:
        if self.album is not None and self.card and not self.remote:
            st = self.playback.status()  # keep the card's own place before taking over
            if st.state != "stop":
                self.store.set_resume(self.card, st.track_index, st.elapsed)
                self.store.save()
        self.remote = True
        self._play(album, track)

    def _refresh_library(self, rescan: bool = True) -> None:
        if rescan:
            self._rescan()
        else:
            self.library.refresh_playlists()
        if self.link_kind and not self.library.of(self.link_kind):
            self.link_kind = None
        if self.mode is Mode.LINKING:
            self.selected = min(self.selected, max(len(self._link_choices()) - 1, 0))
        if self.mode is Mode.LINK_START:
            self._link_to = self.library.get(self._link_to.key)
            if self._link_to is None:  # what was being linked has been deleted: choose again
                self._start_linking()
        if self.mode in MANAGE_MODES:
            self._manage_refresh()
        if self.album is None:
            return
        fresh = self.library.get(self.album.key)
        if fresh is not None:
            self.album = fresh  # same thing, possibly with tracks added or removed
            if self.mode is Mode.TRACKS:
                self.selected = min(self.selected, max(len(fresh.tracks) - 1, 0))
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
        if button == "back_long" and not (self.mode in (Mode.PLAYING, Mode.TRACKS) and self.album and not self.usb_offer):
            button = "back"  # holding back only means something while playing; elsewhere it is a slow back
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
        if self.mode in (Mode.PLAYING, Mode.TRACKS):
            # The transport buttons work the same with the track list open.
            if button == "play" or (button == "knob" and self.mode is Mode.PLAYING):
                self._toggle()
            elif button == "next":
                self.playback.next()
            elif button == "prev":
                self.playback.prev()
            elif button in ("next_hold", "prev_hold"):
                self._scan(button == "next_hold")
            elif button == "back_long":
                self._restart_album()
            elif self.mode is Mode.TRACKS:
                if button == "knob":
                    self._play_track(self.selected)
                elif button in ("back", "knob_long"):
                    self.mode = Mode.PLAYING
            elif button == "back":
                self._open_tracks()
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
                self._ask_start(self.library.of(self.link_kind)[self.selected])
            elif button == "back" and self.link_kind is not None:
                self._start_linking(self.link_kind)  # back to choosing the kind
            elif button == "back":
                self.mode = Mode.PLAYING if self.album else Mode.UNLINKED
        elif self.mode is Mode.LINK_START:
            if button == "knob":
                self._link(self._link_to, from_start=self.selected == 1)
            elif button == "back":
                self._browse(self.link_kind, self._link_to)  # back to the list, on what was chosen
        elif self.mode is Mode.UNLINKED:
            if button == "knob":
                self._start_linking()
        elif self.mode is Mode.IDLE:
            if button == "knob_long":
                self._open_list(Mode.SETTINGS, 0)
        elif self.mode in SETTINGS_MODES:
            self._settings_press(button)

    # ---- settings -----------------------------------------------------------

    def _settings_press(self, button: str) -> None:
        back = button in ("back", "knob_long")
        if self.mode in MANAGE_MODES:
            self._manage_press(button, back)
        elif self.mode is Mode.SETTINGS:
            if back:
                self.mode = Mode.IDLE
            elif button == "knob":
                self._settings_choice(self.selected)
        elif self.mode is Mode.WIFI:
            choice = self._wifi_items()[self.selected] if button == "knob" else None
            if back or choice == "Back":
                self._open_list(Mode.SETTINGS, 0)
            elif choice == "Wi-Fi":
                self.store.wifi = not self.store.wifi
                self.store.save()
                self.wifi.set_enabled(self.store.wifi)
            elif choice == "Connect to a new network":
                self.wifi.open_portal()
                self.mode = Mode.WIFI_SETUP
            elif choice == "Show web player":
                self.store.web_remote = not self.store.web_remote
                self.store.save()
        elif self.mode is Mode.VOLUME_LIMIT:
            if button == "knob":
                self._set_limit(VOLUME_LIMITS[self.selected])
            if button == "knob" or back:
                self._open_list(Mode.SETTINGS, SETTINGS_ITEMS.index("Volume limit"))
        elif self.mode is Mode.ABOUT:
            if button == "knob" or back:
                self._open_list(Mode.SETTINGS, SETTINGS_ITEMS.index("About this player"))
        elif self.mode is Mode.WIFI_SETUP:
            state = self.wifi.state
            if state in ("joined", "error") and (button == "knob" or back):
                self.wifi.close_portal()
                self._open_list(Mode.SETTINGS, 0)
            elif state in ("starting", "ready", "failed") and back:
                self.wifi.close_portal()  # back to the saved network
                self._open_list(Mode.WIFI, 1)  # on Connect to a new network, not the on/off switch
            # while joining nothing can be cancelled: the screen says it takes up to a minute

    def _settings_choice(self, index: int) -> None:
        choice = SETTINGS_ITEMS[index]
        if choice == "Wi-Fi":
            self._open_list(Mode.WIFI, 0)
        elif choice == "Volume limit":
            self._open_list(Mode.VOLUME_LIMIT, VOLUME_LIMITS.index(self.store.max_volume))
        elif choice == "Manage music":
            self._open_list(Mode.MANAGE, 0)
        elif choice == "About this player":
            self._about = self._about_lines()
            self.mode = Mode.ABOUT
        elif choice == "Restart the player":
            self._restart()
        else:
            self.mode = Mode.IDLE

    # ---- manage music: deleting from the player itself ------------------------

    def _manage_kinds(self) -> list[tuple[str, str]]:
        """The sections there is something in."""
        return [(k, name) for k, name in MANAGE_KINDS if (self.library.albums if k == "song" else self.library.of(k))]

    def _manage_entries(self) -> list:
        """The albums, artists or lists of the open section, or every song."""
        if self.manage_kind == "song":
            return [t for a in self.library.albums for t in a.tracks]
        return list(self.library.of(self.manage_kind)) if self.manage_kind else []

    def _manage_rows(self) -> list:
        """The open item's page: delete all of it (not a made list, which is not a folder), then its songs."""
        item = self.manage_item
        whole = [None] if item.kind == "artist" or item.folder is not None else []
        return whole + list(item.tracks)

    def _manage_press(self, button: str, back: bool) -> None:
        if self.mode is Mode.MANAGE:
            kinds = self._manage_kinds()
            if back or (button == "knob" and self.selected >= len(kinds)):
                self._open_list(Mode.SETTINGS, SETTINGS_ITEMS.index("Manage music"))
            elif button == "knob":
                self.manage_kind = kinds[self.selected][0]
                self._open_list(Mode.MANAGE_LIST, 0)
        elif self.mode is Mode.MANAGE_LIST:
            if back:
                kinds = [k for k, _ in self._manage_kinds()]
                self._open_list(Mode.MANAGE, kinds.index(self.manage_kind) if self.manage_kind in kinds else 0)
            elif button == "knob":
                entry = self._manage_entries()[self.selected]
                if self.manage_kind == "song":
                    self._ask_delete(("song", entry), (Mode.MANAGE_LIST, self.selected))
                else:
                    self.manage_item, self._entry_at = entry, self.selected
                    self._open_list(Mode.MANAGE_ITEM, 0)
        elif self.mode is Mode.MANAGE_ITEM:
            if back:
                self._back_to_entries()
            elif button == "knob":
                row = self._manage_rows()[self.selected]
                what = ("item", self.manage_item) if row is None else ("song", row)
                self._ask_delete(what, (Mode.MANAGE_ITEM, self.selected))
        elif self.mode is Mode.MANAGE_CONFIRM:
            if button == "knob" and self.selected == 1:
                self._delete_confirmed()
            elif button == "knob" or back:
                self._open_list(*self._confirm_back)

    def _manage_refresh(self) -> None:
        """Keeps the manage screens in step with a library that changed under them."""
        if self.manage_item is not None:
            self.manage_item = self.library.get(self.manage_item.key)
        if self.mode is Mode.MANAGE_ITEM and (self.manage_item is None or not self.manage_item.tracks):
            self._back_to_entries()
        if self.mode is Mode.MANAGE_LIST and not self._manage_entries():
            self._open_list(Mode.MANAGE, 0)
        count = {Mode.MANAGE: lambda: len(self._manage_kinds()) + 1, Mode.MANAGE_LIST: lambda: len(self._manage_entries()),
                 Mode.MANAGE_ITEM: lambda: len(self._manage_rows())}.get(self.mode)
        if count:
            self.selected = min(self.selected, max(count() - 1, 0))

    def _ask_delete(self, what: tuple, back: tuple) -> None:
        self._confirm, self._confirm_back = what, back
        self._open_list(Mode.MANAGE_CONFIRM, 0)  # Keep it comes first, so a stray push deletes nothing

    def _back_to_entries(self) -> None:
        entries = self._manage_entries()
        if not entries:
            self._open_list(Mode.MANAGE, 0)
            return
        at = entries.index(self.manage_item) if self.manage_item in entries else self._entry_at
        self.manage_item = None
        self._open_list(Mode.MANAGE_LIST, min(at, len(entries) - 1))

    def _delete_confirmed(self) -> None:
        kind, target = self._confirm
        self._confirm = None
        if self.delete_music is None:
            self.show_error("Deleting is not available on this player.", self._now)
            self._open_list(*self._confirm_back)
            return
        try:
            if kind == "song":
                album = self.library.album_of(target.path)
                if album is None or album.folder is None:
                    raise OSError("That song is no longer on the player.")
                self.delete_music(album.key, target.path[len(album.folder) + 1 :])
            elif target.kind == "artist":
                for album in self.library.albums_by(target):
                    self.delete_music(album.key, None)
            else:
                self.delete_music(target.key, None)
        except Exception as e:  # a read-only drive, a file already gone: say so and stay put
            self.show_error(f"Could not delete it. {getattr(e, 'message', None) or e}", self._now)
        # Back to where the deleted thing was listed; the refresh moves further back if that is gone too.
        self._open_list(*self._confirm_back)
        self._refresh_library()

    def _set_limit(self, limit: int) -> None:
        self.store.max_volume = limit
        if self.store.volume > limit:
            self.store.volume = limit
            self.playback.set_volume(limit)
        self.store.save()

    def _end_wifi_setup(self) -> None:
        if self.mode is Mode.WIFI_SETUP:
            self.wifi.close_portal()

    def _wifi_line(self) -> str:
        if not self.store.wifi:
            return "Off"
        network, bars = self.wifi.network(), self.wifi.bars()
        return f"{network} · {SIGNAL_WORDS[bars]}" if network and bars else "Not connected"

    def _wifi_items(self) -> list[str]:
        return [i for i in WIFI_ITEMS if self.store.wifi or i in ("Wi-Fi", "Back")]

    def _wifi_rows(self) -> list[tuple[str, str]]:
        subs = {
            "Wi-Fi": self.wifi.note or ("On" if self.store.wifi else "Off: the player does not connect"),
            "Connect to a new network": "Set it up from your phone",
            "Show web player": "Off: the web page is closed" if not self.store.web_remote else f"On: {self.web_address}" if self.web_address else "On",
            "Back": "",
        }
        values = {"Wi-Fi": self.store.wifi, "Show web player": self.store.web_remote}  # for the OLED, which shows no subtitles
        return [(i, subs[i], ("On" if values[i] else "Off") if i in values else "") for i in self._wifi_items()]

    def _about_lines(self) -> list[str]:
        """Worked out once when the screen opens: none of it changes while it is up."""
        connected = self.wifi.bars() is not None
        lines = [f"Wi-Fi: {self._wifi_line()}" if connected or not self.store.wifi else "Wi-Fi: not connected"]
        if connected and self.web_address and self.store.web_remote:
            lines.append(f"Web remote: {self.web_address}")
            address = wifi_mod.local_address()
            if address and address not in self.web_address:
                lines.append(f"or http://{address}")
        try:
            free = f" · {shutil.disk_usage(self.library.root).free / 1e9:.1f} GB free"
        except OSError:
            free = ""
        lines.append(f"{_count(len(self.library.albums), 'album')}{free}")
        return lines

    def _settings_screen(self):
        if self.mode is Mode.SETTINGS:
            limit = self.store.max_volume
            subs = (
                self._wifi_line(),
                "No limit" if limit == 100 else f"Up to {limit}",
                "Delete albums, artists, lists or songs",
                "Web address, music and storage",
                "",
                "",
            )
            return self.ui.list_screen("Settings", list(zip(SETTINGS_ITEMS, subs)), self.selected)
        if self.mode is Mode.WIFI:
            title = f"Wi-Fi: {self._wifi_line()}" if self.store.wifi else "Wi-Fi is off"
            return self.ui.list_screen(title, self._wifi_rows(), self.selected)
        if self.mode is Mode.VOLUME_LIMIT:
            rows = [("No limit" if v == 100 else f"Up to {v}", "Chosen now" if v == self.store.max_volume else "") for v in VOLUME_LIMITS]
            return self.ui.list_screen("Volume limit: the loudest it can go", rows, self.selected)
        if self.mode is Mode.ABOUT:
            return self.ui.message("About this player", "\n".join(self._about))
        if self.mode in MANAGE_MODES:
            return self._manage_screen()
        w = self.wifi
        if w.state == "starting":
            return self.ui.message("Starting Wi-Fi setup", "Looking for networks nearby…")
        if w.state in ("ready", "failed"):
            return self.ui.wifi_join(wifi_mod.SETUP_SSID, w.password, w.address(), w.message if w.state == "failed" else "")
        if w.state == "joining":
            return self.ui.message("Joining the network", "This can take up to a minute.")
        if w.state == "joined":
            where = f"\nThe web remote is at {self.web_address}." if self.web_address and self.store.web_remote else ""
            return self.ui.message(f"Connected to {w.joined}", f"{where}\nPush the knob to finish.".strip())
        if w.state == "error":
            return self.ui.message("Wi-Fi setup did not work", f"{w.message}\nPush the knob to go back.")
        return self.ui.message("Closing Wi-Fi setup")

    def _manage_screen(self):
        lib = self.library
        if self.mode is Mode.MANAGE:
            counts = {"album": len(lib.albums), "artist": len(lib.artists), "list": len(lib.lists), "song": sum(len(a.tracks) for a in lib.albums)}
            nouns = {"album": "album", "artist": "artist", "list": "list", "song": "song"}
            rows = [(name, _count(counts[k], nouns[k])) for k, name in self._manage_kinds()] + [("Back", "")]
            return self.ui.list_screen("Manage music" if lib.albums else "No music on the player", rows, self.selected)
        if self.mode is Mode.MANAGE_LIST:
            if self.manage_kind == "song":
                rows = [(t.title, " · ".join(filter(None, (t.artist, t.album)))) for t in self._manage_entries()]
                return self.ui.list_screen("Choose a song to delete", rows, self.selected)
            items = self._manage_entries()
            if self.manage_kind == "album":
                rows = [(a.title, a.artist) for a in items]
            elif self.manage_kind == "artist":
                rows = [(a.title, f"{_count(a.albums, 'album')} · {_count(len(a.tracks), 'track')}") for a in items]
            else:
                rows = [(a.title, _count(len(a.tracks), "track")) for a in items]
            return self.ui.list_screen(dict(MANAGE_KINDS)[self.manage_kind], rows, self.selected)
        if self.mode is Mode.MANAGE_ITEM:
            item, entries = self.manage_item, self._manage_rows()
            first = 0 if entries and entries[0] is None else 1  # song numbers start at 1 either way
            rows = []
            for i, row in enumerate(entries):
                if row is None:
                    noun = "all music by this artist" if item.kind == "artist" else f"whole {KIND_NAMES[item.kind][1]}"
                    rows.append((f"Delete {noun}", _count(len(item.tracks), "song")))
                else:
                    rows.append((f"{i + first}. {row.title}", "Push to delete this song"))
            return self.ui.list_screen(item.title, rows, self.selected)
        kind, target = self._confirm
        if kind == "song":
            name, what = target.title, "this song"
        elif target.kind == "artist":
            name, what = target.title, f"all {_count(len(target.tracks), 'song')}"
        else:
            name, what = target.title, f"this {KIND_NAMES[target.kind][1]}"
        rows = [("Keep it", ""), (f"Delete {what}", "This cannot be undone")]
        return self.ui.list_screen(f"Delete {name}?", rows, self.selected)

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

    def _restart_album(self) -> None:
        """Plays what is playing from the start of its first track."""
        if self.album.tracks:
            self.playback.play(self.album.tracks, 0)
            self.status = self.playback.status()
        self.mode = Mode.PLAYING

    def _scan(self, forward: bool) -> None:
        """One step of fast-forward or rewind; called repeatedly while the button is held."""
        st = self.playback.status()
        if st.state == "stop" or not st.duration:
            return
        now = self._now
        if forward != self._scan_forward or now - self._scan_last > SCAN_GAP:
            self._scan_start, step = now, SCAN_FIRST_STEP
        else:
            speed = SCAN_SPEEDS[1] if now - self._scan_start >= SCAN_FASTER_AFTER else SCAN_SPEEDS[0]
            step = speed * min(now - self._scan_last, SCAN_GAP)
        self._scan_forward, self._scan_last = forward, now
        target = st.elapsed + (step if forward else -step)
        if forward and target >= st.duration - 0.5:
            if st.track_index + 1 < st.track_count:
                self.playback.next()  # carry on scanning from the start of the next track
            else:
                self.playback.seek(st.duration - 0.5)
        else:
            self.playback.seek(max(target, 0.0))  # rewinding stops at the start of the track
        self.status = self.playback.status()

    def _open_tracks(self) -> None:
        if not self.album or not self.album.tracks:
            return
        st = self.playback.status()
        self._open_list(Mode.TRACKS, st.track_index if st.state != "stop" else 0)

    def _play_track(self, index: int) -> None:
        st = self.playback.status()
        if st.state != "stop" and index == st.track_index:
            if st.state == "pause":
                self.playback.resume()
        else:
            self.playback.play(self.album.tracks, index)
        self.status = self.playback.status()
        self.mode = Mode.PLAYING

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
        track, elapsed = (0, 0.0) if self.store.from_start(self.card) else self.store.resume_point(self.card)
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

    def _browse(self, kind: str, at: Item | None = None) -> None:
        items = self.library.of(kind)
        at = at or self.album
        self.link_kind = kind
        self._open_list(Mode.LINKING, items.index(at) if at in items else 0)

    def _ask_start(self, album: Item) -> None:
        """Asks whether the card carries on where it stopped (chosen first, the default) or starts over."""
        self._link_to = album
        linked = self.store.album_for(self.card) is not None
        self._open_list(Mode.LINK_START, 1 if linked and self.store.from_start(self.card) else 0)

    def _link(self, album: Item, from_start: bool | None = None) -> None:
        self.store.link(self.card, album.key, from_start)
        self._link_to = None
        self.remote = False
        self._play(album)

    def _menu_choice(self, index: int) -> None:
        choice = MENU_ITEMS[index]
        if choice == "Link to something else":
            self._start_linking()
        elif choice == "Always start over":
            self.store.set_from_start(self.card, not self.store.from_start(self.card))  # stays in the menu
        elif choice == "Unlink this card":
            self._unlink()
        else:
            self.mode = Mode.PLAYING

    def _menu_rows(self) -> list[tuple[str, str, str]]:
        on = self.store.from_start(self.card)
        subs = {"Always start over": "On: plays from the first song every time" if on else "Off: carries on where it left off"}
        values = {"Always start over": "On" if on else "Off"}  # for the OLED, which shows no subtitles
        return [(i, subs.get(i, ""), values.get(i, "")) for i in MENU_ITEMS]

    def _unlink(self) -> None:
        self.store.unlink(self.card)
        if self.remote:
            return  # something else is playing from the web page; leave it alone
        self.playback.stop()
        self.album, self.status = None, Status()
        self.mode, self.note = Mode.UNLINKED, "Card unlinked."

    def _power_off(self) -> None:
        """Saves the card's place and stops playback; main then shuts the Pi down."""
        if self.mode is Mode.TRANSFER:
            self.show_error("The music drive is connected to a computer. Eject it there first, then press power again.", self._now)
            return
        if self.is_uploading():
            self.show_error("An upload from the web page is still running. Try again when it finishes.", self._now)
            return
        self._end_wifi_setup()
        self._leave_card()  # remembers where the card stopped and saves the volume
        self.playback.stop()
        self.store.save()
        self.usb_offer = False
        self._error_until = 0.0  # nothing may cover the last screen
        self.mode = Mode.OFF

    def _restart(self) -> None:
        """Like turning off, but main starts the player again (to use new hardware settings)."""
        if self.mode is Mode.TRANSFER:
            self.show_error("The music drive is connected to a computer. Eject it there first, then restart.", self._now)
            return
        if self.is_uploading():
            self.show_error("An upload from the web page is still running. Try again when it finishes.", self._now)
            return
        self._end_wifi_setup()
        self._leave_card()  # the card picks up where it stopped once the player is back
        self.playback.stop()
        self.store.save()
        self.restart_requested = True

    def _start_transfer(self) -> None:
        self.usb_offer = False
        self._end_wifi_setup()
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
        self.ui.forget_covers()
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
            "linked": self.store.linked_keys(),
            "remote": self.remote,
            "volume": self.store.volume,
            "max_volume": self.store.max_volume,
            "wifi": {"bars": self.wifi.bars(), "network": self.wifi.network()},
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
        if self.mode is Mode.OFF:
            return self.ui.message("Turning off")  # stays up until the Pi is off; then the screen goes dark
        if self.restart_requested:
            return self.ui.message("Restarting")
        if now < self._test_until:
            return self.ui.test_pattern()
        if not self.store.wifi:
            return self._screen(now)  # switched off in the settings: no icon at all
        return self.ui.wifi_badge(self._screen(now), self.wifi.bars())

    def _screen(self, now: float):
        if now < self._error_until:
            return self.ui.message("Something went wrong", self._error)
        if self.mode is Mode.TRANSFER:
            return self.ui.message(
                "Transfer mode",
                "Copy music to the MUSIC drive, then eject it on your computer.\nOr hold the knob when finished.",
            )
        if self.usb_offer:
            return self.ui.message("Connected to a computer", "Push the knob to transfer music.\nBack to keep listening.")
        if self.mode is Mode.IDLE:
            return self.ui.message("Place a card", "to start playing")
        if self.mode in SETTINGS_MODES:
            return self._settings_screen()
        if self.mode is Mode.UNLINKED:
            prompt = "Push the knob to choose what it plays." if self.library.albums else ""
            return self.ui.message("Card not linked", f"{self.note}\n{prompt}".strip())
        if self.mode is Mode.LINKING and self.link_kind is None:
            rows = [(KIND_NAMES[k][0], _count(len(self.library.of(k)), KIND_NAMES[k][1])) for k in self._kinds()]
            return self.ui.list_screen("Link this card to", rows, self.selected)
        if self.mode is Mode.LINKING:
            items = self.library.of(self.link_kind)
            if self.link_kind == "album":
                rows = [(a.title, a.artist) for a in items]
            elif self.link_kind == "artist":
                rows = [(a.title, f"{_count(a.albums, 'album')} · {_count(len(a.tracks), 'track')}") for a in items]
            else:
                rows = [(a.title, _count(len(a.tracks), "track")) for a in items]
            article = "an" if self.link_kind[0] == "a" else "a"
            return self.ui.list_screen(f"Choose {article} {self.link_kind} for this card", rows, self.selected)
        if self.mode is Mode.LINK_START:
            return self.ui.list_screen("When the card goes back in", list(START_CHOICES), self.selected)
        if self.mode is Mode.MENU:
            return self.ui.list_screen(self.album.title, self._menu_rows(), self.selected)
        if self.mode is Mode.TRACKS:
            playing = self.status.track_index if self.status.state != "stop" else -1
            rows = []
            for i, t in enumerate(self.album.tracks):
                sub = t.artist if self.album.kind == "list" else t.album if self.album.kind == "artist" else ""
                rows.append((f"{i + 1}. {t.title}", "Playing now" if i == playing else sub))
            return self.ui.list_screen(self.album.title, rows, self.selected)
        volume = self.store.volume if now < self._volume_until else None
        scanning = now - self._scan_last < SCAN_LABEL_SECONDS
        note = ("Fast forward" if self._scan_forward else "Rewind") if scanning else None
        return self.ui.now_playing(self.album.title, self._details(), self._cover(), self.status, volume, note)
