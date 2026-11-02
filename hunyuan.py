"""Image-to-3D on the public Hunyuan3D-2 space (Hugging Face). Usage: hunyuan.py NAME IMAGE"""
import shutil, sys, time
from gradio_client import Client, handle_file
name, image = sys.argv[1], sys.argv[2]
t = time.time()
c = Client("tencent/Hunyuan3D-2", verbose=False)
out = c.predict(caption=None, image=handle_file(image), mv_image_front=None, mv_image_back=None,
                mv_image_left=None, mv_image_right=None, steps=30, guidance_scale=5.0, seed=1234,
                octree_resolution=256, check_box_rembg=True, num_chunks=8000, randomize_seed=False,
                api_name="/generation_all")
for i, f in enumerate(out[:2]):
    path = f["value"] if isinstance(f, dict) and "value" in f else (f.get("path") if isinstance(f, dict) else f)
    ext = path.rsplit(".", 1)[-1]
    dst = f"source/ai3d/{name}_{'white' if i == 0 else 'textured'}.{ext}"
    shutil.copy(path, dst)
    print("saved", dst)
print("stats", out[3] if len(out) > 3 else None, f"{time.time() - t:.0f}s")
