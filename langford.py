"""A Langford pairing (n=7) as glowing rainbow arcs over a dark floor.

Run:  blender --background --python langford.py
Writes langford.blend (open it and orbit) and langford.png (a render).
"""
import bpy, math, os, colorsys

HERE = os.path.dirname(os.path.abspath(__file__))
ROW = [1, 4, 1, 5, 6, 7, 4, 2, 3, 5, 2, 6, 3, 7]  # each k has k numbers between its pair
N = max(ROW)
STEP = 1.0

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def emission(name, rgb, strength):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*rgb, 1)
    em.inputs["Strength"].default_value = strength
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs[0], out.inputs[0])
    return m


def arc(k, a, b, up):
    """A half circle from slot a to slot b, as a thick curve."""
    cu = bpy.data.curves.new(f"arc{k}", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = 0.06
    cu.bevel_resolution = 4
    sp = cu.splines.new("POLY")
    cx, r = (a + b) / 2 * STEP, (b - a) / 2 * STEP
    pts = 48
    sp.points.add(pts - 1)
    for i in range(pts):
        t = math.pi * i / (pts - 1)
        x = cx - r * math.cos(t)
        z = r * math.sin(t) * (1 if up else 0.6)
        y = 0 if up else -0.0
        sp.points[i].co = (x, y if up else 0.0, z if up else -z, 1)
    ob = bpy.data.objects.new(f"pair {k}", cu)
    hue = (k - 1) / N * 0.8
    ob.data.materials.append(emission(f"glow{k}", colorsys.hsv_to_rgb(hue, 0.85, 1.0), 1.6))
    scene.collection.objects.link(ob)
    # a small bead on each end, the number's two places in the row
    for s in (a, b):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.14, location=(s * STEP, 0, 0))
        bpy.context.object.data.materials.append(ob.data.materials[0])


# alternate arcs above and below the row, like the wake drawings
for k in range(1, N + 1):
    a, b = [i for i, v in enumerate(ROW) if v == k]
    arc(k, a, b, up=(k % 2 == 1))

# a dark reflective floor, under the lower arcs
bpy.ops.mesh.primitive_plane_add(size=80, location=(len(ROW) / 2, 0, -4.5))
floor = bpy.context.object
fm = bpy.data.materials.new("floor")
fm.use_nodes = True
bsdf = fm.node_tree.nodes["Principled BSDF"]
bsdf.inputs["Base Color"].default_value = (0.01, 0.01, 0.015, 1)
bsdf.inputs["Roughness"].default_value = 0.15
floor.data.materials.append(fm)

# world: near black
scene.world = bpy.data.worlds.new("night")
scene.world.use_nodes = True
scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.002, 0.002, 0.004, 1)

# camera, slightly from the front and above
cx = (len(ROW) - 1) / 2 * STEP
bpy.ops.object.camera_add(location=(cx, -17, 3.5))
cam = bpy.context.object
target = bpy.data.objects.new("look here", None)
target.location = (cx, 0, 0.5)
scene.collection.objects.link(target)
c = cam.constraints.new("TRACK_TO")
c.target = target
scene.camera = cam

# a slow turntable: the target spins, the camera rides with it
cam.parent = target
cam.location = (0, -26, 5.0)
scene.frame_start, scene.frame_end = 1, 240
target.rotation_euler = (0, 0, 0)
target.keyframe_insert("rotation_euler", frame=1)
target.rotation_euler = (0, 0, math.radians(360))
target.keyframe_insert("rotation_euler", frame=240)
for fc in target.animation_data.action.fcurves if hasattr(target.animation_data.action, "fcurves") else []:
    for kp in fc.keyframe_points:
        kp.interpolation = "LINEAR"

# Eevee with bloom-like glow comes from the compositor-free emission; keep it light for an Intel iGPU
scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items.keys() else "BLENDER_EEVEE"
scene.render.resolution_x, scene.render.resolution_y = 1280, 720
scene.render.filepath = os.path.join(HERE, "langford.png")
scene.view_settings.view_transform = "AgX"

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "langford.blend"))
bpy.ops.render.render(write_still=True)
print("DONE", scene.render.filepath)
