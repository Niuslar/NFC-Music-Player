"""NFC Player Case v3: the one source of truth for every dimension. Millimetres throughout.

This file only describes shapes. build.py turns them into STLs with Blender and
writes the OpenSCAD copy, so both always agree:

    blender -b -P build.py

Axes: x across the front (0 = left), y front to back (0 = front face), z up (0 = underside).

MEASURE FIRST. The values marked MEASURE depend on the exact parts you bought and
could not be confirmed from published drawings. Change them here, then rebuild.
"""

import math

# ---- shell ------------------------------------------------------------------
W, D, H = 200.0, 128.0, 59.0  # outside size, without feet, knob or screw heads
BODY_H = 56.0  # top of the chassis walls; the lid sits on this
LID_T = 3.0
FRONT_T = 4.2  # front panel, solid: printed in black, its face is the finished front
REAR_T = 3.0
WALL = 4.0
FLOOR = 3.0
R_TOP = 6.0  # radius of the two top edges
CHAMFER = 2.5  # 45 degree chamfer on the two bottom edges; prints cleanly, a radius does not
TOWER_X, TOWER_Y = 14.0, 16.0  # corner blocks that take the panel and lid screws

# ---- screws -----------------------------------------------------------------
SCREW_X = (7.0, W - 7.0)
SCREW_Z = (9.0, 50.0)  # front and rear panel screws, the same 7 mm from each side
LID_SCREW_Y = (FRONT_T + 12.5, D - REAR_T - 12.5)
LID_SCREW_X = (10.0, W - 10.0)  # in from the sides so the heads clear the 6 mm top radius
PILOT_M3 = 2.55  # M3 threads straight into the print
CLEAR_M3 = 3.3

# ---- front controls ---------------------------------------------------------
CTRL_Z = 29.5  # centre line of screen, keys and knob (half the height)
LCD_X = 136.0  # centre of the screen window: right of the keys, clear of the front board
LCD_WINDOW = (42.2, 32.0)  # the Waveshare 2 inch panel shows 40.8 x 30.6
LCD_PCB = (58.0, 35.0, 1.6)
LCD_GLASS = 3.0  # MEASURE: how far the glass stands in front of the board
LCD_OFF_X = -2.0  # From Waveshare's drawing, fitted with the pin pads on the right. Centre of the lit area minus centre of the board, seen from the
LCD_OFF_Z = 0.0  #          front; x to the right, z up. Room for -4 to +4 in x, -2 to +2 in z.
# The screen screws onto an upright bracket through the four brass standoffs it comes with.
# Its 8-pin PH2.0 socket lies along one short edge of its back and opens sideways. The board is
# fitted with that edge on the left (seen from the front), so the plug faces the front board its
# lead runs to, and the bracket is open on that side for the plug and its wires.
LCD_HOLES = (52.0, 30.0)  # MEASURE: centres of the board's four corner holes, across and up
LCD_STANDOFF = 6.0  # MEASURE: how far the standoffs stand out behind the board
CLEAR_M25 = 2.9
CRADLE_TRAVEL = (2.5, 4.0)  # how far the bracket slides forward and back from where the glass meets the panel
KEYS_X = (37.0, 55.0, 73.0, 91.0)  # previous, play, next, back, 18 mm apart. Left, so the board behind them sits in front of the DAC
# Keys: the four printed caps are one part, the key carrier, with a thin frame that lies on the
# inside of the panel. Each cap slides in a square hole through the panel, flush with its face,
# and hangs from two thin bridges, one above it and one below, by a short tab in the
# middle of each edge. A press bends the bridges a little and the cap presses a 6 x 6 mm tactile
# switch soldered to the front board; the switch gives the click and pushes it back. The bridges
# keep each cap centred in its hole, so it does not rattle, and keep it from falling out. Two pegs
# on the carrier locate it in the panel, and the board's screws clamp it between the panel and a
# printed spacer. keycaps.py makes the carrier.
KEY_CAP = 14.0  # the cap, square
KEY_CAP_R = 2.0  # its corner radius
KEY_HOLE = 14.4  # the hole through the panel that guides it
KEY_PROUD = 0.0  # how far the cap's face stands in front of the panel; 0 is flush
KEY_FACE_T = 1.6  # solid face of the cap, in front of the switch (its symbol is cut 0.6 into it)
KEY_FREE = 0.1  # between the cap and the switch's button at rest, so the switch is never held down
TACT = 6.0  # MEASURE: the switch body, square
TACT_BODY_H = 3.5  # MEASURE: its body height, without the button
TACT_H = 5.0  # MEASURE: its height with the button, from the board; the "6x6x5" of the listing
TACT_TRAVEL = 0.25  # about this much until it clicks
CARRIER_T = 1.2  # the carrier's frame, between the panel and the spacer
BRIDGE_T = 0.4  # the bridges and tabs: two 0.2 mm layers. They add about 0.5 N to a press; 0.6 would add three times that
BRIDGE_W = 0.8  # each bridge's width, in the plane of the carrier
BRIDGE_GAP = 0.5  # the slots either side of a bridge, and between a cap and the frame beside it
TAB_W = 2.0  # the tab joining a bridge to the middle of its cap's edge
KEY_LENGTH = KEY_PROUD + FRONT_T + CARRIER_T  # the cap, from its face to its back, which is flush with the carrier's
KEY_HOLLOW = TACT + 1.0  # the hollow in the cap's back, round the switch body
KEY_WIN_X = KEY_CAP / 2 + BRIDGE_GAP  # from a key's centre to the frame beside it, in the carrier and the spacer
KEY_WIN_Z = KEY_CAP / 2 + 2 * BRIDGE_GAP + BRIDGE_W  # and to the frame above and below, past its bridges
PEGS = ((26.0, CTRL_Z), (88.0, 45.0))  # x, z of the carrier's two locating pegs, in blind holes in the panel
PEG_D, PEG_L = 2.0, 1.8  # the pegs, standing on the carrier's front
PEG_HOLE, PEG_DEPTH = 2.3, 2.2  # their holes in the inside of the panel
KNOB_X = 178.5
KNOB_D = 30.0  # the largest knob the front takes: it sits close to the screen window
ENCODER_HOLE = 7.3  # M7 bushing
ENCODER_BODY = (13.5, 14.5)  # pocket for the encoder body; it also stops the body turning
PANEL_AT_NUT = 2.3  # plastic left where the encoder and socket nuts tighten
# Power key: a 12 mm panel push button with its own LED, left of the screen. It must be
# momentary (not latching). Its body reaches into the case past the front corner tower, so
# that tower is cut away between TOWER_GAP_Z; its screw pilots stay above and below.
POWER_X = 14.0
POWER_HOLE = 12.2  # MEASURE: the button's thread
POWER_BODY = (16.0, 30.0)  # MEASURE: across its nut, and depth behind the panel including the solder tags
TOWER_GAP_Z = (16.0, 43.0)
# Headphones: the DAC Pro's own 3.5 mm socket sits on the same edge as its RCA sockets, so it
# comes out through its own hole in the rear panel with no extra parts. Set REAR_JACK to True only if you want a
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

# ---- front board ------------------------------------------------------------
# A printed circuit board lies flat behind the front panel, behind the keys, on a printed spacer
# that lies on the key carrier.
# The four key switches are soldered to its front, and a 40-pin ribbon runs from it to the
# pins on top of the DAC. front-board/board.py draws it from these numbers.
# The spacer sets the board just far back that a switch's button sits KEY_FREE behind its cap.
SPACER_T = -KEY_PROUD + KEY_FACE_T + KEY_FREE + TACT_H - FRONT_T - CARRIER_T
BOARD_Y = FRONT_T + CARRIER_T + SPACER_T  # the board's front face, in the case
# Its 40-pin header sits straight in front of the Pi's, the same way round, so the ribbon runs
# back and down onto the DAC's pins with one bend and no twist (see front-board/board.py).
PI_HEADER_X = None  # set below, from PI_X
BOARD_OUTLINE = ((23.0, 4.0), (101.5, 4.0), (101.5, 51.5), (17.5, 51.5), (17.5, 40.0), (23.0, 40.0))  # x, z; the top clears the card tray under the lid; the step at the
# top left lets the 40-pin header reach over the power key's nut
BOARD_X = (min(x for x, z in BOARD_OUTLINE), max(x for x, z in BOARD_OUTLINE))
BOARD_Z = (min(z for x, z in BOARD_OUTLINE), max(z for x, z in BOARD_OUTLINE))
BOARD_T = 1.6
BOARD_SCREWS = ((27.0, 8.0), (97.5, 8.0), (97.5, 47.0))  # M2 x 6, through pilots in the spacer and the carrier and into the panel
PILOT_M2 = 1.6
PILOT_M2_DEPTH = 2.8
# The other through-hole parts sit on the back of the board and are soldered on its front, so
# the spacer and the key carrier have openings under their solder joints: x0, z0, x1, z1. board.py
# checks that every through-hole pad lies inside one of these or inside a key's opening. The lower
# two stop just short of the bridges under the keys.
BOARD_POCKETS = (
    (21.5, 42.5, 73.5, 49.5),  # the 40-pin header
    (31.0, 5.5, 75.5, 18.0),  # the headers for the screen, reader, knob, power key and OLED
    (78.5, 5.5, 95.5, 20.6),  # diodes, transistor and resistors
)

# ---- electronics ------------------------------------------------------------
# The Pi and the DAC Pro form one stack. It stands on four M2.5 standoffs screwed up through
# two slots in the floor, so it can slide front to back. It goes right back, until the DAC's
# rear edge meets the rear panel, so its sockets sit in round holes in the panel.
PI_X = 15.0  # left edge of the Pi; its mounting holes are 58 x 23 mm apart
PI_HEADER_X = PI_X + 32.5  # centre of its 40-pin header, which the front board's header lines up with
STANDOFF_H = 5.0
DAC_LEN = 56.5  # front to back
DAC_GAP = 0.5  # between the DAC's rear edge and the inside of the rear panel
DAC_Y1 = D - REAR_T - DAC_GAP  # the DAC's rear edge, where its sockets are
PI_Y = DAC_Y1 - DAC_LEN  # the front edge of the Pi and the DAC
DAC_Z = FLOOR + STANDOFF_H + 1.6 + 11  # underside of the DAC board, straight on the Pi
PI_SLOT_Y = (40.0, 97.0)  # the standoffs sit at PI_Y + 3.5 and PI_Y + 26.5; room to slide either way
# MEASURE: x, z of each socket's centre, and the hole for it. The barrels end about 1 mm inside
# the panel's outer face, so each hole clears the plug's metal shell, not just the barrel.
# The header's pin 1 is on the right seen from the front, so seen from behind the case the
# sockets read as on the board: red RCA (left), white RCA (right), then the 3.5 mm socket.
DAC_JACKS = (
    ("RCA left", 53.5, DAC_Z + 1.6 + 6.5, 11.5),
    ("RCA right", 39.5, DAC_Z + 1.6 + 6.5, 11.5),
    ("headphones", 24.5, DAC_Z + 4.6, 9.0),
)
USB_X, USB_Z = 130.0, 16.0  # panel-mount USB-C socket
USB_SLOT = (12.5, 6.5)  # MEASURE: its body opening
USB_SCREW_PITCH = 17.0  # MEASURE: its two fixing screws
CRADLE_BOSS_DX = 20.0  # the bracket's two floor screws, either side of LCD_X
CRADLE_PLATE_Y = FRONT_T + LCD_GLASS + LCD_PCB[2] + LCD_STANDOFF  # front of the bracket's upright, with the glass on the panel
CRADLE_PLATE_T = 3.0
CRADLE_Y = 25.5  # the floor screws, behind the upright, so a screwdriver reaches them from above
CRADLE_TAB = 10.0  # width of the two tabs that reach back from the upright to those screws
WASHER_M3 = 7.0

assert FRONT_T + CARRIER_T + TACT_TRAVEL + 0.3 <= BOARD_Y, "a pressed cap's back must clear the board"
assert SPACER_T >= 0.8, "the spacer would be too thin to print"
assert BOARD_Y - TACT_BODY_H >= -KEY_PROUD + KEY_FACE_T, "the switch body must fit in the hollow behind the cap's face"
assert KEYS_X[1] - KEYS_X[0] - 2 * KEY_WIN_X >= 2.0, "the frame between two keys would be too thin"
assert all(z1 <= CTRL_Z - KEY_WIN_Z + BRIDGE_GAP + 0.01 for x0, z0, x1, z1 in BOARD_POCKETS[1:]), "a pocket would cut into the bridges under the keys"
assert CRADLE_Y - CRADLE_TRAVEL[1] - WASHER_M3 / 2 >= CRADLE_PLATE_Y + CRADLE_PLATE_T, "with the bracket slid right back, the washers must clear its upright"
assert CRADLE_Y + CRADLE_TRAVEL[0] + CLEAR_M3 / 2 + 1.5 + CRADLE_TRAVEL[1] + 0.5 <= GUIDE_Y - 8, "with the bracket slid right back, its tabs must clear the card guide's foot"
assert PI_SLOT_Y[0] <= PI_Y + 3.5 and PI_Y + 26.5 <= PI_SLOT_Y[1], "the standoffs must reach their place in the floor slots"


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
CARRIER_M = [(1, 0, 0, 0), (0, 0, -1, FRONT_T + CARRIER_T), (0, 1, 0, 0)]  # the carrier's coordinates (x, height, from its back) to the case
REAR_M = [(-1, 0, 0, W), (0, 0, 1, D - REAR_T), (0, 1, 0, 0)]


def envelope():
    """The silhouette swept from front to back; every shell part is trimmed to it."""
    return xf([(1, 0, 0, 0), (0, 0, -1, D), (0, 1, 0, 0)], prism(outline(), 0, D))


def cradle_centre():
    return LCD_X - LCD_OFF_X, CTRL_Z - LCD_OFF_Z


# ---- printed parts ---------------------------------------------------------------
def chassis():
    y0, y1 = FRONT_T + 0.001, D - REAR_T  # at exactly 4.2, Blender's exact boolean leaves the chassis open
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
    cuts.append(box(WALL - 0.5, TOWER_X + 1, y0 - 1, y0 + TOWER_Y + 1, *TOWER_GAP_Z))  # room for the power key
    cuts += [cyly(x, z, y0 - 1, y0 + 9, PILOT_M3) for x in SCREW_X for z in SCREW_Z]
    cuts += [cyly(x, z, y1 - 9, y1 + 1, PILOT_M3) for x in SCREW_X for z in SCREW_Z]
    cuts += [cylz(x, GUIDE_Y, 1, 6, PILOT_M3) for x in GUIDE_X]
    cuts += [cylz(x, CRADLE_Y, 1, 6, PILOT_M3) for x in boss_x]
    cuts += [prism(slot_y(PI_X + dx, *PI_SLOT_Y, 2.9), -1, FLOOR + 1) for dx in (3.5, 61.5)]
    cuts += [box(x, x + 7, 24, 27, -1, FLOOR + 1) for x in range(20, 177, 12) if all(x - 4.5 > bx or x + 7 + 4.5 < bx for bx in boss_x)]  # air intake; keep the feet and the bracket's bosses clear of it
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
    cuts = [box(LCD_X - LCD_WINDOW[0] / 2, LCD_X + LCD_WINDOW[0] / 2, CTRL_Z - LCD_WINDOW[1] / 2, CTRL_Z + LCD_WINDOW[1] / 2, -1, FRONT_T + 1)]
    cuts += [prism(key_square(k, CTRL_Z, KEY_HOLE), -1, FRONT_T + 1) for k in KEYS_X]
    cuts += [cylz(x, z, -1, FRONT_T + 1, CLEAR_M3) for x in SCREW_X for z in SCREW_Z]
    cuts.append(cylz(KNOB_X, CTRL_Z, -1, FRONT_T + 1, ENCODER_HOLE))
    cuts.append(box(KNOB_X - ENCODER_BODY[0] / 2, KNOB_X + ENCODER_BODY[0] / 2, CTRL_Z - ENCODER_BODY[1] / 2, CTRL_Z + ENCODER_BODY[1] / 2, -1, FRONT_T - PANEL_AT_NUT))
    cuts.append(cylz(POWER_X, CTRL_Z, -1, FRONT_T + 1, POWER_HOLE))
    cuts += [cylz(x, z, -1, PILOT_M2_DEPTH, PILOT_M2) for x, z in BOARD_SCREWS]
    cuts += [cylz(x, z, -1, PEG_DEPTH, PEG_HOLE) for x, z in PEGS]  # the key carrier's pegs
    return diff(prism(outline(), 0, FRONT_T), *cuts)


def key_square(x, z, size, r=None):
    """A key-shaped square outline centred on x, z, its corners rounded to match the cap."""
    r = KEY_CAP_R + (size - KEY_CAP) / 2 if r is None else r
    return rrect(x - size / 2, z - size / 2, x + size / 2, z + size / 2, r)


def key_window(x):
    """The opening round a key in the carrier and the spacer: its cap, its bridges and their slots."""
    return rrect(x - KEY_WIN_X, CTRL_Z - KEY_WIN_Z, x + KEY_WIN_X, CTRL_Z + KEY_WIN_Z, 1.0)


def spacer():
    """Printed flat. Panel coordinates as for the front, but z = 0 is the side against the board."""
    cuts = [prism(key_window(k), -1, SPACER_T + 1) for k in KEYS_X]
    cuts += [box(x0, x1, z0, z1, -1, SPACER_T + 1) for x0, z0, x1, z1 in BOARD_POCKETS]
    cuts += [cylz(x, z, -1, SPACER_T + 1, PILOT_M2) for x, z in BOARD_SCREWS]
    return diff(prism(BOARD_OUTLINE, 0, SPACER_T), *cuts)


def key_carrier():
    """The four key caps on their frame; keycaps.py draws it, since the symbols live there."""
    import keycaps

    return keycaps.carrier()


def rear():
    """Panel coordinates as for the front, seen from behind, so x runs the other way."""
    u = lambda x: W - x
    cuts = [cylz(u(x), z, -1, REAR_T + 1, CLEAR_M3) for x in SCREW_X for z in SCREW_Z]
    cuts += [cylz(u(x), z, -1, REAR_T + 1, d) for name, x, z, d in DAC_JACKS]
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
        box(-4, half + 2.5, -8, 7, 0, 3),  # its front edge stays behind the screen bracket's tabs
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
    """An upright the screen screws onto, on a base that slides back and forth over two floor
    bosses. The floor screws sit behind the upright, in two tabs, so they stay in reach from
    above. Case coordinates, drawn where the glass meets the panel; prints standing as drawn."""
    cx, cz = cradle_centre()
    hx, hz = LCD_HOLES[0] / 2, LCD_HOLES[1] / 2
    side = hx + 4.5  # past the holes' slots
    y0, y1 = CRADLE_PLATE_Y, CRADLE_PLATE_Y + CRADLE_PLATE_T
    low = cz - hz + 3.5  # top of the lower bar
    solid = [
        box(cx - side, cx + side, y0, y1 + 4, 5, 8),  # foot along the upright
        box(cx - side, cx + side, y0, y1, 5, low),  # lower bar, below the socket
        box(cx - side, cx + side, y0, y1, cz + hz - 3.5, cz + hz + 3.5),  # upper bar
        box(cx + hx - 3.5, cx + side, y0, y1, 5, cz + hz + 3.5),  # right side, behind the pin pads; the left stays open for the plug
    ]
    for s in (-1, 1):
        bx = LCD_X + s * CRADLE_BOSS_DX
        solid.append(box(bx - CRADLE_TAB / 2, bx + CRADLE_TAB / 2, y0, CRADLE_Y + CRADLE_TRAVEL[0] + CLEAR_M3 / 2 + 1.5, 5, 8))  # tab back to a floor screw
        ex = cx + s * (side - 1.25)  # a rib at each end of the upright, so it stays square to its base
        solid.append(hull(box(ex - 1.25, ex + 1.25, y1 - 0.1, y1 + 4, 7.9, 8), box(ex - 1.25, ex + 1.25, y1 - 0.1, y1, low - 0.1, low)))
    cuts = [hull(cyly(x - 2, z, y0 - 1, y1 + 1, CLEAR_M25), cyly(x + 2, z, y0 - 1, y1 + 1, CLEAR_M25)) for x in (cx - hx, cx + hx) for z in (cz - hz, cz + hz)]  # 2 mm either way to centre the picture
    cuts += [prism(slot_y(LCD_X + s * CRADLE_BOSS_DX, CRADLE_Y - CRADLE_TRAVEL[1], CRADLE_Y + CRADLE_TRAVEL[0], CLEAR_M3), 4, 9) for s in (-1, 1)]
    return diff(union(*solid), *cuts)


def fit_gauge():
    """Print this first, on the settings you will use for the case, and try every part in it."""
    cuts = [prism(key_square(12, 17, KEY_HOLE), -1, FRONT_T + 1)]  # a cap must slide freely in this
    cuts.append(cylz(60, 24, -1, PEG_DEPTH, PEG_HOLE))  # and a carrier peg go into this
    cuts += [cylz(32, 15, -1, FRONT_T + 1, ENCODER_HOLE), box(32 - ENCODER_BODY[0] / 2, 32 + ENCODER_BODY[0] / 2, 15 - ENCODER_BODY[1] / 2, 15 + ENCODER_BODY[1] / 2, -1, FRONT_T - PANEL_AT_NUT)]
    if REAR_JACK:
        cuts.append(cylz(52, 15, -1, FRONT_T + 1, PHONES_HOLE))
    cuts += [cylz(x, 15, -1, FRONT_T + 1, d) for x, d in ((66, CLEAR_M3), (73, PILOT_M3), (80, 2.9))]
    cuts.append(box(15, 15 + CHANNEL_W, 30, 30 + CHANNEL_T, -1, FRONT_T + 1))
    return diff(box(0, 90, 0, 36, 0, FRONT_T), *cuts)


PARTS = {"chassis": chassis, "lid": lid, "front": front, "key-carrier": key_carrier, "board-spacer": spacer, "rear": rear, "card-guide": card_guide, "display-cradle": display_cradle, "fit-gauge": fit_gauge}
# Where each part's own coordinates sit in the assembled case.
PLACE = {
    "chassis": move(0, 0, 0),
    "lid": move(0, 0, BODY_H),
    "front": xf(FRONT_M),
    "key-carrier": xf(CARRIER_M),
    "board-spacer": xf([(1, 0, 0, 0), (0, 0, -1, BOARD_Y), (0, 1, 0, 0)]),  # its z = 0 against the board
    "rear": xf(REAR_M),
    "card-guide": move(GUIDE_X[0], GUIDE_Y, 5),
    "display-cradle": move(0, 0, 0),
    "fit-gauge": None,
}


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
    for key in PARTS:
        out.append(f'if (part == "{key}") {names[key]}();')
    out.append('if (part == "assembly") {')
    for key, place in PLACE.items():
        if place is not None:
            rows = ",".join("[" + ",".join(str(float(v)) for v in r) + "]" for r in place.p["m"])
            out.append(f"    multmatrix([{rows},[0,0,0,1]]) {names[key]}();")
    out.append("}")
    return "\n".join(out) + "\n"
