"""A hair cap for the base body: her own scalp lifted a hair's breadth off her skin and drawn with short hair, a buzz
cut, the first hair PART (the layer every other part sits on). Made of her own vertices, it keeps her bones, her
weights and every shape key of hers (her other faces, the body types, the face controls) by name, so in Forge it
follows whatever her head becomes; a part made apart from her and hung rigid on the head bone would not (sheet_base.py
measured her scalp moving up to 23 mm under HeadHeight, 10 between her faces, 9 between the body types).

    blender -b -P hair_cap.py [-- <Name> <strands.png>]      (HairBuzz, hair/buzz_strands.png)

Reads build/body_<Title>.blend (build_body.py's, the FBX's twin) and the strands: a picture of short hairs, black on
white (Iris). The hairline is drawn round her head: across the forehead, back at the temples, down in front of the
ears, over them, behind them and low at the nape (HAIRLINE; the ears found as what stands out of her skull); its edge
soft, the hairs thinning over a few millimetres. Writes build/forge/<Title>/Hair/<Name>.fbx (the cap on her rig, one
slot <Name>) and <Name>_Color.png (the hair's colour, its alpha where the hairs are), and checks/hair_<name>_{front,
side,back,quarter}.jpg: her head wearing it, drawn flat.
"""
import bmesh, json, math, os, sys
import bpy
import numpy as np
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from eyes import save_map  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
NAME = ARGS[0] if ARGS else "HairBuzz"
STRANDS = ARGS[1] if len(ARGS) > 1 else os.path.join(HERE, "hair", "buzz_strands.png")
SPEC = json.load(open(os.path.join(HERE, "types.json")))
TITLE = SPEC["title"]
OUT = os.path.join(HERE, "build", "forge", TITLE, "Hair")
os.makedirs(OUT, exist_ok=True)

LIFT = 0.0012        # m the cap stands off her skin: over it at every shape, never in it
SIZE = 2048          # the map's side
TILE = 0.15          # m of scalp one picture of strands covers (its strands about 3 mm long)
HAIR = (0.16, 0.12, 0.09)   # the hair's own colour (sRGB): a mid brown, so a dye can carry it as dark as black or as light as platinum (CharacterHair.MostTint)
UNDER = 0.10         # how much the hair covers between its strands (the scalp seen through a buzz cut reads darker)
EDGE = (0.002, 0.005)   # m under and over the hairline over which the hairs thin out to none
EAR_CLEAR = (0.002, 0.007)  # m from the ear over which they thin out to none
# The hairline: how high it runs (m above her eyes' centre) round her head, by the angle from her front (degrees, each
# side alike). Over the ear it runs EAR_ARCH above the ear's top, from the ear's front to its back (found below).
FOREHEAD, TEMPLE, SIDEBURN, BEHIND, NAPE = 0.060, 0.046, 0.004, -0.024, -0.075
EAR_ARCH = 0.008

bpy.ops.wm.open_mainfile(filepath=os.path.join(HERE, "build", "body_%s.blend" % TITLE))
body = bpy.data.objects["Body"]
rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
me = body.data
assert all(k.value == 0.0 for k in me.shape_keys.key_blocks), "a shape key is not at 0"
world = np.array(body.matrix_world)
co = np.array([tuple(v.co) for v in me.vertices]) @ world[:3, :3].T + world[:3, 3]
normals = np.array([tuple(v.normal) for v in me.vertices]) @ world[:3, :3].T
normals /= np.linalg.norm(normals, axis=1, keepdims=True)
slots = [m.name for m in me.materials]
EYES, FACE = slots.index(TITLE + "Eyes"), slots.index(TITLE + "Face")
eye_verts = sorted({v for p in me.polygons if p.material_index == EYES for v in p.vertices})
face_verts = np.array(sorted({v for p in me.polygons if p.material_index == FACE for v in p.vertices}))

# Her head's frame: its axis (the middle of her skull, seen from above), up, forward (toward her eyes), right; heights
# from her eyes' centre.
eye = co[eye_verts].mean(axis=0)
top = co[:, 2].max()
skull = face_verts[co[face_verts, 2] > eye[2] + 0.02]
axis = np.array([(co[skull, 0].min() + co[skull, 0].max()) / 2, (co[skull, 1].min() + co[skull, 1].max()) / 2, eye[2]])
forward = np.array([eye[0] - axis[0], eye[1] - axis[1], 0.0])
forward /= np.linalg.norm(forward)
right = np.cross(forward, (0.0, 0.0, 1.0))


def frame(p):
    """Points in her head's frame: across (right), ahead, up from her eyes; and the angle round from her front (deg)."""
    d = p - axis
    x, y, z = d @ right, d @ forward, d[..., 2]
    return x, y, z, np.degrees(np.abs(np.arctan2(x, y)))


x, y, z, turn = frame(co)

# Her ears: what stands out of her skull at their height on her sides. The skull is an ellipsoid fitted to her scalp
# over the ears and round the back of her head; an ear's points stand more than 4 mm outside it.
fit = face_verts[((z[face_verts] > 0.035) & (z[face_verts] < top - eye[2] - 0.01)) |
                 ((turn[face_verts] > 140) & (z[face_verts] > -0.03))]
A = np.stack([x[fit] ** 2, y[fit] ** 2, z[fit] ** 2, x[fit], y[fit], z[fit]], 1)
q = np.linalg.lstsq(A, np.ones(len(fit)), rcond=None)[0]


def outside(i):
    """How far (m, about) points stand outside the skull's ellipsoid."""
    value = q[0] * x[i] ** 2 + q[1] * y[i] ** 2 + q[2] * z[i] ** 2 + q[3] * x[i] + q[4] * y[i] + q[5] * z[i]
    return (np.sqrt(np.maximum(value, 0)) - 1) * np.sqrt(x[i] ** 2 + y[i] ** 2)


window = face_verts[(z[face_verts] > -0.065) & (z[face_verts] < 0.04) & (turn[face_verts] > 55) & (turn[face_verts] < 135)]
ears = window[outside(window) > 0.004]
assert len(ears) > 20, "no ears found (%d points)" % len(ears)
ear_top = z[ears].max()
ear_front, ear_back = np.percentile(turn[ears], 3), np.percentile(turn[ears], 97)
print("ears: %d points, top %.1f mm above the eyes, %.0f to %.0f deg round from the front, standing out up to %.1f mm" % (
    len(ears), ear_top * 1000, ear_front, ear_back, outside(ears).max() * 1000), flush=True)

# The hairline round her head: by the angle from her front, how high it runs.
LINE = np.array([(0, FOREHEAD), (30, FOREHEAD - 0.003), (48, TEMPLE), (56, TEMPLE - 0.012), (ear_front - 3, SIDEBURN),
                 (ear_front + 3, ear_top + EAR_ARCH), (ear_back - 2, ear_top + EAR_ARCH),
                 (ear_back + 14, BEHIND), (140, NAPE + 0.014), (180, NAPE)])
assert np.all(np.diff(LINE[:, 0]) > 0), "the hairline's angles are out of order: %s" % LINE[:, 0]


def hairline(turn):
    """How high (m above the eyes) the hairline runs at an angle round from her front; a little uneven, as hair grows."""
    return np.interp(turn, LINE[:, 0], LINE[:, 1]) + 0.0012 * np.sin(np.radians(turn) * 9.0) + 0.0007 * np.sin(np.radians(turn) * 23.0 + 1.0)


def smooth(a, b, t):
    t = np.clip((t - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


# --- the cap: her faces from a little under the hairline up, her eyes' and ears' left out ----------------------------
over = z >= hairline(turn) - EDGE[0] - 0.006
is_ear = np.zeros(len(co), bool)
is_ear[ears] = True
keep = [p.index for p in me.polygons
        if p.material_index != EYES and any(over[v] for v in p.vertices) and not any(is_ear[v] for v in p.vertices)]
cap = body.copy()
cap.data = me.copy()
cap.name = cap.data.name = NAME
bpy.context.scene.collection.objects.link(cap)
bm = bmesh.new()
bm.from_mesh(cap.data)
keep_set = set(keep)
bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in keep_set], context="FACES_ONLY")
bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
bm.to_mesh(cap.data)
bm.free()
cd = cap.data
# Which of her vertices each of the cap's is: its place, and its normal, at her basis.
mine = np.array([int(np.argmin(np.linalg.norm(co - (world[:3, :3] @ np.array(v.co) + world[:3, 3]), axis=1))) for v in cd.vertices])
lift = normals[mine] * LIFT @ np.linalg.inv(world[:3, :3]).T
for block in cd.shape_keys.key_blocks:
    for i, d in enumerate(block.data):
        d.co = Vector(np.array(d.co) + lift[i])
for i, v in enumerate(cd.vertices):
    v.co = Vector(np.array(v.co) + lift[i])
cd.materials.clear()
material = bpy.data.materials.new(NAME)
cd.materials.append(material)
for p in cd.polygons:
    p.material_index = 0
    p.use_smooth = True
print("cap: %d of her faces, %d vertices, %d shape keys, lifted %.1f mm" % (
    len(cd.polygons), len(cd.vertices), len(cd.shape_keys.key_blocks) - 1, LIFT * 1000), flush=True)

# Its own UV square, flattened as evenly as it goes (conformal: the strands keep their shape everywhere).
bpy.ops.object.select_all(action="DESELECT")
cap.select_set(True)
bpy.context.view_layer.objects.active = cap
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.unwrap(method="CONFORMAL", margin=0.02)
bpy.ops.object.mode_set(mode="OBJECT")

# --- its map: the strands where the hairline says, the hair's colour everywhere -------------------------------------
P = co[mine]                                   # the cap's points on her skin (world)
uv = np.zeros((len(cd.loops), 2))
cd.uv_layers.active.data.foreach_get("uv", uv.ravel())
tris = []
for p in cd.polygons:
    loops = list(p.loop_indices)
    for k in range(1, len(loops) - 1):
        tris.append((loops[0], loops[k], loops[k + 1]))
tris = np.array(tris)
vert_of = np.array([l.vertex_index for l in cd.loops])
area3 = np.linalg.norm(np.cross(P[vert_of[tris[:, 1]]] - P[vert_of[tris[:, 0]]], P[vert_of[tris[:, 2]]] - P[vert_of[tris[:, 0]]]), axis=1) / 2
e1, e2 = uv[tris[:, 1]] - uv[tris[:, 0]], uv[tris[:, 2]] - uv[tris[:, 0]]
area2 = np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) / 2
scale = np.sqrt(area3 / np.maximum(area2, 1e-12))           # m of scalp per UV unit, triangle by triangle
metres = float(np.sqrt(area3.sum() / area2.sum()))
print("UV: %.3f m of scalp per unit; triangles from %.2f to %.2f of that (5th to 95th percentile)" % (
    metres, *(np.percentile(scale, [5, 95]) / metres)), flush=True)

strands = bpy.data.images.load(STRANDS)
w, h = strands.size
grey = np.array(strands.pixels[:]).reshape(h, w, 4)[..., :3].mean(-1)
# Made seamless: the picture laid over itself shifted half a side, each where it is farther from its own edge.
shifted = np.roll(np.roll(grey, h // 2, 0), w // 2, 1)
ry = np.minimum(np.arange(h), h - 1 - np.arange(h)) / (h / 2)
rx = np.minimum(np.arange(w), w - 1 - np.arange(w)) / (w / 2)
weight = np.clip(np.minimum.outer(ry, rx) * 4, 0, 1)
grey = grey * weight + shifted * (1 - weight)
dark = np.clip((1 - grey) * 1.15, 0, 1)

colour = np.zeros((SIZE, SIZE, 4), np.float32)
colour[..., :3] = HAIR
for t in tris:
    a, b, c = uv[t] * SIZE
    lo = np.floor(np.minimum(np.minimum(a, b), c)).astype(int)
    hi = np.ceil(np.maximum(np.maximum(a, b), c)).astype(int)
    gx, gy = np.meshgrid(np.arange(max(lo[0], 0), min(hi[0] + 1, SIZE)), np.arange(max(lo[1], 0), min(hi[1] + 1, SIZE)))
    px = np.stack([gx.ravel() + 0.5, gy.ravel() + 0.5], 1)
    m = np.array([[b[0] - a[0], c[0] - a[0]], [b[1] - a[1], c[1] - a[1]]])
    if abs(np.linalg.det(m)) < 1e-9:
        continue
    l12 = (px - a) @ np.linalg.inv(m).T
    bary = np.column_stack([1 - l12.sum(1), l12])
    inside = (bary >= -0.02).all(1)
    if not inside.any():
        continue
    bary, px = bary[inside], px[inside]
    p3 = bary @ P[vert_of[t]]
    px_, py_, pz_, pt = frame(p3)
    density = smooth(-EDGE[0], EDGE[1], pz_ - hairline(pt))
    near = np.abs(pt - (ear_front + ear_back) / 2) < 50
    if near.any():
        d = np.full(len(p3), 1.0)
        d[near] = np.min(np.linalg.norm(p3[near, None, :] - co[None, ears, :], axis=2), axis=1)
        density *= smooth(*EAR_CLEAR, d)
    # The strands, a picture to every TILE metres of scalp.
    sx = (px[:, 0] / SIZE * metres / TILE * w) % w
    sy = (px[:, 1] / SIZE * metres / TILE * h) % h
    hair = dark[sy.astype(int) % h, sx.astype(int) % w]
    iy, ix = px[:, 1].astype(int), px[:, 0].astype(int)
    colour[iy, ix, 3] = density * np.clip(UNDER + (0.95 - UNDER) * hair, 0, 1)
save_map(colour, os.path.join(OUT, NAME + "_Color.png"), "sRGB")
print("map: %d px, hair over %.1f%% of it" % (SIZE, (colour[..., 3] > 0.05).mean() * 100), flush=True)

# --- the FBX: the cap on her rig, as build_body.py exports her --------------------------------------------------------
bpy.ops.object.select_all(action="DESELECT")
cap.select_set(True)
rig.select_set(True)
path = os.path.join(OUT, NAME + ".fbx")
bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={"ARMATURE", "MESH"}, apply_unit_scale=True,
                         apply_scale_options="FBX_SCALE_ALL", add_leaf_bones=False, bake_anim=False,
                         mesh_smooth_type="FACE", path_mode="STRIP")
print("wrote", path, flush=True)

# --- the check: her head wearing it, drawn flat (her paint, the cap's over it) ---------------------------------------
maps = os.path.join(HERE, "build", "forge", TITLE)
for slot in body.material_slots:
    name = slot.material.name.split(".")[0]
    mat = bpy.data.materials.new(name + "_check")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(os.path.join(maps, name + "_Color.png"))
    emit = nodes.new("ShaderNodeEmission")
    out = nodes.new("ShaderNodeOutputMaterial")
    links.new(tex.outputs["Color"], emit.inputs["Color"])
    links.new(emit.outputs["Emission"], out.inputs["Surface"])
    slot.material = mat
material.use_nodes = True
nodes, links = material.node_tree.nodes, material.node_tree.links
nodes.clear()
tex = nodes.new("ShaderNodeTexImage")
tex.image = bpy.data.images.load(os.path.join(OUT, NAME + "_Color.png"))
emit, clear, mix, out = (nodes.new("ShaderNodeEmission"), nodes.new("ShaderNodeBsdfTransparent"),
                         nodes.new("ShaderNodeMixShader"), nodes.new("ShaderNodeOutputMaterial"))
links.new(tex.outputs["Color"], emit.inputs["Color"])
links.new(tex.outputs["Alpha"], mix.inputs["Fac"])
links.new(clear.outputs[0], mix.inputs[1])
links.new(emit.outputs[0], mix.inputs[2])
links.new(mix.outputs[0], out.inputs["Surface"])
if hasattr(material, "surface_render_method"):
    material.surface_render_method = "BLENDED"
rig.hide_render = True
scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.view_settings.view_transform = "Standard"
sky = bpy.data.worlds.new("check")
sky.use_nodes = True
sky.node_tree.nodes["Background"].inputs[0].default_value = (0.5, 0.5, 0.5, 1)
scene.world = sky
scene.render.resolution_x = scene.render.resolution_y = 900
scene.render.image_settings.file_format = "JPEG"
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
cam.data.ortho_scale = 0.34
scene.collection.objects.link(cam)
scene.camera = cam
centre = Vector((axis[0], axis[1], eye[2] + 0.01))
f, r = Vector(forward), Vector(right)
for view, toward in {"front": -f, "side": -r, "back": f, "quarter": -(f - r).normalized(), "top": Vector((0, 0, -1)) + 0.4 * -f}.items():
    toward = toward.normalized()
    cam.location = centre - toward * 1.0
    cam.rotation_euler = toward.to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = os.path.join(HERE, "checks", "hair_%s_%s.jpg" % (NAME.lower(), view))
    bpy.ops.render.render(write_still=True)
print("checks written", flush=True)

# Her other faces (types.json "faces", each a shape key of hers with maps of its own): the side and the ear close, with
# the cap and without, so what the cap does there shows apart from what the face does.
ear_at = Vector(tuple(co[ears].mean(axis=0)))
cap_keys = cap.data.shape_keys.key_blocks
for other in [f["name"] for f in SPEC.get("faces", []) if f["name"] != SPEC.get("face")]:
    me.shape_keys.key_blocks[other].value = cap_keys[other].value = 1.0
    for slot in body.material_slots:
        base = slot.material.name.replace("_check", "")
        part = base[len(TITLE):]  # "Face", "Eyes" or ""
        path = os.path.join(maps, "Bodies", other + part + "_Color.png")
        if part and os.path.exists(path):
            slot.material.node_tree.nodes["Image Texture"].image = bpy.data.images.load(path)
    for shown in (True, False):
        cap.hide_render = not shown
        for view, toward, scale, at in (("front", -f, 0.34, centre), ("side", -r, 0.34, centre), ("ear", -r, 0.12, ear_at)):
            toward = toward.normalized()
            cam.data.ortho_scale = scale
            cam.location = at - toward * 1.0
            cam.rotation_euler = toward.to_track_quat("-Z", "Y").to_euler()
            scene.render.filepath = os.path.join(HERE, "checks", "hair_%s_%s_%s%s.jpg" % (
                NAME.lower(), other, view, "" if shown else "_bare"))
            bpy.ops.render.render(write_still=True)
    me.shape_keys.key_blocks[other].value = cap_keys[other].value = 0.0
    for slot in body.material_slots:
        base = slot.material.name.replace("_check", "")
        slot.material.node_tree.nodes["Image Texture"].image = bpy.data.images.load(os.path.join(maps, base + "_Color.png"))
    cap.hide_render = False
print("faces' checks written", flush=True)
