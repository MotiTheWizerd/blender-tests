"""MPFB's own sliders set to match a Tripo body type, so the type is MPFB's body and its rig refits with it.

    blender -b -P fit_macros.py -- <tripo file> <type name>

Both bodies at 1.70 m, feet on the ground. Each is measured as a profile: the trunk's width and depth at twenty
levels from the crotch to under the armpits, each leg's from the ankle to the crotch, each arm's depth from the
forearm to the armpit, and how far the breasts stand forward of the breastbone level by level (BREAST_WEIGHT).
MPFB's female (gender 0) is then fitted by damped Gauss-Newton over its macro sliders (weight, muscle,
proportions, cupsize, firmness, 0 to 1) and the detail sliders in DETAIL (-1 to 1, left and right as one), the
profile's squared differences the loss, the detail sliders held near 0 by RIDGE. Each is one of MPFB's own
targets, so the rig refits to the result.

Writes checks/fit_<type>.json (the values, the profile before and after) and checks/fit_<type>_front/side.png
(MPFB left, Tripo right, both overlaid in the middle).
"""
import bpy, json, os, sys, time
import numpy as np
from bl_ext.blender_org.mpfb.services.humanservice import HumanService
from bl_ext.blender_org.mpfb.services.targetservice import TargetService
from bl_ext.blender_org.mpfb.services.locationservice import LocationService
from bl_ext.blender_org.mpfb.entities.objectproperties import HumanObjectProperties

ARGS = sys.argv[sys.argv.index("--") + 1:]
SOURCE, TYPE = ARGS[0], ARGS[1]
HERE = os.path.dirname(os.path.abspath(__file__))
HEIGHT = 1.70
MACRO = ["weight", "muscle", "proportions", "cupsize", "firmness"]
# detail sliders: a target pair <name>-decr / -incr (or the ends given) under data/targets/<folder>; "l-" and "r-"
# both when sided
DETAIL = [("torso", "measure-bust-circ"), ("torso", "measure-underbust-circ"), ("torso", "measure-waist-circ"),
          ("torso", "measure-hips-circ"), ("torso", "torso-scale-depth"), ("torso", "torso-scale-horiz"),
          ("torso", "torso-vshape"), ("hip", "hip-scale-depth"), ("hip", "hip-scale-horiz"),
          ("stomach", "stomach-pregnant"), ("buttocks", "buttocks-volume"),
          ("legs", "upperleg-fat"), ("legs", "upperleg-muscle"), ("legs", "upperleg-scale-depth"),
          ("legs", "upperleg-scale-horiz"), ("legs", "lowerleg-fat"), ("legs", "lowerleg-muscle"),
          ("legs", "lowerleg-scale-depth"), ("legs", "lowerleg-scale-horiz"), ("legs", "measure-knee-circ"),
          ("arms", "upperarm-fat"), ("arms", "upperarm-muscle"), ("arms", "lowerarm-fat"),
          ("arms", "lowerarm-muscle"), ("breast", "breast-volume-vert", ("down", "up"))]
BREAST_LEVELS = 12
BREAST_WEIGHT = 3.0  # the breasts' entries count this much more: few, small numbers that make the figure
RIDGE = 0.004  # m of profile error a detail slider at 1 is worth: keeps them from fighting each other
T0 = time.time()


def log(*a):
    print("[%6.1fs]" % (time.time() - T0), *a, flush=True)


bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# --- the Tripo body --------------------------------------------------------------------------------------------------
if SOURCE.endswith(".glb"):
    bpy.ops.import_scene.gltf(filepath=SOURCE)
else:
    bpy.ops.import_scene.fbx(filepath=SOURCE)
tripo = [o for o in scene.objects if o.type == "MESH"][0]
bpy.context.view_layer.update()
T = np.array([tripo.matrix_world @ v.co for v in tripo.data.vertices])


def normalised(P):
    """Feet on the ground, centred, HEIGHT tall."""
    lo, hi = P.min(0), P.max(0)
    c = np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])
    return (P - c) * (HEIGHT / (hi[2] - lo[2]))


T = normalised(T)

# --- the profile ---------------------------------------------------------------------------------------------------
# A cross-section is where the mesh's edges cross a level. Its points fall into pieces (trunk, legs, arms) by the
# mesh itself: two crossing edges of one face are one piece.
TOP = 0.69  # the trunk's top as a share of height, under the armpits (a heavy body's arms join it by 0.72)
BUST = 0.76  # the chest's reach is looked for up to here: past the nipples, the arms merged in no further forward


class Mesh:
    def __init__(self, obj, keep=None):
        me = obj.data
        E = np.empty(len(me.edges) * 2, dtype=np.int64)
        me.edges.foreach_get("vertices", E)
        self.E = E.reshape(-1, 2)
        le = np.empty(len(me.loops), dtype=np.int64)
        me.loops.foreach_get("edge_index", le)
        start = np.empty(len(me.polygons), dtype=np.int64)
        me.polygons.foreach_get("loop_start", start)
        total = np.empty(len(me.polygons), dtype=np.int64)
        me.polygons.foreach_get("loop_total", total)
        self.face_edges = le
        self.face_of_loop = np.repeat(np.arange(len(start)), total)
        if keep is not None:
            ok = keep[self.E[:, 0]] & keep[self.E[:, 1]]
            self.E[~ok] = 0  # a dropped edge never crosses: both ends one vertex


def section(P, mesh, z):
    """The pieces of the section at z, each an array of (x, y) points."""
    E = mesh.E
    a, b = P[E[:, 0], 2] - z, P[E[:, 1], 2] - z
    cross = a * b < 0
    idx = np.where(cross)[0]
    if not len(idx):
        return []
    slot = -np.ones(len(E), dtype=np.int64)
    slot[idx] = np.arange(len(idx))
    parent = np.arange(len(idx))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    loops = slot[mesh.face_edges] >= 0
    faces, edges = mesh.face_of_loop[loops], slot[mesh.face_edges[loops]]
    order = np.argsort(faces, kind="stable")
    faces, edges = faces[order], edges[order]
    same = np.where(faces[1:] == faces[:-1])[0]
    for i in same:
        ra, rb = root(edges[i]), root(edges[i + 1])
        if ra != rb:
            parent[ra] = rb
    A, B = P[E[idx, 0]], P[E[idx, 1]]
    t = ((z - A[:, 2]) / (B[:, 2] - A[:, 2]))[:, None]
    pts = (A + t * (B - A))[:, :2]
    roots = np.array([root(i) for i in range(len(idx))])
    return [pts[roots == r] for r in np.unique(roots) if (roots == r).sum() >= 6]


def size(piece):
    return [piece[:, 0].max() - piece[:, 0].min(), piece[:, 1].max() - piece[:, 1].min()]


def crotch(P, E):
    """Coming down from the waist, the first level at which no piece spans x = 0: the legs part there. (From
    below, a heavy body's inner thighs touch under the crotch and would pass for it.)"""
    for z in np.arange(0.6, 0.35, -0.002) * HEIGHT:
        if not any(p[:, 0].min() < 0 < p[:, 0].max() for p in section(P, E, z)):
            return z
    raise RuntimeError("no crotch")


def leg(pieces, side):
    """The leg on one side: the piece nearest the middle on that side, or its half when the thighs touch."""
    near = []
    for p in pieces:
        if p[:, 0].min() < 0 < p[:, 0].max():
            p = p[side * p[:, 0] > 0]
        if len(p) >= 6 and side * p[:, 0].mean() > 0:
            near.append(p)
    return min(near, key=lambda p: abs(p[:, 0].mean())) if near else None


def profile(P, E):
    c = crotch(P, E)
    out = []
    # the trunk, crotch to under the armpits: the piece across x = 0
    for f in np.arange(0.02, 1.0001, 0.05):
        z = c + f * (TOP * HEIGHT - c)
        trunk = [p for p in section(P, E, z) if p[:, 0].min() < 0 < p[:, 0].max()]
        out += size(trunk[0]) if trunk else [0.0, 0.0]
    # each leg, ankle to just under the crotch
    for side in (1, -1):
        for f in np.arange(0.0, 1.0001, 0.1):
            z = 0.06 * HEIGHT + f * (c - 0.015 - 0.06 * HEIGHT)
            p = leg(section(P, E, z), side)
            out += size(p) if p is not None else [0.0, 0.0]
    # each arm, forearm to armpit: the piece farthest out on its side, its depth alone (its width on a level
    # grows with the arm's slant, which differs between the two bodies)
    for side in (1, -1):
        for z in np.arange(0.58, TOP + 0.0001, 0.02) * HEIGHT:
            arms = [p for p in section(P, E, z) if side * p[:, 0].min() > 0]
            out.append(size(max(arms, key=lambda p: abs(p[:, 0].mean())))[1] if arms else 0.0)
    # the breasts: at each level from the underbust up, how far the chest stands forward of the breastbone
    for z in np.linspace(c + 0.70 * (TOP * HEIGHT - c), BUST * HEIGHT, BREAST_LEVELS):
        trunk = [p for p in section(P, E, z) if p[:, 0].min() < 0 < p[:, 0].max()]
        if not trunk:
            out.append(0.0)
            continue
        p = trunk[0]
        front = p[p[:, 1] < np.median(p[:, 1])]
        mid = front[np.abs(front[:, 0]) < 0.015]
        out.append((-front[:, 1].min()) - (-mid[:, 1].min()) if len(mid) else 0.0)
    return np.array(out), c


TE = Mesh(tripo)
TP, tc = profile(T, TE)
log("tripo", len(T), "vertices, crotch", round(tc, 3))

# --- MPFB ----------------------------------------------------------------------------------------------------------
macro = TargetService.get_default_macro_info_dict()
macro.update({"gender": 0.0, "age": 0.5})
macro["race"] = {"asian": 0.0, "caucasian": 1.0, "african": 0.0}
base = HumanService.create_human(mask_helpers=True, macro_detail_dict=macro)
base.name = "mpfb"
mask = [m for m in base.modifiers if m.type == "MASK"][0]
group = base.vertex_groups[mask.vertex_group].index
# the mask keeps its group's vertices, or all but them when inverted
grouped = np.array([any(g.group == group for g in v.groups) for v in base.data.vertices])
body = ~grouped if mask.invert_vertex_group else grouped
log("mpfb", int(body.sum()), "body vertices of", len(grouped), "(mask group", mask.vertex_group + ")")
N = len(base.data.vertices)
ME = Mesh(base, keep=body)

# each detail slider: its (decr keys, incr keys), loaded at weight 0
TARGETS = LocationService.get_mpfb_data("targets")
detail_keys = []
for folder, name, *ends in DETAIL:
    ends = ends[0] if ends else ("decr", "incr")
    sides = ["l-", "r-"] if os.path.exists(os.path.join(TARGETS, folder, "l-%s-%s.target.gz" % (name, ends[1]))) else [""]
    pair = []
    for end in ends:
        keys = []
        for side in sides:
            key = "fit-%s%s-%s" % (side, name, end)
            TargetService.load_target(base, os.path.join(TARGETS, folder, "%s%s-%s.target.gz" % (side, name, end)),
                                      weight=0.0, name=key)
            keys.append(key)
        pair.append(keys)
    detail_keys.append(pair)
log(len(DETAIL), "detail sliders loaded")

NM = len(MACRO)
LO = np.array([0.0] * NM + [-1.0] * len(DETAIL))
HI = np.array([1.0] * NM + [1.0] * len(DETAIL))
_macro_now = [None]


def mpfb_points(x):
    if _macro_now[0] is None or np.any(_macro_now[0] != x[:NM]):
        for k, v in zip(MACRO, x[:NM]):
            HumanObjectProperties.set_value(k, float(v), entity_reference=base)
        TargetService.reapply_macro_details(base, remove_zero_weight_targets=False)
        _macro_now[0] = x[:NM].copy()
    blocks = base.data.shape_keys.key_blocks
    for (decr, incr), v in zip(detail_keys, x[NM:]):
        for k in decr:
            blocks[k].value = max(-v, 0.0)
        for k in incr:
            blocks[k].value = max(v, 0.0)
    basis = np.empty(N * 3)
    blocks[0].data.foreach_get("co", basis)
    basis = basis.reshape(N, 3)
    P = basis.copy()
    tmp = np.empty(N * 3)
    for kb in blocks[1:]:
        if kb.value and not kb.mute:
            kb.data.foreach_get("co", tmp)
            P += kb.value * (tmp.reshape(N, 3) - basis)
    W = np.array(base.matrix_world)
    P = P @ W[:3, :3].T + W[:3, 3]
    lo, hi = P[body].min(0), P[body].max(0)
    c = np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])
    return (P - c) * (HEIGHT / (hi[2] - lo[2]))


WEIGHTS = np.ones(len(TP))
WEIGHTS[-BREAST_LEVELS:] = BREAST_WEIGHT


def residual(x):
    return np.concatenate([WEIGHTS * (profile(mpfb_points(x), ME)[0] - TP), RIDGE * x[NM:]])


def rms_mm(x):
    d = profile(mpfb_points(x), ME)[0] - TP
    return float(np.sqrt(np.mean(d * d))) * 1000


x = np.array([0.5] * NM + [0.0] * len(DETAIL))
before = profile(mpfb_points(x), ME)[0]
r = residual(x)
mu = 1e-4
log("start", round(rms_mm(x), 2), "mm")
for it in range(8):
    J = np.empty((len(r), len(x)))
    for j in range(len(x)):
        h = 0.05 if x[j] + 0.05 <= HI[j] else -0.05
        xj = x.copy()
        xj[j] += h
        J[:, j] = (residual(xj) - r) / h
    while True:
        step = np.linalg.solve(J.T @ J + mu * np.eye(len(x)), -J.T @ r)
        trial = np.clip(x + step, LO, HI)
        rt = residual(trial)
        if rt @ rt < r @ r:
            x, r, mu = trial, rt, mu / 3
            break
        mu *= 4
        if mu > 1e3:
            break
    log("iteration", it, round(rms_mm(x), 2), "mm")
    if mu > 1e3:
        break

values = {k: round(float(v), 3) for k, v in zip(MACRO, x[:NM])}
values.update({name: round(float(v), 3) for (_, name, *_e), v in zip(DETAIL, x[NM:])})
best = rms_mm(x)
log("fit", values)
M = mpfb_points(x)
after = profile(M, ME)[0]
os.makedirs(os.path.join(HERE, "checks"), exist_ok=True)
with open(os.path.join(HERE, "checks", "fit_%s.json" % TYPE), "w") as f:
    json.dump({"type": TYPE, "source": os.path.basename(SOURCE), "rms_mm": round(best, 2),
               "values": {k: round(v, 3) for k, v in values.items()},
               "profile": {"tripo": np.round(TP, 4).tolist(), "start": np.round(before, 4).tolist(),
                           "fit": np.round(after, 4).tolist()}}, f, indent=1)

# --- pictures (the base stands as fitted: mpfb_points(x) set its sliders last) --------------------------------------
dg = bpy.context.evaluated_depsgraph_get()
baked = bpy.data.meshes.new_from_object(base.evaluated_get(dg))
base.modifiers.clear()
base.shape_key_clear()
base.data = baked
for o in (base, tripo):
    o.parent = None
    P = np.array([o.matrix_world @ v.co for v in o.data.vertices])
    o.matrix_world.identity()
    o.data.vertices.foreach_set("co", normalised(P).ravel())


def material(name, rgba):
    m = bpy.data.materials.new(name)
    m.diffuse_color = rgba
    return m


over_b = base.copy(); over_b.data = base.data.copy(); scene.collection.objects.link(over_b)
over_t = tripo.copy(); over_t.data = tripo.data.copy(); scene.collection.objects.link(over_t)
for o, m in ((base, material("b", (0.55, 0.65, 0.85, 1))), (over_b, material("b2", (0.55, 0.65, 0.85, 1))),
             (tripo, material("t", (0.85, 0.6, 0.5, 1))), (over_t, material("t2", (0.85, 0.6, 0.5, 1)))):
    o.data.materials.clear()
    o.data.materials.append(m)
base.location.x, tripo.location.x = -0.9, 0.9
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "MATERIAL"
scene.display.shading.show_xray = True
scene.display.shading.xray_alpha = 0.6
scene.render.resolution_x, scene.render.resolution_y = 1800, 1000
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
cam.data.ortho_scale = 3.0
scene.collection.objects.link(cam)
scene.camera = cam
cam.location, cam.rotation_euler = (0, -10, 0.85), (1.5708, 0, 0)
scene.render.filepath = os.path.join(HERE, "checks", "fit_%s_front.png" % TYPE)
bpy.ops.render.render(write_still=True)
for o in (base, tripo, over_b, over_t):
    o.rotation_euler.z = -1.5708
scene.render.filepath = os.path.join(HERE, "checks", "fit_%s_side.png" % TYPE)
bpy.ops.render.render(write_still=True)
log("done")
