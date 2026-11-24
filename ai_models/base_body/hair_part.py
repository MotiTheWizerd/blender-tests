"""A hair part made on her own head: her head drawn flat (sheet_base.py), the hair painted on by Iris from the front, the
sides and the back, and Tripo given those pictures, so the hair is born round HER skull. Its skin is laid on her head
(haircut.py's fit, as hair.py does it for a warrior's head) and what is not hair cut away by its paint.

What is left is made two parts, as hair_cap.py makes the buzz cut:
- the CAP: what lies on her skull (cornrows, hair combed flat) drawn on her own scalp: her faces under it, lifted a hair's
  breadth off her, her weights and every shape key kept (so it follows her faces, types and head controls), with Tripo's
  paint carried onto it (each texel the paint of Tripo's surface nearest it; see-through where that paint is her skin's,
  the scalp between the rows), or, model.json "cap": "cornrows", rows drawn from her hairline to each lock's root
  (Tripo's own cornrows are paint on a near-flat surface, guessed where it saw no picture: the crown came out in
  blocks; cut out as faces they came apart).
- the LOCKS: what stands or hangs free of the skull (braids hanging past the nape) kept as Tripo made it, each part of it
  on a chain of bones of its own under her Head bone (locks.py: a curtain of columns round her head, or model.json
  "each_piece", each braid its own), so Forge moves it
  (HairLocks), and each of its points carrying the shapes of the scalp its lock hangs from, so it moves with her head.

    blender -b -P hair_part.py -- <Name> <folder>      (HairBraidsLong hair/braids_long)

Reads build/body_<Title>.blend (build_body.py's) and <folder>/source_tripo.fbx with source_tripo.fbm/Color.jpg; its
<folder>/model.json may say how the locks move ("motion", as hair.py's). Writes build/forge/<Title>/Hair/<Name>.fbx (her
rig with the locks' bones, the cap and the locks: slots <Name> and <Name>Locks), <Name>_Color.png (the cap's, alpha
where hair), <Name>Locks_Color.png and <Name>_Motion.json; build/hair_<name>.blend; checks/hair_<name>_*.jpg and
checks/hair_<name>.json.
"""
import bmesh, json, math, os, sys
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from haircut import classify_and_fit, paint_hair_only, nose_and_width  # noqa: E402
import locks as hair_locks  # noqa: E402
from eyes import save_map  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
NAME = ARGS[0] if ARGS else "HairBraidsLong"
SOURCE = os.path.join(HERE, ARGS[1] if len(ARGS) > 1 else os.path.join("hair", "braids_long"))
MODEL = json.load(open(os.path.join(SOURCE, "model.json"))) if os.path.exists(os.path.join(SOURCE, "model.json")) else {}
SPEC = json.load(open(os.path.join(HERE, "types.json")))
TITLE = SPEC["title"]
OUT = os.path.join(HERE, "build", "forge", TITLE, "Hair")
CHECKS = os.path.join(HERE, "checks")
os.makedirs(OUT, exist_ok=True)
REACH = 0.12        # m under her chin her surface is fitted to (Tripo made her neck and shoulders too)
UNDER = 0.012       # m: her skin with hair within this of it is the cap's
LIFT = 0.0012       # m the cap stands off her skin (as the buzz cut's)
CAP_SIZE = 2048     # the cap's map
LOCKS_SIZE = 4096   # the locks' map
SOFT = 0.05         # how far either side of the paint's line between skin and hair the cap's alpha fades


def imported(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=os.path.abspath(path))
    return [o for o in bpy.data.objects if o not in before]


def smooth(a, b, t):
    t = np.clip((t - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


bpy.ops.wm.open_mainfile(filepath=os.path.join(HERE, "build", "body_%s.blend" % TITLE))
body = bpy.data.objects["Body"]
rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
me = body.data
assert all(k.value == 0.0 for k in me.shape_keys.key_blocks), "a shape key is not at 0"
world = np.array(body.matrix_world)
co = np.array([tuple(v.co) for v in me.vertices]) @ world[:3, :3].T + world[:3, 3]
normals = np.array([tuple(v.normal) for v in me.vertices]) @ world[:3, :3].T
normals /= np.linalg.norm(normals, axis=1, keepdims=True)
slots = [m.name for m in me.materials]
EYES = slots.index(TITLE + "Eyes")
eye_verts = sorted({v for p in me.polygons if p.material_index == EYES for v in p.vertices})
eye = co[eye_verts].mean(axis=0)
top = co[:, 2].max()
chin = eye[2] - (top - eye[2]) * 1.05
skull = co[co[:, 2] > eye[2] + 0.02]
assert eye[1] < skull[:, 1].mean(), "her face is not toward -y (haircut.py lays a head facing -y)"
prefix = next(b.name for b in rig.data.bones if b.name.endswith("Hips"))[:-len("Hips")]
keys = [k.name for k in me.shape_keys.key_blocks[1:]]
key_co = {k: np.array([tuple(d.co) for d in me.shape_keys.key_blocks[k].data]) @ world[:3, :3].T + world[:3, 3] for k in keys}

# Her surface as Tripo saw it: her head, neck and shoulders, down to REACH under her chin, not her eyes (Tripo's eyes are
# paint on a closed face).
low = chin - REACH
faces = [tuple(p.vertices) for p in me.polygons
         if p.material_index != EYES and all(co[v, 2] > low for v in p.vertices)]
used = np.array(sorted({v for f in faces for v in f}))
index = {int(v): i for i, v in enumerate(used)}
head_co = [Vector(co[v]) for v in used]
head_faces = [tuple(index[v] for v in f) for f in faces]
head_points = co[used]
head_bvh = BVHTree.FromPolygons(head_co, head_faces)
print("her surface: %d faces, from %.3f m up" % (len(head_faces), low), flush=True)

# --- Tripo's head with the hair on, laid on hers, the hair told from her skin by its paint ----------------------------
new = imported(os.path.join(SOURCE, "source_tripo.fbx"))
hair = next(o for o in new if o.type == "MESH")
for o in new:
    if o is not hair:
        bpy.data.objects.remove(o, do_unlink=True)
hair.data.transform(hair.matrix_world)
hair.matrix_world.identity()
hair.parent = None
hm = hair.data
report = {"name": NAME, "source": {"vertices": len(hm.vertices), "faces": len(hm.polygons)}}
colour_map = bpy.data.images.load(os.path.join(SOURCE, "source_tripo.fbm", "Color.jpg"))
is_hair, _, _, cut = classify_and_fit(hair, colour_map, head_co, head_faces)
cut.pop("grown")
report["cut"] = cut
print("cut:", json.dumps(cut), flush=True)

# The whole of it, laid, kept to read its paint from (triangles, so a point's place in its face is three weights).
laid = bpy.data.meshes.new("laid")
bm = bmesh.new()
bm.from_mesh(hm)
bmesh.ops.triangulate(bm, faces=bm.faces[:])
bm.to_mesh(laid)
bm.free()
laid_co = np.array([v.co[:] for v in laid.vertices])
laid_tris = np.array([p.vertices[:] for p in laid.polygons])
laid_uv = np.zeros((len(laid.loops), 2))
laid.uv_layers.active.data.foreach_get("uv", laid_uv.ravel())
laid_tri_uv = laid_uv[np.array([list(p.loop_indices) for p in laid.polygons])]
laid_bvh = BVHTree.FromPolygons([Vector(c) for c in laid_co], [tuple(t) for t in laid_tris])

# The skin away: the hair alone.
bm = bmesh.new()
bm.from_mesh(hm)
bm.faces.ensure_lookup_table()
bmesh.ops.delete(bm, geom=[bm.faces[i] for i in np.nonzero(~is_hair)[0]], context="FACES")
bm.to_mesh(hm)
bm.free()
hm.update()
hair_points = np.array([v.co[:] for v in hm.vertices])

# --- what of it hangs free: the locks --------------------------------------------------------------------------------
skull_base = float(nose_and_width(head_points)[0][2])
found, links, lock_weights, off, free, report["locks"] = hair_locks.find(
    hair_points, [tuple(e.vertices) for e in hm.edges], head_points, head_bvh, skull_base, MODEL.get("roots"),
    MODEL.get("each_piece", False))
report["locks"]["skull_base_z"] = round(skull_base, 4)
cap_weight = 1.0 - lock_weights.sum(axis=(1, 2))
cap_weight, lock_weights = hair_locks.limit(cap_weight, lock_weights)
print("locks: %d, %s" % (len(found), json.dumps({k: v for k, v in report["locks"].items() if k != "pieces"})), flush=True)

# The locks' object: the hair's faces that are free (or touch what is); what lies on the skull is the cap's to draw.
keep_face = np.array([any(free[v] for v in p.vertices) for p in hm.polygons])
bm = bmesh.new()
bm.from_mesh(hm)
bm.faces.ensure_lookup_table()
original = bm.verts.layers.int.new("original")
for v in bm.verts:
    v[original] = v.index
bmesh.ops.delete(bm, geom=[bm.faces[i] for i in np.nonzero(~keep_face)[0]], context="FACES")
bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
bm.verts.ensure_lookup_table()
kept = np.array([v[original] for v in bm.verts])
bm.verts.layers.int.remove(original)
bm.to_mesh(hm)
bm.free()
hm.update()
locks_ob = hair
locks_ob.name = hm.name = NAME + "Locks"
cap_weight, lock_weights = cap_weight[kept], lock_weights[kept]
locks_co = hair_points[kept]
report["locks_part"] = {"vertices": len(hm.vertices), "faces": len(hm.polygons)}

# The locks' bones: each a chain under her Head bone, root to tip, and a last bone at its tip that carries nothing
# (Forge reads where the chain ends from it).
bpy.ops.object.select_all(action="DESELECT")
bpy.context.view_layer.objects.active = rig
rig.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
bones = rig.data.edit_bones
for bone in [b for b in bones if b.name.startswith(prefix + "HairLock")]:
    bones.remove(bone)
to_rig = rig.matrix_world.inverted()
lock_bones = []
for i, lock in enumerate(found):
    joints = lock["joints"]
    names, parent = [], bones[prefix + "Head"]
    for k in range(len(joints)):
        bone = bones.new(f"{prefix}HairLock{i}_{k}")
        bone.head = to_rig @ Vector(joints[k])
        ahead = joints[k + 1] if k + 1 < len(joints) else joints[k] + 0.3 * (joints[k] - joints[k - 1])
        bone.tail = to_rig @ Vector(ahead)
        bone.parent = parent
        bone.use_deform = k + 1 < len(joints)
        names.append(bone.name)
        parent = bone
    lock_bones.append(names)
bpy.ops.object.mode_set(mode="OBJECT")
locks_ob.vertex_groups.clear()
head_group = locks_ob.vertex_groups.new(name=prefix + "Head")
for i, w in enumerate(cap_weight):
    if w > 0:
        head_group.add([i], float(w), "REPLACE")
for i, names in enumerate(lock_bones):
    for k, name in enumerate(names[:-1]):
        on = lock_weights[:, i, k]
        if (on > 0).any():
            group = locks_ob.vertex_groups.new(name=name)
            for v in np.nonzero(on > 0)[0]:
                group.add([int(v)], float(on[v]), "REPLACE")
locks_ob.parent = rig
locks_ob.matrix_parent_inverse = rig.matrix_world.inverted()
mod = locks_ob.modifiers.new("Armature", "ARMATURE")
mod.object = rig

# Her shapes on the locks: each lock hangs from her scalp and moves as the scalp at its root moves under each of her
# shapes (her other faces, the body types, the head controls), all of it alike; what stays with her head (its weight to
# the Head bone) moves as the scalp nearest it.
tree = KDTree(len(co))
for i, c in enumerate(co):
    tree.insert(Vector(c), i)
tree.balance()
nearest = np.array([tree.find(Vector(c))[1] for c in locks_co])
root_of = [tree.find(Vector(lock["joints"][0]))[1] for lock in found]
share = lock_weights.sum(axis=2)                       # (points, locks)
locks_ob.shape_key_add(name="Basis", from_mix=False)
moves = {}
for k in keys:
    delta = key_co[k] - co
    moved = cap_weight[:, None] * delta[nearest] + share @ delta[root_of]
    block = locks_ob.shape_key_add(name=k, from_mix=False)
    block.data.foreach_set("co", (locks_co + moved).ravel())
    block.value = 0.0
    moves[k] = round(float(np.linalg.norm(delta[root_of], axis=1).max()) * 1000, 1) if root_of else 0.0
report["locks_roots_move_mm"] = moves
print("locks' roots move (mm, most of any lock) by shape:", json.dumps(moves), flush=True)
hm.materials.clear()
locks_material = bpy.data.materials.new(NAME + "Locks")
hm.materials.append(locks_material)
for p in hm.polygons:
    p.material_index = 0
    p.use_smooth = True

# The locks' map: Tripo's, black where no face of the locks draws it (Forge measures the hair's colour from the rest).
locks_map = bpy.data.images.load(os.path.join(SOURCE, "source_tripo.fbm", "Color.jpg"))
report["locks_painted"] = paint_hair_only(locks_map, locks_ob, LOCKS_SIZE)
locks_map.filepath_raw = os.path.join(OUT, NAME + "Locks_Color.png")
locks_map.file_format = "PNG"
locks_map.save()

# What Forge reads beside it: each lock's bones (root to tip), its radius at each joint past its root, its neighbours,
# how thick the cap is (the cap is drawn on her now: as thick as it is lifted), and how it moves.
motion = {"capThickness": LIFT,
          "locks": [{"bones": names, "radii": [round(float(r), 4) for r in lock["radii"]]} for names, lock in zip(lock_bones, found)],
          "links": [{"a": int(a), "b": int(b)} for a, b in links],
          "motion": MODEL.get("motion", {})}
json.dump(motion, open(os.path.join(OUT, NAME + "_Motion.json"), "w"), indent=1)

# --- the cap: her skin under the hair that lies on her skull, drawn with Tripo's paint ---------------------------------
hair_tree = KDTree(len(hair_points))
for i, c in enumerate(hair_points):
    hair_tree.insert(Vector(c), i)
hair_tree.balance()
under = np.array([hair_tree.find(Vector(c))[2] < UNDER for c in co])
under[eye_verts] = False
keep = {p.index for p in me.polygons if p.material_index != EYES and all(under[v] for v in p.vertices)}
cap = body.copy()
cap.data = me.copy()
cap.name = cap.data.name = NAME
bpy.context.scene.collection.objects.link(cap)
bm = bmesh.new()
bm.from_mesh(cap.data)
bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in keep], context="FACES_ONLY")
bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
bm.to_mesh(cap.data)
bm.free()
cd = cap.data
for block in cd.shape_keys.key_blocks:
    block.value = 0.0
cap_co = np.array([v.co[:] for v in cd.vertices]) @ world[:3, :3].T + world[:3, 3]
mine = np.array([tree.find(Vector(c))[1] for c in cap_co])
lift = normals[mine] * LIFT @ np.linalg.inv(world[:3, :3]).T
for block in cd.shape_keys.key_blocks:
    for i, d in enumerate(block.data):
        d.co = Vector(np.array(d.co) + lift[i])
for i, v in enumerate(cd.vertices):
    v.co = Vector(np.array(v.co) + lift[i])
cd.materials.clear()
cap_material = bpy.data.materials.new(NAME)
cd.materials.append(cap_material)
for p in cd.polygons:
    p.material_index = 0
    p.use_smooth = True
bpy.ops.object.select_all(action="DESELECT")
cap.select_set(True)
bpy.context.view_layer.objects.active = cap
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.unwrap(method="CONFORMAL", margin=0.004)
bpy.ops.object.mode_set(mode="OBJECT")
report["cap"] = {"faces": len(cd.polygons), "vertices": len(cd.vertices), "shape_keys": len(cd.shape_keys.key_blocks) - 1}
print("cap: %d of her faces" % len(cd.polygons), flush=True)

P = co[mine]
uv = np.zeros((len(cd.loops), 2))
cd.uv_layers.active.data.foreach_get("uv", uv.ravel())
vert_of = np.array([l.vertex_index for l in cd.loops])
colour = np.zeros((CAP_SIZE, CAP_SIZE, 4), np.float32)
colour[..., :3] = cut["hair_paint"]


def texels():
    """Each texel of the cap's map its faces draw: (rows, columns, its place on her (world)), triangle by triangle."""
    for p in cd.polygons:
        loops = list(p.loop_indices)
        for k in range(1, len(loops) - 1):
            t = [loops[0], loops[k], loops[k + 1]]
            a, b, c = uv[t] * CAP_SIZE
            lo = np.floor(np.minimum(np.minimum(a, b), c)).astype(int)
            hi = np.ceil(np.maximum(np.maximum(a, b), c)).astype(int)
            gx, gy = np.meshgrid(np.arange(max(lo[0], 0), min(hi[0] + 1, CAP_SIZE)), np.arange(max(lo[1], 0), min(hi[1] + 1, CAP_SIZE)))
            px = np.stack([gx.ravel() + 0.5, gy.ravel() + 0.5], 1)
            m = np.array([[b[0] - a[0], c[0] - a[0]], [b[1] - a[1], c[1] - a[1]]])
            if abs(np.linalg.det(m)) < 1e-12:
                continue
            l12 = (px - a) @ np.linalg.inv(m).T
            bary = np.column_stack([1 - l12.sum(1), l12])
            inside = (bary >= -0.05).all(1)
            if inside.any():
                yield px[inside, 1].astype(int), px[inside, 0].astype(int), bary[inside] @ P[vert_of[t]]


if MODEL.get("cap") == "cornrows":
    # Cornrows drawn: a row from her hairline back over her head to each lock's root, rows taken in order (the lock
    # at her nape from the middle of her forehead, those beside her ears from in front of them), so none crosses another.
    # A row is the curve of directions from the middle of her skull, from its start's to its root's, lifted toward the
    # top (ARCH: the middle row runs over the crown, the side rows arch over the ears), laid on her where each meets her
    # head. Its width runs from ROW_TIP at the hairline to its braid's own at the root; its paint a braid's, strands
    # crossing every ROW_PITCH, darker at its edges.
    ARCH, ROW_TIP, ROW_PITCH, ROW_SAMPLES = 0.9, 0.0028, 0.0055, 400
    centre = np.array(skull.mean(axis=0))
    centre[2] = eye[2] + 0.025

    def azimuth(points):
        d = points - centre
        return np.degrees(np.arctan2(d[..., 0], -d[..., 1]))       # 0 her front, +90 her +x side, +-180 her back

    def elevation(points):
        d = points - centre
        return np.degrees(np.arctan2(d[..., 2], np.hypot(d[..., 0], d[..., 1])))

    roots = np.array([lock["joints"][0] for lock in found])
    root_width = np.array([2.0 * float(lock["radii"][0]) for lock in found])
    order = np.argsort(-(azimuth(roots) % 360.0))                   # round her back from her -x side to her +x side
    # The hairline: how low the hair lying on her skull comes at each bearing round her front (its lowest tenth there).
    lying = hair_points[~free]
    widest = min(80.0, 180.0 - float(np.min(np.abs(azimuth(roots)))) + 5.0)
    bearings = np.linspace(-widest, widest, len(found))
    starts = []
    for b in bearings:
        near = lying[np.abs(((azimuth(lying) - b) + 180.0) % 360.0 - 180.0) < 6.0]
        low = float(np.percentile(elevation(near), 10)) if len(near) > 20 else 20.0
        a, e = np.radians(b), np.radians(low + 2.0)
        starts.append(centre + np.array([np.sin(a) * np.cos(e), -np.cos(a) * np.cos(e), np.sin(e)]))
    rows = []
    for k, lock in enumerate(order):
        d0 = (starts[k] - centre) / np.linalg.norm(starts[k] - centre)
        d1 = (roots[lock] - centre) / np.linalg.norm(roots[lock] - centre)
        path = []
        for t in np.linspace(0.0, 1.0, ROW_SAMPLES):
            d = (1 - t) * d0 + t * d1 + ARCH * math.sin(math.pi * t) * np.array([0.0, 0.0, 1.0])
            d /= np.linalg.norm(d)
            hit = head_bvh.ray_cast(Vector(centre), Vector(d))[0]
            if hit is not None:
                path.append(np.array(hit[:]))
        if len(path) < 10:
            continue
        path = np.array(path)
        along = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))])
        tangent = np.gradient(path, axis=0)
        tangent /= np.maximum(np.linalg.norm(tangent, axis=1, keepdims=True), 1e-9)
        rows.append({"path": path, "along": along, "tangent": tangent, "width": (ROW_TIP, max(root_width[lock], 2 * ROW_TIP))})
    samples = [(r, i) for r, row in enumerate(rows) for i in range(len(row["path"]))]
    row_tree = KDTree(len(samples))
    for j, (r, i) in enumerate(samples):
        row_tree.insert(Vector(rows[r]["path"][i]), j)
    row_tree.balance()
    base = np.array(cut["hair_paint"], np.float32)
    for iy, ix, points in texels():
        for y, x, q in zip(iy, ix, points):
            _, j, _ = row_tree.find(Vector(q))
            r, i = samples[j]
            row = rows[r]
            rel = q - row["path"][i]
            ahead = float(rel @ row["tangent"][i])
            across = float(np.linalg.norm(rel - ahead * row["tangent"][i]))
            s_ = row["along"][i] + ahead
            share = min(max(s_ / max(row["along"][-1], 1e-6), 0.0), 1.0)
            half = 0.5 * (row["width"][0] + (row["width"][1] - row["width"][0]) * share)
            u = across / half
            if u > 1.15:
                continue
            # A braid: strands crossing it in a chevron, each lit at its middle, the braid round (darker at its edges).
            f = (s_ / ROW_PITCH + 0.5 * u) % 1.0
            strand = 0.65 + 0.7 * math.sin(math.pi * f) ** 2
            colour[y, x, :3] = np.clip(base * strand * (1.0 - 0.45 * u * u), 0.0, 1.0)
            colour[y, x, 3] = float(smooth(1.1, 0.8, np.array(u)))
    report["cap"]["rows"] = len(rows)
    print("cornrows: %d rows" % len(rows), flush=True)
else:
    # Its map: each texel the paint of Tripo's surface nearest its place on her (Tripo's cornrows lie on her skull), its
    # alpha the hair's: none where that paint is her skin's (between the rows), all where it is the hair's.
    tex = np.array(colour_map.pixels[:], dtype=np.float32).reshape(colour_map.size[1], colour_map.size[0], 4)[..., :3]
    th, tw = tex.shape[:2]
    line = cut["light_line"]
    weights_lum = np.array([0.2126, 0.7152, 0.0722], np.float32)
    for iy, ix, points in texels():
        found_paint = np.zeros((len(points), 3), np.float32)
        for j, q in enumerate(points):
            at, _, face, _ = laid_bvh.find_nearest(Vector(q))
            tri = laid_co[laid_tris[face]]
            # The point's weights in Tripo's triangle, its paint there.
            v0, v1, v2 = tri[1] - tri[0], tri[2] - tri[0], np.array(at[:]) - tri[0]
            d00, d01, d11, d20, d21 = v0 @ v0, v0 @ v1, v1 @ v1, v2 @ v0, v2 @ v1
            den = d00 * d11 - d01 * d01
            w1 = (d11 * d20 - d01 * d21) / den if den else 0.0
            w2 = (d00 * d21 - d01 * d20) / den if den else 0.0
            tuv = (1 - w1 - w2) * laid_tri_uv[face, 0] + w1 * laid_tri_uv[face, 1] + w2 * laid_tri_uv[face, 2]
            found_paint[j] = tex[int((tuv[1] % 1.0) * th) % th, int((tuv[0] % 1.0) * tw) % tw]
        lum = found_paint @ weights_lum
        colour[iy, ix, :3] = found_paint
        colour[iy, ix, 3] = smooth(line + SOFT, line - SOFT, lum)
# The hair's colour into its see-through texels too, so the map's filtering brings no skin round the rows' edges.
seen = colour[..., 3] > 0.5
colour[~seen, :3] = cut["hair_paint"]
save_map(colour, os.path.join(OUT, NAME + "_Color.png"), "sRGB")
report["cap"]["hair_share"] = round(float(seen.mean()), 4)
print("cap map: hair over %.1f%% of it" % (seen.mean() * 100), flush=True)

# --- the FBX: her rig with the locks' bones, the cap and the locks -----------------------------------------------------
bpy.ops.object.select_all(action="DESELECT")
for ob in (cap, locks_ob, rig):
    ob.select_set(True)
path = os.path.join(OUT, NAME + ".fbx")
bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={"ARMATURE", "MESH"}, apply_unit_scale=True,
                         apply_scale_options="FBX_SCALE_ALL", add_leaf_bones=False, bake_anim=False,
                         mesh_smooth_type="FACE", path_mode="STRIP")
print("wrote", path, flush=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "build", "hair_%s.blend" % NAME.lower()))

# --- the checks: her head wearing it, drawn flat; then the locks, each its own colour, the joints balls ---------------
maps = os.path.join(HERE, "build", "forge", TITLE)


def flat(material, image, see_through=False):
    material.use_nodes = True
    nodes, links_ = material.node_tree.nodes, material.node_tree.links
    nodes.clear()
    tex_node = nodes.new("ShaderNodeTexImage")
    tex_node.image = image
    emit, out = nodes.new("ShaderNodeEmission"), nodes.new("ShaderNodeOutputMaterial")
    links_.new(tex_node.outputs["Color"], emit.inputs["Color"])
    if see_through:
        clear, mix = nodes.new("ShaderNodeBsdfTransparent"), nodes.new("ShaderNodeMixShader")
        links_.new(tex_node.outputs["Alpha"], mix.inputs["Fac"])
        links_.new(clear.outputs[0], mix.inputs[1])
        links_.new(emit.outputs[0], mix.inputs[2])
        links_.new(mix.outputs[0], out.inputs["Surface"])
        if hasattr(material, "surface_render_method"):
            material.surface_render_method = "BLENDED"
    else:
        links_.new(emit.outputs["Emission"], out.inputs["Surface"])


for slot in body.material_slots:
    name = slot.material.name.split(".")[0]
    mat = bpy.data.materials.new(name + "_check")
    flat(mat, bpy.data.images.load(os.path.join(maps, name + "_Color.png")))
    slot.material = mat
flat(cap_material, bpy.data.images.load(os.path.join(OUT, NAME + "_Color.png")), see_through=True)
flat(locks_material, bpy.data.images.load(os.path.join(OUT, NAME + "Locks_Color.png")))
rig.hide_render = True
for o in bpy.data.objects:
    if o.type == "MESH" and o not in (body, cap, locks_ob):
        o.hide_render = True
scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.view_settings.view_transform = "Standard"
sky = bpy.data.worlds.new("check")
sky.use_nodes = True
sky.node_tree.nodes["Background"].inputs[0].default_value = (0.5, 0.5, 0.5, 1)
scene.world = sky
scene.render.resolution_x = scene.render.resolution_y = 900
scene.render.image_settings.file_format = "JPEG"
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
reach = max(top - locks_co[:, 2].min(), 0.3) if len(locks_co) else 0.4
cam.data.ortho_scale = reach * 1.15
scene.collection.objects.link(cam)
scene.camera = cam
centre = Vector((eye[0], co[eye_verts, 1].mean() + 0.09, top - reach / 2))
VIEWS = {"front": Vector((0, 1, 0)), "side": Vector((-1, 0, 0)), "back": Vector((0, -1, 0)),
         "quarter": Vector((-1, 1, 0)).normalized()}


def pictures(kind):
    for view, toward in VIEWS.items():
        cam.location = centre - toward * 2.0
        cam.rotation_euler = toward.to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = os.path.join(CHECKS, "hair_%s_%s%s.jpg" % (NAME.lower(), kind, view))
        bpy.ops.render.render(write_still=True)


pictures("")
if found:
    palette = np.array([(0.95, 0.3, 0.2), (0.2, 0.6, 0.95), (0.3, 0.85, 0.35), (0.95, 0.8, 0.2), (0.75, 0.35, 0.9),
                        (0.2, 0.85, 0.85), (0.95, 0.5, 0.75), (0.6, 0.45, 0.25)])
    shade = hm.color_attributes.new("locks", "FLOAT_COLOR", "POINT")
    for v in range(len(hm.vertices)):
        c = cap_weight[v] * np.array([0.55, 0.55, 0.55]) + sum(share[v, i] * palette[i % len(palette)] for i in range(len(found)))
        shade.data[v].color = (*c, 1.0)
    locks_material.node_tree.nodes.clear()
    attr = locks_material.node_tree.nodes.new("ShaderNodeVertexColor")
    attr.layer_name = "locks"
    emit = locks_material.node_tree.nodes.new("ShaderNodeEmission")
    out = locks_material.node_tree.nodes.new("ShaderNodeOutputMaterial")
    locks_material.node_tree.links.new(attr.outputs["Color"], emit.inputs["Color"])
    locks_material.node_tree.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    for lock in found:
        for k, joint in enumerate(lock["joints"]):
            radius = lock["radii"][k - 1] if k > 0 else 0.006
            bpy.ops.mesh.primitive_uv_sphere_add(radius=float(radius) * 0.6, location=Vector(joint), segments=12, ring_count=8)
            ball = bpy.context.active_object
            ball.data.materials.append(bpy.data.materials.new("ball"))
    pictures("locks_")
json.dump(report, open(os.path.join(CHECKS, "hair_%s.json" % NAME.lower()), "w"), indent=1, default=str)
print("HAIR PART", json.dumps({k: v for k, v in report.items() if k != "locks"}, default=str), flush=True)
