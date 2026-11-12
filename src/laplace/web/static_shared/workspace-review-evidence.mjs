// Explicit review-evidence reading over issued Work owner handles. This door
// owns only the inspector lifetime and presentation, never review/edit authority.
import {sharedInspector} from './workspace-inspector.mjs';
import {qualifiedOwnerHTTP} from './writing-owner-read.mjs';
import {projectRequest} from './writing-request.mjs';
import {admitWorkReviewRecord,renderWorkReviewPhaseRows,workReviewPhaseBodyReader} from './workspace-work-review.mjs';
import {pendingRead} from './pending-read.mjs';
const object=v=>v!==null&&typeof v==='object'&&!Array.isArray(v),clone=v=>structuredClone(v);
const stable=v=>Array.isArray(v)?v.map(stable):object(v)?Object.fromEntries(Object.keys(v).sort().map(k=>[k,stable(v[k])])):v;
const equal=(a,b)=>JSON.stringify(stable(a))===JSON.stringify(stable(b)),PIN=/^sha256:[a-f0-9]{64}$/;
const el=(tag,text='',cls='')=>{const n=document.createElement(tag);n.textContent=text??'';n.className=cls;return n;};
const button=(label,run,control=null)=>{const n=el('button',label,'act act-read');n.type='button';n.onclick=run;if(control)n.dataset.control=control;return n;};
const technical=(label,value,current)=>{const d=el('details'),s=el('summary',label);d.append(s);d.ontoggle=()=>{if(!d.open||!current())return;d.querySelector('pre')?.remove();d.append(el('pre',JSON.stringify(value,null,2)));};return d;};
const readable=v=>String(v??'not observed').replaceAll('_',' ').replaceAll('-',' ').toLowerCase();
const headerOnly=phase=>object(phase)&&phase.rows==null&&phase.rows_state==='NOT_EXPANDED'&&Array.isArray(phase.header)&&phase.header.length>0&&object(phase.body);
export function reviewEvidenceURL(handle,{namespace,workId,phase=false}={}){
 const qualified=qualifiedOwnerHTTP(handle,namespace),owner=qualified?.owner,payload=handle?.payload;
 const kind=phase?(payload?.obligation_id?'work-review-obligation':'work-review-phase'):'work-review-evidence';
 if(handle?.operation!=='project'||!object(payload)||!owner||owner.project!==namespace||owner.id!==workId||owner.kind!==kind||(payload.namespace??payload.project)!==namespace)throw Error('An exact issued read for this Work and namespace is required.');
 return qualified.url;
}
function panel(){const node=el('dialog','','workspace-dialog source-inspector-dialog review-evidence-dialog'),heading=el('h2','Review evidence'),close=button('Close',()=>node.close()),status=el('p','','work-status'),body=el('div');node.setAttribute('aria-label','Review evidence');close.setAttribute('aria-label','Close review evidence');status.setAttribute('role','status');node.dataset.control='review-evidence:read';node.append(heading,close,status,body);document.body.append(node);return {node,heading,close,status,body};}
const keyFor=(label,handle,context)=>JSON.stringify(stable([label,handle.payload,handle.http,context]));
// Same explicit-return rule as the existing Source reader: retain a qualified
// control key, restore only in the returning frame, and let later intent win.
function returnedFocus(view,key,current){
 if(!key)return {finish(){},dispose(){}};let cancelled=false,done=false;
 const dispose=()=>{document.removeEventListener('pointerdown',cancel,true);document.removeEventListener('keydown',cancel,true);document.removeEventListener('focusin',focused,true);};
 const cancel=()=>{cancelled=true;dispose();},focused=e=>{if(e.target!==view.close&&e.target!==document.body)cancel();};
 document.addEventListener('pointerdown',cancel,true);document.addEventListener('keydown',cancel,true);document.addEventListener('focusin',focused,true);
 return {dispose,finish(){if(done)return;done=true;dispose();if(cancelled||!current()||document.activeElement!==view.close)return;const target=[...view.node.querySelectorAll('[data-review-read-key]')].find(n=>n.dataset.reviewReadKey===key);if(target?.isConnected&&!target.disabled){for(let at=target.parentElement;at&&at!==view.node;at=at.parentElement)if(at.tagName==='DETAILS')at.open=true;target.focus({preventScroll:true});}}};
}
function reopen(args,pin){return openReviewEvidence({...args,handle:pin?.handle||args.handle,expectedObservation:pin?.observation||null,returnFocus:pin?.focusKey||null,reinspected:true});}
export function admitReviewEvidence(value,expected,{namespace,workId}){
 if(value?.schema_version!=='laplace.work-review-evidence/1'||value.work?.namespace!==namespace||value.work?.id!==workId||typeof value.managed!=='boolean')throw Error('The review evidence belongs to another Work or unsupported owner response.');
 if(!object(value.observation)||!PIN.test(value.observation.token||'')||value.observation.unit!=='review-obligation')throw Error('The owner has not supplied a qualified review observation.');
 const wanted=expected.request||{},demand=wanted.demand||'aggregate',selector=wanted.selector||'all';
 if(value.observation.selector!==selector||wanted.observation&&value.observation.token!==wanted.observation)throw Error('The review observation or selected obligation set changed. Read a fresh summary explicitly.');
 if(value.caller_scope?.kind==='project'&&value.caller_scope.namespace!==namespace)throw Error('The review evidence leaves the actual caller scope.');
 const counts=value.counts;if(value.managed?(!object(counts)||counts.unit!=='review-obligation'||['total','required','satisfied_required','remaining_required'].some(k=>!Number.isSafeInteger(counts[k])||counts[k]<0)||counts.required>counts.total||counts.satisfied_required+counts.remaining_required!==counts.required):counts!==null)throw Error('The owner obligation counts are incomplete.');
 if(!['aggregate','enumerate','support'].includes(demand))throw Error('Unsupported review evidence demand.');
 return {demand,selector};
}
export async function openReviewEvidence({handle,namespace,workId,request=projectRequest,isCurrent=()=>true,onOpen=()=>{},returnFocus=null,reinspected=false,expectedObservation=null,recordBinding=null}={}){
 if(!isCurrent())return null;const phase=handle?.payload?.view==='review',url=reviewEvidenceURL(handle,{namespace,workId,phase}),issued=clone(handle),view=panel(),inspector=sharedInspector();let alive=true,focusKey=returnFocus,focusReturn=null,observedToken=expectedObservation;
 const args={handle:issued,namespace,workId,request,isCurrent,onOpen,recordBinding},token=inspector.adopt(view.node,{kind:'work-review-evidence',title:'Review evidence',reopen:{factory:reopen,args}}).token,current=()=>alive&&isCurrent()&&inspector.current?.token===token;
 view.node.onclose=()=>{alive=false;focusReturn?.dispose();view.node.remove();};view.node.showModal();view.close.focus();onOpen(view.node);focusReturn=returnedFocus(view,returnFocus,current);pendingRead(view.status,'Reading this Work’s review evidence…');
 const link=(host,label,next,context=null,control='review-evidence:inspect')=>{
  const childPhase=next?.payload?.view==='review';reviewEvidenceURL(next,{namespace,workId,phase:childPhase});const key=keyFor(label,next,context),node=button(label,async()=>{try{if(!current())return;focusKey=key;inspector.pin(token,{handle:issued,focusKey,observation:observedToken});await openReviewEvidence({...args,handle:next,recordBinding:childPhase?context:null,isCurrent:inspector.lineage(token)});}catch(error){if(current())view.status.textContent=error.message;}},control);node.dataset.reviewReadKey=key;host.append(node);return node;
 };
 try{
  const value=await request(url);if(!current())return view.node;const content=el('div');let heading='Review evidence';
  if(phase){
   admitWorkReviewRecord({project:namespace,workId},issued,value);
   // A large recorded phase arrives as its owner-issued header plus one exact body page (rows:null, NOT_EXPANDED). Its
   // header rows carry the same phase/obligation identities, so support is judged on them, never on fabricated rows.
   const compact=headerOnly(value.phase);
   if(compact&&(!PIN.test(value.phase.revision||'')||!PIN.test(value.phase.body.sha256||'')||!Number.isSafeInteger(value.phase.body.chars)||!object(value.read_cut)||recordBinding?.cut&&!equal(value.read_cut,recordBinding.cut)))throw Error('The recorded phase header is not bound to its exact phase revision and Work cut.');
   if(recordBinding?.obligation&&issued.payload.phase_id){const rows=(compact?value.phase.header:value.phase?.rows)||[];if(recordBinding.recordKind==='review'&&(recordBinding.reviewId&&issued.payload.phase_id!==recordBinding.reviewId||!rows.some(row=>row.phase==='review'&&row.obligation_id===recordBinding.obligation)||rows.some(row=>row.phase==='review'&&row.obligation_id!==recordBinding.obligation))||recordBinding.recordKind==='handoff'&&(!rows.some(row=>row.phase==='handoff'&&row.obligations?.includes(recordBinding.obligation))||rows.some(row=>row.phase==='handoff'&&!row.obligations?.includes(recordBinding.obligation))))throw Error('The recorded phase does not support the selected review obligation.');}
   heading='Recorded review phase';content.append(el('p','Exact observed phase rows. This is separate from current review standing and original evidence-body inspection.','muted'));
   view.node.dataset.control='review-evidence:phase';
   if(issued.payload.obligation_id){heading='Review obligation · '+(value.obligation?.label||'Selected obligation');renderObligation(content,value,{link,current});}
   else renderWorkReviewPhaseRows(content,value,compact?{onRead:(page,label)=>workReviewPhaseBodyReader({project:namespace,workId,phase:value.phase,cut:value.read_cut,current,
     load:next=>request(reviewEvidenceURL(next,{namespace,workId,phase:true}))})(content,page,label)}:{});
   content.append(technical('Exact recorded observation',value,current));
  }else{
   const {demand}=admitReviewEvidence(value,issued.payload,{namespace,workId});if(expectedObservation&&value.observation.token!==expectedObservation)throw Object.assign(Error('The previously observed review inputs changed. Read a fresh summary explicitly.'),{restart_read:value.restart_read});observedToken=value.observation.token;heading='Review evidence · '+(value.work.title||'Selected Work');if(value.work.purpose)content.append(el('p',value.work.purpose,'operator-work-purpose'));if(reinspected)content.append(el('p','Reinspected owner observation','muted'));
   view.node.dataset.reviewEvidenceState=demand==='enumerate'?'list':demand==='support'?'support':'aggregate';
   const c=value.counts;if(!value.managed)content.append(el('h3','No managed review obligations'),el('p','This Work does not define a managed review. It has not been declared satisfied by a zero count.'));
   else{content.append(el('h3',c.remaining_required?'Required review remains':'Required review count'),el('p',c.required+' required · '+c.satisfied_required+' satisfied · '+c.remaining_required+' remaining','source-inspector-state'));if(!c.required)content.append(el('p','No required obligations are declared. No success percentage is inferred.','muted'));}
   if(c?.obligations_with_known_missing_source_segments>0)content.append(el('p',c.obligations_with_known_missing_source_segments+' obligations have known missing Source segment coverage. Local satisfaction does not establish complete Source coverage.','work-review-needed'));
   if(value.managed&&demand==='aggregate'){for(const [name,label]of [['by_status','Review outcomes'],['by_currentness','Evidence currentness'],['by_independence','Recorded independence']]){const values=c[name];if(!object(values)||Object.values(values).some(n=>!Number.isSafeInteger(n)||n<0))throw Error('The owner review outcome counts are incomplete.');content.append(el('p',label+': '+Object.entries(values).map(([key,n])=>n+' '+readable(key)).join(' · '),'muted'));}}
   if(value.work.title_complete===false||value.work.purpose_complete===false)content.append(el('p','Task preview is bounded; the complete Work remains available from its original editor.','muted'));
   if(value.pending_joins?.unit==='follow-up'&&value.pending_joins.count>0)content.append(el('p',value.pending_joins.count+' pending follow-up joins · counted separately from obligations.','muted'));
   const choices=el('div','','source-inspector-controls');if(value.managed)for(const [selector,label]of [['remaining-required','List remaining required obligations'],['required','List required obligations'],['all','List all obligations']])if(value.enumerate_reads?.[selector]){const next=value.enumerate_reads[selector],q=next.payload?.request;if(q?.demand!=='enumerate'||q.selector!==selector||!PIN.test(q.observation||''))throw Error('The owner obligation list changes its declared selector.');link(choices,label,next,value.observation,'review-evidence:list');}if(demand==='aggregate')content.append(choices);else{const other=el('details');other.append(el('summary','Other obligation lists'),choices);content.append(other);}
   if(demand!=='aggregate')await renderRequested(content,value,{issued,namespace,workId,current,link});if(!current())return view.node;
   content.append(el('p','A complete count does not mean supporting bodies were inspected. Local satisfaction, evidence currentness and independence remain separate.','muted'));
   if(value.restart_read)link(content,'Read fresh review summary',value.restart_read,value.observation,'review-evidence:read');
   content.append(technical('Observation, count units and reading limits',{observation:value.observation,counts:value.counts,pending_joins:value.pending_joins,qualification:value.qualification,caller_scope:value.caller_scope},current));
  }
  if(!current())return view.node;view.heading.textContent=heading;view.body.replaceChildren(content);
  inspector.pin(token,{handle:issued,focusKey,observation:observedToken});view.status.textContent='';focusReturn.finish();
 }catch(error){focusReturn?.dispose();if(current()){view.node.dataset.reviewEvidenceState='changed';view.body.replaceChildren(el('p','No qualified review evidence is displayed. Your editor, drafts and original pending requests are unchanged.','muted'));view.status.textContent=error.message;const refusal=error.result||{},reads=[error.restart_read,refusal.restart_read,refusal.details?.restart_read,...(refusal.next_reads||refusal.details?.next_reads||[])].filter(Boolean),seen=new Set();for(const next of reads){try{const key=JSON.stringify(stable(next)),aggregate=next.payload?.view==='review-evidence'&&(next.payload.request?.demand||'aggregate')==='aggregate',record=next.payload?.view==='review'&&next.payload.phase_id&&PIN.test(next.payload.phase_revision||'');if(!seen.has(key)&&(aggregate||record)){link(view.body,aggregate?'Read fresh review summary':'Read current recorded phase',next,null,'review-evidence:read');seen.add(key);}}catch{}}}}
 return view.node;
}
function renderStanding(host,s={}){host.append(el('p',readable(s.status)+' · evidence '+readable(s.currentness)+' · independence '+readable(s.independence)),el('p',s.satisfied===true?'Locally satisfied':'Not locally satisfied','muted'));}
function sameRequest(handle,value,namespace,workId,{demand,selector,observation}={}){
 reviewEvidenceURL(handle,{namespace,workId});const r=handle.payload.request||{};
 if(demand&&r.demand!==demand||selector&&r.selector!==selector||observation&&r.observation!==observation)throw Error('The offered read changes the selected review observation.');return r;
}
export async function decodeReviewSupport(value,expected,{namespace,workId}){
 const support=value.support,binding={namespace,work_id:workId,observation:expected.observation,selector:expected.selector,enumeration:expected.enumeration,ids:expected.ids};
 if(!object(support)||!equal(support.binding,binding)||!Array.isArray(support.items)||!Array.isArray(expected.ids)||!equal(support.items.map(i=>i.id),expected.ids))throw Error('The selected support does not match its exact observation, page and obligation set.');
 if(support.encoding==='inline'){
  if(support.descriptors!==undefined||support.items.some(i=>i.inspection_refs!==undefined||!Array.isArray(i.inspection_routes)))throw Error('Mixed or incomplete support encoding.');return clone(support.items);
 }
 if(support.encoding!=='descriptor-table'||!Array.isArray(support.descriptors)||!globalThis.crypto?.subtle)throw Error('Exact support descriptor verification is unavailable.');
 const table=[];
 for(const [index,row]of support.descriptors.entries()){
  if(!object(row)||!Number.isSafeInteger(row.id)||row.id!==index||!PIN.test(row.sha256||'')||!object(row.route)||Object.keys(row.route).some(k=>!['kind','title','read'].includes(k)))throw Error('The support descriptor table is incomplete.');
  const bytes=new TextEncoder().encode(JSON.stringify(stable(row.route))),digest=await globalThis.crypto.subtle.digest('SHA-256',bytes),observed='sha256:'+Array.from(new Uint8Array(digest),n=>n.toString(16).padStart(2,'0')).join('');
  if(observed!==row.sha256)throw Error('An exact support descriptor changed.');table.push(row.route);
 }
 return support.items.map(item=>{if(item.inspection_routes!==undefined||!Array.isArray(item.inspection_refs)||item.inspection_refs.some(ref=>!Number.isSafeInteger(ref)||ref<0||ref>=table.length))throw Error('An ordered support reference is missing or outside this response.');const out=clone(item);delete out.inspection_refs;out.inspection_routes=item.inspection_refs.map(ref=>clone(table[ref]));return out;});
}
async function renderRequested(host,value,{issued,namespace,workId,current,link}){
 const q=issued.payload.request,selector=value.observation.selector,token=value.observation.token;
 if(q.demand==='enumerate'){
  const page=value.enumeration,items=value.items;
  if(!object(page)||!Array.isArray(items)||!PIN.test(page.basis||'')||page.selector!==selector||page.offset!==(q.offset??0)||page.limit!==(q.limit??6)||!Number.isSafeInteger(page.known)||!Number.isSafeInteger(page.covered)||page.covered<0||page.covered>page.limit||page.returned!==items.length||page.covered<page.returned||page.offset+page.covered>page.known||typeof page.complete!=='boolean'||!Array.isArray(page.oversized)||new Set(items.map(i=>i.id)).size!==items.length)throw Error('The returned obligation page does not match its issued window.');
  const known=value.managed?(selector==='all'?value.counts.total:selector==='required'?value.counts.required:value.counts.remaining_required):0;if(page.known!==known)throw Error('The obligation page does not cover the selected owner count.');
  for(const item of items){if(typeof item.id!=='string'||typeof item.label!=='string')throw Error('An obligation has no owner-issued identity and label.');if(item.support_read){const r=sameRequest(item.support_read,value,namespace,workId,{demand:'support',selector,observation:token});if(r.offset!==page.offset||r.limit!==page.limit||r.enumeration!==page.basis||!equal(r.ids,[item.id]))throw Error('The selected inspection read does not belong to this exact enumerated obligation.');}else if(item.metadata_state!=='OVERSIZED'||!item.inspection_read)throw Error('An obligation has no inspection route or explicit oversized qualification.');}
  host.append(el('h3',selector==='remaining-required'?'Remaining required obligations':selector==='required'?'Required obligations':'All review obligations'),el('p',page.returned+' shown · '+page.known+' in this list'+(page.complete?' · complete list':' · bounded page'),'source-inspector-state'));
  if(!items.length)host.append(el('p','No obligations match this owner-issued list.'));
  for(const item of items){const card=el('section','','source-inspector-card');card.append(el('h3',item.label));if(item.metadata_state==='OVERSIZED'){card.append(el('p','The metadata is too large for this page. Read the owner’s full selected record deliberately.'));link(card,'Inspect full obligation record',item.inspection_read,{obligation:item.id,observation:value.observation});}else{card.append(el('p',(item.required?'Required':'Optional')+' · '+(item.independent_required?'independent review required':'owner’s declared independence rule'),'muted'));renderStanding(card,item.standing);if(item.reason)card.append(el('p',item.reason));if(item.reason_complete===false)card.append(el('p','This reason is a bounded preview; inspect the full obligation record.','muted'));link(card,'Inspect evidence routes · '+item.label,item.support_read,{obligation:item.id,observation:value.observation});}host.append(card);}
  if(value.support_read){const r=sameRequest(value.support_read,value,namespace,workId,{demand:'support',selector,observation:token});if(r.offset!==page.offset||r.limit!==page.limit||r.enumeration!==page.basis||!equal(r.ids,items.map(i=>i.id)))throw Error('The full-page inspection does not name the enumerated obligations.');link(host,'Inspect evidence routes for this page',value.support_read,{observation:value.observation});}
  if(page.next_read){const r=sameRequest(page.next_read,value,namespace,workId,{demand:'enumerate',selector,observation:token});if(r.offset!==page.offset+page.covered||r.limit!==page.limit||r.offset<=page.offset)throw Error('The obligation continuation does not advance at the same observation.');link(host,'More obligations',page.next_read,{observation:value.observation},'review-evidence:list');}
 }else if(q.demand==='support'){
  const items=await decodeReviewSupport(value,q,{namespace,workId});if(!current())return;
  for(const item of items){if(typeof item.label!=='string'||!['EXPANDED','OVERSIZED'].includes(item.metadata_state)||item.body_inspection!=='NOT_READ'||!Array.isArray(item.inspection_routes))throw Error('The selected support metadata is incomplete.');for(const route of item.inspection_routes){const r=route.read?.payload;reviewEvidenceURL(route.read,{namespace,workId,phase:true});if(route.kind==='obligation'?r.obligation_id!==item.id:!['review','handoff'].includes(route.kind)||!r.phase_id||!PIN.test(r.phase_revision||'')||route.kind==='review'&&r.phase_id!==item.standing?.review_id)throw Error('A selected inspection route names another obligation or unsupported record.');}}
  for(const item of items){const card=el('section','','source-inspector-card'),occurrences=new Map();card.append(el('h3',item.label),el('p',item.metadata_state==='EXPANDED'?'Selected evidence metadata':'Selected metadata is oversized; full inspection is separate.','source-inspector-state'));if(item.standing)renderStanding(card,item.standing);for(const route of item.inspection_routes){const routeKey=JSON.stringify(stable(route)),occurrence=occurrences.get(routeKey)||0;occurrences.set(routeKey,occurrence+1);link(card,route.title,route.read,{obligation:item.id,observation:value.observation,occurrence,recordKind:route.kind,reviewId:item.standing?.review_id},route.kind==='obligation'?'review-evidence:inspect':'review-evidence:phase');}if(item.metadata_state==='EXPANDED'){const fields=el('details'),list=el('ul');fields.append(el('summary','Declared inputs · '+(item.declared_inputs||[]).length));for(const input of item.declared_inputs||[])list.append(el('li',input));fields.append(list);card.append(fields);}card.append(el('p','Inspection routes are available. Original evidence bodies have not been read.','muted'),technical('Exact selected metadata and limits',item,current));host.append(card);}
 }
}
function renderObligation(host,value,{link,current}){
 const obligation=value.obligation,inputs=obligation.inputs||[],history=value.history||{};host.append(el('p','Current declared inputs and recorded history. This container read does not inspect original evidence bodies.','muted'));if(obligation.standing)renderStanding(host,obligation.standing);const list=el('ul');for(const input of inputs)list.append(el('li',input));host.append(el('h3','Declared inputs'),inputs.length?list:el('p','No declared inputs.'),el('h3','Recorded history'));
 for(const row of history.items||[]){if(!row.read)throw Error('A recorded phase has no issued inspection read.');link(host,'Read '+readable(row.phase)+(row.verdict?' · '+row.verdict:''),row.read,{obligation:obligation.id,phase:row.id,recordKind:row.phase,reviewId:row.phase==='review'?row.id:undefined,cut:value.read_cut},'review-evidence:phase');}
 if(history.next_read)link(host,'More recorded history',history.next_read,{obligation:obligation.id,cut:value.read_cut},'review-evidence:inspect');
 host.append(technical('Exact obligation and history coverage',{obligation,pagination:history},current));
}
