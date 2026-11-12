// THE TEMPLATE WORKFLOW through the shared inspector, with the ACTUAL openDocumentTemplate,
// the ACTUAL openPdf (PDF-library double) and the owner-produced candidate fixture:
// form → exact preview PDF (replaces the setup) → rendering acknowledgement while the PDF is
// current → Back → explicit, guarded Apply; changed basis refuses; genuine close ends it.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {templateWire as wire} from './helpers/document_template_fixture.mjs';
import {installDOM,Node,findButton} from './helpers/evidence_reader_harness.mjs';
import {installPdfGlobals,loadRealPdf} from './helpers/real_pdf_environment.mjs';
import {openDocumentTemplate} from '../src/laplace/web/static_shared/document-template.mjs';
import {sharedInspector,resetSharedInspector} from '../src/laplace/web/static_shared/workspace-inspector.mjs';
const clone=value=>structuredClone(value);
const {openPdf}=await loadRealPdf();
function page(){
  const state=installDOM(),oldListener=Node.prototype.addEventListener;
  // the evidence Node has no listeners; chain close listeners so a door and the inspector both see a close
  Node.prototype.addEventListener=function(name,fn){if(name!=='close')return;const prior=this.onclose;this.onclose=prior?(...args)=>{prior(...args);fn(...args);}:fn;};
  Node.prototype.removeEventListener=function(){};
  resetSharedInspector();
  const env=installPdfGlobals(state);
  return {...state,env,restore(){env.restore();Node.prototype.addEventListener=oldListener;delete Node.prototype.removeEventListener;state.restore();resetSharedInspector();}};
}
const discovery={...wire.discovery,candidates_read:{operation:'document',payload:{project:'book',view:'template-candidates'},http:{method:'GET',url:'/authoring/document?project=book&view=template-candidates'}}};
function owner(built,{applied=[],changedAfterPreview=false}={}){
  const calls=[];
  const request=async(url,payload)=>{calls.push({url,payload});const q=new URL(url,'http://local/').searchParams;
    if(q.get('view')==='template-candidates')return {schema_version:built.reviewed.schema_version,project:'book',candidates:[]};
    if(payload){assert.equal(payload.action,'apply');assert.deepEqual(payload.preview_ref,built.finished.preview_ref);applied.push(payload);return clone(built.applied);}
    if(url.startsWith('/authoring/build'))return clone(built.finished);
    if(changedAfterPreview&&q.has('preview_ref')){const changed={...clone(built.reviewed),currentness:clone(wire.changed.currentness),semantic_currentness:'NOT_ASSERTED'};delete changed.apply_action;return changed;}   // the same candidate, its source basis changed under it: the owner offers no apply action
    if(q.has('preview_ref'))assert.deepEqual(JSON.parse(q.get('preview_ref')),built.finished.preview_ref);
    return clone(built.reviewed);};
  return {calls,request};
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));

test('form → REAL preview PDF replaces the setup → rendering acknowledged while the PDF is current → Back restores the setup with the reviewed proof → explicit Apply sends exactly that proof',async()=>{
  const d=page(),built=wire.built,applied=[],{calls,request}=owner(built,{applied});
  try{
    const inspector=sharedInspector();let acknowledged=0;
    const view=await openDocumentTemplate({project:'book',documentState:{template:discovery},request,openPreview:openPdf,onApplied:async()=>{acknowledged++;return {reason:'Exact draft acknowledged.'};},capturePlace:()=>({mode:'tex',position:{anchor:7}})});
    await view.load(built.reviewed.read_handle);
    const setup=view.dialog;
    assert.deepEqual({open:setup.open,connected:setup.isConnected,applyDisabled:findButton(setup,'Apply this reviewed preview').disabled},{open:true,connected:true,applyDisabled:true},'before preview');
    assert.equal(inspector.current.kind,'template-setup');assert.deepEqual(inspector.current.pin.selected,built.reviewed.candidate_ref);
    const reason=setup.all().find(n=>n.attrs['aria-label']==='Reason for template preview');reason.value='Check the title page';reason.oninput();
    await findButton(setup,'Open exact preview PDF').click();await tick();await tick();
    const pdf=d.dialogs().at(-1);
    assert.notEqual(pdf,setup);assert.equal(setup.open,false,'the setup was REPLACED by the exact preview, not closed as a form');assert.equal(setup.dataset.inspectorReplaced,'true');
    assert.equal(inspector.current.kind,'pdf');assert.deepEqual(inspector.trail.map(e=>[e.kind,e.title,e.retainsDialog]),[['template-setup','Template & layout',false]]);
    assert.equal(view.reviewedPreview,null,'nothing is reviewed until the PDF has rendered');
    await d.env.renderLatest();   // the real render path: first page visible → onRendered
    assert.deepEqual(view.workflow.reviewed,built.finished.preview_ref,'the acknowledgement reached the workflow state while the PDF is current');assert.equal(inspector.current.kind,'pdf','the PDF stays current; nothing reopened by itself');
    assert.equal(pdf.children[0].textContent,'Back to Template & layout');
    await pdf.children[0].onclick();await tick();await tick();await tick();
    const reopened=d.dialogs().at(-1);
    assert.notEqual(reopened,setup);assert.equal(pdf.open,false);assert.equal(inspector.current.kind,'template-setup');assert.deepEqual(inspector.trail,[]);
    const apply=findButton(reopened,'Apply this reviewed preview');assert.ok(apply,'Apply is offered again');assert.equal(apply.disabled,false,'Apply is enabled only because the owner re-read the candidate under the reviewed proof');
    assert.equal(reopened.all().find(n=>n.attrs['aria-label']==='Reason for template preview').value,'Check the title page','the typed reason survived the transition');
    assert.match(reopened.textContent,/Exact preview reviewed/);
    const readsUnderProof=calls.filter(c=>!c.payload&&new URL(c.url,'http://local/').searchParams.has('preview_ref'));assert.ok(readsUnderProof.length>=1,'the reopen re-read the candidate under the exact proof');
    await apply.click();await tick();
    assert.equal(applied.length,1,'one explicit Apply');assert.deepEqual(applied[0].preview_ref,built.finished.preview_ref);assert.equal(acknowledged,1);
    reopened.close();assert.equal(inspector.current,null);
  }finally{d.restore();}
});

test('a changed candidate basis after the preview shows the owner\'s changed state without Apply; a genuine close ends the workflow so a late acknowledgement is ignored',async()=>{
  const d=page(),built=wire.built;
  try{
    const inspector=sharedInspector();
    const {request}=owner(built,{changedAfterPreview:true});
    const view=await openDocumentTemplate({project:'book',documentState:{template:discovery},request,openPreview:openPdf});
    await view.load(built.reviewed.read_handle);
    await findButton(view.dialog,'Open exact preview PDF').click();await tick();await tick();
    await d.env.renderLatest();assert.deepEqual(view.workflow.reviewed,built.finished.preview_ref);
    const pdf=d.dialogs().at(-1);await pdf.children[0].onclick();await tick();await tick();await tick();
    const reopened=d.dialogs().at(-1);
    assert.equal(findButton(reopened,'Apply this reviewed preview'),undefined,'the owner\'s changed basis carries no apply action: nothing to weaken');assert.match(reopened.textContent,/Source basis changed/);
    // GENUINE close of the setup at the trail root ends the workflow
    reopened.close();assert.equal(inspector.current,null);assert.equal(view.workflow.closed,true);
    const stale=view.workflow.reviewed;view.workflow.reviewed=null;
    // a late rendering acknowledgement after the genuine close changes nothing
    const {previewAcknowledgementForTest}=await import('../src/laplace/web/static_shared/document-template.mjs');
    if(previewAcknowledgementForTest)previewAcknowledgementForTest(view.workflow,built.reviewed.candidate_ref,stale,{token:'gone'})();
    assert.equal(view.workflow.reviewed,null);
  }finally{d.restore();}
});

test('a stub preview that does not replace the setup still refreshes it on acknowledgement (the editor\'s existing flow), and genuine close restores the place',async()=>{
  const d=page(),built=wire.built;let rendered,restored=null;
  try{
    const {request}=owner(built);
    const view=await openDocumentTemplate({project:'book',documentState:{template:discovery},request,openPreview:async(_url,_title,options)=>{rendered=options.onRendered;},capturePlace:()=>({mode:'tex',position:{anchor:3}}),restorePlace:value=>{restored=value;}});
    await view.load(built.reviewed.read_handle);
    await findButton(view.dialog,'Open exact preview PDF').click();rendered();await tick();await tick();
    assert.equal(findButton(view.dialog,'Apply this reviewed preview').disabled,false);
    view.dialog.close();assert.deepEqual(restored,{mode:'tex',position:{anchor:3}});assert.equal(view.workflow.closed,true);
  }finally{d.restore();}
});
