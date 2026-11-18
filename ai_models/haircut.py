"""A hair cut out of a head Tripo made with it on: the body's own head drawn (sheet.py), the hair painted on by Iris,
and Tripo given that picture, so the hair is born round HER skull and not another's. hair.py calls this when the hair's
model.json says "made_on": "head".

The faces are told apart by their paint (Tripo's colour map under each face's middle): the hair is the darker of the two
kinds of face the head has (Otsu's line between them, so no colour is named), and of the dark faces the largest
connected patch (the brows, the lashes and the pupils are dark too, each a patch of its own). The head's skin, every
face that is not hair, is laid onto the body's head (an ICP: a scale, a turn and a shift, Umeyama's; the worst points
let go each round), which carries the hair onto her skull where it was made. The skin is then deleted: the hair alone
remains, a shell open at the hairline, already in place. Its map is Tripo's, black outside the hair's own faces (Forge
averages what is not black: the hair's colour must not count her skin).
"""
import math
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

FIT_STEPS = 40
FIT_KEEP = 0.7       # each fitting round weighs the skin's points nearest the head, this share of them
FIT_POINTS = 4000    # points each way a fitting round measures
FIT_SIZES = (0.9, 1.0, 1.1)   # the sizes the fit starts from, about the skin's width against hers
SAMPLE = 2048        # the colour map is read at this size to tell hair from skin (not to draw)
MASK_GROW = 6        # texels the hair's paint keeps past its faces' edges (the map is filtered between texels)
STANDS_OFF = 0.004   # metres off her head a face of the skin's paint must stand to be taken as hair beside the hair
GROW_RINGS = 2       # rings of faces the hair takes from the skin beside it (its highlights at the hairline)
BRIDGE = 200         # faces a piece of hair apart from the largest needs, standing off her head, to be kept
EDGE_RINGS = 2       # rings of the hair's faces from its cut edge whose skin-light paint is made the hair's


def face_colours(ob, image, size=SAMPLE):
    """Each face's paint: the colour map under its middle (its loops' UVs' mean), RGB 0..1, (faces, 3)."""
    me = ob.data
    small = image.copy()
    small.scale(size, size)
    px = np.array(small.pixels[:], dtype=np.float32).reshape(size, size, 4)[:, :, :3]
    import bpy
    bpy.data.images.remove(small)
    uv = me.uv_layers.active.data
    loops = np.array([(uv[l].uv.x, uv[l].uv.y) for l in range(len(uv))], dtype=np.float64)
    starts = np.array([p.loop_start for p in me.polygons])
    totals = np.array([p.loop_total for p in me.polygons])
    sums = np.add.reduceat(loops, starts, axis=0)
    centre = sums / totals[:, None]
    col = ((centre[:, 0] % 1.0) * size).astype(int).clip(0, size - 1)
    row = ((centre[:, 1] % 1.0) * size).astype(int).clip(0, size - 1)
    return px[row, col]


def otsu(values, bins=256):
    """The line between two kinds of value, where the spread within each kind is least (Otsu)."""
    hist, edges = np.histogram(values, bins=bins)
    hist = hist.astype(float)
    mids = (edges[:-1] + edges[1:]) / 2
    weight1 = np.cumsum(hist)                  # the bins up to and including each
    weight2 = weight1[-1] - weight1            # the bins above it
    total1 = np.cumsum(hist * mids)
    mean1 = total1 / np.maximum(weight1, 1e-9)
    mean2 = (total1[-1] - total1) / np.maximum(weight2, 1e-9)
    between = weight1 * weight2 * (mean1 - mean2) ** 2
    return float(edges[np.argmax(between) + 1])


def patches(ob, chosen):
    """The faces in chosen (a bool per face) joined by shared edges: a patch number per face (-1: not chosen)."""
    me = ob.data
    n = len(me.polygons)
    parent = np.arange(n)

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    by_edge = {}
    for p in me.polygons:
        if not chosen[p.index]:
            continue
        for key in p.edge_keys:
            other = by_edge.setdefault(key, p.index)
            if other != p.index:
                a, b = find(other), find(p.index)
                if a != b:
                    parent[a] = b
    label = np.full(n, -1)
    for i in np.nonzero(chosen)[0]:
        label[i] = find(i)
    return label


def umeyama(source, target):
    """The scale, turn and shift laying source (n, 3) onto target (n, 3), least squares (Umeyama 1991)."""
    ms, mt = source.mean(0), target.mean(0)
    s, t = source - ms, target - mt
    cov = t.T @ s / len(s)
    u, d, vt = np.linalg.svd(cov)
    sign = np.eye(3)
    if np.linalg.det(u) * np.linalg.det(vt) < 0:
        sign[2, 2] = -1
    rot = u @ sign @ vt
    scale = float((d * np.diag(sign)).sum() / (s ** 2).sum(1).mean())
    shift = mt - scale * rot @ ms
    return scale, rot, shift


def lay_onto(points, bvh, start, back_points=None, back_bvh=None):
    """ICP: points (n, 3) carried by a scale, a turn and a shift onto the surface in bvh, from start (4x4); each round
    the nearest surface point of each, the worst let go (FIT_KEEP). With back_points (m, 3) and back_bvh (the moving
    surface, in its own frame), also the other way: each of back_points to its nearest point of the moving surface, so a
    smaller copy that lies on the surface from inside (the face on her face, its skull inside hers) is pulled out to
    meet the rest of it. The transform (4x4) and how far the kept points end from the surface each way (metres,
    medians; the second None without back_points)."""
    m = start.copy()
    err = back_err = None
    for _ in range(FIT_STEPS):
        moved = np.array([(m @ Vector(p))[:] for p in points])
        near = np.array([bvh.find_nearest(Vector(p))[0][:] for p in moved])
        dist = np.linalg.norm(near - moved, axis=1)
        keep = dist <= np.quantile(dist, FIT_KEEP)
        source, target = [moved[keep]], [near[keep]]
        err = float(np.median(dist[keep]))
        if back_points is not None:
            inverse = m.inverted()
            on = np.array([(m @ back_bvh.find_nearest(inverse @ Vector(p))[0])[:] for p in back_points])
            back = np.linalg.norm(on - back_points, axis=1)
            kept = back <= np.quantile(back, FIT_KEEP)
            source.append(on[kept])
            target.append(back_points[kept])
            back_err = float(np.median(back[kept]))
        scale, rot, shift = umeyama(np.concatenate(source), np.concatenate(target))
        step = Matrix.Translation(Vector(shift)) @ (Matrix(rot.tolist()).to_4x4() @ Matrix.Scale(scale, 4))
        m = step @ m
    return m, err, back_err


def nose_and_width(points):
    """A head's (n, 3; the face toward -y) most forward point, its nose's tip, and its width (x, outliers clipped)."""
    lo, hi = np.percentile(points[:, 0], [1, 99])
    front = points[points[:, 1] <= np.percentile(points[:, 1], 0.2)]
    return front.mean(0), hi - lo


def face_adjacency(ob):
    """Each face's neighbours across its edges: (pairs (m, 2) of face indices)."""
    by_edge = {}
    for p in ob.data.polygons:
        for key in p.edge_keys:
            by_edge.setdefault(key, []).append(p.index)
    return np.array([(f[0], f[1]) for f in by_edge.values() if len(f) == 2], dtype=np.int64).reshape(-1, 2)


def classify_and_fit(ob, image, head_co, head_faces):
    """ob: Tripo's head with its hair, one mesh (modified in place: laid on the body's head). image: its colour map.
    head_co, head_faces: the body's head. Returns (is_hair per face, each face's distance off the body's head (signed,
    metres), each face's paint, the report).

    The skin is the largest patch of the head's lighter paint (its face, ears, neck; a shaved scalp): a hair's own
    highlights are as light as skin, but they lie in specks of their own, not joined to the face. That skin alone is
    laid onto the body's head, from a first guess its ears give (ear to ear as wide as hers, their middle on hers: a
    hair hanging past the head makes the whole model wider than a head, and the fit from the model's width settled on a
    shrunken head inside hers). Every face not of that skin is hair, and the hair then takes the skin's faces beside it
    that stand off her head (a highlight at the hairline joined to the face), until none is left; of the hair, the
    largest piece and every piece that stands off her head (BRIDGE faces at least), not the brows, lashes and lips."""
    me = ob.data
    paint = face_colours(ob, image)
    light = paint @ np.array([0.2126, 0.7152, 0.0722])
    # The line is drawn between the two kinds the head mostly has: the few faces whose paint is off the map (white)
    # or in a crease (black) would pull it to themselves.
    line = otsu(light[(light >= np.quantile(light, 0.01)) & (light <= np.quantile(light, 0.99))])
    dark = light < line
    label = patches(ob, ~dark)
    kinds, counts = np.unique(label[label >= 0], return_counts=True)
    skin = label == kinds[np.argmax(counts)]
    report = {"faces": len(me.polygons), "light_line": round(line, 3), "dark_faces": int(dark.sum()),
              "light_patches": len(kinds), "skin_faces": int(skin.sum())}

    # The skin onto the body's head: nose on nose, as wide as hers, at three sizes about that; each laid on both ways
    # (its skin onto her head, her head onto it whole), the one that lies closest both ways kept.
    co = np.array([v.co[:] for v in me.vertices])
    skin_verts = np.zeros(len(co), bool)
    for p in me.polygons:
        if skin[p.index]:
            skin_verts[p.vertices] = True
    head = np.array([c[:] for c in head_co])
    head_nose, head_width = nose_and_width(head)
    skin_nose, skin_width = nose_and_width(co[skin_verts])
    bvh = BVHTree.FromPolygons(head_co, head_faces)
    own = BVHTree.FromPolygons([v.co.copy() for v in me.vertices], [tuple(p.vertices) for p in me.polygons])
    rng = np.random.default_rng(1)
    points = co[skin_verts]
    if len(points) > FIT_POINTS:
        points = points[rng.choice(len(points), FIT_POINTS, replace=False)]
    back_points = head if len(head) <= FIT_POINTS else head[rng.choice(len(head), FIT_POINTS, replace=False)]
    tries = []
    for factor in FIT_SIZES:
        scale = factor * head_width / skin_width
        start = Matrix.Translation(Vector(head_nose - scale * skin_nose)) @ Matrix.Scale(scale, 4)
        m, err, back_err = lay_onto(points, bvh, start, back_points, own)
        tries.append((err + back_err, m, err, back_err, factor))
    _, m, err, back_err, factor = min(tries, key=lambda t: t[0])
    me.transform(m)
    me.update()
    report["laid_on_head"] = {"first_scale": round(float(head_width / skin_width), 4), "started_at": factor,
                              "scale": round(float(m.to_scale().x), 4),
                              "turn_deg": [round(math.degrees(a), 2) for a in m.to_euler()],
                              "skin_off_mm_median": round(err * 1000, 2), "head_off_mm_median": round(back_err * 1000, 2),
                              "tries_mm": [[t[4], round(t[2] * 1000, 2), round(t[3] * 1000, 2)] for t in tries]}

    # Each face's middle: how far off her head (signed by her head's normal there: inside it, less than nothing).
    off = np.zeros(len(me.polygons))
    for p in me.polygons:
        at, normal, _, _ = bvh.find_nearest(p.center)
        off[p.index] = (p.center - at).dot(normal)

    # The hair: of all but the skin, the largest piece and every piece standing off her head (not the brows, lashes,
    # pupils and lips); then, GROW_RINGS rings from it, the skin's faces beside it that stand off her head (a highlight at
    # the hairline joined to the face). Only from the hair, and only so far: Tripo's face is not hers to the millimetre,
    # and a brow ridge or a neck standing off hers is skin all the same.
    pairs = face_adjacency(ob)
    # A light patch apart from the face that lies on her head is skin too (the scalp between cornrows, painted by
    # Tripo): the hair's own highlights lie on the hair, which stands off her head.
    light_label = patches(ob, ~dark)
    on_head = 0
    for k in np.unique(light_label[light_label >= 0]):
        faces = light_label == k
        if not skin[faces].any() and np.median(off[faces]) < STANDS_OFF:
            skin |= faces
            on_head += int(faces.sum())
    label = patches(ob, ~skin)
    kinds, counts = np.unique(label[label >= 0], return_counts=True)
    largest = kinds[np.argmax(counts)]
    kept = {largest} | {k for k, n in zip(kinds, counts) if n >= BRIDGE and np.median(off[label == k]) > STANDS_OFF}
    hair = np.isin(label, list(kept))
    grown = np.zeros(len(hair), bool)
    for _ in range(GROW_RINGS):
        touching = np.zeros(len(hair), bool)
        touching[pairs[:, 0][hair[pairs[:, 1]]]] = True
        touching[pairs[:, 1][hair[pairs[:, 0]]]] = True
        take = touching & ~hair & (off > STANDS_OFF)
        hair |= take
        grown |= take
    is_hair = hair
    report.update({"scalp_faces": on_head, "hair_grown_into_skin": int(grown.sum()), "hair_pieces": len(kinds), "hair_pieces_kept": len(kept),
                   "hair_faces": int(is_hair.sum()),
                   # The hair's own colour: its darker faces' (its highlights are as light as skin).
                   "hair_paint": [round(float(c), 3) for c in paint[is_hair & dark].mean(0)],
                   "skin_paint": [round(float(c), 3) for c in paint[skin].mean(0)]})
    report["grown"] = grown
    return is_hair, off, paint, report


def cut_from_head(ob, image, head_co, head_faces):
    """ob: Tripo's head with its hair, one mesh (modified in place: laid on the body's head, its skin deleted, the hair
    left; classify_and_fit). image: its colour map. head_co, head_faces: the body's head. Returns the report."""
    import bmesh
    me = ob.data
    is_hair, _, _, report = classify_and_fit(ob, image, head_co, head_faces)
    report.pop("grown")

    # The skin away: the hair alone remains.
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.faces[i] for i in np.nonzero(~is_hair)[0]], context="FACES")
    bm.to_mesh(me)
    bm.free()
    me.update()
    report["hair_vertices"] = len(me.vertices)
    return report


def paint_hair_only(image, ob, size, line=None, hair_colour=None):
    """The colour map at size, black wherever no face of ob (the hair alone, by now) is drawn, grown MASK_GROW texels.
    With line (the paint's light between skin and hair) and hair_colour: the skin's texels under the hair's faces at
    its cut edge (EDGE_RINGS rings of faces from it: a face at the hairline is cut as hair, its edge still painted
    skin) are painted the hair's colour; the hair's own highlights inside it, as light as skin, are left as they are."""
    image.scale(size, size)
    px = np.array(image.pixels[:], dtype=np.float32).reshape(size, size, 4)
    me = ob.data
    uv = me.uv_layers.active.data
    edge_faces = cut_edge_faces(ob, EDGE_RINGS)
    mask = np.zeros((size, size), bool)
    edge = np.zeros((size, size), bool)
    for p in me.polygons:
        pts = np.array([(uv[l].uv.x * size, uv[l].uv.y * size) for l in p.loop_indices])
        for i in range(1, len(pts) - 1):
            a, b, c = pts[0], pts[i], pts[i + 1]
            x0, x1 = int(max(0, math.floor(min(a[0], b[0], c[0])))), int(min(size - 1, math.ceil(max(a[0], b[0], c[0]))))
            y0, y1 = int(max(0, math.floor(min(a[1], b[1], c[1])))), int(min(size - 1, math.ceil(max(a[1], b[1], c[1]))))
            if x1 < x0 or y1 < y0:
                continue
            xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(d) < 1e-9:
                continue
            l1 = ((b[1] - c[1]) * (xs - c[0]) + (c[0] - b[0]) * (ys - c[1])) / d
            l2 = ((c[1] - a[1]) * (xs - c[0]) + (a[0] - c[0]) * (ys - c[1])) / d
            l3 = 1 - l1 - l2
            inside = (l1 >= -1e-6) & (l2 >= -1e-6) & (l3 >= -1e-6)
            mask[y0:y1 + 1, x0:x1 + 1] |= inside
            if edge_faces[p.index]:
                edge[y0:y1 + 1, x0:x1 + 1] |= inside
    grown = mask.copy()
    for _ in range(MASK_GROW):
        grown |= np.roll(grown, 1, 0) | np.roll(grown, -1, 0) | np.roll(grown, 1, 1) | np.roll(grown, -1, 1)
    for _ in range(MASK_GROW):
        edge |= np.roll(edge, 1, 0) | np.roll(edge, -1, 0) | np.roll(edge, 1, 1) | np.roll(edge, -1, 1)
    recoloured = 0
    if line is not None and hair_colour is not None:
        light = px[:, :, :3] @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
        skin = edge & grown & (light > line)
        px[skin, :3] = np.array(hair_colour, dtype=np.float32)
        recoloured = int(skin.sum())
    px[~grown, :3] = 0.0
    image.pixels = px.ravel()
    return {"texels_painted": int(mask.sum()), "share": round(float(mask.mean()), 4), "edge_faces": int(edge_faces.sum()),
            "skin_texels_recoloured": recoloured}


def cut_edge_faces(ob, rings):
    """The faces within rings of the mesh's open edge (where its skin was cut away): a bool per face."""
    me = ob.data
    count = {}
    for p in me.polygons:
        for key in p.edge_keys:
            count[key] = count.get(key, 0) + 1
    near = np.array([any(count[k] == 1 for k in p.edge_keys) for p in me.polygons], dtype=bool)
    pairs = face_adjacency(ob)
    for _ in range(rings - 1):
        grow = near.copy()
        grow[pairs[:, 0][near[pairs[:, 1]]]] = True
        grow[pairs[:, 1][near[pairs[:, 0]]]] = True
        near = grow
    return near
