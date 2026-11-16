"""A hair for a replaceable body's heads: Tripo's hair alone (a hollow shell, no head inside: the head is the face
editor's) fitted onto the body's head and exported as a piece of its own on the body's skeleton, which Forge puts on
whichever head is worn.

    blender -b --factory-startup -P hair.py -- hair_pixie body_warrior_f

Reads <hair>/source_tripo.fbx and .fbm, and the body's pieces (pieces.py's build/forge/<Body>/: its skeleton and its
heads). The hair is fitted to the body's first face editor head (model.json "heads"), the one it is made in: its inside
(the faces turned toward the shell's middle) sized and placed by ellipsoids: rays from within the head (the middle of its scalp, above the brows) and from within
the hair (the middle of the sphere its inside makes) out to each surface, along the same directions, an axis-aligned
ellipsoid fitted to each; the hair scaled along each axis to the head's, middle on middle. Its inside is then laid
on the scalp (what faces the head within REACH, CLEAR off it, the rest moving with it over SPREAD), so it hugs it. Then no part of it may lie inside the head: a hair vertex within CLEAR of its surface, or
inside it, goes out along the head's normal to CLEAR off it (the body's other heads are measured, not pushed:
a hair is made for a head). It is reduced to TRIANGLES (keeping its UVs: one
material, its own maps) and weighed wholly to a bone of its own, <prefix>Hair on the Head bone, whose place on the
head is the hair's seat (Forge's Hold Stage tunes it).

Writes the body's build/forge/<Body>/Hair/<Title>.fbx (the skeleton and one mesh, "Hair", its material <Title>),
<Title>_Color.png and <Title>_Normal.png; <hair>/checks/hair.json and pictures of it on each head (hair_<view>_<Head>.jpg).
"""
import bmesh, bpy, json, math, os, sys
from glob import glob
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

ARGS = sys.argv[sys.argv.index("--") + 1:]
NAME, BODY = ARGS[:2]
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from place import Creature, pictures_as_jpeg
C = Creature(NAME)
B = Creature(BODY)
TITLE = C.title
BODY_OUT = B.build("forge", B.title)
OUT = os.path.join(BODY_OUT, "Hair")
TRIANGLES = C.spec.get("triangles", 20000)
TEXTURE = 4096
CLEAR = 0.002       # metres every hair vertex keeps off the heads' surface
BROWS = 0.035       # the scalp: the head above its eyes by this much (metres)
REACH = 0.03       # the hair's inside this near the head, facing it, is laid on it
SPREAD = 0.03      # the rest of the hair moves with the inside within this
LEVEL = -0.15       # the fit's rays go no lower than this (the sine of their angle below level): not into the face
os.makedirs(OUT, exist_ok=True)


def imported(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=os.path.abspath(path))
    return [o for o in bpy.data.objects if o not in before]


def world_mesh(ob):
    """The object's mesh as it stands (its armature's rest pose), in the world's frame: a BVH, its vertices."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(depsgraph)
    me = ev.to_mesh()
    co = [ob.matrix_world @ v.co for v in me.vertices]
    faces = [tuple(p.vertices) for p in me.polygons]
    ev.to_mesh_clear()
    return co, faces


bpy.ops.wm.read_factory_settings(use_empty=True)
report = {"hair": NAME, "body": BODY}

# The body's skeleton and its heads (the face editor's first), as Forge wears them.
spec_heads = B.spec.get("heads", [])
head_files = sorted(glob(os.path.join(BODY_OUT, "Heads", "*.fbx")))
heads = {}
rig = None
for path in head_files:
    new = imported(path)
    mesh = next(o for o in new if o.type == "MESH")
    arm = next(o for o in new if o.type == "ARMATURE")
    title = os.path.splitext(os.path.basename(path))[0]
    heads[title] = mesh
    if rig is None:
        rig = arm
    else:
        mesh.modifiers[0].object = rig if mesh.modifiers else None
        bpy.data.objects.remove(arm, do_unlink=True)
first = None
for name in spec_heads:
    made = glob(os.path.join(os.path.dirname(B.root), name, "build", "forge", "*"))
    if made and os.path.basename(made[0]) in heads:
        first = os.path.basename(made[0])
        break
first = first or B.title
head_co, head_faces = world_mesh(heads[first])
head_bvh = BVHTree.FromPolygons(head_co, head_faces)
crown = max(c.z for c in head_co)
report["fitted_on"] = first

# The scalp: the head's surface above its brows (its eye bones, else 60% up it).
prefix = next(b.name for b in rig.data.bones if b.name.endswith("Hips"))[:-len("Hips")]
eyes = [rig.matrix_world @ b.head_local for b in rig.data.bones if b.name in (prefix + "LeftEye", prefix + "RightEye")]
low = min(c.z for c in head_co)
brows = (sum(e.z for e in eyes) / len(eyes) if eyes else low + 0.6 * (crown - low)) + BROWS
scalp_faces = [f for f in head_faces if all(head_co[v].z > brows for v in f)]
scalp_bvh = BVHTree.FromPolygons(head_co, scalp_faces)
scalp = [c for c in head_co if c.z > brows]
centre = sum(scalp, Vector()) / len(scalp)

# The hair, in the world's frame.
new = imported(os.path.join(C.root, "source_tripo.fbx"))
hair = next(o for o in new if o.type == "MESH")
for o in new:
    if o is not hair:
        bpy.data.objects.remove(o, do_unlink=True)
hair.data.transform(hair.matrix_world)
hair.matrix_world = Matrix.Identity(4)
hair.parent = None
hm = hair.data
hco = np.array([v.co[:] for v in hm.vertices])
hair_bvh = BVHTree.FromPolygons([v.co.copy() for v in hm.vertices], [tuple(p.vertices) for p in hm.polygons])


def directions(n=400):
    """Directions over the upper part of a sphere (up to 30 degrees below level), evenly (a Fibonacci spiral)."""
    out = []
    for i in range(n):
        z = 1 - (i + 0.5) / n * 1.5
        r = math.sqrt(max(0.0, 1 - z * z))
        a = i * math.pi * (3 - math.sqrt(5))
        out.append(Vector((r * math.cos(a), r * math.sin(a), z)))
    return out


def cavity(bvh, start, rounds=4):
    """The sphere the inside of a shell makes round start: rays out from its middle, the first surface each meets (a
    ray out through an opening, the face, meets none), a sphere fitted to those, again from its centre."""
    centre = Vector(start)
    for _ in range(rounds):
        hits = [bvh.ray_cast(centre, d)[0] for d in directions()]
        hits = np.array([h[:] for h in hits if h is not None])
        c, radius = sphere_sit(hits)
        centre = Vector(c)
    return np.array(centre[:]), radius, len(hits)


from eyes import sphere_fit as sphere_sit

# Its size and place: the hair's inside and the scalp, each measured from within along the same directions (the
# upper part of a sphere, rays from the middle of each: the hair's inside's sphere's, the scalp's), each an axis-aligned
# ellipsoid round that middle (1/r^2 = x^2/a^2 + y^2/b^2 + z^2/c^2, least squares, its worst rays let go); the hair
# scaled along each axis to the head's and moved middle onto middle, CLEAR over it. A ray through the face's opening
# meets nothing and counts for neither.
head_centre, head_radius = sphere_sit(np.array([c[:] for c in scalp]))
lo, hi = hco.min(0), hco.max(0)
hair_centre, hair_radius, _ = cavity(hair_bvh, ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2] + (hi[2] - lo[2]) / 3))
ways = [d for d in directions(600) if d.z > LEVEL]


def reach(bvh, centre):
    """How far each of `ways` reaches from centre to the surface; None where it meets nothing."""
    out = []
    for d in ways:
        hit = bvh.ray_cast(Vector(centre[:]), d)[0]
        out.append((hit - Vector(centre[:])).length if hit is not None else None)
    return out


def ellipsoid(reaches):
    rows = [(d.x * d.x, d.y * d.y, d.z * d.z, 1 / (r * r)) for d, r in zip(ways, reaches) if r]
    a = np.array([r[:3] for r in rows]); b = np.array([r[3] for r in rows])
    keep = np.ones(len(b), bool)
    for _ in range(3):
        x = np.linalg.lstsq(a[keep], b[keep], rcond=None)[0]
        err = np.abs(a @ x - b)
        keep = err <= np.quantile(err, 0.85)
    return 1 / np.sqrt(np.maximum(x, 1e-9)), int(keep.sum())


head_bvh_all = BVHTree.FromPolygons(head_co, head_faces)
head_axes, head_rays = ellipsoid(reach(head_bvh_all, head_centre))
hair_axes, hair_rays = ellipsoid(reach(hair_bvh, hair_centre))
scale = (head_axes + CLEAR) / hair_axes
shift = head_centre - hair_centre * scale
hm.transform(Matrix.Translation(Vector(shift)) @ Matrix.Diagonal(Vector(scale).to_4d()))
hm.update()
report["fit"] = {"head_axes_cm": [round(float(a) * 100, 2) for a in head_axes], "head_rays": head_rays,
                 "hair_axes": [round(float(a), 4) for a in hair_axes], "hair_rays": hair_rays,
                 "scale_xyz": [round(float(a), 4) for a in scale], "shift_m": [round(float(a), 4) for a in shift]}

# Laid on the scalp: the hair's inside is not an ellipsoid (open at the face, the fringe off the forehead), so where
# it faces the head within REACH, each such point goes onto the head CLEAR off it, and the rest of the hair moves with
# the points within SPREAD of it (their moves averaged, nearer more), fading out SPREAD past the nearest: the hair
# hugs the head and keeps its thickness.
fitted_co, fitted_faces = world_mesh(heads[first])
fitted_bvh = BVHTree.FromPolygons(fitted_co, fitted_faces)
moves = {}
for v in hm.vertices:
    at, normal, _, distance = fitted_bvh.find_nearest(v.co)
    if at is None or distance > REACH or v.normal.dot(at - v.co) <= 0:
        continue
    moves[v.index] = (at + normal * CLEAR) - v.co
from mathutils.kdtree import KDTree
tree = KDTree(len(moves))
for i in moves:
    tree.insert(hm.vertices[i].co, i)
tree.balance()
moved_by = []
for v in hm.vertices:
    near = tree.find_range(v.co, SPREAD)
    if not near:
        continue
    weights = [(1 - d / SPREAD) ** 2 for _, _, d in near]
    step = sum((moves[i] * w for (_, i, _), w in zip(near, weights)), Vector()) / sum(weights)
    fade = (1 - min(d for _, _, d in near) / SPREAD)
    v.co = v.co + step * (1 if v.index in moves else fade)
    moved_by.append(step.length)
hm.update()
report["laid_on_scalp"] = {"inside_points": len(moves), "vertices_moved": len(moved_by),
                           "moved_mm_median_max": [round(float(np.median(moved_by)) * 1000, 2), round(max(moved_by) * 1000, 2)]}

# Off the head it is made on: what lies inside it or within CLEAR goes out along its normal. (The others are
# measured: how much of the hair lies inside each.)
pushed = {}
for title, ob in heads.items():
    co, faces = world_mesh(ob)
    bvh = BVHTree.FromPolygons(co, faces)
    count, most = 0, 0.0
    for v in hm.vertices:
        at, normal, _, distance = bvh.find_nearest(v.co)
        if at is None:
            continue
        side = (v.co - at).dot(normal)
        if side < CLEAR:
            if title == first:
                v.co = at + normal * CLEAR
            count += 1
            most = max(most, CLEAR - side)
    pushed[title] = {"vertices": count, "most_mm": round(most * 1000, 2)}
hm.update()
report["pushed_off_heads"] = pushed
bpy.ops.wm.save_as_mainfile(filepath=C.build("hair_fitted.blend"))

# For the game: reduced (collapse, keeping its UVs: its own maps still fit), smooth, weighed wholly to the Head bone,
# on the body's skeleton; its material named as it, Forge's name for its maps.
full_triangles = sum(len(p.vertices) - 2 for p in hm.polygons)
bpy.ops.object.select_all(action="DESELECT")
bpy.context.view_layer.objects.active = hair
hair.select_set(True)
if full_triangles > TRIANGLES:
    collapse = hair.modifiers.new("reduce", "DECIMATE")
    collapse.ratio = TRIANGLES / full_triangles
    bpy.ops.object.modifier_apply(modifier=collapse.name)
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.quads_convert_to_tris()
bpy.ops.object.mode_set(mode="OBJECT")
for p in hm.polygons:
    p.use_smooth = True
hm.materials[0].name = TITLE
hair.name = hm.name = "Hair"
# Its own bone, <prefix>Hair on the Head bone where the head's is, carrying all of it: Forge adds it to the body as it
# puts the hair on, and its seat on the head (the Hold Stage's, saved beside the hair) is that bone's place.
bpy.ops.object.select_all(action="DESELECT")
bpy.context.view_layer.objects.active = rig
rig.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
bones = rig.data.edit_bones
for bone in [b for b in bones if b.name == prefix + "Hair"]:
    bones.remove(bone)
seat = bones.new(prefix + "Hair")
seat.head = bones[prefix + "Head"].head.copy()
seat.tail = bones[prefix + "Head"].tail.copy()
seat.roll = bones[prefix + "Head"].roll
seat.parent = bones[prefix + "Head"]
seat.use_deform = True
bpy.ops.object.mode_set(mode="OBJECT")
bpy.ops.object.select_all(action="DESELECT")
bpy.context.view_layer.objects.active = hair
hair.select_set(True)
group = hair.vertex_groups.new(name=prefix + "Hair")
group.add(list(range(len(hm.vertices))), 1.0, "REPLACE")
hair.parent = rig
hair.matrix_parent_inverse = rig.matrix_world.inverted()
skin = hair.modifiers.new("Armature", "ARMATURE")
skin.object = rig
report["triangles"] = {"source": full_triangles, "game": sum(len(p.vertices) - 2 for p in hm.polygons)}

for kind, space in (("Color", "sRGB"), ("Normal", "Non-Color")):
    image = bpy.data.images.load(os.path.join(C.root, "source_tripo.fbm", f"{kind}.jpg"))
    image.colorspace_settings.name = space
    if image.size[0] != TEXTURE:
        image.scale(TEXTURE, TEXTURE)
    image.filepath_raw = os.path.join(OUT, f"{TITLE}_{kind}.png")
    image.file_format = "PNG"
    image.save()

bpy.ops.object.select_all(action="DESELECT")
rig.select_set(True); hair.select_set(True)
fbx = os.path.join(OUT, f"{TITLE}.fbx")
bpy.ops.export_scene.fbx(filepath=fbx, use_selection=True, object_types={"ARMATURE", "MESH"}, apply_unit_scale=True,
                         apply_scale_options="FBX_SCALE_ALL", add_leaf_bones=False, bake_anim=False,
                         mesh_smooth_type="FACE", path_mode="STRIP")

# Read back, as Forge will: one mesh on the skeleton, wholly on the Head bone; pictured on each head.
bpy.ops.wm.read_factory_settings(use_empty=True)
back = [o for o in imported(fbx) if o.type == "MESH"]
if len(back) != 1:
    raise SystemExit(f"HAIR {fbx} read back as {len(back)} meshes")
report["in_fbx"] = {"mesh": back[0].name, "materials": [m.name for m in back[0].data.materials],
                    "groups": [g.name for g in back[0].vertex_groups], "vertices": len(back[0].data.vertices)}
json.dump(report, open(C.checks("hair.json"), "w"), indent=1)
print("HAIR", json.dumps(report))
