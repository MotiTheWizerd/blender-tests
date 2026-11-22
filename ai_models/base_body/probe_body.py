"""A Tripo body looked over before it joins the recipe: its mesh, its maps, its head against its height, how even its
paint is (a lit render baked into the paint shows as a darker back and underside), and two renders of it as it comes.

    blender -b --factory-startup -P probe_body.py -- <tripo file> <name>

Prints the numbers, writes checks/probe_body_<name>.json and checks/probe_body_<name>_{front,back}.png.
"""
import bpy, json, os, sys
import numpy as np

ARGS = sys.argv[sys.argv.index("--") + 1:]
SOURCE, NAME = ARGS[0], ARGS[1]
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
from pose import import_tripo  # noqa: E402
from face import profile  # noqa: E402

HEIGHT, NECK, SKULL = 1.70, 0.84, 0.7
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
tripo = import_tripo(SOURCE, "Tripo " + NAME)
me = tripo.data
P = np.array([v.co for v in me.vertices])
lo, hi = P.min(0), P.max(0)
report = {"name": NAME, "source": os.path.basename(SOURCE), "vertices": len(P), "faces": len(me.polygons),
          "size": np.round(hi - lo, 3).tolist(), "uv_layers": len(me.uv_layers)}

# the maps, by the socket each feeds
maps = {}
if me.materials and me.materials[0].use_nodes:
    for n in me.materials[0].node_tree.nodes:
        if n.type == "TEX_IMAGE" and n.image:
            for l in n.outputs[0].links:
                maps[l.to_socket.name] = {"image": n.image.name, "size": list(n.image.size), "file": os.path.basename(n.image.filepath)}
report["maps"] = maps

# the head against the height, as fit_macros measures it
Q = (P - [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]]) * (HEIGHT / (hi[2] - lo[2]))
above = Q[Q[:, 2] > NECK * HEIGHT]
try:
    crown, chin_z, nose, chin = profile(above)
    skull = above[above[:, 2] > chin_z + SKULL * (crown - chin_z)]
    report["head"] = {"chin_to_crown": round(float(crown - chin_z), 4), "heads_to_height": round(float(HEIGHT / (crown - chin_z)), 2),
                      "width": round(float(skull[:, 0].max() - skull[:, 0].min()), 4), "depth": round(float(skull[:, 1].max() - skull[:, 1].min()), 4)}
except Exception as e:  # noqa: BLE001
    report["head"] = {"error": str(e)}

# the paint's evenness: the mean brightness of the paint on faces that look forward, back, up and down (world normals);
# an unlit paint is even, a lit one is darker behind and below
colour = maps.get("Base Color")
if colour:
    img = bpy.data.images[colour["image"]]
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)[:, :, :3]
    uv = np.empty(len(me.loops) * 2)
    me.uv_layers[0].data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    lv = np.empty(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", lv)
    nrm = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("normal", nrm)
    nrm = nrm.reshape(-1, 3)[lv]
    sample = px[np.clip((uv[:, 1] % 1.0) * h, 0, h - 1).astype(int), np.clip((uv[:, 0] % 1.0) * w, 0, w - 1).astype(int)]
    lum = sample @ [0.2126, 0.7152, 0.0722]
    body = Q[lv][:, 2] < NECK * HEIGHT  # the body's skin, not the face
    sides = {"front": nrm[:, 1] < -0.7, "back": nrm[:, 1] > 0.7, "up": nrm[:, 2] > 0.7, "down": nrm[:, 2] < -0.7,
             "left": nrm[:, 0] > 0.7, "right": nrm[:, 0] < -0.7}
    report["paint"] = {k: round(float(np.median(lum[m & body])), 3) for k, m in sides.items() if (m & body).sum() > 50}
    report["paint"]["painted_share"] = round(float((px.sum(2) > 0.05).mean()), 3)

print("PROBE " + json.dumps(report))
with open(os.path.join(HERE, "checks", "probe_body_%s.json" % NAME), "w") as f:
    json.dump(report, f, indent=1)

# the renders, its own paint on
for p in me.polygons:
    p.use_smooth = True
scene.render.engine = "BLENDER_EEVEE"
world = bpy.data.worlds.new("w"); world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.5, 0.5, 0.5, 1); scene.world = world
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); sun.data.energy = 3.0
sun.rotation_euler = (np.radians(55), 0, np.radians(-30)); scene.collection.objects.link(sun)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); cam.data.type = "ORTHO"; cam.data.ortho_scale = (hi[2] - lo[2]) * 1.1
scene.collection.objects.link(cam); scene.camera = cam
c = (lo + hi) / 2
scene.render.resolution_x, scene.render.resolution_y = 900, 1400
for view, loc, rot in (("front", (c[0], c[1] - 10, c[2]), (90, 0, 0)), ("back", (c[0], c[1] + 10, c[2]), (90, 0, 180))):
    cam.location = loc
    cam.rotation_euler = [np.radians(a) for a in rot]
    scene.render.filepath = os.path.join(HERE, "checks", "probe_body_%s_%s.png" % (NAME, view))
    bpy.ops.render.render(write_still=True)
print("PROBE rendered")
