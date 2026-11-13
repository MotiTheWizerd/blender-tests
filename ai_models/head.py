"""A head for Forge's face editor: a Tripo bust (bald, neutral, symmetric), at a real head's size, exported for Forge.

    blender -b --factory-startup -P head.py -- head_warrior_m WarriorM

Reads <name>/source_tripo.fbx (and its .fbm textures), finds the chin and the crown on the face's middle line, scales
the bust so they are HEAD_HEIGHT apart (an adult's chin to crown), and writes build/forge/<Title>/: <Title>.fbx
(metres, front to Unity's +Z, as export.py), <Title>_BaseColor.jpg, <Title>_Normal.png and
<Title>_MetallicSmoothness.png (no metal: skin; smoothness = (1 - roughness) * SKIN_SHINE), the maps at MAP_SIZE. checks/head.json
says what was measured.
"""
import bpy, json, os, sys
import numpy as np
from mathutils import Vector

NAME, TITLE = sys.argv[sys.argv.index("--") + 1:][:2]
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, NAME)
OUT = os.path.join(ROOT, "build", "forge", TITLE)
HEAD_HEIGHT = 0.232  # chin to crown, an adult man's
MAP_SIZE = 4096
SKIN_SHINE = 0.6  # Tripo's roughness read as URP smoothness looks wet (oily lips and brow): skin shines this much of it

os.makedirs(OUT, exist_ok=True)
os.makedirs(os.path.join(ROOT, "checks"), exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=os.path.join(ROOT, "source_tripo.fbx"))
head = next(o for o in bpy.context.scene.objects if o.type == "MESH")
bpy.context.view_layer.objects.active = head
head.select_set(True)
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

co = np.array([v.co[:] for v in head.data.vertices])
width = co[:, 0].max() - co[:, 0].min()
crown = co[:, 2].max()

# The face's middle line seen from the side: the frontmost point (least y: Tripo's front is -Y) in each 1% of the
# height (about 1 cm of a bust; finer slices of the 4% strip are often empty).
middle = co[np.abs(co[:, 0] - (co[:, 0].max() + co[:, 0].min()) / 2) < width * 0.02]
step = (crown - co[:, 2].min()) / 100
bins = {}
for x, y, z in middle:
    k = int(z / step)
    bins[k] = min(bins.get(k, 1e9), y)
levels = sorted(bins)
nose = min(levels, key=lambda k: bins[k] if k * step > co[:, 2].min() + 0.3 * (crown - co[:, 2].min()) else 1e9)
# Down from the nose tip: the chin's underside is where the profile falls back toward the neck the most over 3%
# of the height (the lips recess too, but less).
reach = int(0.4 * (crown - co[:, 2].min()) / step)
below = [k for k in levels if nose - reach < k < nose and bins.get(k - 3) is not None]
chin_k = max(below, key=lambda k: bins[k - 3] - bins[k])
chin = chin_k * step
scale = HEAD_HEIGHT / (crown - chin)
print(f"crown {crown:.4f} chin {chin:.4f} nose {nose * step:.4f} -> scale {scale:.4f}")

head.scale = (scale,) * 3
bpy.ops.object.transform_apply(scale=True)
co = np.array([v.co[:] for v in head.data.vertices])
head.location = Vector((-(co[:, 0].max() + co[:, 0].min()) / 2, -(co[:, 1].max() + co[:, 1].min()) / 2, -co[:, 2].min()))
bpy.ops.object.transform_apply(location=True)
head.name = head.data.name = TITLE


def image_of(label):
    """The texture behind the material's socket <label> (Base Color, Normal, Roughness)."""
    nodes = head.active_material.node_tree.nodes
    bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
    link = bsdf.inputs[label].links[0] if bsdf.inputs[label].links else None
    node = link.from_node if link else None
    while node is not None and node.type != "TEX_IMAGE":
        node = next((i.links[0].from_node for i in node.inputs if i.links), None)
    return node.image


def pixels(image, size):
    copy = image.copy()
    copy.scale(size, size)
    array = np.array(copy.pixels[:], dtype=np.float32).reshape(size, size, copy.channels)
    bpy.data.images.remove(copy)
    return array


def save(array, path, fmt, alpha):
    size = array.shape[0]
    image = bpy.data.images.new(os.path.basename(path), size, size, alpha=alpha)
    image.colorspace_settings.name = "Non-Color" if fmt == "PNG" else "sRGB"
    image.pixels = array.ravel()
    image.filepath_raw = path
    image.file_format = fmt
    if fmt == "JPEG":
        bpy.context.scene.render.image_settings.quality = 92
    image.save()


base = pixels(image_of("Base Color"), MAP_SIZE)
base[..., 3] = 1.0
save(base, os.path.join(OUT, f"{TITLE}_BaseColor.jpg"), "JPEG", False)
save(pixels(image_of("Normal"), MAP_SIZE), os.path.join(OUT, f"{TITLE}_Normal.png"), "PNG", False)
rough = pixels(image_of("Roughness"), MAP_SIZE)
ms = np.zeros_like(rough)
ms[..., 3] = (1.0 - rough[..., 0]) * SKIN_SHINE
save(ms, os.path.join(OUT, f"{TITLE}_MetallicSmoothness.png"), "PNG", True)

bpy.ops.object.select_all(action="DESELECT")
head.select_set(True)
bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, f"{TITLE}.fbx"), use_selection=True, object_types={"MESH"},
                         apply_unit_scale=True, apply_scale_options="FBX_SCALE_UNITS", axis_forward="-Z", axis_up="Y",
                         bake_space_transform=True, mesh_smooth_type="FACE", add_leaf_bones=False, path_mode="STRIP")
open(os.path.join(OUT, "CREDITS.md"), "w").write(
    f"# {TITLE}\n\nGenerated by Tripo AI (tripo3d.ai) from Iris's reference sheet, on Moti's Tripo Pro plan (private models, "
    "commercial use).\nScaled and exported by blender-tests/ai_models/head.py (Moti + Claude).\n")
co = np.array([v.co[:] for v in head.data.vertices])
report = {"chin_to_crown": HEAD_HEIGHT, "scale": round(float(scale), 4),
          "size_m": [round(float(d), 3) for d in co.max(0) - co.min(0)],
          "triangles": sum(len(p.vertices) - 2 for p in head.data.polygons)}
json.dump(report, open(os.path.join(ROOT, "checks", "head.json"), "w"), indent=2)
print("REPORT", report)
