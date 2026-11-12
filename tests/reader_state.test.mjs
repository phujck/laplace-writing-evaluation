import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {readerMetadataSubmission,editReaderMetadata,inspectArchitecturePrior} from '../src/laplace/web/static_shared/reader-state.mjs';
import {installDOM,Node,findButton} from './helpers/evidence_reader_harness.mjs';
const fixture=JSON.parse(await readFile(new URL('./fixtures/editor_spine/owner-wire.json',import.meta.url),'utf8'));
// The descriptor shape is the agreed owner declaration. Final runtime tests use
// the producer's emitted contract fixture, rather than minting a write token here.
const readerOwner=JSON.parse(await readFile(new URL('./fixtures/editor_spine/reader-state.json',import.meta.url),'utf8'));
const contractBasis=readerOwner.initial.sections[0].reader_transition.reader_basis;
test('contextual architecture editor delegates to the real profile owner while read-only peeks keep their own route',async()=>{
 const profile=JSON.parse(await readFile(new URL('./fixtures/editor_spine/profile-candidates.json',import.meta.url),'utf8'));
 const dom=installDOM(),oldListener=Node.prototype.addEventListener,reads=[],generated=[];
 Node.prototype.addEventListener=function(name,fn){if(name==='close')this.onclose=fn;};
 try{
  const request=async url=>{reads.push(url);const q=new URL(url,'http://local').searchParams;assert.equal(q.get('project'),'book');assert.equal(q.get('family'),'architecture');assert.equal(q.get('scope'),'workspace');return q.get('view')==='candidates'?{candidates:[]}:structuredClone(profile.before);};
  const dialog=await inspectArchitecturePrior({project:'book',request,value:{},read:()=>assert.fail('Editable preferences use their existing profile owner.'),opener:dom.editor,onGenerate:value=>generated.push(value)});
  assert.equal(reads.length,2);assert.ok(findButton(dialog,'Edit structural preferences')||findButton(dialog,'Write structural preferences'));
  await findButton(dialog,'Generate suggestion').click();assert.equal(generated.length,1);assert.equal(generated[0].project,'book');assert.equal(generated[0].family,'architecture');
  await findButton(dialog,'Close').click();assert.equal(document.activeElement,dom.editor);
  let readOnlyReads=0;
  const peek=await inspectArchitecturePrior({value:{read_more:{operation:'structure',payload:{view:'architecture-profile'}}},read:async()=>{readOnlyReads++;return profile.before;},opener:dom.editor});
  assert.equal(readOnlyReads,1);assert.match(peek.textContent,/read-only in this view/);assert.equal(findButton(peek,'Generate suggestion'),undefined);await findButton(peek,'Close').click();
 }finally{Node.prototype.addEventListener=oldListener;dom.restore();}
});
const action=()=>({operation:'structure_change',http:{method:'POST',route:'/work/structure/change'},
 payload:{operation:'section_contract',section_id:'first',expected_plan_revision:fixture.summary_after.authority.plan_revision,expected_contract_revision:null,expected_reader_basis:contractBasis},
 fields:[{name:'entry_state',label:'Reader arrives with',type:'string',multiline:true},
 {name:'depends_on',label:'Authored dependencies',type:'string_array',choices:[{value:'a',label:'Earlier idea'},{value:'b',label:'Later explanation'}]}],
 values:{entry_state:'A stated assumption',depends_on:['b','a']}});
test('reader metadata payload binds the original template and preserves only changed authored fields',()=>{
 const base=action();assert.deepEqual(readerMetadataSubmission(base,base.values,'book').changes,{});
 assert.deepEqual(readerMetadataSubmission(base,{...base.values,entry_state:'A revised assumption'},'book'),{project:'book',...base.payload,changes:{entry_state:'A revised assumption'}});
 assert.throws(()=>readerMetadataSubmission({...base,payload:{...base.payload,project:'other'}},base.values,'book'),/unobserved/);
 assert.throws(()=>readerMetadataSubmission(base,{title:'Guessed field'},'book'),/not offered/);
 assert.throws(()=>readerMetadataSubmission(base,{depends_on:'b'},'book'),/field type/);
});
test('descriptor form preserves saved dependency order and sends no incidental changes',async()=>{
 const dom=installDOM(),calls=[],storage=new Map();const cache={getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)};
 const oldListener=Node.prototype.addEventListener;Node.prototype.addEventListener=function(name,fn){if(name==='close')this.onclose=fn;};
 try{
  const original=action();original.payload.expected_contract_revision=fixture.summary_after.authority.plan_revision;
  const dialog=await editReaderMetadata({project:'book',action:original,title:'Reader transition',opener:dom.editor,storage:cache,
   request:async(url,payload)=>{calls.push({url,payload});return {applied:true,plan_publication:{owner:'reader-contract',status:'COMMITTED',complete:false,ledger_append_count:1}};}});
  const form=dialog.all().find(node=>node.tag==='form');await form.onsubmit({preventDefault(){}});assert.equal(calls.length,0);
  const entry=dialog.all().find(node=>node.name==='entry_state');entry.value='Reader knows the new assumption';form.oninput();
  await form.onsubmit({preventDefault(){}});assert.equal(calls.length,1);
  assert.deepEqual(calls[0].payload.changes,{entry_state:'Reader knows the new assumption'});
  assert.match(dialog.textContent,/recorded, but required follow-through is incomplete/);assert.equal(storage.size,1);
  await form.onsubmit({preventDefault(){}});assert.equal(calls.length,1,'incomplete publication is not replayed');
  await findButton(dialog,'Close').click();assert.equal(dom.editor.value,'UNSAVED manuscript');assert.equal(document.activeElement,dom.editor);
 }finally{Node.prototype.addEventListener=oldListener;dom.restore();}
});

test('paragraph movement preserves opaque IDs and refuses a paged subset as whole-plan order',async()=>{
 const {readerParagraphAction}=await import('../src/laplace/web/static_shared/reader-state.mjs');
 const prepared={operation:'structure_change',http:{method:'POST',route:'/work/structure/change'},payload:{operation:'paragraph_plan',section_id:'first',expected_plan_revision:fixture.summary_after.authority.plan_revision,expected_narrative_revision:null,expected_reader_basis:{...contractBasis,subject_id:'@order'},action:'reorder',order:['unit:old-7','merged:a+b','unit:2']}};
 const result=readerParagraphAction(prepared,'book',['unit:2','unit:old-7','merged:a+b']);
 assert.deepEqual(result.order,['unit:2','unit:old-7','merged:a+b']);assert.equal(Object.hasOwn(result,'changes'),false);
 assert.throws(()=>readerParagraphAction(prepared,'book',['unit:old-7']),/complete original/);
 assert.throws(()=>readerParagraphAction(prepared,'book',['unit:1','unit:2','unit:3']),/complete original/);
});

test('actual reader publication and retained partial receipts drive acknowledgement without fresh input substitution',async()=>{
 const {readerAcknowledgementMatches,readerReviewSubmission}=await import('../src/laplace/web/static_shared/reader-state.mjs');
 const {planPublicationDisposition}=await import('../src/laplace/web/static_shared/plan-publication.mjs');
 const original=readerOwner.initial.sections[0].reader_transition.edit_action;
 const payload={project:'book',...original.payload};
 assert.equal(readerAcknowledgementMatches(readerOwner.contract_write,payload),true);
 const corrupted=structuredClone(readerOwner.contract_write),key=Object.keys(original.payload.expected_reader_basis.inputs)[0];corrupted.reader_basis.inputs[key]='sha256:'+'0'.repeat(64);
 assert.equal(readerAcknowledgementMatches(corrupted,payload),false);
 assert.equal(planPublicationDisposition(readerOwner.committed_incomplete).acknowledged,false);
 assert.match(planPublicationDisposition(readerOwner.committed_incomplete).message,/recorded/);
 assert.equal(planPublicationDisposition(readerOwner.partial_spine).publication.status,'PARTIAL');
 const prepared=readerOwner.detail.sections[0].reader_transition.review_action;
 assert.deepEqual(readerReviewSubmission(prepared,'book').reader_basis,prepared.payload.reader_basis);
});

test('a deferred save locks reader inputs until acknowledgement and refresh have both settled',async()=>{
 const dom=installDOM(),storage=new Map(),cache={getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)};
 const oldListener=Node.prototype.addEventListener;Node.prototype.addEventListener=function(name,fn){if(name==='close')this.onclose=fn;};
 let finishWrite,finishRefresh;
 const write=new Promise(resolve=>finishWrite=resolve),refresh=new Promise(resolve=>finishRefresh=resolve);
 try{
  const original=readerOwner.initial.sections[0].reader_transition.edit_action;
  const dialog=await editReaderMetadata({project:'book',action:original,title:'Reader transition',opener:dom.editor,storage:cache,request:async()=>write,onSaved:async()=>refresh});
  const input=dialog.all().find(node=>node.name==='entry_state'),form=dialog.all().find(node=>node.tag==='form');
  input.value=readerOwner.contract_request.changes.entry_state;form.oninput();
  const saving=form.onsubmit({preventDefault(){}});
  for(const control of dialog.all().filter(node=>['input','textarea','select','button'].includes(node.tag)))assert.equal(control.disabled,true,'pending '+control.tag+' stays non-editable');
  let cancelled=false;dialog.oncancel({preventDefault(){cancelled=true;}});assert.equal(cancelled,true,'a pending write is not presented as cancellable');
  finishWrite(readerOwner.contract_write);await new Promise(resolve=>setImmediate(resolve));
  assert.equal(input.disabled,true,'post-write view refresh must not reopen a late-typing window');assert.equal(dialog.open,true);
  finishRefresh();await saving;assert.equal(dialog.open,false);assert.equal(storage.size,0);
 }finally{finishWrite?.(readerOwner.contract_write);finishRefresh?.();Node.prototype.addEventListener=oldListener;dom.restore();}
});
