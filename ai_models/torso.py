"""A torso made on its own laid onto a replaceable body: pieces.py calls graft() when the body's model.json names one
under "torso" (a torso_* folder holding Tripo's source_tripo.fbx and .fbm: the body's own torso, neck to the hips and
arms to the elbows, made alone so the AI spends all its detail there).

The torso is fitted to the body (ICP: its points to the body's surface, a scale per axis and a shift, its worst points
let go), then the body's own torso is laid onto it: each vertex moved to the nearest point of the torso's surface,
wholly from FADE inside and not at all at the edge of what it covers (the neck seam, the limbs' lines, WAIST short of
the torso's own ragged cuts), so every seam and line keeps its vertices where they were and nothing steps. The
covered faces get UVs of their own and a material named <Title>Torso, and its colour and normals are baked from the
torso (Cycles, selected to active), so the torso's detail draws at a map of its own instead of a share of the body's.
The fade's triangles (each corner's UV on the torso's map, the body's UV under it and how much of the torso shows)
go back to pieces.py, which paints the body's skin into the torso's map there, as it does for a head's neck.

The body keeps its vertices, weights and topology: only where they stand and which material they wear change.
Works in the body mesh's frame, which is the world's: metres, front -Y, up Z.
"""
import math
import os
import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

FADE = 0.04       # metres from the edge of what the torso covers to where the body takes its shape wholly
WAIST = 0.04      # what the torso covers keeps this far (metres) from its open edges (Tripo's cuts are ragged)
CAP_BAND = 0.15               # the torso's ends: this share of its height at the bottom and the top
CAP_FACING = 0.7              # a face there turned out of the end steeper than this (its normal's z) is a cap's
FACING = 0.5                  # the torso's surface and the body's turned less than 60 degrees apart
FIT_STEPS = 40
FIT_KEEP = 0.8    # each fitting step weighs the torso's points nearest the body, this share of them
TEXTURE = 4096
REACH = 0.003     # the bake's cage out past the body's surface (metres); its rays 3x as long
FAR_REACH = 0.02  # the second bake's, for what the first missed
MISS = (1.0, 0.0, 1.0, 1.0)   # a bake's image before it: what no ray wrote stays this


def smoothstep(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def load_torso(folder, name):
    """The torso's mesh in the world's frame, its material drawing its own colour and normal maps: Tripo's FBX with
    its .fbm maps, or its GLB once chest.py's prepare step has welded and reduced it to build/reduced.blend (a body
    type's torso, torso_warrior_f_soft: 2M triangles that pieces.py cannot hold beside everything else)."""
    if os.path.exists(os.path.join(folder, "build", "reduced.blend")):
        from chest import load_chest
        high = load_chest(folder, name)
        high.name = f"{name}_torso"
        return high
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=os.path.abspath(os.path.join(folder, "source_tripo.fbx")))
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH"]
    if len(meshes) != 1:
        raise SystemExit(f"TORSO {name} has {len(meshes)} meshes")
    high = meshes[0]
    high.data.transform(high.matrix_world)
    high.matrix_world = Matrix.Identity(4)
    high.parent = None
    for o in new:
        if o is not high:
            bpy.data.objects.remove(o, do_unlink=True)
    maps = os.path.join(folder, "source_tripo.fbm")
    material = bpy.data.materials.new(f"{name}_source")
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    shader = nodes["Principled BSDF"]
    colour = nodes.new("ShaderNodeTexImage")
    colour.image = bpy.data.images.load(os.path.join(maps, "Color.jpg"))
    links.new(colour.outputs["Color"], shader.inputs["Base Color"])
    normal_path = os.path.join(maps, "Normal.jpg")
    if os.path.exists(normal_path):
        normal = nodes.new("ShaderNodeTexImage")
        normal.image = bpy.data.images.load(normal_path)
        normal.image.colorspace_settings.name = "Non-Color"
        bump = nodes.new("ShaderNodeNormalMap")
        links.new(normal.outputs["Color"], bump.inputs["Color"])
        links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    high.data.materials.clear()
    high.data.materials.append(material)
    return high


def forward_pair(co, keep):
    """The most forward point (least y) on each side (x < 0, x > 0) among co where keep: a woman's nipples."""
    left = min((c for c, k in zip(co, keep) if k and c.x < 0), key=lambda c: c.y)
    right = min((c for c, k in zip(co, keep) if k and c.x > 0), key=lambda c: c.y)
    return left, right


def fit(high, body_bvh, body_pair):
    """Scale per axis and shift the torso onto the body: started by the nipples, then ICP. The transform applied to
    its mesh, and the numbers."""
    co = [v.co.copy() for v in high.data.vertices]
    lo_x, hi_x = min(c.x for c in co), max(c.x for c in co)
    lo_z, hi_z = min(c.z for c in co), max(c.z for c in co)
    # The breasts: the most forward points of the trunk's middle half across, in its top two thirds.
    middle = (lo_x + hi_x) / 2
    keep = [abs(c.x - middle) < (hi_x - lo_x) / 4 and c.z > lo_z + (hi_z - lo_z) / 3 for c in co]
    t_left, t_right = forward_pair(co, keep)
    b_left, b_right = body_pair
    s = (b_right - b_left).length / (t_right - t_left).length
    scale = Vector((s, s, s))
    shift = (b_left + b_right) / 2 - (t_left + t_right) / 2 * s
    points = np.array([c[:] for c in co[::7]])
    steps = []
    for _ in range(FIT_STEPS):
        moved = points * np.array(scale) + np.array(shift)
        near = np.array([body_bvh.find_nearest(Vector(p))[0][:] for p in moved])
        far = np.linalg.norm(near - moved, axis=1)
        keep = far <= np.quantile(far, FIT_KEEP)
        steps.append(float(np.median(far)))
        # Per axis, the least squares line from the torso's coordinate to the body's nearest point's.
        for axis in range(3):
            x, y = points[keep, axis], near[keep, axis]
            a, b = np.polyfit(x, y, 1)
            scale[axis], shift[axis] = a, b
    high.data.transform(Matrix.Translation(shift) @ Matrix.Diagonal(scale.to_4d()))
    high.data.update()
    return {"nipples_body_m": [[round(c, 3) for c in b_left], [round(c, 3) for c in b_right]],
            "scale_xyz": [round(a, 4) for a in scale], "shift_m": [round(a, 4) for a in shift],
            "median_off_mm_first_last": [round(steps[0] * 1000, 2), round(steps[-1] * 1000, 2)]}


def lay(body, torso_folder, torso_name, body_piece=0, torso_segment=0, shoulder_x=None):
    """The shape: the torso of torso_folder fitted to body (the whole cut body: its faces' "piece" and "segment" and
    its vertices' "seam" attributes as pieces.py set them) and the Body piece's torso part laid onto it, each covered
    vertex to the torso's surface, wholly from FADE inside and not at all at the edge of what it covers. With
    shoulder_x the covered faces end at the shoulders (|x| within it): a body type's torso made from a picture whose
    arms hang otherwise than the body's would pull its upper arms after them. Returns the report, the torso (for
    graft's bake; the caller removes it), the covered faces (list and set), the covered vertices, the edge's among
    them and how much of the torso shows at each."""
    if any(abs(a - b) > 1e-5 for row_a, row_b in zip(body.matrix_world, Matrix.Identity(4)) for a, b in zip(row_a, row_b)):
        raise SystemExit("TORSO the body's mesh is not in the world's frame")
    me = body.data
    piece = [a.value for a in me.attributes["piece"].data]
    segment = [a.value for a in me.attributes["segment"].data]
    seam = [a.value for a in me.attributes["seam"].data]
    on_body = [i for i, f in enumerate(me.polygons) if piece[i] == body_piece]

    bm = bmesh.new(); bm.from_mesh(me)
    bm.faces.ensure_lookup_table(); bm.verts.ensure_lookup_table()
    body_bvh = BVHTree.FromPolygons([me.vertices[v].co.copy() for v in range(len(me.vertices))],
                                    [tuple(me.polygons[i].vertices) for i in on_body])
    # Her nipples: the most forward points of the Body's torso part, between her shoulders' height and her hips'.
    torso_verts = {v for i in on_body if segment[i] == torso_segment for v in me.polygons[i].vertices}
    zs = sorted(me.vertices[v].co.z for v in torso_verts)
    lo, hi = zs[0], zs[-1]
    co = [me.vertices[v].co for v in torso_verts]
    body_pair = forward_pair(co, [lo + (hi - lo) * 0.4 < c.z < lo + (hi - lo) * 0.85 and abs(c.x) < 0.15 for c in co])

    high = load_torso(torso_folder, torso_name)
    report = {"fade_cm": FADE * 100, "waist_cm": WAIST * 100, "fit": fit(high, body_bvh, body_pair)}
    # The torso's own cuts (the hips all round, the elbows, under the jaw), which Tripo closed with flat caps: a cap is
    # the faces in its lowest or highest CAP_BAND turned out of that end (steeper than CAP_FACING), taken away, so
    # nothing of the body lands on one (her crotch faces down as the hips' cap does) and their rims are its open edges.
    hbm = bmesh.new(); hbm.from_mesh(high.data)
    lo_z, hi_z = min(v.co.z for v in hbm.verts), max(v.co.z for v in hbm.verts)
    band = CAP_BAND * (hi_z - lo_z)
    caps = [f for f in hbm.faces if (f.calc_center_median().z < lo_z + band and f.normal.z < -CAP_FACING)
            or (f.calc_center_median().z > hi_z - band and f.normal.z > CAP_FACING)]
    bmesh.ops.delete(hbm, geom=caps, context="FACES")
    rim = [v.co.copy() for v in hbm.verts if v.is_boundary]
    hbm.to_mesh(high.data); hbm.free()
    high.data.update()
    report["cap_faces"] = len(caps)
    if not rim:
        raise SystemExit(f"TORSO {torso_name}: no cut found at its ends")
    high_bvh = BVHTree.FromObject(high, bpy.context.evaluated_depsgraph_get())
    rim_tree = KDTree(len(rim))
    for k, c in enumerate(rim):
        rim_tree.insert(c, k)
    rim_tree.balance()
    # Clear: the nearest point of the torso is WAIST from a rim (its cuts are ragged: the hips' runs higher at the back
    # than its lowest point) and faces the way the body does there.
    clear = {}
    for i in on_body:
        if segment[i] == torso_segment:
            for v in me.polygons[i].vertices:
                if v not in clear:
                    vert = me.vertices[v]
                    at, facing, _, _ = high_bvh.find_nearest(vert.co)
                    clear[v] = rim_tree.find(at)[2] > WAIST and facing.dot(vert.normal) > FACING

    # What the torso covers: the Body's torso part clear of the torso's open edges. Its edge is where it meets any
    # other face (a limb's line, the neck seam, what isn't clear) or lies on a seam or line.
    covered = [i for i in on_body if segment[i] == torso_segment and all(clear[v] for v in me.polygons[i].vertices)
               and (shoulder_x is None or all(abs(me.vertices[v].co.x) <= shoulder_x for v in me.polygons[i].vertices))]
    covered_set = set(covered)
    inside = {v for i in covered for v in me.polygons[i].vertices}
    edge = {v.index for v in bm.verts if v.index in inside
            and (seam[v.index] or any(f.index not in covered_set for f in v.link_faces))}
    tree = KDTree(len(edge))
    for v in edge:
        tree.insert(me.vertices[v].co, v)
    tree.balance()
    bm.free()

    # Each covered vertex onto the torso's surface, by how far it lies from the edge.
    shows, moves, unreached = {}, [], 0
    for v in inside:
        vert = me.vertices[v]
        w = 0.0 if v in edge else smoothstep(tree.find(vert.co)[2] / FADE)
        hit = high_bvh.find_nearest(vert.co)
        if hit[0] is None:
            unreached += 1; w = 0.0
        shows[v] = w
        if w > 0:
            step = (hit[0] - vert.co) * w
            moves.append(step.length)
            vert.co = vert.co + step
    me.update()
    report.update({"covered_faces": len(covered), "covered_vertices": len(inside), "edge_vertices": len(edge),
                   "unreached": unreached, "moved_mm_median_max": [round(float(np.median(moves)) * 1000, 2),
                                                                   round(float(max(moves)) * 1000, 2)]})
    return report, high, covered, covered_set, inside, edge, shows


def shape(body, torso_folder, torso_name, body_piece=0, torso_segment=0, shoulder_x=None):
    """A whole body type: body (a copy of the body, pieces.py's) laid onto the torso and nothing more. No maps: the
    type is a shape key of the one Body in Forge and the body's own skin rides it, its areolas with its breasts, since
    the UVs are the vertices'. Returns the report."""
    report, high, *_ = lay(body, torso_folder, torso_name, body_piece, torso_segment, shoulder_x)
    high_data = high.data
    bpy.data.objects.remove(high, do_unlink=True)
    bpy.data.meshes.remove(high_data)
    return report


def graft(body, torso_folder, torso_name, title, body_piece=0, torso_segment=0):
    """Lays the torso of torso_folder onto body (lay()), on the faces of the Body piece's torso part, which then draw
    maps of their own baked from the torso. Returns the report, the baked maps (paths: colour, normal) and the fade's
    triangles."""
    me = body.data
    report, high, covered, covered_set, inside, edge, shows = lay(body, torso_folder, torso_name, body_piece, torso_segment)

    # Its own material and UVs: the covered faces' corners in the first UV layer, unwrapped afresh (the body's UVs
    # under them kept for the fade).
    uv = me.uv_layers[0]
    body_uv = {l: tuple(uv.data[l].uv) for i in covered for l in me.polygons[i].loop_indices}
    material = bpy.data.materials.new(f"{title}Torso")
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

    # The bake, onto a copy of the covered faces alone (a bake writes every material's active image).
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
    bake_material = bpy.data.materials.new(f"{title}Torso_bake")
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
    bpy.ops.object.select_all(action="DESELECT")
    high.select_set(True); low.select_set(True)
    bpy.context.view_layer.objects.active = low
    bake.margin = 16
    bake.use_pass_direct = bake.use_pass_indirect = False
    bake.use_pass_color = True
    out, missed = {}, {}
    for kind, space in (("Color", "sRGB"), ("Normal", "Non-Color")):
        # Twice: rays from just past the body (REACH; a longer one starting across a fold, under a breast, lands on
        # the fold's far side), then from far (FAR_REACH) for what they missed: where the body comes back to its own
        # shape it lies further inside or outside the torso than the near rays reach.
        layers = []
        for reach in (REACH, FAR_REACH):
            image = bpy.data.images.new(f"{title}Torso_{kind}", TEXTURE, TEXTURE, alpha=False)
            image.colorspace_settings.name = space
            image.generated_color = MISS
            bake.cage_extrusion, bake.max_ray_distance = reach, 3 * reach
            target.image = image
            bpy.ops.object.bake(type="DIFFUSE" if kind == "Color" else "NORMAL")
            array = np.empty(TEXTURE * TEXTURE * 4, dtype=np.float32)
            image.pixels.foreach_get(array)
            layers.append(array.reshape(-1, 4))
            if reach == REACH:
                near_image = image
            else:
                bpy.data.images.remove(image)
        near, far = layers
        miss = (np.abs(near[:, :3] - np.array(MISS[:3])).max(1) < 1e-3) | (near[:, :3].max(1) < 1e-4)
        far_hit = (np.abs(far[:, :3] - np.array(MISS[:3])).max(1) >= 1e-3) & (far[:, :3].max(1) >= 1e-4)
        near[miss] = far[miss]
        unwritten = np.abs(near[:, :3] - np.array(MISS[:3])).max(1) < 1e-3     # off every island: as Blender leaves it
        near[unwritten] = (0.0, 0.0, 0.0, 1.0) if kind == "Color" else (0.5, 0.5, 1.0, 1.0)
        missed[kind] = int((miss & far_hit).sum())
        image = near_image
        image.pixels.foreach_set(near.ravel())
        path = os.path.join(torso_folder, "build", f"{title}Torso_{kind}.png")
        image.filepath_raw = path
        image.file_format = "PNG"
        image.save()
        out[kind] = path
    scene.render.engine = engine
    bpy.data.objects.remove(low, do_unlink=True)
    bpy.data.objects.remove(high, do_unlink=True)

    # The fade: each covered triangle's corners on the torso's map, the body's skin under them, how much shows.
    fade = []
    for i in covered:
        p = me.polygons[i]
        loops = list(p.loop_indices)
        if min(shows[me.loops[l].vertex_index] for l in loops) >= 1.0:
            continue
        for tri in ([loops[0], loops[k], loops[k + 1]] for k in range(1, len(loops) - 1)):
            fade.append(([tuple(uv.data[l].uv) for l in tri], [body_uv[l] for l in tri],
                         [shows[me.loops[l].vertex_index] for l in tri]))
    report["fade_triangles"] = len(fade)
    report["texels_missed_near_filled_far"] = missed
    return report, out, fade
