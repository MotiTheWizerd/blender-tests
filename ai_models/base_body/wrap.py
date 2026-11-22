"""Her skin the rest of the way onto a Tripo body: from the slider fit (millimetres off) onto its surface, kept as
her rest shape, so the body's muscle and form are in her mesh and not only in a normal map over a smooth one.

    blender -b -P wrap.py -- <tripo file> <name>

1. Her at the sliders in checks/fit_<name>.json, settled on the mixamo_unity rig: the bones stand where the slider
   fit put them, and the wrap moves only the skin (s1026: a wrap after a pose fit by surface alone put the knees
   3 cm off the bones).
2. The Tripo body at her height, its trunk over hers; her bones turned until she lies on it (pose.fit).
3. The wrap, in that pose: each vertex pulled to the nearest Tripo surface that faces its way, the pull smoothed
   over the mesh as a membrane, stiff first and looser each round. Free of any pull, following what they hang on:
   the head and neck (the face is the bust's), the fingers and toes (Tripo's are fused), the breasts (their own
   kind, one chest for every type).
4. Unposed through the inverse of each vertex's skinning: her rest shape. Kept as a delta on the slider fit, so
   the face's sliders and the controls go on as before; and every bone's head and tail move as the skin around them
   moved, so the joints keep their place in their limbs (her.apply_wrap puts both on).

Pass bar, logged and in the json: her body's surface to the Tripo one at the median under GAP_MM, and no knee or
elbow further from its limb's centre than it stood after the slider fit by more than OFF_CENTRE_MM.

Writes build/wrap_<name>.npy (the delta, her local frame), checks/wrap_<name>.json (the pose, the gaps, the joints,
the bones' moves, the verdict), checks/wrap_<name>_{front,side,wire}.png, build/wrap_<name>.blend.
"""
import bpy, json, os, sys, time
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

ARGS = sys.argv[sys.argv.index("--") + 1:]
SOURCE, NAME = ARGS[0], ARGS[1]
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from her import create, settle  # noqa: E402
from pose import place, fit, posed, Skinning, world_points, off_centre, JOINTS, import_tripo  # noqa: E402

ROUNDS = 24
FAR = 0.08  # m: a Tripo surface further than this is not hers
FACING = 0.3  # cosine: a Tripo surface facing less than this her way is the wrong surface
STIFF, LOOSE = 0.05, 2.0  # the data's pull against the membrane, first round and last
SMOOTH = 60  # relaxations of the membrane a round
FREE = ["Head", "Neck", "Jaw", "LeftEye", "RightEye", "LeftOrbicularis", "RightOrbicularis",
        "LeftHandIndex", "LeftHandMiddle", "LeftHandRing", "LeftHandPinky", "LeftHandThumb",
        "RightHandIndex", "RightHandMiddle", "RightHandRing", "RightHandPinky", "RightHandThumb",
        "LeftToeBase", "RightToeBase", "LeftBreast", "RightBreast"]
NEAR = 24  # skin vertices whose mean move a bone's head or tail takes
GAP_MM, OFF_CENTRE_MM = 1.0, 5.0
T0 = time.time()


def log(*a):
    print("[%6.1fs]" % (time.time() - T0), *a, flush=True)


bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
os.makedirs(os.path.join(HERE, "build"), exist_ok=True)

# --- 1. her ----------------------------------------------------------------------------------------------------------
fit_values = json.load(open(os.path.join(HERE, "checks", "fit_%s.json" % NAME)))["values"]
base, rig = create(fit_values)
settle(base, rig)
base.name, rig.name = "her " + NAME, "rig " + NAME
N = len(base.data.vertices)
rest_world = world_points(base)
skinning = Skinning(base, rig)
free = np.clip(skinning.weight_of(FREE), 0, 1)
log("her: %d vertices, %d free of pull" % (N, int((free > 0.5).sum())))

# --- 2. the Tripo body, her pose on it --------------------------------------------------------------------------------
tripo = import_tripo(SOURCE, "Tripo " + NAME)
T, tripo_bvh, T_sample, placement = place(tripo, rest_world)
log("tripo: %d vertices, scaled %.4f" % (len(T), placement["scale"]))
best, pose_angles = fit(base, rig, tripo_bvh, T_sample, log=log)
P, _ = posed(base)
gap0 = np.array([tripo_bvh.find_nearest(Vector(p))[3] for p in P])
log("posed on the slider fit: her surface to the Tripo one %.1f mm median, %.1f p90, %.1f max" % tuple(np.percentile(gap0, [50, 90, 100]) * 1000))

# --- 3. the wrap ---------------------------------------------------------------------------------------------------------
edges = np.empty(len(base.data.edges) * 2, dtype=np.int64)
base.data.edges.foreach_get("vertices", edges)
edges = edges.reshape(-1, 2)
deg = np.bincount(edges.ravel(), minlength=N).astype(float)
faces = [list(f.vertices) for f in base.data.polygons]


def neighbour_sum(U):
    S = np.zeros_like(U)
    np.add.at(S, edges[:, 0], U[edges[:, 1]])
    np.add.at(S, edges[:, 1], U[edges[:, 0]])
    return S


def normals(co):
    tmp = bpy.data.meshes.new("tmp")
    tmp.from_pydata(co.tolist(), [], faces)
    n = np.empty(N * 3)
    tmp.vertices.foreach_get("normal", n)
    bpy.data.meshes.remove(tmp)
    return n.reshape(N, 3)


start = P.copy()
for r in range(ROUNDS):
    nb = normals(P)
    D = np.zeros((N, 3))
    w = np.zeros(N)
    for i in range(N):
        hit = tripo_bvh.find_nearest(Vector(P[i]))
        if hit[0] is None or hit[3] > FAR or np.dot(nb[i], hit[1]) < FACING:
            continue
        D[i] = np.array(hit[0]) - P[i]
        w[i] = 1.0
    w *= 1.0 - free
    alpha = STIFF * ((LOOSE / STIFF) ** (r / (ROUNDS - 1)))
    U = D * w[:, None]
    for _ in range(SMOOTH):
        U = (alpha * w[:, None] * D + neighbour_sum(U)) / (alpha * w + deg)[:, None]
    P = P + U
    gap = np.linalg.norm(D[w > 0], axis=1)
    if r % 4 == 3 or r == ROUNDS - 1:
        log("  round %2d: alpha %.2f, %d pulled, their gap %.2f mm median, %.1f p95" % (r, alpha, int((w > 0).sum()), 1000 * np.median(gap), 1000 * np.percentile(gap, 95)))

# --- 4. unposed, as a delta on the slider fit ----------------------------------------------------------------------------
roundtrip = np.abs(skinning.unpose(start) - rest_world).max()
rest_shape = skinning.unpose(P)
delta_world = rest_shape - rest_world
R_inv = np.array(base.matrix_world.inverted())[:3, :3]
delta_local = delta_world @ R_inv.T
np.save(os.path.join(HERE, "build", "wrap_%s.npy" % NAME), delta_local.astype(np.float32))
moved = np.linalg.norm(delta_world, axis=1)
log("unpose round trip %.3f mm; the wrap moves her %.1f mm median, %.1f p95, %.1f max" % (1000 * roundtrip, *np.percentile(moved, [50, 95, 100]) * 1000))

# the bones ride the same field: each head and tail moves as the NEAR nearest skin vertices moved on average, so a
# joint keeps its place in its limb (s1026: the skin wrapped onto the Tripo knee while the bone stayed, 3 cm off)
tree = KDTree(N)
for i in range(N):
    tree.insert(Vector(rest_world[i]), i)
tree.balance()


def move_at(p):
    return delta_world[[idx for _, idx, _ in tree.find_n(Vector(p), NEAR)]].mean(0)


bone_moves, H, H_after = {}, {}, {}
for b in rig.data.bones:
    head, tail = np.array(rig.matrix_world @ b.head_local), np.array(rig.matrix_world @ b.tail_local)
    mh, mt = move_at(head), move_at(tail)
    bone_moves[b.name] = {"head": [round(float(v), 5) for v in mh], "tail": [round(float(v), 5) for v in mt]}
    H[b.name], H_after[b.name] = head, head + mh
bone_moved = np.array([np.linalg.norm(m["head"]) for m in bone_moves.values()])
log("the bones move with the skin: %.1f mm median, %.1f max (%s)" % (np.median(bone_moved) * 1000, bone_moved.max() * 1000,
                                                                      max(bone_moves, key=lambda n: np.linalg.norm(bone_moves[n]["head"]))))

# --- the measures ------------------------------------------------------------------------------------------------------
# her posed surface, wrapped, to the Tripo body: from the Tripo side (every Tripo vertex to her), body region only
tmp = bpy.data.meshes.new("wrapped posed")
tmp.from_pydata(P.tolist(), [], faces)
wrapped_posed = bpy.data.objects.new("wrapped posed", tmp)
scene.collection.objects.link(wrapped_posed)
bpy.context.view_layer.update()
bvh = BVHTree.FromObject(wrapped_posed, bpy.context.evaluated_depsgraph_get())
hits = [bvh.find_nearest(Vector(p)) for p in T]
dist = np.array([h[3] for h in hits])
region = np.array([free[faces[h[2]][0]] > 0.5 for h in hits])
body_gap = dist[~region]
# her own vertices, pulled ones, to the Tripo surface
own = np.array([tripo_bvh.find_nearest(Vector(p))[3] for p in P])[(free < 0.5)]
# the joints in their limbs: on the slider fit, and on the wrapped shape with the bones moved along
joints = {}
for j, a, b, s in JOINTS:
    before_mm = off_centre(rest_world, H["mixamorig:" + j], H["mixamorig:" + a], H["mixamorig:" + b], s)
    after_mm = off_centre(rest_shape, H_after["mixamorig:" + j], H_after["mixamorig:" + a], H_after["mixamorig:" + b], s)
    joints[j] = {"slider_fit": round(before_mm * 1000, 1), "wrapped": round(after_mm * 1000, 1)}
worst_joint = max(v["wrapped"] - v["slider_fit"] for v in joints.values())
verdict = {"gap_median_mm": round(float(np.median(body_gap)) * 1000, 2), "gap_bar_mm": GAP_MM,
           "joint_moved_off_centre_mm": round(worst_joint, 1), "joint_bar_mm": OFF_CENTRE_MM}
verdict["pass"] = bool(verdict["gap_median_mm"] <= GAP_MM and worst_joint <= OFF_CENTRE_MM)
log("Tripo to her wrapped surface (body): %.2f mm median, %.1f p95, %.1f p99, %.1f max; head, hands, feet %.1f median" % (
    *np.percentile(body_gap, [50, 95, 99, 100]) * 1000, np.median(dist[region]) * 1000))
log("her pulled vertices to the Tripo surface: %.2f mm median, %.1f p95" % tuple(np.percentile(own, [50, 95]) * 1000))
log("joints off their limb's centre (mm, slider fit -> wrapped): %s" % {k: (v["slider_fit"], v["wrapped"]) for k, v in joints.items()})
log("%s: gap %.2f mm (bar %.1f), joints moved off centre by %.1f mm at most (bar %.1f)" % (
    "PASS" if verdict["pass"] else "FAIL", verdict["gap_median_mm"], GAP_MM, worst_joint, OFF_CENTRE_MM))
with open(os.path.join(HERE, "checks", "wrap_%s.json" % NAME), "w") as f:
    json.dump({"name": NAME, "source": os.path.basename(SOURCE), "pose_fit_cost": best, "pose": pose_angles, "tripo_placement": placement,
               "slider_fit_gap_mm": {"median": round(float(np.median(gap0)) * 1000, 2), "p90": round(float(np.percentile(gap0, 90)) * 1000, 1)},
               "tripo_to_wrapped_mm_body": {"median": round(float(np.median(body_gap)) * 1000, 2), "p95": round(float(np.percentile(body_gap, 95)) * 1000, 2),
                                            "p99": round(float(np.percentile(body_gap, 99)) * 1000, 2), "max": round(float(body_gap.max()) * 1000, 2)},
               "wrap_moves_mm": {"median": round(float(np.median(moved)) * 1000, 2), "p95": round(float(np.percentile(moved, 95)) * 1000, 2), "max": round(float(moved.max()) * 1000, 2)},
               "unpose_roundtrip_mm": round(float(roundtrip) * 1000, 4), "joints_off_centre_mm": joints, "verdict": verdict,
               "bones": bone_moves}, f, indent=1)

# --- the pictures: her slider fit, her wrapped, the Tripo body, at rest side by side; a wire of the wrapped torso ------
bpy.data.objects.remove(wrapped_posed)
for pb in rig.pose.bones:
    pb.rotation_euler = (0, 0, 0)
bpy.context.view_layer.update()


def material(name, rgba):
    m = bpy.data.materials.new(name)
    m.diffuse_color = rgba
    return m


def still(name, co_world, x, mat):
    me = bpy.data.meshes.new(name)
    me.from_pydata(co_world.tolist(), [], faces)
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(mat)
    o = bpy.data.objects.new(name, me)
    scene.collection.objects.link(o)
    o.location.x = x
    return o


blue, clay, dark = material("her", (0.55, 0.65, 0.85, 1)), material("tripo", (0.85, 0.6, 0.5, 1)), material("wire", (0.05, 0.05, 0.08, 1))
shots = [still("slider fit", rest_world, -1.0, blue), still("wrapped", rest_shape, 0.0, blue)]
for p in tripo.data.polygons:
    p.use_smooth = True
tripo.data.materials.clear()
tripo.data.materials.append(clay)
tripo.location.x = 1.0
wire = still("wrapped wire", rest_shape, 0.0, dark)
wm = wire.modifiers.new("wire", "WIREFRAME")
wm.thickness, wm.use_replace = 0.0012, True
wire.hide_render = True
base.hide_render = rig.hide_render = True
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "MATERIAL"
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
scene.collection.objects.link(cam)
scene.camera = cam
ground, height = rest_world[:, 2].min(), rest_world[:, 2].max() - rest_world[:, 2].min()


def shoot(fname, loc, rot, scale, res):
    cam.location, cam.rotation_euler, cam.data.ortho_scale = loc, rot, scale
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.filepath = os.path.join(HERE, "checks", fname)
    bpy.ops.render.render(write_still=True)


shoot("wrap_%s_front.png" % NAME, (0, -10, ground + height / 2), (1.5708, 0, 0), 3.2, (1800, 1000))
for o in shots + [tripo]:
    o.rotation_euler.z = -1.5708
shoot("wrap_%s_side.png" % NAME, (0, -10, ground + height / 2), (1.5708, 0, 0), 3.2, (1800, 1000))
for o in shots + [tripo]:
    o.rotation_euler.z = 0
wire.hide_render = False
shots[1].hide_render = True
shoot("wrap_%s_wire.png" % NAME, (0, -10, ground + 0.62 * height), (1.5708, 0, 0), 0.8, (1000, 1000))
shots[1].hide_render = wire.hide_render = False
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "build", "wrap_%s.blend" % NAME))
log("done")
