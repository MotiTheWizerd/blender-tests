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
from built import import_build, light_and_camera  # noqa: E402

types = json.load(open(os.path.join(HERE, "types.json")))
TITLE = types["title"]
OUT = os.path.join(HERE, "build", "forge", TITLE)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
body = import_build(OUT, TITLE, "%s (built)" % TITLE)
P = np.array([body.matrix_world @ v.co for v in body.data.vertices])
ground, height = P[:, 2].min(), P[:, 2].max() - P[:, 2].min()

# the painted Tripo body beside her, at her height, its own paint on
skin = next((t for t in types["types"] if t["name"] == types.get("skin")), None)
if skin:
    tripo = import_tripo(os.path.join(HERE, os.path.expanduser(types["sources"]), skin["source"]), "Tripo %s (the skin's body)" % skin["name"])
    T = np.array([v.co for v in tripo.data.vertices])
    T = (T - [0, 0, T[:, 2].min()]) * (height / (T[:, 2].max() - T[:, 2].min())) + [0, 0, ground]
    T[:, :2] -= T[:, :2].mean(0) - P[:, :2].mean(0)
    tripo.data.vertices.foreach_set("co", T.ravel()); tripo.data.update()
    tripo.location.x = 1.0
    for p in tripo.data.polygons:
        p.use_smooth = True

cam = light_and_camera(scene)
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
