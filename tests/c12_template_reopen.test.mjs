// C12 RESIDUAL R3 (Sol, 2026-10-15): an existing failed preview build is reconciled on EVERY candidate read path, not
// only when the dialog follows a build to its end. The ACTUAL openDocumentTemplate with the real template owner's
// fixture (tests/helpers/document_template_fixture.mjs); the owner's build-status answers are the real started job in
// a terminal shape. Saved-candidate load, Refresh, reopen with the pinned workflow, cancelled, another version, and a
// stale read are each checked. No build is started and nothing is retried.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {templateWire as wire} from './helpers/document_template_fixture.mjs';
import {installDOM,Node,findButton} from './helpers/evidence_reader_harness.mjs';
import {openDocumentTemplate} from '../src/laplace/web/static_shared/document-template.mjs';
import {resetSharedInspector} from '../src/laplace/web/static_shared/workspace-inspector.mjs';
const clone=value=>structuredClone(value),built=wire.built;
const discovery={...wire.discovery,candidates_read:{operation:'document',payload:{project:'book',view:'template-candidates'},http:{method:'GET',url:'/authoring/document?project=book&view=template-candidates'}}};
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function page(){
  const state=installDOM(),oldListener=Node.prototype.addEventListener;
  Node.prototype.addEventListener=function(name,fn){if(name!=='close')return;const prior=this.onclose;this.onclose=prior?(...args)=>{prior(...args);fn(...args);}:fn;};
  Node.prototype.removeEventListener=function(){};resetSharedInspector();
  return {...state,restore(){Node.prototype.addEventListener=oldListener;delete Node.prototype.removeEventListener;state.restore();resetSharedInspector();}};
}
const LOG='! Existing failed preview reason\nl.3 \\broken';
const terminal=(fields)=>({...clone(built.started),running:false,cleanup_unproved:false,...fields});
const failed=()=>terminal({state:'error',ok:false,log_tail:LOG,diagnostics:[]});
function owner(){
  const o={mode:'failed',calls:[],gate:null,status:null};
  o.request=async(url)=>{o.calls.push(url);const q=new URL(url,'http://local/').searchParams;
    if(q.get('view')==='template-candidates')return {schema_version:built.latest.schema_version,project:'book',candidates:[]};
    if(url.startsWith('/authoring/build')&&q.has('build_job'))return {...failed(),historical:true};   // the exact job read
    if(url.startsWith('/authoring/build')){if(o.gate)await o.gate;
      return o.status?clone(o.status):o.mode==='failed'?failed():o.mode==='done'?terminal({state:'done',ok:true,log_tail:''}):terminal({state:'cancelled',ok:false,log_tail:''});}
    return clone(built.latest);};   // carries a preview from an EARLIER successful job
  return o;
}
const dialogText=()=>document.body.all().filter(node=>String(node.className).includes('document-template-dialog')).map(node=>node.textContent).join(' ');
const earlierButton=()=>document.body.all().find(node=>node.tag==='button'&&node.textContent.startsWith('Open the earlier preview PDF (build '));

test('an existing failure shows on load, its log is read from that job only, a success clears it and a reopen shows it again',async()=>{
  const d=page(),o=owner();
  try{
    assert.notEqual(built.latest.preview_pdf_read.payload.preview_ref.build_job.id,built.started.build_job.id,'the failed job and the earlier PDF job differ');
    const view=await openDocumentTemplate({project:'book',documentState:{template:discovery},request:o.request});
    await view.load(built.latest.read_handle);await tick();
    assert.equal(view.workflow.failedBuild?.build_job.id,built.started.build_job.id,'the saved-candidate load reconciles the observed failure');
    assert.match(dialogText(),/Why the preview failed/);assert.match(dialogText(),/! Existing failed preview reason/);
    assert.ok(earlierButton(),'the earlier PDF is named as earlier');assert.equal(findButton(document.body,'Open exact preview PDF'),undefined);
    const reads=o.calls.length;await findButton(document.body,'Read the compiler log of this build').onclick();
    const logRead=o.calls.slice(reads).find(url=>url.includes('build_job='));assert.ok(logRead,'the log is that exact job\'s read');
    assert.match(dialogText(),/l\.3 \\broken/);
    // selecting another candidate version drops this candidate's failure from the workflow (it is not that candidate's)
    const version=built.latest.candidate_ref.version,otherVersion='sha256:'+'7'.repeat(64);
    const otherHandle=JSON.parse(JSON.stringify(built.latest.read_handle).replaceAll(version,otherVersion).replaceAll(encodeURIComponent(version),encodeURIComponent(otherVersion)));
    const answer=o.request;o.request=async(url,...rest)=>url.includes(encodeURIComponent(otherVersion))&&!url.startsWith('/authoring/build')
      ?{...clone(built.latest),candidate_ref:{...built.latest.candidate_ref,version:otherVersion}}:answer(url,...rest);
    const switched=await openDocumentTemplate({project:'book',documentState:{template:discovery},request:o.request,workflow:view.workflow});
    await switched.load(otherHandle).catch(()=>{});await tick();
    assert.deepEqual(switched.workflow.selected,{...built.latest.candidate_ref,version:otherVersion});
    assert.equal(switched.workflow.failedBuild,null,'another candidate version never carries this one\'s failure');
    switched.destroy();o.request=answer;
    const back=await openDocumentTemplate({project:'book',documentState:{template:discovery},request:o.request,workflow:switched.workflow});   // the shared inspector replaced the first dialog
    await back.load(built.latest.read_handle);await tick();
    assert.equal(back.workflow.failedBuild?.build_job.id,built.started.build_job.id,'back on the failed candidate its failure is read again');
    const view2=back;
    // a later CANCELLED job of this candidate makes no claim: the recorded failure stays as it was
    o.mode='cancelled';await view2.load(built.latest.read_handle);await tick();
    assert.equal(view2.workflow.failedBuild?.build_job.id,built.started.build_job.id,'cancelled neither clears nor replaces the failure');
    // Refresh: a terminal success of this candidate clears the failure and the PDF is this candidate's preview again
    o.mode='done';await view2.load(built.latest.read_handle);await tick();
    assert.equal(view2.workflow.failedBuild,null);assert.doesNotMatch(dialogText(),/Why the preview failed/);assert.ok(findButton(document.body,'Open exact preview PDF'));
    // the failure returns; reopen with the pinned workflow shows it again after its own read
    o.mode='failed';await view2.load(built.latest.read_handle);await tick();
    const workflow=view2.workflow;view2.destroy();
    const again=await openDocumentTemplate({project:'book',documentState:{template:discovery},request:o.request,workflow});
    await again.load(built.latest.read_handle);await tick();
    assert.equal(again.workflow.failedBuild?.build_job.id,built.started.build_job.id);assert.match(dialogText(),/Why the preview failed/);
    again.destroy();
    assert.ok(o.calls.every(url=>!url.includes('action=')),'nothing was started or retried');
  }finally{d.restore();}
});

test('cancelled is not a failure, another version is refused, and a stale read cannot replace the current state',async()=>{
  const d=page(),o=owner();
  try{
    o.mode='cancelled';
    const view=await openDocumentTemplate({project:'book',documentState:{template:discovery},request:o.request});
    await view.load(built.latest.read_handle);await tick();
    assert.equal(view.workflow.failedBuild,null);assert.doesNotMatch(dialogText(),/Why the preview failed/);
    // another candidate version: the exact build-target guard refuses it and records nothing
    const other=failed();other.build_job=clone(other.build_job);other.build_job.build_target={...other.build_job.build_target,candidate_ref:{...other.build_job.build_target.candidate_ref,version:'sha256:'+'9'.repeat(64)}};
    other.build_target=other.build_job.build_target;o.status=other;
    await view.load(built.latest.read_handle);await tick();
    assert.equal(view.workflow.failedBuild,null,'another version is never recorded');assert.match(dialogText(),/another candidate|exact build target/i);
    // a stale read: the first (failed) answer arrives after a newer read was asked; it is ignored
    o.status=null;let release;o.gate=new Promise(resolve=>release=resolve);o.mode='failed';
    const stale=view.load(built.latest.read_handle);await tick();
    o.gate=null;o.mode='done';await view.load(built.latest.read_handle);release();await stale;await tick();
    assert.equal(view.workflow.failedBuild,null,'the stale failed answer does not replace the newer state');
    view.destroy();
  }finally{d.restore();}
});
