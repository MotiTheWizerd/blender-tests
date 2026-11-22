"""How big her head is against her body, beside the Tripo bodies' own heads.

    blender -b -P probe_head_size.py

Each body (MPFB at its defaults; at the base type's fitted sliders; at those and the face's; each Tripo body in
types.json) is measured the same way, standing HEIGHT tall as fit_macros measures them (face.profile's chin finder
works in metres): its head's chin to crown, width and depth, the chin from face.profile over everything above NECK
of the height, the width and depth the widest and deepest the skull is above SKULL of the head's height from the
chin (over the ears); and "heads", the height over the head. Writes checks/head_size.json and prints the table.
"""
import bpy, json, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
from her import create, settle, body_of  # noqa: E402
from face import profile  # noqa: E402

TYPES = json.load(open(os.path.join(HERE, "types.json")))
SOURCES = os.path.expanduser(TYPES["sources"])
HEIGHT = 1.70
NECK = 0.84  # of the height: the head on its neck, nothing below the collarbones, is above this
SKULL = 0.7  # of the head's height from the chin: above the ears, where the skull is widest and deepest
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def measure(P):
    """Height as given, then chin to crown, skull width and depth (m) of the body stood HEIGHT tall, feet on the
    ground."""
    lo, hi = P.min(0), P.max(0)
    given = hi[2] - lo[2]
    P = (P - [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]]) * (HEIGHT / given)
    lo, hi = P.min(0), P.max(0)
    height = hi[2] - lo[2]
    head = P[P[:, 2] > lo[2] + NECK * height]
    crown, chin_z, nose, chin = profile(head)
    h = crown - chin_z
    skull = head[head[:, 2] > chin_z + SKULL * h]
    return {"height": given, "head": h, "width": skull[:, 0].max() - skull[:, 0].min(),
            "depth": skull[:, 1].max() - skull[:, 1].min(), "chin_z": chin_z - lo[2], "crown_z": crown - lo[2],
            "nose_z": nose[2] - lo[2]}


def her_points(fit, face=None):
    base, rig = create(fit, face)
    me = settle(base, rig)
    P = np.array([base.matrix_world @ v.co for v in me.vertices])
    keep = body_of(base, me)
    bpy.data.objects.remove(base)
    bpy.data.objects.remove(rig)
    return P[keep]


def tripo_points(path):
    before = set(scene.objects)
    if path.endswith(".glb"):
        bpy.ops.import_scene.gltf(filepath=path)
    else:
        bpy.ops.import_scene.fbx(filepath=path)
    new = [o for o in scene.objects if o not in before]
    mesh = [o for o in new if o.type == "MESH"][0]
    bpy.context.view_layer.update()
    P = np.array([mesh.matrix_world @ v.co for v in mesh.data.vertices])
    for o in new:
        bpy.data.objects.remove(o)
    return P


rows = {}
default = {"weight": 0.5, "muscle": 0.5, "proportions": 0.5, "cupsize": 0.5, "firmness": 0.5}
rows["mpfb default"] = measure(her_points(default))
base_fit = json.load(open(os.path.join(HERE, "checks", "fit_%s.json" % TYPES["base"])))["values"]
rows["her, %s fit" % TYPES["base"]] = measure(her_points(base_fit))
if TYPES.get("face"):
    face = json.load(open(os.path.join(HERE, "checks", "face_%s.json" % TYPES["face"])))
    rows["her, %s fit + face" % TYPES["base"]] = measure(her_points(base_fit, face))
for t in TYPES["types"]:
    rows["tripo " + t["name"]] = measure(tripo_points(os.path.join(SOURCES, t["source"])))

print("%-28s %7s %7s %7s %7s %7s %7s %7s %7s" % ("body", "height", "head", "width", "depth", "heads", "w/h", "d/h", "chin"))
for name, m in rows.items():
    m["heads"] = m["height"] / m["head"]
    m["width/head"] = m["width"] / m["head"]
    m["depth/head"] = m["depth"] / m["head"]
    print("%-28s %7.3f %7.3f %7.3f %7.3f %7.2f %7.3f %7.3f %7.3f" % (
        name, m["height"], m["head"], m["width"], m["depth"], m["heads"], m["width/head"], m["depth/head"], m["chin_z"] / m["height"]))
with open(os.path.join(HERE, "checks", "head_size.json"), "w") as f:
    json.dump({k: {kk: round(float(vv), 4) for kk, vv in v.items()} for k, v in rows.items()}, f, indent=1)
