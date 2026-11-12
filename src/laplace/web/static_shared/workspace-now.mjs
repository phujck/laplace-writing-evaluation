// NOW (wave 9): the page the app opens on (/project?workspace=writing, app=now). Four groups, in this order, each a
// top rule and a heading, every row one click from open:
//   Running now      - the engine's live work across all projects: GET /authoring/health active_work (bounded to 16 by
//                      turn_jobs.active_work_projection; active_work_omitted counts the rest). Re-read every 5 s while
//                      the page is visible. Nothing is said to be running unless that read says so, with its time.
//   Waiting for you  - completed tasks whose evidence needs current review, across all projects: the Work catalogue the
//                      workspace Tasks page reads (GET /work/state view=catalogue currentness=REVIEW_REQUIRED), and the
//                      catalogue's own suggested next task (lifecycle_group=unfinished, planning_filter=not-deferred).
//   Continue         - the viewer's most recently opened projects (workspace-frame.mjs RECENT_KEY), up to six, from the
//                      landing's read GET /projects/library; library order when nothing was opened here yet.
//   Start            - Create a project and Bring an existing manuscript: the landing's own panels, opened there.
// Words on rows are the owners' (the task chips come from workspace-presentation.mjs taskStateChips). Storage: none of
// its own (reads RECENT_KEY). Public contract: mountNow(root,{request,storage,interval}) -> {refresh(), destroy()};
// activeWorkRow(row) (pure: the label, state word and destination of one active_work row). State words come from
// workspace-presentation.mjs ownerStateWord; the exact owner constant is the row state's title. The running dot is drawn by workspace.css.
import {pendingRead} from './pending-read.mjs';
import {taskStateChips,ownerStateWord} from './workspace-presentation.mjs';
import {recentProjects,orderByRecent} from './workspace-frame.mjs';
const el=(tag,text='',cls='')=>{const n=document.createElement(tag);if(text)n.textContent=text;if(cls)n.className=cls;return n;};
const clock=value=>{const at=value instanceof Date?value:new Date(value);return Number.isFinite(at.getTime())?at.toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}):'';};
const projectHref=(project,extra={})=>'/project?'+new URLSearchParams({workspace:'writing',corpus:project,...extra});
const appHref=(id,extra={})=>'/project?'+new URLSearchParams({workspace:'writing',app:id,...extra});

export function activeWorkRow(row={}){
  const project=typeof row.project==='string'&&row.project?row.project:null;
  const label=String(row.label||row.request_label||row.run_id||'Work in progress').replace(/\s+/g,' ').trim().slice(0,180);
  // the word comes from the one table: a research run states its own state (research_runs.active_runs), every other row its kind
  const word=row.kind==='research-run'?ownerStateWord('research-run',row.state):ownerStateWord('active-work',row.kind),state=word.words;
  let href=null,open='Open project';
  if(project&&row.session_id){href=projectHref(project,{view:'overview',conversation:'open',session:row.session_id});open='Open conversation';}
  else if(project&&row.kind==='research-run'){href=projectHref(project,{view:'research'});open='Open research';}
  else if(project)href=projectHref(project,{view:'overview'});
  const key=row.turn_id||row.run_id||row.session_id||[row.kind,project,label].join('|');
  return {key,project,label,state,provider:row.provider?String(row.provider).slice(0,40):null,exact:word.exact,exactName:row.kind==='research-run'?'Owner state: ':'Owner work kind: ',href,open};
}

function group(root,cls,heading,link=null){
  const section=el('section','','now-group '+cls),head=el('div','','now-group-head'),h=el('h2',heading);h.id=cls+'-heading';section.setAttribute('aria-labelledby',h.id);
  head.append(h);if(link)head.append(link);section.append(head);root.append(section);return section;
}
const anchor=(label,href,cls='now-action',control=null,owner=null)=>{const a=el('a',label,cls);a.href=href;if(control){a.dataset.control=control;if(owner!=null)a.dataset.controlOwner=String(owner);}return a;};

export async function mountNow(root,{request,storage,interval=5000}={}){
  root.classList.add('frame-now');root.replaceChildren();
  const heading=el('h1','Now');heading.tabIndex=-1;root.append(heading);
  const columns=el('div','','now-columns'),first=el('div','','now-column'),second=el('div','','now-column');columns.append(first,second);root.append(columns);
  let alive=true,timer=null,titles=new Map(),library=null;const seen=new Map();
  const active=()=>alive&&root.isConnected!==false;
  const titleOf=name=>titles.get(name)||name;
  // ---- Running now ----
  const running=group(first,'now-running','Running now',anchor('All sessions',appHref('activity'),'now-more','now:all-sessions'));
  const runningRead=el('p','','now-read');runningRead.setAttribute('role','status');const runningRows=el('ul','','now-rows');running.append(runningRead,runningRows);
  let firstRead=true,readingLive=false;
  async function readLive(){
    if(!active()||readingLive)return;readingLive=true;if(firstRead)pendingRead(runningRead,'Reading live work…');
    try{const health=await request('/authoring/health');if(!active())return;firstRead=false;const at=new Date();
      const rows=(Array.isArray(health?.active_work)?health.active_work:[]).map(activeWorkRow);runningRows.replaceChildren();
      for(const row of rows){if(!seen.has(row.key))seen.set(row.key,at);
        const item=el('li','','now-row now-row-running'),main=el('div','','now-row-main');
        main.append(el('strong',row.label,'now-row-title'));
        const meta=el('span','','now-row-meta');const stateNode=el('span',row.state,'now-state');stateNode.title=row.exactName+String(row.exact);meta.append(stateNode,document.createTextNode(' · '+[row.project?titleOf(row.project):'No project named',row.provider,'first seen '+clock(seen.get(row.key))].filter(Boolean).join(' · ')));main.append(meta);
        item.append(main);if(row.href)item.append(anchor(row.open,row.href,'now-action','now:open-running',row.key));runningRows.append(item);}
      for(const key of [...seen.keys()])if(!rows.some(row=>row.key===key))seen.delete(key);
      const omitted=Number(health?.active_work_omitted)||0;
      runningRead.textContent=rows.length?('Read at '+clock(at)+' from the engine’s live work'+(omitted?'; '+omitted+' more not listed by the engine.':'.')):('Nothing is running in any project. Read at '+clock(at)+'.');
      running.dataset.count=String(rows.length);
    }catch(error){if(active()){runningRows.replaceChildren();runningRead.textContent='Live work could not be read at '+clock(new Date())+': '+error.message;runningRead.classList.add('error');running.dataset.count='unknown';}}
    finally{readingLive=false;}
  }
  // ---- Waiting for you ----
  const waiting=group(first,'now-waiting','Waiting for you',anchor('All tasks',appHref('backlog'),'now-more','now:all-tasks'));
  const waitingRead=el('p','','now-read');waitingRead.setAttribute('role','status');const waitingCount=el('p','','now-count'),waitingRows=el('ul','','now-rows'),suggested=el('div','','now-suggested');waiting.append(waitingCount,waitingRows,suggested,waitingRead);
  const taskRow=row=>{const item=el('li','','now-row'),main=el('div','','now-row-main');main.append(el('strong',row.title||row.id,'now-row-title'));
    const chip=taskStateChips(row)[0];main.append(el('span',[titleOf(row.namespace),chip?.label].filter(Boolean).join(' · '),'now-row-meta'));
    item.append(main,anchor('Open task',projectHref(row.namespace,{view:'work',work:row.id}),'now-action','now:open-task',row.namespace+'::'+row.id));return item;};
  async function readWaiting(){
    pendingRead(waitingRead,'Reading the Work catalogue across all projects…');
    try{const [review,next]=await Promise.all([request('/work/state?'+new URLSearchParams({view:'catalogue',currentness:'REVIEW_REQUIRED',limit:'5'})),
        request('/work/state?'+new URLSearchParams({view:'catalogue',lifecycle_group:'unfinished',planning_filter:'not-deferred',limit:'1'}))]);
      if(!active())return;const total=Number(review?.coverage?.matching_work??(review?.rows||[]).length)||0;waitingRows.replaceChildren();suggested.replaceChildren();
      waitingCount.textContent=total?(total+' completed task'+(total===1?' needs':'s need')+' current review across all projects.'):'No completed task needs current review in any project.';
      for(const row of (review?.rows||[]).slice(0,5))waitingRows.append(taskRow(row));
      if(total>5){const more=el('li','','now-row now-row-more');more.append(el('span',(total-5)+' more on the All tasks page.','now-row-meta'),anchor('Open All tasks',appHref('backlog'),'now-action','now:open-all-tasks'));waitingRows.append(more);}
      const s=next?.suggested_next;
      if(s?.state==='SUGGESTED'&&s.namespace&&s.id){const item=el('div','','now-row now-row-suggested'),main=el('div','','now-row-main');main.append(el('span','Suggested next to inspect','now-row-label'),el('strong',s.title||s.id,'now-row-title'),el('span',titleOf(s.namespace)+' · Ready','now-row-meta'));item.append(main,anchor('Open task',projectHref(s.namespace,{view:'work',work:s.id}),'now-action','now:open-suggested-task',s.namespace+'::'+s.id));suggested.append(item);}
      waitingRead.textContent='Read at '+clock(new Date())+' from the Work catalogue (all projects).';
    }catch(error){if(active()){waitingRead.textContent='The Work catalogue could not be read: '+error.message;waitingRead.classList.add('error');}}
  }
  // ---- Continue ----
  const cont=group(second,'now-continue','Continue',anchor('All projects',appHref('projects'),'now-more','now:all-projects'));
  const contRows=el('ul','','now-rows pw-library');cont.append(contRows);
  async function readLibrary(){
    const status=pendingRead(el('p','','now-read'),'Reading your projects…');cont.append(status);
    try{const value=await request('/projects/library');if(!active())return;library=value?.projects||[];titles=new Map(library.map(row=>[row.name,row.title||row.name]));status.remove();
      const rows=orderByRecent(library,recentProjects(storage)).slice(0,6);contRows.replaceChildren();
      for(const row of rows){const item=el('li','','now-row now-row-project'),main=el('div','','now-row-main'),whole=row.title||row.name;const t=el('a',whole,'now-row-title now-project-title');t.dataset.control='now:project-title';t.dataset.controlOwner=row.name;t.href=projectHref(row.name,{view:'overview'});t.title=whole;main.append(t);
        if(row.creation?.status==='failed')main.append(el('span','Creation needs attention. Open the project to inspect its recorded outcome.','now-row-meta'));
        const actions=el('div','','now-row-actions');if(!row.source_optional)actions.append(anchor('Continue writing',projectHref(row.name,{view:'manuscript'}),'now-action','now:project-writing',row.name));actions.append(anchor('Tasks',projectHref(row.name,{view:'work'}),'now-action','now:project-tasks',row.name),anchor('Open',projectHref(row.name,{view:'overview'}),'now-action','now:project-open',row.name));
        item.append(main,actions);contRows.append(item);}
      if(!rows.length)contRows.append(el('li','No projects yet. Create one below.','now-row now-empty'));
    }catch(error){if(active()){status.textContent='Projects could not be read: '+error.message;status.classList.add('error');}}
  }
  // ---- Start ----
  const start=group(second,'now-start','Start');const startRow=el('div','','now-start-actions');
  startRow.append(anchor('Create a project',appHref('projects',{start:'create'}),'now-action','now:create-project'),anchor('Bring an existing manuscript',appHref('projects',{start:'existing'}),'now-action','now:bring-manuscript'));start.append(startRow);
  // the library first (its titles name the projects in the other groups), then the two live groups together
  await readLibrary();
  await Promise.all([readLive(),readWaiting()]);
  const tick=()=>{if(!active()){clearInterval(timer);return;}if(globalThis.document?.hidden)return;readLive();};
  if(typeof setInterval==='function'&&interval>0)timer=setInterval(tick,interval);
  const visible=()=>{if(active()&&!document.hidden){readLive();readWaiting();}};document.addEventListener?.('visibilitychange',visible);
  return {refresh:()=>Promise.all([readLive(),readWaiting()]),destroy(){alive=false;clearInterval(timer);document.removeEventListener?.('visibilitychange',visible);}};
}
