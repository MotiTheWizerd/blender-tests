"""Re-pack the sword's UVs for a tall texture (width:height = 1:ASPECT).
In a 1:4 texture one UV unit across is 4x fewer pixels than one unit up, so islands
are made 4x wider in UV space before packing; pixels on the sword stay square."""
import bpy
ASPECT = float(globals().get("ASPECT", 4))
sc = bpy.data.scenes["sword"]; ob = sc.objects["Sword"]; vl = sc.view_layers[0]
ob.select_set(True, view_layer=vl); vl.objects.active = ob
win = bpy.context.window_manager.windows[0]
area = next(a for a in win.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
ov = dict(window=win, area=area, region=region, scene=sc, view_layer=vl, active_object=ob, object=ob, selected_objects=[ob])

def pack(**kw):
    with bpy.context.temp_override(**ov):
        bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT"); bpy.ops.uv.select_all(action="SELECT")
        bpy.ops.uv.pack_islands(shape_method="CONCAVE", margin=0.004, **kw)
        bpy.ops.object.mode_set(mode="OBJECT")

def coverage():
    uv = ob.data.uv_layers.active.data; tot = 0
    for p in ob.data.polygons:
        pts = [uv[li].uv for li in p.loop_indices]
        tot += abs(sum(pts[i].x * pts[(i+1) % len(pts)].y - pts[(i+1) % len(pts)].x * pts[i].y for i in range(len(pts)))) / 2
    return tot

with bpy.context.temp_override(**ov):                     # start from a clean unwrap every time
    bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.unwrap(method="CONFORMAL", margin=0.004)
    bpy.ops.uv.select_all(action="SELECT"); bpy.ops.uv.average_islands_scale()
    bpy.ops.object.mode_set(mode="OBJECT")
pack(rotate=True, rotate_method="AXIS_ALIGNED_Y")        # stand every island upright first
uv = ob.data.uv_layers.active.data
for d in uv:
    d.uv.x *= ASPECT
pack(rotate=False)                                      # rotating a stretched island would skew it
ob.select_set(False)
print(f"aspect 1:{ASPECT:g} coverage {coverage():.3f}")
