import bpy,sys,os,math
from mathutils import Vector
fbx,tex,out=sys.argv[sys.argv.index('--')+1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=fbx)
sc=bpy.context.scene
objs=[o for o in sc.objects if o.type=='MESH' and not o.name.endswith('_COL')]
for o in sc.objects:
    if o.name.endswith('_COL'): o.hide_render=True
m=bpy.data.materials.new('m'); nt=m.node_tree; b=nt.nodes['Principled BSDF']
def img(p,nc=False):
    if not os.path.exists(p): return None
    n=nt.nodes.new('ShaderNodeTexImage'); n.image=bpy.data.images.load(p)
    if nc: n.image.colorspace_settings.name='Non-Color'
    return n
c=img(tex+'_BaseColor.png')
if c:
    nt.links.new(c.outputs['Color'],b.inputs['Base Color'])
    if os.path.exists(tex+'_Alpha.png'):
        a=img(tex+'_Alpha.png',True); nt.links.new(a.outputs['Color'],b.inputs['Alpha'])
    elif c.image.channels==4: nt.links.new(c.outputs['Alpha'],b.inputs['Alpha'])
nrm=img(tex+'_Normal.png',True)
if nrm:
    nm=nt.nodes.new('ShaderNodeNormalMap'); nt.links.new(nrm.outputs['Color'],nm.inputs['Color']); nt.links.new(nm.outputs['Normal'],b.inputs['Normal'])
b.inputs['Roughness'].default_value=0.8
for o in objs:
    o.data.materials.clear(); o.data.materials.append(m)
pts=[o.matrix_world@Vector(cc) for o in objs for cc in o.bound_box]
mn=Vector([min(p[i] for p in pts) for i in range(3)]); mx=Vector([max(p[i] for p in pts) for i in range(3)])
ctr=(mn+mx)/2; size=(mx-mn).length
cd=bpy.data.cameras.new('c'); cd.lens=50; cam=bpy.data.objects.new('c',cd); sc.collection.objects.link(cam); sc.camera=cam
d=Vector((0.8,-1.6,0.7)).normalized()*size*1.35
cam.location=ctr+d; cam.rotation_euler=(ctr-cam.location).to_track_quat('-Z','Y').to_euler()
ld=bpy.data.lights.new('s','SUN'); ld.energy=3.5; lo=bpy.data.objects.new('s',ld); sc.collection.objects.link(lo); lo.rotation_euler=(math.radians(45),0,math.radians(30))
w=bpy.data.worlds.new('w'); sc.world=w; w.color=(0.35,0.4,0.48)
sc.render.engine='BLENDER_EEVEE'; sc.render.resolution_x=sc.render.resolution_y=400; sc.render.filepath=out
bpy.ops.render.render(write_still=True)
