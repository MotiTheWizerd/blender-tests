"""What a Tripo head is: its parts, size, UVs, textures, and six pictures of it.

    blender -b -P probe_head.py -- <tripo file> <tag>

Writes checks/head_<tag>_{front,side,quarter,back}.png (textured, flat light) and
checks/head_<tag>_{solid_front,solid_side}.png (the geometry alone).
"""
import bpy, os, sys, bmesh
import numpy as np

ARGS = sys.argv[sys.argv.index("--") + 1:]
SOURCE, TAG = ARGS[0], ARGS[1]
HERE = os.path.dirname(os.path.abspath(__file__))
CHECKS = os.path.join(HERE, "checks")
os.makedirs(CHECKS, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
if SOURCE.endswith(".glb"):
    bpy.ops.import_scene.gltf(filepath=SOURCE)
else:
    bpy.ops.import_scene.fbx(filepath=SOURCE)
bpy.context.view_layer.update()
for o in scene.objects:
    print("PROBE object", o.type, repr(o.name), "parent", o.parent.name if o.parent else None,
          "scale", [round(s, 4) for s in o.matrix_world.to_scale()], "rot(deg)", [round(np.degrees(a), 1) for a in o.matrix_world.to_euler()])
meshes = [o for o in scene.objects if o.type == "MESH"]
allP = []
for m in meshes:
    me = m.data
    P = np.array([m.matrix_world @ v.co for v in me.vertices])
    allP.append(P)
    lo, hi = P.min(0), P.max(0)
    print("PROBE mesh", repr(m.name), len(me.vertices), "verts", len(me.polygons), "faces",
          "tris", sum(1 for p in me.polygons if len(p.vertices) == 3), "quads", sum(1 for p in me.polygons if len(p.vertices) == 4))
    print("PROBE   bounds lo", lo.round(4).tolist(), "hi", hi.round(4).tolist(), "size", (hi - lo).round(4).tolist())
    print("PROBE   uv layers", [u.name for u in me.uv_layers], "colour attrs", [c.name for c in me.color_attributes],
          "shape keys", [k.name for k in me.shape_keys.key_blocks] if me.shape_keys else None, "vgroups", len(m.vertex_groups))
    if me.uv_layers:
        uv = np.empty(len(me.loops) * 2)
        me.uv_layers[0].data.foreach_get("uv", uv)
        uv = uv.reshape(-1, 2)
        print("PROBE   uv range", uv.min(0).round(3).tolist(), uv.max(0).round(3).tolist())
    for mat in me.materials:
        print("PROBE   material", mat.name if mat else None)
        if mat and mat.use_nodes:
            for n in mat.node_tree.nodes:
                if n.type == "TEX_IMAGE" and n.image:
                    print("PROBE     image", n.image.name, n.image.filepath, list(n.image.size), n.image.colorspace_settings.name,
                          "->", [l.to_node.name + ":" + l.to_socket.name for l in n.outputs[0].links])
    bm = bmesh.new()
    bm.from_mesh(me)
    print("PROBE   boundary edges", sum(1 for e in bm.edges if e.is_boundary), "non-manifold", sum(1 for e in bm.edges if not e.is_manifold))
    # loose parts
    parent = np.arange(len(me.vertices))
    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    E = np.empty(len(me.edges) * 2, dtype=np.int64)
    me.edges.foreach_get("vertices", E)
    for a, b in E.reshape(-1, 2):
        ra, rb = root(a), root(b)
        if ra != rb:
            parent[ra] = rb
    roots = np.array([root(i) for i in range(len(me.vertices))])
    uniq, counts = np.unique(roots, return_counts=True)
    order = np.argsort(-counts)
    print("PROBE   loose parts", len(uniq), "sizes", counts[order][:12].tolist())
    for r in uniq[order][:8]:
        Q = P[roots == r]
        print("PROBE     part", int((roots == r).sum()), "verts centre", Q.mean(0).round(4).tolist(), "size", (Q.max(0) - Q.min(0)).round(4).tolist())
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
# the pictures: ortho, around the whole thing
P = np.concatenate(allP)
lo, hi = P.min(0), P.max(0)
centre = (lo + hi) / 2
span = (hi - lo).max() * 1.15
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
cam.data.ortho_scale = span
cam.data.clip_end = 100
scene.collection.objects.link(cam)
scene.camera = cam
scene.render.resolution_x = scene.render.resolution_y = 1200
world = bpy.data.worlds.new("w")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (1, 1, 1, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 1.0
scene.world = world
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 2.0
scene.collection.objects.link(sun)
VIEWS = {"front": (0, -10, 0, (90, 0, 0)), "side": (10, 0, 0, (90, 0, 90)), "quarter": (7.07, -7.07, 0, (90, 0, 45)),
         "back": (0, 10, 0, (90, 0, 180))}
for engine, names in (("BLENDER_EEVEE", ["front", "side", "quarter", "back"]), ("BLENDER_WORKBENCH", ["front", "side"])):
    scene.render.engine = engine
    if engine == "BLENDER_WORKBENCH":
        scene.display.shading.light = "STUDIO"
        scene.display.shading.color_type = "SINGLE"
    for name in names:
        x, y, z, rot = VIEWS[name]
        cam.location = centre + np.array([x, y, z])
        cam.rotation_euler = [np.radians(a) for a in rot]
        sun.rotation_euler = cam.rotation_euler
        tag = name if engine == "BLENDER_EEVEE" else "solid_" + name
        scene.render.filepath = os.path.join(CHECKS, "head_%s_%s.png" % (TAG, tag))
        bpy.ops.render.render(write_still=True)
        print("PROBE wrote", scene.render.filepath)
