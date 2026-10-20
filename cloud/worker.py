"""Cloud Run Jobs entrypoint: genuine Blender production with resumable GCS frames."""
import concurrent.futures, hashlib, importlib.util, json, os, queue, re, shutil, signal, subprocess, sys, threading, time
from pathlib import Path
import psutil
from google.cloud import storage
from .domain import ARTIFACT_FILES, MIME_TYPES, now_iso, storage_prefix, valid_id
from .repository import Repository

ROOT=Path(__file__).resolve().parents[1]
ROOT_FILES={'config.json','resolved-config.json','build-manifest.json','render-state.json','delivery.json','second-nature.blend','second-nature.mp4','soundtrack.wav','opening.png','closing.png','poster.jpg','build.log','render.log','assembly.log'}

class Cancelled(Exception):pass

def stop_process_tree(proc):
    """Blender uses a separate session; traverse descendants instead of one pgid."""
    try:parent=psutil.Process(proc.pid);targets=parent.children(recursive=True)+[parent]
    except psutil.NoSuchProcess:return
    for process in targets:
        try:process.terminate()
        except psutil.NoSuchProcess:pass
    _,alive=psutil.wait_procs(targets,timeout=3)
    for process in alive:
        try:process.kill()
        except psutil.NoSuchProcess:pass
    psutil.wait_procs(alive,timeout=2)
    try:proc.wait(timeout=1)
    except subprocess.TimeoutExpired:pass

class Checkpoint:
    def __init__(self,bucket,prefix,folder):
        self.bucket=bucket;self.prefix=prefix;self.folder=Path(folder);self.sent={}
    def download(self,blob,destination):
        destination.parent.mkdir(parents=True,exist_ok=True);temp=destination.with_suffix(destination.suffix+'.download')
        blob.download_to_filename(str(temp),timeout=60);temp.replace(destination)
        self.sent[blob.name]=(destination.stat().st_size,destination.stat().st_mtime_ns)
    def restore(self):
        # Root manifests and source artifacts first. Frame namespaces are keyed by
        # render fingerprint, so a resumed build never mixes two configurations.
        for blob in self.bucket.list_blobs(prefix=self.prefix):
            relative=blob.name[len(self.prefix):]
            if relative in ROOT_FILES:self.download(blob,self.folder/relative)
        state=self.folder/'render-state.json'
        if not state.is_file():return
        fingerprint=json.loads(state.read_text()).get('fingerprint','')
        if not re.fullmatch(r'[a-f0-9]{64}',fingerprint):raise RuntimeError('Stored render state has an invalid fingerprint.')
        prefix=self.prefix+'frame-cache/'+fingerprint+'/'
        frames=[blob for blob in self.bucket.list_blobs(prefix=prefix) if re.fullmatch(r'frame_[0-9]{4}\.png',blob.name[len(prefix):])]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda blob:self.download(blob,self.folder/'frames'/blob.name[len(prefix):]),frames))
    def candidates(self):
        result=[(self.folder/name,self.prefix+name) for name in ROOT_FILES if (self.folder/name).is_file()]
        state=self.folder/'render-state.json'
        if state.is_file():
            fingerprint=json.loads(state.read_text()).get('fingerprint','')
            if re.fullmatch(r'[a-f0-9]{64}',fingerprint):
                result.extend((path,self.prefix+'frame-cache/'+fingerprint+'/'+path.name) for path in (self.folder/'frames').glob('frame_[0-9][0-9][0-9][0-9].png'))
        return result
    def sync(self):
        changed=[]
        for path,name in self.candidates():
            stat=path.stat();identity=(stat.st_size,stat.st_mtime_ns)
            if self.sent.get(name)!=identity:changed.append((path,name,identity))
        def upload(item):
            path,name,identity=item;self.bucket.blob(name).upload_from_filename(str(path),timeout=60)
            return name,identity
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for name,identity in pool.map(upload,changed):self.sent[name]=identity
    def artifact_metadata(self):
        result={}
        for kind,name in ARTIFACT_FILES.items():
            path=self.folder/name
            if path.is_file():result[kind]={'size':path.stat().st_size,'updated_at':now_iso(),'content_type':MIME_TYPES[kind]}
        return result

def parse_progress(line):
    if not line.startswith('FRAME_DONE '):return None
    try:
        data=json.loads(line[11:]);done=data['completed'];remaining=data['remaining'];frame=data['frame']
        if any(isinstance(v,bool) or not isinstance(v,int) or v<0 for v in (done,remaining,frame)) or frame<1 or done+remaining<1:return None
        return {'completed':done,'total':done+remaining,'frame':frame,'seconds':data.get('seconds')}
    except (ValueError,KeyError,TypeError):return None

def command_plan(action,cached_build):
    if action=='all':return ([] if cached_build else ['build'])+['render','assemble']
    return [action]

class Worker:
    def __init__(self,repo,bucket,jid,stop=None,root=ROOT):
        self.repo=repo;self.bucket=bucket;self.jid=valid_id(jid);self.stop=stop or threading.Event();self.root=Path(root);self.log='';self.progress={'completed':0,'total':576};self.stage='starting';self.last_report=0;self.last_poll=0
    def append(self,line):
        self.log=(self.log+line)[-20000:];print(line.rstrip(),flush=True)
    def report(self,force=False):
        if force or time.monotonic()-self.last_report>3:
            self.repo.update_job(self.jid,{'log':self.log,'progress':self.progress,'stage':self.stage,'heartbeat_at':now_iso()});self.last_report=time.monotonic()
    def check_cancel(self):
        if self.stop.is_set():raise Cancelled()
        if time.monotonic()-self.last_poll>2:
            self.last_poll=time.monotonic();record=self.repo.worker_job(self.jid)
            if record['status'] in ('cancelling','cancelled','interrupted'):raise Cancelled()
    def run_command(self,command,checkpoint):
        self.check_cancel();proc=subprocess.Popen([str(x) for x in command],cwd=self.root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1,start_new_session=True)
        lines=queue.Queue()
        def read():
            try:
                for line in proc.stdout:lines.put(line)
            finally:lines.put(None)
        reader=threading.Thread(target=read,daemon=True);reader.start();saved=0
        try:
            while True:
                self.check_cancel()
                try:line=lines.get(timeout=.5)
                except queue.Empty:self.report();continue
                if line is None:break
                self.append(line);progress=parse_progress(line)
                if progress:
                    self.progress=progress
                    if progress['completed']-saved>=5:
                        checkpoint.sync();saved=progress['completed']
                self.report()
            code=proc.wait()
            if code:raise RuntimeError(self.stage+' failed with process exit code '+str(code)+'. Inspect the production log.')
        finally:
            if proc.poll() is None:stop_process_tree(proc)
            reader.join(timeout=1)
            if proc.stdout:proc.stdout.close()
        checkpoint.sync();self.report(force=True)
    def verify_movie(self,folder):
        movie=folder/'second-nature.mp4'
        info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(movie)],text=True,timeout=30))
        video=next((s for s in info['streams'] if s['codec_type']=='video'),{})
        if video.get('width')!=960 or video.get('height')!=540 or not any(s['codec_type']=='audio' for s in info['streams']) or abs(float(info['format']['duration'])-24)>.1:raise RuntimeError('Encoded movie failed delivery validation.')
        delivery=json.loads((folder/'delivery.json').read_text())
        if delivery['sha256']!=hashlib.sha256(movie.read_bytes()).hexdigest():raise RuntimeError('Encoded movie hash does not match its delivery manifest.')
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-ss','20','-i',str(movie),'-frames:v','1','-q:v','2',str(folder/'poster.jpg')],check=True,timeout=30)
    def execute(self):
        short=os.getenv('CLOUD_RUN_EXECUTION','')
        job=os.getenv('RENDER_JOB','second-nature-render').split('/')[-1]
        execution=f"projects/{os.environ['GOOGLE_CLOUD_PROJECT']}/locations/{os.getenv('RUN_REGION','us-central1')}/jobs/{job}/executions/{short}" if short else ''
        record=self.repo.claim(self.jid,execution)
        if not record:return 'unclaimed'
        folder=Path('/tmp/second-nature')/record['project_id'];folder.mkdir(parents=True,exist_ok=True)
        checkpoint=Checkpoint(self.bucket,storage_prefix(record['owner_id'],record['project_id']),folder)
        terminal='failed';error=None
        try:
            self.stage='restoring';self.report(force=True);checkpoint.restore();self.check_cancel()
            project=self.repo.get_project(record['project_id'],record['owner_id'])
            config={key:project[key] for key in ('name','seed','hero_color','accent_color','profile')};config['output_dir']=str(folder)
            config_path=folder/'config.json';config_path.write_text(json.dumps(config,indent=2)+'\n')
            spec=importlib.util.spec_from_file_location('production_pipeline',self.root/'pipeline.py');pipeline=importlib.util.module_from_spec(spec);spec.loader.exec_module(pipeline)
            try:pipeline.assert_build(config);cached=True
            except (OSError,ValueError,KeyError,RuntimeError):cached=False
            if cached and record['action']=='all':self.append('Validated the saved Blender scene; reusing this exact build.\n')
            for stage in command_plan(record['action'],cached):
                self.stage=stage;self.report(force=True)
                command=[sys.executable,self.root/'pipeline.py',stage,'--config',config_path]
                if stage=='render':command+=['--profile','preview']
                self.run_command(command,checkpoint)
            if record['action'] in ('all','assemble'):
                self.stage='verifying';self.run_command([sys.executable,self.root/'pipeline.py','verify','--config',config_path],checkpoint);self.verify_movie(folder)
            self.check_cancel();checkpoint.sync();terminal='complete'
            if record['action'] in ('all','render','assemble'):self.progress={'completed':576,'total':576}
        except Cancelled:
            terminal='cancelled';self.append('Production cancelled. Saved frames can be resumed.\n')
        except Exception as exc:
            error=str(exc)[:500];self.append('Production failed: '+error+'\n')
        finally:
            # Checkpoint on failure/cancellation too; these are real completed
            # atomic PNGs, never estimated or generated stand-ins.
            try:checkpoint.sync()
            except Exception as exc:
                terminal='failed';error='Cloud checkpoint could not be saved: '+str(exc)[:350]
            self.report(force=True)
            self.repo.finish(self.jid,terminal,error,checkpoint.artifact_metadata())
        return terminal

def main():
    stop=threading.Event()
    for name in ('SIGINT','SIGTERM','SIGHUP'):
        if hasattr(signal,name):signal.signal(getattr(signal,name),lambda *_:stop.set())
    jid=os.environ.get('JOB_ID','');valid_id(jid)
    repo=Repository();client=storage.Client(project=os.environ['GOOGLE_CLOUD_PROJECT']);bucket=client.bucket(os.environ['RENDER_BUCKET'])
    status=Worker(repo,bucket,jid,stop).execute()
    return 1 if status=='failed' else 0
if __name__=='__main__':raise SystemExit(main())
