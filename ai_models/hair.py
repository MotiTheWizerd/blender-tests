"""A hair for a replaceable body's heads: Tripo's hair alone (a hollow shell, no head inside: the head is the face
editor's) fitted onto the body's head and exported as a piece of its own on the body's skeleton, which Forge puts on
whichever head is worn.

    blender -b --factory-startup -P hair.py -- hair_pixie body_warrior_f

Reads <hair>/source_tripo.fbx and .fbm, and the body's pieces (pieces.py's build/forge/<Body>/: its skeleton and its
heads). The hair is fitted to the body's first face editor head (model.json "heads"), the one it is made in: its inside
(the faces turned toward the shell's middle) sized and placed by ellipsoids: rays from within the head (the middle of its scalp, above the brows) and from within
the hair (the middle of the sphere its inside makes) out to each surface, along the same directions, an axis-aligned
ellipsoid fitted to each; the hair scaled along each axis to the head's, middle on middle. It is then shaped to the
scalp: each vertex placed between the hair's inside, laid CLEAR off the scalp, and its outside, kept within a pixie's
thickness (THIN at the brows, THICK at the crown), so it hugs her skull instead of floating round it. Then no part of it may lie inside the head: a hair vertex within CLEAR of its surface, or
inside it, goes out along the head's normal to CLEAR off it (the body's other heads are measured, not pushed:
a hair is made for a head). It is reduced to TRIANGLES (keeping its UVs: one
material, its own maps) and weighed wholly to a bone of its own, <prefix>Hair on the Head bone, whose place on the
head is the hair's seat (Forge's Hold Stage tunes it). A hair whose model.json says "locks": true has what of it stands
or hangs free of the head on chains of bones of its own under that one, <prefix>HairLock<i>_<k> (locks.py), and a
<Title>_Motion.json beside it that says how Forge moves them (HairLocks).

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
THIN = 0.01        # a pixie's thickness over the head at the brows' height (metres)
THICK = 0.028      # and at the crown
SMOOTH = 8         # passes evening out how far neighbouring points move (not the shape: its strands stay)
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
colour_map = bpy.data.images.load(os.path.join(C.root, "source_tripo.fbm", "Color.jpg"))
# model.json "made_on": "head": Tripo made the whole head with the hair on, from the body's own head drawn (sheet.py)
# and the hair painted on by Iris; the hair is cut out of it by its paint and laid on her by its skin (haircut.py), so
# it needs no fit and no shaping: it was born on her skull.
ON_HEAD = C.spec.get("made_on") == "head"
if ON_HEAD:
    from haircut import cut_from_head, paint_hair_only
    report["cut_from_head"] = cut_from_head(hair, colour_map, head_co, head_faces)
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

if not ON_HEAD:
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

    # Shaped to the scalp: the hair was made round another head, a shell 2-3 cm thick everywhere, so fitted by size alone
    # it floats where her skull differs and puffs out like a helmet. Each hair vertex is taken along the line from the
    # head's surface nearest it, out through the hair: where that line first enters the hair (its inside) and last leaves
    # it (its outside). Its place between the two is kept, but the inside is laid CLEAR off the scalp and the outside no
    # further than a pixie's thickness there (THIN at the brows' height, THICK at the crown, between by height), thinner
    # where the hair already is; a vertex no line through the hair finds is pulled in softly toward that thickness.
    fitted_co, fitted_faces = world_mesh(heads[first])
    fitted_bvh = BVHTree.FromPolygons(fitted_co, fitted_faces)
    # model.json "drop" (metres, optional): the hair lowered on the head first, so its hairline comes down onto a taller
    # forehead than the one it was made on (hair_pixie on WarriorF: 0.02).
    DROP = C.spec.get("drop", 0.0)
    if DROP:
        hm.transform(Matrix.Translation((0, 0, -DROP)))
        hm.update()
    hair_bvh = BVHTree.FromPolygons([v.co.copy() for v in hm.vertices], [tuple(p.vertices) for p in hm.polygons])


    def through(start, way, most=0.08):
        """How far out from start along way the line first enters the hair and last leaves it (None: it meets none)."""
        hits, at, gone = [], start + way * 1e-4, 1e-4
        for _ in range(24):
            hit = hair_bvh.ray_cast(at, way, most - gone)
            if hit[0] is None:
                break
            gone += hit[3] + 1e-4
            hits.append(gone)
            at = hit[0] + way * 1e-4
        return (hits[0], hits[-1]) if len(hits) >= 2 else None


    def thickness_at(z):
        h = min(max((z - brows) / max(crown - brows, 1e-6), 0.0), 1.0)
        return THIN + (THICK - THIN) * h


    moved, lined, soft = [], 0, 0
    new_co = []
    for v in hm.vertices:
        at, normal, _, _ = fitted_bvh.find_nearest(v.co)
        out = v.co - at
        d = out.length
        way = out.normalized() if d > 1e-6 else normal
        if way.dot(normal) < 0:          # inside the head: out along its normal
            way = normal
            d = -d
        room = thickness_at(at.z)
        span = through(at, way)
        if span is not None and span[1] > span[0]:
            t = min(max((d - span[0]) / (span[1] - span[0]), 0.0), 1.0)
            depth = CLEAR + t * min(room - CLEAR, span[1] - span[0])
            lined += 1
        else:
            depth = CLEAR + room * (1 - math.exp(-max(d, 0.0) / room))
            soft += 1
        target = at + way * depth
        moved.append((target - v.co).length)
        new_co.append(target)
    # How far each point moves, evened with its neighbours' (the edge where the hair's inside meets its outside is found
    # by no line and would crumple), the shape's own relief riding on it.
    step = np.array([(c - v.co)[:] for v, c in zip(hm.vertices, new_co)])
    edges = np.array([e.vertices[:] for e in hm.edges])
    count = np.bincount(edges.ravel(), minlength=len(step)).astype(float)[:, None]
    for _ in range(SMOOTH):
        total = np.zeros_like(step)
        np.add.at(total, edges[:, 0], step[edges[:, 1]])
        np.add.at(total, edges[:, 1], step[edges[:, 0]])
        step = 0.5 * step + 0.5 * total / np.maximum(count, 1)
    for v, d in zip(hm.vertices, step):
        v.co = v.co + Vector(d)
    hm.update()
    report["shaped_to_scalp"] = {"thin_cm": THIN * 100, "thick_cm": THICK * 100, "lined": lined, "soft": soft,
                                 "moved_mm_median_max": [round(float(np.median(moved)) * 1000, 2), round(max(moved) * 1000, 2)]}

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
# model.json "locks": true: what of it stands or hangs free of the head on chains of bones of its own under the hair's,
# which Forge moves (locks.py; HairLocks), held where model.json "roots" says (points in the body's frame, one per
# chain; none: all along where it meets the cap). The skull's base: the height of her nose's tip (her head's most
# forward point).
found_locks, lock_links, cap_weight, lock_weights = [], [], np.ones(len(hm.vertices)), None
if C.spec.get("locks"):
    import locks as hair_locks
    from haircut import nose_and_width
    head_points = np.array([c[:] for c in head_co])
    skull_base = float(nose_and_width(head_points)[0][2])
    found_locks, lock_links, lock_weights, _, _, report["locks"] = hair_locks.find(
        np.array([v.co[:] for v in hm.vertices]), [tuple(e.vertices) for e in hm.edges], head_points, head_bvh,
        skull_base, C.spec.get("roots"))
    report["locks"]["skull_base_z"] = round(skull_base, 4)
    cap_weight = 1.0 - lock_weights.sum(axis=(1, 2))
    cap_weight, lock_weights = hair_locks.limit(cap_weight, lock_weights)
hm.materials[0].name = TITLE
hair.name = hm.name = "Hair"
# Its own bone, <prefix>Hair on the Head bone where the head's is, carrying all of it: Forge adds it to the body as it
# puts the hair on, and its seat on the head (the Hold Stage's, saved beside the hair) is that bone's place.
bpy.ops.object.select_all(action="DESELECT")
bpy.context.view_layer.objects.active = rig
rig.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
bones = rig.data.edit_bones
for bone in [b for b in bones if b.name == prefix + "Hair" or b.name.startswith(prefix + "HairLock")]:
    bones.remove(bone)
seat = bones.new(prefix + "Hair")
seat.head = bones[prefix + "Head"].head.copy()
seat.tail = bones[prefix + "Head"].tail.copy()
seat.roll = bones[prefix + "Head"].roll
seat.parent = bones[prefix + "Head"]
seat.use_deform = True
# Each lock's chain, <prefix>HairLock<i>_<k>, from its root (on the hair's bone) joint to joint, and a last bone at its
# tip that carries nothing (Forge reads where the chain ends from it: a bone's tail is not in the file).
to_rig = rig.matrix_world.inverted()
lock_bones = []
for i, lock in enumerate(found_locks):
    joints = lock["joints"]
    names, parent = [], seat
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
bpy.ops.object.select_all(action="DESELECT")
bpy.context.view_layer.objects.active = hair
hair.select_set(True)
group = hair.vertex_groups.new(name=prefix + "Hair")
for i, w in enumerate(cap_weight):
    if w > 0:
        group.add([i], float(w), "REPLACE")
for i, names in enumerate(lock_bones):
    for k, name in enumerate(names[:-1]):
        on = lock_weights[:, i, k]
        if (on > 0).any():
            bone_group = hair.vertex_groups.new(name=name)
            for v in np.nonzero(on > 0)[0]:
                bone_group.add([int(v)], float(on[v]), "REPLACE")
if found_locks:
    # What Forge reads beside the hair: each lock's bones (root to tip), its radius at each joint past its root, its
    # neighbours, how thick the cap is, and how it moves (model.json "motion"; none: HairLocks' own).
    motion = {"capThickness": report["locks"]["cap_thickness_m"],
              "locks": [{"bones": names, "radii": [round(float(r), 4) for r in lock["radii"]]}
                        for names, lock in zip(lock_bones, found_locks)],
              "links": [{"a": int(a), "b": int(b)} for a, b in lock_links],
              "motion": C.spec.get("motion", {})}
    json.dump(motion, open(os.path.join(OUT, f"{TITLE}_Motion.json"), "w"), indent=1)
hair.parent = rig
hair.matrix_parent_inverse = rig.matrix_world.inverted()
skin = hair.modifiers.new("Armature", "ARMATURE")
skin.object = rig
report["triangles"] = {"source": full_triangles, "game": sum(len(p.vertices) - 2 for p in hm.polygons)}

for kind, space in (("Color", "sRGB"), ("Normal", "Non-Color")):
    image = colour_map if kind == "Color" else bpy.data.images.load(os.path.join(C.root, "source_tripo.fbm", f"{kind}.jpg"))
    image.colorspace_settings.name = space
    if kind == "Color" and ON_HEAD:
        cut = report["cut_from_head"]
        report["painted"] = paint_hair_only(image, hair, TEXTURE, cut["light_line"], cut["hair_paint"])
    if image.size[0] != TEXTURE:
        image.scale(TEXTURE, TEXTURE)
    image.filepath_raw = os.path.join(OUT, f"{TITLE}_{kind}.png")
    image.file_format = "PNG"
    image.save()

# Pictured on its head, flat (the maps as they are), front, side and back.
def textured(name, folders):
    material = bpy.data.materials.new(f"{name}_look")
    material.use_nodes = True
    for folder in folders:
        file = os.path.join(folder, f"{name}_Color.png")
        if os.path.exists(file):
            texture = material.node_tree.nodes.new("ShaderNodeTexImage")
            texture.image = bpy.data.images.load(file)
            material.node_tree.links.new(texture.outputs["Color"], material.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
            break
    return material


for slot in heads[first].material_slots:
    slot.material = textured(slot.material.name, (os.path.join(BODY_OUT, "Heads"), BODY_OUT))
shown = hm.materials[0].node_tree.nodes.new("ShaderNodeTexImage")   # the hair's own material draws its written map
shown.image = bpy.data.images.load(os.path.join(OUT, f"{TITLE}_Color.png"))
hm.materials[0].node_tree.nodes.active = shown
hm.materials[0].node_tree.links.new(shown.outputs["Color"], hm.materials[0].node_tree.nodes["Principled BSDF"].inputs["Base Color"])
for title, ob in heads.items():
    ob.hide_render = title != first
scene = bpy.context.scene
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light, scene.display.shading.color_type = "FLAT", "TEXTURE"
scene.display.render_aa = "8"
scene.view_settings.view_transform = "Standard"
scene.world = bpy.data.worlds.new("look")
scene.world.color = (0.5, 0.5, 0.5)
scene.render.resolution_x = scene.render.resolution_y = 900
pictures_as_jpeg(scene)
look = bpy.data.cameras.new("look")
look.type = "ORTHO"
look.ortho_scale = (crown - low) * 1.6
camera = bpy.data.objects.new("look", look)
scene.collection.objects.link(camera)
scene.camera = camera
middle = Vector(((min(c.x for c in head_co) + max(c.x for c in head_co)) / 2, (min(c.y for c in head_co) + max(c.y for c in head_co)) / 2, (low + crown) / 2))
for view, toward in {"front": Vector((0, 1, 0)), "side": Vector((-1, 0, 0)), "back": Vector((0, -1, 0))}.items():
    camera.location = middle - toward * 3
    camera.rotation_euler = (-toward).to_track_quat("Z", "Y").to_euler()
    scene.render.filepath = C.picture(f"hair_{view}_{first}")
    bpy.ops.render.render(write_still=True)
# The locks pictured: each lock its own colour, mixed by its weights, the cap grey; the hair seen through, each joint a
# ball as big as the lock is thick there. Then gone again: no colours or balls go to Forge.
if found_locks:
    palette = np.array([(0.95, 0.3, 0.2), (0.2, 0.6, 0.95), (0.3, 0.85, 0.35), (0.95, 0.8, 0.2), (0.75, 0.35, 0.9),
                        (0.2, 0.85, 0.85), (0.95, 0.5, 0.75), (0.6, 0.45, 0.25)])
    shade = hm.color_attributes.new("locks", "FLOAT_COLOR", "POINT")
    per_lock = lock_weights.sum(axis=2)
    for v in range(len(hm.vertices)):
        c = cap_weight[v] * np.array([0.55, 0.55, 0.55]) + sum(per_lock[v, i] * palette[i % len(palette)] for i in range(len(found_locks)))
        shade.data[v].color = (*c, 1.0)
    hm.color_attributes.active_color = shade
    balls = []
    for lock in found_locks:
        for k, joint in enumerate(lock["joints"]):
            radius = lock["radii"][k - 1] if k > 0 else 0.006
            bpy.ops.mesh.primitive_uv_sphere_add(radius=float(radius), location=Vector(joint), segments=12, ring_count=8)
            balls.append(bpy.context.active_object)
    scene.display.shading.color_type = "VERTEX"
    scene.display.shading.show_xray = True
    scene.display.shading.xray_alpha = 0.55
    for view, toward in {"front": Vector((0, 1, 0)), "side": Vector((-1, 0, 0)), "back": Vector((0, -1, 0)), "other_side": Vector((1, 0, 0))}.items():
        camera.location = middle - toward * 3
        camera.rotation_euler = (-toward).to_track_quat("Z", "Y").to_euler()
        scene.render.filepath = C.picture(f"locks_{view}_{first}")
        bpy.ops.render.render(write_still=True)
    scene.display.shading.show_xray = False
    for ball in balls:
        bpy.data.objects.remove(ball, do_unlink=True)
    hm.color_attributes.remove(shade)

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
