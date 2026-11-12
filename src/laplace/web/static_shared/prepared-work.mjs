// DISPATCH LADDER AND PREPARED WORK. Validates the continuation/dispatch owners' descriptors
// (parentContinuation, child rows, synthesis and cancellation submissions) and paints them as
// the shared coordinationLadder: parent, children, returns, synthesis, recovery; prepared
// storyboard Work with its run action. It reads nothing by itself and infers no completion.
import {qualifiedOwnerHTTP, artifactHumanTarget} from './writing-owner-read.mjs';
import {coordinationLadder, continuationChip, childChip, objectHeader, actionRow, ownerStateWord} from './workspace-presentation.mjs';

const pin = value => typeof value === 'string' && /^sha256:[0-9a-f]{64}$/.test(value);
const same = (left, right) => JSON.stringify(left) === JSON.stringify(right);

const continuationPhases=['WAITING','READY','OBSERVATION_EXPIRED','PARENT_STOPPED','STALE','BLOCKED'];
const identifier=value=>typeof value==='string'&&!!value&&value===value.trim()&&!/[\u0000-\u001f]/.test(value);
function continuationArtifact(artifact,project){
  const read=artifactHumanTarget(artifact?.human_read?.url,{project});
  if(!read||read.artifactId!==artifact.id||String(read.expectedSha256||'').replace(/^sha256:/,'')!==String(artifact.revision||'').replace(/^sha256:/,''))throw Error('The continuation artifact has no matching retained identity. Reinspect its dispatch.');
  return read;
}
export function parentContinuation(value,{project,sessionId=null,turnId=null}={}){
  if(value==null)return null;
  const ids=['session_id','turn_id','origin_parent_session_id','origin_parent_turn_id','generation','dispatch_id'];
  if(value.schema_version!=='laplace.dispatch-continuation/1'||value.project!==project||
    !ids.every(key=>identifier(value[key]))||sessionId&&value.session_id!==sessionId||turnId&&value.turn_id!==turnId||
    value.work_id!==null&&!identifier(value.work_id)||!continuationPhases.includes(value.phase)||
    typeof value.execution_settled!=='boolean'||!Number.isSafeInteger(value.children_active)||value.children_active<0||
    typeof value.execution_state!=='string'||typeof value.review_state!=='string'||
    value.cancel_scope!=='parent-observation'||value.child_custody!=='detached-supervised'||
    value.parent_active!==undefined&&typeof value.parent_active!=='boolean'||
    !Array.isArray(value.readable_returns)||typeof value.synthesis?.required!=='boolean'||
    !['NOT_REQUIRED','MISSING','INVALID','VALID'].includes(value.synthesis.status)||
    value.synthesis.attachment!==undefined&&!['ATTACHED','MISSING','UNCONFIRMED'].includes(value.synthesis.attachment))throw Error('The parent continuation does not match its inspected execution. Reinspect the recorded parent.');
  for(const key of ['dispatch_deadline_at','observation_deadline_at'])if(value[key]!==null&&(!Number.isFinite(value[key])||value[key]<=0))throw Error('The continuation owner returned an invalid deadline.');
  const dispatch=qualifiedOwnerHTTP(value.dispatch_read,project)?.owner;
  if(dispatch?.kind!=='work'||dispatch.id!==value.dispatch_id)throw Error('The continuation has no exact dispatch reading route.');
  if(value.work_id){const work=qualifiedOwnerHTTP(value.work_read,project)?.owner;if(work?.kind!=='work'||work.id!==value.work_id)throw Error('The continuation has no exact parent Work reading route.');}
  else if(value.work_read!==undefined)throw Error('The continuation assigned Work without an admitted target.');
  for(const row of value.readable_returns){
    if(!identifier(row.packet)||!['worker','judge'].includes(row.role))throw Error('A continuation return has no declared packet identity.');
    if(row.status==='UNAVAILABLE'){
      if(row.artifact||!identifier(row.return_path)||typeof row.reason!=='string')throw Error('An unavailable return has no owner diagnostic.');
    }else continuationArtifact(row.artifact,project);
  }
  if(value.synthesis.artifact)continuationArtifact(value.synthesis.artifact,project);
  if(value.synthesis.status==='VALID'&&!value.synthesis.artifact)throw Error('The retained synthesis has no exact artifact reading route.');
  if(value.synthesis.retained_status!=null&&!['COMPLETE','BLOCKED','INCOMPLETE','INTERRUPTED','DEMONSTRATED-IMPOSSIBILITY'].includes(value.synthesis.retained_status))throw Error('The synthesis owner returned an unknown goal standing.');
  if(value.synthesis.errors!==undefined&&(!Array.isArray(value.synthesis.errors)||value.synthesis.errors.some(item=>typeof item!=='string')))throw Error('The synthesis owner returned an invalid diagnostic.');
  if(value.child_outcomes!==undefined&&(!Array.isArray(value.child_outcomes)||value.child_outcomes.length>8))throw Error('The continuation owner returned an invalid child outcome scope.');
  if(value.reason!=null&&typeof value.reason!=='string')throw Error('The continuation owner returned an invalid reason.');
  if(value.connected_observation!=null&&
    (value.connected_observation.schema_version!=='laplace.connected-observation/1'||!Number.isSafeInteger(value.connected_observation.admitted_seconds)||value.connected_observation.admitted_seconds<=0))throw Error('The continuation has no matching admitted observation budget.');
  if(value.recovery!=null&&(value.recovery.mode!=='explicit-parent-send'||value.recovery.automatic!==false||
    value.recovery.session_id!==value.origin_parent_session_id||value.recovery.origin_parent_turn_id!==value.origin_parent_turn_id))throw Error('Continuation recovery does not match the recorded parent.');
  return value;
}
export function parentContinuationLabel(value){
  if(value.phase==='WAITING')return 'Parent waiting for dispatched work.';
  if(value.phase==='READY'){
    const settled=value.review_state==='REJECTED'?'Dispatch settled with rejected review; ':value.execution_state!=='COMPLETE'?'Dispatch execution settled with missing or failed evidence; ':'Dispatch settled; ';
    return settled+(value.synthesis?.status==='VALID'?
      value.synthesis.attachment==='UNCONFIRMED'?'synthesis retained, but Work attachment is unconfirmed.':'parent synthesis retained. Work acceptance remains separate.':'parent synthesis is needed.');
  }
  if(value.phase==='OBSERVATION_EXPIRED')return 'Connected wait ended; dispatched work is retained.';
  if(value.phase==='PARENT_STOPPED')return 'Parent observation stopped; dispatched work has separate standing.';
  if(value.phase==='STALE')return 'Continuation inputs changed; inspect before proceeding.';
  if(value.phase==='BLOCKED')return 'Parent continuation needs recovery.';
  return 'Parent continuation needs reinspection.';
}
// Work and continuation read the same bounded child projection. Neither reader
// infers completion or publication permission from a provider's final reply.
// Each child becomes one ladder row: who (packet · role), its owner-reported state,
// the outcome facts, its errors, and the exact drilldowns the owner issued.
export function dispatchChildRows(children,{project,onTurn,onConversation,onOwner,settingsText=()=>'',status=()=>{}}={}){
  const onError=error=>status(error.message,true),rows=[];
  for(const child of children||[]){
    if(!identifier(child.packet)||!['worker','judge'].includes(child.role)||child.failure_summary!==undefined&&typeof child.failure_summary!=='string'||child.failure_count!==undefined&&(!Number.isSafeInteger(child.failure_count)||child.failure_count<0))throw Error('The dispatch returned an invalid child identity. Reinspect its Work owner.');
    const facts=[],errors=[],actions=[];
    if(child.reply_status)facts.push('Provider reply: '+ownerStateWord('reply',child.reply_status).words+' · typed return: '+(child.return_exists?'retained':'missing'));
    if(child.verdict)facts.push('Recorded verdict: '+(child.verdict.accepted?'accepted':'not accepted')+(child.review_exact?' · exact current return':' · historical/unverified exact return'));
    if(child.execution?.dependency_state)facts.push('Execution dependencies: '+ownerStateWord('dependency',child.execution.dependency_state).words.toLowerCase());
    if(child.terminal_error)errors.push(typeof child.terminal_error==='string'?child.terminal_error:JSON.stringify(child.terminal_error));
    for(const error of child.return_errors||[])errors.push(String(error));
    if(child.failure_summary)errors.push((child.failure_count?'Recorded tool failure: ':'')+child.failure_summary);
    if(child.reply_excerpt)facts.push('Recorded child reply: '+child.reply_excerpt);
    if(child.return_path)facts.push('Declared return: '+child.return_path);
    const settings=settingsText({...child.provider_settings,tier:child.tier,model_source:child.model_source});if(settings)facts.push(settings);
    if(onTurn&&identifier(child.turn_id)){
      if(child.failure_count)actions.push({label:'Read '+child.packet+' failed attempts',run:()=>onTurn(child.turn_id,{focusView:'failures'}),onError});
      actions.push({label:'Read '+child.packet+' exact turn',run:()=>onTurn(child.turn_id),onError});
    }
    if(onConversation&&identifier(child.session_id))actions.push({label:'Open '+child.packet+' conversation',run:()=>onConversation(child.session_id),onError});
    if(child.publication_read&&onOwner){const target=qualifiedOwnerHTTP(child.publication_read,project)?.owner;if(target?.kind!=='current-help'||target.turnId!==child.turn_id)throw Error('The child publication contract has mismatched reading coordinates.');actions.push({label:'Inspect '+child.packet+' return publication',run:()=>onOwner(target,'Child return publication contract'),onError});}
    // the chip is the one table's word and shape (childChip); the exact owner constant is its title
    const chip=childChip(child),owned=ownerStateWord('dispatch-child',child.state);chip.label=child.state?owned.shape+' '+owned.words:chip.label;if(child.state)chip.title='Owner state: '+owned.exact;
    rows.push({role:'child',who:child.packet+' · '+child.role,chip,facts,errors,actions});
  }
  return rows;
}
export function renderDispatchChildren(host,children,options={}){
  return coordinationLadder(host,{rows:dispatchChildRows(children,options)});
}
export function parentSynthesisSubmission(value,project){
  const action=value?.synthesis?.attach_action,payload=action?.payload;
  const target=qualifiedOwnerHTTP(action?.target_work_read,project)?.owner;
  const allowed=['project','id','status','expected_work_scope_revision','expected_work_status_revision','expected_dependency_revision','evidence','summary'];
  if(value?.project!==project||value.synthesis.status!=='VALID'||value.synthesis.attachment==='ATTACHED'||
    action?.operation!=='task_status'||action.project!==project||action.permitted!==true||
    action.http?.method!=='POST'||action.http.url!=='/work/transition'||
    target?.kind!=='work'||![value.work_id,value.dispatch_id].includes(target.id)||
    !payload||Object.keys(payload).some(key=>!allowed.includes(key))||payload.project!==project||payload.id!==target.id||
    payload.status!==(value.synthesis.retained_status==='COMPLETE'?'done':'blocked')||
    !['expected_work_scope_revision','expected_work_status_revision','expected_dependency_revision'].every(key=>pin(payload[key]))||
    !Array.isArray(payload.evidence)||payload.evidence.length!==1||
    payload.evidence[0]!==value.synthesis.artifact?.path||
    payload.evidence.some(path=>!identifier(path)||path.startsWith('/')||path.includes('\\')||path.split('/').includes('..'))||
    typeof payload.summary!=='string'||!payload.summary.trim())throw Error('The retained synthesis has no matching Work attachment action. Reinspect its dispatch.');
  continuationArtifact(value.synthesis.artifact,project);
  return {url:action.http.url,payload:structuredClone(payload),owner:target};
}
export function parentDispatchCancellationSubmission(value,project){
  const action=value?.dispatch_cancel_action,payload=action?.payload;
  const target=qualifiedOwnerHTTP(action?.target_work_read,project)?.owner;
  const allowed=['project','id','status','expected_work_scope_revision','expected_work_status_revision','expected_dependency_revision'];
  if(value?.project!==project||action?.operation!=='task_status'||action.project!==project||action.permitted!==true||
    action.http?.method!=='POST'||action.http.url!=='/work/transition'||target?.kind!=='work'||target.id!==value.dispatch_id||
    !payload||Object.keys(payload).some(key=>!allowed.includes(key))||payload.project!==project||payload.id!==value.dispatch_id||payload.status!=='cancelled'||
    !['expected_work_scope_revision','expected_work_status_revision','expected_dependency_revision'].every(key=>pin(payload[key])))throw Error('The dispatch has no matching cancellation action. Reinspect its Work owner.');
  return {url:action.http.url,payload:structuredClone(payload),owner:target};
}
// The one coordination ladder: parent turn, dispatched children, their returns, the
// synthesis and the explicit recovery. The conversation paints it compact (who, state,
// one sentence, the drilldowns); Work paints it in full with facts. Same rows, same
// validators, no second reading of the dispatch.
export function continuationRows(observed,{project,onOwner,onArtifact,onConversation,onTurn,onAttach,onCancel,status=()=>{},parentActive=false,compact=false,showChildren=true}={}){
  const onError=error=>status(error.message,true),rows=[];
  const facts=[],actions=[];
  const activeNote=observed.children_active?observed.children_active+' dispatched '+(observed.children_active===1?'child remains active or needs cleanup.':'children remain active or need cleanup.'):'';
  if(activeNote)facts.push(activeNote);
  if(['WAITING','PARENT_STOPPED','OBSERVATION_EXPIRED'].includes(observed.phase))facts.push('Parent Stop ends this observation. It does not cancel dispatched work.');
  facts.push('Execution: '+ownerStateWord('run-execution',observed.execution_state).words+' · Review: '+ownerStateWord('run-review',observed.review_state).words);
  if(observed.reason)facts.push(observed.reason);
  if(observed.parent_return_contract?.missing_packets?.length)facts.push('Missing typed returns: '+observed.parent_return_contract.missing_packets.join(', ')+'.');
  if(observed.connected_observation)facts.push('Admitted connected observation: '+observed.connected_observation.admitted_seconds+' seconds. The task deadline is separate.');
  if(observed.dispatch_deadline_at)facts.push('Dispatched work deadline: '+new Date(observed.dispatch_deadline_at*1000).toLocaleString());
  if(observed.observation_deadline_at)facts.push('This observation deadline: '+new Date(observed.observation_deadline_at*1000).toLocaleString());
  facts.push('Original parent turn: '+observed.origin_parent_turn_id);
  const dispatch=qualifiedOwnerHTTP(observed.dispatch_read,project).owner;
  if(onOwner)actions.push({label:'Inspect dispatched work',run:()=>onOwner(dispatch,'Dispatched work and cancellation'),onError});
  if(onOwner&&observed.work_id&&observed.work_id!==observed.dispatch_id)actions.push({label:'Inspect parent Work',run:()=>onOwner(qualifiedOwnerHTTP(observed.work_read,project).owner,'Parent Work and continuation'),onError});
  if(observed.dispatch_cancel_action?.permitted&&onCancel){
    const cancellation=parentDispatchCancellationSubmission(observed,project);
    actions.push({label:'Cancel dispatched work',kind:'danger',run:()=>onCancel(cancellation,observed),onError});
  }
  if(observed.parent_return_contract?.publication_read&&onOwner){
    const target=qualifiedOwnerHTTP(observed.parent_return_contract.publication_read,project)?.owner;
    if(target?.kind!=='current-help'||target.turnId!==observed.turn_id)throw Error('The synthesis publication contract has mismatched reading coordinates.');
    actions.push({label:'Inspect parent synthesis contract',run:()=>onOwner(target,'Parent synthesis contract'),onError});
  }
  const parent={role:'parent',who:'Parent turn',chip:continuationChip(observed),what:parentContinuationLabel(observed)+(compact&&activeNote?' '+activeNote:''),facts,actions,children:[]};
  rows.push(parent);
  if(showChildren&&!compact&&observed.child_outcomes?.length)parent.children=dispatchChildRows(observed.child_outcomes,{project,onTurn,onOwner,status});
  for(const row of observed.readable_returns){
    if(row.status==='UNAVAILABLE'){rows.push({role:'return',who:row.packet+' '+row.role+' return',chip:{label:'Unavailable',tone:'blocked'},errors:[row.packet+' '+row.role+' return is unavailable: '+row.reason]});continue;}
    const target=continuationArtifact(row.artifact,project);
    rows.push({role:'return',who:row.packet+' '+row.role+' return',chip:{label:'Retained',tone:'ok'},actions:onArtifact?[{label:'Read '+row.packet+' '+row.role+' return',run:()=>onArtifact(target.path,row.packet+' return',target),onError}]:[]});
  }
  const synthesis=observed.synthesis;
  if(synthesis.required||synthesis.status!=='NOT_REQUIRED'||synthesis.artifact){
    const chip=synthesis.status==='VALID'?{label:'Synthesis retained'+(synthesis.retained_status?' · '+ownerStateWord('goal-standing',synthesis.retained_status).words.toLowerCase():''),tone:'ok'}:synthesis.status==='MISSING'?{label:'Synthesis needed',tone:'attention'}:synthesis.status==='INVALID'?{label:'Synthesis invalid',tone:'blocked'}:{label:'Synthesis not required',tone:'neutral'};
    const row={role:'synthesis',who:'Parent synthesis',chip,facts:[],errors:[...(synthesis.errors||[])],actions:[]};
    if(synthesis.attachment)row.facts.push('Work evidence attachment: '+ownerStateWord('synthesis-attachment',synthesis.attachment).words.toLowerCase());
    if(synthesis.artifact&&onArtifact){const target=continuationArtifact(synthesis.artifact,project);row.actions.push({label:'Read retained synthesis',run:()=>onArtifact(target.path,'Retained parent synthesis',target),onError});}
    if(synthesis.attach_action&&!parentActive&&onAttach){
      if(synthesis.attach_action.permitted===true){
        const attachment=parentSynthesisSubmission(observed,project);
        row.facts.push('Attaching this retained synthesis records '+attachment.owner.id+' as '+attachment.payload.status+'. Parent Work acceptance remains separate.');
        row.actions.push({label:'Attach retained synthesis to Work',kind:'write',run:()=>onAttach(attachment,observed),onError});
      }else row.facts.push(synthesis.attach_action.reason||'Work attachment is unavailable. Inspect its Work owner before proceeding.');
    }
    if(!compact||row.actions.length||row.errors.length)rows.push(row);
    else if(compact&&synthesis.status!=='VALID')rows.push({role:'synthesis',who:'Parent synthesis',chip});
  }
  if(observed.recovery&&!parentActive){
    rows.push({role:'recovery',who:'Continue',what:'Continuation is explicit: prepare a new author message in the recorded parent conversation, then Send. Nothing restarts automatically.',
      actions:onConversation?[{label:'Open recorded parent',run:()=>onConversation(observed.recovery.session_id),onError}]:[]});
  }
  return rows;
}
export function renderParentContinuation(host,value,{project,sessionId=null,turnId=null,onOwner,onArtifact,onConversation,onTurn,onAttach,onCancel,status=()=>{},active=null,compact=false,showChildren=true}={}){
  const observed=parentContinuation(value,{project,sessionId,turnId});if(!observed)return null;
  const parentActive=active===null?observed.parent_active===true:active;
  const panel=document.createElement('section');panel.className='parent-continuation';
  const rows=continuationRows(observed,{project,onOwner,onArtifact,onConversation,onTurn,onAttach,onCancel,status,parentActive,compact,showChildren});
  coordinationLadder(panel,{rows,compact});
  if(compact){
    // The conversation keeps the ladder to one line per row; the exact basis (execution,
    // review, deadlines, origin turn) stays behind one quiet disclosure whose open state
    // the session preserves across repaints.
    const exact=document.createElement('details');exact.className='operator-exact';
    const summary=document.createElement('summary');summary.textContent='Results and continuation';exact.append(summary);
    for(const fact of rows[0]?.facts||[]){const line=document.createElement('p');line.textContent=fact;exact.append(line);}
    panel.append(exact);
  }
  host.append(panel);return panel;
}

export function preparedWorkSubmission(action, project, sectionIds) {
  const payload = action?.payload;
  const allowed = ['operation', 'expected_plan_revision', 'expected_selection', 'section_ids'];
  if (action?.operation !== 'structure_change' || action.project !== project ||
      action.http?.method !== 'POST' || action.http.route !== '/work/structure/change' ||
      !payload || Object.keys(payload).some(key => !allowed.includes(key)) ||
      payload.operation !== 'prepare_work' || !pin(payload.expected_plan_revision) ||
      !pin(payload.expected_selection) || !Array.isArray(sectionIds) || !sectionIds.length ||
      !same(payload.section_ids, sectionIds)) {
    throw Error('Inspect this reader-plan scope before preparing its Work. No preparation was submitted.');
  }
  return {project, ...structuredClone(payload)};
}

export function preparedRunSubmission(action, project, task, {requirePermitted = true} = {}) {
  const payload = action?.payload;
  const retained=preparedParentContinuations(task,task?.prepared_execution,project);
  const parentSession=retained.length===1?retained[0].origin_parent_session_id:task?.prepared_execution?.items?.at(-1)?.session_id;
  const allowed = ['project', 'mode', 'work_id', 'expected_work_scope_revision',
    'expected_dependency_revision', 'text', 'session_id'];
  if (requirePermitted && (action?.permitted !== true||retained.length>1) || action?.project !== project || action.requires_role !== 'author-parent' ||
      action.http?.method !== 'POST' || action.http.route !== '/authoring/turn' ||
      !payload || Object.keys(payload).some(key => !allowed.includes(key)) ||
      payload.project !== project || payload.mode !== 'work' || payload.work_id !== task?.id ||
      typeof payload.text !== 'string' || !payload.text.trim() ||
      payload.session_id !== undefined && (typeof payload.session_id !== 'string' || !payload.session_id.trim() || /[\u0000-\u001f]/.test(payload.session_id) || payload.session_id !== parentSession) ||
      !pin(payload.expected_work_scope_revision) || !pin(payload.expected_dependency_revision) ||
      payload.expected_work_scope_revision !== task.work_scope_revision ||
      payload.expected_dependency_revision !== task.dependency_revision) {
    throw Error('The prepared action does not match this inspected Work. Reinspect the Work before composing its parent request.');
  }
  // Session/provider settings and request identity are chosen by the existing
  // conversation owner. A returned action cannot inject transport fields.
  return structuredClone(payload);
}

export function preparedParentContinuations(task,execution,project){
  if(execution?.retained_dispatches!==undefined){
    if(!Array.isArray(execution.retained_dispatches))throw Error('Prepared Work has no valid retained dispatch scope. Reinspect its owner.');
    const seen=new Set();
    return execution.retained_dispatches.map(raw=>{
      const value=parentContinuation(raw,{project});
      if(!value||value.work_id!==task?.id||seen.has(value.dispatch_id)||Array.isArray(task.depends_on)&&!task.depends_on.includes(value.dispatch_id))throw Error('The retained dispatch does not match this prepared Work. Reinspect its owner.');
      seen.add(value.dispatch_id);return value;
    });
  }
  const legacy=execution?.parent_continuation||task?.parent_continuation||task?.dispatch?.parent_continuation||execution?.items?.at(-1)?.parent_continuation;
  return legacy?[parentContinuation(legacy,{project})]:[];
}

export function preparedWorkReceipt(value, project) {
  const work = qualifiedOwnerHTTP(value?.work_read, project)?.owner;
  if (value?.ok !== true || value.provider_started !== false ||
      work?.kind !== 'work' || work.id !== value.work_id ||
      value.task?.id !== value.work_id || !value.preparation ||
      typeof value.preparation.current !== 'boolean') {
    throw Error('Preparation returned no matching durable Work receipt. Inspect Work before preparing again.');
  }
  preparedRunSubmission(value.run_action, project, {...value.task, prepared_execution:value.execution}, {requirePermitted: false});
  return value;
}

export function renderPreparedWork(host, {project, task, preparation, execution,
  action, artifact = preparation?.artifact, onUse, onWork, onArtifact,
  onConversation, onTurn, onOwner, onAttach, onCancel, status = () => {}}) {
  const element = (tag, text = '') => {
    const node = document.createElement(tag);
    node.textContent = text;
    return node;
  };
  const onError = error => status(error.message, true);
  const panel = element('section');
  panel.className = 'work-card prepared-work';
  panel.append(objectHeader({eyebrow: 'Prepared from the reader plan', title: 'Prepared reader-plan work', level: 'h3',
    chips: [preparation?.current ? {label: 'Prepared inputs current', tone: 'ok'} : {label: 'Prepared inputs need inspection', tone: 'attention'}],
    summary: preparation?.current ? '' : (preparation?.error || preparation?.recovery || 'Inspect the current reader plan and prepare again.')}));
  const retained=preparedParentContinuations(task,execution,project),continuation=retained.length===1?retained[0]:null;
  for(const value of retained)renderParentContinuation(panel,value,{project,active:execution?.running===true,onArtifact,onConversation,onTurn,onAttach,onCancel,status,
    onOwner:onOwner||(onWork?(read=>onWork(read.id)):null)});
  if(retained.length>1)panel.append(element('p','Several retained dispatches belong to this Work. Inspect the intended dispatch before preparing a continuation.'));
  const actions = [];
  if (onWork) actions.push({label: 'Inspect Work', run: () => onWork(task.id), onError});
  const source = artifact?.human_read?.url ?
    artifactHumanTarget(artifact.human_read.url, {project}) : null;
  if (source && source.artifactId === artifact.id &&
      source.expectedSha256 === artifact.revision && onArtifact) {
    actions.push({label: 'Read prepared inputs', run: () => onArtifact(source.path, 'Prepared reader-plan inputs', source), onError});
  }
  if (onUse && action) {
    actions.push({label: action.payload?.session_id ? continuation?.recovery?'Prepare continuation message':'Prepare parent follow-up' : 'Use in next message',
      kind: 'write', primary: action.permitted === true, disabled: action.permitted !== true, onError,
      title: action.permitted ? continuation?.recovery?'Prepare a new author message in the recorded parent conversation. Nothing is sent until Send.':'Review the parent message before sending.' :
        action.reason||'Inspect prepared inputs and the recorded parent execution before continuing.',
      run: () => onUse(action, {...task, prepared_execution:execution})});
  }
  const row = actionRow(actions); row.className += ' work-actions'; panel.append(row);
  // copy (plan §10): what starts provider work is said on the buttons' titles; the cost block
  // carries the owner's own cost sentence when it has one
  for (const node of row.querySelectorAll?.('button') || []) {
    if (/^Use /.test(node.textContent) || /^Send/.test(node.textContent)) node.title = node.title || 'Sending starts provider work.';
    else if (/^Prepare/.test(node.textContent)) node.title = node.title || 'Preparation starts no provider work.';
  }
  const cost = element('details');
  cost.append(element('summary', 'Execution and cost'));
  if (action?.provider_cost) cost.append(element('p', action.provider_cost));
  for (const row of execution?.items || []) {
    const item = element('div');
    item.append(element('p', 'Parent turn: ' + ownerStateWord('prepared-turn', row.state).words.toLowerCase()));
    if(row.parent_continuation){const retained=parentContinuation(row.parent_continuation,{project,sessionId:row.session_id,turnId:row.turn_id});item.append(element('p',parentContinuationLabel(retained)));}
    if (row.session_id && onConversation) item.append(actionRow([{label: 'Open parent conversation', run: () => onConversation(row.session_id), onError}]));
    if (row.turn_id && onTurn) item.append(actionRow([{label: 'Read exact parent turn', run: () => onTurn(row.turn_id), onError}]));
    cost.append(item);
  }
  if (execution?.omitted) cost.append(element('p', execution.omitted +
    ' older parent turns remain in the conversation history.'));
  panel.append(cost);
  host.append(panel);
  return panel;
}

export function renderPreparationFailure(host, value, {project, onArtifact,
  onWork, status = () => {}}) {
  const publication = value?.preparation_publication;
  if (publication?.state !== 'ARTIFACT_RETAINED' || publication.complete !== false) {
    throw Error('This failure has no verified retained preparation receipt.');
  }
  const artifact = publication.artifact;
  const source = artifactHumanTarget(artifact?.human_read?.url, {project});
  if (!source || source.artifactId !== artifact.id || source.expectedSha256 !== artifact.revision) {
    throw Error('The retained input artifact has no matching pinned inspection route.');
  }
  const element = (tag, text = '') => {
    const node = document.createElement(tag);
    node.textContent = text;
    return node;
  };
  const onError = error => status(error.message, true);
  const panel = element('section');
  panel.append(objectHeader({title: 'Inputs retained; Work needs inspection', level: 'h3', chips: [{label: 'Publication incomplete', tone: 'attention'}],
    summary: [value.error || 'Work publication or inspection did not finish.', value.recovery].filter(Boolean).join(' ')}));
  const actions = [];
  if (onArtifact) actions.push({label: 'Read retained inputs', run: () => onArtifact(source.path, 'Retained prepared inputs', source), onError});
  const work = (value.next_reads || []).map(handle =>
    qualifiedOwnerHTTP(handle, project)?.owner).find(target =>
    target?.kind === 'work' && target.id === publication.work_id);
  if (work && onWork) actions.push({label: publication.work_publication === 'COMMITTED' ?
    'Inspect retained Work' : 'Inspect possible Work', run: () => onWork(work.id), onError});
  panel.append(actionRow(actions));
  host.append(panel);
  return panel;
}
