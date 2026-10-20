"""Input validation and ownership boundaries, independent of cloud SDKs."""
import hashlib, hmac, re, uuid
from datetime import datetime, timezone

ACTIONS = ('build','render','assemble','all')
TERMINAL = ('complete','failed','cancelled','interrupted')
ACTIVE = ('queued','running','cancelling')
ARTIFACT_FILES = {'movie':'second-nature.mp4','blend':'second-nature.blend','config':'config.json','poster':'poster.jpg'}
MIME_TYPES = {'movie':'video/mp4','blend':'application/octet-stream','config':'application/json','poster':'image/jpeg'}

class Problem(Exception):
    def __init__(self, status, detail): self.status=status; self.detail=detail; super().__init__(detail)

def now_iso(): return datetime.now(timezone.utc).isoformat()
def day_key(): return datetime.now(timezone.utc).strftime('%Y-%m-%d')
def new_id(): return uuid.uuid4().hex

def valid_id(value):
    if not isinstance(value,str) or not re.fullmatch(r'[a-f0-9]{32}',value): raise Problem(404,'Not found.')
    return value

def owner_key(uid): return hashlib.sha256(uid.encode()).hexdigest()[:40]
def storage_prefix(uid, pid): return 'users/'+owner_key(uid)+'/projects/'+valid_id(pid)+'/'
def ip_key(ip, salt): return hmac.new(salt.encode(),ip.encode(),hashlib.sha256).hexdigest()

def require_owner(record, uid):
    if not record or record.get('owner_id') != uid: raise Problem(404,'Not found.')
    return record

def validate_config(payload):
    if not isinstance(payload,dict) or set(payload)-{'name','seed','hero_color','accent_color','profile'}: raise Problem(400,'Unknown project configuration fields.')
    name=payload.get('name','Second Nature - My cut')
    seed=payload.get('seed',42)
    if not isinstance(name,str) or not 1<=len(name.strip())<=80: raise Problem(400,'Name must contain 1–80 characters.')
    if isinstance(seed,bool) or not isinstance(seed,int) or not 0<=seed<=999999: raise Problem(400,'Seed must be a whole number from 0 to 999999.')
    colors={key:payload.get(key,default) for key,default in [('hero_color','#ED785B'),('accent_color','#3D9893')]}
    if any(not isinstance(c,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',c) for c in colors.values()): raise Problem(400,'Colors must be six-digit hexadecimal values.')
    if payload.get('profile','preview')!='preview': raise Problem(400,'Cloud production currently supports Preview (960×540) only. Final rendering is available in the downloadable source.')
    return {'name':name.strip(),'seed':seed,**colors,'profile':'preview'}

def validate_job(payload):
    if not isinstance(payload,dict) or set(payload)-{'action','profile'}: raise Problem(400,'Unknown job fields.')
    action=payload.get('action','all');profile=payload.get('profile','preview')
    if action not in ACTIONS: raise Problem(400,'Choose build, render, assemble, or all.')
    if profile!='preview': raise Problem(400,'Cloud jobs use the Preview profile. Download the source for Final rendering.')
    return action,profile

def public_project(record):
    allowed=('id','name','seed','hero_color','accent_color','profile','created_at','updated_at','active_job')
    result={key:record[key] for key in allowed if key in record}
    result['artifacts']={kind:{key:meta[key] for key in ('size','updated_at','content_type') if key in meta} for kind,meta in record.get('artifacts',{}).items()}
    return result

def public_job(record):
    allowed=('id','project_id','action','profile','status','stage','progress','log','error','message','created_at','updated_at','ended_at','resume_from')
    return {key:record[key] for key in allowed if key in record}
