import assert from 'node:assert/strict';
import {test} from 'node:test';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {validBuildJob,sameBuildJob,buildJobStatusURL,buildCancelSubmission,mountBuildCancellation} from '../src/laplace/web/static_shared/derived-output.mjs';
import {ownerHumanTarget,qualifiedOwnerHTTP} from '../src/laplace/web/static_shared/writing-owner-read.mjs';
import {projectRequest} from '../src/laplace/web/static_shared/workspace-session.mjs';
import {installDOM,Node,findButton,loadReader} from './helpers/evidence_reader_harness.mjs';

// Real issuer/status/action shapes; controlled UI timing below supplements the
// backend's real owned-process cancellation tests, not their execution proof.
const generated=spawnSync('./scripts/laplace-python',['-c',String.raw`
import json,os,tempfile
from pathlib import Path
from laplace.manuscript import manuscript_source, projection_viewer as compiler
from laplace.manuscript import build_jobs,build_targets
import sys
sys.path.insert(0,'tests')
from test_derived_build_target import _derived_sources
with tempfile.TemporaryDirectory(prefix='laplace-cancel-consumer-') as raw:
 root=Path(raw);os.environ['LAPLACE_STATE']=str(root/'state');os.environ['LAPLACE_SESSION_WORKSPACES']=str(root/'workspaces')
 _derived_sources(root)
 values={}
 for kind in ('manuscript','derived'):
  target=build_targets.issue('book',root) if kind=='derived' else None
  source=manuscript_source.resolve('book',repo_root=root)
  path=root/(target['root'] if target else source['root'])
  scope=compiler._compile_scope(path,corpus='book',repo_root=root,build_target=target)
  job=build_jobs.issue(scope,root)
  compiler._write_recompile_status(path,{'build_job':job,'state':'cancelled','ok':False,'log_tail':'Owned build stopped.'})
  values[kind]=build_jobs.status(job,'book',root)
 print(json.dumps(values))
`],{cwd:fileURLToPath(new URL('..',import.meta.url)),encoding:'utf8',timeout:30000});
assert.equal(generated.status,0,generated.stderr);
const wire=JSON.parse(generated.stdout);

test('actual job issuer/status/action bind original root, input pins and native/HTTP companions',()=>{
 for(const value of Object.values(wire)){
  assert.ok(validBuildJob(value.build_job,'book'));
  const action=buildCancelSubmission(value,'book');assert.deepEqual(action.payload,{project:'book',action:'cancel',build_job:value.build_job});
  const read=ownerHumanTarget(buildJobStatusURL(value,'book'));assert.deepEqual(read.buildJob,value.build_job);
  assert.deepEqual(qualifiedOwnerHTTP(value.job_status_read,'book').owner.buildJob,value.build_job);
  const crossed=structuredClone(value.job_status_read);crossed.payload.build_job.id='BLD-'+'0'.repeat(32);assert.equal(qualifiedOwnerHTTP(crossed,'book'),null);
  const bad=structuredClone(value);bad.cancel_action.payload.pid=123;assert.throws(()=>buildCancelSubmission(bad,'book'),/does not match/);
  assert.equal(validBuildJob({...value.build_job,pid:123},'book'),false);
 }
 assert.equal(validBuildJob({...wire.manuscript.build_job,build_target:wire.derived.build_job.build_target},'book'),false);
 const wrong=structuredClone(wire.derived.build_job);wrong.input_revision='sha256:'+'0'.repeat(64);assert.equal(validBuildJob(wrong,'book'),false);
});

test('Stop follows its original job through stopping and ignores an automatically observed replacement',async()=>{
 const dom=installDOM(),host=new Node('section'),calls=[],terminal=[];dom.body.append(host);
 const running={...wire.derived,state:'running',running:true,ok:null},stopping={...running,state:'cancelling'};
 let next=stopping;
 const control=mountBuildCancellation(host,{project:'book',request:async(url,payload,options)=>{calls.push({url,payload,options});return structuredClone(next);},onTerminal:value=>terminal.push(value)});
 try{
  control.observe(running);assert.ok(findButton(host,'Stop build'));
  const replacement={...wire.manuscript,state:'running',running:true,ok:null};
  control.observe(replacement);assert.ok(sameBuildJob(control.data.build_job,running.build_job));
  await findButton(host,'Stop build').onclick();assert.deepEqual(calls[0].payload.build_job,running.build_job);
  control.observe(running);assert.equal(control.data.state,'cancelling');
  assert.equal(findButton(host,'Stopping…').disabled,true);assert.match(host.textContent,/waiting for its processes to end/);assert.equal(terminal.length,0);
  next=wire.derived;await control.refresh();assert.equal(calls[1].url,buildJobStatusURL(running,'book'));assert.equal(calls[1].payload,undefined);
  assert.match(host.textContent,/Build stopped/);assert.equal(terminal[0].state,'cancelled');assert.equal(control.active,false);
  control.observe(running);assert.equal(control.data.state,'cancelled');
 }finally{control.destroy();dom.restore();}
});

test('crossed status preserves the old receipt and exposes explicit inspection instead of adopting another job',async()=>{
 const dom=installDOM(),host=new Node('section'),errors=[];dom.body.append(host);
 const running={...wire.manuscript,state:'running',running:true,ok:null};let inspected=0;
 const control=mountBuildCancellation(host,{project:'book',request:async()=>wire.derived,onError:error=>errors.push(error.message),onInspect:()=>{inspected++;control.observe(wire.manuscript,{replace:true});}});
 try{
  control.observe(running);await findButton(host,'Stop build').onclick();assert.match(errors[0],/another job/);
  assert.ok(sameBuildJob(control.data.build_job,running.build_job));assert.equal(findButton(host,'Stop build').disabled,true);
  control.observe(wire.derived);assert.ok(sameBuildJob(control.data.build_job,running.build_job));
  await findButton(host,'Refresh build status').onclick();assert.ok(sameBuildJob(control.data.build_job,running.build_job));assert.match(errors.at(-1),/another job/);
  await findButton(host,'Inspect current output').onclick();assert.equal(inspected,1);assert.equal(control.data.state,'cancelled');
 }finally{control.destroy();dom.restore();}
});

test('a status read started before Stop cannot undo the acknowledged stopping state',async()=>{
 const dom=installDOM(),host=new Node('section');dom.body.append(host);let release,releaseCancel;
 const running={...wire.manuscript,state:'running',running:true,ok:null},stopping={...running,state:'cancelling'};
 const control=mountBuildCancellation(host,{project:'book',request:async(_url,payload)=>new Promise(resolve=>{if(payload)releaseCancel=resolve;else release=resolve;})});
 try{
  control.observe(running);const old=control.refresh(),cancel=findButton(host,'Stop build').onclick();control.observe(running);releaseCancel(stopping);await cancel;
  release(running);await old;assert.equal(control.data.state,'cancelling');assert.equal(findButton(host,'Stopping…').disabled,true);
 }finally{control.destroy();dom.restore();}
});

test('reversed concurrent status responses cannot revive a settled original job',async()=>{
 const dom=installDOM(),host=new Node('section'),reads=[],terminal=[];dom.body.append(host);
 const running={...wire.manuscript,state:'running',running:true,ok:null};
 const control=mountBuildCancellation(host,{project:'book',request:()=>new Promise(resolve=>reads.push(resolve)),onTerminal:value=>terminal.push(value)});
 try{
  control.observe(running);const old=control.refresh(),recent=control.refresh();
  reads[1](wire.manuscript);await recent;reads[0](running);await old;
  assert.equal(control.data.state,'cancelled');assert.equal(control.active,false);assert.equal(terminal.length,1);
 }finally{control.destroy();dom.restore();}
});

test('owner-unavailable cancellation omits Stop and keeps unproved replacement blocked',()=>{
 const dom=installDOM(),host=new Node('section');dom.body.append(host);
 const previousTimer=globalThis.setTimeout,previousClear=globalThis.clearTimeout,scheduled=[];
 globalThis.setTimeout=fn=>{scheduled.push(fn);return fn;};globalThis.clearTimeout=()=>{};
 const control=mountBuildCancellation(host,{project:'book',request:()=>{throw Error('No cancellation action is available');}});
 try{
  const {cancel_action,...receipt}=wire.manuscript;
  const unavailable={...receipt,state:'cancelling',running:false,owned_processes_active:false,replacement_blocked:true,cleanup_unproved:true,
    cancellation:{available:false,reason:'Cleanup ownership is unproved; replacement stays blocked.'}};
  control.observe(unavailable);assert.equal(findButton(host,'Stopping…').hidden,true);assert.match(host.textContent,/ownership is unproved/);assert.ok(control.active);
  assert.equal(scheduled.length,0);
  assert.throws(()=>buildCancelSubmission(unavailable,'book'));
  const {cancel_action:otherCancel,...other}=wire.derived;
  control.observe({...other,state:'running',running:true,cleanup_unproved:false,cancellation:{available:false,reason:'Cancellation is unavailable on this platform.'}},{replace:true});
  assert.equal(scheduled.length,1,'ordinary unsupported-platform builds still have progress inspection');
 }finally{control.destroy();dom.restore();globalThis.setTimeout=previousTimer;globalThis.clearTimeout=previousClear;}
});

test('only exact acknowledged cancellation accepts intentional terminal ok:false over the mutation gateway',async()=>{
 const previous=globalThis.fetch;let value={...wire.manuscript,cancel_outcome:'already_terminal'},ok=true;
 globalThis.fetch=async()=>({ok,status:ok?200:409,headers:{get:()=> 'application/json'},json:async()=>value});
 const payload=buildCancelSubmission(wire.manuscript,'book').payload;
 try{
  assert.equal((await projectRequest('/authoring/build',payload)).cancel_outcome,'already_terminal');
  value={...wire.derived,cancel_outcome:'already_terminal'};await assert.rejects(projectRequest('/authoring/build',payload));
  value={...wire.manuscript};await assert.rejects(projectRequest('/authoring/build',payload,{allowStateError:true}));
  value={...wire.manuscript,cancel_outcome:'already_terminal'};ok=false;await assert.rejects(projectRequest('/authoring/build',payload));
 }finally{globalThis.fetch=previous;}
});

test('addressed cancelled-job context is read-only and retains its exact identity',async()=>{
 const dom=installDOM(),reader=await loadReader();
 try{
  const read=ownerHumanTarget(buildJobStatusURL(wire.derived,'book'));
  const dialog=await reader.openArtifact({ownerRead:read,request:async()=>structuredClone(wire.derived)});
  assert.match(dialog.textContent,/This build was stopped/);assert.ok(dialog.textContent.includes(wire.derived.build_job.id));assert.equal(findButton(dialog,'Stop build'),undefined);dialog.close();
 }finally{reader.destroy();dom.restore();}
});
