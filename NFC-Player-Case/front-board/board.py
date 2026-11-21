"""Draws the NFC Player front board in KiCad from case.py: schematic, footprints, layout and copper.

Run it with the Python that comes with KiCad, from this folder:

    /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 board.py

It writes nfc-front-board.kicad_sch, .kicad_pcb and .kicad_pro, routes the copper with a
simple two-layer router, pours ground on both sides, then runs KiCad's electrical rules
check and design rules check and writes the files a board maker needs to fab/.

The board lies flat against the inside of the front panel, behind the four keys. The keys'
Kailh Choc switches plug into hot-swap sockets on its back. Everything else is through-hole,
also on the back, and soldered on the front; the panel has shallow pockets under those joints.
The 40-pin header takes a ribbon from the pins on top of the DAC, so the board sees every Pi pin.
"""

import heapq
import json
import math
import shutil
import subprocess
import sys
import uuid
from array import array
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import case as c  # noqa: E402
import sexpr  # noqa: E402

NAME = "nfc-front-board"
REVISION = "1"
KICAD = Path("/Applications/KiCad/KiCad.app/Contents")
CLI = KICAD / "MacOS" / "kicad-cli"
FOOTPRINTS = KICAD / "SharedSupport" / "footprints"
SYMBOLS = KICAD / "SharedSupport" / "symbols"
LOCAL_LIB = "NFC-Front-Board"
FAB = HERE / "fab"

# Board coordinates are the case's: x across the front, and y = TOP - z (KiCad's y runs down).
# The board's front (KiCad's top side) faces the panel, so KiCad's top view is the player seen from the front.
TOP = 60.0


def Y(z):
    return TOP - z


# ---- what is on the board ---------------------------------------------------------------
# The Pi's 40 pins, as they reach the board through the ribbon. None: not used here.
PI_PINS = {
    1: "3V3", 2: "5V", 3: "SDA", 4: "5V", 5: "SCL", 6: "GND", 7: "PREV", 8: None, 9: "GND", 10: None,
    11: "PLAY", 12: None, 13: "LCD_RST", 14: "GND", 15: "LIGHT", 16: None, 17: "3V3", 18: "POWER", 19: "MOSI", 20: "GND",
    21: "MISO", 22: "LCD_DC", 23: "SCLK", 24: "LCD_CS", 25: "GND", 26: "NFC_CS", 27: None, 28: None, 29: "ENC_A", 30: "GND",
    31: "ENC_B", 32: "BACK", 33: "LCD_BL", 34: "GND", 35: None, 36: "NEXT", 37: "ENC_SW", 38: None, 39: "GND", 40: None,
}
POWER_NETS = ("GND", "3V3", "5V")

# Headers on the back of the board, pin 1 first. Pin names are printed beside the pins.
HEADERS = {
    # ref: (title, pin names, nets, pin 1 x, z, value)
    "J2": ("LCD", ("VCC", "GND", "DIN", "CLK", "CS", "DC", "RST", "BL"), ("3V3", "GND", "MOSI", "SCLK", "LCD_CS", "LCD_DC", "LCD_RST", "LCD_BL"), 118.78, 9.5, "Screen"),
    "J3": ("NFC", ("SCK", "MISO", "MOSI", "SS", "VCC", "GND"), ("SCLK", "MISO", "MOSI", "NFC_CS", "3V3", "GND"), 140.7, 9.5, "NFC reader"),
    "J5": ("PWR", ("KEY", "GND", "LED+", "LED-"), ("KEY", "GND", "LED_A", "LED_K"), 108.62, 16.0, "Power key"),
    "J6": ("OLED", ("GND", "VCC", "SCL", "SDA"), ("GND", "3V3", "SCL", "SDA"), 123.62, 16.0, "OLED"),
    "J4": ("ENC", ("A", "C", "B", "SW", "SW"), ("ENC_A", "GND", "ENC_B", "ENC_SW", "GND"), 141.16, 16.0, "Knob"),
}
KEY_NAMES = ("PREV", "PLAY", "NEXT", "BACK")
KEY_NETS = ("PREV", "PLAY", "NEXT", "BACK")

PARTS = []  # filled in below: one dict per part
_UIDS = iter(range(1, 1_000_000))


def uid():
    """The same IDs on every run, so a rebuild only changes what really changed."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"nfc-front-board/{next(_UIDS)}"))


def part(ref, value, symbol, footprint, nets, at, side="back", rot=0.0, desc=""):
    PARTS.append({"ref": ref, "value": value, "symbol": symbol, "footprint": footprint, "nets": nets, "at": at, "side": side, "rot": rot, "desc": desc, "uuid": uid()})


part("J1", "Pi GPIO, ribbon from the DAC", ("Connector_Generic", "Conn_02x20_Odd_Even"), ("Connector_IDC", "IDC-Header_2x20_P2.54mm_Vertical"),
     {str(k): v for k, v in PI_PINS.items()}, (119.0, Y(46.0)), rot=90, desc="Shrouded 2x20 box header, 2.54 mm")
for i, (k, name, net) in enumerate(zip(c.KEYS_X, KEY_NAMES, KEY_NETS)):
    part(f"SW{i + 1}", f"{name.title()} key", ("Switch", "SW_Push"), (LOCAL_LIB, "Kailh_Choc_V1_Hotswap"), {"1": net, "2": "GND"}, (k, Y(c.CTRL_Z)), side="front",
         desc="Kailh Choc V1 switch in a CPG135001S30 hot-swap socket")
for ref, (title, names, nets, x1, z, value) in HEADERS.items():
    part(ref, value, ("Connector_Generic", f"Conn_01x{len(nets):02d}"), ("Connector_PinHeader_2.54mm", f"PinHeader_1x{len(nets):02d}_P2.54mm_Vertical"),
         {str(i + 1): n for i, n in enumerate(nets)}, (x1, Y(z)), desc="Straight pin header, 2.54 mm")
part("D1", "BAT43", ("Device", "D_Schottky"), ("Diode_THT", "D_DO-35_SOD27_P7.62mm_Horizontal"), {"1": "KEY", "2": "POWER"}, (147.5, 40.6), desc="Schottky diode, stripe (cathode) towards the key")
part("D2", "BAT43", ("Device", "D_Schottky"), ("Diode_THT", "D_DO-35_SOD27_P7.62mm_Horizontal"), {"1": "KEY", "2": "SCL"}, (147.5, 43.9), desc="Schottky diode, stripe (cathode) towards the key")
part("R1", "1k", ("Device", "R"), ("Resistor_THT", "R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal"), {"1": "LIGHT", "2": "LED_BASE"}, (147.5, 47.5), desc="Base resistor")
part("R2", "220", ("Device", "R"), ("Resistor_THT", "R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal"), {"1": "5V", "2": "LED_A"}, (147.5, 51.1), desc="Sets the power light's current. A wire link if the button's LED has its own resistor")
part("Q1", "2N3904", ("Transistor_BJT", "Q_NPN_EBC"), ("Package_TO_SOT_THT", "TO-92_Inline"), {"1": "GND", "2": "LED_BASE", "3": "LED_K"}, (159.8, 44.0), desc="Switches the power light from 5 V")


# ---- the Choc hot-swap footprint ------------------------------------------------------------
def choc_footprint():
    """Kailh PG1350 (Choc V1) on a CPG135001S30 socket, from Kailh's two drawings. Seen from the switch side."""
    f = lambda v: f"{v:g}"
    npth = [(0, 0, 3.4), (-5.5, 0, 1.9), (5.5, 0, 1.9), (0, 5.9, 3.0), (5, 3.8, 3.0)]
    lines = [
        f'(footprint "Kailh_Choc_V1_Hotswap" (version 20240108) (generator "board.py") (layer "F.Cu")',
        '  (descr "Kailh Choc V1 (PG1350) switch in a CPG135001S30 hot-swap socket on the back. Holes and pads from the Kailh drawings.")',
        '  (tags "kailh choc pg1350 hotswap")',
        '  (property "Reference" "SW**" (at 0 -9) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))',
        '  (property "Value" "Choc" (at 0 9.5) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))',
        '  (attr smd)',
        '  (fp_rect (start -7.5 -7.5) (end 7.5 7.5) (stroke (width 0.1) (type solid)) (fill no) (layer "F.Fab"))',
        '  (fp_rect (start -7.75 -7.75) (end 7.75 7.75) (stroke (width 0.05) (type solid)) (fill no) (layer "F.CrtYd"))',
        '  (fp_rect (start -4.85 1.2) (end 9.85 8.55) (stroke (width 0.05) (type solid)) (fill no) (layer "B.CrtYd"))',
        '  (fp_poly (pts (xy -4.75 2.3) (xy 1.5 2.3) (xy 2.6 1.3) (xy 9.75 1.3) (xy 9.75 6.2) (xy 3.5 6.2) (xy 2.4 7.25) (xy -4.75 7.25)) (stroke (width 0.1) (type solid)) (fill no) (layer "B.Fab"))',
    ]
    for x, y, d in npth:
        lines.append(f'  (pad "" np_thru_hole circle (at {f(x)} {f(y)}) (size {f(d)} {f(d)}) (drill {f(d)}) (layers "*.Cu" "*.Mask"))')
    lines.append('  (pad "1" smd rect (at -3.275 5.95) (size 2.6 2.6) (layers "B.Cu" "B.Paste" "B.Mask"))')
    lines.append('  (pad "2" smd rect (at 8.275 3.75) (size 2.6 2.6) (layers "B.Cu" "B.Paste" "B.Mask"))')
    lines.append(")")
    lib = HERE / f"{LOCAL_LIB}.pretty"
    lib.mkdir(exist_ok=True)
    (lib / "Kailh_Choc_V1_Hotswap.kicad_mod").write_text("\n".join(lines) + "\n")
    (HERE / "fp-lib-table").write_text(f'(fp_lib_table\n  (version 7)\n  (lib (name "{LOCAL_LIB}")(type "KiCad")(uri "${{KIPRJMOD}}/{LOCAL_LIB}.pretty")(options "")(descr "Parts drawn for this board"))\n)\n')


# ---- schematic ----------------------------------------------------------------------------
S = sexpr.Str
SCH_AT = {  # symbol origins on the sheet, mm (A4 landscape)
    "J1": (76.2, 101.6),
    "SW1": (152.4, 35.56), "SW2": (152.4, 45.72), "SW3": (152.4, 55.88), "SW4": (152.4, 66.04),
    "D1": (152.4, 86.36), "D2": (152.4, 96.52), "J5": (152.4, 114.3),
    "R1": (134.62, 152.4), "Q1": (160.02, 152.4), "R2": (190.5, 132.08),
    "J2": (243.84, 40.64), "J3": (243.84, 71.12), "J4": (243.84, 99.06), "J6": (243.84, 124.46),
}


def eff(size=1.27, hide=False, justify=None):
    e = ["effects", ["font", ["size", size, size]]]
    if justify:
        e.append(["justify", *justify])
    if hide:
        e.append(["hide", "yes"])
    return e


def schematic():
    root = uid()
    libs, cache = {}, {}
    for p in PARTS:
        lib, name = p["symbol"]
        key = f"{lib}:{name}"
        if key not in libs:
            sym = sexpr.library_symbol(SYMBOLS / f"{lib}.kicad_sym", name)
            sym = list(sym)
            sym[1] = S(key)
            libs[key] = sym
            pins = {}
            for unit in sexpr.find(sym, "symbol"):
                for pin in sexpr.find(unit, "pin"):
                    at = sexpr.find(pin, "at")[0]
                    number = sexpr.find(pin, "number")[0][1]
                    pins[str(number)] = (float(at[1]), float(at[2]), float(at[3]))
            cache[key] = pins
    out = [
        "kicad_sch", ["version", "20250114"], ["generator", S("eeschema")], ["generator_version", S("9.0")], ["uuid", S(root)], ["paper", S("A4")],
        ["title_block", ["title", S("NFC Player front board")], ["date", S(date.today().isoformat())], ["rev", S(REVISION)],
         ["comment", 1, S("Generated by front-board/board.py from case.py. Edit that, not this file.")],
         ["comment", 2, S("J1 pin numbers are the Pi's physical header pins, through a straight 40-way ribbon.")]],
        ["lib_symbols", *libs.values()],
    ]
    used = set()
    for p in PARTS:
        key = "{}:{}".format(*p["symbol"])
        sx, sy = SCH_AT[p["ref"]]
        props = [("Reference", p["ref"], (sx, sy - 7.62), False), ("Value", p["value"], (sx, sy + 7.62), False),
                 ("Footprint", "{}:{}".format(*p["footprint"]), (sx, sy), True), ("Datasheet", "", (sx, sy), True), ("Description", p["desc"], (sx, sy), True)]
        offsets = {"J1": ((1.27, -27.94), (1.27, 30.48)), "SW": ((0, -3.81), (0, 3.81)), "D": ((0, -3.81), (0, 3.81)),
                   "J": ((7.62, -1.27), (7.62, 1.27)), "R": ((5.08, -1.27), (5.08, 1.27)), "Q": ((10.16, -1.27), (10.16, 1.27))}
        kind = p["ref"] if p["ref"] == "J1" else p["ref"].rstrip("0123456789")
        (rx, ry), (vx, vy) = offsets[kind]
        props[0] = ("Reference", p["ref"], (sx + rx, sy + ry), False)
        props[1] = ("Value", p["value"], (sx + vx, sy + vy), False)
        sym = ["symbol", ["lib_id", S(key)], ["at", sx, sy, 0], ["unit", 1], ["exclude_from_sim", "no"], ["in_bom", "yes"], ["on_board", "yes"], ["dnp", "no"], ["uuid", S(p["uuid"])]]
        for name, value, (px, py), hide in props:
            sym.append(["property", S(name), S(value), ["at", round(px, 2), round(py, 2), 0], eff(hide=hide)])
        for number in cache[key]:
            sym.append(["pin", S(number), ["uuid", S(uid())]])
        sym.append(["instances", ["project", S(NAME), ["path", S("/" + root), ["reference", S(p["ref"])], ["unit", 1]]]])
        out.append(sym)
        for number, (px, py, angle) in cache[key].items():
            ax, ay = round(sx + px, 2), round(sy - py, 2)
            net = p["nets"].get(number)
            if net is None:
                out.append(["no_connect", ["at", ax, ay], ["uuid", S(uid())]])
                continue
            used.add(net)
            label_angle = {0: 180, 180: 0, 90: 270, 270: 90}[int(angle) % 360]
            justify = {0: ["left", "bottom"], 180: ["right", "bottom"], 90: ["left", "bottom"], 270: ["right", "bottom"]}[label_angle]
            out.append(["global_label", S(net), ["shape", "passive"], ["at", ax, ay, label_angle], ["fields_autoplaced", "yes"], eff(justify=[justify[0]]), ["uuid", S(uid())],
                        ["property", S("Intersheetrefs"), S("${INTERSHEET_REFS}"), ["at", ax, ay, 0], eff(hide=True)]])
    notes = [
        (20.32, 160.02, "Keys and the knob pull a GPIO pin to ground; the Pi's own pull-ups hold them high."),
        (20.32, 165.1, "The power key reaches GPIO 24 and GPIO 3 through D1 and D2. GPIO 3 is the only pin that wakes a Pi that has shut down."),
        (20.32, 170.18, "GPIO 22 lights the key's LED through Q1 from 5 V. config.txt switches it on at boot and the shutdown hook switches it off."),
        (20.32, 175.26, "R2 sets the LED current (about 10-13 mA). Fit a wire link instead if the button's LED has its own resistor (rated 5 V or 6 V)."),
        (20.32, 180.34, "J6 is for the 0.91-inch OLED instead of the 2-inch screen. Fit one or the other."),
    ]
    for x, y, text in notes:
        out.append(["text", S(text), ["exclude_from_sim", "no"], ["at", x, y, 0], eff(justify=["left", "bottom"]), ["uuid", S(uid())]])
    out.append(["sheet_instances", ["path", S("/"), ["page", S("1")]]])
    out.append(["embedded_fonts", "no"])
    (HERE / f"{NAME}.kicad_sch").write_text(sexpr.dump(out) + "\n")
    return used


# ---- project ------------------------------------------------------------------------------
def project():
    base = json.loads((KICAD / "SharedSupport/template/RaspberryPi-HAT/RaspberryPi-HAT.kicad_pro").read_text())
    rules = base["board"]["design_settings"]["rules"]
    rules.update({"min_clearance": 0.2, "min_copper_edge_clearance": 0.3, "min_track_width": 0.25, "min_via_diameter": 0.6,
                  "min_through_hole_diameter": 0.3, "min_hole_to_hole": 0.25, "min_hole_clearance": 0.25, "min_via_annular_width": 0.13, "min_resolved_spokes": 1})
    classes = base["net_settings"]["classes"]
    for cl in classes:
        if cl["name"] == "Default":
            cl.update({"clearance": 0.2, "track_width": 0.3, "via_diameter": 0.6, "via_drill": 0.3})
        if cl["name"] == "Power":
            cl.update({"clearance": 0.2, "track_width": 0.5, "via_diameter": 0.6, "via_drill": 0.3})
    base["net_settings"]["netclass_patterns"] = [{"netclass": "Power", "pattern": n} for n in POWER_NETS]
    base["net_settings"]["netclass_assignments"] = None
    base["meta"]["filename"] = f"{NAME}.kicad_pro"
    base["sheets"] = []
    base["boards"] = []
    base.get("libraries", {}).update({"pinned_footprint_libs": [], "pinned_symbol_libs": []})
    (HERE / f"{NAME}.kicad_pro").write_text(json.dumps(base, indent=2) + "\n")


# ---- router -------------------------------------------------------------------------------
GRID = 0.2
CLEAR = 0.2  # copper to copper, as in the rules
MARGIN = 0.07  # extra the router keeps, for the grid
EDGE = 0.3
VIA, VIA_DRILL = 0.6, 0.3


def width(net):
    return 0.5 if net in POWER_NETS else 0.3


class Shape:
    def __init__(self, net, layers, kind, *p):
        self.net, self.layers, self.kind, self.p = net, layers, kind, p

    def dist(self, x, y):
        if self.kind == "circle":
            cx, cy, r = self.p
            return max(0.0, math.hypot(x - cx, y - cy) - r)
        if self.kind == "rect":
            x0, y0, x1, y1 = self.p
            dx = max(x0 - x, 0.0, x - x1)
            dy = max(y0 - y, 0.0, y - y1)
            return math.hypot(dx, dy)
        x0, y0, x1, y1, hw = self.p
        vx, vy = x1 - x0, y1 - y0
        L = vx * vx + vy * vy
        t = 0.0 if L == 0 else max(0.0, min(1.0, ((x - x0) * vx + (y - y0) * vy) / L))
        return max(0.0, math.hypot(x - x0 - t * vx, y - y0 - t * vy) - hw)

    def box(self):
        if self.kind == "circle":
            cx, cy, r = self.p
            return cx - r, cy - r, cx + r, cy + r
        if self.kind == "rect":
            return self.p
        x0, y0, x1, y1, hw = self.p
        return min(x0, x1) - hw, min(y0, y1) - hw, max(x0, x1) + hw, max(y0, y1) + hw


class Router:
    def __init__(self, outline, shapes, pads):
        self.x0, self.y0, self.x1, self.y1 = outline
        self.nx = int(round((self.x1 - self.x0) / GRID)) + 1
        self.ny = int(round((self.y1 - self.y0) / GRID)) + 1
        self.N = self.nx * self.ny
        self.shapes = shapes  # every piece of copper and every hole
        self.pads = pads  # net: [(shape, name)]
        self.tracks, self.vias, self.failed = [], [], []
        self.holes = []  # (x, y, radius) of every drilled hole: vias keep clear of them all

    def xy(self, i, j):
        return self.x0 + i * GRID, self.y0 + j * GRID

    def paint(self, grid, shape, r):
        bx0, by0, bx1, by1 = shape.box()
        i0, i1 = max(0, int((bx0 - r - self.x0) / GRID)), min(self.nx - 1, int((bx1 + r - self.x0) / GRID) + 1)
        j0, j1 = max(0, int((by0 - r - self.y0) / GRID)), min(self.ny - 1, int((by1 + r - self.y0) / GRID) + 1)
        for j in range(j0, j1 + 1):
            y = self.y0 + j * GRID
            row = j * self.nx
            for i in range(i0, i1 + 1):
                if not grid[row + i] and shape.dist(self.x0 + i * GRID, y) <= r:
                    grid[row + i] = 1

    def blocked(self, net, r, edge, holes=False):
        cache = self.__dict__.setdefault("_edges", {})
        if edge not in cache:
            g = bytearray(self.N)
            for j in range(self.ny):
                y = self.y0 + j * GRID
                for i in range(self.nx):
                    x = self.x0 + i * GRID
                    if min(x - self.x0, self.x1 - x, y - self.y0, self.y1 - y) < edge:
                        g[j * self.nx + i] = 1
            cache[edge] = bytes(g)
        grids = [bytearray(cache[edge]), bytearray(cache[edge])]
        for s in self.shapes:
            if s.net == net and s.net is not None:
                continue
            for layer in s.layers:
                self.paint(grids[layer], s, r)
        if holes:
            for hx, hy, hr in self.holes:
                s = Shape(None, (0, 1), "circle", hx, hy, hr)
                for layer in (0, 1):
                    self.paint(grids[layer], s, VIA_DRILL / 2 + 0.25 + MARGIN)
        return grids

    def cells(self, shape):
        out = []
        bx0, by0, bx1, by1 = shape.box()
        for j in range(max(0, int((by0 - self.y0) / GRID)), min(self.ny, int((by1 - self.y0) / GRID) + 2)):
            for i in range(max(0, int((bx0 - self.x0) / GRID)), min(self.nx, int((bx1 - self.x0) / GRID) + 2)):
                if shape.dist(*self.xy(i, j)) <= 0.0:
                    out.extend(layer * self.N + j * self.nx + i for layer in shape.layers)
        if not out:  # a pad smaller than a grid cell: take the nearest cell
            cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
            i, j = int(round((cx - self.x0) / GRID)), int(round((cy - self.y0) / GRID))
            out = [layer * self.N + j * self.nx + i for layer in shape.layers]
        return out

    def route(self, net):
        w = width(net)
        track = self.blocked(net, w / 2 + CLEAR + MARGIN, EDGE + w / 2)
        via = self.blocked(net, VIA / 2 + CLEAR + MARGIN, EDGE + VIA / 2, holes=True)
        free = track[0] + track[1]  # one array over both layers: 0 is free
        via_ok = bytes(1 if not (via[0][k] or via[1][k]) else 0 for k in range(self.N))
        pads = self.pads[net]
        tree = set(self.cells(pads[0][0]))
        left = list(range(1, len(pads)))
        N, nx = self.N, self.nx
        while left:
            targets = {}
            for k in left:
                for cell in self.cells(pads[k][0]):
                    targets[cell] = k
            goals = []
            for k in left:
                bx0, by0, bx1, by1 = pads[k][0].box()
                goals.append(((bx0 + bx1) / 2, (by0 + by1) / 2))

            def h(n):
                rest = n % N
                x, y = self.xy(rest % nx, rest // nx)
                return min(max(abs(x - gx), abs(y - gy)) + 0.414 * min(abs(x - gx), abs(y - gy)) for gx, gy in goals) / GRID

            INF = float("inf")
            g = array("d", [INF]) * (2 * N)
            came = array("i", [-1]) * (2 * N)
            heap = []
            for n in tree:
                g[n] = 0.0
                heapq.heappush(heap, (h(n), n))
            found = None
            steps = ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0), (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414))
            while heap:
                f, n = heapq.heappop(heap)
                gn = g[n]
                if f - h(n) > gn + 1e-9:
                    continue
                if n in targets and n not in tree:
                    found = n
                    break
                layer, rest = divmod(n, N)
                j, i = divmod(rest, nx)
                for di, dj, cost in steps:
                    ii, jj = i + di, j + dj
                    if not (0 <= ii < nx and 0 <= jj < self.ny):
                        continue
                    m = layer * N + jj * nx + ii
                    if free[m] and m not in targets and m not in tree:
                        continue
                    if di and dj and (free[layer * N + j * nx + ii] or free[layer * N + jj * nx + i]):
                        continue
                    # each side has a preferred direction, so tracks fall into tidy lanes
                    if (layer == 0 and dj and not di) or (layer == 1 and di and not dj):
                        cost *= 1.25
                    ng = gn + cost
                    if ng < g[m]:
                        g[m], came[m] = ng, n
                        heapq.heappush(heap, (ng + h(m), m))
                if via_ok[rest]:
                    m = (1 - layer) * N + rest
                    if not free[m] or m in tree or m in targets:
                        ng = gn + 8.0
                        if ng < g[m]:
                            g[m], came[m] = ng, n
                            heapq.heappush(heap, (ng + h(m), m))
            if found is None:
                self.failed.append(net)
                return False
            path = [found]
            while came[path[-1]] != -1:
                path.append(came[path[-1]])
            path.reverse()
            self.lay(net, path)
            k = targets[found]
            tree.update(path)
            tree.update(self.cells(pads[k][0]))
            left.remove(k)
        return True

    def stitch(self, net, pitch):
        """Vias on a grid wherever they fit, tying the two ground pours together."""
        via = self.blocked(net, VIA / 2 + CLEAR + 0.3, EDGE + VIA / 2 + 0.3, holes=True)
        step = int(round(pitch / GRID))
        for j in range(step // 2, self.ny, step):
            for i in range(step // 2, self.nx, step):
                k = j * self.nx + i
                if not via[0][k] and not via[1][k]:
                    x, y = self.xy(i, j)
                    self.vias.append((net, round(x, 3), round(y, 3)))
                    self.shapes.append(Shape(net, (0, 1), "circle", x, y, VIA / 2))
                    self.holes.append((x, y, VIA_DRILL / 2))

    def lay(self, net, path):
        N, w = self.N, width(net)
        pts = []
        for n in path:
            layer, rest = divmod(n, N)
            x, y = self.xy(rest % self.nx, rest // self.nx)
            pts.append((layer, round(x, 3), round(y, 3)))
        run = [pts[0]]
        for p in pts[1:]:
            if p[0] != run[-1][0]:
                self.add_run(net, run, w)
                self.vias.append((net, p[1], p[2]))
                self.shapes.append(Shape(net, (0, 1), "circle", p[1], p[2], VIA / 2))
                self.holes.append((p[1], p[2], VIA_DRILL / 2))
                run = [p]
            else:
                run.append(p)
        self.add_run(net, run, w)

    def add_run(self, net, run, w):
        if len(run) < 2:
            return
        corners = [run[0]]
        for a, b, cc in zip(run, run[1:], run[2:]):
            d1 = (round(b[1] - a[1], 3), round(b[2] - a[2], 3))
            d2 = (round(cc[1] - b[1], 3), round(cc[2] - b[2], 3))
            if d1 != d2:
                corners.append(b)
        corners.append(run[-1])
        for a, b in zip(corners, corners[1:]):
            self.tracks.append((net, a[0], a[1], a[2], b[1], b[2], w))
            self.shapes.append(Shape(net, (a[0],), "seg", a[1], a[2], b[1], b[2], w / 2))


# ---- board --------------------------------------------------------------------------------
def build_board(used_nets):
    import pcbnew

    mm = pcbnew.FromMM
    board = pcbnew.BOARD()
    board.SetFileName(str(HERE / f"{NAME}.kicad_pcb"))
    ds = board.GetDesignSettings()
    ds.SetCopperLayerCount(2)
    nets = {}
    unused = {str(k): f"unconnected-(J1-Pin_{k}-Pad{k})" for k, v in PI_PINS.items() if v is None}
    for name in sorted(used_nets) + sorted(unused.values()):
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        nets[name] = ni

    def footprint(lib, name):
        path = HERE / f"{LOCAL_LIB}.pretty" if lib == LOCAL_LIB else FOOTPRINTS / f"{lib}.pretty"
        fp = pcbnew.FootprintLoad(str(path), name)
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        return fp

    def pad_centroid(fp):
        pts = [p.GetPosition() for p in fp.Pads() if p.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH]
        return sum(p.x for p in pts) / len(pts), sum(p.y for p in pts) / len(pts)

    sch_file = f"{NAME}.kicad_sch"
    for p in PARTS:
        fp = footprint(*p["footprint"])
        board.Add(fp)
        fp.SetReference(p["ref"])
        fp.SetValue(p["value"])
        fp.SetPath(pcbnew.KIID_PATH("/" + p["uuid"]))
        fp.SetSheetname("/")
        fp.SetSheetfile(sch_file)
        fp.SetPosition(pcbnew.VECTOR2I(0, 0))
        fp.SetOrientationDegrees(p["rot"])
        if p["side"] == "back":
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        x, y = p["at"]
        if p["ref"] in HEADERS or p["ref"][0] in "DR":
            # pin 1 at the given point. Headers run to smaller x, so from behind they read 1, 2, 3
            # left to right; diodes and resistors have pin 1 on the left seen from the front.
            want = 1 if p["ref"][0] in "DR" else -1
            base = fp.GetOrientationDegrees()
            for turn in (0, 90, 180, 270):
                fp.SetOrientationDegrees(base + turn)
                pads = {q.GetNumber(): q.GetPosition() for q in fp.Pads()}
                dx, dy = pads["2"].x - pads["1"].x, pads["2"].y - pads["1"].y
                if abs(dy) < 1000 and dx * want > 0:
                    break
            else:
                raise RuntimeError(f"could not turn {p['ref']}")
            fp.Move(pcbnew.VECTOR2I(mm(x) - pads["1"].x, mm(y) - pads["1"].y))
        elif p["ref"].startswith("SW"):
            fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        else:
            cx, cy = pad_centroid(fp)
            fp.Move(pcbnew.VECTOR2I(int(mm(x) - cx), int(mm(y) - cy)))
        for pad in fp.Pads():
            net = p["nets"].get(pad.GetNumber()) or (unused.get(pad.GetNumber()) if p["ref"] == "J1" else None)
            if net:
                pad.SetNet(nets[net])
        fp.SetField("Description", p["desc"])
        fp.Reference().SetVisible(False)
    for i, (x, z) in enumerate(c.BOARD_SCREWS):
        fp = footprint("MountingHole", "MountingHole_2.2mm_M2")
        board.Add(fp)
        fp.SetReference(f"H{i + 1}")
        fp.SetBoardOnly(True)
        fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(Y(z))))
        fp.Reference().SetVisible(False)

    # outline
    x0, x1 = c.BOARD_X
    y0, y1 = Y(c.BOARD_Z[1]), Y(c.BOARD_Z[0])
    rect = pcbnew.PCB_SHAPE(board)
    rect.SetShape(pcbnew.SHAPE_T_RECT)
    rect.SetStart(pcbnew.VECTOR2I(mm(x0), mm(y0)))
    rect.SetEnd(pcbnew.VECTOR2I(mm(x1), mm(y1)))
    rect.SetLayer(pcbnew.Edge_Cuts)
    rect.SetWidth(mm(0.1))
    board.Add(rect)

    def text(s, x, y, size=1.0, layer=pcbnew.B_SilkS, angle=0, just=0, bold=False):
        t = pcbnew.PCB_TEXT(board)
        t.SetText(s)
        t.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        t.SetLayer(layer)
        t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
        t.SetTextThickness(mm(0.15 if size >= 1 else 0.12))
        t.SetBold(bold)
        if layer in (pcbnew.B_SilkS, pcbnew.B_Fab):
            t.SetMirrored(True)
        t.SetTextAngleDegrees(angle)
        t.SetHorizJustify(just)
        board.Add(t)

    # labels on the back, for the person plugging things in: header names, pin names, keys
    for ref, (title, names, netl, x1p, z, value) in HEADERS.items():
        y = Y(z)
        text(title, x1p + 1.6, y, 1.0, just=pcbnew.GR_TEXT_H_ALIGN_RIGHT, bold=True)
        for k, name in enumerate(names):
            text(name, x1p - 2.54 * k, y + 1.4 + 0.35 * len(name) + 0.2, 0.8, angle=90)
    for k, name in zip(c.KEYS_X, KEY_NAMES):
        text(name, k, Y(c.CTRL_Z) - 6.0, 1.0, bold=True)
    for p in PARTS:
        if p["ref"][0] in "DR":
            text(p["ref"], p["at"][0] + 3.81, p["at"][1], 0.8)
    text("Q1", 159.8, 47.6, 0.8)
    text(f"NFC PLAYER FRONT BOARD  REV {REVISION}", 120.0, 21.4, 1.0)
    text("PARTS ON THIS SIDE. TRIM LEADS ON THE OTHER SIDE TO 1.5 MM", 120.0, 38.4, 0.8)
    text("THIS SIDE AGAINST THE PANEL", 120.0, 21.4, 1.0, layer=pcbnew.F_SilkS)
    text("NO PARTS ON THIS SIDE", 120.0, 41.0, 0.8, layer=pcbnew.F_SilkS)

    # copper to route around
    shapes, pads, holes = [], {}, []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            pos = pad.GetPosition()
            px, py = pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)
            layers = tuple(l for l, lid in ((0, pcbnew.F_Cu), (1, pcbnew.B_Cu)) if pad.IsOnLayer(lid))
            if pad.GetDrillSize().x:
                holes.append((px, py, pcbnew.ToMM(pad.GetDrillSize().x) / 2))
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                shapes.append(Shape(None, (0, 1), "circle", px, py, pcbnew.ToMM(pad.GetDrillSize().x) / 2))
                continue
            if pad.GetShape(pcbnew.F_Cu if 0 in layers else pcbnew.B_Cu) == pcbnew.PAD_SHAPE_CIRCLE:
                s = Shape(pad.GetNetname() or None, layers, "circle", px, py, pcbnew.ToMM(pad.GetSize(pcbnew.F_Cu if 0 in layers else pcbnew.B_Cu).x) / 2)
            else:
                bb = pad.GetBoundingBox()
                s = Shape(pad.GetNetname() or None, layers, "rect", pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()), pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()))
            if s.net is None:  # an unused pin is still copper
                s.net = f"unused-{fp.GetReference()}-{pad.GetNumber()}"
            shapes.append(s)
            if pad.GetNetname():
                pads.setdefault(pad.GetNetname(), []).append((s, f"{fp.GetReference()}.{pad.GetNumber()}"))
    router = Router((x0, y0, x1, y1), shapes, pads)
    router.holes = holes

    def span(net):
        xs = [((s.box()[0] + s.box()[2]) / 2) for s, _ in pads[net]]
        ys = [((s.box()[1] + s.box()[3]) / 2) for s, _ in pads[net]]
        return (max(xs) - min(xs)) + (max(ys) - min(ys))

    order = sorted((n for n in pads if n not in POWER_NETS), key=span) + ["5V", "3V3", "GND"]
    for net in order:
        try:
            ok = router.route(net)
        except IndexError:
            ok = False
            print("index", net, [(n, s.box()) for s, n in pads[net]])
        print(f"  routed {net:10s}" if ok else f"  COULD NOT ROUTE {net}")

    router.stitch("GND", 3.0)
    for net, layer, ax, ay, bx, by, w in router.tracks:
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(mm(ax), mm(ay)))
        t.SetEnd(pcbnew.VECTOR2I(mm(bx), mm(by)))
        t.SetWidth(mm(w))
        t.SetLayer(pcbnew.F_Cu if layer == 0 else pcbnew.B_Cu)
        t.SetNet(nets[net])
        board.Add(t)
    for net, vx, vy in router.vias:
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(mm(vx), mm(vy)))
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        try:
            v.SetWidth(mm(VIA))
        except TypeError:
            v.SetWidth(pcbnew.F_Cu, mm(VIA))
        v.SetDrill(mm(VIA_DRILL))
        v.SetNet(nets[net])
        board.Add(v)

    # ground on both sides
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(nets["GND"])
        z.SetLocalClearance(mm(0.25))
        z.SetMinThickness(mm(0.25))
        z.SetThermalReliefGap(mm(0.4))
        z.SetThermalReliefSpokeWidth(mm(0.4))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetThermalReliefSpokeWidth(mm(0.5))
        ol = z.Outline()
        ol.NewOutline()
        for px, py in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            ol.Append(mm(px), mm(py))
        board.Add(z)
    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(str(HERE / f"{NAME}.kicad_pcb"), board)
    return router, board


def check_pockets(board):
    """Every through-hole solder joint must sit over a pocket in the panel."""
    import pcbnew

    bad = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetAttribute() != pcbnew.PAD_ATTRIB_PTH:
                continue
            bb = pad.GetBoundingBox()
            x0, x1 = pcbnew.ToMM(bb.GetLeft()) - 0.4, pcbnew.ToMM(bb.GetRight()) + 0.4
            z0, z1 = TOP - pcbnew.ToMM(bb.GetBottom()) - 0.4, TOP - pcbnew.ToMM(bb.GetTop()) + 0.4
            if not any(a <= x0 and x1 <= b and lo <= z0 and z1 <= hi for a, lo, b, hi in c.BOARD_POCKETS):
                bad.append(f"{fp.GetReference()}.{pad.GetNumber()}")
    return bad


def run(*args):
    r = subprocess.run([str(CLI), *map(str, args)], cwd=HERE, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def report_counts(path):
    text = Path(path).read_text()
    errors = text.count("; error")
    warnings = text.count("; warning")
    return errors, warnings, text


def main():
    print("== footprints, schematic, project ==")
    choc_footprint()
    used = schematic()
    project()
    print("== board ==")
    router, board = build_board(used)
    problems = []
    if router.failed:
        problems.append("could not route: " + ", ".join(router.failed))
    bad = check_pockets(board)
    if bad:
        problems.append("solder joints outside the panel pockets: " + ", ".join(bad))
    print(f"  {len(router.tracks)} tracks, {len(router.vias)} vias")

    print("== checks ==")
    FAB.mkdir(exist_ok=True)
    run("sch", "erc", "--output", FAB / "erc.rpt", "--severity-all", f"{NAME}.kicad_sch")
    e, w, _ = report_counts(FAB / "erc.rpt")
    print(f"  ERC: {e} errors, {w} warnings (fab/erc.rpt)")
    if e:
        problems.append(f"{e} ERC errors")
    run("pcb", "drc", "--schematic-parity", "--output", FAB / "drc.rpt", "--severity-all", f"{NAME}.kicad_pcb")
    e, w, _ = report_counts(FAB / "drc.rpt")
    print(f"  DRC: {e} errors, {w} warnings (fab/drc.rpt)")
    if e:
        problems.append(f"{e} DRC errors")

    print("== files for the board maker ==")
    gerbers = FAB / "gerbers"
    shutil.rmtree(gerbers, ignore_errors=True)
    gerbers.mkdir()
    run("pcb", "export", "gerbers", "--output", gerbers, "--layers", "F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts", "--no-protel-ext", f"{NAME}.kicad_pcb")
    run("pcb", "export", "drill", "--output", str(gerbers) + "/", "--format", "excellon", "--excellon-separate-th", f"{NAME}.kicad_pcb")
    archive = shutil.make_archive(str(FAB / f"{NAME}-gerbers"), "zip", gerbers)
    print("  ", Path(archive).name)
    run("sch", "export", "pdf", "--output", FAB / f"{NAME}-schematic.pdf", f"{NAME}.kicad_sch")
    run("sch", "export", "bom", "--output", FAB / f"{NAME}-bom.csv", "--fields", "Reference,Value,Footprint,Description,${QUANTITY}", "--labels", "Refs,Value,Footprint,Description,Qty", "--group-by", "Value,Footprint", f"{NAME}.kicad_sch")
    for side in ("front", "back"):
        run("pcb", "export", "svg", "--output", FAB / f"{NAME}-{side}.svg", "--layers", ("F.Cu,F.SilkS,Edge.Cuts" if side == "front" else "B.Cu,B.SilkS,Edge.Cuts"), "--mode-single", "--page-size-mode", "2", "--exclude-drawing-sheet", *(["--mirror"] if side == "back" else []), f"{NAME}.kicad_pcb")
        code, out = run("pcb", "render", "--output", FAB / f"{NAME}-{side}.png", "--side", "top" if side == "front" else "bottom", "--width", "1600", "--height", "1000", "--zoom", "1.55", "--quality", "high", "--background", "opaque", f"{NAME}.kicad_pcb")
        if code:
            print("   render failed:", out[-200:])
    print("== result ==")
    print("\n".join("PROBLEM: " + p for p in problems) or "No problems found.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
