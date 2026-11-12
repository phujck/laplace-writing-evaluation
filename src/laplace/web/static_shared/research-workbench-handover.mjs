import {el,button,details,textBody,actionRows} from './research-workbench-view.mjs';
// The manifest owner distinguishes frozen portable content from current origin
// observations. Omission labels deliberately carry no hidden subject metadata.
export function renderResearchHandover(host,value,{onRead=()=>{},onAction=()=>{},isCurrent=()=>true}={}){
  if(value?.schema_version!=='laplace.research-handover/1'){host.append(el('p','The selected owner returned no compatible handover manifest.','rw-qualification'));return false;}
  host.append(el('h3','Selected portable handover'));textBody(host,value.qualification,'rw-qualification');
  const rows=value.entries||[],included=rows.filter(row=>row.class==='included');host.append(el('p',included.length+' included objects · '+(rows.length-included.length)+' omitted, external or unbound entries.'));
  actionRows(host,value.actions,{onAction,isCurrent});
  for(const row of rows){const card=el('article','','rw-card');
    if(row.class==='included'){
      const label=row.title||row.reference?.kind?.replaceAll('-',' ')||'Included object';card.append(el('h4',label));
      card.append(el('p',row.representation==='frozen-owner-snapshot'?'Frozen owner snapshot; its original assertion is not recreated as live scientific state.':row.reference?.kind==='workflow-definition'?'Exact saved workflow and its selected lineage.':'Selected frozen source bytes.'));
      if(row.currentness)card.append(el('p','Origin observation: '+String(row.currentness).toLowerCase().replaceAll('_',' '),'rw-qualification'));
      if(row.frozen_read){
        const focus={kind:'carried-read',scope_id:value.scope_id,manifest:value.reference,manifest_basis:value.basis,reference:row.reference,basis:row.basis,read:row.frozen_read};
        const open=button('Read carried copy',()=>{if(isCurrent())return onRead(row.frozen_read,label,row,focus);});
        open.dataset.rwFocus=JSON.stringify(focus);card.append(open);
      }
      card.append(details('Exact included identity, carried bytes and reading',row,{isCurrent}));
    }else if(row.class==='external'){card.append(el('h4','External public reference'),el('p',row.public_locator||'Public locator unavailable'));}
    else if(row.class==='runtime-unbound'){card.append(el('h4','Runtime remains unbound'),el('p',[row.provider,row.model].filter(Boolean).join(' · ')));textBody(card,row.qualification,'rw-qualification');}
    else{card.append(el('h4',({'private_not_included':'Private material not included',excluded:'Excluded material',unavailable:'Unavailable material'})[row.class]||'Not included'));if(row.reason_code)card.append(el('p',String(row.reason_code).toLowerCase().replaceAll('_',' '),'rw-qualification'));}
    host.append(card);
  }
  host.append(details('Manifest identity and request receipt',{project:value.project,reference:value.reference,basis:value.basis,request_id:value.request_id,intent_sha256:value.intent_sha256},{isCurrent}));return true;
}
