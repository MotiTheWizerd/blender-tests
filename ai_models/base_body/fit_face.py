"""MPFB's face sliders set to match a Tripo head, so the face is MPFB's own (its sliders, its rig, its expressions)
with this head's shape.

    blender -b -P fit_face.py -- <tripo bust> <face name>

The MPFB female at the base type's fitted sliders (checks/fit_<base>.json), every face target under FOLDERS loaded as
a slider (a decr/incr pair one slider from -1 to 1, left and right as one; a one-sided shape 0 to 1). The Tripo bust
is scaled onto her head by chin to crown, as fit_macros sized the head from the Tripo body (the bust says nothing
about the head's size against the body, and its scale stays put: let float, it followed the head-shrinking sliders
down and she lost a tenth of her head's height and a sixth of its width), and moved onto it with the sliders (a
translation; head-scale-vert and head-trans stay out). Landmarks in the bust's paint: the pupils (the darkest
points above the nose), each eye's opening (the sclera flooded from the pupil), the mouth's corners (the dark line
between the lips); on her, the lid rims and the lip line are the vertices her head island shares with its eye cups
and mouth pocket. Gauss-Newton: every head vertex to the bust's surface along its normal there (a hit whose surface
faces more than STRAY degrees from hers dropped), the landmarks pulled together, the sliders held near 0 by RIDGE.

Writes checks/face_<name>.json (the sliders, the bust's scale and shift, the landmarks, the distances) and
checks/face_<name>_{front,side}.png (her head in blue over the bust in orange, landmarks as dots).
"""
import bpy, json, os, sys, time
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from bl_ext.blender_org.mpfb.services.targetservice import TargetService
from bl_ext.blender_org.mpfb.services.locationservice import LocationService

ARGS = sys.argv[sys.argv.index("--") + 1:]
SOURCE, NAME = ARGS[0], ARGS[1]
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
from face import profile  # noqa: E402
from her import create  # noqa: E402

TYPES = json.load(open(os.path.join(HERE, "types.json")))
BASE = TYPES["base"]
# the face's sliders: every target in these folders but the ones that place or size the whole head or neck against
# the body (the bust cannot say), and age
FOLDERS = ["head", "forehead", "eyebrows", "eyes", "nose", "mouth", "chin", "cheek", "ears", "neck"]
LEAVE = ("head-scale-vert", "head-trans-", "head-fat", "head-age", "neck-trans-", "neck-scale-vert", "measure-neck-height")
PAIRS = [("decr", "incr"), ("down", "up"), ("in", "out"), ("backward", "forward"), ("concave", "convex"),
         ("compress", "uncompress")]
RIDGE = 0.03  # a slider at 1 is worth this much surface error (3000 surface terms at 2 mm sum to 0.012): keeps them few
STRAY = 60.0  # degrees: a bust surface facing further from hers than this is the wrong surface
# her chin is read with her neck in (everything above NECK of her height, as fit_macros reads it): the head island
# ends right under the chin, and over it alone the profile takes the lip crease for the chin, 3 cm up
NECK = 0.84
LANDMARK = 4.0  # a landmark's pull against one surface point's
PUPIL = 6.0
ITERATIONS = 30
T0 = time.time()


def log(*a):
    print("[%6.1fs]" % (time.time() - T0), *a, flush=True)


bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
TARGETS = LocationService.get_mpfb_data("targets")

# --- 1. her, at the base type's sliders, the face targets loaded at 0 ----------------------------------------------
fit = json.load(open(os.path.join(HERE, "checks", "fit_%s.json" % BASE)))["values"]
base, rig = create(fit)
me = base.data
N = len(me.vertices)
blocks = me.shape_keys.key_blocks
basis = np.empty(N * 3)
blocks[0].data.foreach_get("co", basis)
basis = basis.reshape(N, 3)
P_fit = basis.copy()
tmp = np.empty(N * 3)
for kb in blocks[1:]:
    if kb.value and not kb.mute:
        kb.data.foreach_get("co", tmp)
        P_fit += kb.value * (tmp.reshape(N, 3) - basis)
W = np.array(base.matrix_world)
P_fit = P_fit @ W[:3, :3].T + W[:3, 3]
log("her: %d vertices (helpers in), %d body sliders" % (N, sum(1 for kb in blocks[1:] if kb.value)))


def target_sliders():
    """[(name, [neg keys], [pos keys])] for every face slider: a pair's negative end's keys, both sides, and its
    positive end's; a one-sided shape has no negative keys."""
    sliders = []
    for folder in FOLDERS:
        names = sorted(set(f.split(".target")[0] for f in os.listdir(os.path.join(TARGETS, folder)) if f.endswith(".target.gz")))
        groups = {}
        for n in names:
            side = n[:2] if n[:2] in ("l-", "r-") else ""
            stem = n[len(side):]
            if stem.startswith(LEAVE):
                continue
            groups.setdefault(stem, set()).add(side)
        by_stem = {}
        for stem, sides in groups.items():
            parts = stem.rsplit("-", 1)
            key = parts[0] if len(parts) == 2 and any(parts[1] in p for p in PAIRS) else stem
            by_stem.setdefault(key, []).append((stem, sorted(sides)))
        for key, members in sorted(by_stem.items()):
            ends = {m[0].rsplit("-", 1)[1]: m for m in members} if len(members) == 2 else {}
            pair = next((p for p in PAIRS if set(p) == set(ends)), None)
            if pair:
                neg, pos = ends[pair[0]], ends[pair[1]]
                sliders.append((folder + "/" + key, [s + neg[0] for s in neg[1]], [s + pos[0] for s in pos[1]]))
            else:
                for stem, sides in members:
                    sliders.append((folder + "/" + stem, [], [s + stem for s in sides]))
    return sliders


SLIDERS = target_sliders()
D_pos, D_neg = [], []
for name, neg, pos in SLIDERS:
    folder = name.split("/")[0]
    for keys, store in ((pos, D_pos), (neg, D_neg)):
        delta = np.zeros((N, 3))
        for k in keys:
            key = "face-" + k
            TargetService.load_target(base, os.path.join(TARGETS, folder, k + ".target.gz"), weight=0.0, name=key)
            blocks[key].data.foreach_get("co", tmp)
            delta += tmp.reshape(N, 3) - basis
        store.append(delta @ W[:3, :3].T)
K = len(SLIDERS)
LO = np.array([-1.0 if neg else 0.0 for _, neg, _ in SLIDERS])
HI = np.ones(K)
log("%d face sliders (%d pairs)" % (K, int((LO < 0).sum())))

# the head: her head's UV island (the eye cups and the mouth pocket are islands of their own), body vertices only
mask = [m for m in base.modifiers if m.type == "MASK"][0]
group = base.vertex_groups[mask.vertex_group].index
grouped = np.array([any(g.group == group for g in v.groups) for v in me.vertices])
body = ~grouped if mask.invert_vertex_group else grouped
gi = {g.index: g.name for g in base.vertex_groups}
head_w = np.array([sum(g.weight for g in v.groups if gi[g.group].startswith("mixamorig:Head")) for v in me.vertices])
uv = np.empty(len(me.loops) * 2)
me.uv_layers[0].data.foreach_get("uv", uv)
uv = uv.reshape(-1, 2)
lv = np.empty(len(me.loops), dtype=np.int64)
me.loops.foreach_get("vertex_index", lv)
ltotal = np.array([p.loop_total for p in me.polygons])
lstart = np.array([p.loop_start for p in me.polygons])
parent = np.arange(len(me.loops))


def root(i):
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i


seen = {}
for i in range(len(me.loops)):
    k = (lv[i], round(uv[i, 0], 5), round(uv[i, 1], 5))
    if k in seen:
        parent[root(i)] = root(seen[k])
    else:
        seen[k] = i
for s, n in zip(lstart, ltotal):
    for a in range(s + 1, s + n):
        ra, rb = root(s), root(a)
        if ra != rb:
            parent[ra] = rb
roots = np.array([root(i) for i in range(len(me.loops))])
islands = []
for r in np.unique(roots):
    verts = np.unique(lv[roots == r])
    if body[verts].all() and (head_w[verts] > 0.5).mean() > 0.9:
        islands.append(verts)
islands.sort(key=len, reverse=True)
head = islands[0]
pockets = [v for v in islands[1:] if 100 < len(v) < 1000]
head_set = set(head.tolist())
rims = [np.array(sorted(head_set & set(v.tolist()))) for v in pockets]
rims_z = [P_fit[r, 2].mean() for r in rims]
eye_rims = sorted([r for r, z in zip(rims, rims_z) if z > P_fit[head, 2].mean()], key=lambda r: P_fit[r, 0].mean())
mouth_rim = next(r for r, z in zip(rims, rims_z) if z <= P_fit[head, 2].mean())
log("head island %d vertices, eye rims %s, lip line %d" % (len(head), [len(r) for r in eye_rims], len(mouth_rim)))
# the head's faces, for its vertex normals
head_faces = [list(range(s, s + n)) for s, n in zip(lstart, ltotal) if all(lv[j] in head_set for j in range(s, s + n))]
tri = np.array([[lv[f[0]], lv[f[i]], lv[f[i + 1]]] for f in head_faces for i in range(1, len(f) - 1)])
index_in_head = {v: i for i, v in enumerate(head.tolist())}


def vertex_normals(P):
    n = np.zeros((N, 3))
    fn = np.cross(P[tri[:, 1]] - P[tri[:, 0]], P[tri[:, 2]] - P[tri[:, 0]])
    for c in range(3):
        np.add.at(n, tri[:, c], fn)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


# --- 2. the bust ---------------------------------------------------------------------------------------------------
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
tripo.name = "Tripo " + NAME
tme = tripo.data
T = np.empty(len(tme.vertices) * 3)
tme.vertices.foreach_get("co", T)
T = T.reshape(-1, 3)
tripo_bvh = BVHTree.FromObject(tripo, bpy.context.evaluated_depsgraph_get())
log("bust: %d vertices, %.3f m tall" % (len(T), T[:, 2].max() - T[:, 2].min()))

# its paint, sampled at every loop: the landmarks are in it
image = next(n.image for n in tme.materials[0].node_tree.nodes if n.type == "TEX_IMAGE"
             and any(l.to_socket.name == "Base Color" for l in n.outputs[0].links))
SAMPLE = 2048
image.scale(SAMPLE, SAMPLE)
px = np.empty(SAMPLE * SAMPLE * 4, dtype=np.float32)
image.pixels.foreach_get(px)
px = px.reshape(SAMPLE, SAMPLE, 4)[:, :, :3]
tuv = np.empty(len(tme.loops) * 2)
tme.uv_layers[0].data.foreach_get("uv", tuv)
tuv = tuv.reshape(-1, 2)
tlv = np.empty(len(tme.loops), dtype=np.int64)
tme.loops.foreach_get("vertex_index", tlv)
C = px[np.clip((tuv[:, 1] % 1.0) * SAMPLE, 0, SAMPLE - 1).astype(int), np.clip((tuv[:, 0] % 1.0) * SAMPLE, 0, SAMPLE - 1).astype(int)]
V = C.max(1)
S = (C.max(1) - C.min(1)) / np.maximum(V, 1e-6)
LP = T[tlv]  # each loop's place
t_crown, t_chin_z, t_nose, t_chin = profile(T)
t_head_h = t_crown - t_chin_z
log("bust crown %.3f chin %.3f nose tip %s" % (t_crown, t_chin_z, t_nose.round(3).tolist()))


def clusters(points, link):
    """Groups of points within link of each other (single linkage)."""
    n = len(points)
    par = list(range(n))

    def rt(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i

    for i in range(n):
        d = np.linalg.norm(points - points[i], axis=1)
        for j in np.where(d < link)[0]:
            ri, rj = rt(i), rt(j)
            if ri != rj:
                par[ri] = rj
    rts = np.array([rt(i) for i in range(n)])
    return [np.where(rts == r)[0] for r in np.unique(rts)]


front = LP[:, 1] < (T[:, 1].min() + T[:, 1].max()) / 2
# and seen from in front: the first surface a ray from before the face meets at that point. A bust may carry parts
# inside it (bald human head: 34 loose parts, the dark ones inside the skull and mouth took the pupils 21 cm behind
# the nose tip and the mouth's corners onto the cheeks); paint nobody sees is no landmark.
seen = np.zeros(len(T), dtype=bool)
y0 = T[:, 1].min() - 0.1 * t_head_h
for i in np.unique(tlv[front]):
    hit = tripo_bvh.ray_cast(Vector((T[i, 0], y0, T[i, 2])), Vector((0.0, 1.0, 0.0)))[0]
    seen[i] = hit is not None and hit.y > T[i, 1] - 0.005 * t_head_h
front &= seen[tlv]
log("seen from in front: %d of %d vertices" % (int(seen.sum()), len(T)))
# pupils: the darkest paint above the nose tip, in two clusters mirrored about the middle
band = front & (LP[:, 2] > t_nose[2] + 0.1 * t_head_h) & (LP[:, 2] < t_nose[2] + 0.45 * t_head_h) & (np.abs(LP[:, 0]) < 0.35 * t_head_h)
# each side's own darkest: one pupil a shade lighter than the other (woman4) left none of it in a darkest share taken
# over both
groups, dark = [], np.zeros(0, int)
for side in (LP[:, 0] < 0, LP[:, 0] >= 0):
    near = band & side
    if not near.any():
        continue
    darkest = np.where(near & (V < np.percentile(V[near], 1.5)))[0]
    dark = np.concatenate([dark, darkest])
    groups += [darkest[g] for g in clusters(LP[darkest], 0.02 * t_head_h) if len(g) >= 3]
centres = [LP[g].mean(0) for g in groups]
best, pupils = None, None
for i in range(len(centres)):
    for j in range(i + 1, len(centres)):
        a, b = centres[i], centres[j]
        if a[0] * b[0] < 0 and abs(a[0] + b[0]) < 0.06 * t_head_h and abs(a[2] - b[2]) < 0.04 * t_head_h:
            score = len(groups[i]) + len(groups[j]) - abs(a[0] + b[0]) * 100
            if best is None or score > best:
                best, pupils = score, sorted([a, b], key=lambda p: p[0])
if pupils is None:
    log("no pupils: %d in the band, %d darkest (value under %.3f), groups %s" % (int(band.sum()), len(dark),
        float(np.percentile(V[band], 1.5)), [(len(g), np.round(c, 3).tolist()) for g, c in zip(groups, centres)]))
assert pupils is not None, "no pupils found in the paint"
t_pupils = np.array(pupils)
# each eye's opening: the sclera (light, unsaturated) within reach of the pupil, with the pupil: its width across
t_eye_width = []
for p in t_pupils:
    near = np.linalg.norm(LP - p, axis=1) < 0.11 * t_head_h
    sclera = near & (S < 0.2) & (V > 0.45)
    eye = LP[sclera | (near & (V < np.percentile(V[band], 1.5)))]
    t_eye_width.append(float(eye[:, 0].max() - eye[:, 0].min()))
# the mouth's corners: the dark line between the lips, under the nose, above the chin
band = front & (LP[:, 2] > t_chin_z + 0.08 * t_head_h) & (LP[:, 2] < t_nose[2] - 0.02 * t_head_h) & (np.abs(LP[:, 0]) < 0.3 * t_head_h)
line = np.where(band & (V < np.percentile(V[band], 4)))[0]
groups = sorted([line[g] for g in clusters(LP[line], 0.03 * t_head_h)], key=lambda g: -len(g))
# a closed mouth's line can break where the lips press (bald human head: the biggest piece was its left half), so
# the line is every piece at the biggest's height; a side it misses mirrors the other about the pupils' middle
z0 = LP[groups[0], 2].mean()
mouth = LP[np.concatenate([g for g in groups if abs(LP[g, 2].mean() - z0) < 0.03 * t_head_h])]
mid = t_pupils[:, 0].mean()
left, right = mouth[mouth[:, 0].argmin()], mouth[mouth[:, 0].argmax()]
if left[0] > mid:
    left = right * [-1, 1, 1] + [2 * mid, 0, 0]
if right[0] < mid:
    right = left * [-1, 1, 1] + [2 * mid, 0, 0]
t_mouth = np.array([left, right])
# the iris's colour: the paint in a ring round each pupil, seen from in front: past the pupil, inside the iris, both
# measured on the eye's opening (an iris is about two fifths of it across, its pupil a third of the iris at most).
# The ring is the iris whatever its colour; read by colour (cool for an eye, warm and dark for a brown one) a pale
# grey-green iris lost to the lids' brown shadow round it (woman4: 99 cool points against 919 brown, iris brown).
ring = np.zeros(len(LP), dtype=bool)
for p, w in zip(t_pupils, t_eye_width):
    d = np.linalg.norm((LP - p)[:, [0, 2]], axis=1)
    ring |= front & (d > 0.07 * w) & (d < 0.18 * w)
log("iris: %d points in the rings round the pupils" % int(ring.sum()))
t_iris = np.median(C[ring], axis=0) if ring.sum() >= 6 else np.array([0.35, 0.3, 0.25])
log("paint: pupils %s, eye widths %s, mouth corners %s, iris %s" % (t_pupils.round(3).tolist(), np.round(t_eye_width, 3).tolist(),
                                                                     t_mouth.round(3).tolist(), t_iris.round(3).tolist()))

# --- 3. the fit ------------------------------------------------------------------------------------------------------
Dp = np.stack([d[head] for d in D_pos])  # (K, n, 3)
Dn = np.stack([d[head] for d in D_neg])
n_head = len(head)
rim_idx = [np.array([index_in_head[v] for v in r]) for r in eye_rims]
mouth_idx = np.array([index_in_head[v] for v in mouth_rim])


def her(x):
    """Her head's vertices at the sliders x."""
    pos, neg = np.maximum(x, 0), np.maximum(-x, 0)
    return P_fit[head] + np.einsum("k,kij->ij", pos, Dp) + np.einsum("k,kij->ij", neg, Dn)


def jac(x):
    """d(her)/dx: (K, n, 3), the end in use at each slider."""
    return np.where((x >= 0)[:, None, None], Dp, -Dn)


# her nose tip and chin front: read once, with her neck in, and kept as the head vertices nearest them (the same
# points of her through the fit, whatever the sliders do to them)
skin = P_fit[body]
h_crown, h_chin_z, h_nose, h_chin = profile(skin[skin[:, 2] > skin[:, 2].min() + NECK * (skin[:, 2].max() - skin[:, 2].min())])
P_head0 = P_fit[head]
mid = np.abs(P_head0[:, 0]) < 0.02
NOSE_V = int(np.where(mid)[0][np.linalg.norm(P_head0[mid][:, 1:] - h_nose[1:], axis=1).argmin()])
CHIN_V = int(np.where(mid)[0][np.linalg.norm(P_head0[mid][:, 1:] - h_chin[1:], axis=1).argmin()])
log("her head: crown %.3f, chin %.3f (%.3f m chin to crown), nose tip %.3f; chin vertex %.1f mm from the profile's chin front" % (
    h_crown, h_chin_z, h_crown - h_chin_z, h_nose[2], np.linalg.norm(P_head0[CHIN_V] - h_chin) * 1000))


def her_marks(P):
    """Her landmarks as vertex indices into the head: crown, nose tip, chin front, each eye's rim middle (the rim's
    vertices, averaged), each rim's inner and outer vertex, the mouth's corners."""
    marks = {"crown": [int(P[:, 2].argmax())], "nose": [NOSE_V], "chin": [CHIN_V]}
    for side, r in zip(("l", "r"), rim_idx):
        marks["eye_" + side] = r.tolist()
        marks["eye_%s_in" % side] = [int(r[P[r, 0].argmax() if side == "l" else P[r, 0].argmin()])]
        marks["eye_%s_out" % side] = [int(r[P[r, 0].argmin() if side == "l" else P[r, 0].argmax()])]
    marks["mouth_l"] = [int(mouth_idx[P[mouth_idx, 0].argmin()])]
    marks["mouth_r"] = [int(mouth_idx[P[mouth_idx, 0].argmax()])]
    return marks


def bust_marks():
    """The bust's landmarks, in its own space, matching her_marks' names."""
    m = {"crown": np.array([0.0, T[T[:, 2].argmax(), 1], t_crown]), "nose": t_nose, "chin": t_chin}
    for side, p, w in zip(("l", "r"), t_pupils, t_eye_width):
        m["eye_" + side] = p
        m["eye_%s_in" % side] = p + [w / 2 if side == "l" else -w / 2, 0, 0]
        m["eye_%s_out" % side] = p + [-w / 2 if side == "l" else w / 2, 0, 0]
    m["mouth_l"], m["mouth_r"] = t_mouth[0], t_mouth[1]
    return m


BM = bust_marks()
WEIGHT = {"crown": 0.5, "nose": LANDMARK, "chin": LANDMARK, "eye_l": PUPIL, "eye_r": PUPIL, "eye_l_in": 0.0,
          "eye_r_in": 0.0, "eye_l_out": 0.0, "eye_r_out": 0.0, "mouth_l": LANDMARK, "mouth_r": LANDMARK}
# the bust's scale: chin to crown onto her head's, as fit_macros sized it from the Tripo body; the start shift puts
# her eyes' middle on its pupils' middle
x = np.zeros(K)
P0 = her(x)
s = (h_crown - h_chin_z) / t_head_h
eyes_her = np.mean([P0[r].mean(0) for r in rim_idx], axis=0)
t = eyes_her - s * t_pupils.mean(0)
log("scale %.3f (her head %.3f m chin to crown, the bust's %.3f), start shift %s" % (s, h_crown - h_chin_z, t_head_h, t.round(3).tolist()))


def nearest(P, s, t, n_her):
    """For each head vertex: the nearest bust point (her space), the bust's normal there, and whether it is hers to
    match (not a stray hit on a surface facing elsewhere)."""
    Q = np.empty_like(P)
    Nn = np.empty_like(P)
    ok = np.zeros(len(P), dtype=bool)
    for i, p in enumerate(P):
        hit = tripo_bvh.find_nearest(Vector((p - t) / s))
        if hit[0] is None:
            continue
        Q[i] = np.array(hit[0]) * s + t
        Nn[i] = np.array(hit[1])
        ok[i] = np.dot(Nn[i], n_her[i]) > np.cos(np.radians(STRAY))
    return Q, Nn, ok


def normals_of(P):
    full = P_fit.copy()
    full[head] = P
    return vertex_normals(full)[head]


def residual(x, s, t, marks, Q, Nn, ok):
    P = her(x)
    r = [(np.einsum("ij,ij->i", Nn, P - Q) * ok)]
    for k, verts in marks.items():
        r.append(WEIGHT[k] * (P[verts].mean(0) - (BM[k] * s + t)))
    r.append(RIDGE * x)
    return np.concatenate(r)


def jacobian(x, s, t, marks, Q, Nn, ok):
    """d(residual)/d(x, t): the sliders' columns, then the shift's three (the scale is not fitted)."""
    J = jac(x)
    rows = [np.einsum("ij,kij->ik", Nn, J) * ok[:, None]]
    rows_t = [-Nn * ok[:, None]]
    for k, verts in marks.items():
        rows.append(WEIGHT[k] * J[:, verts, :].mean(1).T)
        rows_t.append(-WEIGHT[k] * np.eye(3))
    rows.append(RIDGE * np.eye(K))
    rows_t.append(np.zeros((K, 3)))
    return np.column_stack([np.vstack(rows), np.vstack(rows_t)])


def cost(x, s, t):
    P = her(x)
    Q, Nn, ok = nearest(P, s, t, normals_of(P))
    r = residual(x, s, t, her_marks(P), Q, Nn, ok)
    return r @ r, (Q, Nn, ok)


def gap_mm(x, s, t):
    P = her(x)
    d = np.array([tripo_bvh.find_nearest(Vector((p - t) / s))[3] * s for p in P])
    return np.percentile(d, [50, 90, 100]) * 1000


c, (Q, Nn, ok) = cost(x, s, t)
start_gap = gap_mm(x, s, t)
log("start: cost %.6f, her surface to the bust %.1f mm median, %.1f p90, %.1f max; %.0f%% stray" % (
    c, *start_gap, 100 - 100 * ok.mean()))
mu = 1e-3
for it in range(ITERATIONS):
    P = her(x)
    marks = her_marks(P)
    r = residual(x, s, t, marks, Q, Nn, ok)
    J = jacobian(x, s, t, marks, Q, Nn, ok)
    A = J.T @ J
    g = J.T @ r
    improved = False
    for _ in range(8):
        step = np.linalg.solve(A + mu * np.diag(np.diag(A) + 1e-9), -g)
        x1 = np.clip(x + step[:K], LO, HI)
        t1 = t + step[K:]
        c1, corr = cost(x1, s, t1)
        if it == 0:
            applied = np.concatenate([x1 - x, t1 - t])
            r_lin = r + J @ applied
            r_same = residual(x1, s, t1, marks, Q, Nn, ok)
            log("    debug: cost %.6f, linear model %.6f, same correspondences %.6f, new ones %.6f; |step| x %.3f t %.4f" % (
                r @ r, r_lin @ r_lin, r_same @ r_same, c1, np.abs(applied[:K]).max(), np.abs(applied[K:]).max()))
        if c1 < c:
            x, t, c, (Q, Nn, ok) = x1, t1, c1, corr
            mu = max(mu / 3, 1e-6)
            improved = True
            break
        mu *= 4
    log("  %2d: cost %.6f, %d sliders in use, mu %.0e" % (it, c, int((np.abs(x) > 0.01).sum()), mu))
    if not improved or np.abs(step[:K]).max() < 1e-3:
        break
final_gap = gap_mm(x, s, t)
P = her(x)
marks = her_marks(P)
log("fit: her surface to the bust %.1f mm median, %.1f p90, %.1f max; %.0f%% stray" % (*final_gap, 100 - 100 * ok.mean()))
for k in marks:
    d = np.linalg.norm(P[marks[k]].mean(0) - (BM[k] * s + t)) * 1000
    log("  %-10s %.1f mm off" % (k, d))
values = {name: round(float(v), 4) for (name, _, _), v in zip(SLIDERS, x) if abs(v) > 1e-3}
log("%d sliders set:" % len(values), {k: v for k, v in sorted(values.items(), key=lambda kv: -abs(kv[1]))[:20]})
FACE_JSON = os.path.join(HERE, "checks", "face_%s.json" % NAME)
kept = json.load(open(FACE_JSON)) if os.path.exists(FACE_JSON) else {}
with open(FACE_JSON, "w") as f:
    json.dump({**{k: v for k, v in kept.items() if k in ("uv", "skin")},  # bake_face.py's, kept across a refit
               "name": NAME, "source": os.path.basename(SOURCE), "base": BASE, "iris": [round(float(v), 4) for v in t_iris],
               "bust": {"scale": round(s, 5), "shift": [round(float(v), 5) for v in t]},
               "gap_mm": {"start": np.round(start_gap, 1).tolist(), "fit": np.round(final_gap, 1).tolist()},
               "landmarks": {k: {"her": np.round(P[marks[k]].mean(0), 4).tolist(), "bust": np.round(BM[k] * s + t, 4).tolist()} for k in marks},
               "values": values,
               "targets": {name: {"neg": neg, "pos": pos} for name, neg, pos in SLIDERS if name in values}}, f, indent=1)

# --- the pictures: her head over the bust, both as they stand after the fit ----------------------------------------
for kb in blocks:
    if kb.name.startswith("face-"):
        kb.value = 0.0
for (name, neg, pos), v in zip(SLIDERS, x):
    for k in (pos if v > 0 else neg):
        blocks["face-" + k].value = abs(float(v))
for m in base.modifiers:
    if m.type == "ARMATURE":
        m.show_viewport = False
dg = bpy.context.evaluated_depsgraph_get()
baked = bpy.data.meshes.new_from_object(base.evaluated_get(dg))
base.modifiers.clear()
base.shape_key_clear()
base.data = baked
base.parent = None
Pw = np.array([base.matrix_world @ v.co for v in baked.vertices])
base.matrix_world.identity()
baked.vertices.foreach_set("co", Pw.ravel())
tripo.matrix_world.identity()
tme.vertices.foreach_set("co", (T * s + t).ravel())
tme.update()


def material(name, rgba):
    m = bpy.data.materials.new(name)
    m.diffuse_color = rgba
    return m


for o, m in ((base, material("her", (0.55, 0.65, 0.85, 1))), (tripo, material("bust", (0.85, 0.6, 0.5, 1)))):
    o.data.materials.clear()
    o.data.materials.append(m)
    for p in o.data.polygons:
        p.use_smooth = True
for k in marks:
    for who, at, col in (("her", P[marks[k]].mean(0), (0.2, 0.9, 1.0, 1)), ("bust", BM[k] * s + t, (1.0, 0.9, 0.2, 1))):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.003, location=at.tolist(), segments=8, ring_count=4)
        dot = bpy.context.active_object
        dot.name = "%s %s" % (who, k)
        dot.data.materials.append(material(dot.name, col))
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "MATERIAL"
scene.display.shading.show_xray = True
scene.display.shading.xray_alpha = 0.5
scene.render.resolution_x = scene.render.resolution_y = 1400
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
cam.data.ortho_scale = 0.4
scene.collection.objects.link(cam)
scene.camera = cam
centre = P.mean(0)
for view, loc, rot in (("front", (0, -10, 0), (90, 0, 0)), ("side", (10, 0, 0), (90, 0, 90))):
    cam.location = centre + np.array(loc)
    cam.rotation_euler = [np.radians(a) for a in rot]
    scene.render.filepath = os.path.join(HERE, "checks", "face_%s_%s.png" % (NAME, view))
    bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "build", "face_%s.blend" % NAME))
log("done")
