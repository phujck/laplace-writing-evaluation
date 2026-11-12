import {beforeEach,test} from 'node:test';
import assert from 'node:assert/strict';
import {mountSharedReferences,mountMaterial,workspaceViewAvailable} from '../src/laplace/web/static_shared/workspace-material.mjs';
class Node{
 constructor(tag='div'){this.tag=tag;this.children=[];this.attrs={};this.dataset={};this.className='';this._text='';this.value='';this.hidden=false;this.disabled=false;this.isConnected=true;this.classList={add:value=>{this.className+=' '+value;}};}
 set textContent(value){this._text=String(value??'');this.children=[];}get textContent(){return this._text+this.children.map(node=>node.textContent).join('');}
 append(...nodes){for(const node of nodes){node.parentElement=this;this.children.push(node);}}replaceChildren(...nodes){this._text='';this.children=[];this.append(...nodes);}setAttribute(key,value){this.attrs[key]=String(value);}all(){return [this,...this.children.flatMap(node=>node.all())];}
 after(node){const p=this.parentElement;p.children.splice(p.children.indexOf(this)+1,0,node);node.parentElement=p;}
}
beforeEach(()=>{globalThis.document={createElement:tag=>new Node(tag)};});
const button=(host,label)=>host.all().find(node=>node.tag==='button'&&node.textContent===label),field=(host,label)=>host.all().find(node=>node.attrs['aria-label']===label);
const ref={id:'MAT-one',target:{owner:'artifact',project:'producer',path:'notes.txt',scope:'project'},consumed_revision:'consumed-one',current_revision:'current-two',currentness:'CHANGED_INPUT'};
async function fixture({failAttach=false,failAdopt=false,deferPreview=false,draft=null}={}){
 const host=new Node(),calls=[],dirty=[];let release;
 const request=async(path,payload)=>{calls.push({path,payload});if(payload){if(payload.action==='attach'&&failAttach)throw Error('registry revision conflict');if(payload.action==='adopt'&&failAdopt)throw Error('source revision conflict');return {action:payload.action};}
  const q=new URL(path,'http://local').searchParams,view=q.get('view');
  if(view==='preview'){const value={target:JSON.parse(q.get('target')),currentness:'UNBOUND',current_revision:'inspected-source',consumed_revision:null,revision:'captured-registry',owner_result:{content:'Inspected bytes',next_offset:null}};return deferPreview?new Promise(resolve=>{release=()=>resolve(value);}):value;}
  if(view==='source')return {...ref,revision:'source-registry',owner_result:{content:'Changed producer content',next_offset:null}};
  if(path.startsWith('/work/materials'))return {materials:[],pagination:{next_offset:null,total:0},coverage:'Scoped fixture'};
  return {references:q.get('offset')==='1'?[{...ref,id:'MAT-two',target:{...ref.target,path:'other.txt'}}]:[ref],revision:'list-registry',total:2,next_offset:q.get('offset')==='1'?null:1,owners:{repositories:[{id:'external-data',available:true,access:'read-only'},{id:'offline-source',available:false,access:'read-only'}]}};
 };
 const options={project:'consumer',request,projects:[{name:'producer',title:'Producer'},{name:'consumer',title:'Consumer'}],draft,onDirty:value=>dirty.push(value)};
 const controller=await mountSharedReferences(host,options);return {host,calls,dirty,controller,options,release:()=>release()};
}
test('repository choices come from owner aliases; link uses inspected identity and captured guard with no typed hashes',async()=>{
 const v=await fixture(),path=field(v.host,'Material path');assert.equal(field(v.host,'Material owner').value,'external-data');assert.equal(button(v.host,'Link inspected revision').disabled,true);assert.ok(!v.host.all().some(node=>node.attrs['aria-label']?.includes('revision')));
 path.value='shared/notes.txt';path.oninput();await button(v.host,'Inspect material').onclick();assert.match(v.host.textContent,/Inspected bytes/);assert.equal(button(v.host,'Link inspected revision').disabled,false);assert.equal(v.calls.filter(row=>row.payload).length,0);
 await button(v.host,'Link inspected revision').onclick();assert.deepEqual(v.calls.find(row=>row.payload).payload,{project:'consumer',action:'attach',target:{owner:'repository',repository:'external-data',path:'shared/notes.txt'},consumed_revision:'inspected-source',expected_revision:'captured-registry'});assert.equal(path.value,'');assert.equal(v.controller.hasDraft,false);assert.equal(button(v.host,'Link inspected revision').disabled,true);
});
test('guard conflict preserves choices and disables link until an explicit new inspection',async()=>{
 const v=await fixture({failAttach:true}),path=field(v.host,'Material path');path.value='draft.txt';path.oninput();await button(v.host,'Inspect material').onclick();const reads=v.calls.length;await button(v.host,'Link inspected revision').onclick();assert.equal(v.calls.length,reads+1);assert.equal(path.value,'draft.txt');assert.match(v.host.textContent,/inspect again before retrying/);assert.equal(button(v.host,'Link inspected revision').disabled,true);await button(v.host,'Refresh shared material').onclick();assert.equal(path.value,'draft.txt');assert.equal(button(v.host,'Link inspected revision').disabled,true);assert.deepEqual(v.controller.capture(),{kind:'repository',owner:'external-data',scope:'project',path:'draft.txt'});
});
test('bound inspection reaches stored owner and adoption takes its own snapshot without copying or implicit refresh',async()=>{
 const v=await fixture();await button(v.host,'Inspect notes.txt').onclick();assert.match(v.host.textContent,/Changed producer content/);const before=v.calls.length;await button(v.host,'Adopt inspected revision').onclick();const write=v.calls.slice(before).find(row=>row.payload);assert.deepEqual(write.payload,{project:'consumer',action:'adopt',id:'MAT-one',consumed_revision:'current-two',expected_revision:'source-registry'});assert.equal(v.calls.filter(row=>row.payload).length,1);assert.match(v.host.textContent,/Explicitly adopted/);const owner=v.host.all().find(node=>node.tag==='a'&&node.textContent==='Open material owner');assert.match(owner.href,/corpus=producer/);
});
test('adoption conflicts retain consumed identity and require reinspection; removal uses the listed binding guard',async()=>{
 const v=await fixture({failAdopt:true});await button(v.host,'Inspect notes.txt').onclick();const count=v.calls.length;await button(v.host,'Adopt inspected revision').onclick();assert.equal(v.calls.length,count+1);assert.equal(button(v.host,'Adopt inspected revision').disabled,true);assert.match(v.host.textContent,/Consumed: consumed-one/);assert.match(v.host.textContent,/Inspect this binding again/);await button(v.host,'Remove reference').onclick();assert.deepEqual(v.calls.find(row=>row.payload?.action==='remove').payload,{project:'consumer',action:'remove',id:'MAT-one',expected_revision:'list-registry'});
});
test('pagination follows exact owner continuation and refresh retains a linking draft',async()=>{
 const v=await fixture(),path=field(v.host,'Material path');path.value='retain.txt';path.oninput();await button(v.host,'Show more shared material').onclick();assert.match(v.calls.at(-1).path,/offset=1/);assert.match(v.host.textContent,/2 of 2/);assert.equal(button(v.host,'Show more shared material').hidden,true);await button(v.host,'Refresh shared material').onclick();assert.equal(path.value,'retain.txt');assert.match(v.host.textContent,/1 of 2/);
});
test('late inspection cannot arm a changed draft or a destroyed view',async()=>{
 const v=await fixture({deferPreview:true}),path=field(v.host,'Material path');path.value='first.txt';path.oninput();const read=button(v.host,'Inspect material').onclick();await Promise.resolve();path.value='second.txt';path.oninput();v.release();await read;assert.equal(button(v.host,'Link inspected revision').disabled,true);assert.ok(!v.host.textContent.includes('Inspected bytes'));const next=button(v.host,'Inspect material').onclick();await Promise.resolve();v.controller.destroy();v.release();await next;assert.equal(v.calls.filter(row=>row.payload).length,0);assert.equal(path.value,'second.txt');
});
test('project targets use loaded library choices and drafts restore without reusing a prior inspection',async()=>{
 const v=await fixture({draft:{kind:'artifact',owner:'producer',scope:'project',path:'notes.txt'}});assert.equal(field(v.host,'Material owner').value,'producer');assert.equal(field(v.host,'Material path').value,'notes.txt');assert.equal(button(v.host,'Link inspected revision').disabled,true);await button(v.host,'Inspect material').onclick();const q=new URL(v.calls.at(-1).path,'http://local').searchParams;assert.deepEqual(JSON.parse(q.get('target')),{owner:'artifact',project:'producer',path:'notes.txt',scope:'project'});
});
test('Material carries the shared reference owner; the Dependencies view is retired and source-optional capabilities suppress specialized readers',async()=>{
 const v=await fixture(),info={source_optional:true,capabilities:{work:true,materials:true,turns:true,history:true,settings:true,material_references:true,manuscript:false,concepts:false,research:false,review:false,presentation:false}},a=new Node();
 for(const name of ['work','material','turns','history','settings'])assert.equal(workspaceViewAvailable(info,name),true);for(const name of ['structure','research','manuscript','review','presentation','dependencies'])assert.equal(workspaceViewAvailable(info,name),false);
 await mountMaterial(a,{...v.options,info,onShow:()=>{},onArtifact:()=>{},onHistory:()=>{}});assert.ok(button(a,'Inspect material'));assert.equal(button(a,'Open manuscript'),undefined);assert.equal(button(a,'Research & sources'),undefined);assert.match(a.textContent,/manuscript is optional/);
 const {readFile}=await import('node:fs/promises');const material=await readFile(new URL('../src/laplace/web/static_shared/workspace-material.mjs',import.meta.url),'utf8');assert.ok(!material.includes('export async function mountDependencies'),'the project Dependencies view has no painter');
});

test('navigation consumes owner flags and updates only availability without loading specialized source',async()=>{
 const source=(await import('./helpers/workspace_source.mjs')).workspaceSource(),{SERVICE_PRELUDE}=await import('./helpers/shell_services.mjs');
 const code=source.slice(source.indexOf('  function refreshCapabilityNavigation(){'),source.indexOf('\n  return {openSession',source.indexOf('  function refreshCapabilityNavigation(){')));
 const info={source_optional:true,capabilities:{work:true,materials:true,turns:true,history:true,settings:true,concepts:false,research:false,manuscript:false,review:false,presentation:false}},buttons=['overview','work','material','history','settings','structure','research','manuscript','review','presentation'].map(view=>({dataset:{view},hidden:false,disabled:true})),group={hidden:false},bookNav={hidden:true};
 globalThis.__capNavigation={info,workspaceViewAvailable,bookNav,root:{querySelectorAll:()=>buttons,querySelector:()=>group}};
 try{const {refreshCapabilityNavigation}=await import('data:text/javascript;base64,'+Buffer.from('const {info,workspaceViewAvailable,bookNav,root}=globalThis.__capNavigation;'+SERVICE_PRELUDE+code+'\nexport {refreshCapabilityNavigation};').toString('base64'));refreshCapabilityNavigation();for(const b of buttons){const unavailable=['structure','research','manuscript','review','presentation'].includes(b.dataset.view);assert.equal(b.hidden,unavailable);assert.equal(b.disabled,unavailable);}assert.equal(group.hidden,true);assert.equal(bookNav.hidden,true);info.capabilities.manuscript=true;refreshCapabilityNavigation();assert.equal(buttons.find(b=>b.dataset.view==='manuscript').hidden,false);assert.equal(group.hidden,false);}finally{delete globalThis.__capNavigation;}
 // Specialized readers load when opened; the navigation contract does not require an eager structure read.
});

test('general Home presents optional manuscript and purpose without a forced document form or logical-reader action',async()=>{
 const source=(await import('./helpers/workspace_source.mjs')).workspaceSource(),{SERVICE_PRELUDE}=await import('./helpers/shell_services.mjs');
 const code=source.slice(source.indexOf('  async function renderOverview(host){'),source.indexOf('  async function mountWritingStyle('));
 const E=(tag,text='',cls='')=>{const n=new Node(tag);n.textContent=text;n.className=cls;return n;},section=(host,label)=>{const n=E('section');n.append(E('h3',label));host.append(n);return n;},forms=[];
 globalThis.__genericHome={state:{framing:{revision:'purpose-guard',framing:{purpose:'Organize the company work',audience:'The team'}},form:'book',tasks:[]},info:{title:'Company project',source_optional:true,capabilities:{manuscript:false,start_manuscript:true,concepts:false}},project:'company',E,section,button:(label,fn)=>{const b=E('button',label);b.onclick=fn;return b;},field:(form,label,name,value)=>{const n=E('input');n.name=name;n.value=value;form.append(n);return n;},mountProjectTitle:host=>{host.append(E('h2','Company project'));return {destroy(){}};},root:{querySelector:()=>null},wireForm:form=>forms.push(form)};
 const setup=`import {workCountSummary} from ${JSON.stringify(new URL('../src/laplace/web/static_shared/workspace-work.mjs',import.meta.url).href)};const {state,info,project,E,section,button,field,mountProjectTitle,root,wireForm}=globalThis.__genericHome;const area=field,acceptProjectMetadata=()=>{},api=async()=>{},openSession=()=>{},show=()=>{},changed=()=>{};let projectOverviewRefresh=null,projectHomeController=null,projectTitleController=null,writingStyleController=null,dirty=false,task=null,requestedWork=null;`;
 try{const {renderOverview}=await import('data:text/javascript;base64,'+Buffer.from(setup+SERVICE_PRELUDE+"const manuscript={editor:()=>null};"+code+'\nexport {renderOverview};').toString('base64'));const host=new Node();await renderOverview(host);assert.match(host.textContent,/A manuscript is optional/);assert.equal(button(host,'Continue manuscript'),undefined);assert.ok(button(host,'Add manuscript'));assert.equal(button(host,'Open questions'),undefined);assert.ok(!host.all().some(n=>n.tag==='dt'&&n.textContent==='Form'));const editor=host.all().find(n=>n.tag==='details'&&n.children[0].textContent==='Edit purpose and audience');editor.open=true;editor.ontoggle();assert.equal(forms.length,1);assert.equal(forms[0].children.some(n=>n.name==='form'),false);assert.equal(host.all().find(n=>n.className==='project-home-manuscript').hidden,true);}finally{delete globalThis.__genericHome;}
});

test('shared material continuation invalidates linking after a changed basis without modifying membership',async()=>{
 const host=new Node(),target={owner:'repository',repository:'declared',path:'criteria.md'},next='/projects/material-references?project=consumer&view=preview&offset=2',calls=[];
 const request=async(path,payload)=>{calls.push({path,payload});if(payload)throw Error('No writes allowed');if(path===next)return {target,currentness:'UNBOUND',current_revision:'changed',revision:'registry',owner_result:{content:'MOVED'}};const q=new URL(path,'http://local').searchParams;if(q.get('view')==='preview')return {target,currentness:'UNBOUND',current_revision:'first',revision:'registry',owner_result:{content:'π🌱'},read_handle:{http:{method:'GET',url:next}},restart_read:{http:{method:'GET',url:path}}};return {owners:{repositories:[{id:'declared',available:true}]},references:[],revision:'registry',total:0,next_offset:null};};
 await mountSharedReferences(host,{project:'consumer',request});const path=field(host,'Material path');path.value='criteria.md';path.oninput();await button(host,'Inspect material').onclick();assert.equal(button(host,'Link inspected revision').disabled,false);
 await button(host,'Read more source').onclick();assert.equal(button(host,'Link inspected revision').disabled,true);assert.ok(!host.textContent.includes('MOVED'));assert.match(host.textContent,/cannot mix read bases/);await button(host,'Link inspected revision').onclick();assert.ok(calls.every(row=>!row.payload));
});

for(const phase of ['initial','continuation'])for(const late of ['unchanged','changed','error'])test('connected Material slot discards superseded '+phase+' '+late+' and adopts only its displayed basis',async()=>{
 const host=new Node(),target={owner:'repository',repository:'declared',path:'source.md'},row={id:'MAT-one',target,consumed_revision:'historical'},calls=[];let count=0,release;
 const next='/projects/material-references?project=consumer&view=source&id=MAT-one&offset=2';
 const observation=(revision,content,more=false)=>({...row,currentness:'CHANGED_INPUT',current_revision:revision,revision:'registry',units:'Unicode characters',owner_result:{content},...(more?{read_handle:{http:{method:'GET',url:next}}}:{})});
 const delayed=()=>new Promise((resolve,reject)=>{release=()=>late==='error'?reject(Error('OLD_ERROR')):resolve(observation(late==='changed'?'C':'A','OLD_PAGE'));});
 const request=async(path,payload)=>{calls.push({path,payload});if(payload)return {};const q=new URL(path,'http://local').searchParams;if(q.get('offset')==='2')return delayed();if(q.get('view')==='source'){if(++count===1)return phase==='initial'?delayed():observation('A','FIRST_A',true);return observation('B','FRESH_B');}return {references:[row],owners:{repositories:[{id:'declared',available:true}]},revision:'registry',total:1,next_offset:null};};
 await mountSharedReferences(host,{project:'consumer',request});
 let pending;if(phase==='initial')pending=button(host,'Inspect source.md').onclick();else{await button(host,'Inspect source.md').onclick();pending=button(host,'Read more source').onclick();}
 assert.ok(release);await button(host,'Inspect source.md').onclick();assert.match(host.textContent,/FRESH_B/);assert.equal(button(host,'Adopt inspected revision').disabled,false);
 release();await pending;assert.match(host.textContent,/Current: B/);assert.ok(!host.textContent.includes('OLD_PAGE')&&!host.textContent.includes('OLD_ERROR')&&!host.textContent.includes('cannot mix read bases'));
 assert.equal(button(host,'Adopt inspected revision').disabled,false);await button(host,'Adopt inspected revision').onclick();assert.equal(calls.find(row=>row.payload)?.payload.consumed_revision,'B');
});

test('Material reading cards have independent epochs and unchanged outstanding pages remain readable',async()=>{
 const host=new Node(),target={owner:'repository',repository:'declared',path:'one.md'},rows=[{id:'MAT-one',target,consumed_revision:'old'},{id:'MAT-two',target:{...target,path:'two.md'},consumed_revision:'old'}];let release;
 const request=async path=>{const q=new URL(path,'http://local').searchParams;if(q.get('offset')==='2')return new Promise(resolve=>{release=()=>resolve({...rows[0],currentness:'CHANGED_INPUT',current_revision:'A',units:'Unicode characters',owner_result:{content:'FIRST_CARD_NEXT'}});});if(q.get('view')==='source'){const row=rows.find(x=>x.id===q.get('id'));return {...row,currentness:'CHANGED_INPUT',current_revision:row.id==='MAT-one'?'A':'B',revision:'registry',units:'Unicode characters',owner_result:{content:row.id},...(row.id==='MAT-one'?{read_handle:{http:{method:'GET',url:path+'&offset=2'}}}:{})};}return {references:rows,owners:{repositories:[{id:'declared',available:true}]},revision:'registry',total:2,next_offset:null};};
 await mountSharedReferences(host,{project:'consumer',request});await button(host,'Inspect one.md').onclick();const pending=button(host,'Read more source').onclick();await button(host,'Inspect two.md').onclick();release();await pending;assert.match(host.textContent,/FIRST_CARD_NEXT/);assert.match(host.textContent,/Current: B/);
});

for(const phase of ['initial','continuation'])test('reinspecting a draft source disarms and destroys its old reader before arming current link basis: '+phase,async()=>{
 const host=new Node(),target={owner:'repository',repository:'declared',path:'source.md'},calls=[];let count=0,release;
 const next='/projects/material-references?project=consumer&view=preview&offset=2';
 const observation=(revision,content,more=false)=>({target,currentness:'UNBOUND',current_revision:revision,revision:'registry',owner_result:{content},...(more?{read_handle:{http:{method:'GET',url:next}}}:{})});
 const request=async(path,payload)=>{calls.push({path,payload});if(payload)return {};const q=new URL(path,'http://local').searchParams;if(q.get('offset')==='2')return new Promise(resolve=>{release=()=>resolve(observation('C','OLD_PAGE'));});if(q.get('view')==='preview'){if(++count===1)return phase==='initial'?new Promise(resolve=>{release=()=>resolve(observation('A','OLD_PAGE'));}):observation('A','FIRST_A',true);return observation('B','FRESH_B');}return {references:[],owners:{repositories:[{id:'declared',available:true}]},revision:'registry',total:0,next_offset:null};};
 await mountSharedReferences(host,{project:'consumer',request});const path=field(host,'Material path');path.value='source.md';path.oninput();let pending;
 if(phase==='initial')pending=button(host,'Inspect material').onclick();else{await button(host,'Inspect material').onclick();pending=button(host,'Read more source').onclick();}
 await button(host,'Inspect material').onclick();release();await pending;assert.match(host.textContent,/Current: B/);assert.ok(!host.textContent.includes('OLD_PAGE'));assert.equal(button(host,'Link inspected revision').disabled,false);
 await button(host,'Link inspected revision').onclick();assert.equal(calls.find(row=>row.payload)?.payload.consumed_revision,'B');
});

test('superseded Material adoption error cannot disarm a fresh inspection',async()=>{
 const host=new Node(),row={id:'MAT-one',target:{owner:'repository',repository:'declared',path:'source.md'},consumed_revision:'old'};let reads=0,reject;
 const request=async(path,payload)=>{if(payload)return new Promise((_,no)=>{reject=()=>no(Error('OLD_ADOPTION_ERROR'));});if(new URL(path,'http://local').searchParams.get('view')==='source')return {...row,currentness:'CHANGED_INPUT',current_revision:++reads===1?'A':'B',revision:'registry',owner_result:{content:reads===1?'FIRST_A':'FRESH_B'}};return {references:[row],owners:{repositories:[{id:'declared',available:true}]},revision:'registry',total:1,next_offset:null};};
 await mountSharedReferences(host,{project:'consumer',request});await button(host,'Inspect source.md').onclick();const pending=button(host,'Adopt inspected revision').onclick();await button(host,'Inspect source.md').onclick();reject();await pending;assert.match(host.textContent,/FRESH_B/);assert.equal(button(host,'Adopt inspected revision').disabled,false);assert.ok(!host.textContent.includes('OLD_ADOPTION_ERROR'));
});

// M5 D: Home names the selected or requested Work before the next ready Work; a refused request keeps its recovery
test('Home leads with the selected Work, keeps a refused request with recovery, and never offers Next ready in its place',async()=>{
 const source=(await import('./helpers/workspace_source.mjs')).workspaceSource(),{SERVICE_PRELUDE}=await import('./helpers/shell_services.mjs');
 const code=source.slice(source.indexOf('  async function renderOverview(host){'),source.indexOf('  async function mountWritingStyle('));
 const E=(tag,text='',cls='')=>{const n=new Node(tag);n.textContent=text;n.className=cls;return n;},section=(host,label)=>{const n=E('section');n.append(E('h3',label));host.append(n);return n;};
 const opened=[];const next={id:'WORK-first-pending',title:'First pending work',status:'ready'};
 for(const [index,[task,requested]] of [[{id:'WORK-far',title:'Requested refactor'},null],[null,{id:'WORK-gone',state:'refused',reason:'Exact work identity is unavailable in this namespace.'}],[null,null]].entries()){
  globalThis.__homeWork={state:{framing:{revision:'r',framing:{purpose:'P'}},form:'paper',tasks:[],next,counts:{pending:2}},info:{title:'Project',capabilities:{manuscript:false,concepts:false}},project:'p',E,section,
   button:(label,fn,cls='')=>{const b=E('button',label,cls);b.onclick=fn;return b;},field:(form,label,name,value)=>{const n=E('input');n.name=name;n.value=value;form.append(n);return n;},mountProjectTitle:host=>{host.append(E('h2','Project'));return {destroy(){}};},root:{querySelector:()=>null},wireForm:()=>{},openWork:id=>opened.push(id),task,requested};
  const setup=`import {workCountSummary} from ${JSON.stringify(new URL('../src/laplace/web/static_shared/workspace-work.mjs',import.meta.url).href)};const {state,info,project,E,section,button,field,mountProjectTitle,root,wireForm,openWork}=globalThis.__homeWork;const area=field,acceptProjectMetadata=()=>{},api=async()=>{},openSession=()=>{},show=()=>{},changed=()=>{};let projectOverviewRefresh=null,projectHomeController=null,projectTitleController=null,writingStyleController=null,dirty=false,task=globalThis.__homeWork.task,requestedWork=globalThis.__homeWork.requested;`;
  try{const {renderOverview}=await import('data:text/javascript;base64,'+Buffer.from(setup+SERVICE_PRELUDE+"const manuscript={editor:()=>null};"+code+'\nexport {renderOverview};//case '+index).toString('base64'));const host=new Node();await renderOverview(host);
   const primary=host.all().filter(n=>n.tag==='button'&&n.className==='primary').map(n=>n.textContent);
   if(task){assert.match(host.textContent,/Selected work: Requested refactor/);assert.ok(primary.includes('Open selected work'));assert.ok(!primary.includes('Open next task'));await button(host,'Open selected work').onclick();assert.equal(opened.at(-1),'WORK-far');}
   else if(requested){assert.match(host.textContent,/Requested work WORK-gone is not available: Exact work identity is unavailable/);assert.ok(button(host,'Retry requested work')&&button(host,'Clear request'));assert.ok(!primary.includes('Open next task'),'Next ready never stands in for the request');}
   else assert.ok(primary.includes('Open next task'),'with no selection or request, Next ready leads');
   assert.match(host.textContent,/Next ready work: First pending work/);
  }finally{delete globalThis.__homeWork;}
 }
});
