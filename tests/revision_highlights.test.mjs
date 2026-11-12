import {test} from 'node:test';
import assert from 'node:assert/strict';
import {revisionTextDiff,revisionBlockDiff} from '../src/laplace/web/static_shared/manuscript-editing.mjs';

const snippets=(text,spans)=>spans.map(span=>text.slice(span.start,span.end));

test('prose additions and replacements mark changed wording but leave shared words untouched',()=>{
  const before='The stable claim holds here.';
  const after='The stable central result holds here.';
  const diff=revisionTextDiff(before,after);
  assert.deepEqual(snippets(before,diff.before),['claim']);
  assert.deepEqual(snippets(after,diff.after).map(value=>value.trim()),['central result']);
  assert.ok(!snippets(after,diff.after).join('').includes('stable'));
  assert.ok(!snippets(after,diff.after).join('').includes('holds'));
});

test('a deleted clause has only a deletion span',()=>{
  const before='The bound is finite under the stated assumption.';
  const after='The bound is finite.';
  const diff=revisionTextDiff(before,after);
  assert.equal(diff.after.length,0);
  assert.deepEqual(snippets(before,diff.before),[' under the stated assumption']);
});

test('grapheme clusters are never split at a revision boundary',()=>{
  const before='A 👩‍🔬 result';
  const after='A 🧑‍🔬 result';
  const diff=revisionTextDiff(before,after);
  assert.deepEqual(snippets(before,diff.before),['👩‍🔬']);
  assert.deepEqual(snippets(after,diff.after),['🧑‍🔬']);
});

test('a reference-key change marks the whole reference atom even when its rendered number is unchanged',()=>{
  const before='See 4 for the proof.',after='See 4 for the proof.';
  const oldRef={start:4,end:5,key:'ref:eq:old'},newRef={start:4,end:5,key:'ref:eq:new'};
  const diff=revisionTextDiff(before,after,[oldRef],[newRef]);
  assert.deepEqual(diff,{before:[{start:4,end:5}],after:[{start:4,end:5}]});
});

test('block alignment preserves unchanged paragraphs and treats changed equations atomically',()=>{
  const before=[
    {kind:'para',text:'Unchanged explanation.',atoms:[]},
    {kind:'equation',text:'E = mc²',atoms:[{start:0,end:7,key:'math:E = mc^2'}]},
    {kind:'para',text:'A removable aside.',atoms:[]},
  ];
  const after=[
    {kind:'para',text:'Unchanged explanation.',atoms:[]},
    {kind:'equation',text:'E = ħω',atoms:[{start:0,end:6,key:'math:E = \\hbar\\omega'}]},
  ];
  const diff=revisionBlockDiff(before,after);
  assert.deepEqual(diff.before[0],[]);
  assert.deepEqual(diff.after[0],[]);
  assert.deepEqual(diff.before[1],[{start:0,end:7}]);
  assert.deepEqual(diff.after[1],[{start:0,end:6}]);
  assert.deepEqual(diff.before[2],[{start:0,end:18}]);
});
