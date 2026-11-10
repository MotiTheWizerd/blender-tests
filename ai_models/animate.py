"""Step 6 for a creature: its animations, written as motion on its skeleton (no hand keys), so the next creature with
the same chains gets them too.

    blender -b --factory-startup -P animate.py -- dragon

Reads build/<name>_rig.blend (step 3). Each clip is an action keyed on every frame from curves of time; every loop
ends where it began. The rest pose is the legs' full reach (its feet are planted by IK, step 3), so the body only
ever moves DOWN from it and back: a chest that rose past rest would pull the feet off the ground. A motion is a turn
about an axis of the creature's own frame (X across, Y front to back, Z up),
added on top of the bone's parent, so a wing's beat reads the same on both sides with the sign mirrored.
Writes build/<name>_anim.blend (the clips as actions, Idle playing, the frame range set) and, in checks/, for each
clip anim_<clip>.jpg (frames across one loop, side by side) and, for a clip that moves, anim_<clip>_side.jpg (four
large side views over the ground, a quarter cycle apart).

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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from place import Creature, pictures_as_jpeg, save_blend
C = Creature(NAME)
FPS = 30
bpy.ops.wm.open_mainfile(filepath=C.blend("rig"))
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


# The bird set (model.json "clips": "bird"; raven_1): chains spine (2 bones), neck, head (skull, beak), tail, leg.L/R
# (planted), wing.L/R folded along the body. A folded wing can lift and ruffle but not open to fly: the feathers were
# made folded.

def ease(q):
    q = max(0.0, min(1.0, q))
    return q * q * (3 - 2 * q)


def blend_keys(t, keys, snap):
    """A value held at each key (time, value...) and snapped to the next over `snap` of the cycle (a bird's head
    holds still and moves in jerks). The keys wrap: the last one snaps back to the first by t = 1."""
    keys = list(keys) + [(1.0,) + tuple(keys[0][1:])]
    for (t0, *a), (t1, *b) in zip(keys, keys[1:]):
        if t0 <= t < t1 or t1 == 1.0:
            q = ease((t - (t1 - snap)) / snap)
            return [x + (y - x) * q for x, y in zip(a, b)]


def flick(t, at, width):
    """0 .. 1 .. 0 over `width` of the cycle centred on `at`: a quick flick."""
    d = abs(t - at) / (width / 2)
    return 0.0 if d >= 1 else math.sin(math.pi * (1 - d) / 2) ** 2


def bird_head(yaw, roll, pitch):
    """Look: the neck takes a third, the head the rest. Yaw +Z is the bird's left, roll about Y cocks the head,
    pitch +X looks down."""
    neck, head = chain("neck"), chain("head")[0]
    for b in neck:
        turn(b, Z, yaw / 3 / len(neck)); turn(b, X, pitch / 3 / len(neck))
    turn(head, Z, yaw * 2 / 3); turn(head, Y, roll); turn(head, X, pitch * 2 / 3)


def bird_idle(t):
    w = 2 * math.pi * t
    sink = (1 - math.cos(3 * w)) / 2                     # three breaths a loop, the chest only sinking from rest
    spine = chain("spine")
    turn(spine[1], X, 1.0 * sink)
    turn(chain("neck")[0], X, -1.0 * sink)
    bird_head(*blend_keys(t, [(0.0, 0, 0, 0), (0.16, 35, 0, -4), (0.34, 35, -18, 0), (0.52, -30, 0, -6),
                              (0.72, -12, 12, 10), (0.88, 0, 0, 0)], 0.03))
    up = 12 * flick(t, 0.3, 0.05) + 9 * flick(t, 0.66, 0.05)   # two quick flicks of the tail
    for i, b in enumerate(chain("tail")):
        turn(b, X, up / 3 + 0.8 * math.sin(w - 0.4 * i))
    for side, s in SIDES:
        turn(chain("wing", side)[0], Y, -s * 1.5 * sink)


def bird_peck(t):
    down = ease(t / 0.3) * (1 - ease((t - 0.72) / 0.28))     # tip forward, hold, come back up
    jabs = flick(t, 0.42, 0.14) + flick(t, 0.6, 0.14)        # two pecks while down
    spine = chain("spine")
    turn(spine[0], X, 14 * down)
    turn(spine[1], X, 16 * down)
    for b in chain("neck"):
        turn(b, X, (22 + 10 * jabs) * down)
    turn(chain("head")[0], X, (12 + 6 * jabs) * down)
    for i, b in enumerate(chain("tail")):
        turn(b, X, (3 + 2 * i) * down)                        # the tail rises with the bow (+X lifts a bone pointing back)
    for side, s in SIDES:
        turn(chain("wing", side)[0], Y, -s * 3 * down)


BIRD_STRIDE = 0.07 * HEIGHT
BIRD_LIFT = 0.06 * HEIGHT
BIRD_STANCE = 0.6
BIRD_WALK_SECONDS = 0.9


def bird_walk(t):
    w = 2 * math.pi * t
    for side, phase in (("L", 0.0), ("R", 0.5)):
        target = next(p for p in pose if p.name.startswith("ik_leg_") and p.name.endswith("." + side))
        p = (t - phase) % 1.0
        if p < BIRD_STANCE:
            y, z = -BIRD_STRIDE + 2 * BIRD_STRIDE * p / BIRD_STANCE, 0.0
        else:
            q = (p - BIRD_STANCE) / (1 - BIRD_STANCE)
            y, z = BIRD_STRIDE - 2 * BIRD_STRIDE * ease(q), BIRD_LIFT * math.sin(math.pi * q)
        shift(target, (0, y, z))
    spine = chain("spine")
    dip = 0.015 * HEIGHT * (1 - math.cos(2 * w)) / 2         # twice a cycle, down only
    shift(spine[0], (0.015 * HEIGHT * math.sin(w), 0, -0.03 * HEIGHT - dip))
    turn(spine[0], Y, 4 * math.sin(w))                        # the swagger: the body rolls over the standing foot
    turn(spine[0], Z, 3 * math.sin(w))
    thrust = math.sin(2 * w)                                  # the head thrusts forward with each step
    for b in chain("neck"):
        turn(b, X, 4 * thrust)
    turn(chain("head")[0], X, -4 * thrust)
    for i, b in enumerate(chain("tail")):
        turn(b, Z, -(2 + i) * math.sin(w - 0.4 * i))


def bird_shake(t):
    env = math.sin(math.pi * t) ** 2                          # from rest to rest
    shiver = math.sin(2 * math.pi * 6 * t)
    turn(chain("spine")[1], Y, 6 * env * shiver)
    for side, s in SIDES:
        out = 22 * env * (0.6 + 0.4 * math.sin(2 * math.pi * 2 * t)) ** 2
        wing = chain("wing", side)
        turn(wing[0], Y, -s * out)
        turn(wing[1], Z, -s * out * 0.4)                      # the primaries part a little
    for i, b in enumerate(chain("tail")):
        turn(b, Z, 5 * env * math.sin(2 * math.pi * 6 * t - 0.5 * i))
        turn(b, X, 6 * env)
    bird_head(0, 10 * env * math.sin(2 * math.pi * 6 * t + 1.0), -3 * env)


TAKEOFF_SECONDS = 1.8
TAKEOFF_BEATS = 3.5             # wingbeats a second once it is up


def bird_takeoff(t):
    """Played once: a crouch, a spring off the ground with the first downstroke, then the climb, beating. It moves
    itself (up about its height, forward half its length), so it ends in the air where the game takes over. The folded
    wings swing out from the body and beat; they don't fan open (the feathers were made folded)."""
    crouch = ease(t / 0.2) * (1 - ease((t - 0.22) / 0.1))           # down, then sprung out of
    climb = ease((t - 0.25) / 0.75) ** 0.8                           # up and forward from the spring
    air = ease((t - 0.28) / 0.12)                                    # the feet off the ground and tucking
    opened = ease((t - 0.08) / 0.17)                                 # the wings out from the body
    beat = math.cos(2 * math.pi * TAKEOFF_BEATS * TAKEOFF_SECONDS * max(0.0, t - 0.27))   # +1 up, -1 down
    bob = 0.03 * HEIGHT * air * -math.sin(2 * math.pi * TAKEOFF_BEATS * TAKEOFF_SECONDS * max(0.0, t - 0.27))
    lift = (-0.08 * HEIGHT * crouch + 0.9 * HEIGHT * climb + bob)
    ahead = -0.5 * LENGTH * climb                                    # forward is -Y
    spine = chain("spine")
    shift(spine[0], (0, ahead, lift))
    turn(spine[0], X, 12 * crouch + 28 * air)                        # tips forward to crouch, and towards level to fly
    # The feet hold the ground until the spring, then ride with the body, tucked up and back under it.
    for side, s in SIDES:
        target = next(p for p in pose if p.name.startswith("ik_leg_") and p.name.endswith("." + side))
        shift(target, (0, (ahead + 0.12 * LENGTH * air) * air, (lift + 0.12 * HEIGHT) * air))
    for side, s in SIDES:
        wing = chain("wing", side)
        turn(wing[0], Z, -s * 55 * opened)                            # out from the body, sideways
        # and beating about the body's axis: the folded wing slopes down at rest, so 45 +- 40 is just below level to high
        turn(wing[0], Y, -s * opened * (45 + 40 * (beat if t > 0.27 else 1.0)))
        turn(wing[1], Z, -s * 20 * opened)                            # the primaries swung out to a longer line
        turn(wing[1], Y, -s * 15 * opened * math.cos(2 * math.pi * TAKEOFF_BEATS * TAKEOFF_SECONDS * max(0.0, t - 0.27) - 0.7))
    for b in chain("neck"):
        turn(b, X, -6 * crouch - 9 * air)                             # looks up in the crouch, and ahead in the air
    turn(chain("head")[0], X, -10 * air)                              # the head kept level against the forward-tipped body
    for i, b in enumerate(chain("tail")):
        turn(b, X, 10 * crouch - 6 * air + 4 * air * beat)           # up in the crouch, down and pumping in the air


# The flying set (model.json "clips": "bird_fly"; raven_1_fly, made with its wings spread): chains spine, neck, head,
# tail, wing.L/R (shoulder, elbow, wrist, then the hand in two bones). No feet: it is in the air.
FLY_SECONDS = 0.32              # one wingbeat: a raven beats about three times a second


def bird_fly(t):
    """One wingbeat. Down with the wing spread; up with the hand folded back and bent, the way a wing recovers
    without lifting air against itself. The body rises on the downstroke; the tail and head steady it."""
    w = 2 * math.pi * t
    up = math.cos(w)                                       # +1 at the top of the beat, -1 at the bottom
    recover = max(0.0, -math.sin(w))                        # 0 .. 1 .. 0 over the upstroke (the second half)
    for side, s in SIDES:
        wing = chain("wing", side)
        turn(wing[0], Y, -s * (8 + 42 * up))                 # the shoulder: 50 up .. 34 down
        turn(wing[1], Y, -s * 12 * math.cos(w - 0.5))         # the arm lags the shoulder
        turn(wing[2], Z, s * 38 * recover)                    # the hand sweeps back on the way up (+Z sweeps a left wing back)
        turn(wing[2], Y, -s * 18 * math.cos(w - 1.0))         # and trails the arm
        turn(wing[3], Y, -s * 14 * math.cos(w - 1.4))         # the tips trail most
    spine = chain("spine")
    shift(spine[0], (0, 0, 0.03 * HEIGHT * math.sin(w)))   # lifted by the downstroke
    turn(spine[0], X, 10 + 2 * math.sin(w))                  # flies a little more level than it was made
    for b in chain("neck"):
        turn(b, X, -4 - 1.5 * math.sin(w))                    # the head held steady against the body
    for i, b in enumerate(chain("tail")):
        turn(b, X, 3 * math.sin(w - 0.6 - 0.3 * i))


def bird_glide(t):
    """Soaring: the wings held in a shallow V, slow banking rolls, the tail steering against them, the head looking
    about."""
    w = 2 * math.pi * t
    bank = math.sin(w)
    spine = chain("spine")
    turn(spine[0], Y, 9 * bank)                               # roll into the turn
    turn(spine[0], X, 6 + 2 * math.sin(2 * w))
    shift(spine[0], (0, 0, 0.02 * HEIGHT * math.sin(2 * w + 0.5)))
    for side, s in SIDES:
        wing = chain("wing", side)
        turn(wing[0], Y, -s * (10 + 3 * math.sin(2 * w + (0.4 if s > 0 else 0))))   # the V, breathing in the air
        turn(wing[2], Y, s * 4 * math.sin(2 * w + 1.0))       # the hands flex a little
        turn(wing[3], Y, -s * 6 * math.sin(2 * w + 1.6))      # the tips give to the air
    for i, b in enumerate(chain("tail")):
        turn(b, Y, -6 * bank)                                 # the tail twists against the roll
        turn(b, Z, 4 * math.sin(w - 0.8))
    for b in chain("neck"):
        turn(b, Y, -6 * bank)                                 # the head stays level while the body banks
    turn(chain("head")[0], Z, 20 * math.sin(w + 1.2))         # and looks about


# name: (motion, seconds, whether its feet move, the view its picture is taken from)
if C.spec.get("clips") == "bird_fly":
    CLIPS = {
        "Fly": (bird_fly, FLY_SECONDS, False, (0.7, -1, 0.4)),
        "Glide": (bird_glide, 4.0, False, (0.7, -1, 0.4)),
    }
elif C.spec.get("clips") == "bird":
    STRIDE, STANCE, WALK_SECONDS = BIRD_STRIDE, BIRD_STANCE, BIRD_WALK_SECONDS     # the walk's speed, below
    CLIPS = {
        "Idle": (bird_idle, 6.0, False, (0.8, -1, 0.35)),
        "Peck": (bird_peck, 1.6, False, (1, -0.3, 0.2)),
        "Walk": (bird_walk, BIRD_WALK_SECONDS, True, (1, -0.15, 0.12)),
        "Shake": (bird_shake, 1.6, False, (0.6, 1, 0.5)),
        "TakeOff": (bird_takeoff, TAKEOFF_SECONDS, True, (1, -0.2, 0.3)),
    }
else:
    CLIPS = {
        "Idle": (idle, 4.0, False, (0.8, -1, 0.35)),
        "WingFlap": (wing_flap, 1.0, False, (0.8, -1, 0.35)),
        "Walk": (walk, WALK_SECONDS, True, (1, -0.15, 0.12)),
    }

ONCE = {"TakeOff"}               # clips that don't loop

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
    if name in ONCE:              # played once (it ends somewhere else): no repeat
        print("CLIP", name, frames, "frames, once")
        continue
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
targets = [p for p in pose if p.name.startswith("ik_")]
# The skin on the ground is the legs' (a raven's tail tip hangs 1.5 cm up, inside the 2%, and is meant to move).
legs = tuple(t.name[3:].split("_")[0] + "_" for t in targets)
names = {g.index: g.name for g in body.vertex_groups}
ground = [i for i, c in enumerate(rest) if c.z < HEIGHT * 0.02 and body.data.vertices[i].groups
          and names[max(body.data.vertices[i].groups, key=lambda g: g.weight).group].startswith(legs)]
report = {}
for name, (_, seconds, moves, _) in CLIPS.items():
    rig.animation_data.action = bpy.data.actions[name]
    frames = int(round(seconds * FPS))
    moved = miss = 0.0
    for f in range(1, frames + 1, max(1, frames // 24)):
        scene.frame_set(f)
        for t in targets:
            miss = max(miss, (pose[t.name[3:]].head - t.head).length)
        if not moves and ground:            # (a creature in the air has no ground)
            verts = body.evaluated_get(dg).data.vertices
            moved = max(moved, max((verts[i].co - rest[i]).length for i in ground))
    entry = {"reach_miss_per_metre": round(miss / HEIGHT, 4)}
    if moves and name in ONCE:
        pass                                                # it travels: no stance to measure
    elif moves:
        speed = 2 * STRIDE / (STANCE * seconds)             # what the feet carry: the game moves it at this
        entry["speed_body_lengths_per_second"] = round(speed / LENGTH, 4)
        print("WALK", name, f"{speed / LENGTH:.3f} body lengths a second")
    else:
        entry["feet_moved_per_metre"] = round(moved / HEIGHT, 4)
        print("FEET", name, f"{1000 * moved / HEIGHT:.1f} mm per metre of height")
    print("REACH", name, f"{1000 * miss / HEIGHT:.1f} mm per metre of height")
    report[name] = entry
json.dump(report, open(C.checks("anim.json"), "w"), indent=1)

# Pictures: frames across each loop, Workbench in the texture's colours, from each clip's view.
scene.render.engine = "BLENDER_WORKBENCH"
shading = scene.display.shading
shading.light = "STUDIO"; shading.color_type = "TEXTURE"
W, H = 480, 360
scene.render.resolution_x, scene.render.resolution_y = W, H
pictures_as_jpeg(scene)
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
        path = C.build("_frame.jpg")
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(path)
        sheet[:, k * W:(k + 1) * W] = np.array(img.pixels[:], np.float32).reshape(H, W, 4)
        bpy.data.images.remove(img)
    out = bpy.data.images.new(f"anim_{name}", W * shots, H, alpha=True)
    out.pixels.foreach_set(sheet.ravel())
    out.filepath_raw = C.picture(f"anim_{name}"); out.file_format = "JPEG"; out.save()

# A clip that moves its feet, close: four large side views a quarter cycle apart, over a ground plane, the legs and
# feet big enough to judge whether each foot is planted or swinging.
floor = bpy.data.meshes.new("floor")
floor.from_pydata([(-size, -size, 0), (size, -size, 0), (size, size, 0), (-size, size, 0)], [], [(0, 1, 2, 3)])
ground_plane = bpy.data.objects.new("floor", floor); scene.collection.objects.link(ground_plane)
SW, SH = 900, 520
scene.render.resolution_x, scene.render.resolution_y = SW, SH
cam.data.ortho_scale = size * 0.75
d = Vector((1, -0.1, 0.05)).normalized()
cam.location = Vector((0, -0.15 * size, 0.2 * size)) + d * size * 3
cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
for name, (_, seconds, moves, _) in CLIPS.items():
    if not moves:
        continue
    rig.animation_data.action = bpy.data.actions[name]
    frames = int(round(seconds * FPS))
    sheet = np.zeros((SH * 2, SW * 2, 4), np.float32)
    for k in range(4):
        scene.frame_set(1 + round(k * frames / 4))
        scene.render.filepath = C.build("_frame.jpg")
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(C.build("_frame.jpg"))
        row, col = 1 - k // 2, k % 2                      # first frame top left (images count rows from the bottom)
        sheet[row * SH:(row + 1) * SH, col * SW:(col + 1) * SW] = np.array(img.pixels[:], np.float32).reshape(SH, SW, 4)
        bpy.data.images.remove(img)
    out = bpy.data.images.new(f"anim_{name}_side", SW * 2, SH * 2, alpha=True)
    out.pixels.foreach_set(sheet.ravel())
    out.filepath_raw = C.picture(f"anim_{name}_side"); out.file_format = "JPEG"; out.save()
bpy.data.objects.remove(ground_plane, do_unlink=True)
os.remove(C.build("_frame.jpg"))

bpy.data.objects.remove(cam, do_unlink=True)
first = next(iter(CLIPS))                      # Idle, or a flying set's Fly
rig.animation_data.action = bpy.data.actions[first]
scene.frame_start, scene.frame_end = 1, int(CLIPS[first][1] * FPS)
# Saved with the skeleton chosen, so the Action Editor shows its clip on opening (it shows only the active object's).
bpy.ops.object.select_all(action="DESELECT")
rig.select_set(True)
bpy.context.view_layer.objects.active = rig
scene.render.engine = "BLENDER_EEVEE"
save_blend(bpy, C.blend("anim"))
