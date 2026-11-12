import test from 'node:test';import assert from 'node:assert/strict';import {readFile} from 'node:fs/promises';
import {register} from 'node:module';register(new URL('./helpers/shared_resolve.mjs',import.meta.url));
// the binding candidates are the real facade export (workspace-research.mjs, M5 S2 F1)
const {researchBindingCandidates}=await import('../src/laplace/web/static_shared/workspace.mjs');
test('result binding offers actual logical claims, not the first citation or raw equation',()=>{const rows=[{id:'cite:first',kind:'citation',label:'First citation'},{id:'eq:raw',kind:'equation',label:'\\frac{x}{y}'},{id:'thm:bound',kind:'theorem',label:'A long theorem statement '.repeat(20)},{id:'def:unit',kind:'definition',label:'Unit'}];assert.deepEqual(researchBindingCandidates(rows).map(row=>row.id),['thm:bound','def:unit']);assert.deepEqual(researchBindingCandidates(rows,'bound').map(row=>row.id),['thm:bound']);});
