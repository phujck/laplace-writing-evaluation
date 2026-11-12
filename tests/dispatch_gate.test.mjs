import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import test from 'node:test'

import { bindDispatchAgent } from '../scripts/dispatch_gate.mjs'

const sha256 = (bytes) => 'sha256:' + createHash('sha256').update(bytes).digest('hex')
const canonical = (value) => {
  if (value === null || typeof value === 'boolean' || typeof value === 'string' || typeof value === 'number') return JSON.stringify(value)
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']'
  return '{' + Object.keys(value).sort().map((key) => JSON.stringify(key) + ':' + canonical(value[key])).join(',') + '}'
}

const LABEL = 'stage:one'
const PROMPT = 'exact provider prompt'

function fixture() {
  const continuation = {
    schema_version: 'laplace.continuation-admission/1',
    status: 'ADMITTED',
    function: 'ego',
    seat_id: 'ego-seat',
    generation: 'generation:1',
    goal_digest: sha256(Buffer.from('perform exact work')),
    profile_handle: 'sha256:' + 'e'.repeat(64),
    semantic_fold_handle: 'sha256:' + 'd'.repeat(64),
    semantic_source: { commit: 'a'.repeat(40), tree: 'b'.repeat(40) },
    selected: [{ kind: 'atlas-custody', reference: 'sha256:' + 'e'.repeat(64), content_status: 'COMPLETE', content_handle: 'sha256:' + 'f'.repeat(64), current_root: null }],
    fog: [],
    watcher_state: { status: 'NOT-AN-ATTENTION-TURN' },
    reasons: [],
    substantive_work_allowed: true,
    human_conversation_allowed: true,
    authority_effect: 'none',
  }
  continuation.decision_handle = sha256(Buffer.from(canonical(continuation)))
  const turn = {
    schema_version: 'laplace.turn-reconstruction/1',
    status: 'ADMITTED',
    profile_handle: 'sha256:' + 'e'.repeat(64),
    semantic_fold_health_handle: 'sha256:' + 'd'.repeat(64),
    goal_author_turn_digest: sha256(Buffer.from('perform exact work')),
    selected: [{ kind: 'atlas-custody', reference: 'sha256:' + 'e'.repeat(64), content_status: 'COMPLETE', content_handle: 'sha256:' + 'f'.repeat(64) }],
    fog: [],
    claims_with_unknown_context: false,
    read_only: true,
    authority_effect: 'none',
    canonical_authority_write: 'none',
    local_telemetry_effect: 'bounded receipt outside fold',
    continuation_decision: continuation,
  }
  turn.receipt_handle = sha256(Buffer.from(canonical(turn)))
  const reconstruction = {
    kind: 'atlas-object',
    reference: 'node:exact',
    goal: 'perform exact work',
    content_status: 'COMPLETE',
    content: '{"exact":true}',
    content_handle: sha256(Buffer.from('{"exact":true}')),
    read_only: true,
    transition_claim: 'none',
    authority_write: 'none',
    current_root: 'sha256:' + 'a'.repeat(64),
    authority_root: 'sha256:' + 'b'.repeat(64),
    drift_token: { cursor: 7, head_event_id: 'sha256:' + 'c'.repeat(64) },
    integrity_boundary: 'CHECKSUMMED-CRUTCH',
    authenticated: false,
    current: true,
    clean: true,
    authority_suffix_count: 64,
    authority_suffix_limit: 64,
    read_metrics: { suffix_rows_loaded: 64 },
  }
  const claim = {
    schema_version: 'laplace.dispatch-reconstruction-claim/1',
    kind: reconstruction.kind,
    node: reconstruction.reference,
    goal_utf8: reconstruction.goal,
    content_status: reconstruction.content_status,
    content_handle: reconstruction.content_handle,
    read_only: reconstruction.read_only,
    transition_claim: reconstruction.transition_claim,
    authority_write: reconstruction.authority_write,
    current_root: reconstruction.current_root,
    authority_root: reconstruction.authority_root,
    drift_token: reconstruction.drift_token,
    integrity_boundary: reconstruction.integrity_boundary,
  }
  reconstruction.reconstruction_receipt = claim
  reconstruction.reconstruction_receipt_handle = sha256(Buffer.from(canonical(claim)))
  const phase = {
    schema_version: 'laplace.dispatch-reconstruction/1',
    node: reconstruction.reference,
    goal_utf8: reconstruction.goal,
    goal_bytes_hex: Buffer.from(reconstruction.goal).toString('hex'),
    reconstruction_content_handle: reconstruction.content_handle,
    reconstruction_receipt_handle: reconstruction.reconstruction_receipt_handle,
    current_root: reconstruction.current_root,
    authority_root: reconstruction.authority_root,
    drift_token: reconstruction.drift_token,
    worker: 'derive',
    target: reconstruction.reference,
    admission_result: { status: 'ADMITTED', reason: 'EXACT' },
    integrity_boundary: { status: 'CHECKSUMMED-CRUTCH' },
    d2: { status: 'OPEN' },
  }
  phase.receipt_handle = sha256(Buffer.from(canonical(phase)))
  return {
    label: LABEL,
    prompt_handle: sha256(Buffer.from(PROMPT)),
    reconstruction,
    phaseReceipt: phase,
    turnReconstruction: turn,
  }
}

test('exact admission invokes the provider exactly once', async () => {
  const calls = []
  const gated = bindDispatchAgent(async (...args) => { calls.push(args); return 'ok' }, { [LABEL]: fixture() })
  assert.equal(await gated(PROMPT, { label: LABEL, model: 'sonnet' }), 'ok')
  assert.equal(calls.length, 1)
  assert.match(calls[0][0], /TURN RECONSTRUCTION/)
  assert.match(calls[0][0], /laplace\.turn-reconstruction\/1/)
})

for (const [name, alter] of [
  ['missing', () => null],
  ['budget', (a) => { a.reconstruction.content_status = 'BUDGET'; return a }],
  ['content', (a) => { a.reconstruction.content += 'x'; return a }],
  ['claim', (a) => { a.reconstruction.reconstruction_receipt_handle = 'sha256:' + '0'.repeat(64); return a }],
  ['phase', (a) => { a.phaseReceipt.receipt_handle = 'sha256:' + '0'.repeat(64); return a }],
  ['suffix-65', (a) => { a.reconstruction.authority_suffix_count = 65; return a }],
  ['dirty', (a) => { a.reconstruction.clean = false; return a }],
  ['moved', (a) => { a.reconstruction.moved = true; return a }],
  ['ambiguous', (a) => { a.reconstruction.ambiguous = true; return a }],
  ['checkpoint', (a) => { a.reconstruction.current = false; return a }],
  ['suffix-disagreement', (a) => { a.reconstruction.read_metrics.suffix_rows_loaded = 63; return a }],
  ['current-root', (a) => { a.phaseReceipt.current_root = 'sha256:' + '1'.repeat(64); return a }],
  ['authority-root', (a) => { a.phaseReceipt.authority_root = 'sha256:' + '1'.repeat(64); return a }],
  ['drift', (a) => { a.phaseReceipt.drift_token = { cursor: 8 }; return a }],
  ['prompt', (a) => { a.prompt_handle = 'sha256:' + '1'.repeat(64); return a }],
  ['turn-missing', (a) => { delete a.turnReconstruction; return a }],
  ['turn-receipt', (a) => { a.turnReconstruction.receipt_handle = 'sha256:' + '0'.repeat(64); return a }],
  ['turn-unknown', (a) => { a.turnReconstruction.status = 'UNKNOWN'; a.turnReconstruction.claims_with_unknown_context = true; return a }],
  ['turn-target', (a) => { a.turnReconstruction.selected = []; return a }],
]) {
  test(`${name} refusal invokes zero providers`, () => {
    let calls = 0
    const admission = alter(fixture())
    const gated = bindDispatchAgent(() => { calls += 1 }, { [LABEL]: admission })
    assert.throws(() => gated(PROMPT, { label: LABEL }))
    assert.equal(calls, 0)
  })
}
