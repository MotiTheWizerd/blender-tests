"""The AI guard's material as iron: Hunyuan's GLB came with metallic 0 / roughness 1 (chalk).
Its painted texture stays (scales, red eyes); darkened toward the reference's black iron and made metal."""
import bpy
m = bpy.data.objects["Guard_AI"].data.materials[0]
m.name = "DragonAI"
nt = m.node_tree; b = nt.nodes["Principled BSDF"]
tex = next(n for n in nt.nodes if n.type == "TEX_IMAGE")
mul = nt.nodes.get("darken") or nt.nodes.new("ShaderNodeMix")
mul.name = "darken"; mul.data_type = "RGBA"; mul.blend_type = "MULTIPLY"
mul.inputs["Factor"].default_value = 1.0
mul.inputs["B"].default_value = (0.5, 0.5, 0.52, 1)
nt.links.new(tex.outputs["Color"], mul.inputs["A"])
nt.links.new(mul.outputs["Result"], b.inputs["Base Color"])
b.inputs["Metallic"].default_value = 0.85
b.inputs["Roughness"].default_value = 0.42
print("iron:", m.name)
