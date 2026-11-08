"""Export one Forge model from any .blend/.fbx/.glb: blender -b --python forge_export2.py -- spec.json

spec: {"src", "objects": [names] | null (all meshes), "out_dir", "name",
       "rotate": [x, y, z] degrees applied first (Blender axes), "length": metres along Z after rotating (scales to it),
       "flip": true to turn it end over end (180 deg about X) so the grip end is down,
       "grip": z of the grip as a fraction of the length from the bottom, "hulls": [z fractions to cut colliders at],
       "bake": true -> new UV atlas, bake base colour (and normals, if the materials have any) to <name>_BaseColor/_Normal,
       "size": bake size, "wire": {"base": img, "normal": img} hooks images into legacy materials first,
       "parts": {material: part} -> no bake: each part is its own mesh <name>_<part>_LOD0 with its material's own maps
                (<name>_<part>_BaseColor/_Normal/_MetallicSmoothness/_Occlusion), "size" caps their size, "part_size": {part: cap},
                "arm": true -> the roughness map's red is occlusion (Poly Haven), "alpha_maps": {part: image} its alpha,
       "decimate": ratio for LOD0 (an over-dense source), "lods": [ratios] adds <..>_LOD1, _LOD2 (parts only),
       "collide": [parts] -> colliders from these parts only}
"""
import json
import math
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector

spec = json.load(open(sys.argv[sys.argv.index("--") + 1]))
src, name, out_dir = spec["src"], spec["name"], spec["out_dir"]
os.makedirs(out_dir, exist_ok=True)

if src.lower().endswith(".blend"):
    bpy.ops.wm.open_mainfile(filepath=src)
else:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    (bpy.ops.import_scene.gltf if src.lower().endswith((".glb", ".gltf")) else bpy.ops.import_scene.fbx)(filepath=src)

scene = bpy.context.scene
wanted = spec.get("objects")
sources = [o for o in scene.objects if o.type == "MESH" and (wanted is None or o.name in wanted)]
assert sources, "no meshes"

# Legacy (Blender Internal) materials keep their images outside the node tree: hook them in so a bake sees them.
wire = spec.get("wire") or {}
for o in sources:
    for slot in o.material_slots:
        m = slot.material
        hook = wire.get(m.name) if m else None
        if not hook:
            continue
        m.use_nodes = True
        nt = m.node_tree
        bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf is None:
            bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
            out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None) or nt.nodes.new("ShaderNodeOutputMaterial")
            nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
        if any(l.to_node == bsdf for l in nt.links if l.to_socket.name == "Base Color"):
            continue  # already hooked (a material shared by several sources)
        uv = nt.nodes.new("ShaderNodeUVMap")
        uv.uv_map = o.data.uv_layers.active.name
        scale = nt.nodes.new("ShaderNodeVectorMath")
        scale.operation = "MULTIPLY"
        scale.inputs[1].default_value = [hook.get("tile", 1.0)] * 3
        nt.links.new(uv.outputs["UV"], scale.inputs[0])
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images[hook["base"]]
        nt.links.new(scale.outputs["Vector"], tex.inputs["Vector"])
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        if hook.get("normal"):
            nimg = bpy.data.images[hook["normal"]]
            nimg.colorspace_settings.name = "Non-Color"
            ntex = nt.nodes.new("ShaderNodeTexImage")
            ntex.image = nimg
            nt.links.new(scale.outputs["Vector"], ntex.inputs["Vector"])
            nmap = nt.nodes.new("ShaderNodeNormalMap")
            nmap.uv_map = uv.uv_map
            nt.links.new(ntex.outputs["Color"], nmap.inputs["Color"])
            nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])

# One mesh: copies of the sources, modifiers applied, joined.
dg = bpy.context.evaluated_depsgraph_get()
bm = bmesh.new()
mats = []
for o in sources:
    ev = o.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev)
    me.transform(o.matrix_world)
    remap = []
    for slot in o.material_slots:
        if slot.material not in mats:
            mats.append(slot.material)
        remap.append(mats.index(slot.material))
    for p in me.polygons:
        p.material_index = remap[p.material_index] if remap else 0
    bm.from_mesh(me)
    bpy.data.meshes.remove(me)
if spec.get("fix_normals"):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
if spec.get("double_sided"):  # single planes (planks, boards): each gets a back face, sharing its UVs
    back = bmesh.ops.duplicate(bm, geom=list(bm.faces))["geom"]
    bmesh.ops.reverse_faces(bm, faces=[f for f in back if isinstance(f, bmesh.types.BMFace)])
mesh = bpy.data.meshes.new(f"{name}_LOD0")
bm.to_mesh(mesh)
bm.free()
for m in mats:
    mesh.materials.append(m)
obj = bpy.data.objects.new(f"{name}_LOD0", mesh)
for o in list(scene.objects):
    o.hide_render = True
    o.hide_set(True)
scene.collection.objects.link(obj)

# Turn, flip, scale to length, grip to the origin.
rot = Euler([math.radians(a) for a in spec.get("rotate", [0, 0, 0])]).to_matrix().to_4x4()
if spec.get("flip"):
    rot = Matrix.Rotation(math.pi, 4, "X") @ rot
mesh.transform(rot)
if spec.get("stretch"):
    mesh.transform(Matrix.Diagonal(list(spec["stretch"]) + [1.0]))
zs = [v.co.z for v in mesh.vertices]
k = spec["scale"] if "scale" in spec else spec["length"] / (max(zs) - min(zs))
mesh.transform(Matrix.Scale(k, 4))
xs, ys, zs = ([v.co[i] for v in mesh.vertices] for i in range(3))
length = max(zs) - min(zs)
grip = Vector(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, min(zs) + spec["grip"] * length))
grip = Vector(spec["grip_xy"] + [grip.z]) if spec.get("grip_xy") else grip
mesh.transform(Matrix.Translation(-grip))
mesh.update()

bpy.context.view_layer.objects.active = obj
obj.hide_set(False)
obj.select_set(True)

textures = {}
parts = spec.get("parts")
if spec.get("bake") and not parts:
    size = spec.get("size", 1024)
    render_uv = next((u.name for u in mesh.uv_layers if u.active_render), None)
    mesh.uv_layers.new(name="atlas")
    mesh.uv_layers.active = mesh.uv_layers["atlas"]
    if render_uv:
        mesh.uv_layers[render_uv].active_render = True  # the materials keep reading their own UVs
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 8
    scene.cycles.device = "CPU"
    has_normals = any(m and m.use_nodes and any(n.type == "NORMAL_MAP" for n in m.node_tree.nodes) for m in mats)
    surface = spec.get("surface")
    passes = ([("Normal", "NORMAL")] if has_normals else []) + [("BaseColor", "EMIT")] + ([("Surface", "EMIT")] if surface else []) + ([("Alpha", "EMIT")] if spec.get("alpha") else [])
    for label, kind in passes:
        img = bpy.data.images.new(f"{name}_{label}", size, size, alpha=False)
        if label == "Normal":
            img.colorspace_settings.name = "Non-Color"
        for m in mats:
            if m is None:
                continue
            m.use_nodes = True
            nt = m.node_tree
            node = nt.nodes.new("ShaderNodeTexImage")
            node.image = img
            nt.nodes.active = node
        if label == "BaseColor":
            for m in mats:
                if m is None:
                    continue
                nt = m.node_tree
                em = nt.nodes.new("ShaderNodeEmission")
                link = next((l for l in nt.links if l.to_node.type in ("BSDF_PRINCIPLED", "GROUP", "BSDF_DIFFUSE")
                             and l.to_socket.name in ("Base Color", "Texture", "Color")), None)
                if link:
                    nt.links.new(link.from_socket, em.inputs["Color"])
                else:
                    shader = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
                    em.inputs["Color"].default_value = shader.inputs["Base Color"].default_value if shader else (0.8, 0.8, 0.8, 1)
                for out in [n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"]:
                    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
        elif label == "Alpha":
            for m in mats:
                if m is None:
                    continue
                nt = m.node_tree
                bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
                em = nt.nodes.new("ShaderNodeEmission")
                link = next((l for l in nt.links if l.to_socket.name == "Alpha" and l.to_node.type in ("BSDF_PRINCIPLED", "GROUP")), None)
                if link:
                    nt.links.new(link.from_socket, em.inputs["Color"])
                else:
                    a = bsdf.inputs["Alpha"].default_value if bsdf else 1.0
                    em.inputs["Color"].default_value = (a, a, a, 1.0)
                for out in [n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"]:
                    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
            img.colorspace_settings.name = "Non-Color"
        elif kind == "EMIT":
            for m in mats:
                if m is None:
                    continue
                metal, smooth = surface.get(m.name, surface.get("*", [0.0, 0.3]))
                em = m.node_tree.nodes.new("ShaderNodeEmission")
                em.inputs["Color"].default_value = (metal, smooth, 0.0, 1.0)
                for out in [n for n in m.node_tree.nodes if n.type == "OUTPUT_MATERIAL"]:
                    m.node_tree.links.new(em.outputs["Emission"], out.inputs["Surface"])
            img.colorspace_settings.name = "Non-Color"
        if kind == "DIFFUSE":
            scene.render.bake.use_pass_direct = False
            scene.render.bake.use_pass_indirect = False
            scene.render.bake.use_pass_color = True
        scene.render.bake.margin = 8
        bpy.ops.object.bake(type=kind)
        path = os.path.join(out_dir, f"{name}_{label}.png")
        img.filepath_raw = path
        img.file_format = "PNG"
        img.save()
        textures[label] = path
        for m in mats:
            if m is None:
                continue
            nt = m.node_tree
            for n in [n for n in nt.nodes if n.type == "TEX_IMAGE" and n.image == img]:
                nt.nodes.remove(n)
    if render_uv:
        mesh.uv_layers.remove(mesh.uv_layers[render_uv])
    mesh.uv_layers["atlas"].active_render = True

def source_of(socket):
    """(image, channel) feeding a shader socket, through Separate Color, Math and Normal Map; channel "rgb", 0-2 or 3."""
    if not socket.is_linked:
        return None
    link = socket.links[0]
    node = link.from_node
    if node.type == "TEX_IMAGE" and node.image:
        return node.image, 3 if link.from_socket.name == "Alpha" else "rgb"
    if node.type == "SEPARATE_COLOR":
        found = source_of(node.inputs[0])
        return (found[0], {"Red": 0, "Green": 1, "Blue": 2}[link.from_socket.name]) if found else None
    if node.type in ("MATH", "NORMAL_MAP", "MIX", "MIX_RGB"):
        # Through to whichever input reaches an image (a glTF colour times its vertex colour: the texture; URP Lit
        # draws no vertex colour).
        for i in node.inputs:
            found = source_of(i) if i.is_linked else None
            if found:
                return found
    return None


def gltf_occlusion():
    # glTF keeps ambient occlusion outside Blender's node tree: material name -> the image whose red is its occlusion.
    if not src.lower().endswith(".gltf"):
        return {}
    g = json.load(open(src, encoding="utf-8"))
    found = {}
    for m in g.get("materials", []):
        occ = m.get("occlusionTexture")
        if occ is not None:
            uri = g["images"][g["textures"][occ["index"]]["source"]]["uri"]
            found[m["name"]] = os.path.join(os.path.dirname(src), uri.replace("%20", " "))
    return found


def pixels(img, cap):
    """An image's raw pixels as (h, w, 4), shrunk to fit cap."""
    w, h = img.size
    if max(w, h) > cap:
        img.scale(max(1, cap * w // max(w, h)), max(1, cap * h // max(w, h)))
    a = np.empty(img.size[0] * img.size[1] * 4, np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(img.size[1], img.size[0], 4)


def fit(a, shape):
    # Nearest-pixel resample to (h, w): the maps of one material sometimes differ in size.
    if a.shape[:2] == shape:
        return a
    ys = np.arange(shape[0]) * a.shape[0] // shape[0]
    xs = np.arange(shape[1]) * a.shape[1] // shape[1]
    return a[ys][:, xs]


def channel(found, cap, default, shape):
    if not found:
        return np.full(shape, default, np.float32)
    a = pixels(found[0], cap)
    return fit(a[..., 0] if found[1] == "rgb" else a[..., found[1]], shape)


def save(arr, label, alpha, colour):
    h, w = arr.shape[:2]
    img = bpy.data.images.new(f"{name}_{label}", w, h, alpha=alpha)
    img.colorspace_settings.name = "sRGB" if colour else "Non-Color"
    img.pixels.foreach_set(np.ascontiguousarray(arr, np.float32).ravel())
    path = os.path.join(out_dir, f"{name}_{label}.{'png' if alpha else 'jpg'}")
    if colour:
        img.filepath_raw = path
        img.file_format = "PNG" if alpha else "JPEG"
        img.save(quality=92)
    else:  # data maps: the render settings' strongest lossless compression, no colour transform
        st = scene.render.image_settings
        st.file_format, st.color_mode = ("PNG", "RGBA") if alpha else ("JPEG", "RGB")
        st.compression, st.quality = 100, 92
        img.save_render(path, scene=scene)
    textures[label] = path


def write_maps(part, m, cap, occlusion, alpha_map=None):
    """A part's maps from its material: base colour (with its alpha, if the material has one), normal, metal and
    smoothness, occlusion."""
    bsdf = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    base = source_of(bsdf.inputs["Base Color"])
    if base:
        colour = pixels(base[0], cap).copy()
    else:
        colour = np.ones((4, 4, 4), np.float32) * np.array(list(bsdf.inputs["Base Color"].default_value), np.float32)
    shape = colour.shape[:2]
    alpha = source_of(bsdf.inputs["Alpha"])
    if alpha_map:  # an alpha the source keeps beside its colour, not in it (Poly Haven's sails): its red
        alpha = (bpy.data.images.load(alpha_map), 0)
    if alpha:
        colour[..., 3] = channel(alpha, cap, 1.0, shape)
    save(colour, f"{part}BaseColor", alpha=bool(alpha), colour=True)
    normal = source_of(bsdf.inputs["Normal"])
    if normal:
        save(pixels(normal[0], cap), f"{part}Normal", alpha=False, colour=False)
    # Smoothness and occlusion vary slowly: half the colour's size (a quarter of the bytes).
    cap = max(256, cap // 2)
    metal, rough = source_of(bsdf.inputs["Metallic"]), source_of(bsdf.inputs["Roughness"])
    either = rough or metal
    shp = pixels(either[0], cap).shape[:2] if either else (4, 4)
    ms = np.zeros(shp + (4,), np.float32)
    ms[..., 0] = channel(metal, cap, bsdf.inputs["Metallic"].default_value, shp)
    ms[..., 3] = 1.0 - channel(rough, cap, bsdf.inputs["Roughness"].default_value, shp)
    save(ms, f"{part}MetallicSmoothness", alpha=True, colour=False)
    if spec.get("arm") and rough:  # Poly Haven packs occlusion, roughness, metal in one map: occlusion is its red
        ao = pixels(rough[0], cap).copy()
        ao[..., 1] = ao[..., 2] = ao[..., 0]
        save(ao, f"{part}Occlusion", alpha=False, colour=False)
    elif m.name in occlusion:
        ao = pixels(bpy.data.images.load(occlusion[m.name]), cap).copy()
        ao[..., 1] = ao[..., 2] = ao[..., 0]
        save(ao, f"{part}Occlusion", alpha=False, colour=False)


def decimated(source, ratio, label):
    """A copy of source collapsed to ratio of its triangles."""
    o = bpy.data.objects.new(label, source.data.copy())
    scene.collection.objects.link(o)
    mod = o.modifiers.new("lod", "DECIMATE")
    mod.ratio = ratio
    mod.use_collapse_triangulate = True
    data = bpy.data.meshes.new_from_object(o.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    old = o.data
    o.modifiers.clear()
    o.data = data
    bpy.data.meshes.remove(old)
    data.name = label
    return o


drawn = [obj]
collide_faces = None
if parts:
    # One mesh per part, its material's own maps; the levels of detail decimate it. The joined mesh steps aside so a
    # part "" (the model's own mesh) takes the name <name>_LOD0 itself, not <name>_LOD0.001.
    obj.name = mesh.name = f"{name}_joined"
    occlusion = gltf_occlusion()
    cap = spec.get("size", 2048)
    by_part = {}
    for i, m in enumerate(mats):
        assert m is not None and m.name in parts, f"material {m.name if m else None} has no part (spec 'parts')"
        by_part.setdefault(parts[m.name], []).append(i)
    keep = set(spec.get("collide") or by_part)
    drawn, collide_faces = [], []
    for part, indices in by_part.items():
        stem = f"{name}_{part}" if part else name  # part "": the model's own mesh and maps
        write_maps(f"{part}_" if part else "", mats[indices[0]], (spec.get("part_size") or {}).get(part, cap), occlusion,
                   (spec.get("alpha_maps") or {}).get(part))
        pb = bmesh.new()
        pb.from_mesh(mesh)
        bmesh.ops.delete(pb, geom=[f for f in pb.faces if f.material_index not in indices], context="FACES")
        if part in keep:
            collide_faces += [v.co.copy() for v in pb.verts]
        pm = bpy.data.meshes.new(f"{stem}_LOD0")
        pb.to_mesh(pm)
        pb.free()
        po = bpy.data.objects.new(pm.name, pm)
        scene.collection.objects.link(po)
        if spec.get("decimate"):
            d = decimated(po, spec["decimate"], pm.name + "_d")
            label = pm.name
            bpy.data.objects.remove(po)
            bpy.data.meshes.remove(pm)
            d.name = d.data.name = label
            po = d
        drawn.append(po)
        for level, ratio in enumerate(spec.get("lods", []), start=1):
            drawn.append(decimated(po, ratio, f"{stem}_LOD{level}"))
    for o in drawn:
        o.data.materials.clear()
    obj.hide_set(True)
else:
    for slot in obj.material_slots:
        slot.material = None
    while len(mesh.materials) > 1:
        mesh.materials.pop()
    for p in mesh.polygons:
        p.material_index = 0


def hull(label, verts):
    hb = bmesh.new()
    for co in verts:
        hb.verts.new(co)
    bmesh.ops.convex_hull(hb, input=hb.verts)
    bmesh.ops.delete(hb, geom=[v for v in hb.verts if not v.link_faces], context="VERTS")
    data = bpy.data.meshes.new(f"{name}_{label}_COL")
    hb.to_mesh(data)
    hb.free()
    h = bpy.data.objects.new(data.name, data)
    scene.collection.objects.link(h)
    # PhysX cooks a convex hull of at most 255 faces: collapse a larger one and wrap it again (still convex).
    while len(data.polygons) > 250:
        mod = h.modifiers.new("fit", "DECIMATE")
        mod.ratio = 240 / len(data.polygons)
        coarse = bpy.data.meshes.new_from_object(h.evaluated_get(bpy.context.evaluated_depsgraph_get()))
        h.modifiers.clear()
        hb = bmesh.new()
        for v in coarse.vertices:
            hb.verts.new(v.co)
        bpy.data.meshes.remove(coarse)
        bmesh.ops.convex_hull(hb, input=hb.verts)
        bmesh.ops.delete(hb, geom=[v for v in hb.verts if not v.link_faces], context="VERTS")
        hb.to_mesh(data)
        hb.free()
    return h


coords = [v.co.copy() for v in mesh.vertices]
hull_coords = collide_faces if collide_faces is not None else coords
zmin = min(c.z for c in coords)
cols = []
if spec.get("trunk"):
    r, h = spec["trunk"]
    part = [c for c in hull_coords if c.x * c.x + c.y * c.y <= r * r and c.z <= zmin + h]
    if len(part) < 4:  # nothing that slim: a post of that radius and height
        part = [Vector((x * r, y * r, zmin + z * h)) for x in (-1, 1) for y in (-1, 1) for z in (0, 1)]
    cols.append(hull("Trunk", part))
else:
    cuts = [zmin + f * length for f in spec.get("hulls", [])]
    bounds = [-1e9] + cuts + [1e9]
    for i in range(len(bounds) - 1):
        part = [c for c in hull_coords if bounds[i] <= c.z <= bounds[i + 1]]
        if len(part) >= 4:
            cols.append(hull(f"Part{i}", part))

bpy.ops.object.select_all(action="DESELECT")
for o in drawn + cols:
    o.hide_set(False)
    o.select_set(True)
bpy.ops.export_scene.fbx(filepath=os.path.join(out_dir, f"{name}.fbx"), use_selection=True, object_types={"MESH"},
                         apply_unit_scale=True, apply_scale_options="FBX_SCALE_UNITS", axis_forward="-Z", axis_up="Y",
                         bake_space_transform=True, use_mesh_modifiers=True, mesh_smooth_type="FACE",
                         add_leaf_bones=False, path_mode="STRIP")
dims = [round(max(c[i] for c in coords) - min(c[i] for c in coords), 3) for i in range(3)]
tris = {o.name: sum(len(p.vertices) - 2 for p in o.data.polygons) for o in drawn}
print("EXPORTED", name, "tris", tris, "dims", dims, "hulls", [len(c.data.polygons) for c in cols], "textures", list(textures))
