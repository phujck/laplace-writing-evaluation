// THE RESEARCH RESULT CARD. Purpose: paint one recorded research result (values, measurement
// table, visual readiness and placement, provenance, evidence role) from the research owner's
// read. Ownership: /research/state and the visual specs own values, currentness and readiness;
// this module formats (formatValue, measurementTable, renderMeasurementValue) and never asserts
// truth. Public contract: renderResearchCard(host, value, options), visualRenderState,
// renderVisualReadiness, visualRepairPrompt, visualPlacementReason, researchEvidenceRole,
// ensureResearchCardStyles (loads research-card.css once). Inputs: one result; outputs: DOM.
// Currentness: recomputed by the owner only when read (plan §5 research). Errors: a missing
// render or spec is named with its repair prompt. Consumers: concept-explorer.mjs,
// writing-evidence.mjs. Controls: research:result (in writing-evidence). Storage: none.
import {openPdf} from '/shared/writing-pdf.mjs';
import {scientificLimitations} from '/shared/concept-reader.mjs';

const e=(tag,text='',cls='')=>{const n=document.createElement(tag);n.textContent=text;n.className=cls;return n;};
const firstLine=value=>String(value||'').split('\n')[0].trim();
const statusClass=value=>'research-status research-status--'+String(value||'unknown').toLowerCase().replace(/[^a-z0-9]+/g,'-');

export function ensureResearchCardStyles(){
  if(document.querySelector('link[data-research-card-styles]'))return;
  const link=document.createElement('link');link.rel='stylesheet';link.href='/shared/research-card.css';link.dataset.researchCardStyles='';document.head.append(link);
}

export function visualRenderState(spec={}){
  const readiness=spec.render_readiness,blocked=readiness?.can_render===false;
  const issues=blocked?(readiness.issues||[]).map(issue=>({field:String(issue.field||''),reason:String(issue.reason||'')})).filter(issue=>issue.reason):[];
  return {blocked,issues,reason:issues.map(issue=>(issue.field?issue.field+': ':'')+issue.reason).join('; ')||(blocked?'The figure owner reports that this brief is not ready to render.':'')};
}
export function renderVisualReadiness(host,spec){
  const state=visualRenderState(spec);if(!state.blocked)return state;
  const box=e('div','','visual-render-readiness');box.setAttribute('role','status');
  box.append(e('p',spec.render_readiness.status==='INCOMPLETE'?'Complete this figure brief before rendering.':'This figure cannot render from its current inputs.'));
  if(state.issues.length){const list=e('ul');for(const issue of state.issues)list.append(e('li',(issue.field?issue.field+': ':'')+issue.reason));box.append(list);}else box.append(e('p',state.reason));host.append(box);return state;
}
export function visualRepairPrompt(spec={}){
  const state=visualRenderState(spec),name=spec.title||spec.id;
  return `${state.blocked?'Complete and render':'Revise'} existing figure ${spec.id} (${name}). Read its current brief and spec_revision, authored manuscript use, bound results and scientific source first. ${state.reason?'The figure owner reports: '+state.reason+'. ':''}Use the existing visual_create/visual_render help and guarded owner to update this same figure ID, then render and inspect the result. Preserve any existing placement and avoid a duplicate figure or placement.`;
}
export function visualPlacementReason(spec={}){
  if(!spec.render)return 'Render the completed figure brief before placing it.';
  const drawing=spec.render_freshness||spec.currentness?.status,basis=spec.currentness?.evidence_binding_status;
  if(drawing&&drawing!=='CURRENT')return 'Render the current drawing inputs before placing this figure.';
  if(basis&&!['CURRENT','THEORY_ONLY'].includes(basis))return 'Review the figure’s current evidence binding before placement.';
  return '';
}

const numericFormats=new Map();
export function formatValue(value){
  const number=v=>{const scientific=Number.isFinite(v)&&v!==0&&(Math.abs(v)<1e-4||Math.abs(v)>=1e7);if(!numericFormats.has(scientific))numericFormats.set(scientific,new Intl.NumberFormat('en-GB',{maximumSignificantDigits:6,...(scientific?{notation:'scientific'}:{})}));return numericFormats.get(scientific).format(v);};
  if(value==null)return 'Unavailable';
  if(Array.isArray(value))return value.every(item=>item==null||typeof item!=='object')?'('+value.map(v=>typeof v==='number'?number(v):String(v)).join(', ')+')':value.length+' structured values';
  if(typeof value==='number')return number(value);
  if(typeof value==='boolean')return value?'Yes':'No';
  return typeof value==='object'?Object.keys(value).length+' fields':String(value);
}
const scalar=value=>value==null||['number','string','boolean'].includes(typeof value);
export function measurementTable(value,{maxRows=32,maxColumns=12}={}){
  if(Array.isArray(value)&&value.length){
    const shown=value.slice(0,maxRows);
    if(shown.every(row=>row&&typeof row==='object'&&!Array.isArray(row))){const keys=Object.keys(shown[0]);if(keys.length&&shown.every(row=>Object.keys(row).length===keys.length&&keys.every(key=>Object.hasOwn(row,key)&&scalar(row[key]))))return {columns:keys.slice(0,maxColumns),rows:shown.map(row=>keys.slice(0,maxColumns).map(key=>row[key])),rowsTotal:value.length,rowsOmitted:Math.max(0,value.length-shown.length),columnsOmitted:Math.max(0,keys.length-maxColumns)};}
    if(value.length>8&&shown.every(scalar))return {columns:['Index','Value'],rows:shown.map((item,index)=>[index+1,item]),rowsTotal:value.length,rowsOmitted:Math.max(0,value.length-shown.length),columnsOmitted:0};
  }
  if(value&&typeof value==='object'&&!Array.isArray(value)&&Object.values(value).every(scalar)){const entries=Object.entries(value);return {columns:['Field','Value'],rows:entries.slice(0,maxRows),rowsTotal:entries.length,rowsOmitted:Math.max(0,entries.length-maxRows),columnsOmitted:0};}
  return null;
}
export function renderMeasurementValue(host,value,{exact=false,label='Structured measured values'}={}){
  let shortened=false;const plain=item=>{const text=item==null?'Unavailable':typeof item==='object'?formatValue(item):exact?String(item):formatValue(item);if(!exact&&typeof item==='string'&&text.length>240){shortened=true;return text.slice(0,239)+'…';}return text;},table=measurementTable(value),note=()=>{if(shortened)host.append(e('p','Long text values are shortened here; open Exact recorded values to read them.','writing-muted'));};
  if(table){const frame=e('div','','research-measure-table-scroll');frame.tabIndex=0;frame.setAttribute('aria-label',label);const data=e('table','','research-structured-values');data.setAttribute('aria-label',label);const head=e('thead'),row=e('tr');for(const key of table.columns){const th=e('th',key);th.scope='col';row.append(th);}head.append(row);data.append(head);const body=e('tbody');for(const values of table.rows){const row=e('tr');for(const value of values){const cell=e('td',plain(value));cell.title=String(value??'Unavailable');row.append(cell);}body.append(row);}data.append(body);frame.append(data);host.append(frame);if(table.rowsOmitted||table.columnsOmitted)host.append(e('p',`${table.rows.length} of ${table.rowsTotal} returned rows shown`+(table.columnsOmitted?` · ${table.columnsOmitted} columns omitted`:'')+'. Open the result file for complete data.','writing-muted'));note();return;}
  if(scalar(value)||Array.isArray(value)&&value.every(scalar)&&value.length<=8){host.textContent=Array.isArray(value)?'('+value.map(plain).join(', ')+')':plain(value);note();return;}
  // Irregular bounded JSON remains readable as named fields, never a JSON dump.
  let budget=48;const tree=(node,item,depth=0)=>{if(budget--<=0){node.append(e('p','Additional returned values omitted from this preview. Open the result file for complete data.','writing-muted'));return;}if(scalar(item)){node.append(e('span',plain(item)));return;}if(depth>=3){node.append(e('span',formatValue(item)+' · nested values; inspect the result file.'));return;}const list=e('dl','','research-measure-fields'),entries=Array.isArray(item)?item.map((value,index)=>['Item '+(index+1),value]):Object.entries(item);for(const [key,value]of entries){if(budget<=0){list.append(e('dt','More'),e('dd',(entries.length-list.children.length/2)+' fields omitted from this preview.'));break;}list.append(e('dt',key));const cell=e('dd');tree(cell,value,depth+1);list.append(cell);}node.append(list);};tree(host,value);note();
}

export function researchEvidenceRole(record,file){
  const role=file.role||file.label||'Evidence',scope=file.scope||record.scope||'manuscript';
  if(role!=='Input data'||scope!==(record.scope||'manuscript')||!(record.data||[]).includes(file.path))return role;
  return scope===(record.producer?.scope||'manuscript')&&(record.producer?.dependencies||[]).includes(file.path)?'Producer input':'Data file';
}

function exactMetadata(record){
  const dl=e('dl','','research-identities');
  const add=(term,value)=>{if(value==null||value==='')return;dl.append(e('dt',term),e('dd',String(value)));};
  add('Record',record.id);add('Revision',record.revision);add('Scope',record.scope||'manuscript');
  add('Scientific review',record.scientific_review||'Not recorded');
  add('Recorded',record.provenance?.recorded_at?new Date(record.provenance.recorded_at*1000).toLocaleString():'');
  add('Execution',record.run_id);return dl;
}

function limitationsView(value,{prefix=''}={}){
  const view=scientificLimitations(value);if(view.kind==='list'){if(!view.items.length)return null;const box=e('div','','research-limitations'),list=e('ul');for(const item of view.items)list.append(e('li',item));box.append(list);return box;}
  if(view.kind==='prose')return e('p',prefix+view.text,'research-limitations');
  return null;
}

function artifactUrl(project,artifact,preview=false){
  if(artifact.visual_id)return '/visuals/asset?'+new URLSearchParams({project,id:artifact.visual_id,format:preview?'png':'pdf',inspect:'1'});
  const params=new URLSearchParams({project,path:artifact.path,scope:artifact.scope||'manuscript'});
  if(preview&&/\.pdf$/i.test(artifact.path||''))params.set('preview','png');
  return '/research/artifact?'+params;
}

function figureGallery(card,record,project,action){
  const declared=(record.artifacts||[]).filter(a=>/\.(pdf|png|jpe?g|webp|svg)$/i.test(a.path||''));
  const linked=(record.linked_figures||[]).flatMap(binding=>binding.figure?.artefact?[{
    path:binding.figure.artefact,scope:'manuscript',label:binding.figure.label||binding.figure_id,
    caption:binding.figure.promise,binding_id:binding.binding_id,
  }]:[]);
  const specFigures=(record.linked_visuals||[]).filter(visual=>visual.rendered);
  const seen=new Set(),figures=[...declared,...linked,...specFigures].filter(item=>{const identity=item.visual_id||item.path;return item.path&&!seen.has(identity)&&seen.add(identity);});
  if(!figures.length)return new Set();
  const render=(host,rows)=>{const gallery=e('div','','research-gallery');
    for(const figure of rows){
      const item=e('figure'),isPdf=/\.pdf$/i.test(figure.path),full=artifactUrl(project,figure,false);
      if(figure.status)item.append(e('span',figure.status,statusClass(figure.status)));
      const open=action('Open '+(figure.label||'figure'),()=>isPdf?openPdf(full,figure.label||record.title,{notice:figure.status&&figure.status!=='CURRENT'?'This figure is available for inspection; its recorded render is '+figure.status.toLowerCase()+'. Review its source and evidence before relying on it.':''}):window.open(full,'_blank','noopener'));
      open.className='research-figure-open';open.setAttribute('aria-label','Open full '+(figure.label||'figure'));open.textContent='';
      const img=e('img');img.alt=figure.caption||figure.label||record.title||'Research figure';img.loading='lazy';
      img.src=artifactUrl(project,figure,true)+'&v='+encodeURIComponent(record.revision||'');
      img.onerror=()=>img.replaceWith(e('p','Preview unavailable. Open the full figure to inspect it.','writing-muted'));
      open.append(img);item.append(open,e('figcaption',figure.caption||figure.label||'Recorded figure'));
      const link=e('a',isPdf?'Open vector PDF':'Open full image');link.href=full;link.target='_blank';link.rel='noopener';item.append(link);gallery.append(item);
    }host.append(gallery);};
  render(card,figures.slice(0,1));
  if(figures.length>1){const rest=e('details','','research-more-figures');rest.append(e('summary',`${figures.length-1} more figures`));rest.ontoggle=()=>{if(rest.open&&!rest.dataset.rendered){rest.dataset.rendered='true';render(rest,figures.slice(1));}};card.append(rest);}
  return new Set(figures.map(figure=>figure.path));
}

export function renderResearchCard(host,record,{
  project,inspect,bind,work,onInspectResult,onDiscussResult,onOpenUsage,onError=()=>{},
}={}) {
  ensureResearchCardStyles();
  const card=e('article','','writing-card research-result');card.dataset.researchId=record.id||'';card.tabIndex=-1;
  const action=(label,fn,cls='')=>{const b=e('button',label,cls);b.type='button';b.onclick=async()=>{b.disabled=true;try{await fn();}catch(error){onError(error.message);}finally{b.disabled=false;}};return b;};
  const header=e('header','','research-result__header'),heading=e('div');
  heading.append(e('p',record.kind==='experiment'?'Experiment':'Result','research-kicker'),e('h4',record.title||record.id));
  // the result card header (M5 C9): kind eyebrow, title, the currentness word as a state chip
  const state=e('span',String(record.currentness||'UNKNOWN').toLowerCase().replaceAll('_',' '),'state-chip '+statusClass(record.currentness));state.setAttribute('data-tone',({CURRENT:'ok',STALE:'attention',CHANGED_INPUT:'attention',UNAVAILABLE:'blocked',MISSING:'blocked'})[record.currentness]||'neutral');state.title='File provenance; scientific interpretation is in the record below.';header.append(heading,state);card.append(header);

  const argument=e('div','','research-argument');
  if(record.question)argument.append(e('p','Question','research-label'),e('p',record.question,'research-question'));
  if(record.summary)argument.append(e('p',record.kind==='experiment'?'Purpose':'Finding','research-label'),e('p',record.summary,'research-summary'));
  else if(record.kind==='result')argument.append(e('p','Finding','research-label'),e('p','No interpretation has been recorded for this result.','research-missing'));
  if(argument.children.length)card.append(argument);

  const provenance=e('div','','research-currentness');
  const currentText=record.currentness==='CURRENT'?'Recorded files match their pinned identities':record.currentness==='STALE'?'Recorded files or execution inputs have changed':'Input provenance has not been established';
  provenance.append(e('strong',currentText),e('p',record.currentness_reason||'', 'writing-muted'));
  if(record.run){const run=e('p','','research-run-state');run.append(e('span','Execution '+(record.run.state||'UNKNOWN'),statusClass(record.run.state)),document.createTextNode(record.run.mode?' · '+record.run.mode+' mode':''));provenance.append(run);}
  provenance.append(e('p','Current provenance describes file identity and execution state; it does not establish scientific truth.','research-truth-note'));

  if(record.measurements?.length){
    const table=e('table','','research-measures');table.append(e('caption','Measured values'));
    const head=e('thead'),hr=e('tr');hr.append(e('th','Measure'),e('th','Value'),e('th','Unit'));head.append(hr);table.append(head);
    const body=e('tbody');
    for(const measure of record.measurements){const row=e('tr'),value=e('td');renderMeasurementValue(value,measure.value,{label:measure.label||measure.key});const label=e('th',measure.label||measure.key);label.scope='row';row.append(label,value,e('td',measure.unit||'not stated',measure.unit?'':'research-unit-missing'));body.append(row);}
    table.append(body);card.append(table);const exact=e('details','','research-exact-values');exact.append(e('summary','Exact recorded values'));let rendered=false;exact.ontoggle=()=>{if(!exact.open||rendered)return;rendered=true;const values=e('dl','','research-identities');for(const measure of record.measurements){values.append(e('dt',measure.label||measure.key));const value=e('dd');renderMeasurementValue(value,measure.value,{exact:true,label:'Exact '+(measure.label||measure.key)});if(measure.unit)value.append(document.createTextNode(' '+measure.unit));values.append(value);}exact.append(values);};card.append(exact);
  }

  const figurePaths=figureGallery(card,record,project,action);
  if(record.linked_visuals?.length){const visuals=e('section','','research-linked-visuals');visuals.append(e('h5','Figure provenance'));for(const visual of record.linked_visuals){const drawing=visual.status||'UNKNOWN',basis=visual.evidence_binding_status||visual.result_currentness||'UNLINKED',metadata=visual.presentation_status||'UNKNOWN';visuals.append(e('p',`${visual.label||visual.visual_id} · drawing ${drawing.toLowerCase()}, evidence ${basis.toLowerCase()}, metadata ${metadata.toLowerCase()}${visual.rendered?'':' · render pending'}`,'research-visual-summary'));const changes=[...(visual.changed_dependencies||[]),...(visual.basis_changes||[]),...(visual.metadata_changes||[])];if(changes.length){const detail=e('details','','research-trail');detail.append(e('summary','Inspect figure provenance'));for(const change of changes)detail.append(e('p',change.reason||change.state,'writing-muted'));visuals.append(detail);}}card.append(visuals);}
  if(record.interpretation)card.append(e('p','Interpretation','research-label'),e('p',record.interpretation,'research-interpretation'));
  const limitations=limitationsView(record.limitations);if(limitations)card.append(e('p','Limits','research-label'),limitations);
  if(record.provenance_limit)card.append(e('p',record.provenance_limit,'research-provenance-limit'));

  const files=[...(record.evidence_files||[]).map(file=>({...file,role:researchEvidenceRole(record,file)})),...(record.artifacts||[]).filter(a=>!figurePaths.has(a.path)).map(a=>({...a,role:a.label||a.role||'Artifact',declared_artifact:true}))];
  const fileMap=new Map(),filesByLocation=new Map(),filesByIdentity=new Map();for(const file of files){if(!file.path)continue;const scope=file.scope||record.scope||'manuscript',location=scope+':'+file.path,identity=file.identity||'',role=file.role||file.label||'Evidence',prior=(identity&&filesByIdentity.get(identity))||filesByLocation.get(location);if(prior){if(!prior.roles.includes(role))prior.roles.push(role);if(file.declared_artifact)prior.declared_artifact=true;continue;}const row={...file,scope,roles:[role]};fileMap.set(identity||location,row);filesByLocation.set(location,row);if(identity)filesByIdentity.set(identity,row);}const fileRows=[...fileMap.values()];
  const sourcePanels=e('div','','research-source-panels'),opened=new Map();
  const inspectOnce=(label,path,scope)=>async()=>{
    const key=scope+':'+path;if(opened.has(key)){const prior=opened.get(key);prior.open=true;prior.scrollIntoView({block:'nearest'});return;}
    if(!inspect)throw Error('Artifact inspection is unavailable in this view.');
    const panel=await inspect(sourcePanels,label,path,scope);if(panel)opened.set(key,panel);
  };
  const shortcuts=e('section','','research-source-shortcuts'),shortcutKeys=new Set();shortcuts.append(e('h5','Open the evidence'));
  const addFile=(label,file)=>{const scope=file.scope||record.scope||'manuscript',key=file.identity||scope+':'+file.path;if(shortcutKeys.has(key))return;shortcutKeys.add(key);const basename=file.path.replaceAll('\\','/').split('/').at(-1),name=label+' · '+basename,open=action(name,inspectOnce(name,file.path,scope),'research-source-action');open.title=scope+': '+file.path;open.setAttribute('aria-label',name+' ('+scope+')');shortcuts.append(open);};
  const hasRole=(file,role)=>(file.roles||[file.role]).includes(role);
  const code=fileRows.find(file=>hasRole(file,'Code'));if(code)addFile('Calculation code',code);
  const legacySource=!code&&fileRows.find(file=>hasRole(file,'Analysis source'));if(legacySource)addFile('Analysis source',legacySource);
  fileRows.filter(file=>hasRole(file,'Data file')).forEach(file=>addFile('Data file',file));
  const inputs=fileRows.filter(file=>['Configuration','Input data','Producer input'].some(role=>hasRole(file,role)));
  inputs.slice(0,4).forEach((file,index)=>addFile((index?'Input':'Inputs'),file));
  const visualInputs=[];for(const visual of record.linked_visuals||[]){const declared=(visual.input_files||[]).filter(file=>file.role==='Input data'&&file.status==='PRESENT');for(const file of declared)if(!visualInputs.some(item=>(item.identity||item.scope+':'+item.path)===(file.identity||file.scope+':'+file.path)))visualInputs.push(file);if(!declared.length&&visual.source_data&&!fileRows.some(file=>file.path===visual.source_data))visualInputs.push({path:visual.source_data,scope:visual.input_scope||'project'});}
  visualInputs.forEach((file,index)=>addFile(index?'Input':'Inputs',file));
  const outputs=fileRows.filter(file=>hasRole(file,'Recorded output'));
  outputs.slice(0,3).forEach((file,index)=>addFile((index?'Output':'Outputs'),file));
  const customArtifacts=fileRows.filter(file=>file.declared_artifact);
  customArtifacts.forEach(file=>addFile((file.roles||[file.label||file.role||'Artifact']).join(' · '),file));
  const diagramSources=[];
  for(const visual of record.linked_visuals||[]){
    const declared=(visual.input_files||[]).filter(file=>file.role==='Diagram source'&&file.status==='PRESENT');for(const file of declared)if(!diagramSources.some(item=>(item.identity||item.scope+':'+item.path)===(file.identity||file.scope+':'+file.path)))diagramSources.push(file);
    const path=visual.source;if(!declared.length&&path&&!fileRows.some(file=>file.path===path)&&!diagramSources.some(item=>item.path===path&&item.scope===(visual.input_scope||'project')))diagramSources.push({path,scope:visual.input_scope||'project'});
  }
  diagramSources.forEach(file=>addFile('Diagram source',file));
  if(!diagramSources.length&&(record.linked_visuals||[]).some(visual=>visual.kind==='diagram'))shortcuts.append(e('span','Diagram source · inline canonical visual specification','research-source-note'));
  if(shortcuts.children.length>1)card.append(shortcuts,sourcePanels);

  const support=e('section','','research-support');support.append(e('h5','Where this result is used'));
  if(record.usage?.length){
    const list=e('ul');
    for(const usage of record.usage){
      const item=e('li'),concept=usage.concept||{},label=firstLine(concept.label||concept.id);
      if(onOpenUsage)item.append(action(label,()=>onOpenUsage(usage),'research-link-button'));else item.append(e('span',label));
      if(usage.binding_revision&&record.revision&&usage.binding_revision!==record.revision)item.append(e('span',' Bound to a different result revision.','research-binding-warning'));
      const locations=usage.manuscript_locations||[];
      if(locations.length){const where=e('span',' Used in ');locations.forEach((location,index)=>{if(index)where.append(document.createTextNode(', '));if(onOpenUsage)where.append(action(location.title||location.id,()=>onOpenUsage({...usage,location}),'research-inline-link'));else where.append(document.createTextNode(location.title||location.id));});item.append(where);}
      else item.append(e('span',' Connected to the concept; not placed in the reader plan.','writing-muted'));
      list.append(item);
    }support.append(list);
  }else support.append(e('p',record.kind==='result'?'Not yet connected to a conceptric claim.':'No result-to-claim binding is expected for an experiment declaration.','writing-muted'));
  card.append(support);

  card.append(provenance);

  const details=e('details','','research-trail');details.append(e('summary','Inspect evidence trail'));
  if(fileRows.length){const fileList=e('div','','research-file-list');for(const file of fileRows){const label=(file.roles||[file.role||file.label||'Evidence']).join(' · '),row=e('div','','research-file');row.append(e('span',label+' ['+file.scope+']'),e('code',file.path),action('Open',inspectOnce(label,file.path,file.scope),'research-open-file'));fileList.append(row);}details.append(e('h5','Inputs, code and outputs'),fileList);}
  if(record.run){const run=e('section','','research-receipt');run.append(e('h5','Execution receipt'),exactMetadata({...record,id:record.run.id,revision:record.run.result_sha256,scope:record.run.mode,scientific_review:null,run_id:record.run.producer_id}));if(record.run.reason)run.append(e('p',record.run.reason,'writing-muted'));details.append(run);}
  const retired=record.dependency_coverage?.retired_derived_presentation_pins||[],retiredPaths=new Set(retired.map(dep=>(dep.scope||record.scope||'manuscript')+':'+dep.path));
  if(retired.length){const historical=e('section','','research-receipt');historical.append(e('h5','Historical downstream figures'));for(const dep of retired)historical.append(e('p',`${dep.path} · excluded from current numerical inputs; its drawing freshness is tracked with the linked visual.`,'writing-muted'));details.append(historical);}
  const dependencies=(record.provenance?.dependencies||[]).filter(dep=>!retiredPaths.has((dep.scope||record.scope||'manuscript')+':'+dep.path));
  const currentByPath=new Map((record.current_dependencies||[]).map(dep=>[dep.path,dep]));
  if(dependencies.length){const table=e('table','','research-dependencies');table.append(e('caption','Recorded and current file identities'));const head=e('thead'),hr=e('tr');hr.append(e('th','Path'),e('th','State'),e('th','Recorded SHA-256'),e('th','Current SHA-256'));head.append(hr);table.append(head);const body=e('tbody');for(const dep of dependencies){const current=currentByPath.get(dep.path),changed=!current||current.status!==dep.status||current.sha256!==dep.sha256;const row=e('tr');row.append(e('td',dep.path),e('td',changed?(current?.status==='MISSING'?'MISSING':'CHANGED'):(current?.status||dep.status||''),changed?'research-binding-warning':''),e('td',dep.sha256||'—'),e('td',current?.sha256||'—'));body.append(row);}table.append(body);details.append(table);}
  if(record.renewal_history?.length){const history=e('details','','research-history');history.append(e('summary',`${record.renewal_history.length} prior recorded ${record.renewal_history.length===1?'revision':'revisions'}`));for(const prior of [...record.renewal_history].reverse()){const row=e('article','','research-history__row');row.append(e('h6',prior.revision||'Unknown revision'));if(prior.archived_at)row.append(e('p','Archived '+new Date(prior.archived_at*1000).toLocaleString(),'writing-muted'));if(prior.summary)row.append(e('p',prior.summary));const priorLimits=limitationsView(prior.limitations,{prefix:'Limits: '});if(priorLimits)row.append(priorLimits);const identities=e('dl','','research-identities');for(const dep of prior.dependencies||[]){identities.append(e('dt',dep.path||'Dependency'),e('dd',(dep.status||'')+(dep.sha256?' · '+dep.sha256:'')));}if(identities.children.length)row.append(identities);history.append(row);}details.append(history);}
  details.append(e('h5','Record identity'),exactMetadata(record));card.append(details);

  const controls=e('div','','writing-actions research-primary-actions');
  if(record.result&&inspect)controls.append(action('Inspect full result',async()=>{details.open=true;await inspectOnce('Recorded output',record.result,record.scope||'manuscript')();}));
  if(onInspectResult)controls.append(action('Focus result',()=>onInspectResult(record)));
  if(bind&&record.kind==='result')controls.append(action(record.usage?.length?'Connect to another claim':'Connect to a claim',()=>bind(record),'primary'));
  const discuss=onDiscussResult||work;if(discuss)controls.append(action('Discuss this result',()=>discuss(record)));
  card.append(controls);
  host.append(card);return card;
}
