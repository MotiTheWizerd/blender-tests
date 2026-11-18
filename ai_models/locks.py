"""A hair's locks: what of it stands or hangs free of the head, each lock on a chain of bones of its own, so Forge
moves it (HairLocks: a spring bone each, with gravity, the body and the other locks to meet). hair.py calls this when
the hair's model.json says "locks": true.

The hair is split in two. Its cap lies on the skull: where the hair over a spot of the scalp is no thicker than CAP
(braids, hair combed flat; the hair over a spot: every hair point whose nearest point of the head lies within REACH
of it, so a ponytail lying on the back of the head is free inside and out, not cap where it touches), above the
skull's base (the height of the nose's tip: below it the head is face, jaw and neck, which hair hangs beside, not on).
The cap stays with the hair's own bone. The rest is free: a ponytail or a bun standing off the skull, hair hanging
past the skull's base.

Each free piece (joined through free points; fewer than LEAST_POINTS stay with the cap) meets the cap along a line.
Where it is held there, its roots, is said by the hair's model.json "roots" (points in the body's frame, one per
chain: a ponytail's tie, places along where hair hangs from; each takes the meeting line's points nearest it, within
ROOT_REACH): only a person can tell a tie from the place a ponytail merely lies against the head. Without roots, the
whole line is shared out between chains SPACING apart (a bun's base, hair hanging round the head). Each point of the
piece goes to the chain whose root is nearest it over the hair's surface (geodesics: a lock follows the hair, not a
straight line through the air). A
lock's joints are the middles of its points at even steps of their distance from its root over the lock itself, about
BONE apart, so the chain runs down the middle of the lock as the lock runs; its radius at each joint is how thick the
lock is there.

Weights: along a chain each point is shared between the two bones whose middles it lies between (so a lock bends
smoothly, not at its joints); its first ROOT_BLEND past its root along its first bone it is shared with the hair's bone
(it leaves the cap without a crease; hair beside or behind its root stays with the cap); where two locks of a piece meet, LOCK_BLEND either side, between both (the hair between two chains follows
both). At most four bones a point.
"""
import heapq
import numpy as np
from mathutils import Vector

CAP = 0.015         # metres thick the hair lying on the skull is at most over a spot; thicker, it stands free
REACH = 0.012       # metres round a spot of the scalp whose hair counts as over it
ROOT_REACH = 0.04   # metres from a given root the meeting line's points it takes reach
SPACING = 0.06      # metres between chains along a free piece's root
BONE = 0.05         # metres a chain's bone spans, about
MOST_BONES = 10
LEAST_POINTS = 40   # a free piece smaller than this stays with the cap
ROOT_BLEND = 0.015  # metres from its root over which a lock's weight comes from the hair's bone
LOCK_BLEND = 0.03   # metres either side of where two locks meet over which their weights mix
INFLUENCES = 4      # bones a point may follow at most
ACROSS = 3.0        # how much dearer going across (level) is than going down or up, choosing a point's root: hair hangs


def neighbours(count, edges):
    """Each point's neighbours along edges, with the edges' lengths and their hanging lengths (level going ACROSS times
    dearer): a list per point of (other, length, hanging)."""
    out = [[] for _ in range(count)]
    for a, b, length, hanging in edges:
        out[a].append((b, length, hanging))
        out[b].append((a, length, hanging))
    return out


def geodesic(graph, sources, allowed, hanging=False):
    """How far each point is from the nearest of sources over the surface, through allowed points only (inf: not
    reached); hanging: as hair hangs (going level ACROSS times dearer than going down or up)."""
    far = np.full(len(graph), np.inf)
    heap = []
    for s in sources:
        far[s] = 0.0
        heap.append((0.0, s))
    heapq.heapify(heap)
    while heap:
        d, p = heapq.heappop(heap)
        if d > far[p]:
            continue
        for q, length, hang in graph[p]:
            if not allowed[q]:
                continue
            nd = d + (hang if hanging else length)
            if nd < far[q]:
                far[q] = nd
                heapq.heappush(heap, (nd, q))
    return far


def pieces(graph, chosen):
    """The chosen points joined through chosen points: a piece number per point (-1: not chosen)."""
    label = np.full(len(graph), -1)
    count = 0
    for start in np.nonzero(chosen)[0]:
        if label[start] >= 0:
            continue
        stack = [start]
        label[start] = count
        while stack:
            p = stack.pop()
            for q, _, _ in graph[p]:
                if chosen[q] and label[q] < 0:
                    label[q] = count
                    stack.append(q)
        count += 1
    return label, count


def farthest_samples(points, count):
    """count of points spread as far apart as they go (farthest point sampling, from the one farthest from their
    middle): their indices."""
    middle = points.mean(0)
    chosen = [int(np.argmax(np.linalg.norm(points - middle, axis=1)))]
    near = np.linalg.norm(points - points[chosen[0]], axis=1)
    while len(chosen) < count:
        nxt = int(np.argmax(near))
        chosen.append(nxt)
        near = np.minimum(near, np.linalg.norm(points - points[nxt], axis=1))
    return chosen


def chain_place(points, joints):
    """Each point's place along a chain (joints (k+1, 3)): k + its part along the bone nearest it (0 at the root, the
    bones' count at the tip)."""
    best = np.full(len(points), np.inf)
    place = np.zeros(len(points))
    for k in range(len(joints) - 1):
        a, b = joints[k], joints[k + 1]
        ab = b - a
        t = np.clip(((points - a) @ ab) / max(ab @ ab, 1e-12), 0, 1)
        d = np.linalg.norm(points - (a + np.outer(t, ab)), axis=1)
        closer = d < best
        best[closer] = d[closer]
        place[closer] = k + t[closer]
    return place


def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def thickness(points, head_points, head_bvh):
    """How far each point is off the head, and how thick the hair is over the spot of the scalp it lies over: the
    farthest of the points whose nearest head point lies within REACH of its own."""
    from mathutils.kdtree import KDTree
    tree = KDTree(len(head_points))
    for i, c in enumerate(head_points):
        tree.insert(Vector(c), i)
    tree.balance()
    off = np.zeros(len(points))
    spot = np.zeros(len(points), dtype=np.int64)
    for i, p in enumerate(points):
        at = head_bvh.find_nearest(Vector(p))[0]
        off[i] = (Vector(p) - at).length
        spot[i] = tree.find(at)[1]
    over = np.zeros(len(head_points))
    np.maximum.at(over, spot, off)
    spread = over.copy()
    for i in np.nonzero(over > 0)[0]:
        for _, j, _ in tree.find_range(Vector(head_points[i]), REACH):
            if over[i] > spread[j]:
                spread[j] = over[i]
    return off, spread[spot]


def find(points, edges, head_points, head_bvh, skull_base, roots=None):
    """points (n, 3), the hair's, in the world's frame; edges: (a, b) point pairs; head_points, head_bvh: the head it
    lies on; skull_base: the height (z) below which the head is no skull to lie on; roots: where gathered hair is held
    (a ponytail's tie: [x, y, z] or {"at": [x, y, z], "reach": metres}). Returns the locks (a list of dicts: "joints"
    (k+1, 3) from root to tip, "radii" (k,) at joints 1..k, "piece", "kind"), the links between neighbouring locks
    (pairs), the weights (n, locks, MOST_BONES + 1: the share of each lock's bones; the rest the hair's bone), each
    point's distance off the head, which points are free, and a report."""
    n = len(points)

    def hanging(d):
        return float(np.hypot(ACROSS * np.hypot(d[0], d[1]), d[2]))
    edge_list = [(a, b, float(np.linalg.norm(points[a] - points[b])), hanging(points[a] - points[b])) for a, b in edges]
    graph = neighbours(n, edge_list)
    off, thick = thickness(points, head_points, head_bvh)
    free = (thick > CAP) | (points[:, 2] < skull_base)
    label, count = pieces(graph, free)
    report = {"cap_points": int((~free).sum()), "free_points": int(free.sum()), "free_pieces": count,
              "cap_thickness_m": round(float(np.percentile(off[~free], 95)), 4) if (~free).any() else 0.0}
    given = [{"at": np.array(r if isinstance(r, list) else r["at"], dtype=float),
              "reach": ROOT_REACH if isinstance(r, list) else float(r.get("reach", ROOT_REACH))} for r in (roots or [])]
    # The head's upright middle (its skull's), which hanging hair hangs round.
    skull = head_points[head_points[:, 2] > skull_base]
    centre = (skull.min(0) + skull.max(0)) / 2
    angle = np.arctan2(points[:, 0] - centre[0], points[:, 1] - centre[1])     # 0 behind, the face at +-pi
    across = np.hypot(points[:, 0] - centre[0], points[:, 1] - centre[1])

    locks, links = [], []
    lock_of = np.full(n, -1)
    owning = []                 # per lock: how far each point is from it, as whose a point is (inf off its piece)
    pieces_report = []
    for piece in range(count):
        inside = label == piece
        if inside.sum() < LEAST_POINTS:
            free[inside] = False
            continue
        idx = np.nonzero(inside)[0]
        line = np.array([p for p in idx if any(not free[q] for q, _, _ in graph[p])], dtype=np.int64)
        if not len(line):
            # Joined to the cap nowhere (a piece apart): its points nearest the head are where it meets it.
            line = idx[off[idx] <= np.percentile(off[idx], 5)]
        extent = float(np.linalg.norm(points[line].max(0) - points[line].min(0)))
        # Gathered hair: held at a given root (the line's points within its reach), or, with none here, a piece that rises
        # from the line (a bun) held all along it. The rest of the line holds hanging hair: a curtain.
        held = [r for r in given if np.linalg.norm(points[line] - r["at"], axis=1).min() <= r["reach"]]
        taken = np.zeros(len(line), bool)
        starts = []
        for r in held:
            mine = np.linalg.norm(points[line] - r["at"], axis=1) <= r["reach"]
            starts.append(line[mine])
            taken |= mine
        if not held and np.median(points[idx, 2]) > np.median(points[line, 2]):
            # A piece that rises from where it meets the cap (a bun, a topknot) is gathered there, all along it.
            starts.append(line)
            taken[:] = True
        hangs = [geodesic(graph, st, inside, hanging=True) for st in starts]
        rest = line[~taken]
        distances = list(hangs)
        kinds = ["gathered"] * len(hangs)
        columns = []
        if len(rest):
            from_rest = geodesic(graph, rest, inside, hanging=True)
            gathered = np.min(np.stack(hangs), axis=0) if hangs else np.full(n, np.inf)
            curtain = inside & (from_rest < gathered)
            if curtain.sum() >= LEAST_POINTS:
                # Columns round the head, SPACING apart along it, each a strip of the curtain: whose a point is, by how
                # far it hangs from the line and how far round the head from the column it is.
                lo, hi = np.percentile(angle[curtain], [2, 98])
                radius = float(np.median(across[curtain]))
                k = max(1, int(round(radius * (hi - lo) / SPACING)))
                columns = lo + (np.arange(k) + 0.5) * (hi - lo) / k
                for c in columns:
                    distances.append(from_rest + radius * np.abs(angle - c))
                    kinds.append("hanging")
        if not distances:
            free[inside] = False
            continue
        stacked = np.stack(distances)
        nearest = np.argmin(stacked, axis=0)
        first = len(locks)
        for c, kind in enumerate(kinds):
            mine = inside & (nearest == c) & np.isfinite(stacked[c])
            if mine.sum() < 8:
                continue
            if kind == "gathered":
                # Along it: how far each of its points is from its root over the lock itself; its joints the middles
                # of its points at even steps of that, about BONE apart, the last at its 95th part.
                g = geodesic(graph, starts[c], mine)
                length = float(np.percentile(g[mine & np.isfinite(g)], 95))
                bones = int(np.clip(round(length / BONE), 1, MOST_BONES))
                step = length / bones
                joints = [points[starts[c]].mean(0)]
                for k in range(1, bones + 1):
                    ring = mine & (np.abs(g - k * step) <= 0.35 * step)
                    if ring.sum() < 3:
                        ring = mine & (np.abs(g - k * step) <= 0.7 * step)
                    if ring.any():
                        joints.append(points[ring].mean(0))
                    else:
                        joints.append(2 * joints[-1] - joints[-2] if k > 1 else joints[-1] + np.array([0.0, 0.0, -step]))
            else:
                # Hanging: from its top (its highest points) down, its middle at even heights about BONE apart to its
                # bottom.
                top_points = np.nonzero(mine & (points[:, 2] >= np.percentile(points[mine, 2], 95)))[0]
                top = points[top_points].mean(0)
                bottom = float(np.percentile(points[mine, 2], 3))
                bones = int(np.clip(round((top[2] - bottom) / BONE), 1, MOST_BONES))
                step = (top[2] - bottom) / bones
                joints = [top]
                for k in range(1, bones + 1):
                    level = top[2] - k * step
                    ring = mine & (np.abs(points[:, 2] - level) <= 0.5 * step)
                    if ring.sum() < 3:
                        ring = mine & (np.abs(points[:, 2] - level) <= step)
                    joints.append(points[ring].mean(0) if ring.any() else joints[-1] + np.array([0.0, 0.0, -step]))
                length = float(top[2] - bottom)
            joints = np.array(joints, dtype=float)
            if length < 0.5 * BONE:
                continue                                  # a scrap: it stays with the cap
            bones = len(joints) - 1
            # Along the chain: each point's place, its nearest bone's (its part along it), counted in bones; its
            # radius at each joint: how far across the chain the lock's points round it lie (the thinner way).
            along = chain_place(points, joints)
            radii = []
            for k in range(1, bones + 1):
                a, b = joints[k - 1], joints[k]
                axis = (b - a) / max(np.linalg.norm(b - a), 1e-6)
                ring = mine & (np.abs(along - k) <= 0.4)
                rel = points[ring] - b
                spread = np.linalg.norm(rel - np.outer(rel @ axis, axis), axis=1) if ring.any() else np.array([0.01])
                radii.append(float(np.clip(np.percentile(spread, 30), 0.004, 0.03)))
            lock_of[mine] = len(locks)
            locks.append({"joints": joints, "radii": np.array(radii), "piece": piece, "kind": kind, "length": length,
                          "along": along})
            owning.append(stacked[c])
        made = list(range(first, len(locks)))
        # Neighbours: two locks of a piece whose points meet across an edge.
        for i in made:
            for j in made:
                if i < j:
                    a = lock_of == i
                    b = lock_of == j
                    meet = sum(1 for p, q, _, _ in edge_list if (a[p] and b[q]) or (a[q] and b[p]))
                    if meet >= 3:
                        links.append((i, j))
        pieces_report.append({"points": int(inside.sum()), "line_points": int(len(line)),
                              "line_extent_cm": round(extent * 100, 1),
                              "gathered_roots": [points[st].mean(0).round(3).tolist() for st in starts],
                              "curtain_columns_deg": [round(float(np.degrees(c)), 1) for c in columns],
                              "locks": [locks[i]["kind"] for i in made],
                              "bones": [len(locks[i]["joints"]) - 1 for i in made],
                              "chain_cm": [round(float(np.linalg.norm(np.diff(locks[i]["joints"], axis=0), axis=1).sum()) * 100, 1)
                                           for i in made]})
    report["pieces"] = pieces_report
    report["locks"] = len(locks)
    report["links"] = [list(l) for l in links]

    # Weights: along each lock's chain, from the cap at its root; where two locks meet, shared: a point a neighbour is d
    # further from than its own (as whose a point is) takes half of its weight from the neighbour at d = 0, none from
    # LOCK_BLEND.
    def given(d):
        return 0.5 * (1 - smoothstep(d / LOCK_BLEND))
    weights = np.zeros((n, len(locks), MOST_BONES + 1))
    near_of = {i: [b if a == i else a for a, b in links if i in (a, b)] for i in range(len(locks))}
    for i, lock in enumerate(locks):
        g = owning[i]
        bones = len(lock["joints"]) - 1
        own = lock_of == i
        share = np.zeros(n)
        kept = np.ones(n)
        for j in near_of[i]:
            gap = owning[j] - g                             # for my points: how much further the neighbour is
            kept -= np.where(own & np.isfinite(gap), given(np.where(np.isfinite(gap), gap, LOCK_BLEND)), 0.0)
            back = g - owning[j]                            # for the neighbour's points: how much further I am
            share = np.where((lock_of == j) & np.isfinite(back), given(np.where(np.isfinite(back), back, LOCK_BLEND)), share)
        share = np.where(own, kept, share)
        reach = (share > 0) & np.isfinite(g)
        t = np.where(reach, lock["along"], 0.0)
        for k in range(bones):
            # A tent over each bone's middle (k + 0.5): the first bone has all before its middle, the last all past it.
            w = np.clip(1 - np.abs(t - (k + 0.5)), 0, 1)
            if k == 0:
                w = np.where(t < 0.5, 1.0, w)
            if k == bones - 1:
                w = np.where(t > bones - 0.5, 1.0, w)
            # From the cap: as far past its root as along its first bone (hair beside or behind the root, on the
            # scalp round a bun's base or a ponytail's tie, stays with the cap).
            first = lock["joints"][1] - lock["joints"][0]
            past = (points - lock["joints"][0]) @ (first / max(np.linalg.norm(first), 1e-9))
            weights[:, i, k] = np.where(reach, w * share * smoothstep(past / ROOT_BLEND), 0.0)
    report["weighted_points"] = int((weights.sum(axis=(1, 2)) > 0).sum())
    return locks, links, weights, off, free, report


def limit(cap_weight, weights, most=INFLUENCES):
    """Each point's at most `most` biggest weights (the hair's bone's among them), summing to one: (hair (n,),
    weights (n, locks, bones)) made so."""
    n = len(cap_weight)
    flat = np.concatenate([cap_weight[:, None], weights.reshape(n, -1)], axis=1)
    order = np.argsort(-flat, axis=1)
    keep = np.zeros_like(flat, dtype=bool)
    np.put_along_axis(keep, order[:, :most], True, axis=1)
    flat = np.where(keep, flat, 0.0)
    flat /= np.maximum(flat.sum(1, keepdims=True), 1e-9)
    return flat[:, 0], flat[:, 1:].reshape(weights.shape)
