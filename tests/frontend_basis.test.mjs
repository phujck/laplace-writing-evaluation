// P2 service spine, page side: the neutral owner request and its Writing adapter (owner-request.mjs + projectRequest),
// the shared selected lifetime (selected-lifetime.mjs) and the page-issued frontend basis with its explicit, draft-safe
// refresh in the actual shell (workspace.mjs over tests/helpers/shell_fixture.mjs owner doubles). The two bases are the
// real frozen snapshots the guarded case tests/test_frontend_basis.py publishes (FRONTEND_BASIS names its file); this
// process imports no Laplace code.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
import {ownerRequest} from '../src/laplace/web/static_shared/owner-request.mjs';
import {createSelectedLifetime} from '../src/laplace/web/static_shared/selected-lifetime.mjs';
import {fixtures} from './helpers/source_effect_fixture.mjs';
import {inspectRefreshCarry,acknowledgeRefreshCarry} from '../src/laplace/web/static_shared/frontend-basis.mjs';
const {mountShell,ownerReply}=await import('./helpers/shell_fixture.mjs');
const {projectRequest}=await import('../src/laplace/web/static_shared/workspace-session.mjs');

const basesFile=process.env.FRONTEND_BASIS;
const bases=basesFile&&existsSync(basesFile)?JSON.parse(readFileSync(basesFile,'utf8')):null;
const reply=(status,value)=>({ok:status<300,status,headers:{get:()=>'application/json'},json:async()=>structuredClone(value),text:async()=>JSON.stringify(value)});

test('transport: GET/POST carriage, the source effect is announced before its completion refusal, owner bodies, connection and abort stay uncertain, another origin is never sent',async()=>{
  const saved={fetch:globalThis.fetch,window:globalThis.window,location:globalThis.location};
  const calls=[],events=[];let next=null;
  globalThis.location={href:'http://local/project?corpus=book'};globalThis.window=new EventTarget();
  for(const type of ['laplace-source-effect','laplace-workspace-connection'])window.addEventListener(type,event=>events.push(type==='laplace-source-effect'?event.detail.status||'effect':type));
  globalThis.fetch=async(path,init)=>{calls.push({path,init});return next(path,init);};
  try{
    next=()=>reply(200,{tasks:[]});
    assert.deepEqual(await projectRequest('/work/state?project=book&view=summary'),{tasks:[]});
    assert.deepEqual(calls[0],{path:'/work/state?project=book&view=summary',init:{method:'GET',headers:{},body:undefined}});
    next=()=>reply(201,{ok:true});
    await projectRequest('/work/task',{project:'book',id:'W'});
    assert.deepEqual(calls[1].init,{method:'POST',headers:{'Content-Type':'application/json','X-Laplace-Writing':'1'},body:'{"project":"book","id":"W"}'});
    // a partial source effect (the shared incomplete-effect fixture): its event is dispatched FIRST, then the reply is
    // refused with its body kept; a metadata-only reply of the same body announces nothing and is not refused for its effect
    const partial=fixtures.incomplete.result;next=()=>reply(200,partial);
    await assert.rejects(projectRequest('/visuals/place',{project:'book'}),error=>{assert.match(error.message,/incomplete/);assert.deepEqual(error.result,partial);return true;});
    assert.equal(events.length,1,'the source effect was announced before the refusal');
    next=()=>reply(200,{...partial,metadata_only:true});   // its own ok:false still refuses it, as an owner error, not an effect
    await assert.rejects(projectRequest('/visuals/place',{project:'book'}),error=>!/incomplete/.test(error.message)&&error.result.metadata_only===true);assert.equal(events.length,1);
    next=()=>reply(409,{error:'CHANGED_INPUT',code:'CHANGED_INPUT'});
    await assert.rejects(projectRequest('/work/task',{project:'book'}),error=>{assert.equal(error.result.code,'CHANGED_INPUT');assert.equal(error.transport,undefined);return true;});
    const before=events.length;
    next=()=>{throw new TypeError('Failed to fetch');};
    await assert.rejects(projectRequest('/work/task',{project:'book'}),error=>{assert.match(error.message,/local engine is unavailable/);assert.equal(error.effect,'unknown');assert.equal(error.result,undefined);return true;});
    await assert.rejects(projectRequest('/work/state?project=book'),error=>error.effect==='none');
    assert.deepEqual(events.slice(before),['laplace-workspace-connection','laplace-workspace-connection']);
    const abort=new AbortController();abort.abort();next=()=>{throw new DOMException('aborted','AbortError');};
    await assert.rejects(projectRequest('/work/task',{project:'book'},{signal:abort.signal}),error=>error.transport==='aborted'&&error.effect==='unknown');
    assert.equal(events.length,before+2,'an abort is not a lost engine');
    const sent=calls.length;
    await assert.rejects(ownerRequest('http://elsewhere.example/work/task',{project:'book'}),error=>error.transport==='refused-origin'&&error.effect==='none');
    assert.equal(calls.length,sent,'nothing was sent to another origin');
    assert.equal(calls.filter(call=>call.init.method==='POST').length,6,'every POST was sent once; none was retried');
  }finally{Object.assign(globalThis,saved);}
});

test('selected lifetime: visits, deliveries ordered by issue, leases end at replacement and disposal, disposal once',()=>{
  const region=createSelectedLifetime(),seen=[],cleaned=[];
  region.own(()=>cleaned.push('a'));region.own(()=>cleaned.push('b'));
  region.subscribe(value=>seen.push(value));
  assert.equal(region.select({project:'p',id:'X'}),true);const lease=region.lease();
  assert.equal(region.select({project:'p',id:'X'}),false);assert.equal(lease(),true,'the same qualified Work is no replacement');
  const older=region.issue('p::X'),newer=region.issue('p::X');
  assert.equal(region.admissible('p::X',newer),true);region.accept('p::X',newer);
  assert.equal(region.admissible('p::X',older),false);assert.equal(region.superseded('p::X',older),true);
  region.select({project:'q',id:'X'});assert.equal(lease(),false,'another namespace is another Work');assert.equal(region.visitDepth,1);
  assert.deepEqual(region.back(),{project:'p',id:'X'});assert.equal(region.back(),null);
  region.notify(1);assert.deepEqual(seen,[1]);
  const held=region.lease();assert.equal(region.dispose(),true);assert.equal(region.dispose(),false);
  assert.equal(held(),false);assert.deepEqual(cleaned,['b','a']);region.notify(2);assert.deepEqual(seen,[1]);
  assert.throws(()=>region.subscribe(()=>{}),/disposed/);let late=0;region.own(()=>late++);assert.equal(late,1);
});

const head=(basis)=>env=>{if(!basis)return;const meta=document.createElement('meta');meta.setAttribute('name','laplace-frontend-basis');meta.setAttribute('content',basis);document.head.append(meta);};
const detail=q=>({project:'book',view:'detail',task:{id:q.get('id')||'WORK-a',title:'Approach A',goal:'Authored criterion',status:'blocked',work_revision:'r1'},
  blockers:[],children:{items:[]},dependants:{items:[]},read_cut:{revision:'cut-1'},
  allowed_actions:{task:{permitted:true,payload:{id:q.get('id')||'WORK-a',expected_work_revision:'r1'},http:{method:'POST',url:'/work/task'}}}});

const KEY='laplace:frontend-refresh:book';
const summary=()=>({project:'book',view:'summary',tasks:[{id:'WORK-a',title:'Approach A',status:'blocked',lifecycle:{closed:false}}],counts:{}});
const workRoutes=(served,extra={})=>({'/work/state':q=>q.get('view')==='detail'?detail(q):summary(),'/authoring/health':()=>({pid:42,active_work:[],frontend_bundle:{sha256:served}}),...extra});
const titleField=s=>s.root.querySelectorAll('input').find(node=>node.name==='title');
// page A: a real draft typed into the actual card and a real save whose reply is lost at the transport, then the explicit
// refresh toward served B; returns the exact carry bytes the tab stored (the next page receives exactly those)
async function firstPage(){
  let reloads=0;
  const s=await mountShell({query:'view=work&work=WORK-a',before:head(bases.issued),routes:workRoutes(bases.served_newer,{'/work/task':()=>{throw new TypeError('Failed to fetch: the reply was lost');}})});
  try{
    await s.settle();location.reload=()=>{reloads++;};
    const form=s.root.querySelectorAll('form').find(node=>node.querySelectorAll('input').some(input=>input.name==='title'));
    titleField(s).value='Typed before the refresh';form.oninput?.();titleField(s).oninput?.();
    await form.onsubmit({preventDefault(){}});await s.settle();
    assert.match(s.root.querySelector('[data-control="work:attempt"]').textContent,/uncertain/);
    const line=s.root.querySelector('[data-frontend-update]');
    assert.equal(line.dataset.frontendBasis,'different-served');assert.doesNotMatch(line.textContent,/newer/);
    const go=line.querySelector('button');assert.equal(go.textContent,'Refresh to the served app version');
    s.workspace.session.unsavedDrafts=new Map([['new','words the browser could not store']]);
    await go.onclick();
    assert.match(line.textContent,/Not refreshed; this page stays as it is\. The conversation draft could not be stored/);
    assert.equal(reloads,0);assert.equal(sessionStorage.getItem(KEY),null);
    s.workspace.session.unsavedDrafts.clear();
    await go.onclick();assert.equal(reloads,1);
    const text=sessionStorage.getItem(KEY),carry=JSON.parse(text);
    assert.equal(carry.from,bases.issued);assert.equal(carry.to,bases.served_newer);assert.equal(typeof carry.id,'string');
    assert.deepEqual(carry.carried.visit,{view:'work'});assert.equal(carry.carried.work.selected,'WORK-a');
    assert.equal(carry.carried.work.port.drafts[0].fields.title,'Typed before the refresh');
    assert.equal(carry.carried.work.port.attempts[0].status,'uncertain');
    return {text,posts:s.calls.filter(call=>call.startsWith('POST')).length};
  }finally{s.restore();}
}
const nextPage=(text,issued,routes)=>mountShell({query:'view=work&work=WORK-a',before:env=>{head(issued)(env);sessionStorage.setItem(KEY,text);},routes});
const restoredInto=(s,text)=>{
  assert.equal(s.root.querySelector('[data-refresh-carry]').dataset.refreshCarry,'restored');
  assert.equal(titleField(s)?.value,'Typed before the refresh');
  assert.match(s.root.querySelector('[data-control="work:attempt"]').textContent,/Attempt A1 .*uncertain/);
  assert.equal(sessionStorage.getItem(KEY),null,'exactly the restored record was acknowledged');
  assert.ok(!s.calls.some(call=>call.startsWith('POST')),'nothing was resent');
};

test('shell: two real frozen bases offer an explicit refresh; a missing capture refuses and keeps the page; the capture carries the visit and Work memory and reloads once',{skip:!bases&&'FRONTEND_BASIS is not published by the guarded case'},async()=>{
  const {text,posts}=await firstPage();assert.equal(posts,1,'only the original save was ever sent');
  const s=await nextPage(text,bases.served_newer,workRoutes(bases.served_newer));
  try{await s.settle();await s.settle();
    assert.equal(s.root.querySelector('[data-refresh-carry]').dataset.issuedBasis,'matched');restoredInto(s,text);
    assert.match(s.root.querySelector('[data-refresh-carry]').textContent,/restored into this page .*nothing was resent/);
    assert.equal(s.root.querySelector('[data-frontend-update]').dataset.frontendBasis,'current');}
  finally{s.restore();}
});

test('carry: a failed entry keeps the exact carry, the existing Retry reopens the project, and the matched page restores and acknowledges it once',{skip:!bases&&'FRONTEND_BASIS is not published by the guarded case'},async()=>{
  const {text}=await firstPage();let reloads=0;
  const failed=await nextPage(text,bases.served_newer,workRoutes(bases.served_newer,{'/projects/metadata':()=>({error:'The project metadata owner is unavailable.'})}));
  try{await failed.settle();location.reload=()=>{reloads++;};
    assert.equal(failed.root.dataset.entry,'failed');assert.equal(sessionStorage.getItem(KEY),text,'entry failure keeps the exact carry');
    assert.equal(failed.workspace.refreshCarry(),'adopting');
    const retry=failed.root.querySelectorAll('button').find(node=>node.textContent==='Retry opening project');await retry.onclick();
    assert.equal(reloads,1);assert.equal(sessionStorage.getItem(KEY),text,'Retry keeps the exact carry');
    assert.ok(!failed.calls.some(call=>call.startsWith('POST')));}
  finally{failed.restore();}
  const s=await nextPage(text,bases.served_newer,workRoutes(bases.served_newer));   // the reload Retry asked for
  try{await s.settle();await s.settle();restoredInto(s,text);}finally{s.restore();}
});

test('carry: a refused (503) initial read of the carried Work keeps the carry; the existing Retry delivers that Work, restores and acknowledges once',{skip:!bases&&'FRONTEND_BASIS is not published by the guarded case'},async()=>{
  const {text}=await firstPage();let reads=0;
  const s=await nextPage(text,bases.served_newer,workRoutes(bases.served_newer,{'/work/state':q=>q.get('view')!=='detail'?summary():
    ++reads===1?ownerReply(503,{error:'The Work owner is unavailable.'}):detail(q)}));
  try{await s.settle();await s.settle();
    assert.equal(reads,1);assert.equal(s.root.dataset.entry,'ready','the entry itself succeeded: entry ready is not restoration');
    assert.equal(s.workspace.refreshCarry(),'adopting');assert.equal(sessionStorage.getItem(KEY),text,'a refused owner read keeps the exact carry');
    assert.match(s.root.querySelector('[data-refresh-carry]').textContent,/kept in this tab until the Work they belong to is shown from its owner/);
    const retry=s.root.querySelectorAll('button').find(node=>node.textContent==='Retry focused work');assert.ok(retry,'the existing Retry is offered');
    await retry.onclick();await s.settle();
    assert.equal(reads,2);restoredInto(s,text);
    await s.workspace.show('overview',false);await s.workspace.show('work',false);await s.settle();   // a later delivery of the same Work
    assert.equal(s.workspace.refreshCarry(),'restored','acknowledged once; nothing further');assert.ok(!s.calls.some(call=>call.startsWith('POST')));}
  finally{s.restore();}
});

test('carry: a different or unknown issued basis keeps the carry and says so; explicit restore adopts and acknowledges only that record',{skip:!bases&&'FRONTEND_BASIS is not published by the guarded case'},async()=>{
  const {text}=await firstPage();
  const rolled=await nextPage(text,bases.issued,workRoutes(bases.served_same));   // the refresh targeted B; the page came back from A
  try{await rolled.settle();await rolled.settle();
    const line=rolled.root.querySelector('[data-refresh-carry]');
    assert.equal(line.dataset.refreshCarry,'kept');assert.equal(line.dataset.issuedBasis,'different');
    assert.match(line.textContent,/intended frontend .* but this page was issued from .* \(the version before the refresh\)\. .*kept in this tab, not restored; nothing was resent/);
    assert.doesNotMatch(rolled.root.textContent,/newer/);assert.equal(rolled.root.querySelector('[data-frontend-update]').dataset.frontendBasis,'current');
    assert.notEqual(titleField(rolled)?.value,'Typed before the refresh');assert.equal(sessionStorage.getItem(KEY),text);
    await line.querySelector('button').onclick();await rolled.settle();await rolled.settle();
    restoredInto(rolled,text);}
  finally{rolled.restore();}
  const blind=await nextPage(text,null,workRoutes(bases.served_same));
  try{await blind.settle();const line=blind.root.querySelector('[data-refresh-carry]');
    assert.equal(line.dataset.issuedBasis,'unknown');assert.equal(line.dataset.refreshCarry,'kept');assert.match(line.textContent,/issued from an unreported version/);
    assert.equal(sessionStorage.getItem(KEY),text);assert.ok(!blind.calls.some(call=>call.startsWith('POST')));}
  finally{blind.restore();}
});

test('carry: a stale acknowledgement cannot delete a newer capture; the exact record is acknowledged once',()=>{
  const store=new Map(),storage={getItem:k=>store.has(k)?store.get(k):null,setItem:(k,v)=>store.set(k,String(v)),removeItem:k=>store.delete(k)};
  const record=id=>JSON.stringify({schema:'laplace.frontend-refresh-carry/1',id,project:'book',from:'a'.repeat(64),to:'b'.repeat(64),at:'t',carried:{visit:{view:'work'}}});
  storage.setItem(KEY,record('first'));const first=inspectRefreshCarry('book',{issued:'b'.repeat(64),storage});
  assert.equal(first.status,'matched');assert.equal(storage.getItem(KEY),record('first'),'inspection never removes');
  storage.setItem(KEY,record('second'));
  assert.equal(acknowledgeRefreshCarry('book',first,storage),false);assert.equal(storage.getItem(KEY),record('second'),'the newer capture stays');
  const second=inspectRefreshCarry('book',{issued:'a'.repeat(64),storage});assert.equal(second.status,'different');
  assert.equal(acknowledgeRefreshCarry('book',second,storage),true);assert.equal(storage.getItem(KEY),null);
  assert.equal(acknowledgeRefreshCarry('book',second,storage),false,'once');
  assert.equal(inspectRefreshCarry('book',{issued:null,storage}),null);storage.setItem(KEY,record('third'));
  assert.equal(inspectRefreshCarry('book',{issued:null,storage}).status,'unknown');
});

test('shell: a page served without an issued basis is unknown and offers no refresh',async()=>{
  const s=await mountShell({routes:{'/authoring/health':()=>({pid:42,active_work:[],frontend_bundle:{sha256:'a'.repeat(64)}})}});
  try{await s.settle();const line=s.root.querySelector('[data-frontend-update]');
    assert.equal(line.dataset.frontendBasis,'unknown-issued');assert.equal(line.hidden,true);assert.equal(line.querySelector('button'),null);}
  finally{s.restore();}
});
