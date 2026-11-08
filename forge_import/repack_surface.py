"""The bake writes metal in red and smoothness in green (<Name>_Surface.png); URP reads smoothness from alpha."""
import os
import sys

import bpy
import numpy as np

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
for name in sys.argv[sys.argv.index("--") + 1:]:
    src = os.path.abspath(f"{name}/{name}_Surface.png")
    img = bpy.data.images.load(src)
    img.colorspace_settings.name = "Non-Color"
    a = np.empty(img.size[0] * img.size[1] * 4, np.float32)
    img.pixels.foreach_get(a)
    a = a.reshape(-1, 4)
    out = np.zeros_like(a)
    out[:, 0] = a[:, 0]
    out[:, 3] = a[:, 1]
    im = bpy.data.images.new(name, img.size[0], img.size[1], alpha=True)
    im.colorspace_settings.name = "Non-Color"
    im.pixels.foreach_set(out.ravel())
    st = bpy.context.scene.render.image_settings
    st.file_format, st.color_mode, st.compression = "PNG", "RGBA", 100
    im.save_render(os.path.abspath(f"{name}/{name}_MetallicSmoothness.png"), scene=bpy.context.scene)
    os.remove(src)
    print("REPACKED", name)
