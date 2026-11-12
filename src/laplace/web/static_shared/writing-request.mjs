// Thin writing response/request adapter. Moved verbatim from workspace-session;
// readers and metadata routes do not import the conversation/manuscript graph.
// Partial source events, refusal bodies, unknown POST delivery and no-retry order
// remain the existing contract. The conversation re-exports these same functions.
import {ownerRequest} from './owner-request.mjs';
import {buildCancelAcknowledged} from './derived-output.mjs';
import {requirePlanCompletion} from './plan-publication.mjs';
import {sourceEffectDisposition,requireSourceCompletion} from './source-effect.mjs';
export function writingOwnerResponse({ok,status,value},path,payload,{allowStateError=false}={}){
  if(payload){
    const expectedSelection=value.metadata_only===true?undefined:payload.expected_selection??payload.guards?.expected_selection;
    const effect=sourceEffectDisposition(value,{project:payload.project||payload.corpus,selectionIdentity:expectedSelection});
    if(effect&&value.metadata_only!==true&&typeof window!=='undefined')window.dispatchEvent(new CustomEvent('laplace-source-effect',{detail:effect.effect}));
    requirePlanCompletion(value);
    if(value.metadata_only!==true)requireSourceCompletion(value,{project:payload.project||payload.corpus,selectionIdentity:expectedSelection});
  }
  const cancelled=path==='/authoring/build'&&payload&&buildCancelAcknowledged(payload,value);
  if(!ok||(!cancelled&&(!allowStateError||payload)&&(value.error||value.ok===false))){const error=Error(value.error||value.reason||value.status||value.writer_result?.error||`Operation did not complete (${status})`);error.result=value;throw error;}return value;
}
export async function projectRequest(path,payload,{allowStateError=false,signal=null}={}){
  let carried;
  try{carried=await ownerRequest(path,payload,{signal,headers:payload?{'X-Laplace-Writing':'1'}:null});}
  catch(error){
    if(error.transport!=='connection')throw error;
    window.dispatchEvent(new CustomEvent('laplace-workspace-connection',{detail:{available:false}}));
    throw Object.assign(Error('The local engine is unavailable. Your draft is preserved; reconnect to continue.'),{transport:error.transport,effect:error.effect});
  }
  return writingOwnerResponse(carried,path,payload,{allowStateError});
}
