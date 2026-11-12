// C12 REACHED REPAIR (Root actual holds, 2026-10-15): the template dialog's failed-preview reason, bound to the
// exact terminal BLD job of the exact candidate version, and the truthful post-Apply proof row. Owner answers are
// the real template owner's (tests/helpers/document_template_fixture.mjs: a real build and a real recorded Apply).
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {templateWire as wire} from './helpers/document_template_fixture.mjs';
import {installDOM,findButton} from './helpers/evidence_reader_harness.mjs';
import {renderTemplateCandidate,failedTemplateBuild,readFailedBuildLog} from '../src/laplace/web/static_shared/document-template.mjs';
const project='book',built=wire.built,ref=built.metadata.candidate_ref;
const LOG='This is pdfTeX\n! Undefined control sequence.\nl.12 \\foo\n! Emergency stop.\n'+'x'.repeat(400);
const failed=(extra={})=>({...structuredClone(built.started),state:'error',ok:false,running:false,log_tail:LOG,diagnostics:[{code:'UNBOUND_EXTERNAL_INPUT',path:'/usr/x.sty'}],...extra});

test('a failed terminal job of this candidate is kept with its exact job read and a bounded glance; anything else is not',()=>{
  const record=failedTemplateBuild(failed(),ref,project);
  assert.equal(record.build_job.id,built.started.build_job.id);
  assert.match(record.read,/^\/authoring\/build\?project=book&build_job=/,'the owner-issued exact job read, not the target status');
  assert.deepEqual(record.glance,['UNBOUND_EXTERNAL_INPUT · /usr/x.sty','! Undefined control sequence.','! Emergency stop.']);
  assert.ok(record.glance.every(line=>line.length<=240));
  assert.equal(failedTemplateBuild(failed({state:'cancelled',ok:false}),ref,project),null,'a stopped build is not a failure');
  assert.equal(failedTemplateBuild({...structuredClone(built.started),state:'done',ok:true,running:false},ref,project),null);
  assert.equal(failedTemplateBuild(failed(),{...ref,version:'other-version'},project),null,'another candidate version');
  assert.deepEqual(failedTemplateBuild(failed({diagnostics:[],log_tail:'no bang lines'}),ref,project).glance,['The compiler log of this build has the details.']);
});

test('the compiler log is read from exactly that job; a newer job\'s answer is refused',async()=>{
  const record=failedTemplateBuild(failed(),ref,project),asked=[];
  const log=await readFailedBuildLog(async(url,_body,options)=>{asked.push([url,options]);return {...failed(),historical:true};},record);
  assert.equal(log,LOG);assert.deepEqual(asked,[[record.read,{allowStateError:true}]]);
  const newer={...failed(),build_job:{...built.started.build_job,id:'BLD-'+'f'.repeat(32)}};
  await assert.rejects(readFailedBuildLog(async()=>newer,record),/another build job/);
});

test('the candidate shows why its preview failed, reads the log only on request, and names an earlier PDF as earlier',async()=>{
  const dom=installDOM();try{
    const record=failedTemplateBuild(failed(),ref,project);let reads=0;
    const value=structuredClone(built.latest);   // carries a preview from an earlier successful build
    const host=document.createElement('section');
    renderTemplateCandidate(host,value,{project,failedBuild:record,onReadFailedLog:async()=>{reads++;return LOG;},onPdf:()=>{}});
    assert.match(host.textContent,/Why the preview failed/);assert.match(host.textContent,/! Undefined control sequence\./);
    assert.match(host.textContent,new RegExp(record.build_job.id));assert.equal(reads,0,'no log read until asked');
    await findButton(host,'Read the compiler log of this build').onclick();assert.equal(reads,1);
    const earlier=host.all().find(node=>node.tag==='button'&&node.textContent.startsWith('Open the earlier preview PDF (build '));
    assert.ok(earlier,'an earlier preview is never presented as this build\'s result');assert.equal(findButton(host,'Open exact preview PDF'),undefined);
    const other=document.createElement('section');
    renderTemplateCandidate(other,value,{project,failedBuild:{...record,candidate_ref:{...ref,version:'v-other'}},onReadFailedLog:async()=>LOG,onPdf:()=>{}});
    assert.doesNotMatch(other.textContent,/Why the preview failed/,'a failure of another candidate version is not shown here');
    assert.ok(findButton(other,'Open exact preview PDF'));
  }finally{dom.restore();}
});

test('after a recorded Apply the row says the candidate was applied, without a proof match or another Apply',()=>{
  const dom=installDOM();try{
    const reviewed=built.reviewed.apply_action.payload.preview_ref;
    const host=document.createElement('section');
    renderTemplateCandidate(host,structuredClone(built.applied),{project,onApply:()=>{},reviewedPreview:reviewed});
    const row=host.all().find(node=>node.attrs['data-control']==='template:proof');
    assert.match(row.textContent,/Candidate application recorded · WA-/);
    assert.doesNotMatch(row.textContent,/Not the proof Apply binds|Apply binds this proof/);
    assert.equal(host.all().find(node=>node.attrs['data-control']==='template:apply'),undefined,'no second Apply');
    const unreviewed=document.createElement('section');renderTemplateCandidate(unreviewed,structuredClone(built.applied),{project});
    assert.match(unreviewed.textContent,/Candidate application recorded/,'the recorded application is said without a reviewed proof too');
    // unknown recording and changed basis keep their own words
    const unknown=document.createElement('section');
    renderTemplateCandidate(unknown,{...structuredClone(built.reviewed),application_recording:{status:'UNKNOWN'}},{project,reviewedPreview:reviewed});
    assert.match(unknown.textContent,/Application outcome needs inspection/);
    const changed=document.createElement('section');
    renderTemplateCandidate(changed,{...structuredClone(built.reviewed),currentness:{...built.reviewed.currentness,status:'CHANGED_INPUT'}},{project,reviewedPreview:reviewed});
    assert.match(changed.textContent,/Basis changed since this preview/);
    const ready=document.createElement('section');renderTemplateCandidate(ready,structuredClone(built.reviewed),{project,onApply:()=>{},reviewedPreview:reviewed});
    assert.match(ready.textContent,/Apply binds this proof/,'before Apply the exact proof still says so');
  }finally{dom.restore();}
});
