"""Events that hardware drivers (real or simulated) put on the app's queue."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CardInserted:
    uid: str


@dataclass(frozen=True)
class CardRemoved:
    pass


@dataclass(frozen=True)
class Rotate:
    """Raw encoder counts since the last event; positive is clockwise."""

    counts: int


@dataclass(frozen=True)
class Press:
    """button is one of: knob, knob_long, prev, play, next, back, prev_hold, next_hold.

    prev_hold and next_hold repeat for as long as the button is held.
    """

    button: str


@dataclass(frozen=True)
class UsbHost:
    """A computer (not a charger) started or stopped talking to the USB port."""

    connected: bool


@dataclass(frozen=True)
class UsbEjected:
    """The computer ejected the music drive."""


@dataclass(frozen=True)
class WebCommand:
    """From the web remote. action: toggle, next, prev, volume (value 0-100), play_album, link_card (value = album path), unlink_card."""

    action: str
    value: object = None


@dataclass(frozen=True)
class LibraryChanged:
    """Files on the music drive changed (an upload finished)."""
