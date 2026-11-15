"""Knob and buttons on the Pi's GPIO pins.

The encoder is decoded on every edge with lgpio (fast, level comes with the
edge), and movement is sent on as one Rotate event every 20 ms.
"""

import threading
import time

from .. import events as ev
from ..knob import COUNTS_PER_REV

# Quadrature transitions: index is (previous AB << 2) | current AB.
_STEP = (0, -1, 1, 0, 1, 0, 0, -1, -1, 0, 0, 1, 0, 1, -1, 0)

ENCODERS = {
    # name: (pulses per revolution, use the Pi's pull-ups, debounce in microseconds)
    "pec11": (24, True, 800),  # clicky mechanical encoder, 24 clicks per turn, contacts to ground
    "em14": (64, False, 0),  # smooth optical encoder, driven outputs through 5 V -> 3.3 V dividers
}
# Volume steps per turn: two per click on the clicky one, so every click feels the same.
VOLUME_STEPS_PER_REV = {"pec11": 48, "em14": 60}


class Quadrature:
    """Pure decoder: feed pin levels, collect counts scaled to COUNTS_PER_REV."""

    def __init__(self, ppr: int, reverse: bool = False):
        self._scale = COUNTS_PER_REV / (4 * ppr) * (-1 if reverse else 1)
        self._state = 0
        self._edges = 0
        self._lock = threading.Lock()

    def update(self, a: int, b: int) -> None:
        state = (a << 1) | b
        with self._lock:
            self._edges += _STEP[(self._state << 2) | state]
            self._state = state

    def take(self) -> float:
        with self._lock:
            edges, self._edges = self._edges, 0
        return edges * self._scale


class Encoder:
    def __init__(self, event_queue, pin_a: int, pin_b: int, kind: str = "pec11", reverse: bool = False):
        import lgpio

        ppr, pull_up, debounce = ENCODERS[kind]
        self.queue = event_queue
        self.decoder = Quadrature(ppr, reverse)
        self._lg, self._pins = lgpio, (pin_a, pin_b)
        self._chip = lgpio.gpiochip_open(0)
        flags = lgpio.SET_PULL_UP if pull_up else lgpio.SET_PULL_NONE
        self._levels = {}
        self._callbacks = []
        for pin in self._pins:
            lgpio.gpio_claim_alert(self._chip, pin, lgpio.BOTH_EDGES, flags)
            if debounce:
                lgpio.gpio_set_debounce_micros(self._chip, pin, debounce)
            self._levels[pin] = lgpio.gpio_read(self._chip, pin)
            self._callbacks.append(lgpio.callback(self._chip, pin, lgpio.BOTH_EDGES, self._edge))
        self.decoder.update(self._levels[pin_a], self._levels[pin_b])
        self.decoder.take()
        threading.Thread(target=self._flush, daemon=True).start()

    def _edge(self, chip, pin, level, tick) -> None:
        if level in (0, 1):  # 2 is a watchdog timeout, not an edge
            self._levels[pin] = level
            self.decoder.update(self._levels[self._pins[0]], self._levels[self._pins[1]])

    def _flush(self) -> None:
        while True:
            time.sleep(0.02)
            counts = self.decoder.take()
            if counts:
                self.queue.put(ev.Rotate(counts))


class Buttons:
    """buttons maps a name (prev, play, next, back) to its GPIO; knob is the encoder's push switch."""

    def __init__(self, event_queue, knob_pin: int, buttons: dict[str, int], hold_seconds: float = 0.6):
        from gpiozero import Button

        self.queue = event_queue
        self._held = False
        self._devices = []
        knob = Button(knob_pin, pull_up=True, bounce_time=0.02, hold_time=hold_seconds)
        knob.when_held = self._knob_held
        knob.when_released = self._knob_released
        self._devices.append(knob)
        for name, pin in buttons.items():
            b = Button(pin, pull_up=True, bounce_time=0.02)
            b.when_pressed = lambda name=name: self.queue.put(ev.Press(name))
            self._devices.append(b)

    def _knob_held(self) -> None:
        self._held = True
        self.queue.put(ev.Press("knob_long"))

    def _knob_released(self) -> None:
        if not self._held:
            self.queue.put(ev.Press("knob"))
        self._held = False
