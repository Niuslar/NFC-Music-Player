"""Draws the dimensioned SVGs from case.py, so they always match the STLs. Plain Python, no Blender.

    python3 drawings.py

Front-Panel.svg       the front as built, seen from the front, with the controls' positions
Rear-Panel.svg        the rear panel seen from behind, with the socket openings
Board-Stack.svg       a side section through the Pi and DAC stack and the front board, with heights

Every label sits outside the part, in its own row or column, so none can overlap.
"""

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import case as c  # noqa: E402

INK, DIM, FAINT = "#222826", "#5f6b66", "#a9b1ad"
CHARCOAL, BLACK, SILVER, PAPER = "#3b403e", "#1f2221", "#c3c7ca", "#ffffff"
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
    s.poly(c.outline(), BLACK)
    for k in c.KEYS_X:  # the keys' holes, and the caps in them
        s.poly(c.key_square(k, c.CTRL_Z, c.KEY_HOLE), PAPER)
    w, h = c.LCD_WINDOW
    s.rect(c.LCD_X - w / 2, c.CTRL_Z - h / 2, c.LCD_X + w / 2, c.CTRL_Z + h / 2, "#1d3138")
    for k in c.KEYS_X:
        s.poly(c.key_square(k, c.CTRL_Z, c.KEY_CAP), SILVER)
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
    R(c.FRONT_T, bz0, c.FRONT_T + c.CARRIER_T, bz1, "#6d7370")  # the key carrier's frame
    R(c.FRONT_T + c.CARRIER_T, bz0, c.BOARD_Y, bz1, "#c9c9c4")  # the spacer
    R(c.BOARD_Y, bz0, c.BOARD_Y + c.BOARD_T, bz1, "#1d5a35")
    hb = c.BOARD_Y + c.BOARD_T
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
        (bz0 + 4, c.BOARD_Y + 0.8, f"Front board, on a {n(c.SPACER_T)} mm spacer and the {n(c.CARRIER_T)} mm key carrier, {n(bz0)}–{n(bz1)}"),
        (pz + 6, pi_y + 3.5, "40-pin header"),
    ])
    s.text(s.X(0), s.Y(-9), "Front", 3, "start", DIM, 600)
    s.text(s.X(c.D), s.Y(-9), "Rear", 3, "end", DIM, 600)
    s.text(s.X(c.D / 2), s.Y(-9), "Header heights are nominal (11 mm between the boards). Measure yours. Dashed: the ribbon.", 2.6, "middle", DIM)
    return s.svg()


# ---- controls ----------------------------------------------------------------------
# Nominal sizes of the bought parts in the section drawing. Check them against yours.
ENC_BODY = (13.4, 6.5)  # height, depth
ENC_THREAD = 5.0  # threaded bushing length
WASHER_T, NUT_T, NUT_W = 0.5, 2.0, 10.0
SHAFT = 15.0  # shaft beyond the bushing
KNOB_GAP, KNOB_DEPTH = 1.0, 16.0


def controls_section():
    """Two side sections, seen from the left (front of the case on the left): through a key, and through the encoder."""
    pocket_front = c.PANEL_AT_NUT  # y where the encoder pocket's floor is, from the front face
    K = 3.0  # drawn three times full size
    s = Sheet(268, 268, "NFC Player: sections through a key and through the volume encoder, seen from the left, three times full size. Millimetres.")
    PANEL, KNOB, PART = "#c9ccc8", SILVER, "#4a4f4d"

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
    for sgn in (-1, 1):
        def span(half):  # from the opening out to the edge of the drawing, on one side
            return sorted((c.CTRL_Z + sgn * half, c.CTRL_Z + sgn * 15))
        a, b = span(c.KEY_HOLE / 2)
        s.rect(0, a, c.FRONT_T, b, PANEL, DIM, 0.2)
        a, b = span(c.KEY_WIN_Z)
        s.rect(c.FRONT_T, a, c.FRONT_T + c.CARRIER_T, b, "#2b2f31", DIM, 0.2)  # the key carrier's frame
        s.rect(c.FRONT_T + c.CARRIER_T, a, c.BOARD_Y, b, "#dcdcd6", DIM, 0.2)  # the spacer
    s.rect(c.BOARD_Y, z0, c.BOARD_Y + c.BOARD_T, z1, "#1d5a35", DIM, 0.15)
    s.poly([(y, c.CTRL_Z + u) for y, u in cap_profile()], "#2b2f31")
    body = c.BOARD_Y - c.TACT_BODY_H
    s.rect(body, c.CTRL_Z - c.TACT / 2, c.BOARD_Y, c.CTRL_Z + c.TACT / 2, PART)
    s.rect(c.BOARD_Y - c.TACT_H, c.CTRL_Z - 1.75, body, c.CTRL_Z + 1.75, "#8e3b2e", "none")  # the button
    for u in (-2.25, 2.25):  # its legs, through the board
        s.rect(c.BOARD_Y, c.CTRL_Z + u - 0.35, c.BOARD_Y + c.BOARD_T + 1.0, c.CTRL_Z + u + 0.35, "#b9b7ad", DIM, 0.15)
    back = c.FRONT_T + c.CARRIER_T
    bridge = c.KEY_CAP / 2 + c.BRIDGE_GAP + c.BRIDGE_W / 2
    callouts(0, [
        (c.CTRL_Z + 5, 0.3, "Key cap, printed: face flush with the panel"),
        (c.CTRL_Z - bridge, back - c.BRIDGE_T / 2, f"Bridge, {n(c.BRIDGE_T)} thick: holds the cap and bends"),
    ], [
        (c.CTRL_Z + 12, c.FRONT_T - 1, "Front panel: its hole guides the cap"),
        (c.CTRL_Z + 13, c.FRONT_T + c.CARRIER_T / 2, f"Key carrier's frame, {n(c.CARRIER_T)}"),
        (c.CTRL_Z + 9.5, (back + c.BOARD_Y) / 2, f"Spacer, {n(c.SPACER_T)}, printed"),
        (c.CTRL_Z + 1.75, c.BOARD_Y - c.TACT_H, f"Button: {n(c.KEY_FREE)} mm from the cap, clicks after about {n(c.TACT_TRAVEL)} mm"),
        (c.CTRL_Z - 2, body + 1.5, f"Tactile switch, {n(c.TACT)} × {n(c.TACT)} × {n(c.TACT_H)} mm, in the cap's hollow"),
        (c.CTRL_Z - 10, c.BOARD_Y + c.BOARD_T / 2, f"Front board, {n(c.BOARD_T)}, switch soldered on"),
    ], s.X(-11), s.X(c.BOARD_Y + c.BOARD_T + 3))

    # ---- encoder ----
    s.place(132, 130, c.CTRL_Z + 20, K)
    s.text(8, 124, "Through the volume encoder", 4.6, "start", INK, 650)
    s.line(8, 116, s.w - 8, 116, FAINT, 0.2)
    z0, z1 = c.CTRL_Z - 19, c.CTRL_Z + 19
    eh, ph = c.ENCODER_HOLE / 2, c.ENCODER_BODY[1] / 2
    for a, b in ((z0, c.CTRL_Z - ph), (c.CTRL_Z + ph, z1)):
        s.rect(0, a, c.FRONT_T, b, PANEL, DIM, 0.2)
    for a, b in ((c.CTRL_Z - ph, c.CTRL_Z - eh), (c.CTRL_Z + eh, c.CTRL_Z + ph)):
        s.rect(0, a, pocket_front, b, PANEL, DIM, 0.2)
    bh = ENC_BODY[0] / 2
    s.rect(pocket_front, c.CTRL_Z - bh, pocket_front + ENC_BODY[1], c.CTRL_Z + bh, PART)
    s.rect(pocket_front + ENC_BODY[1], c.CTRL_Z - bh, pocket_front + ENC_BODY[1] + 3.5, c.CTRL_Z - bh + 0.7, "#b9b7ad", DIM, 0.15)
    s.rect(pocket_front - ENC_THREAD, c.CTRL_Z - 3.5, pocket_front, c.CTRL_Z + 3.5, "#9a9a94", DIM, 0.2)  # threaded bushing
    s.rect(-WASHER_T, c.CTRL_Z - 6, 0, c.CTRL_Z + 6, "#b9b7ad", DIM, 0.2)
    s.rect(-WASHER_T - NUT_T, c.CTRL_Z - NUT_W / 2, -WASHER_T, c.CTRL_Z + NUT_W / 2, "#9a9a94", DIM, 0.2)
    shaft_end = pocket_front - ENC_THREAD - SHAFT
    s.rect(shaft_end, c.CTRL_Z - 3, pocket_front - ENC_THREAD, c.CTRL_Z + 3, "#c8c8c2", DIM, 0.2)
    k0 = -WASHER_T - NUT_T - KNOB_GAP
    s.poly([(k0, c.CTRL_Z - c.KNOB_D / 2 + 1), (k0 - KNOB_DEPTH, c.CTRL_Z - c.KNOB_D / 2 + 1), (k0 - KNOB_DEPTH, c.CTRL_Z + c.KNOB_D / 2 - 1), (k0, c.CTRL_Z + c.KNOB_D / 2 - 1), (k0, c.CTRL_Z + 3.4), (shaft_end - 0.5, c.CTRL_Z + 3.4), (shaft_end - 0.5, c.CTRL_Z - 3.4), (k0, c.CTRL_Z - 3.4)], KNOB, "#7d8285", 0.25)
    s.rect(k0 - 9, c.CTRL_Z - c.KNOB_D / 2 + 1, k0 - 6, c.CTRL_Z - 3.4, "#4a4f52", "none")  # set screw
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
    s.text(s.w / 2, s.h - 3, f"Bought parts at nominal sizes. The nut clamps {n(c.PANEL_AT_NUT)} mm of panel between itself and the encoder body.", 3.3, "middle", DIM)
    return s.svg()


# ---- key close-up -----------------------------------------------------------------
def cap_profile():
    """A key cap and its two bridges, cut through its middle: (depth from the panel's face, offset
    across), round the outline. The cut runs through the tabs, so cap, tabs and bridges are one piece."""
    half, hollow = c.KEY_CAP / 2, c.KEY_HOLLOW / 2
    outer = half + c.BRIDGE_GAP + c.BRIDGE_W  # the far edge of a bridge
    face = -c.KEY_PROUD
    back = face + c.KEY_LENGTH
    ceiling = face + c.KEY_FACE_T
    tab = back - c.BRIDGE_T
    right = [(face, half), (tab, half), (tab, outer), (back, outer), (back, hollow), (ceiling, hollow)]
    return right + [(d, -u) for d, u in reversed(right)]


def key_closeup():
    """One key cut through its middle, front of the case at the top: pulled apart, then put together.

    Drawn with u across the key (sheet x) and d into the case from the panel's face (sheet y, down)."""
    K = 4.0
    W = 10.5  # half the width drawn
    body = c.BOARD_Y - c.TACT_BODY_H
    s = Sheet(360, 214, "NFC Player: close-up of one key cut through its middle, front of the case at the top, four times full size. Left: pulled apart in the order it goes together. Right: assembled. Millimetres.")
    PANEL, PART, PIN = "#c9ccc8", "#4a4f4d", "#b9b7ad"

    def R(u0, d0, u1, d1, fill, stroke=INK, sw=0.3, extra=""):
        s.rect(u0, -d0, u1, -d1, fill, stroke, sw, extra=extra)

    def panel():
        for sgn in (-1, 1):
            R(sgn * c.KEY_HOLE / 2, 0, sgn * W, c.FRONT_T, PANEL, DIM, 0.2)

    def spacer(o):
        for sgn in (-1, 1):
            R(sgn * c.KEY_WIN_Z, c.FRONT_T + c.CARRIER_T + o, sgn * W, c.BOARD_Y + o, "#dcdcd6", DIM, 0.2)

    def cap(o):  # the key carrier: the cap on its bridges, and the frame beyond them
        s.poly([(u, -(d + o)) for d, u in cap_profile()], "#2b2f31")
        for sgn in (-1, 1):
            R(sgn * c.KEY_WIN_Z, c.FRONT_T + o, sgn * W, c.FRONT_T + c.CARRIER_T + o, "#2b2f31", "none")

    def board(o):
        R(-W, c.BOARD_Y + o, W, c.BOARD_Y + c.BOARD_T + o, "#1d5a35", DIM, 0.15)
        R(-c.TACT / 2, body + o, c.TACT / 2, c.BOARD_Y + o, PART)
        R(-1.75, c.BOARD_Y - c.TACT_H + o, 1.75, body + o, "#8e3b2e", "none")  # the button
        for u in (-2.25, 2.25):  # legs through the board, soldered behind it
            R(u - 0.35, c.BOARD_Y + o, u + 0.35, c.BOARD_Y + c.BOARD_T + 1.0 + o, PIN, DIM, 0.15)
            R(u - 0.9, c.BOARD_Y + c.BOARD_T + o, u + 0.9, c.BOARD_Y + c.BOARD_T + 0.5 + o, "#c9c9c0", DIM, 0.1)

    def callouts(items, x_text, side):
        """items: (u, d, text) anchors. Labels stack in a column at sheet x x_text, never closer than 5.4."""
        items = sorted(items, key=lambda i: s.Y(-i[1]))
        ys = [s.Y(-d) for _, d, _ in items]
        for i in range(1, len(ys)):
            ys[i] = max(ys[i], ys[i - 1] + 5.4)
        for (u, d, text), y in zip(items, ys):
            s.line(s.X(u), s.Y(-d), x_text - side * 0.8, y - 1.0, FAINT, 0.18)
            s.circle(u, -d, 0.9 / K, DIM, stroke="none")
            s.text(x_text, y, text, 3.5, "start" if side > 0 else "end")

    def arrow(u, d0, d1, label):
        y0, y1 = s.Y(-d0), s.Y(-d1)
        s.line(s.X(u), y0, s.X(u), y1 - 1.6, "#d2452d", 0.5)
        s.out.append(f'<polygon points="{n(s.X(u))},{n(y1)} {n(s.X(u) - 1.3)},{n(y1 - 2.6)} {n(s.X(u) + 1.3)},{n(y1 - 2.6)}" fill="#d2452d"/>')
        s.text(s.X(u) + 2.2, (y0 + y1) / 2 + 1.2, label, 3.5, "start", "#b3361f", 650)

    # ---- pulled apart ----
    CAP, SP, BD = 8.0, 14.0, 20.0  # how far behind its place each part is drawn
    back = c.FRONT_T + c.CARRIER_T
    bridge = c.KEY_CAP / 2 + c.BRIDGE_GAP + c.BRIDGE_W / 2
    s.place(108, 22, 0, K)
    s.text(8, 8, "Pulled apart, in the order it goes together", 4.6, "start", INK, 650)
    panel()
    cap(CAP)
    spacer(SP)
    board(BD)
    face = -c.KEY_PROUD
    arrow(W + 1.5, face + CAP, face + 0.6, "1")  # each from its part's front to where that ends up
    arrow(W + 4.5, c.FRONT_T + SP, c.FRONT_T + 0.6, "2")
    arrow(W + 7.5, c.BOARD_Y - c.TACT_H + BD, c.BOARD_Y - c.TACT_H + 0.6, "3")
    callouts([
        (-c.KEY_CAP / 2, CAP + 1.5, "Key cap, printed"),
        (-bridge, back + CAP - c.BRIDGE_T / 2, "Bridge and tab"),
        (-W, c.FRONT_T + c.CARRIER_T / 2 + CAP, "Carrier's frame"),
        (-W, c.FRONT_T - 1, "Front panel"),
        (-W, (c.FRONT_T + c.BOARD_Y) / 2 + SP, "Spacer, printed"),
        (-c.TACT / 2, body + 1.5 + BD, "Tactile switch"),
        (-W, c.BOARD_Y + c.BOARD_T / 2 + BD, "Front board"),
        (-2.25, c.BOARD_Y + c.BOARD_T + 0.5 + BD, "Soldered from behind"),
    ], s.X(-W - 4), -1)
    steps = [
        "1  With the panel face down, lay the key carrier on it, caps into their holes and pegs into theirs.",
        "2  Lay the spacer on the carrier.",
        "3  Fit the board, switches towards the panel, with four M2 × 6 screws.",
    ]
    for i, t in enumerate(steps):
        s.text(8, s.h - 22 + 5.2 * i, t, 3.5, "start", INK)

    # ---- assembled ----
    ax = 232
    s.place(ax, 60, 0, K)
    s.text(ax - K * W, 8, "Put together", 4.6, "start", INK, 650)
    panel()
    spacer(0)
    board(0)
    cap(0)
    callouts([
        (c.KEY_CAP / 2 - 0.5, 0.1, "Face flush with the panel"),
        (bridge, back - c.BRIDGE_T / 2, f"Bridge, {n(c.BRIDGE_T)} thick: bends when pressed"),
        (W, c.FRONT_T + c.CARRIER_T / 2, f"Carrier's frame, {n(c.CARRIER_T)} mm, on the panel"),
        (1.75, c.BOARD_Y - c.TACT_H, f"{n(c.KEY_FREE)} mm to the button"),
        (c.TACT / 2, body + 1.5, "Switch inside the cap's hollow"),
        (W, (back + c.BOARD_Y) / 2, f"Spacer, {n(c.SPACER_T)} mm"),
        (W, c.BOARD_Y + c.BOARD_T / 2, "Board, held by four M2 screws"),
    ], s.X(W + 4), 1)
    hold = [
        "What holds what:",
        "• The bridges hold the cap centred in the panel's hole.",
        "• The switch clicks and pushes it back out.",
        "• The board's screws clamp the carrier and spacer to the panel.",
    ]
    for i, t in enumerate(hold):
        s.text(ax - K * W, s.Y(-(c.BOARD_Y + c.BOARD_T + 1.0)) + 16 + 5.2 * i, t, 3.5, "start", INK, 650 if i == 0 else 400)
    s.text(s.w / 2, s.h - 3, "Switch at nominal size; check yours. Cut through the middle of the key.", 3.0, "middle", DIM)
    return s.svg()


DRAWINGS = {
    "Front-Panel.svg": front_panel,
    "Rear-Panel.svg": rear_panel,
    "Board-Stack.svg": board_stack,
    "Controls-Section.svg": controls_section,
    "Key-Closeup.svg": key_closeup,
}

if __name__ == "__main__":
    for name, make in DRAWINGS.items():
        (HERE / name).write_text(make())
        print("wrote", name)
