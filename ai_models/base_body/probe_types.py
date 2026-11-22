"""The four fitted MPFB bodies compared as candidates for one mesh with shape keys: do they share the vertex order,
where does each type's rig put its joints, and how far is each knee and elbow from the centre of its limb there.

    blender -b -P probe_types.py

Reads types.json (the types, the base) and checks/fit_<type>.json. Prints the numbers; writes checks/probe_types.json.
"""
import bpy, json, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from her import create, settle  # noqa: E402

TYPES = json.load(open(os.path.join(HERE, "types.json")))
# a joint, the two joints its limb runs between, and the side its slice lies on (x sign in Blender)
JOINTS = [("LeftLeg", "LeftUpLeg", "LeftFoot", 1), ("RightLeg", "RightUpLeg", "RightFoot", -1),
          ("LeftForeArm", "LeftArm", "LeftHand", 1), ("RightForeArm", "RightArm", "RightHand", -1)]

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def fitted(name):
    """The MPFB female at a type's fitted sliders, with the mixamo_unity rig, helpers dropped, targets baked in."""
    fit = json.load(open(os.path.join(HERE, "checks", "fit_%s.json" % name)))["values"]
    body, rig = create(fit)
    settle(body)
    body.name, rig.name = "body " + name, "rig " + name
    return body, rig


def points(body):
    return np.array([body.matrix_world @ v.co for v in body.data.vertices])


def edges(body):
    E = np.empty(len(body.data.edges) * 2, dtype=np.int64)
    body.data.edges.foreach_get("vertices", E)
    return E.reshape(-1, 2)


def heads(rig):
    return {b.name: np.array(rig.matrix_world @ b.head_local) for b in rig.data.bones}


def off_centre(P, J, A, B, side):
    """How far joint J stands from the centre of the limb's cross-section there: the vertices within 1 cm of J's level
    along the limb's axis A->B and within 15 cm of it, on the joint's side; the distance taken across the axis."""
    axis = (B - A) / np.linalg.norm(B - A)
    along = (P - J) @ axis
    near = (np.abs(along) < 0.01) & (np.linalg.norm(P - J, axis=1) < 0.15) & (side * P[:, 0] > 0)
    if near.sum() < 6:
        return None
    d = P[near].mean(0) - J
    d -= (d @ axis) * axis
    return float(np.linalg.norm(d))


report = {}
base = None
for t in TYPES["types"]:
    name = t["name"]
    body, rig = fitted(name)
    P, E, H = points(body), edges(body), heads(rig)
    row = {"vertices": len(P), "edges": len(E), "height": round(float(P[:, 2].max() - P[:, 2].min()), 4)}
    if base is None:
        base = (P, E, H)
    else:
        row["same_edges"] = bool(len(E) == len(base[1]) and np.array_equal(E, base[1]))
        row["moved_mm"] = {"median": round(float(np.median(np.linalg.norm(P - base[0], axis=1))) * 1000, 1),
                           "max": round(float(np.linalg.norm(P - base[0], axis=1).max()) * 1000, 1)}
        row["joints_moved_mm"] = {k: round(float(np.linalg.norm(H[k] - base[2][k])) * 1000, 1)
                                  for k in ("mixamorig:Hips", "mixamorig:LeftUpLeg", "mixamorig:LeftLeg",
                                            "mixamorig:LeftArm", "mixamorig:LeftForeArm", "mixamorig:LeftShoulder")}
    row["off_centre_mm"] = {j: (None if (v := off_centre(P, H["mixamorig:" + j], H["mixamorig:" + a],
                                                          H["mixamorig:" + b], s)) is None else round(v * 1000, 1))
                            for j, a, b, s in JOINTS}
    report[name] = row
    print(name, json.dumps(row), flush=True)
    bpy.data.objects.remove(body)
    bpy.data.objects.remove(rig)

with open(os.path.join(HERE, "checks", "probe_types.json"), "w") as f:
    json.dump(report, f, indent=1)
