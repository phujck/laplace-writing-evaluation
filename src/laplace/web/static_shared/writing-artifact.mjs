// THE ARTIFACT INSPECTOR. Purpose: open one saved artifact (argument snapshot, visual, derived
// output, recorded source, restructure outcome, reader-plan guard subject, markdown) read-only
// from its exact owner read, with its links opened only through admitted owner coordinates.
// Ownership: each artifact's owner (artifact routes, derived-output, reader_restructure,
// reader_plan projection:guard) owns bytes and currentness; writing-owner-read admits links;
// this module paints and routes. Public contract: openArtifact(options) and the kind helpers
// (artifactKind, argumentSnapshot, recordedSource, recordedResultFiles, visualOutputs,
// checkArtifactPage, artifactURL; ARGUMENT_SCHEMA, VISUAL_SCHEMA, STRUCTURED_LIMIT bounds).
// Inputs: one path or handle; outputs: a dialog. Currentness: the response it was given; no
// second read for a guard subject. Errors: the owner's refusal inline; a foreign owner link
// refuses before any read. Storage: none.
import {mountDerivedOutput,sameDerivedTarget,sameBuildJob,sameBuildTarget} from './derived-output.mjs';
import {renderRestructureOutcome,renderMetadataReconciliation,inspectStructuralInput} from './reader-restructure.mjs';
import {renderReaderGuard} from './reader-state.mjs';
import {mountReaderPlan} from './workspace-spine.mjs';
import {renderEngineeringSupport} from './engineering-support.mjs';
import {ownerHumanTarget,conceptHumanTarget,qualifiedOwnerHTTP} from './writing-owner-read.mjs';
import {analyticsExactTarget,renderAnalyticsRecord} from './workspace-analytics.mjs';
import {mountOperatorWork,renderWorkNeighbourhood} from './workspace-work.mjs';
import {renderMaterialObservation} from './workspace-material-observation.mjs';
import {validateTemplateMetadata,renderTemplateCandidate,readTemplatePart,templateOutputURL} from './document-template.mjs';
import {sharedInspector,replacedByInspector,payloadCut} from './workspace-inspector.mjs';
import {pendingRead} from './pending-read.mjs';
// Read-only saved evidence. This adapter never selects/replaces the manuscript pane.
export const ARGUMENT_SCHEMA='writing-system-architecture.argument-map/1';
export const ARGUMENT_SCHEMA_V2='writing-system-architecture.argument-map/2';
const ARGUMENT_SCHEMAS=new Set([ARGUMENT_SCHEMA,ARGUMENT_SCHEMA_V2]);
export const VISUAL_SCHEMA='writing-system-architecture.visual-index/1';
export const STRUCTURED_LIMIT=2*1024*1024;
const RELATIONS=new Set(['prerequisite','support','counterevidence','validated_by','implementation','analogy','questions','unknown']);
const RELATION_LABELS={prerequisite:'requires',support:'draws documentary support from',counterevidence:'has counterevidence',validated_by:'is validated by',implementation:'is implemented by',analogy:'is analogous to',questions:'questions',unknown:'has an unresolved relation to'};
export const artifactURL=({project,path,scope='project',artifactId,artifactOwner},extra={})=>'/research/artifact?'+new URLSearchParams({project,path,scope,...(artifactId?{artifact_id:artifactId}:{}),...(artifactOwner?{owner:artifactOwner}:{}),...extra});
export function checkArtifactPage(page,offset,identity=null){
  if(!page||typeof page.content!=='string'||page.filtered||page.offset!==offset||
     !Number.isSafeInteger(page.total_chars)||page.total_chars<0||
     !Number.isSafeInteger(page.bytes)||page.bytes<0||!/^[a-f0-9]{64}$/i.test(page.sha256||''))
    throw Error('Invalid artifact page. Reopen the evidence or download the complete file.');
  const current={sha256:page.sha256,bytes:page.bytes,total_chars:page.total_chars,path:page.path,scope:page.scope};
  if(identity&&Object.keys(current).some(key=>current[key]!==identity[key]))
    throw Error('Artifact changed while reading. No mixed snapshot is displayed. Close and reopen it.');
  const end=offset+Array.from(page.content).length;
  if(end>page.total_chars||page.next_offset!==null&&page.next_offset!==end||
     page.next_offset===null&&end!==page.total_chars||page.next_offset!==null&&end<=offset)
    throw Error('Artifact continuation is invalid or incomplete. Reopen or download the file.');
  return current;
}
export async function readArtifact({request,project,path,scope='project',artifactId=null,artifactOwner=null,expectedSha256=null,onProgress=()=>{},alive=()=>true}){
  const ref={project,path,scope,artifactId,artifactOwner};let offset=0,identity=null,text='',page;
  do{
    if(!alive())throw Error('Reader closed.');
    page=await request(artifactURL(ref,{format:'json',offset,limit:32768,...(expectedSha256?{expected_sha256:digest(expectedSha256)}:{})}));
    if(!alive())throw Error('Reader closed.');
    identity=checkArtifactPage(page,offset,identity);
    if(identity.bytes>STRUCTURED_LIMIT)return {identity,text:page.content,complete:false,page,reason:'Structured preview is limited to 2 MiB. Continue as text or download the complete file.'};
    text+=page.content;offset=page.next_offset;onProgress(text.length,identity);
  }while(offset!==null);
  return {identity,text,complete:true,page};
}
export function artifactKind(value){
  if(ARGUMENT_SCHEMAS.has(value?.schema_version))return 'argument';
  if(value?.schema_version===VISUAL_SCHEMA)return 'visual-index';
  if(value?.schema_version==='laplace.research-result-detail/1')return 'result-detail';
  if(value?.schema_version==='laplace.research-records/1')return 'research-records';
  return 'generic';
}
// Validate the fields this declared representation actually renders. Other
// canonical/native shapes cannot become an empty saved-map support projection.
function validateArgumentFields(value,ids){
  const object=v=>v!==null&&typeof v==='object'&&!Array.isArray(v);
  const text=v=>typeof v==='string'&&v.trim().length>0;
  const fail=(field,reason)=>{throw Error('Incompatible argument snapshot: '+field+' '+reason+
    '. Correct the saved artifact to its declared schema; inspect the complete raw JSON or download.');};
  const optionalArray=(row,key,field)=>{
    if(Object.hasOwn(row,key)&&!Array.isArray(row[key]))fail(field,'must be an array');
    return row[key]||[];
  };
  for(const key of ['source_registry','results'])
    if(Object.hasOwn(value,key)&&!object(value[key]))fail(key,'must be a dictionary keyed by recorded identity');
  const bindings=optionalArray(value,'research_bindings','research_bindings');
  for(const [i,row]of bindings.entries())
    if(!object(row)||!text(row.claim)||!text(row.result))
      fail('research_bindings['+i+']','must contain claim and result identities');
  const claims=new Set(bindings.map(row=>row.claim));
  for(const [i,node]of value.nodes.entries()){
    const field='nodes['+i+'] ('+node.id+')';
    if(Object.hasOwn(node,'kind')&&!text(node.kind))fail(field+'.kind','must be an object kind');
    const sources=optionalArray(node,'sources',field+'.sources');
    if(sources.some(key=>!text(key)))fail(field+'.sources','must contain recorded source keys');
    const current=optionalArray(node,'sources_current',field+'.sources_current');
    if(current.length&&!sources.length)fail(field+'.sources','is required when sources_current declares support; no source keys were recorded');
    for(const key of sources){
      try{recordedSource(value,key);}catch(error){fail(field+'.sources',error.message);}
    }
    if(node.kind==='question'){
      if(!text(node.target)||!ids.has(node.target))fail(field+'.target','must identify a recorded target node');
      if(!['open','addressed','withdrawn'].includes(node.state))fail(field+'.state','must be open, addressed or withdrawn');
      if(!text(node.discharge))fail(field+'.discharge','must record the discharge condition');
    }
    const bindings=optionalArray(node,'result_bindings',field+'.result_bindings');
    if(bindings.length&&!claims.has(node.id))
      fail(field+'.result_bindings','has no corresponding declared research_bindings claim/result row');
  }
  for(const [i,chapter]of value.chapters.entries()){
    const field='chapters['+i+']';if(!object(chapter))fail(field,'must be an object');
    const nodes=optionalArray(chapter,'nodes',field+'.nodes');
    if(nodes.some(id=>!text(id)))fail(field+'.nodes','must contain object identities');
    if(nodes.length&&(!text(chapter.id)||!text(chapter.source)))fail(field,'must identify its chapter and source for recorded placements');
  }
  if(Object.hasOwn(value,'mechanism_source')&&!object(value.mechanism_source))fail('mechanism_source','must be an object');
  if(value.mechanism_source?.sections&&!object(value.mechanism_source.sections))fail('mechanism_source.sections','must be a dictionary');
  for(const key of Object.keys(value.source_registry||{})){
    if(!object(value.source_registry[key]))fail('source_registry.'+key,'must be a source object');
    try{recordedSource(value,key);}catch(error){fail('source_registry.'+key,error.message);}
  }
  for(const key of Object.keys(value.mechanism_source?.sections||{})){
    try{recordedSource(value,'@'+key);}catch(error){fail('mechanism_source.sections.'+key,error.message);}
  }
  const documentary=optionalArray(value,'documentary_bindings','documentary_bindings');
  for(const [i,row]of documentary.entries())
    if(!Array.isArray(row)||row.length!==4||row.some(item=>!text(item)))
      fail('documentary_bindings['+i+']','must contain claim, source key, reference and reading receipt');
  for(const [id,result]of Object.entries(value.results||{})){
    const field='results.'+id;if(!object(result))fail(field,'must be a result object');
    optionalArray(result,'dependencies',field+'.dependencies');
    const limitations=optionalArray(result,'limitations',field+'.limitations');
    if(limitations.some(item=>typeof item!=='string'))fail(field+'.limitations','must contain text');
    try{if(result.output_sha256!=null)digest(result.output_sha256);recordedResultFiles(result);}catch(error){fail(field,error.message);}
  }
}
export function argumentSnapshot(value,project,identity){
  if(!ARGUMENT_SCHEMAS.has(value?.schema_version)||value.project!==project||
     !Array.isArray(value.nodes)||!Array.isArray(value.relations)||!Array.isArray(value.chapters))
    throw Error('Invalid argument snapshot schema or project. Raw JSON remains available.');
  if(value.nodes.length>2000||value.relations.length>10000||value.chapters.length>500)
    throw Error('Argument exceeds the bounded viewer limits. Use the exact JSON download.');
  const ids=new Set();
  for(const node of value.nodes){
    if(!node||typeof node.id!=='string'||!node.id||ids.has(node.id))throw Error('Argument snapshot contains a missing or duplicate object identity.');
    ids.add(node.id);
  }
  validateArgumentFields(value,ids);
  const relations=value.relations.map(row=>{
    if(!Array.isArray(row)||row.length!==3||row.some(x=>typeof x!=='string')||!RELATIONS.has(row[1]))
      throw Error('Argument snapshot has an unsupported typed relation. No inferred prerequisite was drawn.');
    return {source:row[0],rel:row[1],target:row[2]};
  });
  // The renderer consumes dependent -> prerequisite, and labels its drawn
  // prerequisite -> dependent projection explicitly. No citation enters this DAG.
  const byId=new Map(value.nodes.map(n=>[n.id,n]));
  const edges=relations.filter(r=>r.rel==='prerequisite').map(r=>{
    if(!ids.has(r.source)||!ids.has(r.target)||byId.get(r.target).kind==='citation')
      throw Error('A prerequisite has an absent or citation endpoint. Inspect the recorded JSON.');
    return {from:r.source,to:r.target};
  });
  const rootId='view:recorded-argument';
  if(ids.has(rootId))throw Error('Snapshot object collides with the display-only root.');
  return {identity,rootId,nodes:[{id:rootId,kind:'paper',title:'Recorded argument',members:[...ids]},
    ...value.nodes.map(n=>({...n,label:n.title||n.id,parent:rootId,members:[]}))],
    edges,relations,obligations:value.nodes.filter(n=>n.kind==='question').map(n=>({
      id:n.id,meaning:n.title||n.id,state:n.state,target:{kind:'node',node_id:n.target}})),
    diagnostics:[],recorded:value};
}

function digest(value){
  if(typeof value!=='string'||!/^(?:sha256:)?[a-f0-9]{64}$/i.test(value))throw Error('Recorded SHA-256 identity is missing or invalid.');
  return value.replace(/^sha256:/i,'').toLowerCase();
}
export function recordedSource(value,key){
  if(typeof key!=='string')throw Error('Recorded source key must be text.');
  let source;
  if(key.startsWith('@')){
    const section=key.slice(1),mechanism=value.mechanism_source;
    if(!mechanism||!Object.hasOwn(mechanism.sections||{},section))return null;
    source={path:mechanism.path,sha256:mechanism.sha256,scope:'project',lines:mechanism.sections[section]};
  }else source=value.source_registry?.[key];
  if(!source)return null;
  if(typeof source.path!=='string'||!source.path)throw Error('Recorded source path is missing: '+key);
  const scope=source.scope||'project';if(!['project','manuscript'].includes(scope))throw Error('Unsupported recorded source scope.');
  const range=source.lines||null;
  if(range&&(!Array.isArray(range)||range.length!==2||!range.every(Number.isSafeInteger)||range[0]<1||range[1]<range[0]))
    throw Error('Invalid recorded source range: '+key);
  return {...source,scope,sha256:digest(source.sha256),lineRange:range};
}
export function recordedResultFiles(result){
  if(!Array.isArray(result?.dependencies))return [];
  if(result.dependencies.length>200)throw Error('Recorded result dependency list exceeds the viewer bound.');
  const output=result.output_sha256?digest(result.output_sha256):null;
  return result.dependencies.map(file=>{
    if(!file||typeof file.path!=='string'||!file.path)throw Error('Recorded result dependency path is missing.');
    // argument-map/1 result dependencies inherit manuscript scope unless
    // the dependency itself declares project scope, as in canonical records.
    const scope=file.scope||'manuscript';if(!['project','manuscript'].includes(scope))throw Error('Unsupported recorded result scope.');
    const sha256=file.sha256?digest(file.sha256):null;
    return {...file,scope,sha256,role:sha256&&sha256===output?'recorded output':'recorded input/source'};
  });
}
export function visualOutputs(figure){
  const render=figure?.render;
  if(!render||!Array.isArray(render.outputs))throw Error('Visual has no supported recorded output array: '+(figure?.id||'unknown'));
  if(render.outputs.length>32)throw Error('Visual output list exceeds the viewer bound.');
  const paths=render.outputs,objects=paths.every(p=>p&&typeof p==='object'&&!Array.isArray(p)),strings=paths.every(p=>typeof p==='string');
  if(!strings&&!objects)throw Error('Mixed or unknown visual output representation. Inspect raw JSON.');
  const map=render.output_digests;
  if(strings&&paths.length&&(!map||typeof map!=='object'||Array.isArray(map)))throw Error('String output paths require their recorded output_digests map.');
  const seen=new Set();
  return paths.map(entry=>{
    // Current visual-index/1 mirrors visual_render: paths are manuscript-relative
    // and output_digests is keyed by the EXACT same path. The earlier retained
    // variant uses {path,scope,format,sha256} records. No other key is guessed.
    const path=strings?entry:entry.path;
    if(typeof path!=='string'||!path||seen.has(path))throw Error('Missing or duplicate visual output path.');
    seen.add(path);
    const format=path.split('.').at(-1).toLowerCase();
    if(!['pdf','svg','png','jpg','jpeg','tikz'].includes(format))throw Error('Unsupported recorded visual output format: '+path);
    const scope=strings?'manuscript':entry.scope;
    if(!['project','manuscript'].includes(scope)||!strings&&entry.format!==format)throw Error('Visual output format/scope contradicts its declared representation.');
    if(strings&&(/^(?:[a-z]:|[\\/])/i.test(path)||path.split(/[\\/]/).includes('..')))throw Error('Current visual output paths must be manuscript-relative.');
    const sha256=digest(strings?map[path]:entry.sha256);
    if(!strings&&map&&Object.hasOwn(map,path)&&digest(map[path])!==sha256)throw Error('Conflicting recorded visual output digests.');
    return {path,scope,format,sha256};
  });
}
// Inline research-card inspectors cache a truthy returned panel. Removable
// dialogs deliberately return no cacheable panel through this callback.
export async function inspectArtifactDialog(options){await openArtifact(options);}
let artifactReaderSequence=0;

const el=(tag,text='',cls='')=>{const n=document.createElement(tag);n.textContent=text;n.className=cls;return n;};
const button=(label,fn)=>{const b=el('button',label);b.type='button';b.onclick=fn;return b;};
async function defaultRequest(url,_payload,{allowStateError=false}={}){const r=await fetch(url);const v=await r.json();if(!r.ok||v.error&&!allowStateError)throw Error(v.error||'Evidence request failed ('+r.status+').');return v;}
function styles(){
  if(document.querySelector('link[data-writing-artifact]'))return;
  const link=document.createElement('link');link.rel='stylesheet';link.href='/shared/writing-artifact.css';link.dataset.writingArtifact='';document.head.append(link);
}
// THE READING DOOR. Every artifact and owner read opens here and is adopted by the one
// inspector (workspace-inspector.mjs) before it is shown: the PDF shortcut hands the same
// `onOpen` to openPdf, which adopts at its own door; nested reads re-enter this door bound to
// this panel's lineage. The reopen descriptor is this door's own arguments without opener /
// onOpen; a reopen from the trail receives the entry's PIN (the exact owner URL + cut this
// panel displayed) and renders that snapshot as "Previously inspected · HH:MM" with Read
// current and exact provenance on demand. Artifact bytes, PDFs and live build status are
// always re-read; a first read never consults the cache.
// the reopen factory and the nested opener live at module level: neither closes over a door's
// render scope. A nested opener carries explicit coordinates, the stable services and the
// door's lifetime handle {token}; a PDF viewer may retain it in its reopen arguments safely.
const reopenArtifact=(args,pin)=>openArtifact({...args,fromTrail:true,snapshotPin:pin||null});
const nestedOpener=(project,request,renderMarkdown,lineage)=>(p,l,o={})=>openArtifact({project:o.project||project,path:p,label:l,scope:o.scope||'project',notice:o.notice||'',expectedSha256:o.expectedSha256||null,artifactId:o.artifactId||null,artifactOwner:o.artifactOwner||null,lineRange:o.lineRange||null,request,renderMarkdown,isCurrent:lineage});
export async function openArtifact(options){
  let {project,path,label=path,scope='project',notice='',request=defaultRequest,renderMarkdown=null,expectedSha256=null,artifactId=null,artifactOwner=null,lineRange=null,ownerRead=null,opener=null,backRead=null,workEvidence=false,consumedRevision=null,completeReading=false,isCurrent=()=>true,onOpen=null,onReadError=()=>{},fromTrail=false,snapshotPin=null,host=null,onClose=()=>{}}=options;
  if(!isCurrent())return;
  const inspector=sharedInspector();const lifetime={token:null};
  const {opener:_opener,onOpen:_onOpen,isCurrent:_isCurrent,onReadError:_onReadError,host:_host,onClose:_onClose,...reopenArgs}=options;   // plain args: no DOM, no caller bookkeeping, no currency callback
  const adopt=dialog=>{if(host){onOpen?.(dialog);return;}lifetime.token=inspector.adopt(dialog,{kind:ownerRead?'owner-read':'artifact',title:label||path||'Reading',reopen:{factory:reopenArtifact,args:reopenArgs}}).token;onOpen?.(dialog);};
  if(ownerRead){if(ownerRead.http?.method!=='GET')throw Error('An explicit GET owner read is required.');ownerRead=ownerHumanTarget(ownerRead.http.url);if(!ownerRead)throw Error('The selected owner read coordinates are invalid.');project=ownerRead.project;path=ownerRead.http.url;label=label||'Owner reading';}
  if(!project||typeof path!=='string'||!path||!['project','manuscript'].includes(scope))throw Error('An exact project artifact and scope are required.');
  const ref={project,path,scope,artifactId,artifactOwner},pin=expectedSha256?digest(expectedSha256):null,url=ownerRead?ownerRead.http.url:artifactURL(ref,pin?{expected_sha256:pin}:{});
  if(!host&&/\.pdf$/i.test(path)){const {openPdf}=await import('/shared/writing-pdf.mjs');return openPdf(url,label,{notice:[notice,pin?'Recorded PDF SHA256 '+pin+'; media reads and download are hash-guarded.':'Current PDF file; no recorded byte identity requested.'].filter(Boolean).join(' '),onOpen,onOpenArtifact:(p,l,o={})=>openArtifact({project,path:p,label:l,request,renderMarkdown,...o})});}
  // owner JSON reads go through the inspector snapshot rule; live build status never does.
  // A reopen from the trail renders the PINNED url+cut only (never another cut of the URL).
  let snapshotBasis=null,dialog=null;
  const readOwner=async(ownerURL,readOptions={},{live=false}={})=>{snapshotBasis=null;if(fromTrail&&!live&&snapshotPin&&snapshotPin.url===ownerURL){const hit=inspector.snapshot(ownerURL,snapshotPin.cut);if(hit){snapshotBasis=hit;inspector.pin(lifetime,{url:hit.url,cut:hit.cut});return structuredClone(hit.value);}}const value=await request(ownerURL,undefined,readOptions);if(!live){inspector.remember(ownerURL,value);inspector.pin(lifetime,{url:ownerURL,cut:payloadCut(value)});}return value;};
  styles();const originNode=opener||document.activeElement,originRef=typeof WeakRef==='function'&&originNode?new WeakRef(originNode):{deref:()=>originNode};dialog=el(host?'section':'dialog','',host?'evidence-artifact artifact-hosted':'workspace-dialog evidence-artifact');
  const heading=el(host?'h3':'h2',label),status=pendingRead(el('p','Reading evidence…','artifact-status')),controls=el('nav','','writing-actions'),reading=el('section','','artifact-reading-region'),body=el('div','','artifact-body');
  const readerId='evidence-artifact-'+(++artifactReaderSequence);
  heading.id=readerId+'-title';dialog.setAttribute('aria-labelledby',heading.id);
  status.id=readerId+'-status';status.setAttribute('role','status');status.setAttribute('aria-live','polite');status.setAttribute('aria-atomic','true');
  reading.tabIndex=0;reading.setAttribute('role','region');reading.setAttribute('aria-label','Evidence reading');
  body.setAttribute('aria-busy','true');
  const announce=(message,error=false)=>{status.textContent=message;status.className=error?'error':'artifact-status';status.setAttribute('role',error?'alert':'status');status.setAttribute('aria-live',error?'assertive':'polite');};
  const raw=el('pre','','artifact-raw');raw.hidden=true;let closed=false,loaded=null,graph=null,rawPage=null,pendingMedia=false,currentPanel=null,currentGeneration=0,ownerController=null;
  const alive=()=>{if(closed)return false;if(!isCurrent()||!dialog.isConnected){dialog.close();return false;}return true;};
  const safe=fn=>async()=>{try{await fn();}catch(e){if(alive()){announce(e.message,true);}}};
  const nested=nestedOpener(project,request,renderMarkdown,host?()=>alive():inspector.lineage(lifetime));   // module-level: retains no render scope
  const download=el('a',ownerRead?'Exact owner read route':pin?'Download recorded bytes':'Download current file (unverified)');download.href=ownerRead?url:artifactURL(ref,{download:1,...(pin?{expected_sha256:pin}:{})});if(!ownerRead)download.download=path.split('/').at(-1);else{download.target='_blank';download.rel='noopener noreferrer';}
  const closeReading=button(host?'Change source':'Close',()=>dialog.close());closeReading.setAttribute('aria-label',host?'Change source':'Close this reading and return to where it was opened');controls.append(download);const exact=host?el('details','','artifact-host-details'):null;
  if(host){const top=el('header','','artifact-host-heading');top.append(heading,closeReading);exact.append(el('summary','Reading details and actions'),controls);dialog.append(top,status,reading,exact);}else{controls.append(closeReading);dialog.append(heading,status,controls,reading);}
  if(notice)(exact||reading).append(el('p',notice,'artifact-identity-notice'));reading.append(body,raw);const scrollOwners=[];for(let node=originNode;node;node=node.parentElement)if(node.scrollTop||node.scrollLeft)scrollOwners.push([typeof WeakRef==='function'?new WeakRef(node):{deref:()=>node},node.scrollTop,node.scrollLeft]);
  const closeOnNavigation=()=>dialog.close();
  dialog.onclose=()=>{closed=true;++currentGeneration;ownerController?.destroy();graph?.destroy();globalThis.window?.removeEventListener?.('popstate',closeOnNavigation);dialog.remove();if(host){onClose();return;}if(!isCurrent()||replacedByInspector(dialog))return;for(const [ref,top,left]of scrollOwners){const node=ref.deref();if(node?.isConnected){node.scrollTop=top;node.scrollLeft=left;}}const origin=originRef.deref();const back=origin?.isConnected&&!origin.disabled?origin:document.querySelector('.workspace')||document.body;if(back!==origin)back.tabIndex=-1;back.focus?.({preventScroll:true});};
  if(host){dialog.close=()=>{if(!closed)dialog.onclose();};host.replaceChildren(dialog);adopt(dialog);}else{document.body.append(dialog);adopt(dialog);dialog.showModal();globalThis.window?.addEventListener?.('popstate',closeOnNavigation);heading.tabIndex=0;heading.focus();}
  // Reveal inside this reader only. scrollIntoView can move the dialog itself and
  // clip its title/Close even when focus uses preventScroll (long Work/source reads).
  const revealInspector=(panel,fresh)=>{if(!fresh())return;panel.tabIndex=-1;panel.focus({preventScroll:true});
    const bounds=reading.getBoundingClientRect?.(),target=panel.getBoundingClientRect?.();
    if(bounds&&target)reading.scrollTop=Math.max(0,reading.scrollTop+target.top-bounds.top);
  };
  const inspectOwner=async(read,reading={})=>{
    if(!alive())return;
    body.setAttribute('aria-busy','true');
    if(read?.http?.method!=='GET')throw Error('An explicit GET owner read is required.');read=ownerHumanTarget(read.http.url);if(!read)throw Error('The selected owner coordinates are invalid.');
    if(read.kind==='concept')return currentNode(read.node,read.project);
    if(read.kind==='research-result')return currentResult(read.id,read.project);
    const ticket=++currentGeneration;ownerController?.destroy();ownerController=null;
    if(!currentPanel){currentPanel=el('section','','artifact-current');body.append(currentPanel);}
    const panel=currentPanel,fresh=()=>alive()&&ticket===currentGeneration&&panel.isConnected;
    panel.replaceChildren(el('h3','Owner reading'),el('p',read.project+' · '+(read.id||read.target?.path||read.view)),pendingRead(el('p','Reading the exact owner…','muted')));
    try{
      if(read.kind==='template-preview'){
        if(read.part==='preview-output'){const {openPdf}=await import('/shared/writing-pdf.mjs');await openPdf(read.http.url,'Exact template preview',{onOpenArtifact:nested,notice:'Retained candidate output, separate from the current manuscript PDF.'});return;}
        panel.replaceChildren(el('h3','Exact template preview image'));const image=el('img');image.src=read.http.url;image.alt='Pinned template preview page '+read.read_handle.payload.page;image.style.maxWidth='100%';panel.append(image);return;
      }
      const recordTarget=read.kind==='history-record'?analyticsExactTarget({http:read.http},{project:read.project}):null;
      const buildStatus=['derived-build-status','manuscript-build-status','candidate-build-status'].includes(read.kind);
      const structuralOutcome=read.kind==='structure'&&read.view==='restructure';
      const value=await readOwner(read.http.url,buildStatus||structuralOutcome?{allowStateError:true}:{},{live:buildStatus||structuralOutcome});if(!fresh())return;
      if(value.project!==read.project&&!(buildStatus&&value.corpus===read.project))throw Error('The owner returned a different project namespace.');
      panel.replaceChildren();
      if(snapshotBasis){const basis=snapshotBasis,when=/T(\d\d:\d\d)/.exec(basis.at)?.[1]||basis.at;panel.dataset.snapshot='true';
        const state=el('p','','artifact-identity-notice snapshot-state');state.append(el('span','Previously inspected · '+when+' · read-only'),document.createTextNode(' '),button('Read current',safe(()=>{fromTrail=false;snapshotPin=null;return inspectOwner(read,reading);})));
        const exact=el('details','','snapshot-provenance');exact.append(el('summary','Exact provenance'),el('pre','owner read '+basis.url+'\ncut '+(basis.cut||'none stated')+'\nread at '+basis.at+'\n'+basis.bytes+' bytes retained; no current permission is implied'));
        panel.append(state,exact);}
      if(read.kind==='template-candidates'){
        if(value.schema_version!=='laplace.document-template-candidate/1'||!Array.isArray(value.candidates))throw Error('The template owner returned a different candidate catalogue.');
        panel.append(el('h3','Saved template candidates'));
        for(const row of value.candidates){const target=qualifiedOwnerHTTP(row.read_handle,read.project);
          if(target?.owner?.kind!=='template-candidate'||target.owner.candidateRef.id!==row.candidate_ref?.id||target.owner.candidateRef.version!==row.candidate_ref?.version)throw Error('The catalogue has no exact candidate read.');
          panel.append(button(row.reason||'Read saved template candidate',safe(()=>inspectOwner(target.owner))));}
        if(!value.candidates.length)panel.append(el('p','No saved template candidates.'));
      }else if(read.kind==='template-candidate'){
        if(!fresh())return;
        if(read.part!=='metadata'){
          const text=await readTemplatePart({...read.read_handle,http:read.http},{project:read.project,candidateRef:read.candidateRef,request});
          if(fresh())panel.append(el('h3','Exact retained template '+read.part),el('pre',text.text));
        }else{
          validateTemplateMetadata(value,{project:read.project,candidateRef:read.candidateRef});
          ownerController=renderTemplateCandidate(panel,value,{project:read.project,isCurrent:fresh,
            onReadPart:handle=>readTemplatePart(handle,{project:read.project,candidateRef:read.candidateRef,request}),
            onPdf:async(metadata,proof)=>{const {openPdf}=await import('/shared/writing-pdf.mjs');await openPdf(templateOutputURL(metadata.preview_pdf_read,read.project,read.candidateRef,proof),'Exact template preview',{onOpenArtifact:nested});}});
          const full=el('a','Open manuscript for template actions (opens separately)');full.href=read.href;full.target='_blank';full.rel='noopener noreferrer';panel.append(full);
        }
      }else if(read.kind==='derived-output'){
        const full=el('a','Open Figures & output for actions (opens separately)');full.href=read.href;full.target='_blank';full.rel='noopener noreferrer';panel.append(full);
        const host=el('section');panel.append(host);
        const controller=await mountDerivedOutput(host,{project:read.project,request,initial:value,readOnly:true,
          onReadPdf:async(url,title,options)=>{const {openPdf}=await import('/shared/writing-pdf.mjs');return openPdf(url,title,{...options,onOpenArtifact:nested});},
          status:(text,error)=>{if(fresh())announce(text,error);}});
        if(!fresh()){controller.destroy();return;}ownerController=controller;
      }else if(buildStatus||read.kind==='manuscript-document'){
        if(read.buildTarget&&!sameBuildTarget(value.build_target,read.buildTarget))throw Error('The build owner returned a different derived target.');
        const observed=value.current_build||value;
        if(read.buildJob&&!sameBuildJob(observed.build_job,read.buildJob))throw Error('The build owner returned a different job.');
        panel.append(el('h3',read.kind==='manuscript-document'?'Manuscript document':'Build observation'),
          el('p',observed.state==='cancelling'?'Stopping this build; waiting for its processes to end.':observed.state==='cancelled'?'This build was stopped.':observed.running?'The owner reports this build running.':observed.ok===false?'The latest build failed.':observed.fresh?'The owner reports output current.':'Output needs inspection.'));
        if(read.buildJob)panel.append(el('p','Build job: '+read.buildJob.id+' · '+read.buildJob.root));
        if(observed.reason||observed.error)panel.append(el('p',observed.reason||observed.error));
        if(observed.log_tail)panel.append(el('pre',observed.log_tail));
        const exact=el('details');exact.append(el('summary','Exact owner observation'),el('pre',JSON.stringify(value,null,2)));panel.append(exact);
        const full=el('a','Open output workspace (opens separately)');full.href=read.href;full.target='_blank';full.rel='noopener noreferrer';panel.append(full);
      }else if(read.kind==='structure'&&read.view==='delivery'){
        const original=read.read_handle.payload;
        if(value.schema_version!=='laplace.delivery-part/1'||value.view!=='delivery'||value.recorded_context_id!==original.context_id||
          value.part!==original.part||value.expected_token!==original.expected_token||typeof value.text!=='string'||
          !/^[0-9a-f]{32}$/.test(value.token||'')||typeof value.matches_expected!=='boolean'||
          value.matches_expected!==(value.token===value.expected_token)||value.historical_bytes!==false||value.context_recorded!==false||
          value.currentness!==(value.matches_expected?'CURRENT_MATCH':'CHANGED_CURRENT_CONTENT'))throw Error('The scoped-context owner returned a different recorded scope or comparison.');
        const labels={canonical_structure:'Reader-plan context',direct_prerequisites:'Direct prerequisites',mathematical_record:'Mathematical record',section_notes:'Section notes',local_source_refs:'Local source links'};
        panel.append(el('h3',labels[value.part]),el('p',value.matches_expected?'Current scoped content matches the recorded input.':'The current scoped content changed. This is current content, not retained historical bytes.'),
          el('pre',value.text));
        const basis=el('details');basis.append(el('summary','Scope and comparison basis'),el('p','Recorded context: '+value.recorded_context_id),el('p','Included bytes: '+value.bytes),el('pre',JSON.stringify(value.scope,null,2)));panel.append(basis);
        panel.append(button('Refresh current comparison',safe(()=>inspectOwner(read))));
      }else if(read.kind==='current-help'){

        if(value.inspection?.binding!=='recorded-turn'||value.inspection.turn_id!==read.turnId||typeof value.inspection.mode!=='string'||!value.inspection.mode||!value.help||typeof value.help!=='object'||Array.isArray(value.help)||read.selector.operation&&value.help.requested_operation!==read.selector.operation)throw Error('Current help returned a different recorded-turn inspection.');
        panel.append(el('h3','Current recovery contract'),el('p',read.project+' · original turn '+read.turnId+' · admitted mode '+value.inspection.mode),el('p','Explicit current inspection. The historical failure and its saved guidance are unchanged; no retry or resolution is inferred.','muted'),el('pre',JSON.stringify(value.help,null,2)));
      }else if(read.kind==='changed-reads'){
        // the exact candidate asked for, and on a continuation the exact observation cut it continues (AR-R3)
        if(value.schema_version!=='laplace.changed-consulted-reads/2'||value.turn_id!==read.id||!Array.isArray(value.changed_reads)
          ||read.version&&value.proposal_version!==read.version||read.recordId&&value.status==='OBSERVED'&&value.record_id!==read.recordId)
          throw Error('The proposal owner returned a different changed-read page.');
        if(reading.expectedCut&&value.observation?.cut!==reading.expectedCut)throw Error('The continuation returned a different observation cut.');
        if(value.status==='REFUSED'){
          panel.append(el('h3','Changed consulted reads'),el('p',read.project+' · candidate '+(read.recordId||read.id)),
            el('p','Stopped before observing: '+(value.reason||'the candidate was refused.'),'error'),el('p','No consulted read was observed, so nothing is listed or complete.','muted'));
        }else{
          if(value.status!=='OBSERVED'||!value.observation||!value.changed)throw Error('The proposal owner returned a different changed-read page.');
          const span=value.changed;
          panel.append(el('h3','Changed consulted reads'),el('p',read.project+' · candidate '+value.record_id+' · changed reads '+span.from+'–'+span.to+' of '+span.of
            +' · '+value.observation.consulted+' consulted reads observed'),el('p',value.note,'muted'));
          const list=el('ul');for(const row of value.changed_reads){const item=el('li');
            item.append(el('p',row.operation+' · '+row.currentness+(row.payload_omitted?' · exact payload in its receipt':'')),el('small',row.read_id));
            if(row.changed_selectors?.changed?.length)item.append(el('p','Moved: '+row.changed_selectors.changed.join(', '),'muted'));
            if(row.read_detail?.payload?.id)item.append(button('Open consulted receipt',safe(()=>inspectOwner({http:{method:'GET',url:'/authoring/history?'+new URLSearchParams({project:read.project,view:'record',id:row.read_detail.payload.id})}},{backRead:read}))));
            list.append(item);}
          panel.append(list);
          const next=value.next?.http?.method==='GET'&&ownerHumanTarget(value.next.http.url);
          if(value.next&&!(next&&next.kind==='changed-reads'&&next.project===read.project&&next.id===read.id&&next.recordId===value.record_id&&next.version===value.proposal_version&&next.cursor))
            throw Error('The proposal owner offered a continuation for a different candidate.');
          if(next)panel.append(button('Next changed reads',safe(()=>inspectOwner(value.next,{...reading,expectedCut:value.observation.cut}))));
          else if(value.complete&&span.to===span.of)panel.append(el('p',span.of?'All '+span.of+' changed consulted reads of this observation are listed.':'No consulted read changed in this observation.','muted'));
        }
      }else if(read.kind==='history-record'){
        renderAnalyticsRecord(panel,value,recordTarget,{isCurrent:fresh,onInspectOwner:(target,options)=>{options.onOpen?.(dialog);return inspectOwner(target,{backRead:read});}});
      }else if(read.kind==='bibliography-entry'){
        if(value.citekey!==read.citekey||!['AVAILABLE','AMBIGUOUS','MISSING'].includes(value.status)||!Array.isArray(value.entries))throw Error('The bibliography owner returned a different entry.');
        panel.append(el('h3','Citation: '+value.citekey),el('p',value.status==='AMBIGUOUS'?'Several entries use this key. Inspect the source before choosing.':value.status==='MISSING'?'No entry with this key exists in the selected bibliography.':'Selected bibliography entry'));
        for(const entry of value.entries){
          if(entry.citekey!==value.citekey||typeof entry.file!=='string'||typeof entry.complete!=='boolean'||entry.complete&&typeof entry.content!=='string')throw Error('The bibliography entry has an invalid source witness.');
          const record=el('details');record.open=value.entries.length===1;record.append(el('summary',entry.file.split('/').at(-1)));
          record.append(entry.complete?el('pre',entry.content):el('p','This entry exceeds the bounded preview. Read its bibliography file to inspect it.'));
          const source=qualifiedOwnerHTTP(entry.source_read,read.project);
          if(source?.source?.file===entry.file)record.append(button('Read bibliography source',safe(async()=>{
            const observed=await request(source.url);if(!fresh())return;
            if(observed.file!==entry.file||observed.expected_source_digest!==entry.file_revision||typeof observed.content!=='string')throw Error('The bibliography changed after this entry was inspected. Refresh the entry before reading the file.');
            record.append(el('pre',observed.content));
          })));
          panel.append(record);
        }
        if(value.meaning)panel.append(el('p',value.meaning,'muted'));
      }else if(read.kind==='structure'){
        const full=el('a','Open Reader plan for actions (opens separately)');
        full.href=read.href;full.target='_blank';full.rel='noopener noreferrer';panel.append(full);
        if(read.view==='restructure'){
          if(value.section_id!==read.sectionIds[0]||value.receipt?.id!==read.read_handle.payload.receipt_id||value.receipt.intent_artifact_id!==read.read_handle.payload.intent_artifact_id)throw Error('The structural owner returned a different retained operation.');
          panel.append(el('h3',value.receipt_recorded === false ? 'Retained structural operation' : 'Recorded structural outcome'),el('p',value.receipt_recorded === false
            ? 'The operation admission is retained; receipt recording is unproved. Inspect its source outcome before continuing.'
            : 'This is the exact saved receipt. Later changes have separate standing.','muted'));
          ownerController=renderRestructureOutcome(panel,value,{project:read.project,isCurrent:fresh});
          if(read.read_handle.payload.reconcile_current===true)renderMetadataReconciliation(panel,value,{project:read.project,isCurrent:fresh,
            onRead:(handle,label)=>inspectStructuralInput(handle,{project:read.project,request,label,opener:document.activeElement,isCurrent:fresh,
              onRead:(handle)=>{const target=qualifiedOwnerHTTP(handle,read.project);if(target?.owner)return inspectOwner(target.owner);throw Error('This input has no contextual owner read.');}})});
        }else if(read.view==='detail'&&read.read_handle.payload.projection==='guard'){
          // ONE exact guard subject (Sol guard-consumer): rendered from this response alone,
          // never remounted as a reader plan (which would read a fresh summary and repeat the
          // guard read); a response for another owner, section, subject or paragraph refuses
          const payload=read.read_handle.payload,subject=payload.subject||(payload.paragraph_id?'paragraph':'contract');
          if(read.sectionIds.length!==1)throw Error('A guard read names exactly one canonical section; read the plain detail for a node or file selection, then its section_ids guard.');
          const host=el('section');panel.append(host);
          renderReaderGuard(host,value,{project:read.project,sectionId:read.sectionIds[0],subject,paragraphId:payload.paragraph_id||null,
            onRead:(handle,label)=>{const target=qualifiedOwnerHTTP(handle,read.project);if(target?.owner)return inspectOwner(target.owner);throw Error('This '+label+' has no qualified inspection route.');}});
        }else if(!['summary','detail'].includes(read.view)){
          panel.append(el('h3','Read-only '+read.view+' observation'),el('pre',JSON.stringify(value,null,2)));
        }else{
          const host=el('section');panel.append(host);
          const inspectHandle=(handle,label='Reader-plan input')=>{
            const target=qualifiedOwnerHTTP(handle,read.project);
            if(target?.owner)return inspectOwner(target.owner);
            if(target?.artifact)return nested(target.artifact.path,label,target.artifact);
            if(!target)throw Error('This input has no qualified inspection route.');
            const link=el('a','Read exact '+label+' (opens separately)');link.href=target.url;link.target='_blank';link.rel='noopener noreferrer';host.append(link);
          };
          const controller=await mountReaderPlan(host,{
            project:read.project,readOnly:true,
            initial:{sectionId:read.sectionIds?.length===1?read.sectionIds[0]:null,beatId:read.read_handle.payload.node_id||null,readHandle:read.read_handle},
            request:(url,payload)=>{if(payload)throw Error('This contextual reader is read-only. Open Reader plan for actions.');return request(url);},
            onRead:inspectHandle,
            onConcept:(id,handle)=>handle?inspectHandle(handle,'argument object'):currentNode(id,read.project),
            onWork:(_id,handle)=>inspectHandle(handle,'Work'),
            onEvidence:(_id,handle)=>inspectHandle(handle,'evidence'),
            onSource:({sourceRead})=>inspectHandle(sourceRead,'source'),
            status:(text,error)=>{if(fresh())announce(text,error);}
          });
          if(!fresh()){controller.destroy();return;}ownerController=controller;
        }
      }else if(read.kind==='work'&&read.view==='graph'){
        renderWorkNeighbourhood(panel,value,{project:read.project,request,isCurrent:fresh,parentWorkId:read.parentWorkId||null,
          onSelect:id=>inspectOwner({http:{method:'GET',url:'/work/state?'+new URLSearchParams({project:read.project,view:'detail',id})}}),
          onRead:handle=>inspectOwner(handle)});
      }else if(read.kind==='work'){
        if(value.view!==read.view||read.view==='detail'&&value.task?.id!==read.id)throw Error('The Work owner returned different focused coordinates.');
        const full=el('a','Open the full Work tab for actions');full.href=read.href;full.target='_blank';full.rel='noopener noreferrer';panel.append(full);
        const host=el('section');panel.append(host);
        const controller=await mountOperatorWork(host,{project:read.project,summary:read.view==='summary'?value:null,request,readOnly:true,detailOnly:read.view==='detail',initialWork:read.id||null,initialDetail:read.view==='detail'?value:null,onSelect:task=>{full.href=ownerHumanTarget('/work/state?'+new URLSearchParams({project:read.project,view:'detail',id:task.id})).href;},onArtifact:(p,l,o)=>nested(p,l,o),onInspectOwner:(handle,_label,options)=>{return inspectOwner(handle,options);}});
        if(!fresh()){controller.destroy();return;}ownerController=controller;
      }else{
        if(value.schema_version!=='laplace.material-reference-source/1'||read.id&&value.id!==read.id||read.consumer&&value.consumer!==read.consumer)throw Error('The source owner returned incompatible reading coordinates.');
        if(read.target&&(!value.target||Object.keys(value.target).length!==Object.keys(read.target).length||Object.keys(read.target).some(key=>value.target[key]!==read.target[key])))throw Error('The source owner returned a different qualified target.');
        ownerController=renderMaterialObservation(panel,value,{request,isCurrent:fresh,initialHandle:{http:read.http},workEvidence:reading.workEvidence===true,consumedRevision:reading.consumedRevision,completeReading:reading.completeReading===true});
      }
      if(reading.backRead)panel.append(button('Back to recorded failure',safe(()=>inspectOwner(reading.backRead))));
      revealInspector(panel,fresh);return true;
    }catch(error){if(fresh()){panel.replaceChildren(el('p','Owner reading unavailable: '+error.message,'error'));announce(error.message,true);onReadError(error);revealInspector(panel,fresh);}return false;}finally{if(fresh())body.setAttribute('aria-busy','false');}
  };
  const currentNode=async(id,ownerProject=project)=>{
    if(!alive())return;
    const readURL='/concepts/state?'+new URLSearchParams({project:ownerProject,node:id});
    const target=conceptHumanTarget(readURL);
    if(!target)throw Error('Exact project and claim coordinates are required.');
    const ownerLink=()=>{const link=el('a','Open in Argument & evidence (opens separately)');link.href=target.href;link.target='_blank';link.rel='noopener noreferrer';return link;};
    const ticket=++currentGeneration;
    ownerController?.destroy();ownerController=null;
    if(!currentPanel){currentPanel=el('section','','artifact-current');body.append(currentPanel);}
    const panel=currentPanel,scroll=reading.scrollTop,fresh=()=>alive()&&ticket===currentGeneration&&panel.isConnected;
    panel.replaceChildren(el('h3','Read-only claim preview'),el('p',ownerProject+' · '+id),ownerLink(),pendingRead(el('p','Reading current object…','muted')));
    try{
      const state=await request(readURL);if(!fresh())return;
      const {renderConceptRecord}=await import('/shared/concept-reader.mjs');if(!fresh())return;
      // Async scientific rendering stays off the live inspector until this exact
      // request is still selected. A later traversal cannot inherit partial old DOM.
      const staged=el('div');staged.append(el('h3','Read-only claim preview'),el('p',ownerProject+' · '+id),ownerLink(),el('p','Current revision: '+(state.content_revision||'unavailable')));
      await renderConceptRecord(staged,{node:{id,...state.focus},state,onNavigate:target=>currentNode(typeof target==='string'?target:target.node||target.id,ownerProject)});
      if(!fresh())return;
      panel.replaceChildren(...staged.childNodes);reading.scrollTop=scroll;
      revealInspector(panel,fresh);
    }catch(error){if(fresh()){panel.replaceChildren(el('h3','Read-only claim preview'),el('p',ownerProject+' · '+id),ownerLink(),el('p',error.message,'error'));announce(error.message,true);}}
  };
  const currentResult=async(id,ownerProject=project)=>{
    if(!alive())return;
    const readURL='/research/result?'+new URLSearchParams({project:ownerProject,id});
    if(!ownerHumanTarget(readURL))throw Error('Exact project and result coordinates are required.');
    const ticket=++currentGeneration;ownerController?.destroy();ownerController=null;
    if(!currentPanel){currentPanel=el('section','','artifact-current');body.append(currentPanel);}
    const panel=currentPanel,fresh=()=>alive()&&ticket===currentGeneration&&panel.isConnected;
    panel.replaceChildren(el('h3','Read-only result preview'),el('p',ownerProject+' · '+id),pendingRead(el('p','Reading current result…','muted')));
    try{
      const data=await request(readURL);if(!fresh())return;
      if(data.project!==ownerProject||data.result?.id!==id)throw Error('The result owner returned different coordinates.');
      const {renderResearchCard}=await import('/shared/research-card.mjs');if(!fresh())return;
      const staged=el('section');staged.append(el('h3','Current result — separate from the recorded binding'));
      renderResearchCard(staged,data.result,{project:ownerProject,inspect:async(_parent,l,p,s)=>{await nested(p,l,{project:ownerProject,scope:s});},onError:m=>{if(fresh())announce(m,true);}});
      if(!fresh())return;panel.replaceChildren(...staged.childNodes);revealInspector(panel,fresh);return true;
    }catch(error){if(fresh()){panel.replaceChildren(el('p',error.message,'error'));announce(error.message,true);}return false;}finally{if(fresh())body.setAttribute('aria-busy','false');}
  };
  const recordNode=async(host,id,snapshot)=>{
    host.replaceChildren();const v=snapshot.recorded,n=v.nodes.find(n=>n.id===id);
    if(!n){host.append(el('p','This endpoint has no recorded object details: '+id),button('Open current canonical object',safe(()=>currentNode(id))));return;}
    host.append(el('h3',n.title||id),el('code',id),el('p','Recorded revision: '+(n.revision||'not recorded')),
      el('p',[n.kind,n.class,n.qualification].filter(Boolean).join(' · ')),
      button('Open current canonical object',safe(()=>currentNode(id))));
    if(n.meaning)host.append(el('p',n.meaning));
    if(n.discharge)host.append(el('p','Open question / discharge condition: '+n.discharge));
    const placement=el('section');placement.append(el('h4','Recorded chapter placements'));
    const chapters=v.chapters.filter(c=>c.nodes?.includes(id));
    for(const c of chapters)placement.append(el('p',c.id+' — '+(c.job||'')),button('Inspect chapter source (current file)',safe(()=>nested(c.source,c.id))));
    if(!chapters.length)placement.append(el('p','No chapter placement recorded.'));
    host.append(placement);
    const relationBox=el('section');relationBox.append(el('h4','Recorded typed relationships'));
    for(const r of snapshot.relations.filter(r=>r.source===id||r.target===id)){
      const line=el('p',r.source+' '+RELATION_LABELS[r.rel]+' '+r.target);
      const target=r.source===id?r.target:r.source;
      line.append(document.createTextNode(' '),button('Inspect '+target,safe(()=>recordNode(host,target,snapshot))));relationBox.append(line);
    }host.append(relationBox);
    const sources=el('section');sources.append(el('h4','Recorded documentary support'));
    for(const key of n.sources||[]){
      const source=recordedSource(v,key);sources.append(el('p',key));
      if(source){
        sources.append(el('code',source.path+' · SHA256 '+source.sha256));
        if(source.lineRange)sources.append(el('p','Recorded lines '+source.lineRange[0]+'–'+source.lineRange[1]));
        if(source.origin)sources.append(el('p','Original source: '+JSON.stringify(source.origin)));
        sources.append(button('Read pinned source snapshot '+key,safe(()=>nested(source.path,key,{scope:source.scope,expectedSha256:source.sha256,lineRange:source.lineRange}))));
      }else sources.append(el('p','Source identity absent from this snapshot: '+key));
    }
    for(const row of v.documentary_bindings||[])if(row[0]===id)sources.append(el('p','Reference '+row[2]+' · reading receipt '+row[3]));
    host.append(sources);
    const results=el('section');results.append(el('h4','Recorded research support'));
    for(const bind of v.research_bindings||[])if(bind.claim===id){
      const result=v.results?.[bind.result];results.append(el('p',bind.result+' · recorded revision '+(result?.revision||'not recorded')));
      if(result){
        results.append(el('p','Recorded run: '+(result.run||'not recorded')+' · '+(result.state||'state not recorded')+' · exit '+(result.exit_code??'not recorded')));
        if(result.output_sha256)results.append(el('code','Recorded output SHA256 '+result.output_sha256));
        const files=recordedResultFiles(result);
        if(result.output_sha256&&!files.some(file=>file.role==='recorded output'))results.append(el('p','Output identity is recorded but no matching declared file path is available. No path was inferred.'));
        for(const file of files){
          results.append(el('p',file.role+' · '+file.scope+': '+file.path+' · '+(file.status||'status not recorded')),el('code','SHA256 '+(file.sha256||'not recorded')));
          if(file.sha256)results.append(button('Open '+file.role+' '+file.path,safe(()=>nested(file.path,file.role,{scope:file.scope,expectedSha256:file.sha256}))));
          else results.append(button('Open current dependency (unverified)',safe(()=>nested(file.path,file.path,{scope:file.scope}))));
        }
      }
      if(result?.limitations)for(const text of result.limitations)results.append(el('p',text));
      results.append(button('Open current result inspector',safe(()=>currentResult(bind.result))));
    }host.append(results);
  };
  try{
    if(ownerRead){const ready=await inspectOwner(ownerRead,{workEvidence,consumedRevision,backRead,completeReading});if(alive()&&ready)announce('Read-only owner · '+ownerRead.project+' · current observations are separate from acceptance.');return dialog;}
    if(/\.(png|jpe?g|svg)$/i.test(path)){
      pendingMedia=true;const img=el('img');img.alt=label;
      img.onload=()=>{if(!alive())return;pendingMedia=false;body.setAttribute('aria-busy','false');announce((pin?'Recorded image · SHA256 '+pin:'Current project image')+' · '+path);};
      img.onerror=()=>{if(!alive())return;pendingMedia=false;body.setAttribute('aria-busy','false');img.remove();announce(pin?'Recorded image is missing or its SHA256 changed. No different bytes were displayed.':'Current image unavailable.',true);
        if(pin)body.append(button('Open current image (unverified against record)',safe(()=>nested(path,label,{scope,notice:'Explicit current-file view; it is not the recorded image.'}))));};
      img.src=url;body.append(img);announce(pin?'Loading hash-guarded recorded image…':'Loading current project image…');return dialog;
    }
    loaded=await readArtifact({request,...ref,expectedSha256:pin,alive,onProgress:(_n,id)=>{status.textContent=host?'Reading source…':'Reading complete artifact · '+id.bytes+' bytes · SHA256 '+id.sha256;}});
    if(!alive())return dialog;
    const expected=expectedSha256?.replace(/^sha256:/,'');
    if(expected&&expected.toLowerCase()!==loaded.identity.sha256.toLowerCase()){const observed=loaded.identity.sha256;loaded=null;throw Error('Linked source identity changed. Expected '+expected+'; observed '+observed+'. Reopen the current source explicitly; it is not the recorded snapshot.');}
    const prepareReader=button('Prepare text-only reader',safe(async()=>{const {openSealedReader,inspectedReaderItem}=await import('./sealed-reader.mjs');if(alive())return openSealedReader({project,primary:inspectedReaderItem({owner:'artifact',project,path:loaded.identity.path,scope:loaded.identity.scope},loaded.identity.sha256)});}));controls.append(prepareReader);
    if(loaded.page.literature){const add=button('Add to Literature',safe(async()=>{const {openRetainedSourceLiterature}=await import('./retained-source-literature.mjs');if(alive())return openRetainedSourceLiterature({project,read:loaded.page.literature,request,isCurrent,target:options?.literatureTarget??null});}));add.dataset.control='material:add-literature';add.dataset.controlOwner=project+'::'+(loaded.page.literature.payload?.original?.artifact_id||path);controls.append(add);}
    raw.textContent=loaded.text;rawPage=loaded.page;
    // the painted extent and read time: the actual scalar range on screen now (this owner pages decoded text in Unicode scalar
    // offsets; checkArtifactPage verified them), never the whole-file size. File bytes stay separate exact metadata (status line,
    // Reading details); a Complete reading names its whole scalar count.
    const readAt=()=>new Date().toISOString().replace('T',' ').slice(0,19)+' UTC',scalars=text=>Array.from(String(text??'')).length,total=loaded.identity.total_chars;
    const extentText=(from,text)=>loaded.complete?'Complete · '+total+' characters · read at '+readAt():'Partial · characters '+from+'–'+(from+scalars(text))+' of '+total+' · read at '+readAt();
    const painted=el('p','','artifact-extent');painted.dataset.extent=loaded.complete?'complete':'partial';painted.textContent=extentText(0,loaded.text);
    if(reading.insertBefore)reading.insertBefore(painted,body);else reading.append(painted);
    const inspectClaim=target=>safe(()=>currentNode(target.node,target.project))();
    renderEngineeringSupport(reading,loaded.page.engineering_support);
    const degradation=loaded.page.custody_degradation;
    if(degradation?.status==='INLINE_RETAINED')reading.append(el('p','Saved inline: body-store verification unavailable · '+degradation.failed_attempts+' attempts · '+degradation.inline_bytes+' inline bytes','artifact-identity-notice'));
    announce(host?(expected?'Matches saved revision':'Current file · no saved content pin')+' · '+loaded.identity.bytes+' bytes':(expected?'Recorded file · matched expected revision':'Current file contents')+' · '+scope+': '+path+' · SHA256 '+loaded.identity.sha256);
    if(host)exact.append(el('pre',JSON.stringify({project,path,scope,artifact_id:artifactId,expected_sha256:pin,observed:loaded.identity,complete:loaded.complete},null,2)));
    download.textContent='Download inspected bytes';download.href=artifactURL(ref,{download:1,expected_sha256:loaded.identity.sha256});
    const toggle=button('Show raw JSON / text',()=>{raw.hidden=!raw.hidden;body.hidden=!raw.hidden;toggle.textContent=raw.hidden?'Show raw JSON / text':'Return to evidence view';reading.scrollTop=0;});controls.prepend(toggle);
    // Continue names the next requested scalar range from the owner's next_offset, the bounded page limit and the total. One
    // continuation is in flight at a time, read at this reader's exact pin; a duplicate click issues nothing, and a stale, changed
    // (checkArtifactPage) or closed-reader reply never repaints. On receipt the actual returned page extent is painted.
    const PAGE_LIMIT=32768,continueLabel=()=>rawPage.next_offset===null?'End of text reached':'Continue: characters '+rawPage.next_offset+'–'+Math.min(rawPage.next_offset+PAGE_LIMIT,total)+' of '+total;
    let continuing=false;
    const next=button(continueLabel(),safe(async()=>{
      if(continuing||rawPage.next_offset===null)return;
      const offset=rawPage.next_offset;continuing=true;next.disabled=true;
      try{const page=await request(artifactURL(ref,{format:'json',offset,limit:PAGE_LIMIT,...(pin?{expected_sha256:pin}:{})}));
        if(!alive()||offset!==rawPage.next_offset)return;
        checkArtifactPage(page,offset,loaded.identity);rawPage=page;raw.textContent=page.content;
        status.textContent='Text page '+offset+'–'+(offset+scalars(page.content))+' of '+page.total_chars+' · SHA256 '+page.sha256;
        painted.dataset.extent='partial';painted.textContent=extentText(offset,page.content);}
      finally{continuing=false;if(alive()){next.textContent=continueLabel();next.disabled=rawPage.next_offset===null;}}
    }));next.hidden=loaded.complete;controls.append(next);
    if(!loaded.complete){body.append(el('p',loaded.reason));raw.hidden=false;if(host)reading.append(next);return dialog;}
    if(lineRange){
      if(!Array.isArray(lineRange)||lineRange.length!==2||!lineRange.every(Number.isSafeInteger)||lineRange[0]<1||lineRange[1]<lineRange[0])throw Error('Invalid recorded line range.');
      const lines=loaded.text.split(/\r?\n/);if(lines.at(-1)==='')lines.pop();
      if(lineRange[1]>lines.length)throw Error('Recorded line range is outside these identified bytes.');
      body.append(el('p','Recorded lines '+lineRange[0]+'–'+lineRange[1]+'; full-file SHA256 '+loaded.identity.sha256),
        el('pre',lines.slice(lineRange[0]-1,lineRange[1]).map((line,i)=>(lineRange[0]+i)+' | '+line).join('\n')));
      return dialog;
    }
    let value=null;if(/\.json$/i.test(path)){try{value=JSON.parse(loaded.text);}catch(e){throw Error('Complete file is not valid JSON: '+e.message);}}
    const kind=artifactKind(value);
    if(kind==='argument'){
      const snapshot=argumentSnapshot(value,project,loaded.identity.sha256);
      body.append(el('p','Recorded argument snapshot. The graph and selections below use only this file. Current canonical records open only through explicitly labelled actions.','artifact-identity-notice'),
        el('p','Recorded network revision: '+(value.authority?.concept_network_revision||'not recorded')));
      const graphHost=el('div','','artifact-graph'),detail=el('section','','artifact-record');body.append(graphHost,detail);
      const filter=el('input');filter.placeholder='Find a recorded goal, claim or question';filter.setAttribute('aria-label',filter.placeholder);
      const list=el('div','','artifact-node-index');body.prepend(filter,list);
      const paintList=()=>{list.replaceChildren();const q=filter.value.toLowerCase(),rows=value.nodes.filter(n=>(n.id+' '+n.title+' '+n.kind).toLowerCase().includes(q));for(const n of rows.slice(0,100))list.append(button((n.kind||'object')+': '+(n.title||n.id),safe(()=>recordNode(detail,n.id,snapshot))));if(rows.length>100)list.append(el('p',(rows.length-100)+' more objects. Narrow the filter.'));};
      filter.oninput=paintList;paintList();
      snapshot.renderNode=(host,id)=>recordNode(host,id,snapshot);
      const {mountArgumentOverview}=await import('/shared/concept-explorer.mjs');if(!alive())return dialog;
      graph=await mountArgumentOverview(graphHost,{project,request:()=>{throw Error('Snapshot graph cannot fetch canonical state.');},snapshot,onSelect:q=>recordNode(detail,q.node,snapshot),onError:m=>announce(m,true)});
      const goals=value.nodes.filter(n=>n.kind==='goal');if(goals[0])await recordNode(detail,goals[0].id,snapshot);
    }else if(kind==='visual-index'){
      if(value.project!==project||!Array.isArray(value.figures)||value.figures.length>200)throw Error('Invalid or oversized visual index.');
      const {renderVisualReadiness}=await import('/shared/research-card.mjs');
      body.append(el('p','Recorded visual index. Captions, placements and output hashes below come from this file. Open current metadata explicitly to compare.'));
      const figureIds=new Set();for(const f of value.figures){if(typeof f?.id!=='string'||!f.id||figureIds.has(f.id))throw Error('Missing or duplicate recorded figure identity.');figureIds.add(f.id);}
      const outputsByFigure=value.figures.map(f=>visualOutputs(f));
      for(const [figureIndex,f] of value.figures.entries()){
        const card=el('article','','writing-card');card.append(el('h3',f.title||f.id),el('code',f.id),
          el('p',f.question||''),el('p',f.caption||''),el('p','Proposed chapters: '+(f.proposed_chapter_ids||[]).join(', ')));
        renderVisualReadiness(card,{...f,render_freshness:f.render?.drawing_currentness,readiness:'RECORDED'});
        card.append(el('p','Recorded placement: '+(f.placement_status||'not recorded')));
        if(f.placement){
          card.append(el('p','Chapter '+(f.placement.chapter||'not recorded')+' · '+(f.placement.source||'source not recorded')+' · lines '+(f.placement.source_lines||[]).join('–')+' · PDF page '+(f.placement.pdf_page??'not recorded')));
          if(f.placement.source)card.append(button('Inspect placed source (current file)',safe(()=>nested(f.placement.source,f.title||f.id))));
          if(f.placement.caption)card.append(el('p','Recorded placed caption: '+f.placement.caption));
        }
        const outputs=outputsByFigure[figureIndex];
        if(!outputs.length)card.append(el('p','No outputs were recorded for this figure.'));
        for(const out of outputs)if(['pdf','svg'].includes(out.format))card.append(el('p',out.format+' · '+out.scope+': '+out.path+' · SHA256 '+out.sha256),
          button('Open recorded '+out.format,safe(()=>nested(out.path,f.title||f.id,{scope:out.scope,expectedSha256:out.sha256}))),
          button('Open current '+out.format+' (unverified against record)',safe(()=>nested(out.path,f.title||f.id,{scope:out.scope,notice:'Explicit current-file view, separate from the recorded output hash.'}))));
        card.append(button('Compare current visual metadata',safe(async()=>{const live=await request('/visuals/state?'+new URLSearchParams({project}));const s=live.specs?.find(s=>s.id===f.id);if(!s)throw Error('Current visual is unavailable: '+f.id);const p=el('section');card.append(p);p.append(el('h4','Current visual metadata'),el('p','Current spec revision: '+s.spec_revision));renderVisualReadiness(p,s);})));
        body.append(card);
      }
    }else if(kind==='result-detail'||kind==='research-records'){
      if(value.project&&value.project!==project)throw Error('Research snapshot belongs to a different project.');
      const rows=kind==='result-detail'?[value.result]:value.records;
      if(!Array.isArray(rows)||rows.length>200)throw Error('Research snapshot exceeds the bounded inspector.');
      const {renderResearchCard}=await import('/shared/research-card.mjs');
      body.append(el('p','Recorded result snapshot. No currentness beyond the saved file is asserted.'));
      for(const r of rows){if(!r?.id)throw Error('Result identity is missing.');renderResearchCard(body,{...r,currentness:'UNKNOWN',currentness_reason:'Recorded snapshot; open current inspector to compare.'},{project,inspect:async(_p,l,p,s)=>{await nested(p,l,{scope:s});},onError:m=>announce(m,true)});body.append(button('Open current result '+r.id,safe(()=>currentResult(r.id))));}
    }else if(/\.md$/i.test(path)&&renderMarkdown){await renderMarkdown(body,loaded.text,{project,path,scope,onInspectClaim:inspectClaim,onInspectOwner:read=>safe(()=>inspectOwner(read))()});}
    else{if(value?.schema_version)body.append(el('p','File contents (read-only).'));body.append(el('pre',loaded.text));}
  }catch(e){if(alive()){announce(e.message,true);body.replaceChildren(el('p','No structured view was accepted. Download remains available.'));if(loaded?.complete){raw.textContent=loaded.text;raw.hidden=false;}}}
  finally{if(alive()&&!pendingMedia)body.setAttribute('aria-busy','false');}
  return dialog;
}
