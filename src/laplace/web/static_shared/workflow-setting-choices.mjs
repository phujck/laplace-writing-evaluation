// Suggestions from literal draft declarations only. The saved owner resolves effective settings.
import {providerModelOptions,providerEffortOptions} from './provider-options.mjs';
const keys=['provider','model','effort'];
// The settings the Design column shows for a step, in the owner's order (workflow_definitions.resolve_settings).
export const WORKFLOW_SETTING_KEYS=Object.freeze(['provider','model','effort','input_policy']);
// What the draft itself declares, nearest scope first. `origins` names each value's scope in the owner's own
// coordinates ('definition', 'assignment:<step id>'), so a draft value and an owner fact are worded by one function.
export function declaredWorkflowSettings(body,stepId=null,wanted=keys){
  const values={},sources={},origins={},steps=new Map((body.steps||[]).map(row=>[row.id,row])),seen=new Set();
  let cursor=stepId==null?null:steps.get(stepId);
  if(stepId!=null&&!cursor)return {values,sources,origins,known:false};
  while(cursor){
    if(seen.has(cursor.id))return {values:{},sources:{},origins:{},known:false};seen.add(cursor.id);
    for(const key of wanted)if(values[key]===undefined&&Object.hasOwn(cursor.assignment?.settings||{},key)){values[key]=cursor.assignment.settings[key];sources[key]=cursor.title||cursor.id;origins[key]='assignment:'+cursor.id;}
    if(cursor.parent_id&&!steps.has(cursor.parent_id))return {values:{},sources:{},origins:{},known:false};
    cursor=steps.get(cursor.parent_id);
  }
  for(const key of wanted)if(values[key]===undefined&&Object.hasOwn(body.settings||{},key)){values[key]=body.settings[key];sources[key]='Workflow defaults';origins[key]='definition';}
  return {values,sources,origins,known:true};
}
// Compare only the relevant literal declarations/containment, never instructions or titles.
function declarationBasis(body,stepId,keys,role=false){
  const steps=new Map((body?.steps||[]).map(row=>[row.id,row])),seen=new Set(),path=[];let step=steps.get(stepId);
  if(!step)return null;const selectedRole=step.assignment?.role;
  while(step){if(seen.has(step.id))return null;seen.add(step.id);path.push([step.id,...keys.map(key=>Object.hasOwn(step.assignment?.settings||{},key)?[key,step.assignment.settings[key]]:[key])]);if(step.parent_id&&!steps.has(step.parent_id))return null;step=steps.get(step.parent_id);}
  return JSON.stringify([path,keys.map(key=>Object.hasOwn(body.settings||{},key)?[key,body.settings[key]]:[key]),...(role?[selectedRole]:[])]);
}
export function workflowSettingChoices(body,stepId,providers=[],saved=null){
  const declared=declaredWorkflowSettings(body,stepId);
  if(declared.known&&stepId&&saved?.definition){
    for(const key of ['provider','model']){
      const keys=key==='provider'?['provider']:['provider','model'],basis=declarationBasis(body,stepId,keys,key==='model'),prior=declarationBasis(saved.definition,stepId,keys,key==='model'),fact=saved.effective_settings?.[stepId]?.[key];
      if(declared.values[key]===undefined&&basis!==null&&basis===prior&&typeof fact?.value==='string'&&fact.value){declared.values[key]=fact.value;declared.sources[key]='Saved version';}
    }
  }
  const provider=providers.find(row=>row.id===declared.values.provider),model=providerModelOptions(provider).find(row=>row.id===declared.values.model);
  return {...declared,provider,model,choices:{provider:providers.filter(row=>row.id).map(row=>({value:row.id,label:row.name||row.id})),model:providerModelOptions(provider).filter(row=>row.id).map(row=>({value:row.id,label:row.name||row.id})),effort:model&&model.supports_effort!==false?providerEffortOptions(model).map(value=>({value,label:value})):[]}};
}
// WHERE A VALUE COMES FROM, in words (wave 12). The one mapping from the settings owner's origins
// (resolve_settings: 'definition', 'assignment:<id>', 'worker-tier-default', 'unset', and a selected
// 'existing-session-resolver' normalisation in the lineage) to the words the page shows. The exact
// origin stays one click away (Identity).
export function settingOriginWords(fact,body,stepId){
  const origin=fact?.origin,normalised=(fact?.lineage||[]).some(row=>row?.kind==='normalization'&&row.selected===true);
  let words;
  if(origin==='definition')words='Workflow defaults';
  else if(typeof origin==='string'&&origin.startsWith('assignment:')){const id=origin.slice('assignment:'.length);words=id===stepId?'This step':'The group '+((body?.steps||[]).find(row=>row.id===id)?.title||id);}
  else if(origin==='worker-tier-default')words='The provider’s default for this role';
  else if(origin==='unset')words='No scope sets it';
  else words='An origin this page has no words for (see Identity)';
  return normalised?words+' · Normalised by the provider':words;
}
// Which scope's declarations decide each key, so an owner fact is reused only while they are unchanged.
const LINEAGE_BASIS={provider:[['provider'],false],model:[['provider','model'],true],effort:[['provider','model','effort'],true],input_policy:[['input_policy'],false]};
// Each setting of one step with where it comes from. 'owner': the settings owner resolved it in the saved
// version's read and the declarations that decide it are unchanged in this draft. 'draft': only what the
// draft declares (unchecked); an undeclared key has no value here and none is supplied.
export function workflowSettingLineage(body,stepId,saved=null){
  const declared=declaredWorkflowSettings(body,stepId,WORKFLOW_SETTING_KEYS),facts=stepId?saved?.effective_settings?.[stepId]:null,rows={};
  for(const key of WORKFLOW_SETTING_KEYS){
    const fact=facts?.[key],[basisKeys,role]=LINEAGE_BASIS[key],basis=declared.known&&fact&&saved?.definition?declarationBasis(body,stepId,basisKeys,role):null;
    rows[key]=basis!==null&&basis===declarationBasis(saved.definition,stepId,basisKeys,role)
      ?{checked:'owner',value:fact.value??null,origin:fact.origin,fact}
      :{checked:'draft',declared:Object.hasOwn(declared.values,key),value:declared.values[key]??null,origin:declared.origins[key]||null};
  }
  return {known:declared.known,rows,unavailable:Array.isArray(facts?.unavailable_scopes)?[...facts.unavailable_scopes]:null,boundary:facts?.provider?.application_boundary||null};
}
