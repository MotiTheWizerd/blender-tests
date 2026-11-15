"""The step after reduce for a character Tripo rigged (model.json "rig": "tripo"), in place of Mixamo's.

    blender -b --factory-startup -P tripo_rig.py -- body_warrior_f

Tripo can rig a humanoid on Mixamo's skeleton itself (its bones named "mixamorig:Hips" and so on, weighed on its full
mesh), so the model needs no trip to mixamo.com. Reads <name>/source_tripo.fbx (the rigged export; its maps in
source_tripo.fbm) and build/<name>_low.blend (reduce's mesh). Stands both model.json's "height" tall (metres), feet
on the ground at the origin, centred, the transforms applied (as mixamo.py stands a model for Mixamo), weighs the
reduced mesh from the full one (each vertex from the nearest face's, interpolated, at most 4 bones, summing to 1) and
binds it to the skeleton.

Writes build/<name>_rigged.fbx (the skeleton and the reduced mesh, skinned, no clip: what pieces.py reads in place of
Mixamo's download) and checks/tripo_rig.json (bones, weights, the size) and tripo_rig_pose_<view>.jpg: the mesh bent
(an arm raised, an elbow, a knee, the spine and the head turned) to see that the skin follows its bones.
"""
import bpy, json, math, os, sys
from mathutils import Euler, Matrix, Vector

NAME = sys.argv[sys.argv.index("--") + 1]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from place import Creature, pictures_as_jpeg
C = Creature(NAME)
HEIGHT = float(C.spec.get("height", 1.75))
BONES_PER_VERTEX = 4          # as Unity skins by default

bpy.ops.wm.open_mainfile(filepath=C.blend("low"))
scene = bpy.context.scene
low = next(o for o in scene.objects if o.type == "MESH")
for o in list(scene.objects):
    if o is not low:
        bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.import_scene.fbx(filepath=os.path.abspath(os.path.join(C.root, "source_tripo.fbx")))
rig = next(o for o in scene.objects if o.type == "ARMATURE")
high = next(o for o in scene.objects if o.type == "MESH" and o is not low)
for action in list(bpy.data.actions):
    bpy.data.actions.remove(action)
rig.animation_data_clear()

# Where the full mesh stands decides the size and place, for all three alike: reduce's mesh came from the same model
# (its glTF, the same frame), so it lies on the full one.
points = [high.matrix_world @ v.co for v in high.data.vertices]
lo = Vector([min(p[i] for p in points) for i in range(3)])
hi = Vector([max(p[i] for p in points) for i in range(3)])
scale = HEIGHT / (hi.z - lo.z)
stand = Matrix.Diagonal((scale, scale, scale, 1.0)) @ Matrix.Translation(-Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z)))
low_points = [low.matrix_world @ v.co for v in low.data.vertices]
low_off_mm = 1000 * max(abs(min(p[i] for p in low_points) - lo[i]) + abs(max(p[i] for p in low_points) - hi[i])
                        for i in range(3))

# Transforms applied: each mesh's vertices and the skeleton's bones in the world's frame, every object at identity.
for ob in (high, low):
    ob.data.transform(stand @ ob.matrix_world)
    ob.parent = None
    ob.matrix_world = Matrix.Identity(4)
rig.data.transform(stand @ rig.matrix_world)
rig.matrix_world = Matrix.Identity(4)

# The reduced mesh weighed from the full one: each vertex the weights at the nearest point of the full mesh's faces.
low.vertex_groups.clear()
transfer = low.modifiers.new("weights", "DATA_TRANSFER")
transfer.object = high
transfer.use_vert_data = True
transfer.data_types_verts = {"VGROUP_WEIGHTS"}
transfer.vert_mapping = "POLYINTERP_NEAREST"
transfer.layers_vgroup_select_src = "ALL"
transfer.layers_vgroup_select_dst = "NAME"
bpy.context.view_layer.objects.active = low
bpy.ops.object.datalayout_transfer(modifier=transfer.name)
bpy.ops.object.modifier_apply(modifier=transfer.name)
bpy.ops.object.vertex_group_limit_total(group_select_mode="ALL", limit=BONES_PER_VERTEX)
bpy.ops.object.vertex_group_normalize_all(group_select_mode="ALL", lock_active=False)
bones = {b.name for b in rig.data.bones}
for group in [g for g in low.vertex_groups if g.name not in bones]:
    low.vertex_groups.remove(group)
unweighed = sum(1 for v in low.data.vertices if not any(g.weight > 0 for g in v.groups))
if unweighed:
    raise SystemExit(f"TRIPO_RIG {unweighed} vertices of the reduced mesh have no bone")
bpy.data.objects.remove(high, do_unlink=True)

low.parent = rig
low.modifiers.new("skeleton", "ARMATURE").object = rig
report = {"height_m": HEIGHT, "scale": round(scale, 5), "bones": len(rig.data.bones),
          "deforming_bones_weighed": len(low.vertex_groups), "vertices": len(low.data.vertices),
          "triangles": len(low.data.polygons), "low_off_high_mm": round(low_off_mm, 3)}
if low_off_mm > 5:
    raise SystemExit(f"TRIPO_RIG reduce's mesh lies {low_off_mm:.1f} mm off the rigged one: not the same model")

bpy.ops.object.select_all(action="DESELECT")
rig.select_set(True); low.select_set(True)
bpy.ops.export_scene.fbx(filepath=C.build(f"{NAME}_rigged.fbx"), use_selection=True, object_types={"ARMATURE", "MESH"},
                         apply_unit_scale=True, apply_scale_options="FBX_SCALE_ALL", add_leaf_bones=False,
                         bake_anim=False, mesh_smooth_type="FACE", path_mode="STRIP")
json.dump(report, open(C.checks("tripo_rig.json"), "w"), indent=1)

# The skin bent with its bones: the left arm raised and its elbow bent, the right knee up, the spine and head turned.
# Each about the bone's own axes, as an animation turns it.
pose = {"LeftArm": (0, 0, 60), "LeftForeArm": (0, 0, 70), "RightUpLeg": (-60, 0, 0), "RightLeg": (90, 0, 0),
        "Spine1": (10, 15, 0), "Head": (0, 30, 0)}
prefix = next(b.name for b in rig.data.bones if b.name.endswith("Hips"))[:-len("Hips")]
for name, angles in pose.items():
    bone = rig.pose.bones[prefix + name]
    bone.rotation_mode = "XYZ"
    bone.rotation_euler = Euler([math.radians(a) for a in angles])
for material in low.data.materials:          # Workbench shows a material's active image: its colour, not reduce's normals
    tree = material.node_tree
    tree.nodes.active = next(link.from_node for link in tree.links if link.to_socket.name == "Base Color"
                             and link.from_node.type == "TEX_IMAGE")
pictures_as_jpeg(scene)
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"; scene.display.shading.color_type = "TEXTURE"
scene.render.resolution_x, scene.render.resolution_y = 800, 1000
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam); scene.camera = cam
cam.data.type = "ORTHO"; cam.data.ortho_scale = HEIGHT * 1.15
for view, d in {"front": (0, -1, 0), "three_quarter": (0.7, -0.7, 0), "side": (1, 0, 0)}.items():
    d = Vector(d).normalized()
    cam.location = Vector((0, 0, HEIGHT / 2)) + d * 5
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = C.picture(f"tripo_rig_pose_{view}")
    bpy.ops.render.render(write_still=True)
print("TRIPO_RIG", json.dumps(report))
