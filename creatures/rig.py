"""Step 3 for a creature: a skeleton from its landmarks, skinned with automatic weights, then bent to be looked at.

    blender -b --factory-startup -P rig.py -- dragon

Reads <name>/<name>_low.blend (step 2) and <name>/landmarks.json: named chains of joints in the source frame, the
paired ones (".L", the creature's left, +X) mirrored to ".R" when "mirror" is set, and each chain's parent ("spine" is
its last bone, "spine:0" its first). Bones are "<chain>_<i>" ("tail_3", "finger1_2.L"), each chain connected, rolled so
its X axis is level (a bend about X lifts and lowers).

Finding the landmarks is the judgment in this step (the dragon's were read off grid views and mesh slices: see
RECIPE.md); the rest is mechanical. Writes <name>/<name>_rig.blend, rig.json (bones, vertices no bone moves), and
pictures: rig_<view>.png (the bones drawn through the body) and bend_<view>.png (wings folded up, neck and tail turned,
a front leg lifted) to look at for tearing. The chains listed in "feet" stand on the ground: their last bone is held
by an unparented twin ("ik_<bone>") that the leg reaches by IK, so the body moves over planted feet.
"""
import bpy, json, math, os, sys
from mathutils import Vector, Matrix

NAME = sys.argv[sys.argv.index("--") + 1]
HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), NAME)
bpy.ops.wm.open_mainfile(filepath=os.path.join(HERE, f"{NAME}_low.blend"))
scene = bpy.context.scene
body = next(o for o in scene.objects if o.type == "MESH")
spec = json.load(open(os.path.join(HERE, "landmarks.json")))

chains, parents = dict(spec["chains"]), dict(spec["parents"])
if spec.get("mirror"):
    for name in [n for n in chains if n.endswith(".L")]:
        twin = name[:-2] + ".R"
        chains[twin] = [[-p[0], p[1], p[2]] for p in chains[name]]
        parent = parents[name]
        parents[twin] = parent[:-2] + ".R" if parent and parent.endswith(".L") else parent


def bone_name(chain, i):
    base, _, side = chain.partition(".")
    return f"{base}_{i}" + (f".{side}" if side else "")


arm_data = bpy.data.armatures.new(NAME + "_Rig")
rig = bpy.data.objects.new(NAME.capitalize() + "_Rig", arm_data)
scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="EDIT")
edit = arm_data.edit_bones
for chain in chains:            # every bone first, then the chains hung on their parents
    points = [Vector(p) for p in chains[chain]]
    previous = None
    for i in range(len(points) - 1):
        b = edit.new(bone_name(chain, i))
        b.head, b.tail = points[i], points[i + 1]
        b.align_roll(Vector((0, 0, 1)) if abs((b.tail - b.head).normalized().z) < 0.9 else Vector((0, -1, 0)))
        if previous:
            b.parent, b.use_connect = previous, True
        previous = b
for chain in chains:
    parent = parents[chain]
    if parent:
        owner, _, index = parent.partition(":")
        count = len(chains[owner]) - 1
        edit[bone_name(chain, 0)].parent = edit[bone_name(owner, int(index) if index else count - 1)]

# Planted feet: each foot chain's last bone (the foot on the ground) gets a twin, "ik_<bone>", parented to nothing,
# so it stays where it stands; the leg reaches it by IK and the foot keeps its turn. The body can then breathe, bob
# or turn while the feet hold the ground (a leg hung on the spine otherwise rides along and the creature floats).
feet = list(spec.get("feet", []))
if spec.get("mirror"):
    feet += [f[:-2] + ".R" for f in feet if f.endswith(".L")]
for chain in feet:
    foot = edit[bone_name(chain, len(chains[chain]) - 2)]
    ik = edit.new("ik_" + foot.name)
    ik.head, ik.tail, ik.roll = foot.head, foot.tail, foot.roll
    ik.use_deform = False
bpy.ops.object.mode_set(mode="OBJECT")
for chain in feet:
    n = len(chains[chain]) - 1                       # bones in the chain; the last is the foot
    foot = bone_name(chain, n - 1)
    reach = rig.pose.bones[bone_name(chain, n - 2)].constraints.new("IK")
    reach.target, reach.subtarget, reach.chain_count = rig, "ik_" + foot, n - 1
    hold = rig.pose.bones[foot].constraints.new("COPY_ROTATION")
    hold.target, hold.subtarget = rig, "ik_" + foot

# Automatic (heat) weights.
bpy.ops.object.select_all(action="DESELECT")
body.select_set(True); rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.parent_set(type="ARMATURE_AUTO")
# Feet are rigid: the skin below a planted foot's ankle (its bone's head), near the foot, goes to the foot alone.
# Shared with the lower leg, a sole slides whenever the leg bends over it, and the planted foot looks to skate.
for chain in feet:
    foot = arm_data.bones[bone_name(chain, len(chains[chain]) - 2)]
    ankle, toe = foot.head_local, foot.tail_local
    group = body.vertex_groups[foot.name]
    reach = max(body.dimensions) * 0.07
    for v in body.data.vertices:
        if v.co.z > ankle.z:
            continue
        flat, a, b = v.co.xy, ankle.xy, toe.xy
        t = max(0.0, min(1.0, (flat - a).dot(b - a) / max((b - a).length_squared, 1e-9)))
        if (flat - (a + (b - a) * t)).length > reach:
            continue
        for g in list(v.groups):
            body.vertex_groups[g.group].remove([v.index])
        group.add([v.index], 1.0, "REPLACE")

groups = {g.index for g in body.vertex_groups}
unweighted = sum(1 for v in body.data.vertices if not any(g.group in groups and g.weight > 1e-4 for g in v.groups))
report = {"bones": len(arm_data.bones), "vertices": len(body.data.vertices), "unweighted": unweighted}
print("RIG", json.dumps(report))
json.dump(report, open(os.path.join(HERE, "rig.json"), "w"), indent=1)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, f"{NAME}_rig.blend"))

# Pictures. Workbench draws no armature, so the bones are drawn as sticks, the body see-through.
scene.render.engine = "BLENDER_WORKBENCH"
shading = scene.display.shading
shading.light = "STUDIO"
scene.render.resolution_x, scene.render.resolution_y = 1400, 1000
scene.world = bpy.data.worlds.new("w")
size = max(body.dimensions)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam); scene.camera = cam
cam.data.type = "ORTHO"; cam.data.ortho_scale = size * 1.2; cam.data.clip_end = size * 10
centre = Vector((0, 0, body.dimensions.z / 2))
views = {"front": (0, -1, 0), "side": (1, 0, 0), "top": (0, -0.001, 1), "three_quarter": (0.8, -1, 0.45)}


def shoot(prefix):
    for view, d in views.items():
        d = Vector(d).normalized()
        cam.location = centre + d * size * 3
        cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = os.path.join(HERE, f"{prefix}_{view}.png")
        bpy.ops.render.render(write_still=True)


stick = bpy.data.materials.new("stick"); stick.diffuse_color = (1, 0.15, 0.05, 1)
sticks = []
for b in arm_data.bones:
    h, t = rig.matrix_world @ b.head_local, rig.matrix_world @ b.tail_local
    bpy.ops.mesh.primitive_cylinder_add(radius=size * 0.004, depth=(t - h).length, location=(h + t) / 2)
    c = bpy.context.object
    c.rotation_euler = (t - h).to_track_quat("Z", "Y").to_euler()
    bpy.ops.mesh.primitive_uv_sphere_add(radius=size * 0.008, location=h)
    sticks += [c, bpy.context.object]
for s in sticks:
    s.data.materials.append(stick)
shading.color_type = "MATERIAL"
shading.show_xray = True; shading.xray_alpha = 0.35
shoot("rig")
for s in sticks:
    bpy.data.objects.remove(s, do_unlink=True)

# Bent: each chain turned about its bones' level X axis (or Z, sideways), spread along the chain.
shading.show_xray = False; shading.color_type = "TEXTURE"
pose = rig.pose.bones
def turn(chain, axis, degrees):
    base, _, side = chain.partition(".")
    bones = [p for p in pose if p.name.startswith(base + "_") and (not side or p.name.endswith("." + side))]
    for p in bones:
        p.rotation_mode = "XYZ"
        r = list(p.rotation_euler); r["XYZ".index(axis)] += math.radians(degrees) / len(bones); p.rotation_euler = r
for side, sign in (("L", 1), ("R", -1)):
    turn("wing." + side, "Y", 40 * sign)
    turn("finger1." + side, "X", 30)
turn("neck", "Z", 50)
turn("tail", "Z", -70)
bpy.context.view_layer.update()
# A front foot lifted: its planted target raised, the leg bending up to it.
lift = pose["ik_" + bone_name("arm.L", len(chains["arm.L"]) - 2)]
m = lift.matrix.copy(); m.translation.z += size * 0.1; m.translation.y -= size * 0.05; lift.matrix = m
bpy.context.view_layer.update()
shoot("bend")
