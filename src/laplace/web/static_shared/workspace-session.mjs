import {providerModelOptions,providerEffortOptions} from './provider-options.mjs';
import {readerSession} from './sealed-reader-port.mjs';
import {paintReaderSession} from './sealed-reader.mjs';
import {WorkspaceWorkflowAction} from './workspace-workflow-action.mjs';
import {workflowActionInput,workflowActionSummary} from './workflow-action-context.mjs';
import {workflowConversationAction} from './workflow-port.mjs';
import {objectContextInput} from './research-object-context.mjs';
import {materialReadingInput} from './local-document-intake-port.mjs';
// Presentation only: describe the retained next-message intent, never the current
// reader location. Validation reuses the attachment owner; this does not create a handle.
export function nextMessagePreview(intent={},selection=null,{project,label=''}={}){
 const rows=[];
 if(intent.material_read){
  try{const reading=materialReadingInput(intent.material_read,{project}),p=reading.read_payload;
   const extent=p.page!==undefined?'Page '+p.page+(p.page_count>1?' through '+(p.page+p.page_count-1):''):p.offset!==undefined||p.limit!==undefined?'Text window: offset '+(p.offset??0)+(p.limit!==undefined?', limit '+p.limit+' characters':''):p.pointer?'Selected document part '+p.pointer:'Owner-issued document reading';
   rows.push({kind:'document',title:label||intent.label||reading.artifact_id,extent,identity:reading});
  }catch{rows.push({kind:'unavailable',title:'Document attachment needs inspection',extent:'The retained pointer could not be verified for this project. It has not been changed.'});}
 }
 if(intent.object_context)rows.push({kind:'object',title:intent.label||'Selected object',extent:'Selected object context; this does not imply the whole source was attached.',identity:intent.object_context});
 if(selection)rows.push({kind:'selection',title:selection.draft?'Selected unsaved writing':'Selected writing',extent:selection.quote||((selection.files||[]).join(', ')||'Selected passage'),identity:selection.anchor||null});
 if(intent.workflow_action)rows.push({kind:'action',title:intent.label||'Selected workflow action',extent:'This owner action is checked on Send; previewing it starts nothing.'});
 if(!rows.length)rows.push({kind:'framing',title:intent.label||'Project',extent:'Project and reading context only. Inspect a source and choose Use reading for next message to attach its exact reading.'});
 return rows;
}
// workspace-session.mjs — THE CONVERSATION PANE: one project conversation, independent of the
// manuscript view (M5 C8).
// Ownership: /authoring/state view=sessions (library), /authoring/session view=summary (turn
//   rows, limit 20, older_cursor), session-turn (exact bodies, actions, failures, controls),
//   turn / steer / interrupt (writes), events (the ONE turn stream owner), providers and
//   session-settings. Work and dispatch facts are read through their owners, never inferred.
// Public contract: class WorkspaceSession (mount, loadSession, send, steer, scope, appendTurn,
//   facets, actions, failures, proposal, ...); projectRequest (over owner-request.mjs) and writingOwnerResponse; turnFailures;
//   turnCompletionStatus; messageLinkParts; sessionOrigin; savedActionDestination;
//   contextUsageCounter; conversationMetadata; settingsTruthText; appendStreamText.
// Summary rows remain the owner's cheap identity/count glances. Visible message parts
// use conversation-reading.mjs and session-turn view=message for exact in-place text;
// long parts continue explicitly under one basis. Partial pages are literal, complete
// assembly may use the existing safe Markdown renderer. Audit, artifacts, actions and
// failure disclosures keep their separate lazy reads. Stable message nodes and the
// selected-session reading cache survive summary refresh; only target/basis/extent
// intent (never message words) is retained in sessionStorage for reload.
// Target chip row: message target, attached reading or passage, intent; Clear only when
//   something is retained. The composer target line names steering / follow-up / new.
// Currentness: a session load is ticketed (session, epoch, load); a late response cannot
//   restore a replaced conversation; settings truth is the admitted turn's, next-message
//   settings are the form's.
// Errors/recovery: stream loss -> passive provider refresh on laplace-workspace-reconnected;
//   failed settings saves retry on Send; unsent drafts survive reloads.
// Storage: localStorage laplace:compose:<project>:<session> (draft), laplace:mode:<project>:
//   <session>, laplace:conversation-settings:<project>:<session>, laplace:session:*,
//   laplace:workspace:conversation-width, laplace:workspace:composer-height; sessionStorage for
//   the composer backup. No key renamed in M5.
import {mountMessageReading} from './conversation-reading.mjs';
import {preparedRunSubmission,preparedParentContinuations,parentContinuation,renderParentContinuation} from './prepared-work.mjs';
import {buildCancelAcknowledged} from './derived-output.mjs';
import {messageTarget,encodeComposerDraft,decodeComposerDraft,sameComposerIntent,connectedObservationSeconds,preferenceDraftEnvelope} from './workspace-interaction.mjs';
import {planPublicationDisposition,requirePlanCompletion,savedActionPlanPublication,savedFailurePlanPublication} from './plan-publication.mjs';
import {sourceEffectDisposition,requireSourceCompletion,sourceEffectFromError,savedActionSourceEffect,savedFailureSourceEffect} from './source-effect.mjs';
// One project conversation, independent of the manuscript view.
import {analyticsQuery,analyticsEnvelope,analyticsReadURL,openResponseFeedback,renderRecordedRecovery as appendSavedRecovery,inspectRecoveryRead} from './workspace-analytics.mjs';
import {fileOnlyManuscriptSelection,sourceOnlyProposalContext} from './manuscript-editing.mjs';
import {artifactHumanTarget,conceptHumanTarget,ownerHumanTarget,isKnownOwnerReadRoute} from './writing-owner-read.mjs';
import {chipRow,relationList} from './workspace-presentation.mjs';
import {pendingRead} from './pending-read.mjs';
import {refuseEmptySend} from './workspace-sessions.mjs';
export {renderRecordedRecovery as appendSavedRecovery} from './workspace-analytics.mjs';
export {artifactHumanTarget,conceptHumanTarget,ownerHumanTarget} from './writing-owner-read.mjs';
const make=(tag,text='',cls='')=>{const e=document.createElement(tag);e.textContent=text;e.className=cls;return e;};
// Closed history disclosures keep exact records in memory without building their
// entire DOM. Opening a collection renders one page; individual receipts remain lazy.
// WHO SAID IT AND WHEN (wave 5): the speaker label keeps its words ('You', 'Eigen'); the owner's recorded time for that
// message (the thread row's ts, session_projection.py) rides as data-when, drawn after the label by CSS. No time, no mark.
function spokenAt(row,ts){if(!ts)return;const label=[...(row?.children||[])].find(node=>String(node?.tagName||'').toUpperCase()==='STRONG');if(!label)return;const at=new Date(ts);if(!Number.isFinite(at.getTime()))return;
  label.setAttribute?.('data-when',at.toLocaleString(undefined,{day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'}));label.title=String(ts);}
function lazyContent(details,build){let built=false;details.ontoggle=()=>{if(!details.open||built)return;built=true;build();};}
function pagedItems(details,items,render,noun){
  lazyContent(details,()=>{
    const list=make('div'),more=make('button');more.type='button';let shown=0;
    const append=()=>{const end=Math.min(items.length,shown+20);for(;shown<end;shown++)list.append(render(items[shown]));more.hidden=shown===items.length;more.textContent=`Show next ${Math.min(20,items.length-shown)} ${noun} (${shown} of ${items.length} shown)`;};
    more.onclick=append;append();details.append(list,more);
  });
}
// projectRequest = the neutral carrier (owner-request.mjs) + THE WRITING RESPONSE ADAPTER below. Order is kept: a
// reply's source-effect event is dispatched BEFORE plan and source completion are required, so a partial effect is
// announced even when the reply then throws; a metadata-only reply has no source effect; an acknowledged build
// cancellation is not an error; an owner refusal keeps its body as error.result. A lost connection keeps the
// existing event and message and adds transport/effect (effect 'unknown' for a POST: nothing is resent).
import {projectRequest,writingOwnerResponse} from './writing-request.mjs';
export {projectRequest,writingOwnerResponse} from './writing-request.mjs';
// The text `settingsTruth` renders, pulled out as its own pure function so a SECOND
// renderer -- the project-work pane's dispatch card, one session row per child, S3
// dispatch-pane -- reads a child's tier/model/effort/model_source through the exact same
// function the live conversation pane already uses, rather than a second formatter that
// could say something different for the same banked row. `fallbackProvider` is read off
// the live [data-provider] control only by the one caller that HAS a form on screen; a
// dispatch card has none, and passes the child's own `session.provider` instead.
export function settingsTruthText(session,defaults,fallbackProvider){
  const parts=[];
  if(session?.provider||session?.model){
    const tier=session.tier?` (${session.tier} tier)`:'';
    parts.push(`${session.model||'—'}${tier}`);
    parts.push(`effort ${session.effort==null?'Automatic':session.effort}`);
    parts.push(session.model_source?`recorded model source: ${session.model_source.replace('-',' ')}`:'model choice origin not recorded');
  }
  if(defaults)parts.push(`session default: ${defaults.models?.[fallbackProvider??session?.provider]||''} (${defaults.tier})`);
  return parts.filter(Boolean).join(' · ');
}
export function turnFailures(turn){
  const normalize=value=>{const raw=value.record&&typeof value.record==='object'?value.record:value;const row={...raw,...Object.fromEntries(['recovery_read','related_action'].filter(key=>Object.hasOwn(value,key)).map(key=>[key,value[key]]))};return ({project:row.project,turn_id:row.turn_id,operation:row.operation||row.tool_name||'project operation',error:row.error||row.reason||'No failure detail was recorded.',id:row.id||row.tool_use_id,target:row.payload?.file||row.payload?.node||row.payload?.id||row.payload?.key||row.payload?.path||row.payload?.run_id||row.payload?.url||'',kind:row.error_type||'',recovery:row.recovery,sourceEffect:savedFailureSourceEffect(row),planPublication:savedFailurePlanPublication(row),call:row.tool_use_id,ts:row.ts||'',resolved_later:row.recovery_read?.recovers_read_goal===true,recovery_read:row.recovery_read||null,related_action:row.related_action||null});};
  const fingerprint=row=>row.operation+'\n'+row.error+'\n'+row.target,seen=new Set(),canonical=new Set(),rows=[];
  for(const row of (turn.tool_failures||[]).map(normalize)){const key=row.call||row.id||fingerprint(row);if(seen.has(key))continue;seen.add(key);canonical.add(fingerprint(row));rows.push(row);}
  for(const row of (turn.reply?.provider_issues||[]).map(normalize)){const key=row.call||row.id||fingerprint(row);if(seen.has(key)||canonical.has(fingerprint(row)))continue;seen.add(key);rows.push(row);}
  return rows;
}
export function failureAttemptSummary(turn,failures=turnFailures(turn)){
  const count=turn.failure_count??failures.length,reads=turn.read_recovery_count??failures.filter(row=>row.recovery_read?.recovers_read_goal===true).length,related=turn.related_action_count??failures.filter(row=>row.related_action?.basis==='same_operation_target').length;
  return count+' failed attempt'+(count===1?'':'s')+(reads?' · '+reads+' with recovery reads':'')+(related?' · '+related+' linked to later actions':'');
}
export function turnCompletionStatus(result,hasAttempts=false){
  const effects=(result.actions||[]).flatMap(action=>[savedActionSourceEffect(action),savedActionPlanPublication(action)]).filter(Boolean);
  const failures=turnFailures({tool_failures:result.tool_failures,reply:result});
  const unresolved=effects.find(effect=>!effect.acknowledged)||failures.filter(failure=>!failure.resolved_later).flatMap(failure=>[failure.sourceEffect,failure.planPublication]).find(Boolean);
  if(unresolved)return {text:'Reply saved. '+unresolved.message,error:true};
  const warning=effects.find(effect=>effect.warnings?.length);
  if(warning)return {text:'Reply saved. '+warning.message,error:true};
  return {text:result.status==='completed'?'Reply saved.'+(hasAttempts?' Failed attempts are available in this reply’s history.':''):result.status==='interrupted'?'Stopped; partial reply saved.':'Turn failed; inspect the reply.',error:result.status==='failed'};
}
export function proposalPresentation(turn={}){
  const terminal={applied:'Saved proposal applied',rejected:'Saved proposal rejected','applied-elsewhere':'Saved proposal applied in another turn',superseded:'Saved proposal superseded',fulfilled:'Saved proposal fulfilled','resolved-into-successor':'Saved proposal resolved in a later revision'};
  const state=turn.proposal_state,count=turn.proposal_edit_count??(turn.proposal||turn.reply?.proposal)?.edits?.length??0;
  if(terminal[state])return {terminal:true,label:terminal[state],count};
  if(!count)return null;
  return {terminal:false,count,label:state==='in-progress'?'Preparing manuscript changes…':`Review ${count} manuscript change${count===1?'':'s'}`,disabled:state==='in-progress'};
}

// Disclosure only: these are settled transport facts, not proof of model action.
export function inputReceiptNeedsAttention(row={}){
  if(row.kind==='native-acknowledgement'&&row.delivery_mode==='native_rpc'&&row.project&&row.session&&row.turn&&row.response&&typeof row.response==='object'&&!Array.isArray(row.response))return false;
  if(row.state==='PUBLISHED_AT_TOOL_BOUNDARY'){
    const parts=row.publication?.parts;
    return row.publication?.scope!=='FULL'||!parts||['author_request','context'].some(key=>{
      const part=parts[key];return part?.complete!==true||!Number.isInteger(part.included_chars)||!Number.isInteger(part.total_chars)||part.total_chars<0||part.included_chars!==part.total_chars;
    });
  }
  return !['EXACT_SCOPED_CONTROL_READ','DELIVERED'].includes(row.state);
}

export function inputDeliveryMode(capabilities={}){const modes=Array.isArray(capabilities.input_delivery_modes)?capabilities.input_delivery_modes:[];return capabilities.can_steer===true&&modes.includes('native_rpc')?'native_rpc':capabilities.can_offer_input===true&&modes.includes('project_tool_boundary')?'project_tool_boundary':null;}
export function steeringObservation(capabilities={},snapshots=false){const mode=inputDeliveryMode(capabilities);return (snapshots?'Execution observed. Live token streaming is unavailable.':'Live public output from the selected turn.')+(mode==='native_rpc'?' Native steering is available for this selected turn.':mode==='project_tool_boundary'?' You can queue input for its next project tool result; this is not immediate native steering.':capabilities.can_steer===false?' Steering is unavailable for this execution; your draft can be sent as a follow-up after it ends.':' Input capability has not been reported.');}
export function savedExecutionObservation(data={}){const saved=(data.turns||[]).at(-1);if(data.execution?.state==='FINISHED')return 'Last observed turn ended: '+String(data.execution.result_status||'outcome not recorded').replaceAll('_',' ')+'.';if(saved?.reply)return 'Saved reply: '+String(saved.reply.status||'status not recorded').replaceAll('_',' ')+'.';return data.session?'No active turn reported; no final reply is saved for the latest turn.':'';}

export function appendStreamText(previous,chunk,messageStart=false){
  if(!chunk)return previous;
  const existingBoundary=previous.match(/\n*$/)[0].length+chunk.match(/^\n*/)[0].length;
  const separator=messageStart&&previous?'\n'.repeat(Math.max(0,2-existingBoundary)):'';
  return previous+separator+chunk;
}

export function markdownProtectedRanges(text){
  return [...String(text).matchAll(/```[\s\S]*?(?:```|$)|(`+)(?!`)[^\n]*?\1(?!`)|\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|\$(?!\$)[^$]+?\$|\\\([\s\S]*?\\\)/g)].map(match=>[match.index,match.index+match[0].length]);
}
export function messageLinkParts(value,{project,resultLinks=[]}={}){
  const text=String(value||''),parts=[],pattern=/\[([^\]\n]+)\]\(\s*(?:<([^>\n]+)>|([^\)\n]+))\s*\)/g;
  const code=markdownProtectedRanges(text);let at=0,match;
  while((match=pattern.exec(text))){if(code.some(([start,end])=>match.index>=start&&match.index<end))continue;const target=(match[2]||match[3]).trim();let kind=null,path=target;
    const conceptRead=conceptHumanTarget(target),ownerRead=ownerHumanTarget(target);
    if(conceptRead)kind='concept';
    else if(ownerRead)kind='owner-read';
    else if(isKnownOwnerReadRoute(target))continue;
    else if(/^(?:https?:\/\/|\/\/)/i.test(target)||/^\/(?:project|walk|research\/artifact|references\/source)\?/.test(target))kind='web';
    else if(!/^[A-Za-z][A-Za-z0-9+.-]*:/.test(target)&&(/[/\\]/.test(target)||/\.(?:md|txt|tex|pdf|json|jsonl|csv|tsv|py|lean|log|toml|yaml|yml|png|jpe?g|svg)(?:#.*)?$/i.test(target))){kind='artifact';try{path=decodeURIComponent(target.split('#')[0]);}catch{}}
    let humanRead=project?artifactHumanTarget(target,{project}):null;const exact=resultLinks.filter(read=>(read.aliases||[]).includes(path));if(!humanRead&&exact.length===1)humanRead=artifactHumanTarget(exact[0].url,{project});if(humanRead)kind='human-artifact';
    if(!kind)continue;if(match.index>at)parts.push({text:text.slice(at,match.index)});parts.push({kind,label:match[1],target:path,...(ownerRead?{ownerRead,href:ownerRead.href}:{}),...(conceptRead?{conceptRead,href:conceptRead.href}:{}),...(humanRead?{humanRead,href:exact.length===1?exact[0].url:target}:{})});at=pattern.lastIndex;
  }
  if(at<text.length)parts.push({text:text.slice(at)});return parts;
}

export function sessionWorkTarget(data={}){
  const latest=(data.turns||[]).at(-1)||{},active=data.active||{};
  return active.work_id||active.dispatch_id||latest.work_id||latest.dispatch_id||data.session?.dispatch_id||null;
}
export function sessionOrigin(data={}){
  const turns=data.turns||[],latest=turns.at(-1)||{};
  return {workId:sessionWorkTarget(data),dispatchId:data.active?.dispatch_id||latest.dispatch_id||data.session?.dispatch_id||null,
    parentTurnId:data.active?.parent_turn_id||latest.parent_turn_id||turns.find(t=>t.parent_turn_id)?.parent_turn_id||null,
    packet:data.session?.packet||null,turnId:data.active?.id||latest.id||null};
}
export function savedActionDestination(action={}){
  const outcome=action.outcome||{},payload=action.payload||{};
  if(action.operation==='store_artifact'){
    const read=outcome.human_read;if(read?.path&&read.scope&&read.expected_sha256)return {kind:'artifact',path:read.path,scope:read.scope,expectedSha256:read.expected_sha256,...(read.owner?{artifactOwner:read.owner}:{}),...(read.artifact_id?{artifactId:read.artifact_id}:{})};
    const path=payload.path||outcome.paths?.[0],scope=payload.scope||'project';
    if(typeof path==='string'&&path&&['project','manuscript'].includes(scope))return {kind:'artifact',path,scope,artifactOwner:'writing-artifact',...(outcome.revisions?.revision?{expectedSha256:outcome.revisions.revision}:{})};
  }
  if(['task','task_status'].includes(action.operation)){
    const id=payload.id||outcome.identities?.find(id=>typeof id==='string'&&id.startsWith('WORK-'));
    if(id)return {kind:'work',id};
  }
  return null; // The receipt remains available; never invent a semantic destination.
}

// R2 (2026-10-14): a historical reply's meter is compatible with the form only when it names its
// own provider and model and they equal the selection; a meter without identity is historical/
// unknown and never matched against proposed next settings. The active turn and the session
// keep the permissive rule (absent fields mean the selection).
export function meterMatchesSelection(reported={},provider,model,historical=false){
  if(historical)return !!reported.provider&&!!reported.model&&reported.provider===provider&&reported.model===model;
  return (!reported.provider||reported.provider===provider)&&(!reported.model||reported.model===model);
}
export function contextUsageCounter(usage,context={}){
  const number=value=>value!==null&&value!==undefined&&value!==''&&Number.isFinite(Number(value))&&Number(value)>=0?Number(value):null;
  const selection=context?.usage_selection?.selected||context?.usage_selection||context?.usage_facts_projection?.selected;const snapshot=selection?.context_snapshot;
  const limit=number(context?.context_window_effective??usage?.context_window??usage?.thread_token_usage?.modelContextWindow);
  if(snapshot)return {kind:snapshot.metric==='last_request_input_proxy'?'request-proxy':'selected',value:number(snapshot.value),metric:snapshot.metric||null,basis:snapshot.basis,limit};
  const value=number(context?.context_tokens_used??context?.used_tokens??usage?.thread_token_usage?.last?.totalTokens??usage?.assistant_message?.input_tokens);
  return {kind:value===null?'unknown':'legacy',value,limit};
}

// THE CONVERSATION ROW (brief V5, display only). running rests only on an owner observation of GET /authoring/session
// (ownerRunningObservation) and always carries that observation's time; page memory is never shown as running. A row
// bound to a Work (its work_title joined from the Work owner's own detail read on work_id) leads with that title, then one
// owner state word (running, or finished followed by the saved reply's own completed, failed or interrupted), the
// recorded last event time and whether Stop applies. An unbound row keeps its existing lines.
// seconds between owner re-reads while a conversation is shown running (the interval workspace-project.mjs:55 already uses)
const RUNNING_REFRESH_MS=5000;
const clockTime=value=>{if(!value)return null;const at=new Date(value);return Number.isFinite(at.getTime())?at.toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit',hourCycle:'h23'}):null;};
const eventTime=value=>{if(!value)return null;const at=new Date(value);return Number.isFinite(at.getTime())?at.toLocaleString(undefined,{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}):null;};
export function ownerRunningObservation(data){
  const active=data?.active;if(!active||!active.observed_at||['ORPHANED','UNKNOWN-OWNERSHIP'].includes(active.progress))return null;
  const stop=active.capabilities?.can_interrupt;
  return {turn:active.id||active.turn_id||'',at:active.observed_at,stop:stop===true?true:stop===false?false:null,workId:active.work_id||null,title:data.session?.title||''};
}
export function runningWords(running){
  const time=running?.at?clockTime(running.at):null;if(!time)return null;
  return ['running, observed '+time,running.stop===true?'Stop applies':running.stop===false?'Stop does not apply':null].filter(Boolean).join(' · ');
}
export function conversationRowLead(row={}){return row.work_title||row.title||row.id;}
export function conversationMetadata(row={}, {running=null,draft=false,loading=false}={}){
  const lines=[],created=Number(row.created_at),when=row.created_at?new Date(Number.isFinite(created)?created*1000:row.created_at):null,bound=!!row.work_title,observed=runningWords(running);
  if(bound){const finished=!observed&&row.saved_terminal_kind&&row.latest_admission_has_reply!==false?'finished · '+row.saved_terminal_kind:null,last=row.latest_recorded_at?eventTime(row.latest_recorded_at):null;
    const state=[observed||finished,last?'last event '+last:null].filter(Boolean);if(state.length)lines.push(state.join(' · '));if(row.title&&row.title!==row.work_title)lines.push(row.title);}
  const model=row.admitted_settings;const facts=[when&&Number.isFinite(when.getTime())?'Created '+when.toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric'}):null,model?.provider||row.provider,model?.model?'Admitted '+model.model:row.model,row.role==='review'?'Independent review':row.role==='author'?'Author conversation':row.role].filter(Boolean);
  if(facts.length)lines.push(facts.join(' · '));const recorded=[row.saved_terminal_kind&&!bound?'Last saved reply: '+row.saved_terminal_kind:null,row.turn_count!=null?row.turn_count+(Number(row.turn_count)===1?' turn':' turns'):null,row.retained_failure_receipts?row.retained_failure_receipts+' saved failures':null,row.artifact_receipt_count?row.artifact_receipt_count+' artifacts':null].filter(Boolean);if(recorded.length)lines.push(recorded.join(' · '));if(row.dispatch_id)lines.push('Dispatch '+row.dispatch_id);else if(row.work_id)lines.push('Work '+row.work_id);
  const observation=[!bound&&observed?observed:loading?'Opening':null,row.latest_admission_has_reply===false?'Latest request: no saved reply':null,draft?'Local draft retained':null].filter(Boolean);if(observation.length)lines.push(observation.join(' · '));
  return lines;
}

// One sentence joining where the next message goes, what it reads, its intent
// and settings with any retained or active request. Pure text; it sends nothing.
export function composerDecisionSummary({destination='',reading='',intent='',pending=false,active=false,stopRequested=false}={}){
  const state=pending?'A sent request is retained with its original text and settings; changes here apply only to a later message.':stopRequested?'Stop was requested for the active turn; completion is not yet confirmed.':active?'A turn is active. What you type now is steering or queued input, not a new request.':'Nothing is sent until you choose Send.';
  return (destination||'New conversation')+' · reading '+(reading||'This project')+' · '+(intent||'Next message')+'. Model & settings apply to the next message only. '+state;
}
export function conversationOperationPresentation({initializing=false,startupFailed=false,loadingSession=false,submitting=false,submission=null,controlPending=null,active='',stopRequested=false}={}){
  if(startupFailed)return 'Conversation unavailable. Your local message is retained.';
  if(initializing||loadingSession)return 'Reading the selected conversation…';
  if(submission)return 'Submission needs an exact receipt check. Its original message and settings are retained; changing a future choice does not resend it.';
  if(controlPending)return 'Input has a retained request receipt. Delivery still needs observation; do not send a replacement.';
  if(submitting)return 'Request in progress. Admission and delivery are not yet confirmed.';
  if(stopRequested)return 'Stop requested for the selected turn. Completion is not yet confirmed; recorded effects are not undone.';
  if(active)return 'Selected turn is active in the last owner observation. Its admitted settings stay separate from future messages.';
  return '';
}

export class WorkspaceSession {
  constructor(host,{project,initialSession='',getContext=()=>({}),onClose=()=>{},onChanged=()=>{},onInspect=()=>{},onReviewProposal=()=>{},onOpenReview=()=>{},onProposalChanged=async()=>{},onInspectPassage=()=>{},onApplication=()=>{},onOpenArtifact=()=>{},onOpenOwner=null,onAddLocalDocument=null,renderFinalMessage=null,onReadTurn=null,onWorkAssociation=null,onWorkObservation=null,onOpenWork=null,onActivity=null,onScope=null,prepareSend=async()=>{}}){
    Object.assign(this,{host,project,initialSession,getContext,onClose,onChanged,onInspect,onReviewProposal,onOpenReview,onProposalChanged,onInspectPassage,onApplication,onOpenArtifact,onOpenOwner,onAddLocalDocument,renderFinalMessage,onReadTurn,onWorkAssociation,onWorkObservation,onOpenWork,onActivity,onScope,prepareSend});
    this.initializing=true;this.startupFailed=false;this.queued=[];this.session='';this.active='';this.role='author';this.providers=[];this.stream=null;this.limit=30;this.modeRevision=0;this.sessionLoad=0;this.settingsRevision=0;this.settingsSave=Promise.resolve();this.viewEpoch=0;this.streamGeneration=0;this.loadingSession=false;this.sessionRows=[];this.runningSessions=new Map();this.ownerRunning=new Map();this.listLoad=0;
    this.key='laplace:session:'+project;this.draftKey='laplace:compose:'+project;
    host.classList.add('workspace-session');
    host.innerHTML=`<div data-resize class="session-divider" role="separator" tabindex="0" aria-label="Resize conversation" aria-orientation="vertical" title="Drag to resize; arrow keys adjust width; double-click to reset"></div>
      <header><div class="session-identity"><strong>Conversation</strong><span data-conversation-title>New conversation</span></div><div class="session-header-actions"><button type="button" data-browse>Conversations</button><button type="button" data-expand aria-label="Expand conversation" aria-pressed="false">Expand</button><button type="button" data-close aria-label="Close the conversation and return to reading">Close</button></div></header>
      <aside class="conversation-library" data-library hidden aria-label="Conversation library"><div class="conversation-library-fixed"><div class="conversation-library-head"><h2>Conversations</h2><button type="button" data-new>New</button></div><label class="sr-only" for="conversation-search">Find a conversation</label><input id="conversation-search" type="search" data-conversation-search placeholder="Find title, work or identity" aria-label="Find a conversation"><label class="conversation-library-filter">Show<select data-conversation-filter aria-label="Filter conversations"><option value="all">All saved</option><option value="running">Observed running</option><option value="draft">Local drafts</option></select></label></div><div data-conversation-list class="conversation-library-list"></div><footer class="conversation-library-footer"><p data-library-status role="status"></p><div class="session-controls"><button type="button" data-more>Older</button><button type="button" data-library-close>Return to reading</button></div><details><summary>Library options & coverage</summary><button type="button" data-library-refresh>Refresh list</button><p class="session-help">This project’s loaded records. Filters use recorded metadata and local drafts/observations.</p><button type="button" data-review>New independent review</button></details></footer></aside><div class="session-conversation-surface"><input type="hidden" data-sessions><div class="session-context-doors"><button type="button" data-add-local-document data-control="conversation:add-document">Add local document</button><button type="button" data-context-open data-control="conversation:context">Context</button><button type="button" data-settings-open data-control="conversation:next-message">Next message</button><button type="button" class="session-project-reviews" data-proposals hidden aria-label="Project Review & notes">Review</button><button type="button" data-refresh-turn aria-label="Refresh selected conversation">Refresh</button></div>
      <div class="session-context-summary"><p class="session-reading-brief" data-reading-brief></p><p class="session-mode-brief" data-mode-brief></p><p class="session-help error" data-composer-block hidden role="status"></p><div class="session-origin" data-origin></div><p data-message-target class="session-help"></p><p data-message-preview></p><button type="button" data-use-reading>Use reading for next message</button><button type="button" data-clear-target hidden>Clear message target</button></div>
      <section class="session-inspector" data-inspector id="workspace-session-inspector" tabindex="-1" hidden><div class="session-inspector-head"><strong data-inspector-title>Context</strong><button type="button" data-activity-open aria-label="Activity for selected conversation">Session activity</button><button type="button" data-inspector-close aria-label="Close context and settings">Close</button></div><details class="session-context-inspection" open><summary>Current reading and admitted context</summary><p class="session-scope" data-scope></p><p class="session-help" data-observation></p><button type="button" data-response-feedback>Note on this response</button><div data-context-inspection></div><div class="session-control-receipts" data-control-receipts></div></details><details class="session-settings"><summary>Next-message preferences <span data-summary></span></summary><p class="session-help" data-preference-scope></p><div data-preference-owner></div><label>Provider<select data-provider></select><span class="session-setting-origin" data-provider-origin></span></label><div class="session-model-bar session-next-model"><label>Next model<select data-model aria-label="Next-message model"></select><span class="session-setting-origin" data-model-origin></span></label><label>Effort<select data-effort aria-label="Next-message effort"></select><span class="session-setting-origin" data-effort-origin></span></label></div><div data-preference-actions class="session-controls"></div><p data-preference-status class="session-help" role="status"></p><div data-preference-authority></div><label class="session-mode-label">For the next message<select data-mode aria-label="Next message intent"><option value="work">Work on a task</option><option value="discuss">Discuss a question</option><option value="revise">Suggest writing changes</option><option value="review" hidden>Independent review conversation</option></select></label><p class="session-help" data-mode-help></p><button type="button" data-separate-review>Open separate review conversation</button><p data-model-description class="session-help"></p><p class="session-help" data-settings-truth aria-live="polite"></p><p class="session-help" data-catalogue-freshness></p><label>Wait for dispatched work (seconds)<input type="number" min="1" step="1" data-connected-observation aria-label="Wait for dispatched work (seconds)" aria-describedby="workspace-connected-observation-help"></label><p class="session-help" id="workspace-connected-observation-help">Optional, for the next author turn only. Allows one wait for dispatched work within this duration; it starts no work by itself. The task deadline is separate. Work stays recorded if the wait ends.</p><details class="session-future-defaults"><summary>Future new conversations in this project</summary><p class="session-help">Saving project defaults changes future new ordinary conversations only. Existing conversations, admitted work and workflow settings keep their own values.</p><button type="button" data-project-default>Make project default</button><div data-project-preference-status></div></details><button type="button" data-refresh>Refresh providers</button></details><div class="session-context-meter" data-context-meter aria-live="polite"><span data-context-label>Context usage available after the session starts</span><progress data-context-progress hidden></progress></div></section><div class="session-execution-summary"><p class="session-admitted-model" data-admitted-model hidden></p><p class="session-help" data-observation-brief></p></div><section data-sealed-reader hidden></section><div data-parent-continuation hidden></div><button type="button" class="session-input-attention" data-input-attention hidden aria-controls="workspace-session-inspector" aria-expanded="false">Input needs attention — inspect</button><div class="session-thread" data-thread aria-live="polite"></div>
      <form class="session-composer"><div class="session-composer-heading"><p class="session-composer-target" data-composer-target></p><button type="button" data-compose-expand aria-expanded="false" aria-controls="workspace-message">Expand message</button></div><details class="session-queue" data-queue hidden><summary data-queue-summary></summary><div data-queue-items></div></details><div class="session-selection-chip" data-selection-chip hidden><span data-selection-label></span><button type="button" data-clear-selection aria-label="Remove attached passage">×</button></div><div data-selected-action></div><label class="sr-only" for="workspace-message">Message to Eigen</label><textarea id="workspace-message" data-message rows="2" placeholder="Work through the question, evidence or structure…"></textarea>
        <div class="session-controls"><button type="button" data-stop hidden>Stop</button><button type="submit" class="primary" data-send data-control="conversation:send" disabled>Opening conversation…</button></div>
        <p class="session-help" data-legacy-draft hidden></p><p class="session-help error" data-draft-storage hidden role="alert"></p>
      </form><p class="session-status" data-status role="status">Opening conversation…</p></div>`;
    this.find=s=>host.querySelector(s);
    // Reuse the actual controls and listeners: navigation, future intent,
    // attached reading and admitted work are separate author decisions.
    const options=make('details','','session-options'),optionsTitle=make('summary','Options'),optionsBody=make('div','','session-options-body');options.dataset.sessionOptions='';options.append(optionsTitle,optionsBody);this.find('.session-conversation-surface').prepend(options);
    optionsBody.append(this.find('[data-expand]'),this.find('[data-proposals]'),this.find('[data-origin]'),this.find('[data-message-preview]'));
    const composer=this.find('.session-composer'),destination=make('section','','session-message-destination');destination.setAttribute('aria-label','Message destination and attached reading');
    destination.append(this.find('[data-message-target]'),this.find('[data-use-reading]'),this.find('[data-add-local-document]'),this.find('[data-clear-target]'),this.find('[data-context-open]'));
    destination.querySelector('[data-context-open]').textContent='Inspect context';
    const next=make('section','','session-next-decision');next.setAttribute('aria-label','Next-message intent and settings');next.append(this.find('.session-mode-label'),this.find('[data-settings-open]'),this.find('[data-mode-brief]'));next.querySelector('[data-settings-open]').textContent='Model & settings';const summary=make('p','','session-next-summary session-help');summary.setAttribute('data-next-summary','');summary.setAttribute('aria-live','polite');next.append(summary);
    composer.prepend(destination,next);
    const operation=make('p','','session-operation-state');operation.dataset.operationState='';operation.setAttribute('role','status');const execution=this.find('.session-execution-summary');execution.prepend(operation);execution.append(this.find('[data-refresh-turn]'),this.find('[data-stop]'));this.find('[data-refresh-turn]').textContent='Refresh status';this.find('[data-stop]').textContent='Stop active turn';this.find('[data-stop]').title='Ask the selected turn owner to interrupt this turn. This is not a workflow-wide stop or undo.';this.find('.session-context-doors').remove();
    // THE PANEL'S TOP ROW AND STATUS ROW (frontend redesign wave 5): what the panel reads and Options share one row, so an
    // empty conversation opens on one calm line and the box. The conversation's status is one group at the panel's foot,
    // outside the scrolling surface so it never covers a composer line: the status line ("Draft a message"), the selected
    // turn's execution words, Refresh status and the selected turn's Stop (the execution summary, moved whole).
    const readingRow=make('div','','session-reading-row');this.find('.session-conversation-surface').prepend(readingRow);readingRow.append(this.find('.session-context-summary'),options);
    execution.prepend(this.find('[data-status]'));execution.classList.add('session-status-row');host.append(execution);
    // where the thread and the composer do not both fit, the surface scrolls as one region; while more lies below its edge
    // it says so (session-more-below, drawn as a rule on the status row above the panel's foot, never over a control)
    // THE THREAD FIRST (wave 6): once the conversation has a turn, the composer stops at the bottom of its intent row (its
    // label, the box, Expand message and Send, the intent select and Model & settings) and scrolls to the rest: the two
    // notes, the chips and Use reading / Add local document / Inspect context. --composer-fold is that height, measured
    // from the composer's own rows, so the thread keeps the room (workspace.css, page: Conversation); a composer
    // that has just become capped opens at its top, on the box and Send
    const surface=this.find('.session-conversation-surface'),fold=()=>{const rows=[composer.querySelector('.session-next-decision [data-mode]'),composer.querySelector('.session-next-decision [data-settings-open]')].filter(node=>node?.getClientRects?.().length);if(!rows.length||!composer.style?.setProperty||typeof getComputedStyle!=='function')return;const box=composer.getBoundingClientRect(),bottom=Math.max(...rows.map(node=>node.getBoundingClientRect().bottom));composer.style.setProperty('--composer-fold',Math.ceil(bottom-box.top+composer.scrollTop+(parseFloat(getComputedStyle(composer).paddingBottom)||0))+'px');composer.style.setProperty('--composer-scrollbar',Math.max(0,composer.offsetWidth-composer.clientWidth)+'px');};
    const edge=()=>{fold();const capped=!!composer&&composer.scrollHeight>composer.clientHeight+1;if(capped&&!this.composerCapped)composer.scrollTop=0;this.composerCapped=capped;surface?.classList?.toggle?.('session-more-below',surface.scrollHeight-surface.scrollTop-surface.clientHeight>1);composer?.classList?.toggle?.('session-composer-more',composer.scrollHeight-composer.scrollTop-composer.clientHeight>1);};
    surface?.addEventListener?.('scroll',edge,{passive:true});composer?.addEventListener?.('scroll',edge,{passive:true});if(typeof ResizeObserver==='function'&&surface){this.surfaceEdge=new ResizeObserver(edge);for(const node of [surface,...surface.children,...composer.children])this.surfaceEdge.observe(node);}
    // Expand message works on the box, so it sits on Send's row, at its left; the line above the box names the destination
    composer.querySelector('.session-controls')?.prepend(this.find('[data-compose-expand]'));
    this.find('[data-close]').onclick=()=>{this.setLibrary(false);this.expand(false);onClose();};
    this.find('[data-proposals]').hidden=false;this.find('[data-proposals]').textContent='Review & notes';this.find('[data-proposals]').onclick=()=>this.guard(()=>this.onOpenReview());
    this.find('[data-expand]').onclick=()=>{if(this.libraryOpen)this.setLibrary(false);else this.expand(!host.closest('.workspace')?.classList.contains('session-expanded'));};
    this.mountSizing();
    this.composerSession=this.initialSession||this.readConversationSelection()||'';
    this.composerStored=this.readComposerDraft();this.find('[data-message]').value=this.composerStored;
    this.find('[data-message]').oninput=()=>{const text=this.find('[data-message]').value;this.persistComposerDraft(text);};
    this.find('[data-message]').addEventListener('change',()=>this.persistComposerDraft(this.find('[data-message]').value));
    this.find('[data-message]').addEventListener('focus',()=>this.syncComposerDraft({allowFocused:true}));
    this.onDraftStorage=event=>{if(event.storageArea===this.composerStorage&&event.key===this.composerStorageKey)this.syncComposerDraft();};window.addEventListener('storage',this.onDraftStorage);
    this.onRunningFocus=()=>{void this.observeRunning();};window.addEventListener('focus',this.onRunningFocus);this.onRunningVisibility=()=>this.runningVisibilityChanged();document.addEventListener('visibilitychange',this.onRunningVisibility);
    this.paintDraftRecovery();
    this.find('[data-clear-selection]').onclick=()=>this.clearSelection();
    this.find('[data-use-reading]').onclick=()=>this.guard(()=>this.pinMessageTarget(this.getContext()));
    this.find('[data-clear-target]').onclick=()=>this.guard(()=>this.clearMessageTarget());
    this.find('[data-compose-expand]').onclick=()=>this.setComposerExpanded(!this.composerExpanded);
    this.find('form').onsubmit=e=>{e.preventDefault();this.guard(()=>this.send());};
    this.find('[data-message]').onkeydown=e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();this.find('form').requestSubmit();}};
    this.find('[data-new]').onclick=()=>this.newConversation();
    this.find('[data-review]').onclick=()=>{this.find('[data-mode]').value='review';this.newConversation();this.status('Independent review starts separately so it does not inherit the writing conversation.');};
    this.find('[data-refresh-turn]').onclick=()=>this.guard(()=>this.refreshSelectedConversation());
    this.find('[data-more]').onclick=()=>this.guard(async()=>{if(this.libraryCatalogue){if(this.libraryNext)await this.loadLibraryCatalogue(this.libraryNext);}else{this.limit+=30;await this.loadSessions();}});
    this.find('[data-refresh]').onclick=()=>this.guard(()=>this.loadProviders(true));
    this.find('[data-browse]').onclick=()=>this.guard(()=>this.browseConversations());
    this.find('[data-library-close]').onclick=()=>this.setLibrary(false);this.find('[data-library-refresh]').onclick=()=>this.guard(()=>this.loadLibraryCatalogue());
    this.find('[data-conversation-search]').oninput=()=>this.paintConversations();
    this.find('[data-conversation-filter]').onchange=()=>this.paintConversations();
    this.find('[data-add-local-document]').onclick=()=>this.guard(()=>this.onAddLocalDocument?.());
    this.find('[data-add-local-document]').hidden=!this.onAddLocalDocument;
    this.find('[data-context-open]').onclick=()=>this.openInspector('context');
    this.find('[data-settings-open]').onclick=()=>this.openInspector('settings');
    this.find('[data-inspector-close]').onclick=()=>this.openInspector(null);
    this.find('[data-input-attention]').onclick=()=>this.inspectInputReceipts();
    this.find('[data-activity-open]').onclick=()=>this.guard(()=>this.onActivity?.({session_id:this.session}));
    this.find('[data-activity-open]').disabled=!this.onActivity;this.find('[data-response-feedback]').onclick=()=>this.guard(()=>this.noteOnResponse());
    this.find('[data-project-default]').onclick=()=>{const opening=this.preferenceOpening,values=this.preferenceUI?.values||{provider:this.find('[data-provider]').value,model:this.find('[data-model]').value,effort:this.effortSupported===false?this.savedSettings()?.effort??null:this.find('[data-effort]').value};return this.guard(async()=>{const panel=await this.preferencesInspector();if(this.preferenceOpening===opening)await panel?.projectDefault(values);},()=>this.preferenceOpening===opening);};
    host.addEventListener('keydown',event=>{if(event.key==='Escape'){if(!this.find('[data-inspector]').hidden){event.preventDefault();this.openInspector(null);}else if(!this.find('[data-library]').hidden){event.preventDefault();this.setLibrary(false);}}});
    this.find('[data-provider]').onchange=()=>this.guard(async()=>{const model=this.find('[data-model]').value,effort=this.find('[data-effort]').value;this.models(model);this.efforts(effort);this.resetUsage();await this.stagePreferences();});
    this.find('.session-settings').addEventListener('toggle',()=>{if(this.find('.session-settings').open)this.syncComposerDraft();});
    for(const selector of ['[data-model]','[data-provider]']){
      this.find(selector).addEventListener('focus',()=>this.guard(()=>this.refreshProvidersPassive()));
      this.find(selector).addEventListener('pointerdown',()=>this.guard(()=>this.refreshProvidersPassive()));
    }
    this.onCatalogueFocus=()=>{if(!this.host.hidden)this.guard(()=>this.refreshProvidersPassive());};window.addEventListener('focus',this.onCatalogueFocus);
    this.find('[data-model]').onchange=()=>this.guard(async()=>{this.efforts();this.resetUsage();await this.stagePreferences();});
    this.find('[data-effort]').onchange=()=>this.guard(async()=>{this.summary();await this.stagePreferences();});
    this.find('[data-connected-observation]').oninput=()=>this.setConnectedObservation(this.find('[data-connected-observation]').value);
    this.find('[data-mode]').value='work';
    this.find('[data-mode]').onchange=()=>{if(this.find('[data-mode]').value==='review'||this.role==='review'){this.find('[data-mode]').value=this.role==='review'?'review':this.savedMode()||'work';this.modeHelp();this.status('Independent review uses a separate conversation. Choose Open separate review conversation; your current draft and target remain here.');}else this.rememberMode();};
    this.find('[data-separate-review]').onclick=()=>{this.find('[data-mode]').value='review';this.newConversation();};
    this.find('[data-stop]').onclick=()=>this.guard(()=>this.stopSelectedTurn());
    this.onReconnect=()=>this.guard(async()=>{const epoch=this.viewEpoch;await this.refreshProvidersPassive({force:true});if(epoch!==this.viewEpoch)return;if(this.session)await this.loadSession();if(epoch!==this.viewEpoch)return;if(epoch===this.viewEpoch)this.status('Local engine reconnected. Your unsent message is preserved.');});window.addEventListener('laplace-workspace-reconnected',this.onReconnect);
    this.empty();this.scope();this.modeHelp();this.setBusy(true);this.ready=this.start();
  }
  composerStorageFailure(error,clearing=false){const message=clearing?'Message sent, but the local draft could not be cleared; it may reappear on reload.':'Browser storage could not save this draft. It remains recoverable in this tab under its original conversation.';this.draftStorageError=message;const note=this.find('[data-draft-storage]');if(note){note.hidden=false;note.classList?.add('error');note.textContent=message;}this.status(message+' '+(error?.message||String(error)),true);}
  composerStorageRecovered(){this.draftStorageError='';const note=this.find('[data-draft-storage]');if(note){note.hidden=true;note.textContent='';}}
  composerBackupKey(session=this.composerSession??this.session??''){return this.draftKey+':conversation:'+encodeURIComponent(session||'new');}
  initComposerStorage(){
    if(!this.composerStorage){let tab;try{tab=globalThis.sessionStorage;tab?.getItem(this.draftKey);}catch{tab=null;}this.composerStorage=tab||localStorage;}
    this.composerSession??=this.session||'';this.composerStorageKey=this.composerBackupKey();
  }
  readComposerDraft(){try{this.initComposerStorage();const held=this.unsavedDrafts?.get(this.composerSession||'new');if(held!=null){this.messageIntent=this.unsavedIntents?.get(this.composerSession||'new')||null;this.selectionOverride=this.messageIntent?.selection||null;return held;}const stored=this.composerStorage.getItem(this.composerStorageKey);if(stored!==null){const record=decodeComposerDraft(stored);this.messageIntent=record.intent;this.selectionOverride=record.intent?.selection||null;return record.text;}
    const backup=localStorage.getItem(this.composerBackupKey());if(backup!==null){this.composerStorage.setItem(this.composerStorageKey,backup);const record=decodeComposerDraft(backup);this.messageIntent=record.intent;this.selectionOverride=record.intent?.selection||null;return record.text;}
    // A project-wide legacy buffer has no reliable conversation identity. Its
    // own backup/restore control retains it, never a sendable target assignment.
    this.messageIntent=null;this.selectionOverride=null;this.legacyComposerDraft=this.composerStorage.getItem(this.draftKey)||localStorage.getItem(this.draftKey)||'';this.composerStorage.setItem(this.composerStorageKey,'');return '';
  }catch(error){this.composerStorageFailure(error);return this.unsavedDrafts?.get(this.composerSession||'new')||'';}}
  persistComposerDraft(value){this.unsavedDrafts??=new Map();this.unsavedDrafts.set((this.composerSession??this.session??'')||'new',value);this.unsavedIntents??=new Map();this.unsavedIntents.set((this.composerSession??this.session??'')||'new',this.messageIntent?structuredClone(this.messageIntent):null);try{this.initComposerStorage();const record=encodeComposerDraft(value,this.messageIntent);this.composerStorage.setItem(this.composerStorageKey,record);localStorage.setItem(this.composerBackupKey(),record);this.unsavedDrafts.delete(this.composerSession||'new');this.unsavedIntents.delete(this.composerSession||'new');if(value&&value===this.legacyComposerDraft){if(localStorage.getItem(this.draftKey)===value)localStorage.removeItem(this.draftKey);if(this.composerStorage.getItem(this.draftKey)===value)this.composerStorage.removeItem(this.draftKey);this.legacyComposerDraft='';}this.composerStored=value;this.composerStorageRecovered();this.paintDraftRecovery();this.paintConversations();return true;}catch(error){this.composerStorageFailure(error);return false;}}
  switchDraftTarget(session){const target=session||'';if(this.composerSession==null)this.initComposerStorage();if(this.composerSession===target&&this.composerStorageKey)return;const input=this.find('[data-message]');if(this.composerStorageKey)this.persistComposerDraft(input.value);this.composerSession=target;this.composerStorageKey=null;this.composerStored=this.readComposerDraft();input.value=this.composerStored;this.paintDraftRecovery();}
  paintDraftRecovery(){const note=this.find('[data-legacy-draft]');if(!note)return;note.hidden=!this.legacyComposerDraft;note.replaceChildren();if(!this.legacyComposerDraft)return;note.textContent='An older project draft has no known conversation target. It is preserved separately. ';const restore=make('button','Restore older draft here');restore.type='button';restore.onclick=()=>{const input=this.find('[data-message]');if(input.value.trim()){this.status('Keep the current draft before restoring the older one.');return;}input.value=this.legacyComposerDraft;this.persistComposerDraft(input.value);input.focus();};note.append(restore);}
  syncComposerDraft({allowFocused=false}={}){
    const input=this.find('[data-message]');
    // A storage failure or an unreported local edit must not be replaced remotely.
    if(this.draftStorageError||input.value!==(this.composerStored??input.value))return;
    if(!allowFocused&&globalThis.document?.activeElement===input)return;
    const stored=this.readComposerDraft();if(this.draftStorageError)return;input.value=stored;this.composerStored=stored;
  }
  clearSentDraft(submitted, {intentRevision, submittedIntent} = {}) {
    const input = this.find('[data-message]');
    if (input.value !== submitted || intentRevision !== undefined &&
        (this.intentRevision || 0) !== intentRevision || submittedIntent !== undefined &&
        !sameComposerIntent(this.messageIntent, submittedIntent)) return false;
    try {
      this.initComposerStorage();
      const stored = decodeComposerDraft(this.composerStorage.getItem(this.composerStorageKey) || '');
      if (stored.text !== submitted || submittedIntent !== undefined &&
          !sameComposerIntent(stored.intent, submittedIntent)) {
        input.value = stored.text;
        this.composerStored = stored.text;
        this.messageIntent = stored.intent;
        this.selectionOverride = stored.intent?.selection || null;
        this.intentRevision = (this.intentRevision || 0) + 1;
        this.scope();
        return false;
      }
      // Acknowledgement consumes exactly the submitted text AND its target in
      // one draft-carrier write. In particular, a sent New-conversation target
      // must not survive as a ghost attachment in an otherwise empty New slot.
      if (intentRevision !== undefined) {
        this.messageIntent = null;
        this.selectionOverride = null;
        this.intentRevision = (this.intentRevision || 0) + 1;
      }
      input.value = '';
      const cleared = this.persistComposerDraft('');
      if (cleared) this.composerStorageRecovered();
      this.scope();
      return cleared;
    } catch (error) {
      input.value = '';
      this.composerStorageFailure(error, true);
      return false;
    }
  }
  settleAdmittedDraft(pending){
    if(!pending?.admitted||pending.project!==this.project||pending.session!==this.session||pending.draft_settled)return;
    pending.draft_settled=true;this.clearSentDraft(pending.submitted,{intentRevision:pending.intentRevision,submittedIntent:pending.submittedIntent});
  }
  restorePublicationSlot(execution,active){
    if(this.controlPending||!active||execution?.turn_id!==active.id||execution.project!==this.project)return;
    const row=(execution.controls||[]).find(row=>row.turn_id===active.id&&row.delivery_mode==='project_tool_boundary'&&row.terminal!==true&&['ADMITTED','PENDING','OFFERED_AT_TOOL_BOUNDARY','PREPARING_AT_EXACT_READ','PREPARING_AT_TOOL_BOUNDARY','PREPARED_AT_TOOL_BOUNDARY','PUBLICATION_UNCONFIRMED'].includes(row.state));
    if(!row?.control_id)return;
    // A reload has no proven submitted draft association. Recover the owner slot,
    // never clear a possibly newer local draft by comparing it with old input.
    const pending={id:row.control_id,turn:row.turn_id,project:this.project,session:this.session,delivery_mode:row.delivery_mode,admitted:true,draft_settled:true};
    this.pendingControls??=new Map();this.pendingControls.set(this.session,pending);this.controlPending=pending;
  }
  pendingInputFor(session){const input=this.pendingControls?.get(session);return input?.project===this.project&&input.kind!=='native-acknowledgement'?input:null;}
  nativeAcknowledgement(){const input=this.pendingControls?.get(this.session);return input?.project===this.project&&input.kind==='native-acknowledgement'?input:null;}
  showNativeAcknowledgement(){
    const acknowledged=this.nativeAcknowledgement();if(!acknowledged)return false;
    if(!acknowledged.draft_settled){acknowledged.draft_settled=true;this.clearSentDraft(acknowledged.submitted,{intentRevision:acknowledged.intentRevision,submittedIntent:acknowledged.submittedIntent});}this.paintControlReceipts();
    this.status('Native steering acknowledged for its original turn; acting on it is not proven.');return true;
  }
  observationText(text){
    const node=this.find('[data-observation]');if(node){node.textContent=text;node.hidden=!text;}
    const brief=this.find('[data-observation-brief]');if(!brief)return;brief.hidden=!text;
    const mode=inputDeliveryMode(this.activeCapabilities||{});
    brief.textContent=this.active?(mode==='native_rpc'?'Native steering · selected turn':mode==='project_tool_boundary'?'Queued input · project-tool boundary':this.activeCapabilities?'No input capability offered · inspect Context':'Input capability unreported · inspect Context'):text;
  }
  paintParentContinuation(raw,{turnId=this.active||this.selectedTurnRecord?.id,active=!!this.active,keep=false}={}){
    if(raw==null&&keep&&this.parentContinuationError)return;
    if(raw==null&&!(keep&&this.parentContinuationValue?.turn_id===turnId)){this.parentContinuationValue=null;this.parentContinuationError=false;}
    const host=this.find('[data-parent-continuation]');if(!host)return;
    if(raw==null&&keep&&this.parentContinuationValue?.turn_id===turnId)raw=this.parentContinuationValue;
    if(raw==null){this.parentContinuationPaint=null;host.replaceChildren();host.hidden=true;return;}
    try{
      const value=parentContinuation(raw,{project:this.project,sessionId:this.session,turnId});
      const previous=this.parentContinuationValue;
      if(previous?.turn_id===turnId){
        if(previous.generation!==value.generation)throw Error('The admitted observation generation changed. Refresh its owner before continuing.');
        if(['PARENT_STOPPED','OBSERVATION_EXPIRED'].includes(previous.phase)&&value.phase==='WAITING')return;
      }
      const painted=JSON.stringify([value,active,!!this.stopRequested]);
      if(this.parentContinuationPaint===painted&&!this.parentContinuationError)return;
      const expanded=new Map([...(host.querySelectorAll?.('details')||[])].map(details=>[details.querySelector('summary')?.textContent,details.open]));
      const session=this.session,epoch=this.viewEpoch,fresh=()=>session===this.session&&epoch===this.viewEpoch&&
        this.parentContinuationValue?.turn_id===turnId&&this.parentContinuationValue?.generation===value.generation&&
        (this.active?this.active===turnId:this.selectedTurnRecord?.id===turnId);
      this.parentContinuationValue=value;this.parentContinuationError=false;host.replaceChildren();host.hidden=false;
      renderParentContinuation(host,value,{project:this.project,sessionId:session,turnId,active,compact:true,
        onOwner:this.onOpenOwner?(read,label)=>fresh()?this.guard(()=>this.onOpenOwner(read,label),fresh):undefined:
          this.onOpenWork?(read)=>fresh()?this.guard(()=>this.onOpenWork(read.id),fresh):undefined:null,
        onArtifact:this.onOpenArtifact?(path,label,options)=>fresh()?this.guard(()=>this.onOpenArtifact(path,label,options),fresh):undefined:null,
        onTurn:this.onReadTurn?(id,options)=>fresh()?this.guard(()=>this.onReadTurn(id,options),fresh):undefined:null,
        onConversation:id=>fresh()?this.guard(()=>this.openConversation(id),fresh):undefined,
        onAttach:this.role==='author'&&!this.selectedSessionRecord?.dispatch_id?async attachment=>{
          if(!fresh())throw Error('The selected conversation changed. Reinspect the retained synthesis before attaching it.');
          await projectRequest(attachment.url,attachment.payload);
          if(!fresh())return;
          await this.loadSession();
          if(fresh())this.status('Retained synthesis attached through its Work owner. Inspect Work for current acceptance.');
        }:null,
        onCancel:this.role==='author'&&!this.selectedSessionRecord?.dispatch_id?async cancellation=>{
          if(!fresh())throw Error('The selected conversation changed. Reinspect the dispatch before cancelling it.');
          await projectRequest(cancellation.url,cancellation.payload);
          if(!fresh())return;
          await this.refreshSelectedConversation();
          if(fresh())this.status('Dispatch cancellation requested. Child cleanup and parent observation have separate standing.');
        }:null,
        status:(text,error)=>{if(fresh())this.status(text,error);}});
      if(this.stopRequested&&active)host.prepend(make('p','Parent Stop requested. Dispatched work remains supervised separately.','session-help'));
      for(const details of host.querySelectorAll?.('details')||[]){const label=details.querySelector('summary')?.textContent;if(expanded.has(label))details.open=expanded.get(label);}
      this.parentContinuationPaint=painted;
    }catch(error){this.parentContinuationPaint=null;this.parentContinuationError=true;host.replaceChildren(make('p','Parent continuation needs reinspection: '+error.message,'session-help error'));host.hidden=false;}
  }
  status(text,error=false){const e=this.find('[data-status]');e.textContent=text;e.classList.toggle('error',error);}
  modeKey(){return 'laplace:mode:'+this.project+':'+(this.session||'new');}
  savedMode(){const value=localStorage.getItem(this.modeKey());return ['work','discuss','revise','review'].includes(value)?value:null;}
  rememberMode(mode=this.find('[data-mode]').value){this.find('[data-mode]').value=mode;this.modeRevision++;localStorage.setItem(this.modeKey(),mode);this.modeHelp();}
  paintNextSummary(){const node=this.find('[data-next-summary]');if(!node)return;const pending=this.messageIntent?.submission,mode=pending?.payload?.mode||this.find('[data-mode]')?.value;node.textContent=composerDecisionSummary({destination:this.find('[data-composer-target]')?.textContent||'',reading:(this.find('[data-reading-brief]')?.textContent||'').replace(/^Reading: /,''),intent:{discuss:'Discuss a question',work:'Work on a task',revise:'Suggest writing changes',review:'Independent review'}[mode]||mode||'',pending:!!pending,active:!!this.active,stopRequested:!!this.stopRequested});}
  modeHelp(){const pending=this.messageIntent?.submission,mode=pending?.payload?.mode||this.find('[data-mode]').value,brief=this.find('[data-mode-brief]');if(brief)brief.textContent=(pending?'Retained submission: ':this.active?'Next input: ':'Next message: ')+({discuss:'Discuss a question',work:'Work on a task',revise:'Suggest writing changes',review:'Independent review (separate conversation)'}[mode]||mode)+(pending?'. Original request unchanged.':'. Intent does not change permissions.');const help=this.find('[data-mode-help]');if(help)help.textContent={discuss:'Discuss the selected work and reading; project tools remain available.',work:'Work on the selected task and reading context.',revise:'Prepare manuscript suggestions for review.',review:'A separate review with project context; findings and tasks may be recorded.'}[this.find('[data-mode]').value]||'';this.paintConnectedObservation();this.paintNextSummary();}
  settingsKey(session=this.session){return 'laplace:conversation-settings:'+this.project+':'+(session||'new');}
  savedSettings(){try{return JSON.parse(localStorage.getItem(this.settingsKey())||'null');}catch{return null;}}
  expand(expanded){const root=this.host.closest('.workspace');if(!root)return;root.classList.toggle('session-expanded',expanded);const button=this.find('[data-expand]');button.textContent=expanded?'Restore':'Expand';button.setAttribute('aria-label',expanded?'Restore conversation width':'Expand conversation');button.setAttribute('aria-pressed',String(expanded));this.updateWidth?.();window.dispatchEvent(new Event('resize'));}
  mountSizing(){
    const root=this.host.closest('.workspace'),handle=this.find('[data-resize]'),editor=this.find('[data-message]');if(!root)return;
    const widthKey='laplace:workspace:conversation-width',heightKey='laplace:workspace:composer-height';
    this.requestedWidth=Number(localStorage.getItem(widthKey))||440;
    this.updateWidth=()=>{const nav=root.querySelector('.workspace-nav')?.getBoundingClientRect().width||0;const max=Math.max(320,Math.min(960,root.clientWidth-nav-300));const width=Math.max(320,Math.min(max,this.requestedWidth));root.style.setProperty('--session-width',width+'px');handle.setAttribute('aria-valuemin','320');handle.setAttribute('aria-valuemax',String(max));handle.setAttribute('aria-valuenow',String(Math.round(width)));};
    const setWidth=value=>{this.requestedWidth=value;this.updateWidth();this.requestedWidth=Number(handle.getAttribute('aria-valuenow'));localStorage.setItem(widthKey,String(this.requestedWidth));};
    handle.onpointerdown=event=>{if(event.button!==0||innerWidth<=720||root.classList.contains('session-expanded'))return;event.preventDefault();const start=event.clientX,width=this.host.getBoundingClientRect().width;handle.setPointerCapture(event.pointerId);root.classList.add('resizing-session');handle.onpointermove=move=>setWidth(width+start-move.clientX);const finish=()=>{root.classList.remove('resizing-session');handle.onpointermove=null;handle.onpointerup=null;handle.onpointercancel=null;handle.onlostpointercapture=null;window.dispatchEvent(new Event('resize'));};handle.onpointerup=finish;handle.onpointercancel=finish;handle.onlostpointercapture=finish;};
    handle.ondblclick=()=>setWidth(440);handle.onkeydown=event=>{const width=this.host.getBoundingClientRect().width;if(event.key==='ArrowLeft')setWidth(width+24);else if(event.key==='ArrowRight')setWidth(width-24);else if(event.key==='Home')setWidth(320);else if(event.key==='End')setWidth(Number(handle.getAttribute('aria-valuemax')));else return;event.preventDefault();};
    const height=Number(localStorage.getItem(heightKey));if(height>=92)editor.style.height=height+'px';
    this.editorResize=new ResizeObserver(()=>{const height=editor.getBoundingClientRect().height;if(height>=92)localStorage.setItem(heightKey,String(Math.round(height)));});this.editorResize.observe(editor);
    this.updateWidth();window.addEventListener('resize',this.updateWidth);
  }
  async guard(work,isCurrent=()=>true){try{await work();}catch(error){if(isCurrent())this.status(error.message,true);}}
  async usePreparedWork(action, task) {
    const payload = preparedRunSubmission(action, this.project, task);
    if (payload.session_id) {
      if (this.session !== payload.session_id && !await this.openConversation(payload.session_id)) {
        throw Error('The recorded parent conversation could not open. Your draft is retained.');
      }
      if (this.session !== payload.session_id || this.active) {
        throw Error('Inspect the recorded parent turn before resuming. No new message was prepared.');
      }
    } else if (this.active || this.role !== 'author' || this.selectedSessionRecord?.dispatch_id) {
      if (!this.newConversation()) throw Error('Open an idle author conversation before preparing this message.');
    }
    this.compose(payload.text, 'work');
    this.pinMessageTarget({surface: 'structure', label: task.title || task.id,
      section_ids: task.section_ids || []}, task);
    const retained=preparedParentContinuations(task,task.prepared_execution,this.project);
    this.status(retained.length?'Continuation message prepared. Send starts a new provider turn in the recorded parent conversation; choose any connected wait for this new draft explicitly.':'Prepared Work attached. Review the message, then Send to start provider work.');
  }
  async useWorkflowAction(raw) {
    const action=workflowConversationAction(raw,this.project),payload=action.payload;
    await this.ready;
    if(this.submitting||this.initializing||this.loadingSession||this.startupFailed)throw Error('Wait for this conversation to open before preparing the workflow request.');
    if(payload.session_id){
      if(this.session!==payload.session_id&&!await this.openConversation(payload.session_id))throw Error('The original preparation conversation could not open.');
      if(this.session!==payload.session_id||this.active||this.role!=='author'||this.selectedSessionRecord?.dispatch_id)throw Error('Open the idle original author conversation before preparing Start.');
    }else if(this.active||this.role!=='author'||this.selectedSessionRecord?.dispatch_id){
      if(!this.newConversation())throw Error('Open an idle author conversation before preparing the workflow request.');
    }
    this.syncComposerDraft({allowFocused:true});const existing=this.find('[data-message]').value;
    if(existing.trim())throw Error('This conversation already has a message draft. Its text and target are retained; send, save or clear it before preparing another workflow request.');
    if(this.messageIntent?.submission)throw Error('Check the retained submission before preparing another request.');
    this.clearMessageTarget();this.compose(payload.text,payload.mode);
    if(payload.work_id)this.pinMessageTarget({surface:'project',label:action.work_target.title||payload.work_id,...(payload.workspace_context?.workflow_action?{workflow_action:payload.workspace_context.workflow_action}:{})},action.work_target);
    if(payload.workspace_context?.workflow_action){this.messageIntent.action_summary=workflowActionSummary(action.action_context);this.messageIntent.action_read=structuredClone(action.action_context.read||action.read);this.persistComposerDraft(this.find('[data-message]').value);this.scope();}
    if(this.draftStorageError)throw Error('The prepared message is visible but its recovery could not be stored. Keep the page open; nothing was sent.');
    this.status('Workflow request prepared. Review the message and Send explicitly; no dispatch was started.');
    return true;
  }
  workflowActionConsumer(){return this.workflowActionService??=new WorkspaceWorkflowAction(this,projectRequest);}
  persistActionDraft(...args){return this.workflowActionConsumer().persistActionDraft(...args);}
  paintSelectedAction(...args){return this.workflowActionConsumer().paintSelectedAction(...args);}
  paintActionInspector(...args){return this.workflowActionConsumer().paintActionInspector(...args);}
  inspectWorkflowAction(...args){return this.workflowActionConsumer().inspectWorkflowAction(...args);}
  useInspectedWorkflowAction(...args){return this.workflowActionConsumer().useInspectedWorkflowAction(...args);}
  submitActionPayload(...args){return this.workflowActionConsumer().submitActionPayload(...args);}
  postActionSubmission(...args){return this.workflowActionConsumer().postActionSubmission(...args);}
  retryActionSubmission(...args){return this.workflowActionConsumer().retryActionSubmission(...args);}
  reconcileActionSubmission(...args){return this.workflowActionConsumer().reconcileActionSubmission(...args);}
  authoredContext() {
    return this.messageIntent?.context || {surface: 'project', label: 'Project'};
  }
  localDocumentTarget(){return {session_id:this.session||'',context:structuredClone(this.authoredContext())};}
  useLocalDocument(read,label,target,{epoch=this.viewEpoch,intentRevision=this.intentRevision||0}={}){
    if(readerSession(this.selectedSessionRecord))throw Error('This text-only reader keeps its sealed input. Open an ordinary conversation before selecting this document.');
    if(this.messageIntent?.submission)throw Error('Check the retained message submission before changing its document reading.');
    if(epoch!==this.viewEpoch||intentRevision!==(this.intentRevision||0)||(this.session||'')!==target.session_id||!sameComposerIntent(this.authoredContext(),target.context))throw Error('The original conversation or message target changed. Your document and draft are retained; return to that conversation before using the reading.');
    if(this.authoredContext().workflow_action)throw Error('Clear the selected action explicitly before attaching a document reading.');
    const pointer=materialReadingInput(read,{project:this.project}),context={...structuredClone(this.authoredContext()),material_read:pointer};
    if(context.surface==='project'&&context.label==='Project'||context.surface==='sources'&&this.authoredContext().material_read){context.surface='sources';context.label=String(label||'Selected local document').slice(0,240);}
    this.messageIntent={...(this.messageIntent||{}),context,selection:this.selectionOverride||null,material_label:String(label||'Selected document').slice(0,240)};
    this.intentRevision=(this.intentRevision||0)+1;this.persistComposerDraft(this.find('[data-message]').value);this.scope();this.status('Document reading selected for this conversation. Send remains explicit.');
  }
  useResearchObject(pointer,label,target,{epoch=this.viewEpoch,intentRevision=this.intentRevision||0}={}){
    if(readerSession(this.selectedSessionRecord))throw Error('This reader keeps its sealed input. Choose an ordinary conversation for the object.');
    if(this.messageIntent?.submission)throw Error('Check the retained message submission before changing its object context.');
    if(epoch!==this.viewEpoch||intentRevision!==(this.intentRevision||0)||(this.session||'')!==target.session_id||!sameComposerIntent(this.authoredContext(),target.context))throw Error('The conversation or message target changed after opening this object. Reopen the action from the intended conversation.');
    if(this.authoredContext().workflow_action)throw Error('Clear the selected action before attaching an object context.');
    const context={...structuredClone(this.authoredContext()),object_context:objectContextInput(pointer)};
    if(context.surface==='project'&&context.label==='Project'){context.surface='project';context.label=String(label||'Selected research object').slice(0,240);}
    this.messageIntent={...(this.messageIntent||{}),context,selection:this.selectionOverride||null,object_label:String(label||'Selected research object').slice(0,240)};
    this.intentRevision=(this.intentRevision||0)+1;this.persistComposerDraft(this.find('[data-message]').value);this.scope();this.status('Object context selected. Your message is unchanged; Send remains explicit.');
  }
  pinMessageTarget(reading = this.getContext(), work = null) {
    if(readerSession(this.selectedSessionRecord))throw Error('This text-only reader retains its admitted input. Prepare an explicit fresh reader instead.');
    if(this.messageIntent?.context?.workflow_action&&!reading.workflow_action)throw Error('The selected action keeps its original Work. Clear the message target before replacing its context.');
    const context = messageTarget(reading.review ? reading : sourceOnlyProposalContext(reading, work ? this.selectionOverride : reading.selection), work);
    if(work&&this.authoredContext().material_read&&!context.material_read)context.material_read=structuredClone(this.authoredContext().material_read);
    if(work&&this.authoredContext().object_context&&!context.object_context)context.object_context=structuredClone(this.authoredContext().object_context);
    // Choosing a passage changes the attachment. Choosing Work changes the
    // execution subject while retaining the explicitly attached passage.
    if (!work && this.messageIntent?.context?.task_id) {
      for (const key of ['task_id', 'work_label', 'expected_work_scope_revision', 'expected_dependency_revision']) {
        context[key] = this.messageIntent.context[key];
      }
    }
    const selection = work ? this.selectionOverride : reading.selection;
    this.selectionOverride = selection ? structuredClone(selection) : null;
    this.intentRevision = (this.intentRevision || 0) + 1;
    this.messageIntent = {...(this.messageIntent||{}),context, selection: this.selectionOverride};
    this.persistComposerDraft(this.find('[data-message]').value);
    this.scope();
    this.status('Message target retained. Reading elsewhere will keep this target.');
  }
  clearMessageTarget() {
    if(this.messageIntent?.submission)throw Error('Check the retained submission before clearing its target. Its outcome is unresolved.');
    this.workflowActionDetail=null;this.workflowActionProposal=null;this.workflowActionProposalBasis=null;this.workflowActionIssue=null;this.workflowActionIssueBasis=null;
    this.intentRevision = (this.intentRevision || 0) + 1;
    const budget=this.messageIntent?.connected_observation_seconds;
    this.messageIntent = budget===undefined?null:{context:{surface:'project',label:'Project'},selection:null,connected_observation_seconds:budget};
    this.selectionOverride = null;
    this.persistComposerDraft(this.find('[data-message]').value);
    this.scope();
  }
  setSelection(value) {
    // Passage commands are explicit author acts, unlike scrolling.
    this.pinMessageTarget({...this.getContext(), selection: value});
  }
  setConnectedObservation(raw) {
    if(this.active||this.submitting||this.loadingSession||this.initializing||this.role!=='author'||this.selectedSessionRecord?.dispatch_id||this.find('[data-mode]').value!=='work')return;
    this.messageIntent={...(this.messageIntent||{context:{surface:'project',label:'Project'},selection:this.selectionOverride||null})};
    if(raw==='')delete this.messageIntent.connected_observation_seconds;
    else this.messageIntent.connected_observation_seconds=Number(raw);
    this.intentRevision=(this.intentRevision||0)+1;
    this.persistComposerDraft(this.find('[data-message]').value);
    this.paintConnectedObservation();
  }
  paintConnectedObservation() {
    const input=this.find('[data-connected-observation]');if(!input)return;
    const value=this.messageIntent?.connected_observation_seconds;input.value=value===undefined?'':String(value);
    input.disabled=!!this.active||!!this.submitting||!!this.loadingSession||!!this.initializing||this.role!=='author'||!!this.selectedSessionRecord?.dispatch_id||this.find('[data-mode]').value!=='work';
  }
  clearSelection() {
    this.intentRevision = (this.intentRevision || 0) + 1;
    this.selectionOverride = null;
    if (this.messageIntent) {
      const {selection, ...context} = this.messageIntent.context;
      this.messageIntent = {...this.messageIntent,context, selection: null};
      this.persistComposerDraft(this.find('[data-message]').value);
    }
    this.scope();
  }
  paintSelection(){const chip=this.find('[data-selection-chip]');if(!chip)return;chip.hidden=!this.selectionOverride;const anchor=this.selectionOverride?.anchor||{},text=this.selectionOverride?.quote||[anchor.file,anchor.line_start].filter(Boolean).join(':');const fileOnly=fileOnlyManuscriptSelection(this.selectionOverride);this.find('[data-selection-label]').textContent=fileOnly?'Source files: '+this.selectionOverride.files.join(', '):'Attached passage: '+String(text||'selected manuscript passage').slice(0,130);this.find('[data-clear-selection]').ariaLabel=fileOnly?'Remove source files':'Remove attached passage';}
  // scope() is where the shell tells the conversation that the reading moved; onScope lets the shell's where-am-I line follow
  scope(){try{this.onScope?.();}catch{/* the header is the shell's; the conversation still paints its own scope */}paintReaderSession(this);this.paintSelectedAction();this.paintConnectedObservation();const feedback=this.find('[data-response-feedback]');if(feedback)feedback.disabled=!this.selectedTurnRecord?.reply?.id;const target=this.find('[data-composer-target]');if(target){const selected=this.session||this.composerSession;const saved=this.sessionRows?.find(row=>row.id===selected),targetTitle=saved?.title||this.selectedConversationTitle||selected;target.textContent=this.active?(inputDeliveryMode(this.activeCapabilities||{})==='project_tool_boundary'?'Queued-input target: ':'Steering ')+targetTitle+(!this.activeCapabilities?' · Refresh status before steering.':''):selected?'Follow-up in '+targetTitle:'New conversation';}const context=this.getContext(),intent=this.authoredContext();const readingBrief=this.find('[data-reading-brief]');if(readingBrief)readingBrief.textContent='Reading: '+(context.label||'This project');this.modeHelp();const retained=!!this.messageIntent&&(!!this.selectionOverride||intent.surface!=='project'||intent.label!=='Project'||Object.keys(intent).some(key=>!['surface','label'].includes(key)));const targetNote=this.find('[data-message-target]');if(targetNote&&typeof targetNote.replaceChildren!=='function')targetNote.textContent='Message target: '+(intent.work_label||intent.label||'Project')+(retained?' · retained':' · no reading attached');else if(targetNote){
      // THE TARGET CHIP ROW (M5 C8): target, attached reading and intent as chips; Clear stays
      // the one action beside them and appears only when something is retained
      const anchor=this.selectionOverride?.anchor||{};
      targetNote.replaceChildren(chipRow([{label:intent.work_label||intent.label||'Project',tone:'neutral',title:'Message target'},
        retained?{label:intent.workflow_action?'Action context attached':intent.object_context?'Object context attached':intent.material_read?'Document reading attached':this.selectionOverride?'Passage attached'+(anchor.file?' · '+String(anchor.file).split('/').pop():''):'Reading context selected',tone:'neutral',title:intent.workflow_action?'Selected owner action; checked on Send':'Retained with the next message'}:{label:'No reading attached',tone:'neutral'},
        ]));targetNote.setAttribute('data-control','conversation:target');targetNote.title='Message target: '+(intent.work_label||intent.label||'Project')+(retained?' · retained':' · no reading attached');}const preview=this.find('[data-message-preview]');if(preview){const rows=nextMessagePreview(intent,this.selectionOverride,{project:this.project,label:this.messageIntent?.material_label});preview.textContent='Next message: '+rows.map(row=>row.title+' · '+(row.kind==='selection'?'Selected passage (inspect Context for exact words)':row.extent)).join(' · ');}const clear=this.find('[data-clear-target]');if(clear)clear.hidden=!retained;const useReading=this.find('[data-use-reading]');if(useReading)useReading.hidden=!!intent.workflow_action||readerSession(this.selectedSessionRecord);this.paintSelection();if(this.active&&this.activeScope){this.find('[data-scope]').textContent='Active turn work: '+this.activeScope+' · Reading: '+(context.label||'this project')+'.';this.paintContext(context);return;}this.find('[data-scope]').textContent='Reading: '+(context.label||'This project');this.paintContext(context);}

  paintContext(context=this.getContext()){
    const originHost=this.find('[data-origin]'),detail=this.find('[data-context-inspection]');
    if(originHost){
      originHost.replaceChildren();
      const recorded=this.origin?.workId,next=this.authoredContext().task_id;
      const workLink=(caption,id)=>{const label=id===next?this.authoredContext().work_label||id:id;
        const open=make('button',caption);open.type='button';open.title=label+' · '+id;
        open.setAttribute('aria-label',caption+': '+label+' · '+id);
        open.onclick=()=>this.guard(()=>this.onOpenWork?.(id));open.disabled=!this.onOpenWork;originHost.append(open);};
      if(recorded&&(this.active||recorded!==next))workLink(this.active?'Admitted work':'Recorded work',recorded);
      if(next&&(!this.active||recorded!==next))workLink('Next-message work',next);
    }
    if(!detail)return;detail.replaceChildren();
    if(this.authoredContext().workflow_action){this.paintActionInspector(detail);return;}
    detail.append(make('p',this.active?'Input goes to this admitted turn. Reading elsewhere preserves the authored attachment.':'Reading is separate from the retained message target. Use reading explicitly to attach it.'));const intent=this.authoredContext();detail.append(make('h4','Next message context'));for(const row of nextMessagePreview(intent,this.selectionOverride,{project:this.project,label:this.messageIntent?.material_label})){const item=make('section','','message-context-preview');item.append(make('strong',row.title),make(row.kind==='selection'?'blockquote':'p',row.extent));if(row.identity){const exact=make('details');exact.append(make('summary','Exact attachment identity'),make('pre',JSON.stringify(row.identity,null,2)));item.append(exact);}detail.append(item);}
    const selection=this.selectionOverride||{};
    const facts=[['Conversation',this.sessionRows?.find(row=>row.id===this.session)?.title||this.selectedConversationTitle||this.session||'New conversation'],['Project',this.project],[this.active?'Admitted work':'Recorded work',this.origin?.workId||'No recorded work association'],['Next-message work',intent.task_id||'No selected work'],['Reading view',context.surface||'project'],['Reading location',context.label||'Project'],['Writing files',(selection.files||[]).join(', ')||'No writing file attachment'],['Plan object targets',[intent.node_id,...(intent.node_ids||[])].filter(Boolean).join(', ')||'No plan object target'],['Target plan sections',(intent.section_ids||selection.section_ids||[]).join(', ')||'None selected']];
    for(const [name,value]of facts)detail.append(make('p',name+': '+value));
    if(this.origin?.packet)detail.append(make('p','Packet: '+this.origin.packet));
    if(this.origin?.parentTurnId&&this.onReadTurn){const parent=this.origin.parentTurnId,read=make('button','Read exact parent turn');read.type='button';read.onclick=()=>this.guard(()=>this.onReadTurn(parent));detail.append(read);}
    if(this.selectionOverride)detail.append(make('p','Explicit attachment: '+(this.selectionOverride.draft?'unsaved draft; saved source is separate':'selected source; exact currentness is checked where the owner supplied an observation')));
    if(this.selectedTurnRecord){const turn=this.selectedTurnRecord;detail.append(make('h4','Recorded turn'),make('p','Response intent: '+(turn.mode||'Not recorded')),make('p','Admitted work: '+(turn.work_id||turn.dispatch_id||'No recorded work association')));if(this.onReadTurn){const exact=make('button','Read exact admitted context and turn');exact.type='button';exact.onclick=()=>this.guard(()=>this.onReadTurn(turn.id));detail.append(exact);}const recorded=make('details');recorded.append(make('summary','Audit recorded turn basis'));lazyContent(recorded,()=>recorded.append(make('pre',JSON.stringify({turn_id:turn.id,mode:turn.mode,workspace_context:turn.workspace_context,selection:{files:turn.selection?.files,section_ids:turn.selection?.section_ids,anchor:turn.selection?.anchor?{file:turn.selection.anchor.file,line_start:turn.selection.anchor.line_start,line_end:turn.selection.anchor.line_end}:undefined,quote_chars:turn.selection?.quote_chars??(typeof turn.selection?.quote==='string'?turn.selection.quote.length:turn.selection?.quote_omitted?'uninspected · summary_read':0),unsaved_draft_chars:turn.unsaved_draft?.text_chars??(typeof turn.unsaved_draft?.text==='string'?turn.unsaved_draft.text.length:turn.unsaved_draft?'uninspected · summary_read':0)},work_basis:turn.work_basis??(turn.detail?'uninspected · summary_read':undefined),basis:'thread row counts; exact words and basis on the saved turn read'},null,2))));detail.append(recorded);}
    const framing=make('details');framing.append(make('summary','Project framing and specialised readers'),make('p','An ordinary conversation includes project framing and argument. A source-only blind reader is a separate supported intake, not a switch in this control.','session-help'));detail.append(framing);
  }

  empty(){this.find('[data-thread]').replaceChildren(make('p',this.session?'No messages in this conversation yet.':'Ask a question or choose saved work from Conversations.','session-empty'));}
  rememberConversationSelection(id,{projectDefault=true}={}){
    this.tabSelection=id||'';
    try{globalThis.sessionStorage?.setItem(this.key,this.tabSelection);}catch{/* Restricted storage retains this view's in-memory selection. */}
    if(projectDefault)try{if(id)localStorage.setItem(this.key,id);else localStorage.removeItem(this.key);}catch{/* The tab's selection remains usable when project storage is restricted. */}
  }
  readConversationSelection(){
    if(this.tabSelection!==undefined)return this.tabSelection;
    let selected=null;try{selected=globalThis.sessionStorage?.getItem(this.key)??null;}catch{}
    if(selected===null){try{selected=localStorage.getItem(this.key)||'';}catch{selected='';}this.rememberConversationSelection(selected,{projectDefault:false});}
    else this.tabSelection=selected;return this.tabSelection;
  }
  async start(){for(const node of [this.find('[data-status]'),this.find('[data-send]')])if(String(node?.textContent||'').endsWith('…'))pendingRead(node);this.initializing=true;this.startupFailed=false;this.startupResourcesReady=false;this.setBusy(true);this.initComposerStorage();const epoch=this.viewEpoch,settingsRevision=this.settingsRevision;let loaded=false;await this.guard(async()=>{await Promise.all([this.loadProviders(),this.loadSessions(),this.loadQueue()]);if(epoch!==this.viewEpoch)return;this.startupResourcesReady=true;const requested=this.initialSession;this.initialSession='';this.session=requested||this.readConversationSelection();this.switchDraftTarget(this.session);this.controlPending=this.pendingInputFor(this.session);if(this.session){try{await this.loadSession();if(requested&&epoch===this.viewEpoch)this.rememberConversationSelection(this.session);}catch(error){if(requested){this.initialSession=requested;this.session='';this.empty();}this.status(error.message,true);return;}}else{if(settingsRevision===this.settingsRevision)this.applySettings(this.savedSettings()||this.preferences);this.status('Draft a message');}loaded=true;});if(epoch===this.viewEpoch){this.initializing=false;this.startupFailed=!loaded;this.setBusy(!!this.active);}void this.observeRunning();}

  catalogueOpened(){this.syncComposerDraft();return this.guard(()=>this.refreshProvidersPassive({force:true}));}
  async refreshProvidersPassive({force=false}={}){
    if(this.providerRequest)return this.loadProviders(false);
    if(!force&&this.providerCatalogueReadAt&&Date.now()-this.providerCatalogueReadAt<1000)return;
    return this.loadProviders(false);
  }
  async loadProviders(refresh=false){
    if(this.providerRequest){
      if(!refresh||this.providerRequestLive)return this.providerRequest;
      await this.providerRequest;return this.loadProviders(true);
    }
    this.providerCatalogueReadAt=Date.now();this.providerRequestLive=refresh;
    const request=this.readProviderCatalogue(refresh);this.providerRequest=request;
    try{return await request;}finally{if(this.providerRequest===request){this.providerRequest=null;this.providerRequestLive=false;}}
  }
  async readProviderCatalogue(refresh=false){
    const revision=this.settingsRevision;
    const [catalogue,preferenceResponse]=await Promise.all([projectRequest('/authoring/providers'+(refresh?'?refresh=1':'')),this.preferences?Promise.resolve({preferences:this.preferences,settings_read:this.projectSettingsRead}):projectRequest('/work/session-preferences?project='+encodeURIComponent(this.project))]);
    const {preferences}=preferenceResponse;this.projectSettingsRead=preferenceResponse.settings_read||this.projectSettingsRead;const {providers,model_choice}=catalogue;
    // Read the selection at completion. A choice made during the passive fetch wins.
    const previous={provider:this.find('[data-provider]').value,model:this.find('[data-model]').value,effort:this.find('[data-effort]').value};
    this.providers=providers;this.modelChoice=model_choice;if(revision===this.settingsRevision||!this.preferences)this.preferences=preferences;
    // Catalogue freshness is a fact the person can act on: the dropdown names come from
    // the passive catalogue (possibly an earlier discovery); the admitted turn reports the
    // exact resolved model separately. Refresh providers re-discovers; nothing is hardcoded.
    const freshness=this.find('[data-catalogue-freshness]');
    if(freshness){const observed=Number(catalogue.observed_at);const age=Number.isFinite(observed)&&observed>0?Math.max(0,Date.now()/1000-observed):null;
      const ago=age===null?'':age<90?'just now':age<5400?Math.round(age/60)+' min ago':age<172800?Math.round(age/3600)+' h ago':Math.round(age/86400)+' d ago';
      freshness.textContent=(catalogue.cached?'Model list from the saved catalogue':'Model list discovered live')+(ago?', observed '+ago:'')+'. Names here may lag the installed runtime; the admitted turn shows the exact resolved model. Use Refresh providers to re-discover.';}
    const select=this.find('[data-provider]');select.replaceChildren();
    for(const provider of providers){const option=make('option',provider.name+(provider.available?'':' · unavailable'));option.value=provider.id;option.disabled=!provider.available;select.append(option);}
    const preferred=previous.provider||this.preferences?.provider;
    if(preferred&&!providers.some(provider=>provider.id===preferred)){const option=make('option',preferred+' · unavailable');option.value=preferred;option.disabled=true;select.append(option);}
    select.value=preferred||providers.find(provider=>provider.available)?.id||'';
    const model=previous.provider?previous.model:this.preferences?.provider===select.value?this.preferences.model:undefined;
    const effort=previous.provider?previous.effort:this.preferences?.effort;
    this.models(model);this.efforts(effort);
  }
  // The preselected model is the ENGINE's session default (`session_default`, derived from
  // src/laplace/pipeline/schema.py TIERS/ROLE_TIER by writing_provider.with_model_choice),
  // not the vendor's own `default` flag: that flag is still in the catalogue because it is
  // the provider's own statement, and this pane no longer decides anything by it.
  models(preferred,{advertisedOnly=false}={}){if(this.initializing&&this.initialSession&&!this.session){const select=this.find('[data-model]'),option=make('option','Loading selected conversation…');option.value='';select.replaceChildren(option);select.value='';select.disabled=true;return;}const provider=this.providers.find(row=>row.id===this.find('[data-provider]').value),select=this.find('[data-model]');select.replaceChildren();for(const model of providerModelOptions(provider)){const option=make('option',model.name);option.value=model.id;select.append(option);}let wanted=preferred!==undefined?preferred:(this.preferences?.provider===provider?.id?this.preferences.model:undefined);if(advertisedOnly&&!provider?.models.some(model=>model.id===wanted))wanted=undefined;if(wanted!=null&&!provider?.models.some(model=>model.id===wanted)){const option=make('option',wanted?'Retained literal: '+wanted:'Configured model');option.value=wanted;select.append(option);}select.value=wanted??provider?.models.find(model=>model.session_default)?.id??provider?.models[0]?.id??'';this.efforts();if(!this.session){this.showUsage(null,provider?.models.find(model=>model.id===select.value));this.settingsTruth(null);}}

  applySettings(values){
    if(!values?.provider)return;
    const select=this.find('[data-provider]');
    if(typeof select.append==='function'&&!this.providers.some(provider=>provider.id===values.provider)&&![...(select.options||[])].some(option=>option.value===values.provider)){
      const option=make('option',values.provider+' · unavailable');option.value=values.provider;option.disabled=true;select.append?.(option);
    }
    select.value=values.provider;this.models(values.model);this.efforts(values.effort);
  }

  async preferencesInspector(){
    if(this.preferencesDisposed)return null;
    if(!this.preferenceUI){if(!this.preferenceLoading)this.preferenceLoading=import('./session-preferences.mjs').then(({mountSessionPreferences})=>{if(this.preferencesDisposed)return null;return this.preferenceUI=mountSessionPreferences(this,{request:projectRequest,readFor:target=>{if(target.kind==='project-defaults')return this.projectSettingsRead;if(target.session_id!==this.session)throw Error('Open the original conversation to inspect its settings.');return this.sessionSettingsRead;}});});await this.preferenceLoading;}
    return this.preferenceUI;
  }
  async stagePreferences(){this.settingsRevision++;const opening=this.preferenceOpening,session=this.session,panel=await this.preferencesInspector();if(opening!==this.preferenceOpening||session!==this.session)return;panel?.stage();this.settingsTruth(this.selectedSessionRecord);}
  async savePreferences(){const opening=this.preferenceOpening,session=this.session,panel=await this.preferencesInspector();if(opening===this.preferenceOpening&&session===this.session)return panel?.saveCurrent();}
  preferenceBlockReason(){
    try{if(this.preferenceUI)return this.preferenceUI.blockSend();for(const target of [this.session,'project-defaults']){const raw=JSON.parse(localStorage.getItem(this.settingsKey(target))||'{}'),held=preferenceDraftEnvelope(raw);if(held?.pending)return 'Check or withdraw the original settings save before Send. Nothing was retried.';if(target===this.session&&this.session&&held?.dirty)return 'Save or discard the next-message settings edits before Send.';}}catch{return 'The local settings draft cannot be read. Inspect Next message before Send.';}
    return this.settingsFailed?'An earlier settings save was not acknowledged. Inspect Next message before Send; nothing was retried.':'';
  }
  applyFutureDefaults(values){
    this.preferences={...values};
    // New-conversation preferences may predate the project default. Update that
    // cache without touching this conversation's controls or saved settings.
    try{localStorage.setItem(this.settingsKey(''),JSON.stringify(values));}catch{try{localStorage.removeItem(this.settingsKey(''));}catch{}}
  }
  async saveProjectDefaults(values){const opening=this.preferenceOpening,panel=await this.preferencesInspector();if(opening===this.preferenceOpening)return panel?.projectDefault(values);}
  efforts(preferred){
    const provider=this.providers.find(p=>p.id===this.find('[data-provider]').value),model=provider?.models.find(m=>m.id===this.find('[data-model]').value),select=this.find('[data-effort]');let old=preferred!==undefined?preferred:select.value;
    // A capability toggle changes the available control, not the author's retained choice.
    if(preferred===null)this.retainedEffort=null;else if(old!=null&&old!=='')this.retainedEffort=old;else if(this.retainedEffort!==undefined)old=this.retainedEffort;
    this.effortSupported=model?.supports_effort!==false;const values=this.effortSupported?[...providerEffortOptions(model)]:[''];if(this.effortSupported&&old===null)values.unshift('');else if(this.effortSupported&&old!=null&&old!==''&&!values.includes(old))values.push(old);
    select.replaceChildren(...values.map(v=>{const option=make('option',!this.effortSupported?'Automatic — no effort flag':v===''?'Retained automatic value — select an offered effort':v);option.value=v;return option;}));select.value=this.effortSupported?(old===null?'':old!=null&&values.includes(old)?old:values.includes('medium')?'medium':values[0]):'';
    select.disabled=!!this.active||!!this.loadingSession||!!this.submitting||!!this.initializing||!this.effortSupported;if(select.parentElement)select.parentElement.hidden=false;this.find('[data-model-description]').textContent=model?.description||'';this.summary();
  }
  summary(){this.find('[data-summary]').textContent=this.find('[data-provider]').value==='claude'?'Claude':'Codex';this.paintAdmittedModel();}
  paintAdmittedModel(){const node=this.find('[data-admitted-model]');if(!node)return;node.hidden=!this.active;if(this.active){const values=this.admittedSettings;node.textContent='Admitted: '+(values?[values.provider,values.model,'effort '+(values.effort??'Automatic')].filter(Boolean).join(' · '):'model and effort not reported');}}
  setComposerExpanded(expanded){this.composerExpanded=!!expanded;this.host.classList.toggle('composer-expanded',this.composerExpanded);const button=this.find('[data-compose-expand]');button.setAttribute('aria-expanded',String(this.composerExpanded));button.textContent=this.composerExpanded?'Compact message':'Expand message';}
  inspectInputReceipts(){
    this.openInspector('context','[data-input-attention]');
    const detail=this.find('[data-control-receipts]')?.querySelector('details');
    if(detail){detail.open=true;detail.querySelector('summary')?.focus();}
  }
  openInspector(tab,opener=null){
    const inspector=this.find('[data-inspector]');if(!inspector)return;inspector.hidden=!tab;this.preferenceOpening=Symbol('settings opening');if(tab==='settings'){const opening=this.preferenceOpening;this.guard(async()=>{const panel=await this.preferencesInspector();if(this.preferenceOpening===opening&&!this.find('[data-inspector]').hidden&&this.find('.session-settings').open)await panel?.open();},()=>this.preferenceOpening===opening);}
    if(tab)this.inspectorOpener=opener||(tab==='settings'?'[data-settings-open]':'[data-context-open]');
    for(const [name,selector]of [['context','[data-context-open]'],['settings','[data-settings-open]'],['context','[data-input-attention]']])this.find(selector)?.setAttribute('aria-expanded',String(tab===name));
    if(tab){const settings=this.find('.session-settings'),context=this.find('.session-context-inspection');settings.open=tab==='settings';context.open=tab==='context';
      this.find('[data-inspector-title]').textContent=tab==='settings'?'Next message':'Context';
      this.find('[data-preference-scope]').textContent=this.session?'Changes apply to this conversation’s future messages. Admitted turns keep their original settings. Preferences are locked while a turn is active.':'Choices apply when you send the first message. Project defaults change only with Make project default.';
      inspector.focus?.({preventScroll:true});
    }else{const target=this.find(this.inspectorOpener||'[data-context-open]');(target&&!target.hidden?target:this.find('[data-context-open]'))?.focus();}
  }

  setLibrary(open){const library=this.find('[data-library]');if(!library)return;library.hidden=!open;const root=this.host.closest('.workspace');root?.classList.toggle('session-library-open',open);if(open&&!this.libraryOpen){this.libraryOpen=true;this.libraryWasExpanded=root?.classList.contains('session-expanded');this.expand(true);this.paintConversations();this.find('[data-conversation-search]')?.focus();}else if(!open){this.libraryOpen=false;this.expand(false);this.find('[data-browse]')?.focus();}}
  async browseConversations(){this.setLibrary(true);const known=this.libraryCatalogue;await this.refreshConversationChoices();if(!known)await this.loadLibraryCatalogue();}
  async loadLibraryCatalogue(handle=null){
    const ticket=this.listLoad=(this.listLoad||0)+1,previous=this.sessionRows||[],labels=new Map(previous.map(row=>[row.id,row.title]));try{const path=handle?analyticsReadURL(handle,{project:this.project,projection:'sessions',scope:'project',expectedQuery:analyticsQuery(this.project,'sessions')}):analyticsQuery(this.project,'sessions'),value=analyticsEnvelope(await projectRequest(path),{project:this.project,projection:'sessions',scope:'project',expectedQuery:analyticsQuery(this.project,'sessions')});if(ticket!==this.listLoad)return;if(handle&&value.as_of!==this.libraryCut)throw Error('Conversation history changed between pages. Refresh the library; no pages were mixed.');if(value.items.some(row=>row.project!==this.project||typeof row.id!=='string'||!row.id))throw Error('A conversation summary does not match this project identity.');const rows=value.items.map(row=>({...row,...(row.title_basis==='owner-identity'&&labels.get(row.id)?{title:labels.get(row.id),title_basis:'existing-owner-catalogue-display-join'}:{})}));this.sessionRows=handle?[...previous,...rows.filter(row=>!previous.some(held=>held.id===row.id))]:rows;this.libraryCatalogue=true;this.libraryCut=value.as_of;this.libraryNext=value.pagination.next_read;this.libraryCoverage=value.coverage;this.sessionCount=value.pagination.total;this.libraryError='';this.find('[data-more]').hidden=!this.libraryNext;this.paintSessions();void this.joinWorkTitles(this.sessionRows);}catch(error){if(ticket===this.listLoad){this.libraryError=error.message;this.status('Conversation summaries unavailable: '+error.message,true);this.paintConversations();}throw error;}
  }
  async noteOnResponse(){const saved=this.selectedTurnRecord,reply=saved?.reply?.id,epoch=this.viewEpoch,session=this.session;if(!saved?.id||!reply)throw Error('A saved response is required before recording response feedback.');const query=analyticsQuery(this.project,'sessions',{turn_id:saved.id}),value=analyticsEnvelope(await projectRequest(query),{project:this.project,projection:'sessions',scope:'turn',expectedQuery:query});if(epoch!==this.viewEpoch||session!==this.session||this.selectedTurnRecord?.id!==saved.id)return;const target=value.items.find(row=>row.session_id===session)?.latest_reply_target;if(target?.turn_id!==saved.id||target.reply_record_id!==reply)throw Error('This saved reply has no matching qualified feedback target. Inspect its exact turn before continuing.');return openResponseFeedback(target,{request:projectRequest,onTurn:target=>this.onReadTurn?.(target.id),onSaved:()=>{if(epoch===this.viewEpoch&&session===this.session)this.status('Response note saved.');}});}
  conversationDraft(id){const held=this.unsavedDrafts?.get(id||'new');if(held!=null)return !!held.trim();try{const local=this.composerStorage?.getItem(this.composerBackupKey(id));return !!(local!==null&&local!==undefined?local:localStorage.getItem(this.composerBackupKey(id))||'').trim();}catch{return false;}}
  paintConversations(){
    const list=this.find('[data-conversation-list]');if(!list)return;list.replaceChildren();const needle=(this.find('[data-conversation-search]')?.value||'').toLowerCase(),filter=this.find('[data-conversation-filter]')?.value||'all';
    const rows=this.libraryCatalogue?[...(this.sessionRows||[])]:[...(this.sessionRows||[])].reverse();let shown=0;
    for(const row of rows){const running=this.ownerRunning?.get(row.id)||null,draft=this.conversationDraft(row.id);if(needle&&![row.title,row.work_title,row.id,row.work_id,row.dispatch_id,row.packet].some(value=>String(value||'').toLowerCase().includes(needle)))continue;if(filter==='running'&&!running||filter==='draft'&&!draft)continue;
      const card=make('button','','conversation-library-row');card.type='button';card.disabled=!!this.submitting||!!this.initializing;card.setAttribute('aria-current',row.id===this.session?'true':'false');card.append(make('strong',conversationRowLead(row)));const metadata=conversationMetadata(row,{running,draft,loading:row.id===this.session&&this.loadingSession});for(const line of metadata)card.append(make('span',line));card.onclick=()=>this.guard(async()=>{const opened=await this.openConversation(row.id);if(opened&&this.session===row.id)this.setLibrary(false);this.paintConversations();});list.append(card);shown++;
    }
    if(!shown)list.append(make('p',needle||filter!=='all'?'No matching conversation in this loaded page.':'No saved conversations yet.'));
    const status=this.find('[data-library-status]');if(status)status.textContent=(this.libraryError?'Summary unavailable · ':'')+shown+' shown'+(this.sessionCount!=null?' / '+this.sessionCount+' saved':'')+(shown!==(this.sessionRows?.length||0)?' · loaded matches':'');
  }
  paintSessions(){
    const menu=this.find('[data-sessions]');menu.value=this.session;
    const title=this.find('[data-conversation-title]');if(title){title.textContent=this.sessionRows?.find(row=>row.id===this.session)?.title||this.selectedConversationTitle||this.session||'New conversation';title.title=title.textContent;}this.paintConversations();
  }
  markRunning(session,turn){if(!session)return;this.runningSessions??=new Map();if(turn)this.runningSessions.set(session,turn);else this.runningSessions.delete(session);this.paintSessions();void this.observeRunning();}
  async loadSessions({refreshRunning=false}={}){
    if(this.libraryCatalogue){await this.loadLibraryCatalogue();if(refreshRunning){await this.refreshKnownRunning();this.paintSessions();}return;}
    const load=this.listLoad=(this.listLoad||0)+1,state=await projectRequest('/authoring/state?project='+encodeURIComponent(this.project)+'&session_limit='+this.limit+'&view=sessions');if(load!==this.listLoad)return;
    this.sessionRows=state.sessions;this.sessionCount=state.session_count;this.find('[data-more]').hidden=state.sessions.length>=state.session_count;
    if(refreshRunning)await this.refreshKnownRunning();
    if(load===this.listLoad)this.paintSessions();
  }
  async refreshKnownRunning(){return this.observeRunning();}
  // WHAT IS RUNNING (ruling D4 on the sessions trace): health active_work nominates this project's sessions (its rows carry
  // no state), together with the sessions this page has seen active; GET /authoring/session confirms each. A session is
  // running only while that read returns active, not ORPHANED or UNKNOWN-OWNERSHIP, with its observed_at. A failed read
  // keeps the previous observation with its own time. Re-read on the page's existing occasions and on window focus.
  observeRunning(){
    if(this.runningRead){this.runningAgain=true;return this.runningRead;}
    const read=this.runningRead=(async()=>{try{
      let health={};try{health=await projectRequest('/authoring/health');}catch{}
      const ids=new Set([...(Array.isArray(health?.active_work)?health.active_work:[]).filter(row=>row?.project===this.project&&row.session_id).map(row=>row.session_id),...(this.runningSessions||new Map()).keys(),...(this.ownerRunning||new Map()).keys()]);
      const next=new Map();
      await Promise.all([...ids].map(async id=>{const nominated=this.runningSessions?.get(id);try{const owner=await projectRequest('/authoring/session?id='+encodeURIComponent(id)+'&view=summary&limit=1'),observed=ownerRunningObservation(owner);
        if(observed){if(observed.workId)observed.workTitle=await this.workTitle(observed.workId);next.set(id,observed);}else if(this.runningSessions?.get(id)===nominated)this.runningSessions.delete(id);this.settleContinuingStatus(id,!!observed);}
        catch{const held=this.ownerRunning?.get(id);if(held)next.set(id,held);}}));
      const ended=[...(this.ownerRunning||new Map()).keys()].some(id=>!next.has(id));this.ownerRunning=next;this.syncRunningTimer();this.paintConversations();this.onRunningObserved?.(this.runningObservations());
      // a conversation the owner no longer reports running: its saved half (reply, last event) is re-read with it
      if(ended&&this.libraryCatalogue)await this.loadLibraryCatalogue().catch(()=>{});
    }finally{this.runningRead=null;}})();
    return read.then(()=>{if(this.runningAgain){this.runningAgain=false;return this.observeRunning();}});
  }
  // The one timer that keeps the running display current: while an owner observation shows a conversation running and the
  // page is visible, the same observeRunning runs every RUNNING_REFRESH_MS. It is armed and cleared only here, after each
  // observation, on the page being hidden, and in destroy(); nothing is polled while nothing is shown running.
  syncRunningTimer(){
    const want=!this.runningDisposed&&this.ownerRunning?.size>0&&!globalThis.document?.hidden;
    if(!want){if(this.runningTimer){globalThis.clearInterval(this.runningTimer);this.runningTimer=null;}return;}
    if(!this.runningTimer)this.runningTimer=globalThis.setInterval(()=>{void this.observeRunning();},RUNNING_REFRESH_MS);
  }
  // hidden: the timer is cleared; shown again: one read, which re-arms the timer if a conversation is still shown running
  runningVisibilityChanged(){if(globalThis.document?.hidden)this.syncRunningTimer();else if(this.ownerRunning?.size)void this.observeRunning();}
  // teardown of the session view: the place that removes onRunningFocus also removes the visibility listener and the timer
  stopRunningObservation(){window.removeEventListener('focus',this.onRunningFocus);document.removeEventListener('visibilitychange',this.onRunningVisibility);this.runningDisposed=true;this.syncRunningTimer();}
  runningObservations(){return [...(this.ownerRunning||new Map())].map(([session,observed])=>({session,...observed}));}
  // the Work owner's own title (else goal) for a bound work_id, from its detail read; null when the owner does not return it
  async workTitle(id){try{const value=await projectRequest('/work/state?'+new URLSearchParams({project:this.project,view:'detail',id}));const task=value?.task;return task?.id===id?(task.title||task.goal||null):null;}catch{return null;}}
  // the bound Work's title joins the rows of this one catalogue load (a reload replaces the rows and joins again)
  async joinWorkTitles(rows){const ids=[...new Set(rows.filter(row=>row.work_id&&!row.dispatch_id).map(row=>row.work_id))];if(!ids.length)return;const titles=new Map(await Promise.all(ids.map(async id=>[id,await this.workTitle(id)])));let joined=false;for(const row of rows){const title=titles.get(row.work_id);if(title&&!row.dispatch_id){row.work_title=title;row.work_title_basis='work-owner-detail-display-join';joined=true;}}if(joined&&rows.every(row=>this.sessionRows?.includes(row)))this.paintConversations();}
  // the once-only "continues running" lines (newConversation, openConversationAttempt) leave once an owner read shows that turn is no longer active
  settleContinuingStatus(id,running){const held=this.continuingStatus;if(running||!held||held.session!==id)return;this.continuingStatus=null;const node=this.find('[data-status]');if(node&&node.textContent===held.text)this.status(held.replacement);}
  async refreshConversationChoices(){
    if(this.sessionsRequest)return this.sessionsRequest;if(this.sessionsReadAt&&Date.now()-this.sessionsReadAt<1000)return;this.sessionsReadAt=Date.now();
    const request=this.loadSessions({refreshRunning:true});this.sessionsRequest=request;try{await request;}finally{if(this.sessionsRequest===request)this.sessionsRequest=null;}
  }
  detachConversation(){
    this.preferenceOpening=Symbol('conversation changed');
    const running=!!this.active;if(this.active)this.markRunning(this.session,this.active);
    clearTimeout(this.snapshotTimer);this.snapshotTimer=null;this.activeCapabilities=null;this.stopRequested=false;this.turnTarget=null;
    this.suspendMessageReading();this.stream?.close();this.stream=null;this.streamGeneration=(this.streamGeneration||0)+1;this.viewEpoch=(this.viewEpoch||0)+1;this.sessionLoad++;this.settingsRevision++;
    this.sessionSettingsRead=null;this.active='';this.activeScope='';this.observationText('');this.origin=null;this.selectedTurnRecord=null;this.selectedSessionRecord=null;this.admittedSettings=null;this.controlPending=null;this.loadingSession=false;this.settingsFailed=false;
    this.execution=null;this.controlReceiptSignature=null;
    this.find('[data-control-receipts]')?.replaceChildren();
    const cue=this.find('[data-input-attention]');if(cue){cue.hidden=true;cue.textContent='Input needs attention — inspect';}
    this.paintParentContinuation(null);
    // Keep global preference writes ordered across views. An old session's
    // failure must neither poison the next send nor overtake newer settings.
    this.settingsSave=(this.settingsSave||Promise.resolve()).catch(()=>{});return running;
  }
  newConversation(){
    if(this.submitting||this.initializing){this.find('[data-sessions]').value=this.session;return false;}
    if(this.startupFailed&&!this.startupResourcesReady){this.status('Conversation startup is unavailable. Refresh before starting a new conversation.',true);return false;}this.startupFailed=false;this.initialSession='';const previous=this.session,running=this.detachConversation();this.switchDraftTarget('');this.session='';this.role=this.find('[data-mode]').value==='review'?'review':'author';this.rememberMode();this.rememberConversationSelection('');this.selectedConversationTitle='';this.paintSessions();
    this.applySettings(this.savedSettings()||this.preferences);this.resetUsage();this.empty();this.setBusy(false);this.scope();this.paintSessions();this.preferenceUI?.repaint();this.status(running?'New conversation. The previous conversation continues running.':'New conversation; project framing and feedback remain available.');this.continuingStatus=running?{session:previous,text:'New conversation. The previous conversation continues running.',replacement:'New conversation; project framing and feedback remain available.'}:null;if(running)void this.observeRunning();return true;
  }
  async openConversation(id){
    // A turn named for an open belongs to that one attempt (the shell does not forward a refused open's false): a refused, failed
    // or unrelated open drops exactly the target it carried; a target named later is left for its own attempt.
    const named=this.pendingTurnTarget,release=()=>{if(named&&this.pendingTurnTarget===named)this.pendingTurnTarget=null;};
    if(named&&named.sessionId!==id)release();
    let opened=false;
    try{opened=await (this.openConversationAttempt||WorkspaceSession.prototype.openConversationAttempt).call(this,id);return opened;}
    finally{if(opened===false)release();}
  }
  async openConversationAttempt(id){
    if(this.submitting||this.initializing){this.find('[data-sessions]').value=this.session;return false;}if(!id)return this.newConversation();
    const previous=this.session,running=this.detachConversation(),epoch=this.viewEpoch;this.switchDraftTarget(id);this.session=id;this.controlPending=this.pendingInputFor(id);this.rememberConversationSelection(id);this.find('[data-sessions]').value=id;this.paintSessions();
    await this.loadSession();if(epoch!==this.viewEpoch)return false;if(this.preferenceUI&&!this.find('[data-inspector]').hidden&&this.find('.session-settings').open)await this.preferenceUI.open();if(epoch!==this.viewEpoch)return false;this.startupFailed=false;this.initialSession='';this.setBusy(!!this.active);if(running&&!this.active){this.status('Conversation opened. The previous conversation continues running.');this.continuingStatus={session:previous,text:'Conversation opened. The previous conversation continues running.',replacement:''};void this.observeRunning();}return true;
  }
  message(role,text,{formatted=false,excerpt=false,resultLinks=[]}={}){this.find('.session-empty')?.remove();const row=make('article','','session-message '+role),body=make('div','','session-body');if(role==='assistant'&&!excerpt){for(const part of messageLinkParts(text,{project:this.project,resultLinks})){if(part.text!=null)body.append(document.createTextNode(part.text));else{const link=make('a',part.label);if(part.ownerRead){link.href=part.href;link.onclick=event=>{if(this.onOpenOwner){event.preventDefault();this.guard(()=>this.onOpenOwner(part.ownerRead,part.label));}};}else if(part.kind==='human-artifact'){link.href=part.href;link.onclick=event=>{event.preventDefault();this.guard(()=>this.onOpenArtifact(part.humanRead.path,part.label,part.humanRead));};}else if(part.kind==='artifact'){link.href='/research/artifact?'+new URLSearchParams({project:this.project,path:part.target,scope:'project'});link.onclick=event=>{event.preventDefault();this.guard(()=>this.onOpenArtifact(part.target,part.label));};}else{link.href=part.target;link.target='_blank';link.rel='noopener noreferrer';}body.append(link);}}}else body.textContent=text;row.append(make('strong',role==='user'?'You':'Eigen'),body);(this.turnContainer||this.find('[data-thread]')).append(row);
    if(role==='assistant'&&formatted&&this.renderFinalMessage){
      body.classList.add('is-rendered');
      const fallback=error=>{body.textContent=text;body.classList.remove('is-rendered');const note=make('p','Formatted view unavailable; original reply shown.','session-help');note.title=error?.message||String(error);row.append(note);};
      try{row.rendered=Promise.resolve(this.renderFinalMessage(body,text,{resultLinks})).catch(fallback);}catch(error){fallback(error);}
    }
    return row;}
  // These DOM rows belong to one acknowledged turn, not to the latest reply.
  // Keep partial bodies in place until that exact owner's saved row can adopt them.
  transientMessages(id,part){
    return [...this.find('[data-thread]').querySelectorAll('[data-transient-turn]')].filter(row=>
      row.dataset.transientProject===this.project&&row.dataset.transientSession===this.session&&
      row.dataset.transientTurn===id&&row.dataset.transientPart===part);
  }
  markTransient(row,id,part){
    Object.assign(row.dataset,{transientProject:this.project,transientSession:this.session,transientTurn:id,transientPart:part});
    return row;
  }
  authorMessage(text,selection){
    const row=this.message('user',text),draft=selection?.draft;
    if(row&&draft){const detail=make('details','','session-draft-attachment');detail.append(make('summary','Unsaved manuscript draft sent'),make('p',draft.reason||'These words have not been written to the manuscript.'));
      if(typeof draft.text==='string')detail.append(make('pre',draft.text));else if(draft.text_omitted)detail.append(make('p','Draft of '+Number(draft.text_chars||0).toLocaleString()+' characters; the saved turn holds the exact words.','session-help'));
      // A thread row carries a bounded draft; the saved turn holds the exact words.
      if(draft.text_truncated)detail.append(make('p','Draft shortened to '+String(draft.text||'').length.toLocaleString()+' of '+Number(draft.text_chars||0).toLocaleString()+' characters; the saved turn holds the exact draft.','session-help'));
      row.append(detail);}
    if(row&&selection?.quote_truncated)row.append(make('p','Quoted passage shortened to '+String(selection.quote||'').length.toLocaleString()+' of '+Number(selection.quote_chars||0).toLocaleString()+' characters.','session-help'));
    return row;
  }
  appendTurn(turn,active=false){
    for(const application of turn.undo_entries||[])this.guard(()=>this.onApplication({...application,project:this.project}));
    if(turn.application?.edits?.length)this.guard(()=>this.onApplication(turn.application));
    for(const action of turn.actions||turn.reply?.actions||[])if(action.outcome?.undo_ref)this.guard(()=>this.onApplication({id:action.id,undo_ref:action.outcome.undo_ref}));
    const requestRow=this.authorMessage(turn.text,turn.unsaved_draft?{...turn.selection,draft:turn.unsaved_draft}:turn.selection);requestRow.dataset.messagePart='request';spokenAt(requestRow,turn.ts);
    for(const steer of turn.steering||[])this.authorMessage(steer.text,steer.unsaved_draft?{...steer.selection,draft:steer.unsaved_draft}:steer.selection);
    const reply=turn.reply||{},proposal=turn.proposal||reply.proposal,actions=turn.action_count??turn.actions?.length??0,failures=turn.failure_count??turnFailures(turn).length;
    if(!turn.reply&&!proposal&&!turn.proposal_edit_count){const row=this.message('assistant','');row.dataset.messagePart='reply';if(actions||failures){this.actions(row,turn.actions||[],turn);this.failures(row,turn);}return;}
    const text=typeof reply.display_text==='string'?reply.display_text:reply.proposal?.answer||reply.text||proposal?.answer||turn.proposal_answer||(typeof reply.error==='string'?reply.error:reply.error?.message)||'';
    const row=this.message('assistant',text,{excerpt:true});row.dataset.messagePart='reply';row.dataset.turnId=turn.id;spokenAt(row,reply.ts);
    // the row's facets as chips (G15): saved changes, failed attempts, reply standing; the counts
    // come from the owner's row projection, never from re-reading the turn
    const facets=[actions?{label:actions+' saved change'+(actions===1?'':'s'),tone:'ok'}:null,failures?{label:failures+' failed attempt'+(failures===1?'':'s'),tone:'attention',title:'Recorded failed operations; the saved turn lists each attempt.'}:null,
      reply.status==='interrupted'?{label:'Stopped',tone:'historical'}:null,turn.proposal_state==='saved-without-final-reply'?{label:'Saved proposal · no final reply',tone:'attention'}:null].filter(Boolean);
    this.facets(row,facets);
    if(turn.steering_truncated)row.append(make('p','Showing '+(turn.steering||[]).length+' of '+Number(turn.steering_total||0)+' steering messages; the saved turn holds them all.','session-help'));
    if(turn.proposal_state==='saved-without-final-reply')row.prepend(make('p','Recovered saved proposal · the writer did not finish a final reply. Inspect the changes before applying.','session-help'));
    // G15 (M5 C8): a turn's saved artifacts are relation rows (kind, exact read, receipt note);
    // the complete list and the bodies stay on the saved turn read.
    // G15 (repair H1): a thread row carries the artifact COUNT; the links themselves (up to 20,
    // with receipts and aliases) are on the single-turn summary read and load on request
    const linkRows=links=>{const rows=[];for(const read of links||[]){const target=artifactHumanTarget(read.url,{project:this.project});if(!target)continue;rows.push({kind:'Artifact',label:read.path,run:()=>this.onOpenArtifact(target.path,read.path,target),title:'Receipt '+(read.artifact_id||'unrecorded')+' · SHA256 '+read.expected_sha256,note:read.artifact_id?'receipt '+String(read.artifact_id).replace(/^ART-/,'').slice(0,12):'',onError:error=>this.status(error.message,true)});}return rows;};
    const artifactCount=turn.result_links_total??turn.result_links?.length??0;
    if(artifactCount){
      // R3: a capped discovery is a lower bound ("at least"); R4: the lazy read is loaded only after
      // an exact successful validated read, a failure shows its cause with Retry, a closed
      // disclosure issues no read, and a stale callback (replaced row, later open) paints nothing
      const lowerBound=turn.result_links_total_basis==='at-least'||turn.result_links_more===true;
      const results=make('details','','session-result-links');results.setAttribute('data-control','conversation:artifact');
      const headline=(count,lower,{listed=null,entry=null}={})=>(lower?'At least ':'')+count+' saved artifact'+(count===1?'':'s')+' from this turn'+(listed!==null&&listed<count?' · '+listed+' listed':'')+(entry!==null&&entry!==count?' · the entry row counted '+entry:'');
      const summary=make('summary',headline(artifactCount,lowerBound));results.append(summary);
      const body=make('div');results.append(body);let loaded=false,loading=false,ticket=0;const project=this.project,turnId=turn.detail?.turn_id||turn.id;
      // the current exact response carries the authoritative coverage of what it lists (R3): the
      // header and the coverage sentence follow it; the entry row's count is shown as such when it differs
      const paint=(links,{more=false,basis=null,total=null}={})=>{const lower=more||basis==='at-least';const count=lower?Math.max(total||0,links.length):(total??links.length);
        body.replaceChildren(relationList(linkRows(links),{emptyText:'No readable artifact in this row.'}));
        summary.textContent=headline(count,lower,{listed:links.length,entry:artifactCount});
        if(lower||links.length<count){const note=make('p','Showing '+links.length+' of '+(lower?'at least ':'')+count+' saved artifacts; the saved turn\'s actions list the rest.','session-help');
          if(this.onReadTurn){const read=make('button','Read the saved turn');read.type='button';read.onclick=()=>this.guard(()=>this.onReadTurn(turnId));note.append(' ',read);}body.append(note);}};
      const load=()=>{if(loaded||loading)return;loading=true;const mine=++ticket;body.replaceChildren(pendingRead(make('p','Reading the saved artifacts…','session-help')));
        this.guard(async()=>{try{const value=await projectRequest('/authoring/session-turn?'+new URLSearchParams({project,id:turnId,view:'summary'}));
            if(mine!==ticket||results.isConnected===false)return;
            if(value.project!==project||value.turn?.id!==turnId)throw Error('The saved turn belongs to a different project or turn.');
            paint(value.turn.result_links||[],{more:value.turn.result_links_more===true,basis:value.turn.result_links_total_basis||null,total:Number.isInteger(value.turn.result_links_total)?value.turn.result_links_total:null});loaded=true;}
          catch(error){if(mine!==ticket||results.isConnected===false)return;const retry=make('button','Retry');retry.type='button';retry.onclick=()=>load();body.replaceChildren(make('p','Saved artifacts unavailable: '+error.message,'session-help error'),retry);throw error;}
          finally{if(mine===ticket)loading=false;}});};
      if(turn.result_links?.length){paint(turn.result_links,{more:turn.result_links_more===true,basis:turn.result_links_total_basis||null,total:Number.isInteger(turn.result_links_total)?turn.result_links_total:null});loaded=true;}
      results.ontoggle=()=>{if(!results.open)return;load();};
      row.append(results);}
    this.actions(row,turn.actions||reply.actions||[],turn);this.failures(row,turn);this.proposal(row,turn);
    if(turn.detail?.turn_id){const complete=make('details','','session-complete-turn');complete.append(make('summary','Audit saved turn'));if(this.onReadTurn){const read=make('button','Read saved turn');read.type='button';read.onclick=()=>this.guard(()=>this.onReadTurn(turn.detail.turn_id));complete.append(read);}lazyContent(complete,()=>{const download=make('a','Download the exact saved turn');download.href='/authoring/session-turn?'+new URLSearchParams({project:this.project,id:turn.detail.turn_id,view:'turn'});download.download='saved-turn.json';complete.append(make('p','The public response is shown above. The exact saved record also includes every retained action, error and source-edit receipt.','session-help'),download);});row.append(complete);}
    if(reply.status==='interrupted')row.append(make('p',this.parentContinuationValue?.turn_id===turn.id?'Parent observation stopped · partial reply retained. Dispatched work has separate standing.':'Stopped · partial reply retained.','session-help'));
  }
  suspendMessageReading(){
    if(this.threadMessageSession===this.session){this.messageScroll??=new Map();this.messageScroll.set(this.session,{thread:this.find('[data-thread]')?.scrollTop||0,surface:this.find('.session-conversation-surface')?.scrollTop||0});}
    this.messageObserver?.disconnect();this.messageObserver=null;this.messageResize?.disconnect();this.messageResize=null;
    for(const group of this.messageGroups?.values()||[])for(const reader of group.readers||[])reader.deactivate();
  }
  preserveReadingViewport(change){
    const thread=this.find('[data-thread]'),surface=this.find('.session-conversation-surface'),scroll=thread.scrollHeight>thread.clientHeight+4?thread:surface;
    if(!scroll)return change();const rect=scroll.getBoundingClientRect(),atEnd=scroll.scrollHeight-scroll.scrollTop-scroll.clientHeight<60;
    const anchor=[...thread.querySelectorAll('.session-message')].find(n=>n.getBoundingClientRect().bottom>rect.top),top=anchor?.getBoundingClientRect().top;
    change();if(anchor?.isConnected){if(atEnd)scroll.scrollTop=scroll.scrollHeight;else scroll.scrollTop+=anchor.getBoundingClientRect().top-top;}
  }
  renderMessageTurns(turns,{before=false,activeId}={}){
    const thread=this.find('[data-thread]'),session=this.session,epoch=this.viewEpoch,project=this.project;
    this.messageGroups??=new Map();this.messageOrders??=new Map();const order=this.messageOrders.get(session)||[],newIds=[],switching=this.threadMessageSession!==session;
    const current=()=>this.session===session&&this.viewEpoch===epoch;
    const metadata=(old,row,renew=false)=>{const held=[...old.children].filter(n=>!n.matches('strong,.session-body,.session-message-reading')),fresh=[...row.children].filter(n=>!n.matches('strong,.session-body'));
      if(!renew&&held.map(n=>n.outerHTML).join('')===fresh.map(n=>n.outerHTML).join(''))return;
      const open=new Map([...old.querySelectorAll('details')].map(n=>[n.querySelector('summary')?.textContent,n.open]));for(const n of held)n.remove();for(const n of fresh)old.append(n);for(const n of old.querySelectorAll('details'))if(open.has(n.querySelector('summary')?.textContent))n.open=open.get(n.querySelector('summary')?.textContent);
    };
    this.preserveReadingViewport(()=>{
      if(this.threadMessageSession!==session){thread.replaceChildren();this.threadMessageSession=session;}
      for(const turn of turns){const key=JSON.stringify([project,session,turn.id]);let entry=this.messageGroups.get(key);const signature=JSON.stringify([epoch,turn]);
        if(!entry){entry={node:make('section','','session-saved-messages'),signature:null,readers:[]};entry.node.dataset.turnKey=turn.id;this.messageGroups.set(key,entry);if(!order.includes(turn.id))newIds.push(turn.id);}
        if(entry.signature!==signature){const scratch=make('section');this.turnContainer=scratch;try{this.appendTurn(turn,turn.id===activeId);}finally{this.turnContainer=null;}
          const loose=[...entry.node.children].filter(n=>!n.dataset.messagePart),desired=[];
          for(const node of [...scratch.children]){const part=node.dataset.messagePart,transient=part?this.transientMessages(turn.id,part):[],old=part?(entry.node.querySelector('[data-message-part="'+part+'"]')||transient[0]):loose.find(n=>n.outerHTML===node.outerHTML&&!desired.includes(n));
            if(old&&part){metadata(old,node,entry.epoch!==epoch);old.dataset.messagePart=part;if(node.dataset.turnId)old.dataset.turnId=node.dataset.turnId;}
            const adopted=old||node;desired.push(adopted);
            // Retire only exact same-turn/part duplicates; never sweep the transcript.
            // Stream text is retained in messageStreams and adopted by the reader below.
            for(const row of transient)if(row!==adopted)row.remove();
            for(const key of ['transientProject','transientSession','transientTurn','transientPart'])delete adopted.dataset[key];
          }
          let previous=null;for(const node of desired){if(node.parentNode!==entry.node||node.previousSibling!==previous)entry.node.insertBefore(node,previous?previous.nextSibling:entry.node.firstChild);previous=node;}for(const node of [...entry.node.children])if(!desired.includes(node))node.remove();
          entry.signature=signature;entry.epoch=epoch;
        }
        for(const row of entry.node.querySelectorAll('[data-message-part]')){
          if(!row.messageReading){const target={project,session_id:session,turn_id:turn.id,part:row.dataset.messagePart};row.messageReading=mountMessageReading(row,{target,request:projectRequest,renderMarkdown:this.renderFinalMessage,isCurrent:current,storage:globalThis.sessionStorage,changed:change=>this.preserveReadingViewport(change)});entry.readers.push(row.messageReading);}
          row.messageReading.activate(current);if(row.dataset.messagePart==='reply'&&this.messageStreams?.has(turn.id))row.messageReading.stream(this.messageStreams.get(turn.id));
        }
      }
      const ids=before?[...newIds,...order]:[...order,...newIds];this.messageOrders.set(session,ids);
      let previous=thread.querySelector('[data-older]');for(const id of ids){const node=this.messageGroups.get(JSON.stringify([project,session,id]))?.node;if(!node)continue;if(node.parentNode!==thread||node.previousSibling!==previous)thread.insertBefore(node,previous?previous.nextSibling:thread.firstChild);previous=node;}
    });
    if(switching){const held=this.messageScroll?.get(session),surface=this.find('.session-conversation-surface');const restore=()=>{if(!current()||!thread.clientHeight)return;thread.scrollTop=held?held.thread:thread.scrollHeight;if(surface&&held)surface.scrollTop=held.surface;this.messageResize?.disconnect();this.messageResize=null;};if(typeof ResizeObserver==='function'){this.messageResize?.disconnect();this.messageResize=new ResizeObserver(restore);this.messageResize.observe(thread);}restore();}
    this.messageObserver?.disconnect();
    const show=reader=>{if(!current())return;if(reader.state.content===null&&!reader.state.absent)void reader.open();else void reader.refresh();};
    if(typeof IntersectionObserver==='function'){
      this.messageObserver=new IntersectionObserver(entries=>{for(const item of entries)if(item.isIntersecting){this.messageObserver.unobserve(item.target);show(item.target.messageReading);}},{root:null,rootMargin:'40px'});
      for(const row of thread.querySelectorAll('[data-message-part]'))this.messageObserver.observe(row);
    }else for(const row of thread.querySelectorAll('[data-message-part]'))show(row.messageReading);
  }
  async loadQueue(){
    const generation=this.queueLoad=(this.queueLoad||0)+1,project=this.project,rows=[],pages=new Set();
    let path='/work/state?'+new URLSearchParams({project,view:'queue'});
    while(path){if(pages.has(path))throw Error('The queue owner repeated its continuation. No incomplete queue was accepted.');pages.add(path);const state=await projectRequest(path);if(generation!==this.queueLoad||project!==this.project)return;rows.push(...(state.tasks||[]));const next=state.pagination?.next_read;if(next){const h=next.http,url=new URL(h?.url||'',globalThis.location?.href||'http://localhost/');if(h?.method!=='GET'||url.origin!==new URL(globalThis.location?.href||'http://localhost/').origin||url.pathname!=='/work/state'||url.searchParams.get('project')!==project||url.searchParams.get('view')!=='queue')throw Error('The queue owner did not supply a valid continuation. No incomplete queue was accepted.');path=url.pathname+url.search;}else{if(state.pagination?.next_offset!=null)throw Error('The queue is incomplete and has no owner continuation.');path=null;}}
    this.queued=rows.filter(task=>task.task_kind==='session-request'&&!['done','verified','cancelled'].includes(task.status));
    const box=this.find('[data-queue]'),items=this.find('[data-queue-items]');box.hidden=!this.queued.length;items.replaceChildren();
    this.queueExcluded??=new Set();const ready=this.queued.filter(task=>['open','ready'].includes(task.status));
    const included=ready.filter(task=>!this.queueExcluded.has(task.id));this.find('[data-queue-summary]').textContent=included.length+' of '+ready.length+' queued requests included in your next message'+(this.queued.length>ready.length?' · '+(this.queued.length-ready.length)+' underway':'');
    for(const task of this.queued){const row=make('article','','session-queued-request');const jump=make('button',task.title);jump.type='button';jump.onclick=()=>this.onInspectPassage(task.anchor);row.append(jump);if(task.anchor?.quote)row.append(make('blockquote',task.anchor.quote));if(task.goal!==task.title)row.append(make('p',task.goal));
      if(['open','ready'].includes(task.status)){const includeLabel=make('label','Include in next message'),include=make('input');include.type='checkbox';include.checked=!this.queueExcluded.has(task.id);include.onchange=()=>{if(include.checked)this.queueExcluded.delete(task.id);else this.queueExcluded.add(task.id);const count=this.queued.filter(row=>['open','ready'].includes(row.status)&&!this.queueExcluded.has(row.id)).length;this.find('[data-queue-summary]').textContent=count+' of '+ready.length+' queued requests included in your next message';};includeLabel.append(include);row.append(includeLabel);const remove=make('button','Cancel canonical request');remove.type='button';remove.onclick=()=>this.guard(async()=>{const action=task.allowed_actions?.task_status;if(!action?.permitted||!action.statuses?.includes('cancelled')||action.http?.method!=='POST'||action.http?.url!=='/work/transition')throw Error('Reinspect this queued request before cancelling it; the owner supplied no cancellation authority.');await projectRequest(action.http.url,{project:this.project,...action.payload,status:'cancelled'});await this.loadQueue();});row.append(remove);}else row.append(make('small',task.status==='in-progress'?'In progress':task.status));items.append(row);}
  }
  async reviewSavedProposal(turnId,{proposalVersion,readHandle,readOnly=false}={}){
    if(!proposalVersion||!readHandle)return this.onOpenReview({turnId});
    return this.onReviewProposal(turnId,{proposalVersion,readHandle,readOnly});
  }
  async loadSession(before){
    if(!before){clearTimeout(this.snapshotTimer);this.snapshotTimer=null;this.activeCapabilities=null;this.stream?.close();this.stream=null;this.streamGeneration=(this.streamGeneration||0)+1;this.active='';this.activeScope='';this.loadingSession=true;this.setBusy(true);this.paintSelection();this.resetUsage();this.status('Opening conversation…');pendingRead(this.find('[data-status]'));}
    const session=this.session,epoch=this.viewEpoch,modeRevision=this.modeRevision,settingsRevision=this.settingsRevision,load=++this.sessionLoad,pendingAtRead=this.controlPending;let controlMessage=null;
    try{const data=await projectRequest('/authoring/session?id='+encodeURIComponent(session)+'&view=summary&limit=20'+(before?'&before='+encodeURIComponent(before):''));
    if(session!==this.session||epoch!==this.viewEpoch||load!==this.sessionLoad)return;
    if(data.session?.project&&data.session.project!==this.project)throw Error('This conversation belongs to a different project. Open it from that project.');
    if(!before){
      this.origin=sessionOrigin(data);const associated=this.origin.workId;if(associated&&this.onWorkAssociation)await this.onWorkAssociation(associated,()=>session===this.session&&epoch===this.viewEpoch&&load===this.sessionLoad);if(session!==this.session||epoch!==this.viewEpoch||load!==this.sessionLoad)return;
      this.sessionSettingsRead=data.settings_read;this.selectedSessionRecord=data.session;this.selectedTurnRecord=(data.turns||[]).at(-1)||null;
      this.selectedConversationTitle=data.session.title||(data.turns||[]).at(-1)?.text||this.session;
      const latest=[...data.turns].reverse().find(t=>t.reply?.usage||t.reply?.usage_facts_projection)?.reply;
      this.role=data.session.role||'author';
      if(settingsRevision===this.settingsRevision)this.applySettings(data.active?data.session:this.savedSettings()||data.session);
      if(this.role==='review')this.find('[data-mode]').value='review';
      else if(modeRevision===this.modeRevision)this.find('[data-mode]').value='work';
      const reported=data.active||latest||data.session;
      const matches=meterMatchesSelection(reported,this.find('[data-provider]').value,this.find('[data-model]').value,reported===latest&&!data.active);
      if(matches)this.showUsage(data.active?.usage||latest?.usage,reported);else this.resetUsage();
      this.admittedSettings=data.active?.provider_settings||(data.turns||[]).find(turn=>turn.id===data.active?.id)?.provider_settings||null;this.settingsTruth(data.session);
      this.modeHelp();
      this.find('[data-sessions]').value=this.session;
    }
    if(!before){if(!data.active)this.observationText(savedExecutionObservation(data));this.markRunning(session,data.active?.id);this.execution=data.execution;const caller=data.active?.id||this.selectedTurnRecord?.id;this.paintParentContinuation(data.active?.parent_continuation??(data.execution?.turn_id===caller?data.execution?.parent_continuation:undefined)??(!data.active?this.selectedTurnRecord?.parent_continuation:undefined),{turnId:caller,active:!!data.active});this.restorePublicationSlot(data.execution,data.active);this.paintControlReceipts(data.execution);}
    if(!before&&this.controlPending){this.settleAdmittedDraft(this.controlPending);const receipt=(data.execution?.controls||[]).find(row=>row.control_id===this.controlPending.id&&row.turn_id===this.controlPending.turn);if(receipt)this.settleControlReceipt(receipt);if(this.controlPending&&!data.active){try{await this.readPendingControl();}catch(error){if(session===this.session&&epoch===this.viewEpoch&&load===this.sessionLoad)this.status('Input receipt observation is unavailable; your text is retained and nothing is replayed.',true);}if(session===this.session&&epoch===this.viewEpoch&&load===this.sessionLoad)this.finishPendingObservation(data.execution);}if(session!==this.session||epoch!==this.viewEpoch||load!==this.sessionLoad)return;if(pendingAtRead||this.controlPending)controlMessage={text:this.find('[data-status]').textContent,error:this.find('[data-status]').classList.contains('error')};}
    const thread=this.find('[data-thread]');this.renderMessageTurns(data.turns,{before,activeId:data.active?.id});if(!before)this.adoptTurnTarget(data);
    if(data.older_cursor){let older=thread.querySelector('[data-older]');if(!older){older=make('button','Earlier messages');older.dataset.older='';thread.prepend(older);}older.onclick=()=>this.guard(()=>this.loadSession(data.older_cursor));}else{const older=thread.querySelector('[data-older]');if(older){older.textContent='Start of saved conversation';older.setAttribute('aria-disabled','true');older.onclick=null;}}if(!data.turns.length&&!before)this.empty();if(!before&&data.session.imported_history)thread.prepend(make('p','Imported conversation history. The next turn opens a new provider conversation; saved project context and messages remain available.','session-import-notice session-help'));if(data.active&&!before){await this.connect(data.active.id,data.active.cursor,data.active);}if(data.recovery)this.status(data.recovery,true);if(!data.active&&!data.recovery)this.status('Draft a message');if(controlMessage)this.status(controlMessage.text,controlMessage.error);if(!before&&session===this.session&&epoch===this.viewEpoch&&load===this.sessionLoad&&!this.nativeAcknowledgement()?.draft_settled)this.showNativeAcknowledgement();if(this.controlPending)this.scheduleControlObservation();if(this.lastControlError?.session===this.session)this.status('Control request needs attention: '+this.lastControlError.message+' The original draft is retained; nothing was replayed.',true);
    }catch(error){if(session===this.session&&epoch===this.viewEpoch&&load===this.sessionLoad)throw error;}finally{if(session===this.session&&epoch===this.viewEpoch&&load===this.sessionLoad){this.loadingSession=false;this.setBusy(!!this.active);this.scope();}}
  }
  resetUsage(){const model=this.providers.find(p=>p.id===this.find('[data-provider]').value)?.models.find(m=>m.id===this.find('[data-model]').value);this.showUsage(null,model||{});}
  // The round trip's own readout: provider, tier and model, effort AS SENT, model_source
  // and the role's own defaults, all from rows the app already banks --- the EXISTING
  // writing-session-settings row (folded onto `session` by `authoring_surface._records`)
  // and the EXISTING catalogue annotation (`writing_provider.with_model_choice`,
  // `schema.model_choice_declaration`). No new row, no poll: this renders on every
  // session load and every settings save, from data already in hand.
  settingsTruth(session){
    this.paintAdmittedModel();
    const node=this.find('[data-settings-truth]');if(!node)return;
    const next={...session,provider:this.find('[data-provider]').value,model:this.find('[data-model]').value,effort:this.find('[data-effort]').value};if(session?.provider!==next.provider||session?.model!==next.model){delete next.model_source;delete next.tier;}if(this.effortSupported===false)next.effort=null;
    node.textContent=(this.active?'Admitted turn settings: '+(this.admittedSettings?settingsTruthText(this.admittedSettings,null):'not reported by this observation')+' · ':'')+'Next-message settings: '+settingsTruthText(next,null,next.provider);
  }
  showUsage(usage,context={}){
    const counter=contextUsageCounter(usage,context||{}),provider=this.providers.find(item=>item.id===this.find('[data-provider]').value),selected=provider?.models.find(item=>item.id===this.find('[data-model]').value);
    const number=value=>value!==null&&value!==undefined&&value!==''&&Number.isFinite(Number(value))&&Number(value)>0?Number(value):null;
    const selectedCapacity=!context?.provider||context.provider===provider?.id?selected?.context_window_advertised||selected?.context_window:null;
    const advertised=number(context?.context_window_advertised||context?.context_window||selectedCapacity),count=n=>n>=1000?(n/1000).toLocaleString(undefined,{maximumFractionDigits:1})+'k':n.toLocaleString();
    const label=this.find('[data-context-label]'),bar=this.find('[data-context-progress]');if(!label||!bar)return;bar.hidden=true;
    const capacity=counter.limit?' · reported limit '+count(counter.limit):advertised?' · advertised capacity '+count(advertised):'';
    if(counter.kind==='request-proxy'&&counter.value!==null)label.textContent='Latest request input: '+count(counter.value)+' tokens (proxy; exact context occupancy unavailable)'+capacity;
    else if(counter.kind==='selected'&&counter.value!==null)label.textContent='Selected context counter: '+count(counter.value)+' tokens · '+(counter.metric||'metric not specified')+capacity;
    else if(counter.kind==='legacy')label.textContent='Legacy reported usage value: '+count(counter.value)+' tokens · counter basis unknown'+capacity;
    else label.textContent=usage||context?.usage_selection||context?.usage_facts_projection?'Context usage unknown'+capacity:counter.limit?'Reported context limit '+count(counter.limit)+' tokens · usage not reported':advertised?'Advertised capacity '+count(advertised)+' tokens · actual usage not reported':'Context usage available after the session starts';
  }
  setBusy(busy){
    const operation=this.find('[data-operation-state]');if(operation){const words=conversationOperationPresentation({...this,submission:this.messageIntent?.submission});if(operation.textContent!==words){if(words.endsWith('…'))pendingRead(operation,words);else operation.textContent=words;}operation.hidden=!operation.textContent;}this.paintNextSummary?.();
    paintReaderSession(this);
    if(this.authoredContext().workflow_action)this.workflowActionConsumer().setBusy();
    if(this.parentContinuationValue?.turn_id===this.active)this.paintParentContinuation(this.parentContinuationValue,{turnId:this.active,active:true,keep:true});
    this.paintConnectedObservation();
    this.paintAdmittedModel();
    if(this.active&&this.activeCapabilities)this.observationText(steeringObservation(this.activeCapabilities,this.activeCapabilities.observation==='snapshots'));
    const locked=!!this.initializing||!!this.startupFailed||busy||!!this.active||!!this.loadingSession||!!this.submitting||!!this.messageIntent?.submission||readerSession(this.selectedSessionRecord);
    for(const selector of ['[data-provider]','[data-model]','[data-effort]','[data-mode]','[data-refresh]'])this.find(selector).disabled=locked||(selector==='[data-effort]'&&this.effortSupported===false);
    for(const selector of ['[data-sessions]','[data-new]','[data-review]'])this.find(selector).disabled=!!this.submitting||!!this.initializing;
    // Update existing cards in place: admission settlement must not rebuild the
    // library, steal focus or disturb the selected conversation's draft.
    for(const card of this.find('[data-conversation-list]')?.children||[])if(String(card.className||'').split(' ').includes('conversation-library-row'))card.disabled=!!this.submitting||!!this.initializing;
    this.syncTurnTarget?.();this.find('[data-more]').disabled=!!this.loadingSession;this.find('[data-stop]').hidden=!this.active;this.find('[data-stop]').disabled=!this.active||!!this.submitting||this.stopRequested||this.activeCapabilities?.can_interrupt!==true||this.stopWithheld();
    const visibleBlock=this.find('[data-composer-block]');if(visibleBlock){visibleBlock.textContent=this.preferenceBlockReason();visibleBlock.hidden=!visibleBlock.textContent;}this.modeHelp();
    const delivery=inputDeliveryMode(this.activeCapabilities||{}),inputReady=!!this.active&&!!delivery&&!this.controlPending&&!this.stopRequested;this.find('[data-send]').disabled=!!this.preferenceBlockReason()||readerSession(this.selectedSessionRecord)||!this.messageIntent?.submission&&!!this.controlPending||!!this.initializing||!!this.startupFailed||!!this.submitting||!!this.loadingSession||locked&&!inputReady&&!this.messageIntent?.submission;this.find('[data-send]').textContent=this.messageIntent?.submission?'Check submission':this.initializing?'Opening conversation…':this.startupFailed?'Conversation unavailable':this.active?(delivery==='native_rpc'?'Steer selected turn':delivery==='project_tool_boundary'?'Queue input for next tool result':'Input unavailable'):this.controlPending?'Inspect pending input':this.session?'Send follow-up':'Send';this.preferenceUI?.syncLocks();
  }
  async send(){
    const preferenceBlock=this.preferenceBlockReason();if(preferenceBlock){this.openInspector('settings');throw Error(preferenceBlock);}
    if(readerSession(this.selectedSessionRecord))throw Error('This text-only reader is one attempt. Inspect its report or prepare a fresh reader.');
    if(this.submitting||this.loadingSession||this.initializing||this.startupFailed)return;
    if(this.messageIntent?.submission){await this.reconcileActionSubmission();return;}
    {const box=this.find('[data-message]'),queued=(this.queued||[]).some(task=>['open','ready'].includes(task.status)&&!this.queueExcluded?.has(task.id));if(box&&!box.value.trim()&&!queued){refuseEmptySend(box,this.find('[data-send]'));return;}}
    if(this.controlPending)throw Error('The exact input receipt is unresolved. Refresh this conversation to inspect it; no follow-up was sent.');
    this.submitting=true;this.setBusy(true);
    const input=this.find('[data-message]'),controlTarget=this.active,controlSession=this.session,controlProject=this.project,controlEpoch=this.viewEpoch,deliveryMode=inputDeliveryMode(this.activeCapabilities||{}),submittedDraft=input.value,intentRevision=this.intentRevision||0,submittedIntent=this.messageIntent?structuredClone(this.messageIntent):null,intentContext=structuredClone(this.authoredContext()),intentSelection=this.selectionOverride?structuredClone(this.selectionOverride):null,intentQueued=(this.queued||[]).filter(task=>['open','ready'].includes(task.status)&&!this.queueExcluded?.has(task.id)).map(task=>task.id);this.lastControlError=null;
    try{
      const connectedSeconds=!controlTarget&&this.role==='author'&&!this.selectedSessionRecord?.dispatch_id&&this.find('[data-mode]').value==='work'?connectedObservationSeconds(submittedIntent):undefined;
      await this.ready;await this.loadQueue();
      if(this.project!==controlProject||this.viewEpoch!==controlEpoch||this.session!==controlSession||this.active!==controlTarget)throw Error('The selected conversation or turn changed while preparing this request. No follow-up or input was started; the draft is retained.');
      const queuedIds=intentQueued;
      const text=submittedDraft.trim()||(queuedIds.length?'Work through the queued requests at their selected manuscript passages.':'');
      if(!text){refuseEmptySend(input,this.find('[data-send]'));return;}
      if(this.active&&(!deliveryMode||inputDeliveryMode(this.activeCapabilities||{})!==deliveryMode||this.stopRequested||this.controlPending))throw Error('The execution owner has not enabled this input mode for the selected turn. Refresh its status or wait for the reply.');
      this.setBusy(true);this.status('Preparing the current project context…');pendingRead(this.find('[data-status]'));
      const prepared=await this.prepareSend?.({context:intentContext,selection:intentSelection});
      if(this.project!==controlProject||this.viewEpoch!==controlEpoch||this.session!==controlSession||this.active!==controlTarget||controlTarget&&inputDeliveryMode(this.activeCapabilities||{})!==deliveryMode)throw Error('The selected turn ended or its input mode changed while preparing this request. No follow-up or input was started; the draft is retained.');
      // Saving may change source spans or the current block. Attention is read only
      // after the editor has settled; an explicit unsaved draft remains separate.
      const fresh=this.authoredContext(),scope=value=>JSON.stringify(value);
      if((this.intentRevision||0)!==intentRevision||!sameComposerIntent(this.messageIntent,submittedIntent)||scope(fresh)!==scope(intentContext))throw Error('The selected work or context changed while preparing this request. Nothing was dispatched; the original draft is retained.');
      const context=intentContext;
      const selection=prepared?.selection||intentSelection||undefined;
      if(context.workflow_action&&controlTarget)throw Error('Selected workflow actions require an idle original author conversation.');
      const workspace_context={...(context.workflow_action?{workflow_action:workflowActionInput(context.workflow_action,{project:controlProject,session:controlSession,work:context.task_id})}:{}),surface:context.surface||'project',node_id:context.node_ids?.length?null:context.node_id,node_ids:context.node_ids,...(context.label?{label:String(context.label).slice(0,240)}:{}),section_ids:context.section_ids,beat_id:context.beat_id,...(context.review?{review:context.review}:{}),...(context.structure_observation?{structure_observation:context.structure_observation}:{}),...(context.material_read?{material_read:materialReadingInput(context.material_read,{project:controlProject})}:{}),...(context.object_context?{object_context:objectContextInput(context.object_context)}:{})};
      const clearSubmitted=()=>this.clearSentDraft(submittedDraft,{intentRevision,submittedIntent});
      if(this.active){
        const observation=this.activeCapabilities?.observation;
        const response=await projectRequest('/authoring/steer',{project:controlProject,turn_id:controlTarget,text,selection,workspace_context,delivery_mode:deliveryMode});
        const sameView=()=>this.project===controlProject&&this.viewEpoch===controlEpoch&&this.session===controlSession;
        if(deliveryMode==='project_tool_boundary'||response.delivery==='PENDING'||observation==='snapshot'&&response.delivery!=='DELIVERED'){
          if(typeof response.control_id!=='string'||!response.control_id)throw Error('Input acknowledgement has no exact receipt. The draft is retained; inspect the selected turn before retrying.');
          if(deliveryMode==='project_tool_boundary'&&(response.delivery!=='PENDING'||response.delivery_mode!==deliveryMode))throw Error('Queued input acknowledgement did not identify the requested delivery mode. Your draft is retained; inspect the turn before retrying.');
          const pending={id:response.control_id,turn:controlTarget,session:controlSession,project:controlProject,delivery_mode:deliveryMode,submitted:submittedDraft,selection,intentRevision,submittedIntent,admitted:true};this.pendingControls??=new Map();this.pendingControls.set(controlSession,pending);
          if(!sameView())return;
          this.controlPending=pending;this.settleAdmittedDraft(pending);this.status(deliveryMode==='project_tool_boundary'?'Input saved, waiting for the next tool result. You can compose the next input while publication settles.':'Native steering admitted; delivery is not confirmed. The saved input remains in its receipt.');
          if(this.active!==controlTarget){try{await this.readPendingControl(pending);}catch{if(sameView())this.status('Input was admitted before this turn ended or changed. Its exact receipt remains available; your text is retained.',true);}}
          if(sameView())this.scheduleControlObservation();
        }else{
          // A direct native reply has no control receipt. Retain the actual
          // acknowledgement before any view/turn guard, without fabricating one.
          const acknowledged={kind:'native-acknowledgement',turn:controlTarget,session:controlSession,project:controlProject,delivery_mode:deliveryMode,submitted:submittedDraft,selection,intentRevision,submittedIntent,response};this.pendingControls??=new Map();this.pendingControls.set(controlSession,acknowledged);
          if(!sameView())return;
          this.authorMessage(text,selection);this.showNativeAcknowledgement();
        }
        if(this.activeCapabilities?.observation==='snapshot')await this.refreshSelectedConversation();return;
      }
      const mode=this.find('[data-mode]').value;
      if(context.workflow_action&&(mode!=='work'||this.role!=='author'||this.selectedSessionRecord?.dispatch_id))throw Error('Use the original author conversation in work mode for this selected action.');
      await this.settingsSave;
      const payload={project:this.project,session_id:this.session||undefined,provider:this.find('[data-provider]').value,model:this.find('[data-model]').value,effort:this.effortSupported===false?null:this.find('[data-effort]').value,text,mode,...(connectedSeconds!==undefined?{connected_observation_seconds:connectedSeconds}:{}),queued_work_ids:queuedIds,selection,work_id:context.task_id,...(context.task_id&&context.expected_work_scope_revision?{expected_work_scope_revision:context.expected_work_scope_revision,expected_dependency_revision:context.expected_dependency_revision}:{}),workspace_context,request_id:crypto.randomUUID()};
      const result=context.workflow_action?await this.submitActionPayload(payload,{submittedDraft,intentRevision,submittedIntent}):await projectRequest('/authoring/turn',payload);
      if(context.workflow_action)return;
      clearSubmitted();this.switchDraftTarget(result.session_id);this.session=result.session_id;this.sessionSettingsRead=result.settings_read;this.rememberMode(mode);
      localStorage.setItem(this.settingsKey(),JSON.stringify({...this.savedSettings(),provider:this.find('[data-provider]').value,model:this.find('[data-model]').value,effort:this.effortSupported===false?null:this.find('[data-effort]').value}));this.rememberConversationSelection(this.session);
      this.markTransient(this.authorMessage(text,selection),result.turn_id,'request');if(selection?.draft)this.status('Included the unsaved manuscript draft; the saved source is unchanged.');
      this.markTransient(this.message('assistant',''),result.turn_id,'reply');this.admittedSettings=null;this.activeScope=context.label||'This project';this.origin={...(this.origin||{}),workId:context.task_id||null,turnId:result.turn_id};if(this.onWorkObservation)void this.observeWork('acknowledged',result.turn_id,()=>this.project===controlProject&&this.session===result.session_id&&this.viewEpoch===controlEpoch&&this.origin?.turnId===result.turn_id);await this.connect(result.turn_id);await this.loadQueue();this.find('[data-thread]').scrollTop=this.find('[data-thread]').scrollHeight;
    }catch(error){if(controlTarget)this.lastControlError={session:controlSession,turn:controlTarget,message:error.message};throw error;}finally{this.submitting=false;this.setBusy(!!this.active);}
  }

  observationURL(raw,path,id,key){const base=globalThis.location?.href||'http://localhost/';const value=new URL(raw,base);if(value.origin!==new URL(base).origin||value.pathname!==path||value.searchParams.get(key)!==id)throw Error('The owner observation URL does not match this selected target.');return value;}
  paintControlReceipts(execution=this.execution){
    const host=this.find('[data-control-receipts]');if(!host)return;
    const matching=!!this.session&&(!execution?.project||execution.project===this.project)&&(!execution?.session_id||execution.session_id===this.session);
    const rows=matching?(execution?.controls||[]).filter(row=>(!row.project||row.project===this.project)&&(!row.session_id||row.session_id===this.session)&&(row.turn_id===this.active||!this.active)):[],acknowledged=this.session?this.nativeAcknowledgement():null;
    const signature=JSON.stringify([this.project,this.session,this.active,rows,acknowledged]);if(signature===this.controlReceiptSignature)return;this.controlReceiptSignature=signature;
    // Placement only: the sender's display classifier owns uncertainty; slot settlement is unchanged.
    const attentionRows=rows.filter(inputReceiptNeedsAttention),ackAttention=acknowledged&&inputReceiptNeedsAttention(acknowledged);
    const cue=this.find('[data-input-attention]');if(cue){const heldFocus=cue===document.activeElement;cue.hidden=!attentionRows.length&&!ackAttention;if(cue.hidden&&heldFocus)this.find('[data-context-open]')?.focus({preventScroll:true});cue.textContent=attentionRows.some(row=>row.state==='OFFERED_UNACKNOWLEDGED')?'Reading unconfirmed — inspect':'Input needs attention — inspect';}
    const opened=!!host.querySelector('details')?.open;host.replaceChildren();if(!rows.length&&!acknowledged)return;const detail=make('details');detail.open=opened;detail.append(make('summary',rows.length?'Input receipts · '+rows.length:'Native input acknowledgement'));
    if(acknowledged){detail.append(make('p','Native steering acknowledged for its original turn; acting on it is not proven.'));const provenance=make('details');provenance.append(make('summary','Original target, input and acknowledgement'));lazyContent(provenance,()=>provenance.append(make('pre',JSON.stringify(acknowledged,null,2))));detail.append(provenance);}
    for(const row of rows){const words={ADMITTED:'Queued',PENDING:'Queued',OFFERED_AT_TOOL_BOUNDARY:'Offered at the next tool result',PUBLISHED_AT_TOOL_BOUNDARY:'Sent with a project tool result; model attention is not proven',PREPARING_AT_TOOL_BOUNDARY:'Preparing scoped publication',PREPARED_AT_TOOL_BOUNDARY:'Prepared; publication pending',PUBLICATION_UNCONFIRMED:'Publication unconfirmed',PREPARING_AT_EXACT_READ:'Preparing exact input read',EXACT_SCOPED_CONTROL_READ:'Read by the session',DELIVERED:'Native delivery acknowledged',FAILED:'Failed',UNCONFIRMED:'Reading unconfirmed',OFFERED_UNACKNOWLEDGED:'Turn ended before reading was confirmed'};detail.append(make('p',(row.state==='PUBLISHED_AT_TOOL_BOUNDARY'&&inputReceiptNeedsAttention(row)?row.publication?.scope==='PREVIEW'?'Preview offered; full input/context not yet read':'Publication completeness unproved; inspect saved input':words[row.state]||'Unproved input state')+(row.error?' · '+row.error:'')));
      const provenance=make('details');provenance.append(make('summary','Exact receipt and input'));lazyContent(provenance,()=>{provenance.append(make('pre',JSON.stringify(row,null,2)));if(row.control_id&&row.turn_id){const read=make('a','Read the exact saved input');read.href='/authoring/session-turn?'+new URLSearchParams({project:this.project,id:row.turn_id,view:'controls',item_id:row.control_id,limit:1});read.download='saved-input.json';provenance.append(read);}});detail.append(provenance);
    }host.append(detail);
  }
  finishPendingObservation(execution){
    const pending=this.controlPending;if(!pending||pending.project!==this.project||pending.session!==this.session||execution?.turn_id!==pending.turn||!['FINISHED','FAILED','BLOCKED'].includes(execution.state))return;
    this.status('Turn ended before input reading was confirmed. Your text is retained; no follow-up is sent automatically.',true);this.controlPending=null;if(this.pendingControls?.get(this.session)===pending)this.pendingControls.delete(this.session);clearTimeout(this.snapshotTimer);this.snapshotTimer=null;
  }
  settleControlReceipt(receipt){
    const pending=this.controlPending;if(!pending||pending.project!==this.project||pending.session!==this.session||receipt?.control_id!==pending.id||receipt.turn_id!==pending.turn||receipt.delivery_mode!==pending.delivery_mode)return false;
    const published=pending.delivery_mode==='project_tool_boundary'&&receipt.state==='PUBLISHED_AT_TOOL_BOUNDARY';
    const acknowledged=pending.delivery_mode==='native_rpc'?receipt.state==='DELIVERED':receipt.state==='EXACT_SCOPED_CONTROL_READ';
    const failed=['FAILED','UNCONFIRMED','OFFERED_UNACKNOWLEDGED'].includes(receipt.state)||pending.delivery_mode==='project_tool_boundary'&&receipt.terminal===true;
    if(acknowledged||published){if(pending.admitted)this.settleAdmittedDraft(pending);else this.clearSentDraft(pending.submitted,{intentRevision:pending.intentRevision,submittedIntent:pending.submittedIntent});if(typeof pending.submitted==='string')this.authorMessage(pending.submitted,pending.selection);this.status(pending.delivery_mode==='native_rpc'?'Native steering delivery acknowledged; acting on it is not proven.':published?inputReceiptNeedsAttention(receipt)?receipt.publication?.scope==='PREVIEW'?'Preview offered; full input/context not yet read. The saved input remains inspectable.':'Publication completeness unproved; inspect the saved input.':'Input sent with a project tool result. Model attention or action is not proven; the saved input is inspectable.':'Queued input read by the session in its exact project context; acting on it is not proven.');}
    else if(failed)this.status((receipt.state==='OFFERED_UNACKNOWLEDGED'?'Turn ended before input reading was confirmed.':receipt.state==='FAILED'?'Queued input failed.':receipt.state==='PUBLICATION_UNCONFIRMED'?'Input publication is unconfirmed.':'Input reading is unconfirmed.')+' Your text is retained; nothing is replayed.',true);
    else if(pending.observed_state!==receipt.state)this.status(receipt.state==='OFFERED_AT_TOOL_BOUNDARY'?'Input offered at the next tool result; reading is not confirmed. Your draft is retained.':receipt.state==='PREPARING_AT_EXACT_READ'?'The session is preparing an exact input read; acknowledgement is pending. Your draft is retained.':pending.admitted?'Input saved, waiting for publication at the next tool result. Your current draft is preserved.':'Input queued for this turn; reading is not confirmed. Your draft is retained.');
    pending.observed_state=receipt.state;
    if(acknowledged||published||failed){this.controlPending=null;if(this.pendingControls?.get(this.session)===pending)this.pendingControls.delete(this.session);clearTimeout(this.snapshotTimer);this.snapshotTimer=null;this.setBusy(!!this.active);return true;}return false;
  }
  async readPendingControl(pending=this.controlPending){
    if(!pending)return;if(pending.project!==this.project||pending.session!==this.session)throw Error('Input receipt belongs to another conversation or project.');const epoch=this.viewEpoch,session=this.session,project=this.project;
    const current=()=>epoch===this.viewEpoch&&session===this.session&&project===this.project&&this.controlPending===pending;
    const path='/authoring/session-turn?'+new URLSearchParams({project:pending.project,id:pending.turn,view:'controls',item_id:pending.id,limit:1});
    const data=await projectRequest(path);if(!current())return;
    if(data.project!==pending.project||data.turn_id!==pending.turn||data.view!=='controls'||data.exact!==true||data.items?.length!==1)throw Error('Input observation did not match its exact owner receipt. Your draft is retained.');
    this.paintControlReceipts({controls:data.items});this.settleControlReceipt(data.items[0]);
  }
  scheduleControlObservation(){
    if(!this.controlPending||this.activeCapabilities?.observation==='snapshot')return;
    clearTimeout(this.snapshotTimer);const pending=this.controlPending,session=this.session,project=this.project,epoch=this.viewEpoch;
    const current=()=>pending===this.controlPending&&session===this.session&&project===this.project&&epoch===this.viewEpoch;
    const poll=async()=>{if(!current())return;if(globalThis.document?.visibilityState==='hidden'){this.snapshotTimer=setTimeout(poll,2000);return;}try{await this.readPendingControl(pending);if(current())this.snapshotTimer=setTimeout(poll,2000);}catch(error){if(current())this.status('Queued input observation is unavailable. Your text is retained; refresh this conversation to inspect it.',true);}};
    this.snapshotTimer=setTimeout(poll,2000);
  }
  acceptObservation(data,id){
    if(data.session?.id&&data.session.id!==this.session)throw Error('Observed conversation identity changed.');if(data.session?.project&&data.session.project!==this.project)throw Error('Observed project identity changed.');
    if(data.execution)this.execution=data.execution;const admitted=data.active?.id===id?data.active.provider_settings:null;const saved=(data.turns||[]).find(turn=>turn.id===id)?.provider_settings;if(admitted||saved)this.admittedSettings=admitted||saved;
    this.settingsTruth(data.session);this.paintControlReceipts(data.execution);const pending=this.controlPending;if(pending){const receipt=(data.execution?.controls||[]).find(row=>row.control_id===pending.id&&row.turn_id===pending.turn);if(receipt)this.settleControlReceipt(receipt);}
    if(data.active?.id===id){this.activeCapabilities=data.active.capabilities;const continuation=Object.hasOwn(data.active,'parent_continuation')?data.active.parent_continuation:data.execution?.turn_id===id?data.execution?.parent_continuation:undefined;this.paintParentContinuation(continuation,{turnId:id,active:true,keep:true});this.setBusy(true);return true;}return false;
  }
  // THE SELECTED ACTOR'S TURN (Work Now → this conversation): the Work view names turn A when it opens the conversation; loadSession
  // confirms A against the owner's current active turn, and Stop is withheld whenever the conversation shows another turn or no
  // active turn. The recorded A stays readable; a newer turn B is targeted only by an explicit choice, never by the original link.
  // the Work a conversation observation itself records for ONE exact turn (its active record, the execution of that turn, its
  // saved turn), read ONLY from the canonical work_id of a fresh record whose own id is that turn. Never a cached origin, the
  // general session origin or work target, another turn's Work, a dispatch identity or the Work of a superseded link.
  static turnWorks(data,turnId){const found=new Set();if(!turnId||!data)return found;const add=row=>{if(typeof row?.work_id==='string'&&row.work_id)found.add(row.work_id);};
    if(data.active?.id===turnId)add(data.active);
    if(data.execution?.turn_id===turnId)add(data.execution);
    for(const turn of data.turns||[])if(turn?.id===turnId)add(turn);
    return found;}
  // exactly one Work named by those fresh same-turn records, else null: missing, conflicting or ambiguous stays withheld
  static turnWork(data,turnId){const found=WorkspaceSession.turnWorks(data,turnId);return found.size===1?[...found][0]:null;}
  targetTurn(target){if(!target?.sessionId||!target.turnId)return;this.pendingTurnTarget={project:target.project||this.project,workId:target.workId||null,sessionId:target.sessionId,turnId:target.turnId,observedState:target.observedState||null,observedAt:target.observedAt||null};}
  // a named turn belongs to the one open attempt that carried it: a refused or failed open drops it
  dropTurnTarget(target=null){const held=this.pendingTurnTarget;if(held&&(!target||(held.sessionId===target.sessionId&&held.turnId===target.turnId)))this.pendingTurnTarget=null;}
  adoptTurnTarget(data){const held=this.pendingTurnTarget;if(held&&held.sessionId===this.session&&(!held.project||!this.project||held.project===this.project)){this.turnTarget={...held};this.pendingTurnTarget=null;}const target=this.turnTarget;if(!target||target.sessionId!==this.session)return null;
    const activeId=data?.active?.id||null;target.activeId=activeId;target.confirmedAt=new Date().toISOString();
    // A link target is confirmed by the loaded conversation showing that turn as current. An explicitly chosen turn is confirmed
    // ONLY by confirmTurnTarget: a poll, a reload or the live-turn sync can withdraw its confirmation, never manufacture one.
    if(target.explicit){if(!data?.settled){if(activeId!==target.turnId){if(target.state!=='refused'){target.state=activeId?'advanced':'ended';target.reason='';}}else if(['advanced','ended'].includes(target.state)){target.state='unconfirmed';target.reason='it is shown as current again but has not been confirmed';}}
      target.matched=target.state==='confirmed';}
    else target.matched=activeId===target.turnId;
    const thread=this.find('[data-thread]');if(thread){thread.querySelector?.('[data-turn-target]')?.remove();const note=make('p','','session-help session-turn-target');note.dataset.turnTarget=target.turnId;note.dataset.turnTargetState=target.explicit?target.state:target.matched?'confirmed':activeId?'advanced':'ended';
      note.append(make('span',target.explicit&&target.state==='pending'?'You chose turn '+target.turnId+'. Checking it with its conversation owner; Stop is withheld until it is confirmed.':target.explicit&&['unconfirmed','unavailable','refused'].includes(target.state)?'You chose turn '+target.turnId+'. '+(target.state==='refused'?'It was refused: ':'It is not confirmed: ')+(target.reason||'its conversation owner has not confirmed it')+'. Stop is withheld.':target.matched?(target.explicit?'You chose turn '+target.turnId+'. ':'')+'Stop targets turn '+target.turnId+' exactly; confirmed as the current turn at '+target.confirmedAt+'.':activeId?(target.explicit?'You chose turn ':'This link named turn ')+target.turnId+'. The conversation has advanced to turn '+activeId+'; Stop is withheld because it would end '+activeId+', not '+target.turnId+'.':'Turn '+target.turnId+' is not running now (no active turn observed at '+target.confirmedAt+'); there is nothing to stop.'));
      if(this.onReadTurn){const read=make('button','Read saved turn '+target.turnId);read.type='button';read.onclick=()=>this.guard(()=>this.onReadTurn(target.turnId));note.append(' ',read);}
      if(target.explicit&&['unconfirmed','unavailable','refused'].includes(target.state)){const again=make('button','Check turn '+target.turnId+' again');again.type='button';again.onclick=()=>{void this.confirmTurnTarget?.();};note.append(' ',again);}
      if(!target.matched&&activeId&&activeId!==target.turnId){const choose=make('button','Target turn '+activeId+' explicitly');choose.type='button';choose.onclick=()=>{
        // the explicit choice PINS that exact project, Work, conversation and turn; it is never cleared into an untargeted Stop.
        // The Work is the one the session records for that turn, never the Work of the superseded link.
        this.turnTarget={project:this.project||target.project||null,workId:WorkspaceSession.turnWork(data,activeId),sessionId:this.session,turnId:activeId,explicit:true,state:'pending',reason:'',chosenAt:new Date().toISOString(),supersedes:target.turnId,activeId,matched:false};
        // pinned BEFORE any read and painted as pending: Stop stays withheld until the session door confirms this exact turn
        WorkspaceSession.prototype.adoptTurnTarget.call(this,{active:{id:activeId},settled:true});this.setBusy(!!this.active);void this.confirmTurnTarget?.();};note.append(' ',choose);}
      thread.prepend(note);}
    return target;}
  // the pin is compared with the live turn as well as with the last adopted observation, so a turn that started after the
  // chosen one never inherits Stop; a newer turn is targeted only by its own explicit choice
  stopWithheld(){const target=this.turnTarget;if(!target||target.sessionId!==this.session)return false;if(typeof this.active==='string'&&this.active&&this.active!==target.turnId)return true;if(target.explicit)return target.state!=='confirmed';return target.activeId!==undefined&&!target.matched;}
  // a turn that became active without a conversation reload is shown against the pin at once, with its own explicit choice
  syncTurnTarget(){const target=this.turnTarget;if(!target||target.sessionId!==this.session||typeof this.active!=='string'||!this.active||this.active===target.turnId||target.activeId===this.active)return;this.adoptTurnTarget({active:{id:this.active}});}
  // AFTER AN EXPLICIT CHOICE the pinned project, Work, conversation and turn are re-observed through the session door before
  // Stop is trusted: the same project and conversation, that turn still the active one, with the owner's current interrupt
  // capability. A failed or foreign observation withholds Stop; nothing is retargeted.
  async confirmTurnTarget(read=projectRequest){const pin=this.turnTarget;if(!pin?.explicit||pin.sessionId!==this.session)return null;const project=this.project,session=this.session,epoch=this.viewEpoch;
    const attempt=pin.attempt=(this.turnTargetAttempt=(this.turnTargetAttempt||0)+1),adopt=data=>WorkspaceSession.prototype.adoptTurnTarget.call(this,data);
    // one outcome per attempt: the pin keeps its turn in every state and is never cleared; only `confirmed` releases Stop
    const settle=(state,reason,data=null)=>{pin.state=state;pin.reason=reason;pin.matched=state==='confirmed';adopt({...(data||{active:pin.activeId?{id:pin.activeId}:null}),settled:true});this.setBusy(!!this.active);return pin;};
    if(pin.state!=='pending'){pin.state='pending';pin.reason='';pin.matched=false;adopt({active:pin.activeId?{id:pin.activeId}:null,settled:true});this.setBusy(!!this.active);}
    if(pin.project&&project&&pin.project!==project)return settle('refused','it was chosen in another project');
    let data=null,failure='';try{data=await read('/authoring/session?'+new URLSearchParams({project,id:session,view:'summary',limit:1}));}catch(error){failure=error?.message||'the read failed';}
    // a late reply for an older attempt, a replaced pin, another conversation or another view changes nothing
    if(this.turnTarget!==pin||pin.attempt!==attempt||project!==this.project||session!==this.session||epoch!==this.viewEpoch)return null;
    // CONFIRMED only by exact facts of this one observation: its project and conversation, this turn as the active one, the Work
    // that observation records for this turn (equal to the pinned Work when one was pinned) and can_interrupt true
    if(!data)return settle('unconfirmed','its conversation owner could not be read ('+failure+')');
    if(data.session?.id==null||data.session?.project==null)return settle('unconfirmed','the conversation owner did not say which project and conversation it answered for');
    if(data.session.id!==session||data.session.project!==project)return settle('refused','the reply belongs to another project or conversation');
    const activeId=data.active?.id||null;if(activeId!==pin.turnId)return settle(activeId?'advanced':'ended','',data);
    // the Work comes ONLY from this fresh observation's own records naming this exact turn; nothing cached or general is consulted
    const works=WorkspaceSession.turnWorks(data,pin.turnId),work=works.size===1?[...works][0]:null;
    if(works.size>1)return settle('unconfirmed','the conversation owner reports conflicting tasks for this turn',data);
    if(!work)return settle('unconfirmed','the conversation owner does not say which task this turn belongs to',data);
    if(pin.workId&&work!==pin.workId)return settle('refused','the turn now reports another task than the one pinned',data);
    const capability=data.active.capabilities?.can_interrupt;
    if(capability!==true)return settle(capability===false?'unavailable':'unconfirmed',capability===false?'its owner says it cannot be interrupted now':'its owner did not report whether it can be interrupted',data);
    pin.workId=work;pin.revalidatedAt=new Date().toISOString();
    if(this.active===pin.turnId)this.acceptObservation(data,pin.turnId);   // the fresh owner capability replaces the cached one
    return settle('confirmed','',data);}
  // A NEWER OBSERVATION OF ANOTHER TURN RETIRES AN OLDER PENDING CONFIRMATION. The selected refresh and the detached snapshot
  // poll call this on their own mismatch branch, already inside this conversation's session, view and stream lifetime, when the
  // owner reports an active turn other than the one being observed. A confirmation read of the chosen turn that is still in
  // flight was asked before that fact, so its reply may not release Stop after it: the attempt is retired on the existing
  // attempt counter (its late reply returns without effect) and the pin, which keeps its turn, is shown as advanced with its
  // saved-turn read and the newer turn's own explicit choice. Nothing is retargeted and no second store is kept; only a later
  // confirmation, a new attempt on its own fresh read, can confirm. A reply naming another conversation or project, no active
  // turn, the observed turn itself or the pinned turn retires nothing; a conversation with no explicit choice is untouched.
  retireTurnConfirmation(data,id){const seen=data?.active?.id,pin=this.turnTarget;
    if(typeof seen!=='string'||!seen||seen===id||!pin?.explicit||pin.sessionId!==this.session||pin.turnId===seen)return false;
    if((data.session?.id!=null&&data.session.id!==this.session)||(data.session?.project!=null&&data.session.project!==this.project))return false;
    pin.attempt=this.turnTargetAttempt=(this.turnTargetAttempt||0)+1;
    WorkspaceSession.prototype.adoptTurnTarget.call(this,data);return true;}
  async stopSelectedTurn(post=projectRequest){const id=this.active,epoch=this.viewEpoch,session=this.session;if(!id||this.activeCapabilities?.can_interrupt!==true||this.stopRequested||this.stopWithheld())return;
    // the pin is compared once more at the one Stop request: only its exact turn, and for a chosen turn only once confirmed
    const pin=this.turnTarget;if(pin&&pin.sessionId===session&&(pin.turnId!==id||(pin.explicit&&pin.state!=='confirmed')))return;
    this.stopRequested=true;this.setBusy(true);try{await post('/authoring/interrupt',{project:this.project,turn_id:id});if(epoch===this.viewEpoch&&session===this.session&&this.active===id){this.status('Stop requested for the selected turn. Waiting for its terminal owner observation.');await this.refreshSelectedConversation();}}catch(error){if(epoch===this.viewEpoch&&session===this.session){this.stopRequested=false;this.setBusy(!!this.active);}throw error;}}
  async refreshSelectedConversation(){if(this.startupFailed)return this.start();if(!this.session)return;const session=this.session,epoch=this.viewEpoch,id=this.active;if(!id)return this.loadSession();const raw=this.activeCapabilities?.snapshot_url||'/authoring/session?'+new URLSearchParams({project:this.project,id:session,view:'summary',limit:1});const endpoint=this.observationURL(raw,'/authoring/session',session,'id');const data=await projectRequest(endpoint.pathname+endpoint.search);if(session!==this.session||epoch!==this.viewEpoch)return;if(this.acceptObservation(data,id))return;if(data.active){this.activeCapabilities=null;this.retireTurnConfirmation(data,id);this.status('The active turn changed. Select this conversation again before targeting the new turn.',true);this.setBusy(true);return;}this.active='';this.activeCapabilities=null;this.stopRequested=false;clearTimeout(this.snapshotTimer);this.snapshotTimer=null;this.markRunning(session,null);await this.loadSession();}
  observeSnapshots(id,observation){this.stream?.close();this.stream=null;clearTimeout(this.snapshotTimer);const generation=this.streamGeneration=(this.streamGeneration||0)+1,session=this.session,epoch=this.viewEpoch;this.active=id;this.markRunning(session,id);this.settingsTruth(this.selectedSessionRecord);this.scope();this.setBusy(true);this.observationText(steeringObservation(observation.capabilities,true));this.status('Owner reports '+(observation.progress||'active execution')+'.');const interval=Math.max(500,Math.min(10000,Number(observation.capabilities.poll_interval_ms)||2000));const endpoint=this.observationURL(observation.capabilities.snapshot_url,'/authoring/session',session,'id');const current=()=>session===this.session&&epoch===this.viewEpoch&&generation===this.streamGeneration&&this.active===id;
    const poll=async()=>{if(!current())return;try{const data=await projectRequest(endpoint.pathname+endpoint.search);if(!current())return;if(!this.acceptObservation(data,id)){if(data.active){this.activeCapabilities=null;this.retireTurnConfirmation(data,id);this.setBusy(true);this.status('The selected turn changed. Select this conversation again to inspect its new target.',true);return;}void this.observeWork('complete',id,()=>session===this.session&&epoch===this.viewEpoch&&this.origin?.turnId===id);if(!current())return;this.active='';this.activeCapabilities=null;this.stopRequested=false;this.markRunning(session,null);await this.loadSession();return;}this.snapshotTimer=setTimeout(poll,interval);}catch(error){if(!current())return;this.activeCapabilities=null;this.scope();this.setBusy(true);this.status('Execution observation unavailable: '+error.message+'. Automatic observation stopped; refresh to check again.',true);}};this.snapshotTimer=setTimeout(poll,interval);}
  async observeWork(phase,id,isCurrent=()=>true){
    const project=this.project,session=this.session,epoch=this.viewEpoch,work=this.origin?.turnId===id?this.origin.workId:null;
    if(!this.onWorkObservation||!project||!session||!id||this.origin?.turnId!==id||!isCurrent())return;
    const key=[project,session,epoch,id].join('|'),field=phase==='complete'?'workCompletedObservation':'workStartedObservation';
    if(this[field]===key)return;this[field]=key; // One callback per observed turn phase, never a polling cache of Work truth.
    const fresh=()=>project===this.project&&session===this.session&&epoch===this.viewEpoch&&isCurrent();
    try{return await this.onWorkObservation({project,session_id:session,turn_id:id,work_id:work??null,phase},fresh);}catch(error){if(fresh())this.status('Execution is retained; selected Work needs reinspection: '+error.message,true);}
  }
  async connect(id,cursor=0,observation=null){
    if(!observation?.capabilities){const session=this.session,epoch=this.viewEpoch;const data=await projectRequest('/authoring/session?'+new URLSearchParams({project:this.project,id:session,view:'summary',limit:1}));if(session!==this.session||epoch!==this.viewEpoch)return;if(data.active?.id!==id){this.status('The selected turn is no longer active. Refresh this conversation before sending.',true);return;}observation=data.active;this.acceptObservation(data,id);}
    if(observation.session_id&&observation.session_id!==this.session||observation.id!==id)throw Error('The observed execution does not match the selected conversation and turn.');
    const workSession=this.session,workEpoch=this.viewEpoch;if(this.onWorkObservation)void this.observeWork('start',id,()=>this.session===workSession&&this.viewEpoch===workEpoch&&this.origin?.turnId===id);if(this.session!==workSession||this.viewEpoch!==workEpoch)return;
    this.activeCapabilities=observation.capabilities;this.stopRequested=false;this.paintParentContinuation(observation.parent_continuation,{turnId:id,active:true,keep:true});
    if(observation.capabilities.observation==='snapshot')return this.observeSnapshots(id,observation);
    if(observation.capabilities.observation!=='events'||!observation.capabilities.events_url){this.status('The owner has not provided a live observation capability. Refresh the selected conversation.',true);this.setBusy(true);return;}
    this.stream?.close();const generation=this.streamGeneration=(this.streamGeneration||0)+1,session=this.session,epoch=this.viewEpoch;
    this.active=id;this.markRunning(session,id);this.settingsTruth(this.selectedSessionRecord);this.scope();this.setBusy(true);this.status('The execution owner reports this turn active.');
    let answer;let messageStart=false;
    const endpoint=this.observationURL(this.activeCapabilities.events_url,'/authoring/events',id,'turn');endpoint.searchParams.set('after',cursor);this.observationText(steeringObservation(this.activeCapabilities));const savedRow=this.find('[data-thread]').querySelector('[data-turn-key=\"'+CSS.escape(id)+'\"] [data-message-part=reply]');answer=(savedRow||this.transientMessages(id,'reply')[0]||this.markTransient(this.message('assistant',''),id,'reply')).querySelector('.session-body');this.messageStreams??=new Map();const retained=this.messageStreams.get(id)||'',observed=typeof observation.text==='string'?observation.text:'';if(this.find('[data-mode]').value!=='revise'){const text=observed.startsWith(retained)?observed:retained;this.messageStreams.set(id,text);if(answer.parentElement.messageReading)answer.parentElement.messageReading.stream(text);else answer.textContent=text;}const stream=new EventSource(endpoint.pathname+endpoint.search);this.stream=stream;
    let terminal=false,reconciling=false;
    const current=()=>session===this.session&&epoch===this.viewEpoch&&generation===this.streamGeneration;
    const finish=()=>{if(terminal)return false;terminal=true;stream.close();if(this.stream===stream)this.stream=null;this.active='';this.activeScope='';this.paintParentContinuation(null);this.observationText('Live output ended.');this.markRunning(session,null);this.scope();this.setBusy(false);return true;};
    const unsaved=text=>{if(!finish())return;answer.dataset.unsavedReply='true';const row=answer.parentElement;if(row&&!row.querySelector?.('.session-unsaved-reply'))row.append(make('p','This streamed reply is preserved here but was not saved. Reopen the conversation before relying on it.','session-help error session-unsaved-reply'));this.status(text,true);};
    stream.onmessage=event=>{
      if(!current()||this.stream!==stream||this.active!==id)return;const item=JSON.parse(event.data);
      if(item.type==='delta'&&this.find('[data-mode]').value!=='revise'){const thread=this.find('[data-thread]'),atEnd=thread.scrollHeight-thread.scrollTop-thread.clientHeight<80;const reader=answer.parentElement.messageReading;const text=appendStreamText(reader?.state.stream||answer.textContent,item.text,messageStart);this.messageStreams??=new Map();this.messageStreams.set(id,text);if(reader)reader.stream(text);else answer.textContent=text;if(item.text)messageStart=false;if(atEnd)thread.scrollTop=thread.scrollHeight;}
      else if(item.type==='progress'){if(item.text==='agentMessage')messageStart=true;this.status(String(item.text).replace(/([a-z])([A-Z])/g,'$1 $2'));}
      else if(item.type==='usage')this.showUsage(item.usage,item);
      else if(item.type==='dispatch-continuation'){
        const continuation=item.parent_continuation;
        if(continuation?.project!==this.project||continuation.session_id!==session||continuation.turn_id!==id)return;
        this.paintParentContinuation(continuation,{turnId:id,active:true});
      }
      else if(item.type==='execution-observation'){
        if(item.project!==this.project||item.session_id!==session||item.turn_id!==id||!item.capabilities||item.capabilities.observation!=='events'||typeof item.capabilities.can_steer!=='boolean'||typeof item.capabilities.can_interrupt!=='boolean')return;
        try{this.observationURL(item.capabilities.events_url,'/authoring/events',id,'turn');}catch{return;}
        this.acceptObservation({session:{id:session,project:item.project},active:{id,capabilities:item.capabilities}},id);
      }
      else if(item.type==='complete'){
        this.showUsage(item.result.usage,item.result);if(!finish())return;
        this.guard(async()=>{
          let catalogueError=null;try{await this.loadSessions();}catch(error){catalogueError=error;}if(!current())return;
          // Loading the final reply invalidates the old stream generation itself.
          const finalLoad=this.sessionLoad+1;await this.loadSession();
          const sameView=()=>session===this.session&&epoch===this.viewEpoch&&finalLoad===this.sessionLoad&&!this.active;
          if(!sameView())return;const hadFailures=turnFailures({reply:item.result,tool_failures:item.result.tool_failures}).length>0||this.find('[data-thread]').lastElementChild?.querySelector('.session-tool-failures');const completion=turnCompletionStatus(item.result,!!hadFailures);this.status(completion.text+(catalogueError?' Conversation list unavailable: '+catalogueError.message+'. Refresh the list to retry.':''),completion.error||!!catalogueError);
          await this.onProposalChanged();if(!sameView())return;
          const workObservation=await this.observeWork('complete',id,sameView);if(!sameView())return;
          await this.onChanged(item.result.actions||[],workObservation);if(!sameView())return;await this.loadQueue();
        },()=>session===this.session&&epoch===this.viewEpoch);
      }else if(item.type==='error')unsaved(item.message);
    };
    stream.onerror=()=>{if(!current()||terminal||this.stream!==stream)return;stream.close();this.stream=null;if(reconciling)return;reconciling=true;this.guard(async()=>{const saved=await projectRequest('/authoring/session?'+new URLSearchParams({project:this.project,id:session,view:'summary',limit:1}));if(!current()||terminal)return;if(saved.active?.id===id){this.activeCapabilities=saved.active.capabilities;this.execution=saved.execution;this.paintControlReceipts(saved.execution);this.setBusy(true);this.status('Live output disconnected. The owner still reports this turn active; refresh the selected conversation to reconnect.',true);return;}const turn=(saved.turns||[]).find(row=>row.id===id);if(turn?.reply){finish();await this.loadSession();return;}unsaved('Connection ended before a final reply was saved. The visible text is preserved; no reconnect or provider replay was requested.');},()=>current()&&!terminal);};
  }
  remoteHistory(box,turn,view,render){
    const epoch=this.viewEpoch,session=this.session,list=make('div'),note=make('p','','session-help'),more=make('button','Load records');more.type='button';more.hidden=true;box.append(list,note,more);let offset=0,loaded=false,busy=false;
    const current=()=>epoch===this.viewEpoch&&session===this.session&&box.isConnected!==false;
    const load=async()=>{if(busy||offset==null||!current())return;busy=true;more.disabled=true;pendingRead(note,'Loading saved records…');try{const data=await projectRequest('/authoring/session-turn?'+new URLSearchParams({project:this.project,id:turn.detail.turn_id,view,offset,limit:20}));if(!current())return;if(view==='failures'&&(data.project!==this.project||data.turn_id!==turn.detail.turn_id||data.view!=='failures'))throw Error('The failure page belongs to a different project or turn.');for(const item of data.items||[])list.append(render(item));offset=data.pagination?.next_offset??null;loaded=true;note.textContent='';more.hidden=offset==null;more.textContent='Show more '+(view==='actions'?'changes':'attempts')+` (${list.children.length} of ${data.pagination?.total??list.children.length} shown)`;}catch(error){if(current()){note.textContent='Saved records could not load: '+error.message;more.hidden=false;more.textContent='Retry saved records';}}finally{busy=false;more.disabled=false;}};
    more.onclick=load;box.ontoggle=()=>{if(box.open&&!loaded)return load();};
  }
  failures(row,turn){
    const project=this.project,turnId=turn.detail?.turn_id||turn.id,epoch=this.viewEpoch,session=this.session;
    const recoveryCurrent=()=>project===this.project&&epoch===this.viewEpoch&&session===this.session&&row.isConnected!==false;
    const failures=turnFailures(turn),count=turn.failure_count??failures.length;if(!count)return;
    const summaryText=failureAttemptSummary(turn,failures);
    const box=make('details','','session-tool-failures');box.append(make('summary',summaryText));
    const render=failure=>{const item=make('article');for(const effect of [failure.sourceEffect,failure.planPublication].filter(Boolean))item.append(make('p',effect.message));item.append(make('p',failure.operation.replaceAll('_',' ')+(failure.target?' · '+failure.target:'')));const detail=make('details');detail.append(make('summary','Error and follow-up'));lazyContent(detail,()=>{detail.append(make('p',failure.error));if(failure.id)detail.append(make('small','Recorded failure '+failure.id));appendSavedRecovery(detail,failure,{project,turnId,isCurrent:recoveryCurrent,onInspect:(read,options)=>this.onOpenOwner?this.onOpenOwner(read,options.label||'Recovery inspection',options):inspectRecoveryRead(read,{request:projectRequest,project,...options})});if(this.onReadTurn&&(turn.detail?.turn_id||turn.id)){const read=make('button','Read failed attempts in this turn');read.type='button';read.onclick=()=>this.guard(()=>this.onReadTurn(turn.detail?.turn_id||turn.id,{focusView:'failures'}));detail.append(read);}const discuss=make('button','Ask Eigen about this failure');discuss.type='button';discuss.onclick=()=>this.compose('Review the recorded '+failure.operation+' failure'+(failure.target?' on '+failure.target:'')+(failure.id?' ('+failure.id+')':'')+'. The recorded error was: '+failure.error+'. Inspect whether later actions addressed it, and continue only work that remains through the existing project tools.');detail.append(discuss);});item.append(detail);return item;};
    if(turn.detail?.turn_id&&turn.failure_count!=null)this.remoteHistory(box,turn,'failures',value=>{const failure=turnFailures({tool_failures:[value]})[0];return render(failure);});else pagedItems(box,failures,render,'attempts');row.append(box);
  }
  facets(row,facets){if(!facets.length||typeof row?.prepend!=='function')return;const chips=chipRow(facets);chips.classList.add('session-turn-chips');chips.setAttribute('data-control','conversation:turn');row.prepend(chips);}
  actions(row,actions,turn={}){const count=turn.action_count??actions.length;if(!count)return;const box=make('details','','session-actions');box.append(make('summary',count+' saved project changes'));
    const render=action=>{const outcome=action.outcome||action;const item=make('div','','session-action');const publication=savedActionPlanPublication(action);if(publication)item.append(make('p',publication.message));item.append(make('strong',action.operation.replaceAll('_',' ')),make('span',String(outcome.status||'Recorded').toLowerCase()));if(outcome.identities?.length)item.append(make('p',outcome.identities.join(', ')));const hasDestination=!!savedActionDestination(action)||!!outcome.views?.length||action.operation==='apply_revision';const inspect=make('button',hasDestination?'Inspect change':'Read saved action');inspect.type='button';inspect.onclick=()=>this.guard(()=>hasDestination?this.onInspect(action):this.onReadTurn?.(turn.detail?.turn_id||turn.id,{focusView:'actions'}));inspect.disabled=!hasDestination&&!this.onReadTurn;item.append(inspect);const detail=make('details');detail.append(make('summary','Receipt'));lazyContent(detail,()=>detail.append(make('pre',JSON.stringify(action,null,2))));item.append(detail);return item;};
    if(turn.detail?.turn_id&&turn.action_count!=null)this.remoteHistory(box,turn,'actions',render);else pagedItems(box,actions,render,'changes');row.append(box);
  }
  proposal(row,turn){
    row.querySelector('.session-proposal-state')?.remove();const state=proposalPresentation(turn);if(!state)return;
    const holder=make('div','','session-proposal-state');holder.append(make('p','Saved proposal provenance · '+state.label,'session-proposal-status'));
    const version=turn.proposal_version||turn.reply?.proposal_carrier?.candidate_version,handle=turn.proposal_read_handle||turn.read_handle;
    const link=make('button',version&&handle?(state.terminal?'Inspect this saved comparison':'Review this saved version'):'Choose a saved version in project Review',state.terminal?'session-inspect-proposal':'session-review-proposal');link.type='button';
    link.onclick=()=>this.guard(()=>this.reviewSavedProposal(turn.proposal_turn_id||turn.id,{proposalVersion:version,readHandle:handle,readOnly:state.terminal}));holder.append(link);row.append(holder);
  }
  compose(text,mode='work'){if(readerSession(this.selectedSessionRecord)){this.status('This text-only reader is one attempt. Prepare a fresh reader or explicitly open an ordinary conversation.',true);return;}if(this.active){this.status('The current turn is active; send a steering message or stop it first.');return;}const separate=mode==='review'||this.role==='review';this.find('[data-mode]').value=mode;if(separate)this.newConversation();else this.rememberMode(mode);this.syncComposerDraft({allowFocused:true});const existing=this.find('[data-message]').value;const composed=!text||existing.includes(text)?existing:existing.trim()?existing+'\n\n'+text:text;this.find('[data-message]').value=composed;this.persistComposerDraft(composed);this.find('[data-message]').focus();this.scope();}
  destroy(){this.surfaceEdge?.disconnect();this.preferencesDisposed=true;this.preferenceOpening=Symbol('disposed');this.preferenceUI?.destroy();this.suspendMessageReading();for(const group of this.messageGroups?.values()||[])for(const reader of group.readers||[])reader.dispose();clearTimeout(this.snapshotTimer);this.snapshotTimer=null;this.viewEpoch=(this.viewEpoch||0)+1;this.streamGeneration=(this.streamGeneration||0)+1;this.stream?.close();this.editorResize?.disconnect();window.removeEventListener('resize',this.updateWidth);this.stopRunningObservation();window.removeEventListener('laplace-workspace-reconnected',this.onReconnect);window.removeEventListener('focus',this.onCatalogueFocus);window.removeEventListener('storage',this.onDraftStorage);}
}
