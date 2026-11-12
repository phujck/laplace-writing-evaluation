// ONE consumer of a running turn's owner event stream (GET /authoring/events?turn=<id>, served by authoring_http from the
// turn's job: delta, progress, complete and error events). Used by the Sessions page (workspace-sessions.mjs) and the
// Workflows run river (workspace-workflow-river.mjs). The stream URL is the owner's issued events_url (from the session
// summary read's active.capabilities); this module never composes one. It checks the URL names the same origin, the
// events door and the exact turn, adds the owner's cursor as `after`, opens one EventSource and hands each parsed event
// to the consumer. Unparseable events are skipped, as before.
export function turnEventsURL(raw, turnId) {
  const base = globalThis.location?.href || 'http://localhost/', value = new URL(raw, base);
  if (value.origin !== new URL(base).origin || value.pathname !== '/authoring/events' || value.searchParams.get('turn') !== turnId) throw Error('The owner observation URL does not match this turn.');
  return value;
}
// Returns the open EventSource (with .turnId) or null when the browser has none; throws when the URL is not the owner's.
export function openTurnEvents(raw, turnId, {after = null, onEvent = () => {}, onError = () => {}} = {}) {
  if (typeof EventSource !== 'function') return null;
  const url = turnEventsURL(raw, turnId);
  if (after != null) url.searchParams.set('after', String(after));
  const source = new EventSource(url.pathname + url.search); source.turnId = turnId;
  source.onmessage = event => { let item; try { item = JSON.parse(event.data); } catch { return; } onEvent(item, source); };
  source.onerror = () => onError(source);
  return source;
}
// The words of a progress event's text (a provider item name such as agentMessage or command_execution), as the
// Sessions page and the run river both print it: camel case split, underscores and hyphens as spaces.
export function progressWords(text) {
  return String(text ?? '').replace(/([a-z])([A-Z])/g, '$1 $2').replaceAll('_', ' ').replaceAll('-', ' ');
}
