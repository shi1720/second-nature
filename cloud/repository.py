"""Private-bucket metadata with generation-CAS transactions; no shared database IAM."""
import copy, json, os, random, time
from google.api_core.exceptions import NotFound, PreconditionFailed
from google.cloud import storage
from .domain import Problem, ACTIVE, TERMINAL, day_key, new_id, now_iso, owner_key, require_owner, valid_id

class GCSState:
    """One compare-and-swap state document makes quotas and leases atomic."""
    def __init__(self,bucket=None):
        self.bucket=bucket or storage.Client(project=os.environ['GOOGLE_CLOUD_PROJECT']).bucket(os.environ['RENDER_BUCKET'])
    def read(self):
        blob=self.bucket.blob('metadata/state.json')
        try:
            blob.reload(timeout=20);generation=int(blob.generation)
            data=json.loads(blob.download_as_bytes(if_generation_match=generation,timeout=20))
            return data,generation
        except NotFound:return {},0
    def write(self,data,generation):
        self.bucket.blob('metadata/state.json').upload_from_string(json.dumps(data,separators=(',',':')),content_type='application/json',if_generation_match=generation,timeout=20)

class Repository:
    def __init__(self,state=None):
        self.state=state or GCSState();self.job_timeout=int(os.getenv('JOB_TIMEOUT_SECONDS','7200'))
    def read(self):
        for attempt in range(8):
            try:
                data,_=self.state.read()
                for key in ('projects','jobs','limits'):data.setdefault(key,{})
                return data
            except (NotFound,PreconditionFailed):time.sleep(.02*(attempt+1))
        raise Problem(503,'Metadata is busy. Please retry.')
    def atomic(self,change):
        for attempt in range(10):
            try:
                data,generation=self.state.read()
                for key in ('projects','jobs','limits'):data.setdefault(key,{})
                result=change(data)
                # Keep bounded history; configurations and finished artifacts stay.
                terminal=sorted([j for j in data['jobs'].values() if j['status'] in TERMINAL],key=lambda j:j['created_at'],reverse=True)
                for old in terminal[200:]:data['jobs'].pop(old['id'],None)
                data['version']=1
                self.state.write(data,generation)
                return copy.deepcopy(result)
            except (NotFound,PreconditionFailed):time.sleep(min(.02*(2**attempt),.5)+random.random()*.015)
        raise Problem(503,'Metadata changed concurrently. Please retry.')
    def get_project(self,pid,uid):return require_owner(self.read()['projects'].get(valid_id(pid)),uid)
    def get_job(self,jid,uid):return require_owner(self.read()['jobs'].get(valid_id(jid)),uid)
    def worker_job(self,jid):
        record=self.read()['jobs'].get(valid_id(jid))
        if not record:raise Problem(404,'Job not found.')
        return record
    def list_projects(self,uid):return sorted([p for p in self.read()['projects'].values() if p['owner_id']==uid],key=lambda p:p['created_at'],reverse=True)
    def list_jobs(self,pid,uid):
        self.get_project(pid,uid)
        return sorted([j for j in self.read()['jobs'].values() if j['owner_id']==uid and j['project_id']==pid],key=lambda j:j['created_at'],reverse=True)[:30]
    def create_project(self,uid,config,ip_hash=None):
        pid=new_id();stamp=now_iso();day=day_key()
        def create(data):
            projects=data['projects'];limits=data['limits'];user=limits.setdefault('user-'+owner_key(uid),{})
            global_day=limits.setdefault('global-'+day,{})
            if sum(p['owner_id']==uid for p in projects.values())>=20:raise Problem(429,'This account has reached its 20-project limit.')
            if len(projects)>=1000 or global_day.get('projects',0)>=100:raise Problem(429,'The studio has reached its project budget. Please try another day.')
            ip_day=limits.setdefault('ip-'+str(ip_hash)+'-'+day,{})
            if ip_hash and ip_day.get('projects',0)>=20:raise Problem(429,'The daily project limit for this network is used.')
            record={'id':pid,'owner_id':uid,**config,'created_at':stamp,'updated_at':stamp,'artifacts':{},'active_job':None}
            projects[pid]=record;user['project_count']=user.get('project_count',0)+1;global_day['projects']=global_day.get('projects',0)+1
            if ip_hash:ip_day['projects']=ip_day.get('projects',0)+1
            return record
        return self.atomic(create)
    def reserve_job(self,uid,pid,action,profile,ip_hash,resume_from=None):
        jid=new_id();stamp=now_iso();now=time.time();day=day_key();valid_id(pid)
        def reserve(data):
            project=require_owner(data['projects'].get(pid),uid);limits=data['limits']
            keys={'global':'global','user':'user-'+owner_key(uid),'global_day':'global-'+day,'user_day':'user-'+owner_key(uid)+'-'+day,'ip_day':'ip-'+ip_hash+'-'+day}
            values={key:limits.setdefault(name,{}) for key,name in keys.items()}
            if any(values[key].get('active_job') and values[key].get('lease_until',0)>now for key in ('global','user')):raise Problem(409,'A production job is already active. Wait for it or cancel your active job.')
            budgets={'global_day':int(os.getenv('MAX_DAILY_JOBS','30')),'user_day':int(os.getenv('MAX_USER_DAILY_JOBS','10')),'ip_day':int(os.getenv('MAX_IP_DAILY_JOBS','15'))}
            for key,limit in budgets.items():
                if values[key].get('jobs',0)>=limit:raise Problem(429,'Daily production limit reached. The UTC budget resets tomorrow.')
            rendering=action in ('render','all')
            if rendering:
                budgets={'global_day':int(os.getenv('MAX_DAILY_RENDERS','3')),'user_day':int(os.getenv('MAX_USER_DAILY_RENDERS','2')),'ip_day':int(os.getenv('MAX_IP_DAILY_RENDERS','2'))}
                for key,limit in budgets.items():
                    if values[key].get('renders',0)>=limit:raise Problem(429,'The daily render budget is used. It resets at 00:00 UTC. Resuming a render also uses a render slot.')
            lease=now+self.job_timeout+600
            record={'id':jid,'owner_id':uid,'project_id':pid,'action':action,'profile':profile,'status':'queued','stage':'queued','progress':{'completed':0,'total':576},'log':'','created_at':stamp,'updated_at':stamp,'lease_until':lease,'resume_from':resume_from}
            data['jobs'][jid]=record
            for key in ('global','user'):values[key].update({'active_job':jid,'lease_until':lease})
            project.update({'active_job':jid,'updated_at':stamp})
            for key in ('global_day','user_day','ip_day'):values[key].update({'jobs':values[key].get('jobs',0)+1,'renders':values[key].get('renders',0)+int(rendering)})
            return record
        return self.atomic(reserve)
    def update_job(self,jid,fields):
        valid_id(jid)
        def update(data):
            if jid not in data['jobs']:raise Problem(404,'Job not found.')
            data['jobs'][jid].update({**fields,'updated_at':now_iso()})
        self.atomic(update)
    def claim(self,jid,execution):
        valid_id(jid)
        def claim(data):
            job=data['jobs'].get(jid)
            if not job or job['status']!='queued':return None
            job.update({'status':'running','stage':'starting','execution':execution,'updated_at':now_iso()});return job
        return self.atomic(claim)
    def finish(self,jid,status,error=None,artifacts=None):
        if status not in TERMINAL:raise ValueError('Terminal status required')
        valid_id(jid)
        def finish(data):
            job=data['jobs'].get(jid)
            if not job or job['status'] in TERMINAL:return
            stamp=now_iso();job.update({'status':status,'stage':status,'updated_at':stamp,'ended_at':stamp})
            if error:job['error']=error[:500]
            for key in ('global','user-'+owner_key(job['owner_id'])):
                limit=data['limits'].setdefault(key,{})
                if limit.get('active_job')==jid:limit.update({'active_job':None,'lease_until':0})
            project=data['projects'][job['project_id']];project['updated_at']=stamp
            if project.get('active_job')==jid:project['active_job']=None
            if artifacts:project['artifacts']={**project.get('artifacts',{}),**artifacts}
        self.atomic(finish)
    def request_cancel(self,jid,uid):
        valid_id(jid)
        def cancel(data):
            record=require_owner(data['jobs'].get(jid),uid)
            if record['status'] in TERMINAL:return record
            was_queued=record['status']=='queued'
            record.update({'status':'cancelling','message':'Cancellation requested; saved frames remain available for resume.','updated_at':now_iso()})
            return {**record,'_was_queued':was_queued}
        return self.atomic(cancel)
    def reconcile(self,job):
        if job.get('status') in ACTIVE and job.get('lease_until',0)<time.time():
            self.finish(job['id'],'interrupted','The worker lease expired. Saved frames can be resumed.')
            return self.worker_job(job['id'])
        return job
    def quota(self,uid,ip_hash):
        limits=self.read()['limits'];day=day_key();global_day=limits.get('global-'+day,{});user_day=limits.get('user-'+owner_key(uid)+'-'+day,{});active=limits.get('global',{})
        return {'global_render_remaining':max(0,int(os.getenv('MAX_DAILY_RENDERS','3'))-global_day.get('renders',0)),
                'user_render_remaining':max(0,int(os.getenv('MAX_USER_DAILY_RENDERS','2'))-user_day.get('renders',0)),
                'global_job_active':bool(active.get('active_job') and active.get('lease_until',0)>time.time()),'resets_at':'00:00 UTC','profile':'preview'}
