// document-template.mjs — THE TEMPLATE INSPECTOR: prepare, preview, review and apply one
// exact template candidate from Document setup (M5 C7).
// Ownership: candidates, builds, previews and applications belong to /authoring/document
//   view=template* and /work/style; this module validates every handle it is handed and never
//   mints a candidate, preview or application identity.
// Public contract: openDocumentTemplate({project,documentState,request,captureDraft,...});
//   renderTemplateCandidate(host,value,{project,onReadPart,onBuild,onPdf,onApply,...,
//   reviewedPreview}); templateApplySubmission / templateBuildSubmission /
//   templateRecoverySubmission / templatePrepareSubmission (exact owner payloads);
//   templateOutputURL; readTemplatePart; validateTemplateMetadata; templateWorkflowState.
// Presentation: object header (basis, preview, reviewed, recording chips); per-file Diff /
//   Original / Proposed beside the file; closure and provenance lazy; the reviewed-proof row
//   names the build receipt and PDF that Apply binds; Apply is enabled only for that proof.
// Currentness: a changed candidate or source shows the owner's changed-basis state without
//   Apply; the preview is polled only while a job is active (derived-output cancellation).
// Errors/recovery: an uncertain application offers Finish template application record
//   (recovery_action) and Inspect application record; nothing is replayed.
// Storage: none (the captured TeX draft rides inside the candidate as immutable text).
// Retired (C7): the "Preview output is separate…" disclaimer (now one sentence pointing to
//   Figures & output).
import {validBuildJob,sameBuildJob,buildJobStatusURL,buildJobActive,validCandidateTarget,sameBuildTarget,mountBuildCancellation,validTemplateCandidateRef,validTemplatePreviewRef} from './derived-output.mjs';
import {qualifiedOwnerHTTP} from './writing-owner-read.mjs';
import {pendingRead} from './pending-read.mjs';
import {validateSourceRead} from './manuscript-source-client.mjs';
import {sourceEffectDisposition} from './source-effect.mjs';
import {openPdf} from './writing-pdf.mjs';
import {sharedInspector} from './workspace-inspector.mjs';
import {objectHeader,templateChips,stateChip,chipRow,lazySection,clippedText,presentationStyles} from './workspace-presentation.mjs';

export const TEMPLATE_SCHEMA='laplace.document-template-candidate/1';
const pin=value=>typeof value==='string'&&/^sha256:[0-9a-f]{64}$/.test(value);
const relative=value=>typeof value==='string'&&!!value&&!value.startsWith('/')&&!value.includes('\\')&&!value.split('/').includes('..')&&!/[\u0000-\u001f]/.test(value);
const canonical=value=>Array.isArray(value)?value.map(canonical):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonical(value[key])])):value;
const same=(left,right)=>JSON.stringify(canonical(left))===JSON.stringify(canonical(right));
const copy=value=>structuredClone(value);
export {validTemplateCandidateRef,validTemplatePreviewRef} from './derived-output.mjs';
function styleAction(action,project,kind,fields){
  const http=action?.http,base=globalThis.location?.href||'http://local/',url=new URL(http?.url||http?.route||'',base),payload=action?.payload;
  if(action?.operation!=='style'||action.permitted!==true||http?.method!=='POST'||url.origin!==new URL(base).origin||url.pathname!=='/work/style'||url.search||url.hash||url.username||url.password||
      action.project&&action.project!==project||payload?.project&&payload.project!==project||payload?.action!==kind||Object.keys(payload).some(key=>!['project','action',...fields].includes(key)))
    throw Error(action?.reason||'Inspect the exact template action before continuing.');
  return {url:url.pathname,payload:{...copy(payload),project}};
}
export function templateApplySubmission(action,project,candidateRef,previewRef){
  const request=styleAction(action,project,'apply',['candidate_ref','preview_ref']);
  if(!validTemplatePreviewRef(previewRef,project,candidateRef)||!same(request.payload.candidate_ref,candidateRef)||!same(request.payload.preview_ref,previewRef))
    throw Error('Apply does not match the exact candidate and PDF preview you reviewed. Inspect that preview again.');
  return request;
}
export function templateRecoverySubmission(action,project,candidateRef){
  const request=styleAction(action,project,'recover',['candidate_ref','application_id','application_intent_id']);
  const hasApplication=Object.hasOwn(request.payload,'application_id'),hasIntent=Object.hasOwn(request.payload,'application_intent_id');
  if(!validTemplateCandidateRef(candidateRef)||!same(request.payload.candidate_ref,candidateRef)||hasApplication===hasIntent||
      hasApplication&&!/^WA-[0-9a-f]{32}$/.test(request.payload.application_id)||hasIntent&&!/^DEC-[0-9a-f]{32}$/.test(request.payload.application_intent_id))
    throw Error('Recovery has no exact durable application or admission intent. Inspect the retained source outcome.');
  return request;
}
export function templateBuildSubmission(action,project,candidateRef){
  const http=action?.http,base=globalThis.location?.href||'http://local/',url=new URL(http?.url||http?.route||'',base),target=action?.payload?.build_target;
  if(action?.operation!=='build'||action.permitted===false||action.project!==project||http?.method!=='POST'||url.origin!==new URL(base).origin||url.pathname!=='/authoring/build'||url.search||url.hash||url.username||url.password||
      Object.keys(action.payload||{}).length!==1||!validCandidateTarget(target,project)||!same(target.candidate_ref,candidateRef))
    throw Error('The preview build does not belong to this exact template candidate.');
  return {url:url.pathname,payload:{project,build_target:copy(target)}};
}

export function templatePrepareSubmission(action,project,source,{reason,draft=false}={}){
  const request=styleAction(action,project,'prepare',['guards','reason']);
  if(!relative(source?.file)||typeof source.content!=='string'||source.read_only===true||!pin(source.expected_source_digest)||!pin(source.selection_identity)||
      request.payload.guards?.expected_selection!==source.selection_identity||typeof reason!=='string'||!reason.trim())
    throw Error('Preview needs the exact editable source observation and a reason. Its original basis was retained; no edits were saved.');
  request.payload={...request.payload,reason:reason.trim(),source_edits:[{file:source.file,content:source.content}],
    guards:{expected_selection:source.selection_identity,source_guards:{[source.file]:source.expected_source_digest}}};
  if(draft){if(typeof source.revision!=='string'||!source.revision||!pin(source.input_content_sha256))throw Error('This TeX draft has no captured lease. Capture the existing buffer again; no source was saved.');
    request.payload.draft_basis={file:source.file,revision:source.revision};}
  return request;
}

export function templateOutputURL(handle,project,candidateRef,previewRef,{image=false,page=1}={}){
  const http=handle?.http,base=globalThis.location?.href||'http://local/',url=new URL(http?.url||'',base),query=url.searchParams,payload=handle?.payload;
  let subject,proof;try{subject=JSON.parse(query.get('candidate_ref'));proof=JSON.parse(query.get('preview_ref'));}catch{throw Error('The preview output has no exact candidate/build witness.');}
  const keys=image?['project','candidate_ref','preview_ref','format','page']:['project','candidate_ref','preview_ref'];
  if(handle?.operation!=='document'||http?.method!=='GET'||url.origin!==new URL(base).origin||url.pathname!=='/work/style/pdf'||url.hash||url.username||url.password||
      [...query.keys()].some(key=>!keys.includes(key)||query.getAll(key).length!==1)||keys.some(key=>!query.has(key))||query.get('project')!==project||
      !validTemplatePreviewRef(previewRef,project,candidateRef)||!same(subject,candidateRef)||!same(proof,previewRef)||
      payload?.project&&payload.project!==project||payload?.view!=='template'||payload.part!==(image?'preview-image':'preview-output')||
      !same(payload.candidate_ref,candidateRef)||!same(payload.preview_ref,previewRef)||
      Object.keys(payload).some(key=>!['project','view','candidate_ref','preview_ref','part',...(image?['page']:[])].includes(key))||
      image&&(!Number.isInteger(page)||page<1||query.get('format')!=='png'||Number(query.get('page'))!==page||payload.page!==page))
    throw Error('The output read does not match the exact template PDF you selected. No newer PDF was substituted.');
  return url.pathname+url.search;
}

export async function readTemplatePart(handle,{project,candidateRef,request,onProgress=()=>{}}={}){
  const first=qualifiedOwnerHTTP(handle,project),owner=first?.owner;
  if(owner?.kind!=='template-candidate'||!same(owner.candidateRef,candidateRef)||!['original','proposed','diff','closure','diagnostics'].includes(owner.part))throw Error('Use the exact retained template text read.');
  const part=owner.part,file=owner.read_handle.payload.file??null,chunks=[];let next=handle,offset=0,total=null,revision=null;
  while(next){
    const target=qualifiedOwnerHTTP(next,project),scope=target?.owner;
    if(scope?.kind!=='template-candidate'||!same(scope.candidateRef,candidateRef)||scope.part!==part||(scope.read_handle.payload.file??null)!==file||(scope.read_handle.payload.offset||0)!==offset)throw Error('The template continuation changed its exact candidate or text scope.');
    const value=await request(target.url),coverage=value?.coverage;
    if(value.schema_version!==TEMPLATE_SCHEMA||value.project!==project||!same(value.candidate_ref,candidateRef)||value.part!==part||(value.file??null)!==file||typeof value.content!=='string'||
        coverage?.unit!=='utf8-bytes'||!Number.isSafeInteger(coverage.start)||coverage.start!==offset||!Number.isSafeInteger(coverage.end)||coverage.end<offset||
        !Number.isSafeInteger(coverage.total)||coverage.total<coverage.end||coverage.end===offset&&coverage.end!==coverage.total||
        new TextEncoder().encode(value.content).length!==coverage.end-offset||!pin(coverage.sha256)||
        coverage.complete!==(offset===0&&coverage.end===coverage.total)||coverage.at_end!==(coverage.end===coverage.total)||coverage.has_more!==(coverage.end<coverage.total)||
        total!==null&&(coverage.total!==total||coverage.sha256!==revision))throw Error('The template part has incomplete or crossed byte coverage. Its retained candidate was not changed.');
    total=coverage.total;revision=coverage.sha256;chunks.push(value.content);offset=coverage.end;onProgress({received:offset,total});
    if(coverage.has_more&&!value.next_read||!coverage.has_more&&value.next_read)throw Error('The template part has no matching terminal or continuation read.');
    next=value.next_read||null;
  }
  const text=chunks.join(''),bytes=new TextEncoder().encode(text),digest=new Uint8Array(await globalThis.crypto.subtle.digest('SHA-256',bytes));
  if(bytes.length!==total||'sha256:'+Array.from(digest,byte=>byte.toString(16).padStart(2,'0')).join('')!==revision)throw Error('The assembled template text did not match its retained byte identity.');
  return {text,content_revision:revision,bytes:total,part,file};
}

const element=(tag,text='',className='')=>{const node=document.createElement(tag);node.textContent=text;node.className=className;return node;};
export function validateTemplateMetadata(value,{project,candidateRef}={}){
  if(value?.schema_version!==TEMPLATE_SCHEMA||value.project!==project||value.candidate_kind!=='document-template'||!validTemplateCandidateRef(value.candidate_ref)||candidateRef&&!same(value.candidate_ref,candidateRef)||
      !['CURRENT','CHANGED_INPUT','READ_ONLY','UNAVAILABLE'].includes(value.currentness?.status)||!Array.isArray(value.source_changes)||
      value.source_changes.some(row=>!relative(row.file)||!pin(row.before_sha256)||!pin(row.after_sha256)||typeof row.changed!=='boolean'||!row.reads?.diff))throw Error('The template owner did not return this exact candidate and source basis.');
  return value;
}
export function renderTemplateCandidate(host,value,{project,onReadPart,onBuild,onPdf,onApply,onRecover,onRead,isCurrent=()=>true,reviewedPreview=null,failedBuild=null,onReadFailedLog=null}={}){
  validateTemplateMetadata(value,{project});const ref=value.candidate_ref,panel=element('section','','template-candidate'),status=element('p');status.setAttribute('role','status');host.append(panel);
  let alive=true;const fresh=()=>alive&&panel.isConnected!==false&&isCurrent();
  const button=(label,run)=>{const node=element('button',label);node.type='button';node.onclick=async()=>{if(!fresh()||node.disabled)return;node.disabled=true;try{await run();}catch(error){if(fresh())status.textContent=error.message;}finally{if(fresh())node.disabled=false;}};return node;};
  // Glance: the candidate's reason, its state chips (source basis, preview, review,
  // recording). Card: the changed files with their exact reads beside them. Exact:
  // provenance and the declared input closure behind deliberate reads.
  const chips=templateChips(value,reviewedPreview);
  if(value.included_draft)chips.push({label:'Includes captured TeX draft · '+value.included_draft.file.split('/').at(-1),tone:'neutral',title:'The captured buffer is immutable in this candidate; newer typing stays local.'});
  const header=objectHeader({eyebrow:'Template change',title:value.reason||'Exact proposed source change',chips,level:'h3',
    summary:[value.currentness.reason||'',value.currentness.changed_inputs?.length?'Changed inputs: '+value.currentness.changed_inputs.join(', '):''].filter(Boolean).join(' ')});
  panel.append(header);
  const changes=element('section','','template-changes');changes.append(element('h4','Source changes'));
  for(const row of value.source_changes){
    const file=element('article','','template-change');
    const head=element('div','','template-change-head');head.append(element('code',row.file),stateChip(row.changed?{label:'Changed',tone:'attention'}:{label:'Unchanged',tone:'neutral'}));file.append(head);
    const content=element('section','','template-change-content');
    if(onReadPart){const reads=element('div','','action-row');let shown='';
      for(const [part,label]of [['diff','Review exact changes'],['original','Original source'],['proposed','Proposed source']])if(row.reads[part])reads.append(button(label,async()=>{
        if(shown===part){content.replaceChildren();shown='';return;}
        status.textContent='Reading exact '+part+'…';pendingRead(status);const read=await onReadPart(row.reads[part]);if(!fresh())return;
        content.replaceChildren(element('h5',label),clippedText(read.text||'No source text changes.',{lines:40,cls:'template-source-comparison'}));shown=part;status.textContent='Exact retained '+part+' loaded.';
      }));
      file.append(reads);}
    file.append(content);changes.append(file);
  }
  panel.append(changes);
  const closureState=value.closure?.status==='COMPLETE'?{label:'Declared inputs recorded',tone:'ok'}:{label:'Preview inputs need inspection',tone:'attention'};
  const closure=element('section','','template-closure');closure.append(chipRow([closureState]));
  for(const row of value.closure?.diagnostics||[])closure.append(element('p',row.reason||row.message||[row.code||row.kind,row.argument||row.path].filter(Boolean).join(' · '),'muted'));
  if(value.closure_read&&onReadPart)closure.append(lazySection({label:'Inspect exact input closure',load:()=>onReadPart(value.closure_read),render:(body,read)=>{body.append(clippedText(read.text,{lines:30}));}}));
  panel.append(closure);
  const provenance=element('details','','operator-exact');provenance.append(element('summary','Candidate and authorship'),element('p',value.author?.kind==='agent'?'Agent-authored source revision':value.author?.kind==='human'?'Human-authored source revision':'Authorship not reported'),element('code',ref.id),element('code',ref.version));
  if(value.author?.turn_id)provenance.append(element('code',value.author.turn_id));panel.append(provenance);
  const build=value.build;
  if(build?.error||build?.reason)panel.append(element('p',build.error||build.reason,'error'));
  // WHY THE PREVIEW FAILED (C12, 2026-10-15): the terminal failed BLD job of THIS candidate version, as the build
  // owner observed it: a bounded glance (owner diagnostics, the compiler's own error lines) and, on request, the
  // compiler log read from that exact job's owner-issued read (a newer build is never shown in its place).
  const failure=failedBuild&&same(failedBuild.candidate_ref,value.candidate_ref)?failedBuild:null;
  if(failure){const why=element('section','','template-build-failure');why.append(element('h4','Why the preview failed'),element('p','Preview build '+failure.build_job.id+' ended without a preview. Source and drafts are unchanged.','muted'));
    for(const line of failure.glance)why.append(element('p',line,'error'));
    if(onReadFailedLog)why.append(lazySection({label:'Read the compiler log of this build',hideLabel:'Hide the compiler log',cls:'template-build-log',load:()=>onReadFailedLog(failure),render:(body,text)=>{body.append(clippedText(text||'This build recorded no compiler log.',{lines:60,cls:'template-build-log-text'}));}}));
    panel.append(why);}
  const controls=element('div','','template-actions action-row');
  if(value.build_action&&onBuild){const buildButton=button('Build template preview',()=>onBuild(value));buildButton.disabled=value.build_action.permitted===false;controls.append(buildButton);}
  const outputProof=value.preview_pdf_read?.payload?.preview_ref;
  // after a failed build an earlier preview of this candidate is named as earlier, never as this build's result
  const earlier=failure&&outputProof?.build_job?.id&&outputProof.build_job.id!==failure.build_job.id;
  if(value.preview_pdf_read&&onPdf)controls.append(button(earlier?'Open the earlier preview PDF (build '+outputProof.build_job.id.replace(/^BLD-/,'').slice(0,8)+')':'Open exact preview PDF',()=>onPdf(value,outputProof)));
  // THE REVIEWED-PROOF ROW (M5 C7): names the exact build receipt and PDF that Apply binds, from
  // the preview ref the opened PDF qualified; Apply stays disabled until that proof is the one
  // the owner's apply_action carries.
  // APPLICATION TRUTH (C12, 2026-10-15): before Apply the chip compares the reviewed proof with the one Apply
  // binds. After the owner records the candidate's application, apply_action is gone and the owner publishes only
  // the application id, not the preview it bound, so the row says the candidate was applied and makes no proof
  // match claim. An unpublished or unknown recording and a changed basis keep their own words.
  const recording=value.application_recording?.status;
  if(reviewedPreview||recording==='RECORDED'){const proof=element('p','','template-proof-row');proof.setAttribute('data-control','template:proof');
    const same_=same(value.apply_action?.payload?.preview_ref,reviewedPreview);
    const verdict=recording==='RECORDED'?{label:'Candidate application recorded · '+String(value.application_recording.application_id||value.application_id||'').slice(0,16),tone:'ok',title:'The owner recorded this candidate\'s application. It does not say which reviewed preview that application bound.'}
      :recording==='UNPUBLISHED'||recording==='UNKNOWN'?{label:'Application outcome needs inspection',tone:'attention',title:value.recording_gap||'Inspect the current source before another Apply.'}
      :value.currentness?.status!=='CURRENT'?{label:'Basis changed since this preview',tone:'attention',title:value.apply_action?.reason||'Consumed source or template inputs changed.'}
      :same_?{label:'Apply binds this proof',tone:'ok'}:{label:'Not the proof Apply binds',tone:'attention',title:'A different preview is selected. Inspect the reviewed proof before applying.'};
    if(!reviewedPreview){proof.append(element('strong','Application: '),stateChip(verdict));panel.append(proof);}else{
    proof.append(element('strong','Reviewed proof: '),element('span','build '+String(reviewedPreview.build_receipt_id||'').replace(/^ART-/,'').slice(0,12)+' · PDF '+String(reviewedPreview.output?.file||'').split('/').at(-1)+' · '+String(reviewedPreview.output?.content_revision||'').replace(/^sha256:/,'').slice(0,12)),
      stateChip(verdict));
    panel.append(proof);}}
  if(value.apply_action&&onApply){const apply=button('Apply this reviewed preview',()=>onApply(value,reviewedPreview));apply.disabled=value.apply_action.permitted!==true||!reviewedPreview||!same(value.apply_action.payload.preview_ref,reviewedPreview);apply.setAttribute('data-control','template:apply');controls.append(apply);
    if(value.apply_action.permitted!==true&&value.apply_action.reason)controls.append(element('span',value.apply_action.reason,'muted'));
    if(!reviewedPreview)controls.append(element('span','Open the exact preview before applying.','muted'));else if(!same(value.apply_action.payload.preview_ref,reviewedPreview))controls.append(element('span','A different preview is selected. Inspect the reviewed proof before applying.','muted'));}
  const application=value.application_recording;
  if(application?.reason||value.recording_gap)panel.append(element('p',application?.reason||value.recording_gap,'error'));
  if(value.recovery_action&&onRecover)controls.append(button('Finish template application record',()=>onRecover(value)));
  if(value.application_read&&onRead)controls.append(button('Inspect application record',()=>onRead(value.application_read,'Template application')));
  panel.append(controls,status,element('p','Preview only; the manuscript PDF is built from Figures & output.','muted'));
  return {destroy(){alive=false;},get panel(){return panel;}};
}

// THE TEMPLATE WORKFLOW (form → exact preview PDF → rendering acknowledgement → Back → explicit
// Apply) is ONE shared-inspector workflow. The setup panel is adopted by the one inspector (kind
// template-setup); opening the exact preview REPLACES it with the PDF viewer and pushes it onto
// the trail with its WORKFLOW STATE as the entry's pin: a small plain object {selected,
// reviewed, handle, reason, uncertain, place, closed} that is independent of the disposed
// dialog. The rendering acknowledgement is a module-level closure over that state (never the
// render scope): while the PDF is current it records the exact proof; Back (or Close on the
// PDF) reopens the setup through `reopenDocumentTemplate(args, state)`, which re-reads the
// selected candidate under the reviewed proof so the owner's apply_action is the guard — the
// proof is never weakened and Apply stays explicit. A changed candidate/source shows the owner's
// changed-basis state without Apply; a genuine Close of the setup marks the state closed so a
// late acknowledgement is ignored. The existing source editor remains the only mutable
// manuscript; this panel holds immutable candidate/proof selections and sends only
// owner-issued actions.
const liveSetups=new Map();   // token → WeakRef(refresh): a setup still open refreshes when its preview is acknowledged
const previewAcknowledgement=(state,ref,proof,lifetime)=>()=>{if(state.closed||!same(state.selected,ref))return;state.reviewed=copy(proof);state.acknowledgedAt=new Date().toISOString();liveSetups.get(lifetime.token)?.deref()?.();};
const reopenDocumentTemplate=(args,pin)=>openDocumentTemplate({...args,workflow:pin||args.workflow||null});
export const previewAcknowledgementForTest=previewAcknowledgement;
export function templateWorkflowState(){return {selected:null,reviewed:null,handle:null,reason:'Inspect template and layout',uncertain:false,place:null,closed:false,acknowledgedAt:null,failedBuild:null};}
// THE FAILED BUILD (C12, 2026-10-15): a terminal failed BLD job of one exact candidate version, kept with that
// candidate and its owner-issued exact job read, and a bounded glance: up to five owner diagnostics and up to three
// of the compiler's own error lines ("! ..."), each at most 240 characters. Anything else is not a failure record.
// The compiler log of exactly that terminal job, from its owner-issued read; another job's answer is refused.
export async function readFailedBuildLog(request,failure){
  const page=await request(failure.read,undefined,{allowStateError:true});
  if(!sameBuildJob(page?.build_job,failure.build_job))throw Error('The compiler log belongs to another build job. Nothing else is shown.');
  return String(page.log_tail||'');
}
export function failedTemplateBuild(observed,candidateRef,project){
  if(!observed||observed.ok!==false&&observed.state!=='error'||observed.state==='cancelled')return null;
  if(!validBuildJob(observed.build_job,project)||observed.build_job.target_kind!=='candidate'||!same(observed.build_job.build_target?.candidate_ref,candidateRef))return null;
  const clip=text=>String(text).slice(0,240);
  const diagnostics=(Array.isArray(observed.diagnostics)?observed.diagnostics:[]).slice(0,5).map(row=>clip([row.code||row.kind,row.path||row.argument||row.reason].filter(Boolean).join(' · ')));
  const errors=String(observed.log_tail||'').split('\n').filter(line=>line.startsWith('!')).slice(0,3).map(clip);
  return {candidate_ref:copy(candidateRef),build_job:copy(observed.build_job),read:buildJobStatusURL(observed,project),
    glance:[...diagnostics,...errors].length?[...diagnostics,...errors]:['The compiler log of this build has the details.']};
}
export async function openDocumentTemplate({project,documentState,request,captureDraft,capturePlace,restorePlace,
  onApplied=async()=>{},onCanonicalBuild,onCanonicalPdf,onEditSource,onRead,onOpenArtifact,
  isCurrent=()=>true,openPreview=openPdf,opener=document.activeElement,workflow=null}={}){
  const descriptor=documentState?.template;
  if(!descriptor?.available||!descriptor.prepare_action||!descriptor.candidates_read)throw Error(descriptor?.reason||'Template inspection is unavailable for this selected source.');
  const state=workflow&&typeof workflow==='object'?workflow:templateWorkflowState();state.closed=false;
  const inspector=sharedInspector(),lifetime={token:null};
  // the reopen descriptor: the editor's stable services and the owner descriptor; no DOM, no opener
  const descriptorArgs={project,documentState,request,captureDraft,capturePlace,restorePlace,onApplied,onCanonicalBuild,onCanonicalPdf,onEditSource,onRead,onOpenArtifact,isCurrent,openPreview};
  const place=state.place||capturePlace?.()||null;state.place=place;
  const dialog=element('dialog','','document-template-dialog'),header=element('header'),body=element('section'),
    notice=element('p','','template-notice'),candidateHost=element('section'),buildHost=element('div','','template-build-controls'),catalogue=element('details'),catalogueBody=element('section');
  notice.setAttribute('role','status');header.append(element('h2','Template & layout'));
  const close=element('button','Back to manuscript');close.type='button';header.append(close);dialog.append(header,body,notice,buildHost,candidateHost,catalogue);
  let alive=true,generation=0,value=null,renderer=null,pending=false,returnPlace=true;
  const fresh=()=>alive&&isCurrent()&&dialog.isConnected;
  const say=(text,error=false)=>{if(fresh()){notice.textContent=text;notice.classList.toggle('error',error);}};
  const button=(label,run)=>{const node=element('button',label);node.type='button';node.onclick=async()=>{
    if(!fresh()||pending)return;pending=true;node.disabled=true;
    try{await run();}catch(error){say(error.message,true);}finally{pending=false;if(fresh())node.disabled=false;}
  };return node;};
  const read=async(handle,expectedKind)=>{const target=qualifiedOwnerHTTP(handle,project);
    if(!target?.owner||expectedKind&&target.owner.kind!==expectedKind)throw Error('Use the exact template owner read for this project.');
    return request(target.url,undefined,{allowStateError:true});};
  const metadataHandle=(handle,proof)=>{
    const target=qualifiedOwnerHTTP(handle,project);
    if(target?.owner?.kind!=='template-candidate'||!same(target.owner.candidateRef,state.selected))throw Error('This read belongs to another template candidate.');
    const payload={...copy(handle.payload),part:'metadata'};
    if(proof)payload.preview_ref=copy(proof);else delete payload.preview_ref;
    const url=new URL(target.url,globalThis.location?.href||'http://local/');url.searchParams.set('part','metadata');
    if(proof)url.searchParams.set('preview_ref',JSON.stringify(proof));else url.searchParams.delete('preview_ref');
    return {...handle,payload,http:{method:'GET',url:url.pathname+url.search}};
  };
  const cancellation=mountBuildCancellation(buildHost,{project,request,
    onStatus:state=>{if(fresh())buildHost.setAttribute('aria-label','Template preview build · '+state.state);},
    onTerminal:async observed=>{if(fresh())reconcileTerminal(observed);
      if(fresh()&&value)await load(value.read_handle,{proof:state.reviewed,checkBuild:false});
      // The build has ended: the notice says so, instead of retaining the starting sentence.
      if(fresh())say(observed?.state==='cancelled'?'Template preview build stopped. Source and drafts are unchanged.':observed?.ok===false||observed?.state==='error'?'Template preview build failed; the reason is shown with the candidate.':'Template preview built. Open the exact preview PDF to review it before applying.',observed?.ok===false||observed?.state==='error');},
    onInspect:async()=>{if(value)await load(value.read_handle,{proof:state.reviewed});},onError:error=>say(error.message,true)});
  async function checkBuild(metadata,ticket){
    if(!metadata.build_status_read)return;
    const target=qualifiedOwnerHTTP(metadata.build_status_read,project);
    if(target?.owner?.kind!=='candidate-build-status'||!same(target.owner.buildTarget?.candidate_ref,metadata.candidate_ref))throw Error('Preview status belongs to another candidate.');
    const status=await request(target.url,undefined,{allowStateError:true});
    if(!fresh()||ticket!==generation)return;
    if(!sameBuildTarget(status.build_target||status.build_job?.build_target,target.owner.buildTarget))throw Error('Preview status changed its exact build target.');
    if(status.build_job)cancellation.observe(status,{replace:true});else cancellation.observe(null,{replace:true});
    if(reconcileTerminal(status))paint();
  }
  // FAILED BUILDS ON EVERY READ PATH (C12 residual R3). A terminal status observed for the selected candidate is
  // reconciled the same way wherever it is read: a followed build ending (onTerminal) and every candidate read
  // (checkBuild: the saved-candidate load, Refresh/Inspect latest, an inspector Back or reopen, which load again).
  // A failed job of THIS candidate version is recorded with its exact job read (failedTemplateBuild); a terminal
  // success of this candidate clears it; a cancelled or still-active job changes nothing (no claim either way);
  // another candidate or version is never recorded. Returns whether the failure state changed. Nothing is retried,
  // no newer job's log stands in for a failed one, and no proof is renewed.
  function reconcileTerminal(observed){
    if(!state.selected||!observed?.build_job||buildJobActive(observed)||observed.build_job.target_kind!=='candidate'||
       !same(observed.build_job.build_target?.candidate_ref,state.selected))return false;
    const failed=failedTemplateBuild(observed,state.selected,project);
    if(failed){if(sameBuildJob(state.failedBuild?.build_job,failed.build_job))return false;state.failedBuild=failed;return true;}
    if(observed.state==='done'&&observed.ok===true&&state.failedBuild){state.failedBuild=null;return true;}
    return false;
  }
  function paint(){
    renderer?.destroy();candidateHost.replaceChildren();if(!value)return;
    const ticket=generation;
    renderer=renderTemplateCandidate(candidateHost,value,{project,reviewedPreview:state.reviewed,isCurrent:()=>fresh()&&ticket===generation,
      failedBuild:state.failedBuild,
      onReadFailedLog:failure=>readFailedBuildLog(request,failure),
      onReadPart:handle=>readTemplatePart(handle,{project,candidateRef:state.selected,request}),
      onRead,
      onBuild:async metadata=>{
        if(state.uncertain)throw Error('The previous send needs exact owner inspection before another build or Apply. Use Refresh selected candidate.');
        const action=templateBuildSubmission(metadata.build_action,project,state.selected);
        say('Starting an isolated template preview. Manuscript source is unchanged.');
        try{const receipt=await request(action.url,action.payload,{allowStateError:true});
          if(!fresh()||ticket!==generation)return;
          if(!validBuildJob(receipt?.build_job,project)||!sameBuildTarget(receipt.build_job.build_target,action.payload.build_target))throw Error('The build acknowledgement has no matching candidate job.');
          await cancellation.follow(receipt);await load(metadata.read_handle,{proof:state.reviewed});
        }catch(error){state.uncertain=true;say(error.message+' Inspect the selected candidate and build status before retrying.',true);}
      },
      onPdf:async(metadata,proof)=>{
        const url=templateOutputURL(metadata.preview_pdf_read,project,state.selected,proof),ref=copy(state.selected);
        state.handle=copy(metadata.read_handle);inspector.pin(lifetime,state);
        await openPreview(url,'Template preview PDF',{notice:'Exact candidate preview. The current manuscript source and PDF are separate.',onOpenArtifact,
          onRendered:previewAcknowledgement(state,ref,proof,lifetime)});
      },
      onApply:async(metadata,proof)=>{
        if(state.uncertain)throw Error('Inspect the previous application outcome before another write.');
        // Re-observe precisely the reviewed proof. The owner may refuse it; a
        // newer successful build must never replace the user's inspected output.
        const exact=validateTemplateMetadata(await read(metadataHandle(metadata.read_handle,proof),'template-candidate'),{project,candidateRef:state.selected});
        if(!fresh()||ticket!==generation)return;
        const action=templateApplySubmission(exact.apply_action,project,state.selected,proof);
        state.uncertain=true;say('Applying the exact reviewed source revision…');
        let result;
        try{result=await request(action.url,action.payload,{allowStateError:true});}
        catch(error){result=error.result?.source_effect?error.result:error.body?.source_effect?error.body:null;
          if(!result){say(error.message+' The send outcome is unknown. Inspect the selected candidate before retrying.',true);return;}}
        await settle(result,exact,ticket);
      },
      onRecover:async metadata=>{
        const action=templateRecoverySubmission(metadata.recovery_action,project,state.selected);state.uncertain=true;
        say('Finishing the retained application record…');
        let result;
        try{result=await request(action.url,action.payload,{allowStateError:true});}
        catch(error){result=error.result?.source_effect?error.result:error.body?.source_effect?error.body:null;
          if(!result){say(error.message+' Inspect the retained application before retrying.',true);return;}}
        await settle(result,metadata,ticket);
      }});
    if(state.uncertain)for(const node of candidateHost.querySelectorAll('button'))if(['Apply this reviewed preview','Build template preview'].includes(node.textContent))node.disabled=true;
  }
  async function settle(result,metadata,ticket){
    validateTemplateMetadata(result,{project,candidateRef:metadata.candidate_ref});
    if(result.metadata_only===true){
      if(result.complete!==true||result.application_recording?.status!=='RECORDED'||!/^WA-[0-9a-f]{32}$/.test(result.application_recording.application_id||''))throw Error('Application recording was not acknowledged. Keep its exact recovery handle for inspection.');
      if(fresh()&&ticket===generation){value=result;state.uncertain=false;paint();say('Application record finished. No new source write. Existing drafts remain retained.');}
      try{const acknowledgement=await onApplied(result,metadata);if(fresh()&&ticket===generation)say('Application record finished. No new source write. '+(acknowledgement?.reason||'Existing drafts remain retained.'));}
      catch(error){say('Application record finished. Local observation needs inspection: '+error.message,true);}
      return;
    }
    const effect=sourceEffectDisposition(result,{project,selectionIdentity:metadata.selected_source.selection_identity});
    if(!effect)throw Error('No exact source outcome was returned. Preserve the draft and inspect the selected candidate.');
    for(const row of effect.effect.files){const expected=metadata.source_changes.find(item=>item.file===row.path);
      if(!expected||row.before_sha256!==expected.before_sha256||['COMMITTED','UNCHANGED'].includes(effect.state)&&row.after_sha256!==expected.after_sha256)
        throw Error('The source acknowledgement differs from the immutable candidate. Preserve the draft and inspect the outcome.');}
    // Physical acknowledgement precedes secondary observation/UI reads, even if
    // metadata follow-through or a later refresh is unavailable.
    // Show the physical receipt even if draft reopening or secondary observation
    // fails. A failed UI refresh must not turn a committed write into a retry.
    if(fresh()&&ticket===generation){value=result;paint();say(effect.message,!effect.complete);}
    let acknowledgement;
    try{acknowledgement=await onApplied(result,metadata);}catch(error){if(fresh())say(effect.message+' Local draft acknowledgement needs inspection: '+error.message,true);return;}
    if(!fresh()||ticket!==generation)return;
    value=result;state.uncertain=!['COMMITTED','UNCHANGED','ROLLED_BACK'].includes(effect.state)||result.application_recording?.status==='UNKNOWN';paint();
    say((result.metadata_only?'Application record observed; no new source write.':effect.message)+' '+(acknowledgement?.reason||'')+
      (effect.state==='COMMITTED'?' Build the current manuscript PDF when you are ready.':''),!effect.complete);
  }
  async function load(handle,{proof=null,checkBuild:check=true}={}){
    const owner=qualifiedOwnerHTTP(handle,project)?.owner;
    if(owner?.kind!=='template-candidate')throw Error('This is not an exact template candidate read.');
    if(!same(state.selected,owner.candidateRef)){state.selected=copy(owner.candidateRef);state.reviewed=null;state.failedBuild=null;cancellation.observe(null,{replace:true});state.uncertain=false;}
    const ticket=++generation,metadata=validateTemplateMetadata(await read(metadataHandle(handle,proof),'template-candidate'),{project,candidateRef:state.selected});
    if(!fresh()||ticket!==generation)return;
    value=metadata;state.uncertain=metadata.application_recording?.status==='UNKNOWN';paint();
    if(check)try{await checkBuild(metadata,ticket);}catch(error){say('Candidate loaded. '+error.message,true);}
  }
  async function prepare(draft){
    let source;
    if(draft)source=await captureDraft();
    else{const target=qualifiedOwnerHTTP({http:descriptor.current_source_read},project);
      if(target?.source?.file!==descriptor.current_source_file)throw Error('The saved source read does not match this document.');
      source=validateSourceRead(await request(target.url));
      if(source.file!==descriptor.current_source_file||source.selection_identity!==descriptor.expected_selection||source.expected_source_digest!==descriptor.expected_source_digest)
        throw Error('Saved source changed. Reopen Template & layout to inspect its current basis. No edits were saved.');}
    const action=templatePrepareSubmission(descriptor.prepare_action,project,source,{draft,reason:reason.value});
    say(draft?'Capturing this TeX draft without saving…':'Preparing a saved-source preview without saving…');
    const prepared=validateTemplateMetadata(await request(action.url,action.payload),{project});
    if(!fresh())return;
    state.selected=copy(prepared.candidate_ref);state.reviewed=null;state.uncertain=false;value=prepared;++generation;cancellation.observe(null,{replace:true});paint();
    say(draft?'The included TeX draft is now an immutable candidate. Newer typing remains local.':'Saved-source candidate retained. Source and current PDF are unchanged.');
    await list();
  }
  async function list(handle=descriptor.candidates_read,append=false){
    const owner=qualifiedOwnerHTTP(handle,project)?.owner,expectedOffset=owner?.read_handle.payload.offset||0;
    const listing=await read(handle,'template-candidates');if(!fresh())return;
    if(listing.schema_version!==TEMPLATE_SCHEMA||listing.project!==project||!Array.isArray(listing.candidates))throw Error('The candidate catalogue returned a different owner scope.');
    if(listing.coverage&&(!Number.isSafeInteger(listing.coverage.total)||listing.coverage.offset!==expectedOffset||listing.coverage.returned!==listing.candidates.length))throw Error('The candidate catalogue returned crossed page coverage.');
    if(!append)catalogueBody.replaceChildren();
    for(const row of listing.candidates){if(!validTemplateCandidateRef(row.candidate_ref)||!same(qualifiedOwnerHTTP(row.read_handle,project)?.owner?.candidateRef,row.candidate_ref))throw Error('A catalogue row has no exact candidate read.');
      catalogueBody.append(button((row.reason||'Saved template candidate')+' · '+row.candidate_ref.id.slice(0,13),()=>load(row.read_handle)));}
    if(!listing.candidates.length)catalogueBody.append(element('p','No saved template candidates.'));
    if(listing.next_read){const next=qualifiedOwnerHTTP(listing.next_read,project)?.owner;
      if(next?.kind!=='template-candidates'||next.read_handle.payload.offset!==expectedOffset+listing.candidates.length)throw Error('The catalogue continuation changed its exact owner or position.');
      const more=button('Read older template candidates',async()=>{await list(listing.next_read,true);more.remove();});catalogueBody.append(more);
    }else if(listing.coverage&&expectedOffset+listing.candidates.length<listing.coverage.total)catalogueBody.append(element('p','Additional saved candidates require an exact owner continuation.','muted'));
  }
  presentationStyles();
  const reason=element('input');reason.value=state.reason||'Inspect template and layout';reason.setAttribute('aria-label','Reason for template preview');reason.oninput=()=>{state.reason=reason.value;};
  body.append(element('p','Preview the selected source, including its custom class and local inputs. Previewing does not save source or change rendering defaults.'),
    element('code',descriptor.current_source_file),reason);
  const prepareRow=element('div','','action-row');prepareRow.append(button('Preview saved source',()=>prepare(false)));
  if(captureDraft){prepareRow.append(button('Preview this TeX draft',()=>prepare(true)));
    // The saved-source preview leaves an unsaved TeX buffer out and keeps it; the draft
    // preview captures it once, without Save (m5-template-frontend-handoff reached repair).
    body.append(prepareRow,element('p','You have an open TeX buffer. Preview saved source leaves it out and keeps it retained on its original basis; Preview this TeX draft captures it without saving.','muted template-draft-note'));}
  else body.append(prepareRow);
  const secondary=element('div','','action-row');
  if(onEditSource)secondary.append(button('Edit template in TeX',async()=>{returnPlace=false;dialog.close();await onEditSource();}));
  secondary.append(button('Refresh selected candidate',async()=>{if(value)await load(value.read_handle,{proof:state.reviewed});else await list();}),
    button('Inspect latest preview',async()=>{if(value){state.reviewed=null;await load(value.read_handle);}}));
  body.append(secondary);
  const canonical=element('div','','action-row template-canonical');canonical.append(element('span','Current manuscript, separate from any preview:','muted'));
  if(onCanonicalBuild){const build=button('Close and build current manuscript PDF',async()=>{returnPlace=false;dialog.close();await onCanonicalBuild();});build.title='Closes this inspector and starts the canonical build in the editor; the template preview is not promoted.';canonical.append(build);}
  if(onCanonicalPdf)canonical.append(button('Open current manuscript PDF',()=>onCanonicalPdf()));
  if(canonical.children.length>1)body.append(canonical);
  catalogue.append(element('summary','Saved template candidates'),catalogueBody);
  const navigation=()=>{returnPlace=false;dialog.close();};
  const release=()=>{if(!alive)return;alive=false;++generation;renderer?.destroy();cancellation.destroy();liveSetups.delete(lifetime.token);globalThis.window?.removeEventListener?.('popstate',navigation);dialog.remove();
    if(inspector.wasReplaced(dialog))return;   // replaced by the exact preview: the trail returns here with this state
    state.closed=true;if(returnPlace&&isCurrent())void Promise.resolve(restorePlace?.(place)).catch(()=>{});if(isCurrent()&&opener?.isConnected)opener.focus({preventScroll:true});};
  close.onclick=()=>dialog.close();dialog.addEventListener('close',release);document.body.append(dialog);
  lifetime.token=inspector.adopt(dialog,{kind:'template-setup',title:'Template & layout',reopen:{factory:reopenDocumentTemplate,args:descriptorArgs}}).token;inspector.pin(lifetime,state);
  liveSetups.set(lifetime.token,new WeakRef(()=>{if(fresh()&&state.handle)void load(state.handle,{proof:state.reviewed}).catch(error=>say(error.message,true));}));
  dialog.showModal();
  globalThis.window?.addEventListener?.('popstate',navigation);
  try{await list();if(state.handle)await load(state.handle,{proof:state.reviewed});say(state.reviewed?'Exact preview reviewed. Apply this reviewed preview sends only that proof.':'Use the existing TeX editor to customise source; choose which version to preview here.');}catch(error){say(error.message,true);}
  return {dialog,destroy(){dialog.close();release();},get candidate(){return value;},get reviewedPreview(){return state.reviewed;},get workflow(){return state;},load};
}
