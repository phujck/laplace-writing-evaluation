import assert from 'node:assert/strict';
import {test} from 'node:test';
import {parentContinuation,parentContinuationLabel,parentSynthesisSubmission,parentDispatchCancellationSubmission,preparedRunSubmission,preparedParentContinuations,renderParentContinuation,renderPreparedWork} from '../src/laplace/web/static_shared/prepared-work.mjs';
import {WorkspaceSession} from '../src/laplace/web/static_shared/workspace-session.mjs';
import {openSavedTurn} from '../src/laplace/web/static_shared/workspace-material.mjs';
import {workStandingLabel,mountOperatorWork} from '../src/laplace/web/static_shared/workspace-work.mjs';
import {installDOM,Node,findButton} from './helpers/evidence_reader_harness.mjs';
import {parentWire} from './helpers/parent_continuation_fixture.mjs';

const original=parentWire.observation;
test('actual continuation coordinates preserve caller, original parent, and exact reading handles',()=>{
 assert.equal(parentContinuation(original,{project:'book',sessionId:'WS-parent',turnId:'WT-parent'}),original);
 assert.equal(original.cancel_scope,'parent-observation');assert.equal(original.child_custody,'detached-supervised');
 for(const patch of [{session_id:'WS-other'},{turn_id:'WT-other'},{project:'other'},{children_active:true},{phase:'DONE'},{cancel_scope:'all-work'}])assert.throws(()=>parentContinuation({...original,...patch},{project:'book',sessionId:'WS-parent',turnId:'WT-parent'}));
 const crossed=structuredClone(original);crossed.dispatch_read.http.url+='&id=other';assert.throws(()=>parentContinuation(crossed,{project:'book'}));
 const recovered={...original,turn_id:'WT-explicit-recovery'};assert.equal(parentContinuation(recovered,{project:'book',sessionId:'WS-parent',turnId:'WT-explicit-recovery'}).origin_parent_turn_id,'WT-parent');
});

test('settled rejection and retained synthesis never become inferred Work acceptance',()=>{
 const rejected={...original,phase:'READY',execution_state:'COMPLETE',execution_settled:true,review_state:'REJECTED'};
 assert.match(parentContinuationLabel(rejected),/rejected review.*synthesis is needed/);
 const task={project:'book',status:'in-progress',lifecycle:{status:'in-progress',closed:false},readiness:{status:'IN_PROGRESS'},parent_continuation:rejected};
 assert.match(workStandingLabel(task),/rejected review/);assert.ok(!workStandingLabel(task).includes('accepted'));
 assert.match(parentContinuationLabel({...rejected,synthesis:{status:'VALID',attachment:'UNCONFIRMED'}}),/attachment is unconfirmed/);
});

test('stopped parent shows outstanding child custody, exact retained returns and read-only dispatch controls',async()=>{
 const dom=installDOM(),host=new Node('section'),reads=[],artifacts=[];dom.body.append(host);
 const stopped={...original,phase:'PARENT_STOPPED',children_active:2,readable_returns:[{packet:'develop',role:'worker',artifact:parentWire.artifact}]};
 try{
  renderParentContinuation(host,stopped,{project:'book',active:false,onOwner:(...args)=>reads.push(args),onArtifact:(...args)=>artifacts.push(args)});
  assert.match(host.textContent,/2 dispatched children remain active/);assert.match(host.textContent,/does not cancel dispatched work/);assert.match(host.textContent,/Nothing restarts automatically/);
  await findButton(host,'Inspect dispatched work').onclick();assert.equal(reads[0][0].id,original.dispatch_id);
  await findButton(host,'Read develop worker return').onclick();assert.equal(artifacts[0][2].artifactId,parentWire.artifact.id);
  assert.equal(findButton(host,'Cancel all work'),undefined);assert.equal(findButton(host,'Send'),undefined);assert.equal(dom.editor.value,'UNSAVED manuscript');
 }finally{dom.restore();}
});

test('continuation synthesis artifacts require their original digest and expose unconfirmed attachment',()=>{
 const dom=installDOM(),host=new Node('section');dom.body.append(host);
 const retained={...original,phase:'READY',synthesis:{required:true,status:'VALID',retained_status:'BLOCKED',artifact:parentWire.artifact,attachment:'UNCONFIRMED'}};
 try{
  renderParentContinuation(host,retained,{project:'book',onArtifact(){}});assert.match(host.textContent,/attachment is unconfirmed/);assert.ok(findButton(host,'Read retained synthesis'));
  const crossed=structuredClone(retained);crossed.synthesis.artifact.revision='0'.repeat(64);assert.throws(()=>parentContinuation(crossed,{project:'book'}));
 }finally{dom.restore();}
});

test('selected-parent phase painting preserves native controls, draft and queued-input receipts',()=>{
 const dom=installDOM(),host=new Node('section');dom.body.append(host);
 const current=Object.create(WorkspaceSession.prototype);Object.assign(current,{project:'book',session:'WS-parent',active:'WT-parent',viewEpoch:1,
  activeCapabilities:{can_interrupt:true,can_steer:false,can_offer_input:true,input_delivery_modes:['project_tool_boundary']},
  controlPending:{id:'INPUT-kept'},messageIntent:{context:{surface:'project',label:'Project'}},find:key=>key==='[data-parent-continuation]'?host:null});
 try{
  current.paintParentContinuation({...original,children_active:2},{turnId:'WT-parent',active:true});assert.match(host.textContent,/Parent waiting/);
  const details=host.querySelector('details');details.open=true;
  current.paintParentContinuation({...original,children_active:2},{turnId:'WT-parent',active:true});assert.equal(host.querySelector('details'),details);
  assert.equal(current.activeCapabilities.can_interrupt,true);assert.equal(current.activeCapabilities.can_offer_input,true);assert.equal(current.controlPending.id,'INPUT-kept');assert.equal(current.messageIntent.context.label,'Project');
  current.stopRequested=true;current.paintParentContinuation(original,{turnId:'WT-parent',active:true});assert.match(host.textContent,/Stop requested/);
  assert.equal(host.querySelector('details').open,true);
  current.paintParentContinuation({...original,turn_id:'WT-other'},{turnId:'WT-parent',active:true});assert.match(host.textContent,/needs reinspection/);assert.equal(current.activeCapabilities.can_interrupt,true);
  current.paintParentContinuation(undefined,{turnId:'WT-parent',active:true,keep:true});assert.match(host.textContent,/needs reinspection/);
  current.paintParentContinuation(null);assert.equal(host.hidden,true);assert.equal(current.parentContinuationValue,null);
 }finally{dom.restore();}
});

test('terminal observation cannot return to waiting or accept another generation',()=>{
 const dom=installDOM(),host=new Node('section');dom.body.append(host);
 const current=Object.create(WorkspaceSession.prototype);Object.assign(current,{project:'book',session:'WS-parent',active:'WT-parent',find:key=>key==='[data-parent-continuation]'?host:null});
 try{
  current.paintParentContinuation({...original,phase:'PARENT_STOPPED'},{turnId:'WT-parent',active:true});
  current.paintParentContinuation(original,{turnId:'WT-parent',active:true});assert.equal(current.parentContinuationValue.phase,'PARENT_STOPPED');assert.match(host.textContent,/observation stopped/);
  current.paintParentContinuation({...original,generation:'DWAIT-other'},{turnId:'WT-parent',active:true});assert.match(host.textContent,/generation changed/);assert.equal(current.parentContinuationValue.phase,'PARENT_STOPPED');
  current.paintParentContinuation(null);current.paintParentContinuation({...original,phase:'OBSERVATION_EXPIRED'},{turnId:'WT-parent',active:false});
  current.paintParentContinuation(original,{turnId:'WT-parent',active:true});assert.equal(current.parentContinuationValue.phase,'OBSERVATION_EXPIRED');
 }finally{dom.restore();}
});

test('a failed return read remains a visible owner diagnostic without a fabricated artifact control',()=>{
 const dom=installDOM(),host=new Node('section');dom.body.append(host);
 try{
  renderParentContinuation(host,{...original,phase:'READY',readable_returns:[{packet:'develop',role:'worker',status:'UNAVAILABLE',return_path:'development/missing.json',reason:'Retained artifact is missing.'}]},{project:'book',onArtifact(){}});
  assert.match(host.textContent,/develop worker return is unavailable/);assert.match(host.textContent,/Retained artifact is missing/);assert.equal(findButton(host,'Read develop worker return'),undefined);
 }finally{dom.restore();}
});

test('contextual dispatch cancellation uses exact current owner guards and leaves manuscript intent intact',async()=>{
 const dom=installDOM(),host=new Node('section'),posts=[];dom.body.append(host);
 const detail=structuredClone(parentWire.detail);detail.task.dispatch={...detail.task.dispatch,parent_continuation:{...original,phase:'PARENT_STOPPED',children_active:2}};
 let controller;
 try{
  controller=await mountOperatorWork(host,{project:'book',summary:{tasks:[detail.task]},initialWork:detail.task.id,
    request:async(path,payload)=>{if(payload)posts.push({path,payload});return structuredClone(detail);}});
  assert.match(host.textContent,/Parent observation stopped/);assert.ok(findButton(host,'Cancel dispatched work'));
  await findButton(host,'Cancel dispatched work').onclick();assert.equal(posts.length,1);assert.equal(posts[0].path,'/work/transition');
  assert.deepEqual(posts[0].payload,original.dispatch_cancel_action.payload);
  assert.equal(dom.editor.value,'UNSAVED manuscript');assert.match(host.textContent,/cleanup standing/);
 }finally{controller?.destroy();dom.restore();}
});

test('owner-issued accepted and rejected synthesis attachments keep exact guards and recorded disposition',async()=>{
 const dom=installDOM();
 try{
  for(const [name,standing] of [['accepted','done'],['rejected','blocked']]){
   const value={...original,...parentWire[name],phase:'READY',parent_active:false,execution_settled:true,execution_state:'COMPLETE',review_state:name==='accepted'?'ACCEPTED':'REJECTED'};
   const submission=parentSynthesisSubmission(value,'book'),action=value.synthesis.attach_action;
   assert.equal(submission.url,action.http.url);assert.deepEqual(submission.payload,action.payload);assert.equal(submission.payload.status,standing);
   const host=new Node('section'),attached=[];dom.body.append(host);
   renderParentContinuation(host,value,{project:'book',onAttach:read=>attached.push(read)});
   assert.ok(!host.textContent.includes('synthesis is needed'));await findButton(host,'Attach retained synthesis to Work').onclick();assert.deepEqual(attached,[submission]);
   assert.equal(dom.editor.value,'UNSAVED manuscript');
   for(const patch of [
    {...action,http:{method:'POST',url:'/authoring/turn'}},
    {...action,payload:{...action.payload,project:'other'}},
    {...action,payload:{...action.payload,status:standing==='done'?'blocked':'done'}},
    {...action,payload:{...action.payload,expected_dependency_revision:'stale'}},
    {...action,payload:{...action.payload,evidence:['development/other-retained.json']}},
    {...action,payload:{...action.payload,text:'Injected provider message'}}
   ])assert.throws(()=>parentSynthesisSubmission({...value,synthesis:{...value.synthesis,attach_action:patch}},'book'),/matching Work attachment/);
  }
 }finally{dom.restore();}
});

test('a held attachment preserves readable retained synthesis and exposes the owner clearing reason',()=>{
 const dom=installDOM(),host=new Node('section');dom.body.append(host);
 try{
  const synthesis=parentWire.accepted.synthesis;
  const value={...original,...parentWire.accepted,phase:'READY',parent_active:false,
    synthesis:{...synthesis,attach_action:{...synthesis.attach_action,permitted:false,reason:'Work was explicitly withdrawn; inspect its current disposition.'}}};
  renderParentContinuation(host,value,{project:'book',onArtifact(){},onAttach(){assert.fail('Held attachment must not submit');}});
  assert.match(host.textContent,/Work was explicitly withdrawn/);assert.ok(findButton(host,'Read retained synthesis'));assert.equal(findButton(host,'Attach retained synthesis to Work'),undefined);
 }finally{dom.restore();}
});

test('active-parent recovery stays unavailable and dispatch cancellation stays bound to its exact owner',()=>{
 const dom=installDOM(),host=new Node('section');dom.body.append(host);
 try{
  const value={...original,...parentWire.accepted,phase:'READY',parent_active:true};
  renderParentContinuation(host,value,{project:'book',onAttach(){},onConversation(){}});
  assert.equal(findButton(host,'Attach retained synthesis to Work'),undefined);assert.equal(findButton(host,'Open recorded parent'),undefined);
  const cancellation=parentDispatchCancellationSubmission(original,'book');assert.deepEqual(cancellation.payload,original.dispatch_cancel_action.payload);
  for(const patch of [
   {...original.dispatch_cancel_action,payload:{...cancellation.payload,id:'WORK-other'}},
   {...original.dispatch_cancel_action,payload:{...cancellation.payload,status:'done'}},
   {...original.dispatch_cancel_action,project:'other'},
   {...original.dispatch_cancel_action,permitted:false},
   {...original.dispatch_cancel_action,http:{method:'POST',url:'/authoring/interrupt'}}
  ])assert.throws(()=>parentDispatchCancellationSubmission({...original,dispatch_cancel_action:patch},'book'),/matching cancellation action/);
 }finally{dom.restore();}
});

test('a retained action cannot mutate after a newer turn starts in the same selected conversation',async()=>{
 const dom=installDOM(),host=new Node('section'),note=new Node('p'),posts=[];dom.body.append(host,note);
 const previousFetch=globalThis.fetch;
 const current=Object.create(WorkspaceSession.prototype);Object.assign(current,{project:'book',session:'WS-parent',active:'WT-parent',role:'author',viewEpoch:1,
  find:key=>key==='[data-parent-continuation]'?host:key==='[data-status]'?note:null});
 try{
  globalThis.fetch=async(...args)=>{posts.push(args);throw Error('Stale action reached transport');};
  current.paintParentContinuation(original,{turnId:'WT-parent',active:true});const cancel=findButton(host,'Cancel dispatched work');assert.ok(cancel);
  current.active='WT-newer';await cancel.onclick();assert.equal(posts.length,0);assert.equal(current.active,'WT-newer');assert.equal(dom.editor.value,'UNSAVED manuscript');
 }finally{globalThis.fetch=previousFetch;dom.restore();}
});

test('an exact older parent reply exposes retained recovery without targeting the newer conversation',async()=>{
 const dom=installDOM(),calls=[],owners=[],conversations=[];
 try{
  const receipt={...original,phase:'OBSERVATION_EXPIRED',parent_active:false};
  const turn={id:original.turn_id,session_id:original.session_id,text:'Original admitted parent request',reply:{text:'Observation ended; dispatch retained.'},parent_continuation:receipt};
  const dialog=await openSavedTurn({project:'book',turnId:original.turn_id,request:async path=>{calls.push(path);return {project:'book',turn};},onInspectOwner:(...args)=>owners.push(args),onConversation:id=>conversations.push(id)});
  assert.equal(calls.length,1);assert.match(dialog.textContent,/Connected wait ended/);assert.match(dialog.textContent,/new author message in the recorded parent conversation/);
  await findButton(dialog,'Inspect dispatched work').onclick();assert.equal(owners[0][0].id,original.dispatch_id);assert.equal(conversations.length,0);assert.equal(dom.editor.value,'UNSAVED manuscript');
  assert.equal(findButton(dialog,'Cancel dispatched work'),undefined);assert.equal(findButton(dialog,'Attach retained synthesis to Work'),undefined);
  await findButton(dialog,'Open recorded parent').onclick();assert.deepEqual(conversations,[original.origin_parent_session_id]);assert.equal(dialog.isConnected,false);
 }finally{dom.restore();}
});

test('readonly Work peek shows the same missing judge return and exact failed attempts in context',async()=>{
 const dom=installDOM(),host=new Node('section'),calls=[];dom.body.append(host);let controller;
 try{
  const value=parentWire.no_return,judge=value.detail.task.dispatch.children.find(child=>child.role==='judge');
  assert.equal(judge.state,'NO-RETURN');assert.equal(judge.reply_status,'completed');assert.match(judge.failure_summary,/store_artifact.*not permitted/);
  controller=await mountOperatorWork(host,{project:'book',detailOnly:true,readOnly:true,initialWork:value.detail.task.id,initialDetail:value.detail,
    request:async(path,payload)=>{calls.push({path,payload});assert.equal(payload,undefined);const q=new URL(path,'http://local').searchParams;assert.equal(q.get('id'),judge.turn_id);return q.get('view')==='summary'?value.turn_summary:value.turn_failures;}});
  assert.match(host.textContent,/Replied without a typed return/);assert.match(host.textContent,/Provider reply: replied · typed return: missing/);assert.match(host.textContent,/store_artifact.*not permitted/);
  assert.equal(findButton(host,'Cancel dispatched work'),undefined);assert.equal(findButton(host,'Use for next message'),undefined);
  await findButton(host,'Read '+judge.packet+' failed attempts').onclick();
  assert.equal(calls.length,2);assert.ok(calls[0].path.includes('view=summary'));assert.ok(calls[1].path.includes('view=failures'));
  const reader=dom.dialogs().at(-1);assert.match(reader.textContent,/store_artifact.*not permitted/);assert.equal(findButton(reader,'Open this conversation'),undefined);assert.equal(dom.editor.value,'UNSAVED manuscript');
  controller.destroy();assert.equal(reader.isConnected,false);
 }finally{controller?.destroy();dom.restore();}
});

test('parent panel surfaces owner child publication failure without inferring accepted completion',async()=>{
 const dom=installDOM(),host=new Node('section'),turns=[],owners=[];dom.body.append(host);
 try{
  const value=parentWire.no_return.continuation,judge=value.child_outcomes.find(child=>child.role==='judge');
  assert.equal(value.execution_settled,true);assert.equal(value.execution_state,'FAILED');assert.equal(value.review_state,'PENDING');
  renderParentContinuation(host,value,{project:'book',onTurn:(...args)=>turns.push(args),onOwner:(...args)=>owners.push(args)});
  assert.match(host.textContent,/missing or failed evidence/);assert.match(host.textContent,/Recorded tool failure: store_artifact.*not permitted/);assert.ok(!host.textContent.includes('review accepted'));
  await findButton(host,'Read '+judge.packet+' failed attempts').onclick();assert.deepEqual(turns,[[judge.turn_id,{focusView:'failures'}]]);
  await findButton(host,'Inspect '+judge.packet+' return publication').onclick();assert.equal(owners.at(-1)[0].turnId,judge.turn_id);assert.equal(dom.editor.value,'UNSAVED manuscript');
 }finally{dom.restore();}
});

test('reply-only publication inability remains a reported reason without a fabricated tool refusal',async()=>{
 const dom=installDOM(),host=new Node('section'),turns=[];dom.body.append(host);
 try{
  const value=parentWire.reply_only.continuation,judge=value.child_outcomes.find(child=>child.role==='judge');
  assert.equal(judge.failure_count,0);assert.equal(judge.state,'NO-RETURN');assert.match(judge.reply_excerpt,/advertised as unavailable/);
  assert.ok(!judge.failure_summary.includes('store_artifact'));
  renderParentContinuation(host,value,{project:'book',onTurn:(...args)=>turns.push(args)});
  assert.match(host.textContent,/Recorded child reply: I could not publish/);assert.equal(findButton(host,'Read '+judge.packet+' failed attempts'),undefined);
  await findButton(host,'Read '+judge.packet+' exact turn').onclick();assert.deepEqual(turns,[[judge.turn_id]]);assert.equal(dom.editor.value,'UNSAVED manuscript');
 }finally{dom.restore();}
});

test('prepared Work keeps the exact retained dispatch after a newer parent ended without another wait',async()=>{
 const dom=installDOM(),host=new Node('section'),opened=[],used=[];dom.body.append(host);
 try{
  const value=parentWire.retained_prepared,execution=value.execution,task={...value.task,prepared_execution:execution};
  assert.equal(execution.items.at(-1).turn_id,'WT-no-new-wait');assert.equal(execution.items.at(-1).parent_continuation,undefined);
  assert.equal(preparedParentContinuations(task,execution,'book')[0].dispatch_id,value.dispatch_id);
  assert.equal(preparedRunSubmission(value.run_action,'book',task).session_id,'WS-parent');assert.ok(!value.run_action.payload.text.includes('create a dispatch_plan'));
  renderPreparedWork(host,{project:'book',task,preparation:{current:true},execution,action:value.run_action,
    onOwner:(...args)=>opened.push(args),onUse:(...args)=>used.push(args)});
  assert.match(host.textContent,/Parent observation stopped/);await findButton(host,'Inspect dispatched work').onclick();assert.equal(opened[0][0].id,value.dispatch_id);
  await findButton(host,'Prepare continuation message').onclick();assert.equal(used[0][0],value.run_action);assert.equal(dom.editor.value,'UNSAVED manuscript');
  const wrong={...execution,retained_dispatches:[{...execution.retained_dispatches[0],work_id:'WORK-other'}]};
  assert.throws(()=>preparedParentContinuations(task,wrong,'book'),/match|parent Work/);
  assert.deepEqual(preparedParentContinuations(task,{...execution,retained_dispatches:[]},'book'),[],'An explicit empty current dependency scope cannot revive an old turn receipt.');
 }finally{dom.restore();}
});
