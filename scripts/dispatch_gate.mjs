import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'

const sha256 = (bytes) => 'sha256:' + createHash('sha256').update(bytes).digest('hex')

function canonical(value) {
  if (value === null || typeof value === 'boolean' || typeof value === 'string') return JSON.stringify(value)
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new Error('DISPATCH_RECEIPT_MALFORMED')
    return JSON.stringify(value)
  }
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']'
  if (typeof value !== 'object') throw new Error('DISPATCH_RECEIPT_MALFORMED')
  return '{' + Object.keys(value).sort().map((key) => JSON.stringify(key) + ':' + canonical(value[key])).join(',') + '}'
}

const same = (left, right) => canonical(left) === canonical(right)
const validHash = (value) => typeof value === 'string' && /^sha256:[0-9a-f]{64}$/.test(value)

export function verifyDispatchAdmission({ label, prompt, admission }) {
  const refuse = (reason) => { throw new Error(reason) }
  if (!label || !admission || admission.label !== label) refuse('DISPATCH_LABEL_MISMATCH')
  const turn = admission.turnReconstruction
  if (!turn || turn.schema_version !== 'laplace.turn-reconstruction/1') {
    refuse('TURN_RECONSTRUCTION_MISSING')
  }
  if (turn.status !== 'ADMITTED' || turn.claims_with_unknown_context !== false || turn.read_only !== true || turn.authority_effect !== 'none') {
    refuse('TURN_RECONSTRUCTION_MALFORMED')
  }
  if (!validHash(turn.profile_handle) || !validHash(turn.semantic_fold_health_handle) || !validHash(turn.goal_author_turn_digest)) {
    refuse('TURN_RECONSTRUCTION_COORDINATE_MISSING')
  }
  const continuation = turn.continuation_decision
  if (!continuation || continuation.schema_version !== 'laplace.continuation-admission/1'
      || continuation.status !== 'ADMITTED' || continuation.substantive_work_allowed !== true) {
    refuse('CONTINUATION_NOT_ADMITTED')
  }
  const continuationBody = { ...continuation }
  delete continuationBody.decision_handle
  if (!validHash(continuation.decision_handle)
      || sha256(Buffer.from(canonical(continuationBody), 'utf8')) !== continuation.decision_handle) {
    refuse('CONTINUATION_DECISION_MISMATCH')
  }
  const selectedContext = Array.isArray(turn.selected) && turn.selected.some((row) => (
    row && typeof row.kind === 'string' && typeof row.reference === 'string'
      && row.content_status === 'COMPLETE' && validHash(row.content_handle)
  ))
  if (!selectedContext) {
    refuse('TURN_RECONSTRUCTION_CONTEXT_MISSING')
  }
  const turnBody = { ...turn }
  delete turnBody.receipt_handle
  if (!validHash(turn.receipt_handle) || sha256(Buffer.from(canonical(turnBody), 'utf8')) !== turn.receipt_handle) {
    refuse('TURN_RECONSTRUCTION_RECEIPT_MISMATCH')
  }
  const reconstruction = admission.reconstruction
  const phase = admission.phaseReceipt
  if (!reconstruction || !phase) refuse('DISPATCH_RECONSTRUCTION_MISSING')
  if (reconstruction.kind !== 'atlas-object' || reconstruction.content_status !== 'COMPLETE') {
    refuse(`DISPATCH_RECONSTRUCTION_${String(reconstruction.content_status || 'REFUSED')}`)
  }
  if (reconstruction.read_only !== true || reconstruction.transition_claim !== 'none' || reconstruction.authority_write !== 'none') {
    refuse('DISPATCH_RECONSTRUCTION_NOT_PURE')
  }
  if (reconstruction.integrity_boundary !== 'CHECKSUMMED-CRUTCH' || reconstruction.authenticated === true) {
    refuse('DISPATCH_INTEGRITY_BOUNDARY_MISMATCH')
  }
  if (reconstruction.moved === true) refuse('DISPATCH_AUTHORITY_MOVED')
  if (reconstruction.ambiguous === true) refuse('DISPATCH_AUTHORITY_AMBIGUOUS')
  if (reconstruction.current !== true) refuse('DISPATCH_CHECKPOINT_UNAVAILABLE')
  if (reconstruction.clean !== true) refuse('DISPATCH_AUTHORITY_DIRTY')
  const suffix = reconstruction.authority_suffix_count
  if (!Number.isInteger(suffix) || suffix < 0 || suffix > 64) refuse('DISPATCH_AUTHORITY_SUFFIX_REFUSED')
  if (reconstruction.authority_suffix_limit !== 64 || reconstruction.read_metrics?.suffix_rows_loaded !== suffix) {
    refuse('DISPATCH_AUTHORITY_SUFFIX_MISMATCH')
  }
  if (!validHash(reconstruction.content_handle) || sha256(Buffer.from(reconstruction.content, 'utf8')) !== reconstruction.content_handle) {
    refuse('DISPATCH_CONTENT_HANDLE_MISMATCH')
  }
  if (!validHash(reconstruction.current_root) || !validHash(reconstruction.authority_root) || !reconstruction.drift_token) {
    refuse('DISPATCH_AUTHORITY_PROOF_MALFORMED')
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
  const claimHandle = sha256(Buffer.from(canonical(claim), 'utf8'))
  if (!same(reconstruction.reconstruction_receipt, claim) || reconstruction.reconstruction_receipt_handle !== claimHandle) {
    refuse('DISPATCH_RECONSTRUCTION_RECEIPT_MISMATCH')
  }
  if (admission.prompt_handle !== sha256(Buffer.from(String(prompt), 'utf8'))) refuse('DISPATCH_PROMPT_MISMATCH')
  if (phase.schema_version !== 'laplace.dispatch-reconstruction/1' || phase.node !== reconstruction.reference || phase.goal_utf8 !== reconstruction.goal || phase.goal_bytes_hex !== Buffer.from(reconstruction.goal, 'utf8').toString('hex')) {
    refuse('DISPATCH_PHASE_COORDINATE_MISMATCH')
  }
  if (phase.reconstruction_content_handle !== reconstruction.content_handle || phase.reconstruction_receipt_handle !== claimHandle || phase.current_root !== reconstruction.current_root || phase.authority_root !== reconstruction.authority_root || !same(phase.drift_token, reconstruction.drift_token)) {
    refuse('DISPATCH_PHASE_PROOF_MISMATCH')
  }
  if (phase.admission_result?.status !== 'ADMITTED' || phase.admission_result?.reason !== 'EXACT' || phase.integrity_boundary?.status !== 'CHECKSUMMED-CRUTCH') {
    refuse('DISPATCH_PHASE_NOT_ADMITTED')
  }
  const body = { ...phase }
  delete body.receipt_handle
  if (!validHash(phase.receipt_handle) || sha256(Buffer.from(canonical(body), 'utf8')) !== phase.receipt_handle) {
    refuse('DISPATCH_PHASE_RECEIPT_MISMATCH')
  }
  return {
    schema_version: 'laplace.dispatch-gate/1',
    status: 'ADMITTED',
    label,
    phase_receipt_handle: phase.receipt_handle,
    turn_reconstruction_handle: turn.receipt_handle,
    claims_with_unknown_context: turn.claims_with_unknown_context === true,
  }
}

export function bindDispatchAgent(provider, admissionsSource) {
  if (typeof provider !== 'function') throw new Error('DISPATCH_PROVIDER_MISSING')
  return function dispatchAgent(prompt, options = {}) {
    const label = options?.label
    const admissions = typeof admissionsSource === 'function' ? admissionsSource() : admissionsSource
    const admission = admissions && label ? admissions[label] : null
    verifyDispatchAdmission({ label, prompt, admission })
    const reconstructedPrompt = `${prompt}\n\nTURN RECONSTRUCTION\n${canonical(admission.turnReconstruction)}`
    return provider(reconstructedPrompt, options)
  }
}

if (process.argv[1] && process.argv[1].endsWith('dispatch_gate.mjs') && process.argv.includes('--verify-json')) {
  try {
    const payload = JSON.parse(readFileSync(0, 'utf8'))
    process.stdout.write(JSON.stringify(verifyDispatchAdmission(payload)) + '\n')
  } catch (error) {
    process.stderr.write(String(error?.message || error) + '\n')
    process.exitCode = 2
  }
}
