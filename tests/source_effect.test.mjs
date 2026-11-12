import test from 'node:test';
import assert from 'node:assert/strict';
import {sourceEffectDisposition,requireSourceCompletion,savedActionSourceEffect,savedFailureSourceEffect} from '../src/laplace/web/static_shared/source-effect.mjs';
import {turnCompletionStatus} from '../src/laplace/web/static_shared/workspace-session.mjs';

import {fixtures} from './helpers/source_effect_fixture.mjs';

for (const [name, expected] of Object.entries({unchanged:'UNCHANGED',committed:'COMMITTED',incomplete:'COMMITTED',rollback:'ROLLED_BACK',partial:'PARTIAL',unproved:'UNPROVED',unchanged_incomplete:'UNCHANGED'})) {
  test(`actual owner ${name} preserves physical fate through its reached consumers`, () => {
    const packet=fixtures[name];
    for (const result of [packet.result,packet.native,packet.action].filter(Boolean)) {
      const disposition=sourceEffectDisposition(result,{project:'book',selectionIdentity:'sha256:'+'b'.repeat(64)});
      assert.equal(disposition.state,expected);
      assert.equal(disposition.acknowledged,['unchanged','committed'].includes(name));
      if(!disposition.acknowledged)assert.throws(()=>requireSourceCompletion(result),/incomplete|rolled back|unproved/);
    }
  });
}
test('optional maintenance settles source while required failure explicitly reports landed bytes',()=>{
  assert.equal(requireSourceCompletion(fixtures.optional.result).acknowledged,true);
  const incomplete=sourceEffectDisposition(fixtures.incomplete.result);
  assert.equal(incomplete.sourceLanded,true);
  assert.match(incomplete.message,/Source was saved.*incomplete/);
  assert.equal(incomplete.suppressRetry,true);
  assert.match(turnCompletionStatus({status:'completed',actions:[{project:'book',outcome:fixtures.incomplete.action}]}).text,/Source was saved/);
});
test('refusal and legacy aliases remain distinct; crossed receipt and empty proof cannot settle',()=>{
  assert.equal(sourceEffectDisposition({error:'refused',reason:'source-revision-conflict'}),null);
  assert.equal(sourceEffectDisposition({source_applied:true,source_effect_retained:true,receipts:[{source_effect:'UNPROVED'}]}),null);
  assert.throws(()=>sourceEffectDisposition(fixtures.committed.result,{project:'other'}),/could not be verified/);
  const malformed=structuredClone(fixtures.committed.result);malformed.source_effect.files=[];
  assert.throws(()=>requireSourceCompletion(malformed),/could not be verified/);
});

test('saved action envelope uses its explicit owner outcome without recursively scanning nested failure strings',()=>{
 const row={record:'writing-tool-action',project:'book',outcome:fixtures.incomplete.action};
 assert.equal(savedActionSourceEffect(row).state,'COMMITTED');
 assert.equal(savedActionSourceEffect(row).complete,false);
 assert.equal(savedActionSourceEffect({outcome:{receipts:[{source_effect:'UNPROVED'}]}}),null);
});

test('shared project transport prevents figure, bibliography and proposal success callbacks on incomplete source result',async()=>{
 const {projectRequest}=await import('../src/laplace/web/static_shared/workspace-session.mjs');
 const previousFetch=globalThis.fetch;
 try{
  for(const route of ['/visuals/place','/references/bind','/authoring/proposal-decision']){
   let calls=0;
   globalThis.fetch=async()=>{calls++;return {ok:true,status:200,headers:{get:()=> 'application/json'},json:async()=>fixtures.incomplete.result};};
   await assert.rejects(projectRequest(route,{project:'book'}),/Source was saved.*incomplete/);
   assert.equal(calls,1);
  }
 }finally{globalThis.fetch=previousFetch;}
});

test('actual admitted native applications and persisted action envelopes keep identical source truth',async()=>{
 const {readFile}=await import('node:fs/promises');
 const actual=JSON.parse(await readFile(new URL('./fixtures/source-effect-native-20261011.json',import.meta.url),'utf8'));
 for(const [name,packet] of Object.entries(actual)){
  const native=sourceEffectDisposition(packet.native_result,{project:'fixture'});
  const saved=savedActionSourceEffect(packet.saved_action,{project:'fixture'});
  assert.deepEqual(native.effect,saved.effect);
  assert.deepEqual(native.effect,packet.native_result.action_receipt.source_effect);
  assert.equal(native.state,'COMMITTED');
  assert.equal(native.complete,name==='committed');
  const status=turnCompletionStatus({status:'completed',actions:[packet.saved_action]});
  if(name==='tracking_unproved')assert.match(status.text,/Source was saved.*incomplete/);
 }
});

test('an error carrying a complete source effect never invites replay',async()=>{
 const {sourceEffectFromError}=await import('../src/laplace/web/static_shared/source-effect.mjs');
 const disposition=sourceEffectFromError({result:fixtures.committed.result});
 assert.equal(disposition.sourceLanded,true);
 assert.equal(disposition.suppressRetry,true);
 assert.match(disposition.message,/Source saved.*do not repeat/);
});

test('embedded visual outcome bridge preserves the exact receipt for document currentness',async()=>{
 const {readFile}=await import('node:fs/promises');
 const source=await readFile(new URL('../src/laplace/web/static_shared/writing-panel.mjs',import.meta.url),'utf8');
 const start=source.indexOf("window.walk.on('source-outcome',");
 const end=source.indexOf("window.walk.on('source-warning',",start);
 assert.ok(start>=0&&end>start);
 let listener,message;
 new Function('window','location',source.slice(start,end))({walk:{on:(name,fn)=>{assert.equal(name,'source-outcome');listener=fn;}},parent:{postMessage:value=>{message=value;}}},{origin:'http://fixture'});
 listener({source_effect:fixtures.incomplete.result.source_effect});
 assert.equal(message.type,'laplace:source-outcome');
 assert.equal(message.source_effect,fixtures.incomplete.result.source_effect);
});

test('owner completion invariant is mirrored and corrupt contradictory aggregates cannot acknowledge',()=>{
 assert.equal(fixtures.constructor_invariant.complete,false);
 assert.equal(fixtures.constructor_invariant.state,'COMMITTED');
 for(const status of ['FAILED','UNPROVED','COMPENSATED']){
  const result=structuredClone(fixtures.committed.result);
  result.source_effect.follow_through.required=[{owner:'fixture-domain',status}];
  assert.throws(()=>requireSourceCompletion(result),/could not be verified/);
 }
 for(const malformed of ['UNPROVED',null,false,0])assert.throws(()=>sourceEffectDisposition({source_effect:malformed}),/could not be verified/);
 assert.equal(sourceEffectDisposition({receipts:[{source_effect:'UNPROVED'}],rollbacks:[{source_effect:'UNPROVED'}]}),null);
});
test('actual banked native failure retains one recovery receipt and reports landed source in later UI history',async()=>{
 const {turnFailures}=await import('../src/laplace/web/static_shared/workspace-session.mjs');
 const row=fixtures.saved_failure;
 assert.equal(Object.hasOwn(row,'source_effect'),false);
 const disposition=savedFailureSourceEffect(row);
 assert.equal(disposition.state,'COMMITTED');assert.equal(disposition.complete,false);
 const failure=turnFailures({tool_failures:[row]})[0];
 assert.deepEqual(failure.sourceEffect.effect,row.recovery.source_effect);
 assert.match(turnCompletionStatus({status:'completed',tool_failures:[row]}).text,/Source was saved.*incomplete/);
});

test('real section failure with source rollback survives native response, direct bank and exact History read',async()=>{
 const {readFile}=await import('node:fs/promises');
 const packet=JSON.parse(await readFile(new URL('./fixtures/source-effect-failure-20261011.json',import.meta.url),'utf8'));
 const immediate=sourceEffectDisposition(packet.immediate);
 const saved=savedFailureSourceEffect(packet.saved_failure);
 const history=savedFailureSourceEffect(packet.history_exact.record);
 assert.equal(immediate.state,'ROLLED_BACK');assert.equal(immediate.complete,false);
 assert.deepEqual(saved.effect,immediate.effect);assert.deepEqual(history.effect,immediate.effect);
 assert.match(turnCompletionStatus({status:'completed',tool_failures:[packet.saved_failure]}).text,/rolled back/);
});

test('explicit failed physical observation cannot be acknowledged by forged equal pins',()=>{
 for(const error of ['cannot observe','',{}]){
  const value=structuredClone(fixtures.committed.result);
  value.source_effect.files[0].observation_error=error;
  assert.throws(()=>requireSourceCompletion(value),/could not be verified/);
 }
 const value=structuredClone(fixtures.unproved.result);
 value.source_effect.files[0].observation_error={};
 assert.throws(()=>sourceEffectDisposition(value),/could not be verified/);
});

test('optional view follow-through preserves acknowledged source and never runs for incomplete effects',async()=>{
 const {afterSourceWrite}=await import('../src/laplace/web/static_shared/source-effect.mjs');
 let calls=0;
 await assert.rejects(afterSourceWrite(fixtures.incomplete.result,async()=>{calls++;}),/incomplete/);
 assert.equal(calls,0);
 await assert.rejects(afterSourceWrite(fixtures.committed.result,async()=>{calls++;throw Error('view unavailable');}),error=>{
  assert.equal(error.result,fixtures.committed.result);assert.equal(error.effectAcknowledged,true);
  assert.match(error.message,/Source saved.*Do not repeat/);return true;
 });
 assert.equal(calls,1);
});
