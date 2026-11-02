"""A beauty shot of the Viking sword: scene `viking_beauty` (studio lighting, Cycles).

Run in the live Blender (python3 bl.py code beauty.py) to build the scene, then press F12 there
or render it headless: blender -b langford.blend -P render_beauty.py

The sword is the full high-poly `VikingSword` collection, instanced, so edits to it show here.
The lighting is a product-photo studio, built for METAL. Metal has almost no colour of its own:
it shows what it reflects. So the room is nearly black and the lights are long soft strips
whose reflections run down the blade:
  key    big soft box, upper left, warm       shapes the guard's heads and the pommel
  rims   two tall strips behind, cool / warm   outline the blade's edges against the dark
  fill   wide and weak, front right            keeps the shadow side from going to black
  glow   a pool of light on the backdrop       separates the sword from the background
"""
import bpy, math
from mathutils import Matrix, Vector

D = bpy.data
SW = D.collections["VikingSword"]
NAME = "viking_beauty"

old = D.scenes.get(NAME)
if old:
    for o in list(old.objects):
        D.objects.remove(o, do_unlink=True)
    D.scenes.remove(old)
sc = D.scenes.new(NAME)


def add(o):
    sc.collection.objects.link(o)
    return o


def aim(o, target):
    o.rotation_euler = (Vector(target) - o.location).to_track_quat("-Z", "Y").to_euler()


# ---------------- the sword: diagonal, turned so the guard's heads read in three-quarter ----------------
POSE = Matrix.Rotation(math.radians(-38), 4, "Y") @ Matrix.Rotation(math.radians(28), 4, "Z") \
    @ Matrix.Translation((0, 0, -0.19))                      # the sword's middle at the origin
sword = add(D.objects.new("sword", None))
sword.instance_type = "COLLECTION"; sword.instance_collection = SW
sword.matrix_world = POSE
GUARD = POSE @ Vector((0, 0, 0.005))

# ---------------- backdrop ----------------
bpy_mesh = D.meshes.new("backdrop")
bpy_mesh.from_pydata([(-6, 3.0, -4), (6, 3.0, -4), (6, 3.0, 4), (-6, 3.0, 4)], [], [(0, 1, 2, 3)])
back = add(D.objects.new("backdrop", bpy_mesh))
bm = D.materials.new("backdrop"); bm.use_nodes = True
bm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.02, 0.021, 0.024, 1)
bm.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9
bpy_mesh.materials.append(bm)

# ---------------- lights ----------------
def area(name, loc, size, energy, color, shape="RECTANGLE", target=(0, 0, 0), spread=180):
    l = D.lights.new(name, "AREA")
    l.shape = shape; l.size, l.size_y = size
    l.energy = energy; l.color = color; l.spread = math.radians(spread)
    o = add(D.objects.new(name, l)); o.location = loc; aim(o, target)
    return o


area("key", (-1.3, -1.1, 1.3), (1.2, 0.7), 220, (1.0, 0.9, 0.8), spread=70)
area("rim_left", (-1.15, 0.9, 0.2), (0.12, 1.8), 420, (0.75, 0.85, 1.0), spread=35)
area("rim_right", (1.2, 0.85, 0.45), (0.12, 1.8), 380, (1.0, 0.88, 0.72), spread=35)
area("fill", (1.6, -1.6, -0.1), (2.0, 2.0), 25, (0.9, 0.95, 1.0))
area("glow", (0.0, 1.0, -1.2), (2.0, 2.0), 90, (0.45, 0.52, 0.65), "DISK", target=(0, 3.0, 0.3), spread=60)

# The blade is a mirror-flat face: it shows a light only from the mirror direction. So a long
# softbox goes exactly there, computed from the pose and the hero camera, its long side along
# the blade. The highlight then sweeps down the steel.
HERO = Vector((0.05, -2.55, 0.12))
BLADE_MID = POSE @ Vector((0, 0, 0.33))
n = (POSE.to_3x3() @ Vector((0, -1, 0))).normalized()
v = (HERO - BLADE_MID).normalized()
r = (2 * n.dot(v) * n - v).normalized()
card = area("blade_card", BLADE_MID + r * 1.6, (0.3, 2.0), 260, (0.92, 0.96, 1.0), target=BLADE_MID)
up = (POSE.to_3x3() @ Vector((0, 0, 1))).normalized()
card.rotation_euler = (BLADE_MID - card.location).to_track_quat("-Z", "Y").to_euler()
# turn the strip about its own axis so its long side (local Y) runs along the blade
fwd = (BLADE_MID - card.location).normalized()
side = up - fwd * up.dot(fwd)
card.rotation_euler = Matrix((fwd.cross(side).normalized(), side.normalized(), -fwd)).transposed().to_euler()

world = D.worlds.new(NAME); world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.01, 0.01, 0.012, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0
sc.world = world

# The leather was varnish-glossy (roughness 0.55) and mirrored the softboxes as grey. Leather is
# ~0.75 with a weak specular. This changes the SHARED material: game_viking.py's next bake gets it too.
lb = next(n for n in D.materials["BlackLeather"].node_tree.nodes if n.type == "BSDF_PRINCIPLED")
lb.inputs["Roughness"].default_value = 0.78
lb.inputs["Specular IOR Level"].default_value = 0.3

# ---------------- cameras ----------------
def camera(name, loc, target, lens, fstop=None, focus=None):
    cd = D.cameras.new(name); cd.lens = lens; cd.clip_start = 0.01
    if fstop:
        cd.dof.use_dof = True; cd.dof.aperture_fstop = fstop
        cd.dof.focus_distance = (Vector(loc) - Vector(focus)).length
    o = add(D.objects.new(name, cd)); o.location = loc; aim(o, target)
    return o


hero = camera("cam_hero", HERO, (0.01, 0, -0.035), 68)
NEAR_HEAD = POSE @ Vector((-0.062, 0, 0.012))           # the dragon head nearer the camera
hilt = camera("cam_hilt", GUARD + Vector((-0.36, -0.78, 0.08)), GUARD + Vector((-0.01, 0, -0.03)), 100,
              fstop=4.0, focus=NEAR_HEAD)
sc.camera = hero

# ---------------- render ----------------
sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.samples = 96
sc.cycles.use_adaptive_sampling = True
sc.cycles.use_denoising = True
sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
sc.view_settings.view_transform = "AgX"
# One stop down: five lights each lit the black leather to grey. Metal shows only what it
# reflects, so the blade strip above is pushed up instead and the steel keeps its shine.
sc.view_settings.exposure = -1.0
for look in ("AgX - Punchy", "Punchy"):
    try:
        sc.view_settings.look = look
        break
    except TypeError:
        pass

for win in bpy.context.window_manager.windows:
    win.scene = sc
print("built", NAME, "guard at", tuple(round(c, 3) for c in GUARD))
