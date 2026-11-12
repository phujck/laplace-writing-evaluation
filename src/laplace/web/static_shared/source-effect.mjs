// One interpretation of the source owner's additive effect receipt. Presentation
// adapters still bind their own exact file or proposal identity before settling a
// draft. A physical commit and complete required follow-through are distinct.
export const SOURCE_EFFECT_SCHEMA = 'laplace.source-effect/1';
const STATES = new Set(['UNCHANGED', 'COMMITTED', 'ROLLED_BACK', 'PARTIAL', 'UNPROVED']);
const REQUIRED = new Set(['COMPLETE', 'NOT_NEEDED', 'COMPENSATED', 'FAILED', 'UNPROVED']);
const pin = value => value === null || /^sha256:[0-9a-f]{64}$/.test(value || '');

export function sourceEffectDisposition(result, {project, selectionIdentity, file, beforeDigest, afterDigest} = {}) {
  const effect = result?.source_effect;
  // Compatibility is explicit: an absent additive object leaves the older
  // endpoint's established acknowledgement contract to its adapter. Nested
  // receipts[i].source_effect strings are never traversed or reinterpreted.
  if (effect === undefined) return null;
  const invalid = () => {
    const error = Error('The source effect receipt could not be verified. Preserve the recovery draft and inspect the recorded outcome before retrying.');
    error.sourceEffectUnverified = true;
    error.result = result;
    throw error;
  };
  if (effect === null || typeof effect !== 'object') invalid();
  if (effect.schema_version !== SOURCE_EFFECT_SCHEMA || !STATES.has(effect.state) ||
      typeof effect.complete !== 'boolean' || typeof effect.project !== 'string' ||
      !pin(effect.selection_identity) || !Array.isArray(effect.files) || !effect.files.length ||
      !Array.isArray(effect.follow_through?.required) ||
      !Array.isArray(effect.follow_through?.maintenance_warnings) ||
      !['NONE', 'REOBSERVE', 'UNPROVED'].includes(effect.impact?.status) ||
      !Array.isArray(effect.impact?.reads)) invalid();
  if (project && effect.project !== project) invalid();
  if (selectionIdentity !== undefined && effect.selection_identity !== selectionIdentity) invalid();
  for (const file of effect.files) {
    if (file?.scope !== 'repository' || typeof file.path !== 'string' || !file.path ||
        !pin(file.before_sha256) || !pin(file.after_sha256) || !pin(file.observed_after_sha256)) invalid();
    if (Object.hasOwn(file, 'observation_error') &&
        (typeof file.observation_error !== 'string' || effect.state !== 'UNPROVED')) invalid();
    if (effect.state === 'COMMITTED' && file.after_sha256 !== file.observed_after_sha256) invalid();
    if (effect.state === 'ROLLED_BACK' && file.before_sha256 !== file.observed_after_sha256) invalid();
    if (effect.state === 'UNCHANGED' && (file.before_sha256 !== file.after_sha256 ||
        file.after_sha256 !== file.observed_after_sha256)) invalid();
  }
  for (const step of effect.follow_through.required) {
    if (typeof step?.owner !== 'string' || !REQUIRED.has(step.status)) invalid();
  }
  if (effect.complete && (!['COMMITTED', 'UNCHANGED'].includes(effect.state) ||
      effect.follow_through.required.some(step => !['COMPLETE', 'NOT_NEEDED'].includes(step.status)))) invalid();
  if (file) {
    const row = effect.files.find(row => row.path === file);
    if (!row || beforeDigest !== undefined && row.before_sha256 !== beforeDigest ||
        afterDigest !== undefined && row.observed_after_sha256 !== afterDigest) invalid();
  }
  const warnings = effect.follow_through.maintenance_warnings;
  const acknowledged = effect.complete && ['COMMITTED', 'UNCHANGED'].includes(effect.state);
  const messages = {
    UNCHANGED: effect.complete ? 'No source changes.' : 'No source changes; required work is incomplete. Inspect the recorded outcome before another action.',
    COMMITTED: effect.complete
      ? 'Source saved.' + (warnings.length ? ' Follow-up maintenance needs attention.' : '')
      : 'Source was saved, but required follow-through is incomplete. Do not repeat the source write.',
    ROLLED_BACK: 'Source changes were rolled back. Your recovery draft is retained; inspect the outcome before an explicit retry.',
    PARTIAL: 'Some source changes remain. Required follow-through is incomplete. Do not repeat the source write.',
    UNPROVED: 'The source outcome is unproved. Keep the recovery draft and inspect the recorded outcome before retrying.'
  };
  return {
    effect,
    state: effect.state,
    complete: effect.complete,
    acknowledged,
    sourceLanded: effect.state === 'COMMITTED' || effect.state === 'PARTIAL',
    suppressRetry: !acknowledged,
    changed: effect.state !== 'UNCHANGED',
    warnings,
    message: messages[effect.state],
    impactReads: effect.impact.reads
  };
}

export function requireSourceCompletion(result, expected = {}) {
  const disposition = sourceEffectDisposition(result, expected);
  if (disposition && !disposition.acknowledged) {
    const error = Error(disposition.message);
    error.sourceDisposition = disposition;
    error.result = error.body = result;
    throw error;
  }
  return disposition;
}

export function sourceEffectFromError(error, expected = {}) {
  const disposition = sourceEffectDisposition(error?.result || error?.body, expected);
  if (!disposition) return null;
  // A transport or adapter failure may coexist with a complete physical effect.
  // Preserve that truth while refusing to treat the failed call as replay-safe.
  return {
    ...disposition,
    suppressRetry:true,
    message:disposition.acknowledged
      ? disposition.message + ' The response also reported a failure. Inspect the recorded outcome; do not repeat the source write.'
      : disposition.message
  };
}

// Persisted writing-tool-action rows put the owner's summary in outcome;
// native immediate/compact results keep the additive receipt at their top level.
export function savedActionSourceEffect(action, expected = {}) {
  if (expected.project && action?.project && expected.project !== action.project) {
    throw Error('This saved source action belongs to another project.');
  }
  return sourceEffectDisposition(action?.outcome, {
    ...expected,
    project:expected.project || action?.project
  });
}

// Failure rows already retain their owner response as recovery. Do not copy the
// receipt into another history field or treat a historical failure as new work.
export function savedFailureSourceEffect(failure) {
  return sourceEffectDisposition(failure?.recovery, {project:failure?.project});
}

// View refresh is optional follow-through after an acknowledged writer response.
// Preserve the exact result if a later read/render fails; never re-run the write.
export async function afterSourceWrite(result, followThrough, {project, savedLabel='Source saved.'} = {}) {
  const effect = requireSourceCompletion(result, {project});
  try {
    return await followThrough(result);
  } catch (cause) {
    if (!effect?.acknowledged && result?.ok !== true) throw cause;
    const error = Error((effect?.message || savedLabel) + ' Follow-up view refresh is unavailable: ' + cause.message + ' Do not repeat the saved operation.');
    error.cause = cause;
    error.result = result;
    error.effectAcknowledged = true;
    throw error;
  }
}
