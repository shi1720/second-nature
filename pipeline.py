#!/usr/bin/env python3
"""Deterministic, resumable Blender film production. No cloud credentials needed."""
import argparse, contextlib, hashlib, json, os, re, shutil, signal, struct, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
VERSION='1.0.0'; FRAMES=576;FPS=24
PROFILES={'preview':{'width':960,'height':540,'samples':16},'final':{'width':1920,'height':1080,'samples':48}}

def emit(event,**data): print(json.dumps({'event':event,**data}),flush=True)
def atomic_json(path,data):
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(data,indent=2)+'\n');tmp.replace(path)
def digest(data):return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def settings(config):return {k:config[k] for k in ['seed','hero_color','accent_color']}
def file_hash(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def renderer_hash():return file_hash(ROOT/'source/render.py')
def source_hash():return hashlib.sha256((ROOT/'source/scene.py').read_bytes()).hexdigest()
def load_config(path):
    c=json.loads(Path(path).read_text())
    if not isinstance(c,dict):raise ValueError('Configuration must be a JSON object')
    c={'name':'SECOND NATURE','seed':1720,'hero_color':'#FF763E','accent_color':'#154D58',**c}
    if isinstance(c['seed'],bool) or not isinstance(c['seed'],int) or not 0<=c['seed']<=2147483647:raise ValueError('Seed must be an integer between 0 and 2147483647')
    for k in ['hero_color','accent_color']:
        if not isinstance(c[k],str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',c[k]):raise ValueError(k+' must be a six-digit hexadecimal color')
    if not isinstance(c.get('name'),str) or len(c['name'])>100:raise ValueError('Project name must be text under 100 characters')
    output=c.get('output_dir',str(ROOT/'film'))
    if not isinstance(output,str) or not output.strip():raise ValueError('output_dir must be a nonempty path string')
    c['output_dir']=str(Path(output).expanduser().resolve());return c

def blender_bin(explicit=None):
    candidates=[explicit,os.getenv('BLENDER_BIN'),shutil.which('blender'),'/Applications/Blender.app/Contents/MacOS/Blender']
    # The portable workstation fallback is optional. Containers can place this
    # project at /app, which has only one ancestor; do not index beyond it.
    if len(ROOT.parents)>1:candidates.append(str(ROOT.parents[1]/'work/tools/Blender.app/Contents/MacOS/Blender'))
    for p in candidates:
        if p and Path(p).is_file():return str(Path(p).resolve())
    raise RuntimeError('Blender 4.5 LTS is required. Install Blender and set BLENDER_BIN to its executable.')

@contextlib.contextmanager
def lock(out):
    out.mkdir(parents=True,exist_ok=True);p=out/'.pipeline.lock'
    for attempt in range(2):
        try:
            fd=os.open(str(p),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.write(fd,str(os.getpid()).encode());os.close(fd);break
        except FileExistsError:
            try:pid=int(p.read_text());os.kill(pid,0)
            except (ValueError,ProcessLookupError):p.unlink(missing_ok=True);continue
            raise RuntimeError('Another pipeline operation is running for this project')
    else:raise RuntimeError('Could not acquire project lock')
    try:yield
    finally:p.unlink(missing_ok=True)

def run(cmd,log=None):
    emit('command',argv=[str(x) for x in cmd])
    proc=subprocess.Popen([str(x) for x in cmd],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1,start_new_session=(os.name!='nt'))
    previous={}
    def stop(sig,frame):
        if proc.poll() is None:
            if os.name!='nt':os.killpg(proc.pid,signal.SIGTERM)
            else:proc.terminate()
        raise KeyboardInterrupt
    for sig in [signal.SIGINT,signal.SIGTERM]:previous[sig]=signal.signal(sig,stop)
    stream=open(log,'a') if log else None
    try:
        for line in proc.stdout:
            if stream:stream.write(line);stream.flush()
            # Blender emits detailed logs to disk, compact progress to the studio.
            if line.startswith(('FRAME_DONE ','DEVICE ','BUILD_COMPLETE','Error:','Traceback')):print(line.rstrip(),flush=True)
        code=proc.wait()
        if code:raise RuntimeError('Command failed with exit code %d; see %s'%(code,log or 'console'))
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:proc.wait(timeout=10)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
        if stream:stream.close()
        for sig,handler in previous.items():signal.signal(sig,handler)

def png_size(path):
    try:
        with open(path,'rb') as f:head=f.read(24)
        if len(head)!=24 or head[:8]!=b'\x89PNG\r\n\x1a\n':return None
        return struct.unpack('>II',head[16:24])
    except OSError:return None

def valid_png(path,size):
    if png_size(path)!=tuple(size):return False
    # Verify chunk CRCs so a crash-truncated PNG cannot count as a finished frame.
    import zlib
    try:
        with open(path,'rb') as f:
            f.read(8)
            while True:
                n=f.read(4)
                if len(n)!=4:return False
                length=struct.unpack('>I',n)[0]
                if length>128*1024*1024:return False
                typ=f.read(4);data=f.read(length);crc=f.read(4)
                if len(crc)!=4 or len(data)!=length or zlib.crc32(typ+data)&0xffffffff!=struct.unpack('>I',crc)[0]:return False
                if typ==b'IEND':return True
    except OSError:return False

def build(c,exe):
    out=Path(c['output_dir']);atomic_json(out/'resolved-config.json',c)
    run([exe,'--background','--factory-startup','--python-exit-code','1','--python',ROOT/'source/scene.py','--',out/'resolved-config.json'],out/'build.log')
    blend=out/'second-nature.blend'
    if not blend.exists() or blend.stat().st_size<10000:raise RuntimeError('Blender did not create the project file')
    atomic_json(out/'build-manifest.json',{'version':VERSION,'source_sha256':source_hash(),'settings':settings(c),'settings_sha256':digest(settings(c)),'frames':FRAMES,'fps':FPS,'blend_sha256':file_hash(blend),'built_at':time.time()})
    emit('build_complete',file=str(blend))

def assert_build(c):
    out=Path(c['output_dir']);p=out/'build-manifest.json'
    if not p.exists():raise RuntimeError('Build this configuration before rendering')
    manifest=json.loads(p.read_text())
    if manifest['settings_sha256']!=digest(settings(c)) or manifest['source_sha256']!=source_hash():raise RuntimeError('Configuration or scene source changed. Rebuild before rendering.')
    if not (out/'second-nature.blend').exists():raise RuntimeError('Blender project is missing. Rebuild first.')
    if manifest.get('blend_sha256')!=file_hash(out/'second-nature.blend'):raise RuntimeError('Saved Blender project changed. Rebuild before resuming this deterministic render.')
    return manifest

def render_identity(c,manifest,pr):
    return digest({'build':manifest['settings_sha256'],'source':source_hash(),'blend':manifest['blend_sha256'],'renderer':renderer_hash(),'profile':pr})

def check_render_state(c,manifest,state):
    if state.get('profile') not in PROFILES:raise RuntimeError('Unknown render profile in state')
    pr=PROFILES[state['profile']]
    if state.get('fingerprint')!=render_identity(c,manifest,pr):raise RuntimeError('Frame configuration is stale. Render again before assembly or verification.')
    if [state.get('width'),state.get('height'),state.get('samples')]!=[pr['width'],pr['height'],pr['samples']]:raise RuntimeError('Render state dimensions are inconsistent')
    return pr

def render(c,exe,profile,start=1,end=FRAMES):
    manifest=assert_build(c);out=Path(c['output_dir']);pr=PROFILES[profile]
    fingerprint=render_identity(c,manifest,pr)
    state=out/'render-state.json';folder=out/'frames'
    if state.exists():
        old=json.loads(state.read_text())
        if old['fingerprint']!=fingerprint and folder.exists():
            archive=out/('frames-'+old.get('profile','old')+'-'+old['fingerprint'][:10])
            if archive.exists():shutil.rmtree(archive)
            folder.rename(archive)
    elif folder.exists() and any(folder.iterdir()):raise RuntimeError('Untracked frames exist. Move them aside or restore render-state.json before rendering.')
    folder.mkdir(exist_ok=True)
    atomic_json(state,{'fingerprint':fingerprint,'profile':profile,**pr,'fps':FPS,'frames':FRAMES})
    size=(pr['width'],pr['height']);missing=[f for f in range(start,end+1) if not valid_png(folder/('frame_%04d.png'%f),size)]
    emit('render_start',profile=profile,remaining=len(missing),total=FRAMES)
    if missing:
        job={**pr,'frames':missing,'output_dir':str(folder)};atomic_json(out/'render-job.json',job)
        run([exe,'--background',out/'second-nature.blend','--python-exit-code','1','--python',ROOT/'source/render.py','--',out/'render-job.json'],out/'render.log')
    broken=[f for f in range(start,end+1) if not valid_png(folder/('frame_%04d.png'%f),size)]
    if broken:raise RuntimeError('Missing or corrupt frames: '+str(broken[:12]))
    emit('render_complete',range=[start,end],profile=profile)

def assemble(c):
    out=Path(c['output_dir']);manifest=assert_build(c)
    statepath=out/'render-state.json'
    if not statepath.exists():raise RuntimeError('Render the project before assembly')
    state=json.loads(statepath.read_text());pr=check_render_state(c,manifest,state)
    size=[state['width'],state['height']]
    missing=[f for f in range(1,FRAMES+1) if not valid_png(out/'frames'/('frame_%04d.png'%f),size)]
    if missing:raise RuntimeError('Assembly requires all 576 intact frames. Missing: '+str(missing[:12]))
    ffmpeg=shutil.which('ffmpeg')
    if not ffmpeg:raise RuntimeError('FFmpeg is required for audio/video assembly')
    run([sys.executable,ROOT/'source/finish.py',out,ffmpeg],out/'assembly.log')
    movie=out/'second-nature.mp4'
    emit('assembly_complete',file=str(movie))

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['build','render','assemble','all','verify']);p.add_argument('--config',default=str(ROOT/'project.json'));p.add_argument('--blender');p.add_argument('--profile',choices=PROFILES,default='final');p.add_argument('--start',type=int,default=1);p.add_argument('--end',type=int,default=FRAMES)
    a=p.parse_args(argv)
    if not 1<=a.start<=a.end<=FRAMES:p.error('Frame range must fall between 1 and 576')
    try:
        c=load_config(a.config);out=Path(c['output_dir'])
        with lock(out):
            if a.command in ['build','all']:build(c,blender_bin(a.blender))
            if a.command in ['render','all']:render(c,blender_bin(a.blender),a.profile,a.start,a.end)
            if a.command in ['assemble','all']:assemble(c)
            if a.command=='verify':
                manifest=assert_build(c);state=json.loads((out/'render-state.json').read_text());check_render_state(c,manifest,state);bad=[f for f in range(1,577) if not valid_png(out/'frames'/('frame_%04d.png'%f),(state['width'],state['height']))]
                if bad:raise RuntimeError('Incomplete sequence: %d missing/corrupt frames'%len(bad))
                emit('verified',frames=576,width=state['width'],height=state['height'],duration=24)
        return 0
    except KeyboardInterrupt:emit('cancelled');return 130
    except (ValueError,KeyError,OSError,RuntimeError,json.JSONDecodeError) as e:emit('error',message=str(e));return 1
if __name__=='__main__':raise SystemExit(main())
