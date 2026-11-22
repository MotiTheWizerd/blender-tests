"""Two builds of the body side by side, to see what a face change did: a snapshot of the build before it
(build/forge/<Title>_<tag>, copied there before the rebuild) on the left, the current build (build/forge/<Title>) on
the right, each with its own maps, the heads framed together.

    blender -b -P compare_faces.py -- <tag of the snapshot> [<tag of the current, default types.json's face>]

Writes build/faces.blend and checks/faces_{front,whole}.png (both) and checks/faces_quarter_<tag>.png (each head alone).
"""
import bpy, os, sys, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from built import import_build, light_and_camera  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:]
types = json.load(open(os.path.join(HERE, "types.json")))
TITLE = types["title"]
BEFORE, NOW = ARGS[0], ARGS[1] if len(ARGS) > 1 else types["face"]
APART = 1.2  # m between the two: their A-pose hands clear of each other
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

bodies = []
for tag, folder, x in ((BEFORE, os.path.join(HERE, "build", "forge", TITLE + "_" + BEFORE), -APART / 2),
                       (NOW, os.path.join(HERE, "build", "forge", TITLE), APART / 2)):
    body = import_build(folder, TITLE, "%s (%s)" % (TITLE, tag))
    P = np.array([body.matrix_world @ v.co for v in body.data.vertices])
    (body.parent or body).location.x += x
    bodies.append((tag, body, P))
    print("%s: %s, %d vertices, %d shape keys, slots %s" % (tag, folder, len(P), len(body.data.shape_keys.key_blocks) - 1,
                                                           [m.name for m in body.data.materials]), flush=True)
ground = min(P[:, 2].min() for _, _, P in bodies)
height = max(P[:, 2].max() for _, _, P in bodies) - ground
head_z = ground + height * 0.91

cam = light_and_camera(scene)
CHECKS = os.path.join(HERE, "checks")


def shoot(name, loc, turn, lens):
    """A picture from loc, the camera turned by `turn` degrees about z from looking along +y (a camera at (sin a,
    -cos a) of its subject looks at it turned by a)."""
    cam.location = loc
    cam.rotation_euler = (np.radians(90), 0, np.radians(turn))
    cam.data.lens = lens
    scene.render.filepath = os.path.join(CHECKS, "faces_%s.png" % name)
    bpy.ops.render.render(write_still=True)


FRONT = ((0.0, -1.9, head_z), 0, 40)  # both heads, APART apart, in one frame with a head's width to spare each side
shoot("front", *FRONT)
shoot("whole", (0.0, -5.2, ground + height * 0.52), 0, 50)
for tag, body, P in bodies:
    x = (body.parent or body).location.x
    a = 35.0
    shoot("quarter_" + tag, (x + 0.9 * np.sin(np.radians(a)), -0.9 * np.cos(np.radians(a)), head_z), a, 85)
cam.location, cam.rotation_euler, cam.data.lens = FRONT[0], (np.radians(90), 0, 0), FRONT[2]
path = os.path.join(HERE, "build", "faces.blend")
bpy.ops.wm.save_as_mainfile(filepath=path)
print("FACES saved", path, "left %s, right %s" % (BEFORE, NOW), flush=True)
