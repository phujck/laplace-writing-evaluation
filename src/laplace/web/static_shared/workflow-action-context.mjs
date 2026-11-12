// Selected workflow action carrier and exact parent-submission transformations.
const pin=value=>typeof value==='string'&&/^sha256:[0-9a-f]{64}$/.test(value);
// Selected workflow context is a locator, never a browser mutation grant.
export function workflowActionInput(value,{project,session,work}={}){
 const ref=value?.reference,id=ref?.identity,version=ref?.version;
 const keys=(object,expected)=>object&&typeof object==='object'&&!Array.isArray(object)&&Object.keys(object).sort().join(',')===expected.sort().join(',');
 if(!keys(value,['reference','expected_basis'])||!pin(value.expected_basis)||!keys(ref,['schema_version','owner','kind','identity','version'])||ref.schema_version!=='laplace.reference/1'||ref.owner!=='pipeline.workflow'||!['failed-review-continuation','research-workflow-start'].includes(ref.kind)||!keys(id,ref.kind==='research-workflow-start'?['project','work_id','request_id','parent_session_id','writer_binding_id','reviewer_binding_id']:['project','definition_id','work_id','step_id','request_id','parent_session_id'])||Object.values(id).some(v=>typeof v!=='string'||!v||v.length>160)||!keys(version,['definition_revision'])||!pin(version.definition_revision)||project&&id.project!==project||session&&id.parent_session_id!==session||work&&id.work_id!==work)throw Error('The selected workflow action has no matching original project, conversation and Work basis.');
 return structuredClone(value);
}
export function workflowActionSummary(snapshot){
 const leaf=workflowActionInput({reference:snapshot?.reference,expected_basis:snapshot?.expected_basis}),s=snapshot.summary;
 if(leaf.reference.kind==='research-workflow-start'){if(snapshot.schema_version!=='laplace.workflow-action-context/1'||!s||s.work_id!==leaf.reference.identity.work_id)throw Error('The owner action summary does not match this research workflow.');return {kind:leaf.reference.kind,workflow_title:String(s.workflow_title||'Saved workflow'),work_id:s.work_id,input_policy:s.input_policy,application_boundary:s.application_boundary,policy:structuredClone(s.policy)};}
 if(snapshot.schema_version!=='laplace.workflow-action-context/1'||!s||s.step_id!==leaf.reference.identity.step_id||s.work_id!==leaf.reference.identity.work_id||s.parent_session_id!==leaf.reference.identity.parent_session_id)throw Error('The owner action summary does not match the selected context.');
 return {step_title:String(s.step_title||s.step_id).slice(0,240),workflow_title:String(s.workflow_title||'Saved workflow').slice(0,240),outputs:(s.reused_outputs||[]).map(row=>String(row.output?.artifact_path||row.output?.path||row.packet||'Retained worker output').slice(0,240)),budget:{max_child_launches:s.budget?.max_child_launches,deadline_at:s.budget?.deadline_at,deadline_seconds:s.budget?.deadline_seconds}};
}
export function workflowActionRead(leaf){
 const {reference,expected_basis}=workflowActionInput(leaf),id=reference.identity;
 if(reference.kind==='research-workflow-start')throw Error('This research action requires its retained exact owner-issued read. Reopen its recorded action; no Start identity is reconstructed.');
 return {definition_id:id.definition_id,version:reference.version.definition_revision,facet:'app-continue-compose',work_id:id.work_id,step_id:id.step_id,request_id:id.request_id,expected_action_basis:expected_basis};
}
const canonical=value=>Array.isArray(value)?value.map(canonical):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(k=>[k,canonical(value[k])])):value;
export async function actionSubmissionDigest(payload){
 const wire=JSON.parse(JSON.stringify(payload));delete wire.request_id;
 const bytes=new TextEncoder().encode(JSON.stringify(canonical(wire))),hash=await globalThis.crypto.subtle.digest('SHA-256',bytes);
 return 'sha256:'+Array.from(new Uint8Array(hash),b=>b.toString(16).padStart(2,'0')).join('');
}
export function actionSubmissionRead(pending){
 const p=pending.payload;workflowActionInput(p?.workspace_context?.workflow_action,{project:p?.project,session:p?.session_id,work:p?.work_id});
 if(p.mode!=='work'||typeof p.request_id!=='string'||!p.request_id||p.request_id.length>160||!pin(pending.intent_sha256))throw Error('The retained parent submission identity is incomplete.');
 return '/authoring/session-turn?'+new URLSearchParams({view:'request',project:p.project,session_id:p.session_id,request_id:p.request_id});
}
export function actionSubmissionReceipt(value,pending){
 const p=pending.payload;
 if(value?.exact!==true||value.project!==p.project||value.session_id!==p.session_id||value.request_id!==p.request_id||!['NONE','RECORDED'].includes(value.effect)||value.effect==='NONE'&&value.receipt!==null)throw Error('The submission lookup did not identify the retained project and conversation.');
 if(value.effect==='NONE')return null;
 const r=value.receipt;if(!r||r.session_id!==p.session_id||r.request_id!==p.request_id||r.intent_sha256!==pending.intent_sha256||typeof r.turn_id!=='string'||!r.turn_id)throw Error('The recorded submission does not match the exact retained intent.');
 const url=new URL(r.read?.http?.url||'',globalThis.location?.href||'http://localhost/');
 if(r.read?.http?.method!=='GET'||url.pathname!=='/authoring/session-turn'||url.searchParams.get('project')!==p.project||url.searchParams.get('id')!==r.turn_id||url.searchParams.get('view')!=='turn'||url.origin!==new URL(globalThis.location?.href||'http://localhost/').origin)throw Error('The submission receipt has no matching exact turn read.');
 return structuredClone(r);
}
