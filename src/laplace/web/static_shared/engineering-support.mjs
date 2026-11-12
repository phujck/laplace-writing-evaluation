// ENGINEERING SUPPORT ROWS. Purpose: project the engineering work/claim owner's rows for one
// argument object as relation rows with their standing. Ownership: the rows are the owner's
// (/work engineering support reads); nothing here saves or infers status. Public contract:
// engineeringRows(value) -> rows; renderEngineeringSupport(host, value, {onRead}). Inputs: one
// owner value; outputs: DOM. Currentness: whatever the read carried; no cache. Errors: an
// absent owner value renders the honest empty text. Consumers: concept-reader.mjs. Storage: none.
import {conceptHumanTarget} from './writing-owner-read.mjs';
// A projection of the existing engineering work/claim owner, never saved status.
const el=(tag,text='',cls='')=>{const node=document.createElement(tag);node.textContent=text;node.className=cls;return node;};
export function engineeringRows(support={}){
  if(support.status==='HISTORICAL_ARTIFACT')return [{status:support.status,reason:support.reason}];
  return support.claims?.flatMap(claim=>(claim.bindings||[]).map(row=>({...row,node:claim.node,claimRead:claim.read_handle})))||support.bindings||[];
}
export function renderEngineeringSupport(host,support={}, {onAdopt=null}={}){
  const rows=engineeringRows(support);
  if(!rows.length&&['UNDECLARED',undefined].includes(support.status))return;
  const section=el('section','','concept-record-section engineering-support');
  section.append(el('h4','Engineering support'),el('p',support.status==='CURRENT'?'Current scoped engineering observation':'Review required before relying on this engineering assertion',support.status==='CURRENT'?'muted':'error'));
  for(const row of rows){
    const detail=el('section');detail.append(el('strong',row.covered_scope||'Recorded guide'),el('p',String(row.status||'UNKNOWN').replaceAll('_',' ').toLowerCase()),el('p',row.reason||support.reason||'Current basis is unavailable.'));
    if(row.read_handle){const id=row.read_handle.payload?.id,link=el('a','Inspect engineering work');link.href=id?'/project?'+new URLSearchParams({workspace:'writing',corpus:row.read_handle.payload?.namespace,view:'work',work:id}):row.read_handle.http?.url||'#';detail.append(link);}
    if(row.claimRead?.http?.url){const target=row.claimRead.http.method==='GET'?conceptHumanTarget(row.claimRead.http.url):null;
      if(target){const link=el('a','Open in Argument & evidence (opens separately)');link.href=target.href;link.target='_blank';link.rel='noopener noreferrer';detail.append(link);}
      else detail.append(el('p','Current claim read route is unavailable: exact project and node coordinates are required.','error'));
    }
    if(row.completion_revision){const basis=el('details');basis.append(el('summary','Consumed and current basis'),el('p','Consumed work: '+row.completion_revision),el('p','Current work: '+(row.current_completion_revision||'unavailable')),el('p','Consumed meaning: '+row.meaning_revision),el('p','Current meaning: '+(row.current_meaning_revision||'unavailable')));detail.append(basis);}
    section.append(detail);
  }
  section.append(el('p','This covers the named engineering assertion only. Independent verification is not asserted.','muted'));
  if(onAdopt&&support.adoption_handle&&rows.some(row=>row.status==='ACK_REQUIRED')){const button=el('button','Acknowledge inspected engineering basis');button.type='button';button.onclick=async()=>{button.disabled=true;try{await onAdopt(support.adoption_handle);}catch(error){section.append(el('p',error.message,'error'));button.disabled=false;}};section.append(button);}
  host.append(section);return section;
}
