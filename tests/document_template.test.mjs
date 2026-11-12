import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {templateWire as wire} from './helpers/document_template_fixture.mjs';
import {installDOM,Node,findButton,loadReader} from './helpers/evidence_reader_harness.mjs';
import {qualifiedOwnerHTTP,ownerHumanTarget} from '../src/laplace/web/static_shared/writing-owner-read.mjs';
import {templatePrepareSubmission,templateBuildSubmission,templateApplySubmission,templateOutputURL,readTemplatePart,validateTemplateMetadata,renderTemplateCandidate,openDocumentTemplate} from '../src/laplace/web/static_shared/document-template.mjs';
const project='template-book',clone=value=>structuredClone(value);
function dom(){const state=installDOM(),oldListener=Node.prototype.addEventListener,oldRemove=Node.prototype.removeEventListener;
  // the evidence Node has no listeners; chain close listeners so the door and the shared inspector both observe a close
  Node.prototype.addEventListener=function(name,fn){if(name!=='close')return;const prior=this.onclose;this.onclose=prior?(...args)=>{prior(...args);fn(...args);}:fn;};
  Node.prototype.removeEventListener=function(){};
  return {...state,restore(){Node.prototype.addEventListener=oldListener;Node.prototype.removeEventListener=oldRemove;state.restore();}};}
test('real candidate discovery has exact source, candidate and build reads without a model turn',()=>{
  assert.equal(qualifiedOwnerHTTP({http:wire.discovery.current_source_read},project).source.file,wire.source.file);
  for(const value of [wire.saved,wire.draft,wire.changed])assert.equal(validateTemplateMetadata(value,{project,candidateRef:value.candidate_ref}),value);
  assert.equal(qualifiedOwnerHTTP(wire.saved.read_handle,project).owner.kind,'template-candidate');
  assert.equal(qualifiedOwnerHTTP(wire.discovery.candidates_read,project).owner.kind,'template-candidates');
  assert.equal(qualifiedOwnerHTTP(wire.saved.build_status_read,project).owner.kind,'candidate-build-status');
  assert.equal(templateBuildSubmission(wire.saved.build_action,project,wire.saved.candidate_ref).payload.build_target.kind,'candidate');
  assert.equal(wire.saved.author.kind,'human');assert.ok(!wire.saved.author.turn_id);
  const crossed=clone(wire.saved.read_handle);crossed.payload.candidate_ref=wire.draft.candidate_ref;
  assert.equal(qualifiedOwnerHTTP(crossed,project),null);
  assert.equal(ownerHumanTarget(wire.saved.read_handle.http.url+'&file=private.tex'),null);
});
test('explicit captured draft carries its original source guard once and cannot cross selection',()=>{
  const source={...wire.source,content:'\\documentclass{custom}\nCaptured unsaved body.',revision:'draft-1',input_content_sha256:wire.draft.included_draft.input_content_sha256};
  const action=templatePrepareSubmission(wire.discovery.prepare_action,project,source,{draft:true,reason:'Inspect this exact draft'});
  assert.deepEqual(action.payload.source_edits,[{file:source.file,content:source.content}]);
  assert.deepEqual(action.payload.guards,{expected_selection:source.selection_identity,source_guards:{[source.file]:source.expected_source_digest}});
  assert.deepEqual(action.payload.draft_basis,{file:source.file,revision:'draft-1'});
  assert.ok(!Object.hasOwn(action.payload,'before'));
  assert.throws(()=>templatePrepareSubmission(wire.discovery.prepare_action,project,{...source,selection_identity:'sha256:'+'a'.repeat(64)},{draft:true,reason:'Inspect'}),/original basis/);
  const include={...source,file:source.file.replace(/[^/]+$/,'chapters/chapter.tex')};
  assert.equal(templatePrepareSubmission(wire.discovery.prepare_action,project,include,{draft:true,reason:'Inspect include'}).payload.source_edits[0].file,include.file);
});
test('actual owner byte parts assemble exact text, not just the last complete-looking chunk',async()=>{
  for(const part of ['original','proposed','diff']){
    const pieces=wire.parts[part],first=clone(wire.saved.source_changes[0].reads[part]);
    // The first handle can request a smaller owner-supported chunk; all following
    // continuations are the real producer's exact issued reads.
    first.payload.limit=40;first.http.url+='&limit=40';let index=0;
    const result=await readTemplatePart(first,{project,candidateRef:wire.saved.candidate_ref,request:async()=>clone(pieces[index++])});
    assert.equal(result.text,pieces.map(row=>row.content).join(''));assert.equal(index,pieces.length);
    assert.equal(pieces.at(-1).coverage.at_end,true);
    if(pieces.length>1)assert.equal(pieces.at(-1).coverage.complete,false);
  }
  const handle=wire.saved.source_changes[0].reads.original,bad=clone(wire.parts.original[0]);bad.coverage.complete=true;
  await assert.rejects(readTemplatePart(handle,{project,candidateRef:wire.saved.candidate_ref,request:async()=>bad}),/coverage/);
});
test('shared candidate reader exposes lazy exact differences, source currentness and separate preview state',async()=>{
  const state=dom();try{const host=document.createElement('section'),reads=[];
    const view=renderTemplateCandidate(host,wire.changed,{project,onReadPart:async handle=>{reads.push(handle);return {text:'Exact retained difference'};}});
    assert.match(host.textContent,/Source basis changed/);assert.match(host.textContent,/manuscript PDF is built from Figures & output/);
    assert.equal(findButton(host,'Apply this reviewed preview'),undefined);
    assert.equal(reads.length,0);await findButton(host,'Review exact changes').click();assert.equal(reads.length,1);assert.match(host.textContent,/Exact retained difference/);view.destroy();
  }finally{state.restore();}
});
test('existing editor draft preview is nonmutating and modal return restores its place',async()=>{
  const state=dom(),calls=[],place={mode:'tex',position:{anchor:7}},captured={...wire.source,content:wire.parts.proposed.map(row=>row.content).join(''),revision:'draft-1',input_content_sha256:wire.draft.included_draft.input_content_sha256};
  let restored=null,captureCount=0;
  try{const view=await openDocumentTemplate({project,documentState:{template:wire.discovery},captureDraft:async()=>{captureCount++;return captured;},capturePlace:()=>place,restorePlace:value=>restored=value,
      request:async(url,payload)=>{calls.push({url,payload});return payload?clone(wire.draft):clone(wire.listing);}});
    assert.equal(calls.length,1);await findButton(view.dialog,'Preview this TeX draft').click();
    const mutation=calls.find(row=>row.payload);assert.equal(mutation.url,'/work/style');assert.equal(mutation.payload.action,'prepare');assert.equal(mutation.payload.source_edits[0].content,captured.content);
    assert.equal(captureCount,1);assert.match(view.dialog.textContent,/Includes captured TeX draft/);assert.equal(state.editor.value,'UNSAVED manuscript');
    assert.ok(calls.every(row=>!row.url.includes('/projection/tex')&&!['apply','recover'].includes(row.payload?.action)));
    await findButton(view.dialog,'Back to manuscript').click();assert.deepEqual(restored,place);
  }finally{state.restore();}
});
test('saved preview rejects a changed original guard before preparing any candidate',async()=>{
  const state=dom(),calls=[];try{
    const view=await openDocumentTemplate({project,documentState:{template:wire.discovery},request:async(url,payload)=>{
      calls.push({url,payload});return url.includes('/projection/tex')?{...clone(wire.source),expected_source_digest:'sha256:'+'b'.repeat(64)}:clone(wire.listing);}});
    await findButton(view.dialog,'Preview saved source').click();assert.ok(!calls.some(row=>row.payload));assert.match(view.dialog.textContent,/Saved source changed/);view.destroy();
  }finally{state.restore();}
});
test('real catalogue pages stay bounded and older candidates are reached through the issued continuation',async()=>{
  const state=dom(),calls=[];try{
    assert.equal(wire.catalogue_pages.length,2);assert.equal(wire.catalogue_pages[0].coverage.bodies_loaded,0);
    const view=await openDocumentTemplate({project,documentState:{template:wire.discovery},request:async url=>{
      calls.push(url);const offset=Number(new URL(url,'http://local/').searchParams.get('offset')||0);
      return clone(wire.catalogue_pages.find(page=>page.coverage.offset===offset));}});
    assert.equal(calls.length,1);await findButton(view.dialog,'Read older template candidates').click();
    assert.equal(calls.length,2);assert.equal(new URL(calls[1],'http://local/').searchParams.get('offset'),'20');
    assert.equal(findButton(view.dialog,'Read older template candidates'),undefined);view.destroy();
  }finally{state.restore();}
});
test('real built output and Apply bind the exact candidate, BLD receipt and PDF witness',()=>{
  const {reviewed,finished}=wire.built,proof=finished.preview_ref,ref=reviewed.candidate_ref;
  assert.equal(templateApplySubmission(reviewed.apply_action,'book',ref,proof).payload.preview_ref.build_receipt_id,proof.build_receipt_id);
  assert.match(templateOutputURL(reviewed.preview_pdf_read,'book',ref,proof),/^\/work\/style\/pdf\?/);
  assert.match(templateOutputURL(reviewed.preview_image_read,'book',ref,proof,{image:true}),/format=png/);
  assert.equal(qualifiedOwnerHTTP(reviewed.preview_pdf_read,'book').owner.kind,'template-preview');
  assert.notEqual(proof.build_job.id,wire.built.latest.build.preview_ref.build_job.id);
  assert.deepEqual(reviewed.apply_action.payload.preview_ref,proof);
  const crossed=clone(proof);crossed.build_receipt_id='ART-'+'a'.repeat(32);
  assert.throws(()=>templateApplySubmission(reviewed.apply_action,'book',ref,crossed),/exact candidate/);
  assert.throws(()=>templateOutputURL(reviewed.preview_pdf_read,'book',ref,crossed),/exact template PDF/);
});
test('candidate build Stop uses the exact admitted job and closing the inspector does not cancel it',async()=>{
  const built=JSON.parse(readFileSync(new URL('fixtures/editor_spine/document-template-build.json',import.meta.url))),state=dom(),calls=[];
  try{
    const project=built.prepared.project,descriptor={...wire.discovery,candidates_read:{operation:'document',payload:{view:'template-candidates'},http:{method:'GET',url:'/authoring/document?project='+project+'&view=template-candidates'}}};
    const view=await openDocumentTemplate({project,documentState:{template:descriptor},request:async(url,payload)=>{
      calls.push({url,payload});if(url.includes('template-candidates'))return {schema_version:built.prepared.schema_version,project,candidates:[]};
      if(payload){assert.equal(payload.action,'cancel');assert.deepEqual(payload.build_job,built.active_status.build_job);return clone(built.terminal_status);}
      return url.startsWith('/authoring/build')?clone(built.active_status):clone(built.prepared);
    }});
    await view.load(built.prepared.read_handle);assert.equal(findButton(view.dialog,'Stop build').hidden,false);
    await findButton(view.dialog,'Stop build').click();assert.equal(calls.filter(row=>row.payload?.action==='cancel').length,1);
    view.destroy();assert.equal(calls.filter(row=>row.payload).length,1);
  }finally{state.restore();}
});
test('shared contextual candidate inspector is read-only and keeps exact differences lazy',async()=>{
  const state=dom(),reader=await loadReader(),calls=[];try{
    const dialog=await reader.openArtifact({ownerRead:wire.saved.read_handle,label:'Template candidate',request:async(url,payload)=>{
      calls.push({url,payload});assert.equal(payload,undefined);return clone(wire.saved);}});
    assert.match(dialog.textContent,/Template change/);assert.match(dialog.textContent,/Source basis current/);
    assert.equal(findButton(dialog,'Build template preview'),undefined);assert.equal(findButton(dialog,'Apply this reviewed preview'),undefined);
    assert.equal(calls.length,1);await findButton(dialog,'Close').click();
  }finally{reader.destroy();state.restore();}
});
test('a transport error carrying the real committed receipt remains visible and cannot replay Apply',async()=>{
  const state=dom(),built=wire.built;let rendered,acknowledged=0;
  try{
    const descriptor={...wire.discovery,candidates_read:{operation:'document',payload:{view:'template-candidates'},http:{method:'GET',url:'/authoring/document?project=book&view=template-candidates'}}};
    const view=await openDocumentTemplate({project:'book',documentState:{template:descriptor},request:async(url,payload)=>{
      if(url.includes('template-candidates'))return {schema_version:built.reviewed.schema_version,project:'book',candidates:[]};
      if(payload)throw Object.assign(Error('Connection ended after save'),{body:clone(built.applied)});
      return url.startsWith('/authoring/build')?clone(built.finished):clone(built.reviewed);
    },openPreview:async(_url,_title,options)=>rendered=options.onRendered,onApplied:async()=>{acknowledged++;throw Error('Postimage read unavailable');}});
    await view.load(built.reviewed.read_handle);await findButton(view.dialog,'Open exact preview PDF').click();rendered();await new Promise(resolve=>setImmediate(resolve));
    await findButton(view.dialog,'Apply this reviewed preview').click();assert.equal(acknowledged,1);assert.match(view.dialog.textContent,/Source saved.*Local draft acknowledgement needs inspection/);
    assert.equal(findButton(view.dialog,'Apply this reviewed preview'),undefined);view.destroy();
  }finally{state.restore();}
});
test('real template flow requires successful PDF rendering and requalifies precisely that proof before Apply',async()=>{
  const state=dom(),built=wire.built,calls=[],ref=built.reviewed.candidate_ref;let rendered,acknowledged=0;
  try{
    const discovery={...wire.discovery,candidates_read:{operation:'document',payload:{project:'book',view:'template-candidates'},http:{method:'GET',url:'/authoring/document?project=book&view=template-candidates'}}};
    const view=await openDocumentTemplate({project:'book',documentState:{template:discovery},request:async(url,payload)=>{
      calls.push({url,payload});const q=new URL(url,'http://local/').searchParams;
      if(q.get('view')==='template-candidates')return {schema_version:built.reviewed.schema_version,project:'book',candidates:[]};
      if(payload){assert.equal(payload.action,'apply');assert.deepEqual(payload.preview_ref,built.finished.preview_ref);return clone(built.applied);}
      if(url.startsWith('/authoring/build'))return clone(built.finished);
      if(q.has('preview_ref'))assert.deepEqual(JSON.parse(q.get('preview_ref')),built.finished.preview_ref);
      return clone(built.reviewed);
    },openPreview:async(_url,_title,options)=>{rendered=options.onRendered;},onApplied:async()=>{acknowledged++;return {reason:'Exact draft acknowledged.'};}});
    await view.load(built.reviewed.read_handle);
    assert.equal(findButton(view.dialog,'Apply this reviewed preview').disabled,true);
    await findButton(view.dialog,'Open exact preview PDF').click();
    assert.equal(findButton(view.dialog,'Apply this reviewed preview').disabled,true);
    rendered();await new Promise(resolve=>setImmediate(resolve));
    assert.deepEqual(view.reviewedPreview,built.finished.preview_ref);assert.equal(findButton(view.dialog,'Apply this reviewed preview').disabled,false);
    await findButton(view.dialog,'Apply this reviewed preview').click();assert.equal(acknowledged,1);
    assert.equal(calls.filter(row=>row.payload?.action==='apply').length,1);assert.match(view.dialog.textContent,/Source saved/);
    assert.equal(findButton(view.dialog,'Apply this reviewed preview'),undefined);view.destroy();
  }finally{state.restore();}
});

// M5 C7: the reviewed-proof row names the exact build receipt and PDF that Apply binds
test('the reviewed-proof row names the build receipt and PDF that Apply binds, and only that proof enables Apply',async()=>{
  const state=dom();try{
    const value=wire.changed;const proof=value.apply_action?.payload?.preview_ref||value.preview_pdf_read?.payload?.preview_ref;
    const host=document.createElement('section');
    renderTemplateCandidate(host,value,{project,onApply:()=>{},reviewedPreview:proof||null});
    const row=host.all().find(node=>node.attrs['data-control']==='template:proof');
    if(proof){assert.ok(row,'a reviewed proof renders its row');assert.match(row.textContent,/Reviewed proof: build /);assert.match(row.textContent,/PDF /);
      const apply=host.all().find(node=>node.attrs['data-control']==='template:apply');assert.ok(apply);}
    else{assert.equal(row,undefined,'no proof, no row');}
    const unreviewed=document.createElement('section');renderTemplateCandidate(unreviewed,value,{project,onApply:()=>{}});
    assert.equal(unreviewed.all().find(node=>node.attrs['data-control']==='template:proof'),undefined);
    assert.match(unreviewed.textContent,/Preview only; the manuscript PDF is built from Figures & output/);
  }finally{state.restore();}
});
