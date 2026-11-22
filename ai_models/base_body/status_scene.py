"""The body as built for Forge (build/forge/<Title>: the FBX, its colour, normal and smoothness maps) beside the painted
Tripo body her skin came from, at her height, to look at in Blender: the comparison that decides.

    blender -b -P status_scene.py

Writes build/status.blend and checks/status_{whole,torso,face}.png.
"""
import bpy, os, sys, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from pose import import_tripo  # noqa: E402

types = json.load(open(os.path.join(HERE, "types.json")))
TITLE = types["title"]
OUT = os.path.join(HERE, "build", "forge", TITLE)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
bpy.ops.import_scene.fbx(filepath=os.path.join(OUT, TITLE + ".fbx"))
body = next(o for o in scene.objects if o.type == "MESH")
body.name = "%s (built)" % TITLE
for m in body.data.materials:
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
    spath = os.path.join(OUT, m.name + "_MetallicSmoothness.png")
    if os.path.exists(spath):  # smoothness in the alpha, as URP reads it: roughness is 1 - alpha
        s = nodes.new("ShaderNodeTexImage"); s.image = bpy.data.images.load(spath); s.image.colorspace_settings.name = "Non-Color"; s.location = (-500, -500)
        inv = nodes.new("ShaderNodeMath"); inv.operation = "SUBTRACT"; inv.inputs[0].default_value = 1.0; inv.location = (-200, -500)
        links.new(s.outputs["Alpha"], inv.inputs[1]); links.new(inv.outputs["Value"], bsdf.inputs["Roughness"])
P = np.array([body.matrix_world @ v.co for v in body.data.vertices])
ground, height = P[:, 2].min(), P[:, 2].max() - P[:, 2].min()

# the painted Tripo body beside her, at her height, its own paint on
skin = next((s for s in types.get("skins", []) if s["name"] == types.get("skin")), None)
if skin:
    tripo = import_tripo(os.path.join(HERE, os.path.expanduser(types["sources"]), skin["source"]), "Tripo %s (the skin's body)" % skin["name"])
    T = np.array([v.co for v in tripo.data.vertices])
    T = (T - [0, 0, T[:, 2].min()]) * (height / (T[:, 2].max() - T[:, 2].min())) + [0, 0, ground]
    T[:, :2] -= T[:, :2].mean(0) - P[:, :2].mean(0)
    tripo.data.vertices.foreach_set("co", T.ravel()); tripo.data.update()
    tripo.location.x = 1.0
    for p in tripo.data.polygons:
        p.use_smooth = True
for p in body.data.polygons:
    p.use_smooth = True
for o in scene.objects:
    if o.type == "ARMATURE":
        o.hide_viewport = o.hide_render = True

# light, world, camera
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
for name, loc, lens in (("whole", (0.5, -4.6, ground + height * 0.52), 50), ("torso", (0.5, -2.2, ground + height * 0.68), 85), ("face", (0.0, -1.0, ground + height * 0.91), 85)):
    cam.location = loc
    cam.rotation_euler = (np.radians(90), 0, 0)
    cam.data.lens = lens
    scene.render.filepath = os.path.join(HERE, "checks", "status_%s.png" % name)
    bpy.ops.render.render(write_still=True)
cam.location = (0.5, -2.2, ground + height * 0.68)
path = os.path.join(HERE, "build", "status.blend")
bpy.ops.wm.save_as_mainfile(filepath=path)
print("STATUS saved", path, "shape keys:", len(body.data.shape_keys.key_blocks) - 1, "slots:", [m.name for m in body.data.materials])
