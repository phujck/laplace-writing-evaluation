import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {beforeEach, test} from 'node:test';
import {WorkspaceSession,projectRequest,turnFailures,turnCompletionStatus,appendStreamText,messageLinkParts,ownerHumanTarget} from '../src/laplace/web/static_shared/workspace-session.mjs';
import {pilotSessionFixture} from './helpers/session_preferences_fixture.mjs';
import {decodeComposerDraft,connectedObservationSeconds,encodeComposerDraft} from '../src/laplace/web/static_shared/workspace-interaction.mjs';


// E0 engineering fixture: synthetic identities/content, retained owner DTO structure.
// Real send/connect/complete/loadSession/renderMessageTurns and real Markdown renderer.
async function e0Replay({catalogueFailure=false,width=1280,zeroActions=false,replyAvailable=true,terminalEvent='complete',historyError=false}={}) {
 const {installHTMLDocument,Element:FixtureElement}=await import('./helpers/html_dom.mjs');
 // This DOM double omits outerHTML. Supply actual structural serialization so the
 // controller's unchanged metadata equality test cannot mistake controls for "".
 const outerBefore=Object.getOwnPropertyDescriptor(FixtureElement.prototype,'outerHTML');
 const escape=value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
 const serialize=node=>node.nodeType===3?escape(node.textContent):'<'+node.localName+node.attributes.map(a=>' '+a.name+'="'+escape(a.value)+'"').join('')+'>'+node.childNodes.map(serialize).join('')+'</'+node.localName+'>';
 Object.defineProperty(FixtureElement.prototype,'outerHTML',{configurable:true,get(){return serialize(this);}});
 // Resolve the app's public /shared/ module URLs to the exact staged source files.
 const {registerHooks}=await import('node:module');
 const hook=registerHooks({resolve(specifier,context,next){return next(specifier.startsWith('/shared/')?new URL('../src/laplace/web/static_shared/'+specifier.slice(8),import.meta.url).href:specifier,context);}});
 let renderArtifactMarkdown;try{({renderArtifactMarkdown}=await import('../src/laplace/web/static_shared/workspace-inspection.mjs'));}finally{hook.deregister();}
 const env=installHTMLDocument({width}),css=globalThis.CSS,transport=globalThis.EventSource,fetchBefore=globalThis.fetch;
 globalThis.CSS={escape:value=>String(value).replace(/[^A-Za-z0-9_-]/g,'\\$&')};
 class Stream {static instances=[];static CLOSED=2;constructor(url){this.url=url;this.readyState=1;Stream.instances.push(this);}close(){this.readyState=2;}emit(item){this.onmessage?.({data:JSON.stringify(item)});}}
 globalThis.EventSource=Stream;
 const current=Object.create(WorkspaceSession.prototype),fields=new Map(),host=document.createElement('section');document.body.append(host);
 current.find=selector=>{if(selector==='.session-empty')return fields.get('[data-thread]')?.querySelector(selector)||null;
  if(!fields.has(selector)){const node=document.createElement(selector==='[data-message]'?'textarea':'div');
   if(selector.startsWith('.'))node.className=selector.slice(1);if(selector.startsWith('[data-'))node.setAttribute(selector.slice(1,-1),'');
   fields.set(selector,node);host.append(node);}return fields.get(selector);};
 Object.assign(current,{host,project:'pilot',session:'WS-e0',active:'',role:'author',sessionLoad:0,viewEpoch:0,streamGeneration:0,settingsRevision:0,modeRevision:0,
  settingsSave:Promise.resolve(),ready:Promise.resolve(),runningSessions:new Map(),sessionRows:[],queued:[],limit:30,key:'laplace:session:pilot',draftKey:'laplace:compose:pilot',
  getContext:()=>({surface:'project',label:'Fixture'}),loadQueue:async()=>{},onProposalChanged:async()=>{},onChanged:async()=>{},onReadTurn:()=>{},onReviewProposal:()=>{},onOpenArtifact:()=>{},onApplication:()=>{}});
 current.providers=[{id:'claude',models:[{id:'opus',name:'Opus',efforts:['low','medium','high']}]}];
 current.find('[data-provider]').value='claude';current.models('opus');current.efforts('high');current.find('[data-mode]').value='work';
 const sid=current.session,tid='WT-e0',project=current.project,pin='sha256:'+'a'.repeat(64),text='**Synthetic terminal reply**',request='Synthetic request',calls=[];
 const thread=current.find('[data-thread]');Object.defineProperties(thread,{clientHeight:{value:100},scrollHeight:{value:240}});
 const turn={id:tid,session_id:sid,project,text:request,mode:'work',role:'author',reply:{id:'WR-e0',status:'completed',display_text:'Synthetic',display_text_chars:text.length,display_text_truncated:true},
  action_count:zeroActions?0:1,failure_count:zeroActions?0:1,unresolved_count:zeroActions?0:1,result_links_total:zeroActions?0:1,
  ...(!zeroActions?{proposal_edit_count:1,proposal_state:'resolved-into-successor',proposal_version:pin,proposal_turn_id:tid,
   proposal_read_handle:{http:{method:'GET',url:'/authoring/proposal-preview?'+new URLSearchParams({project,id:tid,proposal_version:pin,view:'summary'})}}}:{}),
  detail:{turn_id:tid},body_read:{http:{method:'GET',url:'/authoring/session-turn?'+new URLSearchParams({project,id:tid,view:'turn'})}}};
 const session={id:sid,project,provider:'claude',model:'opus',effort:'high',role:'author',title:'Synthetic conversation'};
 let saved=false,failCatalogue=catalogueFailure,failHistory=historyError;
 current.renderFinalMessage=(body,content,options)=>renderArtifactMarkdown(body,content,{project,...options});
 globalThis.fetch=async(path,options={})=>{calls.push({path,method:options.method||'GET'});const url=new URL(path,'http://local'),q=url.searchParams;
  if(path==='/authoring/turn')return response({session_id:sid,turn_id:tid});
  if(url.pathname==='/authoring/state'){if(saved&&failCatalogue){failCatalogue=false;throw Error('Fixture catalogue unavailable');}return response({sessions:[session],session_count:1});}
  if(url.pathname==='/authoring/session')return response({session,turns:saved?[turn]:[],active:null});
  if(url.pathname==='/authoring/session-turn'){
   if(q.get('view')==='message'){const part=q.get('part'),content=part==='request'?request:text;
    const identity={project,session_id:sid,turn_id:tid,part},handle=basis=>({identity,http:{method:'GET',url:'/authoring/session-turn?'+new URLSearchParams({project,session_id:sid,id:tid,part,view:'message',offset:0,limit:4000,...(basis?{expected_basis:pin}:{})})}});
    return response({schema_version:'laplace.writing-message-part/1',...identity,state:part==='reply'&&!replyAvailable?'ABSENT':'AVAILABLE',basis:pin,content:part==='reply'&&!replyAvailable?null:content,offset:0,end:content.length,limit:4000,total_characters:content.length,total_utf8_bytes:content.length,page_utf8_bytes:content.length,complete:true,truncated:false,source_record_id:part==='reply'?'WR-e0':tid,source_row_sha256:pin,session_row_sha256:pin,turn_row_sha256:pin,content_sha256:pin,presentation_origin:'text',presentation_policy:'laplace.writing-public-message-presentation/1',currentness:{state:'CURRENT_AT_READ',basis:pin},restart_read:handle(false),page_read:handle(true),next_read:null});}
   if(q.get('view')==='summary')return response({project,turn:{...turn,result_links:[],result_links_total:0,result_links_more:false},exact:true});
   const view=q.get('view');if(view==='actions'&&failHistory){failHistory=false;throw Error('Fixture records unavailable');}const items=view==='actions'?[{id:'ACTION-e0',operation:'propose_revision',outcome:{status:'SUCCEEDED',views:['proposal'],paths:[]}}]:view==='failures'?[{origin:'journal',record:{record:'writing-tool-failure',id:'FAIL-e0',operation:'help',error:'Fixture refusal',payload:{}},resolved_later:false,recovery_read:null,related_action:null}]:[];
   return response({project,turn_id:tid,view,items,exact:true,pagination:{offset:0,limit:20,total:items.length,next_offset:null}});
  }throw Error('Unexpected fixture read '+path);
 };
 const observation={id:tid,session_id:sid,capabilities:{observation:'events',events_url:'/authoring/events?turn='+tid,can_interrupt:true,can_steer:false,input_delivery_modes:[]}};
 const connect=current.connect;current.connect=(id,cursor=0,value)=>connect.call(current,id,cursor,value||observation);
 const settle=async()=>{for(let i=0;i<8;i++)await new Promise(resolve=>setImmediate(resolve));for(const group of current.messageGroups?.values()||[])for(const reader of group.readers||[])await reader.open();for(let i=0;i<4;i++)await new Promise(resolve=>setImmediate(resolve));};
 const close=()=>{current.suspendMessageReading();current.stream?.close();clearTimeout(current.snapshotTimer);if(css===undefined)delete globalThis.CSS;else globalThis.CSS=css;globalThis.EventSource=transport;globalThis.fetch=fetchBefore;if(outerBefore)Object.defineProperty(FixtureElement.prototype,'outerHTML',outerBefore);else delete FixtureElement.prototype.outerHTML;env.restore();};
 try{await current.loadSession();current.find('[data-message]').value=request;await current.send();const stream=Stream.instances.at(-1);assert.ok(stream,'real connect reached the model-free event transport');
  stream.emit({type:'delta',text});const composer=current.find('[data-message]');composer.value='Newer unsent draft';current.persistComposerDraft(composer.value);composer.focus();composer.selectionStart=3;composer.selectionEnd=7;thread.scrollTop=17;
  saved=terminalEvent==='complete';stream.emit(terminalEvent==='error'?{type:'error',message:'Fixture transport failed'}:{type:'complete',result:{status:'completed'}});await settle();return {current,thread,tid,text,calls,settle,close};
 }catch(error){close();throw error;}
}
test('E0 real live terminal and reopen reconcile one rich owner reply with lazy evidence controls',async()=>{
 const f=await e0Replay();try{
  assert.equal(f.thread.querySelectorAll('.session-message.assistant').length,1,'unkeyed optimistic and stream rows must not survive canonical terminal reconciliation');
  const row=f.thread.querySelector('[data-turn-key="'+f.tid+'"] [data-message-part="reply"]');assert.ok(row);
  assert.ok(row.querySelector('.session-body strong'),'actual Markdown renderer formats the complete owner body');
  for(const selector of ['.session-message-basis','.session-complete-turn','.session-actions','.session-tool-failures','.session-inspect-proposal','.session-result-links'])assert.ok(row.querySelector(selector),selector);
  assert.ok(f.calls.every(c=>!/[?&]view=(actions|failures)/.test(c.path)),'closed history stays lazy');
  const actions=row.querySelector('.session-actions');actions.open=true;await actions.ontoggle();assert.equal(actions.querySelectorAll('.session-action').length,1);
  const failures=row.querySelector('.session-tool-failures');failures.open=true;await failures.ontoggle();assert.match(failures.textContent,/help/);
  const composer=f.current.find('[data-message]');assert.equal(composer.value,'Newer unsent draft');assert.equal(document.activeElement,composer);assert.equal(composer.selectionStart,3);assert.equal(composer.selectionEnd,7);assert.equal(f.thread.scrollTop,17);
  assert.deepEqual(['provider','model','effort','mode'].map(name=>f.current.find('[data-'+name+']').value),['claude','opus','high','work']);
  await f.current.openConversation('WS-e0');await f.settle();assert.equal(f.thread.querySelectorAll('.session-message.assistant').length,1);assert.ok(f.thread.querySelector('.session-complete-turn'));
  assert.equal(composer.value,'Newer unsent draft');assert.equal(f.calls.filter(c=>c.method==='POST').length,1);
 }finally{f.close();}
});
test('E0 optional catalogue failure does not block critical terminal audit for a zero-action reply',async()=>{
 const f=await e0Replay({catalogueFailure:true,width:720,zeroActions:true});try{
  assert.ok(f.thread.querySelector('[data-turn-key="'+f.tid+'"] .session-complete-turn'),'critical saved reply must load despite the optional catalogue failure');
  assert.ok(f.thread.querySelector('.session-message-basis'));assert.equal(f.current.find('[data-message]').value,'Newer unsent draft');
 }finally{f.close();}
});


test('E0 reopened lazy controls read the exact turn in the current visit and retry a real read error',async()=>{
 const f=await e0Replay({historyError:true});try{
  await f.current.openConversation('WS-e0');await f.settle();
  const row=f.thread.querySelector('[data-turn-key="'+f.tid+'"] [data-message-part="reply"]'),actions=row.querySelector('.session-actions');
  actions.open=true;await actions.ontoggle();assert.match(actions.textContent,/Saved records could not load: The local engine is unavailable/);assert.equal(actions.lastElementChild.textContent,'Retry saved records');
  await actions.lastElementChild.onclick();assert.equal(actions.querySelectorAll('.session-action').length,1);
  const reads=f.calls.filter(c=>/[?&]view=actions/.test(c.path));assert.equal(reads.length,2);assert.ok(reads.every(c=>new URL(c.path,'http://local').searchParams.get('id')===f.tid));
 }finally{f.close();}
});
test('E0 absent saved body retains its streamed text without pretending it is formatted saved content',async()=>{
 const f=await e0Replay({replyAvailable:false});try{
  const row=f.thread.querySelector('[data-turn-key="'+f.tid+'"] [data-message-part="reply"]');
  assert.equal(f.thread.querySelectorAll('.session-message.assistant').length,1);
  assert.match(row.querySelector('.session-body').textContent,/Synthetic terminal reply/);
  assert.equal(row.querySelector('.session-body strong'),null);
  assert.equal(f.current.find('[data-message]').value,'Newer unsent draft');
 }finally{f.close();}
});
test('E0 terminal error preserves partial output and draft without inventing saved audit or actions',async()=>{
 const f=await e0Replay({terminalEvent:'error'});try{
  assert.equal(f.thread.querySelectorAll('.session-message.assistant').length,1);
  assert.match(f.thread.textContent,/Synthetic terminal reply/);assert.ok(f.thread.querySelector('.session-unsaved-reply'));
  assert.equal(f.thread.querySelector('.session-complete-turn'),null);assert.equal(f.thread.querySelector('.session-actions'),null);
  assert.equal(f.current.find('[data-message]').value,'Newer unsent draft');
 }finally{f.close();}
});

test('qualified Work and material URLs are owners before filenames; malformed routes never fall through',()=>{
 const work='/work/state?project=other&view=detail&id=WORK-exact&limit=1';
 const target={owner:'artifact',project:'owner-project',path:'notes/a.md',scope:'project'};
 const material='/projects/material-references?'+new URLSearchParams({project:'consumer',view:'preview',target:JSON.stringify(target)});
 const parts=messageLinkParts(`[Work](${work}) [Source](${material})`,{project:'selected'}).filter(p=>p.kind);
 assert.deepEqual(parts.map(p=>p.kind),['owner-read','owner-read']);assert.equal(parts[0].ownerRead.project,'other');assert.equal(parts[1].ownerRead.project,'consumer');assert.deepEqual(parts[1].ownerRead.target,target);
 for(const uri of [work+'&id=other',work+'&project=selected',work+'&write=1',work+'#fragment','/work/state?view=detail&id=WORK-exact',material+'&target=%7B%7D',material+'&id=MAT-other','/projects/material-references?project=p&view=preview&target=bad','/projects/material-references?project=p&view=preview&target=%7B%22owner%22%3A%22wrong%22%7D']){
  assert.equal(ownerHumanTarget(uri),null,uri);assert.ok(messageLinkParts(`[Read](${uri})`,{project:'selected'}).every(p=>!p.kind),uri);
 }
 const external='https://external.example'+work;assert.equal(ownerHumanTarget(external),null);assert.equal(messageLinkParts(`[External](${external})`)[0].kind,'web');
 assert.equal(ownerHumanTarget('http://user:secret@localhost'+work),null);assert.equal(messageLinkParts(`[External](//external.example${work})`)[0].kind,'web');
 assert.equal(messageLinkParts('[File](notes/a.md)',{project:'selected'})[0].kind,'artifact');
 assert.equal(messageLinkParts('[File](work/state.md)',{project:'selected'})[0].kind,'artifact');
});
test('unformatted conversation owner clicks use the same inspector callback without changing conversation or draft',async()=>{
 const original=globalThis.document;
 const node=(tag,text='')=>({tag,textContent:text,children:[],className:'',append(...values){this.children.push(...values);},classList:{add(){},remove(){}}});
 const thread=node('section'),opened=[],scope={conversation:'WS-kept',selection:'chapter-3',draft:'Unsent scope draft'};
 try{globalThis.document={createElement:tag=>node(tag),createTextNode:text=>node('#text',text)};
 const reader={project:'selected',find:selector=>selector==='[data-thread]'?thread:null,guard:fn=>fn(),onOpenOwner:(...args)=>opened.push(args)};
 const url='/work/state?project=other&view=detail&id=WORK-owned';WorkspaceSession.prototype.message.call(reader,'assistant',`[Read work](${url})`);
 const link=thread.children[0].children[1].children.find(n=>n.tag==='a');link.onclick({preventDefault(){}});await Promise.resolve();
 assert.equal(opened[0][0].http.url,url);assert.equal(opened[0][0].project,'other');assert.deepEqual(scope,{conversation:'WS-kept',selection:'chapter-3',draft:'Unsent scope draft'});
 }finally{globalThis.document=original;}
});

test('archived figure failures retain errors without client-inferred resolution',()=>{
  const archive=JSON.parse(readFileSync(new URL('./fixtures/spanspermia_editor_archive.json',import.meta.url)));
  const attempts=archive.attempts.filter(row=>row.turn_id===archive.turn_id);
  const actions=attempts.filter(row=>row.record==='writing-tool-action');
  const failures=attempts.filter(row=>row.record==='writing-tool-failure'&&row.operation==='visual_render');
  const result=turnFailures({tool_failures:failures,actions});
  assert.equal(result.length,5);assert.ok(result.every(row=>!row.resolved_later&&row.error));
  const observed=turnFailures({tool_failures:failures.map(row=>({...row,resolved_later:true})),actions});
  assert.ok(observed.every(row=>!row.resolved_later&&row.error));assert.ok(failures.every(row=>row.resolved_later===undefined),'Raw historical records are not rewritten.');
  assert.equal(turnFailures({tool_failures:[{...failures[0],payload:{id:'different-figure'}}],actions})[0].resolved_later,false);
  assert.equal(turnFailures({tool_failures:[{...failures[0],payload:{}}],actions})[0].resolved_later,false);
});

test('matched original read evidence is carried from backend without local retry inference',()=>{
  const recovery={read_id:'READ-one',operation:'help',basis:'Same retained help selector',recovers_read_goal:true,task_completion_inferred:false,read_handle:{operation:'author_history',payload:{view:'record',id:'activity:journal:READ-one'}}};
  const turn={tool_failures:[{id:'FAIL-one',operation:'help',error:'selector rejected',resolved_later:true,recovery_read:recovery}]};
  assert.deepEqual(turnFailures(turn)[0].recovery_read,recovery);assert.equal(turnFailures(turn)[0].resolved_later,true);assert.equal(turnFailures({tool_failures:[{...turn.tool_failures[0],recovery_read:{...recovery,recovers_read_goal:false}}]})[0].resolved_later,false);
  assert.equal(turnFailures({tool_failures:[{...turn.tool_failures[0],resolved_later:undefined}],actions:[{operation:'help'}]})[0].resolved_later,true);
});

test('an exact queue version opens its own comparison despite a terminal latest slot',async()=>{
  const seen=[];
  const session={onReviewProposal:(...args)=>seen.push(args)};
  await WorkspaceSession.prototype.reviewSavedProposal.call(session,'WT-six-versions',{proposalVersion:'sha256:earlier',readHandle:{owner:'exact'}});
  assert.deepEqual(seen,[['WT-six-versions',{proposalVersion:'sha256:earlier',readHandle:{owner:'exact'},readOnly:false}]]);
});

beforeEach(()=>{
  const tabValues=new Map();globalThis.sessionStorage={getItem:key=>tabValues.get(key)??null,setItem:(key,value)=>tabValues.set(key,String(value)),removeItem:key=>tabValues.delete(key)};
  const values=new Map();
  globalThis.localStorage={getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,String(value)),removeItem:key=>values.delete(key)};
  if(!globalThis.crypto)Object.defineProperty(globalThis,'crypto',{value:webcrypto,configurable:true});
});

const reply=(mode='discuss',role='author')=>({session:{role,provider:'codex',model:'model',effort:'medium'},turns:[{mode,text:'Previous message'}]});
const response=value=>({ok:true,headers:{get:()=> 'application/json'},json:async()=>value});

test('explicit state reads return failed domain state while HTTP and mutation errors still reject',async()=>{
 const state={ok:false,reason:'The last recompile failed — see log tail',log_tail:'! Missing $ inserted.'};globalThis.fetch=async()=>response(state);
 assert.equal(await projectRequest('/authoring/build?project=fixture',undefined,{allowStateError:true}),state);
 await assert.rejects(projectRequest('/authoring/build?project=fixture'),/last recompile failed/);
 await assert.rejects(projectRequest('/authoring/build',{project:'fixture'}),/last recompile failed/);
 await assert.rejects(projectRequest('/authoring/build',{project:'fixture'},{allowStateError:true}),/last recompile failed/);
 globalThis.fetch=async()=>({...response(state),ok:false,status:503});await assert.rejects(projectRequest('/authoring/build?project=fixture',undefined,{allowStateError:true}),/last recompile failed/);
});

// Exercise the controller against controlled asynchronous API replies. Browser
// selection and page-reload persistence are also checked on the live workspace.
function fixture(session='existing'){
  const controller=Object.create(WorkspaceSession.prototype);
  Object.assign(controller,{providers:[],queued:[],project:'book',session,role:'author',active:'',sessionLoad:0,modeRevision:0,settingsRevision:0,settingsSave:Promise.resolve(),
    activeCapabilities:{can_interrupt:true,can_steer:true,input_delivery_modes:['native_rpc'],observation:'events'},key:'laplace:session:book',draftKey:'laplace:compose:book',ready:Promise.resolve(),selectionOverride:null});
  const elements=new Map();
  for(const selector of ['[data-mode]','[data-provider]','[data-model]','[data-effort]','[data-sessions]','[data-thread]','[data-message]']){
    elements.set(selector,{value:'',childNodes:[],scrollTop:0,scrollHeight:0,replaceChildren(){},focus(){}});
  }
  elements.get('[data-mode]').value='discuss';
  controller.find=selector=>elements.get(selector);
  controller.models=value=>{if(value)elements.get('[data-model]').value=value;};controller.efforts=value=>{if(value)elements.get('[data-effort]').value=value;};controller.appendTurn=()=>{};controller.summary=()=>{};
  controller.paintSessions=()=>{};controller.status=()=>{};controller.empty=()=>{};controller.scope=()=>{};
  // Isolated settings/send tests do not render, but message() returns a row in the real controller.
  controller.message=()=>({dataset:{}});controller.authorMessage=()=>({dataset:{}});controller.setBusy=()=>{};controller.getContext=()=>({surface:'project'});
  controller.loadQueue=async()=>{};
  controller.connect=id=>{controller.active=id;};
  return controller;
}

test('author conversations reopen in ordinary work mode',async()=>{
  globalThis.fetch=async()=>response(reply());
  const current=fixture();current.rememberMode('work');
  await current.loadSession();
  assert.equal(current.find('[data-mode]').value,'work');
  const reopened=fixture();await reopened.loadSession();
  assert.equal(reopened.find('[data-mode]').value,'work');
  const other=fixture('different');await other.loadSession();
  assert.equal(other.find('[data-mode]').value,'work');
});

test('a mode change made during an in-flight session refresh wins over historical mode',async()=>{
  let resolve;
  globalThis.fetch=()=>new Promise(done=>{resolve=done;});
  const current=fixture();const pending=current.loadSession();
  current.rememberMode('work');
  resolve(response(reply()));await pending;
  assert.equal(current.find('[data-mode]').value,'work');
});

test('late session response cannot restore a conversation after New conversation',async()=>{
  let resolve;
  globalThis.fetch=()=>new Promise(done=>{resolve=done;});
  const current=fixture();const pending=current.loadSession();
  current.rememberMode('work');current.newConversation();
  resolve(response(reply('review','review')));await pending;
  assert.equal(current.session,'');assert.equal(current.role,'author');
  assert.equal(current.find('[data-mode]').value,'work');
});

test('review conversations remain reviews and changing to work starts a separate conversation',async()=>{
  globalThis.fetch=async()=>response(reply('review','review'));
  const current=fixture();current.rememberMode('work');await current.loadSession();
  assert.equal(current.find('[data-mode]').value,'review');
  current.compose('Develop the project.','work');
  assert.equal(current.session,'');assert.equal(current.role,'author');
  assert.equal(current.find('[data-mode]').value,'work');
});

test('sending after a reconnect submits work mode in the existing conversation',async()=>{
  let submitted;
  globalThis.fetch=async(path,options)=>{
    if(options.method==='POST'){
      submitted=JSON.parse(options.body);
      return response({session_id:'existing',turn_id:'new-turn'});
    }
    return response(reply());
  };
  const current=fixture();current.rememberMode('work');await current.loadSession();
  current.find('[data-message]').value='Develop this question.';
  await current.send();
  assert.equal(submitted.mode,'work');assert.equal(submitted.session_id,'existing');
  assert.equal(current.active,'new-turn');assert.equal(current.savedMode(),'work');
});

test('explicit next-message save keeps the conversation and draft after staged model and effort changes',async()=>{
 const f=await pilotSessionFixture();try{const current=f.current;await f.open();current.find('[data-message]').value='My continuing thought';
 current.find('[data-model]').value='different-model';await current.find('[data-model]').onchange();current.find('[data-effort]').value='high';await current.find('[data-effort]').onchange();
 assert.equal(f.calls.filter(r=>r.method==='POST').length,0);await f.button('Save next-message preferences').onclick();
 const writes=f.calls.filter(r=>r.method==='POST');assert.equal(writes.length,1);assert.equal(writes[0].payload.target.session_id,'existing');assert.equal(writes[0].payload.values.model,'different-model');assert.equal(writes[0].payload.values.effort,'high');
 assert.equal(current.session,'existing');assert.equal(current.find('[data-message]').value,'My continuing thought');await current.loadSession();assert.equal(current.find('[data-model]').value,'different-model');assert.equal(current.find('[data-effort]').value,'high');}finally{f.close();}
});

test('new conversation settings are local choices before any session is admitted',async()=>{
 const f=await pilotSessionFixture({initialSession:''});try{const current=f.current;await f.open();current.find('[data-model]').value='gpt-6-luna';await current.find('[data-model]').onchange();current.find('[data-effort]').value='low';await current.find('[data-effort]').onchange();await f.button('Keep new conversation choices').onclick();
 assert.match(current.find('[data-settings-truth]').textContent,/Next-message settings: gpt-6-luna.*effort low/);assert.equal(current.session,'');assert.equal(f.calls.filter(r=>r.method==='POST').length,0);assert.match(f.host.textContent,/no conversation admitted/);}finally{f.close();}
});

test('admitted settings come from the exact turn rather than mutable session preferences',()=>{
 const current=fixture(),label={textContent:''},find=current.find;current.find=selector=>selector==='[data-settings-truth]'?label:find(selector);
 current.active='exact-turn';current.find('[data-provider]').value='claude';current.find('[data-model]').value='haiku';current.find('[data-effort]').value='medium';current.effortSupported=false;
 current.acceptObservation({session:{id:'existing',model:'different-next-model'},active:{id:'exact-turn',capabilities:{}},turns:[{id:'other-turn',provider_settings:{model:'wrong'}},{id:'exact-turn',provider_settings:{provider:'codex',model:'gpt-6-luna',effort:'low'}}]},'exact-turn');
 assert.match(label.textContent,/Admitted turn settings: gpt-6-luna.*effort low/);assert.match(label.textContent,/Next-message settings: haiku.*effort Automatic/);assert.ok(!label.textContent.includes('different-next-model'));
});

test('discussion, development and revision composition retain one conversation',()=>{
  const current=fixture();
  for(const mode of ['discuss','work','revise','discuss']){
    current.compose('',mode);assert.equal(current.session,'existing');assert.equal(current.savedMode(),mode);
  }
});

test('rapid local settings choices produce one deliberate save and retain the latest staged effort',async()=>{
 const f=await pilotSessionFixture();try{const current=f.current;await f.open();current.find('[data-effort]').value='low';await current.find('[data-effort]').onchange();current.find('[data-effort]').value='high';await current.find('[data-effort]').onchange();
 assert.equal(f.calls.filter(r=>r.method==='POST').length,0);await f.button('Save next-message preferences').onclick();const writes=f.calls.filter(r=>r.method==='POST');assert.deepEqual(writes.map(r=>r.payload.values.effort),['high']);assert.equal(current.find('[data-effort]').value,'high');assert.equal(current.session,'existing');}finally{f.close();}
});

test('uncertain settings save refuses Send; only explicit Check and original-wire Retry may recover',async()=>{
 let fail=true;const f=await pilotSessionFixture({change:async()=>{if(fail){fail=false;return new Response(JSON.stringify({error:'Temporarily unavailable'}),{status:503,headers:{'content-type':'application/json'}});}}});
 try{const current=f.current;await f.open();current.find('[data-effort]').value='high';await current.find('[data-effort]').onchange();await assert.rejects(current.savePreferences(),/Temporarily unavailable/);
 const key=current.settingsKey(),wire=JSON.parse(localStorage.getItem(key)).pilot_preferences.pending.wire;current.find('[data-message]').value='Continue this discussion.';await assert.rejects(current.send(),/original settings save/);await f.guards.at(-1);assert.equal(f.calls.filter(r=>r.method==='POST').length,1);
 await f.button('Check original save').onclick();await f.button('Retry original save').onclick();const writes=f.calls.filter(r=>r.method==='POST');assert.equal(writes.length,2);assert.deepEqual(writes.map(r=>r.payload),[JSON.parse(wire),JSON.parse(wire)]);assert.equal(current.session,'existing');assert.equal(current.find('[data-message]').value,'Continue this discussion.');assert.ok(!f.calls.some(r=>r.path==='/authoring/turn'));assert.equal(JSON.parse(localStorage.getItem(key)).pilot_preferences.pending,null);}finally{f.close();}
});

test('historical revision mode cannot silently constrain a reopened author conversation',async()=>{
  globalThis.fetch=async()=>response(reply('revise'));
  const current=fixture();current.rememberMode('revise');
  await current.loadSession();
  assert.equal(current.find('[data-mode]').value,'work');
});


test('queued passage requests are included once on Send while underway work stays out',async()=>{
  let submitted;globalThis.fetch=async(path,options)=>{submitted=JSON.parse(options.body);return response({session_id:'existing',turn_id:'queued-turn'});};
  const current=fixture();current.queued=[{id:'ready-request',status:'ready'},{id:'open-request',status:'open'},{id:'underway-request',status:'in-progress'}];
  await current.send();
  assert.deepEqual(submitted.queued_work_ids,['ready-request','open-request']);
  assert.match(submitted.text,/queued requests/);assert.equal(submitted.session_id,'existing');
});

test('switching to an unreported provider clears usage and capacity from the prior provider',()=>{
  const current=fixture(),label={textContent:''},bar={hidden:true};const originalFind=current.find;
  current.find=selector=>selector==='[data-context-label]'?label:selector==='[data-context-progress]'?bar:originalFind(selector);
  current.showUsage({thread_token_usage:{modelContextWindow:1050000,last:{totalTokens:10000}}},{});
  assert.match(label.textContent,/1,050k/);assert.equal(bar.hidden,true);
  current.find('[data-provider]').value='claude';current.find('[data-model]').value='configured';current.providers=[{id:'claude',models:[{id:'configured'}]}];
  current.resetUsage();assert.equal(label.textContent,'Context usage available after the session starts');assert.equal(bar.hidden,true);
});

test('recovered applied edits are offered to the existing manuscript history',async()=>{
  const current=fixture(),seen=[];current.appendTurn=WorkspaceSession.prototype.appendTurn;current.onApplication=application=>{seen.push(application);};
  const application={id:'applied-once',edits:[{file:'main.tex',line_start:2,before:'Old.',after:'New.'}]};
  WorkspaceSession.prototype.appendTurn.call(current,{text:'Revise the passage',application});
  await Promise.resolve();assert.deepEqual(seen,[application]);
});

test('a model without effort controls stays disabled after the reply completes',()=>{
  const originalDocument=globalThis.document;
  globalThis.document={createElement:()=>({value:'',textContent:''})};
  try{
    const current=Object.create(WorkspaceSession.prototype),fields=new Map();
    current.find=selector=>{if(!fields.has(selector))fields.set(selector,{value:'',parentElement:{hidden:false},replaceChildren(...children){this.options=children;}});return fields.get(selector);};
    current.providers=[{id:'claude',models:[{id:'haiku',supports_effort:false,efforts:[]},{id:'opus',supports_effort:true,efforts:['low','medium','high']}]}];
    current.active='';current.summary=()=>{};current.find('[data-provider]').value='claude';current.find('[data-model]').value='haiku';
    current.efforts('high');current.setBusy(true);current.setBusy(false);
    assert.equal(current.find('[data-effort]').disabled,true);
    assert.equal(current.find('[data-effort]').parentElement.hidden,true);
    current.find('[data-model]').value='opus';current.efforts('high');current.setBusy(false);
    assert.equal(current.find('[data-effort]').disabled,false);
    assert.equal(current.find('[data-effort]').parentElement.hidden,false);
    assert.equal(current.find('[data-effort]').value,'high');
  }finally{globalThis.document=originalDocument;}
});


test('saved provider denials and tool failures remain distinct from successful actions',()=>{
  const turn={actions:[{operation:'note'}],tool_failures:[{id:'fail-1',operation:'source',error:'Permission unavailable'}],reply:{status:'completed',provider_issues:[{operation:'source',reason:'Permission unavailable'},{operation:'proof_check',reason:'Declaration missing'}]}};
  assert.deepEqual(turnFailures(turn).map(row=>[row.operation,row.error]),[['source','Permission unavailable'],['proof_check','Declaration missing']]);
  assert.equal(turn.actions.length,1);
});


test('shared argument scope sends canonical member identities in new and resumed requests',async()=>{
 for(const active of ['', 'running-turn']){
  const current=fixture('continuing-session');current.active=active;current.find('[data-provider]').value='codex';current.find('[data-message]').value='Work through this group.';current.getContext=()=>({surface:'structure',label:'Shared prerequisites',node_ids:['def:finite','thm:cost']});let sent;
  globalThis.fetch=async(path,options)=>{sent={path,payload:JSON.parse(options.body)};return response({session_id:'continuing-session',turn_id:'next-turn'});};
  current.pinMessageTarget(current.getContext());await current.send();assert.deepEqual(sent.payload.workspace_context.node_ids,['def:finite','thm:cost']);assert.equal(sent.payload.workspace_context.node_id,null);assert.equal(sent.payload.workspace_context.label,'Shared prerequisites');assert.equal(sent.path,active?'/authoring/steer':'/authoring/turn');
 }
});
test('discussion of an accepted comparison sends exact review identity and affected source without stale node focus',async()=>{
 for(const active of ['', 'running-turn']){const current=fixture('continuing-session');current.active=active;current.find('[data-provider]').value='codex';current.find('[data-message]').value='Explain this accepted edit.';current.getContext=()=>({surface:'review',label:'Accepted comparison · two.tex',selection:{files:['chapters/two.tex']},review:{turn_id:'WT-two',application_ids:['WA-two']}});let sent;globalThis.fetch=async(path,options)=>{sent={path,payload:JSON.parse(options.body)};return response({session_id:'continuing-session',turn_id:'new-turn'});};current.pinMessageTarget(current.getContext());await current.send();assert.equal(sent.payload.workspace_context.surface,'review');assert.equal(sent.payload.workspace_context.label,'Accepted comparison · two.tex');assert.deepEqual(sent.payload.workspace_context.review,{turn_id:'WT-two',application_ids:['WA-two']});assert.deepEqual(sent.payload.selection,{files:['chapters/two.tex']});assert.equal(sent.payload.workspace_context.node_id,undefined);}
});

test('passive cold catalogue preserves the saved model identity',()=>{
  const original=globalThis.document;globalThis.document={createElement:()=>({value:'',textContent:''})};
  try{const current=fixture();current.providers=[{id:'claude',models:[{id:'',name:'Configured model',default:true}]}];current.preferences={provider:'claude',model:'claude-fable-5-1'};current.find('[data-provider]').value='claude';const model=current.find('[data-model]');model.options=[];model.append=option=>model.options.push(option);
    WorkspaceSession.prototype.models.call(current);
    assert.equal(model.value,'claude-fable-5-1');assert.ok(model.options.some(option=>option.value==='claude-fable-5-1'));
  }finally{globalThis.document=original;}
});

test('Send waits for scoped saving and uses an explicit prepared source span',async()=>{
  let release,posted;const current=fixture();let line=4;
  current.find('[data-message]').value='Discuss my latest sentence.';
  current.getContext=()=>({surface:'manuscript',selection:{files:['main.tex'],line_start:line,line_end:line}});
  current.prepareSend=()=>new Promise(done=>{release=()=>{line=7;done({selection:{files:['main.tex'],line_start:line,line_end:line}});};});
  globalThis.fetch=async(path,options)=>{posted=JSON.parse(options.body);return response({session_id:'existing',turn_id:'new-turn'});};
  current.pinMessageTarget(current.getContext());const pending=current.send();while(!release)await Promise.resolve();
  assert.equal(posted,undefined);current.find('[data-message]').value='Another thought while saving';release();await pending;
  assert.equal(posted.selection.line_start,7);assert.equal(posted.text,'Discuss my latest sentence.');assert.equal(current.find('[data-message]').value,'Another thought while saving');
});

test('Send and steer keep unsaved source explicitly separate from the persisted selection',async()=>{
  for(const active of ['', 'active-turn']){
    let posted;const current=fixture();current.active=active;current.find('[data-provider]').value='codex';current.find('[data-message]').value='Discuss this draft.';
    const draft={status:'UNSAVED',format:'tex',text:'\\bad{draft',anchor:{file:'main.tex',line_start:3,line_end:3},reason:'Source editor has unsaved text.'};
    current.prepareSend=async()=>({selection:{files:['main.tex'],line_start:3,line_end:3,draft}});
    globalThis.fetch=async(path,options)=>{posted=JSON.parse(options.body);return response({session_id:'existing',turn_id:'new-turn'});};
    await current.send();assert.deepEqual(posted.selection.draft,draft);
  }
});

test('reopening a conversation offers compact structural receipts to the common history',()=>{
  const current=fixture(),seen=[];current.appendTurn=WorkspaceSession.prototype.appendTurn;current.onApplication=application=>seen.push(application);current.guard=fn=>fn();current.actions=()=>{};current.failures=()=>{};current.proposal=()=>{};current.facets=()=>{};current.message=()=>({dataset:{}});
  const undo_ref={kind:'section',id:'MSC-example',project:'book'};
  current.appendTurn({id:'turn',text:'Create this heading.',actions:[{id:'action',operation:'section_change',outcome:{undo_ref}}],reply:{text:'Created.'}});
  assert.deepEqual(seen,[{id:'action',undo_ref}]);
});

test('advertised model capacity is not presented as an observed session context limit',()=>{
  const current=fixture(),label={},bar={};current.find=selector=>selector==='[data-context-label]'?label:bar;
  current.showUsage(null,{context_window_advertised:1050000});assert.match(label.textContent,/Advertised capacity/);assert.equal(bar.hidden,true);
  current.showUsage({thread_token_usage:{last:{totalTokens:1234},modelContextWindow:828400}},{context_window_advertised:1050000});assert.match(label.textContent,/828\.4k/);assert.doesNotMatch(label.textContent,/1,050k/);assert.equal(bar.hidden,true);
});

test('saved unsaved-draft attachments remain visible after reopening the conversation',()=>{
  const current=fixture(),seen=[];current.appendTurn=WorkspaceSession.prototype.appendTurn;current.authorMessage=(text,selection)=>seen.push({text,selection});current.actions=()=>{};current.failures=()=>{};current.proposal=()=>{};current.message=()=>({dataset:{}});
  const draft={status:'UNSAVED',format:'tex',text:'\\invalid{',anchor:{file:'main.tex',line_start:3,line_end:3},reason:'Not saved'};
  current.appendTurn({text:'Discuss this.',selection:{files:['main.tex']},unsaved_draft:draft,reply:{text:'Received.'}});assert.deepEqual(seen[0].selection.draft,draft);
});

function catalogueFixture(){
  const current=fixture(),originalFind=current.find,extras=new Map();
  for(const selector of ['[data-provider]','[data-model]','[data-effort]']){const element=originalFind(selector);element.options=[];element.replaceChildren=(...options)=>{element.options=options;};element.append=option=>element.options.push(option);element.parentElement={};}
  current.find=selector=>originalFind(selector)||extras.get(selector)||(extras.set(selector,{}),extras.get(selector));
  current.models=WorkspaceSession.prototype.models;current.efforts=WorkspaceSession.prototype.efforts;
  current.preferences={provider:'claude',model:'claude-fable-5-1',effort:'high'};
  current.find('[data-provider]').value='claude';current.find('[data-model]').value='claude-fable-5-1';current.find('[data-effort]').value='high';current.find('[data-message]').value='Keep this draft.';
  return current;
}
const fullCatalogue=[{id:'claude',name:'Claude',available:true,models:[{id:'default',name:'Default',default:true,efforts:['low','medium','high']},{id:'claude-fable-5-1',name:'Fable',efforts:['low','medium','high']},{id:'sonnet',name:'Sonnet',efforts:['low','medium','high']}]},{id:'codex',name:'Codex',available:true,models:[{id:'gpt-5.6-luna',name:'Luna',default:true,efforts:['low','medium','high']}]}];

test('opening provider controls passively receives new cached models without changing choices or draft',async()=>{
  const original=globalThis.document;try{globalThis.document={createElement:()=>({value:'',textContent:''})};const current=catalogueFixture(),paths=[];globalThis.fetch=async(path,options)=>{paths.push({path,method:options.method});return response({providers:fullCatalogue});};await current.refreshProvidersPassive({force:true});assert.deepEqual(paths,[{path:'/authoring/providers',method:'GET'}]);assert.equal(current.find('[data-model]').options.length,3);assert.equal(current.find('[data-model]').value,'claude-fable-5-1');assert.equal(current.find('[data-effort]').value,'high');assert.equal(current.find('[data-message]').value,'Keep this draft.');assert.equal(current.session,'existing');}finally{globalThis.document=original;}
});

test('passive catalogue gestures coalesce and a newer selection wins over the in-flight response',async()=>{
  const original=globalThis.document;try{globalThis.document={createElement:()=>({value:'',textContent:''})};const current=catalogueFixture();let release,count=0;globalThis.fetch=()=>{count++;return new Promise(resolve=>{release=()=>resolve(response({providers:fullCatalogue}));});};const first=current.refreshProvidersPassive({force:true}),second=current.refreshProvidersPassive();await Promise.resolve();current.find('[data-provider]').value='codex';current.find('[data-model]').value='gpt-5.6-luna';current.find('[data-effort]').value='low';release();await Promise.all([first,second]);assert.equal(count,1);assert.equal(current.find('[data-provider]').value,'codex');assert.equal(current.find('[data-model]').value,'gpt-5.6-luna');assert.equal(current.find('[data-effort]').value,'low');await current.refreshProvidersPassive();assert.equal(count,1);}finally{globalThis.document=original;}
});

test('passive refresh retains an explicit configured-model choice and only explicit refresh probes metadata',async()=>{
  const original=globalThis.document;try{globalThis.document={createElement:()=>({value:'',textContent:''})};const current=catalogueFixture();current.find('[data-model]').value='';const paths=[];globalThis.fetch=async path=>{paths.push(path);return response({providers:fullCatalogue});};await current.refreshProvidersPassive({force:true});assert.equal(current.find('[data-model]').value,'');assert.ok(current.find('[data-model]').options.some(option=>option.value==='claude-fable-5-1'));await current.loadProviders(true);assert.deepEqual(paths,['/authoring/providers','/authoring/providers?refresh=1']);}finally{globalThis.document=original;}
});

test('sending clears only this tab and cannot adopt or erase another conversation draft',async()=>{
 const current=fixture('codex');current.find('[data-message]').value='Sent thought';current.persistComposerDraft('Sent thought');
 globalThis.fetch=async()=>{localStorage.setItem(current.draftKey+':conversation:claude','Another task');return response({session_id:'codex',turn_id:'next'});};
 await current.send();assert.equal(localStorage.getItem(current.draftKey+':conversation:claude'),'Another task');assert.equal(current.find('[data-message]').value,'');assert.equal(sessionStorage.getItem(current.composerBackupKey()),'');
});
test('a local explicit clear survives refresh and does not overwrite unreported typing',()=>{
 const current=fixture();current.persistComposerDraft('Old QA text');current.find('[data-message]').value='Old QA text';sessionStorage.setItem(current.composerBackupKey(),'');
 current.compose('');assert.equal(current.find('[data-message]').value,'');
 current.find('[data-message]').value='New text not yet stored';current.composerStored='';current.syncComposerDraft({allowFocused:true});assert.equal(current.find('[data-message]').value,'New text not yet stored');
});
test('two tab buffers remain separate across reload and intentional session switching preserves this tab',()=>{
 const a=sessionStorage,first=fixture('codex');first.persistComposerDraft('Revise chapter one');first.find('[data-message]').value='Revise chapter one';
 const values=new Map(),b={getItem:k=>values.get(k)??null,setItem:(k,v)=>values.set(k,String(v))};globalThis.sessionStorage=b;
 const second=fixture('claude');assert.equal(second.readComposerDraft(),'');second.persistComposerDraft('Find the primary source');second.find('[data-message]').value='Find the primary source';
 first.syncComposerDraft();assert.equal(first.find('[data-message]').value,'Revise chapter one');
 const reloadB=fixture('claude');assert.equal(reloadB.readComposerDraft(),'Find the primary source');globalThis.sessionStorage=a;const reloadA=fixture('codex');assert.equal(reloadA.readComposerDraft(),'Revise chapter one');
 first.switchDraftTarget('claude');first.session='claude';assert.equal(first.find('[data-message]').value,'Find the primary source');first.switchDraftTarget('codex');first.session='codex';assert.equal(first.find('[data-message]').value,'Revise chapter one');
});
test('reopened tabs recover only their conversation backup and preserve unidentified legacy drafts',()=>{
 const current=fixture('codex');localStorage.setItem(current.draftKey,'Legacy message of unknown target');localStorage.setItem(current.draftKey+':conversation:claude','Claude only');
 assert.equal(current.readComposerDraft(),'');assert.equal(current.legacyComposerDraft,'Legacy message of unknown target');assert.equal(localStorage.getItem(current.draftKey),current.legacyComposerDraft);
 sessionStorage.removeItem(current.composerBackupKey());const claude=fixture('claude');assert.equal(claude.readComposerDraft(),'Claude only');
});
test('message storage failures remain visible without clearing the editable draft',()=>{
 const current=fixture(),statuses=[];current.status=(message,error)=>statuses.push({message,error});current.find('[data-message]').value='Keep these words';localStorage.setItem=()=>{throw Error('quota exceeded');};
 assert.equal(current.persistComposerDraft('Keep these words'),false);assert.equal(current.find('[data-message]').value,'Keep these words');assert.match(statuses[0].message,/browser storage/i);assert.equal(statuses[0].error,true);
});


test('streaming preserves chunks within one message and separates native message starts exactly once',()=>{
 let text=appendStreamText('','The arch',true);text=appendStreamText(text,'itecture.');text=appendStreamText(text,'The Wigner',true);text=appendStreamText(text,' source.');assert.equal(text,'The architecture.\n\nThe Wigner source.');assert.equal(appendStreamText('A.\n','B.',true),'A.\n\nB.');assert.equal(appendStreamText('A.\n\n','B.',true),'A.\n\nB.');
});
test('saved project artifact links preserve exact paths and reject executable/file URI links',()=>{
 const parts=messageLinkParts('Saved [reading record](</home/author/My Project/research/reading.md>).');assert.equal(parts[1].kind,'artifact');assert.equal(parts[1].target,'/home/author/My Project/research/reading.md');
 assert.deepEqual(messageLinkParts('[bad](javascript:alert(1))').map(part=>part.kind).filter(Boolean),[]);assert.deepEqual(messageLinkParts('[bad](file:///etc/passwd)').map(part=>part.kind).filter(Boolean),[]);
 assert.ok(messageLinkParts('`[literal](research/a.md)` and $[A](x/y)$').every(part=>part.text!=null));
});

function messageNode(tag){return {tag,children:[],dataset:{},textContent:'',className:'',classList:{add(){},remove(){}},append(...nodes){this.children.push(...nodes);},replaceChildren(...nodes){this.children=nodes;},querySelector(selector){return this.children.find(node=>node.className===selector.slice(1));}};}

test('failed attempts are collapsed as historical records without asserting recovery',()=>{
 const original=globalThis.document;try{globalThis.document={createElement:messageNode};const current=fixture(),row=messageNode('article'),attempts=Array.from({length:34},(_,index)=>({id:'failure-'+index,operation:'source',error:'Exact error '+index}));
 WorkspaceSession.prototype.failures.call(current,row,{reply:{status:'completed'},actions:[{operation:'source'}],tool_failures:attempts});const box=row.children[0];assert.equal(box.tag,'details');assert.ok(!box.open);assert.equal(box.children[0].textContent,'34 operations failed without a recorded successful retry');assert.equal(box.children.filter(node=>node.tag==='article').length,0);
 box.open=true;box.ontoggle();const list=box.children[1],more=box.children[2];assert.equal(list.children.length,20);const detail=list.children[0].children[2];assert.equal(detail.children.length,1);detail.open=true;detail.ontoggle();let followup;current.compose=text=>{followup=text;};detail.children.at(-1).onclick();assert.match(followup,/whether later actions addressed it/);assert.match(followup,/failure-0/);more.onclick();assert.equal(list.children.length,34);assert.equal(more.hidden,true);box.open=false;box.ontoggle();box.open=true;box.ontoggle();assert.equal(list.children.length,34);
 }finally{globalThis.document=original;}
});
test('hundreds of saved actions build no closed rows or receipt JSON and remain exactly inspectable in pages',()=>{
 const original=globalThis.document;try{let nodes=0,receiptReads=0;globalThis.document={createElement:tag=>{nodes++;return messageNode(tag);}};const current=fixture(),row=messageNode('article'),seen=[];current.onInspect=action=>seen.push(action);
 const actions=Array.from({length:516},(_,index)=>({id:'action-'+index,operation:'apply_revision',outcome:{status:'SUCCEEDED',identities:['claim:'+index],get receipts(){receiptReads++;return ['receipt-'+index];}}}));
 WorkspaceSession.prototype.actions.call(current,row,actions);assert.equal(nodes,2);assert.equal(receiptReads,0);const box=row.children[0];box.open=true;box.ontoggle();const list=box.children[1],more=box.children[2];assert.equal(list.children.length,20);assert.equal(receiptReads,0);list.children[0].children.find(child=>child.tag==='button').onclick();assert.equal(seen[0],actions[0]);
 const detail=list.children[0].children.find(child=>child.tag==='details');detail.open=true;detail.ontoggle();assert.equal(receiptReads,1);assert.match(detail.children[1].textContent,/receipt-0/);detail.open=false;detail.ontoggle();detail.open=true;detail.ontoggle();assert.equal(receiptReads,1);
 while(!more.hidden)more.onclick();assert.equal(list.children.length,516);list.children.at(-1).children.find(child=>child.tag==='button').onclick();assert.equal(seen[1],actions[515]);assert.equal(receiptReads,1);
 }finally{globalThis.document=original;}
});
test('equal errors from distinct saved attempts retain their identities while provider projections deduplicate',()=>{
 const failures=turnFailures({tool_failures:[{id:'first',operation:'source',error:'Retry required'},{id:'second',operation:'source',error:'Retry required'}],reply:{provider_issues:[{operation:'source',reason:'Retry required'}]}});assert.deepEqual(failures.map(row=>row.id),['first','second']);
});
test('completion posture follows the actual turn, not the existence of failed attempts',()=>{
 assert.deepEqual(turnCompletionStatus({status:'completed'},true),{text:'Reply saved. Failed attempts are available in this reply’s history.',error:false});assert.equal(turnCompletionStatus({status:'failed'},true).error,true);assert.match(turnCompletionStatus({status:'interrupted'},true).text,/partial reply/);
});
test('saved replies opt into formatted reading while live messages retain chunk text',async()=>{
 const original=globalThis.document;try{globalThis.document={createElement:messageNode,createTextNode:text=>({textContent:text})};const current=fixture(),thread=messageNode('section'),calls=[];current.find=selector=>selector==='[data-thread]'?thread:null;current.renderFinalMessage=(body,text)=>{calls.push(text);body.replaceChildren({textContent:'Rendered '+text});};current.message=WorkspaceSession.prototype.message;
 const live=current.message('assistant','**Partial');assert.equal(calls.length,0);assert.equal(live.querySelector('.session-body').children[0].textContent,'**Partial');
 const saved=current.message('assistant','**Complete**',{formatted:true});await saved.rendered;assert.deepEqual(calls,['**Complete**']);assert.equal(saved.querySelector('.session-body').children[0].textContent,'Rendered **Complete**');
 }finally{globalThis.document=original;}
});
test('a formatted-view failure retains the exact original saved reply',async()=>{
 const original=globalThis.document;try{globalThis.document={createElement:messageNode,createTextNode:text=>({textContent:text})};const current=fixture(),thread=messageNode('section');current.find=selector=>selector==='[data-thread]'?thread:null;current.renderFinalMessage=async()=>{throw Error('Renderer unavailable');};const text=String.raw`Exact μ*=T(μ*) ~ V_d and \(x\)`;const saved=WorkspaceSession.prototype.message.call(current,'assistant',text,{formatted:true});await saved.rendered;assert.equal(saved.querySelector('.session-body').textContent,text);assert.match(saved.children.at(-1).textContent,/original reply shown/);
 }finally{globalThis.document=original;}
});

test('native paragraph separator deltas do not double the frontend message boundary',()=>{
 assert.equal(appendStreamText('First.','\n\n',true),'First.\n\n');assert.equal(appendStreamText('First.\n','\n',true),'First.\n\n');assert.equal(appendStreamText('First.','\nSecond.',true),'First.\n\nSecond.');assert.equal(appendStreamText('First.\n\n','Second.',true),'First.\n\nSecond.');
 let text=appendStreamText('First.','\n\n',true);text=appendStreamText(text,'Sec');text=appendStreamText(text,'ond.');assert.equal(text,'First.\n\nSecond.');assert.equal(appendStreamText('First.','Second.',true),'First.\n\nSecond.');
});

test('selected conversation work link consumes banked owner work_id and never derives it from words',async()=>{
 const current=fixture('existing'),associated=[];current.onWorkAssociation=async(id,isCurrent)=>{assert.equal(isCurrent(),true);associated.push(id);};globalThis.fetch=async()=>response({session:{id:'existing',project:'book',provider:'codex',model:'model',effort:'medium'},turns:[{id:'WT-owned',text:'Ignore this misleading work label',work_id:'WORK-owner-exact'}],active:null});await current.loadSession();assert.deepEqual(associated,['WORK-owner-exact']);
});

test('fresh file-only context is labelled as source files without inventing a passage',()=>{
 const chip={},label={},clear={},nodes={'[data-selection-chip]':chip,'[data-selection-label]':label,'[data-clear-selection]':clear};
 const view={selectionOverride:{files:['chapters/chapter01.tex']},find:key=>nodes[key]};
 WorkspaceSession.prototype.paintSelection.call(view);
 assert.equal(label.textContent,'Source files: chapters/chapter01.tex');assert.equal(clear.ariaLabel,'Remove source files');assert.equal(chip.hidden,false);
 view.selectionOverride={quote:'Current selected prose',anchor:{file:'chapters/chapter01.tex',line_start:2}};
 WorkspaceSession.prototype.paintSelection.call(view);assert.equal(label.textContent,'Attached passage: Current selected prose');assert.equal(clear.ariaLabel,'Remove attached passage');
});

test('repeating a review shortcut cannot discard author text appended to its reply draft',()=>{
 const current=fixture('reply-target'),request='Please reconcile the saved candidate.';
 const draft=request+'\n\nMy unsaved reasoning and caveat.';current.find('[data-message]').value=draft;current.persistComposerDraft(draft);
 current.compose(request,'work');assert.equal(current.find('[data-message]').value,draft);
 current.compose('Read the current file first.','work');assert.equal(current.find('[data-message]').value,draft+'\n\nRead the current file first.');
});

test('a dispatched child with no work_id aligns to its explicit dispatch owner',async()=>{
 const current=fixture('child'),associated=[];current.onWorkAssociation=async(id,isCurrent)=>{assert.equal(isCurrent(),true);associated.push(id);};
 globalThis.fetch=async()=>response({session:{id:'child',project:'book',provider:'codex',model:'model',effort:'medium',dispatch_id:'WORK-dispatch',packet:'judge',role:'review'},turns:[{id:'WT-child',text:'Read exact returns',work_id:null,dispatch_id:'WORK-dispatch',parent_turn_id:'WT-parent'}],active:null});
 await current.loadSession();assert.deepEqual(associated,['WORK-dispatch']);assert.equal(current.origin.parentTurnId,'WT-parent');assert.equal(current.role,'review');
});

test('source result destination uses an actual stored artifact payload and preserves its declared scope',async()=>{
 const {savedActionDestination,sessionWorkTarget}=await import('../src/laplace/web/static_shared/workspace-session.mjs');
 assert.deepEqual(savedActionDestination({operation:'store_artifact',payload:{path:'blueprint/result.json',scope:'project'},outcome:{paths:['other.json']}}),{kind:'artifact',path:'blueprint/result.json',scope:'project',artifactOwner:'writing-artifact'});
 assert.equal(savedActionDestination({operation:'store_artifact',payload:{path:'x',scope:'unknown'}}),null);
 assert.equal(savedActionDestination({operation:'unknown',outcome:{paths:['claimed.json']}}),null);
 assert.equal(sessionWorkTarget({active:{work_id:'WORK-active'},session:{dispatch_id:'WORK-older'},turns:[{work_id:'WORK-saved'}]}),'WORK-active');
});


test('active child dispatch target takes precedence over an unrelated historical work target',async()=>{
 const {sessionWorkTarget}=await import('../src/laplace/web/static_shared/workspace-session.mjs');
 assert.equal(sessionWorkTarget({active:{dispatch_id:'WORK-active-dispatch'},turns:[{work_id:'WORK-older'}]}),'WORK-active-dispatch');
});

test('queued request excluded for this message is not cancelled or silently recaptured during send',async()=>{
 const current=fixture(),sent=[];current.queued=[{id:'WORK-one',status:'ready'},{id:'WORK-two',status:'ready'}];current.queueExcluded=new Set(['WORK-one']);current.find('[data-message]').value='Inspect only the included request';current.loadQueue=async()=>{};current.loadSessions=async()=>{};
 globalThis.fetch=async(path,options)=>{sent.push({path,body:JSON.parse(options.body)});return response({session_id:'existing',turn_id:'WT-sent'});};
 await current.send();assert.equal(sent.length,1);assert.equal(sent[0].path,'/authoring/turn');assert.deepEqual(sent[0].body.queued_work_ids,['WORK-two']);
});

test('artifact route recognition rejects cross-project, external-origin and duplicate identity parameters',async()=>{
 const {artifactHumanTarget,messageLinkParts,savedActionDestination}=await import('../src/laplace/web/static_shared/workspace-session.mjs');const pin='c'.repeat(64),url='/research/artifact?'+new URLSearchParams({project:'book',scope:'project',path:'result with spaces.txt',expected_sha256:pin,artifact_id:'ART-one'});
 assert.equal(artifactHumanTarget(url,{project:'other'}),null);assert.equal(artifactHumanTarget('https://outside.example'+url,{project:'book'}),null);assert.equal(artifactHumanTarget(url+'&project=other',{project:'book'}),null);
 assert.equal(messageLinkParts(`[result](${url})`,{project:'book'})[0].kind,'human-artifact');
 assert.deepEqual(savedActionDestination({operation:'store_artifact',payload:{path:'incorrect.txt'},outcome:{human_read:{path:'exact.txt',scope:'manuscript',expected_sha256:pin,artifact_id:'ART-one'}}}),{kind:'artifact',path:'exact.txt',scope:'manuscript',expectedSha256:pin,artifactId:'ART-one'});
});

test('reading elsewhere preserves the authored source target through Send and reload',async()=>{
 const current=fixture(),reading={surface:'structure',label:'Reader intention',node_ids:['beat:a'],structure_observation:{plan_revision:'original-plan'}};
 current.getContext=()=>reading;current.find('[data-message]').value='Keep this exact request';current.pinMessageTarget(reading);
 reading.label='Unrelated inspection';reading.node_ids=['beat:other'];
 const encoded=sessionStorage.getItem(current.composerBackupKey());
 assert.deepEqual(decodeComposerDraft(encoded).intent.context.node_ids,['beat:a']);
 const reopened=fixture();reopened.composerSession='existing';reopened.find('[data-message]').value=reopened.readComposerDraft();
 assert.equal(reopened.find('[data-message]').value,'Keep this exact request');assert.deepEqual(reopened.authoredContext().node_ids,['beat:a']);
 let submitted;globalThis.fetch=async(_path,options)=>{submitted=JSON.parse(options.body);return response({session_id:'existing',turn_id:'WT-pinned'});};
 await reopened.send();assert.deepEqual(submitted.workspace_context.node_ids,['beat:a']);assert.equal(submitted.workspace_context.label,'Reader intention');
});

test('ordinary reading sends no attachment until the author chooses it',async()=>{
 const current=fixture();current.getContext=()=>({surface:'manuscript',label:'Reading only',selection:{files:['unrelated.tex']},task_id:'observed-work'});current.find('[data-message]').value='A project question';let submitted;
 globalThis.fetch=async(_path,options)=>{submitted=JSON.parse(options.body);return response({session_id:'existing',turn_id:'WT-neutral'});};
 await current.send();assert.equal(submitted.workspace_context.surface,'project');assert.equal(submitted.work_id,undefined);assert.equal(submitted.selection,undefined);
});

test('connected waiting is explicit per-draft author admission, outside the reading context, and consumed on acknowledgement',async()=>{
 const ordinary=fixture();ordinary.find('[data-mode]').value='work';ordinary.find('[data-message]').value='Ordinary author request';let sent;
 globalThis.fetch=async(_path,options)=>{sent=JSON.parse(options.body);return response({session_id:'existing',turn_id:'WT-ordinary'});};
 await ordinary.send();assert.equal(sent.connected_observation_seconds,undefined);assert.equal(connectedObservationSeconds(null),undefined);
 const current=fixture();current.find('[data-mode]').value='work';current.find('[data-message]').value='Finite connected observation';current.setConnectedObservation('300');
 const originalFind=current.find,extra=new Map(['[data-scope]','[data-message-target]','[data-clear-target]'].map(key=>[key,{}]));current.find=key=>originalFind(key)||extra.get(key);current.paintContext=()=>{};current.scope=WorkspaceSession.prototype.scope;
 current.pinMessageTarget({surface:'manuscript',selection:{files:['chapter.tex']}});current.clearSelection();assert.equal(current.messageIntent.connected_observation_seconds,300);
 current.clearMessageTarget();assert.equal(current.messageIntent.connected_observation_seconds,300);assert.equal(current.authoredContext().surface,'project');
 assert.equal(extra.get('[data-clear-target]').hidden,true);assert.match(extra.get('[data-message-target]').textContent,/no reading attached/);
 await current.send();assert.equal(sent.connected_observation_seconds,300);assert.equal(sent.workspace_context.connected_observation_seconds,undefined);assert.equal(current.messageIntent,null);assert.equal(current.find('[data-message]').value,'');
});

test('each conversation draft restores its own connected observation without applying a project default',()=>{
 const current=fixture();current.find('[data-mode]').value='work';current.find('[data-message]').value='A';current.setConnectedObservation('300');
 current.switchDraftTarget('other');assert.equal(current.messageIntent,null);current.find('[data-message]').value='B';current.setConnectedObservation('90');
 current.switchDraftTarget('existing');assert.equal(current.find('[data-message]').value,'A');assert.equal(current.messageIntent.connected_observation_seconds,300);
 current.switchDraftTarget('other');assert.equal(current.find('[data-message]').value,'B');assert.equal(current.messageIntent.connected_observation_seconds,90);
 current.setConnectedObservation('');assert.equal(connectedObservationSeconds(current.messageIntent),undefined);
});

test('invalid connected observation refuses before delivery and server refusal retains the finite budget',async()=>{
 const current=fixture();current.find('[data-mode]').value='work';current.find('[data-message]').value='Retain original admission';let calls=0;
 globalThis.fetch=async()=>{calls++;return {...response({error:'Original observation admission unavailable'}),ok:false,status:409};};
 current.setConnectedObservation('0');await assert.rejects(current.send(),/positive whole number/);assert.equal(calls,0);assert.equal(current.submitting,false);
 current.setConnectedObservation('300');await assert.rejects(current.send(),/Original observation admission unavailable/);assert.equal(calls,1);assert.equal(current.find('[data-message]').value,'Retain original admission');assert.equal(current.messageIntent.connected_observation_seconds,300);
 for(const value of [-1,1.5,Infinity,'300'])assert.throws(()=>connectedObservationSeconds({connected_observation_seconds:value}));
});

test('a same-text remote budget change during pending acknowledgement remains a new unsent draft',async()=>{
 const current=fixture();current.find('[data-mode]').value='work';current.find('[data-message]').value='Keep same text';current.setConnectedObservation('300');let release,sent;
 globalThis.fetch=(_path,options)=>{sent=JSON.parse(options.body);return new Promise(resolve=>{release=()=>resolve(response({session_id:'existing',turn_id:'WT-budget'}));});};
 const sending=current.send();while(!release)await Promise.resolve();
 const later={...current.messageIntent,connected_observation_seconds:90};current.composerStorage.setItem(current.composerStorageKey,encodeComposerDraft('Keep same text',later));current.readComposerDraft();
 release();await sending;assert.equal(sent.connected_observation_seconds,300);assert.equal(current.messageIntent.connected_observation_seconds,90);assert.equal(current.find('[data-message]').value,'Keep same text');
});

test('connected observation control is unavailable for a running or dispatched/review context',()=>{
 const current=fixture();current.find('[data-mode]').value='work';current.active='WT-running';current.setConnectedObservation('300');assert.equal(current.messageIntent,undefined);
 current.active='';current.role='review';current.setConnectedObservation('300');assert.equal(current.messageIntent,undefined);
 current.role='author';current.selectedSessionRecord={dispatch_id:'WORK-child'};current.setConnectedObservation('300');assert.equal(current.messageIntent,undefined);
});

test('stale Work refusal keeps exact draft and original guards until explicit adoption',async()=>{
 const current=fixture(),work={id:'WORK-pinned',title:'Pinned task',work_scope_revision:'sha256:'+'a'.repeat(64),dependency_revision:'sha256:'+'b'.repeat(64)};
 current.find('[data-message]').value='Retain this request';current.pinMessageTarget({surface:'project'},work);const original=structuredClone(current.messageIntent),posts=[];
 globalThis.fetch=async(_path,options)=>{posts.push(JSON.parse(options.body));return {...response({error:'Work scope changed',code:'CHANGED_INPUT',next_reads:[{operation:'project',payload:{id:work.id}}]}),ok:false,status:409};};
 await assert.rejects(current.send(),/Work scope changed/);
 assert.equal(posts[0].expected_work_scope_revision,work.work_scope_revision);assert.equal(posts[0].expected_dependency_revision,work.dependency_revision);assert.equal(current.find('[data-message]').value,'Retain this request');assert.deepEqual(current.messageIntent,original);
 current.pinMessageTarget({surface:'project'},{...work,work_scope_revision:'sha256:'+'c'.repeat(64)});assert.equal(current.authoredContext().expected_work_scope_revision,'sha256:'+'c'.repeat(64));assert.equal(current.find('[data-message]').value,'Retain this request');
});

test('conversation switching retains targets beside their original draft only',()=>{
 const current=fixture();current.find('[data-message]').value='Draft A';current.pinMessageTarget({surface:'structure',label:'A',node_id:'a'});
 current.switchDraftTarget('other');assert.equal(current.find('[data-message]').value,'');assert.equal(current.messageIntent,null);
 current.find('[data-message]').value='Draft B';current.pinMessageTarget({surface:'structure',label:'B',node_id:'b'});
 current.switchDraftTarget('existing');assert.equal(current.find('[data-message]').value,'Draft A');assert.equal(current.authoredContext().node_id,'a');
 current.clearMessageTarget();assert.equal(current.find('[data-message]').value,'Draft A');assert.equal(current.authoredContext().surface,'project');
});

test('Use reading replaces passage A with B and removal never reattaches either',async()=>{
 const current=fixture();current.find('[data-message]').value='Discuss the attached passage';
 current.pinMessageTarget({surface:'manuscript',label:'A',selection:{files:['a.tex'],quote:'A'}});
 current.pinMessageTarget({surface:'manuscript',label:'B',selection:{files:['b.tex'],quote:'B'}});
 assert.deepEqual(current.selectionOverride,{files:['b.tex'],quote:'B'});assert.equal(current.authoredContext().selection,undefined);
 current.clearSelection();assert.equal(current.messageIntent.selection,null);let submitted;
 globalThis.fetch=async(_path,options)=>{submitted=JSON.parse(options.body);return response({session_id:'existing',turn_id:'WT-clear'});};
 await current.send();assert.equal(submitted.selection,undefined);assert.equal(submitted.workspace_context.label,'B');
});

test('removing an attachment during preparation cancels delivery and keeps the message',async()=>{
 const current=fixture();current.find('[data-message]').value='Do not send the removed passage';current.pinMessageTarget({surface:'manuscript',selection:{files:['a.tex']}});let release,calls=0;
 current.prepareSend=()=>new Promise(resolve=>{release=resolve;});globalThis.fetch=async()=>{calls++;return response({});};
 const sending=current.send();while(!release)await Promise.resolve();current.clearSelection();release();
 await assert.rejects(sending,/work or context changed/);assert.equal(calls,0);assert.equal(current.find('[data-message]').value,'Do not send the removed passage');assert.equal(current.selectionOverride,null);
});

test('file-only authored attachment translates message scope without contaminating later reading',()=>{
 const current=fixture();let reading={surface:'structure',label:'Logical item A',node_id:'a'};current.getContext=()=>reading;
 current.pinMessageTarget({...reading,selection:{files:['a.tex']}});
 assert.equal(current.authoredContext().surface,'project');assert.equal(current.authoredContext().node_id,undefined);
 reading={surface:'structure',label:'Reading B',node_id:'b'};assert.equal(current.getContext().node_id,'b');assert.deepEqual(current.selectionOverride,{files:['a.tex']});
 current.pinMessageTarget(reading);assert.equal(current.authoredContext().node_id,'b');assert.equal(current.selectionOverride,null);
});

test('successful first Send consumes the New-slot target with its submitted text',async()=>{
 const current=fixture('');current.find('[data-message]').value='First admitted request';current.pinMessageTarget({surface:'structure',label:'First target',node_id:'first'});
 globalThis.fetch=async()=>response({session_id:'WS-admitted',turn_id:'WT-first'});
 await current.send();assert.equal(current.session,'WS-admitted');assert.equal(sessionStorage.getItem(current.composerBackupKey('')),'');
 current.newConversation();assert.equal(current.find('[data-message]').value,'');assert.equal(current.messageIntent,null);assert.equal(current.selectionOverride,null);assert.equal(current.authoredContext().surface,'project');
});

test('an acknowledged request preserves newer text and target authored while delivery was pending',async()=>{
 for(const change of ['text','target']){
  const current=fixture();current.find('[data-message]').value='Submitted';current.pinMessageTarget({surface:'structure',label:'Original',node_id:'original'});let release;
  globalThis.fetch=()=>new Promise(resolve=>{release=()=>resolve(response({session_id:'existing',turn_id:'WT-ack'}));});
  const sending=current.send();while(!release)await Promise.resolve();
  if(change==='text'){current.find('[data-message]').value='Newer unsent text';current.persistComposerDraft('Newer unsent text');}
  else current.pinMessageTarget({surface:'structure',label:'New target',node_id:'new'});
  release();await sending;
  assert.equal(current.find('[data-message]').value,change==='text'?'Newer unsent text':'Submitted');assert.equal(current.authoredContext().node_id,change==='text'?'original':'new');
 }
});

test('same-text storage retargeting during pending ACK survives whether observed locally yet or not',async()=>{
 const {encodeComposerDraft}=await import('../src/laplace/web/static_shared/workspace-interaction.mjs');
 for(const observed of [false,true]){
  const current=fixture();current.find('[data-message]').value='Same text';current.pinMessageTarget({surface:'structure',node_id:'original',label:'Original'});let release;
  globalThis.fetch=()=>new Promise(resolve=>{release=()=>resolve(response({session_id:'existing',turn_id:'WT-ack'}));});
  const sending=current.send();while(!release)await Promise.resolve();
  const intent={context:{surface:'structure',node_id:'remote-new',label:'Authored elsewhere'},selection:null};
  const stored=encodeComposerDraft('Same text',intent);current.composerStorage.setItem(current.composerStorageKey,stored);
  if(observed)current.readComposerDraft();
  release();await sending;
  assert.equal(current.find('[data-message]').value,'Same text');assert.deepEqual(current.messageIntent,intent);assert.equal(current.composerStorage.getItem(current.composerStorageKey),stored);
 }
});
