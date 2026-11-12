// One comment's finite review route. Owners issue policy/recipient/action/result facts;
// this leaf presents them in the existing inspector and retains only local reader intent.
import {feedbackHTTP,feedbackRevisionSummary,feedbackBuildFreshness} from './feedback-route-port.mjs';
import {sharedInspector} from './workspace-inspector.mjs';
import {createLifetime} from './selected-lifetime.mjs';
import {createMessageReading,messageReadURL} from './conversation-reading.mjs';
import {openSavedTurn} from './workspace-material.mjs';
import {admitWorkReviewRecord,renderWorkReviewPhaseRows} from './workspace-work-review.mjs';
import {proposalDecisionOutcome} from './workspace-bridge.mjs';
import {pendingRead} from './pending-read.mjs';
import {declareControl} from './workspace-presentation.mjs';
const el=(tag,text='',cls='')=>{const node=document.createElement(tag);node.textContent=text;node.className=cls;return node;};
const copy=value=>JSON.parse(JSON.stringify(value));
export function deliveryRead(project,payload){return '/work/delivery?'+new URLSearchParams({project,request:JSON.stringify(payload)});}
function styles(){if(document.querySelector('[data-feedback-route-style]'))return;const link=el('link');link.rel='stylesheet';link.href='/shared/feedback-route.css';link.dataset.feedbackRouteStyle='true';document.head.append(link);}
const reopenResponses=(args,readerPlace)=>openFeedbackResponses({...args,readerPlace});
export async function openFeedbackResponses(options){
 // openProposal is the canonical project Review controller (workspace-review createProjectReview.open -> workspace-proposals
 // mountProposalReview): drafts, permission, decision and Apply stay that owner's. Without it this view only inspects.
 // onDecisionOpened releases the exact initiating parent (a passage comment dialog) only after an actual opening.
 const {project,origin,workId,read=null,request,isCurrent=()=>true,onOpen=null,readerPlace=null,openProposal=null,onDecisionOpened=null}=options;
 if(!isCurrent())return;styles();const inspector=sharedInspector(),life=createLifetime(),dialog=el('dialog','','workspace-dialog feedback-route-reader');dialog.setAttribute('aria-label','Review responses');dialog.dataset.guidePanel='responses';let token=null,aggregate=null,busy=false,historical=false,snapshot=null,returnPlace=readerPlace,returnFocus=null,focusVersion=0,reviewContext=null,contextOpening=false;
 dialog.addEventListener?.('focusin',()=>{focusVersion++;});
 const current=()=>!life.disposed&&isCurrent()&&dialog.isConnected!==false,lineage=()=>isCurrent()&&inspector.lineage(token)();
 const heading=el('h2','Review responses'),close=el('button','Close review responses'),notice=el('p','','feedback-route-status'),comment=el('blockquote'),sourceQuote=el('blockquote'),contextHost=el('section'),content=el('section');comment.setAttribute('aria-label','Saved comment');sourceQuote.setAttribute('aria-label','Selected source passage');sourceQuote.hidden=true;notice.setAttribute('role','status');close.type='button';close.onclick=()=>dialog.close();dialog.append(heading,close,sourceQuote,comment,contextHost,notice,content);document.body.append(dialog);
 dialog.onclose=()=>{life.dispose();reviewContext?.destroy();dialog.remove();};token=inspector.adopt(dialog,{kind:'feedback-responses',title:'Review responses',reopen:{factory:reopenResponses,args:{project,origin,workId,read,request,openProposal}}}).token;onOpen?.(dialog);dialog.showModal();close.focus();
 const button=(label,fn)=>{const node=el('button',label);node.type='button';node.dataset.feedbackControl=label;node.onclick=async()=>{if(busy||!current())return;returnPlace={scrollTop:dialog.scrollTop,edge:node.dataset.feedbackEdge||null,control:label};inspector.pin(token,{snapshot,...returnPlace});returnFocus={node,version:focusVersion};busy=true;node.disabled=true;try{await fn();}catch(error){if(current()){notice.textContent=error.message+' Previously read responses are retained.';notice.className='error';}}finally{busy=false;node.disabled=false;}};return node;};
 const ownerRead=(handle,label)=>openFeedbackWorkReview({project,workId,handle,label,request,isCurrent:lineage});
 async function observe(handle=aggregate?.read||read){
  const path=handle?feedbackHTTP(handle,{project,paths:['/work/delivery']}):deliveryRead(project,{action:'route-status',work_id:workId,origin}),lease=life.lease(),value=await request(path);
  if(!lease()||!current())return;
  const next=value.aggregate||value;
  if(next.schema_version!=='laplace.feedback-route/1'||next.project!==project||next.work?.id!==workId||!sameFeedbackValue(next.origin?.origin_ref,origin))throw Error('The feedback owner returned another comment or Work.');
  for(const edge of next.edges||[])if(edge.public_reply_read){const target=edge.public_reply_read.identity,admitted=edge.event?.admitted;if(target?.project!==project||target.session_id!==admitted?.session_id||target.turn_id!==admitted?.turn_id||target.part!=='reply')throw Error('The response read does not match its recipient admitted turn.');messageReadURL(edge.public_reply_read,target);}
  for(const edge of next.edges||[])feedbackRevisionSummary(edge.revision,{project,turnId:edge.event?.admitted?.turn_id||null});
  aggregate=next;historical=false;const version='browser-observation:'+crypto.randomUUID();snapshot=inspector.remember(path,{version,aggregate:next})?{url:path,cut:version}:null;paint();return next;
 }
 async function effect(action){
  const payload=action?.payload;if(historical||!action?.permitted||payload?.work_id!==workId||payload?.route_id!==aggregate.route_id)throw Error(action?.reason||'Reinspect this route before changing it.');
  const lease=life.lease();await request(feedbackHTTP(action,{project,method:'POST',paths:['/work/delivery']}),{...copy(payload),project});if(lease()&&current())await observe();
 }
 async function showContext(saved=null){
  if(contextOpening||reviewContext||!aggregate?.review_context)return;contextOpening=true;const observed=aggregate,intended=focusVersion;
  try{const {mountFeedbackReviewContext}=await import('./feedback-review-context.mjs');if(!current()||aggregate!==observed)return;const initial=saved?.presentation||(saved&&inspector.snapshot(saved.url,saved.cut)?.value?.context);
   reviewContext=mountFeedbackReviewContext(contextHost,{project,workId,origin,capability:observed.review_context,request,isCurrent:current,initial,onRead:async row=>{
    if(!lineage())return;const captured=reviewContext.capture(),url=captured.read?.http?.url,cut='review-context:'+crypto.randomUUID(),cached=url&&inspector.remember(url,{version:cut,context:captured}),{value:discardedPage,history:discardedTimeline,...presentation}=captured;inspector.pin(token,{snapshot,scrollTop:dialog.scrollTop,reviewContextSnapshot:cached?{url,cut}:{presentation}});
    if(row.adapter?.kind==='work-review-phase')return openFeedbackWorkReview({project:row.adapter.project,workId:row.adapter.work_id,handle:row.detail_read,label:row.title||'Recorded review phase',request,isCurrent:lineage});
    if(row.coordinate?.kind==='delivery-event'){const {openResearchDelivery}=await import('./research-workbench-readers.mjs');if(lineage())return openResearchDelivery({project:row.reference.identity.namespace,workId:row.reference.identity.id,eventId:row.coordinate.id,handle:row.detail_read,title:row.title,request,isCurrent:lineage});}
   }});for(const node of [...contextHost.children])if(node!==reviewContext.element)node.remove();await reviewContext.open();if(initial&&current()&&focusVersion===intended&&(document.activeElement===close||document.activeElement===document.body))reviewContext.restoreFocus();
  }finally{contextOpening=false;}
 }
 function paint(){
  const active=document.activeElement,ownsFocus=!returnFocus||(returnFocus.version===focusVersion&&(active===returnFocus.node||active===document.body||active?.isConnected===false)),place=(ownsFocus&&returnPlace)||{scrollTop:dialog.scrollTop,edge:active?.dataset?.feedbackEdge,control:active?.dataset?.feedbackControl};returnPlace=null;returnFocus=null;content.replaceChildren();notice.className='feedback-route-status';
  comment.textContent=aggregate.origin.correction?.text||'';
  // the comment's own recorded disposition (correction status/status_history) and passage currentness, as the owner reports them
  {const correction=aggregate.origin.correction||{},changes=Array.isArray(correction.status_history)?correction.status_history.length:0,passage=aggregate.origin.currentness?.state;
   const standing=el('p','Comment status: '+String(correction.status||'not reported').replaceAll('_',' ')+(changes?' · '+changes+' recorded status change'+(changes===1?'':'s'):'')+(passage?' · passage '+String(passage).toLowerCase().replaceAll('_',' '):'')+(correction.status_note?'. '+correction.status_note:'')+'. A status records your disposition of the comment; it is not acceptance of any revision.','muted feedback-comment-status');
   content.append(standing);}
  sourceQuote.textContent=aggregate.origin.correction?.anchor?.quote||'';sourceQuote.hidden=!sourceQuote.textContent;
  const cap=aggregate.review_context;if(cap){if(cap.association?.route_id!==aggregate.route_id)throw Error('The review context belongs to another recorded route.');if(reviewContext)reviewContext.update(cap);else if(!contextHost.children.length)contextHost.append(button('Show review context',()=>showContext()));}

  const edges=aggregate.edges||[],received=edges.filter(edge=>edge.event?.result?.available).length,unconfirmed=edges.filter(edge=>!edge.event?.admitted&&!edge.event?.result?.available&&['SUBMITTED','UNCONFIRMED','DELIVERING'].includes(edge.event?.state)).length;
  notice.textContent=(historical?'Previously inspected · refresh for current status. ':'')+received+' response'+(received===1?'':'s')+' received'+(unconfirmed?' · '+unconfirmed+' start'+(unconfirmed===1?'':'s')+' unconfirmed':'')+'.';
  content.append(el('p','Project-context review','muted'));
  const allowance=aggregate.allowance||{},limits=aggregate.policy?.limits||{};
  const refresh=button('Refresh review responses',()=>observe());content.append(refresh);
  for(const edge of aggregate.edges||[]){const row=el('article','','feedback-route-edge'),recipient=edge.recipient||{},event=edge.event||{};row.dataset.feedbackEdge=edge.edge_id;
   const focus=edge.obligation||{},authored=focus.state==='AUTHORED_SNAPSHOT'&&focus.label&&focus.id===edge.obligation_id,purpose=authored?String(focus.label)+(focus.scope?' · '+String(focus.scope).replaceAll('_',' ').replaceAll('-',' '):''):'the recorded question of this request · inspect handed inputs; the current Work question is not substituted';
   const focusDetail=el('details','','feedback-focus-identity');focusDetail.append(el('summary','Review focus identity'),el('p','Obligation '+String(edge.obligation_id||'not reported')+(authored?' · authored when this review was requested':' · '+String(focus.state||'not reported').toLowerCase().replaceAll('_',' ')),'muted'));
   row.append(el('h3',recipient.label||recipient.id||'Reviewer'),el('p','Review focus: '+purpose),focusDetail);
   const progress=event.result?.available?'Response received.':event.admitted?'Review started; waiting for its response.':['SUBMITTED','UNCONFIRMED','DELIVERING'].includes(event.state)?'Start unconfirmed.':event.state==='CANCELLED'?'Review stopped.':event.state==='EXPIRED'?'Time allowed to start this review has expired.':event.state==='STALE'?'Review inputs or settings changed; inspect before requesting more work.':event.state==='UNSUPPORTED'?'The selected review setup is unavailable.':'Waiting for a confirmed review start.';
   row.append(el('p',progress));
   const a=event.acceptance;
   if(a?.status==='AWAITING_REVIEW')row.append(el('p','Awaiting a recorded verdict.','muted'));
   else if(a?.status){const verdict=String(a.status).toLowerCase().replaceAll('_',' ');row.append(el('p',a.by_this_delivery&&a.currentness==='CURRENT'?'Current verdict: '+verdict+'.':a.by_this_delivery?'Earlier verdict: '+verdict+'; inspect its current standing.':'A different review recorded '+verdict+'; inspect its current standing.','muted'));}
   const result=event.result;if(result?.available){row.append(el('h4','Response preview'),el('p',result.text||''),el('p',result.complete===true?'Public response is available.':'Preview only · open the complete response.','muted'));}
   const actions=el('div','','feedback-route-actions');
   if(edge.public_reply_read){const b=button('Read complete response',()=>openFeedbackReply({project,handle:edge.public_reply_read,request,isCurrent:lineage}));b.dataset.feedbackEdge=edge.edge_id;actions.append(b);}
   if(edge.turn_read)actions.append(button('Inspect saved review turn',async()=>{const url=new URL(feedbackHTTP(edge.turn_read,{project,paths:['/authoring/session-turn']}),'http://local');return openSavedTurn({project,turnId:url.searchParams.get('id'),ownerRead:edge.turn_read,request,isCurrent:lineage});}));
   if(edge.review_read)actions.append(button('Inspect recorded verdict',()=>ownerRead(edge.review_read,'Recorded review verdict')));
   if(edge.handoff_read)actions.append(button('Inspect handed inputs',()=>ownerRead(edge.handoff_read,'Review handed inputs')));
   for(const node of actions.querySelectorAll('button'))node.dataset.feedbackEdge=edge.edge_id;row.append(actions);
   // the owner revision join: proposal -> application/source effect -> matching build, each an exact owner read
   const chain=feedbackRevisionSummary(edge.revision,{project,turnId:event.admitted?.turn_id||null});
   if(chain){const box=el('section','','feedback-revision-chain');box.dataset.revisionState=chain.state;box.append(el('h4','Revision chain'));
    for(const line of chain.lines)box.append(el('p',line,'muted'));
    for(const link of chain.links){const anchor=el('a',link.label);anchor.href=link.url;anchor.dataset.revisionLink=link.kind;anchor.dataset.feedbackEdge=edge.edge_id;box.append(anchor);}
    for(const item of chain.inspect||[]){const inspectButton=button(item.label,async()=>{const preview=await request('/authoring/proposal-preview?'+new URLSearchParams({project,turn_id:item.turnId,proposal_version:item.version}));if(!lineage())return;if(preview?.proposal_version!==undefined&&preview.proposal_version!==item.version)throw Error('The proposal owner returned another version; nothing was shown.');if(!globalThis.walk?.showProposal)throw Error('Open Writing to inspect this proposal in the manuscript.');globalThis.walk.showProposal(preview,{readOnly:true});});inspectButton.dataset.revisionInspect=item.version;inspectButton.dataset.feedbackEdge=edge.edge_id;box.append(inspectButton);
     // review F5: the same exact version opened in the manuscript's existing proposal decision view; the apply decision and its guards stay that owner's
     const decide=button('Review '+item.version.slice(7,19)+' to apply in the manuscript',async()=>{const preview=await request('/authoring/proposal-preview?'+new URLSearchParams({project,turn_id:item.turnId,proposal_version:item.version}));if(!lineage())return;if(preview?.proposal_version!==undefined&&preview.proposal_version!==item.version)throw Error('The proposal owner returned another version; nothing was shown.');if(typeof openProposal!=='function')throw Error('This response view cannot decide proposals. Open Review responses from project Review in Writing, where the manuscript proposal decision owns drafts, permission and Apply.');const checked=proposalDecisionOutcome(await openProposal(item.turnId,{proposalVersion:item.version,readHandle:item.read,readOnly:false,decision:true}),{project,turnId:item.turnId,proposalVersion:item.version});if(!checked.ok)throw Error(checked.error+' This response view stays open.');/* Leave THIS inspection for the already accepted decision view through the shared inspector's explicit destination
       (closeTo): it clears the trail instead of running Back, so a parked passage comment is not reopened over the decision.
       Ordinary close remains only for a dialog that is no longer the current inspection. */if(!life.disposed&&!inspector.closeTo(token,()=>{}))dialog.close();onDecisionOpened?.(checked.outcome);});decide.dataset.revisionDecide=item.version;decide.dataset.feedbackEdge=edge.edge_id;box.append(decide);}
    for(const item of chain.builds||[]){const facts=el('div','','feedback-build-freshness');const check=button('Check build '+item.id+' against today\'s source',async()=>{const status=await request(item.url);if(!lineage())return;const shown=feedbackBuildFreshness(status,{project});facts.replaceChildren(...shown.lines.map(line=>el('p',line,'muted')));facts.dataset.buildFresh=String(shown.fresh);});check.dataset.revisionBuild=item.id;check.dataset.feedbackEdge=edge.edge_id;box.append(check,facts);}
    row.append(box);}
   content.append(row);
  }
  const controls=el('div','','feedback-route-actions');for(const [key,label]of [['recover','Recover outstanding reviews'],['cancel','Stop this review route']])if(!historical&&aggregate.actions?.[key]?.permitted)controls.append(button(label,()=>effect(aggregate.actions[key])));content.append(controls);
  const settings=el('details');settings.append(el('summary','Review settings'),el('p',`Reviews allowed: ${limits.max_new_admissions??'not reported'} · connection attempts per review: ${limits.max_attempts??'not reported'} · time allowed to start reviews: ${limits.admission_seconds??'not reported'} seconds · review time limit: ${limits.runtime_seconds??'not reported'} seconds.`),el('p',`Remaining allowance: ${allowance.remaining??'unknown'} · admitted: ${allowance.admitted??'unknown'} · reserved: ${allowance.reserved??'unknown'} · unconfirmed: ${allowance.unconfirmed??'unknown'}.`),el('p','Source observation: '+(aggregate.origin.currentness?.state||'UNAVAILABLE')+(aggregate.origin.currentness?.reason?' · '+aggregate.origin.currentness.reason:'')));for(const edge of aggregate.edges||[]){const event=edge.event||{};settings.append(el('h4',edge.recipient?.label||edge.obligation_id||'Reviewer'),el('p',[edge.recipient?.provider,edge.recipient?.model,edge.recipient?.effort].filter(Boolean).join(' · ')),el('p',[event.reason,event.last_error,edge.error&&JSON.stringify(edge.error)].filter(Boolean).join(' · ')),el('pre',JSON.stringify({state:event.state,recipient_ack:edge.recipient_ack,attempts:event.attempts,execution_limits:edge.execution_limits,acceptance:event.acceptance},null,2)));}content.append(settings);
  const exact=el('details');exact.append(el('summary','Exact route and receipt details'),el('pre',JSON.stringify(aggregate,null,2)));content.append(exact);dialog.scrollTop=place.scrollTop||0;if(place.control)[...content.querySelectorAll('button')].find(node=>(node.dataset.feedbackEdge||null)===(place.edge||null)&&node.dataset.feedbackControl===place.control)?.focus({preventScroll:true});
 }
 try{if(readerPlace?.snapshot){const cached=inspector.snapshot(readerPlace.snapshot.url,readerPlace.snapshot.cut);if(cached?.value?.aggregate){const value=cached.value.aggregate;if(value.project!==project||value.work?.id!==workId||!sameFeedbackValue(value.origin?.origin_ref,origin))throw Error('The previous review observation belongs to another comment.');aggregate=value;historical=true;snapshot=readerPlace.snapshot;paint();if(readerPlace.reviewContextSnapshot)await showContext(readerPlace.reviewContextSnapshot);}else{notice.textContent='The previous observation is no longer in the bounded inspector cache.';content.append(button('Read current review responses',()=>observe()));}}else await observe();}catch(error){if(current()){notice.textContent=error.message;notice.className='error';content.append(button('Retry review observation',()=>observe()));}}
 return dialog;
}
const reopenReply=args=>openFeedbackReply(args);
export async function openFeedbackReply({project,handle,request,isCurrent=()=>true}){
 const target=handle?.identity;if(target?.project!==project||target.part!=='reply')throw Error('The complete response read has no exact project, conversation and reply identity.');messageReadURL(handle,target);if(!isCurrent())return;
 const inspector=sharedInspector(),life=createLifetime(),dialog=el('dialog','','workspace-dialog feedback-route-reader');dialog.setAttribute('aria-label','Complete review response');const heading=el('h2','Complete review response'),close=declareControl(el('button','Close response'),'review:response-close'),body=el('div','','feedback-route-response'),note=el('p'),more=declareControl(el('button','Continue reading response'),'review:response-continue'),retry=declareControl(el('button','Retry response read'),'review:response-retry'),restart=declareControl(el('button','Restart response read'),'review:response-restart'),details=el('details'),facts=el('pre');details.append(declareControl(el('summary','Exact response basis'),'review:response-basis'),facts);for(const b of [close,more,retry,restart])b.type='button';dialog.append(heading,close,note,body,more,retry,restart,details);let token=null;
 let focusVersion=0;dialog.addEventListener?.('focusin',()=>{focusVersion++;});
 const fresh=()=>!life.disposed&&isCurrent()&&dialog.isConnected!==false;
 const key='laplace:message-reading:'+JSON.stringify(target);let intent={target,page_read:handle,end:0};try{intent=JSON.parse(globalThis.sessionStorage?.getItem(key)||'null')||intent;}catch{}
 const reader=createMessageReading({target,request,intent,remember:value=>{try{globalThis.sessionStorage?.setItem(key,JSON.stringify(value));}catch{}},changed:state=>{if(!fresh())return;if(state.content!==null)body.textContent=state.content;note.textContent=state.error?'Response read failed; prior text is retained. '+state.error:state.complete?'Complete saved public response.':state.absent?'No saved response is recorded.':'Public response page '+state.end+' of '+(state.total??'unknown')+' characters.';more.hidden=!state.next||!!state.error;retry.hidden=!state.error||state.changed;restart.hidden=!state.error;more.disabled=retry.disabled=restart.disabled=state.busy;facts.textContent=JSON.stringify({...target,basis:state.basis,characters:{end:state.end,total:state.total},complete:state.complete,...state.facts},null,2);}});reader.activate(fresh);
 body.tabIndex=-1;const readingAction=(button,fn)=>async()=>{const focused=document.activeElement===button,version=focusVersion,scroll=dialog.scrollTop;await fn();if(focused&&version===focusVersion&&(document.activeElement===button||document.activeElement===document.body)&&button.hidden&&fresh()){body.focus({preventScroll:true});dialog.scrollTop=scroll;}};close.onclick=()=>dialog.close();more.onclick=readingAction(more,()=>reader.next());retry.onclick=readingAction(retry,()=>reader.retry());restart.onclick=readingAction(restart,()=>reader.restart());dialog.onclose=()=>{life.dispose();reader.dispose();dialog.remove();};document.body.append(dialog);token=inspector.adopt(dialog,{kind:'feedback-response',title:'Complete review response',reopen:{factory:reopenReply,args:{project,handle,request}}}).token;dialog.showModal();close.focus();await reader.open();return dialog;
}

// The comment editor is a selected local draft, not a delivery/status owner.
import {createFeedbackDraft,feedbackOriginReceipt,sameFeedbackValue,retainFeedbackSubmission,retainedFeedbackPayload,feedbackLookupURL,feedbackRouteReceipt,bindFeedbackLookup,feedbackTerminalOutcome,feedbackRequestIdentity,feedbackComparisonURL,feedbackAssociation,feedbackRequestOutcome,feedbackUnresolved} from './feedback-route-port.mjs';
const reopenComment=(args,readerPlace)=>openFeedbackComment({...args,readerPlace});
// The displayed passage: a legacy quote, or a mapped selection's displayed observation (never its source target).
const quoteOf=selection=>selection?.anchor?.quote||selection?.anchor?.source_selection?.display_quote||'';
export async function openFeedbackComment({project,selection,request,onSaved=()=>{},isCurrent=()=>true,existingOrigin:givenOrigin=null,readerPlace=null,openProposal=null}){
 if(!isCurrent())return;styles();let existingOrigin=givenOrigin,saveDraft=null;let life=createLifetime(),draft=createFeedbackDraft({project,key:existingOrigin?'origin:'+JSON.stringify(existingOrigin.origin_ref):'passage-comment',initial:{text:existingOrigin?.correction.text||'',selection,route_work:existingOrigin?.review_route_spec?.work_id,request_id:null}}),dialog=el('dialog','','workspace-dialog feedback-route-reader feedback-route-editor');dialog.setAttribute('aria-label','Passage comment and reviews');let prepared=null,preview=null,busy=false,workPage=null,chosenPolicy='',policyDirty=false,commentToken=null,focusVersion=0;dialog.addEventListener?.('focusin',()=>{focusVersion++;});
 const held=draft.snapshot();preview=held.route_preview||null;let autoNeedsInspection=!!held.route_policy_id,routeNeedsInspection=!!preview;if(!held.selection)draft.update({selection});
 const header=el('h2','Comment on this passage'),quote=el('blockquote',quoteOf(draft.snapshot().selection)),meaning=el('p','This is an author instruction for the selected passage. A review response does not apply a manuscript change.','muted'),text=el('textarea'),status=el('p'),save=declareControl(el('button','Save comment'),'review:comment-save'),send=declareControl(el('button','Save and request reviews'),'review:comment-send'),check=declareControl(el('button','Check save'),'review:comment-check'),retry=declareControl(el('button','Retry same save'),'review:comment-retry'),settle=declareControl(el('button','Resolve uncertain save'),'review:comment-settle'),reinspect=el('button','Check selected passage'),close=declareControl(el('button','Close comment'),'review:comment-close'),route=el('details'),routing=el('fieldset'),submitted=el('section');
 text.rows=5;text.readOnly=!!existingOrigin;text.value=held.text||'';text.setAttribute('aria-label','Your comment');status.setAttribute('role','status');for(const b of [save,send,check,retry,settle,reinspect,close])b.type='button';route.append(declareControl(el('summary','Reviewers and limits'),'review:comment-routing'),routing);dialog.append(header,quote,meaning,text,route,status,save,send,check,retry,settle,reinspect,close,submitted);document.body.append(dialog);
 if(!sameFeedbackValue(held.selection,selection))meaning.append(document.createTextNode(' Your existing draft and its original passage were retained; the new selection was not substituted.'));
 // Late typing after Save is retained in this origin's draft; after close/reopen it is shown, never sent or substituted.
 // One rendering path for this origin's retained unsent text, used at origin open and after adoption alike, so retained
 // text is never durable but invisible (review 30e422e0 finding 2). It is never part of the saved comment.
 const unsentSection=el('section','','feedback-unsent-draft'),conflictSection=el('section','','feedback-unsent-conflict');dialog.append(unsentSection,conflictSection);let adoptRefusal='',unsentConflict=null;
 function paintOriginUnsent(){const value=existingOrigin?String(draft.snapshot().unsaved_text||''):'';unsentSection.replaceChildren();unsentSection.hidden=!value.trim()||(!text.readOnly&&text.value===value);
  if(!unsentSection.hidden)unsentSection.append(el('h3','Unsent later typing'),el('p','Recovered from this comment draft. It is not part of the saved comment or its review request, and nothing here sends it.','muted'),el('pre',value));}
 // Two independently changed unsent versions are shown side by side; only an explicit choice writes one of them.
 function paintConflict(){conflictSection.replaceChildren();conflictSection.hidden=!unsentConflict;if(!unsentConflict)return;const {stored,editor,origin_ref}=unsentConflict;
  const choose=(label,value)=>{const b=el('button',label);b.type='button';b.dataset.unsentChoice=label;b.onclick=act(async()=>{const before=draft.snapshot().unsaved_text;draft.update({unsaved_text:value});
   if(draft.retained!==true){draft.update({unsaved_text:before});throw Error(draft.storageError+' Both unsent versions are kept as they were.');}
   saveDraft?.update({transferred:{origin_ref:copy(origin_ref),text:editor}});unsentConflict=null;text.value=value;text.readOnly=false;paintConflict();paintOriginUnsent();status.className='';status.textContent='Unsent text chosen. It stays in this comment\'s draft and is not part of the saved comment.';});conflictSection.append(b);};
  conflictSection.append(el('h3','Two unsent versions'),el('p','This saved comment\'s draft and this editor hold different unsent text. Nothing is merged on its own; choose what to keep.','muted'),
   el('h4','Kept in the saved comment\'s draft'),el('pre',stored),el('h4','From this editor'),el('pre',editor));
  choose('Keep the saved comment\'s unsent text',stored);choose('Use the text from this editor',editor);choose('Keep both, saved comment\'s text first',stored+'\n\n'+editor);}
 paintOriginUnsent();
 // Two stored copies of this draft that do not descend from one another are shown side by side with what each holds;
 // nothing is prepared, saved or sent until one is chosen explicitly, and both original copies stay untouched until then.
 const storeLabel={session:'this tab\'s browser storage',backup:'shared browser storage'};
 let disagreementSection=null;const checks=new Map(),settles=new Map();
 function paintDisagreement(){const section=disagreementSection||el('section','','feedback-draft-disagreement');section.replaceChildren();disagreementSection=section;section.append(el('h3','Two stored copies of this comment draft'),el('p','The browser kept two different copies and neither is known to be the newer one. Both are kept exactly. Choose which copy to continue with; nothing is saved or sent until you do.','muted'));
  (draft.disagreement||[]).forEach((item,index)=>{const s=item.state||{},facts=[s.receipt?'a saved comment receipt':'',s.pending?'an unconfirmed comment request':'',s.policy_pending?'an unconfirmed review policy request':''].filter(Boolean);
   section.append(el('h4','Copy from '+storeLabel[item.store]),el('pre',(String(s.text||'')||'(no comment text)')+(typeof s.unsaved_text==='string'&&s.unsaved_text.trim()?'\n\nUnsent later typing:\n'+s.unsaved_text:'')));if(facts.length)section.append(el('p','It also holds '+facts.join(', ')+'.','muted'));
   const blockedBy=draft.canChoose(index);const b=el('button','Continue with the copy from '+storeLabel[item.store]+'; the other copy is replaced');b.type='button';b.dataset.recovery='disagreement-'+item.store;b.disabled=!!blockedBy;
   b.onclick=act(async()=>{if(!draft.choose(index))throw Error(draft.storageError+' Both copies are kept as they were.');dialog.close();await reopenComment(reopenArgs);});
   const other=(draft.disagreement||[]).find((_copy,i)=>i!==index),replaced=String(other?.state?.text||'');
   section.append(b,el('p','Choosing it replaces the other copy\'s prose'+(replaced.trim()?': “'+replaced+'”':'')+'; every unconfirmed request stays protected.','muted'));if(blockedBy)section.append(el('p',blockedBy,'muted'));});
  paintCopyRequests(section);if(!section.dataset.mounted){section.dataset.mounted='true';dialog.append(section);}text.readOnly=true;}
 // Per-copy recovery of every distinct unconfirmed request (at most 2 copies x Save/route + policy). Check is a pure owner
 // read: the issued legacy lookup, then the owner-issued comparison with only its declared field filled. Zero POST, no write
 // before a matched outcome; that outcome commits only to the checked copy under both shown raw copies and its exact identity.
 const requestLabel={origin:'comment Save',route:'review request',policy:'review policy request'};
 function paintCopyRequests(section){const rows=draft.inventory();if(!rows.length)return;section.append(el('h4','Unconfirmed requests in these copies'));
  for(const entry of rows){const label=requestLabel[entry.kind]||'request',where=entry.holders.map(h=>storeLabel[h.store]).join(' and ');
   section.append(el('p','A '+label+' ('+entry.request_id+') is held by '+where+'.'+(checks.has(entry.identity)?' '+checks.get(entry.identity):''),'muted'));
   const b=el('button','Check this '+label+' (read-only)');b.type='button';b.dataset.requestCheck=String(entry.request_id);b.onclick=act(()=>checkCopyRequest(entry));section.append(b);
   const action=settles.get(entry.identity);if(action){const s=el('button','Settle this '+label+' as never admitted');s.type='button';s.dataset.requestSettle=String(entry.request_id);s.onclick=act(()=>settleCopyRequest(entry,action));section.append(s);}}}
 // F3: the view lease, this exact draft, the copy holding K/wire and BOTH raw copies (as shown and as stored) are captured
 // BEFORE the first await and rechecked after every await and before any POST or commit; a snapshot taken after a reply is
 // never the fence. An outcome that is no longer current stays canonical and unadopted for a later fresh Check.
 function captureCopy(entry){const holder=entry.holders[0],pending=draft.disagreement?.[holder.index]?.state?.[holder.slot];
  if(!pending||feedbackRequestIdentity(holder.slot,pending)!==entry.identity||pending.wire!==entry.wire)throw Error('This copy no longer holds the request; reopen the comment.');
  return {lease:life.lease(),draft,holder,pending,shown:(draft.disagreement||[]).map(item=>({store:item.store,raw:item.raw})),stored:draft.storedBasis()};}
 const copyCurrent=view=>view.lease()&&current()&&draft===view.draft&&sameFeedbackValue(draft.storedBasis(),view.stored);
 async function checkCopyRequest(entry,view=captureCopy(entry)){
  const {holder,pending}=view;
  const legacy=await request(await feedbackLookupURL(pending,entry.kind));if(!copyCurrent(view))return;
  const value=await request(await feedbackComparisonURL(pending,legacy?.compare,holder.slot));if(!copyCurrent(view))return;
  const found=await feedbackRequestOutcome(value,legacy,pending,holder.slot);if(!copyCurrent(view))return;  // a late or raced reply is an observation only
  const said={MATCH:'The owner matched this exact request',MISMATCH:'The owner records another intent under this request id; this copy is kept and nothing is settled from it',
   UNRECORDED:'The owner has no record of this exact request at this read',UNKNOWN:'The owner cannot establish this request; it stays unconfirmed'}[found.state];
  checks.set(entry.identity,said+'.');settles.delete(entry.identity);
  if(found.fields){const fields=found.fields;let ok=true;
   for(const h of entry.holders){if(!copyCurrent(view)||!draft.settleCopy({index:h.index,slot:h.slot,identity:entry.identity,wire:entry.wire,basis:view.shown},fields)){ok=false;break;}
    view.shown=(draft.disagreement||[]).map(item=>({store:item.store,raw:item.raw}));view.stored=draft.storedBasis();}  // the basis advances only by this check's own commit
   checks.set(entry.identity,said+(ok?'; its copy now records that outcome.':'; this copy could not record it locally ('+(draft.lastWriteError||draft.storageError)+'). Both copies are kept.'));}
  else if(found.settle)settles.set(entry.identity,copy(found.settle));
  paintDisagreement();if(draft.conflict)paintWriteConflict();
 }
 // Outcome classification and validation is the shared port feedbackRequestOutcome (one-copy and per-copy alike).
 // Explicit author settlement of one copy's exact request through the owner-issued action; its outcome is then re-observed by
 // the pure Check, and only a matched owner terminal changes that copy. Nothing is retried, refunded or cancelled here.
 async function settleCopyRequest(entry,action){
  const view=captureCopy(entry),{pending}=view;
  const payload=await retainedFeedbackPayload(pending);if(!copyCurrent(view))return;let path,body;
  if(entry.kind==='origin'){path=feedbackHTTP(action,{project,method:'POST',paths:['/authoring/correction-settle']});body={...copy(action.http?.body||{}),project,submission:payload};
   if(body.request_id&&body.request_id!==payload.request_id||body.ledger&&body.ledger!==payload.source_basis?.ledger)throw Error('Settlement changed the retained original request or home.');}
  else{path=feedbackHTTP(action,{project,method:'POST',paths:['/work/delivery']});body={...copy(action.payload||{}),submission:payload};
   if(body.action!=='request-settle'||body.request_kind!==entry.kind||body.request_id!==payload.request_id||body.work_id!==payload.work_id)throw Error('Settlement changed the retained original request.');}
  if(!copyCurrent(view))return;settles.delete(entry.identity);await request(path,body);if(!copyCurrent(view))return;  // the canonical settle stays unadopted for a fresh Check
  await checkCopyRequest(entry,view);
 }
 // A write conflict (this draft changed in another editor after it opened here) keeps this editor's text visible beside the
 // stored copies; nothing is retained or sent from here, and reopening continues with the stored draft.
 const writeConflict=el('section','','feedback-draft-write-conflict');writeConflict.hidden=true;dialog.append(writeConflict);
 function paintWriteConflict(){const c=draft.conflict;writeConflict.hidden=!c;writeConflict.replaceChildren();if(!c)return;const mine=draft.snapshot();
  const textOf=raw=>{if(raw==null)return '(no stored copy)';try{const s=JSON.parse(raw).state||{};return String(s.text||'')+(typeof s.unsaved_text==='string'&&s.unsaved_text.trim()?'\n\nUnsent later typing:\n'+s.unsaved_text:'');}catch(_error){return '(unreadable stored copy, kept as it is)';}};
  writeConflict.append(el('h3','This draft changed in another editor'),el('p','Nothing was overwritten. The text from this editor below is not retained; copy it if you need it, then reopen the comment to continue with the stored draft.','muted'),
   el('h4','Text in this editor (not retained)'),el('pre',String(mine.text||'')+(typeof mine.unsaved_text==='string'&&mine.unsaved_text.trim()?'\n\nUnsent later typing:\n'+mine.unsaved_text:'')));
  for(const item of c.stored)writeConflict.append(el('h4','Stored in '+storeLabel[item.store]),el('pre',textOf(item.raw)));
  const b=el('button','Reopen with the stored draft');b.type='button';b.onclick=act(async()=>{dialog.close();await reopenComment(reopenArgs);});writeConflict.append(b);}
 if(draft.recovered)dialog.append(el('p','Recovered the newer copy of this draft that '+storeLabel[draft.recovered.from]+' kept; the older copy in '+storeLabel[draft.recovered.stale]+' is replaced only when this draft is next saved.','muted feedback-draft-recovered'));
 // Explicit recovery of the one fresh-comment slot: no storage clearing and no silent retarget. A pending or UNKNOWN
 // request, a saved receipt, a terminal non-admission and damaged recovery each keep their own owner path.
 const recovery=el('section','','feedback-draft-recovery'),target=el('p','','muted feedback-comment-target');dialog.append(target,recovery);
 let prepareGeneration=0,prepareFailure=null,keepEarlier=false;
 function draftState(){const s=draft.snapshot();return draft.recoveryError||draft.disagreement?'corrupt':feedbackUnresolved(s)?'pending':s.receipt?'receipt':s.terminal?'terminal':String(s.text||'').trim()?'unsent':'empty';}
 function paintTarget(){const s=draft.snapshot(),anchor=prepared?.anchor||s.selection?.prepare?.anchor||s.selection?.anchor||{},chosen=anchor.source_selection,lines=anchor.line_start?' (lines '+anchor.line_start+(anchor.line_end>anchor.line_start?'–'+anchor.line_end:'')+')':'';
  target.textContent=existingOrigin?'':s.selection?.mapping&&!prepared&&!s.prepared?'No comment target yet: choose a qualified target below. Nothing is inspected or saved until you do.':chosen?.kind==='whole-block'?'Comment target: the whole paragraph source'+lines+'.':chosen?.kind==='piece-span'?'Comment target: the selected source text'+lines+'.':anchor.file?'Comment target: the quoted text'+lines+'.':'';}
 function paintRecovery(){
  recovery.replaceChildren();if(existingOrigin||!current())return;
  const s=draft.snapshot(),state=draftState(),moved=!!selection&&!sameFeedbackValue(s.selection,selection);
  const offer=(label,fn)=>{const b=el('button',label);b.type='button';b.dataset.recovery=label;b.onclick=act(fn);recovery.append(b);};
  if(state==='pending'){if(moved)recovery.append(el('p','An earlier comment request is still unconfirmed. Check it before using the passage you just selected; its exact request is kept.','muted'));return;}
  if(state==='corrupt'||state==='receipt'||state==='terminal')return;
  if(moved&&!keepEarlier){
   if(state==='empty'){recovery.append(el('p','The earlier draft has no text. You can comment on the passage you just selected instead.','muted'));offer('Use the newly selected passage',()=>retarget(''));}
   else{recovery.append(el('p','Your unsent text belongs to the earlier passage. Choose what happens to it; nothing moves on its own.','muted'));
    offer('Keep it on the earlier passage',async()=>{keepEarlier=true;paintRecovery();});
    offer('Move it to the newly selected passage',()=>retarget(text.value));
    offer('Copy it aside and start on the newly selected passage',()=>retarget('',text.value));
    offer('Discard it and use the newly selected passage',()=>retarget(''));}
  }
  // A mapper refusal is not an absent mapping: its reason and qualified choices come first, before any prepare.
  const mapping=s.selection?.mapping;if(mapping){if(mapping.reason)recovery.append(el('p',mapping.reason,'muted'));
   for(const choice of mapping.choices||[])if(choice?.anchor)offer(choice.label,()=>widen(choice));
   if(!(mapping.choices||[]).some(choice=>choice?.anchor))recovery.append(el('p','Close this comment and select text within one paragraph, or right-click the paragraph and choose Comment on this passage.','muted'));}
 }
 async function retarget(kept,aside=null){
  if(['pending','corrupt','receipt'].includes(draftState()))throw Error('This draft has an unconfirmed or saved request; it is not retargeted.');
  draft.reset({text:kept,selection:copy(selection),request_id:null});
  prepared=null;preview=null;prepareFailure=null;keepEarlier=false;text.value=kept;quote.textContent=quoteOf(selection);submitted.replaceChildren();
  meaning.textContent='This is an author instruction for the selected passage. A review response does not apply a manuscript change.';
  if(aside){const held=el('details');held.open=true;held.append(el('summary','Your earlier unsent text'),el('pre',aside));submitted.append(held);}
  await runPrepare();
 }
 async function widen(choice){
  const s=draft.snapshot();if(['pending','corrupt','receipt'].includes(draftState()))throw Error('This draft has an unconfirmed or saved request; its target is not changed.');
  const next={...s.selection,anchor:copy(choice.anchor),prepare:{...s.selection.prepare,anchor:copy(choice.anchor),...(choice.expected?{expected:copy(choice.expected)}:{}),...(choice.selection_identity?{selection_identity:choice.selection_identity}:{})}};delete next.mapping;
  draft.update({selection:next,prepared:null});prepared=null;prepareFailure=null;quote.textContent=quoteOf(next);await runPrepare();
 }
 // Every prepare outcome, success or rejection, belongs to the generation that started it; a superseded one is ignored.
 async function runPrepare(){prepareFailure=null;const generation=++prepareGeneration;try{await prepare(generation);}catch(error){if(current()&&generation===prepareGeneration){prepareFailure=error.message;status.textContent=error.message+' Your original comment draft is retained.';status.className='error';}}if(current()&&generation===prepareGeneration){paintRecovery();paintTarget();buttons();}}
 async function openSavedOrigin(){
  const receipt=draft.snapshot().receipt;if(!receipt?.origin_ref||!receipt.read)throw Error('The saved comment has no owner read; open it from Review & notes.');
  const lease=life.lease(),value=await request(feedbackHTTP(receipt.read,{project,paths:['/authoring/correction-origin']}));if(!lease()||!current())return;
  if(!sameFeedbackValue(value?.origin_ref,receipt.origin_ref)||value.correction?.text!==receipt.correction?.text)throw Error('The comment owner returned another saved comment; nothing was opened.');
  // Unsent typing that differs from the saved text is handed to the origin draft once (see adoptSaved).
  const later=text.value.trim()!==value.correction.text;
  if(!adoptSaved({...receipt,correction:copy(value.correction)},later,value))throw Error(adoptRefusal?'This saved comment\'s draft could not retain your unsent text ('+adoptRefusal+'). Nothing was moved; your text stays in this editor.':'This saved comment cannot be opened here; open it from Review & notes.');
  paintReceipt(null);paintTarget();recovery.replaceChildren();status.className='';status.textContent='Saved comment opened. Choose reviewers and request reviews here; it is not saved again.'+(unsentConflict?' Two different unsent versions exist; choose below.':text.readOnly?'':' Your later typing remains in this draft and is not part of the saved comment.');
  const held=draft.snapshot();if(held.route_work&&workPage)await readPreview({work_id:held.route_work});else if(workPage)paintRouting();
 }
 const current=()=>!life.disposed&&isCurrent()&&dialog.isConnected!==false;
 const act=fn=>async()=>{if(busy||!current())return;const focused=document.activeElement,coordinate=routing.contains?.(focused)?{label:focused.getAttribute('aria-label'),text:focused.textContent,tag:focused.tagName}:null;busy=true;buttons();try{await fn();}catch(error){if(current()){status.textContent=(error.message||draft.storageError||'This action did not complete.')+' Your comment and its original request are retained.';status.className='error';}}finally{busy=false;if(current()){if(draft.conflict)paintWriteConflict();buttons();if(coordinate&&(!document.activeElement||document.activeElement===document.body||document.activeElement===focused||document.activeElement.isConnected===false)){const node=[...routing.querySelectorAll('input,select,button')].find(n=>coordinate.label?n.getAttribute('aria-label')===coordinate.label:n.tagName===coordinate.tag&&n.textContent===coordinate.text);node?.focus?.({preventScroll:true});}}}};
 function buttons(){routing.disabled=busy;const s=draft.snapshot(),pending=feedbackUnresolved(s)||!!draft.recoveryError||!!draft.disagreement||!!draft.conflict,automatic=preview?.policy?.mode==='automatic'&&!policyDirty;
  save.hidden=!!existingOrigin;save.disabled=busy||pending||!!s.receipt||!prepared||autoNeedsInspection;save.textContent=automatic?'Save comment and request reviews':'Save comment';send.textContent=existingOrigin?'Request reviews':'Save and request reviews';send.hidden=!existingOrigin&&automatic;send.disabled=busy||pending||!!s.receipt||!(prepared||existingOrigin)||policyDirty||routeNeedsInspection||!preview?.actions?.compose?.permitted;
  check.textContent=existingOrigin?'Check review request':'Check save';retry.textContent=existingOrigin?'Retry same review request':'Retry same save';check.hidden=!s.pending;check.disabled=busy;retry.hidden=!s.pending||s.pending.observation!=='NONE';retry.disabled=busy;settle.hidden=existingOrigin||!s.pending||!(s.pending.settle||prepared?.settle);settle.disabled=busy;reinspect.hidden=!s.terminal||!!s.pending;reinspect.disabled=busy;close.disabled=false;settleRequest.hidden=!offeredSettle('pending');settleRequest.disabled=busy;
 }
 // Typing that no store retains is reported, never presented as kept.
 text.oninput=()=>{draft.update(existingOrigin?.adopted?{unsaved_text:text.value}:{text:text.value});if(draft.retained===false&&!draft.disagreement&&!draft.recoveryError){status.textContent=draft.storageError;status.className='error';}if(draft.conflict){paintWriteConflict();buttons();}};close.onclick=()=>dialog.close();dialog.onclose=()=>{life.dispose();dialog.remove();};const reopenArgs={project,selection,request,onSaved,existingOrigin,openProposal};commentToken=sharedInspector().adopt(dialog,{kind:'feedback-comment',title:'Passage comment',reopen:{factory:reopenComment,args:reopenArgs}}).token;dialog.showModal();text.focus();const openingFocus=focusVersion;
 async function prepare(generation=++prepareGeneration){
  const s=draft.snapshot();if(s.pending){prepared=s.prepared||null;status.textContent='The original submission outcome is unconfirmed. Keep its exact request and check it before another submission.';return;}if(s.receipt){paintReceipt(s.receipt);return;}if(s.terminal){prepared=s.readdressed?s.prepared:null;const comparison=el('details');comparison.append(el('summary','Original settled submission and passage'),el('pre',JSON.stringify(s.terminal,null,2)));submitted.append(comparison);status.textContent=s.readdressed?'The revised passage was explicitly inspected. Your retained prose is ready; a new request is created only when you Save.':'The original request is terminally not admitted. Your prose is retained. If the passage changed, close this editor, refresh the manuscript and select the intended passage. Explicitly inspect that selection before a new Save.';return;}if(existingOrigin){paintReceipt(s.receipt);status.textContent='The saved comment remains unchanged. Choose its review recipients and policy.';return;}if(s.pending||s.receipt){paintReceipt(s.receipt);return;}
  // A refused reader mapping waits for an explicit qualified choice; its rendered quote is never prepared on its own.
  if(s.selection?.mapping&&!s.prepared){prepared=null;status.className='';status.textContent='This selection has no qualified source target yet. Choose one of the targets offered; nothing is inspected or saved until you do.';return;}
  const original=copy(s.selection.prepare||{});delete original.project;delete original.request_id;const body=s.prepared?{project,anchor:s.prepared.anchor,source_basis:s.prepared.source_basis,base_revision:s.prepared.base_revision,...(s.request_id?{request_id:s.request_id}:{})}:{project,...original,...(s.request_id?{request_id:s.request_id}:{})};
  const lease=life.lease(),value=await request('/authoring/correction-prepare',body);if(!lease()||!current()||generation!==prepareGeneration)return;
  if(value.project!==project||value.source_basis?.project!==project||!value.save||!value.reconcile)throw Error('The comment owner returned another project or incomplete preparation.');
  if(s.prepared&&(!sameFeedbackValue(s.prepared.source_basis,value.source_basis)||s.prepared.base_revision!==value.base_revision))throw Error('The comment owner changed this draft basis; the original was retained.');
  prepared=value;draft.update({prepared:copy(value)});paintTarget();if(s.route_work&&s.route_policy_id)await readPreview({work_id:s.route_work,policy_id:s.route_policy_id});meaning.textContent=value.meaning||meaning.textContent;status.textContent='Original passage inspected. Save keeps this exact source basis.';
 }
 // The kind of an outcome is the kind of the verified retained wire, never the editor's existingOrigin flag. A Check passes
 // its captured view: every await is followed by the same fence before the local commit (F3).
 async function accept(value,pending,view=null){
  const kind=JSON.parse(feedbackRequestIdentity('pending',pending))[0],live=()=>!view||stillCurrent(view);
  if(kind==='origin'&&value?.effect==='NOT_ADMITTED'){const terminal=await feedbackTerminalOutcome(value,pending);if(!live())return staleView(view);draft.update({pending:null,terminal,prepared:null,request_id:null,readdressed:false});prepared=null;if(current()){status.textContent='This original request is terminally not admitted. Your prose and passage comparison are retained; inspect the selected passage before a new Save.';buttons();}return terminal;}
  if(kind==='route'){if(!existingOrigin)throw Error('This review request belongs to a saved comment; open it from Review & notes.');await feedbackRouteReceipt(value,pending,existingOrigin.origin_ref);if(!live())return staleView(view);draft.settle(value);if(current()){paintReceipt(value);status.textContent='Review route recorded. The comment remains unchanged.';}return value;}
  const receipt=await feedbackOriginReceipt(value,pending);if(!live())return staleView(view);if(!receipt){if(current())status.textContent='The saved outcome is not established. Keep this exact request and check its status.';return null;}
  // Settle the effect under its original identity even if this editor was closed while awaiting it.
  draft.settle(receipt,{route_outcome:value.review_route||null,previous_terminal:draft.snapshot().terminal||draft.snapshot().previous_terminal||null,terminal:null,readdressed:false});
  // A matched canonical outcome that this editor could not record locally is said distinctly; nothing is sent again.
  if(draft.retained===false&&current()){status.className='error';status.textContent='The owner recorded this comment, but this editor could not record that locally: '+draft.storageError+' Nothing is sent again; reopen the comment to continue from the stored draft.';paintWriteConflict();buttons();return receipt;}
  if(current()){const later=text.value.trim()!==receipt.correction.text,adopted=adoptSaved(receipt,later);paintReceipt(receipt);status.textContent=(later?'Original comment saved. Your later typing remains in this draft.':'Comment saved.')+(adopted?' Choose reviewers and request reviews of this saved comment here.':'');buttons();await onSaved(receipt);const routeHeld=draft.snapshot();if(adopted&&current()&&workPage){if(routeHeld.route_work)await readPreview({work_id:routeHeld.route_work,...(routeHeld.route_policy_id?{policy_id:routeHeld.route_policy_id}:{})},{adopt:true});else paintRouting();}}
  return receipt;
 }
 // Same editor (a7): the ACTUAL Save receipt becomes this editor's saved origin at once; no close/reopen. The settled Save
 // custody stays in its own draft; a review request gets the origin-keyed custody (its own pending and lost-ack lookup).
 function adoptSaved(receipt,later,inspected=null){
  if(existingOrigin||!receipt?.origin_ref||(receipt.review_route_spec&&!inspected))return false;
  adoptRefusal='';const s=draft.snapshot(),fresh=draft,mine=text.value;
  // The fresh slot hands its unsent text to this origin once; the exact text handed over is remembered on the fresh draft,
  // so reopening never hands the same, now stale, fragment over again (review 30e422e0 finding 1). No text is merged by
  // heuristic: an origin draft changed independently since the hand-over is a conflict that needs an explicit choice.
  const handed=s.transferred&&sameFeedbackValue(s.transferred.origin_ref,receipt.origin_ref)?s.transferred.text:null;
  const next=createFeedbackDraft({project,key:'origin:'+JSON.stringify(receipt.origin_ref),initial:{text:receipt.correction.text,selection:copy(s.selection||selection),route_work:s.route_work||null,route_policy_id:s.route_policy_id||null,route_form:s.route_form||null,request_id:null}});
  if(next.recoveryError||next.disagreement){adoptRefusal=next.storageError;return false;}
  const prior=typeof next.snapshot().unsaved_text==='string'?next.snapshot().unsaved_text:'',offered=later&&mine!==handed?mine:null;let conflict=null;
  if(offered!==null){if(!prior.trim()||prior===offered||(handed!==null&&prior===handed))next.update({unsaved_text:offered});else conflict={stored:prior,editor:offered,origin_ref:copy(receipt.origin_ref)};}
  // Retain the destination before anything counts as moved; a failed hand-over keeps the fresh draft and its custody.
  const retained=next.persist();if(!retained&&offered!==null&&!conflict){adoptRefusal=next.storageError;return false;}
  if(offered!==null&&!conflict)fresh.update({transferred:{origin_ref:copy(receipt.origin_ref),text:offered}});
  saveDraft=fresh;draft=next;unsentConflict=conflict;
  existingOrigin={origin_ref:copy(receipt.origin_ref),correction:copy(receipt.correction),source_basis:copy(receipt.source_basis||null),review_route_spec:inspected?.review_route_spec?copy(inspected.review_route_spec):null,review_route_read:inspected?.review_route_read?copy(inspected.review_route_read):null,adopted:{request_id:receipt.request_id}};
  reopenArgs.existingOrigin=existingOrigin;preview=null;policyDirty=false;autoNeedsInspection=false;routeNeedsInspection=false;
  const unsent=conflict?'':String(draft.snapshot().unsaved_text||'');
  if(unsent.trim()){text.value=unsent;text.readOnly=false;}else{text.value=receipt.correction.text;text.readOnly=true;}
  paintConflict();paintOriginUnsent();
  meaning.textContent='Saved comment. A review response does not apply a manuscript change.'+(unsent.trim()?' The text box holds unsent typing kept in this comment\'s draft: not part of the saved comment or its review request.':'')+(conflict?' Two different unsent versions exist; choose below.':'')+(retained?'':' '+draft.storageError);
  return true;
 }
 async function post(){const pending=draft.snapshot().pending,payload=await draft.pendingPayload();draft.observe('UNKNOWN');const value=await request(existingOrigin?'/work/delivery':'/authoring/correction',payload);await accept(value,pending);}
 async function submit(withReviews){
  const blocked=unresolvedReason();if(blocked)throw Error(blocked);
  const s=draft.snapshot();if(!existingOrigin&&!text.value.trim())throw Error('Write the comment first.');if(!(prepared||existingOrigin))throw Error('Inspect the original passage first.');
  const automatic=preview?.policy?.mode==='automatic'&&!policyDirty,compose=preview?.actions?.compose;
  if((withReviews||automatic)&&(policyDirty||routeNeedsInspection||!compose?.permitted))throw Error(compose?.reason||'Preview a permitted finite review route first.');
  if(existingOrigin){if(!preview?.request_read)throw Error('The route owner supplied no exact request reconciliation.');const payload={...copy(compose.route_spec),project,origin:copy(existingOrigin.origin_ref)};if(payload.request_id!==(s.route_request_id||s.request_id))throw Error('The review route changed its original request.');await draft.retain(payload,preview.request_read);await post();return;}
  const requestId=s.request_id||('FC-'+crypto.randomUUID());if(!s.request_id)draft.update({request_id:requestId});
  const payload={project,request_id:requestId,source_basis:copy(prepared.source_basis),base_revision:prepared.base_revision,anchor:copy(prepared.anchor),text:text.value,kind:'note',scope:'passage',by:'author',...((withReviews||automatic)?{review_route:copy(compose.route_spec)}:{})};
  await draft.retain(payload,bindFeedbackLookup(prepared.reconcile,requestId));if(prepared.settle)draft.update({pending:{...draft.snapshot().pending,settle:copy(prepared.settle)}});await post();
 }
 // F3: ONE fence for every one-copy lookup, comparison, settle and recheck. The view lifetime, this exact draft, the slot's
 // request identity K and raw wire, and BOTH raw stored copies are captured BEFORE the first await and rechecked after each
 // await and before any POST, local commit or paint; a snapshot taken after a reply is never the fence. Close, a copy
 // choice, a new view, a same-ID changed wire or new typing makes the old outcome non-current: it stays canonical and
 // unadopted for a fresh Check, and nothing here clears custody, overwrites prose or target, or repaints another view.
 function captureView(slot){const held=draft.snapshot()[slot]||null,identity=feedbackRequestIdentity(slot,held);
  return {lease:life.lease(),draft,slot,held,identity,kind:identity?JSON.parse(identity)[0]:null,wire:typeof held?.wire==='string'?held.wire:null,basis:draft.storedBasis()};}
 function stillCurrent(view){if(!view.lease()||!current()||draft!==view.draft)return false;const held=draft.snapshot()[view.slot];
  return !!held&&feedbackRequestIdentity(view.slot,held)===view.identity&&held.wire===view.wire&&sameFeedbackValue(draft.storedBasis(),view.basis);}
 function staleView(view){if(view.lease()&&current()&&draft===view.draft){status.className='';status.textContent='This comment draft changed while its request was checked. That owner reply is kept only as an observation and nothing was changed here; check the request again.';}return null;}
 // F2: ONE unresolved predicate (port feedbackUnresolved: pending OR policy_pending) for the controls and for every new
 // Save, Request reviews, Save and request and automatic-policy handler alike, so no programmatic or queued call bypasses a
 // disabled control. The pure Check, the owner-issued settle and the exact retry of the same retained request stay available.
 const UNRESOLVED='An earlier request of this comment is still unconfirmed. Check or settle it first; nothing new is saved or sent until then.';
 const unresolvedReason=()=>feedbackUnresolved(draft.snapshot())?UNRESOLVED:'';
 // The owner-issued request-settle offered for a slot, kept with the exact request identity it was issued for.
 const settleActions={pending:null,policy_pending:null};
 const offeredSettle=slot=>{const held=draft.snapshot()[slot],item=settleActions[slot];return item&&held&&feedbackRequestIdentity(slot,held)===item.identity?item.action:null;};
 async function reconcile(){
  // A Check is a pure owner read: no persisting payload read and no observation write before a validated reply.
  const view=captureView('pending'),pending=view.held;if(!pending)throw Error('No retained comment request is selected.');
  await draft.payloadOf('pending');if(!stillCurrent(view))return staleView(view);
  const value=await request(await feedbackLookupURL(pending,view.kind));if(!stillCurrent(view))return staleView(view);
  if(value?.compare){await consumeHeld(view,value);return;}
  if((view.kind==='origin'&&(value.project!==project||value.request_id!==pending.request_id))||!['RECORDED','NOT_ADMITTED','NONE','UNKNOWN'].includes(value.effect))throw Error('The comment lookup returned another request or an unknown envelope.');
  if(value.effect==='RECORDED'||value.effect==='NOT_ADMITTED'){await accept(value,pending,view);return;}
  if(value.settle)draft.update({pending:{...draft.snapshot().pending,settle:copy(value.settle)}});draft.observe(value.effect,view.identity);status.textContent=value.effect==='NONE'?'No origin was recorded at this read. This does not settle another in-flight copy. Retry only this exact retained submission.':'The owner could not establish this request outcome. Keep the original request and check again.';
 }
 // One-copy recovery consumes the SAME issued comparison and shared outcome validation as the per-copy recovery: only a
 // fully validated outcome changes the slot, through the checked local commit under the view captured before the first await.
 const settleRequest=el('button','Settle this review request as never admitted');settleRequest.type='button';settleRequest.hidden=true;dialog.append(settleRequest);
 async function consumeHeld(view,legacy){
  const pending=view.held,kind=view.kind,value=await request(await feedbackComparisonURL(pending,legacy.compare,'pending'));if(!stillCurrent(view))return staleView(view);
  const outcome=await feedbackRequestOutcome(value,legacy,pending,'pending');if(!stillCurrent(view))return staleView(view);
  settleActions.pending=null;
  if(outcome.fields&&outcome.effect==='RECORDED'){await accept(legacy,pending,view);return;}
  if(outcome.fields&&kind==='origin'){await accept(value,pending,view);return;}
  if(outcome.fields){
   if(!draft.settleCopy({slot:'pending',identity:view.identity,wire:view.wire,basis:view.basis},{...outcome.fields,route_request_id:'FR-'+crypto.randomUUID()}))
    throw Error('The owner settled this review request, but this editor could not record that locally: '+(draft.lastWriteError||draft.storageError)+' Nothing is sent again.');
   preview=null;routeNeedsInspection=true;status.className='';
   status.textContent='This review request was settled as never admitted'+(outcome.fields.route_terminal?.preserved_effects?.length?'; its recorded review policy stays recorded':'')+'. Preview reviews again to send a new request.';buttons();return;}
  if(outcome.state==='MISMATCH')throw Error('The owner records another intent under this request id; this original request is retained and nothing is settled.');
  if(outcome.settle&&kind!=='origin')settleActions.pending={identity:view.identity,action:copy(outcome.settle)};
  if(kind==='origin'&&outcome.settle)draft.update({pending:{...draft.snapshot().pending,settle:copy(outcome.settle)}});
  draft.observe(outcome.state==='UNRECORDED'?'NONE':'UNKNOWN',view.identity);const settleable=!!settleActions.pending;
  status.textContent=outcome.state==='UNRECORDED'?'No record of this exact request at this read. Retry only this exact retained submission'+(settleable?', or settle it as never admitted.':'.')
   :'The owner could not establish this request outcome'+(settleable?'; you can settle it as never admitted. Any recorded policy effect stays recorded.':'. Keep the original request and check again.');buttons();
 }
 // F1: ONE owner-permitted request-settle for a one-copy held route OR policy request. Its kind comes from the verified
 // retained wire; the owner-issued action is posted once with that exact submission, then the SAME pure recheck (issued
 // lookup and comparison), the SAME full validation and the checked local commit, all under the view captured here.
 async function settleHeld(slot){
  const view=captureView(slot),action=offeredSettle(slot);if(!view.held||!action)throw Error('The owner has not issued a settlement for this request.');
  if(!['route','policy'].includes(view.kind))throw Error('This request is settled through its own comment owner.');
  const payload=await draft.payloadOf(slot);if(!stillCurrent(view))return staleView(view);
  const body={...copy(action.payload||{}),submission:payload};
  if(body.action!=='request-settle'||body.request_kind!==view.kind||body.request_id!==payload.request_id||body.work_id!==payload.work_id||(body.project!==undefined&&body.project!==project))throw Error('Settlement changed the retained original request.');
  settleActions[slot]=null;if(slot==='policy_pending')paintPolicyRecovery();
  await request(feedbackHTTP(action,{project,method:'POST',paths:['/work/delivery']}),body);if(!stillCurrent(view))return staleView(view);
  const legacy=await request(await feedbackLookupURL(view.held,view.kind));if(!stillCurrent(view))return staleView(view);
  if(!legacy?.compare)throw Error('The owner issued no comparison for this request after the settlement; it stays unconfirmed. Check it again.');
  await (slot==='policy_pending'?consumePolicy(view,legacy):consumeHeld(view,legacy));
 }
 settleRequest.onclick=act(()=>settleHeld('pending'));
 settle.onclick=act(async()=>{const view=captureView('pending'),pending=view.held,action=pending?.settle||prepared?.settle;if(!pending||!action)throw Error('The owner has not issued a settlement action.');const payload=await draft.payloadOf('pending');if(!stillCurrent(view))return staleView(view);const body={...copy(action.http?.body||{}),project,submission:payload};if(action.http?.body?.project&&action.http.body.project!==project||body.request_id&&body.request_id!==payload.request_id||body.ledger&&body.ledger!==payload.source_basis.ledger)throw Error('Settlement changed the retained original request or home.');
  if(!draft.observe('UNKNOWN',view.identity))throw Error(draft.storageError||'This comment draft could not be retained; nothing was sent.');view.basis=draft.storedBasis();  // advanced only by this action's own write
  const value=await request(feedbackHTTP(action,{project,method:'POST',paths:['/authoring/correction-settle']}),body);if(!stillCurrent(view))return staleView(view);await accept(value,pending,view);});
 reinspect.onclick=act(async()=>{const s=draft.snapshot();if(!s.terminal||s.pending)throw Error('Observe terminal non-admission before changing the original request.');const original=copy(selection.prepare||{});delete original.project;delete original.request_id;const value=await request('/authoring/correction-prepare',{project,...original});if(!current())return;if(value.project!==project||value.source_basis?.project!==project)throw Error('The comment owner inspected another passage project.');prepared=value;draft.update({selection:copy(selection),prepared:copy(value),request_id:null,readdressed:true});quote.textContent=quoteOf(selection);status.textContent='Selected passage explicitly inspected. Your prose is retained; a new request will be created only when you Save.';buttons();});
 save.onclick=act(()=>submit(false));send.onclick=act(()=>submit(true));check.onclick=act(reconcile);retry.onclick=act(async()=>{if(draft.snapshot().pending?.observation!=='NONE')throw Error('Check the original request first.');await post();});
 function paintReceipt(receipt){
  submitted.replaceChildren();if(!receipt&&!existingOrigin)return;const origin=existingOrigin||receipt;submitted.append(el('h3','Saved comment'),el('p',origin.correction.text));if(existingOrigin){const spec=existingOrigin.review_route_spec,workId=receipt?.aggregate?.work?.id||spec?.work_id;if(workId){const open=el('button','Review responses');open.type='button';open.onclick=act(()=>openFeedbackResponses({project,origin:origin.origin_ref,workId,read:existingOrigin.review_route_read||null,request,isCurrent,openProposal,onDecisionOpened:()=>{draft.update({text:text.value});if(dialog.isConnected!==false)dialog.close();}}));submitted.append(open);}return;}const another=el('button','Prepare another comment on the selected passage');another.type='button';another.onclick=act(async()=>{const currentText=text.value.trim()===receipt.correction.text?'':text.value,previous=draft.snapshot();draft.reset({text:currentText,selection,request_id:null,route_work:previous.route_work,route_policy_id:previous.route_policy_id,route_preview:previous.route_preview});prepared=null;preview=null;text.value=currentText;quote.textContent=quoteOf(selection);submitted.replaceChildren();await runPrepare();});submitted.append(another);
  if(!receipt.review_route_spec&&receipt.read){const open=el('button','Open saved comment and request reviews');open.type='button';open.dataset.recovery='adopt-saved';open.onclick=act(openSavedOrigin);submitted.append(open);}
  const spec=(existingOrigin||receipt).review_route_spec||{work_id:receipt.aggregate?.work?.id};if(spec?.work_id){const open=el('button','Review responses');open.type='button';open.onclick=act(()=>openFeedbackResponses({project,origin:receipt.origin_ref,workId:spec.work_id,read:receipt.review_route_read||null,request,isCurrent:()=>isCurrent(),openProposal,onDecisionOpened:()=>{draft.update({text:text.value});if(dialog.isConnected!==false)dialog.close();}}));submitted.append(open);const outcome=draft.snapshot().route_outcome;if(outcome)submitted.append(el('p','Review routing: '+(outcome.effect||outcome.state||'outcome not yet observed'),'muted'));}
 }
 async function readPreview(body,{adopt=false}={}){
  if(!draft.snapshot().route_request_id)draft.update({route_request_id:'FR-'+crypto.randomUUID()});
  const lease=life.lease(),value=await request(deliveryRead(project,{action:'route-preview',...body,...(existingOrigin?{origin:existingOrigin.origin_ref}:{}),request_id:draft.snapshot().route_request_id||draft.snapshot().request_id}));if(!lease()||!current())return null;
  if(value.work?.id!==body.work_id)throw Error('The route preview returned another Work.');const old=draft.snapshot().route_preview,prior=old?.policy;if(!adopt&&old?.work?.id===value.work.id&&old.work.revision!==value.work.revision){autoNeedsInspection=!!prior?.id;routeNeedsInspection=true;throw Error('The inspected Work basis changed. Your draft is retained; explicitly preview and use its current review inputs before sending.');}if(!adopt&&prior?.id&&value.policy?.id===prior.id&&value.policy.revision!==prior.revision){autoNeedsInspection=true;throw Error('The selected author policy changed. Your original draft policy is retained; explicitly inspect and use a current policy before requesting reviews.');}preview=value;autoNeedsInspection=false;routeNeedsInspection=false;draft.update({route_work:body.work_id,route_preview:copy(value)});paintRouting();buttons();return value;
 }
 async function chooseWork(id){chosenPolicy='';policyDirty=false;await readPreview({work_id:id},{adopt:true});}
 function field(host,label,value,change,{options=null,type='text',id=null,owner=null}={}){const wrap=el('label',label),input=el(options?'select':'input');input.setAttribute('aria-label',label);if(id)declareControl(input,id,owner);if(options)for(const [id,title]of options){const option=el('option',title);option.value=id;input.append(option);}else input.type=type;input.value=value??'';input.onchange=()=>change(input.value);wrap.append(input);host.append(wrap);return input;}
 let recipientFields=[],limitFields={};
 function authoredPolicy(mode){
  return {mode,recipients:recipientFields.filter(row=>row.check.checked).map(row=>({obligation_id:row.id,recipient_binding_id:row.binding.value})),limits:Object.fromEntries(Object.entries(limitFields).map(([key,input])=>[key,Number(input.value)]))};
 }
 function paintRouting(){
  routing.replaceChildren();if(!workPage){routing.append(el('p','Choose an existing review Work.'));return;}
  field(routing,'Existing review Work',preview?.work?.id||'',id=>id&&act(()=>chooseWork(id))(),{id:'review:comment-work',options:[['','Choose Work'],...(workPage.tasks||[]).map(task=>[task.id,task.title||task.id])]});
  if(workPage.pagination?.next_read){const more=declareControl(el('button','More existing Work'),'review:comment-more-work');more.type='button';more.onclick=act(async()=>{const next=await request(feedbackHTTP(workPage.pagination.next_read,{project,paths:['/work/state']}));if(next.project!==project||next.read_cut?.revision!==workPage.read_cut?.revision)throw Error('Work changed between pages; inspect the list again.');workPage={...next,tasks:[...workPage.tasks,...next.tasks]};paintRouting();});routing.append(more);}
  const setupWork=preview?.work?.id||draft.snapshot().route_work;
  const setup=el('button','Set up reviews');setup.type='button';setup.dataset.control='work:review-setup';setup.disabled=!setupWork;setup.onclick=act(async()=>{draft.update({review_setup_opened:true});const inspector=sharedInspector(),url='/work/state?'+new URLSearchParams({project,view:'summary',limit:'30'}),cut=workPage?.read_cut?.revision;const cached=workPage&&cut&&inspector.remember(url,workPage);inspector.pin(commentToken,{routeOpen:route.open,scroll:dialog.scrollTop,control:'Set up reviews',workSnapshot:cached?{url,cut}:null});const module=await import('./review-setup.mjs');if(current())await module.openReviewSetup({project,workId:setupWork,request,read:preview?.bindings_coverage?.read||null,sourceFile:prepared?.source_basis?.file||draft.snapshot().prepared?.source_basis?.file||existingOrigin?.source_basis?.file||null,isCurrent});});routing.append(setup);
  if(!setupWork)routing.append(el('p','Choose an existing Work to set up its review questions and reviewers.','muted'));
  if(draft.snapshot().review_setup_opened&&setupWork){routing.append(el('p','Your comment and its original request are retained. Explicitly preview the updated setup before requesting reviews.','muted'));const inspect=el('button','Preview updated review setup');inspect.type='button';inspect.onclick=act(async()=>{const previous=draft.snapshot().route_preview?.policy;await readPreview({work_id:setupWork,...(previous?.id?{policy_id:previous.id}:{})},{adopt:true});draft.update({review_setup_opened:false});paintRouting();});routing.append(inspect);}
  if(!preview)return;routing.append(el('p',preview.work.title||preview.work.id));const form=draft.snapshot().route_form||{},policy=preview.policy;
  field(routing,'Saved review settings',chosenPolicy||policy?.id||'',async id=>{chosenPolicy=id;policyDirty=false;await act(()=>readPreview({work_id:preview.work.id,...(id?{policy_id:id}:{})},{adopt:true}))();},{id:'review:comment-policy',options:[['','Use manual review settings'],...(preview.policies||[]).map(item=>[item.id,(item.mode||'manual')+' · '+item.id])]});
  if(policy)routing.append(el('p',(policy.id?'Saved ':'Preview ')+policy.mode+' review settings. '+(policy.mode==='automatic'?'Saving the comment requests these reviews once; no second Send.':'One explicit Save and request reviews decision is required.'),'muted'));
  const selected=policy?.recipients||(preview.selected_recipients?.length?preview.selected_recipients:form.recipients)||[];recipientFields=[];
  for(const obligation of preview.obligations||[]){const held=selected.find(row=>row.obligation_id===obligation.id),line=el('label'),check=el('input');check.type='checkbox';check.checked=!!held;line.append(check,document.createTextNode(obligation.label||obligation.id));routing.append(line);
   const binding=field(routing,'Reviewer for '+(obligation.label||obligation.id),held?.recipient_binding_id||'',()=>{policyDirty=true;keepForm();},{options:[['','Choose approved reviewer'],...(preview.bindings||[]).map(item=>[item.id,item.label||item.id])]});recipientFields.push({id:obligation.id,check,binding});check.onchange=()=>{policyDirty=true;keepForm();};}
  const limits=el('div','','feedback-route-limits');limitFields={};for(const [key,label]of [['max_new_admissions','Reviews allowed'],['max_attempts','Connection attempts per review'],['admission_seconds','Time allowed to start reviews (seconds)'],['runtime_seconds','Review time limit (seconds)']])limitFields[key]=field(limits,label,policy?.limits?.[key]??form.limits?.[key]??'',()=>{policyDirty=true;keepForm();},{type:'number',id:'review:comment-limit',owner:key});routing.append(limits,el('p','Reviews allowed is shared across this comment’s reviews. Connection recovery keeps the original request.','muted'));
  const inspect=declareControl(el('button','Preview reviews'),'review:comment-preview');inspect.type='button';inspect.onclick=act(async()=>{keepForm();if(draft.snapshot().policy_receipt&&!draft.snapshot().policy_pending)draft.update({route_request_id:'FR-'+crypto.randomUUID()});await readPreview({work_id:preview.work.id,policy:authoredPolicy('manual')},{adopt:true});policyDirty=false;});routing.append(inspect);
  for(const row of preview.recipients||[]){routing.append(el('p',(row.recipient?.label||row.recipient_binding_id)+' · '+(row.obligation?.label||row.obligation_id)+' · '+(row.relevance?.reason||row.relevance?.state||'relevance not reported'),'muted'));if(row.obligation?.inputs?.length){const detail=el('details');detail.append(el('summary','Handed review inputs'),el('pre',JSON.stringify(row.obligation.inputs,null,2)));routing.append(detail);}}
  for(const issue of preview.issues||[])routing.append(el('p',typeof issue==='string'?issue:issue.reason||issue.code||JSON.stringify(issue),'error'));
  // Automatic policy recording is a separate explicit author decision; no caller boolean triggers it.
  const automatic=declareControl(el('button','Save automatic review settings'),'review:comment-auto-save');automatic.type='button';automatic.disabled=!!unresolvedReason()||!!draft.recoveryError||!!draft.disagreement||!!draft.conflict;automatic.hidden=!!policy?.id&&policy.mode==='automatic'&&!policyDirty;
  automatic.onclick=act(async()=>{const blocked=unresolvedReason();if(blocked)throw Error(blocked);const action=preview.actions?.policy_save;if(!action?.permitted)throw Error(action?.reason||'Policy recording is unavailable.');if(!preview.policy_request_read)throw Error('The owner supplied no policy request reconciliation.');const payload={...copy(action.payload),project,policy:authoredPolicy('automatic')};const pending=await retainFeedbackSubmission(payload,preview.policy_request_read);if(unresolvedReason())throw Error(UNRESOLVED+' Nothing was sent.');draft.update({policy_pending:pending});if(!draft.persist())throw Error(draft.storageError);await postPolicy();});routing.append(automatic);
  paintPolicyRecovery();
 }
 function keepForm(){draft.update({route_form:authoredPolicy('manual')});buttons();}
 // The held policy request's own recovery is painted wherever this editor holds one, never only inside a preview: the pure
 // Check, the exact retry of the same retained request and the owner-issued settle stay reachable while every new effect
 // refuses through the shared predicate.
 const policyRecovery=el('section','','feedback-policy-recovery');dialog.append(policyRecovery);
 function paintPolicyRecovery(){policyRecovery.replaceChildren();if(!current())return;const held=draft.disagreement||draft.recoveryError?null:draft.snapshot().policy_pending;if(!held)return;
  const add=label=>{const b=el('button',label);b.type='button';policyRecovery.append(b);return b;};
  policyRecovery.append(el('p','A review policy request ('+held.request_id+') is unconfirmed. Check it before any new request; nothing new is sent meanwhile.','muted'));
  add('Check policy submission').onclick=act(checkPolicy);
  if(held.observation==='NONE')add('Retry this exact policy submission').onclick=act(postPolicy);
  if(offeredSettle('policy_pending'))add('Settle this review policy request as never admitted').onclick=act(()=>settleHeld('policy_pending'));}
 async function settlePolicy(value,view=null){const policy=value.policy,held=view?view.held:draft.snapshot().policy_pending,payload=await retainedFeedbackPayload(held);if(view&&!stillCurrent(view))return staleView(view);
  if(!policy?.id||policy.project!==project||policy.work_id!==payload.work_id||policy.request_id!==payload.request_id||['mode','recipients','limits'].some(key=>!sameFeedbackValue(policy[key],payload.policy[key])))throw Error('Policy outcome is not yet established; retain its exact request.');
  if(view){if(!draft.settleCopy({slot:'policy_pending',identity:view.identity,wire:view.wire,basis:view.basis},{policy_receipt:copy(value),route_policy_id:policy.id}))throw Error('The owner recorded this review policy, but this editor could not record that locally: '+(draft.lastWriteError||draft.storageError)+' Nothing is sent again.');}
  else draft.update({policy_pending:null,policy_receipt:copy(value),route_policy_id:policy.id});
  settleActions.policy_pending=null;chosenPolicy=policy.id;paintPolicyRecovery();if(current()&&workPage)await readPreview({work_id:payload.work_id,policy_id:chosenPolicy},{adopt:true});policyDirty=false;buttons();}
 async function postPolicy(){const held=draft.snapshot().policy_pending,payload=await retainedFeedbackPayload(held);draft.update({policy_pending:{...held,observation:'UNKNOWN'}});if(draft.retained!==true)throw Error(draft.storageError||'The review policy request could not be retained; nothing was sent.');paintPolicyRecovery();await settlePolicy(await request('/work/delivery',payload));}
 async function checkPolicy(){
  const view=captureView('policy_pending');if(!view.held)throw Error('No review policy request is held.');
  await draft.payloadOf('policy_pending');if(!stillCurrent(view))return staleView(view);
  const value=await request(await feedbackLookupURL(view.held,view.kind));if(!stillCurrent(view))return staleView(view);
  if(value?.compare){await consumePolicy(view,value);return;}
  if(value.effect==='RECORDED'){await settlePolicy(value,view);return;}
  if(!['NONE','UNKNOWN'].includes(value.effect))throw Error('The policy lookup did not establish the retained request outcome.');
  draft.update({policy_pending:{...view.held,observation:value.effect}});status.textContent='Policy submission '+value.effect.toLowerCase()+'. The original wire and request are retained.';paintPolicyRecovery();}
 async function consumePolicy(view,legacy){const held=view.held,value=await request(await feedbackComparisonURL(held,legacy.compare,'policy_pending'));if(!stillCurrent(view))return staleView(view);
  const outcome=await feedbackRequestOutcome(value,legacy,held,'policy_pending');if(!stillCurrent(view))return staleView(view);
  settleActions.policy_pending=null;
  if(outcome.fields&&outcome.effect==='RECORDED'){await settlePolicy(outcome.receipt_value,view);return;}
  if(outcome.fields){if(!draft.settleCopy({slot:'policy_pending',identity:view.identity,wire:view.wire,basis:view.basis},outcome.fields))throw Error('The owner settled this policy request, but this editor could not record that locally: '+(draft.lastWriteError||draft.storageError)+' Nothing is sent again.');
   status.className='';status.textContent='This review policy request was settled as never admitted. Choose and save review settings again.';paintPolicyRecovery();paintRouting();buttons();return;}
  if(outcome.state==='MISMATCH')throw Error('The owner records another intent under this policy request id; the original is retained.');
  if(outcome.settle)settleActions.policy_pending={identity:view.identity,action:copy(outcome.settle)};
  draft.update({policy_pending:{...held,observation:outcome.state==='UNRECORDED'?'NONE':'UNKNOWN'}});
  status.textContent='Policy submission '+(outcome.state==='UNRECORDED'?'none':'unknown')+'. The original wire and request are retained'+(settleActions.policy_pending?'; you can settle it as never admitted.':'.');paintPolicyRecovery();}
 route.ontoggle=act(async()=>{if(!route.open||workPage)return;const lease=life.lease(),page=await request('/work/state?'+new URLSearchParams({project,view:'summary',limit:'30'}));if(!lease()||!current())return;if(page.project!==project||!Array.isArray(page.tasks))throw Error('The Work owner returned another project or list.');workPage=page;paintRouting();const previous=draft.snapshot().route_work;if(previous)await readPreview({work_id:previous});else paintRouting();});
 buttons();paintRecovery();paintTarget();paintPolicyRecovery();const openGeneration=++prepareGeneration;try{if(draft.disagreement){paintDisagreement();throw Error(draft.storageError);}if(draft.recoveryError){const raw=el('details');raw.append(el('summary','Retained unreadable comment recovery'),el('pre',draft.recoveryRaw.join('\n')));submitted.append(raw);throw Error(draft.recoveryError);}await prepare(openGeneration);}catch(error){if(current()&&openGeneration===prepareGeneration){prepareFailure=error.message;status.textContent=error.message+' Your original comment draft is retained.';status.className='error';}}if(current()&&openGeneration===prepareGeneration){paintRecovery();paintTarget();}buttons();
 if(current()&&readerPlace?.routeOpen){const cached=readerPlace.workSnapshot&&sharedInspector().snapshot(readerPlace.workSnapshot.url,readerPlace.workSnapshot.cut);if(cached?.value?.project===project&&Array.isArray(cached.value.tasks)){workPage=cached.value;paintRouting();}route.open=true;if(!workPage)await route.ontoggle();if(current()&&focusVersion===openingFocus&&(document.activeElement===text||document.activeElement===document.body)){[...routing.querySelectorAll('button')].find(node=>node.textContent===readerPlace.control)?.focus({preventScroll:true});dialog.scrollTop=readerPlace.scroll||0;}}
 return dialog;
}

export async function openFeedbackRouteForOrigin({project,origin,request,isCurrent=()=>true,openProposal=null}){
 const value=await request('/authoring/correction-origin?'+new URLSearchParams({project,origin_ref:JSON.stringify(origin)}));
 if(!isCurrent())return;if(!sameFeedbackValue(value.origin_ref,origin))throw Error('The comment owner returned another saved origin.');
 if(value.review_route_spec?.work_id)return openFeedbackResponses({project,origin,workId:value.review_route_spec.work_id,read:value.review_route_read||null,request,isCurrent,openProposal});
 return openFeedbackComment({project,selection:{anchor:value.correction.anchor},existingOrigin:value,request,isCurrent,openProposal});
}

const reopenWorkReview=args=>openFeedbackWorkReview(args);
export async function openFeedbackWorkReview({project,workId,handle,label,request,isCurrent=()=>true}){
 const path=feedbackHTTP(handle,{project,paths:['/work/state']});if(!isCurrent())return;
 const inspector=sharedInspector(),life=createLifetime(),dialog=el('dialog','','workspace-dialog feedback-route-reader'),heading=el('h2',label),close=el('button','Close review record'),body=el('section'),note=pendingRead(el('p','Reading exact review record…'));let token=null;
 close.type='button';close.onclick=()=>dialog.close();dialog.append(heading,close,note,body);dialog.setAttribute('aria-label',label);dialog.onclose=()=>{life.dispose();dialog.remove();};document.body.append(dialog);token=inspector.adopt(dialog,{kind:'feedback-review-record',title:label,reopen:{factory:reopenWorkReview,args:{project,workId,handle,label,request}}}).token;dialog.showModal();close.focus();
 const current=()=>!life.disposed&&isCurrent(),lineage=()=>isCurrent()&&inspector.lineage(token)();
 function history(page,list){for(const item of page?.items||[]){const open=el('button',[item.phase,item.verdict,item.actor?.actor,item.ts].filter(Boolean).join(' · '));open.type='button';open.onclick=()=>openFeedbackWorkReview({project,workId,handle:item.read,label:'Exact review phase',request,isCurrent:lineage});list.append(open);}}
 try{const value=admitWorkReviewRecord({project,workId},handle,await request(path));if(!current())return dialog;
  note.textContent='Exact saved review record; Work acceptance and manuscript effects remain separate.';renderWorkReviewPhaseRows(body,value);
  if(value.obligation){body.append(el('h3',value.obligation.label||value.obligation.id),el('p','Declared inputs: '+(value.obligation.inputs||[]).join(', '),'muted'));const list=el('div','','feedback-route-actions');body.append(list);history(value.history,list);if(!value.history?.items?.length)body.append(el('p','No review phase has been recorded for this obligation yet.','muted'));
   let next=value.history?.next_read;const more=el('button','More review history');more.type='button';more.hidden=!next;more.onclick=async()=>{if(!current()||!next)return;more.disabled=true;const asked=next;try{const page=admitWorkReviewRecord({project,workId},asked,await request(feedbackHTTP(asked,{project,paths:['/work/state']})));if(!current()||asked!==next)return;history(page.history,list);next=page.history?.next_read;more.hidden=!next;}catch(error){if(current()){note.textContent=error.message+' Earlier review records are retained.';note.className='error';}}finally{more.disabled=false;}};body.append(more);
  }
 }catch(error){if(current()){note.textContent=error.message;note.className='error';}}return dialog;
}
