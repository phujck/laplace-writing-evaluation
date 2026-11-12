import {mountGlobalHelp} from './workspace-help-door.mjs';
// One local-file chooser presentation shared by Material and the conversation door.
// Transport and standing are supplied by the scoped intake controller, never inferred
// from the chosen filename, progress events or a closed dialog.
import {createLocalDocumentDraft,inspectLocalDocument,sameLocalDocument,intakeReadURL,intakeHTTP,intakeStatusHandle,retainIntakeSubmission,intakeSubmissionMetadata,uploadLocalDocument,materialReadingInput,intakeDocumentReadURL,intakeOriginalURL,inspectedIntakeReading,focusIntakeDestination} from './local-document-intake-port.mjs';
import {sharedInspector} from './workspace-inspector.mjs';
import {renderMaterialObservation,documentReadingCoverage} from './workspace-material-observation.mjs';
import {openPdf} from './writing-pdf.mjs';
import {pendingRead} from './pending-read.mjs';
const copy=value=>JSON.parse(JSON.stringify(value));
const el=(tag,text='',cls='')=>{const node=document.createElement(tag);node.textContent=text;node.className=cls;return node;};
// Human outcome labels are derived from the recorded result, never a substitute
// for retain/link state or the original pending request.
export function documentIntakeOutcome(value){
 if(value?.state==='UNKNOWN')return 'The document result is still unknown. Check the original request.';
 if(value?.state==='NONE')return 'No saved result was found. The original request is kept.';
 if(value?.state==='PARTIAL')return value.original?.state==='RETAINED'?'Original file saved. Some requested steps are unfinished; see the result below.':'Some requested steps are unfinished; see the result below.';
 if(value?.state==='RECORDED'&&value.original?.state==='RETAINED')return ['LINKED','OBSERVED'].includes(value.membership?.state)?'Document saved and available in Sources.':'Original file saved. Check its Sources entry below.';
 return 'Document result received. Check the result below.';
}
export function renderLocalDocumentChoice(host,{project,projectTitle=null,selection=null,onChoose,onMediaChange,disabled=false}){
 const form=el('fieldset','','local-document-choice');form.disabled=disabled;
 form.append(el('legend','Local document'),el('p','Add to '+(projectTitle||project),'local-document-destination'));
 const fileLabel=el('label','Choose a PDF or UTF-8 document'),file=el('input');file.type='file';file.accept='.pdf,.txt,.md,.markdown,.log,text/plain,text/markdown,application/pdf';file.setAttribute('aria-label','Choose a PDF or UTF-8 document');fileLabel.append(file);
 const typeLabel=el('label','Document type'),type=el('select');type.setAttribute('aria-label','Document type');
 for(const [value,label]of [['text/plain; charset=utf-8','UTF-8 text or transcript'],['application/pdf','PDF']]){const option=el('option',label);option.value=value;type.append(option);}
 type.value=selection?.media_type||'text/plain; charset=utf-8';typeLabel.append(type);
 const selected=el('p','','local-document-selected');selected.setAttribute('role','status');
 if(selection)selected.textContent=selection.display_name+' · '+selection.size.toLocaleString()+' bytes · '+(selection.media_type==='application/pdf'?'PDF':'UTF-8 text');
 else selected.textContent='No local file selected.';
 file.onchange=()=>{const chosen=file.files?.[0];if(!chosen)return;type.value=chosen.type==='application/pdf'||/\.pdf$/i.test(chosen.name)?'application/pdf':'text/plain; charset=utf-8';return onChoose(chosen,type.value);};
 type.onchange=()=>onMediaChange(type.value);
 form.append(fileLabel,typeLabel,selected);host.append(form);return {element:form,file,type};
}
export function renderLocalDocumentProgress(host,{phase,message,loaded=null,total=null}){
 host.replaceChildren();const note=el('p',message);note.setAttribute('role','status');host.append(note);
 if(phase==='transferring'){
  const progress=el('progress');progress.setAttribute('aria-label','Document transfer');
  if(Number.isFinite(loaded)&&Number.isFinite(total)&&total>0){progress.max=total;progress.value=loaded;}
  host.append(progress);
 }
}

const reopenIntake=args=>openLocalDocumentIntake(args);
export async function openLocalDocumentIntake({project,projectTitle=null,request,draft=createLocalDocumentDraft({project}),onUse=null,onMaterial=null,returnTarget=null,isCurrent=()=>true,upload=uploadLocalDocument}){
 if(!isCurrent())return;
 if(!document.querySelector('[data-local-document-intake-style]')){const style=el('link');style.rel='stylesheet';style.href='/shared/local-document-intake.css';style.dataset.localDocumentIntakeStyle='true';document.head.append(style);}
 const dialog=el('dialog','','workspace-dialog local-document-intake'),heading=el('h2','Add local document'),close=el('button','Close document intake'),note=el('div'),choice=el('section'),options=el('section'),controls=el('div','','local-document-actions'),result=el('section'),reading=el('section');
 dialog.setAttribute('aria-label','Add local document');close.type='button';close.onclick=()=>dialog.close();dialog.append(heading,close,note,choice,options,controls,result,reading);dialog.addEventListener('keydown',event=>event.stopPropagation());
 let owner=null,busy=false,closed=false,inspecting=false,selectionTicket=0,readTicket=0,reader=null,linkBasis=null,focusVersion=0,selectedReading=null,useButton=null,readingIssue=null;
 dialog.addEventListener('focusin',()=>focusVersion++);dialog.addEventListener('pointerdown',()=>focusVersion++);
 const live=()=>!closed&&dialog.open!==false&&dialog.isConnected!==false&&isCurrent();
 dialog.onclose=()=>{help.dispose();closed=true;selectionTicket++;readTicket++;reader?.destroy();dialog.remove();};document.body.append(dialog);
 // A fresh explicit reading action owns its opening target; persisted return_target
 // remains the immutable upload/recovery origin. Back reuses this captured basis.
 const useTarget=copy(returnTarget);
 const inspector=sharedInspector(),token=inspector.adopt(dialog,{kind:'local-document-intake',title:'Local document',reopen:{factory:reopenIntake,args:{project,projectTitle,request,draft,onUse,onMaterial,returnTarget:useTarget,isCurrent,upload}}}).token;dialog.showModal();close.focus();const help=mountGlobalHelp(dialog,{navigation:dialog,project,view:'document-intake',shortcut:false,request,isCurrent:live});close.after(dialog.querySelector('[data-control="help:guide"]'));
 const closeTo=destination=>{if(!inspector.closeTo(token,()=>focusIntakeDestination(destination,{isCurrent})))throw Error('This inspection was replaced. The document and its reading selection are retained.');};
 const report=(message,error=false)=>{if(!live())return;renderLocalDocumentProgress(note,{message});note.className=error?'error':'';};
 const button=(label,action)=>{const node=el('button',label);node.type='button';node.onclick=async()=>{if(busy||!live())return;const heldFocus=document.activeElement===node,version=focusVersion;busy=true;paintChoice();paintControls();try{await action();}catch(error){report(error.message,true);}finally{busy=false;if(live()){paintChoice();paintControls();if(heldFocus&&focusVersion===version){const replacement=[...dialog.querySelectorAll('button')].find(item=>item.textContent===label&&!item.disabled);if(replacement)replacement.focus({preventScroll:true});}}}};return node;};
 const equal=(a,b)=>JSON.stringify(Object.fromEntries(Object.entries(a).sort()))===JSON.stringify(Object.fromEntries(Object.entries(b).sort()));
 function validateStanding(value,pending){
  if(value?.schema_version!=='laplace.material-intake-result/1'||value.project!==project||value.request_id!==pending.request_id||!['RECORDED','PARTIAL','NONE','UNKNOWN'].includes(value.state))throw Error('The document owner returned another request or an incomplete standing.');
  if(value.intent){const original=JSON.parse(pending.wire),observed=copy(value.intent);for(const item of [original,observed])item.expected_sha256=String(item.expected_sha256).replace(/^sha256:/,'');if(!equal(original,observed))throw Error('The retained document standing describes a different original intent.');}
  if(value.original?.state==='RETAINED'){
   const meta=JSON.parse(pending.wire),original=value.original;
   if(String(original.sha256).replace(/^sha256:/,'')!==meta.expected_sha256.replace(/^sha256:/,'')||original.bytes!==meta.declared_size||original.media_type!==meta.media_type||original.target&&original.target.project!==project||original.artifact_publication==='RECORDED'&&!original.artifact_id)throw Error('The retained original does not match the selected document.');
  }
  return value;
 }
 function accept(value,pending){
  validateStanding(value,pending);const held=draft.snapshot();
  if(held.pending?.wire_sha256!==pending.wire_sha256)return;
  if(['NONE','UNKNOWN'].includes(value.state)&&held.standing?.original?.state==='RETAINED'){
   draft.update({latest_check:copy(value)});if(live())paint();return;
  }
  draft.update({pending:{...held.pending,observation:value.state},standing:copy(value),latest_check:null});
  readingIssue=null;try{selectedReading=held.reading?inspectedIntakeReading(held.reading,value.original,{project}).pointer:value.original?.material_read?materialReadingInput(value.original.material_read,{project}):null;}catch(error){selectedReading=null;readingIssue=error.message;}
  if(value.original?.state==='RETAINED')draft.releaseFile();
  if(live())paint();
 }
 async function describe(){
  const value=await request(intakeReadURL(project));if(!live())return null;
  if(value?.schema_version!=='laplace.material-intake/1'||value.project!==project||typeof value.project_revision!=='string'||!value.project_revision||!value.metadata||!value.actions?.upload||!value.limits)throw Error('The document owner supplied no preparation for this project.');
  owner=value;return value;
 }
 async function choose(file,mediaType){
  const ticket=++selectionTicket;inspecting=true;paintControls();report('Checking the selected document…');pendingRead(note);
  try{
   const pending=draft.snapshot().pending,original=pending?await intakeSubmissionMetadata(pending):null;
   const maximum=original&&original.media_type===mediaType?original.declared_size:owner?.limits?.[mediaType];
   const identity=await inspectLocalDocument(file,mediaType,maximum);if(!live()||ticket!==selectionTicket)return;
   const held=draft.snapshot();if(held.pending){const metadata=await intakeSubmissionMetadata(held.pending),expected={display_name:metadata.display_name,media_type:metadata.media_type,size:metadata.declared_size,sha256:'sha256:'+metadata.expected_sha256.replace(/^sha256:/,'')};if(!sameLocalDocument(identity,expected))throw Error('This is not the exact original file. The retained document request is unchanged.');}
   draft.retainFile(file,identity);draft.update({selection:identity});paint();report(held.pending?'Original bytes selected for an explicit same-request retry.':'Document checked. Add retains its original bytes; it sends no message.');
  }catch(error){if(live())paintChoice();report(error.message,true);}finally{if(ticket===selectionTicket){inspecting=false;if(live())paintControls();}}
 }
 function paintChoice(){
  choice.replaceChildren();const held=draft.snapshot();renderLocalDocumentChoice(choice,{project,projectTitle,selection:held.selection,disabled:busy||!owner&&!held.pending,onChoose:choose,onMediaChange:async type=>{const file=draft.selectedFile(held.selection);if(file)await choose(file,type);else report('Choose the original file to inspect this document type.',true);}});
  options.replaceChildren();const label=el('label'),link=el('input');link.type='checkbox';link.checked=held.attach_material!==false;link.disabled=busy||!!held.pending;link.onchange=()=>draft.update({attach_material:link.checked});label.append(link,document.createTextNode(' Show this document in Sources'));options.append(label);
 }
 function paintControls(){
  controls.replaceChildren();const held=draft.snapshot(),pending=held.pending,standing=held.standing;
  if(!pending){const add=button('Add document',addDocument);add.disabled=busy||inspecting||draft.damaged||!held.selection||!draft.selectedFile(held.selection)||owner?.actions?.upload?.permitted!==true;controls.append(add);if(!owner)controls.append(button('Inspect document intake',async()=>{await describe();paint();report('Document destination inspected.');}));else if(owner.actions.upload.permitted!==true)controls.append(el('p',owner.actions.upload.reason||'Adding documents is unavailable for this project.','muted'));}
  else{
   controls.append(button('Check document request',check));
   if(pending.observation==='NONE'||standing?.actions?.retry_upload?.permitted){const retry=button('Retry same document',post);retry.disabled=busy||!draft.selectedFile(held.selection);controls.append(retry);if(!draft.selectedFile(held.selection))controls.append(el('p','Reselect the exact original file only if the owner still needs its bytes.','muted'));}
   if(standing?.actions?.link?.permitted&&!held.latest_check){controls.append(button('Check project before adding to Sources',async()=>{const path=intakeHTTP(standing.actions.link.inspect_destination,{project,paths:['/projects/material-intake']}),value=await request(path);if(!live())return;if(value?.schema_version!=='laplace.material-intake/1'||value.project!==project||typeof value.project_revision!=='string')throw Error('The owner supplied no current project destination.');linkBasis=value.project_revision;report('Project checked. Add saved original to Sources uses this inspected version.');paintControls();}));if(linkBasis)controls.append(button('Add saved original to Sources',linkRetained));}
   if(standing?.state==='RECORDED'){controls.append(button('Add another document',async()=>{if(!await describe())return;draft.releaseFile();draft.update({previous:standing,selection:null,pending:null,standing:null,return_target:null,reading:null});linkBasis=null;reader?.destroy();reader=null;reading.replaceChildren();paint();report('Choose another local document. The earlier original remains retained.');}));}
  }
  for(const node of controls.querySelectorAll('button'))if(busy)node.disabled=true;
 }
 function paintResult(){
  result.replaceChildren();const held=draft.snapshot(),value=held.standing;if(!value)return;
  const original=value.original;result.append(el('h3',original?.display_name||held.selection?.display_name||'Document'));
  if(held.latest_check)result.append(el('p','Earlier retained-original receipt preserved. The latest check did not establish current standing.','muted'));
  result.append(el('p',original?.state==='RETAINED'?(held.latest_check?'The original file was saved at the earlier receipt.':'Original file saved.'):value.state==='NONE'?'No recorded outcome was found at this check. The original request is retained.':'The original document outcome is not yet confirmed.'));
  if(original?.state==='RETAINED'){
   const membershipText=({LINKED:'Available in Sources.',OBSERVED:'Matching entry found in Sources.',NOT_REQUESTED:'Original saved without a Sources entry.',PENDING:'Adding it to Sources is still pending.',REMOVED:'Its Sources entry has since been removed.',UNAVAILABLE:'Its Sources entry could not be checked.'})[value.membership?.state]||'Its Sources entry is not confirmed.';
   result.append(el('p',(held.latest_check?'Earlier membership observation: ':'')+membershipText));
   const actions=el('div','','local-document-actions');
   if(original.literature){const add=button('Add to Literature',async()=>{const {openRetainedSourceLiterature}=await import('./retained-source-literature.mjs');if(live())return openRetainedSourceLiterature({project,read:copy(original.literature),request,isCurrent});});add.dataset.control='material:add-literature';add.dataset.controlOwner=project+'::'+original.artifact_id;actions.append(add);}
   if(onMaterial&&original.artifact_id)actions.append(button('View in Sources',()=>{const destination=onMaterial();closeTo(()=>destination);}));
   if(original.original_read){const path=intakeOriginalURL(original.original_read,{project,artifactId:original.artifact_id,sha256:original.sha256});if(original.media_type==='application/pdf')actions.append(button('Open original PDF',()=>openPdf(path,original.display_name)));else{const anchor=el('a','Download original');anchor.href=path;anchor.download=original.display_name;actions.append(anchor);}}
   if(original.text_read)actions.append(button(original.media_type==='application/pdf'?'Inspect PDF text':'Inspect document text',()=>inspectText(original.text_read)));
   if(original.page_image_read)actions.append(button('Inspect first PDF page',()=>inspectImage(original.page_image_read)));
   if(onUse&&original.material_read){useButton=button('Use in conversation',async()=>{if(!selectedReading)throw Error('Inspect the document reading before selecting it for this conversation.');const version=focusVersion,destination=await onUse(copy(selectedReading),original.display_name,copy(useTarget));if(live()&&focusVersion===version)closeTo(()=>destination);});useButton.disabled=!selectedReading;actions.append(useButton);}
   result.append(actions);
  }
  const details=el('details');details.append(el('summary','Exact document and request details'),el('pre',JSON.stringify(held.latest_check?{earlier_confirmed:value,latest_check:held.latest_check}:value,null,2)));result.append(details);
 }
 function paint(){if(!live())return;paintChoice();paintControls();paintResult();if(!reader&&draft.snapshot().reading)paintInspectedReading();}
 function paintInspectedReading(){const held=draft.snapshot(),original=held.standing?.original;if(!original)return;if(readingIssue){reading.replaceChildren(el('h3',original.display_name),el('p',readingIssue,'error'),el('p','The prior selection is preserved. Inspect the document above explicitly before using another reading.','muted'));return;}const saved=inspectedIntakeReading(held.reading,original,{project});const exact=el('details');exact.append(el('summary','Exact inspected reading'),el('pre',JSON.stringify(saved,null,2)));reading.replaceChildren(el('h3',original.display_name),el('p','Last inspected · '+saved.coverage.label,'document-reading-coverage'),el('p','This is the retained reading selection. Reinspection is explicit.','muted'),button('Reinspect selected reading',()=>inspectText(saved.handle)),exact);}
 async function check(){const held=draft.snapshot();if(!held.pending)throw Error('There is no retained document request.');await intakeSubmissionMetadata(held.pending);const value=await request(intakeHTTP(held.pending.status,{project,paths:['/projects/material-intake']}));accept(value,held.pending);report(value.state==='UNKNOWN'?'The original result is still unknown. Keep this request and check again.':'Document request checked.');}
 async function addDocument(){
  const held=draft.snapshot();if(held.pending)throw Error('Check the original document request first.');if(!owner?.actions?.upload?.permitted)throw Error(owner?.actions?.upload?.reason||'Adding documents is unavailable.');
  const selected=held.selection;if(!selected||!draft.selectedFile(selected))throw Error('Choose one local document.');
  if(Array.from(selected.display_name).length>(owner.metadata.properties?.display_name?.maxLength??240))throw Error('The selected filename exceeds the owner’s display-name limit. Choose a suitably named copy.');
  const metadata={request_id:'intake-'+crypto.randomUUID(),display_name:selected.display_name,media_type:selected.media_type,declared_size:selected.size,expected_sha256:selected.sha256,attach_material:held.attach_material!==false,expected_revision:owner.project_revision};
  const status=intakeStatusHandle(owner.actions.status,metadata.request_id,{project}),pending=await retainIntakeSubmission(project,metadata,owner.actions.upload,status);draft.update({pending,standing:null,return_target:copy(returnTarget),reading:null});if(!draft.persist())throw Error(draft.error);await post();
 }
 async function post(){
  const held=draft.snapshot(),pending=held.pending;if(!pending||pending.project!==project)throw Error('The document request belongs to another project.');const metadata=await intakeSubmissionMetadata(pending),file=draft.selectedFile(held.selection);
  if(!file)throw Error('Reselect the exact original document before retrying.');if(!draft.persist())throw Error(draft.error);
  draft.update({pending:{...pending,observation:'UNKNOWN'}});renderLocalDocumentProgress(note,{phase:'transferring',message:'Transferring original document…'});
  try{const value=await upload(pending.action,metadata,file,{project});accept(value,pending);report(documentIntakeOutcome(value));}catch(error){report(error.message+' The original request is retained; check its standing before retrying.',true);throw error;}
 }
 async function linkRetained(){
  const held=draft.snapshot(),action=held.standing?.actions?.link;if(!action||!linkBasis)throw Error('Inspect the project destination before linking.');
  const path=intakeHTTP(action,{project,method:'POST',paths:['/projects/material-intake/link']}),basis=linkBasis;linkBasis=null;
  const value=await request(path,{project,request_id:held.pending.request_id,expected_revision:basis});accept(value,held.pending);report(documentIntakeOutcome(value));
 }
 async function inspectText(handle){
  const ticket=++readTicket,original=draft.snapshot().standing?.original,coordinates={project,artifactId:original?.artifact_id,sha256:original?.sha256},path=intakeDocumentReadURL(handle,coordinates),value=await request(path);if(!live()||ticket!==readTicket)return;
  const pointer=(value.owner_result||value).material_read;
  const observed=pointer?materialReadingInput(pointer,{project}):null;if(!observed||observed.artifact_id!==original?.artifact_id||observed.sha256.replace(/^sha256:/,'')!==String(original.sha256).replace(/^sha256:/,''))throw Error('The reader returned another retained document.');
  const restart=value.restart_read?intakeDocumentReadURL(value.restart_read,{...coordinates,allowCurrent:true}):null;
  reader?.destroy();reading.replaceChildren();reader=renderMaterialObservation(reading,value,{documentLabel:original.display_name,request:path=>request(intakeDocumentReadURL({http:{method:'GET',url:path}},{...coordinates,allowCurrent:path===restart})),isCurrent:()=>live()&&ticket===readTicket,initialHandle:handle,onObservation:observed=>{const next=(observed.owner_result||observed).material_read;if(next){const candidate=materialReadingInput(next,{project});if(candidate.artifact_id!==original.artifact_id||candidate.sha256.replace(/^sha256:/,'')!==String(original.sha256).replace(/^sha256:/,''))throw Error('The source reading changed its document identity.');const selected={pointer:candidate,handle:observed.page_read,coverage:documentReadingCoverage(observed)};inspectedIntakeReading(selected,original,{project});draft.update({reading:selected});readingIssue=null;selectedReading=candidate;if(useButton?.isConnected)useButton.disabled=false;}},onInvalidated:()=>{selectedReading=null;if(useButton?.isConnected)useButton.disabled=true;},onReadError:()=>{selectedReading=null;if(useButton?.isConnected)useButton.disabled=true;}});
 }
 async function inspectImage(handle){return inspectText(handle);}
 report('Inspecting this project’s document intake…');pendingRead(note);
 try{if(draft.snapshot().pending){paint();await check();}else{await describe();if(live()){paint();report('Choose a PDF or UTF-8 document. Adding it starts no conversation or review.');}}}catch(error){report(error.message,true);}
 return dialog;
}
