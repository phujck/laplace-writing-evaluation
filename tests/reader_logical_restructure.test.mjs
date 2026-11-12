import {test} from 'node:test';
import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import {validateLogicalPreparation,createLogicalDraft,openLogicalRestructure} from '../src/laplace/web/static_shared/reader-logical-restructure.mjs';
import {installDOM,Node,findButton,loadReader} from './helpers/evidence_reader_harness.mjs';
import {logicalWire as wire} from './helpers/reader_logical_fixture.mjs';
import {restructureApplySubmission,restructureFollowThroughSubmission,validateRestructureEffect,renderRestructureOutcome,reconciliationSubmission,validateReconciliationResult,renderMetadataReconciliation,openMetadataReconciliation,inspectStructuralInput,openRecordedRestructure} from '../src/laplace/web/static_shared/reader-restructure.mjs';
import {renderReaderState} from '../src/laplace/web/static_shared/reader-state.mjs';
import {qualifiedOwnerHTTP} from '../src/laplace/web/static_shared/writing-owner-read.mjs';
import {projectRequest} from '../src/laplace/web/static_shared/workspace-session.mjs';

function dom(){
  const state=installDOM(),oldListener=Node.prototype.addEventListener,oldQuery=Node.prototype.querySelectorAll;
  Node.prototype.addEventListener=function(name,fn){if(name==='close')this.onclose=fn;};
  Node.prototype.querySelectorAll=function(selector){return selector.includes(',')?this.all().slice(1).filter(node=>selector.split(',').some(part=>node.matches(part))):oldQuery.call(this,selector);};
  return {...state,restore(){Node.prototype.addEventListener=oldListener;Node.prototype.querySelectorAll=oldQuery;state.restore();}};
}
const group=(dialog,key,id)=>dialog.all().find(node=>node.dataset?.[key]===id);
const labelled=(host,label)=>host.all().find(node=>node.getAttribute?.('aria-label')===label);
function author(dialog,draft){
  for(const row of draft.successors){const card=group(dialog,'successorId',row.paragraph_id);
    for(const [field,label]of [['function','What this unit does'],['proposition','Main point']]){const control=labelled(card,label);control.value=row.changes[field];control.oninput();}}
  for(const row of draft.attachment_assignments){const card=group(dialog,'attachmentId',row.attachment_id),choice=labelled(card,'Keep or assign this attachment');choice.value=row.disposition;choice.onchange();
    for(const id of row.successor_ids){const index=draft.successors.findIndex(row=>row.paragraph_id===id);const check=labelled(card,'New unit '+(index+1));check.checked=true;check.onchange();}}
  for(const row of draft.occurrence_assignments){const card=group(dialog,'occurrenceId',row.occurrence_id);
    for(const id of row.successor_ids){const index=draft.successors.findIndex(row=>row.paragraph_id===id);const check=labelled(card,'New unit '+(index+1));check.checked=true;check.onchange();}}
}
test('actual logical preview binds offered identities, complete reader basis and explicit attachments',()=>{
  for(const value of [wire.initial,wire.preview])assert.equal(validateLogicalPreparation(value,{project:'book',sectionId:'first',kind:'logical-split',draft:value.draft}),value);
  const fresh=createLogicalDraft(wire.initial);assert.deepEqual(fresh.successors.map(row=>row.changes),[{},{}]);
  assert.equal(wire.preview.ready,true);assert.equal(wire.preview.semantic_currentness,'NOT_REVIEWED');
  assert.equal(wire.initial.occurrence_inventory.length,3);assert.ok(wire.initial.occurrence_inventory.every(row=>row.preserved_ids.includes('first-p2')));
  assert.throws(()=>validateLogicalPreparation({...wire.initial,guards:{...wire.initial.guards,expected_reader_basis:{}}},{project:'book',sectionId:'first',kind:'logical-split'}),/reader|logical/);
  const crossed=structuredClone(wire.initial);crossed.attachment_inventory[0].allowed_successor_ids=['invented'];
  assert.throws(()=>validateLogicalPreparation(crossed,{project:'book',sectionId:'first',kind:'logical-split'}),/disposition/);
});

test('local typed fields and assignments preview through the real owner before application',async()=>{
  const state=dom(),calls=[];
  try{
    const dialog=await openLogicalRestructure({project:'book',action:wire.action,kind:'logical-split',request:async(url,payload)=>{
      calls.push({url,payload});assert.equal(payload.action,'preview-restructure');
      if(calls.length===1)return structuredClone(wire.initial);
      assert.deepEqual(payload.draft,wire.draft);return structuredClone(wire.preview);
    },opener:state.editor});
    assert.match(dialog.textContent,/Current units being retired/);assert.match(dialog.textContent,/Other planned-unit links.*preserved/);
    assert.equal(dialog.all().filter(node=>node.tag==='textarea'&&node.required).length,2);
    author(dialog,wire.draft);await findButton(dialog,'Preview logical change').click();
    assert.equal(calls.length,2);assert.equal(findButton(dialog,'Apply logical split').disabled,false);
    assert.equal(state.editor.value,'UNSAVED manuscript');await findButton(dialog,'Cancel local choices').click();
  }finally{state.restore();}
});

test('existing reader-state draft storage restores local logical choices without restoring application authority',async()=>{
  const state=dom(),cache=new Map(),storage={getItem:key=>cache.get(key),setItem:(key,value)=>cache.set(key,value),removeItem:key=>cache.delete(key)};
  try{
    const options={project:'book',action:wire.action,kind:'logical-split',storage,request:async()=>structuredClone(wire.initial),opener:state.editor};
    const original=await openLogicalRestructure(options);author(original,wire.draft);assert.equal(cache.size,1);original.close();
    const recovered=await openLogicalRestructure(options);assert.match(recovered.textContent,/Recovered local logical choices/);
    for(const row of wire.draft.successors)assert.equal(labelled(group(recovered,'successorId',row.paragraph_id),'Main point').value,row.changes.proposition);
    assert.equal(findButton(recovered,'Apply logical split').disabled,true,'Reload requires a new exact preview.');
    await findButton(recovered,'Cancel local choices').click();assert.equal(cache.size,0);
  }finally{state.restore();}
});

test('refresh and explicit adoption preserve stable authored choices and retain unmatched occurrence intent',async()=>{
  const state=dom();let refresh=false,calls=0;
  try{
    const dialog=await openLogicalRestructure({project:'book',action:wire.action,kind:'logical-split',request:async(_url,payload)=>{
      calls++;assert.equal(payload.action,'preview-restructure');return structuredClone(refresh?wire.refreshed:wire.initial);
    },opener:state.editor});
    author(dialog,wire.draft);refresh=true;await findButton(dialog,'Inspect refreshed basis').click();
    assert.equal(findButton(dialog,'Apply logical split').disabled,true);assert.ok(findButton(dialog,'Adopt refreshed basis'));
    await findButton(dialog,'Adopt refreshed basis').click();
    for(const row of wire.draft.successors){const card=group(dialog,'successorId',row.paragraph_id);assert.equal(labelled(card,'Main point').value,row.changes.proposition);}
    assert.match(dialog.textContent,/Earlier choices retained for inspection/);
    const changed=wire.refreshed.occurrence_inventory.find(row=>!wire.initial.occurrence_inventory.some(before=>before.id===row.id));assert.ok(changed);
    assert.equal(labelled(group(dialog,'occurrenceId',changed.id),'New unit 2').checked,false,'Changed occurrence is not silently retargeted.');
    assert.equal(calls,2);await findButton(dialog,'Cancel local choices').click();
  }finally{state.restore();}
});

function applicationHarness(item,{partial=false}={}){
  const calls=[],saved=[];
  return {calls,saved,options:{project:'book',action:wire.action,kind:'logical-split',onSaved:value=>saved.push(value),
    request:async(url,payload)=>{
      calls.push({url,payload});
      if(payload.action==='preview-restructure'){
        if(!payload.draft.successors)return structuredClone(item.initial);
        assert.deepEqual(payload.draft,item.preview.draft);return structuredClone(item.preview);
      }
      if(payload.action==='restructure'){
        assert.deepEqual(payload,restructureApplySubmission(item.preview,'book').payload);
        if(partial)throw Object.assign(Error('Required publication is incomplete.'),{result:structuredClone(item.result)});
        return structuredClone(item.result);
      }
      if(payload.action==='recover-restructure'){
        assert.deepEqual(payload,restructureFollowThroughSubmission(item.result.recovery_action,'book',item.result).payload);
        return structuredClone(item.recovered);
      }
      if(payload.action==='undo-restructure'){
        if(payload.intent_artifact_id===item.result.receipt.intent_artifact_id){assert.deepEqual(payload,restructureFollowThroughSubmission(item.result.undo_action,'book',item.result,'undo-restructure').payload);return structuredClone(item.inverse);}
        assert.deepEqual(payload,restructureFollowThroughSubmission(item.inverse.undo_action,'book',item.inverse,'undo-restructure').payload);return structuredClone(item.redo);
      }
      assert.fail('Unknown structural request.');
    }}};
}

test('human sourceful logical application and exact inverse use the same owner receipts and guards',async()=>{
  const state=dom(),h=applicationHarness(wire.application);
  try{
    const dialog=await openLogicalRestructure({...h.options,opener:state.editor});author(dialog,wire.application.preview.draft);
    await findButton(dialog,'Preview logical change').click();await findButton(dialog,'Apply logical split').click();
    assert.match(dialog.textContent,/Logical change and required records saved/);assert.equal(h.saved.length,1);
    assert.equal(findButton(dialog,'Apply logical split').disabled,true);assert.ok(dialog.querySelectorAll('input,textarea,select').every(node=>node.disabled));
    await findButton(dialog,'Undo this logical change').click();await findButton(dialog,'Undo this logical change').click();
    assert.equal(h.saved.length,3);assert.deepEqual(h.calls.filter(row=>row.payload.action!=='preview-restructure').map(row=>row.payload.action),['restructure','undo-restructure','undo-restructure']);
    assert.equal(state.editor.value,'UNSAVED manuscript');await findButton(dialog,'Close').click();
  }finally{state.restore();}
});

test('combine chooses active owner units explicitly and applies one newly issued successor',async()=>{
  const state=dom(),item=wire.merge,calls=[];
  try{
    const dialog=await openLogicalRestructure({project:'book',action:item.action,kind:'logical-merge',plan:item.plan,opener:state.editor,request:async(_url,payload)=>{
      calls.push(payload);
      if(payload.action==='preview-restructure'){
        if(!payload.draft.successors){assert.deepEqual(payload.draft.paragraph_ids,item.preview.draft.paragraph_ids);return structuredClone(item.initial);}
        assert.deepEqual(payload.draft,item.preview.draft);return structuredClone(item.preview);
      }
      assert.deepEqual(payload,restructureApplySubmission(item.preview,'book').payload);return structuredClone(item.result);
    }});
    assert.equal(calls.length,0,'The merge chooser cannot silently pick another unit.');
    const other=item.plan.paragraphs.items.find(row=>row.paragraph_id===item.preview.draft.paragraph_ids[1]);
    const checkbox=labelled(dialog,other.proposition);checkbox.checked=true;checkbox.onchange();
    await findButton(dialog,'Continue with selected units').click();author(dialog,item.preview.draft);
    await findButton(dialog,'Preview logical change').click();await findButton(dialog,'Apply logical combine').click();
    assert.match(dialog.textContent,/required records saved/);assert.equal(calls.filter(row=>row.action==='restructure').length,1);
    assert.ok(item.result.successor_ids.every(id=>!item.result.retired_ids.includes(id)));await findButton(dialog,'Close').click();
  }finally{state.restore();}
});

test('a saved-source partial result locks replay and recovers only its exact metadata step',async()=>{
  const state=dom(),h=applicationHarness(wire.partial,{partial:true});
  try{
    const dialog=await openLogicalRestructure({...h.options,opener:state.editor});author(dialog,wire.partial.preview.draft);
    await findButton(dialog,'Preview logical change').click();await findButton(dialog,'Apply logical split').click();
    assert.match(dialog.textContent,/Text saved.*Reader-plan recording needs attention/);assert.equal(findButton(dialog,'Apply logical split').disabled,true);
    await findButton(dialog,'Finish structural record').click();assert.match(dialog.textContent,/required records saved/);
    assert.equal(h.calls.filter(row=>row.payload.action==='restructure').length,1);assert.equal(h.calls.filter(row=>row.payload.action==='recover-restructure').length,1);assert.equal(h.saved.length,2);
    await findButton(dialog,'Close').click();
  }finally{state.restore();}
});

test('plan-only logical application settles its plan without inventing a source receipt',async()=>{
  const state=dom(),h=applicationHarness(wire.plan_only);
  try{
    const dialog=await openLogicalRestructure({...h.options,opener:state.editor});author(dialog,wire.plan_only.preview.draft);
    await findButton(dialog,'Preview logical change').click();await findButton(dialog,'Apply logical split').click();
    assert.match(dialog.textContent,/No manuscript text change was required/);assert.doesNotMatch(dialog.textContent,/Text saved\./);
    const observed=validateRestructureEffect(wire.plan_only.result,{project:'book',preview:wire.plan_only.preview});assert.equal(observed.source,null);assert.equal(observed.complete,true);
    assert.equal(h.saved.length,1);await findButton(dialog,'Close').click();
  }finally{state.restore();}
});

test('narrative-pending publication remains recoverable from its section without a successor paragraph lease',async()=>{
  const state=dom(),item=wire.narrative_partial,calls=[],host=new Node('section');state.body.append(host);
  try{
    assert.ok(item.tagged_block_leases.every(value=>value===null));assert.equal(item.top_pending.length,1);
    renderReaderState(host,{section:{id:'first',paragraph_plan:item.plan},project:'book',onRecoverStructure:(action,retained)=>calls.push(restructureFollowThroughSubmission(action,'book',retained))});
    assert.match(host.textContent,/Text saved.*Reader-plan recording needs attention/);
    await findButton(host,'Finish structural record').click();assert.equal(calls.length,1);assert.equal(calls[0].payload.intent_artifact_id,item.result.receipt.intent_artifact_id);
    assert.equal(item.recovered.complete,true);assert.equal(item.recovered.source_receipt_id,item.result.source_receipt_id);
  }finally{state.restore();}
});

test('shared mutation transport observes committed source before rejecting partial plan publication',async()=>{
  const item=wire.partial,previousFetch=globalThis.fetch,previousWindow=globalThis.window,previousEvent=globalThis.CustomEvent,events=[];
  globalThis.window={dispatchEvent:event=>events.push(event.detail)};globalThis.CustomEvent=class{constructor(type,{detail}){this.type=type;this.detail=detail;}};
  globalThis.fetch=async()=>new Response(JSON.stringify(item.result),{status:200,headers:{'Content-Type':'application/json'}});
  try{
    const payload=restructureApplySubmission(item.preview,'book').payload;
    await assert.rejects(projectRequest('/work/structure/change',payload),error=>{assert.deepEqual(error.result,item.result);return true;});
    assert.equal(events.length,1);assert.equal(events[0].state,'COMMITTED');
    const crossed=structuredClone(payload);crossed.guards.expected_selection='sha256:'+'0'.repeat(64);
    await assert.rejects(projectRequest('/work/structure/change',crossed),/could not be verified/);assert.equal(events.length,1);
  }finally{globalThis.fetch=previousFetch;globalThis.window=previousWindow;globalThis.CustomEvent=previousEvent;}
});


test('current-source reconciliation preserves historical effects and plan-only no-effect receipts',async()=>{
  for(const [name,item]of Object.entries(wire.reconciliation)){
    const submission=reconciliationSubmission(item.ready,'book');assert.equal(submission.payload.action,'reconcile-restructure');
    const ack=validateReconciliationResult(item.acknowledged,{project:'book',inspected:item.ready});
    assert.equal(ack.complete,true);assert.equal(ack.metadataReconciled,true);assert.equal(item.acknowledged.undo_action,undefined);
    if(name==='plan_only')assert.equal(ack.source,null);else assert.deepEqual(ack.source.effect,item.partial.source_effect);
    const state=dom();try{
      const host=new Node('section');state.body.append(host);renderRestructureOutcome(host,item.acknowledged,{project:'book',onRecovery:()=>assert.fail('Settled metadata must not offer Finish')});
      assert.match(host.textContent,/Reader-plan record saved/);assert.equal(findButton(host,'Finish structural record'),undefined);
    }finally{state.restore();}
  }
});

test('shifted repeated source recovery uses explicit owner-allowed passages and disables unpreviewed choices',async()=>{
  const state=dom(),item=wire.reconciliation.shifted,seen=[],host=new Node('section');state.body.append(host);
  try{
    assert.equal(item.needs_input.metadata_reconciliation.status,'NEEDS_INPUT');
    renderMetadataReconciliation(host,item.needs_input,{project:'book',onRead:()=>{},onPreview:(_value,choices)=>seen.push(choices),onReconcile:()=>assert.fail('Needs explicit preview')});
    const reconcile=findButton(host,'Reconcile reader record with inspected source');assert.equal(reconcile.disabled,true);
    for(const row of item.needs_input.metadata_reconciliation.occurrence_inventory){
      const card=group(host,'expectedOccurrenceId',row.id),select=labelled(card,'Current passage');
      select.onfocus();assert.deepEqual(select.children.slice(1).map(option=>option.value),item.needs_input.metadata_reconciliation.current_occurrence_groups.find(group=>group.id===row.allowed_current_occurrence_group_id).choice_ids);
      select.value=item.ready.metadata_reconciliation.current_occurrence_assignments.find(choice=>choice.expected_occurrence_id===row.id).current_occurrence_id;select.onchange();
    }
    await findButton(host,'Preview inspected passage mapping').click();assert.deepEqual(seen[0],item.ready.metadata_reconciliation.current_occurrence_assignments);
    assert.equal(reconcile.disabled,true);assert.ok(findButton(host,'Inspect current source at recorded coordinates'));
    const crossed=structuredClone(seen[0]);crossed[1].current_occurrence_id=crossed[0].current_occurrence_id;
    assert.throws(()=>reconciliationSubmission(item.needs_input,'book',{previewAssignments:crossed}),/distinct current passages/);
    assert.throws(()=>reconciliationSubmission(item.unprovable,'book'),/not proved/);
    const readonly=new Node('section');state.body.append(readonly);renderMetadataReconciliation(readonly,item.ready,{project:'book'});
    assert.equal(findButton(readonly,'Reconcile reader record with inspected source'),undefined);assert.match(readonly.textContent,/read-only/);
  }finally{state.restore();}
});

test('shared recovery dialog previews mapping and adopts metadata without replaying source',async()=>{
  const state=dom(),item=wire.reconciliation.shifted,calls=[],saved=[];
  try{
    const dialog=await openMetadataReconciliation({project:'book',handle:item.partial.reconciliation_read,retained:item.partial,opener:state.editor,
      request:async(url,payload)=>{calls.push({url,payload});if(!payload)return item.needs_input;
        if(payload.action==='preview-reconciliation'){assert.deepEqual(payload.current_occurrence_assignments,item.ready.metadata_reconciliation.current_occurrence_assignments);return item.ready;}
        assert.deepEqual(payload,reconciliationSubmission(item.ready,'book').payload);return item.acknowledged;},onSaved:result=>saved.push(result)});
    for(const row of item.needs_input.metadata_reconciliation.occurrence_inventory){const select=labelled(group(dialog,'expectedOccurrenceId',row.id),'Current passage');select.value=item.ready.metadata_reconciliation.current_occurrence_assignments.find(choice=>choice.expected_occurrence_id===row.id).current_occurrence_id;select.onchange();}
    await findButton(dialog,'Preview inspected passage mapping').click();assert.equal(findButton(dialog,'Reconcile reader record with inspected source').disabled,false);
    await findButton(dialog,'Reconcile reader record with inspected source').click();assert.equal(saved.length,1);assert.equal(calls.length,3);
    assert.match(dialog.textContent,/Reader record reconciled/);assert.equal(findButton(dialog,'Finish structural record'),undefined);await findButton(dialog,'Close').click();
  }finally{state.restore();}
});

test('source inspection stays contextual with exact current coordinates and file identity',async()=>{
  const state=dom(),item=wire.reconciliation.shifted,row=item.ready.metadata_reconciliation.current_occurrence_choices[0],reads=[];
  try{
    const dialog=await inspectStructuralInput(row.read,{project:'book',request:async url=>{reads.push(url);return item.source_read;},onRead:()=>assert.fail('Source inspection must not navigate away'),opener:state.editor});
    assert.equal(reads.length,1);assert.match(dialog.textContent,/Current source/);assert.ok(dialog.textContent.includes(row.line_start+' | '));assert.equal(dialog.querySelectorAll('textarea').length,0);
    await findButton(dialog,'Close').click();assert.equal(document.activeElement,state.editor);
    const wrong={...item.source_read,file:'different.tex'};
    const refused=await inspectStructuralInput(row.read,{project:'book',request:async()=>wrong});assert.match(refused.textContent,/different file/);assert.equal(refused.querySelectorAll('pre').length,0);
  }finally{state.restore();}
});

test('metadata-only recovery transport does not announce an old physical effect as a new save',async()=>{
  const previousFetch=globalThis.fetch,previousWindow=globalThis.window,previousEvent=globalThis.CustomEvent,events=[];
  globalThis.window={dispatchEvent:event=>events.push(event.detail)};globalThis.CustomEvent=class{constructor(type,{detail}){this.type=type;this.detail=detail;}};
  try{
    for(const item of [wire.reconciliation.logical,wire.reconciliation.plan_only]){
      globalThis.fetch=async()=>new Response(JSON.stringify(item.acknowledged),{status:200,headers:{'Content-Type':'application/json'}});
      const submission=reconciliationSubmission(item.ready,'book');assert.deepEqual(await projectRequest(submission.url,submission.payload),item.acknowledged);
    }
    assert.equal(events.length,0);
  }finally{globalThis.fetch=previousFetch;globalThis.window=previousWindow;globalThis.CustomEvent=previousEvent;}
});


test('exact current-source receipt GET stays read-only through both shared request layers',async()=>{
  const value=wire.reconciliation.shifted.needs_input;
  for(const request of [undefined,projectRequest]){
    const state=dom(),reader=await loadReader(),previousFetch=globalThis.fetch;let observed=value;
    globalThis.fetch=async()=>new Response(JSON.stringify(observed),{status:200,headers:{'Content-Type':'application/json'}});
    try{
      const handle=qualifiedOwnerHTTP(wire.reconciliation.shifted.partial.reconciliation_read,'book').owner;
      const dialog=await reader.openArtifact({ownerRead:handle,label:'Current recovery basis',...(request?{request}:{})});
      assert.match(dialog.textContent,/Current recovery basis/);assert.match(dialog.textContent,/Choose the current passage/);assert.doesNotMatch(dialog.textContent,/Owner reading unavailable/);
      assert.equal(findButton(dialog,'Reconcile reader record with inspected source'),undefined);dialog.close();
      observed={...value,receipt:{...value.receipt,id:'RPUB-crossed'}};
      const refused=await reader.openArtifact({ownerRead:handle,label:'Current recovery basis',...(request?{request}:{})});
      assert.match(refused.textContent,/different retained operation/);assert.doesNotMatch(refused.textContent,/Choose the current passage/);refused.close();
    }finally{globalThis.fetch=previousFetch;reader.destroy();state.restore();}
  }
});

test('recovery mapping refresh blocks old authority when the inspected source really changes',async()=>{
  const state=dom(),item=wire.reconciliation.shifted;let submissions=0;
  try{
    const dialog=await openMetadataReconciliation({project:'book',handle:item.partial.reconciliation_read,retained:item.partial,
      request:async(_url,payload)=>{if(!payload)return item.needs_input;submissions++;assert.equal(payload.action,'preview-reconciliation');return item.unprovable;}});
    for(const row of item.needs_input.metadata_reconciliation.occurrence_inventory){const select=labelled(group(dialog,'expectedOccurrenceId',row.id),'Current passage');select.value=item.ready.metadata_reconciliation.current_occurrence_assignments.find(choice=>choice.expected_occurrence_id===row.id).current_occurrence_id;select.onchange();}
    await findButton(dialog,'Preview inspected passage mapping').click();assert.match(dialog.textContent,/changed during inspection/);
    assert.equal(findButton(dialog,'Reconcile reader record with inspected source').disabled,true);
    await findButton(dialog,'Adopt refreshed recovery basis').click();assert.match(dialog.textContent,/cannot be proved/);
    assert.equal(findButton(dialog,'Reconcile reader record with inspected source').disabled,true);assert.equal(submissions,1);
    await findButton(dialog,'Close').click();
  }finally{state.restore();}
});


test('large repeated recovery mounts linear options and expands only one owner group at a time',()=>{
  const state=dom(),item=wire.large_reconciliation.inspected,view=item.metadata_reconciliation,host=new Node('section');state.body.append(host);
  try{
    assert.equal(view.status,'NEEDS_INPUT');assert.equal(view.occurrence_inventory.length,120);
    assert.equal(view.current_occurrence_groups.length,1);assert.equal(view.current_occurrence_groups[0].choice_ids.length,120);
    assert.ok(view.occurrence_inventory.every(row=>row.allowed_current_occurrence_group_id===view.current_occurrence_groups[0].id&&!('allowed_current_occurrence_ids'in row)));
    renderMetadataReconciliation(host,item,{project:'book',onPreview:()=>{},onReconcile:()=>{}});
    const selects=host.querySelectorAll('select');assert.equal(selects.length,120);assert.equal(host.querySelectorAll('option').length,120);
    selects[0].onfocus();assert.equal(selects[0].children.length,121);assert.equal(host.querySelectorAll('option').length,240);
    selects[0].value=view.current_occurrence_groups[0].choice_ids[0];selects[0].onchange();
    selects[1].onpointerdown();assert.equal(selects[0].children.length,2);assert.equal(selects[0].value,view.current_occurrence_groups[0].choice_ids[0]);
    assert.equal(selects[1].children.length,121);assert.equal(host.querySelectorAll('option').length,241);
    assert.equal(findButton(host,'Reconcile reader record with inspected source').disabled,true);
    const crossed=structuredClone(item);crossed.metadata_reconciliation.current_occurrence_groups[0].file='different.tex';
    assert.throws(()=>renderMetadataReconciliation(new Node('section'),crossed,{project:'book',onPreview:()=>{}}),/eligibility group/);
  }finally{state.restore();}
});


test('saved structural operation remains discoverable once with exact item-level lineage reads',async()=>{
  const state=dom(),item=wire.discovery,host=new Node('section'),inspections=[],reads=[];state.body.append(host);
  try{
    assert.equal(item.plan.latest_restructure.currentness.status,'NOT_REOBSERVED');assert.equal(item.plan.latest_restructure.source_effect,undefined);assert.equal(item.plan.latest_restructure.guards,undefined);
    renderReaderState(host,{project:'book',section:{id:'first',paragraph_plan:item.plan},onInspectLatestStructure:row=>inspections.push(row),onRead:handle=>reads.push(handle)});
    assert.equal(host.all().filter(node=>node.tag==='button'&&node.textContent==='Inspect latest structural operation').length,1);
    await findButton(host,'Inspect latest structural operation').click();assert.deepEqual(inspections,[item.plan.latest_restructure]);
    await findButton(host,'Inspect recorded restructuring decision').click();assert.deepEqual(reads,[item.plan.paragraphs.items[0].lineage.items[0].read]);
    assert.equal(findButton(host,'Undo this structural operation'),undefined,'summary carries no mutation lease');
  }finally{state.restore();}
});

test('saved structural operation lazily rechecks exact Undo and Redo through retained receipts',async()=>{
  const state=dom(),item=wire.discovery,calls=[],saved=[];let post=0;
  try{
    const dialog=await openRecordedRestructure({project:'book',retained:item.plan.latest_restructure,opener:state.editor,
      request:async(url,payload)=>{calls.push({url,payload});if(!payload)return post===0?item.saved:post===1?item.inverse:item.redo;
        assert.deepEqual(payload,restructureFollowThroughSubmission(post===0?item.saved.undo_action:item.inverse.undo_action,'book',post===0?item.saved:item.inverse,'undo-restructure').payload);
        return ++post===1?wire.application.inverse:wire.application.redo;},onSaved:result=>saved.push(result)});
    assert.equal(calls.length,1);assert.equal(calls[0].payload,undefined);
    await findButton(dialog,'Undo this structural operation').click();assert.equal(saved.length,1);assert.ok(findButton(dialog,'Redo this structural operation'));
    await findButton(dialog,'Redo this structural operation').click();assert.equal(saved.length,2);assert.ok(findButton(dialog,'Undo this structural operation'));
    assert.equal(calls.filter(row=>row.payload).length,2);assert.equal(calls.length,5);await findButton(dialog,'Close').click();assert.equal(document.activeElement,state.editor);
  }finally{state.restore();}
});

test('saved structural operation with a changed basis is inspectable without an inverse or false Finish',async()=>{
  const state=dom(),item=wire.discovery,calls=[];
  try{
    const dialog=await openRecordedRestructure({project:'book',retained:item.plan.latest_restructure,request:async(url,payload)=>{calls.push({url,payload});return item.changed;}});
    assert.match(dialog.textContent,/Reader metadata or its declared plan changed/);assert.equal(findButton(dialog,'Undo this structural operation'),undefined);assert.equal(findButton(dialog,'Finish structural record'),undefined);
    assert.equal(calls.length,1);assert.equal(calls[0].payload,undefined);await findButton(dialog,'Close').click();
  }finally{state.restore();}
});

test('saved structural inverse never revives old controls after an unknown acknowledgement or secondary read failure',async()=>{
  for(const physicalAck of [false,true]){
    const state=dom(),item=wire.discovery,saved=[];let writes=0;
    try{
      const dialog=await openRecordedRestructure({project:'book',retained:item.plan.latest_restructure,
        request:async(_url,payload)=>{if(!payload&&writes===0)return item.saved;if(payload){writes++;if(physicalAck)return wire.application.inverse;}throw Error('Simulated receipt connection outage');},onSaved:result=>saved.push(result)});
      await findButton(dialog,'Undo this structural operation').click();assert.equal(writes,1);assert.equal(saved.length,physicalAck?1:0);
      assert.equal(findButton(dialog,'Undo this structural operation'),undefined);assert.equal(findButton(dialog,'Redo this structural operation'),undefined);assert.match(dialog.textContent,/outage.*Inspect the latest saved operation/);
      await findButton(dialog,'Close').click();
    }finally{state.restore();}
  }
});


test('retained disposition summary shows exact qualification and factual counts without asserting review',()=>{
  const state=dom(),value=wire.discovery.saved,host=new Node('section');state.body.append(host);
  try{
    renderRestructureOutcome(host,value,{project:'book'});
    assert.match(host.textContent,/Recorded attachment choices/);assert.match(host.textContent,/1 attachments · 3 saved passages/);
    assert.ok(host.textContent.includes('Qualification: '+value.disposition_summary.qualifications[0].value));
    assert.match(host.textContent,/1 assigned; 0 kept with retired units; 0 retained for scoped review/);
    assert.match(host.textContent,/do not assert scientific acceptance/);assert.match(host.textContent,/Earlier reviews remain historical/);
    assert.equal(host.querySelectorAll('code').length,1);assert.equal(host.querySelectorAll('details').some(node=>node.open),false);
  }finally{state.restore();}
});

test('bounded retained disposition summary declares omitted exact values and never hides saved receipts',()=>{
  const state=dom(),host=new Node('section'),value=wire.summary_omitted;state.body.append(host);
  try{
    assert.equal(value.disposition_summary.coverage.omitted_qualification_values,1);assert.equal(value.disposition_summary.qualifications[0].value,undefined);
    renderRestructureOutcome(host,value,{project:'book'});assert.match(host.textContent,/Qualification text omitted/);assert.match(host.textContent,/1 qualification texts/);
    assert.match(host.textContent,/Text saved.*Reader-plan record saved/);assert.doesNotMatch(host.textContent,/Exact long qualification/);
    const crossed=structuredClone(wire.discovery.saved);crossed.disposition_summary.basis.receipt_id='RPUB-crossed';host.replaceChildren();
    renderRestructureOutcome(host,crossed,{project:'book',onInverse:()=>{}});
    assert.match(host.textContent,/Compact attachment summary unavailable/);assert.match(host.textContent,/Text saved.*Reader-plan record saved/);assert.ok(findButton(host,'Undo this structural operation'));
  }finally{state.restore();}
});


test('recorded operation Reader callback follows its own Undo and Redo refreshes while external navigation wins',async()=>{
  const state=dom(),source=await readFile(new URL('../src/laplace/web/static_shared/workspace-spine.mjs',import.meta.url),'utf8');
  try{
    const start=source.indexOf('onInspectLatestStructure:readOnly?null:'),end=source.indexOf(',\n      onRecoverStructure:',start);
    assert.ok(start>=0&&end>start);const callback=source.slice(start+'onInspectLatestStructure:'.length,end),refreshes=[],saved=[];
    const make=new Function('bindings',`const {section,project,request,onRead,onChanged,detailHandle,openRecordedRestructure}=bindings;let version=0,selected=section,alive=true;const readOnly=false;const selectSection=async(id,handle)=>{version++;selected={id};bindings.refreshes.push({id,handle});};const launch=${callback};return {launch,navigate(){version++;selected={id:'another-section'};}};`);
    const controller=make({section:{id:'first'},project:'book',request:()=>{},onRead:()=>{},onChanged:result=>saved.push(result),detailHandle:()=>wire.discovery.plan.latest_restructure.read_handle,openRecordedRestructure:options=>options,refreshes});
    const options=controller.launch(wire.discovery.plan.latest_restructure);
    await options.onSaved(wire.application.inverse);await options.onSaved(wire.application.redo);assert.equal(refreshes.length,2);
    controller.navigate();await options.onSaved(wire.application.inverse);assert.equal(refreshes.length,2);assert.equal(saved.length,3);
  }finally{state.restore();}
});


test('carried attachment cards show mixed predecessor choices and unresolved scope without adopting old decisions',async()=>{
  for(const [name,item]of Object.entries(wire.carried_witnesses)){
    const state=dom();
    try{
      const dialog=await openLogicalRestructure({project:'book',kind:'logical-merge',action:item.action,plan:{paragraphs:{items:item.initial.predecessors.map(row=>row.values)}},storage:null,
        request:async(_url,payload)=>{assert.deepEqual(payload.draft.paragraph_ids,item.initial.draft.paragraph_ids);return item.initial;},onRead:()=>{}});
      await findButton(dialog,'Continue with selected units').click();
      const rows=item.initial.attachment_inventory.filter(row=>['note','protection'].includes(row.kind));assert.equal(rows.length,2);
      for(const row of rows){const card=group(dialog,'attachmentId',row.id);
        assert.match(card.textContent,name==='mixed'?/Earlier choices differ/:/Previously retained for scoped review/);assert.match(card.textContent,/scope remains unresolved/);
        assert.equal(labelled(card,'Keep or assign this attachment').value,'','prior disposition is evidence, never a new decision');
        const details=card.querySelector('details');assert.ok(details);assert.equal(!!details.open,false);assert.match(details.textContent,/Assigned|Retained for scoped review/);
        for(const witness of row.prior_dispositions){assert.ok(details.textContent.includes(witness.paragraph_id));assert.ok(details.textContent.includes(witness.intent_artifact_id));}
      }
      assert.equal(findButton(dialog,'Apply logical combine').disabled,true);await findButton(dialog,'Cancel local choices').click();
    }finally{state.restore();}
  }
});
