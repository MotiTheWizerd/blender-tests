"""Render a Mixamo animation FBX as a short MP4 (EEVEE, fast): a turntable-free studio shot.

    blender -b --factory-startup -P render_anim.py -- viking_hero/anim/dancing.fbx [frames]
"""
import bpy, math, os, sys
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
SRC = os.path.abspath(args[0]); FRAMES = int(args[1]) if len(args) > 1 else 0
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
bpy.ops.import_scene.fbx(filepath=SRC, automatic_bone_orientation=True)
arm = next(o for o in sc.objects if o.type == "ARMATURE")
meshes = [o for o in sc.objects if o.type == "MESH"]
act = arm.animation_data.action if arm.animation_data else None
start, end = (int(act.frame_range[0]), int(act.frame_range[1])) if act else (1, 1)
if FRAMES:
    end = min(end, start + FRAMES - 1)
sc.frame_start, sc.frame_end = start, end
print("ANIM", act and act.name, start, end, "meshes", [m.name for m in meshes],
      "textures", [i.name for i in bpy.data.images])

# the space he moves through, measured over the clip
dg = bpy.context.evaluated_depsgraph_get()
lo, hi = Vector((1e9,) * 3), Vector((-1e9,) * 3)
for f in range(start, end + 1, max(1, (end - start) // 12)):
    sc.frame_set(f)
    for m in meshes:
        for c in m.evaluated_get(dg).bound_box:
            p = m.matrix_world @ Vector(c)
            lo = Vector(map(min, lo, p)); hi = Vector(map(max, hi, p))
centre, size = (lo + hi) / 2, hi - lo
print("SPACE", tuple(round(v, 2) for v in lo), tuple(round(v, 2) for v in hi))

floor = bpy.data.meshes.new("floor")
floor.from_pydata([(-20, -20, lo.z), (20, -20, lo.z), (20, 20, lo.z), (-20, 20, lo.z)], [], [(0, 1, 2, 3)])
fo = bpy.data.objects.new("floor", floor); sc.collection.objects.link(fo)
fm = bpy.data.materials.new("floor"); fm.use_nodes = True
fm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.08, 0.08, 0.09, 1)
fm.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.8
floor.materials.append(fm)
w = bpy.data.worlds.new("w"); w.use_nodes = True
w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.03, 0.035, 0.045, 1)
sc.world = w

def light(name, kind, loc, energy, size=1.0, color=(1, 1, 1)):
    d = bpy.data.lights.new(name, kind); d.energy = energy; d.color = color
    if kind == "AREA":
        d.size = size
    o = bpy.data.objects.new(name, d); o.location = loc; sc.collection.objects.link(o)
    o.rotation_euler = (centre - o.location).to_track_quat("-Z", "Y").to_euler()

H = size.z
light("key", "AREA", centre + Vector((-2.0, -2.5, 2.2)) * H, 600 * H * H, 2.0 * H, (1, 0.92, 0.82))
light("rim", "AREA", centre + Vector((1.8, 2.0, 1.6)) * H, 500 * H * H, 1.0 * H, (0.7, 0.8, 1))
light("fill", "AREA", centre + Vector((2.5, -2.0, 0.5)) * H, 120 * H * H, 2.5 * H)

cd = bpy.data.cameras.new("cam"); cd.lens = 50
cam = bpy.data.objects.new("cam", cd); sc.collection.objects.link(cam); sc.camera = cam
reach = max(size.x, size.y, size.z) * 1.25
cam.location = centre + Vector((0.35, -1, 0.12)).normalized() * (reach / math.tan(cd.angle / 2) * 0.62)
cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()

engines = {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
sc.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
sc.render.resolution_x, sc.render.resolution_y = 640, 640
# This machine renders EEVEE on an Intel UHD 620: ~11 s a frame at 960 px and 64 samples (s968).
sc.eevee.taa_render_samples = 8
sc.render.fps = 30
sc.view_settings.view_transform = "AgX"
# Blender 5 has no FFMPEG file_format here: frames as PNG, then the system's ffmpeg stitches them.
import shutil, subprocess, tempfile
frames = tempfile.mkdtemp(prefix="anim-")
sc.render.image_settings.file_format = "PNG"
sc.render.filepath = os.path.join(frames, "f_")
bpy.ops.render.render(animation=True)
out = os.path.splitext(SRC)[0] + ".mp4"
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "30", "-start_number", str(start),
                "-i", os.path.join(frames, "f_%04d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", out], check=True)
shutil.copy(os.path.join(frames, f"f_{start + (end - start) // 2:04d}.png"), os.path.splitext(SRC)[0] + "_mid.png")
shutil.rmtree(frames)
print("RENDERED", out, end - start + 1, "frames")
