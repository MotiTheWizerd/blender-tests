"""The body's colour: a skin shifted to the face's tone, so her face slot (the Tripo paint, bake_face.py) and her body
meet at the neck in one skin. The skin is a painted Tripo body's paint baked onto her UV (bake_detail.py's
build/<name>_color.png, 8K) when there is one of that name, else MPFB's own skin (a MakeHuman system asset, CC0,
2K on her UV).

    blender -b -P skin_body.py -- <skin: a baked Tripo body's name, or an MPFB skin, e.g. young_caucasian_female> <face name>

The tone is skin against skin: the median of the face paint's pixels over the median of the skin's, in linear light, a
gain per channel laid on the whole skin in linear light (a gain on the encoded values bent the hue green). The seam,
the ring of head-island vertices that touch the body's faces, is read on both maps and logged. Writes
build/body_<face>_color.png (what build_body.py takes for <Title>_Color.png and every type's) and
checks/skin_body_<face>.json (the two tones, the gain).
"""
import bpy, json, os, sys
import numpy as np
from bl_ext.blender_org.mpfb.services.locationservice import LocationService

ARGS = sys.argv[sys.argv.index("--") + 1:]
SKIN, FACE = ARGS[0], ARGS[1]
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from her import create, settle, Head  # noqa: E402

TYPES = json.load(open(os.path.join(HERE, "types.json")))
BASE = TYPES["base"]
bpy.ops.wm.read_factory_settings(use_empty=True)
fit = json.load(open(os.path.join(HERE, "checks", "fit_%s.json" % BASE)))["values"]
face = json.load(open(os.path.join(HERE, "checks", "face_%s.json" % FACE)))
base, rig = create(fit, face)
me = settle(base, rig)
head = Head(base, me)

# the seam: head-island vertices on a face outside the island
in_head = np.zeros(len(me.polygons), dtype=bool)
in_head[head.faces] = True
skin = set(head.skin.tolist())
seam = sorted({v for p in me.polygons if not in_head[p.index] for v in p.vertices if v in skin})
uv = np.empty(len(me.loops) * 2)
me.uv_layers[0].data.foreach_get("uv", uv)
uv = uv.reshape(-1, 2)
lv = np.empty(len(me.loops), dtype=np.int64)
me.loops.foreach_get("vertex_index", lv)
loop_of = {}
for i in head.loops:  # a seam vertex's UV on the head island (its other loops lie on the body's islands)
    loop_of.setdefault(int(lv[i]), int(i))
seam_uv = np.array([uv[loop_of[v]] for v in seam])
print("seam: %d vertices" % len(seam), flush=True)


def pixels(path, srgb):
    img = bpy.data.images.load(path)
    img.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    return px.reshape(h, w, 4), img


def sample(px, uvs):
    h, w = px.shape[:2]
    x = np.clip((uvs[:, 0] % 1.0) * w, 0, w - 1).astype(int)
    y = np.clip((uvs[:, 1] % 1.0) * h, 0, h - 1).astype(int)
    return px[y, x, :3]


baked = os.path.join(HERE, "build", "%s_color.png" % SKIN)
tripo_skin = os.path.exists(baked)
if tripo_skin:
    skin_px, skin_img = pixels(baked, True)
    print("the skin: the Tripo body %s's paint on her UV, %dx%d" % (SKIN, *skin_px.shape[1::-1]), flush=True)
else:
    mhmat = os.path.join(LocationService.get_user_data("skins"), SKIN, SKIN + ".mhmat")
    assert os.path.exists(mhmat), "no baked paint %s (bake_detail.py) and no MPFB skin %s" % (baked, mhmat)
    diffuse = next(l.split(None, 1)[1].strip() for l in open(mhmat) if l.startswith("diffuseTexture"))
    skin_px, skin_img = pixels(os.path.join(os.path.dirname(mhmat), diffuse), True)
    print("the skin: MPFB's %s" % SKIN, flush=True)
face_px, _ = pixels(os.path.join(HERE, "build", "face_%s_color.png" % FACE), True)
on_face = sample(face_px, seam_uv * face["uv"]["scale"] + face["uv"]["offset"])
on_skin = sample(skin_px, seam_uv)
print("at the seam: the face %s, the skin %s" % (np.median(on_face, axis=0).round(3), np.median(on_skin, axis=0).round(3)), flush=True)


def linear(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def encoded(c):
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(np.maximum(c, 0), 1 / 2.4) - 0.055)


# the tone: the face paint's skin against the body skin, each the median of its painted pixels, in linear light; a gain
# laid on one of them in linear light (a gain in the encoded values bends the hue: the first try went green). A
# painted Tripo body sets the tone and the face follows it (its paint is the look, and nineteen twentieths of her);
# MPFB's skin follows the face.
painted = lambda px: px[:, :, :3][px[:, :, :3].sum(2) > 0.1]
face_mean, skin_mean = np.median(linear(painted(face_px)), axis=0), np.median(linear(painted(skin_px)), axis=0)
print("the tone: the face %s, the skin %s (linear)" % (face_mean.round(4), skin_mean.round(4)), flush=True)


def save(px, name):
    px[:, :, 3] = 1.0
    image = bpy.data.images.new(name, px.shape[1], px.shape[0], alpha=False, float_buffer=False)
    image.colorspace_settings.name = "sRGB"
    image.pixels.foreach_set(px.ravel())
    path = os.path.join(HERE, "build", name + ".png")
    image.filepath_raw = path
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)
    print("wrote", path, flush=True)


if tripo_skin:
    gain = skin_mean / np.maximum(face_mean, 1e-4)
    face_px[:, :, :3] = np.clip(encoded(linear(face_px[:, :, :3]) * gain), 0, 1)
    save(face_px, "face_%s_skin" % FACE)  # build_body.py takes it for the face slot over face_<face>_color.png
    save(skin_px, "body_%s_color" % FACE)
    toned = "the face, to the body's tone"
else:
    gain = face_mean / np.maximum(skin_mean, 1e-4)
    skin_px[:, :, :3] = np.clip(encoded(linear(skin_px[:, :, :3]) * gain), 0, 1)
    save(skin_px, "body_%s_color" % FACE)
    old = os.path.join(HERE, "build", "face_%s_skin.png" % FACE)
    if os.path.exists(old):
        os.remove(old)
    toned = "the body, to the face's tone"
print("toned %s: gain %s" % (toned, gain.round(3)), flush=True)
with open(os.path.join(HERE, "checks", "skin_body_%s.json" % FACE), "w") as f:
    json.dump({"skin": SKIN, "face": FACE, "seam_vertices": len(seam), "face_tone_linear": face_mean.round(4).tolist(),
               "skin_tone_linear": skin_mean.round(4).tolist(), "toned": toned, "gain": gain.round(4).tolist()}, f, indent=1)
