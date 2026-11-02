"""A basic game-ready one-handed sword for a Unity project.

Conventions (what a Unity weapon pipeline expects):
- metres, real size: 1.15 m overall, blade 0.88 m
- pivot at the centre of the grip (it parents straight onto a hand bone)
- blade along +Z in Blender  -> +Y (up) in Unity after the FBX axis conversion
- one mesh, three material slots: 0 Blade_Steel, 1 Guard_Iron, 2 Grip_Leather
- UVs laid out in one 0..1 atlas, no overlaps between parts
- hard edges split by angle, so the bevels read sharp in Unity's lighting
"""
import bpy, bmesh, math, os

D = bpy.data
OUT = "/mnt/fast/apps/blender-play/export"
os.makedirs(OUT, exist_ok=True)

old = D.scenes.get("sword")
if old:
    for ob in list(old.objects):
        D.objects.remove(ob, do_unlink=True)
    D.scenes.remove(old)
sc = D.scenes.new("sword")
for win in bpy.context.window_manager.windows:
    win.scene = sc

bm = bmesh.new()
part_of = {}          # face -> part name, for the UV layout


def ring(pts, z=None):
    return [bm.verts.new(p) for p in pts]


def bridge(a, b, mat, part):
    n = len(a)
    for i in range(n):
        f = bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]))
        f.material_index = mat
        part_of[f] = part


def cap(r, mat, part):
    f = bm.faces.new(r)
    f.material_index = mat
    part_of[f] = part


# ---------------- blade: diamond section with a fuller, tapering to a point ----------------
Z0, BL = 0.12, 0.88
rings = []
STN = 26
for i in range(STN):
    s = i / STN * 0.985
    hw = 0.03 * (1 - 0.18 * s)
    t = 0.0065 * (1 - 0.3 * s)
    if s > 0.84:                                   # the point
        k = ((1 - s) / 0.16) ** 0.85
        hw *= k
        t *= max(k, 0.35)
    f = 1.0 if s < 0.55 else max(0.0, 1 - (s - 0.55) / 0.15)
    z = Z0 + BL * s
    sec = [(hw, 0), (0.5 * hw, t), (0.18 * hw, t), (0, t * (1 - 0.55 * f)), (-0.18 * hw, t), (-0.5 * hw, t),
           (-hw, 0), (-0.5 * hw, -t), (-0.18 * hw, -t), (0, -t * (1 - 0.55 * f)), (0.18 * hw, -t), (0.5 * hw, -t)]
    rings.append(ring([(x, y, z) for x, y in sec]))
cap(list(reversed(rings[0])), 0, "blade")
for a, b in zip(rings, rings[1:]):
    bridge(a, b, 0, "blade")
tip = bm.verts.new((0, 0, Z0 + BL))
last = rings[-1]
for i in range(len(last)):
    f = bm.faces.new((last[i], last[(i + 1) % len(last)], tip))
    f.material_index = 0
    part_of[f] = "blade"

# ---------------- cross-guard: chamfered bar whose ends sweep toward the blade ----------------
GX = 0.115
grings = []
for i in range(15):
    xn = -1 + 2 * i / 14
    x = GX * xn
    zc = 0.1075 + 0.026 * xn * xn
    hy = 0.017 * (1 - 0.35 * abs(xn))
    zh = 0.0125 * (1 - 0.3 * abs(xn))
    sec = [(hy, 0.5 * zh), (0.6 * hy, zh), (-0.6 * hy, zh), (-hy, 0.5 * zh),
           (-hy, -0.5 * zh), (-0.6 * hy, -zh), (0.6 * hy, -zh), (hy, -0.5 * zh)]
    grings.append(ring([(x, y, zc + z) for y, z in sec]))
cap(grings[0], 1, "guard")
cap(list(reversed(grings[-1])), 1, "guard")
for a, b in zip(grings, grings[1:]):
    bridge(a, b, 1, "guard")

# ---------------- grip: leather wraps as ridges every 1.9 cm ----------------
SIDES = 10
hrings = []
for i in range(25):
    z = -0.095 + 0.19 * i / 24
    r = 0.0150 + 0.0012 * math.sin(math.pi * (z + 0.095) / 0.19) + 0.0016 * abs(math.sin(math.pi * (z + 0.095) / 0.019))
    hrings.append(ring([(r * math.cos(2 * math.pi * k / SIDES), r * math.sin(2 * math.pi * k / SIDES), z) for k in range(SIDES)]))
cap(list(reversed(hrings[0])), 2, "grip")
cap(hrings[-1], 2, "grip")
for a, b in zip(hrings, hrings[1:]):
    bridge(a, b, 2, "grip")

# ---------------- pommel: an eight-sided faceted wheel ----------------
prings = []
PS = 8
for i in range(7):
    u = i / 6
    z = -0.098 - 0.052 * u
    r = 0.006 + 0.024 * math.sin(math.pi * u) ** 0.55
    prings.append(ring([(r * math.cos(2 * math.pi * k / PS + math.pi / 8), r * math.sin(2 * math.pi * k / PS + math.pi / 8) * 0.75, z)
                        for k in range(PS)]))
cap(prings[0], 1, "pommel")
cap(list(reversed(prings[-1])), 1, "pommel")
for a, b in zip(prings, prings[1:]):
    bridge(a, b, 1, "pommel")

bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

# ---------------- seams: where the sewing pattern is cut ----------------
# Blender's unwrapper flattens each piece between seams; the seams go where a
# texture join will be least seen: the blade's cutting edges, the bottom of the
# guard, the back line of the grip and pommel, and the rim of every end cap.
def seam(v1, v2):
    e = bm.edges.get((v1, v2))
    if e:
        e.seam = True


def seam_ring(r):
    for i in range(len(r)):
        seam(r[i], r[(i + 1) % len(r)])


for a, b in zip(rings, rings[1:]):
    seam(a[0], b[0]); seam(a[6], b[6])          # the two cutting edges: front | back
seam(last[0], tip); seam(last[6], tip)
seam_ring(rings[0])
for a, b in zip(grings, grings[1:]):
    seam(a[5], b[5])                            # underside of the guard
seam_ring(grings[0]); seam_ring(grings[-1])
for group in (hrings, prings):
    for a, b in zip(group, group[1:]):
        seam(a[0], b[0])                        # the back line, where a hand covers it
    seam_ring(group[0]); seam_ring(group[-1])

me = D.meshes.new("Sword")
bm.to_mesh(me)
bm.free()
for p in me.polygons:
    p.use_smooth = True
try:
    me.set_sharp_from_angle(angle=math.radians(35))
except Exception as e:
    print("sharp-by-angle unavailable:", e)


def pbr(name, color, metal, rough):
    m = D.materials.get(name) or D.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    tex = m.node_tree.nodes.get("uv_check") or m.node_tree.nodes.new("ShaderNodeTexImage")
    tex.name = "uv_check"
    tex.location = (-600, 300)
    m.node_tree.nodes.active = tex
    return m


me.materials.append(pbr("Blade_Steel", (0.62, 0.63, 0.66), 1.0, 0.28))
me.materials.append(pbr("Guard_Iron", (0.22, 0.2, 0.19), 1.0, 0.5))
me.materials.append(pbr("Grip_Leather", (0.12, 0.06, 0.03), 0.0, 0.75))
sword = D.objects.new("Sword", me)
sc.collection.objects.link(sword)

# ---------------- unwrap with Blender's own tools, then pack the islands ----------------
me.uv_layers.new(name="UVMap")
vl = sc.view_layers[0]
for o in sc.objects:
    o.select_set(False, view_layer=vl)
sword.select_set(True, view_layer=vl)
vl.objects.active = sword
win = bpy.context.window_manager.windows[0]
area = next(a for a in win.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
with bpy.context.temp_override(window=win, area=area, region=region, scene=sc, view_layer=vl,
                               active_object=sword, object=sword, selected_objects=[sword]):
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.unwrap(method="CONFORMAL", margin=0.004)
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.average_islands_scale()          # same texel density everywhere: no blurry grip
    bpy.ops.uv.pack_islands(rotate=True, margin=0.006)
    bpy.ops.object.mode_set(mode="OBJECT")

# a checker on every material, shown in Solid > Texture view: squares that stay
# square mean no stretching. It is not wired into the material, so it never exports.
grid = D.images.get("uv_check") or D.images.new("uv_check", 1024, 1024)
grid.generated_type = "COLOR_GRID"
for m in me.materials:
    m.node_tree.nodes["uv_check"].image = grid

# ---------------- a small studio to look at it ----------------
w = D.worlds.new("studio")
sc.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.03, 0.032, 0.036, 1)
for name, loc, rot, energy, size, col in (
        ("key", (1.2, -1.4, 1.4), (math.radians(55), 0, math.radians(40)), 120, 1.0, (1.0, 0.93, 0.85)),
        ("rim", (-1.3, 1.2, 1.0), (math.radians(-60), 0, math.radians(220)), 160, 0.6, (0.7, 0.8, 1.0)),
        ("fill", (-1.6, -1.6, 0.2), (math.radians(80), 0, math.radians(-45)), 30, 2.0, (1, 1, 1))):
    L = D.lights.new(name, "AREA"); L.energy = energy; L.size = size; L.color = col
    o = D.objects.new(name, L); o.location = loc; o.rotation_euler = rot
    sc.collection.objects.link(o)
cam = D.objects.new("camera", D.cameras.new("camera"))
cam.data.lens = 52
cam.location = (0.42, -1.7, 0.42)
cam.rotation_euler = (math.radians(90), math.radians(-90), math.radians(14))   # lying flat across the frame
sc.collection.objects.link(cam)
sc.camera = cam
sc.view_settings.view_transform = "AgX"
sc.render.resolution_x, sc.render.resolution_y = 1280, 720

for win in bpy.context.window_manager.windows:
    for area in win.screen.areas:
        if area.type == "VIEW_3D":
            sp = area.spaces.active
            sp.shading.type = "SOLID"
            sp.shading.color_type = "TEXTURE"
            sp.region_3d.view_perspective = "CAMERA"
            sp.overlay.show_floor = False
            sp.overlay.show_axis_x = sp.overlay.show_axis_y = False

# ---------------- export for Unity ----------------
vl = sc.view_layers[0]
for o in sc.objects:
    o.select_set(o == sword, view_layer=vl)
vl.objects.active = sword
path = os.path.join(OUT, "Sword.fbx")
bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={"MESH"},
                         apply_unit_scale=True, apply_scale_options="FBX_SCALE_UNITS",
                         axis_forward="-Z", axis_up="Y", bake_space_transform=True,
                         mesh_smooth_type="FACE", use_mesh_modifiers=True,
                         add_leaf_bones=False, path_mode="AUTO")
tris = sum(len(p.vertices) - 2 for p in me.polygons)
print(f"Sword: {len(me.vertices)} verts, {tris} tris, {len(me.materials)} materials -> {path}")
