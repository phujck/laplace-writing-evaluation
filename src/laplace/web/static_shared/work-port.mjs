// WORK PORT (P1, WORK-frontend-p1-owner-port-20261021). Purpose: one renderer-neutral service for a selected Work's
// read, title/purpose draft, guarded edit attempt, owner result and lifetime, so that any renderer (the current Work
// card through its adapter in workspace-work.mjs, the plain-DOM outline in work-port-outline.mjs, a later renderer)
// paints the same immutable snapshot and issues the same intents. Ownership: project_work owns every fact and
// decision (GET /work/state view=detail, its allowed_actions.task guard, POST /work/task and its receipt or
// CHANGED_INPUT refusal); this module keeps only what a client must keep, each item under its QUALIFIED identity
// (project::id): the owner reads it received, the typed draft with the ORIGINAL issued guard, each attempt with its
// unchanged owner result, the comparison it displayed, the selection and visits. It decides no permission or
// currentness; the owner refuses a stale guard.
// Public contract: createWorkPort({request, project, initial, observe, now}) -> {snapshot(), dispatch(intent),
// subscribe(listener) -> unsubscribe, listenerCount(), capture(), draftFor(id, project), attemptFor(id, project),
// hasDirtyDraft(), hasUnresolved()}.
// Snapshot (laplace.work-port/2): immutable JSON. read {io: reading|ready|error (the transport state of the latest
// read of this object), at, error, token, owner: {the owner's fields, including its Work standing status}}; draft
// {project, id, fields, basis, stale}; attempt; comparison {current fields and basis as displayed, token}; selection;
// generation (selection generation); visit depth. Never a DOM node, framework object or inferred default.
// Delivery: every owner read of an object (select/inspect/reinspect/compare/postimage, or an observe intent carrying a
// read another owner client made) takes a per-object token when issued; a delivery is accepted only if no newer
// delivery of the same object was accepted already, so a superseded read can never replace a newer one. This orders
// deliveries by issue, not by the owner's source time, which a client cannot prove. A failed read marks io=error and
// keeps the last owner values. An accepted delivery whose action basis moved invalidates that object's comparison.
// Intents: select, observe, inspect/reinspect, edit {fields: title/goal only, target: {project,id}} (a target other
// than the selection is refused: a field typed for one Work never edits another), cancel-local, submit, compare,
// adopt-current {basis: the displayed comparison basis} (refused unless it is exactly the displayed one and still the
// latest delivered), return, dispose.
// Attempts: local ids A1, A2... (client delivery identity, not a server idempotency key; continued across capture).
// recorded = owner receipt, then the postimage read through the owner's returned handle; refused = the owner's
// refusal unchanged, draft and original guard kept; uncertain = no response, draft kept, nothing ever resent.
// Capture (laplace.work-port-capture/2): lossless and qualified - drafts and attempts as lists of {project, id, ...}
// with their original bases, and the next attempt number. Restoring a pending attempt yields an UNRESOLVED
// uncertain attempt (nothing is resent, nothing is called complete). The legacy envelope {drafts:{id:{fields,basis}}}
// is still accepted for the port's own project.
// Lifetime: the selection, its visits and generation, per-object delivery tokens, listeners and disposal are the
// shared selected lifetime (selected-lifetime.mjs); this module keeps the Work fields, guards, attempts and comparisons.
import {createSelectedLifetime} from './selected-lifetime.mjs';
export const WORK_PORT_SCHEMA='laplace.work-port/2';
export const WORK_PORT_CAPTURE='laplace.work-port-capture/2';
const EDITABLE=['title','goal'];
const clone=value=>value==null?value:JSON.parse(JSON.stringify(value));
const freeze=value=>{if(value&&typeof value==='object'){Object.freeze(value);for(const item of Object.values(value))freeze(item);}return value;};
const qualified=(project,id)=>project+'::'+id;
const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
const detailURL=(project,id)=>'/work/state?'+new URLSearchParams({project,view:'detail',id});
const postURL=action=>{const url=action?.http?.url;if(action?.http?.method!=='POST'||!url)throw Error('The owner exposed no POST route for this action.');return url;};

// the owner facts a renderer may paint, selected from one detail read; absence is explicit, never a default
function ownerFacts(value){
  const task=value.task||{},action=value.allowed_actions?.task||null,unavailable=[];
  if(typeof task.title!=='string')unavailable.push('title: not returned by the owner');
  if(typeof task.goal!=='string')unavailable.push('goal: not returned by the owner');
  if(!action)unavailable.push('edit: the owner exposed no task action for this Work');
  else if(!action.permitted)unavailable.push('edit: '+(action.reason||'not permitted by the owner'));
  return {reference:{project:value.project,id:task.id,qualified_id:task.qualified_id||qualified(value.project,task.id)},
    title:task.title??null,goal:task.goal??null,status:task.status??null,recorded_status:task.recorded_status??null,
    standing:task.standing??null,activity:task.activity?{state:task.activity.state??null,qualification:task.activity.qualification??null}:null,
    work_revision:task.work_revision??null,read_cut:value.read_cut??null,read_handle:task.read_handle||null,observe_basis:value.observe_basis??null,
    action:action?{name:'task',permitted:!!action.permitted,payload:clone(action.payload),http:clone(action.http),requires:action.requires??null}:null,
    unavailable};
}

export function createWorkPort({request,project=null,initial={},observe=null,now=()=>new Date().toISOString()}={}){
  if(typeof request!=='function')throw Error('A Work port needs the owner request function.');
  let attempts=0,observer=null;
  const region=createSelectedLifetime(),objects=new Map(),drafts=new Map(),results=new Map(),comparisons=new Map();
  region.own(()=>{observer?.stop();observer=null;});
  const object=(p,id)=>{const k=qualified(p,id);if(!objects.has(k))objects.set(k,{project:p,id,key:k,read:null});return objects.get(k);};
  const numbered=id=>Number(String(id||'').replace(/^A/,''))||0;
  // restore: the lossless qualified capture, or the legacy {drafts:{id:{fields,basis}}} envelope for this project
  if(initial?.schema===WORK_PORT_CAPTURE){
    for(const held of initial.drafts||[])drafts.set(qualified(held.project,held.id),{project:held.project,id:held.id,fields:clone(held.fields),basis:clone(held.basis)});
    for(const attempt of initial.attempts||[])results.set(qualified(attempt.project,attempt.work_id),attempt.status==='pending'
      ?{...clone(attempt),status:'uncertain',restored:true,effect:'unresolved: this attempt was still waiting for its owner when its view was captured; nothing is resent. Reinspect to see the owner\'s current fields.'}
      :clone(attempt));
    attempts=Math.max(Number(initial.next_attempt)||0,...(initial.attempts||[]).map(attempt=>numbered(attempt.id)));
  }else{
    for(const [id,held]of Object.entries(initial?.drafts||{}))if(held?.fields&&held.basis){const p=held.project||project;drafts.set(qualified(p,id),{project:p,id,fields:clone(held.fields),basis:clone(held.basis)});}
  }
  const selectedKey=()=>region.selection?qualified(region.selection.project,region.selection.id):null;
  function snapshot(){
    const k=selectedKey(),obj=k?objects.get(k):null,draft=k?drafts.get(k):null,current=obj?.read?.owner?.action?.payload;
    return freeze(clone({schema:WORK_PORT_SCHEMA,generation:region.generation,disposed:region.disposed,selection:region.selection,visit:{depth:region.visitDepth},
      read:obj?.read?{io:obj.read.io,at:obj.read.at,error:obj.read.error||null,token:region.accepted(k),owner:obj.read.owner||null}:null,
      draft:draft?{project:draft.project,id:draft.id,fields:draft.fields,basis:draft.basis,stale:!!current&&!same(current,draft.basis.payload)}:null,
      attempt:k?results.get(k)||null:null,comparison:k?comparisons.get(k)||null:null}));
  }
  function notify(){if(!region.disposed)region.notify(snapshot());}
  function live(){region.live('This Work port was disposed.');}
  // THE one admission of an owner delivery for an object: accepted only if nothing newer was accepted already
  function deliver(obj,token,value){
    if(!region.admissible(obj.key,token))return false;
    if(value?.view!=='detail'||value.project!==obj.project||value.task?.id!==obj.id)throw Error('The Work owner did not return this Work.');
    if(project&&value.project!==project)throw Error('The Work owner returned another project.');
    const k=qualified(obj.project,obj.id),owner=ownerFacts(value);
    region.accept(obj.key,token);obj.read={io:'ready',at:now(),owner};
    const compared=comparisons.get(k);
    if(compared&&!same(compared.current.basis,owner.action?.payload))comparisons.delete(k);   // its displayed basis moved
    const attempt=results.get(k);
    if(attempt&&attempt.status==='uncertain')results.set(k,{...attempt,observed:{at:now(),fields:{title:owner.title,goal:owner.goal},work_revision:owner.work_revision,
      matches_attempt:EDITABLE.every(name=>!(name in attempt.fields)||attempt.fields[name]===owner[name])}});
    return true;
  }
  async function read(p,id,handle){
    const obj=object(p,id),token=region.issue(obj.key),url=handle?.http?.url||obj.read?.owner?.read_handle?.http?.url||detailURL(p,id);
    obj.read={...(obj.read||{}),io:'reading'};notify();
    let value;
    try{value=await request(url);}
    catch(error){
      if(region.superseded(obj.key,token))return null;          // superseded: a newer read owns the outcome
      obj.read={...(obj.read||{}),io:'error',error:error.message,at:now()};notify();throw error;
    }
    const accepted=deliver(obj,token,value);if(accepted)notify();return accepted?value:null;
  }
  const select=(p,id)=>region.select({project:p,id});
  async function submit(){
    const k=selectedKey(),draft=drafts.get(k);
    if(!draft)throw Error('There is no authored title or purpose to submit.');
    if(results.get(k)?.status==='pending')throw Error('An attempt for this Work is still waiting for its owner.');
    const fields=clone(draft.fields),basis=clone(draft.basis),id='A'+(++attempts),{project:p,id:work}=draft;
    const submitted=draft;results.set(k,{id,project:p,work_id:work,status:'pending',at:now(),fields,basis});comparisons.delete(k);notify();
    let result;
    try{result=await request(postURL(basis),{project:p,...basis.payload,...fields});}
    catch(error){
      if(region.disposed)return null;
      const owner=error.result??error.details??null;
      results.set(k,owner?{id,project:p,work_id:work,status:'refused',at:now(),fields,basis,refusal:clone(owner),error:error.message,
          effect:'none recorded: the owner refused this attempt',next_reads:clone(owner.next_reads||[])}
        :{id,project:p,work_id:work,status:'uncertain',at:now(),fields,basis,error:error.message,
          effect:'unknown: no owner response; the draft is kept and nothing is resent. Reinspect to see the owner\'s current fields.'});
      notify();return results.get(k);
    }
    if(region.disposed)return null;
    if(drafts.get(k)===submitted)drafts.delete(k);       // a newer draft typed meanwhile stays
    results.set(k,{id,project:p,work_id:work,status:'recorded',at:now(),fields,basis,result:clone(result),
      effect:'recorded by the owner: '+(result?.owned_changes?'receipt returned':'no receipt in the response')});notify();
    // only the observed postimage, read through the owner's returned handle, makes the presentation current
    try{const value=await read(p,work,result?.read_handle);
      if(value){const owner=ownerFacts(value);results.set(k,{...results.get(k),postimage:{at:now(),fields:{title:owner.title,goal:owner.goal},work_revision:owner.work_revision}});}}
    catch(error){results.set(k,{...results.get(k),postimage_error:error.message});}
    notify();return results.get(k);
  }
  async function dispatch(intent){
    live();const type=intent?.type,k=selectedKey(),selection=region.selection;
    if(type==='select'){select(intent.project||project,intent.id);notify();await read(region.selection.project,region.selection.id,intent.read);return snapshot();}
    if(type==='observe'){const value=intent.value;if(value?.view!=='detail'||!value.task?.id)throw Error('observe takes an owner detail read.');
      if(!selection||selection.project!==value.project||selection.id!==value.task.id)select(value.project,value.task.id);
      const obj=object(value.project,value.task.id);if(deliver(obj,region.issue(obj.key),value))notify();return snapshot();}
    if(type==='inspect'||type==='reinspect'){if(!selection)throw Error('Select Work first.');await read(selection.project,selection.id);return snapshot();}
    if(type==='edit'){
      if(!selection)throw Error('Select Work first.');
      if(intent.target&&qualified(intent.target.project,intent.target.id)!==k)throw Error('This field was written for another Work; it does not edit the selected one.');
      const fields=intent.fields||{},names=Object.keys(fields);
      if(!names.length||names.some(name=>!EDITABLE.includes(name)))throw Error('Only the title and purpose (goal) are edited here.');
      if(names.some(name=>typeof fields[name]!=='string'))throw Error('Title and purpose are text.');
      const owner=objects.get(k)?.read?.owner,held=drafts.get(k);
      if(!held&&!owner?.action?.permitted)throw Error((owner?.unavailable||[]).find(item=>item.startsWith('edit'))||'Read the Work before editing it.');
      // the ORIGINAL issued guard is taken once, when drafting starts; it never silently advances
      drafts.set(k,{project:selection.project,id:selection.id,fields:{...(held?.fields||{}),...fields},basis:held?.basis||{payload:owner.action.payload,http:owner.action.http,operation:'task'}});
      notify();return snapshot();}
    if(type==='cancel-local'){drafts.delete(k);comparisons.delete(k);notify();return snapshot();}
    if(type==='submit'){await submit();return snapshot();}
    if(type==='compare'){
      const draft=drafts.get(k);if(!draft)throw Error('There is no draft to compare.');
      await read(selection.project,selection.id);
      const obj=objects.get(k),owner=obj.read?.owner;
      if(!owner)throw Error('The current Work could not be read.');
      comparisons.set(k,{at:now(),token:region.accepted(k),draft:{fields:draft.fields,basis:draft.basis.payload},
        current:{fields:{title:owner.title,goal:owner.goal},basis:owner.action?.payload||null,work_revision:owner.work_revision},
        same_basis:same(owner.action?.payload,draft.basis.payload)});
      notify();return snapshot();}
    if(type==='adopt-current'){
      const draft=drafts.get(k),compared=comparisons.get(k),owner=objects.get(k)?.read?.owner;
      if(!draft||!compared)throw Error('Compare the draft with the current Work before adopting its basis.');
      if(!same(intent.basis,compared.current.basis))throw Error('Adopt exactly the basis that the comparison displayed.');
      if(!owner?.action?.permitted||!same(owner.action.payload,compared.current.basis)){comparisons.delete(k);notify();throw Error('The Work changed after the comparison; compare again.');}
      drafts.set(k,{...draft,basis:{payload:owner.action.payload,http:owner.action.http,operation:'task'}});comparisons.delete(k);notify();return snapshot();}
    if(type==='return'){if(region.back())notify();return snapshot();}
    if(type==='dispose'){region.dispose();return null;}
    throw Error('Unknown Work port intent: '+type);
  }
  if(observe)observer=observe({selected:()=>region.selection,isCurrent:()=>!region.disposed,basis:()=>objects.get(selectedKey())?.read?.owner?.observe_basis||null,
    onChange:async()=>{const selection=region.selection;if(selection)await read(selection.project,selection.id);}});
  const at=(id,p)=>qualified(p||region.selection?.project||project,id);
  return {
    snapshot,dispatch,
    subscribe(listener){live();return region.subscribe(listener);},
    listenerCount:()=>region.listenerCount(),
    draftFor:(id,p)=>{const held=drafts.get(at(id,p));return held?freeze(clone({project:held.project,id:held.id,fields:held.fields,basis:held.basis})):null;},
    attemptFor:(id,p)=>freeze(clone(results.get(at(id,p))||null)),
    hasDirtyDraft:()=>drafts.size>0,
    hasUnresolved:()=>drafts.size>0||[...results.values()].some(attempt=>attempt.status==='pending'||attempt.status==='uncertain'),
    capture:()=>clone({schema:WORK_PORT_CAPTURE,next_attempt:attempts,
      drafts:[...drafts.values()].map(held=>({project:held.project,id:held.id,fields:held.fields,basis:held.basis})),
      attempts:[...results.values()]}),
  };
}
