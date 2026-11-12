// Declared control render coverage through the actual shell or direct view mounts.
// This omnibus checks its named states with owner-shaped public data. Separately
// declared focused evaluators mount the source host, ready Writing tools, Task
// trail/list, workflow and Source readers; the registry below checks that exact
// assignment. A control must be usable in its declared state (including explicitly
// opened optional panels), and absent or unavailable in other mounted states.
// These DOM checks do not claim browser geometry, keyboard or screen-reader proof.
import {register} from 'node:module';register(new URL('./helpers/shared_resolve.mjs',import.meta.url));
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile,readFileSync} from 'node:fs';
import {installDOM,Node,findButton} from './helpers/evidence_reader_harness.mjs';
const CONTROLS=JSON.parse(readFileSync(new URL('./fixtures/help/controls.json',import.meta.url),'utf8'));
const AREAS=JSON.parse(readFileSync(new URL('./fixtures/help/areas.json',import.meta.url),'utf8'));
const DISPLAY=JSON.parse(readFileSync(new URL('./fixtures/editor_spine/display-owner.json',import.meta.url),'utf8'));
const copy=value=>structuredClone(value);
// a module that imports its peers by the served absolute /shared/ path is loaded by file, as its own test does
const shared=new URL('../src/laplace/web/static_shared/',import.meta.url);
// The same selected resolve hook as the focused harnesses preserves normal module
// identity and cycles, without recursively duplicating the graph into data URLs.
const loadShared=name=>import(new URL(name,shared));
const declared=new Map(CONTROLS.controls.map(row=>[row.id,row]));
const controlOf=node=>node.dataset?.control||node.attrs?.['data-control']||null;
const ownerOf=node=>node.dataset?.controlOwner||node.attrs?.['data-control-owner']||null;
// usable: no hidden ancestor, not disabled, and not inside a closed <details> (other than its summary)
const usable=node=>{let child=null;for(let n=node;n;child=n,n=n.parent||n.parentNode||n.parentElement){if(n.hidden===true)return false;
  if((n.tag==='details'||n.localName==='details')&&n!==node&&n.open!==true&&!(child&&(child.tag==='summary'||child.localName==='summary')))return false;}return node.disabled!==true;};
const controlOf2=node=>controlOf(node)||node.getAttribute?.('data-control')||null;
const found=host=>host.all().filter(controlOf2).map(node=>({id:controlOf2(node),owner:ownerOf(node)||node.getAttribute?.('data-control-owner')||null,usable:usable(node)}));
function check(view,state,host){
 const rows=found(host);
 for(const row of rows)assert.ok(declared.has(row.id),view+'/'+state+': undeclared control '+row.id);
 const present=new Set(rows.filter(r=>r.usable).map(r=>r.id)),rendered=new Set(rows.map(r=>r.id));// wave 13: a control declared disabled_until is present, disabled, until its condition holds
 for(const [id,row] of declared){
  if(row.view!==view)continue;
  if(row.states.includes(state)){assert.ok(present.has(id)||(row.disabled_until&&rendered.has(id)),view+'/'+state+': declared control '+id+' is not rendered usable');
   if(row.dynamic)assert.ok(rows.filter(r=>r.id===id).every(r=>r.owner),view+'/'+state+': dynamic '+id+' instances carry data-control-owner');}
  else assert.ok(!present.has(id),view+'/'+state+': '+id+' is declared for other states only but renders usable here');
 }
 return rows;
}
// ---- harnesses: one per source-covered view/state ----
// M5: Work A is review-managed (the project_work_review facet and its allowed work_review phases, owner shapes)
const reviewFacet={managed:true,remaining:['source'],reviews_recorded:0,handoff:null,synthesis:null,followups:[],pending_joins:[],next:{kind:'handoff',says:'Submit the implementation for scoped review (metadata only; nothing is launched).'},
  obligations:[{id:'source',scope:'source',label:'Source review',required:true,independent:true,status:'AWAITING_HANDOFF',currentness:'UNKNOWN',satisfied:false}]};
const workDetail=(id,extra={})=>({project:'fixture',view:'detail',task:{id,title:'Title of '+id,goal:'Authored criterion',status:'blocked',recorded_status:'done',depends_on:['B'],...(id==='A'?{review:reviewFacet}:{})},blockers:[],allowed_actions:{task_status:{permitted:true,statuses:['ready','blocked','done'],payload:{id,expected_work_scope_revision:'old-scope',expected_dependency_revision:'old-deps'},http:{method:'POST',url:'/work/transition'}},
  ...(id==='A'?{work_review:{operation:'work_review',permitted:true,project:'fixture',payload:{id,expected_work_revision:'old-work'},phases:['handoff','review','synthesis','followup'],http:{method:'POST',url:'/work/review'}}}:{})},children:{items:[]},dependants:{items:[]},read_cut:{revision:'cut'},...extra});
const blocker={message:'Consumed literature scope differs.',current_coverage_ready:true,subject:{owner:'literature',qualified_id:'fixture::A'},consumed_revision:'consumed',observed_revision:'current',clear_when:{predicate:'explicit_completion_on_inspected_current_basis'},next_actions:[{permitted:true,kind:'inspect-prerequisite',purpose:'Inspect prerequisite',http:{method:'GET',url:'/work/state?project=fixture&view=detail&id=B'}}],read_handles:[{http:{method:'GET',url:'/work/state?project=fixture&view=detail&id=B'}}]};
async function work({selected=true,readOnly=false,listOpen=false,nextAction=false}={}){
 const {mountOperatorWork}=await import('../src/laplace/web/static_shared/workspace-work.mjs');
 const host=new Node('main');document.body.append(host);
 await mountOperatorWork(host,{project:'fixture',summary:{tasks:[{id:'A',title:'Title of A',status:'blocked'},{id:'B',title:'Title of B',status:'ready',parent_work_id:'A'}]},initialWork:selected?'A':null,readOnly,request:async path=>path.includes('id=B')?workDetail('B'):workDetail('A',{blockers:nextAction?[blocker]:[]})});
 if(listOpen)host.querySelector('.task-catalogue-browser').open=true;return host;
}
async function readerPlan({state}){
 const {mountReaderPlan}=await import('../src/laplace/web/static_shared/workspace-spine.mjs');
 const host=new Node('main');document.body.append(host);
 const summary=copy(DISPLAY.summary);if(state==='empty'){summary.sections.items=[];summary.sections.total=0;summary.spine.items=[];}
 const display=copy(DISPLAY.display);const section=display.sections[0];section.source.precision='EXACT_HEADING';section.source.heading={...section.source.heading,file:section.source.source_files[0]};
 const request=async url=>{const q=new URL(url,'http://local').searchParams;if(q.get('view')==='summary')return summary;if(q.get('projection')==='display')return copy(display);throw Error('Unexpected read '+url);};
 await mountReaderPlan(host,{project:'book',request,readOnly:state==='read-only',onCreate(){},onScope(){},onConcept(){},onEvidence(){},onWork(){},onSource(){},onPrepareWork:async()=>{},onReview:async()=>{}});
 return host;
}
const historyItem=index=>({id:'action:'+index,owner:'journal',category:'manuscript',at:'2026-09-30T12:'+String(index%60).padStart(2,'0')+':00Z',actor:{kind:'agent',label:'Eigen',provider:'codex',model:'historical-model'},summary:'Changed section '+index,status:'Applied',targets:[{kind:'manuscript',label:'Chapter '+index,file:'chapters/ch'+index+'.tex',correction_id:'AC-'+index}],conversation:{session_id:'session-'+index,turn_id:'turn-'+index},detail_available:true});
async function history({open=false}={}){
 const {mountHistory}=await import('../src/laplace/web/static_shared/workspace-history.mjs');
 const host=new Node('main');document.body.append(host);globalThis.scrollHost=host;
 const request=async path=>{const q=new URL(path,'http://fixture').searchParams;if(q.has('id'))return {item:historyItem(0),description:'A guarded source change.',comparison:{format:'tex',before:'Old paragraph',after:'New paragraph'},hashes:[{label:'Chapter source',path:'chapters/ch0.tex',recorded:'abc',current:'def',status:'CHANGED'}],limitations:[]};const offset=Number(q.get('offset'));return {as_of:'2026-09-30T13:00:00Z',items:Array.from({length:offset?3:20},(_,i)=>historyItem(i+offset)),pagination:{total:23,next_offset:offset?null:20},coverage:[]};};
 await mountHistory(host,{project:'fixture',request,onOpenTarget:async()=>{},onOpenConversation:async()=>{}});
 if(open)await findButton(host,'Changed section 0').onclick();
 return host;
}
async function material(){
 const {mountMaterial}=await import('../src/laplace/web/static_shared/workspace-material.mjs');
 const host=new Node('main');document.body.append(host);
 const info={capabilities:{manuscript:true,research:true,review:false,presentation:true,materials:true,material_references:false}};
 const request=async path=>{if(path.startsWith('/work/materials'))return {materials:[{id:'m1',path:'notes/present.md',scope:'project',availability:'present',recorded_revision:'sha256:'+'1'.repeat(64)}],pagination:{next_offset:null,total:1},coverage:'One recorded file.'};throw Error('unexpected '+path);};
 await mountMaterial(host,{project:'p',info,request,onShow(){},onArtifact(){},onHistory(){},onAddLocalDocument(){},projects:[]});
 return host;
}
async function appSettings(){
 const {mountAppSettings}=await loadShared('workspace-app.mjs');
 const host=new Node('main');document.body.append(host);
 const voice={project:null,scope:'global',selected_profile:null,profile:'profiles/voice/main.md',inspected_profile:'profiles/voice/main.md',profile_title:'Shared voice',profile_version:'v1',profile_revision:'profile-1',revision:'global-1',profile_editable:true,content:'# Shared voice',runtime_content:'Keep reasoning connected.',provenance:{revision:'prov-1',status:'NOT_RECORDED'},guidance:'',genre:'',profiles:[{path:'profiles/voice/main.md',title:'Shared voice',version:'v1',status:'AVAILABLE'}]};
 const summary={providers:{cached:true,providers:[{id:'codex',name:'Codex',available:false,auth_state:'UNVERIFIED',models:[{id:'sol',tier:'deep',session_default:true}]}]},model_policy:{row_source:'pipeline.schema TIERS',law:'Session runs at highest tier',tiers:{deep:{codex:'sol'}},role_defaults:{session:{tier:'deep',effort:'high',models:{codex:'sol'}}}},runtime:{observed:{version:'3.14.7'},declared:{lifecycle:{python:'/declared/python'}},revision:'runtime-1'},voice,gaps:[]};
 const oldWindow=globalThis.window;globalThis.window={addEventListener(){},removeEventListener(){}};
 try{await mountAppSettings(host,{request:async path=>path==='/projects/app-settings'?summary:voice});}finally{globalThis.window=oldWindow;}
 return host;
}
async function argument(){
 const {renderConceptRecord}=await import('../src/laplace/web/static_shared/concept-reader.mjs');
 const host=new Node('main');document.body.append(host);const oldWindow=globalThis.window;globalThis.window={katex:{render(){}}};
 try{await renderConceptRecord(host,{node:{id:'support:source-audit',kind:'support',label:'Source audit',summary:'Original reading provenance.'},state:{source_locations:[]},onSource(){}});}finally{globalThis.window=oldWindow;}
 return host;
}
async function research(){
 const {mountEvidence}=await loadShared('writing-evidence.mjs');
 const host=new Node('main');document.body.append(host);
 const record={id:'result-1',title:'Audit',question:'One question',summary:'One finding',usage:[],evidence_files:[],producer:null};
 const request=async path=>{if(path.startsWith('/visuals/state'))return {specs:[]};if(path.startsWith('/research/state'))return {results:[record]};if(path.startsWith('/formal/targets'))return {targets:[]};if(path.startsWith('/formal/state'))return {receipts:[]};if(path.startsWith('/concepts/state'))return null;throw Error('unexpected '+path);};
 await mountEvidence(host,{project:'coverage-fixture',request,status(){},work(){},onOpenUsage(){},view:'numerics'});
 return host;
}
async function conversationOpen(){
 const {WorkspaceSession}=await import('../src/laplace/web/static_shared/workspace-session.mjs');
 const host=new Node('main');document.body.append(host);
 const message=()=>{const row=new Node('article');host.append(row);return row;};
 const current={project:'p',onApplication(){},guard:fn=>fn(),onOpenArtifact(){},status(){},authorMessage:message,actions(){},failures(){},remoteHistory(){},message,onReadTurn:null,parentContinuationValue:null};
 current.facets=WorkspaceSession.prototype.facets;current.proposal=WorkspaceSession.prototype.proposal;current.appendTurn=WorkspaceSession.prototype.appendTurn;
 current.appendTurn({id:'turn-1',text:'Request',action_count:2,failure_count:0,reply:{text:'Done',status:'completed'},result_links:[{url:'/research/artifact?'+new URLSearchParams({project:'p',path:'notes/a.md',scope:'project',artifact_id:'ART-'+'a'.repeat(32),expected_sha256:'b'.repeat(64)}),path:'notes/a.md',artifact_id:'ART-'+'a'.repeat(32),expected_sha256:'b'.repeat(64)}]},false);
 return host;
}
async function topology({wide}){
 const {mountTopology}=await import('../src/laplace/web/static_shared/workspace-topology.mjs');
 document.createElementNS=(_ns,tag)=>new Node(tag);
 const host=new Node('main');document.body.append(host);
 const nodes=wide?[{id:'parent',title:'Parent'},...Array.from({length:49},(_,i)=>({id:'child-'+i,title:'Child '+i}))]:[{id:'A',title:'A'},{id:'B',title:'B'},{id:'C',title:'C'}];
 // wave 13: the plain page also has one relationship coming in from an object outside it, with an owner read to open it (the source end is a door)
 const edges=wide?nodes.slice(1).map(n=>({kind:'contains',source:'parent',target:n.id})):[{kind:'contains',source:'A',target:'B'},{kind:'requires',source:'B',target:'C'},{kind:'contains',source:'OUTER',target:'A'}];
 mountTopology(host,{nodes,edges,selected:wide?'parent':'A',boundaries:wide?[]:[{id:'OUTER',title:'Containing task'}],onExpand:wide?null:()=>{}});
 return host;
}
async function guardInspector(){
 const {renderReaderGuard}=await import('../src/laplace/web/static_shared/reader-state.mjs');
 const host=new Node('main');document.body.append(host);
 for(const subject of ['section','structure'])renderReaderGuard(host,copy(DISPLAY[subject+'_subject']),{project:'book',sectionId:'first',subject,paragraphId:DISPLAY[subject+'_subject'].paragraph?.paragraph_id||null});
 return host;
}
// THE REAL SHELL: mountWorkspace over the markup DOM double with owner-shaped answers
const {mountShell,METADATA,defaultRoutes,ownerReply}=await import('./helpers/shell_fixture.mjs');
const NO_MANUSCRIPT={'/projects/metadata':()=>({...structuredClone(METADATA),capabilities:{...METADATA.capabilities,manuscript:false,presentation:false}})};
const OWNERS=JSON.parse(readFileSync(new URL('./fixtures/shell/owner-answers.json',import.meta.url),'utf8'));
const shell=(steps=async()=>{},options={})=>async()=>{const s=await mountShell(options);await steps(s);await s.settle();await s.settle();return {host:document.documentElement,restore:()=>s.restore(),shell:s};};
const click=async(s,selector)=>{const node=s.root.querySelector(selector)||document.querySelector(selector);assert.ok(node,'no '+selector);await node.onclick?.({preventDefault(){},stopPropagation(){},target:node});await s.settle();};
const view=name=>async s=>{await s.workspace.show(name);await s.settle();await s.settle();};
const REF={id:'MAT-one',target:{owner:'artifact',project:'producer',path:'notes.txt',scope:'project'},consumed_revision:'consumed-one',current_revision:'current-two',currentness:'CHANGED_INPUT'};
const PROPOSAL={id:'T',project:'book',proposal_version:'V',read_handle:{http:{method:'GET',url:'/authoring/proposal-preview?'+new URLSearchParams({project:'book',id:'T',proposal_version:'V',record_id:'record-V',view:'summary'})},native_request:{verb:'read',target:'book::T',payload:{id:'T',proposal_version:'V',record_id:'record-V',view:'summary'}}},edit_count:2,files:['chapter.tex']};
const FAILED_DOCUMENT={...OWNERS.document,status:'FAILED',current_build:{...(OWNERS.document.current_build||{}),ok:false,running:false,present:true,reason:'The last recompile failed',log_tail:'! Missing $ inserted.'}};
async function profilePreferences(){
 const {mountProfilePreferences}=await import('../src/laplace/web/static_shared/profile-preferences.mjs');
 const fixture=JSON.parse(readFileSync(new URL('./fixtures/editor_spine/profile-candidates.json',import.meta.url),'utf8'));
 const host=new Node('main');document.body.append(host);
 const request=async path=>{const url=new URL(path,'http://local'),v=url.searchParams.get('view');if(v==='summary')return copy(url.searchParams.has('project')?fixture.before:fixture.global_summary);if(v==='content')return copy(fixture.current);if(v==='candidates')return {candidates:[copy(fixture.candidate)],pagination:{returned:1,total:1}};if(v==='candidate')return copy(fixture.candidate);return {};};
 await mountProfilePreferences(host,{project:'book',family:'architecture',scope:'workspace',request,onChanged(){},enableEdit:false});
 return host;
}
// the editor band with a READY reader (its frame's walk can undo): mounted over the markup DOM double
async function manuscriptWrite(){
 const {installHTMLDocument}=await import('./helpers/html_dom.mjs');const env=installHTMLDocument();
 const {createManuscriptEditor}=await import('../src/laplace/web/static_shared/manuscript-editor.mjs');
 const host=document.createElement('div'),frame=document.createElement('iframe');host.append(frame);document.body.append(host);
 frame.contentWindow={walk:{editState:()=>({dirty:false}),captureFocus:()=>null,restoreFocus(){},commitAll:async()=>{},refresh:async()=>{},flipState:()=>({open:false}),undoEdit:async()=>{},redoEdit:async()=>{}}};
 const controller=createManuscriptEditor(host,{project:'book',frame,storage:{getItem:()=>null,setItem(){},removeItem(){}},request:async()=>copy(OWNERS.document)});await controller.observe();controller.showWrite?.();
 return {host:document.documentElement,restore:()=>{controller.destroy?.();env.restore();},shell:{notice:()=>''}};
}
async function manuscriptSource(){
 const {installHTMLDocument}=await import('./helpers/html_dom.mjs');const env=installHTMLDocument();
 const {createManuscriptEditor}=await import('../src/laplace/web/static_shared/manuscript-editor.mjs');
 const host=document.createElement('div'),frame=document.createElement('iframe');host.append(frame);document.body.append(host);
 frame.contentWindow={walk:{editState:()=>({dirty:false}),captureFocus:()=>null,restoreFocus(){},commitAll:async()=>{},refresh:async()=>{},flipState:()=>({open:false}),undoEdit:async()=>{},redoEdit:async()=>{}}};
 const doc=copy(OWNERS.document),sourceRead=async({file})=>({schema_version:'laplace.projection-source/1',file,content:'\\documentclass{article}\n\\begin{document}\nA saved line.\n\\end{document}\n',expected_source_digest:doc.files.find(row=>row.file===file).expected_source_digest,selection_identity:doc.selection_identity});
 const controller=createManuscriptEditor(host,{project:'book',frame,storage:{getItem:()=>null,setItem(){},removeItem(){}},request:async()=>copy(OWNERS.document),sourceClient:{read:sourceRead,save:async()=>{throw Error('The coverage harness performs no save.');}}});await controller.observe();
 const tex=document.documentElement.all().find(n=>controlOf2(n)==='writing:mode-tex');assert.ok(tex,'the TeX mode button');await tex.onclick();await new Promise(resolve=>setTimeout(resolve,20));
 return {host:document.documentElement,restore:()=>{controller.destroy?.();env.restore();},shell:{notice:()=>''}};
}
async function templateCandidate({reviewed}){
 const {renderTemplateCandidate}=await import('../src/laplace/web/static_shared/document-template.mjs');
 const {templateWire:wire}=await import('./helpers/document_template_fixture.mjs');
 const host=new Node('section');document.body.append(host);
 const value=reviewed?wire.built.reviewed:wire.changed;
 renderTemplateCandidate(host,copy(value),{project:value.project,onApply:()=>{},reviewedPreview:reviewed?copy(wire.built.finished.preview_ref):null});
 return host;
}
async function researchBrowser(selected){const {mountResearchFixture}=await import('./helpers/research_workbench_fixture.mjs'),mounted=await mountResearchFixture({selected});const outline=mounted.host.querySelectorAll('button').find(n=>n.textContent==='Show outline');if(outline)await outline.onclick();mounted.host.querySelector('[data-rw-browser]').open=true;const saved=mounted.host.querySelector('.rg-saved');if(saved)saved.open=true;return mounted;}
const selectedWorkRoutes=nextAction=>({'/work/state':q=>{if(q.get('view')!=='detail')return defaultRoutes()['/work/state'](q);const value=workDetail('A',{blockers:nextAction?[blocker]:[]});value.project='book';value.task.id=q.get('id');value.allowed_actions.task={operation:'task',permitted:true,payload:{id:q.get('id'),expected_work_revision:'old-work'},http:{method:'POST',url:'/work/task'}};value.allowed_actions.task_status.payload.id=q.get('id');value.allowed_actions.work_review.project='book';value.allowed_actions.work_review.payload.id=q.get('id');return value;}});
// wave 11: the selected Task's authored-work and containing-work panels opened explicitly (their Save and attempt line are declared)
const openEditors=async s=>{await view('work')(s);for(const box of s.root.querySelectorAll('details').filter(n=>/operator-work-(editor|containment)/.test(String(n.className))))box.open=true;};
// wave 13: the Now page over owner-shaped reads (the same stand-ins tests/workspace_frame.test.mjs uses), on the markup DOM double
async function nowPage(){
 const {installHTMLDocument}=await import('./helpers/html_dom.mjs');const env=installHTMLDocument({width:1440});
 const {mountNow}=await import('../src/laplace/web/static_shared/workspace-now.mjs');
 const root=document.createElement('section');root.id='project-work';document.body.append(root);
 const request=async path=>{const u=new URL(path,'http://local');
  if(u.pathname==='/projects/library')return {projects:[{name:'garden',title:'Garden watering study'},{name:'notes',title:'Notes',source_optional:true}]};
  if(u.pathname==='/authoring/health')return {active_work:[{kind:'turn',project:'garden',session_id:'WS-1',turn_id:'WT-1',label:'Compare the pots',provider:'claude'}],active_work_omitted:0};
  if(u.searchParams.get('currentness')==='REVIEW_REQUIRED')return {coverage:{matching_work:6},rows:Array.from({length:6},(_,i)=>({namespace:'garden',id:'W'+i,title:'Compare the notes '+i,lifecycle:{status:'done',completed:true,closed:true},current_acceptance:{status:'REVIEW_REQUIRED',review_required:true}}))};
  return {coverage:{matching_work:3},rows:[],suggested_next:{state:'SUGGESTED',namespace:'garden',id:'W2',title:'Observe both pots'}};};
 const now=await mountNow(root,{request,interval:0});
 return {host:document.documentElement,restore:()=>{now.destroy();env.restore();},shell:{notice:()=>''}};
}
// wave 13: the workspace pages that are not project views, each mounted through its own exported mount over owner-shaped reads
async function dependenciesPage(){
 const {installHTMLDocument}=await import('./helpers/html_dom.mjs');const env=installHTMLDocument({width:1440});
 const {mountWorkspaceDependencies}=await loadShared('workspace-app.mjs');
 const host=document.createElement('main');document.body.append(host);
 const request=async()=>({registry_revision:'r1',offset:0,next_offset:20,total:1,projects:[{id:'garden',title:'Garden'}],references:[{id:'MAT-1',target:{path:'notes.txt',project:'producer'},consumer:{project:'garden',title:'Garden'},relation:'reads',consumed_revision:'c1'}],coverage:[{kind:'shared material',owner:'domain.material',listing:'listed'}],gaps:[]});
 const view=await mountWorkspaceDependencies(host,{request,parameters:new URLSearchParams('consumer=garden')});
 return {host:document.documentElement,restore:()=>{view.destroy();env.restore();},shell:{notice:()=>''}};
}
async function projectsPage(){
 const {installHTMLDocument}=await import('./helpers/html_dom.mjs');const env=installHTMLDocument({width:1440});
 location.href='http://local/project?workspace=writing&app=projects';
 const root=document.createElement('section');root.id='project-work';document.body.append(root);
 const oldFetch=globalThis.fetch;globalThis.fetch=async url=>{const body=String(url).includes('/projects/library')?{projects:[{name:'garden',title:'Garden watering study'},{name:'notes',title:'Notes',source_optional:true}]}:{};return {ok:true,status:200,headers:{get:()=>'application/json'},json:async()=>body,text:async()=>JSON.stringify(body)};};
 const {initProjectWork}=await import('../src/laplace/web/static_shared/project-work.mjs');await initProjectWork();
 const create=root.querySelector('.pw-create-toggle');if(create)create.onclick?.();
 return {host:document.documentElement,restore:()=>{globalThis.fetch=oldFetch;env.restore();},shell:{notice:()=>''}};
}
async function ownersPage(){
 const {mountOwnerDiscovery}=await loadShared('workspace-owners.mjs');
 const host=new Node('main');document.body.append(host);
 const table={'/work/discovery?facet=describe':{facet:'describe',purpose:'Start here.',scope:{says:'Owned workspace.'},coverage:{},subsystems:[{reference:{identity:{id:'core.identity'}},next:{http:{url:'/d'}},layer:'core',affecting_work:{bound_in_scope:0},summary:'Identity.'}]}};
 await mountOwnerDiscovery(host,{request:async url=>{const reply=table[url];if(!reply)throw Error('unexpected '+url);return structuredClone(reply);}});
 return host;
}
// wave 13: every disclosure on a page opened (and its lazy content asked for), twice over so what the first opening paints is opened too
const openAll=async s=>{for(let round=0;round<3;round++){for(const box of s.root.querySelectorAll('details')){if(!box.open){box.open=true;await box.ontoggle?.();}}await s.settle();await s.settle();}};
// the Home page's disclosures open over a project that names its writing file and has a ready task (what the census's seeded load has)
const homeRoutes={'/projects/metadata':()=>({...METADATA,root:'chapters/main.tex'}),'/work/state':q=>q.get('view')==='queue'?{project:'book',view:'queue',items:[{id:'WORK-b',title:'Approach B',status:'ready',lifecycle:{closed:false}}],next:{id:'WORK-b',title:'Approach B'}}:defaultRoutes()['/work/state'](q)};
// the open task as the census's seeded load has it: a recorded lifecycle, a containing task and the detail read for Reinspect
const richWorkRoutes=(()=>{const routes=selectedWorkRoutes(true),base=routes['/work/state'];routes['/work/state']=q=>{const v=base(q);if(q.get('view')==='detail'){v.task.lifecycle={status:'blocked',closed:false};v.parent={id:'WORK-p',title:'Containing task'};v.reads={detail:{http:{method:'GET',url:'/work/state?project=book&view=detail&id='+q.get('id')}}};}return v;};return routes;})();
// ---- wave 13 captured owner answers (begin): the real answers of the census's seeded project (gen/capture.mjs), project name rewritten to book ----
const CAPTURED={"concepts_tree":{"ancestors":[],"ancestors_omitted":0,"atlas_conjugate":{"authority":"DESIGN_2026-08-24_the-conjugate-serve.md (SEED)","reason":"No materialized per-block Atlas chart or transition map is registered for this project corpus; no spectral coordinates were invented.","status":"UNAVAILABLE"},"children":[{"child_count":0,"descent":{"authority":"conceptric.children_view","kind":"containment-descent","query":{"direction":"down","from":"paper://","node":"sec:chapter-01","project":"book"},"revision":"8c06d329ae11d4680e191c3ce8c6658d0cac747a8da09310014aede9c749bde6"},"grade":0,"has_children":false,"id":"sec:chapter-01","kind":"section","label":"Introduction","parent":"paper://","projection":{},"share":1,"source":null,"status":null,"summary":"Introduction","summary_truncated":false,"title":null},{"child_count":0,"descent":{"authority":"conceptric.children_view","kind":"containment-descent","query":{"direction":"down","from":"paper://","node":"references","project":"book"},"revision":"8c06d329ae11d4680e191c3ce8c6658d0cac747a8da09310014aede9c749bde6"},"grade":0,"has_children":false,"id":"references","kind":"references","label":"the bibliography","parent":"paper://","projection":{},"share":0,"source":null,"status":null,"summary":"the bibliography","summary_truncated":false,"title":null}],"children_next_offset":null,"children_offset":0,"children_omitted":0,"children_total":2,"current":{"child_count":2,"grade":1,"has_children":true,"id":"paper://","kind":"paper","label":"Garden watering study","parent":null,"projection":{},"source":null,"status":null,"summary":"Garden watering study","summary_truncated":false,"title":null},"dependencies":{"boundary":[],"internal":[],"next_offset":null,"offset":0,"omitted":0,"total":0},"hierarchy_gaps":[],"identity_chain":[],"navigation":{"ascent":{"authority":"conceptric.identity_chain","available":false,"from":"paper://","kind":"containment-ascent","query":{"direction":"up","node":"paper://","project":"book"},"rederive_on_follow":true,"resolved_parent":null,"revision":"8c06d329ae11d4680e191c3ce8c6658d0cac747a8da09310014aede9c749bde6"}},"navigation_semantics":{"limitations":["identity-chain ascent is a live containment re-projection, not browser history","dependency traversal is not conjugate UP","no materialized project-corpus Atlas chart or transition-map record is available"],"supported":["grade descent through conceptric.children_view","live enclosing-context ascent through conceptric.identity_chain","bounded goal reconstruction through keeper_ring.reconstruct when goal is supplied","typed dependency traversal kept distinct from containment"]},"omission_residual":{"ancestors_not_shown":0,"children_not_shown":0,"dependencies_not_shown":0},"project":"book","relation_diagnostics":[],"request":{"authority":"corpus_ingest.corpus_network","direction":"current","from_node":null,"kind":"open","rederived_from_live_revision":"8c06d329ae11d4680e191c3ce8c6658d0cac747a8da09310014aede9c749bde6","requested_node":"paper://","resolved_node":"paper://"},"revision":"8c06d329ae11d4680e191c3ce8c6658d0cac747a8da09310014aede9c749bde6","root_id":"paper://","schema_version":"laplace.concept-tree/1","semantic_return":{"authority":"keeper_ring.reconstruct","reason":"Navigation alone has no reconstruction goal, so no semantic pull-up was executed.","status":"NOT_RUN"},"uncontained":[],"uncontained_next_offset":null,"uncontained_offset":0,"uncontained_total":0},"concepts_state":{"content_revision":"15ab0b240b930b47efb67cb441ec8f85f7b91fe34de1bb75eeaef720fb4c910c","focus":{"id":"paper://","kind":"paper","label":"Garden watering study","projection":{},"source":null,"status":null,"summary":"Garden watering study","title":null},"glossary":[],"identities":{"concept-network:book":"rev:concept-network:book:8c06d329ae11d4680e191c3ce8c6658d0cac747a8da09310014aede9c749bde6","concept-node:book::paper://":"rev:concept-node:book::paper://:15ab0b240b930b47efb67cb441ec8f85f7b91fe34de1bb75eeaef720fb4c910c"},"mutation_revision":"15ab0b240b930b47efb67cb441ec8f85f7b91fe34de1bb75eeaef720fb4c910c","neighbors":[],"neighbors_omitted":0,"omitted":0,"project":"book","relation_diagnostics":[],"relations":[],"revision":"8c06d329ae11d4680e191c3ce8c6658d0cac747a8da09310014aede9c749bde6","schema_version":"laplace.concepts/1","search":[],"source_locations":[],"source_support":{"authored_proof":false,"citation_assessment":"NOT_REQUESTED","declared_role":null,"documented_proof":{"source":null,"status":"NOT_RECORDED"},"engineering_support":{"bindings":[],"read_metrics":{},"reason":"No engineering support has been adopted","status":"UNDECLARED"},"gaps":[],"independent_verification":"NOT_ASSERTED","meaning_revision":"sha256:860884353967b1e4e09b3cc0b61c994c9ffb78f2d5aa33bb0b80f48ad9b8b1d2","node":"paper://","omission":{"associations_omitted":0,"citation_projection":"ON_DEMAND","citations_omitted":null},"own_evidence":[],"qualification":"AUTHORED_BASIS","sources":[]},"spine":[]},"concepts_plan":{"authority":{"edits":"corpus_friction rewire records","evidence":"canonical result/source bindings","objects":"corpus_ingest.corpus_network","reader_order":"projection-plan ledger","relations":"corpus_ingest.relation_projection"},"containers":[{"child_count":2,"grade":1,"has_children":true,"id":"paper://","kind":"paper","label":"Garden watering study","members":["references","sec:chapter-01"],"parent":null,"projection":{},"source":null,"status":null,"summary":"Garden watering study","summary_truncated":false,"title":null}],"containers_omitted":0,"derivation_face":{"aspiration":{"present":false},"authority":"pipeline.derivation_organ.read_sheet; joined only by node_id/from_ids/to_id","bound_links":[],"present":false,"reach":{"aspiration_present":false,"depth_attested":0,"frontier_gap":[],"frontier_n":0,"links_attested":0,"links_total":0},"unbound_links":[]},"identities":{"concept-network:book":"rev:concept-network:book:8c06d329ae11d4680e191c3ce8c6658d0cac747a8da09310014aede9c749bde6","selected-edition:book":"rev:selected-edition:book:51260fc321abc6d19ab348cc7c3b871781c1699b07572d4bafa3fd9b9bc51291"},"issues":[],"objects":[],"obligations":[],"omission":{"note":"Follow object identities and source references; absent L2 placement is explicit.","objects_offset":0,"objects_omitted":0,"objects_returned":0,"objects_total":0,"relations_total":0,"sections_total":0,"support_objects_assessed":0,"support_scope":"Returned object page only; other object evidence was not hydrated"},"placed_count":0,"project":"book","reader_order":{"omitted_sections":0,"reason":"No L2 reader order is declared; logical planning remains available.","source_outline":[{"basis":{"selection_identity":null,"source_digest":"sha256:4ccb9f8abfda29a22b4de7a79cc19173da8459ff202e2ea7d049568c6dfb29ac"},"bound":false,"display_title":"Introduction","file":"synthetics papers/book/manuscript/chapters/chapter-01.tex","heading_before":"\\section{Introduction}","heading_line_end":1,"id":"source-heading-1","include_line":9,"include_parent":"synthetics papers/book/manuscript/Garden-watering-study.tex","kind":"section","label":null,"labels":[],"level":2,"line":1,"line_end":4,"parent_file":null,"parent_id":null,"parent_line":null,"shared_occurrences":1,"source_order":1,"source_read":{"operation":"source","payload":{"files":["synthetics papers/book/manuscript/chapters/chapter-01.tex"],"line_end":4,"line_start":1}},"structure_read":{"http":{"method":"GET","query":{"files":["synthetics papers/book/manuscript/chapters/chapter-01.tex"],"line_end":4,"line_start":1,"project":null,"view":"detail"},"route":"/work/structure"},"operation":"structure","payload":{"files":["synthetics papers/book/manuscript/chapters/chapter-01.tex"],"line_end":4,"line_start":1,"view":"detail"}},"title":"Introduction"}],"status":"UNDECLARED"},"relation_diagnostics":[],"revision":"8c06d329ae11d4680e191c3ce8c6658d0cac747a8da09310014aede9c749bde6","schema_version":"laplace.logical-plan/1","selected":null,"source_currentness":{"diagnostics":[],"edition":"draft","read_only":false,"root":"synthetics papers/book/manuscript/Garden-watering-study.tex","status":"resolved"},"source_support_gaps":[],"source_support_gaps_omitted":0,"unplaced_count":0},"concepts_history":{"basis":{"ledger_revision":"sha256:4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945","reason":"Rewire operations are exact. Historical corpus source bytes were not pinned, so before/after structure is reprojected over the current source.","source_revision":"51260fc321abc6d19ab348cc7c3b871781c1699b07572d4bafa3fd9b9bc51291","source_root":"synthetics papers/book/manuscript/Garden-watering-study.tex","status":"REPROJECTED_ON_CURRENT_SOURCE"},"current":{"authority":{"dependencies":"canonical typed edge","hierarchy":"conceptric.children_view","uplinks":"conceptric.identity_chain"},"boundary_nodes":[],"current":{"child_count":2,"depth":0,"grade":1,"has_children":true,"id":"paper://","kind":"paper","label":"Garden watering study","parent":null,"projection":{},"share":null,"source":null,"status":null,"summary":"Garden watering study","summary_truncated":false,"title":null},"dependencies":[],"descendants":[{"child_count":0,"depth":1,"grade":0,"has_children":false,"id":"sec:chapter-01","kind":"section","label":"Introduction","parent":"paper://","projection":{},"share":1,"source":null,"status":null,"summary":"Introduction","summary_truncated":false,"title":null},{"child_count":0,"depth":1,"grade":0,"has_children":false,"id":"references","kind":"references","label":"the bibliography","parent":"paper://","projection":{},"share":0,"source":null,"status":null,"summary":"the bibliography","summary_truncated":false,"title":null}],"identity_chain":[],"omission_residual":{"boundary_nodes_not_projected":0,"complete":true,"deeper_descendant_count_unknown":false,"dependencies_not_projected":0,"depth_limit":4,"known_children_beyond_depth":0,"node_limit":32,"queued_descendants_not_projected":0,"uplinks_not_projected":0},"project":"book","revision":"5bbabc4be06f90d5e9b08204a953d4f028168165d13eaf21ad9859a309459766","schema_version":"laplace.concept-focus/1"},"history":[],"impact":{"objects":[{"available":true,"id":"paper://","kind":"paper","label":"Garden watering study","posture":"CURRENT_JOIN_NOT_HISTORICAL","reader_locations":[],"source_refs":[],"source_support":{"authored_proof":false,"citation_assessment":"CANONICAL_SECTIONS","declared_role":null,"documented_proof":{"source":null,"status":"NOT_RECORDED"},"engineering_support":{"bindings":[],"read_metrics":{},"reason":"No engineering support has been adopted","status":"UNDECLARED"},"gaps":[],"independent_verification":"NOT_ASSERTED","meaning_revision":"sha256:860884353967b1e4e09b3cc0b61c994c9ffb78f2d5aa33bb0b80f48ad9b8b1d2","node":"paper://","omission":{"associations_omitted":0,"citation_projection":"CANONICAL_SECTIONS","citations_omitted":0},"own_evidence":[],"qualification":"AUTHORED_BASIS","sources":[]}}],"posture":"No dependent was re-proven and no manuscript prose was propagated."},"limitations":["Historical source bytes are unavailable unless another canonical owner pinned them.","Reader locations and source references are current joins, not historical placement snapshots."],"node":"paper://","pagination":{"limit":3,"next_offset":null,"offset":0,"total":0},"project":"book","schema_version":"laplace.concept-history/1"},"concepts_catalog":{"items":[],"next_offset":null,"offset":0,"project":"book","read_routes":{"attention":{"operation":"logical_plan","payload":{"node":"<item_id>"}},"item":{"operation":"concept","payload":{"node":"<item_id>"}},"tree":{"operation":"concept_tree","payload":{"node":"<item_id>"}}},"revision":"4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945","schema_version":"laplace.concept-catalog/1","scope":"declared logical objects","total":0},"corpus_map":{"nodes":[],"edges":[],"truncated":0,"max_grade":0,"n_gaps":0,"relation_diagnostics":[]},"history_overview":{"schema_version":"laplace.session-analytics/1","project":"book","projection":"overview","scope":"project","filters":{"projection":"overview","scope":"project"},"as_of":"eyJ2IjoxLCJxdWVyeSI6InNoYTI1NjphOGVjYmY5Y2E5ZDJkNmQ1ZjAxMDE1NzdiZWNiOWNkOTQ0ZmVmOWM1ZTA1NzA0Y2RkN2IwMTA0Yzg5OTA0MDdkIiwidXBwZXIiOjM3LCJyZXZpc2lvbiI6InNoYTI1NjplNDI0Nzk4YzBhMGFlMjgzNGY3ZTEyYjZkODg2ODI4ODMwZTAyYmJjZmIxODI0ZWU3Nzg4NGM5NzQzNGEzMzEzIn0","read_cut":{"revision":"sha256:e424798c0a0ae2834f7e12b6d886828830e02bbcfb1824ee77884c97434a3313","scope":"selected metadata rows through retained owner cut"},"coverage":{"selected_metadata_rows":35,"original_tool_attempts":1,"duplicate_original_rows":0,"ambiguous_original_ids":0,"missing_original_ids":0,"unjoined_turn_rows":0,"talk_source_status":"AVAILABLE","malformed_source_rows_unattributed":0,"usage_basis":"legacy numeric reports do not establish complete logical-turn consumption","body_reads":0,"raw_content_in_aggregates":false,"identity_issues":[]},"work_scope":{"basis":"existing project-work parent_work_id; prerequisites are not containment","included_work_ids":[],"issues":[],"revision":"sha256:eaa0498eca4c4408a79798a2ab439863573d4529a71910c098e58c1ff63aac9b"},"items":[],"pagination":{"total":0,"offset":0,"limit":30,"next_read":null},"limits":["Saved metadata is not live execution or scientific acceptance.","Legacy usage is unknown counter basis, not zero or a cost total.","Full source/response/error/comment bodies remain behind exact owner reads."],"totals":{"sessions":7,"logical_turns":7,"original_tool_attempts":1,"retained_tool_failures":0},"nesting":{"basis":"Unique turn leaves; parent_turn_id and work containment remain separate. No child sums are added to global leaves.","turns":[{"turn_id":"WT-public-design","session_id":"WS-public-design","project":"book","parent_turn_id":null,"child_turn_ids":[],"work_id":"WORK-evidence-trail","queued_work_ids":[],"allocation":"explicit-work-association","owner_ref":{"owner":"authoring_surface","kind":"writing-turn","id":"WT-public-design","project":"book"},"conceptric_mapping":{"logical_target":null,"obligation_id":null,"status":"unmapped"},"original_tool_attempts":{"writing-tool-read":0,"writing-tool-action":0,"writing-tool-failure":0},"coverage":{"duplicate_original_rows":0,"ambiguous_original_ids":0,"missing_original_ids":0},"failure_receipts":0,"saved_terminal_kinds":[],"execution_coverage":"saved-terminal-receipt"},{"turn_id":"WT-6b0b80cfcbe744ac862274b4c8b240c8","session_id":"WS-2dd4fb8565af49f2a6a7a2acfd589f5a","project":"book","parent_turn_id":null,"child_turn_ids":[],"work_id":null,"queued_work_ids":[],"allocation":"unallocated-shared-turn","owner_ref":{"owner":"authoring_surface","kind":"writing-turn","id":"WT-6b0b80cfcbe744ac862274b4c8b240c8","project":"book"},"conceptric_mapping":{"logical_target":null,"obligation_id":null,"status":"unmapped"},"original_tool_attempts":{"writing-tool-read":0,"writing-tool-action":0,"writing-tool-failure":0},"coverage":{"duplicate_original_rows":0,"ambiguous_original_ids":0,"missing_original_ids":0},"failure_receipts":0,"saved_terminal_kinds":["completed"],"execution_coverage":"saved-terminal-receipt"},{"turn_id":"WT-d189eaa4b04847a69a6fee878b23f855","session_id":"WS-3bed4958b6d743f1b520775640d491e9","project":"book","parent_turn_id":null,"child_turn_ids":[],"work_id":null,"queued_work_ids":[],"allocation":"unallocated-shared-turn","owner_ref":{"owner":"authoring_surface","kind":"writing-turn","id":"WT-d189eaa4b04847a69a6fee878b23f855","project":"book"},"conceptric_mapping":{"logical_target":null,"obligation_id":null,"status":"unmapped"},"original_tool_attempts":{"writing-tool-read":0,"writing-tool-action":0,"writing-tool-failure":0},"coverage":{"duplicate_original_rows":0,"ambiguous_original_ids":0,"missing_original_ids":0},"failure_receipts":0,"saved_terminal_kinds":["completed"],"execution_coverage":"saved-terminal-receipt"},{"turn_id":"WT-7906f51187724018b5948e6d87b6cd20","session_id":"WS-cab6be9771e544b2a63e440ac0b2f6b5","project":"book","parent_turn_id":null,"child_turn_ids":[],"work_id":null,"queued_work_ids":[],"allocation":"unallocated-shared-turn","owner_ref":{"owner":"authoring_surface","kind":"writing-turn","id":"WT-7906f51187724018b5948e6d87b6cd20","project":"book"},"conceptric_mapping":{"logical_target":null,"obligation_id":null,"status":"unmapped"},"original_tool_attempts":{"writing-tool-read":0,"writing-tool-action":0,"writing-tool-failure":0},"coverage":{"duplicate_original_rows":0,"ambiguous_original_ids":0,"missing_original_ids":0},"failure_receipts":0,"saved_terminal_kinds":["completed"],"execution_coverage":"saved-terminal-receipt"},{"turn_id":"WT-c24044c3b0a94ef5be8ba8109c513cee","session_id":"WS-125ec0ee90a34de2afc0a876ad3b71da","project":"book","parent_turn_id":null,"child_turn_ids":[],"work_id":null,"queued_work_ids":[],"allocation":"unallocated-shared-turn","owner_ref":{"owner":"authoring_surface","kind":"writing-turn","id":"WT-c24044c3b0a94ef5be8ba8109c513cee","project":"book"},"conceptric_mapping":{"logical_target":null,"obligation_id":null,"status":"unmapped"},"original_tool_attempts":{"writing-tool-read":0,"writing-tool-action":0,"writing-tool-failure":0},"coverage":{"duplicate_original_rows":0,"ambiguous_original_ids":0,"missing_original_ids":0},"failure_receipts":0,"saved_terminal_kinds":["failed"],"execution_coverage":"saved-terminal-receipt"},{"turn_id":"WT-d96c51be347845019e7e95eb403d68fe","session_id":"WS-277c199d3ef0445aaeaa4271f78bfcb2","project":"book","parent_turn_id":null,"child_turn_ids":[],"work_id":null,"queued_work_ids":[],"allocation":"unallocated-shared-turn","owner_ref":{"owner":"authoring_surface","kind":"writing-turn","id":"WT-d96c51be347845019e7e95eb403d68fe","project":"book"},"conceptric_mapping":{"logical_target":null,"obligation_id":null,"status":"unmapped"},"original_tool_attempts":{"writing-tool-read":0,"writing-tool-action":0,"writing-tool-failure":0},"coverage":{"duplicate_original_rows":0,"ambiguous_original_ids":0,"missing_original_ids":0},"failure_receipts":0,"saved_terminal_kinds":[],"execution_coverage":"UNKNOWN"},{"turn_id":"WT-1d6986c73edd4bac9e3c90502c2f4316","session_id":"WS-49decfcbd08e4a43aa6fb346b473c621","project":"book","parent_turn_id":null,"child_turn_ids":[],"work_id":null,"queued_work_ids":[],"allocation":"unallocated-shared-turn","owner_ref":{"owner":"authoring_surface","kind":"writing-turn","id":"WT-1d6986c73edd4bac9e3c90502c2f4316","project":"book"},"conceptric_mapping":{"logical_target":null,"obligation_id":null,"status":"unmapped"},"original_tool_attempts":{"writing-tool-read":0,"writing-tool-action":1,"writing-tool-failure":0},"coverage":{"duplicate_original_rows":0,"ambiguous_original_ids":0,"missing_original_ids":0},"failure_receipts":0,"saved_terminal_kinds":["completed"],"execution_coverage":"saved-terminal-receipt"}],"unallocated_turn_ids":["WT-6b0b80cfcbe744ac862274b4c8b240c8","WT-d189eaa4b04847a69a6fee878b23f855","WT-7906f51187724018b5948e6d87b6cd20","WT-c24044c3b0a94ef5be8ba8109c513cee","WT-d96c51be347845019e7e95eb403d68fe","WT-1d6986c73edd4bac9e3c90502c2f4316"]}},"history_telemetry":{"schema_version":"laplace.activity-history/1","project":"book","as_of":"2026-11-08T21:20:25.273Z","scope":{},"totals":{"activity":15,"dated":15,"unrecorded_date":0},"series":{"activity":[{"start":"2026-10-29T00:00:00Z","end":"2026-10-30T00:00:00Z","label":"2026-10-29","count":3,"filter":{"from":"2026-10-29T00:00:00Z","to":"2026-10-30T00:00:00Z","as_of":"2026-11-08T21:20:25.273Z"}},{"start":"2026-11-08T00:00:00Z","end":"2026-11-09T00:00:00Z","label":"2026-11-08","count":12,"filter":{"from":"2026-11-08T00:00:00Z","to":"2026-11-09T00:00:00Z","as_of":"2026-11-08T21:20:25.273Z"}}],"by_day":[{"day":"2026-10-29","count":3,"filter":{"day":"2026-10-29","as_of":"2026-11-08T21:20:25.273Z"}},{"day":"2026-11-08","count":12,"filter":{"day":"2026-11-08","as_of":"2026-11-08T21:20:25.273Z"}}],"by_actor":[{"actor":"agent","count":6,"filter":{"actor":"agent","as_of":"2026-11-08T21:20:25.273Z"}},{"actor":"unknown","count":9,"filter":{"actor":"unknown","as_of":"2026-11-08T21:20:25.273Z"}}],"by_category":[{"category":"notes","count":1,"filter":{"category":"notes","as_of":"2026-11-08T21:20:25.273Z"}},{"category":"session","count":14,"filter":{"category":"session","as_of":"2026-11-08T21:20:25.273Z"}}],"by_outcome":[{"outcome":"completed","count":4,"filter":{"outcome":"completed","as_of":"2026-11-08T21:20:25.273Z"}},{"outcome":"failed","count":1,"filter":{"outcome":"failed","as_of":"2026-11-08T21:20:25.273Z"}},{"outcome":"recorded","count":10,"filter":{"outcome":"recorded","as_of":"2026-11-08T21:20:25.273Z"}}]},"runs":[],"usage":{"records":0,"missing":6,"by_provider_model":[],"scope_status":"selected-session-activity"},"tool_calls":{"filter":{"event_kind":"tool-attempt","as_of":"2026-11-08T21:20:25.273Z"},"total":1,"by_operation":[{"operation":"workflow_definition_change","count":1,"filter":{"event_kind":"tool-attempt","as_of":"2026-11-08T21:20:25.273Z","operation":"workflow_definition_change"}}],"by_time_operation":[{"start":"2026-11-08T21:00:00Z","end":"2026-11-08T22:00:00Z","operation":"workflow_definition_change","count":1,"filter":{"event_kind":"tool-attempt","as_of":"2026-11-08T21:20:25.273Z","from":"2026-11-08T21:00:00Z","to":"2026-11-08T22:00:00Z","operation":"workflow_definition_change"}}],"by_outcome":[{"outcome":"not_started","count":1,"filter":{"event_kind":"tool-attempt","as_of":"2026-11-08T21:20:25.273Z","outcome":"not_started"}}],"session_choices":[{"id":"WS-49decfcbd08e4a43aa6fb346b473c621","provider":"claude","model":"opus","count":1,"label":"Prepare only this exact saved workflow through workflow_definition_change using…","filter":{"event_kind":"tool-attempt","as_of":"2026-11-08T21:20:25.273Z","session_id":"WS-49decfcbd08e4a43aa6fb346b473c621"}}],"coverage":{"dated":1,"unrecorded_date":0,"provider_model_recorded":1,"response_bytes_recorded":0,"storage_bytes_recorded":1050,"duration_recorded":0,"context_tokens_recorded":0},"operations_omitted":0,"time_operation_bins_omitted":0,"limitations":["Counts include each original writing-tool-read/action/failure row once. Read baselines, context bookkeeping, and reply action copies are excluded.","Durations, response bytes, and context tokens are reported only when the tool row recorded them. Storage bytes are exact journal-line bytes."]},"identity_coverage":[{"type":"recorded_file_identities","count":0,"status":"absent"},{"type":"record_revisions","count":0,"status":"absent"},{"type":"response_fingerprints","count":1,"status":"recorded"}],"activity_buckets_omitted":0,"limitations":["Telemetry uses only banked timestamps, durations, usage, and identities; it does not estimate missing values or verify file bytes."]},"history_activity":{"schema_version":"laplace.activity-history/1","project":"book","as_of":"2026-11-08T21:20:25.273Z","items":[{"id":"activity:journal:WR-06e2df262e23472d83aa04482acb9884","owner":"journal","category":"session","at":"2026-11-08T21:20:25.273Z","actor":{"label":null,"kind":"agent","provider":"claude","model":"opus","role":"author"},"summary":"Stand-in reply for the Sessions scenario. It says nothing about the project.","status":"completed","targets":[],"detail_available":true,"conversation":{"session_id":"WS-49decfcbd08e4a43aa6fb346b473c621","turn_id":"WT-1d6986c73edd4bac9e3c90502c2f4316"}},{"id":"activity:journal:ACTION-f8699c931476406e9ec129a3f344481b","owner":"journal","category":"session","at":"2026-11-08T21:20:25.073Z","actor":{"label":null,"kind":"agent","provider":"claude","model":"opus","role":"author"},"summary":"Tool action: workflow definition change","status":"recorded","targets":[],"detail_available":true,"conversation":{"session_id":"WS-49decfcbd08e4a43aa6fb346b473c621","turn_id":"WT-1d6986c73edd4bac9e3c90502c2f4316"},"event_kind":"tool-attempt","operation":"workflow_definition_change"},{"id":"activity:journal:WT-1d6986c73edd4bac9e3c90502c2f4316","owner":"journal","category":"session","at":"2026-11-08T21:20:22.749Z","actor":{"label":null,"kind":"unknown"},"summary":"Prepare only this exact saved workflow through workflow_definition_change using exactly this request: {\"action\": \"prepare\", \"fan_out_max\": 2, \"goal\": \"Done when the summary is written and checked against the observations.\", \"profile\": \"laplace.app-dispatch/1\", \"reference\": {\"ide…","status":"recorded","targets":[],"detail_available":true,"conversation":{"session_id":"WS-49decfcbd08e4a43aa6fb346b473c621","turn_id":"WT-1d6986c73edd4bac9e3c90502c2f4316"}},{"id":"activity:journal:WT-d96c51be347845019e7e95eb403d68fe","owner":"journal","category":"session","at":"2026-11-08T21:20:15.660Z","actor":{"label":null,"kind":"unknown"},"summary":"SLOWTURN: compare both weeks paragraph by paragraph","status":"recorded","targets":[],"detail_available":true,"conversation":{"session_id":"WS-277c199d3ef0445aaeaa4271f78bfcb2","turn_id":"WT-d96c51be347845019e7e95eb403d68fe"}},{"id":"activity:journal:WR-35a4b719595a48a79737eb6afc8c66bc","owner":"journal","category":"session","at":"2026-11-08T21:20:15.316Z","actor":{"label":null,"kind":"agent","provider":"claude","model":"default","role":"author"},"summary":"Stand-in failure: the provider stopped before replying.","status":"failed","targets":[],"detail_available":true,"conversation":{"session_id":"WS-125ec0ee90a34de2afc0a876ad3b71da","turn_id":"WT-c24044c3b0a94ef5be8ba8109c513cee"}},{"id":"activity:journal:WT-c24044c3b0a94ef5be8ba8109c513cee","owner":"journal","category":"session","at":"2026-11-08T21:20:15.215Z","actor":{"label":null,"kind":"unknown"},"summary":"FAILTURN: check the basil readings against the notebook","status":"recorded","targets":[],"detail_available":true,"conversation":{"session_id":"WS-125ec0ee90a34de2afc0a876ad3b71da","turn_id":"WT-c24044c3b0a94ef5be8ba8109c513cee"}},{"id":"activity:journal:WR-4c45367f1e55469fb0d7434a78b01c24","owner":"journal","category":"session","at":"2026-11-08T21:20:14.868Z","actor":{"label":null,"kind":"agent","provider":"claude","model":"default","role":"author"},"summary":"Stand-in reply for the Sessions scenario. It says nothing about the project.","status":"completed","targets":[],"detail_available":true,"conversation":{"session_id":"WS-cab6be9771e544b2a63e440ac0b2f6b5","turn_id":"WT-7906f51187724018b5948e6d87b6cd20"}},{"id":"activity:journal:WT-7906f51187724018b5948e6d87b6cd20","owner":"journal","category":"session","at":"2026-11-08T21:20:14.770Z","actor":{"label":null,"kind":"unknown"},"summary":"Which readings are the weakest evidence?","status":"recorded","targets":[],"detail_available":true,"conversation":{"session_id":"WS-cab6be9771e544b2a63e440ac0b2f6b5","turn_id":"WT-7906f51187724018b5948e6d87b6cd20"}},{"id":"activity:journal:WR-722392bb58ba4100983d033faf503d11","owner":"journal","category":"session","at":"2026-11-08T21:20:14.427Z","actor":{"label":null,"kind":"agent","provider":"claude","model":"default","role":"author"},"summary":"Stand-in reply for the Sessions scenario. It says nothing about the project.","status":"completed","targets":[],"detail_available":true,"conversation":{"session_id":"WS-3bed4958b6d743f1b520775640d491e9","turn_id":"WT-d189eaa4b04847a69a6fee878b23f855"}},{"id":"activity:journal:WT-d189eaa4b04847a69a6fee878b23f855","owner":"journal","category":"session","at":"2026-11-08T21:20:14.332Z","actor":{"label":null,"kind":"unknown"},"summary":"Draft a caption for the moisture figure","status":"recorded","targets":[],"detail_available":true,"conversation":{"session_id":"WS-3bed4958b6d743f1b520775640d491e9","turn_id":"WT-d189eaa4b04847a69a6fee878b23f855"}},{"id":"activity:journal:WR-65884c276deb4efaaf62640754aa9611","owner":"journal","category":"session","at":"2026-11-08T21:20:13.966Z","actor":{"label":null,"kind":"agent","provider":"claude","model":"default","role":"author"},"summary":"Stand-in reply for the Sessions scenario. It says nothing about the project.","status":"completed","targets":[],"detail_available":true,"conversation":{"session_id":"WS-2dd4fb8565af49f2a6a7a2acfd589f5a","turn_id":"WT-6b0b80cfcbe744ac862274b4c8b240c8"}},{"id":"activity:journal:WT-6b0b80cfcbe744ac862274b4c8b240c8","owner":"journal","category":"session","at":"2026-11-08T21:20:13.870Z","actor":{"label":null,"kind":"unknown"},"summary":"What did the second week of watering show?","status":"recorded","targets":[],"detail_available":true,"conversation":{"session_id":"WS-2dd4fb8565af49f2a6a7a2acfd589f5a","turn_id":"WT-6b0b80cfcbe744ac862274b4c8b240c8"}},{"id":"activity:journal:WR-public-design","owner":"journal","category":"session","at":"2026-10-29T15:42:33.760Z","actor":{"label":null,"kind":"unknown","role":"author"},"summary":"Controlled public answer Ω. The notes describe observations; they do not establish a causal claim or scientific approval.","status":"recorded","targets":[],"detail_available":true,"conversation":{"session_id":"WS-public-design","turn_id":"WT-public-design"}},{"id":"activity:journal:WT-public-design","owner":"journal","category":"session","at":"2026-10-29T15:42:33.727Z","actor":{"label":null,"kind":"unknown"},"summary":"Controlled public request: explain the observations. Created as fixture setup, not a provider execution.","status":"recorded","targets":[],"detail_available":true,"conversation":{"session_id":"WS-public-design","turn_id":"WT-public-design"}},{"id":"activity:concept:seed:book","owner":"concept","category":"notes","at":"2026-10-29T12:41:46Z","actor":{"label":null,"kind":"unknown"},"summary":"project scaffolded through the New Project door (dashboard, J6); the conceptric grows from here","status":"recorded","targets":[{"kind":"concept"}],"detail_available":true}],"pagination":{"offset":0,"limit":20,"total":15,"next_offset":null},"coverage":[{"owner":"authoring","label":"Author corrections","status":"available","omitted":0},{"owner":"journal","label":"Writing activity","status":"available","omitted":0},{"owner":"editor-save","label":"Banked editor saves","status":"available","omitted":0},{"owner":"snapshot","label":"Banked manuscript snapshots","status":"available","omitted":0},{"owner":"concept","label":"Concept rewire records","status":"available","omitted":0},{"owner":"research","label":"Retained research revisions","status":"available","omitted":0},{"owner":"formal","label":"Formal check receipts","status":"available","omitted":0},{"owner":"literature","label":"Reading observations","status":"available","omitted":0}],"limitations":[]}};
// ---- wave 13 captured owner answers (end) ----
// ---- wave 13 second pass (begin): the owners' captured answers for the seeded project (gen/capture2.mjs), served by path and the query the page sent ----
const W13=JSON.parse(readFileSync(new URL('./fixtures/shell/captured-w13.json',import.meta.url),'utf8'));
const seededRoutes=(...paths)=>Object.fromEntries(paths.map(path=>{const rows=Object.entries(W13).filter(([key])=>new URL(key,'http://local').pathname===path).map(([key,value])=>[new URL(key,'http://local').searchParams,value]);
 return [path,q=>{const same=(a,b)=>[...new Set([...a.keys(),...b.keys()])].every(key=>key==='project'||a.get(key)===b.get(key)),hit=rows.find(([params])=>same(params,q));return hit?copy(hit[1]):defaultRoutes()[path](q);}];}));
async function researchCatalogue(){const {installHTMLDocument}=await import('./helpers/html_dom.mjs'),{mountResearchWorkbench}=await import('../src/laplace/web/static_shared/research-workbench.mjs');
 const env=installHTMLDocument({width:1280}),host=document.createElement('main');document.body.append(host);
 const controller=await mountResearchWorkbench(host,{parameters:new URLSearchParams(),request:async(url,payload)=>{if(payload)throw Error('The coverage harness performs no action.');const hit=W13['/work/discovery?'+new URL(url,'http://local').searchParams];if(!hit)throw Error('no captured owner answer for '+url);return copy(hit);}});
 const outline=host.querySelectorAll('button').find(n=>n.textContent==='Show outline');if(outline)await outline.onclick();host.querySelector('[data-rw-browser]').open=true;const saved=host.querySelector('.rg-saved');if(saved)saved.open=true;
 const inspector=host.querySelector('[data-control="research:inspector-toggle"]');if(inspector)await inspector.onclick();
 return {host,controller,shell:{notice:()=>host.querySelector('.rw-status')?.textContent||''},restore(){controller.destroy();env.restore();}};}
// ---- wave 13 second pass (end) ----
const panelsOpen=(name,options={})=>shell(async s=>{await view(name)(s);await openAll(s);if(name==='history'){const overview=s.root.querySelector('[data-control="history:overview"]');if(overview){await overview.onclick?.({preventDefault(){}});await s.settle();await s.settle();await openAll(s);}}},options);
const HARNESSES={
 'research-workbench/workspace':()=>researchBrowser(false),
 'research-workbench/source-selected':()=>researchBrowser(true),
 'shell/cold-entry':shell(),'shell/work-selected':shell(async()=>{},{query:'work=WORK-a'}),
 'shell/return-place':shell(async s=>{await click(s,'[data-work-scope]');},{query:'work=WORK-a'}),
 'shell/manuscript-view':shell(view('manuscript')),
 'shell/help-open':shell(async s=>{await click(s,'[data-guide]');await s.settle();}),
 'shell/cue-running':shell(async s=>{await click(s,'[data-guide]');await s.settle();await click(s,'[data-control="help:task"]');}),
 'shell/manuscript-unavailable':shell(async()=>{},{routes:NO_MANUSCRIPT}),'shell/compact-layout':shell(async()=>{},{width:1000}),
 'now/page':nowPage,
 'dependencies/page':dependenciesPage,'projects/page':projectsPage,'owners/page':ownersPage,
 'shell/switcher-open':shell(async s=>{await click(s,'[data-frame-switch]');}),
 'shell/more-open':shell(async s=>{const more=s.root.querySelector('.frame-more');assert.ok(more,'the frame More');more.open=true;}),
 'overview/ready':shell(),'overview/no-manuscript':shell(async()=>{},{routes:NO_MANUSCRIPT}),
 'work/catalogue':shell(async s=>{await view('work')(s);s.root.querySelector('.task-catalogue-browser').open=true;},{routes:{'/work/state':q=>q.get('view')==='roots'?{project:'book',view:'roots',roots:[{id:'WORK-a',title:'Approach A',status:'blocked',lifecycle:{closed:false}}],counts:{work:1,campaigns:0},read_cut:{revision:'cut'},pagination:{offset:0,returned:1,covered:1,total:1,next_read:null}}:defaultRoutes()['/work/state'](q)}}),'work/selected':shell(openEditors,{query:'work=WORK-a',routes:selectedWorkRoutes(false)}),'work/read-only':()=>work({readOnly:true,listOpen:true}),
 'work/next-action-offered':shell(openEditors,{query:'work=WORK-a',routes:selectedWorkRoutes(true)}),
 'material/files':material,
 'material/readers-open':async()=>{const host=await material(),reader=host.all().find(n=>controlOf2(n)==='material:reader');let parent=reader;while(parent&&(parent.tag!=='details'&&parent.localName!=='details'))parent=parent.parent||parent.parentElement;assert.ok(parent);parent.open=true;return host;},
 'material/bindings':shell(async s=>{await view('material')(s);const options=s.root.querySelector('.material-link-options');assert.ok(options,'existing optional source linking');options.open=true;},{routes:{'/projects/material-references':()=>({references:[copy(REF)],revision:'list-registry',total:1,next_offset:null,owners:{repositories:[]}})}}),
 'material/bindings-artifact':shell(async s=>{await view('material')(s);const options=s.root.querySelector('.material-link-options');assert.ok(options,'existing optional source linking');options.open=true;const kind=s.root.querySelector('[data-control="material:owner-type"]');assert.ok(kind,'the material owner type');kind.value='artifact';await kind.onchange?.();await s.settle();},{routes:{'/projects/material-references':()=>({references:[copy(REF)],revision:'list-registry',total:1,next_offset:null,owners:{repositories:[]}})}}),
 'material/retained-source':shell(async s=>{await view('material')(s);s.root.querySelector('.material-link-options').open=true;},{routes:{'/work/materials':()=>({materials:[{id:'ART-help-public',path:'.artifacts/originals/public.txt',scope:'project',availability:'present',recorded_revision:'sha256:'+'a'.repeat(64),literature:{project:'book',operation:'reference_source',payload:{original:{artifact_id:'ART-help-public',expected_sha256:'sha256:'+'a'.repeat(64)}},http:{method:'GET',url:'/references/source?'+new URLSearchParams({project:'book',original:JSON.stringify({artifact_id:'ART-help-public',expected_sha256:'sha256:'+'a'.repeat(64)})})}}}],pagination:{next_offset:null,total:1},coverage:'One retained public original target.'}),'/projects/material-references':()=>({references:[copy(REF)],revision:'list-registry',total:1,next_offset:null,owners:{repositories:[]}})}}),
 'history/timeline':()=>history(),'history/record-open':()=>history({open:true}),
 
 'settings/families':appSettings,'settings/project':shell(async s=>{await view('settings')(s);const editor=s.root.querySelectorAll('details').find(n=>n.children.some(c=>(c.tag==='summary'||c.localName==='summary')&&c.textContent==='Change future defaults'));assert.ok(editor,'the New conversation defaults editor');editor.open=true;await editor.ontoggle?.();await s.settle();}),// wave 11b: Change future defaults opened explicitly (its Save future defaults is declared)
'settings/preferences':profilePreferences,
 'argument/record':argument,
 'reader-plan/empty':()=>readerPlan({state:'empty'}),'reader-plan/selected':()=>readerPlan({state:'selected'}),'reader-plan/read-only':()=>readerPlan({state:'read-only'}),
 'research/results':research,'research/empty':shell(view('research'),{routes:{'/research/state':()=>({results:[],producers:[]})}}),
 'manuscript/opening':shell(view('manuscript')),'manuscript/write':manuscriptWrite,'manuscript/source-tex':manuscriptSource,
 'manuscript/setup-open':shell(async s=>{await view('manuscript')(s);const setup=s.root.querySelector('[data-control="manuscript:document-setup"]');assert.ok(setup);const tools=setup.closest('.manuscript-tools-more');if(tools)tools.open=true;setup.open=true;await s.settle();}),
 'manuscript/template-open':()=>templateCandidate({reviewed:false}),'manuscript/template-reviewed':()=>templateCandidate({reviewed:true}),
 'review/pending':shell(view('review'),{routes:{'/authoring/proposals':()=>({project:'book',view:'queue',as_of:'cut',proposals:[copy(PROPOSAL)],count:1,count_basis:'current rows on this inspected page; total unknown until complete traversal',pagination:{next_read:null,remaining_candidates:0},coverage:{unavailable_candidate_records:[]}})}}),
 'review/empty':shell(view('review')),
 'review/comments':shell(async s=>{await view('review')(s);const comments=[...s.root.querySelectorAll('button')].find(n=>n.textContent.startsWith('Comments'));if(!comments)throw Error('The existing Comments tab is unavailable.');await comments.onclick();await s.settle();},{routes:{'/authoring/history':()=>({items:[{id:'AC-help-public',kind:'note',scope:'passage',status:'open',text:'Clarify this public claim.',anchor:{file:'paper.tex',line_start:1,line_end:1,quote:'Public claim'},origin_ref:{schema_version:'laplace.feedback-origin/1',project:'book',correction_id:'AC-help-public',feedback_id:'FB-help-public',material_revision:'sha256:'+'a'.repeat(64)},has_review_route:true}],counts:{'passage-comments':{open:1}},revision:'help-revision',pagination:{total:1,next_offset:null}})}}),
 'presentation/not-built':shell(view('presentation')),
 'presentation/build-failed':shell(view('presentation'),{routes:{'/authoring/document':q=>copy(q.get('target_kind')==='derived'?OWNERS.document_derived:FAILED_DOCUMENT)}}),
 'conversation/open':conversationOpen,
 'conversation/composer':shell(async s=>{await click(s,'[data-talk]');}),
 'conversation/context-open':shell(async s=>{await click(s,'[data-talk]');s.root.querySelector('[data-session-options]').open=true;await click(s,'[data-context-open]');s.root.querySelector('[data-session-options]').open=false;}),
 'shared/topology-plain':()=>topology({wide:false}),'shared/topology-folded':()=>topology({wide:true}),'shared/guard-inspector':guardInspector,
};
// wave 13 second pass: the seeded project's owner answers
// the one owner field the seeded project's task lacks, containment deeper than the path shown (reference.location.omitted with its root), is set on the captured detail
const deepWork=()=>{const routes=seededRoutes('/work/state'),base=routes['/work/state'];routes['/work/state']=q=>{const value=base(q),location=value.reference?.location;if(q.get('view')==='detail'&&location?.path?.length)value.reference.location={...location,omitted:2,root:location.path[0]};return value;};return routes;};
HARNESSES['work/seeded']=panelsOpen('work',{query:'work=WORK-w5-002',routes:deepWork()});
// wave 13b: three more of the seeded project's tasks, over the owners' own detail, continuity and observe reads captured for each (gen/capture6.mjs): one that contains other Work, one whose completion needs review, one that waits on another Work
const TASKS=JSON.parse(readFileSync(new URL('./fixtures/shell/captured-w13b-tasks.json',import.meta.url),'utf8'));
const taskRoutes=()=>{const routes=seededRoutes('/work/state'),base=routes['/work/state'];routes['/work/state']=q=>{const id=q.get('id'),viewName=q.get('view');if(id&&['detail','continuity','observe'].includes(viewName)){const hit=Object.entries(TASKS).find(([key])=>{const u=new URL(key,'http://local');return u.searchParams.get('id')===id&&u.searchParams.get('view')===viewName;});if(hit)return copy(hit[1]);}return base(q);};return routes;};
HARNESSES['work/task-contained']=panelsOpen('work',{query:'work=WORK-w5-001',routes:taskRoutes()});
HARNESSES['work/task-review-required']=panelsOpen('work',{query:'work=WORK-compare-notes',routes:taskRoutes()});
HARNESSES['work/task-waiting']=panelsOpen('work',{query:'work=WORK-weekly-guidance',routes:taskRoutes()});
HARNESSES['work/task-held']=panelsOpen('work',{query:'work=WORK-w5-026',routes:taskRoutes()});
HARNESSES['overview/seeded']=panelsOpen('overview',{routes:seededRoutes('/work/state')});
HARNESSES['argument/seeded']=panelsOpen('argument',{routes:{...seededRoutes('/work/state'),'/concepts/tree':()=>CAPTURED.concepts_tree,'/concepts/state':()=>CAPTURED.concepts_state,'/concepts/plan':()=>CAPTURED.concepts_plan,'/concepts/history':()=>CAPTURED.concepts_history,'/concepts/catalog':()=>CAPTURED.concepts_catalog,'/corpus/map':()=>CAPTURED.corpus_map}});
HARNESSES['settings/seeded']=panelsOpen('settings',{routes:seededRoutes('/work/storage')});
HARNESSES['presentation/seeded']=panelsOpen('presentation',{routes:seededRoutes('/authoring/document')});
HARNESSES['research-workbench/catalogue']=researchCatalogue;
// a turn the owner observes running, bound to a task: the captured health and running-session answers, with the owner's work_id field set to a seeded task
HARNESSES['shell/running-now']=shell(async()=>{},{routes:{'/authoring/health':()=>copy(W13['/authoring/health']),'/authoring/session':q=>{const hit=W13['/authoring/session?id=WS-810f2ff31bc54c08a708990dbd8f7581&view=summary&limit=1'];if(q.get('id')!=='WS-810f2ff31bc54c08a708990dbd8f7581'||!hit)return defaultRoutes()['/authoring/session'](q);const value=copy(hit);value.active={...value.active,work_id:'WORK-w5-002'};return value;}}});
// ---- wave 13b: Activity > Graphs (the session analytics views), each view a state, over the owners' captured answers ----
// tests/fixtures/shell/captured-w13b-graphs.json holds the owners' real GET answers for the seeded project (gen/capture3.mjs, project renamed 'book');
// the feedback and commissioned-conversation states use the owner's actual emission in tests/fixtures/session-analytics-joined-3e69533c3.json (project 'p' renamed 'book').
const GRAPHS=JSON.parse(readFileSync(new URL('./fixtures/shell/captured-w13b-graphs.json',import.meta.url),'utf8'));
const JOINED=JSON.parse(readFileSync(new URL('./fixtures/session-analytics-joined-3e69533c3.json',import.meta.url),'utf8'));
const joinedAsBook=value=>JSON.parse(JSON.stringify(value).replaceAll('"project":"p"','"project":"book"'));
const queryKey=params=>[...params].filter(([k])=>k!=='as_of').map(([k,v])=>k+'='+v).sort().join('&');
const GRAPH_ANSWERS=new Map(Object.entries(GRAPHS).map(([url,value])=>[queryKey(new URL(url,'http://local').searchParams),value]));
const FACETS=JSON.parse(readFileSync(new URL('./fixtures/actual-call-facets-20261007.json',import.meta.url),'utf8')),facetsAsBook=value=>JSON.parse(JSON.stringify(value).replaceAll('writing-system-architecture','book'));
const graphsRoutes=(over={})=>({'/authoring/history':q=>{const projection=q.get('projection'),hit=over[projection||(q.get('outcome')==='failed'?'failures':'telemetry')]?.(q);if(hit!==undefined)return hit;const found=GRAPH_ANSWERS.get(queryKey(q));if(!found)throw Error('no captured owner answer for '+queryKey(q));return found;}});
const graphsTab=label=>async s=>{const tab=[...s.root.querySelectorAll('button')].find(b=>b.textContent===label);assert.ok(tab,'the '+label+' tab');await tab.onclick?.({preventDefault(){}});await s.settle();await s.settle();};
const graphsView=(label,over)=>shell(async s=>{await view('history')(s);await graphsTab('Graphs')(s);if(label)await graphsTab(label)(s);},{routes:graphsRoutes(over)});
HARNESSES['history/graphs']=graphsView(null);
// the plots draw the owner's actual call facets (tests/fixtures/actual-call-facets-20261007.json, project renamed) and, for usage bars, its actual usage emission
HARNESSES['history/graphs-analysis']=graphsView('Graphs & analysis',{telemetry:()=>facetsAsBook(FACETS.telemetry),failures:()=>facetsAsBook(FACETS.failures),usage:()=>joinedAsBook(JOINED.queries.usage)});
HARNESSES['history/graphs-trace']=graphsView('Selected activity');
HARNESSES['history/graphs-usage']=shell(async s=>{await view('history')(s);await graphsTab('Graphs')(s);await graphsTab('Usage')(s);await openAll(s);},{routes:graphsRoutes()});// each attempt's card opened
HARNESSES['history/graphs-delivery']=graphsView('Delivery');
// the owner's actual feedback emission (one recorded feedback record) answers the Feedback view
HARNESSES['history/graphs-feedback']=graphsView('Feedback',{feedback:()=>joinedAsBook(JOINED.queries.feedback)});
// the owner's actual sessions emission lists a conversation that a saved turn commissioned
HARNESSES['history/graphs-commissioned']=graphsView(null,{sessions:()=>joinedAsBook(JOINED.queries.sessions),overview:()=>joinedAsBook(JOINED.queries.overview)});
// a read of the view fails with an owner refusal; the page keeps the refusal and offers Retry
HARNESSES['history/graphs-failed']=graphsView(null,{overview:()=>ownerReply(503,{error:'The recorded activity could not be read.'})});
// the exact saved record behind one Selected activity row (the owner's captured record read), rendered by renderAnalyticsRecord
HARNESSES['history/graphs-record']=async()=>{const {installHTMLDocument}=await import('./helpers/html_dom.mjs'),{renderAnalyticsRecord}=await loadShared('workspace-analytics.mjs');
 const env=installHTMLDocument({width:1280}),host=document.createElement('section');document.body.append(host);
 const record=copy([...GRAPH_ANSWERS].find(([key])=>/view=record/.test(key))[1]);renderAnalyticsRecord(host,record,{project:'book',id:record.item.id});
 return {host,restore:()=>env.restore(),shell:{notice:()=>''}};};
// the response note box, opened over the response target the owner names on the latest conversation (the captured sessions answer)
HARNESSES['history/graphs-note']=async()=>{const {installHTMLDocument}=await import('./helpers/html_dom.mjs'),{openResponseFeedback}=await loadShared('workspace-analytics.mjs');
 const env=installHTMLDocument({width:1280}),sessions=[...GRAPH_ANSWERS].find(([key])=>/projection=sessions/.test(key))[1],target=sessions.items.find(row=>row.latest_reply_target).latest_reply_target;
 openResponseFeedback(copy(target),{request:async()=>{throw Error('The coverage harness performs no action.');},onTurn(){}});
 return {host:document.documentElement,restore:()=>env.restore(),shell:{notice:()=>''}};};
// ---- wave 13b: the Literature source box a retained original opens (retained-source-literature.mjs), each state mounted through its own exported opener ----
// the owner's shapes are the ones tests/retained_source_literature.test.mjs holds for the retained-source Literature owner (standing read, import action, closed-schema refusal)
const RSL={project:'book',original:{artifact_id:'ART-public',expected_sha256:'sha256:'+'a'.repeat(64)}};
RSL.read={project:RSL.project,operation:'reference_source',payload:{original:RSL.original},http:{method:'GET',url:'/references/source?'+new URLSearchParams({project:RSL.project,original:JSON.stringify(RSL.original)})}};
RSL.action={permitted:true,operation:'literature_import',http:{method:'POST',url:'/references/literature-import'},payload:{project:RSL.project,original:RSL.original},requires:['metadata','provenance']};
RSL.standing=(state='NONE',association=null)=>({schema_version:'laplace.retained-source-literature/1',project:RSL.project,original:RSL.original,source:{display_name:'Public transcript.txt',media_type:'text/plain; charset=utf-8'},support:{permitted:true},standing:{state,...(association?{association,key:association.key}:{}),metadata_saved:state==='RECORDED',bibliography:{state:'PENDING'}},actions:{import:RSL.action,reconcile:RSL.read},read:RSL.read});
RSL.association={key:'local:public',citekey:'public2026',metadata:{title:'Public finding'}};
RSL.rejection={error:'Retained source metadata violates the closed schema.',metadata_saved:false,disposition:{state:'REJECTED_BEFORE_EFFECTS',operation:'literature_import',reason_code:'INVALID_RETAINED_IMPORT'}};
const retainedLiterature=mode=>async()=>{const {installHTMLDocument}=await import('./helpers/html_dom.mjs'),{openRetainedSourceLiterature,createRetainedLiteratureDraft}=await loadShared('retained-source-literature.mjs');
 const env=installHTMLDocument({width:1280}),keep=()=>{const data=new Map();return {getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,v)};};
 let phase=mode==='recorded'?'RECORDED':'NONE';const request=async(path,payload)=>{if(payload){if(mode==='rejected'||mode==='edited')throw Object.assign(Error('refused'),{result:copy(RSL.rejection)});throw Error('The owner did not answer before the connection closed.');}return RSL.standing(phase,phase==='RECORDED'?RSL.association:null);};
 const draft=createRetainedLiteratureDraft({project:RSL.project,original:RSL.original,storage:keep(),backup:keep()}),opened=await openRetainedSourceLiterature({project:RSL.project,read:RSL.read,request,draft}),dialog=opened.dialog,settle=()=>new Promise(resolve=>setTimeout(resolve,15));
 const field=name=>dialog.querySelectorAll('input, textarea, select').find(node=>node.name===name);
 if(['lost','found','rejected','edited'].includes(mode)){for(const [name,value] of Object.entries({title:'Public finding',description:'Supplied public original',item_type:'unpublished'})){const node=field(name);node.value=value;node.oninput?.();}await dialog.querySelectorAll('form')[0].onsubmit({preventDefault(){}});await settle();}
 if(mode==='found'){phase='RECORDED';await dialog.querySelectorAll('button').find(node=>node.textContent==='Check Literature source').onclick();await settle();}
 if(mode==='edited'){await dialog.querySelectorAll('button').find(node=>node.textContent==='Edit details').onclick();await settle();}
 await settle();dialog.querySelectorAll('details').forEach(box=>{box.open=true;});
 return {host:document.documentElement,restore:()=>{dialog.close?.();env.restore();},shell:{notice:()=>''}};};
for(const mode of ['new','recorded','lost','found','rejected','edited'])HARNESSES['material/literature-'+mode]=retainedLiterature(mode);
// ---- wave 13b: the complete review response box (openFeedbackReply, feedback-route.mjs), over the owner's captured message-part read ----
const reviewResponse=failing=>async()=>{const {installHTMLDocument}=await import('./helpers/html_dom.mjs'),{openFeedbackReply}=await loadShared('feedback-route.mjs');
 const env=installHTMLDocument({width:1280}),first=copy(Object.entries(GRAPHS).find(([key])=>/session-turn.*limit=40/.test(key))[1]);let calls=0;
 const dialog=await openFeedbackReply({project:first.project,handle:copy(first.page_read),request:async()=>{if(failing&&calls++){if(calls>1)throw Error('The owner could not read the next page.');}return copy(first);}});
 const press=async label=>{const node=dialog.querySelectorAll('button').find(b=>b.textContent===label);await node.onclick();await new Promise(resolve=>setTimeout(resolve,15));};
 if(failing){await press('Continue reading response');}
 dialog.querySelectorAll('details').forEach(box=>{box.open=true;});
 return {host:document.documentElement,restore:()=>{dialog.close?.();env.restore();},shell:{notice:()=>''}};};
HARNESSES['review/response-partial']=reviewResponse(false);
HARNESSES['review/response-failed']=reviewResponse(true);
// ---- wave 13c: the passage comment dialog (openFeedbackComment, feedback-route.mjs) over the owner's answers captured from the seeded throwaway project ----
// authoring/correction-prepare, work/state and work/delivery route-preview are the owner's own answers (tests/fixtures/shell/captured-w13c-comment.json, capture8.mjs and capture9.mjs); the one write, POST /authoring/correction, is refused as a lost connection, so nothing is invented about what the owner would record
const COMMENT=JSON.parse(readFileSync(new URL('./fixtures/shell/captured-w13c-comment.json',import.meta.url),'utf8'));
const withRequestId=(value,from,to)=>JSON.parse(JSON.stringify(value).replaceAll(from,to));
const commentDialog=steps=>async()=>{const {installHTMLDocument}=await import('./helpers/html_dom.mjs'),{openFeedbackComment}=await loadShared('feedback-route.mjs');
 const env=installHTMLDocument({width:1280}),oldSession=globalThis.sessionStorage,stored=new Map();globalThis.sessionStorage={getItem:k=>stored.get(k)??null,setItem:(k,v)=>stored.set(k,String(v)),removeItem:k=>stored.delete(k)};
 const settle=()=>new Promise(resolve=>setTimeout(resolve,60)),prepare=copy(COMMENT.prepare.request);delete prepare.project;
 const request=async(path,body)=>{const url=new URL(path,'http://local');
  if(url.pathname==='/authoring/correction-prepare')return copy(COMMENT.prepare.response);
  if(url.pathname==='/work/state')return copy(COMMENT.work_state);
  if(url.pathname==='/work/delivery'){const asked=JSON.parse(url.searchParams.get('request')),held=COMMENT.route_previews[asked.work_id];if(!held)throw Error('No captured route preview for '+asked.work_id);return withRequestId(held.answer,held.request_id,asked.request_id);}
  if(url.pathname==='/authoring/correction')throw Error('The connection closed before the owner answered.');
  if(url.pathname==='/authoring/correction-request'){const id=url.searchParams.get('request_id');return withRequestId(url.searchParams.has('submission')?COMMENT.comparison:COMMENT.lookup,COMMENT.retained_request_id,id);}
  throw Error('UNRECORDED_COMMENT_READ '+path);};
 const dialog=await openFeedbackComment({project:'book',selection:{anchor:copy(prepare.anchor),prepare},request});await settle();
 const press=async label=>{const node=dialog.querySelectorAll('button').find(b=>b.textContent===label);await node.onclick();await settle();};
 const reviewers=()=>{const box=dialog.querySelectorAll('details').find(d=>d.querySelectorAll('summary').some(n=>n.textContent==='Reviewers and limits'));box.open=true;return box.ontoggle();};
 await steps({dialog,settle,press,reviewers,type:value=>{const box=dialog.querySelector('textarea');box.value=value;box.oninput?.();}});
 return {host:document.documentElement,restore:()=>{dialog.close?.();env.restore();globalThis.sessionStorage=oldSession;},shell:{notice:()=>''}};};
const chooseFirstWork=async({dialog,settle})=>{const select=dialog.querySelectorAll('select')[0];select.value=Object.keys(COMMENT.route_previews)[0];await select.onchange();await settle();};
const loseSave=async c=>{c.type(COMMENT.comment_text);await c.press('Save comment');};
HARNESSES['review/comment-new']=commentDialog(async()=>{});
HARNESSES['review/comment-routing']=commentDialog(async c=>{await c.reviewers();await c.settle();});
HARNESSES['review/comment-routed']=commentDialog(async c=>{await c.reviewers();await c.settle();await chooseFirstWork(c);});
HARNESSES['review/comment-lost']=commentDialog(loseSave);
HARNESSES['review/comment-unrecorded']=commentDialog(async c=>{await loseSave(c);await c.press('Check save');});
// ---- wave 13c: the editor frame's toolbar (writing-panel.mjs and walk.html) ----
// walk.html's own header markup is parsed, and the toolbar lines of writing-panel.mjs, cut from the module's actual text, run over it with the frame's workbench query; the walk is a stand-in that is only read when a button is pressed
// the frame's own address contract (writing-panel.mjs header G and its `q.get('editor')==='workbench'` branch): the shell hosts the frame as /walk?corpus=<project>&embedded=1&editor=workbench; the harnesses pass that query, they do not restate any other rule
const FRAME_QUERY='editor=workbench&corpus=book&embedded=1';
const frameToolbar=open=>async()=>{const {installHTMLDocument}=await import('./helpers/html_dom.mjs'),{declareControl}=await loadShared('workspace-presentation.mjs');
 const env=installHTMLDocument({width:1280}),walkHtml=readFileSync(new URL('../src/laplace/web/walk.html',import.meta.url),'utf8'),panel=readFileSync(new URL('../src/laplace/web/static_shared/writing-panel.mjs',import.meta.url),'utf8');
 const header=/<header id="bar">[\s\S]*?<\/header>/.exec(walkHtml)[0].replace(/<!--[\s\S]*?-->/g,''),root=document.createElement('div');root.id='walk';root.innerHTML=header+'<main id="paper"></main>';document.body.append(root);
 const first=panel.indexOf("  const points=declareControl(E('button','','Open points')"),mark="$('#bar').insertBefore(reading,editorStatus);}",last=panel.indexOf(mark,first);assert.ok(first>0&&last>first,'writing-panel holds the toolbar lines');
 const E=(tag,cls,text)=>{const node=document.createElement(tag);if(cls)node.className=cls;if(text!=null)node.textContent=text;return node;},$=(selector,scope=document)=>scope.querySelector(selector),editorStatus=E('span','','Click to write');$('#bar').append(editorStatus);
 const store=new Map(),localStorage={getItem:k=>store.get(k)??null,setItem:(k,v)=>store.set(k,String(v))},win={walk:{},dispatchEvent(){},parent:{postMessage(){}}};
 new Function('E','$','declareControl','openPoints','editorStatus','root','save','q','send','projectId','request','pendingRead','window','localStorage',panel.slice(first,last+mark.length))(E,$,declareControl,()=>{},editorStatus,root,{hidden:false},new URLSearchParams(FRAME_QUERY),()=>{},'book',async()=>({}),()=>{},win,localStorage);
 if(open)root.querySelectorAll('details').find(box=>box.className.includes('writing-reading-options')).open=true;
 return {host:document.documentElement,restore:()=>env.restore(),shell:{notice:()=>''}};};
HARNESSES['manuscript/frame-toolbar']=frameToolbar(false);
HARNESSES['manuscript/frame-reading']=frameToolbar(true);
// the selection toolbar and the passage menu of the editor frame: their lines are cut from writing-panel.mjs's own text and run over a stand-in walk that answers from the frame's captured model rows of the seeded project (tests/fixtures/shell/captured-w13c-frame.json)
const FRAME=JSON.parse(readFileSync(new URL('./fixtures/shell/captured-w13c-frame.json',import.meta.url),'utf8'));
const frameParts=async()=>{const {installHTMLDocument}=await import('./helpers/html_dom.mjs'),{declareControl,groupedMenu,contextMenuPlacement}=await loadShared('workspace-presentation.mjs');
 const env=installHTMLDocument({width:1280}),panel=readFileSync(new URL('../src/laplace/web/static_shared/writing-panel.mjs',import.meta.url),'utf8');
 const E=(tag,cls,text)=>{const node=document.createElement(tag);if(cls)node.className=cls;if(text!=null)node.textContent=text;return node;},editorStatus=E('span','','');
 const cut=(from,to)=>{const first=panel.indexOf(from),last=panel.indexOf(to,first);assert.ok(first>0&&last>first,'writing-panel holds '+from.trim().slice(0,40));return panel.slice(first,last);};
 return {env,panel,E,editorStatus,cut,declareControl,groupedMenu,contextMenuPlacement};};
HARNESSES['manuscript/frame-bubble']=async()=>{const {env,E,editorStatus,cut,declareControl}=await frameParts(),bubble=E('div');document.body.append(bubble);
 new Function('E','declareControl','bubble','selected','selectedPoint','editorStatus','commentFrom','queueRequest','window','location',cut("  for(const [label,mode,id]of [['Comment'","  $('#paper').addEventListener('mouseup'"))(E,declareControl,bubble,{},{},editorStatus,async()=>{},()=>{},{walk:{},parent:{postMessage(){}}},{origin:'http://local'});
 return {host:document.documentElement,restore:()=>env.restore(),shell:{notice:()=>''}};};
// wave 14a/14b: the save warning on the frame's status line carries Keep my text and save it first, and Show the other version
// when another writer changed a paragraph under his draft (walk.editState().moved)
HARNESSES['manuscript/frame-save-warning']=async()=>{const {env,E,editorStatus,cut,declareControl}=await frameParts();document.body.append(editorStatus);
 editorStatus.textContent='A recovered draft was typed against text that has changed since; your text is kept in its paragraph.';
 const offerKeep=new Function('E','declareControl','editorStatus','window','document',cut("  const offerKeep=","  const ready=()=>{")+';return offerKeep;')(E,declareControl,editorStatus,{walk:{editState:()=>({dirty:true,parked:1,moved:1}),commitAll:async()=>({message:'Saved'}),showOtherVersion:()=>true}},document);
 offerKeep();return {host:document.documentElement,restore:()=>env.restore(),shell:{notice:()=>''}};};
HARNESSES['manuscript/frame-menu']=async()=>{const {env,E,editorStatus,cut,declareControl,groupedMenu,contextMenuPlacement}=await frameParts();
 const row=FRAME.rows.find(r=>r.kind==='para'),paper=document.createElement('div');paper.id='paper';const blockEl=document.createElement('div');blockEl.className='blk';blockEl.dataset.block=row.id;paper.append(blockEl);document.body.append(paper);
 const walk={blocks:query=>query?.id?[{...row,text:FRAME.texts[row.id]}]:copy(FRAME.rows),contextualInsertionPoint:()=>copy(FRAME.points[row.id]),objectKind:()=>FRAME.object_kinds[row.id],sections:()=>copy(FRAME.sections),ready:()=>true,sourceObservation:()=>({current_revision:'sha256:'+'1'.repeat(64)})};
 const handler=cut("  document.addEventListener('contextmenu'","  const ready=()=>{bindPassageContext");
 new Function('E','document','window','q','bubble','selected','closeMenuHolder','groupedMenu','contextMenuPlacement','blockSourceLocation','queueRequest','commentBasis','commentFrom','openPoints','send','editorStatus','declareControl','location','innerWidth','blocks','let contextMenu=null;const closeMenu=()=>{contextMenu?.remove();contextMenu=null;};\n'+handler)(E,document,{walk},new URLSearchParams(FRAME_QUERY),{hidden:true},null,null,groupedMenu,contextMenuPlacement,()=>null,()=>{},()=>({}),async()=>{},()=>{},()=>{},editorStatus,declareControl,{origin:'http://local'},1280,FRAME.rows);
 document.dispatchEvent({type:'contextmenu',target:blockEl,clientX:40,clientY:40,preventDefault(){}});
 return {host:document.documentElement,restore:()=>env.restore(),shell:{notice:()=>''}};};
HARNESSES['manuscript/frame-find']=async()=>{const {installHTMLDocument}=await import('./helpers/html_dom.mjs'),env=installHTMLDocument({width:1280});
 document.body.innerHTML='<div id="walk"><header id="bar"></header><main id="paper"><div id="doc"></div><div id="doc-note"></div></main></div>';
 (await loadShared('walk-card.mjs')).openFindDialog();
 return {host:document.documentElement,restore:()=>{document.querySelectorAll('dialog').forEach(box=>box.close?.());env.restore();},shell:{notice:()=>''}};};
HARNESSES['manuscript/frame-context']=async()=>{const {env,E,cut,declareControl}=await frameParts(),{pendingRead}=await loadShared('pending-read.mjs'),owner=await loadShared('writing-owner-read.mjs');
 const row=FRAME.rows.find(r=>r.kind==='para'),doc=document.createElement('div');doc.id='doc';document.body.append(doc);const $=(selector,scope=document)=>scope.querySelector(selector);
 const win={walk:{captureFocus:()=>null,restoreFocus(){}},getSelection:()=>null,parent:{postMessage(){}}},asked=[];
 const open=new Function('E','declareControl','$','window','projectId','request','pendingRead','passageProvenancePresentation','passageContinuationURL','send0',cut('  let contextFocus=null','  const points=declareControl(E(\'button\',\'\',\'Open points\')')+'\nreturn openPoints;')(E,declareControl,$,win,'book',async path=>{asked.push(path);assert.ok(path.startsWith('/concepts/plan/context?'),'only the owner context read is asked');return copy(FRAME.passage_context);},pendingRead,owner.passageProvenancePresentation,owner.passageContinuationURL,()=>{});
 await open({...row,text:FRAME.texts[row.id]});await new Promise(resolve=>setTimeout(resolve,30));
 assert.equal(asked.length,1);
 return {host:document.documentElement,restore:()=>env.restore(),shell:{notice:()=>''}};};
HARNESSES['manuscript/frame-queue']=async()=>{const {env,E,editorStatus,cut,declareControl}=await frameParts(),row=FRAME.rows.find(r=>r.kind==='para');
 const queue=new Function('E','declareControl','editorStatus','request','projectId','window','location',cut('  function queueRequest(selection){','  function commentBasis(')+'\nreturn queueRequest;')(E,declareControl,editorStatus,async()=>({}),'book',{parent:{postMessage(){}}},{origin:'http://local'});
 queue({anchor:{file:row.file,line_start:row.line_start,line_end:row.line_end,section:row.section},quote:FRAME.texts[row.id]});
 return {host:document.documentElement,restore:()=>{document.querySelectorAll('dialog').forEach(box=>box.close?.());env.restore();},shell:{notice:()=>''}};};
// ---- wave 13b: Graphs (end) ----
// ---- wave 13b: the reader of one saved message (conversation-reading.mjs), mounted over the owner's captured message-part read ----
// a short page of one saved reply (the owner's own read with limit=40, so it issues a next page); after a failed continuation the reader offers Retry and Restart
const messageReading=failing=>async()=>{const {installHTMLDocument}=await import('./helpers/html_dom.mjs'),{mountMessageReading}=await loadShared('conversation-reading.mjs');
 const env=installHTMLDocument({width:1280}),first=copy(Object.entries(GRAPHS).find(([key])=>/session-turn.*limit=40/.test(key))[1]),target={project:first.project,session_id:first.session_id,turn_id:first.turn_id,part:first.part};
 const row=document.createElement('article'),body=document.createElement('div');body.className='session-body';row.append(body);document.body.append(row);let calls=0;
 const reader=mountMessageReading(row,{target,request:async()=>{if(failing&&calls++)throw Error('The owner could not read the next page.');return copy(first);},isCurrent:()=>true,changed:write=>write()});
 await reader.open();if(failing){await reader.next();}
 return {host:document.documentElement,restore:()=>{reader.dispose();env.restore();},shell:{notice:()=>''}};};
HARNESSES['conversation/reading-partial']=messageReading(false);
HARNESSES['conversation/reading-failed']=messageReading(true);
// ---- wave 13b: Review & notes (workspace-review.mjs), the records of the history owner and the proposal owner, mounted by the real shell ----
// the record shapes are the history owner's (the existing 'review/comments' harness holds the same passage comment with its exact origin); the closed page, a reply and an applied edit are owner-shaped
const REVIEW_ORIGIN={schema_version:'laplace.feedback-origin/1',project:'book',correction_id:'AC-help-public',feedback_id:'FB-help-public',material_revision:'sha256:'+'a'.repeat(64)};
const reviewRow=(over={})=>({id:'AC-help-public',kind:'note',scope:'passage',status:'open',text:'Clarify this public claim.',anchor:{file:'paper.tex',line_start:1,line_end:1,quote:'Public claim'},origin_ref:REVIEW_ORIGIN,has_review_route:true,...over});
const CLOSED_ROWS=()=>[reviewRow({id:'AC-resolved',status:'resolved',status_history:[{status:'resolved',at:'2026-11-01T10:00:00Z',by:'author'}]}),reviewRow({id:'AC-reply',status:'dismissed',reply_to:'AC-resolved',origin_ref:null,has_review_route:false}),reviewRow({id:'AC-edit',correction_category:'applied-edits',status:'applied',origin_ref:null,has_review_route:false})];
const reviewHistory=(rows,{next=false}={})=>q=>{if(q.get('id'))return {item:rows.find(row=>row.id===q.get('id'))||rows[0],revision:'help-revision'};const offset=Number(q.get('offset')||0);return {items:copy(rows),counts:{'passage-comments':{open:1}},revision:'help-revision',total:rows.length,next_offset:next&&!offset?20:null,pagination:{total:rows.length,next_offset:next&&!offset?20:null}};};
const reviewTab=label=>async s=>{const node=[...s.root.querySelectorAll('button')].find(n=>n.textContent.startsWith(label));assert.ok(node,'the '+label+' tab');await node.onclick();await s.settle();};
const reviewPress=label=>async s=>{const node=[...s.root.querySelectorAll('button')].find(n=>n.textContent===label);assert.ok(node,'the '+label+' button');await node.onclick({preventDefault(){}});await s.settle();};
const reviewShell=(steps,routes)=>shell(async s=>{await view('review')(s);for(const step of steps)await step(s);},{routes});
const PROPOSALS_ROUTE=(more=false)=>({'/authoring/proposals':()=>({project:'book',view:'queue',as_of:'cut',proposals:[copy(PROPOSAL)],count:1,count_basis:'current rows on this inspected page; total unknown until complete traversal',pagination:{next_read:more?{http:{method:'GET',url:'/authoring/proposals?project=book&offset=1'}}:null,remaining_candidates:more?1:0},coverage:{unavailable_candidate_records:[]}})});
HARNESSES['review/note-draft']=reviewShell([reviewTab('Comments'),reviewPress('New project note'),reviewPress('Review current save revision')],{'/authoring/history':reviewHistory([reviewRow()])});
HARNESSES['review/comments-closed']=reviewShell([reviewTab('Closed')],{'/authoring/history':reviewHistory(CLOSED_ROWS(),{next:true})});
HARNESSES['review/comments-paged']=reviewShell([reviewTab('Closed'),reviewPress('More records')],{'/authoring/history':reviewHistory(CLOSED_ROWS(),{next:true})});
HARNESSES['review/comments-focus']=reviewShell([reviewTab('Comments'),reviewPress('Inspect full record')],{'/authoring/history':reviewHistory([reviewRow()])});
HARNESSES['review/page-failed']=reviewShell([reviewTab('Comments')],{'/authoring/history':()=>ownerReply(503,{error:'The recorded history could not be read.'})});
HARNESSES['review/proposals-more']=reviewShell([],PROPOSALS_ROUTE(true));
// ---- wave 13b: App settings categories (workspace-app.mjs with workspace-writing-style.mjs) and structural preferences with editing ----
const appSettingsCategory=(label,search='')=>async()=>{const oldLocation=globalThis.location;if(search)globalThis.location={search,href:'http://local/'+search,pathname:'/'};const host=await appSettings();if(search){if(oldLocation)globalThis.location=oldLocation;else delete globalThis.location;}
 const node=host.all().find(n=>n.tag==='button'&&n.textContent===label);assert.ok(node,'the '+label+' category');await node.onclick();await new Promise(resolve=>setTimeout(resolve,20));
 return host;};
HARNESSES['settings/writing-voice']=appSettingsCategory('Writing & voice');
HARNESSES['settings/storage-recovery']=appSettingsCategory('Storage & recovery');
HARNESSES['settings/storage-recovery-project']=appSettingsCategory('Storage & recovery','?return_project=book');
HARNESSES['settings/architecture']=async()=>{const {mountProfilePreferences}=await import('../src/laplace/web/static_shared/profile-preferences.mjs');
 const fixture=JSON.parse(readFileSync(new URL('./fixtures/editor_spine/profile-candidates.json',import.meta.url),'utf8')),host=new Node('main');document.body.append(host);
 const request=async path=>{const url=new URL(path,'http://local'),v=url.searchParams.get('view');if(v==='summary')return copy(url.searchParams.has('project')?fixture.before:fixture.global_summary);if(v==='content')return copy(fixture.current);if(v==='candidates')return {candidates:[copy(fixture.candidate)],pagination:{returned:1,total:1}};if(v==='candidate')return copy(fixture.candidate);return {};};
 await mountProfilePreferences(host,{project:'book',family:'architecture',scope:'workspace',request,onChanged(){},enableEdit:true});return host;};
// ---- wave 13b: Explore (research-workbench.mjs), mounted over the owners' captured /work/discovery reads of the seeded project (gen/captured7.json, the four reads these states need) ----
const EXPLORE=JSON.parse(readFileSync(new URL('./fixtures/shell/captured-w13b-explore.json',import.meta.url),'utf8'));
const exploreState=steps=>async()=>{const {installHTMLDocument}=await import('./helpers/html_dom.mjs'),{mountResearchWorkbench}=await loadShared('research-workbench.mjs');
 const env=installHTMLDocument({width:1280}),host=document.createElement('main'),settle=()=>new Promise(resolve=>setTimeout(resolve,25));document.body.append(host);
 const request=async(url,payload)=>{if(payload)throw Error('The coverage harness performs no action.');const hit=EXPLORE[url];if(!hit)throw Error('no captured owner answer for '+url.slice(0,120));return copy(hit);};
 const controller=await mountResearchWorkbench(host,{parameters:new URLSearchParams(),request});await settle();
 const press=async(label,exact=true)=>{const node=host.querySelectorAll('button').find(n=>exact?n.textContent===label:n.textContent.startsWith(label));assert.ok(node,'no button '+label);await node.onclick({preventDefault(){},stopPropagation(){}});await settle();await settle();};
 await steps({host,press,settle,controller});host.querySelectorAll('details').forEach(box=>{box.open=true;});
 return {host:document.documentElement,restore:()=>{controller.destroy();env.restore();},shell:{notice:()=>''}};};
const EXPLORE_TASK='Confirm the dates of the two missing readings',EXPLORE_WORKFLOW='Write and check a summary';
HARNESSES['research-workbench/object-overview']=exploreState(async m=>{await m.press(EXPLORE_TASK,false);});
HARNESSES['research-workbench/object-consequences']=exploreState(async m=>{await m.press(EXPLORE_TASK,false);await m.press('Consequences');});
HARNESSES['research-workbench/object-handover']=exploreState(async m=>{await m.press(EXPLORE_TASK,false);await m.press('Handover');});
HARNESSES['research-workbench/workflow-settings']=exploreState(async m=>{await m.press(EXPLORE_WORKFLOW,false);await m.press('Settings');});
HARNESSES['research-workbench/relation-outline']=exploreState(async m=>{await m.press('Relation outline');});
HARNESSES['research-workbench/relation-map']=exploreState(async m=>{await m.press('Relation map');});
// ---- wave 13b: Research > Formal proof (writing-evidence.mjs): the owners' captured formal state and targets reads of the seeded project, formal checking not yet set up ----
HARNESSES['research/formal-setup']=async()=>{const {installHTMLDocument}=await import('./helpers/html_dom.mjs'),{mountEvidence}=await loadShared('writing-evidence.mjs'),FORMAL=JSON.parse(readFileSync(new URL('./fixtures/shell/captured-w13b-formal.json',import.meta.url),'utf8'));
 const env=installHTMLDocument({width:1280}),host=document.createElement('main'),hadFrame=globalThis.requestAnimationFrame;globalThis.requestAnimationFrame=fn=>setTimeout(fn,0);document.body.append(host);const read=prefix=>copy(Object.entries(FORMAL).find(([key])=>key.startsWith(prefix))[1]);
 const request=async path=>{if(path.startsWith('/formal/state'))return read('/formal/state');if(path.startsWith('/formal/targets'))return read('/formal/targets');if(path.startsWith('/research/state'))return read('/research/state');if(path.startsWith('/visuals/state'))return {specs:[]};if(path.startsWith('/concepts/state'))return null;throw Error('unexpected '+path);};
 await mountEvidence(host,{project:'book',request,status(){},work(){},onOpenUsage(){},view:'formal'});document.documentElement.querySelectorAll('details').forEach(box=>{box.open=true;});
 await new Promise(resolve=>setTimeout(resolve,30));return {host:document.documentElement,restore:()=>{env.restore();if(hadFrame)globalThis.requestAnimationFrame=hadFrame;else delete globalThis.requestAnimationFrame;},shell:{notice:()=>''}};};
// ---- wave 13b: Research > Literature (workspace-literature.mjs, with literature-metadata.mjs) ----
// the owners' captured reads of the seeded project after one local source is saved through its own form (gen/capture4.mjs, name rewritten to 'book'); fields the seeded
// project's owner does not answer (claim links, citations, fetched text, discovery, a further page) are owner-shaped, taken from tests/workspace_literature.test.mjs
const LITC=JSON.parse(readFileSync(new URL('./fixtures/shell/captured-w13b-literature.json',import.meta.url),'utf8'));
const litRead=prefix=>copy(Object.entries(LITC).find(([key])=>key.startsWith(prefix))[1]);
const LIT_SPAN={file:'paper/manuscript/chapter.tex',line_start:4,line_end:4,character_start:22,character_end:35,instance:0,text:'\\cite{Author}',source_sha256:'current'};
const LIT_LINKED={key:'doi:10.1234/source',citekey:'Author',metadata:{title:'A meaningful paper',creators:['A. Author'],year:'2024'},source:{provider:'crossref'},bibliography:{state:'ATTACHED',entry_present:true},state:'STALE',claim_id:'claim:law',relation:'supports',rationale:'The argument requires this bounded premise.',reading_status:'partial',evidence_status:'authored-passage',evidence:{locator:'page 4'},manuscript_uses:[LIT_SPAN]};
const LIT_CANON={key:'canonical:law',canonical_source:true,canonical_id:'canonical:law',metadata:{title:'An argument source'},source:{provider:'canonical'},provider:'canonical',source_refs:[],bibliography:{state:'ABSENT',entry_present:false,reason:'No bibliography entry is linked.'}};
const litUses=(rows,pagination)=>{const found=litRead('/references/literature-uses');found.uses=rows;found.pagination={...found.pagination,...pagination};return found;};
const litRoutes=(over={})=>async(path,payload)=>{const route=path.split('?')[0],hit=over[route];if(hit)return copy(await hit(path,payload));
 if(route==='/references/literature-uses')return litUses([]);if(route==='/references/literature-scope')return litRead('/references/literature-scope');if(route==='/references/source')return litRead('/references/source');
 if(route==='/concepts/catalog')return {items:[{id:'claim:law',label:'The proposed law',kind:'result'}],next_offset:200};
 if(route==='/concepts/state')return {focus:{id:'claim:law',kind:'result',summary:'The inspected proposed law'},source_support:{meaning_revision:'sha256:meaning-read'}};
 if(route==='/references/text')return {source_state:'extracted',text:'A bounded controlled passage.',next_offset:12000,reading_receipt:{id:'READ-1',locator:'characters 0–29',source_sha256:'sha256:source'}};
 throw Error('Unexpected route '+route);};
const litMount=(options={},over={})=>async()=>{const {installHTMLDocument}=await import('./helpers/html_dom.mjs'),{mountLiterature}=await loadShared('workspace-literature.mjs');
 const env=installHTMLDocument({width:1280}),host=document.createElement('section'),settle=()=>new Promise(resolve=>setTimeout(resolve,15));document.body.append(host);
 const view=mountLiterature(host,{project:'book',request:litRoutes(over),status(){},onDiscuss(){},onOpenConcept(){},onOpenPassage(){},onInsertCitation(){},...options});await view.ready;await settle();
 const press=async label=>{const node=document.documentElement.querySelectorAll('button').find(b=>b.textContent===label);assert.ok(node,'no button '+label);await node.onclick({preventDefault(){}});await settle();};
 const named=name=>document.documentElement.querySelectorAll('input, textarea, select').find(node=>node.name===name);
 return {host,view,press,named,settle,env,open(){document.documentElement.querySelectorAll('details').forEach(box=>{box.open=true;});}};};
const litState=(options,over,steps=async()=>{})=>async()=>{const m=await litMount(options,over)();await steps(m);m.open();return {host:document.documentElement,restore:()=>{m.view.destroy();m.env.restore();},shell:{notice:()=>''}};};
const litSource={key:'local:73a56c4835d69b195c4ba932',metadata:{title:'Soil moisture and watering intervals'},citekey:'Gardener2024976223',claims:[],rows:[],uses:[]};
const litSourceInfo=()=>({...litRead('/references/source'),available:true,kind:'text',acquisition_state:'AVAILABLE',currentness:'CURRENT',pdf_url:'/files/source.pdf',sources:[{index:0,label:'notes/source.pdf'},{index:1,label:'notes/reading-note.txt'}],fulltext_candidates:[{id:'candidate-1',url:'https://example.org/full-text.pdf'}],publisher_url:'https://example.org/paper'});
const litSearch=(path,payload)=>{const found=/zotero|search\?/.test(path)&&!/discover/.test(path);return found?{items:[{key:'zotero:1',title:'A Zotero item',creators:['Z. Author'],year:2022,url:'https://example.org/zotero-item'}]}:{items:[{title:'New public work',doi:'10.1234/new',creators:['B. Author']},{title:'Soil moisture and watering intervals',doi:'10.1234/held',key:litSource.key,creators:['A. Gardener']}],local_candidates:[{title:'An existing local candidate',authors:['C. Author'],year:2020,doi:'10.1234/local',cand_id:'cand-1',source_record:{}}]};};
const litSearchSteps=zotero=>async m=>{await m.press('Discover sources');if(zotero){const provider=m.named('provider');provider.value='zotero';await provider.onchange();m.settle();}
 const term=m.named('query');term.value='soil';term.oninput?.();const form=term.parent?.parent||null;const searchForm=document.documentElement.querySelectorAll('form').find(f=>f.querySelectorAll('input, textarea, select').some(n=>n.name==='query'));await searchForm.onsubmit({preventDefault(){}});await m.settle();};
const LITERATURE_MOUNTS={
 'library':litState({},{'/references/literature-uses':()=>litUses([...litRead('/references/literature-uses').uses,LIT_LINKED,LIT_CANON],{next_offset:200,next_citation_offset:500})}),
 'claim':litState({target:{claim_id:'claim:law',label:'The proposed law'}},{}),
 'discover':litState({},{'/references/literature-uses':()=>litUses([litRead('/references/literature-uses').uses[0]]),'/references/literature-discover':litSearch},litSearchSteps(false)),
 'zotero':litState({},{'/references/search':litSearch},litSearchSteps(true)),
 'local':litState({},{},async m=>{await m.press('Add local source');}),
 'source':litState({readerOnly:true,reader:{key:litSource.key,title:litSource.metadata.title,source_index:0,mode:'source'}},{'/references/source':litSourceInfo}),
 'source-failed':litState({readerOnly:true,reader:{key:litSource.key,title:litSource.metadata.title,source_index:0,mode:'source'}},{'/references/source':()=>{throw Error('The owner could not read the source.');}}),
 'bind':litState({readerOnly:true,target:{claim_id:'claim:law',label:'The proposed law'}},{},async m=>{await m.view.linkSource(litSource);await m.settle();await m.press('Inspect current claim meaning');}),
 'coverage':litState({},{'/references/literature-scope':path=>{const found=litRead('/references/literature-scope'),offset=Number(new URL(path,'http://local').searchParams.get('offset')||0);found.claims=[{id:'claim:law',label:'The proposed law',qualification:'supported by one linked source',sources:[],own_evidence:[]}];found.pagination={limit:20,offset,next_offset:offset+20,total:60};return found;}},async m=>{await m.press('Inspect project coverage');await m.press('More coverage records');}),
};
for(const [name,mount] of Object.entries(LITERATURE_MOUNTS))HARNESSES['research/literature-'+name]=mount;
// wave 13: every project view that gained a 'panels-open' state is mounted by the real shell with its page opened out
for(const [name,states] of Object.entries(CONTROLS.coverage))if(states['panels-open']&&!HARNESSES[name+'/panels-open'])HARNESSES[name+'/panels-open']=panelsOpen(name,name==='overview'?{routes:homeRoutes}:name==='work'?{query:'work=WORK-a',routes:richWorkRoutes}:name==='history'?{routes:{'/authoring/history':q=>q.get('view')==='telemetry'?(q.get('projection')==='overview'?CAPTURED.history_overview:q.get('projection')?{}:CAPTURED.history_telemetry):CAPTURED.history_activity}}:name==='argument'?{routes:{'/concepts/tree':()=>CAPTURED.concepts_tree,'/concepts/state':()=>CAPTURED.concepts_state,'/concepts/plan':()=>CAPTURED.concepts_plan,'/concepts/history':()=>CAPTURED.concepts_history,'/concepts/catalog':()=>CAPTURED.concepts_catalog,'/corpus/map':()=>CAPTURED.corpus_map}}:name==='material'?{routes:{'/projects/material-references':()=>({references:[copy(REF)],revision:'list-registry',total:1,next_offset:null,owners:{repositories:[]}})}}:{});
test('every declared source-covered view state has a harness, every harness names a declared state, and the actual-only states carry a reason',()=>{
 const sourceStates=[],actualStates=[],focusedStates=[];const stateEvaluators={'workflows/river-run':'tests/workflow_river.test.mjs','workflows/empty':'tests/workflow_operation_frontend.test.mjs','workflows/runs':'tests/workflow_operation_frontend.test.mjs','workflows/guide':'tests/workflow_operation_frontend.test.mjs','workflows/draft-design':'tests/workflow_operation_frontend.test.mjs','workflows/lineage-prepare-offered':'tests/workflow_history_frontend.test.mjs','workflows/history-offered':'tests/workflow_history_frontend.test.mjs','workflows/history-open':'tests/workflow_history_frontend.test.mjs','workflows/history-next-offered':'tests/workflow_history_frontend.test.mjs','workflows/saved-body-partial':'tests/workflow_history_frontend.test.mjs','workflows/saved-body-complete':'tests/workflow_history_frontend.test.mjs','conversation/options-open':'tests/human_workspace_shell.test.mjs','work/trail-offered':'tests/task_trail.test.mjs','work/draft-compared':'tests/work_port.test.mjs','work/result-offered':'tests/human_workspace_shell.test.mjs',...Object.fromEntries(['continuity-continue-offered','continuity-proof-offered','continuity-unresolved','continuity-resend-offered','continuity-review-offered','continuity-read-failed'].map(state=>['work/'+state,'tests/eigen_continuity_frontend.test.mjs'])),'manuscript/source-host':'tests/human_workspace_shell.test.mjs','manuscript/tools-open':'tests/human_workspace_shell.test.mjs','work/list-open':'tests/human_workspace_shell.test.mjs','shell/project-tools-open':'tests/human_workspace_shell.test.mjs','research-workbench/focus-inspection-offered':'tests/research_geometry.test.mjs',...Object.fromEntries(['check-offered','check-result','withdraw-offered','observation-offered','observation-next-offered','river-reads-offered','run-detail-offered','stop-offered','stop-pending','stop-resend-offered'].map(state=>['workflows/'+state,'tests/workflow_operation_frontend.test.mjs']))};const focused={workflows:'tests/workflow_first_use.test.mjs','review-evidence':'tests/workspace_review_evidence.test.mjs','source-inspector':'tests/workspace_source_inspector.test.mjs','historical-obligations':'tests/workspace_source_inspector.test.mjs',backlog:'tests/workspace_backlog.test.mjs'};
 for(const [view,states] of Object.entries(CONTROLS.coverage))for(const [state,cover] of Object.entries(states)){
  assert.ok(CONTROLS.view_states[view]?.[state],view+'/'+state+' is not a declared view state');
  assert.equal(cover.coverage,'source',view+'/'+state+' must be source-mounted (repair2 R4: no actual-only waiver)');const evaluator=stateEvaluators[view+'/'+state]||(view==='shell'&&state==='global-entry'?'tests/first_use_shell.test.mjs':focused[view]);if(evaluator){focusedStates.push(view+'/'+state);assert.ok(cover.harness.includes(evaluator),view+'/'+state+' names its separate focused evaluator');assert.ok(readFileSync(new URL('../'+evaluator,import.meta.url),'utf8').length);}else sourceStates.push(view+'/'+state);
 }
 assert.deepEqual(Object.keys(HARNESSES).sort(),sourceStates.sort(),'harness keys are exactly the source-covered states');
 assert.equal(actualStates.length,0);assert.equal(sourceStates.length+focusedStates.length,Object.values(CONTROLS.view_states).reduce((n,s)=>n+Object.keys(s).length,0),'every declared state is assigned here or to its named focused evaluator');
 for(const row of CONTROLS.controls){assert.ok(row.states.length,row.id+' declares states');for(const state of row.states)assert.ok(CONTROLS.view_states[row.view][state],row.id+' names a declared state');}
});
for(const [key,mount] of Object.entries(HARNESSES)){
 const [view,state]=key.split('/');
 test('source render coverage · '+key,async()=>{
 const direct=key==='material/readers-open',shellHosted=!direct&&(String(CONTROLS.coverage[view][state].harness).startsWith('the real shell')||['manuscript/write','manuscript/source-tex','work/selected','work/next-action-offered','now/page','dependencies/page','projects/page','history/graphs-record','history/graphs-note','conversation/reading-partial','conversation/reading-failed','review/response-partial','review/response-failed','manuscript/frame-toolbar','manuscript/frame-reading','manuscript/frame-bubble','manuscript/frame-save-warning','manuscript/frame-menu','manuscript/frame-find','manuscript/frame-context','manuscript/frame-queue',...['new','routing','routed','lost','unrecorded'].map(m=>'review/comment-'+m),...['new','recorded','lost','found','rejected','edited'].map(m=>'material/literature-'+m),'research/formal-setup',...['library','claim','discover','zotero','local','source','source-failed','bind','coverage'].map(m=>'research/literature-'+m)].includes(key)||view==='research-workbench');
  if(shellHosted){const mounted=await mount();try{const rows=check(view,state,mounted.host);const expected=CONTROLS.controls.filter(row=>row.view===view&&row.states.includes(state)).length;if(expected)assert.ok(rows.length,key+': at least one declared control rendered');
    assert.ok(!/Cannot read|is not a function|undefined/.test(mounted.shell.notice()),key+': the shell raised no fixture error: '+mounted.shell.notice());}finally{mounted.restore();}return;}
  const dom=installDOM();const oldNS=document.createElementNS,oldListener=Node.prototype.addEventListener;Node.prototype.addEventListener=function(name,fn){if(name==='close')this.onclose=fn;};
  Object.defineProperty(Node.prototype,'clientWidth',{configurable:true,get:()=>760});Object.defineProperty(Node.prototype,'clientHeight',{configurable:true,get:()=>420});
  try{const host=await mount();const rows=check(view,state,host);const expected=CONTROLS.controls.filter(row=>row.view===view&&row.states.includes(state)).length;if(expected)assert.ok(rows.length,key+': at least one declared control rendered');}
  finally{delete Node.prototype.clientWidth;delete Node.prototype.clientHeight;Node.prototype.addEventListener=oldListener;if(oldNS)document.createElementNS=oldNS;else delete document.createElementNS;dom.restore();}
 });
}
// ACTUAL-C10-HELP-RESIZE (2026-10-14): help opened wide docks when the viewport narrows and returns, through the
// workspace's own resize handling; the help door stays pressed and the layer is the same node.
test('help opened at 1280 docks at 1000 and returns at 1280 through the workspace resize path',async()=>{
 const s=await mountShell({width:1280});
 try{
  await click(s,'[data-guide]');await s.settle();
  const layer=s.root.querySelector('[data-control="help:layer"]');assert.ok(layer);
  const has=name=>layer.className.split(' ').includes(name);
  assert.ok(!has('is-dock'),'wide open: overlay');
  const resize=width=>{for(const target of [globalThis,window])Object.defineProperty(target,'innerWidth',{value:width,configurable:true,writable:true});window.dispatchEvent({type:'resize'});};
  resize(1000);
  assert.ok(has('is-dock'),'narrowed: docked');assert.equal(s.root.querySelector('[data-control="help:layer"]'),layer,'the same layer');
  const expand=layer.querySelector('.workspace-help-expand');assert.ok(expand&&!expand.hidden);expand.onclick();assert.ok(has('is-expanded'));
  resize(1280);assert.ok(!has('is-dock')&&expand.hidden,'widened: overlay again');
  resize(1000);assert.ok(has('is-dock')&&has('is-expanded'),'narrowed again: the expanded choice is kept');
  assert.equal(document.querySelector('[data-guide]').attrs?.['aria-pressed']??document.querySelector('[data-guide]').getAttribute('aria-pressed'),'true','help is still open');
 }finally{s.restore();}
});
// campaign research visibility (2026-10-14): a source-optional general project with no manuscript reaches its
// Research catalogue through the same capability the owner reports; manuscript-specific doors stay closed.
// Owner answers: tests/fixtures/shell/generate_owner_answers.py (real /projects/metadata and /research/state).
const CAMPAIGN=JSON.parse(readFileSync(new URL('./fixtures/shell/owner-answers.json',import.meta.url),'utf8'));
const asBook=value=>JSON.parse(JSON.stringify(value).replaceAll('"campaign"','"book"'));
const resultRoutes=research=>({'/research/state':()=>asBook(research),'/research/result':()=>asBook(CAMPAIGN.campaign_research_exact)});
const campaignRoutes=research=>({'/projects/metadata':()=>asBook(CAMPAIGN.campaign_metadata),...resultRoutes(research)});
// open the recorded result's complete evidence (the exact owner read), where the card's actions are
// (the shell remembers an opened result across mounts; then it reopens it itself with the same exact read)
const openResult=async s=>{const row=s.root.querySelectorAll('button').find(n=>n.textContent.startsWith('Source audit'));if(row){await row.onclick?.({preventDefault(){},stopPropagation(){},target:row});await s.settle();await s.settle();await s.settle();}
 assert.ok(s.calls.some(c=>c.startsWith('GET /research/result?')),'the exact result is read');assert.ok(s.root.textContent.includes('Sources checked'),'its measurement is shown');};
// the shell's markup DOM double: buttons are found through its own query (the harness findButton reads the other double)
const shellButton=(s,label)=>s.root.querySelectorAll('button').find(n=>n.textContent===label);
const navButton=(s,id)=>s.root.querySelector('.workspace-nav [data-view="'+id+'"]');
for(const [label,research,results] of [['an empty campaign',CAMPAIGN.campaign_research_empty,0],['a campaign with a canonical result',CAMPAIGN.campaign_research_result,1]]){
 test('source-optional navigation: '+label+' shows Research, keeps manuscript-only views closed and offers no claim binding',async()=>{
  const s=await mountShell({routes:campaignRoutes(research)});
  try{
   assert.equal(CAMPAIGN.campaign_metadata.source_optional,true);assert.equal(CAMPAIGN.campaign_metadata.capabilities.research,true,'the owner projection reports Research');
   assert.equal(navButton(s,'research').hidden,false,'Research is in the navigation');
   for(const view of ['manuscript','review','presentation','argument','reader-plan'])assert.equal(navButton(s,view)?.hidden??true,true,view+' stays closed');
   await click(s,'[data-view="material"]');
   const readers=s.root.querySelector('[data-control="material:reader"]');assert.ok(readers.textContent.includes('Research & sources'),'Material lists the Research reader');assert.ok(!readers.textContent.includes('No readers are available'));
   await click(s,'[data-view="research"]');await s.settle();
   assert.ok(s.root.textContent.includes('Establish the evidence'),'the Research view opens');assert.ok(!s.notice().includes('unavailable'),'no unavailable notice: '+s.notice());
   assert.ok(s.calls.includes('GET /research/state?project=book&view=summary'),'the owner catalogue is read');
   if(results){assert.ok(s.root.textContent.includes('Source audit'),'the recorded result is visible');await openResult(s);assert.ok(!shellButton(s,'Connect to a claim'),'no claim binding without concepts');}
   else assert.ok(!s.root.textContent.includes('Source audit'));
  }finally{s.restore();}
 });
}
test('a project with concepts keeps its claim binding on the same owner result and its manuscript-specific views',async()=>{
 const s=await mountShell({routes:resultRoutes(CAMPAIGN.campaign_research_result)});
 try{for(const view of ['research','manuscript','argument','reader-plan','review','presentation'])assert.equal(navButton(s,view).hidden,false,view+' stays open');
  await click(s,'[data-view="research"]');await s.settle();assert.ok(s.root.textContent.includes('Source audit'));await openResult(s);
  assert.ok(shellButton(s,'Connect to a claim'),'unchanged where the project has concepts');}
 finally{s.restore();}
});
test('figure placement refusal names the owner currentness and its one next step, never a retry',async()=>{
 const {figurePlacementRefusal}=await loadShared('workspace-figures.mjs');
 const refused=currentness=>Object.assign(Error('The placement owner refused a stale basis.'),{result:{currentness}});
 assert.equal(figurePlacementRefusal(Error('Plain failure.')),'Plain failure.');   // no currentness: the owner message unchanged
 assert.match(figurePlacementRefusal(refused({drawing_freshness:'STALE',evidence_binding_status:'STALE'})),/Drawing stale, evidence stale\. Render the figure again and bind its current result, then place it\.$/);
 assert.match(figurePlacementRefusal(refused({status:'STALE',evidence_binding_status:'THEORY_ONLY'})),/Drawing stale, evidence theory only\. Render the figure again, then place it\.$/);
 assert.match(figurePlacementRefusal(refused({drawing_freshness:'CURRENT',evidence_binding_status:'UNBOUND'})),/Drawing current, evidence unbound\. Bind the figure to its current research result, then place it\.$/);
 assert.match(figurePlacementRefusal(refused({drawing_freshness:'CURRENT',evidence_binding_status:'CURRENT'})),/Inspect the figure before placing it\.$/);
 assert.match(figurePlacementRefusal(refused({})),/^The placement owner refused a stale basis\. Drawing not reported, evidence not reported\. /);
 // C3: an unreported or UNKNOWN fact asks for the owner's current status, never a re-render or rebind on a guess;
 // a REPORTED stale or unbound fact keeps its specific repair beside it
 for(const facts of [{},{drawing_freshness:'UNKNOWN',evidence_binding_status:'UNKNOWN'}]){const text=figurePlacementRefusal(refused(facts));
  assert.match(text,/did not report the drawing freshness or evidence binding; inspect the figure's current status before changing it\.$/);assert.doesNotMatch(text,/Render the figure again|Bind the figure/);}
 const staleUnknown=figurePlacementRefusal(refused({drawing_freshness:'STALE'}));
 assert.match(staleUnknown,/Render the figure again\. The placement owner did not report the evidence binding; inspect the figure's current status before changing it, then place it\.$/);assert.doesNotMatch(staleUnknown,/Bind the figure/);
 const unknownUnbound=figurePlacementRefusal(refused({evidence_binding_status:'UNBOUND'}));
 assert.match(unknownUnbound,/Bind the figure to its current research result\. The placement owner did not report the drawing freshness; inspect the figure's current status before changing it, then place it\.$/);assert.doesNotMatch(unknownUnbound,/Render the figure again/);
 const currentUnknown=figurePlacementRefusal(refused({drawing_freshness:'CURRENT'}));
 assert.match(currentUnknown,/did not report the evidence binding; inspect the figure's current status before changing it\.$/);assert.doesNotMatch(currentUnknown,/Render the figure again|Bind the figure/);
});
test('dispatch card: synthesis attach is guidance only; a permitted POST is never sent, an unpermitted one shows its reason, read-only shows none',async()=>{
 const {mountOperatorWork}=await import('../src/laplace/web/static_shared/workspace-work.mjs');
 const post={method:'POST',url:'/work/transition'},attachLabel='Read how to attach the synthesis';
 const cases=[
  {attach:{permitted:true,operation:'task_status',http:post},readOnly:false,text:/does not send that form\. Attach it from the original parent session\./,link:false},
  {attach:{permitted:false,reason:'The synthesis return is not current.',http:post},readOnly:false,text:/The synthesis return is not current\./,link:false},
  {attach:{permitted:true,http:{method:'GET',url:'/work/state?project=fixture&view=detail&id=A'}},readOnly:false,text:null,link:true},
  {attach:{permitted:true,operation:'task_status',http:post},readOnly:true,text:null,link:false},
 ];
 for(const item of cases){
  // the same local DOM double and prototype shims the direct-mount coverage harness installs (installDOM + restore)
  const dom=installDOM(),oldListener=Node.prototype.addEventListener;Node.prototype.addEventListener=function(name,fn){if(name==='close')this.onclose=fn;};
  Object.defineProperty(Node.prototype,'clientWidth',{configurable:true,get:()=>760});Object.defineProperty(Node.prototype,'clientHeight',{configurable:true,get:()=>420});
  try{
  const calls=[],host=new Node('main');dom.body.append(host);
  const detail=workDetail('A');detail.task.dispatch={execution_state:'SETTLED',review_state:'ACCEPTED',
   parent_synthesis:{title:'Synthesis',status:'AWAITING_SYNTHESIS',authored:false,execution_location:'original-parent',attach_action:item.attach}};
  const controller=await mountOperatorWork(host,{project:'fixture',summary:{tasks:[{id:'A',title:'Title of A',status:'blocked'}]},initialWork:'A',readOnly:item.readOnly,
   request:async(path,body)=>{calls.push([String(path),body]);return detail;}});
  for(let i=0;i<10;i++)await new Promise(resolve=>setImmediate(resolve));
  const card=host.querySelector('.work-dispatch');assert.ok(card,'the dispatch card renders');
  assert.match(card.textContent,/Parent synthesis .Synthesis.: awaiting synthesis · not authored yet\. It is written in the original parent session; it is not a review or acceptance\./);
  if(item.text)assert.match(card.textContent,item.text);
  else assert.ok(!/does not send that form|not offered now|not current/.test(card.textContent),'no attach guidance where none applies');
  assert.equal([...card.querySelectorAll('button')].some(node=>node.textContent===attachLabel),item.link,'only a permitted GET attach is a read link');
  assert.ok(calls.every(([,body])=>body===undefined),'no attach or transition POST was sent: '+JSON.stringify(calls));
  controller?.destroy?.();
  }finally{delete Node.prototype.clientWidth;delete Node.prototype.clientHeight;Node.prototype.addEventListener=oldListener;dom.restore();}
 }
});

// closure contract 2026-11-02: the primary writing panel's Review responses reach the SHELL's canonical project Review
// controller through the validated bridge. Two same-origin window objects stand where the iframe and its shell stand;
// only postMessage delivery is simulated. The controller is the real createProjectReview with its exact read-handle
// guard; its onReviewProposal records the hand-off to workspace-proposals mountProposalReview (mounted by its own suites).
// Not a browser, iframe, focus or real draft-conflict proof.
test('primary writing panel decisions cross the validated bridge to the canonical project Review controller; inspect stays inspect',async()=>{
 const bridge=await import(new URL('workspace-bridge.mjs',shared).href);
 const {createProjectReview}=await import(new URL('workspace-review.mjs',shared).href);
 const origin='http://localhost',version='sha256:'+'1'.repeat(64);
 const readHandle={http:{method:'GET',url:'/authoring/proposal-preview?project=p&id=WT-producer&proposal_version='+version+'&view=summary'}};
 const listeners={shell:new Set(),frame:new Set()},deliver=(set,event)=>queueMicrotask(()=>{for(const listener of [...set])listener(event);});
 const shell={addEventListener:(_type,fn)=>listeners.shell.add(fn),removeEventListener:(_type,fn)=>listeners.shell.delete(fn)};
 const frame={parent:shell,addEventListener:(_type,fn)=>listeners.frame.add(fn),removeEventListener:(_type,fn)=>listeners.frame.delete(fn)};
 shell.postMessage=(data,target)=>{assert.equal(target,origin);deliver(listeners.shell,{origin,source:frame,data:structuredClone(data)});};
 frame.postMessage=(data,target)=>{assert.equal(target,origin);deliver(listeners.frame,{origin,source:shell,data:structuredClone(data)});};
 const opened=[];let refuse=null;
 const controller=createProjectReview({project:'p',request:async()=>({}),events:null,document:null,onReviewProposal:async(turnId,choice)=>{opened.push({turnId,choice:structuredClone(choice)});if(refuse)throw Error(refuse);
  return {opened:true,decision:true,state:'DECISION',project:'p',turn_id:turnId,proposal_version:choice.proposalVersion};}});
 const handlers=Object.fromEntries(bridge.BRIDGE_ROUTES.map(route=>[route.handler,()=>{}]));
 handlers.reviewProposal=bridge.createProposalDecisionHandler({project:'p',projectReview:controller,origin:()=>origin});
 const ledger=bridge.createBridgeLedger();
 const installed=bridge.installWalkBridge({target:shell,origin:()=>origin,sourceWindow:()=>frame,ledger,handlers});
 const inspected=[];
 const panel=(project='p',timeoutMs=500)=>bridge.panelProposalReview({project,inspect:async(id,choice)=>{inspected.push({id,choice});},
  decide:args=>bridge.requestProposalDecision({...args,frame,origin:()=>origin,timeoutMs})});
 const decide={proposalVersion:version,readHandle,readOnly:false,decision:true};
 try{
  // the historical saved-comparison card opens with readOnly false but no decision capability: it only inspects
  await panel()('WT-producer',{proposalVersion:version,readHandle,readOnly:false});
  assert.equal(inspected.length,1);assert.equal(opened.length,0);
  // an explicit decision reaches the canonical controller with the exact project/turn/version/read identity
  await panel()('WT-producer',decide);
  assert.deepEqual(opened,[{turnId:'WT-producer',choice:decide}]);
  assert.deepEqual(controller.snapshot().selection,{turnId:'WT-producer',proposalVersion:version,readHandle,readOnly:false});
  // a canonical refusal (draft or permission) returns to the caller as that refusal
  refuse='Unsaved manuscript changes would be replaced; save or discard them first.';
  await assert.rejects(()=>panel()('WT-producer',decide),/Unsaved manuscript changes/);refuse=null;
  const count=opened.length;
  // a stale version, a foreign read handle and a foreign project never reach a decision view
  await assert.rejects(()=>panel()('WT-producer',{...decide,proposalVersion:'sha256:'+'9'.repeat(64)}),/changed the selected turn, version or edit/);
  await assert.rejects(()=>panel()('WT-producer',{...decide,readHandle:{http:{method:'GET',url:'/authoring/proposal-preview?project=other&id=WT-producer&proposal_version='+version}}}),/does not match this project/);
  await assert.rejects(()=>panel('other')('WT-producer',decide),/another project/);
  assert.equal(opened.length,count);
  // a message from any window other than the current manuscript frame is fenced out and counted
  deliver(listeners.shell,{origin,source:{},data:{type:'laplace:review-proposal',project:'p',turn_id:'WT-producer',proposal_version:version,read_handle:readHandle,request_id:'review-foreign-1'}});
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.equal(ledger.ledger.rejected,1);assert.equal(opened.length,count);
  // a frame outside the workspace refuses at once; a late request after the shell left says nothing was decided
  await assert.rejects(()=>bridge.requestProposalDecision({project:'p',turnId:'WT-producer',proposalVersion:version,readHandle,frame:{parent:undefined},origin:()=>origin}),/inside the Writing workspace/);
  installed.uninstall();
  await assert.rejects(()=>panel('p',50)('WT-producer',decide),/did not answer/);
  assert.equal(opened.length,count);
 }finally{installed.uninstall();}
});

// closure contract 2026-11-02, inspector destination correction (request system-closure-inspector-destination-20261102-01).
// The ACTUAL Work view (mountWorkView -> renderWork -> mountOperatorWork) and the ACTUAL existing-comment receipt
// (openFeedbackComment -> its own Review responses -> panel capability -> validated bridge) reach the REAL
// createProjectReview and REAL mountProposalReview through the real shared inspector on the faithful HTML document helper,
// with the operator-captured public owner DTOs (tests/fixtures/system_closure/actual-owner-decision.json, read-only).
// Transport stands at fetch and a walk object stands for the manuscript editor; a browser, iframe focus, real draft
// computation and the compiler are later checks.
test('actual Work view and existing comment reach the canonical decision; success exits the inspector trail and Back keeps its meaning',async()=>{
 const {installHTMLDocument}=await import('./helpers/html_dom.mjs');
 const inspectorModule=await import(new URL('workspace-inspector.mjs',shared).href);
 inspectorModule.resetSharedInspector();
 const env=installHTMLDocument(),realFetch=globalThis.fetch;let work=null,controller=null,installed=null;
 try{
  const {mountWorkView}=await import(new URL('workspace-work-view.mjs',shared).href);
  const {createProjectReview}=await import(new URL('workspace-review.mjs',shared).href);
  const {mountProposalReview}=await import(new URL('workspace-proposals.mjs',shared).href);
  const {openFeedbackComment}=await import(new URL('feedback-route.mjs',shared).href);
  const bridge=await import(new URL('workspace-bridge.mjs',shared).href);
  const v=JSON.parse(readFileSync(new URL('./fixtures/system_closure/actual-owner-decision.json',import.meta.url),'utf8'));
  const copy=x=>structuredClone(x),posts=[],shown=[],notices=[];
  env.location.href='http://local/project?workspace=writing&corpus=p&work=review-claim';
  const summary=v.work_owner_reads.work_summary.body,detail=v.work_owner_reads.work_detail.body;
  const route=Object.values(v.work_owner_reads).find(r=>r.body?.schema_version==='laplace.feedback-route/1').body;
  let state=copy(summary),mode='work',gen=1,available=false,conflict=false;
  const response=value=>({ok:true,status:200,headers:{get:()=>'application/json'},json:async()=>copy(value),text:async()=>JSON.stringify(value)});
  // transport stand-in: serves the captured owner DTOs unchanged; an unrecorded read fails the test
  globalThis.fetch=async(path,init={})=>{
   const u=new URL(path,'http://local');
   if(init.method==='POST'){const body=JSON.parse(init.body);posts.push({url:u.pathname,body});
    return response({...v.preview,edits:v.preview.edits.map(e=>({...e,status:body.edit_id===e.edit_id?'rejected':e.status}))});}
   if(u.pathname==='/work/state')return response(u.searchParams.get('view')==='detail'?detail:u.searchParams.get('view')==='namespaces'?v.work_owner_reads.namespaces?.body:summary);
   if(u.pathname==='/work/delivery')return response(route);
   if(u.pathname==='/authoring/proposal-preview'){const edit=u.searchParams.get('edit_id'),view=u.searchParams.get('view');
    const selected=v.selected_children.find(c=>{const q=new URL(c.handle.url,'http://local').searchParams;return q.get('edit_id')===edit&&q.get('view')===view;});
    return response(selected?.body||v.preview);}
   if(u.pathname==='/authoring/proposals')return response({project:'p',view:'queue',proposals:[],as_of:v.version});
   if(u.pathname==='/authoring/help')return response({});
   throw Error('UNRECORDED_OWNER_READ '+u.pathname+'?'+u.searchParams);};
  const root=document.createElement('main');document.body.append(root);
  for(const attr of ['data-clear-task','data-work-scope']){const n=document.createElement('span');n.setAttribute(attr,'');root.append(n);}
  const host=document.createElement('section');root.append(host);
  const button=(text,fn)=>{const n=document.createElement('button');n.textContent=text;n.onclick=fn;return n;};
  const views={current:()=>mode,generation:()=>gen,show:async next=>{mode=next;gen++;return true;}};
  const walk={showProposal:(data,options)=>shown.push({data,options}),proposalDraftConflict:()=>conflict,editState:()=>({}),refresh:async()=>{},clearProposal(){}};
  const frame={walk},manuscript={ready:async()=>{if(!available)return null;mode='manuscript';gen++;return walk;},sourceWindow:()=>frame,saved(){},editor:()=>null,rememberApplication:async()=>{}};
  const proposals=mountProposalReview('p',{views,ui:{$:s=>root.querySelector(s),notice:(text,error)=>notices.push({text,error})},manuscript,
   projectReview:{open:(...args)=>controller.open(...args),settled:async()=>null},inspect:{ownerRead:async()=>{},projectArtifact:async()=>{}},discussion:{open(){},savedTurn(){},talk(){}},workState:{reload:async()=>{}}});
  controller=createProjectReview({project:'p',request:async()=>({}),events:null,document:null,onReviewProposal:(...args)=>proposals.review(...args)});
  const settle=async()=>{for(let n=0;n<12;n++)await new Promise(r=>setTimeout(r,0));};
  const inspector=inspectorModule.sharedInspector();
  const openComments=()=>[...document.querySelectorAll('dialog[open]')].filter(n=>n.getAttribute('aria-label')==='Passage comment and reviews');
  const decideIn=dialog=>dialog.querySelector('[data-revision-decide="'+v.version+'"]');
  // 1. ACTUAL WORK ENTRY: the shell's Work discussion carries projectReview and workspace-work-view forwards it
  work=mountWorkView('p',{enc:encodeURIComponent,initialQuery:new URLSearchParams('work=review-claim'),views,
   forms:{setDirty(){},wire(){},changed:async()=>{},guard:async()=>true},ui:{root,$:s=>root.querySelector(s),notice:(text,error)=>notices.push({text,error}),button,actionAlert:(node,text)=>{node.textContent=text;}},
   workState:{get:()=>state,set:value=>{state=value;},summaryRead:'/work/state?project=p&view=summary'},
   inspect:{ownerRead:async()=>{},projectArtifact:async()=>{},savedMarkdown:async()=>{}},
   discussion:{projectReview:controller,session:()=>({scope(){},pinMessageTarget(){}}),open(){},conversation(){},savedTurn(){},talk(){}},
   activity:{openOwner(){}},place:{remember(){}},context:()=>({})});
  await work.admit('review-claim');await work.render(host);await settle();
  const workButton=[...host.querySelectorAll('button')].find(n=>n.textContent==='Review responses');assert.ok(workButton,'the mounted Work view owns its Review responses');
  await workButton.click();await settle();
  const workDialog=[...document.querySelectorAll('[data-guide-panel="responses"]')].at(-1);assert.ok(workDialog,'the Work button opened the actual responses');
  assert.ok(decideIn(workDialog),'the decision control names the owner version');
  await decideIn(workDialog).click();await settle();
  assert.equal(shown.length,0);assert.equal(posts.length,0);assert.ok(workDialog.isConnected,'a no-show keeps the initiating dialog');
  available=true;await decideIn(workDialog).click();await settle();
  assert.equal(shown.length,1);const opened=shown[0];
  assert.equal(opened.data.project,'p');assert.equal(opened.data.turn_id,v.turn_id);assert.equal(opened.data.proposal_version,v.version);
  assert.equal(opened.options.readOnly,false);assert.equal(typeof opened.options.onDecision,'function');
  assert.equal(posts.length,0,'opening is neither a decision nor an application');
  assert.equal(workDialog.isConnected,false,'the initiating responses dialog is released after the actual opening');
  assert.equal(inspector.current,null);assert.equal(inspector.trail.length,0);
  const edit=opened.data.edits[0],displayed=Object.values(opened.data.identities||{});
  assert.ok(edit.allowed_actions.includes('accept')&&edit.allowed_actions.includes('reject')&&!edit.allowed_actions.includes('withdraw'),'owner-issued actions');
  conflict=true;await assert.rejects(()=>opened.options.onDecision(edit.edit_id,'accept'),/Your unsaved manuscript text overlaps this edit/);conflict=false;
  await assert.rejects(()=>opened.options.onDecision(edit.edit_id,'withdraw'),/unavailable for the current source and basis/);
  assert.equal(posts.length,0,'draft and unissued refusals send nothing');
  await opened.options.onDecision(edit.edit_id,'reject');
  assert.deepEqual(posts,[{url:'/authoring/proposal-decision',body:{project:'p',turn_id:v.turn_id,edit_id:edit.edit_id,decision:'reject',...(displayed.length?{expected:displayed}:{})}}]);
  // 2. CONTROLLER GUARDS: a stale version or foreign read opens nothing; a read-only open inspects without a decision
  const readHandle=v.preview.read_handle,shownBeforeGuards=shown.length;
  await assert.rejects(()=>controller.open(v.turn_id,{proposalVersion:'sha256:'+'9'.repeat(64),readHandle,readOnly:false,decision:true}),/changed the selected turn, version or edit/);
  await assert.rejects(()=>controller.open(v.turn_id,{proposalVersion:v.version,readHandle:{...readHandle,http:{...readHandle.http,url:readHandle.http.url.replace('project=p','project=other')}},readOnly:false,decision:true}),/does not match this project/);
  assert.equal(shown.length,shownBeforeGuards);
  const inspected=await controller.open(v.turn_id,{proposalVersion:v.version,readHandle,readOnly:true});
  assert.equal(inspected?.opened,true);assert.equal(inspected.decision,false);assert.equal(shown.at(-1).options.readOnly,true);assert.equal(shown.at(-1).options.onDecision,undefined);
  assert.equal(posts.length,1,'guards and inspection post nothing');
  // 3. ACTUAL EXISTING COMMENT RECEIPT through the panel capability and the validated bridge to the SAME controller
  mode='work';available=false;
  const listeners={shell:new Set(),frame:new Set()},deliver=(set,event)=>queueMicrotask(()=>{for(const fn of [...set])fn(event);});
  const shellWin={addEventListener:(_t,fn)=>listeners.shell.add(fn),removeEventListener:(_t,fn)=>listeners.shell.delete(fn)};
  frame.parent=shellWin;frame.addEventListener=(_t,fn)=>listeners.frame.add(fn);frame.removeEventListener=(_t,fn)=>listeners.frame.delete(fn);
  shellWin.postMessage=data=>deliver(listeners.shell,{origin:'http://local',source:frame,data:structuredClone(data)});
  frame.postMessage=data=>deliver(listeners.frame,{origin:'http://local',source:shellWin,data:structuredClone(data)});
  const handlers=Object.fromEntries(bridge.BRIDGE_ROUTES.map(r=>[r.handler,()=>{}]));handlers.reviewProposal=bridge.createProposalDecisionHandler({project:'p',projectReview:controller,origin:()=>'http://local'});
  installed=bridge.installWalkBridge({target:shellWin,origin:()=>'http://local',sourceWindow:()=>frame,ledger:bridge.createBridgeLedger(),handlers});
  const openProposal=bridge.panelProposalReview({project:'p',inspect:async()=>{throw Error('A decision must not fall back to inspection');},decide:args=>bridge.requestProposalDecision({...args,frame,origin:()=>'http://local',timeoutMs:500})});
  // the recorded route's own canonical origin (origin_ref, correction, source_basis, currentness, read), joined only to the
  // same route's Work id and read handle; the pinned fixture holds no separate correction-origin response
  const original=route.origin;
  assert.ok(original?.origin_ref&&original.correction?.anchor&&original.read,'the recorded route carries its canonical comment origin');
  assert.equal(original.origin_ref.project,'p');
  const existingOrigin={...copy(original),project:'p',review_route_spec:{work_id:route.work.id},review_route_read:copy(route.read)};
  const request=async path=>{const u=new URL(path,'http://local');if(u.pathname==='/work/delivery')return copy(route);if(u.pathname==='/authoring/correction-origin')return copy(original);if(u.pathname==='/authoring/proposal-preview')return copy(v.preview);throw Error('UNRECORDED_COMMENT_READ '+path);};
  const comment=await openFeedbackComment({project:'p',selection:{anchor:copy(original.correction.anchor)},existingOrigin,request,openProposal});await settle();
  const openResponses=async from=>{const control=[...from.querySelectorAll('button')].find(n=>n.textContent==='Review responses');assert.ok(control,'the comment receipt owns its Review responses');
   await control.click();await settle();return [...document.querySelectorAll('[data-guide-panel="responses"]')].at(-1);};
  const firstResponses=await openResponses(comment);assert.ok(firstResponses&&decideIn(firstResponses));
  const shownBefore=shown.length,postsBefore=posts.length;
  await decideIn(firstResponses).click();await settle();
  assert.equal(shown.length,shownBefore);assert.equal(posts.length,postsBefore);assert.ok(firstResponses.isConnected,'a no-show keeps the responses inspection');
  assert.ok([...firstResponses.querySelectorAll('button')].some(n=>n.textContent==='Back to Passage comment'),'the refusal keeps the inspector Back control');
  // ordinary Close on the nested responses keeps its existing Back meaning: the parked comment reopens
  [...firstResponses.querySelectorAll('button')].find(n=>n.textContent==='Close review responses').click();await settle();
  assert.equal(firstResponses.isConnected,false);const reopened=openComments();assert.equal(reopened.length,1,'Close on a nested inspection returns to the passage comment');
  // the reopened comment (its reopen descriptor carries the same capability) now decides
  const secondResponses=await openResponses(reopened[0]);assert.ok(secondResponses&&decideIn(secondResponses));
  available=true;await decideIn(secondResponses).click();await settle();
  assert.equal(shown.length,shownBefore+1);assert.equal(shown.at(-1).data.proposal_version,v.version);assert.equal(shown.at(-1).options.readOnly,false);assert.equal(typeof shown.at(-1).options.onDecision,'function');
  assert.equal(posts.length,postsBefore,'opening from the comment posts nothing');
  assert.equal(secondResponses.isConnected,false);
  assert.equal(openComments().length,0,'successful decision must not reopen a comment modal over the decision');
  assert.equal(inspector.current,null);assert.equal(inspector.trail.length,0,'the explicit destination exit clears the inspector trail');
 }finally{installed?.uninstall();work?.release();controller?.destroy();env.restore();inspectorModule.resetSharedInspector();globalThis.fetch=realFetch;}
});

// F4/F5 (Root adjudication of the external HOLD). The FRESH Save branch of the actual comment editor, opened with the PRIMARY
// caller's selection shape (writing-panel commentFrom: {anchor, prepare: commentBasis}), against ONE coherent public owner run
// (tests/fixtures/system_closure/coherent-owner-review-corrections.json, read-only): its exact prepare/save requests and
// responses; then that SAME saved comment's actual /authoring/correction-origin read and recorded review route reach the
// canonical decision through the panel capability and validated bridge, and success exits the inspector trail. Draft
// storage restores the run's retained request identity (client state only); no owner field is rewritten or minted. The
// writing-panel iframe menu itself, browser focus and draft computation remain later real-browser checks.
test('fresh comment Save with the primary caller selection and the same run actual correction origin reach the canonical decision',async()=>{
 const {installHTMLDocument}=await import('./helpers/html_dom.mjs');
 const inspectorModule=await import(new URL('workspace-inspector.mjs',shared).href);
 inspectorModule.resetSharedInspector();
 const env=installHTMLDocument(),realFetch=globalThis.fetch,realSession=globalThis.sessionStorage;let controller=null,installed=null;
 try{
  const {createProjectReview}=await import(new URL('workspace-review.mjs',shared).href);
  const {mountProposalReview}=await import(new URL('workspace-proposals.mjs',shared).href);
  const {openFeedbackComment}=await import(new URL('feedback-route.mjs',shared).href);
  const bridge=await import(new URL('workspace-bridge.mjs',shared).href);
  const f=JSON.parse(readFileSync(new URL('./fixtures/system_closure/coherent-owner-review-corrections.json',import.meta.url),'utf8'));
  const copy=x=>structuredClone(x),fresh=f.fresh_comment_owner,origin=f.work_owner_reads.correction_origin;
  const route=Object.values(f.work_owner_reads).find(r=>r.body?.schema_version==='laplace.feedback-route/1').body;
  // ONE run: the saved comment, its correction-origin read and the recorded review route name the same origin
  assert.deepEqual(fresh.save_response.origin_ref,origin.body.origin_ref);assert.deepEqual(route.origin.origin_ref,origin.body.origin_ref);
  assert.equal(fresh.save_response.request_id,fresh.save_request.request_id);
  const stored=new Map();globalThis.sessionStorage={getItem:k=>stored.get(k)??null,setItem:(k,value)=>stored.set(k,String(value)),removeItem:k=>stored.delete(k)};
  const selection={anchor:copy(fresh.prepare_request.anchor),prepare:copy(fresh.prepare_request)};   // writing-panel commentFrom's exact shape
  stored.set('laplace:feedback-route:'+JSON.stringify(['p','passage-comment']),JSON.stringify({schema_version:'laplace.feedback-route-draft/1',project:'p',key:'passage-comment',
   state:{text:fresh.save_request.text,selection:copy(selection),request_id:fresh.save_request.request_id}}));
  const posts=[],shown=[],saved=[],owner=[];
  const response=value=>({ok:true,status:200,headers:{get:()=>'application/json'},json:async()=>copy(value),text:async()=>JSON.stringify(value)});
  globalThis.fetch=async(path,init={})=>{const u=new URL(path,'http://local');
   if(init.method==='POST'){posts.push({url:u.pathname,body:JSON.parse(init.body)});return response(f.preview);}
   if(u.pathname==='/authoring/proposal-preview'){const edit=u.searchParams.get('edit_id'),view=u.searchParams.get('view');
    const selected=f.selected_children.find(c=>{const q=new URL(c.handle.url,'http://local').searchParams;return q.get('edit_id')===edit&&q.get('view')===view;});return response(selected?.body||f.preview);}
   if(u.pathname==='/authoring/proposals')return response({project:'p',view:'queue',proposals:[],as_of:f.version});
   throw Error('UNRECORDED_OWNER_READ '+u.pathname+'?'+u.searchParams);};
  const root=document.createElement('main');document.body.append(root);let mode='manuscript',gen=1;
  const views={current:()=>mode,generation:()=>gen,show:async next=>{mode=next;gen++;return true;}};
  const walk={showProposal:(data,options)=>shown.push({data,options}),proposalDraftConflict:()=>false,editState:()=>({}),refresh:async()=>{},clearProposal(){}};
  const frame={walk},manuscript={ready:async()=>walk,sourceWindow:()=>frame,saved(){},editor:()=>null,rememberApplication:async()=>{}};
  const proposals=mountProposalReview('p',{views,ui:{$:s=>root.querySelector(s),notice(){}},manuscript,projectReview:{open:(...args)=>controller.open(...args),settled:async()=>null},
   inspect:{ownerRead:async()=>{},projectArtifact:async()=>{}},discussion:{open(){},savedTurn(){},talk(){}},workState:{reload:async()=>{}}});
  controller=createProjectReview({project:'p',request:async()=>({}),events:null,document:null,onReviewProposal:(...args)=>proposals.review(...args)});
  const listeners={shell:new Set(),frame:new Set()},deliver=(set,event)=>queueMicrotask(()=>{for(const fn of [...set])fn(event);});
  const shellWin={addEventListener:(_t,fn)=>listeners.shell.add(fn),removeEventListener:(_t,fn)=>listeners.shell.delete(fn)};
  frame.parent=shellWin;frame.addEventListener=(_t,fn)=>listeners.frame.add(fn);frame.removeEventListener=(_t,fn)=>listeners.frame.delete(fn);
  shellWin.postMessage=data=>deliver(listeners.shell,{origin:'http://local',source:frame,data:structuredClone(data)});
  frame.postMessage=data=>deliver(listeners.frame,{origin:'http://local',source:shellWin,data:structuredClone(data)});
  const handlers=Object.fromEntries(bridge.BRIDGE_ROUTES.map(r=>[r.handler,()=>{}]));handlers.reviewProposal=bridge.createProposalDecisionHandler({project:'p',projectReview:controller,origin:()=>'http://local'});
  installed=bridge.installWalkBridge({target:shellWin,origin:()=>'http://local',sourceWindow:()=>frame,ledger:bridge.createBridgeLedger(),handlers});
  const openProposal=bridge.panelProposalReview({project:'p',inspect:async()=>{throw Error('A decision must not fall back to inspection');},decide:args=>bridge.requestProposalDecision({...args,frame,origin:()=>'http://local',timeoutMs:500})});
  const settle=async()=>{for(let n=0;n<12;n++)await new Promise(r=>setTimeout(r,0));};
  const inspector=inspectorModule.sharedInspector();
  const request=async(path,body)=>{const u=new URL(path,'http://local');owner.push({path:u.pathname,body:body===undefined?undefined:copy(body)});
   if(u.pathname==='/authoring/correction-prepare')return copy(fresh.prepare_response);
   if(u.pathname==='/authoring/correction')return copy(fresh.save_response);
   if(u.pathname==='/authoring/correction-origin'){assert.deepEqual(JSON.parse(u.searchParams.get('origin_ref')),origin.body.origin_ref,'only the recorded origin is read');return copy(origin.body);}
   if(u.pathname==='/work/delivery')return copy(route);
   if(u.pathname==='/authoring/proposal-preview')return copy(f.preview);
   throw Error('UNRECORDED_COMMENT_READ '+path);};
  // 1. FRESH SAVE: the actual editor inspects the selected passage, then Save sends the run's exact save request once
  const editor=await openFeedbackComment({project:'p',selection:copy(selection),request,openProposal,onSaved:receipt=>saved.push(receipt)});await settle();
  assert.deepEqual(owner[0],{path:'/authoring/correction-prepare',body:{project:'p',...copy(fresh.prepare_request),request_id:fresh.save_request.request_id}});
  const saveButton=[...editor.querySelectorAll('button')].find(n=>n.textContent==='Save comment');assert.ok(saveButton,'the fresh editor offers Save comment');
  await saveButton.click();await settle();
  const saves=owner.filter(row=>row.path==='/authoring/correction');assert.equal(saves.length,1,'one Save request');assert.deepEqual(saves[0].body,fresh.save_request,'the exact recorded save request');
  assert.equal(saved.length,1);assert.deepEqual(saved[0].origin_ref,fresh.save_response.origin_ref);
  assert.ok([...editor.querySelectorAll('h3')].some(n=>n.textContent==='Saved comment'));
  // this run saved without a review route, so the fresh receipt honestly offers no Review responses of its own
  assert.equal([...editor.querySelectorAll('button')].some(n=>n.textContent==='Review responses'),false);
  assert.equal(posts.length,0,'saving a comment is not a decision');
  editor.close();await settle();
  // 2. THE SAME SAVED COMMENT through its actual recorded correction-origin read (F5: no assembled origin), joined only to
  // the same run's review route Work id and read, reaches the canonical decision
  const actual=await request(origin.http.url);
  const existingOrigin={...copy(actual),project:'p',review_route_spec:{work_id:route.work.id},review_route_read:copy(route.read)};
  const comment=await openFeedbackComment({project:'p',selection:{anchor:copy(actual.correction.anchor)},existingOrigin,request,openProposal});await settle();
  const control=[...comment.querySelectorAll('button')].find(n=>n.textContent==='Review responses');assert.ok(control,'the saved comment owns its Review responses');
  await control.click();await settle();
  const responses=[...document.querySelectorAll('[data-guide-panel="responses"]')].at(-1),decide=responses?.querySelector('[data-revision-decide="'+f.version+'"]');
  assert.ok(decide,'the decision control names the same run owner version');
  await decide.click();await settle();
  assert.equal(shown.length,1);assert.equal(shown[0].data.proposal_version,f.version);assert.equal(shown[0].data.turn_id,f.turn_id);
  assert.equal(shown[0].options.readOnly,false);assert.equal(typeof shown[0].options.onDecision,'function');
  assert.equal(posts.length,0,'opening the decision posts nothing');
  assert.equal([...document.querySelectorAll('dialog[open]')].filter(n=>n.getAttribute('aria-label')==='Passage comment and reviews').length,0,'no comment modal over the decision');
  assert.equal(inspector.current,null);assert.equal(inspector.trail.length,0);
 }finally{installed?.uninstall();controller?.destroy();env.restore();inspectorModule.resetSharedInspector();globalThis.fetch=realFetch;globalThis.sessionStorage=realSession;}
});

// The comment reader's own mapping glue: walk-selection reads offsets from an actual paragraph DOM with the same
// chrome-skipping reader as every gesture, then the shared mapper names the exact raw target. Rendered spans and
// source offsets are those the renderer records for this paragraph (math drawn as a non-KaTeX stand-in here).
test('comment reader selection maps one actual paragraph DOM range through walk-selection and the shared mapper',async()=>{
 const {installHTMLDocument}=await import('./helpers/html_dom.mjs');
 const env=installHTMLDocument();
 try{
  const {commentTargetOf}=await import(new URL('walk-selection.mjs',shared).href);
  const line='The file \\texttt{observations.csv} contains $(x,y)$ only.';
  const parts=[['text','The file ',0,9],['code','observations.csv',9,34],['text',' contains ',34,44],['math','(x,y)',44,51],['text',' only.',51,57]];
  const text=(s)=>{const n=document.createTextNode(s);n.nodeValue=s;return n;};
  const body=document.createElement('p'),other=document.createElement('p');other.append(text('Another paragraph.'));
  let at=0;const pieceMap=parts.map(([t,shown,oStart,oEnd])=>{const span=document.createElement('span');span.append(text(shown));body.append(span);
   const row={t,oStart,oEnd,rStart:at,rEnd:at+shown.length,rText:shown,nodes:[span]};at+=shown.length;return row;});
  document.body.append(body,other);
  const block={id:'b-comment',tex:line,pieceMap,bodyEl:body};
  const whole=commentTargetOf(block);
  assert.equal(whole.selection.kind,'whole-block');assert.equal(whole.selection.end,line.length);
  assert.equal(whole.selection.display_quote,'The file observations.csv contains (x,y) only.');
  // The HTML harness has no live Range; a StaticRange-shaped boundary record carries exactly the four boundary
  // fields commentTargetOf reads from a browser selection range.
  const boundary=(startContainer,startOffset,endContainer,endOffset)=>({startContainer,startOffset,endContainer,endOffset});
  const range=boundary(body.childNodes[2].firstChild,1,body.childNodes[3].firstChild,5);
  const span=commentTargetOf(block,range);
  assert.equal(span.selection.kind,'piece-span');assert.equal(line.slice(span.selection.start,span.selection.end),'contains $(x,y)$');
  assert.equal(span.selection.display_quote,'contains (x,y)');
  const inside=boundary(body.childNodes[2].firstChild,1,body.childNodes[3].firstChild,2);
  assert.equal(commentTargetOf(block,inside).refused,'inside-math');
  const across=boundary(body.childNodes[2].firstChild,1,other.firstChild,3);
  assert.equal(commentTargetOf(block,across).refused,'multi-source');
 }finally{env.restore();}
});

// Review 276bdce0 F1: the ACTUAL writing-panel commentBasis, mouseup and commentFrom source (sliced verbatim from
// writing-panel.mjs) run against the real walk-selection mapper over DOM paragraphs. An inside-math selection and a
// selection across paragraphs reach typed refusals with explicit qualified whole-paragraph choices and no source target of
// their own, and the comment opener receives that refusal; a valid in-paragraph span still names its piece-span target.
test('comment reader caller: actual writing-panel mouseup and commentBasis reach typed refusals with qualified choices',async()=>{
 const {installHTMLDocument}=await import('./helpers/html_dom.mjs');
 const env=installHTMLDocument();
 try{
  const {commentTargetOf}=await loadShared('walk-selection.mjs');
  const panel=readFileSync(new URL('../src/laplace/web/static_shared/writing-panel.mjs',import.meta.url),'utf8');
  const slice=(from,to)=>{const start=panel.indexOf(from),end=panel.indexOf(to,start);assert.ok(start>=0&&end>start,'writing-panel holds '+from.trim());return panel.slice(start,end);};
  const text=s=>{const n=document.createTextNode(s);n.nodeValue=s;return n;};
  const paragraph=(id,parts)=>{const blk=document.createElement('div');blk.className='blk';blk.dataset.block=id;const body=document.createElement('p');blk.append(body);let at=0;
   const pieceMap=parts.map(([t,shown,oStart,oEnd])=>{const span=document.createElement('span');span.append(text(shown));body.append(span);
    const row={t,oStart,oEnd,rStart:at,rEnd:at+shown.length,rText:shown,nodes:[span]};at+=shown.length;return row;});return {blk,body,pieceMap};};
  const first='The file \\texttt{observations.csv} contains $(x,y)$ only.',second='Another paragraph.';
  const p1=paragraph('b1',[['text','The file ',0,9],['code','observations.csv',9,34],['text',' contains ',34,44],['math','(x,y)',44,51],['text',' only.',51,57]]);
  const p2=paragraph('b2',[['text',second,0,second.length]]);
  const paper=document.createElement('div');paper.append(p1.blk,p2.blk);document.body.append(paper);
  const model={b1:{id:'b1',tex:first,pieceMap:p1.pieceMap,bodyEl:p1.body},b2:{id:'b2',tex:second,pieceMap:p2.pieceMap,bodyEl:p2.body}};
  const rows=[{id:'b1',file:'main.tex',repo_file:'main.tex',section:'s1',line_start:3,line_end:3},{id:'b2',file:'main.tex',repo_file:'main.tex',section:'s1',line_start:5,line_end:5}];
  let pick=null;
  const win={getSelection:()=>pick,parent:{postMessage(){}},walk:{editState:()=>null,blocks:()=>rows,identities:id=>['identity-'+id],insertionPoint:()=>null,
   commentSelection:(id,range=null)=>commentTargetOf(model[id],range)}};
  const located=()=>({basis:{selection_identity:'sha256:'+'1'.repeat(64),source_digest:'sha256:'+'2'.repeat(64)}});
  const commentBasis=new Function('window','blockSourceLocation',slice('  function commentBasis(','\n  // The selected-passage comment carries')+'\nreturn commentBasis;')(win,located);
  const mouseup=panel.split('\n').find(line=>line.includes("$('#paper').addEventListener('mouseup'"));assert.ok(mouseup,'writing-panel holds the mouseup caller');
  const bubble={style:{},hidden:true,offsetWidth:0};
  const selected=new Function('$','window','bubble','commentBasis','innerWidth','let selected=null,selectedPoint=null;'+mouseup+'\nreturn ()=>selected;')(name=>name==='#paper'?paper:null,win,bubble,commentBasis,1024);
  const select=(startNode,startOffset,endNode,endOffset,touched,quote)=>{const range={startContainer:startNode,startOffset,endContainer:endNode,endOffset,
    intersectsNode:node=>touched.includes(node),cloneRange(){return this;},getBoundingClientRect:()=>({left:0,top:0})};
   pick={rangeCount:1,isCollapsed:false,getRangeAt:()=>range,toString:()=>quote};paper.dispatchEvent({type:'mouseup'});return selected();};
  const containsText=p1.body.childNodes[2].firstChild,mathText=p1.body.childNodes[3].firstChild;
  const inside=select(containsText,1,mathText,2,[p1.blk],'contains (x');
  assert.equal(inside.comment.mapping.refused,'inside-math');assert.ok(!inside.comment.anchor.source_selection,'no source target is invented');
  assert.deepEqual(inside.comment.mapping.choices.map(choice=>choice.anchor.source_selection.kind),['whole-block']);
  const across=select(containsText,1,p2.body.firstChild.firstChild,3,[p1.blk,p2.blk],'contains (x,y) only. Ano');
  assert.equal(across.comment.mapping.refused,'multi-source','the actual multi-paragraph gesture reaches the typed refusal');assert.ok(!across.comment.anchor.source_selection);
  assert.deepEqual(across.comment.mapping.choices.map(choice=>[choice.anchor.block,choice.anchor.line_start,choice.anchor.source_selection.kind,choice.anchor.source_selection.end,choice.expected]),
   [['b1',3,'whole-block',first.length,['identity-b1']],['b2',5,'whole-block',second.length,['identity-b2']]]);
  const span=select(containsText,1,mathText,5,[p1.blk],'contains (x,y)');
  assert.equal(span.comment.anchor.source_selection.kind,'piece-span');assert.equal(span.comment.mapping,undefined);
  // Review 30e422e0 finding 3: a range starting in the paragraph and ending in its margin (outside the body, inside the
  // same paragraph block) is refused, and the paragraph's own qualified whole-block target is offered, never applied.
  const margin=document.createElement('span');p1.blk.append(margin);margin.append(text(' '));
  const overhang=select(containsText,1,margin.firstChild,1,[p1.blk],'contains (x,y) only.');
  assert.equal(overhang.comment.mapping.refused,'outside-paragraph');assert.ok(!overhang.comment.anchor.source_selection,'no target is applied');
  assert.deepEqual(overhang.comment.mapping.choices.map(choice=>[choice.label,choice.anchor.block,choice.anchor.source_selection.kind,choice.anchor.source_selection.end]),
   [['Comment on the whole paragraph','b1','whole-block',first.length]]);
  const opened=[];
  const commentFrom=new Function('openFeedbackComment','projectId','request','panelProposalReview','window','location',slice('  const commentFrom=','\n  for(const [label,mode,id]of')+'\nreturn commentFrom;')(
   args=>{opened.push(args);return null;},'p',async()=>{throw Error('no owner request here');},()=>null,win,{origin:'http://local'});
  commentFrom(across.comment);
  assert.equal(opened.length,1);assert.equal(opened[0].selection.mapping.refused,'multi-source','the comment opener receives the refusal');
  assert.ok(!('mapping' in opened[0].selection.prepare),'the prepare request carries no refusal');assert.ok(!opened[0].selection.prepare.anchor.source_selection);
 }finally{env.restore();}
});

// Review 276bdce0 F5: the real exported walk-pieces renderer (renderPiecesMapped, usableMap, refreshPieceMap) draws the
// owner tokenizer's own pieces, math through the bundled KaTeX via the real walk-media mathNode, into the DOM double; its
// measured map then feeds the shared mapper, and the owner's _target qualifies the result. No map is hand-built here.
test('comment mapping parity: the real walk-pieces renderer map of owner tokenizer pieces with bundled KaTeX feeds the mapper and owner target',async()=>{
 const {installHTMLDocument}=await import('./helpers/html_dom.mjs');
 const env=installHTMLDocument();
 const {execFileSync}=await import('node:child_process'),{createRequire}=await import('node:module');
 const launcher=new URL('../scripts/laplace_python.py',import.meta.url).pathname,wrapper=new URL('../scripts/laplace-python',import.meta.url).pathname;
 const ownerPython=args=>process.env.LAPLACE_PYTHON?execFileSync(process.env.LAPLACE_PYTHON,['-I','-B',launcher,...args],{encoding:'utf8'}):execFileSync(wrapper,args,{encoding:'utf8'});
 // The double's Text keeps its characters in data; a browser Text exposes the same characters as nodeValue, which the
 // renderer measures. This makes the double faithful for the duration of this test only.
 const proto=Object.getPrototypeOf(document.createTextNode('')),prior=Object.getOwnPropertyDescriptor(proto,'nodeValue');
 Object.defineProperty(proto,'nodeValue',{configurable:true,get(){return this.data;},set(value){this.data=String(value??'');}});
 try{
  const media=await loadShared('walk-media.mjs'),renderer=await loadShared('walk-pieces.mjs'),reader=await loadShared('walk-selection.mjs'),{commentSourceSelection}=await loadShared('manuscript-editing.mjs');
  media.K.katex=createRequire(import.meta.url)('../src/laplace/web/static_shared/katex/katex.min.js');
  const line='The file \\texttt{observations.csv} contains $(x,y) = (0,0)$ and $(1,2)$ only.';
  const pieces=JSON.parse(ownerPython(['-c','import json,sys;from laplace.manuscript.walk import tex_pieces;print(json.dumps(tex_pieces(sys.argv[1])))',line]));
  const body=document.createElement('p'),map=[];document.body.append(body);renderer.renderPiecesMapped(pieces,body,map,body);
  assert.ok(renderer.usableMap(map),'every renderer row carries ordered owner source offsets');
  for(const piece of pieces){const drawn=map.filter(row=>row.oStart>=piece.o_start&&row.oEnd<=piece.o_end);assert.ok(drawn.length,'the renderer drew owner piece '+piece.t+' at '+piece.o_start);
   if(!Array.isArray(piece.pieces))assert.deepEqual(drawn.map(row=>[row.t,row.oStart,row.oEnd]),[[piece.t,piece.o_start,piece.o_end]]);}
  const formulas=map.filter(row=>row.t==='math');assert.equal(formulas.length,2);assert.ok(formulas.every(row=>row.rEnd>row.rStart),'bundled KaTeX drew measurable text for each formula');
  const display=reader.hostText(body);assert.equal(map.at(-1).rEnd,display.length,'the map covers exactly the displayed paragraph');
  const measured=map.map(row=>[row.rStart,row.rEnd]);renderer.refreshPieceMap({pieceMap:map,bodyEl:body});
  assert.deepEqual(map.map(row=>[row.rStart,row.rEnd]),measured,'refreshPieceMap re-measures the same rendered spans');
  const owner=selection=>JSON.parse(ownerPython(['-c','import json,sys\nfrom laplace.pipeline.correction_origin import _target\ntry:print(json.dumps({"target":_target({"source_selection":json.loads(sys.argv[2])},{"source_quote":sys.argv[1]})}))\nexcept ValueError as error:print(json.dumps({"refused":str(error)}))',line,JSON.stringify(selection)]));
  const whole=commentSourceSelection({tex:line,pieceMap:map,display});
  assert.equal(whole.selection.end,line.length);assert.deepEqual(owner(whole.selection),{target:line});
  const contains=map.find(row=>row.t==='text'&&row.rText.includes('contains')),math=formulas[0];
  const span=commentSourceSelection({tex:line,pieceMap:map,display,start:contains.rStart+1,end:math.rEnd});
  assert.equal(span.selection?.kind,'piece-span',JSON.stringify(span));assert.deepEqual(owner(span.selection),{target:'contains $(x,y) = (0,0)$'});
  assert.equal(commentSourceSelection({tex:line,pieceMap:map,display,start:contains.rStart+1,end:math.rStart+1}).refused,'inside-math');
 }finally{
  // The imported reader modules finish their own deferred start-up against the document before it is removed.
  await new Promise(resolve=>setTimeout(resolve,250));
  if(prior)Object.defineProperty(proto,'nodeValue',prior);else delete proto.nodeValue;env.restore();}
});

// wave 13 id sweep: pages whose own focused evaluators mount them (the All tasks page) are checked here too: every data-control
// the mounted page renders is declared for its view, and the page's always-present controls are rendered.
test('wave 13: the All tasks page renders only declared ids and its declared controls',async()=>{
 const {fixture}=await import('./helpers/backlog_fixture.mjs');const f=await fixture();
 try{
  const rows=f.host.all().filter(controlOf2).map(node=>({id:controlOf2(node),owner:ownerOf(node)||node.getAttribute?.('data-control-owner')||null}));
  for(const row of rows)assert.ok(declared.has(row.id),'All tasks: undeclared control '+row.id);
  const present=new Set(rows.map(r=>r.id));
  for(const id of ['backlog:add-task-open','backlog:guide','backlog:queue-active','backlog:queue-all','backlog:filter-options','backlog:refresh','backlog:plan','backlog:filter','backlog:row-details'])assert.ok(present.has(id),'All tasks: '+id+' is rendered');
  for(const row of rows.filter(r=>declared.get(r.id)?.dynamic))assert.ok(row.owner,'All tasks: dynamic '+row.id+' carries data-control-owner');
 }finally{f.close();}
});
