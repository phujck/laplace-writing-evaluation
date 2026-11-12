// Interpretation of the published research/Work receipts only. Generic HTTP
// status, source currentness and matching visible text do not settle a request.
import {copy,equal} from './research-workbench-state.mjs';
import {sourceEffectDisposition} from './source-effect.mjs';
import {workflowConversationAction} from './workflow-port.mjs';
import {feedbackWireDigest} from './feedback-route-port.mjs';
const canonical=value=>Array.isArray(value)?value.map(canonical):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonical(value[key])])):value;
export async function projectedIntent(payload,projection){
  if(projection?.algorithm!=='sha256-canonical-json-utf8'||!Array.isArray(projection.excluded_fields)||projection.excluded_fields.some(key=>typeof key!=='string'))return null;
  const value=copy(payload);for(const key of projection.excluded_fields)delete value[key];return feedbackWireDigest(JSON.stringify(canonical(value)));
}
export function retainedOutcome(value){
  if(value?.request_receipt)value={...value,...value.request_receipt};
  const out={};for(const key of ['schema_version','operation','project','work_id','request_id','intent_sha256','state','effect','terminal','record_id','reference','basis','read','reconcile','settle','new_decision_read','reason_code','error','meaning','status','destination','manifest_digest','receipt_sha256','counts','qualification','run_read','id','turn_id','candidate_version','complete','source_effect','historical','current_read'])if(value?.[key]!==undefined)out[key]=copy(value[key]);
  if(value?.schema_version==='laplace.project-data-handover/2')for(const key of ['intent','export','inspect','continue','checkpoint','progress','resources','endpoints','definitions','accounting','staging_accounting','origin_reads','providers_started'])if(value[key]!==undefined)out[key]=copy(value[key]);
  if(value?.event?.record_id)out.event={record_id:value.event.record_id};
  if(value?.receipt){out.receipt={};for(const key of ['request_id','intent_sha256','phase_id','action','read'])if(value.receipt[key]!==undefined)out.receipt[key]=copy(value.receipt[key]);if(value.receipt.binding)out.receipt.binding={id:value.receipt.binding.id,revision:value.receipt.binding.revision};}
  return out;
}
export function workbenchOutcome(value,pending){
  const payload=pending.payload;
  if(value?.request_receipt)return workbenchOutcome(value.request_receipt,pending);
  const route=new URL(pending.url,globalThis.location?.href||'http://local/');
  if(['/research/run','/research/record'].includes(route.pathname)){
    const project=route.searchParams.get('project');let read;try{read=new URL(value?.read?.http?.url||'',globalThis.location?.href||'http://local/');}catch{}
    let original;try{original=JSON.parse(read?.searchParams.get('request')||'null');}catch{}
    if(!project||value?.request_id!==payload.request_id||!equal(value?.original_request,payload)||read?.pathname!==route.pathname+'/request'||read.searchParams.get('project')!==project||!equal(original,payload))return {state:'UNKNOWN'};
    if(value.effect==='NONE')return {state:'NONE'};
    if(route.pathname==='/research/run'&&value.effect==='RECORDED'&&value.run?.id===value.id&&value.run.project===project&&value.run.request_id===payload.request_id&&value.run.producer_id===payload.producer_id&&value.run.request_intent===value.intent_digest)return {state:'RECORDED'};
    if(route.pathname==='/research/record'&&value.effect==='RECORDED'&&value.record?.id===payload.record.id&&value.record.run_id===payload.record.run_id&&value.record.record_request?.request_id===payload.request_id&&value.record.record_request.intent_digest===value.intent_digest&&/^sha256:[a-f0-9]{64}$/.test(value.record.revision||''))return {state:'RECORDED'};
    return {state:'UNKNOWN'};
  }
  if(payload.action==='workflow-compose-start'&&value?.action){
    try{const action=workflowConversationAction(value.action,payload.project),native=action.action_context.native.payload;if(native.work_id===payload.work_id&&native.request_id===payload.request_id&&equal(native.recipients,payload.recipients))return {state:'PREPARED',composer_action:action};}catch{}return {state:'UNKNOWN'};
  }

  if(value?.schema_version==='laplace.research-object-mutation/1'||pending.url==='/work/object-change'&&['bind-consumed','mark-reconsideration','clear-reconsideration'].includes(payload.operation)&&value?.operation===payload.operation){
    if(value.project!==payload.project||value.request_id!==payload.request_id||!equal(value.original_request,payload))return {state:'UNKNOWN'};
    if(value.state==='NONE')return {state:'NONE'};
    if(value.terminal===true&&value.record_id&&['RECORDED','NOT_ADMITTED'].includes(value.state))return {state:value.state};
    if(value.terminal===true&&value.event?.record_id&&value.state==='RECORDED')return {state:'RECORDED'};
    return {state:'UNKNOWN'};
  }
  if(pending.url==='/authoring/apply'){
    if(value?.project===payload.project&&value.turn_id===payload.turn_id&&value.candidate_version===payload.proposal_version&&value.id&&value.complete===true&&sourceEffectDisposition(value,{project:payload.project})?.acknowledged)return {state:'RECORDED'};
    if(value?.schema_version==='laplace.research-workflow-run/1'&&value.work?.id===pending.action.run_work_id&&value.work?.project===payload.project&&value.state==='APPLIED'&&value.proposal?.turn_id===payload.turn_id&&value.proposal?.proposal_version===payload.proposal_version)return {state:'RECORDED'};
  }
  if(pending.url==='/work/object-handover'){
    if(payload.action==='prepare'){
      if(value?.state==='NONE'&&value.request_id===payload.request_id)return {state:'NONE'};
      if(value?.schema_version==='laplace.research-handover/1'&&value.project===payload.project&&value.request_id===payload.request_id&&value.state==='RECORDED'&&pending.intent_sha256&&value.intent_sha256===pending.intent_sha256)return {state:'RECORDED'};
    }else if(payload.action==='export'){
      if(value?.state==='NONE'&&value.terminal===false)return {state:'NONE'};
      if(value?.state==='COMPLETE_MATCH'||value?.status==='EXPORTED'&&typeof (value.manifest_digest||value.receipt)==='string')return {state:'RECORDED'};
    }
  }
  if(value?.project===payload.project&&value.work_id===payload.work_id&&value.request_id===payload.request_id){
    if(value.effect==='NONE'&&value.receipt==null)return {state:'NONE'};
    if(value.effect==='RECORDED'&&value.receipt?.request_id===payload.request_id&&pending.intent_sha256&&value.receipt.intent_sha256===pending.intent_sha256)return {state:'RECORDED'};
  }
  return {state:'UNKNOWN'};
}

// The response root is a current owner observation only when explicitly marked.
// A receipt.run is historical and is never used as the current projection.
export function currentWorkflowProjection(value,payload){
  const view=value?.current_projection;if(view?.schema_version!=='laplace.current-projection/1'||view.kind!=='workflow-run'||view.location!=='response-root'||view.observation!=='AT_OWNER_RESPONSE'||view.project!==payload.project||view.work_id!==payload.work_id||value?.schema_version!=='laplace.research-workflow-run/1'||value.work?.project!==payload.project||value.work.id!==payload.work_id||value.revision!==view.basis||value.plan_generation!==view.plan_generation)return null;
  try{const url=new URL(value.read.http.url,globalThis.location?.href||'http://local/'),request=JSON.parse(url.searchParams.get('request'));if(value.read.http.method!=='GET'||url.pathname!=='/work/delivery'||url.searchParams.get('project')!==payload.project||request.action!=='workflow-status'||request.work_id!==payload.work_id)return null;}catch{return null;}return value;
}

// Opt-in handover/v2 uses the same exact-wire attempt owner as other forms.
// These checks establish which issued next action may be presented; they never
// derive a stage path, repair progress or infer completion from HTTP success.
const lineageSchema='laplace.project-data-handover/2',lineagePin=value=>typeof value==='string'&&/^sha256:[a-f0-9]{64}$/.test(value);
const lineageBase=value=>Object.fromEntries(Object.entries(copy(value)).filter(([key])=>!['action','expected_checkpoint'].includes(key)));
export function checkedLineageTransferHandle(handle,{action=null,original=null,checkpoint=null}={}){
 const here=new URL(globalThis.location?.href||'http://local/'),url=new URL(handle?.http?.url||'',here),payload=handle?.http?.payload;
 const allowed=['action','definition_transport','project','request_id','definitions','reference','expected_basis','destination','max_files','max_rows','max_bytes','expected_lineage_basis','expected_checkpoint','cell_rows','cell_bytes','cell_seconds','capture_max_bytes','metadata_max_rows','max_staged_bytes'];
 if(handle?.http?.method!=='POST'||url.origin!==here.origin||url.pathname!=='/work/object-handover'||url.search||url.hash||url.username||url.password||!payload||Array.isArray(payload)||payload.definition_transport!=='lineage-v2'||!['request','export','continue','inspect'].includes(payload.action)||action&&payload.action!==action||Object.keys(payload).some(k=>!allowed.includes(k))||typeof payload.request_id!=='string'||!payload.request_id||typeof payload.destination!=='string'||!payload.destination)throw Error('The owner issued no closed lineage handover action.');
 if(['max_files','max_rows','max_bytes','capture_max_bytes','metadata_max_rows','max_staged_bytes'].some(k=>payload[k]!==undefined&&(!Number.isSafeInteger(payload[k])||payload[k]<1))||['max_files','max_rows','max_bytes'].some(k=>payload[k]===undefined)||payload.cell_rows!==undefined&&(!Number.isSafeInteger(payload.cell_rows)||payload.cell_rows<1||payload.cell_rows>32)||payload.cell_bytes!==undefined&&(!Number.isSafeInteger(payload.cell_bytes)||payload.cell_bytes<1||payload.cell_bytes>1000000)||payload.cell_seconds!==undefined&&(!Number.isFinite(payload.cell_seconds)||payload.cell_seconds<=0||payload.cell_seconds>30))throw Error('The lineage handover has invalid admitted resource limits.');
 if(payload.action!=='request'&&!lineagePin(payload.expected_lineage_basis)||payload.action==='continue'&&(!lineagePin(payload.expected_checkpoint)||checkpoint&&payload.expected_checkpoint!==checkpoint)||payload.action!=='continue'&&payload.expected_checkpoint!==undefined||original&&!equal(lineageBase(payload),lineageBase(original)))throw Error('The lineage action changed the original wire, basis or checkpoint.');
 if(handle.native&&(handle.native.operation!=='research_handover'||!equal(handle.native.payload,payload))||handle.sdk&&(handle.sdk.method!=='research_handover'||!equal(handle.sdk.payload,payload)))throw Error('The lineage action companions changed the original payload.');
 return {url:url.pathname,payload:copy(payload)};
}
export async function lineageTransferOutcome(value,pending){
 if(value?.schema_version!==lineageSchema)return {state:'UNKNOWN'};
 const payload=pending.payload,scope=pending.lineage_scope_id,binding=pending.lineage_binding;
 if(payload.action==='request'){
  if(value.state!=='PREPARED'||value.effect!=='none'||!lineagePin(scope)||value.resources?.source_scope_id!==scope||!lineagePin(value.intent))return {state:'UNKNOWN'};
  try{
   const offered=checkedLineageTransferHandle(value.export,{action:'export'}),inspect=checkedLineageTransferHandle(value.inspect,{action:'inspect',original:offered.payload});
   if(Object.entries(payload).some(([key,entry])=>key!=='action'&&!equal(entry,offered.payload[key]))||!Array.isArray(value.endpoints)||!value.endpoints.length)return {state:'UNKNOWN'};
   if(!Number.isSafeInteger(value.resources?.rows)||value.resources.rows<1||value.resources.rows>offered.payload.max_rows)return {state:'UNKNOWN'};
   if(payload.definitions&&!equal(payload.definitions,value.endpoints.map(row=>row.reference)))return {state:'UNKNOWN'};
   // The wire contains authored safe numbers and opaque owner pins, not the
   // plan's filesystem stamps (whose large integers must not be reinterpreted).
   const wire={...lineageBase(offered.payload),source_scope_id:scope};if(await feedbackWireDigest(JSON.stringify(canonical(wire)))!==value.intent)return {state:'UNKNOWN'};
   return {state:'PREPARED',lineage_binding:{intent:value.intent,scope_id:scope,export:copy(value.export),inspect:copy(value.inspect),endpoints:copy(value.endpoints),row_limit:value.resources.rows}};
  }catch{return {state:'UNKNOWN'};}
 }
 if(!binding||binding.scope_id!==scope||value.intent!==binding.intent||value.destination!==binding.export?.http?.payload?.destination)return {state:'UNKNOWN'};
 try{checkedLineageTransferHandle(pending.action,{original:binding.export.http.payload});}catch{return {state:'UNKNOWN'};}
 if(value.state==='PARTIAL'){
  try{if(value.terminal!==false||!lineagePin(value.checkpoint)||!['capture','assemble','inventory','publish'].includes(value.progress?.phase)||!Number.isSafeInteger(value.progress.row_cursor)||value.progress.row_cursor<0||value.progress.row_cursor>binding.row_limit||value.progress.phase!=='capture'&&value.progress.row_cursor!==binding.row_limit||!Number.isSafeInteger(value.progress.cells)||value.progress.cells<1)return {state:'UNKNOWN'};
   checkedLineageTransferHandle(value.continue,{action:'continue',original:binding.export.http.payload,checkpoint:value.checkpoint});checkedLineageTransferHandle(value.inspect,{action:'inspect',original:binding.export.http.payload});return {state:'PARTIAL',lineage_binding:copy(binding)};
  }catch{return {state:'UNKNOWN'};}
 }
 if(value.state==='COMPLETE'&&value.terminal===true&&lineagePin(value.receipt_sha256)&&Array.isArray(value.definitions)&&equal(value.definitions.map(row=>row.reference),binding.endpoints.map(row=>row.reference))&&value.definitions.every((row,i)=>row.versions===binding.endpoints[i].known)&&['files','rows','bytes'].every(key=>Number.isSafeInteger(value.counts?.[key])&&value.counts[key]>=0&&value.counts[key]<=binding.export.http.payload['max_'+key]))return {state:'COMPLETE',lineage_binding:copy(binding)};
 // NONE, UNKNOWN, CHANGED_INPUT and malformed progress grant no retry/Continue.
 return {state:'UNKNOWN'};
}
