'use strict';
const $ = id => document.getElementById(id);
let csrf = '', user = null, authMode = 'register', state = null, selected = null, toastTimer;
const activeStates = ['queued','running','cancelling'];
function toast(message) { $('toast').textContent=message; $('toast').hidden=false; clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('toast').hidden=true,6000); }
async function request(path, data) {
  const response = await fetch(path, data === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) {
    if (response.status===401 && user) { user=null; showAuth(); }
    throw new Error(result.error || 'The request could not be completed.');
  }
  return result;
}
function showAuth() { $('auth-dialog').showModal(); $('logout').hidden=true; $('logout-mobile').hidden=true; $('account').textContent='Local creator workspace'; }
function element(tag, cls, text) {const el=document.createElement(tag);if(cls) el.className=cls;if(text!==undefined) el.textContent=text;return el;}
function button(label, action, cls='secondary') {const el=element('button','button '+cls,label);el.type='button';el.addEventListener('click',action);return el;}
function mediaURL(project, file) {return '/media/'+encodeURIComponent(project)+'/'+file.split('/').map(encodeURIComponent).join('/');}
function updatePreview(project) {
  selected=project?.id || null;
  const ownVideo=project?.assets.video;
  const url=ownVideo ? mediaURL(project.id,'second-nature.mp4') : state.demo_video ? mediaURL('demo','film/second-nature.mp4') : null;
  const video=$('film'); const poster=$('poster');
  video.hidden=!url; poster.hidden=true; $('placeholder').hidden=Boolean(url);
  if (url && video.getAttribute('src')!==url) {video.src=url;video.load();}
  if (!url && state.stills.length) {poster.src=mediaURL('demo','stills/'+state.stills[0]);poster.hidden=false;$('placeholder').hidden=true;}
  $('preview-badge').textContent=ownVideo ? 'PRODUCTION / '+project.config.profile.toUpperCase() : state.demo_video ? 'FEATURED / COMPLETE FILM' : state.stills.length ? 'LOOK DEVELOPMENT / RENDERED FRAME' : 'STUDIO / AWAITING RENDER';
  $('preview-caption').textContent=ownVideo ? project.name+' · Seed '+project.config.seed+'. Your assembled film is ready to review.' : state.demo_video ? 'The complete Second Nature film. Create your own production below to explore a new seed and palette.' : 'One luminous drop races through a precision machine to reach a dry seed. Speed resolves into stillness; a sculptural flower unfolds.';
}
function renderProjects() {
  const list=$('project-list'); list.replaceChildren();
  $('production-count').textContent=state.projects.length+' production'+(state.projects.length===1?'':'s');
  if (!state.projects.length) {
    const empty=element('div','empty');empty.append(element('span','empty-symbol','↗'),element('h3','','Your next frame starts here.'),element('p','','Create a production to choose its palette, seed, and render profile.'),button('Create first production',openProject));list.append(empty);
  }
  const active=state.jobs.some(j=>activeStates.includes(j.status));
  for (const p of state.projects) {
    const row=element('div','project-row'); const icon=element('div','project-icon','◈'); const details=element('div','project-details');
    details.append(element('div','project-name',p.name),element('div','project-meta','SEED '+p.config.seed+'  /  '+p.config.profile.toUpperCase()+'  /  '+p.assets.frames+' FRAMES'+(p.assets.blend?'  /  SCENE READY':'')));
    const actions=element('div','project-actions');
    for(const [kind,label] of [['build','01 Build'],['render','02 Render'],['assemble','03 Assemble']]) {
      const b=button(label,()=>runJob(p.id,kind),kind==='build'?'secondary':'secondary');b.disabled=active || !state.pipeline_ready;
      b.title=active?'A production job is already active.':!state.pipeline_ready?'Pipeline is not installed yet.':kind==='render'?'Render can take several minutes or longer.':'Run '+kind;
      actions.append(b);
    }
    if(p.assets.video) actions.append(button('▶ Play',()=>{updatePreview(p);$('preview').scrollIntoView({behavior:'smooth',block:'center'});},'primary'));
    if(p.assets.blend) {const a=element('a','asset-link','↓ .blend');a.href=mediaURL(p.id,'second-nature.blend');a.setAttribute('download','second-nature.blend');actions.append(a);}
    row.append(icon,details,actions);list.append(row);
  }
}
function renderJobs() {
  const job=state.jobs.find(j=>activeStates.includes(j.status)) || state.jobs[0];
  $('cancel-job').hidden=!job || !activeStates.includes(job.status);
  if(!job){$('job-detail').textContent='No active production job.';$('job-log').textContent='Your production output will appear here.\n\nNo hidden queues. No simulated progress.';$('job-progress').hidden=true;return;}
  const project=state.projects.find(p=>p.id===job.project_id);
  $('job-detail').textContent=(project?.name || 'Production')+' / '+job.kind+' / '+job.status;
  const log=$('job-log');const follow=log.scrollHeight-log.scrollTop-log.clientHeight<50;log.textContent=job.log || (job.status==='queued'?'Waiting for the local process to start…':'Waiting for process output…');if(follow)log.scrollTop=log.scrollHeight;
  const progress=$('job-progress');progress.hidden=!activeStates.includes(job.status);
  // Use actual renderer completions; incomplete output leaves an activity bar.
  const reported = parseRenderProgress(job.log);
  if(reported){progress.max=reported.max;progress.value=reported.value;}
  else {progress.removeAttribute('value');progress.removeAttribute('max');}
  $('cancel-job').onclick=async()=>{try{await request('/api/cancel',{job_id:job.id});toast('Cancellation requested. Waiting for the local process to stop.');await refresh();}catch(e){toast(e.message);}};
}
function renderGallery() {
  const gallery=$('gallery');gallery.replaceChildren();$('gallery-section').hidden=!state.stills.length;
  state.stills.forEach((name,i)=>{const figure=element('figure');const img=element('img');img.src=mediaURL('demo','stills/'+name);img.alt='Second Nature Blender render '+(i+1);img.loading='lazy';figure.append(img,element('figcaption','','Frame study '+String(i+1).padStart(2,'0')));gallery.append(figure);});
}
async function refresh() {
  if(!user) return;
  try {
    const previous=state;state=await request('/api/state');renderProjects();renderJobs();
    $('pipeline-status').textContent=state.pipeline_ready?'PIPELINE READY':'PIPELINE NOT INSTALLED';
    const current=state.projects.find(p=>p.id===selected);
    if(!previous || JSON.stringify(previous.stills)!==JSON.stringify(state.stills))renderGallery();
    if(!previous || previous.demo_video!==state.demo_video || current?.assets.video!==previous.projects.find(p=>p.id===selected)?.assets.video)updatePreview(current);
  }catch(e){toast(e.message);}
}
function openProject() {if(!user)return showAuth();$('project-error').textContent='';$('project-dialog').showModal();}
async function runJob(projectId, kind) {try{await request('/api/jobs',{project_id:projectId,kind});toast(kind==='render'?'Render started. Progress appears in the workbench.':'Production job started.');await refresh();$('workbench').scrollIntoView({behavior:'smooth'});}catch(e){toast(e.message);}}
$('auth-form').addEventListener('submit',async event=>{
  event.preventDefault();$('auth-error').textContent='';$('auth-submit').disabled=true;
  try{const result=await request('/api/'+authMode,{email:$('email').value,password:$('password').value});csrf=result.csrf;user=result.user;$('password').value='';$('auth-dialog').close();$('logout').hidden=false;$('logout-mobile').hidden=false;$('account').textContent=user.email;await refresh();}
  catch(e){$('auth-error').textContent=e.message;}finally{$('auth-submit').disabled=false;}
});
$('auth-toggle').addEventListener('click',()=>{
  authMode=authMode==='register'?'login':'register';const register=authMode==='register';
  $('auth-title').textContent=register?'Welcome to the studio.':'Welcome back.';
  $('auth-description').textContent=register?'Create a local account to save productions and run the Blender pipeline.':'Sign in to continue your local productions.';
  $('auth-submit').textContent=register?'Create local account →':'Sign in →';
  $('auth-toggle').textContent=register?'Already have an account? Sign in':'New to the studio? Create an account';
  $('password').autocomplete=register?'new-password':'current-password';$('auth-error').textContent='';
});
$('auth-dialog').addEventListener('cancel',event=>event.preventDefault());
$('new-production').addEventListener('click',openProject);$('empty-create').addEventListener('click',openProject);$('close-project').addEventListener('click',()=>$('project-dialog').close());
$('project-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget;const data=Object.fromEntries(new FormData(form));data.seed=Number(data.seed);const submit=form.querySelector('[type=submit]');submit.disabled=true;$('project-error').textContent='';
  try{const result=await request('/api/projects',data);$('project-dialog').close();selected=result.id;toast('Production created. Start with Build to generate your Blender scene.');await refresh();}catch(e){$('project-error').textContent=e.message;}finally{submit.disabled=false;}
});
async function logout(){try{const result=await request('/api/logout',{});csrf=result.csrf;user=null;state=null;selected=null;$('film').pause();$('film').removeAttribute('src');$('film').load();location.reload();}catch(e){toast(e.message);}}
$('logout').addEventListener('click',logout);$('logout-mobile').addEventListener('click',logout);
(async()=>{try{const result=await request('/api/session');csrf=result.csrf;user=result.user;if(user){$('logout').hidden=false;$('logout-mobile').hidden=false;$('account').textContent=user.email;await refresh();}else showAuth();}catch(e){toast('The studio server is unavailable. Restart it, then reload this page.');}})();
setInterval(()=>{if(!document.hidden)refresh();},2500);
