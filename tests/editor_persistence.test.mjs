import assert from 'node:assert/strict';
import {test} from 'node:test';
import {normalizeDraftRows,mergeDraftRows} from '../src/laplace/web/static_shared/manuscript-editing.mjs';
const row=(id,text='Draft',draft_id=id)=>[id,{draft_id,pristine:'Source',text,src:{file:'main.tex',lineStart:2},tex:'Source'}];
test('an empty or unrelated tab cannot erase drafts it never loaded',()=>{
 const remote=[row('a')];assert.deepEqual(mergeDraftRows([],[],remote).rows,remote);
 const merged=mergeDraftRows([],[row('b','Second draft')],remote);assert.deepEqual(new Set(merged.rows.map(([,entry])=>entry.text)),new Set(['Draft','Second draft']));
});
test('clearing a draft removes only the exact stored version this tab held',()=>{
 const previous=[row('a')];assert.equal(mergeDraftRows(previous,[],previous).rows.length,0);
 const newer=[row('a','New text from another tab')];assert.deepEqual(mergeDraftRows(previous,[],newer).rows,newer);
 assert.equal(mergeDraftRows(previous,previous,[]).rows.length,0,'unchanged stale state cannot resurrect a cleared draft');
});
test('simultaneous versions survive as explicit conflicts and repeated saves do not fork again',()=>{
 const previous=[row('a')],mine=[row('a','My revision')],other=[row('a','Other revision')];
 const result=mergeDraftRows(previous,mine,other,()=> 'fork');assert.equal(result.conflicts,1);assert.equal(result.rows.length,2);assert.ok(result.rows.every(([,entry])=>entry.conflict&&entry.unplaced));assert.deepEqual(new Set(result.rows.map(([,entry])=>entry.text)),new Set(['My revision','Other revision']));
 const savedAgain=mergeDraftRows(result.local,result.local,result.rows,()=>{throw Error('unexpected second fork');});assert.equal(savedAgain.rows.length,2);assert.equal(savedAgain.conflicts,0);assert.equal(other[0][1].conflict,undefined,'caller snapshots are not mutated');
});
test('a draft edited after another tab cleared it becomes a new version',()=>{
 const result=mergeDraftRows([row('a')],[row('a','Continued typing')],[],()=> 'continued');assert.equal(result.rows[0][1].draft_id,'continued');assert.equal(result.rows[0][1].text,'Continued typing');
});
test('legacy draft rows normalize without dropping content and corrupt rows are rejected',()=>{
 const old=[['main.tex#b7',{pristine:'Old',text:'New'}]];assert.equal(normalizeDraftRows(old)[0][1].draft_id,'legacy:main.tex#b7');assert.throws(()=>normalizeDraftRows([['a',{text:'Missing baseline'}]]),/unreadable/);
});
