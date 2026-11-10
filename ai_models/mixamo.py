"""A character, ready for Mixamo's auto-rigger (the step after reduce, for model.json "kind": "character").

    blender -b --factory-startup -P mixamo.py -- viking_f_1

Reads build/<name>_low.blend (step 2: the reduced mesh, the AI's colour map). Writes build/<name>_mixamo.fbx:
model.json's "height" tall (metres), feet on the ground at the origin, centred, facing -Y (Blender's front), the
transforms applied, the colour texture embedded; and checks/mixamo_front.jpg, mixamo_side.jpg to look at.

Upload it at mixamo.com (Upload Character). The rigger asks for chin, wrists, elbows, knees and groin markers; then
Download as FBX (with skin, T-pose or the pose it stands in). The rigged FBX goes to unity-game-test
Content/Characters/<Name>/<Name>.fbx with its colour as <Name>_Color.png (ARCHITECTURE.md, "Characters").
"""
import bpy, math, os, sys
from mathutils import Vector

NAME = sys.argv[sys.argv.index("--") + 1]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from place import Creature, pictures_as_jpeg
C = Creature(NAME)
HEIGHT = float(C.spec.get("height", 1.75))

bpy.ops.wm.open_mainfile(filepath=C.blend("low"))
scene = bpy.context.scene
mesh = next(o for o in scene.objects if o.type == "MESH")
me = mesh.data
me.transform(mesh.matrix_world)
mesh.parent = None
mesh.matrix_world.identity()
for o in list(scene.objects):
    if o is not mesh:
        bpy.data.objects.remove(o, do_unlink=True)

xs = [v.co.x for v in me.vertices]; ys = [v.co.y for v in me.vertices]; zs = [v.co.z for v in me.vertices]
s = HEIGHT / (max(zs) - min(zs))
cx, cy, z0 = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2, min(zs)
for v in me.vertices:
    v.co = Vector(((v.co.x - cx) * s, (v.co.y - cy) * s, (v.co.z - z0) * s))
me.update()
mesh.name = me.name = C.title
for p in me.polygons:
    p.use_smooth = True

# model.json "cut" (optional): boxes {"about", "min": [x, y, z], "max": [...]} in the metres above. Their vertices go,
# and the holes they leave are closed. For thin loose bits the rigger can't skin: elf_m_1's goatee, a 4 cm sliver
# hanging in front of the throat, took the neck's weights and waved the head in every clip.
import bmesh
bm = bmesh.new(); bm.from_mesh(me)
for box in C.spec.get("cut", []):
    lo, hi = Vector(box["min"]), Vector(box["max"])
    gone = [v for v in bm.verts if all(lo[i] <= v.co[i] <= hi[i] for i in range(3))]
    bmesh.ops.delete(bm, geom=gone, context="VERTS")
    holes = bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=0)["faces"]
    for f in bmesh.ops.triangulate(bm, faces=holes)["faces"]:
        f.smooth = True
    print(f"MIXAMO cut {box.get('about', '')}: {len(gone)} vertices, {len(holes)} holes closed")
bm.to_mesh(me); bm.free(); me.update()

# Mixamo reads one colour texture: keep only the base colour on the material, so the embedded image is that one.
material = me.materials[0]
nodes = material.node_tree.nodes
bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
colour = bsdf.inputs["Base Color"].links[0].from_node.image
for link in list(material.node_tree.links):
    if link.to_node == bsdf and link.to_socket.name != "Base Color":
        material.node_tree.links.remove(link)
# Mixamo only shows the colour while rigging: 4096 at most keeps the upload small (an 8K map is ~100 MB embedded).
if colour.size[0] > 4096:
    colour.scale(4096, 4096)

out = C.build(f"{NAME}_mixamo.fbx")
bpy.ops.export_scene.fbx(filepath=out, use_selection=False, object_types={"MESH"}, apply_unit_scale=True,
                         apply_scale_options="FBX_SCALE_ALL", path_mode="COPY", embed_textures=True,
                         mesh_smooth_type="FACE")

# The checks: front and side, as the rigger will see her.
pictures_as_jpeg(scene)
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"; scene.display.shading.color_type = "TEXTURE"
scene.render.resolution_x, scene.render.resolution_y = 800, 1000
scene.world = bpy.data.worlds.new("w")
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam); scene.camera = cam
cam.data.type = "ORTHO"; cam.data.ortho_scale = HEIGHT * 1.1
for view, d in {"front": (0, -1, 0), "side": (1, 0, 0)}.items():
    d = Vector(d)
    cam.location = Vector((0, 0, HEIGHT / 2)) + d * 5
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = C.picture(f"mixamo_{view}")
    bpy.ops.render.render(write_still=True)

xs = [v.co.x for v in me.vertices]; ys = [v.co.y for v in me.vertices]; zs = [v.co.z for v in me.vertices]
print(f"MIXAMO {len(me.polygons)} faces, {max(xs)-min(xs):.2f} x {max(ys)-min(ys):.2f} x {max(zs)-min(zs):.2f} m, "
      f"colour {colour.name} {colour.size[:]}, {os.path.getsize(out) / 2**20:.1f} MB -> {out}")
