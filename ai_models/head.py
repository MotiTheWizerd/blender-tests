"""A head for Forge's face editor: a Tripo bust (bald, neutral, symmetric), at a real head's size, exported for Forge.

    blender -b --factory-startup -P head.py -- head_warrior_m WarriorM

Reads <name>/source_tripo.fbx (and its .fbm textures), finds the chin and the crown on the face's middle line, scales
the bust so they are HEAD_HEIGHT apart (an adult's chin to crown), and writes build/forge/<Title>/: <Title>.fbx
(metres, front to Unity's +Z, as export.py), <Title>_BaseColor.jpg, <Title>_Normal.png and
<Title>_MetallicSmoothness.png (no metal: skin; smoothness = (1 - roughness) * SKIN_SHINE), the maps at MAP_SIZE; and its
eyes of their own (eyes.py: the painted eyes opened, eyeballs put in, their material <Title>Eyes, the mesh's second,
with <Title>Eyes_Color.png and <Title>Eyes_MetallicSmoothness.png). checks/head.json says what was measured;
checks/eyes_*.jpg and eyes_map_<side>.png show the eyes.
"""
import bpy, json, os, sys
import numpy as np
from mathutils import Vector

NAME, TITLE = sys.argv[sys.argv.index("--") + 1:][:2]
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from face import profile
ROOT = os.path.join(HERE, NAME)
OUT = os.path.join(ROOT, "build", "forge", TITLE)
HEAD_HEIGHT = 0.232  # chin to crown, an adult man's
EYES_OVER_HEIGHT = (0.245, 0.33)  # the eyes' middles apart over chin to crown, a face's (WarriorM 0.281, WarriorM2 0.297, WarriorF 0.284; WarriorF2 0.254 as a tall narrow head and 0.320 made from the sheet, landmarks_*.jpg right both times)
MAP_SIZE = 4096
SKIN_SHINE = 0.6  # Tripo's roughness read as URP smoothness looks wet (oily lips and brow): skin shines this much of it
ROUGHNESS = 0.55  # skin's roughness, flat, for an export without a roughness map (WarriorF3)

os.makedirs(OUT, exist_ok=True)
os.makedirs(os.path.join(ROOT, "checks"), exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
# Tripo's FBX export (source_tripo.fbx + .fbm) or its GLB (source_tripo.glb; WarriorF5). A glTF splits its vertices
# along every texture seam (the recipe's step 1), so it is welded first, or every seam is an open edge to close_holes
# and the eyes' cut; its roughness is the green channel of a packed map (image_of says which).
GLB = not os.path.exists(os.path.join(ROOT, "source_tripo.fbx")) and os.path.exists(os.path.join(ROOT, "source_tripo.glb"))
SOURCE = os.path.join(ROOT, "source_tripo.glb" if GLB else "source_tripo.fbx")
# The reduced head (reduce_head: 4 minutes on a 2M-triangle GLB) kept beside the build and taken from there while the
# source is older than it, so a run that fails past it (an eye's cut) costs seconds to try again. Delete it to reduce afresh.
REDUCED = os.path.join(ROOT, "build", f"{TITLE}_reduced.blend")
FROM_REDUCED = os.path.exists(REDUCED) and os.path.getmtime(REDUCED) > os.path.getmtime(SOURCE)
if FROM_REDUCED:
    bpy.ops.wm.open_mainfile(filepath=REDUCED)
    print(f"REDUCE taken from {os.path.basename(REDUCED)}")
elif GLB:
    bpy.ops.import_scene.gltf(filepath=SOURCE)
else:
    bpy.ops.import_scene.fbx(filepath=SOURCE)
head = next(o for o in bpy.context.scene.objects if o.type == "MESH")
bpy.context.view_layer.objects.active = head
head.select_set(True)
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
if GLB and not FROM_REDUCED:
    import bmesh
    welded = bmesh.new()
    welded.from_mesh(head.data)
    before_weld = len(welded.verts)
    bmesh.ops.remove_doubles(welded, verts=welded.verts, dist=1e-5)
    welded.to_mesh(head.data)
    welded.free()
    print(f"WELD {before_weld} -> {len(head.data.vertices)} vertices")

HEAD_TRIANGLES = 50000      # a head's game mesh (the FBX exports came at 50k to 94k; a face editor head is seen closest)
REDUCE_OVER = 60000         # a source past this many triangles is reduced, its detail baked into its normal map
BAKE_REACH = 0.004          # the bake's cage out past the reduced surface, a share of the head's size (reduce.py's)


def reduce_head(high):
    """A game mesh from a film-scale head (Tripo's GLB: WarriorF5 came at 1.96M triangles), as reduce.py makes a
    creature's: a collapse to HEAD_TRIANGLES keeping the UVs (the colour and roughness maps still fit), smooth and
    triangulated, and its normals baked in Cycles from the full head with its own normal map, so the sculpt's pores
    and folds ride on the reduced mesh. Returns the reduced head; the full one is gone."""
    scene = bpy.context.scene
    source = sum(len(f.vertices) - 2 for f in high.data.polygons)
    low = high.copy(); low.data = high.data.copy()
    scene.collection.objects.link(low)
    bpy.context.view_layer.objects.active = low
    mod = low.modifiers.new("reduce", "DECIMATE")
    mod.decimate_type = "COLLAPSE"
    mod.ratio = HEAD_TRIANGLES / source
    mod.use_collapse_triangulate = True
    bpy.ops.object.modifier_apply(modifier=mod.name)
    for f in low.data.polygons:
        f.use_smooth = True
    material = high.data.materials[0]
    low_mat = material.copy(); low_mat.name = f"{TITLE}_reduced"
    low.data.materials.clear(); low.data.materials.append(low_mat)
    baked = bpy.data.images.new(f"{TITLE}_NormalBaked", MAP_SIZE, MAP_SIZE, alpha=False)
    baked.colorspace_settings.name = "Non-Color"
    target = low_mat.node_tree.nodes.new("ShaderNodeTexImage")
    target.image = baked
    low_mat.node_tree.nodes.active = target
    scene.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"; prefs.get_devices()
    for d in prefs.devices:
        d.use = d.type == "OPTIX"
    scene.cycles.device = "GPU"
    scene.cycles.samples = 1
    size = max(high.dimensions)
    bake = scene.render.bake
    bake.use_selected_to_active = True
    bake.cage_extrusion = BAKE_REACH * size
    bake.max_ray_distance = 3 * BAKE_REACH * size
    bake.margin = 8
    bake.normal_space = "TANGENT"
    bpy.ops.object.select_all(action="DESELECT")
    high.select_set(True); low.select_set(True)
    bpy.context.view_layer.objects.active = low
    bpy.ops.object.bake(type="NORMAL")
    # Saved and loaded back from the file: a generated image's copy (pixels() takes one to scale it) carries no
    # pixels, and the first WarriorF5 map came out black.
    path = os.path.join(ROOT, "build", f"{TITLE}_NormalBaked.png")
    baked.filepath_raw = path
    baked.file_format = "PNG"
    baked.save()
    bpy.data.images.remove(baked)
    baked = bpy.data.images.load(path)
    baked.colorspace_settings.name = "Non-Color"
    # The bake takes the place of the source's normal map on the reduced material (image_of("Normal") finds it there).
    bsdf = next(n for n in low_mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    node = bsdf.inputs["Normal"].links[0].from_node if bsdf.inputs["Normal"].links else None
    while node is not None and node.type != "TEX_IMAGE":
        node = next((i.links[0].from_node for i in node.inputs if i.links), None)
    if node is not None:
        node.image = baked
        low_mat.node_tree.nodes.remove(target)
    else:
        nodes, links = low_mat.node_tree.nodes, low_mat.node_tree.links
        normal_map = nodes.new("ShaderNodeNormalMap")
        links.new(target.outputs["Color"], normal_map.inputs["Color"])
        links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])
    low.name = low.data.name = high.name
    bpy.data.objects.remove(high, do_unlink=True)
    reduced = sum(len(f.vertices) - 2 for f in low.data.polygons)
    print(f"REDUCE {source} -> {reduced} triangles, normals baked at {MAP_SIZE}")
    return low


if not FROM_REDUCED and sum(len(f.vertices) - 2 for f in head.data.polygons) > REDUCE_OVER:
    head = reduce_head(head)
    bpy.context.view_layer.objects.active = head
    head.select_set(True)
    os.makedirs(os.path.dirname(REDUCED), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=REDUCED, relative_remap=False, copy=True)


def close_holes(mesh):
    """The AI's holes in the bust closed (WarriorF came with slits along her lower lids, 83 and 29 vertices round,
    which the eyes' cut took for its own edge), so the cut's hole is its only one; each new face draws the texture its
    neighbours draw at its corners. A bust the AI closed (WarriorM) is as it was. Returns how many faces were made."""
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(mesh)
    uv = bm.loops.layers.uv.active
    made = bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=0)["faces"]
    made_set = set(made)
    for f in made:
        f.smooth = True
        # Each corner's choices: what the faces across the hole's edges at that corner draw there. A hole along a
        # texture seam offers two islands; every corner takes the island most of them lie on (WarriorF3's one hole,
        # on her right upper lid, had one corner given the other island and the face stretched across the map).
        choices = {}
        for loop in f.loops:
            choices[loop] = [l[uv].uv.copy() for e in loop.vert.link_edges for g in e.link_faces
                             if g not in made_set for l in g.loops if l.vert is loop.vert]
        offered = [c for cs in choices.values() for c in cs]
        if not offered:
            continue
        middle = Vector(np.median(np.array([c[:] for c in offered]), axis=0))
        for loop, cs in choices.items():
            if cs:
                loop[uv].uv = min(cs, key=lambda c: (c - middle).length)
    bm.to_mesh(mesh)
    bm.free()
    return len(made)


holes_closed = close_holes(head.data)
print(f"HOLES closed {holes_closed}")
co = np.array([v.co[:] for v in head.data.vertices])
# The face's landmarks on its middle line, seen from the side (face.py; Tripo's front is -Y).
crown, chin, nose_found, chin_found = profile(co)
scale = HEAD_HEIGHT / (crown - chin)
print(f"crown {crown:.4f} chin {chin:.4f} nose {nose_found[2]:.4f} -> scale {scale:.4f}")

head.scale = (scale,) * 3
bpy.ops.object.transform_apply(scale=True)
co = np.array([v.co[:] for v in head.data.vertices])
shift = np.array([-(co[:, 0].max() + co[:, 0].min()) / 2, -(co[:, 1].max() + co[:, 1].min()) / 2, -co[:, 2].min()])
head.location = Vector(shift)
bpy.ops.object.transform_apply(location=True)
head.name = head.data.name = TITLE

# The face's sliders, each a shape key Forge's face editor drives by its part and name ("Nose" "Width": NoseWidth), at
# 100 the most one way and, driven negative, the other. Each pushes the vertices round a landmark (the nose tip, the
# chin's front, in the final frame: metres, front -Y, up Z) by a soft falloff, so nothing near the neck moves.
nose_tip = nose_found * scale + shift
chin_front = chin_found * scale + shift
co = np.array([v.co[:] for v in head.data.vertices])


def falloff(centre, radii):
    """1 at <centre>, 0.14 at its <radii> (an ellipsoid's), nearly 0 past one and a half of them."""
    return np.exp(-2.0 * (((co - centre) / radii) ** 2).sum(1))


def shape(name, moved):
    key = head.shape_key_add(name=name, from_mix=False)
    key.data.foreach_set("co", moved.astype(np.float32).ravel())


head.shape_key_add(name="Basis")
f = falloff(nose_tip + [0, 0.012, -0.004], np.array([0.022, 0.02, 0.02]))
shape("NoseWidth", co + np.c_[co[:, 0] * 0.30 * f, 0 * f, 0 * f])
f = falloff(chin_front + [0, 0.06, 0.025], np.array([0.2, 0.07, 0.035]))
shape("JawWidth", co + np.c_[co[:, 0] * 0.15 * f, 0 * f, 0 * f])
f = falloff(chin_front + [0, 0, 0.012], np.array([0.03, 0.03, 0.025]))
shape("JawChin", co + np.c_[0 * f, -0.012 * f, 0 * f])
print("LANDMARKS nose", nose_tip.round(4), "chin", chin_front.round(4))


def landmark_pictures():
    """checks/landmarks_front.jpg and landmarks_side.jpg: the head flat grey with its crown (red), nose tip (blue) and
    chin's front (green) marked, to see by eye that its size was taken between the right places (a chin found on the
    neck made head_face_1 13% small; eyes set close for a tall head, WarriorF2's, are the face's own, and the eyes'
    check below cannot tell the two apart)."""
    from place import pictures_as_jpeg
    scene = bpy.context.scene
    pictures_as_jpeg(scene)
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "FLAT"
    scene.display.shading.color_type = "MATERIAL"
    crown_z = co[:, 2].max()
    crown_y = co[co[:, 2] > crown_z - 0.01][:, 1].mean()
    marks = []
    for name, at, colour in (("crown", (0.0, crown_y, crown_z), (1, 0, 0, 1)), ("nose", nose_tip, (0, 0, 1, 1)),
                             ("chin", chin_front, (0, 1, 0, 1))):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.005, location=tuple(float(v) for v in at))
        mark = bpy.context.object
        material = bpy.data.materials.new(name + " (mark)")
        material.diffuse_color = colour
        mark.data.materials.append(material)
        marks.append(mark)
    cam = bpy.data.objects.new("landmarks camera", bpy.data.cameras.new("landmarks camera"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = crown_z * 1.15
    centre = Vector((0.0, (co[:, 1].min() + co[:, 1].max()) / 2, crown_z / 2))
    scene.render.resolution_x = scene.render.resolution_y = 900
    for view, direction in (("front", (0, -1, 0)), ("side", (1, 0, 0))):
        d = Vector(direction)
        cam.location = centre + d * 2
        cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = os.path.join(ROOT, "checks", f"landmarks_{view}.jpg")
        bpy.ops.render.render(write_still=True)
    for mark in marks:
        bpy.data.objects.remove(mark)
    bpy.data.objects.remove(cam)
    bpy.context.view_layer.objects.active = head
    head.select_set(True)


landmark_pictures()


CHANNELS = {"Red": 0, "Green": 1, "Blue": 2}


def image_of(label, channel=False):
    """The texture behind the material's socket <label> (Base Color, Normal, Roughness); None when the export has
    none there (WarriorF3's Tripo FBX came with colour and normal maps alone). With channel, also which channel of
    it feeds the socket (a glTF packs roughness in the green of one map, split by a Separate Color node): 0 when
    the image feeds it whole."""
    nodes = head.active_material.node_tree.nodes
    bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
    link = bsdf.inputs[label].links[0] if bsdf.inputs[label].links else None
    node = link.from_node if link else None
    which = 0
    while node is not None and node.type != "TEX_IMAGE":
        if node.type in ("SEPARATE_COLOR", "SEPRGB") and link is not None:
            which = CHANNELS.get(link.from_socket.name, 0)
        link = next((i.links[0] for i in node.inputs if i.links), None)
        node = link.from_node if link is not None else None
    image = node.image if node is not None else None
    return (image, which) if channel else image


def pixels(image, size):
    copy = image.copy()
    copy.scale(size, size)
    array = np.array(copy.pixels[:], dtype=np.float32).reshape(size, size, copy.channels)
    bpy.data.images.remove(copy)
    return array


def save(array, path, fmt, alpha):
    size = array.shape[0]
    image = bpy.data.images.new(os.path.basename(path), size, size, alpha=alpha)
    image.colorspace_settings.name = "Non-Color" if fmt == "PNG" else "sRGB"
    image.pixels = array.ravel()
    image.filepath_raw = path
    image.file_format = fmt
    if fmt == "JPEG":
        bpy.context.scene.render.image_settings.quality = 92
    image.save()


# Eyes of their own (eyes.py): the painted ones opened, eyeballs put in, in a material of their own (<Title>Eyes).
from eyes import give_eyes, eye_pictures
skin = image_of("Base Color")
# <name>/model.json (optional): "lid_rest", how far shut the lids rest (eyes.py rest_lids; WarriorF 0.3).
SPEC = json.load(open(os.path.join(ROOT, "model.json"))) if os.path.exists(os.path.join(ROOT, "model.json")) else {}
eyes = give_eyes(head, skin, TITLE, OUT, os.path.join(ROOT, "checks"), nose_tip, SPEC.get("lid_rest", 0.0))
eye_pictures(head, skin, eyes, os.path.join(ROOT, "checks"))
print("EYES", json.dumps(eyes))
# The size cross-checked by the eyes: their spacing over the chin to the crown is a face's proportion, so a chin found
# in the wrong place (head_face_1's was on the neck: a head 13% small, seated high) stops the build here.
spacing = abs(eyes["right"]["eyeball"]["centre_m"][0] - eyes["left"]["eyeball"]["centre_m"][0])
eyes["spacing_over_height"] = round(spacing / HEAD_HEIGHT, 3)
if not EYES_OVER_HEIGHT[0] <= spacing / HEAD_HEIGHT <= EYES_OVER_HEIGHT[1]:
    raise SystemExit(f"HEAD the eyes are {spacing * 1000:.1f} mm apart on a head {HEAD_HEIGHT * 100:.1f} cm chin to crown "
                     f"({spacing / HEAD_HEIGHT:.3f}, a face's is {EYES_OVER_HEIGHT[0]} to {EYES_OVER_HEIGHT[1]}): its chin "
                     f"or crown was found in the wrong place")

base = pixels(skin, MAP_SIZE)
base[..., 3] = 1.0
save(base, os.path.join(OUT, f"{TITLE}_BaseColor.jpg"), "JPEG", False)
save(pixels(image_of("Normal"), MAP_SIZE), os.path.join(OUT, f"{TITLE}_Normal.png"), "PNG", False)
roughness, rough_channel = image_of("Roughness", channel=True)
rough = pixels(roughness, MAP_SIZE)[..., rough_channel] if roughness is not None else np.full((MAP_SIZE, MAP_SIZE), ROUGHNESS, np.float32)
ms = np.zeros((MAP_SIZE, MAP_SIZE, 4), np.float32)
ms[..., 3] = (1.0 - rough) * SKIN_SHINE
save(ms, os.path.join(OUT, f"{TITLE}_MetallicSmoothness.png"), "PNG", True)

bpy.ops.object.select_all(action="DESELECT")
head.select_set(True)
bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, f"{TITLE}.fbx"), use_selection=True, object_types={"MESH"},
                         apply_unit_scale=True, apply_scale_options="FBX_SCALE_UNITS", axis_forward="-Z", axis_up="Y",
                         bake_space_transform=True, mesh_smooth_type="FACE", add_leaf_bones=False, path_mode="STRIP")
open(os.path.join(OUT, "CREDITS.md"), "w").write(
    f"# {TITLE}\n\nGenerated by Tripo AI (tripo3d.ai) from Iris's reference sheet, on Moti's Tripo Pro plan (private models, "
    "commercial use).\nScaled and exported by blender-tests/ai_models/head.py (Moti + Claude).\n")
co = np.array([v.co[:] for v in head.data.vertices])
report = {"chin_to_crown": HEAD_HEIGHT, "scale": round(float(scale), 4), "holes_closed": holes_closed,
          "size_m": [round(float(d), 3) for d in co.max(0) - co.min(0)],
          "triangles": sum(len(p.vertices) - 2 for p in head.data.polygons),
          "nose_tip": [round(float(c), 4) for c in nose_tip], "chin_front": [round(float(c), 4) for c in chin_front],
          "shapes": [k.name for k in head.data.shape_keys.key_blocks[1:]], "eyes": eyes}
json.dump(report, open(os.path.join(ROOT, "checks", "head.json"), "w"), indent=2)
print("REPORT", report)
