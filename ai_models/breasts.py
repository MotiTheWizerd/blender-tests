"""Bones for a body's breasts, so the game can let them move with her (Forge's SoftTissue springs them after each
frame's animation): pieces.py calls add() for a body whose model.json says "breasts" (after the torso is laid on, so
the bones and weights are on the final shape).

Each breast a bone of its own (<prefix>LeftBreast, <prefix>RightBreast: the character's left at +x), a child of the
chest's bone (Spine2), from the chest wall behind the nipple out to the nipple. The nipple is the most forward point of
the torso on that side, the chest wall as deep as the breastbone at the nipples' height. A vertex is the breast's by
how far it lies from the bone's root: wholly within the breast's own depth past it (FULL), none at REACH times half the
nipples' spacing, smoothly between, so the soft tissue moves and the ribs round it don't; and only as much as the
trunk weighs it (the spine's bones), so no arm or shoulder is pulled along. The weight is taken from the vertex's other
bones in proportion, so every vertex still weighs 1.

Works in the body mesh's frame, which is the world's: metres, front -Y, up Z.
"""
import bpy
from mathutils import Vector

REACH = 0.5       # where a breast's weight ends, times the nipples' spacing (her 0.24 m: 12 cm from the root)
FULL = 1.1        # wholly the breast's within this times its depth (root to nipple)
TRUNK = ("Spine", "Spine1", "Spine2")


def smoothstep(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def add(body, rig, prefix, on):
    """Adds the breasts' bones to rig and their weights to body's vertices where on(vertex index) (the Body piece's
    torso part). Returns the report."""
    me = body.data
    co = {i: me.vertices[i].co for i in range(len(me.vertices)) if on(i)}
    zs = sorted(c.z for c in co.values())
    lo, hi = zs[0], zs[-1]
    band = [i for i, c in co.items() if lo + (hi - lo) * 0.4 < c.z < lo + (hi - lo) * 0.85 and abs(c.x) < 0.15]
    nipples = {"Left": min((co[i] for i in band if co[i].x > 0), key=lambda c: c.y),
               "Right": min((co[i] for i in band if co[i].x < 0), key=lambda c: c.y)}
    level = (nipples["Left"].z + nipples["Right"].z) / 2
    wall = min(c.y for c in co.values() if abs(c.x) < 0.01 and abs(c.z - level) < 0.02)    # the breastbone's front
    spacing = (nipples["Left"] - nipples["Right"]).length
    reach = REACH * spacing

    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bones = rig.data.edit_bones
    to_rig = rig.matrix_world.inverted()
    roots = {}
    for side, nipple in nipples.items():
        root = Vector((nipple.x, wall, nipple.z))
        bone = bones.new(f"{prefix}{side}Breast")
        bone.head, bone.tail = to_rig @ root, to_rig @ nipple.copy()
        bone.parent = bones[f"{prefix}Spine2"]
        bone.use_deform = True
        roots[side] = root
    bpy.ops.object.mode_set(mode="OBJECT")

    trunk = {body.vertex_groups[f"{prefix}{b}"].index for b in TRUNK if f"{prefix}{b}" in body.vertex_groups}
    report = {"spacing_cm": round(spacing * 100, 2), "reach_cm": round(reach * 100, 2)}
    for side, root in roots.items():
        group = body.vertex_groups.new(name=f"{prefix}{side}Breast")
        depth = (nipples[side] - root).length
        full = FULL * depth
        weighed, most = 0, 0.0
        for i, c in co.items():
            if (c.x > 0) != (side == "Left"):
                continue
            d = (c - root).length
            if d >= reach:
                continue
            v = me.vertices[i]
            of_trunk = sum(g.weight for g in v.groups if g.group in trunk)
            w = smoothstep((reach - d) / max(reach - full, 1e-6)) * min(of_trunk, 1.0)
            if w <= 1e-4:
                continue
            for g in v.groups:
                g.weight *= 1.0 - w
            group.add([i], w, "REPLACE")
            weighed += 1
            most = max(most, w)
        report[side] = {"root_m": [round(a, 4) for a in root], "nipple_m": [round(a, 4) for a in nipples[side]],
                        "depth_cm": round(depth * 100, 2), "vertices": weighed, "most": round(most, 3)}
    return report
