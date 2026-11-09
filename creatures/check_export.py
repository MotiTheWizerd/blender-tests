"""Step 4b: the exported FBX read back, to look at: <name>/export_colliders.png (the hulls, each its own colour, over
the see-through LOD0) and export_lods.png (LOD0, 1, 2 side by side).

    blender -b --factory-startup -P check_export.py -- dragon
"""
import bpy, os, sys
from mathutils import Vector
NAME = sys.argv[sys.argv.index("--") + 1]; Title = NAME.capitalize()
HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), NAME)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=os.path.join(HERE, "forge", Title, f"{Title}.fbx"))
scene = bpy.context.scene
objs = {o.name: o for o in scene.objects if o.type == "MESH"}
lods = [objs[f"{Title}_LOD{i}"] for i in range(3)]
cols = [o for n, o in objs.items() if n.endswith("_COL")]
scene.render.engine = "BLENDER_WORKBENCH"; sh = scene.display.shading; sh.light = "STUDIO"
scene.render.resolution_x, scene.render.resolution_y = 1600, 1000
scene.world = bpy.data.worlds.new("w")
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam); scene.camera = cam
cam.data.type = "ORTHO"; cam.data.clip_end = 500
def shoot(path, centre, scale, d=(0.8, -1, 0.5)):
    d = Vector(d).normalized(); cam.location = centre + d * 60
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler(); cam.data.ortho_scale = scale
    scene.render.filepath = path; bpy.ops.render.render(write_still=True)
print("DIMS", [round(x, 2) for x in lods[0].dimensions], "LOCATION", [round(x, 2) for x in lods[0].location])
for o in lods[1:]: o.hide_render = True
sh.color_type = "RANDOM"; sh.show_xray = True; sh.xray_alpha = 0.6
for o in cols: o.display_type = "SOLID"
shoot(os.path.join(HERE, "export_colliders.png"), Vector((0, 0, 3.5)), 17)
for o in cols: o.hide_render = True
sh.show_xray = False; sh.color_type = "SINGLE"
for i, o in enumerate(lods): o.hide_render = False; o.location.x += (i - 1) * 14
shoot(os.path.join(HERE, "export_lods.png"), Vector((0, 0, 3.5)), 44, (0, -1, 0.25))
