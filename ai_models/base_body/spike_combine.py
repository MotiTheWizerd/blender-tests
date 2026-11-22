"""Spike, step 1c: one base, every wrapped type a shape key of it.

    blender -b -P spike_combine.py -- skinny=<tripo file> fit=<tripo file> ...

Reads build/shape_<type>.npy (spike_wrap.py), writes build/base_types.blend (the base, its rig, a key per type) and
checks/types_front.png and checks/types_side.png: top row the base and each type at rest, bottom row the Tripo sources.
"""
import bpy, os, sys
import numpy as np
from bl_ext.blender_org.mpfb.services.humanservice import HumanService
from bl_ext.blender_org.mpfb.services.targetservice import TargetService

PAIRS = [a.split("=", 1) for a in sys.argv[sys.argv.index("--") + 1:]]
HERE = os.path.dirname(os.path.abspath(__file__))

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
macro = TargetService.get_default_macro_info_dict()
macro.update({"gender": 0.0, "age": 0.5, "muscle": 0.5, "weight": 0.5})
macro["race"] = {"asian": 0.0, "caucasian": 1.0, "african": 0.0}
base = HumanService.create_human(mask_helpers=True, macro_detail_dict=macro)
rig = HumanService.add_builtin_rig(base, "mixamo_unity")
for m in base.modifiers:
    if m.type == "ARMATURE":
        m.show_viewport = False
dg = bpy.context.evaluated_depsgraph_get()
baked = bpy.data.meshes.new_from_object(base.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
base.shape_key_clear()
base.modifiers.clear()
base.data = baked
base.modifiers.new("Armature", "ARMATURE").object = rig
base.name, rig.name = "base", "rig"
N = len(base.data.vertices)

base.shape_key_add(name="Basis")
for name, _ in PAIRS:
    co = np.load(os.path.join(HERE, "build", "shape_%s.npy" % name))
    assert co.shape == (N, 3), (name, co.shape, N)
    key = base.shape_key_add(name=name.capitalize())
    key.data.foreach_set("co", co.ravel())
    key.value = 0.0
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "build", "base_types.blend"))

# --- pictures ----------------------------------------------------------------------------------------------------------
bpy.context.view_layer.update()
world = np.array([base.matrix_world @ v.co for v in base.data.vertices])
ground, height = world[:, 2].min(), world[:, 2].max() - world[:, 2].min()
blue = bpy.data.materials.new("blue"); blue.diffuse_color = (0.55, 0.65, 0.85, 1)
clay = bpy.data.materials.new("clay"); clay.diffuse_color = (0.85, 0.6, 0.5, 1)
keys = base.data.shape_keys.key_blocks
row = [None] + [n.capitalize() for n, _ in PAIRS]
STEP = 0.95
shown = []
for i, name in enumerate(row):
    for k in keys[1:]:
        k.value = 1.0 if k.name == name else 0.0
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(base.evaluated_get(dg), depsgraph=dg)
    me.transform(base.matrix_world)
    me.materials.clear(); me.materials.append(blue)
    o = bpy.data.objects.new("shown_%s" % (name or "base"), me)
    scene.collection.objects.link(o)
    o.location = ((i - (len(row) - 1) / 2) * STEP, 0, 0)
    shown.append(o)
for i, (name, path) in enumerate(PAIRS, start=1):
    before = set(scene.objects)
    if path.endswith(".glb"):
        bpy.ops.import_scene.gltf(filepath=path)
    else:
        bpy.ops.import_scene.fbx(filepath=path)
    t = [o for o in scene.objects if o not in before and o.type == "MESH"][0]
    for o in scene.objects:
        if o not in before and o is not t:
            bpy.data.objects.remove(o)
    mw = t.matrix_world.copy()
    t.parent = None
    me = t.data
    me.transform(mw)
    t.matrix_world.identity()
    T = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", T); T = T.reshape(-1, 3)
    k = height / (T[:, 2].max() - T[:, 2].min())
    T = (T - [(T[:, 0].max() + T[:, 0].min()) / 2, (T[:, 1].max() + T[:, 1].min()) / 2, T[:, 2].min()]) * k
    me.vertices.foreach_set("co", T.ravel()); me.update()
    me.materials.clear(); me.materials.append(clay)
    t.location = ((i - (len(row) - 1) / 2) * STEP, 0, ground - height - 0.1)
    shown.append(t)
base.hide_render = rig.hide_render = True

scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "MATERIAL"
scene.render.resolution_x, scene.render.resolution_y = 2000, 1500
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
cam.data.ortho_scale = len(row) * STEP + 0.1
scene.collection.objects.link(cam)
scene.camera = cam
cam.location, cam.rotation_euler = (0, -10, ground - 0.05), (1.5708, 0, 0)
scene.render.filepath = os.path.join(HERE, "checks", "types_front.png")
bpy.ops.render.render(write_still=True)
for o in shown:
    o.rotation_euler.z = -1.5708
scene.render.filepath = os.path.join(HERE, "checks", "types_side.png")
bpy.ops.render.render(write_still=True)
print("COMBINED", [k.name for k in keys])
