"""Checks the Setup page runs on a working player: a log of inputs, and a tone through the DAC."""

import io
import math
import re
import struct
import subprocess
import tempfile
import threading
import time
import wave
from collections import deque
from pathlib import Path

from .. import events as ev

MPD_CONF = Path("/etc/mpd.conf")


def describe(event) -> str | None:
    """A line for the input log, or None for events that are not from the controls or the reader."""
    if isinstance(event, ev.Press):
        return f"Button: {event.button}"
    if isinstance(event, ev.Rotate):
        return f"Knob: {'clockwise' if event.counts > 0 else 'anticlockwise'} {abs(event.counts):.0f}"
    if isinstance(event, ev.CardInserted):
        return f"Card in: {event.uid}"
    if isinstance(event, ev.CardRemoved):
        return "Card out"
    return None


class InputLog:
    """The last inputs, numbered so the page can ask for only the new ones. Thread-safe."""

    def __init__(self, size: int = 60):
        self._lock = threading.Lock()
        self._items: deque = deque(maxlen=size)
        self._seq = 0
        self.card: str | None = None

    def add(self, event, clock=time.time) -> None:
        text = describe(event)
        if text is None:
            return
        with self._lock:
            if isinstance(event, ev.CardInserted):
                self.card = event.uid
            elif isinstance(event, ev.CardRemoved):
                self.card = None
            if isinstance(event, ev.Rotate) and self._items and self._items[-1]["kind"] == "knob" and clock() - self._items[-1]["time"] < 0.5:
                # one turn arrives as many small events: keep it as one growing line
                last = self._items[-1]
                last["counts"] += event.counts
                c = last["counts"]
                last["text"] = f"Knob: {'clockwise' if c > 0 else 'anticlockwise'} {abs(c):.0f}"
                last["time"] = clock()
                self._seq += 1
                last["n"] = self._seq
                return
            self._seq += 1
            self._items.append(
                {"id": self._seq, "n": self._seq, "time": clock(), "text": text, "kind": "knob" if isinstance(event, ev.Rotate) else "other", "counts": getattr(event, "counts", 0)}
            )

    def since(self, after: int) -> dict:
        with self._lock:
            return {
                "seq": self._seq,
                "card": self.card,
                "items": [{"id": i["id"], "n": i["n"], "time": i["time"], "text": i["text"]} for i in self._items if i["n"] > after],
            }


def tone_wav(rate: int = 48000, level_db: float = -18.0) -> bytes:
    """A short tone in the left ear, then a higher one in the right, gently faded in and out."""
    amp = 32767 * 10 ** (level_db / 20)
    frames = bytearray()
    for freq, left in ((440, True), (660, False)):
        n = int(rate * 0.8)
        fade = int(rate * 0.03)
        for i in range(n):
            env = min(1.0, i / fade, (n - i) / fade)
            v = int(amp * env * math.sin(2 * math.pi * freq * i / rate))
            frames += struct.pack("<hh", v if left else 0, 0 if left else v)
        frames += bytes(4 * int(rate * 0.15))  # a short gap
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return buf.getvalue()


def mpd_device(conf: Path = MPD_CONF) -> str | None:
    """The ALSA device MPD plays to, from the config setup.sh wrote; None for the silent output."""
    try:
        text = conf.read_text()
    except OSError:
        return None
    m = re.search(r'device\s+"(hw:[^"]+)"', text)
    return m.group(1) if m else None


def dac_test(mpd_port: int = 6600, conf: Path = MPD_CONF, run=subprocess.run) -> dict:
    """Pauses playback, plays a tone straight to the DAC, then gives the DAC back to MPD."""
    device = mpd_device(conf)
    if device is None:
        return {"ok": False, "message": "MPD has no DAC to play to: setup.sh found no sound card. Fit the DAC, reboot and run setup.sh again."}
    cards = run(["aplay", "-l"], capture_output=True, text=True).stdout
    name = device.split("=", 1)[-1]
    if f"[{name}]" not in cards and f" {name} " not in cards:
        return {"ok": False, "message": f"The sound card {name} that MPD uses is not there. Is the DAC seated? Sound cards found:\n{cards.strip() or 'none'}"}

    from mpd import MPDClient

    client = MPDClient()
    client.timeout = 10
    client.connect("127.0.0.1", mpd_port)
    try:
        status = client.status()
        volume = status.get("volume", "?")
        paused = status.get("state") == "play"
        if paused:
            client.pause(1)
        enabled = [o["outputid"] for o in client.outputs() if o.get("outputenabled") == "1"]
        for oid in enabled:
            client.disableoutput(oid)  # MPD lets go of the DAC so the tone can use it
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav") as f:
                f.write(tone_wav())
                f.flush()
                done = run(["aplay", "-q", "-D", "plug" + device, f.name], capture_output=True, text=True, timeout=15)
        finally:
            for oid in enabled:
                client.enableoutput(oid)
    finally:
        client.close()
        client.disconnect()
    if done.returncode:
        return {"ok": False, "message": f"The tone could not be played on {name}: {done.stderr.strip()}"}
    note = " Playback was paused for the test." if paused else ""
    return {
        "ok": True,
        "message": f"Played a low tone on the left, then a higher one on the right, through {name} at volume {volume}.{note} "
        "Heard nothing? Turn the volume up and try again, and check the cable is in the DAC's output.",
    }
