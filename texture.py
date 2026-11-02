"""Step 4: texture the sword and bake it into the images Unity reads.

Source: three procedural materials (worn steel, dark iron, wrapped leather) built from
noise in OBJECT space, so the seams never show in the pattern.
Bake (Cycles) onto the sword's 1:4 UVs, 512 x 2048:
  Sword_BaseColor.png   colour                         (sRGB)
  Sword_MetallicSmoothness.png  R = metallic, A = smoothness (Unity URP/Lit's layout)
  Sword_Normal.png      tangent-space normal, OpenGL Y+ (what Unity expects)
Game object: 'Sword' gets ONE material that uses only the baked images (one draw call),
the procedural version is kept as 'Sword_source', hidden.
"""
import bpy, os, numpy as np

D = bpy.data
OUT = "/mnt/fast/apps/blender-play/export"
W, H = 512, 2048
sc = D.scenes["sword"]
vl = sc.view_layers[0]
ob = sc.objects["Sword"]


# ---------------- node helpers ----------------
def nodes_of(m):
    return m.node_tree.nodes, m.node_tree.links


def node(m, kind, loc, **inputs):
    n = m.node_tree.nodes.new(kind)
    n.location = loc
    for k, v in inputs.items():
        n.inputs[k].default_value = v
    return n


def coord(m, scale, loc=(-1400, 0)):
    tc = node(m, "ShaderNodeTexCoord", loc)
    mp = node(m, "ShaderNodeMapping", (loc[0] + 200, loc[1]))
    mp.inputs["Scale"].default_value = scale
    m.node_tree.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    return mp.outputs["Vector"]


def noise(m, vec, scale, detail, loc, rough=0.55):
    n = node(m, "ShaderNodeTexNoise", loc, Scale=scale, Detail=detail, Roughness=rough)
    m.node_tree.links.new(vec, n.inputs["Vector"])
    return n


def ramp(m, src, stops, loc):
    r = node(m, "ShaderNodeValToRGB", loc)
    els = r.color_ramp.elements
    while len(els) < len(stops):
        els.new(0.5)
    for e, (pos, col) in zip(els, stops):
        e.position = pos
        e.color = (*col, 1) if len(col) == 3 else col
    m.node_tree.links.new(src, r.inputs["Fac"])
    return r


def fresh(name):
    m = D.materials.get(name) or D.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type not in {"BSDF_PRINCIPLED", "OUTPUT_MATERIAL"}:
            nt.nodes.remove(n)
    return m, nt.nodes["Principled BSDF"]


def bump(m, height_socket, strength, distance, loc):
    b = node(m, "ShaderNodeBump", loc, Strength=strength, Distance=distance)
    m.node_tree.links.new(height_socket, b.inputs["Height"])
    return b


# ---------------- worn steel: long polishing scratches along the blade ----------------
steel, p = fresh("Blade_Steel")
L = steel.node_tree.links
v = coord(steel, (60, 60, 1.2))                      # stretched along Z = scratches run down the blade
scr = noise(steel, v, 9, 6, (-900, 200), 0.65)
v2 = coord(steel, (1, 1, 1), (-1400, -400))
blot = noise(steel, v2, 14, 4, (-900, -300))
col = ramp(steel, blot.outputs["Fac"], [(0.35, (0.50, 0.51, 0.53)), (0.7, (0.70, 0.71, 0.74))], (-600, 300))
L.new(col.outputs["Color"], p.inputs["Base Color"])
rgh = ramp(steel, scr.outputs["Fac"], [(0.4, (0.18, 0.18, 0.18)), (0.62, (0.42, 0.42, 0.42))], (-600, 0))
L.new(rgh.outputs["Color"], p.inputs["Roughness"])
p.inputs["Metallic"].default_value = 1.0
L.new(bump(steel, scr.outputs["Fac"], 0.12, 0.002, (-300, -300)).outputs["Normal"], p.inputs["Normal"])

# ---------------- dark iron: pitted, with rust in the low spots ----------------
iron, p = fresh("Guard_Iron")
L = iron.node_tree.links
v = coord(iron, (1, 1, 1))
pit = noise(iron, v, 120, 8, (-900, 200), 0.6)
rust = noise(iron, v, 22, 5, (-900, -200))
col = ramp(iron, rust.outputs["Fac"], [(0.52, (0.16, 0.15, 0.145)), (0.66, (0.24, 0.12, 0.06))], (-600, 300))
L.new(col.outputs["Color"], p.inputs["Base Color"])
rgh = ramp(iron, rust.outputs["Fac"], [(0.5, (0.45, 0.45, 0.45)), (0.7, (0.8, 0.8, 0.8))], (-600, 0))
L.new(rgh.outputs["Color"], p.inputs["Roughness"])
met = ramp(iron, rust.outputs["Fac"], [(0.55, (1, 1, 1)), (0.7, (0.2, 0.2, 0.2))], (-600, -250))
L.new(met.outputs["Color"], p.inputs["Metallic"])     # rust is not metal
L.new(bump(iron, pit.outputs["Fac"], 0.35, 0.002, (-300, -350)).outputs["Normal"], p.inputs["Normal"])

# ---------------- leather: grain plus a stitched wrap ----------------
leather, p = fresh("Grip_Leather")
L = leather.node_tree.links
v = coord(leather, (1, 1, 1))
grain = noise(leather, v, 260, 6, (-900, 250), 0.7)
wave = node(leather, "ShaderNodeTexWave", (-900, -150), Scale=52, Distortion=1.5)
wave.wave_type = "BANDS"; wave.bands_direction = "Z"
L.new(v, wave.inputs["Vector"])
mix = node(leather, "ShaderNodeMath", (-650, -150)); mix.operation = "MULTIPLY"
L.new(wave.outputs["Fac"], mix.inputs[0]); L.new(grain.outputs["Fac"], mix.inputs[1])
col = ramp(leather, grain.outputs["Fac"], [(0.35, (0.07, 0.035, 0.018)), (0.65, (0.16, 0.085, 0.045))], (-600, 350))
L.new(col.outputs["Color"], p.inputs["Base Color"])
rgh = ramp(leather, wave.outputs["Fac"], [(0.2, (0.55, 0.55, 0.55)), (0.9, (0.8, 0.8, 0.8))], (-600, 50))
L.new(rgh.outputs["Color"], p.inputs["Roughness"])
p.inputs["Metallic"].default_value = 0.0
L.new(bump(leather, mix.outputs["Value"], 0.6, 0.003, (-300, -350)).outputs["Normal"], p.inputs["Normal"])

SOURCE = [steel, iron, leather]

# ---------------- the bake ----------------
for o in sc.objects:
    o.select_set(o == ob, view_layer=vl)
vl.objects.active = ob
sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.samples = 4
sc.render.bake.margin = 12
sc.render.bake.normal_space = "TANGENT"


def target(name, noncolor, alpha=False):
    img = D.images.get(name)
    if img:
        D.images.remove(img)
    img = D.images.new(name, W, H, alpha=alpha)
    if noncolor:
        img.colorspace_settings.name = "Non-Color"
    for m in SOURCE:
        t = m.node_tree.nodes.get("bake_target") or m.node_tree.nodes.new("ShaderNodeTexImage")
        t.name = "bake_target"; t.location = (300, 400); t.image = img
        m.node_tree.nodes.active = t
    return img


def bake_channel(socket, img):
    """Route one Principled input into an Emission shader, bake EMIT, put it back."""
    saved = []
    for m in SOURCE:
        nt = m.node_tree
        pb, out = nt.nodes["Principled BSDF"], nt.nodes["Material Output"]
        em = nt.nodes.new("ShaderNodeEmission"); em.name = "bake_emit"
        src = pb.inputs[socket]
        if src.is_linked:
            nt.links.new(src.links[0].from_socket, em.inputs["Color"])
        else:
            val = src.default_value
            em.inputs["Color"].default_value = tuple(val) if hasattr(val, "__len__") else (val, val, val, 1)
        nt.links.new(em.outputs[0], out.inputs["Surface"])
        saved.append((nt, pb, out, em))
    run_bake("EMIT")
    for nt, pb, out, em in saved:
        nt.links.new(pb.outputs[0], out.inputs["Surface"])
        nt.nodes.remove(em)


win = bpy.context.window_manager.windows[0]
area = next(a for a in win.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")


def run_bake(kind):
    with bpy.context.temp_override(window=win, area=area, region=region, scene=sc, view_layer=vl,
                                   active_object=ob, object=ob, selected_objects=[ob]):
        bpy.ops.object.bake(type=kind, margin=12, use_clear=True)


def save(img, fname):
    img.filepath_raw = os.path.join(OUT, fname)
    img.file_format = "PNG"
    img.save()


base = target("Sword_BaseColor", False)
bake_channel("Base Color", base)
save(base, "Sword_BaseColor.png")

rough = target("Sword_Roughness_tmp", True)
bake_channel("Roughness", rough)
metal = target("Sword_Metallic_tmp", True)
bake_channel("Metallic", metal)

normal = target("Sword_Normal", True)
run_bake("NORMAL")
save(normal, "Sword_Normal.png")

# Unity URP/Lit: metallic in R (G, B unused), smoothness = 1 - roughness in A
r = np.empty(W * H * 4, dtype=np.float32); rough.pixels.foreach_get(r)
mt = np.empty(W * H * 4, dtype=np.float32); metal.pixels.foreach_get(mt)
ms = np.empty(W * H * 4, dtype=np.float32)
ms[0::4] = ms[1::4] = ms[2::4] = mt[0::4]
ms[3::4] = 1.0 - r[0::4]
msimg = D.images.get("Sword_MetallicSmoothness")
if msimg:
    D.images.remove(msimg)
msimg = D.images.new("Sword_MetallicSmoothness", W, H, alpha=True)
msimg.colorspace_settings.name = "Non-Color"
msimg.alpha_mode = "STRAIGHT"
msimg.pixels.foreach_set(ms)
save(msimg, "Sword_MetallicSmoothness.png")
D.images.remove(rough); D.images.remove(metal)
for m in SOURCE:                                      # the target node is a bake tool, not part of the look
    t = m.node_tree.nodes.get("bake_target")
    if t:
        m.node_tree.nodes.remove(t)

# ---------------- the game version: one mesh, one material, baked images only ----------------
src = sc.objects.get("Sword_source")
if src is None:
    src = ob.copy(); src.data = ob.data.copy(); src.name = "Sword_source"
    sc.collection.objects.link(src)
src.hide_set(True, view_layer=vl); src.hide_render = True

game = D.materials.get("Sword_Mat") or D.materials.new("Sword_Mat")
game.use_nodes = True
nt = game.node_tree
for n in list(nt.nodes):
    if n.type != "OUTPUT_MATERIAL":
        nt.nodes.remove(n)
pb = nt.nodes.new("ShaderNodeBsdfPrincipled"); pb.location = (0, 0)
nt.links.new(pb.outputs[0], nt.nodes["Material Output"].inputs["Surface"])


def tex(img, loc, noncolor):
    t = nt.nodes.new("ShaderNodeTexImage"); t.image = img; t.location = loc
    if noncolor:
        img.colorspace_settings.name = "Non-Color"
    return t


tb = tex(base, (-700, 300), False)
nt.links.new(tb.outputs["Color"], pb.inputs["Base Color"])
tm = tex(msimg, (-700, 0), True)
sep = nt.nodes.new("ShaderNodeSeparateColor"); sep.location = (-400, 50)
nt.links.new(tm.outputs["Color"], sep.inputs["Color"])
nt.links.new(sep.outputs["Red"], pb.inputs["Metallic"])
inv = nt.nodes.new("ShaderNodeMath"); inv.operation = "SUBTRACT"; inv.location = (-400, -100)
inv.inputs[0].default_value = 1.0
nt.links.new(tm.outputs["Alpha"], inv.inputs[1])
nt.links.new(inv.outputs[0], pb.inputs["Roughness"])
tn = tex(normal, (-700, -350), True)
nm = nt.nodes.new("ShaderNodeNormalMap"); nm.location = (-400, -350)
nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
nt.links.new(nm.outputs["Normal"], pb.inputs["Normal"])

me = ob.data
for poly in me.polygons:
    poly.material_index = 0
me.materials.clear()
me.materials.append(game)

# ---------------- export: FBX with the textures embedded, plus the PNGs beside it ----------------
sc.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items.keys() else "BLENDER_EEVEE"
for o in sc.objects:
    o.select_set(o == ob, view_layer=vl)
bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, "Sword.fbx"), use_selection=True, object_types={"MESH"},
                         apply_unit_scale=True, apply_scale_options="FBX_SCALE_UNITS",
                         axis_forward="-Z", axis_up="Y", bake_space_transform=True,
                         mesh_smooth_type="FACE", add_leaf_bones=False,
                         path_mode="COPY", embed_textures=True)
ob.select_set(False)
for w in bpy.context.window_manager.windows:
    for a in w.screen.areas:
        if a.type == "VIEW_3D":
            a.spaces.active.shading.type = "RENDERED"
bpy.ops.wm.save_mainfile()
print("baked:", sorted(f for f in os.listdir(OUT) if f.startswith("Sword")))
