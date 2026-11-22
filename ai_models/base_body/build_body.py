"""The body for Forge: one mesh, the base type, with every other type as a shape key, on the mixamo_unity rig, each
type's joint positions so the game moves the bones with the shape, her face on it and eyes of her own.

    blender -b -P build_body.py

Reads types.json (title, base, types, face), checks/fit_<type>.json (fit_macros.py), build/<type>_normal.png
(bake_detail.py) and, with a face named, checks/face_<name>.json (fit_face.py: the face's sliders; bake_face.py: her
head's UV square, her skin's tone) and its maps (build/face_<name>_{color,normal}.png, build/body_<name>_color.png).
Every type is MPFB's female at its fitted sliders and the face's, wrapped onto its Tripo body where wrap.py ran
(build/wrap_<type>.npy), so all share the vertex order; the base is the mesh, the others are shape keys named for
them.

A type's skeleton stands elsewhere (a heavier body's knees are 45 mm from the base's), and in the game the bones are
moved there by translation, rotations as they are. Moving a bone moves the skin weighted to it, so a shape key holds
the type's vertices LESS that movement (sum over the vertex's bones of weight times the bone's move): the shape key
at 1 and the bones moved give the type exactly, in Unity's linear skinning (at most 4 bones a vertex, normalised,
as Unity reads them; the groups are trimmed to that here).

Her face: the head's skin island wears a slot of its own, <Title>Face, on its own UV square (bake_face.py's maps);
Forge's face controls (FaceEditorScreen's parts and controls, a blend shape each named for them, -100 to 100) are
MPFB's own targets (CONTROLS: a pair's two ends as one shape, the positive end at 100), each carrying the eyeballs
along with their sockets. Her eyes: eyeballs (eyes.py's, the iris in the paint's colour) on the LeftEye and RightEye
bones, their radius from the lid rims, a slot <Title>Eyes with maps of their own.

Writes build/forge/<Title>/:
  <Title>.fbx                     "Body" on the rig, the shape keys; feet at the origin, metres, facing -Y
  <Title>_Color.png, _Normal.png  the base's maps (bake_face.py's body colour, or a flat skin; bake_detail.py's map)
  <Title>Face_Color.png, _Normal.png, <Title>Eyes_Color.png, _MetallicSmoothness.png   the face's and the eyes'
  Bodies/<Type>_Color.png, _Normal.png   the other types' maps (drawn in the body's one slot)
  Bodies/types.json               the types for Forge as CharacterBuilder reads them: name, shape, kind, slots,
                                  softTissue, "joints": every bone's rest position in Unity's frame (as the FBX lands:
                                  x right, y up, z forward; metres from the feet) and "landmarks": positions on the
                                  type's skin (x y z, flat) for the game's check that the shape and the moved bones
                                  give the type.
"""
import bpy, json, os, shutil, sys, bmesh
import numpy as np
from mathutils import Vector
from bl_ext.blender_org.mpfb.services.targetservice import TargetService

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
from her import create, settle, apply_wrap, Head, body_of, targets_dir  # noqa: E402
from eyes import eyeball, eye_texture, save_map, SHINE, EYE_TEXTURE  # noqa: E402

TYPES = json.load(open(os.path.join(HERE, "types.json")))
TITLE, BASE = TYPES["title"], TYPES["base"]
FACE = TYPES.get("face")
SKIN = TYPES.get("skin")  # the painted Tripo body whose paint dresses her (skin_body.py took its colour already)
OUT = os.path.join(HERE, "build", "forge", TITLE)
os.makedirs(os.path.join(OUT, "Bodies"), exist_ok=True)
FLAT_SKIN = (0.80, 0.62, 0.52)  # a flat skin when there is no face to take the tone from
BONES_A_VERTEX = 4
LANDMARKS = 48  # vertices spread over the body whose positions each type records, for the game's check
LID_OVER = 0.0005  # m the lids' rims stand off the eyeball
# Forge's face controls (FaceEditorScreen.Parts: the part and the control, as the blend shape is named) and the MPFB
# target each drives: its folder, its stem and, unless decr/incr, the pair's ends (negative, positive)
CONTROLS = {
    "HeadWidth": ("head", "head-scale-horiz"), "HeadHeight": ("head", "head-scale-vert"),
    "HeadRoundness": ("head", "head-round", None), "HeadCheekbones": ("cheek", "cheek-bones"),
    "HeadCheeks": ("cheek", "cheek-volume"),
    "EyesSize": ("eyes", "eye-scale"), "EyesSpacing": ("eyes", "eye-trans", ("in", "out")),
    "EyesHeight": ("eyes", "eye-trans", ("down", "up")), "EyesTilt": ("eyes", "eye-corner1", ("down", "up")),
    "EyesDepth": ("eyes", "eye-push1", ("in", "out")),
    "BrowsHeight": ("eyebrows", "eyebrows-trans", ("down", "up")), "BrowsAngle": ("eyebrows", "eyebrows-angle", ("down", "up")),
    "BrowsDepth": ("eyebrows", "eyebrows-trans", ("backward", "forward")),
    "NoseLength": ("nose", "nose-scale-vert"), "NoseWidth": ("nose", "nose-scale-horiz"),
    "NoseHeight": ("nose", "nose-trans", ("down", "up")), "NoseBridge": ("nose", "nose-hump"),
    "NoseTip": ("nose", "nose-point", ("down", "up")),
    "MouthWidth": ("mouth", "mouth-scale-horiz"), "MouthHeight": ("mouth", "mouth-trans", ("down", "up")),
    "MouthUpperLip": ("mouth", "mouth-upperlip-volume"), "MouthLowerLip": ("mouth", "mouth-lowerlip-volume"),
    "MouthCorners": ("mouth", "mouth-angles", ("down", "up")),
    "JawWidth": ("chin", "chin-bones"), "JawLength": ("chin", "chin-height"), "JawForward": ("chin", "chin-prognathism"),
    "JawChin": ("chin", "chin-prominent"), "JawChinWidth": ("chin", "chin-width"),
}

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
TARGETS = targets_dir()
face = json.load(open(os.path.join(HERE, "checks", "face_%s.json" % FACE))) if FACE else None


def control_keys(folder, stem, ends=("decr", "incr")):
    """The target files of a control's ends ([negative keys], [positive keys]), both sides when sided; a one-sided
    shape (ends None) has no negative keys."""
    if ends is None:
        names = [stem]
        sided = os.path.exists(os.path.join(TARGETS, folder, "l-%s.target.gz" % stem))
        return [], [s + stem for s in (["l-", "r-"] if sided else [""])]
    sided = os.path.exists(os.path.join(TARGETS, folder, "l-%s-%s.target.gz" % (stem, ends[1])))
    sides = ["l-", "r-"] if sided else [""]
    return ["%s%s-%s" % (s, stem, ends[0]) for s in sides], ["%s%s-%s" % (s, stem, ends[1]) for s in sides]


def fitted(name, controls=False):
    """The MPFB female at a type's fitted sliders and the face's, with the mixamo_unity rig, settled; with
    controls, each Forge control's shape as a delta (full mesh, world frame) before settling."""
    fit = json.load(open(os.path.join(HERE, "checks", "fit_%s.json" % name)))["values"]
    body, rig = create(fit, face)
    deltas = {}
    if controls:
        me = body.data
        n = len(me.vertices)
        basis = np.empty(n * 3)
        me.shape_keys.key_blocks[0].data.foreach_get("co", basis)
        basis = basis.reshape(n, 3)
        W = np.array(body.matrix_world)
        tmp = np.empty(n * 3)
        for control, spec in CONTROLS.items():
            ends = spec[2] if len(spec) > 2 else ("decr", "incr")
            neg, pos = control_keys(spec[0], spec[1], ends)
            delta = np.zeros((n, 3))
            for keys, sign in ((pos, 1.0), (neg, -1.0)):
                for k in keys:
                    key = "ctrl-" + k
                    TargetService.load_target(body, os.path.join(TARGETS, spec[0], k + ".target.gz"), weight=0.0, name=key)
                    me.shape_keys.key_blocks[key].value = 0.0  # a weight of 0 given to load_target is taken as "the default"
                    me.shape_keys.key_blocks[key].data.foreach_get("co", tmp)
                    delta += sign * (tmp.reshape(n, 3) - basis)
            deltas[control] = (delta / (2.0 if neg else 1.0)) @ W[:3, :3].T
        is_body = body_of(body, me)
        deltas = {k: v[is_body] for k, v in deltas.items()}
    settle(body, rig)
    delta = apply_wrap(body, rig, name)  # wrap.py: the rest of the way onto the Tripo body, the bones along
    if delta is not None:
        print("%s: wrapped onto its Tripo body, %.1f mm median" % (name, np.median(np.linalg.norm(delta, axis=1)) * 1000), flush=True)
    return body, rig, deltas


def world_points(body):
    return np.array([body.matrix_world @ v.co for v in body.data.vertices])


def heads(rig):
    return {b.name: np.array(rig.matrix_world @ b.head_local) for b in rig.data.bones}


def unity(p):
    """Blender's frame (x left, y back, z up) to Unity's as the FBX lands there (x right, y up, z forward)."""
    return [round(float(-p[0]), 5), round(float(p[2]), 5), round(float(-p[1]), 5)]


# --- the base ------------------------------------------------------------------------------------------------------
body, rig, controls = fitted(BASE, controls=bool(face))
body.name = body.data.name = "Body"
rig.name = TITLE
me = body.data
N = len(me.vertices)
P0 = world_points(body)
H0 = heads(rig)
bones = [b.name for b in rig.data.bones]
print("base %s: %d vertices, %d bones, %.3f m" % (BASE, N, len(bones), P0[:, 2].max() - P0[:, 2].min()), flush=True)
assert all(len(d) == N for d in controls.values()), "a control's shape is not on the body's vertices"

# the skin weights as Unity reads them: the BONES_A_VERTEX heaviest, normalised
gi = {g.index: g.name for g in body.vertex_groups}
bi = {n: i for i, n in enumerate(bones)}
W = np.zeros((N, len(bones)))
for v in me.vertices:
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
for name in ("mixamorig:LeftEye", "mixamorig:RightEye"):
    if name not in body.vertex_groups:
        body.vertex_groups.new(name=name)

mod = body.modifiers.new("Armature", "ARMATURE")
mod.object = rig
for p in me.polygons:
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
    other, other_rig, _ = fitted(name)
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

# --- her face: its slot and square, the controls' shapes ------------------------------------------------------------
head = Head(body, me) if face else None
mat = bpy.data.materials.new(TITLE)
me.materials.clear()
me.materials.append(mat)
if face:
    me.materials.append(bpy.data.materials.new(TITLE + "Face"))
    me.materials.append(bpy.data.materials.new(TITLE + "Eyes"))
    for i in head.faces:
        me.polygons[i].material_index = 1
    uvl = me.uv_layers[0]
    arr = np.empty(len(me.loops) * 2)
    uvl.data.foreach_get("uv", arr)
    arr = arr.reshape(-1, 2)
    arr[head.loops] = arr[head.loops] * face["uv"]["scale"] + face["uv"]["offset"]
    uvl.data.foreach_set("uv", arr.ravel())
    # each control: its shape, local; the eyeballs (made below) follow each socket's rim
    rim_moves = {}
    for control, delta in controls.items():
        key = body.shape_key_add(name=control, from_mix=False)
        local = (P0 + delta) @ to_local[:3, :3].T + to_local[:3, 3]
        key.data.foreach_set("co", local.ravel().astype(np.float32))
        rim_moves[control] = [delta[r].mean(0) @ to_local[:3, :3].T for r in head.eyes]
    print("%d face controls as shapes: %s" % (len(controls), ", ".join(
        "%s %.1f mm" % (c, np.linalg.norm(d, axis=1).max() * 1000) for c, d in list(controls.items())[:6])), flush=True)

# --- her eyes ----------------------------------------------------------------------------------------------------------
if face:
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    deform = bm.verts.layers.deform.verify()
    shapes = bm.verts.layers.shape
    radius = None
    for side, bone, rim in (("left", "mixamorig:LeftEye", head.eyes[1]), ("right", "mixamorig:RightEye", head.eyes[0])):
        centre = H0[bone]
        d = np.linalg.norm(P0[rim] - centre, axis=1)
        r = float(d.min() - LID_OVER)
        radius = r if radius is None else min(radius, r)
        print("%s eye: the bone %.1f mm from its rim (%.1f to %.1f); eyeball %.1f mm" % (side, d.mean() * 1000, d.min() * 1000, d.max() * 1000, r * 1000), flush=True)
    for side, bone, which, rim in (("left", "mixamorig:LeftEye", 2, head.eyes[1]), ("right", "mixamorig:RightEye", 1, head.eyes[0])):
        centre = to_local[:3, :3] @ H0[bone] + to_local[:3, 3]
        before = set(bm.verts)
        faces = eyeball(bm, centre, radius, to_local[:3, :3] @ np.array([0.0, -1.0, 0.0]), which, 2)
        new = [v for f in faces for v in f.verts]
        group = body.vertex_groups[bone].index
        k = 1 if side == "left" else 0
        for v in set(new):
            v[deform].clear()
            v[deform][group] = 1.0
            for control, moves in rim_moves.items():
                v[shapes[control]] = v.co + Vector(moves[k])
    bm.to_mesh(me)
    bm.free()
    for kb in me.shape_keys.key_blocks:  # written back from bmesh, every key's value comes out 1.0
        kb.value = 0.0
    print("eyeballs of %.1f mm on the eye bones; %d vertices now" % (radius * 1000, len(me.vertices)), flush=True)
    iris = face.get("iris", [0.35, 0.3, 0.25])
    bpy.data.images.remove(save_map(eye_texture(iris, radius), os.path.join(OUT, TITLE + "Eyes_Color.png"), "sRGB"))
    shine = np.zeros((EYE_TEXTURE, EYE_TEXTURE, 4), np.float32)
    shine[..., 3] = SHINE
    bpy.data.images.remove(save_map(shine, os.path.join(OUT, TITLE + "Eyes_MetallicSmoothness.png"), "Non-Color"))

# --- the maps ------------------------------------------------------------------------------------------------------------
if face:
    shutil.copyfile(os.path.join(HERE, "build", "body_%s_color.png" % FACE), os.path.join(OUT, TITLE + "_Color.png"))
    toned_face = os.path.join(HERE, "build", "face_%s_skin.png" % FACE)  # skin_body.py: the face in the body's tone
    shutil.copyfile(toned_face if os.path.exists(toned_face) else os.path.join(HERE, "build", "face_%s_color.png" % FACE),
                    os.path.join(OUT, TITLE + "Face_Color.png"))
    shutil.copyfile(os.path.join(HERE, "build", "face_%s_normal.png" % FACE), os.path.join(OUT, TITLE + "Face_Normal.png"))
else:
    colour = bpy.data.images.new(TITLE + "_Color", 256, 256)
    colour.pixels.foreach_set(np.tile(np.array([*FLAT_SKIN, 1.0], dtype=np.float32), 256 * 256))
    colour.filepath_raw = os.path.join(OUT, TITLE + "_Color.png")
    colour.file_format = "PNG"
    colour.save()
shutil.copyfile(os.path.join(HERE, "build", "%s_normal.png" % BASE), os.path.join(OUT, TITLE + "_Normal.png"))


def pixels_of(path, space):
    img = bpy.data.images.load(path)
    img.colorspace_settings.name = space
    px = np.empty(img.size[0] * img.size[1] * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(img.size[1], img.size[0], 4)
    bpy.data.images.remove(img)
    return px


# the roughness (bake_detail.py, a painted Tripo body's; every type's lies on the one UV, so the skin's serves all,
# or the first type's that has one) as URP Lit reads it: smoothness in the alpha, no metal
rough_of = [n for n in ([SKIN] if SKIN else []) + [t["name"] for t in TYPES["types"]]
            if n and os.path.exists(os.path.join(HERE, "build", "%s_roughness.png" % n))]
if rough_of:
    rough = pixels_of(os.path.join(HERE, "build", "%s_roughness.png" % rough_of[0]), "Non-Color")
    ms = np.zeros_like(rough)
    ms[..., 3] = 1.0 - rough[..., 0]
    del rough
    bpy.data.images.remove(save_map(ms, os.path.join(OUT, TITLE + "_MetallicSmoothness.png"), "Non-Color"))
    print("%s's roughness as %s_MetallicSmoothness.png (smoothness %.2f to %.2f)" % (rough_of[0], TITLE, ms[..., 3].min(), ms[..., 3].max()), flush=True)
    del ms


def linear(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def encoded(c):
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(np.maximum(c, 0), 1 / 2.4) - 0.055)


def tone_of(px):
    """The median colour of a map's painted pixels, in linear light, over every 16th row and column."""
    s = px[::16, ::16, :3]
    return np.median(linear(s[s.sum(2) > 0.1]), axis=0)


# every other type's maps: its own relief; its own paint when its Tripo body is painted, toned to the body's (the
# skin's, median over median in linear light as skin_body.py tones), else the body's paint
body_tone = tone_of(pixels_of(os.path.join(OUT, TITLE + "_Color.png"), "sRGB")) if face else None
for t in forge_types:
    for slot in t["slots"]:
        shutil.copyfile(os.path.join(HERE, "build", "%s_normal.png" % t["name"]),
                        os.path.join(OUT, "Bodies", "%s_Normal.png" % slot["map"]))
        own = os.path.join(HERE, "build", "%s_color.png" % t["name"])
        if face and os.path.exists(own):
            px = pixels_of(own, "sRGB")
            gain = body_tone / np.maximum(tone_of(px), 1e-4)
            px[..., :3] = np.clip(encoded(linear(px[..., :3]) * gain), 0, 1)
            px[..., 3] = 1.0
            bpy.data.images.remove(save_map(px, os.path.join(OUT, "Bodies", "%s_Color.png" % slot["map"]), "sRGB"))
            del px
            print("%s: its own paint, toned to the body's (gain %s)" % (t["name"], np.round(gain, 3).tolist()), flush=True)
        else:
            shutil.copyfile(os.path.join(OUT, TITLE + "_Color.png"), os.path.join(OUT, "Bodies", "%s_Color.png" % slot["map"]))
with open(os.path.join(OUT, "Bodies", "types.json"), "w") as f:
    json.dump({"types": forge_types}, f, indent=1)

# --- the check: her mesh and her Basis are the settled body, every key at 0 ----------------------------------------
P0_local = P0 @ to_local[:3, :3].T + to_local[:3, 3]
co = np.empty(len(me.vertices) * 3)
me.vertices.foreach_get("co", co)
co = co.reshape(-1, 3)[:N]
basis = np.empty(len(me.vertices) * 3)
me.shape_keys.key_blocks[0].data.foreach_get("co", basis)
basis = basis.reshape(-1, 3)[:N]
values = sorted({round(float(k.value), 3) for k in me.shape_keys.key_blocks})
print("check: matrix_world scale %s; vertices off the settled body %.2f mm max, the Basis %.2f mm max; key values %s" % (
    [round(float(s), 3) for s in body.matrix_world.to_scale()], np.linalg.norm(co - P0_local, axis=1).max() * 1000,
    np.linalg.norm(basis - P0_local, axis=1).max() * 1000, values), flush=True)
assert values == [0.0], "a shape key is not at 0: the FBX would carry it in the body"
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "build", "body_%s.blend" % TITLE))

# --- the FBX --------------------------------------------------------------------------------------------------------
bpy.ops.object.select_all(action="DESELECT")
body.select_set(True)
rig.select_set(True)
path = os.path.join(OUT, TITLE + ".fbx")
bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={"ARMATURE", "MESH"}, apply_unit_scale=True,
                         apply_scale_options="FBX_SCALE_ALL", add_leaf_bones=False, bake_anim=False,
                         mesh_smooth_type="FACE", path_mode="STRIP")
print("wrote", path, "with", len(me.shape_keys.key_blocks) - 1, "shape keys and", len(me.materials), "slots", flush=True)
