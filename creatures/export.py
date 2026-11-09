"""Step 4 for a creature: the files Forge's model contract wants, so it stands in the world (a still model; Forge has
no moving creatures yet).

    blender -b --factory-startup -P export.py -- dragon [length=12]

Reads <name>/<name>_rig.blend (step 3: the reduced mesh, its maps, its skeleton's weights). Writes <name>/forge/<Name>/,
ready to copy to unity-game-test Assets/_Project/Content/Models/<Name>/:
  <Name>.fbx     metres, `length` long front to back, standing on its pivot at its footprint's middle; meshes
                 <Name>_LOD0/1/2 (the reduced mesh, 40% and 12% of it) and <Name>_<Region>_COL, a convex hull for each
                 region of the skeleton (the vertices its bones move most), so the colliders hug the body and leave the
                 air between the wings empty
  <Name>_BaseColor.jpg, <Name>_Normal.png (OpenGL), <Name>_MetallicSmoothness.png (metal R, smoothness A), at 2048
  CREDITS.md
"""
import bmesh, bpy, json, os, sys
import numpy as np
from mathutils import Matrix, Vector

args = sys.argv[sys.argv.index("--") + 1:]
NAME = args[0]
LENGTH = float(args[1]) if len(args) > 1 else 12.0
Title = NAME.capitalize()
HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), NAME)
OUT = os.path.join(HERE, "forge", Title)
os.makedirs(OUT, exist_ok=True)
MAPS = 2048
LODS = (0.4, 0.12)
# Which bones make each collider: a region is the vertices whose strongest bone starts with one of its prefixes.
REGIONS = {
    "Body": ["spine_"], "Neck": ["neck_"], "Head": ["head_"],
    "TailBase": ["tail_0", "tail_1", "tail_2"], "TailMid": ["tail_3", "tail_4", "tail_5"],
    "TailEnd": ["tail_6", "tail_7", "tail_8", "tail_9"],
    "ArmL": ["arm_*.L"], "ArmR": ["arm_*.R"], "LegL": ["leg_*.L"], "LegR": ["leg_*.R"],
    "WingL": ["wing_*.L", "finger"], "WingR": ["wing_*.R", "finger"],
}

bpy.ops.wm.open_mainfile(filepath=os.path.join(HERE, f"{NAME}_rig.blend"))
scene = bpy.context.scene
body = next(o for o in scene.objects if o.type == "MESH")
mesh = body.data.copy()
mesh.transform(body.matrix_world)

# Size and pivot: `length` along Y (front to back), the lowest point on the pivot, the footprint centred on it.
co = np.empty(len(mesh.vertices) * 3); mesh.vertices.foreach_get("co", co); co = co.reshape(-1, 3)
k = LENGTH / (co[:, 1].max() - co[:, 1].min())
centre = (co.min(0) + co.max(0)) / 2
mesh.transform(Matrix.Scale(k, 4) @ Matrix.Translation((-centre[0], -centre[1], -co[:, 2].min())))
mesh.update()

# The regions, from the weights (on the same vertices: the copy keeps their order).
names = {g.index: g.name for g in body.vertex_groups}
def region_of(bone):
    for region, prefixes in REGIONS.items():
        for p in prefixes:
            stem, _, side = p.partition("*")
            if bone.startswith(stem) and bone.endswith(side) and (region[-1] not in "LR" or bone.endswith("." + region[-1])):
                return region
    return "Body"
points = {r: [] for r in REGIONS}
for v, src in zip(mesh.vertices, body.data.vertices):
    strongest = max(src.groups, key=lambda g: g.weight, default=None)
    points[region_of(names[strongest.group]) if strongest else "Body"].append(v.co.copy())

for o in list(scene.objects):
    bpy.data.objects.remove(o, do_unlink=True)


def link(label, data):
    o = bpy.data.objects.new(label, data)
    scene.collection.objects.link(o)
    return o


lod0 = link(f"{Title}_LOD0", mesh); mesh.name = lod0.name
material = mesh.materials[0]
mesh.materials.clear()
drawn = [lod0]
for level, ratio in enumerate(LODS, start=1):
    o = link(f"{Title}_LOD{level}", mesh.copy())
    m = o.modifiers.new("lod", "DECIMATE"); m.ratio = ratio; m.use_collapse_triangulate = True
    data = bpy.data.meshes.new_from_object(o.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    o.modifiers.clear(); old = o.data; o.data = data; bpy.data.meshes.remove(old)
    data.name = o.name
    drawn.append(o)


def hull(label, verts):
    """A convex hull of at most 250 faces (PhysX cooks at most 255): a larger one is collapsed and wrapped again."""
    hb = bmesh.new()
    for c in verts:
        hb.verts.new(c)
    bmesh.ops.convex_hull(hb, input=hb.verts)
    bmesh.ops.delete(hb, geom=[v for v in hb.verts if not v.link_faces], context="VERTS")
    data = bpy.data.meshes.new(label); hb.to_mesh(data); hb.free()
    h = link(label, data)
    while len(data.polygons) > 250:
        m = h.modifiers.new("fit", "DECIMATE"); m.ratio = 240 / len(data.polygons)
        coarse = bpy.data.meshes.new_from_object(h.evaluated_get(bpy.context.evaluated_depsgraph_get()))
        h.modifiers.clear()
        hb = bmesh.new()
        for v in coarse.vertices:
            hb.verts.new(v.co)
        bpy.data.meshes.remove(coarse)
        bmesh.ops.convex_hull(hb, input=hb.verts)
        bmesh.ops.delete(hb, geom=[v for v in hb.verts if not v.link_faces], context="VERTS")
        hb.to_mesh(data); hb.free()
    return h


cols = [hull(f"{Title}_{r}_COL", p) for r, p in points.items() if len(p) >= 4]

# Maps at Forge's size, in its packing (glTF's rm: roughness G, metal B -> URP: metal R, smoothness A).
def image_in(socket_name):
    bsdf = next(n for n in material.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    node = bsdf.inputs[socket_name].links[0].from_node
    while node.type != "TEX_IMAGE":
        node = next(i for i in node.inputs if i.is_linked).links[0].from_node
    return node.image
def pixels(image):
    image = image.copy(); image.scale(MAPS, MAPS)
    a = np.empty(MAPS * MAPS * 4, np.float32); image.pixels.foreach_get(a)
    return a.reshape(MAPS, MAPS, 4)
def save(array, label, alpha, colour):
    image = bpy.data.images.new(label, MAPS, MAPS, alpha=alpha)
    image.colorspace_settings.name = "sRGB" if colour else "Non-Color"
    image.pixels.foreach_set(np.ascontiguousarray(array, np.float32).ravel())
    settings = scene.render.image_settings
    settings.file_format, settings.color_mode = ("PNG", "RGBA" if alpha else "RGB") if not colour else ("JPEG", "RGB")
    settings.compression, settings.quality = 100, 92
    image.save_render(os.path.join(OUT, label + (".jpg" if colour else ".png")), scene=scene)
save(pixels(image_in("Base Color")), f"{Title}_BaseColor", alpha=False, colour=True)
save(pixels(image_in("Normal")), f"{Title}_Normal", alpha=False, colour=False)
rm = pixels(image_in("Roughness"))
ms = np.zeros_like(rm); ms[..., 0] = rm[..., 2]; ms[..., 3] = 1.0 - rm[..., 1]
save(ms, f"{Title}_MetallicSmoothness", alpha=True, colour=False)

bpy.ops.object.select_all(action="DESELECT")
for o in drawn + cols:
    o.select_set(True)
bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, f"{Title}.fbx"), use_selection=True, object_types={"MESH"},
                         apply_unit_scale=True, apply_scale_options="FBX_SCALE_UNITS", axis_forward="-Z", axis_up="Y",
                         bake_space_transform=True, mesh_smooth_type="FACE", add_leaf_bones=False, path_mode="STRIP")
open(os.path.join(OUT, "CREDITS.md"), "w").write(
    f"# {Title}\n\nGenerated by Tripo AI (tripo3d.ai, H3.1, 4K PBR) from Moti's own picture, on his Tripo Pro plan\n"
    "(private models, commercial use). Reduced, baked and exported by blender-tests/creatures (Moti + Claude).\n")
dims = [round(float(d), 2) for d in (co.max(0) - co.min(0)) * k]
report = {"length": LENGTH, "scale": round(k, 3), "size_m": dims,
          "triangles": {o.name: sum(len(p.vertices) - 2 for p in o.data.polygons) for o in drawn},
          "colliders": {c.name: len(c.data.polygons) for c in cols}}
json.dump(report, open(os.path.join(HERE, "export.json"), "w"), indent=1)
print("EXPORT", json.dumps(report))
