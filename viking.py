"""The legendary Viking sword from Moti's reference sheet, built from code.

Metres; z = 0 is the guard, the point is up. Organic parts (dragon heads, ravens) are
metaballs: soft blobs that melt into each other, with negative blobs carving mouths and
eye sockets, converted to a mesh. Everything else is lofted geometry and curves.
Rendered as the reference sheet: front view + side view, orthographic, light grey.
"""
import bpy, bmesh, math
from mathutils import Vector, Euler

D = bpy.data
SCN = "viking"

# ---------------- a clean scene ----------------
for cname in ("VikingSword", "viking_build"):
    c = D.collections.get(cname)
    if c:
        for ob in list(c.objects):
            D.objects.remove(ob, do_unlink=True)
        D.collections.remove(c)
old = D.scenes.get(SCN)
if old:
    for ob in list(old.objects):
        D.objects.remove(ob, do_unlink=True)
    D.scenes.remove(old)
for mb in list(D.metaballs):
    if mb.users == 0:
        D.metaballs.remove(mb)
sc = D.scenes.new(SCN)
for win in bpy.context.window_manager.windows:
    win.scene = sc
vl = sc.view_layers[0]
SW = D.collections.new("VikingSword")
sc.collection.children.link(SW)


def put(ob):
    SW.objects.link(ob)
    return ob


# ---------------- materials ----------------
def mat(name):
    m = D.materials.get(name)
    if m:
        D.materials.remove(m)
    m = D.materials.new(name)
    m.use_nodes = True
    return m, m.node_tree.nodes, m.node_tree.links, m.node_tree.nodes["Principled BSDF"]


def N(nodes, kind, loc=(0, 0), **inp):
    n = nodes.new(kind)
    n.location = loc
    for k, v in inp.items():
        n.inputs[k].default_value = v
    return n


def obj_coords(nodes, links, scale=(1, 1, 1)):
    tc = N(nodes, "ShaderNodeTexCoord", (-1500, 0))
    mp = N(nodes, "ShaderNodeMapping", (-1300, 0))
    mp.inputs["Scale"].default_value = scale
    links.new(tc.outputs["Object"], mp.inputs["Vector"])
    return mp.outputs["Vector"]


def ramp(nodes, links, src, stops, loc):
    r = N(nodes, "ShaderNodeValToRGB", loc)
    el = r.color_ramp.elements
    while len(el) < len(stops):
        el.new(0.5)
    for e, (p, c) in zip(el, stops):
        e.position = p
        e.color = (*c, 1)
    links.new(src, r.inputs["Fac"])
    return r


def bump(nodes, links, h, strength, dist, loc, normal=None):
    b = N(nodes, "ShaderNodeBump", loc, Strength=strength, Distance=dist)
    links.new(h, b.inputs["Height"])
    if normal is not None:
        links.new(normal, b.inputs["Normal"])
    return b


# damascus: rings swirled by noise, dark and light steel
m_dam, n, l, p = mat("Damascus")
v = obj_coords(n, l, (1.0, 1.0, 0.33))
w = N(n, "ShaderNodeTexWave", (-1000, 200), Scale=24, Distortion=11, Detail=3)
w.inputs["Detail Scale"].default_value = 2.5
w.wave_type = "RINGS"; w.rings_direction = "Y"
l.new(v, w.inputs["Vector"])
c = ramp(n, l, w.outputs["Fac"], [(0.2, (0.014, 0.014, 0.015)), (0.5, (0.042, 0.042, 0.045)), (0.8, (0.017, 0.017, 0.018))], (-700, 300))
l.new(c.outputs["Color"], p.inputs["Base Color"])
r = ramp(n, l, w.outputs["Fac"], [(0.3, (0.5, 0.5, 0.5)), (0.5, (0.3, 0.3, 0.3)), (0.72, (0.48, 0.48, 0.48))], (-700, 0))
l.new(r.outputs["Color"], p.inputs["Roughness"])
p.inputs["Metallic"].default_value = 1.0
nz = N(n, "ShaderNodeTexNoise", (-1000, -300), Scale=900, Detail=4)
l.new(v, nz.inputs["Vector"])
b1 = bump(n, l, w.outputs["Fac"], 0.06, 0.001, (-400, -200))
b2 = bump(n, l, nz.outputs["Fac"], 0.08, 0.0005, (-200, -300), b1.outputs["Normal"])     # fine scratches
l.new(b2.outputs["Normal"], p.inputs["Normal"])

m_silver, n, l, p = mat("Silver")
p.inputs["Base Color"].default_value = (0.92, 0.92, 0.94, 1); p.inputs["Metallic"].default_value = 1; p.inputs["Roughness"].default_value = 0.16

m_gold, n, l, p = mat("Gold")
ao = N(n, "ShaderNodeAmbientOcclusion", (-900, 200), Distance=0.006)
gc = ramp(n, l, ao.outputs["AO"], [(0.35, (0.06, 0.045, 0.02)), (0.85, (0.83, 0.55, 0.2))], (-600, 250))
l.new(gc.outputs["Color"], p.inputs["Base Color"])
p.inputs["Metallic"].default_value = 1; p.inputs["Roughness"].default_value = 0.3

m_wire_gold, n, l, p = mat("GoldWire")
p.inputs["Base Color"].default_value = (0.78, 0.5, 0.18, 1); p.inputs["Metallic"].default_value = 1; p.inputs["Roughness"].default_value = 0.32
m_wire_silver, n, l, p = mat("SilverWire")
p.inputs["Base Color"].default_value = (0.7, 0.7, 0.72, 1); p.inputs["Metallic"].default_value = 1; p.inputs["Roughness"].default_value = 0.3

m_leather, n, l, p = mat("BlackLeather")
v = obj_coords(n, l)
g = N(n, "ShaderNodeTexNoise", (-900, -200), Scale=500, Detail=5)
l.new(v, g.inputs["Vector"])
p.inputs["Base Color"].default_value = (0.012, 0.010, 0.009, 1); p.inputs["Roughness"].default_value = 0.55
l.new(bump(n, l, g.outputs["Fac"], 0.25, 0.0006, (-400, -200)).outputs["Normal"], p.inputs["Normal"])

# blackened iron, its scales traced in gold wire (voronoi cell edges)
m_iron, n, l, p = mat("DragonIron")
v = obj_coords(n, l)
vo = N(n, "ShaderNodeTexVoronoi", (-1000, 200), Scale=330)
vo.feature = "DISTANCE_TO_EDGE"
l.new(v, vo.inputs["Vector"])
vf = N(n, "ShaderNodeTexVoronoi", (-1000, -250), Scale=330)
l.new(v, vf.inputs["Vector"])
mr = N(n, "ShaderNodeMapRange", (-750, 200))
mr.inputs["From Min"].default_value = 0.0; mr.inputs["From Max"].default_value = 0.045
mr.inputs["To Min"].default_value = 1.0; mr.inputs["To Max"].default_value = 0.0
l.new(vo.outputs["Distance"], mr.inputs["Value"])
mix = N(n, "ShaderNodeMix", (-450, 250)); mix.data_type = "RGBA"
mix.inputs["A"].default_value = (0.022, 0.021, 0.02, 1)
mix.inputs["B"].default_value = (0.8, 0.52, 0.18, 1)
l.new(mr.outputs["Result"], mix.inputs["Factor"])
l.new(mix.outputs["Result"], p.inputs["Base Color"])
rr = N(n, "ShaderNodeMapRange", (-450, 0))
rr.inputs["To Min"].default_value = 0.5; rr.inputs["To Max"].default_value = 0.28
l.new(mr.outputs["Result"], rr.inputs["Value"])
l.new(rr.outputs["Result"], p.inputs["Roughness"])
p.inputs["Metallic"].default_value = 0.9
l.new(bump(n, l, vf.outputs["Distance"], 0.35, 0.0015, (-300, -300)).outputs["Normal"], p.inputs["Normal"])

m_ivory, n, l, p = mat("Ivory")
p.inputs["Base Color"].default_value = (0.62, 0.56, 0.44, 1); p.inputs["Roughness"].default_value = 0.35
m_throat, n, l, p = mat("Throat")
p.inputs["Base Color"].default_value = (0.06, 0.008, 0.01, 1); p.inputs["Roughness"].default_value = 0.45
m_garnet, n, l, p = mat("Garnet")
p.inputs["Base Color"].default_value = (0.32, 0.005, 0.02, 1); p.inputs["Roughness"].default_value = 0.04
p.inputs["Coat Weight"].default_value = 1.0

# darkened bronze: patina in the recesses, gold where it is worn and proud; feathers in relief
m_bronze, n, l, p = mat("RavenBronze")
v = obj_coords(n, l, (1, 1, 0.45))
ao = N(n, "ShaderNodeAmbientOcclusion", (-1000, 300), Distance=0.008)
nz = N(n, "ShaderNodeTexNoise", (-1000, 0), Scale=420, Detail=2)
l.new(v, nz.inputs["Vector"])
fe = N(n, "ShaderNodeTexVoronoi", (-1000, -300), Scale=170)
l.new(v, fe.inputs["Vector"])
mulao = N(n, "ShaderNodeMath", (-750, 250)); mulao.operation = "MULTIPLY"
l.new(ao.outputs["AO"], mulao.inputs[0]); l.new(nz.outputs["Fac"], mulao.inputs[1])
bc = ramp(n, l, mulao.outputs["Value"], [(0.2, (0.01, 0.011, 0.008)), (0.5, (0.07, 0.04, 0.016)), (0.75, (0.6, 0.4, 0.14))], (-500, 300))
l.new(bc.outputs["Color"], p.inputs["Base Color"])
p.inputs["Metallic"].default_value = 1; p.inputs["Roughness"].default_value = 0.38
l.new(bump(n, l, fe.outputs["Distance"], 0.5, 0.0012, (-300, -300)).outputs["Normal"], p.inputs["Normal"])


# ---------------- mesh helpers ----------------
def loft(name, rings, material, cap_start=True, cap_end=True, apex=None, smooth=True):
    bm = bmesh.new()
    vr = [[bm.verts.new(pt) for pt in r] for r in rings]
    k = len(rings[0])
    for a, b in zip(vr, vr[1:]):
        for i in range(k):
            bm.faces.new((a[i], a[(i + 1) % k], b[(i + 1) % k], b[i]))
    if cap_start:
        bm.faces.new(list(reversed(vr[0])))
    if apex is not None:
        t = bm.verts.new(apex)
        for i in range(k):
            bm.faces.new((vr[-1][i], vr[-1][(i + 1) % k], t))
    elif cap_end:
        bm.faces.new(vr[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = D.meshes.new(name)
    bm.to_mesh(me); bm.free()
    for f in me.polygons:
        f.use_smooth = smooth
    me.materials.append(material)
    return put(D.objects.new(name, me))


def tube(name, splines, material, radius, res=3):
    """splines: list of point lists, or of (point, radius-factor) lists."""
    cu = D.curves.new(name, "CURVE")
    cu.dimensions = "3D"; cu.bevel_depth = radius; cu.bevel_resolution = res
    cu.use_fill_caps = True
    for pts in splines:
        sp = cu.splines.new("POLY")
        sp.points.add(len(pts) - 1)
        for i, q in enumerate(pts):
            if isinstance(q[0], (tuple, list, Vector)):
                q, rad = q
            else:
                rad = 1.0
            sp.points[i].co = (*q, 1)
            sp.points[i].radius = rad
        sp.use_smooth = True
    cu.materials.append(material)
    return put(D.objects.new(name, cu))


def sphere(name, loc, r, material, scale=(1, 1, 1)):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=10, radius=r)
    for vtx in bm.verts:
        vtx.co = Vector((vtx.co.x * scale[0], vtx.co.y * scale[1], vtx.co.z * scale[2])) + Vector(loc)
    me = D.meshes.new(name); bm.to_mesh(me); bm.free()
    for f in me.polygons:
        f.use_smooth = True
    me.materials.append(material)
    return put(D.objects.new(name, me))


# ---------------- metaballs -> mesh ----------------
SURF = 0.67   # with threshold 0.6 and stiffness 2 the surface sits at ~0.67 of the radius


def metaball(name, elements, material, res=0.0011, smooth_passes=2):
    # Blender clamps metaball resolution at 5 mm, too coarse for a 4 cm dragon head:
    # build 10x larger, where 5 mm is fine detail, and shrink the mesh back after.
    UP = 10.0
    mb = D.metaballs.new(name)
    mb.resolution = mb.render_resolution = max(res * UP, 0.005)
    mb.threshold = 0.6
    for kind, co, r, size, rot, neg in elements:
        e = mb.elements.new(type=kind)
        e.co = tuple(c * UP for c in co)
        e.radius = r / SURF * UP
        e.size_x, e.size_y, e.size_z = (size[0] * UP, size[1], size[2]) if kind in ("CUBE",) else size
        if kind == "CUBE":
            e.size_y, e.size_z = size[1] * UP, size[2] * UP
        if kind == "CAPSULE":
            e.size_x = size[0] * UP
        e.rotation = Euler([math.radians(a) for a in rot]).to_quaternion()
        e.use_negative = neg
    tmp = D.objects.new(name, mb)
    sc.collection.objects.link(tmp)
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    me = D.meshes.new_from_object(tmp.evaluated_get(dg))
    D.objects.remove(tmp, do_unlink=True)
    D.metaballs.remove(mb)
    bm = bmesh.new(); bm.from_mesh(me)
    for vtx in bm.verts:
        vtx.co /= UP
    for _ in range(smooth_passes):
        bmesh.ops.smooth_vert(bm, verts=bm.verts, factor=0.5, use_axis_x=True, use_axis_y=True, use_axis_z=True)
    bm.to_mesh(me); bm.free()
    me.name = name + "_mesh"
    for f in me.polygons:
        f.use_smooth = True
    me.materials.append(material)
    return put(D.objects.new(name.replace("MB", ""), me))


def mirror_x(elements):
    out = list(elements)
    for kind, (x, y, z), r, size, (rx, ry, rz), neg in elements:
        out.append((kind, (-x, y, z), r, size, (rx, -ry, -rz), neg))
    return out


# =====================================================================
# BLADE: broad, lenticular, a deep fuller; shoulder at the base, ogive point
# =====================================================================
Z0, BL = 0.002, 0.656          # the tang end sits inside the guard


def blade_shape(s):
    hw = 0.037 * (1 - 0.2 * s)
    if s < 0.035:
        hw = 0.0305
    elif s < 0.05:
        k = (s - 0.035) / 0.015
        hw = 0.0305 + (hw - 0.0305) * (k * k * (3 - 2 * k))
    t = 0.0046 * (1 - 0.45 * s)
    if s > 0.78:
        k = (s - 0.78) / 0.22
        f = max(1 - k ** 1.7, 0) ** 0.72
        hw *= f
        t *= max(f, 0.3)
    fd = 1.0
    if s < 0.03:
        fd = 0.0
    elif s < 0.05:
        fd = (s - 0.03) / 0.02
    elif s > 0.8:
        fd = 0.0
    elif s > 0.7:
        fd = 1 - (s - 0.7) / 0.1
    fw = 0.011 * hw / 0.037
    d = 0.0024 * fd
    return hw, t, fw, d


rings = []
STN = 90
for i in range(STN):
    s = i / STN * 0.997
    hw, t, fw, d = blade_shape(s)
    front = [(hw, 0), (0.82 * hw, 0.45 * t), (0.6 * hw, 0.8 * t), (fw, t), (0.8 * fw, t - 0.85 * d), (0.4 * fw, t - d),
             (0, t - d), (-0.4 * fw, t - d), (-0.8 * fw, t - 0.85 * d), (-fw, t), (-0.6 * hw, 0.8 * t), (-0.82 * hw, 0.45 * t)]
    back = [(-x, -y) for x, y in front]
    z = Z0 + s * BL
    rings.append([(x, y, z) for x, y in front + back])
blade = loft("Blade", rings, m_dam, apex=(0, 0, Z0 + BL))
blade.data.set_sharp_from_angle(angle=math.radians(40))

# ---------------- silver runes inlaid in the fuller (front face is -y: the camera side) ----------------
RUNES = {
    "H": [[(0, 0), (0, 1)], [(0.6, 0), (0.6, 1)], [(0, 0.62), (0.6, 0.38)]],
    "U": [[(0, 0), (0, 1), (0.6, 0.72), (0.6, 0)]],
    "G": [[(0, 0), (0.6, 1)], [(0, 1), (0.6, 0)]],
    "I": [[(0.3, 0), (0.3, 1)]],
    "N": [[(0.3, 0), (0.3, 1)], [(0.05, 0.62), (0.55, 0.38)]],
    "M": [[(0, 0), (0, 1)], [(0.6, 0), (0.6, 1)], [(0, 1), (0.6, 0.55)], [(0.6, 1), (0, 0.55)]],
    "·": [[(0.28, 0.47), (0.32, 0.53)]],
}
GH, GW = 0.0155, 0.0085
strokes = []
zc = Z0 + 0.6 * BL
for ch in "HUGINN·MUNINN":
    s = (zc - Z0) / BL
    hw, t, fw, d = blade_shape(s)
    y = -(t - d) - 0.00025
    for st in RUNES[ch]:
        strokes.append([((gx - 0.3) / 0.6 * GW, y, zc - 0.5 * GH + gy * GH) for gx, gy in st])
    zc -= 1.3 * GH
tube("Runes", strokes, m_silver, 0.00075, 2)

# =====================================================================
# GUARD: an iron collar whose two ends are snarling dragon heads, garnet eyes
# =====================================================================
half = [
    # collar and neck, rising gently toward the blade
    ("CUBE", (0.0, 0, 0.004), 0.011, (0.022, 0.006, 0.004), (0, 0, 0), False),
    ("CAPSULE", (0.04, 0, 0.007), 0.0115, (0.018, 1, 1), (0, -8, 0), False),
    ("ELLIPSOID", (0.062, 0, 0.012), 0.012, (1.2, 0.95, 1.0), (0, -12, 0), False),
    # skull, brow, snout
    ("ELLIPSOID", (0.08, 0, 0.018), 0.0135, (1.25, 0.85, 0.9), (0, -10, 0), False),
    ("BALL", (0.084, 0.0075, 0.027), 0.0058, (1, 1, 1), (0, 0, 0), False),
    ("BALL", (0.084, -0.0075, 0.027), 0.0058, (1, 1, 1), (0, 0, 0), False),
    ("ELLIPSOID", (0.103, 0, 0.021), 0.0095, (1.55, 0.72, 0.6), (0, -6, 0), False),
    # lower jaw, dropped open
    ("ELLIPSOID", (0.097, 0, 0.0055), 0.0082, (1.6, 0.62, 0.42), (0, 22, 0), False),
    # the mouth, carved out
    ("ELLIPSOID", (0.11, 0, 0.0135), 0.0068, (1.8, 0.62, 0.55), (0, 8, 0), True),
    # eye sockets and nostrils
    ("BALL", (0.091, 0.0095, 0.0235), 0.0034, (1, 1, 1), (0, 0, 0), True),
    ("BALL", (0.091, -0.0095, 0.0235), 0.0034, (1, 1, 1), (0, 0, 0), True),
    ("BALL", (0.119, 0.0035, 0.0245), 0.0017, (1, 1, 1), (0, 0, 0), True),
    ("BALL", (0.119, -0.0035, 0.0245), 0.0017, (1, 1, 1), (0, 0, 0), True),
]
GS, GDZ = 1.4, -0.009
def gscale(e):
    kind, (x, y, z), r, size, rot, neg = e
    return (kind, (x * 0.92, y * GS, z * GS + GDZ), r * GS, size, rot, neg)
half = [gscale(e) for e in half]
guard = metaball("GuardMB", mirror_x(half), m_iron, res=0.0009)
G = lambda x, y, z: (x * 0.92, y * GS, z * GS + GDZ)

for sx in (1, -1):
    for sy in (1, -1):
        sphere("eye", G(sx * 0.0905, sy * 0.0083, 0.0235), 0.0028 * GS, m_garnet)
    horns = []
    for sy in (1, -1):
        pts = [(G(sx * 0.082, sy * 0.0065, 0.029), 1.0), (G(sx * 0.072, sy * 0.010, 0.036), 0.8),
               (G(sx * 0.06, sy * 0.012, 0.039), 0.55), (G(sx * 0.049, sy * 0.012, 0.037), 0.3), (G(sx * 0.042, sy * 0.011, 0.033), 0.08)]
        horns.append(pts)
    tube("horns", horns, m_iron, 0.0032 * GS, 3)
    # teeth: upper row points down, lower row points up
    bm = bmesh.new()
    for i in range(4):
        x = sx * (0.1 + i * 0.0045)
        for sy in (1, -1):
            for z, up in ((0.0158 - i * 0.0004, False), (0.0085 + i * 0.0006, True)):
                ret = bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=0.0011 * GS, radius2=0.0, depth=0.0042 * GS)
                for vv in ret["verts"]:
                    co = vv.co.copy()
                    if not up:
                        co.z = -co.z
                    vv.co = co + Vector(G(x, sy * 0.0042, z + (0.0021 if up else -0.0021)))
    me = D.meshes.new("teeth"); bm.to_mesh(me); bm.free()
    me.materials.append(m_ivory)
    put(D.objects.new("teeth", me))
    sphere("throat", G(sx * 0.099, 0, 0.0115), 0.0062, m_throat, (1.7, 0.75, 0.75))

# =====================================================================
# HILT: knotwork bands, black leather grip, braided gold and silver wire
# =====================================================================
def band(name, z_top, height, R, strands=8):
    prof = [(0.0, R + 0.0016), (0.12, R + 0.0016), (0.18, R + 0.0004), (0.82, R + 0.0004), (0.88, R + 0.0016), (1.0, R + 0.0016)]
    rings = []
    for u, rad in prof:
        z = z_top - u * height
        rings.append([(rad * math.cos(2 * math.pi * k / 48), rad * math.sin(2 * math.pi * k / 48), z) for k in range(48)])
    loft(name, rings, m_gold)
    # two-strand interlace: the strands weave over and under at every crossing
    zc = z_top - height / 2
    A = height * 0.24
    for sgn in (1, -1):
        pts = []
        for i in range(241):
            th = 2 * math.pi * i / 240
            z = zc + sgn * A * math.sin(strands * th)
            rr = R + 0.0011 + sgn * 0.00055 * math.cos(strands * th)
            pts.append((rr * math.cos(th), rr * math.sin(th), z))
        tube(name + "_knot", [pts], m_gold, 0.0011, 2)


band("BandTop", -0.012, 0.017, 0.0245)
GZ0, GZ1 = -0.027, -0.176
GR = 0.0205
grip_r = lambda z: GR + 0.0018 * math.sin(math.pi * (GZ0 - z) / (GZ0 - GZ1))
rings = []
for i in range(31):
    z = GZ0 + (GZ1 - GZ0) * i / 30
    r = grip_r(z)
    rings.append([(r * math.cos(2 * math.pi * k / 36), r * math.sin(2 * math.pi * k / 36), z) for k in range(36)])
loft("Grip", rings, m_leather)
band("BandBottom", GZ1, 0.018, 0.026)

# criss-cross wire: a gold braid winding one way, a silver braid the other; each braid is two twisted strands
TURNS = 2.5
for direction, material in ((1, m_wire_gold), (-1, m_wire_silver)):
    for strand in (0, 1):
        pts = []
        for i in range(601):
            u = i / 600
            z = GZ0 + (GZ1 - GZ0) * u
            th = direction * 2 * math.pi * TURNS * u + (0 if direction > 0 else math.pi / 2)
            R = grip_r(z) + 0.0011
            nrm = Vector((math.cos(th), math.sin(th), 0))
            tan = Vector((-math.sin(th) * direction, math.cos(th) * direction, 0)) * (2 * math.pi * TURNS * R) + Vector((0, 0, GZ1 - GZ0))
            tan.normalize()
            bin_ = tan.cross(nrm).normalized()
            ph = 2 * math.pi * 55 * u + strand * math.pi
            off = 0.0008 * (math.cos(ph) * nrm + math.sin(ph) * bin_)
            pts.append(tuple(Vector((R * math.cos(th), R * math.sin(th), z)) + off))
        tube("WireBraid", [pts], material, 0.00078, 2)

# =====================================================================
# POMMEL: two ravens back to back, wings folded, beaks outward, darkened bronze
# =====================================================================
PZ = -0.192   # top of the pommel, tucked into the lower band
raven = [
    ("BALL", (0.004, 0, PZ - 0.004), 0.0175, (1, 1, 1), (0, 0, 0), False),                 # collar into the band
    ("ELLIPSOID", (0.004, 0, PZ - 0.07), 0.021, (1.2, 0.95, 0.9), (0, 0, 0), False),       # the shared rounded base
    ("ELLIPSOID", (0.019, 0, PZ - 0.05), 0.023, (0.95, 0.9, 1.35), (0, -18, 0), False),    # body
    ("BALL", (0.027, 0, PZ - 0.03), 0.0155, (1, 1, 1), (0, 0, 0), False),                  # chest
    ("CAPSULE", (0.031, 0, PZ - 0.019), 0.0105, (0.006, 1, 1), (0, -60, 0), False),        # neck
    ("BALL", (0.038, 0, PZ - 0.012), 0.0145, (1, 1, 1), (0, 0, 0), False),                 # head
    ("ELLIPSOID", (0.016, 0.0145, PZ - 0.047), 0.0145, (1.0, 0.42, 1.7), (8, -16, 0), False),   # folded wings
    ("ELLIPSOID", (0.016, -0.0145, PZ - 0.047), 0.0145, (1.0, 0.42, 1.7), (-8, -16, 0), False),
    ("BALL", (0.043, 0.0102, PZ - 0.0085), 0.003, (1, 1, 1), (0, 0, 0), True),             # eye sockets
    ("BALL", (0.043, -0.0102, PZ - 0.0085), 0.003, (1, 1, 1), (0, 0, 0), True),
]
raven.append(("ELLIPSOID", (0.0, 0, PZ - 0.03), 0.017, (1.0, 0.95, 1.6), (0, 0, 0), False))   # fills the cleft between the backs
pommel = metaball("RavensMB", mirror_x(raven), m_bronze, res=0.0006, smooth_passes=3)

for sx in (1, -1):
    # beak: lofted, flattened sideways, hooked down at the tip
    rings = []
    BLN, RB = 0.024, 0.0072
    for i in range(10):
        u = i / 10
        cx = sx * (0.046 + BLN * u)
        cz = PZ - 0.012 + 0.006 * u - 0.007 * u ** 2.2
        rb = RB * (1 - u) ** 0.85
        rings.append([(cx, 0.72 * rb * math.sin(2 * math.pi * k / 10), cz + 1.05 * rb * math.cos(2 * math.pi * k / 10)) for k in range(10)])
    loft("beak", rings, m_bronze, apex=(sx * (0.046 + BLN), 0, PZ - 0.012 + 0.006 - 0.007 - 0.0015))
    for sy in (1, -1):
        sphere("raven_eye", (sx * 0.0425, sy * 0.0092, PZ - 0.0085), 0.0023, m_gold)

# ---------------- the reference sheet: front view + side view ----------------
for o in vl.layer_collection.children:
    if o.collection == SW:
        o.exclude = True
for name, x, rz in (("front view", -0.16, 0), ("side view", 0.16, 90)):
    inst = D.objects.new(name, None)
    inst.instance_type = "COLLECTION"; inst.instance_collection = SW
    inst.location = (x, 0, 0); inst.rotation_euler = (0, 0, math.radians(rz))
    sc.collection.objects.link(inst)

w = D.worlds.new("studio grey"); sc.world = w; w.use_nodes = True
wn, wl = w.node_tree.nodes, w.node_tree.links
bg_cam = wn["Background"]; bg_cam.inputs["Color"].default_value = (0.8, 0.8, 0.78, 1)
bg_env = wn.new("ShaderNodeBackground"); bg_env.inputs["Strength"].default_value = 1.0
grad = wn.new("ShaderNodeTexGradient"); gtc = wn.new("ShaderNodeTexCoord")
gmap = wn.new("ShaderNodeMapping"); gmap.inputs["Rotation"].default_value = (0, math.radians(-90), 0)
wl.new(gtc.outputs["Generated"], gmap.inputs["Vector"]); wl.new(gmap.outputs["Vector"], grad.inputs["Vector"])
genv = wn.new("ShaderNodeValToRGB")
genv.color_ramp.elements[0].position = 0.45; genv.color_ramp.elements[0].color = (0.015, 0.015, 0.016, 1)
genv.color_ramp.elements[1].position = 0.75; genv.color_ramp.elements[1].color = (0.55, 0.55, 0.56, 1)
wl.new(grad.outputs["Fac"], genv.inputs["Fac"]); wl.new(genv.outputs["Color"], bg_env.inputs["Color"])
lp = wn.new("ShaderNodeLightPath"); mixw = wn.new("ShaderNodeMixShader")
wl.new(lp.outputs["Is Camera Ray"], mixw.inputs[0])
wl.new(bg_env.outputs[0], mixw.inputs[1]); wl.new(bg_cam.outputs[0], mixw.inputs[2])
wl.new(mixw.outputs[0], wn["World Output"].inputs["Surface"])
for name, loc, rot, energy, size in (("softbox front", (0, -2.0, 0.25), (90, 0, 0), 110, 2.2),
                                     ("softbox top", (0, -0.8, 1.6), (30, 0, 0), 45, 2.0)):
    Lt = D.lights.new(name, "AREA"); Lt.energy = energy; Lt.size = size
    o = D.objects.new(name, Lt); o.location = loc; o.rotation_euler = [math.radians(a) for a in rot]
    sc.collection.objects.link(o)
cam = D.objects.new("sheet camera", D.cameras.new("sheet camera"))
cam.data.type = "ORTHO"; cam.data.ortho_scale = 1.08
cam.location = (0, -3, 0.17); cam.rotation_euler = (math.radians(90), 0, 0)
sc.collection.objects.link(cam); sc.camera = cam
sc.render.resolution_x = sc.render.resolution_y = 1024
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Medium High Contrast"
sc.render.film_transparent = False
for win in bpy.context.window_manager.windows:
    for area in win.screen.areas:
        if area.type == "VIEW_3D":
            sp = area.spaces.active
            sp.shading.type = "RENDERED"
            sp.region_3d.view_perspective = "CAMERA"
            sp.overlay.show_floor = False
            sp.overlay.show_axis_x = sp.overlay.show_axis_y = False
sc.render.filepath = "/mnt/fast/apps/blender-play/export/viking_sheet.png"
bpy.ops.render.render(write_still=True)
tris = 0
dg = bpy.context.evaluated_depsgraph_get()
for o in SW.objects:
    ev = o.evaluated_get(dg)
    try:
        m = ev.to_mesh(); tris += sum(len(pp.vertices) - 2 for pp in m.polygons); ev.to_mesh_clear()
    except Exception:
        pass
print(f"viking sword: {len(SW.objects)} parts, ~{tris} tris")
