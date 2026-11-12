import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {Node,installDOM,findButton} from './helpers/evidence_reader_harness.mjs';
import {mountSessionAnalytics} from '../src/laplace/web/static_shared/workspace-analytics.mjs';

// the History view is the activity owner's (workspace-activity.mjs, M5 S2 F1)
const workspace=await readFile(new URL('../src/laplace/web/static_shared/workspace-activity.mjs',import.meta.url),'utf8');
// Execute the actual parent callback composition, changing only its module transport.
const historySource=workspace.slice(workspace.indexOf('  async function renderHistory(host){'),workspace.indexOf('  async function renderLegacyHistory(host){'))
 .replace("await import('/shared/workspace-analytics.mjs')",'analyticsModule');
const projectHost=new Function('analyticsModule','E','api','initial',`
 let project='P',historyMemory=initial,historyController=null,legacy=0;
 const views={show:()=>{}},discussion={conversation:()=>{},savedTurn:()=>{}},work={open:()=>{}};
 const renderLegacyHistory=()=>{legacy++;};
 ${historySource}
 return {render:renderHistory,capture:()=>historyController.capture(),destroy:()=>historyController.destroy(),memory:()=>historyMemory,legacy:()=>legacy};
`);
const globalSource=await readFile(new URL('../src/laplace/web/static_shared/project-work.mjs',import.meta.url),'utf8');
const globalActivity=globalSource.slice(globalSource.indexOf("  if(app==='activity'){"),globalSource.indexOf("  if(app==='dependencies')"));
const mountGlobal=new (Object.getPrototypeOf(async function(){}).constructor)('root','api','mountSessionAnalytics','location',`const app='activity';${globalActivity}`);
const handle=(project='P',id='TOOLFAIL-F')=>({operation:'author_history',payload:{view:'record',id:'activity:journal:'+id},http:{method:'GET',url:'/authoring/history?'+new URLSearchParams({project,view:'record',id:'activity:journal:'+id})}});
const failure=()=>({project:'P',record_kind:'writing-tool-failure',record:{record:'writing-tool-failure',id:'TOOLFAIL-F',project:'P',turn_id:'WT-original',operation:'read_artifact',error:'Original refusal',resolved_later:false,recovery:{help:{operation:'help',payload:{operation:'read_artifact'}}}}});
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function dom(){const d=installDOM(),create=document.createElement;document.createElement=tag=>{const node=create(tag);node.insertBefore=(child,before)=>{child.parent=node;node.children.splice(node.children.indexOf(before),0,child);};return node;};return d;}
function fixture(d,{rowProject='P',pending=null}={}){
 const calls=[],host=document.createElement('section');host.scrollTop=477;d.body.append(host);
 const request=async path=>{calls.push(path);const q=new URL(path,'http://local').searchParams;
  if(path==='/projects/library')return {projects:[]};
  if(q.get('view')==='record')return pending?pending():failure();
  if(path.startsWith('/authoring/help?'))return {project:'P',inspection:{binding:'recorded-turn',turn_id:'WT-original',mode:'work'},help:{requested_operation:'read_artifact',action:{name:'read_artifact'}}};
  const projection=q.get('projection'),scope=q.get('scope'),next=new URL(path,'http://local');next.searchParams.set('cursor','opaque-page-two');
  return {schema_version:'laplace.session-analytics/1',project:q.get('project')||'',projection,scope,filters:Object.fromEntries([...q].filter(([key])=>!['view','project','limit','cursor'].includes(key))),as_of:'cut-one',read_cut:{revision:'cut-one'},coverage:{selected_metadata_rows:1},items:projection==='sessions'?[]:[{record:'writing-tool-failure',project:rowProject,read_handle:handle(rowProject),error:'Original refusal'}],pagination:{total:2,next_read:q.has('cursor')?null:{http:{method:'GET',url:next.pathname+next.search}}}};
 };
 const initial={activityTab:'trace',analytics:{projection:'trace',scope:{provider:'codex'}}};
 const E=(tag,text='')=>{const node=document.createElement(tag);node.textContent=text;return node;};
 return {host,calls,request,parent:projectHost({mountSessionAnalytics},E,request,initial)};
}

test('actual project Activity opens same inspector, retains filters/cut/page, and keeps explicit Changes & history',async()=>{
 const d=dom();try{const {host,calls,parent}=fixture(d);await parent.render(host);
 await findButton(host,'More recorded activity').click();assert.match(calls.at(-1),/cursor=opaque-page-two/);
 const before=structuredClone(parent.capture()),memory=structuredClone(parent.memory()),analyticsHost=host.children[0],opener=findButton(host,'Inspect recorded basis');
 await opener.click();const dialog=d.dialogs()[0];assert.ok(dialog);assert.equal(host.children[0],analyticsHost);assert.equal(parent.legacy(),0);assert.deepEqual(parent.capture(),before);assert.deepEqual(parent.memory(),memory);
 await findButton(dialog,'Inspect current tool help').click();assert.equal(d.dialogs()[0],dialog);assert.match(dialog.textContent,/original turn WT-original/);
 await findButton(dialog,'Back to recorded failure').click();assert.equal(d.dialogs()[0],dialog);assert.match(dialog.textContent,/Original refusal/);
 await findButton(dialog,'Close').click();assert.equal(document.activeElement,opener);assert.equal(host.scrollTop,477);assert.deepEqual(parent.capture(),before);
 await findButton(host,'Changes & history').click();assert.equal(parent.legacy(),1);assert.equal(parent.memory().activityTab,'changes');assert.equal(d.dialogs().length,0);
 }finally{d.restore();}
});
test('actual project Activity rejects a cross-project row before any exact read',async()=>{
 const d=dom();try{const {host,calls,parent}=fixture(d,{rowProject:'OTHER'});await parent.render(host);await findButton(host,'Inspect recorded basis').click();assert.match(host.textContent,/belongs to another project/);assert.equal(d.dialogs().length,0);assert.equal(calls.filter(path=>new URL(path,'http://local').searchParams.get('view')==='record').length,0);assert.equal(parent.legacy(),0);parent.destroy();}finally{d.restore();}
});
for(const end of ['close','destroy'])test(`actual project Activity ${end} while pending prevents late focus theft`,async()=>{
 const d=dom();try{let release;const {host,parent}=fixture(d,{pending:()=>new Promise(resolve=>{release=resolve;})});await parent.render(host);const opener=findButton(host,'Inspect recorded basis'),pending=opener.click();for(let n=0;n<20&&!release;n++)await tick();assert.ok(release);assert.equal(opener.disabled,false);
 if(end==='close'){await findButton(d.dialogs()[0],'Close').click();assert.equal(document.activeElement,opener);}else parent.destroy();
 const newer=new Node('button');d.body.append(newer);newer.focus();release(failure());await pending;assert.equal(d.dialogs().length,0);assert.equal(document.activeElement,newer);parent.destroy();}finally{d.restore();}
});
test('actual global Activity inspects mixed-project exact rows without navigating away',async()=>{
 const d=dom();try{const {host,request}=fixture(d);const location={href:'unchanged'};await mountGlobal(host,request,mountSessionAnalytics,location);await findButton(host,'Selected activity').click();const opener=findButton(host,'Inspect recorded basis');await opener.click();assert.equal(d.dialogs().length,1);assert.equal(location.href,'unchanged');await findButton(d.dialogs()[0],'Close').click();assert.equal(document.activeElement,opener);}finally{d.restore();}
});
