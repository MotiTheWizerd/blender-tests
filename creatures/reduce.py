"""Step 2 for a creature: a game mesh from the AI's film-scale one, its detail baked into a normal map.

    blender -b --factory-startup -P reduce.py -- dragon [triangles=40000] [bake_size=4096]

Reads <name>/source_tripo.glb. Welds the glTF's UV-seam splits (they stay seams in the UVs), copies the mesh and
collapses the copy to `triangles`, keeping its UVs, so the AI's own colour and roughness/metal maps still fit it.
Only the shape's detail is lost, so only the normal map is baked again: Cycles on the GPU, from the full mesh with
its own normal map (so the bake carries both the sculpted scales and the map's fine grain) onto the reduced one.

Writes, in <name>/build/ (made again by running it):
  <Name>_BaseColor.jpg, <Name>_RM.jpg   the AI's maps, unchanged (R unused, G roughness, B metal: glTF's packing)
  <Name>_Normal.png                     the baked tangent-space normals (OpenGL, Y+, as Unity wants)
  <name>_low.blend                      the reduced mesh with its material, for the rig (step 3)
and in <name>/checks/: reduce_compare.jpg (full left, reduced right, EEVEE, the same light), reduce_head_high/low.jpg
(the head close), reduce.json (triangles before and after, timings).
"""
import bmesh, bpy, json, math, os, sys, time
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
NAME = args[0]
TRIANGLES = int(args[1]) if len(args) > 1 else 40000
BAKE = int(args[2]) if len(args) > 2 else 4096
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from place import Creature, pictures_as_jpeg, save_blend
C = Creature(NAME)
Title = C.title
report = {"triangles_target": TRIANGLES, "bake_size": BAKE}
t0 = time.time()

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=C.source)
scene = bpy.context.scene
high = next(o for o in scene.objects if o.type == "MESH")
high.data.transform(high.matrix_world)       # the glTF's root baked in; the mesh stands on its own
high.parent = None
high.matrix_world.identity()
for o in list(scene.objects):
    if o is not high:
        bpy.data.objects.remove(o, do_unlink=True)
high.name = high.data.name = Title + "_High"

bm = bmesh.new(); bm.from_mesh(high.data)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
bm.to_mesh(high.data); bm.free()
report["triangles_source"] = sum(len(f.vertices) - 2 for f in high.data.polygons)

# The AI's maps, saved beside the script under our names.
material = high.data.materials[0]
images = {n.image.name: n for n in material.node_tree.nodes if n.type == "TEX_IMAGE" and n.image}
def save(image, path, fmt):
    image.filepath_raw = path
    image.file_format = fmt
    image.save()
for name, node in images.items():
    if "basecolor" in name:
        save(node.image, C.build(f"{Title}_BaseColor.jpg"), "JPEG")
    elif "_rm" in name:
        save(node.image, C.build(f"{Title}_RM.jpg"), "JPEG")
normal_node = next(n for name, n in images.items() if "normal" in name)

# The reduced copy: collapse keeps the UVs, triangulated so Unity shades it exactly as it was baked.
low = high.copy(); low.data = high.data.copy()
low.name = low.data.name = Title
scene.collection.objects.link(low)
bpy.context.view_layer.objects.active = low
mod = low.modifiers.new("reduce", "DECIMATE")
mod.decimate_type = "COLLAPSE"
mod.ratio = TRIANGLES / report["triangles_source"]
mod.use_collapse_triangulate = True
t = time.time()
bpy.ops.object.modifier_apply(modifier=mod.name)
report["decimate_s"] = round(time.time() - t, 1)
report["triangles"] = sum(len(f.vertices) - 2 for f in low.data.polygons)
for f in low.data.polygons:
    f.use_smooth = True

# The low material: the AI's own, its normal map swapped for the bake once it is done.
low_mat = material.copy(); low_mat.name = Title
low.data.materials.clear(); low.data.materials.append(low_mat)
baked = bpy.data.images.new(f"{Title}_Normal", BAKE, BAKE, alpha=False)
baked.colorspace_settings.name = "Non-Color"
target = low_mat.node_tree.nodes.new("ShaderNodeTexImage")
target.image = baked
low_mat.node_tree.nodes.active = target

scene.render.engine = "CYCLES"
prefs = bpy.context.preferences.addons["cycles"].preferences
prefs.compute_device_type = "OPTIX"; prefs.get_devices()
for d in prefs.devices:
    d.use = d.type == "OPTIX"
scene.cycles.device = "GPU"
scene.cycles.samples = 1
size = max(high.dimensions)
bake = scene.render.bake
bake.use_selected_to_active = True
bake.cage_extrusion = 0.004 * size        # out past the reduced surface, so the rays start outside the full one
bake.max_ray_distance = 0.012 * size
bake.margin = 8
bake.normal_space = "TANGENT"
bpy.ops.object.select_all(action="DESELECT")
high.select_set(True); low.select_set(True)
bpy.context.view_layer.objects.active = low
t = time.time()
bpy.ops.object.bake(type="NORMAL")
report["bake_s"] = round(time.time() - t, 1)
save(baked, C.build(f"{Title}_Normal.png"), "PNG")
own_normal = next(n for n in low_mat.node_tree.nodes if n.type == "TEX_IMAGE" and n.image is normal_node.image)
own_normal.image = baked
low_mat.node_tree.nodes.remove(target)

# Side by side: the full mesh left, the reduced right, in EEVEE under one light.
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x, scene.render.resolution_y = 1800, 900
pictures_as_jpeg(scene)
world = bpy.data.worlds.new("w"); scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.05, 0.05, 0.06, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 1.0
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 4; sun.rotation_euler = (math.radians(50), 0, math.radians(30))
scene.collection.objects.link(sun)
offset = high.dimensions.x * 1.1
low.location.x = offset / 2; high.location.x = -offset / 2
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
scene.collection.objects.link(cam); scene.camera = cam
cam.data.type = "ORTHO"; cam.data.clip_end = size * 20
def shoot(path, centre, scale, d):
    d = Vector(d).normalized()
    cam.location = centre + d * size * 4
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    cam.data.ortho_scale = scale
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
mid = Vector((0, 0, size * 0.28))
shoot(C.picture("reduce_compare"), mid, offset * 2.1, (0.5, -1, 0.35))
# The head close: each dragon's own head, one above the other is not possible in one frame, so two shots.
head = max(high.data.vertices, key=lambda v: v.co.z - v.co.y * 0.5).co.copy()   # far up and forward: the horns
for which, obj in (("high", high), ("low", low)):
    for o in (high, low):
        o.hide_render = o is not obj
    shoot(C.picture(f"reduce_head_{which}"), obj.location + head - Vector((0, 0, size * 0.06)), size * 0.3, (0.6, -1, 0.15))
for o in (high, low):
    o.hide_render = False
low.location = (0, 0, 0)

# Keep only the reduced dragon for the rig.
bpy.data.objects.remove(high, do_unlink=True)
for o in (sun, cam):
    bpy.data.objects.remove(o, do_unlink=True)
for image in bpy.data.images:
    if image.filepath_raw:
        image.filepath = image.filepath_raw     # point at the saved files, not the glb's packed copies
bpy.ops.file.make_paths_relative()
save_blend(bpy, C.blend("low"))
report["total_s"] = round(time.time() - t0, 1)
json.dump(report, open(C.checks("reduce.json"), "w"), indent=1)
print("REDUCE", json.dumps(report))
