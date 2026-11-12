import test from 'node:test';
import assert from 'node:assert/strict';
import {installDOM,Node} from './helpers/evidence_reader_harness.mjs';
import {WorkspaceSession,turnFailures} from '../src/laplace/web/static_shared/workspace-session.mjs';
import {openSavedTurn} from '../src/laplace/web/static_shared/workspace-material.mjs';
import {inspectRecoveryRead} from '../src/laplace/web/static_shared/workspace-analytics.mjs';
import {recordedRecoveryRead} from '../src/laplace/web/static_shared/writing-owner-read.mjs';

const readHandle=(project='P',id='READ-r')=>({operation:'author_history',payload:{view:'record',id:'activity:journal:'+id},http:{method:'GET',url:'/authoring/history?'+new URLSearchParams({project,view:'record',id:'activity:journal:'+id})}});
const failure=()=>({record:'writing-tool-failure',id:'TOOLFAIL-original',project:'P',turn_id:'WT-original',operation:'read_artifact',error:'Exact read refused',resolved_later:false,
 recovery:{help:{operation:'help',payload:{operation:'read_artifact'}},next_reads:[{operation:'read_artifact',payload:{id:'ART-original'}}]},
 recovery_read:{read_id:'READ-r',read_handle:readHandle(),basis:'Exact retained recovery handle',recovers_read_goal:false}});
const exactRead=()=>({project:'P',record_kind:'writing-tool-read',record:{record:'writing-tool-read',id:'READ-r',project:'P',turn_id:'WT-original',operation:'help',payload:{operation:'read_artifact'}}});
const help=()=>({project:'P',inspection:{binding:'recorded-turn',turn_id:'WT-original',mode:'work'},help:{requested_operation:'read_artifact',action:{name:'read_artifact'}}});
const find=(node,label)=>node.all().find(n=>n.tag==='button'&&n.textContent===label);
const disclose=(node,label)=>{const detail=node.all().find(n=>n.tag==='details'&&n.children[0]?.textContent===label);assert.ok(detail,label);detail.open=true;detail.ontoggle?.();return detail;};
const tick=()=>new Promise(resolve=>setImmediate(resolve));
async function until(predicate){for(let n=0;n<20&&!predicate();n++)await tick();assert.ok(predicate());}
function inline(d,row=failure(),overrides={}){
 const host=new Node('article');host.scrollTop=71;d.body.append(host);
 const session=Object.assign(Object.create(WorkspaceSession.prototype),{project:'P',session:'WS-original',viewEpoch:1,guard:fn=>fn(),compose(){},...overrides});
 session.failures(host,{id:'WT-original',tool_failures:[row]});
 disclose(host,'1 failed attempt');disclose(host,'Error and follow-up');
 return {session,host};
}

test('canonical recovery transport validates native/HTTP/project/read identity without guessing routes',()=>{
 const row=failure();assert.equal(recordedRecoveryRead(row,{project:'P',turnId:'WT-original'}).id,'activity:journal:READ-r');
 for(const change of [r=>r.project='OTHER',r=>r.turn_id='WT-other',r=>r.recovery_read.read_id='READ-other',r=>r.recovery_read.read_handle.http.method='POST',r=>r.recovery_read.read_handle.payload.id='activity:journal:TOOLFAIL-wrong',r=>delete r.recovery_read.read_handle.http,r=>r.recovery_read.read_handle.http.url+='+garbage',r=>r.recovery_read.read_handle.http.url='/authoring/history?project=OTHER&view=record&id=activity%3Ajournal%3AREAD-r']){
  const changed=structuredClone(row);change(changed);assert.equal(recordedRecoveryRead(changed,{project:'P',turnId:'WT-original'}),null);
 }
 assert.equal(turnFailures({tool_failures:[row]})[0].turn_id,'WT-original');assert.equal(turnFailures({tool_failures:[row]})[0].project,'P');
});

test('actual inline failure controls open exact READ and original-turn current help; inspection remains unresolved',async()=>{
 const d=installDOM();try{const row=failure(),before=JSON.stringify(row),calls=[];
 const request=async path=>{calls.push(path);return path.startsWith('/authoring/help?')?help():exactRead();};
 const {host}=inline(d,row,{onOpenOwner:(read,label,options)=>{document.activeElement=d.body;return inspectRecoveryRead(read,{request,project:'P',...options});}});
 assert.equal(calls.length,0);assert.match(host.textContent,/Recovery read inspected/);
 const recorded=find(host,'Open recorded recovery read');await recorded.click();let dialog=d.dialogs()[0];assert.match(dialog.textContent,/READ-r/);assert.match(calls[0],/id=activity%3Ajournal%3AREAD-r/);
 await find(dialog,'Close').click();assert.equal(document.activeElement,recorded);assert.equal(host.scrollTop,71);
 const current=find(host,'Inspect current tool help');await current.click();dialog=d.dialogs()[0];assert.match(dialog.textContent,/original turn WT-original/);assert.match(dialog.textContent,/admitted mode work/);
 assert.match(calls[1],/turn_id=WT-original/);assert.ok(!calls[1].includes('mode='));await find(dialog,'Close').click();assert.equal(document.activeElement,current);
 assert.equal(JSON.stringify(row),before);assert.match(host.textContent,/Recovery read inspected/);assert.equal(d.dialogs().length,0);
 }finally{d.restore();}
});

test('actual saved-turn failure consumes scoped owner page and uses the same exact recovery inspector',async()=>{
 const d=installDOM();try{const row=failure(),calls=[];const request=async path=>{calls.push(path);const q=new URL(path,'http://localhost').searchParams;
  if(path.startsWith('/authoring/help?'))return help();if(q.get('view')==='record')return exactRead();
  if(q.get('view')==='summary')return {project:'P',turn:{id:'WT-original',session_id:'WS-original',text:'Original request',failure_count:1}};
  return {project:'P',turn_id:'WT-original',view:'failures',items:[{origin:'tool-failure',record:row,resolved_later:false,recovery_read:row.recovery_read}],pagination:{next_offset:null,total:1}};
 };
 const turn=await openSavedTurn({project:'P',turnId:'WT-original',focusView:'failures',request});assert.equal(calls.length,2);
 // one modal (M5 C3): the recovery read REPLACES the saved-turn panel and carries Back to it; Close on the nested reader is Back
 const open=find(turn,'Open recorded recovery read');await open.click();assert.equal(d.dialogs().length,1);const inspected=d.dialogs()[0];assert.notEqual(inspected,turn);assert.match(inspected.textContent,/READ-r/);assert.equal(inspected.children[0].textContent,'Back to Saved turn');
 await find(inspected,'Close').click();await new Promise(resolve=>setTimeout(resolve,0));assert.equal(d.dialogs().length,1);const reopened=d.dialogs()[0];assert.notEqual(reopened,turn,'the saved turn was reopened through its door');assert.match(reopened.textContent,/Recovery read inspected/);
 const current=find(reopened,'Inspect current tool help');await current.click();assert.equal(d.dialogs().length,1);assert.match(d.dialogs()[0].textContent,/original turn WT-original/);await find(d.dialogs()[0],'Close').click();await new Promise(resolve=>setTimeout(resolve,0));assert.equal(d.dialogs().length,1);d.dialogs()[0].close();assert.equal(d.dialogs().length,0);assert.equal(document.activeElement,d.editor);
 }finally{d.restore();}
});

test('inline binding mismatch exposes saved data but cannot open a different original project/turn',async()=>{
 const d=installDOM();try{for(const key of ['project','turn_id']){const row=failure();row[key]='OTHER';const opened=[];const {host}=inline(d,row,{onOpenOwner:read=>opened.push(read)});
  assert.equal(find(host,'Open recorded recovery read'),undefined);assert.equal(find(host,'Inspect current tool help'),undefined);assert.match(host.textContent,/binding is unavailable or mismatched/);assert.equal(opened.length,0);
 }}finally{d.restore();}
});

test('pending-close releases exact opener and late success/error cannot reopen or steal newer focus',async()=>{
 for(const rejected of [false,true]){const d=installDOM();try{let settle;const pending=new Promise((resolve,reject)=>settle=rejected?()=>reject(Error('Late scoped error')):()=>resolve(exactRead()));
  const {host}=inline(d,failure(),{onOpenOwner:(read,label,options)=>inspectRecoveryRead(read,{request:()=>pending,project:'P',...options})});
  const open=find(host,'Open recorded recovery read'),completion=open.click();await until(()=>d.dialogs().length===1);assert.equal(open.disabled,false);
  await find(d.dialogs()[0],'Close').click();assert.equal(document.activeElement,open);d.editor.focus();settle();await completion;assert.equal(document.activeElement,d.editor);assert.equal(d.dialogs().length,0);
 }finally{d.restore();}}
});

test('inline namespace switch during pending owner read removes stale inspector without rendering late data',async()=>{
 const d=installDOM();try{let settle;const pending=new Promise(resolve=>settle=resolve);const {session,host}=inline(d,failure(),{onOpenOwner:(read,label,options)=>inspectRecoveryRead(read,{request:()=>pending,project:'P',...options})});
  const click=find(host,'Open recorded recovery read').click();await until(()=>d.dialogs().length===1);session.viewEpoch++;session.session='WS-new';d.editor.focus();settle(exactRead());await click;assert.equal(d.dialogs().length,0);assert.ok(!d.body.textContent.includes('Recorded arguments'));
 }finally{d.restore();}
});


test('inline canonical failure page refuses a different owner scope before offering any read actions',async()=>{
 const d=installDOM(),oldFetch=globalThis.fetch;try{
  globalThis.fetch=async()=>({ok:true,headers:{get:()=> 'application/json'},json:async()=>({project:'OTHER',turn_id:'WT-original',view:'failures',items:[{record:failure()}],pagination:{total:1,next_offset:null}})});
  const host=new Node('article');d.body.append(host);const session=Object.assign(Object.create(WorkspaceSession.prototype),{project:'P',session:'WS-original',viewEpoch:1,guard:fn=>fn(),compose(){}});
  session.failures(host,{id:'WT-original',detail:{turn_id:'WT-original'},failure_count:1});const box=host.all().find(n=>n.tag==='details');box.open=true;await box.ontoggle();
  assert.match(host.textContent,/different project or turn/);assert.equal(find(host,'Open recorded recovery read'),undefined);assert.equal(find(host,'Inspect current tool help'),undefined);
 }finally{globalThis.fetch=oldFetch;d.restore();}
});

test('recorded recovery response must match its exact requested ID and never implies retry success',async()=>{
 const d=installDOM();try{const {host}=inline(d,failure(),{onOpenOwner:(read,label,options)=>inspectRecoveryRead(read,{request:async()=>({...exactRead(),record:{...exactRead().record,id:'READ-other'}}),project:'P',...options})});
  await find(host,'Open recorded recovery read').click();assert.match(d.dialogs()[0].textContent,/different immutable identity/);assert.match(host.textContent,/Recovery read inspected/);await find(d.dialogs()[0],'Close').click();
 }finally{d.restore();}
});

test('closing the saved-turn parent before lazy inspector creation cannot open a late dialog',async()=>{
 const d=installDOM();try{let reads=0;const row=failure(),request=async path=>{const q=new URL(path,'http://localhost').searchParams;
  if(q.get('view')==='summary')return {project:'P',turn:{id:'WT-original',session_id:'WS-original',failure_count:1}};
  if(q.get('view')==='failures')return {project:'P',turn_id:'WT-original',view:'failures',items:[{record:row,recovery_read:row.recovery_read}],pagination:{total:1,next_offset:null}};
  reads++;return exactRead();};
  const parent=await openSavedTurn({project:'P',turnId:'WT-original',focusView:'failures',request});const opening=find(parent,'Open recorded recovery read').click();parent.close();d.editor.focus();await opening;
  assert.equal(reads,0);assert.equal(d.dialogs().length,0);assert.equal(document.activeElement,d.editor);
 }finally{d.restore();}
});

test('saved-turn original namespace is validated before any recovery actions are rendered',async()=>{
 const d=installDOM();try{const dialog=await openSavedTurn({project:'P',turnId:'WT-original',request:async()=>({project:'OTHER',turn:{id:'WT-original',failure_count:1}})});
  assert.match(dialog.textContent,/different project or turn/);assert.equal(find(dialog,'Inspect current tool help'),undefined);dialog.close();
 }finally{d.restore();}
});
