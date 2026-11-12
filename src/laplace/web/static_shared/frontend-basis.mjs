// FRONTEND BASIS (P2 service spine, WORK-frontend-p2-service-spine-20261021). Purpose: say which frontend this open
// view was issued from, notice when the writing process now serves another, and refresh only when the person asks
// and only after every open draft, attempt and visit was captured by its own owner.
// Basis: the served project page carries <meta name="laplace-frontend-basis"> = the frozen asset snapshot's digest
// (shared_ui.issued_page); it is read ONCE when this module's controller is created. It is the issued/open-view basis,
// not an attestation of every module the page imported. A page served without it (an older page, or a process
// without a captured snapshot) is UNKNOWN, never diagnosed stale. The served basis is /authoring/health
// frontend_bundle.sha256, read on check().
// States: unknown-issued | unknown-served (health names no bundle) | unavailable (health read failed) | current |
// different-served. Only different-served offers the refresh affordance; a different digest is not an order (it may be
// a rollback), so nothing calls it newer. Nothing ever reloads by itself.
// Refresh: refresh(adapters) asks each adapter {name, capture() -> {ok:true, carry?} | {ok:false, missing}} in order.
// Any missing precondition refuses: nothing is stored, the page stays as it is and the reasons are returned. When all
// are captured, one record (laplace.frontend-refresh-carry/1: a unique id, project, from and to bases, each adapter's
// carry) is written to sessionStorage for this tab and read back byte-exact before the explicit reload.
// Carry admission (P2S-R1): the carry is pending recovery intent, not a one-shot read. inspectRefreshCarry() reads it
// WITHOUT removing it and compares its intended basis with this page's observed issued basis: matched, different (the
// page came from another snapshot, e.g. the one before the refresh) or unknown (no issued basis). The shell restores
// it only through its owners (the visit, the Work view memory) and then acknowledgeRefreshCarry() removes exactly that
// record: if the slot now holds any other bytes (a newer capture) it is left alone. Until then the record survives
// entry failure, Retry and owner restore failure. Restored attempts follow their owner's rule (a pending attempt is
// restored unresolved; nothing is resent). Owners keep their own storage (the compose draft, editor and walk drafts).
export const FRONTEND_BASIS_META='laplace-frontend-basis';
export const FRONTEND_REFRESH_CARRY='laplace.frontend-refresh-carry/1';
const carryKey=project=>'laplace:frontend-refresh:'+project;
const digest=value=>typeof value==='string'&&/^[0-9a-f]{64}$/.test(value)?value:null;
export function issuedFrontendBasis(doc=globalThis.document){
  return digest(doc?.querySelector?.('meta[name="'+FRONTEND_BASIS_META+'"]')?.getAttribute?.('content'));
}
export function createFrontendBasis({project,request,doc=globalThis.document,storage=globalThis.sessionStorage,reload=()=>globalThis.location.reload(),now=()=>new Date().toISOString()}){
  const issued=issuedFrontendBasis(doc);
  let served=null,checked=null,error=null;
  const state=()=>({issued,served,checked,error,
    status:!issued?'unknown-issued':error?'unavailable':!served?'unknown-served':served===issued?'current':'different-served'});
  async function check(){
    try{const health=await request('/authoring/health');served=digest(health?.frontend_bundle?.sha256);error=null;}
    catch(failure){error=failure.message;}
    checked=now();return state();
  }
  async function refresh(adapters=[]){
    const carried={},missing=[];
    for(const adapter of adapters){
      let result;try{result=await adapter.capture();}catch(failure){result={ok:false,missing:adapter.name+': '+failure.message};}
      if(!result?.ok)missing.push(result?.missing||adapter.name+': no reload-safe capture is available');
      else if(result.carry!==undefined)carried[adapter.name]=result.carry;
    }
    if(missing.length)return {refreshed:false,missing};
    const id=globalThis.crypto?.randomUUID?.()||now()+':'+Math.random().toString(36).slice(2);
    const text=JSON.stringify({schema:FRONTEND_REFRESH_CARRY,id,project,from:issued,to:served,at:now(),carried});
    try{storage.setItem(carryKey(project),text);if(storage.getItem(carryKey(project))!==text)throw Error('it did not read back');}
    catch(failure){try{storage.removeItem(carryKey(project));}catch{}return {refreshed:false,missing:['This tab could not keep the captured drafts for a refresh ('+failure.message+').']};}
    reload();return {refreshed:true,carried:Object.keys(carried)};
  }
  return {issued,state,check,refresh};
}
// the stored carry for this project, unchanged in storage; status says how this page's issued basis relates to its target
export function inspectRefreshCarry(project,{issued=issuedFrontendBasis(),storage=globalThis.sessionStorage}={}){
  let text=null;try{text=storage?.getItem(carryKey(project))??null;}catch{return null;}
  if(!text)return null;
  let record=null;try{record=JSON.parse(text);}catch{/* kept as unreadable */}
  if(record?.schema!==FRONTEND_REFRESH_CARRY||record.project!==project||!record.carried||typeof record.carried!=='object')return {text,record:null,issued,status:'unreadable'};
  return {text,record,issued,status:!issued?'unknown':issued===record.to?'matched':'different'};
}
// remove exactly the inspected record once its owners restored it; any other bytes in the slot are a newer capture and stay
export function acknowledgeRefreshCarry(project,carry,storage=globalThis.sessionStorage){
  try{if(!carry?.text||storage.getItem(carryKey(project))!==carry.text)return false;storage.removeItem(carryKey(project));return true;}catch{return false;}
}
