import {taskStateChips,taskFacetRow} from './workspace-work-navigator.mjs';
import {stateChip,declareControl} from './workspace-presentation.mjs';
// Human presentation of already-issued object/run facts. No reads, scientific
// conclusions, permission resolver, effects or hidden technical serialization.
import {referenceKey} from './research-workbench-state.mjs';
export const el=(tag,text='',cls='')=>{const node=document.createElement(tag);node.textContent=text??'';node.className=cls;return node;};
export function button(label,run,{disabled=false,control=null,primary=false}={}){
  const node=el('button',label,primary?'rw-primary':'');node.type='button';node.disabled=disabled;
  if(control)node.dataset.control=control;node.onclick=run;return node;
}
export function details(label,value,{isCurrent=()=>true,control=''}={}){
  const node=el('details','','rw-technical'),summary=el('summary',label);if(control)declareControl(summary,control);node.append(summary);
  node.ontoggle=()=>{if(!node.open||!isCurrent())return;node.querySelector('[data-rw-exact]')?.remove();const text=el('pre',JSON.stringify(typeof value==='function'?value():value,null,2));text.dataset.rwExact='';node.append(text);};
  return node;
}
export function textBody(host,text,cls='rw-recorded'){
  if(typeof text!=='string')return;const body=el('div',text,cls);host.append(body);return body;
}
export function unavailable(host,facet,label){
  if(facet?.state==='AVAILABLE')return false;
  host.append(el('p',(label?label+': ':'')+(facet?.reason||facet?.qualification||(facet?.state==='UNKNOWN'?'The owner could not establish this reading.':'The owner has not supplied this view.')),'rw-qualification'));return true;
}
export const titleFor=row=>row?.title||row?.label||row?.facets?.purpose?.value?.title||row?.reference?.identity?.id||row?.reference?.identity?.path||'Object title not returned';
export function coverage(host,value){
  const row=value?.coverage||{};const text=row.qualification||row.reason;
  if(text)host.append(el('p',text,'rw-qualification'));
  if(row.omitted>0)host.append(el('p',row.omitted+' more entries are outside this page.','rw-qualification'));
  if(row.state==='UNKNOWN'||row.state==='UNAVAILABLE')host.append(el('p','This coverage is '+row.state.toLowerCase()+'. Absence from this view is not an empty result.','rw-alert'));
}
export function evidenceLinks(items,{subject,title,known=[]}={}){
  const sources=new Set(['artifact','source-file','repository-file','reference']);
  const rows=(items||[]).map((row,index)=>{const match=row.reference&&known.find(item=>item.reference&&referenceKey(item.reference)===referenceKey(row.reference));const name=row.title||row.label||row.summary||match?.title||match?.label||(row.reference&&subject&&referenceKey(row.reference)===referenceKey(subject)?title:null)||((row.reference?.kind||'owner result').replaceAll('-',' ')+' '+(index+1));let objectOnly=false;
    try{const url=new URL(row.read.http.url,'http://local');objectOnly=sources.has(row.reference?.kind)&&url.pathname==='/work/discovery'&&url.searchParams.get('facet')==='object'&&url.searchParams.get('section')!=='body';}catch{}
    return {...row,title:(objectOnly?'Open source: ':'Read ')+name,sourceNavigation:objectOnly,focusKey:'evidence:'+index+(row.reference?':'+referenceKey(row.reference):'')};
  });return rows.map((row,index)=>rows.filter(other=>other.title===row.title).length>1?{...row,title:row.title+' ('+(index+1)+')'}:row);
}
export function referenceRows(host,items,{onOpen=()=>{},empty='No entries are recorded in this reading.',selected=null}={}){
  const list=el('ul','','rw-list');
  for(const row of items||[]){
    const item=el('li'),open=button(titleFor(row),()=>onOpen(row),{disabled:!row.read,control: 'research:object'});open.className='rw-object-link';
    if(row.reference)open.dataset.rwReferenceKey=referenceKey(row.reference);if(row.focusKey)open.dataset.rwFocus=row.focusKey;
    if(selected&&row.reference&&referenceKey(row.reference)===referenceKey(selected))open.setAttribute('aria-current','page');
    if(row.kind)open.append(el('small',row.kind.replaceAll('-',' ')));
    if(row.currentness&&row.currentness!=='CURRENT')open.append(el('small',String(row.currentness).replaceAll('_',' ')));
    item.append(open);if(row.reason)item.append(el('p',row.reason,'rw-qualification'));list.append(item);
  }
  if(!list.children.length)list.append(el('li',empty,'rw-qualification'));
  host.append(list);return list;
}
export function actionRows(host,actions,{onAction=()=>{},isCurrent=()=>true,readOnly=false}={}){
  const place=el('div','','rw-actions');
  for(const action of actions||[]){
    if(action.available===false)continue;
    const label=action.title||action.label||String(action.name||action.id||'Owner action').replaceAll('_',' ');
    const invoke=button(label,()=>{if(isCurrent())onAction(action);},{disabled:readOnly||action.permitted!==true,primary:action.primary===true,control: 'research:action'});
    place.append(invoke);if(action.reason){if(action.id==='add-question'&&action.permitted!==true&&/logical.plan/i.test(action.reason)){place.append(el('span','Choose a project context with an editable question or argument plan to add a question here. This is optional for writing and reading sources.','rw-qualification'),details('Exact availability reason',{reason:action.reason},{isCurrent,control:'research:availability-reason'}));}else place.append(el('span',action.reason,'rw-qualification'));}
  }
  host.append(place);return place;
}
export function objectHeader(host,value,{retained=false,at=null,onAction=()=>{},onRefresh=()=>{},isCurrent=()=>true}={}){
  const heading=el('header','','rw-object-heading'),purpose=value.facets?.purpose,body=purpose?.value||{};
  heading.append(el('p',value.subject?.kind?.replaceAll('-',' ')||'Research object','rw-eyebrow'),el('h2',body.title||'Selected object'));
  if(purpose?.state==='AVAILABLE')textBody(heading,Object.hasOwn(body,'summary')?body.summary:body.purpose,'rw-purpose');else unavailable(heading,purpose,'Purpose');
  const standing=value.facets?.standing;
  if(standing?.state==='AVAILABLE'){
    const fact=standing.value||{};const primary=fact.primary||fact.label||fact.summary;
    if(primary){const raw=typeof primary==='string'?primary:primary.label||primary.says||'',words={CURRENT_AT_READ:'Current at this read',OBSERVED_AT_READ:'Observed at this read',CURRENT:'Current recorded version',PINNED:'Pinned recorded version',DECLARED:'Declared by the owner',OPEN:'Open',DISPOSED:'Disposition recorded'};if(value.subject?.kind==='work')heading.append(...taskStateChips(taskFacetRow(fact)).map(stateChip));else heading.append(el('p',words[raw]||raw,'rw-standing'));}
    else if(fact.currentness)heading.append(el('p','Version observation: '+String(fact.currentness).toLowerCase().replaceAll('_',' '),'rw-qualification'));
  }else unavailable(heading,standing,'Current situation');
  if(retained){const old=el('div','','rw-alert');old.append(el('p','Previously inspected'+(at?' at '+new Date(at).toLocaleTimeString(): '')+'. This reading has not been refreshed.'),button('Read current',onRefresh));heading.append(old);}
  actionRows(heading,value.facets?.actions?.items,{onAction,isCurrent,readOnly:retained});host.append(heading);return heading;
}
export function overview(host,value,{onOpen=()=>{},onRead=()=>{},onAction=()=>{},isCurrent=()=>true}={}){
  const links=el('section');links.append(el('h3','Recorded relationships'));
  const relationships=value.facets?.relationships;
  if(!unavailable(links,relationships)){
    const rows=el('ul','','rw-list');
    for(const relation of relationships.items||[]){
      const li=el('li','','rw-card');li.append(el('strong',relation.label||relation.relation||relation.kind||'Recorded relation'));
      if(relation.summary)textBody(li,relation.summary);
      const target=relation.target||relation.object||relation;
      if(target.reference&&target.read)li.append(button(titleFor(target),()=>onOpen(target)));
      else if(relation.read)li.append(button('Inspect relation',()=>onRead(relation.read,relation.label||'Recorded relation')));
      if(relation.qualification)li.append(el('p',relation.qualification,'rw-qualification'));
      if(relation.consumed_basis)li.append(details('Consumed basis',relation.consumed_basis,{isCurrent}));
      rows.append(li);
    }
    if(!rows.children.length)rows.append(el('li','No explicit relationships are recorded in this reading.','rw-qualification'));links.append(rows);
  }
  host.append(links);coverage(host,value);const ownerRead=value.facets?.history?.value?.read;if(ownerRead)host.append(button('Inspect owner record',()=>{if(isCurrent())onRead(ownerRead,'Recorded owner evidence');},{control:'research:inspect-owner'}));
  const technical=details('Identity, currentness and exact owner facts',{subject:value.subject,basis:value.basis,scope:value.scope,standing:value.facets?.standing,coverage:value.coverage},{isCurrent,control:'research:identity-facts'});host.append(technical);
}
export function settingsFacts(host,settings,{onEdit=null,isCurrent=()=>true}={}){
  if(!settings||settings.error){host.append(el('p',settings?.error||'The owner has not supplied effective settings for this selection.','rw-qualification'));return;}
  const rows=settings.effective_settings||settings;
  for(const [stepId,step]of Object.entries(rows)){
    if(!step||typeof step!=='object'||!step.values)continue;
    const card=el('section','','rw-card');card.append(el('h3',step.title||stepId));
    const observation=step.observation||step.provider?.observation||step.model?.observation;
    if(observation)textBody(card,typeof observation==='string'?observation:observation.qualification,'rw-qualification');
    const facts=el('dl','','rw-facts');
    for(const [key,label]of [['provider','Provider'],['model','Model'],['effort','Reasoning effort'],['input_policy','Review input']]){
      const fact=step[key]||{},value=Object.hasOwn(step.values,key)?step.values[key]:undefined;
      facts.append(el('dt',label),el('dd',value===null?'Not used':value===undefined?'Not reported':String(value)));
      const line=fact.lineage||step.lineage?.[key];
      if(line?.length){const parent=el('dd'),d=el('details');d.append(declareControl(el('summary','Where '+label.toLowerCase()+' comes from'),'research:setting-origin',label));const list=el('ol');for(const item of line){const li=el('li');li.append(el('span',item.label||item.origin||item.kind||'Owner scope'));if(Object.hasOwn(item,'value'))li.append(el('span',' · '+String(item.value)));if(item.selected)li.append(el('strong',' · used'));list.append(li);}d.append(list);parent.append(d);facts.append(el('dt','Lineage'),parent);}
      else if(fact.origin)facts.append(el('dt','Origin'),el('dd',fact.origin));
    }
    card.append(facts);
    if(step.instruction?.value!==undefined){const d=el('details');d.append(declareControl(el('summary','Complete instructions'),'research:setting-instructions'));textBody(d,step.instruction.value);if(step.instruction.composition)d.append(el('p',step.instruction.composition,'rw-qualification'));card.append(d);}
    const boundaries=new Set([step.application_boundary,...['provider','model','effort','input_policy'].map(key=>step[key]?.application_boundary)].filter(value=>typeof value==='string'));
    for(const boundary of boundaries)textBody(card,boundary,'rw-qualification');
    card.append(details('Exact setting facts and edit guard',step,{isCurrent,control:'research:setting-facts'}));host.append(card);
  }
  if(onEdit)host.append(button('Edit workflow definition',onEdit));
}
