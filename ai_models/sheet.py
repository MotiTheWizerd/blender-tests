"""A head's sheet for Iris: a body's face editor head as Forge wears it, drawn flat (its own colour, no shading, no
shadow) on plain grey, from the front, the side and the back, each a square picture with room round the head for what
Iris will add (a hair, a helmet, a beard), so Tripo can make that thing on HER head and the piece then fits her skull.

    blender -b --factory-startup -P sheet.py -- body_warrior_f [head_warrior_f]

Reads the body's built heads (pieces.py's build/forge/<Body>/Heads/<Head>.fbx and <Head>_Color.png; the head given, else
the body's first face editor head). Writes <head>/build/sheet/<Head>_<view>.png (SIZE square, PNG, what Iris gets) and
<head>/checks/sheet_<view>.jpg (small, the record).
"""
import os, sys
import bpy
from mathutils import Vector

ARGS = sys.argv[sys.argv.index("--") + 1:]
BODY = ARGS[0]
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from place import Creature, pictures_as_jpeg

B = Creature(BODY)
HEAD = ARGS[1] if len(ARGS) > 1 else B.spec["heads"][0]
H = Creature(HEAD)
TITLE = next(iter(os.listdir(H.build("forge"))))   # the head's Forge name is head.py's export folder (head_warrior_f: WarriorF)
SIZE = 3000           # the picture's side (pixels): Iris edits at full detail
ROOM = 1.9            # the picture's side in heads: the head takes about half, the rest is for what is added
BACKGROUND = (0.5, 0.5, 0.5)   # plain mid grey: not skin, not hair, not the white a model paints with
OUT = H.build("sheet")
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
path = os.path.join(B.build("forge", B.title), "Heads", f"{TITLE}.fbx")
bpy.ops.import_scene.fbx(filepath=os.path.abspath(path))
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
if not meshes:
    raise SystemExit(f"no mesh in {path}")


def textured(name):
    """A material drawing <name>_Color.png: the head's own (Heads/), else the body's (its collar wears the body's)."""
    for folder in (os.path.dirname(path), os.path.dirname(os.path.dirname(path))):
        file = os.path.join(folder, f"{name}_Color.png")
        if os.path.exists(file):
            break
    else:
        raise SystemExit(f"no {name}_Color.png beside {path}")
    material = bpy.data.materials.new(f"{name}_sheet")
    material.use_nodes = True
    texture = material.node_tree.nodes.new("ShaderNodeTexImage")
    texture.image = bpy.data.images.load(file)
    bsdf = material.node_tree.nodes["Principled BSDF"]
    material.node_tree.links.new(texture.outputs["Color"], bsdf.inputs["Base Color"])
    return material


# The FBX names its materials and maps; the maps are wired here (the import finds the eyes' alone).
for ob in meshes:
    for slot in ob.material_slots:
        slot.material = textured(slot.material.name)

# The head's bounds as it stands, and its front: where its eyes are (an "Eyes" material), else -Y.
depsgraph = bpy.context.evaluated_depsgraph_get()
points = [o.matrix_world @ Vector(c) for o in meshes for c in o.evaluated_get(depsgraph).bound_box]
lo = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
hi = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
centre = (lo + hi) / 2
height = hi.z - lo.z
forward = Vector((0, -1, 0))
for ob in meshes:
    eyes = [i for i, s in enumerate(ob.material_slots) if s.material.name.startswith(TITLE + "Eyes")]
    if eyes:
        me = ob.data
        eye_centre = sum((ob.matrix_world @ me.vertices[v].co for p in me.polygons if p.material_index in eyes
                          for v in p.vertices), Vector()) / max(1, sum(len(p.vertices) for p in me.polygons if p.material_index in eyes))
        forward = Vector((eye_centre.x - centre.x, eye_centre.y - centre.y, 0)).normalized()
right = forward.cross(Vector((0, 0, 1)))
# Each view: the way the camera looks (at the face from in front of it, and so on).
VIEWS = {"front": -forward, "side": -right, "back": forward, "three_quarter": -(forward + right).normalized()}

# Flat: the colour map as it is, through the Workbench, nothing lit or shaded.
scene = bpy.context.scene
scene.render.engine = "BLENDER_WORKBENCH"
shading = scene.display.shading
shading.light = "FLAT"
shading.color_type = "TEXTURE"
shading.show_backface_culling = False
shading.show_shadows = False
shading.show_cavity = False
shading.show_object_outline = False
scene.display.render_aa = "16"
scene.view_settings.view_transform = "Standard"
scene.render.film_transparent = False
world = bpy.data.worlds.new("Sheet")
world.color = BACKGROUND
scene.world = world
scene.render.resolution_x = scene.render.resolution_y = SIZE
scene.render.resolution_percentage = 100

cam_data = bpy.data.cameras.new("Sheet")
cam_data.type = "ORTHO"
cam_data.ortho_scale = height * ROOM
cam = bpy.data.objects.new("Sheet", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam

for view, toward in VIEWS.items():
    toward = toward.normalized()
    cam.location = centre - toward * 3.0
    cam.rotation_euler = (-toward).to_track_quat("Z", "Y").to_euler()
    scene.render.image_settings.file_format, scene.render.image_settings.color_mode = "PNG", "RGB"
    scene.render.filepath = os.path.join(OUT, f"{TITLE}_{view}.png")
    bpy.ops.render.render(write_still=True)

# The record: the same, small.
scene.render.resolution_percentage = 25
pictures_as_jpeg(scene)
for view, toward in VIEWS.items():
    toward = toward.normalized()
    cam.location = centre - toward * 3.0
    cam.rotation_euler = (-toward).to_track_quat("Z", "Y").to_euler()
    scene.render.filepath = H.picture(f"sheet_{view}")
    bpy.ops.render.render(write_still=True)

print(f"SHEET {TITLE}: head {height * 100:.1f} cm tall, {len(VIEWS)} views of {SIZE} px in {OUT}")
