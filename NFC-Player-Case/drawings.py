"""Draws the dimensioned SVGs from case.py, so they always match the STLs. Plain Python, no Blender.

    python3 drawings.py

Front-Panel.svg       the front as built, seen from the front, with the controls' positions
Rear-Panel.svg        the rear panel seen from behind, with the socket openings
Board-Stack.svg       a side section through the Pi and DAC stack and the front board, with heights
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
        self.ox, self.oy, self.top, self.k = 0.0, 0.0, 0.0, 1.0  # sheet position of panel x = 0 and z = top; scale

    def place(self, ox, oy, top, scale=1.0):
        self.ox, self.oy, self.top, self.k = ox, oy, top, scale

    def X(self, x):
        return self.ox + self.k * x

    def Y(self, z):
        return self.oy + self.k * (self.top - z)

    def poly(self, pts, fill, stroke=INK, sw=0.3, extra=""):
        d = " ".join(f"{n(self.X(x))},{n(self.Y(z))}" for x, z in pts)
        self.out.append(f'<polygon points="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" {extra}/>')

    def rect(self, x0, z0, x1, z1, fill, stroke=INK, sw=0.3, rx=0, extra=""):
        self.out.append(
            f'<rect x="{n(self.X(min(x0, x1)))}" y="{n(self.Y(max(z0, z1)))}" width="{n(self.k * abs(x1 - x0))}" height="{n(self.k * abs(z1 - z0))}" rx="{n(self.k * rx)}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" {extra}/>'
        )

    def circle(self, x, z, d, fill, stroke=INK, sw=0.3):
        self.out.append(f'<circle cx="{n(self.X(x))}" cy="{n(self.Y(z))}" r="{n(self.k * d / 2)}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')

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
    s.circle(c.POWER_X, c.CTRL_Z, c.POWER_HOLE, PAPER)
    for x in c.SCREW_X:
        for z in c.SCREW_Z:
            s.circle(x, z, c.CLEAR_M3, PAPER)
            s.circle(x, z, 6.0, "none", stroke=DIM, sw=0.15)
    s.line(s.X(-3), s.Y(c.CTRL_Z), s.X(c.W + 3), s.Y(c.CTRL_Z), DIM, 0.15, 'stroke-dasharray="2 1 0.4 1"')
    s.hdim(0, c.W, s.Y(c.H) - 7, f"{n(c.W)}", s.Y(c.H) - 1)
    s.vdim(0, c.H, s.X(c.W) + 9, f"{n(c.H)}", s.X(c.W) + 1)
    s.ordinates_x([c.SCREW_X[0], c.POWER_X, c.LCD_X, *c.KEYS_X, c.KNOB_X, c.SCREW_X[1]], s.Y(0) + 7, s.Y(0) + 1)
    s.ordinates_z([c.SCREW_Z[0], c.CTRL_Z, c.SCREW_Z[1]], s.X(0) - 7, s.X(0) - 1, -1)
    s.text(s.X(0), s.h - 4, f"Centre line {n(c.CTRL_Z)}. Power key hole {n(c.POWER_HOLE)}. Dashed circles: the {n(c.KNOB_D)} mm knob and 6 mm screw heads.", 2.8, "start", DIM)
    return s.svg()


# ---- rear ---------------------------------------------------------------------------
def rear_panel():
    s = Sheet(c.W + 50, c.H + 52, "NFC Player rear panel, seen from behind. Millimetres from its left edge as you look at it.")
    s.place(26, 16, c.H)
    u = lambda x: c.W - x
    s.poly(c.outline(), CHARCOAL)
    for name, x, z, d in c.DAC_JACKS:
        s.circle(u(x), z, d, PAPER)
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
    xs = [c.SCREW_X[0], u(c.USB_X), *[u(x) for name, x, z, d in c.DAC_JACKS], c.SCREW_X[1]] + ([u(c.PHONES_X)] if c.REAR_JACK else [])
    s.ordinates_x(xs, s.Y(0) + 7, s.Y(0) + 1)
    s.ordinates_z(sorted({c.USB_Z, *[z for name, x, z, d in c.DAC_JACKS]}), s.X(0) - 7, s.X(0) - 1, -1)
    s.text(s.X(0), s.h - 4, f"Holes Ø{n(c.DAC_JACKS[0][3])} for the DAC's RCA sockets, Ø{n(c.DAC_JACKS[2][3])} for its headphone socket. USB-C slot {n(us[0])} × {n(us[1])}, screws {n(c.USB_SCREW_PITCH)} apart.", 2.8, "start", DIM)
    return s.svg()


# ---- board stack ---------------------------------------------------------------------
def board_stack():
    """Side section, seen from the left: front of the case on the left, rear on the right."""
    import importlib

    pz = c.FLOOR + c.STANDOFF_H
    dac_z = pz + 1.6 + 11
    pi_y, dac_y1 = c.PI_Y, c.DAC_Y1
    plug_z = dac_z + 1.6 + 2.5
    s = Sheet(c.D + 120, c.H + 30, "NFC Player: side section through the Pi and DAC stack, with the front board behind the keys, seen from the left. Millimetres.")
    s.place(60, 12, c.H)
    R = s.rect  # here x is depth from the front face (y), z is height
    R(0, 0, c.FRONT_T, c.H, "#e2e3df", FAINT)
    R(c.FRONT_T, 0, c.D - c.REAR_T, c.FLOOR, "#e2e3df", FAINT)
    rca_z, rca_d = c.DAC_JACKS[0][2], c.DAC_JACKS[0][3]  # the section runs through an RCA socket's hole
    R(c.D - c.REAR_T, 0, c.D, rca_z - rca_d / 2, "#e2e3df", FAINT)
    R(c.D - c.REAR_T, rca_z + rca_d / 2, c.D, c.H, "#e2e3df", FAINT)
    R(c.FRONT_T + 0.2, c.BODY_H, c.D - c.REAR_T - 0.2, c.H, "#e2e3df", FAINT)
    t0, t1 = c.TRAY[1] - 2, c.TRAY[3] + 2
    R(t0, c.BODY_H - (c.TRAY_DEPTH - c.LID_T) - c.TRAY_FLOOR, t1, c.BODY_H, "#e2e3df", FAINT)
    for y in (pi_y + 3.5, pi_y + 26.5):
        R(y - 2.5, c.FLOOR, y + 2.5, pz, "#c9c9c4")
    R(pi_y, pz, pi_y + 30, pz + 1.6, "#2f7a4a")
    R(pi_y + 1, pz + 1.6, pi_y + 6, dac_z, "#1c1c1e")
    R(pi_y, dac_z, dac_y1, dac_z + 1.6, "#1d5a35")
    R(pi_y + 1, dac_z + 1.6, pi_y + 6, plug_z, "#9a9a94")  # the header's pins above the DAC
    R(pi_y - 1, plug_z, pi_y + 8, plug_z + 9, "#55595a")  # ribbon plug
    bz0, bz1 = c.BOARD_Z
    R(c.FRONT_T, bz0, c.FRONT_T + c.BOARD_T, bz1, "#1d5a35")
    hb = c.FRONT_T + c.BOARD_T
    R(hb, 41.0, hb + 9, 51.0, "#1c1c1e")  # 40-pin header on the board
    R(hb + 9, 41.0, hb + 18, 51.0, "#55595a")  # its ribbon plug
    ribbon = f"M {s.X(hb + 18)} {s.Y(46)} C {s.X(hb + 40)} {s.Y(46)} {s.X(pi_y + 3.5)} {s.Y(plug_z + 22)} {s.X(pi_y + 3.5)} {s.Y(plug_z + 9)}"
    s.out.append(f'<path d="{ribbon}" fill="none" stroke="#8d8f8c" stroke-width="1.2" stroke-dasharray="2 1"/>')
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
        (dac_z + 8, dac_y1 + 1, "DAC sockets, in holes in the rear panel"),
        (dac_z + 0.8, dac_y1 - 20, f"DAC board, underside at {n(dac_z)}"),
        (plug_z + 6, pi_y + 7, "Ribbon plug on the DAC's pins"),
        (pz + 0.8, pi_y + 28, f"Pi, underside at {n(pz)}"),
        (pz - 2.5, pi_y + 26.5, f"Standoffs, {n(c.STANDOFF_H)} tall"),
        (c.FLOOR / 2, c.D - 25, f"Floor, {n(c.FLOOR)} thick"),
    ])
    column(-1, [
        (51.0, hb + 13, "Ribbon plug on the board"),
        (c.CTRL_Z + 12, lcd_y + 0.8, "Screen board (nearer the left)"),
        (bz0 + 4, c.FRONT_T + 0.8, f"Front board, flat on the panel, {n(bz0)}–{n(bz1)}"),
        (pz + 6, pi_y + 3.5, "40-pin header"),
    ])
    s.text(s.X(0), s.Y(-9), "Front", 3, "start", DIM, 600)
    s.text(s.X(c.D), s.Y(-9), "Rear", 3, "end", DIM, 600)
    s.text(s.X(c.D / 2), s.Y(-9), "Header heights are nominal (11 mm between the boards). Measure yours. Dashed: the ribbon.", 2.6, "middle", DIM)
    return s.svg()


# ---- controls ----------------------------------------------------------------------
# Nominal sizes of the bought parts in the section drawing. Check them against yours.
CHOC_TOP = 2.8  # Choc V1 housing height in front of the plate
CHOC_BELOW = c.CHOC_BELOW_PLATE  # housing depth behind the plate
CHOC_TRAVEL = 3.0
KEYCAP_T = 2.5
ENC_BODY = (13.4, 6.5)  # height, depth
ENC_THREAD = 5.0  # threaded bushing length
WASHER_T, NUT_T, NUT_W = 0.5, 2.0, 10.0
SHAFT = 15.0  # shaft beyond the bushing
KNOB_GAP, KNOB_DEPTH = 1.0, 16.0


def controls_section():
    """Two side sections, seen from the left (front of the case on the left): through a key, and through the encoder."""
    back = c.FRONT_T - c.BRASS_T  # plastic behind the brass, measured from the inside face
    plate_front = c.BRASS_T  # y of the plate's front face (the back of the brass)
    plate_back = c.BRASS_T + c.KEY_PLATE
    pocket_front = c.FRONT_T - (back - c.PANEL_AT_NUT)  # y where the encoder pocket's floor is
    K = 3.0  # drawn three times full size
    s = Sheet(268, 268, "NFC Player: sections through a key and through the volume encoder, seen from the left, three times full size. Millimetres.")
    PANEL, BRASSC, PART = "#c9ccc8", BRASS, "#4a4f4d"

    def callouts(origin_y, items_left, items_right, x_left, x_right):
        for side, items in ((-1, items_left), (1, items_right)):
            items = sorted(items, key=lambda i: -i[0])
            zs = [i[0] for i in items]
            for i in range(1, len(zs)):
                zs[i] = min(zs[i], zs[i - 1] - 6.2 / K)
            for (z, y, text), zt in zip(items, zs):
                xt = x_left if side < 0 else x_right
                s.line(s.X(y), s.Y(z), xt - side * 0.8, s.Y(zt) - 1.0, FAINT, 0.18)
                s.circle(y, z, 0.9 / K, DIM, stroke="none")
                s.text(xt, s.Y(zt), text, 3.7, "end" if side < 0 else "start")

    # ---- key ----
    s.place(122, 14, c.CTRL_Z + 16, K)
    s.text(8, 8, "Through a key", 4.6, "start", INK, 650)
    z0, z1 = c.CTRL_Z - 15, c.CTRL_Z + 15
    hole, pocket, slot = c.KEY_HOLE / 2, 8.5, 8.25
    for a, b in ((z0, c.CTRL_Z - slot), (c.CTRL_Z + slot, z1)):
        s.rect(0, a, c.BRASS_T, b, BRASSC, "#8a6a2e", 0.2)
    for a, b in ((z0, c.CTRL_Z - pocket), (c.CTRL_Z + pocket, z1)):
        s.rect(plate_front, a, c.FRONT_T, b, PANEL, DIM, 0.2)
    for a, b in ((c.CTRL_Z - pocket, c.CTRL_Z - hole), (c.CTRL_Z + hole, c.CTRL_Z + pocket)):
        s.rect(plate_front, a, plate_back, b, PANEL, DIM, 0.2)
    top = plate_front - CHOC_TOP
    s.rect(top, c.CTRL_Z - 7.5, plate_front, c.CTRL_Z + 7.5, PART)  # top housing, sits on the plate
    bottom = plate_back + CHOC_BELOW  # underside of the switch = inside face of the panel
    s.rect(plate_front, c.CTRL_Z - 6.9, bottom, c.CTRL_Z + 6.9, PART)  # bottom housing
    for d in (-1, 1):  # the clips that catch the back of the plate
        s.poly([(plate_back, c.CTRL_Z + d * 6.9), (plate_back + 0.4, c.CTRL_Z + d * 7.6), (plate_back + 1.6, c.CTRL_Z + d * 6.9)], PART)
    s.rect(bottom, z0, bottom + c.BOARD_T, z1, "#1d5a35", DIM, 0.15)  # the front board, flat on the panel
    s.rect(bottom + c.BOARD_T, c.CTRL_Z - 7.25, bottom + c.BOARD_T + 1.85, c.CTRL_Z - 1.0, "#e9e6dc", DIM, 0.15)  # hot-swap socket
    s.rect(bottom, c.CTRL_Z - 6.5, bottom + 3.0, c.CTRL_Z - 5.3, "#b9b7ad", DIM, 0.15)  # switch pins
    s.rect(bottom, c.CTRL_Z - 4.4, bottom + 3.0, c.CTRL_Z - 3.2, "#b9b7ad", DIM, 0.15)
    s.rect(top - CHOC_TRAVEL, c.CTRL_Z - 1.5, top, c.CTRL_Z + 1.5, "#8e3b2e", "none")  # stem
    s.rect(top - CHOC_TRAVEL - KEYCAP_T, c.CTRL_Z - 8.25, top - CHOC_TRAVEL, c.CTRL_Z + 8.25, "#2b2f31")
    callouts(0, [
        (c.CTRL_Z + 8, top - CHOC_TRAVEL - KEYCAP_T, "Keycap (Choc V1 fit)"),
        (c.CTRL_Z + 1.5, top - CHOC_TRAVEL / 2, f"Stem: {n(CHOC_TRAVEL)} mm of travel"),
        (c.CTRL_Z - 6, top + 1, "Switch housing, in the brass slot"),
        (c.CTRL_Z - 11, c.BRASS_T / 2, f"Brass, {n(c.BRASS_T)}"),
    ], [
        (c.CTRL_Z + 12, c.FRONT_T, "Front panel"),
        (c.CTRL_Z + 7.3, plate_back + 0.4, f"Clips catch the back of the {n(c.KEY_PLATE)} mm plate"),
        (c.CTRL_Z + 10, bottom + c.BOARD_T / 2, f"Front board, {n(c.BOARD_T)}, flat on the panel"),
        (c.CTRL_Z - 4.5, bottom + c.BOARD_T + 1.85, "Pins plug into the hot-swap socket"),
        (c.CTRL_Z - 9, c.FRONT_T - 0.5, "Pocket: room for the clips"),
    ], s.X(-11), s.X(c.FRONT_T + 5))

    # ---- encoder ----
    s.place(132, 130, c.CTRL_Z + 20, K)
    s.text(8, 124, "Through the volume encoder", 4.6, "start", INK, 650)
    s.line(8, 116, s.w - 8, 116, FAINT, 0.2)
    z0, z1 = c.CTRL_Z - 19, c.CTRL_Z + 19
    eh, ph = c.ENCODER_HOLE / 2, c.ENCODER_BODY[1] / 2
    for a, b in ((z0, c.CTRL_Z - eh), (c.CTRL_Z + eh, z1)):
        s.rect(0, a, c.BRASS_T, b, BRASSC, "#8a6a2e", 0.2)
    for a, b in ((z0, c.CTRL_Z - ph), (c.CTRL_Z + ph, z1)):
        s.rect(plate_front, a, c.FRONT_T, b, PANEL, DIM, 0.2)
    for a, b in ((c.CTRL_Z - ph, c.CTRL_Z - eh), (c.CTRL_Z + eh, c.CTRL_Z + ph)):
        s.rect(plate_front, a, pocket_front, b, PANEL, DIM, 0.2)
    bh = ENC_BODY[0] / 2
    s.rect(pocket_front, c.CTRL_Z - bh, pocket_front + ENC_BODY[1], c.CTRL_Z + bh, PART)
    s.rect(pocket_front + ENC_BODY[1], c.CTRL_Z - bh, pocket_front + ENC_BODY[1] + 3.5, c.CTRL_Z - bh + 0.7, "#b9b7ad", DIM, 0.15)
    s.rect(pocket_front - ENC_THREAD, c.CTRL_Z - 3.5, pocket_front, c.CTRL_Z + 3.5, "#9a9a94", DIM, 0.2)  # threaded bushing
    s.rect(-WASHER_T, c.CTRL_Z - 6, 0, c.CTRL_Z + 6, "#b9b7ad", DIM, 0.2)
    s.rect(-WASHER_T - NUT_T, c.CTRL_Z - NUT_W / 2, -WASHER_T, c.CTRL_Z + NUT_W / 2, "#9a9a94", DIM, 0.2)
    shaft_end = pocket_front - ENC_THREAD - SHAFT
    s.rect(shaft_end, c.CTRL_Z - 3, pocket_front - ENC_THREAD, c.CTRL_Z + 3, "#c8c8c2", DIM, 0.2)
    k0 = -WASHER_T - NUT_T - KNOB_GAP
    s.poly([(k0, c.CTRL_Z - c.KNOB_D / 2 + 1), (k0 - KNOB_DEPTH, c.CTRL_Z - c.KNOB_D / 2 + 1), (k0 - KNOB_DEPTH, c.CTRL_Z + c.KNOB_D / 2 - 1), (k0, c.CTRL_Z + c.KNOB_D / 2 - 1), (k0, c.CTRL_Z + 3.4), (shaft_end - 0.5, c.CTRL_Z + 3.4), (shaft_end - 0.5, c.CTRL_Z - 3.4), (k0, c.CTRL_Z - 3.4)], BRASSC, "#8a6a2e", 0.25)
    s.rect(k0 - 9, c.CTRL_Z - c.KNOB_D / 2 + 1, k0 - 6, c.CTRL_Z - 3.4, "#6f5426", "none")  # set screw
    lug = pocket_front - 1.0
    s.rect(lug, c.CTRL_Z + 4.6, pocket_front, c.CTRL_Z + 5.6, "none", "#d2452d", 0.3, extra='stroke-dasharray="0.8 0.5"')
    callouts(0, [
        (c.CTRL_Z + 14, k0 - KNOB_DEPTH / 2, f"Knob, up to {n(c.KNOB_D)} mm"),
        (c.CTRL_Z - 12, k0 - 7.5, "Set screw onto the shaft's flat"),
        (c.CTRL_Z + 4.5, -WASHER_T - NUT_T / 2, "Nut"),
        (c.CTRL_Z - 5.5, -WASHER_T / 2, "Washer"),
    ], [
        (c.CTRL_Z + 16, c.FRONT_T, "Front panel"),
        (c.CTRL_Z + 5.1, lug + 0.5, "Locating lug, if fitted: nip it off"),
        (c.CTRL_Z + 0.5, pocket_front - 2.5, f"Threaded bushing, needs ≥ {n(ENC_THREAD)} mm"),
        (c.CTRL_Z - 4, pocket_front + ENC_BODY[1] / 2, "Body in the pocket: it cannot turn"),
        (c.CTRL_Z - 9, pocket_front + ENC_BODY[1] + 3, "Five pins, wired to the board's ENC header"),
    ], s.X(-21.5), s.X(c.FRONT_T + 5))
    s.text(s.w / 2, s.h - 3, "Bought parts at nominal sizes. The nut clamps brass and panel between itself and the encoder body.", 3.3, "middle", DIM)
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
    "Controls-Section.svg": controls_section,
    "Brass-Front-Template.svg": brass_template,
}

if __name__ == "__main__":
    for name, make in DRAWINGS.items():
        (HERE / name).write_text(make())
        print("wrote", name)
