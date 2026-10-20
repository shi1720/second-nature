"""Blender-side renderer. Atomic frames, persistent render data, baked scene."""
import bpy,sys,json,os,time
from pathlib import Path
job=json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text());s=bpy.context.scene
s.render.resolution_x=job['width'];s.render.resolution_y=job['height'];s.render.resolution_percentage=100
s.cycles.samples=job['samples'];s.render.use_persistent_data=True
p=bpy.context.preferences.addons['cycles'].preferences;device='CPU'
for typ in ['METAL','OPTIX','CUDA','HIP','ONEAPI']:
 try:
  p.compute_device_type=typ;p.get_devices();available=[d for d in p.devices if d.type==typ]
  if available:
   for d in p.devices:d.use=d.type==typ
   s.cycles.device='GPU';device=typ;break
 except (TypeError,RuntimeError):pass
print('DEVICE '+device,flush=True)
folder=Path(job['output_dir']);folder.mkdir(parents=True,exist_ok=True)
for count,f in enumerate(job['frames'],1):
 t=time.time();s.frame_set(f);temp=folder/('frame_%04d.partial.png'%f);dest=folder/('frame_%04d.png'%f)
 s.render.filepath=str(temp);bpy.ops.render.render(write_still=True);os.replace(temp,dest)
 print('FRAME_DONE '+json.dumps({'frame':f,'completed':count,'remaining':len(job['frames'])-count,'seconds':round(time.time()-t,2)}),flush=True)
