"""NFC Player Case v3: the one source of truth for every dimension. Millimetres throughout.

This file only describes shapes. build.py turns them into STLs with Blender and
writes the OpenSCAD copy and the brass template, so all three always agree:

    /Applications/Blender.app/Contents/MacOS/Blender -b -P build.py

Axes: x across the front (0 = left), y front to back (0 = front face), z up (0 = underside).

MEASURE FIRST. The values marked MEASURE depend on the exact parts you bought and
could not be confirmed from published drawings. Change them here, then rebuild.
"""

import math

# ---- shell ------------------------------------------------------------------
W, D, H = 200.0, 128.0, 59.0  # outside size, without feet, knob or screw heads
BODY_H = 56.0  # top of the chassis walls; the lid sits on this
LID_T = 3.0
FRONT_T = 4.0  # front panel: 3.2 of plastic behind a 0.8 deep pocket for the brass
REAR_T = 3.0
WALL = 4.0
FLOOR = 3.0
R_TOP = 6.0  # radius of the two top edges
CHAMFER = 2.5  # 45 degree chamfer on the two bottom edges; prints cleanly, a radius does not
TOWER_X, TOWER_Y = 14.0, 16.0  # corner blocks that take the panel and lid screws

# ---- brass ------------------------------------------------------------------
RIM = 1.2  # printed rim left around the brass; thinner than this is fragile
BRASS_T = 0.8  # sheet thickness = pocket depth, so the brass sits flush with the rim
BRASS_GAP = 0.15  # clearance all round between brass and rim

# ---- screws -----------------------------------------------------------------
SCREW_X = (7.0, W - 7.0)
SCREW_Z = (9.0, 50.0)  # front and rear panel screws, the same 7 mm from each side
LID_SCREW_Y = (FRONT_T + 12.5, D - REAR_T - 12.5)
LID_SCREW_X = (10.0, W - 10.0)  # in from the sides so the heads clear the 6 mm top radius
PILOT_M3 = 2.55  # M3 threads straight into the print
CLEAR_M3 = 3.3

# ---- front controls ---------------------------------------------------------
CTRL_Z = 29.5  # centre line of screen, keys and knob (half the height)
LCD_X = 48.4  # centre of the screen window
LCD_WINDOW = (42.2, 32.0)  # the Waveshare 2 inch panel shows 40.8 x 30.6
LCD_PCB = (58.0, 35.0, 1.6)
LCD_GLASS = 3.0  # MEASURE: how far the glass stands in front of the board
LCD_OFF_X = 2.0  # From Waveshare's drawing, with the pin pads on the left. Centre of the lit area minus centre of the board, seen from the
LCD_OFF_Z = 0.0  #          front; x to the right, z up. Room for -4 to +4 in x, -2 to +2 in z.
KEYS_X = (92.5, 110.5, 128.5, 146.5)  # Kailh Choc V1 at 18 mm pitch: previous, play, next, back
KEY_HOLE = 13.9
KEY_PLATE = 1.2  # plate thickness the Choc clips need
KNOB_X = 177.0
KNOB_D = 34.0
ENCODER_HOLE = 7.3  # M7 bushing
ENCODER_BODY = (13.5, 14.5)  # pocket for the encoder body; it also stops the body turning
PANEL_AT_NUT = 1.5  # plastic left where the encoder and socket nuts tighten (plus the brass)
# Headphones: the DAC Pro's own 3.5 mm socket sits on the same edge as its RCA sockets, so it
# comes out through RCA_WINDOW with no extra parts. Set REAR_JACK to True only if you want a
# separate panel socket on a short extension lead, at PHONES_X, PHONES_Z on the rear panel.
REAR_JACK = False
PHONES_X = 175.0
PHONES_Z = 22.0
PHONES_HOLE = 6.6  # MEASURE: the thread of that panel socket

# ---- card slot, guide and tray ----------------------------------------------
CARD_ANGLE = 5.0  # the card leans back by this much
CARD_X, CARD_Y = 157.0, 43.0  # where the card plane crosses the top of the lid
CHANNEL_W, CHANNEL_T = 55.4, 1.65
CARD_STOP_Z = 13.2  # bottom edge of an inserted card
GUIDE_X = (121.0, 193.0)  # the guide's two floor screws
GUIDE_Y = 44.5
PN532_CENTRE_Z = 34.0
PN532_PCB = (42.7, 40.4, 1.6)
# The PN532 V3 misses cards held against it and reads best about 20 mm away (bench test).
# READER_GAP runs from the card's centre to the reader's antenna face. The reader slides down
# into one of three pairs of grooves, READER_SLOTS from that distance, so it can be tuned in the case.
READER_GAP = 20.0
READER_SLOTS = (-4.0, 0.0, 4.0)
READER_Y = CARD_Y + READER_GAP  # antenna face of the reader in the middle grooves, at the top of the lid
TRAY = (15.0, 20.0, 104.0, 77.0)  # x0, y0, x1, y1 of the card tray in the lid
TRAY_DEPTH = 5.0
TRAY_FLOOR = 2.0

# ---- electronics ------------------------------------------------------------
# The Pi, the generic 1-to-2 splitter and the DAC Pro form one stack. It stands on four
# M2.5 standoffs screwed up through two slots in the floor, so it can slide front to back
# until the DAC's sockets meet the rear panel.
PI_X = 15.0  # left edge of the Pi; its mounting holes are 58 x 23 mm apart
PI_SLOT_Y = (40.0, 93.0)
STANDOFF_H = 5.0
RCA_WINDOW = (17.0, 78.0, 32.0, 51.0)  # MEASURE: x0, x1, z0, z1 of the opening for the DAC's RCA and headphone sockets
USB_X, USB_Z = 130.0, 16.0  # panel-mount USB-C socket
USB_SLOT = (12.5, 6.5)  # MEASURE: its body opening
USB_SCREW_PITCH = 17.0  # MEASURE: its two fixing screws
CRADLE_Y = 14.0  # the screen cradle's two floor screws, 20 mm either side of LCD_X
CRADLE_BOSS_DX = 20.0


# ---- shape tree ---------------------------------------------------------------
class Node:
    def __init__(self, kind, children=(), **params):
        self.kind, self.children, self.p = kind, list(children), params


def box(x0, x1, y0, y1, z0, z1):
    return Node("box", lo=(x0, y0, z0), hi=(x1, y1, z1))


def cylz(x, y, z0, z1, d):
    return Node("cyl", at=(x, y), z=(z0, z1), d=d)


def prism(points, z0, z1):
    """points: a counter-clockwise outline in x, y."""
    return Node("prism", pts=[tuple(p) for p in points], z=(z0, z1))


def xf(matrix, *children):
    """matrix: three rows of four, applied as world = M * local."""
    return Node("xf", children, m=[tuple(r) for r in matrix])


def union(*c):
    return Node("union", c)


def diff(first, *cuts):
    return Node("diff", (first,) + cuts)


def inter(*c):
    return Node("inter", c)


def hull(*c):
    return Node("hull", c)


def move(dx, dy, dz, *children):
    return xf([(1, 0, 0, dx), (0, 1, 0, dy), (0, 0, 1, dz)], *children)


def cyly(x, z, y0, y1, d):
    """A cylinder lying along y."""
    return xf([(1, 0, 0, 0), (0, 0, 1, 0), (0, -1, 0, 0)], cylz(x, -z, y0, y1, d))


# ---- outlines -------------------------------------------------------------------
def arc(cx, cy, r, a0, a1, n=12):
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)), cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def outline(inset=0.0):
    """The front silhouette in x, z, moved inwards by inset: chamfers below, radii above."""
    c = CHAMFER - inset * (2 - math.sqrt(2))
    r = R_TOP - inset
    pts = [(inset + c, inset), (W - inset - c, inset), (W - inset, inset + c)]
    pts += arc(W - R_TOP, H - R_TOP, r, 0, 90)
    pts += arc(R_TOP, H - R_TOP, r, 90, 180)
    pts.append((inset, inset + c))
    return pts


def rrect(x0, y0, x1, y1, r, n=8):
    return arc(x1 - r, y0 + r, r, -90, 0, n) + arc(x1 - r, y1 - r, r, 0, 90, n) + arc(x0 + r, y1 - r, r, 90, 180, n) + arc(x0 + r, y0 + r, r, 180, 270, n)


def circle(cx, cy, r, n=48):
    return arc(cx, cy, r, 0, 360, n)[:-1]


def slot_x(cx, cy, half, d, n=12):
    """A slot along x with round ends: centres half either side of cx."""
    return arc(cx + half, cy, d / 2, -90, 90, n) + arc(cx - half, cy, d / 2, 90, 270, n)


def slot_y(cx, y0, y1, d, n=12):
    return arc(cx, y1, d / 2, 0, 180, n) + arc(cx, y0, d / 2, 180, 360, n)


TAN = math.tan(math.radians(CARD_ANGLE))
FRONT_M = [(1, 0, 0, 0), (0, 0, -1, FRONT_T), (0, 1, 0, 0)]  # panel coordinates (x, height, depth from the inside face) to the case
REAR_M = [(-1, 0, 0, W), (0, 0, 1, D - REAR_T), (0, 1, 0, 0)]


def envelope():
    """The silhouette swept from front to back; every shell part is trimmed to it."""
    return xf([(1, 0, 0, 0), (0, 0, -1, D), (0, 1, 0, 0)], prism(outline(), 0, D))


def cradle_centre():
    return LCD_X - LCD_OFF_X, CTRL_Z - LCD_OFF_Z


# ---- printed parts ---------------------------------------------------------------
def chassis():
    y0, y1 = FRONT_T, D - REAR_T
    boss_x = (LCD_X - CRADLE_BOSS_DX, LCD_X + CRADLE_BOSS_DX)
    solid = union(
        box(0, W, y0, y1, 0, FLOOR),
        box(0, WALL, y0, y1, 0, BODY_H),
        box(W - WALL, W, y0, y1, 0, BODY_H),
        *[box(x, x + TOWER_X, y, y + TOWER_Y, 0, BODY_H) for x in (0, W - TOWER_X) for y in (y0, y1 - TOWER_Y)],
        *[cylz(x, GUIDE_Y, FLOOR - 0.1, 5, 8) for x in GUIDE_X],
        *[cylz(x, CRADLE_Y, FLOOR - 0.1, 5, 8) for x in boss_x],
    )
    cuts = [cylz(x, y, 47, BODY_H + 1, PILOT_M3) for x in LID_SCREW_X for y in LID_SCREW_Y]
    cuts += [cyly(x, z, y0 - 1, y0 + 9, PILOT_M3) for x in SCREW_X for z in SCREW_Z]
    cuts += [cyly(x, z, y1 - 9, y1 + 1, PILOT_M3) for x in SCREW_X for z in SCREW_Z]
    cuts += [cylz(x, GUIDE_Y, 1, 6, PILOT_M3) for x in GUIDE_X]
    cuts += [cylz(x, CRADLE_Y, 1, 6, PILOT_M3) for x in boss_x]
    cuts += [prism(slot_y(PI_X + dx, *PI_SLOT_Y, 2.9), -1, FLOOR + 1) for dx in (3.5, 61.5)]
    cuts += [box(x, x + 7, 24, 27, -1, FLOOR + 1) for x in range(20, 177, 12)]  # air intake; keep the feet clear of it
    return inter(diff(solid, *cuts), envelope())


def tray_outline(grow, r):
    x0, y0, x1, y1 = TRAY
    return [rrect(x0 - grow, y0 - grow, x1 + grow, y1 + grow, r + grow), circle((x0 + x1) / 2, y0, 10 + grow)]


def lid():
    """Lid coordinates: z = 0 is its underside (BODY_H in the case)."""
    y0, y1 = FRONT_T + 0.2, D - REAR_T - 0.2  # it drops in between the front and rear panels
    under = -(TRAY_DEPTH - LID_T) - TRAY_FLOOR  # underside of the tray
    solid = union(box(0, W, y0, y1, 0, LID_T), *[prism(p, under, LID_T) for p in tray_outline(2, 4)])
    lean = [(1, 0, 0, 0), (0, 1, TAN, -LID_T * TAN), (0, 0, 1, 0)]
    cuts = [prism(p, under + TRAY_FLOOR, LID_T + 1) for p in tray_outline(0, 4)]
    cuts += [cylz(x, y, -1, LID_T + 1, CLEAR_M3) for x in LID_SCREW_X for y in LID_SCREW_Y]
    # Recess low-profile heads (maximum diameter 6 mm, height 1.5 mm).
    cuts += [cylz(x, y, LID_T - 1.6, LID_T + 1, 6.4) for x in LID_SCREW_X for y in LID_SCREW_Y]
    cuts.append(xf(lean, box(CARD_X - CHANNEL_W / 2, CARD_X + CHANNEL_W / 2, CARD_Y - 1.05, CARD_Y + 1.05, -1, LID_T + 1)))
    cuts.append(  # a funnel so the card finds the slot
        hull(
            box(CARD_X - CHANNEL_W / 2, CARD_X + CHANNEL_W / 2, CARD_Y - 1.05, CARD_Y + 1.05, 1.4, 1.5),
            box(CARD_X - CHANNEL_W / 2 - 1, CARD_X + CHANNEL_W / 2 + 1, CARD_Y - 2.05, CARD_Y + 2.05, 2.95, 3.2),
        )
    )
    cuts += [box(x, x + 3, y, y + 11, -1, LID_T + 1) for x in range(22, 79, 8) for y in (86, 101)]  # above the DAC
    return inter(diff(solid, *cuts), move(0, 0, -BODY_H, envelope()))


def front():
    """Panel coordinates: x, height, and depth measured from the inside face (the print bed)."""
    back = FRONT_T - BRASS_T  # plastic thickness behind the brass
    cuts = [prism(outline(RIM), back, FRONT_T + 1)]  # the pocket the brass drops into
    cuts.append(box(LCD_X - LCD_WINDOW[0] / 2, LCD_X + LCD_WINDOW[0] / 2, CTRL_Z - LCD_WINDOW[1] / 2, CTRL_Z + LCD_WINDOW[1] / 2, -1, FRONT_T + 1))
    for k in KEYS_X:
        cuts.append(box(k - KEY_HOLE / 2, k + KEY_HOLE / 2, CTRL_Z - KEY_HOLE / 2, CTRL_Z + KEY_HOLE / 2, -1, FRONT_T + 1))
        cuts.append(box(k - 8.5, k + 8.5, CTRL_Z - 8.5, CTRL_Z + 8.5, -1, back - KEY_PLATE))  # room for the switch clips
    cuts += [cylz(x, z, -1, FRONT_T + 1, CLEAR_M3) for x in SCREW_X for z in SCREW_Z]
    cuts.append(cylz(KNOB_X, CTRL_Z, -1, FRONT_T + 1, ENCODER_HOLE))
    cuts.append(box(KNOB_X - ENCODER_BODY[0] / 2, KNOB_X + ENCODER_BODY[0] / 2, CTRL_Z - ENCODER_BODY[1] / 2, CTRL_Z + ENCODER_BODY[1] / 2, -1, back - PANEL_AT_NUT))
    return diff(prism(outline(), 0, FRONT_T), *cuts)


def rear():
    """Panel coordinates as for the front, seen from behind, so x runs the other way."""
    u = lambda x: W - x
    x0, x1, z0, z1 = RCA_WINDOW
    cuts = [cylz(u(x), z, -1, REAR_T + 1, CLEAR_M3) for x in SCREW_X for z in SCREW_Z]
    cuts.append(box(u(x1), u(x0), z0, z1, -1, REAR_T + 1))
    cuts.append(prism(slot_x(u(USB_X), USB_Z, (USB_SLOT[0] - USB_SLOT[1]) / 2, USB_SLOT[1]), -1, REAR_T + 1))
    cuts += [cylz(u(USB_X) + s * USB_SCREW_PITCH / 2, USB_Z, -1, REAR_T + 1, CLEAR_M3) for s in (-1, 1)]
    cuts += [box(u(x) - 5, u(x), 44, 47, -1, REAR_T + 1) for x in range(100, 171, 10)]  # warm air out
    if REAR_JACK:
        cuts.append(cylz(u(PHONES_X), PHONES_Z, -1, REAR_T + 1, PHONES_HOLE))
    return diff(prism(outline(), 0, REAR_T), *cuts)


def card_guide():
    """Origin: the left floor screw, at the underside of the foot (5 mm above the case's underside)."""
    gx, gy = CARD_X - GUIDE_X[0], CARD_Y - GUIDE_Y
    top = BODY_H - 0.3 - 5  # stops just under the lid
    stop = CARD_STOP_Z - 5
    outer, wall = CHANNEL_W + 4.4, 2.0
    lean = [(1, 0, 0, 0), (0, 1, TAN, -TAN * (H - 5)), (0, 0, 1, 0)]
    back = gy + CHANNEL_T / 2 + wall  # rear face of the card channel
    # Two grooved posts behind the channel hold the reader by its side edges, antenna facing the card.
    edge = PN532_PCB[0] / 2  # board centre to its side edge
    face = gy + READER_GAP  # antenna face in the middle grooves
    p0, p1 = face + min(READER_SLOTS) - 2.2, face + max(READER_SLOTS) + PN532_PCB[2] + 2.2
    post_top = PN532_CENTRE_Z + PN532_PCB[1] / 2 - 5 - 3  # below the board's top edge and its header
    board_low = PN532_CENTRE_Z - PN532_PCB[1] / 2 - 5  # the board's lower edge rests here
    half = GUIDE_X[1] - GUIDE_X[0]
    solid = [
        box(-4, half + 2.5, -11, 7, 0, 3),
        xf(lean, box(gx - outer / 2, gx + outer / 2, gy - CHANNEL_T / 2 - wall, back, 2.9, top)),
        box(gx - edge - 3.3, gx + edge + 3.3, 6.9, p1 - TAN * (H - 5) + 0.5, 0, 3),  # foot under the posts
    ]
    for s in (-1, 1):
        rx = gx + s * (outer / 2 - 2)
        solid.append(hull(box(rx - 1.5, rx + 1.5, -7, 7, 1, 3), xf(lean, box(rx - 1.5, rx + 1.5, -2, 1, 16, 17))))
        i0, i1 = sorted((gx + s * (edge - 1.5), gx + s * (edge + 3.3)))
        solid.append(xf(lean, box(i0, i1, p0, p1, 0, post_top)))  # post
        w0, w1 = sorted((gx + s * (edge + 1.3), gx + s * (edge + 3.3)))
        solid.append(xf(lean, box(w0, w1, back - 0.1, p0 + 0.1, 0, post_top)))  # web from the channel to the post
    cuts = [xf(lean, box(gx - CHANNEL_W / 2, gx + CHANNEL_W / 2, gy - CHANNEL_T / 2, gy + CHANNEL_T / 2, stop, top + 5))]
    cuts += [cylz(x, 0, -1, 4, CLEAR_M3) for x in (0, half)]
    for o in READER_SLOTS:  # grooves 0.4 wider than the board and 0.3 past its edges
        for s in (-1, 1):
            g0, g1 = sorted((gx + s * (edge - 1.5 - 0.1), gx + s * (edge + 0.3)))
            cuts.append(xf(lean, box(g0, g1, face + o - 0.2, face + o + PN532_PCB[2] + 0.2, board_low - 0.2, post_top + 5)))
    return diff(union(*solid), *cuts)


def display_cradle():
    """Holds the screen against the window. Case coordinates; prints standing as drawn."""
    cx, cz = cradle_centre()
    half = LCD_PCB[0] / 2 + 0.2
    board_y = FRONT_T + LCD_GLASS
    top = cz + LCD_PCB[1] / 2 + 2
    y0, y1 = FRONT_T + 0.2, board_y + LCD_PCB[2] + 3
    solid = [box(cx - half - 2.5, cx + half + 2.5, y0, 20, 5, 8)]
    solid += [box(min(a, b), max(a, b), y0, y1, 5, top) for a, b in ((cx - half - 2.5, cx - half + 1), (cx + half + 2.5, cx + half - 1))]
    cuts = [box(cx - half, cx + half, board_y - 0.15, board_y + LCD_PCB[2] + 0.15, cz - LCD_PCB[1] / 2 - 0.2, top + 1)]  # the board slides in from above
    cuts += [prism(slot_x(LCD_X + s * CRADLE_BOSS_DX, CRADLE_Y, 5, CLEAR_M3), 4, 9) for s in (-1, 1)]
    return diff(union(*solid), *cuts)


def fit_gauge():
    """Print this first, on the settings you will use for the case, and try every part in it."""
    back = FRONT_T - BRASS_T
    cuts = [box(4, 4 + KEY_HOLE, 8, 8 + KEY_HOLE, -1, FRONT_T + 1), box(4 + KEY_HOLE / 2 - 8.5, 4 + KEY_HOLE / 2 + 8.5, 8 + KEY_HOLE / 2 - 8.5, 8 + KEY_HOLE / 2 + 8.5, -1, back - KEY_PLATE)]
    cuts += [cylz(32, 15, -1, FRONT_T + 1, ENCODER_HOLE), box(32 - ENCODER_BODY[0] / 2, 32 + ENCODER_BODY[0] / 2, 15 - ENCODER_BODY[1] / 2, 15 + ENCODER_BODY[1] / 2, -1, back - PANEL_AT_NUT)]
    if REAR_JACK:
        cuts.append(cylz(52, 15, -1, FRONT_T + 1, PHONES_HOLE))
    cuts += [cylz(x, 15, -1, FRONT_T + 1, d) for x, d in ((66, CLEAR_M3), (73, PILOT_M3), (80, 2.9))]
    cuts.append(box(15, 15 + CHANNEL_W, 30, 30 + CHANNEL_T, -1, FRONT_T + 1))
    cuts.append(box(-1, 90 - RIM, -1, 36 - RIM, back, FRONT_T + 1))  # a corner of the brass pocket and its rim
    return diff(box(0, 90, 0, 36, 0, FRONT_T), *cuts)


PARTS = {"chassis": chassis, "lid": lid, "front": front, "rear": rear, "card-guide": card_guide, "display-cradle": display_cradle, "fit-gauge": fit_gauge}
# Where each part's own coordinates sit in the assembled case.
PLACE = {
    "chassis": move(0, 0, 0),
    "lid": move(0, 0, BODY_H),
    "front": xf(FRONT_M),
    "rear": xf(REAR_M),
    "card-guide": move(GUIDE_X[0], GUIDE_Y, 5),
    "display-cradle": move(0, 0, 0),
    "fit-gauge": None,
}


# ---- brass ---------------------------------------------------------------------
def brass_shapes():
    """The brass face as flat shapes in x, z: an outline, then the openings to cut."""
    k0, k1 = KEYS_X[0] - 8.25, KEYS_X[-1] + 8.25  # one slot for all four switches; the keycaps cover it
    return {
        "outline": outline(RIM + BRASS_GAP),
        "rects": [
            (LCD_X - LCD_WINDOW[0] / 2 - 0.6, CTRL_Z - LCD_WINDOW[1] / 2 - 0.6, LCD_X + LCD_WINDOW[0] / 2 + 0.6, CTRL_Z + LCD_WINDOW[1] / 2 + 0.6),
            (k0, CTRL_Z - 8.25, k1, CTRL_Z + 8.25),
        ],
        "circles": [(x, z, CLEAR_M3) for x in SCREW_X for z in SCREW_Z] + [(KNOB_X, CTRL_Z, ENCODER_HOLE)],
    }


def brass():
    """The brass as a solid, in front-panel coordinates, for the render and the clearance checks."""
    s = brass_shapes()
    back = FRONT_T - BRASS_T
    cuts = [box(x0, x1, z0, z1, back - 1, FRONT_T + 1) for x0, z0, x1, z1 in s["rects"]]
    cuts += [cylz(x, z, back - 1, FRONT_T + 1, d) for x, z, d in s["circles"]]
    return diff(prism(s["outline"], back, FRONT_T), *cuts)


def brass_svg():
    s = brass_shapes()
    f = lambda v: f"{v:.3f}".rstrip("0").rstrip(".")
    path = "M " + " L ".join(f"{f(x)},{f(H - z)}" for x, z in s["outline"]) + " Z"
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{f(W)}mm" height="{f(H)}mm" viewBox="0 0 {f(W)} {f(H)}">',
        f"<title>NFC Player brass face, {f(BRASS_T)} mm sheet. Drawn at actual size, seen from the front.</title>",
        '<g fill="none" stroke="black" stroke-width="0.1">',
        f'<path d="{path}"/>',
    ]
    out += [f'<rect x="{f(x0)}" y="{f(H - z1)}" width="{f(x1 - x0)}" height="{f(z1 - z0)}"/>' for x0, z0, x1, z1 in s["rects"]]
    out += [f'<circle cx="{f(x)}" cy="{f(H - z)}" r="{f(d / 2)}"/>' for x, z, d in s["circles"]]
    return "\n".join(out + ["</g>", "</svg>", ""])


# ---- OpenSCAD copy ---------------------------------------------------------------
def scad(node, depth=1):
    pad, p = "    " * depth, node.p
    n = lambda v: f"{v:.4f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)
    inner = "".join(scad(c, depth + 1) for c in node.children)
    if node.kind == "box":
        lo, hi = p["lo"], p["hi"]
        return f"{pad}translate([{n(lo[0])},{n(lo[1])},{n(lo[2])}]) cube([{n(hi[0] - lo[0])},{n(hi[1] - lo[1])},{n(hi[2] - lo[2])}]);\n"
    if node.kind == "cyl":
        return f"{pad}translate([{n(p['at'][0])},{n(p['at'][1])},{n(p['z'][0])}]) cylinder(h={n(p['z'][1] - p['z'][0])},d={n(p['d'])});\n"
    if node.kind == "prism":
        pts = ",".join(f"[{n(float(x))},{n(float(y))}]" for x, y in p["pts"])
        return f"{pad}translate([0,0,{n(p['z'][0])}]) linear_extrude({n(p['z'][1] - p['z'][0])}) polygon([{pts}]);\n"
    if node.kind == "xf":
        rows = ",".join("[" + ",".join(n(float(v)) for v in r) + "]" for r in p["m"])
        return f"{pad}multmatrix([{rows},[0,0,0,1]]) {{\n{inner}{pad}}}\n"
    name = {"union": "union", "diff": "difference", "inter": "intersection", "hull": "hull"}[node.kind]
    return f"{pad}{name}() {{\n{inner}{pad}}}\n"


def scad_file():
    out = [
        "// NFC Player Case v3. GENERATED by build.py from case.py: edit case.py, not this file.",
        "// openscad -o chassis.stl -D 'part=\"chassis\"' NFC-Player-Case.scad",
        'part = "assembly";',
        "$fn = 48;",
        "",
    ]
    names = {k: k.replace("-", "_") for k in PARTS}
    for key, make in PARTS.items():
        out.append(f"module {names[key]}() {{\n{scad(make())}}}\n")
    out.append(f"module brass() {{\n{scad(brass())}}}\n")
    for key in PARTS:
        out.append(f'if (part == "{key}") {names[key]}();')
    out.append('if (part == "brass") brass();')
    out.append('if (part == "brass-template") projection() brass();')
    out.append('if (part == "assembly") {')
    for key, place in PLACE.items():
        if place is not None:
            rows = ",".join("[" + ",".join(str(float(v)) for v in r) + "]" for r in place.p["m"])
            out.append(f"    multmatrix([{rows},[0,0,0,1]]) {names[key]}();")
    rows = ",".join("[" + ",".join(str(float(v)) for v in r) + "]" for r in FRONT_M)
    out.append(f'    color("#b68a4e") multmatrix([{rows},[0,0,0,1]]) brass();')
    out.append("}")
    return "\n".join(out) + "\n"
