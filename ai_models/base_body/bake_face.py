"""A Tripo head's paint and relief baked onto her head as maps of its own, and its neck and shoulders onto the body's.

    blender -b -P bake_face.py -- <tripo bust> <face name>

1. Her at the base type's sliders and the face's (checks/face_<name>.json, fit_face.py), settled, at rest.
2. The bust scaled and shifted onto her head as the fit found it.
3. Her head's skin island on a UV square of its own (her.head_uv_fit: the island scaled to fill it), and Cycles
   bakes from the bust onto a copy of her head alone: the bust's normals (its own normal map in them), tangent
   space, and its colour (the diffuse colour pass alone: no light), MAP square. A hit on a bust surface facing more
   than STRAY_FROM degrees from hers is the wrong surface (an ear's back from its front): the normal goes flat there.
4. The body's colour on her own UV: the bust's colour wherever her skin lies within BODY_REACH of it (the neck, the
   shoulders), fading over BODY_FADE beyond to one flat colour, the bust's own skin (the mean of what the neck took).

Writes build/face_<name>_color.png, build/face_<name>_normal.png, build/body_<name>_color.png; the UV fit into
checks/face_<name>.json ("uv"); build/bake_face_<name>.blend (her with the maps on, the bust beside her);
checks/bake_face_<name>_{face,quarter,whole}.png.
"""
import bpy, json, os, sys, time, bmesh
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ARGS = sys.argv[sys.argv.index("--") + 1:]
SOURCE, NAME = ARGS[0], ARGS[1]
HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build")
sys.path.insert(0, HERE)
from her import create, settle, Head, head_uv_fit  # noqa: E402

TYPES = json.load(open(os.path.join(HERE, "types.json")))
BASE = TYPES["base"]
MAP = 4096
CAGE, REACH = 0.02, 0.05  # the bake rays start CAGE outside her head and run REACH inward
STRAY_FROM, STRAY_FULL = 35.0, 55.0
BODY_REACH, BODY_FADE = 0.015, 0.05
T0 = time.time()


def log(*a):
    print("[%6.1fs]" % (time.time() - T0), *a, flush=True)


bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
FACE_JSON = os.path.join(HERE, "checks", "face_%s.json" % NAME)
face = json.load(open(FACE_JSON))
fit = json.load(open(os.path.join(HERE, "checks", "fit_%s.json" % BASE)))["values"]

# --- 1. her ----------------------------------------------------------------------------------------------------------
base, rig = create(fit, face)
me = settle(base, rig)
for p in me.polygons:
    p.use_smooth = True
head = Head(base, me)
P = np.array([base.matrix_world @ v.co for v in me.vertices])
log("her: %d vertices, the head's skin %d faces, %d vertices" % (len(P), len(head.faces), len(head.skin)))

# --- 2. the bust on her head ------------------------------------------------------------------------------------------
before = set(scene.objects)
if SOURCE.endswith(".glb"):
    bpy.ops.import_scene.gltf(filepath=SOURCE)
else:
    bpy.ops.import_scene.fbx(filepath=SOURCE)
bust = [o for o in scene.objects if o not in before and o.type == "MESH"][0]
for o in scene.objects:
    if o not in before and o is not bust:
        bpy.data.objects.remove(o)
bm_ = bust.matrix_world.copy()
bust.parent = None
bust.matrix_world = bm_
bpy.ops.object.select_all(action="DESELECT")
bust.select_set(True)
bpy.context.view_layer.objects.active = bust
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bust.name = "bust " + NAME
T = np.empty(len(bust.data.vertices) * 3)
bust.data.vertices.foreach_get("co", T)
T = T.reshape(-1, 3) * face["bust"]["scale"] + face["bust"]["shift"]
bust.data.vertices.foreach_set("co", T.ravel())
bust.data.update()
for p in bust.data.polygons:
    p.use_smooth = True

# Only what of the bust is seen from outside it. A part wholly inside (woman4's teeth and the inside of her mouth,
# woman3's 34 loose parts) is paint nobody sees, and where her surface lies under the bust's (woman4's chin, up to 9 mm
# behind it) the bake's rays met that part first: a brown patch on her chin. A part is seen when rays from round the
# head (26 ways) meet it first at a share of its points; the largest part, the bust's skin, always is.
bm = bmesh.new()
bm.from_mesh(bust.data)
bm.faces.ensure_lookup_table()
island = np.full(len(bm.faces), -1)
for start in bm.faces:
    if island[start.index] >= 0:
        continue
    label, stack = island.max() + 1, [start]
    island[start.index] = label
    while stack:
        f = stack.pop()
        for e in f.edges:
            for g in e.link_faces:
                if island[g.index] < 0:
                    island[g.index] = label
                    stack.append(g)
part_bvh = BVHTree.FromBMesh(bm)
ways = [Vector((x, y, z)).normalized() for x in (-1, 0, 1) for y in (-1, 0, 1) for z in (-1, 0, 1) if (x, y, z) != (0, 0, 0)]
sizes = np.bincount(island)
inner = []
for label in range(len(sizes)):
    if label == int(np.argmax(sizes)):
        continue
    faces = np.where(island == label)[0]
    points = [bm.faces[i].calc_center_median() for i in faces[:: max(1, len(faces) // 60)]]
    seen = 0
    for c in points:
        for w in ways:
            hit = part_bvh.ray_cast(c + w * 0.5, -w, 0.6)
            if hit[0] is not None and island[hit[2]] == label and (hit[0] - c).length < 1e-3:
                seen += 1
                break
    if seen < 0.1 * len(points):
        inner.append(label)
bmesh.ops.delete(bm, geom=[f for f in bm.faces if island[f.index] in inner], context="FACES")
bm.to_mesh(bust.data)
bm.free()
bust.data.update()
log("bust: %d of its %d parts left out, inside it and seen from nowhere (%d faces)" % (
    len(inner), len(sizes), int(np.isin(island, inner).sum())))
bust_bvh = BVHTree.FromObject(bust, bpy.context.evaluated_depsgraph_get())
log("bust: %d vertices at scale %.3f" % (len(bust.data.vertices), face["bust"]["scale"]))


# --- 3. the face's maps -----------------------------------------------------------------------------------------------
def new_image(name, srgb, fill=None):
    img = bpy.data.images.new(name, MAP, MAP, alpha=False, float_buffer=False)
    img.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
    if fill is not None:
        img.pixels.foreach_set(np.tile(np.array([*fill, 1.0], dtype=np.float32), MAP * MAP))
    return img


def bake_material(name, image):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
    tex.image = image
    mat.node_tree.nodes.active = tex
    return mat, tex


def pixels_of(image):
    px = np.empty(MAP * MAP * 4, dtype=np.float32)
    image.pixels.foreach_get(px)
    return px.reshape(-1, 4)


def save(image, path):
    image.filepath_raw = path
    image.file_format = "PNG"
    image.save()
    image.filepath = path
    image.source = "FILE"
    log("wrote", path)


def bake(target, kind, cage, reach, **kw):
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 1
    scene.cycles.device = "CPU"
    scene.render.bake.use_selected_to_active = True
    scene.render.bake.cage_extrusion = cage
    scene.render.bake.max_ray_distance = reach
    scene.render.bake.normal_space = "TANGENT"
    scene.render.bake.margin = 16
    scene.render.bake.use_pass_direct = False
    scene.render.bake.use_pass_indirect = False
    scene.render.bake.use_pass_color = True
    bpy.ops.object.select_all(action="DESELECT")
    bust.select_set(True)
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.bake(type=kind, **kw)


uv_scale, uv_offset = head_uv_fit(me, head)
log("the head's island fills its square at %.3f" % uv_scale)
head_obj = base.copy()
head_obj.data = me.copy()
head_obj.name = "head"
head_obj.modifiers.clear()
scene.collection.objects.link(head_obj)
bm = bmesh.new()
bm.from_mesh(head_obj.data)
bm.faces.ensure_lookup_table()
keep = set(head.faces.tolist())
bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in keep], context="FACES")
bm.to_mesh(head_obj.data)
bm.free()
uvl = head_obj.data.uv_layers[0]
arr = np.empty(len(head_obj.data.loops) * 2)
uvl.data.foreach_get("uv", arr)
uvl.data.foreach_set("uv", (arr.reshape(-1, 2) * uv_scale + uv_offset).ravel())
face_normal = new_image("face_%s_normal" % NAME, False, (0.5, 0.5, 1.0))
face_color = new_image("face_%s_color" % NAME, True, (0.0, 0.0, 0.0))
mat, tex = bake_material("face bake", face_normal)
head_obj.data.materials.clear()
head_obj.data.materials.append(mat)
log("baking the face's normals %d x %d" % (MAP, MAP))
bake(head_obj, "NORMAL", CAGE, REACH)
px = pixels_of(face_normal)
angle = np.degrees(np.arccos(np.clip(px[:, 2] * 2 - 1, -1, 1)))
stray = np.clip((angle - STRAY_FROM) / (STRAY_FULL - STRAY_FROM), 0, 1)[:, None]
px[:, :3] = px[:, :3] * (1 - stray) + np.array([0.5, 0.5, 1.0], dtype=np.float32) * stray
face_normal.pixels.foreach_set(px.ravel())
log("stray hits: %.1f%% of the map flattened" % (100 * stray.mean()))
save(face_normal, os.path.join(BUILD, "face_%s_normal.png" % NAME))
tex.image = face_color
log("baking the face's colour")
bake(head_obj, "DIFFUSE", CAGE, REACH, pass_filter={"COLOR"})
save(face_color, os.path.join(BUILD, "face_%s_color.png" % NAME))

# --- 4. the body's colour ----------------------------------------------------------------------------------------------
body_color = new_image("body_%s_color" % NAME, True, (0.0, 0.0, 0.0))
mat_b, tex_b = bake_material("body bake", body_color)
me.materials.clear()
me.materials.append(mat_b)
# the bust baked from without its cut base (a flat cap at its bottom, facing down): her chest lies just above it
bm = bmesh.new()
bm.from_mesh(bust.data)
bottom = T[:, 2].min() + 0.03
cap = [f for f in bm.faces if f.normal.z < -0.5 and f.calc_center_median().z < bottom]
bmesh.ops.delete(bm, geom=cap, context="FACES")
bm.to_mesh(bust.data)
bm.free()
log("baking the body's colour where the bust reaches (%d cap faces cut off it)" % len(cap))
bake(base, "DIFFUSE", BODY_REACH, BODY_REACH + BODY_FADE, pass_filter={"COLOR"})
baked = pixels_of(body_color)
# a ray that found nothing paints black (Cycles writes misses so, whatever the image held): skin is never black
hit = baked[:, :3].sum(1) > 0.05
# the mask: 1 where her skin lies within BODY_REACH of the bust, fading over BODY_FADE beyond; baked on her UV
reach = np.array([bust_bvh.find_nearest(Vector(p))[3] for p in P])
weight = np.clip(1 - (reach - BODY_REACH) / BODY_FADE, 0, 1)
weight[P[:, 2] < T[:, 2].min() + 0.02] = 0.0  # not the plinth's cut
colour = me.color_attributes.new("reach", "FLOAT_COLOR", "POINT")
colour.data.foreach_set("color", np.repeat(weight, 4).astype(np.float32).ravel())
mask_image = new_image("body_%s_mask" % NAME, False, (0.0, 0.0, 0.0))
mask_mat = bpy.data.materials.new("reach mask")
mask_mat.use_nodes = True
mn, ml = mask_mat.node_tree.nodes, mask_mat.node_tree.links
attr = mn.new("ShaderNodeVertexColor")
attr.layer_name = "reach"
emit = mn.new("ShaderNodeEmission")
ml.new(attr.outputs["Color"], emit.inputs["Color"])
ml.new(emit.outputs["Emission"], mn["Material Output"].inputs["Surface"])
mask_tex = mn.new("ShaderNodeTexImage")
mask_tex.image = mask_image
mn.active = mask_tex
me.materials[0] = mask_mat
scene.render.bake.use_selected_to_active = False
bpy.ops.object.select_all(action="DESELECT")
base.select_set(True)
bpy.context.view_layer.objects.active = base
bpy.ops.object.bake(type="EMIT")
mask = pixels_of(mask_image)[:, :1] * hit[:, None]
took = mask[:, 0] > 0.99
flat = baked[took, :3].mean(0)
log("the bust reaches %.1f%% of the body's map (%.1f%% of it painted); its skin %s" % (
    100 * (mask > 0.5).mean(), 100 * hit.mean(), flat.round(3).tolist()))
baked[:, :3] = baked[:, :3] * mask + flat * (1 - mask)
body_color.pixels.foreach_set(baked.ravel())
save(body_color, os.path.join(BUILD, "body_%s_color.png" % NAME))
face["uv"] = {"scale": round(uv_scale, 6), "offset": [round(v, 6) for v in uv_offset]}
face["skin"] = [round(float(v), 4) for v in flat]
with open(FACE_JSON, "w") as f:
    json.dump(face, f, indent=1)

# --- the file to look at: her with the maps on, the bust beside her ----------------------------------------------------
bpy.data.objects.remove(head_obj)


def skin_material(name, color_img, normal_img):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nodes, links = m.node_tree.nodes, m.node_tree.links
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.55
    c = nodes.new("ShaderNodeTexImage")
    c.image = color_img
    links.new(c.outputs["Color"], bsdf.inputs["Base Color"])
    n = nodes.new("ShaderNodeTexImage")
    n.image = normal_img
    nm = nodes.new("ShaderNodeNormalMap")
    links.new(n.outputs["Color"], nm.inputs["Color"])
    links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    return m


body_normal = bpy.data.images.load(os.path.join(BUILD, "%s_normal.png" % BASE))
body_normal.colorspace_settings.name = "Non-Color"
me.materials.clear()
me.materials.append(skin_material(TYPES["title"], body_color, body_normal))
me.materials.append(skin_material(TYPES["title"] + "Face", face_color, face_normal))
for i in head.faces:
    me.polygons[i].material_index = 1
uvl = me.uv_layers[0]
arr = np.empty(len(me.loops) * 2)
uvl.data.foreach_get("uv", arr)
arr = arr.reshape(-1, 2)
arr[head.loops] = arr[head.loops] * uv_scale + uv_offset
uvl.data.foreach_set("uv", arr.ravel())
me.color_attributes.remove(me.color_attributes["reach"])
bust.location.x += 0.45
scene.render.engine = "BLENDER_EEVEE"
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 3.0
sun.rotation_euler = (np.radians(60), 0, np.radians(-30))
scene.collection.objects.link(sun)
world = bpy.data.worlds.new("w")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.3, 0.3, 0.3, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.8
scene.world = world
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
scene.collection.objects.link(cam)
scene.camera = cam
scene.render.resolution_x, scene.render.resolution_y = 1600, 1200
centre = P[head.skin].mean(0)
for name, scale, at, rot in (("face", 0.75, (0.22, -10, 0), (90, 0, 0)), ("quarter", 0.45, (7.07, -7.07, 0), (90, 0, 45)),
                             ("whole", 2.0, (0.2, -10, -centre[2] + 0.85), (90, 0, 0))):
    cam.data.ortho_scale = scale
    cam.location = centre + np.array(at)
    cam.rotation_euler = [np.radians(a) for a in rot]
    scene.render.filepath = os.path.join(HERE, "checks", "bake_face_%s_%s.png" % (NAME, name))
    bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(BUILD, "bake_face_%s.blend" % NAME))
log("done")
