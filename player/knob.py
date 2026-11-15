"""Turns raw counts from a detent-less encoder into steps that feel right.

Slow turns give fine single steps; fast spins are multiplied so a flick covers a lot.
The fractional remainder is kept, so no movement is ever lost between events.
"""

COUNTS_PER_REV = 256  # Bourns EM14: 64 pulses/rev, 4 edges per pulse


class KnobScaler:
    def __init__(
        self,
        counts_per_step: float,
        accel_max: float = 1.0,
        accel_start: float = 0.5 * COUNTS_PER_REV,  # counts/s where acceleration begins
        accel_full: float = 2.0 * COUNTS_PER_REV,  # counts/s where it reaches accel_max
    ):
        self.counts_per_step = counts_per_step
        self.accel_max = accel_max
        self.accel_start = accel_start
        self.accel_full = accel_full
        self._acc = 0.0
        self._speed = 0.0
        self._last = None

    def reset(self) -> None:
        self._acc, self._speed, self._last = 0.0, 0.0, None

    def feed(self, counts: int, now: float) -> int:
        """Returns whole steps (signed) produced by this movement."""
        if counts == 0:
            return 0
        dt = None if self._last is None else now - self._last
        self._last = now
        if dt is None or dt > 0.3:
            self._speed = 0.0  # a fresh gesture starts unaccelerated
        else:
            self._speed = 0.5 * self._speed + 0.5 * abs(counts) / max(dt, 0.005)
        if self._acc * counts < 0:
            self._acc = 0.0  # reversing direction: drop the leftover so it responds at once
        span = self.accel_full - self.accel_start
        t = min(max((self._speed - self.accel_start) / span, 0.0), 1.0)
        self._acc += counts * (1 + (self.accel_max - 1) * t)
        # The nudge stops rounding error turning an exact 2.0 into 1.999 and losing a step.
        steps = int(self._acc / self.counts_per_step + (1e-9 if self._acc > 0 else -1e-9))
        self._acc -= steps * self.counts_per_step
        return steps


def volume_scaler(steps_per_rev: int = 60) -> KnobScaler:
    # Fine steps when turned slowly, up to 3x when spun.
    return KnobScaler(COUNTS_PER_REV / steps_per_rev, accel_max=3.0)


def list_scaler() -> KnobScaler:
    # One list item per 15 degrees.
    return KnobScaler(COUNTS_PER_REV * 15 / 360)
