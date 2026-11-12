// THE ARGUMENT RECORD READER. Purpose: paint one canonical argument object (its kind, title,
// statement, proof and formal standing, relations, engineering support) the same way in the
// logical reader and its edit surface. Ownership: the record is concepts_surface's (the concept
// read); proof/formal vocabularies are the owner's (PROOF_STATUS_TONES maps them to chip tones
// and never shows a positive tone for an absent or unproven standing). Public contract:
// renderConceptRecord and the display helpers (displayLabel, displayConceptKind,
// statementDisplayTex, normalizeScientificProse, relationshipLabel, scientificLimitations,
// formalAssumptionPosture, formalTargetIndex, conceptReferenceSourceIndex). Inputs: one concept
// value; outputs: DOM. Currentness: the read's content_revision; no cache. Errors: a missing
// record renders its reason. Consumers: concept-explorer.mjs, workspace.mjs (Argument view),
// writing-artifact.mjs. Controls: argument:record. Storage: none.
import {renderEngineeringSupport} from './engineering-support.mjs';
import {pendingRead} from './pending-read.mjs';
// A readable scientific record shared by the logical reader and its edit surface.
const el=(tag,text='',cls='')=>{const node=document.createElement(tag);node.textContent=text;node.className=cls;return node;};
let mathReady;
async function mathRenderer(){
  if(window.katex)return window.katex;
  if(!mathReady)mathReady=new Promise(resolve=>{if(!document.querySelector('link[data-concept-math]')){const css=el('link');css.rel='stylesheet';css.href='/shared/katex/katex.min.css';css.dataset.conceptMath='';document.head.append(css);}const script=el('script');script.src='/shared/katex/katex.min.js';script.onload=()=>resolve(window.katex||null);script.onerror=()=>resolve(null);document.head.append(script);});
  return mathReady;
}
const content=value=>typeof value==='string'?value:value?.text||value?.statement||value?.description||value?.summary||value?.tex||value?.latex||'';
export function normalizeScientificProse(value){
  return String(value||'').replace(/\r\n?/g,'\n').replace(/\\par\b/g,'\n\n')
    .replace(/\n[ \t]*\n+/g,'\u0000').replace(/[ \t]*\n[ \t]*/g,' ')
    .replace(/\u0000/g,'\n\n');
}
function appendProse(host,text,onReference){
  const pattern=/\\(emph|textit|textbf|texttt|label|eqref|ref|cref|Cref)\s*\{([^{}]*)\}/g;let at=0,match;
  const plain=value=>host.append(document.createTextNode(normalizeScientificProse(value).replace(/~/g,'\u00a0').replace(/\\noindent\b/g,'').replace(/\\([%&_#])/g,'$1')));
  while((match=pattern.exec(text))){plain(text.slice(at,match.index));const [,kind,value]=match;if(['emph','textit','textbf','texttt'].includes(kind)){const node=el(kind==='textbf'?'strong':kind==='texttt'?'code':'em');appendProse(node,value,onReference);host.append(node);}else if(kind!=='label'){const link=el('button',kind==='eqref'?'(view)':'reference','concept-inline-reference');link.type='button';link.setAttribute('aria-label','Read source reference '+value);link.title=value;link.onclick=()=>onReference?.({key:value,kind},link);if(!onReference){link.disabled=true;link.textContent=value;}host.append(link);}at=pattern.lastIndex;}plain(text.slice(at));
}
export function statementDisplayTex(value){
  const text=String(value||'');
  if(/\$|\\[\[(]|\\begin\{/.test(text))return text;
  const prose=text.replace(/\\(?:text|textrm|mathrm|operatorname)\s*\{[^{}]*\}/g,'M').replace(/\\[A-Za-z]+/g,'').replace(/\\./g,'');
  return /[\\_^=<>]/.test(text)&&!/[A-Za-z]{3,}/.test(prose)?'\\['+text+'\\]':text;
}
export function conceptReferenceSourceIndex(record){
  const sources=record.source_locations||[],primary=record.authored?.sources?.[record.authored?.primary_source];
  if(primary){const index=sources.findIndex(source=>source.path===primary.path&&(source.repository||'')===(primary.repository||''));if(index>=0)return index;}
  if(record.statement_origin==='SOURCE'){const matches=sources.map((source,index)=>({source,index})).filter(({source})=>source.statement_tex===record.statement_tex);if(matches.length===1)return matches[0].index;}
  return sources.length===1?0:-1;
}
const equationEnvironments=/^(equation|align|gather|multline|displaymath)\*?$/;
const sourceStatement=source=>source?.statement_tex&&equationEnvironments.test(source.environment||'')?'\\begin{'+source.environment+'}'+source.statement_tex+'\\end{'+source.environment+'}':source?.statement_tex||source?.excerpt||'';
export async function scientificText(host,value,{onReference}={}){
  const text=String(content(value)||'');
  const pattern=/(\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|\\begin\{(equation\*?|align\*?|gather\*?|multline\*?|displaymath)\}[\s\S]*?\\end\{\2\}|\$(?!\$)[^$]+?\$|\\\([\s\S]*?\\\))/g;
  let offset=0,match;const maths=[];
  while((match=pattern.exec(text))){appendProse(host,text.slice(offset,match.index),onReference);const raw=match[0],environment=raw.match(/^\\begin\{([^}]+)\}/)?.[1],display=!!environment||raw.startsWith('$$')||raw.startsWith('\\['),length=raw.startsWith('$')&&!display?1:2;let source=environment?raw.replace(/^\\begin\{[^}]+\}/,'').replace(/\\end\{[^}]+\}$/,''):raw.slice(length,-length);source=source.replace(/\\label\s*\{[^}]*\}/g,'');if(environment?.startsWith('align'))source='\\begin{aligned}'+source+'\\end{aligned}';else if(environment&&/^(gather|multline)/.test(environment))source='\\begin{gathered}'+source+'\\end{gathered}';const math=el(display?'div':'span',raw,display?'concept-display-math':'concept-inline-math');host.append(math);maths.push({math,source,display});offset=pattern.lastIndex;}
  appendProse(host,text.slice(offset),onReference);if(!maths.length)return;
  const katex=await mathRenderer();if(katex)for(const {math,source,display}of maths)katex.render(source,math,{displayMode:display,throwOnError:false,trust:false,strict:'ignore'});
}
const short=value=>{const line=String(value||'').trim().split(/\r?\n/)[0].replace(/\s+/g,' ').trim();return line&&line.length<=96?line:'';};
const humanizeId=value=>{const leaf=String(value||'').split(/[/:#]/).filter(Boolean).at(-1)||'Concept';return leaf.replace(/[-_]+/g,' ').replace(/\s+/g,' ').trim();};
export function displayConceptKind(node={}){
  if(node.kind==='portal')return node.members?.length||node.child_count||node.has_children?'Group':'Linked concept';
  return String(node.kind||'Concept').replaceAll('-',' ');
}
export function displayLabel(node={}){
  const authored=String(node.title||node.projection?.title||'').trim().replace(/\s+/g,' ');
  return authored||short(node.projection?.term)||(node.kind==='citation'&&node.label?String(node.label).trim().replace(/\s+/g,' '):short(node.label))||humanizeId(node.id);
}
export function formalAssumptionPosture(target={}){
  const assumptions=target.assumptions||[],qualification=target.qualification||{};
  const gap=[...(qualification.missing||[]),...(qualification.indexing_gaps||[])].some(value=>String(value).includes('assumption'));
  if(assumptions.length)return {state:'STATED',text:'Stated assumptions'};
  if(target.assumptions_authored)return {state:'EXPLICIT_NONE',text:'No additional assumptions are stated.'};
  if(target.statement_origin==='SOURCE')return {state:'SOURCE_NOT_INDEXED',text:'Source hypotheses are not separately indexed. Inspect the linked statement.'};
  return {state:gap?'MISSING':'NOT_RECORDED',text:'Assumptions have not been recorded. Record an explicit empty list only when there are none.'};
}
export function formalTargetIndex(targets=[],receipts=[],query=''){
  const needle=String(query||'').trim().toLowerCase();
  return targets.filter(target=>target.binding_ready||target.statement_tex).map(target=>{
    const receipt=receipts.find(row=>!row.superseded&&row.concept?.id===target.id);
    return {target,receipt,status:receipt?(receipt.stale?'STALE':receipt.proof_status):target.binding_ready?'NOT CHECKED':'NOT CHECKABLE'};
  }).filter(({target,status})=>!needle||[target.id,target.label,target.statement_tex,target.origin_posture,
    target.documentation_status,status].some(value=>String(value||'').toLowerCase().includes(needle)));
}
export function scientificLimitations(value){
  if(Array.isArray(value))return {kind:'list',items:value.filter(item=>typeof item==='string'&&item.trim())};
  if(typeof value==='string'&&value.trim())return {kind:'prose',text:value};
  return {kind:'empty'};
}
export const relationNames={prerequisite:'Requires',support:'Draws on',validated_by:'Validated by',counterevidence:'Counterevidence',implementation:'Implemented by',analogy:'Analogy',questions:'Questions',contains:'Contains'};
export function relationshipLabel(rel,outgoing=true){return outgoing?(relationNames[rel]||rel):({prerequisite:'Required by',support:'Supports',validated_by:'Validates',counterevidence:'Counterevidence for',implementation:'Implements',analogy:'Analogous to',questions:'Questioned by',contains:'Contained by'}[rel]||'Incoming '+rel);}
// THE PROOF AND FORMAL CHIP TONES (Sol proof-chips, 2026-10-14): explicit maps over the canonical
// owner vocabulary, never a substring test. mathematical_records.read publishes proof.status as
// NOT_RECORDED, SOURCE_UNREVIEWED or AUTHORED_UNREVIEWED; _verification publishes NOT_CHECKED,
// NOT_OBSERVED, RELATED_FORMAL_RECEIPT, STALE, UNAVAILABLE, CHECKED_DECLARATION, PARTIALLY_CHECKED
// or NOT_ESTABLISHED. An absent or unreviewed proof is never green; only an explicit positive
// state is; an unknown state is neutral. RECORDED/VERIFIED remain the explicit positive words.
export const PROOF_STATUS_TONES=Object.freeze({NOT_RECORDED:'attention',UNPROVED:'attention',INCOMPLETE:'attention',MISSING:'attention',OPEN:'attention',
  SOURCE_UNREVIEWED:'neutral',AUTHORED_UNREVIEWED:'neutral',RECORDED:'ok',PROVED:'ok',COMPLETE:'ok'});
export const FORMAL_STATUS_TONES=Object.freeze({NOT_CHECKED:'neutral',NOT_OBSERVED:'neutral',RELATED_FORMAL_RECEIPT:'neutral',NOT_ESTABLISHED:'neutral',PARTIALLY_CHECKED:'neutral',
  CHECKED_DECLARATION:'ok',VERIFIED:'ok',STALE:'attention',UNAVAILABLE:'attention',FAILED:'attention'});
export const proofStatusTone=status=>PROOF_STATUS_TONES[String(status||'')]||'neutral';
export const formalStatusTone=status=>FORMAL_STATUS_TONES[String(status||'')]||'neutral';
export async function renderConceptRecord(host,{node,state={},record,onNavigate,onSource,showTitle=true,afterMeaning=null,onAdoptEngineering=null,onEditRelation,onDirty=()=>{},resolveReference}={}){
  const math=record||state.mathematical_record||{};
  const article=el('article','','concept-record');host.append(article);
  const verification=math.verification||state.verification||{},proof=math.proof||{};
  const proofStatus=proof.status,formalStatus=verification.status;
  const proofKinds=new Set(['theorem','lemma','proposition','corollary','claim','result','derivation-step']),proofRequired=proofKinds.has(node.kind);
  // THE RECORD HEADER (M5 C6, object-header pattern): kind as eyebrow, the title, then the
  // proof and formal-verification standing as chips; the prose below stays the owner's. The
  // proof chip is shown where a proof is owed or where one is recorded; a definition with the
  // owner default NOT_RECORDED carries no proof chip. A related receipt keeps its qualifier.
  const header=el('header','','object-header concept-record-header');header.setAttribute('data-control','argument:record');
  header.append(el('span',displayConceptKind(node),'object-eyebrow concept-type'));if(showTitle)header.append(el('h3',displayLabel(node),'object-title'));
  const chips=el('div','','chip-row');const chip=(label,tone,title='')=>{const node=el('span',label,'state-chip');node.setAttribute('data-tone',tone);if(title)node.title=title;return node;};
  const words=value=>String(value).replaceAll('_',' ').toLowerCase();
  if(proofStatus&&(proofRequired||proofStatus!=='NOT_RECORDED'))chips.append(chip('Proof '+words(proofStatus),proofStatusTone(proofStatus)));
  if(formalStatus&&formalStatus!=='NOT_CHECKED')chips.append(chip('Formal '+words(formalStatus),formalStatusTone(formalStatus),formalStatus==='RELATED_FORMAL_RECEIPT'?String(verification.reason||'Shares a result binding; no declaration is linked to this concept.'):''));
  if(chips.children.length)header.append(chips);article.append(header);
  const posture=el('p','','concept-proof-posture');
  const hasFormal=!!formalStatus&&formalStatus!=='NOT_CHECKED';
  if(proofRequired||hasFormal){if(proofRequired)posture.append(el('strong','Proof: '),document.createTextNode(proofStatus?String(proofStatus).replaceAll('_',' ').toLowerCase():'not recorded'),el('br'));posture.append(el('strong','Formal verification: '),document.createTextNode(formalStatus?String(formalStatus).replaceAll('_',' ').toLowerCase():'not checked'));if(formalStatus==='RELATED_FORMAL_RECEIPT')posture.append(el('br'),document.createTextNode(verification.reason||'A formal check shares an evidence result but does not verify this declaration.'));if(hasFormal)posture.append(el('br'),el('strong','Scientific alignment: '),document.createTextNode(String(verification.informal_alignment||'UNASSESSED').replaceAll('_',' ').toLowerCase()));}
  const formal=el('details','','concept-formal-facet');formal.append(el('summary','Proof and formalisation · '+(formalStatus?String(formalStatus).replaceAll('_',' ').toLowerCase():'not checked')));formal.append(posture);
  const referenceIndex=conceptReferenceSourceIndex(math);
  const reference=async(ref,button)=>{const existing=button.nextElementSibling;if(existing?.classList.contains('concept-source-popout')){existing.remove();return;}const panel=el('section','','concept-source-popout'),close=el('button','Close reference');close.type='button';close.onclick=()=>{panel.remove();button.focus({preventScroll:true});};panel.append(close,pendingRead(el('p','Reading referenced source…')));button.after(panel);try{if(!resolveReference)throw Error('Source-reference lookup is unavailable.');if(referenceIndex<0)throw Error('Choose the statement source before following this reference.');const source=await resolveReference(ref,referenceIndex);if(source.error)throw Error(source.error);panel.replaceChildren(close,el('strong',source.label||ref.key));const content=el('div','','scientific-prose');await scientificText(content,sourceStatement(source),{onReference:reference});panel.append(content,el('p',(source.path||source.file||'')+(source.line_start?':'+source.line_start+'–'+source.line_end:''),'muted'));const exact=el('details');exact.append(el('summary','Exact source'),el('pre',source.excerpt||'','concept-source-excerpt'));panel.append(exact);}catch(error){panel.replaceChildren(close,el('p',error.message,'error'));}};
  const section=async(label,value,empty,parent=article)=>{const box=el('section','','concept-record-section');box.append(el('h4',label));const values=Array.isArray(value)?value:value?[value]:[];if(!values.length)box.append(el('p',empty,'muted'));for(const item of values){const p=el('div','','scientific-prose');await scientificText(p,item,{onReference:reference});box.append(p);const target=item?.node_id||item?.concept_id;if(target&&onNavigate){const link=el('button',item.label||target,'concept-record-link');link.type='button';link.onclick=()=>onNavigate(target);box.append(link);}}parent.append(box);return box;};
  const statement=math.statement_origin==='SOURCE'?sourceStatement((math.source_locations||[]).find(source=>source.statement_tex===math.statement_tex))||math.statement_tex:math.statement_tex;
  if(statement)await section('Statement',statementDisplayTex(statement));
  if(statement&&afterMeaning)article.append(afterMeaning);
  if(math.domain)await section('Domain',math.domain);
  if(!statement)await section('Authored description',node.summary||node.meaning||node.essence,'No statement or description has been recorded.');
  if(!statement&&afterMeaning)article.append(afterMeaning);
  if(proofRequired||hasFormal)article.append(formal);
  if(['theorem','lemma','proposition','corollary','result','postulate','assumption','definition'].includes(node.kind)||statement){
    await section('Assumptions',math.assumptions,Object.hasOwn(math.authored||{},'assumptions')?'No additional assumptions are stated.':'Assumptions have not been recorded separately.',statement?article:formal);
    if(proofRequired)await section('Proof or derivation',proof.text,'No proof or derivation is recorded for this object.',formal);
  }
  if(math.limitations?.length)await section('Scope and limitations',math.limitations);
  renderEngineeringSupport(article,state.source_support?.engineering_support,{onAdopt:onAdoptEngineering});
  if(math.source_ambiguity?.length)article.append(el('p','Linked sources contain different statements. Choose the statement source in Edit mathematical record.','error'));
  if(math.qualification?.missing?.length)await section('Required scientific content',math.qualification.missing,'',formal);
  if(math.qualification?.indexing_gaps?.length)await section('Optional indexing',math.qualification.indexing_gaps,'',formal);
  if(math.qualification?.source_gaps)article.append(el('p',`${math.qualification.source_gaps} linked ${math.qualification.source_gaps===1?'source is':'sources are'} unresolved. Inspect Sources below.`,'error'));
  if(!formal.parentElement&&(formal.children.length>2||math.qualification?.missing?.length||math.qualification?.indexing_gaps?.length))article.append(formal);
  const sources=math.source_locations||state.source_locations||[];
  const sourceBox=el('section','','concept-record-section');sourceBox.append(el('h4','Sources'));
  if(!sources.length)sourceBox.append(el('p','No source location is linked.','muted'));
  for(const source of sources){const label=source.label||[source.path||source.file,source.line_start?':'+source.line_start:''].join('');if(!label)continue;const detail=el('details','','concept-source');detail.append(el('summary',label));if(source.excerpt)detail.append(el('pre',source.excerpt,'concept-source-excerpt'));if(source.error)detail.append(el('p',source.error,'error'));if(source.status)detail.append(el('p',String(source.status).replaceAll('_',' ').toLowerCase(),'muted'));if(source.sha256){const receipt=el('details');receipt.append(el('summary','Source fingerprint'),el('code',source.sha256));detail.append(receipt);}if(onSource&&source.file){const locate=el('button','Locate in manuscript');locate.type='button';locate.onclick=()=>onSource(source);detail.append(locate);}sourceBox.append(detail);}article.append(sourceBox);
  const relations=state.relations||node.relations||[],neighbors=new Map([node,...(state.neighbors||[])].map(item=>[item.id,item]));
  if(relations.length){const relationships=el('section','','concept-record-section');relationships.append(el('h4','Relationships'));const list=el('div','','concept-relationship-list');for(const relation of relations){const outgoing=relation.source===node.id,target=outgoing?relation.target:relation.source,other=neighbors.get(target)||{id:target};const row=el('div','','concept-relationship');row.append(el('span',relationshipLabel(relation.rel,outgoing),'concept-relationship-kind'));const link=el('button',displayLabel(other));link.type='button';link.title=target;link.onclick=()=>onNavigate?.(target);row.append(link);if(relation.rationale){const reason=el('details');reason.append(el('summary','Why this relationship'));const words=el('div','','scientific-prose');reason.append(words);await scientificText(words,relation.rationale);row.append(reason);}
      if(onEditRelation){const edit=el('details');edit.append(el('summary','Edit relationship'));const form=el('form','','work-form'),type=el('select'),reason=el('textarea'),status=el('p');type.setAttribute('aria-label','Relationship type');for(const [value,name]of Object.entries(relationNames)){const option=el('option',name);option.value=value;type.append(option);}if(![...type.options].some(option=>option.value===relation.rel)){const option=el('option',relation.rel);option.value=relation.rel;type.append(option);}type.value=relation.rel;reason.rows=3;reason.value=relation.rationale||'';reason.setAttribute('aria-label','Relationship reasoning');const save=el('button','Save relationship');form.append(type,reason,save,status);form.oninput=()=>onDirty(true);form.onsubmit=async event=>{event.preventDefault();save.disabled=true;try{await onEditRelation(relation,{rel:type.value,rationale:reason.value});}catch(error){status.textContent=error.message;save.disabled=false;}};edit.append(form);row.append(edit);}list.append(row);}relationships.append(list);article.append(relationships);}
  return article;
}


const localConceptChanges=new Set(['edit_node','set_source','set_projection','set_mathematics','set_kind','set_status']);
export function conceptChangeGuard(state,node,operation){
  // The explicit field is also the running server's capability signal. Older
  // servers expose content_revision but cannot accept this mutation guard.
  if(localConceptChanges.has(operation)&&state?.focus?.id===node&&typeof state.mutation_revision==='string'&&state.mutation_revision)return {mutation_revision:state.mutation_revision};
  return {base_revision:state?.revision};
}

export function mountMathematicsEditor(host,{record={},node,state,project,request,onDirty=()=>{},onSaved=()=>{}}){
  const authored=record.authored||{},details=el('details','','mathematics-editor');details.append(el('summary','Edit mathematical record'));const form=el('form','','work-form');details.append(form);host.append(details);
  const area=(name,label,value,rows=4)=>{const wrap=el('label',label),field=el('textarea');field.name=name;field.rows=rows;field.value=value||'';wrap.append(field);form.append(wrap);return field;};
  const ownsStatement=typeof authored.statement_tex==='string'&&!!authored.statement_tex.trim(),sourceStatementText=!ownsStatement&&record.statement_origin==='SOURCE'?record.statement_tex||'':'';
  const statement=area('statement','Statement',ownsStatement?authored.statement_tex:sourceStatementText,5),domain=area('domain','Domain and definitions',authored.domain||'',2);
  if(sourceStatementText){const source=record.source_locations?.find(item=>item.statement_tex===record.statement_tex)||{};statement.parentElement?.append(el('small','From linked source '+(source.label||source.path||source.file||'')+'. Edit to create an authored version; leave unchanged to retain source attribution.','muted'));}
  const assumptions=el('section','','mathematics-assumptions');assumptions.append(el('h4','Assumptions'));const rows=el('div');assumptions.append(rows);form.append(assumptions);
  const assumptionRow=value=>{const row=el('div','','mathematics-assumption-row'),text=el('textarea'),link=el('input');text.value=value.text||'';text.rows=2;text.placeholder='State the assumption';text.setAttribute('aria-label','Assumption');link.value=value.node_id||'';link.placeholder='Linked concept (optional)';link.setAttribute('aria-label','Linked concept identity');const remove=el('button','Remove assumption');remove.type='button';remove.onclick=()=>{row.remove();onDirty(true);};row.append(text,link,remove);rows.append(row);};
  for(const value of authored.assumptions||[])assumptionRow(value);const add=el('button','Add assumption');add.type='button';add.onclick=()=>{assumptionRow({});onDirty(true);};assumptions.append(add);
  const noneLabel=el('label','','mathematics-no-assumptions'),none=el('input');none.type='checkbox';none.checked=Object.hasOwn(authored,'assumptions')&&authored.assumptions.length===0;noneLabel.append(none,document.createTextNode('No additional assumptions to list'));assumptions.append(noneLabel);const noneChanged=()=>{rows.hidden=none.checked;add.disabled=none.checked;};none.onchange=()=>{noneChanged();onDirty(true);};noneChanged();
  let primarySource=null;if((authored.sources||[]).length>1){const wrap=el('label','Statement source'),select=el('select'),automatic=el('option','Use the unambiguous linked statement');automatic.value='';select.append(automatic);authored.sources.forEach((source,index)=>{const option=el('option',source.label?source.label+' · '+source.path:source.path);option.value=String(index);select.append(option);});select.value=Number.isInteger(authored.primary_source)?String(authored.primary_source):'';wrap.append(select);form.append(wrap);primarySource=select;}
  const ownsProof=typeof authored.proof?.text==='string'&&!!authored.proof.text.trim(),sourceProofText=!ownsProof&&record.proof?.status==='SOURCE_UNREVIEWED'?record.proof.text||'':'';
  const proof=area('proof','Proof or derivation',ownsProof?authored.proof.text:sourceProofText,7),limitations=area('limitations','Scope and limitations (one per line)',(authored.limitations||[]).join('\n'),3);
  if(sourceProofText)proof.parentElement?.append(el('small','From the linked proof source. Edit to create an authored version; leave unchanged to retain source attribution.','muted'));
  const note=el('p','Saving authored mathematics does not mark the claim verified. Proof status comes from its linked evidence.','muted');form.append(note);
  const save=el('button','Save mathematical record','primary'),status=el('p','','work-status');save.type='submit';form.append(save,status);form.oninput=()=>onDirty(true);
  form.onsubmit=async event=>{event.preventDefault();save.disabled=true;status.textContent='Saving…';try{const assumptionValues=[...rows.children].map(row=>({text:row.querySelector('textarea').value,...(row.querySelector('input').value.trim()?{node_id:row.querySelector('input').value.trim()}:{})})).filter(row=>row.text.trim());const statementChanged=statement.value!==sourceStatementText,proofChanged=proof.value!==sourceProofText;const value={...(statement.value.trim()&&(ownsStatement||statementChanged)?{statement_tex:statement.value}:{}),...(domain.value.trim()?{domain:domain.value}:{}),...(none.checked?{assumptions:[]}:assumptionValues.length?{assumptions:assumptionValues}:{}),...(proof.value.trim()&&(ownsProof||proofChanged)?{proof:{text:proof.value}}:{}),sources:authored.sources||[],...(primarySource&&primarySource.value!==''?{primary_source:Number(primarySource.value)}:!primarySource&&Number.isInteger(authored.primary_source)?{primary_source:authored.primary_source}:{}),formal_targets:authored.formal_targets||[],limitations:limitations.value.split('\n').map(line=>line.trim()).filter(Boolean)};await request('/concepts/change',{project,node:node.id,operation:'set_mathematics',...conceptChangeGuard(state,node.id,'set_mathematics'),value,by:'author'});onDirty(false);status.textContent='Mathematical record saved.';await onSaved();}catch(error){status.textContent=error.message;status.classList.add('error');}finally{save.disabled=false;}};
  return details;
}
