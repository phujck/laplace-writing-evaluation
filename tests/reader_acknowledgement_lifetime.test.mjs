// G1 acknowledgement lifetime (M5 S2-R1). The production mountReaderPlan and acknowledgeReaderInputs run on the
// real-owner fixtures (tests/fixtures/editor_spine: owner-wire summary, reader-state detail with the guard's
// unobserved currentness, the reader_plan owner's guard and RECORDED reply) in the disposable DOM double. The
// dialog belongs to the plan that opened it: destroy or another selected item disposes it; nothing is posted or
// refreshed afterwards; a write already sent states its truthful outcome with the exact read and Close only.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {readerSubjectAction,acknowledgeReaderInputs} from '../src/laplace/web/static_shared/reader-state.mjs';
import {installDOM,Node,findButton} from './helpers/evidence_reader_harness.mjs';
const fixture=async name=>JSON.parse(await readFile(new URL('./fixtures/editor_spine/'+name,import.meta.url),'utf8'));
const owner=await fixture('reader-acknowledgement.json'),wire=await fixture('owner-wire.json'),plan=await fixture('reader-state.json');
const boxes=dialog=>dialog.all().filter(node=>node.tag==='input');
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
const withDialog=async run=>{
 const dom=installDOM(),old=Node.prototype.addEventListener;
 Node.prototype.addEventListener=function(name,fn){if(name==='close')this.onclose=fn;};
 try{await run(dom);}finally{Node.prototype.addEventListener=old;dom.restore();}
};
// the real plan on the fixtures; hold.guard / hold.post park the next guard read / write until released
async function mountPlan(dom,hold={}){
 const {mountReaderPlan}=await import('../src/laplace/web/static_shared/workspace-spine.mjs');
 const detail=structuredClone(plan.detail);detail.sections[0].reader_transition.input_currentness=structuredClone(owner.guard.reader_transition.input_currentness);
 const second=structuredClone(detail);second.sections[0].id='second';second.sections[0].title='Second';
 const workspace=new Node('main');workspace.className='workspace';const host=new Node('section');workspace.append(host);dom.body.append(workspace);
 const log={gets:[],posts:[],changed:0};
 const controller=await mountReaderPlan(host,{project:'book',onChanged:()=>{log.changed++;},request:async(url,payload)=>{
  if(payload){log.posts.push(payload);if(hold.post){const parked=hold.post;hold.post=null;return parked.promise;}return owner.reply_recorded;}
  const q=new URL(url,'http://local').searchParams;log.gets.push(Object.fromEntries(q));
  if(q.get('projection')==='guard'){if(hold.guard){const parked=hold.guard;hold.guard=null;await parked.promise;}return structuredClone(owner.guard);}
  if(q.get('view')==='summary')return structuredClone(wire.summary_after);
  return structuredClone(q.get('section_ids')==='["second"]'?second:detail);
 }});
 const open=async()=>{const door=host.all().find(node=>node.attrs?.['data-control']==='reader-plan:acknowledge-inputs');assert.ok(door,'the door is offered');
  const opened=door.click();return {opened,dialog:()=>workspace.all().find(node=>node.tag==='dialog')||dom.dialogs().at(-1)};};
 return {controller,log,open,workspace};
}
const detailReads=log=>log.gets.filter(q=>q.view==='detail'&&q.projection!=='guard').length;

test('destroying the plan closes its open acknowledgement; the retained dialog posts and refreshes nothing',()=>withDialog(async dom=>{
 const {controller,log,open,workspace}=await mountPlan(dom);
 const {opened,dialog}=await open();await opened;const held=dialog();
 assert.ok(held&&held.open&&boxes(held).length,'the dialog is open with its inputs');
 controller.destroy();
 assert.equal(held.open,false,'destroy closes the dialog');assert.equal(held.isConnected,false,'and removes it');
 assert.equal(workspace.all().some(node=>node===held),false);
 const reads=detailReads(log);
 boxes(held)[0].checked=true;await findButton(held,'Record selected inputs as inspected').click();
 assert.equal(log.posts.length,0,'no POST after destroy');assert.equal(log.changed,0,'no onChanged after destroy');
 assert.equal(detailReads(log),reads,'no refresh after destroy');
 assert.match(held.textContent,/no longer open\. Nothing was recorded/);
}));

test('selecting another reader-plan item disposes the acknowledgement of the previous item',()=>withDialog(async dom=>{
 const {controller,log,open}=await mountPlan(dom);
 const {opened,dialog}=await open();await opened;const held=dialog();
 await controller.select('second');
 assert.equal(held.open,false,'the dialog of "first" is closed when "second" is selected');
 boxes(held)[0].checked=true;await findButton(held,'Record selected inputs as inspected').click();
 assert.equal(log.posts.length,0);assert.equal(log.changed,0);
}));

test('a guard read still pending at destroy mounts nothing and posts nothing',()=>withDialog(async dom=>{
 const guard=deferred();
 const {controller,log,open}=await mountPlan(dom,{guard});
 const {opened,dialog}=await open();
 await new Promise(resolve=>setTimeout(resolve,0));const held=dialog();
 assert.ok(held,'the dialog shows while its guard read is pending');assert.equal(boxes(held).length,0);
 controller.destroy();guard.resolve();await opened;
 assert.equal(held.open,false);assert.equal(boxes(held).length,0,'the late guard reply lists nothing');
 assert.equal(log.posts.length,0);assert.equal(log.changed,0);
}));

test('a write acknowledged after destroy states RECORDED with the exact read, refreshes no view and offers only Close',()=>withDialog(async dom=>{
 const post=deferred();
 const {controller,log,open}=await mountPlan(dom,{post});
 const {opened,dialog}=await open();await opened;const held=dialog();
 boxes(held)[0].checked=true;const clicked=findButton(held,'Record selected inputs as inspected').click();
 await new Promise(resolve=>setTimeout(resolve,0));
 assert.equal(log.posts.length,1,'the write was sent');assert.deepEqual(log.posts[0],owner.submission,'with the named pins only');
 const reads=detailReads(log);
 controller.destroy();
 assert.equal(held.open,true,'a dialog with a write out stays to report it');
 post.resolve(owner.reply_recorded);await clicked;
 assert.match(held.textContent,/Recorded as inspected: Citation new-a\..*Do not repeat the recorded action\. The reader-plan view closed or moved on, so it was not refreshed\./s);
 assert.match(held.textContent,/Exact read: GET \/work\/structure\?project=book&view=detail&section_ids=first&projection=guard&subject=contract\./);
 assert.equal(held.dataset.outcome,'orphaned');
 assert.equal(findButton(held,'Record selected inputs as inspected').hidden,true);assert.equal(findButton(held,'Re-read inputs').hidden,true);
 assert.equal(log.changed,0,'no onChanged for the closed view');assert.equal(detailReads(log),reads,'no refresh of any view');
 assert.equal(log.posts.length,1,'never resent');
 await findButton(held,'Close').click();assert.equal(held.isConnected,false);
}));

test('a write that fails after destroy is reported as unknown with the exact read, never as not recorded',()=>withDialog(async dom=>{
 const post=deferred();
 const {controller,log,open}=await mountPlan(dom,{post});
 const {opened,dialog}=await open();await opened;const held=dialog();
 boxes(held)[0].checked=true;const clicked=findButton(held,'Record selected inputs as inspected').click();
 await new Promise(resolve=>setTimeout(resolve,0));
 controller.destroy();post.reject(Error('The local engine is unavailable.'));await clicked;
 assert.match(held.textContent,/Whether the owner recorded this is unknown \(The local engine is unavailable\.\)\. Read the subject before recording again\./);
 assert.match(held.textContent,/Exact read: GET \/work\/structure\?/);
 assert.doesNotMatch(held.textContent,/Nothing was recorded/);
 assert.equal(log.posts.length,1);assert.equal(log.changed,0);
}));

test('the lower-level dialog posts nothing once its isCurrent is false, and a live dialog still records and re-reads',()=>withDialog(async dom=>{
 let current=true;const sent=[],saved=[];let reads=0;
 const acquire=async()=>{reads++;const guard=structuredClone(owner.guard);
  return {action:readerSubjectAction(guard,'contract',{project:'book',sectionId:'first'}),currentness:guard.reader_transition.input_currentness};};
 const dialog=await acknowledgeReaderInputs({project:'book',opener:dom.editor,acquire,isCurrent:()=>current,
  request:async(url,payload)=>{sent.push(payload);return sent.length===1?owner.reply_recorded:owner.reply_already;},onSaved:async(r,o)=>saved.push(o.disposition)});
 boxes(dialog)[0].checked=true;await findButton(dialog,'Record selected inputs as inspected').click();
 assert.deepEqual(saved,['RECORDED']);assert.equal(reads,2,'a live dialog re-reads after recording');
 boxes(dialog)[0].checked=true;await findButton(dialog,'Record selected inputs as inspected').click();
 assert.deepEqual(saved,['RECORDED','ALREADY_RECORDED']);
 current=false;boxes(dialog)[0].checked=true;await findButton(dialog,'Record selected inputs as inspected').click();
 assert.equal(sent.length,2,'no POST once the subject is no longer current');assert.equal(saved.length,2);
 assert.match(dialog.textContent,/no longer open\. Nothing was recorded/);
}));
