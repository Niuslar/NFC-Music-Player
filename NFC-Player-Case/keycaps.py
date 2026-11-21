"""The four key caps, with their symbols cut into the face. Millimetres.

    /Applications/Blender.app/Contents/MacOS/Blender -b -P keycaps.py

Writes STL/keycap-previous.stl, keycap-play.stl, keycap-next.stl and keycap-back.stl.

Each cap slides in a square hole through the brass and the front panel, its face flush with the
brass, and presses a 6 x 6 mm tactile switch on the front board behind it. A lip round its back,
chamfered at 45 degrees, seats against the inside of the panel and stops it coming out of the front.
The back is hollow: the switch's body stands inside it, and the button presses the back of the face.
All the sizes come from case.py (KEY_*, TACT_*), which also makes the holes and the spacer.

Each cap is laid face down, ready to print: no support, and the face comes out as smooth as the
bed. The symbols read the right way round from the front of the case. Try one cap in the fit gauge's
square hole first: it should slide freely without rattling.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build  # noqa: E402  (Blender mesh helpers)
import case  # noqa: E402
from case import diff, hull, prism, xf  # noqa: E402

SYMBOL_DEPTH = 0.6  # how deep the symbols are cut; fill them with paint if you like
FACE_CHAMFER = 0.3  # a small 45 degree edge round the face

# Lengths along the cap, from its back (z = 0) to its face.
LENGTH = case.KEY_LENGTH  # back of the cap to its face
LIP_FLAT, HOLLOW = case.KEY_LIP_FLAT, case.KEY_HOLLOW
CEILING = LENGTH - case.KEY_FACE_T  # the back of the face, where the switch's button presses

# The lip's chamfer meets the panel's hole where the chamfer is as wide as the hole, so that
# is where the cap stops: KEY_LIP_T from its back.
assert abs(LIP_FLAT + (case.KEY_CAP + 2 * case.KEY_LIP - case.KEY_HOLE) / 2 - case.KEY_LIP_T) < 1e-6, "the lip must seat at KEY_LIP_T"
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


# ---- the cap, built face up (z = 0 its back), then turned over to print --------------------------
def square(size, r=None):
    return case.key_square(0, 0, size, r)


def keycap(name):
    c, lip = FACE_CHAMFER, case.KEY_CAP + 2 * case.KEY_LIP
    body = hull(prism(square(case.KEY_CAP), 0, LENGTH - c), prism(square(case.KEY_CAP - 2 * c), LENGTH - 0.01, LENGTH))
    rim = hull(prism(square(lip), 0, LIP_FLAT), prism(square(case.KEY_CAP), 0, LIP_FLAT + case.KEY_LIP))
    hollow = prism(square(HOLLOW, 0.8), -1, CEILING)
    cuts = [prism(s, LENGTH - SYMBOL_DEPTH, LENGTH + 1) for s in SYMBOLS[name]]
    return diff(case.union(body, rim), hollow, *cuts)


TO_PRINT = [(-1, 0, 0, 0), (0, 1, 0, 0), (0, 0, -1, LENGTH)]  # turned over about y: face on the bed, still reads right from the front
# From the printed STL to the case, round a key's centre at rest: x across, y back from the brass, z up.
TO_CASE = [(-1, 0, 0, 0), (0, 0, 1, -case.KEY_PROUD), (0, 1, 0, 0)]


def main():
    for ob in list(build.bpy.data.objects):
        build.bpy.data.objects.remove(ob)
    out = HERE / "STL"
    problems = []
    for n in SYMBOLS:
        name = f"keycap-{n}"
        ob = build.make(xf(TO_PRINT, keycap(n)))
        closed, volume, bounds = build.describe(ob)
        print(f"{name:16s} closed={closed}  {volume * 1000:6.0f} mm3  " + " x ".join(f"{hi - lo:g}" for lo, hi in bounds) + " mm")
        if not closed or volume <= 0:
            problems.append(f"{name} is not a closed solid")
        build.write_stl(ob, out / f"{name}.stl")
        build._drop(ob)
    print("\n".join("PROBLEM: " + p for p in problems) or "No problems found.")


if __name__ == "__main__":
    main()
