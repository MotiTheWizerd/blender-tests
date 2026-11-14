"""Eyes of their own for a head: where its painted eyes open, cut open, and eyeballs put in (head.py calls give_eyes()
for every head it makes, and eye_pictures() for its checks).

A Tripo head is one closed skin with its eyes painted on, its lids sculpted over an even grid that runs straight across
them (probe_eyes.py). Each eye is seen from the front as a map: the face is ray-cast along its front (-y) on a fine
grid round the eye, and each hit takes the colour its texture has there (no light: the paint itself). The eye is what
is not skin there, reached from the iris: the white and the iris are cool or grey where skin is warm. Its outline,
a radius for every angle round its middle smoothed of the pixels' steps, is the opening. The opening is cut, its edge
laid on the outline, and the lids' inside carried into the eyeball's sphere; the eyeball is a sphere fitted to the
painted eye (the AI sculpts the eyeball under its paint: WarriorM's are 11.9 and 11.3 mm in radius, a real eye's 12),
its cornea rising over an iris painted by code in the painted iris's colour.
"""
import bpy, math, os, sys
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.interpolate import poly_3d_calc

STEP = 0.00015      # the front map's grid, metres
REACH = (0.024, 0.016)   # the map's half width and half height round an eye's middle
WARM = 0.16         # skin: (red - blue) over the brightest channel above this; the eye's white and iris below
ANGLES = 180        # the outline's radii round the eye
SMOOTH = 8          # the outline keeps this many waves round the eye (its corners, its lids' curves), no finer


def front_map(head, image, centre):
    """The colour under each point of a grid round centre (x, z), seen from the front, and the hits' depth (y);
    nan where the ray misses."""
    me = head.data
    me.calc_loop_triangles()
    tree = BVHTree.FromObject(head, bpy.context.evaluated_depsgraph_get())
    uv = me.uv_layers.active.data
    w, h = image.size
    pixels = np.array(image.pixels[:], dtype=np.float32).reshape(h, w, image.channels)[..., :3]
    xs = np.arange(centre[0] - REACH[0], centre[0] + REACH[0], STEP)
    zs = np.arange(centre[2] - REACH[1], centre[2] + REACH[1], STEP)
    colour = np.full((len(zs), len(xs), 3), np.nan, dtype=np.float32)
    depth = np.full((len(zs), len(xs)), np.nan, dtype=np.float32)
    polygons = me.polygons
    for j, z in enumerate(zs):
        for i, x in enumerate(xs):
            hit, _, index, _ = tree.ray_cast(Vector((x, -1.0, z)), Vector((0.0, 1.0, 0.0)), 2.0)
            if hit is None:
                continue
            poly = polygons[index]
            corners = [me.vertices[v].co for v in poly.vertices]
            weights = poly_3d_calc(corners, hit)
            u = sum(uv[l].uv[0] * wt for l, wt in zip(poly.loop_indices, weights))
            v = sum(uv[l].uv[1] * wt for l, wt in zip(poly.loop_indices, weights))
            colour[j, i] = pixels[int(min(max(v, 0), 1) * (h - 1)), int(min(max(u, 0), 1) * (w - 1))]
            depth[j, i] = hit.y
    return xs, zs, colour, depth


def opening(colour, seed):
    """The eye in the map: the not-warm pixels joined to seed (the iris, (row, column)), its holes (the pupil, the
    catch-light) filled."""
    r, g, b = colour[..., 0], colour[..., 1], colour[..., 2]
    warmth = (r - b) / np.maximum(colour.max(-1), 1e-3)
    eye = np.nan_to_num(warmth, nan=1.0) < WARM
    # Joined to the seed (4-neighbours), by a flood over the mask.
    reached = np.zeros_like(eye)
    if not eye[seed]:
        near = np.argwhere(eye)
        seed = tuple(near[np.argmin(((near - np.array(seed)) ** 2).sum(1))])
    stack = [seed]
    reached[seed] = True
    rows, cols = eye.shape
    while stack:
        y, x = stack.pop()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < rows and 0 <= nx < cols and eye[ny, nx] and not reached[ny, nx]:
                reached[ny, nx] = True
                stack.append((ny, nx))
    return reached, warmth


def outline(mask, xs, zs):
    """The opening's outline: its middle (x, z) and, for ANGLES angles round it, its radius (metres), smoothed to
    SMOOTH waves."""
    ys, xs_i = np.nonzero(mask)
    px, pz = xs[xs_i], zs[ys]
    middle = np.array([(px.min() + px.max()) / 2, (pz.min() + pz.max()) / 2])
    angles = np.arctan2(pz - middle[1], px - middle[0])
    radii = np.hypot(px - middle[0], pz - middle[1])
    bins = ((angles + math.pi) / (2 * math.pi) * ANGLES).astype(int) % ANGLES
    radius = np.zeros(ANGLES)
    np.maximum.at(radius, bins, radii)
    # An empty bin takes its neighbours' (none should be, but an eye's corner can be thin).
    for k in np.nonzero(radius == 0)[0]:
        radius[k] = (radius[k - 1] + radius[(k + 1) % ANGLES]) / 2
    spectrum = np.fft.rfft(radius)
    spectrum[SMOOTH + 1:] = 0
    return middle, np.fft.irfft(spectrum, ANGLES)


def radius_at(middle, radius, x, z):
    """The outline's radius toward (x, z)."""
    a = math.atan2(z - middle[1], x - middle[0])
    centres = -math.pi + 2 * math.pi * (np.arange(ANGLES) + 0.5) / ANGLES
    return float(np.interp(a, centres, radius, period=2 * math.pi))


TUCK = 0.0005       # how far inside the eyeball's sphere the lids' inside lies, so the eyeball always hides it
FRONT = 0.012       # only faces this near the eye's painted surface are cut (not the back of the head behind it)
OUTLINE = 720       # the outline as a line, a point every half degree round the eye
RIM_SMOOTH = 3      # a rim vertex's depth is sought from the mean of its own and this many neighbours' each way
SCRAP = 50          # skin of at most this many faces, left alone in an opening by the cut, is taken away


def rim_loop(rim):
    """The hole's edge (rim: its vertices) in order round it, one loop."""
    rim = set(rim)
    start = next(iter(rim))
    loop, previous = [start], None
    while True:
        at = loop[-1]
        ways = [e.other_vert(at) for e in at.link_edges if e.is_boundary and e.other_vert(at) in rim]
        if len(ways) != 2:
            raise SystemExit(f"EYES the eye's hole is not one plain loop ({len(ways)} edges of it at a vertex)")
        ahead = ways[0] if ways[1] is previous else ways[1]
        if ahead is start:
            break
        previous = at
        loop.append(ahead)
    if len(loop) != len(rim):
        raise SystemExit(f"EYES the eye's hole is {len(rim)} vertices but its loop {len(loop)}")
    return loop


def cut(bm, middle, radius, surface_y, eyeball):
    """The opening cut through the skin: the faces inside the outline near the eye's surface gone, the hole's edge
    laid on the outline (the grid's steps smoothed away) and drawing the skin that lies there, and the lids' inside:
    a band from that edge straight toward the eyeball's middle (eyeball: its centre, its radius), TUCK under its
    surface, so it lies behind the eyeball however it turns. Returns the band's faces, the edge's vertices and what was
    mended: vertices made where the hole touched itself, and the faces of the scraps it left."""
    import bmesh
    inside = [f for f in bm.faces
              if abs(f.calc_center_median().y - surface_y) < FRONT
              and math.hypot(f.calc_center_median().x - middle[0], f.calc_center_median().z - middle[1])
              < radius_at(middle, radius, f.calc_center_median().x, f.calc_center_median().z)]
    # The skin whole, across the opening: what the rim's depth is read from (the skin left after the cut would put
    # every point over the hole back on the cut's edge).
    whole = bm.copy()
    whole_tree = BVHTree.FromBMesh(whole)
    bmesh.ops.delete(bm, geom=inside, context="FACES_ONLY")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    # Where two faces cut only met at a corner, the hole touches itself there: that vertex made one for each fan of
    # skin round it, so the hole's edge is one plain loop and each goes its own way onto the outline.
    split, fans = 0, []
    for v in [v for v in bm.verts if sum(e.is_boundary for e in v.link_edges) > 2]:
        made = bmesh.utils.vert_separate(v, [e for e in v.link_edges if e.is_boundary])
        split += len(made) - 1
        fans += [f for m in made for f in m.link_faces]
    # A scrap of skin the cut left inside the opening, held only by such a corner, now stands alone: it goes too.
    scraps = set()
    for start in fans:
        if not start.is_valid or start in scraps:
            continue
        piece, todo = {start}, [start]
        while todo and len(piece) <= SCRAP:
            for e in todo.pop().edges:
                for g in e.link_faces:
                    if g not in piece:
                        piece.add(g)
                        todo.append(g)
        if len(piece) <= SCRAP:
            scraps |= piece
    bmesh.ops.delete(bm, geom=list(scraps), context="FACES_ONLY")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    # The skin left, as it is before the rim moves: where a moved vertex lies on it, and the texture under it there
    # (the eye's own faces gone from it, or the rim and the lid's inside would draw the eye's white and the paint's
    # padding round it).
    skin_face = bm.faces.layers.int.new("skin_face")     # each face's place in `before`, as faces come and go
    for i, f in enumerate(bm.faces):
        f[skin_face] = i
    before = bm.copy()
    before.faces.ensure_lookup_table()
    uv_layer = bm.loops.layers.uv.active
    before_uv = before.loops.layers.uv.active
    # The texture's islands round the eye: a moved corner draws what lies under it on its own face's island, for a
    # seam may run through the lid, and a corner given the other island's texture would stretch its face across the
    # whole map between them (the lid's shards).
    centre_3d = Vector((middle[0], surface_y, middle[1]))
    near = {f for f in before.faces if (f.calc_center_median() - centre_3d).length < 0.03}

    def same_texture(f, g, edge):
        for v in edge.verts:
            uf = next(l[before_uv].uv for l in f.loops if l.vert is v)
            ug = next(l[before_uv].uv for l in g.loops if l.vert is v)
            if (uf - ug).length > 1e-6:
                return False
        return True

    island_of, islands = {}, []
    for start in near:
        if start in island_of:
            continue
        island_of[start] = len(islands)
        faces, todo = [start], [start]
        while todo:
            f = todo.pop()
            for e in f.edges:
                for g in e.link_faces:
                    if g in near and g not in island_of and same_texture(f, g, e):
                        island_of[g] = len(islands)
                        faces.append(g)
                        todo.append(g)
        islands.append((faces, BVHTree.FromPolygons([v.co for v in before.verts],
                                                    [[v.index for v in f.verts] for f in faces])))
    whole_skin = (list(before.faces), BVHTree.FromBMesh(before))

    def uv_under(co, face=None):
        """The texture under co on the skin left: on face's island (a face of bm), else wherever is nearest."""
        home = before.faces[face[skin_face]] if face is not None else None
        faces, tree = islands[island_of[home]] if home in island_of else whole_skin
        location, _, index, _ = tree.find_nearest(co)
        found = faces[index]
        weights = poly_3d_calc([v.co for v in found.verts], location)
        return sum((l[before_uv].uv * w for l, w in zip(found.loops, weights)), Vector((0.0, 0.0)))

    rim = {v for e in bm.edges if e.is_boundary for v in e.verts
           if abs(v.co.y - surface_y) < FRONT and math.hypot(v.co.x - middle[0], v.co.z - middle[1]) < 0.03}
    shapes = list(bm.verts.layers.shape.values())
    # The cut's edge is a staircase on the skin's grid. Each of its vertices goes onto the outline in its turn round
    # the hole, as far along the outline as it is along the staircase: in order, evenly, so the rim never folds back
    # (each to the outline at its own angle, a stair's corners crossed over, and where the upper lid overhangs several
    # stood one behind another at the same place: the lid's inside hung from them in flaps).
    loop = rim_loop(rim)
    xz = np.array([(v.co.x, v.co.z) for v in loop])
    if np.sum(xz[:, 0] * np.roll(xz[:, 1], -1) - np.roll(xz[:, 0], -1) * xz[:, 1]) < 0:
        loop, xz = loop[::-1], xz[::-1]         # round the way the outline goes (its angle growing)
    stairs = np.r_[0.0, np.cumsum(np.hypot(*np.diff(np.r_[xz, xz[:1]], axis=0).T))]
    along = stairs[:-1] / stairs[-1]
    angles = -math.pi + 2 * math.pi * np.arange(OUTLINE) / OUTLINE
    radii = np.array([radius_at(middle, radius, middle[0] + math.cos(a), middle[1] + math.sin(a)) for a in angles])
    line = np.c_[middle[0] + radii * np.cos(angles), middle[1] + radii * np.sin(angles)]
    arc = np.r_[0.0, np.cumsum(np.hypot(*np.diff(np.r_[line, line[:1]], axis=0).T))]
    # Where along the outline each vertex's own angle puts it; the staircase's share laid on from there, turned so
    # its vertices move the least.
    own = np.interp(np.arctan2(xz[:, 1] - middle[1], xz[:, 0] - middle[0]), angles, arc[:-1], period=2 * math.pi) / arc[-1]
    shift = np.angle(np.mean(np.exp(2j * math.pi * (own - along)))) / (2 * math.pi)
    target = ((along + shift) % 1.0) * arc[-1]
    on_line = np.c_[np.interp(target, arc, np.r_[line[:, 0], line[0, 0]]), np.interp(target, arc, np.r_[line[:, 1], line[0, 1]])]
    # Its depth: the whole skin's nearest there, sought from its neighbours' depth (its own, on a stair, may stand a
    # millimetre behind the next; nearest, not along the front, where the upper lid overhangs and a ray would land
    # on it), and evened with its neighbours'; on the outline as seen from the front.
    def along_loop(values, reach):
        return np.mean([np.roll(values, k) for k in range(-reach, reach + 1)], axis=0)

    sought = along_loop(np.array([v.co.y for v in loop]), RIM_SMOOTH)
    depth = along_loop(np.array([whole_tree.find_nearest(Vector((x, y, z)))[0].y
                                 for (x, z), y in zip(on_line, sought)]), 1)
    for v, (x, z), y in zip(loop, on_line, depth):
        move = Vector((x, y, z)) - v.co
        v.co += move
        for layer in shapes:
            v[layer] += move
    # Edges of the rim that the snapping made too short to see: their two ends become one.
    bmesh.ops.remove_doubles(bm, verts=list(rim), dist=0.0002)
    rim = [v for v in bm.verts if v.is_valid and v.is_boundary
           and abs(v.co.y - surface_y) < FRONT and math.hypot(v.co.x - middle[0], v.co.z - middle[1]) < 0.03]
    # The rim draws the skin now under it (its corners' texture was where the grid's corner stood, on the eye's white),
    # each face's corner from that face's island.
    for v in rim:
        for loop in v.link_loops:
            loop[uv_layer].uv = uv_under(v.co, loop.face)
    edges = [e for e in bm.edges if e.is_boundary and all(v in rim for v in e.verts)]
    made = bmesh.ops.extrude_edge_only(bm, edges=edges)["geom"]
    wall_verts = [g for g in made if isinstance(g, bmesh.types.BMVert)]
    centre, r = Vector(eyeball[0]), eyeball[1]
    for v in wall_verts:
        # Straight toward the eyeball's middle, TUCK under its surface: neighbours stay in their order round the
        # opening, so the lid's inside is one smooth band from the rim to the eyeball.
        target = centre + (v.co - centre).normalized() * (r - TUCK)
        move = target - v.co
        v.co += move
        for layer in shapes:
            v[layer] += move
    wall = [g for g in made if isinstance(g, bmesh.types.BMFace)]
    # The wall draws the lid's rim colour down into the eye (each of its corners the rim vertex it came from, as the
    # skin face it hangs from draws it there), not the stretched paint the extrusion left it.
    rim_set = set(rim)
    origin = {}
    for w in wall_verts:
        for e in w.link_edges:
            other = e.other_vert(w)
            if other in rim_set:
                origin[w] = other
    for f in wall:
        f.smooth = True
        hung = next(e for e in f.edges if all(v in rim_set for v in e.verts))
        skin = next(g for g in hung.link_faces if g is not f)
        drawn = {l.vert: l[uv_layer].uv.copy() for l in skin.loops}
        for loop in f.loops:
            loop[uv_layer].uv = drawn[origin.get(loop.vert, loop.vert)]
    bm.faces.layers.int.remove(skin_face)
    before.free()
    whole.free()
    return wall, rim, {"corners_split": split, "scrap_faces": len(scraps)}


RINGS, SEGMENTS = 28, 48     # the eyeball's rings from its front to its back, and its segments round its axis
LIMBUS = math.radians(30)    # where the iris meets the white, from the front (a 6 mm iris on a 12 mm eye)
PUPIL = math.radians(7.5)    # the pupil's edge (a 3 mm pupil)
BULGE = 0.06                 # the cornea's rise over the sphere at its middle, a share of the radius (0.7 mm of 12)
EYE_TEXTURE = 1024


def eyeball(bm, centre, radius, forward, side, material):
    """An eyeball in bm: a sphere of radius round centre, looking along forward, the cornea rising over the iris; its
    texture laid round its front (the middle of the texture is the front, its edge the back), so the iris is a disc in
    the middle of eye_texture's map. Its faces wear material (an index) and say side (1 right, 2 left) in the
    "eye" face layer. Every shape key holds it still."""
    import bmesh
    f = Vector(forward).normalized()
    u = (Vector((1.0, 0.0, 0.0)) - f * f.x).normalized()
    v = f.cross(u)
    uv = bm.loops.layers.uv.active
    shapes = list(bm.verts.layers.shape.values())
    eye_layer = bm.faces.layers.int.get("eye") or bm.faces.layers.int.new("eye")

    def point(theta, phi):
        lift = BULGE * (1 - (theta / LIMBUS) ** 2) ** 2 if theta < LIMBUS else 0.0
        d = f * math.cos(theta) + (u * math.cos(phi) + v * math.sin(phi)) * math.sin(theta)
        return Vector(centre) + d * radius * (1 + lift)

    def texture_at(theta, phi):
        return Vector((0.5 + 0.5 * theta / math.pi * math.cos(phi), 0.5 + 0.5 * theta / math.pi * math.sin(phi)))

    # Rings closer together at the front, where the cornea curves and the iris is drawn.
    thetas = [math.pi * (k / RINGS) ** 1.4 for k in range(RINGS + 1)]
    phis = [2 * math.pi * s / SEGMENTS for s in range(SEGMENTS)]
    verts = {}
    for k, theta in enumerate(thetas):
        for s, phi in enumerate(phis if 0 < k < RINGS else [0.0]):
            at = point(theta, phi)
            vert = bm.verts.new(at)
            for layer in shapes:
                vert[layer] = at.copy()
            verts[k, s] = vert
    faces = []

    def face(keys, angles):
        made = bm.faces.new([verts[k] for k in keys])
        made.material_index = material
        made[eye_layer] = side
        made.smooth = True
        for loop, (theta, phi) in zip(made.loops, angles):
            loop[uv].uv = texture_at(theta, phi)
        faces.append(made)

    for s in range(SEGMENTS):
        n = (s + 1) % SEGMENTS
        phi, phi_n = phis[s], phis[s] + 2 * math.pi / SEGMENTS
        face([(0, 0), (1, s), (1, n)], [(0.0, (phi + phi_n) / 2), (thetas[1], phi), (thetas[1], phi_n)])
        for k in range(1, RINGS - 1):
            face([(k, s), (k + 1, s), (k + 1, n), (k, n)],
                 [(thetas[k], phi), (thetas[k + 1], phi), (thetas[k + 1], phi_n), (thetas[k], phi_n)])
        face([(RINGS - 1, s), (RINGS, 0), (RINGS - 1, n)],
             [(thetas[RINGS - 1], phi), (math.pi, (phi + phi_n) / 2), (thetas[RINGS - 1], phi_n)])
    # Outward: the front fan's normal must point forward.
    faces[0].normal_update()
    if faces[0].normal.dot(f) < 0:
        bmesh.ops.reverse_faces(bm, faces=faces)
    return faces


def eye_texture(iris, size=EYE_TEXTURE, seed=7):
    """The eyeball's colour map (rows bottom-up, RGB 0..1, sRGB-encoded) for an iris of colour iris (sRGB 0..1): the
    white, faintly warm and a little shaded toward the iris's rim and the back; the iris in fibres running out from the
    pupil, darker at its rim, lighter round the pupil; the pupil black. Laid as eyeball() lays its texture."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:size, 0:size]
    dx, dy = (x + 0.5) / size - 0.5, (y + 0.5) / size - 0.5
    theta = np.hypot(dx, dy) * 2 * math.pi
    phi = np.arctan2(dy, dx)
    smooth = lambda e0, e1, t: np.clip((t - e0) / (e1 - e0), 0, 1) ** 2 * (3 - 2 * np.clip((t - e0) / (e1 - e0), 0, 1))
    # Fibres: noise round the pupil, a few frequencies, stretched along the radius.
    fibres = np.zeros_like(theta)
    for k, amp in ((23, 0.5), (57, 0.3), (131, 0.2)):
        phase = rng.uniform(0, 2 * math.pi, 4)
        fibres += amp * np.sin(k * phi + phase[0] + 3 * np.sin(theta * 9 + phase[1]))
    t = np.clip((theta - PUPIL) / (LIMBUS - PUPIL), 0, 1)          # 0 at the pupil, 1 at the rim
    shade = 1.0 + 0.18 * fibres - 0.45 * smooth(0.7, 1.0, t) + 0.25 * (1 - smooth(0.0, 0.35, t))
    iris_colour = np.array(iris, dtype=np.float32)[None, None, :] * shade[..., None]
    white = np.array([0.86, 0.83, 0.79], dtype=np.float32)
    sclera = white[None, None, :] * (1 - 0.10 * (1 - smooth(LIMBUS, LIMBUS + 0.12, theta))[..., None]
                                     - 0.25 * smooth(1.6, 2.8, theta)[..., None])
    sclera = sclera + np.array([0.04, -0.01, -0.02]) * smooth(1.2, 2.4, theta)[..., None]
    edge = 0.012        # the soft edges: a little over half a degree
    into_white = smooth(LIMBUS - edge, LIMBUS + edge, theta)[..., None]
    colour = iris_colour * (1 - into_white) + sclera * into_white
    pupil = 1 - smooth(PUPIL - edge, PUPIL + edge, theta)[..., None]
    colour = colour * (1 - pupil) + np.array([0.02, 0.02, 0.025]) * pupil
    return np.clip(colour, 0, 1).astype(np.float32)


def sphere_fit(points):
    """The sphere through points (n, 3) nearest them: its centre and radius."""
    a = np.c_[2 * points, np.ones(len(points))]
    solution = np.linalg.lstsq(a, (points ** 2).sum(1), rcond=None)[0]
    centre = solution[:3]
    return centre, float(np.sqrt(solution[3] + (centre ** 2).sum()))


IRIS_BAND = (0.005, 0.07)     # where painted eyes can be: this far above the nose tip (metres)
SHINE = 0.9                   # the eye's smoothness: wet, every bit of it


def painted_irises(head, image, nose):
    """Each painted eye's iris (x, y, z), from the texture under the mesh's vertices: in the band above the nose tip
    (nose: its (x, y, z)), at the face's front, the vertices whose paint is the iris (coloured, not warm), else the
    white too (bright and grey). The subject's right first (at -x), then left."""
    me = head.data
    co = np.array([v.co[:] for v in me.vertices])
    w, h = image.size
    pixels = np.array(image.pixels[:], dtype=np.float32).reshape(h, w, image.channels)[..., :3]
    uv = np.empty(len(me.loops) * 2, dtype=np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    loop_vert = np.empty(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", loop_vert)
    colour = np.zeros((len(co), 3))
    np.add.at(colour, loop_vert, pixels[(np.clip(uv[:, 1], 0, 1) * (h - 1)).astype(int),
                                        (np.clip(uv[:, 0], 0, 1) * (w - 1)).astype(int)])
    colour /= np.maximum(np.bincount(loop_vert, minlength=len(co)), 1)[:, None]
    r, g, b = colour.T
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    band = (co[:, 2] > nose[2] + IRIS_BAND[0]) & (co[:, 2] < nose[2] + IRIS_BAND[1]) & (co[:, 1] < nose[1] + 0.06)
    white = band & (lum > 0.55) & (colour.max(1) - colour.min(1) < 0.12)
    iris = band & ~white & ((b > r + 0.02) | (g > r + 0.02)) & (lum < 0.6)
    found = []
    for side in (co[:, 0] < 0, co[:, 0] > 0):
        pick = co[iris & side] if (iris & side).sum() >= 3 else co[(iris | white) & side]
        if len(pick) < 3:
            raise SystemExit("EYES no painted eye on one side of the face")
        found.append(pick.mean(0))
    return found


def save_map(array, path, space):
    """array (rows bottom-up, RGB or RGBA, 0..1) as a PNG at path; the image it made."""
    image = bpy.data.images.new(os.path.basename(path), array.shape[1], array.shape[0], alpha=array.shape[2] == 4)
    image.colorspace_settings.name = space
    rgba = array if array.shape[2] == 4 else np.concatenate([array, np.ones(array.shape[:2] + (1,), np.float32)], -1)
    image.pixels = rgba.astype(np.float32).ravel()
    image.filepath_raw = path
    image.file_format = "PNG"
    image.save()
    return image


def give_eyes(head, image, title, maps, checks, nose):
    """The head's painted eyes opened and eyeballs of their own put in (head: the mesh object, in its final frame:
    metres, front -y, up z; image: its colour map; nose: its nose tip). The eyeballs wear a material named
    <title>Eyes, the head's last slot, whose maps go to maps: <title>Eyes_Color.png (the iris the painted one's colour)
    and <title>Eyes_MetallicSmoothness.png (no metal, wet). Each shape key holds the eyeballs still. checks gets each
    eye's front map with its outline drawn (eyes_map_<side>.png). Returns what was found and made."""
    import bmesh
    report, outlines = {}, {}
    for side, iris in zip(("right", "left"), painted_irises(head, image, nose)):
        xs, zs, colour, depth = front_map(head, image, iris)
        seed = (int(np.argmin(np.abs(zs - iris[2]))), int(np.argmin(np.abs(xs - iris[0]))))
        mask, warmth = opening(colour, seed)
        middle, radius = outline(mask, xs, zs)
        gx, gz = np.meshgrid(xs, zs)
        surface = np.c_[gx[mask], depth[mask], gz[mask]]
        centre, r = sphere_fit(surface[~np.isnan(surface).any(1)])
        # The painted iris's colour: the eye's coloured middle round the seed, not the pupil, not the white.
        near_seed = np.hypot(gx - xs[seed[1]], gz - zs[seed[0]]) < 0.0045
        lum = colour @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
        painted = mask & near_seed & (lum > 0.12) & (lum < 0.62) & (np.nan_to_num(warmth, nan=1) < 0.1)
        report[side] = {"middle_m": [round(float(middle[0]), 4), round(float(middle[1]), 4)],
                        "width_mm": round(float(radius[0] + radius[ANGLES // 2]) * 1000, 1),
                        "height_mm": round(float(radius[ANGLES // 4] + radius[3 * ANGLES // 4]) * 1000, 1),
                        "pixels": int(mask.sum()),
                        "touches_map_edge": bool(mask[0].any() or mask[-1].any() or mask[:, 0].any() or mask[:, -1].any()),
                        "surface_y": round(float(np.nanmedian(depth[mask])), 4),
                        "eyeball": {"centre_m": centre.round(4).tolist(), "radius_mm": round(r * 1000, 1)},
                        "iris_rgb": np.median(colour[painted], 0).round(3).tolist() if painted.any() else None}
        outlines[side] = (middle, radius)
        # The map as seen (rows bottom-up: z grows up), the found eye tinted green and the outline drawn.
        picture = np.nan_to_num(colour, nan=0.0).copy()
        picture[mask] = picture[mask] * 0.6 + np.array([0.0, 0.35, 0.0])
        for k in range(ANGLES * 4):
            a = -math.pi + 2 * math.pi * k / (ANGLES * 4)
            rr = radius_at(middle, radius, middle[0] + math.cos(a), middle[1] + math.sin(a))
            i = int(round((middle[0] + rr * math.cos(a) - xs[0]) / STEP))
            j = int(round((middle[1] + rr * math.sin(a) - zs[0]) / STEP))
            if 0 <= j < picture.shape[0] and 0 <= i < picture.shape[1]:
                picture[j, i] = (1.0, 0.1, 0.8)
        bpy.data.images.remove(save_map(picture, os.path.join(checks, f"eyes_map_{side}.png"), "sRGB"))

    bm = bmesh.new()
    bm.from_mesh(head.data)
    for side in ("right", "left"):
        middle, radius = outlines[side]
        before = len(bm.faces)
        eye = report[side]["eyeball"]
        wall, rim, mended = cut(bm, middle, radius, report[side]["surface_y"], (eye["centre_m"], eye["radius_mm"] / 1000))
        report[side].update(faces_cut=before - len(bm.faces) + len(wall), rim_vertices=len(rim), wall_faces=len(wall),
                            **mended)
    slot = len(head.data.materials)
    for k, side in enumerate(("right", "left")):
        eye = report[side]["eyeball"]
        eyeball(bm, eye["centre_m"], eye["radius_mm"] / 1000, (0, -1, 0), k + 1, slot)
    bm.to_mesh(head.data)
    bm.free()
    if "eye" in head.data.attributes:
        head.data.attributes.remove(head.data.attributes["eye"])
    # Normals from the shape as it now is (the import's own were for the closed skin; the new faces had none).
    head.data.normals_split_custom_set_from_vertices([v.normal for v in head.data.vertices])
    head.data.update()

    irises = [report[s]["iris_rgb"] for s in ("right", "left") if report[s]["iris_rgb"]]
    iris = np.mean(irises, 0) if irises else np.array([0.35, 0.28, 0.2])
    report["iris_rgb"] = np.round(iris, 3).tolist()
    colour_map = save_map(eye_texture(iris), os.path.join(maps, f"{title}Eyes_Color.png"), "sRGB")
    shine = np.zeros((64, 64, 4), np.float32)
    shine[..., 3] = SHINE
    bpy.data.images.remove(save_map(shine, os.path.join(maps, f"{title}Eyes_MetallicSmoothness.png"), "Non-Color"))
    # The eyes' material, after every other slot: adding one keeps each face's slot (clearing them would not).
    material = bpy.data.materials.new(f"{title}Eyes")
    material.use_nodes = True
    node = material.node_tree.nodes.new("ShaderNodeTexImage")
    node.image = colour_map
    material.node_tree.links.new(node.outputs["Color"], material.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
    material.node_tree.nodes.active = node
    head.data.materials.append(material)
    return report


def eye_pictures(head, skin_image, report, checks):
    """The eyes in their colours (Workbench, studio light): eyes_front.jpg, eyes_close.jpg (the right eye),
    eyes_three_quarter.jpg. The head's materials are left as they were."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from place import pictures_as_jpeg
    scene = bpy.context.scene
    first = head.data.materials[0]
    pictures_as_jpeg(scene)
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "TEXTURE"
    scene.world = scene.world or bpy.data.worlds.new("w")
    skin = bpy.data.materials.new("skin (picture)")
    skin.use_nodes = True
    node = skin.node_tree.nodes.new("ShaderNodeTexImage")
    node.image = skin_image
    skin.node_tree.nodes.active = node
    head.data.materials[0] = skin        # in place: clearing them would put every face in slot 0
    cam = bpy.data.objects.new("eyes camera", bpy.data.cameras.new("eyes camera"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.type = "ORTHO"
    right, left = report["right"], report["left"]
    mid = Vector(((right["middle_m"][0] + left["middle_m"][0]) / 2, right["surface_y"], right["middle_m"][1]))
    close = Vector((right["middle_m"][0], right["surface_y"], right["middle_m"][1]))
    for name, centre, direction, ortho, size in (("eyes_front", mid, (0, -1, 0), 0.11, (1200, 600)),
                                                 ("eyes_close", close, (0.25, -1, 0.1), 0.04, (900, 600)),
                                                 ("eyes_three_quarter", mid, (0.8, -1, 0.05), 0.13, (1200, 600))):
        d = Vector(direction).normalized()
        cam.location = centre + d * 1.5
        cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
        cam.data.ortho_scale = ortho
        scene.render.resolution_x, scene.render.resolution_y = size
        scene.render.filepath = os.path.join(checks, name + ".jpg")
        bpy.ops.render.render(write_still=True)
    head.data.materials[0] = first
    bpy.data.objects.remove(cam, do_unlink=True)


