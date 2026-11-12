// Port protocol tests use declared transport replies. Composed owner/browser proof is separate.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createWorkflowPort,editWorkflow,emptyWorkflow} from '../src/laplace/web/static_shared/workflow-port.mjs';
const handle=url=>({http:{method:'GET',url}}),action=(revision)=>({permitted:true,http:{method:'POST',url:'/save'},payload:{definition_id:'WDEF-one',expected_revision:revision}});
const listing={scope_id:'scope-one',definitions:[],actions:{create:{permitted:true,http:{method:'POST',url:'/save'},payload:{expected_revision:null}}}};
const detail=(revision='v1',body=emptyWorkflow())=>({scope_id:'scope-one',definition_id:'WDEF-one',version:revision,definition:body,read:handle('/one?version='+revision),current_read_handle:handle('/one'),actions:{save:action(revision),prepare:{permitted:true,http:{method:'POST',url:'/prepare'},payload:{reference:{id:'WDEF-one',version:revision}}}}});
const select=port=>port.dispatch({type:'select',id:'WDEF-one',read:handle('/one')});
test('graph/list operations preserve complete text, cycles are local, data/feedback stay distinct',()=>{
  let body=emptyWorkflow();for(const [id,role]of [['group','group'],['author','builder'],['critic','adversary']])body=editWorkflow(body,{type:'add',id,role});
  body=editWorkflow(body,{type:'nest',id:'author',parent_id:'group'});body=editWorkflow(body,{type:'assignment',id:'author',fields:{instructions:'Full paragraph\n\nSecond paragraph '+ 'x'.repeat(30000)}});
  body=editWorkflow(body,{type:'connect',from:'author',to:'critic',kind:'feedback'});body=editWorkflow(body,{type:'connect',from:'critic',to:'author',kind:'data'});
  assert.equal(body.steps[1].parent_id,'group');assert.ok(body.steps[1].assignment.instructions.length>30000);assert.deepEqual(body.edges.map(row=>row.kind),['feedback','data']);
  assert.throws(()=>editWorkflow(body,{type:'nest',id:'group',parent_id:'author'}),/cycle/);assert.equal(body.steps[0].parent_id,null);
});
test('original guard survives reread; comparison adoption is exact and never automatic',async()=>{
  let current=detail(),calls=[];const request=async(url,payload)=>{calls.push({url,payload});if(payload)throw Object.assign(Error('stale'),{result:{code:'STALE',effect:'none'}});return structuredClone(url==='/work/workflow-definitions'?listing:current);};
  const port=createWorkflowPort({request,initialListing:listing});await select(port);await port.dispatch({type:'edit',edit:{type:'fields',fields:{title:'Draft'}}});current=detail('v2');await port.dispatch({type:'reinspect'});
  assert.equal(port.snapshot().draft.basis.payload.expected_revision,'v1');await port.dispatch({type:'save'});assert.equal(port.snapshot().attempt.status,'refused');assert.equal(calls.at(-1).payload.expected_revision,'v1');
  await port.dispatch({type:'compare'});const compared=port.snapshot().comparison;await assert.rejects(port.dispatch({type:'adopt',basis:action('unseen')}),/exact guard/);await port.dispatch({type:'adopt',basis:compared.basis});assert.equal(port.snapshot().draft.basis.payload.expected_revision,'v2');assert.equal(port.snapshot().draft.definition.title,'Draft');
});
test('uncertain writes remain guarded and captured; nothing resends on recovery or reread',async()=>{
  let posts=0;const request=async(_url,payload)=>{if(payload){posts++;throw Error('lost response');}return detail();};const port=createWorkflowPort({request,initialListing:listing});await select(port);await port.dispatch({type:'edit',edit:{type:'fields',fields:{description:'Unsent full text'}}});await port.dispatch({type:'save'});
  assert.equal(port.snapshot().attempt.status,'uncertain');assert.equal(posts,1);await assert.rejects(port.dispatch({type:'save'}),/unresolved/);await port.dispatch({type:'reinspect'});assert.equal(posts,1);
  const restored=createWorkflowPort({request,initial:port.capture(),initialListing:listing});assert.equal(restored.snapshot().draft.definition.description,'Unsent full text');assert.equal(restored.snapshot().attempt.status,'uncertain');assert.equal(posts,1);
});
test('owner receipt and readback separate saved effect from observation; newer typing is retained',async()=>{
  let release,posted;let current=detail();const gate=new Promise(r=>{release=r;});const request=async(_url,payload)=>{if(!payload)return structuredClone(current);posted=payload;await gate;current=detail('v2',payload.definition);return {effect:'saved',definition_id:'WDEF-one',receipt:{request_id:payload.request_id,definition_id:'WDEF-one',definition_revision:'v2'},read:handle('/one?version=v2')};};
  const port=createWorkflowPort({request,initialListing:listing});await select(port);await port.dispatch({type:'edit',edit:{type:'fields',fields:{title:'First'}}});const pending=port.dispatch({type:'save'});await port.dispatch({type:'edit',edit:{type:'fields',fields:{title:'Second'}}});release();await pending;
  assert.equal(posted.definition.title,'First');assert.equal(port.snapshot().read.value.definition.title,'First');assert.equal(port.snapshot().draft.definition.title,'Second');assert.equal(port.snapshot().draft.basis.payload.expected_revision,'v1');assert.equal(port.snapshot().attempt.effect,'saved');
});
test('scope mismatch, stale delivery, invalid full text, and prepare form recovery keep honest boundaries',async()=>{
  let release;const late=new Promise(r=>{release=r;});let read=0;const request=async()=>{if(++read===1){await late;return detail('old');}return detail('new');};const port=createWorkflowPort({request,initialListing:listing});const first=select(port);await port.dispatch({type:'reinspect'}).catch(()=>{}); // no owner handle until first read; not a silent invented URL
  const second=select(port);await second;release();await first;assert.equal(port.snapshot().read.value.version,'new');
  await port.dispatch({type:'text',name:'inputs',value:'[{ broken',invalid:true});await assert.rejects(port.dispatch({type:'save'}),/invalid/);await port.dispatch({type:'context',fields:{goal:'Full execution goal\nsecond line'}});
  const restored=createWorkflowPort({request,initial:port.capture(),initialListing:listing});assert.equal(restored.snapshot().draft.text_fields.inputs,'[{ broken');assert.equal(restored.snapshot().context.goal,'Full execution goal\nsecond line');
  assert.throws(()=>createWorkflowPort({initial:port.capture(),initialListing:{...listing,scope_id:'other'}}),/another workspace/);
});
test('lost create response recovers the exact owner-issued identity by request read, with zero replay',async()=>{
  let posted,posts=0;const request=async(url,payload)=>{if(payload){posted=payload;posts++;throw Error('response lost after save');}if(url.startsWith('/requests'))return {...detail('v-created',posted.definition),status:'RECORDED',effect:'saved',receipt:{request_id:posted.request_id,definition_id:'WDEF-one',definition_revision:'v-created'}};return detail('v-created',posted.definition);};
  const port=createWorkflowPort({request,initialListing:{...listing,actions:{...listing.actions,inspect_request:{http:{method:'GET',url:'/requests?facet=request'}}}}});await port.dispatch({type:'create'});await port.dispatch({type:'edit',edit:{type:'fields',fields:{title:'Lost but saved'}}});await port.dispatch({type:'save'});assert.ok(port.snapshot().selection.id.startsWith('local:'));assert.equal(port.snapshot().attempt.status,'uncertain');await port.dispatch({type:'recover'});assert.equal(posts,1);assert.equal(port.snapshot().selection.id,'WDEF-one');assert.equal(port.snapshot().draft,null);assert.equal(port.snapshot().attempt.recovered,true);assert.equal(port.snapshot().read.value.definition.title,'Lost but saved');
});
test('background save readback stays qualified to A while B remains selected',async()=>{
  let release;const gate=new Promise(r=>{release=r;}),a=detail(),b={...detail(),definition_id:'WDEF-two',definition:{...emptyWorkflow(),title:'B'}};
  const request=async(url,payload)=>{if(!payload)return url==='/two'?b:a;await gate;return {effect:'saved',definition_id:'WDEF-one',receipt:{request_id:payload.request_id,definition_id:'WDEF-one',definition_revision:'v2'},read:handle('/one')};};
  const port=createWorkflowPort({request,initialListing:listing});await select(port);await port.dispatch({type:'edit',edit:{type:'fields',fields:{title:'A draft'}}});const pending=port.dispatch({type:'save'});await port.dispatch({type:'select',id:'WDEF-two',read:handle('/two')});release();await pending;assert.equal(port.snapshot().selection.id,'WDEF-two');assert.equal(port.snapshot().read.io,'ready');assert.equal(port.snapshot().read.value.definition.title,'B');
});
test('typing during acknowledged CREATE retains text and requires exact guard adoption without duplicate create',async()=>{
  let release,posted,posts=0;const gate=new Promise(r=>{release=r;});const current=()=>detail('v-created',posted.definition);const request=async(_url,payload)=>{if(!payload)return current();posted=payload;posts++;await gate;return {...current(),effect:'saved',receipt:{request_id:payload.request_id,definition_id:'WDEF-one',definition_revision:'v-created'}};};
  const port=createWorkflowPort({request,initialListing:listing});await port.dispatch({type:'create'});await port.dispatch({type:'edit',edit:{type:'fields',fields:{title:'First'}}});const pending=port.dispatch({type:'save'});await port.dispatch({type:'edit',edit:{type:'fields',fields:{title:'Typed later'}}});release();await pending;
  assert.equal(port.snapshot().selection.id,'WDEF-one');assert.equal(port.snapshot().draft.definition.title,'Typed later');assert.equal(port.snapshot().draft.needs_adoption,true);await assert.rejects(port.dispatch({type:'save'}),/Compare and adopt/);assert.equal(posts,1);await port.dispatch({type:'compare'});await port.dispatch({type:'adopt',basis:port.snapshot().comparison.basis});assert.equal(port.snapshot().draft.basis.payload.definition_id,'WDEF-one');assert.equal(port.snapshot().draft.basis.payload.expected_revision,'v-created');
});
test('completed background CREATE does not pull selection away or leave a broken local visit',async()=>{
  let release,posted;const gate=new Promise(r=>{release=r;});const a=()=>detail('v-created',posted.definition),b={...detail(),definition_id:'WDEF-two'};const request=async(url,payload)=>{if(!payload)return url==='/two'?b:a();posted=payload;await gate;return {...a(),effect:'saved',receipt:{request_id:payload.request_id,definition_id:'WDEF-one',definition_revision:'v-created'}};};
  const port=createWorkflowPort({request,initialListing:listing});await port.dispatch({type:'create'});const pending=port.dispatch({type:'save'});await port.dispatch({type:'select',id:'WDEF-two',read:handle('/two')});release();await pending;assert.equal(port.snapshot().selection.id,'WDEF-two');await port.dispatch({type:'back'});assert.equal(port.snapshot().selection.id,'WDEF-one');assert.equal(port.snapshot().read.io,'ready');
});
test('historical selection capture/restoration keeps its exact version until explicit current read',async()=>{
  const calls=[],request=async url=>{calls.push(url);return detail(url==='/one?version=v1'?'v1':'v2');};const port=createWorkflowPort({request,initialListing:listing});await port.dispatch({type:'select',id:'WDEF-one',read:handle('/one?version=v1')});
  const capture=port.capture();assert.equal(capture.selection.read.http.url,'/one?version=v1');const restored=createWorkflowPort({request,initial:capture,initialListing:listing});await restored.dispatch({type:'select',...capture.selection});assert.equal(restored.snapshot().read.value.version,'v1');await restored.dispatch({type:'reinspect'});assert.equal(restored.snapshot().read.value.version,'v2');assert.deepEqual(calls,['/one?version=v1','/one?version=v1','/one']);
});
