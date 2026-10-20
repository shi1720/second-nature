"""SECOND NATURE: deterministic procedural Blender film, no downloaded 3D assets.
Run through pipeline.py. Animation is baked into the saved .blend (no handlers).
"""
import bpy, math, random, json, sys, os
from mathutils import Vector, Quaternion
from pathlib import Path

TAU=math.tau
args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
config=json.loads(Path(args[0]).read_text()) if args else {}
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(config.get('output_dir',ROOT/'film')).resolve(); OUT.mkdir(parents=True,exist_ok=True)
SEED=int(config.get('seed',1720)); random.seed(SEED)
FPS=24; END=576

def linear(c): return ((c+0.055)/1.055)**2.4 if c>0.04045 else c/12.92

def rgb(h):
    h=h.lstrip('#');return tuple(linear(int(h[i:i+2],16)/255) for i in (0,2,4))

def mat(name,color,metal=0,rough=.35,emission=0,transmission=0):
    m=bpy.data.materials.new(name);m.diffuse_color=(*rgb(color),1);m.use_nodes=True
    p=m.node_tree.nodes.get('Principled BSDF');p.inputs['Base Color'].default_value=(*rgb(color),1)
    p.inputs['Metallic'].default_value=metal;p.inputs['Roughness'].default_value=rough
    p.inputs['Transmission Weight'].default_value=transmission
    p.inputs['Emission Color'].default_value=(*rgb(color),1);p.inputs['Emission Strength'].default_value=emission
    return m

bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
for block in bpy.data.materials: bpy.data.materials.remove(block)
S=bpy.context.scene;S.frame_start=1;S.frame_end=END;S.render.fps=FPS
S.render.engine='CYCLES';S.cycles.samples=32;S.cycles.use_denoising=True
S.cycles.use_adaptive_sampling=True;S.cycles.adaptive_threshold=.05
S.render.resolution_x=1920;S.render.resolution_y=1080;S.render.resolution_percentage=100
S.render.image_settings.file_format='PNG';S.render.film_transparent=False
S.render.use_motion_blur=True;S.render.motion_blur_shutter=.35
S.view_settings.view_transform='AgX';S.view_settings.look='AgX - Medium High Contrast';S.view_settings.exposure=-.55
S.render.image_settings.color_mode='RGB';S.render.image_settings.color_depth='8'
S.world.color=(.1,.1,.1);S.world.use_nodes=True
S.world.node_tree.nodes['Background'].inputs[0].default_value=(*rgb('#90b8be'),1)
S.world.node_tree.nodes['Background'].inputs[1].default_value=.22

teal=mat('01 | Midnight petrol enamel',config.get('accent_color','#154D58'),.38,.28)
dark=mat('02 | Deep blue ceramic','#071E29',.25,.32)
brass=mat('03 | Brushed champagne alloy','#CFA77C',.7,.26)
coral=mat('04 | Living amber',config.get('hero_color','#FF763E'),.27,.17,0,.18)
light=mat('05 | Cool luminous seam','#91F2DF',.1,.24,3)
warm=mat('06 | Amber luminous core','#FFD49B',.1,.19,2)
soil=mat('07 | Dry umber earth','#30251F',0,.9)
fissure=mat('07b | Recessed fissure','#100E0B',0,1)
ivory=mat('08 | Porcelain','#EFE3C7',.1,.27)
petalmat=mat('09 | Apricot silk','#EC8B60',.02,.48)
innerpetal=mat('09b | Inner apricot silk','#E78050',.02,.44)
pollenmat=mat('09c | Saffron pollen','#E3A641',.18,.52,.12)
heartmat=mat('09d | Burnished flower heart','#784529',.1,.6)
leafmat=mat('10 | Jade foliage','#4B9A77',.12,.32)
white=mat('11 | Typography','#F6EDDE',0,.5,1)
# Fine procedural material variation; all textures are node generated.
for m,scale,strength in [(soil,12,.22),(brass,180,.065),(petalmat,45,.08)]:
    nt=m.node_tree;n=nt.nodes.new('ShaderNodeTexNoise');n.inputs['Scale'].default_value=scale
    b=nt.nodes.new('ShaderNodeBump');b.inputs['Strength'].default_value=strength;b.inputs['Distance'].default_value=.06
    nt.links.new(n.outputs['Fac'],b.inputs['Height']);nt.links.new(b.outputs['Normal'],nt.nodes.get('Principled BSDF').inputs['Normal'])

def smooth(o):
    if hasattr(o.data,'polygons'):
        for p in o.data.polygons:p.use_smooth=True
    return o

def material(o,m):o.data.materials.append(m);return o

def bevel(o,w=.08,segments=3):
    mod=o.modifiers.new('Soft machined edges','BEVEL');mod.width=w;mod.segments=segments
    mod=o.modifiers.new('Weighted corner normals','WEIGHTED_NORMAL');return o

def cube(name,loc,scale,m,b=.06):
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc);o=bpy.context.object;o.name=name;o.dimensions=scale
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);material(o,m)
    if b:bevel(o,b)
    return o

def uv(name,loc,scale,m,segments=48):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments,ring_count=24,location=loc);o=bpy.context.object;o.name=name;o.scale=scale;material(o,m);smooth(o);return o

def cyl(name,loc,r,depth,m,vertices=96):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices,radius=r,depth=depth,location=loc);o=bpy.context.object;o.name=name;material(o,m);bevel(o,.035,3);smooth(o);return o

def curve(name,pts,r,m,cyclic=False):
    c=bpy.data.curves.new(name,'CURVE');c.dimensions='3D';c.resolution_u=16;c.bevel_depth=r;c.bevel_resolution=4
    p=c.splines.new('POLY');p.points.add(len(pts)-1)
    for a,v in zip(p.points,pts):a.co=(*v,1)
    p.use_cyclic_u=cyclic;o=bpy.data.objects.new(name,c);bpy.context.collection.objects.link(o);material(o,m);return o

def torus(name,loc,major,minor,m,rot=(0,0,0)):
    bpy.ops.mesh.primitive_torus_add(major_segments=96,minor_segments=12,location=loc,major_radius=major,minor_radius=minor,rotation=rot)
    o=bpy.context.object;o.name=name;material(o,m);smooth(o);return o

def empty(name,loc=(0,0,0)):
    o=bpy.data.objects.new(name,None);bpy.context.collection.objects.link(o);o.location=loc;return o

def parent(o,p):o.parent=p;return o

def clamp(x):return max(0,min(1,x))
def ease(x):x=clamp(x);return x*x*(3-2*x)
def lerp(a,b,t):return a+(b-a)*t

def text(name,body,loc,size,m,rot=(0,0,0),align='CENTER'):
    c=bpy.data.curves.new(name,'FONT');c.body=body;c.align_x=align;c.size=size;c.extrude=.001;c.space_character=1.15
    font=ROOT/'assets/fonts/SpaceGrotesk.ttf'
    if font.exists():c.font=bpy.data.fonts.load(str(font),check_existing=True)
    o=bpy.data.objects.new(name,c);bpy.context.collection.objects.link(o);o.location=loc;o.rotation_euler=rot;material(o,m);return o

# One sculptural installation, rather than separate disconnected backgrounds.
cube('Infinite studio floor',(0,0,-1.22),(200,200,.3),dark,.15)
cube('Floating architectural plinth',(-3,0,-.55),(51,12,.85),teal,.32)
cube('Champagne lower reveal',(-3,0,-.94),(50.6,11.6,.1),brass,.04)
# Stations and floor-line graphic rhythm.
for x in range(-26,22,2):
    cube('Recessed luminous floor dash',(x,-4.7,-.1),(.65,.028,.012),light,.01)
    cube('Fine engraved crossbar',(x,4.3,-.1),(.025,.45,.015),brass,.005)
for x in [-24,-18,-12,-6,1,7,13]:
    cyl('Fluted track support',(x,0,.18),.27,.55,brass,32)
    cube('Support foot',(x,0,-.04),(1.1,1.3,.15),dark)

# twin horizontal rails, loop, and rising final glide.
for yy in [-.34,.34]:
    curve('Launch twin rail',[(-26+i*.2,yy,.65) for i in range(111)],.11,brass)
    curve('Full vertical loop rail',[(-4+3*math.cos(-math.pi/2+i*TAU/240),yy,3.65+3*math.sin(-math.pi/2+i*TAU/240)) for i in range(241)],.11,brass)
    curve('Final rising twin rail',[(-4+i*.1,yy,.65+2.5*ease((i*.1)/20)) for i in range(201)],.11,brass)
curve('Launch energy seam',[(-26+i*.2,0,.62) for i in range(111)],.035,light)
curve('Loop energy seam',[(-4+3*math.cos(-math.pi/2+i*TAU/240),0,3.65+3*math.sin(-math.pi/2+i*TAU/240)) for i in range(241)],.035,light)
curve('Final energy seam',[(-4+i*.1,0,.62+2.5*ease(i/200)) for i in range(201)],.035,light)
# Loop support arcs in dark metal and fine brass ribs.
for yy in [-.68,.68]:
    curve('Structural halo',[(-4+3.3*math.cos(i*TAU/192),yy,3.65+3.3*math.sin(i*TAU/192)) for i in range(193)],.12,teal)
    for i in range(0,48):
        a=i*TAU/48
        curve('Halo calibration tick',[(-4+r*math.cos(a),yy,3.65+r*math.sin(a)) for r in [3.16,3.38]],.018,brass)
for x in [-21,-17,-13,-9]:
    for side in [-1,1]:
        cube('Accelerator pedestal',(x,side*1.5,.45),(.5,.6,1.1),dark)
    torus('Accelerator brass gate',(x,0,1.3),1.22,.095,brass,(0,math.pi/2,0))
    torus('Accelerator illuminated ring',(x+.06,0,1.3),1.1,.027,light,(0,math.pi/2,0))
    # fan fins around gates, the layers rotate independently.
    for a in range(8):
        ang=a*TAU/8
        o=cube('Gate radial fin',(x,1.44*math.sin(ang),1.3+1.44*math.cos(ang)),(.48,.19,.5),teal,.045)
        o.rotation_euler[0]=-ang

# Destination: a large machined planter, dry soil, a visibly waiting seed.
PX=17.0
cyl('Destination lower foot',(PX,0,.08),1.7,.35,brass)
cyl('Destination porcelain vessel',(PX,0,.38),1.48,.65,ivory)
torus('Vessel upper brass lip',(PX,0,.72),1.43,.07,brass)
cyl('Dry soil surface',(PX,0,.71),1.35,.08,soil)
for i in range(42):
    a=random.random()*TAU;r=math.sqrt(random.random())*1.22
    uv('Clay granule',(PX+r*math.cos(a),r*math.sin(a),.77),(random.uniform(.03,.1),random.uniform(.04,.09),.035),soil,16)
# Four angular cracks read as dry earth in the opening close-up.
for i in range(8):
    a=i*TAU/8+.2
    pts=[]
    for j in range(5):
        r=.35+j*.21; aa=a+random.uniform(-.12,.12);pts.append((PX+r*math.cos(aa),r*math.sin(aa),.747))
    curve('Dry earth fissure',pts,.012,fissure)
seed=uv('Waiting seed',(PX,0,.89),(.28,.17,.13),brass)
seed.rotation_euler=(.2,.15,.4)
curve('Seed central seam',[(PX-.24+i*.016,.005,.92+.095*math.sin(i*math.pi/30)) for i in range(31)],.012,dark)
for i in range(56):
    a=i*TAU/56;c=cube('Planter fluting',(PX+1.484*math.cos(a),1.484*math.sin(a),.35),(.018,.018,.44),brass,.008)
text('Destination label','N A T U R E',(PX,-1.506,.39),.16,dark,(math.pi/2,0,0))
# Decorative circular brass landing rim suspended above pot.
torus('Arrival halo',(PX,0,3.15),.95,.065,brass)
for a in [0,TAU/3,2*TAU/3]:
    curve('Arrival halo support',[(PX+1.7*math.cos(a),1.7*math.sin(a),.2),(PX+1.7*math.cos(a),1.7*math.sin(a),2.9),(PX+.97*math.cos(a),.97*math.sin(a),3.15)],.045,teal)

# Hero is a modeled liquid drop with a tiny luminous nucleus.
hero=empty('HERO | one precious drop')
verts=[];faces=[];N=64;R=32
for j in range(R+1):
    theta=j*math.pi/R
    z=.56*math.cos(theta)
    rad=.43*math.sin(theta)*(1-.37*max(math.cos(theta),0))
    # a small pulled tip is part of the silhouette.
    if j==0:z=.82
    for i in range(N):a=i*TAU/N;verts.append((rad*math.cos(a),rad*math.sin(a),z))
for j in range(R):
    for i in range(N):a=j*N+i;b=j*N+(i+1)%N;faces.append((a,b,b+N,a+N))
mesh=bpy.data.meshes.new('Analytic droplet surface');mesh.from_pydata(verts,[],faces);mesh.update()
drop=bpy.data.objects.new('Amber water envelope',mesh);bpy.context.collection.objects.link(drop);material(drop,coral);smooth(drop);parent(drop,hero)
parent(uv('Drop luminous nucleus',(0,0,-.08),(.19,.19,.23),warm),hero)
# Petal mesh is a curled, tapered spoon. Separate whorls unfurl with offsets.
def petal_mesh(name,length,width,m):
    v=[];f=[];rows=22;cols=10
    for j in range(rows+1):
        t=j/rows
        for k in range(cols+1):
            u=2*k/cols-1
            w=width*(math.sin(math.pi*t)**.7)*(.65+.35*t)
            v.append((length*t,w*u,.18*math.sin(math.pi*t)-.18*t*t+.15*u*u*math.sin(math.pi*t)))
    for j in range(rows):
        for k in range(cols):
            a=j*(cols+1)+k;f.append((a,a+1,a+cols+2,a+cols+1))
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(v,[],f);mesh.update();o=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(o);material(o,m);smooth(o)
    mod=o.modifiers.new('Silk petal thickness','SOLIDIFY');mod.thickness=.022
    mod=o.modifiers.new('Petal softness','SUBSURF');mod.levels=1;return o

flower=empty('FLOWER | growth rig',(PX,0,.8))
stem=parent(cyl('Living stem',(0,0,1.25),.052,2.5,leafmat,24),flower)
petals=[]
for layer,(count,length,width,height) in enumerate([(13,1.55,.42,2.45),(10,1.22,.39,2.53),(7,.9,.32,2.60)]):
    for i in range(count):
        rig=parent(empty('Petal hinge L%d.%02d'%(layer,i),(0,0,height)),flower)
        rig.rotation_euler[2]=i*TAU/count+layer*.24
        petal=parent(petal_mesh('Apricot petal L%d.%02d'%(layer,i),length,width,petalmat if layer<2 else innerpetal),rig)
        petals.append((rig,petal,layer,i,count))
center=parent(uv('Flower golden heart',(0,0,2.58),(.39,.39,.2),heartmat),flower)
florets=[]
for i in range(100):
    a=i*2.39996323;r=.34*math.sqrt((i+.5)/100)
    o=parent(uv('Fibonacci pollen',(r*math.cos(a),r*math.sin(a),2.63+.14*math.sqrt(1-(r/.37)**2)),(.032,.032,.05),pollenmat,12),flower);florets.append(o)
leaves=[]
for j in range(3):
    rig=parent(empty('Leaf hinge',(0,0,.7+j*.45)),flower);rig.rotation_euler[2]=j*2.4+.5
    leaf=parent(petal_mesh('Jade leaf',.95,.24,leafmat),rig);leaves.append((rig,leaf,j))
# radial ripple rings on impact, analytically expanded and faded via size.
ripples=[]
for i in range(3):ripples.append(torus('Impact ripple %d'%i,(PX,0,.82),.4,.013,light))
# Filaments trailing behind the one drop, not independent story objects.
trail=[]
for i in range(25):
    o=uv('Speed wake %02d'%i,(0,0,0),(.07,.07,.07),warm,12);trail.append(o)

# Minimal architectural inscriptions (part of the 3D set).
text('Launch floor inscription','01  /  RELEASE',(-23,-2,-.098),.35,ivory)
text('Loop floor inscription','02  /  ACCELERATE',(-4,2.8,-.098),.29,ivory)
text('Arrival floor inscription','03  /  GROW',(11,-2,-.098),.35,ivory)
for x in range(-24,16,1):
    # moving-light travel measured against repeated static geometry.
    cube('Track timing tick',(x,-.82,.66 if x<-4 else .66+2.5*ease((x+4)/20)),(.025,.2,.035),ivory,.008)

# Lighting: large physical softboxes give clean gradients and metallic shape.
def area(name,loc,power,color,size,target):
    d=bpy.data.lights.new(name,'AREA');d.energy=power;d.color=rgb(color);d.shape='DISK';d.size=size
    o=bpy.data.objects.new(name,d);bpy.context.collection.objects.link(o);o.location=loc;o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler();return o
area('Key | long warmbox',(0,-6,13),5200,'#FFE1BC',14,(0,0,0))
area('Rim | cool softbox',(-7,5,9),6500,'#85DBE1',12,(-5,0,2))
area('Launch | coral rim',(-24,-2,6),1700,'#FFB488',7,(-20,0,1))
area('Garden | warm key',(18,-4,9),1400,'#FFE4C4',6,(17,0,2))
area('Garden | turquoise edge',(21,4,7),1700,'#91E4D7',5,(17,0,2))

bpy.ops.object.camera_add();cam=bpy.context.object;cam.name='CAMERA | five editorial shots';S.camera=cam
cam.data.lens=48;cam.data.clip_end=500;cam.data.dof.use_dof=True
focus=empty('Camera focus target');cam.data.dof.focus_object=focus;cam.data.dof.aperture_fstop=5.6
# in-camera title cards are added during lossless assembly for exact pixel typography.

def path(f):
    if f<49:return Vector((-24,0,1.3))
    if f<=144:
        t=(f-49)/95;return Vector((lerp(-24,-4,t**1.35),0,1.3))
    if f<=264:
        t=(f-144)/120;a=-math.pi/2+2*TAU*(t**1.2)
        return Vector((-4+3*math.cos(a),0,3.65+3*math.sin(a)+.65))
    if f<=330:
        t=ease((f-264)/66);return Vector((lerp(-4,PX,t),0,1.3+2.8*t))
    if f<=348:return Vector((PX,0,4.1+.04*math.sin((f-330)*.18)))
    if f<=366:
        t=((f-348)/18)**2;return Vector((PX,0,lerp(4.1,1.08,t)))
    return Vector((PX,0,1.08))

# Bake every animated value: saved file plays without Python autorun.
for f in range(1,END+1):
    S.frame_set(f);pos=path(f);hero.location=pos
    vel=(path(min(END,f+1))-path(max(1,f-1))).normalized()
    hero.rotation_mode='QUATERNION'
    if 49<=f<=342:
        q=vel.to_track_quat('Z','Y') if f<318 else Vector((1,0,0)).to_track_quat('Z','Y')
        braking=ease((f-318)/24)
        hero.rotation_quaternion=q.slerp(Quaternion((1,0,0,0)),braking)
        hero.scale=(lerp(.8,1,braking),lerp(.8,1,braking),lerp(1.28,1,braking))
    elif f<367:hero.rotation_quaternion=(1,0,0,0);hero.scale=(1,1,1)
    else:hero.scale=(.001,.001,.001)
    if f<49:hero.scale=(.001,)*3
    for prop in ['location','rotation_quaternion','scale']:hero.keyframe_insert(prop,frame=f)
    # staged growth with an actual stem extending before petals unfold.
    growth=ease((f-366)/70);flower.scale=(max(.001,growth),max(.001,growth),max(.001,growth));flower.keyframe_insert('scale',frame=f)
    for rig,o,l,i,count in petals:
        opening=ease((f-(392+l*9+i*1.0))/(66-l*5))
        rig.rotation_euler[1]=lerp(-1.48,-.06+l*.15,opening)
        # small overshoot carries organic settling, staggered per whorl.
        rig.rotation_euler[1]+=.07*math.sin((f-400)*.09+i*.4)*opening*math.exp(-max(0,f-435)/50)
        rig.keyframe_insert('rotation_euler',frame=f)
        o.scale=(max(.02,opening),max(.035,opening),1);o.keyframe_insert('scale',frame=f)
    for rig,o,j in leaves:
        op=ease((f-378-j*7)/65);rig.rotation_euler[1]=lerp(-1.4,-.25,op);rig.keyframe_insert('rotation_euler',frame=f)
    seed.scale=(.28,.17,.13) if f<366 else (.28*(1-ease((f-366)/30)),.17*(1-ease((f-366)/30)),.13*(1-ease((f-366)/30)))
    seed.keyframe_insert('scale',frame=f)
    for i,o in enumerate(ripples):
        t=(f-366-i*5)/24
        o.scale=(.001,)*3 if t<=0 or t>=1 else (1+2*t,1+2*t,math.sin(math.pi*t))
        o.keyframe_insert('scale',frame=f)
    for i,o in enumerate(trail):
        o.location=path(max(49,f-(i+1)*.55))
        active=49<=f<=329
        size=.075*(1-i/27) if active else .001
        o.scale=(size,size,size);o.keyframe_insert('location',frame=f);o.keyframe_insert('scale',frame=f)
    # Shot 1: intimate stakes. Shot 2: chase. Shot 3: full loop.
    # Shot 4: braking, held drop and impact. Shot 5: unfolding life, title space.
    if f<=48:
        t=ease((f-1)/47);loc=(PX+2.9-.3*t,-4.6+.4*t,3.3-.25*t);target=(PX,0,.91);lens=62;ap=5.6
    elif f<=144:
        t=(f-49)/95;loc=(pos.x-3.9,-6.8,3.4);target=(pos.x+.8,0,1.3);lens=46;ap=5.6
    elif f<=264:
        t=ease((f-145)/119);loc=(-9+1.5*t,-17,7.5-.5*t);target=(-4,0,3.7);lens=40;ap=8
    elif f<=366:
        t=ease((f-265)/101)
        blend=ease((f-294)/36)
        loc=(lerp(pos.x+4.7,PX+4.7,blend),lerp(-7.7,-9.5,blend),lerp(5.5,6.2,blend))
        target=(lerp(pos.x+.2,PX,blend),0,lerp(pos.z-.25,2.55,blend))
        lens=48;ap=7.1
    else:
        t=ease((f-367)/209);loc=(PX+5.2+2*t,-8.2-3*t,5.6+.7*t);target=(PX-.55-.5*t,0,2.05);lens=52;ap=8
    cam.location=loc;cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.lens=lens
    focus.location=target;cam.data.dof.aperture_fstop=ap
    for prop in ['location','rotation_euler']:cam.keyframe_insert(prop,frame=f)
    cam.data.keyframe_insert('lens',frame=f);cam.data.dof.keyframe_insert('aperture_fstop',frame=f);focus.keyframe_insert('location',frame=f)


# Independent shot cameras hold their own boundary poses during shutter sampling.
def trim_action(owner,first,last):
    if owner.animation_data and owner.animation_data.action:
        owner.animation_data.action=owner.animation_data.action.copy()
        for fc in owner.animation_data.action.fcurves:
            for idx in reversed(range(len(fc.keyframe_points))):
                k=fc.keyframe_points[idx]
                if k.co.x<first or k.co.x>last:fc.keyframe_points.remove(k,fast=True)
            fc.update()
for i,(first,last) in enumerate([(1,48),(49,144),(145,264),(265,366),(367,576)],1):
    shot=cam.copy();shot.data=cam.data.copy();bpy.context.collection.objects.link(shot);shot.name='SHOT %02d | camera'%i
    target=focus.copy();bpy.context.collection.objects.link(target);target.name='SHOT %02d | focus'%i
    trim_action(shot,first,last);trim_action(shot.data,first,last);trim_action(target,first,last)
    shot.data.dof.focus_object=target
    marker=S.timeline_markers.new('SHOT %02d'%i,frame=first);marker.camera=shot
    if i==1:S.camera=shot
bpy.data.objects.remove(cam,do_unlink=True);bpy.data.objects.remove(focus,do_unlink=True)

# Linear baked animation eliminates interpolation drift and out-of-order rendering differences.
for o in bpy.data.objects:
    if o.animation_data and o.animation_data.action:
        for fc in o.animation_data.action.fcurves:
            for k in fc.keyframe_points:k.interpolation='LINEAR'
S.use_nodes=True;tree=S.node_tree;tree.nodes.clear()
r=tree.nodes.new('CompositorNodeRLayers');g=tree.nodes.new('CompositorNodeGlare');g.glare_type='FOG_GLOW';g.quality='HIGH';g.threshold=2;g.size=7
out=tree.nodes.new('CompositorNodeComposite');tree.links.new(r.outputs['Image'],g.inputs['Image']);tree.links.new(g.outputs['Image'],out.inputs[0])
S['film']='SECOND NATURE';S['entrant']='Shivam Gupta';S['seed']=SEED;S['duration_seconds']=24
S['workflow']='Original procedural bpy meshes, deterministic baked motion, scripted petals and camera, original synthetic score. AI-assisted code and production.'
S.render.filepath=str(OUT/'frames'/'frame_');S.frame_set(430)
# An intentionally composed startup viewport provides useful source evidence.
for a in bpy.context.screen.areas:
    if a.type=='VIEW_3D':a.spaces.active.region_3d.view_perspective='CAMERA'
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'second-nature.blend'))
print('BUILD_COMPLETE',json.dumps({'objects':len(bpy.data.objects),'frames':END,'output':str(OUT)}))
