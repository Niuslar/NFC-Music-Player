"""The four keycaps for the Kailh Choc V1 keys, with their symbols cut into the top. Millimetres.

    /Applications/Blender.app/Contents/MacOS/Blender -b -P keycaps.py

Writes STL/keycap-previous.stl, keycap-play.stl, keycap-next.stl, keycap-back.stl and
keycap-fit-test.stl. Print the fit test first: it has three pairs of legs marked with 1, 2
and 3 dots, from thinnest to thickest. Push each into a switch, then set LEG_W to the one that holds
firmly without forcing and rebuild.

Every cap is laid top down, legs up, ready to print: no support, and the top comes out
as smooth as the bed. The symbols are seen the right way round from the front of the case.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build  # noqa: E402  (Blender mesh helpers)
import case  # noqa: E402
from case import box, diff, hull, prism, rrect, union, xf  # noqa: E402

# ---- the cap ------------------------------------------------------------------------
CAP_W, CAP_H = 17.5, 16.5  # across and up; the keys are 18 mm apart (case.KEYS_X), so 0.5 mm between caps
CAP_T = 2.5  # thickness, as in the key drawings (drawings.KEYCAP_T)
CAP_R = 1.5  # corner radius
TOP_CHAMFER = 0.6  # 45 degrees round the top edge
SYMBOL_DEPTH = 0.6  # how deep the symbols are cut; fill them with paint if you like

# ---- the legs that go into the switch stem ---------------------------------------------
# A Choc V1 stem has two slots side by side, 5.7 mm apart, each about 1.2 wide and 3.0 tall.
# The legs are a little smaller so a printed cap goes in without splitting the stem.
LEG_PITCH = 5.7
LEG_W, LEG_H = 1.15, 2.9  # MEASURE: confirm LEG_W with keycap-fit-test.stl
LEG_L = 3.0  # how far the legs reach into the stem
LEG_TIP = 0.3  # chamfer on the leg ends so they find the slots

assert CAP_W < case.KEYS_X[1] - case.KEYS_X[0], "neighbouring caps would touch"


# ---- symbols, as outlines in x (right) and y (up) seen from the front ------------------------
def tri(x0, x1, h):
    """A triangle h tall with its base at x0 and its tip at x1 (x1 > x0)."""
    return [(x0, -h / 2), (x1, 0), (x0, h / 2)]


def bar(x0, x1, h):
    return [(x0, -h / 2), (x1, -h / 2), (x1, h / 2), (x0, h / 2)]


def mirror(shapes):
    return [[(-x, y) for x, y in reversed(s)] for s in shapes]


H = 6.4  # symbol height
NEXT = [tri(-4.6, -0.6, H), tri(-1.0, 3.0, H), bar(2.8, 4.1, H)]  # two triangles and a bar: >>|
NEXT = [[(x + 0.25, y) for x, y in s] for s in NEXT]
PLAY = [tri(-4.5, 0.3, H), bar(1.6, 2.8, H), bar(3.8, 5.0, H)]  # play and pause: |> ||
PLAY = [[(x - 0.25, y) for x, y in s] for s in PLAY]


def back_arrow():
    """A U-turn arrow pointing left, like the return key: one outline plus its head."""
    band, r_out, cx = 1.25, 3.0, 1.4
    r_in = r_out - band
    pts = case.arc(cx, 0, r_out, 90, -90, 16)  # outside of the bend, top to bottom
    pts += [(-2.0, -r_out), (-2.0, -r_in)]  # the tail along the bottom
    pts += case.arc(cx, 0, r_in, -90, 90, 16)  # inside of the bend, bottom to top
    pts += [(-1.6, r_in)]  # along the top to the head
    pts += [(-1.6, r_out)]
    pts.reverse()  # counter-clockwise for prism()
    head = [(-1.4, r_out + 1.6), (-5.2, (r_out + r_in) / 2), (-1.4, r_in - 1.6)]
    shapes = [pts, head]
    dx, dy = 0.4, -0.8  # centre it on the cap
    return [[(x + dx, y + dy) for x, y in s] for s in shapes]


SYMBOLS = {
    "previous": mirror(NEXT),
    "play": PLAY,
    "next": NEXT,
    "back": back_arrow(),
}


# ---- solids, built top up (z = 0 is the underside of the cap), then turned over to print ---------
def body():
    full = rrect(-CAP_W / 2, -CAP_H / 2, CAP_W / 2, CAP_H / 2, CAP_R)
    c = TOP_CHAMFER
    top = rrect(-CAP_W / 2 + c, -CAP_H / 2 + c, CAP_W / 2 - c, CAP_H / 2 - c, CAP_R - c)
    return hull(prism(full, 0, CAP_T - c), prism(top, CAP_T - 0.01, CAP_T))


def legs(x_centre=0.0, w=LEG_W):
    t = LEG_TIP
    out = []
    for s in (-1, 1):
        x = x_centre + s * LEG_PITCH / 2
        out.append(hull(
            box(x - w / 2, x + w / 2, -LEG_H / 2, LEG_H / 2, -LEG_L + t, 0.2),
            box(x - w / 2 + t, x + w / 2 - t, -LEG_H / 2 + t, LEG_H / 2 - t, -LEG_L, -LEG_L + t),
        ))
    return out


def keycap(name):
    cuts = [prism(s, CAP_T - SYMBOL_DEPTH, CAP_T + 1) for s in SYMBOLS[name]]
    return diff(union(body(), *legs()), *cuts)


def fit_test():
    """A bar with three pairs of legs, marked with 1, 2 and 3 dots from thinnest to thickest."""
    widths = (LEG_W - 0.1, LEG_W, LEG_W + 0.1)
    pitch = 12.0
    plate = box(-pitch * 1.5, pitch * 1.5, -4.0, 4.0, 0, 1.6)
    parts = [plate]
    dots = []
    for i, w in enumerate(widths):
        x = (i - 1) * pitch
        parts += legs(x, w)
        dots += [case.cylz(x + (j - i / 2) * 1.6, 2.6, 1.0, 2.6, 0.9) for j in range(i + 1)]
    return diff(union(*parts), *dots)


TO_PRINT = [(-1, 0, 0, 0), (0, 1, 0, 0), (0, 0, -1, CAP_T)]  # turned over about y: top on the bed, still reads right from the front


def main():
    for ob in list(build.bpy.data.objects):
        build.bpy.data.objects.remove(ob)
    out = HERE / "STL"
    problems = []
    jobs = {f"keycap-{n}": xf(TO_PRINT, keycap(n)) for n in SYMBOLS}
    jobs["keycap-fit-test"] = xf([(-1, 0, 0, 0), (0, 1, 0, 0), (0, 0, -1, 1.6)], fit_test())  # plate down, legs up
    for name, node in jobs.items():
        ob = build.make(node)
        closed, volume, bounds = build.describe(ob)
        print(f"{name:18s} closed={closed}  {volume * 1000:6.0f} mm3  " + " x ".join(f"{hi - lo:g}" for lo, hi in bounds) + f" mm  z {bounds[2][0]:g}..{bounds[2][1]:g}")
        if not closed or volume <= 0:
            problems.append(f"{name} is not a closed solid")
        build.write_stl(ob, out / f"{name}.stl")
        build._drop(ob)
    print("\n".join("PROBLEM: " + p for p in problems) or "No problems found.")


if __name__ == "__main__":
    main()
