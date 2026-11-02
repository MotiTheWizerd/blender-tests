"""Fit the Hunyuan3D pommel (made by Moti on the web from our crop) onto the Viking sword."""
import bpy, bmesh
from mathutils import Matrix, Vector
D = bpy.data
src = D.scenes["ai_test"].objects["hy3d_model"]
vk = D.scenes["viking"]; SW = D.collections["VikingSword"]

# the code-built ravens step aside, kept in their own (excluded) collection
old = D.collections.get("ravens_from_code") or D.collections.new("ravens_from_code")
if old.name not in [c.name for c in vk.collection.children]:
    vk.collection.children.link(old)
for o in list(SW.objects):
    if o.name.startswith(("Ravens", "beak", "raven_eye")):
        SW.objects.unlink(o)
        if o.name not in old.objects:
            old.objects.link(o)
for lc in vk.view_layers[0].layer_collection.children:
    if lc.collection == old:
        lc.exclude = True
prev = D.objects.get("Pommel_AI")
if prev:
    D.objects.remove(prev, do_unlink=True)

me = src.data.copy(); me.name = "Pommel_AI"
bm = bmesh.new(); bm.from_mesh(me)
bm.transform(src.matrix_world)
CUT = 0.6                                   # above this sit the AI's own band and cap
bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, CUT), plane_no=(0, 0, 1), clear_outer=True)
S = 0.117 / 1.96                            # its wingspan becomes the reference pommel's 11.7 cm
GZ1 = -0.176                                # bottom of the grip; our lower band ends 1.8 cm below
top_z = GZ1 - 0.018 + 0.004                 # tuck the open top 4 mm up into our band
bm.transform(Matrix.Translation((0.02 * S, -0.03 * S, top_z)) @ Matrix.Scale(S, 4) @ Matrix.Translation((0, 0, -CUT)))
bm.to_mesh(me); bm.free()
for p in me.polygons:
    p.use_smooth = True
me.materials.clear(); me.materials.append(D.materials["RavenBronze"])
SW.objects.link(D.objects.new("Pommel_AI", me))
print("fitted:", len(me.polygons), "faces")
