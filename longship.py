"""The longship at night: hull, striped sail, shields, two ravens on the yard, an ocean that moves.
Sent into the live Blender through bl.py; builds a fresh scene called 'longship'."""
import bpy, math, bmesh
from mathutils import Vector

D = bpy.data
old = D.scenes.get("longship")
if old:
    for ob in list(old.objects):
        D.objects.remove(ob, do_unlink=True)
    D.scenes.remove(old)
sc = D.scenes.new("longship")
for win in bpy.context.window_manager.windows:
    win.scene = sc


def link(ob):
    sc.collection.objects.link(ob)
    return ob


def mat(name, color, rough=0.5, metal=0.0, emit=None, strength=0.0):
    m = D.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emit:
        b.inputs["Emission Color"].default_value = (*emit, 1)
        b.inputs["Emission Strength"].default_value = strength
    return m


def mesh_obj(name, verts, faces, material):
    me = D.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(material)
    return link(D.objects.new(name, me))


wood = mat("oak", (0.16, 0.08, 0.035), 0.7)
dark_wood = mat("tarred oak", (0.05, 0.03, 0.02), 0.6)
feathers = mat("raven", (0.004, 0.004, 0.006), 0.35)
beak = mat("beak", (0.02, 0.02, 0.02), 0.25)
eye = mat("eye", (0.9, 0.7, 0.2), 0.2, emit=(1.0, 0.6, 0.1), strength=3)

# ---- the ship rides an empty, so one driver rocks everything aboard ----
ship = link(D.objects.new("ship", None))

# ---- hull: lofted U sections, the sheer sweeping up at both ends ----
L, W, DEPTH = 7.0, 1.5, 1.0
ST, SEC = 41, 17
verts, faces = [], []
for i in range(ST):
    x = -1 + 2 * i / (ST - 1)
    w = W * max(1 - x * x, 0) ** 0.55
    top = 0.35 + 1.5 * x ** 6
    keel = -DEPTH * max(1 - x * x, 0) ** 0.5
    for j in range(SEC):
        a = math.pi * j / (SEC - 1)                  # 0 = port rail, pi = starboard rail
        y = w * math.cos(a)
        z = keel + (top - keel) * (1 - math.sin(a) ** 1.6)
        verts.append((x * L, y, z))
for i in range(ST - 1):
    for j in range(SEC - 1):
        a = i * SEC + j
        faces.append((a, a + 1, a + SEC + 1, a + SEC))
hull = mesh_obj("hull", verts, faces, wood)
hull.parent = ship
hull.modifiers.new("planks", "SOLIDIFY").thickness = 0.06

# ---- stem and stern posts curling into a spiral ----
for side in (1, -1):
    cu = D.curves.new(f"post{side}", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = 0.11
    cu.bevel_resolution = 3
    sp = cu.splines.new("POLY")
    pts = []
    for k in range(40):
        t = k / 39
        ang = t * math.pi * 1.6
        r = 1.1 * (1 - 0.65 * t)
        pts.append((side * (L + 0.25 + r * math.sin(ang) * 0.9), 0, 1.6 + r * (1 - math.cos(ang)) * 1.1))
    sp.points.add(len(pts) - 1)
    for k, p in enumerate(pts):
        sp.points[k].co = (*p, 1)
    cu.materials.append(dark_wood)
    link(D.objects.new(f"post {side}", cu)).parent = ship

# ---- mast, yard and a billowing striped sail ----
bpy.ops.mesh.primitive_cylinder_add(radius=0.12, depth=8, location=(0, 0, 4))
mast = bpy.context.object; mast.name = "mast"; mast.data.materials.append(dark_wood); mast.parent = ship
bpy.ops.mesh.primitive_cylinder_add(radius=0.08, depth=7.2, location=(0, 0, 7.4), rotation=(math.pi / 2, 0, 0))
yard = bpy.context.object; yard.name = "yard"; yard.data.materials.append(dark_wood); yard.parent = ship

sail_m = D.materials.new("sail")
sail_m.use_nodes = True
nt = sail_m.node_tree
b = nt.nodes["Principled BSDF"]
tc = nt.nodes.new("ShaderNodeTexCoord")
sep = nt.nodes.new("ShaderNodeSeparateXYZ")
mul = nt.nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"; mul.inputs[1].default_value = 7
mod = nt.nodes.new("ShaderNodeMath"); mod.operation = "PINGPONG"; mod.inputs[1].default_value = 1
gt = nt.nodes.new("ShaderNodeMath"); gt.operation = "GREATER_THAN"; gt.inputs[1].default_value = 0.5
mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"
mix.inputs["A"].default_value = (0.55, 0.04, 0.03, 1)
mix.inputs["B"].default_value = (0.85, 0.78, 0.62, 1)
nt.links.new(tc.outputs["UV"], sep.inputs[0])
nt.links.new(sep.outputs["X"], mul.inputs[0])
nt.links.new(mul.outputs[0], mod.inputs[0])
nt.links.new(mod.outputs[0], gt.inputs[0])
nt.links.new(gt.outputs[0], mix.inputs["Factor"])
nt.links.new(mix.outputs["Result"], b.inputs["Base Color"])
b.inputs["Roughness"].default_value = 0.85
b.inputs["Subsurface Weight"].default_value = 0.0

GU, GV = 24, 18
sv, sf, uvs = [], [], []
for v in range(GV + 1):
    for u in range(GU + 1):
        uu, vv = u / GU, v / GV
        y = -3.4 + 6.8 * uu
        z = 7.35 - 5.0 * vv
        x = 0.9 * math.sin(math.pi * uu) * math.sin(math.pi * (0.15 + 0.85 * vv)) + 0.12
        sv.append((x, y, z))
for v in range(GV):
    for u in range(GU):
        a = v * (GU + 1) + u
        sf.append((a, a + 1, a + GU + 2, a + GU + 1))
sail = mesh_obj("sail", sv, sf, sail_m)
uv = sail.data.uv_layers.new(name="UV")
for poly in sail.data.polygons:
    for li in poly.loop_indices:
        vi = sail.data.loops[li].vertex_index
        uv.data[li].uv = ((vi % (GU + 1)) / GU, 1 - (vi // (GU + 1)) / GV)
sail.parent = ship

# ---- shields along both rails ----
colors = [(0.6, 0.05, 0.03), (0.85, 0.7, 0.2), (0.08, 0.15, 0.4)]
for side in (1, -1):
    for k in range(9):
        x = -4.6 + k * 1.15
        w = W * max(1 - (x / L) ** 2, 0) ** 0.55
        top = 0.35 + 1.5 * (x / L) ** 6
        bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.48, depth=0.07,
                                            location=(x, side * (w + 0.06), top - 0.12),
                                            rotation=(math.pi / 2, 0, 0))
        s = bpy.context.object; s.name = f"shield {side} {k}"
        s.data.materials.append(mat(f"shield{side}{k}", colors[(k + (side > 0)) % 3], 0.5))
        s.parent = ship
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.13, location=(x, side * (w + 0.11), top - 0.12))
        boss = bpy.context.object; boss.data.materials.append(mat("iron", (0.5, 0.5, 0.52), 0.3, 1.0)); boss.parent = ship


# ---- two ravens on the yard: Huginn ahead, Muninn looking home ----
def raven(name, y, facing):
    root = link(D.objects.new(name, None))
    root.location = (0, y, 7.55)
    root.rotation_euler = (0, 0, facing)
    root.parent = ship
    parts = []
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.3, location=(0, 0, 0.32)); body = bpy.context.object
    body.scale = (1.45, 0.8, 0.85); parts.append((body, feathers))
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.19, location=(0.42, 0, 0.62)); parts.append((bpy.context.object, feathers))
    bpy.ops.mesh.primitive_cone_add(radius1=0.07, depth=0.28, location=(0.66, 0, 0.6), rotation=(0, math.pi / 2 + 0.25, 0))
    parts.append((bpy.context.object, beak))
    for sy in (1, -1):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.035, location=(0.53, sy * 0.13, 0.68)); parts.append((bpy.context.object, eye))
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.3, location=(-0.08, sy * 0.24, 0.38)); wing = bpy.context.object
        wing.scale = (1.5, 0.25, 0.6); wing.rotation_euler = (sy * 0.2, 0.15, 0); parts.append((wing, feathers))
    bpy.ops.mesh.primitive_cone_add(radius1=0.2, radius2=0.02, depth=0.6, location=(-0.6, 0, 0.26), rotation=(0, -math.pi / 2 - 0.3, 0))
    tail = bpy.context.object; tail.scale = (1, 1.4, 0.4); parts.append((tail, feathers))
    for ob, m in parts:
        ob.data.materials.append(m)
        if hasattr(ob.data, "polygons"):
            for p in ob.data.polygons:
                p.use_smooth = True
        ob.parent = root
    return root


huginn = raven("Huginn", 2.2, 0.0)            # faces the bow, scouting ahead
muninn = raven("Muninn", -2.2, math.pi)       # faces the stern, looking home

# ---- the sea ----
me = D.meshes.new("sea")
sea = link(D.objects.new("sea", me))
oc = sea.modifiers.new("ocean", "OCEAN")
oc.geometry_mode = "GENERATE"
oc.resolution = 7
oc.spatial_size = 60
oc.repeat_x = oc.repeat_y = 3
oc.wave_scale = 0.9
oc.choppiness = 1.1
oc.wind_velocity = 9
sea.location = (-90, -90, 0)
sea_m = mat("night sea", (0.004, 0.012, 0.02), 0.06)
me.materials.append(sea_m)
fc = sea.driver_add('modifiers["ocean"].time')
fc.driver.expression = "frame / 24"

# ---- the ship rocks and drifts ----
for idx, expr in ((0, "sin(frame / 23) * 0.045"), (1, "sin(frame / 31 + 1) * 0.03")):
    fc = ship.driver_add("rotation_euler", idx)
    fc.driver.expression = expr
fc = ship.driver_add("location", 2)
fc.driver.expression = "sin(frame / 17) * 0.18 + 0.15"

# ---- night: dark sky with stars, a moon, moonlight, a lantern aboard ----
w = D.worlds.new("night sky")
sc.world = w
w.use_nodes = True
nt = w.node_tree
bg = nt.nodes["Background"]
tc = nt.nodes.new("ShaderNodeTexCoord")
noise = nt.nodes.new("ShaderNodeTexNoise"); noise.inputs["Scale"].default_value = 420
ramp = nt.nodes.new("ShaderNodeValToRGB")
ramp.color_ramp.elements[0].position = 0.72
ramp.color_ramp.elements[1].position = 0.76
grad = nt.nodes.new("ShaderNodeMix"); grad.data_type = "RGBA"; grad.blend_type = "ADD"
grad.inputs["A"].default_value = (0.004, 0.007, 0.02, 1)
nt.links.new(tc.outputs["Generated"], noise.inputs["Vector"])
nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
nt.links.new(ramp.outputs["Color"], grad.inputs["B"])
grad.inputs["Factor"].default_value = 0.6
nt.links.new(grad.outputs["Result"], bg.inputs["Color"])

bpy.ops.mesh.primitive_uv_sphere_add(radius=6, location=(-60, 120, 38))
moon = bpy.context.object; moon.name = "moon"
moon.data.materials.append(mat("moon", (1, 1, 1), emit=(0.85, 0.9, 1.0), strength=6))
sun = D.lights.new("moonlight", "SUN"); sun.energy = 1.4; sun.color = (0.62, 0.72, 1.0)
s = link(D.objects.new("moonlight", sun)); s.rotation_euler = (math.radians(60), 0, math.radians(200))
lamp = D.lights.new("lantern", "POINT"); lamp.energy = 160; lamp.color = (1.0, 0.55, 0.2); lamp.shadow_soft_size = 0.3
lt = link(D.objects.new("lantern", lamp)); lt.location = (L - 0.8, 0, 2.2); lt.parent = ship

# ---- camera low over the water, three quarters from the bow ----
cam = link(D.objects.new("camera", D.cameras.new("camera")))
cam.data.lens = 32
cam.location = (16, -15, 3.2)
aim = link(D.objects.new("aim", None)); aim.location = (0, 0, 3.0)
t = cam.constraints.new("TRACK_TO"); t.target = aim
sc.camera = cam
sc.frame_start, sc.frame_end = 1, 480
sc.render.resolution_x, sc.render.resolution_y = 1280, 720
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Medium High Contrast"

for win in bpy.context.window_manager.windows:
    for area in win.screen.areas:
        if area.type == "VIEW_3D":
            sp = area.spaces.active
            sp.shading.type = "RENDERED"
            sp.region_3d.view_perspective = "CAMERA"
            sp.overlay.show_floor = False
            sp.overlay.show_axis_x = sp.overlay.show_axis_y = False
print("longship built:", len(sc.objects), "objects")
