// The P1 Work port (work-port.mjs) and its two renderers: the current Work card through its adapter
// (workspace-work.mjs mountOperatorWork) and the independent plain-DOM outline (work-port-outline.mjs).
// The "real owner" cases run against the loopback socket that the guarded case
// tests/test_work_port_owner.py::test_work_port_renderers_drive_the_real_work_owner_over_http serves over the actual
// /work/* HTTP door (WORK_PORT_SERVER names its published URL file); that case then checks the ledger. This process
// imports no Laplace code. The other cases are pure service and lifetime cases over small owner-shaped doubles.
import {test,after} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,existsSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {installDOM,findButton} from './helpers/evidence_reader_harness.mjs';
import {createWorkPort} from '../src/laplace/web/static_shared/work-port.mjs';
import {mountWorkOutline} from '../src/laplace/web/static_shared/work-port-outline.mjs';
import {mountOperatorWork} from '../src/laplace/web/static_shared/workspace-work.mjs';
import {observeWork} from '../src/laplace/web/static_shared/workspace-work-observer.mjs';
import {projectRequest} from '../src/laplace/web/static_shared/workspace-session.mjs';

const serverFile=process.env.WORK_PORT_SERVER;
const server=serverFile&&existsSync(serverFile)?JSON.parse(readFileSync(serverFile,'utf8')):null;
const report={passed:0,failed:0,posts_issued:0,connection_events:0};
const field=(host,name)=>host.all().find(n=>n.name===name);
// P2: the real-owner cases use the app's own transport, workspace-session.projectRequest over owner-request.mjs, on a page
// whose origin is the owner's loopback door (location; fetch resolves a relative path against it as a browser does).
// A lost response is lost AT THE TRANSPORT: the owner receives and records the POST, then the reply never arrives.
const losing=new Set();   // Work ids whose NEXT POST reply is lost
if(server){
  const realFetch=globalThis.fetch;
  globalThis.location={href:server.url+'/',origin:new URL(server.url).origin};
  globalThis.window=new EventTarget();window.addEventListener('laplace-workspace-connection',()=>{report.connection_events++;});
  globalThis.fetch=async(path,init={})=>{const response=await realFetch(new URL(path,globalThis.location.href),init);
    const id=init.method==='POST'?JSON.parse(init.body).id:null;
    if(losing.delete(id))throw new TypeError('Failed to fetch: the response was lost');return response;};   // one lost reply per arming
}
async function http(path,payload){
  if(payload!==undefined)report.posts_issued++;
  return projectRequest(path,payload);
}
const real=(name,fn)=>test(name,{skip:!server&&'WORK_PORT_SERVER is not published by the guarded owner case'},async()=>{
  const dom=installDOM();try{await fn();report.passed++;}catch(error){report.failed++;throw error;}finally{dom.restore();}});
after(()=>{if(server)writeFileSync(join(dirname(serverFile),'work-port-node-report.json'),JSON.stringify(report));});

real('both renderers reach the real owner: read, typed title, guarded submit, receipt and observed postimage',async()=>{
  const project=server.project;
  // the current Work card, through its adapter: the same port owns the draft, guard and attempt
  const card=document.createElement('main');
  const summary=await http('/work/state?'+new URLSearchParams({project,view:'summary'}));
  const controller=await mountOperatorWork(card,{project,summary,request:http,initialWork:'W-card'});
  const form=card.all().find(n=>n.tag==='form');field(form,'title').value='Card title, renamed through the card';form.oninput();
  assert.equal(controller.port.draftFor('W-card').fields.title,'Card title, renamed through the card');
  const guard=controller.port.draftFor('W-card').basis.payload.expected_work_revision;
  await form.onsubmit({preventDefault(){}});
  const attempt=controller.port.attemptFor('W-card');
  assert.equal(attempt.status,'recorded');assert.ok(attempt.result.owned_changes,'the owner receipt is kept unchanged');
  assert.equal(attempt.basis.payload.expected_work_revision,guard);
  assert.equal(attempt.postimage.fields.title,'Card title, renamed through the card');
  assert.equal(controller.port.draftFor('W-card'),null);assert.match(card.textContent,/Card title, renamed through the card/);
  report.card_title='Card title, renamed through the card';controller.destroy();
  // the independent plain-DOM outline over its own port
  const port=createWorkPort({request:http,project}),host=document.createElement('main'),outline=mountWorkOutline(host,port);
  await port.dispatch({type:'select',project,id:'W-outline'});
  assert.equal(field(host,'title').value,'Outline title');
  field(host,'title').value='Outline title, renamed through the outline';await field(host,'title').oninput();
  await host.all().find(n=>n.tag==='form').onsubmit({preventDefault(){}});
  const done=port.snapshot();
  assert.equal(done.attempt.status,'recorded');assert.equal(done.attempt.postimage.fields.title,'Outline title, renamed through the outline');
  assert.equal(done.read.owner.title,'Outline title, renamed through the outline');assert.equal(done.read.io,'ready');assert.equal(done.draft,null);
  assert.match(host.textContent,/Attempt A1: recorded/);report.outline_title='Outline title, renamed through the outline';
  outline.destroy();port.dispatch({type:'dispose'});
});

real('an external edit refuses the original guard; words and guard stay; compare then adopt makes a new attempt that succeeds',async()=>{
  const project=server.project,port=createWorkPort({request:http,project}),host=document.createElement('main');mountWorkOutline(host,port);
  await port.dispatch({type:'select',project,id:'W-stale'});
  field(host,'title').value='Draft words written first';await field(host,'title').oninput();
  const original=port.snapshot().draft.basis.payload.expected_work_revision;report.stale_original_guard=original;
  // another writer changes the specification through the same owner door
  const current=await http('/work/state?'+new URLSearchParams({project,view:'detail',id:'W-stale'}));
  await http('/work/task',{project,...current.allowed_actions.task.payload,title:'Changed by another writer'});
  await host.all().find(n=>n.tag==='form').onsubmit({preventDefault(){}});
  let snap=port.snapshot();
  assert.equal(snap.attempt.status,'refused');assert.equal(snap.attempt.refusal.code,'CHANGED_INPUT');
  assert.ok(snap.attempt.next_reads.length,'the owner\'s next reads are kept');
  assert.equal(snap.draft.fields.title,'Draft words written first');assert.equal(snap.draft.basis.payload.expected_work_revision,original);
  await findButton(host,'Compare with the current Work').onclick();snap=port.snapshot();
  assert.equal(snap.comparison.current.fields.title,'Changed by another writer');assert.equal(snap.comparison.same_basis,false);
  assert.match(host.textContent,/The Work changed since your draft was written/);
  await findButton(host,'Use the displayed current Work as my basis').onclick();
  assert.notEqual(port.snapshot().draft.basis.payload.expected_work_revision,original);
  await host.all().find(n=>n.tag==='form').onsubmit({preventDefault(){}});snap=port.snapshot();
  assert.equal(snap.attempt.status,'recorded');assert.equal(snap.attempt.id,'A2','a new attempt, not a replay');
  assert.equal(snap.attempt.postimage.fields.title,'Draft words written first');report.stale_final_title='Draft words written first';
  port.dispatch({type:'dispose'});
});

real('a lost response stays uncertain, is never resent on remount, and reinspection reports the observed fields',async()=>{
  const project=server.project;let lost=0;
  losing.add('W-lost');const lossy=async(path,payload)=>{try{return await http(path,payload);}catch(error){if(payload?.id==='W-lost'&&error.transport==='connection'){lost++;assert.equal(error.effect,'unknown');}throw error;}};
  const port=createWorkPort({request:lossy,project}),first=document.createElement('main');let outline=mountWorkOutline(first,port);
  await port.dispatch({type:'select',project,id:'W-lost'});
  field(first,'title').value='Words whose response was lost';await field(first,'title').oninput();
  await first.all().find(n=>n.tag==='form').onsubmit({preventDefault(){}});
  let snap=port.snapshot();
  assert.equal(snap.attempt.status,'uncertain');assert.match(snap.attempt.effect,/unknown/);assert.equal(snap.draft.fields.title,'Words whose response was lost');
  const posts=report.posts_issued;
  outline.destroy();const second=document.createElement('main');outline=mountWorkOutline(second,port);   // a new renderer: nothing is resent
  assert.equal(report.posts_issued,posts);assert.equal(field(second,'title').value,'Words whose response was lost');
  await findButton(second,'Reinspect').onclick();snap=port.snapshot();
  assert.equal(report.posts_issued,posts,'reinspection reads only');assert.equal(snap.attempt.status,'uncertain');
  assert.equal(snap.attempt.observed.matches_attempt,true);assert.match(second.textContent,/The owner now shows the fields you attempted/);
  assert.equal(lost,1);report.lost_title='Words whose response was lost';outline.destroy();port.dispatch({type:'dispose'});
});

// ---------------------------------------------------------------------------------------- pure service and lifetime
const detail=(id,extra={})=>({project:'p',view:'detail',read_cut:{revision:'cut-'+id},observe_basis:{records:'r1',selected:'s1',activity:'a1'},
  task:{id,title:'Title '+id,goal:'Goal '+id,status:'open',work_revision:'rev-'+id,read_handle:{http:{method:'GET',url:'/work/state?project=p&view=detail&id='+id}},...(extra.task||{})},
  allowed_actions:extra.allowed_actions??{task:{permitted:true,payload:{id,expected_work_revision:'rev-'+id},http:{method:'POST',url:'/work/task'}}}});
const pure=(name,fn)=>test(name,async()=>{const dom=installDOM();try{await fn();}finally{dom.restore();}});

pure('replacing the renderer keeps selection, draft and attempt; destroy drops only its own listener and nothing posts',async()=>{
  const calls=[];const port=createWorkPort({request:async(url,payload)=>{calls.push({url,payload});return detail('X');},project:'p'});
  const a=document.createElement('main');let mount=mountWorkOutline(a,port);assert.equal(port.listenerCount(),1);
  await port.dispatch({type:'select',project:'p',id:'X'});field(a,'goal').value='Typed purpose';await field(a,'goal').oninput();
  mount.destroy();assert.equal(port.listenerCount(),0);
  const b=document.createElement('main');mount=mountWorkOutline(b,port);const again=mountWorkOutline(document.createElement('main'),port);
  assert.equal(port.listenerCount(),2,'one listener per live mount, none left behind');again.destroy();
  assert.equal(field(b,'goal').value,'Typed purpose');assert.deepEqual(port.snapshot().selection,{project:'p',id:'X'});
  assert.ok(calls.every(call=>call.payload===undefined),'mounting and remounting never post');
  assert.deepEqual(port.capture().drafts.map(d=>[d.project,d.id,d.fields]),[['p','X',{goal:'Typed purpose'}]]);
  assert.throws(()=>Object.assign(port.snapshot().draft.fields,{goal:'x'}),'snapshots are immutable');
});

pure('a late read for an earlier selection never paints the newer one; return goes back to the earlier visit',async()=>{
  const pending=new Map();const port=createWorkPort({project:'p',request:url=>new Promise(resolve=>pending.set(new URL(url,'http://l').searchParams.get('id'),resolve))});
  const host=document.createElement('main');mountWorkOutline(host,port);
  const first=port.dispatch({type:'select',project:'p',id:'X'}),second=port.dispatch({type:'select',project:'p',id:'Y'});
  pending.get('Y')(detail('Y'));await second;pending.get('X')(detail('X'));await first;
  const snap=port.snapshot();assert.equal(snap.selection.id,'Y');assert.equal(snap.read.owner.title,'Title Y');assert.match(host.textContent,/Title Y/);
  assert.doesNotMatch(host.textContent,/Title X/);assert.equal(snap.visit.depth,1);
  await findButton(host,'Return').onclick();assert.equal(port.snapshot().selection.id,'X');
});

pure('observer: a failed delivery keeps the applied token, draft and selection; hidden reads nothing; dispose stops it',async()=>{
  let fail=true,observer=null,detailReads=0;const timers=[];
  const clock={setTimeout:(fn)=>{timers.push(fn);return timers.length;},clearTimeout:()=>{},now:()=>0};
  const doc={visibilityState:'visible',addEventListener(){},removeEventListener(){}};
  const request=async url=>{const q=new URL(url,'http://l').searchParams;
    if(q.get('view')==='observe')return {project:'p',view:'observe',token:'wo1.r2.s2.a1',changed:true,changes:['records'],poll:{after_ms:1000,max_ms:4000,backoff:2}};
    detailReads++;if(detailReads>1&&fail)throw Error('owner read failed');return detail('X');};
  const port=createWorkPort({request,project:'p',observe:hooks=>(observer=observeWork({project:'p',request,clock,doc,start:999999,
    selected:()=>hooks.selected()?.id||null,isCurrent:hooks.isCurrent,onChange:hooks.onChange,basis:hooks.basis}))});
  await port.dispatch({type:'select',project:'p',id:'X'});await port.dispatch({type:'edit',fields:{title:'Kept through observation'}});
  await observer.tick();
  assert.equal(observer.state().token,null,'a failed delivery does not advance the applied token');assert.equal(observer.state().failures,1);
  assert.equal(port.snapshot().draft.fields.title,'Kept through observation');assert.equal(port.snapshot().selection.id,'X');
  doc.visibilityState='hidden';const reads=detailReads;await observer.tick();assert.equal(detailReads,reads,'hidden: no read');
  doc.visibilityState='visible';fail=false;await observer.tick();
  assert.equal(observer.state().token,'wo1.r2.s2.a1','the same hint is applied once the owner read succeeds');
  assert.equal(port.snapshot().draft.fields.title,'Kept through observation');
  await port.dispatch({type:'dispose'});assert.equal(observer.state().stopped,true);
  const after=detailReads;await observer.tick();assert.equal(detailReads,after,'a disposed port reads nothing');
});

pure('unread and unavailable owner fields stay explicit; only title and purpose are editable',async()=>{
  const port=createWorkPort({project:'p',request:async()=>detail('Z',{task:{goal:undefined},allowed_actions:{task:{permitted:false,reason:'The Work is held by its owner.'}}})});
  const host=document.createElement('main');mountWorkOutline(host,port);await port.dispatch({type:'select',project:'p',id:'Z'});
  const snap=port.snapshot();
  assert.deepEqual(snap.read.owner.unavailable,['goal: not returned by the owner','edit: The Work is held by its owner.']);
  assert.match(host.textContent,/goal: not returned by the owner/);assert.equal(field(host,'title').disabled,true);
  await assert.rejects(port.dispatch({type:'edit',fields:{title:'x'}}),/held by its owner/);
  const open=createWorkPort({project:'p',request:async()=>detail('Q')});await open.dispatch({type:'select',project:'p',id:'Q'});
  await assert.rejects(open.dispatch({type:'edit',fields:{parent_work_id:'R'}}),/Only the title and purpose/);
  await assert.rejects(open.dispatch({type:'submit'}),/no authored title or purpose/);
});

pure('keyboard: Enter in the title submits once; actions are plain buttons; a pending attempt cannot be submitted again',async()=>{
  let release;const posts=[];
  const port=createWorkPort({project:'p',request:(url,payload)=>payload?(posts.push(payload),new Promise(resolve=>{release=()=>resolve({ok:true,read_handle:{http:{method:'GET',url}}});})):Promise.resolve(detail('K'))});
  const host=document.createElement('main');mountWorkOutline(host,port);await port.dispatch({type:'select',project:'p',id:'K'});
  const form=host.all().find(n=>n.tag==='form'),buttons=form.all().filter(n=>n.tag==='button');
  assert.deepEqual(buttons.map(b=>b.type),['submit','button','button','button','button','button']);
  assert.equal(buttons[0].disabled,true,'nothing to save before typing');
  field(host,'title').value='Typed then Enter';await field(host,'title').oninput();assert.equal(buttons[0].disabled,false);
  const pressed=form.onsubmit({preventDefault(){}});            // Enter in a text field submits its form
  await new Promise(resolve=>setTimeout(resolve,0));
  await form.onsubmit({preventDefault(){}});assert.match(host.textContent,/still waiting for its owner/);
  assert.equal(posts.length,1);assert.deepEqual(posts[0],{project:'p',id:'K',expected_work_revision:'rev-K',title:'Typed then Enter'},'only authored fields and the issued guard');
  release();await pressed;assert.equal(port.snapshot().attempt.status,'recorded');
});

// ---------------------------------------------------------------------------------------- correction 1 (P1-R1/R2/R3)
import {mountOwnerDiscovery} from '../src/laplace/web/static_shared/workspace-owners.mjs';
import {WORK_PORT_CAPTURE} from '../src/laplace/web/static_shared/work-port.mjs';

pure('read IO state is separate from Work standing: a failed reread says error and keeps the last owner values',async()=>{
  let fail=false;const port=createWorkPort({project:'p',request:async()=>{if(fail)throw Error('owner unreachable');return detail('S',{task:{status:'done'}});}});
  const host=document.createElement('main');mountWorkOutline(host,port);await port.dispatch({type:'select',project:'p',id:'S'});
  assert.equal(port.snapshot().read.io,'ready');assert.equal(port.snapshot().read.owner.status,'done');
  fail=true;await assert.rejects(port.dispatch({type:'reinspect'}),/owner unreachable/);
  const snap=port.snapshot();assert.equal(snap.read.io,'error');assert.equal(snap.read.error,'owner unreachable');
  assert.equal(snap.read.owner.status,'done','standing stays the owner\'s, not the transport\'s');assert.equal(snap.read.owner.title,'Title S');
  assert.match(host.textContent,/Last read failed: owner unreachable\. The values shown are from the last successful read/);assert.match(host.textContent,/Standing: done/);
});

pure('an older read released after a newer same-object delivery never replaces it, a reread or a postimage alike',async()=>{
  let release;const port=createWorkPort({project:'p',request:url=>new Promise(resolve=>{release=resolve;})});
  const selecting=port.dispatch({type:'select',project:'p',id:'O'});release(detail('O'));await selecting;
  const older=port.dispatch({type:'reinspect'}),hold=release;                               // an owner read still in flight
  await port.dispatch({type:'observe',value:detail('O',{task:{title:'Newer observed title',work_revision:'rev-2'}})});
  hold(detail('O',{task:{title:'Older title from the held read'}}));await older;
  assert.equal(port.snapshot().read.owner.title,'Newer observed title');assert.equal(port.snapshot().read.owner.work_revision,'rev-2');
});

pure('a focused field typed for X is replaced when the selection becomes Y and on Return; X\'s words never edit Y',async()=>{
  const posts=[];const port=createWorkPort({project:'p',request:async(url,payload)=>{if(payload)posts.push(payload);return detail(new URL(url,'http://l').searchParams.get('id'));}});
  const host=document.createElement('main');mountWorkOutline(host,port);await port.dispatch({type:'select',project:'p',id:'X'});
  const titleX=field(host,'title');titleX.focus();titleX.value='Words for X';await titleX.oninput();
  await port.dispatch({type:'select',project:'p',id:'Y'});
  const titleY=field(host,'title');assert.notEqual(titleY,titleX,'Y gets its own field');assert.equal(titleY.value,'Title Y');assert.equal(titleY.dataset.work,'p::Y');
  titleX.value='Words for X, typed again in the old field';await titleX.oninput();         // a late event from X's field
  assert.equal(port.draftFor('Y'),null);assert.match(host.textContent,/written for another Work/);
  assert.equal(port.draftFor('X').fields.title,'Words for X');
  await findButton(host,'Return').onclick();assert.equal(field(host,'title').value,'Words for X');assert.equal(field(host,'title').dataset.work,'p::X');
  assert.equal(posts.length,0,'nothing was posted');
});

pure('capture is lossless and qualified: one local id in two namespaces, original bases, continued attempt ids, a pending attempt restores unresolved',async()=>{
  let release;const port=createWorkPort({request:async(url,payload)=>{if(payload)return new Promise(resolve=>{release=resolve;});const q=new URL(url,'http://l').searchParams;return {...detail('SAME'),project:q.get('project')};}});
  for(const project of ['alpha','beta']){await port.dispatch({type:'select',project,id:'SAME'});await port.dispatch({type:'edit',fields:{title:'Draft in '+project}});}
  port.dispatch({type:'submit'});await new Promise(resolve=>setTimeout(resolve,0));          // beta's attempt A1 is pending
  const saved=port.capture();
  assert.equal(saved.schema,WORK_PORT_CAPTURE);assert.deepEqual(saved.drafts.map(d=>[d.project,d.id,d.fields.title]).sort(),[['alpha','SAME','Draft in alpha'],['beta','SAME','Draft in beta']]);
  assert.deepEqual(saved.attempts.map(a=>[a.project,a.work_id,a.id,a.status]),[['beta','SAME','A1','pending']]);
  const restored=createWorkPort({request:async()=>{throw Error('a restore never reads or posts by itself');},initial:JSON.parse(JSON.stringify(saved))});
  assert.equal(restored.draftFor('SAME','alpha').fields.title,'Draft in alpha');assert.equal(restored.draftFor('SAME','beta').basis.payload.expected_work_revision,'rev-SAME');
  const unresolved=restored.attemptFor('SAME','beta');assert.equal(unresolved.status,'uncertain');assert.equal(unresolved.restored,true);assert.match(unresolved.effect,/unresolved/);
  assert.equal(restored.hasUnresolved(),true);assert.equal(restored.capture().next_attempt,1,'the next local attempt is A2, never a reused A1');
  release({ok:true});
});

pure('the card keeps containment and title drafts on their own original bases through capture; the legacy envelope still restores',async()=>{
  let revision='r0';const reads=[];
  const request=async(url,payload)=>{if(payload)throw Error('no post in this case');reads.push(url);const d=detail('C');d.project='p';d.task.work_revision=revision;d.allowed_actions.task.payload.expected_work_revision=revision;return d;};
  const host=document.createElement('main');const card=await mountOperatorWork(host,{project:'p',summary:{tasks:[{id:'C',title:'Title C',status:'open'}]},request,initialWork:'C'});
  const containment=host.all().find(n=>n.name==='parent_work_id');containment.value='PARENT';containment.parentElement.parentElement.oninput();   // authored at r0
  revision='r1';await card.select('C');                                                       // the owner moved; title authored at r1
  const title=host.all().find(n=>n.tag==='form'&&n.all().some(m=>m.name==='title'));const t=title.all().find(m=>m.name==='title');t.value='Title authored at r1';title.oninput();
  const saved=card.capture();card.destroy();
  assert.equal(saved.drafts.C.containment.basis.payload.expected_work_revision,'r0');
  assert.equal(saved.port.drafts[0].basis.payload.expected_work_revision,'r1');
  const again=await mountOperatorWork(document.createElement('main'),{project:'p',summary:{tasks:[{id:'C',title:'Title C',status:'open'}]},request,initialWork:'C',memory:saved});
  const back=again.capture();assert.equal(back.drafts.C.containment.basis.payload.expected_work_revision,'r0','containment keeps its own original basis');
  assert.equal(again.port.draftFor('C').basis.payload.expected_work_revision,'r1');assert.equal(again.port.draftFor('C').fields.title,'Title authored at r1');
  again.destroy();
  const legacy=await mountOperatorWork(document.createElement('main'),{project:'p',summary:{tasks:[{id:'C',title:'Title C',status:'open'}]},request,initialWork:'C',
    memory:{drafts:{C:{fields:{title:'Legacy title',parent_work_id:'OLD'},editBasis:{payload:{id:'C',expected_work_revision:'legacy'},http:{method:'POST',url:'/work/task'}},dirty:true}}}});
  assert.equal(legacy.port.draftFor('C').fields.title,'Legacy title');assert.equal(legacy.capture().drafts.C.containment.value,'OLD');legacy.destroy();
});

pure('the owners view asks before leaving with a draft: Stay keeps it, Open anyway says it is not carried, and the page guard blocks unload',async()=>{
  const inspect={schema_version:'laplace.owner-discovery/1',facet:'inspect',grade:'work',scope:{says:''},coverage:{},title:'Title X',purpose:'Goal X',
    reference:{identity:{namespace:'p',id:'X'}},legacy:{read:{http:{method:'GET',url:'/work/state?project=p&view=detail&id=X'}}},standing:{},next:{actions:[]},up:[],lateral:[]};
  let opened=null;const host=document.createElement('main');
  const view=await mountOwnerDiscovery(host,{request:async url=>url.startsWith('/work/discovery')?structuredClone(inspect):detail('X'),onWork:target=>{opened=target;}});
  const unload=()=>{const event={prevented:false,preventDefault(){this.prevented=true;}};view.leaveGuard(event);return event;};
  assert.equal(unload().prevented,false,'nothing to lose: leaving is not blocked');
  await findButton(host,'Edit title and purpose').onclick();
  field(host,'title').value='Words not yet saved';await field(host,'title').oninput();
  assert.equal(view.hasDraft,true);const blocked=unload();assert.equal(blocked.prevented,true);assert.equal(blocked.returnValue,'');
  await findButton(host,'Open in project').onclick();
  assert.equal(opened,null,'the first click only asks');assert.match(host.textContent,/they are not carried there/);
  await findButton(host,'Stay here').onclick();
  assert.equal(opened,null);assert.equal(field(host,'title').value,'Words not yet saved');assert.equal(view.port.draftFor('X','p').fields.title,'Words not yet saved');
  await findButton(host,'Open in project').onclick();await findButton(host,'Open in project anyway (the draft is not carried)').onclick();
  assert.deepEqual({project:opened.project,id:opened.id},{project:'p',id:'X'});
  await view.port.dispatch({type:'cancel-local'});assert.equal(unload().prevented,false,'after discarding, leaving is free');
  view.destroy();
});

real('card: capture, destroy and a new card after a lost response keep the words, guard and uncertainty; nothing is resent',async()=>{
  const project=server.project;
  // faithful connection lifetime, as in a browser: a node is connected only while document.body is among its
  // ancestors, so a line prepared in a detached fragment reports isConnected false until it is attached
  const make=document.createElement;
  document.createElement=tag=>{const node=make(tag);Object.defineProperty(node,'isConnected',{configurable:true,set(){},
    get(){for(let at=this;at;at=at.parent){if(at===document.body)return true;if(at.parent&&!at.parent.children.includes(at))return false;}return false;}});return node;};
  losing.add('W-capture');const lossy=http;   // the save's reply is lost at the transport (projectRequest: connection, effect unknown)
  const summary=await http('/work/state?'+new URLSearchParams({project,view:'summary'}));
  const card=document.createElement('main');document.body.append(card);assert.equal(document.createElement('p').isConnected,false,'a fresh node is detached');
  const live=await mountOperatorWork(card,{project,summary,request:lossy,initialWork:'W-capture'});
  const edit=card.all().find(n=>n.tag==='form'&&n.all().some(m=>m.name==='title'));
  edit.all().find(m=>m.name==='title').value='Captured words, response lost';edit.oninput();
  const guard=live.port.draftFor('W-capture').basis.payload.expected_work_revision;
  await edit.onsubmit({preventDefault(){}});
  assert.equal(live.port.attemptFor('W-capture').status,'uncertain');
  assert.match(card.all().find(n=>n.dataset?.control==='work:attempt').textContent,/: uncertain\. unknown: no owner response; the draft is kept and nothing is resent/,'the same presenter paints the first card');
  const saved=JSON.parse(JSON.stringify(live.capture()));live.destroy();
  const posts=report.posts_issued;
  card.remove();assert.equal(card.isConnected,false,'the destroyed card is detached');const shown=document.createElement('main');document.body.append(shown);
  const next=await mountOperatorWork(shown,{project,summary,request:http,initialWork:'W-capture',memory:saved});
  assert.equal(report.posts_issued,posts,'a new card posts nothing');
  const attempt=next.port.attemptFor('W-capture');assert.equal(attempt.status,'uncertain');assert.equal(attempt.basis.payload.expected_work_revision,guard);
  assert.equal(next.port.draftFor('W-capture').fields.title,'Captured words, response lost');assert.equal(next.hasDraft,true);
  // what the person sees on the new card, before any further submit: the unresolved save, its attribution and basis
  const line=()=>shown.all().find(n=>n.dataset?.control==='work:attempt');
  assert.equal(line().dataset.attempt,'uncertain');
  assert.match(line().textContent,/Attempt A1 \(.+\): uncertain\. unknown: no owner response; the draft is kept and nothing is resent/);
  assert.match(line().textContent,new RegExp('Written against work revision '+guard));
  assert.equal(shown.all().find(n=>n.name==='title').value,'Captured words, response lost');
  // a read-only reinspection through the card: the owner now shows the attempted fields (an observation, not a receipt)
  await findButton(shown,'Reinspect this work').onclick();assert.equal(report.posts_issued,posts,'reinspection reads only');
  assert.equal(next.port.attemptFor('W-capture').observed.matches_attempt,true);
  assert.match(line().textContent,/A later owner read \(.+\) shows the fields you attempted; that is an observation, not a receipt\./);assert.equal(line().dataset.attempt,'uncertain');
  // another writer changes the title; the next read-only reinspection shows the attempted fields are no longer there
  const now=await http('/work/state?'+new URLSearchParams({project,view:'detail',id:'W-capture'}));
  await http('/work/task',{project,...now.allowed_actions.task.payload,title:'Changed elsewhere after the lost save'});const after=report.posts_issued;
  await findButton(shown,'Reinspect this work').onclick();assert.equal(report.posts_issued,after,'the card posted nothing');
  assert.match(line().textContent,/A later owner read \(.+\) does not show the fields you attempted\./);
  assert.equal(shown.all().find(n=>n.name==='title').value,'Captured words, response lost','the words are kept');
  assert.equal(next.port.listenerCount(),1,'one presenter subscription for the controller, however often the editor repaints');
  next.destroy();assert.equal(next.port.listenerCount(),0,'destroy removes it');
  report.capture_title='Captured words, response lost';report.capture_external_title='Changed elsewhere after the lost save';
});

real('card: the comparison is displayed, adoption is a separate click of the displayed basis, and a newer delivery invalidates it',async()=>{
  const project=server.project,id='W-compare';
  const external=async title=>{const now=await http('/work/state?'+new URLSearchParams({project,view:'detail',id}));await http('/work/task',{project,...now.allowed_actions.task.payload,title});return now;};
  const summary=await http('/work/state?'+new URLSearchParams({project,view:'summary'}));
  const card=document.createElement('main');const controller=await mountOperatorWork(card,{project,summary,request:http,initialWork:id});
  const edit=()=>card.all().find(n=>n.tag==='form'&&n.all().some(m=>m.name==='title'));
  edit().all().find(m=>m.name==='title').value='Card draft words';edit().oninput();
  const r0=controller.port.draftFor(id).basis.payload.expected_work_revision;
  await external('Changed to r1');await controller.observed({});                           // the card shows r1: the draft is stale
  assert.equal(edit().dataset.stale,'true');assert.ok(findButton(card,'Compare with the current work'));
  await external('Changed to r2');                                                          // r2 lands before the person compares
  await findButton(card,'Compare with the current work').onclick();
  assert.match(card.textContent,/Current title: Changed to r2/);assert.equal(controller.port.draftFor(id).basis.payload.expected_work_revision,r0,'comparing adopts nothing');
  await external('Changed to r3');await controller.observed({});                           // a newer delivery: the displayed r2 basis moved
  assert.equal(findButton(card,'Use the displayed current work as my basis'),undefined,'the invalidated comparison offers no adoption');
  await assert.rejects(controller.port.dispatch({type:'adopt-current',basis:{id,expected_work_revision:'not displayed'}}),/Compare the draft/);
  assert.equal(controller.port.draftFor(id).basis.payload.expected_work_revision,r0);
  await findButton(card,'Compare with the current work').onclick();assert.match(card.textContent,/Current title: Changed to r3/);
  // wave 11: the comparison region carries its declared id and the task's owner coordinate (state draft-compared)
  {const region=card.all().find(n=>n.dataset?.control==='work:compare');assert.ok(region,'work:compare is rendered');assert.match(region.dataset.controlOwner,/::/);assert.match(region.textContent,/Current title: Changed to r3/);}
  await findButton(card,'Use the displayed current work as my basis').onclick();
  assert.notEqual(controller.port.draftFor(id).basis.payload.expected_work_revision,r0);
  await edit().onsubmit({preventDefault(){}});
  const attempt=controller.port.attemptFor(id);assert.equal(attempt.status,'recorded');assert.equal(attempt.postimage.fields.title,'Card draft words');
  report.compare_final_title='Card draft words';controller.destroy();
});

// Wave 11b census repair D2 (R8): after a real containing-work save the card says the time the owner's reply recorded (its
// ts), not the browser clock; a reply that states no time shows no time.
pure('wave 11b D2: Saved at shows the owner reply ts, and no time when the owner states none',async()=>{
  for(const ts of ['2001-02-03T04:05:06+00:00',null]){
    let parent=null;const posts=[];
    const request=async(url,payload)=>{if(payload){posts.push({url,payload});parent=payload.parent_work_id;return {record:'project-work',id:'C',task_id:'C',project:'p',...(ts?{ts}:{})};}
      const d=detail('C',{task:parent?{parent_work_id:parent}:{}});d.parent=parent?{id:parent,title:'Parent task'}:null;return d;};
    const host=document.createElement('main');const card=await mountOperatorWork(host,{project:'p',summary:{tasks:[{id:'C',title:'Title C',status:'open'},{id:'PARENT',title:'Parent task',status:'open'}]},request,initialWork:'C'});
    const input=host.all().find(n=>n.name==='parent_work_id');input.value='PARENT';const form=input.parentElement.parentElement;form.oninput();
    await form.onsubmit({preventDefault(){}});await new Promise(resolve=>setTimeout(resolve,0));
    assert.equal(posts.length,1);const note=host.all().find(n=>n.tag==='form'&&n.all().some(m=>m.name==='parent_work_id')).all().find(n=>String(n.className).includes('work-status'));
    if(ts)assert.equal(note.textContent,'Saved at '+new Date(ts).toLocaleTimeString()+'. This task is now part of “Parent task”.');
    else assert.equal(note.textContent,'Saved. This task is now part of “Parent task”.');
    card.destroy();
  }
});
