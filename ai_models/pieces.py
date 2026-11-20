"""The step after Mixamo for a replaceable body: its rigged mesh cut into the pieces equipment replaces, as Skyrim's.

    blender -b --factory-startup -P pieces.py -- body_warrior_m

Reads <name>/source_mixamo.fbx (Mixamo's download, with skin; private, as the Tripo source is), the AI's colour map
(the reduced mesh kept its UVs) and reduce's baked normal map. Cuts the mesh into four pieces on the one skeleton:

  Body    torso, arms and legs       replaced by a cuirass, a robe, clothes
  Head    above the neck seam        replaced by the face editor's head (and a full helm)
  Hands   past the wrist seams       replaced by gauntlets, gloves
  Feet    below the ankle seams      replaced by boots

Inside Body, LINES mark where a fight can cut a limb off (the middle of each upper arm and each thigh): Body is split
along them and each vertex says its part (SEGMENTS) in the UV layer "Segment" (u), so Forge can hide a limb and drop
a copy of it; lines, not pieces, so armour over one stays one piece. A line is cut as a seam is and measured as one.

A seam is a plane square to a bone, through a point part way along it (SEAMS), found from the rig, so every body
Mixamo rigs is cut at the same places. The plane cuts only the limb it crosses near that point (faces within REACH
whose vertices the limb's bones weigh most), so a wrist's plane never slices the thigh beside the hand; the piece is
what is reached from the limb's end (the crown, a fingertip, a toe) without crossing the cut. A cut that leaves a gap
would let that reach run into the rest of the body; it is refused.

The two sides of a seam keep the same vertices: the same place, the same weights (a cut's new vertex is weighed
between its edge's ends) and the same normal (each piece's custom normals are the whole body's smooth ones), so no
line shows where they meet. checks/pieces.json says so in numbers, measured on the pieces and again on the exported
FBX read back: for each seam's two sides, how many vertices, how far apart (mm) and how far their normals turn (deg).

The head is a piece any of the body's heads replaces: the body's own (its Head piece as cut) and each face editor head
model.json names, seated on the neck seam (neck.py). Each is exported on its own, on the same skeleton, for Forge to
put on the body by its bones' names.

Writes build/forge/<Title>/: <Title>.fbx (the meshes "Body", "Hands", "Feet" bound to the skeleton; no clip),
<Title>_Color.png and <Title>_Normal.png (TEXTURE px); Heads/<Head>.fbx for each head (the skeleton and one mesh,
"Head": the body's own is Heads/<Title>.fbx and draws the body's maps; a face editor head's collar draws them too, its
material slot 0, and the rest its own maps, slot 1: Heads/<Head>_Color.png and _Normal.png), for Forge's
Content/Characters/<Title>; and checks/pieces_front.jpg, pieces_back.jpg, pieces_side.jpg (each piece its own colour,
from the FBX read back), segments_front.jpg and segments_back.jpg (each of Body's parts its own colour), and for each head whole_front_<Head>.jpg and neck_<view>_<Head>.jpg (in its colours).
"""
import bmesh, bpy, json, math, os, shutil, sys
import numpy as np
from collections import deque
from mathutils import Vector
from mathutils.kdtree import KDTree

ARGS = sys.argv[sys.argv.index("--") + 1:]
NAME = ARGS[0]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eyes import sphere_fit
from place import Creature, pictures_as_jpeg
C = Creature(NAME)
Title = C.title
# Mixamo's download, or for a model Tripo rigged (model.json "rig": "tripo") tripo_rig.py's, on the same skeleton.
SOURCE = C.build(f"{NAME}_rigged.fbx") if C.spec.get("rig") == "tripo" else os.path.join(C.root, "source_mixamo.fbx")
# model.json "heads" (optional): the head_* models (head.py's) seated on the neck seam (neck.py), each a Head piece
# beside the body's own, at "head_size" times the body's own head (chin to crown; 1: the same). "--head-size S" tries
# another size: its pictures and numbers are tagged with it, and its export goes to build/forge_<tag>/, leaving the
# real one alone.
HEADS = C.spec.get("heads", [])
HEAD_SIZE = float(ARGS[ARGS.index("--head-size") + 1]) if "--head-size" in ARGS else C.spec.get("head_size", 1.0)
# model.json "skin_even" (optional, 0 to 1): how much of the large dark and light patches the AI painted into the
# body's skin (baked shading, grime) is evened out; its pores and creases stay. 0: as made.
SKIN_EVEN = C.spec.get("skin_even", 0.0)
TAG = f"_size{HEAD_SIZE:g}" if "--head-size" in ARGS else ""
OUT = C.build("forge" + TAG, Title)
TEXTURE = 4096
REACH = 0.15          # metres from a seam's point: how far its plane may cut
ON_PLANE = 1e-4       # a vertex this near a seam's plane is on it (0.1 mm), so the cut leaves no slivers
HOLE_SIDES = 24       # the AI's holes closed before the cut: up to this many edges round
PIECES = ("Body", "Head", "Hands", "Feet")    # Body first: what no seam takes

# A seam: its name, the bone it crosses (from, to, how far along), whether a bone (its name less the rig's prefix) is
# of the limb it cuts, the piece past it, and the bone at the limb's end the piece is reached from.
# model.json "neck_along" (optional): how far up the Neck bone the neck seam lies, 0.4 unless a rig puts its Head bone
# nearer the chin (Tripo's on body_warrior_f: at 0.4 the seam lay under her jaw, too near for a head's neck to blend).
SEAMS = [("neck", "Neck", "Head", C.spec.get("neck_along", 0.4),
          lambda b: b in ("Neck", "Head", "HeadTop_End", "LeftEye", "RightEye", "Spine2", "LeftShoulder", "RightShoulder"),
          "Head", "HeadTop_End")]
for side in ("Left", "Right"):
    SEAMS.append((f"wrist.{side[0]}", f"{side}ForeArm", f"{side}Hand", 0.8,
                  lambda b, s=side: b == f"{s}ForeArm" or b.startswith(f"{s}Hand"), "Hands", f"{side}HandMiddle4"))
    SEAMS.append((f"ankle.{side[0]}", f"{side}Leg", f"{side}Foot", 0.8,
                  lambda b, s=side: b in (f"{s}Leg", f"{s}Foot", f"{s}ToeBase", f"{s}Toe_End"), "Feet", f"{side}Toe_End"))
# A line where a fight can cut a limb off: inside the Body piece, not a piece of its own, so armour that covers it is
# still one piece, cut on the same line. The Body's vertices are split along it (both sides the same place, weights
# and normal, as a seam's) and each says which part of the body it is (SEGMENTS, in the UV layer "Segment", u), so
# Forge can hide a limb and drop a copy of it; the hand or foot past it goes with it. Fields as a seam's, the part past
# it in place of the piece.
SEGMENTS = ("Torso", "ArmL", "ArmR", "LegL", "LegR")
LINES = []
for side in ("Left", "Right"):
    LINES.append((f"arm.{side[0]}", f"{side}Arm", f"{side}ForeArm", 0.5,
                  lambda b, s=side: b in (f"{s}Arm", f"{s}ForeArm"), f"Arm{side[0]}", f"{side}HandMiddle4"))
    LINES.append((f"thigh.{side[0]}", f"{side}UpLeg", f"{side}Leg", 0.5,
                  lambda b, s=side: b in (f"{s}UpLeg", f"{s}Leg"), f"Leg{side[0]}", f"{side}Toe_End"))

HEADS_OUT = os.path.join(OUT, "Heads")
os.makedirs(HEADS_OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=SOURCE)
scene = bpy.context.scene
rig = next(o for o in scene.objects if o.type == "ARMATURE")
body = next(o for o in scene.objects if o.type == "MESH")
for action in list(bpy.data.actions):           # Mixamo's two-frame "clip": the skeleton stands in its rest pose
    bpy.data.actions.remove(action)
rig.animation_data_clear()
prefix = next(b.name for b in rig.data.bones if b.name.endswith("Hips"))[:-len("Hips")]   # "mixamorig:"
to_mesh = body.matrix_world.inverted()


def joint(bone):
    """A bone's head, in the mesh's frame."""
    return to_mesh @ (rig.matrix_world @ rig.data.bones[prefix + bone].head_local)


me = body.data
bm = bmesh.new(); bm.from_mesh(me)
deform = bm.verts.layers.deform.active
# The AI's small holes (an ear's fold, the mouth, specks the reduce left) closed first: a piece's only open edge is
# then its seam, and nothing shows through. A hole is HOLE_SIDES edges at most; the new faces take existing vertices,
# so their weights are the body's.
open_before = sum(1 for e in bm.edges if e.is_boundary)
closed = bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=HOLE_SIDES)["faces"]
for f in closed:
    f.smooth = True
group_bone = {g.index: g.name[len(prefix):] if g.name.startswith(prefix) else g.name for g in body.vertex_groups}
cut_at = bm.verts.layers.int.new("seam")       # the seam a vertex lies on, 1-based; 0 for none

# Tripo's auto-rig lets the shoulders (the clavicles) hold the throat and the jaw: on body_warrior_f up to 0.08 of some
# 600 jaw vertices a side, where Mixamo's rig gives the jaw none, so an arm raised (the bow's) dragged that side of
# every woman's face and its skin with it (Moti, s1022: "right stretch/deform" on all the women, not the men). Above
# the neck seam only the neck and the head move the skin (every head takes its weights from here, neck.py); below it
# the limbs' hold fades in over NECK_CLEAR, what they held going to the neck; and only near the neck's axis (wholly
# within NECK_REACH of it, fading out to NECK_REACH + NECK_FADE), so the shoulders' tops beside it keep their
# clavicles' hold and nothing steps where the clearing ends.
NECK_CLEAR = 0.06
NECK_REACH = 0.06
NECK_FADE = 0.04
LIMB_BONES = {f"{side}{bone}" for side in ("Left", "Right") for bone in ("Shoulder", "Arm", "ForeArm", "Hand")}


def smoothstep(x):
    t = min(max(x, 0.0), 1.0)
    return t * t * (3 - 2 * t)


_seam, _a, _b, _along = SEAMS[0][:4]
clear_point = joint(_a).lerp(joint(_b), _along)
clear_normal = (joint(_b) - joint(_a)).normalized()
neck_group = body.vertex_groups[prefix + "Neck"].index
neck_clear = {"clear_cm": NECK_CLEAR * 100, "reach_cm": NECK_REACH * 100, "fade_cm": NECK_FADE * 100, "vertices": 0,
              "weight_moved": 0.0, "weight_moved_max": 0.0}
for v in bm.verts:
    above = (v.co - clear_point).dot(clear_normal)
    lateral = ((v.co - clear_point) - above * clear_normal).length
    if above < -NECK_CLEAR or lateral > NECK_REACH + NECK_FADE:
        continue
    # The limbs' whole hold NECK_CLEAR below the seam and past the neck's reach; none at and above the seam on the neck.
    keep = 1 - (1 - smoothstep(-above / NECK_CLEAR)) * (1 - smoothstep((lateral - NECK_REACH) / NECK_FADE))
    moved = 0.0
    for g, w in list(v[deform].items()):
        if group_bone.get(g) in LIMB_BONES:
            moved += w * (1 - keep)
            if keep > 0:
                v[deform][g] = w * keep
            else:
                del v[deform][g]
    if moved > 0:
        v[deform][neck_group] = v[deform].get(neck_group, 0.0) + moved
        neck_clear["vertices"] += 1
        neck_clear["weight_moved"] += moved
        neck_clear["weight_moved_max"] = max(neck_clear["weight_moved_max"], moved)
neck_clear["weight_moved"] = round(neck_clear["weight_moved"], 2)
neck_clear["weight_moved_max"] = round(neck_clear["weight_moved_max"], 3)

# model.json "neck_width_cm" (optional): how wide the body's neck is across at the join, NECK_FIT_ABOVE above the seam,
# the heads' own necks' width (body_warrior_f, s1022: the body's 13.3 cm against her heads' 10.7 to 11.7, and the 3.3 cm
# blend stretched every head's neck out to it: Moti, "the body neck part is too big and the woman's neck is small").
# The neck is scaled across (about its axis) to that width: wholly between NECK_FIT_FROM below the seam and
# NECK_FIT_ABOVE above it, fading in from the collarbones (NECK_FIT_FADE) and out under the jaw; vertices past
# NECK_FIT_REACH of the axis (the shoulders) are left alone.
NECK_WIDTH = C.spec.get("neck_width_cm")
# The body's own head's landmarks (crown, chin, nose, chin front: face.profile), taken before the neck is shaped, for
# every head's seat (neck.seat): the chin finder reads the profile's fall-back to the neck, which a thinner neck moves.
from face import profile
BODY_PROFILE = profile(np.array([v.co[:] for v in bm.verts if (v.co - clear_point).dot(clear_normal) > -0.02]))
NECK_FIT_ABOVE = 0.035
NECK_FIT_FROM = -0.03
NECK_FIT_FADE = 0.04         # in from the collarbones
NECK_FIT_FADE_OUT = 0.025    # out under the jaw (the chin stands 7 cm above the seam: untouched, or neck.py's limit moves)
NECK_FIT_REACH = 0.12
neck_fit = None
if NECK_WIDTH:
    band = [v for v in bm.verts if NECK_FIT_ABOVE - 0.005 <= (v.co - clear_point).dot(clear_normal) <= NECK_FIT_ABOVE + 0.005
            and ((v.co - clear_point) - (v.co - clear_point).dot(clear_normal) * clear_normal).length < NECK_FIT_REACH]
    side = Vector((1.0, 0.0, 0.0))
    across = [v.co.dot(side) for v in band]
    was = max(across) - min(across)
    factor = NECK_WIDTH / 100 / was
    axis_point = sum((v.co for v in band), Vector()) / len(band)
    neck_fit = {"width_was_cm": round(was * 100, 2), "width_cm": NECK_WIDTH, "factor": round(factor, 4), "vertices": 0,
                "moved_mm_max": 0.0}
    for v in bm.verts:
        above = (v.co - clear_point).dot(clear_normal)
        if above < NECK_FIT_FROM - NECK_FIT_FADE or above > NECK_FIT_ABOVE + NECK_FIT_FADE_OUT:
            continue
        radial = (v.co - axis_point) - (v.co - axis_point).dot(clear_normal) * clear_normal
        if radial.length > NECK_FIT_REACH:
            continue
        hold = smoothstep((above - (NECK_FIT_FROM - NECK_FIT_FADE)) / NECK_FIT_FADE) * smoothstep((NECK_FIT_ABOVE + NECK_FIT_FADE_OUT - above) / NECK_FIT_FADE_OUT)
        move = radial * ((factor - 1) * hold)
        if move.length > 0:
            v.co += move
            neck_fit["vertices"] += 1
            neck_fit["moved_mm_max"] = max(neck_fit["moved_mm_max"], round(move.length * 1000, 2))


def heaviest(v):
    weights = v[deform]
    return group_bone.get(max(weights.items(), key=lambda kv: kv[1])[0]) if len(weights) else None


report = {"source": os.path.basename(SOURCE), "triangles_source": len(bm.faces) - len(closed),
          "open_edges_source": open_before, "holes_closed": len(closed),
          "open_edges_left": sum(1 for e in bm.edges if e.is_boundary), "neck_clear": neck_clear, "neck_fit": neck_fit,
          "seams": {}, "lines": {}}
planes = []
for i, (seam, a, b, along, of_limb, piece, end) in enumerate(SEAMS + LINES):
    point = joint(a).lerp(joint(b), along)
    normal = (joint(b) - joint(a)).normalized()     # pointing past the seam, into the piece
    planes.append((point, normal))
    near = [f for f in bm.faces if (f.calc_center_median() - point).length < REACH
            and any(of_limb(heaviest(v) or "") for v in f.verts)]
    edges = {e for f in near for e in f.edges}
    verts = {v for f in near for v in f.verts}
    cut = bmesh.ops.bisect_plane(bm, geom=near + list(edges) + list(verts), dist=ON_PLANE, plane_co=point,
                                 plane_no=normal)["geom_cut"]
    ring = [g for g in cut if isinstance(g, bmesh.types.BMVert)]
    for v in ring:
        v[cut_at] = i + 1
    report["seams" if i < len(SEAMS) else "lines"][seam] = {
        "bone": f"{a} -> {b} at {along}", "point_m": [round(c, 3) for c in point], "faces_cut": len(near),
        "ring_vertices": len(ring)}
# A cut face is a triangle and a quad: triangles all, as the rest are.
bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])

# Each piece is what its limb's end reaches without crossing its seam's cut. Faces touching at a vertex reach each
# other (the AI joins an ear's fold to the head at a point), unless that vertex is on the cut: the seam's other side.
piece_of = bm.faces.layers.int.new("piece")
bm.verts.ensure_lookup_table()
tree = KDTree(len(bm.verts))
for v in bm.verts:
    tree.insert(v.co, v.index)
tree.balance()
hips_faces = set(bm.verts[tree.find(joint("Hips"))[1]].link_faces)


def spread(start, through):
    """The faces reached from start, from face to face over their vertices while through(vertex)."""
    reached, todo = set(start), deque(start)
    while todo:
        for v in todo.popleft().verts:
            if through(v):
                for g in v.link_faces:
                    if g not in reached:
                        reached.add(g); todo.append(g)
    return reached


for i, (seam, a, b, along, of_limb, piece, end) in enumerate(SEAMS):
    seed = bm.verts[tree.find(joint(end))[1]]
    reached = spread(seed.link_faces, lambda v, i=i: v[cut_at] != i + 1)
    if reached & hips_faces or len(reached) > len(bm.faces) // 4:
        raise SystemExit(f"PIECES the {seam} cut leaves a gap: {piece} reached {len(reached)} of {len(bm.faces)} faces")
    for f in reached:
        if f[piece_of]:
            raise SystemExit(f"PIECES {piece} ({seam}) runs into {PIECES[f[piece_of]]}")
        f[piece_of] = PIECES.index(piece)
    report["seams"][seam]["piece_faces"] = len(reached)

# Each limb's part is what its end reaches without crossing its line (over the wrist or ankle seam: the hand or foot
# goes with it); the rest is the torso.
segment_of = bm.faces.layers.int.new("segment")
for j, (line, a, b, along, of_limb, segment, end) in enumerate(LINES):
    i = len(SEAMS) + j
    seed = bm.verts[tree.find(joint(end))[1]]
    reached = spread(seed.link_faces, lambda v, i=i: v[cut_at] != i + 1)
    if reached & hips_faces or len(reached) > len(bm.faces) // 4:
        raise SystemExit(f"PIECES the {line} cut leaves a gap: {segment} reached {len(reached)} of {len(bm.faces)} faces")
    for f in reached:
        if f[segment_of]:
            raise SystemExit(f"PIECES {segment} ({line}) runs into {SEGMENTS[f[segment_of]]}")
        f[segment_of] = SEGMENTS.index(segment)
    report["lines"][line]["segment_faces"] = len(reached)

# What is left loose of the body (a bit of the AI's mesh joined to nothing) goes with the piece past whose seam it
# lies (the nearest, within REACH twice), else stays with the body.
rest = {f for f in bm.faces if not f[piece_of]}
main = spread(hips_faces & rest, lambda v: True) & rest
loose, rest = [], rest - main
while rest:
    island = spread([next(iter(rest))], lambda v: True) & rest
    rest -= island
    centre = sum((f.calc_center_median() for f in island), Vector()) / len(island)
    past = [(i, (centre - planes[i][0]).length) for i in range(len(SEAMS))
            if (centre - planes[i][0]).dot(planes[i][1]) > 0 and (centre - planes[i][0]).length < 2 * REACH]
    if past:
        seam = min(past, key=lambda p: p[1])[0]
        for f in island:
            f[piece_of] = PIECES.index(SEAMS[seam][5])
    loose.append({"faces": len(island), "centre_m": [round(c, 3) for c in centre],
                  "to": SEAMS[min(past, key=lambda p: p[1])[0]][5] if past else "Body"})
report["loose"] = loose

bm.verts.index_update()
whole_index = bm.verts.layers.int.new("whole")
for v in bm.verts:
    v[whole_index] = v.index
bm.to_mesh(me); bm.free()
# model.json "torso" (optional): a torso_* model (Tripo's, made alone at a higher detail) laid onto the Body's torso
# part, drawing maps of its own (torso.py); before the normals, so they are the new shape's.
TORSO = C.spec.get("torso")
torso_fade = None
if TORSO:
    from torso import graft
    report["torso"], torso_maps, torso_fade = graft(body, os.path.join(os.path.dirname(C.root), TORSO), TORSO, Title,
                                                    PIECES.index("Body"), SEGMENTS.index("Torso"))
# model.json "chests" (optional): chest_* models (Tripo's, from a picture of a woman's chest), each laid onto a copy of
# the body as one of its body types (chest.py, below), its breasts grown by the chest's model.json "size" (1: as the
# picture). The copies are taken after the torso and before the breasts are weighed, so every type keeps the body's
# skeleton and weighs its own breasts to the body's breast bones (Forge's SoftTissue only moves those bones, so where
# they rest does not matter to a type). Exported as Bodies/<Chest>.fbx beside the body's own Body as Bodies/<Title>.fbx,
# for Forge to switch.
CHESTS = C.spec.get("chests", [])
COLOUR_REACH = 30     # a chest's colour field smoothed over this many steps of the mesh's edges (about 6 cm on her)
BODIES_OUT = os.path.join(OUT, "Bodies")
chest_copies = {}
for chest_name in CHESTS:
    copy = body.copy(); copy.data = me.copy()
    for collection in body.users_collection:
        collection.objects.link(copy)
    chest_copies[chest_name] = copy
# model.json "breasts" (optional): a bone for each, weighed on the Body's torso part (breasts.py), for Forge to spring.
if C.spec.get("breasts"):
    from breasts import add as add_breasts, weigh as weigh_breasts
    face_piece = me.attributes["piece"].data
    face_segment = me.attributes["segment"].data
    trunk_verts = {v for k, p in enumerate(me.polygons)
                   if face_piece[k].value == PIECES.index("Body") and face_segment[k].value == SEGMENTS.index("Torso")
                   for v in p.vertices}
    report["breasts"] = add_breasts(body, rig, prefix, trunk_verts.__contains__)
chest_bodies = {}
if CHESTS:
    from chest import lay
    for chest_name, copy in chest_copies.items():
        chest_title = "".join(part.capitalize() for part in chest_name.split("_"))
        chest_size = float(Creature(chest_name).spec.get("size", 1.0))
        chest_report, chest_maps, chest_fade = lay(copy, os.path.join(os.path.dirname(C.root), chest_name), chest_name,
                                                   chest_title, PIECES.index("Body"), SEGMENTS.index("Torso"), chest_size)
        if C.spec.get("breasts"):
            chest_report["breasts"] = weigh_breasts(copy, prefix, trunk_verts.__contains__, report["breasts"]["wall_m"])
        report.setdefault("chests", {})[chest_title] = chest_report
        chest_bodies[chest_title] = (copy, chest_maps, chest_fade)
me.shade_smooth()
me.update()
whole_normals = [v.normal.copy() for v in me.vertices]   # across every seam: both sides' faces


def cut(source, k, name, normals):
    """Piece k of source (the cut body or a body type's copy of it): its own faces, on the same skeleton with the same
    weights, its normals the whole body's (normals: per whole vertex), Body split along the lines."""
    ob = source.copy(); ob.data = source.data.copy()
    ob.name = ob.data.name = name
    for collection in source.users_collection:
        collection.objects.link(ob)
    pbm = bmesh.new(); pbm.from_mesh(ob.data)
    layer = pbm.faces.layers.int["piece"]
    bmesh.ops.delete(pbm, geom=[f for f in pbm.faces if f[layer] != k], context="FACES_ONLY")
    bmesh.ops.delete(pbm, geom=[v for v in pbm.verts if not v.link_faces], context="VERTS")
    if PIECES[k] == "Body":
        # Apart along the lines (each new vertex a copy: the same place, weights and whole vertex, so the same
        # normal), each corner saying its part.
        segment = pbm.faces.layers.int["segment"]
        bmesh.ops.split_edges(pbm, edges=[e for e in pbm.edges if len(e.link_faces) == 2
                                          and e.link_faces[0][segment] != e.link_faces[1][segment]])
        uv = pbm.loops.layers.uv.new("Segment")
        for f in pbm.faces:
            for loop in f.loops:
                loop[uv].uv = (f[segment], 0.0)
    pbm.to_mesh(ob.data); pbm.free()
    whole = ob.data.attributes["whole"].data
    ob.data.normals_split_custom_set_from_vertices([normals[whole[j].value] for j in range(len(ob.data.vertices))])
    for attribute in ("whole", "piece", "seam", "segment"):
        if attribute in ob.data.attributes:
            ob.data.attributes.remove(ob.data.attributes[attribute])
    return ob


# The pieces: copies of the cut body, each keeping its own faces.
pieces = [cut(body, k, name, whole_normals) for k, name in enumerate(PIECES)]
# Each body type's Body, its normals its own shape's.
chest_pieces = {}
for chest_title, (copy, _, _) in chest_bodies.items():
    copy.data.shade_smooth()
    copy.data.update()
    chest_pieces[chest_title] = cut(copy, PIECES.index("Body"), f"Body {chest_title}",
                                    [v.normal.copy() for v in copy.data.vertices])
    bpy.data.objects.remove(copy, do_unlink=True)
world_planes = [(body.matrix_world @ p, (body.matrix_world.to_3x3() @ n).normalized()) for p, n in planes]
bpy.data.objects.remove(body, do_unlink=True)

# The heads, by title: the body's own Head piece, and each face editor head seated on the neck seam beside it (neck.py),
# its own faces drawing its own maps (painted below: `seated`, its export's folder and the fade's triangles).
own_head = next(p for p in pieces if p.name == "Head")
heads, seated = {Title: own_head}, {}
for head_name in HEADS:
    from glob import glob
    from neck import seat
    made = glob(os.path.join(os.path.dirname(C.root), head_name, "build", "forge", "*", "*.fbx"))
    if len(made) != 1:
        raise SystemExit(f"PIECES the head {head_name} has {len(made)} exports (run head.py)")
    head_title = os.path.basename(os.path.dirname(made[0]))
    if head_title in heads:
        raise SystemExit(f"PIECES two heads are called {head_title}")
    # The head's own model.json may say how far up its neck is laid onto the body's ("neck_blend_cm"; neck.py BLEND).
    head_spec_path = os.path.join(os.path.dirname(C.root), head_name, "model.json")
    head_spec = json.load(open(head_spec_path)) if os.path.exists(head_spec_path) else {}
    heads[head_title], placed = seat(made[0], own_head, *world_planes[0], material=head_title, size=HEAD_SIZE,
                                     body_profile=BODY_PROFILE,
                                     **({"blend": head_spec["neck_blend_cm"] / 100} if "neck_blend_cm" in head_spec else {}))
    seated[head_title] = (os.path.dirname(made[0]), placed.pop("fade_triangles"))
    report.setdefault("heads", {})[head_title] = dict(
        placed, source=os.path.relpath(made[0], os.path.dirname(C.root)).replace(os.sep, "/"),
        fade_triangles=len(seated[head_title][1]))
body_pieces = {p.name: p for p in pieces if p is not own_head}


def seam_match(named):
    """Each seam's two sides (its piece's open edge on the plane against the Body's), for the pieces by name (Body,
    Head, Hands, Feet): how many vertices each, how far apart at most (mm), how far their normals turn at most
    (degrees); and each piece's open edges on no seam."""
    rims, parts = {}, {}
    for name, ob in named.items():
        mesh = ob.data
        b = bmesh.new(); b.from_mesh(mesh)
        rim = {v.index for e in b.edges if e.is_boundary for v in e.verts}
        b.free()
        normals = {i: Vector() for i in rim}
        for loop, corner in zip(mesh.loops, mesh.corner_normals):
            if loop.vertex_index in normals:
                normals[loop.vertex_index] += corner.vector
        world = ob.matrix_world
        rims[name] = [(world @ mesh.vertices[i].co, (world.to_3x3() @ n).normalized()) for i, n in normals.items()]
        if "Segment" in mesh.uv_layers:
            part = {loop.vertex_index: round(d.uv[0]) for loop, d in zip(mesh.loops, mesh.uv_layers["Segment"].data)}
            for k, segment in enumerate(SEGMENTS):
                parts[segment] = [r for i, r in zip(normals, rims[name]) if part[i] == k]

    def on(seam, rim):
        point, normal = world_planes[seam]
        return [(co, n) for co, n in rim if abs((co - point).dot(normal)) < 10 * ON_PLANE and (co - point).length < REACH]

    def against(inside, outside):
        tree = KDTree(max(len(outside), 1))
        for j, (co, _) in enumerate(outside):
            tree.insert(co, j)
        tree.balance()
        far = turn = 0.0
        for co, n in inside:
            _, j, distance = tree.find(co)
            far = max(far, distance)
            turn = max(turn, math.degrees(n.angle(outside[j][1], 0.0)))
        return {"apart_mm": round(far * 1000, 4), "turn_deg": round(turn, 3)}

    result = {}
    for i, (seam, *_, piece, end) in enumerate(SEAMS):
        inside, outside = on(i, rims[piece]), on(i, rims["Body"])
        result[seam] = {piece: len(inside), "Body": len(outside), **against(inside, outside)}
    for j, (line, *_, segment, end) in enumerate(LINES):
        i = len(SEAMS) + j
        inside, outside = on(i, parts.get(segment, [])), on(i, parts.get("Torso", []))
        result[line] = {segment: len(inside), "Torso": len(outside), **against(inside, outside)}
    result["open_edge_vertices_on_no_seam"] = {
        name: sum(1 for co, n in rim if not any(on(i, [(co, n)]) for i in range(len(SEAMS) + len(LINES))))
        for name, rim in rims.items()}
    return result


def neck_of(match):
    """The neck seam's numbers out of a seam_match, and the head's open edges on no seam (0: its only edge is the seam)."""
    return dict(match["neck"], head_open_edge_vertices_on_no_seam=match["open_edge_vertices_on_no_seam"]["Head"])


report["seams_on_pieces"] = seam_match(dict(body_pieces, Head=own_head))
for head_title in seated:
    report["heads"][head_title]["neck_on_pieces"] = neck_of(seam_match(dict(body_pieces, Head=heads[head_title])))
report["triangles"] = dict({name: len(ob.data.polygons) for name, ob in body_pieces.items()},
                           heads={title: len(ob.data.polygons) for title, ob in heads.items()})

# The maps, as Forge's characters take them: the AI's colour (the reduced mesh kept its UVs) and reduce's normal bake;
# each face editor head's own (head.py's), its skin matched to the body's.
def pixels(path):
    image = bpy.data.images.load(path)
    if image.size[0] != TEXTURE:
        image.scale(TEXTURE, TEXTURE)
    array = np.empty(TEXTURE * TEXTURE * 4, dtype=np.float32)
    image.pixels.foreach_get(array)
    bpy.data.images.remove(image)
    return array.reshape(TEXTURE, TEXTURE, 4)


def save(array, path, space):
    image = bpy.data.images.new(os.path.basename(path), array.shape[1], array.shape[0], alpha=False)
    image.colorspace_settings.name = space
    image.pixels.foreach_set(array.ravel())
    image.filepath_raw = path
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)


def linear(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def encoded(c):
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def paint(target, triangles, under_at):
    """Over each triangle of the fade, in target (the head's map): what lies under it (under_at, from the body's UVs)
    mixed under the head's own by how much of the head's shows there, so the head's skin comes out of the body's."""
    size = np.array([target.shape[1] - 1, target.shape[0] - 1])
    for head_uv, body_uv, shows in triangles:
        p = np.array(head_uv) * size
        lo = np.maximum(np.floor(p.min(0)).astype(int) - 1, 0)
        hi = np.minimum(np.ceil(p.max(0)).astype(int) + 1, size)
        xs, ys = np.meshgrid(np.arange(lo[0], hi[0] + 1), np.arange(lo[1], hi[1] + 1))
        e1, e2 = p[1] - p[0], p[2] - p[0]
        det = e1[0] * e2[1] - e1[1] * e2[0]
        if abs(det) < 1e-9:
            continue
        dx, dy = xs - p[0][0], ys - p[0][1]
        b1, b2 = (dx * e2[1] - dy * e2[0]) / det, (e1[0] * dy - e1[1] * dx) / det
        b0 = 1 - b1 - b2
        slack = 1.0 / max(np.linalg.norm(e1), np.linalg.norm(e2), 1.0)     # about a pixel past each edge
        inside = (b0 >= -slack) & (b1 >= -slack) & (b2 >= -slack)
        if not inside.any():
            continue
        w = np.stack([b0[inside], b1[inside], b2[inside]], 1).clip(0, None)
        w /= w.sum(1, keepdims=True)
        t = (w @ np.array(shows))[:, None]
        yi, xi = ys[inside], xs[inside]
        target[yi, xi, :3] = under_at(w @ np.array(body_uv)) * (1 - t) + target[yi, xi, :3] * t


def skin_of(array):
    """Where a colour map is skin: warm (red over blue), not the black between its islands, the grey of cloth, the
    whites and blues of eyes, or the glare some maps pad their islands with."""
    r, g, b = array[..., 0], array[..., 1], array[..., 2]
    return (r > 0.15) & (r - b > 0.06) & (r >= g) & (0.2126 * r + 0.7152 * g + 0.0722 * b < 0.92)


def box(x, r):
    """Each place's sum over the square 2r + 1 round it (zero past the edges)."""
    n = 2 * r + 1
    c = np.pad(x, ((r + 1, r), (r + 1, r))).cumsum(0).cumsum(1)
    return c[n:, n:] - c[:-n, n:] - c[n:, :-n] + c[:-n, :-n]


def even(array, strength, step=4, reach=12):
    """The skin of a colour map with its large dark and light patches evened out by strength (0 none, 1 flat): each
    skin pixel's brightness against its neighbourhood's (reach pixels of a map step times smaller round it: about 1%
    of the map, skin only), moved toward the skin's middle brightness. Pores and creases, finer than that, stay."""
    mask = skin_of(array)
    lum = linear(array[..., :3]) @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    h, w = mask.shape
    coarse = lambda x: x.reshape(h // step, step, w // step, step).mean((1, 3))
    around = box(coarse(lum * mask), reach) / np.maximum(box(coarse(mask.astype(np.float32)), reach), 1e-6)
    around = np.repeat(np.repeat(around, step, 0), step, 1)
    factor = np.clip((np.median(lum[mask]) / np.maximum(around, 1e-4)) ** strength, 0.6, 1.6)
    colour = linear(array[..., :3])
    colour[mask] *= factor[mask][:, None]
    array[..., :3] = encoded(colour)
    return float(np.percentile(factor[mask], 5)), float(np.percentile(factor[mask], 95))


body_colour = pixels(os.path.join(C.root, "source_tripo.fbm", "Color.jpg"))
if SKIN_EVEN:
    report["skin_even"] = {"strength": SKIN_EVEN, "factor_p5_p95": [round(f, 3) for f in even(body_colour, SKIN_EVEN)]}
save(body_colour, os.path.join(OUT, f"{Title}_Color.png"), "sRGB")
save(pixels(C.build(f"{Title}_Normal.png")), os.path.join(OUT, f"{Title}_Normal.png"), "Non-Color")
body_skin = np.median(linear(body_colour[..., :3][skin_of(body_colour)]), 0)


def body_at(uvs):
    at = np.clip(uvs, 0.0, 1.0)
    return body_colour[(at[:, 1] * (TEXTURE - 1)).astype(int), (at[:, 0] * (TEXTURE - 1)).astype(int), :3]


for head_title, (folder, fade) in seated.items():
    # The head's skin to the body's colour: their whole skins' middles (linear), not a strip of either; evened as the
    # body's is first (a head from a picture brings its neck painted in the jaw's shadow: on body_warrior_f the neck
    # of every head read 0.475 to 0.49 against a 0.51 to 0.54 face and a 0.56 chest, a dark ring under the jaw).
    head_colour = pixels(os.path.join(folder, f"{head_title}_BaseColor.jpg"))
    if SKIN_EVEN:
        report["heads"][head_title]["skin_even"] = {"strength": SKIN_EVEN,
                                                   "factor_p5_p95": [round(f, 3) for f in even(head_colour, SKIN_EVEN)]}
    gain = body_skin / np.median(linear(head_colour[..., :3][skin_of(head_colour)]), 0)
    head_colour[..., :3] = encoded(linear(head_colour[..., :3]) * gain)
    report["heads"][head_title]["skin_gain_rgb"] = [round(float(g), 3) for g in gain]
    paint(head_colour, fade, body_at)
    save(head_colour, os.path.join(HEADS_OUT, f"{head_title}_Color.png"), "sRGB")
    del head_colour
    # The normals likewise come out of flat where the head's skin meets the body's (the two maps' frames differ).
    head_normal = pixels(os.path.join(folder, f"{head_title}_Normal.png"))
    paint(head_normal, fade, lambda uvs: np.array([0.5, 0.5, 1.0]))
    save(head_normal, os.path.join(HEADS_OUT, f"{head_title}_Normal.png"), "Non-Color")
    # Its eyes' maps (head.py's eyes.py), as they are.
    for suffix in ("Color", "MetallicSmoothness"):
        eyes_map = os.path.join(folder, f"{head_title}Eyes_{suffix}.png")
        if os.path.exists(eyes_map):
            shutil.copyfile(eyes_map, os.path.join(HEADS_OUT, f"{head_title}Eyes_{suffix}.png"))
if torso_fade is not None:
    # The torso's maps as a head's: its skin to the body's colour, the body's skin painted in where it fades out.
    torso_colour = pixels(torso_maps["Color"])
    if SKIN_EVEN:
        report["torso"]["skin_even"] = {"strength": SKIN_EVEN,
                                        "factor_p5_p95": [round(f, 3) for f in even(torso_colour, SKIN_EVEN)]}
    covered = skin_of(torso_colour)
    gain = body_skin / np.median(linear(torso_colour[..., :3][covered]), 0)
    torso_colour[..., :3] = encoded(linear(torso_colour[..., :3]) * gain)
    report["torso"]["skin_gain_rgb"] = [round(float(g), 3) for g in gain]
    paint(torso_colour, torso_fade, body_at)
    save(torso_colour, os.path.join(OUT, f"{Title}Torso_Color.png"), "sRGB")
    del torso_colour
    torso_normal = pixels(torso_maps["Normal"])
    paint(torso_normal, torso_fade, lambda uvs: np.array([0.5, 0.5, 1.0]))
    save(torso_normal, os.path.join(OUT, f"{Title}Torso_Normal.png"), "Non-Color")
if chest_bodies:
    # Each chest's maps as the torso's: its skin to the body's colour, evened as the body's is, and where it fades out
    # what lay under it painted in (the torso's skin under the torso's faces, the body's elsewhere).
    os.makedirs(BODIES_OUT, exist_ok=True)
    torso_final = pixels(os.path.join(OUT, f"{Title}Torso_Color.png")) if torso_fade is not None else None

    def torso_at(uvs):
        at = np.clip(uvs, 0.0, 1.0)
        return torso_final[(at[:, 1] * (TEXTURE - 1)).astype(int), (at[:, 0] * (TEXTURE - 1)).astype(int), :3]

    def corners_at(array, uvs):
        uvs = np.clip(np.array(uvs), 0.0, 1.0)
        return array[(uvs[:, 1] * (TEXTURE - 1)).astype(int), (uvs[:, 0] * (TEXTURE - 1)).astype(int), :3]

    def scale_triangles(target, triangles, corner_gains):
        """Each triangle's texels of target (its corners' UVs on it) times the gain between its corners' (linear)."""
        size = np.array([target.shape[1] - 1, target.shape[0] - 1])
        for uvs, gains in zip(triangles, corner_gains):
            p = np.array(uvs) * size
            lo = np.maximum(np.floor(p.min(0)).astype(int) - 1, 0)
            hi = np.minimum(np.ceil(p.max(0)).astype(int) + 1, size)
            xs, ys = np.meshgrid(np.arange(lo[0], hi[0] + 1), np.arange(lo[1], hi[1] + 1))
            e1, e2 = p[1] - p[0], p[2] - p[0]
            det = e1[0] * e2[1] - e1[1] * e2[0]
            if abs(det) < 1e-9:
                continue
            dx, dy = xs - p[0][0], ys - p[0][1]
            b1, b2 = (dx * e2[1] - dy * e2[0]) / det, (e1[0] * dy - e1[1] * dx) / det
            b0 = 1 - b1 - b2
            slack = 1.0 / max(np.linalg.norm(e1), np.linalg.norm(e2), 1.0)
            inside = (b0 >= -slack) & (b1 >= -slack) & (b2 >= -slack)
            if not inside.any():
                continue
            w = np.stack([b0[inside], b1[inside], b2[inside]], 1).clip(0, None)
            w /= w.sum(1, keepdims=True)
            yi, xi = ys[inside], xs[inside]
            target[yi, xi, :3] = encoded(linear(target[yi, xi, :3]) * (w @ np.array(gains)))

    for chest_title, (_, chest_maps, (chest_triangles, chest_edges)) in chest_bodies.items():
        chest_colour = pixels(chest_maps["Color"])
        # Its skin coloured as hers under it, its own detail kept (the areolas, the pores; the picture's woman had paler
        # breasts, tan lines, which one gain for the whole map turned grey): each vertex's chest colour and her skin's
        # under it, each smoothed over the mesh (COLOUR_REACH steps of its neighbours: about 6 cm, wider than an
        # areola; on the mesh, so the map's islands make no steps), their ratio the gain painted into each triangle.
        on_torso = [torso_final is not None and t[3].startswith(f"{Title}Torso") for t in chest_triangles]
        mine = corners_at(chest_colour, [uv for t in chest_triangles for uv in t[0]])
        under = np.concatenate([
            (torso_at if torso else body_at)(np.array(t[1])) for t, torso in zip(chest_triangles, on_torso)])
        valid = skin_of(np.concatenate([mine, np.ones((len(mine), 1))], 1))             & skin_of(np.concatenate([under, np.ones((len(under), 1))], 1))
        vertex_of = [v for t in chest_triangles for v in t[4]]
        sums = {}
        for v, ok, m, u in zip(vertex_of, valid, linear(mine), linear(under)):
            if ok:
                s_m, s_u, n = sums.get(v, (0.0, 0.0, 0))
                sums[v] = (s_m + m, s_u + u, n + 1)
        field = {v: (m / n, u / n) for v, (m, u, n) in sums.items()}
        neighbours = {}
        for a, b in chest_edges:
            neighbours.setdefault(a, []).append(b)
            neighbours.setdefault(b, []).append(a)
        known = dict(field)
        for _ in range(COLOUR_REACH):
            known = {v: tuple(np.mean([known[n][k] for n in [v] + neighbours.get(v, []) if n in known], 0) for k in (0, 1))
                     for v in set(known) | {n for v in known for n in neighbours.get(v, [])}}
        gain_of = {v: m_u[1] / np.maximum(m_u[0], 1e-4) for v, m_u in known.items()}
        overall = np.median(np.array(list(gain_of.values())), 0)
        scale_triangles(chest_colour, [t[0] for t in chest_triangles],
                        [[gain_of.get(v, overall) for v in t[4]] for t in chest_triangles])
        gains = np.array(list(gain_of.values()))
        report["chests"][chest_title]["skin_gain_rgb_p5_median_p95"] = [
            [round(float(g), 3) for g in np.percentile(gains, q, 0)] for q in (5, 50, 95)]
        fade = [t for t in chest_triangles if min(t[2]) < 1.0]
        paint(chest_colour, [t[:3] for t, torso in zip(chest_triangles, on_torso) if min(t[2]) < 1.0 and torso], torso_at)
        paint(chest_colour, [t[:3] for t, torso in zip(chest_triangles, on_torso) if min(t[2]) < 1.0 and not torso], body_at)
        save(chest_colour, os.path.join(BODIES_OUT, f"{chest_title}_Color.png"), "sRGB")
        del chest_colour
        chest_normal = pixels(chest_maps["Normal"])
        paint(chest_normal, [t[:3] for t in fade], lambda uvs: np.array([0.5, 0.5, 1.0]))
        save(chest_normal, os.path.join(BODIES_OUT, f"{chest_title}_Normal.png"), "Non-Color")
    del torso_final
del body_colour


def export(path, objects):
    """The skeleton and these meshes on it, as Forge takes a character."""
    bpy.ops.object.select_all(action="DESELECT")
    for ob in [rig] + objects:
        ob.select_set(True)
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={"ARMATURE", "MESH"}, apply_unit_scale=True,
                             apply_scale_options="FBX_SCALE_ALL", add_leaf_bones=False, bake_anim=False,
                             mesh_smooth_type="FACE", path_mode="STRIP")


EYES = ("LeftEye", "RightEye")
if any(b.name[len(prefix):] in EYES for b in rig.data.bones):
    raise SystemExit("PIECES the rig has eye bones of its own (heads bring theirs)")


def eye_bones(eyeballs):
    """The skeleton with bones for a head's eyeballs (neck.py's report: each side's middle, the world's frame), children
    of the Head bone, looking ahead (-y), in place of any added before; none: just taken away. Forge adds them to the
    body as it puts the head on."""
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    bones = rig.data.edit_bones
    for bone in [b for b in bones if b.name[len(prefix):] in EYES]:
        bones.remove(bone)
    to_rig = rig.matrix_world.inverted()
    for side, eye in eyeballs.items():
        centre = Vector(eye["centre_m"])
        bone = bones.new(f"{prefix}{side}Eye")
        bone.head, bone.tail = to_rig @ centre, to_rig @ (centre + Vector((0, -eye["radius_mm"] / 1000, 0)))
        bone.parent = bones[f"{prefix}Head"]
        bone.use_deform = True
    bpy.ops.object.mode_set(mode="OBJECT")


fbx = os.path.join(OUT, f"{Title}.fbx")
export(fbx, list(body_pieces.values()))
# Each head named "Head" in its file, the others out of the way while it is, on the skeleton with its eye bones.
for head_title, ob in heads.items():
    ob.name = f"Head {head_title}"
for head_title, ob in heads.items():
    ob.name = "Head"
    eye_bones(report.get("heads", {}).get(head_title, {}).get("eyeballs", {}))
    export(os.path.join(HEADS_OUT, f"{head_title}.fbx"), [ob])
    ob.name = f"Head {head_title}"
eye_bones({})
# Each body type's Body named "Body" in its file, the body's own among them (Bodies/<Title>.fbx), the others out of
# the way while it is.
if chest_pieces:
    body_types = dict({Title: body_pieces["Body"]}, **chest_pieces)
    for type_title, ob in body_types.items():
        ob.name = f"Body {type_title}"
    for type_title, ob in body_types.items():
        ob.name = "Body"
        export(os.path.join(BODIES_OUT, f"{type_title}.fbx"), [ob])
        ob.name = f"Body {type_title}"
    body_pieces["Body"].name = "Body"


# What Forge will read: the FBX back, measured again, and pictured.
def imported(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=path)
    return [o for o in bpy.data.objects if o not in before and o.type == "MESH"]


bpy.ops.wm.read_factory_settings(use_empty=True)
body_back = {o.name: o for o in imported(fbx)}
report["bones_in_fbx"] = sum(len(o.data.bones) for o in bpy.data.objects if o.type == "ARMATURE")
heads_back = {}
for head_title in heads:
    meshes = imported(os.path.join(HEADS_OUT, f"{head_title}.fbx"))
    if len(meshes) != 1:
        raise SystemExit(f"PIECES the head {head_title} read back as {len(meshes)} meshes")
    heads_back[head_title] = meshes[0]
scene = bpy.context.scene
report["meshes_in_fbx"] = sorted(body_back)
report["seams_in_fbx"] = seam_match(dict(body_back, Head=heads_back[Title]))
for head_title in seated:
    head = heads_back[head_title]
    faces_per_slot = np.bincount([p.material_index for p in head.data.polygons], minlength=3)
    # Its eye bones as read back: where each stands against the eyeball it carries (its vertices' sphere), and how many
    # of the eyeball's vertices it weighs wholly.
    skeleton = next(m.object for m in head.modifiers if m.type == "ARMATURE")
    eyes_back = {}
    for side in ("Left", "Right"):
        bone = skeleton.data.bones.get(f"{prefix}{side}Eye")
        group = head.vertex_groups.get(f"{prefix}{side}Eye")
        if bone is None or group is None:
            continue
        carried = [v for v in head.data.vertices if any(g.group == group.index and g.weight > 0.999 for g in v.groups)]
        co = np.array([(head.matrix_world @ v.co)[:] for v in carried])
        centre, _ = sphere_fit(co[co[:, 1] > co[:, 1].mean()])
        at = skeleton.matrix_world @ bone.head_local
        eyes_back[side] = {"vertices": len(carried), "parent": bone.parent.name if bone.parent else None,
                           "bone_off_eyeball_mm": round((at - Vector(centre)).length * 1000, 3)}
    report["heads"][head_title].update(
        eye_bones_in_fbx=eyes_back,
        neck_in_fbx=neck_of(seam_match(dict(body_back, Head=head))),
        shape_keys_in_fbx=[k.name for k in head.data.shape_keys.key_blocks[1:]] if head.data.shape_keys else [],
        materials_in_fbx=[m.name for m in head.data.materials],
        faces_per_material_in_fbx={"0 body's (collar)": int(faces_per_slot[0]), "1 its own": int(faces_per_slot[1]),
                                   "2 its eyes": int(faces_per_slot[2])})
# Each body type read back: its seams against the body's other pieces and its own head (the chest never reaches them).
types_back = {}
for chest_title in chest_pieces:
    meshes = imported(os.path.join(BODIES_OUT, f"{chest_title}.fbx"))
    if len(meshes) != 1:
        raise SystemExit(f"PIECES the body type {chest_title} read back as {len(meshes)} meshes")
    types_back[chest_title] = meshes[0]
    meshes[0].hide_render = True       # out of the body's own pictures; its own come last
    report["chests"][chest_title].update(
        seams_in_fbx=seam_match(dict(body_back, Body=meshes[0], Head=heads_back[Title])),
        materials_in_fbx=[m.name for m in meshes[0].data.materials])
json.dump(report, open(C.checks(f"pieces{TAG}.json"), "w"), indent=1)

colours = {"Body": (0.62, 0.62, 0.6, 1), "Head": (0.85, 0.35, 0.3, 1), "Hands": (0.3, 0.55, 0.85, 1),
           "Feet": (0.35, 0.7, 0.35, 1)}
for name, ob in body_back.items():
    ob.color = colours[name]
for ob in heads_back.values():
    ob.color = colours["Head"]


def wearing(head_title):
    """Only this head shows (the body always)."""
    for title, ob in heads_back.items():
        ob.hide_render = title != head_title


wearing(Title)
height = max((o.matrix_world @ Vector(c)).z for o in [*body_back.values(), heads_back[Title]] for c in o.bound_box)
pictures_as_jpeg(scene)
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"; scene.display.shading.color_type = "OBJECT"
scene.render.resolution_x, scene.render.resolution_y = 800, 1000
scene.world = bpy.data.worlds.new("w")
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam); scene.camera = cam
cam.data.type = "ORTHO"; cam.data.ortho_scale = height * 1.1
for view, d in {"front": (0, -1, 0), "back": (0, 1, 0), "side": (1, 0, 0)}.items():
    d = Vector(d)
    cam.location = Vector((0, 0, height / 2)) + d * 5
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = C.picture(f"pieces_{view}{TAG}")
    bpy.ops.render.render(write_still=True)

# The Body's parts as Forge reads them (its "Segment" layer, read back), each its own colour; the other pieces white.
tints = [(0.62, 0.62, 0.6, 1), (0.85, 0.55, 0.2, 1), (0.85, 0.3, 0.6, 1), (0.3, 0.7, 0.75, 1), (0.55, 0.4, 0.85, 1)]
for ob in [*body_back.values(), *heads_back.values()]:
    mesh = ob.data
    paint_of = mesh.color_attributes.new("Part", "FLOAT_COLOR", "CORNER")
    segment = mesh.uv_layers.get("Segment")
    for k in range(len(mesh.loops)):
        paint_of.data[k].color = tints[round(segment.data[k].uv[0])] if segment else (0.95, 0.95, 0.95, 1)
    mesh.color_attributes.active_color = paint_of
scene.display.shading.color_type = "VERTEX"
for view, d in {"front": (0, -1, 0), "back": (0, 1, 0)}.items():
    d = Vector(d)
    cam.location = Vector((0, 0, height / 2)) + d * 5
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = C.picture(f"segments_{view}{TAG}")
    bpy.ops.render.render(write_still=True)


def textured(path):
    material = bpy.data.materials.new(os.path.basename(path))
    material.use_nodes = True
    texture = material.node_tree.nodes.new("ShaderNodeTexImage")
    texture.image = bpy.data.images.load(path)
    material.node_tree.links.new(texture.outputs["Color"], material.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
    material.node_tree.nodes.active = texture
    return material


# Each head on the body in their colours, whole and the neck close, where a seam, a step or two skins would show. The
# slots are replaced in place: clearing a mesh's materials puts every face in slot 0.
skin = textured(os.path.join(OUT, f"{Title}_Color.png"))
torso_skin = textured(os.path.join(OUT, f"{Title}Torso_Color.png")) if torso_fade is not None else None
for ob in body_back.values():
    for k, m in enumerate(ob.data.materials):     # by name: the FBX keeps each slot's material's name
        ob.data.materials[k] = torso_skin if torso_skin and m and m.name.startswith(f"{Title}Torso") else skin
scene.display.shading.color_type = "TEXTURE"
scene.render.resolution_x = scene.render.resolution_y = 800
neck = world_planes[0][0] + Vector((0, 0, 0.07))
for head_title, head in heads_back.items():
    head.data.materials[0] = skin
    if head_title in seated:
        head.data.materials[1] = textured(os.path.join(HEADS_OUT, f"{head_title}_Color.png"))
        if len(head.data.materials) > 2:
            head.data.materials[2] = textured(os.path.join(HEADS_OUT, f"{head_title}Eyes_Color.png"))
    wearing(head_title)
    for name, ortho, centre in (("whole", height * 1.1, Vector((0, 0, height / 2))), ("neck", 0.42, neck)):
        cam.data.ortho_scale = ortho
        for view, d in {"front": (0, -1, 0), "three_quarter": (0.7, -0.7, 0), "side": (1, 0, 0), "back": (0, 1, 0)}.items():
            if name == "whole" and view != "front":
                continue
            d = Vector(d).normalized()
            cam.location = centre + d * 5
            cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
            scene.render.filepath = C.picture(f"{name}_{view}_{head_title}{TAG}")
            bpy.ops.render.render(write_still=True)

# Each body type in its colours with the body's own head, whole and the chest close, beside the body's own.
if types_back:
    wearing(Title)
    chest_at = Vector((0, 0, report["breasts"]["Left"]["nipple_m"][2] if "breasts" in report else height * 0.72))
    for type_title, ob in [(Title, body_back["Body"]), *types_back.items()]:
        for other in [body_back["Body"], *types_back.values()]:
            other.hide_render = other is not ob
        for k, m in enumerate(ob.data.materials):
            if m and m.name.startswith(f"{Title}Torso") and torso_skin:
                ob.data.materials[k] = torso_skin
            elif m and type_title != Title and m.name.startswith(type_title):
                ob.data.materials[k] = textured(os.path.join(BODIES_OUT, f"{type_title}_Color.png"))
            elif m and not m.name.endswith("_Color.png"):
                ob.data.materials[k] = skin
        for name, ortho, centre in (("whole", height * 1.1, Vector((0, 0, height / 2))), ("chest", 0.6, chest_at)):
            cam.data.ortho_scale = ortho
            for view, d in {"front": (0, -1, 0), "three_quarter": (0.7, -0.7, 0), "side": (1, 0, 0)}.items():
                if name == "whole" and view != "front":
                    continue
                d = Vector(d).normalized()
                cam.location = centre + d * 5
                cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
                scene.render.filepath = C.picture(f"type_{name}_{view}_{type_title}{TAG}")
                bpy.ops.render.render(write_still=True)

print("PIECES", json.dumps(report))
