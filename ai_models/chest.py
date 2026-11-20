"""A chest of another shape laid onto a replaceable body, as one of its body types: pieces.py calls lay() for each
chest_* folder the body's model.json lists under "chests" (Tripo's source_tripo.glb: a woman's chest from the neck to
under the breasts, made from a picture), on a copy of the body after its torso and its breasts' bones, so the type keeps
the body's skeleton, weights and topology: only where her breasts stand and what they draw change.

Unlike torso.py's torso (her own shape, edited), a chest of another shape cannot be laid on vertex by vertex onto the
nearest point (s1023, measured: her sparse skin under a rounder breast lands on the ribs below and folds; along her
normals it spikes at the nipple). So:

  The fit: started by the nipples, then one scale and a shift (ICP) on the chest's FRAME only (breastbone, collarbones,
  ribs; not its breasts, which would pull it toward hers, nor its arms, which a picture's chest hangs straight down).
  The shape: her breasts' region (her vertices within REACH of either nipple, not her arms'); its edge held still; in its
  CORE each vertex goes where the line from a point inside her chest behind the nipple through it leaves the chest's
  surface (a breast is a dome round that point: each line meets it once, so neighbours stay neighbours), turned so the
  line through her nipple meets the chest's nipple; every other vertex takes its neighbours' mean move (a harmonic fill),
  so the move eases to the held edge with no step. The surface aimed at is the chest reduced to about her density:
  finer detail (the nipple's tip, the areola's bumps) comes through the normal map.
  The maps: the region's faces get their own material (<Title>, the chest's) and UVs, baked from the full chest
  (selected to active, near then far as torso.py does); the faces near the held edge fade into what was under them
  (pieces.py paints it, as for a head's neck), so the skin has no line.
  The size (the chest's model.json "size"; 1: as the picture): a picture carries a breast only in proportion to its
  frame, and every woman's breast is about three quarters of her nipples' spacing wide (measured s1024: her own 0.70,
  two chests 0.73 and 0.75, laid on her 0.79 and 0.75), so from the front every type has the same footprint and only
  its depth differs. For a breast beyond any picture's, each vertex's stand over the chest wall (the region relaxed
  to its held edge, a harmonic surface, so the wall is her ribs with the breasts taken off) is grown by the size along
  her normal, and a share of the growth (SAG) goes downward, so the extra is depth and hang, not a wider base (the
  base is where the stand is nothing, so it stays; nothing slides along the wall, so nothing folds under). The maps
  are baked before the growth, so the grown surface wears them stretched rather than missing the chest.

Works in the body mesh's frame, which is the world's: metres, front -Y, up Z.

Tripo's chest comes at about 2M triangles; held whole inside pieces.py beside everything else it ran this 16 GB PC out
of memory (s1023: Blender and the Unity editor died together). So it is made smaller once, on its own:

    blender -b --factory-startup -P chest.py -- chest_warrior_f2

welds its UV-seam splits, reduces it to SOURCE_FACES and saves it with its maps packed as build/reduced.blend, which
lay() reads (and refuses to run without).
"""
import math
import os
import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

REACH = 0.62        # her breasts' region: within this times her nipples' spacing of either nipple
CORE = 0.75         # of REACH: where vertices are aimed at the chest; beyond, filled from their neighbours
BEHIND = Vector((0, 0.07, -0.01))   # the point inside her chest the lines start from, from each nipple (metres)
FIT_LEAVES = 0.5    # the fit leaves out the chest within this times its nipples' spacing of either nipple
FIT_MIDDLE = 0.3    # and keeps its middle: within this share of its width of its centre (not its arms)
FIT_STEPS = 40
FIT_KEEP = 0.8
ARM_MOST = 0.3      # a vertex the arms' bones weigh more than this stays hers
CAP_BAND, CAP_FACING = 0.15, 0.7    # Tripo's flat caps over its cuts, as torso.py finds them
NEAR_CUT = 0.015    # a line meeting the chest this near its cut (metres) has no answer there
SOURCE_FACES = 300000   # the chest made this small once (prepare()): its detail for the bake, with its normal map
SHAPE_FACES = 90000     # and smaller again for the shape her surface takes
FILL_STEPS = 400
SMOOTH_STEPS = 3
TEX_FADE = 0.03     # metres in from the held edge over which the chest's maps come in
FULL_STAND = 0.01   # a vertex standing this far (metres) over the chest wall is wholly the breast's, for the size
SAG = 0.5           # of the size's growth goes downward too, so a bigger breast hangs as well as stands
GROW_SMOOTH = 36    # the stand and her normal smoothed over this many steps (about 5 cm) before the growth
MIDLINE = 0.004     # a breast grown into the other stops this far (metres) from the breastbone's line
TEXTURE = 4096
NEAR, FAR = 0.003, 0.02             # the bake's cage, as torso.py's
MISS = (1.0, 0.0, 1.0, 1.0)


def smoothstep(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def forward_pair(co, keep):
    """The most forward point (least y) on each side (x < 0, x > 0) among co where keep: a woman's nipples."""
    left = min((c for c, k in zip(co, keep) if k and c.x < 0), key=lambda c: c.y)
    right = min((c for c, k in zip(co, keep) if k and c.x > 0), key=lambda c: c.y)
    return left, right


REDUCED = "reduced.blend"


def prepare(folder, name):
    """Tripo's GLB as lay() reads it: one mesh in the world's frame, its UV-seam splits welded (a glTF splits its
    vertices along every seam), reduced to SOURCE_FACES, saved with its maps packed as build/reduced.blend."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=os.path.abspath(os.path.join(folder, "source_tripo.glb")))
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if len(meshes) != 1:
        raise SystemExit(f"CHEST {name} has {len(meshes)} meshes")
    high = meshes[0]
    world = high.matrix_world.copy()
    high.parent = None
    high.data.transform(world)
    high.matrix_world = Matrix.Identity(4)
    for o in [o for o in bpy.data.objects if o is not high]:
        bpy.data.objects.remove(o, do_unlink=True)
    high.name = "Chest"
    faces = len(high.data.polygons)
    bm = bmesh.new(); bm.from_mesh(high.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bm.to_mesh(high.data); bm.free()
    bpy.context.view_layer.objects.active = high
    high.modifiers.new("reduce", "DECIMATE").ratio = min(1.0, SOURCE_FACES / faces)
    bpy.ops.object.modifier_apply(modifier="reduce")
    bpy.ops.file.pack_all()
    os.makedirs(os.path.join(folder, "build"), exist_ok=True)
    path = os.path.join(folder, "build", REDUCED)
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=True)
    print(f"CHEST {name}: {faces} faces -> {len(high.data.polygons)}, saved {path}")


def load_chest(folder, name):
    """The chest as prepare() saved it, linked into this scene: one mesh in the world's frame, its glTF material (colour
    and normal map) as it came."""
    path = os.path.join(folder, "build", REDUCED)
    if not os.path.exists(path):
        raise SystemExit(f"CHEST {name}: no {path} (run: blender -b --factory-startup -P chest.py -- {name})")
    with bpy.data.libraries.load(path) as (source, target):
        target.objects = ["Chest"]
    high = target.objects[0]
    bpy.context.scene.collection.objects.link(high)
    return high


def lay(body, folder, name, title, body_piece=0, torso_segment=0, size=1.0):
    """Lays the chest of folder onto body (the whole cut body, as pieces.py has it after the torso), its breasts grown
    by size (1: as the picture). Returns the report, the baked maps' paths (Color, Normal) and (triangles, edges): each
    covered triangle's corners' UVs on the chest's map, the UVs under them, how much of the chest shows at each, the
    material under and its vertices; the covered vertices' edges."""
    if any(abs(a - b) > 1e-5 for row_a, row_b in zip(body.matrix_world, Matrix.Identity(4)) for a, b in zip(row_a, row_b)):
        raise SystemExit("CHEST the body's mesh is not in the world's frame")
    me = body.data
    piece = [a.value for a in me.attributes["piece"].data]
    segment = [a.value for a in me.attributes["segment"].data]
    on_body = [i for i, f in enumerate(me.polygons) if piece[i] == body_piece]
    body_verts = {v for i in on_body for v in me.polygons[i].vertices}
    arm_groups = {g.index for g in body.vertex_groups if "Arm" in g.name}
    arm_weight = [sum(g.weight for g in v.groups if g.group in arm_groups) for v in me.vertices]

    # Her nipples, as torso.py finds them.
    torso_verts = {v for i in on_body if segment[i] == torso_segment for v in me.polygons[i].vertices}
    zs = sorted(me.vertices[v].co.z for v in torso_verts)
    lo, hi = zs[0], zs[-1]
    co = [me.vertices[v].co for v in torso_verts]
    hers = forward_pair(co, [lo + (hi - lo) * 0.4 < c.z < lo + (hi - lo) * 0.85 and abs(c.x) < 0.15 for c in co])
    spacing = (hers[1] - hers[0]).length
    body_bvh = BVHTree.FromPolygons([v.co.copy() for v in me.vertices], [tuple(me.polygons[i].vertices) for i in on_body])

    # The fit.
    high = load_chest(folder, name)
    hco = np.empty(len(high.data.vertices) * 3, dtype=np.float64)
    high.data.vertices.foreach_get("co", hco)
    hco = hco.reshape(-1, 3)
    lo_x, hi_x, lo_z, hi_z = hco[:, 0].min(), hco[:, 0].max(), hco[:, 2].min(), hco[:, 2].max()
    middle = (lo_x + hi_x) / 2
    central = np.abs(hco[:, 0] - middle) < FIT_MIDDLE * (hi_x - lo_x)
    upper = central & (hco[:, 2] > lo_z + (hi_z - lo_z) / 4)
    left, right = hco[upper & (hco[:, 0] < middle)], hco[upper & (hco[:, 0] > middle)]
    t_left, t_right = left[np.argmin(left[:, 1])], right[np.argmin(right[:, 1])]
    b_left, b_right = np.array(hers[0][:]), np.array(hers[1][:])
    scale = np.linalg.norm(b_right - b_left) / np.linalg.norm(t_right - t_left)
    shift = (b_left + b_right) / 2 - (t_left + t_right) / 2 * scale
    t_spacing = np.linalg.norm(t_right - t_left)
    frame = central & (np.linalg.norm(hco - t_left, axis=1) > FIT_LEAVES * t_spacing) \
        & (np.linalg.norm(hco - t_right, axis=1) > FIT_LEAVES * t_spacing)
    points = hco[frame][::max(1, int(frame.sum()) // 16000)]
    steps = []
    for _ in range(FIT_STEPS):
        moved = points * scale + shift
        near = np.array([body_bvh.find_nearest(Vector(p))[0][:] for p in moved])
        far = np.linalg.norm(near - moved, axis=1)
        keep = far <= np.quantile(far, FIT_KEEP)
        steps.append(float(np.median(far)))
        p, q = points[keep], near[keep]
        pm, qm = p.mean(0), q.mean(0)
        scale = float(((p - pm) * (q - qm)).sum() / ((p - pm) ** 2).sum())
        shift = qm - scale * pm
    high.data.transform(Matrix.Translation(Vector(shift)) @ Matrix.Diagonal(Vector((scale, scale, scale, 1.0))))
    high.data.update()
    theirs = [Vector(t_left * scale + shift), Vector(t_right * scale + shift)]
    report = {"fit": {"scale": round(scale, 4), "shift_m": [round(a, 4) for a in shift],
                      "median_off_mm_first_last": [round(steps[0] * 1000, 2), round(steps[-1] * 1000, 2)],
                      "nipples_body_m": [[round(c, 3) for c in n] for n in hers],
                      "nipples_chest_m": [[round(c, 3) for c in n] for n in theirs],
                      "nipples_apart_mm": [round((t - h).length * 1000, 1) for t, h in zip(theirs, hers)]}}

    # Its cuts: Tripo's caps taken off; a glTF splits its vertices along every UV seam, so they are welded first or
    # every seam would read as a cut.
    hbm = bmesh.new(); hbm.from_mesh(high.data)
    bmesh.ops.remove_doubles(hbm, verts=hbm.verts, dist=1e-6)
    zz = [v.co.z for v in hbm.verts]
    lz, hz = min(zz), max(zz)
    band = CAP_BAND * (hz - lz)
    caps = [f for f in hbm.faces if (f.calc_center_median().z < lz + band and f.normal.z < -CAP_FACING)
            or (f.calc_center_median().z > hz - band and f.normal.z > CAP_FACING)]
    bmesh.ops.delete(hbm, geom=caps, context="FACES")
    rim = [v.co.copy() for v in hbm.verts if v.is_boundary]
    hbm.to_mesh(high.data); hbm.free()
    high.data.update()
    report["cap_faces"] = len(caps)
    if not rim:
        raise SystemExit(f"CHEST {name}: no cut found at its ends")
    rim_tree = KDTree(len(rim))
    for k, c in enumerate(rim):
        rim_tree.insert(c, k)
    rim_tree.balance()

    # The surface aimed at: the chest reduced.
    shape = high.copy(); shape.data = high.data.copy()
    for c in high.users_collection:
        c.objects.link(shape)
    shape.modifiers.new("reduce", "DECIMATE").ratio = min(1.0, SHAPE_FACES / len(high.data.polygons))
    bpy.context.view_layer.update()
    evaluated = shape.evaluated_get(bpy.context.evaluated_depsgraph_get())
    low_mesh = evaluated.to_mesh()
    shape_bvh = BVHTree.FromPolygons([v.co.copy() for v in low_mesh.vertices], [tuple(p.vertices) for p in low_mesh.polygons])
    report["shape_faces"] = len(low_mesh.polygons)
    evaluated.to_mesh_clear()
    shape_data = shape.data
    bpy.data.objects.remove(shape, do_unlink=True)
    bpy.data.meshes.remove(shape_data)

    # The shape.
    reach = REACH * spacing
    bm = bmesh.new(); bm.from_mesh(me); bm.verts.ensure_lookup_table()
    region = {v for v in body_verts if arm_weight[v] <= ARM_MOST and min((me.vertices[v].co - n).length for n in hers) < reach}
    neighbours = {v: [e.other_vert(bm.verts[v]).index for e in bm.verts[v].link_edges] for v in region}
    held = {v for v in region if any(n not in region for n in neighbours[v])}
    move = {v: Vector() for v in region}
    fixed = set(held)
    turns = []
    for her, their in zip(hers, theirs):
        centre = her + BEHIND
        turns.append((her, centre, (her - centre).normalized().rotation_difference((their - centre).normalized())))
    aimed = missed = near_cut = 0
    for v in region - held:
        at = me.vertices[v].co
        her, centre, turn = min(turns, key=lambda t: (at - t[0]).length)
        d = (at - her).length
        if d > CORE * reach:
            continue
        line = Quaternion().slerp(turn, smoothstep(1 - d / (CORE * reach))) @ (at - centre).normalized()
        hit = shape_bvh.ray_cast(centre, line, 0.3)[0]
        if hit is None:
            missed += 1
            continue
        if rim_tree.find(hit)[2] < NEAR_CUT:
            near_cut += 1
            continue
        move[v] = hit - at
        fixed.add(v)
        aimed += 1
    free = [v for v in region if v not in fixed]
    for _ in range(FILL_STEPS):
        for v in free:
            around = [move[n] for n in neighbours[v] if n in move]
            move[v] = sum(around, Vector()) / len(around)
    for _ in range(SMOOTH_STEPS):
        smoothed = {}
        for v in region - held:
            around = [move[n] for n in neighbours[v] if n in move]
            smoothed[v] = (move[v] + sum(around, Vector()) / len(around)) / 2
        move.update(smoothed)

    # The size: the chest wall under her breasts is the region relaxed to its held edge; each vertex's stand over it,
    # once laid, grows by the size along her normal, a share of it downward. Applied after the bake (below).
    growth = {}
    stands = {}
    if size != 1.0:
        wall = {v: me.vertices[v].co.copy() for v in region}
        for _ in range(FILL_STEPS):
            for v in region - held:
                around = [wall[n] for n in neighbours[v] if n in wall]
                wall[v] = sum(around, Vector()) / len(around)
        # Each vertex's stand over the wall and her normal there, both smoothed over the mesh (GROW_SMOOTH steps), so
        # the growth is the breast's gross shape and not its detail: the chest's puffy areola grown with the rest stood
        # out as a disc with a rim, and neighbours grown along their own normals spread apart (size 2, seen s1024).
        normals = {v: me.vertices[v].normal.copy() for v in region}
        stands = {v: 0.0 for v in region}
        for v in region - held:
            stands[v] = (me.vertices[v].co + move[v] - wall[v]).dot(normals[v])
        raw = dict(stands)
        inside = {v: [n for n in neighbours[v] if n in stands] for v in region - held}
        for _ in range(GROW_SMOOTH):
            stands.update({v: (stands[v] + sum(stands[n] for n in inside[v]) / len(inside[v])) / 2 for v in inside})
            normals.update({v: (normals[v] + sum((normals[n] for n in inside[v]), Vector())).normalized() for v in inside})
        for v in region - held:
            grow = (size - 1) * smoothstep(stands[v] / FULL_STAND) * stands[v]
            if grow <= 0:
                continue
            g = grow * (normals[v] + SAG * Vector((0, 0, -1)))
            # Not through the middle: a breast grown into the other stops at the breastbone's line, pressed flat.
            x = (me.vertices[v].co + move[v]).x
            if x * (x + g.x) < 0 or abs(x + g.x) < MIDLINE:
                g.x = math.copysign(MIDLINE, x) - x
            growth[v] = g
    moves = []
    for v in region:
        me.vertices[v].co += move[v]
        moves.append(move[v].length)
    me.update()
    report.update({"region_vertices": len(region), "held": len(held), "aimed": aimed, "filled": len(free),
                   "missed": missed, "near_cut": near_cut,
                   "moved_mm_median_max": [round(float(np.median(moves)) * 1000, 2), round(float(max(moves)) * 1000, 2)]})
    if size != 1.0:
        nipple_verts = [min(region, key=lambda v: (me.vertices[v].co - move[v] - her).length) for her in hers]
        report["size"] = {"size": size, "grown_vertices": len(growth),
                          "nipple_stand_cm_laid": [round(raw.get(v, 0.0) * 100, 2) for v in nipple_verts],
                          "nipple_stand_cm_smoothed": [round(stands.get(v, 0.0) * 100, 2) for v in nipple_verts],
                          "nipple_grown_cm": [round(growth[v].length * 100, 2) if v in growth else 0.0 for v in nipple_verts],
                          "grown_mm_max": round(max(g.length for g in growth.values()) * 1000, 2) if growth else 0.0}

    # The maps' share: the region's faces, the chest showing by how far each corner is in from the held edge.
    covered = [p.index for p in me.polygons if piece[p.index] == body_piece and all(v in region for v in p.vertices)]
    covered_set = set(covered)
    tree = KDTree(len(held))
    for v in held:
        tree.insert(me.vertices[v].co, v)
    tree.balance()
    shows = {v: 0.0 if v in held else smoothstep(tree.find(me.vertices[v].co)[2] / TEX_FADE)
             for p in covered for v in me.polygons[p].vertices}
    bm.free()
    uv = me.uv_layers[0]
    under_uv = {l: tuple(uv.data[l].uv) for i in covered for l in me.polygons[i].loop_indices}
    under_material = {i: me.materials[me.polygons[i].material_index].name for i in covered}
    material = bpy.data.materials.new(title)
    me.materials.append(material)
    slot = len(me.materials) - 1
    for i in covered:
        me.polygons[i].material_index = slot
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = body
    body.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_mode(type="FACE")
    bpy.ops.mesh.select_all(action="DESELECT")
    ebm = bmesh.from_edit_mesh(me)
    ebm.faces.ensure_lookup_table()
    for i in covered:
        ebm.faces[i].select_set(True)
    bmesh.update_edit_mesh(me)
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.003, scale_to_bounds=False)
    bpy.ops.uv.pack_islands(rotate=True, margin=0.003)
    bpy.ops.object.mode_set(mode="OBJECT")
    uv = me.uv_layers[0]
    report["covered_faces"] = len(covered)

    # The bake, onto a copy of the covered faces alone, from the full chest (its glTF material: colour and normal map).
    low = body.copy(); low.data = me.copy()
    for c in body.users_collection:
        c.objects.link(low)
    low.modifiers.clear()
    lbm = bmesh.new(); lbm.from_mesh(low.data)
    lbm.faces.ensure_lookup_table()
    bmesh.ops.delete(lbm, geom=[f for f in lbm.faces if f.index not in covered_set], context="FACES")
    lbm.to_mesh(low.data); lbm.free()
    for f in low.data.polygons:
        f.use_smooth = True
    low.data.materials.clear()
    bake_material = bpy.data.materials.new(f"{title}_bake")
    bake_material.use_nodes = True
    low.data.materials.append(bake_material)
    target = bake_material.node_tree.nodes.new("ShaderNodeTexImage")
    bake_material.node_tree.nodes.active = target
    scene = bpy.context.scene
    engine = scene.render.engine
    scene.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"; prefs.get_devices()
    for d in prefs.devices:
        d.use = d.type == "OPTIX"
    scene.cycles.device = "GPU"
    scene.cycles.samples = 1
    bake = scene.render.bake
    bake.use_selected_to_active = True
    bake.normal_space = "TANGENT"
    bake.margin = 16
    bake.use_pass_direct = bake.use_pass_indirect = False
    bake.use_pass_color = True
    bpy.ops.object.select_all(action="DESELECT")
    high.select_set(True); low.select_set(True)
    bpy.context.view_layer.objects.active = low
    out, missed_texels = {}, {}
    os.makedirs(os.path.join(folder, "build"), exist_ok=True)
    for kind, space in (("Color", "sRGB"), ("Normal", "Non-Color")):
        layers = []
        for cage in (NEAR, FAR):
            image = bpy.data.images.new(f"{title}_{kind}", TEXTURE, TEXTURE, alpha=False)
            image.colorspace_settings.name = space
            image.generated_color = MISS
            bake.cage_extrusion, bake.max_ray_distance = cage, 3 * cage
            target.image = image
            bpy.ops.object.bake(type="DIFFUSE" if kind == "Color" else "NORMAL")
            array = np.empty(TEXTURE * TEXTURE * 4, dtype=np.float32)
            image.pixels.foreach_get(array)
            layers.append(array.reshape(-1, 4))
            if cage == NEAR:
                near_image = image
            else:
                bpy.data.images.remove(image)
        near, far = layers
        miss = (np.abs(near[:, :3] - np.array(MISS[:3])).max(1) < 1e-3) | (near[:, :3].max(1) < 1e-4)
        far_hit = (np.abs(far[:, :3] - np.array(MISS[:3])).max(1) >= 1e-3) & (far[:, :3].max(1) >= 1e-4)
        near[miss] = far[miss]
        unwritten = np.abs(near[:, :3] - np.array(MISS[:3])).max(1) < 1e-3
        near[unwritten] = (0.0, 0.0, 0.0, 1.0) if kind == "Color" else (0.5, 0.5, 1.0, 1.0)
        missed_texels[kind] = int((miss & far_hit).sum())
        near_image.pixels.foreach_set(near.ravel())
        path = os.path.join(folder, "build", f"{title}_{kind}.png")
        near_image.filepath_raw = path
        near_image.file_format = "PNG"
        near_image.save()
        out[kind] = path
    scene.render.engine = engine
    # The size's growth, now that the maps are baked on the surface as the chest has it.
    for v, grow in growth.items():
        me.vertices[v].co += grow
    if growth:
        me.update()
    # Gone with what they hold: removing an object leaves its mesh, and its material its images (an 8K map).
    low_data, high_data = low.data, high.data
    images = {n.image for m in high_data.materials if m and m.node_tree for n in m.node_tree.nodes
              if n.type == "TEX_IMAGE" and n.image}
    images |= {target.image} if target.image else set()
    bpy.data.objects.remove(low, do_unlink=True)
    bpy.data.objects.remove(high, do_unlink=True)
    bpy.data.meshes.remove(low_data)
    bpy.data.meshes.remove(high_data)
    for image in images:
        if image.name in bpy.data.images:
            bpy.data.images.remove(image)
    for image in [i for i in bpy.data.images if i.name.startswith(f"{title}_")]:
        bpy.data.images.remove(image)
    report["texels_missed_near_filled_far"] = missed_texels

    # Every covered triangle: its corners on the chest's map and under it, how much of the chest shows at each, the
    # material under, its vertices; and the covered vertices' edges (pieces.py colours the chest by her skin under it,
    # smoothed over the mesh, and paints what lay under it where it fades out).
    triangles = []
    for i in covered:
        p = me.polygons[i]
        loops = list(p.loop_indices)
        for tri in ([loops[0], loops[k], loops[k + 1]] for k in range(1, len(loops) - 1)):
            triangles.append(([tuple(uv.data[l].uv) for l in tri], [under_uv[l] for l in tri],
                              [shows[me.loops[l].vertex_index] for l in tri], under_material[i],
                              [me.loops[l].vertex_index for l in tri]))
    inside = {v for t in triangles for v in t[4]}
    edges = [tuple(e.vertices) for e in me.edges if e.vertices[0] in inside and e.vertices[1] in inside]
    report["fade_triangles"] = sum(1 for t in triangles if min(t[2]) < 1.0)
    return report, out, (triangles, edges)


if __name__ == "__main__":
    import sys
    _name = sys.argv[sys.argv.index("--") + 1]
    prepare(os.path.join(os.path.dirname(os.path.abspath(__file__)), _name), _name)
