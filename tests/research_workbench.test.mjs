import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createWorkbenchState,referenceKey,issuedHTTP} from '../src/laplace/web/static_shared/research-workbench-state.mjs';
import {actionPayload,createActionAttempt,actionDraftKey} from '../src/laplace/web/static_shared/research-workbench-actions.mjs';
import {messageTarget,encodeComposerDraft,decodeComposerDraft} from '../src/laplace/web/static_shared/workspace-interaction.mjs';
import {WorkspaceSession} from '../src/laplace/web/static_shared/workspace-session.mjs';
const pin='sha256:'+'a'.repeat(64),otherPin='sha256:'+'b'.repeat(64);
const ref=id=>({schema_version:'laplace.reference/1',owner:'domain.research',kind:'concept',identity:{project:'public',node:id}});
const read=id=>({http:{method:'GET',url:'/work/discovery?facet=object&reference='+encodeURIComponent(JSON.stringify(ref(id)))}});
const envelope=(id=null,scope='public-scope')=>({schema_version:'laplace.object-facets/1',view:id?'object':'workspace',subject:id?ref(id):null,basis:pin,scope:{kind:'owned-workspace'},scope_id:scope,coverage:{state:'AVAILABLE',known:1,omitted:0},facets:{},items:[]});
const memory=()=>{const values=new Map(),writes=[];return {values,writes,getItem:key=>values.get(key)??null,setItem(key,value){values.set(key,value);writes.push({key,value});}};};
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};

test('Current selected visit rejects stale responses and cross-root recovery, retaining exact Back reading',async()=>{
  const delayed=deferred(),state=createWorkbenchState({request:url=>url.includes('slow')?delayed.promise:Promise.resolve(envelope('new')),initialWorkspace:envelope(),storage:memory(),backup:null,key:'public'});
  const first=state.read({http:{method:'GET',url:'/work/discovery?slow=1'}},ref('old'));await state.read(read('new'),ref('new'));delayed.resolve(envelope('old'));assert.equal(await first,null);assert.equal(state.snapshot().selected.value.subject.identity.node,'new');
  await state.read(read('new'),ref('new'));assert.equal(state.back(),true);assert.equal(state.snapshot().selected.retained,true);assert.equal(state.snapshot().selected.value.basis,pin);state.destroy();
  const wrong=createWorkbenchState({request:async()=>envelope('new','other-root'),initialWorkspace:envelope(),storage:memory(),backup:null,key:'public'});await assert.rejects(wrong.read(read('new'),ref('new')),/workspace changed/);assert.equal(wrong.snapshot().selected,null);wrong.destroy();
});

test('Typing commits only its compact draft, restores uncertain wire without replay, and never stores owner bodies',()=>{
  const storage=memory(),state=createWorkbenchState({request:()=>{throw Error('No read expected');},initialWorkspace:{...envelope(),private_payload:'not-a-draft'},storage,backup:null,key:'public'});
  state.updateDraft('first',{values:{meaning:'Exact α 中 🌱'},dirty:true});state.updateDraft('second',{values:{meaning:'Other'}});const before=storage.writes.length;state.updateDraft('first',{values:{meaning:'Newer α'}});assert.equal(storage.writes.length-before,1);assert.ok(!storage.writes.some(row=>row.value.includes('not-a-draft')));
  state.updateDraft('first',{pending:{url:'/effect',payload:{request_id:'original',meaning:'Original'},observation:'AWAITING_RESPONSE'}});state.destroy();let calls=0;const restored=createWorkbenchState({request:()=>{calls++;},initialWorkspace:envelope(),storage,backup:null,key:'public'});assert.equal(restored.draft('first').pending.observation,'UNKNOWN');assert.equal(restored.draft('first').values.meaning,'Newer α');assert.equal(calls,0);restored.destroy();
});

test('A successful newer backup defeats an old primary draft without silently choosing conflicting copies',()=>{
  const primary=memory(),backup=memory(),state=createWorkbenchState({request:async()=>envelope(),initialWorkspace:envelope(),storage:primary,backup,key:'public'});state.updateDraft('question',{values:{meaning:'Old'}});const set=primary.setItem;primary.setItem=()=>{throw Error('primary full');};state.updateDraft('question',{values:{meaning:'Newer α'},pending:{payload:{request_id:'exact'},observation:'AWAITING_RESPONSE'}});assert.equal(state.storageError,'');state.destroy();
  const restored=createWorkbenchState({request:async()=>envelope(),initialWorkspace:envelope(),storage:primary,backup,key:'public'});assert.equal(restored.draft('question').values.meaning,'Newer α');assert.equal(restored.draft('question').pending.payload.request_id,'exact');restored.destroy();primary.setItem=set;
  const raw=JSON.parse(backup.getItem('public:draft:question'));primary.setItem('public:draft:question',JSON.stringify({...raw,values:{meaning:'Conflicting α'}}));const conflict=createWorkbenchState({request:async()=>envelope(),initialWorkspace:envelope(),storage:primary,backup,key:'public'});assert.match(conflict.recoveryError,/disagree/);assert.throws(()=>conflict.updateDraft('question',{values:{meaning:'replace'}}),/disagree/);assert.match(primary.getItem('public:draft:question'),/Conflicting α/);conflict.destroy();
});

test('Action admission preserves held guard and exact unknown wire across new typing and uses pure reconciliation',async()=>{
  const storage=memory(),response=deferred(),started=deferred(),requests=[],state=createWorkbenchState({request:async()=>envelope(),initialWorkspace:envelope(),storage,backup:null,key:'public'}),action={id:'question',title:'Save question',permitted:true,fields:[{name:'meaning',label:'Your question',type:'textarea',required:true}],http:{method:'POST',url:'/effect',payload:{request_id:'owner-issued',base_revision:pin}},reconcile:{http:{method:'GET',url:'/status?request_id=owner-issued'}}};
  state.updateDraft('question',{action,values:{meaning:'Original α'},dirty:true});const attempt=createActionAttempt({action,state,key:'question',request:async(url,payload)=>{requests.push({url,payload});if(payload)started.resolve();return payload?response.promise:{state:'RECORDED',id:'owner-issued'};},observe:value=>({state:value.state||'UNKNOWN'})});
  const pending=attempt.submit();await started.promise;assert.equal(requests.length,1);state.updateDraft('question',{values:{meaning:'Newer 中'}});response.reject(Error('ACK lost'));await assert.rejects(pending,/ACK lost/);assert.equal(state.draft('question').pending.payload.meaning,'Original α');assert.equal(state.draft('question').pending.payload.base_revision,pin);await assert.rejects(attempt.retry(),/Inspect the original/);await attempt.reconcile();assert.equal(state.draft('question').pending,null);assert.equal(state.draft('question').values.meaning,'Newer 中');assert.equal(state.draft('question').dirty,true);assert.equal(requests.length,2);assert.equal(requests[1].payload,undefined);state.destroy();
});

test('Closed action edits cannot overwrite owner guard and object context survives exact composer recovery',()=>{
  const action={permitted:true,http:{method:'POST',payload:{base_revision:pin}},fields:[{name:'meaning',label:'Question',type:'text',required:true}]};assert.deepEqual(actionPayload(action,{meaning:'Question?',base_revision:otherPin}),{base_revision:pin,meaning:'Question?'});
  const pointer={reference:ref('Q1'),expected_basis:pin},context=messageTarget({surface:'project',label:'Question',object_context:pointer}),text='Unsent draft α 中 🌱';const decoded=decodeComposerDraft(encodeComposerDraft(text,{context}));assert.equal(decoded.text,text);assert.deepEqual(decoded.intent.context.object_context,pointer);pointer.reference.identity.node='mutated';assert.equal(context.object_context.reference.identity.node,'Q1');assert.throws(()=>messageTarget({object_context:{reference:ref('Q1'),expected_basis:pin,authority:'write'}}),/Inspect this object/);
  assert.equal(referenceKey({...ref('Q1'),version:{pin}}),referenceKey(ref('Q1')));assert.throws(()=>issuedHTTP({http:{method:'GET',url:'https://foreign.example/read'}}),/selected local action/);
});


test('Native workspace and selected-window rendering retain tabs, source text and compact input selection',async()=>{
  const {mountResearchFixture}=await import('./helpers/research_workbench_fixture.mjs');const fixture=await mountResearchFixture({selected:true});
  try{const {host,controller,calls}=fixture;assert.match(host.textContent,/PURPOSE END/);assert.match(host.textContent,/SOURCE END/);const tabs=host.querySelector('.rw-tabs'),source=host.querySelector('.rw-recorded'),button=host.querySelectorAll('button').find(row=>row.textContent==='Include this inspected window as an input');button.focus();button.onclick();assert.equal(document.activeElement,button);assert.equal(host.querySelector('.rw-recorded'),source);assert.equal(controller.state.draft('@inputs').entries[0].descriptor.selection.offset,0);controller.state.setTab('settings');assert.equal(host.querySelector('.rw-tabs'),tabs);controller.state.setTab('evidence');assert.match(host.textContent,/SOURCE END/);assert.equal(calls.length,3);assert.equal(calls.filter(row=>row.payload).length,0);}
  finally{fixture.restore();}
});

test('Explicit situated Use preserves prose and earlier attachments, while late target or session changes refuse',()=>{
  const text={value:'Unsent exact α 中 🌱'},writes=[],context={surface:'sources',label:'Earlier reading',material_read:{artifact_id:'earlier'}},session={project:'public',session:'WS-public',viewEpoch:4,intentRevision:2,selectedSessionRecord:null,messageIntent:{context},selectionOverride:{files:['earlier.txt']},authoredContext(){return this.messageIntent.context;},find:()=>text,persistComposerDraft:value=>writes.push(value),scope(){},status(){}};
  const target={session_id:session.session,context:structuredClone(context)},pointer={reference:ref('Q1'),expected_basis:pin};WorkspaceSession.prototype.useResearchObject.call(session,pointer,'Question Q1',target,{epoch:4,intentRevision:2});assert.equal(text.value,'Unsent exact α 中 🌱');assert.deepEqual(writes,[text.value]);assert.equal(session.messageIntent.context.material_read.artifact_id,'earlier');assert.equal(session.messageIntent.context.object_context.reference.identity.node,'Q1');assert.deepEqual(session.messageIntent.selection,{files:['earlier.txt']});
  assert.throws(()=>WorkspaceSession.prototype.useResearchObject.call(session,pointer,'Question Q1',target,{epoch:4,intentRevision:2}),/changed after opening/);assert.equal(writes.length,1);session.messageIntent.submission={request_id:'pending'};assert.throws(()=>WorkspaceSession.prototype.useResearchObject.call(session,pointer,'Question Q1',{session_id:'WS-public',context:session.authoredContext()}),/retained message submission/);assert.equal(writes.length,1);
});


test('Closed preparation cannot replace a newer uncertain wire; typed fields retain exact numeric and selected descriptors',async()=>{
  const native=globalThis.crypto,descriptor=Object.getOwnPropertyDescriptor(globalThis,'crypto'),digest=deferred(),oldDigest=native.subtle.digest.bind(native.subtle);let first=true,current=true;Object.defineProperty(globalThis,'crypto',{configurable:true,value:{subtle:{digest:(...args)=>{if(first){first=false;return digest.promise.then(()=>oldDigest(...args));}return oldDigest(...args);}}}});
  const state=createWorkbenchState({request:async()=>envelope(),initialWorkspace:envelope(),storage:memory(),backup:null,key:'public'}),action={id:'create',title:'Save',permitted:true,fields:[{name:'meaning',label:'Meaning',type:'text',required:true}],http:{method:'POST',url:'/effect',payload:{request_id:'original',project:'public'}}};state.updateDraft('q',{action,values:{meaning:'OLD'}});let posts=0;
  try{const attempt=createActionAttempt({action,state,key:'q',request:async()=>{posts++;},isCurrent:()=>current});const old=attempt.submit();current=false;state.updateDraft('q',{values:{meaning:'NEW'},pending:{payload:{request_id:'newer',meaning:'NEW'},url:'/effect',observation:'UNKNOWN'}});digest.resolve();await old;assert.equal(posts,0);assert.equal(state.draft('q').pending.payload.request_id,'newer');assert.equal(state.draft('q').values.meaning,'NEW');}
  finally{state.destroy();if(descriptor)Object.defineProperty(globalThis,'crypto',descriptor);else delete globalThis.crypto;}
  const input={reference:ref('Q1'),expected_basis:pin},typed={permitted:true,http:{method:'POST',payload:{expected_run_revision:pin}},fields:[{name:'recipients.writer',label:'Writer',type:'select',required:true,choices:[{value:'RB-exact',label:'Named writer'}]},{name:'lifetime_s',label:'Duration',type:'number',required:true,minimum:60,maximum:2592000},{name:'inputs',label:'Inputs',type:'selected-inputs',required:true}]};
  const payload=actionPayload(typed,{'recipients.writer':'RB-exact',lifetime_s:'86400',inputs:[input]});assert.equal(payload.lifetime_s,86400);assert.deepEqual(payload.recipients,{writer:'RB-exact'});assert.deepEqual(payload.inputs,[input]);assert.equal(payload.expected_run_revision,pin);assert.throws(()=>actionPayload(typed,{'recipients.writer':'Named writer',lifetime_s:'86400',inputs:[input]}),/offered/);assert.throws(()=>actionPayload({...typed,fields:[{name:'__proto__.x',type:'text',label:'Bad'}]},{}),/unsupported/);
});


test('Dependent actions retain separate target drafts without rebasing an uncertain original',()=>{
  const action=target=>({id:'mark-reconsideration',http:{payload:{operation:'mark-reconsideration',reference:ref(target),expected_basis:pin}}}),source=ref('R7');
  assert.notEqual(actionDraftKey(action('C12'),source),actionDraftKey(action('C9'),source));
  const changed=action('C12');changed.http.payload.expected_basis=otherPin;assert.equal(actionDraftKey(action('C12'),source),actionDraftKey(changed,source));
});

test('Damaged recovered actions cannot retry or settle; intact original wire survives newer prose',async()=>{
  const {feedbackWireDigest}=await import('../src/laplace/web/static_shared/feedback-route-port.mjs');
  const action={id:'question',title:'Save question',permitted:true,fields:[{name:'meaning',label:'Your question',type:'text',required:true}],http:{method:'POST',url:'/work/object-change',payload:{project:'public',operation:'save-question',request_id:'original',base_revision:pin}},reconcile:{http:{method:'GET',url:'/status'}},settle:{http:{method:'POST',url:'/work/object-change',payload:{project:'public',operation:'settle'}},field:'original_request'}},values={meaning:'Original question'},payload=actionPayload(action,values),wire=JSON.stringify(payload),wire_sha256=await feedbackWireDigest(wire);
  for(const damage of ['missing-wire','empty-wire','missing-digest','changed-payload','changed-url','changed-template','changed-values','changed-held-action','intact']){
    const state=createWorkbenchState({request:async()=>envelope(),initialWorkspace:envelope(),storage:memory(),backup:null,key:'public'}),pending={action:structuredClone(action),values:structuredClone(values),payload:structuredClone(payload),url:action.http.url,wire,wire_sha256,observation:'UNKNOWN'},held=structuredClone(action),posts=[];
    if(damage==='missing-wire')delete pending.wire;if(damage==='empty-wire')pending.wire='';if(damage==='missing-digest')delete pending.wire_sha256;if(damage==='changed-payload')pending.payload.meaning='Corrupted replacement';if(damage==='changed-url')pending.url='/other-effect';if(damage==='changed-template')pending.action.http.payload.base_revision=otherPin;if(damage==='changed-values')pending.values.meaning='Changed after admission';if(damage==='changed-held-action')held.http.payload.base_revision=otherPin;
    state.updateDraft('q',{action:held,values:{meaning:'Newer unsent α 中 🌱'},pending});
    const attempt=createActionAttempt({action,state,key:'q',observe:()=>({state:'NONE'}),request:async(url,body)=>{if(body)posts.push({url,body});return {};}});
    await attempt.reconcile();if(damage==='intact'){await attempt.retry();assert.deepEqual(posts,[{url:action.http.url,body:payload}]);}else{await assert.rejects(attempt.retry(),/damaged or incomplete/);await assert.rejects(attempt.settle(),/damaged or incomplete/);assert.equal(posts.length,0,damage);}
    assert.equal(state.draft('q').values.meaning,'Newer unsent α 中 🌱');assert.ok(state.draft('q').pending);state.destroy();
  }
});
