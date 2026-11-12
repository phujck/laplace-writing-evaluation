// Native research doors reuse the existing exact message, source and proposal
// interpreters. The shared inspector alone owns Close/Back and opener return.
import {sharedInspector} from './workspace-inspector.mjs';
import {mountMessageReading,messageReadURL} from './conversation-reading.mjs';
import {renderMaterialObservation} from './workspace-material-observation.mjs';
import {intakeDocumentReadURL} from './local-document-intake-port.mjs';
import {proposalReadURL,selectedProposalBody,proposalStepHeading} from './manuscript-editing.mjs';
import {projectRequest} from './writing-request.mjs';
import {el,button,details,textBody} from './research-workbench-view.mjs';
const copy=value=>structuredClone(value);
function dialog(title){const node=el('dialog','','workspace-dialog rw-dialog');node.setAttribute('aria-label',title);const close=button('Close '+title.toLowerCase(),()=>node.close()),heading=el('h2',title),body=el('div'),status=el('p','','rw-status');status.setAttribute('role','status');status.tabIndex=-1;node.append(heading,close,status,body);document.body.append(node);return {node,close,body,status};}
function reopenMessage(args){return openResearchMessage(args);}
export async function openResearchMessage({handle,title='Complete response',request=projectRequest,isCurrent=()=>true}={}){
  const target=copy(handle?.identity);messageReadURL(handle,target);const inspector=sharedInspector(),view=dialog(title);let alive=true,reader;
  const token=inspector.adopt(view.node,{kind:'owner-read',title,reopen:{factory:reopenMessage,args:{handle:copy(handle),title,request}}}).token,current=()=>alive&&isCurrent()&&inspector.current?.token===token;
  view.node.onclose=()=>{alive=false;reader?.dispose();view.node.remove();};view.node.showModal();view.close.focus();
  const row=el('section'),body=el('div','','session-body rw-recorded');row.append(body);view.body.append(row);
  reader=mountMessageReading(row,{target,request,initialRead:handle,isCurrent:current,storage:globalThis.sessionStorage,changed:write=>{if(current())write();}});await reader.open();return view.node;
}
function reopenSource(args,pin){return openResearchSource({...args,handle:pin?.handle||args.handle});}
export async function openResearchSource({project,artifactId,sha256,handle,title='Carried source',request=projectRequest,isCurrent=()=>true}={}){
  const path=intakeDocumentReadURL(handle,{project,artifactId,sha256}),inspector=sharedInspector(),view=dialog(title);let alive=true,reading;
  const token=inspector.adopt(view.node,{kind:'owner-read',title,reopen:{factory:reopenSource,args:{project,artifactId,sha256,handle:copy(handle),title,request}}}).token,current=()=>alive&&isCurrent()&&inspector.current?.token===token;
  view.node.onclose=()=>{alive=false;reading?.destroy();view.node.remove();};view.node.showModal();view.close.focus();
  try{const value=await request(path);if(!current())return;reading=renderMaterialObservation(view.body,value,{documentLabel:title,request,isCurrent:current,initialHandle:handle,onObservation:row=>inspector.pin(token,{handle:copy(row.page_read||handle)})});}
  catch(error){if(current())view.status.textContent=error.message;}return view.node;
}
function reopenProposal(args){return openResearchProposal(args);}
export async function openResearchProposal({project,handle,title='Manuscript proposal',request=projectRequest,isCurrent=()=>true,applyAction=null,onApply=null}={}){
  const raw=new URL(handle?.http?.url||'',globalThis.location?.href||'http://local/'),turnId=raw.searchParams.get('id')||raw.searchParams.get('turn_id'),version=raw.searchParams.get('proposal_version');
  const path=proposalReadURL(handle,{project,turnId,version}),inspector=sharedInspector(),view=dialog(title);let alive=true;
  const token=inspector.adopt(view.node,{kind:'owner-read',title,reopen:{factory:reopenProposal,args:{project,handle:copy(handle),title,request}}}).token,current=()=>alive&&isCurrent()&&inspector.current?.token===token;
  view.node.onclose=()=>{alive=false;view.node.remove();};view.node.showModal();view.close.focus();
  try{const summary=await request(path);if(!current())return;if(summary.turn_id!==turnId||summary.proposal_version!==version)throw Error('The proposal owner returned another saved candidate.');
    view.body.append(el('p','Inspect the exact proposed source changes. Review acceptance and human manuscript application remain separate.','rw-qualification'));
    const navigation=summary.navigation_edits||summary.edits||[];
    for(const edit of summary.edits||[]){const card=el('section','','rw-card'),label=proposalStepHeading({...summary,navigation_edits:navigation},edit.edit_id,{file:edit.file});card.append(el('h3',label.eyebrow));if(edit.status)card.append(el('p',String(edit.status).replaceAll('_',' '),'rw-qualification'));if(edit.reason)textBody(card,edit.reason);
      const text=el('div');card.append(text);let ticket=0;
      const show=selected=>{text.replaceChildren(el('h4','Before'),el('pre',selected.before??selected.current_before??'', 'rw-recorded'),el('h4','Proposed'),el('pre',selected.after??selected.proposed??'', 'rw-recorded'));};
      if(typeof edit.before==='string'&&typeof edit.after==='string')show(edit);
      else{const read=edit.preview_read||edit.read_handle;if(read)card.append(button('Read complete change',async()=>{const mine=++ticket;try{const value=await request(proposalReadURL(read,{project,turnId,version,editId:edit.edit_id}));if(current()&&mine===ticket)show(selectedProposalBody(summary,value,edit.edit_id).edits[0]);}catch(error){if(current()&&mine===ticket)view.status.textContent=error.message;}}));else card.append(el('p','The owner has not supplied this change body.','rw-qualification'));}
      card.append(details('Exact edit standing and read basis',edit,{isCurrent:current}));view.body.append(card);
    }
    if(applyAction&&onApply&&applyAction.permitted===true&&applyAction.http?.payload?.turn_id===turnId&&applyAction.http.payload.proposal_version===version)view.body.append(button(applyAction.title||'Apply reviewed manuscript proposal',async()=>{if(!current())return;view.status.textContent='Keeping the original application request…';view.status.focus();try{const outcome=await onApply(copy(applyAction));if(current())view.status.textContent=outcome||'Inspect the original application outcome before another decision.';}catch(error){if(current())view.status.textContent=error.message;}},{primary:true}));
    view.body.append(details('Candidate identity and currentness',summary,{isCurrent:current}));
  }catch(error){if(current())view.status.textContent=error.message;}return view.node;
}

export async function openResearchReceipt({project,handle,title='Recorded workflow action',request=projectRequest,isCurrent=()=>true}={}){
  const url=new URL(handle?.http?.url||'',globalThis.location?.href||'http://local/');let original;try{original=JSON.parse(url.searchParams.get('request')||'null');}catch{}
  if(handle?.http?.method!=='GET'||url.origin!==new URL(globalThis.location?.href||'http://local/').origin||url.pathname!=='/work/delivery'||url.searchParams.get('project')!==project||!['workflow-bind-request','workflow-request'].includes(original?.action)||!original.work_id||!original.request_id)throw Error('This is not an exact issued workflow request read.');
  const inspector=sharedInspector(),view=dialog(title);let alive=true;const token=inspector.adopt(view.node,{kind:'owner-read',title}).token,current=()=>alive&&isCurrent()&&inspector.current?.token===token;
  view.node.onclose=()=>{alive=false;view.node.remove();};view.node.showModal();view.close.focus();
  try{const value=await request(url.pathname+url.search);if(!current())return;if(value.project!==project||value.work_id!==original.work_id||value.request_id!==original.request_id)throw Error('The owner returned a receipt for another request.');
    view.body.append(el('h3',value.effect==='RECORDED'?'Original action recorded':value.effect==='NONE'?'Original request not observed':'Original request unresolved'));
    if(value.receipt?.binding){const row=value.receipt.binding;view.body.append(el('p',row.label||String(row.effect||row.role||'Approved recipient').replaceAll('-',' ')),el('p',[row.provider,row.model,row.effort].filter(Boolean).join(' · ')));if(row.expires_at)view.body.append(el('p','Approval expires '+row.expires_at));}
    if(value.receipt?.action)view.body.append(el('p','Recorded decision: '+value.receipt.action.replace(/^workflow-/,'').replaceAll('-',' ')));
    view.body.append(el('p','This receipt identifies the original decision. Inspect the current run for progress, review and manuscript application.','rw-qualification'),details('Exact original receipt',value,{isCurrent:current}));
  }catch(error){if(current())view.status.textContent=error.message;}return view.node;
}

// The same bounded source-body envelope used in Evidence & inputs, in the
// existing neutral inspector so inspecting a preparation target keeps its form.
export async function openResearchSourceWindow({handle,title='Selected manuscript source',scopeId,request=projectRequest,isCurrent=()=>true}={}){
  const {checkedFacets,checkedReference,equal}=await import('./research-workbench-state.mjs');
  const here=new URL(globalThis.location?.href||'http://local/'),first=new URL(handle?.http?.url||'',here);let reference;try{reference=checkedReference(JSON.parse(first.searchParams.get('reference')||'null'));}catch{throw Error('This manuscript has no issued source reference.');}
  const pin=first.searchParams.get('as_of');if(reference.owner!=='domain.projects'||reference.kind!=='source-file'||!/^sha256:[a-f0-9]{64}$/.test(pin||''))throw Error('Inspect a pinned source-file window issued by its owner.');
  function urlFor(read){const url=new URL(read?.http?.url||'',here);let subject;try{subject=JSON.parse(url.searchParams.get('reference')||'null');}catch{}if(read?.http?.method!=='GET'||url.origin!==here.origin||url.pathname!=='/work/discovery'||url.searchParams.get('facet')!=='object'||url.searchParams.get('section')!=='body'||url.searchParams.get('as_of')!==pin||!equal(subject,reference))throw Error('The manuscript window changed its issued source or pin.');return url.pathname+url.search;}
  urlFor(handle);const inspector=sharedInspector(),view=dialog(title);let alive=true,ticket=0;
  const token=inspector.adopt(view.node,{kind:'owner-read',title,reopen:{factory:reopenSourceWindow,args:{handle:copy(handle),title,scopeId,request}}}).token,current=()=>alive&&isCurrent()&&inspector.current?.token===token;
  view.node.onclose=()=>{alive=false;ticket++;view.node.remove();};view.node.showModal();view.close.focus();
  async function readWindow(read){const mine=++ticket;try{const value=checkedFacets(await request(urlFor(read)),{reference,view:'object'});if(!current()||mine!==ticket)return;if(value.scope_id!==scopeId||value.basis!==pin)throw Error('The manuscript window belongs to another workspace or changed source.');const page=value.items?.find(row=>typeof row.content==='string');if(!page||!Number.isSafeInteger(page.offset)||!Number.isSafeInteger(page.end)||!Number.isSafeInteger(page.total_characters)||page.end-page.offset!==Array.from(page.content).length||page.end>page.total_characters)throw Error('The source owner returned an incomplete window extent.');
      view.body.replaceChildren(el('h3',value.facets.purpose.value.title||title),el('p','Characters '+page.offset+'–'+page.end+' of '+page.total_characters+(page.offset===0&&page.end===page.total_characters?' · complete source in this reading':' · selected window; other text remains uninspected'),'rw-qualification'),el('pre',page.content,'rw-recorded'));
      inspector.pin(token,{handle:copy(read)});if(value.pagination?.next_read)view.body.append(button('Read next source window',()=>readWindow(value.pagination.next_read)));view.body.append(details('Exact source and observed basis',{reference,basis:value.basis,scope:value.scope,coverage:value.coverage},{isCurrent:current}));view.status.textContent='';
    }catch(error){if(current()&&mine===ticket)view.status.textContent=error.message;}}
  await readWindow(handle);return view.node;
}
function reopenSourceWindow(args,pin){return openResearchSourceWindow({...args,handle:pin?.handle||args.handle});}

// Exact existing Work phase reader, with the same owner reply admission and
// human phase renderer used by the canonical Work surface.
export async function openResearchReview({project,workId,handle,title='Recorded independent review',request=projectRequest,isCurrent=()=>true}={}){
  const url=new URL(handle?.http?.url||'',globalThis.location?.href||'http://local/'),want=handle?.payload;
  if(handle?.http?.method!=='GET'||url.origin!==new URL(globalThis.location?.href||'http://local/').origin||url.pathname!=='/work/state'||url.searchParams.get('project')!==project||url.searchParams.get('view')!=='review'||url.searchParams.get('id')!==workId||!url.searchParams.get('phase_id')||want?.phase_id!==url.searchParams.get('phase_id')||want.id!==workId||want.view!=='review'||want.namespace!==project)throw Error('This is not the exact issued Work review phase.');
  const {admitWorkReviewRecord,renderWorkReviewPhaseRows}=await import('./workspace-work-review.mjs');if(!isCurrent())return;
  const inspector=sharedInspector(),view=dialog(title);let alive=true;const token=inspector.adopt(view.node,{kind:'owner-read',title}).token,current=()=>alive&&isCurrent()&&inspector.current?.token===token;
  view.node.onclose=()=>{alive=false;view.node.remove();};view.node.showModal();view.close.focus();
  try{const value=await request(url.pathname+url.search);if(!current())return;admitWorkReviewRecord({project,workId},handle,value);renderWorkReviewPhaseRows(view.body,value);view.body.append(el('p','Recorded review evidence is separate from manuscript Apply and scientific acceptance.','rw-qualification'));}catch(error){if(current())view.status.textContent=error.message;}return view.node;
}

// Delivery coordinates stay local to their exact Work. A recorded response,
// current scoped acceptance and parent return are separate owner observations.
export async function openResearchDelivery({project,workId,eventId,handle,title='Recorded delivery',request=projectRequest,isCurrent=()=>true}={}){
  const here=new URL(globalThis.location?.href||'http://local/'),url=new URL(handle?.http?.url||'',here);let payload;try{payload=JSON.parse(url.searchParams.get('request')||'null');}catch{}
  if(handle?.http?.method!=='GET'||url.origin!==here.origin||url.pathname!=='/work/delivery'||url.searchParams.get('project')!==project||payload?.action!=='status'||payload.event_id!==eventId||Object.keys(payload).some(k=>!['action','event_id'].includes(k))||!workId)throw Error('This is not the issued delivery event read for the selected Work.');
  const inspector=sharedInspector(),view=dialog(title);let alive=true;const token=inspector.adopt(view.node,{kind:'owner-read',title,reopen:{factory:openResearchDelivery,args:{project,workId,eventId,handle:copy(handle),title,request}}}).token,current=()=>alive&&isCurrent()&&inspector.current?.token===token;
  view.node.onclose=()=>{alive=false;view.node.remove();};view.node.showModal();view.close.focus();
  try{const result=await request(url.pathname+url.search);if(!current())return;const event=result?.event;if(event?.id!==eventId)throw Error('The delivery owner returned another event.');
    let workflow=false;if(event.work_id===undefined&&event.event_id===eventId&&event.binding?.work_id===workId){try{const read=new URL(event.read?.http?.url||'',here),target=JSON.parse(read.searchParams.get('request')||'null');workflow=event.read.http.method==='GET'&&read.origin===here.origin&&read.pathname==='/work/delivery'&&read.searchParams.get('project')===project&&target?.action==='workflow-status'&&target.work_id===workId;}catch{}}
    const generic=event.event_id===undefined&&event.work_id===workId&&event.recipient&&typeof event.recipient==='object'&&!Array.isArray(event.recipient);if(!generic&&!workflow)throw Error('The delivery owner returned another event or Work.');
    const recipient=workflow?event.binding:event.recipient,coordinates=workflow?{session_id:event.session_id,turn_id:event.turn_id}:event.admitted,labels={RESULT:'Response received',ADMITTED:'Recipient admitted',SUBMITTED:'Intent recorded; admission needs inspection',RESERVED:'Recipient preparation recorded',STALE:'Recorded input basis changed',UNCONFIRMED:'Admission not confirmed'};
    view.body.append(el('h3',recipient.label||String(event.effect||recipient.role||'Recorded recipient').replaceAll('-',' ')),el('p',labels[event.state]||String(event.state||'Standing unavailable').replaceAll('_',' '),'rw-standing'),el('p',[recipient.provider,recipient.model,recipient.effort].filter(Boolean).join(' · ')),el('p','Response receipt, scoped review acceptance, manuscript application and scientific judgement remain separate.','rw-qualification'));
    if(event.reason)textBody(view.body,event.reason,'rw-alert');if(event.last_error||event.error)textBody(view.body,event.last_error||event.error,'rw-alert');if(typeof event.running==='boolean')view.body.append(el('p',event.running?'Owner observes this recipient running.':'Owner does not currently observe this recipient running.','rw-qualification'));
    if(event.public_reply_read&&(event.public_reply_read.identity?.project!==project||event.public_reply_read.identity?.turn_id!==coordinates?.turn_id||event.public_reply_read.identity?.session_id!==coordinates?.session_id))throw Error('The response handle does not identify this admitted recipient.');
    if(event.public_reply_read)view.body.append(button('Read complete response',()=>{if(current())return openResearchMessage({handle:event.public_reply_read,title:'Complete recipient response',request,isCurrent});}));
    if(event.turn_read&&coordinates?.turn_id)view.body.append(button('Inspect saved recipient turn',async()=>{if(!current())return;const {openSavedTurn}=await import('./workspace-material.mjs');if(!current())return;return openSavedTurn({project,turnId:coordinates.turn_id,ownerRead:event.turn_read,request,isCurrent});}));
    if(workflow&&event.proposal_read)view.body.append(button('Inspect recipient proposal',()=>{if(current())return openResearchProposal({project,handle:event.proposal_read,request,isCurrent});}));
    const acceptance=event.acceptance;if(acceptance){view.body.append(el('h3','Scoped review standing'),el('p',String(acceptance.status||'Not reported').replaceAll('_',' ')),el('p','Currentness: '+String(acceptance.currentness||'Not reported').replaceAll('_',' ')));if(acceptance.currentness_reason)textBody(view.body,acceptance.currentness_reason,'rw-qualification');if(acceptance.independence)view.body.append(el('p','Recorded independence: '+acceptance.independence));}
    if(event.parent_return)view.body.append(el('h3','Return to original parent'),el('p',event.parent_return.state?String(event.parent_return.state).replaceAll('_',' '):'No return state is reported.','rw-qualification'));
    view.body.append(details('Exact delivery, captured approval and current owner facts',event,{isCurrent:current}));
  }catch(error){if(current())view.status.textContent=error.message;}return view.node;
}
