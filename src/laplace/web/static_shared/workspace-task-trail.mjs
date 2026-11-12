// Task outcomes over issued owner reads. No body fanout or inferred work/session
// binding; the shared inspector owns nested reading and explicit return.
import {sharedInspector} from './workspace-inspector.mjs';
import {qualifiedOwnerHTTP,artifactHumanTarget} from './writing-owner-read.mjs';
import {messageReadURL} from './conversation-reading.mjs';
import {inspectorReturnFocus} from './workspace-returns.mjs';
import {projectRequest} from './writing-request.mjs';
import {pendingRead} from './pending-read.mjs';
const PIN=/^sha256:[a-f0-9]{64}$/,clone=v=>structuredClone(v);
const stable=v=>Array.isArray(v)?v.map(stable):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,stable(v[k])])):v;
const key=v=>JSON.stringify(stable(v));
const el=(tag,text='',cls='')=>{const n=document.createElement(tag);n.textContent=text??'';n.className=cls;return n;};
const button=(label,run)=>{const n=el('button',label,'act act-read');n.type='button';n.onclick=run;return n;};
const human=v=>String(v??'not reported').toLowerCase().replaceAll('_',' ').replaceAll('-',' ');
export function taskTrailURL(handle,{namespace,workId}={}){
 const q=qualifiedOwnerHTTP(handle,namespace);
 if(q?.owner?.kind!=='work-provenance'||q.owner.id!==workId||handle.operation!=='project'||(handle.payload?.namespace??handle.payload?.project)!==namespace)throw Error('This is not an issued evidence read for the selected task.');return q.url;
}
export function admitTaskTrail(value,handle,{namespace,workId}={}){
 taskTrailURL(handle,{namespace,workId});const wanted=handle.payload.request;
 if(value?.schema_version!=='laplace.work-provenance/1'||value.read_only!==true||value.work?.namespace!==namespace||value.work?.id!==workId||!PIN.test(value.observation?.token||'')||value.caller_scope?.kind==='project'&&value.caller_scope.namespace!==namespace)throw Error('The evidence response belongs to another task, project or observation.');
 if(!value.counts||['relationships','direct_evidence','bound_turns'].some(k=>!Number.isSafeInteger(value.counts[k])||value.counts[k]<0)||value.counts.bound_turns>value.counts.relationships)throw Error('The selected owner counts are incomplete.');
 if(wanted.as_of&&wanted.as_of!==value.observation.token)throw Error('The recorded inputs changed. Read a fresh task summary explicitly.');
 if(wanted.demand!=='aggregate'){
  const p=value.pagination,rows=value.items;
  if(!p||!Array.isArray(rows)||p.offset!==(wanted.offset??0)||!Number.isSafeInteger(p.limit)||p.limit<1||p.limit>(wanted.limit??6)||!Number.isSafeInteger(p.total)||!Number.isSafeInteger(p.covered)||p.covered<rows.length||p.covered>p.limit||p.offset+p.covered>p.total)throw Error('The evidence page does not match its issued window.');
  if(p.next_read){taskTrailURL(p.next_read,{namespace,workId});const r=p.next_read.payload.request;if(r.demand!==wanted.demand||r.as_of!==value.observation.token||r.offset!==p.offset+p.covered||r.offset<=p.offset)throw Error('The evidence continuation leaves this observation.');}
 }
 return value;
}
export function admitTaskArtifact(row,namespace){
 const target=artifactHumanTarget(row.read?.http?.url,{project:namespace}),pin=x=>String(x||'').replace(/^sha256:/,'');
 if(row.read?.http?.method!=='GET'||!target||row.project!==namespace||row.target?.project&&row.target.project!==namespace||target.artifactId!==row.artifact_id||row.target?.artifact_id&&row.target.artifact_id!==row.artifact_id||target.path!==row.path||target.scope!==row.scope||pin(target.expectedSha256)!==pin(row.expected_sha256)||!pin(row.expected_sha256))throw Error('The recorded artifact read changes its exact project, scope, item or content pin.');return target;
}
export function taskChildURL(read,row,{namespace,workId}={}){
 const base=new URL(globalThis.location?.href||'http://local/'),u=new URL(read?.http?.url||'',base),q=u.searchParams;
 if(read?.http?.method!=='GET'||read.project!==undefined&&read.project!==namespace||u.origin!==base.origin||u.hash||[...q.keys()].some(k=>q.getAll(k).length!==1)||q.get('project')!==namespace)throw Error('The selected evidence read leaves this project.');
 const coordinate=row.owner_target,pinValue=v=>String(v||'').replace(/^sha256:/,'');
 if(coordinate){
  if(coordinate.project!==namespace)throw Error('The evidence owner coordinate leaves the selected project.');
  if(coordinate.kind==='project-file'){const target=artifactHumanTarget(read.http.url,{project:namespace});if(!target||target.path!==coordinate.path||target.scope!==coordinate.scope||coordinate.expected_sha256&&pinValue(target.expectedSha256)!==pinValue(coordinate.expected_sha256))throw Error('The read does not match its exact owner file coordinate.');}
  else if(coordinate.kind==='material-source'){const owner=qualifiedOwnerHTTP(read,namespace)?.owner;let target;try{target=JSON.parse(q.get('target'));}catch{}if(read.operation!==undefined&&read.operation!=='material_references'||read.payload&&(['view','offset','limit'].some(k=>read.payload[k]!==undefined&&String(read.payload[k])!==q.get(k)))||owner?.kind!=='material-source'||key(target)!==key(coordinate.target)||key(read.payload?.target)!==key(coordinate.target)||coordinate.expected_sha256&&pinValue(q.get('expected_sha256'))!==pinValue(coordinate.expected_sha256)||read.payload?.expected_sha256!==undefined&&pinValue(read.payload.expected_sha256)!==pinValue(q.get('expected_sha256')))throw Error('The Source read changes its exact owner target or consumed pin.');}
  else throw Error('Unsupported evidence owner coordinate.');
 }
 if(u.pathname==='/research/artifact'){
  const target=artifactHumanTarget(read.http.url,{project:namespace}),payload=read.payload,expected=row.consumed_revision||row.reference?.expected_sha256||row.expected_sha256,pin=v=>String(v||'').replace(/^sha256:/,'');
  if(!target||expected&&pin(target.expectedSha256)!==pin(expected)||row.reference?.id&&target.artifactId!==row.reference.id||row.reference?.path&&(target.path!==row.reference.path||target.scope!==row.reference.scope))throw Error('The evidence read changes its recorded content, item or scope.');
  if(read.operation){if(read.operation!=='read_artifact'||!payload||Object.keys(payload).some(k=>!['path','scope','id','expected_sha256'].includes(k))||payload.path!==undefined&&payload.path!==target.path||payload.scope!==undefined&&payload.scope!==target.scope||payload.id!==undefined&&payload.id!==target.artifactId||payload.expected_sha256!==undefined&&pin(payload.expected_sha256)!==pin(target.expectedSha256))throw Error('The artifact read companions disagree.');}
 }else if(u.pathname==='/work/state'&&['review-phase','source-basis'].includes(row.kind)){
  const t=qualifiedOwnerHTTP(read,namespace);if(t?.owner?.kind!=='work-review-phase'||t.owner.id!==workId||t.owner.read_handle.payload.phase_id!==row.target?.phase_id||row.target?.work_id!==workId)throw Error('The review read names another task or phase.');
 }else if(u.pathname==='/research/run/status'){
  if(read.operation!=='run_status'||read.payload?.id!==q.get('id')||row.reference?.id&&row.reference.id!==q.get('id')||[...q.keys()].some(k=>!['project','id'].includes(k)))throw Error('The run read names another result.');
 }else if(u.pathname==='/work/delivery'){
  let payload;try{payload=JSON.parse(q.get('request'));}catch{}if(payload?.action!=='status'||payload.event_id!==row.target?.event_id||row.target?.work_id!==workId)throw Error('The delivery read names another event or task.');
 }else if(u.pathname==='/authoring/session-turn'){
  if(q.get('id')!==row.target?.turn_id||!['turn','summary'].includes(q.get('view')))throw Error('The saved turn read names another turn.');
 }else if(!qualifiedOwnerHTTP(read,namespace)&&!artifactHumanTarget(read.http.url,{project:namespace}))throw Error('This exact evidence owner has no compatible human reader.');
 return u.pathname+u.search;
}
function reopen(args,pin){return openTaskTrail({...args,handle:pin?.handle||args.handle,returnFocus:pin?.focusKey||null,expectedObservation:pin?.observation||null});}
export async function openTaskTrail({handle,namespace,workId,request=projectRequest,isCurrent=()=>true,returnFocus=null,expectedObservation=null,onConversation=null,rootReturn=null}={}){
 if(!isCurrent())return null;const url=taskTrailURL(handle,{namespace,workId}),inspector=sharedInspector(),node=el('dialog','','workspace-dialog source-inspector-dialog task-trail-dialog'),heading=el('h2','What led here'),close=button('Close',()=>node.close()),status=el('p','','work-status'),body=el('div');status.setAttribute('role','status');node.setAttribute('aria-label','Task evidence and history');node.dataset.control='task:trail';node.append(heading,close,status,body);document.body.append(node);
 let alive=true,focusKey=returnFocus,observation=expectedObservation,readingHandle=clone(handle);const args={handle:clone(handle),namespace,workId,request,isCurrent,onConversation};
 const token=inspector.adopt(node,{kind:'owner-read',title:'What led here',reopen:{factory:reopen,args},returnFocus:rootReturn}).token,current=()=>alive&&isCurrent()&&inspector.current?.token===token;
 node.onclose=()=>{alive=false;focus.dispose();node.remove();};node.showModal();close.focus();const focus=inspectorReturnFocus({dialog:node,close,key:returnFocus,attribute:'data-task-trail-key',isCurrent:current});
 const pin=()=>inspector.pin(token,{handle:clone(readingHandle),focusKey,observation});
 const link=(host,label,read,run=null)=>{const b=button(label,async()=>{if(!current())return;focusKey=key([label,read]);pin();try{if(run)await run();else await openTaskTrail({...args,handle:read,isCurrent:inspector.lineage(token)});}catch(error){if(current())status.textContent=error.message;}});b.setAttribute('data-task-trail-key',key([label,read]));host.append(b);return b;};
 try{
  let value=admitTaskTrail(await request(url),readingHandle,{namespace,workId});if(!current())return node;
  if(readingHandle.payload.request.demand==='aggregate'&&value.reads?.relationships){const next=value.reads.relationships;if(next.payload?.request?.demand!=='relationships'||next.payload.request.as_of!==value.observation.token)throw Error('The owner did not bind the history page to this task observation.');readingHandle=clone(next);value=admitTaskTrail(await request(taskTrailURL(next,{namespace,workId})),next,{namespace,workId});if(!current())return node;}

  if(observation&&value.observation.token!==observation)throw Error('The previous task evidence changed. No held page has been mixed with new facts.');observation=value.observation.token;heading.textContent=value.work.title||'What led here';body.append(el('p','What led here','operator-eyebrow'),el('p',value.work.purpose||''),el('p','Recorded task status: '+human(value.work.recorded_status)+'. Current completion checks and observed activity stay separate.','muted'));
  const demand=readingHandle.payload.request.demand;
  const navigation=el('nav','','task-trail-navigation');if(demand!=='evidence'&&value.reads?.evidence)link(navigation,'Completion evidence and availability',value.reads.evidence);if(value.reads?.review)link(navigation,'Review outcomes',value.reads.review,async()=>{const {openReviewEvidence}=await import('./workspace-review-evidence.mjs');if(current())return openReviewEvidence({handle:value.reads.review,namespace,workId,request,isCurrent:inspector.lineage(token)});});body.append(navigation);
  const completed=['done','verified'].includes(value.work.recorded_status);if(value.support?.state==='NOT_DECLARED')body.append(el('p',completed?'No retained-support manifest was declared for the recorded completion. Direct completion checks stay separate.':'No retained-support manifest has been declared for this task. Adding evidence and marking Done are separate explicit actions.','muted'));
  if(demand==='aggregate'){
   body.append(el('h3','Recorded history and results'),el('p',`${value.counts.relationships} recorded links · ${value.counts.bound_turns} bound conversation turns · ${value.counts.direct_evidence} direct completion items`));
  }else{
   body.append(el('h3',demand==='relationships'?'Recorded history':demand==='evidence'?'Completion evidence':'Admitted evidence choices'));
   if(value.direct_completion)body.append(el('p','Direct completion: '+human(value.direct_completion.status||value.direct_completion.currentness)),el('p',value.direct_completion.reason||''));
   if(demand==='evidence')body.append(el('p','Supporting evidence: '+human(value.support?.state)+' · separate from the task’s direct completion standing.','muted'));
   if(!(value.items||[]).length)body.append(el('p','No items were returned on this page. Coverage and unavailable records remain qualified below.'));
   for(const row of value.items||[]){const card=el('section','','task-trail-item'),file=row.path||row.target?.path,title=file?file.split('/').at(-1):row.title||row.session_title||(row.kind==='conversation-turn'?'Conversation response':row.kind==='review-phase'?'Review outcome':row.kind==='source-basis'?'Source basis':row.kind==='delivery-event'?'Recipient response':row.role||row.label||'Linked item');card.append(el('h4',title));const state=row.availability==='PRESENT'?'Available':row.availability==='CHANGED'?'Changed since its saved pin':row.availability==='MISSING'||row.availability==='UNAVAILABLE'||row.state==='UNAVAILABLE'?'Unavailable':row.state==='ASSOCIATED'?'Linked to this task':row.state==='RECORDED'?'Saved record':row.currentness==='NOT_CHECKED'?'Content not checked':human(row.state||row.availability);card.append(el('p',state,'task-trail-state'));if(row.recorded_at)card.append(el('p','Recorded '+new Date(row.recorded_at).toLocaleString(),'muted'));if(row.reason)card.append(el('p',row.reason));if(row.kind==='direct-completion-evidence'&&!row.consumed_revision)card.append(el('p','No retained content identity was recorded for this association. Opening checks the current owner file; it does not recover an earlier body.','muted'));
    if(row.reply_read){messageReadURL(row.reply_read,{project:namespace,session_id:row.target?.session_id,turn_id:row.target?.turn_id,part:'reply'});link(card,'Read reply',row.reply_read,async()=>{const {openResearchMessage}=await import('./research-workbench-readers.mjs');if(current())return openResearchMessage({handle:row.reply_read,title:'Saved task reply',request,isCurrent:inspector.lineage(token)});});}
    if(row.conversation_read&&onConversation){link(card,'Open conversation',row.conversation_read,async()=>{const read=row.conversation_read,u=new URL(read.http?.url||'',globalThis.location?.href||'http://local/');if(read.http?.method!=='GET'||u.pathname!=='/authoring/session'||u.searchParams.get('project')!==namespace||u.searchParams.get('id')!==row.target?.session_id)throw Error('The conversation link leaves its recorded target.');const value=await request(u.pathname+u.search);if(!current())return;if(value.session?.id!==row.target.session_id||value.session?.project!==namespace)throw Error('The owner returned another conversation.');inspector.closeTo(token,()=>onConversation(value.session.id));});}
    if(row.kind==='artifact-receipt'&&row.read){admitTaskArtifact(row,namespace);link(card,'Read file',row.read,async()=>{const {openArtifact}=await import('./writing-artifact.mjs');if(current())return openArtifact({project:namespace,...admitTaskArtifact(row,namespace),label:row.label,request,isCurrent:inspector.lineage(token)});});if(row.historical_body==='NOT_ASSERTED')card.append(el('p','The receipt is historical. Available bytes are checked on opening; historical body custody is not asserted.','muted'));}
    else if(row.read&&!row.reply_read){taskChildURL(row.read,row,{namespace,workId});link(card,row.kind==='conversation-turn'?'Read summary':row.kind==='review-phase'?'Read review':row.kind==='source-basis'?'Read Source basis':row.kind==='declared-support'&&row.owner==='research-run-output'?'Read run':'Read linked evidence',row.read,async()=>{
      if(row.kind==='conversation-turn'){const {openSavedTurn}=await import('./workspace-material.mjs');if(current())return openSavedTurn({project:namespace,turnId:row.target.turn_id,ownerRead:row.read,request,replyUnavailable:!row.reply_read,allowConversation:!!onConversation,...(onConversation?{onConversation}:{}),isCurrent:inspector.lineage(token)});}
      if(['review-phase','source-basis'].includes(row.kind)){const {openResearchReview}=await import('./research-workbench-readers.mjs');if(current())return openResearchReview({project:namespace,workId,handle:row.read,title:row.label,request,isCurrent:inspector.lineage(token)});}
      if(row.kind==='delivery-event'){const {openResearchDelivery}=await import('./research-workbench-readers.mjs');if(current())return openResearchDelivery({project:namespace,workId,eventId:row.target.event_id,handle:row.read,title:row.label,request,isCurrent:inspector.lineage(token)});}
      if(new URL(row.read.http.url,globalThis.location?.href||'http://local/').pathname==='/research/run/status')return openTaskRun({row,namespace,workId,request,isCurrent:inspector.lineage(token)});
      const {openArtifact}=await import('./writing-artifact.mjs'),artifact=artifactHumanTarget(row.read.http.url,{project:namespace});if(current())return openArtifact({project:namespace,...(artifact?artifact:{ownerRead:row.read}),label:row.label,request,isCurrent:inspector.lineage(token)});
    });}
    if(row.current_read){const currentRow={...row,consumed_revision:null,owner_target:row.owner_target?{...row.owner_target,expected_sha256:null}:null};taskChildURL(row.current_read,currentRow,{namespace,workId});link(card,'Read current source separately',row.current_read,async()=>{const {openArtifact}=await import('./writing-artifact.mjs');if(current())return openArtifact({project:namespace,ownerRead:row.current_read,label:'Current source · separate from recorded evidence',notice:'Current owner bytes. The original completion evidence and its consumed pin are unchanged.',request,isCurrent:inspector.lineage(token)});});}
    const exact=el('details');exact.append(el('summary','Exact record and reading basis'));exact.ontoggle=()=>{if(exact.open&&current()){exact.querySelector('pre')?.remove();exact.append(el('pre',JSON.stringify(row,null,2)));}};card.append(exact);body.append(card);
   }
   const p=value.pagination;body.append(el('p',`${p.offset+p.covered} of ${p.total} metadata entries covered`,'muted'));if(p.next_read)link(body,'Read next page',p.next_read);
  }
  if(value.restart_read)link(body,'Read current '+(demand==='aggregate'?'summary':'page'),value.restart_read);
  const facts=el('details');facts.append(el('summary','Reading scope and exact observation'));facts.ontoggle=()=>{if(facts.open&&current()){facts.querySelector('pre')?.remove();facts.append(el('pre',JSON.stringify({observation:value.observation,coverage:value.coverage,inspection:value.inspection,qualification:value.qualification},null,2)));}};body.append(facts);pin();focus.finish();
 }catch(error){focus.dispose();if(current()){status.textContent=error.message;body.replaceChildren(el('p','No qualified evidence is displayed. Your task, drafts and pending requests remain unchanged.'));const fresh=error.result?.restart_read||error.result?.details?.restart_read;if(fresh){try{taskTrailURL(fresh,{namespace,workId});link(body,'Read fresh task evidence',fresh);}catch{}}}}
 return node;
}

// Selection is a proposal in the existing status form. Reads enumerate admitted
// names only; selecting a normal file never promotes it to a support manifest.
export async function mountTaskEvidenceChoices(host,{handle,namespace,workId,request=projectRequest,isCurrent=()=>true,selected=()=>[],onSelect=()=>{},onManifest=()=>{}}={}){
 let alive=true,ticket=0;const live=()=>alive&&isCurrent()&&host.isConnected!==false;host.replaceChildren();const list=el('div'),note=el('p','','muted'),more=button('More saved evidence',()=>load(next)),manifests=el('details');manifests.append(el('summary','Optional: declare a retained-support manifest'),el('p','Only choose a file that has the retained-support manifest schema. A normal answer or Run output is not automatically a manifest.','muted'));let next=null,hasManifests=false;more.hidden=true;host.append(list,note,more,manifests);manifests.hidden=true;
 async function load(read){if(!read||!live())return;const mine=++ticket;more.disabled=true;pendingRead(note,'Reading admitted evidence names…');try{const value=admitTaskTrail(await request(taskTrailURL(read,{namespace,workId})),read,{namespace,workId});if(!live()||mine!==ticket)return;if(read.payload.request.demand!=='choices')throw Error('The owner did not issue an evidence-choice page.');
  for(const item of value.items||[]){if(typeof item.evidence_value!=='string'||!item.evidence_value.trim())continue;const label=el('label'),check=el('input');check.type='checkbox';check.checked=selected().includes(item.evidence_value);label.append(check,document.createTextNode(item.label||item.evidence_value));check.onchange=()=>{if(live())onSelect(item.evidence_value,check.checked);};list.append(label);
   if(item.completion_support){hasManifests=true;const pick=button('Use '+(item.label||'file')+' as support manifest',()=>{if(live())onManifest(clone(item.completion_support));});manifests.append(pick);}
  }
  manifests.hidden=!hasManifests;next=value.pagination.next_read;more.hidden=!next;const coverage=value.coverage?.evidence_choices;note.textContent=(list.children.length?list.children.length+' evidence choices shown. ':'No choices on this page. ')+(coverage?.status==='PARTIAL'?'Some evidence metadata is unavailable; no absence or integrity is inferred. ':'')+'Selecting prepares the status draft. File content and support schema have not been checked here.';
 }catch(error){if(live()&&mine===ticket)note.textContent=error.message;}finally{if(live()&&mine===ticket)more.disabled=false;}}
 await load(handle);return {destroy(){alive=false;ticket++;}};
}

async function openTaskRun({row,namespace,workId,request,isCurrent}){
 const path=taskChildURL(row.read,row,{namespace,workId}),inspector=sharedInspector();
 return inspector.panel({kind:'owner-read',title:'Recorded run',render:async(body,{dialog})=>{dialog.querySelector('.inspector-close')?.focus();const token=inspector.tokenOf(dialog),current=()=>isCurrent()&&inspector.current?.token===token;try{const value=await request(path);if(!current())return;const id=new URL(path,'http://local').searchParams.get('id');if(value.id!==id||value.project!==undefined&&value.project!==namespace||typeof value.state!=='string')throw Error('The Run owner returned another run.');body.append(el('h3',value.title||value.producer_id||'Recorded run'),el('p',human(value.state)));if(value.reason)body.append(el('p',value.reason));const expected=row.reference?.expected_sha256,observed=value.result_provenance?.sha256;if(expected)body.append(el('p',observed&&observed.replace(/^sha256:/,'')===expected.replace(/^sha256:/,'')?'Current output matches the selected retained content pin.':'The selected retained output is not verified by this current Run observation.','muted'));body.append(el('p','This is an explicit current Run-owner observation. Task completion, a saved definition and a past receipt are separate facts.','muted'));const details=el('details');details.append(el('summary','Exact run observation'));details.ontoggle=()=>{if(details.open&&current()){details.querySelector('pre')?.remove();details.append(el('pre',JSON.stringify(value,null,2)));}};body.append(details);}catch(error){if(current())body.replaceChildren(el('p',error.message,'error'));}}});
}
