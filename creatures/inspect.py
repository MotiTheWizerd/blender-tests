"""Step 1 for a creature: what the AI model is, before anything is cut.

    blender -b --factory-startup -P inspect.py -- dragon     (a folder beside this file, holding source_tripo.glb)

Prints the meshes (vertices, faces, the shells once the UV seams are welded, open edges), the materials and their images, and the
size; writes <name>/inspect.json and four views (front, side, top, three-quarter) to <name>/inspect_<view>.png.
"""
import bmesh, bpy, json, os, sys
from mathutils import Vector

NAME = sys.argv[sys.argv.index("--") + 1]
HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), NAME)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=os.path.join(HERE, "source_tripo.glb"))
scene = bpy.context.scene
meshes = [o for o in scene.objects if o.type == "MESH"]


def shells(me):
    """The real shells, sizes biggest first, and the open and non-manifold edges. A glTF splits its vertices along
    the UV seams (the Tripo dragon: 388 loose patches), so they are welded first; what is still apart is apart."""
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    seen, sizes = set(), []
    for v in bm.verts:
        if v.index in seen:
            continue
        stack, count = [v], 0
        seen.add(v.index)
        while stack:
            x = stack.pop()
            count += 1
            for e in x.link_edges:
                y = e.other_vert(x)
                if y.index not in seen:
                    seen.add(y.index)
                    stack.append(y)
        sizes.append(count)
    welded = len(bm.verts)
    open_edges = sum(1 for e in bm.edges if e.is_boundary)
    non_manifold = sum(1 for e in bm.edges if not e.is_manifold) - open_edges
    bm.free()
    return sorted(sizes, reverse=True), welded, open_edges, non_manifold


report = {"objects": [], "materials": [], "images": []}
lo, hi = Vector((1e9,) * 3), Vector((-1e9,) * 3)
for o in meshes:
    me = o.data
    for v in (o.matrix_world @ Vector(c) for c in o.bound_box):
        lo = Vector(map(min, lo, v)); hi = Vector(map(max, hi, v))
    sizes, welded, open_edges, non_manifold = shells(me)
    report["objects"].append({
        "name": o.name, "vertices": len(me.vertices), "welded_vertices": welded, "faces": len(me.polygons),
        "triangles": sum(len(f.vertices) - 2 for f in me.polygons), "uv_layers": [u.name for u in me.uv_layers],
        "materials": [m.name for m in me.materials if m], "shells": len(sizes), "biggest_shells": sizes[:8],
        "open_edges": open_edges, "non_manifold_edges": non_manifold,
    })
for m in bpy.data.materials:
    if m.use_nodes:
        links = {}
        for node in m.node_tree.nodes:
            if node.type == "TEX_IMAGE" and node.image:
                for link in node.outputs[0].links:
                    links[link.to_socket.name] = node.image.name
        report["materials"].append({"name": m.name, "maps": links})
for im in bpy.data.images:
    if im.size[0]:
        report["images"].append({"name": im.name, "size": list(im.size), "colorspace": im.colorspace_settings.name})
report["size_m"] = [round(x, 3) for x in (hi - lo)]
report["min"] = [round(x, 3) for x in lo]
report["armatures"] = [o.name for o in scene.objects if o.type == "ARMATURE"]
report["animations"] = [a.name for a in bpy.data.actions]
json.dump(report, open(os.path.join(HERE, "inspect.json"), "w"), indent=1)
print("INSPECT", json.dumps(report, indent=1))

# Four views in Workbench with the texture's colours, the model framed by its bounds.
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "TEXTURE"
scene.render.resolution_x, scene.render.resolution_y = 1200, 900
scene.render.film_transparent = False
world = bpy.data.worlds.new("w"); scene.world = world
center, size = (lo + hi) / 2, max(hi - lo)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
scene.collection.objects.link(cam); scene.camera = cam
cam.data.type = "ORTHO"; cam.data.ortho_scale = size * 1.15
# Blender front is -Y; the glTF importer turns glTF's +Z forward into -Y.
# Top is tipped a hair off vertical, or the picture's up is undefined.
views = {"front": (0, -1, 0), "side": (1, 0, 0), "top": (0, -0.001, 1), "three_quarter": (0.8, -1, 0.45)}
for view, d in views.items():
    d = Vector(d).normalized()
    cam.location = center + d * size * 3
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    cam.data.clip_end = size * 10
    scene.render.filepath = os.path.join(HERE, f"inspect_{view}.png")
    bpy.ops.render.render(write_still=True)
print("VIEWS", list(views))
