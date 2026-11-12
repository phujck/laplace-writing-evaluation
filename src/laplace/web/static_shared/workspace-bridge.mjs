// THE WALK BRIDGE, SHELL SIDE (M5 readability P2, 2026-10-14).
//
// Purpose: receive the manuscript iframe's postMessage traffic in the workspace shell, count it, and route
// each admitted message to ONE named shell handler. The walk (walk.mjs), its panel (writing-panel.mjs) and
// store.mjs are the producers; their contract header is in walk.mjs ("THE BRIDGE CONTRACT").
//
// Ownership: this module owns the message fence (same origin AND event.source === the current manuscript
// iframe window), the bridge ledger (window.laplaceBridge, read by root during actual pilots) and the
// route table below. It owns no view state: every effect is a handler the shell passes in
// (workspace.mjs, "THE WALK BRIDGE HANDLERS"), so what a message DOES is read in one named function there.
//
// Public contract:
//   HANDLED_BRIDGE_MESSAGES        the 20 declared message types, in route order (the ledger's keys)
//   PROPOSAL_DECISION_RESULT       the shell's one reply type to laplace:review-proposal (closure contract 2026-11-02)
//   createProposalDecisionHandler({project, projectReview, origin}) -> the shell's reviewProposal handler
//   requestProposalDecision({project, turnId, proposalVersion, readHandle, frame, origin, timeoutMs}) -> Promise (frame side)
//   panelProposalReview({project, inspect, decide}) -> the writing panel's review callback: inspect unless decision:true
//   UNKNOWN_PRODUCER_MESSAGES      handled types with no producer in this tree (counted, never inferred)
//   UNKNOWN_SAMPLE_LIMIT           distinct undeclared type names the ledger keeps
//   BRIDGE_ROUTES                  [{type, handler, accepts}]: handler is the name the shell must supply
//   createBridgeLedger()           {ledger, count(type, bytes), reject()}
//   messageBytes(data)             UTF-8 bytes of the message's JSON (the place payload meter)
//   routeBridgeMessage(message, handlers, event) -> handler name | null (an unrouted message does nothing)
//   installWalkBridge({target, origin, sourceWindow, ledger, handlers}) -> {listener, uninstall(), installed}
//
// Lifecycle: installWalkBridge adds exactly one 'message' listener to `target` (the shell window); the
// shell calls uninstall() from workspace.destroy(), which removes it once (repeat calls are no-ops). The
// ledger lives as long as the shell that created it.
// Inputs: MessageEvent (origin, source, data). Outputs: ledger counts and one handler call; nothing else.

export const UNKNOWN_PRODUCER_MESSAGES = ['laplace:focus-manuscript', 'laplace:show-sections', 'laplace:read-origin-turn'];
export const UNKNOWN_SAMPLE_LIMIT = 8;

const string = key => message => typeof message[key] === 'string';
// An exact source location (C12 nested source identity): the block's repository path, a line and the source basis it
// was read under. The editor's openSource re-checks the basis against the owner; a bare or relative name never routes.
const sourceLocation = message => typeof message.file === 'string' && !!message.file && !message.file.startsWith('/') && !message.file.split('/').includes('..') &&
  Number.isInteger(message.line) && message.line > 0 && /^sha256:[a-f0-9]{64}$/.test(message.basis?.selection_identity || '') && /^sha256:[a-f0-9]{64}$/.test(message.basis?.source_digest || '');
// The route table: one row per declared message, in the order the shell historically tested them. `accepts`
// is the shape a message must have to reach its handler; a declared message that fails it is counted (the
// ledger counts every fenced message) and does nothing, exactly as before the extraction.
export const BRIDGE_ROUTES = Object.freeze([
  {type: 'laplace:place', handler: 'place'},
  {type: 'laplace:engine-unavailable', handler: 'engineUnavailable'},
  {type: 'laplace:open-owner-read', handler: 'openOwnerRead', accepts: string('url')},
  {type: 'laplace:open-project-artifact', handler: 'openProjectArtifact', accepts: message => typeof message.url === 'string' || typeof message.path === 'string'},
  {type: 'laplace:editor-state', handler: 'editorState'},
  {type: 'laplace:open-document-source', handler: 'openDocumentSource', accepts: sourceLocation},
  {type: 'laplace:open-document-pdf', handler: 'openDocumentPdf', accepts: string('file')},
  {type: 'laplace:focus-manuscript', handler: 'focusManuscript'},
  {type: 'laplace:show-sections', handler: 'showSections'},
  {type: 'laplace:logical-object', handler: 'logicalObject', accepts: string('node')},
  {type: 'laplace:research-result', handler: 'researchResult', accepts: string('id')},
  {type: 'laplace:obligation-work', handler: 'obligationWork', accepts: string('id')},
  {type: 'laplace:read-origin-turn', handler: 'readOriginTurn', accepts: string('id')},
  {type: 'laplace:logical-context', handler: 'logicalContext'},
  {type: 'laplace:queued-request', handler: 'queuedRequest'},
  {type: 'laplace:discuss-selection', handler: 'discussSelection'},
  {type: 'laplace:source-outcome', handler: 'sourceOutcome'},
  {type: 'laplace:source-warning', handler: 'sourceWarning'},
  {type: 'laplace:source-saved', handler: 'sourceSaved'},
  {type: 'laplace:review-proposal', handler: 'reviewProposal', accepts: message => proposalDecisionRequest(message)}
].map(route => Object.freeze(route)));
export const HANDLED_BRIDGE_MESSAGES = BRIDGE_ROUTES.map(route => route.type);
const ROUTES = new Map(BRIDGE_ROUTES.map(route => [route.type, route]));

// THE BRIDGE LEDGER (plan §4 bridge_contract): every fenced iframe message is counted so reachability of the
// three unknown-producer types is observed in use rather than inferred from a grep. The counters are
// DECLARED (the handled types); an undeclared type increments one `unknown.count`, keeps at most
// UNKNOWN_SAMPLE_LIMIT distinct sample names and counts the rest as overflow, so a hostile or buggy producer
// cannot grow the ledger without bound.
export function createBridgeLedger() {
  const ledger = {messages: Object.fromEntries(HANDLED_BRIDGE_MESSAGES.map(type => [type, 0])),
    unknown_producer: Object.fromEntries(UNKNOWN_PRODUCER_MESSAGES.map(type => [type, 0])),
    unknown: {count: 0, samples: [], overflow: 0}, rejected: 0, place: 0, place_bytes: {last: 0, max: 0}};
  return {ledger,
    count(type, bytes = 0) {
      if (typeof type !== 'string' || !(type in ledger.messages)) {
        ledger.unknown.count++;
        const name = typeof type === 'string' ? type.slice(0, 80) : String(type);
        if (ledger.unknown.samples.includes(name)) return;
        if (ledger.unknown.samples.length < UNKNOWN_SAMPLE_LIMIT) ledger.unknown.samples.push(name);
        else ledger.unknown.overflow++;
        return;
      }
      ledger.messages[type]++;
      if (type in ledger.unknown_producer) ledger.unknown_producer[type]++;
      if (type === 'laplace:place') {
        ledger.place++;
        if (bytes) {ledger.place_bytes.last = bytes; ledger.place_bytes.max = Math.max(ledger.place_bytes.max, bytes);}
      }
    },
    reject() {ledger.rejected++;}};
}
// THE PROPOSAL DECISION REQUEST (closure contract 2026-11-02). One exact human decision request from the manuscript
// frame: project, producer turn, saved version and the owner-issued GET read handle, with a request id for its one reply.
// It is navigation to the shell's canonical project Review controller (createProjectReview.open, then
// workspace-proposals mountProposalReview), which validates the handle and owns drafts, permission, decision and Apply.
export const PROPOSAL_DECISION_RESULT = 'laplace:review-proposal-result';
const VERSION = /^sha256:[a-f0-9]{64}$/;
const REQUEST = /^[A-Za-z0-9._:-]{8,96}$/;
function proposalDecisionRequest(message) {
  return typeof message.project === 'string' && !!message.project && typeof message.turn_id === 'string' && !!message.turn_id &&
    VERSION.test(message.proposal_version || '') && REQUEST.test(message.request_id || '') &&
    message.read_handle?.http?.method === 'GET' && typeof message.read_handle.http.url === 'string';
}
// Shell side: the bridge handler. A foreign project refuses; the controller's own guards decide everything else, and the
// outcome (opened, or the controller's refusal text) is answered once to the requesting frame.
export function createProposalDecisionHandler({project, projectReview, origin = () => globalThis.location.origin}) {
  return async (message, event) => {
    const reply = value => {
      try {event?.source?.postMessage({type: PROPOSAL_DECISION_RESULT, request_id: message.request_id, ...value}, origin());}
      catch {/* the requesting frame has gone; its own timeout reports that nothing was confirmed */}
    };
    try {
      if (message.project !== project) throw Error('This proposal belongs to another project; nothing was opened.');
      const outcome = await projectReview.open(message.turn_id, {proposalVersion: message.proposal_version, readHandle: message.read_handle, readOnly: false, decision: true});
      const checked = proposalDecisionOutcome(outcome, {project, turnId: message.turn_id, proposalVersion: message.proposal_version});
      reply(checked.ok ? {ok: true, outcome: checked.outcome} : {ok: false, state: checked.state, error: checked.error});
    } catch (error) {
      reply({ok: false, error: String(error?.message || error).slice(0, 400)});
    }
  };
}
// Frame side: ask the shell, then wait for its one reply from that exact parent window and origin.
export function requestProposalDecision({project, turnId, proposalVersion, readHandle, frame = globalThis.window, origin = () => globalThis.location.origin, timeoutMs = 15000}) {
  const shell = frame?.parent;
  if (!shell || shell === frame) return Promise.reject(Error('Open this manuscript inside the Writing workspace to decide proposals; this view only inspects them.'));
  const id = 'review-' + String(globalThis.crypto?.randomUUID?.() || Math.random().toString(36).slice(2) + Date.now()).replaceAll('-', '').slice(0, 40);
  return new Promise((resolve, reject) => {
    let timer = null;
    const listener = event => {
      const data = event?.data;
      if (event?.origin !== origin() || event.source !== shell || data?.type !== PROPOSAL_DECISION_RESULT || data.request_id !== id) return;
      frame.removeEventListener('message', listener); clearTimeout(timer);
      if (data.ok === true) resolve(data.outcome);
      else reject(Error(data.error || 'The proposal decision did not open; nothing was decided.'));
    };
    frame.addEventListener('message', listener);
    timer = setTimeout(() => {frame.removeEventListener('message', listener); reject(Error('The Writing workspace did not answer; nothing was opened or decided.'));}, timeoutMs);
    shell.postMessage({type: 'laplace:review-proposal', project, turn_id: turnId, proposal_version: proposalVersion, read_handle: readHandle, request_id: id}, origin());
  });
}
// THE TRUTHFUL OPENING (closure contract 2026-11-02): an explicit decision counts as opened only when the canonical
// mountProposalReview reports it showed the decision view for exactly the requested project, turn and version. An
// allocation, a fulfilled promise without a report, a read-only showing or another target is not an opening.
export function proposalDecisionOutcome(outcome, {project, turnId, proposalVersion}) {
  if (outcome?.opened === true && outcome.decision === true && outcome.project === project && outcome.turn_id === turnId && outcome.proposal_version === proposalVersion)
    return {ok: true, outcome: {opened: true, decision: true, state: outcome.state, project, turn_id: turnId, proposal_version: proposalVersion}};
  const state = outcome?.opened === true ? (outcome.decision === true ? 'OTHER_TARGET' : 'READ_ONLY') : (outcome?.state || 'UNKNOWN');
  const error = outcome?.opened === true
    ? (outcome.decision === true ? 'The decision view opened another proposal; nothing is decided here.' : 'The proposal opened read-only; it is not decidable now.')
    : (outcome?.reason || 'The decision view did not report an opening; nothing was shown or decided.');
  return {ok: false, state, error};
}
// The writing panel's review callback: an explicit decision:true request reaches the shell decision; every other
// open (the historical saved-comparison cards, return to selection) stays the read-only inspection it always was.
export function panelProposalReview({project, inspect, decide = requestProposalDecision}) {
  return async (turnId, {proposalVersion, readHandle, readOnly = true, decision = false} = {}) => {
    if (decision !== true || readOnly !== false) return inspect(turnId, {proposalVersion});
    if (!proposalVersion || !readHandle) throw Error('Choose an exact saved version before deciding it.');
    return decide({project, turnId, proposalVersion, readHandle});
  };
}
export const messageBytes = data => {try {return new TextEncoder().encode(JSON.stringify(data)).length;} catch {return 0;}};

// One admitted message to its named handler. Returns the handler name it called, or null when the type is
// undeclared or the message does not have the declared shape.
export function routeBridgeMessage(message, handlers, event) {
  const route = message && typeof message === 'object' ? ROUTES.get(message.type) : undefined;
  if (!route || (route.accepts && !route.accepts(message))) return null;
  const handler = handlers[route.handler];
  if (typeof handler !== 'function') throw Error('The workspace bridge has no handler for ' + route.type + '.');
  handler(message, event);
  return route.handler;
}

// The single 'message' listener of the shell. A message from another origin, or from any window other than
// the CURRENT manuscript iframe, is rejected and counted; every other message is counted (with the place
// payload's bytes) and routed.
export function installWalkBridge({target = globalThis.window, origin = () => globalThis.location.origin, sourceWindow, ledger, handlers}) {
  const missing = BRIDGE_ROUTES.filter(route => typeof handlers?.[route.handler] !== 'function').map(route => route.handler);
  if (missing.length) throw Error('The workspace bridge is missing handlers: ' + missing.join(', ') + '.');
  const listener = event => {
    if (event.origin !== origin() || event.source !== sourceWindow()) {ledger.reject(); return;}
    const message = event.data;
    ledger.count(message?.type, message?.type === 'laplace:place' ? messageBytes(message) : 0);
    routeBridgeMessage(message, handlers, event);
  };
  target.addEventListener('message', listener);
  let installed = true;
  return {listener,
    get installed() {return installed;},
    uninstall() {if (!installed) return; target.removeEventListener('message', listener); installed = false;}};
}
