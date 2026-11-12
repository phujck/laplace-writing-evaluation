// Selected review-setup draft and exact step custody; no owner truth, I/O or automatic retry.
import {providerModelOptions,providerEffortOptions} from './provider-options.mjs';
import {feedbackWireDigest,sameFeedbackValue} from './feedback-route-port.mjs';
const copy=value=>JSON.parse(JSON.stringify(value));
export const sameSetupValue=sameFeedbackValue;
export function ordinarySetupQuestion(row){return row?.scope!=='closure'&&!row?.closure_work_id&&!row?.source_contract;}
export async function retainSetupStep(kind,payload,action,{project,workId}){
 if(!['questions','bind','renew'].includes(kind))throw Error('Unknown review setup step.');
 if(payload?.project!==project||(kind==='questions'?payload.id:payload.work_id)!==workId)throw Error('The setup step belongs to another Work.');
 const wire=JSON.stringify(payload);return {kind,project,workId,wire,wire_sha256:await feedbackWireDigest(wire),action:copy(action),state:'UNKNOWN'};
}
export async function setupStepPayload(step){
 if(typeof step?.wire!=='string'||await feedbackWireDigest(step.wire)!==step.wire_sha256)throw Error('The retained setup submission is damaged; nothing was sent.');
 const value=JSON.parse(step.wire);if(!['questions','bind','renew'].includes(step.kind)||step.kind!=='questions'&&value.action!==step.kind)throw Error('The retained setup action changed.');if(value.project!==step.project||(step.kind==='questions'?value.id:value.work_id)!==step.workId)throw Error('The retained setup submission changed its target.');return value;
}
export function createReviewSetupDraft({project,workId,storage=globalThis.sessionStorage,backup=globalThis.localStorage}){
 const key='laplace:review-setup:'+JSON.stringify([project,workId]);let state={},generation=0,error='',unreadable=false;
 function refresh(){let winner=null;for(const store of [storage,backup]){let raw;try{raw=store?.getItem(key);}catch{continue;}if(!raw)continue;try{const held=JSON.parse(raw);if(held.schema!=='laplace.review-setup-draft/1'||held.project!==project||held.workId!==workId||!held.state||typeof held.state!=='object'||Array.isArray(held.state))throw Error();if(!winner||(held.generation||0)>winner.generation)winner={generation:held.generation||0,state:held.state};}catch{unreadable=true;error='Stored review setup is unreadable. Keep its original recovery copy; a new Save is unavailable.';}}
  if(winner&&winner.generation>=generation){state=copy(winner.state);generation=winner.generation;}}
 refresh();
 function persist(){if(unreadable)return false;const wire=JSON.stringify({schema:'laplace.review-setup-draft/1',project,workId,generation:++generation,state});let kept=false;for(const store of [storage,backup])try{store?.setItem(key,wire);if(store?.getItem(key)===wire)kept=true;}catch{}if(!kept)error='Review setup could not be retained. Keep this panel open; Save needs a recovery copy.';return kept;}
 return {snapshot(){refresh();return copy(state);},persist,get error(){return error;},get unreadable(){return unreadable;},update(value){refresh();state={...state,...copy(value)};persist();return copy(state);}};
}
// The same catalogue facts used by conversation choices, without selecting its first model
// or writing conversation preferences. A missing configured choice stays visible as such.
export function setupProviderOptions(providers,held={},defaults={}){
 const provider=providers.find(row=>row.id===held.provider),models=providerModelOptions(provider).map(row=>({value:row.id,label:row.name||row.id}));
 if(held.model&&!models.some(row=>row.value===held.model))models.push({value:held.model,label:held.model+' (not in observed choices)'});
 const model=provider?.models?.find(row=>row.id===held.model),efforts=providerEffortOptions(model).map(value=>({value,label:value}));
 if(model?.supports_effort===false&&defaults.effort)efforts.splice(0,efforts.length,{value:defaults.effort,label:'Automatic'});
 if(model?.supports_effort!==false&&held.effort&&!efforts.some(row=>row.value===held.effort))efforts.push({value:held.effort,label:held.effort+(model?'':' (configured)')});
 return {providers:providers.map(row=>({value:row.id,label:row.name||row.id})),models,efforts,description:model?.description||'',effortSupported:model?.supports_effort!==false};
}

// Explicit comparison/adoption preserves current specialised fields and unrelated additions.
// Only the ordinary question fields authored relative to the original basis are overlaid.
export function mergeSetupQuestions(base,authored,current){
 const fields=['label','scope','required','independent','inputs'],before=new Map(base.map(row=>[row.id,row])),edited=new Map(authored.map(row=>[row.id,row])),seen=new Set(),out=[];
 for(const row of current){seen.add(row.id);const old=before.get(row.id),draft=edited.get(row.id);if(!old){out.push(copy(row));continue;}if(!draft){if(ordinarySetupQuestion(row))continue;out.push(copy(row));continue;}if(!ordinarySetupQuestion(row)&&ordinarySetupQuestion(old)&&!sameSetupValue(old,draft))throw Error('A question with your edits became specialised. Keep this comparison and copy the intended prose into a new ordinary question before adopting.');const next=copy(row);if(ordinarySetupQuestion(old)&&ordinarySetupQuestion(row))for(const field of fields)if(!sameSetupValue(old[field]??null,draft[field]??null))next[field]=copy(draft[field]);out.push(next);}
 for(const row of authored){if(before.has(row.id)&&!seen.has(row.id)&&ordinarySetupQuestion(row)&&!sameSetupValue(before.get(row.id),row))throw Error('An edited question was removed by another change. Copy its prose into a new question, then remove the old draft row before adopting.');if(!before.has(row.id)){if(seen.has(row.id))throw Error('A new question ID now belongs to another recorded question. Keep the comparison before saving.');out.push(copy(row));}}
 return out;
}

// Ordinary question labels/unique inputs use the existing obligations() normalisation.
// Raw authored fields remain in the draft and step; source-contract/closure rows are verbatim.
export function canonicalSetupQuestions(rows){return rows.map(row=>ordinarySetupQuestion(row)?{...copy(row),label:row.label.trim(),inputs:[...new Set(row.inputs||[])]}:copy(row));}
