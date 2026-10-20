"""Firebase-authenticated production API; both /v1 and Hosting's /api/v1 work."""
import functools, json, logging, os, re
from datetime import datetime, timezone
import firebase_admin
from firebase_admin import auth
from fastapi import APIRouter, Depends, FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from .domain import ARTIFACT_FILES, MIME_TYPES, Problem, TERMINAL, ip_key, public_job, public_project, validate_config, validate_job
from .repository import Repository
from .services import Artifacts, Launcher, SHOWCASE_FILES, showcase_key

@functools.lru_cache
def dependencies():
    project=os.getenv('AUTH_PROJECT_ID') or os.getenv('FIREBASE_PROJECT_ID') or os.getenv('GOOGLE_CLOUD_PROJECT')
    if not project:raise RuntimeError('AUTH_PROJECT_ID or GOOGLE_CLOUD_PROJECT must be configured.')
    if not firebase_admin._apps:firebase_admin.initialize_app(options={'projectId':project})
    if not os.getenv('RATE_LIMIT_SALT'):raise RuntimeError('RATE_LIMIT_SALT must be configured.')
    return Repository(),Launcher(),Artifacts()

def verified_user(authorization=Header(default='')):
    if not authorization.startswith('Bearer ') or len(authorization)>8192:raise Problem(401,'Sign in to continue.')
    try:
        dependencies()
        token=auth.verify_id_token(authorization[7:],check_revoked=False)
        if not token.get('uid'):raise ValueError('Missing identity')
        return token
    except Problem:raise
    except Exception as exc:raise Problem(401,'Your sign-in session expired. Sign in again.') from exc

def portable_config(project):return {key:project[key] for key in ('name','seed','hero_color','accent_color','profile')} | {'output_dir':'./second-nature-output'}
def config_bytes(project):return (json.dumps(portable_config(project),indent=2)+'\n').encode()

def blob_response(blob,size,media_type,request,headers):
    """Stream a bounded single byte range; HEAD returns identical headers only."""
    start,end,status=0,size-1,200
    requested=request.headers.get('range')
    if requested:
        match=re.fullmatch(r'bytes=(\d{0,20})-(\d{0,20})',requested)
        if not match or not any(match.groups()):
            return JSONResponse({'error':'Invalid byte range.'},status_code=416,headers={'Content-Range':f'bytes */{size}','Accept-Ranges':'bytes'})
        if match[1]:start=int(match[1]);end=min(end,int(match[2])) if match[2] else end
        else:start=max(0,size-int(match[2]))
        if start>end or start>=size:
            return JSONResponse({'error':'Invalid byte range.'},status_code=416,headers={'Content-Range':f'bytes */{size}','Accept-Ranges':'bytes'})
        status=206;headers['Content-Range']=f'bytes {start}-{end}/{size}'
    headers['Content-Length']=str(max(0,end-start+1))
    if request.method=='HEAD':return Response(status_code=status,media_type=media_type,headers=headers)
    def stream():
        with blob.open('rb',chunk_size=1024*1024) as handle:
            handle.seek(start);remaining=end-start+1
            while remaining:
                block=handle.read(min(65536,remaining))
                if not block:break
                yield block;remaining-=len(block)
    return StreamingResponse(stream(),status_code=status,media_type=media_type,headers=headers)

def create_app(deps=None,verify=None):
    application=FastAPI(title='Second Nature Production API',version='1.0.0',docs_url=None,redoc_url=None)
    project=os.getenv('AUTH_PROJECT_ID') or os.getenv('FIREBASE_PROJECT_ID') or os.getenv('GOOGLE_CLOUD_PROJECT') or 'second-nature-studio'
    origins=os.getenv('ALLOWED_ORIGINS',f'https://{project}.web.app,https://{project}.firebaseapp.com').split(',')
    application.add_middleware(CORSMiddleware,allow_origins=[v.strip() for v in origins if v.strip()],allow_methods=['GET','HEAD','POST','OPTIONS'],allow_headers=['Authorization','Content-Type','Range'],expose_headers=['Content-Length','Content-Range','Content-Disposition','Accept-Ranges'])
    get_deps=deps or dependencies;get_user=verify or verified_user
    @application.exception_handler(Problem)
    async def expected_error(request,exc):return JSONResponse({'error':exc.detail},status_code=exc.status,headers={'Cache-Control':'no-store'})
    @application.exception_handler(Exception)
    async def unexpected_error(request,exc):
        logging.exception('Production API request failed')
        return JSONResponse({'error':'The production service is temporarily unavailable. Please retry.'},status_code=503,headers={'Cache-Control':'no-store'})
    @application.middleware('http')
    async def security(request,call_next):
        length=request.headers.get('content-length')
        if length and (not length.isdigit() or int(length)>16384):return JSONResponse({'error':'Request too large.'},status_code=413)
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff';response.headers['Referrer-Policy']='no-referrer'
        public_paths={prefix+'/v1/showcase/'+name for prefix in ('','/api') for name in SHOWCASE_FILES}
        response.headers['Cache-Control']='public, max-age=3600' if request.url.path in public_paths and response.status_code in (200,206) else 'no-store'
        return response
    @application.api_route('/healthz',methods=['GET','HEAD'])
    @application.api_route('/api/healthz',methods=['GET','HEAD'])
    def health():return {'ok':True,'service':'second-nature-api'}
    router=APIRouter()
    def reconcile_job(repo,launcher,job):
        job=repo.reconcile(job)
        heartbeat=job.get('heartbeat_at',job.get('updated_at',job['created_at']))
        quiet=(datetime.now(timezone.utc)-datetime.fromisoformat(heartbeat)).total_seconds()>90
        if job.get('status') not in TERMINAL and job.get('execution') and (job['status']=='cancelling' or quiet):
            try:
                remote=launcher.status(job['execution'])
                if remote.get('finished'):
                    status='cancelled' if remote.get('cancelled') or job['status']=='cancelling' else 'interrupted'
                    repo.finish(job['id'],status,'The cloud execution stopped. Saved frames can be resumed.')
                    job=repo.get_job(job['id'],job['owner_id'])
            except Exception:logging.warning('Execution reconciliation unavailable; retaining its reservation')
        return job
    def budget_ip(request):
        # Cloud Run appends the trusted forwarding hop. Global quotas remain the
        # primary hard budget even if a deployment's proxy topology changes.
        forwarded=request.headers.get('x-forwarded-for','')
        ip=forwarded.split(',')[-1].strip() if forwarded else request.client.host
        return ip_key(ip,os.environ.get('RATE_LIMIT_SALT','test-only-injected-dependency'))
    @router.api_route('/v1/showcase/{filename}',methods=['GET','HEAD'])
    def showcase(filename:str,request:Request):
        # Validate before constructing any storage client or reading an object.
        showcase_key(filename)
        _,_,store=get_deps();blob,meta=store.describe_showcase(filename)
        return blob_response(blob,meta['size'],'video/mp4',request,
                             {'Content-Disposition':f'inline; filename="{filename}"','Accept-Ranges':'bytes'})
    @router.get('/v1/me')
    def me(request:Request,user=Depends(get_user)):
        repo,_,_=get_deps()
        return {'uid':user['uid'],'anonymous':user.get('firebase',{}).get('sign_in_provider')=='anonymous','quota':repo.quota(user['uid'],budget_ip(request))}
    @router.get('/v1/projects')
    def projects(user=Depends(get_user)):
        repo,_,_=get_deps();return {'projects':[public_project(p) for p in repo.list_projects(user['uid'])]}
    @router.post('/v1/projects',status_code=201)
    def create_project(payload:dict,request:Request,user=Depends(get_user)):
        repo,_,_=get_deps();return public_project(repo.create_project(user['uid'],validate_config(payload),budget_ip(request)))
    @router.get('/v1/projects/{pid}')
    def project(pid:str,user=Depends(get_user)):
        repo,launcher,_=get_deps();p=repo.get_project(pid,user['uid'])
        jobs=[public_job(reconcile_job(repo,launcher,j)) for j in repo.list_jobs(pid,user['uid'])]
        return {'project':public_project(p),'jobs':jobs}
    def dispatch(repo,launcher,record):
        try:
            operation=launcher.start(record['id']);repo.update_job(record['id'],{'operation':operation})
        except Exception as exc:
            from google.api_core.exceptions import PermissionDenied,InvalidArgument,NotFound,FailedPrecondition
            if isinstance(exc,(PermissionDenied,InvalidArgument,NotFound,FailedPrecondition)):
                repo.finish(record['id'],'failed','The worker could not be dispatched. The operator must check its Cloud Run configuration.')
                raise Problem(503,'The render worker is unavailable. No animation was produced.') from exc
            # A timed-out API acknowledgement does not prove that dispatch failed.
            # Retain the reservation; a real worker may still claim this job.
            repo.update_job(record['id'],{'message':'Worker dispatch acknowledgement is pending. Refresh to observe its actual state.'})
        return public_job(repo.get_job(record['id'],record['owner_id']))
    @router.post('/v1/projects/{pid}/jobs',status_code=202)
    def start_job(pid:str,payload:dict,request:Request,user=Depends(get_user)):
        repo,launcher,_=get_deps();action,profile=validate_job(payload);p=repo.get_project(pid,user['uid'])
        if action in ('render','assemble') and not p.get('artifacts',{}).get('blend'):raise Problem(409,'Build this production first, or choose the complete production workflow.')
        record=repo.reserve_job(user['uid'],pid,action,profile,budget_ip(request));return dispatch(repo,launcher,record)
    @router.get('/v1/jobs/{jid}')
    def get_job(jid:str,user=Depends(get_user)):
        repo,launcher,_=get_deps();return public_job(reconcile_job(repo,launcher,repo.get_job(jid,user['uid'])))
    @router.post('/v1/jobs/{jid}/cancel')
    def cancel_job(jid:str,user=Depends(get_user)):
        repo,launcher,_=get_deps();record=repo.request_cancel(jid,user['uid'])
        if record.get('_was_queued'):repo.finish(jid,'cancelled')
        elif record.get('execution'):
            try:launcher.cancel(record['execution'])
            except Exception:logging.warning('Execution cancellation API unavailable; worker polling remains active')
        return public_job(repo.get_job(jid,user['uid']))
    @router.post('/v1/jobs/{jid}/resume',status_code=202)
    def resume_job(jid:str,request:Request,user=Depends(get_user)):
        repo,launcher,_=get_deps();old=reconcile_job(repo,launcher,repo.get_job(jid,user['uid']))
        if old['status'] not in ('cancelled','failed','interrupted'):raise Problem(409,'Only a cancelled, failed, or interrupted job can be resumed.')
        record=repo.reserve_job(user['uid'],old['project_id'],old['action'],old['profile'],budget_ip(request),resume_from=jid)
        return dispatch(repo,launcher,record)
    @router.get('/v1/projects/{pid}/artifacts/{kind}')
    def artifact(pid:str,kind:str,request:Request,user=Depends(get_user)):
        repo,_,store=get_deps();p=repo.get_project(pid,user['uid'])
        if kind not in ARTIFACT_FILES:raise Problem(404,'Artifact not found.')
        if kind=='config':meta={'size':len(config_bytes(p)),'content_type':MIME_TYPES[kind]}
        else:_,meta=store.describe(user['uid'],pid,kind)
        prefix='/api' if request.url.path.startswith('/api/') else ''
        return {'url':f'{prefix}/v1/projects/{pid}/artifacts/{kind}/content','requires_auth':True,'filename':ARTIFACT_FILES[kind],**meta}
    @router.get('/v1/projects/{pid}/artifacts/{kind}/content')
    def artifact_content(pid:str,kind:str,request:Request,user=Depends(get_user)):
        repo,_,store=get_deps();p=repo.get_project(pid,user['uid'])
        if kind not in ARTIFACT_FILES:raise Problem(404,'Artifact not found.')
        disposition='inline' if kind in ('movie','poster') else 'attachment'
        headers={'Content-Disposition':f'{disposition}; filename="{ARTIFACT_FILES[kind]}"','Accept-Ranges':'bytes'}
        if kind=='config':
            from fastapi.responses import Response
            return Response(config_bytes(p),media_type=MIME_TYPES[kind],headers=headers)
        blob,meta=store.describe(user['uid'],pid,kind)
        return blob_response(blob,meta['size'],MIME_TYPES[kind],request,headers)
    application.include_router(router);application.include_router(router,prefix='/api')
    return application

app=create_app()
