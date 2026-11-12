// WALK EDIT HISTORY (S2 F6). Purpose: the one bounded Undo/Redo store of this walk's own saves and
// of external applications it was told about, its local persistence, and the structural outcome
// record of presentation splits. Owns: savedEditHistory, editorPersistence, the structural outcome
// maps. Public contract: restoreEditHistory/persistEditHistory, rememberExternalChange/Transaction/
// Application, undoEditorChange (undo and redo on guarded current source), rememberStructuralChange,
// recordStructuralOutcome/showStructuralOutcome, storageFailure/storageRecovered. Storage:
// localStorage laplace:editor-history:<corpus>; failures are disclosed through persistence-status.
import store from "/shared/store.mjs";
import {
  findRestructureAnchor, openMetadataReconciliation, renderRestructureOutcome,
  restructureFollowThroughSubmission, validateRestructureEffect
} from "/shared/reader-restructure.mjs";
import {ownerHumanTarget} from "/shared/writing-owner-read.mjs";
import {captureApplicationChange, captureSourceChange, historySpan} from "/shared/manuscript-editing.mjs";
import {docEl, el, emit} from './walk-base.mjs';
import {D, expectedOf} from './walk-document.mjs';
import {S, scheduleRemeasure} from './walk-position.mjs';
import {readEditorSource, retrySaveOnce, sourceEffectRequest, sourceRequest} from './walk-source-client.mjs';
import {asChrome} from './walk-blocks.mjs';
import {blockAtSpan, srcOf} from './walk-selection.mjs';
import {E, P} from './walk-drafts.mjs';
import {appliedOf} from './walk-bank.mjs';
import {commitAll, editableBlock, structuralRequest} from './walk-editing.mjs';
import {caretRange} from './walk-card.mjs';
import {clearObjectSelection, findObject, selectObject} from './walk-paragraph-ops.mjs';
import {authorChangeRecords} from './walk-review.mjs';

const savedEditHistory = {undo:[], redo:[], busy:false,pending:[],external:new Set()};
let editHistoryLoadedFor=null;
const editorPersistence={history:'',drafts:''};
function storageFailure(domain,error,action='stored'){const message=(
  domain==='history'?'Local Undo history':'Local manuscript drafts')+' could not be '+action+'. Keep this tab open. '+(error?.message||String(error));
  if(editorPersistence[domain]!==message){editorPersistence[domain]=message;emit('persistence-status',{...editorPersistence});}return false;}
function storageRecovered(domain){if(editorPersistence[domain]){editorPersistence[domain]='';emit('persistence-status',{...editorPersistence});}}
function historyKey(){return 'laplace:editor-history:'+S.corpus;}
function persistEditHistory(){if(editHistoryLoadedFor!==S.corpus)return false;try{localStorage.setItem(historyKey(),JSON.stringify({
  undo:savedEditHistory.undo.slice(-40),redo:savedEditHistory.redo.slice(-40),external:[...savedEditHistory.external].slice(-400)}));storageRecovered(
  'history');return true;}catch(error){return storageFailure('history',error);}}
function restoreEditHistory(){
  if(editHistoryLoadedFor===S.corpus)return true;
  try{const h=JSON.parse(localStorage.getItem(historyKey())||'{}');if(h.undo&&!Array.isArray(h.undo)||h.redo&&!Array.isArray(h.redo)||h.external&&
    !Array.isArray(h.external))throw Error('The saved history has an unreadable format. It was left untouched.');
    savedEditHistory.undo=h.undo||[];savedEditHistory.redo=h.redo||[];savedEditHistory.external=new Set(h.external||[]);
    for(const change of [...savedEditHistory.undo,...savedEditHistory.redo]){if(change.correction_id&&change.file)authorChangeRecords.set(change.file,
      change.correction_id);for(const correction of change.corrections||[])authorChangeRecords.set(correction.file,correction.id);}
    editHistoryLoadedFor=S.corpus;storageRecovered('history');return true;
  }catch(error){return storageFailure('history',error,'read');}
}

async function rememberExternalChange(change){
  if(!restoreEditHistory())return;
  if(change.application_id&&[...savedEditHistory.undo,...savedEditHistory.redo].some(row=>row.application_id===change.application_id&&row.edit_id===change.edit_id))return;
  const source=await readEditorSource(change.file);let captured=captureSourceChange(source,change);
  if(!captured&&change.after){const at=source.indexOf(change.after);if(at>=0&&source.indexOf(change.after,at+1)<0)captured=captureSourceChange(source,
    {...change,line_start:source.slice(0,at).split('\n').length});}
  if(!captured){if(!change.quiet)emit('editor-status',{text:'Change saved. Its undo location could not be recorded.',error:true});return;}
  savedEditHistory.undo.push(captured);savedEditHistory.redo=[];persistEditHistory();
}
function rememberExternalTransaction(application){
  if(!restoreEditHistory())return;
  const ref=application?.undo_ref;if(!ref||!['block','section'].includes(ref.kind)||!ref.id||ref.project!==S.corpus)return;
  const key=ref.kind+':'+ref.id;
  if(savedEditHistory.external.has(key)||[...savedEditHistory.undo,...savedEditHistory.redo].some(row=>row.undo_ref?.id===ref.id&&row.undo_ref?.kind===ref.kind))return;
  savedEditHistory.external.add(key);
  savedEditHistory.undo.push({transaction:true,undo_ref:ref,application_id:application.id,undo:null,redo:null});savedEditHistory.redo=[];persistEditHistory();
}
function rememberExternalApplication(application){
  if(!restoreEditHistory())return;
  const ref=application?.detail,count=application?.edit_count;
  if(application.project!==S.corpus||!application.id||!ref?.turn_id||ref.view!=='application'||ref.item_id!==application.id||!Number.isInteger(count)||count<1)return;
  const key='application:'+application.id;if(savedEditHistory.external.has(key))return;savedEditHistory.external.add(key);let added=false;
  for(let index=0;index<count;index++){if([...savedEditHistory.undo,...savedEditHistory.redo].some(row=>row.application_id===application.id&&
    row.edit_id===String(index)))continue;savedEditHistory.undo.push({application_id:application.id,edit_id:String(index),application_ref:{...ref,
    project:S.corpus,index}});added=true;}
  if(added)savedEditHistory.redo=[];persistEditHistory();
}
async function undoEditorChange(redo=false){
  if(!restoreEditHistory())return;
  if(savedEditHistory.busy){savedEditHistory.pending.push(redo);return;}
  if(E.dirty){document.execCommand(redo?'redo':'undo');return;}
  if(P.size)await commitAll();
  const from=redo?savedEditHistory.redo:savedEditHistory.undo,to=redo?savedEditHistory.undo:savedEditHistory.redo;
  const change=from.at(-1);if(!change){emit('editor-status',{text:redo?'Nothing to redo.':'Nothing to undo.'});return;}
  savedEditHistory.busy=true;
  try{
    if (change.history_kind === 'paragraph-restructure') {
      const next = change[redo ? 'redo' : 'undo'];
      if (!next) {
        if (change.structural_result?.recovery_action) {
          const retained = (D.pending_restructures || []).find(value => value.receipt?.intent_artifact_id === change.structural_result.receipt.intent_artifact_id);
          if (retained) showStructuralOutcome(retained);
        }
        throw Error(change.structural_result?.undo_unavailable||'Finish or inspect the structural record before its exact Undo. No text change was repeated.');
      }
      const request = restructureFollowThroughSubmission(next.action, S.corpus, next.result, 'undo-restructure');
      const result = await structuralRequest(request);
      const outcome = validateRestructureEffect(result, {project:S.corpus, prior:next.result, inverse:true});
      recordStructuralOutcome(result, outcome);
      showStructuralOutcome(result);
      if (!outcome.sourceCommitted) throw Error('Inspect the structural inverse outcome. The saved history entry is retained.');
      const observed = structuralHistoryResult(result);
      change.structural_result = observed;
      change[redo ? 'undo' : 'redo'] = result.undo_action ? {action:result.undo_action, result:observed} : null;
      from.pop();to.push(change);persistEditHistory();
      try {await window.walk.refresh();} catch (error) {emit('editor-status', {text:'Structural source change retained; view refresh failed: ' + error.message, error:true});}
      showStructuralOutcome(result);
      emit('bank', {id:result.receipt?.id, shape:'paragraph-restructure', applied:true, source:redo ? 'structural-redo' : 'structural-undo'});
      return;
    }
    if(change.application_ref){
      const ref=change.application_ref;if(ref.project!==S.corpus)throw Error('This saved application belongs to another project.');
      const saved=await store.fetchJSON('/authoring/session-turn?'+new URLSearchParams({project:S.corpus,id:ref.turn_id,view:'application',item_id:ref.item_id}));
      if(saved.project!==S.corpus||saved.application?.id!==ref.item_id)throw Error('The exact saved application could not be verified.');
      const captured=captureApplicationChange(saved.application,ref.index);
      if(!captured)throw Error('The exact saved postimage is unavailable. This Undo entry was retained; no current text was used as a substitute.');
      Object.assign(change,captured);delete change.application_ref;persistEditHistory();
    }
    if(change.transaction){
      const ref=change.undo_ref,side=redo?'redo':'undo';
      if(!change[side]){const recovered=await store.fetchJSON('/authoring/structural-undo?'+new URLSearchParams({project:S.corpus,kind:ref.kind,
        id:ref.id}));change[side]=recovered.undo;}
      if(!change[side])throw Error('The exact inverse of this saved project change is unavailable.');
      const result=await sourceEffectRequest('/authoring/'+(ref.kind==='block'?'block-change':'section-change'),{method:'POST',body:{project:S.corpus,...change[side]}});
      if(!result.ok||!result.undo)throw Error('The change did not return its exact inverse.');
      change[redo?'undo':'redo']=result.undo;from.pop();to.push(change);persistEditHistory();await window.walk.refresh();
      emit('bank',{applied:true,source:redo?'agent-change-redo':'agent-change-undo'});emit('editor-status',{text:redo?'Project edit redone.':'Project edit undone.'});return;
    }
    // `section` is also ordinary source-edit context (the containing manuscript
    // section). Only an explicit history type may route Undo to a structural API.
    // The boolean checks retain histories saved by older builds.
    if(change.history_kind==='section'||change.section===true){const result=await sourceEffectRequest('/authoring/section-change',{method:'POST',
      body:{project:S.corpus,...(redo?change.redo:change.undo)}});if(!result.ok||!result.undo)throw Error(
      'The heading change did not return its inverse.');if(redo)change.undo=result.undo;else change.redo=result.undo;from.pop();to.push(change);
      persistEditHistory();await window.walk.refresh();emit('bank',{applied:true,source:redo?'section-redo':'section-undo'});emit('editor-status',{
      text:redo?'Heading restored.':'Heading removed; following prose preserved.'});return;}
    if(change.history_kind==='block'||change.atomic===true){const edits=redo?change.edits.map(edit=>({...edit,before:edit.after,
      after:edit.before})):change.edits;const placement=redo&&change.placement?{...change.placement,before:change.placement.after,
      after:change.placement.before}:change.placement;await sourceEffectRequest('/authoring/block-change',{method:'POST',body:{project:S.corpus,
      operation:'undo',edits,placement}});from.pop();to.push(change);persistEditHistory();clearObjectSelection();await window.walk.refresh();
      const spec=redo?change.after_block:change.before_block;if(spec){const block=findObject(spec);if(block)selectObject(block,{scroll:true});}emit(
      'bank',{shape:'rewrite',applied:true,source:redo?'editor-redo':'editor-undo'});emit('editor-status',{text:redo?'Object change redone.':'Object change undone.'});return;}
    // ONE REQUEST FOR THE FOURTH GESTURE (WRITING-CONSOLIDATION-W1, the synthesis of the
    // storage-latency and editor-doors lanes). Undo used to build its own body and post it
    // straight at the door with `line_start:1, line_end:<every line>`: a second producer of
    // the request AND the whole chapter in `before`/`after`, banked three times over by the
    // door (`anchor.before`, `anchor.after`, `anchor.quote`).
    //
    // It is now the SAME request the other three gestures send -- `sourceRequest` ->
    // `retrySaveOnce` -- addressed at the HUNK SPAN that `historySpan` answers: the whole
    // lines the inverse touches, with the passage he typed over beside them. The two lanes
    // met exactly here, and the span is what made the identity possible: a request addressed
    // at the whole file has a `prose` home nothing published a token for, so the door could
    // only compare bytes; a request addressed at a block's own span has the home the canvas
    // published a token for in the read the page was built from, so this gesture carries
    // `expected` like every other one. When the hunk is NOT one published block's span the
    // list is empty -- the declared normal path (`expectedOf`) -- and the door's byte guard
    // over `before` decides, as it did for every gesture before this campaign.
    //
    // `retrySaveOnce`, not `saveSourceChange`: this gesture owns its own history (the two
    // stacks above), and the save path's capture would push a SECOND entry for the very undo
    // that is consuming one. The retry is what both share.
    const span=historySpan(await readEditorSource(change.file),change,!redo);
    const result=await retrySaveOnce(sourceRequest({
      file:change.file, lineStart:span.line_start, lineEnd:span.line_end,
      before:span.before, after:span.after,
      passageBefore:span.replaced, passageAfter:span.replacement,
      expected:expectedOf(blockAtSpan(change.file,span.line_start,span.line_end)),
      source:redo?'editor-redo':'editor-undo', extra:{scope:'sentence'}}));
    if(!appliedOf(result,result?.record||{}))throw Error('The passage changed while undoing. Nothing was overwritten.');
    from.pop();to.push(change);persistEditHistory();await window.walk.refresh();
    const savedCaret=redo?change.caret_after:change.caret_before;
    if(savedCaret){const find=point=>S.blocks.find(item=>srcOf(item).file===change.file&&point.tex!=null&&item.tex===point.tex)||S.blocks.find(item=>
      srcOf(item).file===change.file&&srcOf(item).lineStart===point.line_start);const target=find(savedCaret);if(target?.bodyEl&&editableBlock(
      target)){target.bodyEl.focus({preventScroll:true});const range=caretRange(target.bodyEl,savedCaret.offset||0);
      const end=savedCaret.selection_end&&find(savedCaret.selection_end);if(end?.bodyEl){const finish=caretRange(end.bodyEl,
      savedCaret.selection_end.offset||0);range.setEnd(finish.endContainer,finish.endOffset);}const selection=document.getSelection();
      selection.removeAllRanges();selection.addRange(range);}}
    emit('bank',{shape:'rewrite',applied:true,source:redo?'editor-redo':'editor-undo'});emit('editor-status',{text:(
      redo?'Change redone.':'Change undone.')+(result.receipt?.retry_warning?' '+result.receipt.retry_warning:''),error:!!result.receipt?.retry_warning});
  }catch(error){emit('editor-status',{text:error.message,error:true});}finally{savedEditHistory.busy=false;if(
    savedEditHistory.pending.length)undoEditorChange(savedEditHistory.pending.shift());}
}

function structuralHistoryResult(result) {
  return {project:result.project, section_id:result.section_id, kind:result.kind, receipt:result.receipt, receipt_recorded:result.receipt_recorded,
    undo_action:result.undo_action, recovery_action:result.recovery_action,undo_unavailable:result.undo_unavailable||(
      result.metadata_only===true?'The record is settled. Its older exact inverse is unavailable after retaining later edits.':null)};
}

function rememberStructuralChange(result) {
  restoreEditHistory();
  if (savedEditHistory.undo.some(row => row.history_kind === 'paragraph-restructure' &&
      row.structural_result?.receipt?.id === result.receipt.id)) return;
  const observed = structuralHistoryResult(result);
  savedEditHistory.undo.push({history_kind:'paragraph-restructure', structural_result:observed,
    undo:result.undo_action ? {action:result.undo_action, result:observed} : null, redo:null});
  savedEditHistory.redo = [];
  persistEditHistory();
}

const structuralOutcomeControllers = [];
const structuralSourceHolds = new Map();
const pendingPresentationSplits = new Map();
function recordStructuralOutcome(result, outcome) {
  for (const file of outcome.source.effect.files) {
    const held = structuralSourceHolds.get(file.path);
    if (outcome.sourceCommitted && (!held || held.receipt?.intent_artifact_id === result.receipt?.intent_artifact_id)) structuralSourceHolds.delete(file.path);
    else if (['PARTIAL','UNPROVED'].includes(outcome.source.state)) structuralSourceHolds.set(file.path, result);
  }
}
function showStructuralOutcome(result) {
  for (const controller of structuralOutcomeControllers) controller.destroy();
  structuralOutcomeControllers.length = 0;
  docEl.querySelector('[data-structural-outcome]')?.remove();
  const host = asChrome(el('section', 'manuscript-structural-outcome'));host.contentEditable = 'false';
  host.dataset.structuralOutcome = '';
  const anchor = findRestructureAnchor(result, S.blocks);
  if (anchor?.el?.isConnected) anchor.el.before(host); else docEl.prepend(host);
  const rows = [...(D.pending_restructures || []).filter(row => row.receipt?.intent_artifact_id !== result.receipt?.intent_artifact_id), result];
  for (const current of rows) {
  const result = current;
  structuralOutcomeControllers.push(renderRestructureOutcome(host, result, {
    project:S.corpus,
    isCurrent:() => host.isConnected,
    onRead:handle => {
      const url = handle?.http?.url;
      if (handle?.http?.method !== 'GET' || !url) throw Error('The structural owner supplied no exact outcome read.');
      const read = ownerHumanTarget(url);
      if (!read || read.project !== S.corpus) throw Error('The structural read belongs to another project.');
      window.parent.postMessage({type:'laplace:open-owner-read', url, label:'Paragraph structure'}, location.origin);
    },
    onInspectReconciliation:(handle,retained)=>openMetadataReconciliation({project:S.corpus,handle,retained,
      request:(url,payload)=>store.fetchJSON(url,{method:payload?'POST':'GET',inject:[],...(payload?{body:payload}:{})}),
      opener:document.activeElement,isCurrent:()=>host.isConnected,onSaved:async next=>settle(next)}),
    onRecovery:async action => {
      const request = restructureFollowThroughSubmission(action, S.corpus, result);
      const next = await structuralRequest(request);
      await settle(next);
    }
  }));
  async function settle(next){
      const outcome = validateRestructureEffect(next, {project:S.corpus, prior:result});
      recordStructuralOutcome(next, outcome);
      const previousIntent = result.receipt.intent_artifact_id;
      for (const row of [...savedEditHistory.undo, ...savedEditHistory.redo]) {
        if (row.history_kind !== 'paragraph-restructure' || row.structural_result?.receipt?.intent_artifact_id !== previousIntent) continue;
        const observed = structuralHistoryResult(next);row.structural_result = observed;
        const side = savedEditHistory.undo.includes(row) ? 'undo' : 'redo';
        row[side] = next.undo_action ? {action:next.undo_action, result:observed} : null;
      }
      persistEditHistory();
      try { await window.walk.refresh(); } catch (error) { emit('editor-status', {text:'Structural record retained. View refresh failed: ' + error.message, error:true}); }
      showStructuralOutcome(next);
  }
  }
  scheduleRemeasure();
}

export {
  editorPersistence, pendingPresentationSplits, persistEditHistory, recordStructuralOutcome,
  rememberExternalApplication, rememberExternalChange, rememberExternalTransaction, rememberStructuralChange,
  restoreEditHistory, savedEditHistory, showStructuralOutcome, storageFailure, storageRecovered,
  structuralSourceHolds, undoEditorChange
};
