"""Step 6 for a creature: its animations, written as motion on its skeleton (no hand keys), so the next creature with
the same chains gets them too.

    blender -b --factory-startup -P animate.py -- dragon

Reads <name>/<name>_rig.blend (step 3). Each clip is an action keyed on every frame from curves of time; every loop
ends where it began. The rest pose is the legs' full reach (its feet are planted by IK, step 3), so the body only
ever moves DOWN from it and back: a chest that rose past rest would pull the feet off the ground. A motion is a turn
about an axis of the creature's own frame (X across, Y front to back, Z up),
added on top of the bone's parent, so a wing's beat reads the same on both sides with the sign mirrored.
Writes <name>/<name>_anim.blend (the clips as actions, Idle playing, the frame range set) and, for each clip,
anim_<clip>.png: frames across one loop, side by side, to look at.

Clips:
  Idle      4 s loop. Breathing (the chest rises and the neck answers), the head swaying slowly, the tail moving
            in a wave from root to tip, the wings breathing with the chest.
  WingFlap  1 s loop. The wings beat from the shoulder (35 deg up and down), the arms and fingers lagging behind so
            the membrane trails, the body bobbing against the beat, the tail balancing.
  Walk      1.6 s loop, in place (the game moves the creature: anim.json gives the speed its feet carry, so they
            don't skate). A lateral-sequence walk, left hind, left fore, right hind, right fore a quarter apart, each
            foot 70% on the ground sliding back under the body and 30% swinging forward with a lift. The body is
            lowered 5.5% of its height for the whole walk, so the near-straight forelegs have the slack to stride
            (they would otherwise fall short of their feet), dips with the steps, sways; the neck turns against the
            hips so the head stays steady, the tail swings behind, the wings fold down a little.

Checks (anim.json): `feet_moved_per_metre` for clips that stand (the skin on the ground must not move), and
`reach_miss_per_metre` for all (how far a leg falls short of its foot's target: a foot left floating).
"""
import bpy, json, math, os, sys
import numpy as np
from mathutils import Quaternion, Vector

NAME = sys.argv[sys.argv.index("--") + 1]
HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), NAME)
FPS = 30
bpy.ops.wm.open_mainfile(filepath=os.path.join(HERE, f"{NAME}_rig.blend"))
scene = bpy.context.scene
scene.render.fps = FPS
rig = next(o for o in scene.objects if o.type == "ARMATURE")
body = next(o for o in scene.objects if o.type == "MESH")
pose = rig.pose.bones
X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))


def chain(base, side=""):
    """The bones of a chain, root first ("tail" -> tail_0 .. tail_9)."""
    found = [p for p in pose if p.name.startswith(base + "_") and (p.name.endswith("." + side) if side else "." not in p.name)]
    return sorted(found, key=lambda p: int(p.name[len(base) + 1:].split(".")[0]))


def turn(bone, axis, degrees):
    """Add a turn about `axis` (the creature's frame) to `bone`, on top of what it already has this frame."""
    rest = bone.bone.matrix_local.to_quaternion()
    local = rest.inverted() @ Quaternion(axis, math.radians(degrees)) @ rest
    bone.rotation_quaternion = local @ bone.rotation_quaternion


def shift(bone, delta):
    """Add a move by `delta` (the creature's frame) to an unparented bone (the root, a foot's target)."""
    bone.location = bone.location + bone.bone.matrix_local.to_3x3().inverted() @ Vector(delta)


SIDES = (("L", 1), ("R", -1))       # the left wing is on +X: raising it is a turn of -angle about Y
HEIGHT = body.dimensions.z
LENGTH = body.dimensions.y


def idle(t):
    w = 2 * math.pi * t
    breath = math.sin(w)
    sink = (1 + breath) / 2                              # 0 at rest .. 1: the chest only sinks from rest (DOWN)
    spine = chain("spine")
    turn(spine[1], X, 1.2 * sink)                         # +X tips a bone pointing forward down
    turn(spine[2], X, 1.5 * sink)
    for i, b in enumerate(chain("neck")):
        turn(b, X, -0.8 * sink)
        turn(b, Z, 2.0 * math.sin(w - 0.6))
    turn(chain("head")[0], Z, 2.5 * math.sin(w - 1.0))
    for i, b in enumerate(chain("tail")):
        turn(b, Z, (1.5 + 0.5 * i) * math.sin(w - 0.45 * i))
        turn(b, X, 0.6 * math.sin(w - 0.45 * i + 1.0))
    for side, s in SIDES:
        turn(chain("wing", side)[0], Y, -s * 2.5 * breath)
        for f in ("finger1", "finger2", "finger3"):
            turn(chain(f, side)[0], Y, -s * 1.5 * math.sin(w - 0.5))


def wing_flap(t):
    w = 2 * math.pi * t
    for side, s in SIDES:
        up = lambda deg, lag=0.0: -s * deg * math.cos(w - lag)
        wing = chain("wing", side)
        turn(wing[0], Y, up(35))
        turn(wing[1], Y, up(10, 0.6))
        for f, lag in (("finger1", 0.9), ("finger2", 1.1), ("finger3", 1.3)):
            bones = chain(f, side)
            turn(bones[0], Y, up(8, lag))
            for b in bones[1:]:
                turn(b, Y, up(5, lag + 0.3))
    spine = chain("spine")
    dip = (1 - math.cos(w)) / 2                          # 0 with the wings up .. 1 with them down: DOWN only
    turn(spine[0], X, 3.0 * dip)                          # the chest sinks on the downstroke, back up with the wings
    for b in chain("neck"):
        turn(b, X, -1.2 * dip)
    for i, b in enumerate(chain("tail")):
        turn(b, X, (0.8 + 0.3 * i) * math.sin(w - 0.4 * i))


STRIDE = 0.13 * HEIGHT        # how far a foot goes either side of where it stands
LIFT = 0.07 * HEIGHT          # how high a swinging foot rises
STANCE = 0.7                  # the share of the cycle a foot is on the ground
WALK_SECONDS = 1.6
# The order a lateral-sequence walk sets its feet down: (chain, side) -> phase in the cycle.
GAIT = {("leg", "L"): 0.0, ("arm", "L"): 0.25, ("leg", "R"): 0.5, ("arm", "R"): 0.75}


def walk(t):
    w = 2 * math.pi * t
    for (limb, side), phase in GAIT.items():
        target = next(p for p in pose if p.name.startswith(f"ik_{limb}_") and p.name.endswith("." + side))
        p = (t - phase) % 1.0
        if p < STANCE:                                   # on the ground, sliding back under the body
            y, z = -STRIDE + 2 * STRIDE * p / STANCE, 0.0
        else:                                            # swinging forward, lifted
            q = (p - STANCE) / (1 - STANCE)
            ease = q * q * (3 - 2 * q)
            y, z = STRIDE - 2 * STRIDE * ease, LIFT * math.sin(math.pi * q)
        shift(target, (0, y, z))                         # the creature faces -Y: forward is -Y
    spine = chain("spine")
    dip = 0.012 * HEIGHT * (1 - math.cos(2 * w)) / 2     # twice a cycle, down only
    shift(spine[0], (0.012 * HEIGHT * math.sin(w), 0, -0.055 * HEIGHT - dip))
    turn(spine[0], Z, 2.5 * math.sin(w))
    turn(spine[2], Z, -2.0 * math.sin(w))
    for b in chain("neck"):
        turn(b, Z, -0.8 * math.sin(w))
    turn(chain("head")[0], Z, -0.5 * math.sin(w))
    for i, b in enumerate(chain("tail")):
        turn(b, Z, (3.0 + 0.8 * i) * math.sin(w - 0.5 - 0.35 * i))
    for side, s in SIDES:
        turn(chain("wing", side)[0], Y, s * (12 + 2 * math.sin(2 * w)))   # folded down a little, bouncing with the steps


# name: (motion, seconds, whether its feet move, the view its picture is taken from)
CLIPS = {
    "Idle": (idle, 4.0, False, (0.8, -1, 0.35)),
    "WingFlap": (wing_flap, 1.0, False, (0.8, -1, 0.35)),
    "Walk": (walk, WALK_SECONDS, True, (1, -0.15, 0.12)),
}

rig.animation_data_create()
for name, (motion, seconds, _, _) in CLIPS.items():
    action = bpy.data.actions.new(name)
    action.use_fake_user = True
    rig.animation_data.action = action
    frames = int(round(seconds * FPS))
    for f in range(frames + 1):          # the last frame is the first again, so the loop closes
        for p in pose:
            p.rotation_mode = "QUATERNION"
            p.rotation_quaternion = Quaternion()
            p.location = (0, 0, 0)
        motion(f / frames)
        for p in pose:
            p.keyframe_insert("rotation_quaternion", frame=f + 1)
            p.keyframe_insert("location", frame=f + 1)
    action.frame_range = (1, frames + 1)
    action.use_cyclic = True      # a label only: the Cycles modifiers below are what repeat it
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for curve in bag.fcurves:
                    curve.modifiers.new("CYCLES")
    print("CLIP", name, frames, "frames")

# The feet hold the ground. For a clip that stands: how far the skin on the ground (the lowest 2% of the height)
# moves over the loop. For every clip: how far each leg falls short of its foot's target (`ik_<foot>`): a leg that
# can't reach leaves its foot in the air. Both per metre of height; both must be ~0, or the creature floats or skates.
dg = bpy.context.evaluated_depsgraph_get()
rest = [v.co.copy() for v in body.data.vertices]
ground = [i for i, c in enumerate(rest) if c.z < HEIGHT * 0.02]
targets = [p for p in pose if p.name.startswith("ik_")]
report = {}
for name, (_, seconds, moves, _) in CLIPS.items():
    rig.animation_data.action = bpy.data.actions[name]
    frames = int(round(seconds * FPS))
    moved = miss = 0.0
    for f in range(1, frames + 1, max(1, frames // 24)):
        scene.frame_set(f)
        for t in targets:
            miss = max(miss, (pose[t.name[3:]].head - t.head).length)
        if not moves:
            verts = body.evaluated_get(dg).data.vertices
            moved = max(moved, max((verts[i].co - rest[i]).length for i in ground))
    entry = {"reach_miss_per_metre": round(miss / HEIGHT, 4)}
    if moves:
        speed = 2 * STRIDE / (STANCE * seconds)             # what the feet carry: the game moves it at this
        entry["speed_body_lengths_per_second"] = round(speed / LENGTH, 4)
        print("WALK", name, f"{speed / LENGTH:.3f} body lengths a second")
    else:
        entry["feet_moved_per_metre"] = round(moved / HEIGHT, 4)
        print("FEET", name, f"{1000 * moved / HEIGHT:.1f} mm per metre of height")
    print("REACH", name, f"{1000 * miss / HEIGHT:.1f} mm per metre of height")
    report[name] = entry
json.dump(report, open(os.path.join(HERE, "anim.json"), "w"), indent=1)

# Pictures: frames across each loop, Workbench in the texture's colours, from each clip's view.
scene.render.engine = "BLENDER_WORKBENCH"
shading = scene.display.shading
shading.light = "STUDIO"; shading.color_type = "TEXTURE"
W, H = 480, 360
scene.render.resolution_x, scene.render.resolution_y = W, H
scene.world = bpy.data.worlds.new("w")
size = max(body.dimensions)
cam = bpy.data.objects.new("anim_cam", bpy.data.cameras.new("anim_cam")); scene.collection.objects.link(cam)
scene.camera = cam
cam.data.type = "ORTHO"; cam.data.ortho_scale = size * 1.45; cam.data.clip_end = size * 10
for name, (_, seconds, _, view) in CLIPS.items():
    d = Vector(view).normalized()
    cam.location = Vector((0, 0, size * 0.3)) + d * size * 3
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    action = bpy.data.actions[name]
    rig.animation_data.action = action
    frames = int(round(seconds * FPS))
    shots = 8
    sheet = np.zeros((H, W * shots, 4), np.float32)
    for k in range(shots):
        scene.frame_set(1 + round(k * frames / shots))
        path = os.path.join(HERE, "_frame.png")
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(path)
        sheet[:, k * W:(k + 1) * W] = np.array(img.pixels[:], np.float32).reshape(H, W, 4)
        bpy.data.images.remove(img)
    out = bpy.data.images.new(f"anim_{name}", W * shots, H, alpha=True)
    out.pixels.foreach_set(sheet.ravel())
    out.filepath_raw = os.path.join(HERE, f"anim_{name}.png"); out.file_format = "PNG"; out.save()
os.remove(os.path.join(HERE, "_frame.png"))

bpy.data.objects.remove(cam, do_unlink=True)
rig.animation_data.action = bpy.data.actions["Idle"]
scene.frame_start, scene.frame_end = 1, int(4.0 * FPS)
# Saved with the skeleton chosen, so the Action Editor shows its clip on opening (it shows only the active object's).
bpy.ops.object.select_all(action="DESELECT")
rig.select_set(True)
bpy.context.view_layer.objects.active = rig
scene.render.engine = "BLENDER_EEVEE"
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, f"{NAME}_anim.blend"))
