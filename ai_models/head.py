"""A head for Forge's face editor: a Tripo bust (bald, neutral, symmetric), at a real head's size, exported for Forge.

    blender -b --factory-startup -P head.py -- head_warrior_m WarriorM

Reads <name>/source_tripo.fbx (and its .fbm textures), finds the chin and the crown on the face's middle line, scales
the bust so they are HEAD_HEIGHT apart (an adult's chin to crown), and writes build/forge/<Title>/: <Title>.fbx
(metres, front to Unity's +Z, as export.py), <Title>_BaseColor.jpg, <Title>_Normal.png and
<Title>_MetallicSmoothness.png (no metal: skin; smoothness = (1 - roughness) * SKIN_SHINE), the maps at MAP_SIZE; and its
eyes of their own (eyes.py: the painted eyes opened, eyeballs put in, their material <Title>Eyes, the mesh's second,
with <Title>Eyes_Color.png and <Title>Eyes_MetallicSmoothness.png). checks/head.json says what was measured;
checks/eyes_*.jpg and eyes_map_<side>.png show the eyes.
"""
import bpy, json, os, sys
import numpy as np
from mathutils import Vector

NAME, TITLE = sys.argv[sys.argv.index("--") + 1:][:2]
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from face import profile
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
# The face's landmarks on its middle line, seen from the side (face.py; Tripo's front is -Y).
crown, chin, nose_found, chin_found = profile(co)
scale = HEAD_HEIGHT / (crown - chin)
print(f"crown {crown:.4f} chin {chin:.4f} nose {nose_found[2]:.4f} -> scale {scale:.4f}")

head.scale = (scale,) * 3
bpy.ops.object.transform_apply(scale=True)
co = np.array([v.co[:] for v in head.data.vertices])
shift = np.array([-(co[:, 0].max() + co[:, 0].min()) / 2, -(co[:, 1].max() + co[:, 1].min()) / 2, -co[:, 2].min()])
head.location = Vector(shift)
bpy.ops.object.transform_apply(location=True)
head.name = head.data.name = TITLE

# The face's sliders, each a shape key Forge's face editor drives by its part and name ("Nose" "Width": NoseWidth), at
# 100 the most one way and, driven negative, the other. Each pushes the vertices round a landmark (the nose tip, the
# chin's front, in the final frame: metres, front -Y, up Z) by a soft falloff, so nothing near the neck moves.
nose_tip = nose_found * scale + shift
chin_front = chin_found * scale + shift
co = np.array([v.co[:] for v in head.data.vertices])


def falloff(centre, radii):
    """1 at <centre>, 0.14 at its <radii> (an ellipsoid's), nearly 0 past one and a half of them."""
    return np.exp(-2.0 * (((co - centre) / radii) ** 2).sum(1))


def shape(name, moved):
    key = head.shape_key_add(name=name, from_mix=False)
    key.data.foreach_set("co", moved.astype(np.float32).ravel())


head.shape_key_add(name="Basis")
f = falloff(nose_tip + [0, 0.012, -0.004], np.array([0.022, 0.02, 0.02]))
shape("NoseWidth", co + np.c_[co[:, 0] * 0.30 * f, 0 * f, 0 * f])
f = falloff(chin_front + [0, 0.06, 0.025], np.array([0.2, 0.07, 0.035]))
shape("JawWidth", co + np.c_[co[:, 0] * 0.15 * f, 0 * f, 0 * f])
f = falloff(chin_front + [0, 0, 0.012], np.array([0.03, 0.03, 0.025]))
shape("JawChin", co + np.c_[0 * f, -0.012 * f, 0 * f])
print("LANDMARKS nose", nose_tip.round(4), "chin", chin_front.round(4))


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


# Eyes of their own (eyes.py): the painted ones opened, eyeballs put in, in a material of their own (<Title>Eyes).
from eyes import give_eyes, eye_pictures
skin = image_of("Base Color")
eyes = give_eyes(head, skin, TITLE, OUT, os.path.join(ROOT, "checks"), nose_tip)
eye_pictures(head, skin, eyes, os.path.join(ROOT, "checks"))
print("EYES", json.dumps(eyes))

base = pixels(skin, MAP_SIZE)
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
          "triangles": sum(len(p.vertices) - 2 for p in head.data.polygons),
          "nose_tip": [round(float(c), 4) for c in nose_tip], "chin_front": [round(float(c), 4) for c in chin_front],
          "shapes": [k.name for k in head.data.shape_keys.key_blocks[1:]], "eyes": eyes}
json.dump(report, open(os.path.join(ROOT, "checks", "head.json"), "w"), indent=2)
print("REPORT", report)
