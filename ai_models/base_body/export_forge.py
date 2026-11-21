"""The fitted MPFB body exported for Forge: <Title>.fbx (the mesh "Body" on the mixamo_unity rig, feet at the
origin, metres, facing -Y as Forge's other bodies do), <Title>_Color.png (a flat skin for now), <Title>_Normal.png
(bake_detail.py's map).

    blender -b -P export_forge.py -- <type name> <Title>

Writes build/forge/<Title>/. Settings as ai_models/pieces.py's export().
"""
import bpy, json, os, shutil, sys
import numpy as np
from bl_ext.blender_org.mpfb.services.humanservice import HumanService
from bl_ext.blender_org.mpfb.services.targetservice import TargetService
from bl_ext.blender_org.mpfb.services.locationservice import LocationService

ARGS = sys.argv[sys.argv.index("--") + 1:]
TYPE, TITLE = ARGS[0], ARGS[1]
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "build", "forge", TITLE)
os.makedirs(OUT, exist_ok=True)
MACRO = ["weight", "muscle", "proportions", "cupsize", "firmness"]
FOLDER = {"measure-bust-circ": "torso", "measure-underbust-circ": "torso", "measure-waist-circ": "torso",
          "measure-hips-circ": "torso", "torso-scale-depth": "torso", "torso-scale-horiz": "torso",
          "torso-vshape": "torso", "hip-scale-depth": "hip", "hip-scale-horiz": "hip",
          "stomach-pregnant": "stomach", "buttocks-volume": "buttocks", "breast-volume-vert": "breast"}
ENDS = {"breast-volume-vert": ("down", "up")}
SKIN = (0.80, 0.62, 0.52)  # a flat skin until MPFB's own skin is wired in

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
TARGETS = LocationService.get_mpfb_data("targets")

fit = json.load(open(os.path.join(HERE, "checks", "fit_%s.json" % TYPE)))["values"]
macro = TargetService.get_default_macro_info_dict()
macro.update({"gender": 0.0, "age": 0.5})
macro["race"] = {"asian": 0.0, "caucasian": 1.0, "african": 0.0}
macro.update({k: fit[k] for k in MACRO})
body = HumanService.create_human(mask_helpers=True, macro_detail_dict=macro)
for slider, value in fit.items():
    if slider in MACRO or abs(value) < 1e-3:
        continue
    decr, incr = ENDS.get(slider, ("decr", "incr"))
    end = incr if value > 0 else decr
    folder = FOLDER.get(slider, "arms" if "arm" in slider else "legs")
    sided = os.path.exists(os.path.join(TARGETS, folder, "l-%s-%s.target.gz" % (slider, end)))
    for side in (["l-", "r-"] if sided else [""]):
        TargetService.load_target(body, os.path.join(TARGETS, folder, "%s%s-%s.target.gz" % (side, slider, end)),
                                  weight=abs(value))
rig = HumanService.add_builtin_rig(body, "mixamo_unity")
for m in body.modifiers:
    if m.type == "ARMATURE":
        m.show_viewport = False
dg = bpy.context.evaluated_depsgraph_get()
baked = bpy.data.meshes.new_from_object(body.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
body.shape_key_clear()
body.modifiers.clear()
body.data = baked
mod = body.modifiers.new("Armature", "ARMATURE")
mod.object = rig
body.name = body.data.name = "Body"
rig.name = TITLE
for p in body.data.polygons:
    p.use_smooth = True
bpy.context.view_layer.update()
P = np.array([body.matrix_world @ v.co for v in body.data.vertices])
print("body %d vertices, %.3f m tall, feet at %.3f, faces -Y: front at y=%.3f back at y=%.3f" % (
    len(P), P[:, 2].max() - P[:, 2].min(), P[:, 2].min(), P[:, 1].min(), P[:, 1].max()), flush=True)

# the maps and the material, its slot named for them
colour = bpy.data.images.new(TITLE + "_Color", 256, 256)
colour.pixels.foreach_set(np.tile(np.array([*SKIN, 1.0], dtype=np.float32), 256 * 256))
colour.filepath_raw = os.path.join(OUT, TITLE + "_Color.png")
colour.file_format = "PNG"
colour.save()
shutil.copyfile(os.path.join(HERE, "build", "%s_normal.png" % TYPE), os.path.join(OUT, TITLE + "_Normal.png"))
mat = bpy.data.materials.new(TITLE)
mat.use_nodes = True
body.data.materials.clear()
body.data.materials.append(mat)

bpy.ops.object.select_all(action="DESELECT")
body.select_set(True)
rig.select_set(True)
path = os.path.join(OUT, TITLE + ".fbx")
bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={"ARMATURE", "MESH"}, apply_unit_scale=True,
                         apply_scale_options="FBX_SCALE_ALL", add_leaf_bones=False, bake_anim=False,
                         mesh_smooth_type="FACE", path_mode="STRIP")
print("wrote", path, "%d bones" % len(rig.data.bones), flush=True)
