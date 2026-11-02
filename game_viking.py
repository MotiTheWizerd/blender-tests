"""The Viking sword, game-ready: everything in scene `viking` baked onto one low mesh.

    blender -b langford.blend -P game_viking.py        (headless; writes viking_game.blend)

HIGH  every part of the VikingSword collection, curves and modifiers applied, its own
      materials (procedural Damascus / gold / leather, the AI guard and pommel): 166k tris.
LOW   one mesh, triangulated so Unity shades it exactly as it was baked:
        blade, AI guard, AI pommel   decimated copies of the high parts
        grip                         a plain cylinder that encloses the wire braid
        both bands                   the high bands as they are (572 tris each)
      Runes, knotwork and the braid live only in the textures.
BAKE  Cycles, selected-to-active, 4096 x 4096 (Unity can import it smaller):
        Viking_BaseColor (sRGB) · Viking_MetallicSmoothness (R metal, A = 1 - roughness, URP)
        Viking_Normal (tangent, OpenGL +Y, as Unity reads it)
      Base colour, metal and roughness are baked as emission: each high material's own
      socket is wired into an Emission shader, so a metal's colour comes through whole
      (a DIFFUSE colour bake reads black on metal).
THEN  LOD1/LOD2 by decimation, three convex colliders, Viking.fbx (pivot = grip centre,
      point up = Unity +Y), the same import script as the first sword (export/Editor).
"""
import bpy, bmesh, math, os, time
import numpy as np
from mathutils import Matrix, Vector

T0 = time.time()
D = bpy.data
ROOT = os.path.dirname(bpy.data.filepath)
OUT = os.path.join(ROOT, "export", "viking")
os.makedirs(OUT, exist_ok=True)
SIZE = 4096
GRIP_C = (-0.027 + -0.176) / 2            # the grip's centre becomes the pivot
SHIFT = Matrix.Translation((0, 0, -GRIP_C))


def log(*a):
    print(f"[{time.time() - T0:6.1f}s]", *a, flush=True)


vk = D.scenes["viking"]
src = D.collections["VikingSword"]
old = D.scenes.get("viking_game")
if old:
    for o in list(old.objects):
        D.objects.remove(o, do_unlink=True)
    D.scenes.remove(old)
sc = D.scenes.new("viking_game")
vl = sc.view_layers[0]
HIGH = D.collections.new("viking_high"); sc.collection.children.link(HIGH)
GAME = D.collections.new("viking_game"); sc.collection.children.link(GAME)


def depsgraph():
    """The game scene's evaluated depsgraph. A new scene has none until asked through context."""
    with bpy.context.temp_override(scene=sc, view_layer=vl):
        dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    return dg


def ctx(active, selected):
    vl.objects.active = active
    for o in sc.objects:
        o.select_set(o in selected, view_layer=vl)
    return bpy.context.temp_override(scene=sc, view_layer=vl, active_object=active, object=active,
                                     selected_objects=selected, selected_editable_objects=selected)


# ---------------- HIGH: world-space copies, curves made mesh ----------------
dg_vk = vk.view_layers[0].depsgraph
dg_vk.update()
high = {}
for o in src.objects:
    if o.type not in ("MESH", "CURVE"):
        continue
    me = D.meshes.new_from_object(o.evaluated_get(dg_vk), preserve_all_data_layers=True, depsgraph=dg_vk)
    me.transform(SHIFT @ o.matrix_world)
    me.name = o.name + "_high"
    h = D.objects.new(o.name + "_high", me)
    HIGH.objects.link(h)
    high[o.name] = h
log("high:", sum(len(h.data.polygons) for h in high.values()), "faces in", len(high), "parts")


# ---------------- LOW ----------------
def decimated(h, tris):
    """A collapse-decimated copy of a high part, aiming at `tris` triangles."""
    have = sum(len(p.vertices) - 2 for p in h.data.polygons)
    tmp = D.objects.new("tmp", h.data)
    sc.collection.objects.link(tmp)
    m = tmp.modifiers.new("d", "DECIMATE")
    m.decimate_type = "COLLAPSE"; m.ratio = min(1.0, tris / have); m.use_collapse_triangulate = True
    dg = depsgraph()
    me = D.meshes.new_from_object(tmp.evaluated_get(dg))
    D.objects.remove(tmp, do_unlink=True)
    return me


def cylinder(r, z0, z1, seg=20):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=False, segments=seg, radius1=r, radius2=r, depth=z1 - z0,
                          matrix=Matrix.Translation((0, 0, (z0 + z1) / 2 - GRIP_C)))
    me = D.meshes.new("cyl"); bm.to_mesh(me); bm.free()
    return me


parts = [
    decimated(high["Blade"], 1000),
    decimated(high["Guard_AI"], 4400),
    decimated(high["Pommel_AI"], 2200),
    cylinder(0.0238, -0.1775, -0.0255),       # encloses the braid (wires reach r = 0.025)
    high["BandTop"].data.copy(),
    high["BandBottom"].data.copy(),
]
bm = bmesh.new()
for me in parts:
    bm.from_mesh(me)
bmesh.ops.triangulate(bm, faces=bm.faces[:])
for f in bm.faces:
    f.smooth = True
low_me = D.meshes.new("Viking_LOD0"); bm.to_mesh(low_me); bm.free()
low_me.materials.clear()
low_me.set_sharp_from_angle(angle=math.radians(50))
low = D.objects.new("Viking_LOD0", low_me)
GAME.objects.link(low)
log("low:", len(low_me.polygons), "tris")

for coll in (low_me.vertices, low_me.edges, low_me.polygons):
    coll.foreach_set("select", [True] * len(coll))
with ctx(low, [low]):
    bpy.ops.object.mode_set(mode="EDIT")
# headless: an override made before edit mode does not see the edit object, so a fresh one does
with bpy.context.temp_override(scene=sc, view_layer=vl, active_object=low, object=low, edit_object=low,
                               selected_objects=[low], selected_editable_objects=[low]):
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.003, area_weight=0.0)
    bpy.ops.uv.pack_islands(rotate=True, margin=0.003)
with ctx(low, [low]):
    bpy.ops.object.mode_set(mode="OBJECT")
log("uv: smart project + pack")


# ---------------- BAKE ----------------
def image(name, srgb):
    im = D.images.get(name)
    if im:
        D.images.remove(im)
    im = D.images.new(name, SIZE, SIZE, alpha=False, float_buffer=False)
    im.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
    return im


game = D.materials.get("Viking") or D.materials.new("Viking")
game.use_nodes = True
low_me.materials.append(game)
gnt = game.node_tree
target = gnt.nodes.get("bake_target") or gnt.nodes.new("ShaderNodeTexImage")
target.name = "bake_target"
gnt.nodes.active = target

originals = {h: [s.material for s in h.material_slots] for h in high.values()}


def emissive(m, socket):
    """A copy of m whose surface is an Emission of the Principled BSDF's `socket`."""
    c = m.copy(); c.name = f"{m.name}__{socket}"
    nt = c.node_tree
    out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output), None) or \
        next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    b = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    em = nt.nodes.new("ShaderNodeEmission"); em.inputs["Strength"].default_value = 1.0
    if b is None:
        em.inputs["Color"].default_value = (0.5, 0.5, 0.5, 1)
    else:
        inp = b.inputs[socket]
        if inp.is_linked:
            nt.links.new(inp.links[0].from_socket, em.inputs["Color"])
        else:
            v = inp.default_value
            em.inputs["Color"].default_value = (tuple(v)[:3] + (1,)) if hasattr(v, "__len__") else (v, v, v, 1)
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return c


sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.samples = 4
bk = sc.render.bake
bk.use_selected_to_active = True
bk.use_cage = False
bk.cage_extrusion = 0.003                  # the knots and the braid stand up to 1.5 mm proud of the low
bk.max_ray_distance = 0.012
bk.margin = 12
bk.margin_type = "EXTEND"
bk.normal_space = "TANGENT"

highs = list(high.values())
baked = {}
for name, socket, srgb in (("BaseColor", "Base Color", True), ("Metallic", "Metallic", False),
                           ("Roughness", "Roughness", False), ("Normal", None, False)):
    for h, mats in originals.items():
        for i, m in enumerate(mats):
            h.material_slots[i].material = m if socket is None or m is None else emissive(m, socket)
    im = image("Viking_" + name, srgb)
    target.image = im
    with ctx(low, highs + [low]):
        bpy.ops.object.bake(type="NORMAL" if socket is None else "EMIT")
    baked[name] = im
    log("baked", name)
for h, mats in originals.items():
    for i, m in enumerate(mats):
        h.material_slots[i].material = m
for m in [m for m in D.materials if "__" in m.name and m.users == 0]:
    D.materials.remove(m)


def save(im, path):
    im.filepath_raw = path; im.file_format = "PNG"; im.save()


save(baked["BaseColor"], os.path.join(OUT, "Viking_BaseColor.png"))
save(baked["Normal"], os.path.join(OUT, "Viking_Normal.png"))
px = lambda im: (lambda a: (im.pixels.foreach_get(a), a)[1])(np.empty(SIZE * SIZE * 4, np.float32))
met, rough = px(baked["Metallic"]), px(baked["Roughness"])
ms = np.empty_like(met)
ms[0::4] = ms[1::4] = ms[2::4] = met[0::4]
ms[3::4] = 1.0 - rough[0::4]
msi = D.images.new("Viking_MetallicSmoothness", SIZE, SIZE, alpha=True, float_buffer=False)
msi.colorspace_settings.name = "Non-Color"
msi.pixels.foreach_set(ms)
save(msi, os.path.join(OUT, "Viking_MetallicSmoothness.png"))
for n in ("Metallic", "Roughness"):
    D.images.remove(baked[n])
log("saved textures")

# ---------------- the game material, as Unity will wear it ----------------
gnt.nodes.clear()
o = gnt.nodes.new("ShaderNodeOutputMaterial"); b = gnt.nodes.new("ShaderNodeBsdfPrincipled")
gnt.links.new(b.outputs[0], o.inputs[0])
tb = gnt.nodes.new("ShaderNodeTexImage"); tb.image = baked["BaseColor"]
tm = gnt.nodes.new("ShaderNodeTexImage"); tm.image = msi
tn = gnt.nodes.new("ShaderNodeTexImage"); tn.image = baked["Normal"]
inv = gnt.nodes.new("ShaderNodeMath"); inv.operation = "SUBTRACT"; inv.inputs[0].default_value = 1.0
nm = gnt.nodes.new("ShaderNodeNormalMap")
gnt.links.new(tb.outputs["Color"], b.inputs["Base Color"])
gnt.links.new(tm.outputs["Color"], b.inputs["Metallic"])
gnt.links.new(tm.outputs["Alpha"], inv.inputs[1])
gnt.links.new(inv.outputs[0], b.inputs["Roughness"])
gnt.links.new(tn.outputs["Color"], nm.inputs["Color"])
gnt.links.new(nm.outputs["Normal"], b.inputs["Normal"])

# ---------------- hierarchy, LODs, colliders ----------------
root = D.objects.new("VikingSword", None); root.empty_display_size = 0.1
GAME.objects.link(root)
low.parent = root
lods = [low]
for name, ratio in (("Viking_LOD1", 0.5), ("Viking_LOD2", 0.2)):
    l = low.copy(); l.data = low.data.copy(); l.name = l.data.name = name
    d = l.modifiers.new("decimate", "DECIMATE")
    d.decimate_type = "COLLAPSE"; d.ratio = ratio; d.use_collapse_triangulate = True
    GAME.objects.link(l); l.parent = root; lods.append(l)

col_mat = D.materials.get("Collider") or D.materials.new("Collider")


def hull(name, boxes, extra=()):
    bm = bmesh.new()
    for (x, y, z0, z1) in boxes:
        for sx in (-1, 1):
            for sy in (-1, 1):
                for z in (z0, z1):
                    bm.verts.new((sx * x, sy * y, z - GRIP_C))
    for p in extra:
        bm.verts.new((p[0], p[1], p[2] - GRIP_C))
    bmesh.ops.convex_hull(bm, input=bm.verts)
    me = D.meshes.new(name); bm.to_mesh(me); bm.free()
    me.materials.append(col_mat)
    c = D.objects.new(name, me); GAME.objects.link(c); c.parent = root
    c.display_type = "WIRE"; c.hide_render = True
    return c


cols = [
    hull("Viking_Blade_COL", [(0.037, 0.0050, 0.040, 0.040), (0.031, 0.0035, 0.55, 0.55)], [(0, 0, 0.658)]),
    hull("Viking_Guard_COL", [(0.088, 0.016, -0.026, 0.040)]),
    hull("Viking_Grip_COL", [(0.029, 0.029, -0.194, -0.012), (0.058, 0.042, -0.281, -0.19)]),
]

# ---------------- export ----------------
objs = [root] + lods + cols
with ctx(root, objs):
    bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, "Viking.fbx"), use_selection=True,
                             object_types={"EMPTY", "MESH"}, apply_unit_scale=True,
                             apply_scale_options="FBX_SCALE_UNITS", axis_forward="-Z", axis_up="Y",
                             bake_space_transform=True, use_mesh_modifiers=True, mesh_smooth_type="FACE",
                             add_leaf_bones=False, path_mode="COPY", embed_textures=True)
dg = depsgraph()
tri = lambda ob: sum(len(p.vertices) - 2 for p in ob.evaluated_get(dg).data.polygons)
log("exported", {ob.name: tri(ob) for ob in lods + cols})

# ---------------- preview: the game mesh alone, in EEVEE, as the reference sheet ----------------
for o in HIGH.objects:
    o.hide_render = True
for l in lods[1:]:
    l.hide_render = True
sc.render.engine = "BLENDER_EEVEE"
sc.world = vk.world
for o in vk.objects:
    if o.type == "LIGHT":
        sc.collection.objects.link(o)
cd = D.cameras.new("cam"); cd.type = "ORTHO"; cd.ortho_scale = 0.32
cam = D.objects.new("cam", cd); sc.collection.objects.link(cam); sc.camera = cam
sc.render.resolution_x, sc.render.resolution_y = 1000, 1200
centre = Vector((0, 0, -0.08 - GRIP_C))
for name, az, el, scale in (("viking_game_hilt", 0, 6, 0.32), ("viking_game_hilt_34", 35, 18, 0.32),
                            ("viking_game_full", 0, 0, 1.0)):
    a, e = math.radians(az), math.radians(el)
    cd.ortho_scale = scale
    c = centre if scale < 0.5 else Vector((0, 0, 0.19 - GRIP_C))
    cam.location = c + Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))) * 1.5
    cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = os.path.join(OUT, name + ".png")
    with bpy.context.temp_override(scene=sc, view_layer=vl):
        bpy.ops.render.render(write_still=True, scene=sc.name)
    log("rendered", name)

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(ROOT, "viking_game.blend"), copy=True, relative_remap=True)
log("saved viking_game.blend")
