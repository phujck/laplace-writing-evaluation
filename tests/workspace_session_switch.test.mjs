import {beforeEach,test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {webcrypto} from 'node:crypto';
import {WorkspaceSession,proposalPresentation,conversationMetadata,inputDeliveryMode,inputReceiptNeedsAttention} from '../src/laplace/web/static_shared/workspace-session.mjs';
import {parentWire} from './helpers/parent_continuation_fixture.mjs';

class Element {
 constructor(tag='div'){this.attrs={};this.tag=tag;this.children=[];this.dataset={};this.value='';this.className='';this._text='';this.scrollHeight=200;this.scrollTop=150;this.clientHeight=100;const classes=new Set();this.classList={add:c=>classes.add(c),remove:c=>classes.delete(c),toggle:(c,on)=>on?classes.add(c):classes.delete(c),contains:c=>classes.has(c)};}
 set textContent(text){this._text=String(text);this.children=[];}get textContent(){return this._text+this.children.map(node=>node.textContent||'').join('');}
 append(...nodes){for(const node of nodes){node.parentElement=this;this.children.push(node);}}prepend(...nodes){this.children.unshift(...nodes);}replaceChildren(...nodes){this._text='';this.children=[];this.append(...nodes);}
 get lastElementChild(){return this.children.at(-1);}get childNodes(){return this.children;}
 querySelector(selector){for(const node of this.children){if(selector.startsWith('.')&&node.className.split(' ').includes(selector.slice(1)))return node;const nested=node.querySelector?.(selector);if(nested)return nested;}return null;}
 setAttribute(key,value){this.attrs[key]=String(value);}getAttribute(key){return this.attrs[key];}
 remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(node=>node!==this);}focus(){}
}
class Source {
 static CLOSED=2;static instances=[];constructor(url){this.url=url;this.readyState=1;Source.instances.push(this);}close(){this.closed=true;this.readyState=2;}
 emit(value){this.onmessage?.({data:JSON.stringify(value)});}
}
const tabStorage=()=>{const values=new Map();return {getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,String(value)),removeItem:key=>values.delete(key)};};
beforeEach(()=>{
 globalThis.sessionStorage=tabStorage();const values=new Map();globalThis.localStorage={getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,String(value)),removeItem:key=>values.delete(key)};
 globalThis.document={createElement:tag=>new Element(tag),createTextNode:text=>{const node=new Element('#text');node.textContent=text;return node;}};globalThis.EventSource=Source;Source.instances=[];globalThis.window={dispatchEvent(){}};globalThis.CustomEvent=class{constructor(type,detail){this.type=type;this.detail=detail;}};
 if(!globalThis.crypto)Object.defineProperty(globalThis,'crypto',{value:webcrypto,configurable:true});
});
const response=value=>({ok:true,headers:{get:()=> 'application/json'},json:async()=>value});
const localObservation=(id,provider='claude')=>({id,capabilities:{observation:'events',events_url:'/authoring/events?turn='+encodeURIComponent(id),can_interrupt:true,can_steer:provider==='codex',input_delivery_modes:provider==='codex'?['native_rpc']:[]}});
const sessionData=(id,active=null)=>({session:{id,provider:id==='claude'?'claude':'codex',model:id==='claude'?'opus':'luna',effort:id==='claude'?'high':'medium',role:'author'},turns:[],active:active?{...localObservation(active.id,id==='codex'?'codex':'claude'),...active}:null});
const sessions=[{id:'codex',title:'Chapter numerics',provider:'codex'},{id:'claude',title:'Source synthesis',provider:'claude'}];
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function fixture(){
 const current=Object.create(WorkspaceSession.prototype),fields=new Map();
 current.find=selector=>{if(selector==='.session-empty')return fields.get('[data-thread]')?.querySelector(selector);if(!fields.has(selector))fields.set(selector,new Element());return fields.get(selector);};
 Object.assign(current,{project:'pilot',session:'claude',active:'',role:'author',sessionLoad:0,viewEpoch:0,streamGeneration:0,settingsRevision:0,modeRevision:0,settingsSave:Promise.resolve(),ready:Promise.resolve(),runningSessions:new Map(),sessionRows:sessions,queued:[],limit:30,key:'laplace:session:pilot',draftKey:'laplace:compose:pilot',getContext:()=>({surface:'project',label:'Pilot'}),loadQueue:async()=>{},onProposalChanged:async()=>{},onOpenReview:()=>{},onChanged:async()=>{},onReviewProposal:async()=>{},onOpenArtifact:()=>{},onApplication:()=>{}});
 current.providers=[{id:'claude',models:[{id:'opus',name:'Opus',efforts:['low','medium','high'],context_window_advertised:1000000}]},{id:'codex',models:[{id:'luna',name:'Luna',efforts:['low','medium','high']}]}];
 current.find('[data-provider]').value='claude';current.models('opus');current.efforts('high');current.find('[data-mode]').value='work';current.message('assistant','');const connect=WorkspaceSession.prototype.connect;current.connect=(id,cursor=0,observation)=>connect.call(current,id,cursor,observation||localObservation(id,current.find('[data-provider]').value));return current;
}
function route(current,{claudeActive={id:'claude-turn',text:'Reading source',cursor:8},codexActive=null}={}){
 const requests=[];globalThis.fetch=async(path,options)=>{requests.push({path,options});if(path.startsWith('/authoring/state?'))return response({sessions,session_count:2});if(path.includes('id=claude'))return response(sessionData('claude',claudeActive));if(path.includes('id=codex'))return response(sessionData('codex',codexActive));throw Error('Unexpected request '+path);};return requests;
}

const preferenceCatalogue=[
 {id:'claude',name:'Claude',available:true,models:[{id:'opus',name:'Opus',session_default:true,efforts:['high','max']}]},
 {id:'codex',name:'Codex',available:true,models:[{id:'gpt-6.1-sol',name:'Sol',session_default:true,efforts:['medium','high']},{id:'gpt-5.6-terra',name:'Terra',efforts:['low','medium']}]}
];
const projectPreferenceDefaults={provider:'codex',model:'gpt-6.1-sol',effort:'medium'};
function coldPreferenceFixture(){
 const current=fixture();current.session='';current.providers=[];current.preferences=undefined;
 for(const selector of ['[data-provider]','[data-model]','[data-effort]'])current.find(selector).value='';
 current.composerSession=current.readConversationSelection()||'';current.composerStored=current.readComposerDraft();current.find('[data-message]').value=current.composerStored;
 return current;
}
function preferenceReadRoutes(calls,session=null){
 globalThis.fetch=async(path,options)=>{
  calls.push({path,method:options.method});assert.notEqual(options.method,'POST','Reload must not change defaults or session settings');
  if(path==='/authoring/providers')return response({providers:preferenceCatalogue});
  if(path.startsWith('/work/session-preferences?'))return response({preferences:projectPreferenceDefaults});
  if(path.startsWith('/authoring/state?'))return response({sessions:session?[{id:session,title:'Retained author conversation',provider:'codex'}]:[],session_count:session?1:0});
  if(path.startsWith('/authoring/session?'))return response({session:{id:session,project:'pilot',role:'author',...projectPreferenceDefaults},turns:[],active:null});
  throw Error('Unexpected preference reload route '+path);
 };
}

test('cold New-draft reload restores explicit Terra low with text, Work and wait without changing defaults',async()=>{
 const writer=fixture();writer.providers=preferenceCatalogue;writer.newConversation();writer.find('[data-provider]').value='codex';writer.models('gpt-5.6-terra');writer.efforts('low');
 writer.find('[data-message]').value='Retain this deliberate request';writer.setConnectedObservation('300');writer.pinMessageTarget({surface:'project',label:'Current project'},{id:'WORK-retained',title:'Retained Work',work_scope_revision:'sha256:'+'a'.repeat(64),dependency_revision:'sha256:'+'b'.repeat(64)});
 await writer.savePreferences();const saved=localStorage.getItem(writer.settingsKey('')),calls=[];preferenceReadRoutes(calls);
 const reopened=coldPreferenceFixture();await reopened.start();
 assert.equal(reopened.session,'');assert.equal(reopened.find('[data-provider]').value,'codex');assert.equal(reopened.find('[data-model]').value,'gpt-5.6-terra');assert.equal(reopened.find('[data-effort]').value,'low');
 assert.equal(reopened.find('[data-message]').value,'Retain this deliberate request');assert.equal(reopened.messageIntent.connected_observation_seconds,300);assert.equal(reopened.messageIntent.context.task_id,'WORK-retained');
 assert.equal(localStorage.getItem(writer.settingsKey('')),saved);assert.equal(projectPreferenceDefaults.model,'gpt-6.1-sol');assert.ok(calls.every(call=>call.method==='GET'));
});

test('cold saved-conversation reload restores its own future model and effort instead of New-slot preferences',async()=>{
 const writer=fixture();writer.providers=preferenceCatalogue;writer.session='codex';writer.switchDraftTarget('codex');writer.rememberConversationSelection('codex');
 writer.find('[data-provider]').value='codex';writer.models('gpt-5.6-terra');writer.efforts('low');writer.find('[data-message]').value='Saved conversation draft';writer.persistComposerDraft('Saved conversation draft');
 globalThis.fetch=async(path,options)=>{assert.equal(path,'/authoring/session-settings');return response({session:{id:'codex',...JSON.parse(options.body)}});};await writer.savePreferences();
 localStorage.setItem(writer.settingsKey(''),JSON.stringify({provider:'claude',model:'opus',effort:'max'}));
 const calls=[];preferenceReadRoutes(calls,'codex');const reopened=coldPreferenceFixture();await reopened.start();
 assert.equal(reopened.session,'codex');assert.equal(reopened.find('[data-provider]').value,'codex');assert.equal(reopened.find('[data-model]').value,'gpt-5.6-terra');assert.equal(reopened.find('[data-effort]').value,'low');assert.equal(reopened.find('[data-message]').value,'Saved conversation draft');
 assert.ok(calls.every(call=>call.method==='GET'));assert.equal(JSON.parse(localStorage.getItem(writer.settingsKey(''))).model,'opus');
});

test('explicit provider switch chooses advertised target model and effort while passive retention preserves its choice',async()=>{
 const current=fixture();current.providers=preferenceCatalogue;current.preferences={provider:'codex',model:'opus',effort:'max'};
 current.find('[data-provider]').value='codex';current.find('[data-effort]').value='max';current.models(undefined,{advertisedOnly:true});
 const codex=preferenceCatalogue[1],selected=codex.models.find(model=>model.id===current.find('[data-model]').value);assert.ok(selected);assert.ok(selected.efforts.includes(current.find('[data-effort]').value));assert.ok(!current.find('[data-model]').children.some(option=>option.value==='opus'));
 current.models('gpt-5.6-terra');current.efforts('low');current.preferences={provider:'codex',model:'gpt-5.6-terra',effort:'low'};
 globalThis.fetch=async()=>response({providers:preferenceCatalogue});await current.refreshProvidersPassive({force:true});assert.equal(current.find('[data-model]').value,'gpt-5.6-terra');assert.equal(current.find('[data-effort]').value,'low');
 current.find('[data-provider]').value='claude';current.models(undefined,{advertisedOnly:true});assert.equal(current.find('[data-model]').value,'opus');assert.equal(current.find('[data-effort]').value,'high');
});

test('native continuation events keep Stop and queued input available without reviving a detached parent',async()=>{
 const current=fixture();current.project='book';current.session='WS-parent';current.selectedSessionRecord={role:'author'};
 const capabilities={observation:'events',events_url:'/authoring/events?turn=WT-parent',can_interrupt:true,can_steer:false,can_offer_input:true,input_delivery_modes:['project_tool_boundary']};
 await WorkspaceSession.prototype.connect.call(current,'WT-parent',0,{id:'WT-parent',session_id:'WS-parent',capabilities,parent_continuation:parentWire.observation});
 const stream=Source.instances.at(-1);assert.match(current.find('[data-parent-continuation]').textContent,/Parent waiting/);assert.equal(current.find('[data-stop]').disabled,false);assert.equal(current.find('[data-send]').textContent,'Queue input for next tool result');
 current.find('[data-message]').value='Retain queued instruction';current.controlPending={id:'INPUT-pending',turn:'WT-parent',session:'WS-parent',project:'book',delivery_mode:'project_tool_boundary'};
 stream.emit({type:'dispatch-continuation',parent_continuation:{...parentWire.observation,phase:'READY',execution_settled:true,execution_state:'COMPLETE',review_state:'REJECTED'}});
 current.setBusy(true);assert.match(current.find('[data-parent-continuation]').textContent,/rejected review/);assert.equal(current.find('[data-stop]').disabled,false);assert.equal(current.controlPending.id,'INPUT-pending');assert.equal(current.find('[data-send]').disabled,true);assert.equal(current.find('[data-message]').value,'Retain queued instruction');
 const posts=[];globalThis.fetch=async(path,options)=>{posts.push({path,payload:JSON.parse(options.body)});return response({});};current.refreshSelectedConversation=async()=>{};
 await current.stopSelectedTurn();assert.equal(posts.length,1);assert.equal(posts[0].path,'/authoring/interrupt');assert.deepEqual(posts[0].payload,{project:'book',turn_id:'WT-parent'});assert.match(current.find('[data-parent-continuation]').textContent,/Parent Stop requested/);
 current.detachConversation();current.session='WS-new';current.active='WT-new';const before=current.find('[data-parent-continuation]').textContent;
 stream.emit({type:'dispatch-continuation',parent_continuation:{...parentWire.observation,phase:'READY'}});stream.emit({type:'complete',result:{status:'completed'}});
 assert.equal(current.active,'WT-new');assert.equal(current.find('[data-parent-continuation]').textContent,before);assert.equal(current.find('[data-message]').value,'Retain queued instruction');assert.equal(posts.length,1);
});

test('running Claude detaches to idle Codex without interruption and reconnects at its saved cursor',async()=>{
 const current=fixture(),requests=route(current);current.find('[data-message]').value='Keep my unsent thought';current.persistComposerDraft('Keep my unsent thought');current.connect('claude-turn');const old=Source.instances.at(-1),oldAnswer=current.find('[data-thread]').lastElementChild.querySelector('.session-body');
 assert.equal(current.find('[data-sessions]').disabled,false);assert.equal(current.find('[data-new]').disabled,false);assert.equal(current.find('[data-model]').disabled,true);assert.equal(current.find('[data-send]').disabled,true);assert.match(current.find('[data-conversation-list]').textContent,/Source synthesis.*Last observed running/);
 await current.openConversation('codex');assert.ok(old.closed);assert.equal(current.active,'');assert.equal(current.find('[data-provider]').value,'codex');assert.equal(current.find('[data-model]').value,'luna');assert.equal(current.find('[data-effort]').value,'medium');assert.equal(current.find('[data-model]').disabled,false);assert.equal(current.find('[data-send]').disabled,false);assert.equal(current.find('[data-message]').value,'');assert.equal(sessionStorage.getItem(current.composerBackupKey('claude')),'Keep my unsent thought');
 const status=current.find('[data-status]').textContent;old.emit({type:'delta',text:'STALE'});old.emit({type:'complete',result:{status:'completed'}});old.onerror();assert.equal(current.find('[data-status]').textContent,status);assert.equal(oldAnswer.textContent,'');assert.equal(current.session,'codex');
 await current.openConversation('claude');assert.equal(current.find('[data-message]').value,'Keep my unsent thought');assert.equal(current.active,'claude-turn');assert.match(Source.instances.at(-1).url,/turn=claude-turn&after=8/);assert.equal(current.find('[data-model]').value,'opus');assert.equal(current.find('[data-effort]').value,'high');assert.equal(current.find('[data-model]').disabled,true);assert.equal(current.find('[data-sessions]').disabled,false);assert.ok(!requests.some(row=>row.path.includes('interrupt')||row.options.method==='POST'));
});

test('initial connection reads admitted settings from the exact turn in its owner response',async()=>{
 const current=fixture();current.admittedSettings=null;
 const active=localObservation('exact-turn','codex');
 globalThis.fetch=async()=>response({session:{id:'claude',provider:'claude',model:'opus',effort:'high'},active,turns:[{id:'other-turn',provider_settings:{model:'wrong'}},{id:'exact-turn',provider_settings:{provider:'codex',model:'gpt-6-luna',effort:'low'}}]});
 await WorkspaceSession.prototype.connect.call(current,'exact-turn');
 assert.deepEqual(current.admittedSettings,{provider:'codex',model:'gpt-6-luna',effort:'low'});
 assert.match(current.find('[data-settings-truth]').textContent,/Admitted turn settings: gpt-6-luna.*effort low/);
 assert.match(current.find('[data-settings-truth]').textContent,/Next-message settings: opus.*effort high/);
});

test('New conversation retains the original draft at its conversation and restores new preferences',()=>{
 const current=fixture();current.find('[data-message]').value='Draft';current.persistComposerDraft('Draft');localStorage.setItem(current.settingsKey(''),JSON.stringify({provider:'codex',model:'luna',effort:'low'}));current.connect('claude-turn');const stream=Source.instances.at(-1);
 assert.equal(current.newConversation(),true);assert.ok(stream.closed);assert.equal(current.session,'');assert.equal(current.active,'');assert.equal(current.find('[data-provider]').value,'codex');assert.equal(current.find('[data-model]').value,'luna');assert.equal(current.find('[data-effort]').value,'low');assert.equal(current.find('[data-message]').value,'');assert.equal(sessionStorage.getItem(current.composerBackupKey('claude')),'Draft');assert.ok(current.runningSessions.has('claude'));assert.equal(current.find('[data-send]').disabled,false);
});

test('completion awaiting a list response cannot reload or update a newly selected conversation',async()=>{
 const current=fixture();let release;const changed=[];current.onChanged=async actions=>changed.push(actions);globalThis.fetch=async path=>path.startsWith('/authoring/state?')?new Promise(resolve=>{release=()=>resolve(response({sessions,session_count:2}));}):response(sessionData('codex'));
 current.connect('claude-turn');Source.instances.at(-1).emit({type:'complete',result:{status:'completed',actions:[{operation:'note'}]}});await tick();await current.openConversation('codex');const status=current.find('[data-status]').textContent;release();await tick();assert.equal(current.session,'codex');assert.equal(current.find('[data-status]').textContent,status);assert.equal(changed.length,0);assert.equal(Source.instances.length,1);
});

test('completion already fetching its final reply cannot overwrite a switch away and back',async()=>{
 const current=fixture();let release,reads=0;globalThis.fetch=async path=>{if(path.startsWith('/authoring/state?'))return response({sessions,session_count:2});if(path.includes('id=claude')&&++reads===1)return new Promise(resolve=>{release=()=>resolve(response(sessionData('claude')));});return response(sessionData(path.includes('id=claude')?'claude':'codex',path.includes('id=claude')?{id:'newer-turn',text:'Current stream',cursor:4}:null));};
 current.connect('claude-turn');const old=Source.instances.at(-1);old.emit({type:'complete',result:{status:'completed'}});await tick();await current.openConversation('codex');await current.openConversation('claude');release();await tick();assert.equal(current.active,'newer-turn');assert.equal(current.find('[data-status]').textContent,'The execution owner reports this turn active.');assert.equal(current.find('[data-model]').disabled,true);old.emit({type:'delta',text:'late'});assert.equal(current.find('[data-thread]').lastElementChild.querySelector('.session-body').textContent,'');
});

test('terminal reply-save error clears busy state, preserves streamed text and cannot be overwritten by onerror',async()=>{
 const current=fixture();current.connect('claude-turn');const stream=Source.instances.at(-1),answer=current.find('[data-thread]').lastElementChild.querySelector('.session-body');stream.emit({type:'delta',text:'Public text that could not be saved.'});stream.emit({type:'error',message:'Could not save the reply: disk full'});
 assert.equal(current.active,'');assert.equal(stream.closed,true);assert.equal(answer.textContent,'Public text that could not be saved.');assert.equal(answer.dataset.unsavedReply,'true');assert.match(answer.parentElement.textContent,/not saved/);assert.match(current.find('[data-status]').textContent,/Could not save the reply: disk full/);assert.equal(current.find('[data-send]').disabled,false);const status=current.find('[data-status]').textContent;stream.onerror();assert.equal(current.find('[data-status]').textContent,status);
});

test('closed expired stream reconciles once and clears inactive unsaved turn without replaying provider work',async()=>{
 const current=fixture(),requests=[];globalThis.fetch=async(path,options)=>{requests.push({path,options});return response(sessionData('claude',null));};current.connect('expired-turn');const stream=Source.instances.at(-1),answer=current.find('[data-thread]').lastElementChild.querySelector('.session-body');stream.emit({type:'delta',text:'Partial visible text.'});stream.readyState=Source.CLOSED;stream.onerror();await tick();await tick();
 assert.equal(current.active,'');assert.equal(answer.textContent,'Partial visible text.');assert.equal(answer.dataset.unsavedReply,'true');assert.match(current.find('[data-status]').textContent,/before a final reply was saved/);assert.deepEqual(requests.map(row=>row.path),['/authoring/session?project=pilot&id=claude&view=summary&limit=1']);assert.ok(requests.every(row=>!row.options||row.options.method!=='POST'));
});

test('closed stream with authoritative active turn remains stoppable and does not start or replay work',async()=>{
 const current=fixture(),requests=[];globalThis.fetch=async(path,options)=>{requests.push({path,options});return response(sessionData('claude',{id:'claude-turn',text:'Still running',cursor:9}));};current.connect('claude-turn');const stream=Source.instances.at(-1);stream.readyState=Source.CLOSED;stream.onerror();await tick();await tick();
 assert.equal(current.active,'claude-turn');assert.match(current.find('[data-status]').textContent,/still reports this turn active/);assert.deepEqual(requests.map(row=>row.path),['/authoring/session?project=pilot&id=claude&view=summary&limit=1']);assert.ok(requests.every(row=>!row.options||row.options.method!=='POST'));
});

test('a stale failed session load cannot put an error on the newly selected session',async()=>{
 const current=fixture();let reject;globalThis.fetch=path=>path.includes('id=claude')?new Promise((_,fail)=>{reject=fail;}):Promise.resolve(response(sessionData('codex')));
 const first=current.openConversation('claude');await current.openConversation('codex');reject(Error('old connection failed'));await first;assert.equal(current.session,'codex');assert.equal(current.find('[data-status]').textContent,'Ready');
});

test('dispatch is serialized, switching during submission is refused, and active settings cannot be written',async()=>{
 const current=fixture();current.connect('claude-turn');let writes=0;globalThis.fetch=async()=>{writes++;return response({});};await assert.rejects(current.savePreferences(),/conversation is running/);assert.equal(writes,0);
 current.newConversation();current.find('[data-provider]').value='codex';current.models('luna');current.find('[data-message]').value='Start numerics';let release;globalThis.fetch=async(path,options)=>{assert.equal(path,'/authoring/turn');writes++;return new Promise(resolve=>{release=()=>resolve(response({session_id:'new-codex',turn_id:'new-turn'}));});};
 const pending=current.send();await tick();await current.send();assert.equal(await current.openConversation('claude'),false);assert.equal(current.find('[data-sessions]').disabled,true);assert.equal(writes,1);release();await pending;assert.equal(current.session,'new-codex');assert.equal(current.active,'new-turn');assert.equal(current.find('[data-sessions]').disabled,false);assert.equal(current.find('[data-model]').disabled,true);assert.equal(current.find('[data-send]').textContent,'Steer selected turn');
});

test('settled submission updates existing catalogue cards without rebuilding focus or drafts',async()=>{
 const current=fixture();current.newConversation();current.paintConversations();current.find('[data-provider]').value='codex';current.models('luna');current.find('[data-message]').value='Start selected task';let release,finishQueue,queueReads=0;
 current.loadQueue=async()=>{if(++queueReads===2)await new Promise(resolve=>{finishQueue=resolve;});};
 globalThis.fetch=async()=>new Promise(resolve=>{release=()=>resolve(response({session_id:'new-codex',turn_id:'new-turn'}));});
 const sending=current.send();await tick();assert.ok(current.find('[data-conversation-list]').children.every(card=>card.disabled));release();await tick();
 const cards=[...current.find('[data-conversation-list]').children];assert.ok(cards.every(card=>card.disabled));current.find('[data-message]').value='New typing';finishQueue();await sending;
 assert.deepEqual(current.find('[data-conversation-list]').children,cards);assert.ok(cards.every(card=>!card.disabled));assert.equal(current.find('[data-message]').value,'New typing');assert.equal(current.active,'new-turn');
});

test('trusted capability transition updates controls; wrong namespace and detached stream cannot change drafts',async()=>{
 const current=fixture();current.session='codex';current.connect('selected-turn',0,{id:'selected-turn',session_id:'codex',capabilities:{...localObservation('selected-turn').capabilities,can_steer:false}});const stream=Source.instances.at(-1);current.find('[data-message]').value='Retained draft';
 const observed={type:'execution-observation',project:'pilot',session_id:'codex',turn_id:'selected-turn',capabilities:{...localObservation('selected-turn','codex').capabilities,can_offer_input:true,input_delivery_modes:['native_rpc','project_tool_boundary']}};
 assert.equal(current.find('[data-send]').textContent,'Input unavailable');for(const bad of [{...observed,project:'other'},{...observed,session_id:'claude'},{...observed,turn_id:'old-turn'},{...observed,capabilities:{...observed.capabilities,events_url:'/authoring/events?turn=other'}},{...observed,capabilities:{can_steer:true,can_interrupt:true,input_delivery_modes:['native_rpc']}}])stream.emit(bad);
 assert.equal(current.activeCapabilities.can_steer,false);stream.emit(observed);assert.equal(current.activeCapabilities.can_steer,true);assert.equal(current.find('[data-send]').textContent,'Steer selected turn');assert.equal(current.find('[data-send]').disabled,false);assert.match(current.find('[data-observation]').textContent,/Native steering is available/);
 const execution={controls:[{control_id:'retained'}]};current.execution=execution;stream.emit(observed);assert.equal(current.execution,execution);assert.equal(current.find('[data-message]').value,'Retained draft');
 current.detachConversation();current.session='claude';const after=current.find('[data-observation]').textContent;stream.emit(observed);assert.equal(current.active,'');assert.equal(current.find('[data-observation]').textContent,after);assert.equal(current.find('[data-message]').value,'Retained draft');
});

test('post-admission queue failure retains the started execution and unlocks actual cards without replay',async()=>{
 const current=fixture();current.newConversation();current.find('[data-provider]').value='codex';current.models('luna');current.find('[data-message]').value='Original request';let queueReads=0,posts=0;current.loadQueue=async()=>{if(++queueReads===2)throw Error('Queue unavailable');};
 globalThis.fetch=async()=>{posts++;return response({session_id:'new-codex',turn_id:'new-turn'});};const connect=current.connect;current.connect=async(...args)=>{await connect(...args);current.find('[data-message]').value='Later local typing';};
 await assert.rejects(current.send(),/Queue unavailable/);assert.equal(posts,1);assert.equal(current.active,'new-turn');assert.equal(current.session,'new-codex');assert.equal(current.submitting,false);assert.ok(current.find('[data-conversation-list]').children.every(card=>!card.disabled));assert.equal(current.find('[data-message]').value,'Later local typing');
});

test('opening choices refreshes only known running entries and removes a completed badge',async()=>{
 const current=fixture();current.connect('claude-turn');current.newConversation();const requests=route(current,{claudeActive:null});await current.refreshConversationChoices();await current.refreshConversationChoices();assert.deepEqual(requests.map(row=>row.path),['/authoring/state?project=pilot&session_limit=30&view=sessions','/authoring/session?id=claude&view=summary&limit=1']);assert.ok(!current.find('[data-conversation-list]').textContent.includes('Running'));assert.equal(current.session,'');
});

test('reported usage retains selected advertised capacity without inventing an effective limit',()=>{
 const current=fixture();current.showUsage(null,{context_tokens_used:71900});assert.match(current.find('[data-context-label]').textContent,/71\.9k tokens · counter basis unknown · advertised capacity 1,000k/);assert.equal(current.find('[data-context-progress]').hidden,true);
 current.showUsage({thread_token_usage:{last:{totalTokens:71900},modelContextWindow:828400}},{});assert.match(current.find('[data-context-label]').textContent,/71\.9k tokens · counter basis unknown · reported limit 828\.4k/);assert.equal(current.find('[data-context-progress]').hidden,true);
});

test('detaching preserves preference-write order so an old session cannot overwrite newer conversation intent',async()=>{
 const current=fixture(),writes=[];let release;globalThis.fetch=async(path,options)=>{const payload=JSON.parse(options.body);writes.push({path,...payload});if(writes.length===1)await new Promise(resolve=>{release=resolve;});return response({});};
 const old=current.savePreferences();await tick();current.newConversation();current.find('[data-provider]').value='codex';current.models('luna');current.efforts('low');const latest=current.savePreferences();await tick();assert.equal(writes.length,1);release();await Promise.all([old,latest]);
 assert.deepEqual(writes.map(row=>[row.path,row.session_id||null,row.provider]),[['/authoring/session-settings','claude','claude']]);assert.equal(current.preferences.provider,'codex');assert.equal(current.find('[data-model]').value,'luna');assert.equal(current.find('[data-effort]').value,'low');
});

test('a detached settings failure does not poison the new conversation’s settings or Send barrier',async()=>{
 const current=fixture();let reject;globalThis.fetch=()=>new Promise((_,fail)=>{reject=fail;});const old=current.savePreferences();const oldFailure=assert.rejects(old,/unavailable/);await tick();current.newConversation();current.find('[data-provider]').value='codex';current.models('luna');current.efforts('medium');const writes=[];globalThis.fetch=async(path,options)=>{writes.push([path,JSON.parse(options.body)]);return response({});};const latest=current.savePreferences();reject(Error('old settings write failed'));await Promise.all([oldFailure,latest]);assert.equal(current.settingsFailed,false);assert.equal(writes.length,0);await current.settingsSave;
});


test('two tabs retain independent selected conversations across reload while new tabs use the project default',async()=>{
 const a=tabStorage(),b=tabStorage(),requests=route(null),load=async store=>{globalThis.sessionStorage=store;const view=fixture();view.loadProviders=async()=>{};await view.start();return view;};
 localStorage.setItem('laplace:session:pilot','codex');const first=await load(a);assert.equal(first.session,'codex');const second=await load(b);await second.openConversation('claude');assert.equal(second.active,'claude-turn');assert.equal(localStorage.getItem(second.key),'claude');
 const firstReload=await load(a);assert.equal(firstReload.session,'codex');assert.equal(firstReload.find('[data-provider]').value,'codex');assert.equal(firstReload.find('[data-model]').value,'luna');assert.equal(second.active,'claude-turn');assert.equal(second.stream.closed,undefined);
 const secondReload=await load(b);assert.equal(secondReload.session,'claude');assert.equal(secondReload.active,'claude-turn');const third=await load(tabStorage());assert.equal(third.session,'claude');assert.ok(!requests.some(row=>row.path.includes('interrupt')||row.options.method==='POST'));
});

test('an explicitly new conversation uses an empty tab sentinel rather than another tab’s project choice',async()=>{
 const a=tabStorage(),b=tabStorage();route(null);globalThis.sessionStorage=a;const first=fixture();first.newConversation();assert.equal(a.getItem(first.key),'');globalThis.sessionStorage=b;const second=fixture();await second.openConversation('claude');globalThis.sessionStorage=a;const reloaded=fixture();reloaded.loadProviders=async()=>{};await reloaded.start();assert.equal(reloaded.session,'');assert.equal(second.active,'claude-turn');
});

test('conversation selection falls back safely under restricted storage without changing model settings',()=>{
 const current=fixture();localStorage.setItem(current.key,'codex');globalThis.sessionStorage={getItem(){throw Error('blocked');},setItem(){throw Error('blocked');}};assert.equal(current.readConversationSelection(),'codex');current.rememberConversationSelection('claude');assert.equal(current.readConversationSelection(),'claude');assert.equal(localStorage.getItem(current.key),'claude');assert.equal(current.find('[data-model]').value,'opus');
 globalThis.sessionStorage=tabStorage();globalThis.sessionStorage.setItem(current.key,'codex');globalThis.localStorage={getItem(){throw Error('blocked');},setItem(){throw Error('blocked');},removeItem(){throw Error('blocked');}};const other=fixture();assert.equal(other.readConversationSelection(),'codex');assert.doesNotThrow(()=>other.rememberConversationSelection('claude'));assert.equal(globalThis.sessionStorage.getItem(other.key),'claude');
});

test('completion notifies the project owner once and never opens a comparison or reads a competing queue',async()=>{
 const current=fixture(),opened=[],changed=[];const requests=route(current,{claudeActive:null});current.onProposalChanged=async()=>changed.push('owner');current.onReviewProposal=(...args)=>opened.push(args);
 current.connect('claude-turn');Source.instances.at(-1).emit({type:'complete',result:{status:'completed',proposal:{edits:[{file:'chapter.tex',before:'Old',after:'Proposed'}]}}});await tick();await tick();
 assert.deepEqual(opened,[]);assert.deepEqual(changed,['owner']);assert.equal(requests.filter(row=>row.path.startsWith('/authoring/proposals')).length,0);
});

test('queue loading uses the compatible thin work view and retains pending anchored requests',async()=>{const current=fixture(),paths=[],opened=[];current.onInspectPassage=anchor=>opened.push(anchor);globalThis.fetch=async path=>{paths.push(path);return response({tasks:[{id:'pending',task_kind:'session-request',status:'ready',title:'Explain this passage',goal:'Explain this passage',anchor:{file:'chapter.tex',line_start:7}},{id:'done',task_kind:'session-request',status:'done',title:'Completed'},{id:'other',task_kind:'research',status:'ready',title:'Research'}]});};await WorkspaceSession.prototype.loadQueue.call(current);assert.deepEqual(paths,['/work/state?project=pilot&view=queue']);assert.equal(current.queued.length,1);assert.equal(current.queued[0].id,'pending');const row=current.find('[data-queue-items]').children[0];row.children[0].onclick();assert.equal(opened[0].line_start,7);});

test('queue follows exact owner pages and cancellation consumes the displayed standing guard',async()=>{
 const current=fixture(),calls=[],next='/work/state?project=pilot&view=queue&offset=50&as_of=cut';
 const pending={id:'last',task_kind:'session-request',status:'ready',title:'Last request',goal:'Full request',anchor:{file:'chapter.tex',line_start:9},allowed_actions:{task_status:{permitted:true,statuses:['cancelled'],payload:{id:'last',expected_work_scope_revision:'scope',expected_work_status_revision:'standing'},http:{method:'POST',url:'/work/transition'}}}};
 globalThis.fetch=async(path,options)=>{calls.push([path,options]);if(options.method==='POST')return response({ok:true});return response(path===next?{tasks:[pending]}:{tasks:[],pagination:{next_read:{http:{method:'GET',url:next}}}});};
 await WorkspaceSession.prototype.loadQueue.call(current);assert.equal(current.queued[0].anchor.line_start,9);
 const row=current.find('[data-queue-items]').children[0],cancel=row.children.find(n=>n.tag==='button'&&n.textContent==='Cancel canonical request');await cancel.onclick();
 const sent=JSON.parse(calls.find(([path])=>path==='/work/transition')[1].body);
 assert.equal(sent.expected_work_status_revision,'standing');assert.equal(sent.expected_work_scope_revision,'scope');assert.equal(sent.status,'cancelled');
});

test('unavailable or repeating queue continuation cannot silently accept a partial queue',async()=>{
 const current=fixture();current.queued=[{id:'retained'}];
 globalThis.fetch=async()=>response({tasks:[{id:'partial'}],pagination:{next_offset:50}});
 await assert.rejects(WorkspaceSession.prototype.loadQueue.call(current),/incomplete/);assert.equal(current.queued[0].id,'retained');
 globalThis.fetch=async()=>response({tasks:[],pagination:{next_read:{http:{method:'GET',url:'/work/state?project=pilot&view=queue'}}}});
 await assert.rejects(WorkspaceSession.prototype.loadQueue.call(current),/repeated/);assert.equal(current.queued[0].id,'retained');
});

test('summary conversation loads keep full public text and lazy Undo handles, fetching exact action pages only on demand',async()=>{
 const current=fixture(),paths=[],applications=[],inspected=[];current.onApplication=value=>applications.push(value);current.onInspect=value=>inspected.push(value);current.onReadTurn=(id,options)=>inspected.push({id,options});const inverse={id:'WA-one',kind:'source-edits',edit_count:2,detail:{turn_id:'turn-one',view:'application',item_id:'WA-one'}},turn={id:'turn-one',text:'Author direction.',reply:{text:'The complete saved scientific response.'},action_count:21,failure_count:0,proposal_edit_count:0,undo_entries:[inverse],detail:{turn_id:'turn-one',views:['actions','failures','turn']}};
 globalThis.fetch=async path=>{paths.push(path);if(path.startsWith('/authoring/session?'))return response({...sessionData('codex'),turns:[turn]});const query=new URL(path,'http://local').searchParams,offset=Number(query.get('offset'));assert.equal(query.get('view'),'actions');return response({items:Array.from({length:offset?1:20},(_,index)=>({id:'action-'+(offset+index),operation:'note',outcome:{status:'SUCCEEDED',receipts:['receipt-'+(offset+index)]}})),pagination:{total:21,next_offset:offset?null:20}});};
 await current.openConversation('codex');assert.match(paths[0],/view=summary&limit=20/);assert.equal(paths.length,1);assert.deepEqual(applications,[{...inverse,project:'pilot'}]);const thread=current.find('[data-thread]');assert.match(thread.textContent,/complete saved scientific response/);const box=thread.querySelector('.session-actions');assert.equal(box.children[0].textContent,'21 saved project changes');assert.equal(box.children[1].children.length,0);box.open=true;await box.ontoggle();assert.equal(paths.length,2);assert.equal(box.children[1].children.length,20);await box.children[3].onclick();assert.equal(box.children[1].children.length,21);assert.equal(paths.length,3);box.children[1].children.at(-1).children.find(node=>node.tag==='button').onclick();assert.deepEqual(inspected[0],{id:'turn-one',options:{focusView:'actions'}});const exact=thread.querySelector('.session-complete-turn');exact.open=true;exact.ontoggle();const download=exact.children.at(-1);assert.match(download.href,/view=turn/);assert.equal(paths.length,3,'full exact public turn remains available without an eager read');
});

test('late action detail from a detached conversation cannot paint into the newly selected session',async()=>{
 const current=fixture(),box=new Element('details');let release;current.remoteHistory(box,{detail:{turn_id:'old'}},'actions',value=>new Element(value.id));globalThis.fetch=()=>new Promise(resolve=>{release=()=>resolve(response({items:[{id:'late'}],pagination:{next_offset:null,total:1}}));});box.open=true;const pending=box.ontoggle();current.newConversation();release();await pending;assert.equal(box.children[0].children.length,0);assert.equal(current.session,'');
});

test('accepted, rejected and fulfilled history has terminal text and only an inspect-only comparison action',async()=>{
 const current=fixture(),opened=[];current.onReviewProposal=(...args)=>opened.push(args);
 for(const state of ['applied','rejected','applied-elsewhere','superseded','fulfilled']){const row=new Element('article');current.proposal(row,{id:'turn-'+state,proposal_state:state,proposal_edit_count:1,proposal_version:'V',proposal_read_handle:{exact:state}});assert.equal(row.querySelector('.session-review-proposal'),null);assert.equal(row.querySelector('.session-proposal-status').onclick,undefined);await row.querySelector('.session-inspect-proposal').onclick();assert.deepEqual(opened.at(-1),['turn-'+state,{readOnly:true,proposalVersion:'V',readHandle:{exact:state}}]);assert.equal(proposalPresentation({proposal_state:state,reply:{proposal:{edits:[{}]}}}).terminal,true);}
});

test('an explicit conversation destination overrides only this tab and preserves its unsent draft',async()=>{
 const current=fixture();route(current);current.loadProviders=async()=>{};current.initialSession='claude';current.session='codex';current.find('[data-message]').value='Keep my thought';sessionStorage.setItem(current.key,'codex');localStorage.setItem(current.key,'codex');
 await current.start();assert.equal(current.session,'claude');assert.equal(current.active,'claude-turn');assert.equal(current.find('[data-message]').value,'');assert.equal(sessionStorage.getItem(current.composerBackupKey('codex')),'Keep my thought');assert.equal(sessionStorage.getItem(current.key),'claude');assert.equal(current.initialSession,'');
 await current.openConversation('codex');await current.start();assert.equal(current.session,'codex','the deep link is consumed once, not forced again');
});

test('an explicit destination cannot attach another project’s conversation or replace the previous choice on failure',async()=>{
 const current=fixture();current.loadProviders=async()=>{};current.loadSessions=async()=>{};current.initialSession='outside';sessionStorage.setItem(current.key,'codex');localStorage.setItem(current.key,'codex');globalThis.fetch=async()=>response({...sessionData('outside'),session:{id:'outside',project:'different-book',provider:'claude',model:'opus'}});
 await current.start();assert.equal(current.session,'');assert.equal(current.active,'');assert.match(current.find('[data-status]').textContent,/different project/);assert.equal(sessionStorage.getItem(current.key),'codex');assert.equal(localStorage.getItem(current.key),'codex');assert.equal(Source.instances.length,0);
});

test('project future defaults replace a stale new-conversation cache without changing the active session',()=>{
 const current=fixture();localStorage.setItem(current.settingsKey(''),JSON.stringify({provider:'codex',model:'luna',effort:'low'}));current.connect('claude-turn');const values={provider:'codex',model:'luna',effort:'high'};current.applyFutureDefaults(values);assert.equal(current.active,'claude-turn');assert.equal(current.find('[data-model]').value,'opus');assert.equal(current.find('[data-effort]').value,'high');assert.equal(current.find('[data-model]').disabled,true);assert.deepEqual(JSON.parse(localStorage.getItem(current.settingsKey(''))),values);current.newConversation();assert.equal(current.find('[data-provider]').value,'codex');assert.equal(current.find('[data-model]').value,'luna');assert.equal(current.find('[data-effort]').value,'high');
});

test('project-home default saves follow queued session settings without letting a refusal block the current conversation',async()=>{
 const current=fixture(),writes=[];let release;globalThis.fetch=async(path,options)=>{const value=JSON.parse(options.body);writes.push([path,value]);if(writes.length===1)await new Promise(resolve=>{release=resolve;});return response({preferences:{provider:value.provider,model:value.model,effort:value.effort}});};const old=current.savePreferences();await tick();const future=current.saveProjectDefaults({provider:'codex',model:'luna',effort:'low'});await tick();assert.equal(writes.length,1);release();await Promise.all([old,future]);assert.deepEqual(writes.map(row=>[row[0],row[1].provider]),[['/authoring/session-settings','claude'],['/work/session-preferences','codex']]);assert.equal(current.find('[data-model]').value,'opus');assert.equal(current.preferences.model,'luna');globalThis.fetch=async()=>({...response({error:'Future preference refused'}),ok:false});await assert.rejects(current.saveProjectDefaults({provider:'unknown'}),/refused/);await current.settingsSave;assert.equal(current.find('[data-model]').value,'opus');
});

test('imported transcript notice is visible without replaying or sending history and disappears after a new native binding',async()=>{
 const current=fixture(),paths=[];let imported=true;globalThis.fetch=async(path,options)=>{paths.push({path,options});return response({...sessionData('codex'),session:{...sessionData('codex').session,...(imported?{imported_history:{reason:'Imported source history'}}:{})}});};await current.openConversation('codex');assert.match(current.find('[data-thread]').textContent,/Imported conversation history/);assert.match(current.find('[data-thread]').textContent,/next turn opens a new provider conversation/);assert.ok(paths.every(row=>row.options.method!=='POST'));imported=false;await current.loadSession();assert.ok(!current.find('[data-thread]').textContent.includes('Imported conversation history'));
});

test('snapshot-only child observes controls without creating SSE and cancels observation on selection switch',async()=>{
 const current=fixture();current.session='codex';const active={id:'remote-turn',session_id:'codex',progress:'RUNNING',capabilities:{observation:'snapshot',snapshot_url:'/authoring/session?project=pilot&id=codex&view=summary&limit=1',poll_interval_ms:500,events_url:null,can_interrupt:true,can_steer:true,input_delivery_modes:['native_rpc']}};
 await WorkspaceSession.prototype.connect.call(current,active.id,0,active);assert.equal(Source.instances.length,0);assert.match(current.find('[data-observation]').textContent,/Live token streaming is unavailable/);assert.equal(current.find('[data-stop]').disabled,false);assert.equal(current.find('[data-send]').textContent,'Steer selected turn');const timer=current.snapshotTimer;current.detachConversation();assert.equal(current.snapshotTimer,null);assert.equal(current.active,'');clearTimeout(timer);
});
test('known native admission retains saved input while composer clears only submitted draft',async()=>{
 const current=fixture();current.session='codex';current.active='remote-turn';current.activeCapabilities={observation:'snapshot',snapshot_url:'/authoring/session?project=pilot&id=codex&view=summary&limit=1',can_interrupt:true,can_steer:true,input_delivery_modes:['native_rpc']};current.find('[data-message]').value='Inspect the selected result';current.persistComposerDraft(current.find('[data-message]').value);let delivered=false;const requests=[];
 globalThis.fetch=async(path,options)=>{requests.push({path,options});if(path==='/authoring/steer')return response({control_id:'control-one',delivery:'PENDING'});return response({...sessionData('codex',{id:'remote-turn',capabilities:current.activeCapabilities}),execution:{controls:[{control_id:'control-one',turn_id:'remote-turn',delivery_mode:'native_rpc',state:delivered?'DELIVERED':'ADMITTED'}]}});};
 await current.send();assert.equal(current.find('[data-message]').value,'');assert.equal(current.controlPending.id,'control-one');assert.equal(current.find('[data-send]').disabled,true);delivered=true;await current.refreshSelectedConversation();assert.equal(current.find('[data-message]').value,'');assert.equal(current.controlPending,null);assert.equal(requests.filter(row=>row.path==='/authoring/steer').length,1);assert.equal(Source.instances.length,0);
});

test('input mode requires both declared capability and route without provider inference',()=>{
 assert.equal(inputDeliveryMode({can_steer:true}),null);assert.equal(inputDeliveryMode({can_offer_input:true}),null);assert.equal(inputDeliveryMode({can_offer_input:true,input_delivery_modes:'project_tool_boundary'}),null);
 assert.equal(inputDeliveryMode({provider:'claude',can_offer_input:true,input_delivery_modes:['project_tool_boundary']}),'project_tool_boundary');assert.equal(inputDeliveryMode({provider:'claude',can_steer:true,input_delivery_modes:['native_rpc']}),'native_rpc');assert.equal(inputDeliveryMode({provider:'codex',can_steer:false,input_delivery_modes:['native_rpc']}),null);
});

test('queued input remains queued/offered until exact session read; newer typing survives acknowledgement',async()=>{
 const current=fixture();current.session='claude';current.active='queued-turn';current.activeCapabilities={observation:'events',can_interrupt:true,can_steer:false,can_offer_input:true,input_delivery_modes:['project_tool_boundary']};current.scheduleControlObservation=()=>{};current.setBusy(true);assert.equal(current.find('[data-send]').textContent,'Queue input for next tool result');assert.equal(current.find('[data-send]').disabled,false);
 current.find('[data-message]').value='Original queued input';current.persistComposerDraft(current.find('[data-message]').value);const calls=[];
 globalThis.fetch=async(path,options)=>{calls.push({path,body:JSON.parse(options.body)});return response({control_id:'queued-control',delivery:'PENDING',delivery_mode:'project_tool_boundary'});};
 await current.send();assert.equal(calls.length,1);assert.equal(calls[0].body.delivery_mode,'project_tool_boundary');assert.equal(calls[0].body.turn_id,'queued-turn');assert.equal(current.find('[data-message]').value,'');assert.match(current.find('[data-status]').textContent,/saved.*waiting/);
 const receipt={control_id:'queued-control',turn_id:'queued-turn',delivery_mode:'project_tool_boundary',state:'OFFERED_AT_TOOL_BOUNDARY'};current.settleControlReceipt(receipt);assert.ok(current.controlPending);assert.match(current.find('[data-status]').textContent,/offered.*reading is not confirmed/);
 current.find('[data-message]').value='Newer local typing';current.persistComposerDraft('Newer local typing');current.settleControlReceipt({...receipt,state:'EXACT_SCOPED_CONTROL_READ'});assert.equal(current.controlPending,null);assert.equal(current.find('[data-message]').value,'Newer local typing');assert.match(current.find('[data-status]').textContent,/read by the session.*not proven/);assert.equal(calls.length,1);
});

test('failed or ended queued input retains text and never creates a follow-up',async()=>{
 for(const state of ['FAILED','OFFERED_UNACKNOWLEDGED','UNCONFIRMED']){
  const current=fixture();current.session='claude';current.active='queued-turn';current.find('[data-message]').value='Recoverable input';current.persistComposerDraft('Recoverable input');const pending={id:'control',turn:'queued-turn',project:'pilot',session:'claude',delivery_mode:'project_tool_boundary',submitted:'Recoverable input'};current.controlPending=pending;current.pendingControls=new Map([['claude',pending]]);let writes=0;globalThis.fetch=async()=>{writes++;throw Error('no request permitted');};
  current.settleControlReceipt({control_id:'control',turn_id:'queued-turn',delivery_mode:'project_tool_boundary',state});assert.equal(current.find('[data-message]').value,'Recoverable input');assert.equal(current.controlPending,null);assert.match(current.find('[data-status]').textContent,/retained.*replayed/);assert.equal(writes,0);
 }
});

test('exact pending input read is bounded and rejects wrong turn/mode before draft settlement',async()=>{
 const current=fixture();current.session='claude';current.active='queued-turn';current.find('[data-message]').value='Exact input';current.persistComposerDraft('Exact input');const pending={id:'control',turn:'queued-turn',project:'pilot',session:'claude',delivery_mode:'project_tool_boundary',submitted:'Exact input'};current.controlPending=pending;let calls=0,bad=true;
 globalThis.fetch=async path=>{calls++;assert.ok(path.includes('view=controls')&&path.includes('item_id=control')&&!path.includes('view=summary'));return response({project:'pilot',turn_id:bad?'other':'queued-turn',view:'controls',exact:true,items:[{control_id:'control',turn_id:'queued-turn',delivery_mode:'project_tool_boundary',state:'EXACT_SCOPED_CONTROL_READ'}]});};
 await assert.rejects(current.readPendingControl(),/exact owner receipt/);assert.equal(current.find('[data-message]').value,'Exact input');current.settleControlReceipt({control_id:'control',turn_id:'queued-turn',delivery_mode:'native_rpc',state:'DELIVERED'});assert.ok(current.controlPending);bad=false;await current.readPendingControl();assert.equal(current.find('[data-message]').value,'');assert.equal(calls,2);
});

test('queued preparation cannot silently change delivery mode or target',async()=>{
 const current=fixture();current.session='claude';current.active='queued-turn';current.activeCapabilities={can_steer:false,can_offer_input:true,input_delivery_modes:['project_tool_boundary']};current.find('[data-message]').value='Keep intended queue';let release,writes=0;current.prepareSend=()=>new Promise(resolve=>{release=resolve;});globalThis.fetch=async()=>{writes++;return response({});};
 const sent=current.send();await tick();current.activeCapabilities={can_steer:true,input_delivery_modes:['native_rpc']};release();await assert.rejects(sent,/input mode changed/);assert.equal(writes,0);assert.equal(current.find('[data-message]').value,'Keep intended queue');
});

for(const changed of ['ended','switched'])test('known queued acknowledgement survives post-effect '+changed+' target',async()=>{
 const current=fixture();current.session='claude';current.active='queued-turn';current.activeCapabilities={observation:'events',can_offer_input:true,input_delivery_modes:['project_tool_boundary']};current.scheduleControlObservation=()=>{};current.find('[data-message]').value='Admitted original input';current.persistComposerDraft('Admitted original input');let release,writes=0,reads=0;
 globalThis.fetch=async(path,options)=>{if(path==='/authoring/steer'){writes++;return new Promise(resolve=>{release=()=>resolve(response({control_id:'late-control',delivery:'PENDING',delivery_mode:'project_tool_boundary'}));});}reads++;assert.ok(path.includes('id=queued-turn')&&path.includes('item_id=late-control'));return response({project:'pilot',turn_id:'queued-turn',view:'controls',exact:true,items:[{control_id:'late-control',turn_id:'queued-turn',delivery_mode:'project_tool_boundary',state:'OFFERED_UNACKNOWLEDGED'}]});};
 const sending=current.send();await tick();if(changed==='ended'){current.active='';}else{current.detachConversation();current.session='codex';current.find('[data-message]').value='New conversation draft';current.status('New selected view');}release();await sending;
 assert.equal(writes,1);if(changed==='ended'){assert.equal(reads,1);assert.equal(current.controlPending,null);assert.equal(current.find('[data-message]').value,'');assert.match(current.find('[data-status]').textContent,/Turn ended.*retained/);}else{assert.equal(reads,0);assert.equal(current.pendingControls.get('claude').id,'late-control');assert.equal(current.find('[data-message]').value,'New conversation draft');assert.equal(current.find('[data-status]').textContent,'New selected view');}
});

for(const changed of ['active','ended','newer','switched','switched-newer'])test('known native acknowledgement survives post-effect '+changed+' target without inventing a receipt',async()=>{
 const current=fixture();current.active='native-turn';current.activeCapabilities={observation:'events',can_steer:true,input_delivery_modes:['native_rpc']};current.find('[data-message]').value='Original native input';current.persistComposerDraft('Original native input');let release,writes=0,controlReads=0;
 globalThis.fetch=async(path,options)=>{if(path==='/authoring/steer'){writes++;const body=JSON.parse(options.body);assert.equal(body.turn_id,'native-turn');assert.equal(body.delivery_mode,'native_rpc');return new Promise(resolve=>{release=()=>resolve(response({}));});}if(path.includes('view=controls')){controlReads++;throw Error('Direct native acknowledgement has no control receipt');}if(path.includes('id=codex'))return response(sessionData('codex'));if(path.includes('id=claude'))return response(sessionData('claude'));throw Error('Unexpected request '+path);};
 const sending=current.send();await tick();const detached=changed.startsWith('switched');
 if(detached){current.detachConversation();current.switchDraftTarget('codex');current.session='codex';await current.loadSession();current.find('[data-message]').value='Other conversation draft';current.persistComposerDraft('Other conversation draft');current.status('Other selected view');if(changed==='switched-newer'){sessionStorage.setItem(current.composerBackupKey('claude'),'Newer original conversation draft');localStorage.setItem(current.composerBackupKey('claude'),'Newer original conversation draft');}}
 else if(changed!=='active'){current.active='';if(changed==='newer'){current.find('[data-message]').value='Newer original conversation draft';current.persistComposerDraft('Newer original conversation draft');}}
 release();await sending;
 const acknowledged=current.pendingControls.get('claude');assert.equal(acknowledged.kind,'native-acknowledgement');assert.equal(acknowledged.project,'pilot');assert.equal(acknowledged.session,'claude');assert.equal(acknowledged.turn,'native-turn');assert.equal(acknowledged.submitted,'Original native input');assert.equal(acknowledged.delivery_mode,'native_rpc');assert.deepEqual(acknowledged.response,{});assert.equal('id' in acknowledged,false);assert.equal(current.controlPending??null,null);assert.equal(controlReads,0);assert.equal(writes,1);
 if(detached){assert.equal(acknowledged.draft_settled,undefined);assert.equal(current.find('[data-message]').value,'Other conversation draft');assert.equal(current.find('[data-status]').textContent,'Other selected view');await current.openConversation('claude');assert.equal(current.controlPending,null);}
 assert.equal(current.find('[data-message]').value,changed.includes('newer')?'Newer original conversation draft':'');assert.match(current.find('[data-status]').textContent,/Native steering acknowledged.*original turn.*not proven/);assert.equal(current.snapshotTimer??null,null);assert.equal(controlReads,0);assert.equal(writes,1);
 const provenance=current.find('[data-control-receipts]').children[0].children.find(node=>node.tag==='details');provenance.open=true;await provenance.ontoggle();assert.match(provenance.textContent,/native-turn/);assert.match(provenance.textContent,/Original native input/);assert.match(provenance.textContent,/"response": \{\}/);
 // A later draft with the same text is a new edit, not an old acknowledgement's work.
 current.find('[data-message]').value='Original native input';current.persistComposerDraft('Original native input');await current.loadSession();assert.equal(current.find('[data-message]').value,'Original native input');assert.equal(controlReads,0);assert.equal(writes,1);
});

test('pending receipt observer reads only one exact control and a switched view cannot settle its draft',async()=>{
 const current=fixture();current.session='claude';current.active='queued-turn';current.activeCapabilities={observation:'events'};current.find('[data-message]').value='Retain offered text';const pending={id:'control',turn:'queued-turn',project:'pilot',session:'claude',delivery_mode:'project_tool_boundary',submitted:'Retain offered text'};current.controlPending=pending;const queued=[];const originalSet=globalThis.setTimeout,originalClear=globalThis.clearTimeout;let release,reads=0;
 try{globalThis.setTimeout=(fn,ms)=>{queued.push({fn,ms});return queued.length;};globalThis.clearTimeout=()=>{};globalThis.fetch=async path=>{reads++;assert.ok(path.includes('item_id=control')&&path.includes('view=controls'));return new Promise(resolve=>{release=()=>resolve(response({project:'pilot',turn_id:'queued-turn',view:'controls',exact:true,items:[{control_id:'control',turn_id:'queued-turn',delivery_mode:'project_tool_boundary',state:'EXACT_SCOPED_CONTROL_READ'}]}));});};
  current.scheduleControlObservation();assert.equal(queued[0].ms,2000);const observing=queued[0].fn();await tick();current.detachConversation();current.session='codex';release();await observing;assert.equal(reads,1);assert.equal(queued.length,1);assert.equal(current.find('[data-message]').value,'Retain offered text');
 }finally{globalThis.setTimeout=originalSet;globalThis.clearTimeout=originalClear;}
});

test('terminal session render keeps unconfirmed input outcome visible and exposes exact recovery',async()=>{
 const current=fixture();current.session='claude';current.active='queued-turn';current.find('[data-message]').value='Recover this input';current.persistComposerDraft('Recover this input');const pending={id:'control',turn:'queued-turn',project:'pilot',session:'claude',delivery_mode:'project_tool_boundary',submitted:'Recover this input'};current.controlPending=pending;current.pendingControls=new Map([['claude',pending]]);
 globalThis.fetch=async()=>response({...sessionData('claude'),execution:{turn_id:'queued-turn',state:'FINISHED',controls:[{control_id:'control',turn_id:'queued-turn',delivery_mode:'project_tool_boundary',state:'OFFERED_UNACKNOWLEDGED'}]}});
 await current.loadSession();assert.equal(current.controlPending,null);assert.equal(current.find('[data-message]').value,'Recover this input');assert.match(current.find('[data-status]').textContent,/Turn ended.*retained/);const receipts=current.find('[data-control-receipts]');assert.match(receipts.textContent,/Turn ended before reading/);
 const provenance=receipts.children[0].children.find(node=>node.tag==='details');provenance.open=true;await provenance.ontoggle();const recovery=provenance.children.find(node=>node.tag==='a');assert.match(recovery.href,/view=controls.*item_id=control/);
});
test('an unavailable native steering capability cannot be inferred from a Codex provider label',async()=>{
 const current=fixture();current.session='codex';current.find('[data-provider]').value='codex';current.active='starting-child';current.activeCapabilities={observation:'snapshot',can_interrupt:true,can_steer:false};current.setBusy(true);assert.equal(current.find('[data-send]').disabled,true);let called=false;globalThis.fetch=async()=>{called=true;return response({});};current.find('[data-message]').value='Do not dispatch this yet';await assert.rejects(current.send(),/owner has not enabled this input mode/);assert.equal(called,false);assert.equal(current.find('[data-message]').value,'Do not dispatch this yet');
});
test('same-tab selection restores each conversation draft and a storage failure retains original target memory',async()=>{
 const current=fixture();route(current,{claudeActive:null});current.find('[data-message]').value='Claude draft';current.persistComposerDraft('Claude draft');await current.openConversation('codex');assert.equal(current.find('[data-message]').value,'');current.find('[data-message]').value='Codex draft';current.persistComposerDraft('Codex draft');await current.openConversation('claude');assert.equal(current.find('[data-message]').value,'Claude draft');await current.openConversation('codex');assert.equal(current.find('[data-message]').value,'Codex draft');
 const originalSet=localStorage.setItem;localStorage.setItem=()=>{throw Error('quota');};current.find('[data-message]').value='Recover in Codex';assert.equal(current.persistComposerDraft('Recover in Codex'),false);await current.openConversation('claude');assert.equal(current.find('[data-message]').value,'Claude draft');await current.openConversation('codex');assert.equal(current.find('[data-message]').value,'Recover in Codex');localStorage.setItem=originalSet;
});

test('expired steering during awaited preparation never falls through to a new turn and keeps original session draft',async()=>{
 const current=fixture();current.session='codex';current.active='selected-child';current.activeCapabilities={observation:'snapshot',can_steer:true,can_interrupt:true,input_delivery_modes:['native_rpc']};current.find('[data-provider]').value='codex';current.find('[data-message]').value='Steer only this child';current.persistComposerDraft(current.find('[data-message]').value);let release;current.prepareSend=()=>new Promise(resolve=>{release=resolve;});const writes=[];globalThis.fetch=async(path,options)=>{writes.push({path,options});return response({});};const sending=current.send();await tick();current.active='';release();await assert.rejects(sending,/ended or.*changed/);assert.equal(writes.length,0);assert.equal(current.find('[data-message]').value,'Steer only this child');assert.equal(sessionStorage.getItem(current.composerBackupKey('codex')),'Steer only this child');
});
test('steering captures text and semantic work scope before any await',async()=>{
 const current=fixture();current.session='codex';current.active='selected-child';current.activeCapabilities={observation:'events',can_steer:true,input_delivery_modes:['native_rpc']};current.find('[data-provider]').value='codex';current.find('[data-message]').value='Original gesture';let release,context={surface:'project',task_id:'work-original',label:'Original work'};current.getContext=()=>context;current.pinMessageTarget(context);current.loadQueue=()=>new Promise(resolve=>{release=resolve;});const posts=[];globalThis.fetch=async(path,options)=>{posts.push(JSON.parse(options.body));return response({});};const sending=current.send();await tick();current.find('[data-message]').value='Later typing stays';release();await sending;assert.equal(posts[0].text,'Original gesture');assert.equal(posts[0].turn_id,'selected-child');assert.equal(posts[0].workspace_context.label,'Original work');assert.equal(current.find('[data-message]').value,'Later typing stays');
 context={surface:'project',task_id:'old',label:'Old'};current.pinMessageTarget(context);current.find('[data-message]').value='Do not redirect';const next=current.send();await tick();context={surface:'project',task_id:'new',label:'New'};current.pinMessageTarget(context);release();await assert.rejects(next,/work or context changed/);assert.equal(posts.length,1);
});


test('conversation preferences never write project defaults and unsent choices remain local',async()=>{
 const current=fixture(),writes=[];globalThis.fetch=async(path,options)=>{writes.push({path,payload:JSON.parse(options.body)});return response({session:{provider:'claude',model:'opus',effort:'high'},preferences:{provider:'codex',model:'luna',effort:'low'}});};
 current.find('[data-message]').value='Keep my draft';current.persistComposerDraft('Keep my draft');await current.savePreferences();assert.deepEqual(writes.map(row=>row.path),['/authoring/session-settings']);assert.equal(current.find('[data-message]').value,'Keep my draft');
 current.newConversation();current.find('[data-model]').value='luna';await current.savePreferences();assert.equal(writes.length,1);assert.equal(current.savedSettings().model,'luna');await current.saveProjectDefaults({provider:'codex',model:'luna',effort:'low'});assert.equal(writes.at(-1).path,'/work/session-preferences');
});
test('library search uses loaded exact identities and local draft filters do not adopt another tab buffer',()=>{
 const current=fixture();current.initComposerStorage();current.composerStorage.setItem(current.composerBackupKey('claude'),'');localStorage.setItem(current.composerBackupKey('claude'),'Draft in another tab');assert.equal(current.conversationDraft('claude'),false);
 current.find('[data-conversation-search]').value='codex';current.paintConversations();assert.match(current.find('[data-conversation-list]').textContent,/Chapter numerics/);assert.ok(!current.find('[data-conversation-list]').textContent.includes('Source synthesis'));
 current.find('[data-conversation-search]').value='';current.find('[data-conversation-filter]').value='draft';current.paintConversations();assert.match(current.find('[data-conversation-list]').textContent,/No matching/);current.composerStorage.setItem(current.composerBackupKey('claude'),'An exact local draft');current.paintConversations();assert.match(current.find('[data-conversation-list]').textContent,/Source synthesis/);
});


test('Return to reading exits library and expanded posture even when entered from expansion',()=>{
 const current=fixture(),classes=new Set(['session-expanded']);const root={classList:{contains:name=>classes.has(name),toggle:(name,on)=>on?classes.add(name):classes.delete(name)}};current.host={closest:()=>root};current.expand=value=>root.classList.toggle('session-expanded',value);current.find('[data-message]').value='Retain this draft';current.setLibrary(true);assert.ok(classes.has('session-library-open'));assert.ok(classes.has('session-expanded'));current.setLibrary(false);assert.equal(classes.has('session-expanded'),false);assert.equal(classes.has('session-library-open'),false);assert.equal(current.find('[data-message]').value,'Retain this draft');
});
test('conversation row metadata reports recorded creation/provider/model and never infers idle from saved history',()=>{
 const lines=conversationMetadata({id:'S',created_at:'2026-10-07T01:00:00Z',provider:'codex',model:'requested',role:'review'},{draft:true});assert.match(lines.join(' '),/Created.*codex.*requested.*Independent review/);assert.ok(!lines.join(' ').includes('Saved history'));assert.ok(!lines.join(' ').includes('Idle'));assert.match(lines.join(' '),/Local draft retained/);assert.deepEqual(conversationMetadata({id:'S'}),[]);
});


test('real analytics catalogue follows exact pinned owner pages and preserves readable owner title joins',async()=>{
 const held=JSON.parse(await readFile(new URL('./fixtures/session-analytics-catalogue-2f5d4e1cb.json',import.meta.url),'utf8')),current=fixture(),calls=[];current.project='p';current.sessionRows=[{id:'S-B',title:'An existing public catalogue title'}];let conflict=false;globalThis.fetch=async path=>{calls.push(path);return response(conflict?{...held.queries.sessions_next,as_of:'changed-cut'}:path.includes('cursor=')?held.queries.sessions_next:held.queries.sessions);};
 await current.loadLibraryCatalogue();assert.equal(current.sessionRows[0].title,'An existing public catalogue title');assert.equal(current.sessionRows[0].title_basis,'existing-owner-catalogue-display-join');const next=current.libraryNext;await current.loadLibraryCatalogue(next);assert.equal(current.sessionRows.length,2);assert.equal(current.find('[data-conversation-list]').children[0].textContent.startsWith('An existing public catalogue title'),true);assert.equal(calls[1],next.http.url);assert.equal(current.libraryNext,null);conflict=true;const before=current.sessionRows;await assert.rejects(current.loadLibraryCatalogue(next),/changed between pages/);assert.equal(current.sessionRows,before);
});


test('selected request context proxy outranks aggregate tokens and nulls never become zero occupancy',()=>{
 const current=fixture();current.showUsage({provider:'claude',input:100,cached_input:900,cache_write_input:0,output:12,total:1012,context_window:2000},{provider:'claude',context_tokens_used:5,usage_facts_projection:{selected:{context_snapshot:{value:5,metric:'last_request_input_proxy'}}}});assert.match(current.find('[data-context-label]').textContent,/Latest request input: 5 tokens \(proxy/);assert.ok(!current.find('[data-context-label]').textContent.includes('50%'));assert.equal(current.find('[data-context-progress]').hidden,true);
 current.showUsage({input:null,cached_input:null,cache_write_input:null,total:null},{context_tokens_used:null});assert.match(current.find('[data-context-label]').textContent,/unknown/);assert.ok(!current.find('[data-context-label]').textContent.includes('0 tokens'));assert.equal(current.find('[data-context-progress]').hidden,true);
});


test('terminal output cannot keep live label and unsupported steering never claims a delivered control',async()=>{
 const current=fixture();current.connect('claude-turn');assert.match(current.find('[data-observation]').textContent,/Steering is unavailable/);assert.equal(current.find('[data-send]').textContent,'Input unavailable');assert.equal(current.find('[data-send]').disabled,true);Source.instances.at(-1).emit({type:'error',error:'Terminal test'});assert.equal(current.find('[data-observation]').textContent,'Live output ended.');current.newConversation();assert.equal(current.find('[data-observation]').textContent,'');assert.equal(current.controlPending,null);
});





test('startup disables Send and model settings until explicit selected session has loaded',async()=>{const current=fixture();current.session='';current.initialSession='codex';let release;current.loadProviders=async()=>{await new Promise(resolve=>{release=resolve;});};const requests=route(current);const pending=current.start();assert.equal(current.find('[data-send]').disabled,true);assert.equal(current.find('[data-model]').disabled,true);current.find('[data-message]').value='Not ready';const before=requests.length;await current.send();assert.equal(requests.length,before);release();await pending;assert.equal(current.session,'codex');assert.equal(current.find('[data-provider]').value,'codex');assert.equal(current.find('[data-model]').value,'luna');assert.equal(current.find('[data-send]').disabled,false);});


test('failed explicit startup retains its target and draft, and only explicit successful selection unlocks Send',async()=>{const current=fixture();current.session='';current.initialSession='missing';current.loadProviders=async()=>{};sessionStorage.setItem(current.composerBackupKey('missing'),'Retained startup draft');const requests=route(current);await current.start();assert.equal(current.initialSession,'missing');assert.equal(current.startupFailed,true);assert.equal(current.find('[data-send]').disabled,true);const before=requests.length;await current.send();assert.equal(requests.length,before);await current.openConversation('codex');assert.equal(current.session,'codex');assert.equal(current.startupFailed,false);assert.equal(current.find('[data-send]').disabled,false);assert.equal(sessionStorage.getItem(current.composerBackupKey('missing')),'Retained startup draft');});


test('conversation thin link accurately names saved comparison and keeps exact immutable coordinates',async()=>{
 const current=fixture(),row=new Element('article'),opened=[];current.onReviewProposal=(...args)=>opened.push(args);const handle={exact:'record-and-version'};
 current.proposal(row,{id:'T',proposal_state:'ready',proposal_edit_count:2,proposal_turn_id:'T',proposal_version:'V',proposal_read_handle:handle});
 const link=row.querySelector('.session-review-proposal');assert.equal(link.textContent,'Review this saved version');current.session='different-conversation';await link.onclick();assert.deepEqual(opened,[['T',{proposalVersion:'V',readHandle:handle,readOnly:false}]]);
 assert.equal(current.pendingProposals,undefined);assert.equal(current.proposalRows,undefined);
});

test('compact composer disclosure preserves the exact draft and pending admission',()=>{
 const current=fixture(),pending={id:'control-exact',turn:'WT-kept'};current.host=new Element();current.controlPending=pending;current.find('[data-message]').value='First line\nStill unsent';
 WorkspaceSession.prototype.setComposerExpanded.call(current,true);assert.equal(current.host.classList.contains('composer-expanded'),true);assert.equal(current.find('[data-compose-expand]').attrs['aria-expanded'],'true');
 WorkspaceSession.prototype.setComposerExpanded.call(current,false);assert.equal(current.find('[data-message]').value,'First line\nStill unsent');assert.equal(current.controlPending,pending);assert.equal(current.find('[data-compose-expand]').attrs['aria-expanded'],'false');
});

test('next-settings disclosure remains inspectable while active preferences refuse writes',async()=>{
 const current=fixture();current.active='WT-kept';current.find('[data-message]').value='Do not send';let writes=0;globalThis.fetch=async()=>{writes++;return response({});};
 current.openInspector('settings');assert.equal(current.find('[data-inspector]').hidden,false);assert.equal(current.find('[data-settings-open]').attrs['aria-expanded'],'true');assert.match(current.find('[data-preference-scope]').textContent,/locked while a turn is active/);
 await assert.rejects(current.savePreferences(),/active|working|running|Wait|stop/i);assert.equal(writes,0);assert.equal(current.find('[data-message]').value,'Do not send');current.openInspector(null);assert.equal(current.find('[data-settings-open]').attrs['aria-expanded'],'false');
});

test('one existing preference control set lives in disclosure rather than the fixed composer',async()=>{
 const source=await readFile(new URL('../src/laplace/web/static_shared/workspace-session.mjs',import.meta.url),'utf8'),markup=source.slice(source.indexOf('host.innerHTML=`'),source.indexOf('this.find=s=>host.querySelector(s)'));
 for(const name of ['provider','model','effort','mode'])assert.equal((markup.match(new RegExp('data-'+name+'(?=[ >])','g'))||[]).length,1,name);
 const preferences=markup.slice(markup.indexOf('<details class="session-settings">'),markup.indexOf('<div class="session-context-meter"')),composer=markup.slice(markup.indexOf('<form class="session-composer">'));
 for(const name of ['model','effort','mode']){assert.ok(preferences.includes('data-'+name));assert.ok(!composer.includes('data-'+name+' '));}assert.ok(composer.includes('data-send'));assert.ok(composer.includes('data-message'));assert.ok(composer.includes('data-stop'));
});

test('publication releases the existing input slot while preserving newer composed text and history',async()=>{
 const current=fixture();current.active='queued-turn';current.activeCapabilities={observation:'events',can_offer_input:true,input_delivery_modes:['project_tool_boundary']};current.scheduleControlObservation=()=>{};current.find('[data-message]').value='Saved first input';current.persistComposerDraft('Saved first input');let posts=0;
 globalThis.fetch=async(path,options)=>{assert.equal(path,'/authoring/steer');posts++;return response({control_id:'control-'+posts,delivery:'PENDING',delivery_mode:'project_tool_boundary'});};
 await current.send();assert.equal(current.find('[data-message]').value,'');assert.equal(current.find('[data-send]').disabled,true);
 current.find('[data-message]').value='Composed next input';current.persistComposerDraft('Composed next input');current.settleControlReceipt({control_id:'control-1',turn_id:'queued-turn',delivery_mode:'project_tool_boundary',state:'PUBLISHED_AT_TOOL_BOUNDARY',publication:{scope:'PREVIEW',text_complete:true}});
 assert.equal(current.controlPending,null);assert.equal(current.find('[data-send]').disabled,false);assert.equal(current.find('[data-message]').value,'Composed next input');assert.match(current.find('[data-status]').textContent,/Preview offered.*not yet read/);
 await current.send();assert.equal(posts,2);assert.equal(current.controlPending.id,'control-2');assert.equal(current.find('[data-message]').value,'');
});

test('queued admission preserves newer typing and detached receipt settles only original submitted draft',async()=>{
 for(const detached of [false,true]){
  const current=fixture();current.active='queued-turn';current.activeCapabilities={observation:'events',can_offer_input:true,input_delivery_modes:['project_tool_boundary']};current.scheduleControlObservation=()=>{};current.find('[data-message]').value='Original queued input';current.persistComposerDraft('Original queued input');let release,posts=0;
  globalThis.fetch=async(path,options)=>{if(path==='/authoring/steer'){posts++;return new Promise(resolve=>{release=()=>resolve(response({control_id:'known-control',delivery:'PENDING',delivery_mode:'project_tool_boundary'}));});}if(path.includes('view=controls'))return response({project:'pilot',turn_id:'queued-turn',view:'controls',exact:true,items:[{control_id:'known-control',turn_id:'queued-turn',delivery_mode:'project_tool_boundary',state:'PUBLISHED_AT_TOOL_BOUNDARY'}]});return response({...sessionData('claude'),execution:{turn_id:'queued-turn',project:'pilot',state:'FINISHED',controls:[{control_id:'known-control',turn_id:'queued-turn',delivery_mode:'project_tool_boundary',state:'PUBLISHED_AT_TOOL_BOUNDARY'}]}});};
  const sending=current.send();await tick();if(detached){current.detachConversation();current.switchDraftTarget('codex');current.session='codex';}current.find('[data-message]').value='New typing';current.persistComposerDraft('New typing');release();await sending;
  assert.equal(current.find('[data-message]').value,'New typing');assert.equal(posts,1);
  if(detached){assert.equal(current.pendingControls.get('claude').draft_settled,undefined);await current.openConversation('claude');assert.equal(current.find('[data-message]').value,'');assert.equal(current.controlPending,null);}
 }
});

test('reload restores only unresolved owner publication slot without clearing unassociated new draft',async()=>{
 const current=fixture();current.find('[data-message]').value='Fresh local draft';current.persistComposerDraft('Fresh local draft');const active={id:'queued-turn',capabilities:{observation:'events',can_offer_input:true,input_delivery_modes:['project_tool_boundary']}};
 globalThis.fetch=async()=>response({...sessionData('claude',active),execution:{project:'pilot',turn_id:'queued-turn',state:'RUNNING',controls:[{control_id:'stored-control',turn_id:'queued-turn',delivery_mode:'project_tool_boundary',state:'PREPARED_AT_TOOL_BOUNDARY'}]}});
 current.scheduleControlObservation=()=>{};await current.loadSession();assert.equal(current.controlPending.id,'stored-control');assert.equal(current.controlPending.submitted,undefined);assert.equal(current.find('[data-message]').value,'Fresh local draft');assert.equal(current.find('[data-send]').disabled,true);
 current.settleControlReceipt({control_id:'stored-control',turn_id:'queued-turn',delivery_mode:'project_tool_boundary',state:'PUBLISHED_AT_TOOL_BOUNDARY'});assert.equal(current.find('[data-message]').value,'Fresh local draft');assert.equal(current.find('[data-send]').disabled,false);
});

test('receipt disclosure distinguishes settled publication from unresolved or failed transport',()=>{
 for(const state of ['EXACT_SCOPED_CONTROL_READ','DELIVERED'])assert.equal(inputReceiptNeedsAttention({state}),false);
 for(const state of ['ADMITTED','PENDING','OFFERED_AT_TOOL_BOUNDARY','PREPARING_AT_TOOL_BOUNDARY','PREPARED_AT_TOOL_BOUNDARY','PUBLICATION_UNCONFIRMED','FAILED','UNCONFIRMED','OFFERED_UNACKNOWLEDGED','unknown'])assert.equal(inputReceiptNeedsAttention({state}),true);
 assert.equal(inputReceiptNeedsAttention({kind:'native-acknowledgement',delivery_mode:'native_rpc',project:'p',session:'s',turn:'t',response:{}}),false);
 assert.equal(inputReceiptNeedsAttention({kind:'native-acknowledgement'}),true);
 assert.equal(inputReceiptNeedsAttention({state:'PUBLISHED_AT_TOOL_BOUNDARY'}),true);
 const full={state:'PUBLISHED_AT_TOOL_BOUNDARY',publication:{scope:'FULL',parts:{author_request:{complete:true,included_chars:10,total_chars:10},context:{complete:true,included_chars:0,total_chars:0}}}};
 assert.equal(inputReceiptNeedsAttention(full),false);assert.equal(inputReceiptNeedsAttention({...full,publication:{...full.publication,scope:'PREVIEW'}}),true);
 assert.equal(inputReceiptNeedsAttention({...full,publication:{scope:'FULL'}}),true);
});

test('terminal unconfirmed publication frees pending slot but keeps attention and newer draft',()=>{
 const current=fixture();current.active='queued-turn';current.activeCapabilities={can_offer_input:true,input_delivery_modes:['project_tool_boundary']};current.find('[data-message]').value='Newer composed input';current.persistComposerDraft('Newer composed input');
 const pending={id:'uncertain',turn:'queued-turn',project:'pilot',session:'claude',delivery_mode:'project_tool_boundary',admitted:true,draft_settled:true,submitted:'Earlier input'};current.controlPending=pending;current.pendingControls=new Map([['claude',pending]]);
 const receipt={control_id:'uncertain',turn_id:'queued-turn',delivery_mode:'project_tool_boundary',state:'PUBLICATION_UNCONFIRMED',terminal:true};
 current.paintControlReceipts({controls:[receipt]});assert.equal(current.settleControlReceipt(receipt),true);
 assert.equal(current.controlPending,null);assert.equal(current.pendingControls.has('claude'),false);assert.equal(current.snapshotTimer,null);assert.equal(current.find('[data-send]').disabled,false);assert.equal(current.find('[data-message]').value,'Newer composed input');
 assert.match(current.find('[data-status]').textContent,/publication is unconfirmed/);assert.equal(inputReceiptNeedsAttention(receipt),true);assert.match(current.find('[data-control-receipts]').textContent,/Publication unconfirmed/);
});

test('reload never reconstructs a pending slot from a terminal uncertain receipt',async()=>{
 const current=fixture();current.find('[data-message]').value='Unsent next input';current.persistComposerDraft('Unsent next input');
 const active={id:'queued-turn',capabilities:{observation:'events',can_offer_input:true,input_delivery_modes:['project_tool_boundary']}};
 globalThis.fetch=async()=>response({...sessionData('claude',active),execution:{project:'pilot',turn_id:'queued-turn',state:'RUNNING',controls:[{control_id:'uncertain',turn_id:'queued-turn',delivery_mode:'project_tool_boundary',state:'PUBLICATION_UNCONFIRMED',terminal:true}]}});
 await current.loadSession();assert.equal(current.controlPending??null,null);assert.equal(current.find('[data-send]').disabled,false);assert.equal(current.find('[data-message]').value,'Unsent next input');assert.match(current.find('[data-control-receipts]').textContent,/Publication unconfirmed/);
});

test('populated Context keeps full title, reading and parent while distinct Work remains concise',()=>{
 const current=fixture(),opened=[];current.sessionRows=[{id:'claude',title:'Independent review of the complete task and checker package with a long recorded title'}];current.onOpenWork=id=>opened.push(id);current.onReadTurn=()=>{};
 current.origin={workId:'WORK-recorded',packet:'packet-exact',parentTurnId:'WT-parent'};
 const context={task_id:'WORK-next',work_label:'Specify one checkable task and its complete persistence timeline',surface:'review',label:'History for this exact selected task',section_ids:[]};
 current.messageIntent={context};current.paintContext(context);const origin=current.find('[data-origin]'),detail=current.find('[data-context-inspection]');assert.equal(origin.textContent,'Recorded workNext-message work');assert.ok(!origin.textContent.includes('packet'));
 assert.match(detail.textContent,/Independent review of the complete task and checker package/);assert.match(detail.textContent,/History for this exact selected task/);assert.match(detail.textContent,/packet-exact/);assert.match(detail.textContent,/Read exact parent turn/);
 assert.match(origin.children[0].attrs['aria-label'],/WORK-recorded/);assert.match(origin.children[1].attrs['aria-label'],/complete persistence timeline/);origin.children[0].onclick();origin.children[1].onclick();assert.deepEqual(opened,['WORK-recorded','WORK-next']);
 current.active='WT-live';current.paintContext(context);assert.equal(origin.textContent,'Admitted workNext-message work');assert.match(detail.textContent,/Input goes to this admitted turn/);
});

test('input attention preserves ended uncertainty and never changes sender slot or draft',()=>{
 const current=fixture(),pending={id:'original-slot',turn:'WT-live'};current.active='WT-live';current.controlPending=pending;current.find('[data-message]').value='New unsent text';
 const row={turn_id:'WT-live',control_id:'CTRL-historical',state:'OFFERED_UNACKNOWLEDGED',error:'child ended before confirmation'};
 current.paintControlReceipts({controls:[row]});assert.equal(current.find('[data-input-attention]').hidden,false);assert.match(current.find('[data-input-attention]').textContent,/Reading unconfirmed/);assert.match(current.find('[data-control-receipts]').textContent,/child ended before confirmation/);
 current.paintControlReceipts({controls:[{...row,state:'PUBLISHED_AT_TOOL_BOUNDARY',publication:{scope:'PREVIEW'}}]});assert.equal(current.find('[data-input-attention]').hidden,false);
 current.paintControlReceipts({controls:[{...row,state:'EXACT_SCOPED_CONTROL_READ'}]});assert.equal(current.find('[data-input-attention]').hidden,true);assert.match(current.find('[data-control-receipts]').textContent,/Read by the session/);
 assert.equal(current.controlPending,pending);assert.equal(current.find('[data-message]').value,'New unsent text');
});

test('New conversation clears the former input notice while its exact receipt remains recoverable',async()=>{
 const current=fixture(),receipt={turn_id:'WT-ended',control_id:'CTRL-ended',state:'OFFERED_UNACKNOWLEDGED',error:'Original turn ended before reading was confirmed.'};
 const execution={project:'pilot',session_id:'claude',turn_id:'WT-ended',state:'FINISHED',controls:[receipt]};
 current.execution=execution;current.find('[data-message]').value='Original unsent draft';current.persistComposerDraft('Original unsent draft');current.paintControlReceipts();
 assert.equal(current.find('[data-input-attention]').hidden,false);assert.match(current.find('[data-control-receipts]').textContent,/Original turn ended/);
 assert.equal(current.newConversation(),true);assert.equal(current.execution,null);assert.equal(current.find('[data-input-attention]').hidden,true);assert.equal(current.find('[data-control-receipts]').textContent,'');
 current.paintControlReceipts(execution);assert.equal(current.find('[data-input-attention]').hidden,true);
 current.session='codex';current.paintControlReceipts(execution);assert.equal(current.find('[data-input-attention]').hidden,true);assert.equal(current.find('[data-control-receipts]').textContent,'');
 globalThis.fetch=async()=>response({...sessionData('claude'),execution});
 await current.openConversation('claude');assert.equal(current.find('[data-input-attention]').hidden,false);assert.match(current.find('[data-control-receipts]').textContent,/Original turn ended/);assert.equal(current.find('[data-message]').value,'Original unsent draft');
});

test('receipt Context close returns to attention opener or visible Context after settlement',()=>{
 const current=fixture(),focused=[];for(const key of ['[data-inspector]','[data-input-attention]','[data-context-open]'])current.find(key).focus=()=>focused.push(key);
 current.openInspector('context','[data-input-attention]');assert.equal(focused.at(-1),'[data-inspector]');current.openInspector(null);assert.equal(focused.at(-1),'[data-input-attention]');
 current.openInspector('context','[data-input-attention]');current.find('[data-input-attention]').hidden=true;current.openInspector(null);assert.equal(focused.at(-1),'[data-context-open]');
});

test('populated chrome moves exact scope/receipts/activity into one existing disclosure',async()=>{
 const source=await readFile(new URL('../src/laplace/web/static_shared/workspace-session.mjs',import.meta.url),'utf8'),markup=source.slice(source.indexOf('host.innerHTML=`'),source.indexOf('this.find=s=>host.querySelector(s)'));
 const inspector=markup.slice(markup.indexOf('<section class="session-inspector"'),markup.indexOf('</section><div class="session-execution-summary"'));
 for(const name of ['scope','control-receipts','activity-open']){assert.equal((markup.match(new RegExp('data-'+name+'(?=[ >])','g'))||[]).length,1);assert.ok(inspector.includes('data-'+name));}
 assert.match(markup,/aria-label="Project Review & notes">Review/);assert.match(markup,/aria-label="Refresh selected conversation">Refresh/);assert.ok(markup.includes('data-input-attention hidden'));assert.ok(markup.includes('data-stop hidden'));assert.ok(markup.includes('data-send'));
});

test('active compact mode uses the same delivery helper and keeps full explanation in Context',()=>{
 const current=fixture();current.active='WT-live';const full='Live public output from selected turn; source explanation retained without clipping.';
 for(const [caps,expected]of [[{can_steer:true,input_delivery_modes:['native_rpc']},/Native steering/],[{can_offer_input:true,input_delivery_modes:['project_tool_boundary']},/Queued input/],[null,/unreported/],[{can_steer:false},/No input capability offered/]]){
  current.activeCapabilities=caps;current.observationText(full);assert.equal(current.find('[data-observation]').textContent,full);assert.match(current.find('[data-observation-brief]').textContent,expected);assert.equal(current.active,'WT-live');
 }
 current.active='';current.observationText('Last observed turn ended: completed.');assert.equal(current.find('[data-observation-brief]').textContent,'Last observed turn ended: completed.');current.observationText('');assert.equal(current.find('[data-observation-brief]').hidden,true);
});

const {workSelectionFixture,workDetail}=await import('./helpers/work_selection_harness.mjs');
async function joinedWorkSession(){const current=fixture(),f=await workSelectionFixture({project:'pilot',session:current});current.getContext=()=>({surface:'work',label:f.owner.currentTask()?.title||'No selected work',task_id:f.owner.currentTask()?.id});current.pinMessageTarget(current.getContext(),f.controller.detail.task);current.onWorkAssociation=f.owner.restoreConversationWork;current.onWorkObservation=f.owner.refreshSelectedWork;current.find('[data-message]').value='Continue the explicit next Work';const posts=[];globalThis.fetch=async(path,options)=>{if(path==='/authoring/turn'){posts.push(JSON.parse(options.body));return response({turn_id:'WT-new',session_id:'claude'});}throw Error('Unexpected request '+path);};return {current,f,posts};}
test('actual Send ACK refreshes one selected owner detail after external status change, without a global reload',async()=>{
 const {current,f,posts}=await joinedWorkSession();try{f.rows.set('B',workDetail('pilot','B','in-progress'));assert.equal(f.owner.currentTask().status,'open');await current.send();assert.equal(posts.length,1);assert.equal(posts[0].work_id,'B');assert.equal(current.origin.workId,'B');assert.equal(current.origin.turnId,'WT-new');assert.equal(f.owner.currentTask().status,'in-progress');assert.match(f.host.querySelector('.operator-work-heading').textContent,/in-progress/);assert.equal(f.calls.length,1);assert.ok(f.calls[0].includes('view=detail'));await current.connect('WT-new');assert.equal(f.calls.length,1,'The same start observation cannot loop through selection');}finally{f.restore();}
});
test('new Next Work and newer draft survive the acknowledged old turn owner read',async()=>{
 const {current,f,posts}=await joinedWorkSession();try{let finish;f.setRead(url=>url.includes('id=B')?new Promise(resolve=>{finish=()=>resolve(workDetail('pilot','B','in-progress'));}):f.readDefault(url));const pending=current.send();await tick();assert.equal(posts.length,1);await f.owner.requestWorkSelection('C');current.find('[data-message]').value='NEW UNSENT THOUGHT';finish();await pending;assert.equal(posts[0].work_id,'B');assert.equal(current.origin.workId,'B');assert.equal(f.owner.currentTask().id,'C');assert.equal(f.controller.detail.task.id,'C');assert.equal(current.find('[data-message]').value,'NEW UNSENT THOUGHT');}finally{f.restore();}
});
test('owner refresh refusal after ACK preserves the started turn and prior coherent Work',async()=>{
 const {current,f,posts}=await joinedWorkSession();try{f.setRead(()=>{throw Error('OWNER READ REFUSED');});await current.send();assert.equal(posts.length,1);assert.equal(current.active,'WT-new');assert.equal(current.origin.workId,'B');assert.equal(f.owner.currentTask().id,'B');assert.equal(f.controller.detail.task.id,'B');assert.match(f.host.textContent,/Prior selection and drafts are retained/);assert.ok(Source.instances.length);}finally{f.restore();}
});
test('completion observation is a distinct once-only owner read, guarded by the actual conversation/turn',async()=>{
 const current=fixture(),events=[];current.origin={workId:'B',turnId:'WT-owned'};current.onWorkObservation=async(event,isCurrent)=>{events.push(event);assert.equal(isCurrent(),true);};await current.observeWork('start','WT-owned');await current.observeWork('start','WT-owned');await current.observeWork('complete','WT-owned');await current.observeWork('complete','WT-owned');await current.observeWork('complete','WRONG');assert.deepEqual(events.map(row=>[row.phase,row.project,row.session_id,row.turn_id,row.work_id]),[['start','pilot','claude','WT-owned','B'],['complete','pilot','claude','WT-owned','B']]);
});

test('actual finished conversation load preserves explicit Next Work and the previous conversation draft',async()=>{
 const current=fixture(),f=await workSelectionFixture({project:'pilot',session:current});try{
 current.getContext=()=>({surface:'work',label:f.owner.currentTask()?.title,task_id:f.owner.currentTask()?.id});current.pinMessageTarget(current.getContext(),f.controller.detail.task);current.onWorkAssociation=undefined;current.find('[data-message]').value='KEEP ORIGINAL DRAFT';current.persistComposerDraft('KEEP ORIGINAL DRAFT');
 globalThis.fetch=async()=>response({...sessionData('codex'),turns:[{id:'WT-old',work_id:'A',text:'Old request',reply:{status:'completed',text:'Old reply'}}]});
 await current.openConversation('codex');assert.equal(current.origin.workId,'A');assert.equal(f.owner.currentTask().id,'B');assert.equal(f.controller.detail.task.id,'B');assert.equal(new URL(location.href).searchParams.get('work'),'B');assert.equal(f.calls.length,0);assert.equal(JSON.parse(sessionStorage.getItem(current.composerBackupKey('claude'))).text,'KEEP ORIGINAL DRAFT');
 }finally{f.restore();}
});

test('a conversation opened without requested Work intent keeps its recorded association visible and selects nothing (pinned entry rule)',async()=>{
 const current=fixture(),f=await workSelectionFixture({project:'pilot',session:current,initial:null,explicit:false});try{
 current.getContext=()=>({surface:'work',task_id:f.owner.currentTask()?.id});current.onWorkAssociation=undefined;
 globalThis.fetch=async()=>response({...sessionData('codex'),turns:[{id:'WT-old',work_id:'A',text:'Old request',reply:{status:'completed',text:'Old reply'}}]});
 await current.openConversation('codex');assert.equal(current.origin.workId,'A','the association stays a fact of the conversation');assert.equal(f.owner.currentTask(),null,'it is not the selected Work');assert.equal(f.calls.length,0,'no owner detail read was made for it');assert.equal(new URL(location.href).searchParams.has('work'),false);
 current.paintContext(current.getContext());assert.ok(current.find('[data-origin]').children.some(node=>node.textContent==='Recorded work'),'the Recorded work door is the person\'s way to open it');
 }finally{f.restore();}
});

test('actual completion passes its selected-owner observation to known-effect adapter exactly once when origin differs',async()=>{
 const values=(await (await import('./helpers/work_selection_harness.mjs')).actualWorkEffectCases()).direct;
 const current=fixture();current.project='p';const f=await workSelectionFixture({project:'p',session:current});try{
 await f.controller.select('B',values.before);current.getContext=()=>({surface:'work',task_id:f.owner.currentTask()?.id,label:'Selected B'});current.origin={workId:'A',turnId:'T'};current.pinMessageTarget(current.getContext(),f.controller.detail.task);current.onWorkAssociation=undefined;current.onWorkObservation=f.owner.refreshSelectedWork;current.onChanged=f.owner.runChanged;
 f.setRead(()=>structuredClone(values.before));await current.connect('T');await tick();f.calls.length=0;f.setRead(()=>structuredClone(values.after));
 globalThis.fetch=async path=>path.startsWith('/authoring/state?')?response({sessions,session_count:2}):response({...sessionData('claude'),session:{...sessionData('claude').session,project:'p'},turns:[{id:'T',work_id:'A',text:'Admitted A',reply:{status:'completed',text:'Completed A'}}]});
 Source.instances.at(-1).emit({type:'complete',result:{status:'completed',actions:[{operation:'task_status',outcome:{views:['project','pipeline'],identities:['B'],status:'SUCCEEDED'}}]}});await tick();await tick();
 assert.equal(current.origin.workId,'A');assert.equal(f.owner.currentTask().id,'B');assert.equal(f.controller.detail.task.lifecycle.completed,true);assert.equal(f.calls.length,1,'Completion and known effect share one owner read, not two');assert.ok(f.calls[0].includes('view=detail'));
 }finally{f.restore();}
});

test('actual conversation open and refresh preserve each restored authored attachment',async()=>{
 const current=fixture();route(current,{claudeActive:null});
 current.find('[data-message]').value='Draft A';current.pinMessageTarget({surface:'manuscript',label:'A',selection:{files:['a.tex'],quote:'A'}});
 await current.openConversation('codex');assert.equal(current.selectionOverride,null);
 current.find('[data-message]').value='Draft B';current.pinMessageTarget({surface:'manuscript',label:'B',selection:{files:['b.tex'],quote:'B'}});
 await current.openConversation('claude');assert.equal(current.find('[data-message]').value,'Draft A');assert.deepEqual(current.selectionOverride,{files:['a.tex'],quote:'A'});assert.equal(current.authoredContext().label,'A');
 await current.loadSession();assert.deepEqual(current.selectionOverride,{files:['a.tex'],quote:'A'});
 await current.openConversation('codex');assert.equal(current.find('[data-message]').value,'Draft B');assert.deepEqual(current.selectionOverride,{files:['b.tex'],quote:'B'});
});

test('a long reply row shows its excerpt with a control that reads the complete saved reply',async()=>{
 const current=fixture(),inspected=[];current.onReadTurn=(id,options)=>inspected.push({id,options});
 current.appendTurn({id:'turn-long',text:'Summarise.',reply:{status:'completed',display_text:'R'.repeat(4000),display_text_chars:100000,display_text_truncated:true},steering:[{id:'s1',text:'one'}],steering_total:7,steering_truncated:true,detail:{turn_id:'turn-long',views:['actions','failures','turn']}});
 const thread=current.find('[data-thread]'),buttons=[];const visit=node=>{if(node.tag==='button')buttons.push(node);for(const child of node.children||[])visit(child);};visit(thread);
 assert.match(thread.textContent,/Reply shortened to 4,000 of 100,000 characters/);assert.match(thread.textContent,/Showing 1 of 7 steering messages/);
 const read=buttons.find(node=>node.textContent==='Read the complete reply');assert.ok(read,'the complete reply is an actual control, not only a handle');
 await read.onclick();assert.equal(inspected[0].id,'turn-long');
});

test('bounded draft attachments, quotes and proposal-answer fallbacks say so and lead to the exact turn',async()=>{
 const current=fixture(),inspected=[];current.onReadTurn=(id,options)=>inspected.push({id,options});
 current.appendTurn({id:'turn-bounded',text:'Shorten this.',selection:{files:['paper/body.tex'],quote:'Q'.repeat(2000),quote_chars:100000,quote_truncated:true},unsaved_draft:{status:'UNSAVED',format:'tex',text:'D'.repeat(2000),text_chars:100000,text_truncated:true,reason:'why',anchor:{file:'paper/body.tex',line_start:1,line_end:2}},
  proposal_answer:'A'.repeat(4000),proposal_answer_chars:100000,proposal_answer_truncated:true,proposal_edit_count:1,proposal_state:'saved-without-final-reply',detail:{turn_id:'turn-bounded',views:['actions','failures','turn']}});
 const thread=current.find('[data-thread]'),buttons=[];const visit=node=>{if(node.tag==='button')buttons.push(node);for(const child of node.children||[])visit(child);};visit(thread);
 assert.match(thread.textContent,/Draft shortened to 2,000 of 100,000 characters/);assert.match(thread.textContent,/Quoted passage shortened to 2,000 of 100,000 characters/);
 assert.match(thread.textContent,/Proposal answer shortened to 4,000 of 100,000 characters/);
 const read=buttons.find(node=>node.textContent==='Read the complete reply');assert.ok(read);await read.onclick();assert.equal(inspected[0].id,'turn-bounded');
});
