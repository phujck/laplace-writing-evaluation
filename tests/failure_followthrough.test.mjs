import test from 'node:test';
import assert from 'node:assert/strict';
import {installDOM,Node,findButton} from './helpers/evidence_reader_harness.mjs';
import {turnFailures,failureAttemptSummary,WorkspaceSession} from '../src/laplace/web/static_shared/workspace-session.mjs';
import {renderRecordedRecovery,inspectRecoveryRead} from '../src/laplace/web/static_shared/workspace-analytics.mjs';
import {openSavedTurn} from '../src/laplace/web/static_shared/workspace-material.mjs';
const handle=(id='ACTION-bibliography',project='P')=>({operation:'author_history',payload:{view:'record',id:'activity:journal:'+id},http:{method:'GET',url:'/authoring/history?'+new URLSearchParams({project,view:'record',id:'activity:journal:'+id})}});
const related=()=>({action_id:'ACTION-bibliography',operation:'edit',target:'paper.tex',basis:'same_operation_target',read_handle:handle()});
const failure=()=>({record:'writing-tool-failure',id:'FAIL-claim',project:'P',turn_id:'WT-original',operation:'edit',payload:{file:'paper.tex'},error:'Claim edit refused: source changed',resolved_later:true});
const exactAction=()=>({project:'P',record_kind:'writing-tool-action',record:{record:'writing-tool-action',id:'ACTION-bibliography',project:'P',turn_id:'WT-original',operation:'edit',payload:{file:'paper.tex',edits:[{file:'paper.tex',line_start:99,replacement:'Bibliography punctuation only.'}]},outcome:{ok:true}}});
const disclose=(host,label)=>{const node=host.all().find(n=>n.tag==='details'&&n.children[0]?.textContent===label);assert.ok(node,label);node.open=true;node.ontoggle?.();return node;};

test('current read recovery and related metadata override no immutable legacy records or task standing',()=>{
 const raw={...failure(),related_action:related()},before=JSON.stringify(raw);const projected=turnFailures({tool_failures:[{record:raw,related_action:null,recovery_read:null}]})[0];assert.equal(projected.resolved_later,false);assert.equal(projected.related_action,null);assert.equal(JSON.stringify(raw),before);
 assert.equal(failureAttemptSummary({failure_count:3,read_recovery_count:1,related_action_count:2}),'3 failed attempts · 1 with recovery reads · 2 linked to later actions');assert.equal(failureAttemptSummary({failure_count:1,resolved_count:99,unresolved_count:0}),'1 failed attempt');
});

test('one shared follow-through view opens the issued exact action only on request and retains draft/focus',async()=>{
 const d=installDOM();try{const host=new Node('article');host.scrollTop=71;d.body.append(host);const calls=[],row={...failure(),related_action:related()},before=JSON.stringify(row);
 renderRecordedRecovery(host,row,{project:'P',turnId:'WT-original',onInspect:(read,options)=>inspectRecoveryRead(read,{request:async path=>{calls.push(path);return exactAction();},project:'P',...options})});
 assert.match(host.textContent,/Historical failed attempt/);assert.doesNotMatch(host.textContent,/succeeded later|successful retry|unresolved task/);assert.equal(calls.length,0);const button=findButton(host,'Later edit to paper.tex');assert.ok(button);await button.click();assert.equal(calls.length,1);assert.equal(calls[0],row.related_action.read_handle.http.url);assert.match(d.dialogs()[0].textContent,/ACTION-bibliography/);assert.match(d.dialogs()[0].textContent,/Bibliography punctuation only/);await findButton(d.dialogs()[0],'Close').click();assert.equal(document.activeElement,button);assert.equal(host.scrollTop,71);assert.equal(d.editor.value,'UNSAVED manuscript');assert.equal(JSON.stringify(row),before);
 }finally{d.restore();}
});

test('contradictory action/project/HTTP references remain readable data without a link or guessed target',()=>{
 const d=installDOM();try{for(const alter of [r=>r.project='OTHER',r=>r.turn_id='OTHER',r=>r.related_action.action_id='OTHER',r=>r.related_action.read_handle.operation='source',r=>r.related_action.read_handle.http.method='POST',r=>r.related_action.read_handle=handle('ACTION-bibliography','OTHER'),r=>delete r.related_action.read_handle.http]){
 const row={...failure(),related_action:related()};alter(row);const host=new Node('article'),calls=[];renderRecordedRecovery(host,row,{project:'P',turnId:'WT-original',onInspect:r=>calls.push(r)});assert.equal(findButton(host,'Later edit to paper.tex'),undefined);assert.match(host.textContent,/Related action inspection is unavailable/);assert.equal(calls.length,0);assert.ok(host.all().some(n=>n.tag==='summary'&&n.textContent==='Related action reference'));
 }}finally{d.restore();}
});

test('exact read completion stays distinct from help inspection despite old resolved flags',()=>{
 const d=installDOM();try{for(const completes of [true,false]){const row={...failure(),recovery_read:{read_id:'READ-public',recovers_read_goal:completes,basis:'Exact retained recovery handle',read_handle:handle('READ-public')}};const host=new Node('article');renderRecordedRecovery(host,row,{project:'P',turnId:'WT-original'});assert.match(host.textContent,completes?/Recovery read completed/:/Recovery read inspected/);assert.equal(turnFailures({tool_failures:[row]})[0].resolved_later,completes);assert.doesNotMatch(host.textContent,/succeeded later|matching attempt succeeded/);}}
 finally{d.restore();}
});

test('Audit lazy failures consume the same related action and fetch no action until its link opens',async()=>{
 const d=installDOM();try{const calls=[],row=failure();const request=async path=>{calls.push(path);const q=new URL(path,'http://local').searchParams;if(q.get('view')==='summary')return {project:'P',turn:{id:'WT-original',session_id:'WS-original',text:'Public original request.',failure_count:1,related_action_count:1,reply:{display_text:'A failed attempt stays historical.'}}};if(q.get('view')==='failures')return {project:'P',turn_id:'WT-original',view:'failures',items:[{record:row,related_action:related(),recovery_read:null,resolved_later:false}],pagination:{total:1,next_offset:null}};if(q.get('view')==='controls')return {items:[],pagination:{next_offset:null}};return exactAction();};
 const dialog=await openSavedTurn({project:'P',turnId:'WT-original',focusView:'failures',request});assert.equal(calls.filter(x=>x.startsWith('/authoring/history')).length,0);assert.match(dialog.textContent,/Historical failed attempt/);assert.doesNotMatch(dialog.textContent,/matching attempt succeeded|No matching successful retry/);const link=findButton(dialog,'Later edit to paper.tex');assert.ok(link);await link.click();assert.equal(calls.filter(x=>x.startsWith('/authoring/history')).length,1);assert.match(d.dialogs().at(-1).textContent,/ACTION-bibliography/);const child=d.dialogs().at(-1);dialog.onclose();assert.equal(child.open,true,'deferred replaced-parent close must not close its child');assert.match(child.textContent,/ACTION-bibliography/);d.dialogs().forEach(n=>n.close());
 }finally{d.restore();}
});

// A replaced saved-turn panel is on the shared inspector trail, while its old DOM is gone.
test('related inspection retains selected lineage after its original host is replaced',async()=>{
 const d=installDOM();try{const host=new Node('article');d.body.append(host);let selected=true,called=0;
 renderRecordedRecovery(host,{...failure(),related_action:related()},{project:'P',turnId:'WT-original',isCurrent:()=>selected,onInspect:async(_read,options)=>{called++;host.isConnected=false;assert.equal(options.isCurrent(),true);selected=false;assert.equal(options.isCurrent(),false);}});
 await findButton(host,'Later edit to paper.tex').click();assert.equal(called,1);await findButton(host,'Later edit to paper.tex').click();assert.equal(called,1);
 }finally{d.restore();}
});
