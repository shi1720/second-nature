#!/usr/bin/env python3
"""SECOND NATURE local production studio. Python 3.10+, standard library only."""
from __future__ import annotations
import argparse, hashlib, hmac, json, mimetypes, os, re, secrets, signal, sqlite3, subprocess, sys, threading, time, uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent
MAX_BODY = 16_384
SESSION_TTL = 60 * 60 * 12

class Studio:
    def __init__(self, data_dir=None, base=None):
        self.base = Path(base or BASE).resolve()
        self.data = Path(data_dir or ROOT / '.data').resolve()
        self.data.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.dbfile = self.data / 'studio.sqlite3'
        self.lock = threading.RLock()
        self.processes = {}
        self.workers = {}
        self.shutting_down = False
        self.attempts = {}
        with self.db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT,csrf TEXT NOT NULL,expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,name TEXT NOT NULL,config TEXT NOT NULL,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,kind TEXT NOT NULL,status TEXT NOT NULL,log TEXT NOT NULL,created REAL NOT NULL,ended REAL);''')
            db.execute("UPDATE jobs SET status='interrupted',ended=? WHERE status IN ('queued','running','cancelling')", (time.time(),))
        try: os.chmod(self.dbfile, 0o600)
        except OSError: pass
    def db(self):
        db = sqlite3.connect(self.dbfile, timeout=10)
        db.row_factory = sqlite3.Row
        return db
    def session(self, raw):
        if not raw: return None
        with self.db() as db:
            return db.execute('SELECT * FROM sessions WHERE token=? AND expires>?', (hashlib.sha256(raw.encode()).hexdigest(), time.time())).fetchone()
    def new_session(self, user_id=None):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.db() as db:
            db.execute('DELETE FROM sessions WHERE expires<?', (time.time(),))
            db.execute('INSERT INTO sessions VALUES(?,?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), user_id, csrf, time.time()+SESSION_TTL))
        return token, csrf
    @staticmethod
    def password(value, salt=None):
        salt = salt or secrets.token_hex(16)
        return salt + ':' + hashlib.pbkdf2_hmac('sha256', value.encode(), bytes.fromhex(salt), 310_000).hex()
    def project(self, project_id, user_id):
        if not isinstance(project_id, str) or not re.fullmatch(r'[a-f0-9]{32}', project_id): return None
        with self.db() as db:
            return db.execute('SELECT * FROM projects WHERE id=? AND user_id=?', (project_id,user_id)).fetchone()
    def config(self, payload, project_id):
        name = payload.get('name','Untitled production')
        seed = payload.get('seed',42)
        if not isinstance(name,str) or not 1 <= len(name.strip()) <= 80: raise ValueError('Name must contain 1–80 characters.')
        if isinstance(seed,bool) or not isinstance(seed,int) or not 0 <= seed <= 999999: raise ValueError('Seed must be a whole number from 0 to 999999.')
        hero, accent = payload.get('hero_color','#ed785b'), payload.get('accent_color','#3d9893')
        if any(not isinstance(v,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',v) for v in (hero,accent)): raise ValueError('Choose valid six-digit hex colors.')
        profile = payload.get('profile','preview')
        if profile not in ('preview','final'): raise ValueError('Unknown output profile.')
        return dict(name=name.strip(),seed=seed,hero_color=hero,accent_color=accent,profile=profile,output_dir=str(self.base/'projects'/project_id))
    def start_job(self, project, kind):
        if kind not in ('build','render','assemble'): raise ValueError('Unknown production command.')
        if not (self.base/'pipeline.py').is_file(): raise ValueError('The production pipeline is not installed yet.')
        folder = Path(json.loads(project['config'])['output_dir'])
        if kind == 'render' and not (folder/'second-nature.blend').is_file(): raise ValueError('Build the Blender scene before rendering.')
        if kind == 'assemble' and not any((folder/'frames').glob('*.png')): raise ValueError('Render frame images before assembling the film.')
        with self.lock:
            if self.shutting_down: raise ValueError('The studio is shutting down. Restart it before starting another job.')
            with self.db() as db:
                active = db.execute("SELECT id FROM jobs WHERE status IN ('queued','running','cancelling')").fetchone()
                if active: raise ValueError('Another production job is active. Wait or cancel it first.')
                job_id = uuid.uuid4().hex
                db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,NULL)', (job_id, project['id'],kind,'queued','',time.time()))
            thread = threading.Thread(target=self.run_job,args=(job_id,project,kind),daemon=True)
            self.workers[job_id] = thread
            thread.start()
            return job_id
    def update_job(self, job_id, **fields):
        with self.db() as db:
            db.execute('UPDATE jobs SET '+','.join(k+'=?' for k in fields)+' WHERE id=?', (*fields.values(),job_id))
    def run_job(self, job_id, project, kind):
        config = json.loads(project['config'])
        config_path = Path(config['output_dir'])/'config.json'
        command = [sys.executable,str(self.base/'pipeline.py'),kind,'--config',str(config_path)]
        if kind == 'render': command += ['--profile',config['profile']]
        log = ''
        proc = None
        try:
            with self.lock:
                with self.db() as db:
                    status = db.execute('SELECT status FROM jobs WHERE id=?',(job_id,)).fetchone()['status']
                if status == 'cancelling':
                    self.update_job(job_id,status='cancelled',ended=time.time()); return
                if status not in ('queued','running'): return
                proc = subprocess.Popen(command,cwd=self.base,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1,start_new_session=True)
                self.processes[job_id] = proc
                self.update_job(job_id,status='running')
            for line in proc.stdout:
                log = (log + line)[-30000:]
                self.update_job(job_id,log=log)
            code = proc.wait()
            with self.lock:
                with self.db() as db:
                    status = db.execute('SELECT status FROM jobs WHERE id=?',(job_id,)).fetchone()['status']
                final_status = 'cancelled' if status=='cancelling' else ('interrupted' if status=='interrupted' else ('complete' if code==0 else 'failed'))
                self.update_job(job_id,status=final_status,ended=time.time())
        except Exception as exc:
            with self.db() as db:
                row = db.execute('SELECT status FROM jobs WHERE id=?',(job_id,)).fetchone()
            final_status = 'cancelled' if row and row['status']=='cancelling' else ('interrupted' if row and row['status']=='interrupted' else 'failed')
            self.update_job(job_id,status=final_status,log=(log+'\n'+str(exc))[-30000:],ended=time.time())
        finally:
            if proc and proc.stdout: proc.stdout.close()
            with self.lock:
                self.processes.pop(job_id,None)
                self.workers.pop(job_id,None)
    def cancel(self, job_id):
        with self.lock, self.db() as db:
            row = db.execute('SELECT status FROM jobs WHERE id=?',(job_id,)).fetchone()
            if not row or row['status'] not in ('queued','running','cancelling'): raise ValueError('This job is no longer active.')
            db.execute("UPDATE jobs SET status='cancelling' WHERE id=?",(job_id,))
            proc = self.processes.get(job_id)
            if proc:
                try: os.killpg(proc.pid,signal.SIGTERM)
                except ProcessLookupError: pass
                def kill_later():
                    try: proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        try: os.killpg(proc.pid,signal.SIGKILL)
                        except ProcessLookupError: pass
                threading.Thread(target=kill_later,daemon=True).start()

    def shutdown(self, timeout=8):
        """Stop admission, cancel owned jobs, and allow bounded worker cleanup."""
        with self.lock:
            self.shutting_down = True
            with self.db() as db:
                ids = [row['id'] for row in db.execute("SELECT id FROM jobs WHERE status IN ('queued','running','cancelling')")]
            for job_id in ids:
                try: self.cancel(job_id)
                except ValueError: pass
            workers = list(self.workers.values())
        deadline = time.monotonic() + max(0, timeout)
        for worker in workers:
            worker.join(max(0, deadline-time.monotonic()))
        # Normally cancellation escalates after five seconds. Enforce a final
        # bound even if a worker has not received EOF from its process stream.
        with self.lock: processes = list(self.processes.values())
        for proc in processes:
            if proc.poll() is None:
                try: os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError: pass
                try: proc.wait(timeout=1)
                except subprocess.TimeoutExpired: pass
        for worker in workers:
            if worker.is_alive(): worker.join(.25)
        with self.db() as db:
            db.execute("UPDATE jobs SET status='interrupted',ended=? WHERE status IN ('queued','running','cancelling')", (time.time(),))

class Handler(BaseHTTPRequestHandler):
    server_version = 'SecondNatureStudio/1.0'
    def log_message(self, fmt, *args): pass
    @property
    def app(self): return self.server.app
    def headers_out(self, status, mime='application/json', length=None, cookie=None):
        self.send_response(status)
        self.send_header('Content-Type',mime)
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self'; media-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header('Cache-Control','no-store')
        if length is not None: self.send_header('Content-Length',str(length))
        if cookie: self.send_header('Set-Cookie','studio_session='+cookie+'; HttpOnly; SameSite=Strict; Path=/; Max-Age='+str(SESSION_TTL))
        self.end_headers()
    def reply(self, status, value, cookie=None):
        data=json.dumps(value).encode(); self.headers_out(status,length=len(data),cookie=cookie); self.wfile.write(data)
    def valid_host(self):
        host=self.headers.get('Host','')
        return host in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')
    def get_session(self):
        cookies={}
        for part in self.headers.get('Cookie','').split(';'):
            if '=' in part:
                k,v=part.strip().split('=',1); cookies[k]=v
        return self.app.session(cookies.get('studio_session'))
    def do_GET(self):
        if not self.valid_host(): return self.reply(403,{'error':'Local access only.'})
        path=urlsplit(self.path).path
        session=self.get_session()
        if path=='/api/session':
            token=None
            if not session:
                token,_=self.app.new_session(); session=self.app.session(token)
            user=None
            if session['user_id']:
                with self.app.db() as db:
                    row=db.execute('SELECT email FROM users WHERE id=?',(session['user_id'],)).fetchone()
                    user={'email':row['email']} if row else None
            return self.reply(200,{'user':user,'csrf':session['csrf']},token)
        if path.startswith('/api/'):
            if not session or not session['user_id']: return self.reply(401,{'error':'Sign in to continue.'})
            if path=='/api/state':
                with self.app.db() as db:
                    projects=[dict(r) for r in db.execute('SELECT * FROM projects WHERE user_id=? ORDER BY created DESC',(session['user_id'],))]
                    jobs=[dict(r) for r in db.execute('SELECT jobs.* FROM jobs JOIN projects ON projects.id=jobs.project_id WHERE projects.user_id=? ORDER BY jobs.created DESC LIMIT 30',(session['user_id'],))]
                for p in projects:
                    p['config']=json.loads(p['config']); folder=Path(p['config']['output_dir'])
                    p['assets']={'blend':(folder/'second-nature.blend').is_file(),'video':(folder/'second-nature.mp4').is_file(),'frames':len(list((folder/'frames').glob('*.png')))}
                stills=[name for name in ('seed.jpg','drop-chase.jpg','loop.jpg','suspension.jpg','bloom.jpg') if (self.app.base/'stills'/name).is_file()]
                return self.reply(200,{'projects':projects,'jobs':jobs,'demo_video':(self.app.base/'film'/'second-nature.mp4').is_file(),'stills':stills,'pipeline_ready':(self.app.base/'pipeline.py').is_file()})
            return self.reply(404,{'error':'Unknown endpoint.'})
        if path.startswith('/media/'):
            if not session or not session['user_id']: return self.reply(401,{'error':'Sign in to continue.'})
            pieces=unquote(path).split('/')
            if len(pieces)<4: return self.reply(404,{'error':'File not found.'})
            bucket=pieces[2]
            if bucket=='demo':
                rel='/'.join(pieces[3:])
                if rel=='film/second-nature.mp4': root=self.app.base/'film'; rel='second-nature.mp4'
                elif rel.startswith('stills/') and '/' not in rel[7:]: root=self.app.base/'stills'; rel=rel[7:]
                else: return self.reply(404,{'error':'File not found.'})
            else:
                project=self.app.project(bucket,session['user_id'])
                if not project: return self.reply(404,{'error':'File not found.'})
                root=Path(json.loads(project['config'])['output_dir']); rel='/'.join(pieces[3:])
                if rel not in ('second-nature.mp4','second-nature.blend') and not re.fullmatch(r'frames/[A-Za-z0-9_-]+\.png',rel): return self.reply(404,{'error':'File not found.'})
            return self.send_file(root,rel)
        return self.send_file(ROOT/'static','index.html' if path=='/' else unquote(path).lstrip('/'))
    def send_file(self, root, rel):
        root=Path(root).resolve(); target=(root/rel).resolve()
        if not target.is_relative_to(root) or not target.is_file(): return self.reply(404,{'error':'File not found.'})
        length=target.stat().st_size; start=0; end=length-1; status=200
        range_header=self.headers.get('Range')
        if range_header:
            match=re.fullmatch(r'bytes=(\d+)-(\d*)',range_header)
            if not match: return self.reply(416,{'error':'Invalid range.'})
            start=int(match[1]); end=min(int(match[2]) if match[2] else end,end)
            if start>end or start>=length: return self.reply(416,{'error':'Invalid range.'})
            status=206
        self.send_response(status)
        self.send_header('Content-Type',mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
        self.send_header('Content-Length',str(end-start+1)); self.send_header('Accept-Ranges','bytes')
        self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Cache-Control','no-store')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self'; media-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        if target.suffix=='.blend': self.send_header('Content-Disposition','attachment; filename="second-nature.blend"')
        if status==206: self.send_header('Content-Range',f'bytes {start}-{end}/{length}')
        self.end_headers()
        with target.open('rb') as stream:
            stream.seek(start); remaining=end-start+1
            while remaining:
                block=stream.read(min(65536,remaining))
                if not block: break
                try: self.wfile.write(block)
                except (BrokenPipeError,ConnectionResetError): break
                remaining-=len(block)
    def do_POST(self):
        if not self.valid_host(): return self.reply(403,{'error':'Local access only.'})
        origin=self.headers.get('Origin')
        if origin and origin not in ('http://'+self.headers['Host'],): return self.reply(403,{'error':'Origin rejected.'})
        session=self.get_session()
        if not session or not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),session['csrf']): return self.reply(403,{'error':'Session expired. Reload and try again.'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length<0 or length>MAX_BODY: return self.reply(413,{'error':'Request too large.'})
            if self.headers.get_content_type()!='application/json': return self.reply(415,{'error':'JSON required.'})
            payload=json.loads(self.rfile.read(length))
            if not isinstance(payload,dict): raise ValueError('Expected an object.')
        except (ValueError,UnicodeDecodeError): return self.reply(400,{'error':'Invalid request.'})
        path=urlsplit(self.path).path
        try:
            if path in ('/api/login','/api/register'):
                now=time.time(); attempts=[t for t in self.app.attempts.get(self.client_address[0],[]) if t>now-60]
                if len(attempts)>=10: return self.reply(429,{'error':'Too many attempts. Try again in a minute.'})
                self.app.attempts[self.client_address[0]]=attempts+[now]
                email=payload.get('email',''); password=payload.get('password','')
                if not isinstance(email,str) or not re.fullmatch(r'[^\s@]{1,100}@[^\s@]{1,100}\.[^\s@]{1,30}',email) or not isinstance(password,str) or not 12<=len(password)<=256: raise ValueError('Use a valid email and a password of 12–256 characters.')
                email=email.lower().strip()
                with self.app.db() as db:
                    if path=='/api/register':
                        uid=uuid.uuid4().hex
                        try: db.execute('INSERT INTO users VALUES(?,?,?)',(uid,email,self.app.password(password)))
                        except sqlite3.IntegrityError: raise ValueError('Account unavailable. Try signing in.')
                    else:
                        user=db.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
                        reference=user['password'] if user else self.app.password('timing-equalizer-password')
                        valid=hmac.compare_digest(self.app.password(password,reference.split(':')[0]),reference)
                        if not user or not valid: return self.reply(401,{'error':'Email or password is incorrect.'})
                        uid=user['id']
                    db.execute('DELETE FROM sessions WHERE token=?',(session['token'],))
                token,csrf=self.app.new_session(uid)
                return self.reply(200,{'user':{'email':email},'csrf':csrf},token)
            if not session['user_id']: return self.reply(401,{'error':'Sign in to continue.'})
            if path=='/api/logout':
                with self.app.db() as db: db.execute('DELETE FROM sessions WHERE token=?',(session['token'],))
                token,csrf=self.app.new_session(); return self.reply(200,{'csrf':csrf},token)
            if path=='/api/projects':
                pid=uuid.uuid4().hex; config=self.app.config(payload,pid)
                folder=Path(config['output_dir']); folder.mkdir(parents=True,exist_ok=False)
                (folder/'config.json').write_text(json.dumps(config,indent=2)+'\n')
                with self.app.db() as db: db.execute('INSERT INTO projects VALUES(?,?,?,?,?)',(pid,session['user_id'],config['name'],json.dumps(config),time.time()))
                return self.reply(201,{'id':pid})
            if path=='/api/jobs':
                project=self.app.project(payload.get('project_id'),session['user_id'])
                if not project: return self.reply(404,{'error':'Production not found.'})
                return self.reply(201,{'id':self.app.start_job(project,payload.get('kind'))})
            if path=='/api/cancel':
                if not isinstance(payload.get('job_id'),str) or not re.fullmatch(r'[a-f0-9]{32}',payload['job_id']): return self.reply(404,{'error':'Job not found.'})
                with self.app.db() as db:
                    job=db.execute('SELECT jobs.id FROM jobs JOIN projects ON projects.id=jobs.project_id WHERE jobs.id=? AND projects.user_id=?',(payload.get('job_id'),session['user_id'])).fetchone()
                if not job: return self.reply(404,{'error':'Job not found.'})
                self.app.cancel(job['id']); return self.reply(200,{'ok':True})
            return self.reply(404,{'error':'Unknown endpoint.'})
        except ValueError as exc: return self.reply(400,{'error':str(exc)})
        except OSError: return self.reply(500,{'error':'The local filesystem or production process is unavailable.'})

def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--port',type=int,default=8765); parser.add_argument('--open-browser',action='store_true'); args=parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler); server.app=Studio()
    server.timeout = .25
    stopping = threading.Event()
    previous_handlers = {}
    def request_shutdown(signum, frame):
        # Signal handlers only notify the normal control flow. They must not
        # interrupt SQLite transactions or acquire locks held by workers.
        stopping.set()
    for name in ('SIGINT','SIGTERM','SIGHUP'):
        sig = getattr(signal,name,None)
        if sig is not None:
            previous_handlers[sig] = signal.signal(sig,request_shutdown)
    print(f'SECOND NATURE Studio → http://127.0.0.1:{server.server_port}',flush=True)
    browser_timer = None
    if args.open_browser:
        import webbrowser
        browser_timer = threading.Timer(.5,lambda: webbrowser.open(f'http://127.0.0.1:{server.server_port}'))
        browser_timer.daemon = True
        browser_timer.start()
    try:
        while not stopping.is_set(): server.handle_request()
    except KeyboardInterrupt: pass
    finally:
        if browser_timer: browser_timer.cancel()
        try: server.app.shutdown(timeout=8)
        finally:
            server.server_close()
            for sig, handler in previous_handlers.items(): signal.signal(sig,handler)
if __name__=='__main__': main()
