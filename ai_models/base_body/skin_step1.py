"""Step 1 of her skin: MPFB's own skin (a MakeHuman system asset, CC0, 4K on her UV) on her, through MPFB's skin shader,
beside the body as built for Forge (the face bake on its own slot), to look at in Blender.

    blender -b -P skin_step1.py -- <skin name, e.g. young_caucasian_female>

Writes build/skin_step1.blend and checks/skin_step1_{face,whole}.png.
"""
import bpy, json, os, sys
import numpy as np
from bl_ext.blender_org.mpfb.services.humanservice import HumanService
from bl_ext.blender_org.mpfb.services.locationservice import LocationService

ARGS = sys.argv[sys.argv.index("--") + 1:]
SKIN = ARGS[0]
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from her import create, settle  # noqa: E402

TYPES = json.load(open(os.path.join(HERE, "types.json")))
BASE, FACE, TITLE = TYPES["base"], TYPES["face"], TYPES["title"]
OUT = os.path.join(HERE, "build", "forge", TITLE)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
fit = json.load(open(os.path.join(HERE, "checks", "fit_%s.json" % BASE)))["values"]
face = json.load(open(os.path.join(HERE, "checks", "face_%s.json" % FACE)))

# her, MPFB's skin on
base, rig = create(fit, face)
settle(base, rig)
base.name = "Her: MPFB skin " + SKIN
mhmat = os.path.join(LocationService.get_user_data("skins"), SKIN, SKIN + ".mhmat")
assert os.path.exists(mhmat), mhmat
HumanService.set_character_skin(mhmat, base, skin_type="ENHANCED_SSS")
for p in base.data.polygons:
    p.use_smooth = True
print("SKIN material:", [m.name for m in base.data.materials], "from", os.path.basename(mhmat), flush=True)

# the body as built, the face bake on its own slot, beside her
before = set(scene.objects)
bpy.ops.import_scene.fbx(filepath=os.path.join(OUT, TITLE + ".fbx"))
built = [o for o in scene.objects if o not in before and o.type == "MESH"][0]
built.name = "Built for Forge (face bake)"
for m in built.data.materials:
    m.use_nodes = True
    nodes, links = m.node_tree.nodes, m.node_tree.links
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.55
    c = nodes.new("ShaderNodeTexImage"); c.image = bpy.data.images.load(os.path.join(OUT, m.name + "_Color.png")); c.location = (-500, 300)
    links.new(c.outputs["Color"], bsdf.inputs["Base Color"])
    npath = os.path.join(OUT, m.name + "_Normal.png")
    if os.path.exists(npath):
        n = nodes.new("ShaderNodeTexImage"); n.image = bpy.data.images.load(npath); n.image.colorspace_settings.name = "Non-Color"; n.location = (-500, -100)
        nm = nodes.new("ShaderNodeNormalMap"); nm.location = (-200, -100)
        links.new(n.outputs["Color"], nm.inputs["Color"]); links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
for o in scene.objects:
    if o not in before and o.type == "ARMATURE":
        o.location.x += 0.7
for p in built.data.polygons:
    p.use_smooth = True

# light and cameras
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); sun.data.energy = 3.0
sun.rotation_euler = (np.radians(60), 0, np.radians(-30)); scene.collection.objects.link(sun)
world = bpy.data.worlds.new("w"); world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.35, 0.35, 0.35, 1); scene.world = world
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); cam.data.lens = 50
scene.collection.objects.link(cam); scene.camera = cam
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x, scene.render.resolution_y = 1600, 1000
for area in bpy.context.screen.areas:
    if area.type == "VIEW_3D":
        for space in area.spaces:
            if space.type == "VIEW_3D":
                space.shading.type = "MATERIAL"
for name, loc in (("face", (0.35, -1.9, 1.45)), ("whole", (0.35, -4.8, 0.85))):
    cam.location = loc
    cam.rotation_euler = (np.radians(90), 0, 0)
    scene.render.filepath = os.path.join(HERE, "checks", "skin_step1_%s.png" % name)
    bpy.ops.render.render(write_still=True)
cam.location = (0.35, -1.9, 1.45)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "build", "skin_step1.blend"))
print("SKIN saved", flush=True)
