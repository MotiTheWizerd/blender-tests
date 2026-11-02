"""Step 6: colliders and LODs, packaged the way Unity's importer understands.

FBX hierarchy (pivot = centre of the grip, at the root):
  Sword                 empty root
    Sword_LOD0          the full game sword            (1,462 tris)
    Sword_LOD1          decimated, for mid distance
    Sword_LOD2          decimated hard, for far away
    Blade_COL           convex hull around the blade   (physics only, never drawn)
    Hilt_COL            convex hull around guard, grip and pommel
Unity builds a LOD Group by itself from the _LOD0/_LOD1/_LOD2 names.
The _COL meshes get turned into convex MeshColliders by SwordImportSetup.cs (Assets/Editor).
"""
import bpy, bmesh, os

D = bpy.data
OUT = "/mnt/fast/apps/blender-play/export"
sc = D.scenes["sword"]; vl = sc.view_layers[0]

lod0 = sc.objects.get("Sword_LOD0") or sc.objects["Sword"]
lod0.name = "Sword_LOD0"
lod0.data.name = "Sword_LOD0"

for name in ("Sword_LOD1", "Sword_LOD2", "Blade_COL", "Hilt_COL", "Sword"):
    o = sc.objects.get(name)
    if o and o != lod0:
        D.objects.remove(o, do_unlink=True)

root = D.objects.new("Sword", None)
sc.collection.objects.link(root)
root.empty_display_size = 0.1
lod0.parent = root


def tris(ob):
    ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    return sum(len(p.vertices) - 2 for p in ev.data.polygons)


# ---------------- LODs: same UVs, same material, fewer triangles ----------------
for name, ratio in (("Sword_LOD1", 0.5), ("Sword_LOD2", 0.2)):
    o = lod0.copy(); o.data = lod0.data.copy(); o.name = name; o.data.name = name
    sc.collection.objects.link(o)
    dec = o.modifiers.new("decimate", "DECIMATE")
    dec.decimate_type = "COLLAPSE"; dec.ratio = ratio; dec.use_collapse_triangulate = True
    o.parent = root
    o.hide_set(True, view_layer=vl)                 # in Blender we look at LOD0; Unity switches them


# ---------------- colliders: convex hulls from a handful of points ----------------
col_mat = D.materials.get("Collider") or D.materials.new("Collider")
col_mat.diffuse_color = (0.1, 0.9, 0.3, 0.35)


def hull(name, pts):
    bm = bmesh.new()
    for p in pts:
        bm.verts.new(p)
    bmesh.ops.convex_hull(bm, input=bm.verts)
    me = D.meshes.new(name)
    bm.to_mesh(me); bm.free()
    me.materials.append(col_mat)
    o = D.objects.new(name, me)
    sc.collection.objects.link(o)
    o.parent = root
    o.display_type = "WIRE"
    o.hide_render = True
    return o


s = [(x, y) for x in (-1, 1) for y in (-1, 1)]
blade = hull("Blade_COL",
             [(0.031 * x, 0.0068 * y, 0.115) for x, y in s] +
             [(0.026 * x, 0.0055 * y, 0.86) for x, y in s] +
             [(0, 0, 1.0)])
hilt = hull("Hilt_COL",
            [(0.117 * x, 0.018 * y, 0.092) for x, y in s] +
            [(0.117 * x, 0.018 * y, 0.142) for x, y in s] +
            [(0.027 * x, 0.021 * y, -0.152) for x, y in s])

# ---------------- export the whole hierarchy ----------------
for o in sc.objects:
    o.select_set(o in (root, lod0, blade, hilt) or o.name.startswith("Sword_LOD"), view_layer=vl)
for o in (sc.objects["Sword_LOD1"], sc.objects["Sword_LOD2"]):
    o.hide_set(False, view_layer=vl); o.select_set(True, view_layer=vl)
path = os.path.join(OUT, "Sword.fbx")
bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={"EMPTY", "MESH"},
                         apply_unit_scale=True, apply_scale_options="FBX_SCALE_UNITS",
                         axis_forward="-Z", axis_up="Y", bake_space_transform=True,
                         use_mesh_modifiers=True, mesh_smooth_type="FACE", add_leaf_bones=False,
                         path_mode="COPY", embed_textures=True)
for o in (sc.objects["Sword_LOD1"], sc.objects["Sword_LOD2"]):
    o.hide_set(True, view_layer=vl)
for o in sc.objects:
    o.select_set(False, view_layer=vl)
bpy.ops.wm.save_mainfile()
print({o.name: tris(o) for o in (lod0, sc.objects["Sword_LOD1"], sc.objects["Sword_LOD2"], blade, hilt)})
