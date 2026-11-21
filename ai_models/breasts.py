"""Bones for a body's breasts, so the game can let them move with her (Forge's SoftTissue springs them after each
frame's animation): pieces.py calls bones() for a body whose model.json says "breasts" (after the torso is laid on, so
the bones are on the final shape), weights() for the body and for each of its body types (chest.py's laid copies, with
the body's chest wall), and apply() with the most each vertex weighs in any of them: one Body wears every type as a
shape key, so its weights must reach every type's breast (a bigger breast's lower pole is her ribs' skin in her own; the
game springs the tissue by the type's share).

Each breast a bone of its own (<prefix>LeftBreast, <prefix>RightBreast: the character's left at +x), a child of the
chest's bone (Spine2), from the chest wall behind the nipple out to the nipple. The nipple is the most forward point of
the torso on that side, the chest wall as deep as the breastbone at the nipples' height. A vertex is the breast's by
how far it stands proud of the chest wall (the torso round the nipples relaxed to its edge: her ribs with the breasts
taken off): wholly at STAND_FULL, none at the wall, smoothly between, so the soft tissue moves and the ribs round it
don't (by distance from the root it broke on a grown breast, s1024: its most forward point was its sagging lower front,
so its root sat low and its depth outran the reach, and the ribs and belly round it became the breast's); and only as
much as the trunk weighs it (the spine's bones), so no arm or shoulder is pulled along. The weight is taken from the
vertex's other bones in proportion, so every vertex still weighs 1.

Works in the body mesh's frame, which is the world's: metres, front -Y, up Z.
"""
import bpy
from mathutils import Vector

WALL_REACH = 0.62   # the chest wall is found under the torso within this times the nipples' spacing of either nipple
WALL_STEPS = 400    # the region relaxed to its edge this many times: the wall
STAND_FULL = 0.02   # a vertex standing this far (metres) proud of the wall is wholly the breast's; at the wall, none
TRUNK = ("Spine", "Spine1", "Spine2")


def smoothstep(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def find(body, on):
    """A body's nipples (the most forward point of its torso on each side), the breastbone's front at their level (the
    chest wall's depth) and the torso's vertices where on(vertex index)."""
    me = body.data
    co = {i: me.vertices[i].co for i in range(len(me.vertices)) if on(i)}
    zs = sorted(c.z for c in co.values())
    lo, hi = zs[0], zs[-1]
    band = [i for i, c in co.items() if lo + (hi - lo) * 0.4 < c.z < lo + (hi - lo) * 0.85 and abs(c.x) < 0.15]
    nipples = {"Left": min((co[i] for i in band if co[i].x > 0), key=lambda c: c.y),
               "Right": min((co[i] for i in band if co[i].x < 0), key=lambda c: c.y)}
    level = (nipples["Left"].z + nipples["Right"].z) / 2
    wall = min(c.y for c in co.values() if abs(c.x) < 0.01 and abs(c.z - level) < 0.02)    # the breastbone's front
    return nipples, wall, co


def bones(rig, prefix, nipples, wall):
    """Adds the breasts' bones to rig: each from the chest wall (depth wall) behind its nipple out to it, a child of the
    chest's bone."""
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    edit = rig.data.edit_bones
    to_rig = rig.matrix_world.inverted()
    for side, nipple in nipples.items():
        bone = edit.new(f"{prefix}{side}Breast")
        bone.head, bone.tail = to_rig @ Vector((nipple.x, wall, nipple.z)), to_rig @ nipple.copy()
        bone.parent = edit[f"{prefix}Spine2"]
        bone.use_deform = True
    bpy.ops.object.mode_set(mode="OBJECT")


def sides_of(body, on):
    """Which breast each vertex of body where on(vertex index) can be: the character's left at +x. Decided on the body's
    own shape and given to weights() for its types' laid copies, since a chest laid on moves a few vertices by the
    breastbone across the middle."""
    me = body.data
    return {i: "Left" if me.vertices[i].co.x > 0 else "Right" for i in range(len(me.vertices)) if on(i)}


def chest_wall(body, on):
    """The chest wall under a body's breasts: its torso's vertices within WALL_REACH times the nipples' spacing of either
    nipple relaxed to that region's edge (a harmonic surface: her ribs with the breasts taken off, as chest.py finds
    it), with her normal at each, so a vertex's stand over the wall can be read in any of her shapes."""
    import bmesh
    me = body.data
    nipples, _, co = find(body, on)
    spacing = (nipples["Left"] - nipples["Right"]).length
    region = {i for i, c in co.items() if min((c - n).length for n in nipples.values()) < WALL_REACH * spacing}
    bm = bmesh.new(); bm.from_mesh(me); bm.verts.ensure_lookup_table()
    neighbours = {v: [e.other_vert(bm.verts[v]).index for e in bm.verts[v].link_edges] for v in region}
    bm.free()
    held = {v for v in region if any(n not in region for n in neighbours[v])}
    wall = {v: me.vertices[v].co.copy() for v in region}
    for _ in range(WALL_STEPS):
        for v in region - held:
            around = [wall[n] for n in neighbours[v] if n in wall]
            wall[v] = sum(around, Vector()) / len(around)
    return wall, {v: me.vertices[v].normal.copy() for v in region}


def weights(body, prefix, on, wall, normals, sides):
    """What body's vertices weigh to the breasts' bones in its shape: each by how far it stands proud of the chest wall
    (wall, normals: chest_wall()'s, the body's own; wholly the breast's at STAND_FULL, none at the wall, so the ribs
    round it stay) on its side (sides_of()'s, the body's own), and only as much as the trunk weighs it. A body type's
    laid copy is measured this way with the body's wall, normals and sides, so one Body's weights can be the most it
    weighs in any of its types. Returns the report and the weights, {side: {vertex: weight}}, for apply()."""
    me = body.data
    nipples, wall_y, _ = find(body, on)
    spacing = (nipples["Left"] - nipples["Right"]).length
    trunk = {body.vertex_groups[f"{prefix}{b}"].index for b in TRUNK if f"{prefix}{b}" in body.vertex_groups}
    report = {"spacing_cm": round(spacing * 100, 2), "wall_m": round(wall_y, 4)}
    by_side = {side: {} for side in nipples}
    stands = {side: [] for side in nipples}
    for i, under in wall.items():
        side = sides.get(i)
        if side is None:
            continue
        stand = (me.vertices[i].co - under).dot(normals[i])
        stands[side].append(stand)
        of_trunk = sum(g.weight for g in me.vertices[i].groups if g.group in trunk)
        w = smoothstep(stand / STAND_FULL) * min(of_trunk, 1.0)
        if w > 1e-4:
            by_side[side][i] = w
    for side, nipple in nipples.items():
        root = Vector((nipple.x, wall_y, nipple.z))
        report[side] = {"root_m": [round(a, 4) for a in root], "nipple_m": [round(a, 4) for a in nipple],
                        "depth_cm": round((nipple - root).length * 100, 2), "stand_cm_max": round(max(stands[side]) * 100, 2),
                        "weighed": len(by_side[side])}
    return report, by_side


def most(*weights_of):
    """The most each vertex weighs to each breast's bone in any of these (weights()'s): one Body for every type."""
    merged = {}
    for by_side in weights_of:
        for side, w_of in by_side.items():
            mine = merged.setdefault(side, {})
            for i, w in w_of.items():
                mine[i] = max(mine.get(i, 0.0), w)
    return merged


def apply(body, prefix, by_side):
    """Weighs body's vertices to the breasts' bones as by_side says ({side: {vertex: weight}}), the weight taken from
    each vertex's other bones in proportion, so every vertex still weighs 1. Returns per side how many and the most."""
    me = body.data
    counts = {}
    for side, w_of in by_side.items():
        group = body.vertex_groups.get(f"{prefix}{side}Breast") or body.vertex_groups.new(name=f"{prefix}{side}Breast")
        weighed, biggest = 0, 0.0
        for i, w in w_of.items():
            if w <= 1e-4:
                continue
            for g in me.vertices[i].groups:
                g.weight *= 1.0 - w
            group.add([i], w, "REPLACE")
            weighed += 1
            biggest = max(biggest, w)
        counts[side] = {"vertices": weighed, "most": round(biggest, 3)}
    return counts


def add(body, rig, prefix, on):
    """A body with no types: its bones and its own weights at once. Returns the report."""
    nipples, wall_y, _ = find(body, on)
    bones(rig, prefix, nipples, wall_y)
    wall, normals = chest_wall(body, on)
    report, by_side = weights(body, prefix, on, wall, normals, sides_of(body, on))
    for side, counts in apply(body, prefix, by_side).items():
        report[side].update(counts)
    return report
