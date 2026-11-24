"""Where her face slot meets her body at the neck: the colour on each side of the seam as the game draws it, the face
map at the head island's UVs and the body map at the body's, in bands of the skin by distance from the seam.

    blender -b -P probe_seam.py -- <face name> [<face map> <body map>]

Defaults to what build_body.py ships: build/face_<face>_skin.png (or face_<face>_color.png) and build/body_<face>_color.png.
Prints each band's median colour (encoded and linear) and the linear ratio of the body side to the face side.
"""
import bpy, json, os, sys
import numpy as np

ARGS = sys.argv[sys.argv.index("--") + 1:]
FACE = ARGS[0]
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from her import create, settle, Head  # noqa: E402

TYPES = json.load(open(os.path.join(HERE, "types.json")))
bpy.ops.wm.read_factory_settings(use_empty=True)
fit = json.load(open(os.path.join(HERE, "checks", "fit_%s.json" % TYPES["base"])))["values"]
face = json.load(open(os.path.join(HERE, "checks", "face_%s.json" % FACE)))
base, rig = create(fit, face)
me = settle(base, rig)
head = Head(base, me)
toned = os.path.join(HERE, "build", "face_%s_skin.png" % FACE)
face_map = ARGS[1] if len(ARGS) > 1 else (toned if os.path.exists(toned) else os.path.join(HERE, "build", "face_%s_color.png" % FACE))
body_map = ARGS[2] if len(ARGS) > 2 else os.path.join(HERE, "build", "body_%s_color.png" % FACE)

n = len(me.vertices)
P = np.empty(n * 3)
me.vertices.foreach_get("co", P)
P = P.reshape(-1, 3)
uv = np.empty(len(me.loops) * 2)
me.uv_layers[0].data.foreach_get("uv", uv)
uv = uv.reshape(-1, 2)
lv = np.empty(len(me.loops), dtype=np.int64)
me.loops.foreach_get("vertex_index", lv)
in_head = np.zeros(len(me.polygons), dtype=bool)
in_head[head.faces] = True
skin = set(head.skin.tolist())
head_uv, body_uv = {}, {}
for p in me.polygons:
    for li in p.loop_indices:
        (head_uv if in_head[p.index] else body_uv).setdefault(int(lv[li]), uv[li])
seam = np.array(sorted(v for v in body_uv if v in head_uv and v in skin))
print("seam: %d vertices" % len(seam), flush=True)


def pixels(path):
    img = bpy.data.images.load(path)
    img.colorspace_settings.name = "sRGB"
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)[:, :, :3]


def sample(px, uvs):
    h, w = px.shape[:2]
    return px[np.clip((uvs[:, 1] % 1.0) * h, 0, h - 1).astype(int), np.clip((uvs[:, 0] % 1.0) * w, 0, w - 1).astype(int)]


def linear(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


fpx, bpx = pixels(face_map), pixels(body_map)
dist = np.min(np.linalg.norm(P[:, None, :] - P[seam][None, :, :], axis=2), axis=1)
scale, offset = np.array(face["uv"]["scale"]), np.array(face["uv"]["offset"])
for name, lo, hi in (("the seam", 0.0, 1e-6), ("0-1 cm", 0.0, 0.01), ("1-3 cm", 0.01, 0.03)):
    # each side's vertices in the band (the seam's own on both, at each side's UV)
    fv = [v for v in head_uv if lo <= dist[v] < hi]
    bv = [v for v in body_uv if lo <= dist[v] < hi]
    f = sample(fpx, np.array([head_uv[v] for v in fv]) * scale + offset)
    b = sample(bpx, np.array([body_uv[v] for v in bv]))
    fm, bm = np.median(f, 0), np.median(b, 0)
    print("%-8s: face %s (%d) | body %s (%d) | body/face linear %s" % (
        name, fm.round(3), len(fv), bm.round(3), len(bv), (np.median(linear(b), 0) / np.maximum(np.median(linear(f), 0), 1e-4)).round(2)), flush=True)
