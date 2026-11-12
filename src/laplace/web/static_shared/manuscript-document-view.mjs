// Human labels and transport of the document owner's facts; no freshness inference.
export function manuscriptPdfState(doc) {
  if(doc?.current_build?.state==='cancelling')return 'Stopping PDF build…';
  if(doc?.current_build?.state==='cancelled')return 'Last PDF build stopped';
  return ({
    RUNNING: 'Building PDF…',
    FAILED: 'Last PDF build failed',
    READY: 'PDF matches saved document',
    STALE: 'PDF needs rebuilding',
    NOT_BUILT: 'No verified PDF build',
    UNAVAILABLE: 'Document unavailable'
  }) [doc?.status] || 'Document status unavailable';
}
export function documentPdfURL(doc) {
  const handle = doc?.read_handles?.pdf;
  if (!handle) return null;
  const identity = doc.pdf_identity,
  query = handle.query;
  if (handle.method !== 'GET' || handle.route !== '/projection/pdf' || !identity || query?.corpus !== doc.project || query.file !== identity.file || query.expected_content_revision !== identity.content_revision || !/^sha256:[0-9a-f]{64}$/.test(identity.content_revision || '')) throw Error('The PDF handle does not match the observed document output. Refresh the document.');
  return handle.route + '?' + new URLSearchParams(query);
}
export function documentPdfNotice(doc, dirty = false) {
  return manuscriptPdfState(doc) + (doc?.pdf_identity?.verification === 'OBSERVED_ONLY' ? ' · Existing PDF bytes; build basis is unverified.': '') + (dirty ? ' · Unsaved edits are not included.': '');
}
