"""Step 5: a high-poly sword, its detail baked onto the game sword.

High poly ('Sword_high', hidden after): the source sword + Bevel (real rounded edges) +
Subdivision, wearing the procedural materials, plus runes carved into both fullers.
Bake 'selected to active' (Cycles): each pixel of the low sword's texture looks at the
high sword beneath it, so the rounding and the carving land in the normal map.
Front fuller: HUGINN · MUNINN. Back fuller: the makers' mark, MOTI · CLAUDE.
Textures grow to 1024 x 4096 (~35 px per cm on the blade) so the runes stay legible.
"""
import bpy, os, math, numpy as np

D = bpy.data
OUT = "/mnt/fast/apps/blender-play/export"
W, H = 1024, 4096
sc = D.scenes["sword"]; vl = sc.view_layers[0]
low = sc.objects["Sword"]; src = sc.objects["Sword_source"]
Z0, BL = 0.12, 0.88

# ---------------- where the fullers lie in UV space ----------------
me = low.data
uvd = me.uv_layers.active.data
vert_uv = {}
for lp in me.loops:
    vert_uv.setdefault(lp.vertex_index, uvd[lp.index].uv.copy())


def fuller_fit(side):
    zs, us, vs = [], [], []
    for v in me.vertices:
        x, y, z = v.co
        if abs(x) < 1e-6 and side * y > 1e-5 and Z0 + 0.01 < z < Z0 + 0.62:
            zs.append(z); us.append(vert_uv[v.index].x); vs.append(vert_uv[v.index].y)
    zs, us, vs = map(np.array, (zs, us, vs))
    fu, fv = np.polyfit(zs, us, 1), np.polyfit(zs, vs, 1)
    # which way +x (across the blade) runs in u, from the fuller's own rim vertices
    du = []
    for v in me.vertices:
        x, y, z = v.co
        if 0.002 < x < 0.008 and side * y > 1e-5 and Z0 + 0.01 < z < Z0 + 0.62:
            du.append(vert_uv[v.index].x - np.polyval(fu, z))
    sign = 1.0 if np.mean(du) > 0 else -1.0
    px_per_m = abs(fv[0]) * H
    return fu, fv, sign, px_per_m


# ---------------- Elder Futhark, drawn as strokes in a 0.6 x 1 box ----------------
R = {
    "H": [[(0, 0), (0, 1)], [(0.6, 0), (0.6, 1)], [(0, 0.62), (0.6, 0.38)]],
    "U": [[(0, 0), (0, 1), (0.6, 0.72), (0.6, 0)]],
    "G": [[(0, 0), (0.6, 1)], [(0, 1), (0.6, 0)]],
    "I": [[(0.3, 0), (0.3, 1)]],
    "N": [[(0.3, 0), (0.3, 1)], [(0.05, 0.62), (0.55, 0.38)]],
    "M": [[(0, 0), (0, 1)], [(0.6, 0), (0.6, 1)], [(0, 1), (0.6, 0.55)], [(0.6, 1), (0, 0.55)]],
    "O": [[(0, 0.68), (0.3, 1), (0.6, 0.68)], [(0.6, 0.68), (0, 0)], [(0, 0.68), (0.6, 0)]],
    "T": [[(0.3, 0), (0.3, 1)], [(0, 0.7), (0.3, 1), (0.6, 0.7)]],
    "K": [[(0.55, 1), (0.1, 0.65), (0.55, 0.3)]],
    "L": [[(0.15, 0), (0.15, 1), (0.55, 0.65)]],
    "A": [[(0.15, 0), (0.15, 1)], [(0.15, 1), (0.55, 0.75)], [(0.15, 0.72), (0.55, 0.47)]],
    "D": [[(0, 0), (0, 1), (0.6, 0), (0.6, 1), (0, 0)]],
    "E": [[(0, 0), (0, 1), (0.3, 0.7), (0.6, 1), (0.6, 0)]],
    "·": [[(0.27, 0.46), (0.33, 0.54)]],
}
GLYPH = 0.0062          # rune height across the fuller, metres
height = np.ones((H, W), dtype=np.float32)


def carve(text, side, z_start):
    fu, fv, sign, ppm = fuller_fit(side)
    radius = 0.075 * GLYPH * ppm
    cursor = z_start
    for ch in text:
        for stroke in R[ch]:
            pts = []
            for gx, gy in stroke:
                z = cursor + gx * GLYPH
                a = (gy - 0.5) * GLYPH * side         # across the blade; mirrored on the back so it reads
                u = np.polyval(fu, z) + sign * a * ppm / W
                v = np.polyval(fv, z)
                pts.append((u * W, v * H))
            for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                pad = radius + 2
                xa, xb = int(max(min(x0, x1) - pad, 0)), int(min(max(x0, x1) + pad, W - 1)) + 1
                ya, yb = int(max(min(y0, y1) - pad, 0)), int(min(max(y0, y1) + pad, H - 1)) + 1
                yy, xx = np.mgrid[ya:yb, xa:xb].astype(np.float32) + 0.5
                dx, dy = x1 - x0, y1 - y0
                L2 = dx * dx + dy * dy or 1e-9
                t = np.clip(((xx - x0) * dx + (yy - y0) * dy) / L2, 0, 1)
                d = np.hypot(xx - (x0 + t * dx), yy - (y0 + t * dy))
                val = np.clip(d - radius + 0.5, 0, 1)
                height[ya:yb, xa:xb] = np.minimum(height[ya:yb, xa:xb], val)
        cursor += 0.95 * GLYPH
    return ppm


ppm = carve("HUGINN·MUNINN", +1, Z0 + 0.05)
carve("MOTI·KLAUDE", -1, Z0 + 0.05)
runes = D.images.get("Sword_Runes_height")
if runes:
    D.images.remove(runes)
runes = D.images.new("Sword_Runes_height", W, H, alpha=False)
runes.colorspace_settings.name = "Non-Color"
rgba = np.ones((H, W, 4), dtype=np.float32)
rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = height
runes.pixels.foreach_set(rgba.ravel())

# the runes become a second bump on the steel, after the scratches
steel = D.materials["Blade_Steel"]
nt = steel.node_tree
for name in ("runes_tex", "runes_bump"):
    if nt.nodes.get(name):
        nt.nodes.remove(nt.nodes[name])
pb = nt.nodes["Principled BSDF"]
prev = pb.inputs["Normal"].links[0].from_socket if pb.inputs["Normal"].is_linked else None
rt = nt.nodes.new("ShaderNodeTexImage"); rt.name = "runes_tex"; rt.image = runes; rt.location = (-650, -650)
rb = nt.nodes.new("ShaderNodeBump"); rb.name = "runes_bump"; rb.location = (-150, -500)
rb.inputs["Strength"].default_value = 1.0
rb.inputs["Distance"].default_value = 0.0008                 # 0.8 mm deep
nt.links.new(rt.outputs["Color"], rb.inputs["Height"])
if prev:
    nt.links.new(prev, rb.inputs["Normal"])
nt.links.new(rb.outputs["Normal"], pb.inputs["Normal"])

# ---------------- the high poly ----------------
old = sc.objects.get("Sword_high")
if old:
    D.objects.remove(old, do_unlink=True)
high = src.copy(); high.data = src.data.copy(); high.name = "Sword_high"
sc.collection.objects.link(high)
high.hide_set(False, view_layer=vl); high.hide_render = False
bev = high.modifiers.new("rounded edges", "BEVEL")
bev.width = 0.0007; bev.segments = 3; bev.limit_method = "ANGLE"; bev.angle_limit = math.radians(30)
sub = high.modifiers.new("smooth", "SUBSURF")
sub.levels = sub.render_levels = 2
for p in high.data.polygons:
    p.use_smooth = True

# hard edges on the game mesh only where the UVs are cut: a hard edge inside a UV island
# makes a seam the normal map cannot hide
for e in me.edges:
    if e.use_edge_sharp and not e.use_seam:
        e.use_edge_sharp = False

# ---------------- bake high -> low ----------------
game = low.active_material
gnt = game.node_tree
old_nodes = {n.image.name: n for n in gnt.nodes if n.type == "TEX_IMAGE" and n.image}
target = gnt.nodes.get("bake_target") or gnt.nodes.new("ShaderNodeTexImage")
target.name = "bake_target"; target.location = (-1000, 600)

sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 4
sc.render.bake.normal_space = "TANGENT"
for o in sc.objects:
    o.select_set(o in (low, high), view_layer=vl)
vl.objects.active = low
win = bpy.context.window_manager.windows[0]
area = next(a for a in win.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
HIGH_MATS = [s.material for s in high.material_slots]


def new_target(name, noncolor, alpha=False):
    img = D.images.new(name, W, H, alpha=alpha)
    if noncolor:
        img.colorspace_settings.name = "Non-Color"
    target.image = img
    gnt.nodes.active = target
    return img


def bake(kind):
    with bpy.context.temp_override(window=win, area=area, region=region, scene=sc, view_layer=vl,
                                   active_object=low, object=low, selected_objects=[low, high],
                                   selected_editable_objects=[low, high]):
        bpy.ops.object.bake(type=kind, use_selected_to_active=True, cage_extrusion=0.003,
                            max_ray_distance=0.012, margin=16, use_clear=True)


def bake_channel(socket):
    saved = []
    for m in HIGH_MATS:
        t = m.node_tree
        p, out = t.nodes["Principled BSDF"], t.nodes["Material Output"]
        em = t.nodes.new("ShaderNodeEmission")
        s = p.inputs[socket]
        if s.is_linked:
            t.links.new(s.links[0].from_socket, em.inputs["Color"])
        else:
            val = s.default_value
            em.inputs["Color"].default_value = tuple(val) if hasattr(val, "__len__") else (val, val, val, 1)
        t.links.new(em.outputs[0], out.inputs["Surface"])
        saved.append((t, p, out, em))
    bake("EMIT")
    for t, p, out, em in saved:
        t.links.new(p.outputs[0], out.inputs["Surface"])
        t.nodes.remove(em)


base = new_target("bake_base", False); bake_channel("Base Color")
rough = new_target("bake_rough", True); bake_channel("Roughness")
metal = new_target("bake_metal", True); bake_channel("Metallic")
normal = new_target("bake_normal", True); bake("NORMAL")

r = np.empty(W * H * 4, np.float32); rough.pixels.foreach_get(r)
mt = np.empty(W * H * 4, np.float32); metal.pixels.foreach_get(mt)
ms = np.empty(W * H * 4, np.float32)
ms[0::4] = ms[1::4] = ms[2::4] = mt[0::4]
ms[3::4] = 1.0 - r[0::4]
msimg = D.images.new("bake_ms", W, H, alpha=True)
msimg.colorspace_settings.name = "Non-Color"; msimg.alpha_mode = "STRAIGHT"
msimg.pixels.foreach_set(ms)
D.images.remove(rough); D.images.remove(metal)
gnt.nodes.remove(target)

# swap the new images into the game material under the old names, and write the files
for new, name in ((base, "Sword_BaseColor"), (msimg, "Sword_MetallicSmoothness"), (normal, "Sword_Normal")):
    n = old_nodes.get(name)
    if n:
        oldimg = n.image
        n.image = new
        D.images.remove(oldimg)
    new.name = name
    new.filepath_raw = os.path.join(OUT, name + ".png")
    new.file_format = "PNG"
    new.save()

high.hide_set(True, view_layer=vl); high.hide_render = True

# ---------------- export ----------------
sc.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items.keys() else "BLENDER_EEVEE"
for o in sc.objects:
    o.select_set(o == low, view_layer=vl)
bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, "Sword.fbx"), use_selection=True, object_types={"MESH"},
                         apply_unit_scale=True, apply_scale_options="FBX_SCALE_UNITS",
                         axis_forward="-Z", axis_up="Y", bake_space_transform=True,
                         mesh_smooth_type="FACE", add_leaf_bones=False, path_mode="COPY", embed_textures=True)
low.select_set(False)
bpy.ops.wm.save_mainfile()
hp = high.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
print(f"high poly {len(hp.polygons)} faces; runes at {ppm / 100:.1f} px/cm; textures {W}x{H}")
