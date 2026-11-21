"""Builds the case from case.py with Blender: STLs, the OpenSCAD copy, the brass template, and checks.

    /Applications/Blender.app/Contents/MacOS/Blender -b -P build.py

Every mesh is checked for being closed, and the assembled parts are checked against
each other and against stand-ins for the boards, so a change that makes two things
collide is reported here instead of at the printer.
"""

import collections
import struct
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import case  # noqa: E402

SEGMENTS = 48


def _object(bm, name="shape"):
    me = bpy.data.meshes.new(name)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _drop(ob):
    me = ob.data
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)


def _boolean(a, b, op):
    mod = a.modifiers.new("b", "BOOLEAN")
    mod.operation, mod.object, mod.solver = op, b, "EXACT"
    done = bpy.data.meshes.new_from_object(a.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    a.modifiers.clear()
    old, a.data = a.data, done
    bpy.data.meshes.remove(old)
    _drop(b)
    return a


def make(node):
    """Turns a case.py shape tree into a Blender mesh object."""
    p = node.p
    if node.kind == "box":
        bm = bmesh.new()
        lo, hi = p["lo"], p["hi"]
        bmesh.ops.create_cube(bm, size=1.0)
        size = [hi[i] - lo[i] for i in range(3)]
        centre = [(hi[i] + lo[i]) / 2 for i in range(3)]
        bm.transform(Matrix.Translation(centre) @ Matrix.Diagonal((*size, 1.0)))
        return _object(bm)
    if node.kind == "cyl":
        bm = bmesh.new()
        (z0, z1), r = p["z"], p["d"] / 2
        bmesh.ops.create_cone(bm, cap_ends=True, segments=SEGMENTS, radius1=r, radius2=r, depth=z1 - z0)
        bm.transform(Matrix.Translation((p["at"][0], p["at"][1], (z0 + z1) / 2)))
        return _object(bm)
    if node.kind == "prism":
        bm = bmesh.new()
        z0, z1 = p["z"]
        low = [bm.verts.new((x, y, z0)) for x, y in p["pts"]]
        high = [bm.verts.new((x, y, z1)) for x, y in p["pts"]]
        bm.faces.new(low[::-1])
        bm.faces.new(high)
        n = len(low)
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((low[i], low[j], high[j], high[i]))
        return _object(bm)
    if node.kind == "hull":
        bm = bmesh.new()
        for child in node.children:
            ob = make(child)
            for v in ob.data.vertices:
                bm.verts.new(v.co)
            _drop(ob)
        result = bmesh.ops.convex_hull(bm, input=bm.verts)
        spare = list({e for e in result["geom_interior"] + result["geom_unused"] if isinstance(e, bmesh.types.BMVert)})
        bmesh.ops.delete(bm, geom=spare, context="VERTS")
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        return _object(bm)
    parts = [make(c) for c in node.children]
    first = parts[0] if parts else _object(bmesh.new())
    op = {"union": "UNION", "xf": "UNION", "diff": "DIFFERENCE", "inter": "INTERSECT"}[node.kind]
    for other in parts[1:]:
        first = _boolean(first, other, op)
    if node.kind == "xf":
        m = Matrix([*p["m"], (0, 0, 0, 1)])
        first.data.transform(m)
        if m.determinant() < 0:
            first.data.flip_normals()
    return first


def triangles(ob):
    me = ob.data
    me.calc_loop_triangles()
    return [[tuple(me.vertices[i].co) for i in t.vertices] for t in me.loop_triangles]


def describe(ob):
    """Returns (is closed, volume in cm3, bounding box)."""
    tris = triangles(ob)
    edges = collections.Counter()
    volume = 0.0
    for a, b, c in tris:
        ka, kb, kc = (tuple(round(v, 4) for v in p) for p in (a, b, c))
        for e in ((ka, kb), (kb, kc), (kc, ka)):
            edges[e] += 1
        volume += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6
    closed = bool(tris) and all(edges.get((b, a), 0) == n for (a, b), n in edges.items())
    pts = [p for t in tris for p in t]
    box = [(round(min(p[i] for p in pts), 2), round(max(p[i] for p in pts), 2)) for i in range(3)] if pts else []
    return closed, volume / 1000, box


def write_stl(ob, path):
    tris = triangles(ob)
    with open(path, "wb") as f:
        f.write(b"NFC Player Case v3".ljust(80, b" "))
        f.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            f.write(struct.pack("<12fH", 0, 0, 0, *a, *b, *c, 0))


def overlap(a, b):
    """Volume two objects share, in mm3. Neither object is changed."""
    x, y = a.copy(), b.copy()
    x.data, y.data = a.data.copy(), b.data.copy()
    for ob in (x, y):
        bpy.context.scene.collection.objects.link(ob)
    shared = _boolean(x, y, "INTERSECT")
    volume = describe(shared)[1] * 1000 if len(shared.data.polygons) else 0.0
    _drop(shared)
    return volume


def stand_ins():
    """Boxes for the bought parts, in case coordinates, at their nominal positions."""
    c = case
    cx, cz = c.cradle_centre()
    pcb_y = c.FRONT_T + c.LCD_GLASS
    pi_y = 62.0  # with the DAC directly above the Pi and its sockets 6.5 mm from the rear panel
    dac_z = c.FLOOR + c.STANDOFF_H + 1.6 + 11  # underside of the DAC board, straight on the Pi
    board_back = c.FRONT_T + c.BOARD_T  # the back of the front board, where its parts stand
    lean = [(1, 0, 0, 0), (0, 1, c.TAN, -c.TAN * c.H), (0, 0, 1, 0)]
    reader_y = c.READER_Y  # antenna face, reader in the middle grooves
    out = {
        "screen board": c.box(cx - 29, cx + 29, pcb_y, pcb_y + 1.6, cz - 17.5, cz + 17.5),
        "screen glass": c.box(cx - 24, cx + 24, c.FRONT_T + 0.05, pcb_y, cz - 17.5, cz + 17.5),
        "screen plug and wires": c.box(cx - 27, cx + 27, pcb_y + 1.6, pcb_y + 1.6 + 12, cz - 12, cz + 12),
        "encoder body": c.box(c.KNOB_X - 6.25, c.KNOB_X + 6.25, c.FRONT_T - 1.6, c.FRONT_T + 12, c.CTRL_Z - 6.7, c.CTRL_Z + 6.7),
        "Pi": c.box(c.PI_X, c.PI_X + 65, pi_y, pi_y + 30, c.FLOOR + c.STANDOFF_H, c.FLOOR + c.STANDOFF_H + 1.6 + 9),
        "ribbon plug on the DAC": c.box(c.PI_X + 4, c.PI_X + 61, pi_y - 2, pi_y + 9, dac_z + 1.6 + 2.5, dac_z + 1.6 + 6 + 9),
        "power key": c.cyly(c.POWER_X, c.CTRL_Z, c.FRONT_T + 0.05, c.FRONT_T + c.POWER_BODY[1], c.POWER_BODY[0]),
        "front board": c.xf(c.FRONT_M, c.prism(c.BOARD_OUTLINE, -c.BOARD_T, -0.05)),
        "board's sockets and small parts": c.box(c.BOARD_X[0] + 6, c.BOARD_X[1] - 0.5, board_back, board_back + 5, c.BOARD_Z[0] + 0.5, 38.0),
        "board's 40-pin header": c.box(c.PI_HEADER_X - 29.7, c.PI_HEADER_X + 29.7, board_back, board_back + 9, 41.0, 51.0),
        "ribbon plug on the board": c.box(c.PI_HEADER_X - 29.5, c.PI_HEADER_X + 29.5, board_back + 9, board_back + 18, 40.5, 51.5),
        "ribbon": c.box(c.PI_HEADER_X - 26, c.PI_HEADER_X + 26, board_back + 18, pi_y + 6, dac_z + 1.6 + 6 + 9, dac_z + 1.6 + 6 + 10),
        "leads on the board's headers": c.box(31.0, 76.0, board_back + 8.5, board_back + 23, 6.5, 18.5),
        "DAC board": c.box(c.PI_X, c.PI_X + 65, pi_y, pi_y + 56.5, dac_z, dac_z + 1.6 + 8),
        "DAC sockets": c.box(c.PI_X + 5, c.PI_X + 60, pi_y + 44, c.D - c.REAR_T - 0.3, dac_z + 1.6, dac_z + 1.6 + 13.5),
        "NFC reader": c.xf(lean, c.box(c.CARD_X - 21.35, c.CARD_X + 21.35, reader_y + 0.05, reader_y + 1.65, c.PN532_CENTRE_Z - 20.2, c.PN532_CENTRE_Z + 20.2)),
        "NFC reader parts": c.xf(lean, c.box(c.CARD_X - 19, c.CARD_X + 19, reader_y + 1.65, reader_y + 5.5, c.PN532_CENTRE_Z - 16, c.PN532_CENTRE_Z + 20.2)),
        "card in slot": c.xf(lean, c.box(c.CARD_X - 27, c.CARD_X + 27, c.CARD_Y - 0.38, c.CARD_Y + 0.38, c.CARD_STOP_Z + 0.05, c.CARD_STOP_Z + 85.6)),
        "five stored cards": c.box(59.5 - 42.8, 59.5 + 42.8, 48.5 - 27, 48.5 + 27, c.H - c.TRAY_DEPTH + 0.05, c.H - c.TRAY_DEPTH + 3.85),
        "USB-C socket": c.cyly(c.USB_X, c.USB_Z, c.D - c.REAR_T - 25, c.D - c.REAR_T - 0.05, 11.0),
    }
    if c.REAR_JACK:
        out["headphone socket"] = c.cyly(c.PHONES_X, c.PHONES_Z, c.D - c.REAR_T - 22, c.D - c.REAR_T - 0.05, 10.0)
    for i, k in enumerate(c.KEYS_X):
        out[f"switch {i + 1}"] = c.box(k - 6.9, k + 6.9, c.FRONT_T - c.BRASS_T - c.KEY_PLATE + 0.05, c.FRONT_T - 0.05, c.CTRL_Z - 6.9, c.CTRL_Z + 6.9)
    return out


def main():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    stl_dir = HERE / "STL"
    stl_dir.mkdir(exist_ok=True)
    problems = []
    world = {}
    print("\n== printed parts ==")
    for name, build in case.PARTS.items():
        ob = make(build())
        closed, volume, box = describe(ob)
        size = " x ".join(f"{hi - lo:g}" for lo, hi in box)
        print(f"{name:15s} closed={closed}  {volume:6.1f} cm3  {size} mm")
        if not closed or volume <= 0:
            problems.append(f"{name} is not a closed solid")
        write_stl(ob, stl_dir / f"{name}.stl")
        if case.PLACE[name] is not None:
            ob.data.transform(Matrix([*case.PLACE[name].p["m"], (0, 0, 0, 1)]))
            ob.name = name
            world[name] = ob
        else:
            _drop(ob)
    brass = make(case.xf(case.FRONT_M, case.brass()))
    brass.name = "brass"
    closed, volume, box = describe(brass)
    print(f"{'brass':15s} closed={closed}  {volume:6.1f} cm3  " + " x ".join(f"{hi - lo:g}" for lo, hi in box) + " mm")
    world["brass"] = brass

    print("\n== printed parts against each other (shared volume, mm3) ==")
    names = list(world)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            v = overlap(world[a], world[b])
            if v > 0.5:
                print(f"  {a} / {b}: {v:.1f}")
                problems.append(f"{a} and {b} overlap by {v:.1f} mm3")
    print("  done")

    print("\n== bought parts against the print (shared volume, mm3) ==")
    for label, node in stand_ins().items():
        ob = make(node)
        hits = [(n, overlap(ob, world[n])) for n in names]
        hits = [(n, v) for n, v in hits if v > 0.5]
        print(f"  {label:22s}", ", ".join(f"{n} {v:.1f}" for n, v in hits) or "clear")
        problems += [f"{label} hits {n} ({v:.1f} mm3)" for n, v in hits]
        _drop(ob)

    (HERE / "NFC-Player-Case.scad").write_text(case.scad_file())
    (HERE / "Brass-Front-Template.svg").write_text(case.brass_svg())
    bpy.ops.wm.save_as_mainfile(filepath=str(HERE / "parts.blend"))
    print("\n== result ==")
    print("\n".join("PROBLEM: " + p for p in problems) or "No problems found.")


if __name__ == "__main__":  # pictures.py imports this file for make()
    main()
