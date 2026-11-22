"""The four fitted body types in one .blend to look at: each a live MPFB human (its sliders in MPFB's panels) with
its Tripo body beside it, scaled to the same height.

    blender -b -P show_types.py

Reads types.json (each type's Tripo file) and checks/fit_<type>.json (fit_macros.py). Writes build/body_types.blend.
"""
import bpy, json, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from her import create  # noqa: E402

_TYPES = json.load(open(os.path.join(HERE, "types.json")))
SOURCES = os.path.join(HERE, os.path.expanduser(_TYPES["sources"]))
TYPES = [(t["name"], t["source"]) for t in _TYPES["types"]]
SPACING = 1.8  # m between types; each Tripo body stands 0.8 m to the right of its MPFB one

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def body_extent(obj):
    """Lowest and highest z of the visible body (MPFB's helpers left out)."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    P = np.array([ev.matrix_world @ v.co for v in me.vertices])
    ev.to_mesh_clear()
    return P[:, 2].min(), P[:, 2].max()


def label(text, x):
    curve = bpy.data.curves.new(text, "FONT")
    curve.body = text
    curve.size = 0.12
    curve.align_x = "CENTER"
    obj = bpy.data.objects.new("label " + text, curve)
    obj.location = (x + 0.4, 0, 1.95)
    obj.rotation_euler = (1.5708, 0, 0)
    scene.collection.objects.link(obj)


for i, (name, source) in enumerate(TYPES):
    fit = json.load(open(os.path.join(HERE, "checks", "fit_%s.json" % name)))["values"]
    x0 = i * SPACING
    human, _ = create(fit, rig=None)
    human.name = "MPFB " + name
    human.location.x += x0
    bpy.context.view_layer.update()
    lo, hi = body_extent(human)

    before = set(scene.objects)
    path = os.path.join(SOURCES, source)
    if path.endswith(".glb"):
        bpy.ops.import_scene.gltf(filepath=path)
    else:
        bpy.ops.import_scene.fbx(filepath=path)
    new = [o for o in scene.objects if o not in before]
    tripo = [o for o in new if o.type == "MESH"][0]
    bpy.context.view_layer.update()
    P = np.array([tripo.matrix_world @ v.co for v in tripo.data.vertices])
    k = (hi - lo) / (P[:, 2].max() - P[:, 2].min())
    c = np.array([(P[:, 0].min() + P[:, 0].max()) / 2, (P[:, 1].min() + P[:, 1].max()) / 2, P[:, 2].min()])
    P = (P - c) * k + np.array([x0 + 0.8, 0, lo])
    tripo.parent = None
    tripo.matrix_world.identity()
    tripo.data.vertices.foreach_set("co", P.ravel())
    tripo.data.update()
    tripo.name = "Tripo " + name
    for o in new:
        if o is not tripo:
            bpy.data.objects.remove(o, do_unlink=True)
    label(name, x0)
    print(name, "height %.3f m" % (hi - lo), flush=True)

os.makedirs(os.path.join(HERE, "build"), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "build", "body_types.blend"))
