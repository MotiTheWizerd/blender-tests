"""Eyes of their own for a head head.py made: where its painted eyes open, cut open, for eyeballs to sit behind.

    blender -b --factory-startup -P eyes.py -- head_warrior_m

A Tripo head is one closed skin with its eyes painted on, its lids sculpted over an even grid that runs straight across
them (probe_eyes.py). Each eye is seen from the front as a map: the face is ray-cast along its front (-y) on a fine
grid round the eye, and each hit takes the colour its texture has there (no light: the paint itself). The eye is what
is not skin there, reached from the iris: the white and the iris are cool or grey where skin is warm. Its outline,
a radius for every angle round its middle smoothed of the pixels' steps, is the opening.

Writes checks/eyes.json (each eye's middle, opening, how much of it was found) and checks/eyes_map_<side>.png (the
front map, the opening's outline drawn on it).
"""
import bpy, json, math, os, sys
import numpy as np
from glob import glob
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.interpolate import poly_3d_calc

STEP = 0.00015      # the front map's grid, metres
REACH = (0.024, 0.016)   # the map's half width and half height round an eye's middle
WARM = 0.16         # skin: (red - blue) over the brightest channel above this; the eye's white and iris below
ANGLES = 180        # the outline's radii round the eye
SMOOTH = 8          # the outline keeps this many waves round the eye (its corners, its lids' curves), no finer


def front_map(head, image, centre):
    """The colour under each point of a grid round centre (x, z), seen from the front, and the hits' depth (y);
    nan where the ray misses."""
    me = head.data
    me.calc_loop_triangles()
    tree = BVHTree.FromObject(head, bpy.context.evaluated_depsgraph_get())
    uv = me.uv_layers.active.data
    w, h = image.size
    pixels = np.array(image.pixels[:], dtype=np.float32).reshape(h, w, image.channels)[..., :3]
    xs = np.arange(centre[0] - REACH[0], centre[0] + REACH[0], STEP)
    zs = np.arange(centre[2] - REACH[1], centre[2] + REACH[1], STEP)
    colour = np.full((len(zs), len(xs), 3), np.nan, dtype=np.float32)
    depth = np.full((len(zs), len(xs)), np.nan, dtype=np.float32)
    polygons = me.polygons
    for j, z in enumerate(zs):
        for i, x in enumerate(xs):
            hit, _, index, _ = tree.ray_cast(Vector((x, -1.0, z)), Vector((0.0, 1.0, 0.0)), 2.0)
            if hit is None:
                continue
            poly = polygons[index]
            corners = [me.vertices[v].co for v in poly.vertices]
            weights = poly_3d_calc(corners, hit)
            u = sum(uv[l].uv[0] * wt for l, wt in zip(poly.loop_indices, weights))
            v = sum(uv[l].uv[1] * wt for l, wt in zip(poly.loop_indices, weights))
            colour[j, i] = pixels[int(min(max(v, 0), 1) * (h - 1)), int(min(max(u, 0), 1) * (w - 1))]
            depth[j, i] = hit.y
    return xs, zs, colour, depth


def opening(colour, seed):
    """The eye in the map: the not-warm pixels joined to seed (the iris, (row, column)), its holes (the pupil, the
    catch-light) filled."""
    r, g, b = colour[..., 0], colour[..., 1], colour[..., 2]
    warmth = (r - b) / np.maximum(colour.max(-1), 1e-3)
    eye = np.nan_to_num(warmth, nan=1.0) < WARM
    # Joined to the seed (4-neighbours), by a flood over the mask.
    reached = np.zeros_like(eye)
    if not eye[seed]:
        near = np.argwhere(eye)
        seed = tuple(near[np.argmin(((near - np.array(seed)) ** 2).sum(1))])
    stack = [seed]
    reached[seed] = True
    rows, cols = eye.shape
    while stack:
        y, x = stack.pop()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < rows and 0 <= nx < cols and eye[ny, nx] and not reached[ny, nx]:
                reached[ny, nx] = True
                stack.append((ny, nx))
    return reached, warmth


def outline(mask, xs, zs):
    """The opening's outline: its middle (x, z) and, for ANGLES angles round it, its radius (metres), smoothed to
    SMOOTH waves."""
    ys, xs_i = np.nonzero(mask)
    px, pz = xs[xs_i], zs[ys]
    middle = np.array([(px.min() + px.max()) / 2, (pz.min() + pz.max()) / 2])
    angles = np.arctan2(pz - middle[1], px - middle[0])
    radii = np.hypot(px - middle[0], pz - middle[1])
    bins = ((angles + math.pi) / (2 * math.pi) * ANGLES).astype(int) % ANGLES
    radius = np.zeros(ANGLES)
    np.maximum.at(radius, bins, radii)
    # An empty bin takes its neighbours' (none should be, but an eye's corner can be thin).
    for k in np.nonzero(radius == 0)[0]:
        radius[k] = (radius[k - 1] + radius[(k + 1) % ANGLES]) / 2
    spectrum = np.fft.rfft(radius)
    spectrum[SMOOTH + 1:] = 0
    return middle, np.fft.irfft(spectrum, ANGLES)


def radius_at(middle, radius, x, z):
    """The outline's radius toward (x, z)."""
    a = math.atan2(z - middle[1], x - middle[0])
    centres = -math.pi + 2 * math.pi * (np.arange(ANGLES) + 0.5) / ANGLES
    return float(np.interp(a, centres, radius, period=2 * math.pi))


WALL = 0.003        # how far back the lids' inside goes from the opening (metres)
TUCK = 0.0005       # how far inside the eyeball's sphere the lids' inside lies, so the eyeball always hides it
FRONT = 0.012       # only faces this near the eye's painted surface are cut (not the back of the head behind it)


def cut(bm, middle, radius, surface_y, eyeball):
    """The opening cut through the skin: the faces inside the outline near the eye's surface gone, the hole's edge
    laid on the outline (the grid's steps smoothed away) and drawing the skin that lies there, and the lids' inside:
    that edge carried WALL back into the eyeball's sphere (eyeball: its centre, its radius), TUCK under its surface,
    so it lies behind the eyeball however it turns. Returns the wall's faces and the edge's vertices."""
    import bmesh
    # The skin as it was, for the texture under a vertex once it has moved.
    before = bm.copy()
    before.faces.ensure_lookup_table()
    before_tree = BVHTree.FromBMesh(before)
    uv_layer = bm.loops.layers.uv.active
    before_uv = before.loops.layers.uv.active

    def uv_under(co):
        location, _, index, _ = before_tree.find_nearest(co)
        face = before.faces[index]
        weights = poly_3d_calc([v.co for v in face.verts], location)
        return sum((l[before_uv].uv * w for l, w in zip(face.loops, weights)), Vector((0.0, 0.0)))

    inside = [f for f in bm.faces
              if abs(f.calc_center_median().y - surface_y) < FRONT
              and math.hypot(f.calc_center_median().x - middle[0], f.calc_center_median().z - middle[1])
              < radius_at(middle, radius, f.calc_center_median().x, f.calc_center_median().z)]
    bmesh.ops.delete(bm, geom=inside, context="FACES_ONLY")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    rim = {v for e in bm.edges if e.is_boundary for v in e.verts
           if abs(v.co.y - surface_y) < FRONT and math.hypot(v.co.x - middle[0], v.co.z - middle[1]) < 0.03}
    shapes = list(bm.verts.layers.shape.values())
    for v in rim:
        a = math.atan2(v.co.z - middle[1], v.co.x - middle[0])
        r = radius_at(middle, radius, v.co.x, v.co.z)
        move = Vector((middle[0] + r * math.cos(a), v.co.y, middle[1] + r * math.sin(a))) - v.co
        v.co += move
        for layer in shapes:
            v[layer] += move
    # Edges of the rim that the snapping made too short to see: their two ends become one.
    bmesh.ops.remove_doubles(bm, verts=list(rim), dist=0.0002)
    rim = [v for v in bm.verts if v.is_valid and v.is_boundary
           and abs(v.co.y - surface_y) < FRONT and math.hypot(v.co.x - middle[0], v.co.z - middle[1]) < 0.03]
    # The rim draws the skin now under it (its corners' texture was where the grid's corner stood, on the eye's white).
    for v in rim:
        at = uv_under(v.co)
        for loop in v.link_loops:
            loop[uv_layer].uv = at
    edges = [e for e in bm.edges if e.is_boundary and all(v in rim for v in e.verts)]
    made = bmesh.ops.extrude_edge_only(bm, edges=edges)["geom"]
    wall_verts = [g for g in made if isinstance(g, bmesh.types.BMVert)]
    centre, r = Vector(eyeball[0]), eyeball[1]
    for v in wall_verts:
        # Back WALL, then onto the sphere TUCK under the eyeball's surface.
        back = v.co + Vector((0.0, WALL, 0.0))
        target = centre + (back - centre).normalized() * (r - TUCK)
        move = target - v.co
        v.co += move
        for layer in shapes:
            v[layer] += move
    wall = [g for g in made if isinstance(g, bmesh.types.BMFace)]
    for f in wall:
        f.smooth = True
    before.free()
    return wall, rim


def sphere_fit(points):
    """The sphere through points (n, 3) nearest them: its centre and radius."""
    a = np.c_[2 * points, np.ones(len(points))]
    solution = np.linalg.lstsq(a, (points ** 2).sum(1), rcond=None)[0]
    centre = solution[:3]
    return centre, float(np.sqrt(solution[3] + (centre ** 2).sum()))


if __name__ == "__main__":
    NAME = sys.argv[sys.argv.index("--") + 1]
    HERE = os.path.dirname(os.path.abspath(__file__))
    ROOT = os.path.join(HERE, NAME)
    made = glob(os.path.join(ROOT, "build", "forge", "*", "*.fbx"))
    if len(made) != 1:
        raise SystemExit(f"EYES {NAME} has {len(made)} exports (run head.py)")
    TITLE = os.path.basename(os.path.dirname(made[0]))
    probe = json.load(open(os.path.join(ROOT, "checks", "eyes_probe.json")))

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=made[0])
    head = next(o for o in bpy.data.objects if o.type == "MESH")
    head.data.transform(head.matrix_world, shape_keys=True)
    head.matrix_world = Matrix.Identity(4)
    head.data.update()
    image = bpy.data.images.load(os.path.join(os.path.dirname(made[0]), f"{TITLE}_BaseColor.jpg"))

    report = {}
    for side in ("right", "left"):
        found = probe["eyes"][side]
        iris = found["iris_centre_m"] or found["centre_m"]
        xs, zs, colour, depth = front_map(head, image, iris)
        seed = (int(np.argmin(np.abs(zs - iris[2]))), int(np.argmin(np.abs(xs - iris[0]))))
        mask, warmth = opening(colour, seed)
        middle, radius = outline(mask, xs, zs)
        report[side] = {"middle_m": [round(float(middle[0]), 4), round(float(middle[1]), 4)],
                        "width_mm": round(float(radius[0] + radius[ANGLES // 2]) * 1000, 1),
                        "height_mm": round(float(radius[ANGLES // 4] + radius[3 * ANGLES // 4]) * 1000, 1),
                        "pixels": int(mask.sum()), "touches_map_edge": bool(mask[0].any() or mask[-1].any()
                                                                            or mask[:, 0].any() or mask[:, -1].any())}
        # The map as seen (its rows bottom-up: z grows up), the found eye tinted and the outline drawn.
        picture = np.nan_to_num(colour, nan=0.0).copy()
        picture[mask] = picture[mask] * 0.6 + np.array([0.0, 0.35, 0.0])
        for k in range(ANGLES * 4):
            a = -math.pi + 2 * math.pi * k / (ANGLES * 4)
            rr = np.interp(a, -math.pi + 2 * math.pi * (np.arange(ANGLES) + 0.5) / ANGLES, radius, period=2 * math.pi)
            x, z = middle[0] + rr * math.cos(a), middle[1] + rr * math.sin(a)
            i, j = int(round((x - xs[0]) / STEP)), int(round((z - zs[0]) / STEP))
            if 0 <= j < picture.shape[0] and 0 <= i < picture.shape[1]:
                picture[j, i] = (1.0, 0.1, 0.8)
        out = bpy.data.images.new(f"eyes_map_{side}", picture.shape[1], picture.shape[0], alpha=False)
        out.pixels = np.concatenate([picture, np.ones(picture.shape[:2] + (1,), np.float32)], -1).ravel()
        out.filepath_raw = os.path.join(ROOT, "checks", f"eyes_map_{side}.png")
        out.file_format = "PNG"
        out.save()
        print("EYES", side, report[side], "warmth p5/p50/p95 in eye", np.percentile(warmth[mask], [5, 50, 95]).round(3),
              "skin", np.nanpercentile(np.where(mask, np.nan, warmth), [5, 50]).round(3))
        gx, gz = np.meshgrid(xs, zs)
        surface = np.c_[gx[mask], depth[mask], gz[mask]]
        centre, r = sphere_fit(surface[~np.isnan(surface).any(1)])
        report[side].update(surface_y=round(float(np.nanmedian(depth[mask])), 4),
                            eyeball_fit={"centre_m": centre.round(4).tolist(), "radius_mm": round(r * 1000, 1)})
        report[side]["_outline"] = (middle, radius)

    # Cut both openings.
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(head.data)
    for side in ("right", "left"):
        middle, radius = report[side].pop("_outline")
        before = len(bm.faces)
        fit = report[side]["eyeball_fit"]
        wall, rim = cut(bm, middle, radius, report[side]["surface_y"], (fit["centre_m"], fit["radius_mm"] / 1000))
        report[side].update(faces_cut=before - len(bm.faces) + len(wall), rim_vertices=len(rim), wall_faces=len(wall))
    report["open_edges_after"] = sum(1 for e in bm.edges if e.is_boundary)
    bm.to_mesh(head.data)
    bm.free()
    head.data.update()
    json.dump(report, open(os.path.join(ROOT, "checks", "eyes.json"), "w"), indent=1)
    print("EYES", json.dumps(report))

    # Pictures: the openings in the face's colours, then with stand-in eyeballs (grey spheres where the fit puts them).
    sys.path.insert(0, HERE)
    from place import pictures_as_jpeg
    scene = bpy.context.scene
    pictures_as_jpeg(scene)
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "TEXTURE"
    scene.render.resolution_x, scene.render.resolution_y = 1200, 600
    scene.world = bpy.data.worlds.new("w")
    skin = bpy.data.materials.new("skin")
    skin.use_nodes = True
    node = skin.node_tree.nodes.new("ShaderNodeTexImage")
    node.image = image
    skin.node_tree.nodes.active = node
    head.data.materials.clear()
    head.data.materials.append(skin)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.type = "ORTHO"
    mid = Vector(((report["right"]["middle_m"][0] + report["left"]["middle_m"][0]) / 2, report["right"]["surface_y"],
                  report["right"]["middle_m"][1]))

    def shoot(name, centre, direction, ortho, size=(1200, 600)):
        d = Vector(direction).normalized()
        cam.location = centre + d * 1.5
        cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
        cam.data.ortho_scale = ortho
        scene.render.resolution_x, scene.render.resolution_y = size
        scene.render.filepath = os.path.join(ROOT, "checks", name + ".jpg")
        bpy.ops.render.render(write_still=True)

    right = Vector((report["right"]["middle_m"][0], report["right"]["surface_y"], report["right"]["middle_m"][1]))
    shoot("eyes_cut_front", mid, (0, -1, 0), 0.11)
    shoot("eyes_cut_close", right, (0.25, -1, 0.1), 0.04, (900, 600))
    shoot("eyes_cut_side", right, (1, -0.35, 0), 0.05, (900, 600))
    grey = bpy.data.materials.new("eyeball")
    grey.diffuse_color = (0.85, 0.85, 0.85, 1)
    for side in ("right", "left"):
        fit = report[side]["eyeball_fit"]
        bpy.ops.mesh.primitive_uv_sphere_add(radius=fit["radius_mm"] / 1000, location=fit["centre_m"], segments=48, ring_count=24)
        bpy.context.object.data.materials.append(grey)
    scene.display.shading.color_type = "MATERIAL"
    skin.diffuse_color = (0.75, 0.55, 0.45, 1)
    shoot("eyes_stand_in_front", mid, (0, -1, 0), 0.11)
    shoot("eyes_stand_in_close", right, (0.25, -1, 0.1), 0.04, (900, 600))
