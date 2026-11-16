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
SAMPLE = 2048        # the colour map is read at this size to tell hair from skin (not to draw)
MASK_GROW = 6        # texels the hair's paint keeps past its faces' edges (the map is filtered between texels)


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


def lay_onto(points, bvh, start_scale, start_shift):
    """ICP: points (n, 3) carried by a scale, a turn and a shift onto the surface in bvh, from a first guess of scale
    and shift (no turn); each round the nearest surface point of each, the worst let go. The transform (4x4) and how
    far the kept points end from the surface (metres, median)."""
    m = Matrix.Translation(Vector(start_shift)) @ Matrix.Scale(start_scale, 4)
    err = None
    for _ in range(FIT_STEPS):
        moved = np.array([(m @ Vector(p))[:] for p in points])
        near = np.array([bvh.find_nearest(Vector(p))[0][:] for p in moved])
        dist = np.linalg.norm(near - moved, axis=1)
        keep = dist <= np.quantile(dist, FIT_KEEP)
        scale, rot, shift = umeyama(moved[keep], near[keep])
        step = Matrix.Translation(Vector(shift)) @ (Matrix(rot.tolist()).to_4x4() @ Matrix.Scale(scale, 4))
        m = step @ m
        err = float(np.median(dist[keep]))
    return m, err


def cut_from_head(ob, image, head_co, head_faces):
    """ob: Tripo's head with its hair, one mesh (modified in place: laid on the body's head, its skin deleted, the hair
    left). image: its colour map. head_co, head_faces: the body's head. Returns the report."""
    import bmesh
    me = ob.data
    paint = face_colours(ob, image)
    light = paint @ np.array([0.2126, 0.7152, 0.0722])
    # The line is drawn between the two kinds the head mostly has: the few faces whose paint is off the map (white)
    # or in a crease (black) would pull it to themselves.
    line = otsu(light[(light >= np.quantile(light, 0.01)) & (light <= np.quantile(light, 0.99))])
    dark = light < line
    label = patches(ob, dark)
    kinds, counts = np.unique(label[label >= 0], return_counts=True)
    hair_patch = kinds[np.argmax(counts)]
    is_hair = label == hair_patch
    report = {"faces": len(me.polygons), "light_line": round(line, 3), "dark_faces": int(dark.sum()),
              "dark_patches": len(kinds), "hair_faces": int(is_hair.sum()),
              "hair_paint": [round(float(c), 3) for c in paint[is_hair].mean(0)],
              "skin_paint": [round(float(c), 3) for c in paint[~is_hair].mean(0)]}

    # The skin onto the body's head. A first guess: as wide as it (ear to ear), crown on crown, middle on middle.
    co = np.array([v.co[:] for v in me.vertices])
    skin_verts = np.zeros(len(co), bool)
    for p in me.polygons:
        if not is_hair[p.index]:
            skin_verts[p.vertices] = True
    head = np.array([c[:] for c in head_co])
    width = (head[:, 0].max() - head[:, 0].min()) / (co[:, 0].max() - co[:, 0].min())
    guess_shift = np.array([head[:, 0].mean(), head[:, 1].mean(), head[:, 2].max()]) - width * np.array(
        [co[:, 0].mean(), co[:, 1].mean(), co[:, 2].max()])
    bvh = BVHTree.FromPolygons(head_co, head_faces)
    skin = co[skin_verts]
    if len(skin) > 6000:
        skin = skin[np.random.default_rng(1).choice(len(skin), 6000, replace=False)]
    m, err = lay_onto(skin, bvh, width, guess_shift)
    me.transform(m)
    me.update()
    scale = m.to_scale()
    report["laid_on_head"] = {"first_width_scale": round(float(width), 4), "scale": round(float(scale.x), 4),
                              "turn_deg": [round(math.degrees(a), 2) for a in m.to_euler()],
                              "skin_off_mm_median": round(err * 1000, 2)}

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
    With line (the paint's light between skin and hair) and hair_colour: the skin's texels under the hair's faces (a
    face at the hairline is cut as hair by its middle, its edge still painted skin) are painted the hair's colour."""
    image.scale(size, size)
    px = np.array(image.pixels[:], dtype=np.float32).reshape(size, size, 4)
    me = ob.data
    uv = me.uv_layers.active.data
    mask = np.zeros((size, size), bool)
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
    grown = mask.copy()
    for _ in range(MASK_GROW):
        grown |= np.roll(grown, 1, 0) | np.roll(grown, -1, 0) | np.roll(grown, 1, 1) | np.roll(grown, -1, 1)
    recoloured = 0
    if line is not None and hair_colour is not None:
        light = px[:, :, :3] @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
        skin = grown & (light > line)
        px[skin, :3] = np.array(hair_colour, dtype=np.float32)
        recoloured = int(skin.sum())
    px[~grown, :3] = 0.0
    image.pixels = px.ravel()
    return {"texels_painted": int(mask.sum()), "share": round(float(mask.mean()), 4), "skin_texels_recoloured": recoloured}
