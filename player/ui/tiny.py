"""The same screens as render.py, drawn for a 128x32 one-colour OLED.

Three short lines fit, so lists show three rows with the chosen one inverted,
and the cover is left out. Pixels are on or off: white means lit.
"""

from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

W, H = 128, 32
ON, OFF = 255, 0
ROW_H = 11
LINES = (0, 11, 22)  # top of each text line


@lru_cache(maxsize=None)
def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=size)


SMALL = 10
BIG = 11


def _canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("1", (W, H), OFF)
    d = ImageDraw.Draw(img)
    d.fontmode = "1"  # no grey edges on a screen that has none
    return img, d


def _fit(text: str, f, width: int) -> str:
    if f.getlength(text) <= width:
        return text
    while text and f.getlength(text + "…") > width:
        text = text[:-1]
    return text.rstrip() + "…"


def _clock(seconds: float) -> str:
    s = max(int(seconds), 0)
    return f"{s // 60}:{s % 60:02d}"


def forget_covers() -> None:
    """No covers on this screen."""


def _lines(text: str, f, width: int, max_lines: int) -> list[str]:
    out: list[str] = []
    for para in text.split("\n"):
        line = ""
        for word in para.split():
            trial = f"{line} {word}".strip()
            if f.getlength(trial) <= width or not line:
                line = trial
            else:
                out.append(line)
                line = word
        if line:
            out.append(line)
    if len(out) > max_lines:
        out = out[:max_lines]
        out[-1] = _fit(out[-1] + " …", f, width)
    return [_fit(line, f, width) for line in out]


def message(title: str, body: str = "") -> Image.Image:
    img, d = _canvas()
    body_lines = _lines(body, font(SMALL), W - 2, 2) if body else []
    top = max((H - ROW_H * (1 + len(body_lines))) // 2, 0)
    d.text((W // 2, top), _fit(title, font(BIG), W - 2), font=font(BIG), fill=ON, anchor="mt")
    for i, line in enumerate(body_lines):
        d.text((W // 2, top + ROW_H * (i + 1)), line, font=font(SMALL), fill=ON, anchor="mt")
    return img


def list_screen(header: str, rows: list[tuple[str, str]], selected: int) -> Image.Image:
    """Three rows; the header and subtitles do not fit and are left out."""
    img, d = _canvas()
    visible = len(LINES)
    top = min(max(selected - 1, 0), max(len(rows) - visible, 0))
    marker = len(rows) > visible
    text_w = W - 6 - (3 if marker else 0)
    for i, (title, _sub) in enumerate(rows[top : top + visible]):
        y = LINES[i]
        if top + i == selected:
            d.rectangle((0, y, W - (4 if marker else 1), y + ROW_H - 1), fill=ON)
            colour = OFF
        else:
            colour = ON
        d.text((3, y + ROW_H // 2), _fit(title, font(SMALL), text_w), font=font(SMALL), fill=colour, anchor="lm")
    if marker:  # scroll position, a thin bar on the right edge
        bar_h = max(H * visible // len(rows), 4)
        bar_y = (H - bar_h) * top // (len(rows) - visible)
        d.rectangle((W - 2, bar_y, W - 1, bar_y + bar_h - 1), fill=ON)
    return img


def now_playing(name: str, details: tuple[str, str], art: bytes | None, status, volume: int | None, note: str | None = None) -> Image.Image:
    """Track, then the album or artist line, then time and a progress (or volume) bar."""
    img, d = _canvas()
    finished = status.state == "stop"
    d.text((0, LINES[0]), _fit("Finished" if finished else status.title, font(BIG), W - 2), font=font(BIG), fill=ON)
    if finished:
        d.text((0, LINES[1]), "Push to play again", font=font(SMALL), fill=ON)
        return img
    d.text((0, LINES[1]), _fit(details[0], font(SMALL), W - 2), font=font(SMALL), fill=ON)

    y = LINES[2]
    if volume is not None:
        left, right, frac = "Vol", str(volume), volume / 100
    else:
        if note:
            left = ">>" if note == "Fast forward" else "<<"
        else:
            left = "Paused" if status.state == "pause" else _clock(status.elapsed)
        right = _clock(status.duration)
        frac = status.elapsed / status.duration if status.duration else 0
    d.text((0, y + 5), left, font=font(SMALL), fill=ON, anchor="lm")
    d.text((W, y + 5), right, font=font(SMALL), fill=ON, anchor="rm")
    x0 = max(int(font(SMALL).getlength(left)) + 4, 30)
    x1 = W - 1 - int(font(SMALL).getlength("00:00")) - 3
    d.rectangle((x0, y + 3, x1, y + 7), outline=ON)
    fill = int((x1 - x0 - 2) * min(max(frac, 0), 1))
    if fill > 0:
        d.rectangle((x0 + 1, y + 4, x0 + 1 + fill, y + 6), fill=ON)
    return img


def test_pattern() -> Image.Image:
    """A border, a checkerboard and the size: every edge pixel and the text should be visible."""
    img, d = _canvas()
    d.rectangle((0, 0, W - 1, H - 1), outline=ON)
    for y in range(2, H - 2, 4):
        for x in range(2, 30, 4):
            if (x // 4 + y // 4) % 2 == 0:
                d.rectangle((x, y, x + 3, y + 3), fill=ON)
    d.text((80, 9), "Screen test", font=font(BIG), fill=ON, anchor="mm")
    d.text((80, 22), "128 x 32", font=font(SMALL), fill=ON, anchor="mm")
    return img
