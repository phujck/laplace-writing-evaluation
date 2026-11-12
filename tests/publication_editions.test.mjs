import assert from 'node:assert/strict';
import {test} from 'node:test';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {validBuildJob,validEditionTarget,sameBuildTarget} from '../src/laplace/web/static_shared/derived-output.mjs';
import {editionPrepareSubmission,editionBuildSubmission,editionPdfURL,mountPublicationEditions} from '../src/laplace/web/static_shared/publication-editions.mjs';
import {installDOM,Node,findButton} from './helpers/evidence_reader_harness.mjs';

// Actual owner views of the public synthetic three-chapter fixture, built by the installed TeX toolchain.
const output=spawnSync('./scripts/laplace-python',['-c',String.raw`
import json,sys,tempfile
from pathlib import Path
import pytest
sys.path.insert(0,'tests')
import test_publication_editions as t
monkey=pytest.MonkeyPatch()
with tempfile.TemporaryDirectory(prefix='laplace-editions-consumer-') as raw:
 make=getattr(t.fixture,'__wrapped__',None) or t.fixture._get_wrapped_function()
 fixture=make(Path(raw),monkey)
 root,master=next(fixture)
 t.define(root)
 initial=t.view(root)
 t.prepare_and_build(root,('alpha','beta'))
 ready=t.view(root)
 (master.parent/'chapters'/'beta.tex').write_text(t.CHAPTERS['beta']+'Changed.\n')
 stale=t.view(root)
 job=t.run(root,'build',{'build_target':stale['editions'][1]['build_target']})
 t.settle(root,stale['editions'][1]['build_target'])
 print(json.dumps({'initial':initial,'ready':ready,'stale':stale,'job':job}))
 fixture.close()
monkey.undo()
`],{cwd:fileURLToPath(new URL('..',import.meta.url)),encoding:'utf8',timeout:120000});
assert.equal(output.status,0,output.stderr);
const wire=JSON.parse(output.stdout);
const by=(view,name)=>view.editions.find(row=>row.name===name);

test('owner-issued prepare, build and saved-PDF actions validate; crossed ones refuse before a request',()=>{
 const alpha=by(wire.initial,'alpha');
 assert.deepEqual(editionPrepareSubmission(alpha,'three'),{url:'/authoring/build',payload:{project:'three',prepare:{edition:'alpha',definition_revision:alpha.definition_revision}}});
 const crossed=structuredClone(alpha);crossed.prepare_action.payload.prepare.edition='beta';assert.throws(()=>editionPrepareSubmission(crossed,'three'),/displayed edition/);
 const ready=by(wire.ready,'alpha');assert.ok(validEditionTarget(ready.build_target,'three'));
 assert.deepEqual(editionBuildSubmission(ready,'three').payload.build_target,ready.build_target);
 const wrong=structuredClone(ready);wrong.build_action.payload.build_target=by(wire.ready,'beta').build_target;assert.throws(()=>editionBuildSubmission(wrong,'three'),/displayed edition target/);
 assert.ok(editionPdfURL(ready,'three').startsWith('/projection/pdf?'));
 const rebound=structuredClone(ready);rebound.pdf_read.content_revision='sha256:'+'0'.repeat(64);assert.throws(()=>editionPdfURL(rebound,'three'),/No other PDF/);
 assert.throws(()=>editionPdfURL(ready,'other'),/No other PDF/);
});

test('an edition build job is one exact build-job identity for the shared cancellation control',()=>{
 assert.ok(validBuildJob(wire.job.build_job,'three'));assert.equal(wire.job.build_job.target_kind,'publication-edition');
 assert.ok(sameBuildTarget(wire.job.build_job.build_target,by(wire.stale,'beta').build_target));
 const crossed=structuredClone(wire.job.build_job);crossed.build_target.input_revision='sha256:'+'0'.repeat(64);assert.equal(validBuildJob(crossed,'three'),false);
});

test('the editions card lists titles and states, sends the displayed actions and returns to the canonical source',async()=>{
 const dom=installDOM(),host=new Node('section'),calls=[],pdf=[],source=[];dom.body.append(host);
 let next=wire.stale;
 try{
  const control=await mountPublicationEditions(host,{project:'three',request:async(url,payload)=>{calls.push({url,payload});return payload?{}:next;},
   onReadPdf:(...args)=>pdf.push(args),onOpenSource:read=>source.push(read)});
  assert.match(host.textContent,/Alpha Edition/);assert.match(host.textContent,/Beta Edition/);assert.match(host.textContent,/Gamma Edition/);
  assert.match(host.textContent,/Canonical source: synthetics papers\/three\/manuscript\/Three-Chapter-Fixture\.tex/);
  const chips=host.all().filter(n=>n.className.includes('state-chip')).map(n=>n.textContent);assert.deepEqual(chips,['ready','stale','unprepared']);
  const alphaCard=host.all().find(n=>n.dataset?.edition==='alpha');
  await findButton(alphaCard,'Read PDF').onclick();assert.equal(pdf[0][0],editionPdfURL(by(wire.stale,'alpha'),'three'));
  const save=alphaCard.all().find(n=>n.tag==='a');assert.equal(save.download,'edition-alpha.pdf');
  const gammaCard=host.all().find(n=>n.dataset?.edition==='gamma');
  await findButton(gammaCard,'Prepare edition').onclick();assert.deepEqual(calls.findLast(call=>call.payload).payload,editionPrepareSubmission(by(wire.stale,'gamma'),'three').payload);
  const betaCard=host.all().find(n=>n.dataset?.edition==='beta');
  await findButton(betaCard,'Build edition PDF').onclick();assert.deepEqual(calls.findLast(call=>call.payload).payload.build_target,by(wire.stale,'beta').build_target);
  await findButton(host,'Open canonical source').onclick();assert.deepEqual(source[0],wire.stale.canonical_source.read);
  control.destroy();
 }finally{dom.restore();}
});

test('no declared editions keep the card hidden; another project refuses',async()=>{
 const dom=installDOM(),host=new Node('section');dom.body.append(host);
 try{
  const empty={...wire.initial,editions:[],status:'NOT_DEFINED'};
  const control=await mountPublicationEditions(host,{project:'three',request:async()=>empty});
  assert.equal(host.all().find(n=>n.className.includes('publication-editions')).hidden,true);control.destroy();
  const other=await mountPublicationEditions(host,{project:'other',request:async()=>wire.ready});
  assert.equal(other.data,null);other.destroy();
 }finally{dom.restore();}
});

test('an unsaved canonical draft sends no prepare or build; after saving the exact displayed target builds',async()=>{
 const dom=installDOM(),host=new Node('section'),posts=[],notices=[];dom.body.append(host);
 let dirty=true,next=wire.stale;
 try{
  const control=await mountPublicationEditions(host,{project:'three',status:(...args)=>notices.push(args),
   hasDocumentDraft:document=>document?.project==='three'&&dirty,
   admitDocumentBuild:()=>{if(dirty)throw Error('Save the current manuscript edits before building the PDF.');},
   request:async(url,payload)=>{if(payload){posts.push(payload);return {};}return url.includes('target_kind=publication-edition')?next:{project:'three'};}});
  const card=name=>host.all().find(n=>n.dataset?.edition===name);
  assert.equal(findButton(card('beta'),'Build edition PDF').disabled,true);assert.equal(findButton(card('gamma'),'Prepare edition').disabled,true);
  assert.match(host.textContent,/Unsaved manuscript edits are not included/);
  await findButton(card('beta'),'Build edition PDF').onclick();await findButton(card('gamma'),'Prepare edition').onclick();
  assert.equal(posts.length,0);assert.match(notices.at(-1)[0],/Save the current manuscript edits/);
  dirty=false;await control.refresh();
  // A target that changed after display is not silently swapped in.
  next=wire.ready;await findButton(card('beta'),'Build edition PDF').onclick();assert.equal(posts.length,0);assert.match(host.textContent,/changed since it was displayed/);
  next=wire.stale;await control.refresh();await findButton(card('beta'),'Build edition PDF').onclick();
  assert.deepEqual(posts,[{project:'three',build_target:by(wire.stale,'beta').build_target}]);
  control.destroy();
 }finally{dom.restore();}
});
