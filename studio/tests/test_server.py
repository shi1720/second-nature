import http.client
import importlib.util
import json
import os
from pathlib import Path
import queue
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest

spec=importlib.util.spec_from_file_location('studio_server',Path(__file__).resolve().parents[1]/'server.py')
server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)

class Client:
    def __init__(self, port): self.port=port;self.cookie='';self.csrf=''
    def call(self,path,data=None,csrf=True,extra=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
        headers={'Cookie':self.cookie}
        if data is not None:
            headers['Content-Type']='application/json'
            if csrf: headers['X-CSRF-Token']=self.csrf
        headers.update(extra or {})
        conn.request('GET' if data is None else 'POST',path,None if data is None else json.dumps(data),headers)
        response=conn.getresponse();body=response.read();cookie=response.getheader('Set-Cookie')
        if cookie: self.cookie=cookie.split(';')[0]
        status=response.status;ctype=response.getheader('Content-Type','')
        conn.close()
        value=json.loads(body) if 'application/json' in ctype else body
        if isinstance(value,dict) and 'csrf' in value:self.csrf=value['csrf']
        return status,value
    def register(self,email='creator@example.com'):
        assert self.call('/api/session')[0]==200
        return self.call('/api/register',{'email':email,'password':'local-long-secret-123'})

class StudioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.app=server.Studio(self.base/'data',self.base)
        self.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);self.http.app=self.app
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.client=Client(self.http.server_port)
    def tearDown(self):
        for jid in list(self.app.processes):
            try:self.app.cancel(jid)
            except ValueError:pass
        deadline=time.time()+3
        while self.app.processes and time.time()<deadline:time.sleep(.03)
        self.http.shutdown();self.http.server_close();self.thread.join();self.temp.cleanup()
    def create(self,client=None,**overrides):
        data={'name':'My production','seed':42,'hero_color':'#ed785b','accent_color':'#3d9893','profile':'preview'};data.update(overrides)
        status,value=(client or self.client).call('/api/projects',data)
        self.assertEqual(status,201,value);return value['id']
    def fake_pipeline(self):
        (self.base/'pipeline.py').write_text("import time\nprint('Starting real local process', flush=True)\ntime.sleep(30)\n")
    def test_authentication_csrf_and_session_rotation(self):
        self.assertEqual(self.client.call('/api/state')[0],401)
        self.client.call('/api/session');old_cookie=self.client.cookie
        self.assertEqual(self.client.call('/api/register',{'email':'a@example.com','password':'long-password-123'},csrf=False)[0],403)
        self.assertEqual(self.client.register()[0],200)
        self.assertNotEqual(old_cookie,self.client.cookie)
        self.assertEqual(self.client.call('/api/state')[0],200)
        self.assertEqual(self.client.call('/api/projects',{'name':'bad'},csrf=False)[0],403)
        self.assertEqual(self.client.call('/api/logout',{})[0],200)
        self.assertEqual(self.client.call('/api/state')[0],401)
        self.assertEqual(self.client.call('/api/login',{'email':'creator@example.com','password':'incorrect-password'})[0],401)
        self.assertEqual(self.client.call('/api/login',{'email':'creator@example.com','password':'local-long-secret-123'})[0],200)
        with self.app.db() as db:
            password=db.execute('SELECT password FROM users').fetchone()[0]
            self.assertNotIn('local-long-secret',password)
            self.assertEqual(len(password.split(':')[1]),64)
    def test_config_validation_output_injection_and_ownership(self):
        self.client.register();pid=self.create(output_dir='/tmp/attacker')
        folder=self.base/'projects'/pid
        config=json.loads((folder/'config.json').read_text());self.assertEqual(config['output_dir'],str(folder.resolve()))
        for data in ({'seed':-1},{'seed':True},{'hero_color':'red'},{'profile':'../../x'},{'name':''}):
            self.assertEqual(self.client.call('/api/projects',data)[0],400)
        other=Client(self.http.server_port);other.register('other@example.com')
        self.assertEqual(other.call('/api/state')[1]['projects'],[])
        self.assertEqual(other.call('/api/jobs',{'project_id':pid,'kind':'build'})[0],404)
        (folder/'second-nature.blend').write_bytes(b'BLENDER')
        self.assertEqual(other.call('/media/'+pid+'/second-nature.blend')[0],404)
        self.assertEqual(self.client.call('/api/jobs',{'project_id':[],'kind':'build'})[0],404)
    def test_static_and_media_path_traversal_and_ranges(self):
        self.client.register();pid=self.create();folder=self.base/'projects'/pid
        (folder/'second-nature.mp4').write_bytes(b'0123456789')
        self.assertEqual(self.client.call('/media/'+pid+'/second-nature.mp4',extra={'Range':'bytes=2-5'}),(206,b'2345'))
        self.assertEqual(self.client.call('/media/'+pid+'/second-nature.mp4',extra={'Range':'bytes=999-'} )[0],416)
        for path in ('/%2e%2e/server.py','/media/'+pid+'/../../data/studio.sqlite3','/media/demo/stills/../../data/studio.sqlite3'):
            self.assertEqual(self.client.call(path)[0],404,path)
        (self.base/'stills').mkdir();(self.base/'secret.txt').write_text('secret')
        (self.base/'stills'/'escape.jpg').symlink_to(self.base/'secret.txt')
        self.assertEqual(self.client.call('/media/demo/stills/escape.jpg')[0],404)
        self.assertEqual(self.client.call('/api/state',extra={'Host':'evil.example:'+str(self.http.server_port)})[0],403)
        self.assertEqual(self.client.call('/api/projects',{'name':'x'},extra={'Origin':'https://evil.example'})[0],403)
    def test_job_prerequisites_concurrency_and_cancellation(self):
        self.client.register();pid=self.create();self.fake_pipeline()
        self.assertEqual(self.client.call('/api/jobs',{'project_id':pid,'kind':'delete'})[0],400)
        self.assertEqual(self.client.call('/api/jobs',{'project_id':pid,'kind':'render'})[0],400)
        self.assertEqual(self.client.call('/api/jobs',{'project_id':pid,'kind':'assemble'})[0],400)
        status,job=self.client.call('/api/jobs',{'project_id':pid,'kind':'build'});self.assertEqual(status,201)
        self.assertEqual(self.client.call('/api/jobs',{'project_id':pid,'kind':'build'})[0],400)
        self.assertEqual(self.client.call('/api/cancel',{'job_id':job['id']})[0],200)
        for _ in range(50):
            jobs=self.client.call('/api/state')[1]['jobs']
            if jobs[0]['status']=='cancelled':break
            time.sleep(.03)
        self.assertEqual(jobs[0]['status'],'cancelled')
        self.assertEqual(self.client.call('/api/cancel',{'job_id':job['id']})[0],400)
    def test_restart_marks_jobs_interrupted(self):
        self.client.register();pid=self.create()
        with self.app.db() as db:db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,NULL)',('1'*32,pid,'build','running','Progress',time.time()))
        restarted=server.Studio(self.base/'data',self.base)
        with restarted.db() as db:row=db.execute('SELECT * FROM jobs').fetchone()
        self.assertEqual(row['status'],'interrupted');self.assertIsNotNone(row['ended'])
    def test_no_public_account_password_or_short_password(self):
        self.client.call('/api/session')
        self.assertEqual(self.client.call('/api/register',{'email':'a@example.com','password':'short'})[0],400)
        self.assertEqual(self.client.call('/api/register',{'email':'invalid','password':'long-password-123'})[0],400)
        self.assertEqual(self.client.call('/media/demo/film/second-nature.mp4')[0],401)

    def run_cli_shutdown_check(self, terminating_signal, stubborn=False):
        fixture=self.base/('cli-'+str(terminating_signal)+('-stubborn' if stubborn else ''))
        studio=fixture/'studio';studio.mkdir(parents=True)
        shutil.copy2(Path(server.__file__),studio/'server.py')
        pipeline=fixture/'pipeline.py'
        pipeline.write_text("""import os, signal, time
from pathlib import Path
def cleanup(signum, frame):
    time.sleep(.2)
    Path('cleanup-complete').write_text('yes')
    raise SystemExit(0)
signal.signal(signal.SIGTERM, signal.SIG_IGN if STUBBORN else cleanup)
Path('pipeline.pid').write_text(str(os.getpid()))
print('Pipeline worker ready', flush=True)
while True: time.sleep(.1)
""".replace('STUBBORN',repr(stubborn)))
        proc=subprocess.Popen([sys.executable,str(studio/'server.py'),'--port','0'],cwd=fixture,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,start_new_session=True)
        worker_pid=None
        try:
            lines=queue.Queue()
            threading.Thread(target=lambda:lines.put(proc.stdout.readline()),daemon=True).start()
            ready=lines.get(timeout=10)
            match=re.search(r'http://127\.0\.0\.1:(\d+)',ready)
            self.assertIsNotNone(match,ready)
            client=Client(int(match[1]));self.assertEqual(client.register()[0],200)
            pid=self.create(client=client)
            status,job=client.call('/api/jobs',{'project_id':pid,'kind':'build'});self.assertEqual(status,201,job)
            deadline=time.monotonic()+5
            while not (fixture/'pipeline.pid').exists() and time.monotonic()<deadline:time.sleep(.02)
            self.assertTrue((fixture/'pipeline.pid').exists(),'Fake pipeline did not start')
            worker_pid=int((fixture/'pipeline.pid').read_text())
            os.kill(worker_pid,0)  # The detached pipeline is really alive before termination.
            started=time.monotonic();proc.send_signal(terminating_signal)
            proc.wait(timeout=12)
            self.assertEqual(proc.returncode,0,proc.stdout.read())
            self.assertLess(time.monotonic()-started,10)
            with self.assertRaises(ProcessLookupError):os.kill(worker_pid,0)
            with sqlite3.connect(studio/'.data'/'studio.sqlite3') as db:
                row=db.execute('SELECT status,ended FROM jobs WHERE id=?',(job['id'],)).fetchone()
            self.assertIn(row[0],('cancelled','interrupted'));self.assertIsNotNone(row[1])
            if not stubborn:self.assertEqual((fixture/'cleanup-complete').read_text(),'yes')
        finally:
            if proc.poll() is None:
                proc.kill();proc.wait(timeout=5)
            if proc.stdout:proc.stdout.close()
            # Test failure cleanup targets only this fixture's process group.
            if worker_pid:
                try:os.killpg(worker_pid,signal.SIGKILL)
                except ProcessLookupError:pass

    @unittest.skipUnless(os.name=='posix','POSIX process-group shutdown test')
    def test_cli_termination_cleans_detached_pipeline(self):
        for signum in (signal.SIGTERM,signal.SIGINT,getattr(signal,'SIGHUP',signal.SIGTERM)):
            with self.subTest(signal=signum):self.run_cli_shutdown_check(signum)

    @unittest.skipUnless(os.name=='posix','POSIX process-group shutdown test')
    def test_cli_shutdown_escalates_stubborn_pipeline(self):
        self.run_cli_shutdown_check(signal.SIGTERM,stubborn=True)

if __name__=='__main__':unittest.main()
