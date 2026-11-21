"""The body for Forge: one mesh, the base type, with every other type as a shape key, on the mixamo_unity rig, and
each type's joint positions, so the game moves the bones with the shape.

    blender -b -P build_body.py

Reads types.json (title, base, types), checks/fit_<type>.json (fit_macros.py) and build/<type>_normal.png
(bake_detail.py). Every type is MPFB's female at its fitted sliders, so all share the vertex order; the base is the
mesh, the others are shape keys named for them.

A type's skeleton stands elsewhere (a heavier body's knees are 45 mm from the base's), and in the game the bones are
moved there by translation, rotations as they are. Moving a bone moves the skin weighted to it, so a shape key holds
the type's vertices LESS that movement (sum over the vertex's bones of weight times the bone's move): the shape key
at 1 and the bones moved give the type exactly, in Unity's linear skinning (at most 4 bones a vertex, normalised,
as Unity reads them; the groups are trimmed to that here).

Writes build/forge/<Title>/:
  <Title>.fbx                     "Body" on the rig, the shape keys; feet at the origin, metres, facing -Y
  <Title>_Color.png, _Normal.png  the base's maps (a flat skin for now; bake_detail.py's map)
  Bodies/<Type>_Color.png, _Normal.png   the other types' maps (drawn in the body's one slot)
  Bodies/types.json               the types for Forge as CharacterBuilder reads them: name, shape, kind, slots,
                                  softTissue, and new here "joints": every bone's rest position in Unity's frame
                                  (as the FBX lands: x right, y up, z forward; metres from the
                                  feet) and "landmarks": positions on the type's surface (x y z, flat) for the
                                  game's check that the shape and the moved bones give the type.
"""
import bpy, json, os, shutil
import numpy as np
from bl_ext.blender_org.mpfb.services.humanservice import HumanService
from bl_ext.blender_org.mpfb.services.targetservice import TargetService
from bl_ext.blender_org.mpfb.services.locationservice import LocationService

HERE = os.path.dirname(os.path.abspath(__file__))
TYPES = json.load(open(os.path.join(HERE, "types.json")))
TITLE, BASE = TYPES["title"], TYPES["base"]
OUT = os.path.join(HERE, "build", "forge", TITLE)
os.makedirs(os.path.join(OUT, "Bodies"), exist_ok=True)
MACRO = ["weight", "muscle", "proportions", "cupsize", "firmness"]
FOLDER = {"measure-bust-circ": "torso", "measure-underbust-circ": "torso", "measure-waist-circ": "torso",
          "measure-hips-circ": "torso", "torso-scale-depth": "torso", "torso-scale-horiz": "torso",
          "torso-vshape": "torso", "hip-scale-depth": "hip", "hip-scale-horiz": "hip",
          "stomach-pregnant": "stomach", "buttocks-volume": "buttocks", "breast-volume-vert": "breast"}
ENDS = {"breast-volume-vert": ("down", "up")}
SKIN = (0.80, 0.62, 0.52)  # a flat skin until MPFB's own skin is wired in
BONES_A_VERTEX = 4
LANDMARKS = 48  # vertices spread over the body whose positions each type records, for the game's check

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
    bpy.context.view_layer.update()
    return body, rig


def world_points(body):
    return np.array([body.matrix_world @ v.co for v in body.data.vertices])


def heads(rig):
    return {b.name: np.array(rig.matrix_world @ b.head_local) for b in rig.data.bones}


def unity(p):
    """Blender's frame (x left, y back, z up) to Unity's as the FBX lands there (x right, y up, z forward)."""
    return [round(float(-p[0]), 5), round(float(p[2]), 5), round(float(-p[1]), 5)]


# --- the base ------------------------------------------------------------------------------------------------------
body, rig = fitted(BASE)
body.name = body.data.name = "Body"
rig.name = TITLE
N = len(body.data.vertices)
P0 = world_points(body)
H0 = heads(rig)
bones = [b.name for b in rig.data.bones]
print("base %s: %d vertices, %d bones, %.3f m" % (BASE, N, len(bones), P0[:, 2].max() - P0[:, 2].min()), flush=True)

# the skin weights as Unity reads them: the BONES_A_VERTEX heaviest, normalised
gi = {g.index: g.name for g in body.vertex_groups}
bi = {n: i for i, n in enumerate(bones)}
W = np.zeros((N, len(bones)))
for v in body.data.vertices:
    for g in v.groups:
        if gi[g.group] in bi:
            W[v.index, bi[gi[g.group]]] = g.weight
if (W > 0).sum(1).max() > BONES_A_VERTEX:
    keep = np.argsort(-W, axis=1)[:, :BONES_A_VERTEX]
    trimmed = np.zeros_like(W)
    np.put_along_axis(trimmed, keep, np.take_along_axis(W, keep, 1), 1)
    W = trimmed
    for g in list(body.vertex_groups):
        body.vertex_groups.remove(g)
    for name in bones:
        body.vertex_groups.new(name=name)
    for i in range(N):
        for j in np.nonzero(W[i])[0]:
            body.vertex_groups[bones[j]].add([i], float(W[i, j]), "REPLACE")
    print("weights trimmed to %d bones a vertex" % BONES_A_VERTEX, flush=True)
W /= np.maximum(W.sum(1, keepdims=True), 1e-9)

mod = body.modifiers.new("Armature", "ARMATURE")
mod.object = rig
for p in body.data.polygons:
    p.use_smooth = True
to_local = np.array(body.matrix_world.inverted())
rng = np.random.default_rng(7)
landmarks = np.sort(rng.choice(N, LANDMARKS, replace=False))

# --- the other types as shape keys --------------------------------------------------------------------------------
body.shape_key_add(name="Basis", from_mix=False)
forge_types = []


def type_entry(name, H, P):
    own = name == BASE
    return {"name": name, "shape": "" if own else name, "kind": "body",
            "slots": [] if own else [{"slot": TITLE, "map": name}], "softTissue": 1.0,
            "joints": [{"name": b, "at": unity(H[b])} for b in bones],
            "landmarks": [c for i in landmarks for c in unity(P[i])]}


forge_types.append(type_entry(BASE, H0, P0))
for t in TYPES["types"]:
    name = t["name"]
    if name == BASE:
        continue
    other, other_rig = fitted(name)
    P, H = world_points(other), heads(other_rig)
    assert len(P) == N, "%s has %d vertices, the base %d" % (name, len(P), N)
    D = np.array([H[b] - H0[b] for b in bones])  # each bone's move, base to this type
    carried = W @ D  # what moving the bones does to each vertex
    shape = P - carried
    key = body.shape_key_add(name=name, from_mix=False)
    local = shape @ to_local[:3, :3].T + to_local[:3, 3]
    key.data.foreach_set("co", local.ravel().astype(np.float32))
    forge_types.append(type_entry(name, H, P))
    print("%s: vertices move %.1f mm median, %.1f max; bones move %.1f mm max; the key holds %.1f mm median" % (
        name, np.median(np.linalg.norm(P - P0, axis=1)) * 1000, np.linalg.norm(P - P0, axis=1).max() * 1000,
        np.linalg.norm(D, axis=1).max() * 1000, np.median(np.linalg.norm(shape - P0, axis=1)) * 1000), flush=True)
    bpy.data.objects.remove(other)
    bpy.data.objects.remove(other_rig)

# --- the maps and the material --------------------------------------------------------------------------------------
colour = bpy.data.images.new(TITLE + "_Color", 256, 256)
colour.pixels.foreach_set(np.tile(np.array([*SKIN, 1.0], dtype=np.float32), 256 * 256))
colour.filepath_raw = os.path.join(OUT, TITLE + "_Color.png")
colour.file_format = "PNG"
colour.save()
shutil.copyfile(os.path.join(HERE, "build", "%s_normal.png" % BASE), os.path.join(OUT, TITLE + "_Normal.png"))
for t in forge_types:
    for slot in t["slots"]:
        shutil.copyfile(os.path.join(HERE, "build", "%s_normal.png" % t["name"]),
                        os.path.join(OUT, "Bodies", "%s_Normal.png" % slot["map"]))
        shutil.copyfile(os.path.join(OUT, TITLE + "_Color.png"), os.path.join(OUT, "Bodies", "%s_Color.png" % slot["map"]))
mat = bpy.data.materials.new(TITLE)
mat.use_nodes = True
body.data.materials.clear()
body.data.materials.append(mat)
with open(os.path.join(OUT, "Bodies", "types.json"), "w") as f:
    json.dump({"types": forge_types}, f, indent=1)

# --- the FBX --------------------------------------------------------------------------------------------------------
bpy.ops.object.select_all(action="DESELECT")
body.select_set(True)
rig.select_set(True)
path = os.path.join(OUT, TITLE + ".fbx")
bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={"ARMATURE", "MESH"}, apply_unit_scale=True,
                         apply_scale_options="FBX_SCALE_ALL", add_leaf_bones=False, bake_anim=False,
                         mesh_smooth_type="FACE", path_mode="STRIP")
print("wrote", path, "with", len(forge_types) - 1, "shape keys", flush=True)
