"""The body as built for Forge, brought into a scene to look at: a build folder's FBX (build/forge/<Title>, or a
snapshot of one) with its colour, normal and smoothness maps wired as URP Lit reads them. What status_scene.py and
compare_faces.py share.

    sys.path.insert(0, <this folder>); from built import import_build
"""
import os
import bpy


def import_build(folder, title, label):
    """The build's FBX imported, each slot's maps from the folder (the slot is the material's name as exported; a
    second build in the scene comes in as <slot>.001), the rig hidden, the faces smooth, the mesh named label.
    Returns the mesh object; its parent, when it has one, is the rig, and moving that moves the body."""
    scene = bpy.context.scene
    before = set(scene.objects)
    bpy.ops.import_scene.fbx(filepath=os.path.join(folder, title + ".fbx"))
    new = [o for o in scene.objects if o not in before]
    body = next(o for o in new if o.type == "MESH")
    body.name = label
    for m in body.data.materials:
        slot = m.name.split(".")[0]
        m.use_nodes = True
        nodes, links = m.node_tree.nodes, m.node_tree.links
        bsdf = nodes["Principled BSDF"]
        bsdf.inputs["Roughness"].default_value = 0.55
        c = nodes.new("ShaderNodeTexImage"); c.image = bpy.data.images.load(os.path.join(folder, slot + "_Color.png")); c.location = (-500, 300)
        links.new(c.outputs["Color"], bsdf.inputs["Base Color"])
        npath = os.path.join(folder, slot + "_Normal.png")
        if os.path.exists(npath):
            n = nodes.new("ShaderNodeTexImage"); n.image = bpy.data.images.load(npath); n.image.colorspace_settings.name = "Non-Color"; n.location = (-500, -100)
            nm = nodes.new("ShaderNodeNormalMap"); nm.location = (-200, -100)
            links.new(n.outputs["Color"], nm.inputs["Color"]); links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
        spath = os.path.join(folder, slot + "_MetallicSmoothness.png")
        if os.path.exists(spath):  # smoothness in the alpha, as URP reads it: roughness is 1 - alpha
            s = nodes.new("ShaderNodeTexImage"); s.image = bpy.data.images.load(spath); s.image.colorspace_settings.name = "Non-Color"; s.location = (-500, -500)
            inv = nodes.new("ShaderNodeMath"); inv.operation = "SUBTRACT"; inv.inputs[0].default_value = 1.0; inv.location = (-200, -500)
            links.new(s.outputs["Alpha"], inv.inputs[1]); links.new(inv.outputs["Value"], bsdf.inputs["Roughness"])
    for p in body.data.polygons:
        p.use_smooth = True
    for o in new:
        if o.type == "ARMATURE":
            o.hide_viewport = o.hide_render = True
    return body


def light_and_camera(scene, grey=0.35):
    """A sun, a grey world, a 50 mm camera and the saved file's viewport in material shading: the look every scene
    of hers shares. Returns the camera."""
    import numpy as np
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); sun.data.energy = 3.0
    sun.rotation_euler = (np.radians(60), 0, np.radians(-30)); scene.collection.objects.link(sun)
    world = bpy.data.worlds.new("w"); world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (grey, grey, grey, 1); scene.world = world
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); cam.data.lens = 50
    scene.collection.objects.link(cam); scene.camera = cam
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y = 1600, 1000
    for area in bpy.context.screen.areas:
        if area.type == "VIEW_3D":
            for space in area.spaces:
                if space.type == "VIEW_3D":
                    space.shading.type = "MATERIAL"
    return cam
