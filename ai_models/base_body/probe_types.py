"""The four fitted MPFB bodies compared as candidates for one mesh with shape keys: do they share the vertex order,
where does each type's rig put its joints, and how far is each knee and elbow from the centre of its limb there.

    blender -b -P probe_types.py

Reads types.json (the types, the base) and checks/fit_<type>.json. Prints the numbers; writes checks/probe_types.json.
"""
import bpy, json, os
import numpy as np
from bl_ext.blender_org.mpfb.services.humanservice import HumanService
from bl_ext.blender_org.mpfb.services.targetservice import TargetService
from bl_ext.blender_org.mpfb.services.locationservice import LocationService

HERE = os.path.dirname(os.path.abspath(__file__))
TYPES = json.load(open(os.path.join(HERE, "types.json")))
MACRO = ["weight", "muscle", "proportions", "cupsize", "firmness"]
FOLDER = {"measure-bust-circ": "torso", "measure-underbust-circ": "torso", "measure-waist-circ": "torso",
          "measure-hips-circ": "torso", "torso-scale-depth": "torso", "torso-scale-horiz": "torso",
          "torso-vshape": "torso", "hip-scale-depth": "hip", "hip-scale-horiz": "hip",
          "stomach-pregnant": "stomach", "buttocks-volume": "buttocks", "breast-volume-vert": "breast"}
ENDS = {"breast-volume-vert": ("down", "up")}
# a joint, the two joints its limb runs between, and the side its slice lies on (x sign in Blender)
JOINTS = [("LeftLeg", "LeftUpLeg", "LeftFoot", 1), ("RightLeg", "RightUpLeg", "RightFoot", -1),
          ("LeftForeArm", "LeftArm", "LeftHand", 1), ("RightForeArm", "RightArm", "RightHand", -1)]

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
TARGETS = LocationService.get_mpfb_data("targets")


def fitted(name):
    """The MPFB female at a type's fitted sliders, with the mixamo_unity rig, helpers dropped, targets baked in."""
    fit = json.load(open(os.path.join(HERE, "checks", "fit_%s.json" % name)))["values"]
    macro = TargetService.get_default_macro_info_dict()
    macro.update({"gender": 0.0, "age": 0.5})
    macro["race"] = {"asian": 0.0, "caucasian": 1.0, "african": 0.0}
    macro.update({k: fit[k] for k in MACRO})
    body = HumanService.create_human(mask_helpers=True, macro_detail_dict=macro)
    for slider, value in fit.items():
        if slider in MACRO or abs(value) < 1e-3:
            continue
        decr, incr = ENDS.get(slider, ("decr", "incr"))
        end = incr if value > 0 else decr
        folder = FOLDER.get(slider, "arms" if "arm" in slider else "legs")
        sided = os.path.exists(os.path.join(TARGETS, folder, "l-%s-%s.target.gz" % (slider, end)))
        for side in (["l-", "r-"] if sided else [""]):
            TargetService.load_target(body, os.path.join(TARGETS, folder, "%s%s-%s.target.gz" % (side, slider, end)),
                                      weight=abs(value))
    rig = HumanService.add_builtin_rig(body, "mixamo_unity")
    for m in body.modifiers:
        if m.type == "ARMATURE":
            m.show_viewport = False
    dg = bpy.context.evaluated_depsgraph_get()
    baked = bpy.data.meshes.new_from_object(body.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    body.shape_key_clear()
    body.modifiers.clear()
    body.data = baked
    body.name, rig.name = "body " + name, "rig " + name
    bpy.context.view_layer.update()
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
