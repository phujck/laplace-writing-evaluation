// The failed-review context consumer. Session owns draft/view/Send lifecycle;
// this adapter uses those services, the pure action carrier, and existing HTTP owners.
import {encodeComposerDraft,sameComposerIntent,messageTarget} from './workspace-interaction.mjs';
import {workflowActionSummary,workflowActionRead,actionSubmissionDigest,actionSubmissionRead,actionSubmissionReceipt} from './workflow-action-context.mjs';
import {workflowConversationAction,readWorkflowConversationAction,readResearchWorkflowAction} from './workflow-port.mjs';
const make=(tag,text='',cls='')=>{const node=document.createElement(tag);node.textContent=text;node.className=cls;return node;};
export class WorkspaceWorkflowAction {
 constructor(session,request){this.session=session;this.request=request;}
  persistActionDraft() {
    const s=this.session;
    const text=s.find('[data-message]').value,record=encodeComposerDraft(text,s.messageIntent);
    if(s.persistComposerDraft(text))return true;
    // Either existing durable draft backend is sufficient. Keep the ordinary
    // draft warning for the failed backup; never gate legacy conversations.
    for(const read of [()=>s.composerStorage?.getItem(s.composerStorageKey),()=>localStorage.getItem(s.composerBackupKey())])try{if(read()===record)return true;}catch{}
    return false;
  }
  setBusy(){const s=this.session;for(const button of s.find('[data-selected-action]')?.querySelectorAll?.('[data-action-submission]')||[])button.disabled=!!s.submitting||!!s.initializing||!!s.loadingSession;}
  paintSelectedAction(){
    const s=this.session;
    const host=s.find('[data-selected-action]');if(!host?.replaceChildren)return;host.replaceChildren();
    const leaf=s.authoredContext().workflow_action;if(!leaf)return;
    const summary=s.messageIntent?.action_summary,id=leaf.reference.identity,pending=s.messageIntent?.submission;
    const research=leaf.reference.kind==='research-workflow-start';
    host.append(make('strong',research?'Research workflow · '+(summary?.workflow_title||'Saved workflow'):'Review continuation · '+(summary?.step_title||id.step_id)),make('p',(summary?.workflow_title||'Saved workflow')+' · original conversation '+id.parent_session_id,'session-help'));
    if(summary?.outputs?.length)host.append(make('p','Reuses: '+summary.outputs.join(', '),'session-help'));
    const version=make('p',research?'Saved workflow · '+(summary?.input_policy||'Input policy not reported')+' · '+(summary?.policy?.max_iterations??'Unreported')+' maximum iterations · human manuscript Apply':('Saved version '+leaf.reference.version.definition_revision.slice(7,19)+'… · '+(summary?.budget?.max_child_launches??'Unreported')+' judge attempt'+(summary?.budget?.deadline_at||summary?.budget?.deadline_seconds?' · original deadline retained':' · no plan deadline')),'session-help');version.title=leaf.reference.version.definition_revision;host.append(version);
    host.append(make('p','Last inspected action. Its current basis is checked when you Send.','session-help'));
    const details=make('button','Inspect selected action');details.type='button';details.onclick=()=>s.openInspector('context');host.append(details);
    if(pending){host.append(make('p',pending.observation==='NONE'?'No matching turn was recorded at the last check. Retry keeps the exact submitted request.':pending.ack?'Parent turn acknowledged; inspect its exact submission receipt.':'Submission outcome unresolved. The exact request and original text are retained.','session-help'));
      const check=make('button','Check submission');check.type='button';check.dataset.actionSubmission='';check.disabled=!!s.submitting;check.onclick=()=>s.guard(()=>s.reconcileActionSubmission());host.append(check);
      if(pending.observation==='NONE'&&!pending.ack){const retry=make('button','Retry this submission');retry.type='button';retry.dataset.actionSubmission='';retry.disabled=!!s.submitting;retry.onclick=()=>s.guard(()=>s.retryActionSubmission());host.append(retry);}
    }
  }
  paintActionInspector(detail){
    const s=this.session;
    const leaf=s.authoredContext().workflow_action;detail.append(make('p','The short message is your request. This selected action supplies its exact owner context; ordinary tool admission still applies.'));
    const identities=make('details');identities.append(make('summary','Saved version and action basis'));const text=make('pre',JSON.stringify(leaf,null,2));text.style.whiteSpace='pre-wrap';text.style.overflowWrap='anywhere';identities.append(text);detail.append(identities);
    const policy=s.messageIntent?.action_summary?.policy;if(policy)detail.append(make('p','Saved policy: at most '+policy.max_iterations+' iterations; '+policy.runtime_seconds+' seconds per admitted step. Apply remains a separate human decision.'));
    const budget=s.messageIntent?.action_summary?.budget;if(budget)detail.append(make('p','Budget: '+budget.max_child_launches+' existing judge attempt; '+(budget.deadline_at?'original deadline '+new Date(budget.deadline_at*1000).toLocaleString():budget.deadline_seconds?'original '+budget.deadline_seconds+' second deadline':'no plan deadline recorded')));
    const inspect=make('button','Read exact selected action');inspect.type='button';inspect.onclick=()=>s.guard(()=>s.inspectWorkflowAction());detail.append(inspect);
    if(s.workflowActionIssue&&sameComposerIntent(s.workflowActionIssueBasis,leaf)){detail.append(make('p','The selected context changed or is unavailable. Your message and selected reference are retained.','error'));const next=(s.workflowActionIssue.refused?.next_reads||s.workflowActionIssue.next_reads||[]).find(r=>r.request?.facet==='app-continue-compose'||leaf.reference.kind==='research-workflow-start'&&r.request?.action==='workflow-compose-start');if(next){const fresh=make('button','Inspect changed proposal');fresh.type='button';fresh.onclick=()=>s.guard(()=>s.inspectWorkflowAction(leaf.reference.kind==='research-workflow-start'?next:next.request,{proposal:true}));detail.append(fresh);}else if(s.workflowActionIssue.code==='CHANGED_INPUT'){
    detail.append(make('p','The explicit Work basis changed. Read the selected action to inspect its owner reinspection route.','session-help'));}}
    const proposal=s.workflowActionProposal&&sameComposerIntent(s.workflowActionProposalBasis,leaf)?s.workflowActionProposal:null;
    const exact=s.workflowActionDetail&&sameComposerIntent(s.workflowActionDetail.payload?.workspace_context?.workflow_action,leaf)?s.workflowActionDetail:null;
    const value=proposal||exact;
    if(value){const raw=make('pre',JSON.stringify(value.action_context,null,2));raw.style.whiteSpace='pre-wrap';raw.style.overflowWrap='anywhere';detail.append(raw);if(proposal){const use=make('button','Use inspected action');use.type='button';use.onclick=()=>s.guard(()=>s.useInspectedWorkflowAction());detail.append(use);}}
  }
  async inspectWorkflowAction(request=null,{proposal=false}={}){
    const s=this.session;
    const leaf=structuredClone(s.authoredContext().workflow_action),epoch=s.viewEpoch,session=s.session;
    const current=()=>epoch===s.viewEpoch&&session===s.session&&sameComposerIntent(s.authoredContext().workflow_action,leaf);
    try{const action=leaf.reference.kind==='research-workflow-start'?await readResearchWorkflowAction(s.project,request||s.messageIntent?.action_read,this.request,{allowInspectedBasis:proposal}):await readWorkflowConversationAction(s.project,request||workflowActionRead(leaf),this.request,{allowInspectedBasis:proposal});if(!current())return;
      if(proposal){s.workflowActionProposal=action;s.workflowActionProposalBasis=leaf;}else s.workflowActionDetail=action;
      s.workflowActionIssue=null;s.paintContext();
    }catch(error){if(current()){s.workflowActionIssue=error.result||{};s.workflowActionIssueBasis=leaf;s.paintContext();}throw error;}
  }
  useInspectedWorkflowAction(){
    const s=this.session;
    if(s.messageIntent?.submission)throw Error('Reconcile the retained submission before choosing another action.');
    const action=workflowConversationAction(s.workflowActionProposal,s.project),p=action.payload,old=s.authoredContext().workflow_action;
    if(s.active||!sameComposerIntent(s.workflowActionProposalBasis,old)||p.session_id!==s.session||!sameComposerIntent(old.reference,p.workspace_context.workflow_action.reference))throw Error('The proposal belongs to a different original action or conversation.');
    s.messageIntent={...s.messageIntent,context:{...messageTarget({...p.workspace_context,label:action.work_target.title},action.work_target)},action_summary:workflowActionSummary(action.action_context),action_read:structuredClone(action.action_context.read||action.read)};
    s.intentRevision=(s.intentRevision||0)+1;s.workflowActionProposal=null;s.workflowActionIssue=null;s.workflowActionDetail=action;s.persistComposerDraft(s.find('[data-message]').value);s.scope();s.status('Inspected action selected. Your message is unchanged; Send remains explicit.');
  }
  async submitActionPayload(payload,draft){
    const s=this.session;
    const wire=JSON.parse(JSON.stringify(payload)),pending={payload:wire,intent_sha256:await actionSubmissionDigest(wire),draft_text:draft.submittedDraft,draft_intent:structuredClone(draft.submittedIntent),observation:'UNKNOWN'};
    if(s.session!==wire.session_id||s.project!==wire.project||!sameComposerIntent(s.messageIntent,draft.submittedIntent)||(s.intentRevision||0)!==draft.intentRevision)throw Error('The retained message changed before submission. Nothing was sent.');
    s.messageIntent={...s.messageIntent,submission:pending};
    if(!s.persistActionDraft())throw Error('The submission identity could not be stored in either draft backend. Nothing was sent; keep this page open to recover the draft.');
    await s.postActionSubmission(pending);
  }
  async postActionSubmission(pending){
    const s=this.session;
    if(await actionSubmissionDigest(pending.payload)!==pending.intent_sha256)throw Error('The retained submission intent is damaged. Keep the draft; no request was sent.');
    pending.observation='UNKNOWN';if(!s.persistActionDraft())throw Error('The exact submission could not be preserved. Nothing was sent.');
    try{const result=await this.request('/authoring/turn',pending.payload),meta=result.action_submission;
      if(result.session_id!==pending.payload.session_id||typeof result.turn_id!=='string'||meta?.request_id!==pending.payload.request_id||meta.intent_sha256!==pending.intent_sha256||meta.read?.http?.method!=='GET'||meta.read.http.url!==actionSubmissionRead(pending))throw Error('Submission acknowledgement did not match the retained intent. Check its exact receipt.');
      pending.ack={turn_id:result.turn_id};if(s.messageIntent?.submission===pending)s.persistActionDraft();await s.reconcileActionSubmission();
    }catch(error){const body=error.result||{},refused=body.refused;
      const known=['ACTION_CONTEXT_CHANGED','ACTION_CONTEXT_UNAVAILABLE','ACTION_WORK_BASIS_CHANGED'].includes(refused?.code)||body.code==='CHANGED_INPUT'&&body.project===pending.payload.project&&body.work_id===pending.payload.work_id&&['expected_work_scope_revision','expected_dependency_revision'].includes(body.field)&&Array.isArray(body.next_reads);
      if(s.messageIntent?.submission===pending){if(known){delete s.messageIntent.submission;s.workflowActionIssue=body;s.workflowActionIssueBasis=pending.payload.workspace_context.workflow_action;s.persistComposerDraft(s.find('[data-message]').value);s.scope();}else{pending.observation='UNKNOWN';s.persistActionDraft();s.scope();}}
      throw error;
    }
  }
  async retryActionSubmission(){
    const s=this.session;
    const pending=s.messageIntent?.submission;if(!pending||pending.observation!=='NONE'||pending.ack)throw Error('Check the exact submission before retrying it.');
    if(s.submitting)return;s.submitting=true;s.setBusy(true);try{await s.postActionSubmission(pending);}finally{s.submitting=false;s.setBusy(!!s.active);s.scope();}
  }
  async reconcileActionSubmission(){
    const s=this.session;
    const pending=s.messageIntent?.submission;if(!pending)return;
    if(s.project!==pending.payload.project||s.session!==pending.payload.session_id||await actionSubmissionDigest(pending.payload)!==pending.intent_sha256)throw Error('The retained submission belongs to another intent or conversation.');
    let result,receipt;try{result=await this.request(actionSubmissionRead(pending));receipt=actionSubmissionReceipt(result,pending);}catch(error){if(s.messageIntent?.submission===pending){pending.observation='UNKNOWN';s.persistActionDraft();s.scope();}throw error;}
    if(s.messageIntent?.submission!==pending||s.session!==pending.payload.session_id)return;
    if(!receipt){if(pending.ack)throw Error('A known acknowledgement is not present in this lookup. Keep the original receipt and check again.');pending.observation='NONE';s.persistActionDraft();s.scope();s.status('No matching turn recorded at this read. Retry this submission sends only the original intent and request identity.');return;}
    if(pending.ack&&pending.ack.turn_id!==receipt.turn_id)throw Error('The exact request lookup returned another turn.');
    delete s.messageIntent.submission;s.persistComposerDraft(s.find('[data-message]').value);
    const unchanged=sameComposerIntent(s.messageIntent,pending.draft_intent);
    if(unchanged)s.clearSentDraft(pending.draft_text,{intentRevision:s.intentRevision||0,submittedIntent:s.messageIntent});
    s.scope();s.status('Submission recorded as '+receipt.turn_id+'. No request was resent.');
    await s.loadSession();return receipt;
  }
}
