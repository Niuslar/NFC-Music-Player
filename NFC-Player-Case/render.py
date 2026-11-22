"""Renders the case from the meshes build.py made. Run build.py first.

    blender -b NFC-Player-Render.blend -P render.py

It reuses the scene's camera, lights and materials, swaps in the freshly built printed parts and
key carrier, and moves the knob, screws and cards to match case.py. Run wood.py too to render the
wood-grain chassis; otherwise the plain one is shown, still in wood. The front is black, with a
steel power key, an aluminium knob and silver key caps.
The knob, screw heads, feet, screen and cards are stand-ins for bought parts.
"""

import math
import os
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import case as c  # noqa: E402
import wood  # noqa: E402

D = bpy.data
OLD = ("Brass panel", "Card guide", "Chassis", "Front support", "Lid", "Rear", "brass", *c.PARTS)
for name in OLD:  # the printed parts from the last render, or from revision 2.1
    if name in D.objects:
        D.objects.remove(D.objects[name])

with D.libraries.load(str(HERE / "parts.blend")) as (src, dst):
    dst.objects = list(src.objects)


def stl_mesh(path, matrix):
    """A mesh from an STL, moved by matrix (three rows of four)."""
    bpy.ops.wm.stl_import(filepath=str(path))
    ob = bpy.context.selected_objects[0]
    me = ob.data
    D.objects.remove(ob)
    me.transform(Matrix([*matrix, (0, 0, 0, 1)]))
    return me


def wood_material():
    """Wood-fill PLA, sanded and stained: wood-grain.png laid on the same way wood.py carves it."""
    m = D.materials.get("Printed wood") or D.materials.new("Printed wood")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    n = nt.nodes.new
    geo, sep, nsep = n("ShaderNodeNewGeometry"), n("ShaderNodeSeparateXYZ"), n("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Position"], sep.inputs[0])
    nt.links.new(geo.outputs["Normal"], nsep.inputs[0])

    def math(op, a, b=0.0):
        node = n("ShaderNodeMath")
        node.operation = op
        for i, v in enumerate((a, b)):
            if isinstance(v, float):
                node.inputs[i].default_value = v
            else:
                nt.links.new(v, node.inputs[i])
        return node.outputs[0]

    def pick(flag, yes, no):  # flag ? yes : no, with flag 0 or 1
        return math("ADD", math("MULTIPLY", flag, yes), math("MULTIPLY", math("SUBTRACT", 1.0, flag), no))

    x, y, z = sep.outputs
    nx, nz = math("ABSOLUTE", nsep.outputs[0]), math("ABSOLUTE", nsep.outputs[2])
    left = math("LESS_THAN", x, c.W / 2)
    if wood.GRAIN == "front-to-back":  # as wood.grain_uv, with the lid's top read across
        u_side = pick(left, y, math("ADD", math("SUBTRACT", c.D, y), 37.0))
        top = math("GREATER_THAN", nz, 0.7)
        u, v = pick(top, y, u_side), pick(top, math("ADD", x, 23.0), z)
    else:
        side = math("GREATER_THAN", nx, nz)
        u_side = pick(left, z, math("SUBTRACT", 2 * c.H + c.W, z))
        u, v = pick(side, u_side, math("ADD", x, c.H)), y
    u, v = math("DIVIDE", u, wood.TILE[0]), math("DIVIDE", v, wood.TILE[1])
    uv = n("ShaderNodeCombineXYZ")
    nt.links.new(u, uv.inputs[0])
    nt.links.new(v, uv.inputs[1])
    tex = n("ShaderNodeTexImage")
    tex.image = D.images.load(str(wood.IMAGE), check_existing=True)
    tex.extension = "MIRROR"
    nt.links.new(uv.outputs[0], tex.inputs["Vector"])
    bsdf, out = n("ShaderNodeBsdfPrincipled"), n("ShaderNodeOutputMaterial")
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.5
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    return m


# Chassis and lid in sanded wood-fill PLA with the grain from wood.py (when it has been run);
# the rear stays charcoal, and the front is black (below).
WOOD = {"chassis": ("chassis-wood", [(1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0)]), "lid": (None, None)}
for ob in dst.objects:
    bpy.context.scene.collection.objects.link(ob)
    if ob.name in WOOD and WOOD[ob.name][0] and (HERE / "STL" / f"{WOOD[ob.name][0]}.stl").exists():
        old, ob.data = ob.data, stl_mesh(HERE / "STL" / f"{WOOD[ob.name][0]}.stl", WOOD[ob.name][1])
        D.meshes.remove(old)
    ob.data.materials.clear()
    ob.data.materials.append(wood_material() if ob.name in WOOD else D.materials["Printed charcoal"])
    for poly in ob.data.polygons:
        poly.use_smooth = False


def numbered(base):
    return [D.objects[n] for n in sorted(D.objects.keys()) if n == base or n.startswith(base + ".")]


# The key caps now come in with the printed parts, on the key carrier; the scene's own separate
# caps (named "Choc keycap", from the earlier keys) go.
for ob in numbered("Choc keycap"):
    D.objects.remove(ob)
spots = [(x, z) for x in c.SCREW_X for z in c.SCREW_Z]
for ob, (x, z) in zip(numbered("Front M3 head"), spots):
    ob.location = (x, -0.9, z)
for ob, (x, z) in zip(numbered("Screw slot"), spots):
    ob.location = (x, -1.85, z)
for ob, (x, y) in zip(numbered("Lid screw"), [(x, y) for x in c.LID_SCREW_X for y in c.LID_SCREW_Y]):
    ob.dimensions.z = 1.5
    ob.location = (x, y, c.H - 1.6 + 0.75)
for ob, (x, y) in zip(numbered("Foot"), [(x, y) for x in (18, c.W - 18) for y in (18, c.D - 18)]):
    ob.location = (x, y, -2.5)

def material(name, colour, rough=0.45, emit=0.0):
    m = D.materials.get(name) or D.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*colour, 1)
    bsdf.inputs["Roughness"].default_value = rough
    if emit:
        bsdf.inputs["Emission Color"].default_value = (*colour, 1)
        bsdf.inputs["Emission Strength"].default_value = emit
    return m


def metal(name, colour, rough):
    m = material(name, colour, rough)
    m.node_tree.nodes["Principled BSDF"].inputs["Metallic"].default_value = 1.0
    return m


def lathe(name, profile, mat, steps=128):
    """A solid of revolution about the power key's axis (pointing out of the front, -y) from
    a profile of (radius, y) points, y negative in front of the panel."""
    me = D.meshes.new(name)
    bm = bmesh.new()
    verts = [bm.verts.new((r, y, 0.0)) for r, y in profile]
    edges = [bm.edges.new(pair) for pair in zip(verts, verts[1:])]
    bmesh.ops.spin(bm, geom=verts + edges, cent=(0, 0, 0), axis=(0, 1, 0), angle=6.283185307, steps=steps, use_merge=True)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bm.to_mesh(me)
    bm.free()
    return placed(name, me, mat)


def placed(name, me, mat):
    ob = D.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = (c.POWER_X, 0.0, c.CTRL_Z)
    me.materials.append(mat)
    for poly in me.polygons:
        poly.use_smooth = True
    me.set_sharp_from_angle(angle=0.6)
    return ob


# The power key: the stainless 12 mm flat-head push button with a green ring and power symbol
# (sourcing map, 1NO, 3-6 V), lit. A stand-in made here each time; only its face shows.
for name in [n for n in D.objects.keys() if n.startswith("Power key")]:
    D.objects.remove(D.objects[name])
steel = metal("Stainless steel", (0.80, 0.79, 0.77), 0.22)
green = material("Power light", (0.06, 1.0, 0.18), 0.4, 5.0)
HEAD, FACE = 2.0, 1.85  # the bezel's height on the panel; the button's face, just behind it
lathe("Power key bezel", [(4.95, -1.2), (4.95, -HEAD + 0.1), (5.05, -HEAD), (6.2, -HEAD), (6.6, -HEAD + 0.12), (6.9, -HEAD + 0.4),
                          (7.0, -HEAD + 0.75), (7.0, 0.0), (4.95, 0.0)], steel)
lathe("Power key ring", [(4.95, -1.6), (4.5, -1.6)], green)  # the lit gap round the button
lathe("Power key button", [(0.0, -FACE), (4.15, -FACE), (4.4, -FACE + 0.1), (4.45, -FACE + 0.3), (4.45, -1.0)], steel)

# The power symbol on the button's face: an open circle with a bar through its gap, lit.
bm = bmesh.new()
y, gap, n = -FACE - 0.02, 0.62, 48
arc = [gap + (6.283185307 - 2 * gap) * i / n for i in range(n + 1)]
inner = [bm.verts.new((1.6 * math.sin(a), y, 1.6 * math.cos(a))) for a in arc]
outer = [bm.verts.new((2.2 * math.sin(a), y, 2.2 * math.cos(a))) for a in arc]
for i in range(n):
    bm.faces.new((inner[i], inner[i + 1], outer[i + 1], outer[i]))
bm.faces.new([bm.verts.new((x, y, z)) for x, z in ((-0.3, 0.3), (0.3, 0.3), (0.3, 2.6), (-0.3, 2.6))])
bm.normal_update()
me = D.meshes.new("Power key symbol")
bm.to_mesh(me)
bm.free()
placed("Power key symbol", me, green)

knob = D.objects["Volume knob"]
knob.location = (c.KNOB_X, -9.0, c.CTRL_Z)
knob.scale = (c.KNOB_D / 26.0, c.KNOB_D / 26.0, 1.0)
for name, d, y in (("Jack surround", 9.0, c.D + 0.5), ("Jack aperture", 3.5, c.D + 1.1)):
    D.objects[name].location = (c.PHONES_X, y, c.PHONES_Z)
    D.objects[name].scale = (d / D.objects[name].dimensions.x * D.objects[name].scale.x,) * 2 + (1.0,)
    D.objects[name].hide_render = not c.REAR_JACK  # otherwise the DAC's own socket is used

# The black front: black PLA, the key caps in silver PLA, an aluminium knob and steel screw
# heads, to go with the stainless power key.
D.objects["front"].data.materials[0] = material("Printed black", (0.012, 0.012, 0.013), 0.55)
D.objects["key-carrier"].data.materials[0] = metal("Silver PLA", (0.62, 0.62, 0.64), 0.4)
D.materials["Silver PLA"].node_tree.nodes["Principled BSDF"].inputs["Metallic"].default_value = 0.7
knob.data.materials[0] = metal("Brushed aluminium", (0.86, 0.86, 0.87), 0.28)
for ob in numbered("Front M3 head"):
    ob.data.materials[0] = steel

screen = D.objects["Display"]  # the screen and its lettering move with the window
for name in ("Now playing", "Alpine Echoes", "Progress"):
    ob = D.objects[name]
    ob.location = (c.LCD_X + ob.location.x - screen.location.x, c.FRONT_T - 0.7, c.CTRL_Z + ob.location.z - screen.location.z)
screen.location = (c.LCD_X, c.FRONT_T - 0.3, c.CTRL_Z)
shift = c.CARD_X - D.objects["Playing card"].location.x
for name in ("Playing card", "ALPINE", "ECHOES"):  # the card in the slot and its print
    D.objects[name].location.x += shift

cam = D.objects["Camera"]
cam.location = (325.0 + (c.W - 188.0) / 2, -390.0, 290.0)  # the original camera, shifted to the new width
cam.data.ortho_scale = c.W + 97

scene = bpy.context.scene
scene.render.filepath = os.environ.get("RENDER_OUT", str(HERE / "NFC-Player-Render.png"))  # RENDER_OUT renders a trial elsewhere
scene.cycles.samples = 64
scene.cycles.use_denoising = True
if "RENDER_OUT" not in os.environ:  # a trial leaves the scene as it was
    bpy.ops.wm.save_as_mainfile(filepath=str(HERE / "NFC-Player-Render.blend"), compress=True)  # the wood grain makes it large
bpy.ops.render.render(write_still=True)
print("Rendered", scene.render.filepath)
