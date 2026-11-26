"""A padded suit for the base body: a stand-in body armor, so Forge's armor pipe (a worn piece stitched on her bones,
hiding the skin it covers, following her body types) is built and seen before the first real set arrives from Tripo.
Made as the hair cap is (hair_cap.py): her own vertices, over her trunk, arms and legs (every face whose vertices all
weigh most to a bone of those: the neck, head, hands and feet stay bare), lifted LIFT off her skin, keeping her bones,
her weights and every shape key of hers by name, so in Forge it follows whatever her body becomes. One slot, the set's
name and the body piece it covers run together (PaddedBody: Forge reads what a piece covers off the end of its name).

    blender -b -P armor_pad.py [-- <Set>]      (Padded)

Reads build/body_<Title>.blend (build_body.py's, the FBX's twin). Writes build/forge/<Title>/Armor/<Set>/<Set>Body.fbx
(the suit on her rig) and <Set>Body_Color.png (quilted linen: diamonds of seams, painted by where each texel stands in
space, so her UV seams don't show in the quilt), and checks/armor_<set>_{front,side,back,quarter}.jpg: her wearing it,
drawn flat; and _<type>_front.jpg for each body type, the suit following it.
"""
import bmesh, json, os, sys
import bpy
import numpy as np
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from eyes import save_map  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SET = ARGS[0] if ARGS else "Padded"
COVERS = "Body"                  # the piece of her it stands in for (Forge: BodyPiece.Body)
NAME = SET + COVERS
SPEC = json.load(open(os.path.join(HERE, "types.json")))
TITLE = SPEC["title"]
OUT = os.path.join(HERE, "build", "forge", TITLE, "Armor", SET)
os.makedirs(OUT, exist_ok=True)

LIFT = 0.005         # m the suit stands off her skin: a padded cloth's thickness, over her at every shape, never in it
SIZE = 2048          # the map's side
DIAMOND = 0.045      # m between the quilt's seams (along each diagonal)
SEAM = 0.0015        # m: half the width of a seam's dark line
LINEN = (0.52, 0.44, 0.33)   # undyed linen (sRGB)
# The bones a vertex weighing most to is in the suit: the trunk and the limbs to the wrists and ankles. Everything else
# (the neck and head, the hands and fingers, the feet and toes, the eyes, jaw and lids) stays her skin.
SUIT = {"Hips", "Spine", "Spine1", "Spine2", "LeftShoulder", "RightShoulder", "LeftArm", "RightArm", "LeftForeArm",
        "RightForeArm", "LeftUpLeg", "RightUpLeg", "LeftLeg", "RightLeg", "LeftBreast", "RightBreast"}


def short(bone):
    return bone.split(":")[-1]


def in_suit(bone):
    return short(bone) in SUIT or "Buttock" in bone


bpy.ops.wm.open_mainfile(filepath=os.path.join(HERE, "build", "body_%s.blend" % TITLE))
body = bpy.data.objects["Body"]
rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
me = body.data
assert all(k.value == 0.0 for k in me.shape_keys.key_blocks), "a shape key is not at 0"
world = np.array(body.matrix_world)
co = np.array([tuple(v.co) for v in me.vertices]) @ world[:3, :3].T + world[:3, 3]
normals = np.array([tuple(v.normal) for v in me.vertices]) @ world[:3, :3].T
normals /= np.linalg.norm(normals, axis=1, keepdims=True)

# Each vertex's heaviest bone.
gi = {g.index: g.name for g in body.vertex_groups}
heaviest = np.full(len(me.vertices), "", dtype=object)
for v in me.vertices:
    best, weight = "", -1.0
    for g in v.groups:
        if g.weight > weight:
            best, weight = gi[g.group], g.weight
    heaviest[v.index] = best
suited = np.array([in_suit(b) for b in heaviest])
print("her: %d vertices, %d of them weighing most to the trunk and limbs" % (len(me.vertices), suited.sum()), flush=True)

# --- the suit: her faces whose every vertex is suited -------------------------------------------------------------
keep = {p.index for p in me.polygons if all(suited[v] for v in p.vertices)}
suit = body.copy()
suit.data = me.copy()
suit.name = suit.data.name = NAME
bpy.context.scene.collection.objects.link(suit)
bm = bmesh.new()
bm.from_mesh(suit.data)
orig = bm.verts.layers.int.new("orig")
for v in bm.verts:
    v[orig] = v.index
bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in keep], context="FACES_ONLY")
bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
bm.to_mesh(suit.data)
bm.free()
cd = suit.data
# Which of her vertices each of the suit's is (the layer survives the cut as an attribute of the mesh).
mine = np.empty(len(cd.vertices), int)
cd.attributes["orig"].data.foreach_get("value", mine)
cd.attributes.remove(cd.attributes["orig"])
assert np.allclose(np.array([tuple(v.co) for v in cd.vertices]) @ world[:3, :3].T + world[:3, 3], co[mine], atol=1e-6), "the cut lost track of her vertices"
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
print("suit: %d of her %d faces, %d vertices, %d shape keys, lifted %.1f mm; from %.2f to %.2f m up" % (
    len(cd.polygons), len(me.polygons), len(cd.vertices), len(cd.shape_keys.key_blocks) - 1, LIFT * 1000,
    co[mine][:, 2].min(), co[mine][:, 2].max()), flush=True)

# --- its map: quilted linen, painted by where each texel stands on her ----------------------------------------------
P = co[mine]                                   # the suit's points on her skin (world, her basis)
NRM = normals[mine]
uv = np.zeros((len(cd.loops), 2))
cd.uv_layers.active.data.foreach_get("uv", uv.ravel())
tris = []
for p in cd.polygons:
    loops = list(p.loop_indices)
    for k in range(1, len(loops) - 1):
        tris.append((loops[0], loops[k], loops[k + 1]))
tris = np.array(tris)
vert_of = np.array([l.vertex_index for l in cd.loops])


def quilt(points, nrm):
    """The linen's colour at points on her (world), the seams' diamonds laid by the plane the skin faces most
    (across her front and back, along her sides, over her shoulders), each a little puffed between its seams."""
    ax = np.argmax(np.abs(nrm), axis=1)
    u = np.where(ax == 1, points[:, 0], np.where(ax == 0, points[:, 1], points[:, 0]))
    v = np.where(ax == 2, points[:, 1], points[:, 2])
    s1, s2 = (u + v) / np.sqrt(2), (u - v) / np.sqrt(2)
    t1 = np.abs(((s1 / DIAMOND + 0.5) % 1.0) - 0.5) * DIAMOND
    t2 = np.abs(((s2 / DIAMOND + 0.5) % 1.0) - 0.5) * DIAMOND
    t = np.minimum(t1, t2)
    puff = np.clip(t / (DIAMOND * 0.35), 0.0, 1.0)
    puff = puff * puff * (3 - 2 * puff)
    seam = np.exp(-(t / SEAM) ** 2)
    shade = (0.84 + 0.16 * puff) * (1 - 0.45 * seam)
    return np.array(LINEN)[None, :] * shade[:, None]


rng = np.random.default_rng(11)
colour = np.zeros((SIZE, SIZE, 4), np.float32)
colour[..., :3] = LINEN
colour[..., 3] = 1.0
painted = np.zeros((SIZE, SIZE), bool)
for t in tris:
    a, b, c = uv[t] * SIZE
    lo = np.floor(np.minimum(np.minimum(a, b), c)).astype(int) - 1
    hi = np.ceil(np.maximum(np.maximum(a, b), c)).astype(int) + 1
    gx, gy = np.meshgrid(np.arange(max(lo[0], 0), min(hi[0] + 1, SIZE)), np.arange(max(lo[1], 0), min(hi[1] + 1, SIZE)))
    px = np.stack([gx.ravel() + 0.5, gy.ravel() + 0.5], 1)
    m = np.array([[b[0] - a[0], c[0] - a[0]], [b[1] - a[1], c[1] - a[1]]])
    if abs(np.linalg.det(m)) < 1e-9:
        continue
    l12 = (px - a) @ np.linalg.inv(m).T
    bary = np.column_stack([1 - l12.sum(1), l12])
    inside = (bary >= -0.08).all(1)        # a texel over the edge too, so no seam shows between islands
    if not inside.any():
        continue
    bary, px = bary[inside], px[inside]
    p3 = bary @ P[vert_of[t]]
    n3 = bary @ NRM[vert_of[t]]
    shade = quilt(p3, n3) * (1 + rng.normal(0, 0.03, (len(p3), 1)))
    iy, ix = px[:, 1].astype(int), px[:, 0].astype(int)
    colour[iy, ix, :3] = np.clip(shade, 0, 1)
    painted[iy, ix] = True
save_map(colour, os.path.join(OUT, NAME + "_Color.png"), "sRGB")
print("map: %d px, the suit over %.1f%% of it" % (SIZE, painted.mean() * 100), flush=True)

# --- the FBX: the suit on her rig, as build_body.py exports her -------------------------------------------------------
bpy.ops.object.select_all(action="DESELECT")
suit.select_set(True)
rig.select_set(True)
path = os.path.join(OUT, NAME + ".fbx")
bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={"ARMATURE", "MESH"}, apply_unit_scale=True,
                         apply_scale_options="FBX_SCALE_ALL", add_leaf_bones=False, bake_anim=False,
                         mesh_smooth_type="FACE", path_mode="STRIP")
print("wrote", path, flush=True)

# --- the check: her wearing it, drawn flat (her paint, the suit's over it) ------------------------------------------
maps = os.path.join(HERE, "build", "forge", TITLE)


def flat(name, image_path, alpha=False):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(image_path)
    emit = nodes.new("ShaderNodeEmission")
    out = nodes.new("ShaderNodeOutputMaterial")
    links.new(tex.outputs["Color"], emit.inputs["Color"])
    links.new(emit.outputs["Emission"], out.inputs["Surface"])
    return mat


for slot in body.material_slots:
    name = slot.material.name.split(".")[0]
    slot.material = flat(name + "_check", os.path.join(maps, name + "_Color.png"))
suit.material_slots[0].material = flat(NAME + "_check", os.path.join(OUT, NAME + "_Color.png"))
rig.hide_render = True
scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.view_settings.view_transform = "Standard"
sky = bpy.data.worlds.new("check")
sky.use_nodes = True
sky.node_tree.nodes["Background"].inputs[0].default_value = (0.5, 0.5, 0.5, 1)
scene.world = sky
scene.render.resolution_x = 700
scene.render.resolution_y = 1400
scene.render.image_settings.file_format = "JPEG"
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
cam.data.ortho_scale = 1.95
scene.collection.objects.link(cam)
scene.camera = cam
centre = Vector((0.0, 0.0, (co[:, 2].max() + co[:, 2].min()) / 2))
f, r = Vector((0.0, -1.0, 0.0)), Vector((1.0, 0.0, 0.0))     # her front faces -y in Blender; her left is +x
for view, toward in {"front": -f, "side": -r, "back": f, "quarter": -(f - r).normalized()}.items():
    toward = toward.normalized()
    cam.location = centre - toward * 3.0
    cam.rotation_euler = toward.to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = os.path.join(HERE, "checks", "armor_%s_%s.jpg" % (SET.lower(), view))
    bpy.ops.render.render(write_still=True)
print("checks written", flush=True)

# Each body type at 1 (her Body's shape and the suit's, by name): the suit on it, from the front.
suit_keys = cd.shape_keys.key_blocks
for other in [t["name"] for t in SPEC["types"] if t["name"] in me.shape_keys.key_blocks]:
    me.shape_keys.key_blocks[other].value = suit_keys[other].value = 1.0
    toward = (-f).normalized()
    cam.location = centre - toward * 3.0
    cam.rotation_euler = toward.to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = os.path.join(HERE, "checks", "armor_%s_%s_front.jpg" % (SET.lower(), other))
    bpy.ops.render.render(write_still=True)
    me.shape_keys.key_blocks[other].value = suit_keys[other].value = 0.0
print("types' checks written", flush=True)
