"""A Tripo body type's surface detail baked onto the fitted MPFB body as a normal map.

    blender -b -P bake_detail.py -- <tripo file> <type name>

1. The MPFB female at the sliders in checks/fit_<type>.json (fit_macros.py), the mixamo_unity rig, helpers dropped.
2. The Tripo body at her height, its trunk over hers.
3. Pose fit: her bones turned until she lies on the Tripo body (coordinate descent, from checks/wrap_<type>.json's
   pose when there is one). Her shape is not touched.
4. Cycles bakes the Tripo surface's normals, tangent space, onto a posed copy of her (same mesh, same UVs);
   the map then shows on her in rest pose. The Tripo hands are cut off the copy baked from (they hang before
   the hips and their fingers are fused); the map starts flat, and is blended back to flat over her hands and
   wrists (a mask baked on the same UVs), so there she keeps her own relief.

Writes build/<type>_normal.png (4096 square), build/detail_<type>.blend (her at rest with the map, the Tripo body
beside her), checks/detail_<type>.json (pose, fit cost), checks/detail_<type>_*.png.
"""
import bpy, json, os, sys, time
import numpy as np
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree
from bl_ext.blender_org.mpfb.services.humanservice import HumanService
from bl_ext.blender_org.mpfb.services.targetservice import TargetService
from bl_ext.blender_org.mpfb.services.locationservice import LocationService

ARGS = sys.argv[sys.argv.index("--") + 1:]
SOURCE, TYPE = ARGS[0], ARGS[1]
HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build")
os.makedirs(BUILD, exist_ok=True)
MACRO = ["weight", "muscle", "proportions", "cupsize", "firmness"]
FOLDER = {"measure-bust-circ": "torso", "measure-underbust-circ": "torso", "measure-waist-circ": "torso",
          "measure-hips-circ": "torso", "torso-scale-depth": "torso", "torso-scale-horiz": "torso",
          "torso-vshape": "torso", "hip-scale-depth": "hip", "hip-scale-horiz": "hip",
          "stomach-pregnant": "stomach", "buttocks-volume": "buttocks", "breast-volume-vert": "breast"}
ENDS = {"breast-volume-vert": ("down", "up")}
MAP = 4096
HAND_CUT = 0.04  # m around her posed hands the Tripo body is cut away before the bake
HAND_FADE = 0.05  # m beyond HAND_CUT over which the map fades from her own relief back to the Tripo one
CAGE, REACH = 0.05, 0.12  # the bake rays start CAGE outside her and run REACH inward
T0 = time.time()


def log(*a):
    print("[%6.1fs]" % (time.time() - T0), *a, flush=True)


bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
TARGETS = LocationService.get_mpfb_data("targets")

# --- 1. the fitted MPFB body ----------------------------------------------------------------------------------------
fit = json.load(open(os.path.join(HERE, "checks", "fit_%s.json" % TYPE)))["values"]
macro = TargetService.get_default_macro_info_dict()
macro.update({"gender": 0.0, "age": 0.5})
macro["race"] = {"asian": 0.0, "caucasian": 1.0, "african": 0.0}
macro.update({k: fit[k] for k in MACRO})
base = HumanService.create_human(mask_helpers=True, macro_detail_dict=macro)
for slider, value in fit.items():
    if slider in MACRO or abs(value) < 1e-3:
        continue
    decr, incr = ENDS.get(slider, ("decr", "incr"))
    end = incr if value > 0 else decr
    folder = FOLDER.get(slider, "arms" if "arm" in slider else "legs")
    sided = os.path.exists(os.path.join(TARGETS, folder, "l-%s-%s.target.gz" % (slider, end)))
    for side in (["l-", "r-"] if sided else [""]):
        TargetService.load_target(base, os.path.join(TARGETS, folder, "%s%s-%s.target.gz" % (side, slider, end)),
                                  weight=abs(value))
rig = HumanService.add_builtin_rig(base, "mixamo_unity")
for m in base.modifiers:
    if m.type == "ARMATURE":
        m.show_viewport = False
dg = bpy.context.evaluated_depsgraph_get()
baked = bpy.data.meshes.new_from_object(base.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
base.shape_key_clear()
base.modifiers.clear()
base.data = baked
mod = base.modifiers.new("Armature", "ARMATURE")
mod.object = rig
base.name, rig.name = "MPFB " + TYPE, "rig " + TYPE
N = len(base.data.vertices)
bpy.context.view_layer.update()
rest_world = np.array([base.matrix_world @ v.co for v in base.data.vertices])
height = rest_world[:, 2].max() - rest_world[:, 2].min()
ground = rest_world[:, 2].min()
log("mpfb", N, "vertices, %.3f m" % height)

# --- 2. the Tripo body -----------------------------------------------------------------------------------------------
before = set(scene.objects)
if SOURCE.endswith(".glb"):
    bpy.ops.import_scene.gltf(filepath=SOURCE)
else:
    bpy.ops.import_scene.fbx(filepath=SOURCE)
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
tripo.name = "Tripo " + TYPE
T = np.array([v.co for v in tripo.data.vertices])
k = height / (T[:, 2].max() - T[:, 2].min())
T = (T - [0, 0, T[:, 2].min()]) * k + [0, 0, ground]
band = lambda P: P[(P[:, 2] > ground + 0.45 * height) & (P[:, 2] < ground + 0.75 * height) & (np.abs(P[:, 0]) < 0.15)]
T[:, :2] += band(rest_world)[:, :2].mean(0) - band(T)[:, :2].mean(0)
tripo.data.vertices.foreach_set("co", T.ravel())
tripo.data.update()
tripo_bvh = BVHTree.FromObject(tripo, bpy.context.evaluated_depsgraph_get())
rng = np.random.default_rng(1)
T_sample = T[rng.choice(len(T), min(4500, len(T)), replace=False)]
log("tripo", len(T), "vertices")


# --- 3. pose fit -----------------------------------------------------------------------------------------------------
def posed():
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = base.evaluated_get(dg)
    co = np.empty(N * 3)
    ev.data.vertices.foreach_get("co", co)
    mw = np.array(base.matrix_world)
    return co.reshape(N, 3) @ mw[:3, :3].T + mw[:3, 3], BVHTree.FromObject(base, dg)


EVERY = np.arange(0, N, 3)


def cost():
    co, bvh = posed()
    there = sum(min(h[3], 0.08) ** 2 if h[0] else 0.0064 for h in (tripo_bvh.find_nearest(Vector(p)) for p in co[EVERY]))
    back = sum(min(h[3], 0.08) ** 2 if h[0] else 0.0064 for h in (bvh.find_nearest(Vector(p)) for p in T_sample))
    return there / len(EVERY) + back / len(T_sample)


FIT = ["Hips", "Spine", "Spine1", "Spine2", "Neck", "Head", "LeftShoulder", "RightShoulder", "LeftArm", "RightArm",
       "LeftForeArm", "RightForeArm", "LeftHand", "RightHand", "LeftUpLeg", "RightUpLeg", "LeftLeg", "RightLeg",
       "LeftFoot", "RightFoot"]
NO_TWIST = {"Spine", "Spine1", "Spine2", "Neck", "LeftArm", "RightArm", "LeftForeArm", "RightForeArm",
            "LeftUpLeg", "RightUpLeg", "LeftLeg", "RightLeg"}
for pb in rig.pose.bones:
    pb.rotation_mode = "XYZ"
start_pose = os.path.join(HERE, "checks", "wrap_%s.json" % TYPE)
if os.path.exists(start_pose):
    for name, angles in json.load(open(start_pose))["pose"].items():
        rig.pose.bones[name].rotation_euler = [np.radians(a) for a in angles]
    first_step = 2.0
else:
    first_step = 8.0
best = cost()
log("pose fit: start cost %.6f" % best)
step = np.radians(first_step)
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
pose = {pb.name: [round(np.degrees(a), 1) for a in pb.rotation_euler] for pb in rig.pose.bones
        if any(abs(a) > 1e-6 for a in pb.rotation_euler)}
co, _ = posed()
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
# her hands and wrists: a mask baked on the same UV layout, 1 within HAND_CUT of her hands and fading out over
# HAND_FADE beyond, and the map blended to flat there (the rays there graze the cut and read it as a dark ring)
reach = np.array([hand_tree.find(Vector(p))[2] for p in P_posed])
weight = np.clip(1 - (reach - HAND_CUT) / HAND_FADE, 0, 1)
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
pixels = np.empty(MAP * MAP * 4, dtype=np.float32)
image.pixels.foreach_get(pixels)
pixels = pixels.reshape(-1, 4)
mask = np.empty(MAP * MAP * 4, dtype=np.float32)
mask_image.pixels.foreach_get(mask)
mask = mask.reshape(-1, 4)[:, :1]
pixels[:, :3] = pixels[:, :3] * (1 - mask) + np.array([0.5, 0.5, 1.0], dtype=np.float32) * mask
image.pixels.foreach_set(pixels.ravel())
log("hands masked: %.1f%% of the map" % (100 * mask.mean()))
image_path = os.path.join(BUILD, "%s_normal.png" % TYPE)
image.filepath_raw = image_path
image.file_format = "PNG"
image.save()
image.filepath = image_path
image.source = "FILE"
log("baked", image_path)

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
    json.dump({"type": TYPE, "pose_fit_cost": best, "pose": pose, "map": os.path.basename(image_path),
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
for name, scale, z in (("torso", 1.0, ground + 0.65 * height), ("whole", 2.0, ground + height / 2)):
    cam.data.ortho_scale = scale
    cam.location = (0.4, -10, z)
    scene.render.filepath = os.path.join(HERE, "checks", "detail_%s_%s.png" % (TYPE, name))
    bpy.ops.render.render(write_still=True)
log("done")
