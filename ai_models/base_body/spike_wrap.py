"""Spike, step 1b: a Tripo body type wrapped onto MPFB's female base, as a shape key of the base in its own rest pose.

    blender -b -P spike_wrap.py -- <tripo file> <type name>

1. The base (MPFB hm08, female, its helpers dropped) with the mixamo_unity rig and its weights.
2. The Tripo body scaled to the base's height, feet on the same ground, its trunk over the base's.
3. Pose fit: the base's limb, spine and head bones turned (coordinate descent) until the posed base lies on the Tripo body.
4. Wrap, in that pose: each base vertex pulled to the nearest Tripo surface that faces its way, the pull smoothed over
   the mesh, stiff first and looser each round. The head and neck, the fingers and toes take no pull of their own:
   the head is its own piece, Tripo's fingers are fused; they follow what they hang on.
5. Unposed: each vertex through the inverse of its skinning matrix, so the shape is the base's rest pose.

Writes checks/wrap_<type>_*.png, checks/wrap_<type>.json (distances), build/wrap_<type>.blend.
"""
import bpy, json, os, sys, time
import numpy as np
from mathutils import Vector, Matrix, Euler
from mathutils.bvhtree import BVHTree
from bl_ext.blender_org.mpfb.services.humanservice import HumanService
from bl_ext.blender_org.mpfb.services.targetservice import TargetService

ARGS = sys.argv[sys.argv.index("--") + 1:]
SOURCE, TYPE = ARGS[0], ARGS[1]
HERE = os.path.dirname(os.path.abspath(__file__))
os.makedirs(os.path.join(HERE, "build"), exist_ok=True)
T0 = time.time()


def log(*a):
    print("[%6.1fs]" % (time.time() - T0), *a, flush=True)


bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# --- 1. the base ---------------------------------------------------------------------------------------------------
macro = TargetService.get_default_macro_info_dict()
macro.update({"gender": 0.0, "age": 0.5, "muscle": 0.5, "weight": 0.5})
macro["race"] = {"asian": 0.0, "caucasian": 1.0, "african": 0.0}
base = HumanService.create_human(mask_helpers=True, macro_detail_dict=macro)
rig = HumanService.add_builtin_rig(base, "mixamo_unity")
for m in base.modifiers:
    if m.type == "ARMATURE":
        m.show_viewport = False
dg = bpy.context.evaluated_depsgraph_get()
baked = bpy.data.meshes.new_from_object(base.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
base.shape_key_clear()
base.modifiers.clear()
base.data = baked
mod = base.modifiers.new("Armature", "ARMATURE")
mod.object = rig
base.name, rig.name = "base", "rig"
N = len(base.data.vertices)
log("base", N, "vertices,", len(base.vertex_groups), "groups,", len(rig.data.bones), "bones")

bpy.context.view_layer.update()
rest_world = np.array([base.matrix_world @ v.co for v in base.data.vertices])
height = rest_world[:, 2].max() - rest_world[:, 2].min()
ground = rest_world[:, 2].min()

# weights, normalised as the armature modifier normalises them
bone_names = [b.name for b in rig.data.bones]
W = np.zeros((N, len(bone_names)))
gi = {g.index: g.name for g in base.vertex_groups}
bi = {n: i for i, n in enumerate(bone_names)}
for v in base.data.vertices:
    for g in v.groups:
        name = gi[g.group]
        if name in bi:
            W[v.index, bi[name]] = g.weight
W /= np.maximum(W.sum(1, keepdims=True), 1e-9)


def weight_of(prefixes):
    cols = [bi[n] for n in bone_names if any(n.startswith("mixamorig:" + p) for p in prefixes)]
    return W[:, cols].sum(1)


# no pull of their own: head and neck, fingers, toes
free = np.clip(weight_of(["Head", "Neck", "Jaw", "LeftEye", "RightEye", "LeftOrbicularis", "RightOrbicularis",
                          "LeftHandIndex", "LeftHandMiddle", "LeftHandRing", "LeftHandPinky", "LeftHandThumb",
                          "RightHandIndex", "RightHandMiddle", "RightHandRing", "RightHandPinky", "RightHandThumb",
                          "LeftToeBase", "RightToeBase"]), 0, 1)

# --- 2. the Tripo body -----------------------------------------------------------------------------------------------
before = set(scene.objects)
if SOURCE.endswith(".glb"):
    bpy.ops.import_scene.gltf(filepath=SOURCE)
else:
    bpy.ops.import_scene.fbx(filepath=SOURCE)
tripo = [o for o in scene.objects if o not in before and o.type == "MESH"][0]
for o in scene.objects:
    if o not in before and o is not tripo:
        bpy.data.objects.remove(o)
tm = tripo.matrix_world.copy()
tripo.parent = None
tripo.matrix_world = tm
bpy.ops.object.select_all(action="DESELECT")
tripo.select_set(True)
bpy.context.view_layer.objects.active = tripo
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
tripo.name = "tripo"
T = np.array([v.co for v in tripo.data.vertices])
k = height / (T[:, 2].max() - T[:, 2].min())
T = (T - [0, 0, T[:, 2].min()]) * k + [0, 0, ground]
trunk_b = rest_world[(rest_world[:, 2] > ground + 0.45 * height) & (rest_world[:, 2] < ground + 0.75 * height) & (np.abs(rest_world[:, 0]) < 0.15)]
trunk_t = T[(T[:, 2] > ground + 0.45 * height) & (T[:, 2] < ground + 0.75 * height) & (np.abs(T[:, 0]) < 0.15)]
T[:, 0] += trunk_b[:, 0].mean() - trunk_t[:, 0].mean()
T[:, 1] += trunk_b[:, 1].mean() - trunk_t[:, 1].mean()
tripo.data.vertices.foreach_set("co", T.ravel())
tripo.data.update()
tripo_bvh = BVHTree.FromObject(tripo, bpy.context.evaluated_depsgraph_get())
rng = np.random.default_rng(1)
T_sample = T[rng.choice(len(T), min(4500, len(T)), replace=False)]
log("tripo", len(T), "vertices, scaled", round(k, 4))


# --- 3. pose fit -----------------------------------------------------------------------------------------------------
def posed():
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = base.evaluated_get(dg)
    co = np.empty(N * 3)
    ev.data.vertices.foreach_get("co", co)
    mw = np.array(base.matrix_world)
    co = co.reshape(N, 3) @ mw[:3, :3].T + mw[:3, 3]
    return co, BVHTree.FromObject(base, dg)


EVERY = np.arange(0, N, 3)


def cost():
    co, bvh = posed()
    there = 0.0
    for p in co[EVERY]:
        hit = tripo_bvh.find_nearest(Vector(p))
        there += min(hit[3], 0.08) ** 2 if hit[0] else 0.0064
    back = 0.0
    for p in T_sample:
        hit = bvh.find_nearest(Vector(p))
        back += min(hit[3], 0.08) ** 2 if hit[0] else 0.0064
    return there / len(EVERY) + back / len(T_sample)


FIT = ["Hips", "Spine", "Spine1", "Spine2", "Neck", "Head", "LeftShoulder", "RightShoulder", "LeftArm", "RightArm",
       "LeftForeArm", "RightForeArm", "LeftHand", "RightHand", "LeftUpLeg", "RightUpLeg", "LeftLeg", "RightLeg",
       "LeftFoot", "RightFoot"]
# no turn about their own length (a bone's Y): a round limb fits as well twisted, and the twist would come back out
# of the unposing as a turned calf or forearm (skinny's first fit: shins 10 and 15 degrees, opposite ways)
NO_TWIST = {"Spine", "Spine1", "Spine2", "Neck", "LeftArm", "RightArm", "LeftForeArm", "RightForeArm",
            "LeftUpLeg", "RightUpLeg", "LeftLeg", "RightLeg"}
for pb in rig.pose.bones:
    pb.rotation_mode = "XYZ"
best = cost()
log("pose fit: start cost %.6f" % best)
step = np.radians(8)
while step > np.radians(0.5):
    improved = False
    for name in FIT:
        pb = rig.pose.bones["mixamorig:" + name]
        for axis in range(3):
            if axis == 1 and name in NO_TWIST:
                continue
            for sign in (1, -1):
                old = pb.rotation_euler[axis]
                pb.rotation_euler[axis] = old + sign * step
                c = cost()
                if c < best - 1e-9:
                    best, improved = c, True
                    break
                pb.rotation_euler[axis] = old
    log("  step %.2f deg: cost %.6f" % (np.degrees(step), best))
    if not improved:
        step /= 2
pose_angles = {pb.name: [round(np.degrees(a), 1) for a in pb.rotation_euler] for pb in rig.pose.bones
               if any(abs(a) > 1e-6 for a in pb.rotation_euler)}

# --- 4. wrap, in the fitted pose -------------------------------------------------------------------------------------
P, _ = posed()
start = P.copy()
edges = np.array([e.vertices[:] for e in base.data.edges])
deg = np.bincount(edges.ravel(), minlength=N).astype(float)


def neighbour_sum(U):
    S = np.zeros_like(U)
    np.add.at(S, edges[:, 0], U[edges[:, 1]])
    np.add.at(S, edges[:, 1], U[edges[:, 0]])
    return S


def normals(co):
    tmp = bpy.data.meshes.new("tmp")
    tmp.from_pydata(co.tolist(), [], [list(f.vertices) for f in base.data.polygons])
    n = np.empty(N * 3)
    tmp.vertices.foreach_get("normal", n)
    bpy.data.meshes.remove(tmp)
    return n.reshape(N, 3)


ROUNDS = 24
for r in range(ROUNDS):
    nb = normals(P)
    D = np.zeros((N, 3))
    w = np.zeros(N)
    for i in range(N):
        hit = tripo_bvh.find_nearest(Vector(P[i]))
        if hit[0] is None or hit[3] > 0.08:
            continue
        if np.dot(nb[i], hit[1]) < 0.3:
            continue
        D[i] = np.array(hit[0]) - P[i]
        w[i] = 1.0
    w *= 1.0 - free
    # stiff to loose: the data's pull against the membrane
    alpha = 0.05 * (40.0 ** (r / (ROUNDS - 1)))
    U = D * w[:, None]
    for _ in range(60):
        U = (alpha * w[:, None] * D + neighbour_sum(U)) / (alpha * w + deg)[:, None]
    P = P + U
    gap = np.linalg.norm(D[w > 0], axis=1)
    log("  wrap round %d: alpha %.3f, pulled %d, gap median %.1f mm, 95%% %.1f mm" %
        (r, alpha, int((w > 0).sum()), 1000 * np.median(gap), 1000 * np.percentile(gap, 95)))

# --- 5. unposed --------------------------------------------------------------------------------------------------------
mw_arm = rig.matrix_world
skin = []
for name in bone_names:
    pb = rig.pose.bones[name]
    m = mw_arm @ pb.matrix @ pb.bone.matrix_local.inverted() @ mw_arm.inverted()
    skin.append(np.array(m))
skin = np.array(skin)                              # (B, 4, 4) world rest -> world posed
M = np.einsum("nb,bij->nij", W, skin)              # (N, 4, 4) each vertex's blended matrix
Minv = np.linalg.inv(M)


def unpose(co):
    h = np.concatenate([co, np.ones((N, 1))], 1)
    return np.einsum("nij,nj->ni", Minv, h)[:, :3]


roundtrip = np.abs(unpose(start) - rest_world).max()
log("unpose round trip: %.3f mm" % (1000 * roundtrip))
rest_shape = unpose(P)
base_inv = np.array(base.matrix_world.inverted())
local = rest_shape @ base_inv[:3, :3].T + base_inv[:3, 3]
base.shape_key_add(name="Basis")
key = base.shape_key_add(name=TYPE)
key.data.foreach_set("co", local.ravel())
np.save(os.path.join(HERE, "build", "shape_%s.npy" % TYPE), local)

# --- measures: how far Tripo's surface is from the wrapped base, both posed alike --------------------------------------
key.value = 1.0
co, bvh = posed()
dist, region = [], []
for p in T:
    hit = bvh.find_nearest(Vector(p))
    dist.append(hit[3])
    region.append(free[base.data.polygons[hit[2]].vertices[0]] > 0.5)
dist, region = np.array(dist), np.array(region)
body = dist[~region]
moved = np.linalg.norm(rest_shape - rest_world, axis=1)
report = {
    "type": TYPE, "base_vertices": N, "tripo_vertices": len(T), "pose_fit_cost": best, "pose": pose_angles,
    "tripo_to_wrapped_mm_body": {"median": round(1000 * float(np.median(body)), 2), "p95": round(1000 * float(np.percentile(body, 95)), 2),
                                 "p99": round(1000 * float(np.percentile(body, 99)), 2), "max": round(1000 * float(body.max()), 2)},
    "tripo_to_wrapped_mm_head_hands_feet": {"median": round(1000 * float(np.median(dist[region])), 2), "p95": round(1000 * float(np.percentile(dist[region], 95)), 2)},
    "shape_moves_mm": {"median": round(1000 * float(np.median(moved)), 2), "max": round(1000 * float(moved.max()), 2)},
    "unpose_roundtrip_mm": round(1000 * float(roundtrip), 4),
}
print("REPORT " + json.dumps(report))
with open(os.path.join(HERE, "checks", "wrap_%s.json" % TYPE), "w") as f:
    json.dump(report, f, indent=1)

# --- pictures ----------------------------------------------------------------------------------------------------------
def mat(name, rgba):
    m = bpy.data.materials.new(name)
    m.diffuse_color = rgba
    return m


def frozen(name, keyval, posed_too, x):
    """A static copy of the base, its key at keyval, in the fitted pose or at rest."""
    key.value = keyval
    for pb in rig.pose.bones:
        pb.matrix_basis  # noqa
    saved = {pb.name: tuple(pb.rotation_euler) for pb in rig.pose.bones}
    if not posed_too:
        for pb in rig.pose.bones:
            pb.rotation_euler = (0, 0, 0)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(base.evaluated_get(dg), depsgraph=dg)
    me.transform(base.matrix_world)
    for pb in rig.pose.bones:
        pb.rotation_euler = saved[pb.name]
    o = bpy.data.objects.new(name, me)
    scene.collection.objects.link(o)
    o.location.x = x
    return o


blue, clay = mat("blue", (0.55, 0.65, 0.85, 1)), mat("clay", (0.85, 0.6, 0.5, 1))
wire = mat("wire", (0.05, 0.05, 0.08, 1))
shots = [frozen("base_rest", 0.0, False, -1.35), frozen("wrapped_rest", 1.0, False, -0.45),
         frozen("wrapped_posed", 1.0, True, 0.45)]
t_copy = tripo.copy(); t_copy.data = tripo.data.copy(); scene.collection.objects.link(t_copy); t_copy.location.x = 1.35
for o in shots:
    o.data.materials.append(blue)
t_copy.data.materials.clear(); t_copy.data.materials.append(clay)
base.hide_render = True
tripo.hide_render = True
rig.hide_render = True
# wire over the wrapped one at rest
w_obj = shots[1].copy(); w_obj.data = shots[1].data.copy(); scene.collection.objects.link(w_obj)
w_obj.data.materials.clear(); w_obj.data.materials.append(wire)
wm = w_obj.modifiers.new("wire", "WIREFRAME"); wm.thickness = 0.0012; wm.use_replace = True

scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "MATERIAL"
scene.render.resolution_x, scene.render.resolution_y = 2000, 900
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
scene.collection.objects.link(cam)
scene.camera = cam
mid_z = ground + height / 2


def shoot(fname, loc, rot, scale, res):
    cam.location, cam.rotation_euler, cam.data.ortho_scale = loc, rot, scale
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.filepath = os.path.join(HERE, "checks", fname)
    bpy.ops.render.render(write_still=True)


shoot("wrap_%s_front.png" % TYPE, (0, -10, mid_z), (1.5708, 0, 0), 3.7, (2000, 900))
for o in shots + [t_copy, w_obj]:
    o.rotation_euler.z = -1.5708
shoot("wrap_%s_side.png" % TYPE, (0, -10, mid_z), (1.5708, 0, 0), 3.7, (2000, 900))
for o in shots + [t_copy, w_obj]:
    o.rotation_euler.z = 0
# torso close-up of the wire
shoot("wrap_%s_wire.png" % TYPE, (-0.45, -10, ground + 0.62 * height), (1.5708, 0, 0), 0.75, (1000, 1000))

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "build", "wrap_%s.blend" % TYPE))
log("done")
