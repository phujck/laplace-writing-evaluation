// MANUSCRIPT SOURCE TRANSPORT. Purpose: one transport and acknowledgement contract for reading
// and saving manuscript source, shared by the writing workspace and the legacy artefact editor.
// Ownership: /projection/tex (read) and the source save route own bytes, selection, retry and
// revision policy; this module validates the shapes it sends and receives (validateSourceRead,
// validateSourceSave), builds the save parameters (sourceSaveParameters), advances the source
// observation after a save (advanceSourceObservation) and acknowledges drafts (acknowledgeDraft,
// sourceDraftDirty). Inputs/outputs: exact owner handles and responses. Currentness: the
// expected_source_digest the owner issued; a changed file refuses at the owner (source-effect).
// Errors: a refused save is surfaced through sourceEffectDisposition. Storage: none.
import {requireSourceCompletion,sourceEffectDisposition} from './source-effect.mjs';
// One transport and acknowledgement contract for Writing and the legacy artefact editor.
// This module owns no source, current selection, retry or revision policy.
const digest = value => typeof value === 'string' && /^sha256:[0-9a-f]{64}$/.test(value);
export function validateSourceRead(value) {
  if (value?.schema_version !== 'laplace.projection-source/1' || typeof value.file !== 'string' || typeof value.content !== 'string' || !digest(value.expected_source_digest)) throw Error('The source owner did not supply an exact inspected basis.');
  return value;
}
export function validateSourceSave(value, submission) {
  requireSourceCompletion(value,{project:submission.corpus||submission.project,selectionIdentity:submission.expected_selection,file:submission.file,beforeDigest:submission.expected_source_digest,afterDigest:value?.expected_source_digest});
  const refuse = message => {throw Object.assign(Error(message), {result:value});};
  if (value?.ok !== true || value.source_committed !== true || value.file !== submission.file || value.consumed_source_digest !== submission.expected_source_digest || !digest(value.expected_source_digest)) refuse('Save acknowledgement did not identify this source. Your draft is retained; inspect the saved file before retrying.');
  if (submission.expected_selection && value.selection_identity !== submission.expected_selection) refuse('Save acknowledgement changed the selected document identity. Your draft is retained.');
  return value;
}
export async function sourceRequest(url, options = {}, fetcher = globalThis.fetch) {
  const response = await fetcher(url, options);
  const value = await response.json();
  if (!response.ok || value.error) {
    const disposition = sourceEffectDisposition(value);
    const error = Error(disposition ? disposition.message : typeof value.error === 'string' ? value.error : 'Source request failed');
    if(disposition)error.sourceDisposition=disposition;
    error.status = response.status;
    error.reason = value.reason;
    error.recovery = value.recovery;
    error.result = error.body = value;
    throw error;
  }
  return value;
}
export async function readManuscriptSource({
  project,
  file,
  endpoint = '/projection/tex',
  transport
}
= {}) {
  const params = {
    file,
    corpus: project,
    view: 'source'
  };
  const value = validateSourceRead(await (transport ? transport(endpoint, {
    params
  }): sourceRequest(endpoint + '?' + new URLSearchParams(params))));
  const handle = value.read_handle;
  if (handle && (handle.method !== 'GET' || handle.route !== '/projection/tex' || handle.query?.file !== value.file || handle.query.corpus !== project || handle.query.view !== 'source')) throw Error('The source read handle does not match the displayed observation.');
  return value;
}
export function sourceSaveParameters(project, observed, {
  surface = 'manuscript-source',
  author = 'author'
}
= {}) {
  validateSourceRead(observed);
  if (observed.read_only) throw Error('This document source is read-only.');
  const handle = observed.save_handle;
  if (observed.selection_identity && !handle) throw Error('The selected source owner supplied no save handle. Reinspect this file.');
  if (handle && (handle.method !== 'POST' || handle.route !== '/projection/tex' || handle.body_kind !== 'raw-text')) throw Error('The source owner returned an unsupported save handle.');
  const expected = {
    file: observed.file,
    corpus: project,
    expected_source_digest: observed.expected_source_digest,
    ...(observed.selection_identity ? {
      expected_selection: observed.selection_identity
    }
    : {})
  };
  if (handle) {
    for (const [key, value] of Object.entries(expected)) if (handle.query?.[key] !== value) throw Error('The save handle does not match the displayed source ' + key + '. Nothing was sent.');
    if (!observed.selection_identity && handle.query?.expected_selection) throw Error('The save handle has an unobserved document identity. Nothing was sent.');
  }
  return {
    ...(handle?.query || {
      ...expected,
      bank: 'editor'
    }),
    surface,
    author
  };
}
export async function saveManuscriptSource({
  project,
  observed,
  content,
  endpoint = '/projection/tex',
  surface = 'manuscript-source',
  author = 'author',
  transport
}
= {}) {
  const params = sourceSaveParameters(project, observed, {
    surface,
    author
  });
  endpoint = observed.save_handle?.route || endpoint;
  const value = await (transport ? transport(endpoint, {
    method: 'POST',
    params,
    body: content
  }): sourceRequest(endpoint + '?' + new URLSearchParams(params), {
    method: 'POST',
    headers: {
      'Content-Type': 'text/plain;charset=UTF-8',
      'X-Laplace-Writing': '1'
    },
    body: content
  }));
  return validateSourceSave(value, params);
}
export function advanceSourceObservation(observed, submitted, receipt) {
  validateSourceSave(receipt, submitted);
  return {
    ...observed,
    content: submitted.content,
    expected_source_digest: receipt.expected_source_digest,
    ...(observed.save_handle ? {
      save_handle: {
        ...observed.save_handle,
        query: {
          ...observed.save_handle.query,
          expected_source_digest: receipt.expected_source_digest
        }
      }
    }
    : {})
  };
}
export function acknowledgeDraft(draft, submitted, receipt) {
  return {
    ...draft,
    base: submitted.content,
    observed: advanceSourceObservation(draft.observed, submitted, receipt),
    uncertain: false
  };
}
export const sourceDraftDirty = draft => !!draft && draft.content !== draft.base;
export async function readHistoricalSource(handle, {
  project,
  file,
  transport
}
= {}) {
  const initial = handle?.query;
  if (handle?.method !== 'GET' || handle.route !== '/authoring/history' || initial?.view !== 'source' || initial.project !== project || initial.file !== file || !['editor-save',
  'snapshot'].includes(initial.kind) || !initial.version_id) throw Error('This revision has no exact historical source read.');
  let next = handle,
  revision = null,
  content = '',
  offset = 0,
  archive = null,
  bytes = 0;
  while (next) {
    const q = next.query;
    if (next.method !== 'GET' || next.route !== handle.route || ['project', 'view', 'kind', 'version_id', 'file'].some(key => q?.[key] !== initial[key]) || (q.offset ?? 0) !== offset || (revision && q.expected_content_revision !== revision)) throw Error('Historical continuation changed the selected archive identity.');
    const value = await (transport ? transport(next.route, {
      params: q
    }): sourceRequest(next.route + '?' + new URLSearchParams(q)));
    const identity = value.archive_identity;
    if (value.schema_version !== 'laplace.historical-source/1' || value.project !== project || value.file !== file || value.read_only !== true || typeof value.content !== 'string' || !digest(value.content_revision) || identity?.kind !== initial.kind || identity.version_id !== initial.version_id || identity.file !== file || value.offset !== offset || (revision && value.content_revision !== revision) || (initial.expected_content_revision && value.content_revision !== initial.expected_content_revision) || value.expected_source_digest || value.save_handle || value.selection_identity) throw Error('The historical source read did not verify this exact archived version.');
    if (archive && JSON.stringify(identity) !== JSON.stringify(archive)) throw Error('The historical archive basis changed during comparison.');
    archive = identity;
    revision = value.content_revision;
    content += value.content;
    bytes += new TextEncoder().encode(value.content).byteLength;
    if (bytes > 2000000) throw Error('This historical source exceeds the comparison limit.');
    if (value.complete === true) {
      if (value.next_read || value.next_offset != null) throw Error('Historical completion has contradictory continuation.');
      return {
        content,
        content_revision: revision,
        archive_identity: archive
      };
    }
    if (!Number.isInteger(value.next_offset) || value.next_offset <= offset || !value.next_read) throw Error('The historical source is incomplete and has no exact continuation.');
    offset = value.next_offset;
    next = value.next_read;
  }
  throw Error('The historical source is incomplete.');
}
