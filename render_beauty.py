"""Render the beauty shots headless: blender -b langford.blend -P render_beauty.py [-- preview]
preview = 960x540 at 24 samples (~30-60 s), for judging light; without it, 1920x1080 at 96 (+ denoise)."""
import bpy, os, sys, time

sc = bpy.data.scenes["viking_beauty"]
preview = "preview" in sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else False
cams = [a for a in (sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []) if a.startswith("cam_")] or ["cam_hero", "cam_hilt"]
out = os.path.join(os.path.dirname(bpy.data.filepath), "export", "beauty")
os.makedirs(out, exist_ok=True)
if preview:
    sc.render.resolution_percentage = 50
    sc.cycles.samples = 24
for cam in cams:
    t = time.time()
    sc.camera = bpy.data.objects[cam]
    sc.render.filepath = os.path.join(out, f"viking_{cam[4:]}{'_preview' if preview else ''}.png")
    bpy.ops.render.render(write_still=True, scene=sc.name)
    print(f"RENDERED {sc.render.filepath} in {time.time() - t:.0f}s", flush=True)
