// G1 human input acknowledgement (S2, 2026-10-15). The fixture is the real reader_plan owner: its guard
// subject, the submission this module built, and the owner's RECORDED and ALREADY_RECORDED replies.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {readerSubjectAction,readerAcknowledgementSubmission,readerAcknowledgementOutcome,acknowledgeReaderInputs,renderReaderState,readerInputName} from '../src/laplace/web/static_shared/reader-state.mjs';
import {installDOM,Node,findButton} from './helpers/evidence_reader_harness.mjs';
const owner=JSON.parse(await readFile(new URL('./fixtures/editor_spine/reader-acknowledgement.json',import.meta.url),'utf8'));
const call=()=>readerSubjectAction(structuredClone(owner.guard),'contract',{project:'book',sectionId:'first'});
const pins=()=>call().payload.expected_reader_basis.inputs;

test('the submission is the current edit call with no change and only the named keys at the owner pins',()=>{
 const sent=readerAcknowledgementSubmission(call(),['citation:new-a'],'book');
 assert.deepEqual(sent,owner.submission,'the module builds the exact bytes the owner accepted');
 assert.deepEqual(sent.changes,{});
 assert.deepEqual(sent.input_observations,{'citation:new-a':pins()['citation:new-a']});
 assert.deepEqual(sent.expected_reader_basis,call().payload.expected_reader_basis,'the expected basis is untouched');
 assert.throws(()=>readerAcknowledgementSubmission(call(),[],'book'),/at least one/);
 assert.throws(()=>readerAcknowledgementSubmission(call(),['citation:gone'],'book'),/no longer consumed/);
 assert.throws(()=>readerAcknowledgementSubmission(call(),['authored-subject'],'book'),/no longer consumed/);
 assert.throws(()=>readerAcknowledgementSubmission(call(),['citation:new-a'],'other'),/basis/);
 const altered=call();altered.payload.changes={entry_state:'smuggled'};
 assert.throws(()=>readerAcknowledgementSubmission(altered,['citation:new-a'],'book'),/unobserved fields/);
});

test('owner replies: RECORDED and ALREADY_RECORDED are explained; a reply for other inputs is refused',()=>{
 const recorded=readerAcknowledgementOutcome(owner.reply_recorded,owner.submission);
 assert.equal(recorded.disposition,'RECORDED');assert.match(recorded.receipt,/^RPUB-/);
 assert.match(recorded.text,/Recorded as inspected: Citation new-a\. Input standing is now unobserved\. This is not a review/);
 const again=readerAcknowledgementOutcome(owner.reply_already,owner.submission);
 assert.equal(again.disposition,'ALREADY_RECORDED');assert.equal(again.receipt,null);assert.match(again.text,/nothing new was written/);
 const other=structuredClone(owner.reply_recorded);other.observation.acknowledged_inputs=['citation:new-b'];
 assert.throws(()=>readerAcknowledgementOutcome(other,owner.submission),/does not match/);
 const content=structuredClone(owner.reply_recorded);content.content_changed=true;
 assert.throws(()=>readerAcknowledgementOutcome(content,owner.submission),/does not match/);
 assert.match(owner.stale_error,/CHANGED_INPUT/,'the owner refuses a resend after the subject moved');
 assert.equal(readerInputName('architecture'),'Structural writing preferences');
});

const withDialog=async run=>{
 const dom=installDOM(),old=Node.prototype.addEventListener;
 Node.prototype.addEventListener=function(name,fn){if(name==='close')this.onclose=fn;};
 try{await run(dom);}finally{Node.prototype.addEventListener=old;dom.restore();}
};
const acquire=(reads)=>async()=>{reads.push(1);const guard=structuredClone(owner.guard);return {action:readerSubjectAction(guard,'contract',{project:'book',sectionId:'first'}),currentness:guard.reader_transition.input_currentness};};
const boxes=dialog=>dialog.all().filter(node=>node.tag==='input');

test('the dialog lists inspectable inputs, sends only the checked pins, and re-reads after recording',()=>withDialog(async dom=>{
 const reads=[],sent=[],saved=[];
 const dialog=await acknowledgeReaderInputs({project:'book',opener:dom.editor,acquire:acquire(reads),
  request:async(url,payload)=>{sent.push({url,payload});return sent.length===1?owner.reply_recorded:owner.reply_already;},
  onSaved:async(result,outcome)=>saved.push(outcome.disposition)});
 assert.equal(reads.length,1);assert.deepEqual(boxes(dialog).map(box=>box.value),['citation:new-a','citation:new-b']);
 await findButton(dialog,'Record selected inputs as inspected').click();
 assert.equal(sent.length,0,'nothing is sent without a selection');assert.match(dialog.textContent,/at least one/);
 boxes(dialog)[0].checked=true;
 await findButton(dialog,'Record selected inputs as inspected').click();
 assert.equal(sent.length,1);assert.equal(sent[0].url,'/work/structure/change');assert.deepEqual(sent[0].payload,owner.submission);
 assert.deepEqual(saved,['RECORDED']);assert.equal(reads.length,2,'the subject is re-read after recording');
 assert.match(dialog.textContent,/Recorded as inspected: Citation new-a/);
 assert.ok(boxes(dialog).every(box=>!box.checked&&!box.disabled),'the re-read list is fresh and enabled');
 await findButton(dialog,'Close').click();assert.equal(document.activeElement,dom.editor);
}));

test('a moved input refuses without a refresh and a removed input is shown but not offered',()=>withDialog(async dom=>{
 const saved=[];let reads=0;
 const dialog=await acknowledgeReaderInputs({project:'book',opener:dom.editor,
  acquire:async()=>{reads++;const guard=structuredClone(owner.guard),current=guard.reader_transition.input_currentness;
   current.changed_inputs=[...current.changed_inputs,'citation:retired','authored-subject'];
   return {action:readerSubjectAction(guard,'contract',{project:'book',sectionId:'first'}),currentness:current};},
  request:async()=>{throw Error('CHANGED_INPUT: these inputs are not at the inspected pin; re-read the subject: citation:new-a');},
  onSaved:async()=>saved.push(1)});
 assert.deepEqual(boxes(dialog).map(box=>box.value),['citation:new-a','citation:new-b']);
 assert.match(dialog.textContent,/Citation retired is no longer consumed and cannot be acknowledged/);
 assert.match(dialog.textContent,/Authored content changed; edit or review the subject itself/);
 boxes(dialog)[1].checked=true;
 await findButton(dialog,'Record selected inputs as inspected').click();
 assert.match(dialog.textContent,/moved since this read\. Nothing was recorded/);assert.equal(saved.length,0);
 await findButton(dialog,'Re-read inputs').click();assert.equal(reads,2);
}));

test('the reader plan offers the acknowledgement only when its consumer wires the owner door',()=>withDialog(async dom=>{
 const transition={...structuredClone(owner.guard.reader_transition),status:'DECLARED'};
 const host=new Node('div'),called=[];
 renderReaderState(host,{section:{id:'first',reader_transition:transition},project:'book',onAcknowledgeInputs:value=>called.push(value)});
 const door=host.all().find(node=>node.dataset?.control==='reader-plan:acknowledge-inputs'||node.attrs?.['data-control']==='reader-plan:acknowledge-inputs');
 assert.ok(door,'a declared transition with unobserved inputs offers the door');
 await door.click();assert.equal(called.length,1);assert.equal(called[0],transition);
 const readOnly=new Node('div');renderReaderState(readOnly,{section:{id:'first',reader_transition:transition},project:'book'});
 assert.equal(readOnly.all().some(node=>node.attrs?.['data-control']==='reader-plan:acknowledge-inputs'),false);
}));

test('the mounted reader plan reads the exact contract guard, records through the owner route and refreshes the section',()=>withDialog(async dom=>{
 const {mountReaderPlan}=await import('../src/laplace/web/static_shared/workspace-spine.mjs');
 const wire=JSON.parse(await readFile(new URL('./fixtures/editor_spine/owner-wire.json',import.meta.url),'utf8'));
 const plan=JSON.parse(await readFile(new URL('./fixtures/editor_spine/reader-state.json',import.meta.url),'utf8'));
 const detail=structuredClone(plan.detail);detail.sections[0].reader_transition.input_currentness=structuredClone(owner.guard.reader_transition.input_currentness);
 const workspace=new Node('main');workspace.className='workspace';const host=new Node('section');workspace.append(host);dom.body.append(workspace);
 const gets=[],posts=[];
 await mountReaderPlan(host,{project:'book',request:async(url,payload)=>{
  if(payload){posts.push({url,payload});return owner.reply_recorded;}
  const q=new URL(url,'http://local').searchParams;gets.push(Object.fromEntries(q));
  if(q.get('projection')==='guard')return structuredClone(owner.guard);
  return structuredClone(q.get('view')==='summary'?wire.summary_after:detail);
 }});
 const door=host.all().find(node=>node.attrs?.["data-control"]==="reader-plan:acknowledge-inputs");assert.ok(door,'the editable plan offers the door');
 const before=gets.length;await door.click();
 const dialog=dom.dialogs().at(-1)||workspace.all().find(node=>node.tag==='dialog');assert.ok(dialog);
 assert.deepEqual([gets[before].projection,gets[before].subject,gets[before].section_ids],['guard','contract','["first"]'],'one bounded guard read of the exact subject');
 boxes(dialog)[0].checked=true;await findButton(dialog,'Record selected inputs as inspected').click();
 assert.equal(posts.length,1);assert.equal(posts[0].url,'/work/structure/change');assert.deepEqual(posts[0].payload,owner.submission);
 assert.ok(gets.slice(before+1).some(q=>q.view==='detail'&&q.projection!=='guard'),'the section is refreshed after recording');
 assert.match(dialog.textContent,/Recorded as inspected/);
}));
