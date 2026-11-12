// Reading of actual Work workflow facts. Owners issue every effect/read handle;
// this view neither advances a run nor infers a verdict from response wording.
import {el,button,details,textBody,actionRows,settingsFacts} from './research-workbench-view.mjs';
import {mountWorkflowRunStop} from './workspace-workflow-operation.mjs';
const states={PREPARED:'Ready to choose recipients',RUNNING:'Work is running',STOP_BEFORE_NEXT:'Paused before the next step',AWAITING_ADVANCE:'Ready for your next-step decision',AWAITING_HUMAN_APPLY:'Ready for human manuscript review',NEEDS_REVISION:'Revision requested',LIMIT_REACHED:'Iteration limit reached',PARTIAL:'Some work needs recovery',APPLIED:'Manuscript application recorded'};
const deliveryStates={SUBMITTED:'Delivery needs inspection',RESERVED:'Preparing recipient',ADMITTED:'Step admitted',RESULT:'Response received',STALE:'Current inputs no longer match',UNCONFIRMED:'Delivery not confirmed',UNSUPPORTED:'Unsupported delivery'};
const effects={'proposal-writer':'Proposal writer','independent-review':'Independent reviewer','research-producer':'Research producer'};
export function runActions(value){return Array.isArray(value)?value:Object.entries(value||{}).map(([id,row])=>({...row,id:row.id||id}));}
export function renderWorkflowRun(host,value,{onAction=()=>{},onRead=()=>{},onObject=()=>{},isCurrent=()=>true,request=null,onStopped=()=>{},stopRecovery=null}={}){
  if(value?.schema_version!=='laplace.research-workflow-run/1'){host.append(el('p','The Work owner has not returned a compatible workflow run.','rw-qualification'));return false;}
  const head=el('header');head.append(el('h3',value.work?.title||'Research workflow'),el('p',states[value.state]||value.state||'Standing not reported','rw-standing'));
  if(value.iteration!==undefined)head.append(el('p','Iteration '+value.iteration+(value.policy?.max_iterations?' of '+value.policy.max_iterations:'')));
  if(value.reason)textBody(head,value.reason,'rw-alert');if(value.qualification)textBody(head,value.qualification,'rw-qualification');host.append(head);
  // Stop and original-parent synthesis are never generic action rows: the guarded
  // shared control sends Stop, and synthesis publication has no app button (its standing is in the synthesis card).
  const invoke=action=>onAction(action.id==='human_apply'?{...action,reconcile:value.read,run_work_id:value.work.id}:action),actions=runActions(value.actions).filter(action=>action.id!=='stop-run'&&action.id!=='synthesis'),applied=value.state==='APPLIED';if(!applied)actionRows(host,actions.filter(action=>action.permitted===true),{onAction:invoke,isCurrent});
  if(!applied)paintStop(host,value,{request,isCurrent,onStopped,stopRecovery});
  const unavailable=actions.filter(action=>action.permitted!==true);if(unavailable.length&&!applied){const more=el('details');more.append(el('summary','Other run controls'));actionRows(more,unavailable,{onAction:invoke,isCurrent});host.append(more);}
  if(value.judgement){const judged=el('section','','rw-card');judged.append(el('h4','Recorded independent review'),el('p',value.judgement.verdict||'Verdict not reported','rw-standing'));for(const finding of value.judgement.findings||[])textBody(judged,typeof finding==='string'?finding:finding.summary||finding.reason||'');if(value.judgement.phase_read)judged.append(button('Inspect recorded review',()=>{if(isCurrent())onRead(value.judgement.phase_read,'Recorded independent review');}));judged.append(el('p','This is the scoped reviewer judgement. Manuscript application and author acceptance remain separate.','rw-qualification'));host.append(judged);}
  if(value.input_packet){const packet=el('section','','rw-card');packet.append(el('h4','Evidence supplied to this run'));
    const facts=value.input_packet;for(const key of ['qualification','input_policy','label'])if(facts[key])textBody(packet,facts[key],'rw-qualification');
    if(facts.read)packet.append(button('Inspect exact evidence packet',()=>{if(isCurrent())onRead(facts.read,'Evidence supplied to the run');}));
    packet.append(details('Packet identity and consumed bases',facts,{isCurrent}));host.append(packet);}
  synthesisCard(host,value.synthesis);
  const attempts=el('section');attempts.append(el('h4','Actual steps and responses'),el('p','Each step shows what it actually received: its review input and consumed bases, and the prepared, admitted and sent settings. Declared context counts only where a step records it as delivered. Grouping passes on declared settings and chosen context, never a conversation or permissions.','rw-qualification'));
  for(const attempt of value.attempts||[]){const card=el('article','','rw-card'),binding=attempt.binding||{},name=binding.label||binding.title||effects[attempt.effect]||attempt.effect||'Recipient';card.append(el('h5',name));
    const purpose=effects[attempt.effect]||attempt.effect;if(purpose)card.append(el('p',purpose+(attempt.iteration!==undefined?' · iteration '+attempt.iteration:'')));
    if(attempt.state)card.append(el('p',deliveryStates[attempt.state]||String(attempt.state).replaceAll('_',' '),'rw-standing'));
    if(attempt.input_policy)card.append(el('p','Review input: '+attempt.input_policy+(attempt.input_policy==='evidence-packet'?' · the reviewer is informed by the selected evidence packet.':''),'rw-qualification'));
    if(attempt.error)textBody(card,attempt.error,'rw-alert');if(attempt.verdict)card.append(el('p','Recorded verdict: '+attempt.verdict));
    for(const [key,label]of [['public_reply_read','Read complete response'],['result_read','Inspect result'],['proposal_read','Inspect proposal'],['turn_read','Inspect exact turn']])if(attempt[key])card.append(button(label,()=>{if(isCurrent())onRead(attempt[key],label);}));
    if(attempt.conversation?.public_content_read)card.append(button('Inspect exact saved turn',()=>{if(isCurrent())onRead(attempt.conversation.public_content_read,'Saved recipient turn');}));
    if(attempt.settings){const d=el('details');d.append(el('summary','Settings consumed by this step'));if(attempt.settings.prepared)d.append(el('p','Prepared provider/model/effort: '+['provider','model','effort'].map(key=>attempt.settings.prepared.values?.[key]??attempt.settings.prepared[key]?.value??attempt.settings.prepared[key]).filter(value=>typeof value==='string').join(' · ')));if(attempt.settings.sent_observation)textBody(d,attempt.settings.sent_observation,'rw-qualification');d.append(details('Prepared, admitted and actual sent settings',attempt.settings,{isCurrent}));card.append(d);}
    card.append(details('Captured approval, execution and input basis',attempt,{isCurrent}));attempts.append(card);
  }
  if(!(value.attempts||[]).length)attempts.append(el('p','No step admission is recorded in this run.','rw-qualification'));host.append(attempts);
  if(value.interventions?.length){const section=el('section');section.append(el('h4','Interventions and consequences'));for(const row of value.interventions){const card=el('article','','rw-card');card.append(el('h5',row.title||row.label||'Recorded intervention'));if(row.summary)textBody(card,row.summary);if(row.concern?.label)textBody(card,row.concern.label);if(row.read)card.append(button('Inspect intervention',()=>{if(isCurrent())onRead(row.read,'Recorded intervention');}));if(row.reference&&row.object_read)card.append(button('Open affected object',()=>{if(isCurrent())onObject({reference:row.reference,read:row.object_read});}));card.append(details('Exact disposition and owner receipt',row,{isCurrent}));section.append(card);}host.append(section);}
  if(value.state==='AWAITING_HUMAN_APPLY')host.append(el('p','Inspect the proposal and its review before choosing the existing manuscript Apply action. Workflow acceptance does not apply source changes.','rw-qualification'));
  if(applied&&actions.length){const future=el('details');future.append(el('summary','Future changes and recovery'),el('p','The application above is already recorded. These are the owner’s still-offered future approval, plan and recovery controls; opening them starts no action.','rw-qualification'));actionRows(future,actions,{onAction:invoke,isCurrent});host.append(future);}
  host.append(el('p','Recorded uses and the observed flow of the saved workflow version are read in Use a workflow, Runs, from the owner’s offers there. This run view carries no flow read, so none is shown here, and nothing is converted between run kinds.','rw-qualification'));
  host.append(details('Consumed definition, policy and exact run facts',value,{isCurrent}));return true;
}
function paintStop(host,value,{request,isCurrent,onStopped,stopRecovery}){
  const card=el('section','','rw-card');card.dataset.rwRunStop='';host.append(card);
  if(typeof request!=='function'){card.append(el('h4','Stop this run'),el('p','Stop is unavailable in this reading because no owner transport was supplied. Refresh this run.','rw-qualification'));return null;}
  return mountWorkflowRunStop(card,{view:value,request,isCurrent,onSettled:onStopped,recovery:stopRecovery});
}
function synthesisCard(host,synthesis){
  if(!synthesis?.required)return;const card=el('section','','rw-card');card.dataset.rwSynthesis='';card.append(el('h4','Original-parent synthesis'));
  const pick=row=>row&&typeof row==='object'?['provider','model','effort'].map(key=>row[key]?.value??row.values?.[key]??row[key]).filter(item=>typeof item==='string').join(' · '):'';
  card.append(el('p','Written in the original parent conversation'+(synthesis.session_id?' ('+synthesis.session_id+')':'')+' with that conversation’s admitted settings and authority. It is not a separate child or executor.'));
  const admitted=pick(synthesis.admitted_settings),declared=pick(synthesis.declared_settings);if(admitted)card.append(el('p','Admitted settings: '+admitted));if(declared)card.append(el('p','Declared on the step: '+declared+'. The owner refuses publication if the publishing parent turn no longer has a declared value.','rw-qualification'));
  card.append(el('p',synthesis.published?'Published once by the original parent. The publication is retained.':synthesis.due?'Due: every step is settled. Publication first reads each required input completely.':'Not yet due'+(synthesis.pending_children?.length?': '+synthesis.pending_children.length+' step(s) still unsettled.':'.'),'rw-standing'));
  if(Number.isSafeInteger(synthesis.inputs_total))card.append(el('p',synthesis.inputs_total+' required input(s) must be read completely before publication. Read coverage is not acceptance. Publication is the original parent’s own action and has no button here.','rw-qualification'));
  if(synthesis.bridge_problem)textBody(card,synthesis.bridge_problem,'rw-alert');host.append(card);
}
