"""Her head's sheet for Iris, as sheet.py draws a warrior's: the base body as built for Forge (build/forge/<Title>), her
own face (types.json "face", the mesh's basis), drawn flat (its own colour, no shading, no shadow) on plain grey, from
the front, the side, the back and three quarters, each a square picture framed on her head with room round it for what
Iris adds (a part of a hair), so Tripo makes that part on HER skull.

    blender -b --factory-startup -P sheet_base.py

Also measures how far each shape key (her other faces, the body types) moves her scalp, the skin above her brows: a
part drawn once on this head is rigid on the Head bone, so a key that moves the scalp is a key the part won't follow.
Writes build/sheet/<Title>_<view>.png (3000 px, what Iris gets) and checks/sheet_<view>.jpg (small, the record).
"""
import json, os, sys
import bpy
import numpy as np
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = json.load(open(os.path.join(HERE, "types.json")))
TITLE = SPEC["title"]
FOLDER = os.path.join(HERE, "build", "forge", TITLE)
OUT = os.path.join(HERE, "build", "sheet")
CHECKS = os.path.join(HERE, "checks")
SIZE = 3000           # the picture's side (pixels): Iris edits at full detail
ROOM = 1.9            # the picture's side in heads: the head takes about half, the rest is for what is added
BACKGROUND = (0.5, 0.5, 0.5)   # plain mid grey: not skin, not hair, not the white a model paints with
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=os.path.join(FOLDER, TITLE + ".fbx"))
body = next(o for o in bpy.data.objects if o.type == "MESH")
for o in bpy.data.objects:
    if o.type == "ARMATURE":
        o.hide_render = True

# Each slot draws its own colour map (the slot is the material's name as exported).
for slot in body.material_slots:
    name = slot.material.name.split(".")[0]
    material = bpy.data.materials.new(f"{name}_sheet")
    material.use_nodes = True
    texture = material.node_tree.nodes.new("ShaderNodeTexImage")
    texture.image = bpy.data.images.load(os.path.join(FOLDER, f"{name}_Color.png"))
    material.node_tree.links.new(texture.outputs["Color"], material.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
    material.node_tree.nodes.active = texture
    slot.material = material

# Her head: the eyes (the "Eyes" slot) and the top of her; the chin as far under the eyes as the crown is over them.
me = body.data
world = body.matrix_world
co = np.array([tuple(world @ v.co) for v in me.vertices])
eye_slots = {i for i, s in enumerate(body.material_slots) if "Eyes" in s.material.name}
eye_verts = sorted({v for p in me.polygons if p.material_index in eye_slots for v in p.vertices})
eye = co[eye_verts].mean(axis=0)
top = co[:, 2].max()
chin = eye[2] - (top - eye[2]) * 1.05
near = np.abs(co[:, 0] - eye[0]) < (top - eye[2]) * 1.2
head = co[(co[:, 2] > chin) & near]
lo, hi = head.min(axis=0), head.max(axis=0)
centre = Vector(((lo + hi) / 2).tolist())
height = float(hi[2] - lo[2])
forward = Vector((eye[0] - centre.x, eye[1] - centre.y, 0)).normalized()
right = forward.cross(Vector((0, 0, 1)))
VIEWS = {"front": -forward, "side": -right, "back": forward, "three_quarter": -(forward + right).normalized()}

# How far each shape key moves her scalp: the skin over her brows (2 cm above the eyes and up), the eyes left out.
basis = np.array([tuple(v.co) for v in me.vertices])
scalp = (co[:, 2] > eye[2] + 0.02) & near
scalp[eye_verts] = False
moves = {}
for key in (me.shape_keys.key_blocks[1:] if me.shape_keys else []):
    shaped = np.array([tuple(p.co) for p in key.data])
    d = np.linalg.norm((shaped - basis)[scalp], axis=1) * world.to_scale()[0]
    moves[key.name] = (float(np.median(d)) * 1000, float(np.percentile(d, 95)) * 1000, float(d.max()) * 1000)
print(f"SCALP {int(scalp.sum())} verts above the brows; per shape key, mm moved (median / p95 / max):")
for name, (med, p95, mx) in sorted(moves.items(), key=lambda kv: -kv[1][2]):
    if mx > 0.5:
        print(f"  {name:28s} {med:6.1f} {p95:6.1f} {mx:6.1f}")

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
sky = bpy.data.worlds.new("Sheet")
sky.color = BACKGROUND
scene.world = sky
scene.render.resolution_x = scene.render.resolution_y = SIZE
scene.render.resolution_percentage = 100

cam_data = bpy.data.cameras.new("Sheet")
cam_data.type = "ORTHO"
cam_data.ortho_scale = height * ROOM
cam = bpy.data.objects.new("Sheet", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam


def shoot(path):
    for view, toward in VIEWS.items():
        toward = toward.normalized()
        cam.location = centre - toward * 3.0
        cam.rotation_euler = (-toward).to_track_quat("Z", "Y").to_euler()
        scene.render.filepath = path(view)
        bpy.ops.render.render(write_still=True)


scene.render.image_settings.file_format, scene.render.image_settings.color_mode = "PNG", "RGB"
shoot(lambda view: os.path.join(OUT, f"{TITLE}_{view}.png"))
scene.render.resolution_percentage = 25
scene.render.image_settings.file_format = "JPEG"
shoot(lambda view: os.path.join(CHECKS, f"sheet_{view}.jpg"))
print(f"SHEET {TITLE} ({SPEC['face']}'s face): head {height * 100:.1f} cm tall, {len(VIEWS)} views of {SIZE} px in {OUT}")
