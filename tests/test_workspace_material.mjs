import test from 'node:test';
import assert from 'node:assert/strict';
import {turnObservation,artifactReaderOptions,taskPrerequisites,terminalWork} from '../src/laplace/web/static_shared/workspace-material.mjs';
test('reply and missing outcome never become task completion or assumed liveness',()=>{
  assert.match(turnObservation({id:'t',reply:{status:'completed'}}),/work completion is separate/);
  assert.match(turnObservation({id:'t'}),/execution status unknown/);
  assert.match(turnObservation({id:'t'},{id:'other'}),/unknown/);
  assert.match(turnObservation({id:'t'},{id:'t'}),/execution owner/);
});
test('artifact reader receives recorded pin and scope rather than inferred currentness',()=>{
  const pin='ab'.repeat(32);
  const value=artifactReaderOptions({id:'ART-a',scope:'project',recorded_revision:'sha256:'+pin});
  assert.equal(value.expectedSha256,pin);assert.equal(value.scope,'project');assert.equal(value.artifactOwner,'writing-artifact');
  assert.match(value.notice,/must match/);
  // P2 repair1: a malformed recorded pin is not a pin; the owner and receipt stay, no revision is implied
  const malformed=artifactReaderOptions({id:'ART-a',scope:'project',recorded_revision:'sha256:abc'});
  assert.deepEqual([malformed.expectedSha256,malformed.artifactId,malformed.artifactOwner],[undefined,'ART-a','writing-artifact']);
  assert.match(malformed.notice,/historical revision is unavailable/);
});
test('prerequisites keep missing owner rows explicit and terminal lifecycle vocabulary intact',()=>{
  const value=taskPrerequisites([{id:'b',title:'Dependent',depends_on:['a','gone']},{id:'a',title:'Source',status:'done'}]);
  assert.deepEqual(value[0].prerequisites,[{id:'a',title:'Source',status:'done'},{id:'gone',title:'gone',status:'unavailable'}]);
  assert.equal(terminalWork({status:'cancelled'}),true);assert.equal(terminalWork({status:'blocked'}),false);
});
