"""Renders the case from the meshes build.py made. Run build.py first.

    /Applications/Blender.app/Contents/MacOS/Blender -b NFC-Player-Render.blend -P render.py

It reuses the scene's camera, lights and materials, swaps in the freshly built printed parts
and brass, and moves the knob, keycaps, screws and cards to match case.py.
The knob, keycaps, screw heads, feet, screen and cards are stand-ins for bought parts.
"""

import sys
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import case as c  # noqa: E402

D = bpy.data
OLD = ("Brass panel", "Card guide", "Chassis", "Front support", "Lid", "Rear", "brass", *c.PARTS)
for name in OLD:  # the printed parts from the last render, or from revision 2.1
    if name in D.objects:
        D.objects.remove(D.objects[name])

with D.libraries.load(str(HERE / "parts.blend")) as (src, dst):
    dst.objects = list(src.objects)
for ob in dst.objects:
    bpy.context.scene.collection.objects.link(ob)
    ob.data.materials.clear()
    ob.data.materials.append(D.materials["Brushed brass" if ob.name == "brass" else "Printed charcoal"])
    for poly in ob.data.polygons:
        poly.use_smooth = False


def numbered(base):
    return [D.objects[n] for n in sorted(D.objects.keys()) if n == base or n.startswith(base + ".")]


for ob, k in zip(numbered("Choc keycap"), c.KEYS_X):
    ob.location = (k, -2.0, c.CTRL_Z)
    ob.dimensions = (17.5, 4.0, 16.5)
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
bpy.ops.wm.save_as_mainfile(filepath=str(HERE / "NFC-Player-Render.blend"))
bpy.ops.render.render(write_still=True)
print("Rendered", scene.render.filepath)
