"""Spike check: does each joint stay inside its limb once a type is worn? At rest, for the knees and elbows, the joint
against the middle of the limb's cross-section through it, with the type's key off and on.

    blender -b build/wrap_<type>.blend -P spike_joints.py -- <type>
"""
import bpy, sys
import numpy as np
from mathutils import Vector

TYPE = sys.argv[sys.argv.index("--") + 1]
base, rig = bpy.data.objects["base"], bpy.data.objects["rig"]
for pb in rig.pose.bones:
    pb.rotation_euler = (0, 0, 0)
key = base.data.shape_keys.key_blocks[TYPE]
gi = {g.name: g.index for g in base.vertex_groups}


def group(name):
    i = gi[name]
    return np.array([any(g.group == i and g.weight > 0.3 for g in v.groups) for v in base.data.vertices])


for joint, upper, lower in (("LeftLeg", "LeftUpLeg", "LeftLeg"), ("RightLeg", "RightUpLeg", "RightLeg"),
                            ("LeftForeArm", "LeftArm", "LeftForeArm"), ("RightForeArm", "RightArm", "RightForeArm")):
    b = rig.data.bones["mixamorig:" + joint]
    head = rig.matrix_world @ b.head_local
    axis = (rig.matrix_world.to_3x3() @ (b.tail_local - b.head_local)).normalized()
    limb = group("mixamorig:" + upper) | group("mixamorig:" + lower)
    out = []
    for value in (0.0, 1.0):
        key.value = value
        bpy.context.view_layer.update()
        ev = base.evaluated_get(bpy.context.evaluated_depsgraph_get())
        co = np.array([base.matrix_world @ v.co for v in ev.data.vertices])
        h = np.array(head)
        along = (co - h) @ np.array(axis)
        ring = co[limb & (np.abs(along) < 0.012)]
        c = ring.mean(0)
        off = c - h
        off -= np.dot(off, axis) * np.array(axis)
        out.append("%s %.1f mm (x %.1f, y %.1f)" % ("off" if value == 0 else "on ", 1000 * np.linalg.norm(off), 1000 * off[0], 1000 * off[1]))
    print("JOINT %-12s centre of the limb from the joint: %s" % (joint, " | ".join(out)))
