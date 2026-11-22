"""Her on a Tripo body: the Tripo body placed at her height over her trunk, her bones turned until she lies on it,
and her skinning as matrices, so a shape found in the pose can be taken back to rest. What wrap.py and
bake_detail.py share.

    sys.path.insert(0, <this folder>); from pose import place, fit, posed, Skinning
"""
import numpy as np
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

# the bones the pose fit turns, and the ones not turned about their own length (a round limb fits as well twisted,
# and the twist would come back out of the unposing as a turned calf or forearm)
FIT = ["Hips", "Spine", "Spine1", "Spine2", "Neck", "Head", "LeftShoulder", "RightShoulder", "LeftArm", "RightArm",
       "LeftForeArm", "RightForeArm", "LeftHand", "RightHand", "LeftUpLeg", "RightUpLeg", "LeftLeg", "RightLeg",
       "LeftFoot", "RightFoot"]
NO_TWIST = {"Spine", "Spine1", "Spine2", "Neck", "LeftArm", "RightArm", "LeftForeArm", "RightForeArm",
            "LeftUpLeg", "RightUpLeg", "LeftLeg", "RightLeg"}
FAR = 0.08  # m: a surface further than this is not the one to fit to


# a joint, the two joints its limb runs between, and the side its slice lies on (x sign in Blender)
JOINTS = [("LeftLeg", "LeftUpLeg", "LeftFoot", 1), ("RightLeg", "RightUpLeg", "RightFoot", -1),
          ("LeftForeArm", "LeftArm", "LeftHand", 1), ("RightForeArm", "RightArm", "RightHand", -1)]


def world_points(obj, me=None):
    me = me or obj.data
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    mw = np.array(obj.matrix_world)
    return co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]


def import_tripo(path, name):
    """A Tripo body imported alone (its extras removed), transforms applied, named. Returns the mesh object."""
    scene = bpy.context.scene
    before = set(scene.objects)
    if path.endswith(".glb"):
        bpy.ops.import_scene.gltf(filepath=path)
    else:
        bpy.ops.import_scene.fbx(filepath=path)
    tripo = [o for o in scene.objects if o not in before and o.type == "MESH"][0]
    for o in scene.objects:
        if o not in before and o is not tripo:
            bpy.data.objects.remove(o)
    tm = tripo.matrix_world.copy()
    tripo.parent = None
    tripo.matrix_world = tm
    bpy.ops.object.select_all(action="DESELECT")
    tripo.select_set(True)
    bpy.context.view_layer.objects.active = tripo
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    tripo.name = name
    return tripo


def off_centre(P, J, A, B, side):
    """How far joint J stands from the centre of the limb's cross-section there: the vertices within 1 cm of J's level
    along the limb's axis A->B and within 15 cm of it, on the joint's side; the distance taken across the axis."""
    axis = (B - A) / np.linalg.norm(B - A)
    along = (P - J) @ axis
    near = (np.abs(along) < 0.01) & (np.linalg.norm(P - J, axis=1) < 0.15) & (side * P[:, 0] > 0)
    if near.sum() < 6:
        return float("nan")
    d = P[near].mean(0) - J
    d -= (d @ axis) * axis
    return float(np.linalg.norm(d))


def place(tripo, rest_world, placement=None):
    """The Tripo body (its transforms already applied) scaled to her height, its feet on her ground, its trunk over
    hers; or placed exactly as before, given a placement ({"scale", "shift"}) a wrap recorded. Returns its points,
    its BVH, a sample of its points for the pose fit's return distance, and the placement."""
    T = np.array([v.co for v in tripo.data.vertices])
    if placement is None:
        ground, height = rest_world[:, 2].min(), rest_world[:, 2].max() - rest_world[:, 2].min()
        scale = height / (T[:, 2].max() - T[:, 2].min())
        band = lambda P: P[(P[:, 2] > ground + 0.45 * height) & (P[:, 2] < ground + 0.75 * height) & (np.abs(P[:, 0]) < 0.15)]
        S = (T - [0, 0, T[:, 2].min()]) * scale + [0, 0, ground]
        shift = np.array([0.0, 0.0, ground - T[:, 2].min() * scale])
        shift[:2] = band(rest_world)[:, :2].mean(0) - band(S)[:, :2].mean(0)
        placement = {"scale": float(scale), "shift": [float(v) for v in shift]}
    T = T * placement["scale"] + np.array(placement["shift"])
    tripo.data.vertices.foreach_set("co", T.ravel())
    tripo.data.update()
    bvh = BVHTree.FromObject(tripo, bpy.context.evaluated_depsgraph_get())
    rng = np.random.default_rng(1)
    return T, bvh, T[rng.choice(len(T), min(4500, len(T)), replace=False)], placement


def posed(base):
    """Her vertices as the rig poses them (world), and her posed BVH."""
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = base.evaluated_get(dg)
    return world_points(base, ev.data), BVHTree.FromObject(base, dg)


def fit(base, rig, tripo_bvh, T_sample, start=None, refine=True, log=print):
    """Her bones turned (coordinate descent) until she lies on the Tripo body: the cost is her surface's distance to
    it and its sample's distance back to her. From `start` (a pose as fit() returns it) when given, finer steps;
    with refine False the start pose is taken as it is (she was wrapped in it). Returns (cost, pose: {bone:
    [degrees x, y, z]})."""
    n = len(base.data.vertices)
    every = np.arange(0, n, 3)

    def cost():
        co, bvh = posed(base)
        there = sum(min(h[3], FAR) ** 2 if h[0] else FAR ** 2 for h in (tripo_bvh.find_nearest(Vector(p)) for p in co[every]))
        back = sum(min(h[3], FAR) ** 2 if h[0] else FAR ** 2 for h in (bvh.find_nearest(Vector(p)) for p in T_sample))
        return there / len(every) + back / len(T_sample)

    for pb in rig.pose.bones:
        pb.rotation_mode = "XYZ"
    if start:
        for name, angles in start.items():
            rig.pose.bones[name].rotation_euler = [np.radians(a) for a in angles]
    best = cost()
    log("pose fit: start cost %.6f" % best)
    step = np.radians(2.0 if start else 8.0) if refine else 0.0
    while step > np.radians(0.5):
        improved = False
        for name in FIT:
            pb = rig.pose.bones["mixamorig:" + name]
            for axis in range(3):
                if axis == 1 and name in NO_TWIST:
                    continue
                for sign in (1, -1):
                    old = pb.rotation_euler[axis]
                    pb.rotation_euler[axis] = old + sign * step
                    c = cost()
                    if c < best - 1e-9:
                        best, improved = c, True
                        break
                    pb.rotation_euler[axis] = old
        log("  step %.2f deg: cost %.6f" % (np.degrees(step), best))
        if not improved:
            step /= 2
    pose = {pb.name: [round(float(np.degrees(a)), 1) for a in pb.rotation_euler] for pb in rig.pose.bones
            if any(abs(a) > 1e-6 for a in pb.rotation_euler)}
    return best, pose


class Skinning:
    """Her vertex weights, normalised as the armature modifier normalises them, and the matrices that take each
    vertex from world rest to world posed in the rig's current pose (linear blend), to unpose a shape found posed."""

    def __init__(self, base, rig):
        self.bones = [b.name for b in rig.data.bones]
        bi = {n: i for i, n in enumerate(self.bones)}
        gi = {g.index: g.name for g in base.vertex_groups}
        n = len(base.data.vertices)
        W = np.zeros((n, len(self.bones)))
        for v in base.data.vertices:
            for g in v.groups:
                if gi[g.group] in bi:
                    W[v.index, bi[gi[g.group]]] = g.weight
        self.W = W / np.maximum(W.sum(1, keepdims=True), 1e-9)
        self.base, self.rig = base, rig

    def weight_of(self, prefixes):
        cols = [i for i, n in enumerate(self.bones) if any(n.startswith("mixamorig:" + p) for p in prefixes)]
        return self.W[:, cols].sum(1)

    def matrices(self):
        mw = self.rig.matrix_world
        skin = np.array([np.array(mw @ self.rig.pose.bones[n].matrix @ self.rig.pose.bones[n].bone.matrix_local.inverted() @ mw.inverted())
                         for n in self.bones])
        return np.einsum("nb,bij->nij", self.W, skin)

    def unpose(self, co):
        """World posed -> world rest, through the inverse of each vertex's blended matrix."""
        Minv = np.linalg.inv(self.matrices())
        h = np.concatenate([co, np.ones((len(co), 1))], 1)
        return np.einsum("nij,nj->ni", Minv, h)[:, :3]
