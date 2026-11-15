"""Draws the dimensioned SVGs from case.py, so they always match the STLs. Plain Python, no Blender.

    python3 drawings.py

Front-Panel.svg       the front as built, seen from the front, with the controls' positions
Rear-Panel.svg        the rear panel seen from behind, with the socket openings
Board-Stack.svg       a side section through the Pi, splitter and DAC stack, with heights
Brass-Front-Template.svg   the brass at actual size, to print at 100% and cut round

Every label sits outside the part, in its own row or column, so none can overlap.
"""

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import case as c  # noqa: E402

INK, DIM, FAINT = "#222826", "#5f6b66", "#a9b1ad"
CHARCOAL, BRASS, PAPER = "#3b403e", "#d4b06c", "#ffffff"
FONT = "font-family:system-ui,-apple-system,'Segoe UI',sans-serif"


def n(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


class Sheet:
    """An SVG in millimetres. Panel coordinates (x right, z up) map to the sheet with an origin."""

    def __init__(self, width, height, title):
        self.w, self.h, self.title, self.out = width, height, title, []
        self.ox, self.oy, self.top = 0.0, 0.0, 0.0  # sheet position of panel x = 0 and z = top

    def place(self, ox, oy, top):
        self.ox, self.oy, self.top = ox, oy, top

    def X(self, x):
        return self.ox + x

    def Y(self, z):
        return self.oy + (self.top - z)

    def poly(self, pts, fill, stroke=INK, sw=0.3, extra=""):
        d = " ".join(f"{n(self.X(x))},{n(self.Y(z))}" for x, z in pts)
        self.out.append(f'<polygon points="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" {extra}/>')

    def rect(self, x0, z0, x1, z1, fill, stroke=INK, sw=0.3, rx=0, extra=""):
        self.out.append(
            f'<rect x="{n(self.X(min(x0, x1)))}" y="{n(self.Y(max(z0, z1)))}" width="{n(abs(x1 - x0))}" height="{n(abs(z1 - z0))}" rx="{n(rx)}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" {extra}/>'
        )

    def circle(self, x, z, d, fill, stroke=INK, sw=0.3):
        self.out.append(f'<circle cx="{n(self.X(x))}" cy="{n(self.Y(z))}" r="{n(d / 2)}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')

    def line(self, x0, y0, x1, y1, colour=DIM, sw=0.2, extra=""):
        """Sheet coordinates."""
        self.out.append(f'<line x1="{n(x0)}" y1="{n(y0)}" x2="{n(x1)}" y2="{n(y1)}" stroke="{colour}" stroke-width="{sw}" {extra}/>')

    def text(self, x, y, s, size=3.0, anchor="middle", colour=INK, weight=400):
        """Sheet coordinates; y is the baseline."""
        s = s.replace("&", "&amp;").replace("<", "&lt;")
        self.out.append(f'<text x="{n(x)}" y="{n(y)}" font-size="{n(size)}" text-anchor="{anchor}" fill="{colour}" font-weight="{weight}" style="{FONT}">{s}</text>')

    def arrowhead(self, x, y, dx, dy, size=1.4):
        a = math.atan2(dy, dx)
        p = [(x, y), (x - size * math.cos(a) + size * 0.45 * math.sin(a), y - size * math.sin(a) - size * 0.45 * math.cos(a)), (x - size * math.cos(a) - size * 0.45 * math.sin(a), y - size * math.sin(a) + size * 0.45 * math.cos(a))]
        self.out.append(f'<polygon points="{" ".join(f"{n(px)},{n(py)}" for px, py in p)}" fill="{DIM}"/>')

    def hdim(self, x0, x1, row, label, reach):
        """A dimension between panel x0 and x1, drawn at sheet height row, with extension lines from sheet y reach."""
        a, b = self.X(x0), self.X(x1)
        for x in (a, b):
            self.line(x, reach, x, row + (1.2 if row > reach else -1.2), FAINT)
        self.line(a, row, b, row)
        self.arrowhead(a, row, -1, 0)
        self.arrowhead(b, row, 1, 0)
        self.text((a + b) / 2, row - 1.0, label)

    def vdim(self, z0, z1, col, label, reach):
        a, b = self.Y(z0), self.Y(z1)
        for y in (a, b):
            self.line(reach, y, col + (1.2 if col > reach else -1.2), y, FAINT)
        self.line(col, a, col, b)
        self.arrowhead(col, a, 0, 1)
        self.arrowhead(col, b, 0, -1)
        x = col + 1.5 if col > reach else col - 1.5
        self.out.append(f'<text x="{n(x)}" y="{n((a + b) / 2)}" font-size="3" text-anchor="middle" fill="{INK}" style="{FONT}" transform="rotate(-90 {n(x)} {n((a + b) / 2)})">{label}</text>')

    def ordinates_x(self, values, row, reach, below=True):
        """Distances from the panel's left edge, read off one baseline. Labels never overlap: close ones step down a row."""
        self.line(self.X(0), row, self.X(max(values)), row)
        last_end, level = -1e9, 0
        for v in sorted(values):
            x = self.X(v)
            self.line(x, reach, x, row, FAINT)
            self.line(x, row - 0.9, x, row + 0.9, INK, 0.25)
            label = n(v)
            half = len(label) * 0.95
            level = level + 1 if x - half < last_end + 0.8 and level == 0 else 0
            y = row + (4.0 + 3.6 * level if below else -1.6 - 3.6 * level)
            if level:
                self.line(x, row + 0.9, x, y - 2.6, FAINT, 0.15)
            self.text(x, y, label)
            last_end = x + half

    def ordinates_z(self, values, col, reach, side):
        """Heights above the panel's bottom edge, on a vertical baseline at sheet x col. side: -1 labels left, +1 right."""
        self.line(col, self.Y(0), col, self.Y(max(values)))
        for v in sorted(values):
            y = self.Y(v)
            self.line(reach, y, col, y, FAINT)
            self.line(col - 0.9, y, col + 0.9, y, INK, 0.25)
            self.text(col + side * 1.8, y + 1.05, n(v), anchor="start" if side > 0 else "end")

    def svg(self, extra_head=""):
        return "\n".join(
            [
                '<?xml version="1.0" encoding="UTF-8"?>',
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{n(self.w)}mm" height="{n(self.h)}mm" viewBox="0 0 {n(self.w)} {n(self.h)}">',
                f"<title>{self.title}</title>",
                f'<rect width="{n(self.w)}" height="{n(self.h)}" fill="{PAPER}"/>',
                extra_head,
                *self.out,
                "</svg>",
                "",
            ]
        )


# ---- front --------------------------------------------------------------------------
def front_panel():
    s = Sheet(c.W + 50, c.H + 52, "NFC Player front panel, seen from the front. Millimetres.")
    s.place(26, 16, c.H)
    s.poly(c.outline(), CHARCOAL)
    b = c.brass_shapes()
    s.poly(b["outline"], BRASS, stroke="#8a6a2e", sw=0.2)
    for x0, z0, x1, z1 in b["rects"][1:]:  # the switch slot shows the plastic plate behind it
        s.rect(x0, z0, x1, z1, CHARCOAL, stroke="#8a6a2e", sw=0.2)
    w, h = c.LCD_WINDOW
    s.rect(c.LCD_X - w / 2, c.CTRL_Z - h / 2, c.LCD_X + w / 2, c.CTRL_Z + h / 2, "#1d3138")
    for k in c.KEYS_X:
        s.rect(k - c.KEY_HOLE / 2, c.CTRL_Z - c.KEY_HOLE / 2, k + c.KEY_HOLE / 2, c.CTRL_Z + c.KEY_HOLE / 2, PAPER)
    s.circle(c.KNOB_X, c.CTRL_Z, c.ENCODER_HOLE, PAPER)
    s.circle(c.KNOB_X, c.CTRL_Z, c.KNOB_D, "none", stroke=DIM, sw=0.2)
    for x in c.SCREW_X:
        for z in c.SCREW_Z:
            s.circle(x, z, c.CLEAR_M3, PAPER)
            s.circle(x, z, 6.0, "none", stroke=DIM, sw=0.15)
    s.line(s.X(-3), s.Y(c.CTRL_Z), s.X(c.W + 3), s.Y(c.CTRL_Z), DIM, 0.15, 'stroke-dasharray="2 1 0.4 1"')
    s.hdim(0, c.W, s.Y(c.H) - 7, f"{n(c.W)}", s.Y(c.H) - 1)
    s.vdim(0, c.H, s.X(c.W) + 9, f"{n(c.H)}", s.X(c.W) + 1)
    s.ordinates_x([c.SCREW_X[0], c.LCD_X, *c.KEYS_X, c.KNOB_X, c.SCREW_X[1]], s.Y(0) + 7, s.Y(0) + 1)
    s.ordinates_z([c.SCREW_Z[0], c.CTRL_Z, c.SCREW_Z[1]], s.X(0) - 7, s.X(0) - 1, -1)
    s.text(s.X(0), s.h - 4, f"Centre line {n(c.CTRL_Z)}. Dashed circles: the {n(c.KNOB_D)} mm knob and 6 mm screw heads.", 2.8, "start", DIM)
    return s.svg()


# ---- rear ---------------------------------------------------------------------------
def rear_panel():
    s = Sheet(c.W + 50, c.H + 52, "NFC Player rear panel, seen from behind. Millimetres from its left edge as you look at it.")
    s.place(26, 16, c.H)
    u = lambda x: c.W - x
    s.poly(c.outline(), CHARCOAL)
    x0, x1, z0, z1 = c.RCA_WINDOW
    s.rect(u(x1), z0, u(x0), z1, PAPER)
    us = c.USB_SLOT
    s.rect(u(c.USB_X) - us[0] / 2, c.USB_Z - us[1] / 2, u(c.USB_X) + us[0] / 2, c.USB_Z + us[1] / 2, PAPER, rx=us[1] / 2)
    for d in (-1, 1):
        s.circle(u(c.USB_X) + d * c.USB_SCREW_PITCH / 2, c.USB_Z, c.CLEAR_M3, PAPER)
    for x in range(100, 171, 10):
        s.rect(u(x) - 5, 44, u(x), 47, PAPER)
    for x in c.SCREW_X:
        for z in c.SCREW_Z:
            s.circle(x, z, c.CLEAR_M3, PAPER)
    if c.REAR_JACK:
        s.circle(u(c.PHONES_X), c.PHONES_Z, c.PHONES_HOLE, PAPER)
    s.hdim(0, c.W, s.Y(c.H) - 7, f"{n(c.W)}", s.Y(c.H) - 1)
    s.vdim(0, c.H, s.X(c.W) + 9, f"{n(c.H)}", s.X(c.W) + 1)
    xs = [c.SCREW_X[0], u(c.USB_X), u(x1), u(x0), c.SCREW_X[1]] + ([u(c.PHONES_X)] if c.REAR_JACK else [])
    s.ordinates_x(xs, s.Y(0) + 7, s.Y(0) + 1)
    s.ordinates_z([c.USB_Z, z0, z1], s.X(0) - 7, s.X(0) - 1, -1)
    s.text(s.X(0), s.h - 4, f"Window {n(x1 - x0)} × {n(z1 - z0)} for the DAC's RCA and headphone sockets. USB-C slot {n(us[0])} × {n(us[1])}, screws {n(c.USB_SCREW_PITCH)} apart.", 2.8, "start", DIM)
    return s.svg()


# ---- board stack ---------------------------------------------------------------------
def board_stack():
    """Side section, seen from the left: front of the case on the left, rear on the right."""
    import importlib

    pz = c.FLOOR + c.STANDOFF_H
    split_z = pz + 1.6 + 11
    dac_z = split_z + 1.6 + 11
    pi_y, dac_y1 = 62.0, 62.0 + 56.5
    s = Sheet(c.D + 120, c.H + 30, "NFC Player: side section through the Pi, splitter and DAC stack, seen from the left. Millimetres.")
    s.place(60, 12, c.H)
    R = s.rect  # here x is depth from the front face (y), z is height
    R(0, 0, c.FRONT_T, c.H, "#e2e3df", FAINT)
    R(c.FRONT_T, 0, c.D - c.REAR_T, c.FLOOR, "#e2e3df", FAINT)
    R(c.D - c.REAR_T, 0, c.D, c.RCA_WINDOW[2], "#e2e3df", FAINT)
    R(c.D - c.REAR_T, c.RCA_WINDOW[3], c.D, c.H, "#e2e3df", FAINT)
    R(c.FRONT_T + 0.2, c.BODY_H, c.D - c.REAR_T - 0.2, c.H, "#e2e3df", FAINT)
    t0, t1 = c.TRAY[1] - 2, c.TRAY[3] + 2
    R(t0, c.BODY_H - (c.TRAY_DEPTH - c.LID_T) - c.TRAY_FLOOR, t1, c.BODY_H, "#e2e3df", FAINT)
    for y in (pi_y + 3.5, pi_y + 26.5):
        R(y - 2.5, c.FLOOR, y + 2.5, pz, "#c9c9c4")
    R(pi_y, pz, pi_y + 30, pz + 1.6, "#2f7a4a")
    R(pi_y + 1, pz + 1.6, pi_y + 6, split_z, "#1c1c1e")
    R(pi_y - 22, split_z, pi_y + 8, split_z + 1.6, "#6b4c95")
    R(pi_y - 20, split_z + 1.6, pi_y - 15, split_z + 10, "#1c1c1e")
    R(pi_y + 1, split_z + 1.6, pi_y + 6, dac_z, "#1c1c1e")
    R(pi_y, dac_z, dac_y1, dac_z + 1.6, "#1d5a35")
    R(dac_y1 - 12, dac_z + 1.6, dac_y1 + 2.5, dac_z + 14.1, "#1c1c1e")
    lcd_y = c.FRONT_T + c.LCD_GLASS
    R(lcd_y, c.CTRL_Z - 17.5, lcd_y + 1.6, c.CTRL_Z + 17.5, "#1f2f6e")
    R(c.FRONT_T + 0.1, c.CTRL_Z - 17.5, lcd_y, c.CTRL_Z + 17.5, "#16252b")

    def label(side, z_at, y_at, z_text, text):
        x_text = s.X(-6) if side < 0 else s.X(c.D + 6)
        s.line(s.X(y_at), s.Y(z_at), x_text - side * 0.8, s.Y(z_text) - 1.0, FAINT, 0.18)
        s.circle(y_at, z_at, 0.9, DIM, stroke="none")
        s.text(x_text, s.Y(z_text), text, 2.9, "end" if side < 0 else "start")

    def column(side, items):
        """items: (feature z, feature y, text). Spreads the text at least 4.6 mm apart, keeping order."""
        items = sorted(items, key=lambda i: -i[0])
        zs = [i[0] for i in items]
        for i in range(1, len(zs)):
            zs[i] = min(zs[i], zs[i - 1] - 4.6)
        for (z, y, text), zt in zip(items, zs):
            label(side, z, y, zt, text)

    column(1, [
        (c.H - 1.5, c.D - 12, f"Lid, {n(c.LID_T)} thick"),
        (c.BODY_H - 4, t1 - 2, f"Card tray, down to {n(c.BODY_H - 4)}"),
        (dac_z + 8, dac_y1 + 1, "DAC sockets, at the rear window"),
        (dac_z + 0.8, dac_y1 - 20, f"DAC board, underside at {n(dac_z)}"),
        (pz + 0.8, pi_y + 28, f"Pi, underside at {n(pz)}"),
        (pz - 2.5, pi_y + 26.5, f"Standoffs, {n(c.STANDOFF_H)} tall"),
        (c.FLOOR / 2, c.D - 25, f"Floor, {n(c.FLOOR)} thick"),
    ])
    column(-1, [
        (c.CTRL_Z + 12, lcd_y + 0.8, "Screen board"),
        (split_z + 6, pi_y - 17.5, "Splitter's spare header"),
        (split_z + 0.8, pi_y - 21, f"Splitter, underside at {n(split_z)}"),
        (pz + 6, pi_y + 3.5, "40-pin header"),
    ])
    s.text(s.X(0), s.Y(-9), "Front", 3, "start", DIM, 600)
    s.text(s.X(c.D), s.Y(-9), "Rear", 3, "end", DIM, 600)
    s.text(s.X(c.D / 2), s.Y(-9), "Header heights are nominal (11 mm per stacked header). Measure yours.", 2.6, "middle", DIM)
    return s.svg()


# ---- brass ------------------------------------------------------------------------
def brass_template():
    b = c.brass_shapes()
    xs = [p[0] for p in b["outline"]]
    zs = [p[1] for p in b["outline"]]
    s = Sheet(c.W + 20, c.H + 34, f"NFC Player brass face template. {n(c.BRASS_T)} mm brass. Print at 100% (actual size), seen from the front.")
    s.place(10 - min(xs) + c.RIM, 10, c.H)
    cut = "#000000"
    s.poly(b["outline"], "none", stroke=cut, sw=0.15)
    for x0, z0, x1, z1 in b["rects"]:
        s.rect(x0, z0, x1, z1, "none", stroke=cut, sw=0.15)
    for x, z, d in b["circles"]:
        s.circle(x, z, d, "none", stroke=cut, sw=0.15)
        s.line(s.X(x) - d, s.Y(z), s.X(x) + d, s.Y(z), FAINT, 0.1)  # centre marks for a punch
        s.line(s.X(x), s.Y(z) - d, s.X(x), s.Y(z) + d, FAINT, 0.1)
    s.text(s.X(c.W / 2), s.Y(c.CTRL_Z + 22), "FRONT FACE · cut on the black lines", 2.6, colour=FAINT)
    y = s.Y(min(zs)) + 9
    s.line(s.X(min(xs)), y, s.X(min(xs)) + 100, y, INK, 0.3)
    for k in range(11):
        s.line(s.X(min(xs)) + 10 * k, y - (1.5 if k % 5 == 0 else 0.8), s.X(min(xs)) + 10 * k, y, INK, 0.2)
    s.text(s.X(min(xs)) + 50, y + 4.5, "Check: this bar must measure exactly 100 mm", 2.8)
    s.text(s.X(max(xs)), y + 4.5, f"Outline {n(max(xs) - min(xs))} × {n(max(zs) - min(zs))} mm, {n(c.BRASS_GAP)} mm inside the pocket all round", 2.8, "end", DIM)
    return s.svg()


DRAWINGS = {
    "Front-Panel.svg": front_panel,
    "Rear-Panel.svg": rear_panel,
    "Board-Stack.svg": board_stack,
    "Brass-Front-Template.svg": brass_template,
}

if __name__ == "__main__":
    for name, make in DRAWINGS.items():
        (HERE / name).write_text(make())
        print("wrote", name)
