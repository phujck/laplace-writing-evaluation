// PROJECT WORK PAGE ENTRY. Purpose: mount the writing workspace and the session analytics on
// the project page from the URL's project and view. Ownership: everything is workspace.mjs',
// workspace-analytics.mjs' and workspace-session.mjs' (the projectRequest transport); this entry
// composes them once. Public contract: the default export mounts and returns the workspace.
// Inputs: location; outputs: a mounted shell. Storage: none of its own (the shell owns its keys).
import {projectRequest as api} from '/shared/writing-request.mjs';
import {pendingRead} from '/shared/pending-read.mjs';
import {guardAppNavigation,mountAppSettings,mountWorkspaceDependencies} from '/shared/workspace-app.mjs';
import {mountFrame} from '/shared/workspace-frame.mjs';
const E=(tag,text='',cls='')=>{const node=document.createElement(tag);node.textContent=text;node.className=cls;return node;};
import {declareControl} from '/shared/workspace-presentation.mjs';
const slug=value=>value.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'').slice(0,64);
// PROJECTS LANDING:BEGIN. Task-first entry uses only the actual library. Historical grouping
// remains a pure compatibility export; it is not a prerequisite for ordinary writing.
const START_HERE=[
  ['synthetics-foundations','The theory: what synthetics is and the laws the system is built on.'],
  ['eigen-technical-due-diligence-briefing','The technical due-diligence briefing: the theory of efficient representation and the working prototypes, with their evidence.'],
  ['writing-system-architecture','The living system guide: how this writing system is built and run, its design principles and its open issues.']];
const PROJECT_GROUPS=[
  ['Representation, hierarchy and learning',['cost-of-complexity','law-of-laws','synthetics-statistical-lawhood','adaptive-normal-form-aek9',
    'the-phases-of-hierarchy','operatorial-loss','variational-wrong-object','qde','free-snacks','self-consistent-loss-geometries',
    'self-consistent-loss-geometries-coupled-evaluators']],
  ['Memory and autonomous research campaigns',['corpus-as-a-state','memory-in-pieces','superarc']],
  ['Mean force and thermal geometry',['equilibrium-from-the-inside-out','dual-representatives-of-mean-force-equilibrium',
    'ground-states-mean-force-and-thermal-geometry']],
  ['Unfinished historical study',['a-little-fun-never-hurt-anybody']]];
export function groupProjects(projects){
  const byName=new Map(projects.map(row=>[row.name,row])),used=new Set();
  const take=ids=>ids.filter(id=>byName.has(id)&&!used.has(id)).map(id=>{used.add(id);return byName.get(id);});
  const start=take(START_HERE.map(([id])=>id));
  const groups=PROJECT_GROUPS.map(([title,ids])=>({title,projects:take(ids)})).filter(group=>group.projects.length);
  const other=projects.filter(row=>!used.has(row.name));
  if(other.length)groups.push({title:'Other projects',projects:other});
  return {start,groups};
}
function renderProjectLanding(host,library,E,{onCreate=()=>{}}={}){
  // A task choice only changes visible project links. It never creates a
  // project, changes a conversation target or submits an owner action.
  // Shape: heading and the live sentence; one row holding the filter, its count and Create a project;
  // the four open-at choices under one caption; the create panel's slot (hidden until asked for);
  // then the library's own order as one-line rows.
  const projects=library.projects||[],views={write:'manuscript',source:'material',tasks:'work',open:'overview'};let task='open';
  const start=E('section','','pw-start-tasks'),heading=E('h1','Your projects and writing');heading.tabIndex=-1;
  start.append(heading,E('p','Keep sources, writing and tasks together. You can read and write locally; AI conversations are optional.','pw-lead'));
  const actions=E('div','','pw-start-actions'),cue=E('p','','pw-next-step'),list=E('section','','pw-project-list');list.id='project-list';
  const listHeading=E('h2',projects.length?'Open a project':'No projects yet','sr-only');listHeading.tabIndex=-1;
  const query=E('input');query.type='search';query.placeholder='Find a project';query.setAttribute('aria-label','Find a project');
  const count=E('p','','pw-muted pw-count');count.setAttribute('role','status');
  const create=declareControl(E('button','Create a project','pw-create-toggle'),'projects:create-toggle');create.type='button';create.setAttribute('aria-expanded',String(!projects.length));create.setAttribute('aria-controls','start-project');
  const find=E('div','','pw-find');find.append(query,count,create);
  const slot=E('div','','pw-create-slot'),rows=E('div','','pw-project-choices');
  query.hidden=!projects.length;count.hidden=!projects.length;create.hidden=!projects.length;find.hidden=!projects.length;slot.hidden=Boolean(projects.length);
  list.append(listHeading,rows);list.hidden=!projects.length;
  function setCreate(open){slot.hidden=!open;create.textContent=open?'Hide the create form':'Create a project';create.setAttribute('aria-expanded',String(Boolean(open)));}
  create.onclick=()=>{const open=slot.hidden;setCreate(open);if(open)onCreate(task);};
  function paint(){rows.replaceChildren();const needle=query.value.trim().toLowerCase(),shown=projects.filter(row=>((row.title||'')+' '+row.name).toLowerCase().includes(needle));count.textContent=shown.length+' of '+projects.length+' projects';
    for(const row of shown){const whole=row.title||row.name,card=E('a','','pw-project');card.dataset.control='projects:project';card.dataset.controlOwner=row.name;card.href='/project?'+new URLSearchParams({workspace:'writing',corpus:row.name,view:row.source_optional&&task==='write'?'overview':views[task]});card.setAttribute('title',whole);card.append(E('span',whole,'pw-project-title'));
      if(task==='write')card.append(E('span',row.source_optional?'Open project and add writing':'Continue writing','pw-muted pw-project-note'));
      if(row.creation?.status==='failed')card.append(E('span','Creation needs attention. Open the project to inspect its recorded outcome.','pw-muted pw-project-alert'));rows.append(card);}
    if(!shown.length&&projects.length)rows.append(E('p','No project matches this search.','pw-muted pw-no-match'));
  }
  const caption=E('span','Clicking a project below:','pw-caption');actions.append(caption);
  for(const [id,label,note,control]of [['write','Start writing','Choose an Article or Book to begin a document.','projects:task-write'],['source','Read a source','Choose a project, then add or open its sources.','projects:task-source'],['tasks','Organise tasks','Choose a project to create or plan its tasks.','projects:task-tasks'],['open','Open existing project','Choose a project to continue.','projects:task-open']]){
    const choose=declareControl(E('button',label),control);choose.type='button';choose.dataset.startTask=id;choose.onclick=()=>{task=id;for(const item of actions.children)if(item!==caption)item.setAttribute('aria-pressed',String(item===choose));cue.textContent=note;paint();if(projects.length)listHeading.focus();else onCreate(id);};choose.setAttribute('aria-pressed',String(id===task));actions.append(choose);
  }
  start.append(find,actions,cue);host.append(start,slot,list);query.oninput=paint;paint();return {query,paint,slot,setCreate,create};
}
// PROJECTS LANDING:END
function field(form,label,name,tag='input'){const wrap=E('label',label),input=E(tag);input.name=name;wrap.append(input);form.append(wrap);return input;}
export async function initProjectWork(){
  const root=document.querySelector('#project-work');if(!root)return;
  const params=new URLSearchParams(location.search),project=params.get('project')||params.get('corpus');
  if(project){const {mountWorkspace}=await import('/shared/workspace.mjs');await mountWorkspace(root,project);return;}
  // ONE FRAME (wave 9): every workspace page sits under the same bar as a project page (workspace-frame.mjs). The app
  // opens on Now; the project list is the page app=projects. Help is the same global door, placed in the bar.
  const app=params.get('app')||'now';const frame=mountFrame({place:app,request:api,skip:true});root.before(frame.bar);root.dataset.place=app;document.body.classList.add('frame-page');const appNav=frame.bar;
  const {mountGlobalHelp}=await import('/shared/workspace-help-door.mjs');if(app!=='research'){mountGlobalHelp(root,{navigation:frame.helpSlot,view:({activity:'workspace-activity',settings:'app-settings'})[app]||app,request:api});}
  if(app==='now'){const {mountNow}=await import('/shared/workspace-now.mjs');await mountNow(root,{request:api});return;}
  if(app==='research'){const {mountResearchWorkbench}=await import('/shared/research-workbench.mjs');const controller=await mountResearchWorkbench(root,{request:api,parameters:params});window.addEventListener('beforeunload',event=>controller.leaveGuard(event));return;}
  if(app==='backlog'){const {mountBacklog}=await import('/shared/workspace-backlog.mjs');const controller=await mountBacklog(root,{request:api,parameters:params});window.addEventListener('beforeunload',event=>controller.leaveGuard(event));return;}
  if(app==='settings'){const controller=await mountAppSettings(root,{request:api});window.addEventListener('beforeunload',event=>{if(controller.hasDraft){event.preventDefault();event.returnValue='';}});return;}
  if(app==='activity'){const {mountSessionAnalytics}=await import('/shared/workspace-analytics.mjs');root.classList.add('workspace-app');const destination=(target,extra={})=>'/project?'+new URLSearchParams({workspace:'writing',corpus:target.project,...extra});await mountSessionAnalytics(root,{request:api,onConversation:target=>{location.href=destination(target,{view:'overview',session:target.id});},onTurn:target=>{location.href=destination(target,{view:'history',history_record:'activity:journal:'+target.id});},onWork:target=>{location.href=destination(target,{view:'work',work:target.id});}});return;}
  if(app==='dependencies'){await mountWorkspaceDependencies(root,{request:api,parameters:params});return;}
  if(app==='workflows'){const {mountWorkflowEditor}=await import('/shared/workspace-workflow-editor.mjs');const controller=await mountWorkflowEditor(root,{helpInDialog:(body,{isCurrent})=>mountGlobalHelp(body,{navigation:body,view:'workflows',shortcut:false,request:api,isCurrent})});guardAppNavigation(appNav,controller);window.addEventListener('beforeunload',event=>controller.leaveGuard(event));return;}
  if(app==='owners'){root.classList.add('workspace-app');const {mountOwnerDiscovery}=await import('/shared/workspace-owners.mjs');const controller=await mountOwnerDiscovery(root,{request:api,onWork:target=>{location.href='/project?'+new URLSearchParams({workspace:'writing',corpus:target.project,view:'work',work:target.id});}});window.addEventListener('beforeunload',event=>controller.leaveGuard(event));return;}
  const notice=E('p','','pw-notice');notice.setAttribute('role','status');root.before(notice);
  const guard=fn=>async event=>{event?.preventDefault();try{await fn(event);}catch(error){notice.textContent=error.message;notice.classList.add('error');}};
  const button=(label,action)=>{const b=E('button',label);b.type='button';b.onclick=guard(action);return b;};
  const panel=(title,help)=>{const p=E('section','','pw-panel');p.append(E('h2',title),E('p',help,'pw-muted'));root.append(p);return p;};
  try{
    const reading=E('p','','pw-muted pw-reading');root.append(reading);pendingRead(reading,'Reading your projects…');
    let library;try{library=await api('/projects/library');}finally{reading.remove();}
    let title,kind;const landing=renderProjectLanding(root,library,E,{onCreate:task=>{if(!title)return;kind.value=task==='write'?'paper':'general';title.focus();}});
    const create=panel('Create a project','Give it a title and purpose. Article and Book include a writing document; a General project can add writing later.');create.id='start-project';landing.slot.append(create);const form=E('form','','pw-form');title=field(form,'Working title','title');title.required=true;kind=declareControl(field(form,'Project category','kind','select'),'projects:category');for(const [value,label]of [['general','General project'],['paper','Article'],['book','Book'],['software','Software'],['company','Company'],['transcript','Transcript'],['campaign','Campaign']]){const o=E('option',label);o.value=value;kind.append(o);}field(form,'Purpose','purpose','textarea');field(form,'Audience','audience');form.append(declareControl(E('button','Create project','pw-primary'),'projects:create'));form.onsubmit=guard(async()=>{const values=Object.fromEntries(new FormData(form));const made=await api('/projects/create',{...values,name:slug(values.title)});location.href='/project?workspace=writing&corpus='+encodeURIComponent(made.project||made.name||slug(values.title))+'&view=overview';});create.append(form);
    const existing=panel('Bring an existing manuscript','Register its source while preserving the original files.');existing.id='start-existing';existing.append(declareControl(button('Find existing manuscripts',async()=>{const found=await api('/projects/discover');const list=E('div','','pw-library');for(const item of found.candidates||[]){const card=E('article','','pw-project');card.append(E('h3',item.title),E('p',item.root,'pw-muted'));const permission=E('label','Allow editing this source'),editable=E('input');editable.type='checkbox';permission.prepend(editable);card.append(permission,button('Add manuscript',async()=>{const name=slug(item.title).slice(0,55)+'-'+Math.random().toString(36).slice(2,6);await api('/projects/import',{name,title:item.title,root:item.root,editable:editable.checked});location.href='/project?workspace=writing&corpus='+name;}));list.append(card);}existing.append(list);notice.textContent=found.candidates?.length?'Choose a source to bring into the workspace.':'All discovered manuscripts are registered.';}),'projects:find-existing'));
    // Reached from Now's Start group: the landing's own create panel opened, or its existing-manuscript panel in view.
    const startAt=params.get('start');if(startAt==='create'){landing.setCreate(true);title.focus({preventScroll:true});create.scrollIntoView?.({block:'start'});}
    else if(startAt==='existing'){existing.scrollIntoView?.({block:'start'});existing.querySelector('button')?.focus({preventScroll:true});}
  }catch(error){notice.textContent=error.message;notice.classList.add('error');}
}
