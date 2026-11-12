import assert from 'node:assert/strict';
import {test} from 'node:test';
import {validateResolution,resolutionSubmission,resolutionReceipt,resolutionAuthorLabel,resolutionFinalizationSubmission,validateResolutionFinalization,mountProposalResolution,mountResolutionTarget} from '../src/laplace/web/static_shared/proposal-resolution.mjs';
import {installDOM,Node,findButton} from './helpers/evidence_reader_harness.mjs';
import {proposalPresentation} from '../src/laplace/web/static_shared/workspace-session.mjs';
import {recordedProposalAttention} from '../src/laplace/web/static_shared/manuscript-editing.mjs';
import {humanWire} from './helpers/human_resolution_fixture.mjs';

const storage=()=>{const values=new Map();return {getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,String(value)),removeItem:key=>values.delete(key)};};
test('actual owner hunk actions preserve exact source/input guards and reject crossed or incomplete selections',()=>{
 const value=humanWire.prepared;assert.equal(validateResolution(value,{project:'fixture'}),value);
 const submitted=resolutionSubmission(value,'apply',{selectedChoices:humanWire.apply_payload.choices});assert.deepEqual(submitted.payload,humanWire.apply_payload);
 assert.equal(resolutionReceipt(humanWire.receipt,{project:'fixture',subject:value.subject}).applied,true);
 for(const selectedChoices of [[],humanWire.apply_payload.choices.slice(1),humanWire.apply_payload.choices.map(row=>({...row,hunk_id:'HUNK-guessed'}))])assert.throws(()=>resolutionSubmission(value,'apply',{selectedChoices}),/Every owner-issued hunk/);
 assert.throws(()=>resolutionSubmission(value,'apply',{selectedChoices:humanWire.apply_payload.choices,resolvedAfter:'Both supplied'}),/either complete/);
 const crossed=structuredClone(value);crossed.actions.apply.payload.target.expected_source_digest='sha256:'+'0'.repeat(64);assert.throws(()=>validateResolution(crossed,{project:'fixture'}),/displayed source/);
 const echoed=structuredClone(value);echoed.actions.preview.payload.target.before='A different echoed passage';assert.throws(()=>validateResolution(echoed,{project:'fixture'}),/displayed source/);
 assert.equal(value.actions.apply.payload.target.before,undefined,'Owner actions carry only exact guards; the picker retains full source text.');
 assert.throws(()=>validateResolution(value,{project:'other'}),/different project/);
});

test('three human choices preview then apply without provider work, retaining exact successor/predecessor receipt',async()=>{
 const dom=installDOM(),host=new Node('section'),state={},saved=storage(),posts=[],applied=[];dom.body.append(host);
 try{
  mountProposalResolution(host,{project:'fixture',value:humanWire.prepared,state,storage:saved,storageKey:'current-draft',
    request:async(path,payload)=>{posts.push({path,payload});assert.equal(path,'/authoring/proposal-decision');return payload.decision==='preview-resolution'?humanWire.preview:humanWire.receipt;},onApplied:(...args)=>applied.push(args)});
  assert.equal(findButton(host,'Apply resolved revision').disabled,true);
  await findButton(host,'Keep current').click();await findButton(host,'Next change').click();await findButton(host,'Use proposed').click();await findButton(host,'Next change').click();await findButton(host,'Custom').click();
  const editor=host.querySelectorAll('textarea')[0];editor.value='Cobalt statement.';editor.selectionStart=3;editor.selectionEnd=5;editor.oninput();
  await findButton(host,'Preview resolved text').click();assert.match(host.textContent,/Emerald statement/);assert.match(host.textContent,/Cobalt statement/);assert.equal(findButton(host,'Apply resolved revision').disabled,false);
  await findButton(host,'Apply resolved revision').click();assert.equal(posts.length,2);assert.deepEqual(posts[1].payload,humanWire.apply_payload);assert.equal(applied[0][1].candidate.id,humanWire.receipt.candidate_ref.id);assert.match(host.textContent,/Resolved revision applied/);assert.equal(saved.getItem('current-draft'),null);assert.equal(dom.editor.value,'UNSAVED manuscript');
 }finally{dom.restore();}
});

test('source races retain custom choice and caret and require explicit adoption of a refreshed owner comparison',async()=>{
 const dom=installDOM(),host=new Node('section'),state={};dom.body.append(host);let controller;
 try{
  controller=mountProposalResolution(host,{project:'fixture',value:humanWire.prepared,state,request:async()=>{throw Error('CHANGED_INPUT: inspected current source changed');}});
  await findButton(host,'Custom').click();let editor=host.querySelectorAll('textarea')[0];editor.value='Retained custom words';editor.selectionStart=4;editor.selectionEnd=9;editor.oninput();
  await findButton(host,'Preview resolved text').click();assert.match(host.textContent,/CHANGED_INPUT/);assert.equal(state.choices[humanWire.prepared.hunks[0].id].text,'Retained custom words');assert.deepEqual(state.caret,{hunk_id:humanWire.prepared.hunks[0].id,start:4,end:9});
  controller.refresh(humanWire.fresh);assert.match(host.textContent,/earlier choices.*retained/);assert.equal(findButton(host,'Preview resolved text').disabled,true);
  await findButton(host,'Use this inspected comparison').click();assert.equal(state.resolution_token,humanWire.fresh.resolution_token);assert.equal(state.retained_choices[humanWire.prepared.hunks[0].id].text,'Retained custom words');assert.equal(dom.editor.value,'UNSAVED manuscript');
 }finally{controller?.destroy();dom.restore();}
});

test('a no-change preview does not create a candidate or invite application',async()=>{
 const dom=installDOM(),host=new Node('section');dom.body.append(host);let calls=0;
 try{mountProposalResolution(host,{project:'fixture',value:humanWire.prepared,request:async()=>{calls++;return humanWire.unchanged;}});await findButton(host,'Preview resolved text').click();assert.match(host.textContent,/No application is needed/);assert.equal(findButton(host,'Apply resolved revision').disabled,true);assert.equal(calls,1);}finally{dom.restore();}
});

test('unproven placement uses exact current source selection without source save or message retargeting',async()=>{
 const dom=installDOM(),host=new Node('section'),calls=[],targets=[];dom.body.append(host);
 try{
  mountResolutionTarget(host,{project:'fixture',value:humanWire.target_required,request:async(path,payload)=>{calls.push({path,payload});return humanWire.source;},onTarget:value=>targets.push(value)});
  const select=host.querySelector('select');select.value=humanWire.source.file;await select.onchange();const source=host.querySelector('textarea'),before=humanWire.prepared.current,start=source.value.indexOf(before);source.selectionStart=start;source.selectionEnd=start+before.length;source.onselect();
  await findButton(host,'Use selected current passage').click();assert.equal(calls.length,1);assert.equal(calls[0].payload,undefined);assert.equal(targets[0].before,before);assert.equal(targets[0].expected_source_digest,humanWire.source.expected_source_digest);assert.equal(targets[0].expected_selection,humanWire.source.selection_identity);assert.equal(dom.editor.value,'UNSAVED manuscript');
 }finally{dom.restore();}
});


test('owner-stable hunk identities preserve exact authored choices and caret after explicit harmless source refresh',async()=>{
 const dom=installDOM(),host=new Node('section'),state={};dom.body.append(host);
 try{
  const old=humanWire.prepared,next=humanWire.harmless;assert.notEqual(old.resolution_token,next.resolution_token);assert.deepEqual(old.hunks.map(row=>row.id),next.hunks.map(row=>row.id));
  const controller=mountProposalResolution(host,{project:'fixture',value:old,state,request:async()=>{throw Error('No implicit requests');}});
  await findButton(host,'Custom').click();const editor=host.querySelectorAll('textarea')[0];editor.value='My retained wording';editor.selectionStart=2;editor.selectionEnd=7;editor.oninput();
  controller.refresh(next);assert.equal(findButton(host,'Preview resolved text').disabled,true);await findButton(host,'Use this inspected comparison').click();
  assert.equal(state.choices[next.hunks[0].id].text,'My retained wording');assert.deepEqual(state.caret,{hunk_id:next.hunks[0].id,start:2,end:7});assert.equal(findButton(host,'Preview resolved text').disabled,false);controller.destroy();
 }finally{dom.restore();}
});

test('resolved revision attribution distinguishes actual human and native actors without invented model turns',()=>{
 assert.equal(resolutionAuthorLabel({kind:'human'}),'Human-authored revision');
 assert.equal(resolutionAuthorLabel({kind:'agent',role:'author-parent',turn_id:'WT-owned'}),'Agent-authored revision · author-parent · WT-owned');
 assert.equal(resolutionAuthorLabel({}),'Resolved revision · authorship not recorded');
});


test('newer custom input during an admitted apply remains authored draft beside the exact effect receipt',async()=>{
 const dom=installDOM(),host=new Node('section'),state={},saved=storage();dom.body.append(host);let release,observed;
 try{
  mountProposalResolution(host,{project:'fixture',value:humanWire.prepared,state,storage:saved,storageKey:'race',request:async(_url,payload)=>payload.decision==='preview-resolution'?humanWire.preview:new Promise(resolve=>{release=resolve;}),onApplied:(_value,receipt)=>{observed=receipt;}});
  await findButton(host,'Preview resolved text').click();const applying=findButton(host,'Apply resolved revision').click();
  // Text input can arrive while the immutable earlier apply is in flight.
  state.choices[humanWire.prepared.hunks[0].id]={choice:'custom',text:'newer'};
  // Use the full-source editor input path so the authored revision counter advances.
  const editor=host.querySelectorAll('textarea').at(-1);editor.value='Newer unsent source';editor.oninput();release(humanWire.receipt);await applying;
  assert.equal(observed.newerDraft,true);assert.equal(state.resolved_after,'Newer unsent source');assert.ok(saved.getItem('race'));assert.match(host.textContent,/newer local choices remain retained/);assert.equal(findButton(host,'Apply resolved revision').disabled,true);
 }finally{dom.restore();}
});


test('real owner coarsening requires inspected adoption without discarding custom drafts or disabling full resolution',async()=>{
 const dom=installDOM(),host=new Node('section'),state={};dom.body.append(host);
 try{
  const exact=humanWire.prepared,coarse=humanWire.coarse;assert.equal(coarse.comparison.scope,'coarse');assert.equal(exact.resolution_token,coarse.resolution_token);assert.equal(coarse.hunks.length,1);assert.equal(coarse.current,exact.current);assert.equal(coarse.proposed,exact.proposed);
  const controller=mountProposalResolution(host,{project:'fixture',value:exact,state,request:async()=>{throw Error('No implicit request');}});
  await findButton(host,'Next change').click();await findButton(host,'Custom').click();const oldId=exact.hunks[1].id,editor=host.querySelectorAll('textarea')[0];editor.value='Retained small-region words';editor.selectionStart=3;editor.selectionEnd=8;editor.oninput();
  controller.refresh(coarse);assert.equal(findButton(host,'Preview resolved text').disabled,true);assert.match(host.textContent,/comparison regions changed/);assert.match(host.textContent,/Some changes are grouped/);
  await findButton(host,'Use this inspected comparison').click();assert.equal(state.retained_choices[oldId].text,'Retained small-region words');assert.deepEqual(state.choices,{});assert.equal(findButton(host,'Preview resolved text').disabled,false);
  await findButton(host,'Custom').click();assert.equal(host.querySelectorAll('textarea').length,2);assert.match(host.textContent,/Edit the complete resolved source/);
  const wholeId=coarse.hunks[0].id,whole=host.querySelectorAll('textarea')[0];whole.value='Retained grouped words';whole.oninput();
  controller.refresh(exact);await findButton(host,'Use this inspected comparison').click();assert.equal(state.retained_choices[oldId].text,'Retained small-region words');assert.equal(state.retained_choices[wholeId].text,'Retained grouped words');assert.equal(dom.editor.value,'UNSAVED manuscript');controller.destroy();
 }finally{dom.restore();}
});

test('current passage can be selected by bounded explicit source lines without keyboard or pointer precision',async()=>{
 const dom=installDOM(),host=new Node('section'),targets=[],calls=[];dom.body.append(host);
 try{
  mountResolutionTarget(host,{project:'fixture',value:humanWire.target_required,request:async(path,payload)=>{calls.push({path,payload});return humanWire.source;},onTarget:value=>targets.push(value)});
  const file=host.querySelector('select');file.value=humanWire.source.file;await file.onchange();
  const [start,end]=host.querySelectorAll('input');assert.equal(start.attrs['aria-label'],'Start source line');assert.equal(end.attrs['aria-label'],'End source line');
  start.value='3';end.value='999';end.oninput();assert.equal(findButton(host,'Use selected current passage').disabled,true);assert.match(host.textContent,/Choose source lines/);
  end.value='7';end.oninput();assert.equal(findButton(host,'Use selected current passage').disabled,false);assert.match(host.textContent,/Selected source lines 3–7/);
  await findButton(host,'Use selected current passage').click();assert.equal(calls.length,1);assert.equal(calls[0].payload,undefined);assert.deepEqual(targets[0],{file:humanWire.source.file,line_start:3,line_end:7,before:humanWire.prepared.current,expected_source_digest:humanWire.source.expected_source_digest,expected_selection:humanWire.source.selection_identity});assert.equal(dom.editor.value,'UNSAVED manuscript');
 }finally{dom.restore();}
});


test('owner-issued metadata recovery finishes only the exact predecessor record after later source changes',async()=>{
 const pending=humanWire.pending_receipt,finished=humanWire.finished_receipt,disposition=pending.disposition,ref=pending.candidate_ref;
 assert.equal(humanWire.pending_history.edits[0].pending_successors[0].disposition_status,'PENDING');assert.deepEqual(humanWire.pending_history.edits[0].pending_successors[0].successor_ref,ref);
 assert.equal(pending.application.complete,true);assert.equal(disposition.status,'PENDING');assert.equal(finished.metadata_only,true);assert.equal(finished.disposition.status,'RECORDED');
 const action=disposition.recovery_action,submission=resolutionFinalizationSubmission(action,'fixture',ref,disposition);assert.equal(submission.payload.decision,'finish-resolution-record');assert.equal(validateResolutionFinalization(finished,{project:'fixture',ref,disposition}),finished);
 for(const payload of [{...submission.payload,resolution_application_id:'WA-other'},{...submission.payload,decision:'apply-candidate'},{...submission.payload,predecessor:{...submission.payload.predecessor,edit_id:'EDIT-other'}}])assert.throws(()=>resolutionFinalizationSubmission({...action,payload},'fixture',ref,disposition),/matching reconciliation-record/);
 const dom=installDOM(),host=new Node('section'),requests=[];dom.body.append(host);
 try{
  mountProposalResolution(host,{project:'fixture',value:humanWire.pending_prepared,request:async(_url,payload)=>payload.decision==='preview-resolution'?humanWire.pending_preview:pending,onFinishResolution:(...args)=>requests.push(args)});
  await findButton(host,'Preview resolved text').click();await findButton(host,'Apply resolved revision').click();assert.match(host.textContent,/The text is saved/);await findButton(host,'Finish reconciliation record').click();assert.equal(requests.length,1);assert.deepEqual(requests[0],[action,ref,disposition]);assert.equal(findButton(host,'Apply resolved revision').disabled,true);assert.equal(dom.editor.value,'UNSAVED manuscript');
 }finally{dom.restore();}
});


test('owner-resolved predecessor remains truthful saved history rather than an active or applied original proposal',()=>{
 const old=humanWire.original_history;assert.equal(old.proposal_state,'resolved-into-successor');assert.equal(old.read_only,true);assert.equal(old.edits[0].status,'resolved-into-successor');
 const presentation=proposalPresentation({...old,proposal_edit_count:old.edits.length});assert.equal(presentation.terminal,true);assert.equal(presentation.label,'Saved proposal resolved in a later revision');assert.doesNotMatch(presentation.label,/applied|accepted/);
 assert.match(recordedProposalAttention(old).label,/Resolved in a later revision/);assert.deepEqual(old.edits[0].successor_ref,humanWire.receipt.candidate_ref);assert.ok(old.edits[0].successor_read);
});
