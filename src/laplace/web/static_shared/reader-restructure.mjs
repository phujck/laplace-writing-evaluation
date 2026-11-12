// PARAGRAPH RESTRUCTURE CONTRACTS. Purpose: the shapes, submissions and outcome rendering of the
// reader-plan owner's structural operations (preview, apply, follow-through, reconciliation) over
// paragraph plans. Ownership: reader_restructure (owner) issues every call with its guards and
// publishes RESTRUCTURE_SCHEMA outcomes; this module validates before sending
// (validateRestructureDraft/Preview/Guards/Effect, validateReconciliationResult), builds the
// submissions (restructurePreviewSubmission, restructureApplySubmission,
// restructureFollowThroughSubmission, reconciliationSubmission) and renders outcomes
// (restructureOutcome, renderRestructureOutcome, renderMetadataReconciliation,
// inspectStructuralInput, findRestructureAnchor). Inputs/outputs: exact owner calls and
// receipts. Currentness: expected revisions on every call; a changed plan refuses at the owner
// and the retained outcome says so. Consumers: reader-state.mjs, workspace-spine.mjs,
// reader-logical-restructure.mjs, writing-artifact.mjs. Storage: none.
import {sourceEffectDisposition} from './source-effect.mjs';
import {planPublicationDisposition} from './plan-publication.mjs';
import {qualifiedOwnerHTTP} from './writing-owner-read.mjs';
import {validateSourceRead} from './manuscript-source-client.mjs';
import {pendingRead} from './pending-read.mjs';

export const RESTRUCTURE_SCHEMA = 'laplace.paragraph-restructure/1';
const kinds = new Set([
  'presentation-split', 'presentation-join', 'logical-split', 'logical-merge'
]);
const fingerprint = value => typeof value === 'string' && /^sha256:[a-f0-9]{64}$/.test(value);
const identifier = value => typeof value === 'string' && !!value.trim() && !/[\u0000-\u001f]/.test(value);
const path = value => identifier(value) && !value.startsWith('/') && !value.includes('\\') && !value.split('/').includes('..');
const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === 'object'
  ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])])) : value;
const same = (left, right) => JSON.stringify(canonical(left)) === JSON.stringify(canonical(right));
const copy = value => structuredClone(value);
// Mapping preview may strengthen empty read guards to the explicitly selected files.
// Physical observations and all non-source dependencies still have to match.
const observationBasis=value=>{const result=copy(value);if(result?.guards)delete result.guards.source_guards;return result;};

export function validateRestructureDraft(draft, kind) {
  if (!draft || !kinds.has(kind) || !Array.isArray(draft.paragraph_ids) || !draft.paragraph_ids.length ||
      draft.paragraph_ids.some(value => !identifier(value)) || new Set(draft.paragraph_ids).size !== draft.paragraph_ids.length) {
    throw Error('The structural change needs the complete inspected planned units and source passages.');
  }
  if(kind.startsWith('logical-')){
    const fields=['paragraph_ids','successor_count','successors','attachment_assignments','occurrence_assignments'];
    if(Object.keys(draft).some(key=>!fields.includes(key))||
        kind==='logical-split'&&draft.paragraph_ids.length!==1||kind==='logical-merge'&&draft.paragraph_ids.length<2||
        draft.successor_count!==undefined&&(!Number.isInteger(draft.successor_count)||draft.successor_count<2)){
      throw Error('Logical changes need exact predecessor units and explicit successor/attachment choices, without free source edits.');
    }
    for(const [field,key]of [['successors','paragraph_id'],['attachment_assignments','attachment_id'],['occurrence_assignments','occurrence_id']]){
      if(draft[field]!==undefined&&(!Array.isArray(draft[field])||draft[field].some(row=>!identifier(row?.[key]))||new Set(draft[field].map(row=>row[key])).size!==draft[field].length))
        throw Error('Use each exact owner-issued logical choice once.');
    }
    return draft;
  }
  if(!Array.isArray(draft.source_edits)||!draft.source_edits.length)throw Error('The layout change has no exact inspected source passages.');
  for (const edit of draft.source_edits) {
    if (!path(edit.file) || !Number.isInteger(edit.line_start) || edit.line_start < 1 ||
        !Number.isInteger(edit.line_end) || edit.line_end < edit.line_start ||
        typeof edit.before !== 'string' || typeof edit.after !== 'string' ||
        !fingerprint(edit.expected_source_digest) || !fingerprint(edit.expected_selection)) {
      throw Error('The structural change has no exact inspected source passage.');
    }
  }
  if (kind === 'presentation-split' && (draft.source_edits.length !== 1 ||
      !Array.isArray(draft.parts) || draft.parts.length < 2 || draft.parts.some(value => typeof value !== 'string') ||
      draft.parts.join('\n\n') !== draft.source_edits[0].after)) {
    throw Error('Paragraph breaks need all exact authored source parts.');
  }
  if (kind === 'presentation-join' && (draft.source_edits.length !== 2 || draft.source_edits[1].after !== '')) {
    throw Error('A paragraph join needs both exact source passages.');
  }
  return draft;
}

function actionPayload(action, project, operation) {
  const route = action?.http?.url || action?.http?.route;
  const payload = action?.payload;
  if (action?.operation !== 'structure_change' || action.permitted === false ||
      action.http?.method !== 'POST' || route !== '/work/structure/change' ||
      action.http.url && action.http.route && action.http.url !== action.http.route ||
      action.project && action.project !== project || payload?.project && payload.project !== project ||
      payload?.operation !== 'paragraph_plan' || payload.action !== operation || !identifier(payload.section_id)) {
    throw Error('The owner supplied no matching structural action. Inspect the passage again.');
  }
  const fields = operation === 'preview-restructure'
    ? ['operation','action','section_id','kind','draft','project','expected_selection','source_guards']
    : operation === 'preview-reconciliation'
      ? ['operation','action','section_id','project','receipt_id','intent_artifact_id','current_occurrence_assignments']
    : operation === 'reconcile-restructure'
      ? ['operation','action','section_id','project','receipt_id','intent_artifact_id','guards','reconciliation_token','current_occurrence_assignments']
    : operation === 'restructure'
      ? ['operation','action','section_id','kind','draft','project','restructure_token','guards']
      : ['operation','action','section_id','project','receipt_id','intent_artifact_id','guards'];
  if (Object.keys(payload).some(key => !fields.includes(key))) {
    throw Error('The structural action contains fields outside its owner contract.');
  }
  return {url: route, payload: {...copy(payload), project}};
}

export function restructurePreviewSubmission(action, project, kind, draft) {
  validateRestructureDraft(draft, kind);
  const request = actionPayload(action, project, 'preview-restructure');
  if(request.payload.kind&&request.payload.kind!==kind)throw Error('The structural preview action belongs to a different operation.');
  request.payload = {...request.payload, kind, draft: copy(draft), project};
  return request;
}

export function validateRestructurePreview(value, {project, kind, draft} = {}) {
  if (value?.schema_version !== RESTRUCTURE_SCHEMA || value.project !== project ||
      !kinds.has(value.kind) || !fingerprint(value.restructure_token) ||
      !value.guards || typeof value.guards !== 'object' || Array.isArray(value.guards) ||
      (!value.kind?.startsWith('logical-')&&(!value.occurrence_mapping || !Array.isArray(value.occurrence_mapping.before) ||
      !Array.isArray(value.occurrence_mapping.after)))) {
    throw Error('The structural preview does not retain its exact source and plan basis.');
  }
  validateRestructureDraft(value.draft, value.kind);
  if (kind && value.kind !== kind || draft && !same(value.draft, draft)) {
    throw Error('The structural preview belongs to a different authored change.');
  }
  return value;
}

const guardFields = [
  'expected_plan_revision', 'expected_narrative_revision', 'expected_decision_revision',
  'expected_provenance_revision', 'expected_attachment_revision', 'expected_selection', 'source_guards'
];

export function validateRestructureGuards(guards,kind='presentation-split') {
  const logical=kind.startsWith('logical-'),fields=logical?[...guardFields,'expected_reader_basis','expected_source_set_revision']:guardFields;
  if (!guards || Object.keys(guards).some(key => !fields.includes(key)) ||
      fields.some(key => !Object.hasOwn(guards, key)) ||
      !fingerprint(guards.expected_plan_revision) || !fingerprint(guards.expected_selection) ||
      ['expected_narrative_revision', 'expected_decision_revision', 'expected_provenance_revision', 'expected_attachment_revision']
        .some(key => guards[key] !== null && !fingerprint(guards[key])) ||
      !guards.source_guards || typeof guards.source_guards !== 'object' || Array.isArray(guards.source_guards) ||
      !logical&&!Object.keys(guards.source_guards).length ||
      Object.entries(guards.source_guards).some(([file, revision]) => !path(file) || !fingerprint(revision))) {
    throw Error('The structural action has no complete source, plan and attachment guards.');
  }
  if(logical&&(!fingerprint(guards.expected_source_set_revision)||!guards.expected_reader_basis||Array.isArray(guards.expected_reader_basis)||
      !Object.keys(guards.expected_reader_basis).length||Object.entries(guards.expected_reader_basis).some(([id,basis])=>
        basis?.schema_version!=='laplace.reader-basis/1'||basis.subject_id!==id||!fingerprint(basis.subject_revision)||
        !identifier(basis.project)||!identifier(basis.section_id)||!path(basis.path)||!basis.inputs||Array.isArray(basis.inputs)||Object.values(basis.inputs).some(value=>!fingerprint(value)))))
    throw Error('The logical change has no exact reader and selected-source basis.');
  return guards;
}

export function restructureApplySubmission(value, project) {
  validateRestructurePreview(value, {project});
  validateRestructureGuards(value.guards,value.kind);
  if(value.kind.startsWith('logical-')&&!Object.keys(value.guards.source_guards).length&&value.source_required!==false)
    throw Error('A logical action without physical source pins must explicitly declare its plan-only scope.');
  const request = actionPayload(value.apply_action, project, 'restructure');
  if (request.payload.kind !== value.kind || request.payload.restructure_token !== value.restructure_token ||
      !same(request.payload.guards, value.guards)) {
    throw Error('The structural action does not retain the comparison you inspected.');
  }
  request.payload.draft = copy(value.draft);
  return request;
}

export function restructureFollowThroughSubmission(action, project, result, operation = 'recover-restructure') {
  if (!['recover-restructure', 'undo-restructure'].includes(operation) ||
      result?.project !== project || !identifier(result.receipt?.id) || !identifier(result.receipt?.intent_artifact_id)) {
    throw Error('Inspect the exact retained structural receipt before this action.');
  }
  const ownedAction = operation === 'undo-restructure' ? result.undo_action : result.recovery_action;
  if (!same(action, ownedAction)) throw Error('Use the exact action returned with this structural receipt.');
  const request = actionPayload(action, project, operation);
  if (request.payload.receipt_id !== result.receipt.id || request.payload.intent_artifact_id !== result.receipt.intent_artifact_id) {
    throw Error('The structural recovery names a different saved operation.');
  }
  validateRestructureGuards(request.payload.guards,result.kind);
  return request;
}

// Physical text and reader-plan publication are separate facts. A committed
// source must never be presented as an unsaved draft merely because the plan's
// required follow-through remains pending.
export function restructureOutcome(result, {project} = {}) {
  if (result?.schema_version !== RESTRUCTURE_SCHEMA || result.project !== project || !kinds.has(result.kind)) {
    throw Error('The structural outcome belongs to another passage or project. Preserve the draft and inspect its receipt.');
  }
  const planOnly=result.kind.startsWith('logical-')&&result.source_required===false;
  if(planOnly&&(result.source_unchanged!==true||result.source_effect!==undefined))throw Error('A plan-only logical change must explicitly retain unchanged source without a source receipt.');
  const source = planOnly?null:sourceEffectDisposition(result, {project});
  const plan = planPublicationDisposition(result);
  if (!plan || !planOnly&&!source) throw Error('The structural owner returned no separate source and plan receipts.');
  const sourceCommitted = !!source&&(source.state === 'COMMITTED' || source.state === 'UNCHANGED');
  const historical=result.metadata_only===true&&result.source_currentness==='HISTORICAL_EFFECT_WITH_SEPARATE_CURRENT_OBSERVATION';
  const metadataReconciled=historical||planOnly&&result.metadata_only===true&&result.source_currentness==='NO_PHYSICAL_EFFECT_WITH_SEPARATE_CURRENT_OBSERVATION';
  if(metadataReconciled){
    const inspected=result.metadata_reconciliation;
    if(!planOnly&&!sourceCommitted||!fingerprint(inspected?.reconciliation_token)||!result.current_observation||
        inspected.original_receipt?.intent_artifact_id!==result.receipt?.intent_artifact_id)
      throw Error('The metadata acknowledgement did not retain its historical source receipt and separate current observation.');
    validateRestructureGuards(result.current_observation.guards,result.kind);
  }
  return {result, source, plan,sourceHistorical:historical,metadataReconciled, sourceCommitted,sourceSettled:planOnly||sourceCommitted,
    complete:(metadataReconciled?result.complete===true&&(planOnly||sourceCommitted):planOnly||source.acknowledged)&&plan.acknowledged};
}

// Eligibility is issued once per full-marker group, never copied per passage.
function reconciliationEligibility(inspection){
  const expected=new Map(),choices=new Map(),groups=new Map(),listed=new Set();
  for(const row of inspection.current_occurrence_choices||[]){if(!identifier(row.id)||choices.has(row.id))throw Error('The current passage inventory has duplicate identities.');choices.set(row.id,row);}
  for(const group of inspection.current_occurrence_groups||[]){
    if(!identifier(group.id)||groups.has(group.id)||!Array.isArray(group.choice_ids))throw Error('The source owner supplied no unique eligibility group.');
    const ids=new Set();
    for(const id of group.choice_ids){const choice=choices.get(id);if(ids.has(id)||listed.has(id)||!choice||choice.file!==group.file||!same(choice.spec_ids,group.spec_ids))throw Error('The source eligibility group does not match its exact passage inventory.');ids.add(id);listed.add(id);}
    groups.set(group.id,{...group,ids});
  }
  for(const row of inspection.occurrence_inventory||[]){const group=groups.get(row.allowed_current_occurrence_group_id);
    if(expected.has(row.id)||!group||group.file!==row.file||!same(group.spec_ids,row.spec_ids))throw Error('The recorded passage has no matching owner-issued eligibility group.');expected.set(row.id,row);
  }
  return {expected,choices,groups};
}

export function reconciliationSubmission(value,project,{previewAssignments}={}){
  const outcome=restructureOutcome(value,{project}),inspection=value.metadata_reconciliation;
  if(!outcome.sourceSettled||!inspection||!['READY','NEEDS_INPUT','UNPROVABLE'].includes(inspection.status)||
      inspection.original_receipt?.id!==value.receipt?.id||inspection.original_receipt?.intent_artifact_id!==value.receipt?.intent_artifact_id)
    throw Error('Inspect this exact retained operation’s current recovery basis.');
  const preview=previewAssignments!==undefined;
  if(!preview&&inspection.status!=='READY')throw Error('The current source mapping is not proved for metadata reconciliation.');
  const action=preview?inspection.preview_action:inspection.action;
  const submission=actionPayload(action,project,preview?'preview-reconciliation':'reconcile-restructure');
  if(submission.payload.section_id!==value.section_id||submission.payload.receipt_id!==value.receipt.id||
      submission.payload.intent_artifact_id!==value.receipt.intent_artifact_id)throw Error('The recovery action belongs to a different retained operation.');
  if(preview){
    const {expected,choices,groups}=reconciliationEligibility(inspection);
    if(!Array.isArray(previewAssignments)||new Set(previewAssignments.map(row=>row.expected_occurrence_id)).size!==previewAssignments.length||
        new Set(previewAssignments.map(row=>row.current_occurrence_id)).size!==previewAssignments.length||previewAssignments.some(row=>
          Object.keys(row).sort().join(',')!=='current_occurrence_id,expected_occurrence_id'||!expected.has(row.expected_occurrence_id)||!choices.has(row.current_occurrence_id)||!groups.get(expected.get(row.expected_occurrence_id)?.allowed_current_occurrence_group_id)?.ids.has(row.current_occurrence_id)))
      throw Error('Choose distinct current passages from this owner’s exact inventory.');
    submission.payload.current_occurrence_assignments=copy(previewAssignments);
  }else{
    validateRestructureGuards(submission.payload.guards,value.kind);
    if(!fingerprint(inspection.reconciliation_token)||submission.payload.reconciliation_token!==inspection.reconciliation_token||
        !same(submission.payload.guards,inspection.guards)||!same(submission.payload.guards,inspection.current_observation?.guards)||
        !same(submission.payload.current_occurrence_assignments,inspection.current_occurrence_assignments))
      throw Error('The metadata action does not retain the exact current observation and passage mapping you inspected.');
  }
  return submission;
}

export function validateReconciliationResult(result,{project,inspected}={}){
  const outcome=validateRestructureEffect(result,{project,prior:inspected});
  if(result.metadata_only!==true||!outcome.metadataReconciled||result.metadata_reconciliation.reconciliation_token!==inspected.metadata_reconciliation.reconciliation_token||
      !same(result.source_effect,inspected.source_effect)||!same(result.current_observation,inspected.metadata_reconciliation.current_observation)||
      result.source_receipt_id!==(inspected.source_receipt_id||inspected.receipt.id)||result.undo_action)
    throw Error('The metadata acknowledgement did not preserve the original physical effect and inspected current source.');
  return outcome;
}

export function validateRestructureEffect(result, {project, preview, prior, inverse = false} = {}) {
  const outcome = restructureOutcome(result, {project});
  if (!identifier(result.receipt?.id) || !identifier(result.receipt?.intent_artifact_id)) {
    throw Error('The structural effect has no retained owner receipt. Preserve the draft and inspect its outcome.');
  }
  const reference = preview || prior;
  if (reference && (result.section_id !== reference.section_id || result.kind !== reference.kind)) {
    throw Error('The structural effect belongs to a different planned section or operation.');
  }
  if (preview) {
    const expected = preview.source_changes;
    const files = result.source_effect?.files;
    if (result.source_required===false ? expected.length!==0 : !files||result.source_effect.selection_identity !== preview.guards.expected_selection ||
        result.source_changes && !same(result.source_changes, expected) ||
        files.length !== expected.length || expected.some(change => !files.some(file =>
          file.path === change.file && file.before_sha256 === change.before_sha256 && file.after_sha256 === change.after_sha256))) {
      throw Error('The structural effect does not retain the exact prepared source change.');
    }
  }
  if (prior && !inverse && result.receipt.intent_artifact_id !== prior.receipt.intent_artifact_id) {
    throw Error('The recovery belongs to another retained structural intent.');
  }
  return outcome;
}

// Place a cue only against the exact current postimage and full occurrence ID
// set. A historical line number alone is never a current passage binding.
export function findRestructureAnchor(result, blocks) {
  const effect = result?.source_effect;
  if (!['COMMITTED','UNCHANGED'].includes(effect?.state)) return null;
  for (const occurrence of result.remapped_occurrences || []) {
    for (const block of blocks) {
      const lease = block.restructure_preview?.payload, file = block.src?.repo_file;
      const physical = effect.files.find(row => row.path === file);
      if (physical && lease?.expected_selection === effect.selection_identity &&
          lease.source_guards?.[file] === physical.after_sha256 &&
          same(block.spec_ids, occurrence.spec_ids) &&
          block.src.line_start >= occurrence.start_line && block.src.line_start <= occurrence.end_line) return block;
    }
  }
  // Fresh pending projections carry the owner's bounded physical scope rather
  // than hydrating every historical occurrence. It is only a cue locator.
  const scope = result.source_scope;
  if (scope && Number.isInteger(scope.line_start) && Number.isInteger(scope.after_line_end)) {
    const physical = effect.files.find(row => row.path === scope.file);
    if (physical) for (const block of blocks) {
      const lease = block.restructure_preview?.payload;
      if (block.src?.repo_file === scope.file && lease?.expected_selection === effect.selection_identity &&
          lease.source_guards?.[scope.file] === physical.after_sha256 &&
          block.src.line_start >= scope.line_start && block.src.line_start <= scope.after_line_end) return block;
    }
  }
  return null;
}

const element = (tag, text = '', className = '') => {
  const node = document.createElement(tag);
  node.textContent = text;
  node.className = className;
  return node;
};

export async function inspectStructuralInput(handle,{project,request,onRead,label='Structural input',opener,isCurrent=()=>true}={}){
  const target=qualifiedOwnerHTTP(handle,project);
  if(!target?.source)return onRead?.(handle,label);
  const payload=handle.payload,lo=payload?.line_start,hi=payload?.line_end;
  if(handle.operation!=='source'||payload.files?.length!==1||payload.files[0]!==target.source.file||
      !Number.isInteger(lo)||lo<1||!Number.isInteger(hi)||hi<lo)throw Error('The source input has no exact owner-issued passage coordinates.');
  const dialog=element('dialog','','spine-binding-dialog'),status=pendingRead(element('p','Reading current source…')),body=element('section'),close=element('button','Close');
  close.type='button';close.onclick=()=>dialog.close();dialog.append(element('h3',label),status,body,close);document.body.append(dialog);dialog.showModal();
  let alive=true;dialog.addEventListener('close',()=>{alive=false;dialog.remove();if(isCurrent()&&opener?.isConnected)opener.focus({preventScroll:true});});
  try{
    const value=validateSourceRead(await request(target.url));if(!alive||!isCurrent()){dialog.close();return null;}
    if(value.file!==target.source.file)throw Error('The source owner returned a different file.');
    const lines=value.content.split('\n');if(hi>lines.length)throw Error('The recorded location is outside the current file. Inspect the current recovery choices.');
    status.textContent='Current source · '+value.file.split('/').at(-1)+':'+lo+'–'+hi;
    body.append(element('pre',lines.slice(lo-1,hi).map((line,index)=>(lo+index)+' | '+line).join('\n'),'spine-source-preview'));
    const identity=element('details');identity.append(element('summary','Current source identity'),element('code',value.expected_source_digest));body.append(identity);
  }catch(error){if(alive)status.textContent=error.message;}
  return dialog;
}

export function renderMetadataReconciliation(host,value,{project,onRead,onPreview,onReconcile,isCurrent=()=>true}={}){
  const observed=restructureOutcome(value,{project});
  const inspection=value.metadata_reconciliation;
  if(!inspection||!['READY','NEEDS_INPUT','UNPROVABLE'].includes(inspection.status)||!fingerprint(inspection.reconciliation_token)||
      inspection.original_receipt?.intent_artifact_id!==value.receipt.intent_artifact_id)
    throw Error('The current-source inspection has no exact retained operation basis.');
  const panel=element('section','','reader-reconciliation-inspection'),status=element('p');status.setAttribute('role','status');
  panel.append(element('h4','Current recovery basis'),element('p',observed.source?'The original save receipt stays historical. Reconciliation records metadata against the explicitly inspected current source; it does not rewrite text.':'No manuscript text change was required. Reconciliation records reader metadata against the explicitly inspected current inputs.'),status);host.append(panel);
  let alive=true,blocked=false;
  const fresh=()=>alive&&panel.isConnected!==false&&isCurrent();
  const button=(label,run)=>{const node=element('button',label);node.type='button';node.onclick=async()=>{
    if(!fresh()||node.disabled)return;node.disabled=true;
    try{await run();}catch(error){if(fresh())status.textContent=error.message;}finally{if(fresh())node.disabled=false;}
  };return node;};
  status.textContent=inspection.status==='READY'?'Current marker bindings and metadata are proved for this recording.':
    inspection.status==='NEEDS_INPUT'?'Choose the current passage for each recorded location, then preview the mapping.':'The current source cannot be proved for this recovery.';
  for(const reason of inspection.refusal_reasons||[])panel.append(element('p',reason,'error'));
  const expected=inspection.occurrence_inventory||[],{choices,groups}=reconciliationEligibility(inspection),assignments=new Map((inspection.current_occurrence_assignments||[]).map(row=>[row.expected_occurrence_id,row.current_occurrence_id]));
  let activeChoice=null;
  if(expected.length){
    const mapping=element('section');mapping.append(element('h5','Recorded and current passages'));
    for(const row of expected){
      const card=element('fieldset');card.dataset.expectedOccurrenceId=row.id;
      card.append(element('legend',row.file.split('/').at(-1)+':'+row.line_start+' (recorded location)'));
      if(row.read&&onRead)card.append(button('Inspect current source at recorded coordinates',()=>onRead(row.read,'Current source at recorded coordinates')));
      if(onPreview&&inspection.status!=='UNPROVABLE'){
        const label=element('label','Current passage'),select=element('select');select.setAttribute('aria-label','Current passage');
        const eligibility=groups.get(row.allowed_current_occurrence_group_id);
        const option=id=>{const current=choices.get(id),node=element('option',current.file.split('/').at(-1)+':'+current.line_start+'–'+current.line_end);node.value=id;return node;};
        const collapse=()=>{const selected=assignments.get(row.id)||'',placeholder=element('option','Choose an inspected current passage');placeholder.value='';select.replaceChildren(placeholder);if(selected){if(!eligibility.ids.has(selected))throw Error('The recorded choice is outside its owner-issued passage group.');select.append(option(selected));}select.value=selected;};
        const activate=()=>{if(!fresh()||activeChoice?.select===select)return;activeChoice?.collapse();const selected=assignments.get(row.id)||'';collapse();for(const id of eligibility.choice_ids)if(id!==selected)select.append(option(id));select.value=selected;activeChoice={select,collapse};};
        collapse();select.onfocus=activate;select.onpointerdown=activate;label.append(select);card.append(label);
        select.onchange=()=>{if(select.value)assignments.set(row.id,select.value);else assignments.delete(row.id);blocked=true;reconcile.disabled=true;status.textContent='Passage choices changed. Preview the mapping before reconciling.';};
        if(onRead)card.append(button('Inspect selected current passage',()=>{const current=choices.get(select.value);if(!current?.read)throw Error('Choose a current passage before inspection.');return onRead?.(current.read,'Current source passage');}));
      }else{
        const current=choices.get(assignments.get(row.id));
        if(current)card.append(element('p','Current passage: '+current.file.split('/').at(-1)+':'+current.line_start+'–'+current.line_end));
      }
      mapping.append(card);
    }
    panel.append(mapping);
  }
  if(inspection.review_obligations?.length){const details=element('details');details.append(element('summary',inspection.review_obligations.length+' retained review obligations'));for(const row of inspection.review_obligations)details.append(element('p',row.reason||row.kind.replaceAll('_',' ').toLowerCase()));panel.append(details);}
  for(const read of inspection.source_reads||[])if(onRead)panel.append(button('Inspect current source',()=>onRead(read,'Current source')));
  const reconcile=button('Reconcile reader record with inspected source',()=>onReconcile(value));reconcile.disabled=inspection.status!=='READY'||!onReconcile;
  if(onPreview&&inspection.status!=='UNPROVABLE')panel.append(button('Preview inspected passage mapping',()=>onPreview(value,expected.flatMap(row=>assignments.has(row.id)?[{expected_occurrence_id:row.id,current_occurrence_id:assignments.get(row.id)}]:[]))));
  if(onReconcile)panel.append(reconcile);
  else panel.append(element('p','This inspection is read-only. Open the Reader plan to reconcile its retained record.','muted'));
  return {destroy(){alive=false;},blockSubmission(){blocked=true;reconcile.disabled=true;},syncControls(){for(const node of panel.querySelectorAll('button'))node.disabled=false;reconcile.disabled=blocked||inspection.status!=='READY'||!onReconcile;}};
}

export async function openMetadataReconciliation({project,handle,retained,request,onRead,onSaved=async()=>{},opener,isCurrent=()=>true}={}){
  const target=qualifiedOwnerHTTP(handle,project);
  if(target?.owner?.kind!=='structure'||target.owner.view!=='restructure'||target.owner.read_handle.payload.reconcile_current!==true||
      target.owner.read_handle.payload.receipt_id!==retained.receipt.id||target.owner.read_handle.payload.intent_artifact_id!==retained.receipt.intent_artifact_id)
    throw Error('The retained operation has no exact current-source inspection handle.');
  if(!document.querySelector('link[data-reader-reconciliation]')){const css=element('link');css.rel='stylesheet';css.href='/shared/workspace-spine.css';css.dataset.readerReconciliation='';document.head.append(css);}
  const dialog=element('dialog','','spine-binding-dialog reader-logical-dialog'),reading=element('section'),status=pendingRead(element('p','Reading the current recovery basis…')),close=element('button','Close');close.type='button';
  dialog.append(element('h2','Reconcile retained reader record'),reading,status,close);document.body.append(dialog);dialog.showModal();
  let alive=true,busy=false,controller=null,inspected=null;
  const fresh=()=>alive&&dialog.isConnected!==false&&isCurrent();
  const inspectInput=(handle,label)=>inspectStructuralInput(handle,{project,request,onRead,label,opener:document.activeElement,isCurrent:fresh});
  const run=async fn=>{
    if(!fresh()||busy)return;busy=true;const disabled=[...dialog.querySelectorAll('button,input,select,textarea')].map(node=>[node,node.disabled]);for(const [node]of disabled)node.disabled=true;
    try{await fn();}catch(error){if(fresh())status.textContent=error.message;}finally{busy=false;if(fresh()){for(const [node,prior]of disabled)if(node.isConnected!==false)node.disabled=prior;controller?.syncControls?.();close.disabled=false;}}
  };
  const accept=value=>{validateRestructureEffect(value,{project,prior:retained});inspected=value;controller?.destroy();reading.replaceChildren();
    controller=renderMetadataReconciliation(reading,value,{project,onRead:inspectInput,isCurrent:fresh,
      onPreview:(value,choices)=>run(async()=>{
        const submission=reconciliationSubmission(value,project,{previewAssignments:choices});
        const next=await request(submission.url,submission.payload);if(!fresh())return;
        if(!same(observationBasis(next.metadata_reconciliation?.current_observation),observationBasis(value.metadata_reconciliation.current_observation))){
          controller.blockSubmission();status.textContent='Current source or metadata changed during inspection. Adopt the refreshed recovery basis before applying.';
          const adopt=element('button','Adopt refreshed recovery basis');adopt.type='button';adopt.onclick=()=>run(async()=>{accept(next);status.textContent='Refreshed basis adopted. Inspect the retained passage mapping before reconciling.';});status.append(adopt);return;
        }
        accept(next);status.textContent=next.metadata_reconciliation.status==='READY'?'Mapping preview ready. Reconcile explicitly to record metadata only.':'Complete the remaining passage choices.';
      }),
      onReconcile:value=>run(async()=>{
        const submission=reconciliationSubmission(value,project);let result;
        try{result=await request(submission.url,submission.payload);}catch(error){if(error.result?.schema_version!==RESTRUCTURE_SCHEMA)throw error;result=error.result;}
        const observed=validateReconciliationResult(result,{project,inspected:value});if(!fresh())return;
        controller?.destroy();reading.replaceChildren();controller=renderRestructureOutcome(reading,result,{project,isCurrent:fresh,onRead:inspectInput});
        await onSaved(result);if(fresh())status.textContent=observed.complete?'Reader record reconciled. Later text was preserved; scientific review obligations remain.':'The metadata reconciliation is retained; inspect its remaining steps.';
      })});
  };
  close.onclick=()=>{if(!busy)dialog.close();};dialog.addEventListener('cancel',event=>{if(busy)event.preventDefault();});
  dialog.addEventListener('close',()=>{alive=false;controller?.destroy();dialog.remove();if(opener?.isConnected)opener.focus({preventScroll:true});});
  await run(async()=>{const value=await request(target.url,undefined,{allowStateError:true});if(fresh()){accept(value);status.textContent='Inspect the current source and retained obligations before recording metadata.';}});
  return dialog;
}

// A section keeps one compact retained operation handle. Reobserve its exact
// receipt before offering an inverse; a historical summary is never a write lease.
export async function openRecordedRestructure({project,retained,request,onRead,onSaved=async()=>{},opener,isCurrent=()=>true}={}){
  const initial=retained?.inverse_inspection_read||retained?.read_handle;
  const targetFor=(handle,reference)=>{const target=qualifiedOwnerHTTP(handle,project),payload=target?.owner?.read_handle?.payload;
    if(target?.owner?.kind!=='structure'||target.owner.view!=='restructure'||payload?.reconcile_current||
        payload?.receipt_id!==reference.receipt?.id||payload.intent_artifact_id!==reference.receipt?.intent_artifact_id||
        !same(target.owner.sectionIds,[reference.section_id]))throw Error('Inspect the exact retained structural operation in this section.');return target;};
  targetFor(initial,retained);
  const dialog=element('dialog','','spine-binding-dialog reader-logical-dialog'),body=element('section'),status=pendingRead(element('p','Reading the exact saved operation…')),close=element('button','Close');
  status.setAttribute('role','status');close.type='button';dialog.append(element('h2','Saved structural operation'),body,status,close);document.body.append(dialog);dialog.showModal();
  let alive=true,busy=false,controller=null;
  const fresh=()=>alive&&dialog.isConnected!==false&&isCurrent();
  const inspectInput=(handle,label)=>inspectStructuralInput(handle,{project,request,onRead,label,opener:document.activeElement,isCurrent:fresh});
  const run=async fn=>{if(!fresh()||busy)return;busy=true;const controls=[...dialog.querySelectorAll('button')].map(node=>[node,node.disabled]);for(const [node]of controls)node.disabled=true;
    try{await fn();}catch(error){if(fresh())status.textContent=error.message+' Inspect the latest saved operation before another inverse.';}finally{busy=false;if(fresh()){for(const [node,disabled]of controls)if(node.isConnected)node.disabled=disabled;close.disabled=false;}}};
  const readExact=async(reference,handle=reference.inverse_inspection_read||reference.read_handle)=>{
    const target=targetFor(handle,reference),value=await request(target.url,undefined,{allowStateError:true});
    validateRestructureEffect(value,{project,prior:reference});
    if(value.receipt.id!==reference.receipt.id||!['CURRENT','CHANGED','UNAVAILABLE'].includes(value.inverse_currentness?.status))throw Error('The operation owner supplied no exact current inverse observation.');
    if(value.undo_action&&value.inverse_currentness?.status!=='CURRENT')throw Error('The owner’s inverse action is not current for this saved operation.');
    return value;
  };
  const render=value=>{if(!fresh())return;controller?.destroy();body.replaceChildren();
    controller=renderRestructureOutcome(body,value,{project,isCurrent:fresh,onRead:inspectInput,
      onRecovery:(action,prior)=>run(async()=>{const submission=restructureFollowThroughSubmission(action,project,prior);let result;
        try{result=await request(submission.url,submission.payload);}catch(error){if(error.result?.schema_version!==RESTRUCTURE_SCHEMA)throw error;result=error.result;}
        validateRestructureEffect(result,{project,prior});await onSaved(result);render(await readExact(result));}),
      onInspectReconciliation:(handle,prior)=>openMetadataReconciliation({project,handle,retained:prior,request,onRead:inspectInput,opener:document.activeElement,isCurrent:fresh,
        onSaved:async result=>{await onSaved(result);render(await readExact(result));}}),
      onInverse:value.inverse_currentness?.status==='CURRENT'?(action,prior)=>run(async()=>{
        const submission=restructureFollowThroughSubmission(action,project,prior,'undo-restructure');let result;
        // Once sent, old controls stay invalid even if an acknowledgement or view read fails.
        controller?.destroy();body.replaceChildren(pendingRead(element('p','Checking the retained structural outcome…')));
        try{result=await request(submission.url,submission.payload);}catch(error){if(error.result?.schema_version!==RESTRUCTURE_SCHEMA)throw error;result=error.result;}
        const outcome=validateRestructureEffect(result,{project,prior,inverse:true});
        await onSaved(result);render(await readExact(result));if(fresh())status.textContent=outcome.complete?'Structural inverse and required records saved.':'The inverse outcome is retained. Finish only its missing record steps.';
      }):null});
    status.textContent=value.inverse_currentness?.status==='CURRENT'?'The owner rechecked this exact operation. Its guarded inverse is available.':value.undo_unavailable||value.inverse_currentness?.reason||'This older inverse is unavailable on the current source and reader basis. No text was changed.';
  };
  close.onclick=()=>{if(!busy)dialog.close();};dialog.addEventListener('cancel',event=>{if(busy)event.preventDefault();});dialog.addEventListener('close',()=>{alive=false;controller?.destroy();dialog.remove();if(isCurrent()&&opener?.isConnected)opener.focus({preventScroll:true});});
  await run(async()=>render(await readExact(retained,initial)));return dialog;
}

// Counts and exact qualification snippets come from the retained owner record.
// A bounded optional summary cannot replace or hide its source/plan receipts.
function renderDispositionSummary(host,result){
  const summary=result.disposition_summary;if(!summary)return;
  const count=value=>Number.isSafeInteger(value)&&value>=0,dispositions=['assign','retain-retired','retain-unresolved'];
  try{
    const coverage=summary.coverage,rows=summary.qualifications;
    if(summary.basis?.receipt_id!==result.receipt?.id||summary.basis.intent_artifact_id!==result.receipt?.intent_artifact_id||
        !count(summary.attachment_count)||!count(summary.occurrence_count)||!count(summary.qualification_count)||
        !dispositions.every(key=>count(summary.disposition_counts?.[key]))||Object.values(summary.disposition_counts).reduce((a,b)=>a+b,0)!==summary.attachment_count||
        !summary.category_counts||Object.values(summary.category_counts).some(value=>!count(value))||Object.values(summary.category_counts).reduce((a,b)=>a+b,0)!==summary.attachment_count||
        !Array.isArray(rows)||!Array.isArray(summary.destination_counts)||coverage?.counts_complete!==true||
        !['destinations_complete','qualifications_complete'].every(key=>typeof coverage[key]==='boolean')||
        !['omitted_destinations','omitted_qualifications','omitted_qualification_values'].every(key=>count(coverage[key]))||
        rows.length+coverage.omitted_qualifications!==summary.qualification_count||
        summary.scientific_acceptance!=='NOT_ASSERTED'||summary.old_reviews!=='HISTORICAL_ONLY')throw Error('The compact disposition summary has no matching complete count basis.');
    const panel=element('section','','reader-disposition-summary');panel.append(element('h5','Recorded attachment choices'),element('p',summary.attachment_count+' attachments · '+summary.occurrence_count+' saved passages.'));
    panel.append(element('p',summary.disposition_counts.assign+' assigned; '+summary.disposition_counts['retain-retired']+' kept with retired units; '+summary.disposition_counts['retain-unresolved']+' retained for scoped review.'));
    const categories=element('details');categories.append(element('summary','Attachment categories and destination counts'));
    for(const [kind,count]of Object.entries(summary.category_counts))categories.append(element('p',kind.replaceAll('_',' ')+' · '+count));
    for(const row of summary.destination_counts){if(!identifier(row.paragraph_id)||!count(row.attachment_count))throw Error('A compact destination count has no exact identity.');categories.append(element('p',row.paragraph_id+' · '+row.attachment_count+' attachments'));}panel.append(categories);
    const labels={assign:'Assigned', 'retain-retired':'Kept with the retired unit','retain-unresolved':'Retained for scoped review'};
    for(const row of rows){
      const text=row.value_coverage;
      if(!identifier(row.attachment_id)||!dispositions.includes(row.disposition)||!count(row.successor_count)||!Array.isArray(row.successor_ids)||row.successor_ids.some(value=>!identifier(value))||
          row.successor_ids.length>row.successor_count||typeof row.destinations_complete!=='boolean'||row.destinations_complete&&row.successor_ids.length!==row.successor_count||
          text?.unit!=='utf8-bytes'||!count(text.total)||!fingerprint(text.sha256)||typeof text.complete!=='boolean'||
          text.complete!==(typeof row.value==='string')||text.complete&&new TextEncoder().encode(row.value).length!==text.total)throw Error('An exact qualification snippet has incomplete identity or coverage.');
      panel.append(element('p',typeof row.value==='string'?'Qualification: '+row.value:'Qualification text omitted from this compact summary.'));
      panel.append(element('p',labels[row.disposition]+(row.successor_count?' · '+row.successor_count+' destination planned units.':'.'),'muted'));
      if(row.successor_ids.length){const detail=element('details');detail.append(element('summary','Exact qualification destinations'+(row.destinations_complete?'':' (partial list)')));for(const id of row.successor_ids)detail.append(element('code',id));panel.append(detail);}
    }
    if(coverage.omitted_destinations||coverage.omitted_qualifications||coverage.omitted_qualification_values)panel.append(element('p','Compact summary omits '+coverage.omitted_destinations+' destinations, '+coverage.omitted_qualifications+' qualifications and '+coverage.omitted_qualification_values+' qualification texts. Inspect the exact retained contract for full detail.','muted'));
    panel.append(element('p','These choices do not assert scientific acceptance. Earlier reviews remain historical.','muted'));host.append(panel);
  }catch(error){host.append(element('p','Compact attachment summary unavailable. The saved source and reader receipts remain inspectable. '+error.message,'muted'));}
}

// This presentation uses the two existing receipts. It never derives a pending
// step or manufactures a recovery request from source bytes or local history.
export function renderRestructureOutcome(host, result, {
  project, onRecovery = null, onRead = null,onInspectReconciliation=null,onInverse=null, isCurrent = () => true
} = {}) {
  const outcome = restructureOutcome(result, {project});
  const panel = element('section', '', 'reader-restructure-outcome');
  panel.contentEditable = 'false';panel.dataset.chrome = '';
  const status = element('p');
  status.setAttribute('role', 'status');
  const sourceLabel = !outcome.source ? 'No manuscript text change was required.' : outcome.sourceHistorical ? 'Original text change recorded.' : outcome.source.state === 'UNCHANGED' ? 'Text unchanged.' : outcome.sourceCommitted
    ? 'Text saved.' : outcome.source.state === 'ROLLED_BACK' ? 'Text change rolled back.' : 'Inspect the source outcome.';
  const planLabel = outcome.plan.acknowledged ? 'Reader-plan record saved.' : 'Reader-plan recording needs attention.';
  status.textContent = sourceLabel + ' ' + planLabel;
  panel.append(status);
  if (typeof result.error === 'string' && result.error) {
    panel.append(element('p', 'Recording reason: ' + result.error.slice(0,500), 'error'));
  }
  if (result.remaining_steps?.length) {
    const steps=result.remaining_steps.filter(value=>typeof value==='string').map(value=>value.replaceAll('-',' '));
    if(steps.length)panel.append(element('p','Remaining recording: '+steps.join('; ')+'.'));
  }
  renderDispositionSummary(panel,result);
  host.append(panel);
  let alive = true;
  const fresh = () => alive && panel.isConnected !== false && isCurrent();
  const button = (label, run) => {
    const node = element('button', label);
    node.type = 'button';
    node.onclick = async () => {
      if (!fresh() || node.disabled) return;
      node.disabled = true;
      try { await run(); }
      catch (error) { if (fresh()) status.textContent = sourceLabel + ' ' + error.message; }
      finally { if (fresh()) node.disabled = false; }
    };
    return node;
  };
  if (result.recovery_action && result.recovery_action.permitted !== false && onRecovery) {
    panel.append(button('Finish structural record', () => onRecovery(result.recovery_action, result)));
  }
  if(result.undo_action&&result.undo_action.permitted!==false&&onInverse)panel.append(button(result.undo_action.title||'Undo this structural operation',()=>onInverse(result.undo_action,result)));
  if (result.read_handle && onRead) {
    panel.append(button('Inspect structural outcome', () => onRead(result.read_handle)));
  }
  if(result.reconciliation_read&&(onInspectReconciliation||onRead))panel.append(button('Inspect current recovery basis',()=>onInspectReconciliation?
    onInspectReconciliation(result.reconciliation_read,result):onRead(result.reconciliation_read)));
  if(result.undo_unavailable||outcome.metadataReconciled)panel.append(element('p',result.undo_unavailable||'The record is settled. An exact inverse of the older operation is unavailable after retaining later edits.','muted'));
  if (result.review_obligations?.length) {
    const details = element('details');
    details.append(element('summary', result.review_obligations.length + ' scoped review obligations'));
    for (const obligation of result.review_obligations) {
      const text = typeof obligation === 'string' ? obligation : obligation.reason || obligation.message || obligation.title;
      if (text) details.append(element('p', text));
    }
    panel.append(details);
  }
  return {outcome, destroy() { alive = false; }};
}
