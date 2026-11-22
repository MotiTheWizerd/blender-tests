"""A Tripo body type's surface detail baked onto the fitted MPFB body as a normal map.

    blender -b -P bake_detail.py -- <tripo file> <type name>

1. The MPFB female at the sliders in checks/fit_<type>.json (fit_macros.py), the mixamo_unity rig, helpers dropped.
2. The Tripo body at her height, its trunk over hers.
3. Pose fit: her bones turned until she lies on the Tripo body (coordinate descent, from checks/wrap_<type>.json's
   pose when there is one). Her shape is not touched.
4. Cycles bakes the Tripo surface's normals, tangent space, onto a posed copy of her (same mesh, same UVs);
   the map then shows on her in rest pose. The Tripo hands are cut off the copy baked from (they hang before
   the hips and their fingers are fused); the map starts flat, and is blended back to flat over her hands and
   wrists and her breasts (a mask baked on the same UVs; the breasts are their own kind) and wherever the Tripo surface a ray found faces more than STRAY_FROM
   degrees away from hers (an upper arm hit from the armpit, a thigh from the crotch), so there she keeps her
   own relief.

Writes build/<type>_normal.png (4096 square), build/detail_<type>.blend (her at rest with the map, the Tripo body
beside her), checks/detail_<type>.json (pose, fit cost), checks/detail_<type>_*.png.
"""
import bpy, json, os, sys, time
import numpy as np
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

ARGS = sys.argv[sys.argv.index("--") + 1:]
SOURCE, TYPE = ARGS[0], ARGS[1]
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from her import create, settle, apply_wrap  # noqa: E402
from pose import place, fit, posed, world_points, import_tripo  # noqa: E402

BUILD = os.path.join(HERE, "build")
os.makedirs(BUILD, exist_ok=True)
MAP = 4096
COLOUR_MAP = 8192  # the Tripo paint, when the body has it (Moti: 8K), baked onto her UV at this size
HAND_CUT = 0.04  # m around her posed hands the Tripo body is cut away before the bake
HAND_FADE = 0.05  # m beyond HAND_CUT over which the map fades from her own relief back to the Tripo one
BREAST_CUT = 0.06  # m around the breasts (the vertices on their bones) that keep her own relief wholly: their own kind
BREAST_FADE = 0.05  # m beyond BREAST_CUT over which the map fades back to the Tripo relief
# a ray that lands on a Tripo surface facing more than STRAY_FROM degrees away from hers hit the wrong surface (an
# upper arm from the armpit, a thigh from the crotch); the map goes flat there, fading in from STRAY_FROM
STRAY_FROM, STRAY_FULL = 35.0, 55.0
CAGE, REACH = 0.05, 0.12  # the bake rays start CAGE outside her and run REACH inward
T0 = time.time()


def log(*a):
    print("[%6.1fs]" % (time.time() - T0), *a, flush=True)


bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# --- 1. the fitted MPFB body, wrapped onto the Tripo body where wrap.py ran ------------------------------------------
fit_values = json.load(open(os.path.join(HERE, "checks", "fit_%s.json" % TYPE)))["values"]
base, rig = create(fit_values)
settle(base, rig)
base.name, rig.name = "MPFB " + TYPE, "rig " + TYPE
N = len(base.data.vertices)
wrap_json = os.path.join(HERE, "checks", "wrap_%s.json" % TYPE)
wrapped = apply_wrap(base, rig, TYPE) is not None
bpy.context.view_layer.update()
rest_world = world_points(base)
height = rest_world[:, 2].max() - rest_world[:, 2].min()
ground = rest_world[:, 2].min()
log("mpfb", N, "vertices, %.3f m%s" % (height, ", wrapped onto the Tripo body" if wrapped else ""))

# --- 2. the Tripo body, her pose on it --------------------------------------------------------------------------------
tripo = import_tripo(SOURCE, "Tripo " + TYPE)
wrap_record = json.load(open(wrap_json)) if wrapped else {}
# wrapped, she lies on the Tripo body placed and posed as the wrap had it: the same placement, the pose as it is
T, tripo_bvh, T_sample, placement = place(tripo, rest_world, wrap_record.get("tripo_placement"))
log("tripo", len(T), "vertices, scaled %.4f%s" % (placement["scale"], " (the wrap's placement)" if wrapped else ""))
best, pose = fit(base, rig, tripo_bvh, T_sample, start=wrap_record.get("pose"), refine=not wrapped, log=log)
co, _ = posed(base)
gap = np.array([tripo_bvh.find_nearest(Vector(p))[3] for p in co])
log("posed, her surface to the Tripo one: median %.1f mm, p90 %.1f, p99 %.1f, max %.1f" % tuple(
    np.percentile(gap, [50, 90, 99, 100]) * 1000))

# --- 4. the bake -----------------------------------------------------------------------------------------------------
dg = bpy.context.evaluated_depsgraph_get()
posed_mesh = bpy.data.meshes.new_from_object(base.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
posed_obj = bpy.data.objects.new("posed", posed_mesh)
posed_obj.matrix_world = base.matrix_world.copy()
scene.collection.objects.link(posed_obj)
image = bpy.data.images.new("%s_normal" % TYPE, MAP, MAP, alpha=False, float_buffer=False)
image.colorspace_settings.name = "Non-Color"
image.pixels.foreach_set(np.tile(np.array([0.5, 0.5, 1.0, 1.0], dtype=np.float32), MAP * MAP))
# the Tripo body baked from, its hands cut away: every vertex within HAND_CUT of her posed hands
hand_groups = {g.index for g in base.vertex_groups if g.name.startswith(("mixamorig:LeftHand", "mixamorig:RightHand"))}
hand_weight = np.array([sum(g.weight for g in v.groups if g.group in hand_groups) for v in base.data.vertices])
P_posed = np.array([posed_obj.matrix_world @ v.co for v in posed_mesh.vertices])
hand_tree = KDTree(len(P_posed))
for i in np.where(hand_weight > 0.3)[0]:
    hand_tree.insert(Vector(P_posed[i]), int(i))
hand_tree.balance()
source = tripo.copy()
source.data = tripo.data.copy()
source.name = "bake source"
scene.collection.objects.link(source)
bm = bmesh.new()
bm.from_mesh(source.data)
cut = [v for v in bm.verts if hand_tree.find_range(source.matrix_world @ v.co, HAND_CUT)]
bmesh.ops.delete(bm, geom=cut, context="VERTS")
bm.to_mesh(source.data)
bm.free()
log("bake source: %d of %d Tripo vertices cut as hands" % (len(cut), len(tripo.data.vertices)))
mat = bpy.data.materials.new("skin " + TYPE)
mat.use_nodes = True
nodes, links = mat.node_tree.nodes, mat.node_tree.links
tex = nodes.new("ShaderNodeTexImage")
tex.image = image
tex.interpolation = "Linear"
normal = nodes.new("ShaderNodeNormalMap")
links.new(tex.outputs["Color"], normal.inputs["Color"])
links.new(normal.outputs["Normal"], nodes["Principled BSDF"].inputs["Normal"])
nodes.active = tex
for o in (posed_obj, base):
    o.data.materials.clear()
    o.data.materials.append(mat)
    for p in o.data.polygons:
        p.use_smooth = True
for p in source.data.polygons:
    p.use_smooth = True
scene.render.engine = "CYCLES"
scene.cycles.samples = 1
scene.cycles.device = "CPU"
scene.render.bake.use_selected_to_active = True
scene.render.bake.cage_extrusion = CAGE
scene.render.bake.max_ray_distance = REACH
scene.render.bake.normal_space = "TANGENT"
scene.render.bake.margin = 16
bpy.ops.object.select_all(action="DESELECT")
source.select_set(True)
posed_obj.select_set(True)
bpy.context.view_layer.objects.active = posed_obj
log("baking %d x %d" % (MAP, MAP))
bpy.ops.object.bake(type="NORMAL")


# where the Tripo surface the ray found faces away from hers, it was the wrong surface: the baked normal's z (its
# blue) is the cosine of the angle between the two
pixels = np.empty(MAP * MAP * 4, dtype=np.float32)
image.pixels.foreach_get(pixels)
pixels = pixels.reshape(-1, 4)
angle = np.degrees(np.arccos(np.clip(pixels[:, 2] * 2 - 1, -1, 1)))
stray = np.clip((angle - STRAY_FROM) / (STRAY_FULL - STRAY_FROM), 0, 1)[:, None]
log("stray hits: %.1f%% of the map flattened" % (100 * stray.mean()))
# her hands and wrists: a mask baked on the same UV layout, 1 within HAND_CUT of her hands and fading out over
# HAND_FADE beyond, and the map blended to flat there (the rays there graze the cut and read it as a dark ring)
reach = np.array([hand_tree.find(Vector(p))[2] for p in P_posed])
weight = np.clip(1 - (reach - HAND_CUT) / HAND_FADE, 0, 1)
# and her breasts: their own kind, with maps of their own; the body's map leaves them her own relief, and the zone
# around them too (the Tripo chest's underside lies just outside the breast bones' reach), fading out beyond
breast_groups = {g.index for g in base.vertex_groups if g.name.startswith(("mixamorig:LeftBreast", "mixamorig:RightBreast"))}
breast_weight = np.array([sum(g.weight for g in v.groups if g.group in breast_groups) for v in base.data.vertices])
breast_tree = KDTree(int((breast_weight > 0.05).sum()))
for i in np.where(breast_weight > 0.05)[0]:
    breast_tree.insert(Vector(P_posed[i]), int(i))
breast_tree.balance()
near_breast = np.array([breast_tree.find(Vector(p))[2] for p in P_posed])
weight = np.maximum(weight, np.clip(1 - (near_breast - BREAST_CUT) / BREAST_FADE, 0, 1))
colour = posed_mesh.color_attributes.new("hand", "FLOAT_COLOR", "POINT")
colour.data.foreach_set("color", np.repeat(weight, 4).astype(np.float32).ravel())
mask_image = bpy.data.images.new("%s_hand_mask" % TYPE, MAP, MAP, alpha=False, float_buffer=False)
mask_image.colorspace_settings.name = "Non-Color"
mask_mat = bpy.data.materials.new("hand mask")
mask_mat.use_nodes = True
mn, ml = mask_mat.node_tree.nodes, mask_mat.node_tree.links
attr = mn.new("ShaderNodeVertexColor")
attr.layer_name = "hand"
emit = mn.new("ShaderNodeEmission")
ml.new(attr.outputs["Color"], emit.inputs["Color"])
ml.new(emit.outputs["Emission"], mn["Material Output"].inputs["Surface"])
mask_tex = mn.new("ShaderNodeTexImage")
mask_tex.image = mask_image
mn.active = mask_tex
posed_obj.data.materials[0] = mask_mat
scene.render.bake.use_selected_to_active = False
bpy.ops.object.select_all(action="DESELECT")
posed_obj.select_set(True)
bpy.ops.object.bake(type="EMIT")
mask = np.empty(MAP * MAP * 4, dtype=np.float32)
mask_image.pixels.foreach_get(mask)
mask = np.maximum(mask.reshape(-1, 4)[:, :1], stray)
pixels[:, :3] = pixels[:, :3] * (1 - mask) + np.array([0.5, 0.5, 1.0], dtype=np.float32) * mask
image.pixels.foreach_set(pixels.ravel())
log("hands and stray hits masked: %.1f%% of the map" % (100 * mask.mean()))
image_path = os.path.join(BUILD, "%s_normal.png" % TYPE)
image.filepath_raw = image_path
image.file_format = "PNG"
image.save()
image.filepath = image_path
image.source = "FILE"
log("baked", image_path)

# --- 5. the paint, when the Tripo body has it: its colour and roughness onto her UV ------------------------------------
# From the whole Tripo body (the hands too: fused fingers still have skin colour). The colour is the surface's own
# (the diffuse pass's colour alone, no light); a pixel no ray painted (black) takes the paint's median.
paint = {}
if tripo.data.materials and tripo.data.materials[0].use_nodes:
    for n in tripo.data.materials[0].node_tree.nodes:
        if n.type == "TEX_IMAGE" and n.image:
            for l in n.outputs[0].links:
                paint[l.to_socket.name] = n.image
maps = {"map": os.path.basename(image_path)}
if "Base Color" in paint:
    log("the Tripo body is painted: %s %dx%d%s" % (paint["Base Color"].name, *paint["Base Color"].size,
                                                   ", roughness too" if "Roughness" in paint else ""))
    for kind, size, space, bake_type in (("color", COLOUR_MAP, "sRGB", "DIFFUSE"), ("roughness", MAP, "Non-Color", "ROUGHNESS")):
        if kind == "roughness" and "Roughness" not in paint:
            continue
        target = bpy.data.images.new("%s_%s" % (TYPE, kind), size, size, alpha=False, float_buffer=False)
        target.colorspace_settings.name = space
        bake_mat = bpy.data.materials.new("bake " + kind)
        bake_mat.use_nodes = True
        node = bake_mat.node_tree.nodes.new("ShaderNodeTexImage")
        node.image = target
        bake_mat.node_tree.nodes.active = node
        posed_obj.data.materials[0] = bake_mat
        scene.render.bake.use_selected_to_active = True
        scene.render.bake.use_pass_direct = scene.render.bake.use_pass_indirect = False
        scene.render.bake.use_pass_color = True
        bpy.ops.object.select_all(action="DESELECT")
        tripo.select_set(True)
        posed_obj.select_set(True)
        bpy.context.view_layer.objects.active = posed_obj
        log("baking %s %d x %d" % (kind, size, size))
        bpy.ops.object.bake(type=bake_type)
        px = np.empty(size * size * 4, dtype=np.float32)
        target.pixels.foreach_get(px)
        px = px.reshape(-1, 4)
        miss = px[:, :3].sum(1) < 0.02
        px[miss, :3] = np.median(px[~miss, :3], axis=0)
        px[:, 3] = 1.0
        target.pixels.foreach_set(px.ravel())
        log("%s: %.1f%% of the map unpainted, filled with the median %s" % (kind, 100 * miss.mean(), np.round(px[~miss, :3].mean(0), 3).tolist()))
        path = os.path.join(BUILD, "%s_%s.png" % (TYPE, kind))
        target.filepath_raw = path
        target.file_format = "PNG"
        target.save()
        maps[kind] = os.path.basename(path)
        bpy.data.images.remove(target)
        del px
        log("baked", path)

# --- the file to look at: her at rest, the map on, the Tripo body beside her -----------------------------------------
bpy.data.objects.remove(posed_obj)
bpy.data.objects.remove(source)
for pb in rig.pose.bones:
    pb.rotation_euler = (0, 0, 0)
tripo.location.x += 0.8
for o in (base, tripo):
    for p in o.data.polygons:
        p.use_smooth = True
with open(os.path.join(HERE, "checks", "detail_%s.json" % TYPE), "w") as f:
    json.dump({"type": TYPE, "pose_fit_cost": best, "pose": pose, "wrapped": wrapped, **maps,
               "gap_mm": {"median": round(float(np.median(gap)) * 1000, 1),
                          "p90": round(float(np.percentile(gap, 90)) * 1000, 1),
                          "max": round(float(gap.max()) * 1000, 1)}}, f, indent=1)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(BUILD, "detail_%s.blend" % TYPE))

# pictures: Eevee, one sun from the front left, torso close-up and whole
scene.render.engine = "BLENDER_EEVEE"
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 3.0
sun.rotation_euler = (np.radians(60), 0, np.radians(-30))
scene.collection.objects.link(sun)
world = bpy.data.worlds.new("w")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.15, 0.15, 0.15, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.6
scene.world = world
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
scene.collection.objects.link(cam)
scene.camera = cam
scene.render.resolution_x, scene.render.resolution_y = 1600, 1000
cam.rotation_euler = (1.5708, 0, 0)
for name, scale, z in (("torso", 1.0, ground + 0.65 * height), ("whole", 2.0, ground + height / 2), ("side", 1.0, ground + 0.65 * height)):
    cam.data.ortho_scale = scale
    cam.location = (0.4, -10, z)
    if name == "side":  # her right side, the Tripo body hidden behind her
        cam.location = (10, 0, z)
        cam.rotation_euler = (1.5708, 0, 1.5708)
    scene.render.filepath = os.path.join(HERE, "checks", "detail_%s_%s.png" % (TYPE, name))
    bpy.ops.render.render(write_still=True)
log("done")
