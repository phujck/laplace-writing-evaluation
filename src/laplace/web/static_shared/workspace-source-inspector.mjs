// Read-only Source/engine readers. The existing inspector owns trail, Close and
// opener return; these views never mutate canonical Work, drafts or execution.
import {sharedInspector,payloadCut} from './workspace-inspector.mjs';
import {projectRequest} from './writing-request.mjs';
import {el,button,details} from './research-workbench-view.mjs';
import {pendingRead} from './pending-read.mjs';
const clone=value=>structuredClone(value),same=(a,b)=>JSON.stringify(a)===JSON.stringify(b),PIN=/^sha256:[a-f0-9]{64}$/,NODE=/^OP-SOURCE-[a-f0-9]{64}$/;
const here=()=>new URL(globalThis.location?.href||'http://local/');
const object=value=>value&&typeof value==='object'&&!Array.isArray(value);

export function sourceOwnerReadURL(handle,{facets=['source-kernel','historical-obligations']}={}){
 const url=new URL(handle?.http?.url||'',here());
 if(handle?.http?.method!=='GET'||url.origin!==here().origin||url.pathname!=='/work/discovery'||!facets.includes(url.searchParams.get('facet'))||!object(handle.request))throw Error('An exact issued read-only Source owner handle is required.');
 const query={};for(const [key,value]of url.searchParams){if(Object.hasOwn(query,key))throw Error('Repeated owner read coordinates are unsupported.');let decoded=value;if(['reference','selection','segments'].includes(key)){try{decoded=JSON.parse(value);}catch{throw Error('The issued owner coordinates are incomplete.');}}else if(['offset','limit','budget','content_offset','content_budget'].includes(key)){decoded=Number(value);if(!Number.isSafeInteger(decoded))throw Error('The issued read window is invalid.');}query[key]=decoded;}
 const keys=Object.keys(query).sort(),expected=Object.keys(handle.request).sort();if(!same(keys,expected)||keys.some(key=>!equal(query[key],handle.request[key])))throw Error('The HTTP read does not match its issued owner request.');return url.pathname+url.search;
}

function panel(title){const node=el('dialog','','workspace-dialog source-inspector-dialog'),close=button('Close',()=>node.close()),heading=el('h2',title),status=el('p','','work-status'),body=el('div');close.setAttribute('aria-label','Close '+title.toLowerCase());node.setAttribute('aria-label',title);status.setAttribute('role','status');node.append(heading,close,status,body);document.body.append(node);return {node,close,heading,status,body};}
function reopenHistorical(args,pin){return openHistoricalObligations({...args,handle:pin?.handle||args.handle,snapshotCut:pin?.cut??null,returnFocus:pin?.focusKey||null});}
const stable=value=>Array.isArray(value)?value.map(stable):object(value)?Object.fromEntries(Object.keys(value).sort().map(key=>[key,stable(value[key])])):value;
const equal=(a,b)=>JSON.stringify(stable(a))===JSON.stringify(stable(b));
// Bind only the owner template's named selector; observation is local read
// qualification, never a request field or a fabricated retained version.
export function sourceConstituentRead(template,key){
 sourceOwnerReadURL(template,{facets:['source-kernel']});
 if(template.request.view!=='declaration'||template.request.reference?.version||template.request.select!==undefined||template.field!=='select'||template.query_field!=='select'||!object(template.values)||!Object.hasOwn(template.values,key)||typeof template.values[key]!=='string'||!PIN.test(template.observation?.declaration||'')||!object(template.observation.segment_bases))throw Error('An exact owner-issued declaration selector and observation are required.');
 const read={request:clone(template.request),http:clone(template.http),observation:clone(template.observation)},url=new URL(read.http.url,here());
 read.request.select=template.values[key];url.searchParams.set(template.query_field,template.values[key]);read.http.url=url.pathname+url.search;return read;
}
export function sourceSiblingRead(template,key){
 sourceOwnerReadURL(template,{facets:['source-kernel']});
 if(template.field!=='view'||template.query_field!=='view'||!object(template.values)||!Object.hasOwn(template.values,key)||!['standing','counterpart'].includes(template.values[key]))throw Error('An exact owner-issued retained Source sibling read is required.');
 const read={request:clone(template.request),http:clone(template.http)},url=new URL(read.http.url,here());read.request.view=template.values[key];url.searchParams.set(template.query_field,template.values[key]);read.http.url=url.pathname+url.search;return read;
}
function retainedTarget(read,value,view,{single=true}={}){
 sourceOwnerReadURL(read,{facets:['source-kernel']});const r=read.request;
 if(r.view!==view||r.namespace!==value.selection.namespace||!sameReference(r.reference,value.reference)||!equal(r.selection,value.selection)||!Array.isArray(r.segments)||!r.segments.length||single&&r.segments.length!==1)throw Error('The retained navigation names another version, selection or scope.');
 return single?r.segments[0]:r.segments;
}
const partName=id=>String(id).replaceAll('_',' ').replaceAll('-',' ').replace(/(^|\s)\S/g,c=>c.toUpperCase());
function matchingObservation(declaration,observation,select){
 if(!PIN.test(observation?.declaration||'')||declaration.reference?.version?.declaration!==observation.declaration)return false;
 const [kind,id]=select.split(':');return declaration.selected===select&&declaration.item?.id===id&&(kind==='step'||kind==='segment'&&PIN.test(observation.segment_bases?.[id]||'')&&declaration.item.basis===observation.segment_bases[id]);
}
function sameReference(observed,expected){return object(observed)&&object(expected)&&observed.schema_version==='laplace.reference/1'&&expected.schema_version==='laplace.reference/1'&&observed.owner===expected.owner&&observed.kind===expected.kind&&equal(observed.identity,expected.identity)&&(!expected.version||equal(observed.version,expected.version));}
function factText(host,title,value){if(value===null||value===undefined)return;host.append(el('h3',title));if(typeof value==='string')host.append(el('p',value));else host.append(el('pre',JSON.stringify(value,null,2),'source-inspector-facts'));}
function renderStanding(host,standing,current){host.append(el('h3','Current owner review standing'));if(standing?.operation)host.append(el('p',standing.operation));const kernel=standing?.consumers?.['kernel.declared-source'];if(kernel)host.append(el('p','Kernel declared-source consumer: '+String(kernel.standing).replaceAll('_',' ').toLowerCase()));else if(standing?.status)host.append(el('p',String(standing.status).replaceAll('_',' ').toLowerCase()));else host.append(el('p','No selected consumer standing was asserted.','source-inspector-note'));if(standing?.semantic_currentness)host.append(el('p','Semantic currentness: '+String(standing.semantic_currentness).replaceAll('_',' ').toLowerCase()));if(standing?.changed_segments?.length)host.append(el('p','Changed segments: '+standing.changed_segments.join(', ')));host.append(details('All exact Source-contract standing',standing,{isCurrent:current}));}
function renderPartFacts(host,facts,current){
 if(!object(facts)){factText(host,'Declared facts',facts);return;}
 for(const [name,value]of Object.entries(facts)){
  if(value===null||value===undefined)continue;
  if(typeof value==='string'||typeof value==='number'||typeof value==='boolean'){host.append(el('h4',partName(name)),el('p',String(value)));continue;}
  if(Array.isArray(value)&&value.every(row=>typeof row==='string')){const list=el('ul');for(const row of value)list.append(el('li',row));host.append(el('h4',partName(name)),list);continue;}
  if(object(value)&&Object.values(value).every(row=>typeof row==='string'||typeof row==='number'||typeof row==='boolean'||Array.isArray(row)&&row.every(v=>typeof v==='string'))){const list=el('dl');for(const [key,row]of Object.entries(value))list.append(el('dt',partName(key)),el('dd',Array.isArray(row)?row.join(' · '):String(row)));host.append(el('h4',partName(name)),list);continue;}
  host.append(details('Inspect '+partName(name),value,{isCurrent:current}));
 }
}
function publicationSummary(value,selection,expectedHandle=null){
 if(!object(value)||!['selected-source-contribution','ordinary-full-deposit'].includes(value.mode)||!PIN.test(value.publication_handle||'')||expectedHandle&&value.publication_handle!==expectedHandle||(value.mode==='selected-source-contribution'?(!PIN.test(value.parent_basis||'')||!PIN.test(value.retained_basis||'')):[value.parent_basis,value.retained_basis].some(basis=>basis!=null&&!PIN.test(basis)))||value.coverage?.kind!=='selected-source-proof'||value.coverage.complete_world!==false||value.coverage.selected_namespace!==selection?.namespace||!object(value.derived_changes))throw Error('A complete active publication receipt for this selected Source scope is required.');
 return value;
}
function renderPublication(host,value,current){
 host.append(el('p',value.mode==='selected-source-contribution'?'Selected Source contribution published.':'Selected Source facts verified in the ordinary active publication.','source-inspector-state'),el('p',value.mode==='selected-source-contribution'?'Other kernel content follows its retained historical basis; this selected proof does not renew its currentness.':'This receipt proves the selected Source facts; it makes no complete-world freshness or authored checkpoint claim.','source-inspector-note'),details('Publication receipt, carried basis and derived changes',value,{isCurrent:current}));
}
function openerKey(label,read,context=null){return JSON.stringify(stable([label,read.request,read.observation??null,context]));}
// Reopen metadata retains a qualified control key, never the replaced DOM.
// The current inspector lifetime owns publication. Any later user intent cancels
// this one restoration; no timer, fallback element or global selection change.
function focusOnReturn(view,key,current){
 if(!key)return {finish(){},dispose(){}};let cancelled=false,done=false;
 const cleanup=()=>{document.removeEventListener('pointerdown',cancel,true);document.removeEventListener('keydown',cancel,true);document.removeEventListener('focusin',changedFocus,true);};
 const cancel=()=>{cancelled=true;cleanup();},changedFocus=event=>{if(event.target!==view.close&&event.target!==document.body)cancel();};
 document.addEventListener('pointerdown',cancel,true);document.addEventListener('keydown',cancel,true);document.addEventListener('focusin',changedFocus,true);
 return {dispose:cleanup,finish(){if(done)return;done=true;cleanup();if(cancelled||!current()||document.activeElement!==view.close)return;const target=[...view.node.querySelectorAll('[data-source-read-key]')].find(node=>node.dataset.sourceReadKey===key);if(target?.isConnected&&!target.disabled){for(let parent=target.parentElement;parent&&parent!==view.node;parent=parent.parentElement)if(parent.tagName==='DETAILS')parent.open=true;target.focus({preventScroll:true});}}};
}
function reopenSourceInspector(args,pin){return openSourceInspector({...args,handle:pin?.handle||args.handle,reinspected:true,returnFocus:pin?.focusKey||null});}

export async function openSourceInspector({handle,title='Source inspector',request=projectRequest,isCurrent=()=>true,reinspected=false,returnFocus=null}={}){
 const url=sourceOwnerReadURL(handle,{facets:['source-kernel','source-inventory']}),issued=clone(handle),expected=issued.request,view=panel(title),inspector=sharedInspector();view.node.dataset.control='source:inspect';let alive=true,focusReturn=null,focusKey=returnFocus;
 view.node.onclose=()=>{alive=false;focusReturn?.dispose();view.node.remove();};
 const token=inspector.adopt(view.node,{kind:'owner-read',title,reopen:{factory:reopenSourceInspector,args:{handle:issued,title,request}}}).token,current=()=>alive&&isCurrent()&&inspector.current?.token===token;
 view.node.showModal();view.close.focus();pendingRead(view.status,'Reading the exact Source owner…');
 focusReturn=focusOnReturn(view,returnFocus,current);
 const open=(next,label)=>{sourceOwnerReadURL(next,{facets:['source-kernel','source-inventory']});if(expected.namespace&&next.request.namespace!==expected.namespace&&next.request.project_lens!==expected.namespace)throw Error('This read leaves the issued Source scope.');return openSourceInspector({handle:next,title:label,request,isCurrent:inspector.lineage(token)});};
 const link=(host,label,read,context=null)=>{if(read){const key=openerKey(label,read,context),control=button(label,async()=>{try{focusKey=key;inspector.pin(token,{handle:issued,focusKey});return await open(read,label);}catch(error){if(current())view.status.textContent=error.message;}});control.dataset.sourceReadKey=key;host.append(control);}};
 try{
  const value=await request(url);if(!current())return;
  if(reinspected)view.body.append(el('p','Reinspected owner reading','source-inspector-note'));
  if(expected.facet==='source-inventory'){
   if(value?.schema_version!=='laplace.source-owner-inventory/1'||!sameReference(value.reference,expected.reference))throw Error('The source inventory does not match this issued owner.');if(value.state==='UNAVAILABLE'&&value.basis===null){factText(view.body,'Declared source inputs unavailable',value.reason_code||'No exact source description is available.');if(value.kernel)factText(view.body,'Kernel correspondence',value.kernel);view.body.append(details('Exact unavailable observation',value,{isCurrent:current}));inspector.pin(token,{handle:issued,focusKey});view.status.textContent='';focusReturn.finish();return view.node;}if(!PIN.test(value.basis||'')||expected.as_of&&value.basis!==expected.as_of)throw Error('The source inventory does not match this issued observation.');
   factText(view.body,'Declared source inputs',value.coverage?.qualification);view.body.append(el('p',String(value.state)+' · '+value.coverage.returned+' returned of '+value.coverage.known+' declared inputs'));
   for(const item of value.items||[]){const card=el('section','','source-inspector-card');card.append(el('h3',item.path),el('p',(item.roles||[]).join(' · ')));if(item.read?.http){const key=openerKey('Read exact source input',{request:item.read.payload},{reference:value.reference,basis:value.basis,path:item.path,sha256:item.sha256,http:item.read.http}),body=button('Read exact source input',async()=>{try{const {qualifiedOwnerHTTP}=await import('./writing-owner-read.mjs');if(!current())return;const project=new URL(item.read.http.url,here()).searchParams.get('project'),target=qualifiedOwnerHTTP(item.read,project);if(!target?.owner)throw Error('No existing qualified human source reader is available.');const {openArtifact}=await import('./writing-artifact.mjs');if(current()){focusKey=key;inspector.pin(token,{handle:issued,focusKey});return openArtifact({project,ownerRead:item.read,label:item.path,request,isCurrent:inspector.lineage(token)});}}catch(error){if(current())view.status.textContent=error.message;}});body.dataset.sourceReadKey=key;card.append(body);}else card.append(el('p',item.read_unavailable||'No human body read was issued at this scope; exact SDK/native coordinates remain in the input details.','source-inspector-note'));card.append(details('Exact declared input and read',item,{isCurrent:current}));view.body.append(card);}
   for(const contract of value.contracts||[])link(view.body,'Inspect retained publications · '+(contract.reference?.identity?.operation||'Source contract'),contract.source_kernel_read);
   if(value.pagination?.next_read){if(value.pagination.next_read.request.as_of!==value.basis)throw Error('The inventory continuation does not keep this observation cut.');link(view.body,'More declared source inputs',value.pagination.next_read);}
   if(value.kernel)factText(view.body,'Kernel correspondence',value.kernel);
  }else{
   if(value?.schema_version!=='laplace.source-kernel/1')throw Error('The Source owner returned an unsupported view.');
   if(expected.selection&&!equal(value.selection,expected.selection))throw Error('The retained reading names another Work/handoff/obligation.');
   if(value.reference&&expected.reference&&!sameReference(value.reference,expected.reference))throw Error('The Source reading names another contract or retained version.');
   if(expected.namespace&&value.scope?.namespace!==expected.namespace)throw Error('The Source observation names another scope.');
   switch(value.state){
    case 'CONTRACTS':
     if((expected.view||'publications')!=='contracts'||!Array.isArray(value.contracts))throw Error('The Source chooser does not match its issued view.');
     view.body.append(el('h3','Declared Source contracts'));
     for(const row of value.contracts){if(!sameReference(row.declaration_read?.request?.reference,row.reference)||!sameReference(row.publications_read?.request?.reference,row.reference)||row.declaration_read.request.view!=='declaration'||(row.publications_read.request.view||'publications')!=='publications'||row.inventory_read?.request?.reference?.identity?.id!==row.reference?.owner)throw Error('The contract chooser links name another owner.');const card=el('section','','source-inspector-card');card.append(el('h3',row.reference?.identity?.operation||'Source contract'),el('p',row.purpose));link(card,'Inspect owner declaration',row.declaration_read);link(card,'Select retained publication',row.publications_read);link(card,'Read declared source inputs',row.inventory_read,row.reference);view.body.append(card);}break;
    case 'DECLARATION':{
     const d=value.declaration;if(expected.view!=='declaration'||!sameReference(d?.reference,expected.reference))throw Error('The declaration belongs to another Source owner.');
     const up=value.up_read;
     if(up){sourceOwnerReadURL(up,{facets:['source-kernel']});if(up.request?.view!=='declaration'||up.request.select!==undefined||up.request.reference?.version||!sameReference(up.request.reference,expected.reference)||expected.namespace&&up.request.namespace!==expected.namespace)throw Error('The declaration return read names another operation or scope.');}
     if(expected.select){
      if(!up)throw Error('The selected current constituent has no issued overview read.');
      const [selectedKind,selectedId]=expected.select.split(':');
      if(!['segment','step'].includes(selectedKind)||d.selected!==expected.select||d.item?.id!==selectedId||d.state!=='CURRENT_DECLARATION'||expected.reference?.version)throw Error('The response does not name this current declaration constituent.');
      if(!PIN.test(issued.observation?.declaration||''))throw Error('The current constituent has no qualified observed declaration.');
      if(!matchingObservation(d,issued.observation,expected.select)){
       view.heading.textContent='Current declaration changed';view.body.append(el('p','The current version or selected basis differs from the observation you chose. No constituent facts are displayed. Reinspect the operation before choosing again.','source-inspector-note'));link(view.body,'Reinspect current declaration',up);view.body.append(details('Exact owner response and read basis',{state:'CURRENT_OBSERVATION_CHANGED',selected:issued.observation,returned:d.reference?.version,returned_basis:d.item?.basis,reference:d.reference,scope:value.scope,read:issued.request,up_read:up},{isCurrent:current}));inspector.pin(token,{handle:issued,focusKey});view.status.textContent='';focusReturn.finish();return view.node;
      }
      const kind=expected.select.split(':')[0];view.heading.textContent='Current '+(kind==='step'?'step':'part')+' · '+partName(d.item.id);view.body.append(el('p','Current declaration · matched the version'+(kind==='segment'?' and semantic basis':'')+' you selected. Reading does not execute, approve or publish this operation.','source-inspector-note'));
      if(kind==='segment')renderPartFacts(view.body,d.item.facts,current);else{factText(view.body,'What this step changes',d.item.effect);factText(view.body,'Required guard',d.item.guard);view.body.append(details('Exact declared primitive and step',d.item,{isCurrent:current}));}
      link(view.body,'Up to operation overview',up);if(d.authority)view.body.append(details('Owner authority',d.authority,{isCurrent:current}));if(d.recovery)view.body.append(details('Interruption and recovery',d.recovery,{isCurrent:current}));break;
     }
     const template=value.constituent_read,parts=[],steps=[];
     if(template){
      if(template.observation?.declaration!==d.reference?.version?.declaration||!sameReference(d.reference,template.request?.reference)||!sameReference(template.request?.reference,expected.reference)||expected.namespace&&template.request?.namespace!==expected.namespace)throw Error('The constituent choices do not match this declaration observation.');
      for(const [kind,rows,into]of [['segment',d.segments||[],parts],['step',d.steps||[],steps]])for(const row of rows){const select=row.next?.select;if(select!==kind+':'+row.id)throw Error('The named constituent selector is incomplete.');const read=sourceConstituentRead(template,select);if(read.request.select!==select||kind==='segment'&&template.observation.segment_bases[row.id]!==row.basis)throw Error('The constituent choice has another semantic basis.');into.push({id:row.id,read});}
     }
     view.heading.textContent='Operation declaration';view.body.append(el('h3',d.state==='CURRENT_DECLARATION'?'Current owner declaration':'Addressed retained declaration'));factText(view.body,'What this operation does',d.purpose?.text||d.purpose);view.body.append(el('p','Choose one named part or step to read its declared facts. Selection is not review acceptance, execution authority or kernel publication.','source-inspector-note'));
     if(parts.length){const list=el('div','','source-inspector-part-list');for(const row of parts)link(list,'Read part: '+partName(row.id),row.read);view.body.append(el('h3','Named parts'),list);}
     if(steps.length){const box=el('details','','material-disclosure'),label=el('summary','How this operation proceeds ('+steps.length+' steps)'),list=el('div','','source-inspector-part-list');for(const row of steps)link(list,'Read step: '+partName(row.id),row.read);box.append(label,list);view.body.append(box);}
     if(d.authority)view.body.append(details('Who may act? Owner authority',d.authority,{isCurrent:current}));if(d.recovery)view.body.append(details('After interruption: owner recovery',d.recovery,{isCurrent:current}));link(view.body,'Select retained publication',d.source_kernel_read);if(d.standing)renderStanding(view.body,d.standing,current);break;}
    case 'PUBLICATIONS':
     if((expected.view||'publications')!=='publications'||!Array.isArray(value.publications))throw Error('The owner did not return the requested retained publications.');
     view.body.append(el('h3','Explicit retained kernel-consumer publications'),el('p','Choose an actual Work, handoff and obligation. An empty list means no eligible publication is available in this scope.','source-inspector-note'));
     for(const [index,row]of value.publications.entries()){const card=el('section','','source-inspector-card'),s=row.selection;if(!object(s)||!equal(row.read?.request?.selection,s)||row.read.request.view!=='prepare'||!sameReference(row.read.request.reference,value.reference)||row.read.request.reference?.version?.declaration!==row.version)throw Error('The publication has no exact retained selection read.');if(!Array.isArray(row.segments)||!row.segments.length||row.read.request.segments&&(!Array.isArray(row.read.request.segments)||row.read.request.segments.some(name=>!row.segments.includes(name))))throw Error('The offered read does not name retained parts from this publication.');card.append(el('h3','Retained meaning'+(value.publications.length>1?' '+(index+1):'')+' · '+(row.title||s.work_id)),el('p',row.segments.length+' parts retained · '+(row.read.request.segments?.length??row.segments.length)+' selected in the offered reading'));link(card,'Inspect selected retained meaning',row.read);card.append(details('Exact project, Work and handoff selection',s,{isCurrent:current}),details('Exact retained part names',row.segments,{isCurrent:current}));view.body.append(card);}if(!value.publications.length)view.body.append(el('p','No eligible retained publication. No kernel leaf was prepared or created.'));break;
    case 'PREPARED':{
     if(!['prepare','counterpart'].includes(expected.view)||!Array.isArray(value.leaves))throw Error('The prepared metadata does not match the selected reading.');
     const selectedParts=value.leaves.map(leaf=>leaf.segment),requestedParts=expected.segments,navigation=value.segment_navigation;
     if(!selectedParts.length||selectedParts.some(part=>typeof part!=='string'||!part)||new Set(selectedParts).size!==selectedParts.length||requestedParts!==undefined&&(!Array.isArray(requestedParts)||!requestedParts.length||new Set(requestedParts).size!==requestedParts.length||!equal([...requestedParts].sort(),[...selectedParts].sort())))throw Error('The prepared parts do not match the exact issued selection.');
     if(navigation&&(!Number.isSafeInteger(navigation.known)||navigation.known<1||navigation.selected!==selectedParts.length||navigation.selected>navigation.known||!equal(navigation.segments,selectedParts)||requestedParts===undefined&&navigation.selected!==navigation.known))throw Error('The retained segment coverage does not match the issued selection.');
     const counterparts=value.kernel?.state==='PUBLISHED'?value.kernel.counterparts:[];
     if(value.kernel?.state==='PUBLISHED'&&(!Array.isArray(counterparts)||!counterparts.length))throw Error('Published counterpart metadata is incomplete.');
     const publication=value.kernel?.state==='PUBLISHED'?publicationSummary(value.kernel.publication,value.selection):null;
     for(const counterpart of counterparts){const leaf=value.leaves.find(row=>row.id===counterpart.id),read=counterpart.read?.request;if(!leaf||!NODE.test(counterpart.id||'')||leaf.content_handle!==counterpart.content_handle||leaf.semantic_handle!==counterpart.semantic_handle||!PIN.test(counterpart.content_handle||'')||!PIN.test(counterpart.semantic_handle||'')||counterpart.publication_handle!==publication.publication_handle||read?.view!=='recover'||read.namespace!==value.selection.namespace||read.node_id!==leaf.id||read.content_handle!==leaf.content_handle||read.semantic_handle!==leaf.semantic_handle||read.publication_handle!==counterpart.publication_handle||!sameReference(read.reference,value.reference)||!equal(read.segments,[leaf.segment])||!equal(read.selection,value.selection))throw Error('The exact active-publication recovery read does not identify this selected leaf.');sourceOwnerReadURL(counterpart.read,{facets:['source-kernel']});}
     view.heading.textContent='Retained Source';const summary=el('section','','source-inspector-summary');if(value.purpose?.text)summary.append(el('p',value.purpose.text));summary.append(el('h3','Kernel counterpart'));if(publication)renderPublication(summary,publication,current);else summary.append(el('p','Unresolved — no verified current publication for this selection.','source-inspector-state'));summary.append(el('p','Retained Work '+[value.selection.namespace,value.selection.work_id].filter(Boolean).join(' · ')+' · obligation '+value.selection.obligation_id),details('Exact retained project and Work',{scope:value.scope,selection:value.selection,reference:value.reference},{isCurrent:current}),el('p','Prepared metadata · '+value.leaves.length+' selected segment'+(value.leaves.length===1?'':'s'),'source-inspector-note'));
     const controls=el('div','','source-inspector-controls');
     if(value.view_read){for(const key of Object.keys(value.view_read.values||{})){const read=sourceSiblingRead(value.view_read,key),target=retainedTarget(read,value,read.request.view,{single:false});if(!equal(target,value.leaves.map(leaf=>leaf.segment)))throw Error('The sibling read changes the selected retained part.');link(controls,read.request.view==='standing'?'Read current owner standing separately':'Check published counterpart',read);}}
     else{link(controls,'Read current owner standing separately',value.current_standing_read);link(controls,'Check published counterpart',value.counterpart_read);}
     if(navigation){
      summary.append(el('p',navigation.known+' parts retained · '+navigation.selected+' selected','source-inspector-state'));
      if(navigation.selected===1){if(navigation.segment!==navigation.segments[0]||!Number.isSafeInteger(navigation.position)||navigation.position<0||navigation.position>=navigation.known)throw Error('The selected retained position is invalid.');summary.append(el('p','Retained part '+(navigation.position+1)+' of '+navigation.known+' · '+partName(navigation.segment)));
       for(const [key,label]of [['previous_read','Previous retained part'],['next_read','Next retained part']])if(navigation[key]){const target=retainedTarget(navigation[key],value,'prepare');if(target===navigation.segment)throw Error('The retained part navigation does not advance.');link(controls,label+' · '+partName(target),navigation[key]);}}
      const up=navigation.up_read;sourceOwnerReadURL(up,{facets:['source-kernel']});if(up.request.view!=='publications'||up.request.namespace!==value.selection.namespace||!sameReference(up.request.reference,value.reference)||up.request.selection||up.request.segments)throw Error('The retained up read names another publication scope.');link(controls,'Up to retained publications',up);
     }
     summary.append(controls);view.body.append(summary);
     for(const leaf of value.leaves){if(!PIN.test(leaf.basis||'')||!PIN.test(leaf.content_handle||'')||!equal(leaf.retained_read?.request?.selection,value.selection)||!sameReference(leaf.retained_read?.request?.reference,value.reference)||leaf.retained_read.request.view!=='segment'||!equal(leaf.retained_read.request.segments,[leaf.segment]))throw Error('The retained segment read does not match this selected leaf.');const card=el('section','','source-inspector-card');card.append(el('h3',leaf.segment));link(card,'Read retained facts · '+leaf.segment,leaf.retained_read);card.append(details('Exact leaf, raw-input and relation metadata',leaf,{isCurrent:current}));view.body.append(card);}
     for(const counterpart of counterparts){const leaf=value.leaves.find(row=>row.id===counterpart.id);link(view.body,'Recover exact published meaning · '+leaf.segment,counterpart.read);}
     break;}
    case 'RETAINED_SEGMENT':
     if(expected.view!=='segment'||!equal(expected.segments,[value.segment])||!PIN.test(value.basis||''))throw Error('The retained facts name another selected segment.');view.heading.textContent='Retained part · '+partName(value.segment);view.body.append(el('p','Exact handed version · this reading does not replace the current declaration or establish kernel publication.','source-inspector-note'));renderPartFacts(view.body,value.facts,current);break;
    case 'CURRENT_STANDING':
     if(expected.view!=='standing')throw Error('This is not the requested current-standing read.');renderStanding(view.body,value.standing,current);view.body.append(el('p','This current observation does not replace retained facts or prove kernel publication.','source-inspector-note'));break;
    case 'RECOVERED':
     if(expected.view!=='recover'||!NODE.test(expected.node_id||'')||![expected.publication_handle,expected.content_handle,expected.semantic_handle].every(value=>PIN.test(value||''))||value.node_id!==expected.node_id||value.content_handle!==expected.content_handle||value.semantic_handle!==expected.semantic_handle||value.publication_handle!==expected.publication_handle||!object(value.facts))throw Error('The recovered facts do not match the exact offered active publication and selected node.');publicationSummary(value.publication,value.selection,expected.publication_handle);view.heading.textContent='Recovered Source';renderPublication(view.body,value.publication,current);factText(view.body,'Recovered exact retained meaning',value.facts);view.body.append(el('p','Exact published leaf recovery is separate from Source review acceptance, authored checkpoint closure, adoption and executable authority.','source-inspector-note'));break;
    default:throw Error('The Source owner returned an unsupported standing.');
   }
  }
  view.body.append(details('Scope and reading limits',{scope:value.scope,qualification:value.qualification,kernel:value.kernel,reinspected:reinspected?'Current standing may differ; retained facts keep their addressed version.':null,meaning:'Source facts, retained handed meaning and verified kernel recovery are separate. These reads do not ingest, fold, approve or grant an effect.'},{isCurrent:current}),details('Exact owner response and read basis',value,{isCurrent:current}));inspector.pin(token,{handle:issued,focusKey});view.status.textContent='';focusReturn.finish();
 }catch(error){focusReturn?.dispose();if(current()){view.body.replaceChildren(el('p','No qualified Source reading is displayed. Previous owner records and drafts are unchanged.','source-inspector-note'));view.status.textContent=error.message;}}
 return view.node;
}

export async function openHistoricalObligations({handle,title='Historical engine obligations',request=projectRequest,isCurrent=()=>true,snapshotCut=null,returnFocus=null}={}){
 const url=sourceOwnerReadURL(handle,{facets:['historical-obligations']}),issued=clone(handle),expected=issued.request,view=panel(title),inspector=sharedInspector();view.node.dataset.control='backlog:historical';let alive=true,ticket=0,focusReturn=null,focusKey=returnFocus;
 view.node.onclose=()=>{alive=false;ticket++;focusReturn?.dispose();view.node.remove();};
 const token=inspector.adopt(view.node,{kind:'owner-read',title,reopen:{factory:reopenHistorical,args:{handle:issued,title,request}}}).token,current=()=>alive&&isCurrent()&&inspector.current?.token===token;
 view.node.showModal();view.close.focus();focusReturn=focusOnReturn(view,returnFocus,current);
 async function read({cached=false}={}){const mine=++ticket;pendingRead(view.status,'Reading this selected historical source…');try{const snapshot=cached?inspector.snapshot(url,snapshotCut):null,value=snapshot?.value||await request(url);if(!current()||mine!==ticket)return;
   if(value?.schema_version!=='laplace.historical-obligations/1'||value.source!==expected.source||!PIN.test(value.read_cut||'')||!['catalogue','record'].includes(value.view))throw Error('The historical owner returned another source or an incomplete observation.');
   if((expected.view||'catalogue')!==value.view||value.view==='record'&&(value.id!==expected.id||value.content_handle!==expected.expected_sha256))throw Error('The returned record does not match the issued identity and content pin.');if(expected.as_of&&value.read_cut!==expected.as_of)throw Error('The historical observation cut changed.');if(value.view==='catalogue'&&(value.state!==(expected.state||'open')||value.pagination?.offset!==(expected.offset||0)))throw Error('The historical owner returned another filter or page.');if(value.view==='record'&&value.content_offset!==(expected.content_offset||0))throw Error('The record window does not match its issued offset.');
   view.body.replaceChildren();if(snapshot){view.body.append(el('p','Previously inspected historical observation · read-only','source-inspector-note'),button('Read current historical observation',()=>read()));}
   view.body.append(el('p','Historical engine records — separate from canonical app Work. Reading does not migrate, close, prioritise or start anything.','source-inspector-note'));
   const open=async(read,label)=>{try{sourceOwnerReadURL(read,{facets:['historical-obligations']});if(read.request.source!==value.source)throw Error('The historical read changes its selected source.');return await openHistoricalObligations({handle:read,title:label,request,isCurrent:inspector.lineage(token)});}catch(error){if(current())view.status.textContent=error.message;}};
   const link=(host,label,next)=>{const key=openerKey(label,next),control=button(label,()=>{focusKey=key;inspector.pin(token,{handle:issued,cut:payloadCut(value),focusKey});return open(next,label);});control.dataset.sourceReadKey=key;host.append(control);};
   if(value.view==='catalogue'){
    if(!Array.isArray(value.rows)||value.rows.some(row=>row.canonical_app_work!==false))throw Error('Historical records must remain separate from canonical Work.');
    view.body.append(el('h3',value.title||'Historical engine records'),el('p',value.coverage.returned+' returned · '+value.coverage.matching+' matching · '+value.coverage.known+' known in this selected source'));if(value.coverage.source_available===false)view.body.append(el('p','Selected engine source is absent. Zero rows do not establish an empty recorded history.','source-inspector-note'));if(value.coverage.malformed_rows||value.coverage.incomplete_tail)view.body.append(el('p','Partial source coverage: '+value.coverage.malformed_rows+' malformed rows'+(value.coverage.incomplete_tail?' · incomplete final row':'')+'. Exact usable rows remain inspectable.','source-inspector-note'));
    const states=el('div','','source-inspector-controls');for(const state of value.states||[])link(states,String(state.value),state.read);view.body.append(states);
    for(const row of value.rows){sourceOwnerReadURL(row.read,{facets:['historical-obligations']});if(row.read.request.source!==value.source||row.read.request.id!==row.id)throw Error('The historical row has another record read.');const section=el('section','','source-inspector-card');link(section,row.title||row.id,row.read);section.append(el('p','Historical record · '+row.id+' · effective '+row.state+' at this read · recorded '+row.recorded_status));view.body.append(section);}
    if(!value.rows.length)view.body.append(el('p','No records match this selected source and effective status.'));
    if(value.pagination?.next_read){const next=value.pagination.next_read;if(next.request.as_of!==value.read_cut)throw Error('The continuation is not pinned to this historical observation.');link(view.body,'More historical records',next);}
    if(value.coverage.qualification)view.body.append(el('p',value.coverage.qualification,'source-inspector-note'));
   }else{
    if(typeof value.content!=='string'||!Number.isSafeInteger(value.content_offset)||!Number.isSafeInteger(value.content_bytes))throw Error('The exact historical record has no bounded text window.');
    view.body.append(el('h3',value.id),el('p',value.content_status+' · byte window starts '+value.content_offset+' of '+value.content_bytes),el('pre',value.content,'source-inspector-facts'));
    if(value.next_read){if(value.next_read.request.id!==value.id||value.next_read.request.expected_sha256!==value.content_handle||!Number.isSafeInteger(value.content_next_offset)||value.content_next_offset<=value.content_offset||value.content_next_offset>value.content_bytes||value.next_read.request.content_offset!==value.content_next_offset)throw Error('The next window changes the original record pin or extent.');link(view.body,'Read next exact record window',value.next_read);}
   }
   if(value.qualification)view.body.append(el('p',value.qualification,'source-inspector-note'));view.body.append(details('Exact historical observation and coverage',value,{isCurrent:current}));inspector.remember(url,value);inspector.pin(token,{handle:issued,cut:payloadCut(value),focusKey});view.status.textContent='';focusReturn.finish();
  }catch(error){focusReturn?.dispose();if(current()&&mine===ticket)view.status.textContent=error.message;}}
 await read({cached:snapshotCut!==null});return view.node;
}
