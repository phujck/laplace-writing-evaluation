import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {walkSource,walkDeclarations} from './helpers/walk_source.mjs';
const source=walkSource();
const body=walkDeclarations('commitAll');
function editor(order){
 const blocks=new Map(['a','b'].map((id,index)=>[id,{id,bodyEl:{text:'new '+id},el:{dataset:{}},src:{file:id+'.tex',lineStart:index+2,lineEnd:index+2}}]));
 const e={assignBasis:(t,b)=>Object.assign(t,{tex:b.tex,src:b.src,expectedSelection:b.expectedSelection,expected:b.expected}),captureBasis:b=>({tex:b.tex||'',src:b.src,expectedSelection:undefined,expected:[]}),pendingPresentationSplits:new Map(),NOT_SAVED:{why:''},P:new Map([['b',{pristine:'saved b',text:'new b',src:blocks.get('b').src,draft_id:'draft-b'}]]),E:{blockId:'a',pristine:'saved a',dirty:true},C:{},cardNote:null,blockById:blocks,srcOf:b=>b?.src||{},hostText:host=>host.text,setEditScope(){},paintParked(){},renderBand(){},paintDeposits(){},events:[],calls:[],emit(name,value){this.events.push({name,value});}};
 e.emit=(name,value)=>e.events.push({name,value});
 e.parkEdit=b=>{e.P.set(b.id,{pristine:e.E.pristine,text:b.bodyEl.text,src:b.src,draft_id:'draft-'+b.id});e.E.blockId='';e.E.dirty=false;};
 e.clearEdit=b=>{e.P.delete(b.id);e.E.blockId='';e.E.dirty=false;};
 let refuse=true;
 e.commitEdit=async()=>{const id=e.E.blockId;e.calls.push(id);if(refuse&&id===order){return null;}e.clearEdit(blocks.get(id));return {id:'receipt-'+id,kind:'rewrite',applied:true};};
 e.allowRetry=()=>{refuse=false;};e.INFLIGHT=new Set();e.QUEUE={why:''};vm.createContext(e);vm.runInContext(body+';this.save=commitAll;',e);return e;
}
for(const refused of ['a','b'])test('batch preserves actual success and refused draft in '+(refused==='a'?'failure→success':'success→failure')+' order',async()=>{
 const e=editor(refused),result=await e.save();
 assert.equal(result.applied.length,1);assert.equal(result.refused.length,1);assert.equal(result.remaining.length,1);
 assert.match(result.message,/Saved 1 edit in/);assert.match(result.message,/Not saved: 1 edit in/);assert.match(result.message,/Kept 1 unsaved draft/);
 assert.doesNotMatch(result.message,/nothing was banked/);assert.equal(e.P.has(refused),true);assert.equal(e.P.size,1);
 assert.equal(e.events.at(-1).value.text,result.message);
 e.allowRetry();const retry=await e.save();assert.equal(retry.applied.length,1);assert.equal(retry.remaining.length,0);
 assert.equal(e.calls.filter(id=>id!==refused).length,1,'successful receipt is never replayed');assert.equal(e.P.size,0);
});
test('unchanged pending receipt is retained without replay or false saved claim',async()=>{const e=editor('a');e.E={blockId:'',dirty:false};e.P=new Map([['b',{pendingRow:'pending-1',text_at_bank:'new b',src:e.blockById.get('b').src}]]);const result=await e.save();assert.equal(e.calls.length,0);assert.equal(result.applied.length,0);assert.equal(e.P.size,1);assert.equal(result.retained_pending.length,1);assert.match(result.message,/pending recorded edit remains unapplied/);assert.doesNotMatch(result.message,/Saved /);});

test("batch does not supersede a provider-owner edit whose save receipt is still in flight",async()=>{const e=editor("a");e.E.committing=true;const result=await e.save();assert.equal(result.inflight,true);assert.equal(e.calls.length,0);assert.equal(e.P.size,1);assert.equal(e.E.dirty,true);assert.match(result.message,/already being saved/);});
test('a refused draft remapped by a later successful source refresh is not replayed within the batch',async()=>{
 const e=editor('a'),commit=e.commitEdit;e.commitEdit=async()=>{const row=await commit();if(row?.applied&&e.P.has('a')){const old=e.blockById.get('a');e.blockById.set('a-remapped',{...old,id:'a-remapped'});e.P.set('a-remapped',e.P.get('a'));e.P.delete('a');}return row;};
 const result=await e.save();assert.deepEqual(e.calls,['a','b']);assert.equal(result.remaining.length,1);assert.equal(e.P.has('a-remapped'),true);
});


test('successful saved source with failed retry retirement retains explicit warning in final batch status',async()=>{
 const e=editor('none'),commit=e.commitEdit;e.commitEdit=async()=>({...await commit(),retry_warning:'Source applied; pending FB-first unresolved. Do not repeat effect.'});const result=await e.save();assert.equal(result.applied.length,2);assert.equal(result.refused.length,0);assert.match(result.message,/Saved 2/);assert.match(result.message,/FB-first unresolved/);assert.equal(e.events.at(-1).value.text,result.message);assert.equal(e.P.size,0);
});
