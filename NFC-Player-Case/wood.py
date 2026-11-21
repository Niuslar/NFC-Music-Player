"""Carves wood grain from wood-grain.png into the sides of the chassis and the front panel's edges.

    /Applications/Blender.app/Contents/MacOS/Blender -b -P wood.py

Run build.py first; this only adds STL/chassis-wood.stl and STL/front-wood.stl beside the plain
ones, in the same print orientation. Print them in wood-fill PLA. Nothing else changes: the grain
is cut inwards only, so every face where parts meet keeps its size.

The grain runs side to side: across the top and down the sides (or front to back; see GRAIN).
Dark parts of the image are cut deepest, up to GRAIN_DEPTH. It is cut only into the two sides (and the bottom chamfers) and fades out over the last few millimetres at the
floor and at the top, so the first layer stays clean and the lid, which stays smooth, sits flush.
Nothing on a face that prints against the bed or over support, where relief would not print.
"""

import math
import os
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build  # noqa: E402
import case  # noqa: E402

IMAGE = HERE / "wood-grain.png"
# "front-to-back": the grain runs along the sides from front to back.
# "side-to-side": it runs across the top and down both sides, like a waterfall edge, so it is
# upright on the side walls. WOOD_GRAIN in the environment overrides this for a trial build.
GRAIN = os.environ.get("WOOD_GRAIN", "side-to-side")
GRAIN_DEPTH = 0.4  # deepest cut; a 0.4 mm nozzle resolves this on a vertical wall
# mm the whole image covers, along the grain and across it
TILE = (160.0, 80.0) if GRAIN == "front-to-back" else (256.0, 128.0)  # side to side, it spans the full 128 mm depth
STEP = 0.3  # mesh spacing on the grained faces
BLUR = 3  # pixels; removes detail finer than about 0.7 mm, which would not print
FADE_FLOOR = (0.0, 1.5)  # grain fades in over this height above the underside
FADE_TOP = (49.0, case.BODY_H - 0.5)  # and out below the lid
CLEAR = 0.05  # where there is no grain the carving surface stands this far outside the case


def grain():
    """The image as a 0..1 array of how deep to cut (1 = darkest), rows from the bottom up."""
    img = bpy.data.images.load(str(IMAGE))
    w, h = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)  # Blender stores rows bottom up
    lum = px[..., 0] * 0.2126 + px[..., 1] * 0.7152 + px[..., 2] * 0.0722
    k = np.ones(2 * BLUR + 1) / (2 * BLUR + 1)
    for axis in (0, 1):
        lum = np.apply_along_axis(lambda m: np.convolve(np.pad(m, BLUR, mode="reflect"), k, "valid"), axis, lum)
    lo, hi = np.percentile(lum, (2, 98))
    return 1 - np.clip((lum - lo) / (hi - lo), 0, 1)


def sample(depth, u, v):
    """Bilinear lookup; u, v in mm. Mirrored tiling so a repeat never shows a seam."""
    h, w = depth.shape
    def fold(t, n):
        t = np.mod(t, 2 * n)
        return np.where(t > n, 2 * n - t, t)
    x = fold(u / TILE[0] * (w - 1), w - 1)
    y = fold(v / TILE[1] * (h - 1), h - 1)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    x1, y1 = np.minimum(x0 + 1, w - 1), np.minimum(y0 + 1, h - 1)
    fx, fy = x - x0, y - y0
    return (depth[y0, x0] * (1 - fx) * (1 - fy) + depth[y0, x1] * fx * (1 - fy) + depth[y1, x0] * (1 - fx) * fy + depth[y1, x1] * fx * fy)


def grain_uv(x, y, z, nx, nz):
    """Where on the image a point of the case surface reads, in mm. render.py does the same."""
    left = x < case.W / 2
    if GRAIN == "front-to-back":
        return np.where(left, y, case.D - y + 37.0), z
    side = np.abs(nx) >= np.abs(nz)  # round the outline: up the left side, across the top, down the right
    return np.where(side, np.where(left, z, 2 * case.H + case.W - z), case.H + x), y


def smooth(t):
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


def profile():
    """The case silhouette (x, z), counter-clockwise, split finely where it gets grain."""
    pts = case.outline()
    out = []
    for i, a in enumerate(pts):
        b = pts[(i + 1) % len(pts)]
        n = 1
        if min(a[1], b[1]) < FADE_TOP[1]:
            n = max(1, math.ceil(math.dist(a, b) / STEP))
        out += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n)]
    p = np.array(out)
    # outward normals at the points: the outline runs counter-clockwise, so outward is (dz, -dx)
    t = np.roll(p, -1, 0) - np.roll(p, 1, 0)
    nrm = np.stack([t[:, 1], -t[:, 0]], 1)
    return p, nrm / np.linalg.norm(nrm, axis=1, keepdims=True)


def carver(depth):
    """The case envelope with grain pressed into its sides: a closed mesh in case coordinates."""
    p, nrm = profile()
    ys = np.arange(-2.0, case.D + 2.0 + 1e-9, STEP)
    z = p[:, 1]
    weight = smooth((z - FADE_FLOOR[0]) / (FADE_FLOOR[1] - FADE_FLOOR[0])) * (1 - smooth((z - FADE_TOP[0]) / (FADE_TOP[1] - FADE_TOP[0])))
    weight *= np.abs(nrm[:, 0]) > 0.3  # sides and chamfers, never the floor or the top
    bm = bmesh.new()
    rings = []
    for y in ys:
        end = smooth(np.minimum(y + 1.0, case.D + 1.0 - y))  # flat beyond both ends of the case
        u, v = grain_uv(p[:, 0], y, z, nrm[:, 0], nrm[:, 1])
        cut = GRAIN_DEPTH * weight * end * sample(depth, u, v)
        off = CLEAR - cut
        xs, zs = p[:, 0] + nrm[:, 0] * off, p[:, 1] + nrm[:, 1] * off
        rings.append([bm.verts.new((float(a), float(y), float(b))) for a, b in zip(xs, zs)])
    n = len(p)
    for r0, r1 in zip(rings, rings[1:]):
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((r0[i], r1[i], r1[j], r0[j]))
    for ring, flip in ((rings[0], False), (rings[-1], True)):
        c = bm.verts.new((sum(v.co.x for v in ring) / n, ring[0].co.y, sum(v.co.z for v in ring) / n))
        for i in range(n):
            f = (c, ring[(i + 1) % n], ring[i])
            bm.faces.new(f[::-1] if flip else f)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return build._object(bm, "carver")


FRONT_BACK = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, -1, 0, case.FRONT_T), (0, 0, 0, 1)))  # case to panel coordinates


def main():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    depth = grain()
    problems = []
    jobs = {
        "chassis-wood": (case.chassis(), Matrix.Identity(4)),
        "front-wood": (case.xf(case.FRONT_M, case.front()), FRONT_BACK),
    }
    for name, (node, back) in jobs.items():
        part = build.make(node)
        part = build._boolean(part, carver(depth), "INTERSECT")
        part.data.transform(back)
        closed, volume, bounds = build.describe(part)
        tris = len(build.triangles(part))
        print(f"{name:14s} closed={closed}  {volume:6.1f} cm3  {tris} triangles  " + " x ".join(f"{hi - lo:g}" for lo, hi in bounds) + " mm")
        if not closed or volume <= 0:
            problems.append(f"{name} is not a closed solid")
        build.write_stl(part, HERE / "STL" / f"{name}.stl")
        build._drop(part)
    print("\n".join("PROBLEM: " + p for p in problems) or "No problems found.")


if __name__ == "__main__":
    main()
