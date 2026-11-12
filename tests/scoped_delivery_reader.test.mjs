import assert from 'node:assert/strict';
import {test} from 'node:test';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {ownerHumanTarget,qualifiedOwnerHTTP} from '../src/laplace/web/static_shared/writing-owner-read.mjs';
import {installDOM,loadReader,findButton} from './helpers/evidence_reader_harness.mjs';

const generated=spawnSync('./scripts/laplace-python',['-c',String.raw`
import json,os,sys,tempfile
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
sys.path.insert(0,'tests')
from test_manuscript_structure import _section_fixture
from laplace.web import project_work_surface
from laplace.pipeline import authoring
with tempfile.TemporaryDirectory(prefix='laplace-delivery-consumer-') as raw:
 root=Path(raw)
 os.environ['LAPLACE_STATE']=str(root/'state')
 os.environ['LAPLACE_SESSION_WORKSPACES']=str(root/'workspaces')
 manuscript,_,_=_section_fixture(root)
 context=authoring.build_context('book',{'section_ids':['first']},root,include_guidance=False)
 part=next(p for p in context['parts'] if p['key']=='canonical_structure')
 handle=part['read'];url=urlsplit(handle['http']['url'])
 status,_,body=project_work_surface.handle(url.path,parse_qs(url.query),'GET',repo_root=root)
 assert status==200;matching=json.loads(body)
 plan_path=manuscript/'projection_plan.json';plan=json.loads(plan_path.read_text());plan['sections'][0]['title']='Changed current reader purpose';plan_path.write_text(json.dumps(plan))
 status,_,body=project_work_surface.handle(url.path,parse_qs(url.query),'GET',repo_root=root)
 assert status==200;changed=json.loads(body)
 print(json.dumps({'handle':handle,'matching':matching,'changed':changed}))
`],{cwd:fileURLToPath(new URL('..',import.meta.url)),encoding:'utf8',timeout:30000});
assert.equal(generated.status,0,generated.stderr);
const wire=JSON.parse(generated.stdout);

test('actual same-owner delivery handle has exact typed scope/token and crossed native fields refuse',()=>{
 const target=ownerHumanTarget(wire.handle.http.url);assert.equal(target.view,'delivery');assert.equal(target.project,'book');
 assert.deepEqual(target.read_handle.payload,wire.handle.payload);assert.equal(qualifiedOwnerHTTP(wire.handle,'book').owner.view,'delivery');
 const crossed=structuredClone(wire.handle);crossed.payload.part='section_notes';assert.equal(qualifiedOwnerHTTP(crossed,'book'),null);
 for(const url of [wire.handle.http.url+'&part=section_notes',wire.handle.http.url.replace('canonical_structure','all_history'),wire.handle.http.url.replace(/expected_token=[0-9a-f]+/,'expected_token=bad')])assert.equal(ownerHumanTarget(url),null);
});

test('contextual delivery text distinguishes matching from changed current content and refresh keeps original comparison',async()=>{
 const dom=installDOM(),reader=await loadReader(),calls=[];let next=wire.matching;
 try{
  const dialog=await reader.openArtifact({ownerRead:ownerHumanTarget(wire.handle.http.url),label:'Scoped reader context',request:async(url,payload)=>{assert.equal(payload,undefined);calls.push(url);return structuredClone(next);}});
  assert.match(dialog.textContent,/Current scoped content matches the recorded input/);assert.ok(dialog.textContent.includes(wire.matching.text));assert.ok(!dialog.textContent.includes('No structured view'));
  next=wire.changed;await findButton(dialog,'Refresh current comparison').onclick();assert.match(dialog.textContent,/current scoped content changed/);assert.match(dialog.textContent,/not retained historical bytes/);assert.ok(dialog.textContent.includes('Changed current reader purpose'));
  assert.ok(calls.every(url=>url===wire.handle.http.url));assert.equal(dom.editor.value,'UNSAVED manuscript');dialog.close();
 }finally{reader.destroy();dom.restore();}
});

test('mismatched delivered scope is a refusal rather than an unqualified text view',async()=>{
 const dom=installDOM(),reader=await loadReader();
 try{
  const dialog=await reader.openArtifact({ownerRead:ownerHumanTarget(wire.handle.http.url),request:async()=>({...wire.matching,recorded_context_id:'CTX-'+'0'.repeat(32)})});
  assert.match(dialog.textContent,/different recorded scope or comparison/);assert.ok(!dialog.textContent.includes(wire.matching.text));dialog.close();
 }finally{reader.destroy();dom.restore();}
});
