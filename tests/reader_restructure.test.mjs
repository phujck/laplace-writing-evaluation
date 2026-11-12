import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {restructurePreviewSubmission, validateRestructurePreview, restructureApplySubmission,restructureOutcome,validateRestructureEffect,findRestructureAnchor,restructureFollowThroughSubmission,renderRestructureOutcome}
  from '../src/laplace/web/static_shared/reader-restructure.mjs';
import {installDOM,Node,findButton,loadReader} from './helpers/evidence_reader_harness.mjs';
import {restructureWire} from './helpers/reader_restructure_fixture.mjs';
import {Store} from '../src/laplace/web/static_shared/store.mjs';
import {sourceEffectFromError} from '../src/laplace/web/static_shared/source-effect.mjs';
import {projectRequest} from '../src/laplace/web/static_shared/workspace-session.mjs';
import {walkSource as readWalkSource,walkDeclarations} from './helpers/walk_source.mjs';

test('actual structural owner preview and application copy the same complete source and plan guards', () => {
  const {preview,draft,preview_action,apply_payload} = restructureWire;
  assert.equal(validateRestructurePreview(preview,{project:'book',kind:'presentation-split',draft}),preview);
  const prepared = restructurePreviewSubmission(preview_action,'book','presentation-split',draft);
  assert.equal(prepared.url,'/work/structure/change');
  assert.equal(prepared.payload.action,'preview-restructure');
  assert.deepEqual(prepared.payload.draft,draft);
  assert.deepEqual(restructureApplySubmission(preview,'book').payload,apply_payload);
  assert.deepEqual(preview.occurrence_mapping.after.map(row=>row.spec_ids),[['first-p1'],['first-p1']]);
});

test('a crossed structural token, source guard or authored source draft cannot become an apply request', () => {
  const {preview,draft} = restructureWire;
  const token = structuredClone(preview);
  token.apply_action.payload.restructure_token='sha256:'+'0'.repeat(64);
  assert.throws(()=>restructureApplySubmission(token,'book'),/comparison you inspected/);
  const source = structuredClone(preview);
  source.apply_action.payload.guards.source_guards[Object.keys(source.guards.source_guards)[0]]='sha256:'+'0'.repeat(64);
  assert.throws(()=>restructureApplySubmission(source,'book'),/comparison you inspected/);
  assert.throws(()=>validateRestructurePreview(preview,{project:'other',draft}),/exact source and plan/);
  assert.throws(()=>validateRestructurePreview(preview,{project:'book',draft:{...draft,parts:['Different','text']}}),/different authored/);
});


test('real committed source with partial plan publication settles text and recovers only the retained metadata step',async()=>{
  const {complete,partial,recovered}=restructureWire;
  assert.equal(restructureOutcome(complete,{project:'book'}).complete,true);
  const pending=restructureOutcome(partial,{project:'book'});
  assert.equal(pending.sourceCommitted,true);assert.equal(pending.complete,false);assert.equal(pending.plan.acknowledged,false);
  const submission=restructureFollowThroughSubmission(partial.recovery_action,'book',partial);
  assert.deepEqual(submission.payload,{...partial.recovery_action.payload,project:'book'});
  assert.equal(restructureOutcome(recovered,{project:'book'}).complete,true);
  assert.equal(recovered.source_receipt_id,partial.source_receipt_id);
  const dom=installDOM(),host=new Node('section'),calls=[];dom.body.append(host);
  try{
    renderRestructureOutcome(host,partial,{project:'book',onRecovery:(...args)=>calls.push(args)});
    assert.match(host.textContent,/Text saved.*Reader-plan recording needs attention/);
    await findButton(host,'Finish structural record').click();assert.deepEqual(calls,[[partial.recovery_action,partial]]);
    assert.equal(dom.editor.value,'UNSAVED manuscript');
  }finally{dom.restore();}
});

test('actual legacy-feedback partial receipt renders through contextual default and workspace GET transports',async()=>{
  const value=restructureWire.legacy_partial_read;
  for(const useWorkspace of [false,true]){
    const dom=installDOM(),reader=await loadReader(),originalFetch=globalThis.fetch,calls=[];let observed=value;
    globalThis.fetch=async(url,init)=>{calls.push({url,init});return new Response(JSON.stringify(observed),{status:200,headers:{'Content-Type':'application/json'}});};
    try{
      const dialog=await reader.openArtifact({ownerRead:value.read_handle,label:'Paragraph structure',...(useWorkspace?{request:projectRequest}:{})});
      assert.equal(calls.length,1);assert.equal(calls[0].url,value.read_handle.http.url);
      assert.ok(!calls[0].init||calls[0].init.method==='GET');
      assert.match(dialog.textContent,/Text saved.*Reader-plan recording needs attention/);
      assert.match(dialog.textContent,/Recording reason: 'record'/);assert.match(dialog.textContent,/author protection; provenance publication/);
      assert.doesNotMatch(dialog.textContent,/Owner reading unavailable/);
      assert.equal(findButton(dialog,'Finish structural record'),undefined,'Contextual receipt inspection remains read-only.');
      assert.ok(value.recovery_action);assert.equal(dom.editor.value,'UNSAVED manuscript');dialog.close();
      for(const crossed of [{...value,project:'other'},{...value,receipt:{...value.receipt,id:'RPUB-other'}},{...value,schema_version:'untyped-error'}]){
        observed=crossed;
        const refused=await reader.openArtifact({ownerRead:value.read_handle,label:'Paragraph structure',...(useWorkspace?{request:projectRequest}:{})});
        assert.match(refused.textContent,/Owner reading unavailable/);assert.doesNotMatch(refused.textContent,/Text saved/);refused.close();
      }
      assert.ok(calls.every(row=>!row.init||row.init.method==='GET'));
    }finally{globalThis.fetch=originalFetch;reader.destroy();dom.restore();}
  }
});

test('guarded Undo and recovery retain the exact intent and receipt, without a generic source rewrite',()=>{
  const {complete,partial}=restructureWire;
  const inverse=restructureFollowThroughSubmission(complete.undo_action,'book',complete,'undo-restructure');
  assert.equal(inverse.url,'/work/structure/change');assert.equal(inverse.payload.action,'undo-restructure');assert.equal(inverse.payload.intent_artifact_id,complete.receipt.intent_artifact_id);
  const crossed=structuredClone(partial.recovery_action);crossed.payload.receipt_id='RPUB-other';assert.throws(()=>restructureFollowThroughSubmission(crossed,'book',partial),/exact action/);
  assert.throws(()=>restructureFollowThroughSubmission(complete.undo_action,'other',complete,'undo-restructure'),/exact retained/);
});


const walkSource=readWalkSource();
function productionFunction(start,end){const at=walkSource.indexOf(start);assert.ok(at>=0);return walkSource.slice(at,walkSource.indexOf(end,at));}
test('production structural adapter crosses the actual Store writing-header gate and retains typed failure evidence',async()=>{
  const originalFetch=globalThis.fetch,requests=[];
  const store=new Store();
  const code=walkDeclarations('structuralRequest');
  const request=new Function('store',`${code};return structuralRequest;`)(store);
  let partial=false,topEffect=false;
  globalThis.fetch=async(url,init)=>{
    requests.push({url,init});
    if(init.headers['X-Laplace-Writing']!=='1')return new Response(JSON.stringify({error:'Missing writing-client header.'}),{status:403});
    const failed=topEffect?{error:'Retained physical effect',source_effect:restructureWire.partial.source_effect,recovery:restructureWire.partial.recovery_action,result:{reason:'METADATA_INCOMPLETE'}}
      :{error:'Retained partial outcome',reason:'PUBLICATION_INCOMPLETE',recovery:restructureWire.partial.recovery_action,result:restructureWire.partial};
    return new Response(JSON.stringify(partial?failed:restructureWire.preview),{status:partial?422:200});
  };
  try{
    const submission=restructurePreviewSubmission(restructureWire.preview_action,'book','presentation-split',restructureWire.draft);
    assert.deepEqual(await request(submission),restructureWire.preview);
    partial=true;assert.deepEqual(await request(submission),restructureWire.partial);
    await assert.rejects(store.fetchJSON(submission.url,{method:'POST',inject:[],body:submission.payload}),error=>{
      assert.equal(error.reason,'PUBLICATION_INCOMPLETE');assert.deepEqual(error.recovery,restructureWire.partial.recovery_action);
      assert.deepEqual(error.body.result,restructureWire.partial);assert.deepEqual(error.result,restructureWire.partial);
      assert.equal(sourceEffectFromError(error,{project:'book'}).state,'COMMITTED');return true;
    });
    topEffect=true;
    await assert.rejects(store.fetchJSON(submission.url,{method:'POST',inject:[],body:submission.payload}),error=>{
      assert.equal(error.reason,'METADATA_INCOMPLETE');assert.equal(error.result,error.body);
      assert.deepEqual(error.recovery,restructureWire.partial.recovery_action);assert.equal(sourceEffectFromError(error,{project:'book'}).state,'COMMITTED');return true;
    });
    assert.equal(requests.length,4);assert.ok(requests.every(row=>row.init.headers['X-Laplace-Writing']==='1'));
    assert.deepEqual(JSON.parse(requests[0].init.body),submission.payload);
  }finally{globalThis.fetch=originalFetch;}
});

test('global Save refusal summary retains the specific structural owner or transport reason',async()=>{
  const block={id:'paragraph',bodyEl:{text:'retained draft'}},E={blockId:block.id,dirty:true},P=new Map(),message='Missing writing-client header.';
  const bindings={E,P,F:{},blockById:new Map([[block.id,block]]),pendingPresentationSplits:new Map([[block.id,{refusal:{message}}]]),
    srcOf:()=>({file:'chapter.tex',lineStart:7,lineEnd:7}),commitEdit:async()=>null,hostText:host=>host.text,INFLIGHT:new Set(),QUEUE:{why:''},NOT_SAVED:{why:''},
    parkEdit:()=>{P.set(block.id,{text:'retained draft',pristine:'saved text'});E.blockId='';E.dirty=false;},paintParked(){},C:{},renderBand(){},emit(){}};
  const code=walkDeclarations('commitAll');
  const commit=new Function('bindings',`const {${Object.keys(bindings).join(',')}}=bindings;${code};return commitAll;`)(bindings);
  const result=await commit();assert.equal(result.refused.length,1);assert.equal(result.refused[0].reason,message);
  assert.match(result.message,/Not saved: 1 edit/);assert.ok(result.message.includes(message));assert.equal(result.remaining.length,1);
});
const presentationCode=productionFunction('function taggedParagraph(', 'async function structuralRequest(')+productionFunction('async function savePresentationChange(', 'async function commitPresentationSplit(');
function presentationFixture({partial=false,refuse=false}={}){
  const block=structuredClone(restructureWire.block),preview=partial?restructureWire.partial_preview:restructureWire.preview,result=partial?restructureWire.partial:restructureWire.complete;
  // The partial publication fixture follows an earlier inverse, so its refreshed
  // owner lease accompanies that exact new source/metadata basis.
  if(partial){block.restructure_preview.payload.source_guards=structuredClone(preview.guards.source_guards);block.restructure_preview.payload.expected_selection=preview.guards.expected_selection;}
  const requests=[],recorded=[],shown=[],leases=[];
  const bindings={S:{corpus:'book'},E:{blockId:''},D:{sourceObservation:{source_observation:{selection_identity:preview.guards.expected_selection}}},structuralSourceHolds:new Map(),
    readManuscriptSource:async()=>{throw Error('The emitted exact lease must avoid another full file read.');},srcOf:row=>({file:row.src.file,lineStart:row.src.line_start,lineEnd:row.src.line_end}),
    restructurePreviewSubmission,validateRestructurePreview,restructureApplySubmission,restructureOutcome,validateRestructureEffect,
    structuralRequest:async request=>{requests.push(request);if(refuse)throw Error('CHANGED_INPUT: source moved');return request.payload.action==='preview-restructure'?preview:result;},recordStructuralOutcome:(...args)=>leases.push(args),rememberStructuralChange:value=>recorded.push(value),showStructuralOutcome:value=>shown.push(value)};
  const run=new Function('bindings',`const {${Object.keys(bindings).join(',')}}=bindings;${presentationCode};return savePresentationChange;`)(bindings);
  return {run,block,preview,result,requests,recorded,shown,leases};
}

test('actual canvas bridge uses owner lease and typed structural request, including committed-source/partial-plan settlement',async()=>{
  for(const partial of [false,true]){
    const fixture=presentationFixture({partial});const draft=fixture.preview.draft;
    const observed=await fixture.run('presentation-split',[fixture.block],draft.source_edits[0].after,draft.parts);
    assert.equal(fixture.requests.length,2);assert.equal(fixture.requests[0].payload.action,'preview-restructure');assert.deepEqual(fixture.requests[0].payload.draft,draft);
    assert.deepEqual(fixture.requests[1].payload,{...fixture.preview.apply_action.payload,project:'book',draft});
    assert.equal(observed.outcome.sourceCommitted,true);assert.equal(observed.outcome.complete,!partial);assert.deepEqual(fixture.recorded,[fixture.result]);assert.deepEqual(fixture.shown,[fixture.result]);
  }
});

test('a refused structural preview cannot fall through to a source apply or create local successful history',async()=>{
  const fixture=presentationFixture({refuse:true}),draft=fixture.preview.draft;
  await assert.rejects(fixture.run('presentation-split',[fixture.block],draft.source_edits[0].after,draft.parts),/CHANGED_INPUT/);
  assert.equal(fixture.requests.length,1);assert.equal(fixture.recorded.length,0);assert.equal(fixture.shown.length,0);
});

const structuralHistoryCode=productionFunction('function structuralHistoryResult(', 'const structuralOutcomeControllers');
const undoCode=walkDeclarations('undoEditorChange');
function structuralUndoFixture(result){
  const history={undo:[],redo:[],busy:false,pending:[]},requests=[],events=[],shown=[];
  const bindings={savedEditHistory:history,restoreEditHistory:()=>true,persistEditHistory(){},E:{dirty:false},P:new Map(),S:{corpus:'book'},D:{pending_restructures:[result]},
    restructureFollowThroughSubmission,validateRestructureEffect,recordStructuralOutcome(){},showStructuralOutcome:value=>shown.push(value),
    structuralRequest:async request=>{requests.push(request);return restructureWire.undone;},window:{walk:{refresh:async()=>true}},emit:(...args)=>events.push(args)};
  const run=new Function('bindings',`const {${Object.keys(bindings).join(',')}}=bindings;${structuralHistoryCode}${undoCode};return {rememberStructuralChange,undoEditorChange};`)(bindings);
  run.rememberStructuralChange(result);return {run,history,requests,events,shown};
}

test('actual editor Undo cursor stores only the owner handle and invokes the guarded structural inverse',async()=>{
  const fixture=structuralUndoFixture(restructureWire.complete);
  const stored=JSON.stringify(fixture.history.undo[0]);assert.doesNotMatch(stored,/First sentence|Second sentence|provenance_before|source_changes/);
  await fixture.run.undoEditorChange();assert.equal(fixture.requests.length,1);
  assert.deepEqual(fixture.requests[0].payload,{...restructureWire.complete.undo_action.payload,project:'book'});
  assert.equal(fixture.history.undo.length,0);assert.equal(fixture.history.redo.length,1);assert.ok(fixture.history.redo[0].redo.action);
  assert.ok(fixture.events.some(([name,value])=>name==='bank'&&value.shape==='paragraph-restructure'));
});

test('a source-committed partial structural record stops Undo before any generic source replay',async()=>{
  const fixture=structuralUndoFixture(restructureWire.partial);
  await fixture.run.undoEditorChange();assert.equal(fixture.requests.length,0);assert.equal(fixture.history.undo.length,1);assert.equal(fixture.history.redo.length,0);
  assert.deepEqual(fixture.shown,[restructureWire.partial]);assert.match(fixture.events.at(-1)[1].text,/Finish or inspect.*No text change was repeated/);
});


test('contextual structural cue needs the current source lease and complete A versus A+B occurrence identity',()=>{
  const {complete,after_blocks,block}=restructureWire;
  assert.equal(findRestructureAnchor(complete,[block]),null,'The old preimage cannot place the current effect.');
  const anchor=findRestructureAnchor(complete,after_blocks);assert.ok(anchor);assert.deepEqual(anchor.spec_ids,['first-p1']);assert.notDeepEqual(anchor.spec_ids,['first-p1','first-p2']);
  const crossed=structuredClone(after_blocks);for(const row of crossed)if(row.restructure_preview)row.restructure_preview.payload.expected_selection='sha256:'+'0'.repeat(64);
  assert.equal(findRestructureAnchor(complete,crossed),null);
  const bounded=structuredClone(complete);delete bounded.remapped_occurrences;
  assert.ok(findRestructureAnchor(bounded,after_blocks),'Fresh pending metadata can use the exact owner source scope without mapping hydration.');
  bounded.source_scope={...bounded.source_scope,line_start:999,after_line_end:1000};
  assert.equal(findRestructureAnchor(bounded,after_blocks),null);
});

test('pasted or in-flight paragraph breaks retain the structural route, including refusal on autosave',async()=>{
  const pendingPresentationSplits=new Map(),block={id:'paragraph',tex:'First sentence.',bodyEl:{}},E={blockId:block.id,pristine:block.tex,committing:false};
  const bindings={E,INFLIGHT:new Set(),QUEUE:{why:''},RELOAD_INFLIGHT:null,blockById:new Map([[block.id,block]]),structuralSourceHolds:new Map(),pendingPresentationSplits,
    hostText:()=> 'First sentence.\n\nSecond sentence.',taggedParagraph:()=>true,clearEdit(){},C:{actor:''},showCard(){},askActor(){}};
  const code=productionFunction('async function commitEdit(', '  let p = 0;');
  const commit=new Function('bindings',`const {${Object.keys(bindings).join(',')}}=bindings;${code}};return commitEdit;`)(bindings);
  await commit('paste');
  assert.equal(pendingPresentationSplits.get(block.id).split.tail,'Second sentence.');
  pendingPresentationSplits.get(block.id).retryRequired=true;
  await commit('autosave');
  assert.equal(pendingPresentationSplits.get(block.id).retryRequired,true,'Autosave must not reset a refused structural intent.');
});

test('actual three-part and twelve-part owner splits preserve every full ID set and have exact inverse',()=>{
  for(const {draft,preview,complete,undone,empty_refusal} of restructureWire.multipart){
    validateRestructurePreview(preview,{project:'book',kind:'presentation-split',draft});
    assert.deepEqual(restructureApplySubmission(preview,'book').payload.draft.parts,draft.parts);
    assert.equal(complete.remapped_occurrences.length,draft.parts.length);
    assert.ok(complete.remapped_occurrences.every(row=>JSON.stringify(row.spec_ids)===JSON.stringify(draft.paragraph_ids)));
    assert.equal(restructureOutcome(complete,{project:'book'}).complete,true);
    assert.equal(restructureOutcome(undone,{project:'book'}).complete,true);
    assert.match(empty_refusal,/empty|nonempty|type into|unfinished/i);
  }
});

test('production split commit submits all pasted parts once and retains the exact result for caret transfer',async()=>{
  const code=productionFunction('async function commitPresentationSplit(', '/** The typed edit, banked.');
  for(const item of restructureWire.multipart){
    const edit=item.draft.source_edits[0],block={id:'paragraph',tex:edit.before,bodyEl:{}},split={focusPart:item.draft.parts.length-1},requests=[],focus=[];
    const bindings={ownerView:v=>v,srcOf:()=>({lineStart:edit.line_start}),savePresentationChange:async(...args)=>{requests.push(args);return {result:item.complete,outcome:restructureOutcome(item.complete,{project:'book'})};},
      pendingPresentationSplits:new Map(),continuedEdit:()=>null,hostText:()=>'',E:{blockId:block.id},clearEdit(){},P:new Map(),reloadBlock:async()=>({ok:true}),focusSplitParagraph:async(...args)=>focus.push(args),showStructuralOutcome(){},emit(){}};
    const commit=new Function('bindings',`const {${Object.keys(bindings).join(',')}}=bindings;${code};return commitPresentationSplit;`)(bindings);
    const result=await commit(block,edit,split,'submitted','pristine');
    assert.equal(result.applied,true);assert.equal(requests.length,1);assert.deepEqual(requests[0][3],item.draft.parts);
    assert.equal(focus[0][1].structuralResult,item.complete);
  }
});

test('production n-part focus selects the witnessed final part and transfers the in-flight draft',async()=>{
  const code=productionFunction('async function focusSplitParagraph(', 'function transferParagraphDraft(');
  for(const item of restructureWire.multipart){
    const blocks=structuredClone(item.after_blocks);for(const block of blocks)block.bodyEl={};
    const calls=[],draft={textContent:'typing during request'},focusPart=item.draft.parts.length-1;
    const bindings={srcOf:row=>({file:row.src.file,lineStart:row.src.line_start}),S:{blocks},findRestructureAnchor,transferParagraphDraft:(...args)=>calls.push(args)};
    const focus=new Function('bindings',`const {${Object.keys(bindings).join(',')}}=bindings;${code};return focusSplitParagraph;`)(bindings);
    await focus(blocks[0],{structuralResult:item.complete,focusPart,liveDraft:draft,draftPristine:'saved tail'});
    assert.equal(calls.length,1);assert.equal(calls[0][0].tex,item.draft.parts[focusPart]);assert.equal(calls[0][1],draft);assert.equal(calls[0][2],'saved tail');
  }
});
