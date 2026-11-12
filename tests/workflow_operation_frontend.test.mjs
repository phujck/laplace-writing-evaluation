// Existing native surfaces with controlled transport. No browser geometry,
// current owner authority, live run or provider completion is inferred here.
import {register} from 'node:module';register(new URL('./helpers/shared_resolve.mjs',import.meta.url));
import test from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';
import {installHTMLDocument} from './helpers/html_dom.mjs';
import {mountWorkflowEditor} from '../src/laplace/web/static_shared/workspace-workflow-editor.mjs';
import {conversationOperationPresentation} from '../src/laplace/web/static_shared/workspace-session.mjs';
const sample=JSON.parse(readFileSync(new URL('./fixtures/workflow_history/public-owner.json',import.meta.url))).lineage_form_sample,copy=structuredClone;
// Release-route controls (Rootb77a R1-R5): the production editor/port with public fixture DTOs; GET only, never POST.
const releaseTick=()=>new Promise(resolve=>setTimeout(resolve,0));
async function releaseEditor({priorSaved=true,selected=sample.selected,listing=sample.listing,fail=null,late=null}={}){const env=installHTMLDocument({width:390}),calls=[];try{const host=document.createElement('main');document.body.append(host);
 const editor=await mountWorkflowEditor(host,{storage:{getItem:()=>null,setItem(){},removeItem(){}},...(priorSaved?{initialReference:sample.selected.reference,initialRead:sample.listing.definitions[0].read}:{}),request:async(url,payload)=>{calls.push({url,payload});assert.equal(payload,undefined,'release-route controls never POST');if(String(url).includes('app-runs')){if(late)return new Promise((_,reject)=>late(reject));if(fail)throw Object.assign(Error(fail),{status:422});}return copy(url==='/work/workflow-definitions'?listing:selected);}});
 return {host,calls,editor,close(){editor.destroy();env.restore();}};}catch(error){env.restore();throw error;}}
test('release route R2: discarding a never-saved local draft closes it without a phantom read or POST',async()=>{
 for(const priorSaved of [false,true]){const view=await releaseEditor({priorSaved});try{const {editor,host,calls}=view;
  await editor.port.dispatch({type:'create',definition:copy(sample.selected.definition)});assert.match(editor.port.snapshot().selection.id,/^local:/);
  const before=calls.length,discard=[...host.querySelectorAll('button')].find(node=>node.textContent==='Discard unsaved edits');await discard.onclick();
  const state=editor.port.snapshot();assert.equal(calls.length,before,'no read of the discarded local id');assert.equal(state.draft,null);
  assert.ok(!state.selection||state.selection.id===sample.selected.definition_id,'chooser or the qualified previous saved workflow');if(!priorSaved)assert.equal(state.selection,null);
  assert.equal(host.textContent.includes('Reading selected workflow'),false);assert.equal(String(editor.port.capture().selection?.id||'').startsWith('local:'),false);
  await editor.port.dispatch({type:'back'});assert.equal(String(editor.port.snapshot().selection?.id||'').startsWith('local:'),false,'Back never returns to a discarded local draft');
 }finally{view.close();}}
});
test('release route R3: discarding saved-workflow edits returns focus to the current editor only',async()=>{const view=await releaseEditor();try{const {editor,host,calls}=view;
 await editor.port.dispatch({type:'edit',edit:{type:'fields',fields:{title:'Public Ω edit'}}});assert.ok(editor.port.snapshot().draft);
 const selected=editor.port.snapshot().selection.id,before=calls.length,discard=host.querySelector('[data-action="discard"]'),proto=Object.getPrototypeOf(discard),own=Object.hasOwn(proto,'focus'),focus=proto.focus;
 // Test double: as in browsers, a disabled control cannot take focus (the micro DOM otherwise allows it). Root's native browser R3 PASS is authoritative.
 proto.focus=function(...args){if(this.disabled)return;return focus.apply(this,args);};try{discard.focus();await discard.onclick();}finally{if(own)proto.focus=focus;else delete proto.focus;}
 const state=editor.port.snapshot();assert.equal(state.draft,null);assert.equal(state.selection.id,selected);assert.equal(calls.length,before);
 assert.equal(document.activeElement?.dataset?.workflowView,'design');
}finally{view.close();}});
test('release route R4: Use as new draft is offered only for a verified saved selection without local edits',async()=>{const view=await releaseEditor();try{const {editor,host}=view,adapt=()=>host.querySelector('[data-control="workflow:adapt"]'),offered=!!(sample.listing.creation_choices_read&&sample.listing.actions?.create?.permitted);
 assert.equal(!!adapt(),offered,'availability follows the owner creation offer');
 await editor.port.dispatch({type:'edit',edit:{type:'fields',fields:{title:'Unsaved Ω change'}}});assert.equal(adapt(),null,'unsaved edits are never silently copied');
}finally{view.close();}});
test('release route R1: a reusable workspace design explains Runs without a project-only read',async()=>{const selected={...copy(sample.selected),scope:{kind:'owned-workspace'},app_runs_read:null},view=await releaseEditor({selected});try{const {host,calls}=view,before=calls.length;
 host.querySelector('[data-workflow-view="runs"]').onclick();await releaseTick();
 assert.equal(calls.slice(before).some(row=>String(row.url).includes('app-runs')),false);assert.ok(host.textContent.includes('reusable workspace design is not run directly'));assert.equal(host.textContent.includes('APP_RUN_NOT_IN_SCOPE'),false);
}finally{view.close();}});
test('release route R1: a Runs read error stays with Runs and does not follow Guide or Design',async()=>{assert.ok(sample.selected.app_runs_read,'fixture carries a project Runs read');const view=await releaseEditor({fail:'APP_RUN_NOT_IN_SCOPE'});try{const {host}=view;
 host.querySelector('[data-workflow-view="runs"]').onclick();await releaseTick();assert.ok(host.textContent.includes('APP_RUN_NOT_IN_SCOPE'));
 host.querySelector('[data-workflow-view="guide"]').onclick();assert.equal(host.textContent.includes('APP_RUN_NOT_IN_SCOPE'),false);
 host.querySelector('[data-workflow-view="design"]').onclick();assert.equal(host.textContent.includes('APP_RUN_NOT_IN_SCOPE'),false);
}finally{view.close();}});
test('release route R4: an unqualified saved identity, version or ownership never offers Use as new draft',async()=>{
 for(const variant of ['foreign-reference','missing-reference-version','missing-scope']){const selected=copy(sample.selected);if(variant==='foreign-reference')selected.reference.identity.id='WDEF-foreign';if(variant==='missing-reference-version')delete selected.reference.version;if(variant==='missing-scope')delete selected.scope;
  const listing={...copy(sample.listing),creation_choices_read:{request:{facet:'creation-choices'},http:{method:'GET',url:'/work/workflow-definitions?facet=creation-choices'}}},view=await releaseEditor({selected,listing});
  try{assert.equal(view.host.querySelector('[data-control="workflow:adapt"]'),null,variant);}finally{view.close();}}
});
test('release route R1: a late Runs rejection after Guide is not published as a current error',async()=>{let refuse;const view=await releaseEditor({late:reject=>{refuse=reject;}});try{const {host,calls}=view;
 host.querySelector('[data-workflow-view="runs"]').onclick();assert.ok(refuse,'the Runs read is pending');host.querySelector('[data-workflow-view="guide"]').onclick();refuse(Error('APP_RUN_NOT_IN_SCOPE late read'));await releaseTick();
 assert.ok(host.querySelector('.workflow-guide'));assert.equal(host.textContent.includes('APP_RUN_NOT_IN_SCOPE'),false);assert.equal(calls.some(row=>row.payload!==undefined),false);
}finally{view.close();}});
test('release route R2: discarding a local draft closes its unadmitted preparation form on fallback',async()=>{const view=await releaseEditor();try{const {editor,host}=view,find=label=>[...host.querySelectorAll('button')].find(node=>node.textContent===label);
 await editor.port.dispatch({type:'create',definition:copy(sample.selected.definition)});find('Prepare external run…').onclick();assert.ok(find('Close preparation'),'local preparation form open');
 await find('Discard unsaved edits').onclick();const state=editor.port.snapshot();assert.equal(String(state.selection?.id||'').startsWith('local:'),false);assert.equal(find('Close preparation'),undefined,'fallback subject does not inherit the local preparation form');
}finally{view.close();}});
test('release route R5: a nested research run identity is accepted exactly; missing, colliding and foreign identities refuse',async()=>{const {createWorkflowRunPort}=await import('../src/laplace/web/static_shared/workflow-port.mjs');
 const reference={schema_version:'laplace.reference/1',owner:'pipeline.workflow',kind:'workflow-definition',identity:{id:'WDEF-public'},version:{definition_revision:'sha256:'+'1'.repeat(64)}},read=url=>({http:{method:'GET',url}});
 const definition={definition_id:'WDEF-public',scope_id:'scope-public',reference,read:read('/work/workflow-definitions?definition_id=WDEF-public'),app_runs_read:read('/work/workflow-definitions?definition_id=WDEF-public&facet=app-runs'),scope:{kind:'project',namespace:'book'}};
 const base={profile:'laplace.app-dispatch/1',reference,definition_read:read('/work/workflow-definitions?definition_id=WDEF-public&version=public')},research=extra=>({...base,schema_version:'laplace.research-workflow-run/1',work:{id:'WORK-public',project:'book'},...extra});
 for(const [value,ok] of [[research(),true],[research({work_id:'WORK-public'}),true],[{...base,work_id:'WORK-public',work:{project:'book'}},true],[research({work_id:'WORK-other'}),false],[research({work:{id:'WORK-other',project:'book'}}),false],[research({work:{id:'WORK-public',project:'foreign'}}),false],[research({work:{project:'book'}}),false]]){
  const port=createWorkflowRunPort({request:async url=>String(url).includes('facet=app-run&')?copy(value):{definition_id:'WDEF-public',scope_id:'scope-public',reference,definition:{steps:[]}}});
  const opened=port.open(definition,'run',read('/work/workflow-definitions?definition_id=WDEF-public&facet=app-run&work_id=WORK-public'),{work_id:'WORK-public'});
  if(ok)assert.equal((await opened).reference.identity.id,'WDEF-public');else await assert.rejects(opened,/Work/);port.destroy();}
});
const button=(host,label)=>[...host.querySelectorAll('button')].find(node=>node.textContent===label);

test('Design/Runs/Guide reuses exact saved selection and native draft; observation is explicit and local discard never cancels a request',async()=>{
 const env=installHTMLDocument({width:390}),calls=[],records=new Map();let editor;
 try{const host=document.createElement('main');document.body.append(host);editor=await mountWorkflowEditor(host,{storage:{getItem:key=>records.get(key)??null,setItem:(key,value)=>records.set(key,value),removeItem:key=>records.delete(key)},initialReference:sample.selected.reference,initialRead:sample.listing.definitions[0].read,request:async(url,payload)=>{calls.push({url,payload});assert.equal(payload,undefined);if(url==='/work/workflow-definitions')return copy(sample.listing);if(url===sample.selected.app_runs_read.http.url)return {profile:'laplace.app-dispatch/1',reference:copy(sample.selected.reference),items:[]};return copy(sample.selected);}});
 const title=host.querySelector('[data-field="Workflow title"]');title.value='Retained design Ω';title.oninput();const before=editor.port.capture(),reads=calls.length;
 await button(host,'Guide').onclick();assert.ok(host.querySelector('.workflow-guide'));assert.equal(calls.length,reads);assert.deepEqual(editor.port.capture(),before);assert.match(host.querySelector('.workflow-guide').textContent,/not spawn a delegated subworkflow/);
 await button(host,'Runs').onclick();await Promise.resolve();await Promise.resolve();assert.equal(calls.length,reads+1);assert.equal(calls.at(-1).url,sample.selected.app_runs_read.http.url);assert.match(host.textContent,/No agent run is recorded/);assert.deepEqual(editor.port.capture(),before);
 await button(host,'Design').onclick();assert.equal(host.querySelector('[data-field="Workflow title"]').value,'Retained design Ω');assert.deepEqual(editor.port.capture(),before);const discard=button(host,'Discard unsaved edits');assert.ok(discard);assert.match(discard.title,/pending requests and runs are not cancelled/);await discard.onclick();assert.equal(editor.port.snapshot().draft,null);assert.equal(calls.length,reads+1,'view and local draft decisions issue no effects');assert.equal(editor.runPort.snapshot().read.value.items.length,0);
 }finally{editor?.destroy();env.restore();}
});

test('chat has separate navigation, attached-reading and future-message choices with the original native composer retained',async()=>{
 const {mountShell}=await import('./helpers/shell_fixture.mjs'),s=await mountShell();try{
 await s.root.querySelector('[data-talk]').onclick();const host=s.root.querySelector('[data-session]'),options=host.querySelector('[data-session-options]'),message=host.querySelector('[data-message]');message.value='Unsent author Ω';message.dispatchEvent({type:'input'});
 assert.equal(host.querySelector('[data-browse]').closest('.session-header-actions')!==null,true);assert.equal(host.querySelector('[data-browse]').closest('[data-session-options]'),null);
 for(const selector of ['[data-context-open]','[data-add-local-document]','[data-use-reading]','[data-message-target]'])assert.ok(host.querySelector(selector).closest('.session-message-destination'));
 assert.ok(host.querySelector('[data-mode]').closest('.session-next-decision'));assert.ok(host.querySelector('[data-settings-open]').closest('.session-next-decision'));assert.equal(host.querySelector('[data-mode]').closest('[data-session-options]'),null);assert.equal(!!options.open,false);
 const before=s.calls.length;await host.querySelector('[data-context-open]').onclick();assert.equal(host.querySelector('[data-inspector-title]').textContent,'Context');await host.querySelector('[data-inspector-close]').onclick();assert.equal(document.activeElement,host.querySelector('[data-context-open]'));assert.equal(host.querySelector('[data-message]'),message);assert.equal(message.value,'Unsent author Ω');assert.equal(s.calls.length,before,'context presentation does not Send or refetch a body');assert.ok(host.querySelector('[data-refresh-turn]').closest('.session-execution-summary'));assert.ok(host.querySelector('[data-stop]').closest('.session-execution-summary'));assert.match(host.querySelector('[data-stop]').title,/not a workflow-wide stop/);assert.ok(s.calls.every(call=>call.startsWith('GET ')));
 }finally{s.restore();}
});

test('pending, admitted, withdrawal and future-choice language never invents settlement or undoes effects',()=>{
 assert.match(conversationOperationPresentation({submission:{payload:{request_id:'original'}}}),/original message and settings.*does not resend/);
 assert.match(conversationOperationPresentation({controlPending:{id:'input'}}),/Delivery still needs observation/);
 assert.match(conversationOperationPresentation({stopRequested:true,active:'turn'}),/Completion is not yet confirmed.*not undone/);
 assert.match(conversationOperationPresentation({active:'turn'}),/last owner observation.*separate from future/);
 assert.equal(conversationOperationPresentation({}), '');
});

test('empty progression is honest and local discard keeps an uncertain owner wire unchanged',async()=>{
 const env=installHTMLDocument({width:390});let editor;try{const host=document.createElement('main');document.body.append(host);const empty=copy(sample.listing);empty.definitions=[];empty.total=0;editor=await mountWorkflowEditor(host,{storage:{getItem:()=>null,setItem(){},removeItem(){}},request:async(_url,payload)=>{assert.equal(payload,undefined);return empty;}});assert.equal(editor.port.snapshot().selection,null);assert.ok(button(host,'Design'));assert.ok(button(host,'Runs'));assert.ok(button(host,'Guide'));await button(host,'Runs').onclick();assert.match(host.textContent,/does not mean there is no other project activity/);await button(host,'Guide').onclick();assert.match(host.textContent,/Saving does not start work/);await button(host,'Design').onclick();assert.equal(editor.port.snapshot().selection,null);
 editor.destroy();const prior={schema:'laplace.workflow-drafts/1',scope_id:sample.selected.scope_id,drafts:[{id:sample.selected.definition_id,definition:{...copy(sample.selected.definition),title:'Unsent Ω'},basis:copy(sample.selected.actions.save),read:copy(sample.selected.read)}],attempts:[{id:sample.selected.definition_id,operation:'save',request_id:'exact-original',status:'uncertain',payload:{definition:{...copy(sample.selected.definition),title:'Original submitted'},request_id:'exact-original',expected_revision:sample.selected.version}}],contexts:[],selection:{id:sample.selected.definition_id,read:copy(sample.selected.read)}};
 editor=await mountWorkflowEditor(host,{storage:{getItem:()=>JSON.stringify(prior),setItem(){},removeItem(){}},request:async(url,payload)=>{assert.equal(payload,undefined);return url==='/work/workflow-definitions'?copy(sample.listing):copy(sample.selected);}});const wire=copy(editor.port.snapshot().attempt);assert.equal(button(host,'Save definition').disabled,true);await button(host,'Discard unsaved edits').onclick();assert.deepEqual(editor.port.snapshot().attempt,wire);assert.equal(editor.port.snapshot().draft,null);assert.equal(editor.port.snapshot().has_unresolved,true,'discard is not durable withdrawal or receipt settlement');
 }finally{editor?.destroy();env.restore();}
});

const operationSample=JSON.parse(readFileSync(new URL('./fixtures/workflow_operation/public-owner.json',import.meta.url)));
test('actual admitted creation rows require explicit project/template choice and keep custody in the original owner action',async()=>{
 const env=installHTMLDocument({width:390}),s=operationSample,calls=[];let editor;try{const host=document.createElement('main');document.body.append(host);
 // Only the library envelope is a controlled wrapper. The choice page and
 // per-row create handles are literal B interface002 owner output.
 const listing={scope_id:s.creation_choices.scope_id,scope:s.creation_choices.caller_scope,definitions:[],actions:{create:s.creation_choices.items[0].create},creation_choices_read:{request:{facet:'creation-choices'},http:{method:'GET',url:'/work/workflow-definitions?facet=creation-choices'}}};
 editor=await mountWorkflowEditor(host,{storage:{getItem:()=>null,setItem(){},removeItem(){}},request:async(url,payload)=>{calls.push({url,payload});assert.equal(payload,undefined);return copy(url==='/work/workflow-definitions'?listing:s.creation_choices);}});await button(host,'New workflow').onclick();assert.equal(editor.port.snapshot().selection,null,'opening ownership choices is not creation or save');assert.equal(calls.length,2);const choice=host.querySelector('[data-creation-choice]');assert.equal(choice.value,'');await assert.rejects(editor.port.dispatch({type:'create'}),/Choose an offered/);choice.value='1';choice.onchange();const form=host.querySelector('.workflow-creation-choice');await form.onsubmit({preventDefault(){}});const state=editor.port.snapshot();assert.match(state.selection.id,/^local:/);assert.deepEqual(state.draft.basis,s.creation_choices.items[1].create);assert.match(host.querySelector('.workflow-eyebrow').textContent,/Project workflow/);assert.equal(calls.length,2,'explicit ownership creates only a draft, no POST');
 }finally{editor?.destroy();env.restore();}
});

test('pure preview binds exact posted bytes and current design, without pretending Python and JS semantic hashes are equal',async()=>{
 const {readWorkflowOperation,workflowOperationRequest}=await import('../src/laplace/web/static_shared/workspace-workflow-operation.mjs'),{feedbackWireDigest}=await import('../src/laplace/web/static_shared/feedback-route-port.mjs'),s=operationSample,inputs={definition:copy(s.preview_request.definition),scope:copy(s.preview_request.scope),step_ids:copy(s.preview_request.step_ids)},offer=s.preview_offer;
 const before=copy(s.preview),calls=[];const request=async(url,payload)=>{calls.push({url,payload:copy(payload)});return {...copy(s.preview),transport_request:{encoding:'utf8-exact-request-body',sha256:await feedbackWireDigest(JSON.stringify(payload))}};};const value=await readWorkflowOperation(offer,inputs,{request,expected:{scope_id:s.preview.scope_id}});assert.equal(value.support,'SUPPORTED_CONFIGURATION');assert.deepEqual(calls[0].payload,s.preview_request);assert.equal(calls[0].url,'/work/workflow-definitions');assert.deepEqual(s.preview,before);
 for(const kind of ['wrong-wire','wrong-scope','wrong-slice'])await assert.rejects(readWorkflowOperation(offer,inputs,{expected:{scope_id:s.preview.scope_id},request:async(url,payload)=>{const value=await request(url,payload);if(kind==='wrong-wire')value.transport_request.sha256='sha256:'+'0'.repeat(64);if(kind==='wrong-scope')value.scope.namespace='foreign';if(kind==='wrong-slice')value.selected_step_ids.reverse();return value;}}));
 assert.throws(()=>workflowOperationRequest(offer,{...inputs,request_id:'not-a-read-field'}));let current=false,requested=0;assert.equal(await readWorkflowOperation(offer,inputs,{request:()=>requested++,isCurrent:()=>current}),null);assert.equal(requested,0);
 let release;current=true;const pending=readWorkflowOperation(offer,inputs,{request:async(...args)=>{const value=await request(...args);return new Promise(resolve=>release=()=>resolve(value));},isCurrent:()=>current});while(!release)await new Promise(resolve=>setImmediate(resolve));current=false;release();assert.equal(await pending,null,'late response cannot repaint another design');
});

test('mounted pure execution check reads one declared role context lazily and becomes old after local typing',async()=>{
 const env=installHTMLDocument({width:390}),s=operationSample,calls=[];let editor;try{const {feedbackWireDigest}=await import('../src/laplace/web/static_shared/feedback-route-port.mjs'),host=document.createElement('main');document.body.append(host);const listing={scope_id:s.preview.scope_id,scope:s.preview.caller_scope,definitions:[],actions:{create:s.creation_choices.items[0].create},execution_preview:s.preview_offer};
 editor=await mountWorkflowEditor(host,{storage:{getItem:()=>null,setItem(){},removeItem(){}},request:async(url,payload)=>{calls.push({url,payload:copy(payload)});if(!payload)return copy(listing);assert.equal(url,'/work/workflow-definitions');const value=payload.facet==='execution-preview'?s.preview:s.role_context;return {...copy(value),transport_request:{encoding:'utf8-exact-request-body',sha256:await feedbackWireDigest(JSON.stringify(payload))}};}});await editor.port.dispatch({type:'create',definition:copy(s.preview_request.definition)});await editor.port.dispatch({type:'edit',edit:{type:'fields',fields:{}}});
 // This controlled wrapper uses workspace-owned creation; bind the preview
 // request's actual project custody through the literal admitted choice basis.
 const held=editor.port.capture();held.drafts[0].basis=copy(s.creation_choices.items[1].create);editor.destroy();const saved=JSON.stringify(held),records=new Map([['laplace:workflow-drafts:'+held.scope_id,saved]]);editor=await mountWorkflowEditor(host,{storage:{getItem:key=>records.get(key)||null,setItem:(key,value)=>records.set(key,value),removeItem:key=>records.delete(key)},request:async(url,payload)=>{calls.push({url,payload:copy(payload)});if(!payload)return copy(listing);const value=payload.facet==='execution-preview'?s.preview:s.role_context;return {...copy(value),transport_request:{encoding:'utf8-exact-request-body',sha256:await feedbackWireDigest(JSON.stringify(payload))}};}});
 const before=editor.port.capture(),initial=calls.filter(row=>row.payload).length;const check=button(host,'Check execution');check.focus();await check.onclick();assert.equal(calls.filter(row=>row.payload).length,initial+1);assert.match(host.querySelector('.workflow-execution-check').textContent,/owner supports this configuration/);assert.equal(calls.filter(row=>row.payload?.facet==='context').length,0);await button(host,'Inspect declared context').onclick();assert.equal(calls.filter(row=>row.payload?.facet==='context').length,1);assert.match(host.querySelector('.workflow-context-reading').textContent,/Produce a public report/);assert.deepEqual(editor.port.capture().drafts,before.drafts);assert.deepEqual(editor.port.capture().attempts,before.attempts);
 const title=host.querySelector('[data-field="Workflow title"]');title.value='Newer checked-later Ω';title.oninput();assert.match(host.querySelector('.workflow-execution-check').textContent,/design changed/);assert.equal(button(host,'Inspect declared context').disabled,true);const n=calls.length;await button(host,'Inspect declared context').onclick();assert.equal(calls.length,n,'old context cannot dispatch after a new draft intent');assert.equal(editor.port.snapshot().draft.definition.title,'Newer checked-later Ω');
 }finally{editor?.destroy();env.restore();}
});

test('owner-computed withdrawal uses the original decimal wire, retains later edits, and UNKNOWN never becomes cancellation',async()=>{
 const {createWorkflowPort}=await import('../src/laplace/web/static_shared/workflow-port.mjs'),{feedbackWireDigest}=await import('../src/laplace/web/static_shared/feedback-route-port.mjs'),s=operationSample;
 for(const outcome of ['withdrawn','unknown']){const original=copy(s.withdrawal_preview_request.original_request),scope=s.withdrawal_prepared.scope,offer=s.creation_choices.items[0].create.withdrawal,key='local:public-withdraw',calls=[],initial={schema:'laplace.workflow-drafts/1',scope_id:s.withdrawal_prepared.scope_id,selection:{id:key},drafts:[{id:key,definition:{...copy(original.definition),title:'Newer unsent Ω'},basis:copy(s.creation_choices.items[0].create)}],attempts:[{id:key,operation:'save',request_id:original.request_id,status:'uncertain',payload:copy(original),scope:copy(scope),withdrawal_offer:copy(offer)}],contexts:[]};
 const port=createWorkflowPort({initial,initialListing:{scope_id:initial.scope_id,scope,actions:{create:s.creation_choices.items[0].create}},request:async(url,payload)=>{calls.push({url,payload:copy(payload)});if(url==='/work/workflow-definitions'){assert.deepEqual(payload.original_request,original);return {...copy(s.withdrawal_prepared),transport_request:{encoding:'utf8-exact-request-body',sha256:await feedbackWireDigest(JSON.stringify(payload))}};}assert.equal(url,'/work/workflow-definitions/withdraw');assert.deepEqual(payload.original_request,original);assert.equal(payload.intent_digest,s.withdrawal_prepared.intent_digest);return outcome==='unknown'?{status:'UNKNOWN',effect:'UNKNOWN',terminal:false,request_id:original.request_id}:{schema_version:'laplace.workflow-request-decision/1',status:'NOT_ADMITTED',effect:'NOT_ADMITTED',terminal:true,reason:'WITHDRAWN',request_id:original.request_id,operation:'save',intent_digest:s.withdrawal_prepared.intent_digest,scope:copy(scope),scope_id:initial.scope_id};}});
 try{const before=port.capture();await port.dispatch({type:'withdraw'});assert.equal(calls.length,2,'one pure owner digest read followed by one explicit withdrawal');assert.deepEqual(port.capture().drafts,before.drafts);assert.deepEqual(port.snapshot().attempt.payload,original);assert.equal(port.snapshot().attempt.status,outcome==='withdrawn'?'withdrawn':'uncertain');if(outcome==='unknown'){await assert.rejects(port.dispatch({type:'resolve-attempt'}),/exact original request/);assert.equal(port.snapshot().has_unresolved,true);}else{assert.equal(port.snapshot().attempt.result.effect,'NOT_ADMITTED');assert.equal(port.snapshot().draft.definition.title,'Newer unsent Ω');}}
 finally{port.destroy();}}
});

test('late original Save UNKNOWN/failure cannot revoke terminal withdrawal or overwrite a newer request after acknowledgement',async()=>{
 const {createWorkflowPort}=await import('../src/laplace/web/static_shared/workflow-port.mjs'),{feedbackWireDigest}=await import('../src/laplace/web/static_shared/feedback-route-port.mjs'),s=operationSample,descriptor=Object.getOwnPropertyDescriptor(globalThis,'crypto'),realCrypto=globalThis.crypto;
 for(const acknowledge of [false,true])for(const failure of [false,true]){const original=copy(s.withdrawal_preview_request.original_request),key='local:race',scope=copy(s.withdrawal_prepared.scope),action={...copy(s.creation_choices.items[0].create),payload:{expected_revision:null}},initial={schema:'laplace.workflow-drafts/1',scope_id:s.withdrawal_prepared.scope_id,selection:{id:key},drafts:[{id:key,definition:copy(original.definition),basis:action}],attempts:[],contexts:[]};let n=0,releaseOld,rejectOld,releaseNew;Object.defineProperty(globalThis,'crypto',{configurable:true,value:{subtle:realCrypto.subtle,randomUUID:()=>n++===0?original.request_id:'new-original-request'}});const terminal={schema_version:'laplace.workflow-request-decision/1',status:'NOT_ADMITTED',effect:'NOT_ADMITTED',terminal:true,reason:'WITHDRAWN',request_id:original.request_id,operation:'save',intent_digest:s.withdrawal_prepared.intent_digest,scope,scope_id:initial.scope_id},calls=[];
 const port=createWorkflowPort({initial,initialListing:{scope_id:initial.scope_id,scope,actions:{create:action}},request:async(url,payload)=>{calls.push({url,payload:copy(payload)});if(url.endsWith('/save'))return new Promise((resolve,reject)=>{if(payload.request_id===original.request_id){releaseOld=resolve;rejectOld=reject;}else releaseNew=resolve;});if(url==='/work/workflow-definitions')return {...copy(s.withdrawal_prepared),transport_request:{encoding:'utf8-exact-request-body',sha256:await feedbackWireDigest(JSON.stringify(payload))}};assert.equal(url,'/work/workflow-definitions/withdraw');return copy(terminal);}});
 try{const first=port.dispatch({type:'save'});assert.ok(releaseOld);await port.dispatch({type:'edit',edit:{type:'fields',fields:{title:'Newer draft Ω'}}});await port.dispatch({type:'withdraw'});assert.equal(port.snapshot().attempt.status,'withdrawn');let second=null;if(acknowledge){await port.dispatch({type:'resolve-attempt'});second=port.dispatch({type:'save'});assert.ok(releaseNew);assert.equal(port.snapshot().attempt.request_id,'new-original-request');}const kept=copy(port.snapshot().attempt);if(failure)rejectOld(Error('OLD_CONNECTION_FAILURE'));else releaseOld({status:'UNKNOWN',effect:'unknown'});await first;assert.deepEqual(port.snapshot().attempt,kept);assert.equal(port.snapshot().draft.definition.title,'Newer draft Ω');if(second){releaseNew({status:'UNKNOWN',effect:'unknown'});await second;}assert.equal(calls.filter(row=>row.url.endsWith('/save')).length,acknowledge?2:1,'no implicit original replay');}
 finally{port.destroy();Object.defineProperty(globalThis,'crypto',descriptor);}}
});

test('late original request inspection UNKNOWN/failure cannot replace a newer terminal withdrawal',async()=>{
 const {createWorkflowPort}=await import('../src/laplace/web/static_shared/workflow-port.mjs'),{feedbackWireDigest}=await import('../src/laplace/web/static_shared/feedback-route-port.mjs'),s=operationSample;
 for(const failure of [false,true]){const original=copy(s.withdrawal_preview_request.original_request),key='local:inspect-race',scope=copy(s.withdrawal_prepared.scope),initial={schema:'laplace.workflow-drafts/1',scope_id:s.withdrawal_prepared.scope_id,selection:{id:key},drafts:[{id:key,definition:{...copy(original.definition),title:'Retain newer Ω'},basis:copy(s.creation_choices.items[0].create)}],attempts:[{id:key,operation:'save',request_id:original.request_id,status:'uncertain',payload:copy(original),scope,withdrawal_offer:copy(s.creation_choices.items[0].create.withdrawal)}],contexts:[]};let release,reject;
 const terminal={schema_version:'laplace.workflow-request-decision/1',status:'NOT_ADMITTED',effect:'NOT_ADMITTED',terminal:true,reason:'WITHDRAWN',request_id:original.request_id,operation:'save',intent_digest:s.withdrawal_prepared.intent_digest,scope,scope_id:initial.scope_id},port=createWorkflowPort({initial,initialListing:{scope_id:initial.scope_id,scope,actions:{inspect_request:{http:{method:'GET',url:'/work/workflow-definitions?facet=request'}}}},request:async(url,payload)=>{if(!payload)return new Promise((a,b)=>{release=a;reject=b;});if(url==='/work/workflow-definitions')return {...copy(s.withdrawal_prepared),transport_request:{encoding:'utf8-exact-request-body',sha256:await feedbackWireDigest(JSON.stringify(payload))}};return copy(terminal);}});
 try{const pending=port.dispatch({type:'recover'});assert.ok(release);await port.dispatch({type:'withdraw'});const kept=copy(port.snapshot().attempt);if(failure)reject(Error('OLD_RECOVERY_FAILURE'));else release({status:'NOT_RECORDED',effect:'unknown'});await pending;assert.deepEqual(port.snapshot().attempt,kept);assert.equal(port.snapshot().draft.definition.title,'Retain newer Ω');}
 finally{port.destroy();}}
});

test('mounted offered withdrawal preserves the later draft and qualifies current result focus without defeating later author intent',async()=>{
 const {feedbackWireDigest}=await import('../src/laplace/web/static_shared/feedback-route-port.mjs'),s=operationSample;
 for(const later of [false,true]){const env=installHTMLDocument({width:390}),original=copy(s.withdrawal_preview_request.original_request),key='local:mounted-withdraw',scope=copy(s.withdrawal_prepared.scope),initial={schema:'laplace.workflow-drafts/1',scope_id:s.withdrawal_prepared.scope_id,selection:{id:key},drafts:[{id:key,definition:{...copy(original.definition),title:'Later local draft Ω'},basis:copy(s.creation_choices.items[0].create)}],attempts:[{id:key,operation:'save',request_id:original.request_id,status:'uncertain',payload:copy(original),scope,withdrawal_offer:copy(s.creation_choices.items[0].create.withdrawal)}],contexts:[]},records=new Map([['laplace:workflow-drafts:'+initial.scope_id,JSON.stringify(initial)]]);let editor,release,effectReached;const effectReady=new Promise(resolve=>effectReached=resolve);
 try{const host=document.createElement('main');document.body.append(host);editor=await mountWorkflowEditor(host,{storage:{getItem:key=>records.get(key)||null,setItem:(key,value)=>records.set(key,value),removeItem:key=>records.delete(key)},request:async(url,payload)=>{if(!payload)return {scope_id:initial.scope_id,scope,definitions:[],actions:{create:s.creation_choices.items[0].create}};if(url==='/work/workflow-definitions')return {...copy(s.withdrawal_prepared),transport_request:{encoding:'utf8-exact-request-body',sha256:await feedbackWireDigest(JSON.stringify(payload))}};assert.equal(url,'/work/workflow-definitions/withdraw');effectReached(true);return new Promise(resolve=>release=()=>resolve({schema_version:'laplace.workflow-request-decision/1',status:'NOT_ADMITTED',effect:'NOT_ADMITTED',terminal:true,reason:'WITHDRAWN',request_id:original.request_id,operation:'save',intent_digest:s.withdrawal_prepared.intent_digest,scope,scope_id:initial.scope_id}));}});
 const opener=button(host,'Withdraw original request');assert.equal(opener.dataset.control,'workflow:withdraw');opener.focus();const pending=opener.onclick();const reached=await Promise.race([effectReady,pending.then(()=>false)]);assert.equal(reached,true,editor.port.snapshot().attempt?.withdrawal_error||'withdrawal effect was not reached');assert.equal(typeof release,'function');document.body.focus();let title=null;if(later){title=host.querySelector('[data-field="Workflow title"]');title.focus();document.dispatchEvent({type:'focusin',target:title});title.value='Latest author Ω';title.oninput();}release();await pending;assert.equal(editor.port.snapshot().attempt.status,'withdrawn');assert.match(host.textContent,/owner confirms this original request was not admitted/);assert.equal(editor.port.snapshot().draft.definition.title,later?'Latest author Ω':'Later local draft Ω');if(later){assert.equal(document.activeElement===host.querySelector('[data-field="Workflow title"]'),true,'later author intent returns to the currently rendered title field');assert.equal(document.activeElement.value,'Latest author Ω');}else assert.equal(document.activeElement.dataset.workflowAttempt,original.request_id);assert.equal(button(host,'Withdraw original request'),undefined);
 }finally{editor?.destroy();env.restore();}}
});

// Focused joins added with the native Design/Runs/Guide slice. Fixture rows are
// literal fe80 owner output unless a line names a controlled wrapper.
test('role presentation explains the actual preview: location, connections and an authored declaration the owner did not echo',async()=>{
 const {workflowRolePresentation,workflowConfiguredFlow}=await import('../src/laplace/web/static_shared/workspace-workflow-operation.mjs'),s=operationSample,body=copy(s.preview_request.definition);
 const write=workflowRolePresentation(s.preview.roles[0],body),review=workflowRolePresentation(s.preview.roles[1],body);
 assert.equal(write.name,'Write');assert.match(write.location,/admitted child/);assert.deepEqual(write.sends,[{to:'Review',kind:'control'}]);assert.equal(write.consumed,'none-authored');
 assert.deepEqual(review.receives,[{from:'Write',kind:'control'}]);assert.match(review.review,/not blind review/);assert.equal(review.original_parent,false);
 body.steps[1].assignment.context=[{kind:'upstream-return',step_id:'write'}];assert.equal(workflowRolePresentation(s.preview.roles[1],body).consumed,'not-echoed','an authored choice the owner did not return is never presented as consumed');
 const shown=workflowRolePresentation({...copy(s.preview.roles[1]),context:[{kind:'upstream-return',step_id:'write'}]},body);assert.equal(shown.consumed,'echoed');assert.deepEqual(shown.context.map(row=>row.from),['Write']);
 const parent=workflowRolePresentation({...copy(s.preview.roles[1]),execution_location:'original-parent'},body);assert.equal(parent.original_parent,true);assert.match(parent.location,/original parent conversation.*admitted model/);
 assert.deepEqual(workflowConfiguredFlow(body).map(row=>[row.from,row.to,row.state]),[['Write','Review','planned']]);assert.deepEqual(s.preview.roles[1].context,[],'fixture unchanged');
});

test('context, handoff and policy choices derive from owner declarations; policy placement stays unwritten',async()=>{
 const {workflowContextChoices,workflowHandoffFields,workflowPolicyBounds,workflowPolicyText,workflowPolicyVariant}=await import('../src/laplace/web/static_shared/workspace-workflow-operation.mjs'),d=operationSample.preview.declarations;
 const choices=workflowContextChoices(d);assert.deepEqual(choices.rows.map(row=>[row.kind,row.needs_step]),[['ancestor-instructions',true],['upstream-return',true],['selected-evidence',false],['previous-review-findings',false],['parent-message',false]]);assert.equal(choices.max,24);
 assert.deepEqual(workflowHandoffFields(d),{purpose:{max:2000},expected_output:{max:4000},downstream:{max:64}});
 const legacy=workflowPolicyBounds(d);assert.equal(legacy.variants.length,1);assert.deepEqual(legacy.variants[0].iterations,{min:1,max:3});assert.deepEqual(legacy.variants[0].runtime_seconds,{min:1,max:3600});assert.deepEqual(legacy.variants[0].advance,['automatic-review','manual']);assert.equal(legacy.variants[0].apply,'human');
 // Actual immutable owner helper declaration (oneOf legacy/v2) relayed by A in ART-f4739aad77b04a3eba5cdeb3a255e835 (actual-owner-run-policy e9f9e681).
 const base={type:'object',additionalProperties:false},common={runtime_seconds:{type:'integer',minimum:1,maximum:3600},advance:{enum:['automatic-review','manual']},apply:{const:'human'}},actual={run_policy:{oneOf:[{...base,required:['profile','max_iterations','runtime_seconds','advance','apply'],properties:{profile:{const:'laplace.research-review/1'},max_iterations:{type:'integer',minimum:1,maximum:3},...common}},{...base,required:['profile','max_iterations','runtime_seconds','advance','apply','max_admissions','deadline_seconds','continuation_criteria','exit_criteria'],properties:{profile:{const:'laplace.research-review/2'},max_iterations:{type:'integer',minimum:1,maximum:9007199254740991},...common,max_admissions:{type:'integer',minimum:2,maximum:9007199254740991},deadline_seconds:{type:'integer',minimum:1,maximum:9007199254740991},continuation_criteria:{type:'string',minLength:1,maxLength:4000},exit_criteria:{type:'string',minLength:1,maxLength:4000}}}]}};
 const both=workflowPolicyBounds(actual);assert.deepEqual(both.variants.map(row=>row.profile),['laplace.research-review/1','laplace.research-review/2']);assert.deepEqual(both.variants[1].admissions,{min:2,max:9007199254740991});assert.deepEqual(both.variants[1].criteria,['continuation_criteria','exit_criteria']);assert.match(workflowPolicyText(both),/research-review\/1: review rounds 1–3.*research-review\/2: review rounds 1 or more, within your own limit/);assert.equal(workflowPolicyVariant(actual,'laplace.research-review/2').properties.exit_criteria.maxLength,4000);assert.equal(workflowPolicyVariant(actual,'laplace.other/1'),null,'no limit for an undeclared profile');
 assert.equal(workflowContextChoices(null),null);assert.equal(workflowPolicyBounds({}),null);
});

test('discard, exact withdrawal and run Stop stay distinct; Stop is not offered without an issued owner interface',async()=>{
 const {workflowInterventions}=await import('../src/laplace/web/static_shared/workspace-workflow-operation.mjs'),offer=operationSample.creation_choices.items[0].create.withdrawal,by=rows=>Object.fromEntries(rows.map(row=>[row.id,row]));
 let rows=by(workflowInterventions({}));assert.equal(rows.discard.available,false);assert.equal(rows.withdraw.available,false);assert.equal(rows.stop.available,false);assert.match(rows.stop.meaning,/carry no Stop.*Plan & run.*Open run detail.*own Stop ends only its current turn/);assert.equal(by(workflowInterventions({run:{schema_version:'laplace.app-dispatch/1',actions:{}}})).stop.available,false,'the app-dispatch run read carries no Stop');
 rows=by(workflowInterventions({draft:{id:'x'},attempt:{status:'uncertain',withdrawal_offer:offer}}));assert.equal(rows.discard.available,true);assert.match(rows.discard.meaning,/not cancelled/);assert.equal(rows.withdraw.available,true);assert.match(rows.withdraw.meaning,/exact original request/);
 assert.equal(by(workflowInterventions({attempt:{status:'uncertain',withdrawal_offer:offer,withdraw_status:'pending'}})).withdraw.available,false);
 assert.match(by(workflowInterventions({attempt:{status:'recorded'}})).withdraw.meaning,/cannot undo/);assert.match(by(workflowInterventions({attempt:{status:'withdrawn'}})).withdraw.meaning,/not admitted/);
 assert.equal(by(workflowInterventions({attempt:{status:'uncertain'}})).withdraw.available,false,'no owner offer means no withdrawal control');
});

test('selected observation reads nothing until asked, keeps one owner cut across pages and states missing coverage honestly',async()=>{
 const env=installHTMLDocument({width:390});try{const {mountWorkflowObservation,findWorkflowOperationOffer}=await import('../src/laplace/web/static_shared/workspace-workflow-operation.mjs'),scope_id=operationSample.preview.scope_id,cut='sha256:'+'a'.repeat(64);
 // Controlled wrapper: fe80 issued no uses sample, so this GET offer only uses the closed uses facet contract.
 const offer={read:{http:{method:'GET',url:'/work/workflow-definitions?facet=uses&definition_id=wdef-public'},request:{facet:'uses',definition_id:'wdef-public'},read_only:true}},owner={actions:{nested:{uses:offer}}},calls=[];assert.equal(findWorkflowOperationOffer(owner,'uses'),offer);assert.equal(findWorkflowOperationOffer(owner,'river'),null);
 const next={http:{method:'GET',url:'/work/workflow-definitions?facet=uses&definition_id=wdef-public&offset=1&as_of='+cut},read_only:true},page=fields=>({schema_version:'laplace.workflow-operation/1',view:'uses',read_only:true,scope_id,total:2,cut,returned:1,...fields});
 const pages=[page({items:[{title:'Prepared run',state:'PREPARED',recorded_at:'2026-10-30T00:00:00Z'}],offset:0,next_read:next}),page({items:[{title:'Admitted run',state:'RUNNING',from:{title:'Write'},to:{title:'Review'}}],offset:1,next_read:null})];
 const host=document.createElement('main');document.body.append(host);const ui=mountWorkflowObservation(host,{offer,facet:'uses',request:async(url,payload)=>{calls.push(url);assert.equal(payload,undefined);return copy(pages[calls.length-1]);},expected:{scope_id}});
 assert.equal(calls.length,0,'mounting is not reading');assert.match(host.textContent,/Nothing is read until you ask/);await button(host,'Read recorded uses').onclick();assert.equal(calls.length,1);assert.match(host.textContent,/1 of 2 recorded uses/);await button(host,'Read more').onclick();assert.equal(calls.length,2);assert.match(host.textContent,/2 of 2 recorded uses.*unknown, not absent/);assert.match(host.textContent,/Write → Review/);assert.equal(ui.value.items.length,2);
 pages.push({...copy(pages[0]),cut:'sha256:'+'b'.repeat(64)},{...copy(pages[1]),cut:'sha256:'+'c'.repeat(64)});await ui.load();await button(host,'Read more').onclick();assert.match(host.textContent,/pages were not mixed|changed while paging/);
 const empty=document.createElement('main');document.body.append(empty);const none=mountWorkflowObservation(empty,{offer,facet:'uses',request:async()=>({schema_version:'laplace.workflow-operation/1',view:'uses',read_only:true,scope_id,items:[],total:0,coverage:'NO_PROJECT_EXECUTION_BINDING'}),expected:{scope_id}});await none.load();assert.match(empty.textContent,/not proof that nothing happened/);
 }finally{env.restore();}
});

test('mounted role delivery authors only owner-declared choices and reports when the owner check did not consume them',async()=>{
 const env=installHTMLDocument({width:390}),s=operationSample,calls=[];let editor;try{const {feedbackWireDigest}=await import('../src/laplace/web/static_shared/feedback-route-port.mjs'),host=document.createElement('main');document.body.append(host);const listing={scope_id:s.preview.scope_id,scope:s.preview.caller_scope,definitions:[],actions:{create:s.creation_choices.items[0].create},execution_preview:s.preview_offer},records=new Map();
 const reply=async(url,payload)=>{calls.push({url,payload:copy(payload)});if(!payload)return copy(listing);const value=payload.facet==='execution-preview'?s.preview:s.role_context;return {...copy(value),transport_request:{encoding:'utf8-exact-request-body',sha256:await feedbackWireDigest(JSON.stringify(payload))}};};
 editor=await mountWorkflowEditor(host,{storage:{getItem:()=>null,setItem(){},removeItem(){}},request:reply});await editor.port.dispatch({type:'create',definition:copy(s.preview_request.definition)});await editor.port.dispatch({type:'edit',edit:{type:'fields',fields:{}}});
 // Controlled wrapper as above: bind the preview's actual project custody through the literal admitted choice basis.
 const held=editor.port.capture();held.drafts[0].basis=copy(s.creation_choices.items[1].create);editor.destroy();records.set('laplace:workflow-drafts:'+held.scope_id,JSON.stringify(held));
 editor=await mountWorkflowEditor(host,{storage:{getItem:key=>records.get(key)||null,setItem:(key,value)=>records.set(key,value),removeItem:key=>records.delete(key)},request:reply});
 await editor.port.dispatch({type:'step',id:'review'});assert.match(host.querySelector('[data-role-delivery="review"]').textContent,/Choose Check execution to load/);
 await button(host,'Check execution').onclick();let box=host.querySelector('[data-role-delivery="review"]');assert.ok(box.querySelector('[data-context-choice="upstream-return:write"]'),'upstream choices come from configured connections');assert.equal(box.querySelector('[data-context-choice^="ancestor-instructions"]'),null);assert.match(box.textContent,/no containing group/);
 const n=calls.length,choice=box.querySelector('[data-context-choice="upstream-return:write"]');choice.checked=true;choice.onchange();assert.deepEqual(editor.port.snapshot().draft.definition.steps[1].assignment.context,[{kind:'upstream-return',step_id:'write'}]);box=host.querySelector('[data-role-delivery="review"]');const expected=box.querySelector('[data-field="Expected output"]');expected.value='A judged report Ω';expected.oninput();assert.deepEqual(editor.port.snapshot().draft.definition.steps[1].assignment.handoff,{expected_output:'A judged report Ω'});assert.equal(calls.length,n,'authoring issues no owner request');
 await button(host,'Check execution').onclick();assert.match(host.querySelector('[data-preview-role="review"]').textContent,/not returned by the owner check/);assert.equal(host.querySelector('[data-preview-role="write"]').textContent.includes('not returned by the owner check'),false);assert.deepEqual(editor.port.snapshot().draft.definition.steps[1].assignment.context,[{kind:'upstream-return',step_id:'write'}],'an unconsumed choice stays in the draft');
 }finally{editor?.destroy();env.restore();}
});

test('Guide explains purpose, ownership, planned connections and the three interventions from the current selection without reads',async()=>{
 const env=installHTMLDocument({width:390}),calls=[];let editor;try{const host=document.createElement('main');document.body.append(host);editor=await mountWorkflowEditor(host,{storage:{getItem:()=>null,setItem(){},removeItem(){}},initialReference:sample.selected.reference,initialRead:sample.listing.definitions[0].read,request:async(url,payload)=>{calls.push(url);assert.equal(payload,undefined);return copy(url==='/work/workflow-definitions'?sample.listing:sample.selected);}});
 const before=calls.length,capture=editor.port.capture();await button(host,'Guide').onclick();const guide=host.querySelector('.workflow-guide');assert.equal(calls.length,before,'Guide reads nothing');
 assert.match(guide.textContent,/This workflow/);assert.match(guide.textContent,/Customise and finish/);assert.match(guide.textContent,/Check execution\. Repair any refusal; the check saves and starts nothing/);assert.match(guide.textContent,/Discard unsaved edits.*Withdraw original request.*Stop admitted run/);assert.match(guide.textContent,/Not offered for this run/);assert.match(guide.textContent,/original parent conversation/);assert.deepEqual(editor.port.capture(),capture);
 }finally{editor?.destroy();env.restore();}
});

test('next-message summary joins destination, reading, intent, settings and pending state without sending',async()=>{
 const {composerDecisionSummary}=await import('../src/laplace/web/static_shared/workspace-session.mjs');
 assert.equal(composerDecisionSummary({destination:'Follow-up in Draft review',reading:'Chapter 2',intent:'Work on a task'}),'Follow-up in Draft review · reading Chapter 2 · Work on a task. Model & settings apply to the next message only. Nothing is sent until you choose Send.');
 assert.match(composerDecisionSummary({pending:true,active:true}),/original text and settings.*later message/);assert.match(composerDecisionSummary({active:true}),/steering or queued input/);assert.match(composerDecisionSummary({active:true,stopRequested:true}),/not yet confirmed/);
 const {mountShell}=await import('./helpers/shell_fixture.mjs'),s=await mountShell();try{await s.root.querySelector('[data-talk]').onclick();const host=s.root.querySelector('[data-session]'),summary=host.querySelector('[data-next-summary]'),message=host.querySelector('[data-message]');assert.ok(summary.closest('.session-next-decision'));message.value='Unsent Ω';message.dispatchEvent({type:'input'});assert.match(summary.textContent,/Model & settings apply to the next message only/);assert.equal(message.value,'Unsent Ω');assert.ok(s.calls.every(call=>call.startsWith('GET ')));}finally{s.restore();}
});

test('Stop is offered only from an issued stop-run action and its composition never claims unobserved settlement',async()=>{
 const {workflowStopOffer,workflowStopPresentation,stopWorkflowRun,workflowInterventions}=await import('../src/laplace/web/static_shared/workspace-workflow-operation.mjs');
 // Source-derived shapes from owner interface ART-bf1d445453eb4628993561acbf6a8849 (c8e96dcb), NOT runtime-emitted owner output.
 // The run view follows B's corrected research DTO (ART-f4739aad77b04a3eba5cdeb3a255e835): work={id,project,title,revision}, revision, state.
 const runView=issued=>({schema_version:'laplace.research-workflow-run/1',work:{id:'WORK-public',project:'book',title:'Public run',revision:payload.expected_run_revision},revision:payload.expected_run_revision,state:'RUNNING',actions:{'stop-run':issued}});
 const payload={action:'workflow-stop-run',work_id:'WORK-public',request_id:'stop-request-0001',expected_run_revision:'sha256:'+'d'.repeat(64),children:['WD-child-1','WD-child-2']},offer={native:{operation:'work_delivery',payload:copy(payload)},http:{method:'POST',url:'/work/delivery',payload:{project:'book',...copy(payload)}},permitted:true,coverage:{owned_children:2,observed:2,complete:true}};
 assert.equal(workflowStopOffer({}),null);assert.equal(workflowStopOffer(runView({...copy(offer),native:{operation:'work_delivery',payload:{...copy(payload),children:[]}}})),null,'carriers must agree');
 const rows=Object.fromEntries(workflowInterventions({run:runView(offer)}).map(row=>[row.id,row]));assert.equal(rows.stop.available,true);assert.match(rows.stop.meaning,/each owned child/);assert.equal(Object.fromEntries(workflowInterventions({run:runView({native:copy(offer.native)})}).map(row=>[row.id,row])).stop.available,false,'no HTTP carrier means no browser Stop');
 const calls=[],pending=await stopWorkflowRun(offer,{view:runView(offer),request:async(url,body)=>{calls.push({url,body:copy(body)});return {stop:{schema_version:'laplace.workflow-stop-composition/1',outcome:'FUTURE_GATED_CHILDREN_PENDING',run_stopped:false,children:[{event_id:'WD-child-1',stop:'SETTLED'},{event_id:'WD-child-2',stop:'REQUESTED'}],unknown:[],effects:'Recorded effects retained; nothing undone or refunded.'}};}});
 assert.deepEqual(calls,[{url:'/work/delivery',body:offer.http.payload}],'the exact issued body is sent once');assert.equal(pending.run_stopped,false);assert.match(pending.text,/1 of 2 are not yet observed settled.*nothing was undone/);
 const claimed=workflowStopPresentation({stop:{schema_version:'laplace.workflow-stop-composition/1',outcome:'STOPPED',run_stopped:true,children:[{event_id:'WD-child-2',stop:'REQUESTED'}],coverage:{complete:true}}});assert.equal(claimed.run_stopped,false);assert.match(claimed.text,/inspect the run/i);
 const unknown=await stopWorkflowRun(offer,{view:runView(offer),request:async()=>{throw Error('connection lost');}});assert.equal(unknown.outcome,'UNKNOWN');assert.match(unknown.text,/nothing is resent/);
 await assert.rejects(stopWorkflowRun({native:copy(offer.native)},{view:runView({native:copy(offer.native)}),request:async()=>{throw Error('must not send');}}),/no owner-issued Stop/);
 // Owner always emits the offer; outside a stoppable state it is permitted:false with a reason.
 const refused={...copy(offer),permitted:false,reason:'Run already applied.'},row=Object.fromEntries(workflowInterventions({run:runView(refused)}).map(item=>[item.id,item])).stop;assert.equal(row.available,false);assert.match(row.meaning,/does not permit it now: Run already applied/);let sent=0;await assert.rejects(stopWorkflowRun(refused,{view:runView(refused),request:async()=>{sent++;}}),/does not permit Stop/);assert.equal(sent,0,'a not-permitted offer never posts');
 assert.equal(workflowStopOffer(runView({http:copy(offer.http),permitted:true})),null,'agreement is required, never inferred from one carrier');
 // Invariants from B production-function controls ART-8ccb75058a734c82a3bb2e665c2fecc4 (b3939865), on the corrected research view shape.
 const foreign={...copy(offer),http:{...copy(offer.http),payload:{...copy(offer.http.payload),work_id:'WORK-wrong'}},native:{operation:'work_delivery',payload:{...copy(payload),work_id:'WORK-wrong'}}};let posted=0;assert.equal(workflowStopOffer(runView(foreign)),null,'an offer for another Work is not this run');await assert.rejects(stopWorkflowRun(foreign,{view:runView(foreign),request:async()=>{posted++;}}),/no owner-issued Stop/);await assert.rejects(stopWorkflowRun(offer,{request:async()=>{posted++;}}),/no owner-issued Stop/);assert.equal(posted,0,'a foreign Work or a missing selected run view never posts');
 assert.equal(workflowStopOffer({...runView(offer),schema_version:'laplace.app-dispatch/1'}),null,'Stop is consumed only from the research run view');assert.equal(workflowStopOffer({...runView(offer),work:{...runView(offer).work,project:'other'}}),null,'project must match the issued carrier');assert.equal(workflowStopOffer({...runView(offer),revision:'sha256:'+'e'.repeat(64)}),null,'run revision must match the issued guard');
 const subject={project:offer.http.payload.project},reply=fields=>({work:{id:payload.work_id,project:subject.project},stop_request:{request_id:payload.request_id,children:[...payload.children]},stop:{schema_version:'laplace.workflow-stop-composition/1',outcome:'STOPPED',run_stopped:true,unknown:[],future_admission:{effective:true},children:[{event_id:'WD-child-1',stop:'SETTLED'},{event_id:'WD-child-2',stop:'SETTLED'}],...fields}});
 assert.equal(workflowStopPresentation(reply({}),payload,offer.coverage,subject).run_stopped,true,'gated, every requested child settled and the nested Work/project/request bound');
 assert.equal(workflowStopPresentation(reply({}),payload,offer.coverage).run_stopped,false,'without the expected project the nested subject is unqualified, never stopped');
 assert.equal(workflowStopPresentation(reply({children:[]}),payload,offer.coverage).run_stopped,false,'missing requested children');assert.equal(workflowStopPresentation(reply({children:[{event_id:'WD-child-1',stop:'SETTLED'},{event_id:'WD-other',stop:'SETTLED'}]}),payload,offer.coverage).run_stopped,false,'substituted child');assert.equal(workflowStopPresentation(reply({children:[{event_id:'WD-child-1',stop:'SETTLED'},{event_id:'WD-child-2',stop:'SETTLED'},{event_id:'WD-child-2',stop:'SETTLED'}]}),payload,offer.coverage).run_stopped,false,'duplicated child');
 const ungated=workflowStopPresentation(reply({future_admission:{effective:false}}),payload,offer.coverage);assert.equal(ungated.run_stopped,false);assert.match(ungated.text,/not shown as gated/);
 const other=workflowStopPresentation(reply({request_id:'another-request'}),payload,offer.coverage);assert.equal(other.outcome,'UNKNOWN');assert.equal(other.run_stopped,false);
});

// Joined research run pane. Owner values are selected pointer reads of B
// ART-c3a51b66 (retained public settled Stop cut, eb80 code, no model). Stop
// replies are controlled compositions in the owner stop_composition shape.
import {renderWorkflowRun as renderResearchRun} from '../src/laplace/web/static_shared/research-workbench-run.mjs';
import * as joined from '../src/laplace/web/static_shared/workspace-workflow-operation.mjs';
const joinedSample=operationSample.joined_research_run,recordedChild='WD-a577e18a1aa08fbaf8c63cbc';
// Controlled variant: the sample's recorded stop_request child is placed in both issued carriers to exercise a non-empty request.
const researchView=({children=null,offer={}}={})=>{const view=copy(joinedSample.run_view_selected),stop=view.actions['stop-run'];Object.assign(stop,offer);if(children)for(const carrier of ['native','http'])stop[carrier].payload.children=[...children];return view;};
const stopReply=(view,fields={},top={})=>{const issued=view.actions['stop-run'].http.payload;return {work:{id:issued.work_id,project:issued.project},stop_request:{request_id:issued.request_id,children:[...issued.children]},...top,stop:{schema_version:'laplace.workflow-stop-composition/1',request_id:issued.request_id,outcome:'STOPPED',run_stopped:true,unknown:[],future_admission:{effective:true},children:issued.children.map(event_id=>({event_id,stop:'SETTLED'})),coverage:{owned_children:issued.children.length,observed:issued.children.length,complete:true},...fields}};};
import {workflowStopRecovery} from '../src/laplace/web/static_shared/research-workbench-state.mjs';
// Controlled browser storage doubles for the existing workbench Stop recovery. Another
// page label over the same storage stands for a browser reload; no browser is claimed.
const memoryStore=({readBack=true}={})=>{const rows=new Map();return {rows,getItem:key=>rows.get(key)??null,setItem:(key,value)=>{if(readBack)rows.set(key,String(value));}};};
const recoveryOn=(store=memoryStore(),page='page-one')=>workflowStopRecovery({storage:store,backup:null,page});
const mountResearch=(view,request,isCurrent=()=>true,stopRecovery=recoveryOn())=>{const host=document.createElement('section');document.body.append(host);renderResearchRun(host,view,{request,isCurrent,stopRecovery,onAction(){throw Error('a generic action row must not run');}});return host;};
const stopControl=host=>host.querySelector('[data-control="workflow:stop-run"]');
const settle=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};

test('the research run pane mounts the guarded Stop from the actual run view, sends the issued body once and binds the nested reply subject',async()=>{
 const env=installHTMLDocument({width:390});try{
  const view=researchView({children:[recordedChild]}),calls=[],host=mountResearch(view,async(url,body)=>{calls.push({url,body:copy(body)});return stopReply(view);});
  const control=stopControl(host);assert.ok(control);assert.equal(control.disabled,false);
  assert.equal([...host.querySelectorAll('button')].filter(node=>node.textContent===view.actions['stop-run'].title).length,1,'Stop is the guarded control only, never also a generic action row');
  await control.onclick();await settle();
  assert.deepEqual(calls,[{url:'/work/delivery',body:view.actions['stop-run'].http.payload}],'exact issued body, sent once');
  const box=host.querySelector('[data-workflow-run-stop]');assert.equal(box.dataset.stopOutcome,'STOPPED');assert.match(box.textContent,/The run is stopped.*Original Stop request: workflow-c0ffc063/);assert.equal(control.disabled,true,'no resend after a sent request');
  await control.onclick();assert.equal(calls.length,1);
  const plain=document.createElement('section');document.body.append(plain);renderResearchRun(plain,view,{});assert.match(plain.textContent,/no owner transport was supplied/);assert.equal(stopControl(plain),null);
 }finally{env.restore();}
});

test('a foreign nested Work or project, an earlier request, an unpermitted offer and an incomplete gate or child set never show STOPPED',async()=>{
 const env=installHTMLDocument({width:390});try{
  const view=researchView({children:[recordedChild]}),issued=view.actions['stop-run'].http.payload;
  const outcome=async reply=>{const host=mountResearch(view,async()=>copy(reply));await stopControl(host).onclick();await settle();return host.querySelector('[data-workflow-run-stop]');};
  let box=await outcome(stopReply(view,{},{work:{id:'WORK-foreign',project:issued.project}}));assert.equal(box.dataset.stopOutcome,'UNKNOWN');assert.doesNotMatch(box.textContent,/The run is stopped/);
  box=await outcome(stopReply(view,{},{work:{id:issued.work_id,project:'other-project'}}));assert.equal(box.dataset.stopOutcome,'UNKNOWN');
  // The actual sample run view still records an EARLIER stop_request; a reply carrying it is not this request.
  box=await outcome(stopReply(view,{},{stop_request:copy(joinedSample.run_view_selected.stop_request)}));assert.equal(box.dataset.stopOutcome,'UNKNOWN');
  box=await outcome(stopReply(view,{},{stop_request:{request_id:issued.request_id,children:[recordedChild,'WD-extra']}}));assert.equal(box.dataset.stopOutcome,'UNKNOWN','the recorded request names a different child set');
  box=await outcome(stopReply(view,{},{work:undefined}));assert.notEqual(box.dataset.stopOutcome,'STOPPED');assert.match(box.textContent,/does not name this exact Work, project and Stop request/);
  box=await outcome(stopReply(view,{outcome:'FUTURE_GATED_CHILDREN_PENDING',run_stopped:false,children:[{event_id:recordedChild,stop:'REQUESTED'}]}));assert.equal(box.dataset.stopOutcome,'FUTURE_GATED_CHILDREN_PENDING');assert.match(box.textContent,/1 of 1 are not yet observed settled.*nothing was undone/);
  box=await outcome(stopReply(view,{future_admission:{effective:false}}));assert.equal(box.dataset.stopOutcome,'NOT_CONFIRMED');assert.match(box.textContent,/not shown as gated/);
  box=await outcome(stopReply(view,{children:[{event_id:recordedChild,stop:'SETTLED'},{event_id:'WD-extra',stop:'SETTLED'}]}));assert.equal(box.dataset.stopOutcome,'NOT_CONFIRMED');
  box=await outcome(stopReply(view,{unknown:[recordedChild]}));assert.equal(box.dataset.stopOutcome,'NOT_CONFIRMED');
  box=await outcome(stopReply(view,{children:[]}));assert.equal(box.dataset.stopOutcome,'NOT_CONFIRMED','an omitted child is not settled');
  const lost=mountResearch(view,async()=>{throw Error('connection lost');});await stopControl(lost).onclick();await settle();assert.equal(lost.querySelector('[data-workflow-run-stop]').dataset.stopOutcome,'UNKNOWN');assert.match(lost.textContent,/outcome is unknown.*nothing is resent/);
  const refused=researchView({offer:{permitted:false,reason:'Run already applied.'}});let posted=0;const host=mountResearch(refused,async()=>{posted++;});const control=stopControl(host);assert.equal(control.disabled,true);assert.match(host.textContent,/does not permit it now: Run already applied/);await control.onclick();assert.equal(posted,0,'permitted:false never posts');
  const moved={...researchView(),revision:'sha256:'+'e'.repeat(64)},stale=mountResearch(moved,async()=>{posted++;});assert.equal(stopControl(stale).disabled,true);assert.match(stale.textContent,/issued no Stop for this exact run and revision/);assert.equal(posted,0);
 }finally{env.restore();}
});

test('schema3 compact river Stop carries no HTTP; Open run detail follows the issued detail read; stale and later-intent results are guarded',async()=>{
 const env=installHTMLDocument({width:390});try{
  const river=joinedSample.river,run=joined.workflowRiverRun(river);
  assert.equal(run.stop.offered,true);assert.equal(run.stop.permitted,true);assert.equal(run.stop.has_http,false,'compact stop.stop_run deliberately omits HTTP');assert.equal(run.work_id,river.work_id);assert.deepEqual(run.detail_read,river.row_projection.detail_read);
  assert.deepEqual(run.actions.find(row=>row.name==='stop-run'),{name:'stop-run',title:'Stop this run and its owned children',permitted:true,reason:''},'row actions are summaries without payloads');
  const view=researchView(),urls=[];
  const got=await joined.readWorkflowRunDetail(run.detail_read,{work_id:run.work_id,project:river.scope.namespace,request:async url=>{urls.push(url);return copy(view);}});
  assert.deepEqual(urls,[run.detail_read.http.url]);assert.equal(got.work.id,river.work_id);assert.equal(got.revision,river.run_identity.run_revision);
  await assert.rejects(joined.readWorkflowRunDetail(run.detail_read,{work_id:run.work_id,project:'book',request:async()=>({schema_version:'laplace.app-dispatch/1',work:{id:run.work_id,project:'book'}})}),/not a research workflow run/);
  {// B's app-dispatch run facts are consumed read-only; the research-run refusal (and its Stop) is unchanged
   const shaped={profile:'app-dispatch',work_id:run.work_id,work:{id:run.work_id,project:'book'},
    parent_synthesis:{status:'MISSING',execution_location:'original-parent',return_path:'returns/synthesis.json'},
    observation_reads:{uses:{http:{method:'GET',url:'/work/workflow-definitions?facet=uses'}},river:{http:{method:'POST',url:'/work/delivery'}}},
    actions:{cancel_dispatch:{permitted:true,cancellation_meaning:'Cancels the dispatch Work; terminates no provider directly.',distinct_from:'selected-turn Stop, route cancellation, Source Stop'}},
    steps:[{packet:'judge',session_id:'WS-child-1',turn_id:'WT-child-1',public_reply_read:{identity:{project:'book',session_id:'WS-child-1',turn_id:'WT-child-1',part:'reply'}}}]};
   const app=joined.workflowAppRunSummary(shaped,{work_id:run.work_id,project:'book'});
   assert.equal(app.synthesis.location,'original-parent');assert.equal(app.reads.uses,'/work/workflow-definitions?facet=uses');assert.equal(app.reads.river,null);
   assert.ok(app.cancel.permitted&&app.cancel.meaning.includes('terminates no provider'));assert.equal(app.steps[0].reply.identity.turn_id,'WT-child-1');
   assert.ok(app.distinctions.some(line=>line.includes('selected-turn Stop'))&&app.distinctions.some(line=>line.includes('Source or kernel Stop')));
   assert.throws(()=>joined.workflowAppRunSummary({...shaped,work:{id:run.work_id,project:'other'}},{work_id:run.work_id,project:'book'}),/another Work or project/);
   assert.throws(()=>joined.workflowAppRunSummary({...shaped,steps:[{...shaped.steps[0],turn_id:'WT-other'}]},{work_id:run.work_id,project:'book'}),/another conversation/);
   assert.equal(joined.workflowAppRunSummary({schema_version:'laplace.app-dispatch/1'},{work_id:run.work_id}),null);
   const refused=await joined.readWorkflowRunDetail(run.detail_read,{work_id:run.work_id,project:'book',request:async()=>shaped}).catch(error=>error);
   assert.match(refused.message,/not a research workflow run/);assert.equal(refused.appRun.synthesis.status,'MISSING');}
  await assert.rejects(joined.readWorkflowRunDetail(run.detail_read,{work_id:run.work_id,project:'book',request:async()=>({...copy(view),work:{...view.work,id:'WORK-foreign'}})}),/another Work or project/);
  await assert.rejects(joined.readWorkflowRunDetail(run.detail_read,{work_id:'WORK-other',request:async()=>{throw Error('must not read');}}),/not an issued run read/);
  await assert.rejects(joined.readWorkflowRunDetail({...copy(run.detail_read),native:{operation:'project',payload:{view:'workflow-definitions',request:{...run.detail_read.request,work_id:'WORK-other'}}}},{work_id:run.work_id,request:async()=>{throw Error('must not read');}}),/carriers disagree/);
  let release,live=true;const first=document.createElement('section');document.body.append(first);
  const staleUI=joined.mountWorkflowRunStop(first,{view:researchView({children:[recordedChild]}),recovery:recoveryOn(),isCurrent:()=>live,request:()=>new Promise(resolve=>{release=resolve;})});
  const waiting=staleUI.stop();live=false;release(stopReply(researchView({children:[recordedChild]})));assert.equal(await waiting,null);assert.equal(first.querySelector('[data-workflow-run-stop]').dataset.stopOutcome,undefined,'a reply for a superseded selection is not published');
  const other=document.createElement('button');document.body.append(other);let finish;const second=document.createElement('section');document.body.append(second);
  const laterUI=joined.mountWorkflowRunStop(second,{view:researchView({children:[recordedChild]}),recovery:recoveryOn(),request:()=>new Promise(resolve=>{finish=resolve;})});
  stopControl(second).focus?.();const pending=laterUI.stop();other.focus?.();finish(stopReply(researchView({children:[recordedChild]})));await pending;
  assert.equal(document.activeElement,other,'a later user focus is not taken back');assert.equal(second.querySelector('[data-workflow-run-stop]').dataset.stopOutcome,'STOPPED');assert.equal(laterUI.value.original_request.request_id,'workflow-c0ffc06307914b90bc886b5e6b982770');
 }finally{env.restore();}
});

// Correction after independent HOLD PHASE-8fe2c1bcc5a90350697413cf (F1, F2, F7) and the
// joined-UI lifetime correction (C2-C5): retention before effect, one shared lifetime,
// Check classification and an explicit unchanged-wire resend. Owner answers are controlled
// variants in the owner request_status shape (workflow_progression.request_status 07ee2627).
const issuedOf=view=>view.actions['stop-run'];
const statusReply=(view,fields={})=>{const p=issuedOf(view).http.payload;return {project:p.project,work_id:p.work_id,request_id:p.request_id,read:copy(issuedOf(view).request_read),...fields};};
const checkControl=host=>host.querySelector('[data-control="workflow:stop-check"]');
const resendControl=host=>host.querySelector('[data-control="workflow:stop-resend"]');
const lostOnce=async(view,store)=>{const host=mountResearch(view,async()=>{throw Error('connection lost');},()=>true,recoveryOn(store));await stopControl(host).onclick();await settle();host.remove();};
// Controlled river offer over the closed river facet; the river page is the saved public
// sample, with cut/offset/returned/total supplied only where the sample omits them.
const riverOffer={read:{http:{method:'GET',url:'/work/workflow-definitions?facet=river&definition_id='+joinedSample.river.reference.identity.id},request:{facet:'river',definition_id:joinedSample.river.reference.identity.id},read_only:true,required_inputs:['work_id']}};
const riverPage={cut:'sha256:'+'a'.repeat(64),offset:0,returned:joinedSample.river.items.length,total:joinedSample.river.items.length,...copy(joinedSample.river)};
const mountRiver=(host,request,stopRecovery)=>joined.mountWorkflowObservation(host,{offer:riverOffer,facet:'river',request,inputs:{work_id:joinedSample.river.work_id},expected:{scope_id:joinedSample.river.scope_id},stopRecovery});

test('a lost Stop reply is retained and read back before the request leaves, survives Refresh and reload as unknown and is never resent automatically; no synthesis publish button',async()=>{
 const env=installHTMLDocument({width:390});try{
  const view=researchView({children:[recordedChild]}),issued=issuedOf(view),store=memoryStore(),calls=[];let atSend=null;
  // The owner always lists actions.synthesis; for a non-author reader it is permitted:false (workflow_progression.view 07ee2627).
  view.actions.synthesis={available:true,permitted:false,reason:'Only a current admitted turn of the original parent session publishes its authored synthesis.',title:'Publish original-parent synthesis'};
  const first=mountResearch(view,async(url,body)=>{atSend=JSON.parse([...store.rows.values()][0]);calls.push({url,body:copy(body)});throw Error('connection lost');},()=>true,recoveryOn(store));
  assert.equal([...first.querySelectorAll('button')].some(node=>node.textContent==='Publish original-parent synthesis'),false,'no publication button, matching the synthesis card and guides');
  await stopControl(first).onclick();await settle();
  assert.equal(calls.length,1);assert.equal(atSend.request_id,issued.http.payload.request_id);assert.deepEqual(atSend.original_request,issued.http.payload,'the exact original body was stored and read back before the request left');assert.deepEqual(atSend.request_read,issued.request_read);assert.equal(atSend.phase,'SENT');
  first.remove();
  const refreshed=mountResearch(view,async()=>{throw Error('mounting neither sends nor reads');},()=>true,recoveryOn(store));
  assert.equal(stopControl(refreshed).disabled,true,'the same cached offer is not a new Stop');assert.match(refreshed.textContent,/Original Stop request workflow-c0ffc063\S* was kept here before it was sent\. Last reply: UNKNOWN/);assert.ok(checkControl(refreshed));assert.equal(resendControl(refreshed),null,'nothing is resendable before a recognised Check');
  refreshed.remove();
  // Reload while the original is still in flight: another page over the same storage.
  const pendingStore=memoryStore();const inflight=mountResearch(view,()=>new Promise(()=>{}),()=>true,recoveryOn(pendingStore));stopControl(inflight).onclick();await settle();
  const sameTab=mountResearch(view,async()=>{throw Error('no replay');},()=>true,recoveryOn(pendingStore));assert.match(sameTab.textContent,/reply has not arrived in this page yet/);assert.equal(stopControl(sameTab).disabled,true);
  const reloaded=mountResearch(view,async()=>{throw Error('no replay after reload');},()=>true,recoveryOn(pendingStore,'page-two'));assert.match(reloaded.textContent,/reopened or reloaded after it was sent, so its outcome is unknown/);assert.equal(stopControl(reloaded).disabled,true);assert.equal(reloaded.querySelector('[data-workflow-stop-original]').dataset.originalStanding,'UNKNOWN');
  // Without a verified readback nothing is sent and the refusal stays visible.
  let sent=0;const unsaved=mountResearch(view,async()=>{sent++;},()=>true,recoveryOn(memoryStore({readBack:false})));await stopControl(unsaved).onclick();await settle();
  assert.equal(sent,0,'no request without a retained readback');assert.equal(unsaved.querySelector('[data-workflow-run-stop]').dataset.stopOutcome,'NOT_RETAINED');assert.match(unsaved.textContent,/Stop was not sent.*could not save and read back/);assert.equal(stopControl(unsaved).disabled,false,'the decision stays available; nothing was sent');
 }finally{env.restore();}
});

test('Check original Stop request releases nothing on UNKNOWN, missing, foreign or malformed answers; RECORDED and NONE are recognised but neither settles nor mints a new Stop',async()=>{
 const env=installHTMLDocument({width:390});try{
  const view=researchView({children:[recordedChild]}),issued=issuedOf(view),p=issued.http.payload;
  const cases=[['recorded',statusReply(view,{effect:'RECORDED',receipt:{request_id:p.request_id,phase_id:'phase-public'}}),'RECORDED',true],
   ['none',statusReply(view,{effect:'NONE',meaning:'No retained request at this cut; only explicit exact-wire retry is permitted. NONE is not a no-effect settlement.'}),'NONE',true],
   ['unknown',statusReply(view,{effect:'UNKNOWN',reason:'Ambiguous original request custody; retain exact wire.'}),'UNKNOWN',false],
   ['missing-subject',{effect:'RECORDED',receipt:{request_id:p.request_id}},'UNQUALIFIED',false],['missing-standing',statusReply(view),'UNQUALIFIED',false],
   ['foreign-project',statusReply(view,{project:'other-project',effect:'RECORDED',receipt:{request_id:p.request_id}}),'UNQUALIFIED',false],['foreign-work',statusReply(view,{work_id:'WORK-foreign',effect:'NONE'}),'UNQUALIFIED',false],
   ['foreign-request',statusReply(view,{request_id:'workflow-foreign-request',effect:'NONE'}),'UNQUALIFIED',false],['recorded-without-receipt',statusReply(view,{effect:'RECORDED'}),'UNQUALIFIED',false],['malformed-standing',statusReply(view,{effect:'DONE'}),'UNQUALIFIED',false]];
  for(const [name,answer,effect,qualified] of cases){
   const store=memoryStore();await lostOnce(view,store);const before=recoveryOn(store).read(p.project,p.work_id).record,reads=[];
   const host=mountResearch(view,async(url,body)=>{reads.push({url,body});return copy(answer);},()=>true,recoveryOn(store));
   await checkControl(host).onclick();await settle();
   assert.deepEqual(reads,[{url:issued.request_read.http.url,body:undefined}],name+': only the issued request read; nothing is sent');
   const after=recoveryOn(store).read(p.project,p.work_id).record;assert.equal(after.checked.effect,effect,name);assert.equal(after.checked.qualified,qualified,name);assert.deepEqual(after.original_request,before.original_request,name+': original receipt retained');assert.equal(after.request_id,p.request_id);
   assert.equal(stopControl(host).disabled,true,name+': the cached offer with the same request is never a new Stop');assert.equal(!!resendControl(host),qualified,name+': only RECORDED or NONE offers the explicit unchanged resend');
   assert.match(host.textContent,new RegExp('Owner standing of the original Stop request: '+effect));if(!qualified)assert.match(host.textContent,/stays held/);assert.doesNotMatch(host.textContent,/under its new identity/);host.remove();
  }
 }finally{env.restore();}
});

test('explicit unchanged-wire resend is distinct from a genuinely new owner-issued Stop; UNKNOWN releases neither and a late reply never overwrites a newer request',async()=>{
 const env=installHTMLDocument({width:390});try{
  const view=researchView({children:[recordedChild]}),p=issuedOf(view).http.payload,store=memoryStore(),posts=[];
  await lostOnce(view,store);
  let host=mountResearch(view,async(url,body)=>{if(body){posts.push(copy(body));throw Error('connection lost again');}return statusReply(view,{effect:'NONE'});},()=>true,recoveryOn(store));
  await checkControl(host).onclick();await settle();await resendControl(host).onclick();await settle();
  assert.equal(posts.length,1);assert.deepEqual(posts[0],p,'the retained original wire, unchanged');
  const record=recoveryOn(store).read(p.project,p.work_id).record;assert.equal(record.attempt,2);assert.equal(record.request_id,p.request_id);assert.equal(record.checked,null,'a new attempt needs its own Check');
  assert.equal(resendControl(host),null,'one resend per explicit decision');assert.equal(stopControl(host).disabled,true);assert.match(host.textContent,/sent 2 times, unchanged/);host.remove();
  // Controlled variant: a newer owner offer carrying a new request identity in every carrier.
  const fresh='workflow-controlled-newly-issued-0001',newer=researchView({children:[recordedChild]});newer.actions['stop-run']=JSON.parse(JSON.stringify(newer.actions['stop-run']).replaceAll(p.request_id,fresh));
  host=mountResearch(newer,async(url,body)=>{if(body){posts.push(copy(body));throw Error('lost');}return statusReply(view,{effect:'UNKNOWN',reason:'Ambiguous original request custody; retain exact wire.'});},()=>true,recoveryOn(store));
  assert.equal(stopControl(host).disabled,true,'the unchecked second attempt still holds');await checkControl(host).onclick();await settle();assert.equal(stopControl(host).disabled,true,'UNKNOWN releases no new Stop');assert.equal(resendControl(host),null);host.remove();
  assert.equal(posts.length,1);
  // A late reply for the earlier request cannot overwrite the newer one.
  const race=memoryStore();let releaseOld,releaseNew;
  // Peer HOLD (B check-supersession 1429f887): two STILL-LIVE controllers share one store.
  let oldSettled=0;const older=document.createElement('section');document.body.append(older);const olderUI=joined.mountWorkflowRunStop(older,{view,recovery:recoveryOn(race),onSettled:()=>oldSettled++,request:()=>new Promise(resolve=>{releaseOld=resolve;})});const oldPending=olderUI.stop();await settle();
  const later=mountResearch(newer,async(url,body)=>{if(!body)return statusReply(view,{effect:'NONE'});posts.push(copy(body));return new Promise(resolve=>{releaseNew=resolve;});},()=>true,recoveryOn(race));
  assert.equal(stopControl(later).disabled,true);await checkControl(later).onclick();await settle();assert.equal(stopControl(later).disabled,false,'a genuinely new owner identity is a separate Stop');assert.match(later.textContent,/newly issued request workflow-controlled-newly-issued-0001/);
  const newPending=stopControl(later).onclick();await settle();assert.equal(posts.at(-1).request_id,fresh);
  const focusBefore=document.activeElement;releaseOld(stopReply(view));assert.equal(await oldPending,null,'a superseded reply is not the old controller’s current result');await settle();
  const oldBox=older.querySelector('[data-workflow-run-stop]');assert.notEqual(oldBox.dataset.stopOutcome,'STOPPED');assert.doesNotMatch(oldBox.textContent,/The run is stopped/);assert.equal(oldSettled,0,'no onSettled for a superseded reply');assert.equal(document.activeElement,focusBefore,'focus is not moved');assert.match(oldBox.textContent,/Original Stop request workflow-controlled-newly-issued-0001/,'the still-live old controller shows the current newer request');assert.match(oldBox.textContent,/A newer Stop request replaced/);
  let current=recoveryOn(race).read(p.project,p.work_id).record;assert.equal(current.request_id,fresh,'the newer request stays current');assert.equal(current.phase,'SENT');assert.equal(current.replaced[0].request_id,p.request_id);assert.equal(current.replaced[0].outcome,'STOPPED','the late reply stays with its own request');
  releaseNew(stopReply(newer));await newPending;await settle();current=recoveryOn(race).read(p.project,p.work_id).record;assert.equal(current.request_id,fresh);assert.equal(current.outcome,'STOPPED');olderUI.destroy();
  // A Check whose attempt is replaced before its answer arrives publishes no standing and releases nothing.
  const checkStore=memoryStore();await lostOnce(view,checkStore);let answer;const checker=mountResearch(view,()=>new Promise(resolve=>{answer=resolve;}),()=>true,recoveryOn(checkStore));const checking=checkControl(checker).onclick();await settle();
  const other=mountResearch(view,async(url,body)=>{if(body)throw Error('lost');return statusReply(view,{effect:'NONE'});},()=>true,recoveryOn(checkStore));await checkControl(other).onclick();await settle();await resendControl(other).onclick();await settle();
  answer(statusReply(view,{effect:'RECORDED',receipt:{request_id:p.request_id}}));assert.equal(await checking,null);await settle();
  assert.doesNotMatch(checker.textContent,/Owner standing of the original Stop request: RECORDED/);assert.match(checker.textContent,/A newer attempt replaced the Stop request being checked/);assert.equal(resendControl(checker),null,'a superseded answer releases nothing');assert.equal(recoveryOn(checkStore).read(p.project,p.work_id).record.checked,null);
 }finally{env.restore();}
});

test('river Open run detail, its reopening, Plan & run and a reload share one retained original with exactly one POST',async()=>{
 const env=installHTMLDocument({width:390});try{
  const river=joinedSample.river,view=researchView({children:[recordedChild]}),p=issuedOf(view).http.payload,store=memoryStore(),calls=[];
  const request=async(url,body)=>{calls.push({url,...(body?{body:copy(body)}:{})});if(body)throw Error('connection lost');return url===riverOffer.read.http.url?copy(riverPage):copy(view);};
  const host=document.createElement('main');document.body.append(host);const ui=mountRiver(host,request,recoveryOn(store));
  assert.equal(await ui.load(),true);await host.querySelector('[data-control="workflow:run-detail"]').onclick();await settle();assert.equal(calls.at(-1).url,river.row_projection.detail_read.http.url);
  await stopControl(host).onclick();await settle();assert.match(host.textContent,/outcome is unknown/);
  await host.querySelector('[data-control="workflow:run-detail"]').onclick();await settle();
  assert.equal(stopControl(host).disabled,true,'reopening the detail keeps the original held');assert.ok(checkControl(host));assert.match(host.textContent,/Last reply: UNKNOWN/);ui.destroy();host.remove();
  const pane=mountResearch(view,request,()=>true,recoveryOn(store));assert.equal(stopControl(pane).disabled,true,'Plan & run reads the same original');assert.equal(pane.querySelector('[data-workflow-stop-original]').dataset.originalRequest,p.request_id);
  const reloaded=document.createElement('main');document.body.append(reloaded);const again=mountRiver(reloaded,request,recoveryOn(store,'page-two'));await again.load();await reloaded.querySelector('[data-control="workflow:run-detail"]').onclick();await settle();assert.equal(stopControl(reloaded).disabled,true);
  assert.equal(calls.filter(row=>row.body).length,1,'one POST in total; nothing replayed on reopen, Plan & run or reload');again.destroy();
 }finally{env.restore();}
});

test('run detail binds the complete issued selector: any HTTP, request, native or SDK disagreement refuses before transport; the exact carrier reads',async()=>{
 const river=joinedSample.river,original=river.row_projection.detail_read,view=researchView();
 const attempt=async(handle,options={})=>{const urls=[];let error=null,value=null;try{value=await joined.readWorkflowRunDetail(handle,{work_id:river.work_id,project:'book',request:async url=>{urls.push(url);return copy(view);},...options});}catch(problem){error=problem.message;}return {urls,error,value};};
 const variant=edit=>{const handle=copy(original);edit(handle);return handle;},query=(handle,key,value)=>{const url=new URL(handle.http.url,'http://local');if(value===undefined)url.searchParams.delete(key);else url.searchParams.set(key,value);handle.http.url=url.pathname+url.search;};
 const exact=await attempt(copy(original));assert.deepEqual(exact.urls,[original.http.url]);assert.equal(exact.value.work.id,river.work_id);
 // The first row is A's original adverse carrier (read-carrier-check.mjs 72371b60): only the HTTP version changes.
 for(const [name,handle,options] of [['http-version',variant(h=>query(h,'version','sha256:'+'f'.repeat(64)))],['http-definition',variant(h=>query(h,'definition_id','WDEF-other'))],['http-lens',variant(h=>query(h,'project_lens','other'))],['http-drops-version',variant(h=>query(h,'version'))],['http-extra-field',variant(h=>query(h,'scope','"x"'))],['http-duplicate',variant(h=>{h.http.url+='&facet=app-run';})],
  ['native-version',variant(h=>{h.native.payload.request.version='sha256:'+'e'.repeat(64);})],['request-lens',variant(h=>{h.request.project_lens='other';})],['request-extra',variant(h=>{h.request.view='full';})],['native-extra-key',variant(h=>{h.native.payload.extra=true;})],
  ['sdk-disagrees',variant(h=>{h.sdk={method:'workflow_request',payload:{...copy(h.request),version:'sha256:'+'d'.repeat(64)}};})],['unknown-carrier',variant(h=>{h.url=h.http.url;})],['http-only',variant(h=>{delete h.request;delete h.native;})],['post',variant(h=>{h.http.method='POST';})],
  ['other-version-than-river',copy(original),{expected:{version:'sha256:'+'c'.repeat(64)}}],['other-project',copy(original),{project:'other-project'}]]){const got=await attempt(handle,options);assert.deepEqual(got.urls,[],name+': refused before transport');assert.ok(got.error,name);}
 assert.equal((await attempt(variant(h=>{h.sdk={method:'workflow_request',payload:copy(h.request)};}))).urls.length,1,'an agreeing SDK carrier reads');
});

// Focused evaluator for conditional workflow controls declared in canonical declarations.py,
// read through the generated tests/fixtures/help/controls.json (regenerated separately).
test('focused declared states: run detail, Stop offered, Stop pending and resend offered render exactly their declared conditional controls',async()=>{
 const env=installHTMLDocument({width:390});try{
  const CONTROLS=JSON.parse(readFileSync(new URL('./fixtures/help/controls.json',import.meta.url),'utf8')),ids=['run-detail','stop-run','stop-check','stop-resend'].map(id=>'workflow:'+id),declared=Object.fromEntries(CONTROLS.controls.filter(row=>ids.includes(row.id)).map(row=>[row.id,row]));
  assert.deepEqual(Object.keys(declared).sort(),[...ids].sort(),'each mounted conditional control is declared');
  const expectState=(host,state)=>{const shown=new Set([...host.querySelectorAll('button')].filter(node=>!node.disabled&&ids.includes(node.dataset.control)).map(node=>node.dataset.control));for(const id of ids)assert.equal(shown.has(id),declared[id].states.includes(state),state+': '+id);};
  const river=joinedSample.river,view=researchView({children:[recordedChild]}),request=async(url,body)=>{if(body)throw Error('connection lost');if(url===riverOffer.read.http.url)return copy(riverPage);if(url===river.row_projection.detail_read.http.url)return copy(view);return statusReply(view,{effect:'NONE'});};
  const host=document.createElement('main');document.body.append(host);const ui=mountRiver(host,request,recoveryOn());
  await ui.load();expectState(host,'run-detail-offered');await host.querySelector('[data-control="workflow:run-detail"]').onclick();await settle();expectState(host,'stop-offered');
  await stopControl(host).onclick();await settle();expectState(host,'stop-pending');await checkControl(host).onclick();await settle();expectState(host,'stop-resend-offered');ui.destroy();
 }finally{env.restore();}
});

test('river rows offer owner-issued reads only through a supplied reader; the current Runs mount supplies none',async()=>{
 const env=installHTMLDocument({width:390});try{
  const opened=[],request=async url=>{if(url!==riverOffer.read.http.url)throw Error('unexpected read '+url);return copy(riverPage);};
  const host=document.createElement('main');document.body.append(host);const ui=joined.mountWorkflowObservation(host,{offer:riverOffer,facet:'river',request,inputs:{work_id:joinedSample.river.work_id},expected:{scope_id:joinedSample.river.scope_id},stopRecovery:recoveryOn(),onRead:(read,label)=>opened.push({read,label})});
  await ui.load();const reads=[...host.querySelectorAll('[data-control="workflow:river-read"]')];assert.ok(reads.length>=1);await reads[0].onclick();assert.equal(opened.length,1);assert.deepEqual(opened[0].read,joinedSample.river.items[0].reads.reply);assert.equal(opened[0].label,'Read complete response');ui.destroy();
  const plain=document.createElement('main');document.body.append(plain);const bare=mountRiver(plain,request,recoveryOn());await bare.load();assert.equal(plain.querySelector('[data-control="workflow:river-read"]'),null,'no reader, no read control');bare.destroy();
 }finally{env.restore();}
});

test('the exact owner Stop reply shape (_stop_children over stop_composition) qualifies STOPPED only with the nested subject and its child set',async()=>{
 const env=installHTMLDocument({width:390});try{
  const view=researchView({children:[recordedChild]}),issued=view.actions['stop-run'].http.payload;
  // Field shape of workflow_progression._stop_children (07ee2627) wrapping workflow_operations.stop_composition (0a19a8d6) inside the action reply {...run view, stop}. Values are controlled.
  const owner={...copy(view),stop_request:{request_id:issued.request_id,children:[recordedChild],requested_at:'2026-10-30T06:00:00+00:00',actor:{kind:'human',turn_id:null,session_id:null}},stop:{schema_version:'laplace.workflow-stop-composition/1',future_admission:{observed_state:'STOP_BEFORE_NEXT',effective:true,owner_result:{state:'STOP_BEFORE_NEXT',effective:true,request_id:issued.request_id}},children:[{event_id:recordedChild,observed_state:'RESULT',stop:'SETTLED',control:null,error:null}],unknown:[],run_stopped:true,outcome:'STOPPED',effects:'Recorded effects, proposals and returns are retained; nothing is undone or refunded.',meaning:'Labels describe this composition only.',request_id:issued.request_id,controls_issued_now:true,coverage:{owned_children:1,observed:1,complete:true},observed_at:'2026-10-30T06:00:01+00:00'}};
  const host=mountResearch(view,async()=>copy(owner));await stopControl(host).onclick();await settle();assert.equal(host.querySelector('[data-workflow-run-stop]').dataset.stopOutcome,'STOPPED');
  const bare=copy(owner);delete bare.stop_request.children;const second=mountResearch(view,async()=>copy(bare));await stopControl(second).onclick();await settle();
  assert.equal(second.querySelector('[data-workflow-run-stop]').dataset.stopOutcome,'NOT_CONFIRMED','a recorded request without its child set is unqualified');
 }finally{env.restore();}
});

// C1 (Root consumer supplement): the app-run summary painted by the actual Open run detail read of an owner app-dispatch
// run. Three children, two of them the same packet, give three reply controls: each carries its child turn as its
// owner, so the shared return coordinate finds exactly that step, while an ownerless coordinate is ambiguous (no target).
test('an app run with several children gives every step reply its own return coordinate and keeps one uses/flow read',async()=>{
 const env=installHTMLDocument({width:390});try{
  const {focusCoordinate,focusTarget}=await import('../src/laplace/web/static_shared/workspace-returns.mjs');
  const river=joinedSample.river,work=river.work_id;
  const step=(packet,n)=>({packet,session_id:'WS-child-'+n,turn_id:'WT-child-'+n,public_reply_read:{identity:{project:'book',session_id:'WS-child-'+n,turn_id:'WT-child-'+n,part:'reply'}}});
  const shaped={profile:'app-dispatch',work_id:work,work:{id:work,project:'book'},parent_synthesis:{status:'MISSING',execution_location:'original-parent',return_path:'returns/synthesis.json'},
   observation_reads:{uses:{http:{method:'GET',url:'/work/workflow-definitions?facet=uses'}},river:{http:{method:'GET',url:'/work/workflow-definitions?facet=river'}}},
   actions:{cancel_dispatch:{permitted:true,cancellation_meaning:'Cancels the dispatch Work; terminates no provider directly.',distinct_from:'selected-turn Stop, route cancellation, Source Stop'}},
   steps:[step('builder',1),step('judge',2),step('judge',3)]};
  const opened=[],request=async url=>{if(url===riverOffer.read.http.url)return copy(riverPage);if(url===river.row_projection.detail_read.http.url)return copy(shaped);throw Error('unexpected read '+url);};
  const host=document.createElement('main');document.body.append(host);
  const ui=joined.mountWorkflowObservation(host,{offer:riverOffer,facet:'river',request,inputs:{work_id:work},expected:{scope_id:river.scope_id},stopRecovery:recoveryOn(),onRead:(read,label,row)=>opened.push({read,label,row})});
  await ui.load();await host.querySelector('[data-control="workflow:run-detail"]').onclick();await settle();
  const replies=[...host.querySelectorAll('[data-control="workflow:app-run-reply"]')];
  assert.deepEqual(replies.map(node=>node.dataset.controlOwner),['WT-child-1','WT-child-2','WT-child-3'],'two judge steps share a packet, never a coordinate');
  for(const id of ['workflow:app-run-uses','workflow:app-run-river'])assert.equal(host.querySelectorAll('[data-control="'+id+'"]').length,1,id);
  const coordinate=focusCoordinate(host,replies[2]);
  assert.deepEqual({control:coordinate.control,owner:coordinate.owner},{control:'workflow:app-run-reply',owner:'WT-child-3'});
  assert.equal(focusTarget(host,coordinate),replies[2],'Back restores the exact step');
  assert.equal(focusTarget(host,{control:'workflow:app-run-reply'}),null,'the former ownerless coordinate names no single step');
  await replies[2].onclick();assert.equal(opened.length,1);assert.equal(opened[0].read.identity.turn_id,'WT-child-3');assert.equal(opened[0].label,'Read complete response');
  ui.destroy();
 }finally{env.restore();}
});
