// Comment/review-route draft and immutable submission custody. Owner response meaning stays
// in the focused route controller. This service never retries, reads or submits on its own.
const copy=value=>JSON.parse(JSON.stringify(value));
export async function feedbackWireDigest(wire){
 const hash=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(wire));
 return 'sha256:'+Array.from(new Uint8Array(hash),byte=>byte.toString(16).padStart(2,'0')).join('');
}
export async function retainFeedbackSubmission(payload,lookup){
 if(typeof payload?.project!=='string'||!payload.project||typeof payload.request_id!=='string'||!payload.request_id)throw Error('A retained comment submission needs its project and original request.');
 const wire=JSON.stringify(payload);
 return {wire,wire_sha256:await feedbackWireDigest(wire),project:payload.project,request_id:payload.request_id,lookup:copy(lookup),observation:'UNKNOWN'};
}
export async function retainedFeedbackPayload(pending){
 if(typeof pending?.wire!=='string'||await feedbackWireDigest(pending.wire)!==pending.wire_sha256)throw Error('The retained comment submission is damaged. Nothing was sent; keep its original request for inspection.');
 const payload=JSON.parse(pending.wire);
 if(payload.project!==pending.project||payload.request_id!==pending.request_id)throw Error('The retained comment submission no longer matches its project and request.');
 return payload;
}
export function feedbackHTTP(handle,{project,method='GET',paths=null,base=globalThis.location?.href||'http://local/'}={}){
 const http=handle?.http;let path=http?.url;if(!path&&http?.route&&http?.query){if(Object.values(http.query).some(value=>typeof value!=='string'))throw Error('The feedback query descriptor is not an exact string carrier.');path=http.route+'?'+new URLSearchParams(http.query);}const url=new URL(path||'',base),here=new URL(base);
 if(http?.method!==method||url.origin!==here.origin||url.hash||url.username||url.password||paths&&!paths.includes(url.pathname)||method==='GET'&&(url.searchParams.getAll('project').length!==1||url.searchParams.get('project')!==project)||url.searchParams.has('project')&&url.searchParams.get('project')!==project)throw Error('The feedback owner handle does not match this project and action.');
 if(handle?.payload?.project&&handle.payload.project!==project)throw Error('The feedback action belongs to another project.');
 return url.pathname+url.search;
}
// Request custody identity K = (kind, project, context, request_id, raw-wire hash): immutable retained-submission fields
// only, never observation, lookup or settle metadata. Two slots are one request only when K AND the raw wire are equal.
// The owner's canonical intent_sha256 is a separate domain and is never compared with this raw wire hash.
export function feedbackRequestIdentity(slot,pending){
 if(!pending)return null;let payload=null;try{payload=JSON.parse(pending.wire);}catch{payload=null;}
 const kind=slot==='policy_pending'||payload?.action==='policy-save'?'policy':payload?.action==='route-submit'?'route':'origin';
 const context=kind==='origin'?payload?.source_basis?.ledger:payload?.work_id;
 return JSON.stringify([kind,String(pending.project??payload?.project??''),String(context??''),String(pending.request_id??''),String(pending.wire_sha256??'')]);
}
const SLOTS=['pending','policy_pending'];
// ONE shared unresolved-custody predicate: an unconfirmed Save/route request (pending) OR policy request (policy_pending).
// Every new Save, Request reviews, Save and request and automatic-policy effect refuses while it holds; the pure Check, the
// owner-issued settle and the exact retry of the same retained request stay available.
export function feedbackUnresolved(state){return SLOTS.some(slot=>!!state?.[slot]);}
const slotsOf=s=>SLOTS.filter(slot=>s?.[slot]).map(slot=>({slot,identity:feedbackRequestIdentity(slot,s[slot]),wire:typeof s[slot].wire==='string'?s[slot].wire:null}));
const sameRequest=(a,b)=>a.identity===b.identity&&a.wire===b.wire;
const COMPARISON='laplace.feedback-request-comparison/1',ASSOCIATION='laplace.feedback-request-association/1';
const KIND_PATH={origin:'/authoring/correction-request',route:'/work/delivery',policy:'/work/delivery'};
// The owner-issued pure comparison read with ONLY its declared field filled by the exact retained original wire. No URL,
// field or schema is guessed: a template that does not name this exact request is refused before any read.
export async function feedbackComparisonURL(pending,template,slot='pending'){
 const payload=await retainedFeedbackPayload(pending),[kind,project,context,requestId]=JSON.parse(feedbackRequestIdentity(slot,pending));
 if(template?.schema_version!==COMPARISON||template.kind!==kind||template.project!==project||template.context!==context||template.request_id!==requestId
   ||!Array.isArray(template.requires)||template.requires.join()!=='submission'||template.field!=='submission')throw Error('The owner did not issue a comparison for this exact request.');
 const path=feedbackHTTP(template.read,{project,paths:[KIND_PATH[kind]]}),url=new URL(path,'http://local');
 if(template.carrier==='query-json'){if(url.searchParams.has(template.field))throw Error('The owner did not issue a comparison for this exact request.');url.searchParams.set(template.field,pending.wire);}
 else if(template.carrier==='request-json'){if(url.searchParams.getAll('request').length!==1)throw Error('The comparison template repeats its request.');let read;try{read=JSON.parse(url.searchParams.get('request'));}catch{throw Error('The comparison template is not an exact owner request.');}
  if(read?.action!=='route-status'||read.work_id!==context||read.request_id!==requestId||(read.request_kind||'route')!==kind||Object.hasOwn(read,template.field))throw Error('The comparison template changed its Work, request or kind.');
  read[template.field]=payload;url.searchParams.set('request',JSON.stringify(read));}
 else throw Error('The comparison template uses an unsupported carrier.');
 return url.pathname+url.search;
}
// The scoped owner association of one exact request; anything naming another request, kind or context is refused.
export function feedbackAssociation(value,pending,slot='pending'){
 const [kind,project,context,requestId]=JSON.parse(feedbackRequestIdentity(slot,pending)),a=value?.association;
 if(a?.schema_version!==ASSOCIATION||a.kind!==kind||a.project!==project||a.context!==context||a.request_id!==requestId
   ||!['MATCH','MISMATCH','UNRECORDED','UNKNOWN'].includes(a.state)||!/^sha256:[0-9a-f]{64}$/.test(a.intent_sha256||''))throw Error('The owner association does not name this exact request.');
 return {state:a.state,effect:String(value.effect||''),intent:a.intent_sha256};
}
// ONE pure outcome classification for origin, route and policy, shared by the one-copy editor and the per-copy recovery of a
// disagreement. Association.MATCH alone is never a receipt: a RECORDED outcome is accepted only through the existing receipt
// contract of its kind, and a NOT_ADMITTED outcome only through its full terminal shape (code, fence intent, outcome scope and
// preserved partial effects). Anything malformed, foreign, mismatched or raced throws, so the pending slot keeps custody.
const REQUEST_TERMINAL='AUTHOR_SETTLED_UNADMITTED_REQUEST';
function requestTerminal(value,payload,kind,association){
 const s=value?.settlement,effects=value?.preserved_effects;
 if(value?.effect!=='NOT_ADMITTED'||value.terminal!==true||value.request_kind!==kind||value.request_id!==payload.request_id||s?.code!==REQUEST_TERMINAL||s.by!=='author'
   ||typeof s.id!=='string'||!s.id||s.request_kind!==kind||s.request_id!==payload.request_id||s.intent_sha256!==association?.intent_sha256
   ||!['request','route-admission-only'].includes(s.outcome_scope)||!Array.isArray(effects))
  throw Error('The owner did not establish terminal non-admission for this exact original request; it stays unconfirmed.');
 if(s.outcome_scope==='route-admission-only'){
  if(kind!=='route'||!payload.policy||!effects.length||effects.some(e=>e?.kind!=='work-delivery-policy'||typeof e.id!=='string'||!/^sha256:[0-9a-f]{64}$/.test(e.revision||'')||typeof e.request_id!=='string'))
   throw Error('The route-admission-only settlement does not preserve its recorded policy effect; the request stays unconfirmed.');
 }else if(effects.length)throw Error('A whole-request settlement does not preserve partial effects; the request stays unconfirmed.');
 return copy(value);
}
function policyReceipt(value,payload){
 const policy=value?.policy;
 if(value?.effect!=='RECORDED'||!policy?.id||policy.project!==payload.project||policy.work_id!==payload.work_id||policy.request_id!==payload.request_id
   ||['mode','recipients','limits'].some(key=>!sameFeedbackValue(policy[key],payload.policy?.[key])))throw Error('Policy outcome is not yet established; retain its exact request.');
 return copy(value);
}
export async function feedbackRequestOutcome(value,legacy,pending,slot='pending'){
 const found=feedbackAssociation(value,pending,slot),[kind]=JSON.parse(feedbackRequestIdentity(slot,pending)),payload=await retainedFeedbackPayload(pending);
 const base={...found,kind,fields:null,settle:null,receipt_value:null};
 if(found.state!=='MATCH'){
  const settle=found.state==='MISMATCH'?null:kind==='origin'?(found.state==='UNRECORDED'&&legacy?.settle?copy(legacy.settle):null):(value.settle?.permitted?copy(value.settle):null);
  return {...base,settle};
 }
 if(found.effect==='NOT_ADMITTED'){
  if(kind==='origin')return {...base,fields:{terminal:await feedbackTerminalOutcome(value,pending),prepared:null,request_id:null,readdressed:false},receipt_value:copy(value)};
  const terminal=requestTerminal(value,payload,kind,value.association);
  return {...base,fields:{[kind==='policy'?'policy_terminal':'route_terminal']:terminal},receipt_value:terminal};
 }
 if(found.effect!=='RECORDED')throw Error('The owner association reports an unknown outcome; the request stays unconfirmed.');
 if(kind==='origin'){const receipt=await feedbackOriginReceipt(legacy,pending);if(!receipt)throw Error('The saved outcome is not yet established by its receipt; the request stays unconfirmed.');
  return {...base,fields:{receipt,route_outcome:legacy.review_route||null,terminal:null},receipt_value:copy(legacy)};}
 if(kind==='route'){const receipt=await feedbackRouteReceipt(legacy,pending,payload.origin);
  if(value.route_id&&receipt.aggregate.route_id!==value.route_id)throw Error('The review receipt names another route; the request stays unconfirmed.');
  return {...base,fields:{receipt},receipt_value:receipt};}
 const receipt=policyReceipt(value,payload);
 return {...base,fields:{policy_receipt:receipt,route_policy_id:receipt.policy.id},receipt_value:receipt};
}
export function createFeedbackDraft({project,key,initial={},storage=globalThis.sessionStorage,backup=globalThis.localStorage}={}){
 const storageKey='laplace:feedback-route:'+JSON.stringify([project,key]);let state=copy(initial),storageError='',recoveryError='',recoveryRaw=[],restored=false,revision=null,lineage=[],disagreement=null,recovered=null,retained=null,conflict=null;const seen={};
 // Both stores are read. Each retained wire names its own revision and the revisions it descends from: the draft's own
 // write lineage, never a clock. A copy that descends from the other is the newer retained state and is recovered (and
 // reported) even when it is not the preferred store's. Copies that do not descend from one another (independent tabs,
 // legacy envelopes without lineage) are a disagreement: both original copies stay untouched until an explicit choice.
 const copies=[];
 for(const [name,store] of [['session',storage],['backup',backup]]){let raw;try{raw=store?.getItem(storageKey);}catch(error){storageError=error.message;continue;}seen[name]=raw??null;if(raw){try{const held=JSON.parse(raw);if(held.schema_version!=='laplace.feedback-route-draft/1'||held.project!==project||held.key!==key||!held.state||typeof held.state!=='object'||Array.isArray(held.state))throw Error('Stored comment recovery does not match this draft.');
   copies.push({store:name,raw,state:held.state,revision:held.revision&&typeof held.revision.id==='string'?{id:held.revision.id,n:Number(held.revision.n)||0}:null,prior:Array.isArray(held.prior)?held.prior.filter(id=>typeof id==='string'):[]});}catch(error){recoveryError='Stored comment recovery is unreadable. The original bytes are retained; no new submission is permitted.';recoveryRaw.push(raw);}}}
 const descends=(a,b)=>!!(a.revision&&b.revision&&a.prior.includes(b.revision.id));
 const adopt=item=>{state=item.state;revision=item.revision;lineage=item.prior;restored=true;};
 if(copies.length===1)adopt(copies[0]);
 else if(copies.length===2){const [first,second]=copies;
  if(JSON.stringify(first.state)===JSON.stringify(second.state))adopt(descends(second,first)?second:first);
  else if(descends(first,second))adopt(first);
  else if(descends(second,first)){adopt(second);recovered={from:second.store,stale:first.store};}
  else{disagreement=copies.map(item=>({store:item.store,raw:item.raw,state:item.state}));restored=true;}}
 const blocked=()=>recoveryError||(disagreement?'Two stored copies of this comment draft disagree. Both are kept exactly; choose one before anything is saved or sent.':'')||(conflict?'Another editor changed this comment draft after it was opened here. Nothing was overwritten; the text in this editor is not retained or sent. Reopen the comment to continue with the stored draft.':'');
 // THE CHECKED WRITE BOUNDARY shared by every persisting mutator (update, reset, retain, pendingPayload, observe, settle,
 // choose): a store is replaced only while it still holds exactly what this instance last read or wrote there. Anything
 // else (another editor, or a newer state written after this instance's own basis) is a write conflict: nothing is
 // replaced, this instance's proposal stays in memory and visible, and every later write and submission refuses. This
 // closes stale-instance and late-callback writes within the browser's storage semantics; it is not a cross-window lock.
 const stores=[['session',storage],['backup',backup]];
 const now=store=>{try{return {raw:store?.getItem(storageKey)??null};}catch(_error){return null;}};
 const snapshot=()=>copy(state);
 // BOTH raw stored copies exactly as the stores hold them now: the basis a request check captures before its first await.
 const storedBasis=()=>stores.map(([name,s])=>({store:name,raw:now(s)?.raw??null}));
 function persist(){if(blocked()){retained=false;return false;}
  for(const [name,store] of stores){const held=now(store);if(held&&held.raw!==(seen[name]??null)){conflict={stored:stores.map(([label,s])=>({store:label,raw:now(s)?.raw??null}))};retained=false;return false;}}
  // The revision advances only with a confirmed write: a failed attempt leaves no phantom id in the lineage.
  const prior=(revision?[revision.id,...lineage]:lineage).slice(0,32),next={id:'R-'+globalThis.crypto.randomUUID(),n:(revision?.n||0)+1};
  const wire=JSON.stringify({schema_version:'laplace.feedback-route-draft/1',project,key,revision:next,prior,state});let stored=false;
  for(const [name,store] of stores)try{store?.setItem(storageKey,wire);if(store?.getItem(storageKey)===wire){stored=true;seen[name]=wire;}}catch(error){storageError=error.message;}
  if(stored){revision=next;lineage=prior;}else storageError='This comment draft could not be retained in browser storage. Keep the editor open; submission needs a durable recovery copy.';
  retained=stored;return stored;
 }
 // Explicit recovery of a disagreement: the chosen copy continues as a revision that descends from both original copies.
 // If nothing can be written, the disagreement and both original copies remain exactly as they were.
 // Choosing prose never drops an unconfirmed Save, review-route or policy request held only by another copy: that copy
 // must be continued (and its request checked through the existing owner lookup) first.
 // Custody is compared by exact request identity K plus raw wire, never by observation metadata: same-wire variants may
 // choose prose while keeping that wire; a distinct unresolved request held only by another copy is never dropped.
 function canChoose(index){const pick=disagreement?.[index];if(!pick)return 'No disagreeing stored copy is selected.';const mine=slotsOf(pick.state);
  return disagreement.some((item,i)=>i!==index&&slotsOf(item.state).some(other=>!mine.some(held=>sameRequest(held,other))))?'The other copy holds a different unconfirmed comment, review or policy request. Check it below first; it is never dropped.':'';}
 // At most 2 copies x (pending, policy_pending): each distinct request once, with every copy and slot holding it.
 function inventory(){const source=disagreement?disagreement.map((item,index)=>({index,store:item.store,state:item.state})):[{index:null,store:null,state}],out=[];
  for(const c of source)for(const entry of slotsOf(c.state)){let row=out.find(item=>sameRequest(item,entry));
   if(!row){row={identity:entry.identity,wire:entry.wire,kind:JSON.parse(entry.identity)[0],request_id:c.state[entry.slot].request_id,holders:[]};out.push(row);}
   row.holders.push({index:c.index,store:c.store,slot:entry.slot,observation:c.state[entry.slot].observation??null});}
  return copy(out);}
 // Commit ONE owner-matched outcome to one copy's slot, guarded by both shown raw copies, the current stored bytes and the
 // exact K/wire. Every other field of that copy and the whole other copy are preserved; a stale basis is an observation only.
 function settleCopy({index=null,slot,identity,wire,basis=null},fields={}){
  if(!SLOTS.includes(slot))throw Error('Unknown request slot.');
  const matches=s=>!!s?.[slot]&&feedbackRequestIdentity(slot,s[slot])===identity&&(typeof s[slot].wire==='string'?s[slot].wire:null)===wire;
  const shown=disagreement?disagreement.map(item=>({store:item.store,raw:item.raw})):null;
  if(basis&&shown&&(basis.length!==shown.length||basis.some((b,i)=>b.store!==shown[i].store||b.raw!==shown[i].raw)))throw Error('The stored copies changed while this request was checked. The owner reply is kept as an observation only; nothing was changed.');
  // One copy: the basis is BOTH raw stored copies captured before the check's first await; other bytes are not this check's.
  if(!disagreement){if(blocked())throw Error(blocked());if(basis&&JSON.stringify(basis)!==JSON.stringify(storedBasis()))throw Error('This comment draft changed while its request was checked. The owner reply is kept as an observation only; nothing was changed.');if(!matches(state))throw Error('This draft no longer holds the checked request; nothing was changed.');const before=state;state={...state,...copy(fields),[slot]:null};if(persist())return true;state=before;return false;}
  if(recoveryError)throw Error(recoveryError);
  if(disagreement.some(item=>(now(item.store==='session'?storage:backup)?.raw??null)!==item.raw))throw Error('The stored copies changed after they were shown. Nothing was replaced; reopen the comment to see the current copies.');
  const item=disagreement[index];if(!item||!matches(item.state))throw Error('This copy no longer holds the checked request; nothing was changed.');
  let held;try{held=JSON.parse(item.raw);}catch{throw Error('This stored copy is unreadable; nothing was changed.');}
  const next={id:'R-'+globalThis.crypto.randomUUID(),n:(Number(held.revision?.n)||0)+1},prior=[...(held.revision?.id?[held.revision.id]:[]),...(Array.isArray(held.prior)?held.prior:[])].slice(0,32);
  const nextState={...item.state,...copy(fields),[slot]:null},out=JSON.stringify({schema_version:'laplace.feedback-route-draft/1',project,key,revision:next,prior,state:nextState}),store=item.store==='session'?storage:backup;
  try{store?.setItem(storageKey,out);}catch(error){storageError=error.message;}
  const after=now(store)?.raw??null;
  if(after!==out){if(after!==item.raw)conflict={stored:stores.map(([label,s])=>({store:label,raw:now(s)?.raw??null}))};storageError=storageError||'This copy could not record the owner outcome; it is kept as it was.';retained=false;return false;}
  item.raw=out;item.state=nextState;seen[item.store]=out;const source=copies.find(c=>c.store===item.store);if(source){source.raw=out;source.state=nextState;source.revision=next;source.prior=prior;}
  return true;}
 function choose(index){const reason=canChoose(index);if(reason)throw Error(reason);
  // The explicit choice rereads the copies it showed; a copy changed since display is never replaced unseen.
  if(disagreement.some(item=>(now(item.store==='session'?storage:backup)?.raw??null)!==item.raw))throw Error('The stored copies changed after they were shown. Nothing was replaced; reopen the comment to see the current copies.');
  const pick=disagreement[index],before={state,revision,lineage,disagreement};
  state=copy(pick.state);revision=null;lineage=copies.map(item=>item.revision?.id).filter(Boolean);disagreement=null;
  if(persist())return true;({state,revision,lineage,disagreement}=before);return false;}
 return {snapshot,get storageError(){return blocked()||storageError;},get recoveryError(){return recoveryError;},get recoveryRaw(){return [...recoveryRaw];},persist,choose,inventory,settleCopy,storedBasis,get lastWriteError(){return storageError;},
  get disagreement(){return disagreement?disagreement.map(item=>({store:item.store,raw:item.raw,state:copy(item.state)})):null;},get recovered(){return recovered?{...recovered}:null;},get retained(){return retained;},canChoose,
  get conflict(){return conflict?{stored:conflict.stored.map(item=>({...item}))}:null;},
  reset(initial){if(blocked())throw Error(blocked());if(feedbackUnresolved(state))throw Error('Check the original comment request before replacing this draft.');state=copy(initial);persist();return snapshot();},
  update(fields){state={...state,...copy(fields)};persist();return snapshot();},
  async retain(payload,lookup){if(blocked())throw Error(blocked());if(feedbackUnresolved(state))throw Error('Check the original comment request before submitting another one.');const pending=await retainFeedbackSubmission(payload,lookup);
   // Re-check after the awaited digest: typing during it stays; a conflict or another request refuses before anything is held.
   if(blocked())throw Error(blocked());if(feedbackUnresolved(state))throw Error('Another comment request was retained while this one was prepared; nothing was sent.');
   const basis=Object.fromEntries(stores.map(([name,store])=>[name,now(store)?.raw??null]));state={...state,pending};if(persist())return copy(pending);
   // Field-local rollback ONLY of this exact attempt when no store changed: it was never retained and is never sent, so it is
   // no phantom request. Any changed store is ambiguous writeback and the attempt stays as custody.
   if(state.pending===pending&&stores.every(([name,store])=>(now(store)?.raw??null)===basis[name]))state={...state,pending:null};else retained=null;
   throw Error(blocked()||storageError||'This comment request could not be retained; nothing was sent.');},
  async pendingPayload(){if(blocked())throw Error(blocked());const payload=await retainedFeedbackPayload(state.pending);if(!persist())throw Error(blocked()||storageError||'This comment draft could not be retained; nothing was sent.');return payload;},
  // Pure: the exact retained original payload of one slot, digest-checked, with no write (every Check uses this).
  async payloadOf(slot='pending'){if(!SLOTS.includes(slot)||!state[slot])throw Error('No retained request is selected.');return retainedFeedbackPayload(state[slot]);},
  observe(observation,identity=null){if(!state.pending)throw Error('No retained comment request is selected.');if(identity!==null&&feedbackRequestIdentity('pending',state.pending)!==identity)return false;state.pending={...state.pending,observation};return persist();},
  settle(receipt,extra={}){state={...state,...copy(extra),receipt:copy(receipt),pending:null};persist();return snapshot();}
 };
}
const canonical=value=>Array.isArray(value)?value.map(canonical):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonical(value[key])])):value;
// The owner revision join (laplace.feedback-revision-join/1, work.feedback_route.revision_join) as reader text and exact
// owner read links. Pure and DOM-free: it validates identity (project, producer turn), never infers a missing link and never
// mints an action; production, application, build and comment disposition stay separate facts.
const REVISION_JOIN='laplace.feedback-revision-join/1';
const REVISION_STATES={NO_ADMITTED_PRODUCER:'No producer has started for this review yet.',
 NOT_APPLICABLE:'This reviewer returns a research result, not a manuscript proposal.',
 UNAVAILABLE:'The revision chain is unavailable.',NOT_PRODUCED:'No proposal was produced by this review.',
 NOT_APPLIED:'A proposal was produced; it has not been applied.',
 APPLICATION_INCOMPLETE:'An application was attempted but its source effect is incomplete; inspect it before any new action.',
 NOT_BUILT:'Applied to source; no recorded build shows these exact bytes yet.',
 BUILT:'Applied, and a recorded build shows these exact bytes.'};
function revisionOwnerURL(handle,project){
 const url=handle?.http?.url;if(typeof url!=='string'||(handle.http.method||'GET')!=='GET'||!/^\/(authoring|work)\//.test(url))return null;
 const query=new URLSearchParams(url.split('?')[1]||'');return query.get('project')===project?url:null;
}
// A resolved successor (revision_join resolved_successors): a separately authored current-source revision of an exact
// predecessor version/edit, with its OWN application and build. Shown beside, never instead of, the original direct facts.
const SUCCESSOR_STATES={NOT_APPLIED:'not applied',APPLICATION_INCOMPLETE:'application incomplete; inspect it before any new action',
 NOT_BUILT:'applied to source; no recorded build shows these exact bytes yet',BUILT:'applied, and a recorded build shows these exact bytes'};
function successorLines(lineage,{revision,project,add,builds,lines}){
 if(lineage==null||lineage.state==='NONE')return;
 if(!['COMPLETE','PARTIAL'].includes(lineage.state))throw Error('The resolved successor lineage reports an unknown state.');
 for(const item of lineage.items||[]){
  const ref=item.candidate_ref||{},pred=item.predecessor||{};
  if(pred.turn_id!==undefined&&typeof revision.turn_id==='string'&&pred.turn_id!==revision.turn_id)throw Error('The resolved successor names another predecessor turn.');
  if(!Object.hasOwn(SUCCESSOR_STATES,item.state))throw Error('The resolved successor reports an unknown state.');
  add('Read resolved successor '+String(ref.id||''),item.read,'successor');
  lines.push('Resolved successor '+String(ref.id||'')+' (a separately authored current-source revision of edit '+String(pred.edit_id||'')+'): '+SUCCESSOR_STATES[item.state]+'.'+(revision.links?.applied===false?' The original version itself stays unapplied.':' The original version keeps its own application facts above.'));
  for(const application of item.applications||[]){
   const effect=application.source_effect||{},build=application.build||{};
   add('Read successor application '+application.id,application.read,'successor-application');
   if(build.state==='BUILT'){add('Read successor build status '+String(build.build_job?.id||''),build.job_status_read,'successor-build');const url=revisionOwnerURL(build.job_status_read,project);if(url&&!builds.some(row=>row.url===url))builds.push({id:String(build.build_job?.id||''),application:String(application.id||''),url});}
   lines.push('Successor application '+application.id+': source effect '+String(effect.state||'UNAVAILABLE').toLowerCase()+(effect.complete?' (complete)':' (incomplete)')
    +' · build '+String(build.state||'UNAVAILABLE').toLowerCase().replaceAll('_',' ')+(build.reason?' — '+build.reason:''));
  }
  for(const row of item.mismatched_applications||[])lines.push('Application '+row.id+' does not name this exact successor version and is not counted.');
  if(item.deeper?.state==='PARTIAL'){lines.push('A later resolution of this successor exists and is not expanded here.');add('Read the later resolution lineage',item.deeper.next_read,'successor-next');}
 }
 if(lineage.state==='PARTIAL'){lines.push(String(lineage.omitted)+' further resolved successor'+(lineage.omitted===1?' is':'s are')+' not shown; read the predecessor proposal.');add('Read the predecessor proposal for further successors',lineage.continuation?.next_read,'successor-next');}
}
export function feedbackRevisionSummary(revision,{project,turnId=null}={}){
 if(revision==null)return null;
 if(revision.schema_version!==REVISION_JOIN||(revision.project!==undefined&&revision.project!==project)||(turnId&&revision.turn_id!==undefined&&revision.turn_id!==turnId))
  throw Error('The revision chain belongs to another project or producer turn.');
 if(!Object.hasOwn(REVISION_STATES,revision.state))throw Error('The revision chain reports an unknown state.');
 const links=[],inspect=[],builds=[],add=(label,handle,kind)=>{const url=revisionOwnerURL(handle,project);if(url&&!links.some(link=>link.url===url))links.push({label,url,kind});};
 const lines=[REVISION_STATES[revision.state]+(revision.reason?' '+revision.reason:'')];
 for(const proposal of revision.proposals||[]){
  add('Read proposal '+String(proposal.version||'').slice(7,19),proposal.read,'proposal');
  // consumption through the existing read-only proposal preview of THIS producer turn and exact version; never an apply
  if(typeof revision.turn_id==='string'&&typeof proposal.version==='string'&&!inspect.some(item=>item.version===proposal.version))
   // the owner-issued exact proposal read travels with the item so the canonical project Review controller can open it
   inspect.push({turnId:revision.turn_id,version:proposal.version,label:'Inspect proposal '+proposal.version.slice(7,19)+' in manuscript',
    read:revisionOwnerURL(proposal.read,project)?JSON.parse(JSON.stringify(proposal.read)):null});
  for(const application of proposal.applications||[]){
   const effect=application.source_effect||{},build=application.build||{};
   add('Read application '+application.id,application.read,'application');
   if(build.state==='BUILT')add('Read build status '+String(build.build_job?.id||''),build.job_status_read,'build');
   // the same build owner job_status_read Figures & output follows; checked on request, never inferred from BUILT
   if(build.state==='BUILT'){const url=revisionOwnerURL(build.job_status_read,project);if(url&&!builds.some(item=>item.url===url))builds.push({id:String(build.build_job?.id||''),application:String(application.id||''),url});}
   lines.push('Application '+application.id+': source effect '+String(effect.state||'UNAVAILABLE').toLowerCase()+(effect.complete?' (complete)':' (incomplete)')
    +' · build '+String(build.state||'UNAVAILABLE').toLowerCase().replaceAll('_',' ')+(build.reason?' — '+build.reason:''));
  }
  successorLines(proposal.resolved_successors,{revision,project,add,builds,lines});
 }
 for(const row of revision.unattributed_applications||[])lines.push('Application '+row.id+' is not attributed to a proposal of this review and is not counted as applied.');
 add('Inspect the next owner read',revision.next_read,'next');
 lines.push('Production, application and build are separate facts; none is your disposition of the comment or review acceptance.');
 const facts=revision.links||{};
 return {state:revision.state,lines,links,inspect,builds,produced:facts.produced===true,applied:facts.applied===true,built:facts.built===true,
  successor:String(revision.resolved_successors?.state||'NONE')};
}
// The build owner's own job status for a chain build fact, as reader facts only. Fresh needs BOTH the owner's fresh and
// a job basis equal to today's compile scope; nothing is inferred from the chain's BUILT match or from a latest PDF.
export function feedbackBuildFreshness(status,{project}){
 if(!status||typeof status!=='object'||Array.isArray(status)||(status.project!==undefined&&status.project!==project))throw Error('The build status belongs to another project.');
 const yes=value=>value===true?'yes':value===false?'no':'not reported',fresh=status.fresh===true&&status.job_basis_current===true;
 const lines=['Build state: '+String(status.state||'not reported').toLowerCase().replaceAll('_',' ')+(status.running===true?' (running)':'')+' · fresh: '+yes(status.fresh)+' · job basis is today\'s source: '+yes(status.job_basis_current)+'.',
  fresh?'Figures & output reads the current PDF of this build basis while it stays fresh.':'Figures & output would not show these exact bytes until a new build of today\'s source.'];
 if(typeof status.reason==='string'&&status.reason)lines.push(status.reason);
 lines.push('A build is not review or scientific acceptance.');
 return {fresh,lines};
}
export const sameFeedbackValue=(left,right)=>JSON.stringify(canonical(left))===JSON.stringify(canonical(right));
export async function feedbackOriginReceipt(value,pending){
 const payload=await retainedFeedbackPayload(pending),receipt=value?.receipt||value;
 if(value?.effect&&value.effect!=='RECORDED')return null;
 if(receipt?.effect!=='RECORDED'||receipt.project!==payload.project||receipt.request_id!==payload.request_id||receipt.origin_ref?.project!==payload.project||receipt.correction?.id!==receipt.origin_ref.correction_id||receipt.correction?.text!==payload.text.trim()||receipt.correction?.kind!==payload.kind||receipt.correction?.scope!==payload.scope||!sameFeedbackValue(receipt.source_basis,payload.source_basis)||!sameFeedbackValue(receipt.correction.anchor,payload.anchor)||!sameFeedbackValue(receipt.review_route_spec??null,payload.review_route??null))throw Error('The comment receipt does not match the retained original submission. Keep its exact request for inspection.');
 return copy(receipt);
}
export async function feedbackLookupURL(pending,kind='origin'){
 const payload=await retainedFeedbackPayload(pending),path=feedbackHTTP(pending.lookup,{project:payload.project,paths:[kind==='origin'?'/authoring/correction-request':'/work/delivery']}),url=new URL(path,'http://local');
 if(kind==='origin'){
  if([...url.searchParams.keys()].some(key=>url.searchParams.getAll(key).length!==1)||url.searchParams.get('request_id')!==payload.request_id||url.searchParams.get('ledger')!==payload.source_basis?.ledger||[...url.searchParams.keys()].some(key=>!['project','request_id','ledger'].includes(key)))throw Error('The retained origin lookup changed its request or canonical home.');
 }else{
  if(url.searchParams.getAll('request').length!==1)throw Error('The retained lookup repeats its request.');let read;try{read=JSON.parse(url.searchParams.get('request'));}catch{throw Error('The retained route lookup is not an exact owner request.');}
  if(read?.action!=='route-status'||read.work_id!==payload.work_id||read.request_id!==payload.request_id||(read.request_kind||'route')!==(kind==='policy'?'policy':'route')||Object.keys(read).some(key=>!['action','work_id','request_id','request_kind'].includes(key)))throw Error('The retained review lookup changed its Work, request or request kind.');
 }
 return path;
}
export async function feedbackRouteReceipt(value,pending,origin){
 const payload=await retainedFeedbackPayload(pending),aggregate=value?.aggregate;
 if(!['route_recorded','RECORDED'].includes(value?.effect)||aggregate?.schema_version!=='laplace.feedback-route/1'||aggregate.project!==payload.project||aggregate.work?.id!==payload.work_id||!sameFeedbackValue(aggregate.origin?.origin_ref,origin)||typeof aggregate.route_id!=='string'||!aggregate.route_id||value.route_id&&value.route_id!==aggregate.route_id)throw Error('The review receipt does not match the original comment and Work request.');
 if(payload.policy_id&&(aggregate.policy?.id!==payload.policy_id||aggregate.policy?.revision!==payload.expected_policy_revision))throw Error('The review receipt consumed another saved author policy.');
 if(payload.policy&&['mode','recipients','limits'].some(key=>!sameFeedbackValue(payload.policy[key],aggregate.policy?.[key])))throw Error('The review receipt consumed another authored policy.');
 return copy(value);
}
export function bindFeedbackLookup(handle,requestId){
 const read=copy(handle);if(read.requires?.includes('request_id')){if(!read.http?.query||Object.hasOwn(read.http.query,'request_id'))throw Error('The comment owner did not issue a bindable request lookup.');read.http.query.request_id=requestId;read.requires=read.requires.filter(key=>key!=='request_id');}return read;
}
export async function feedbackTerminalOutcome(value,pending){
 const payload=await retainedFeedbackPayload(pending);
 if(value?.effect!=='NOT_ADMITTED'||value.terminal!==true||value.receipt!==null||value.project!==payload.project||value.request_id!==payload.request_id||value.ledger!==payload.source_basis?.ledger||!/^sha256:[0-9a-f]{64}$/.test(value.intent_sha256||'')||value.settlement?.code!=='AUTHOR_SETTLED_UNCOMMITTED_REQUEST'||typeof value.settlement.id!=='string'||!value.settlement.id||value.settlement.by!=='author')throw Error('The owner did not establish terminal non-admission for this exact original request.');
 await feedbackLookupURL({...pending,lookup:value.reconcile},'origin');
 return {outcome:copy(value),submission:copy(pending)};
}
