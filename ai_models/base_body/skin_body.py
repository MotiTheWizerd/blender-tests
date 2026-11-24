"""The body's colour: a skin shifted to the face's tone, so her face slot (the Tripo paint, bake_face.py) and her body
meet at the neck in one skin. The skin is a painted Tripo body's paint baked onto her UV (bake_detail.py's
build/<name>_color.png, 8K) when there is one of that name, else MPFB's own skin (a MakeHuman system asset, CC0,
2K on her UV).

    blender -b -P skin_body.py -- <skin: a baked Tripo body's name, or an MPFB skin, e.g. young_caucasian_female> <face name>

The tone is skin against skin: the median of the face paint's pixels over the median of the skin's, in linear light, a
gain per channel laid on the whole skin in linear light (a gain on the encoded values bent the hue green). Then the
seam, the ring of head-island vertices that touch the body's faces: the face map pulled to the body's colour where
they meet, fading out over a few centimetres up the head. Writes build/body_<face>_color.png (what build_body.py
takes for <Title>_Color.png and every type's), build/face_<face>_skin.png (the face slot's) and
checks/skin_body_<face>.json (the two tones, the gain, the seam's ratio).
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

# the seam: head-island vertices on a face of the body's slot (not the eye cups' or the mouth pocket's: islands of
# their own whose rims are the head island's too; taken for the seam, they had the eyes' surround toned to them)
in_head = np.zeros(len(me.polygons), dtype=bool)
in_head[head.faces] = True
poly_of_loop = np.repeat(np.arange(len(me.polygons)), [p.loop_total for p in me.polygons])
in_pocket = np.zeros(len(me.polygons), dtype=bool)
for loops, _ in head.pockets:
    in_pocket[np.unique(poly_of_loop[loops])] = True
skin = set(head.skin.tolist())
seam = sorted({v for p in me.polygons if not in_head[p.index] and not in_pocket[p.index] for v in p.vertices if v in skin})
uv = np.empty(len(me.loops) * 2)
me.uv_layers[0].data.foreach_get("uv", uv)
uv = uv.reshape(-1, 2)
lv = np.empty(len(me.loops), dtype=np.int64)
me.loops.foreach_get("vertex_index", lv)
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
    save(skin_px, "body_%s_color" % FACE)
    toned = "the face, to the body's tone"
else:
    gain = face_mean / np.maximum(skin_mean, 1e-4)
    skin_px[:, :, :3] = np.clip(encoded(linear(skin_px[:, :, :3]) * gain), 0, 1)
    save(skin_px, "body_%s_color" % FACE)
    toned = "the body, to the face's tone"
print("toned %s: gain %s" % (toned, gain.round(3)), flush=True)

# --- the seam: one colour where the face slot meets the body ---------------------------------------------------------
# The tone matches the two paints as wholes; where they touch, under the jaw and round the nape, the face map can still
# be its own colour (woman2: the body half as light as the face map beside it, linear, and behind the ear a lighter,
# oranger patch with a hard edge). Each seam vertex's ratio, the body map's skin within SEAM_BAND of it over the face
# map's, smoothed along the ring over RING, is laid on the face map fading out over FEATHER up the head from the seam
# (a smoothstep, in log gain), so the face keeps its own paint and the neck is the body's where they meet. Each side
# is read at its own UVs (an earlier seam log read the body map at the head island's UVs, a place nobody sees).
SEAM_BAND, RING, FEATHER = 0.025, 0.03, 0.03
P = np.empty(len(me.vertices) * 3)
me.vertices.foreach_get("co", P)
P = P.reshape(-1, 3)
head_uv, body_uv = {}, {}
for p in me.polygons:
    if in_pocket[p.index]:
        continue
    for li in p.loop_indices:
        (head_uv if in_head[p.index] else body_uv).setdefault(int(lv[li]), uv[li])
seam = np.array(seam)
to_seam = np.linalg.norm(P[:, None, :] - P[seam][None, :, :], axis=2)
dist, nearest = to_seam.min(1), to_seam.argmin(1)
scale, offset = np.array(face["uv"]["scale"]), np.array(face["uv"]["offset"])
# each side's skin off the seam itself (the seam's own texels lie on their islands' edges, part gutter: red read 0.57
# there and 0.48 a ring further down), NEAR of each nearest every seam vertex within SEAM_BAND (her neck's rings lie
# more than a centimetre apart in places, so a fixed radius left seam vertices with nothing beside them)
on_seam = set(seam.tolist())
head_side = np.array([v for v in head_uv if v not in on_seam and dist[v] < SEAM_BAND])
body_side = np.array([v for v in body_uv if v not in head_uv and dist[v] < SEAM_BAND])
on_face = linear(sample(face_px, np.array([head_uv[v] for v in head_side]) * scale + offset))
on_body = linear(sample(skin_px, np.array([body_uv[v] for v in body_side])))
print("within %.1f cm of the seam, each at its own UVs: the face map %s (%d), the body %s (%d), linear medians" % (
    SEAM_BAND * 100, np.median(on_face, 0).round(4), len(head_side), np.median(on_body, 0).round(4), len(body_side)), flush=True)
NEAR = 8
log_ratio = np.zeros((len(seam), 3))
for k in range(len(seam)):
    f = on_face[np.argsort(to_seam[head_side, k])[:NEAR]].mean(0)
    b = on_body[np.argsort(to_seam[body_side, k])[:NEAR]].mean(0)
    log_ratio[k] = np.log(np.clip(b / np.maximum(f, 1e-4), 0.25, 4.0))
ring = np.linalg.norm(P[seam][:, None, :] - P[seam][None, :, :], axis=2) < RING
log_ratio = (ring[:, :, None] * log_ratio[None, :, :]).sum(1) / ring.sum(1)[:, None]
print("the seam: body over face %s (linear, median), %s to %s" % (np.exp(np.median(log_ratio, 0)).round(2),
      np.exp(log_ratio.min(0)).round(2), np.exp(log_ratio.max(0)).round(2)), flush=True)
t = np.clip(dist / FEATHER, 0.0, 1.0)
log_gain = (1.0 - t * t * (3.0 - 2.0 * t))[:, None] * log_ratio[nearest]  # per vertex, 0 past FEATHER

# laid on the face map: each head triangle near the seam rasterized in the face square, its corners' log gain
# interpolated; then grown a few texels past the island's edge so the texture's filtering finds it there too
h, w = face_px.shape[:2]
field = np.zeros((h, w, 3), np.float32)
covered = np.zeros((h, w), bool)
me.calc_loop_triangles()
for tri in me.loop_triangles:
    if not in_head[tri.polygon_index]:
        continue
    vs = list(tri.vertices)
    if min(dist[vs]) >= FEATHER:
        continue
    q = np.array([uv[li] for li in tri.loops]) * scale + offset
    q = q * [w, h]
    lo = np.floor(q.min(0)).astype(int)
    hi = np.ceil(q.max(0)).astype(int) + 1
    xs, ys = np.meshgrid(np.arange(max(lo[0], 0), min(hi[0], w)), np.arange(max(lo[1], 0), min(hi[1], h)))
    if xs.size == 0:
        continue
    px_c = np.stack([xs.ravel() + 0.5, ys.ravel() + 0.5], 1)
    a, b, c = q
    den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
    if abs(den) < 1e-12:
        continue
    l0 = ((b[1] - c[1]) * (px_c[:, 0] - c[0]) + (c[0] - b[0]) * (px_c[:, 1] - c[1])) / den
    l1 = ((c[1] - a[1]) * (px_c[:, 0] - c[0]) + (a[0] - c[0]) * (px_c[:, 1] - c[1])) / den
    l2 = 1.0 - l0 - l1
    inside = (l0 >= -1e-4) & (l1 >= -1e-4) & (l2 >= -1e-4)
    if not inside.any():
        continue
    lam = np.stack([l0, l1, l2], 1)[inside]
    yy, xx = ys.ravel()[inside], xs.ravel()[inside]
    field[yy, xx] = lam @ log_gain[vs]
    covered[yy, xx] = True
# (the gain is 0 at FEATHER, so what grows inward from the band's far edge is none)
for _ in range(8):
    acc = np.zeros_like(field)
    cnt = np.zeros((h, w), np.float32)
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        acc += np.roll(field * covered[:, :, None], (dy, dx), (0, 1))
        cnt += np.roll(covered, (dy, dx), (0, 1))
    grow = ~covered & (cnt > 0)
    field[grow] = acc[grow] / cnt[grow][:, None]
    covered |= grow
face_px[:, :, :3] = np.clip(encoded(linear(face_px[:, :, :3]) * np.exp(field)), 0, 1)
# the check: each seam vertex's two sides again, read as before, on the face map now
after = linear(sample(face_px, np.array([head_uv[v] for v in head_side]) * scale + offset))
left = np.array([on_body[np.argsort(to_seam[body_side, k])[:NEAR]].mean(0) / np.maximum(after[np.argsort(to_seam[head_side, k])[:NEAR]].mean(0), 1e-4)
                 for k in range(len(seam))])
print("after: body over face at each seam vertex %s (median), %s to %s; before %s to %s" % (
    np.median(left, 0).round(2), left.min(0).round(2), left.max(0).round(2),
    np.exp(log_ratio.min(0)).round(2), np.exp(log_ratio.max(0)).round(2)), flush=True)
save(face_px, "face_%s_skin" % FACE)  # build_body.py takes it for the face slot over face_<face>_color.png
print("the seam laid on the face map: %d texels, %d triangles' worth within %.0f cm" % (
    int((np.abs(field).sum(2) > 1e-4).sum()), int(sum(1 for t_ in me.loop_triangles if in_head[t_.polygon_index] and min(dist[list(t_.vertices)]) < FEATHER)), FEATHER * 100), flush=True)

with open(os.path.join(HERE, "checks", "skin_body_%s.json" % FACE), "w") as f:
    json.dump({"skin": SKIN, "face": FACE, "seam_vertices": len(seam), "face_tone_linear": face_mean.round(4).tolist(),
               "skin_tone_linear": skin_mean.round(4).tolist(), "toned": toned, "gain": gain.round(4).tolist(),
               "seam_ratio_linear": np.exp(np.median(log_ratio, 0)).round(4).tolist(), "feather_m": FEATHER}, f, indent=1)
