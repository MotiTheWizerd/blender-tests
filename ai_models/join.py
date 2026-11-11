"""Step 1b for a SLICED model (model.json "sliced": true): its parts made one mesh with one colour map, for reduce.

    blender -b --factory-startup -P join.py -- woman_1 [atlas=8192]

Tripo slices a model into parts (woman_1: 19 - head, neck, chest, belly, hips, each limb in two, hands, feet), each
its own mesh with its own colour map, cut where they meet: the cut's vertices are the same on both sides (woman_1:
every seam at distance 0). The rest of the recipe wants one mesh and one map, so here:

- the parts are joined and welded where they meet (1e-5, as reduce welds a glTF's UV splits): one closed body, so the
  rig skins across the cuts and the collapse doesn't open them;
- their maps go into one atlas at their own size, unchanged: each part's square, as the AI made it, is copied into
  its own square of the atlas (biggest first, a quadtree), and its UVs scaled into that square. Nothing is baked or
  resampled, so the atlas is exactly the parts' pixels. woman_1's 4096 + 10 x 2048 + 6 x 1024 + 2 x 512 fill 62.5 of
  an 8192 atlas's 64 1024-squares.

Writes build/<name>_joined.glb (one mesh, one material, the atlas: build/<Title>_Atlas_basecolor.jpg), which reduce
reads in place of source_tripo.glb (place.py, Creature.whole). checks/join.json: the parts, their squares, the open
edges before and after the weld and the holes it closed.
"""
import bmesh, bpy, json, os, sys, time
import numpy as np

args = sys.argv[sys.argv.index("--") + 1:]
NAME = args[0]
ATLAS = int(args[1]) if len(args) > 1 else 8192
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from place import Creature
C = Creature(NAME)
report = {"atlas": ATLAS}
t0 = time.time()

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=C.source)
scene = bpy.context.scene
parts = [o for o in scene.objects if o.type == "MESH"]
for o in parts:
    o.data.transform(o.matrix_world)       # the glTF's root baked in; each part stands on its own
    o.parent = None
    o.matrix_world.identity()
for o in list(scene.objects):
    if o.type != "MESH":
        bpy.data.objects.remove(o, do_unlink=True)


def colour_of(obj):
    """A part's colour map: the image feeding its material's base colour."""
    material = obj.data.materials[0]
    bsdf = next(n for n in material.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    return bsdf.inputs["Base Color"].links[0].from_node.image


# Each part's square in the atlas, biggest first: a free square of its size, else the smallest bigger one split in four
# (a quadtree). The AI's maps are square powers of two, so nothing is wasted that a later one could use. Pixel (x, y)
# from the bottom left, as Blender's pixels and UV space both start.
pieces = sorted(((colour_of(o).size[0], o.name) for o in parts), reverse=True)
free, squares = [(0, 0, ATLAS)], {}
for size, name in pieces:
    image = colour_of(bpy.data.objects[name])
    if image.size[0] != image.size[1] or size & (size - 1):
        raise SystemExit(f"JOIN {name}: its colour map is {tuple(image.size)}, not a square power of two")
    while True:
        fits = [s for s in free if s[2] >= size]
        if not fits:
            raise SystemExit(f"JOIN the parts' maps need more than a {ATLAS} atlas: {pieces}")
        x, y, s = min(fits, key=lambda f: (f[2], f[1], f[0]))
        free.remove((x, y, s))
        if s == size:
            break
        half = s // 2
        free += [(x, y, half), (x + half, y, half), (x, y + half, half), (x + half, y + half, half)]
    squares[name] = (x, y, size)
report["parts"] = {name: {"map": size, "at": squares[name][:2]} for size, name in pieces}
report["atlas_used"] = round(sum(s * s for s, _ in pieces) / ATLAS ** 2, 4)

# The atlas: each part's pixels copied into its square, as they are (byte maps: the stored sRGB values).
atlas_pixels = np.zeros((ATLAS, ATLAS, 4), dtype=np.float32)
atlas_pixels[..., 3] = 1.0
for size, name in pieces:
    image = colour_of(bpy.data.objects[name])
    pixels = np.empty(size * size * 4, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    x, y, _ = squares[name]
    atlas_pixels[y:y + size, x:x + size] = pixels.reshape(size, size, 4)
    del pixels
atlas = bpy.data.images.new(f"{NAME}_basecolor", ATLAS, ATLAS, alpha=False)
atlas.colorspace_settings.name = "sRGB"
atlas.pixels.foreach_set(atlas_pixels.ravel())
del atlas_pixels

# Each part's UVs into its square, then the parts joined into one mesh with one material: the atlas.
for o in parts:
    x, y, size = squares[o.name]
    uv = o.data.uv_layers.active.data
    coords = np.empty(len(uv) * 2, dtype=np.float32)
    uv.foreach_get("uv", coords)
    if coords.size and (coords.min() < -1e-4 or coords.max() > 1 + 1e-4):
        raise SystemExit(f"JOIN {o.name}: its UVs leave the 0..1 square ({coords.min():.3f}..{coords.max():.3f}), so it can't be moved into the atlas")
    coords = coords.reshape(-1, 2)
    coords[:, 0] = (coords[:, 0] * size + x) / ATLAS
    coords[:, 1] = (coords[:, 1] * size + y) / ATLAS
    uv.foreach_set("uv", coords.ravel())

material = bpy.data.materials.new(C.title)
material.use_nodes = True
nodes, links = material.node_tree.nodes, material.node_tree.links
bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
bsdf.inputs["Roughness"].default_value = 0.9       # the AI's: no roughness/metal map, roughness 0.9, metal 0
bsdf.inputs["Metallic"].default_value = 0.0
colour = nodes.new("ShaderNodeTexImage")
colour.image = atlas
links.new(colour.outputs["Color"], bsdf.inputs["Base Color"])
for o in parts:
    o.data.materials.clear()
    o.data.materials.append(material)

bpy.ops.object.select_all(action="DESELECT")
for o in parts:
    o.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
bpy.ops.object.join()
body = bpy.context.view_layer.objects.active
body.name = body.data.name = C.title


def open_edges(me):
    bm = bmesh.new(); bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)      # a glTF's own UV splits aren't openings
    n = sum(1 for e in bm.edges if e.is_boundary)
    bm.free()
    return n


report["open_edges_before"] = open_edges(body.data)
bm = bmesh.new(); bm.from_mesh(body.data)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
report["open_edges_welded"] = sum(1 for e in bm.edges if e.is_boundary)
# What is still open is where a cut didn't quite meet (woman_1: 12 edges, a few small holes): closed, each new face's
# corners taking the UVs the same vertices have in the skin beside them, all from one part's square (the first
# corner's), so the patch shows that skin and never stretches across the atlas between two parts.
uv = bm.loops.layers.uv.active


def square_of(point):
    x, y = point[0] * ATLAS, point[1] * ATLAS
    return next((n for n, (sx, sy, s) in squares.items() if sx <= x <= sx + s and sy <= y <= sy + s), None)


filled = bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=0)["faces"]
filled = bmesh.ops.triangulate(bm, faces=filled)["faces"]
new = set(filled)
for f in filled:
    f.smooth = True
    part = None
    for loop in f.loops:
        beside = [l for l in loop.vert.link_loops if l.face not in new]
        if not beside:
            continue
        part = part or square_of(beside[0][uv].uv)
        loop[uv].uv = next((l for l in beside if square_of(l[uv].uv) == part), beside[0])[uv].uv
report["holes_filled_faces"] = len(filled)
bm.to_mesh(body.data); bm.free()
report["open_edges_after"] = open_edges(body.data)
report["vertices"] = len(body.data.vertices)
report["triangles"] = sum(len(f.vertices) - 2 for f in body.data.polygons)

# The AI's normals go: each part's were made from that part alone, so along a cut the two sides' normals differ and
# the welded body showed a crease on every cut (light lines under the breasts, down the flanks and thighs), which the
# normal bake would carry into the game. Shaded smooth, the normals come from the welded surface itself.
with bpy.context.temp_override(object=body, active_object=body, selected_objects=[body]):
    bpy.ops.mesh.customdata_custom_splitnormals_clear()
body.data.shade_smooth()

# The atlas padded: the AI's maps are black between their UV islands, with next to no margin, so a reduced face
# reaching over an island's edge picked up black (dark specks on woman_1's hip), and a game's mipmaps would darken
# every island's rim from afar. Baked onto itself, each texel read exactly (closest), with Blender's margin extending
# every island 64 texels into the black: inside the islands the pixels are the same, around them the skin goes on.
scene.render.engine = "CYCLES"
prefs = bpy.context.preferences.addons["cycles"].preferences
prefs.compute_device_type = "OPTIX"; prefs.get_devices()
for d in prefs.devices:
    d.use = d.type == "OPTIX"
scene.cycles.device = "GPU"
scene.cycles.samples = 1
colour.interpolation = "Closest"
padded = bpy.data.images.new(f"{NAME}_padded", ATLAS, ATLAS, alpha=False)
padded.colorspace_settings.name = "sRGB"
target = nodes.new("ShaderNodeTexImage")
target.image = padded
nodes.active = target
bake = scene.render.bake
bake.use_selected_to_active = False
bake.margin, bake.margin_type = 64, "EXTEND"
bake.use_pass_direct = bake.use_pass_indirect = False
bake.use_pass_color = True
t = time.time()
with bpy.context.temp_override(object=body, active_object=body, selected_objects=[body]):
    bpy.ops.object.bake(type="DIFFUSE")
report["pad_s"] = round(time.time() - t, 1)
nodes.remove(target)
colour.image, colour.interpolation = padded, "Linear"
bpy.data.images.remove(atlas)
# Its file names the glb's image ("basecolor" is how reduce knows a colour map, as in Tripo's own names).
padded.filepath_raw = C.build(f"{C.title}_Atlas_basecolor.jpg")
padded.file_format = "JPEG"
padded.save(quality=95)

bpy.ops.export_scene.gltf(filepath=C.build(f"{NAME}_joined.glb"), export_format="GLB", use_selection=True,
                          export_image_format="JPEG", export_jpeg_quality=95, export_yup=True)
report["total_s"] = round(time.time() - t0, 1)
json.dump(report, open(C.checks("join.json"), "w"), indent=1)
print("JOIN", json.dumps(report))
