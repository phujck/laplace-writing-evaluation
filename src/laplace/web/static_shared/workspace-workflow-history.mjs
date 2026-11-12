// Bounded saved-workflow reading. All navigation is owner-issued; this module
// retains no authoring guard, executable policy, durable query or effect authority.
import {copy,equal,checkedReference} from './research-workbench-state.mjs';
import {feedbackWireDigest} from './feedback-route-port.mjs';
import {WORKFLOW_ENTRY} from './workflow-port.mjs';
const pin=value=>typeof value==='string'&&/^sha256:[a-f0-9]{64}$/.test(value);
const object=value=>value&&typeof value==='object'&&!Array.isArray(value);
const integer=(value,min=0,max=Number.MAX_SAFE_INTEGER)=>Number.isSafeInteger(value)&&value>=min&&value<=max;
const here=()=>new URL(globalThis.location?.href||'http://local/project');
const definitionScope=scope=>equal(scope,{kind:'owned-workspace'})||scope?.kind==='project'&&typeof scope.namespace==='string'&&!!scope.namespace&&Object.keys(scope).sort().join(',')==='kind,namespace';
function definitionRef(reference,id,version){checkedReference(reference);if(reference.owner!=='pipeline.workflow'||reference.kind!=='workflow-definition'||!equal(reference.identity,{id})||!equal(reference.version,{definition_revision:version}))throw Error('This saved reference belongs to another workflow or version.');}
export function checkedWorkflowHistoryHandle(handle,{facet=null,id=null,head=null,cut=null,selected=null,offset=null,bodyOffset=null}={}){
 const url=new URL(handle?.http?.url||'',here()),q=url.searchParams,raw=handle?.request;
 if(handle?.http?.method!=='GET'||url.origin!==here().origin||url.pathname!==WORKFLOW_ENTRY||url.username||url.password||url.hash||!object(raw))throw Error('No exact workflow history read was issued.');
 const fields=['facet','reference','definition_id','version','project_lens','selected_version','body_offset','body_limit','as_of','offset','limit','capture_max_bytes','metadata_max_rows'],numbers=new Set(['body_offset','body_limit','offset','limit','capture_max_bytes','metadata_max_rows']),decoded={};
 for(const [key,value]of q){if(!fields.includes(key)||q.getAll(key).length!==1)throw Error('The history read contains duplicate or unsupported coordinates.');if(numbers.has(key)){if(!/^(0|[1-9][0-9]*)$/.test(value)||!integer(Number(value)))throw Error('The history read has an invalid page bound.');decoded[key]=Number(value);}else if(key==='reference'){try{decoded[key]=JSON.parse(value);}catch{throw Error('The history reference is invalid.');}}else decoded[key]=value;}
 if(!equal(decoded,raw)||!['history-page','lineage','lineage-page','saved-version'].includes(raw.facet)||facet&&raw.facet!==facet)throw Error('The history URL and typed request do not match.');
 if(handle.native&&(!equal(handle.native.payload?.request,raw)||handle.native.operation!=='project'||handle.native.payload?.view!=='workflow-definitions'||Object.keys(handle.native.payload||{}).some(k=>!['view','request'].includes(k))))throw Error('The native history companion has different coordinates.');
 const target=raw.definition_id||raw.reference?.identity?.id,version=raw.version||raw.reference?.version?.definition_revision;
 if(raw.reference)definitionRef(raw.reference,target,version);
 if(typeof target!=='string'||!target||version!==undefined&&!pin(version)||raw.selected_version!==undefined&&!pin(raw.selected_version)||id&&target!==id||head&&version!==head||cut&&raw.as_of!==cut||selected&&raw.selected_version!==selected||offset!==null&&(raw.offset??0)!==offset||bodyOffset!==null&&(raw.body_offset??0)!==bodyOffset)throw Error('This history read belongs to another selected workflow, cut or position.');
 if(raw.limit!==undefined&&!integer(raw.limit,1,50)||raw.body_limit!==undefined&&!integer(raw.body_limit,1,8000)||['capture_max_bytes','metadata_max_rows'].some(k=>raw[k]!==undefined&&!integer(raw[k],1))||raw.as_of!==undefined&&(typeof raw.as_of!=='string'||!raw.as_of||raw.as_of.length>4096))throw Error('The issued history limits are invalid.');
 return {url:url.pathname+url.search,request:copy(raw),id:target,head:version};
}
export function workflowHistoryExpectation(owner,handle){
 if(!owner?.definition_id||!owner.scope_id||!definitionScope(owner.scope))throw Error('The workflow has no exact scope for history reading.');
 const read=checkedWorkflowHistoryHandle(handle,{facet:'history-page',id:owner.definition_id});return {definition_id:owner.definition_id,scope_id:owner.scope_id,scope:copy(owner.scope),handle:copy(handle),read};
}
export function checkedWorkflowHistoryPage(value,expected,handle=expected.handle){
 const read=checkedWorkflowHistoryHandle(handle,{facet:'history-page',id:expected.definition_id}),r=read.request;
 if(value?.schema_version!=='laplace.workflow-definition-history/1'||value.definition_id!==expected.definition_id||value.scope_id!==expected.scope_id||!equal(value.scope,expected.scope)||!pin(value.head_at_start)||!pin(value.selected_version)||typeof value.cut!=='string'||!value.cut||read.head&&value.head_at_start!==read.head||r.as_of&&value.cut!==r.as_of||value.selected_version!==(r.selected_version||value.head_at_start)||value.body_verification!=='NOT_INSPECTED'||value.unit!=='definition-version'||value.order!=='newest-first'||value.ordinal_base!==1||!integer(value.known,1)||!integer(value.offset)||value.offset!==(r.offset??0)||value.limit!==(r.limit??20)||!integer(value.limit,1,50)||!integer(value.covered,0,Math.min(value.limit,value.known-value.offset))||!Array.isArray(value.items)||value.returned!==value.items.length||value.covered!==value.items.length||value.at_end!==(value.offset+value.covered===value.known))throw Error('The history page returned another scope, cut or covered position. No pages were mixed.');
 definitionRef(value.reference,expected.definition_id,value.head_at_start);
 value.items.forEach((item,index)=>{if(item.ordinal!==value.known-value.offset-index||!pin(item.version))throw Error('History ordinals or versions are not contiguous at this cut.');checkedWorkflowHistoryHandle(item.read,{facet:'saved-version',id:expected.definition_id,head:value.head_at_start,cut:value.cut,selected:item.version,bodyOffset:0});});
 if(!value.covered&&!value.at_end)throw Error('The history page made no covered progress.');
 if(value.next_read)checkedWorkflowHistoryHandle(value.next_read,{facet:'history-page',id:expected.definition_id,head:value.head_at_start,cut:value.cut,selected:value.selected_version,offset:value.offset+value.covered});else if(!value.at_end)throw Error('The history page has no exact continuation.');
 if(value.previous_read)checkedWorkflowHistoryHandle(value.previous_read,{facet:'history-page',id:expected.definition_id,head:value.head_at_start,cut:value.cut,selected:value.selected_version,offset:Math.max(0,value.offset-value.limit)});
 for(const read of [value.restart_read,value.current_head_read])if(read)checkedWorkflowHistoryHandle(read,{facet:'history-page',id:expected.definition_id});
 return copy(value);
}
export function savedHistoryExpectation(page,item){
 const read=checkedWorkflowHistoryHandle(item.read,{facet:'saved-version',id:page.definition_id,head:page.head_at_start,cut:page.cut,selected:item.version,bodyOffset:0});
 return {definition_id:page.definition_id,scope_id:page.scope_id,scope:copy(page.scope),head_at_start:page.head_at_start,cut:page.cut,version:item.version,ordinal:item.ordinal,handle:copy(item.read),read};
}
function savedEnvelope(value,expected){
 if(value?.schema_version!=='laplace.workflow-definition/1'||value.definition_id!==expected.definition_id||value.scope_id!==expected.scope_id||!equal(value.scope,expected.scope)||value.version!==expected.version||value.selected_version!==expected.version||value.head_at_start!==expected.head_at_start||value.cut!==expected.cut||value.ordinal!==expected.ordinal||value.read_only!==true)throw Error('The saved body returned another workflow, version, scope or cut. Its contents were withheld.');
 definitionRef(value.reference,expected.definition_id,expected.version);return value;
}
const body=value=>{if(value?.schema_version!=='laplace.workflow-definition/1'||!Array.isArray(value.steps)||!Array.isArray(value.edges))throw Error('The complete saved text is not a workflow definition.');return value;};
export function createSavedWorkflowBody(expected){
 let chunks=[],characters=0,bytes=0,digest=null,total=null,pages=0,complete=false;
 return {get characters(){return characters;},get pages(){return pages;},get complete(){return complete;},
  async accept(value,handle,{isCurrent=()=>true}={}){
   const request=checkedWorkflowHistoryHandle(handle,{facet:'saved-version',id:expected.definition_id,head:expected.head_at_start,cut:expected.cut,selected:expected.version,bodyOffset:characters});savedEnvelope(value,expected);
   if(complete)throw Error('This saved body has already been assembled.');
   if(value.state!=='BODY_PAGE'){
    if(characters||value.body_verification!=='VERIFIED')throw Error('A partial saved body cannot be replaced by another response shape.');const definition=body(value.definition);if(!isCurrent())return null;complete=true;pages=1;return {owner:copy(value),definition:copy(definition),complete:true,pages,qualification:'Complete owner-issued saved version; read only.'};
   }
   const p=value.body_page,text=value.content,length=typeof text==='string'?Array.from(text).length:-1;
   if(value.definition!==null||!p||p.unit!=='Unicode-code-point'||p.offset!==characters||!integer(p.returned,1)||p.returned!==length||!integer(p.total_chars,1,200000)||characters+length>p.total_chars||p.at_end!==(characters+length===p.total_chars)||!pin(p.sha256)||digest&&p.sha256!==digest||total!==null&&p.total_chars!==total)throw Error('Saved body parts changed identity, order, extent or digest. No complete body was displayed.');
   const nextCharacters=characters+length,nextBytes=bytes+new TextEncoder().encode(text).length;if(nextBytes>200000)throw Error('The saved body exceeds the existing single-body byte bound.');
   if(value.next_body_read)checkedWorkflowHistoryHandle(value.next_body_read,{facet:'saved-version',id:expected.definition_id,head:expected.head_at_start,cut:expected.cut,selected:expected.version,bodyOffset:nextCharacters});else if(!p.at_end)throw Error('The saved body has no exact next part.');
   if(p.at_end&&value.next_body_read)throw Error('The final saved body part still offers a continuation.');
   const nextChunks=[...chunks,text];let definition=null,raw=null;if(p.at_end){raw=nextChunks.join('');if(await feedbackWireDigest(raw)!==p.sha256)throw Error('The complete saved body does not match its retained byte digest.');try{definition=body(JSON.parse(raw));}catch(error){throw Error('The pinned saved body could not be read as a complete workflow: '+error.message);}}
   if(!isCurrent())return null;chunks=nextChunks;characters=nextCharacters;bytes=nextBytes;digest=p.sha256;total=p.total_chars;pages++;complete=p.at_end;
   return {owner:copy(value),definition:definition?copy(definition):null,complete,pages,characters,total,body_sha256:digest,raw_text:raw,next_read:copy(value.next_body_read),qualification:complete?'Complete saved definition assembled and byte-pin checked from explicit parts; read only.':'Partial saved text only; no complete definition displayed. Read the next part explicitly.'};
  }
 };
}
export function checkedSavedObjectRead(handle,reference){
 checkedReference(reference);if(reference.owner!=='pipeline.workflow'||reference.kind!=='workflow-definition'||!pin(reference.version?.definition_revision))throw Error('This is not an exact saved workflow object.');const url=new URL(handle?.http?.url||'',here()),q=url.searchParams;let parsed;try{parsed=JSON.parse(q.get('reference')||'null');}catch{}
 if(handle?.http?.method!=='GET'||url.origin!==here().origin||url.pathname!=='/work/discovery'||url.username||url.password||url.hash||q.get('facet')!=='object'||!equal(parsed,reference)||[...q.keys()].some(key=>!['facet','reference','project_lens'].includes(key)||q.getAll(key).length!==1))throw Error('The owner did not issue this exact saved Workspace object read.');
 const request={facet:'object',reference:copy(reference),...(q.has('project_lens')?{project_lens:q.get('project_lens')}:{})};
 if(handle.native&&(handle.native.operation!=='project'||handle.native.payload?.view!=='discovery'||!equal(handle.native.payload?.request,request)))throw Error('The saved Workspace native companion names another object.');
 if(handle.sdk&&(handle.sdk.method!=='request'||!equal(handle.sdk.payload,request)))throw Error('The saved Workspace SDK companion names another object.');return copy(handle);
}
export function savedWorkflowWorkspaceURL(value){
 checkedSavedObjectRead(value.object_read,value.reference);if(!value.scope_id)throw Error('The saved Workspace scope is unavailable.');
 const context=value.history_read?{read:copy(value.history_read),definition_id:value.definition_id,scope_id:value.scope_id,scope:copy(value.scope),version:value.version,head_at_start:value.head_at_start,cut:value.cut}:null;
 return '/project?'+new URLSearchParams({app:'research',subject:JSON.stringify(value.reference),subject_read:JSON.stringify(value.object_read),subject_scope:value.scope_id,...(context?{subject_context:JSON.stringify(context)}:{})});
}

// A project-scoped saved read and the owned Workspace are different admitted
// contexts. Re-observe only the issued bodyless source context when crossing
// them; a URL-carried scope string is data, never permission or a root alias.
export async function resolveSavedWorkflowWorkspace(parameters,workspace,request,{isCurrent=()=>true}={}){
 let reference,read;try{reference=checkedReference(JSON.parse(parameters.get('subject')||'null'));read=checkedSavedObjectRead(JSON.parse(parameters.get('subject_read')||'null'),reference);}catch(error){throw Error('The saved object destination is invalid: '+error.message);}
 const scope=parameters.get('subject_scope');if(!pin(scope)||!workspace?.scope_id)throw Error('The saved object has no qualified source or Workspace scope.');
 if(scope!==workspace.scope_id){
  let context;try{context=JSON.parse(parameters.get('subject_context')||'null');}catch{}
  if(!context||context.scope_id!==scope||context.definition_id!==reference.identity.id||context.version!==reference.version.definition_revision||!definitionScope(context.scope)||!pin(context.head_at_start)||typeof context.cut!=='string'||!context.cut)throw Error('The scoped saved context must be inspected before opening this Workspace object.');
  const issued=checkedWorkflowHistoryHandle(context.read,{facet:'history-page',id:context.definition_id,head:context.head_at_start,cut:context.cut,selected:context.version});
  const observed=checkedWorkflowHistoryPage(await request(issued.url),workflowHistoryExpectation(context,context.read),context.read);
  if(observed.scope_id!==scope||observed.cut!==context.cut||observed.head_at_start!==context.head_at_start||observed.selected_version!==context.version)throw Error('The original saved context changed or belongs to another root. No object was opened.');
 }
 if(!isCurrent())return null;return {reference:copy(reference),read:copy(read),source_scope_id:scope,workspace_scope_id:workspace.scope_id};
}
