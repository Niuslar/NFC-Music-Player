"""Renders the case from the meshes build.py made. Run build.py first.

    /Applications/Blender.app/Contents/MacOS/Blender -b NFC-Player-Render.blend -P render.py

It reuses the scene's camera, lights and materials, swaps in the freshly built printed parts,
brass and keycaps, and moves the knob, screws and cards to match case.py. Run wood.py too
to render the wood-grain chassis and front; otherwise the plain ones are shown, still in wood.
The knob, screw heads, feet, screen and cards are stand-ins for bought parts.
"""

import sys
from pathlib import Path

import bpy
from mathutils import Matrix

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import case as c  # noqa: E402
import keycaps  # noqa: E402
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


# Chassis, front and lid in sanded wood-fill PLA with the grain from wood.py (when it has been
# run); the rear stays charcoal.
WOOD = {"chassis": ("chassis-wood", [(1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0)]), "front": ("front-wood", c.FRONT_M), "lid": (None, None)}
for ob in dst.objects:
    bpy.context.scene.collection.objects.link(ob)
    if ob.name in WOOD and WOOD[ob.name][0] and (HERE / "STL" / f"{WOOD[ob.name][0]}.stl").exists():
        old, ob.data = ob.data, stl_mesh(HERE / "STL" / f"{WOOD[ob.name][0]}.stl", WOOD[ob.name][1])
        D.meshes.remove(old)
    ob.data.materials.clear()
    mat = "Brushed brass" if ob.name == "brass" else "Printed charcoal"
    ob.data.materials.append(wood_material() if ob.name in WOOD else D.materials[mat])
    for poly in ob.data.polygons:
        poly.use_smooth = False


def numbered(base):
    return [D.objects[n] for n in sorted(D.objects.keys()) if n == base or n.startswith(base + ".")]


# The keycaps from keycaps.py, turned from their print orientation to sit on the switches:
# underside 3 mm (the travel) in front of the switch housing, which stands 2 mm proud of the brass.
CAP_TO_CASE = [(-1, 0, 0, 0), (0, 0, 1, -5.0 - keycaps.CAP_T), (0, 1, 0, 0)]
for ob, k, name in zip(numbered("Choc keycap"), c.KEYS_X, keycaps.SYMBOLS):
    old, ob.data = ob.data, stl_mesh(HERE / "STL" / f"keycap-{name}.stl", CAP_TO_CASE)
    if old.users == 0:
        D.meshes.remove(old)
    ob.data.materials.append(D.materials["Printed charcoal"])
    ob.location, ob.rotation_euler, ob.scale = (k, 0.0, c.CTRL_Z), (0, 0, 0), (1, 1, 1)
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


# The power key: a black 12 mm button with a lit ring, a stand-in made here each time.
for name in ("Power key", "Power key ring", "Power key cap"):
    if name in D.objects:
        D.objects.remove(D.objects[name])
for name, r, y0, y1, mat in (
    ("Power key", 7.5, -2.6, 0.0, material("Black plastic", (0.015, 0.015, 0.016), 0.35)),
    ("Power key ring", 6.3, -2.75, -2.6, material("Power light", (1.0, 0.62, 0.25), 0.4, 6.0)),
    ("Power key cap", 5.3, -2.85, -2.6, material("Black plastic", (0.015, 0.015, 0.016), 0.35)),
):
    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=r, depth=y1 - y0, location=(c.POWER_X, (y0 + y1) / 2, c.CTRL_Z), rotation=(1.5707963, 0, 0))
    ob = bpy.context.active_object
    ob.name = name
    ob.data.materials.append(mat)

knob = D.objects["Volume knob"]
knob.location = (c.KNOB_X, -9.0, c.CTRL_Z)
knob.scale = (c.KNOB_D / 26.0, c.KNOB_D / 26.0, 1.0)
for name, d, y in (("Jack surround", 9.0, c.D + 0.5), ("Jack aperture", 3.5, c.D + 1.1)):
    D.objects[name].location = (c.PHONES_X, y, c.PHONES_Z)
    D.objects[name].scale = (d / D.objects[name].dimensions.x * D.objects[name].scale.x,) * 2 + (1.0,)
    D.objects[name].hide_render = not c.REAR_JACK  # otherwise the DAC's own socket is used

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
scene.render.filepath = str(HERE / "NFC-Player-Render.png")
scene.cycles.samples = 64
scene.cycles.use_denoising = True
bpy.ops.wm.save_as_mainfile(filepath=str(HERE / "NFC-Player-Render.blend"), compress=True)  # the wood grain makes it large
bpy.ops.render.render(write_still=True)
print("Rendered", scene.render.filepath)
