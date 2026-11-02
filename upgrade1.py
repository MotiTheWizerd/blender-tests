import bpy, math
D = bpy.data
sc = D.scenes["longship"]
ship = sc.objects["ship"]
def link(ob): sc.collection.objects.link(ob); return ob

# lift the hull out of the swell
ship.animation_data.drivers.find("location", index=2).driver.expression = "sin(frame / 17) * 0.18 + 0.6"

# oars that row: one pivot per oarlock, the pivot sweeps, the oar rides it
oak = D.materials["oak"]
L, W = 7.0, 1.5
for ob in [o for o in sc.objects if o.name.startswith(("oar", "lock"))]:
    D.objects.remove(ob, do_unlink=True)
for side in (1, -1):
    for k in range(8):
        x = -4.025 + k * 1.15
        w = W * max(1 - (x / L) ** 2, 0) ** 0.55
        top = 0.35 + 1.5 * (x / L) ** 6
        piv = link(D.objects.new(f"lock {side} {k}", None))
        piv.location = (x, side * w, top)
        piv.parent = ship
        fc = piv.driver_add("rotation_euler", 2)
        fc.driver.expression = f"{side} * sin(frame / 9) * 0.32"
        fc = piv.driver_add("rotation_euler", 0)
        fc.driver.expression = f"{side} * (cos(frame / 9) * 0.12)"
        bpy.ops.mesh.primitive_cylinder_add(radius=0.045, depth=4.6, vertices=10,
                                            location=(0, side * 2.0, -1.15), rotation=(side * math.radians(60), 0, 0))
        oar = bpy.context.object; oar.name = f"oar {side} {k}"; oar.data.materials.append(oak); oar.parent = piv
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.3, location=(0, side * 3.9, -2.25))
        blade = bpy.context.object; blade.name = f"oar blade {side} {k}"
        blade.scale = (0.12, 0.9, 0.5); blade.rotation_euler = (side * math.radians(60), 0, 0)
        blade.data.materials.append(oak); blade.parent = piv

# the moon behind the ship, so its road on the water runs to her
sc.objects["moon"].location = (-135, 88, 30)

# the Langford arcs as an aurora over the horizon
for ob in [o for o in sc.objects if o.name.startswith("aurora")]:
    D.objects.remove(ob, do_unlink=True)
sky = link(D.objects.new("aurora", None))
sky.location = (-75, 85, 16)
sky.rotation_euler = (0, 0, math.radians(45))
sky.scale = (6.5, 6.5, 6.5)
fc = sky.driver_add("location", 2); fc.driver.expression = "16 + sin(frame / 40) * 1.2"
src = D.scenes["Scene"]
for o in src.objects:
    if o.type in {"CURVE", "MESH"} and (o.name.startswith("pair") or o.name.startswith("Sphere")):
        c = link(D.objects.new("aurora " + o.name, o.data))
        c.location = o.location
        c.parent = sky
for m in D.materials:
    if m.name.startswith("glow"):
        m.node_tree.nodes["Emission"].inputs["Strength"].default_value = 4.0
bpy.ops.wm.save_mainfile()
print("upgraded")
