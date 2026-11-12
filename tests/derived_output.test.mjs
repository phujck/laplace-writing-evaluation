import assert from 'node:assert/strict';
import {test} from 'node:test';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {validDerivedTarget,derivedBuildSubmission,derivedStatusURL,derivedPdfURL,mountDerivedOutput} from '../src/laplace/web/static_shared/derived-output.mjs';
import {ownerHumanTarget,qualifiedOwnerHTTP} from '../src/laplace/web/static_shared/writing-owner-read.mjs';
import {installDOM,Node,findButton,loadReader} from './helpers/evidence_reader_harness.mjs';

// Actual build/record/read owners with the existing controlled compiler fixture.
// This validates target custody, not execution of an installed TeX engine.
const output=spawnSync('./scripts/laplace-python',['-c',String.raw`
import json,sys,tempfile
from pathlib import Path
import pytest
sys.path.insert(0,'tests')
from test_derived_build_target import derived,settle
from laplace.native import tools as writing_tools
from laplace.manuscript import build_targets
monkey=pytest.MonkeyPatch()
with tempfile.TemporaryDirectory(prefix='laplace-derived-consumer-') as raw:
 make=getattr(derived,'__wrapped__',None) or derived._get_wrapped_function()
 fixture=make(Path(raw),monkey)
 root,plan,canonical,outcome=next(fixture)
 before=canonical.read_bytes()
 initial=build_targets.read('book',root)
 writing_tools.execute(root,'book','work','build',{'build_target':initial['build_target']})
 settle(root,initial['build_target'])
 ready=build_targets.read('book',root)
 (root/'derived/part.tex').write_text('Changed derived input.\n')
 stale=build_targets.read('book',root)
 outcome['ok']=False
 writing_tools.execute(root,'book','work','build',{'build_target':stale['build_target']})
 settle(root,stale['build_target'])
 failed=build_targets.read('book',root)
 (root/'derived/main.pdf').write_bytes(b'%PDF overwritten outside its receipt\n')
 overwritten=build_targets.read('book',root)
 assert canonical.read_bytes()==before
 print(json.dumps({'initial':initial,'ready':ready,'stale':stale,'failed':failed,'overwritten':overwritten}))
 fixture.close()
monkey.undo()
`],{cwd:fileURLToPath(new URL('..',import.meta.url)),encoding:'utf8',timeout:30000});
assert.equal(output.status,0,output.stderr);
const wire=JSON.parse(output.stdout);

test('actual owner target and HTTP/native companions match every required basis',()=>{
 assert.ok(validDerivedTarget(wire.initial.build_target,'book'));
 const build=derivedBuildSubmission(wire.initial,'book');assert.deepEqual(build.payload,{project:'book',build_target:wire.initial.build_target});
 const status=ownerHumanTarget(derivedStatusURL(wire.initial,'book'));assert.equal(status.kind,'derived-build-status');assert.deepEqual(status.buildTarget,wire.initial.build_target);
 assert.equal(qualifiedOwnerHTTP(wire.initial.read_handle,'book').owner.kind,'derived-output');
 assert.equal(qualifiedOwnerHTTP(wire.initial.status_read,'book').owner.kind,'derived-build-status');
 const crossed=structuredClone(wire.initial.status_read);crossed.payload.build_target.input_revision='sha256:'+'0'.repeat(64);assert.equal(qualifiedOwnerHTTP(crossed,'book'),null);
});

test('recorded PDF identity survives changed inputs and latest failure but never an overwrite',()=>{
 assert.equal(wire.ready.status,'READY');assert.ok(derivedPdfURL(wire.ready,'book'));
 assert.equal(wire.stale.pdf_read.current,false);assert.notDeepEqual(wire.stale.build_target,wire.stale.pdf_read.build_target);assert.ok(derivedPdfURL(wire.stale,'book'));
 assert.equal(wire.failed.status,'FAILED');assert.ok(derivedPdfURL(wire.failed,'book'));
 assert.equal(wire.overwritten.pdf_read,undefined);assert.equal(derivedPdfURL(wire.overwritten,'book'),null);
 const crossed=structuredClone(wire.failed);crossed.pdf_read.content_revision='sha256:'+'0'.repeat(64);assert.throws(()=>derivedPdfURL(crossed,'book'),/matching target/);
 const file=structuredClone(wire.ready);const url=new URL(file.pdf_read.http.url,'http://local');url.searchParams.set('file','canonical/main.pdf');file.pdf_read.http.url=url.pathname+url.search;assert.throws(()=>derivedPdfURL(file,'book'),/matching target/);
 const falseCurrent=structuredClone(wire.failed);falseCurrent.pdf_read.current=true;assert.throws(()=>derivedPdfURL(falseCurrent,'book'),/matching target/);
});

test('crossed build or status coordinates refuse before a request',()=>{
 const crossed=structuredClone(wire.initial);crossed.build_action.payload.build_target.root='other/main.tex';assert.throws(()=>derivedBuildSubmission(crossed,'book'),/does not match/);
 const route=structuredClone(wire.initial);route.status_read.http.url+='&project=other';assert.throws(()=>derivedStatusURL(route,'book'),/does not belong/);
 assert.equal(ownerHumanTarget('/authoring/document?project=book&target_kind=unknown'),null);
 assert.equal(ownerHumanTarget('/authoring/document?project=book&target_kind=manuscript').kind,'manuscript-document');
 assert.equal(qualifiedOwnerHTTP({operation:'document',payload:{target_kind:'manuscript'},http:{method:'GET',url:'/authoring/document?project=book&target_kind=manuscript'}},'book').owner.kind,'manuscript-document');
 assert.equal(qualifiedOwnerHTTP({operation:'document',payload:{target_kind:'unknown'},http:{method:'GET',url:'/authoring/document?project=book'}},'book'),null);
 assert.equal(ownerHumanTarget('/authoring/build?project=book&build_target={}'),null);
});

test('derived card sends its displayed target, preserves stale refusal and reads only the saved output',async()=>{
 const dom=installDOM(),host=new Node('section'),calls=[],pdf=[];dom.body.append(host);
 let next=wire.failed;
 try{
  const controller=await mountDerivedOutput(host,{project:'book',initial:wire.stale,request:async(url,payload)=>{
   calls.push({url,payload});if(payload)throw Error('Inspected target changed; refresh explicitly.');return next;
  },onReadPdf:(...args)=>pdf.push(args)});
  await findButton(host,'Build derived PDF').onclick();assert.deepEqual(calls[0].payload.build_target,wire.stale.build_target);assert.match(host.textContent,/Inspected target changed/);
  await findButton(host,'Read saved derived PDF').onclick();assert.equal(pdf[0][0],derivedPdfURL(wire.stale,'book'));assert.match(pdf[0][2].notice,/Saved derived output/);
  await findButton(host,'Refresh derived output').onclick();assert.match(host.textContent,/latest derived build failed/);assert.ok(findButton(host,'Read saved derived PDF'));
  next=wire.overwritten;await controller.refresh();assert.equal(findButton(host,'Read saved derived PDF').hidden,true);assert.equal(dom.editor.value,'UNSAVED manuscript');controller.destroy();
 }finally{dom.restore();}
});

test('typed derived owner links reuse the read-only output renderer and exact PDF route in context',async()=>{
 const dom=installDOM(),reader=await loadReader(),calls=[];
 try{
  const dialog=await reader.openArtifact({ownerRead:ownerHumanTarget(wire.failed.read_handle.http.url),label:'Derived output',request:async(url,payload)=>{assert.equal(payload,undefined);calls.push(url);return structuredClone(wire.failed);}});
  assert.match(dialog.textContent,/latest derived build failed/);assert.equal(findButton(dialog,'Build derived PDF'),undefined);
  await findButton(dialog,'Read saved derived PDF').onclick();assert.equal(reader.pdfCalls[0][0],derivedPdfURL(wire.failed,'book'));assert.equal(calls.length,1);assert.equal(dom.editor.value,'UNSAVED manuscript');dialog.close();
 }finally{reader.destroy();dom.restore();}
});

test('typed derived build-status inspection consumes the owner namespace and exact target',async()=>{
 const dom=installDOM(),reader=await loadReader();
 try{
  const read=ownerHumanTarget(wire.ready.status_read.http.url);
  const dialog=await reader.openArtifact({ownerRead:read,label:'Derived build state',request:async(_url,payload,options)=>{assert.equal(payload,undefined);assert.equal(options.allowStateError,true);return structuredClone(wire.ready.current_build);}});
  assert.match(dialog.textContent,/owner reports output current/);assert.ok(!dialog.textContent.includes('Owner reading unavailable'));assert.equal(dom.editor.value,'UNSAVED manuscript');dialog.close();
 }finally{reader.destroy();dom.restore();}
});

test('only owner-declared absence becomes a quiet collapsed output disclosure',async()=>{
 const dom=installDOM(),host=new Node('section');dom.body.append(host);
 let next={schema_version:'laplace.derived-output/1',project:'book',target_kind:'derived',status:'UNAVAILABLE',reason_code:'NOT_CONFIGURED',reason:'No declared derived target.'};
 try{
  const control=await mountDerivedOutput(host,{project:'book',request:async()=>next});
  const absent=host.all().find(node=>node.tag==='details'&&node.textContent.includes('is not configured'));
  assert.ok(absent);assert.ok(!absent.open);assert.equal(findButton(host,'Build derived PDF').parentElement.hidden,true);assert.ok(!absent.textContent.includes('complete issued'));
  next={...next,reason_code:'INVALID_TARGET',reason:'The issued output crossed its namespace.'};await control.refresh();
  assert.equal(findButton(host,'Build derived PDF').parentElement.hidden,false);assert.match(host.textContent,/crossed its namespace/);assert.equal(findButton(host,'Build derived PDF').disabled,true);control.destroy();
 }finally{dom.restore();}
});

// M5 C7: the derived output card opens with an object header whose chip is the owner's status word
test('the derived output card carries an object header with the owner status as its chip',async()=>{
 const d=installDOM();try{
  const host=new Node('section');d.body.append(host);
  const controller=await mountDerivedOutput(host,{project:'book',initial:wire.ready,request:async()=>wire.ready});
  const card=host.all().find(n=>n.attrs['data-control']==='output:derived');assert.ok(card);
  const header=card.all().find(n=>n.className.includes('object-header'));assert.ok(header);assert.match(header.textContent,/Derived output/);
  const chip=header.all().find(n=>n.className.includes('state-chip'));assert.ok(chip);assert.equal(chip.textContent,'ready');assert.equal(chip.attrs['data-tone'],'ok');
  controller.destroy?.();
 }finally{d.restore();}
});
