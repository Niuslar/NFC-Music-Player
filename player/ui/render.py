"""Draws each screen as a 320x240 Pillow image. No hardware knowledge in here."""

import io
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

W, H = 320, 240
BG = (14, 14, 16)
FG = (240, 238, 232)
DIM = (150, 148, 142)
FAINT = (58, 57, 60)
ACCENT = (232, 163, 61)
PAD = 16
COVER = 124
ROW_H = 38
VISIBLE_ROWS = 5
BADGE_W = 26  # room kept clear in the top right corner for the Wi-Fi icon


@lru_cache(maxsize=None)
def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=size)


def _canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), BG)
    return img, ImageDraw.Draw(img)


def _fit(text: str, f, width: int) -> str:
    if f.getlength(text) <= width:
        return text
    while text and f.getlength(text + "…") > width:
        text = text[:-1]
    return text.rstrip() + "…"


def _wrap(text: str, f, width: int, max_lines: int) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        line = ""
        for word in para.split():
            trial = f"{line} {word}".strip()
            if f.getlength(trial) <= width or not line:
                line = trial
            else:
                lines.append(line)
                line = word
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = _fit(lines[-1] + " …", f, width)
    return [_fit(line, f, width) for line in lines]


def _clock(seconds: float) -> str:
    s = max(int(seconds), 0)
    return f"{s // 60}:{s % 60:02d}"


@lru_cache(maxsize=4)
def _cover(art: bytes | None, title: str) -> Image.Image:
    if art:
        try:
            img = Image.open(io.BytesIO(art)).convert("RGB")
            side = min(img.size)
            left, top = (img.width - side) // 2, (img.height - side) // 2
            return img.crop((left, top, left + side, top + side)).resize((COVER, COVER), Image.LANCZOS)
        except Exception:  # not an image Pillow can read: draw the placeholder
            pass
    img = Image.new("RGB", (COVER, COVER), FAINT)
    d = ImageDraw.Draw(img)
    d.text((COVER // 2, COVER // 2), (title[:1] or "?").upper(), font=font(56), fill=DIM, anchor="mm")
    return img


def forget_covers() -> None:
    """Call after the library changes on disk."""
    _cover.cache_clear()


def message(title: str, body: str = "") -> Image.Image:
    img, d = _canvas()
    body_lines = _wrap(body, font(16), W - 2 * PAD, 5) if body else []
    total = 30 + (12 + 22 * len(body_lines) if body_lines else 0)
    y = (H - total) // 2
    d.text((W // 2, y), _fit(title, font(24), W - 2 * PAD), font=font(24), fill=FG, anchor="mt")
    y += 42
    for line in body_lines:
        d.text((W // 2, y), line, font=font(16), fill=DIM, anchor="mt")
        y += 22
    return img


def list_screen(header: str, rows: list[tuple[str, str]], selected: int) -> Image.Image:
    """rows are (title, subtitle), or (title, subtitle, value); subtitle may be empty.

    value is a short state such as "On" for the OLED, which has no room for subtitles;
    here the subtitle says it already, so it is not drawn.
    """
    img, d = _canvas()
    d.text((PAD, 12), _fit(header, font(15), W - 2 * PAD - BADGE_W), font=font(15), fill=DIM)
    d.line((PAD, 38, W - PAD, 38), fill=FAINT)
    top = min(max(selected - VISIBLE_ROWS // 2, 0), max(len(rows) - VISIBLE_ROWS, 0))
    text_w = W - 2 * PAD - 20
    for i, (title, sub, *_value) in enumerate(rows[top : top + VISIBLE_ROWS]):
        y = 44 + i * ROW_H
        is_sel = top + i == selected
        if is_sel:
            d.rounded_rectangle((PAD - 8, y, W - PAD - 2, y + ROW_H - 4), radius=8, fill=ACCENT)
        main, minor = (BG, (70, 48, 14)) if is_sel else (FG, DIM)
        if sub:
            d.text((PAD, y + 2), _fit(title, font(16), text_w), font=font(16), fill=main)
            d.text((PAD, y + 19), _fit(sub, font(12), text_w), font=font(12), fill=minor)
        else:
            d.text((PAD, y + (ROW_H - 4) // 2), _fit(title, font(17), text_w), font=font(17), fill=main, anchor="lm")
    if len(rows) > VISIBLE_ROWS:  # scroll position marker
        track_h = VISIBLE_ROWS * ROW_H - 4
        bar_h = max(track_h * VISIBLE_ROWS // len(rows), 12)
        bar_y = 44 + (track_h - bar_h) * top // (len(rows) - VISIBLE_ROWS)
        d.rounded_rectangle((W - 7, bar_y, W - 4, bar_y + bar_h), radius=2, fill=FAINT)
    return img


def now_playing(name: str, details: tuple[str, str], art: bytes | None, status, volume: int | None, note: str | None = None) -> Image.Image:
    """details are the two lines under the track title; art is the cover's image data.

    volume is given only while the volume overlay should be visible; note replaces the
    track count under the progress bar (for "Fast forward" and "Rewind").
    """
    img, d = _canvas()
    img.paste(_cover(art, name), (PAD, PAD))
    x = PAD + COVER + 14
    col_w = W - PAD - x
    finished = status.state == "stop"
    title = "Finished" if finished else status.title
    y = PAD + 2
    for line in _wrap(title, font(20), col_w, 3):
        d.text((x, y), line, font=font(20), fill=FG)
        y += 25
    y += 6
    for line in _wrap(details[0], font(14), col_w, 2):
        d.text((x, y), line, font=font(14), fill=DIM)
        y += 18
    if details[1]:
        d.text((x, y), _fit(details[1], font(14), col_w), font=font(14), fill=DIM)

    bar_y = 176
    if volume is not None:
        d.text((PAD, bar_y - 26), "Volume", font=font(14), fill=DIM)
        d.text((W - PAD, bar_y - 26), str(volume), font=font(14), fill=FG, anchor="ra")
        frac, colour = volume / 100, FG
    else:
        frac = status.elapsed / status.duration if status.duration else 0
        colour = ACCENT
    d.rounded_rectangle((PAD, bar_y, W - PAD, bar_y + 5), radius=2, fill=FAINT)
    fill_w = int((W - 2 * PAD) * min(max(frac, 0), 1))
    if fill_w >= 4:
        d.rounded_rectangle((PAD, bar_y, PAD + fill_w, bar_y + 5), radius=2, fill=colour)

    y = bar_y + 18
    if finished:
        d.text((W // 2, y), "Push to play again", font=font(14), fill=DIM, anchor="mt")
        return img
    d.text((PAD, y), _clock(status.elapsed), font=font(14), fill=DIM)
    d.text((W - PAD, y), _clock(status.duration), font=font(14), fill=DIM, anchor="ra")
    if note:
        d.text((W // 2, y), note, font=font(14), fill=ACCENT, anchor="mt")
    elif status.state == "pause":
        d.text((W // 2, y), "Paused", font=font(14), fill=ACCENT, anchor="mt")
    else:
        d.text((W // 2, y), f"{status.track_index + 1} / {status.track_count}", font=font(14), fill=DIM, anchor="mt")
    return img


def test_pattern() -> Image.Image:
    """Colour bars, a white border and the size: every edge pixel and both colours of text should show."""
    img, d = _canvas()
    bars = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)]
    for i, colour in enumerate(bars):
        d.rectangle((i * W // 4, 0, (i + 1) * W // 4, H // 2), fill=colour)
    d.rectangle((0, 0, W - 1, H - 1), outline=(255, 255, 255))
    d.text((W // 2, H * 3 // 4 - 14), "Screen test", font=font(22), fill=FG, anchor="mm")
    d.text((W // 2, H * 3 // 4 + 16), "red · green · blue · white   320 x 240", font=font(14), fill=ACCENT, anchor="mm")
    return img


def splash() -> Image.Image:
    """The boot logo, shown from the moment the player starts until it can play a card."""
    img, d = _canvas()
    cx, cy = W // 2, 92
    # A card with the contactless waves coming off it.
    d.rounded_rectangle((cx - 72, cy - 30, cx + 8, cy + 30), radius=8, outline=FG, width=4)
    d.rectangle((cx - 58, cy - 14, cx - 38, cy + 2), fill=ACCENT)  # its chip
    for r in (18, 31, 44):
        d.arc((cx + 12 - r, cy - r, cx + 12 + r, cy + r), -50, 50, fill=ACCENT, width=5)
    d.text((W // 2, 160), "NFC Player", font=font(30), fill=FG, anchor="mt")
    d.text((W // 2, 202), "Starting…", font=font(16), fill=DIM, anchor="mt")
    return img


def wifi_badge(img: Image.Image, bars: int | None) -> Image.Image:
    """Draws the Wi-Fi signal in the top right corner: 1 to 4 lit parts, or struck through with no connection."""
    d = ImageDraw.Draw(img)
    cx, by = W - PAD - 12, 20  # the fan's point, at the bottom
    lit = FG if bars is not None else DIM
    for i, r in enumerate((0, 8, 12.5, 17)):
        colour = lit if bars is None or i < bars else FAINT
        if r == 0:
            d.ellipse((cx - 2, by - 5, cx + 2, by - 1), fill=colour)
        else:
            d.arc((cx - r, by - r, cx + r, by + r), 225, 315, fill=colour, width=2)
    if bars is None:
        d.line((cx - 11, by - 17, cx + 11, by), fill=BG, width=6)  # a gap either side of the stroke
        d.line((cx - 11, by - 17, cx + 11, by), fill=FG, width=2)
    return img


@lru_cache(maxsize=2)
def _qr(text: str, box: int) -> Image.Image | None:
    """A QR code a phone camera can join the network from, or None without the qrcode package."""
    try:
        import qrcode
    except ImportError:
        return None
    code = qrcode.QRCode(border=2, box_size=1, error_correction=qrcode.constants.ERROR_CORRECT_L)
    code.add_data(text)
    matrix = code.get_matrix()
    scale = max(box // len(matrix), 1)
    img = Image.new("RGB", (len(matrix) * scale, len(matrix) * scale), (255, 255, 255))
    d = ImageDraw.Draw(img)
    for y, row in enumerate(matrix):
        for x, dark in enumerate(row):
            if dark:
                d.rectangle((x * scale, y * scale, (x + 1) * scale - 1, (y + 1) * scale - 1), fill=(0, 0, 0))
    return img


def _qr_escape(text: str) -> str:
    return "".join("\\" + c if c in '\\;,:"' else c for c in text)


def wifi_join(ssid: str, password: str, address: str, note: str = "") -> Image.Image:
    """How to reach the setup page: join this network, then open this address. note is why the last try failed."""
    img, d = _canvas()
    qr = _qr(f"WIFI:T:WPA;S:{_qr_escape(ssid)};P:{_qr_escape(password)};;", 120)
    x = PAD
    if qr is not None:
        img.paste(qr, (PAD, (H - qr.height) // 2 - 12))
        x = PAD + qr.width + 14
    col_w = W - PAD - x
    y = 22
    d.text((x, y), "Join this Wi-Fi", font=font(14), fill=DIM)
    d.text((x, y + 18), _fit(ssid, font(17), col_w), font=font(17), fill=FG)
    d.text((x, y + 46), "Password", font=font(14), fill=DIM)
    d.text((x, y + 64), password, font=font(22), fill=ACCENT)
    d.text((x, y + 100), "Then open", font=font(14), fill=DIM)
    d.text((x, y + 118), _fit(address, font(17), col_w), font=font(17), fill=FG)
    lines = _wrap(note or "Back to cancel", font(14), W - 2 * PAD, 2)
    for i, line in enumerate(lines):
        d.text((W // 2, H - 14 - 18 * (len(lines) - i)), line, font=font(14), fill=DIM, anchor="mt")
    return img
