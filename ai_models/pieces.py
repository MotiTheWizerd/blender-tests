"""The step after Mixamo for a replaceable body: its rigged mesh cut into the pieces equipment replaces, as Skyrim's.

    blender -b --factory-startup -P pieces.py -- body_warrior_m

Reads <name>/source_mixamo.fbx (Mixamo's download, with skin; private, as the Tripo source is), the AI's colour map
(the reduced mesh kept its UVs) and reduce's baked normal map. Cuts the mesh into four pieces on the one skeleton:

  Body    torso, arms and legs       replaced by a cuirass, a robe, clothes
  Head    above the neck seam        replaced by the face editor's head (and a full helm)
  Hands   past the wrist seams       replaced by gauntlets, gloves
  Feet    below the ankle seams      replaced by boots

A seam is a plane square to a bone, through a point part way along it (SEAMS), found from the rig, so every body
Mixamo rigs is cut at the same places. The plane cuts only the limb it crosses near that point (faces within REACH
whose vertices the limb's bones weigh most), so a wrist's plane never slices the thigh beside the hand; the piece is
what is reached from the limb's end (the crown, a fingertip, a toe) without crossing the cut. A cut that leaves a gap
would let that reach run into the rest of the body; it is refused.

The two sides of a seam keep the same vertices: the same place, the same weights (a cut's new vertex is weighed
between its edge's ends) and the same normal (each piece's custom normals are the whole body's smooth ones), so no
line shows where they meet. checks/pieces.json says so in numbers, measured on the pieces and again on the exported
FBX read back: for each seam's two sides, how many vertices, how far apart (mm) and how far their normals turn (deg).

Writes build/forge/<Title>/: <Title>.fbx (the pieces as meshes "Body", "Head", "Hands", "Feet" bound to the
skeleton; no clip), <Title>_Color.png and <Title>_Normal.png (TEXTURE px), for Forge's Content/Characters/<Title>;
and checks/pieces_front.jpg, pieces_back.jpg, pieces_side.jpg (each piece its own colour, from the FBX read back).
"""
import bmesh, bpy, json, math, os, sys
import numpy as np
from collections import deque
from mathutils import Vector
from mathutils.kdtree import KDTree

ARGS = sys.argv[sys.argv.index("--") + 1:]
NAME = ARGS[0]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from place import Creature, pictures_as_jpeg
C = Creature(NAME)
Title = C.title
SOURCE = os.path.join(C.root, "source_mixamo.fbx")
# model.json "head" (optional): the head_* model whose head (head.py's) takes the Head piece's place (neck.py), at
# "head_scale" times its own size (1: a real head's). "--head-scale S" tries another size: its pictures and numbers
# are tagged with it, and its export goes to build/forge_<tag>/, leaving the real one alone.
HEAD = C.spec.get("head")
HEAD_SCALE = float(ARGS[ARGS.index("--head-scale") + 1]) if "--head-scale" in ARGS else C.spec.get("head_scale", 1.0)
# model.json "skin_even" (optional, 0 to 1): how much of the large dark and light patches the AI painted into the
# body's skin (baked shading, grime) is evened out; its pores and creases stay. 0: as made.
SKIN_EVEN = C.spec.get("skin_even", 0.0)
TAG = f"_head{HEAD_SCALE:g}" if "--head-scale" in ARGS else ""
OUT = C.build("forge" + TAG, Title)
TEXTURE = 4096
REACH = 0.15          # metres from a seam's point: how far its plane may cut
ON_PLANE = 1e-4       # a vertex this near a seam's plane is on it (0.1 mm), so the cut leaves no slivers
HOLE_SIDES = 24       # the AI's holes closed before the cut: up to this many edges round
PIECES = ("Body", "Head", "Hands", "Feet")    # Body first: what no seam takes

# A seam: its name, the bone it crosses (from, to, how far along), whether a bone (its name less the rig's prefix) is
# of the limb it cuts, the piece past it, and the bone at the limb's end the piece is reached from.
SEAMS = [("neck", "Neck", "Head", 0.4,
          lambda b: b in ("Neck", "Head", "HeadTop_End", "LeftEye", "RightEye", "Spine2", "LeftShoulder", "RightShoulder"),
          "Head", "HeadTop_End")]
for side in ("Left", "Right"):
    SEAMS.append((f"wrist.{side[0]}", f"{side}ForeArm", f"{side}Hand", 0.8,
                  lambda b, s=side: b == f"{s}ForeArm" or b.startswith(f"{s}Hand"), "Hands", f"{side}HandMiddle4"))
    SEAMS.append((f"ankle.{side[0]}", f"{side}Leg", f"{side}Foot", 0.8,
                  lambda b, s=side: b in (f"{s}Leg", f"{s}Foot", f"{s}ToeBase", f"{s}Toe_End"), "Feet", f"{side}Toe_End"))

os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=SOURCE)
scene = bpy.context.scene
rig = next(o for o in scene.objects if o.type == "ARMATURE")
body = next(o for o in scene.objects if o.type == "MESH")
for action in list(bpy.data.actions):           # Mixamo's two-frame "clip": the skeleton stands in its rest pose
    bpy.data.actions.remove(action)
rig.animation_data_clear()
prefix = next(b.name for b in rig.data.bones if b.name.endswith("Hips"))[:-len("Hips")]   # "mixamorig:"
to_mesh = body.matrix_world.inverted()


def joint(bone):
    """A bone's head, in the mesh's frame."""
    return to_mesh @ (rig.matrix_world @ rig.data.bones[prefix + bone].head_local)


me = body.data
bm = bmesh.new(); bm.from_mesh(me)
deform = bm.verts.layers.deform.active
# The AI's small holes (an ear's fold, the mouth, specks the reduce left) closed first: a piece's only open edge is
# then its seam, and nothing shows through. A hole is HOLE_SIDES edges at most; the new faces take existing vertices,
# so their weights are the body's.
open_before = sum(1 for e in bm.edges if e.is_boundary)
closed = bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=HOLE_SIDES)["faces"]
for f in closed:
    f.smooth = True
group_bone = {g.index: g.name[len(prefix):] if g.name.startswith(prefix) else g.name for g in body.vertex_groups}
cut_at = bm.verts.layers.int.new("seam")       # the seam a vertex lies on, 1-based; 0 for none


def heaviest(v):
    weights = v[deform]
    return group_bone.get(max(weights.items(), key=lambda kv: kv[1])[0]) if len(weights) else None


report = {"source": os.path.basename(SOURCE), "triangles_source": len(bm.faces) - len(closed),
          "open_edges_source": open_before, "holes_closed": len(closed),
          "open_edges_left": sum(1 for e in bm.edges if e.is_boundary), "seams": {}}
planes = []
for i, (seam, a, b, along, of_limb, piece, end) in enumerate(SEAMS):
    point = joint(a).lerp(joint(b), along)
    normal = (joint(b) - joint(a)).normalized()     # pointing past the seam, into the piece
    planes.append((point, normal))
    near = [f for f in bm.faces if (f.calc_center_median() - point).length < REACH
            and any(of_limb(heaviest(v) or "") for v in f.verts)]
    edges = {e for f in near for e in f.edges}
    verts = {v for f in near for v in f.verts}
    cut = bmesh.ops.bisect_plane(bm, geom=near + list(edges) + list(verts), dist=ON_PLANE, plane_co=point,
                                 plane_no=normal)["geom_cut"]
    ring = [g for g in cut if isinstance(g, bmesh.types.BMVert)]
    for v in ring:
        v[cut_at] = i + 1
    report["seams"][seam] = {"bone": f"{a} -> {b} at {along}", "point_m": [round(c, 3) for c in point],
                             "faces_cut": len(near), "ring_vertices": len(ring)}
# A cut face is a triangle and a quad: triangles all, as the rest are.
bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])

# Each piece is what its limb's end reaches without crossing its seam's cut. Faces touching at a vertex reach each
# other (the AI joins an ear's fold to the head at a point), unless that vertex is on the cut: the seam's other side.
piece_of = bm.faces.layers.int.new("piece")
bm.verts.ensure_lookup_table()
tree = KDTree(len(bm.verts))
for v in bm.verts:
    tree.insert(v.co, v.index)
tree.balance()
hips_faces = set(bm.verts[tree.find(joint("Hips"))[1]].link_faces)


def spread(start, through):
    """The faces reached from start, from face to face over their vertices while through(vertex)."""
    reached, todo = set(start), deque(start)
    while todo:
        for v in todo.popleft().verts:
            if through(v):
                for g in v.link_faces:
                    if g not in reached:
                        reached.add(g); todo.append(g)
    return reached


for i, (seam, a, b, along, of_limb, piece, end) in enumerate(SEAMS):
    seed = bm.verts[tree.find(joint(end))[1]]
    reached = spread(seed.link_faces, lambda v, i=i: v[cut_at] != i + 1)
    if reached & hips_faces or len(reached) > len(bm.faces) // 4:
        raise SystemExit(f"PIECES the {seam} cut leaves a gap: {piece} reached {len(reached)} of {len(bm.faces)} faces")
    for f in reached:
        if f[piece_of]:
            raise SystemExit(f"PIECES {piece} ({seam}) runs into {PIECES[f[piece_of]]}")
        f[piece_of] = PIECES.index(piece)
    report["seams"][seam]["piece_faces"] = len(reached)

# What is left loose of the body (a bit of the AI's mesh joined to nothing) goes with the piece past whose seam it
# lies (the nearest, within REACH twice), else stays with the body.
rest = {f for f in bm.faces if not f[piece_of]}
main = spread(hips_faces & rest, lambda v: True) & rest
loose, rest = [], rest - main
while rest:
    island = spread([next(iter(rest))], lambda v: True) & rest
    rest -= island
    centre = sum((f.calc_center_median() for f in island), Vector()) / len(island)
    past = [(i, (centre - planes[i][0]).length) for i in range(len(SEAMS))
            if (centre - planes[i][0]).dot(planes[i][1]) > 0 and (centre - planes[i][0]).length < 2 * REACH]
    if past:
        seam = min(past, key=lambda p: p[1])[0]
        for f in island:
            f[piece_of] = PIECES.index(SEAMS[seam][5])
    loose.append({"faces": len(island), "centre_m": [round(c, 3) for c in centre],
                  "to": SEAMS[min(past, key=lambda p: p[1])[0]][5] if past else "Body"})
report["loose"] = loose

bm.verts.index_update()
whole_index = bm.verts.layers.int.new("whole")
for v in bm.verts:
    v[whole_index] = v.index
bm.to_mesh(me); bm.free()
me.shade_smooth()
me.update()
whole_normals = [v.normal.copy() for v in me.vertices]   # across every seam: both sides' faces

# The pieces: copies of the cut body, each keeping its own faces, on the same skeleton with the same weights.
pieces = []
for k, name in enumerate(PIECES):
    ob = body.copy(); ob.data = me.copy()
    ob.name = ob.data.name = name
    for collection in body.users_collection:
        collection.objects.link(ob)
    pbm = bmesh.new(); pbm.from_mesh(ob.data)
    layer = pbm.faces.layers.int["piece"]
    bmesh.ops.delete(pbm, geom=[f for f in pbm.faces if f[layer] != k], context="FACES_ONLY")
    bmesh.ops.delete(pbm, geom=[v for v in pbm.verts if not v.link_faces], context="VERTS")
    pbm.to_mesh(ob.data); pbm.free()
    whole = ob.data.attributes["whole"].data
    ob.data.normals_split_custom_set_from_vertices([whole_normals[whole[j].value] for j in range(len(ob.data.vertices))])
    for attribute in ("whole", "piece", "seam"):
        if attribute in ob.data.attributes:
            ob.data.attributes.remove(ob.data.attributes[attribute])
    pieces.append(ob)
world_planes = [(body.matrix_world @ p, (body.matrix_world.to_3x3() @ n).normalized()) for p, n in planes]
bpy.data.objects.remove(body, do_unlink=True)

# The face editor's head in the Head piece's place, on the neck seam (neck.py); the body's maps and the head's then
# share one texture, the body's on the left half and the head's on the right.
skin = None
if HEAD:
    from glob import glob
    from neck import seat
    made = glob(os.path.join(os.path.dirname(C.root), HEAD, "build", "forge", "*", "*.fbx"))
    if len(made) != 1:
        raise SystemExit(f"PIECES the head {HEAD} has {len(made)} exports (run head.py)")
    at = next(i for i, p in enumerate(pieces) if p.name == "Head")
    own = pieces[at]
    head, seated = seat(made[0], own, *world_planes[0], scale=HEAD_SCALE)
    own_mesh = own.data
    bpy.data.objects.remove(own, do_unlink=True)
    bpy.data.meshes.remove(own_mesh)
    head.name = head.data.name = "Head"
    pieces[at] = head
    fade = seated.pop("fade_triangles")
    report["head"] = dict(seated, source=os.path.relpath(made[0], os.path.dirname(C.root)).replace(os.sep, "/"),
                          fade_triangles=len(fade))
    # Into the atlas: the body's faces (and the head's collar, which draws the body's skin) to the left half, the
    # head's own to the right.
    for ob in pieces:
        mesh = ob.data
        layer = mesh.uv_layers.active.data
        uvs = np.empty(len(layer) * 2, dtype=np.float32)
        layer.foreach_get("uv", uvs)
        right = np.zeros(len(mesh.polygons), dtype=bool)
        if ob is head:
            from_body = np.empty(len(mesh.polygons), dtype=np.int32)
            mesh.attributes["skin_from_body"].data.foreach_get("value", from_body)
            right = from_body == 0
            mesh.attributes.remove(mesh.attributes["skin_from_body"])
        totals = np.empty(len(mesh.polygons), dtype=np.int32)
        mesh.polygons.foreach_get("loop_total", totals)
        uvs[0::2] = uvs[0::2] * 0.5 + np.where(np.repeat(right, totals), 0.5, 0.0)
        layer.foreach_set("uv", uvs)


def seam_match(objects):
    """Each seam's two sides (its piece's open edge on the plane against the Body's): how many vertices each, how far
    apart at most (mm), how far their normals turn at most (degrees); and each piece's open edges on no seam."""
    rims = {}
    for ob in objects:
        mesh = ob.data
        b = bmesh.new(); b.from_mesh(mesh)
        rim = {v.index for e in b.edges if e.is_boundary for v in e.verts}
        b.free()
        normals = {i: Vector() for i in rim}
        for loop, corner in zip(mesh.loops, mesh.corner_normals):
            if loop.vertex_index in normals:
                normals[loop.vertex_index] += corner.vector
        world = ob.matrix_world
        rims[ob.name] = [(world @ mesh.vertices[i].co, (world.to_3x3() @ n).normalized()) for i, n in normals.items()]

    def on(seam, rim):
        point, normal = world_planes[seam]
        return [(co, n) for co, n in rim if abs((co - point).dot(normal)) < 10 * ON_PLANE and (co - point).length < REACH]

    result = {}
    for i, (seam, *_, piece, end) in enumerate(SEAMS):
        inside, outside = on(i, rims[piece]), on(i, rims["Body"])
        tree = KDTree(max(len(outside), 1))
        for j, (co, _) in enumerate(outside):
            tree.insert(co, j)
        tree.balance()
        far = turn = 0.0
        for co, n in inside:
            _, j, distance = tree.find(co)
            far = max(far, distance)
            turn = max(turn, math.degrees(n.angle(outside[j][1], 0.0)))
        result[seam] = {piece: len(inside), "Body": len(outside), "apart_mm": round(far * 1000, 4),
                        "turn_deg": round(turn, 3)}
    result["open_edge_vertices_on_no_seam"] = {
        name: sum(1 for co, n in rim if not any(on(i, [(co, n)]) for i in range(len(SEAMS)))) for name, rim in rims.items()}
    return result


report["seams_on_pieces"] = seam_match(pieces)
report["triangles"] = {ob.name: len(ob.data.polygons) for ob in pieces}

# The maps, as Forge's characters take them: the AI's colour (the reduced mesh kept its UVs) and reduce's normal bake;
# with a head, its maps beside them (head.py's), its skin matched to the body's.
def pixels(path):
    image = bpy.data.images.load(path)
    if image.size[0] != TEXTURE:
        image.scale(TEXTURE, TEXTURE)
    array = np.empty(TEXTURE * TEXTURE * 4, dtype=np.float32)
    image.pixels.foreach_get(array)
    bpy.data.images.remove(image)
    return array.reshape(TEXTURE, TEXTURE, 4)


def save(array, suffix, space):
    image = bpy.data.images.new(f"{Title}_{suffix}", array.shape[1], array.shape[0], alpha=False)
    image.colorspace_settings.name = space
    image.pixels.foreach_set(array.ravel())
    image.filepath_raw = os.path.join(OUT, f"{Title}_{suffix}.png")
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)


def linear(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def encoded(c):
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def paint(target, triangles, under_at):
    """Over each triangle of the fade, in target (the head's map): what lies under it (under_at, from the body's UVs)
    mixed under the head's own by how much of the head's shows there, so the head's skin comes out of the body's."""
    size = np.array([target.shape[1] - 1, target.shape[0] - 1])
    for head_uv, body_uv, shows in triangles:
        p = np.array(head_uv) * size
        lo = np.maximum(np.floor(p.min(0)).astype(int) - 1, 0)
        hi = np.minimum(np.ceil(p.max(0)).astype(int) + 1, size)
        xs, ys = np.meshgrid(np.arange(lo[0], hi[0] + 1), np.arange(lo[1], hi[1] + 1))
        e1, e2 = p[1] - p[0], p[2] - p[0]
        det = e1[0] * e2[1] - e1[1] * e2[0]
        if abs(det) < 1e-9:
            continue
        dx, dy = xs - p[0][0], ys - p[0][1]
        b1, b2 = (dx * e2[1] - dy * e2[0]) / det, (e1[0] * dy - e1[1] * dx) / det
        b0 = 1 - b1 - b2
        slack = 1.0 / max(np.linalg.norm(e1), np.linalg.norm(e2), 1.0)     # about a pixel past each edge
        inside = (b0 >= -slack) & (b1 >= -slack) & (b2 >= -slack)
        if not inside.any():
            continue
        w = np.stack([b0[inside], b1[inside], b2[inside]], 1).clip(0, None)
        w /= w.sum(1, keepdims=True)
        t = (w @ np.array(shows))[:, None]
        yi, xi = ys[inside], xs[inside]
        target[yi, xi, :3] = under_at(w @ np.array(body_uv)) * (1 - t) + target[yi, xi, :3] * t


def skin_of(array):
    """Where a colour map is skin: warm (red over blue), not the black between its islands, the grey of cloth, the
    whites and blues of eyes, or the glare some maps pad their islands with."""
    r, g, b = array[..., 0], array[..., 1], array[..., 2]
    return (r > 0.15) & (r - b > 0.06) & (r >= g) & (0.2126 * r + 0.7152 * g + 0.0722 * b < 0.92)


def box(x, r):
    """Each place's sum over the square 2r + 1 round it (zero past the edges)."""
    n = 2 * r + 1
    c = np.pad(x, ((r + 1, r), (r + 1, r))).cumsum(0).cumsum(1)
    return c[n:, n:] - c[:-n, n:] - c[n:, :-n] + c[:-n, :-n]


def even(array, strength, step=4, reach=12):
    """The skin of a colour map with its large dark and light patches evened out by strength (0 none, 1 flat): each
    skin pixel's brightness against its neighbourhood's (reach pixels of a map step times smaller round it: about 1%
    of the map, skin only), moved toward the skin's middle brightness. Pores and creases, finer than that, stay."""
    mask = skin_of(array)
    lum = linear(array[..., :3]) @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    h, w = mask.shape
    coarse = lambda x: x.reshape(h // step, step, w // step, step).mean((1, 3))
    around = box(coarse(lum * mask), reach) / np.maximum(box(coarse(mask.astype(np.float32)), reach), 1e-6)
    around = np.repeat(np.repeat(around, step, 0), step, 1)
    factor = np.clip((np.median(lum[mask]) / np.maximum(around, 1e-4)) ** strength, 0.6, 1.6)
    colour = linear(array[..., :3])
    colour[mask] *= factor[mask][:, None]
    array[..., :3] = encoded(colour)
    return float(np.percentile(factor[mask], 5)), float(np.percentile(factor[mask], 95))


body_maps = (os.path.join(C.root, "source_tripo.fbm", "Color.jpg"), C.build(f"{Title}_Normal.png"))
if HEAD:
    folder = os.path.dirname(made[0])
    head_title = os.path.basename(folder)
    body_colour, head_colour = pixels(body_maps[0]), pixels(os.path.join(folder, f"{head_title}_BaseColor.jpg"))
    if SKIN_EVEN:
        report["skin_even"] = {"strength": SKIN_EVEN, "factor_p5_p95": [round(f, 3) for f in even(body_colour, SKIN_EVEN)]}
    # The head's skin to the body's colour: their whole skins' middles (linear), not a strip of either.
    gain = (np.median(linear(body_colour[..., :3][skin_of(body_colour)]), 0)
            / np.median(linear(head_colour[..., :3][skin_of(head_colour)]), 0))
    head_colour[..., :3] = encoded(linear(head_colour[..., :3]) * gain)
    report["head"]["skin_gain_rgb"] = [round(float(g), 3) for g in gain]

    def body_at(uvs):
        at = np.clip(uvs, 0.0, 1.0)
        return body_colour[(at[:, 1] * (TEXTURE - 1)).astype(int), (at[:, 0] * (TEXTURE - 1)).astype(int), :3]

    paint(head_colour, fade, body_at)
    save(np.concatenate([body_colour, head_colour], axis=1), "Color", "sRGB")
    del body_colour, head_colour
    # The normals likewise come out of flat where the head's skin meets the body's (the two maps' frames differ).
    head_normal = pixels(os.path.join(folder, f"{head_title}_Normal.png"))
    paint(head_normal, fade, lambda uvs: np.array([0.5, 0.5, 1.0]))
    save(np.concatenate([pixels(body_maps[1]), head_normal], axis=1), "Normal", "Non-Color")
else:
    save(pixels(body_maps[0]), "Color", "sRGB")
    save(pixels(body_maps[1]), "Normal", "Non-Color")

fbx = os.path.join(OUT, f"{Title}.fbx")
bpy.ops.object.select_all(action="DESELECT")
bpy.ops.export_scene.fbx(filepath=fbx, use_selection=False, object_types={"ARMATURE", "MESH"}, apply_unit_scale=True,
                         apply_scale_options="FBX_SCALE_ALL", add_leaf_bones=False, bake_anim=False,
                         mesh_smooth_type="FACE", path_mode="STRIP")

# What Forge will read: the FBX back, measured again, and pictured.
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=fbx)
scene = bpy.context.scene
read_back = [o for o in scene.objects if o.type == "MESH"]
report["meshes_in_fbx"] = sorted(o.name for o in read_back)
report["bones_in_fbx"] = sum(len(o.data.bones) for o in scene.objects if o.type == "ARMATURE")
report["seams_in_fbx"] = seam_match(read_back)
report["shape_keys_in_fbx"] = {o.name: [k.name for k in o.data.shape_keys.key_blocks[1:]] for o in read_back
                               if o.data.shape_keys}
json.dump(report, open(C.checks(f"pieces{TAG}.json"), "w"), indent=1)

colours = {"Body": (0.62, 0.62, 0.6, 1), "Head": (0.85, 0.35, 0.3, 1), "Hands": (0.3, 0.55, 0.85, 1),
           "Feet": (0.35, 0.7, 0.35, 1)}
for ob in read_back:
    ob.color = colours[ob.name]
height = max((o.matrix_world @ Vector(c)).z for o in read_back for c in o.bound_box)
pictures_as_jpeg(scene)
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"; scene.display.shading.color_type = "OBJECT"
scene.render.resolution_x, scene.render.resolution_y = 800, 1000
scene.world = bpy.data.worlds.new("w")
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam); scene.camera = cam
cam.data.type = "ORTHO"; cam.data.ortho_scale = height * 1.1
for view, d in {"front": (0, -1, 0), "back": (0, 1, 0), "side": (1, 0, 0)}.items():
    d = Vector(d)
    cam.location = Vector((0, 0, height / 2)) + d * 5
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = C.picture(f"pieces_{view}{TAG}")
    bpy.ops.render.render(write_still=True)

# With a head: the neck close, in its colours, where a seam or a step would show.
if HEAD:
    material = bpy.data.materials.new("skin")
    material.use_nodes = True
    texture = material.node_tree.nodes.new("ShaderNodeTexImage")
    texture.image = bpy.data.images.load(os.path.join(OUT, f"{Title}_Color.png"))
    material.node_tree.links.new(texture.outputs["Color"], material.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
    material.node_tree.nodes.active = texture
    for ob in read_back:
        ob.data.materials.clear()
        ob.data.materials.append(material)
    scene.display.shading.color_type = "TEXTURE"
    scene.render.resolution_x = scene.render.resolution_y = 800
    neck = world_planes[0][0] + Vector((0, 0, 0.07))
    for name, ortho, centre in (("whole", height * 1.1, Vector((0, 0, height / 2))), ("neck", 0.42, neck)):
        cam.data.ortho_scale = ortho
        for view, d in {"front": (0, -1, 0), "three_quarter": (0.7, -0.7, 0), "side": (1, 0, 0), "back": (0, 1, 0)}.items():
            if name == "whole" and view != "front":
                continue
            d = Vector(d).normalized()
            cam.location = centre + d * 5
            cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
            scene.render.filepath = C.picture(f"{name}_{view}{TAG}")
            bpy.ops.render.render(write_still=True)

print("PIECES", json.dumps(report))
