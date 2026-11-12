import {beforeEach,test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {mountOperatorWork,operatorHTTP,workStandingLabel,workCountSummary} from '../src/laplace/web/static_shared/workspace-work.mjs';
import {workspaceSource} from './helpers/workspace_source.mjs';
class Node{
 constructor(tag='div'){this.tag=tag;this.children=[];this.attrs={};this.dataset={};this.className='';this._text='';this.value='';this.isConnected=true;}
 set textContent(v){this._text=String(v??'');this.children=[];}get textContent(){return this._text+this.children.map(n=>n.textContent||'').join('');}
 append(...nodes){for(const n of nodes){n.parentElement=this;this.children.push(n);}}replaceChildren(...nodes){this._text='';this.children=[];this.append(...nodes);}setAttribute(k,v){this.attrs[k]=v;}all(){return [this,...this.children.flatMap(n=>n.all?.()||[])];}querySelector(selector){return this.all().find(n=>selector.startsWith('.')?n.className.split(' ').includes(selector.slice(1)):n.tag===selector);}querySelectorAll(selector){return this.all().filter(n=>selector==='[data-work-id]'?n.dataset.workId!=null:selector.startsWith('.')?n.className.split(' ').includes(selector.slice(1)):n.tag===selector);}focus(options){this.focusOptions=options;document.activeElement=this;}scrollIntoView(){this.revealed=true;}showModal(){this.open=true;}close(){this.open=false;this.onclose?.();}remove(){this.isConnected=false;this.parentElement.children=this.parentElement.children.filter(n=>n!==this);}
}
beforeEach(()=>{globalThis.document={createElement:tag=>new Node(tag),body:new Node('body'),head:new Node('head'),querySelector:()=>null};});
const button=(host,label)=>host.all().find(n=>n.tag==='button'&&n.textContent===label);
const get=id=>({http:{method:'GET',url:'/work/state?project=fixture&view=detail&id='+id}});
const detail=(id,extra={})=>({project:'fixture',view:'detail',task:{id,title:id,goal:'Authored criterion',status:'blocked',recorded_status:'done'},blockers:[],allowed_actions:{task_status:{permitted:true,statuses:['ready','blocked','done'],payload:{id,expected_work_scope_revision:'old-scope',expected_dependency_revision:'old-deps'},http:{method:'POST',url:'/work/transition'}}},children:{items:[]},dependants:{items:[]},read_cut:{revision:'cut'},...extra});
async function mounted(request,initial='A'){const host=new Node();const controller=await mountOperatorWork(host,{project:'fixture',summary:{tasks:[{id:'A',title:'A',status:'blocked'}]},initialWork:initial,request});return {host,controller};}
test('reinspection reconciles only the selected catalogue projection and preserves draft, selection and scroll',async()=>{
 let reads=0;const calls=[];
 const {host,controller}=await mounted(async path=>{calls.push(path);const value=detail('A');if(++reads>1)value.task={...value.task,title:'Renewed title',status:'done',currentness:{status:'CURRENT'}};return value;});
 const catalogue=host.querySelector('.operator-work-catalog'),row=catalogue.querySelector('.operator-work-row');catalogue.scrollTop=73;
 const form=host.all().find(n=>n.tag==='form');form.querySelector('textarea').value='Unsent exact evidence';form.oninput();
 assert.equal(row.querySelector('.work-badge').textContent,'blocked');
 await button(host,'Reinspect this work').onclick();
 assert.equal(catalogue.querySelector('.operator-work-row'),row);
 assert.equal(row.querySelector('button').textContent,'Renewed title');
 assert.equal(row.querySelector('.work-badge').textContent,'done');
 assert.equal(row.querySelector('.work-badge').dataset.workState,'done');
 assert.equal(row.querySelector('button').attrs['aria-current'],'true');
 assert.equal(catalogue.scrollTop,73);assert.equal(controller.capture().selected,'A');
 assert.equal(host.all().find(n=>n.tag==='form').querySelector('textarea').value,'Unsent exact evidence');
 assert.match(host.textContent,/Status and evidence/);assert.ok(!host.textContent.includes('Why waiting'));
 assert.equal(calls.length,2);assert.ok(calls.every(path=>path.includes('view=detail')));
});
test('focused owner blockers distinguish current source readiness, stale consumed scope and exact prerequisites',async()=>{
 const d=detail('A',{blockers:[{message:'Consumed literature scope differs.',current_coverage_ready:true,historical_diff:'UNAVAILABLE: old composite receipt',subject:{owner:'literature',qualified_id:'fixture::A'},consumed_revision:'consumed',observed_revision:'current',clear_when:{predicate:'explicit_completion_on_inspected_current_basis'},read_handles:[get('B')]}]});const calls=[];
 const {host,controller}=await mounted(async path=>{calls.push(path);return path.includes('id=B')?detail('B'):d;});
 assert.match(host.textContent,/coverage ready: true/);assert.match(host.textContent,/Consumed: consumed/);assert.match(host.textContent,/Observed: current/);assert.match(host.textContent,/UNAVAILABLE: old composite/);
 await button(host,'Read owner basis').onclick();assert.equal(controller.detail.task.id,'B');assert.equal(calls.length,2);
});
test('refused disposition retains original guards and evidence draft across reinspection; no hidden retries',async()=>{
 let reads=0;const posts=[];const {host,controller}=await mounted(async(path,payload)=>{if(payload){posts.push(payload);throw Error('Dependency changed');}const value=detail('A');if(++reads>1)value.allowed_actions.task_status.payload.expected_dependency_revision='new-deps';return value;});
 let form=host.all().find(n=>n.tag==='form');form.querySelector('textarea').value='exact.json';form.querySelector('select').value='done';form.oninput();await form.onsubmit({preventDefault(){}});
 assert.equal(posts.length,1);assert.equal(posts[0].project,'fixture');assert.equal(posts[0].expected_dependency_revision,'old-deps');assert.equal(controller.hasDraft,true);
 await controller.select('A');form=host.all().find(n=>n.tag==='form');assert.equal(form.querySelector('textarea').value,'exact.json');assert.match(host.textContent,/original work\/dependency guards/);
 await form.onsubmit({preventDefault(){}});assert.equal(posts.length,2);assert.equal(posts[1].expected_dependency_revision,'old-deps');
});
test('late detail and campaign pages cannot repaint a newly selected work item',async()=>{
 let finish;const {host,controller}=await mounted(async path=>path.includes('id=slow')?new Promise(resolve=>{finish=()=>resolve(detail('slow'));}):detail(path.includes('id=B')?'B':'A'));
 const pending=controller.select('slow');await controller.select('B');finish();await pending;assert.equal(controller.detail.task.id,'B');assert.ok(!host.textContent.includes('Current standing: slow'));
});
test('neighbourhood is a deliberate paged read: contains and requires stay typed, boundary handles read through their owner, continuation is cut-pinned',async()=>{
 const calls=[];const page={project:'fixture',read_cut:{revision:'cut'},view:'graph',nodes:[{id:'A',title:'Campaign',status:'open'}],edges:[{source:'A',target:'B',kind:'contains'},{source:'A',target:'C',kind:'requires'}],boundaries:[{id:'B',read_handle:get('B')}],pagination:{next_read:{http:{method:'GET',url:'/work/state?project=fixture&view=graph&parent_work_id=A&offset=1&as_of=cut'}}}};
 const {host}=await mounted(async path=>{calls.push(path);if(path.includes('offset=1'))return {project:'fixture',view:'graph',read_cut:{revision:'cut'},nodes:[{id:'B',title:'Child',status:'done'}],edges:[]};return path.includes('view=graph')?page:detail('A');});
 assert.ok(!calls.some(path=>path.includes('view=graph')),'the detail read pays nothing for the map');
 const toggle=button(host,'Show neighbourhood map');assert.equal(toggle.attrs['data-control'],'work:neighbourhood');await toggle.onclick();
 const map=host.querySelector('.topology');assert.ok(map);assert.equal(calls.filter(path=>path.includes('view=graph')).length,1);
 const relation=label=>map.all().find(n=>n.tag==='li'&&n.textContent.includes(label));
 assert.ok(relation('Campaign').textContent.includes('B'),'contains row');assert.ok(map.textContent.includes('Requires'));assert.ok(map.textContent.includes('Contains'));
 const outside=map.all().find(n=>n.tag==='button'&&n.textContent==='B');assert.ok(outside,'a boundary id reads through its owner handle');await outside.onclick();assert.ok(calls.at(-1).includes('id=B'));
 await button(host,'More neighbourhood').onclick();assert.ok(calls.at(-1).includes('as_of=cut'));assert.ok(map.all().some(n=>n.tag==='button'&&n.textContent==='Child'));
 assert.ok(!host.all().some(n=>n.tag==='button'&&n.textContent==='More neighbourhood'),'the continuation control leaves when the owner has no next page');
 assert.ok(!host.textContent.includes('Campaign relationships'));
});
test('prerequisites list every authored dependency with its observed standing and never a guessed title',async()=>{
 const d=detail('A',{task:{...detail('A').task,depends_on:['B','ghost']},blockers:[{kind:'PREREQUISITE_NOT_COMPLETE',relation:'prerequisite',message:'Prerequisite B is open.',sentence:'Waiting on Beta, which is open.',subject:{owner:'project_work',id:'B',title:'Beta',standing:{status:'open',lifecycle:{status:'open',closed:false},readiness:{status:'READY'}}},next_actions:[],read_handles:[]}]});
 const {host}=await mounted(async path=>path.includes('id=B')?detail('B'):d);
 const box=host.querySelector('.operator-work-prerequisites');assert.ok(box);assert.equal(box.dataset.control,'work:prerequisites');
 const rows=box.querySelectorAll('li');assert.equal(rows.length,2);
 assert.ok(rows[0].textContent.includes('Requires')&&rows[0].textContent.includes('Beta'));assert.ok(rows[0].textContent.includes('Recorded'),'standing chip from the owner subject');
 assert.ok(rows[1].textContent.includes('ghost')&&rows[1].textContent.includes('standing not observed')&&rows[1].textContent.includes('the read names it'));
 assert.equal(host.all().find(n=>n.dataset.control==='work:item').dataset.controlOwner,'fixture::A');
 await rows[0].all().find(n=>n.tag==='button').onclick();
});
test('external workflow observer is lazy and reads only the supplied owner route',async()=>{
 const calls=[];const {host}=await mounted(async path=>{calls.push(path);return path.includes('view=workflows')?{workflows:[{run_id:'WORKFLOW-owned',status:'RECORDED-PENDING',read_handle:{http:{method:'GET',url:'/work/state?view=workflows&run_id=WORKFLOW-owned'}}}]}:detail('A');});assert.equal(calls.length,1);
 const disclosure=host.all().find(n=>n.tag==='details'&&n.children[0].textContent==='Recorded development workflows');disclosure.open=true;await disclosure.ontoggle();assert.equal(calls.length,2);assert.match(host.textContent,/Recorded workflow runs \(read-only\)/);assert.ok(button(host,'Read exact recorded workflow'));
 assert.throws(()=>operatorHTTP({http:{method:'POST',url:'/unsafe'}}),/GET route/);assert.throws(()=>operatorHTTP({http:{method:'GET',url:'https://outside.test/path'}}),/outside/);
});


test('actual owner fixtures render S3, three Spans prerequisite predicates and ready coverage scope mismatch without writes',{skip:!process.env.LAPLACE_OPERATOR_FIXTURES},async()=>{
 const fixtures=JSON.parse(readFileSync(process.env.LAPLACE_OPERATOR_FIXTURES,'utf8'));
 for(const name of ['spans','foundation209','foundationacd','S3']){
  const f=fixtures[name],host=new Node(),calls=[];assert.equal(f.value.view,'detail');const controller=await mountOperatorWork(host,{project:f.project,summary:{tasks:[f.value.task]},initialWork:f.value.task.id,request:async(path,payload)=>{calls.push({path,payload});assert.equal(payload,undefined);return f.value;}});
  assert.equal(controller.detail.task.id,f.value.task.id);assert.equal(calls.length,1);
  for(const blocker of f.value.blockers){assert.ok(host.textContent.includes(blocker.message));if(blocker.clear_when?.predicate)assert.ok(host.textContent.includes(blocker.clear_when.predicate));}
  if(name==='spans')assert.equal(f.value.blockers.filter(x=>x.kind==='PREREQUISITE_NOT_COMPLETE').length,3);
  if(name.startsWith('foundation'))assert.match(host.textContent,/coverage ready: true/);
  if(name==='S3'){assert.ok(f.value.task.dispatch);assert.match(host.textContent,/Exact accepted reviews:/);assert.ok(host.textContent.includes(f.value.task.dispatch.review_state));}
  controller.destroy();
 }
});

test('held work exposes permitted resume dispositions without offering completion',async()=>{
 const held=detail('A');held.task.recorded_status='blocked';held.allowed_actions.task_status.statuses=['ready','blocked'];
 const {host}=await mounted(async()=>held);const form=host.all().find(n=>n.tag==='form');
 assert.ok(form);assert.deepEqual(form.querySelector('select').children.map(n=>n.value),['ready','blocked']);
 assert.ok(host.textContent.includes('Reason or completion summary'));
});

for(const kind of ['authored work','disposition'])test('pending '+kind+' save retains newer drafts and selected work',async()=>{
 const value=id=>{const d=detail(id);if(kind==='authored work')d.allowed_actions.task={permitted:true,payload:{id,expected_work_revision:'old'},http:{method:'POST',url:'/work/task'}};return d;};
 let release;const {host,controller}=await mounted(async(path,payload)=>payload?new Promise(resolve=>{release=()=>resolve({ok:true});}):value(path.includes('id=B')?'B':'A'));
 const form=host.all().find(n=>n.tag==='form'),input=form.querySelector('textarea');
 input.value='submitted';form.oninput();const save=form.onsubmit({preventDefault(){}});
 input.value='newer unsent';form.oninput();await controller.select('B');release();await save;
 assert.equal(controller.detail.task.id,'B');const draft=controller.capture().drafts.A;
 assert.equal(kind==='authored work'?draft.fields.goal:draft.evidence,'newer unsent');
});

test('neighbourhood continuation preserves edges from prior-page parents and distinguishes logical targets',async()=>{
 const first={project:'fixture',view:'graph',read_cut:{revision:'cut'},nodes:[{id:'A',title:'Campaign',status:'ready'}],edges:[],pagination:{next_read:{http:{method:'GET',url:'/work/state?project=fixture&view=graph&parent_work_id=A&offset=1&as_of=cut'}}}};
 const second={project:'fixture',view:'graph',read_cut:{revision:'cut'},nodes:[{id:'B',title:'Child',status:'ready'}],edges:[{source:'A',target:'B',kind:'contains'},{source:'B',target:'logical::concept',kind:'targets-logical-node'}],pagination:{}};
 const {host}=await mounted(async path=>path.includes('offset=1')?second:path.includes('view=graph')?first:detail('A'));
 await button(host,'Show neighbourhood map').onclick();await button(host,'More neighbourhood').onclick();
 const map=host.querySelector('.topology');const rows=map.querySelectorAll('li');
 assert.ok(rows.some(row=>row.textContent.includes('Campaign')&&row.textContent.includes('Child')),'the prior-page parent keeps its edge');
 const logical=rows.find(row=>row.textContent.includes('logical::concept'));assert.ok(logical);assert.ok(map.textContent.includes('not an execution prerequisite'));
 assert.ok(logical.textContent.includes('not an execution prerequisite')&&!logical.all().some(n=>n.tag==='button'));
});

test('Work evidence reuses source observation metadata and refuses changed pages with an explicit restart',async()=>{
 const target={owner:'repository',repository:'declared',path:'criteria.md'},start='/projects/material-references?'+new URLSearchParams({project:'fixture',view:'preview',offset:'0',target:JSON.stringify(target)}),next=start.replace('offset=0','offset=2');
 const handle=url=>({operation:'material_references',payload:{view:'preview',target},http:{method:'GET',url}});
 const evidence={...handle(start),consumed_revision:'historical-pin'},calls=[];let count=0;
 const observation=(revision,content)=>({schema_version:'laplace.material-reference-source/1',project:'fixture',id:null,target,current_revision:revision,currentness:'UNBOUND',consumed_revision:null,units:'Unicode characters',owner_result:{content},restart_read:handle(start)});
 const {host}=await mounted(async path=>{calls.push(path);if(path.startsWith('/work/state'))return detail('A',{task:{...detail('A').task,evidence_reads:[evidence]}});if(path===next)return observation('changed','Do not render moved bytes');const value=observation(++count===1?'first':'changed',count===1?'π🌱':'Restarted bytes');if(count===1)value.read_handle=handle(next);return value;});
 await button(host,'Read evidence').onclick();const inspected=document.body.children.at(-1);assert.match(inspected.textContent,/Work evidence: source changed since recorded completion/);assert.match(inspected.textContent,/Workspace material binding/);assert.match(inspected.textContent,/UNBOUND/);assert.match(inspected.textContent,/Current: first/);assert.match(inspected.textContent,/Recorded evidence consumed: historical-pin/);assert.match(inspected.textContent,/criteria.md/);
 await button(inspected,'Read more source').onclick();assert.match(inspected.textContent,/cannot mix read bases/);assert.ok(!inspected.textContent.includes('Do not render moved bytes'));
 await button(inspected,'Restart source observation').onclick();assert.match(inspected.textContent,/Restarted bytes/);assert.match(inspected.textContent,/Current: changed/);
 assert.deepEqual(calls.slice(1),[start,next,start]);
});

test('evidence choices expose owner paths before reading and distinguish equal filenames',async()=>{
 const paths=['criteria/proposal.json','archive/proposal.json'],calls=[];
 const evidence=paths.map(path=>({path,http:{method:'GET',url:'/projects/material-references?'+new URLSearchParams({project:'fixture',view:'preview',target:JSON.stringify({owner:'repository',repository:'declared',path})})}}));
 const {host}=await mounted(async url=>{calls.push(url);if(url.startsWith('/work/state'))return detail('A',{task:{...detail('A').task,evidence_reads:evidence}});return {schema_version:'laplace.material-reference-source/1',project:'fixture',id:null,target:JSON.parse(new URL(url,'http://fixture').searchParams.get('target')),currentness:'UNBOUND',current_revision:'source',owner_result:{content:url===evidence[0].http.url?'Selected criteria bytes':'Selected archive bytes'}};});
 const choices=host.all().filter(n=>n.tag==='button'&&n.attrs['aria-label']?.startsWith('Read evidence: '));
 assert.deepEqual(choices.map(n=>n.attrs['aria-label']),paths.map(path=>'Read evidence: '+path));
 assert.deepEqual(host.all().filter(n=>n.tag==='code').map(n=>n.textContent),['proposal.json','proposal.json']);
 assert.ok(host.all().some(n=>n._text==='criteria'));assert.ok(host.all().some(n=>n._text==='archive'));
 assert.equal(calls.length,1,'labelling must not fetch evidence bodies');
 await choices[1].onclick();assert.equal(calls.at(-1),evidence[1].http.url);assert.match(document.body.children.at(-1).textContent,/Selected archive bytes/);
});

test('unavailable evidence retains its visible owner identity and reason',async()=>{
 const {host}=await mounted(async()=>detail('A',{task:{...detail('A').task,evidence_reads:[{path:'missing/proposal.json',capability_gap:'Configured repository is unavailable.'}]}}));
 assert.ok(host.all().some(n=>n.tag==='code'&&n.textContent==='proposal.json'));assert.ok(host.all().some(n=>n._text==='missing'));assert.match(host.textContent,/Configured repository is unavailable/);assert.equal(button(host,'Read evidence'),undefined);
});

for(const suffix of ['pdf','md'])test('Work '+suffix+' evidence delegates to existing artifact opener with exact cross-namespace owner and guard, no JSON fetch',async()=>{
 const host=new Node(),opened=[],calls=[],path='notes/π source.'+suffix,url='/research/artifact?'+new URLSearchParams({project:'other-namespace',scope:'project',path,expected_sha256:'sha256:'+'a'.repeat(64)});
 const evidence={http:{method:'GET',url},native_capability_gap:'Native text reader does not cover this canonical media.'};
 await mountOperatorWork(host,{project:'fixture',summary:{tasks:[]},initialWork:'A',request:async route=>{calls.push(route);return detail('A',{task:{...detail('A').task,evidence_reads:[evidence]}});},onArtifact:async(...args)=>opened.push(args)});
 assert.match(host.textContent,/does not cover/);await button(host,'Read evidence').onclick();assert.equal(calls.length,1);assert.deepEqual(opened,[[path,'Read evidence',{project:'other-namespace',scope:'project',expectedSha256:'sha256:'+'a'.repeat(64),artifactId:null,artifactOwner:null}]]);
});
test('artifact evidence without an embedded opener exposes its exact pinned owner link without a parse attempt',async()=>{
 const url='/research/artifact?project=fixture&scope=project&path=edition.pdf&expected_sha256=old',calls=[];
 const {host}=await mounted(async route=>{calls.push(route);return detail('A',{task:{...detail('A').task,evidence_reads:[{http:{method:'GET',url}}]}});});
 await button(host,'Read evidence').onclick();assert.equal(calls.length,1);assert.match(host.textContent,/inspection is unavailable/);assert.equal(host.all().find(n=>n.tag==='a').href,url);
});

test('workspace artifact callback preserves foreign owner through the existing opener and nested Markdown links',async()=>{
 // the inspection owner's doors (workspace-inspection.mjs, M5 S2 F1), run with the services the shell gives them
 const source=readFileSync(new URL('../src/laplace/web/static_shared/workspace-inspection.mjs',import.meta.url),'utf8');
 const body=source.slice(source.indexOf('  function renderSavedMarkdown('),source.indexOf('  return {savedMarkdown'));
 const opened=[],markdown=[];
 globalThis.__artifactCallback={project:'selected-project',api:async()=>assert.fail('No unexpected JSON request'),openEvidenceArtifact:async value=>{opened.push(value);return value;},renderArtifactMarkdown:async(host,text,options)=>{markdown.push(options);return options;},session:{guard:fn=>fn()}};
 try{
  const setup='const {project,api,openEvidenceArtifact,renderArtifactMarkdown,session}=globalThis.__artifactCallback;'
   +'const discussion={session:()=>session,generateProfile:()=>{}},work={reload:async()=>{}},home={refreshStyle:async()=>{}};';
  const {inspectProjectArtifact}=await import('data:text/javascript;base64,'+Buffer.from(setup+body+'\nexport {inspectProjectArtifact};').toString('base64'));
  await inspectProjectArtifact('notes.md','Evidence',{project:'foreign-owner',scope:'manuscript',expectedSha256:'exact-pin'});
  assert.equal(opened[0].project,'foreign-owner');assert.equal(opened[0].scope,'manuscript');assert.equal(opened[0].expectedSha256,'exact-pin');
  await opened[0].renderMarkdown({},'Read source',{project:'foreign-owner',scope:'manuscript'});assert.equal(markdown[0].project,'foreign-owner');
  await markdown[0].onOpenArtifact('child.md','Child',{});assert.equal(opened[1].project,'foreign-owner');
 }finally{delete globalThis.__artifactCallback;}
});

test('Work reuses its inspection dialog but discards their continuation on selection or destroy',async()=>{
 for(const change of ['select','destroy']){
  let release;const observed=(content,more=false)=>({schema_version:'laplace.material-reference-source/1',project:'fixture',id:null,target:{owner:'repository',repository:'declared',path:'source.md'},currentness:'UNBOUND',current_revision:'A',units:'Unicode characters',owner_result:{content},...(more?{read_handle:{http:{method:'GET',url:'/next'}}}:{})});
  const handle={http:{method:'GET',url:'/projects/material-references?'+new URLSearchParams({project:'fixture',view:'preview',target:JSON.stringify({owner:'repository',repository:'declared',path:'source.md'})})}},calls=[];
  const {host,controller}=await mounted(async path=>{calls.push(path);if(path==='/next')return new Promise(resolve=>{release=()=>resolve({...observed('OLD_PAGE'),current_revision:'changed'});});if(path.startsWith('/projects/'))return observed('FIRST_PANEL',true);return detail(path.includes('id=B')?'B':'A',{task:{...detail(path.includes('id=B')?'B':'A').task,evidence_reads:[handle]}});});
  await button(host,'Read evidence').onclick();const first=document.body.children.at(-1),pending=button(first,'Read more source').onclick();await button(host,'Read evidence').onclick();assert.equal(document.body.children.length,1);assert.equal(first.isConnected,false);
  if(change==='select')await controller.select('B');else controller.destroy();release();await pending;assert.ok(!host.textContent.includes('OLD_PAGE')&&!host.textContent.includes('cannot mix read bases'));
 }
});

test('Work selection discards a superseded initial source error without changing the current status',async()=>{
 let reject;const handle={http:{method:'GET',url:'/projects/material-references?'+new URLSearchParams({project:'fixture',view:'preview',target:JSON.stringify({owner:'repository',repository:'declared',path:'source.md'})})}};
 const {host,controller}=await mounted(async path=>path.startsWith('/projects/')?new Promise((_,no)=>{reject=()=>no(Error('OLD_INITIAL_ERROR'));}):detail(path.includes('id=B')?'B':'A',{task:{...detail(path.includes('id=B')?'B':'A').task,evidence_reads:[handle]}}));
 const pending=button(host,'Read evidence').onclick();await new Promise(resolve=>setImmediate(resolve));await controller.select('B');reject();await pending;assert.equal(controller.detail.task.id,'B');assert.ok(!host.textContent.includes('OLD_INITIAL_ERROR'));
 const status=host.querySelector('.work-status');assert.match(status.textContent,/^Work observed /);assert.equal(status.title,'Owner cut: cut');assert.match(host.textContent,/Work cut: cut/);
});


const facetTask=(id,{closed=false,completed=false,review=false,ready='READY'}={})=>({id,title:id,status:review?'blocked':'ready',recorded_status:completed?'done':'open',lifecycle:{status:completed?'done':'open',closed,completed},current_acceptance:{status:review?'REVIEW_REQUIRED':completed?'CURRENT':'NOT_REQUIRED',review_required:review,reason:review?'Source evidence changed.':'Owner currentness observed.'},readiness:{status:closed?'CLOSED':ready,blocked_by:ready==='BLOCKED'?['prerequisite']:[],reason:ready==='BLOCKED'?'Requires current prerequisite acceptance.':'Declared prerequisite requirement satisfied.'}});
test('owner lifecycle counts and groups retain completed review separately from pending work',async()=>{
 const tasks=[...Array.from({length:9},(_,i)=>facetTask('pending:'+i,{ready:i?'READY':'BLOCKED'})),...Array.from({length:14},(_,i)=>facetTask('review:'+i,{closed:true,completed:true,review:true})),...Array.from({length:6},(_,i)=>facetTask('done:'+i,{closed:true,completed:true}))];
 const summary={project:'fixture',view:'summary',tasks,counts:{pending:9,completed:20,completed_review_required:14,recorded_lifecycle:{done:20,open:9}}};
 assert.match(workCountSummary(summary),/9 pending tasks.*20 recorded completions.*14 completed tasks need current review/);
 assert.match(workStandingLabel(tasks[9]),/Recorded done.*review required/);assert.ok(!workCountSummary(summary).includes('23 open'));
 const host=new Node();await mountOperatorWork(host,{project:'fixture',summary,request:async()=>{throw Error('No automatic detail read');}});
 const groups=host.all().filter(n=>n.dataset.workGroup);assert.deepEqual(groups.map(n=>n.dataset.workGroup),['pending','review','history']);assert.equal(groups[0].querySelectorAll('.operator-work-row').length,9);assert.equal(groups[1].querySelectorAll('.operator-work-row').length,14);assert.equal(groups[2].querySelectorAll('.operator-work-row').length,6);
 assert.equal(workCountSummary({tasks}),'Counts unavailable from the owner.');
});
test('guarded completion observes one fresh summary and detail for prerequisite readiness without promoting status',async()=>{
 const calls=[];let completed=false;const host=new Node();const rows=()=>[facetTask('A',{closed:completed,completed}),facetTask('B',{ready:completed?'READY':'BLOCKED'})];
 const summary=()=>({project:'fixture',view:'summary',tasks:rows(),counts:{pending:completed?1:2,completed:completed?1:0,completed_review_required:0}});
 const request=async(path,payload)=>{calls.push({path,payload});if(payload){completed=true;return {task:rows()[0]};}if(path.includes('view=summary'))return summary();const id=new URL(path,'http://local').searchParams.get('id');return detail(id,{task:rows().find(row=>row.id===id)});};
 const controller=await mountOperatorWork(host,{project:'fixture',summary:summary(),initialWork:'A',request});
 const form=host.all().find(n=>n.tag==='form');form.querySelector('textarea').value='validated-evidence.json';form.querySelector('select').value='done';form.oninput();await form.onsubmit({preventDefault(){}});
 assert.equal(calls.filter(c=>c.payload).length,1);assert.equal(calls.filter(c=>c.path.includes('view=summary')).length,1);assert.equal(calls.filter(c=>c.path.includes('view=detail')).length,2);
 assert.equal(calls.find(c=>c.payload).payload.expected_dependency_revision,'old-deps');assert.equal(controller.capture().selected,'A');
 const row=host.all().find(n=>n.dataset.workId==='B');assert.match(row.parentElement.textContent,/readiness ready/);assert.match(host.textContent,/1 pending tasks/);
});
test('completed current review facet is labelled historically while causal prerequisites stay visible',async()=>{
 const host=new Node(),task=facetTask('A',{closed:true,completed:true,review:true});task.readiness.blocked_by=['fixture::required'];
 const controller=await mountOperatorWork(host,{project:'fixture',summary:{tasks:[task]},initialWork:'A',request:async()=>detail('A',{task,blockers:[{message:'Consumed source revision changed.'}]})});
 assert.match(host.textContent,/Recorded completion is retained/);assert.match(host.textContent,/not a new pending job/);assert.match(host.textContent,/Prerequisite readiness/);assert.match(host.textContent,/Blocked by: fixture::required/);assert.match(host.textContent,/Actual runtime execution: not reported/);controller.destroy();
});

test('Work detail exposes one standing and related-turn scope without treating Work as a journal row',async()=>{
 const host=new Node(),related=[],task=facetTask('WORK-parent',{closed:true,completed:true});task.currentness={reason:'Recorded evidence matches.'};
 await mountOperatorWork(host,{project:'fixture',summary:{tasks:[task]},initialWork:task.id,request:async()=>detail(task.id,{task}),onHistory:scope=>related.push(scope)});
 const header=host.querySelector('.operator-work-heading');assert.match(header.textContent,/Recorded done/);assert.equal(header.querySelectorAll('.state-chip').length,1,'one primary standing; full facets remain in Status details');assert.ok(!header.textContent.includes('Recorded status'));
 const basis=host.querySelector('.operator-work-facets');assert.equal(basis.tag,'details');assert.equal(basis.children[0].textContent,'Status details');assert.ok(basis.textContent.includes('CURRENT'));assert.ok(basis.textContent.includes('CLOSED'));assert.ok(basis.textContent.includes('Work cut: cut'));
 await button(host,'View related turns').onclick();assert.deepEqual(related,[{work_id:'WORK-parent',label:'WORK-parent'}]);assert.ok(!('row' in related[0]));
});

test('exact conversation destinations leave the chooser only after successful current selection',async()=>{
 const source=readFileSync(new URL('../src/laplace/web/static_shared/workspace.mjs',import.meta.url),'utf8');const body=source.match(/async function openConversation\(id\)\{[^\n]+/)[0],closed=[],opened=[];
 const session={session:'WS-old',async openConversation(id){this.session=id;return true;},setLibrary:value=>closed.push(value)},open=new Function('chrome','session',body+';return openConversation;')({openSession:value=>opened.push(value)},session);
 await open('WS-exact');assert.deepEqual(closed,[false]);assert.deepEqual(opened,[true]);
 session.openConversation=async()=>{session.session='WS-newer';return false;};await open('WS-stale');assert.deepEqual(closed,[false]);assert.equal(session.session,'WS-newer');
});

const {workSelectionFixture,workDetail}=await import('./helpers/work_selection_harness.mjs');
test('production owner preserves explicit Next Work: a conversation association is not a selection door',async()=>{
 const f=await workSelectionFixture();try{assert.equal(f.owner.restoreConversationWork,undefined,'no association-to-selection door exists (pinned entry rule)');assert.equal(f.owner.currentTask().id,'B');assert.match(f.host.querySelector('.operator-work-heading').textContent,/B/);assert.equal(new URL(location.href).searchParams.get('work'),'B');assert.equal(f.calls.length,0);}finally{f.restore();}
});
test('explicit Clear is coherent and historical association cannot resurrect it',async()=>{
 const f=await workSelectionFixture();try{await f.owner.requestWorkSelection(null);assert.equal(f.owner.currentTask(),null);assert.equal(f.controller.detail,null);assert.equal(f.controller.capture().selected,null);assert.ok(f.host.querySelectorAll('.operator-work-row').every(row=>row.dataset.selectedWork==='false'));assert.equal(new URL(location.href).searchParams.has('work'),true);assert.equal(new URL(location.href).searchParams.get('work'),'');assert.equal(f.owner.currentTask(),null);assert.match(f.host.textContent,/No next Work selected/);assert.equal(f.calls.length,0);}finally{f.restore();}
});
test('a cold association never becomes contextual Work; an explicit choice still works and an owner error retains the prior choice',async()=>{
 const f=await workSelectionFixture({initial:null,explicit:false});try{assert.equal(f.owner.currentTask(),null);assert.equal(f.owner.isExplicit(),false);assert.equal(f.calls.length,0,'nothing is read for a saved association');await f.owner.requestWorkSelection('B');assert.equal(f.owner.currentTask().id,'B');assert.equal(f.controller.detail.task.id,'B');assert.equal(f.owner.isExplicit(),true);f.setRead(()=>{throw Error('OWNER UNAVAILABLE');});assert.equal(await f.owner.requestWorkSelection('C'),false);assert.equal(f.owner.currentTask().id,'B');assert.equal(new URL(location.href).searchParams.get('work'),'B');assert.match(f.host.textContent,/Prior selection and drafts are retained/);}finally{f.restore();}
});
test('known admission observes selected Work once using owner state, never execution or cached status',async()=>{
 const f=await workSelectionFixture();try{f.rows.set('B',workDetail('fixture','B','in-progress'));assert.equal(f.owner.currentTask().status,'open');await f.owner.refreshSelectedWork({project:'fixture',work_id:'B',turn_id:'T',session_id:'S'},()=>true);assert.equal(f.owner.currentTask().status,'in-progress');assert.match(f.host.querySelector('.operator-work-heading').textContent,/in-progress/);assert.equal(f.calls.length,1);assert.ok(f.calls.every(url=>url.includes('view=detail')));}finally{f.restore();}
});
test('selected observation cannot retarget a newer explicit choice or another project/work/turn',async()=>{
 const f=await workSelectionFixture();try{for(const event of [{project:'OTHER',work_id:'B',turn_id:'T',session_id:'S'},{project:'fixture',work_id:'A',turn_id:'T',session_id:'S'},{project:'fixture',work_id:'B'}])await f.owner.refreshSelectedWork(event,()=>true);assert.equal(f.calls.length,0);let finish;f.setRead(url=>url.includes('id=B')?new Promise(resolve=>{finish=()=>resolve(workDetail('fixture','B','done'));}):f.readDefault(url));const old=f.owner.refreshSelectedWork({project:'fixture',work_id:'B',turn_id:'T',session_id:'S'},()=>true);await f.owner.requestWorkSelection('C');finish();await old;assert.equal(f.owner.currentTask().id,'C');assert.equal(f.controller.detail.task.id,'C');}finally{f.restore();}
});
test('fresh observation updates read-only Work facts while the dirty form, its values and guard tokens stay mounted',async()=>{
 const f=await workSelectionFixture();try{const form=f.host.all().find(n=>n.tag==='form'),input=form.querySelector('textarea');input.value='UNSENT EXACT EVIDENCE';form.oninput();const original=f.controller.capture().drafts.B.completionBasis;f.rows.set('B',workDetail('fixture','B','in-progress'));await f.owner.refreshSelectedWork({project:'fixture',work_id:'B',turn_id:'T',session_id:'S'},()=>true);assert.equal(f.host.all().find(n=>n.tag==='form'),form);assert.equal(input.value,'UNSENT EXACT EVIDENCE');assert.deepEqual(f.controller.capture().drafts.B.completionBasis,original);assert.match(f.host.textContent,/Work facts updated from its owner\..*Your text, targets and guards are kept/);assert.match(f.host.querySelector('.operator-work-heading').textContent,/in-progress/,'the read-only standing is the fresh owner fact');assert.ok(!f.host.textContent.includes('Current owner detail read.'));}finally{f.restore();}
});
test('failed project bootstrap and a switched view refuse association/observation without false commit',async()=>{
 const failed=await workSelectionFixture({initial:null,explicit:false});try{assert.equal(failed.owner.restoreConversationWork,undefined,'no association door');assert.equal(failed.calls.length,0);}finally{failed.restore();}
 const f=await workSelectionFixture();try{let finish;f.setRead(()=>new Promise(resolve=>{finish=()=>resolve(workDetail('fixture','B','done'));}));const old=f.owner.refreshSelectedWork({project:'fixture',work_id:'B',turn_id:'T',session_id:'S'},()=>true);f.owner.changeView();finish();await old;assert.equal(f.owner.currentTask().status,'open');assert.equal(f.controller.detail.task.status,'open');}finally{f.restore();}
});


test('actual workspace Work mount honors Clear after leaving and returning, not the original URL selection',async()=>{
 const f=await workSelectionFixture();try{await f.owner.requestWorkSelection(null);f.controller.destroy();const host=document.createElement('section');f.root.append(host);const restored=await f.owner.remount(host);assert.equal(restored.capture().selected,null);assert.equal(restored.detail,null);assert.equal(f.owner.currentTask(),null);assert.equal(new URL(location.href).searchParams.get('work'),'');assert.deepEqual(f.calls.map(url=>new URL(url,'http://local').searchParams.get('view')),['roots'],'the remounted navigator reads its roots once; nothing reads or restores a selection');restored.destroy();}finally{f.restore();}
});


test('production completion change adapter does not rebuild a global catalogue after selected-owner observation',async()=>{
 const f=await workSelectionFixture();try{const observation=await f.owner.refreshSelectedWork({project:'fixture',work_id:'B',turn_id:'T',session_id:'S'},()=>true);await f.owner.runChanged([{operation:'task_status',outcome:{views:['project','pipeline']}}],observation);assert.equal(f.calls.length,1);assert.ok(f.calls.every(url=>url.includes('view=detail')));}finally{f.restore();}
});

const actualWorkEffects=await (await import('./helpers/work_selection_harness.mjs')).actualWorkEffectCases();
for(const [scenario,action]of [
 ['direct',{operation:'task_status',outcome:{views:['project','pipeline'],identities:['B'],status:'SUCCEEDED'}}],
 ['prerequisite',{operation:'task_status',outcome:{views:['project','pipeline'],identities:['A'],status:'SUCCEEDED'}}],
 ['evidence',{operation:'apply_revision',outcome:{views:['manuscript'],source_effect_retained:true,status:'SOURCE_APPLIED_TRACKING_UNPROVED'}}]
])test(`known ${scenario} effect from origin A refreshes selected B through actual owner projection`,async()=>{
 const f=await workSelectionFixture({project:'p',session:{session:'S',origin:{turnId:'T',workId:'A'},scope(){}}});try{
 const values=actualWorkEffects[scenario];await f.controller.select('B',values.before);f.setRead(()=>structuredClone(values.after));await f.owner.runChanged([action]);
 assert.equal(f.calls.length,1);assert.equal(new URL(f.calls[0],'http://local').searchParams.get('id'),'B');assert.equal(f.owner.currentTask().id,'B');assert.deepEqual(f.controller.detail.task,values.after.task);
 if(scenario==='prerequisite'){assert.equal(values.before.task.readiness.status,'BLOCKED');assert.equal(f.controller.detail.task.readiness.status,'READY');}
 if(scenario==='evidence'){assert.equal(values.before.task.current_acceptance.status,'CURRENT');assert.equal(f.controller.detail.task.current_acceptance.status,'REVIEW_REQUIRED');assert.equal(f.controller.detail.task.lifecycle.completed,true);}
 }finally{f.restore();}
});
test('phase read attempt coalesces known effects even with dirty conflict or owner refusal',async()=>{
 for(const failure of ['dirty','refused']){const f=await workSelectionFixture();try{
 if(failure==='dirty'){const form=f.host.all().find(n=>n.tag==='form');form.querySelector('textarea').value='ORIGINAL UNSENT';form.oninput();}else f.setRead(()=>{throw Error('OWNER REFUSED');});
 const observation=await f.owner.refreshSelectedWork({project:'fixture',session_id:'S',turn_id:'T',work_id:'B',phase:'complete'},()=>true);assert.equal(observation.attempted,true);
 await f.owner.runChanged([{operation:'task_status',outcome:{views:['pipeline'],identities:['B']}}],observation);assert.equal(f.calls.length,1);assert.equal(f.owner.currentTask().id,'B');
 if(failure==='dirty'){assert.equal(f.controller.capture().drafts.B.evidence,'ORIGINAL UNSENT');assert.match(f.host.textContent,/Work facts updated from its owner/);}else assert.match(f.host.textContent,/Prior selection and drafts are retained/);
 }finally{f.restore();}}
});
test('old phase effects cannot reread or reselect a newer Next Work, and Clear never adopts an affected task',async()=>{
 const f=await workSelectionFixture();try{const observation=await f.owner.refreshSelectedWork({project:'fixture',session_id:'S',turn_id:'T',work_id:'B',phase:'complete'},()=>true);await f.owner.requestWorkSelection('C');const count=f.calls.length;await f.owner.runChanged([{operation:'task_status',outcome:{views:['pipeline'],identities:['C']}}],observation);assert.equal(f.calls.length,count);assert.equal(f.owner.currentTask().id,'C');await f.owner.requestWorkSelection(null);await f.owner.runChanged([{operation:'task_status',outcome:{views:['pipeline'],identities:['B']}}]);assert.equal(f.owner.currentTask(),null);assert.equal(f.calls.length,count);}finally{f.restore();}
});

// ---- C1a: the Work view consumes the owner's LIST projection and owner-named blockers ----
test('blocker lead names the owner-supplied subject title and standing; no id is parsed from the message',async()=>{
 const standing={status:'ready',recorded_status:'open',lifecycle:{status:'open',completed:false,closed:false},readiness:{status:'READY'},current_acceptance:{status:'NOT_REQUIRED',review_required:false}};
 const blocker={kind:'PREREQUISITE_NOT_COMPLETE',relation:'prerequisite',message:'Prerequisite WORK-decoy is ready.',sentence:'Waiting on Measure the spectrum, which is ready.',
  subject:{owner:'project_work',project:'fixture',id:'B',qualified_id:'fixture::B',revision:'r',title:'Measure the spectrum',standing},
  next_actions:[{...get('B'),operation:'project',kind:'inspect-prerequisite',permitted:true,purpose:'Inspect the exact prerequisite'}],read_handles:[get('B')],clear_when:{description:'Complete the prerequisite on current evidence.'}};
 const calls=[];const {host,controller}=await mounted(async path=>{calls.push(path);return path.includes('id=B')?detail('B'):detail('A',{blockers:[blocker]});});
 const lead=host.querySelector('.operator-blocker-lead');assert.ok(lead,'the lead is painted from the owner subject');
 assert.equal(lead.children[0].textContent,'Waiting on');assert.equal(lead.children[1].textContent,'Measure the spectrum');assert.equal(lead.children[2].textContent,'Recorded open · readiness ready');
 assert.match(host.querySelector('.operator-blocker-message').textContent,/^Waiting on Measure the spectrum/);
 assert.ok(!host.querySelector('.operator-blocker-lead').textContent.includes('WORK-decoy'),'the exact message stays behind the Exact disclosure, never parsed for ids');
 assert.match(host.querySelector('.operator-exact').textContent,/Prerequisite WORK-decoy is ready\./);
 await lead.children[1].onclick();assert.equal(controller.detail.task.id,'B');assert.ok(calls.at(-1).includes('id=B'));
});
test('blockers about this Work itself carry no lead; the owner sentence stands alone',async()=>{
 const blocker={kind:'RECORDED_HOLD',relation:'hold',message:'Awaiting the referee report.',sentence:'Held: Awaiting the referee report.',subject:{owner:'project_work',project:'fixture',id:'A',qualified_id:'fixture::A',title:'A',standing:{status:'blocked'}},next_actions:[],read_handles:[],clear_when:{}};
 const {host}=await mounted(async()=>detail('A',{blockers:[blocker]}));
 assert.ok(!host.querySelector('.operator-blocker-lead'));assert.match(host.querySelector('.operator-blocker-message').textContent,/^Held: Awaiting/);
});
test('More work appends the owner continuation page under the same cut instead of replacing page one',async()=>{
 const row=(id,status='open')=>({id,title:id,status,recorded_status:status,lifecycle:{status,completed:false,closed:false},readiness:{status:'READY'},current_acceptance:{status:'NOT_REQUIRED',review_required:false},read_handle:get(id)});
 const next={operation:'project',payload:{namespace:'fixture',view:'summary',offset:1,limit:1,as_of:'cut'},http:{method:'GET',url:'/work/state?project=fixture&view=summary&offset=1&limit=1&as_of=cut'}};
 const summary={project:'fixture',view:'summary',tasks:[row('A')],counts:{pending:2,completed:0,completed_review_required:0},read_cut:{revision:'cut'},pagination:{total:2,offset:0,limit:1,next_offset:1,next_read:next}};
 const calls=[];const host=new Node();await mountOperatorWork(host,{project:'fixture',summary,request:async path=>{calls.push(path);if(path.includes('offset=1'))return {project:'fixture',view:'summary',continuation:true,tasks:[row('B')],counts:summary.counts,read_cut:{revision:'cut'},pagination:{total:2,offset:1,limit:1,next_offset:null}};throw Error('unexpected read '+path);}});
 assert.deepEqual(host.querySelectorAll('[data-work-id]').map(n=>n.dataset.workId),['A']);
 await button(host,'More work').onclick();
 assert.deepEqual(host.querySelectorAll('[data-work-id]').map(n=>n.dataset.workId),['A','B'],'page one stays visible and page two is appended');
 assert.equal(button(host,'More work'),undefined,'the exhausted continuation removes its control');assert.ok(calls[0].includes('as_of=cut'));
 assert.equal(host.all().filter(n=>n.tag==='h3'&&n.textContent==='Project work').length,1,'one catalogue heading, not one per page');
});
test('a continuation page from a different cut is refused and leaves page one intact',async()=>{
 const row=id=>({id,title:id,status:'open',lifecycle:{status:'open',completed:false,closed:false},readiness:{status:'READY'},current_acceptance:{status:'NOT_REQUIRED',review_required:false}});
 const next={http:{method:'GET',url:'/work/state?project=fixture&view=summary&offset=1&limit=1&as_of=cut'}};
 const host=new Node();await mountOperatorWork(host,{project:'fixture',summary:{project:'fixture',view:'summary',tasks:[row('A')],read_cut:{revision:'cut'},pagination:{total:2,next_offset:1,next_read:next}},request:async()=>({project:'fixture',view:'summary',tasks:[row('B')],read_cut:{revision:'moved'},pagination:{next_offset:null}})});
 await button(host,'More work').onclick();
 assert.deepEqual(host.querySelectorAll('[data-work-id]').map(n=>n.dataset.workId),['A']);assert.match(host.querySelector('.work-status').textContent,/cut changed/);
});

// ---- M5 D: bounded relation pages, keyboard continuity and requested-Work admission ----
const childRow=i=>({id:'C'+String(i).padStart(2,'0'),title:'Child '+i,status:'ready',lifecycle:{status:'open',completed:false,closed:false},readiness:{status:'READY'}});
const childPage=(offset,{total=50,limit=20,cut='cut',items}={})=>{const rows=items||Array.from({length:Math.min(limit,total-offset)},(_,i)=>childRow(offset+i+1)),next=offset+rows.length<total?offset+rows.length:null;
 return {items:rows,total,offset,limit,next_offset:next,next_read:next==null?null:{http:{method:'GET',url:'/work/state?'+new URLSearchParams({project:'fixture',view:'detail',id:'A',limit:String(limit),offset:String(next),as_of:cut})}}};};
test('contained work pages through the owner continuation into one list with one advancing control and focus on the first new row',async()=>{
 const calls=[];const {host}=await mounted(async path=>{calls.push(path);const q=new URL(path,'http://local').searchParams;return detail('A',{children:childPage(Number(q.get('offset')||0))});});
 const family=()=>host.all().find(n=>n.className==='operator-work-family'&&n.children[0]?.textContent==='Contained work');
 const rows=()=>family().all().filter(n=>n.tag==='li').length,controls=()=>host.all().filter(n=>n.tag==='button'&&n.textContent==='More contained work');
 assert.equal(rows(),20);assert.match(family().textContent,/20 of 50 shown/);assert.equal(controls().length,1);
 await controls()[0].onclick();
 assert.equal(rows(),40);assert.match(family().textContent,/40 of 50 shown/);assert.equal(controls().length,1,'the old control left; one control for the next page');
 assert.equal(document.activeElement?.textContent,'Child 21','focus moves to the first appended row');
 const second=new URL(calls.at(-1),'http://local').searchParams;assert.deepEqual([second.get('id'),second.get('offset'),second.get('as_of')],['A','20','cut']);
 await controls()[0].onclick();assert.equal(rows(),50);assert.equal(controls().length,0);assert.ok(!/ of 50 shown/.test(family().textContent),'a complete list makes no partial claim');
 assert.equal(new Set(family().all().filter(n=>n.tag==='li').map(n=>n.textContent)).size,50,'no row painted twice');
});
test('a relation page from a changed cut, another Work or a non-advancing owner is refused and the shown rows stay',async()=>{
 for(const fault of ['cut','other','stall']){
  let first=true;const {host}=await mounted(async path=>{if(first){first=false;return detail('A',{children:childPage(0)});}
   if(fault==='cut')return detail('A',{children:childPage(20),read_cut:{revision:'moved'}});
   if(fault==='other')return {...detail('A',{children:childPage(20)}),task:{id:'B',title:'B'}};
   return detail('A',{children:childPage(20,{items:childPage(0).items})});});
  const family=host.all().find(n=>n.className==='operator-work-family'&&n.children[0]?.textContent==='Contained work');
  const control=host.all().find(n=>n.tag==='button'&&n.textContent==='More contained work');await control.onclick();
  assert.equal(family.all().filter(n=>n.tag==='li').length,20,fault);assert.match(host.querySelector('.work-status').textContent,fault==='cut'?/cut changed/:fault==='other'?/different detail/:/did not advance/);
  assert.ok(control.isConnected,'the control stays for an explicit retry');
 }
});
test('an off-page requested Work is admitted by its exact owner read and never replaced by another Work',async()=>{
 const f=await workSelectionFixture({initial:null,explicit:false});try{
  f.rows.set('FAR',workDetail('fixture','FAR'));assert.ok(!f.owner.currentTask());
  const admitted=await f.owner.admitRequestedWork('FAR');
  assert.equal(admitted.id,'FAR');assert.equal(f.owner.currentTask().id,'FAR');assert.equal(new URL(location.href).searchParams.get('work'),'FAR');
  assert.deepEqual(f.calls.map(url=>new URL(url,'http://local').searchParams.get('id')),['FAR'],'one exact detail read; page one is not taken as absence');
  assert.equal(f.owner.requested(),null);
 }finally{f.restore();}
});
test('an unknown or foreign requested Work keeps the request with explicit recovery and selects nothing else',async()=>{
 const f=await workSelectionFixture({initial:null,explicit:false});try{
  f.setRead(()=>{throw Error('Exact work identity is unavailable in this namespace.');});
  assert.equal(await f.owner.admitRequestedWork('other-project::GONE'),null);
  assert.equal(f.owner.currentTask(),null,'no substitute Work');
  assert.deepEqual(f.owner.requested(),{id:'other-project::GONE',state:'refused',reason:'Exact work identity is unavailable in this namespace.'});
  assert.match(f.notices.at(-1)[0],/Requested Work other-project::GONE was not opened: Exact work identity is unavailable.*Nothing else was selected/);
  f.setRead(f.readDefault);await f.owner.requestWorkSelection('B');assert.equal(f.owner.currentTask().id,'B');assert.equal(f.owner.requested(),null,'an explicit choice ends the request');
 }finally{f.restore();}
});
test('a newer explicit choice wins over a requested Work still being read',async()=>{
 const f=await workSelectionFixture({initial:null,explicit:false});try{
  let finish;f.rows.set('FAR',workDetail('fixture','FAR'));f.setRead(url=>url.includes('id=FAR')?new Promise(resolve=>{finish=()=>resolve(workDetail('fixture','FAR'));}):f.readDefault(url));
  const pending=f.owner.admitRequestedWork('FAR');await f.owner.requestWorkSelection('C');finish();assert.equal(await pending,null);assert.equal(f.owner.currentTask().id,'C');
 }finally{f.restore();}
});
test('boot admits the requested Work through the one admission step before any view or conversation reads it',()=>{
 const source=readFileSync(new URL('../src/laplace/web/static_shared/workspace.mjs',import.meta.url),'utf8');
 const boot=source.indexOf("if(initialQuery.has('work')){await work.admit(initialQuery.get('work'),{isCurrent:entryCurrent});if(!entryCurrent())return workspace;}"),firstView=source.indexOf("const requested=canonicalWorkspaceView(new URLSearchParams(location.search).get('view')");
 assert.ok(boot>0&&firstView>boot,'admission completes before the first view is shown, fenced by this mount\'s lifetime (S2-R2)');
 assert.ok(!source.includes("state.tasks.find(row=>row.id===initialQuery.get('work'))"),'page one is never the admission authority');
 // the Home overview (workspace-home.mjs) reads the selected Work through the Work owner
 assert.match(workspaceSource(),/if\(work\.task\(\)\)workLink\.append\(E\('p','Selected work: '\+work\.task\(\)\.title\)/);
});
test('More neighbourhood keeps keyboard focus on the next page control, then on the map itself',async()=>{
 const page=(offset,next)=>({project:'fixture',view:'graph',read_cut:{revision:'cut'},nodes:[{id:'N'+offset,title:'Node '+offset,status:'open'}],edges:[],
  pagination:{next_read:next==null?null:{http:{method:'GET',url:'/work/state?'+new URLSearchParams({project:'fixture',view:'graph',parent_work_id:'A',offset:String(next),as_of:'cut'})}}}});
 const {host}=await mounted(async path=>{const q=new URL(path,'http://local').searchParams;if(q.get('view')!=='graph')return detail('A');const offset=Number(q.get('offset')||0);return page(offset,offset<2?offset+1:null);});
 await button(host,'Show neighbourhood map').onclick();
 let control=button(host,'More neighbourhood');control.focus();await control.onclick();
 const replacement=button(host,'More neighbourhood');assert.ok(replacement&&replacement!==control);assert.equal(document.activeElement,replacement,'focus moves to the next page control');
 await replacement.onclick();assert.equal(button(host,'More neighbourhood'),undefined);
 const map=host.querySelector('.topology');assert.ok(map.all().includes(document.activeElement),'with no next page, focus stays inside the map');
});
