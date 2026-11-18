"""Which parts this player is built from, saved in a small JSON file next to the card links.

The web remote's Setup page edits it; the player reads it at start-up, so a change
takes effect after a restart. Command-line options, when given, win over the file.
"""

import json
import os
from pathlib import Path

DISPLAYS = {
    "st7789": "2-inch colour LCD, ST7789 over SPI, 320×240",
    "ssd1306": "0.91-inch OLED, SSD1306 over I2C, 128×32",
}
ENCODERS = {
    "pec11": "Clicky, 24 clicks per turn (PEC11 or similar)",
    "em14": "Smooth optical, 64 pulses per turn (Bourns EM14)",
}
ROTATIONS = (0, 180)
DEFAULTS = {"display": "st7789", "encoder": "pec11", "encoder_reverse": False, "rotate": 0}


def clean(raw: dict) -> dict:
    """Returns a full, valid config from raw; raises ValueError naming the first bad value."""
    out = dict(DEFAULTS)
    for key, value in raw.items():
        if key == "display" and value in DISPLAYS:
            out[key] = value
        elif key == "encoder" and value in ENCODERS:
            out[key] = value
        elif key == "encoder_reverse" and isinstance(value, bool):
            out[key] = value
        elif key == "rotate" and value in ROTATIONS and not isinstance(value, bool):
            out[key] = value
        elif key in DEFAULTS:
            raise ValueError(f"{value!r} is not a valid {key}")
        # unknown keys are dropped, so an older file never stops the player starting
    return out


def load(path: Path) -> dict:
    """The saved config, or the defaults when the file is missing or unreadable."""
    try:
        raw = json.loads(Path(path).read_text())
        if not isinstance(raw, dict):
            raise ValueError
        return clean({k: v for k, v in raw.items() if k in DEFAULTS})
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save(path: Path, config: dict) -> dict:
    config = clean(config)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.part")
    temp.write_text(json.dumps(config, indent=2) + "\n")
    os.replace(temp, path)
    return config


def choices() -> dict:
    """What the Setup page offers."""
    return {"display": DISPLAYS, "encoder": ENCODERS, "rotate": list(ROTATIONS)}
