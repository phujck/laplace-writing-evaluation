import assert from 'node:assert/strict';
import {test} from 'node:test';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {preparedWorkSubmission,preparedRunSubmission,preparedWorkReceipt} from '../src/laplace/web/static_shared/prepared-work.mjs';

// Derive the consumer fixture from the actual owner, using one auto-cleaned tiny
// root. Frontend tests cannot pass by agreeing with an invented parallel schema.
const result=spawnSync('./scripts/laplace-python',['-c',String.raw`
import json,sys,tempfile
from pathlib import Path
sys.path.insert(0,'tests')
from test_manuscript_structure import _section_fixture
from laplace.manuscript import project_structure; from laplace.native import tools as writing_tools; from laplace.work import project_work
from laplace.writing import prepared_work
with tempfile.TemporaryDirectory(prefix='laplace-prepared-consumer-') as raw:
 root=Path(raw);_section_fixture(root)
 # G18: the list row carries one detail handle; the prepare action lives on the section's detail
 listed=project_structure.read('book',{'view':'summary'},root)['sections']['items'][0]
 assert 'prepare_action' not in listed
 action=project_structure.read('book',listed['detail_read']['payload'],root)['sections'][0]['prepare_action']
 detail_action=project_structure.read('book',{'view':'detail','section_ids':action['payload']['section_ids']},root)['sections'][0]['prepare_action']
 original=project_work.task
 def fail(*args,**kwargs):raise ValueError('Controlled Work publication refusal')
 project_work.task=fail
 try:
  prepared_work.prepare('book',action['payload'],root)
 except prepared_work.PreparationFailure as error:
  failure={'error':str(error),**error.details}
 finally:project_work.task=original
 receipt=writing_tools.execute(root,'book','work',action['operation'],action['payload'])
 print(json.dumps({'action':action,'detail_action':detail_action,'receipt':receipt,'failure':failure}))
`],{cwd:fileURLToPath(new URL('..',import.meta.url)),encoding:'utf8',timeout:30000});
assert.equal(result.status,0,result.stderr);
const {action,detail_action,receipt,failure}=JSON.parse(result.stdout);

test('actual preparation owner fields roundtrip and start no provider',()=>{
 assert.deepEqual(preparedWorkSubmission(action,'book',action.payload.section_ids),{project:'book',...action.payload});
 assert.deepEqual(preparedWorkSubmission(detail_action,'book',action.payload.section_ids),{project:'book',...action.payload});
 assert.equal(preparedWorkReceipt(receipt,'book'),receipt);
 assert.deepEqual(preparedRunSubmission(receipt.run_action,'book',receipt.task),receipt.run_action.payload);
 assert.equal(receipt.provider_started,false);
});

test('crossed scope, guards, route and injected Run fields refuse before submission',()=>{
 assert.throws(()=>preparedWorkSubmission(action,'other',action.payload.section_ids),/Inspect/);
 assert.throws(()=>preparedWorkSubmission(action,'book',['different-section']),/Inspect/);
 for(const altered of [
  {...receipt.run_action,http:{method:'POST',route:'/authoring/steer'}},
  {...receipt.run_action,requires_role:'child'},
  {...receipt.run_action,payload:{...receipt.run_action.payload,session_id:'injected-child'}},
  {...receipt.run_action,payload:{...receipt.run_action.payload,provider:'injected'}},
  {...receipt.run_action,payload:{...receipt.run_action.payload,expected_dependency_revision:'sha256:'+'0'.repeat(64)}}
 ])assert.throws(()=>preparedRunSubmission(altered,'book',receipt.task),/does not match/);
 assert.throws(()=>preparedWorkReceipt({...receipt,provider_started:true},'book'),/matching durable Work/);
});

test('prepared receipt actions inspect exact inputs and compose without starting a provider',async()=>{
 const {installDOM,Node,findButton}=await import('./helpers/evidence_reader_harness.mjs');
 const {renderPreparedWork}=await import('../src/laplace/web/static_shared/prepared-work.mjs');
 const dom=installDOM(),host=new Node('section'),used=[],inputs=[],work=[];dom.body.append(host);
 try{
  renderPreparedWork(host,{project:'book',task:receipt.task,preparation:receipt.preparation,execution:receipt.execution,artifact:receipt.artifact,action:receipt.run_action,onUse:(...args)=>used.push(args),onWork:id=>work.push(id),onArtifact:(...args)=>inputs.push(args)});
  await findButton(host,'Read prepared inputs').onclick();assert.equal(inputs[0][2].artifactId,receipt.artifact.id);assert.equal(inputs[0][2].expectedSha256,receipt.artifact.revision);
  await findButton(host,'Inspect Work').onclick();assert.deepEqual(work,[receipt.work_id]);
  await findButton(host,'Use in next message').onclick();assert.equal(used[0][0],receipt.run_action);assert.equal(used[0][1].id,receipt.work_id);assert.equal(dom.editor.value,'UNSAVED manuscript');
 }finally{dom.restore();}
});

test('prepared composition opens an exact recorded parent or detaches a child, and never sends',async()=>{
 const {WorkspaceSession}=await import('../src/laplace/web/static_shared/workspace-session.mjs');
 const composed=[],pinned=[],opened=[];
 const current=Object.create(WorkspaceSession.prototype);
 Object.assign(current,{project:'book',session:'child',active:'WT-child',role:'author',selectedSessionRecord:{dispatch_id:'dispatch'},newConversation(){this.session='';this.active='';this.role='author';opened.push('new');return true;},openConversation:async function(id){opened.push(id);this.session=id;this.active='';return true;},compose:(...args)=>composed.push(args),pinMessageTarget:(...args)=>pinned.push(args),status(){},send:()=>assert.fail('Preparation unexpectedly sent a provider request')});
 await current.usePreparedWork(receipt.run_action,receipt.task);assert.deepEqual(opened,['new']);assert.deepEqual(composed[0],[receipt.run_action.payload.text,'work']);assert.equal(pinned[0][1].id,receipt.work_id);
 const action={...receipt.run_action,payload:{...receipt.run_action.payload,session_id:'recorded-parent'}};
 const task={...receipt.task,prepared_execution:{items:[{session_id:'recorded-parent'}]}};
 current.session='another-parent';await current.usePreparedWork(action,task);assert.deepEqual(opened,['new','recorded-parent']);assert.equal(current.session,'recorded-parent');
});

test('retained preparation failure exposes owner-pinned reads without claiming possible Work exists',async()=>{
 const {installDOM,Node,findButton}=await import('./helpers/evidence_reader_harness.mjs');
 const {renderPreparationFailure}=await import('../src/laplace/web/static_shared/prepared-work.mjs');
 const dom=installDOM(),host=new Node('section'),inputs=[],work=[];dom.body.append(host);
 try{
  assert.equal(failure.preparation_publication.work_publication,'UNCONFIRMED');
  renderPreparationFailure(host,failure,{project:'book',onArtifact:(...args)=>inputs.push(args),onWork:id=>work.push(id)});
  await findButton(host,'Read retained inputs').onclick();assert.equal(inputs[0][2].artifactId,receipt.artifact.id);assert.equal(inputs[0][2].expectedSha256,receipt.artifact.revision);
  await findButton(host,'Inspect possible Work').onclick();assert.deepEqual(work,[receipt.work_id]);
  assert.equal(findButton(host,'Retry'),undefined);assert.equal(findButton(host,'Run prepared work'),undefined);assert.equal(dom.editor.value,'UNSAVED manuscript');
 }finally{dom.restore();}
});

test('actual workspace preparation completion after navigation offers exact recovery without opening a modal',async()=>{
 const {readFile}=await import('node:fs/promises');
 const {installDOM,Node,findButton}=await import('./helpers/evidence_reader_harness.mjs');
 const dom=installDOM(),root=new Node('main'),noticeHost=new Node('p'),opened=[];dom.body.append(root);root.append(noticeHost);
 // the reader-plan view's preparation doors (workspace-reader-plan-view.mjs, M5 S2 F1), run with its services
 const source=await readFile(new URL('../src/laplace/web/static_shared/workspace-reader-plan-view.mjs',import.meta.url),'utf8'),{SERVICE_PRELUDE}=await import('./helpers/shell_services.mjs');
 const code=source.slice(source.indexOf('  function inspectPreparationFailure('),source.indexOf('  async function renderReaderPlanHome('));
 const moduleURL=new URL('../src/laplace/web/static_shared/prepared-work.mjs',import.meta.url).href;
 try{
  for(const outcome of ['success','retained']){
   let settle;
   const key='__preparedWorkflow'+Math.random().toString(36).slice(2);
   globalThis[key]={root,project:'book',api:()=>new Promise((resolve,reject)=>{settle=()=>outcome==='success'?resolve(receipt):reject(Object.assign(Error(failure.error),{result:failure}));}),notice:text=>{noticeHost.replaceChildren();noticeHost.textContent=text;},$:()=>noticeHost,E:(tag,text='',className='')=>{const n=new Node(tag);n.textContent=text;n.className=className;n.addEventListener=(type,listener)=>{if(type==='close')n.onclose=listener;};return n;},button:(label,run)=>{const n=new Node('button');n.textContent=label;n.onclick=run;return n;},showReaderDialog:dialog=>{dom.body.append(dialog);dialog.showModal();},openWork:id=>opened.push(id),inspectProjectArtifact:()=>{},openSession:()=>{},openConversation:()=>{},readSavedTurn:()=>{},session:{usePreparedWork:()=>assert.fail('unexpected execution')}};
   const reader=await import('data:text/javascript;base64,'+Buffer.from(`import {preparedWorkSubmission,preparedWorkReceipt,renderPreparedWork,renderPreparationFailure} from ${JSON.stringify(moduleURL)};const {root,project,api,notice,$,E,button,showReaderDialog,openWork,inspectProjectArtifact,openSession,openConversation,readSavedTurn,session}=globalThis[${JSON.stringify(key)}];let loadVersion=1;${SERVICE_PRELUDE}${code};export {prepareStoryboardWork};export const navigate=()=>++loadVersion;`).toString('base64'));
   delete globalThis[key];
   const pending=reader.prepareStoryboardWork(action,{id:action.payload.section_ids[0]});reader.navigate();settle();await pending;
   assert.equal(dom.dialogs().length,0,'Completion must not interrupt the newly selected reading');
   if(outcome==='success'){await findButton(noticeHost,'Open prepared Work').onclick();assert.equal(opened.at(-1),receipt.work_id);}
   else {await findButton(noticeHost,'Inspect retained preparation').onclick();assert.equal(dom.dialogs().length,1);assert.ok(findButton(dom.dialogs()[0],'Read retained inputs'));dom.dialogs()[0].close();}
  }
 }finally{dom.restore();}
});
