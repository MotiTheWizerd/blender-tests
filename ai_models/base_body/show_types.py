"""The four fitted body types in one .blend to look at: each a live MPFB human (its sliders in MPFB's panels) with
its Tripo body beside it, scaled to the same height.

    blender -b -P show_types.py

Reads checks/fit_<type>.json (fit_macros.py). Writes build/body_types.blend.
"""
import bpy, json, os
import numpy as np
from bl_ext.blender_org.mpfb.services.humanservice import HumanService
from bl_ext.blender_org.mpfb.services.targetservice import TargetService
from bl_ext.blender_org.mpfb.services.locationservice import LocationService

HERE = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")
TYPES = [("skinny", "5ab2e08e-3991-416c-8b42-f0e1196ab270.fbx"), ("fit", "c6966c04-6702-4554-b5d2-b20849af1d24.glb"),
         ("built", "b7f39db5-cd1d-43bb-b2c5-0e768aa5a3db.fbx"), ("overweight", "2d2dda91-5b56-42c5-a992-6c2a4d8e24be.fbx")]
MACRO = ["weight", "muscle", "proportions", "cupsize", "firmness"]
# the detail sliders' folders and ends, as fit_macros.py has them
FOLDER = {"measure-bust-circ": "torso", "measure-underbust-circ": "torso", "measure-waist-circ": "torso",
          "measure-hips-circ": "torso", "torso-scale-depth": "torso", "torso-scale-horiz": "torso",
          "torso-vshape": "torso", "hip-scale-depth": "hip", "hip-scale-horiz": "hip",
          "stomach-pregnant": "stomach", "buttocks-volume": "buttocks", "breast-volume-vert": "breast"}
ENDS = {"breast-volume-vert": ("down", "up")}
SPACING = 1.8  # m between types; each Tripo body stands 0.8 m to the right of its MPFB one

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
TARGETS = LocationService.get_mpfb_data("targets")


def body_extent(obj):
    """Lowest and highest z of the visible body (MPFB's helpers left out)."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    P = np.array([ev.matrix_world @ v.co for v in me.vertices])
    ev.to_mesh_clear()
    return P[:, 2].min(), P[:, 2].max()


def label(text, x):
    curve = bpy.data.curves.new(text, "FONT")
    curve.body = text
    curve.size = 0.12
    curve.align_x = "CENTER"
    obj = bpy.data.objects.new("label " + text, curve)
    obj.location = (x + 0.4, 0, 1.95)
    obj.rotation_euler = (1.5708, 0, 0)
    scene.collection.objects.link(obj)


for i, (name, source) in enumerate(TYPES):
    fit = json.load(open(os.path.join(HERE, "checks", "fit_%s.json" % name)))["values"]
    x0 = i * SPACING

    macro = TargetService.get_default_macro_info_dict()
    macro.update({"gender": 0.0, "age": 0.5})
    macro["race"] = {"asian": 0.0, "caucasian": 1.0, "african": 0.0}
    macro.update({k: fit[k] for k in MACRO})
    human = HumanService.create_human(mask_helpers=True, macro_detail_dict=macro)
    for slider, value in fit.items():
        if slider in MACRO or abs(value) < 1e-3:
            continue
        decr, incr = ENDS.get(slider, ("decr", "incr"))
        end = incr if value > 0 else decr
        folder = FOLDER.get(slider, "arms" if "arm" in slider else "legs")
        sided = os.path.exists(os.path.join(TARGETS, folder, "l-%s-%s.target.gz" % (slider, end)))
        for side in (["l-", "r-"] if sided else [""]):
            TargetService.load_target(human, os.path.join(TARGETS, folder, "%s%s-%s.target.gz" % (side, slider, end)),
                                      weight=abs(value))
    human.name = "MPFB " + name
    human.location.x += x0
    bpy.context.view_layer.update()
    lo, hi = body_extent(human)

    before = set(scene.objects)
    path = os.path.join(DOWNLOADS, source)
    if path.endswith(".glb"):
        bpy.ops.import_scene.gltf(filepath=path)
    else:
        bpy.ops.import_scene.fbx(filepath=path)
    new = [o for o in scene.objects if o not in before]
    tripo = [o for o in new if o.type == "MESH"][0]
    bpy.context.view_layer.update()
    P = np.array([tripo.matrix_world @ v.co for v in tripo.data.vertices])
    k = (hi - lo) / (P[:, 2].max() - P[:, 2].min())
    c = np.array([(P[:, 0].min() + P[:, 0].max()) / 2, (P[:, 1].min() + P[:, 1].max()) / 2, P[:, 2].min()])
    P = (P - c) * k + np.array([x0 + 0.8, 0, lo])
    tripo.parent = None
    tripo.matrix_world.identity()
    tripo.data.vertices.foreach_set("co", P.ravel())
    tripo.data.update()
    tripo.name = "Tripo " + name
    for o in new:
        if o is not tripo:
            bpy.data.objects.remove(o, do_unlink=True)
    label(name, x0)
    print(name, "height %.3f m" % (hi - lo), flush=True)

os.makedirs(os.path.join(HERE, "build"), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "build", "body_types.blend"))
