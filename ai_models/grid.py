"""Step 3b for a creature: front, side and top views with a 5 cm grid, to read joints off (the elbows, the wrists).

    blender -b <name>/build/<name>_low.blend -P grid.py [-- centre_z pixels_per_metre]

Writes <name>/checks/grid_<view>.jpg (the blend is in build/): 1500 px a metre, orthographic, centred on (0, 0, 0.3); the line
through the picture's middle is that centre. front: right +X, up +Z; side: right +Y, up +Z; top: right +X, up +Y.
"""
import bpy, numpy as np, os, sys
from mathutils import Vector
# Optional, after "--": the centre's height (0.3) and the pixels a metre (1500), for a model of another size
# (raven_1 stands 0.79 m in its source frame: -- 0.39 1000).
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
Z = float(ARGS[0]) if ARGS else 0.3
scene = bpy.context.scene
o = next(o for o in bpy.data.objects if o.type == "MESH")
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"; scene.display.shading.color_type = "TEXTURE"
W, H = 1600, 1000
scene.render.resolution_x, scene.render.resolution_y = W, H
scene.world = bpy.data.worlds.new("w")
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam); scene.camera = cam
cam.data.type = "ORTHO"; cam.data.clip_end = 10
PX = float(ARGS[1]) if len(ARGS) > 1 else 1500.0      # pixels per metre
cam.data.ortho_scale = W / PX
out = os.path.join(os.path.dirname(os.path.dirname(bpy.data.filepath)), "checks")
# view: camera direction, centre (world), which world axes run right and up in the picture
views = {"front": ((0,-1,0), (0,0,Z), (0, 0)), "side": ((1,0,0), (0,0,Z), (1, 0)), "top": ((0,-0.001,1), (0,0,Z), (2,0))}
for name, (d, c, _) in views.items():
    d = Vector(d).normalized(); c = Vector(c)
    cam.location = c + d * 3
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    bpy.context.view_layer.update()
    right = cam.matrix_world.to_3x3() @ Vector((1,0,0)); up = cam.matrix_world.to_3x3() @ Vector((0,1,0))
    path = os.path.join(out, f"grid_{name}.jpg"); scene.render.filepath = path
    st = scene.render.image_settings; st.file_format, st.color_mode, st.quality = "JPEG", "RGB", 88
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(path); a = np.array(img.pixels[:]).reshape(H, W, 4)
    # grid every 5 cm, brighter every 10 cm; world value at pixel: c.right + (px - W/2)/PX (rows count from the bottom)
    ra = int(np.argmax(np.abs(right))); ua = int(np.argmax(np.abs(up)))
    rs, us = np.sign(right[ra]), np.sign(up[ua])
    for v in np.arange(-1.0, 1.05, 0.05):
        bright = abs(round(v / 0.1) * 0.1 - v) < 1e-6
        px = int(round(W/2 + (v - c[ra]) * rs * PX)); py = int(round(H/2 + (v - c[ua]) * us * PX))
        col = [1, 1, 0, 1] if bright else [0.5, 0.5, 0.2, 1]
        if 0 <= px < W: a[:, px] = col
        if 0 <= py < H: a[py, :] = col
    img.pixels[:] = a.ravel(); img.save()
    print("VIEW", name, "right=", "xyz"[ra], "+" if rs > 0 else "-", "up=", "xyz"[ua], "+" if us > 0 else "-")
