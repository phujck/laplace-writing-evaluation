// Read-side consumer of the workflow owner's closed operation offers. An offer
// is data, not permission. This adapter never saves, prepares, starts or retries.
import {feedbackWireDigest} from './feedback-route-port.mjs';
import {workflowStopRecovery} from './research-workbench-state.mjs';
import {pendingRead} from './pending-read.mjs';
import {ownerStateWord} from './workspace-presentation.mjs';
const copy=structuredClone;
const ordered=value=>Array.isArray(value)?value.map(ordered):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(key=>[key,ordered(value[key])])):value;
export const sameWorkflowOperation=(a,b)=>JSON.stringify(ordered(a))===JSON.stringify(ordered(b));
const equal=sameWorkflowOperation;
const SHA=/^sha256:[a-f0-9]{64}$/;
const facets=new Set(['execution-preview','uses','river','context','creation-choices','withdrawal-preview']);
const keys=new Set(['facet','reference','definition_id','version','project_lens','definition','scope','step_ids','work_id','versions','offset','limit','as_of','step_id','request_token','operation','original_request']);
const here=()=>new URL(globalThis.location?.href||'http://local/project');

export function workflowOperationRequest(offer,inputs={}){
 const handle=offer?.read||offer?.prepare_read||offer,allowed=offer?.required_inputs||handle?.required_inputs||[];
 if(!handle||!Array.isArray(allowed)||Object.keys(inputs).some(key=>!allowed.includes(key))||allowed.some(key=>!Object.hasOwn(inputs,key)))throw Error('Use the exact inputs requested by the workflow owner.');
 const url=new URL(handle.http?.url||'',here()),method=handle.http?.method;
 if(url.origin!==here().origin||url.pathname!=='/work/workflow-definitions'||url.hash||url.username||url.password||!['GET','POST'].includes(method)||[...url.searchParams.keys()].some(key=>url.searchParams.getAll(key).length!==1))throw Error('The workflow operation read has invalid transport coordinates.');
 let base;
 if(method==='POST'){
  if(handle.read_only!==true||!handle.http.payload||Object.keys(Object.fromEntries(url.searchParams)).length)throw Error('A workflow operation POST must be an explicitly pure owner read.');base=copy(handle.http.payload);
 }else{
  base={};for(const [key,text]of url.searchParams){if(!keys.has(key))throw Error('The workflow read contains an unknown field.');base[key]=['reference','scope','definition','step_ids'].includes(key)?JSON.parse(text):['offset','limit'].includes(key)?Number(text):text;}
 }
 if(handle.request&&!equal(handle.request,base)||handle.native&&(handle.native.operation!=='project'||handle.native.payload?.view!=='workflow-definitions'||!equal(handle.native.payload.request,base))||handle.sdk&&(handle.sdk.method!=='workflow_request'||!equal(handle.sdk.payload,base)))throw Error('The workflow read carriers disagree.');
 if(Object.keys(inputs).some(key=>Object.hasOwn(base,key)))throw Error('An authored input cannot replace an owner read coordinate.');
 const payload={...base,...copy(inputs)};
 if(!facets.has(payload.facet)||Object.keys(payload).some(key=>!keys.has(key))||payload.limit!==undefined&&(!Number.isSafeInteger(payload.limit)||payload.limit<1||payload.limit>20)||payload.offset!==undefined&&(!Number.isSafeInteger(payload.offset)||payload.offset<0))throw Error('This workflow operation is outside the closed read contract.');
 if(payload.definition&&(!['execution-preview','context'].includes(payload.facet)||method!=='POST'))throw Error('A draft body must use its offered pure POST, never a generated URL.');
 return {url:url.pathname+url.search,method,payload,wire:method==='POST'?JSON.stringify(payload):null};
}

export function checkedWorkflowOperation(value,read,expected={}){
 const request=read.payload;
 if(value?.schema_version!=='laplace.workflow-operation/1'||value.view!==request.facet||value.read_only!==true||typeof value.scope_id!=='string'||expected.scope_id&&value.scope_id!==expected.scope_id)throw Error('The workflow operation reply belongs to another scope or view.');
 if(request.definition){if(value.reference!==null||!equal(value.scope,request.scope))throw Error('The draft preview returned another ownership basis.');}
 else if(request.reference&&!equal(value.reference,request.reference)||expected.reference&&!equal(value.reference,expected.reference))throw Error('The workflow operation returned another saved version.');
 if(request.facet==='execution-preview'){
  if(!['SUPPORTED_CONFIGURATION','REFUSED_CONFIGURATION'].includes(value.support)||value.execution_permitted!==false||!SHA.test(value.basis||'')||!SHA.test(value.definition_digest||'')||!Array.isArray(value.issues)||!Array.isArray(value.roles)||!equal(value.selected_step_ids,request.step_ids||request.definition?.steps.map(row=>row.id)||value.selected_step_ids))throw Error('The workflow preview omitted its exact configuration basis.');
  const ids=value.roles.map(row=>row.step_id),coverage=value.role_coverage||{known:value.selected_step_ids.length,offset:0,returned:ids.length};if(!Number.isSafeInteger(coverage.offset)||coverage.offset!==(request.offset||0)||coverage.known!==value.selected_step_ids.length||coverage.returned!==ids.length||new Set(ids).size!==ids.length||!equal(ids,value.selected_step_ids.slice(coverage.offset,coverage.offset+ids.length)))throw Error('The preview roles do not cover their selected step positions.');if(expected.basis&&value.basis!==expected.basis||expected.definition_digest&&value.definition_digest!==expected.definition_digest)throw Error('The preview continuation changed its exact design basis.');
 }
 if(request.facet==='withdrawal-preview'&&(value.effect!=='none'||value.request_id!==request.original_request?.request_id||value.operation!==request.operation||!SHA.test(value.intent_digest||'')||value.withdraw?.http?.payload?.request_id!==value.request_id||value.withdraw?.http?.payload?.intent_digest!==value.intent_digest))throw Error('The withdrawal preparation did not identify this original request.');
 if(request.facet==='context'){
  if(value.step_id!==request.step_id||!SHA.test(value.basis||'')||expected.basis&&value.basis!==expected.basis||typeof value.content!=='string'||value.offset!==(request.offset||0)||value.returned!==Array.from(value.content).length||!Number.isSafeInteger(value.total_characters)||value.offset+value.returned>value.total_characters||value.at_end!==(value.offset+value.returned===value.total_characters)||!value.at_end&&!value.next_read)throw Error('The context page changed its step, basis or position.');
 }
 if(['uses','river'].includes(request.facet)){
  if(!Array.isArray(value.items)||!Number.isSafeInteger(value.total)||value.total<value.items.length||request.work_id&&value.work_id!==request.work_id)throw Error('The workflow observation returned another run or an invalid page.');
  if(value.coverage!=='NO_PROJECT_EXECUTION_BINDING'&&(!SHA.test(value.cut||'')||value.offset!==(request.offset||0)||value.returned!==value.items.length||value.offset+value.returned>value.total||request.as_of&&value.cut!==request.as_of))throw Error('Workflow observations changed cut; pages were not mixed.');
 }
 return copy(value);
}

export async function readWorkflowOperation(offer,inputs,{request,expected={},isCurrent=()=>true}={}){
 const read=workflowOperationRequest(offer,inputs),wireHash=read.wire&&await feedbackWireDigest(read.wire);
 if(!isCurrent())return null;
 const value=await request(read.url,read.method==='POST'?copy(read.payload):undefined);
 if(!isCurrent())return null;
 // HTTP correlation is a hash of the exact posted bytes, not a claim that JS
 // and Python semantic JSON/float canonicalisation are interchangeable.
 if(wireHash&&(value?.transport_request?.encoding!=='utf8-exact-request-body'||value.transport_request.sha256!==wireHash))throw Error('The pure workflow reply did not identify this exact submitted request body.');
 return checkedWorkflowOperation(value,read,expected);
}

const el=(tag,text='',cls='')=>{const node=document.createElement(tag);node.textContent=text;node.className=cls;return node;};
const button=(label,run)=>{const node=el('button',label);node.type='button';node.onclick=run;return node;};
const detail=(label,value)=>{const node=el('details');node.append(el('summary',label),el('pre',JSON.stringify(value,null,2)));return node;};
// The one wording of the owner's execution-preview issues (Check execution and the Design view's route patterns).
export const issueText=row=>row.message||({ORIGINAL_PARENT_SYNTHESIS_REQUIRED:'This synthesis must run in the original parent; a separate synthesis child is not admitted.',ONE_ORIGINAL_PARENT_SYNTHESIS:'Choose one original-parent synthesis.',RESEARCH_REQUIRES_ONE_WRITER_AND_REVIEWER:'This review profile needs one writer and one reviewer.',DRAFT_REVIEW_EDGE_REQUIRED:'Connect the writer to its reviewer.',UNSUPPORTED_RESEARCH_TOPOLOGY:'These connections are not supported by this review profile.',SELECT_TWO_TO_EIGHT_CHILD_ROLES:'Choose two to eight supported child roles.',UNSUPPORTED_CONTROL_CYCLE:'Cyclic prerequisites cannot execute. Use an explicitly supported bounded feedback policy.',UNSUPPORTED_ROLE:'This profile does not execute that role.',UNSUPPORTED_CARRIER_DEPENDENCIES:'The declared dependencies do not match this execution profile.',UNSUPPORTED_CLOSED_CONTROL_INPUT:'A selected step has an unsupported or unselected input.',EXPLICIT_DELIVERY_PROFILE_REQUIRED:'This profile does not yet consume the declared context or handoff.',INSTRUCTION_REQUIRED:'Add instructions before execution.',UNCONSUMED_STEP_DECLARATION:'Some declared inputs, outputs or targets have no executable binding.',RESEARCH_EDGE_CROSSES_PAIRS:'This arrow joins different writer and reviewer pairs. Each reviewer reads and answers only its own writer.',RESEARCH_STEP_UNPAIRED:'This step has no writer and reviewer pair. Connect each writer to its own reviewer.',RESEARCH_REVIEWER_PER_WRITER:'Each writer needs exactly one reviewer of its own, and each reviewer one writer.',RESEARCH_PAIRS_PER_RUN:'This selection has more writer and reviewer pairs than one run takes.',UNSUPPORTED_SYNTHESIS_INPUT:'The synthesis reads selected steps through result arrows only.',EXTENDED_POLICY_REQUIRES_PARENT_SYNTHESIS:'This review policy needs one synthesis step, run in the original conversation.',CONTEXT_REQUIRES_EVIDENCE_PACKET_PROFILE:'Selected evidence and earlier findings are delivered only by the review profile.'}[row.code]||'Owner refusal: '+String(row.code||'configuration unavailable').replaceAll('_',' ').toLowerCase());

// An owner refusal (a 4xx reply carrying the owner's code, as workflowRequest throws it) as an issue row for issueText:
// the owner's own sentence is what its reply says after the code ('DEFINITION_BOUND: At most64steps and256edges').
// A reply without an owner code (no answer, 5xx, unknown effect) is not a refusal and gives null.
export function ownerRefusalIssue(error){
  const value=error?.result,code=value?.code;if(typeof code!=='string'||!(error.status>=400&&error.status<500))return null;
  const said=String(value.error||''),message=said.startsWith(code+': ')?said.slice(code.length+2).trim():'';
  return {code,...(message?{message}:{}),...(typeof value.step_id==='string'?{step_id:value.step_id}:{})};
}

// The ownership scope a draft is previewed in, and the check's own default selection (every step but groups).
export const workflowPreviewScope=state=>state?.read?.value?.scope||state?.draft?.basis?.payload?.scope||state?.listing?.scope;
export const workflowPreviewSteps=body=>(body?.steps||[]).filter(row=>row.assignment?.role!=='group').map(row=>row.id);

export function mountWorkflowCapability(host,{offer,snapshot,dispatch,request,isCurrent=()=>true,onDeclarations=()=>{}}){
 const panel=el('section','','workflow-execution-check'),status=el('p','Check the actual selected design before preparing a run. Saving and checking start no work.','workflow-hint'),output=el('div'),choices=el('details'),checks=new Map();status.setAttribute('role','status');choices.append(el('summary','Steps included in this check'));
 const source=()=>{const state=snapshot(),body=state.draft?.definition||state.read?.value?.definition,scope=workflowPreviewScope(state);return {state,body,scope,ids:state.context.preview_step_ids||workflowPreviewSteps(body)};};
 const key=()=>{const {state,body,scope,ids}=source();return JSON.stringify([state.selection?.id,body,scope,ids]);};
 let alive=true,epoch=0,loaded=null,boundKey=null,busy=false,contextVisit=null;
 const current=()=>alive&&panel.isConnected!==false&&isCurrent();
 const check=button('Check execution',()=>observe());check.dataset.control='workflow:preview';
 panel.append(el('h3','Execution check'),status,choices,check,output);host.append(panel);
 for(const step of source().body?.steps||[]){const label=el('label'),input=el('input'),title=el('span',step.title||step.id);input.type='checkbox';input.checked=source().ids.includes(step.id);input.onchange=()=>{const ids=[...checks].filter(([,row])=>row.input.checked).map(([id])=>id);dispatch({type:'context',fields:{preview_step_ids:ids}});};label.append(input,title);choices.append(label);checks.set(step.id,{input,title});}
 function inputs(handle,definition){const names=(handle?.read||handle)?.required_inputs||handle?.required_inputs||[];const values={definition};return Object.fromEntries(names.map(name=>{if(!Object.hasOwn(values,name))throw Error('The role read requests an unavailable input.');return [name,copy(values[name])];}));}
 function unchanged(observed){return current()&&key()===observed;}
 async function observe(handle=null){
  if(busy||!current())return false;const frozen=source(),observed=key(),ticket=++epoch,expected={scope_id:frozen.state.scope_id,...(handle?{basis:loaded?.basis,definition_digest:loaded?.definition_digest}:{})};busy=true;let laterIntent=false;const activation=document.activeElement,later=event=>{if(event.target!==activation&&event.target!==document.body)laterIntent=true;};for(const type of ['focusin','pointerdown','keydown'])document.addEventListener?.(type,later,true);check.disabled=true;pendingRead(status,'Checking this design without saving or starting…');
  try{const value=await readWorkflowOperation(handle||offer,handle?inputs(handle,frozen.body):{definition:copy(frozen.body),scope:copy(frozen.scope),step_ids:copy(frozen.ids)},{request,expected,isCurrent:()=>ticket===epoch&&unchanged(observed)});if(!value)return false;
   loaded=handle?{...value,roles:[...(loaded?.roles||[]),...value.roles],issues:[...(loaded?.issues||[]),...value.issues]}:value;boundKey=observed;onDeclarations(copy(value.declarations));paintResult();return true;
  }catch(error){if(ticket===epoch&&unchanged(observed))status.textContent='Execution check unavailable: '+error.message;return false;}finally{for(const type of ['focusin','pointerdown','keydown'])document.removeEventListener?.(type,later,true);if(ticket===epoch){busy=false;if(current()){check.disabled=false;if(!unchanged(observed))status.textContent='The design changed during this check. Check execution again.';if(!laterIntent&&activation===check&&document.activeElement===document.body&&unchanged(observed))check.focus?.({preventScroll:true});}}}
 }
 function paintResult(){
  if(!loaded||!unchanged(boundKey))return;contextVisit=null;output.replaceChildren();const refused=loaded.support==='REFUSED_CONFIGURATION';status.textContent=(refused?'This configuration is not executable by the selected profile.':'The owner supports this configuration.')+' This check grants no execution permission. Actual Prepare rechecks inputs, settings and authority.';
  const issues=el('ul');for(const row of loaded.issues){const item=el('li',issueText(row));if(row.step_id)item.append(el('span',' · '+(source().body.steps.find(step=>step.id===row.step_id)?.title||row.step_id)));issues.append(item);}if(loaded.issues.length)output.append(issues);
  const body=source().body,roleList=el('ol','','workflow-preview-roles');for(const role of loaded.roles){const shown=workflowRolePresentation(role,body),item=el('li');item.dataset.previewRole=role.step_id;item.append(el('strong',shown.name),el('span',' · '+shown.role+' · '+(shown.original_parent?'original parent':'admitted child')));paintRoleSummary(item,shown);if(role.context_read){const read=button('Inspect declared context',()=>readContext(role));read.dataset.control='workflow:context-read';item.append(read);}roleList.append(item);}output.append(roleList);paintFlowAndPolicy(output,body,loaded.declarations);
  if(loaded.next_read)output.append(button('Read more execution details',()=>observe(loaded.next_read)));
  output.append(el('p',(loaded.required_admission||[]).join(' · '),'workflow-hint'),el('p',loaded.mandatory_context||'','workflow-hint'),detail('Exact preview basis, coverage and refusals',loaded));
 }
 async function readContext(role,handle=null){
  if(busy||!loaded||!unchanged(boundKey))return false;const observed=boundKey,ticket=++epoch,frozen=source(),prior=handle?contextVisit:null;busy=true;
  try{const value=await readWorkflowOperation(handle||role.context_read,inputs(handle||role.context_read,frozen.body),{request,expected:{scope_id:frozen.state.scope_id,basis:loaded.basis},isCurrent:()=>ticket===epoch&&unchanged(observed)});if(!value)return false;
   if(prior&&value.offset!==prior.offset+prior.returned)throw Error('Context parts were not contiguous.');contextVisit=value;
   let reading=output.querySelector('.workflow-context-reading');if(!prior){reading?.remove();reading=el('section','','workflow-context-reading');reading.append(el('h4','Declared context · '+(role.title||role.step_id)),el('p',value.qualification,'workflow-hint'),el('pre','','workflow-context-text'));output.append(reading);}const text=reading.querySelector('.workflow-context-text');text.textContent+=(value.content||'');reading.querySelector('[data-context-next]')?.remove();reading.append(el('p',(value.offset+value.returned)+' of '+value.total_characters+' Unicode characters inspected. Actual admission inputs and permissions remain separate.','workflow-hint'));if(value.next_read){const next=button('Read next context part',()=>readContext(role,value.next_read));next.dataset.contextNext='';reading.append(next);}reading.append(detail('Declared context origin and size receipt',value.delivery));return true;
  }catch(error){if(ticket===epoch&&unchanged(observed))status.textContent='Declared context unavailable: '+error.message;return false;}finally{if(ticket===epoch)busy=false;}
 }
 function update(){if(!current())return;const fresh=source();for(const [id,row]of checks){row.input.checked=fresh.ids.includes(id);row.title.textContent=fresh.body?.steps.find(step=>step.id===id)?.title||id;}if(boundKey&&!unchanged(boundKey)){status.textContent='This design changed after the last check. Check execution again; the previous preview is retained as an old observation.';for(const node of output.querySelectorAll('button'))node.disabled=true;}check.disabled=busy;}
 return {check:()=>observe(),update,destroy(){alive=false;epoch++;},get value(){return loaded&&unchanged(boundKey)?copy(loaded):null;}};
}

// Joined explanation over actual owner declarations and offers. These helpers
// describe only: they never save, prepare, start, stop, withdraw or infer an effect.
const EDGE={control:'order',data:'input',feedback:'revision request'};
const EDGE_MEANING={control:'intended order',data:'intended input',feedback:'intended revision request'};
const CONTEXT_KIND={'ancestor-instructions':'Instructions from a containing group','upstream-return':'The returned result of an earlier step','selected-evidence':'Evidence or reading selected when the run is prepared','previous-review-findings':'Findings from the previous review round','parent-message':'The message from the original parent conversation'};
const ROLE_PURPOSE={builder:'Produces the work and returns it.',adversary:'Reviews the exact handoff it receives.',reviewer:'Reviews the exact handoff it receives.',synthesis:'Combines the returns into the final answer.',group:'Organises steps. A group runs nothing itself.'};
const REVIEW_NOTE='A reviewer judges the exact handoff it receives. A separate session still shares project context, so this is not blind review unless the owner reports a sealed reading.';
export function workflowContextChoices(declarations){
 const schema=declarations?.context,variants=schema?.items?.oneOf;if(!Array.isArray(variants))return null;
 const rows=[];for(const variant of variants){const needs=Array.isArray(variant?.required)&&variant.required.includes('step_id');for(const kind of variant?.properties?.kind?.enum||[])rows.push({kind,needs_step:needs,label:CONTEXT_KIND[kind]||kind});}
 return rows.length?{rows,max:Number.isSafeInteger(schema.maxItems)?schema.maxItems:null}:null;
}
export function workflowHandoffFields(declarations){
 const props=declarations?.handoff?.properties;if(!props||typeof props!=='object')return null;const bound=(row,key)=>row?{max:Number.isSafeInteger(row[key])?row[key]:null}:null;
 return {purpose:bound(props.purpose,'maxLength'),expected_output:bound(props.expected_output,'maxLength'),downstream:bound(props.downstream,'maxItems')};
}
// Run-policy limits come from the owner's declared variants (oneOf v1/v2, or a
// legacy single-object declaration). No limit is invented for an undeclared profile.
export function workflowPolicyVariants(declarations){
 const schema=declarations?.run_policy,list=Array.isArray(schema?.oneOf)?schema.oneOf:schema?.properties?[schema]:[];
 return list.filter(row=>typeof row?.properties?.profile?.const==='string').map(row=>({profile:row.properties.profile.const,properties:copy(row.properties),required:[...(row.required||[])]}));
}
export function workflowPolicyVariant(declarations,profile){return workflowPolicyVariants(declarations).find(row=>row.profile===profile)||null;}
export function workflowPolicyBounds(declarations){
 const variants=workflowPolicyVariants(declarations);if(!variants.length)return null;const range=row=>row&&Number.isSafeInteger(row.minimum)&&Number.isSafeInteger(row.maximum)?{min:row.minimum,max:row.maximum}:null;
 return {variants:variants.map(({profile,properties:p})=>({profile,iterations:range(p.max_iterations),runtime_seconds:range(p.runtime_seconds),admissions:range(p.max_admissions),deadline_seconds:range(p.deadline_seconds),advance:Array.isArray(p.advance?.enum)?[...p.advance.enum]:[],apply:p.apply?.const??null,criteria:['continuation_criteria','exit_criteria'].filter(key=>p[key])}))};
}
export function workflowPolicyText(bounds){
 if(!bounds?.variants?.length)return '';const open=row=>row.max>=Number.MAX_SAFE_INTEGER;
 return bounds.variants.map(row=>{const parts=[];if(row.iterations)parts.push('review rounds '+row.iterations.min+(open(row.iterations)?' or more, within your own limit':'–'+row.iterations.max));if(row.runtime_seconds)parts.push('up to '+row.runtime_seconds.max+' seconds per step');if(row.admissions)parts.push('at least '+row.admissions.min+' admitted steps, within your own limit');if(row.deadline_seconds)parts.push('a run deadline you set');if(row.criteria.length)parts.push('written continue and exit criteria');if(row.apply)parts.push('changes applied by '+(row.apply==='human'?'a person':row.apply));return row.profile+': '+parts.join(', ')+'.';}).join(' ')+' When a workflow carries a review policy, Design edits it within these limits.';
}
export function workflowConfiguredFlow(definition){
 const steps=definition?.steps||[],name=id=>steps.find(row=>row.id===id)?.title||id;
 return (definition?.edges||[]).map(row=>({id:row.id,from:name(row.from),to:name(row.to),kind:row.kind||'control',meaning:EDGE_MEANING[row.kind||'control']||'declared connection',state:'planned'}));
}
export function workflowRolePresentation(role,definition){
 const steps=definition?.steps||[],edges=definition?.edges||[],step=steps.find(row=>row.id===role?.step_id),name=id=>steps.find(row=>row.id===id)?.title||id;
 const authoredContext=step?.assignment?.context||[],authoredHandoff=step?.assignment?.handoff||{},echoContext=Array.isArray(role?.context)?role.context:[],echoHandoff=role?.handoff&&typeof role.handoff==='object'?role.handoff:{};
 const authored=authoredContext.length>0||Object.keys(authoredHandoff).length>0;
 return {step_id:role?.step_id,name:role?.title||step?.title||role?.step_id,role:role?.role||step?.assignment?.role||'unknown',purpose:ROLE_PURPOSE[role?.role]||null,
  original_parent:role?.execution_location==='original-parent',
  location:role?.execution_location==='original-parent'?'Runs in the original parent conversation, with that conversation’s admitted model, settings and authority.':role?.execution_location==='admitted-child'?'Runs as an admitted child session of the prepared run.':'Execution location reported by the owner: '+(role?.execution_location||'not stated')+'.',
  receives:edges.filter(row=>row.to===role?.step_id).map(row=>({from:name(row.from),kind:row.kind||'control'})),
  sends:edges.filter(row=>row.from===role?.step_id).map(row=>({to:name(row.to),kind:row.kind||'control'})),
  context:echoContext.map(row=>({kind:row.kind,label:CONTEXT_KIND[row.kind]||row.kind,from:row.step_id?name(row.step_id):null})),
  handoff:copy(echoHandoff),review:['adversary','reviewer'].includes(role?.role)?REVIEW_NOTE:null,
  inherits_from:role?.parent_id?name(role.parent_id):null,
  consumed:!authored?'none-authored':equal(authoredContext,echoContext)&&equal(authoredHandoff,echoHandoff)?'echoed':'not-echoed'};
}
function paintRoleSummary(item,shown){
 const box=el('div','','workflow-role-summary'),edge=kind=>EDGE[kind]||kind;
 if(shown.purpose)box.append(el('p',shown.purpose));
 box.append(el('p',shown.location,'workflow-hint'));
 box.append(el('p','Receives: '+(shown.receives.length?shown.receives.map(row=>row.from+' ('+edge(row.kind)+')').join(', '):'no connected step')+(shown.context.length?' · also '+shown.context.map(row=>row.label+(row.from?' from '+row.from:'')).join(', '):'')));
 if(shown.sends.length)box.append(el('p','Hands on to: '+shown.sends.map(row=>row.to+' ('+edge(row.kind)+')').join(', ')));
 if(shown.handoff.expected_output)box.append(el('p','Expected output: '+shown.handoff.expected_output));
 if(shown.handoff.purpose)box.append(el('p','Handoff purpose: '+shown.handoff.purpose));
 if(shown.inherits_from)box.append(el('p','Grouped under '+shown.inherits_from+'. Grouping passes on only declared settings and explicitly chosen context, never a conversation or permissions.','workflow-hint'));
 if(shown.review)box.append(el('p',shown.review,'workflow-hint'));
 if(shown.original_parent)box.append(el('p','Synthesis is written by the original parent conversation with its admitted model and settings. A different model or permission chosen on this step is not applied there.','workflow-qualification'));
 if(shown.consumed==='not-echoed')box.append(el('p','The context or handoff authored for this step was not returned by the owner check, so this profile does not consume it yet. It stays in the draft.','workflow-qualification'));
 item.append(box);
}
function paintFlowAndPolicy(output,body,declarations){
 const flow=workflowConfiguredFlow(body);if(flow.length){const list=el('ul','','workflow-configured-flow');for(const row of flow)list.append(el('li',row.from+' → '+row.to+' · '+row.meaning));output.append(el('h4','Configured connections (planned)'),list,el('p','Observed messages appear in Runs only from recorded receipts.','workflow-hint'));}
 const bounds=workflowPolicyBounds(declarations);if(bounds)output.append(el('p',workflowPolicyText(bounds),'workflow-hint'));
}
// Finds an offer the owner already issued for a facet. It never builds a handle.
export function findWorkflowOperationOffer(value,facet,depth=0){
 if(!value||typeof value!=='object'||depth>4)return null;
 const handle=value.read||value.prepare_read||value;
 if(handle?.read_only===true&&(handle.request?.facet===facet||handle.http?.payload?.facet===facet))return value;
 for(const child of Array.isArray(value)?value:Object.values(value)){const hit=findWorkflowOperationOffer(child,facet,depth+1);if(hit)return hit;}
 return null;
}
export function workflowInterventions({draft=null,attempt=null,run=null}={}){
 const stop=workflowStopOffer(run),open=!!attempt&&['pending','uncertain'].includes(attempt.status),offered=open&&!!attempt.withdrawal_offer?.prepare_read,busy=['preparing','pending'].includes(attempt?.withdraw_status);
 const withdraw=!attempt?'No Save or Prepare request is waiting for the owner.':attempt.status==='withdrawn'?'The owner confirmed this exact request was not admitted. Nothing recorded was undone.':attempt.status==='recorded'?'This request is recorded. Withdrawal cannot undo a recorded effect; its receipt stays.':busy?'Withdrawal awaits the owner’s answer for the original request.':offered?'Asks the owner to withdraw this exact original request if it has not yet been admitted. If the owner already recorded it, the receipt stays.':'The owner offered no withdrawal for this request. Inspect it instead; nothing is resent.';
 return [
  {id:'discard',label:'Discard unsaved edits',available:!!draft,meaning:'Removes only this local draft. Recorded saves, pending requests and runs are not cancelled.'},
  {id:'withdraw',label:'Withdraw original request',available:offered&&!busy,meaning:withdraw},
  {id:'stop',label:'Stop admitted run',available:stopPermitted(stop),offer:stop,meaning:stopPermitted(stop)?'Stops admission of further steps, then asks each owned child step to stop through its own owner. Recorded results stay, and the run counts as stopped only when every child is observed settled.':stop?'The owner lists Stop for this run but does not permit it now'+(stop.reason?': '+stop.reason:'.')+' Nothing is sent from here.':'Not offered for this run. The app-dispatch runs this view reads carry no Stop. Stop a research workflow run from its Plan & run view in Explore across projects, or from Open run detail in its observed flow. A conversation’s own Stop ends only its current turn.'}
 ];
}
export function workflowObservationRow(item){
 const pick=(...names)=>{for(const name of names)if(typeof item?.[name]==='string'&&item[name])return item[name];return null;},end=value=>typeof value==='string'?value:value?.title||value?.step_id||value?.role||null;
 const raw=pick('state','status','recorded_status'),word=raw?ownerStateWord('dispatch-child',raw):null;
 return {label:pick('title','summary','kind','event')||'Recorded observation',state:word?word.words:'state not stated',exact:raw,when:pick('observed_at','recorded_at','at'),from:end(item?.from),to:end(item?.to)};
}
// Lazy selected observation of recorded uses or flow. Reads only on an explicit
// request through the owner-issued offer, pages by the owner's continuation and
// never mixes cuts. Missing receipts are unknown, never proof of no action.
export function mountWorkflowObservation(host,{offer,facet,label='',request,inputs={},isCurrent=()=>true,expected={},onRead=null,stopRecovery=null}){
 const panel=el('section','','workflow-observation'),status=el('p',facet==='river'?'Observed flow comes only from recorded run receipts. Nothing is read until you ask.':'Recorded uses of this exact saved version. Nothing is read until you ask.','workflow-hint'),list=el('ol','','workflow-observed-flow');status.setAttribute('role','status');
 let alive=true,epoch=0,page=null,items=[];
 const current=()=>alive&&panel.isConnected!==false&&isCurrent();
 const open=button(label||(facet==='river'?'Read observed flow':'Read recorded uses'),()=>load());open.dataset.control='workflow:'+facet;
 panel.append(status,open,list);host.append(panel);
 async function load(handle=null){
  if(!current())return false;const ticket=++epoch;open.disabled=true;pendingRead(status,'Reading recorded observations without changing anything…');
  try{const value=await readWorkflowOperation(handle||offer,handle?{}:copy(inputs),{request,expected,isCurrent:()=>ticket===epoch&&current()});if(!value)return false;
   if(handle&&(value.cut!==page?.cut||value.offset!==items.length))throw Error('The observations changed while paging. Read them again from the start.');
   page=value;items=handle?[...items,...value.items]:value.items;paint();return true;
  }catch(error){if(ticket===epoch&&current())status.textContent='Observation unavailable: '+error.message;return false;}
  finally{if(ticket===epoch&&current())open.disabled=false;}
 }
 function paint(){
  list.replaceChildren();if(page.coverage==='NO_PROJECT_EXECUTION_BINDING'){status.textContent='No project execution is bound to this saved version, so no flow can be observed here. That is not proof that nothing happened elsewhere.';return;}
  status.textContent=items.length+' of '+page.total+' recorded '+(facet==='river'?'observations':'uses')+' read. A missing receipt means unknown, not absent.';
  for(const item of items){const row=workflowObservationRow(item),entry=el('li');const said=el('span',' · '+row.state+(row.when?' · '+row.when:''));if(row.exact)said.title='Owner state '+row.exact;entry.append(el('strong',row.label),said);if(row.from||row.to)entry.append(el('span',' · '+(row.from||'unknown')+' → '+(row.to||'unknown')));for(const [key,name]of [['reply','Read complete response'],['proposal','Inspect proposal'],['typed_return','Inspect typed return'],['research_run','Inspect research run']]){const read=item?.reads?.[key];if(read&&typeof onRead==='function'){const open=button(name,()=>{if(current())onRead(copy(read),name,copy(item));});open.dataset.control='workflow:river-read';entry.append(open);}}
   if(facet==='river'&&!item?.reads&&item?.public_reply_read)entry.append(el('span',' · older reply handle only; open the run detail for current reads','workflow-hint'));
   entry.append(detail('Exact recorded observation',item));list.append(entry);}
  if(facet==='river')paintRun();
  if(page.next_read){const more=button('Read more',()=>load(page.next_read));more.dataset.control='workflow:'+facet+'-more';list.append(more);}
 }
 // Schema/3 compact river: the row's Stop is a summary without HTTP. Only the
 // issued row_projection.detail_read yields the run view that carries the exact Stop.
 let runSlot=null,stopUI=null,detailEpoch=0;
 function paintRun(){
  stopUI?.destroy();stopUI=null;runSlot?.remove();runSlot=null;const run=workflowRiverRun(page);if(!run)return;
  runSlot=el('section','','workflow-river-run');runSlot.dataset.workflowRiverRun='';
  runSlot.append(el('h4','This run'),el('p','Recorded state: '+(run.recorded_state||'not stated')+(run.run_revision?' · run revision '+run.run_revision.slice(7,19):''),'workflow-hint'),el('p',riverStopText(run.stop),'workflow-hint'));
  if(run.detail_read){const open=button('Open run detail',()=>openDetail(run));open.dataset.control='workflow:run-detail';runSlot.append(open);}
  else runSlot.append(el('p','The owner issued no run detail read for this run, so its exact actions are unavailable here.','workflow-qualification'));
  panel.append(runSlot);
 }
 async function openDetail(run){
  if(!current()||!runSlot)return false;const ticket=++detailEpoch,slotHost=runSlot;stopUI?.destroy();stopUI=null;slotHost.querySelector('.workflow-run-detail')?.remove();const slot=el('div','','workflow-run-detail');slotHost.append(slot);slot.append(pendingRead(el('p','Reading the exact run detail without changing anything…','workflow-hint')));
  const fresh=()=>ticket===detailEpoch&&current()&&runSlot===slotHost;
  try{const view=await readWorkflowRunDetail(run.detail_read,{request,work_id:run.work_id,project:page.scope?.kind==='project'?page.scope.namespace:null,expected:{definition_id:page.reference?.identity?.id,version:page.reference?.version?.definition_revision},isCurrent:fresh});if(!view||!fresh())return false;
   slot.replaceChildren(el('p',(view.work?.title||'Research workflow run')+' · '+(view.state||'standing not reported'),'workflow-hint'));
   if(view.revision!==run.run_revision)slot.append(el('p','The run changed after this flow was read. Stop below uses the current run detail. Read the flow again to compare.','workflow-qualification'));
   stopUI=mountWorkflowRunStop(slot,{view,request,isCurrent:fresh,recovery:stopRecovery});return true;
  }catch(error){if(!fresh())return false;const app=error?.appRun;
   if(app){
    // B's app-dispatch run, read-only: never converted into a research run view or its Stop.
    slot.replaceChildren(el('p','Recorded app run · parent synthesis '+String(app.synthesis.status).toLowerCase().replaceAll('_',' ')+(app.synthesis.location==='original-parent'?' in the original parent conversation':'')+'.','workflow-hint'));
    for(const [key,label] of [['uses','Read recorded uses'],['river','Read observed flow']])if(app.reads[key]){const link=el('a',label);link.href=app.reads[key];link.dataset.control='workflow:app-run-'+key;slot.append(link);}
    for(const step of app.steps)if(step.reply&&typeof onRead==='function'){const open=button('Read '+step.title+' response',()=>{if(fresh())onRead(copy(step.reply),'Read complete response',copy(step));});open.dataset.control='workflow:app-run-reply';const owner=step.reply?.identity?.turn_id||step.packet;if(owner)open.dataset.controlOwner=owner;slot.append(open);}
    if(app.cancel)slot.append(el('p',app.cancel.permitted?'Cancel dispatched work is available on this run’s Work view.':'Cancel dispatched work is not permitted now'+(app.cancel.reason?': '+app.cancel.reason:'.'),'workflow-hint'));
    for(const line of app.distinctions)slot.append(el('p',line,'workflow-hint'));
    return true;}
   slot.replaceChildren(el('p','Run detail unavailable: '+error.message,'workflow-qualification'));return false;}
 }
 return {load:()=>load(),destroy(){alive=false;epoch++;detailEpoch++;stopUI?.destroy();},get value(){return page?copy({...page,items}):null;}};
}
// Run Stop consumes only the owner-issued actions['stop-run'] of a run view
// (accepted owner component A19e/eb80, workflow_progression.view; Root b455). Its carriers must agree; the body
// is sent once exactly as issued and a lost reply stays unknown.
const withoutProject=value=>{const {project,...rest}=value||{};return rest;};
export function workflowStopOffer(view){
 const offer=view?.actions?.['stop-run'];if(!offer||typeof offer!=='object')return null;
 const payload=offer.http?.payload?withoutProject(offer.http.payload):offer.native?.payload;
 if(payload?.action!=='workflow-stop-run'||typeof payload.work_id!=='string'||typeof payload.request_id!=='string'||!SHA.test(payload.expected_run_revision||'')||!Array.isArray(payload.children))return null;
 // Bind the issued coordinates to the selected research run view (work.id,
 // work.project, run revision) before any request. No other view shape is mapped.
 const work=view.work;
 if(view.schema_version!=='laplace.research-workflow-run/1'||typeof work?.id!=='string'||payload.work_id!==work.id||typeof view.revision!=='string'||payload.expected_run_revision!==view.revision)return null;
 if(offer.http?.payload&&(typeof work.project!=='string'||offer.http.payload.project!==work.project))return null;
 // Both carriers are required. Agreement is never inferred from one carrier.
 if(!offer.native||!offer.http||offer.native.operation!=='work_delivery'||!equal(offer.native.payload,payload))return null;
 return copy(offer);
}
const stopPermitted=offer=>!!offer?.http&&offer.permitted===true&&offer.available!==false;
const coverageComplete=value=>value==='COMPLETE'||value?.complete===true||value?.complete==='COMPLETE';
function stopComposition(value,payload={},offerCoverage=null){
 const stop=value?.stop,request_id=payload.request_id||null;
 if(stop?.schema_version!=='laplace.workflow-stop-composition/1'||!Array.isArray(stop.children))return {outcome:'UNKNOWN',run_stopped:false,request_id,raw:copy(value),text:'The owner reply did not include a Stop composition. Treat the outcome as unknown and inspect the run; nothing is resent.'};
 if(stop.request_id!==undefined&&stop.request_id!==request_id||stop.work_id!==undefined&&stop.work_id!==payload.work_id||value.work_id!==undefined&&value.work_id!==payload.work_id)return {outcome:'UNKNOWN',run_stopped:false,request_id,raw:copy(value),text:'The owner reply names another request or Work. Treat the outcome as unknown and inspect the run; nothing is resent.'};
 const settled=stop.children.filter(row=>['SETTLED','GATED_NOT_ADMITTED'].includes(row.stop)).length,total=stop.children.length,coverage=stop.coverage||offerCoverage,complete=coverageComplete(coverage)&&!(stop.unknown||[]).length,requested=Array.isArray(payload.children)?payload.children:null,ids=stop.children.map(row=>row.event_id),exact=!!requested&&ids.length===requested.length&&new Set(ids).size===ids.length&&requested.every(id=>ids.includes(id)),gated=stop.future_admission?.effective===true,stopped=stop.run_stopped===true&&exact&&gated&&settled===total&&complete;
 const text=(stop.outcome==='STOPPED'&&stopped?'The run is stopped: no further step will be admitted and every owned child is observed settled.':!exact?'The owner reply does not account for exactly the children this Stop requested, so the run is not treated as stopped. Inspect the run.':stop.outcome==='STOPPED'&&!gated?'The owner reported the run stopped, but further admission is not shown as gated. Treat it as still stopping and inspect the run.':stop.outcome==='STOPPED'?'The owner reported the run stopped, but child coverage is incomplete. Treat it as still stopping and inspect the run.':stop.outcome==='FUTURE_GATED_CHILDREN_PENDING'?'No further step will be admitted. Stop was requested for running children, but '+(total-settled)+' of '+total+' are not yet observed settled.':'Further admission was not gated. Inspect the run before deciding again.')+' Recorded effects are retained; nothing was undone.';
 return {outcome:stop.outcome||'UNKNOWN',run_stopped:stopped,request_id,children:copy(stop.children),unknown:copy(stop.unknown||[]),coverage:copy(coverage||null),text,raw:copy(value)};
}
// The reply must name the same nested Work, project and Stop request that was
// sent. A different subject is unknown; a missing one is unqualified. Neither is stopped.
export function workflowStopPresentation(value,payload={},offerCoverage=null,subject={}){
 const stop=value?.stop;if(stop?.schema_version!=='laplace.workflow-stop-composition/1'||!Array.isArray(stop.children))return stopComposition(value,payload,offerCoverage);
 const project=subject?.project??payload?.project??null,work=value.work,asked=value.stop_request,requested=Array.isArray(payload?.children)?payload.children:null;
 const sameSet=(a,b)=>Array.isArray(a)&&Array.isArray(b)&&a.length===b.length&&new Set(a).size===a.length&&b.every(id=>a.includes(id));
 const wrong=!!(work&&typeof work==='object'&&(work.id!==payload?.work_id||project!==null&&work.project!==undefined&&work.project!==project)
  ||asked&&typeof asked==='object'&&(asked.request_id!==payload?.request_id||asked.children!==undefined&&requested&&!sameSet(asked.children,requested))
  ||stop.request_id!==undefined&&stop.request_id!==payload?.request_id||stop.work_id!==undefined&&stop.work_id!==payload?.work_id);
 if(wrong)return {outcome:'UNKNOWN',run_stopped:false,subject:'MISMATCHED',request_id:payload?.request_id||null,original_request:copy(payload||{}),raw:copy(value),text:'The owner reply names another Work, project or Stop request than the one sent from here. Treat the outcome as unknown and inspect the run. Nothing is resent and recorded effects stay.'};
 const known=typeof work?.id==='string'&&typeof work?.project==='string'&&project!==null&&typeof asked?.request_id==='string'&&Array.isArray(asked?.children);
 const shown=stopComposition(value,payload,offerCoverage);shown.original_request=copy(payload||{});shown.subject=known?'MATCHED':'MISSING';
 if(!known){const note='The reply does not name this exact Work, project and Stop request, so the run is not treated as stopped.';shown.text=shown.run_stopped?note+' Inspect the run. Nothing is resent. Recorded effects are retained; nothing was undone.':shown.text+' '+note;shown.run_stopped=false;}
 return shown;
}
function issuedStopWire(offer,view){
 const issued=workflowStopOffer(view),checked=issued&&equal(issued,offer)?issued:null,http=checked?.http,u=new URL(http?.url||'',here());
 if(!checked)throw Error('This run has no owner-issued Stop for the selected run. Nothing was sent.');if(!stopPermitted(checked))throw Error('The owner does not permit Stop for this run now'+(checked.reason?': '+checked.reason:'.')+' Nothing was sent.');
 if(http?.method!=='POST'||u.origin!==here().origin||u.pathname!=='/work/delivery'||u.search||u.hash||!http.payload)throw Error('The owner issued Stop without an exact HTTP carrier. Nothing was sent.');
 return {url:u.pathname,body:copy(http.payload),coverage:checked.coverage};
}
async function postStop(url,body,{request,coverage=null}){
 let value;try{value=await request(url,copy(body));}
 catch(error){if(error?.result?.stop)return workflowStopPresentation(error.result,body,coverage);return error?.result?{outcome:'REFUSED',run_stopped:false,request_id:body.request_id,raw:copy(error.result),text:'The owner refused Stop: '+error.message+' Inspect the run before deciding again; nothing is resent.'}:{outcome:'UNKNOWN',run_stopped:false,request_id:body.request_id,text:'The Stop request was sent but its outcome is unknown. Inspect the run; nothing is resent.'};}
 return workflowStopPresentation(value,body,coverage);
}
export async function stopWorkflowRun(offer,{request,view=null}={}){const wire=issuedStopWire(offer,view);return postStop(wire.url,wire.body,{request,coverage:wire.coverage});}

// Follows an issued schema/3 row_projection.detail_read (facet app-run) for one
// Work. Only a research run view naming the same Work and project is returned;
// an app-dispatch run is refused, never converted.
const DETAIL_SELECTORS=['definition_id','version','reference','project_lens','facet','work_id'];
const closed=(value,names)=>!!value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).every(key=>names.includes(key));
export async function readWorkflowRunDetail(handle,{request,work_id,project=null,expected={},isCurrent=()=>true}={}){
 const url=new URL(handle?.http?.url||'',here()),notIssued='The run detail read is not an issued run read for this Work.',disagree='The run detail read carriers disagree. Nothing was read.';
 if(!closed(handle,['http','request','native','sdk'])||!closed(handle.http,['method','url'])||handle.http.method!=='GET'||url.origin!==here().origin||url.pathname!=='/work/workflow-definitions'||url.hash||url.username||url.password||typeof work_id!=='string'||[...url.searchParams.keys()].some(key=>!DETAIL_SELECTORS.includes(key)||url.searchParams.getAll(key).length!==1))throw Error(notIssued);
 const selector={};for(const [key,text]of url.searchParams){if(key!=='reference'){selector[key]=text;continue;}try{selector.reference=JSON.parse(text);}catch{throw Error(notIssued);}}
 if(selector.facet!=='app-run'||selector.work_id!==work_id||!(typeof selector.definition_id==='string'&&typeof selector.version==='string'||selector.reference&&typeof selector.reference==='object'))throw Error(notIssued);
 // The HTTP query and every issued request, native and SDK carrier must name this same
 // complete closed selector before anything is read. None is converted or trusted alone.
 const carriers=[];if(handle.request!==undefined)carriers.push(handle.request);
 if(handle.native!==undefined){if(!closed(handle.native,['operation','payload'])||handle.native.operation!=='project'||!closed(handle.native.payload,['view','request'])||handle.native.payload.view!=='workflow-definitions')throw Error(disagree);carriers.push(handle.native.payload.request);}
 if(handle.sdk!==undefined){if(!closed(handle.sdk,['method','payload'])||handle.sdk.method!=='workflow_request')throw Error(disagree);carriers.push(handle.sdk.payload);}
 if(!carriers.length||carriers.some(row=>!closed(row,DETAIL_SELECTORS)||!equal(row,selector)))throw Error(disagree);
 if(project!==null&&selector.project_lens!==undefined&&selector.project_lens!==project||Object.entries(expected||{}).some(([key,value])=>typeof value==='string'&&selector[key]!==value))throw Error('The run detail read names another workflow version or project. Nothing was read.');
 if(!isCurrent())return null;const value=await request(url.pathname+url.search);if(!isCurrent())return null;
 if(value?.schema_version!=='laplace.research-workflow-run/1'){
  const refusal=Error('This run detail is not a research workflow run. Its own Runs controls apply; it is not converted.');
  try{const app=workflowAppRunSummary(value,{work_id,project});if(app)refusal.appRun=app;}catch(error){refusal.appRunError=error.message;}
  throw refusal;
 }
 if(value.work?.id!==work_id||project!==null&&value.work?.project!==project)throw Error('The run detail names another Work or project.');
 return copy(value);
}
// B's app-dispatch run (writing.workflow_dispatch.run) as read-only facts: the ORIGINAL-parent synthesis, the same-scope
// uses/river reads, each child's exact public reply identity and the cancellation meanings. It refuses a foreign Work,
// project or reply conversation, returns null for anything that is not an owner app run and mints no action.
export function workflowAppRunSummary(value,{work_id,project=null}={}){
 if(!value||typeof value!=='object'||typeof value.profile!=='string'||!value.parent_synthesis||typeof value.parent_synthesis!=='object')return null;
 if(value.work_id!==work_id||value.work?.id!==work_id||typeof value.work?.project!=='string'||project!==null&&value.work.project!==project)throw Error('The app run names another Work or project.');
 const synthesis=value.parent_synthesis,reads=value.observation_reads||{},cancel=value.actions?.cancel_dispatch||null;
 const getURL=handle=>typeof handle?.http?.url==='string'&&(handle.http.method||'GET')==='GET'&&handle.http.url.startsWith('/')&&!handle.http.url.startsWith('//')?handle.http.url:null;
 const steps=(Array.isArray(value.steps)?value.steps:[]).map(step=>{
  const reply=step?.public_reply_read,id=reply?.identity;
  if(reply&&(id?.project!==value.work.project||id?.part!=='reply'||step.session_id&&id.session_id!==step.session_id||step.turn_id&&id.turn_id!==step.turn_id))
   throw Error('A child reply read names another conversation.');
  return {packet:step?.packet||null,title:step?.title||step?.packet||step?.step_id||'step',reply:reply?copy(reply):null};});
 const meaning=typeof cancel?.cancellation_meaning==='string'?cancel.cancellation_meaning:'';
 return {work_id,project:value.work.project,
  synthesis:{status:synthesis.status||'UNKNOWN',location:synthesis.execution_location||null,return_path:synthesis.return_path||null},
  reads:{uses:getURL(reads.uses),river:getURL(reads.river)},
  cancel:cancel?{permitted:cancel.permitted===true,reason:cancel.reason||'',meaning,distinct_from:copy(cancel.distinct_from??null)}:null,
  steps,
  distinctions:['Cancel dispatched work stops this dispatch Work through its owner'+(meaning?': '+meaning:'.'),
   'A selected-turn Stop interrupts one conversation turn only; it does not cancel the dispatch.',
   'Cancelling a comment review route stops that route only; it is not this run.',
   'A Source or kernel Stop belongs to the Source commission and is not offered here.']};
}
// Compact schema/3 river run summary. Actions and Stop are standing only.
export function workflowRiverRun(value){
 if(value?.schema_version!=='laplace.workflow-operation/1'||value.view!=='river'||typeof value.work_id!=='string')return null;
 const projection=value.row_projection,stop=value.stop,compact=stop?.stop_run&&typeof stop.stop_run==='object'?stop.stop_run:null;
 return {work_id:value.work_id,run_revision:value.run_identity?.run_revision||null,recorded_state:value.run_identity?.recorded_state||value.observation?.state||null,
  detail_read:projection?.kind==='COMPACT_IDENTITY_AND_HANDLES'&&projection.detail_read&&typeof projection.detail_read==='object'?copy(projection.detail_read):null,
  stop:{offered:!!compact,permitted:compact?.permitted===true&&compact.available!==false,reason:compact?.reason||'',coverage:stop?.coverage||null,owned_children_total:Number.isSafeInteger(stop?.owned_children_total)?stop.owned_children_total:null,has_http:!!compact?.http},
  actions:Array.isArray(value.actions)?value.actions.map(row=>({name:row?.name,title:row?.title,permitted:row?.permitted===true,reason:row?.reason||''})):[]};
}
function riverStopText(stop){
 if(!stop.offered)return stop.coverage==='INCOMPLETE'?'This run has more owned steps than the flow summary lists, so Stop is not summarised here. Open the run detail.':'The flow summary lists no Stop for this run.';
 if(!stop.permitted)return 'The owner lists Stop for this run but does not permit it now'+(stop.reason?': '+stop.reason:'.');
 return 'The owner offers Stop for this run'+(stop.owned_children_total?' and its '+stop.owned_children_total+' running step(s)':'')+'. This flow row is only a summary without the request itself, so open the run detail to use the exact Stop.';
}
// Shared guarded Stop for one selected research run view (Plan & run, or Runs and
// Open run detail). Before anything is sent, the exact original body, the owner-issued
// request_read and the qualified project/Work/request/attempt are written to the
// research-workbench Stop recovery and read back; if that fails nothing is sent.
// The record outlives this mount: Refresh, reopening, Back and browser reload read
// the same record, and one written by an earlier page is UNKNOWN. Nothing is resent
// automatically. Check original Stop request reads only the owner's request_read.
// RECORDED or NONE for that exact attempt permits one explicit unchanged resend,
// which the owner treats as the same request; a new Stop needs a newly issued
// owner request identity. The client never mints a request identity or carrier.
let sharedStopRecovery=null;
const defaultStopRecovery=()=>sharedStopRecovery||=workflowStopRecovery();
function stopStanding(record){
 const checked=record.checked&&record.checked.attempt===record.attempt?record.checked:null,stopped=record.outcome==='STOPPED',qualified=!!checked?.qualified&&['RECORDED','NONE'].includes(checked.effect),inFlightHere=record.phase==='SENT'&&record.observation!=='UNKNOWN';
 return {checked,stopped,qualified,held:!stopped&&!qualified,resend:qualified&&!stopped&&!inFlightHere&&!!record.original_request};
}
// Classifies an owner request_status answer for the exact retained original only.
// A successful read is not settlement; NONE is no retained request at that cut.
export function workflowStopRequestStanding(value,record){
 const unqualified={effect:'UNQUALIFIED',qualified:false,text:'The owner answer does not name this exact project, Work and original Stop request with a recognised standing. The original stays held and nothing is resent.'};
 if(!value||typeof value!=='object'||!record||value.project!==record.project||value.work_id!==record.work_id||value.request_id!==record.request_id)return unqualified;
 if(value.read?.http?.url!==undefined&&value.read.http.url!==record.request_read?.http?.url)return unqualified;
 if(value.effect==='RECORDED')return value.receipt?.request_id===record.request_id?{effect:'RECORDED',qualified:true,text:'The owner recorded this original Stop request and its effect stays. Resending it unchanged only re-reads the owner’s retained Stop and child receipts; it is not a new Stop.'}:unqualified;
 if(value.effect==='NONE')return {effect:'NONE',qualified:true,text:'The owner holds no record of this original request at this read. That is not proof of no effect. Only an explicit unchanged resend of the original is permitted.'};
 if(value.effect==='UNKNOWN')return {effect:'UNKNOWN',qualified:false,text:'The owner reports this original request as unknown'+(typeof value.reason==='string'&&value.reason?': '+value.reason:'.')+' It stays held and nothing is resent.'};
 return unqualified;
}
function retainedStopWire(record,{project,work_id}){
 const body=record?.original_request;
 if(!body||typeof body!=='object'||record.project!==project||record.work_id!==work_id||body.action!=='workflow-stop-run'||body.project!==project||body.work_id!==work_id||body.request_id!==record.request_id||record.http_url!=='/work/delivery')throw Error('The retained original Stop request is incomplete or names another run. Nothing was sent.');
 return {url:record.http_url,body:copy(body),coverage:null};
}
export function mountWorkflowRunStop(host,{view,request,isCurrent=()=>true,onSettled=()=>{},recovery=null,onRetain=()=>{}}={}){
 const store=recovery||defaultStopRecovery(),offer=workflowStopOffer(view),allowed=stopPermitted(offer),offered=offer?.http?.payload?.request_id||null,project=view?.work?.project,work_id=view?.work?.id;
 const box=el('section','','workflow-run-stop'),status=el('p','','workflow-hint'),original=el('div'),reply=el('div');
 box.dataset.workflowRunStop='';status.setAttribute('role','status');status.tabIndex=-1;
 const meaning=allowed?'Stops admission of further steps, then asks each owned child to stop through its own owner. Recorded results stay. The run counts as stopped only when further admission is gated and every requested child is observed settled.':offer?'The owner lists Stop for this run but does not permit it now'+(offer.reason?': '+offer.reason:'.')+' Nothing is sent from here.':'The owner issued no Stop for this exact run and revision. Nothing is sent from here.';
 const control=button(offer?.title||'Stop this run',()=>send(false));control.dataset.control='workflow:stop-run';
 box.append(el('h4','Stop this run'),el('p',meaning,'workflow-hint'),original,control,status,reply);host.append(box);
 let alive=true,epoch=0,checkEpoch=0,busy=false,checking=false,result=null,ownerRead=null;
 const live=()=>alive&&box.isConnected!==false&&isCurrent();
 const supersededBy=expect=>{const now=store.read(project,work_id).record;return !now||now.request_id!==expect.request_id||now.attempt!==expect.attempt;};
 const unsubscribe=store.subscribe?.((p,w)=>{if(p===project&&w===work_id&&live())paint();})||(()=>{});
 paint();
 function paint(){
  const focused=document.activeElement,kept=focused&&original.contains?.(focused)?focused.dataset?.control:null,got=store.read(project,work_id),record=got.record,s=record?stopStanding(record):null,same=!!record&&offered===record.request_id;
  original.replaceChildren();if(got.error)original.append(el('p',got.error,'workflow-qualification'));if(record)original.append(originalCard(record,s));
  control.disabled=!allowed||busy||checking||got.held||!!record&&(s.held||same);
  if(record&&!s.held&&allowed&&same)original.append(el('p','The current Stop offer still carries the original request '+record.request_id+', so sending it is not a new Stop. Refresh the run for a newly issued offer'+(s.resend?', or use Resend original Stop unchanged.':'.'),'workflow-hint'));
  else if(record&&!s.held&&allowed)original.append(el('p',(offer.title||'Stop this run')+' sends the owner’s newly issued request '+offered+'. The original request stays recorded separately.','workflow-hint'));
  if(kept){const again=original.querySelector?.('[data-control="'+kept+'"]');(again&&!again.disabled?again:status).focus?.({preventScroll:true});}
 }
 function originalCard(record,s){
  const card=el('div','','workflow-stop-original'),awaiting=record.phase==='SENT'&&record.observation!=='UNKNOWN';card.dataset.workflowStopOriginal='';card.dataset.originalRequest=record.request_id;card.dataset.originalStanding=s.checked?.effect||record.observation||'';
  const told=s.stopped?'Its reply showed the run stopped.':awaiting?'Its reply has not arrived in this page yet.':record.phase==='SENT'?'This page was reopened or reloaded after it was sent, so its outcome is unknown.':'Last reply: '+(record.outcome||'not received')+'.';
  card.append(el('p','Original Stop request '+record.request_id+(record.attempt>1?' (sent '+record.attempt+' times, unchanged)':'')+' was kept here before it was sent. '+told+(s.stopped?'':' '+(s.checked?s.checked.text:'Nothing is resent automatically. Check it before deciding again.')),'workflow-qualification'));
  if(!s.stopped){if(record.request_read){const check=button('Check original Stop request',()=>checkOriginal());check.dataset.control='workflow:stop-check';check.disabled=checking||busy;card.append(check);}else card.append(el('p','The owner issued no read for that request. Inspect the run before deciding again.','workflow-hint'));}
  if(s.resend){const again=button('Resend original Stop unchanged',()=>send(true));again.dataset.control='workflow:stop-resend';again.disabled=busy||checking;card.append(again,el('p',s.checked.effect==='RECORDED'?'Sends the same retained request once more. The owner treats it as the same request and re-reads its retained receipts; nothing new is stopped or undone.':'Sends the same retained request once more, the only retry the owner permits after NONE. It is not a new Stop.','workflow-hint'));}
  if(ownerRead&&ownerRead.request_id===record.request_id&&ownerRead.attempt===record.attempt)card.append(detail('Original Stop request as the owner reads it',ownerRead.value));
  card.append(detail('Retained original Stop request',{request_id:record.request_id,attempt:record.attempt,sent_at:record.sent_at,original_request:record.original_request||null,request_read:record.request_read||null,replaced:record.replaced||[]}));
  return card;
 }
 async function checkOriginal(){
  const got=store.read(project,work_id),record=got.record;if(checking||busy||!live()||!record||got.held)return null;
  const ticket=++checkEpoch,expect={project,work_id,request_id:record.request_id,attempt:record.attempt};checking=true;paint();pendingRead(status,'Reading the original Stop request through its owner. Nothing is sent.');
  try{const value=await readStopRequest(record,{request}),shown=workflowStopRequestStanding(value,record);
   const saved=store.check(expect,{effect:shown.effect,qualified:shown.qualified,text:shown.text,at:new Date().toISOString()}),replaced=!!saved.superseded||supersededBy(expect);
   if(ticket!==checkEpoch||!live())return null;checking=false;
   // An answer for an attempt that a newer request replaced, or that could not be saved,
   // stays with that attempt only; it is never shown as the current request's standing.
   if(replaced||!saved.ok){paint();status.textContent=replaced?'A newer attempt replaced the Stop request being checked. Its answer is kept with that attempt; check the current one.':'The owner answer could not be saved with Stop request '+record.request_id+' ('+saved.error+'). It stays held.';return null;}
   ownerRead={request_id:record.request_id,attempt:record.attempt,value:copy(value)};paint();status.textContent='Owner standing of the original Stop request: '+shown.effect+'. '+shown.text;return {...shown,value:copy(value)};
  }catch(error){if(ticket===checkEpoch&&live()){checking=false;paint();status.textContent='Original Stop request unavailable: '+error.message+' It stays held.';}return null;}
  finally{if(ticket===checkEpoch)checking=false;}
 }
 async function send(reconcile){
  const got=store.read(project,work_id),record=got.record,s=record?stopStanding(record):null;
  if(busy||checking||!live()||typeof request!=='function'||got.held)return null;
  let wire,read=null;
  try{if(reconcile){if(!s?.resend)return null;wire=retainedStopWire(record,{project,work_id});read=record.request_read;}
   else{if(!allowed||record&&(s.held||offered===record.request_id))return null;wire=issuedStopWire(offer,view);read=offer.request_read?copy(offer.request_read):null;}}
  catch(error){status.textContent=error.message;return null;}
  // Retain before effect: without a verified readback nothing is sent.
  const begun=store.begin({project,work_id,request_id:wire.body.request_id,original_request:wire.body,http_url:wire.url,request_read:read});
  if(!begun.ok){box.dataset.stopOutcome='NOT_RETAINED';paint();status.textContent='Stop was not sent: this browser could not save and read back the original request first ('+begun.error+'). Nothing was sent; keep this page open and try again.';return null;}
  onRetain(copy(begun.record));busy=true;const ticket=++epoch,attempt=begun.record.attempt,activation=document.activeElement;let laterIntent=false;paint();
  const later=event=>{if(event.target!==activation&&event.target!==control&&event.target!==document.body)laterIntent=true;};
  for(const type of ['focusin','pointerdown','keydown'])document.addEventListener?.(type,later,true);
  status.textContent=reconcile?'Resending the original Stop request unchanged, once. It is not repeated.':'Asking the owner to stop this run. The request is sent once and is not repeated.';
  try{
   const value=await postStop(wire.url,wire.body,{request,coverage:wire.coverage}),label=value.run_stopped?'STOPPED':value.outcome==='STOPPED'?'NOT_CONFIRMED':(value.outcome||'UNKNOWN');
   const expect={request_id:wire.body.request_id,attempt},settled=store.settle({project,work_id,...expect},{phase:'ANSWERED',outcome:label,observation:label}),replaced=!!settled.superseded||supersededBy(expect);if(settled.ok&&!replaced)onRetain(copy(settled.record));
   if(ticket!==epoch||!live())return null;
   busy=false;
   // A reply whose attempt a newer request replaced, or which could not be saved with its
   // request, stays only in that request's history. It is not this run's current result:
   // no outcome label, result text, focus move or onSettled from this controller.
   if(replaced||!settled.ok){paint();status.textContent=replaced?'A newer Stop request replaced '+wire.body.request_id+'. Its reply is kept with that request; the current request is shown above.':'A reply arrived for Stop request '+wire.body.request_id+' but could not be saved with it ('+settled.error+'). It stays held; check it before deciding again.';return null;}
   result={...value,original_request:copy(wire.body)};box.dataset.stopOutcome=label;paint();
   status.textContent=value.text+' Original Stop request: '+wire.body.request_id+'. Refresh the run to read its current standing.';
   reply.replaceChildren(detail('Exact Stop reply and original request',{original_request:wire.body,reply:value.raw??null}));
   onSettled(copy(result));
   const now=document.activeElement;if(!laterIntent&&(now===control||now===activation||!now||now===document.body))status.focus?.({preventScroll:true});
   return copy(result);
  }finally{if(ticket===epoch)busy=false;for(const type of ['focusin','pointerdown','keydown'])document.removeEventListener?.(type,later,true);}
 }
 return {stop:()=>send(false),check:()=>checkOriginal(),resend:()=>send(true),destroy(){alive=false;epoch++;checkEpoch++;unsubscribe();},get value(){return result?copy(result):null;}};
}
// Reads only the owner-issued request_read of the exact original Stop request. Its
// answer is classified by workflowStopRequestStanding; a read alone settles nothing.
async function readStopRequest(record,{request}){
 const handle=record.request_read,url=new URL(handle?.http?.url||'',here());let asked=null;try{asked=JSON.parse(url.searchParams.get('request')||'null');}catch{asked=null;}
 if(handle?.http?.method!=='GET'||url.origin!==here().origin||url.pathname!=='/work/delivery'||url.hash||[...url.searchParams.keys()].some(key=>!['project','request'].includes(key)||url.searchParams.getAll(key).length!==1)||url.searchParams.get('project')!==record.project||asked?.action!=='workflow-request'||asked.work_id!==record.work_id||asked.request_id!==record.request_id||Object.keys(asked).length!==3||handle.native&&(handle.native.operation!=='work_delivery'||!equal(handle.native.payload,asked)))throw Error('The issued request read does not name this original Stop request.');
 if(typeof request!=='function')throw Error('No owner transport is available to read it.');
 return copy(await request(url.pathname+url.search));
}
