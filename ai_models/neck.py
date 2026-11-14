"""The face editor's head seated on a replaceable body as a Head piece: pieces.py calls seat() for each head the body's
model.json names under "heads" (a head_* model head.py made: a bust at a real head's size, its sliders as shape keys).

The head goes where the body's own head was: its chin at the body's chin's height (the chin is what Mixamo's rigger
set the head's joint by), its neck centred on the body's, its chin to its crown as long as the body's own head's
times `size` (1: the same; a head made at a real head's size looks small on a thick-necked body). It is cut CUT above the
body's neck seam, and its neck, from there BLEND further up, is laid onto the body's own neck surface, wholly at the
cut and less the higher, so it narrows or widens into the body's neck instead of stepping. Below the cut a collar of
skin follows the body's neck surface down to the seam, a ring every RING, the last ring the body's seam ring itself:
the same vertices in the same places, with the body's weights and normals, so the seam is the body's own. The head
and the collar are weighed from the body's own head (its nearest point, weighed between that triangle's corners), so
the head turns on the same bones; the collar draws the body's own skin where it lies (it lies on the body's neck): it
wears the body's material (slot 0) and the head's own faces a material named as the head (slot 1; Forge tells them
apart by that name, not the slot), so the head is a piece of its own that any of the body's heads can replace, and
the head's texture on its neck is to be faded from that skin into its own (the fade triangles, painted by pieces.py);
every shape key keeps its slider, the collar moving with none.

Works in the body mesh's frame, which is the world's (Mixamo's import puts the mesh at the origin unturned): metres,
front -Y, up Z.
"""
import math
import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.interpolate import poly_3d_calc
from face import profile

CUT = 0.025       # how far above the seam the head is cut (metres, along the neck)
BLEND = 0.025     # how far above the cut its neck comes back from the body's to its own
RING = 0.006      # between the collar's rings
NECK = 0.1        # a slice of the neck is the vertices this near its line (the jaw and the shoulders are further)


def smoothstep(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


class Plane:
    """The seam's plane and the frame on it: heights along the neck, angles round it."""

    def __init__(self, point, normal):
        self.point, self.n = point.copy(), normal.normalized()
        x = Vector((1, 0, 0))
        self.u = (x - self.n * x.dot(self.n)).normalized()
        self.v = self.n.cross(self.u)

    def height(self, co):
        return (co - self.point).dot(self.n)

    def flat(self, d):
        """d with its part along the neck taken out."""
        return d - self.n * d.dot(self.n)

    def angle(self, co, centre):
        d = co - centre
        return math.atan2(d.dot(self.v), d.dot(self.u)) % (2 * math.pi)


def slice_centre(co, plane, h, around):
    """The middle of the neck's cross-section at height h (the box round its vertices there), on the neck's line
    through `around`."""
    hs = (co - np.array(plane.point)) @ np.array(plane.n)
    on = co[np.abs(hs - h) < 0.003]
    line = np.array(around + plane.n * h)
    flat = on - line - np.outer((on - line) @ np.array(plane.n), np.array(plane.n))
    on = on[np.linalg.norm(flat, axis=1) < NECK]
    if len(on) < 8:
        raise SystemExit(f"NECK no neck at {h * 100:.1f} cm above the seam")
    us, vs = on @ np.array(plane.u), on @ np.array(plane.v)
    c = Vector(on.mean(0))
    c += plane.u * ((us.max() + us.min()) / 2 - c.dot(plane.u)) + plane.v * ((vs.max() + vs.min()) / 2 - c.dot(plane.v))
    return c - plane.n * (plane.height(c) - h)


def ring_of(bm, plane, deform):
    """The body head's open edge on the seam, walked in order round the neck (angle increasing): its vertices."""
    rim = [e for e in bm.edges if e.is_boundary and all(abs(plane.height(v.co)) < 1e-3 for v in e.verts)]
    links = {}
    for e in rim:
        a, b = e.verts
        links.setdefault(a, []).append(b)
        links.setdefault(b, []).append(a)
    if any(len(n) != 2 for n in links.values()):
        raise SystemExit("NECK the seam's ring is not one loop")
    start = next(iter(links))
    loop, previous = [start], None
    while True:
        here = loop[-1]
        nxt = next(n for n in links[here] if n is not previous)
        if nxt is start:
            break
        previous = here
        loop.append(nxt)
    if len(loop) != len(links):
        raise SystemExit("NECK the seam's ring is more than one loop")
    centre = Vector(np.mean([v.co[:] for v in loop], axis=0))
    turn = sum(((loop[i].co - centre).cross(loop[(i + 1) % len(loop)].co - centre)).dot(plane.n) for i in range(len(loop)))
    return (loop if turn > 0 else loop[::-1]), centre


def weights_at(bvh, bm, deform, co):
    """The body head's skin weights at its nearest point to co: its triangle's corners', weighed by where it lies."""
    location, _, index, _ = bvh.find_nearest(co)
    face = bm.faces[index]
    blend = poly_3d_calc([v.co for v in face.verts], location)
    weights = {}
    for v, w in zip(face.verts, blend):
        for group, value in v[deform].items():
            weights[group] = weights.get(group, 0.0) + value * w
    total = sum(weights.values())
    return {g: w / total for g, w in weights.items() if w / total > 1e-4} if total > 0 else {}


class Skin:
    """A mesh's texture read as a surface (its faces triangles): the UV of the nearest point to a place, a face's
    corners all from one island of the texture (faces joined by an edge whose two sides share their UVs), the one
    under the face's middle, since corners from two islands would draw the black between them. Only the faces
    where `near` holds (a point) are split into islands."""

    def __init__(self, bm, near):
        bm.faces.ensure_lookup_table()
        self.bm, self.uv = bm, bm.loops.layers.uv.active
        self.tree = BVHTree.FromBMesh(bm)
        faces = [f for f in bm.faces if near(f.calc_center_median())]
        self.ids = {f.index for f in faces}
        self.root = {i: i for i in self.ids}
        for f in faces:
            for l in f.loops:
                for other in l.edge.link_loops:
                    if other.face.index == f.index or other.face.index not in self.ids:
                        continue
                    mine = (l[self.uv].uv, l.link_loop_next[self.uv].uv)
                    theirs = ((other[self.uv].uv, other.link_loop_next[self.uv].uv) if other.vert == l.vert
                              else (other.link_loop_next[self.uv].uv, other[self.uv].uv))
                    if (mine[0] - theirs[0]).length < 1e-5 and (mine[1] - theirs[1]).length < 1e-5:
                        self.root[self.find(f.index)] = self.find(other.face.index)
        islands = {}
        for f in faces:
            islands.setdefault(self.find(f.index), []).append(f)
        self.islands = {}
        for key, members in islands.items():
            verts = [v.co.copy() for f in members for v in f.verts]
            polygons = [(3 * i, 3 * i + 1, 3 * i + 2) for i in range(len(members))]
            self.islands[key] = (BVHTree.FromPolygons(verts, polygons), members)

    def find(self, i):
        while self.root[i] != i:
            self.root[i] = self.root[self.root[i]]
            i = self.root[i]
        return i

    def uv_on(self, face, co):
        blend = poly_3d_calc([v.co for v in face.verts], co)
        return sum((l[self.uv].uv * w for l, w in zip(face.loops, blend)), Vector((0.0, 0.0)))

    def uvs(self, corners):
        """The UVs of a face's corners, all from the island under its middle."""
        middle = sum(corners, Vector()) / len(corners)
        _, _, index, _ = self.tree.find_nearest(middle)
        if index not in self.ids:
            raise SystemExit("NECK a collar face lies off the skin it takes its texture from")
        tree, members = self.islands[self.find(index)]
        out = []
        for c in corners:
            location, _, local, _ = tree.find_nearest(c)
            out.append(self.uv_on(members[local], location))
        return out


def seat(head_fbx, body_head, point, normal, material, size=1.0):
    """The head of head_fbx seated on body_head's neck as a new object on its skeleton (body_head, the body's own Head
    piece, is left as it is), its own faces wearing `material` (a name) and its collar the body's, and a report: where
    it went, what was cut and blended, and the fade's triangles for pieces.py to paint."""
    if any(abs(a - b) > 1e-5 for row_a, row_b in zip(body_head.matrix_world, Matrix.Identity(4)) for a, b in zip(row_a, row_b)):
        raise SystemExit("NECK the body's mesh is not in the world's frame")
    plane = Plane(point, normal)
    report = {"cut_cm": CUT * 100, "blend_cm": BLEND * 100, "size": size}

    # The body's head: its surface, its weights, its ring on the seam (with the normals the body gives it there).
    body_bm = bmesh.new()
    body_bm.from_mesh(body_head.data)
    body_bm.faces.ensure_lookup_table()
    body_deform = body_bm.verts.layers.deform.active
    body_bvh = BVHTree.FromBMesh(body_bm)
    body_co = np.array([v.co[:] for v in body_bm.verts])
    ring, ring_centre = ring_of(body_bm, plane, body_deform)
    corner_normals = body_head.data.corner_normals
    ring_normal = {v.index: Vector() for v in ring}
    for loop, corner in zip(body_head.data.loops, corner_normals):
        if loop.vertex_index in ring_normal:
            ring_normal[loop.vertex_index] += corner.vector
    b_crown, b_chin, _, b_chin_front = profile(body_co)

    # The head, imported, in the world's frame (its shape keys with it).
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=head_fbx)
    imported = [o for o in bpy.data.objects if o not in before]
    face = next(o for o in imported if o.type == "MESH")
    for o in imported:
        if o is not face:
            bpy.data.objects.remove(o, do_unlink=True)
    me = face.data
    me.transform(face.matrix_world, shape_keys=True)
    face.parent = None
    face.matrix_world = Matrix.Identity(4)
    co = np.array([v.co[:] for v in me.vertices])
    f_crown, f_chin, _, f_chin_front = profile(co)
    scale = size * (b_crown - b_chin) / (f_crown - f_chin)
    report.update({"scale": round(float(scale), 4), "body_chin_to_crown_cm": round(float(b_crown - b_chin) * 100, 2)})

    # Seated: at its scale about its chin's front, the chin at the body's chin's height, the neck on the body's line.
    chin_point = Vector(f_chin_front)
    me.transform(Matrix.Translation(chin_point) @ Matrix.Scale(scale, 4) @ Matrix.Translation(-chin_point), shape_keys=True)
    _, f_chin_scaled, _, _ = profile(np.array([v.co[:] for v in me.vertices]))
    me.transform(Matrix.Translation((0, 0, b_chin - f_chin_scaled)), shape_keys=True)
    co = np.array([v.co[:] for v in me.vertices])
    top = CUT + BLEND
    shift = plane.flat(slice_centre(body_co, plane, top, ring_centre) - slice_centre(co, plane, top, ring_centre))
    me.transform(Matrix.Translation(shift), shape_keys=True)
    co = np.array([v.co[:] for v in me.vertices])
    chin_h = plane.height(Vector((0.0, float(b_chin_front[1]), float(b_chin))))
    report.update({"body_chin_z": round(float(b_chin), 4), "head_chin_z": round(float(f_chin), 4),
                   "crown_body_m": round(float(b_crown), 4), "crown_head_m": round(float(co[:, 2].max()), 4),
                   "shift_in_plane_mm": [round(c * 1000, 1) for c in shift],
                   "chin_above_seam_cm": round(chin_h * 100, 1)})
    if top > chin_h - 0.015:
        raise SystemExit(f"NECK the blend reaches the chin: {top * 100:.1f} cm of {chin_h * 100:.1f}")

    # The body's head as a texture surface: the collar, lying on it, draws the body's own skin there, so the seam's
    # two sides are one texture.
    body_skin = Skin(body_bm, lambda c: -0.01 < plane.height(c) < top + 0.03)

    # Cut, and only the head kept (a bust's shoulders, should they reach above the cut, go too).
    bm = bmesh.new()
    bm.from_mesh(me)
    shapes = list(bm.verts.layers.shape.values())
    uv = bm.loops.layers.uv.active
    # Every layer made now: one added later reallocates the vertices, and the collar's would be lost.
    seam_index = bm.verts.layers.int.new("seam_ring")
    deform = bm.verts.layers.deform.verify()
    from_body = bm.faces.layers.int.new("skin_from_body")   # a face drawing the body's skin (the left of the atlas)
    # The head's eyeballs (head.py's eyes.py: their faces in the material named <head>Eyes), each a shell of its own.
    eyes_slot = next((i for i, m in enumerate(me.materials) if m is not None and "Eyes" in m.name), None)
    eyes_material = me.materials[eyes_slot] if eyes_slot is not None else None
    eye_face = bm.faces.layers.int.new("eye_face")
    for f in bm.faces:
        f[eye_face] = 1 if f.material_index == eyes_slot else 0
    cut_at = plane.point + plane.n * CUT
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-5, plane_co=cut_at,
                           plane_no=plane.n)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if plane.height(f.calc_center_median()) < CUT], context="FACES_ONLY")
    # Only the head kept: what the crown reaches, and its eyeballs (shells of their own).
    crown_vert = max(bm.verts, key=lambda v: v.co.z)
    keep, todo = set(crown_vert.link_faces), list(crown_vert.link_faces)
    while todo:
        for e in todo.pop().edges:
            for g in e.link_faces:
                if g not in keep:
                    keep.add(g)
                    todo.append(g)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f not in keep and not f[eye_face]], context="FACES_ONLY")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    eye_verts = {v for f in bm.faces if f[eye_face] for v in f.verts}
    cut_ring = {v for e in bm.edges if e.is_boundary for v in e.verts if abs(plane.height(v.co) - CUT) < 1e-4}
    eye_centres = [Vector(np.mean([v.co[:] for v in eye_verts if (v.co.x < 0) == right], axis=0))
                   for right in (True, False) if any((v.co.x < 0) == right for v in eye_verts)]
    # The lids' inside ends open within the eyeball, where nothing sees it; any other open edge off the cut is a hole.
    report["head_open_edges_off_the_cut"] = sum(
        1 for e in bm.edges if e.is_boundary and not all(v in cut_ring for v in e.verts)
        and not all(any((v.co - c).length < 0.02 for c in eye_centres) for v in e.verts))
    report["eyeballs"] = len(eye_centres)

    # Its neck laid onto the body's, wholly at the cut and less the higher (each shape key moved with it).
    centres = {}

    def centre_at(h):
        key = round(h, 3)
        if key not in centres:
            centres[key] = slice_centre(body_co, plane, key, ring_centre)
        return centres[key]

    blended = missed = 0
    for v in bm.verts:
        h = plane.height(v.co)
        if h > top:
            continue
        c = centre_at(h) + plane.n * (h - round(h, 3))
        d = plane.flat(v.co - c)
        if d.length < 1e-6 or d.length > NECK:
            continue
        hit, _, _, _ = body_bvh.ray_cast(c, d.normalized(), NECK * 2)
        if hit is None:
            missed += 1
            continue
        move = (hit - v.co) * (1 - smoothstep((h - CUT) / BLEND))
        v.co += move
        for layer in shapes:
            v[layer] += move
        blended += 1
    report.update({"neck_vertices_blended": blended, "rays_missed": missed})

    # The collar: rings on the body's neck from the seam up to the cut, the first the body's seam ring itself.
    count = max(1, round(CUT / RING))
    rows = []
    for k in range(count):
        h = CUT * k / count
        row = []
        for r in ring:
            if k == 0:
                at = r.co.copy()
            else:
                c = centre_at(h) + plane.n * (h - round(h, 3))
                direction = plane.flat(r.co - ring_centre).normalized()
                hit, _, _, _ = body_bvh.ray_cast(c, direction, NECK * 2)
                at = hit if hit is not None else r.co + plane.n * h
            v = bm.verts.new(at)
            for layer in shapes:
                v[layer] = at.copy()
            if k == 0:
                v[seam_index] = len(row) + 1
            row.append(v)
        rows.append(row)

    collar = []

    def face_of(verts, h):
        f = bm.faces.new(verts)
        f.normal_update()
        c = centre_at(h)
        if (f.calc_center_median() - c).dot(f.normal) < 0:
            f.normal_flip()
        f.smooth = True
        collar.append(f)

    n = len(ring)
    for k in range(count - 1):
        for i in range(n):
            face_of([rows[k][i], rows[k][(i + 1) % n], rows[k + 1][(i + 1) % n], rows[k + 1][i]], CUT * (k + 0.5) / count)
    # The last ring zipped to the head's cut, both walked round the neck by angle.
    last = rows[-1]
    centre_last, centre_cut = centre_at(CUT * (count - 1) / count), centre_at(CUT)
    a = sorted(last, key=lambda v: plane.angle(v.co, centre_last))
    b = sorted(cut_ring, key=lambda v: plane.angle(v.co, centre_cut))
    a_ang = [plane.angle(v.co, centre_last) for v in a] + [plane.angle(a[0].co, centre_last) + 2 * math.pi]
    b_ang = [plane.angle(v.co, centre_cut) for v in b] + [plane.angle(b[0].co, centre_cut) + 2 * math.pi]
    i = j = 0
    while i < len(a) or j < len(b):
        if j >= len(b) or (i < len(a) and a_ang[i + 1] <= b_ang[j + 1]):
            face_of([a[i % len(a)], a[(i + 1) % len(a)], b[j % len(b)]], CUT * (count - 0.5) / count)
            i += 1
        else:
            face_of([a[i % len(a)], b[(j + 1) % len(b)], b[j % len(b)]], CUT * (count - 0.5) / count)
            j += 1
    across = 0
    for f in collar:
        uvs = body_skin.uvs([l.vert.co.copy() for l in f.loops])
        for l, at in zip(f.loops, uvs):
            l[uv].uv = at
        f[from_body] = 1
        if max((p - q).length for p in uvs for q in uvs) > 0.02:
            across += 1
    report.update({"collar_rings": count, "seam_ring_vertices": n, "cut_ring_vertices": len(cut_ring),
                   "collar_faces": len(collar), "collar_faces_across_uv_seams": across})

    # The head's own neck where it comes back from the body's: its triangles, each corner with the body's skin under
    # it and how much of the head's own shows there (none at the cut, all of it BLEND above), for pieces.py to paint
    # the body's skin into the head's texture there, so the two skins meet with no edge.
    fade = []
    for f in bm.faces:
        if f[from_body] or not any(plane.height(v.co) < top for v in f.verts):
            continue
        loops = list(f.loops)
        for tri in ([loops[0], loops[i], loops[i + 1]] for i in range(1, len(loops) - 1)):
            corners = [l.vert.co.copy() for l in tri]
            fade.append(([tuple(l[uv].uv) for l in tri], [tuple(u) for u in body_skin.uvs(corners)],
                         [smoothstep((plane.height(c) - CUT) / BLEND) for c in corners]))
    report["fade_triangles"] = fade

    # Weighed from the body's head; the seam ring exactly as the body's; the eyeballs wholly on the head's bone, so
    # they ride the head whole (Mixamo's skeleton has no eye bones: eyes that look about will bring their own).
    for g in body_head.vertex_groups:
        face.vertex_groups.new(name=g.name)
    rig = next(m.object for m in body_head.modifiers if m.type == "ARMATURE")
    head_bone = next(b.name for b in rig.data.bones if b.name.split(":")[-1] == "Head")
    head_group = (face.vertex_groups.get(head_bone) or face.vertex_groups.new(name=head_bone)).index
    for v in bm.verts:
        if v in eye_verts:
            v[deform][head_group] = 1.0
            continue
        k = v[seam_index]
        weights = dict(ring[k - 1][body_deform].items()) if k else weights_at(body_bvh, body_bm, body_deform, v.co)
        for g, w in weights.items():
            v[deform][g] = w
    report["shape_moves_at_cut_mm"] = round(max(((v[layer] - v.co).length for v in cut_ring for layer in shapes[1:]),
                                                 default=0.0) * 1000, 3)
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    me.update()

    # Normals: its own, but the seam ring's are the body's.
    normals = [v.normal.copy() for v in me.vertices]
    ring_attr = me.attributes["seam_ring"].data
    for j in range(len(me.vertices)):
        k = ring_attr[j].value
        if k:
            normals[j] = ring_normal[ring[k - 1].index].normalized()
    me.normals_split_custom_set_from_vertices(normals)
    me.attributes.remove(me.attributes["seam_ring"])

    # Beside the body's own head: its skeleton; the collar the body's material, the eyeballs <material>Eyes, the rest
    # its own.
    face.name = me.name = material
    face.parent = body_head.parent
    face.matrix_parent_inverse = body_head.matrix_parent_inverse.copy()
    face.matrix_world = Matrix.Identity(4)
    for m in body_head.modifiers:
        if m.type == "ARMATURE":
            face.modifiers.new("Armature", "ARMATURE").object = m.object
    me.materials.clear()
    me.materials.append(body_head.data.materials[0])
    me.materials.append(bpy.data.materials.new(material))
    if eye_centres:
        # The head's own (a new one would be named <material>Eyes.001 beside it, and Forge finds the eyes' maps by name).
        eyes_material.name = f"{material}Eyes"
        me.materials.append(eyes_material)
    # Each face's slot after the slots are made: clearing them put every face in slot 0.
    skin_from_body = np.empty(len(me.polygons), dtype=np.int32)
    me.attributes["skin_from_body"].data.foreach_get("value", skin_from_body)
    is_eye = np.empty(len(me.polygons), dtype=np.int32)
    me.attributes["eye_face"].data.foreach_get("value", is_eye)
    me.polygons.foreach_set("material_index", np.where(is_eye == 1, 2, np.where(skin_from_body == 1, 0, 1)).astype(np.int32))
    me.attributes.remove(me.attributes["skin_from_body"])
    me.attributes.remove(me.attributes["eye_face"])
    me.update()
    body_bm.free()
    return face, report
