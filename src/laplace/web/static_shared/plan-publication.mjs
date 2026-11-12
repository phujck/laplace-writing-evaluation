// Read the plan owner's publication receipt without treating metadata as source
// bytes. A recorded plan and completed required follow-through are separate facts.
export function planPublicationDisposition(result) {
  const publication = result?.plan_publication;
  if (publication === undefined) return null;
  const invalid = () => {
    throw Object.assign(Error('The reader-plan publication could not be verified. Keep your draft and inspect the plan before another action.'),
    {
      result,
      planUnverified: true
    });
  };
  if (!publication || typeof publication !== 'object' || !['COMMITTED', 'UNCHANGED', 'COMPENSATED', 'PARTIAL',
  'UNPROVED'].includes(publication.status) || typeof publication.complete !== 'boolean' || !Number.isInteger(publication.ledger_append_count) || publication.ledger_append_count < 0) invalid();
  if (publication.complete && !['COMMITTED', 'UNCHANGED'].includes(publication.status)) invalid();
  if (publication.status === 'COMMITTED' && publication.ledger_append_count < 1 || publication.status === 'UNCHANGED' && publication.ledger_append_count !== 0) invalid();
  const acknowledged = publication.complete && ['COMMITTED', 'UNCHANGED'].includes(publication.status);
  const warnings = Array.isArray(result.maintenance_warnings) ? result.maintenance_warnings: [];
  const message = {
    COMMITTED: publication.complete ? 'Reader plan saved.': 'Reader-plan changes were recorded, but required follow-through is incomplete. Do not repeat the saved action.',
    UNCHANGED: publication.complete ? 'No reader-plan changes.': 'The reader plan is unchanged; required follow-through still needs inspection.',
    COMPENSATED: 'The reader-plan change was compensated. Your draft is retained; inspect the outcome before another action.',
    PARTIAL: 'Some reader-plan changes remain. Required work is incomplete; inspect the recorded outcome and do not repeat the action.',
    UNPROVED: 'The reader-plan outcome is unproved. Keep your draft and inspect the recorded outcome before another action.'
  }
  [publication.status] + (acknowledged && warnings.length ? ' Follow-up maintenance needs attention: ' + warnings.map(row => row.reason || row.operation || 'recorded warning').join('; '): '');
  return {
    publication,
    acknowledged,
    suppressRetry: !acknowledged,
    message,
    warnings
  };
}
export function requirePlanCompletion(result) {
  const disposition = planPublicationDisposition(result);
  if (disposition && !disposition.acknowledged) {
    throw Object.assign(Error(disposition.message), {
      result,
      planDisposition: disposition
    });
  }
  return disposition;
}
export function planFailure(error) {
  const result = error?.result || error?.body;
  const disposition = planPublicationDisposition(result);
  if (!disposition) return null;
  return {
    ...disposition,
    suppressRetry: true,
    message: disposition.acknowledged ? disposition.message + ' Follow-up failed; inspect the plan without repeating the saved action.': disposition.message
  };
}
export function savedActionPlanPublication(action) {
  return planPublicationDisposition(action?.outcome);
}
export function savedFailurePlanPublication(failure) {
  return planPublicationDisposition(failure?.recovery);
}
