"""The key carrier: the four key caps, with their symbols cut into their faces, on one thin frame. Millimetres.

    blender -b -P keycaps.py

Writes STL/key-carrier.stl (build.py writes it too, and checks it against the rest of the case).

Each cap slides in a square hole through the front panel, its face flush with the panel's,
and presses a 6 x 6 mm tactile switch on the front board behind it. It hangs from two thin
bridges, one above and one below, each joined to the middle of its edge by a short tab. The bridges
run between the frame's webs either side of the key. They bend a little when the key is pressed,
and they keep the cap centred in its hole, so it does not rattle, and stop it falling out. The cap's
back is hollow: the switch's body stands inside it, and the button presses the back of the face.
Two pegs on the frame's front locate it in the panel. All the sizes come from case.py (KEY_*,
TACT_*, CARRIER_T, BRIDGE_*, PEGS), which also makes the holes, the windows and the spacer.

The carrier prints as it is drawn here, back on the bed and faces up, with no support: the bridges
are the first two layers, the strongest way for them to bend. The symbols read the right way round
from above. Try a cap in the fit gauge's square hole: it should slide freely without rattling.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import case  # noqa: E402
from case import box, cylz, diff, hull, move, prism, union  # noqa: E402

SYMBOL_DEPTH = 0.6  # how deep the symbols are cut; fill them with paint if you like
FACE_CHAMFER = 0.3  # a small 45 degree edge round the face

# Lengths along the cap, from its back (z = 0, on the bed, flush with the carrier's back) to its face.
LENGTH = case.KEY_LENGTH  # back of the cap to its face
HOLLOW = case.KEY_HOLLOW
CEILING = LENGTH - case.KEY_FACE_T  # the back of the face, where the switch's button presses

assert case.KEY_FACE_T - SYMBOL_DEPTH >= 0.9, "the face would be too thin under the symbols"


# ---- symbols, as outlines in x (right) and y (up) seen from the front ------------------------
def tri(x0, x1, h):
    """A triangle h tall with its base at x0 and its tip at x1 (x1 > x0)."""
    return [(x0, -h / 2), (x1, 0), (x0, h / 2)]


def bar(x0, x1, h):
    return [(x0, -h / 2), (x1, -h / 2), (x1, h / 2), (x0, h / 2)]


def mirror(shapes):
    return [[(-x, y) for x, y in reversed(s)] for s in shapes]


def scaled(shapes, k=0.85):
    """The symbols were drawn for a 17.5 mm cap; this fits them to the 14 mm one."""
    return [[(x * k, y * k) for x, y in s] for s in shapes]


H = 6.4  # symbol height, before scaling
NEXT = [tri(-4.6, -0.6, H), tri(-1.0, 3.0, H), bar(2.8, 4.1, H)]  # two triangles and a bar: >>|
NEXT = [[(x + 0.25, y) for x, y in s] for s in NEXT]
PLAY = [tri(-4.5, 0.3, H), bar(1.6, 2.8, H), bar(3.8, 5.0, H)]  # play and pause: |> ||
PLAY = [[(x - 0.25, y) for x, y in s] for s in PLAY]


def back_arrow():
    """The ↩ the simulator shows on its back key: an arrow pointing left along the bottom,
    curling up on the right into a short hook. One outline plus a solid head."""
    band, r_out, cx = 1.2, 2.5, 1.5
    r_in = r_out - band
    pts = case.arc(cx, 0, r_in, 90, -90, 16)  # inside of the curl, top to bottom
    pts += [(-1.6, -r_in), (-1.6, -r_out)]  # the stem along the bottom, to the head
    pts += case.arc(cx, 0, r_out, -90, 90, 16)  # outside of the curl, bottom to top; it ends square
    mid = -(r_out + r_in) / 2
    head = [(-1.4, mid - 2.0), (-1.4, mid + 2.0), (-4.9, mid)]
    dx, dy = 0.45, 0.85  # centre it on the cap
    return [[(x + dx, y + dy) for x, y in s] for s in (pts, head)]


SYMBOLS = {
    "previous": scaled(mirror(NEXT)),
    "play": scaled(PLAY),
    "next": scaled(NEXT),
    "back": scaled(back_arrow()),
}


# ---- the carrier, built as it prints: x across, y up, z from its back (on the bed) to the faces ------
def square(size, r=None):
    return case.key_square(0, 0, size, r)


def keycap(name):
    """One cap on its own, centred on x = y = 0, back at z = 0 and face up."""
    c = FACE_CHAMFER
    body = hull(prism(square(case.KEY_CAP), 0, LENGTH - c), prism(square(case.KEY_CAP - 2 * c), LENGTH - 0.01, LENGTH))
    h = HOLLOW / 2
    hollow = box(-h, h, -h, h, -1, CEILING)  # square corners: rounded ones left a hole in the mesh once the cap was joined to the frame
    cuts = [prism(s, LENGTH - SYMBOL_DEPTH, LENGTH + 1) for s in SYMBOLS[name]]
    return diff(body, hollow, *cuts)


LIFT = 0.002  # keeps faces that meet on the bed from coinciding exactly, which Blender's boolean cannot join


def hung_cap(name):
    """A cap with its two tabs, which reach out to the middle of its bridges. Centred as keycap()."""
    half, gap, w, t = case.KEY_CAP / 2, case.BRIDGE_GAP, case.BRIDGE_W, case.BRIDGE_T
    tabs = [box(-case.TAB_W / 2, case.TAB_W / 2, *sorted((s * (half - 0.5), s * (half + gap + w / 2))), 2 * LIFT, t + LIFT) for s in (-1, 1)]
    return union(keycap(name), *tabs)


def bridges(x):
    """A key's two bridges, in the carrier's coordinates. Each runs into the frame at both ends,
    past the edges of the key's window."""
    half, z, gap, w = case.KEY_CAP / 2, case.CTRL_Z, case.BRIDGE_GAP, case.BRIDGE_W
    return [box(x - case.KEY_WIN_X - 0.5, x + case.KEY_WIN_X + 0.5, *sorted((z + s * (half + gap), z + s * (half + gap + w))), LIFT, case.BRIDGE_T) for s in (-1, 1)]


def carrier():
    frame_cuts = [prism(case.key_window(k), -1, case.CARRIER_T + 1) for k in case.KEYS_X]
    frame_cuts += [box(x0, x1, z0, z1, -1, case.CARRIER_T + 1) for x0, z0, x1, z1 in case.BOARD_POCKETS]
    frame_cuts += [cylz(x, z, -1, case.CARRIER_T + 1, case.PILOT_M2) for x, z in case.BOARD_SCREWS]
    frame = diff(prism(case.CARRIER_OUTLINE, 0, case.CARRIER_T), *frame_cuts)
    pegs = [cylz(x, z, case.CARRIER_T - 0.01, case.CARRIER_T + case.PEG_L, case.PEG_D) for x, z in case.PEGS]
    caps = [move(k, case.CTRL_Z, 0, hung_cap(n)) for k, n in zip(case.KEYS_X, SYMBOLS)]
    return union(frame, *pegs, *[b for k in case.KEYS_X for b in bridges(k)], *caps)


def main():
    import build  # Blender's mesh helpers; only inside Blender

    for ob in list(build.bpy.data.objects):
        build.bpy.data.objects.remove(ob)
    ob = build.make(carrier())
    closed, volume, bounds = build.describe(ob)
    print(f"key-carrier closed={closed}  {volume * 1000:6.0f} mm3  " + " x ".join(f"{hi - lo:g}" for lo, hi in bounds) + " mm")
    build.write_stl(ob, HERE / "STL" / "key-carrier.stl")
    print("No problems found." if closed and volume > 0 else "PROBLEM: key-carrier is not a closed solid")


if __name__ == "__main__":
    main()
