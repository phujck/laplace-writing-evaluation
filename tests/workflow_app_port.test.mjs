import {messageTarget} from '../src/laplace/web/static_shared/workspace-interaction.mjs';
// Protocol/lifetime fixtures only; actual native/HTTP/browser evidence is separate.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {WorkspaceSession} from '../src/laplace/web/static_shared/workspace-session.mjs';
import {createWorkflowPort,createWorkflowRunPort,composeWorkflowRequest,readWorkflowConversationAction,workflowConversationURL,emptyWorkflow} from '../src/laplace/web/static_shared/workflow-port.mjs';
const handle=request=>({http:{method:'GET',url:'/work/workflow-definitions?'+new URLSearchParams(Object.entries(request).map(([k,v])=>[k,typeof v==='object'?JSON.stringify(v):String(v)]))},request});
const definition=(id='A',version='v1')=>({definition_id:id,version,scope_id:'scope',scope:{kind:'project',namespace:'book'},reference:{identity:{id},version:{definition_revision:version}},definition:{...emptyWorkflow(),title:'Saved '+version},read:handle({definition_id:id,version}),app_runs_read:handle({definition_id:id,version,facet:'app-runs'})});
const run=(d,work='WA',step=null)=>({profile:'laplace.app-dispatch/1',reference:d.reference,definition_read:d.read,work_id:work,work:{id:work,project:'book'},step_detail:step?{step_id:step}:null});
const runRead=(d,work,step=null)=>handle({definition_id:d.definition_id,version:d.version,facet:'app-run',work_id:work,...step?{step_id:step}:{}});
function action(request,project='book'){
  return {project,permitted:true,send_required:true,http:{method:'POST',route:'/authoring/turn'},payload:{project,mode:'work',text:'Exact owner request'},read:handle(request),project_url:'/project?'+new URLSearchParams({workspace:'writing',corpus:project,workflow_action_read:JSON.stringify(request)})};
}
test('run reads keep saved version and late A never replaces selected B',async()=>{
  const a=definition(),b=definition('B');let release;const gate=new Promise(r=>release=r);
  const port=createWorkflowRunPort({request:async url=>{const query=new URL(url,'http://local').searchParams,d=query.get('definition_id')==='A'?a:b;if(!query.get('facet'))return d;if(d===a){await gate;return run(a);}return run(b,'WB');}});
  const first=port.open(a,'run',runRead(a,'WA'),{work_id:'WA'});await port.open(b,'run',runRead(b,'WB'),{work_id:'WB'});release();await first;
  assert.equal(port.snapshot().selection.definition_id,'B');assert.equal(port.snapshot().read.value.work_id,'WB');assert.equal(port.matches(a),false);
});
test('captured run/step restores exact handle and rejects another version or scope',async()=>{
  const d=definition(),transport=async url=>new URL(url,'http://local').searchParams.get('facet')?run(d,'WA','author'):d,port=createWorkflowRunPort({request:transport});await port.open(d,'step',runRead(d,'WA','author'),{work_id:'WA',step_id:'author'});
  const capture=port.capture();assert.equal(JSON.stringify(capture).includes('public messages'),false);
  const restored=createWorkflowRunPort({initial:capture,request:transport});await restored.restore(d);assert.equal(restored.snapshot().selection.step_id,'author');assert.throws(()=>restored.restore(definition('A','v2')),/another saved/);assert.throws(()=>restored.restore({...d,scope_id:'elsewhere'}),/another saved/);
});
test('mismatched run/step replies retain original read and do not publish as selected result',async()=>{
  const d=definition();let current=run(d,'WA','author');const port=createWorkflowRunPort({request:async url=>new URL(url,'http://local').searchParams.get('facet')?current:d});await port.open(d,'step',runRead(d,'WA','author'),{work_id:'WA',step_id:'author'});
  current=run(d,'WA','critic');await assert.rejects(port.refresh(),/another prepared step/);assert.equal(port.snapshot().read.io,'error');assert.equal(port.snapshot().read.value.step_detail.step_id,'author');
});
test('run topology caches the exact consumed body, keeps historical basis and prior snapshot after refresh failure',async()=>{
  const d={...definition(),is_current:false,head_revision:'v2'};let bodies=0,fail=false;
  const port=createWorkflowRunPort({request:async url=>{if(!new URL(url,'http://local').searchParams.get('facet')){bodies++;return d;}if(fail)throw Error('Observation offline');return run(d,'WA','author');}});
  await port.open(d,'step',runRead(d,'WA','author'),{work_id:'WA',step_id:'author'});await port.refresh();
  assert.equal(bodies,1);assert.equal(port.snapshot().read.definition.definition.title,'Saved v1');assert.equal(port.matches(definition('A','v2')),false);
  fail=true;await assert.rejects(port.refresh(),/offline/);assert.equal(port.snapshot().read.value.work_id,'WA');assert.equal(port.snapshot().read.definition.reference.version.definition_revision,'v1');
});
test('late consumed-body response never replaces selected B and foreign body never becomes topology',async()=>{
  const a=definition(),b=definition('B');let release;const gate=new Promise(resolve=>release=resolve);
  const port=createWorkflowRunPort({request:async url=>{const q=new URL(url,'http://local').searchParams,d=q.get('definition_id')==='A'?a:b;if(!q.get('facet')){if(d===a)await gate;return d;}return run(d,d===a?'WA':'WB');}});
  const first=port.open(a,'run',runRead(a,'WA'),{work_id:'WA'});await new Promise(resolve=>setImmediate(resolve));await port.open(b,'run',runRead(b,'WB'),{work_id:'WB'});release();await first;
  assert.equal(port.snapshot().selection.definition_id,'B');assert.equal(port.snapshot().read.definition.definition_id,'B');
  const foreign=createWorkflowRunPort({request:async url=>new URL(url,'http://local').searchParams.get('facet')?run(a):b});await assert.rejects(foreign.open(a,'run',runRead(a,'WA'),{work_id:'WA'}),/consumed definition/);assert.equal(foreign.snapshot().read.value,undefined);
});
test('delayed consumed body is shared once while selected step changes from A to B',async()=>{
  const d=definition();let release,bodies=0;const gate=new Promise(resolve=>release=resolve);
  const port=createWorkflowRunPort({request:async url=>{const q=new URL(url,'http://local').searchParams;if(!q.get('facet')){bodies++;await gate;return d;}return run(d,'WA',q.get('step_id'));}});
  const first=port.open(d,'step',runRead(d,'WA','author'),{work_id:'WA',step_id:'author'});await new Promise(resolve=>setImmediate(resolve));
  const second=port.open(d,'step',runRead(d,'WA','critic'),{work_id:'WA',step_id:'critic'});await new Promise(resolve=>setImmediate(resolve));release();await Promise.all([first,second]);
  assert.equal(bodies,1);assert.equal(port.snapshot().selection.step_id,'critic');assert.equal(port.snapshot().read.value.step_detail.step_id,'critic');
});
test('composition follows issued read, preserves exact payload and never posts',async()=>{
  const d=definition(),fields={request_id:'stable',step_ids:['author','critic'],goal:'Complete goal\nFull text',fan_out_max:2};const request={...d.read.request,facet:'app-compose',...fields};d.actions={app_prepare:{native:{payload:{action:'prepare',profile:'laplace.app-dispatch/1',reference:d.reference}},required_inputs:Object.keys(fields)},use_in_conversation:{available:true,permitted:true,read:handle({...d.read.request,facet:'app-compose'}),required_inputs:Object.keys(fields)}};
  const calls=[],transport=async(url,payload)=>{calls.push({url,payload});return {action:action(request),prepare_payload:{...d.actions.app_prepare.native.payload,...fields}};};
  const result=await composeWorkflowRequest(d,fields,{request:transport});assert.equal(calls[0].payload,undefined);assert.deepEqual(JSON.parse(new URL(calls[0].url,'http://local').searchParams.get('step_ids')),fields.step_ids);
  const route=workflowConversationURL(result,'/project?workspace=writing&app=workflows');assert.ok(route.includes('app_return='));assert.deepEqual((await readWorkflowConversationAction('book',request,transport)).payload,result.payload);assert.equal(calls.length,2);
  await assert.rejects(composeWorkflowRequest(d,{...fields,reference:{}},{request:transport}),/cannot replace/);assert.throws(()=>workflowConversationURL({...result,project_url:'https://foreign.invalid/project'}),/destination/);
});
test('a workflow draft and selected step survive a separate run visit and reload',async()=>{
  const d=definition(),detail={...d,definition:{...emptyWorkflow(),steps:[{id:'author',title:'Author',assignment:{role:'builder',instructions:'Full text',settings:{}}}]},actions:{save:{permitted:true,http:{method:'POST',url:'/save'},payload:{expected_revision:'v1'}}}};
  const main=createWorkflowPort({request:async()=>detail});await main.dispatch({type:'select',id:'A',read:d.read});await main.dispatch({type:'step',id:'author'});await main.dispatch({type:'edit',edit:{type:'assignment',id:'author',fields:{instructions:'Unsaved full instruction\n'+'x'.repeat(30000)}}});
  const captured=main.capture(),restored=createWorkflowPort({initial:captured,request:async()=>detail});await restored.dispatch({type:'select',id:'A',read:captured.selection.read,step:captured.step});assert.equal(restored.snapshot().step,'author');assert.equal(restored.snapshot().draft.basis.payload.expected_revision,'v1');assert.equal(restored.snapshot().draft.definition.steps[0].assignment.instructions,captured.drafts[0].definition.steps[0].assignment.instructions);
});

function composerFixture(){
  const input={value:''},calls=[];return {input,calls,project:'book',session:'WS-parent',role:'author',ready:Promise.resolve(),selectedSessionRecord:{},
    find:()=>input,syncComposerDraft(){},clearMessageTarget(){calls.push('clear');this.messageIntent=null;},compose(text){calls.push('compose');input.value=text;},status(){},
    newConversation(){calls.push('new');this.session='';this.active='';return true;},openConversation:async()=>true};
}
test('workflow composition retains an unrelated or unresolved composer draft and its original target',async()=>{
  const fake=composerFixture();fake.input.value='Original uncertain message';fake.messageIntent={context:{task_id:'original-work'}};const original=structuredClone(fake.messageIntent);
  await assert.rejects(WorkspaceSession.prototype.useWorkflowAction.call(fake,action({facet:'app-compose'})),/already has a message draft/);
  assert.equal(fake.input.value,'Original uncertain message');assert.deepEqual(fake.messageIntent,original);assert.deepEqual(fake.calls,[]);
});
test('deferred Start never types into a different session after delayed original-conversation open',async()=>{
  const fake=composerFixture(),start=action({facet:'app-launch-compose'});start.payload.session_id='WS-parent';fake.session='WS-before';let release;const gate=new Promise(resolve=>release=resolve);
  fake.openConversation=async()=>{fake.session='WS-parent';await gate;return true;};const pending=WorkspaceSession.prototype.useWorkflowAction.call(fake,start);await Promise.resolve();fake.session='WS-other';release();
  await assert.rejects(pending,/original author conversation/);assert.deepEqual(fake.calls,[]);assert.equal(fake.input.value,'');
});

test('owner request text never authorizes replacing any authored composer draft or target',async()=>{
  const owner=action({facet:'app-compose'});
  for(const draft of ['Prefix\n'+owner.payload.text,owner.payload.text+'\nSuffix',owner.payload.text]){
    const fake=composerFixture();fake.input.value=draft;fake.messageIntent={context:{task_id:'retained-work'},attachment:'retained-attachment'};const original=structuredClone(fake.messageIntent);
    await assert.rejects(WorkspaceSession.prototype.useWorkflowAction.call(fake,owner),/already has a message draft/);
    assert.equal(fake.input.value,draft);assert.deepEqual(fake.messageIntent,original);assert.deepEqual(fake.calls,[]);
  }
});

test('failed-review composition preserves exact offer and qualified Work target without Send',async()=>{
  const {composeFailedReviewRequest,workflowConversationAction}=await import('../src/laplace/web/static_shared/workflow-port.mjs');
  const request={definition_id:'A',version:'v1',facet:'app-continue-compose',work_id:'WA',step_id:'critic'},base={id:'WA',packet:'review',guard:{return:{revision:null}},budget:{max_child_launches:1,deadline_at:null,deadline_seconds:null}},target={id:'WA',title:'Retained task',section_ids:[],work_scope_revision:'sha256:'+'1'.repeat(64),dependency_revision:'sha256:'+'2'.repeat(64)};
  const offered={available:true,permitted:true,project:'book',read:handle(request),native:{operation:'dispatch_continue',payload:base}};
  const composed=action({...request,request_id:'stable-review'});Object.assign(composed.payload,{session_id:'WS-parent',work_id:'WA',expected_work_scope_revision:'sha256:'+'1'.repeat(64),expected_dependency_revision:'sha256:'+'2'.repeat(64)});composed.work_target=target;
  const pin='sha256:'+'3'.repeat(64);request.version=pin;composed.read=handle({...request,request_id:'stable-review',expected_action_basis:pin});composed.project_url='/project?'+new URLSearchParams({workspace:'writing',corpus:'book',workflow_action_read:JSON.stringify(composed.read.request)});
  const reference={schema_version:'laplace.reference/1',owner:'pipeline.workflow',kind:'failed-review-continuation',identity:{project:'book',definition_id:'A',work_id:'WA',step_id:'critic',request_id:'stable-review',parent_session_id:'WS-parent'},version:{definition_revision:pin}};
  composed.payload.workspace_context={surface:'project',workflow_action:{reference,expected_basis:pin}};composed.action_context={schema_version:'laplace.workflow-action-context/1',reference,expected_basis:pin,native:{operation:'dispatch_continue',payload:{...base,request_id:'stable-review'}},summary:{step_id:'critic',work_id:'WA',parent_session_id:'WS-parent'}};
  const calls=[],transport=async(url,payload)=>{calls.push({url,payload});return {action:composed,continuation_payload:{...base,request_id:'stable-review'}};};
  const resolved=await composeFailedReviewRequest(offered,'stable-review',{request:transport});assert.equal(calls[0].payload,undefined);
  assert.deepEqual((await readWorkflowConversationAction('book',composed.read.request,transport)).payload,resolved.payload);
  const fake=composerFixture();fake.pinMessageTarget=(reading,work)=>{fake.calls.push('target');fake.work=work;fake.messageIntent={context:messageTarget(reading,work)};};fake.persistComposerDraft=()=>true;fake.scope=()=>{};await WorkspaceSession.prototype.useWorkflowAction.call(fake,resolved);assert.deepEqual(fake.work,target);assert.deepEqual(fake.calls,['clear','compose','target']);
  const fresh={...composed.read.request};delete fresh.expected_action_basis;await assert.rejects(readWorkflowConversationAction('book',fresh,transport),/another workflow request/);await readWorkflowConversationAction('book',fresh,transport,{allowInspectedBasis:true});await assert.rejects(readWorkflowConversationAction('book',{...composed.read.request,expected_action_basis:'sha256:'+'f'.repeat(64)},transport,{allowInspectedBasis:true}),/another workflow request/);
  const malformed=structuredClone(resolved);delete malformed.payload.expected_dependency_revision;assert.throws(()=>workflowConversationAction(malformed,'book'),/matching inspected Work/);
  const occupied=composerFixture();occupied.input.value='Retained message';occupied.messageIntent={context:{task_id:'other'}};await assert.rejects(WorkspaceSession.prototype.useWorkflowAction.call(occupied,resolved),/already has a message draft/);assert.equal(occupied.messageIntent.context.task_id,'other');assert.deepEqual(occupied.calls,[]);
  await assert.rejects(composeFailedReviewRequest(offered,'stable-review',{request:async()=>({action:resolved,continuation_payload:{...base,request_id:'stable-review',budget:{...base.budget,deadline_at:123}}})}),/offer changed/);assert.equal(offered.native.payload.budget.deadline_at,null);
  await assert.rejects(composeFailedReviewRequest(offered,'stable-review',{request:async()=>({action:{permitted:false,reason:'The original deadline expired.'}})}),/deadline expired/);
});
