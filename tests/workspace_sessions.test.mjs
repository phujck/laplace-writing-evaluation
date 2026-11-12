// The Sessions page (wave 9): app=activity opens on every in-app session across projects from the owner's index read,
// opens one beside the list, stops and writes to it through the existing doors, and keeps the records one control away.
import test from 'node:test';
import assert from 'node:assert/strict';
import {installDOM,findButton} from './helpers/evidence_reader_harness.mjs';
import {mountSessionAnalytics} from '../src/laplace/web/static_shared/workspace-analytics.mjs';
import {stateText,roleText,sessionTree,sessionIndexQuery,clockText,refuseEmptySend,EMPTY_SEND_TEXT} from '../src/laplace/web/static_shared/workspace-sessions.mjs';

const NOW=new Date();const iso=minutesAgo=>new Date(NOW.getTime()-minutesAgo*60000).toISOString();
const row=(id,extra={})=>({session_id:id,project:'garden',title:'Session '+id,role:'author',provider:'claude',model:'default',effort:'high',turn_count:1,tool_failures:0,
 state:'completed',active:null,parent:null,created_at:iso(90),last_turn:{turn_id:'WT-'+id,at:iso(60),mode:'discuss',status:'completed',error:null,ended_at:iso(59)},...extra});
const index=(sessions,extra={})=>({schema_version:'laplace.session-index/1',view:'all-sessions',counts:{all:sessions.length,running:sessions.filter(r=>r.state==='running').length,waiting:0,failed:sessions.filter(r=>r.state==='failed').length},
 projects:[{project:'garden',sessions:3},{project:'herbs',sessions:1}],total:sessions.length,offset:0,limit:50,next_offset:null,sessions,observed_at:NOW.toISOString(),...extra});
const RUN=row('WS-run',{state:'running',active:{kind:'turn',turn_id:'WT-live',since:iso(4)},turn_count:2,last_turn:{turn_id:'WT-live',at:iso(4),mode:'discuss'}});
const CHILD=row('WS-child',{state:'interrupted',parent:{session_id:'WS-run',turn_id:'WT-x',title:'Session WS-run',dispatch_id:'D-1'}});
const FAIL=row('WS-fail',{project:'herbs',state:'failed',tool_failures:2,last_turn:{turn_id:'WT-f',at:iso(30),status:'failed',error:'Provider stopped',ended_at:iso(29)}});
const DONE=row('WS-done');
const summary=(id,{active=null,turns=null}={})=>({session:{id,project:'garden',provider:'claude',model:'default',effort:'high',actual_model:'stand-in-model'},
 turns:turns||[{id:'WT-a',ts:iso(10),text:'What did the second week show?',provider_settings:{provider:'claude',model:'default'},reply:{status:'completed',display_text:'The evening beds held more moisture.'}}],active});
const ACTIVE={id:'WT-live',text:'Partial reply so far',cursor:3,capabilities:{events_url:'/authoring/events?turn=WT-live',can_interrupt:true,can_steer:false}};

function fixture({sessions=[RUN,CHILD,FAIL,DONE],session=()=>summary('WS-done'),parameters=new URLSearchParams(),interval=60000,onPost=null}={}){
 const d=installDOM(),calls=[],posts=[],host=document.createElement('section');d.body.append(host);
 let current=sessions;
 const request=async(path,payload)=>{if(payload){posts.push({path,payload});if(onPost)return onPost(path,payload);return {turn_id:'WT-next'};}
  calls.push(path);if(path==='/projects/library')return {projects:[{name:'garden',title:'Garden watering study'},{name:'herbs',title:'Kitchen herb trial'}]};
  const q=new URL(path,'http://local').searchParams;
  if(path.startsWith('/authoring/state?'))return index(current);
  if(path.startsWith('/authoring/session?'))return session(q.get('id'));
  return {schema_version:'laplace.session-analytics/1',project:'',projection:q.get('projection'),scope:q.get('scope'),filters:{},as_of:'cut',read_cut:{revision:'cut'},coverage:{selected_metadata_rows:0},totals:{},items:[],pagination:{}};};
 return {d,host,calls,posts,request,set:value=>{current=value;},mount:()=>mountSessionAnalytics(host,{request,parameters,onConversation:target=>posts.push({opened:target})}),interval};
}
const rows=host=>host.querySelectorAll('li').filter(n=>n.dataset.session);
const shown=node=>{for(let n=node;n;n=n.parent)if(n.hidden===true)return false;return true;};

test('app=activity opens on every session across projects, live first, each state in words with a shape',async()=>{
 const f=fixture();try{const page=await f.mount();
  assert.equal(f.host.querySelector('h1').textContent,'Sessions');
  assert.match(f.calls.find(p=>p.startsWith('/authoring/state?')),/view=all-sessions/);
  assert.deepEqual(rows(f.host).map(n=>n.dataset.session),['WS-run','WS-child','WS-fail','WS-done']);
  const run=rows(f.host)[0];assert.equal(run.dataset.state,'running');assert.match(run.textContent,/Running since \d\d:\d\d · 4 min/);
  assert.equal(run.querySelector('.sessions-mark').textContent,'●');assert.equal(run.querySelector('.sessions-mark').getAttribute('aria-hidden'),'true');
  assert.match(run.textContent,/Garden watering study · author · claude · default · 2 turns/);
  const fail=rows(f.host)[2];assert.match(fail.textContent,/Failed (\d{1,2} \w{3} )?\d\d:\d\d: Provider stopped/)  // the fixture's time is minutes ago: shortly after midnight it falls on yesterday and carries its date;assert.match(fail.textContent,/Kitchen herb trial · author · claude · default · 1 turn · 2 tool failures/);
  assert.equal(fail.querySelector('.sessions-mark').textContent,'✕');
  assert.deepEqual(['All 4','Running 1','Waiting for you 0','Failed 1'].map(label=>!!findButton(f.host,label)),[true,true,true,true]);
  assert.match(f.host.querySelector('.sessions-read').textContent,/^Read at \d\d:\d\d:\d\d · re-read every 5 s while this page is visible$/);
  // the records stay one labelled control away, with their own controls
  const records=findButton(f.host,'Usage and records');assert.ok(records);assert.equal(shown(findButton(f.host,'Selected activity')),false);
  await records.click();assert.equal(shown(findButton(f.host,'Selected activity')),true);assert.equal(records.getAttribute('aria-current'),'page');
  for(const label of ['Overview','Graphs & analysis','Usage','Feedback','Delivery','Coverage'])assert.ok(findButton(f.host,label),label);
  page.destroy();}finally{f.d.restore();}
});

test('a dispatched session is drawn under the session that started it',async()=>{
 const f=fixture();try{const page=await f.mount();const child=rows(f.host)[1];
  assert.equal(child.dataset.depth,'1');assert.match(child.className,/sessions-child/);assert.match(child.textContent,/dispatched by Session WS-run/);
  assert.deepEqual(sessionTree([DONE,CHILD,RUN]).map(i=>[i.row.session_id,i.depth]),[['WS-done',0],['WS-run',0],['WS-child',1]]);
  assert.equal(roleText({...DONE,parent:{session_id:'WS-gone',title:null}}),'dispatched by WS-gone');assert.equal(roleText({...DONE,role:'review'}),'reviewer');
  page.destroy();}finally{f.d.restore();}
});

test('filters and the project filter read the owner again; the project he came from is chosen first',async()=>{
 const f=fixture({parameters:new URLSearchParams({from:'herbs'})});try{const page=await f.mount();
  assert.match(f.calls.find(p=>p.startsWith('/authoring/state?')),/project=herbs/);
  await findButton(f.host,'Failed 1').click();await new Promise(r=>setImmediate(r));
  const last=f.calls.filter(p=>p.startsWith('/authoring/state?')).at(-1);assert.match(last,/state=failed/);assert.match(last,/project=herbs/);
  assert.equal(findButton(f.host,'Failed 1').getAttribute('aria-pressed'),'true');
  assert.equal(sessionIndexQuery({}),'/authoring/state?view=all-sessions&limit=50');
  page.destroy();}finally{f.d.restore();}
});

test('a session opens beside the list; Stop goes only to the turn its owner reports active',async()=>{
 let active=ACTIVE;const f=fixture({session:id=>summary(id,{active,turns:[{id:'WT-live',ts:iso(4),text:'Keep going',provider_settings:{provider:'claude'}}]}),onPost:()=>({interrupted:true})});
 try{const page=await f.mount();await rows(f.host)[0].firstElementChild.click();await new Promise(r=>setImmediate(r));
  const pane=f.host.querySelector('aside');assert.equal(pane.hidden,false);assert.equal(rows(f.host).length,4);
  assert.equal(pane.querySelector('h2').textContent,'Session WS-run');assert.match(pane.textContent,/Partial reply so far/);
  assert.equal(pane.querySelector('.sessions-project-link').href,'/project?workspace=writing&corpus=garden&view=overview');
  assert.match(pane.querySelector('.sessions-in-project').href,/session=WS-run/);
  const stop=findButton(pane,'Stop');assert.equal(shown(stop),true);await stop.click();
  assert.deepEqual(f.posts.filter(p=>p.path),[{path:'/authoring/interrupt',payload:{project:'garden',turn_id:'WT-live'}}]);
  // the running turn changed between the paint and the press: nothing is stopped
  active={...ACTIVE,id:'WT-other'};const again=findButton(pane,'Stop requested')||stop;again.disabled=false;await again.click();
  assert.equal(f.posts.filter(p=>p.path==='/authoring/interrupt').length,1);assert.match(pane.textContent,/nothing was stopped/);
  // a turn its owner cannot steer keeps the message box but not a Send into it
  assert.match(pane.querySelector('.sessions-recipient').textContent,/cannot be steered/);
  await findButton(pane,'Close').click();assert.equal(pane.hidden,true);
  page.destroy();}finally{f.d.restore();}
});

test('Send starts the next turn of an idle session with its recorded provider, model and mode; a refusal keeps the text',async()=>{
 let refuse=false;const f=fixture({onPost:path=>{if(refuse)throw Error('Refused by the owner.');return {turn_id:'WT-next'};}});
 try{const page=await f.mount();await rows(f.host)[3].firstElementChild.click();await new Promise(r=>setImmediate(r));
  const pane=f.host.querySelector('aside'),box=pane.querySelector('textarea'),form=pane.querySelector('form');
  assert.match(pane.querySelector('.sessions-recipient').textContent,/^Goes to claude · default as the next turn · last answered by stand-in-model$/);
  box.value='And the third week?';await form.onsubmit({preventDefault(){}});
  const sent=f.posts.find(p=>p.path==='/authoring/turn');assert.equal(sent.payload.session_id,'WS-done');assert.equal(sent.payload.provider,'claude');assert.equal(sent.payload.model,'default');
  assert.equal(sent.payload.mode,'discuss');assert.equal(sent.payload.text,'And the third week?');assert.ok(sent.payload.request_id);assert.equal(box.value,'');
  refuse=true;box.value='Keep this';await form.onsubmit({preventDefault(){}});assert.equal(box.value,'Keep this');assert.match(pane.textContent,/Refused by the owner\. Your message is kept here\./);
  page.destroy();}finally{f.d.restore();}
});

test('wave 11 census R2b: Send with nothing typed says so beside Send, keeps the box as it is and sends nothing',async()=>{
 const f=fixture();
 try{const page=await f.mount();await rows(f.host)[3].firstElementChild.click();await new Promise(r=>setImmediate(r));
  const pane=f.host.querySelector('aside'),box=pane.querySelector('textarea'),form=pane.querySelector('form'),send=pane.querySelector('.sessions-send');
  assert.equal(send.dataset.control,'sessions:send','the pane Send carries its declared id');assert.equal(send.disabled,false,'Send stays enabled');
  const posted=f.posts.length;box.value='   ';await form.onsubmit({preventDefault(){}});
  assert.equal(f.posts.length,posted,'nothing is sent');assert.equal(box.value,'   ','the box is not touched');
  const line=pane.querySelector('.send-empty-note');assert.ok(line&&shown(line));assert.equal(line.textContent,EMPTY_SEND_TEXT);assert.equal(line.getAttribute('role'),'status');
  page.destroy();}finally{f.d.restore();}
});
test('wave 11 census R2a/R2b: the one shared refusal puts the cursor in the box and goes when he types',()=>{
 const d=installDOM();try{const row=document.createElement('div'),box=document.createElement('textarea'),send=document.createElement('button');row.append(box,send);d.body.append(row);
  let focused=0;box.focus=()=>{focused++;};const line=refuseEmptySend(box,send);
  assert.equal(line.textContent,'Write a message first.');assert.equal(focused,1);assert.equal(refuseEmptySend(box,send),line,'pressed again: one line, not two');
  }finally{d.restore();}
});
test('the list re-reads itself and changes rows in place, keeping the open session and the typed message',async()=>{
 const f=fixture();try{const page=await mountSessionAnalytics(f.host,{request:f.request,parameters:new URLSearchParams()});
  await rows(f.host)[0].firstElementChild.click();await new Promise(r=>setImmediate(r));
  const box=f.host.querySelector('aside').querySelector('textarea');box.value='half-typed';const before=rows(f.host)[0];
  f.set([{...RUN,state:'completed',active:null,last_turn:{turn_id:'WT-live',at:iso(4),status:'completed',ended_at:iso(0)}},CHILD,FAIL,DONE]);
  await page.refresh();
  const after=rows(f.host)[0];assert.equal(after,before);assert.equal(after.dataset.state,'completed');assert.match(after.textContent,/Finished \d\d:\d\d/);
  assert.equal(after.firstElementChild.getAttribute('aria-current'),'true');assert.equal(box.value,'half-typed');assert.equal(f.host.querySelector('aside').hidden,false);
  page.destroy();}finally{f.d.restore();}
});

test('nothing is shown as running unless the owner index says so; an unexpected read is said plainly',async()=>{
 const f=fixture();f.request=(orig=>async(path,payload)=>path.startsWith('/authoring/state?')?{schema_version:'laplace.session-analytics/1',items:[]}:orig(path,payload))(f.request);
 try{const page=await mountSessionAnalytics(f.host,{request:f.request,parameters:new URLSearchParams()});
  assert.equal(rows(f.host).length,0);assert.match(f.host.querySelector('.sessions-status').textContent,/nothing is shown as running/);page.destroy();}finally{f.d.restore();}
 const now=new Date('2026-11-06T10:46:00');
 assert.equal(stateText({state:'running',active:{since:'2026-11-06T10:42:00'}},now),'Running since 10:42 · 4 min');
 assert.equal(stateText({state:'interrupted',last_turn:{at:'2026-11-06T09:15:00'}},now),'Stopped 09:15');
 assert.equal(stateText({state:'failed',last_turn:{ended_at:'2026-11-06T09:15:00',error:'Battery flat'}},now),'Failed 09:15: Battery flat');
 assert.equal(stateText({state:'completed',last_turn:{ended_at:'2026-11-05T09:15:00'}},now),'Finished 5 Nov 09:15');
 assert.equal(stateText({state:'no-reply',last_turn:{at:'2026-11-06T09:15:00'}},now),'Ended without a saved reply · started 09:15');
 assert.equal(clockText('not a time'),'');
});

test('the empty workspace says there are no sessions yet, and a project mount still opens the records',async()=>{
 const f=fixture({sessions:[]});try{const page=await f.mount();assert.match(f.host.textContent,/No in-app sessions yet/);page.destroy();}finally{f.d.restore();}
 const g=fixture();try{const controller=await mountSessionAnalytics(g.host,{project:'p',request:g.request});assert.ok(!g.calls.some(p=>p.startsWith('/authoring/state?')));
  assert.equal(g.host.querySelector('h1'),null);assert.ok(findButton(g.host,'Selected activity'));controller.destroy();}finally{g.d.restore();}
});
