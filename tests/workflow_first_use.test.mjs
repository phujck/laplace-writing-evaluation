// Production controller with a local DOM/transport double. These are identity,
// draft and navigation controls, not browser geometry or actual-owner evidence.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {installDOM,Node,findButton} from './helpers/evidence_reader_harness.mjs';
import {mountWorkflowEditor,savedWorkflowExpectation,checkedSavedWorkflow} from '../src/laplace/web/static_shared/workspace-workflow-editor.mjs';
const copy=value=>structuredClone(value),entry='/work/workflow-definitions';
const ref=version=>({schema_version:'laplace.reference/1',owner:'pipeline.workflow',kind:'workflow-definition',identity:{id:'WDEF-public'},version:{definition_revision:version}});
const handle=version=>{const request={definition_id:'WDEF-public',...(version?{version}:{})};return {request,http:{method:'GET',url:entry+'?'+new URLSearchParams(request)},native:{operation:'project',payload:{view:'workflow-definitions',request}}};};
const definition=title=>({schema_version:'laplace.workflow-definition/1',title,description:'Read the evidence, then explain the finding.',settings:{},layout:{},edges:[],steps:[{id:'read',title:'Read evidence',parent_id:null,assignment:{role:'builder',instructions:'EXACT SAVED INSTRUCTIONS α',settings:{}},inputs:[],outputs:[]}]});
const owner=version=>({schema_version:'laplace.workflow-definition/1',scope_id:'public-scope',scope:{kind:'owned-workspace'},definition_id:'WDEF-public',version,head_revision:'v2',reference:ref(version),is_current:version==='v2',definition:definition('Saved '+version),read:handle(version),current_read_handle:handle(),history:['v2','v1'].map(version=>({version,read:handle(version)})),actions:{save:{permitted:true,http:{method:'POST',url:entry+'/save'},payload:{definition_id:'WDEF-public',expected_revision:version}},use_in_conversation:{available:false,permitted:false}}});
const listing={scope_id:'public-scope',scope:{kind:'owned-workspace'},definitions:[{definition_id:'WDEF-public',title:'Saved v2',read:handle()}],actions:{create:{permitted:true,http:{method:'POST',url:entry+'/save'},payload:{expected_revision:null}}}};
const field=(host,name)=>host.all().find(node=>node.dataset?.field===name);
async function setup({reply=null,storageFailure=false,initial=null,starter=false,helpInDialog=null}={}){
 const dom=installDOM(),old={location:globalThis.location,matchMedia:globalThis.matchMedia};globalThis.location={href:'http://local/project?workspace=writing&app=workflows&return_project=p'};globalThis.matchMedia=()=>({matches:true,addEventListener(){},removeEventListener(){}});document.addEventListener=()=>{};document.removeEventListener=()=>{};
 const host=new Node('main');host.addEventListener=()=>{};host.removeEventListener=()=>{};document.body.append(host);const records=new Map(initial?[['laplace:workflow-drafts:public-scope',JSON.stringify(initial)]]:[]),calls=[],destinations=[];
 const storage={getItem:key=>records.get(key)??null,setItem:(key,value)=>{if(storageFailure)throw Error('PUBLIC STORAGE FAILURE');records.set(key,value);},removeItem:key=>records.delete(key)};
 const editor=await mountWorkflowEditor(host,{storage,helpInDialog,navigate:async url=>destinations.push(url),request:async(url,payload)=>{calls.push({url,payload});assert.equal(payload,undefined,'reading/navigation must issue zero POSTs');if(url===entry)return copy(starter?{...listing,starters_read:{http:{method:'GET',url:entry+'?facet=starters'}}}:listing);if(new URL(url,'http://local').searchParams.get('facet')==='starters')return {schema_version:'laplace.workflow-definition/1',starters:[definition('Public starter')]};const version=new URL(url,'http://local').searchParams.get('version')||'v2';return reply?reply(url,version):owner(version);}});
 return {host,editor,calls,records,destinations,restore(){editor.destroy();globalThis.location=old.location;globalThis.matchMedia=old.matchMedia;dom.restore();}};
}
async function selected(s){await s.editor.port.dispatch({type:'select',id:'WDEF-public',read:handle()});await s.editor.port.dispatch({type:'step',id:'read'});}
const historyButton=s=>findButton(s.host,'Earlier saved version · item 2 in this list');

test('saved version is a separate exact readonly visit while Unicode draft and original guard remain unchanged',async()=>{
 const s=await setup();try{await selected(s);await s.editor.port.dispatch({type:'edit',edit:{type:'fields',fields:{title:'LOCAL Ω DRAFT'}}});const before=s.editor.port.capture(),opener=historyButton(s);opener.focus();assert.equal(await opener.onclick(),true);
 const pane=s.host.querySelector('.workflow-saved-reading');assert.equal(pane.hidden,false);assert.match(pane.textContent,/Saved v1/);assert.match(pane.textContent,/EXACT SAVED INSTRUCTIONS α/);assert.doesNotMatch(pane.textContent,/LOCAL Ω DRAFT/);assert.deepEqual(s.editor.port.capture(),before);assert.equal(s.host.querySelector('.workflow-detail').hidden,true);assert.equal(s.calls.length,3);
 // A same-ID background repaint recreates the opener without changing the visit.
 await s.editor.port.dispatch({type:'step',id:'read'});const newOpener=historyButton(s);assert.notEqual(newOpener,opener);findButton(s.host,'Close saved version').onclick();assert.equal(pane.hidden,true);assert.equal(document.activeElement,newOpener);assert.equal(newOpener.closest('details').open,true);assert.equal(field(s.host,'Workflow title').value,'LOCAL Ω DRAFT');assert.deepEqual(s.editor.port.capture(),before);
 }finally{s.restore();}
});

test('wrong saved version, custody scope, caller scope or reference never publishes body or raw details',async()=>{
 for(const change of [v=>v.version='v3',v=>v.scope={kind:'project',namespace:'foreign'},v=>v.scope_id='foreign',v=>v.reference=ref('v3'),v=>v.definition_id='WDEF-other']){
  const s=await setup({reply:async(_url,version)=>{const value=owner(version);if(version==='v1'){value.definition.title='FOREIGN BODY MUST STAY HIDDEN';change(value);}return value;}});try{await selected(s);const before=s.editor.port.capture();assert.equal(await historyButton(s).onclick(),false);const pane=s.host.querySelector('.workflow-saved-reading');assert.match(pane.textContent,/unavailable/);assert.doesNotMatch(pane.textContent,/FOREIGN BODY/);assert.equal(pane.querySelectorAll('pre').length,0);assert.deepEqual(s.editor.port.capture(),before);}finally{s.restore();}
 }
});

test('saved read handle must agree with expected history coordinates and all companion carriers',()=>{
 const expected=savedWorkflowExpectation(owner('v2'),{version:'v1',read:handle('v1')});assert.equal(checkedSavedWorkflow(owner('v1'),expected).definition.title,'Saved v1');
 for(const mutate of [h=>h.request.version='v2',h=>h.native.payload.request.version='v2',h=>h.http.url+='&version=v2',h=>h.http.url=h.http.url.replace('WDEF-public','WDEF-other')]){const h=copy(handle('v1'));mutate(h);assert.throws(()=>savedWorkflowExpectation(owner('v2'),{version:'v1',read:h}),/does not match/);}
});

test('late saved success and failure cannot replace the editor after explicit Close',async()=>{
 for(const fail of [false,true]){let resolve,reject;const gate=new Promise((a,b)=>{resolve=a;reject=b;});const s=await setup({reply:async(_url,version)=>version==='v1'?gate:owner(version)});try{await selected(s);const pending=historyButton(s).onclick();findButton(s.host,'Close saved version').onclick();const later=new Node('button');document.body.append(later);later.focus();if(fail)reject(Error('LATE ERROR'));else resolve(owner('v1'));await pending;assert.equal(s.host.querySelector('.workflow-saved-reading').hidden,true);assert.equal(document.activeElement,later);assert.equal(s.editor.port.snapshot().read.value.version,'v2');assert.doesNotMatch(s.host.querySelector('.workflow-notice').textContent,/LATE ERROR/);}finally{s.restore();}}
});

test('Return choice preserves local draft, needs explicit leave and verifies storage before navigation',async()=>{
 const s=await setup();try{await s.editor.port.dispatch({type:'create'});await s.editor.port.dispatch({type:'edit',edit:{type:'fields',fields:{title:'Unsaved Ω'}}});const before=s.editor.port.capture(),opener=new Node('a');document.body.append(opener);opener.focus();assert.equal(await s.editor.requestNavigation('/project?workspace=writing&corpus=p',{opener}),false);assert.deepEqual(s.destinations,[]);assert.match(s.host.querySelector('.workflow-notice').textContent,/Keep draft and leave/);findButton(s.host,'Stay in workflow').onclick();assert.equal(document.activeElement,opener);assert.deepEqual(s.editor.port.capture(),before);
 await s.editor.requestNavigation('/project?workspace=writing&corpus=p',{opener});await findButton(s.host,'Keep draft and leave').onclick();assert.deepEqual(s.destinations,['/project?workspace=writing&corpus=p']);assert.deepEqual(JSON.parse([...s.records.values()][0]).drafts,before.drafts);assert.equal(s.editor.leaveGuard({preventDefault(){throw Error('should be safely stored navigation');}}),false);assert.equal(s.calls.length,1);
 }finally{s.restore();}
});

test('storage failure and superseded leave choices do not navigate or discard',async()=>{
 const s=await setup({storageFailure:true});try{await s.editor.port.dispatch({type:'create'});const before=s.editor.port.capture();await s.editor.requestNavigation('/project?corpus=p');const stale=findButton(s.host,'Keep draft and leave');await s.editor.requestNavigation('/project?app=projects');await stale.onclick();assert.deepEqual(s.destinations,[]);await findButton(s.host,'Keep draft and leave').onclick();assert.deepEqual(s.destinations,[]);assert.match(s.host.querySelector('.workflow-notice').textContent,/could not be stored/);assert.deepEqual(s.editor.port.capture(),before);}finally{s.restore();}
});

test('pending original wire survives reload and a saved visit without adoption or resend',async()=>{
 const current=owner('v2'),initial={schema:'laplace.workflow-drafts/1',scope_id:'public-scope',drafts:[{id:'WDEF-public',definition:definition('NEWER Ω'),basis:current.actions.save,read:current.read}],attempts:[{id:'WDEF-public',operation:'save',request_id:'original',status:'pending',payload:{definition:definition('SUBMITTED'),expected_revision:'v2'},definition:definition('SUBMITTED')}],contexts:[],selection:{id:'WDEF-public',read:current.read}};
 const s=await setup({initial});try{const before=s.editor.port.capture();assert.equal(before.attempts[0].status,'uncertain');await historyButton(s).onclick();findButton(s.host,'Close saved version').onclick();assert.deepEqual(s.editor.port.capture(),before);assert.equal(s.calls.filter(row=>row.payload).length,0);assert.equal(s.editor.port.snapshot().draft.basis.payload.expected_revision,'v2');}finally{s.restore();}
});

test('selected task frame leads with purpose and truthful scope; history stays explicitly bounded',async()=>{
 const s=await setup();try{await selected(s);assert.equal(s.host.querySelector('.workflow-library-chooser').open,false);assert.equal(findButton(s.host,'List view').getAttribute('aria-pressed'),'true');assert.match(s.host.querySelector('.workflow-next').textContent,/App runs require a supported project workflow/);assert.doesNotMatch(s.host.querySelector('.workflow-next').textContent,/share/);assert.match(s.host.querySelector('.workflow-history').textContent,/Up to 32/);assert.equal(findButton(s.host,'Prepare agent run…'),undefined);assert.ok(s.host.classList.contains('workflow-step-selected'));assert.ok(field(s.host,'Workflow title'));assert.match(s.host.textContent,/optional/);}finally{s.restore();}
});


test('starters are rows of the opening list with their stages drawn, not a dialog; using one makes an unsaved draft',async()=>{
 let mounted=0;const s=await setup({starter:true,helpInDialog:()=>{mounted++;return {dispose(){}};}});try{
 assert.equal(findButton(s.host,'Start from a research workflow'),undefined);assert.equal(s.calls.length,2);const templates=s.host.querySelector('.workflow-templates');assert.match(templates.textContent,/Start from a template/);assert.match(templates.textContent,/Public starter/);assert.match(templates.querySelector('.workflow-mini').textContent,/Read evidence/);
 const use=findButton(templates,'Use this template');assert.ok(use);assert.equal(mounted,0);assert.equal(s.editor.port.snapshot().selection,null);await use.onclick();assert.equal(s.editor.port.snapshot().draft.definition.title,'Public starter');assert.equal(mounted,0);assert.equal(s.calls.length,2);
 }finally{s.restore();}
});
test('local native return uses the existing explicit keep/stay guard and retains exact draft before callback',async()=>{const s=await setup();try{await selected(s);await s.editor.port.dispatch({type:'edit',edit:{type:'fields',fields:{title:'LOCAL RETURN Ω'}}});const before=s.editor.port.capture();let returned=0;assert.equal(await s.editor.requestReturn(()=>returned++,{opener:field(s.host,'Workflow title')}),false);assert.equal(returned,0);findButton(s.host,'Stay in workflow').onclick();assert.equal(returned,0);await s.editor.requestReturn(()=>returned++);await findButton(s.host,'Keep draft and leave').onclick();assert.equal(returned,1);assert.deepEqual(s.editor.port.capture(),before);assert.match([...s.records.values()].join(''),/LOCAL RETURN Ω/);}finally{s.restore();}});
