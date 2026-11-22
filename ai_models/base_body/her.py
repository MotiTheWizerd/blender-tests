"""Her: MPFB's hm08 female as the recipe wears her. One place for what fit_macros, fit_face, bake_detail, bake_face
and build_body share: her at a body type's sliders and a face's, her mesh settled, her head's UV island and the
rims of its pockets.

    sys.path.insert(0, <this folder>); from her import create, settle, head_of, uv_islands
"""
import json
import os
import bpy
import numpy as np
from bl_ext.blender_org.mpfb.services.humanservice import HumanService
from bl_ext.blender_org.mpfb.services.targetservice import TargetService
from bl_ext.blender_org.mpfb.services.locationservice import LocationService

MACRO = ["weight", "muscle", "proportions", "cupsize", "firmness"]
# a body slider's target folder: the arms' and legs' by their names, the rest here
FOLDER = {"measure-bust-circ": "torso", "measure-underbust-circ": "torso", "measure-waist-circ": "torso",
          "measure-hips-circ": "torso", "torso-scale-depth": "torso", "torso-scale-horiz": "torso",
          "torso-vshape": "torso", "hip-scale-depth": "hip", "hip-scale-horiz": "hip",
          "stomach-pregnant": "stomach", "buttocks-volume": "buttocks", "breast-volume-vert": "breast",
          "head-scale-vert": "head", "head-scale-horiz": "head", "head-scale-depth": "head"}
ENDS = {"breast-volume-vert": ("down", "up")}


def targets_dir():
    return LocationService.get_mpfb_data("targets")


def folder_of(slider):
    return FOLDER.get(slider, "arms" if "arm" in slider else "legs")


def create(fit, face=None, rig="mixamo_unity", mask_helpers=True):
    """The MPFB female at the body sliders `fit` (checks/fit_<type>.json's "values": the macros and the detail
    sliders) and, given, at a face's sliders (checks/face_<name>.json, fit_face.py: its "values" and the target
    files each stands for), helpers masked, the rig added with its modifier hidden (none when rig is None).
    Returns (her, the rig)."""
    targets = targets_dir()
    macro = TargetService.get_default_macro_info_dict()
    macro.update({"gender": 0.0, "age": 0.5})
    macro["race"] = {"asian": 0.0, "caucasian": 1.0, "african": 0.0}
    macro.update({k: fit[k] for k in MACRO})
    base = HumanService.create_human(mask_helpers=mask_helpers, macro_detail_dict=macro)
    for slider, value in fit.items():
        if slider in MACRO or abs(value) < 1e-3:
            continue
        decr, incr = ENDS.get(slider, ("decr", "incr"))
        end = incr if value > 0 else decr
        folder = folder_of(slider)
        sided = os.path.exists(os.path.join(targets, folder, "l-%s-%s.target.gz" % (slider, end)))
        for side in (["l-", "r-"] if sided else [""]):
            TargetService.load_target(base, os.path.join(targets, folder, "%s%s-%s.target.gz" % (side, slider, end)),
                                      weight=abs(value))
    if face:
        for name, value in face["values"].items():
            folder = name.split("/")[0]
            for key in face["targets"][name]["pos" if value > 0 else "neg"]:
                TargetService.load_target(base, os.path.join(targets, folder, key + ".target.gz"), weight=abs(value),
                                          name="face-" + key)
    if rig is None:
        return base, None
    armature = HumanService.add_builtin_rig(base, rig)
    for m in base.modifiers:
        if m.type == "ARMATURE":
            m.show_viewport = False
    return base, armature


def apply_wrap(base, rig, name, where=None):
    """Her wrapped onto her Tripo body (wrap.py): the skin delta on her settled mesh, and every bone moved as the
    skin around it moved, so the joints keep their place in their limbs. Nothing when no wrap of that name exists.
    Returns the delta or None."""
    where = where or os.path.dirname(os.path.abspath(__file__))
    npy = os.path.join(where, "build", "wrap_%s.npy" % name)
    if not os.path.exists(npy):
        return None
    delta = np.load(npy)
    me = base.data
    assert len(delta) == len(me.vertices), "%s: the wrap is on %d vertices, she has %d" % (name, len(delta), len(me.vertices))
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    me.vertices.foreach_set("co", (co.reshape(-1, 3) + delta).ravel())
    me.update()
    moves = json.load(open(os.path.join(where, "checks", "wrap_%s.json" % name)))["bones"]
    move_bones(rig, moves)
    return delta


def move_bones(rig, moves):
    """Each bone's head and tail moved by the world vectors in moves ({bone: {"head": [x, y, z], "tail": [...]}}), in
    the rig's rest; a connected child's head is its parent's tail, moved once."""
    from mathutils import Vector
    view = bpy.context.view_layer
    was_active = view.objects.active
    view.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    R_inv = rig.matrix_world.inverted().to_3x3()
    for eb in rig.data.edit_bones:
        m = moves.get(eb.name)
        if m:
            eb.head += R_inv @ Vector(m["head"])
            eb.tail += R_inv @ Vector(m["tail"])
    bpy.ops.object.mode_set(mode="OBJECT")
    view.objects.active = was_active


def settle(base, rig=None):
    """Her mesh as she stands: shape keys and the helper mask baked in, the groups kept; an Armature modifier to
    the rig when given. Returns the mesh."""
    dg = bpy.context.evaluated_depsgraph_get()
    baked = bpy.data.meshes.new_from_object(base.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    base.shape_key_clear()
    base.modifiers.clear()
    base.data = baked
    if rig is not None:
        mod = base.modifiers.new("Armature", "ARMATURE")
        mod.object = rig
    bpy.context.view_layer.update()
    return baked


def weight_of(base, me, prefix):
    """Each vertex's weight to the groups whose names start with prefix."""
    gi = {g.index: g.name for g in base.vertex_groups}
    return np.array([sum(g.weight for g in v.groups if gi[g.group].startswith(prefix)) for v in me.vertices])


def body_of(base, me):
    """Which vertices are body (not helpers), by the mask modifier's group; all of them when she is settled."""
    masks = [m for m in base.modifiers if m.type == "MASK"]
    if not masks:
        return np.ones(len(me.vertices), dtype=bool)
    group = base.vertex_groups[masks[0].vertex_group].index
    grouped = np.array([any(g.group == group for g in v.groups) for v in me.vertices])
    return ~grouped if masks[0].invert_vertex_group else grouped


def uv_islands(me):
    """The mesh's UV islands: [(loop indices, vertex indices)], largest first. Loops of one vertex at one UV
    coordinate are one place; a face's loops are one island."""
    uv = np.empty(len(me.loops) * 2)
    me.uv_layers[0].data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    lv = np.empty(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", lv)
    parent = np.arange(len(me.loops))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    seen = {}
    for i in range(len(me.loops)):
        k = (int(lv[i]), round(float(uv[i, 0]), 5), round(float(uv[i, 1]), 5))
        if k in seen:
            parent[root(i)] = root(seen[k])
        else:
            seen[k] = i
    for p in me.polygons:
        s = p.loop_start
        for a in range(s + 1, s + p.loop_total):
            ra, rb = root(s), root(a)
            if ra != rb:
                parent[ra] = rb
    roots = np.array([root(i) for i in range(len(me.loops))])
    out = []
    for r in np.unique(roots):
        loops = np.where(roots == r)[0]
        out.append((loops, np.unique(lv[loops])))
    out.sort(key=lambda lv_: -len(lv_[0]))
    return out


class Head:
    """Her head on the mesh: its skin's UV island (loops, vertices), the eye cups and the mouth pocket (islands of
    their own on a closed mesh) and the rims they share with the skin: eyes (left then right) and the lip line."""

    def __init__(self, base, me):
        body = body_of(base, me)
        head_w = weight_of(base, me, "mixamorig:Head")
        P = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", P)
        P = P.reshape(-1, 3)
        head = [(l, v) for l, v in uv_islands(me) if body[v].all() and (head_w[v] > 0.5).mean() > 0.9]
        self.loops, self.skin = head[0]
        self.pockets = [(l, v) for l, v in head[1:] if 100 < len(v) < 1000]
        skin = set(self.skin.tolist())
        rims = [np.array(sorted(skin & set(v.tolist()))) for _, v in self.pockets]
        middle = P[self.skin, 2].mean()
        self.eyes = sorted([r for r in rims if P[r, 2].mean() > middle], key=lambda r: P[r, 0].mean())
        self.mouth = next(r for r in rims if P[r, 2].mean() <= middle)
        self.faces = np.unique(np.repeat(np.arange(len(me.polygons)), [p.loop_total for p in me.polygons])[self.loops])


def head_uv_fit(me, head, margin=0.01):
    """The transform that fills the UV square with the head's skin island: (scale, offset); new = old * scale
    + offset. Uniform, the island centred."""
    uv = np.empty(len(me.loops) * 2)
    me.uv_layers[0].data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)[head.loops]
    lo, hi = uv.min(0), uv.max(0)
    scale = (1 - 2 * margin) / (hi - lo).max()
    offset = 0.5 - (lo + hi) / 2 * scale
    return float(scale), offset.tolist()
