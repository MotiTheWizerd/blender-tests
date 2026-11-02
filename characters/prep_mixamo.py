"""A character, ready for Mixamo's auto-rigger.

    blender -b --factory-startup -P prep_mixamo.py -- viking_warrior     (a folder beside this file)

source_apose.jpg  Qwen Image 2.1 via teikna (A-pose, flat light, empty hands)
source_hunyuan.glb  Hunyuan3D v2.5 via brokkr (50k faces, one PBR texture)
-> <name>_mixamo.fbx: 1.85 m tall, feet on the ground at the origin, facing -Y (Blender
front), transforms applied, texture embedded. Upload it at mixamo.com (Upload Character); the
rigger asks for chin, wrists, elbows, knees and groin markers.
"""
import bpy, os
from mathutils import Vector

import sys
NAME = sys.argv[sys.argv.index("--") + 1]
HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), NAME)
HEIGHT = 1.85
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=os.path.join(HERE, "source_hunyuan.glb"))
mesh = next(o for o in bpy.context.scene.objects if o.type == "MESH")
me = mesh.data
me.transform(mesh.matrix_world)          # the glTF's Y-up root baked into the vertices
mesh.parent = None
mesh.matrix_world.identity()
for o in list(bpy.context.scene.objects):
    if o is not mesh:
        bpy.data.objects.remove(o, do_unlink=True)
xs = [v.co.x for v in me.vertices]; ys = [v.co.y for v in me.vertices]; zs = [v.co.z for v in me.vertices]
s = HEIGHT / (max(zs) - min(zs))
cx, cy, z0 = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2, min(zs)
for v in me.vertices:
    v.co = Vector(((v.co.x - cx) * s, (v.co.y - cy) * s, (v.co.z - z0) * s))
mesh.name = me.name = "".join(w.title() for w in NAME.split("_"))
for p in me.polygons:
    p.use_smooth = True
img = next((i for i in bpy.data.images if i.size[0] > 0), None)
if img:
    img.filepath_raw = os.path.join(HERE, f"{NAME}_basecolor.png"); img.file_format = "PNG"; img.save()
bpy.ops.export_scene.fbx(filepath=os.path.join(HERE, f"{NAME}_mixamo.fbx"), use_selection=False,
                         object_types={"MESH"}, apply_unit_scale=True, apply_scale_options="FBX_SCALE_ALL",
                         path_mode="COPY", embed_textures=True, mesh_smooth_type="FACE")
xs = [v.co.x for v in me.vertices]; ys = [v.co.y for v in me.vertices]; zs = [v.co.z for v in me.vertices]
print(f"PREPPED {len(me.polygons)} faces, {max(xs)-min(xs):.2f} x {max(ys)-min(ys):.2f} x {max(zs)-min(zs):.2f} m, texture {img and img.size[:]}")
