"""Generates a small royalty-free demo library (sine-tone WAVs and plain covers).

    python -m player.demo_library demo/music
"""

import math
import struct
import sys
import wave
from pathlib import Path

from PIL import Image, ImageDraw

ALBUMS = [
    ("Ada Hollis", "Low Tide Signals", (38, 84, 124), ["Harbour Lights", "Salt and Static", "Low Tide", "The Long Way Round"]),
    ("Ada Hollis", "Paper Lanterns", (190, 92, 60), ["Lanterns", "Kite String", "An Unreasonably Long Song Title For Testing Wrapping"]),
    ("Northern Quartet", "Slow Rooms", (64, 110, 82), ["Room One", "Room Two", "Room Three", "Room Four", "Room Five"]),
    ("Mika Tane", "Small Hours", (96, 72, 130), ["0300", "0415", "0530"]),
    ("The Copper Line", "Signal Box", (150, 120, 50), ["Up Main", "Down Relief", "Sidings"]),
    ("Yusuf Bell", "Field Notes", (60, 60, 66), ["Meadow", "Hedgerow", "Stream", "Dusk"]),
    ("", "Loose Album Without Artist", (120, 50, 70), ["One", "Two"]),
]
RATE = 22050


def _tone(path: Path, freq: float, seconds: float) -> None:
    frames = bytearray()
    total = int(RATE * seconds)
    for i in range(total):
        fade = min(i, total - i, RATE // 20) / (RATE // 20)  # no clicks at the ends
        frames += struct.pack("<h", int(6000 * fade * math.sin(2 * math.pi * freq * i / RATE)))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(frames))


def build(root: Path) -> None:
    for a, (artist, title, colour, tracks) in enumerate(ALBUMS):
        folder = root / artist / title if artist else root / title
        folder.mkdir(parents=True, exist_ok=True)
        cover = Image.new("RGB", (400, 400), colour)
        d = ImageDraw.Draw(cover)
        for r in range(40, 200, 32):
            d.ellipse((200 - r, 200 - r, 200 + r, 200 + r), outline=tuple(min(c + 40, 255) for c in colour), width=3)
        cover.save(folder / "cover.jpg", quality=85)
        for t, name in enumerate(tracks):
            _tone(folder / f"{t + 1:02d} {name}.wav", 220 * 2 ** ((a * 3 + t * 2) / 12), 20 + 5 * t)


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "demo/music")
    build(target)
    print(f"Demo library written to {target}")
