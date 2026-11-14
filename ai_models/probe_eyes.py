"""Where a head's eyes are and how its lids are built: the probe before eyes become separate eyeballs.

    blender -b --factory-startup -P probe_eyes.py -- head_warrior_m

Reads head.py's export (<name>/build/forge/<Title>/<Title>.fbx and its _BaseColor.jpg). Each vertex takes the colour
its texture has under it (averaged over its corners); the eye's white (bright, grey) and its iris (coloured, not skin)
in the band between the nose tip and the brow are the painted eyes. Says where each eye is (its centre, its opening's
width and height), how its surface lies against the face round it (how deep it sits behind the brow and the cheek),
and how the mesh is built there (shells, open edges); writes checks/eyes_probe.json and pictures: eyes_front.jpg,
eyes_side.jpg in the texture's colours, eyes_found.jpg with the white red and the iris blue, eyes_wire_<side>.jpg
each eye close with its edges.
"""
import bmesh, bpy, json, os, sys
import numpy as np
from glob import glob
from mathutils import Matrix, Vector

NAME = sys.argv[sys.argv.index("--") + 1]
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from face import profile
from place import pictures_as_jpeg

ROOT = os.path.join(HERE, NAME)
made = glob(os.path.join(ROOT, "build", "forge", "*", "*.fbx"))
if len(made) != 1:
    raise SystemExit(f"EYES {NAME} has {len(made)} exports (run head.py)")
TITLE = os.path.basename(os.path.dirname(made[0]))

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=made[0])
head = next(o for o in bpy.data.objects if o.type == "MESH")
me = head.data
me.transform(head.matrix_world, shape_keys=True)
head.matrix_world = Matrix.Identity(4)
me.update()
co = np.array([v.co[:] for v in me.vertices])
crown, chin, nose, chin_front = profile(co)

image = bpy.data.images.load(os.path.join(os.path.dirname(made[0]), f"{TITLE}_BaseColor.jpg"))
w, h = image.size
pixels = np.array(image.pixels[:], dtype=np.float32).reshape(h, w, image.channels)[..., :3]
uv = np.empty(len(me.loops) * 2, dtype=np.float32)
me.uv_layers.active.data.foreach_get("uv", uv)
uv = uv.reshape(-1, 2)
loop_vert = np.empty(len(me.loops), dtype=np.int64)
me.loops.foreach_get("vertex_index", loop_vert)
px = (np.clip(uv[:, 0], 0, 1) * (w - 1)).astype(int)
py = (np.clip(uv[:, 1], 0, 1) * (h - 1)).astype(int)
loop_colour = pixels[py, px]
colour = np.zeros((len(me.vertices), 3))
np.add.at(colour, loop_vert, loop_colour)
colour /= np.maximum(np.bincount(loop_vert, minlength=len(me.vertices)), 1)[:, None]

r, g, b = colour.T
lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
spread = colour.max(1) - colour.min(1)
# The band the eyes can be in: above the nose tip, below the brow; at the front of the face.
band = (co[:, 2] > nose[2] + 0.005) & (co[:, 2] < nose[2] + 0.07) & (co[:, 1] < nose[1] + 0.06)
white = band & (lum > 0.55) & (spread < 0.12)
iris = band & ~white & ((b > r + 0.02) | (g > r + 0.02)) & (lum < 0.6)
eye = white | iris

report = {"title": TITLE, "vertices": len(co), "nose_tip": nose.round(4).tolist(), "crown": round(float(crown), 4)}
bm = bmesh.new()
bm.from_mesh(me)
report["open_edges"] = sum(1 for e in bm.edges if e.is_boundary)
# Shells: is anything (an eye) a piece of its own?
seen, shells = set(), []
for v in bm.verts:
    if v.index in seen:
        continue
    stack, size = [v], 0
    seen.add(v.index)
    while stack:
        x = stack.pop()
        size += 1
        for e in x.link_edges:
            o = e.other_vert(x)
            if o.index not in seen:
                seen.add(o.index)
                stack.append(o)
    shells.append(size)
report["shells"] = sorted(shells, reverse=True)[:5]

eyes = {}
for side, mask in (("right", eye & (co[:, 0] < 0)), ("left", eye & (co[:, 0] > 0))):
    # The subject's own right is at -x when the face looks along -y.
    if mask.sum() < 10:
        eyes[side] = {"found": int(mask.sum())}
        continue
    p = co[mask]
    lo, hi = p.min(0), p.max(0)
    centre = (lo + hi) / 2
    # The face round it: the brow above, the cheek below, at its middle's x; how far forward each stands.
    near_x = np.abs(co[:, 0] - centre[0]) < 0.006
    brow = co[near_x & (co[:, 2] > hi[2] + 0.005) & (co[:, 2] < hi[2] + 0.02)]
    cheek = co[near_x & (co[:, 2] < lo[2] - 0.005) & (co[:, 2] > lo[2] - 0.02)]
    front = lambda q: float(q[:, 1].min()) if len(q) else None
    eyes[side] = {
        "vertices_white": int((white & mask).sum()), "vertices_iris": int((iris & mask).sum()),
        "centre_m": centre.round(4).tolist(), "opening_width_mm": round(float(hi[0] - lo[0]) * 1000, 1),
        "opening_height_mm": round(float(hi[2] - lo[2]) * 1000, 1),
        "eye_surface_front_y": round(float(p[:, 1].min()), 4), "eye_surface_back_y": round(float(p[:, 1].max()), 4),
        "brow_front_y": front(brow), "cheek_front_y": front(cheek),
        "iris_centre_m": co[iris & mask].mean(0).round(4).tolist() if (iris & mask).any() else None,
    }
    eyes[side]["sits_behind_brow_mm"] = (round((p[:, 1].min() - brow[:, 1].min()) * 1000, 1) if len(brow) else None)
report["eyes"] = eyes
os.makedirs(os.path.join(ROOT, "checks"), exist_ok=True)
json.dump(report, open(os.path.join(ROOT, "checks", "eyes_probe.json"), "w"), indent=1)
print("EYES", json.dumps(report))

# Pictures: the face in its colours, then what was found.
scene = bpy.context.scene
pictures_as_jpeg(scene)
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.render.resolution_x = scene.render.resolution_y = 900
scene.world = bpy.data.worlds.new("w")
material = bpy.data.materials.new("skin")
material.use_nodes = True
tex = material.node_tree.nodes.new("ShaderNodeTexImage")
tex.image = image
material.node_tree.nodes.active = tex
me.materials.clear()
me.materials.append(material)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
scene.collection.objects.link(cam)
scene.camera = cam
cam.data.type = "ORTHO"
eye_mid = Vector(((eyes.get("right", {}).get("centre_m") or [0, 0, 0])[i] / 2 + (eyes.get("left", {}).get("centre_m") or [0, 0, 0])[i] / 2 for i in range(3)))


def shoot(name, centre, direction, ortho):
    d = Vector(direction).normalized()
    cam.location = centre + d * 2
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    cam.data.ortho_scale = ortho
    scene.render.filepath = os.path.join(ROOT, "checks", name + ".jpg")
    bpy.ops.render.render(write_still=True)


scene.display.shading.color_type = "TEXTURE"
shoot("eyes_front", eye_mid, (0, -1, 0), 0.12)
shoot("eyes_side", eye_mid, (1, -0.15, 0), 0.12)
# What was found, painted on the vertices: the white red, the iris blue, the rest grey.
attr = me.color_attributes.new("found", "FLOAT_COLOR", "POINT")
for i, (wt, ir) in enumerate(zip(white, iris)):
    attr.data[i].color = (0.9, 0.1, 0.1, 1) if wt else (0.1, 0.3, 0.95, 1) if ir else (0.6, 0.6, 0.6, 1)
scene.display.shading.color_type = "VERTEX"
shoot("eyes_found", eye_mid, (0, -1, 0), 0.12)
# Each eye close, its edges drawn (a thin wireframe copy over it, dark): how the lids are built.
scene.display.shading.color_type = "TEXTURE"
wire = bpy.data.objects.new("wire", me.copy())
scene.collection.objects.link(wire)
modifier = wire.modifiers.new("wire", "WIREFRAME")
modifier.thickness = 0.00012
modifier.use_replace = True
dark = bpy.data.materials.new("dark")
dark.diffuse_color = (0.02, 0.02, 0.02, 1)
wire.data.materials.clear()
wire.data.materials.append(dark)
scene.display.shading.color_type = "MATERIAL"
for side in ("right", "left"):
    if "centre_m" in eyes.get(side, {}):
        shoot(f"eyes_wire_{side}", Vector(eyes[side]["centre_m"]), (0, -1, 0), 0.045)
