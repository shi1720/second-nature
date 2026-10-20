import copy, io, json, os, subprocess, sys, tempfile, threading, time, unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from fastapi import Header
from fastapi.testclient import TestClient
from google.api_core.exceptions import PreconditionFailed
from cloud.api import create_app, verified_user
from cloud.domain import Problem, public_project, storage_prefix, validate_config
from cloud.repository import Repository
from cloud.worker import Checkpoint, Worker, command_plan, parse_progress

class MemoryState:
    def __init__(self):self.data={};self.generation=0;self.lock=threading.Lock();self.conflicts=0
    def read(self):
        with self.lock:return copy.deepcopy(self.data),self.generation
    def write(self,data,generation):
        with self.lock:
            if generation!=self.generation:self.conflicts+=1;raise PreconditionFailed('CAS conflict')
            self.data=copy.deepcopy(data);self.generation+=1

class Launcher:
    def __init__(self):self.started=[];self.cancelled=[];self.remote={'finished':False}
    def start(self,jid):self.started.append(jid);return 'operations/real-dispatch-interface'
    def cancel(self,execution):self.cancelled.append(execution)
    def status(self,execution):return self.remote

class FakeArtifacts:
    def describe(self,uid,pid,kind):
        class Blob:
            def open(self,*args,**kwargs):return io.BytesIO(b'0123456789')
        return Blob(),{'size':10,'content_type':'video/mp4'}

def identity(authorization=Header(default='')):
    if authorization not in ('Bearer owner','Bearer outsider'):raise Problem(401,'Sign in to continue.')
    return {'uid':authorization.split()[-1],'firebase':{'sign_in_provider':'anonymous'}}

class CloudAPITests(unittest.TestCase):
    def setUp(self):
        self.state=MemoryState();self.repo=Repository(self.state);self.launcher=Launcher()
        self.client=TestClient(create_app(deps=lambda:(self.repo,self.launcher,FakeArtifacts()),verify=identity))
        self.owner={'Authorization':'Bearer owner'};self.other={'Authorization':'Bearer outsider'}
        self.project=self.repo.create_project('owner',validate_config({}))
    def test_auth_ownership_and_rewrite_alias(self):
        self.assertEqual(self.client.get('/v1/projects').status_code,401)
        for root in ('','/api'):
            response=self.client.get(root+'/v1/projects',headers=self.owner);self.assertEqual(response.status_code,200)
            self.assertEqual(response.json()['projects'][0]['id'],self.project['id'])
            self.assertNotIn('owner_id',response.json()['projects'][0])
        self.assertEqual(self.client.get('/v1/projects/'+self.project['id'],headers=self.other).status_code,404)
        self.assertEqual(self.client.get('/v1/projects/'+self.project['id']+'/artifacts/movie/content',headers=self.other).status_code,404)
        self.assertEqual(self.client.head('/healthz').status_code,200)
        with self.assertRaises(Problem):verified_user('not-a-bearer-token')
    def test_validation_prevents_paths_final_and_owner_injection(self):
        for payload in ({'name':'x','output_dir':'/etc'},{'seed':True},{'hero_color':'red'},{'profile':'final'},{'owner_id':'outsider'}):
            self.assertEqual(self.client.post('/v1/projects',json=payload,headers=self.owner).status_code,400)
        self.assertEqual(self.client.get('/v1/projects/../../secrets',headers=self.owner).status_code,404)
        response=self.client.post('/v1/projects/'+self.project['id']+'/jobs',json={'action':'shell'},headers=self.owner)
        self.assertEqual(response.status_code,400);self.assertFalse(self.launcher.started)
    def test_job_dispatch_cancel_and_resume(self):
        path='/api/v1/projects/'+self.project['id']+'/jobs'
        response=self.client.post(path,json={},headers=self.owner);self.assertEqual(response.status_code,202,response.text)
        job=response.json();self.assertEqual(job['action'],'all');self.assertEqual(self.launcher.started,[job['id']])
        self.assertEqual(self.client.post(path,json={},headers=self.owner).status_code,409)
        self.assertEqual(self.client.post('/v1/jobs/'+job['id']+'/cancel',headers=self.other).status_code,404)
        cancel=self.client.post('/v1/jobs/'+job['id']+'/cancel',headers=self.owner);self.assertEqual(cancel.json()['status'],'cancelled')
        self.assertIsNone(self.repo.claim(job['id'],'execution-do-not-run'))
        resumed=self.client.post('/v1/jobs/'+job['id']+'/resume',headers=self.owner)
        self.assertEqual(resumed.status_code,202,resumed.text);self.assertEqual(resumed.json()['resume_from'],job['id'])
    def test_stream_range_and_portable_config(self):
        path='/v1/projects/'+self.project['id']+'/artifacts/'
        response=self.client.get(path+'movie/content',headers={**self.owner,'Range':'bytes=2-5'})
        self.assertEqual((response.status_code,response.content),(206,b'2345'))
        self.assertEqual(response.headers['content-range'],'bytes 2-5/10')
        self.assertEqual(self.client.get(path+'movie/content',headers={**self.owner,'Range':'bytes=100-'}).status_code,416)
        config=self.client.get(path+'config/content',headers=self.owner).json()
        self.assertEqual(config['output_dir'],'./second-nature-output');self.assertNotIn('owner_id',config)
        self.assertTrue(self.client.get(path+'movie',headers=self.owner).json()['requires_auth'])
    def test_remote_cancellation_releases_stale_worker_reservation(self):
        job=self.repo.reserve_job('owner',self.project['id'],'all','preview','ip')
        self.repo.claim(job['id'],'projects/test/locations/test/jobs/test/executions/1')
        self.launcher.remote={'finished':True,'cancelled':True}
        self.client.post('/v1/jobs/'+job['id']+'/cancel',headers=self.owner)
        result=self.client.get('/v1/jobs/'+job['id'],headers=self.owner).json()
        self.assertEqual(result['status'],'cancelled');self.assertFalse(self.repo.quota('owner','ip')['global_job_active'])

class QuotaTests(unittest.TestCase):
    def setUp(self):self.state=MemoryState();self.repo=Repository(self.state);self.project=self.repo.create_project('one',validate_config({}))
    def test_atomic_single_active_job_under_race(self):
        def start(_):
            try:return self.repo.reserve_job('one',self.project['id'],'all','preview','ip')['id']
            except Problem as exc:return exc.status
        with ThreadPoolExecutor(max_workers=12) as pool:results=list(pool.map(start,range(20)))
        self.assertEqual(sum(isinstance(r,str) for r in results),1);self.assertEqual(results.count(409),19)
    def test_cas_retry_does_not_spend_quota_twice(self):
        original=self.state.write;calls=[]
        def collide_once(data,generation):
            calls.append(generation)
            if len(calls)==1:raise PreconditionFailed('Concurrent metadata writer')
            return original(data,generation)
        self.state.write=collide_once
        job=self.repo.reserve_job('one',self.project['id'],'all','preview','ip')
        self.assertEqual(len(calls),2)
        self.assertEqual(len(self.state.data['jobs']),1)
        self.assertEqual(self.repo.quota('one','ip')['global_render_remaining'],2)
        self.assertEqual(self.repo.worker_job(job['id'])['status'],'queued')

    def test_daily_user_and_ip_quotas_survive_new_identity(self):
        for uid in ('one','two'):
            project=self.project if uid=='one' else self.repo.create_project(uid,validate_config({}))
            job=self.repo.reserve_job(uid,project['id'],'all','preview','same-network');self.repo.finish(job['id'],'failed','fixture')
        third=self.repo.create_project('three',validate_config({}))
        with self.assertRaises(Problem) as caught:self.repo.reserve_job('three',third['id'],'all','preview','same-network')
        self.assertEqual(caught.exception.status,429)
    def test_global_budget_and_lease_recovery(self):
        with patch.dict(os.environ,{'MAX_USER_DAILY_RENDERS':'10','MAX_IP_DAILY_RENDERS':'10'}):
            for _ in range(3):
                job=self.repo.reserve_job('one',self.project['id'],'all','preview','ip');self.repo.finish(job['id'],'cancelled')
            with self.assertRaises(Problem) as caught:self.repo.reserve_job('one',self.project['id'],'all','preview','ip')
            self.assertEqual(caught.exception.status,429)
        job=self.repo.reserve_job('one',self.project['id'],'build','preview','ip')
        self.repo.update_job(job['id'],{'lease_until':time.time()-1})
        reconciled=self.repo.reconcile(self.repo.worker_job(job['id']))
        self.assertEqual(reconciled['status'],'interrupted');self.assertFalse(self.repo.quota('one','ip')['global_job_active'])

class FakeBlob:
    def __init__(self,bucket,name):self.bucket=bucket;self.name=name
    def download_to_filename(self,path,**kwargs):Path(path).write_bytes(self.bucket.objects[self.name])
    def upload_from_filename(self,path,**kwargs):self.bucket.objects[self.name]=Path(path).read_bytes()
class FakeBucket:
    def __init__(self):self.objects={}
    def blob(self,name):return FakeBlob(self,name)
    def list_blobs(self,prefix):return [self.blob(name) for name in self.objects if name.startswith(prefix)]

class WorkerTests(unittest.TestCase):
    def test_checkpoint_uses_current_fingerprint_and_reuses_frames(self):
        with tempfile.TemporaryDirectory() as temp:
            bucket=FakeBucket();prefix=storage_prefix('owner','1'*32);first='a'*64;second='b'*64
            bucket.objects[prefix+'render-state.json']=json.dumps({'fingerprint':second}).encode()
            bucket.objects[prefix+'frame-cache/'+first+'/frame_0001.png']=b'old-render'
            bucket.objects[prefix+'frame-cache/'+second+'/frame_0001.png']=b'current-render'
            bucket.objects[prefix+'../../escape']=b'never-download'
            checkpoint=Checkpoint(bucket,prefix,Path(temp));checkpoint.restore()
            self.assertEqual((Path(temp)/'frames/frame_0001.png').read_bytes(),b'current-render')
            (Path(temp)/'frames/frame_0002.png').write_bytes(b'next-real-frame')
            checkpoint.sync()
            self.assertEqual(bucket.objects[prefix+'frame-cache/'+second+'/frame_0002.png'],b'next-real-frame')
            self.assertFalse((Path(temp)/'escape').exists())
    def test_progress_and_stage_plan(self):
        self.assertEqual(parse_progress('FRAME_DONE {"frame":101,"completed":1,"remaining":20}')['total'],21)
        for line in ('FRAME_DONE {broken','FRAME_DONE null','FRAME_DONE {"frame":1,"completed":true,"remaining":0}'):
            self.assertIsNone(parse_progress(line))
        self.assertEqual(command_plan('all',False),['build','render','assemble'])
        self.assertEqual(command_plan('all',True),['render','assemble'])
    def test_real_subprocess_progress_and_failed_exit_are_not_faked(self):
        with tempfile.TemporaryDirectory() as temp:
            state=MemoryState();repo=Repository(state);project=repo.create_project('owner',validate_config({}));job=repo.reserve_job('owner',project['id'],'build','preview','ip');repo.claim(job['id'],'execution')
            worker=Worker(repo,FakeBucket(),job['id'],root=Path(temp));worker.stage='render'
            class Check:
                def __init__(self):self.count=0
                def sync(self):self.count+=1
            check=Check();fixture=Path(temp)/'fake.py'
            fixture.write_text('print(\'FRAME_DONE {"frame":5,"completed":5,"remaining":571}\',flush=True)\n')
            worker.run_command([sys.executable,fixture],check)
            self.assertEqual(repo.worker_job(job['id'])['progress']['completed'],5);self.assertGreaterEqual(check.count,2)
            fixture.write_text('raise SystemExit(7)\n')
            with self.assertRaisesRegex(RuntimeError,'exit code 7'):worker.run_command([sys.executable,fixture],check)


class DispatchTests(unittest.TestCase):
    def test_cloud_run_overrides_and_runtime_project_are_real_sdk_messages(self):
        from types import SimpleNamespace
        from cloud.services import Launcher as RealLauncher
        class Jobs:
            def run_job(self,request,timeout):
                self.request=request;return SimpleNamespace(operation=SimpleNamespace(name='operations/accepted'))
        class Executions:
            def cancel_execution(self,request,timeout):self.cancelled=request.name
            def get_execution(self,request,timeout):return SimpleNamespace(completion_time=object(),cancelled_count=1,failed_count=0)
        jobs=Jobs();executions=Executions()
        with patch.dict(os.environ,{'GOOGLE_CLOUD_PROJECT':'runtime-isolated','AUTH_PROJECT_ID':'auth-isolated','RUN_REGION':'us-central1','RENDER_JOB':'second-nature-render','JOB_TIMEOUT_SECONDS':'7200'}):
            launcher=RealLauncher(jobs,executions)
            self.assertEqual(launcher.start('a'*32),'operations/accepted')
            self.assertEqual(jobs.request.name,'projects/runtime-isolated/locations/us-central1/jobs/second-nature-render')
            self.assertEqual(jobs.request.overrides.task_count,1)
            self.assertEqual(jobs.request.overrides.timeout.total_seconds(),7200)
            self.assertEqual(jobs.request.overrides.container_overrides[0].env[0].value,'a'*32)
            launcher.cancel('execution/owned');self.assertEqual(executions.cancelled,'execution/owned')
            self.assertTrue(launcher.status('execution/owned')['cancelled'])


class EnvironmentTests(unittest.TestCase):
    def test_real_dependency_factory_uses_lazy_auth_project_fallbacks(self):
        import cloud.api as api
        cases = [
            ({'AUTH_PROJECT_ID':'auth-only'}, 'auth-only'),
            ({'AUTH_PROJECT_ID':'', 'FIREBASE_PROJECT_ID':'firebase-only'}, 'firebase-only'),
            ({'GOOGLE_CLOUD_PROJECT':'runtime-fallback'}, 'runtime-fallback'),
        ]
        for configured,expected in cases:
            with self.subTest(configured=configured):
                api.dependencies.cache_clear()
                with patch.dict(os.environ, {**configured,'RATE_LIMIT_SALT':'test-salt'},clear=True), patch.object(api.firebase_admin,'_apps',{}), patch.object(api.firebase_admin,'initialize_app') as initialize, patch.object(api,'Repository') as repo, patch.object(api,'Launcher') as launcher, patch.object(api,'Artifacts') as artifacts:
                    result=api.dependencies()
                    initialize.assert_called_once_with(options={'projectId':expected})
                    self.assertEqual(result,(repo.return_value,launcher.return_value,artifacts.return_value))
                api.dependencies.cache_clear()
        with patch.dict(os.environ, {'RATE_LIMIT_SALT':'test-salt'},clear=True), patch.object(api.firebase_admin,'initialize_app') as initialize:
            with self.assertRaisesRegex(RuntimeError,'AUTH_PROJECT_ID'):
                api.dependencies()
            initialize.assert_not_called()
        api.dependencies.cache_clear()

if __name__=='__main__':unittest.main()
