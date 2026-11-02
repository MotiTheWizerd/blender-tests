"""Fit the AI dragon head (Hunyuan3D v2.5 via Siray, brokkr s968) onto the Viking sword's guard.

source/ai3d/dragon_head_hunyuan.glb was made from source/crops/dragon_head.png with the blade
painted out. It is ONE head, its neck curling down into a slice of the grip's gold band. The
guard in the reference (crops/guard.png) is two of them, mirrored, their necks meeting over
the band. So: drop the AI's band, cut the neck flat where the crop ended, mirror, and scale
by the reference: band 205 px wide, beak tip 348 px from the centre -> 0.088 m on our 52 mm band.
"""
import bpy, bmesh
from mathutils import Matrix, Vector

D = bpy.data
GLB = bpy.path.abspath("//source/ai3d/dragon_head_hunyuan.glb")
vk = D.scenes["viking"]; SW = D.collections["VikingSword"]; ai = D.scenes["ai_test"]

# ---- the AI head, imported once into ai_test ----
src = ai.objects.get("hy3d_dragon")
if src is None:
    win = bpy.context.window_manager.windows[0]
    win.scene = ai
    before = set(ai.objects)
    with bpy.context.temp_override(window=win, scene=ai):
        bpy.ops.import_scene.gltf(filepath=GLB)
    src = next(o for o in ai.objects if o not in before and o.type == "MESH")
    src.name = "hy3d_dragon"
    win.scene = vk

# ---- the code-built guard steps aside, kept in its own (excluded) collection ----
old = D.collections.get("guard_from_code") or D.collections.new("guard_from_code")
if old.name not in [c.name for c in vk.collection.children]:
    vk.collection.children.link(old)
for o in list(SW.objects):
    if o.name.split(".")[0] in ("Guard", "eye", "teeth", "throat", "horns"):
        SW.objects.unlink(o)
        if o.name not in old.objects:
            old.objects.link(o)
for lc in vk.view_layers[0].layer_collection.children:
    if lc.collection == old:
        lc.exclude = True
prev = D.objects.get("Guard_AI")
if prev:
    D.objects.remove(prev, do_unlink=True)

# ---- one half: the head, without its band ----
me = src.data.copy(); me.name = "Guard_AI"
bm = bmesh.new(); bm.from_mesh(me)
bm.transform(src.matrix_world)
xs = [v.co.x for v in bm.verts]; zs = [v.co.z for v in bm.verts]
x0, x1, z0, z1 = min(xs), max(xs), min(zs), max(zs)
# In the crop the band is the bottom-left corner: x < 0.23 of the width, under 0.195 of the
# height (its top at y=595 of 160..700 px). The open jaw dips lower but sits far right of it.
BAND_X = x0 + 0.23 * (x1 - x0)
NECK_Z = z0 + 0.195 * (z1 - z0)
bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.x < BAND_X and v.co.z < NECK_Z], context="VERTS")
# the crop's left edge left a flat stump; cut clean a little inside it, the mirror closes it
XM = x0 + 0.012 * (x1 - x0)
bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(XM, 0, 0), plane_no=(1, 0, 0), clear_inner=True)
yc = sum(v.co.y for v in bm.verts) / len(bm.verts)
S = 0.088 / (x1 - XM)
BAND_TOP = -0.012                           # BandTop's upper rim
bm.transform(Matrix.Translation((0, 0, BAND_TOP - 0.003)) @ Matrix.Scale(S, 4) @ Matrix.Translation((-XM, -yc, -NECK_Z)))

# ---- the other half: mirrored across x = 0, faces turned back outward ----
other = bmesh.new()
tmp = D.meshes.new("tmp"); bm.to_mesh(tmp); other.from_mesh(tmp); D.meshes.remove(tmp)
other.transform(Matrix.Scale(-1, 4, (1, 0, 0)))
bmesh.ops.reverse_faces(other, faces=other.faces[:], flip_multires=False)
tmp = D.meshes.new("tmp"); other.to_mesh(tmp); other.free()
bm.from_mesh(tmp); D.meshes.remove(tmp)
bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=0.0002)
bm.to_mesh(me); bm.free()
for p in me.polygons:
    p.use_smooth = True
SW.objects.link(D.objects.new("Guard_AI", me))
xs = [v.co.x for v in me.vertices]; zs = [v.co.z for v in me.vertices]
print(f"fitted: {len(me.polygons)} faces, x {min(xs):.4f}..{max(xs):.4f}, z {min(zs):.4f}..{max(zs):.4f}, scale {S:.4f}")
