// PROPOSAL RESOLUTION. Purpose: resolve one proposal (a candidate revision of the text) by
// preparing, applying and finalising it against the exact owner guards. Ownership: the proposal
// owner (/proposals routes) issues the subject, target, preparation and finalisation calls;
// this module validates each shape before sending (validateResolution,
// validateResolutionPreparation, validateResolutionFinalization), builds the submissions
// (resolutionPrepareSubmission, resolutionSubmission, candidateApplicationSubmission,
// resolutionFinalizationSubmission) and reads the receipt (resolutionReceipt). Public contract:
// mountProposalResolution(host, options). Inputs: the owner's resolution value; outputs: DOM and
// receipts. Currentness: every submission carries the inspected revision; a stale one refuses at
// the owner and is shown through sourceEffectDisposition. Storage: none.
import {sourceEffectDisposition} from './source-effect.mjs';
import {pendingRead} from './pending-read.mjs';

const pin=value=>typeof value==='string'&&/^sha256:[a-f0-9]{64}$/.test(value);
const identity=value=>typeof value==='string'&&!!value.trim()&&!/[\u0000-\u001f]/.test(value);
const canonical=value=>Array.isArray(value)?value.map(canonical):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonical(value[key])])):value;
const same=(left,right)=>JSON.stringify(canonical(left))===JSON.stringify(canonical(right));
const clone=value=>structuredClone(value);
const changedInput=error=>error?.result?.status==='CHANGED_INPUT'||error?.reason==='CHANGED_INPUT'||String(error?.message||'').startsWith('CHANGED_INPUT');
const choices=new Set(['current','proposed','custom']);
const fields=['turn_id','proposal_version','candidate_ref','edit_id'];
const targetFields=['file','line_start','line_end','expected_source_digest','expected_selection'];
const el=(tag,text='',className='')=>{const node=document.createElement(tag);node.textContent=text;node.className=className;return node;};

export function resolutionSubject(value){
  if(!value||typeof value!=='object'||!identity(value.edit_id)||Object.keys(value).some(key=>!fields.includes(key)))throw Error('The resolution has no exact candidate/edit identity.');
  const original=identity(value.turn_id)&&identity(value.proposal_version)&&value.candidate_ref===undefined;
  const successor=value.turn_id===undefined&&value.proposal_version===undefined&&identity(value.candidate_ref?.id)&&pin(value.candidate_ref?.version);
  if(!original&&!successor)throw Error('The resolution mixes original and successor candidate identities.');
  return value;
}

export function resolutionTarget(value){
  if(!value||!identity(value.file)||value.file.startsWith('/')||value.file.includes('\\')||value.file.split('/').includes('..')||
    !Number.isInteger(value.line_start)||value.line_start<1||!Number.isInteger(value.line_end)||value.line_end<value.line_start||
    typeof value.before!=='string'||!pin(value.expected_source_digest)||!pin(value.expected_selection))throw Error('Choose an exact inspected current passage before resolving this candidate.');
  return value;
}

function actionPayload(action,project,decision,subject){
  const payload=action?.payload;
  if(action?.project!==project||action.operation!=='authoring/proposal-decision'||action.permitted===false||
    action.http?.method!=='POST'||action.http.url!=='/authoring/proposal-decision'||payload?.project!==project||payload.decision!==decision)throw Error('The owner supplied no matching resolution action. Reinspect the candidate.');
  if(Object.keys(payload).some(key=>!['project','decision',...fields,'resolution_token','target','input_observations'].includes(key)))throw Error('The resolution action contains fields outside its inspected contract.');
  const selected=Object.fromEntries(fields.filter(key=>payload[key]!==undefined).map(key=>[key,payload[key]]));
  resolutionSubject(selected);
  if(subject&&!same(selected,subject))throw Error('The resolution action targets a different candidate or edit.');
  return clone(payload);
}

export function resolutionPrepareSubmission(action,project,target){
  const payload=actionPayload(action,project,'prepare-resolution');
  if(target!==undefined)payload.target=clone(resolutionTarget(target));
  return {url:action.http.url,payload};
}

export function validateResolution(value,{project,subject}={}){
  if(value?.schema_version!=='laplace.proposal-resolution/1'||value.project!==project||!pin(value.resolution_token))throw Error('The resolution owner returned a different project or basis.');
  resolutionSubject(value.subject);if(subject&&!same(value.subject,subject))throw Error('The resolution belongs to a different candidate or edit.');
  resolutionTarget(value.target);
  if(['original','current','proposed'].some(key=>typeof value[key]!=='string')||value.current!==value.target.before||
    !Array.isArray(value.hunks)||!value.hunks.length||new Set(value.hunks.map(row=>row.id)).size!==value.hunks.length||
    value.hunks.some(row=>!identity(row.id)||!['proposal','current','conflict'].includes(row.kind)||row.default_choice!=='current'||['original','current','proposed'].some(key=>typeof row[key]!=='string'))||
    !value.input_observations||typeof value.input_observations!=='object'||Array.isArray(value.input_observations)||!Array.isArray(value.review_obligations))throw Error('The owner returned an incomplete current-source comparison.');
  for(const [key,decision]of [['preview','preview-resolution'],['apply','apply-resolution']]){
    const payload=actionPayload(value.actions?.[key],project,decision,value.subject);
    if(payload.resolution_token!==value.resolution_token||!same(Object.fromEntries(targetFields.map(key=>[key,payload.target?.[key]])),Object.fromEntries(targetFields.map(key=>[key,value.target[key]])))||payload.target?.before!==undefined&&payload.target.before!==value.current||!same(payload.input_observations,value.input_observations))throw Error('The resolution action does not retain the displayed source and input observations.');
  }
  return value;
}

export function validateResolutionPreparation(value,{project,subject}={}){
  if(value?.schema_version!=='laplace.proposal-resolution/1'||value.project!==project)throw Error('The resolution belongs to another project.');
  resolutionSubject(value.subject);if(subject&&!same(value.subject,subject))throw Error('The resolution belongs to another candidate or edit.');
  if(value.target_required===true){if(!Array.isArray(value.target_files))throw Error('The owner supplied no current-source target reads.');return value;}
  return validateResolution(value,{project,subject});
}

export function resolutionSubmission(value,mode,{selectedChoices,resolvedAfter}={}){
  validateResolution(value,{project:value?.project});
  if(!['preview','apply'].includes(mode))throw Error('Choose preview or apply for this resolution.');
  const action=value.actions[mode],payload=actionPayload(action,value.project,mode+'-resolution',value.subject);
  if((selectedChoices===undefined)===(resolvedAfter===undefined))throw Error('Supply either complete hunk choices or the resolved source text.');
  if(resolvedAfter!==undefined){if(typeof resolvedAfter!=='string')throw Error('Resolved source must be exact text.');payload.resolved_after=resolvedAfter;}
  else{
    if(!Array.isArray(selectedChoices)||selectedChoices.length!==value.hunks.length||new Set(selectedChoices.map(row=>row.hunk_id)).size!==selectedChoices.length||
      selectedChoices.some(row=>!value.hunks.some(hunk=>hunk.id===row.hunk_id)||!choices.has(row.choice)||Object.keys(row).some(key=>!['hunk_id','choice','text'].includes(key))||
        row.choice==='custom'&&typeof row.text!=='string'||row.choice!=='custom'&&row.text!==undefined))throw Error('Every owner-issued hunk needs exactly one current, proposed or custom choice.');
    payload.choices=clone(selectedChoices);
  }
  return {url:action.http.url,payload};
}

export function resolutionAuthorLabel(author){
  if(author?.kind==='human')return 'Human-authored revision';
  if(author?.kind==='agent')return 'Agent-authored revision'+(author.role?' · '+author.role:author.mode?' · '+author.mode:'')+(author.turn_id?' · '+author.turn_id:'');
  return 'Resolved revision · authorship not recorded';
}

export function resolutionReceipt(result,{project,subject}={}){
  if(result?.project!==project||!identity(result.candidate_ref?.id)||!pin(result.candidate_ref?.version))return null;
  if(subject&&!same(Object.fromEntries(fields.filter(key=>result.predecessor?.[key]!==undefined).map(key=>[key,result.predecessor[key]])),subject))throw Error('The resolved revision receipt names a different predecessor. Reinspect its exact candidate.');
  const effect=sourceEffectDisposition(result,{project});
  return {candidate:result.candidate_ref,applied:result.application?.complete===true&&(!effect||effect.acknowledged),
    author:result.author,disposition:result.disposition,application:result.application,effect,read:result.read_handle,apply:result.apply_action,obligations:result.review_obligations||[]};
}

export function candidateApplicationSubmission(action,project,ref){
  if(action?.project!==project||action.operation!=='authoring/proposal-decision'||action.permitted===false||action.http?.method!=='POST'||action.http.url!=='/authoring/proposal-decision'||
    action.payload?.project!==project||action.payload.decision!=='apply-candidate'||!same(action.payload.candidate_ref,ref)||Object.keys(action.payload).some(key=>!['project','decision','candidate_ref'].includes(key)))throw Error('The owner supplied no matching resolved candidate application action.');
  return {url:action.http.url,payload:clone(action.payload)};
}

export function resolutionFinalizationSubmission(action,project,ref,disposition){
  const payload=action?.payload;
  if(disposition?.status!=='PENDING'||!same(disposition.successor_ref,ref)||!identity(disposition.resolution_application_id)||
    action?.project!==project||action.operation!=='authoring/proposal-decision'||action.permitted!==true||action.recovery_kind!=='finalize-predecessor-only'||
    action.http?.method!=='POST'||action.http.url!=='/authoring/proposal-decision'||payload?.project!==project||payload.decision!=='finish-resolution-record'||
    !same(payload.candidate_ref,ref)||payload.resolution_application_id!==disposition.resolution_application_id||!same(payload.predecessor,disposition.predecessor)||
    Object.keys(payload).some(key=>!['project','decision','candidate_ref','resolution_application_id','predecessor'].includes(key)))throw Error('The owner supplied no matching reconciliation-record recovery. Reinspect the saved revision.');
  const predecessor=clone(disposition.predecessor||{});delete predecessor.record_id;resolutionSubject(predecessor);
  if(!identity(disposition.predecessor.record_id))throw Error('The recovery has no exact recorded predecessor.');
  return {url:action.http.url,payload:clone(payload)};
}

export function validateResolutionFinalization(result,{project,ref,disposition}={}){
  if(result?.project!==project||result.metadata_only!==true||!same(result.candidate_ref,ref)||result.disposition?.status!=='RECORDED'||
    !same(result.disposition.successor_ref,ref)||result.disposition.resolution_application_id!==disposition.resolution_application_id||
    !same(result.disposition.predecessor,disposition.predecessor))throw Error('The reconciliation record was not confirmed for this saved revision. Reinspect its exact owner receipt before another action.');
  return result;
}

function styles(){
  if(document.querySelector('[data-proposal-resolution-style]'))return;
  const link=el('link');link.rel='stylesheet';link.href='/shared/proposal-resolution.css';link.dataset.proposalResolutionStyle='';document.head.append(link);
}

// This state contains authored choices only. All source, hunk and application
// authority comes from the inspected owner response and its exact actions.
// APPROVAL (M5 2026-10-16, WORK-editor-human-change-approval-20261015): with `approve`, the primary action is
// "Approve change": the proposal's own hunks take the proposed text, hunks the author changed after the suggestion keep
// the current text, and a genuinely overlapping (conflict) hunk waits for the author's explicit choice. It runs the
// owner's exact preview then apply once; nothing is forced, renewed or scientifically accepted.
export function approvalChoices(value,choices={}){
  return value.hunks.map(hunk=>{const chosen=choices[hunk.id];if(chosen)return {hunk_id:hunk.id,choice:chosen.choice,...(chosen.choice==='custom'?{text:chosen.text??''}:{})};
    return hunk.kind==='proposal'?{hunk_id:hunk.id,choice:'proposed'}:hunk.kind==='current'?{hunk_id:hunk.id,choice:'current'}:null;});
}

export function mountProposalResolution(host,{project,value,state={},request,storage=null,storageKey=null,isCurrent=()=>true,
  renderPreview=null,onApplied=()=>{},onReadCandidate=null,onFinishResolution=null,onChanged=()=>{},onRefresh=null,approve=false}={}){
  validateResolution(value,{project});styles();
  let current=value,alive=true,busy=false,revision=0,preview=null,receipt=null;
  const fresh=()=>alive&&host.isConnected!==false&&isCurrent();
  if(storage&&storageKey&&!state.loaded){try{const saved=JSON.parse(storage.getItem(storageKey)||'null');if(saved?.schema_version==='laplace.proposal-resolution-draft/1')Object.assign(state,saved);}catch{}state.loaded=true;}
  state.schema_version='laplace.proposal-resolution-draft/1';state.resolution_token??=current.resolution_token;state.input_observations??=clone(current.input_observations);state.choices??={};state.hunk_ids??=Object.keys(state.choices).length?[]:current.hunks.map(hunk=>hunk.id);state.index??=0;state.active_hunk_id??=current.hunks[state.index]?.id;state.view??='current';
  const stale=()=>!!state.needs_inspection||state.resolution_token!==current.resolution_token||!same(state.input_observations,current.input_observations)||!same(state.hunk_ids,current.hunks.map(hunk=>hunk.id));
  const save=()=>{try{if(storage&&storageKey)storage.setItem(storageKey,JSON.stringify(state));}catch{note.textContent='Draft storage is unavailable. Your choices remain in this open review.';}onChanged(state);};
  const selected=()=>current.hunks.map(hunk=>{const choice=state.choices[hunk.id]||{choice:hunk.default_choice};return {hunk_id:hunk.id,choice:choice.choice,...(choice.choice==='custom'?{text:choice.text??''}:{})};});
  const submission=mode=>resolutionSubmission(current,mode,state.full_text?{resolvedAfter:state.resolved_after??''}:{selectedChoices:selected()});
  const signature=()=>JSON.stringify([current.resolution_token,state.full_text?state.resolved_after:selected()]);
  const panel=el('section','','proposal-resolution'),heading=el('h3','Resolve with current source'),note=el('p','','proposal-resolution-status'),body=el('section'),result=el('section'),controls=el('div','','proposal-resolution-actions');
  note.setAttribute('role','status');host.append(panel);panel.append(heading,note,body,result,controls);
  const button=(label,run)=>{const node=el('button',label);node.type='button';node.onclick=async()=>{if(!fresh()||busy)return;try{await run();}catch(error){if(fresh())note.textContent=error.message;}};return node;};
  const canApply=()=>!busy&&!stale()&&!receipt&&preview?.value.changed!==false&&preview?.signature===signature();
  const runPreview=async()=>{
    if(stale())throw Error('Review the refreshed comparison and explicitly use its basis first. Your earlier choices are retained.');
    const sent=submission('preview'),sentSignature=signature(),sentRevision=revision;busy=true;paintPermissions();note.textContent='Preparing the resolved preview…';
    try{
      const observed=await request(sent.url,sent.payload);validateResolution(observed,{project,subject:current.subject});
      if(observed.resolution_token!==current.resolution_token||typeof observed.resolved_after!=='string')throw Error('The resolved preview does not match the inspected source. Refresh the comparison.');
      if(!fresh())return;
      if(sentRevision!==revision){note.textContent='The preview belongs to earlier choices. Your newer choices are retained.';return;}
      preview={value:observed,signature:sentSignature};result.replaceChildren(el('h4','Resolved preview'));
      if(renderPreview)await renderPreview(result,observed);else result.append(el('pre',observed.resolved_after,'proposal-resolution-source'));
      if(fresh())note.textContent=observed.changed===false?'Resolved text matches current source. No application is needed.':'Preview ready. Apply resolved revision changes the inspected current source.';
    }catch(error){if(changedInput(error)){state.needs_inspection=true;preview=null;save();if(fresh())paint();}throw error;}finally{busy=false;if(fresh())paintPermissions();}
  };
  const previewButton=button('Preview resolved text',runPreview);
  const runApply=async()=>{
    if(!canApply())throw Error('Preview these exact choices before applying them.');
    const sent=submission('apply'),sentRevision=revision,subject=clone(current.subject);busy=true;paintPermissions();note.textContent='Applying the resolved revision…';
    try{
      let observed;
      try{observed=await request(sent.url,sent.payload);}catch(error){const retained=resolutionReceipt(error.result||error.body,{project,subject});if(retained){receipt=retained;if(fresh())paintReceipt();}else if(changedInput(error)){state.needs_inspection=true;preview=null;save();if(fresh())paint();}throw error;}
      const retained=resolutionReceipt(observed,{project,subject});if(!retained)throw Error('Application returned no exact resolved candidate receipt. Reinspect before another action.');
      receipt=retained;
      if(!fresh())return;
      if(retained.applied&&revision===sentRevision){state.choices={};state.resolved_after='';try{if(storage&&storageKey)storage.removeItem(storageKey);}catch{}onChanged(state);}
      paintReceipt();await onApplied(observed,{...retained,newerDraft:revision!==sentRevision});
      if(fresh()&&revision!==sentRevision)note.textContent+=' Your newer local choices remain retained.';
    }finally{busy=false;if(fresh())paintPermissions();}
  };
  const applyButton=button('Apply resolved revision',runApply);
  const unresolved=()=>state.full_text?[]:current.hunks.filter(hunk=>hunk.kind==='conflict'&&!state.choices[hunk.id]);
  const approveButton=approve?button('Approve change',async()=>{
    if(stale())throw Error('Review the refreshed comparison and explicitly use its basis first. Your earlier choices are retained.');
    const open=unresolved();if(open.length)throw Error('Choose what to keep for '+(open.length===1?'the overlapping change':'each of the '+open.length+' overlapping changes')+' before approving.');
    if(!state.full_text){const chosen=approvalChoices(current,state.choices);let moved=false;for(const row of chosen){const prior=state.choices[row.hunk_id];
      if(!prior||prior.choice!==row.choice||prior.text!==row.text){state.choices[row.hunk_id]={choice:row.choice,...(row.choice==='custom'?{text:row.text}:{})};moved=true;}}if(moved)changed();}
    if(preview?.signature!==signature())await runPreview();
    if(!fresh()||!preview||preview.signature!==signature())return;
    if(preview.value.changed===false){note.textContent='The approved text already matches the current source; nothing was applied.';return;}
    await runApply();
  }):null;
  if(approveButton)approveButton.className='primary';
  controls.append(...(approveButton?[approveButton]:[]),previewButton,applyButton);
  function paintPermissions(){previewButton.disabled=busy||stale()||!!receipt;applyButton.disabled=!canApply();
    if(approveButton){approveButton.disabled=busy||stale()||!!receipt||unresolved().length>0;approveButton.textContent=state.full_text?'Approve edited text':'Approve change';}}
  function paintReceipt(){
    result.replaceChildren(el('h4',receipt.applied?'Resolved revision applied':'Resolved revision retained'),el('p',resolutionAuthorLabel(receipt.author)));
    note.textContent=receipt.applied?'Resolved revision applied. Scientific review obligations remain separate.':'The resolved revision was retained; source application is not confirmed. Inspect it before recovering.';
    if(receipt.read&&onReadCandidate)result.append(button('Read resolved revision',()=>onReadCandidate(receipt.read,receipt.candidate)));
    if(receipt.disposition?.status==='PENDING'){result.append(el('p','The text is saved. Only the record resolving its predecessor remains to be finished.'));if(receipt.disposition.recovery_action&&onFinishResolution)result.append(button('Finish reconciliation record',()=>onFinishResolution(receipt.disposition.recovery_action,receipt.candidate,receipt.disposition)));}
    if(receipt.obligations.length){const details=el('details');details.append(el('summary','Remaining review obligations'));for(const item of receipt.obligations)details.append(el('p',typeof item==='string'?item:item.reason||item.message||JSON.stringify(item)));result.append(details);}
  }
  function changed(){revision++;preview=null;result.replaceChildren();save();paintPermissions();}
  function paint(){
    body.replaceChildren();
    if(stale()){
      const warning=el('p',state.needs_inspection?'Source changed. Refresh the comparison; your earlier choices and custom text are retained.':'The inspected source, supporting inputs or comparison regions changed. Your earlier choices and custom text are retained.','proposal-resolution-warning');body.append(warning);
      if(!state.needs_inspection){const adopt=button('Use this inspected comparison',()=>{state.retained_choices={...(state.retained_choices||{}),...clone(state.choices)};state.choices=Object.fromEntries(current.hunks.filter(hunk=>Object.hasOwn(state.choices,hunk.id)).map(hunk=>[hunk.id,clone(state.choices[hunk.id])]));state.resolution_token=current.resolution_token;state.hunk_ids=current.hunks.map(hunk=>hunk.id);state.input_observations=clone(current.input_observations);state.full_text=false;changed();paint();note.textContent='Using the comparison you inspected. Choices for unchanged changes are preserved; inspect changed passages and preview before applying.';});body.append(adopt);}
    }
    if(approve){
      // the specific conflict, in ordinary language: what approval will keep, take and wait for
      const kinds=kind=>current.hunks.filter(hunk=>hunk.kind===kind).length,overlap=kinds('conflict'),later=kinds('current'),open=unresolved().length;
      if(overlap)body.append(el('p',(overlap===1?'One change overlaps':overlap+' changes overlap')+' manuscript edits made after this suggestion. '+(open?'Choose Keep current, Use proposed or Custom for '+(open===1?'it':'each of them')+' before approving.':'Your choices are set; Approve change applies them once.'),'proposal-resolution-warning'));
      if(later)body.append(el('p',(later===1?'One later manuscript edit':later+' later manuscript edits')+' outside the suggestion '+(later===1?'is kept as it is.':'are kept as they are.'),'proposal-resolution-status'));
      if(current.review_obligations.length)body.append(el('p','Supporting inputs changed since this suggestion. Approving decides the displayed text only; it does not renew that evidence or record scientific acceptance.','proposal-resolution-warning'));
    }
    if(current.comparison?.scope==='coarse'||current.hunks.some(hunk=>hunk.comparison_scope==='coarse'))body.append(el('p','Some changes are grouped to keep this comparison responsive. You can choose or write custom text for each group, or edit the complete resolved source.','proposal-resolution-status'));
    if(state.retained_choices&&Object.keys(state.retained_choices).length){const held=el('details');held.append(el('summary','Retained earlier choices'));for(const [id,choice]of Object.entries(state.retained_choices))held.append(el('p',id+' · '+choice.choice),...(choice.text!==undefined?[el('pre',choice.text,'proposal-resolution-source')]:[]));body.append(held);}
    const navigation=el('div','','proposal-resolution-navigation'),position=el('strong');const selectedIndex=current.hunks.findIndex(hunk=>hunk.id===state.active_hunk_id);state.index=selectedIndex>=0?selectedIndex:Math.max(0,Math.min(current.hunks.length-1,state.index));state.active_hunk_id=current.hunks[state.index].id;
    const navigate=step=>{state.index=(state.index+step+current.hunks.length)%current.hunks.length;state.active_hunk_id=current.hunks[state.index].id;save();paint();};navigation.append(button('Previous change',()=>navigate(-1)),position,button('Next change',()=>navigate(1)));position.textContent=(current.hunks[state.index].comparison_scope==='coarse'?'Change group ':'Change ')+(state.index+1)+' of '+current.hunks.length;body.append(navigation);
    const hunk=current.hunks[state.index],views=el('div','','proposal-resolution-views'),source=el('pre','','proposal-resolution-source');
    const paintSource=()=>{source.textContent=hunk[state.view]||'[Empty passage]';for(const node of views.children)node.setAttribute('aria-pressed',String(node.dataset.view===state.view));};
    for(const [key,label]of [['original','Original'],['current','Current'],['proposed','Proposed']]){const node=button(label,()=>{state.view=key;save();paintSource();});node.dataset.view=key;views.append(node);}body.append(views,source);paintSource();
    const choice=state.choices[hunk.id]||{choice:hunk.default_choice},selection=el('div','','proposal-resolution-choices');selection.setAttribute('role','group');selection.setAttribute('aria-label','Choice for this change');
    for(const [key,label]of [['current','Keep current'],['proposed','Use proposed'],['custom','Custom']]){
      const node=button(label,()=>{if(stale())throw Error('Use the inspected comparison before changing its choices.');state.choices[hunk.id]={choice:key,...(key==='custom'?{text:state.choices[hunk.id]?.text??hunk.current}:{})};state.full_text=false;changed();paint();});node.setAttribute('aria-pressed',String(choice.choice===key));selection.append(node);
    }body.append(selection);
    if(choice.choice==='custom'){
      const editor=el('textarea');editor.value=choice.text??'';editor.setAttribute('aria-label','Custom text for this change');editor.spellcheck=false;
      editor.oninput=()=>{state.choices[hunk.id]={choice:'custom',text:editor.value};state.caret={hunk_id:hunk.id,start:editor.selectionStart,end:editor.selectionEnd};changed();};
      editor.onselect=()=>{state.caret={hunk_id:hunk.id,start:editor.selectionStart,end:editor.selectionEnd};save();};
      body.append(editor);if(state.caret?.hunk_id===hunk.id)editor.setSelectionRange?.(state.caret.start,state.caret.end);
    }
    const full=el('details');full.open=!!state.full_text||!!state.editing_suggestion;full.append(el('summary',state.full_text?'Complete resolved source is in use':'Edit the complete resolved source'));
    // Edit suggestion starts from the proposal itself when nothing changed beside it; otherwise from the current source
    const seed=approve&&state.editing_suggestion&&current.hunks.every(hunk=>hunk.kind==='proposal')?current.proposed:current.current;
    const complete=el('textarea');complete.value=state.resolved_after??preview?.value.resolved_after??seed;complete.setAttribute('aria-label','Complete resolved source');complete.spellcheck=false;
    complete.oninput=()=>{state.full_text=true;state.resolved_after=complete.value;full.querySelector('summary').textContent='Complete resolved source is in use';changed();};full.append(complete);body.append(full);
    if(current.review_obligations.length){const obligations=el('details');obligations.append(el('summary','Source and supporting review'));for(const item of current.review_obligations)obligations.append(el('p',typeof item==='string'?item:item.reason||item.message||JSON.stringify(item)));body.append(obligations);}
    if(approve&&!state.full_text&&!state.editing_suggestion)body.append(button('Edit suggestion',()=>{state.editing_suggestion=true;save();paint();body.querySelector?.('details textarea')?.focus?.();}));
    if(onRefresh)body.append(button('Refresh comparison',async()=>{const next=await onRefresh();if(next&&fresh()){current=validateResolution(next,{project,subject:current.subject});state.needs_inspection=false;preview=null;paint();}}));
    paintPermissions();
  }
  paint();
  return {value:()=>current,state,refresh(next){current=validateResolution(next,{project,subject:current.subject});state.needs_inspection=false;preview=null;paint();},destroy(){alive=false;},get hasDraft(){return Object.keys(state.choices).length>0||!!state.full_text;}};
}

export function mountResolutionTarget(host,{project,value,request,onTarget,isCurrent=()=>true,onCancel=()=>{}}={}){
  if(value?.schema_version!=='laplace.proposal-resolution/1'||value.project!==project||value.target_required!==true||!Array.isArray(value.target_files))throw Error('The owner supplied no current-source target selection.');
  resolutionSubject(value.subject);styles();
  let alive=true,generation=0,observed=null,selected=null;
  const fresh=()=>alive&&host.isConnected!==false&&isCurrent();
  const panel=el('section','','proposal-resolution'),title=el('h3','Choose the current passage'),note=el('p',value.reason||'Select the passage this revision should now address.');note.setAttribute('role','status');
  const file=el('select'),source=el('textarea'),selection=el('p','','proposal-resolution-status'),use=el('button','Use selected current passage'),refresh=el('button','Refresh current file'),cancel=el('button','Cancel passage selection');
  file.setAttribute('aria-label','Current source file');source.setAttribute('aria-label','Inspect and select current source');source.readOnly=true;source.spellcheck=false;use.type=refresh.type=cancel.type='button';use.disabled=refresh.disabled=true;
  const placeholder=el('option','Choose a current source file');placeholder.value='';file.append(placeholder);
  for(const row of value.target_files){if(!identity(row.file))throw Error('The current source file has no exact identity.');const option=el('option',row.label||row.file);option.value=row.file;file.append(option);}
  const lines=el('div','','proposal-resolution-lines'),startLabel=el('label','Start line'),endLabel=el('label','End line'),startLine=el('input'),endLine=el('input');
  for(const input of [startLine,endLine]){input.type='number';input.min='1';input.step='1';input.disabled=true;}
  startLine.setAttribute('aria-label','Start source line');endLine.setAttribute('aria-label','End source line');startLabel.append(startLine);endLabel.append(endLine);lines.append(startLabel,endLabel);
  panel.append(title,note,file,lines,source,selection,use,refresh,cancel);host.append(panel);
  const choose=()=>{
    selected=null;use.disabled=true;selection.textContent='Select the complete current passage to resolve.';
    if(!observed||source.selectionStart===source.selectionEnd)return;
    const text=observed.content,start=text.lastIndexOf('\n',Math.max(0,source.selectionStart-1))+1;
    const after=text.indexOf('\n',Math.max(source.selectionStart,source.selectionEnd-1)),end=after<0?text.length:after;
    selected={file:observed.file,line_start:text.slice(0,start).split('\n').length,line_end:text.slice(0,end).split('\n').length,
      before:text.slice(start,end),expected_source_digest:observed.expected_source_digest,expected_selection:observed.selection_identity};
    resolutionTarget(selected);startLine.value=String(selected.line_start);endLine.value=String(selected.line_end);selection.textContent='Selected source lines '+selected.line_start+'–'+selected.line_end+'.';use.disabled=false;
  };
  const chooseLines=()=>{
    selected=null;use.disabled=true;if(!observed)return;
    const rows=observed.content.split('\n'),lo=Number(startLine.value),hi=Number(endLine.value);
    if(!Number.isInteger(lo)||!Number.isInteger(hi)||lo<1||hi<lo||hi>rows.length){selection.textContent='Choose source lines from 1 to '+rows.length+', with the end at or after the start.';return;}
    const start=lo===1?0:rows.slice(0,lo-1).join('\n').length+1,end=start+rows.slice(lo-1,hi).join('\n').length;
    source.setSelectionRange?.(start,end);source.selectionStart=start;source.selectionEnd=end;
    selected={file:observed.file,line_start:lo,line_end:hi,before:rows.slice(lo-1,hi).join('\n'),expected_source_digest:observed.expected_source_digest,expected_selection:observed.selection_identity};
    resolutionTarget(selected);selection.textContent='Selected source lines '+lo+'–'+hi+'.';use.disabled=false;
  };
  startLine.oninput=endLine.oninput=chooseLines;
  const read=async()=>{
    const row=value.target_files.find(row=>row.file===file.value);if(!row)return;
    const base=globalThis.location?.href||'http://localhost/',url=new URL(row.read?.http?.url||'',base),q=url.searchParams;
    if(row.read?.http?.method!=='GET'||url.origin!==new URL(base).origin||url.pathname!=='/projection/tex'||q.get('corpus')!==project||q.get('file')!==row.file||q.get('view')!=='source'||[...q.keys()].some(key=>!['corpus','file','view'].includes(key)||q.getAll(key).length!==1))throw Error('The owner supplied a different source reading route.');
    const ticket=++generation;observed=selected=null;source.value='';startLine.value=endLine.value='';startLine.disabled=endLine.disabled=true;use.disabled=refresh.disabled=true;pendingRead(note,'Reading current source…');
    try{const next=await request(url.pathname+url.search);if(!fresh()||ticket!==generation)return;
      if(next.schema_version!=='laplace.projection-source/1'||next.file!==row.file||typeof next.content!=='string'||!pin(next.expected_source_digest)||!pin(next.selection_identity))throw Error('The current source observation changed its file or document identity.');
      observed=next;source.value=next.content;source.setSelectionRange?.(0,0);startLine.max=endLine.max=String(next.content.split('\n').length);startLine.disabled=endLine.disabled=false;note.textContent='Current source inspected · '+startLine.max+' lines. Enter the passage’s line range or select its text; this does not change source or message context.';refresh.disabled=false;choose();
    }catch(error){if(fresh()&&ticket===generation)note.textContent=error.message;}
  };
  file.onchange=()=>read().catch(error=>{if(fresh())note.textContent=error.message;});source.onselect=choose;source.onkeyup=choose;source.onmouseup=choose;
  refresh.onclick=()=>read().catch(error=>{if(fresh())note.textContent=error.message;});
  use.onclick=async()=>{if(!fresh()||!selected)return;use.disabled=true;try{await onTarget(clone(selected));}catch(error){if(fresh()){note.textContent=error.message;use.disabled=false;}}};
  cancel.onclick=()=>{if(fresh())onCancel();};
  return {destroy(){alive=false;generation++;},selection:()=>selected};
}
