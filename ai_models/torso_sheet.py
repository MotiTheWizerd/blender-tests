"""A body's torso sheet for Iris: the body as Forge wears it (its Body piece with the torso laid on, its hands and its own
head), drawn flat (its own colour, no shading, no shadow) on plain grey, framed as the torso Tripo makes for torso.py:
from the jaw to the upper thighs, the arms to the wrists. Iris edits it into another body type ("the same woman,
more muscular"), Tripo makes that torso, and torso.py lays it on as it does her own. Editing her own picture, not
writing a new one, keeps her pose and proportions (s1014: a text prompt made another woman every time).

    blender -b --factory-startup -P torso_sheet.py -- body_warrior_f

Reads pieces.py's build/forge/<Body>/<Body>.fbx, its Heads/<Body>.fbx and the maps beside them. Writes
<body>/build/sheet/<Body>_torso_<view>.png (SIZE square, PNG, what Iris gets) and <body>/checks/torso_sheet_<view>.jpg
(small, the record).
"""
import os, re, sys
import bpy
from mathutils import Vector

ARGS = sys.argv[sys.argv.index("--") + 1:]
BODY = ARGS[0]
WHOLE = "--whole" in ARGS     # the whole body, crown to floor (<Body>_body_<view>.png): a body type's arms and legs too
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from place import Creature, pictures_as_jpeg

B = Creature(BODY)
SIZE = 3000           # the picture's side (pixels): Iris edits at full detail
WHOLE_MARGIN = 0.03   # --whole: the picture's margin over her crown and under her feet, a share of her height
TOP_OVER_CHIN = 0.03  # metres above the body's chin the picture starts: the jaw shows, so the neck's end is plain
BOTTOM = 0.36         # the picture's lower edge, as a share of her height: the upper thighs
BACKGROUND = (0.5, 0.5, 0.5)   # plain mid grey: not skin, not hair, not the white a model paints with
OUT = B.build("sheet")
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
folder = B.build("forge", B.title)
for path in (os.path.join(folder, f"{B.title}.fbx"), os.path.join(folder, "Heads", f"{B.title}.fbx")):
    bpy.ops.import_scene.fbx(filepath=os.path.abspath(path))
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
if not meshes:
    raise SystemExit(f"no mesh in {folder}")
# Her own shape: every body type's shape key off (the FBX carries them, and read back they came on, all at once).
for ob in meshes:
    if ob.data.shape_keys:
        for key in ob.data.shape_keys.key_blocks:
            key.value = 0.0


def textured(name):
    """A material drawing <name>_Color.png, found in the body's folder or its Heads/ (a head draws its own maps)."""
    name = re.sub(r"\.\d+$", "", name)     # a second import names its copy BodyWarriorF.001
    for where in (folder, os.path.join(folder, "Heads")):
        file = os.path.join(where, f"{name}_Color.png")
        if os.path.exists(file):
            break
    else:
        raise SystemExit(f"no {name}_Color.png in {folder}")
    material = bpy.data.materials.new(f"{name}_sheet")
    material.use_nodes = True
    texture = material.node_tree.nodes.new("ShaderNodeTexImage")
    texture.image = bpy.data.images.load(file, check_existing=True)
    bsdf = material.node_tree.nodes["Principled BSDF"]
    material.node_tree.links.new(texture.outputs["Color"], bsdf.inputs["Base Color"])
    return material


wired = {}
for ob in meshes:
    for slot in ob.material_slots:
        if slot.material is None:
            continue
        key = re.sub(r"\.\d+$", "", slot.material.name)
        slot.material = wired.setdefault(key, textured(key))

# Her height and her chin (pieces.py's report has the body's chin; else 86% of her height, where a chin stands).
depsgraph = bpy.context.evaluated_depsgraph_get()
points = [o.matrix_world @ Vector(c) for o in meshes for c in o.evaluated_get(depsgraph).bound_box]
floor = min(p.z for p in points)
height = max(p.z for p in points) - floor
report = os.path.join(B.root, "checks", "pieces.json")
chin = floor + 0.86 * height
if os.path.exists(report):
    import json
    heads = json.load(open(report)).get("heads", {})
    chins = [h["body_chin_z"] for h in heads.values() if "body_chin_z" in h]
    if chins:
        chin = chins[0]
top, bottom = chin + TOP_OVER_CHIN, floor + BOTTOM * height
if WHOLE:
    top, bottom = floor + height * (1 + WHOLE_MARGIN), floor - height * WHOLE_MARGIN
side = top - bottom
SHEET = "body" if WHOLE else "torso"
centre = Vector((0.0, 0.0, (top + bottom) / 2))
# The body's frame: front -Y, up Z (pieces.py's).
VIEWS = {"front": Vector((0, 1, 0)), "side": Vector((-1, 0, 0)), "back": Vector((0, -1, 0)),
         "three_quarter": Vector((-1, 1, 0)).normalized()}

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
cam_data.ortho_scale = side
cam = bpy.data.objects.new("Sheet", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam


def shoot(toward, path):
    cam.location = centre - toward * 3.0
    cam.rotation_euler = (-toward).to_track_quat("Z", "Y").to_euler()
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


scene.render.image_settings.file_format, scene.render.image_settings.color_mode = "PNG", "RGB"
for view, toward in VIEWS.items():
    shoot(toward, os.path.join(OUT, f"{B.title}_{SHEET}_{view}.png"))

# The record: the same, small.
scene.render.resolution_percentage = 25
pictures_as_jpeg(scene)
for view, toward in VIEWS.items():
    shoot(toward, B.picture(f"{SHEET}_sheet_{view}"))

print(f"{SHEET.upper()} SHEET {B.title}: {bottom:.3f} to {top:.3f} m ({side * 100:.0f} cm square), {len(VIEWS)} views of {SIZE} px in {OUT}")
