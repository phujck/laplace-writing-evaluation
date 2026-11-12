import {beforeEach,test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const modulePath=new URL('../src/laplace/web/static_shared/workspace-app.mjs',import.meta.url),stylePath=new URL('../src/laplace/web/static_shared/workspace-writing-style.mjs',import.meta.url);
const source=(await readFile(modulePath,'utf8')).replace("'./profile-preferences.mjs'",JSON.stringify(new URL('../src/laplace/web/static_shared/profile-preferences.mjs',import.meta.url).href)).replace("'/shared/workspace-presentation.mjs'",JSON.stringify(new URL('../src/laplace/web/static_shared/workspace-presentation.mjs',import.meta.url).href)).replace("'/shared/workspace-writing-style.mjs'",JSON.stringify(stylePath.href)).replace("'/shared/workspace-material-observation.mjs'",JSON.stringify(new URL('../src/laplace/web/static_shared/workspace-material-observation.mjs',import.meta.url).href));
const {appLink,bindAppLink,projectReturnURL,mountAppNavigation,mountAppSettings,mountWorkspaceDependencies}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const profileWire=JSON.parse(await readFile(new URL('./fixtures/editor_spine/profile-candidates.json',import.meta.url),'utf8'));
class Node{
 constructor(tag='div'){this.tag=tag;this.children=[];this.attrs={};this._text='';this.value='';this.className='';this.isConnected=true;this.hidden=false;this.disabled=false;this.classList={add:v=>this.className+=' '+v,remove:v=>this.className=this.className.split(' ').filter(x=>x!==v).join(' ')};}
 set textContent(v){this._text=String(v??'');this.children=[];}get textContent(){return this._text+this.children.map(n=>n.textContent).join('');}append(...nodes){for(const n of nodes){n.parentElement=this;this.children.push(n);}}replaceChildren(...nodes){this._text='';this.children=[];this.append(...nodes);}setAttribute(k,v){this.attrs[k]=String(v);}get lastElementChild(){return this.children.at(-1);}all(){return [this,...this.children.flatMap(n=>n.all())];}querySelector(s){return this.all().slice(1).find(n=>s.startsWith('.')?n.className.split(' ').includes(s.slice(1)):n.tag===s);}after(n){const p=this.parentElement;p.children.splice(p.children.indexOf(this)+1,0,n);n.parentElement=p;}remove(){this.isConnected=false;this.parentElement.children=this.parentElement.children.filter(n=>n!==this);}focus(){document.activeElement=this;}
}
beforeEach(()=>{globalThis.document={createElement:tag=>new Node(tag)};globalThis.window={addEventListener(){},removeEventListener(){}};delete globalThis.location;delete globalThis.history;});
const button=(host,label)=>host.all().find(n=>n.tag==='button'&&n.textContent===label),field=(host,label)=>host.all().find(n=>n.attrs['aria-label']===label||n.tag==='label'&&n._text===label)?.children[0]||host.all().find(n=>n.attrs['aria-label']===label),input=(host,label)=>host.all().find(n=>n.tag==='label'&&n._text===label)?.children[0],formOf=n=>{while(n&&n.tag!=='form')n=n.parentElement;return n;};
const voice=()=>({project:null,scope:'global',selected_profile:null,profile:'profiles/voice/main.md',inspected_profile:'profiles/voice/main.md',profile_title:'Shared voice',profile_version:'v1',profile_revision:'profile-1',revision:'global-1',profile_editable:true,content:'# Shared voice\nKeep reasoning connected.',runtime_content:'Keep reasoning connected.',provenance:{revision:'prov-1',status:'NOT_RECORDED'},guidance:'',genre:'',profiles:[{path:'profiles/voice/main.md',title:'Shared voice',version:'v1',status:'AVAILABLE'},{path:'profiles/voice/other.md',title:'Other voice',version:'v1',status:'AVAILABLE'}]});
function summary(){return {providers:{cached:true,providers:[{id:'codex',name:'Codex',available:false,auth_state:'UNVERIFIED',models:[{id:'sol',tier:'deep',session_default:true}]}]},model_policy:{row_source:'pipeline.schema TIERS',law:'Session runs at highest tier',tiers:{deep:{codex:'sol'}},role_defaults:{session:{tier:'deep',effort:'high',models:{codex:'sol'}}}},runtime:{observed:{version:'3.14.7'},declared:{lifecycle:{python:'/declared/python'}},revision:'runtime-1'},voice:voice(),gaps:[{reason:'No global model mutation owner exists; project/session defaults remain local.'}]};}
async function settingsFixture({fail=false}={}){const host=new Node(),calls=[],dirties=[];let state=voice();const request=async(path,payload)=>{calls.push({path,payload});if(payload){if(fail)throw Error('profile revision conflict');state={...state,content:payload.content,runtime_content:payload.content,profile_revision:'profile-2',revision:'global-2'};return state;}if(path==='/projects/app-settings')return summary();if(path==='/authoring/providers?refresh=1')return {...summary().providers,cached:false};return state;};const controller=await mountAppSettings(host,{request,onDirty:v=>dirties.push(v)});return {host,calls,dirties,controller};}
test('application navigation exists without a project and restores workspace dependency return context',()=>{
 const host=new Node();mountAppNavigation(host,'settings');assert.equal(host.all().filter(n=>n.tag==='a').length,4);assert.ok(host.all().some(n=>n.textContent==='App settings'&&n.attrs['aria-current']==='page'));assert.ok(!host.textContent.includes('Return to project'));
 const back='/project?workspace=writing&app=dependencies&query=shared&offset=20&inspect_id=MAT-a';const href='http://local/project?workspace=writing&corpus=consumer&view=material&app_return='+encodeURIComponent(back);assert.equal(appLink('dependencies',href),back);assert.match(appLink('settings',href),/return_project=consumer/);assert.match(appLink('projects','http://local/project?app=settings&return_project=consumer&return_view=material'),/return_view=material/);
});
test('global settings is passive, policy is inspectable, project forms and no-op conversation actions are absent',async()=>{
 const v=await settingsFixture();assert.ok(!v.calls.some(r=>r.path.includes('refresh=1')||r.path.includes('/work/state')||r.path.includes('projects/library')));assert.match(v.host.textContent,/UNVERIFIED/);assert.match(v.host.textContent,/pipeline.schema TIERS/);assert.match(v.host.textContent,/No global model mutation owner/);assert.equal(input(v.host,'Project guidance and approved examples'),undefined);assert.equal(button(v.host,'Save project writing settings'),undefined);assert.equal(button(v.host,'Refine from my feedback'),undefined);assert.ok(button(v.host,'Edit shared profile'));await button(v.host,'Refresh provider availability').onclick();assert.equal(v.calls.filter(r=>r.path.includes('refresh=1')).length,1);assert.ok(!v.calls.some(r=>r.path.includes('/authoring/turn')));
});
test('global voice edit uses profile guard and explicit action without dummy project; refresh does not erase a draft',async()=>{
 const v=await settingsFixture();await button(v.host,'Edit shared profile').onclick();const text=input(v.host,'Shared profile content');text.value='My global preference';input(v.host,'Reason for this preference').value='Human instruction';formOf(text).oninput();await button(v.host,'Refresh provider availability').onclick();assert.equal(text.value,'My global preference');const select=v.host.all().find(n=>n.attrs['aria-label']==='Global voice profile');select.value='profiles/voice/other.md';await select.onchange();assert.equal(select.value,'profiles/voice/main.md');assert.equal(v.controller.hasDraft,true);await formOf(text).onsubmit({preventDefault(){}});const write=v.calls.find(r=>r.payload);assert.equal(write.path,'/projects/app-settings');assert.equal(write.payload.action,'voice-profile');assert.equal(write.payload.expected_profile_revision,'profile-1');assert.equal(Object.hasOwn(write.payload,'project'),false);assert.equal(v.controller.hasDraft,false);
});
test('global voice conflict retains the exact draft and guard without applying settings elsewhere',async()=>{
 const v=await settingsFixture({fail:true});await button(v.host,'Edit shared profile').onclick();const text=input(v.host,'Shared profile content');text.value='Retain this edit';input(v.host,'Reason for this preference').value='Preference';formOf(text).oninput();await formOf(text).onsubmit({preventDefault(){}});assert.equal(text.value,'Retain this edit');assert.equal(v.controller.hasDraft,true);assert.match(v.host.textContent,/revision conflict/);assert.equal(v.calls.filter(r=>r.payload).length,1);
});
test('actual global structural-preferences category lazily mounts its owner and explicit project picker',async()=>{
 const host=new Node(),calls=[];const request=async(path,payload)=>{calls.push({path,payload});if(path==='/projects/app-settings')return summary();const q=new URL(path,'http://local').searchParams;if(path.startsWith('/work/profiles?')){if(q.get('view')==='candidates')return {candidates:[],pagination:{total:0,returned:0}};return structuredClone(q.has('project')?profileWire.before:profileWire.global_summary);}if(q.get('view')==='profile-contexts')return {projects:[{name:'book',title:'Fixture Book'}]};return voice();};
 const controller=await mountAppSettings(host,{request});assert.equal(calls.some(row=>row.path.startsWith('/work/profiles')),false);
 await button(host,'Structural preferences').onclick();await new Promise(resolve=>setImmediate(resolve));
 assert.match(host.textContent,/shared across the workspace/);assert.ok(button(host,'Generate suggestion'));
 await button(host,'Generate suggestion').onclick();assert.ok(calls.some(row=>row.path.includes('view=profile-contexts')));
 assert.equal(calls.some(row=>row.payload),false);assert.equal(calls.some(row=>row.path.includes('/authoring/turn')),false);
 const select=host.all().find(node=>node.tag==='select'&&node.attrs['aria-label']==='Producing project');assert.ok(select);assert.equal(select.value,'');controller.destroy();
});
test('global dependency listing is lazy, qualified, filtered and restores exact owner/project navigation',async()=>{
 const host=new Node(),calls=[];const row={id:'MAT-a',relation:'uses-material',consumer:{project:'consumer',title:'Consumer'},target:{owner:'artifact',project:'producer',path:'notes.txt'},consumed_revision:'source-old'};
 const request=async path=>{calls.push(path);const q=new URL(path,'http://local').searchParams;if(q.get('view')==='workspace-source')return {...row,project:'consumer',currentness:'CHANGED_INPUT',current_revision:'source-new',owner_result:{content:'Current producer bytes'}};return {references:[row],projects:[{id:'consumer',title:'Consumer'}],offset:Number(q.get('offset')),total:2,next_offset:q.get('offset')==='20'?null:20,coverage:[{kind:'task-prerequisites',owner:'project_work',listing:'project-local; open project Dependencies'}]};};
 await mountWorkspaceDependencies(host,{request,parameters:new URLSearchParams()});assert.equal(calls.length,1);assert.match(calls[0],/view=workspace/);assert.match(host.textContent,/currentness has not been inspected/);await button(host,'Inspect binding').onclick();assert.match(calls[1],/consumer=consumer/);assert.match(host.textContent,/Current producer bytes/);assert.match(host.textContent,/Consumed: source-old/);assert.match(host.textContent,/Owner changed/);const link=host.all().find(n=>n.tag==='a'&&n.textContent==='Open binding in project');const q=new URL(link.href,'http://local').searchParams;assert.equal(q.get('corpus'),'consumer');assert.equal(q.get('binding'),'MAT-a');assert.match(q.get('app_return'),/inspect_id=MAT-a/);await button(host,'More dependencies').onclick();assert.match(calls.at(-1),/offset=20/);const count=calls.length;await button(host,'Refresh dependency index').onclick();assert.equal(calls.length,count+1,'refresh reads only registry index');assert.match(host.textContent,/project-local/);
});
test('late profile reads cannot replace the active draft controller or retarget its save',async()=>{
 const host=new Node(),paths=['profiles/voice/main.md','profiles/voice/other.md','profiles/voice/third.md'];
 const profiles=paths.map(path=>({path,title:path,version:'v1',status:'AVAILABLE'}));
 const value=path=>({...voice(),profile:path,inspected_profile:path,profile_revision:'revision-'+path,content:'Source '+path,runtime_content:'Guidance '+path,profiles});
 let release,hold=true;const writes=[];
 const request=async(path,payload)=>{
  if(payload){writes.push(payload);return value(payload.profile);}
  if(path==='/projects/app-settings')return {...summary(),voice:value(paths[0])};
  const profile=new URL(path,'http://fixture').searchParams.get('profile');
  if(profile===paths[1]&&hold){hold=false;await new Promise(resolve=>{release=resolve;});}
  return value(profile);
 };
 const controller=await mountAppSettings(host,{request});
 const choice=host.all().find(n=>n.attrs['aria-label']==='Global voice profile');
 choice.value=paths[1];const pending=choice.onchange();assert.ok(release);
 choice.value=paths[2];await choice.onchange();await button(host,'Edit shared profile').onclick();
 const text=input(host,'Shared profile content');text.value='Retain the third-profile draft.';
 input(host,'Reason for this preference').value='An explicit preference.';formOf(text).oninput();
 assert.equal(controller.hasDraft,true);release();await pending;
 assert.equal(controller.hasDraft,true);assert.equal(input(host,'Shared profile content'),text);
 choice.value=paths[0];await choice.onchange();
 assert.equal(choice.value,paths[2]);assert.equal(text.value,'Retain the third-profile draft.');
 await formOf(text).onsubmit({preventDefault(){}});
 assert.equal(writes.length,1);assert.equal(writes[0].profile,paths[2]);
 assert.equal(writes[0].expected_profile_revision,'revision-'+paths[2]);controller.destroy();
});
test('workspace dependency pages carry the registry cut and never combine changed membership',async()=>{
 const host=new Node(),calls=[],row={id:'MAT-a',relation:'uses-material',consumer:{project:'one',title:'One'},target:{owner:'artifact',project:'two',path:'notes.txt'},consumed_revision:'source-old'};
 let changed=false;
 const request=async path=>{calls.push(path);const q=new URL(path,'http://fixture').searchParams;return {references:[{...row,id:changed?'MAT-new':'MAT-a'}],projects:[],offset:Number(q.get('offset')),total:2,next_offset:1,registry_revision:changed?'registry-new':'registry-old'};};
 await mountWorkspaceDependencies(host,{request});changed=true;
 host.all().find(n=>n.attrs['aria-label']==='Find owner, path or project').value='Unsubmitted filter';
 await button(host,'More dependencies').onclick();
 assert.equal(new URL(calls[1],'http://fixture').searchParams.get('as_of'),'registry-old');
 assert.equal(new URL(calls[1],'http://fixture').searchParams.get('query'),'');
 assert.match(host.textContent,/dependencies changed between pages/);
 assert.equal(host.all().filter(n=>n.className==='material-row').length,1);
 assert.equal(button(host,'More dependencies').hidden,true);
 await button(host,'Refresh dependency index').onclick();
 assert.equal(new URL(calls.at(-1),'http://fixture').searchParams.has('as_of'),false);
 assert.equal(host.all().filter(n=>n.className==='material-row').length,1);
});


test('settings categories work without a project and switching categories retains shared voice drafts',async()=>{
 const v=await settingsFixture();const nav=v.host.all().find(n=>n.attrs['aria-label']==='Settings categories');assert.equal(nav.children.length,5);assert.ok(button(v.host,'Structural preferences'));assert.equal(button(v.host,'Models & providers').attrs['aria-current'],'page');const before=v.calls.length;await button(v.host,'Writing & voice').onclick();assert.equal(v.calls.length,before);await button(v.host,'Edit shared profile').onclick();const text=input(v.host,'Shared profile content');text.value='A retained voice draft';formOf(text).oninput();await button(v.host,'Runtime').onclick();await button(v.host,'Writing & voice').onclick();assert.equal(text.value,'A retained voice draft');assert.equal(v.controller.hasDraft,true);assert.ok(!v.calls.some(row=>row.payload));
});

test('workspace source continuation uses qualified consumer handle and shares changed-basis restart',async()=>{
 const host=new Node(),calls=[],row={id:'MAT-a',relation:'uses-material',consumer:{project:'consumer',title:'Consumer'},target:{owner:'repository',repository:'declared',path:'criteria.md'},consumed_revision:'old'},start='/projects/material-references?view=workspace-source&consumer=consumer&id=MAT-a&offset=0&limit=2',next=start.replace('offset=0','offset=2');
 const handle=url=>({http:{method:'GET',url}});let restarted=false;
 const request=async path=>{calls.push(path);const q=new URL(path,'http://local').searchParams;if(q.get('view')==='workspace')return {references:[row],projects:[{id:'consumer'}],offset:0,total:1,next_offset:null};if(q.get('offset')==='2')return {...row,current_revision:'new',currentness:'CHANGED_INPUT',owner_result:{content:'MOVED'}};if(path===start){restarted=true;return {...row,current_revision:'new',currentness:'CHANGED_INPUT',owner_result:{content:'RESTARTED'}};}return {...row,current_revision:'first',currentness:'CHANGED_INPUT',owner_result:{content:'π🌱'},read_handle:handle(next),restart_read:handle(start)};};
 await mountWorkspaceDependencies(host,{request,parameters:new URLSearchParams()});await button(host,'Inspect binding').onclick();await button(host,'Read more source').onclick();assert.ok(!host.textContent.includes('MOVED'));assert.match(host.textContent,/changed between pages/);await button(host,'Restart source observation').onclick();assert.ok(restarted);assert.match(host.textContent,/RESTARTED/);assert.equal(calls.at(-2),next);assert.equal(calls.at(-1),start);
});

for(const phase of ['initial','continuation'])for(const late of ['unchanged','changed','error'])test('connected workspace slot discards superseded '+phase+' '+late+', retaining current consumer basis',async()=>{
 const host=new Node(),target={owner:'repository',repository:'declared',path:'source.md'},row={id:'MAT-one',relation:'uses-material',consumer:{project:'consumer',title:'Consumer'},target,consumed_revision:'historical'};let count=0,release;
 const next='/projects/material-references?view=workspace-source&consumer=consumer&id=MAT-one&offset=2';
 const observation=(revision,content,more=false)=>({...row,currentness:'CHANGED_INPUT',current_revision:revision,units:'Unicode characters',owner_result:{content},...(more?{read_handle:{http:{method:'GET',url:next}}}:{})});
 const delayed=()=>new Promise((resolve,reject)=>{release=()=>late==='error'?reject(Error('OLD_ERROR')):resolve(observation(late==='changed'?'C':'A','OLD_PAGE'));});
 const request=async path=>{const q=new URL(path,'http://local').searchParams;if(q.get('offset')==='2')return delayed();if(q.get('view')==='workspace-source'){if(++count===1)return phase==='initial'?delayed():observation('A','FIRST_A',true);return observation('B','FRESH_B');}return {references:[row],projects:[{id:'consumer'}],offset:0,total:1,next_offset:null};};
 await mountWorkspaceDependencies(host,{request,parameters:new URLSearchParams()});let pending;
 if(phase==='initial')pending=button(host,'Inspect binding').onclick();else{await button(host,'Inspect binding').onclick();pending=button(host,'Read more source').onclick();}
 assert.ok(release);await button(host,'Inspect binding').onclick();assert.match(host.textContent,/FRESH_B/);release();await pending;
 assert.match(host.textContent,/Current: B/);assert.ok(!host.textContent.includes('OLD_PAGE')&&!host.textContent.includes('OLD_ERROR')&&!host.textContent.includes('cannot mix read bases'));
});


test('global header activation captures current Work and Return restores its exact selector',()=>{
 const link=new Node('a');globalThis.location={href:'http://local/project?workspace=writing&corpus=P&view=overview',search:'?workspace=writing&corpus=P&view=overview'};bindAppLink(link,'activity');
 globalThis.location.href='http://local/project?workspace=writing&corpus=P&view=work&work=WORK-exact';link.onclick();const q=new URL(link.href,'http://local').searchParams;
 assert.equal(q.get('return_view'),'work');assert.equal(q.get('return_work'),'WORK-exact');const back=new URL(projectReturnURL(q),'http://local');assert.equal(back.searchParams.get('work'),'WORK-exact');assert.equal(back.searchParams.get('view'),'work');
 const host=new Node();globalThis.location.search=new URL(link.href,'http://local').search;mountAppNavigation(host,'activity');assert.equal(host.all().find(n=>n.tag==='a'&&n.textContent==='Return to project').href,back.pathname+back.search);
});
test('Material global visits and browser reconstruction retain exact binding without a generic return URL',()=>{
 const route='http://local/project?workspace=writing&corpus=P&view=material&binding=MAT-exact&arbitrary=https://outside.test';
 const q=new URL(appLink('settings',route),'http://local').searchParams,back=new URL(projectReturnURL(q),'http://local');assert.equal(back.searchParams.get('binding'),'MAT-exact');assert.equal(back.searchParams.has('arbitrary'),false);
 const next=new URL(appLink('activity','http://local'+appLink('settings',route)),'http://local').searchParams;assert.equal(projectReturnURL(next),projectReturnURL(q));
});

test('explicit empty Work intent survives global return without a new persistence key',()=>{
 const uri=appLink('activity','http://local/project?workspace=writing&corpus=P&view=work&work=');const q=new URL(uri,'http://local').searchParams;assert.equal(q.has('return_work'),true);assert.equal(q.get('return_work'),'');const returned=new URL(projectReturnURL(q),'http://local').searchParams;assert.equal(returned.has('work'),true);assert.equal(returned.get('work'),'');assert.equal(returned.get('view'),'work');
});


test('project-level Work and explicit Clear survive global visits from non-Work readers',()=>{
 for(const view of ['material','manuscript','research','history']){const q=new URL(appLink('settings','http://local/project?workspace=writing&corpus=P&view='+view+'&work='),'http://local').searchParams;const back=new URL(projectReturnURL(q),'http://local').searchParams;assert.equal(back.get('view'),view);assert.equal(back.has('work'),true);assert.equal(back.get('work'),'');}
 const back='/project?workspace=writing&app=dependencies&return_project=P&return_view=work&return_work=OLD';const uri='http://local/project?'+new URLSearchParams({workspace:'writing',corpus:'P',view:'material',work:'',app_return:back});const restored=new URL(appLink('dependencies',uri),'http://local').searchParams;assert.equal(restored.get('return_work'),'');assert.equal(restored.has('app_return'),false);
 const other=uri.replace('return_project%3DP','return_project%3DOTHER');assert.equal(new URL(appLink('dependencies',other),'http://local').searchParams.get('return_work'),'OLD','A recorded cross-project return never borrows another project Work intent');
});

// M5 C8: the intelligence ladder lives only inside Models & providers; every family opens with a scope chip
test('the scope ladder renders only in Models & providers and each family carries one scope chip and sentence',async()=>{
 const v=await settingsFixture();const panels=v.host.all().filter(n=>n.tag==='section'&&n.children.some(c=>c.attrs['data-control']==='settings:family'));
 assert.equal(panels.length,5,'five families carry a scope head');
 const ladder=v.host.all().filter(n=>n.className.split(' ').includes('settings-scope'));assert.equal(ladder.length,1);
 const owner=panel=>panel.all().includes(ladder[0]);const withLadder=panels.filter(owner);assert.equal(withLadder.length,1);
 assert.match(withLadder[0].textContent,/Engine → project → conversation/);assert.match(withLadder[0].textContent,/Engine declarations/);
 assert.ok(panels.every(panel=>panel.children[0].attrs['data-control']==='settings:family'),'the family head is first in its panel');
 assert.ok(panels.some(panel=>panel.textContent.includes('Workspace shared')));
});
