"""Watch a creature's clips in Blender: every clip in a row, playing, the creature framed. Changes nothing on disk.

    blender ai_models/<name>/build/<name>_anim.blend -P ai_models/watch.py

Idle first, then the rest by name, each repeated to at least 4 s; the timeline's markers name the clip playing.
Space stops and starts; to see one clip alone, pick it in the Action Editor.
"""
import bpy, math
from mathutils import Vector

scene = bpy.context.scene
rig = next(o for o in scene.objects if o.type == "ARMATURE")
body = next(o for o in scene.objects if o.type == "MESH")
actions = sorted((a for a in bpy.data.actions if a.use_fake_user), key=lambda a: (a.name != "Idle", a.name))

rig.animation_data.action = None
track = rig.animation_data.nla_tracks.new()
track.name = "clips"
scene.timeline_markers.clear()
start = 1
for action in actions:
    length = action.frame_range[1] - action.frame_range[0]
    strip = track.strips.new(action.name, int(start), action)
    strip.repeat = max(1, math.ceil(4 * scene.render.fps / length))
    scene.timeline_markers.new(action.name, frame=int(start))
    start = strip.frame_end
scene.frame_start, scene.frame_end, scene.frame_current = 1, int(start) - 1, 1
scene.sync_mode = "FRAME_DROP"          # real time, frames dropped if need be
rig.hide_set(True)                      # the skin only (the skeleton still drives it)


def show():
    window = bpy.context.window_manager.windows[0]
    area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
    space = area.spaces.active
    space.shading.type = "MATERIAL"
    space.overlay.show_floor = True
    r3d = space.region_3d
    size = max(body.dimensions)
    r3d.view_location = Vector((0, 0, body.dimensions.z * 0.7))       # the source frame stands on z = 0
    r3d.view_rotation = Vector((0.9, -1.0, 0.35)).normalized().to_track_quat("Z", "Y")
    r3d.view_distance = size * 2.2                                     # room for a take-off's climb
    r3d.view_perspective = "PERSP"
    with bpy.context.temp_override(window=window, area=area):
        bpy.ops.screen.animation_play()
    print("WATCH", ", ".join(f"{a.name} x{s.repeat:g}" for a, s in zip(actions, track.strips)))
    return None


bpy.app.timers.register(show, first_interval=1.0)
