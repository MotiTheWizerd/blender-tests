"""Spike, step 1a: MPFB's female base beside a Tripo body type, both at 1.70 m, to compare pose and proportions.

    blender -b -P spike_compare.py -- <tripo file>

Writes checks/compare_front.png and checks/compare_side.png (base left, Tripo right, and both overlaid in the middle),
and prints landmarks as fractions of height.
"""
import bpy, json, os, sys
from mathutils import Vector
from bl_ext.blender_org.mpfb.services.humanservice import HumanService
from bl_ext.blender_org.mpfb.services.targetservice import TargetService

SOURCE = sys.argv[sys.argv.index("--") + 1]
HERE = os.path.dirname(os.path.abspath(__file__))
HEIGHT = 1.70

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

macro = TargetService.get_default_macro_info_dict()
macro.update({"gender": 0.0, "age": 0.5, "muscle": 0.5, "weight": 0.5})
macro["race"] = {"asian": 0.0, "caucasian": 1.0, "african": 0.0}
base = HumanService.create_human(mask_helpers=True, macro_detail_dict=macro)
# bake the targets and drop the helpers, so the base is its body alone
depsgraph = bpy.context.evaluated_depsgraph_get()
baked = bpy.data.meshes.new_from_object(base.evaluated_get(depsgraph))
base.modifiers.clear()
base.shape_key_clear()
base.data = baked
base.name = "base"

before = set(scene.objects)
if SOURCE.endswith(".glb"):
    bpy.ops.import_scene.gltf(filepath=SOURCE)
else:
    bpy.ops.import_scene.fbx(filepath=SOURCE)
tripo = [o for o in scene.objects if o not in before and o.type == "MESH"][0]
bpy.context.view_layer.update()
bpy.ops.object.select_all(action="DESELECT")
tripo.select_set(True)
bpy.context.view_layer.objects.active = tripo
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
tripo.parent = None
tripo.name = "tripo"


def fit(o):
    """Feet on the ground, centred, HEIGHT tall."""
    pts = [v.co for v in o.data.vertices]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    k = HEIGHT / (hi.z - lo.z)
    c = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    for v in o.data.vertices:
        v.co = (v.co - c) * k


def marks(o):
    pts = [v.co for v in o.data.vertices]
    hx = max(p.x for p in pts)
    tip = min((p for p in pts if p.x > 0.75 * hx), key=lambda p: p.z)
    # shoulder: the highest point of the arm, out past the neck
    shoulder = max((p for p in pts if 0.10 < p.x < 0.22), key=lambda p: p.z)
    widths = {}
    for name, z in (("chest", 0.72), ("waist", 0.62), ("hips", 0.52), ("thigh", 0.42), ("knee", 0.28)):
        band = [p for p in pts if abs(p.z - z * HEIGHT) < 0.01 and abs(p.x) < (0.17 if z < 0.6 else 0.16)]
        widths[name] = round(max(p.x for p in band) - min(p.x for p in band), 3) if band else None
        widths[name + "_depth"] = round(max(p.y for p in band) - min(p.y for p in band), 3) if band else None
    return {"span": round(2 * hx, 3), "hand_tip": [round(tip.x, 3), round(tip.z, 3)],
            "shoulder_top": [round(shoulder.x, 3), round(shoulder.z, 3)], **widths, "vertices": len(pts)}


fit(base)
fit(tripo)
print("MARKS " + json.dumps({"base": marks(base), "tripo": marks(tripo)}))

# the pictures: base at -0.8, both at 0, tripo at +0.8
over_b = base.copy(); over_b.data = base.data.copy(); scene.collection.objects.link(over_b)
over_t = tripo.copy(); over_t.data = tripo.data.copy(); scene.collection.objects.link(over_t)
base.location.x, tripo.location.x = -0.9, 0.9


def material(name, rgba):
    m = bpy.data.materials.new(name)
    m.diffuse_color = rgba
    return m


for o, m in ((base, material("b", (0.55, 0.65, 0.85, 1))), (over_b, material("b2", (0.55, 0.65, 0.85, 1))),
             (tripo, material("t", (0.85, 0.6, 0.5, 1))), (over_t, material("t2", (0.85, 0.6, 0.5, 0.45)))):
    o.data.materials.clear()
    o.data.materials.append(m)

scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "MATERIAL"
scene.display.shading.show_xray = False
scene.render.resolution_x, scene.render.resolution_y = 1800, 1000
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
cam.data.ortho_scale = 3.0
scene.collection.objects.link(cam)
scene.camera = cam
cam.location, cam.rotation_euler = (0, -10, 0.85), (1.5708, 0, 0)
scene.render.filepath = os.path.join(HERE, "checks", "compare_front.png")
bpy.ops.render.render(write_still=True)
for o in (base, tripo):
    o.rotation_euler.z = -1.5708
for o in (over_b, over_t):
    o.rotation_euler.z = -1.5708
scene.render.filepath = os.path.join(HERE, "checks", "compare_side.png")
bpy.ops.render.render(write_still=True)
