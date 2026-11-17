"""A hair's buns, each on a bone of its own so Forge can swing it about its base (Forge's SwingingBones). hair.py calls
this when the hair's model.json says "buns": true.

A bun is found by how far it stands off the head: the hair's cap lies within a couple of centimetres of the skull, a bun
stands well off it (OFF and more). Those points are split by side of the parting (the head's middle), one bun each side.
Each bun's bone runs from its base (the head's surface nearest the bun's middle: where it sits on the head, the point it
swings about) out through its middle. Its weights: the bun wholly (from FULL off the head), nothing at the cap (NONE and
nearer), smoothly between, and only near the bun (within its own reach, a little grown), so the base bends as the bun
swings instead of tearing off the cap. The rest of each point's weight stays on the hair's own bone.
"""
import numpy as np
from mathutils import Vector

OFF = 0.03     # metres off the head a point of a bun's core stands at least (the cap: within 1.5 cm on WarriorF)
FULL = 0.025   # a point this far off the head goes wholly with its bun
NONE = 0.012   # and one this near, not at all
REACH = 1.25   # a bun's weights reach this many times its core's own radius round its middle


def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def find(points, head_bvh, middle_x, left_sign):
    """points (n, 3), the hair's, in the world's frame. head_bvh: the head it sits on. middle_x: the parting's x.
    left_sign: +1 when the body's left is +x. Returns {side: (base, middle, weights (n,))} for "Left" and "Right", and
    a report."""
    off = np.array([(Vector(p) - head_bvh.find_nearest(Vector(p))[0]).length for p in points])
    core = off >= OFF
    found, report = {}, {}
    for side, sign in (("Left", left_sign), ("Right", -left_sign)):
        mine = core & (np.sign(points[:, 0] - middle_x) == sign)
        if mine.sum() < 50:
            raise SystemExit(f"BUNS: no {side.lower()} bun ({int(mine.sum())} points stand {OFF * 100:.0f} cm off the head on that side)")
        middle = points[mine].mean(0)
        radius = float(np.percentile(np.linalg.norm(points[mine] - middle, axis=1), 95))
        base = np.array(head_bvh.find_nearest(Vector(middle))[0][:])
        near = np.linalg.norm(points - middle, axis=1) <= radius * REACH
        side_ok = np.sign(points[:, 0] - middle_x) == sign
        weights = np.where(near & side_ok, smoothstep((off - NONE) / (FULL - NONE)), 0.0)
        found[side] = (base, middle, weights)
        report[side] = {"core_points": int(mine.sum()), "weighted_points": int((weights > 0).sum()),
                        "radius_cm": round(radius * 100, 2), "base": [round(float(a), 4) for a in base],
                        "middle": [round(float(a), 4) for a in middle],
                        "height_cm": round(float(np.linalg.norm(middle - base)) * 100, 2)}
    return found, report
