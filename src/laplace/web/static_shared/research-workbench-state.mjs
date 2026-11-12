// Local reading/draft lifetime for the native research workbench. Domain meaning,
// permissions, consumed bases and effect/recovery identities stay with owners.
import {createLifetime} from './selected-lifetime.mjs';
export const WORKBENCH_CAPTURE='laplace.research-workbench-drafts/1';
export const copy=value=>value===undefined?undefined:structuredClone(value);
const canonical=value=>Array.isArray(value)?value.map(canonical):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonical(value[key])])):value;
export const equal=(left,right)=>JSON.stringify(canonical(left))===JSON.stringify(canonical(right));
const object=value=>value&&typeof value==='object'&&!Array.isArray(value);
export function checkedReference(value){
  if(!object(value)||value.schema_version!=='laplace.reference/1'||!value.owner||typeof value.owner!=='string'||!value.kind||typeof value.kind!=='string'||!object(value.identity)||!Object.keys(value.identity).length||Object.values(value.identity).some(item=>typeof item!=='string'||!item)||Object.keys(value).some(key=>!['schema_version','owner','kind','identity','version','legacy'].includes(key))||['version','legacy'].some(key=>value[key]!==undefined&&!object(value[key])))throw Error('The selected object has no complete owner-qualified reference.');
  return copy(value);
}
// A browser map key only; never sent as an object identity or new ID space.
export function referenceKey(reference){const value=checkedReference(reference);return JSON.stringify(canonical({owner:value.owner,kind:value.kind,identity:value.identity}));}
export function checkedFacets(value,{reference=null,view=null}={}){
  if(value?.schema_version!=='laplace.object-facets/1'||!['workspace','object','dependents','handover'].includes(value.view)||view&&value.view!==view||!/^sha256:[a-f0-9]{64}$/.test(value.basis||'')||!object(value.scope)||!object(value.coverage))throw Error('The object owner returned an incompatible or unqualified reading.');
  if(value.subject!==null)checkedReference(value.subject);
  if(reference&&(value.subject===null||referenceKey(reference)!==referenceKey(value.subject)||reference.version&&!equal(reference.version,value.subject.version)))throw Error('The returned reading belongs to another object or requested version. The previous reading is retained.');
  return value;
}
export function issuedHTTP(handle,{method='GET',paths=null,base=globalThis.location?.href||'http://local/'}={}){
  const http=handle?.http;let raw=http?.url;
  if(!raw&&http?.route&&object(http.query)){
    if(Object.values(http.query).some(v=>typeof v!=='string'))throw Error('The owner query is not a complete issued carrier.');
    raw=http.route+'?'+new URLSearchParams(http.query);
  }
  if(typeof raw!=='string'||!raw)throw Error('The owner supplied no callable read or action.');
  const here=new URL(base),url=new URL(raw,here);
  if(http.method!==method||url.origin!==here.origin||url.username||url.password||url.hash||paths&&!paths.includes(url.pathname))throw Error('This owner handle does not belong to the selected local action.');
  return url.pathname+url.search;
}
export const WORKBENCH_ENTRY={http:{method:'GET',url:'/work/discovery?facet=workspace'}};
export function workspaceFilter({project_lens=null,family=null}={}){
  const query=new URLSearchParams({facet:'workspace'});
  if(project_lens)query.set('project_lens',project_lens);
  if(family&&family!=='all'){
    if(!['work','concept','research-record','reference','artifact','workflow-definition'].includes(family))throw Error('Choose a supported object family.');
    query.set('family',family);
  }
  return {http:{method:'GET',url:'/work/discovery?'+query}};
}
// Pending Stop requests reuse this workbench recovery storage and its verified
// readback (session store first, local backup second). One qualified record per
// project and Work holds the exact original body, its owner-issued request_read
// and the attempt, written before the request is sent. A record written by an
// earlier page reads back as UNKNOWN. Nothing here sends, replays or settles.
export const STOP_RECOVERY='laplace.research-workbench-stop/1';
const PAGE='page:'+Date.now().toString(36)+':'+Math.random().toString(36).slice(2);
const stopListeners=new Set();
export function workflowStopRecovery({storage=globalThis.sessionStorage,backup=globalThis.localStorage,prefix='laplace:research-workbench:stop:',page=PAGE}={}){
  const stores=[storage,backup].filter(store=>store&&typeof store.getItem==='function'&&typeof store.setItem==='function');
  const name=(project,work_id)=>prefix+JSON.stringify([project,work_id]);
  function read(project,work_id){
    if(typeof project!=='string'||!project||typeof work_id!=='string'||!work_id)return {record:null,held:true,error:'This run has no qualified project and Work, so Stop stays unavailable.'};
    const rows=[];
    for(const store of stores)try{const raw=store.getItem(name(project,work_id));if(raw)rows.push(JSON.parse(raw));}catch(error){return {record:null,held:true,error:'The retained Stop request could not be read ('+error.message+'). It is left unchanged and Stop stays held.'};}
    if(rows.some(row=>!object(row)||row.schema!==STOP_RECOVERY||row.project!==project||row.work_id!==work_id||typeof row.request_id!=='string'||!Number.isSafeInteger(row.revision)||!Number.isSafeInteger(row.attempt)))return {record:null,held:true,error:'A retained Stop request has an unknown format. It is left unchanged and Stop stays held.'};
    rows.sort((a,b)=>b.revision-a.revision);
    if(rows.length>1&&rows[0].revision===rows[1].revision&&!equal(rows[0],rows[1]))return {record:null,held:true,error:'Two retained copies of this Stop request disagree. Both are left unchanged and Stop stays held.'};
    if(!rows.length)return {record:null,held:false,error:''};
    const record=copy(rows[0]);if(record.page!==page&&record.phase==='SENT')record.observation='UNKNOWN';
    return {record,held:false,error:''};
  }
  function write(record){
    const key=name(record.project,record.work_id),wire=JSON.stringify(record);let ok=false,error='No browser recovery storage is available.';
    for(const store of stores)try{store.setItem(key,wire);if(store.getItem(key)!==wire)throw Error('Stop recovery did not read back.');ok=true;}catch(problem){error=problem.message;}
    if(!ok)return {ok:false,record:null,error};
    for(const listener of [...stopListeners])try{listener(record.project,record.work_id);}catch{}
    return {ok:true,record:copy(record),error:''};
  }
  function begin({project,work_id,request_id,original_request,http_url,request_read=null}){
    const prior=read(project,work_id);if(prior.held)return {ok:false,record:null,error:prior.error};
    const was=prior.record,same=was?.request_id===request_id,replaced=[...(was?.replaced||[])];
    if(was&&!same)replaced.unshift({request_id:was.request_id,attempt:was.attempt,phase:was.phase,outcome:was.outcome,checked:was.checked||null,sent_at:was.sent_at});
    return write({schema:STOP_RECOVERY,project,work_id,request_id,original_request:copy(original_request),http_url,request_read:copy(request_read),attempt:same?was.attempt+1:1,revision:(was?.revision||0)+1,page,phase:'SENT',outcome:'SENT_AWAITING_REPLY',observation:'SENDING',checked:null,sent_at:new Date().toISOString(),replaced:replaced.slice(0,8)});
  }
  // A late reply or check for an earlier request or attempt never overwrites a newer one.
  function update({project,work_id,request_id,attempt},fields){
    const prior=read(project,work_id),was=prior.record;if(prior.held||!was)return {ok:false,record:null,error:prior.error||'No retained Stop request.'};
    if(was.request_id===request_id&&was.attempt===attempt)return write({...was,...copy(fields),revision:was.revision+1});
    const index=(was.replaced||[]).findIndex(row=>row.request_id===request_id&&row.attempt===attempt);if(index<0)return {ok:false,record:null,error:'A newer Stop request replaced this attempt.'};
    const replaced=copy(was.replaced);replaced[index]={...replaced[index],...copy(fields)};return {...write({...was,replaced,revision:was.revision+1}),superseded:true};
  }
  return {read,begin,settle:(expect,fields)=>update(expect,fields),check:(expect,checked)=>update(expect,{checked:{...copy(checked),attempt:expect.attempt}}),
    subscribe(listener){stopListeners.add(listener);return()=>stopListeners.delete(listener);}};
}
export function createWorkbenchState({request,initial=null,storage=globalThis.sessionStorage,backup=globalThis.localStorage,key=null,initialWorkspace=null,now=()=>new Date().toISOString()}={}){
  if(typeof request!=='function')throw Error('The workbench needs the existing owner transport.');
  const life=createLifetime(),listeners=new Set(),drafts=new Map(),visits=[];let workspace=initialWorkspace?{value:copy(checkedFacets(initialWorkspace,{view:'workspace'})),handle:copy(WORKBENCH_ENTRY),at:now()}:null,selected=null,tab='overview',listTicket=0,readTicket=0,recoveryError='',storageError='';
  let saved=initial;const indexes=[];
  for(const store of [storage,backup]){if(!key)break;try{const raw=store?.getItem(key);if(raw)indexes.push(JSON.parse(raw));}catch(error){recoveryError='The retained workbench recovery could not be read: '+error.message;}}
  if(saved)indexes.unshift(saved);saved=indexes[0];
  if(saved){
    if(indexes.some(row=>row.schema!==WORKBENCH_CAPTURE||!Array.isArray(row.draft_keys)))recoveryError='The saved workbench format is unknown; its original storage is left unchanged.';
    else{tab=saved.tab||tab;for(const draftKey of new Set(indexes.flatMap(row=>row.draft_keys))){const candidates=[];for(const store of [storage,backup])try{const raw=store?.getItem(key+':draft:'+draftKey);if(raw)candidates.push(JSON.parse(raw));}catch(error){recoveryError='A retained workbench draft is unreadable: '+error.message;}
      if(!candidates.length||candidates.some(value=>!object(value))){recoveryError='A retained draft is unavailable; its recovery index is kept.';continue;}
      candidates.sort((a,b)=>(b.draft_revision||0)-(a.draft_revision||0));const value=candidates[0];if(candidates.some(other=>(other.draft_revision||0)===(value.draft_revision||0)&&!equal(value,other))){recoveryError='Two retained copies of this draft disagree at the same local revision. Both copies are left unchanged.';continue;}
      drafts.set(draftKey,copy({...value,...(value.pending?{pending:{...value.pending,observation:'UNKNOWN'}}:{})}));}}
  }
  const scopeId=initialWorkspace?.scope_id||null;
  const checkScope=value=>{if(scopeId&&value.scope_id!==scopeId)throw Error('The owner workspace changed; original drafts and pending requests are retained without replay.');return value;};
  const current=()=>!life.disposed;
  const snapshot=()=>({workspace,selected,tab,canBack:visits.length>0,recoveryError,storageError});
  function notify(event){for(const listener of listeners)listener(snapshot(),event);}
  function persist(draftKey=null){
    if(recoveryError)return false;if(draftKey!==null&&!drafts.has(draftKey))throw Error('No authored draft exists under this recovery key.');if(!key){storageError='The owner has not supplied a workspace recovery identity. Keep drafts local; no action is sent.';return false;}
    // Typing commits only this authored draft. Do not capture/stringify every
    // other form, owner payload or reading merely to keep one field durable.
    const indexWire=JSON.stringify({...copy(saved||{}),schema:WORKBENCH_CAPTURE,tab,draft_keys:[...drafts.keys()]}),wire=draftKey===null?null:JSON.stringify(drafts.get(draftKey));let ok=false;
    for(const store of [storage,backup])try{if(wire!==null){store?.setItem(key+':draft:'+draftKey,wire);if(store?.getItem(key+':draft:'+draftKey)!==wire)throw Error('Draft recovery did not read back.');}if(store?.getItem(key)!==indexWire)store?.setItem(key,indexWire);if(store?.getItem(key)===indexWire)ok=true;}catch(error){storageError=error.message;}
    if(ok)storageError='';else storageError='Keep this page open: draft recovery could not be saved. '+storageError;return ok;
  }
  async function list(handle=WORKBENCH_ENTRY,{append=false}={}){
    const ticket=++listTicket;notify('listing');let raw;try{raw=await request(issuedHTTP(handle,{paths:['/work/discovery']}));}catch(error){if(!current()||ticket!==listTicket)return null;throw error;}
    if(!current()||ticket!==listTicket)return null;const value=checkScope(checkedFacets(raw,{view:'workspace'}));
    if(append&&workspace&&!equal(workspace.value.project_lens,value.project_lens))throw Error('The list filter changed before continuation.');
    const items=append?[...(workspace?.value.items||[]),...(value.items||[])]:value.items;
    workspace={value:copy({...value,items}),handle:copy(handle),at:now()};notify('list');return value;
  }
  async function read(handle,reference,{replace=false,view='object',record=true}={}){
    reference=checkedReference(reference);const ticket=++readTicket;life.advance();const lease=life.lease();notify('reading');
    let raw;try{raw=await request(issuedHTTP(handle,{paths:['/work/discovery']}));}catch(error){if(!lease()||ticket!==readTicket)return null;throw error;}
    if(!lease()||ticket!==readTicket)return null;const value=checkScope(checkedFacets(raw,{reference,view}));
    if(selected&&!replace&&record){visits.push({...selected,tab});while(visits.length>12)visits.shift();}
    if(!replace)tab='overview';selected={tab,value:copy(value),handle:copy(handle),at:now(),retained:false,position:null};notify('read');return value;
  }
  function back(){if(!visits.length)return false;life.advance();readTicket++;selected={...visits.pop(),retained:true};tab=selected.tab||'overview';notify('back');return true;}
  return {snapshot,get disposed(){return life.disposed;},get recoveryError(){return recoveryError;},get storageError(){return storageError;},
    lease:()=>life.lease(),list,read,back,showWorkspace(){life.advance();readTicket++;if(selected){visits.push({...selected,tab});while(visits.length>12)visits.shift();}selected=null;tab='overview';notify('back');},reinspect:()=>selected?read(selected.handle,selected.value.subject,{replace:true,view:selected.value.view}):list(),
    setTab(value){if(tab===value)return;tab=value;if(selected)selected.tab=value;persist();notify('tab');},
    restore(entry,restoredTab='overview'){life.advance();readTicket++;selected=entry?{...entry,retained:true}:null;tab=restoredTab;notify('back');return selected;},
    presentation(){const held=drafts.get('@presentation');if(!held)return {};if(held.schema!=='laplace.research-presentation/1'||!object(held.value))throw Error('The saved view format is retained unchanged; presentation is read-only.');return copy(held.value);},
    setPresentation(fields){const held=drafts.get('@presentation');if(held&&(held.schema!=='laplace.research-presentation/1'||!object(held.value)))throw Error('The saved view format is retained unchanged.');const value={...copy(held?.value||{}),...copy(fields)};drafts.set('@presentation',{...copy(held||{}),schema:'laplace.research-presentation/1',value,dirty:false,draft_revision:(held?.draft_revision||0)+1});persist('@presentation');return copy(value);},
    rememberPosition(value){if(selected)selected.position=copy(value);},
    draft(draftKey){return copy(drafts.get(draftKey)||null);},
    updateDraft(draftKey,fields){life.live('This workbench was closed; its original drafts remain retained.');if(recoveryError)throw Error(recoveryError);const previous=drafts.get(draftKey)||{},value={...previous,...copy(fields),draft_revision:(previous.draft_revision||0)+1};drafts.set(draftKey,value);persist(draftKey);notify('draft');return copy(value);},
    persist,hasDraft:()=>!!recoveryError||[...drafts.values()].some(row=>row.pending||row.dirty),
    subscribe(listener){listeners.add(listener);return()=>listeners.delete(listener);},
    destroy(){life.dispose();listTicket++;readTicket++;listeners.clear();visits.splice(0);workspace=selected=null;}}
}
