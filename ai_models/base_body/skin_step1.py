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
from her import create, settle, Head  # noqa: E402

TYPES = json.load(open(os.path.join(HERE, "types.json")))
BASE, FACE, TITLE = TYPES["base"], TYPES["face"], TYPES["title"]
PORE_TILES = 36  # the pore tile repeats this often across her UV: 48 cells a tile, 1 UV about 1.8 m, so a cell is about 1 mm
PORE_STRENGTH, PORE_DEPTH = 0.35, 0.0003  # the bump's strength and its height (m)
# roughness by region (Principled: 0 a mirror, 1 matte), and how much rougher a pore groove is than its plateau
ROUGH = {"body": 0.6, "face": 0.52, "nose": 0.4, "forehead": 0.44, "lips": 0.38, "groove": 0.2}
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

# roughness by region, a vertex attribute: skin shines unevenly (the nose, forehead and lips most, the cheeks less, the
# body least); smoothed over the mesh so no region has an edge
me_b = built.data
P = np.array([built.matrix_world @ v.co for v in me_b.vertices])
head_b = Head(built, me_b)
rough = np.full(len(P), ROUGH["body"])
rough[head_b.skin] = ROUGH["face"]
marks = {k: np.array(v["her"]) for k, v in face["landmarks"].items()}
nose, eyes_z = marks["nose"], (marks["eye_l"][2] + marks["eye_r"][2]) / 2
near_nose = np.linalg.norm(P - nose, axis=1) < 0.035
forehead = (P[:, 2] > eyes_z + 0.025) & (np.abs(P[:, 0]) < 0.045) & (P[:, 1] < nose[1] + 0.06)
lips = np.linalg.norm(P[:, None, :] - P[head_b.mouth][None, :, :], axis=2).min(1) < 0.012
rough[near_nose] = ROUGH["nose"]
rough[forehead] = ROUGH["forehead"]
rough[lips] = ROUGH["lips"]
E = np.empty(len(me_b.edges) * 2, dtype=np.int64)
me_b.edges.foreach_get("vertices", E)
E = E.reshape(-1, 2)
for _ in range(6):  # each vertex toward the mean of its neighbours
    s = np.zeros(len(P)); n = np.zeros(len(P))
    np.add.at(s, E[:, 0], rough[E[:, 1]]); np.add.at(s, E[:, 1], rough[E[:, 0]])
    np.add.at(n, E[:, 0], 1); np.add.at(n, E[:, 1], 1)
    rough = np.where(n > 0, 0.5 * rough + 0.5 * s / np.maximum(n, 1), rough)
attr = me_b.color_attributes.new("roughness", "FLOAT_COLOR", "POINT")
attr.data.foreach_set("color", np.repeat(rough, 4).astype(np.float32).ravel())
print("roughness: nose %d, forehead %d, lips %d vertices; %.2f to %.2f" % (near_nose.sum(), forehead.sum(), lips.sum(), rough.min(), rough.max()), flush=True)

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
        links.new(n.outputs["Color"], nm.inputs["Color"])
        # the pores: the tileable height tile (skin_pores.py) as a bump over the baked normals, PORE_TILES across her
        # UV (the face's square holds its island 1.465 times larger, so fewer tiles there keep the pores one size)
        pores = os.path.join(HERE, "build", "skin_pores_height.png")
        if os.path.exists(pores) and m.name.endswith(("Face", TITLE)):
            tiles = PORE_TILES / (face["uv"]["scale"] if m.name.endswith("Face") else 1.0)
            coord = nodes.new("ShaderNodeTexCoord"); coord.location = (-1100, -400)
            mapping = nodes.new("ShaderNodeMapping"); mapping.location = (-900, -400)
            mapping.inputs["Scale"].default_value = (tiles, tiles, 1.0)
            links.new(coord.outputs["UV"], mapping.inputs["Vector"])
            h = nodes.new("ShaderNodeTexImage"); h.image = bpy.data.images.load(pores); h.image.colorspace_settings.name = "Non-Color"; h.location = (-700, -400)
            links.new(mapping.outputs["Vector"], h.inputs["Vector"])
            bump = nodes.new("ShaderNodeBump"); bump.location = (0, -200)
            bump.inputs["Strength"].default_value = PORE_STRENGTH
            bump.inputs["Distance"].default_value = PORE_DEPTH
            links.new(h.outputs["Color"], bump.inputs["Height"])
            links.new(nm.outputs["Normal"], bump.inputs["Normal"])
            links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
            # roughness: the region's, the pore tile's grooves rougher than its plateaus
            ra = nodes.new("ShaderNodeAttribute"); ra.attribute_name = "roughness"; ra.location = (-700, -700)
            groove = nodes.new("ShaderNodeMath"); groove.operation = "MULTIPLY_ADD"; groove.location = (-400, -700)
            groove.inputs[1].default_value = -ROUGH["groove"]  # height 0.5 flat: a groove (low) adds roughness
            groove.inputs[2].default_value = 0.5 * ROUGH["groove"]
            links.new(h.outputs["Color"], groove.inputs[0])
            total = nodes.new("ShaderNodeMath"); total.operation = "ADD"; total.location = (-200, -700)
            links.new(ra.outputs["Fac"], total.inputs[0])
            links.new(groove.outputs["Value"], total.inputs[1])
            links.new(total.outputs["Value"], bsdf.inputs["Roughness"])
        else:
            links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
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
for name, loc in (("face", (0.35, -1.9, 1.45)), ("whole", (0.35, -4.8, 0.85)), ("closeup", (0.78, -0.42, 1.47))):
    cam.location = loc
    cam.rotation_euler = (np.radians(90), 0, 0)
    cam.data.lens = 85 if name == "closeup" else 50
    scene.render.filepath = os.path.join(HERE, "checks", "skin_step1_%s.png" % name)
    bpy.ops.render.render(write_still=True)
cam.location = (0.35, -1.9, 1.45)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "build", "skin_step1.blend"))
print("SKIN saved", flush=True)
