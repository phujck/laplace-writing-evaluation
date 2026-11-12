// DEVELOPER COUNTERS (M5 C12 observation contract, 2026-10-15).
//
// Purpose: an operator who can read only the page's DOM (Root's browser tool) reads the shell's own bounded page
// counters on request. Rendered only when the workspace was opened with diagnostics=1, at the end of Settings; it
// is not part of any user flow and carries no declared control.
//
// Ownership: the counters are the existing owners' (the bridge ledger of workspace-bridge.mjs, the shell's page
// listener registry in workspace.mjs, the shared inspector's current/trail/cache sizes, the help and cue
// lifetimes). This module only renders a snapshot the shell passes in; it keeps no store, starts no timer,
// observes nothing and reads no private runtime state.
//
// Public contract: mountDiagnostics(host, {read}) -> {element, refresh()}; read() returns the snapshot object.
// Scope and limits, also printed in the readout: one page since it loaded (a reload resets it); this browser tab
// only, while the server traffic view (/authoring/health?view=traffic) covers every client of the process.
// Requests are not counted here (the server view counts them, including the iframe, pdf.js and images).
// Memory, when the browser reports it at all, is coarse and quantised; no heap, garbage or per-tab CPU claim.
export const PAGE_COUNTERS_SCHEMA = 'laplace.workspace-page-counters/1';
export const PAGE_COUNTERS_SCOPE = 'This page since it loaded (a reload resets it); this tab only. Requests: read the server traffic view. Memory: browser-reported, coarse, when available.';
const el = (tag, text = '', cls = '') => {const node = document.createElement(tag); node.textContent = text; node.className = cls; return node;};
export function mountDiagnostics(host, {read}) {
  const details = el('details', '', 'workspace-diagnostics'), output = el('pre', 'Not read yet.', 'workspace-diagnostics-output');
  output.setAttribute('data-laplace-diagnostics', '');output.setAttribute('role', 'status');
  const refresh = () => {output.textContent = JSON.stringify(read(), null, 1);};
  const button = el('button', 'Refresh counters', 'act act-read');button.type = 'button';button.onclick = refresh;
  details.append(el('summary', 'Developer counters (diagnostics=1)'), el('p', PAGE_COUNTERS_SCOPE, 'muted'), button, output);
  host.append(details);
  return {element: details, refresh};
}
