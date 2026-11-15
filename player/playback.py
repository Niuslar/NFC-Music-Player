"""Playback backends. The app only talks to the methods FakePlayback and MpdPlayback share."""

import time
from dataclasses import dataclass
from pathlib import PurePosixPath

from .library import UNKNOWN_DURATION, Library, _track_title


@dataclass(frozen=True)
class Status:
    state: str = "stop"  # play | pause | stop
    track_index: int = 0
    track_count: int = 0
    title: str = ""
    elapsed: float = 0.0
    duration: float = 0.0


class FakePlayback:
    """Silent player that keeps time. Used by tests and by the simulator when MPD is absent."""

    def __init__(self, library: Library, clock=time.monotonic):
        self.library = library
        self.clock = clock
        self.volume = 0
        self._tracks = ()
        self._durations: list[float] = []
        self._index = 0
        self._state = "stop"
        self._elapsed = 0.0  # elapsed at _since
        self._since = 0.0

    def _now_elapsed(self) -> float:
        if self._state == "play":
            return self._elapsed + (self.clock() - self._since)
        return self._elapsed

    def _settle(self) -> None:
        """Advance through tracks that finished since we last looked."""
        while self._state == "play":
            elapsed = self._now_elapsed()
            dur = self._durations[self._index]
            if elapsed < dur:
                break
            if self._index + 1 >= len(self._tracks):
                self._state, self._index, self._elapsed = "stop", 0, 0.0
                break
            self._index += 1
            self._elapsed = elapsed - dur
            self._since = self.clock()

    def play_album(self, album_path: str, track: int = 0, elapsed: float = 0.0) -> None:
        album = self.library.get(album_path)
        if album is None:
            self.stop()
            return
        self._tracks = album.tracks
        self._durations = [self.library.duration(t) or UNKNOWN_DURATION for t in album.tracks]
        self._index = min(max(track, 0), len(self._tracks) - 1)
        self._elapsed, self._since, self._state = elapsed, self.clock(), "play"

    def pause(self) -> None:
        self._settle()
        if self._state == "play":
            self._elapsed, self._state = self._now_elapsed(), "pause"

    def resume(self) -> None:
        if self._state == "pause":
            self._since, self._state = self.clock(), "play"

    def stop(self) -> None:
        self._state, self._index, self._elapsed = "stop", 0, 0.0

    def _jump(self, index: int) -> None:
        self._index, self._elapsed, self._since = index, 0.0, self.clock()

    def next(self) -> None:
        self._settle()
        if self._state != "stop" and self._index + 1 < len(self._tracks):
            self._jump(self._index + 1)

    def prev(self) -> None:
        self._settle()
        if self._state == "stop":
            return
        restart = self._now_elapsed() > 3 or self._index == 0
        self._jump(self._index if restart else self._index - 1)

    def set_volume(self, volume: int) -> None:
        self.volume = volume

    def rescan(self) -> None:
        pass

    def status(self) -> Status:
        self._settle()
        if self._state == "stop" or not self._tracks:
            return Status(track_count=len(self._tracks))
        return Status(
            state=self._state,
            track_index=self._index,
            track_count=len(self._tracks),
            title=self._tracks[self._index].title,
            elapsed=self._now_elapsed(),
            duration=self._durations[self._index],
        )


class MpdPlayback:
    """Talks to an MPD daemon whose music_directory is the library root."""

    def __init__(self, host: str = "localhost", port: int = 6600):
        from mpd import MPDClient

        self._host, self._port = host, port
        self._client = MPDClient()
        self._client.timeout = 5
        self._connected = False
        self.volume = None
        self._volume_refused = False

    def _call(self, fn):
        from mpd import ConnectionError as MpdConnectionError

        for attempt in (0, 1):
            try:
                if not self._connected:
                    self._client.connect(self._host, self._port)
                    self._connected = True
                return fn(self._client)
            except (MpdConnectionError, OSError):
                self._connected = False
                try:
                    self._client.disconnect()
                except Exception:
                    pass
                if attempt:
                    raise

    def play_album(self, album_path: str, track: int = 0, elapsed: float = 0.0) -> None:
        def go(c):
            c.clear()
            c.add(album_path)
            if elapsed > 1:
                c.seek(track, elapsed)  # starts playback at that point; seekcur fails before decoding begins
            else:
                c.play(track)

        self._call(go)
        if self._volume_refused and self.volume is not None:
            self.set_volume(self.volume)  # the mixer may exist now that an output is open

    def pause(self) -> None:
        self._call(lambda c: c.pause(1))

    def resume(self) -> None:
        self._call(lambda c: c.pause(0))

    def stop(self) -> None:
        self._call(lambda c: c.stop())

    def next(self) -> None:
        def go(c):
            st = c.status()
            if int(st.get("song", 0)) + 1 < int(st.get("playlistlength", 0)):
                c.next()

        self._call(go)

    def prev(self) -> None:
        def go(c):
            st = c.status()
            if float(st.get("elapsed", 0)) > 3 or int(st.get("song", 0)) == 0:
                c.seekcur(0)
            else:
                c.previous()

        self._call(go)

    def set_volume(self, volume: int) -> None:
        from mpd import CommandError

        self.volume = volume
        try:
            self._call(lambda c: c.setvol(volume))
            self._volume_refused = False
        except CommandError as e:
            # No DAC (or no mixer) yet: carry on, and try again when playback next starts.
            if not self._volume_refused:
                print(f"MPD would not set the volume ({e}); continuing without it", flush=True)
            self._volume_refused = True

    def rescan(self, timeout: float = 120.0) -> None:
        """Update MPD's database and wait for it, so albums can be queued straight after."""
        self._call(lambda c: c.update())
        deadline = time.monotonic() + timeout
        while "updating_db" in self._call(lambda c: c.status()) and time.monotonic() < deadline:
            time.sleep(0.1)

    def status(self) -> Status:
        st, song = self._call(lambda c: (c.status(), c.currentsong()))
        state = st.get("state", "stop")
        if state == "stop":
            return Status(track_count=int(st.get("playlistlength", 0)))
        title = song.get("title") or _track_title(PurePosixPath(song.get("file", "")).stem)
        return Status(
            state=state,
            track_index=int(st.get("song", 0)),
            track_count=int(st.get("playlistlength", 0)),
            title=title if isinstance(title, str) else title[0],
            elapsed=float(st.get("elapsed", 0)),
            duration=float(st.get("duration", 0)),
        )
