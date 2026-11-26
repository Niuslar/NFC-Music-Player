"""The front board as a hand-wired perfboard: where every part, link and wire goes, checked against board.py's schematic and drawn for the guide. Plain Python, no KiCad.

    python3 perfboard.py

It uses the same 70 x 50 mm board, holes and parts as the printed circuit board (case.py sets the
grid, board.py the nets), with through-hole versions of the small parts. It checks that every
net joins exactly the pins it should, that every wire ends beside its pin, that every solder joint
on the front sits over an opening in the spacer, that nothing touches the screws, and that no two
parts stand in each other's way. Then it writes fab/perfboard-back.svg and fab/perfboard-front.svg,
and gives guide.py the parts, the links and the wires in the order to fit them, with a beep test
after each group.

How it is built, all by hand. The parts and headers go in from the back and are soldered on the
front, the side that faces the panel; the four key switches go on the front and are soldered on the
back. The wires run on the back, crossing behind the keys from the 40-pin header to the strip of
headers along the bottom. Each ends in a wire pad, a free hole beside the pin it serves: its stripped
end goes through that hole and is bent onto the pin on the front, so one joint holds both. Short
bare links on the front, and a ground bus along row C, do the rest.

Holes are named by row and column, as D-3: rows A (bottom) to T, with no I or O, and columns 1 to 24
counted from the left seen from the back. Seen from the front, column 1 is on the right.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import board as fb  # noqa: E402
import case as c  # noqa: E402
import drawings as dw  # noqa: E402

COLS, ROWS = c.PERF_HOLES[0], c.BOARD_ROWS
FAB = HERE / "fab"


ROW_LETTERS = "ABCDEFGHJKLMNPQRST"  # no I or O, which read as 1 and 0


def name(h):
    """A hole's name: its row letter, a hyphen and its column number seen from the back. The
    hyphen keeps "D-3", a hole, apart from D3, a part."""
    col, row = h
    return f"{ROW_LETTERS[row]}-{COLS - col}"


def xz(h):
    return c.hole(*h)


# ---- parts: through-hole versions of board.py's, in the holes. Columns count from the left seen from the front. ----
# kind sets how a part is drawn and how much room it takes on the back. "body" is the hole an upright
# part stands over; its other lead loops over the top into the other hole, where a wire can be
# soldered to it from the back.
PARTS = {}


def part(ref, kind, value, pins, body=None, note=""):
    PARTS[ref] = {"kind": kind, "value": value, "pins": pins, "body": body, "note": note}


part("J1", "j1", "2 x 20 straight pin header, plain (no shroud)", {str(p): (c.J1_COLS[1] - (p - 1) // 2, c.J1_ROWS[(p - 1) % 2]) for p in range(1, 41)})
for ref, (col1, row) in c.HEADER_HOLES.items():
    title, names, nets, x1, z, value = fb.HEADERS[ref]
    part(ref, "header", f"1 x {len(names)} straight pin header", {str(k + 1): (col1 - k, row) for k in range(len(names))})
for i, ref in enumerate(("SW1", "SW2", "SW3", "SW4")):
    a = 7 * i  # its legs sit in columns a and a + 2, rows 7 and 10
    # Pins 1 and 2 are wired to diagonally opposite legs, which are always on different contacts,
    # whichever way round the switch's contacts run inside. The other two legs stay free.
    part(ref, "switch", "6 x 6 mm tactile switch, 5 mm tall", {"1": (a + 2, 10), "2": (a, 7), "-a": (a + 2, 7), "-b": (a, 10)})
part("D1", "diode", "BAT43, DO-35", {"1": (15, 3), "2": (15, 4)}, body=(15, 3), note="upright, cathode band down, in the lower hole")
part("D2", "diode", "BAT43, DO-35", {"1": (16, 3), "2": (16, 4)}, body=(16, 3), note="upright, cathode band down, in the lower hole")
part("R1", "resistor", "1 kΩ", {"1": (18, 4), "2": (18, 3)}, body=(18, 3))
part("Q1", "to92", "2N3904, TO-92", {"1": (20, 3), "2": (20, 2), "3": (20, 4)}, note="legs in a column: emitter at the bottom, collector at the top; flat face towards R1")
part("R2", "resistor", "220 Ω", {"1": (22, 4), "2": (22, 3)}, body=(22, 3))
part("R3", "resistor", "1 kΩ", {"1": (20, 0), "2": (20, 1)}, body=(20, 0), note="optional, with D3")
part("D3", "led", "3 mm orange LED", {"1": (18, 1), "2": (18, 0)}, note="optional: lit while the board has 3.3 V. Long leg (anode) in the lower hole")
part("R4", "resistor", "2.2 kΩ", {"1": (21, 0), "2": (21, 1)}, body=(21, 1), note="optional, with D4")
part("D4", "led", "3 mm red LED", {"1": (23, 1), "2": (23, 0)}, note="optional: lit while the board has 5 V. Long leg (anode) in the lower hole")
OPTIONAL = {"R3", "D3", "R4", "D4"}
SWITCH_LEGS = {h for ref, p in PARTS.items() if p["kind"] == "switch" for h in p["pins"].values()}

# ---- links on the front: bare wire along the holes, joining every hole it passes over ----------
# A link from a pin to the free hole next to it is a wire pad: the wire from the back comes up
# through that hole, and its own stripped end makes the link, soldered to the pin.
LINKS = []
J1_USED = (1, 3, 5, 7, 11, 13, 15, 17, 19, 21, 23, 25, 29, 31, 33, 37, 39, 2, 18, 22, 24, 26, 32, 36)
for p in J1_USED:  # each pin to its wire pad: odd pins (row 14) down to row 13, even pins (row 15) up to row 16
    col, row = PARTS["J1"]["pins"][str(p)]
    LINKS.append([(col, row), (col, row - 1 if row == c.J1_ROWS[0] else row + 1)])
LINKS.append([(1, 2), (23, 2)])  # the ground bus, along row 2
for ref, (col1, row) in c.HEADER_HOLES.items():
    title, names, nets, x1, z, value = fb.HEADERS[ref]
    for k, net in enumerate(nets):
        col = col1 - k
        if net == "GND":  # down (or up) to the ground bus
            LINKS.append([(col, row), (col, 2)])
        elif net not in ("KEY",):  # up to its wire pad
            LINKS.append([(col, row), (col, row + 1)])
LINKS += [
    [(14, 3), (16, 3)],  # KEY: the power key to both diodes' cathodes
    [(18, 3), (20, 3)],  # R1 to Q1's base
    [(14, 4), (15, 4)],  # wire pads for D1, D2, R1, Q1 and R2
    [(17, 4), (16, 4)],
    [(19, 4), (18, 4)],
    [(21, 4), (20, 4)],
    [(23, 4), (22, 4)],
    [(23, 3), (22, 3)],
    [(18, 1), (18, 2)],  # D3's cathode to the ground bus
    [(20, 0), (18, 0)],  # R3 to D3's anode
    [(19, 1), (20, 1)],  # R3's wire pad
    [(23, 1), (23, 2)],  # D4's cathode to the ground bus
    [(21, 0), (23, 0)],  # R4 to D4's anode
    [(22, 1), (21, 1)],  # R4's wire pad
]

# ---- insulated wire on the front, inside an opening: (net, points), joined at its two ends only ----
FRONT_WIRES = []

# ---- wires on the back, in the order to fit them: (net, from, to). Each end is a wire pad or a switch's leg. ----
J1 = PARTS["J1"]["pins"]


def pad(p):
    """J1 pin p's wire pad."""
    col, row = J1[str(p)]
    return (col, row - 1) if row == c.J1_ROWS[0] else (col, row + 1)


SW = {ref: PARTS[ref]["pins"] for ref in ("SW1", "SW2", "SW3", "SW4")}
# The wires come in layers, one job and one colour each, fitted in this order: each layer only
# needs the ones before it, and has its own beep test. A wire is (net, from, to), with "optional"
# after it for the two supply lights.
LAYERS = [
    ("ground", "Ground", "#212529", [
        ("GND", pad(39), SW["SW1"]["2"]), ("GND", SW["SW1"]["2"], (1, 2)),
        ("GND", pad(25), SW["SW2"]["2"]), ("GND", SW["SW2"]["2"], SW["SW3"]["2"]), ("GND", SW["SW3"]["2"], SW["SW4"]["2"]),
        ("GND", SW["SW4"]["2"], (21, 2)),
    ]),
    ("3v3", "3.3 V", "#f08c00", [
        ("3V3", pad(17), (12, 1)), ("3V3", pad(17), (9, 1)), ("3V3", pad(1), (2, 4)),
        ("3V3", pad(1), (19, 1), "optional"),
    ]),
    ("5v", "5 V", "#e03131", [
        ("5V", pad(2), (23, 4)),
        ("5V", pad(2), (22, 1), "optional"),
    ]),
    ("keys", "Keys", "#40c057", [
        ("PREV", pad(7), SW["SW1"]["1"]), ("PLAY", pad(11), SW["SW2"]["1"]), ("NEXT", pad(36), SW["SW3"]["1"]), ("BACK", pad(32), SW["SW4"]["1"]),
    ]),
    ("nfc", "NFC reader", "#ae3ec9", [
        ("SCLK", pad(23), (16, 1)), ("MOSI", pad(19), (14, 1)), ("MISO", pad(21), (15, 1)), ("NFC_CS", pad(26), (13, 1)),
    ]),
    ("screen", "Screen", "#1c7ed6", [
        ("SCLK", (16, 1), (6, 1)), ("MOSI", (14, 1), (7, 1)),
        ("LCD_CS", pad(24), (5, 1)), ("LCD_DC", pad(22), (4, 1)), ("LCD_RST", pad(13), (3, 1)), ("LCD_BL", pad(33), (2, 1)),
    ]),
    ("knob", "Knob", "#15aabf", [
        ("ENC_A", pad(29), (9, 4)), ("ENC_B", pad(31), (7, 4)), ("ENC_SW", pad(37), (6, 4)),
    ]),
    ("power", "Power key", "#a5652e", [
        ("SCL", pad(5), (17, 4)), ("POWER", pad(18), (14, 4)), ("LIGHT", pad(15), (19, 4)), ("LED_K", (21, 4), (11, 4)), ("LED_A", (23, 3), (12, 4)),
    ]),
    ("oled", "OLED", "#f06595", [
        ("SCL", (17, 4), (1, 4)), ("SDA", pad(3), (0, 4)),
    ]),
]
WIRES = [tuple(w[:3]) for key, title, colour, ws in LAYERS for w in ws]
WIRE_LAYER = [i for i, (key, title, colour, ws) in enumerate(LAYERS) for w in ws]
WIRE_OPTIONAL = {n for n, w in enumerate(w for key, title, colour, ws in LAYERS for w in ws) if "optional" in w[3:]}


# ---- checks ------------------------------------------------------------------------------------
def holes_on(link):
    (c0, r0), (c1, r1) = link
    assert c0 == c1 or r0 == r1, f"link {link} must run along a row or a column"
    if c0 == c1:
        return [(c0, r) for r in range(min(r0, r1), max(r0, r1) + 1)]
    return [(cc, r0) for cc in range(min(c0, c1), max(c0, c1) + 1)]


def nets_wanted():
    """ref -> {pin: net}, from board.py's parts, with the perfboard's pins."""
    out = {}
    for p in fb.PARTS:
        out[p["ref"]] = dict(p["nets"])
    return out


def check():
    problems = []
    wanted = nets_wanted()
    owner = {}  # hole -> (ref, pin)
    for ref, p in PARTS.items():
        for pin, h in p["pins"].items():
            if not (0 <= h[0] < COLS and 0 <= h[1] < ROWS):
                problems.append(f"{ref}.{pin} at {h} is off the board")
            if h in owner:
                problems.append(f"{ref}.{pin} and {'.'.join(owner[h])} share hole {name(h)}")
            owner[h] = (ref, pin)

    # every hole that is joined to something: links on the front, wire ends on the back
    parent = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def join(a, b):
        parent[find(a)] = find(b)

    front = set()  # holes with solder on the front
    for link in LINKS:
        hs = holes_on(link)
        front.update(hs)
        for a, b in zip(hs, hs[1:]):
            join(a, b)
    for a_pin in J1_USED:  # the Pi joins its own pins that carry the same supply
        for b_pin in J1_USED:
            if a_pin < b_pin and fb.PI_PINS[a_pin] == fb.PI_PINS[b_pin]:
                join(PARTS["J1"]["pins"][str(a_pin)], PARTS["J1"]["pins"][str(b_pin)])
    for net, pts in FRONT_WIRES:
        join(pts[0], pts[-1])
        front.update((pts[0], pts[-1]))
    ends = []
    for net, a, b in WIRES:
        join(a, b)
        ends += [a, b]
    used = set(parent) | set(owner)

    # what each group of joined holes carries
    groups = {}
    for h, (ref, pin) in owner.items():
        if pin.startswith("-"):
            if h in parent and find(h) != h or any(h in holes_on(l) for l in LINKS) or h in ends:
                problems.append(f"{ref}'s spare leg {name(h)} must stay free")
            continue
        net = wanted[ref].get(pin)
        if ref == "J1" and int(pin) not in J1_USED:
            if h in parent and find(h) != h:
                problems.append(f"J1 pin {pin} is not used but is joined to something")
            continue
        if net is None:
            problems.append(f"{ref}.{pin} has no net in board.py")
            continue
        groups.setdefault(find(h), set()).add(net)
    for g, nets in groups.items():
        if len(nets) > 1:
            problems.append("these nets are joined: " + ", ".join(sorted(nets)))
    for net in {n for pins in wanted.values() for n in pins.values() if n}:
        if net.startswith("unconnected") or net is None:
            continue
        pins = [h for h, (ref, pin) in owner.items() if not pin.startswith("-") and wanted[ref].get(pin) == net and not (ref == "J1" and int(pin) not in J1_USED)]
        if not pins:
            continue
        if len({find(h) for h in pins}) > 1:
            problems.append(f"{net} is split: " + " / ".join(sorted({name(h) for h in pins})))
    for net, a, b in WIRES:
        for h in (a, b):
            if h in owner:
                ref, pin = owner[h]
                if not pin.startswith("-") and wanted[ref].get(pin) != net and not (ref == "J1"):
                    problems.append(f"the {net} wire ends on {ref}.{pin}, which is {wanted[ref].get(pin)}")
    # every wire ends on a switch's leg or on a wire pad: a free hole linked to one pin next to it
    for net, a, b in WIRES:
        for h in (a, b):
            if h in SWITCH_LEGS:
                continue
            if h in owner:
                problems.append(f"the {net} wire ends in {name(h)}, a hole with a part's lead in it, not a wire pad")
                continue
            pins = {hh for link in LINKS if h in holes_on(link) for hh in holes_on(link) if hh in owner and abs(hh[0] - h[0]) + abs(hh[1] - h[1]) == 1}
            if not pins and not any(h in holes_on(link) and len(holes_on(link)) > 8 for link in LINKS):
                problems.append(f"the {net} wire's end {name(h)} is not next to the pin it serves")
    # every J1 pin that is wired carries what the Pi has on it
    for p in J1_USED:
        if fb.PI_PINS[p] is None:
            problems.append(f"J1 pin {p} is wired but the Pi has nothing on it")

    # joints on the front must sit over an opening in the spacer: the switches' legs are soldered on the back
    switch_legs = {h for ref, p in PARTS.items() if p["kind"] == "switch" for h in p["pins"].values()}
    joints = (front | {h for h, (ref, pin) in owner.items() if ref not in ("SW1", "SW2", "SW3", "SW4")} | set(ends)) - switch_legs
    for h in sorted(joints):
        x, z = xz(h)
        if not any(x0 + 0.9 <= x <= x1 - 0.9 and z0 + 0.9 <= z <= z1 - 0.9 for x0, z0, x1, z1 in c.BOARD_POCKETS):
            problems.append(f"joint {name(h)} is not over an opening in the spacer")
    for net, pts in FRONT_WIRES:
        for p in pts:
            x, z = c.GRID_X0 + p[0] * c.PITCH, c.GRID_Z0 + p[1] * c.PITCH
            if not any(x0 + 0.6 <= x <= x1 - 0.6 and z0 + 0.6 <= z <= z1 - 0.6 for x0, z0, x1, z1 in c.BOARD_POCKETS):
                problems.append(f"the {net} wire on the front leaves the spacer's openings")
    # nothing in or next to a screw hole
    for sx, sz in c.BOARD_SCREWS:
        for h in used:
            x, z = xz(h)
            if abs(x - sx) < 3.0 and abs(z - sz) < 3.0:
                problems.append(f"hole {name(h)} is too close to the screw at {sx}, {sz}")

    # room on the back: every part's body against every other's, and wire ends not under a body
    shapes = footprints()
    names_ = list(shapes)
    for i, a in enumerate(names_):
        for b in names_[i + 1 :]:
            if {a, b} != {"J1", "J1 plug"} and overlap(shapes[a], shapes[b]):
                problems.append(f"{a} and {b} would touch on the back")
    for h in set(ends):
        x, z = xz(h)
        for ref, s in shapes.items():
            if ref in ("J1 plug",):
                continue
            if inside(s, x, z, -0.2) and not (h in PARTS.get(ref, {}).get("pins", {}).values() and h != PARTS[ref].get("body")):
                problems.append(f"a wire ends on {name(h)}, under {ref}")
    return problems


# ---- room on the back: rectangles x0, z0, x1, z1 and circles (x, z, r) --------------------------------
def footprints():
    out = {}
    for ref, p in PARTS.items():
        pts = [xz(h) for k, h in p["pins"].items()]
        xs, zs = [x for x, z in pts], [z for x, z in pts]
        if p["kind"] in ("header", "j1"):
            out[ref] = ("rect", min(xs) - 1.25, min(zs) - 1.25, max(xs) + 1.25, max(zs) + 1.25)  # side by side, two headers just meet
        elif p["kind"] == "resistor":
            out[ref] = ("circle", *xz(p["body"]), 1.25)
        elif p["kind"] == "diode":
            out[ref] = ("circle", *xz(p["body"]), 0.95)
        elif p["kind"] == "led":
            out[ref] = ("circle", sum(xs) / 2, sum(zs) / 2, 1.9)
        elif p["kind"] == "to92":
            cx, cz = xz(p["pins"]["1"])
            out[ref] = ("rect", cx - 1.75, cz - 2.3, cx + 1.75, cz + 2.3)
    x0, x1 = c.PI_HEADER_X - 29.5, c.PI_HEADER_X + 29.5  # the ribbon's plug on J1 overhangs it, 2.5 mm off the board
    out["J1 plug"] = ("rect", x0, c.J1_Z - 4.5, x1, c.J1_Z + 4.5)
    for i, (x, z) in enumerate(c.BOARD_SCREWS):
        out[f"screw {i + 1}"] = ("circle", x, z, 1.9)
    return out


def overlap(a, b):
    if a[0] == "rect" and b[0] == "rect":
        return a[1] < b[3] and b[1] < a[3] and a[2] < b[4] and b[2] < a[4]
    if a[0] == "circle" and b[0] == "circle":
        return (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2 < (a[3] + b[3]) ** 2
    r, s = (a, b) if a[0] == "rect" else (b, a)
    dx = max(r[1] - s[1], 0, s[1] - r[3])
    dz = max(r[2] - s[2], 0, s[2] - r[4])
    return dx * dx + dz * dz < s[3] * s[3]


def inside(s, x, z, grow=0.0):
    if s[0] == "rect":
        return s[1] - grow <= x <= s[3] + grow and s[2] - grow <= z <= s[4] + grow
    return (x - s[1]) ** 2 + (z - s[2]) ** 2 <= (s[3] + grow) ** 2


# ---- wire routes, for the drawing ------------------------------------------------------------------------
# Each wire is drawn along its own lane between the holes, so no two lie on top of each other. The real
# wire can take any path that goes round the headers' plastic, never over it, since the leads' plugs sit
# there. A lane is named until it gets a place: MID, a row behind the keys; CH, the channel between the two
# rows of headers; T4, above the upper row of headers; T16, above J1; R7, below the switches' lower legs;
# L, left of everything; E, right of J1; G4 and G10, the gaps in the upper row of headers; G16, beside D2.
SLOTS = {
    "MID": [r + d for r in range(12, 5, -1) for d in (0.38, 0.5, 0.62) if 6.3 < r + d < 12.45],
    "CH": [1.3, 1.4, 1.5, 1.6, 1.7],
    "T4": [4.5, 4.62, 4.74, 4.86],
    "T16": [16.42, 16.54, 16.66, 16.78, 16.9],
    "R7": [6.5, 6.62],
    "L": [-0.6, -0.75, -0.9, -1.05, -1.2, -1.35, -1.5, -1.65, -1.8],
    "E": [20.38, 20.5, 20.62],
    "G4": [3.75, 3.92, 4.08, 4.25],
    "G10": [9.7, 9.85, 10.0, 10.15, 10.3],
    "G16": [16.47, 16.6, 16.73],
}
BASE = {"MID": 9.0, "CH": 1.5, "T4": 4.6, "T16": 16.5, "R7": 6.55, "L": -1.0, "E": 20.5, "G4": 4.0, "G10": 10.0, "G16": 16.6}


def skeleton(a, b):
    """Points from a to b; a coordinate given as a lane's name gets its place later."""
    (ca, ra), (cb, rb) = a, b
    if rb > ra or (rb == ra and cb > ca):
        return list(reversed(skeleton(b, a)))
    if ca == cb and not (a in SWITCH_LEGS or b in SWITCH_LEGS):
        return [a, b]  # straight down its own column
    pts = [a]
    if ra >= 13:  # from J1's wire pads
        if ra == 16:  # above J1: round the end of its plastic first
            x = "E" if ca >= 10 else "L"
            pts += [(ca, "T16"), (x, "T16")]
        else:
            x = ca + 0.62
            pts += [(x, 12.62)]
        if b in SWITCH_LEGS or rb >= 3:
            t = cb + 0.38
            pts += [(x, "MID"), (t, "MID"), (t, rb + 0.42), b]
        elif cb >= 17:  # a wire pad among the small parts, below the upper row's headers: straight down beside it
            t = cb + 0.62
            pts += [(x, "MID"), (t, "MID"), (t, rb + 0.45), b]
        elif x == "L" and cb <= 9:
            pts += [("L", "CH"), (cb, "CH"), b]
        else:
            g = "G4" if cb <= 6 else "G16" if cb >= 14 else "G10"  # G16: past D2, for the reader's header
            if rb == 2:  # the ground bus, just below the gap
                pts += [(x, "MID"), (g, "MID"), (g, rb + 0.4), b]
            else:
                pts += [(x, "MID"), (g, "MID"), (g, "CH"), (cb, "CH"), b]
    elif ra in (7, 10):  # from a switch's leg: along below the switches, or down to the ground bus
        if rb == ra:
            pts += [(ca, "R7"), (cb, "R7"), b]
        elif ca >= 12:  # straight down beside it, between Q1 and R2
            pts += [(ca + 0.38, ra - 0.4), (ca + 0.38, rb + 0.45), b]
        else:
            pts += [("L", ra), ("L", rb), b]
    elif ra >= 3 and rb >= 3:
        pts += [(ca, "T4"), (cb, "T4"), b]
    elif ra >= 3 and ca >= 22:  # down the right-hand edge, above the screw
        pts += [(ca + 0.55, ra), (ca + 0.55, "CH"), (cb, "CH"), b]
    elif ra >= 3:
        pts += [(ca, "T4"), ("G4", "T4"), ("G4", "CH"), (cb, "CH"), b]
    else:
        pts += [(ca, "CH"), (cb, "CH"), b]
    return pts


def routes():
    """Every wire's points on the grid, with its lanes placed so that no two run along each other."""
    skel = [skeleton(a, b) for net, a, b in WIRES]
    placed = {}  # (wire, lane) -> value
    taken = {g: [] for g in SLOTS}  # lane -> [(slot, lo, hi)]

    def base(v):
        return BASE[v] if isinstance(v, str) else v

    uses = []  # (wire, lane, lo, hi, least)
    for i, pts in enumerate(skel):
        for p, q in zip(pts, pts[1:]):
            for axis in (0, 1):
                if isinstance(p[axis], str) and p[axis] == q[axis]:
                    lane = p[axis]
                    span = sorted((base(p[1 - axis]), base(q[1 - axis])))
                    least = max((h[1] + 0.5 for h in (pts[0], pts[-1]) if h in SWITCH_LEGS and lane == "MID"), default=-99)  # cross above a switch's leg
                    uses.append((i, lane, span[0], span[1], least))
    # Wires to a switch's leg must cross above it, so they go first and take the highest rows behind
    # the keys; the rest fill those rows from the bottom up, the longest first.
    # Elsewhere, taking them from the left gives each lane the fewest rows it can have.
    for i, lane, lo, hi, least in sorted(uses, key=lambda u: (-u[4], -(u[3] - u[2])) if u[1] == "MID" else (0, u[2])):
        if (i, lane) in placed:
            continue
        spans = [(lo2, hi2) for j, l2, lo2, hi2, _ in uses if j == i and l2 == lane]
        lo, hi = min(s[0] for s in spans), max(s[1] for s in spans)
        order = SLOTS[lane] if lane != "MID" or least > 0 else list(reversed(SLOTS[lane]))
        for slot in order:
            if slot < least:
                continue
            if all(not (lo - 0.3 < h2 and l2 < hi + 0.3) for s2, l2, h2 in taken[lane] if s2 == slot):
                placed[(i, lane)] = slot
                taken[lane].append((slot, lo, hi))
                break
        else:
            raise RuntimeError(f"no room for wire {i + 1} in lane {lane}")
    out = []
    for i, pts in enumerate(skel):
        out.append([tuple(placed[(i, v)] if isinstance(v, str) else v for v in p) for p in pts])
    return out


# ---- drawing --------------------------------------------------------------------------------------------
PCB, PAD, HOLE, CASING = "#2e6b45", "#c9a66b", "#f3f1ea", "#f8f9fa"
SCALE = 3.2  # sheet units per millimetre
# The build, step by step: what each picture adds. The wires go on one layer at a time.
STAGES = ["switches", "parts", "headers", "links"] + [f"wires-{key}" for key, title, colour, ws in LAYERS]
STAGE_TITLES = {
    "switches": "Key switches, on the front",
    "parts": "Small parts, from the back",
    "headers": "Headers, from the back",
    "links": "Bare links and the ground bus, on the front",
    **{f"wires-{key}": f"{'Key switch' if key == 'keys' else title} wires, on the back" for key, title, colour, ws in LAYERS},
}


def wire_colour(i):
    return LAYERS[WIRE_LAYER[i]][2]


class Board:
    """A sheet showing the board from one side. back=True mirrors it, as seen from behind."""

    def __init__(self, back, title):
        self.back = back
        w, h = c.BOARD_X[1] - c.BOARD_X[0], c.BOARD_Z[1] - c.BOARD_Z[0]
        self.m = (9.0, 15.0, 24.0)  # margins round the board, in mm: sides, top and bottom
        self.s = dw.Sheet((w + 2 * self.m[0]) * SCALE, (h + self.m[1] + self.m[2]) * SCALE, title)

    def X(self, x):
        u = c.BOARD_X[1] - x if self.back else x - c.BOARD_X[0]
        return (u + self.m[0]) * SCALE

    def Y(self, z):
        return (c.BOARD_Z[1] - z + self.m[1]) * SCALE

    def P(self, h):
        return self.X(c.GRID_X0 + h[0] * c.PITCH), self.Y(c.GRID_Z0 + h[1] * c.PITCH)

    def add(self, s):
        self.s.out.append(s)

    def text(self, x, y, s, size=2.0, anchor="middle", colour=dw.INK, weight=400):
        """size in millimetres on the board; y is the baseline."""
        self.s.text(x, y, s, size * SCALE, anchor, colour, weight)

    def label(self, h, s, size=1.3, colour="#ffffff", bg="#1f2221"):
        """A small label centred on a grid point, on a dark tag so it reads over wires."""
        x, y = self.P(h)
        w = (len(s) * 0.62 + 0.6) * size * SCALE
        hh = 1.35 * size * SCALE
        self.add(f'<rect x="{f(x - w / 2)}" y="{f(y - hh / 2)}" width="{f(w)}" height="{f(hh)}" rx="{f(hh / 3)}" fill="{bg}" opacity="0.85"/>')
        self.text(x, y + 0.36 * size * SCALE, s, size, colour=colour, weight=700)


def f(v):
    return dw.n(v)


def draw(back, stage="all"):
    """The board from one side: finished (stage "all"), or as it stands after one step of STAGES."""
    title = "NFC Player front board on perfboard, " + ("seen from the back" if back else "seen from the front") + ("" if stage == "all" else ": " + STAGE_TITLES[stage])
    b = Board(back, title)
    k = SCALE
    level = len(STAGES) if stage == "all" else STAGES.index(stage)
    x0, x1 = sorted((b.X(c.BOARD_X[0]), b.X(c.BOARD_X[1])))
    defs = f'<defs><g id="hole"><circle r="{f(0.8 * k)}" fill="{PAD}"/><circle r="{f(0.42 * k)}" fill="{HOLE}"/></g></defs>'
    b.add(f'<rect x="{f(x0)}" y="{f(b.Y(c.BOARD_Z[1]))}" width="{f(x1 - x0)}" height="{f(b.Y(c.BOARD_Z[0]) - b.Y(c.BOARD_Z[1]))}" rx="{f(0.6 * k)}" fill="{PCB}"/>')
    if not back:  # the openings in the spacer: joints and links go only inside them on this side
        for px0, pz0, px1, pz1 in c.BOARD_POCKETS:
            px0, px1, pz1 = max(px0, c.BOARD_X[0]), min(px1, c.BOARD_X[1]), min(pz1, c.BOARD_Z[1])
            xa, xb = sorted((b.X(px0), b.X(px1)))
            b.add(f'<rect x="{f(xa)}" y="{f(b.Y(pz1))}" width="{f(xb - xa)}" height="{f(b.Y(pz0) - b.Y(pz1))}" fill="#3f8a5b"/>')
        for kx in c.KEYS_X:
            xa, xb = sorted((b.X(kx - c.KEY_WIN_X), b.X(kx + c.KEY_WIN_X)))
            b.add(f'<rect x="{f(xa)}" y="{f(b.Y(c.CTRL_Z + c.KEY_WIN_Z))}" width="{f(xb - xa)}" height="{f(2 * c.KEY_WIN_Z * k)}" rx="{f(k)}" fill="none" stroke="#8fd1a6" stroke-width="{f(0.15 * k)}" stroke-dasharray="{f(0.8 * k)} {f(0.5 * k)}"/>')
    for col in range(COLS):
        for row in range(ROWS):
            x, y = b.P((col, row))
            b.add(f'<use href="#hole" x="{f(x)}" y="{f(y)}"/>')
    for ex in (c.BOARD_X[0] + c.PERF_MOUNT[0], c.BOARD_X[1] - c.PERF_MOUNT[0]):  # the long pads along the two ends, which nothing uses
        for row in range(1, ROWS - 1):
            z = c.GRID_Z0 + row * c.PITCH
            b.add(f'<rect x="{f(b.X(ex) - 0.9 * k)}" y="{f(b.Y(z) - 0.75 * k)}" width="{f(1.8 * k)}" height="{f(1.5 * k)}" rx="{f(0.6 * k)}" fill="{PAD}" opacity="0.55"/>')
    for sx, sz in c.BOARD_SCREWS:  # the corner holes, for the screws
        b.add(f'<circle cx="{f(b.X(sx))}" cy="{f(b.Y(sz))}" r="{f(c.PERF_MOUNT[2] / 2 * k)}" fill="#ffffff" stroke="{dw.INK}" stroke-width="{f(0.12 * k)}"/>')
    yt = b.Y(c.BOARD_Z[1])
    for row in range(ROWS):
        y = b.P((0, row))[1] + 0.6 * k
        for xx in (x0 - 3.5 * k, x1 + 3.5 * k):
            b.text(xx, y, ROW_LETTERS[row], 1.7, colour=dw.DIM, weight=600)
    for col in range(COLS):
        x = b.P((col, 0))[0]
        b.text(x, b.Y(c.BOARD_Z[0]) + 2.4 * k, str(COLS - col), 1.45, colour=dw.DIM, weight=600)
        b.text(x, yt - 1.6 * k, str(COLS - col), 1.45, colour=dw.DIM, weight=600)
    b.text(x0, yt - 8.5 * k, ("Seen from the back" if back else "Seen from the front") if stage == "all" else f"Step {level + 1}: {STAGE_TITLES[stage]}", 2.2, anchor="start", weight=700)
    (draw_back if back else draw_front)(b, stage, level)
    return b.s.svg(extra_head=defs)


def poly(b, pts, colour, width, extra=""):
    d = " ".join(f"{f(x)},{f(y)}" for x, y in pts)
    b.add(f'<polyline points="{d}" fill="none" stroke="{colour}" stroke-width="{f(width * SCALE)}" stroke-linecap="round" stroke-linejoin="round" {extra}/>')


def header_titles(b, plastic):
    """Each header's name; the lower row's pin names below the board, the upper row's on their plastic."""
    k = SCALE
    for ref, p in PARTS.items():
        if p["kind"] != "header":
            continue
        title, names, nets, x1, z, value = fb.HEADERS[ref]
        holes_ = list(p["pins"].values())
        cols = [h[0] for h in holes_]
        row = holes_[0][1]
        mid = ((min(cols) + max(cols)) / 2, row)
        tag = f"{ref} {value.lower()}"
        if row == 0:
            for pin, h in p["pins"].items():
                x, y = b.P(h)
                y0 = b.Y(c.BOARD_Z[0]) + 3.6 * k
                b.add(f'<text x="{f(x + 0.4 * k)}" y="{f(y0)}" font-size="{f(1.1 * k)}" text-anchor="end" fill="{dw.INK}" font-weight="700" style="{dw.FONT}" transform="rotate(-90 {f(x + 0.4 * k)} {f(y0)})">{names[int(pin) - 1]}</text>')
            x, y = b.P(mid)
            b.text(x, b.Y(c.BOARD_Z[0]) + 9.4 * k, tag, 1.5, weight=700)
        elif plastic:
            for pin, h in p["pins"].items():
                x, y = b.P(h)
                b.text(x, y - 0.45 * k, names[int(pin) - 1], 0.8, colour="#ffffff", weight=700)


def legend(b, s, line=0):
    b.text((b.X(c.BOARD_X[0]) + b.X(c.BOARD_X[1])) / 2, b.Y(c.BOARD_Z[0]) + (13.2 + 3.2 * line) * SCALE, s, 1.3, colour=dw.DIM)


def colour_key(b, upto=None):
    """A row of swatches naming each layer's colour."""
    k = SCALE
    items = [(title, colour) for i, (key, title, colour, ws) in enumerate(LAYERS) if upto is None or i <= upto]
    widths = [(len(t) * 0.62 + 3.2) * 1.3 * k for t, col in items]
    x = (b.X(c.BOARD_X[0]) + b.X(c.BOARD_X[1])) / 2 - sum(widths) / 2
    y = b.Y(c.BOARD_Z[0]) + 19.5 * k
    for (t, col), w in zip(items, widths):
        b.add(f'<line x1="{f(x)}" y1="{f(y - 0.45 * k)}" x2="{f(x + 2.2 * k)}" y2="{f(y - 0.45 * k)}" stroke="{col}" stroke-width="{f(0.7 * k)}" stroke-linecap="round"/>')
        b.text(x + 2.8 * k, y, t, 1.3, anchor="start", weight=600)
        x += w


def draw_wires(b, which, dim=()):
    """Wires on the back, by index; those in dim faint, the rest in their colour on a light casing."""
    k = SCALE
    paths = routes()
    for i in sorted(which, key=lambda i: i not in dim):
        pts = [b.P(h) for h in paths[i]]
        dash = f'stroke-dasharray="{f(0.9 * k)} {f(0.6 * k)}"' if i in WIRE_OPTIONAL else ""
        if i in dim:
            poly(b, pts, wire_colour(i), 0.3, f'opacity="0.3" {dash}')
        else:
            poly(b, pts, CASING, 0.56)
            poly(b, pts, wire_colour(i), 0.36, dash)
    for i in which:
        if i in dim:
            continue
        net, a, bb = WIRES[i]
        for h in (a, bb):
            x, y = b.P(h)
            b.add(f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(0.55 * k)}" fill="{wire_colour(i)}" stroke="#ffffff" stroke-width="{f(0.12 * k)}"/>')


def draw_back(b, stage, level):
    k = SCALE
    show_headers = level >= STAGES.index("headers")
    show_parts = level >= STAGES.index("parts")
    if show_headers:
        for ref, p in PARTS.items():  # headers' plastic
            if p["kind"] in ("header", "j1"):
                pts = [b.P(h) for h in p["pins"].values()]
                xs, ys = [x for x, y in pts], [y for x, y in pts]
                b.add(f'<rect x="{f(min(xs) - 1.25 * k)}" y="{f(min(ys) - 1.25 * k)}" width="{f(max(xs) - min(xs) + 2.5 * k)}" height="{f(max(ys) - min(ys) + 2.5 * k)}" rx="{f(0.3 * k)}" fill="#1f2221"/>')
                for h in p["pins"].values():
                    x, y = b.P(h)
                    b.add(f'<rect x="{f(x - 0.32 * k)}" y="{f(y - 0.32 * k)}" width="{f(0.64 * k)}" height="{f(0.64 * k)}" fill="#d6c98e"/>')
        x, y = b.P(PARTS["J1"]["pins"]["1"])
        b.add(f'<polygon points="{f(x)},{f(y + 0.55 * k)} {f(x - 0.6 * k)},{f(y + 1.15 * k)} {f(x + 0.6 * k)},{f(y + 1.15 * k)}" fill="#ffffff"/>')
        header_titles(b, plastic=True)
    for ref in ("SW1", "SW2", "SW3", "SW4"):  # switches: only their legs come through to this side
        for h in PARTS[ref]["pins"].values():
            x, y = b.P(h)
            b.add(f'<rect x="{f(x - 0.5 * k)}" y="{f(y - 0.5 * k)}" width="{f(k)}" height="{f(k)}" fill="#bfc4c7" stroke="{dw.INK}" stroke-width="{f(0.1 * k)}"/>')
    if show_parts:
        draw_small_parts(b)
    if stage == "all":
        draw_wires(b, range(len(WIRES)))
    elif stage.startswith("wires-"):
        now = STAGES.index(stage) - STAGES.index(f"wires-{LAYERS[0][0]}")
        draw_wires(b, [i for i in range(len(WIRES)) if WIRE_LAYER[i] <= now], dim={i for i in range(len(WIRES)) if WIRE_LAYER[i] < now})
    if show_parts:
        for ref, at in (("D1", (15, 2.4)), ("D2", (16, 2.4)), ("R1", (18, 2.4)), ("Q1", (20, 5.45)), ("R2", (22, 2.4)), ("R4", (21, -0.75)), ("R3", (20, -0.75))):
            b.label(at, ref, 1.15, bg="#3d4442" if ref in OPTIONAL else "#1f2221")
    for i, ref in enumerate(("SW1", "SW2", "SW3", "SW4")):
        b.label((7 * i + 1, 8.5), f"{ref} {fb.KEY_NAMES[i].lower()}", 1.25)
    if show_headers:
        b.label((c.J1_COLS[1] + 2.5, 14.5), "J1", 1.6)
        b.label((c.J1_COLS[1] + 2.5, 13.4), "pin 1 ▸", 1.1)
        for ref in ("J4", "J5", "J6"):
            col1, row = c.HEADER_HOLES[ref]
            n_ = len(fb.HEADERS[ref][1])
            b.label((col1 - (n_ - 1) / 2, 5.55), f"{ref} {fb.HEADERS[ref][5].lower()}", 1.3)
    if stage == "all":
        legend(b, "Dots: where each wire goes through the board, beside its pin. White: the corner holes, for the four M2 screws. Dashed: optional.", 0)
        colour_key(b)
    elif stage.startswith("wires-"):
        now = STAGES.index(stage) - STAGES.index(f"wires-{LAYERS[0][0]}")
        legend(b, "Bright: the wires for this step, each between two dots. Faint: those fitted already. Dashed: optional.", 0)
        colour_key(b, now)
    elif stage == "parts":
        legend(b, "Each part is drawn between the holes its leads go in. Resistors and diodes stand upright. Dashed: optional (the two supply lights).", 0)
    elif stage == "headers":
        legend(b, "The 40-pin header is a plain one: pin 1 at the triangle. The other headers' pin 1 is on the left, seen from here.", 0)


RESISTOR_BANDS = {"1 kΩ": ("#7b4a12", "#1f1f1f", "#d9480f"), "220 Ω": ("#d9480f", "#d9480f", "#7b4a12"), "2.2 kΩ": ("#d9480f", "#d9480f", "#d9480f")}  # brown black red; red red brown; red red red
GOLD = "#c9a227"


def lead_end(b, h):
    """A small ring where a part's lead goes into its hole."""
    x, y = b.P(h)
    b.add(f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(0.42 * SCALE)}" fill="#ffffff" stroke="#343a40" stroke-width="{f(0.13 * SCALE)}"/>')


def draw_small_parts(b):
    """The resistors, diodes, LEDs and transistor, each drawn between its holes: a lead from each
    hole to the body. The resistors and diodes stand upright on the board, so their bodies are
    shorter than they look here; the drawing shows which two holes each uses."""
    k = SCALE
    for ref, p in PARTS.items():
        kind = p["kind"]
        dash = f' stroke-dasharray="{f(0.4 * k)} {f(0.25 * k)}"' if ref in OPTIONAL else ""
        if kind in ("resistor", "diode"):
            (ax, ay), (bx, by) = b.P(p["pins"]["1"]), b.P(p["pins"]["2"])
            b.add(f'<line x1="{f(ax)}" y1="{f(ay)}" x2="{f(bx)}" y2="{f(by)}" stroke="#495057" stroke-width="{f(0.22 * k)}"/>')
            vertical = abs(ax - bx) < 1e-6
            length, width = (c.PITCH + 1.3) * k, (1.35 if kind == "resistor" else 1.15) * k  # across both holes, the lead ends drawn on top
            cx, cy = (ax + bx) / 2, (ay + by) / 2
            w, h = (width, length) if vertical else (length, width)
            fill, edge = ("#e9d8a6", "#8a6d3b") if kind == "resistor" else ("#b8643c", "#5c2e14")
            b.add(f'<rect x="{f(cx - w / 2)}" y="{f(cy - h / 2)}" width="{f(w)}" height="{f(h)}" rx="{f(min(w, h) / 2.2)}" fill="{fill}" stroke="{edge}" stroke-width="{f(0.12 * k)}"{dash}/>')
            ux, uy = ((bx - ax) / (abs(bx - ax) + abs(by - ay)), (by - ay) / (abs(bx - ax) + abs(by - ay)))  # from pin 1 towards pin 2
            if kind == "resistor":  # its value's colour bands, read from pin 1, then gold, between the lead ends
                for t, colour in zip((-0.62, -0.3, 0.02, 0.5), (*RESISTOR_BANDS[p["value"]], GOLD)):
                    px, py = cx + ux * t * k, cy + uy * t * k
                    bw, bh = (width - 0.1 * k, 0.22 * k) if vertical else (0.22 * k, width - 0.1 * k)
                    b.add(f'<rect x="{f(px - bw / 2)}" y="{f(py - bh / 2)}" width="{f(bw)}" height="{f(bh)}" fill="{colour}"/>')
            else:  # the cathode band, at pin 1's end, just inside its lead
                px, py = cx - ux * 0.62 * k, cy - uy * 0.62 * k
                bw, bh = (width - 0.06 * k, 0.32 * k) if vertical else (0.32 * k, width - 0.06 * k)
                b.add(f'<rect x="{f(px - bw / 2)}" y="{f(py - bh / 2)}" width="{f(bw)}" height="{f(bh)}" fill="#141414"/>')
            for h in p["pins"].values():
                lead_end(b, h)
        elif kind == "led":
            (kx_, ky_), (ax, ay) = b.P(p["pins"]["1"]), b.P(p["pins"]["2"])
            cx, cy = (kx_ + ax) / 2, (ky_ + ay) / 2
            colour = "#f08c00" if "orange" in p["value"] else "#e03131"
            b.add(f'<line x1="{f(kx_)}" y1="{f(ky_)}" x2="{f(ax)}" y2="{f(ay)}" stroke="#495057" stroke-width="{f(0.22 * k)}"/>')
            b.add(f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(1.55 * k)}" fill="{colour}" stroke="#5c1a1a" stroke-width="{f(0.14 * k)}"{dash}/>')
            for h in p["pins"].values():
                lead_end(b, h)
            side = 1 if b.back else -1
            b.text(ax + side * 1.45 * k, ay + 0.35 * k, "A", 1.0, colour="#ffffff", weight=800)  # the anode: the long leg
            b.text(cx + side * 0.05 * k, cy + 0.3 * k, ref, 0.8, colour="#ffffff", weight=800)
        elif kind == "to92":
            ex, ey = b.P(p["pins"]["2"])
            cx_, cy_ = b.P(p["pins"]["3"])
            flat = 1 if b.back else -1  # towards R1: right of Q1 seen from the back
            top, bot = min(ey, cy_) - 0.6 * k, max(ey, cy_) + 0.6 * k
            fx = ex + flat * 0.9 * k
            b.add(f'<path d="M {f(fx)} {f(top)} L {f(fx)} {f(bot)} A {f(2.4 * k)} {f((bot - top) / 2)} 0 0 {1 if flat > 0 else 0} {f(fx)} {f(top)} Z" fill="#2b2f2e" stroke="#000000" stroke-width="{f(0.12 * k)}" opacity="0.95"/>')
            for pin, lab in (("2", "E"), ("1", "B"), ("3", "C")):
                lead_end(b, p["pins"][pin])
                x, y = b.P(p["pins"][pin])
                b.text(x - flat * 1.05 * k, y + 0.35 * k, lab, 0.95, colour="#ffffff", weight=700)  # inside the body, clear of the wire pad beside it


def draw_front(b, stage, level):
    k = SCALE
    for i, ref in enumerate(("SW1", "SW2", "SW3", "SW4")):  # the switches, on this side
        kx = c.KEYS_X[i]
        xa, xb = sorted((b.X(kx - 3), b.X(kx + 3)))
        b.add(f'<rect x="{f(xa)}" y="{f(b.Y(c.CTRL_Z + 3))}" width="{f(xb - xa)}" height="{f(6 * k)}" rx="{f(0.4 * k)}" fill="#1f2221"/><circle cx="{f(b.X(kx))}" cy="{f(b.Y(c.CTRL_Z))}" r="{f(1.75 * k)}" fill="#8e3b2e"/>')
        b.label((7 * i + 1, 11.6), f"{ref} {fb.KEY_NAMES[i].lower()}", 1.25)
        if stage == "switches":  # where its four legs go
            for h in PARTS[ref]["pins"].values():
                x, y = b.P(h)
                b.add(f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(0.75 * k)}" fill="none" stroke="#ffd43b" stroke-width="{f(0.3 * k)}"/>')
    if level >= STAGES.index("links"):
        for ref, p in PARTS.items():  # joints: every lead but the switches', which are soldered on the back
            if p["kind"] == "switch":
                continue
            for pin, h in p["pins"].items():
                x, y = b.P(h)
                b.add(f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(0.72 * k)}" fill="#ced4da" stroke="#495057" stroke-width="{f(0.1 * k)}"/>')
        ends = {}
        for i, (net, a, bb) in enumerate(WIRES):
            for h in (a, bb):
                ends.setdefault(h, wire_colour(i))
        for link in LINKS:  # bare links in grey; a wire's own end, bent onto its pin, in its colour
            hs = holes_on(link)
            pts = [b.P(hs[0]), b.P(hs[-1])]
            colour = next((ends[h] for h in hs if h in ends and len(hs) == 2), None)
            if colour:
                if stage == "all":
                    poly(b, pts, CASING, 0.62)
                    poly(b, pts, colour, 0.4)
            elif stage == "links":
                poly(b, pts, CASING, 0.62)
                poly(b, pts, "#868e96", 0.3)
            else:
                poly(b, pts, "#f1f3f5", 0.5)
                poly(b, pts, "#868e96", 0.16)
        header_titles(b, plastic=False)
        b.label((c.J1_COLS[1] + 2.5, 14.5), "J1", 1.6)
        for ref in ("J4", "J5", "J6"):
            col1, row = c.HEADER_HOLES[ref]
            n_ = len(fb.HEADERS[ref][1])
            b.label((col1 - (n_ - 1) / 2, 5.55), f"{ref} {fb.HEADERS[ref][5].lower()}", 1.3)
        for ref, at in (("D1", (15, 5.45)), ("D2", (16, 5.45)), ("R1", (18, 5.45)), ("Q1", (20, 5.45)), ("R2", (22, 5.45)), ("R4", (21, -0.75)), ("R3", (20, -0.75)), ("D3", (18, -0.75)), ("D4", (23, -0.75))):
            b.label(at, ref, 0.95, bg="#3d4442" if ref in OPTIONAL else "#1f2221")
    if stage == "all":
        legend(b, "Coloured: each wire's own end, bent from its hole onto the pin beside it. Grey: bare links. Lighter green: the spacer's openings; joints only there.", 0)
        colour_key(b)
    elif stage == "switches":
        legend(b, "Yellow rings: the holes for each switch's four legs, in rows H and L. Solder them on the back.", 0)
    elif stage == "links":
        legend(b, "Grey: bare links, on this side. Lighter green: the spacer's openings; joints and links only there.", 0)


# ---- for the guide ----------------------------------------------------------------------------------
def describe(h):
    """What sits in a hole, for the wire list."""
    for ref, p in PARTS.items():
        for pin, hh in p["pins"].items():
            if hh == h:
                if p["kind"] == "switch":
                    return f"{ref} leg ({'ground' if pin == '2' else fb.KEY_NAMES[int(ref[2]) - 1].lower() + ' key'})"
                if p["kind"] == "header":
                    return f"{ref} {fb.HEADERS[ref][1][int(pin) - 1]}"
                if ref == "J1":
                    return f"J1 pin {pin}"
                lead = {"diode": {"1": "cathode", "2": "anode"}, "led": {"1": "cathode", "2": "anode"}, "to92": {"1": "base", "2": "emitter", "3": "collector"}}.get(p["kind"], {}).get(pin)
                if p["kind"] == "resistor":  # a resistor has no ends of its own: name the lead by where it is
                    lead = "upper lead" if hh[1] == max(q[1] for q in p["pins"].values()) else "lower lead"
                return f"{ref} {lead}" if lead else ref
    for link in LINKS:
        hs = holes_on(link)
        if h in hs:
            if len(hs) > 8:
                return "ground bus"
            for hh in hs:
                d = describe_part_only(hh) if hh != h else None
                if d:
                    return f"pad by {d}"
    return "free hole"


def describe_part_only(h):
    for ref, p in PARTS.items():
        for pin, hh in p["pins"].items():
            if hh == h and p["kind"] != "switch":
                if p["kind"] == "header":
                    return f"{ref} {fb.HEADERS[ref][1][int(pin) - 1]}"
                if ref == "J1":
                    return f"J1 pin {pin}"
                return ref
    return None


def served(h):
    """The pin a wire's end serves: the pin its wire pad is linked to, a switch's leg, or the ground bus."""
    if h in SWITCH_LEGS:
        ref = next(r for r, p in PARTS.items() if h in p["pins"].values())
        pin = next(k for k, v in PARTS[ref]["pins"].items() if v == h)
        return f"{ref} leg ({'ground' if pin == '2' else fb.KEY_NAMES[int(ref[2]) - 1].lower() + ' key'})"
    for link in LINKS:
        hs = holes_on(link)
        if h in hs:
            if len(hs) > 8:
                return "ground bus"
            for hh in hs:
                if hh != h and describe_part_only(hh):
                    return describe(hh)
    return "?"


def and_list(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def layer_steps():
    """[(key, title, colour, rows, checks)] for each layer of wires, in building order. A row is
    (number, signal, from hole, beside, to hole, beside, optional). checks: for each group of pins
    the wires so far join, the names of those pins, which should all beep to each other."""
    out, n = [], 0
    joined = {}

    def root(a):
        joined.setdefault(a, a)
        while joined[a] != a:
            a = joined[a]
        return a

    for li, (key, title, colour, ws) in enumerate(LAYERS):
        rows, touched = [], []
        for w in ws:
            net, a, b = w[:3]
            n += 1
            rows.append((n, net, name(a), served(a), name(b), served(b), "optional" in w[3:]))
            joined[root(served(a))] = root(served(b))
            touched += [served(a), served(b)]
        groups = {}
        for thing in list(joined):
            groups.setdefault(root(thing), []).append(thing)
        checks = []
        for r in dict.fromkeys(root(t) for t in touched):
            things = sorted(groups[r], key=lambda t: (not t.startswith("J1"), t != "ground bus", t))
            checks.append(things)
        out.append((key, title, colour, rows, checks))
    return out


def wire_groups():
    """[(title, rows, check text)], for anything that wants the wires as a list."""
    return [(title, [r[:6] for r in rows], "; ".join(and_list(t) for t in checks)) for key, title, colour, rows, checks in layer_steps()]


def wire_rows():
    return [r for title, rows, check in wire_groups() for r in rows]


def link_rows():
    """(holes, what) for every bare link on the front; the wires' own ends are in the wire list."""
    ends = {h for net, a, b in WIRES for h in (a, b)}
    out = []
    for link in LINKS:
        hs = holes_on(link)
        if len(hs) == 2 and (hs[0] in ends or hs[1] in ends):
            continue
        what = "ground bus: one bare wire along the row" if len(hs) > 8 else ", ".join(d for d in (describe_part_only(x) for x in hs) if d)
        if len(hs) <= 8 and any(len(holes_on(l)) > 8 and hs[-1] in holes_on(l) or hs[0] in holes_on(l) and len(holes_on(l)) > 8 for l in LINKS):
            what += " to the ground bus"
        out.append((f"{name(hs[0])} to {name(hs[-1])}", what))
    return out


def parts_rows(kinds=None):
    """(ref, part, holes, note) for the parts list, or only the parts of the given kinds."""
    out = []
    for ref, p in PARTS.items():
        if kinds and p["kind"] not in kinds:
            continue
        pins = p["pins"]
        if p["kind"] == "j1":
            where = f"rows {ROW_LETTERS[c.J1_ROWS[0]]} and {ROW_LETTERS[c.J1_ROWS[1]]}, columns {COLS - c.J1_COLS[1]} to {COLS - c.J1_COLS[0]}; pin 1 in {name(pins['1'])}"
        elif p["kind"] == "header":
            where = f"{name(pins[str(len(pins))])} to {name(pins['1'])}; pin 1 in {name(pins['1'])}"
        elif p["kind"] == "switch":
            where = "legs in " + ", ".join(sorted((name(h) for h in pins.values()), key=lambda s: (s[0], int(s[1:]))))
        elif p["kind"] == "to92":
            where = f"{name(pins['2'])} emitter, {name(pins['1'])} base, {name(pins['3'])} collector"
        elif p["kind"] in ("diode", "led"):
            where = f"{name(pins['1'])} cathode, {name(pins['2'])} anode"
        else:
            where = f"{name(p['body'])} and {name(next(h for h in pins.values() if h != p['body']))}"
        note = p["note"] + ("; " if p["note"] else "") + ("body over " + name(p["body"]) if p["kind"] in ("resistor",) else "")
        out.append((ref, p["value"], where, note.strip("; ")))
    return out


def step_files():
    """(stage, side, file name) for every step's picture, in building order."""
    out = []
    for n, stage in enumerate(STAGES, 1):
        side = "front" if stage in ("switches", "links") else "back"
        out.append((stage, side, f"perfboard-step-{n:02d}-{stage}.svg"))
    return out


def main():
    problems = check()
    FAB.mkdir(exist_ok=True)
    for old in FAB.glob("perfboard-step-*.svg"):
        old.unlink()
    for side in ("back", "front"):
        (FAB / f"perfboard-{side}.svg").write_text(draw(side == "back"))
    for stage, side, file in step_files():
        (FAB / file).write_text(draw(side == "back", stage))
    print(f"  {len(PARTS)} parts, {len(LINKS)} links on the front, {len(WIRES)} wires on the back in {len(LAYERS)} layers")
    print(f"  fab/perfboard-back.svg, fab/perfboard-front.svg and {len(STAGES)} step pictures")
    print("\n".join("PROBLEM: " + p for p in problems) or "No problems found.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
