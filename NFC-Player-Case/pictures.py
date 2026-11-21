"""Draws the assembly pictures for the guide from the built parts. Run build.py first.

    /Applications/Blender.app/Contents/MacOS/Blender -b -P pictures.py

Writes pictures/<name>.png and pictures/<name>.json. The JSON holds where each numbered
marker and arrow lands on the picture, so guide.py can draw them as an overlay and list
what each number means beside the picture, instead of writing text into the image.

The bought parts are simple stand-ins at their nominal sizes and positions from case.py.
They show where things go and which way round, not what the parts look like in detail.
"""

import json
import math
import sys
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build  # noqa: E402
import case as c  # noqa: E402

sys.path.insert(0, str(HERE / "front-board"))
import board as fb  # noqa: E402  (the front board's parts and where they sit)

OUT = HERE / "pictures"
RES = (1600, 1000)

# ---- colours -------------------------------------------------------------------
PRINT = (0.80, 0.81, 0.79)  # printed parts already in place
FOCUS = (0.38, 0.62, 0.86)  # the printed part being fitted in this step
BRASS = (0.83, 0.66, 0.36)
PCB_PI, PCB_DAC, PCB_FRONT = (0.16, 0.47, 0.27), (0.10, 0.34, 0.20), (0.40, 0.28, 0.58)
PCB_LCD, PCB_NFC = (0.10, 0.17, 0.42), (0.72, 0.14, 0.14)
BLACK, METAL, KEYCAP = (0.09, 0.09, 0.10), (0.72, 0.72, 0.70), (0.22, 0.23, 0.24)
GLASS = (0.06, 0.13, 0.16)
CARD = (0.55, 0.72, 0.68)
WIRES = {"screen": (0.95, 0.75, 0.10), "reader": (0.85, 0.20, 0.55), "controls": (0.20, 0.65, 0.85), "power": (0.90, 0.40, 0.15), "usb": (0.15, 0.15, 0.15)}
RIBBON, RIBBON_PLUG, LIGHT = (0.62, 0.63, 0.66), (0.36, 0.37, 0.39), (0.98, 0.80, 0.45)

# ---- nominal positions of the bought parts --------------------------------------
PI_Y = 62.0  # the Pi's front edge, with the DAC's sockets 6.5 mm inside the rear panel
PI_Z = c.FLOOR + c.STANDOFF_H
DAC_Z = PI_Z + 1.6 + 11  # underside of the DAC board, straight on the Pi
DAC_Y1 = PI_Y + 56.5  # the DAC's rear edge, where its sockets are
HEADER_Y = (PI_Y + 1.0, PI_Y + 6.0)  # the 40-pin header row
PLUG_Z = DAC_Z + 1.6 + 2.5  # underside of the ribbon plug on the DAC's pins
RCA_X, PHONES_DAC_X = (42.0, 56.0), 71.0  # APPROXIMATE positions along the DAC's socket edge
LCD_CX, LCD_CZ = c.cradle_centre()
LCD_Y = c.FRONT_T + c.LCD_GLASS
LEAN = [(1, 0, 0, 0), (0, 1, c.TAN, -c.TAN * c.H), (0, 0, 1, 0)]
READER_Y = c.READER_Y
BOARD_BACK = c.FRONT_T + c.BOARD_T  # the back of the front board
J1_Z = 46.0  # centre of the board's 40-pin header
B = c.box


def header_span(ref):
    """x0, x1, z of one of the board's pin headers."""
    title, names, nets, x1, z, value = fb.HEADERS[ref]
    return x1 - 2.54 * (len(names) - 1) - 1.27, x1 + 1.27, z


def ring_y(x, z, y0, y1, d, d_in):
    return c.diff(c.cyly(x, z, y0, y1, d), c.cyly(x, z, y0 - 1, y1 + 1, d_in))


def stand_ins():
    """name: (shape, colour, group). Shapes are in case coordinates."""
    s = {}
    # Pi and DAC
    for i, (x, y) in enumerate((x, y) for x in (c.PI_X + 3.5, c.PI_X + 61.5) for y in (PI_Y + 3.5, PI_Y + 26.5)):
        s[f"standoff {i}"] = (c.cylz(x, y, c.FLOOR, PI_Z, 5.0), METAL, "standoffs")
        s[f"standoff screw {i}"] = (c.cylz(x, y, -1.6, 0, 4.5), METAL, "standoffs")
    s["Pi"] = (B(c.PI_X, c.PI_X + 65, PI_Y, PI_Y + 30, PI_Z, PI_Z + 1.6), PCB_PI, "pi")
    s["Pi header"] = (B(c.PI_X + 7, c.PI_X + 58, *HEADER_Y, PI_Z + 1.6, PI_Z + 1.6 + 2.5), BLACK, "pi")
    s["Pi USB ports"] = (c.union(*[B(c.PI_X + x - 4, c.PI_X + x + 4, PI_Y + 25, PI_Y + 31, PI_Z + 1.6, PI_Z + 4.4) for x in (41.4, 54.0)]), METAL, "pi")
    s["DAC"] = (B(c.PI_X, c.PI_X + 65, PI_Y, DAC_Y1, DAC_Z, DAC_Z + 1.6), PCB_DAC, "dac")
    s["DAC socket"] = (B(c.PI_X + 7, c.PI_X + 58, *HEADER_Y, PI_Z + 1.6 + 2.5, DAC_Z), BLACK, "dac")
    s["DAC pins"] = (B(c.PI_X + 7, c.PI_X + 58, HEADER_Y[0] + 0.8, HEADER_Y[1] - 0.8, DAC_Z + 1.6, PLUG_Z), METAL, "dac")
    sz = DAC_Z + 1.6 + 6.5
    s["DAC RCA sockets"] = (c.union(*[ring_y(x, sz, DAC_Y1 - 12, DAC_Y1 + 2.5, 10.5, 4) for x in RCA_X], *[B(x - 6, x + 6, DAC_Y1 - 14, DAC_Y1 - 2, DAC_Z + 1.6, sz + 6) for x in RCA_X]), BLACK, "dac")
    s["DAC headphone socket"] = (c.union(B(PHONES_DAC_X - 3.5, PHONES_DAC_X + 3.5, DAC_Y1 - 12, DAC_Y1, DAC_Z + 1.6, DAC_Z + 7.6), ring_y(PHONES_DAC_X, DAC_Z + 4.6, DAC_Y1 - 1, DAC_Y1 + 1.5, 6.0, 3.5)), BLACK, "dac")
    s["ribbon plug on the DAC"] = (B(c.PI_X + 5, c.PI_X + 60, HEADER_Y[0] - 2, HEADER_Y[1] + 2, PLUG_Z, PLUG_Z + 9), RIBBON_PLUG, "ribbon")
    # screen
    s["screen board"] = (B(LCD_CX - 29, LCD_CX + 29, LCD_Y, LCD_Y + 1.6, LCD_CZ - 17.5, LCD_CZ + 17.5), PCB_LCD, "screen")
    s["screen glass"] = (B(LCD_CX - 24, LCD_CX + 24, c.FRONT_T + 0.1, LCD_Y, LCD_CZ - 17.5, LCD_CZ + 17.5), GLASS, "screen")
    s["screen connector"] = (B(LCD_CX + 14, LCD_CX + 24, LCD_Y + 1.6, LCD_Y + 7, LCD_CZ - 4, LCD_CZ + 4), (0.92, 0.92, 0.88), "screen")
    # front controls
    for i, k in enumerate(c.KEYS_X):
        bottom = c.FRONT_T - 0.05  # the switch's underside, level with the inside of the panel
        s[f"switch {i}"] = (c.union(B(k - 7.5, k + 7.5, -2.0, c.BRASS_T, c.CTRL_Z - 7.5, c.CTRL_Z + 7.5), B(k - 6.9, k + 6.9, c.BRASS_T, bottom, c.CTRL_Z - 6.9, c.CTRL_Z + 6.9), *[B(k + dx - 0.4, k + dx + 0.4, bottom, bottom + 3.0, c.CTRL_Z - dz - 0.4, c.CTRL_Z - dz + 0.4) for dx, dz in ((0.0, 5.9), (5.0, 3.8))]), (0.30, 0.31, 0.32), f"switch {i}")
        s[f"stem {i}"] = (B(k - 1.5, k + 1.5, -5.0, -2.0, c.CTRL_Z - 1.5, c.CTRL_Z + 1.5), (0.62, 0.22, 0.17), f"switch {i}")
        s[f"keycap {i}"] = (B(k - 8.75, k + 8.75, -7.5, -5.0, c.CTRL_Z - 8.25, c.CTRL_Z + 8.25), KEYCAP, f"keycap {i}")
    enc_face = c.FRONT_T - (c.FRONT_T - c.BRASS_T - c.PANEL_AT_NUT)  # floor of the encoder's pocket
    s["encoder"] = (c.union(B(c.KNOB_X - 6.25, c.KNOB_X + 6.25, enc_face, enc_face + 6.5, c.CTRL_Z - 6.7, c.CTRL_Z + 6.7), c.cyly(c.KNOB_X, c.CTRL_Z, enc_face - 5.0, enc_face, 7.0), c.cyly(c.KNOB_X, c.CTRL_Z, enc_face - 20.0, enc_face - 5.0, 6.0), *[B(c.KNOB_X + dx - 0.4, c.KNOB_X + dx + 0.4, enc_face + 6.5, enc_face + 10, c.CTRL_Z - 8, c.CTRL_Z - 6.5) for dx in (-2.5, 0, 2.5)]), METAL, "encoder")
    s["encoder washer"] = (ring_y(c.KNOB_X, c.CTRL_Z, -0.5, -0.05, 12.0, 7.2), (0.80, 0.80, 0.78), "washer")
    s["encoder nut"] = (ring_y(c.KNOB_X, c.CTRL_Z, -2.5, -0.5, 10.0, 7.0), METAL, "nut")
    s["knob"] = (c.cyly(c.KNOB_X, c.CTRL_Z, -19.5, -3.5, c.KNOB_D), BRASS, "knob")
    # power key: a 12 mm panel button with a lit ring, its nut behind the panel
    px, pz = c.POWER_X, c.CTRL_Z
    s["power key"] = (c.union(c.cyly(px, pz, -3.0, -0.05, 15.0), c.cyly(px, pz, c.FRONT_T + 0.05, c.FRONT_T + 18, 12.0), *[B(px + dx - 0.8, px + dx + 0.8, c.FRONT_T + 18, c.FRONT_T + 24, pz - 0.3, pz + 0.3) for dx in (-3.5, -1.2, 1.2, 3.5)]), BLACK, "power key")
    s["power key ring"] = (ring_y(px, pz, -3.15, -2.9, 12.5, 10.5), LIGHT, "power key")
    s["power key nut"] = (ring_y(px, pz, c.FRONT_T + 0.05, c.FRONT_T + 3.0, c.POWER_BODY[0], 12.2), (0.20, 0.20, 0.21), "power nut")
    # the front board: flat on the panel, sockets and headers on its back
    x0, x1 = c.BOARD_X
    z0, z1 = c.BOARD_Z
    s["front board"] = (B(x0, x1, c.FRONT_T + 0.05, BOARD_BACK, z0, z1), PCB_FRONT, "board")
    for i, k in enumerate(c.KEYS_X):
        s[f"hot-swap socket {i}"] = (B(k - 4.6, k + 9.6, BOARD_BACK, BOARD_BACK + 1.85, c.CTRL_Z - 7.25, c.CTRL_Z - 2.3), (0.93, 0.93, 0.90), "board")
    s["board 40-pin header"] = (B(89.3, 148.7, BOARD_BACK, BOARD_BACK + 9, J1_Z - 5, J1_Z + 5), BLACK, "board")
    for ref in fb.HEADERS:
        hx0, hx1, hz = header_span(ref)
        s[f"board header {ref}"] = (c.union(B(hx0, hx1, BOARD_BACK, BOARD_BACK + 2.5, hz - 1.27, hz + 1.27), *[B(x - 0.32, x + 0.32, BOARD_BACK + 2.5, BOARD_BACK + 8.5, hz - 0.32, hz + 0.32) for x in [hx0 + 1.27 + 2.54 * n for n in range(round((hx1 - hx0) / 2.54))]]), BLACK, "board")
    for p in fb.PARTS:
        if p["ref"][0] in "DR":
            bx, by = p["at"]
            s[f"board {p['ref']}"] = (B(bx + 1.0, bx + 6.6, BOARD_BACK, BOARD_BACK + 2.2, fb.TOP - by - 1.1, fb.TOP - by + 1.1), (0.85, 0.75, 0.55) if p["ref"][0] == "R" else (0.55, 0.62, 0.85), "board")
    s["board Q1"] = (B(157.4, 162.2, BOARD_BACK, BOARD_BACK + 4.5, fb.TOP - 44.0 - 1.0, fb.TOP - 44.0 + 2.5), BLACK, "board")
    s["ribbon plug on the board"] = (B(89.8, 148.2, BOARD_BACK + 9, BOARD_BACK + 18, J1_Z - 4.5, J1_Z + 4.5), RIBBON_PLUG, "ribbon")
    for i, (x, z) in enumerate(c.BOARD_SCREWS):
        s[f"board screw {i}"] = (c.cyly(x, z, BOARD_BACK + 0.05, BOARD_BACK + 1.6, 3.8), METAL, "board")
    # NFC reader and card
    s["NFC reader"] = (c.xf(LEAN, B(c.CARD_X - 21.35, c.CARD_X + 21.35, READER_Y + 0.05, READER_Y + 1.65, c.PN532_CENTRE_Z - 20.2, c.PN532_CENTRE_Z + 20.2)), PCB_NFC, "reader")
    s["NFC reader header"] = (c.xf(LEAN, B(c.CARD_X - 10, c.CARD_X + 10, READER_Y + 1.65, READER_Y + 4.2, c.PN532_CENTRE_Z + 15, c.PN532_CENTRE_Z + 17.5)), BLACK, "reader")
    s["card"] = (c.xf(LEAN, B(c.CARD_X - 27, c.CARD_X + 27, c.CARD_Y - 0.38, c.CARD_Y + 0.38, c.CARD_STOP_Z + 0.05, c.CARD_STOP_Z + 85.6)), CARD, "card")
    tx, ty = (c.TRAY[0] + c.TRAY[2]) / 2, (c.TRAY[1] + c.TRAY[3]) / 2
    floor = c.H - c.TRAY_DEPTH
    for i in range(5):
        s[f"stored card {i}"] = (B(tx - 42.8, tx + 42.8, ty - 27, ty + 27, floor + 0.05 + 0.77 * i, floor + 0.8 + 0.77 * i), CARD, "lid")
    # USB-C panel socket
    s["USB-C socket"] = (c.union(B(c.USB_X - 6, c.USB_X + 6, c.D - c.REAR_T - 14, c.D - c.REAR_T, c.USB_Z - 3.2, c.USB_Z + 3.2), B(c.USB_X - 12, c.USB_X + 12, c.D, c.D + 1.5, c.USB_Z - 4.5, c.USB_Z + 4.5)), BLACK, "rear")
    # screws
    for i, (x, z) in enumerate((x, z) for x in c.SCREW_X for z in c.SCREW_Z):
        s[f"front screw {i}"] = (c.cyly(x, z, -1.8, -0.05, 6.0), METAL, "front screws")
        s[f"rear screw {i}"] = (c.cyly(x, z, c.D + 0.05, c.D + 1.8, 6.0), METAL, "rear")
    for i, (x, y) in enumerate((x, y) for x in c.LID_SCREW_X for y in c.LID_SCREW_Y):
        s[f"lid screw {i}"] = (c.cylz(x, y, c.H - 1.55, c.H - 0.1, 5.8), METAL, "lid screws")
    for i, x in enumerate(c.GUIDE_X):
        s[f"guide screw {i}"] = (c.cylz(x, c.GUIDE_Y, 8.05, 9.8, 6.0), METAL, "guide")
    for i, dx in enumerate((-c.CRADLE_BOSS_DX, c.CRADLE_BOSS_DX)):
        s[f"cradle screw {i}"] = (c.cylz(c.LCD_X + dx, c.CRADLE_Y, 8.05, 9.8, 6.0), METAL, "cradle")
    for i, (x, y) in enumerate((x, y) for x in (18, c.W - 18) for y in (18, c.D - 18)):
        s[f"foot {i}"] = (c.cylz(x, y, -5, -0.05, 14), BLACK, "feet")
    return s


def wires():
    """name: (points, colour, group). Routed clear of the tray, the card and the boards."""
    lead = BOARD_BACK + 22  # where the leads leave the board's pin headers
    j = {ref: ((header_span(ref)[0] + header_span(ref)[1]) / 2, header_span(ref)[2]) for ref in fb.HEADERS}
    out = {
        "screen wires": ([(LCD_CX + 19, LCD_Y + 7, LCD_CZ), (LCD_CX + 22, 26, LCD_CZ - 8), (j["J2"][0] - 6, lead + 6, 9), (j["J2"][0], lead, j["J2"][1])], WIRES["screen"], "wires"),
        "reader wires": ([(c.CARD_X, READER_Y + 6.5, c.PN532_CENTRE_Z + 16), (c.CARD_X - 30, READER_Y + 4, 30), (j["J3"][0] + 4, lead + 10, 8), (j["J3"][0], lead, j["J3"][1])], WIRES["reader"], "wires"),
        "encoder wires": ([(c.KNOB_X, c.FRONT_T + 9, c.CTRL_Z - 7), (c.KNOB_X - 8, 24, 18), (j["J4"][0] + 6, lead + 4, 16), (j["J4"][0], lead, j["J4"][1])], WIRES["controls"], "wires"),
        "power key wires": ([(c.POWER_X, c.FRONT_T + 24, c.CTRL_Z), (c.POWER_X + 6, 30, 14), (60, 28, 9), (j["J5"][0] - 4, lead + 4, 14), (j["J5"][0], lead, j["J5"][1])], WIRES["power"], "wires"),
        "USB lead": ([(c.USB_X, c.D - c.REAR_T - 14, c.USB_Z), (c.USB_X - 10, 110, 14), (90, 100, 12), (c.PI_X + 41.4, PI_Y + 33, PI_Z + 3)], WIRES["usb"], "usb lead"),
    }
    # the ribbon, drawn as a band of wires: back from the board, folded left, down onto the DAC's pins
    for i in range(9):
        t = i / 8
        bx = 92.0 + t * 54.0
        dx = c.PI_X + 8 + t * 49.0
        out[f"ribbon {i}"] = ([(bx, BOARD_BACK + 18, J1_Z), (bx - 4, BOARD_BACK + 28, J1_Z + 1), (dx + 30, 36, J1_Z), (dx, HEADER_Y[0] + 3, PLUG_Z + 20), (dx, HEADER_Y[0] + 3, PLUG_Z + 9)], RIBBON, "ribbon")
    return out


# ---- scene ----------------------------------------------------------------------------
GROUP = {}  # object name -> group


def add_mesh(name, node, colour, group):
    ob = build.make(node)
    ob.name = name
    ob.color = (*colour, 1)
    GROUP[name] = group
    return ob


def add_wire(name, points, colour, group):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions, cu.bevel_depth, cu.bevel_resolution = "3D", 0.9, 3
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(len(points) - 1)
    for bp, p in zip(sp.bezier_points, points):
        bp.co = p
        bp.handle_left_type = bp.handle_right_type = "AUTO"
    ob = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(ob)
    ob.color = (*colour, 1)
    GROUP[name] = group
    return ob


def setup():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    with bpy.data.libraries.load(str(HERE / "parts.blend")) as (src, dst):
        dst.objects = [n for n in src.objects if n in c.PARTS or n == "brass"]
    for ob in dst.objects:
        bpy.context.scene.collection.objects.link(ob)
        ob.color = (*(BRASS if ob.name == "brass" else PRINT), 1)
        GROUP[ob.name] = {"brass": "brass", "front": "front", "rear": "rear", "lid": "lid", "card-guide": "guide", "display-cradle": "cradle"}.get(ob.name, ob.name)
    for name, (node, colour, group) in stand_ins().items():
        add_mesh(name, node, colour, group)
    for name, (pts, colour, group) in wires().items():
        add_wire(name, pts, colour, group)

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x, scene.render.resolution_y = RES
    scene.render.resolution_percentage = 100
    scene.display.render_aa = "16"
    sh = scene.display.shading
    sh.light, sh.color_type = "STUDIO", "OBJECT"
    sh.show_cavity, sh.cavity_type = True, "WORLD"
    sh.show_object_outline, sh.object_outline_color = True, (0.12, 0.13, 0.13)
    sh.show_shadows, sh.shadow_intensity = True, 0.25
    sh.show_specular_highlight = True
    scene.view_settings.view_transform = "Standard"
    scene.world = bpy.data.worlds.new("paper")
    scene.world.color = (0.965, 0.957, 0.93)
    cam = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
    scene.collection.objects.link(cam)
    cam.data.type, cam.data.clip_end = "ORTHO", 10000
    scene.camera = cam
    return scene, cam


def where(name):
    """Where an object's or group's origin has been moved to for this shot."""
    return OFFSETS.get(name, OFFSETS.get(GROUP.get(name), Vector()))


OFFSETS: dict = {}


def pose(shot):
    """Applies a shot's hidden set, offsets and colours."""
    global OFFSETS
    OFFSETS = {k: Vector(v) for k, v in shot.get("move", {}).items()}
    hide, focus = set(shot.get("hide", ())), set(shot.get("focus", ()))
    for ob in bpy.data.objects:
        if ob.type == "CAMERA":
            continue
        g = GROUP.get(ob.name)
        ob.hide_render = ob.name in hide or g in hide
        ob.location = where(ob.name)
        if ob.name in c.PARTS:
            ob.color = (*(FOCUS if ob.name in focus or g in focus else PRINT), 1)
    bpy.context.view_layer.update()


def frame(scene, cam, view_from, names=None, extra=(), margin=0.06):
    """Points the camera along view_from and fits the named (or all visible) objects."""
    if view_from == "top":
        rot = Matrix.Identity(3)
    else:
        rot = (-Vector(view_from)).to_track_quat("-Z", "Y").to_matrix()  # camera y stays as upright as it can
    obs = [ob for ob in bpy.data.objects if ob.type != "CAMERA" and not ob.hide_render and (names is None or ob.name in names or GROUP.get(ob.name) in names)]
    pts = [ob.matrix_world @ Vector(corner) for ob in obs for corner in ob.bound_box] + [Vector(p) for p in extra]
    local = [rot.transposed() @ p for p in pts]
    xs, ys, zs = [p.x for p in local], [p.y for p in local], [p.z for p in local]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    centre = Vector(((max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2, max(zs) + 1000))
    cam.matrix_world = Matrix.Translation(rot @ centre) @ rot.to_4x4()
    cam.data.ortho_scale = max(w, h * RES[0] / RES[1]) * (1 + 2 * margin)
    bpy.context.view_layer.update()


def project(scene, cam, p):
    v = world_to_camera_view(scene, cam, Vector(p))
    return [round(v.x * RES[0], 1), round((1 - v.y) * RES[1], 1)]


def shoot(scene, cam, name, shot):
    pose(shot)
    frame(scene, cam, shot["view"], shot.get("frame"), margin=shot.get("margin", 0.06))
    scene.render.filepath = str(OUT / f"{name}.png")
    bpy.ops.render.render(write_still=True)
    marks = []
    for label, point, attached in shot.get("marks", ()):
        p = Vector(point) + where(attached) if attached else Vector(point)
        marks.append({"label": label, "at": project(scene, cam, p)})
    arrows = [{"from": project(scene, cam, a), "to": project(scene, cam, b)} for a, b in shot.get("arrows", ())]
    (OUT / f"{name}.json").write_text(json.dumps({"size": RES, "marks": marks, "arrows": arrows}, indent=1))
    print("shot", name)


# ---- the pictures ----------------------------------------------------------------------
def v(*a):
    return tuple(a)


ISO_FL = (-1.0, -1.25, 0.95)  # from the front left, above
ISO_FR = (1.0, -1.25, 0.95)
ISO_RL = (-1.0, 1.2, 1.0)  # from the rear left, above
ISO_RR = (1.0, 1.2, 1.0)
INSIDE = ("chassis", "standoffs", "pi", "dac", "screen", "cradle", "guide", "reader", "wires", "usb lead", "encoder", "knob", "nut", "board", "ribbon", "power key", "power nut")
KEYS = tuple(f"switch {i}" for i in range(4)) + tuple(f"keycap {i}" for i in range(4))
BACKS = (c.FRONT_T + 2, c.D - c.REAR_T - 2)  # just inside the panels
BOARD_MID = ((c.BOARD_X[0] + c.BOARD_X[1]) / 2, (c.BOARD_Z[0] + c.BOARD_Z[1]) / 2)
SHOTS = {
    "exploded": {
        "view": ISO_FL,
        "hide": ("wires", "usb lead", "card", "ribbon"),
        "move": {"lid": v(0, 0, 45), "lid screws": v(0, 0, 58), "front": v(0, -40, 0), "brass": v(0, -62, 0), "front screws": v(0, -76, 0), "knob": v(0, -86, 0), "nut": v(0, -40, 0), "washer": v(0, -40, 0), "encoder": v(0, -40, 0), "power key": v(0, -40, 0), "power nut": v(0, -40, 0), "board": v(0, -20, 0), **{k: v(0, -40, 0) for k in KEYS}, "rear": v(0, 40, 0)},
        "marks": [
            ("Lid with the card tray and slot", (60, 30, c.H), "lid"),
            ("Chassis: floor, side walls and screw towers", (4, 70, 30), "chassis"),
            ("Front panel, with the power key, four switches and the encoder fitted", (25, 4, 52), "front"),
            ("Brass face", (25, 0, 8), "brass"),
            ("Knob", (c.KNOB_X, -18.5, c.CTRL_Z + 12), "knob"),
            ("Front board: it goes flat against the inside of the panel, behind the keys", (c.BOARD_X[1], c.FRONT_T, c.BOARD_Z[1] - 3), "board"),
            ("Rear panel with the USB-C socket", (2, c.D - 1.5, 30), "rear"),
            ("Card guide, with the NFC reader behind it", (c.CARD_X - 25, c.CARD_Y - 4, 45), "guide"),
            ("Pi and DAC stack", (20, PI_Y + 20, DAC_Z + 1.6), "dac"),
            ("Screen in its cradle", (LCD_CX - 20, LCD_Y, LCD_CZ + 19), "screen"),
        ],
    },
    "layout-top": {
        "view": "top",
        "hide": ("lid", "lid screws", "card"),
        "marks": [
            ("Power key, its nut and its leads", (c.POWER_X, c.FRONT_T + 12, 45), "power key"),
            ("Screen, held upright in its cradle behind the window", (LCD_CX - 18, LCD_Y + 4, 47), "screen"),
            ("Front board behind the keys, with its 40-pin header on top", (120, BOARD_BACK + 9, 51), "board"),
            ("Ribbon from the board to the pins on top of the DAC", (100, 34, 48), "ribbon"),
            ("Encoder (volume knob)", (c.KNOB_X, 6, 40), "encoder"),
            ("Card guide, card slot leaning 5° back", (c.CARD_X + 24, c.CARD_Y - 3, 50), "guide"),
            ("NFC reader, held 20 mm behind the card slot", (c.CARD_X - 18, READER_Y + 3, 55), "reader"),
            ("DAC on top of the Pi", (c.PI_X + 33, PI_Y + 32, DAC_Z + 1.6), "dac"),
            ("DAC's RCA and headphone sockets, at the rear window", (c.PI_X + 33, DAC_Y1, DAC_Z + 14), "dac"),
            ("USB-C socket, wired to the Pi's USB port", (c.USB_X, c.D - 9, c.USB_Z + 4), "rear"),
            ("Air in through the floor, out through the lid and rear slots", (110, 25.5, c.FLOOR), "chassis"),
        ],
    },
    "layout-inside": {
        "view": ISO_RR,
        "hide": ("lid", "lid screws", "rear", "card"),
        "margin": 0.04,
        "marks": [
            ("Screen cradle", (LCD_CX + 31, c.FRONT_T + 6, 30), "cradle"),
            ("Front board and its leads", (c.BOARD_X[1] - 4, BOARD_BACK + 8, 14), "board"),
            ("Card guide and NFC reader", (c.CARD_X + 12, READER_Y + 2, 45), "reader"),
            ("Pi and DAC stack", (c.PI_X + 64, PI_Y + 40, DAC_Z + 1), "dac"),
            ("Ribbon plug on the pins on top of the DAC", (c.PI_X + 60, HEADER_Y[1] + 2, PLUG_Z + 9), "ribbon"),
            ("DAC sockets: they come out through the rear window", (RCA_X[1], DAC_Y1 + 2, DAC_Z + 8), "dac"),
            ("Floor slots: the stack slides front to back", (c.PI_X + 61.5, PI_Y + 26.5, c.FLOOR), "chassis"),
            ("USB lead from the rear socket to the Pi", (95, 101, 12), "usb lead"),
        ],
    },
    "step-1-brass": {
        "view": ISO_FL,
        "frame": ("front", "brass"),
        "hide": INSIDE + KEYS + ("chassis", "lid", "lid screws", "rear", "front screws", "feet", "card"),
        "focus": ("front",),
        "move": {"brass": v(0, -30, 0)},
        "arrows": [((100, -26, 66), (100, -4, 66))],
        "marks": [
            ("Brass face, 0.8 mm sheet", (30, 0, 48), "brass"),
            ("Pocket, 0.8 mm deep", (100, c.FRONT_T - c.BRASS_T, 53), "front"),
            ("Printed rim, 1.2 mm wide", (c.W - 0.6, 0, 30), "front"),
            ("Screw holes line up through both layers", (c.SCREW_X[0], 0, c.SCREW_Z[1]), "brass"),
        ],
    },
    "step-2-front": {
        "view": (-0.55, -1.0, 0.38),  # from the front left, so parts pulled forward move clear to the right
        "frame": ("encoder", "knob", "nut", "washer", "power key", "power nut") + KEYS,
        "margin": 0.08,
        "hide": ("chassis", "lid", "lid screws", "rear", "standoffs", "pi", "dac", "screen", "cradle", "guide", "reader", "wires", "usb lead", "feet", "card", "front screws", "board", "ribbon"),
        "focus": ("front",),
        "move": {"switch 3": v(0, -18, 0), "keycap 2": v(0, -16, 0), "keycap 3": v(0, -38, 0), "encoder": v(0, 18, 0), "washer": v(0, -14, 0), "nut": v(0, -26, 0), "knob": v(0, -56, 0), "power key": v(0, -24, 0), "power nut": v(0, 16, 0)},
        "arrows": [((c.KEYS_X[3], -34, c.CTRL_Z + 14), (c.KEYS_X[3], -8, c.CTRL_Z + 14)), ((c.KNOB_X, -36, c.CTRL_Z - 22), (c.KNOB_X, -6, c.CTRL_Z - 22)), ((c.POWER_X, -40, c.CTRL_Z + 12), (c.POWER_X, -8, c.CTRL_Z + 12))],
        "marks": [
            ("Power key: goes in from the front; its nut goes on from behind", (c.POWER_X + 7.5, -27, c.CTRL_Z + 7.5), "power key"),
            ("Keycap: presses onto the switch's stem", (c.KEYS_X[3] - 8.75, -7.5, c.CTRL_Z + 8.25), "keycap 3"),
            ("Kailh Choc V1 switch: pushes in from the front until its clips snap behind the plate", (c.KEYS_X[3] - 7.5, -2.0, c.CTRL_Z - 7.5), "switch 3"),
            ("Brass slot: the switch housings sit in it", (c.KEYS_X[0] - 8.25, 0, c.CTRL_Z + 8.25), "brass"),
            ("Encoder: goes in from behind, bushing through the hole", (c.KNOB_X + 6.25, 2.3, c.CTRL_Z + 6.7), "encoder"),
            ("Washer, then nut: clamps panel and brass against the encoder body", (c.KNOB_X + 5, -2.5, c.CTRL_Z + 3), "nut"),
            ("Knob: slides on the shaft, set screw onto the flat", (c.KNOB_X - 12, -19.5, c.CTRL_Z + 12), "knob"),
        ],
    },
    "step-2-controls": {
        "view": (-0.75, 1.0, 0.55),  # from behind the front panel, looking forward
        "frame": ("front", "brass", "encoder", "knob", "nut", "power key", "power nut") + KEYS,
        "hide": ("chassis", "lid", "lid screws", "rear", "standoffs", "pi", "dac", "screen", "cradle", "guide", "reader", "wires", "usb lead", "feet", "card", "front screws", "keycap 3", "board", "ribbon"),
        "focus": ("front",),
        "move": {"switch 3": v(0, -22, 0), "encoder": v(0, 22, 0), "nut": v(0, -16, 0), "washer": v(0, -12, 0), "knob": v(0, -42, 0)},
        "arrows": [((c.KEYS_X[3], -14, c.CTRL_Z + 13), (c.KEYS_X[3], 2, c.CTRL_Z + 13)), ((c.KNOB_X, 26, c.CTRL_Z + 12), (c.KNOB_X, 10, c.CTRL_Z + 12))],
        "marks": [
            ("Switches push in from the front and clip into the 1.2 mm plate", (c.KEYS_X[3] + 8, 2.0, c.CTRL_Z + 7.5), "switch 3"),
            ("Pockets behind the switches leave room for their clips", (c.KEYS_X[1], c.FRONT_T, c.CTRL_Z - 8.5), "front"),
            ("Shallow pockets for the board's solder joints, and three screw pilots", (c.BOARD_POCKETS[1][0] + 4, c.FRONT_T, c.BOARD_POCKETS[1][1] + 4), "front"),
            ("Encoder goes in from behind; its body sits in the pocket", (c.KNOB_X + 6.25, 9, c.CTRL_Z + 6.7), "encoder"),
            ("Power key nut, tightened from behind", (c.POWER_X, c.FRONT_T + 3, c.CTRL_Z + 8), "power nut"),
        ],
    },
    "step-3-board": {
        "view": (1.0, 0.85, 0.5),  # from behind on the knob side, so the gap between board and panel shows
        "frame": ("board",) + KEYS,
        "margin": 0.12,
        "hide": ("chassis", "lid", "lid screws", "rear", "standoffs", "pi", "dac", "screen", "cradle", "guide", "reader", "wires", "usb lead", "feet", "card", "front screws", "ribbon plug on the DAC", "knob", "nut", "washer") + tuple(f"ribbon {i}" for i in range(9)),
        "focus": ("front",),
        "move": {"board": v(0, 26, 0), "ribbon plug on the board": v(0, 26, 0)},
        "arrows": [((c.BOARD_X[1] + 6, 40, BOARD_MID[1]), (c.BOARD_X[1] + 6, 12, BOARD_MID[1]))],
        "marks": [
            ("Front board: the hot-swap sockets on its back take the switches' pins", (c.KEYS_X[2] + 9, BOARD_BACK + 1.85, c.CTRL_Z - 2), "board"),
            ("Ribbon plug: press it onto the 40-pin header before fitting the board", (148.2, BOARD_BACK + 18, J1_Z + 4.5), "board"),
            ("Pin headers for the screen, reader, knob, power key and OLED", (110, BOARD_BACK + 8.5, 16), "board"),
            ("Three M2 × 4 screws into the panel", (c.BOARD_SCREWS[2][0], BOARD_BACK + 1.6, c.BOARD_SCREWS[2][1]), "board"),
            ("Shallow pockets in the panel take the solder joints on the board's front", (c.BOARD_POCKETS[0][0] + 2, c.FRONT_T, c.BOARD_POCKETS[0][3] - 2), "front"),
        ],
    },
    "step-4-screen": {
        "view": (-0.55, 1.0, 0.75),
        "frame": ("cradle", "screen", "brass"),
        "hide": ("lid", "lid screws", "rear", "standoffs", "pi", "dac", "guide", "reader", "wires", "usb lead", "card", "encoder", "knob", "nut", "feet", "ribbon") + KEYS,
        "focus": ("display-cradle",),
        "move": {"screen": v(0, 0, 36)},
        "arrows": [((LCD_CX, LCD_Y + 0.8, LCD_CZ + 44), (LCD_CX, LCD_Y + 0.8, LCD_CZ + 24))],
        "marks": [
            ("Cradle: screwed to two floor bosses through slots, so it can slide sideways", (c.LCD_X + c.CRADLE_BOSS_DX, c.CRADLE_Y, 9.8), "cradle"),
            ("Grooves in both uprights take the board's side edges", (LCD_CX - 30.5, LCD_Y + 0.8, LCD_CZ + 19.5), "cradle"),
            ("Screen board slides down into the grooves, glass facing the window", (LCD_CX - 26, LCD_Y + 1.6, LCD_CZ + 10), "screen"),
            ("Its connector faces into the case: its lead goes to the board's LCD header", (LCD_CX + 19, LCD_Y + 7, LCD_CZ + 4), "screen"),
            ("Power key, through the notch in the corner tower", (c.POWER_X, c.FRONT_T + 12, c.CTRL_Z + 6), "power key"),
        ],
    },
    "step-5-stack": {
        "view": ISO_FL,
        "frame": ("chassis", "pi", "dac"),
        "hide": ("lid", "lid screws", "front", "brass", "front screws", "screen", "cradle", "guide", "reader", "wires", "usb lead", "card", "encoder", "knob", "nut", "rear", "board", "power key", "power nut", "ribbon") + KEYS,
        "focus": ("chassis",),
        "move": {"pi": v(0, -30, 12), "dac": v(0, -30, 50)},
        "arrows": [((c.PI_X + 72, PI_Y + 12, 90), (c.PI_X + 72, PI_Y + 38, 90)), ((c.PI_X + 72, PI_Y - 14, 74), (c.PI_X + 72, PI_Y - 14, 44))],
        "marks": [
            ("Two floor slots, 53 mm long", (c.PI_X + 3.5, c.PI_SLOT_Y[0] + 4, c.FLOOR), "chassis"),
            ("Four 5 mm standoffs, screwed up from below", (c.PI_X + 61.5, PI_Y + 3.5, PI_Z), "standoffs"),
            ("Pi, its 40-pin header at the front", (c.PI_X + 32, PI_Y + 18, PI_Z + 1.6), "pi"),
            ("DAC straight onto the Pi; its header's pins stand up for the ribbon", (c.PI_X + 4, PI_Y + 3.5, PLUG_Z), "dac"),
            ("DAC's sockets at the rear edge", (c.PI_X + 30, DAC_Y1, DAC_Z + 8), "dac"),
            ("Slide the stack back until the sockets meet the rear window, then tighten", (c.PI_X + 72, PI_Y + 25, 90), None),
        ],
    },
    "step-6-reader": {
        "view": (1.0, 1.0, 0.7),
        "frame": ("guide", "reader", "card"),
        "hide": ("lid", "lid screws", "front", "brass", "front screws", "rear", "standoffs", "pi", "dac", "screen", "cradle", "wires", "usb lead", "encoder", "knob", "nut", "feet", "chassis", "board", "power key", "power nut", "ribbon") + KEYS,
        "focus": ("card-guide",),
        "move": {"reader": v(0, 0, 40)},
        "arrows": [((c.CARD_X + 30, READER_Y - 2, c.PN532_CENTRE_Z + 50), (c.CARD_X + 30, READER_Y - 2, c.PN532_CENTRE_Z + 22))],
        "marks": [
            ("Card guide: two screws into the floor bosses", (c.GUIDE_X[1], c.GUIDE_Y, 9.8), "guide"),
            ("Card slot, leaning 5° back", (c.CARD_X, c.CARD_Y, 51), "guide"),
            ("Grooved posts: three positions, 16, 20 and 24 mm behind the card", (c.CARD_X + 23, READER_Y - 3, c.PN532_CENTRE_Z + 10), "guide"),
            ("NFC reader, antenna side toward the card, header at the top", (c.CARD_X + 21.35, READER_Y + 1.65, c.PN532_CENTRE_Z + 45), "reader"),
        ],
    },
    "step-7-wiring": {
        "view": ISO_RL,
        "hide": ("lid", "lid screws", "rear", "card"),
        "margin": 0.04,
        "marks": [
            ("Ribbon: red stripe to pin 1 at both ends", (100, 32, J1_Z + 2), "ribbon"),
            ("Ribbon plug on the DAC's pins", (c.PI_X + 5, HEADER_Y[0] - 2, PLUG_Z + 9), "ribbon"),
            ("Screen lead to the LCD header", (LCD_CX + 22, 26, LCD_CZ - 8), "wires"),
            ("Power key leads to the PWR header", (40, 29, 11), "wires"),
            ("Knob leads to the ENC header", (c.KNOB_X - 8, 24, 18), "wires"),
            ("Reader leads to the NFC header", (c.CARD_X - 30, READER_Y + 4, 30), "wires"),
        ],
    },
    "step-8-rear": {
        "view": (0.8, 1.3, 0.45),
        "frame": ("rear", "chassis"),
        "margin": 0.08,
        "hide": ("lid", "lid screws", "card"),
        "focus": ("rear",),
        "marks": [
            ("Window for the DAC's sockets: two RCA and the 3.5 mm headphone socket", (c.RCA_WINDOW[0] + 2, c.D, c.RCA_WINDOW[3] - 2), "rear"),
            ("Panel-mount USB-C socket: power and the music drive", (c.USB_X + 12, c.D + 1.5, c.USB_Z + 4.5), "rear"),
            ("Warm air out", (c.W - 100, c.D, 47), "rear"),
            ("Four screws into the corner towers", (c.SCREW_X[1], c.D + 1.8, c.SCREW_Z[0]), "rear"),
        ],
    },
    "step-9-close": {
        "view": ISO_FR,
        "hide": ("wires", "ribbon"),
        "focus": ("lid",),
        "move": {"lid": v(0, 0, 40), "lid screws": v(0, 0, 60)},
        "arrows": [((150, 105, c.H + 34), (150, 105, c.H + 6))],
        "marks": [
            ("The lid drops in between the front and rear panels", (c.W - 2, 60, c.H - 3), "lid"),
            ("Four low-profile screws sit in recesses", (c.LID_SCREW_X[1], c.LID_SCREW_Y[0], c.H + 60), None),
            ("Five spare cards in the tray", (40, 40, c.H - 1), "lid"),
            ("Feet: keep them clear of the floor slots and vents", (c.W - 18, 18, -5), "feet"),
        ],
    },
}


def main():
    OUT.mkdir(exist_ok=True)
    scene, cam = setup()
    only = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    for name, shot in SHOTS.items():
        if not only or name in only:
            shoot(scene, cam, name, shot)


main()
