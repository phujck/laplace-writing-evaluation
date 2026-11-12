// Brief V4/V5 (sessions-display, 2026-11-05): what is running is shown only on owner facts. The navigation's Current
// task and Active conversation entries and the conversation row's state rest on GET /authoring/session (active, not
// ORPHANED, with its observed_at); health active_work only nominates which sessions to ask. A Work-bound row leads
// with the Work owner's own title; an unbound row keeps the lines it had at 1dff7d5cb (reference copied below).
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {register} from 'node:module';
register(new URL('./helpers/shared_resolve.mjs',import.meta.url));
import {installHTMLDocument} from './helpers/html_dom.mjs';
import {readFileSync} from 'node:fs';
const DECLARED=new Set(JSON.parse(readFileSync(new URL('./fixtures/help/controls.json',import.meta.url),'utf8')).controls.map(row=>row.id));
const {mountChrome}=await import('../src/laplace/web/static_shared/workspace-chrome.mjs');
const {WorkspaceSession,conversationMetadata,conversationRowLead,ownerRunningObservation,runningWords}=await import('../src/laplace/web/static_shared/workspace-session.mjs');

// conversationMetadata exactly as it was at 1dff7d5cb (workspace-session.mjs:213-219), the reference for unbound rows;
// wave 6 (C3): one saved turn reads '1 turn', not '1 turns'
function conversationMetadataBefore(row={}, {running=false,draft=false,loading=false}={}){
  const lines=[],created=Number(row.created_at),when=row.created_at?new Date(Number.isFinite(created)?created*1000:row.created_at):null;
  const model=row.admitted_settings;const facts=[when&&Number.isFinite(when.getTime())?'Created '+when.toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric'}):null,model?.provider||row.provider,model?.model?'Admitted '+model.model:row.model,row.role==='review'?'Independent review':row.role==='author'?'Author conversation':row.role].filter(Boolean);
  if(facts.length)lines.push(facts.join(' · '));const recorded=[row.saved_terminal_kind?'Last saved reply: '+row.saved_terminal_kind:null,row.turn_count!=null?row.turn_count+(Number(row.turn_count)===1?' turn':' turns'):null,row.retained_failure_receipts?row.retained_failure_receipts+' saved failures':null,row.artifact_receipt_count?row.artifact_receipt_count+' artifacts':null].filter(Boolean);if(recorded.length)lines.push(recorded.join(' · '));if(row.dispatch_id)lines.push('Dispatch '+row.dispatch_id);else if(row.work_id)lines.push('Work '+row.work_id);
  const observation=[running?'Last observed running':loading?'Opening':null,row.latest_admission_has_reply===false?'Latest request: no saved reply':null,draft?'Local draft retained':null].filter(Boolean);if(observation.length)lines.push(observation.join(' · '));
  return lines;
}

const el=(tag,attrs={},text='')=>{const node=document.createElement(tag);for(const [key,value] of Object.entries(attrs))node.setAttribute(key,value);if(text)node.textContent=text;return node;};
const response=value=>({ok:true,status:200,headers:{get:()=> 'application/json'},json:async()=>value,text:async()=>JSON.stringify(value)});
const AT='2026-11-05T20:47:05Z';
function chrome(session){
  const dom=installHTMLDocument({width:1440});
  const root=el('div',{class:'workspace'});document.body.append(root);
  const nav=el('nav',{class:'workspace-nav'});root.append(nav);
  for(const name of ['data-nav','data-focus','data-talk','data-guide'])root.append(el('button',{[name]:''}));
  root.append(el('aside',{'data-session':''}));root.append(el('main',{'data-main':''}));
  const ui={root,$:selector=>root.querySelector(selector),button:(label,run)=>{const b=el('button',{},label);b.onclick=run;return b;}};
  const views={current:()=>'overview',show:async()=>true,info:()=>({capabilities:{manuscript:true,work:true,materials:true,history:true,settings:true}})};
  mountChrome('garden-study',{views,ui,discussion:{session:()=>session},help:{followLayout(){}},initialQuery:new URLSearchParams(''),pageListen:(t,type,fn)=>t.addEventListener(type,fn),outline:{render:async()=>{}}});
  return {dom,root,nav,live:()=>root.querySelector('[data-nav-live]')};
}
const texts=node=>[...node.querySelectorAll('*')].filter(n=>!n.children.length).map(n=>n.textContent.trim()).filter(Boolean);

test('Current task and Active conversation appear only on owner facts and open the exact place',async()=>{
  const opened=[],works=[];let observations=[];
  const session={catalogueOpened(){},setLibrary(){},expand(){},runningObservations:()=>observations,onOpenWork:id=>works.push(id),guard:fn=>fn(),openConversation:async id=>{opened.push(id);return true;}};
  const c=chrome(session);
  try{
    assert.equal(c.live().hidden,true,'nothing observed running: no entry');assert.equal(c.live().children.length,0);
    assert.equal(c.nav.firstElementChild??c.nav.children[0],c.live(),'the entries sit at the top of the navigation');
    // an observation without its owner time is not shown (page memory is never running)
    session.onRunningObserved([{session:'WS-1',at:null,title:'Please note one observation for this task.'}]);
    assert.equal(c.live().hidden,true);
    observations=[{session:'WS-1',turn:'WT-1',at:AT,stop:true,workId:'WORK-next-observation',workTitle:'Observe both pots tomorrow',title:'Please note one observation for this task.'}];
    session.onRunningObserved(observations);
    assert.equal(c.live().hidden,false);
    const shown=texts(c.live());
    assert.deepEqual(shown.slice(0,4),['Current task','Observe both pots tomorrow','Active conversation','Please note one observation for this task.']);
    assert.match(shown[4],/^running, observed \d\d:\d\d$/);
    const [task,conversation]=c.live().querySelectorAll('button');
    assert.equal(task.dataset.navLiveEntry,'current-task');assert.equal(conversation.dataset.navLiveEntry,'active-conversation');
    // every data-control rendered while a turn is observed running is a declared control (the coverage rule of
    // workspace_control_coverage.test.mjs:32); wave 13: the two entries are declared (they carried no control identity before)
    for(const node of c.root.querySelectorAll('[data-control]'))assert.ok(DECLARED.has(node.getAttribute('data-control')),'undeclared control '+node.getAttribute('data-control'));
    assert.deepEqual([task.dataset.control,conversation.dataset.control],['nav:live-task','nav:live-conversation']);
    task.onclick();assert.deepEqual(works,['WORK-next-observation'],'Current task opens that Work');
    await conversation.onclick();assert.deepEqual(opened,['WS-1'],'Active conversation opens that conversation');
    assert.equal(c.root.classList.contains('session-open'),true,'with the conversation column open');
    // an unbound running turn shows no Current task
    session.onRunningObserved([{...observations[0],workId:null,workTitle:null}]);
    assert.deepEqual(texts(c.live()).slice(0,1),['Active conversation']);
    session.onRunningObserved([]);assert.equal(c.live().hidden,true,'the entries leave when the owner no longer reports it running');
  }finally{c.dom.restore();}
});

test('running is the owner session read: health nominates, ORPHANED and other projects never run, a finished turn clears its once-only line',async()=>{
  let held=null;const dom=installHTMLDocument({width:1440});const saved=globalThis.fetch;const asked=[];
  globalThis.fetch=async path=>{asked.push(String(path));const url=new URL(path,'http://127.0.0.1');
    if(url.pathname==='/authoring/health')return response({active_work:[{kind:'turn',project:'garden-study',session_id:'WS-run'},{kind:'turn',project:'garden-study',session_id:'WS-lost'},{kind:'turn',project:'other',session_id:'WS-other'}]});
    if(url.pathname==='/authoring/session'){const id=url.searchParams.get('id');
      if(id==='WS-run')return response({session:{title:'Running one'},active:{id:'WT-run',progress:'agent Message',observed_at:AT,work_id:'WORK-a',capabilities:{can_interrupt:true}}});
      if(id==='WS-lost')return response({session:{title:'Lost one'},active:{id:'WT-lost',progress:'ORPHANED',observed_at:AT,capabilities:{can_interrupt:true}}});
      return response({session:{title:'Ended'},active:null});}
    if(url.pathname==='/work/state')return response({view:'detail',task:{id:url.searchParams.get('id'),title:'Work A title'}});
    return response({});};
  try{
    const status=el('p',{'data-status':''},'New conversation. The previous conversation continues running.');
    const s=held=Object.assign(Object.create(WorkspaceSession.prototype),{project:'garden-study',runningSessions:new Map([['WS-ended','WT-old']]),ownerRunning:new Map(),
      find:selector=>selector==='[data-status]'?status:null,paintConversations(){},
      continuingStatus:{session:'WS-ended',text:'New conversation. The previous conversation continues running.',replacement:'New conversation; project framing and feedback remain available.'}});
    let painted=null;s.onRunningObserved=rows=>{painted=rows;};
    await s.observeRunning();
    assert.deepEqual(painted.map(row=>row.session),['WS-run'],'only the confirmed, non-ORPHANED session of this project');
    assert.deepEqual(painted[0],{session:'WS-run',turn:'WT-run',at:AT,stop:true,workId:'WORK-a',title:'Running one',workTitle:'Work A title'});
    assert.ok(!asked.some(path=>path.includes('WS-other')),'another project is not asked about');
    assert.equal(s.runningSessions.has('WS-ended'),false,'a remembered session the owner reports inactive is dropped');
    assert.equal(status.textContent,'New conversation; project framing and feedback remain available.','the once-only line leaves after the owner read');
  }finally{if(held){held.runningDisposed=true;held.syncRunningTimer();}globalThis.fetch=saved;dom.restore();}
  assert.equal(ownerRunningObservation({active:null}),null);
  assert.equal(ownerRunningObservation({active:{id:'T',progress:'RUNNING'}}),null,'no owner time, no running');
  assert.equal(ownerRunningObservation({active:{id:'T',progress:'UNKNOWN-OWNERSHIP',observed_at:AT}}),null);
  assert.equal(runningWords(null),null);
});

test('a Work-bound conversation row shows the Work title and an owner state word; an unbound one is unchanged',()=>{
  const base={id:'WS-1',title:'Please note one observation for this task.',created_at:'2026-11-05T20:45:50Z',role:'author',admitted_settings:{provider:'claude',model:'opus'},turn_count:1,latest_recorded_at:'2026-11-05T20:46:10Z',work_id:'WORK-next-observation'};
  const bound={...base,work_title:'Observe both pots tomorrow',saved_terminal_kind:'completed',latest_admission_has_reply:true};
  assert.equal(conversationRowLead(bound),'Observe both pots tomorrow');
  const finished=conversationMetadata(bound);
  assert.match(finished[0],/^finished · completed · last event \S+ \S+, \d\d:\d\d$/);
  assert.equal(finished[1],'Please note one observation for this task.');
  assert.ok(!finished.join(' ').includes('Last saved reply'),'one state word, not two');
  assert.equal(finished.at(-1),'Work WORK-next-observation');
  const running=conversationMetadata({...bound,saved_terminal_kind:null,latest_admission_has_reply:false},{running:{at:AT,stop:true}});
  assert.match(running[0],/^running, observed \d\d:\d\d · Stop applies · last event /);
  assert.ok(!running.join(' ').includes('Last observed running'));
  const unknown=conversationMetadata({...bound,saved_terminal_kind:null,latest_admission_has_reply:false},{running:{at:null}});
  assert.ok(!/running/.test(unknown.join(' ')),'no owner observation: no running word and never "not running"');
  for(const row of [{...base,work_id:undefined},{...base,saved_terminal_kind:'completed',latest_admission_has_reply:true},{id:'S',created_at:'2026-10-07T01:00:00Z',provider:'codex',model:'requested',role:'review'},{id:'S'}]){
    assert.equal(conversationRowLead(row),row.title||row.id);
    assert.deepEqual(conversationMetadata(row),conversationMetadataBefore(row));
    assert.deepEqual(conversationMetadata(row,{draft:true,loading:true}),conversationMetadataBefore(row,{draft:true,loading:true}));
  }
  const unboundRunning=conversationMetadata(base,{running:{at:AT,stop:true}});
  assert.match(unboundRunning.at(-1),/^running, observed \d\d:\d\d · Stop applies · Latest request|^running, observed \d\d:\d\d · Stop applies$/);
});

// Ruling 6 (sessions-current, 2026-11-05): while a conversation is shown running, the same observeRunning runs every 5 s;
// the timer stops when nothing is shown running, when the page is hidden, and at teardown. Fake clock: node's mock timers.
import {mock} from 'node:test';
function timerHarness(runningAfter){
  const dom=installHTMLDocument({width:1440});const saved=globalThis.fetch;const calls={session:0,health:0};let running=true;
  globalThis.fetch=async path=>{const url=new URL(path,'http://127.0.0.1');
    if(url.pathname==='/authoring/health'){calls.health++;return response({active_work:[{kind:'turn',project:'garden-study',session_id:'WS-run'}]});}
    if(url.pathname==='/authoring/session'){calls.session++;return response(running?{session:{title:'Running one'},active:{id:'WT-run',progress:'agent Message',observed_at:AT,capabilities:{can_interrupt:true}}}:{session:{title:'Running one'},active:null});}
    return response({});};
  const s=Object.assign(Object.create(WorkspaceSession.prototype),{project:'garden-study',runningSessions:new Map(),ownerRunning:new Map(),find:()=>null,paintConversations(){}});
  const rows=[];s.onRunningObserved=value=>rows.push(value.map(row=>row.session));
  return {s,calls,rows,dom,finish:()=>{running=false;},restore:()=>{globalThis.fetch=saved;dom.restore();}};
}
const settle=async()=>{for(let i=0;i<20;i++)await new Promise(ok=>setImmediate(ok));};
const tick=async(ms)=>{mock.timers.tick(ms);await settle();};
test('the running timer starts on a running observation, one tick is one owner read, a tick that shows nothing running stops it',async()=>{
  mock.timers.enable({apis:['setInterval']});const h=timerHarness();
  try{
    assert.equal(h.s.runningTimer??null,null,'no timer before any observation');
    await h.s.observeRunning();assert.deepEqual(h.rows.at(-1),['WS-run']);assert.ok(h.s.runningTimer,'armed once an observation shows a conversation running');
    const before={...h.calls};
    await tick(4999);assert.deepEqual(h.calls,before,'nothing is read before 5 seconds');
    await tick(1);assert.deepEqual(h.calls,{session:before.session+1,health:before.health+1},'one tick calls the owner reads once');
    await tick(5000);assert.equal(h.calls.session,before.session+2);
    const timer=h.s.runningTimer;await tick(5000);assert.equal(h.s.runningTimer,timer,'still the one timer, never a second');
    h.finish();await tick(5000);assert.deepEqual(h.rows.at(-1),[],'the read shows nothing running');assert.equal(h.s.runningTimer,null,'the timer is cleared by that read');
    const after=h.calls.session;await tick(30000);assert.equal(h.calls.session,after,'nothing is polled while nothing is shown running');
  }finally{h.restore();mock.timers.reset();}
});
test('a hidden page does not read; shown again it reads once and the timer resumes',async()=>{
  mock.timers.enable({apis:['setInterval']});const h=timerHarness();
  try{
    await h.s.observeRunning();assert.ok(h.s.runningTimer);
    Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});
    h.s.runningVisibilityChanged();assert.equal(h.s.runningTimer,null,'hiding the page clears the timer');
    const hidden=h.calls.session;await tick(30000);assert.equal(h.calls.session,hidden,'a hidden page reads nothing');
    await h.s.observeRunning();assert.equal(h.s.runningTimer,null,'an observation made while hidden does not re-arm it');
    Object.defineProperty(document,'hidden',{configurable:true,get:()=>false});
    h.s.runningVisibilityChanged();await settle();assert.equal(h.calls.session,hidden+2,'shown again: one read (after the one made while hidden)');assert.ok(h.s.runningTimer,'and the timer resumes while the conversation is still running');
  }finally{delete document.hidden;h.restore();mock.timers.reset();}
});
test('teardown clears the timer and a read still in flight does not re-arm it',async()=>{
  mock.timers.enable({apis:['setInterval']});const h=timerHarness();
  try{
    await h.s.observeRunning();assert.ok(h.s.runningTimer);
    const reading=h.s.observeRunning();
    const src=readFileSync(new URL('../src/laplace/web/static_shared/workspace-session.mjs',import.meta.url),'utf8');
    assert.match(src,/destroy\(\)\{[^\n]*this\.stopRunningObservation\(\);/,'destroy() calls the teardown that removes onRunningFocus');
    assert.match(src,/stopRunningObservation\(\)\{window\.removeEventListener\('focus',this\.onRunningFocus\);/,'and that teardown removes onRunningFocus');
    h.s.stopRunningObservation();await reading;
    assert.equal(h.s.runningTimer,null,'cleared at teardown, not re-armed by the read in flight');
    const calls=h.calls.session;await tick(30000);assert.equal(h.calls.session,calls,'no tick after teardown');
  }finally{h.restore();mock.timers.reset();}
});
