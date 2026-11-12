// Workflow definition consumer. pipeline.workflow owns identity, admission, settings and effects.
// This port owns only qualified selection, immutable delivery, authored drafts and attempts.
// A draft retains its first owner-issued action guard; rereading never rebases it. Compare and
// explicit adoption are separate. Unknown POST outcomes are kept and never replayed automatically.
import {ownerRequest} from './owner-request.mjs';
import {createSelectedLifetime} from './selected-lifetime.mjs';
import {readWorkflowOperation,sameWorkflowOperation} from './workspace-workflow-operation.mjs';
import {messageTarget} from './workspace-interaction.mjs';
import {workflowActionInput,workflowActionSummary} from './workflow-action-context.mjs';
const clone=value=>value==null?value:structuredClone(value);
const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
const id=()=>globalThis.crypto?.randomUUID?.()||'local-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2);
export const WORKFLOW_CAPTURE='laplace.workflow-drafts/1';
export const WORKFLOW_ENTRY='/work/workflow-definitions';
const handleURL=handle=>handle?.http?.url;
const readHandle=value=>value?.read_handle||value?.read;
const currentHandle=value=>value?.current_read_handle||readHandle(value);
const version=value=>value?.version||value?.definition_revision;
export async function workflowRequest(path,payload,options){
  const response=await ownerRequest(path,payload,{...options,headers:{...(payload?{'X-Laplace-Writing':'1'}:{}),...options?.headers}});
  if(!response.ok)throw Object.assign(Error(response.value?.error||'Workflow owner refused ('+response.status+').'),{result:response.value,status:response.status});
  return response.value;
}
// Why two stages cannot trade places, or null. Their arrows and drawing positions are exchanged by
// the swap; a hand-over target (assignment.handoff.downstream) or a context choice
// (assignment.context[].step_id) that names either stage, and a stage's own upstream-return choice
// (which the owner checks against its incoming arrows), would not follow, so they block the move.
export function workflowSwapBlocker(body,a,b){
  const steps=Array.isArray(body?.steps)?body.steps:[],title=key=>steps.find(row=>row.id===key)?.title||key,moved=new Set([a,b]);
  for(const step of steps){const assignment=step.assignment||{};
    const named=(assignment.handoff?.downstream||[]).find(target=>moved.has(target));if(named)return title(step.id)+' names '+title(named)+' in its hand-over. Change that hand-over before moving these stages.';
    for(const entry of Array.isArray(assignment.context)?assignment.context:[]){
      if(moved.has(entry?.step_id))return title(step.id)+' reads '+title(entry.step_id)+' in its context choices. Change that choice before moving these stages.';
      if(entry?.kind==='upstream-return'&&moved.has(step.id))return title(step.id)+' reads the result of the stage before it in its context choices. Change that choice before moving it.';}}
  return null;
}
// ROUTE PATTERNS (wave 12). Each pattern is one draft edit that inserts only ordinary steps and edges
// (edge kinds control, data, feedback). Whether the owner admits the draft a pattern makes is not decided
// here: the definition owner's checks (workflow_definitions.validate, run first by the execution preview,
// workflow_operations._selected) and its execution profiles (workflow_operations._preview) answer through
// the owner's execution preview (the offer Check execution follows), asked about workflowPatternProbe of
// the pattern's result. workflowPatternBlocker says only what the page still needs to build that draft.
// The draft edit a pattern is, with the ids its new steps and arrows will carry (fixed by the caller, so
// the draft the owner is asked about is the draft the press applies).
export function workflowPatternIntent(kind,{step=null,partner=null,reads=[],ids={}}={}){
  if(kind==='review')return {type:'review-after',after:step,id:ids.step,edge_id:ids.edge,feedback_id:ids.feedback};
  if(kind==='reciprocal')return {type:'reciprocal-review',a:step,b:partner,ids:{copy:ids.copy,ra:ids.ra,rb:ids.rb,ra_edge:ids.ra_edge,ra_feedback:ids.ra_feedback,rb_edge:ids.rb_edge,rb_feedback:ids.rb_feedback}};
  if(kind==='synthesis')return {type:'synthesis',reads,id:ids.step,edge_ids:reads.map((_,index)=>ids.edges?.[index])};
  throw Error('Unknown route pattern: '+kind);
}
// What the owner's execution preview is asked about for a pattern: its result, with every empty
// instruction given a stand-in sentence, so the owner answers whether its execution profiles run these
// steps and arrows; the instructions themselves are written after the press, and Check execution then
// asks the owner about the draft exactly as it is. The stand-in is sent only in this pure read.
export const WORKFLOW_PATTERN_PROBE_INSTRUCTION='Instructions are written after this pattern is added.';
export function workflowPatternProbe(made){
  const out=clone(made);for(const row of out.steps||[])if(row.assignment&&!String(row.assignment.instructions||'').trim())row.assignment={...row.assignment,instructions:WORKFLOW_PATTERN_PROBE_INSTRUCTION};
  return out;
}
export function workflowPatternBlocker(body,kind,{step=null,partner=null,reads=[]}={}){
  const steps=Array.isArray(body?.steps)?body.steps:[],at=key=>steps.some(row=>row.id===key);
  if(kind==='synthesis')return reads.length?null:'Choose the steps the synthesis reads.';
  if(!at(step))return 'Choose a step on the drawing.';
  if(kind==='reciprocal'&&partner&&(partner===step||!at(partner)))return 'Choose two different steps.';
  return null;
}
// The draft a pattern makes, without asking whether it may (editWorkflow asks workflowPatternBlocker first).
// 'Add a review of this step': an adversary step straight after it (insert-after), a control arrow from it and a
// feedback arrow back, with the settings it is given (none: it inherits). 'Make these two review each other': a
// reviewer for each builder (B's settings review A, A's review B), with B a copy of A (its role, instructions and
// settings only) when no partner is chosen. 'Add a synthesis that reads these': a step with the owner's synthesis role
// (run in the original conversation, workflow_operations._preview) and a data arrow from each chosen step.
export function workflowPatternResult(body,intent){
  const out=clone(body),steps=out.steps||(out.steps=[]),edges=out.edges||(out.edges=[]);
  if(intent.type==='review-after'){const after=steps.find(row=>row.id===intent.after);if(!after)throw Error('Choose a step on the drawing.');const key=intent.id||'step-'+id();
    const next=editWorkflow(out,{type:'insert-after',after:after.id,id:key,title:'Review of '+(after.title||after.id),role:'adversary',edge_id:intent.edge_id});
    const review=next.steps.find(row=>row.id===key);review.assignment.settings=clone(intent.settings||{});next.edges.push({id:intent.feedback_id||'edge-'+id(),from:review.id,to:after.id,kind:'feedback'});return next;}
  if(intent.type==='reciprocal-review'){const a=steps.find(row=>row.id===intent.a);let b=intent.b?steps.find(row=>row.id===intent.b):null;
    if(!a||intent.b&&(!b||b===a))throw Error('Choose two different steps.');const ids=intent.ids||{};
    if(!b){const copy={id:ids.copy||'step-'+id(),title:'Copy of '+(a.title||a.id),parent_id:a.parent_id||null,assignment:{role:a.assignment.role,instructions:a.assignment.instructions||'',settings:clone(a.assignment.settings||{})},inputs:[],outputs:[],targets:[]};steps.splice(steps.indexOf(a)+1,0,copy);b=copy;}
    const sa=settingsOf(a),sb=settingsOf(b),next=workflowPatternResult(out,{type:'review-after',after:a.id,id:ids.ra||'step-'+id(),settings:sb,edge_id:ids.ra_edge,feedback_id:ids.ra_feedback});
    return workflowPatternResult(next,{type:'review-after',after:b.id,id:ids.rb||'step-'+id(),settings:sa,edge_id:ids.rb_edge,feedback_id:ids.rb_feedback});}
  if(intent.type==='synthesis'){const reads=(intent.reads||[]).filter(key=>steps.some(row=>row.id===key)),key=intent.id||'step-'+id();if(steps.some(row=>row.id===key))throw Error('A step already uses this id.');
    steps.push({id:key,title:'Synthesis',parent_id:null,assignment:{role:'synthesis',instructions:'',settings:{}},inputs:[],outputs:[],targets:[]});reads.forEach((from,index)=>edges.push({id:intent.edge_ids?.[index]||'edge-'+id(),from,to:key,kind:'data'}));return out;}
  throw Error('Unknown route pattern: '+intent.type);
}
const settingsOf=step=>Object.fromEntries(['provider','model','effort'].filter(key=>Object.hasOwn(step?.assignment?.settings||{},key)).map(key=>[key,step.assignment.settings[key]]));
export function emptyWorkflow(){return {schema_version:'laplace.workflow-definition/1',title:'New workflow',description:'',settings:{},layout:{},steps:[],edges:[]};}
// Local authoring only; the owner independently validates every saved definition.
export function editWorkflow(body,intent){
  const out=clone(body),steps=out.steps||(out.steps=[]),edges=out.edges||(out.edges=[]),step=steps.find(row=>row.id===intent.id);
  if(intent.type==='fields'){Object.assign(out,clone(intent.fields));return out;}
  if(intent.type==='default-setting'){out.settings={...out.settings};if(intent.value==='')delete out.settings[intent.key];else out.settings[intent.key]=intent.value;return out;}
  if(intent.type==='add'){const key=intent.id||'step-'+id();if(steps.some(row=>row.id===key))throw Error('A step already uses this id.');steps.push({id:key,title:intent.title||'New step',parent_id:intent.parent_id||null,assignment:{role:intent.role||'builder',instructions:'',settings:{}},inputs:[],outputs:[],targets:[]});return out;}
  if(intent.type==='connect'){if(!steps.some(row=>row.id===intent.from)||!steps.some(row=>row.id===intent.to))throw Error('Both edge ends must be steps in this draft.');edges.push({id:intent.edge_id||'edge-'+id(),from:intent.from,to:intent.to,kind:intent.kind||'control'});return out;}
  if(intent.type==='remove-edge'){out.edges=edges.filter(row=>row.id!==intent.id);return out;}
  // A stage added on the drawing goes straight after the chosen one: what that stage passed forward
  // (its control arrows) now leaves from the new stage, and the chosen one passes forward to it. Data
  // and feedback arrows keep their ends, because they name whose output is read or revised.
  if(intent.type==='insert-after'){const after=steps.find(row=>row.id===intent.after);if(!after)throw Error('Choose a stage in this draft.');const key=intent.id||'step-'+id();if(steps.some(row=>row.id===key))throw Error('A step already uses this id.');steps.splice(steps.indexOf(after)+1,0,{id:key,title:intent.title||'New stage',parent_id:after.parent_id||null,assignment:{role:intent.role||'builder',instructions:'',settings:{}},inputs:[],outputs:[],targets:[]});for(const edge of edges)if(edge.from===after.id&&edge.kind==='control')edge.from=key;edges.push({id:intent.edge_id||'edge-'+id(),from:after.id,to:key,kind:'control'});return out;}
  // Changing the order swaps two stages' places: the drawing keeps its shape (every arrow keeps its
  // place) and the two stages, with their own instructions and settings, trade positions in it. A
  // hand-over target or context choice that names either stage would then point at the wrong place,
  // so the swap is refused there (workflowSwapBlocker) instead of leaving a draft Save must refuse.
  if(intent.type==='swap'){const a=steps.find(row=>row.id===intent.a),b=steps.find(row=>row.id===intent.b);if(!a||!b||a===b)throw Error('Choose two different stages in this draft.');const blocked=workflowSwapBlocker(body,a.id,b.id);if(blocked)throw Error(blocked);const ia=steps.indexOf(a),ib=steps.indexOf(b);steps[ia]=b;steps[ib]=a;const flip=value=>value===a.id?b.id:value===b.id?a.id:value;for(const edge of edges){edge.from=flip(edge.from);edge.to=flip(edge.to);}const la=out.layout?.[a.id],lb=out.layout?.[b.id];if(la||lb){out.layout={...out.layout};if(lb)out.layout[a.id]=lb;else delete out.layout[a.id];if(la)out.layout[b.id]=la;else delete out.layout[b.id];}return out;}
  // A route pattern: refused where the page cannot build its draft (workflowPatternBlocker), else its draft; the owner's preview is asked before a press applies it.
  if(intent.type==='review-after'||intent.type==='reciprocal-review'||intent.type==='synthesis'){
    const kind=intent.type==='review-after'?'review':intent.type==='reciprocal-review'?'reciprocal':'synthesis',reads=(intent.reads||[]).filter(key=>steps.some(row=>row.id===key));
    const blocked=workflowPatternBlocker(body,kind,{step:intent.after||intent.a||null,partner:intent.b||null,reads});if(blocked)throw Error(blocked);
    return workflowPatternResult(body,{...intent,...(kind==='synthesis'?{reads}:{})});}
  if(!step)throw Error('Select a step in this draft.');
  if(intent.type==='step'){Object.assign(step,clone(intent.fields));return out;}
  if(intent.type==='assignment'){step.assignment={...step.assignment,...clone(intent.fields)};return out;}
  if(intent.type==='setting'){step.assignment={...step.assignment,settings:{...step.assignment?.settings}};if(intent.value==='')delete step.assignment.settings[intent.key];else step.assignment.settings[intent.key]=intent.value;return out;}
  if(intent.type==='nest'){
    const parent=intent.parent_id||null;if(parent&&!steps.some(row=>row.id===parent))throw Error('The parent must be a step in this draft.');
    let cursor=parent;const seen=new Set([step.id]);while(cursor){if(seen.has(cursor))throw Error('Containment cannot form a cycle.');seen.add(cursor);cursor=steps.find(row=>row.id===cursor)?.parent_id;}
    step.parent_id=parent;return out;
  }
  if(intent.type==='move'){out.layout={...out.layout,[step.id]:{x:intent.x,y:intent.y}};return out;}
  // bridge (a stage removed on the drawing): what passed forward into it now passes to what it passed forward to.
  // Removing a stage keeps the chain: each stage that passed forward to it now passes forward to the
  // stages it passed to (control arrows only). Its data and feedback arrows go with it.
  if(intent.type==='remove'){out.steps=steps.filter(row=>row.id!==step.id);out.steps.forEach(row=>{if(row.parent_id===step.id)row.parent_id=step.parent_id||null;});out.edges=edges.filter(row=>row.from!==step.id&&row.to!==step.id);for(const before of edges.filter(row=>row.to===step.id&&row.kind==='control'&&row.from!==step.id))for(const after of edges.filter(row=>row.from===step.id&&row.kind==='control'&&row.to!==step.id))if(before.from!==after.to&&!out.edges.some(row=>row.from===before.from&&row.to===after.to&&row.kind==='control'))out.edges.push({id:'edge-'+id(),from:before.from,to:after.to,kind:'control'});return out;}
  throw Error('Unknown workflow edit: '+intent.type);
}
export function createWorkflowPort({request=workflowRequest,initial=null,initialListing=null,now=()=>new Date().toISOString()}={}){
  const life=createSelectedLifetime({qualify:ref=>ref.id}),objects=new Map(),drafts=new Map(),attempts=new Map(),comparisons=new Map(),contexts=new Map(),aliases=new Map(),released=new Set();let listing=null,scopeId=null,creationChoices=null,lastEvent='initial',selectionStep=initial?.schema===WORKFLOW_CAPTURE?initial.step||null:null;
  if(initial?.schema===WORKFLOW_CAPTURE){scopeId=initial.scope_id;for(const row of initial.drafts||[])drafts.set(row.id,clone(row));for(const row of initial.attempts||[])attempts.set(row.id,{...clone(row),...(['preparing','pending'].includes(row.withdraw_status)?{withdraw_status:'uncertain'}:{}),...(row.status==='pending'?{status:'uncertain',error:'The page closed before an owner response; nothing was resent.'}:{})});if(initial.selection)life.select(clone(initial.selection));}
  if(initialListing){if(scopeId&&scopeId!==initialListing.scope_id)throw Error('Recovery belongs to another workspace.');scopeId=initialListing.scope_id;listing=clone(initialListing);}
  for(const row of initial?.contexts||[]){const fields=clone(row.fields);for(const draft of Object.values(fields.lineage_actions||{}))if(draft.pending)draft.pending={...draft.pending,observation:'UNKNOWN'};contexts.set(row.id,fields);}
  // A discarded never-saved local draft has no owner identity: its selection closes instead of reading a phantom id.
  const selected=()=>{const key=aliases.get(life.selection?.id)||life.selection?.id||null;return key&&released.has(key)?null:key;};
  const selectedReference=()=>life.selection&&selected()?{...life.selection,id:selected(),read:readHandle(objects.get(selected())?.value)||life.selection.read}:null;
  const snapshot=()=>clone({scope_id:scopeId,listing,creation_choices:creationChoices,selection:selectedReference(),step:selectionStep,read:objects.get(selected())||null,draft:drafts.get(selected())||null,attempt:attempts.get(selected())||null,comparison:comparisons.get(selected())||null,context:contexts.get(selected())||{},event:lastEvent,visit_depth:life.visitDepth,has_unresolved:unresolved()});
  function notify(event){lastEvent=event;life.notify(snapshot());}
  function unresolved(){return drafts.size>0||[...contexts.values()].some(row=>row.node||row.goal||row.paths||Object.values(row.lineage_actions||{}).some(draft=>draft.dirty||draft.pending||draft.last&&!draft.last.acknowledged))||[...attempts.values()].some(row=>['pending','uncertain'].includes(row.status));}
  function acceptScope(value){if(!value?.scope_id)throw Error('The workflow owner returned no recovery scope identity.');if(scopeId&&scopeId!==value.scope_id)throw Error('This workflow reply belongs to another workspace scope. The draft was kept.');scopeId=value.scope_id;}
  async function list(handle){const token=life.issue('@list');const value=await request(handleURL(handle)||handleURL(listing?.library_read)||WORKFLOW_ENTRY);if(life.superseded('@list',token))return null;acceptScope(value);life.accept('@list',token);listing=clone(handle?{...value,definitions:[...(listing?.definitions||[]),...(value.definitions||[])]}:value);notify('list');return value;}
  async function read(handle,{compare=false,target=selected()}={}){
    const key=target;if(!key||key.startsWith('local:'))return null;const url=handleURL(handle);if(!url)throw Error('The owner exposed no read handle.');
    const token=life.issue(key);try{const value=await request(url);if(life.superseded(key,token))return null;acceptScope(value);if(value.definition_id!==key||!value.definition)throw Error('The owner returned another workflow or no definition.');life.accept(key,token);objects.set(key,{value:clone(value),at:now(),io:'ready'});
      if(compare)comparisons.set(key,{draft:clone(drafts.get(key)?.definition),current:clone(value.definition),basis:clone(value.actions?.save),version:version(value),token});
      else if(comparisons.get(key)&&!same(comparisons.get(key).basis,value.actions?.save))comparisons.delete(key);
      const attempt=attempts.get(key);if(attempt?.status==='uncertain')attempts.set(key,{...attempt,observation:{version:version(value),matches_draft:same(value.definition,attempt.definition),at:now()}});
      notify(compare?'compare':'read');return value;
    }catch(error){if(!life.superseded(key,token)){const old=objects.get(key);objects.set(key,{...old,io:'error',error:error.message});notify('read-error');}throw error;}
  }
  function draft(){const key=selected(),held=drafts.get(key);if(held)return held;const value=objects.get(key)?.value,action=value?.actions?.save;
    if(!action?.permitted)throw Error(action?.reason||'The owner has not permitted editing this definition.');
    const row={id:key,definition:clone(value.definition),basis:clone(action),read:clone(currentHandle(value)),at:now()};drafts.set(key,row);return row;}
  async function submit(operation,fields={}){
    const key=selected(),held=operation==='save'?drafts.get(key):null,value=objects.get(key)?.value,action=held?.basis||value?.actions?.[operation];
    if(operation==='save'&&!held)throw Error('There is no workflow draft to save.');
    if(operation==='save'&&held.needs_adoption)throw Error('This draft continued while its identity was being created. Compare and adopt the saved workflow guard before saving again.');
    if(operation==='save'&&Object.values(held.invalid_fields||{}).some(Boolean))throw Error('Repair the retained invalid input/output text before saving.');
    if(operation==='prepare'&&drafts.has(key))throw Error('Save or discard this draft before preparing a saved version.');
    if(!action?.permitted||action.http?.method!=='POST'||!action.http?.url)throw Error(action?.reason||'The owner exposed no permitted '+operation+' action.');
    if(['pending','uncertain'].includes(attempts.get(key)?.status))throw Error('This workflow has an unresolved attempt. Reinspect and resolve it before sending another action.');
    const requestId=id(),payload={...clone(action.payload),...clone(fields),request_id:requestId,...(held?{definition:clone(held.definition)}:{})};
    const attempt={id:key,operation,request_id:requestId,status:'pending',definition:clone(held?.definition),payload:clone(payload),withdrawal_offer:clone(action.withdrawal),scope:clone(value?.scope||action.payload?.scope||{kind:listing?.scope?.kind,...(listing?.scope?.kind==='project'?{namespace:listing.scope.namespace}:{})}),at:now()};attempts.set(key,attempt);notify('pending');
    let result;try{result=await request(action.http.url,payload);}catch(error){if(life.disposed||!currentAttempt(key,attempt))return null;if(['withdrawn','recorded'].includes(latestAttempt(key,attempt)?.status))return latestAttempt(key,attempt).result;const effect=error.result?.effect;attempts.set(key,{...latestAttempt(key,attempt),status:error.result?(effect==='unknown'?'uncertain':effect&&effect!=='none'?'partial':'refused'):'uncertain',error:error.message,result:clone(error.result),effect:effect||'effect not stated by owner'});notify('result');return null;}
    if(life.disposed||!currentAttempt(key,attempt))return null;
    const heldTerminal=terminalObservation(key,attempt,result);if(heldTerminal)return heldTerminal;
    const settled=latestAttempt(key,attempt);if(settled?.status==='recorded'&&result?.receipt?.request_id===requestId&&sameWorkflowOperation(settled.result?.receipt,result.receipt))return settled.result;
    if(settleNotAdmitted(key,attempt,result))return result;
    const expected=operation==='save'?'saved':'prepared',receipt=result?.receipt;
    if(result?.effect!==expected||!receipt||receipt.request_id!==requestId||!receipt.definition_id||!receipt.definition_revision||(operation==='save'&&result.definition_id!==receipt.definition_id)||(operation==='prepare'&&receipt.definition_id!==key)){attempts.set(key,{...latestAttempt(key,attempt),status:'uncertain',result:clone(result),error:'The response did not include the matching owner effect receipt. Reinspect; nothing was resent.'});notify('result');return result;}
    const settlement=latestAttempt(key,attempt);let target=key;if(operation==='save'){
      target=result.definition_id||receipt.definition_id;if(!target){attempts.set(key,{...latestAttempt(key,attempt),status:'uncertain',result:clone(result),error:'The saved effect named no definition identity.'});notify('result');return result;}
      // Editing while a save is pending keeps the newer draft and its original guard.
      if(drafts.get(key)===held)drafts.delete(key);if(target!==key){const newer=drafts.get(key);if(newer){drafts.delete(key);drafts.set(target,{...newer,id:target,read:clone(currentHandle(result)),needs_adoption:true});}if(contexts.has(key)){contexts.set(target,contexts.get(key));contexts.delete(key);}attempts.delete(key);aliases.set(key,target);}
    }
    attempts.set(target,{...settlement,id:target,status:'recorded',effect:result.effect,result:clone(result)});notify('result');
    try{await read(readHandle(result)||currentHandle(value),{target});}catch(error){const at=currentAttempt(target,attempt);if(at)attempts.set(target,{...at,postimage_error:error.message});notify('result');}
    if(operation==='save')try{await list();}catch(error){const at=currentAttempt(target,attempt);if(at)attempts.set(target,{...at,list_error:error.message});notify('result');}return result;
  }
  const currentAttempt=(key,attempt)=>{const row=attempts.get(aliases.get(key)||key);return row?.request_id===attempt.request_id?row:null;};
  function terminalObservation(key,attempt,value){
    const current=currentAttempt(key,attempt);if(!current||!['withdrawn','recorded'].includes(current.status))return null;
    const positive=value?.effect===(attempt.operation==='save'?'saved':'prepared')&&value.receipt?.request_id===attempt.request_id&&typeof value.receipt.definition_id==='string'&&typeof value.receipt.definition_revision==='string';
    const negative=value?.schema_version==='laplace.workflow-request-decision/1'&&value.status==='NOT_ADMITTED'&&value.effect==='NOT_ADMITTED'&&value.terminal===true&&value.request_id===attempt.request_id&&value.operation===attempt.operation&&value.scope_id===scopeId;
    const incompatible=current.status==='withdrawn'&&positive||current.status==='recorded'&&negative||current.status==='recorded'&&positive&&!sameWorkflowOperation(current.result?.receipt,value.receipt);
    if(incompatible){attempts.set(aliases.get(key)||key,{...current,status:'uncertain',contradictory_response:clone(value),retained_terminal_result:clone(current.result),error:'Incompatible positive owner receipts need inspection. Both are retained; no replacement was sent.'});notify('result');return value;}
    // An older UNKNOWN, refusal or connection observation cannot revoke an
    // exact terminal decision, even if it arrives after the author moved on.
    return current.result;
  }
  const latestAttempt=(key,fallback)=>{const row=attempts.get(aliases.get(key)||key);return row?.request_id===fallback.request_id?row:fallback;};
  function settleNotAdmitted(key,attempt,value){
    if(!currentAttempt(key,attempt))return false;
    if(value?.schema_version!=='laplace.workflow-request-decision/1'||value.status!=='NOT_ADMITTED'||value.effect!=='NOT_ADMITTED'||value.terminal!==true||value.reason!=='WITHDRAWN'||value.request_id!==attempt.request_id||value.operation!==attempt.operation||value.scope_id!==scopeId||!/^sha256:[a-f0-9]{64}$/.test(value.intent_digest||''))return false;
    const current=latestAttempt(key,attempt),digest=current.withdrawal_preparation?.intent_digest;
    if(digest&&value.intent_digest!==digest||attempt.scope&&!sameWorkflowOperation(value.scope,attempt.scope))throw Error('Non-admission belongs to another original workflow intent or scope.');
    attempts.set(aliases.get(key)||key,{...current,status:'withdrawn',effect:'NOT_ADMITTED',withdraw_status:'settled',result:clone(value),withdrawal_result:clone(value),error:null});notify('result');return true;
  }
  async function withdraw(){
    const key=selected(),attempt=attempts.get(key),offer=attempt?.withdrawal_offer;
    if(!attempt||!['pending','uncertain'].includes(attempt.status)||!offer?.prepare_read)throw Error('This exact original request has no offered withdrawal preparation.');
    if(['preparing','pending'].includes(attempt.withdraw_status))throw Error('Withdrawal already awaits its original owner response.');
    const original=clone(attempt.payload);attempts.set(key,{...attempt,withdraw_status:'preparing'});notify('withdrawal');
    let prepared;
    try{prepared=await readWorkflowOperation(offer,{original_request:original},{request,expected:{scope_id:scopeId},isCurrent:()=>!life.disposed&&!!currentAttempt(key,attempt)});if(!prepared||!currentAttempt(key,attempt))return null;
      const handle=prepared.withdraw,u=new URL(handle?.http?.url||'',globalThis.location?.href||'http://local/project'),base=handle?.http?.payload;
      if(handle?.http?.method!=='POST'||u.origin!==new URL(globalThis.location?.href||'http://local/project').origin||u.pathname!=='/work/workflow-definitions/withdraw'||u.hash||[...u.searchParams.keys()].some(name=>name!=='project_lens'||u.searchParams.getAll(name).length!==1)||base?.action!=='withdraw'||base?.operation!==attempt.operation||base?.request_id!==attempt.request_id||base?.intent_digest!==prepared.intent_digest||!sameWorkflowOperation(handle.required_inputs,['original_request'])||handle.native&&(!sameWorkflowOperation(handle.native.payload,base)||handle.native.operation!=='workflow_definition_change')||handle.sdk&&(!sameWorkflowOperation(handle.sdk.payload,base)||handle.sdk.method!=='workflow_withdraw'))throw Error('The owner returned no matching original-request withdrawal action.');
      const current=latestAttempt(key,attempt);if(!['pending','uncertain'].includes(current.status)){attempts.set(aliases.get(key)||key,{...current,withdraw_status:'recorded-no-undo'});notify('withdrawal');return current.result;}
      attempts.set(key,{...current,withdraw_status:'pending',withdrawal_preparation:clone(prepared)});notify('withdrawal');
      const result=await request(u.pathname+u.search,{...clone(base),original_request:original});if(life.disposed||!currentAttempt(key,attempt))return null;
      const terminal=terminalObservation(key,attempt,result);if(terminal){const won=currentAttempt(key,attempt);if(won?.status==='recorded'){attempts.set(aliases.get(key)||key,{...won,withdraw_status:'recorded-no-undo'});notify('withdrawal');}return terminal;}
      if(settleNotAdmitted(key,attempt,result))return result;
      const latest=latestAttempt(key,attempt);
      if(result?.status==='RECORDED'&&result.withdrawal==='ALREADY_RECORDED_NO_UNDO'&&result.withdrawal_operation===attempt.operation&&result.intent_digest===prepared.intent_digest&&result.receipt?.request_id===attempt.request_id){attempts.set(key,{...latest,withdraw_status:'recorded-no-undo',withdrawal_result:clone(result)});notify('withdrawal');if(latest.status!=='recorded'){attempts.set(key,{...attempts.get(key),status:'uncertain'});await recover(key);}return result;}
      attempts.set(key,{...latest,withdraw_status:'uncertain',withdrawal_result:clone(result),error:'Withdrawal is unconfirmed. Keep the original wire and inspect its owner; nothing was resent.'});notify('withdrawal');return result;
    }catch(error){if(!life.disposed&&currentAttempt(key,attempt)){const current=latestAttempt(key,attempt);if(current.status!=='withdrawn')attempts.set(key,{...current,withdraw_status:'uncertain',withdrawal_error:error.message});notify('withdrawal');}return null;}
  }
  async function recover(targetKey=selected()){
    const key=targetKey,attempt=attempts.get(key),action=listing?.actions?.inspect_request||listing?.recovery;if(!attempt||attempt.status==='pending')throw Error('There is no finished uncertain attempt to inspect.');
    if(action?.http?.method!=='GET'||!action.http.url)throw Error('The owner exposed no request inspection handle.');
    const url=new URL(action.http.url,globalThis.location?.href||'http://same-origin.invalid/');url.searchParams.set('request_id',attempt.request_id);let result;try{result=await request(url.pathname+url.search);}catch(error){const current=currentAttempt(key,attempt);if(!current||['withdrawn','recorded'].includes(current.status))return current?.result||null;throw error;}
    if(life.disposed||!currentAttempt(key,attempt))return null;
    const winner=terminalObservation(key,attempt,result);if(winner)return winner;
    if(settleNotAdmitted(key,attempt,result))return result;
    if(result?.status!=='RECORDED'){attempts.set(key,{...latestAttempt(key,attempt),status:'uncertain',recovery:clone(result),observation:{status:result?.status||'UNKNOWN',at:now()},error:'The owner has not confirmed a recorded effect. The draft is retained; nothing was resent.'});notify('result');return result;}
    const receipt=result.receipt,expected=attempt.operation==='save'?'saved':'prepared';if(result.effect!==expected||receipt?.request_id!==attempt.request_id||!receipt.definition_id||!receipt.definition_revision)throw Error('Request inspection returned no matching effect receipt.');
    const settlement=latestAttempt(key,attempt),target=receipt.definition_id;if(!key.startsWith('local:')&&target!==key)throw Error('Request inspection named another workflow.');
    if(attempt.operation==='save'){
      const held=drafts.get(key);if(held&&same(held.definition,attempt.definition))drafts.delete(key);
      if(target!==key){if(drafts.has(key)){drafts.set(target,{...drafts.get(key),id:target,read:clone(currentHandle(result)),needs_adoption:true});drafts.delete(key);}if(contexts.has(key)){contexts.set(target,contexts.get(key));contexts.delete(key);}attempts.delete(key);aliases.set(key,target);}
    }
    attempts.set(target,{...settlement,id:target,status:'recorded',effect:result.effect,result:clone(result),recovered:true});notify('result');
    await read(readHandle(result),{target});return result;
  }
  async function readCreationChoices(handle=null){
    const issued=handle||listing?.creation_choices_read;if(!issued)throw Error('The owner offered no workflow ownership choices.');
    const url=workflowReadURL(issued),q=new URL(url,globalThis.location?.href||'http://local/project').searchParams;
    if(q.get('facet')!=='creation-choices'||[...q.keys()].some(key=>!['facet','offset','limit','as_of','project_lens'].includes(key)||q.getAll(key).length!==1))throw Error('Invalid workflow ownership choice read.');
    if(handle&&!same(handle,creationChoices?.value?.next_read))throw Error('Use the currently offered ownership continuation.');
    const previous=creationChoices;creationChoices={...previous,io:'loading'};notify('creation-choices');
    try{const value=await request(url);if(life.disposed)return null;
      if(value?.schema_version!=='laplace.workflow-operation/1'||value.view!=='creation-choices'||value.read_only!==true||value.scope_id!==scopeId||!Array.isArray(value.items)||!Number.isSafeInteger(value.total)||value.total<value.items.length||!Number.isSafeInteger(value.offset)||value.offset<0||typeof value.cut!=='string')throw Error('The workflow ownership reply belongs to another context.');
      if(handle&&(value.cut!==previous?.value?.cut||value.offset!==(previous?.items||[]).length))throw Error('Workflow ownership choices changed; read them again.');
      for(const item of value.items){const scope=item.scope,action=item.create,u=new URL(action?.http?.url||'',globalThis.location?.href||'http://local/project');
        if(!scope||!['owned-workspace','project'].includes(scope.kind)||scope.kind==='project'&&(typeof scope.namespace!=='string'||!scope.namespace)||Object.keys(scope).some(key=>!['kind',...(scope.kind==='project'?['namespace']:[])].includes(key))||!same(action?.payload?.scope,scope)||action?.payload?.expected_revision!==null||action?.http?.method!=='POST'||u.origin!==new URL(globalThis.location?.href||'http://local/project').origin||u.pathname!=='/work/workflow-definitions/save'||[...u.searchParams.keys()].some(key=>key!=='project_lens'||u.searchParams.getAll(key).length!==1))throw Error('An ownership choice has no matching owner-issued create action.');
      }
      const items=handle?[...previous.items,...value.items]:value.items,keys=items.map(item=>JSON.stringify(item.scope));if(new Set(keys).size!==keys.length)throw Error('Workflow ownership choices repeat an identity.');
      creationChoices={io:'ready',value:clone(value),items:clone(items)};notify('creation-choices');return value;
    }catch(error){if(!life.disposed){creationChoices={...previous,io:'error',error:error.message};notify('creation-choices');}throw error;}
  }
  async function dispatch(intent){life.live();const key=selected();
    if(intent.type==='creation-choices'){await readCreationChoices(intent.read);return snapshot();}
    if(intent.type==='list'){await list(intent.read);return snapshot();}
    if(intent.type==='select'){life.select({id:intent.id,read:clone(intent.read)});selectionStep=intent.step||null;notify('selection');if(!intent.id.startsWith('local:'))await read(intent.read);return snapshot();}
    if(intent.type==='create'){const choice=intent.choice&&creationChoices?.items?.find(row=>same(row.scope,intent.choice));if(listing?.creation_choices_read&&!choice)throw Error('Choose an offered project or reusable workspace design before creating a draft.');const action=choice?.create||listing?.actions?.create;if(!action?.permitted)throw Error(action?.reason||'The owner has not permitted creating a workflow.');const key='local:'+id();drafts.set(key,{id:key,definition:intent.definition?clone(intent.definition):emptyWorkflow(),basis:clone(action),at:now()});life.select({id:key});selectionStep=null;notify('create');return snapshot();}
    if(intent.type==='step'){selectionStep=intent.id;notify('step');return snapshot();}
    if(intent.type==='context'){contexts.set(key,{...contexts.get(key),...clone(intent.fields)});notify('typing');return snapshot();}
    if(intent.type==='text'){const held=draft();drafts.set(key,{...held,text_fields:{...held.text_fields,[intent.name]:intent.value},invalid_fields:{...held.invalid_fields,[intent.name]:intent.invalid}});notify('typing');return snapshot();}
    if(intent.type==='edit'){if(intent.target&&intent.target!==key)throw Error('This field belongs to another workflow.');const held=draft();drafts.set(key,{...held,definition:editWorkflow(held.definition,intent.edit)});comparisons.delete(key);notify(intent.quiet?'typing':'edit');return snapshot();}
    if(intent.type==='reinspect'){await read(currentHandle(objects.get(key)?.value)||life.selection?.read);return snapshot();}
    if(intent.type==='compare'){if(!drafts.has(key))throw Error('There is no draft to compare.');await read(currentHandle(objects.get(key)?.value)||drafts.get(key).read,{compare:true});return snapshot();}
    if(intent.type==='adopt'){const comparison=comparisons.get(key),value=objects.get(key)?.value,held=drafts.get(key);if(!comparison||!held||!same(intent.basis,comparison.basis)||!same(value.actions?.save,comparison.basis))throw Error('Compare with the current owner version before adopting its exact guard.');if(!comparison.basis?.permitted)throw Error(comparison.basis?.reason||'Editing is unavailable.');drafts.set(key,{...held,basis:clone(comparison.basis),needs_adoption:false});comparisons.delete(key);notify('adopt');return snapshot();}
    if(intent.type==='discard'){drafts.delete(key);comparisons.delete(key);if(key?.startsWith('local:')&&!attempts.has(key)){released.add(key);contexts.delete(key);while(!selected()&&life.back());selectionStep=null;}notify('discard');return snapshot();}
    if(intent.type==='withdraw'){await withdraw();return snapshot();}
    if(intent.type==='resolve-attempt'){const attempt=attempts.get(key);if(attempt?.status==='pending')throw Error('The owner response is still pending.');if(attempt?.status==='uncertain')throw Error('Keep the exact original request until the owner confirms a recorded effect or terminal non-admission. An unknown observation is not cancellation.');attempts.delete(key);notify('resolved');return snapshot();}
    if(intent.type==='recover'){await recover();return snapshot();}
    if(intent.type==='save'||intent.type==='prepare'){await submit(intent.type,intent.fields);return snapshot();}
    if(intent.type==='back'){let moved=false;while(life.back()){moved=true;if(selected())break;}if(moved){selectionStep=null;notify('back');}return snapshot();}
    if(intent.type==='dispose'){life.dispose();return null;}throw Error('Unknown workflow intent: '+intent.type);
  }
  return {dispatch,snapshot,subscribe:life.subscribe,hasUnresolved:unresolved,capture:()=>clone({schema:WORKFLOW_CAPTURE,scope_id:scopeId,drafts:[...drafts.values()],attempts:[...attempts.values()],contexts:[...contexts].map(([id,fields])=>({id,fields})),selection:selectedReference(),step:selectionStep}),destroy:()=>life.dispose()};
}

// App dispatch observation is a selected read, never a browser execution/control owner.
const appProfile='laplace.app-dispatch/1';
const ordered=value=>Array.isArray(value)?value.map(ordered):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(key=>[key,ordered(value[key])])):value;
const equivalent=(a,b)=>JSON.stringify(ordered(a))===JSON.stringify(ordered(b));
const here=()=>new URL(globalThis.location?.href||'http://local/project');
export function workflowReadURL(handle,fields={}){
  const url=new URL(handle?.http?.url||'',here());
  if(handle?.http?.method!=='GET'||url.origin!==here().origin||url.pathname!==WORKFLOW_ENTRY)throw Error('The workflow owner issued no qualified read.');
  for(const [key,value]of Object.entries(fields)){if(url.searchParams.has(key))throw Error('Authored fields cannot replace the owner read identity.');url.searchParams.set(key,typeof value==='object'?JSON.stringify(value):String(value));}
  return url.pathname+url.search;
}
export function workflowConversationAction(action,project){
  const payload=action?.payload;
  if(action?.send_required!==true||action.permitted!==true||action.project!==project||action.http?.method!=='POST'||(action.http.route||action.http.url)!=='/authoring/turn'||payload?.project!==project||payload.mode!=='work'||typeof payload.text!=='string'||!payload.text.trim()||Object.keys(payload).some(key=>!['project','text','mode','session_id','work_id','expected_work_scope_revision','expected_dependency_revision','workspace_context'].includes(key))||payload.session_id!==undefined&&(typeof payload.session_id!=='string'||!payload.session_id))throw Error(action?.reason||'The owner issued no matching conversation preparation.');
  const work=['work_id','expected_work_scope_revision','expected_dependency_revision'];
  if(work.some(key=>Object.hasOwn(payload,key))){
    const target=action.work_target;
    if(!payload.session_id||work.some(key=>typeof payload[key]!=='string'||!payload[key])||target?.id!==payload.work_id||target.work_scope_revision!==payload.expected_work_scope_revision||target.dependency_revision!==payload.expected_dependency_revision)
      throw Error('The continuation message has no matching inspected Work target.');
    messageTarget({surface:'project'},target);
  }
  if(action.read?.request?.facet==='app-continue-compose'&&payload.workspace_context===undefined)throw Error('The continuation has no selected action context.');
  if(payload.workspace_context!==undefined){
    if(payload.workspace_context.surface!=='project'||Object.keys(payload.workspace_context).sort().join(',')!=='surface,workflow_action')throw Error('This workflow action cannot carry selected context.');
    const leaf=workflowActionInput(payload.workspace_context.workflow_action,{project,session:payload.session_id,work:payload.work_id});
    const coordinates=action.read?.request,identity=leaf.reference.identity;
    if(leaf.reference.kind==='research-workflow-start'){
      const native=action.action_context?.native,read=action.read;
      if(coordinates?.action!=='workflow-compose-start'||coordinates.work_id!==identity.work_id||coordinates.request_id!==identity.request_id||coordinates.recipients?.writer!==identity.writer_binding_id||coordinates.recipients?.reviewer!==identity.reviewer_binding_id||native?.operation!=='work_delivery'||native.payload?.action!=='workflow-start'||native.payload.work_id!==identity.work_id||native.payload.request_id!==identity.request_id||native.payload.recipients?.writer!==identity.writer_binding_id||native.payload.recipients?.reviewer!==identity.reviewer_binding_id||read.http?.method!=='GET')throw Error('The research Start and its exact reinspection have different identities.');
      const url=new URL(read.http.url,here());if(url.origin!==here().origin||url.pathname!=='/work/delivery'||url.searchParams.get('project')!==project||!equivalent(JSON.parse(url.searchParams.get('request')||'null'),coordinates))throw Error('The research Start read carrier changed its original request.');
    }else{
      if(action.read?.request?.facet!=='app-continue-compose'||coordinates.definition_id!==identity.definition_id||coordinates.version!==leaf.reference.version.definition_revision||coordinates.work_id!==identity.work_id||coordinates.step_id!==identity.step_id||coordinates.request_id!==identity.request_id||action.action_context?.native?.operation!=='dispatch_continue'||action.action_context.native.payload?.id!==identity.work_id||action.action_context.native.payload?.request_id!==identity.request_id)throw Error('The selected action and its owner read have different identities.');
    }
    if(coordinates.expected_action_basis!==leaf.expected_basis||!equivalent(action.action_context?.reference,leaf.reference)||action.action_context.expected_basis!==leaf.expected_basis)throw Error('The workflow context changed its inspected basis.');
    workflowActionSummary(action.action_context);
  }
  return clone(action);
}
export async function readWorkflowConversationAction(project,ownerRequest,request=workflowRequest,{allowInspectedBasis=false}={}){
  if(!['app-compose','app-launch-compose','app-continue-compose'].includes(ownerRequest?.facet))throw Error('This is not a workflow conversation request.');
  const result=await request(WORKFLOW_ENTRY+'?'+new URLSearchParams(Object.entries(ownerRequest).map(([key,value])=>[key,typeof value==='object'?JSON.stringify(value):String(value)])));
  const action=workflowConversationAction(result.action,project);
  const expected=allowInspectedBasis&&ownerRequest.facet==='app-continue-compose'&&!Object.hasOwn(ownerRequest,'expected_action_basis')?{...ownerRequest,expected_action_basis:action.payload.workspace_context?.workflow_action?.expected_basis}:ownerRequest;
  if(!equivalent(action.read?.request,expected))throw Error('The conversation action belongs to another workflow request.');
  return action;
}
export async function readResearchWorkflowAction(project,handle,request=workflowRequest,{allowInspectedBasis=false}={}){
  const url=new URL(handle?.http?.url||'',here()),expected=handle?.request;
  if(handle?.http?.method!=='GET'||url.origin!==here().origin||url.pathname!=='/work/delivery'||url.searchParams.get('project')!==project||expected?.action!=='workflow-compose-start'||!equivalent(JSON.parse(url.searchParams.get('request')||'null'),expected))throw Error('The research workflow has no exact owner-issued reinspection.');
  const result=await request(url.pathname+url.search),action=workflowConversationAction(result.action,project),actual=action.read.request;
  const basis=allowInspectedBasis&&!Object.hasOwn(expected,'expected_action_basis')?{...expected,expected_action_basis:actual.expected_action_basis}:expected;
  if(!equivalent(actual,basis))throw Error('The research action reply belongs to a different original request.');return action;
}
export function workflowReturnURL(raw){
  if(!raw)return null;const url=new URL(raw,here());
  return url.origin===here().origin&&url.pathname==='/project'&&url.searchParams.get('app')==='workflows'&&!url.searchParams.has('corpus')&&!url.searchParams.has('project')?url.pathname+url.search:null;
}
export function workflowConversationURL(action,back=null){
  workflowConversationAction(action,action?.project);const url=new URL(action.project_url||'',here());
  let requested;try{requested=JSON.parse(url.searchParams.get('workflow_action_read')||'null');}catch{throw Error('The conversation destination has no exact workflow request.');}
  if(url.origin!==here().origin||url.pathname!=='/project'||url.searchParams.get('workspace')!=='writing'||url.searchParams.get('corpus')!==action.project||!equivalent(requested,action.read?.request))throw Error('The conversation destination does not match its owner action.');
  if(back){const target=workflowReturnURL(back);if(!target)throw Error('The workflow return destination is invalid.');url.searchParams.set('app_return',target);}
  return url.pathname+url.search;
}
export async function composeWorkflowRequest(definition,fields,{request=workflowRequest}={}){
  const action=definition?.actions?.use_in_conversation,base=definition?.actions?.app_prepare?.native?.payload;
  if(!action?.available||!action.permitted||!action.read||!base)throw Error(action?.reason||'App preparation is unavailable for this saved workflow.');
  const allowed=action.allowed_inputs||definition.actions.app_prepare.allowed_inputs||action.required_inputs||definition.actions.app_prepare.required_inputs||[];
  if(Object.keys(fields).some(key=>!allowed.includes(key)))throw Error('Authored inputs cannot replace the saved workflow action.');
  const result=await request(workflowReadURL(action.read,fields));
  if(!equivalent(result.prepare_payload,{...base,...fields}))throw Error('The owner composed another workflow intent. Your original inputs are retained.');
  return workflowConversationAction(result.action,definition.scope?.namespace);
}
export async function composeFailedReviewRequest(action,request_id,{request=workflowRequest}={}){
  if(!action?.available||!action.permitted||action.native?.operation!=='dispatch_continue'||action.read?.request?.facet!=='app-continue-compose'||typeof request_id!=='string'||!request_id)throw Error(action?.reason||'Failed review continuation is unavailable.');
  const result=await request(workflowReadURL(action.read,{request_id}));
  if(!result.action?.permitted)throw Error(result.action?.reason||'Review continuation is no longer available. The original intent is retained.');
  if(!equivalent(result.continuation_payload,{...action.native.payload,request_id}))throw Error('The continuation offer changed. Your original request and guard are retained; inspect the current run before choosing another intent.');
  const resolved=workflowConversationAction(result.action,action.project);
  if(!equivalent(resolved.action_context.native,{operation:'dispatch_continue',payload:result.continuation_payload}))throw Error('The selected action details differ from the inspected continuation.');
  return resolved;
}
export function createWorkflowRunPort({request=workflowRequest,initial=null,now=()=>new Date().toISOString()}={}){
  const key=ref=>JSON.stringify(ordered([ref.scope_id,ref.reference,ref.kind,ref.work_id||null,ref.step_id||null]));
  const life=createSelectedLifetime({qualify:key}),reads=new Map();let event='initial';
  if(initial?.selection)life.select(clone(initial.selection));
  const snapshot=()=>clone({selection:life.selection,read:life.selection?reads.get(key(life.selection))||null:null,event,visit_depth:life.visitDepth});
  const notify=value=>{event=value;life.notify(snapshot());};
  function validate(value,ref){
    if(value?.profile!==appProfile||!equivalent(value.reference,ref.reference))throw Error('The app dispatch read belongs to another saved workflow version.');
    // A native research run view nests its Work. Accept only that exact nested identity; a missing or colliding top-level id refuses.
    const research=value.schema_version==='laplace.research-workflow-run/1';
    if(research&&ref.kind!=='list'&&(typeof value.work?.id!=='string'||value.work_id!==undefined&&value.work_id!==value.work.id))throw Error('The research run read has a missing or colliding Work identity.');
    if(ref.kind!=='list'&&((research?value.work.id:value.work_id)!==ref.work_id||value.work?.project!==ref.project))throw Error('The app dispatch read belongs to another Work or project.');
    if(ref.kind==='step'&&value.step_detail?.step_id!==ref.step_id)throw Error('The reply belongs to another prepared step.');
  }
  async function consumedDefinition(value,ref){
    const identity='definition:'+JSON.stringify(ordered([ref.scope_id,ref.reference]));
    const cached=reads.get(identity);if(cached)return await cached;
    if(!value.definition_read)throw Error('The run supplied no exact consumed definition read.');
    const pending=(async()=>{const definition=await request(workflowReadURL(value.definition_read));
      if(definition?.definition_id!==ref.definition_id||definition.scope_id!==ref.scope_id||!equivalent(definition.reference,ref.reference)||!definition.definition)
        throw Error('The consumed definition read belongs to another saved version or scope.');
      return clone(definition);})();
    reads.set(identity,pending);
    try{const definition=await pending;reads.set(identity,definition);return definition;}
    catch(error){if(reads.get(identity)===pending)reads.delete(identity);throw error;}
  }
  async function load(ref,{select=true}={}){
    life.live();const identity=key(ref);if(select)life.select(clone(ref));const token=life.issue(identity),previous=reads.get(identity);reads.set(identity,{...previous,io:'loading'});notify('loading');
    try{const value=await request(workflowReadURL(ref.read));if(life.disposed||life.superseded(identity,token))return null;validate(value,ref);
      const definition=ref.kind==='list'?null:await consumedDefinition(value,ref);
      if(life.disposed||life.superseded(identity,token))return null;
      life.accept(identity,token);reads.set(identity,{io:'ready',value:clone(value),definition:clone(definition),at:now()});notify('read');return value;}
    catch(error){if(!life.disposed&&!life.superseded(identity,token)){reads.set(identity,{...previous,io:'error',error:error.message});notify('error');}throw error;}
  }
  function open(definition,kind,handle,fields={}){
    if(!definition?.reference||!definition?.scope_id||!handle)throw Error('Inspect a saved workflow with its exact app read first.');
    return load({definition_id:definition.definition_id,scope_id:definition.scope_id,reference:clone(definition.reference),definition_read:clone(definition.read_handle||definition.read),list_read:clone(definition.app_runs_read),project:definition.scope?.namespace,kind,read:clone(handle),...clone(fields)});
  }
  function matches(definition){return !!life.selection&&definition?.definition_id===life.selection.definition_id&&definition.scope_id===life.selection.scope_id&&equivalent(definition.reference,life.selection.reference);}
  return {snapshot,subscribe:life.subscribe,open,matches,
    refresh:()=>life.selection?load(life.selection,{select:false}):Promise.resolve(null),
    restore:definition=>{if(!matches(definition))throw Error('The app run return belongs to another saved workflow or scope.');return load(life.selection,{select:false});},
    back:()=>{life.live();const ref=life.back();if(ref)notify('back');return snapshot();},
    capture:()=>clone({selection:life.selection}),destroy:()=>life.dispose()};
}
