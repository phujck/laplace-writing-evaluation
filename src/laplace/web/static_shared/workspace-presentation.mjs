// Shared human presentation of owner facts: one object, one place, one next step.
//
// Every domain view (Work, conversation, history, reader plan, template, editor) paints
// the same kinds of thing: an object with its state, its local relations, the action a
// person can take beside it, and an exact owner read behind a deliberate gesture. This
// module owns those presentations and nothing else. It holds no state, fetches nothing,
// and knows no lifecycle: every fact is the owner's delivered value, every label table
// below is explicit so owner meanings (recorded lifecycle, readiness, current evidence,
// source effect, continuation phase) stay distinct under one visual vocabulary, and
// every exact detail is a callback the consumer supplies. Validators and submissions
// stay where they are (prepared-work, document-template, reader-state, ...).
//
// Three altitudes: a chip row is the glance, an object header with a relation list and
// one action row is the card, and a lazy section or the shared inspector is the exact
// read. Disclosure triangles are not information architecture here; optional detail is
// reached by a named action that loads once.
export const TONES = Object.freeze(['ok', 'attention', 'blocked', 'running', 'historical', 'neutral']);
import {pendingRead} from './pending-read.mjs';
// A control's declared identity (R3): the one place a page names a control for src/laplace/native/declarations.py. `owner` is the
// owner's identity of one row of a repeated family; every page imports this and defines no copy.
export const declareControl=(node,id,owner=null)=>{node.setAttribute('data-control',id);if(owner!=null)node.setAttribute('data-control-owner',String(owner));return node;};
const el = (tag, text = '', cls = '') => {const node = document.createElement(tag); node.textContent = text; node.className = cls; return node;};
// A DOM node versus a plain descriptor; duck-typed so the Node test harness qualifies.
const isNode = value => !!value && typeof value === 'object' && typeof value.append === 'function';
// data-* writes that survive test doubles without a dataset.
const data = (node, key, value) => {if (node.dataset) node.dataset[key] = value; else node.setAttribute('data-' + key.replace(/[A-Z]/g, c => '-' + c.toLowerCase()), value); return node;};
const words = value => String(value ?? '').replaceAll('_', ' ').replaceAll('-', ' ').trim();
const lower = value => words(value).toLowerCase();
// An owner enum word kept verbatim apart from case and underscores: `in-progress` stays
// `in-progress` because that is the word the owner, the native door and the ledger use.
const ownerWord = value => String(value ?? '').replaceAll('_', ' ').trim().toLowerCase();

export function stateChip({label, tone = 'neutral', title = ''} = {}) {
  if (!TONES.includes(tone)) throw Error('Unknown presentation tone: ' + tone);
  const chip = el('span', label, 'state-chip');
  data(chip, 'tone', tone);
  if (title) chip.title = title;
  return chip;
}
export function chipRow(chips = []) {
  const row = el('span', '', 'chip-row');
  for (const chip of chips) if (chip) row.append(isNode(chip) ? chip : stateChip(chip));
  return row;
}

// ---- explicit tone tables; owner labels are kept, only the visual treatment is shared ----
export const GROUP_LABELS={attention:'Needs attention',active:'Observed activity',awaiting:'Awaiting review',blocked:'Waiting','in-progress':'In progress (declared)',ready:'Ready',settled:'Closed'};
const GROUP_TONES={attention:'attention',active:'running',awaiting:'neutral',blocked:'neutral','in-progress':'neutral',ready:'ok',settled:'historical'};
// Completion is a recorded lifecycle fact. Current proof may need a new check;
// the legacy effective status must not turn that completed task into execution.
export function completedTaskChip(row={}){
 const fact=(row.standing?.facts||[]).find(item=>['done-current','done-review-required','done-unknown'].includes(item.code));
 if(row.lifecycle?.completed!==true&&(row.lifecycle||!fact))return null;
 const acceptance=row.current_acceptance?.status||({'done-current':'CURRENT','done-review-required':'REVIEW_REQUIRED','done-unknown':'UNKNOWN'})[fact?.code];
 if(acceptance==='UNKNOWN')return {label:'Completed — evidence unavailable',tone:'attention'};
 if(acceptance==='REVIEW_REQUIRED'||row.current_acceptance?.review_required===true)return {label:'Completed — evidence needs rechecking',tone:'attention'};
 if(acceptance==='CURRENT')return {label:'Completed — evidence current at this check',tone:'historical'};
 return {label:'Completed — current evidence not reported',tone:'attention'};
}
export function taskActivityChip(row={}){
 const fact=(row.standing?.facts||[]).find(item=>/^(observed-|activity-unknown)/.test(item.code)),state=typeof row.activity?.state==='string'?row.activity.state.toLowerCase():null;
 if(fact)return {label:fact.text,tone:fact.code==='observed-running'?'running':fact.code==='observed-failed'?'blocked':'neutral'};
 if(!state||state==='not_observed'||state==='not-observed'){const execution=row.dispatch?.execution_state;if(execution)return {label:'Execution owner: '+String(execution).toLowerCase().replaceAll('_',' '),tone:/running|active/i.test(execution)?'running':/failed|error/i.test(execution)?'blocked':'neutral'};return null;}
 return {label:state==='unknown'?'Activity unknown':'Observed activity: '+String(state).replaceAll('_',' '),tone:state==='running'?'running':state==='failed'?'blocked':'neutral'};
}
export function taskStateChips(row,fallback=()=>({label:'Task state not supplied in this view',tone:'neutral'})){
 const completed=completedTaskChip(row),lifecycle=row?.lifecycle,status=lifecycle?.status;
 let primary=completed;
 // The same qualified owner standing leads every projection. Recorded status
 // stays separate; current readiness is not a declaration or an execution.
 if(!primary&&!lifecycle?.closed&&row.standing?.facts?.length&&GROUP_LABELS[row.standing.group])primary={...standingChip(row,fallback),title:['Recorded status: '+(row.recorded_status||status||'not reported'),...(row.standing.facts||[]).map(fact=>fact.text)].join('. ')};
 if(!primary&&status){const label=({'in-progress':'In progress (declared)',open:'Open',ready:'Ready (declared)',blocked:'On hold',cancelled:'Cancelled',withdrawn:'Withdrawn'})[status]||('Recorded '+status.replaceAll('-',' '));const readiness=lifecycle.closed===false&&row.readiness?.status==='BLOCKED'?' · waiting on prerequisites':row.current_acceptance?.review_required?' · review needed':'';primary={label:label+readiness,tone:lifecycle.closed?'historical':row.current_acceptance?.review_required?'attention':'neutral'};}
 primary=primary||standingChip(row,fallback);const activity=taskActivityChip(row);return [primary,...(activity&&!primary.label.includes(activity.label)?[activity]:[])];
}
export function taskFacetRow(fact={}){return {lifecycle:fact.lifecycle,current_acceptance:fact.current_acceptance,readiness:fact.readiness,activity:fact.activity,standing:fact.standing||(fact.qualification&&typeof fact.qualification==='object'?fact.qualification:{group:fact.label,facts:[]})};}
export const taskStatusName=value=>({done:'Mark done',verified:'Record verified status',open:'Reopen task',ready:'Mark ready','in-progress':'Mark in progress (declaration)',blocked:'Put on hold',cancelled:'Cancel task',withdrawn:'Withdraw task'})[value]||value;
export const taskStatusMeaning=value=>({done:'Records completion only when prerequisites, required reviews and evidence allow it. Later evidence checks remain separate.',verified:'Records the offered verified status; it does not automatically establish scientific verification.',open:'Reopens this task. Earlier completion and review records remain in its history.',ready:'Records readiness without starting execution.','in-progress':'Declares progress. It does not start execution or prove an actor is running.',blocked:'Records a hold and its reason. It does not stop an external actor.',cancelled:'Closes this task as cancelled without claiming its goal was completed. Its history remains.',withdrawn:'Closes this task as withdrawn without claiming its goal was completed. Its history remains.'})[value]||'Choose one of the currently offered status changes.';
// the owner's qualified standing as one chip: the group and its leading fact (the full qualification is on inspection)
export function standingChip(row,fallback=()=>({label:'standing not observed',tone:'neutral'})){
  const completed=completedTaskChip(row);if(completed)return completed;const standing=row?.standing;if(!standing?.group||!GROUP_LABELS[standing.group])return fallback(row);
  return {label:GROUP_LABELS[standing.group],tone:GROUP_TONES[standing.group],title:(standing.facts||[]).map(fact=>fact.text).filter(Boolean).join(' · ')};
}
export function workChips(task={}){return taskStateChips(task);}
export function continuationChip(value) {
  if (!value) return null;
  const synthesis = value.synthesis || {};
  switch (value.phase) {
    case 'WAITING': return {label: 'Waiting for dispatched work', tone: 'running'};
    case 'READY':
      if (value.review_state === 'REJECTED') return {label: 'Settled · review rejected', tone: 'attention'};
      if (value.execution_state !== 'COMPLETE') return {label: 'Settled · evidence missing or failed', tone: 'attention'};
      if (synthesis.status === 'VALID') return synthesis.attachment === 'UNCONFIRMED' ? {label: 'Settled · attachment unconfirmed', tone: 'attention'} : {label: synthesis.attachment === 'ATTACHED' ? 'Settled · synthesis attached' : 'Settled · synthesis retained', tone: 'ok'};
      return {label: 'Settled · synthesis needed', tone: 'attention'};
    case 'OBSERVATION_EXPIRED': return {label: 'Wait ended · work retained', tone: 'attention'};
    case 'PARENT_STOPPED': return {label: 'Parent stopped', tone: 'historical'};
    case 'STALE': return {label: 'Inputs changed', tone: 'attention'};
    case 'BLOCKED': return {label: 'Needs recovery', tone: 'blocked'};
    default: return {label: 'Needs reinspection', tone: 'attention'};
  }
}
export function childChip(child = {}) {
  if (!child.state) return {label: words('not observed'), tone: 'neutral'};
  const word = ownerStateWord('dispatch-child', child.state);
  return {label: word.words, tone: word.tone};
}
// ---- owner state words (R6, R14): the one table that turns an owner's state constant into plain words and a shape ----
// Keyed by the owner field the value comes from, because one constant can mean different things in two fields. The
// exact constant is never thrown away: callers keep it beside the words, behind an Identity control. A value missing
// from the table is shown in lower case with the note that the table has no words for it, never guessed.
//   dispatch-child  project_work.dispatch_view children[].state (also app-run steps[].state and river items[].state)
//   host-liveness   child_hosts.child_execution state, as workflow_operations._liveness current_observation reports it
//   run-execution   project_work.dispatch_view execution_state (app-run observation.execution_state)
//   run-review      project_work.dispatch_view review_state (app-run observation.review_state)
//   reply           a turn's recorded reply.status
//   tool-call       workflow_operations._turn_facts tool_calls[].kind (the writing-tool-read/-action/-failure record)
//   attempt-phase   workflow_dispatch.run steps[].current_attempt.phase: a review continuation receipt's phase
//                   (dispatch_execution: RESERVED :794, LAUNCHING :801, ADMITTED :813, UNKNOWN :819), RECORDED otherwise
//   continuation-effect  dispatch_execution.continuation_request effect (:699): RECORDED, NONE or UNKNOWN
//   stream-event    an /authoring/events event type (turn-events.mjs)
//   session         authoring_http._session_index_row state: running/starting from turn_jobs' live row (:282), no-turn (:284),
//                   no-reply (:286), waiting (proposals without a decision, :287-289), else the saved reply status (:291)
//   active-work     turn_jobs.active_work_projection rows[].kind (turn, turn-start, http-mutation; a research-run row is read
//                   through research-run below because its own state is stated)
//   research-run    research_runs.active_runs rows[].state (:220-252, :407, :444, :752, :894-908, :629-632)
//   prepared-turn   prepared_work.executions items[].state (:209-210): RUNNING, the reply status upper-cased, else UNCONFIRMED
//   dependency      dispatch_execution execution.dependency_state, from project_work.dispatch_dependency_state (:897-921)
//   synthesis-attachment  parent continuation synthesis.attachment (the validated set in prepared-work.mjs parentContinuation)
//   goal-standing   a typed return's goal standing (synthesis.retained_status; packet-return.v2 status enum)
//   provider-auth   provider.py _codex_capabilities (:736-758) and _claude_capabilities (:766-775) and provider_catalogue.py
//                   (:189) auth_state
//   development-lane   development_source development-lane rows[].state (LANE_STATES: ACTIVE, ADOPTED, DISCARDED)
//   development-grant  development_source development-grant rows[].state (ACTIVE when issued, REVOKED by revoke or discard);
//                      ACTIVE is the ledger row, not admissibility (development_source STATUS_NOTES)
//   development-check  development_source development-check rows[].state (TERMINAL_CHECK_STATES; REFUSED means no process ran)
export const OWNER_STATE_WORDS = Object.freeze({
  'dispatch-child': {NOT_STARTED: ['Not started', '○', 'neutral'], RUNNING: ['Running', '▶', 'running'], WAITING: ['Waiting', '◷', 'neutral'],
    BLOCKED: ['Blocked', '■', 'blocked'], COMPLETE: ['Returned', '●', 'ok'], 'NO-RETURN': ['Replied without a typed return', '◐', 'neutral'],
    'NO-REPLY': ['Ended without a reply', '◌', 'attention'], 'INVALID-RETURN': ['Typed return invalid', '✕', 'blocked'], STALE: ['Inputs changed', '△', 'attention'],
    FAILED: ['Failed', '✕', 'blocked'], CANCELLED: ['Cancelled', '⊘', 'historical'], UNAVAILABLE: ['Not mapped to a child', '?', 'neutral']},
  'host-liveness': {STARTING: ['starting', '▶', 'running'], RUNNING: ['running', '▶', 'running'], WAITING: ['waiting', '◷', 'neutral'], BLOCKED: ['blocked', '■', 'blocked'],
    FINISHED: ['finished', '●', 'neutral'], FAILED: ['failed', '✕', 'blocked'], ORPHANED: ['lost its host', '✕', 'blocked'], HISTORICAL: ['finished earlier', '●', 'neutral'],
    NO_ADMITTED_TURN: ['no admitted turn', '–', 'neutral'], NOT_THE_CURRENT_EXECUTION: ['a later turn runs in its session', '–', 'neutral'], UNKNOWN: ['unknown', '?', 'neutral']},
  'run-execution': {PLANNED: ['Planned', '○', 'neutral'], STARTING: ['Starting', '▶', 'running'], RUNNING: ['Running', '▶', 'running'], WAITING: ['Waiting', '◷', 'neutral'],
    BLOCKED: ['Blocked', '■', 'blocked'], COMPLETE: ['Complete', '●', 'ok'], FAILED: ['Failed', '✕', 'blocked'], CANCELLED: ['Cancelled', '⊘', 'historical'], UNKNOWN: ['Unknown', '?', 'neutral']},
  'run-review': {PENDING: ['pending', '◷', 'neutral'], ACCEPTED: ['accepted', '●', 'ok'], REJECTED: ['rejected', '✕', 'attention'], UNVERIFIED: ['not verified', '?', 'attention']},
  reply: {completed: ['replied', '●', 'ok'], complete: ['replied', '●', 'ok'], failed: ['failed', '✕', 'blocked'], interrupted: ['stopped', '⊘', 'historical']},
  'tool-call': {read: ['read', '■', 'neutral'], action: ['change', '■', 'ok'], failure: ['refused or failed', '■', 'blocked']},
  'attempt-phase': {RECORDED: ['recorded', '●', 'neutral'], RESERVED: ['reserved, not launched', '○', 'neutral'], LAUNCHING: ['launching', '▶', 'running'],
    ADMITTED: ['admitted', '●', 'ok'], UNKNOWN: ['outcome unknown', '?', 'attention']},
  'continuation-effect': {RECORDED: ['recorded', '●', 'ok'], NONE: ['none', '○', 'neutral'], UNKNOWN: ['unknown', '?', 'attention']},
  session: {running: ['Running', '●', 'running'], starting: ['Starting', '●', 'running'], waiting: ['Waiting for you', '◆', 'attention'],
    completed: ['Finished', '✓', 'ok'], failed: ['Failed', '✕', 'blocked'], interrupted: ['Stopped', '■', 'historical'],
    'no-reply': ['Ended without a saved reply', '○', 'attention'], 'no-turn': ['No turns yet', '○', 'neutral']},
  'active-work': {turn: ['Running', '●', 'running'], 'turn-start': ['Starting', '●', 'running'], 'http-mutation': ['Saving', '●', 'running']},
  'research-run': {RUNNING: ['Running', '●', 'running'], CANCEL_REQUESTED: ['Stop requested', '■', 'attention'], CLEANUP_UNRESOLVED: ['Clean-up unresolved', '?', 'attention'],
    UNAVAILABLE: ['Not readable', '?', 'attention'], UNKNOWN: ['Unknown', '?', 'attention'], CONFLICT: ['Conflicting records', '✕', 'blocked']},
  'prepared-turn': {RUNNING: ['Running', '●', 'running'], COMPLETED: ['Replied', '●', 'ok'], COMPLETE: ['Replied', '●', 'ok'], FAILED: ['Failed', '✕', 'blocked'],
    INTERRUPTED: ['Stopped', '⊘', 'historical'], TERMINAL: ['Ended, reply status not recorded', '○', 'neutral'], UNCONFIRMED: ['Not confirmed', '?', 'attention']},
  dependency: {READY: ['Ready', '●', 'ok'], WAITING: ['Waiting', '◷', 'neutral'], BLOCKED: ['Blocked', '■', 'blocked'], 'FAILURE-REVIEW': ['Ready for failure review', '△', 'attention']},
  'synthesis-attachment': {ATTACHED: ['Attached', '●', 'ok'], MISSING: ['Not attached', '○', 'attention'], UNCONFIRMED: ['Attachment unconfirmed', '?', 'attention']},
  'goal-standing': {COMPLETE: ['Complete', '●', 'ok'], INCOMPLETE: ['Incomplete', '◐', 'attention'], BLOCKED: ['Blocked', '■', 'blocked'], INTERRUPTED: ['Interrupted', '⊘', 'historical'],
    'DEMONSTRATED-IMPOSSIBILITY': ['Shown impossible', '✕', 'blocked']},
  'provider-auth': {READY: ['Ready, listed its models', '●', 'ok'], AUTHENTICATED_UNTESTED: ['Signed in, not yet tested', '◐', 'attention'], UNAUTHENTICATED: ['Not signed in', '✕', 'blocked'],
    UNAUTHENTICATED_OR_UNVERIFIED: ['Not signed in, or could not be checked', '?', 'attention'], UNVERIFIED: ['Not checked yet', '○', 'neutral']},
  'stream-event': {delta: ['reply arriving', '▶', 'running'], progress: ['working', '▶', 'running'], complete: ['finished', '●', 'neutral'], error: ['ended with an error', '✕', 'blocked']},
  'development-lane': {ACTIVE: ['Active', '●', 'ok'], ADOPTED: ['Adopted', '✓', 'ok'], DISCARDED: ['Discarded', '⊘', 'historical']},
  'development-grant': {ACTIVE: ['Active', '●', 'ok'], REVOKED: ['Revoked', '⊘', 'historical']},
  'development-check': {COMPLETE: ['Passed', '●', 'ok'], FAILED: ['Failed', '✕', 'blocked'], TIMEOUT: ['Timed out', '◷', 'attention'],
    CANCELLED: ['Cancelled', '⊘', 'historical'], UNAVAILABLE: ['Could not run', '?', 'attention'], REFUSED: ['Refused, nothing ran', '■', 'blocked']}
});
export function ownerStateWord(field, value) {
  const table = OWNER_STATE_WORDS[field] || {}, hit = value == null ? null : table[String(value)];
  if (hit) return {words: hit[0], shape: hit[1], tone: hit[2], exact: String(value), known: true};
  return {words: value == null || value === '' ? 'not stated' : lower(value) + ' (no plain words for this owner state)', shape: '?', tone: 'neutral', exact: value == null ? null : String(value), known: false};
}
export function evidenceChip(status) {
  const key = String(status || '').toUpperCase();
  if (['MATCH', 'CURRENT', 'SNAPSHOT_MATCH'].includes(key)) return {label: 'Matches recorded bytes', tone: 'ok'};
  if (['CHANGED', 'SNAPSHOT_MISMATCH'].includes(key)) return {label: 'Changed since this record', tone: 'attention'};
  if (key === 'MISSING') return {label: 'File is missing', tone: 'blocked'};
  if (key === 'UNAVAILABLE') return {label: 'Identity unavailable', tone: 'neutral'};
  if (key === 'UNRECORDED') return {label: 'No recorded hash', tone: 'neutral'};
  return {label: words(status || 'Recorded'), tone: 'neutral'};
}
export function inputChip(currentness) {
  const key = String(currentness?.status || currentness || '').toUpperCase();
  if (key === 'CURRENT') return {label: 'Inputs current', tone: 'ok'};
  if (key === 'STALE') return {label: 'Inputs changed', tone: 'attention'};
  if (key === 'UNPINNED') return {label: 'Inputs unpinned', tone: 'neutral'};
  if (key === 'UNOBSERVED') return {label: 'New support not inspected', tone: 'attention'};
  return null;
}
export function bindingChip(source = {}) {
  const precision = source.precision;
  if (precision === 'EXACT_HEADING') return {label: 'Bound to source heading', tone: 'ok', title: source.heading?.title || ''};
  if (precision === 'INFERRED') return {label: 'Source inferred', tone: 'attention', title: source.reason || 'Suggested file; confirm the heading.'};
  if (precision === 'AMBIGUOUS') return {label: 'Source ambiguous', tone: 'attention', title: source.reason || ''};
  if (precision === 'UNRESOLVED') return {label: 'No source link', tone: 'neutral', title: source.reason || ''};
  return null;
}
// `save`: the editor's save line (walk.mjs saveLine: {word, detail, tone, text}, one of the brief's six
// states) or `true` for unsaved changes the line does not cover; it replaces the 'Unsaved edits' chip.
export function documentChips(doc = {}, save = false) {
  const chips = [];
  const build = doc.current_build || {};
  if (build.state === 'cancelling') chips.push({label: 'Stopping build', tone: 'running'});
  else if (build.state === 'cancelled') chips.push({label: 'Last build stopped', tone: 'historical'});
  else chips.push(({
    RUNNING: {label: 'Building PDF', tone: 'running'},
    FAILED: {label: 'Last build failed', tone: 'blocked'},
    READY: {label: 'PDF matches saved document', tone: 'ok'},
    STALE: {label: 'PDF needs rebuilding', tone: 'attention'},
    NOT_BUILT: {label: 'No verified PDF', tone: 'neutral'},
    UNAVAILABLE: {label: 'Document unavailable', tone: 'blocked'}
  })[doc.status] || {label: 'Document status unavailable', tone: 'neutral'});
  if (doc.pdf_identity?.verification === 'OBSERVED_ONLY') chips.push({label: 'Build basis unverified', tone: 'attention', title: 'Existing PDF bytes; the build basis was not verified.'});
  if (save && typeof save === 'object') chips.push({label: save.text, tone: save.tone || 'neutral', title: save.word === 'Saved' ? '' : (save.full || save.text) + ' (unsaved edits are not in the PDF)'});
  else if (save) chips.push({label: 'Unsaved changes', tone: 'attention', title: 'Unsaved edits are not in the PDF.'});
  return chips;
}
export function templateChips(metadata = {}, reviewed = null) {
  const chips = [];
  const basis = metadata.currentness?.status;
  chips.push(({CURRENT: {label: 'Source basis current', tone: 'ok'}, CHANGED_INPUT: {label: 'Source basis changed', tone: 'attention'}, READ_ONLY: {label: 'Read-only source', tone: 'neutral'}, UNAVAILABLE: {label: 'Source basis unavailable', tone: 'blocked'}})[basis] || {label: 'Basis not reported', tone: 'neutral'});
  const build = metadata.build;
  const state = String(build?.state || build?.status || 'UNBUILT').toLowerCase();
  if (!build || state === 'unbuilt') chips.push({label: 'No preview yet', tone: 'neutral'});
  else if (/running|cancelling/.test(state)) chips.push({label: 'Preview building', tone: 'running'});
  else if (/done|ok|succe|complete/.test(state)) chips.push({label: 'Preview built', tone: 'ok'});
  else if (/error|fail/.test(state)) chips.push({label: 'Preview failed', tone: 'blocked', title: build.error || build.reason || ''});
  else if (/cancel/.test(state)) chips.push({label: 'Preview stopped', tone: 'historical'});
  else chips.push({label: 'Preview ' + words(state), tone: 'neutral'});
  if (reviewed) chips.push({label: 'Exact preview reviewed', tone: 'ok', title: 'The opened PDF page qualifies this proof for Apply.'});
  const recording = metadata.application_recording?.status;
  if (recording === 'RECORDED') chips.push({label: 'Application recorded', tone: 'ok'});
  else if (recording === 'UNPUBLISHED') chips.push({label: 'Recording unpublished', tone: 'attention'});
  else if (recording === 'UNKNOWN') chips.push({label: 'Outcome needs inspection', tone: 'attention'});
  return chips;
}

// WHERE A CONTEXT MENU GOES IN ONE VIEWPORT (C12 menu clip, 2026-10-15). At the pointer, moved left/up to fit,
// and never taller than the viewport: a menu taller than the viewport gets maxHeight and scrolls inside itself, so
// every item stays inside the frame for a pointer as well as the keyboard (nothing is placed past the edge).
// point {x, y}, size {w, h} as measured, viewport {w, h}: the frame's own client area. Returns {left, top, maxHeight}.
export function contextMenuPlacement(point, size, viewport, margin = 8) {
  const maxHeight = Math.max(0, viewport.h - 2 * margin), h = Math.min(size.h, maxHeight), w = Math.min(size.w, Math.max(0, viewport.w - 2 * margin));
  return {left: Math.max(margin, Math.min(point.x, viewport.w - w - margin)), top: Math.max(margin, Math.min(point.y, viewport.h - h - margin)), maxHeight};
}

// ---- cards ----
export function action({label, run, kind = 'read', primary = false, disabled = false, title = '', onError = null} = {}) {
  const button = el('button', label, 'act act-' + kind + (primary ? ' primary' : ''));
  button.type = 'button';
  if (title) button.title = title;
  button.disabled = !!disabled;
  button.onclick = async () => {
    if (button.disabled) return;
    // the explicit action's intent, read before the control changes (M5-R2): the activated control is the
    // place the person acted from, whatever a browser does with focus once the control is disabled
    const intent = {active: button};
    button.disabled = true;
    try {await run(button, intent);}
    catch (error) {
      if (onError) onError(error);
      else {const host = button.parentElement; host?.querySelector?.('.act-error')?.remove(); const note = el('p', error.message, 'act-error error'); note.setAttribute('role', 'alert'); if (typeof button.after === 'function') button.after(note); else host?.append?.(note);}
    } finally {if (button.isConnected !== false) button.disabled = !!disabled;}
  };
  return button;
}
export function actionRow(actions = []) {
  const row = el('div', '', 'action-row');
  for (const item of actions) if (item) row.append(isNode(item) ? item : action(item));
  return row;
}
export function objectHeader({eyebrow = '', title = '', chips = [], summary = '', actions = [], level = 'h3', focusTarget = ''} = {}) {
  const header = el('header', '', 'object-header');
  if (eyebrow) header.append(el('span', eyebrow, 'object-eyebrow'));
  const heading = el(level, title, 'object-title');
  // A deliberate focus destination for one owner's explicit navigation (S2): programmatically
  // focusable, never a tab stop, and named so its owner can find its own heading.
  if (focusTarget) {heading.tabIndex = -1; heading.dataset.focusTarget = focusTarget;}
  header.append(heading);
  if (chips.length) header.append(chipRow(chips));
  if (summary) header.append(el('p', summary, 'object-summary'));
  if (actions.length) header.append(actionRow(actions));
  return header;
}
export function relationList(rows = [], {emptyText = ''} = {}) {
  const list = el('ul', '', 'relation-list');
  for (const row of rows) {
    const item = el('li', '', 'relation');
    // the leading end is a door when the row says so (a readable boundary source), else a label
    if (row.kind) item.append(row.kindRun ? (row.kindControl ? declareControl : n => n)(action({label: row.kind, run: row.kindRun, kind: 'read', title: row.kindTitle || '', onError: row.onError || null}), row.kindControl, row.kindOwner) : el('span', row.kind, 'relation-kind'));
    if (row.run) { const door = action({label: row.label, run: row.run, kind: row.actionKind || 'read', disabled: row.disabled, title: row.title || '', onError: row.onError || null}); if (row.control) { door.dataset.control = row.control; if (row.owner != null) door.dataset.controlOwner = String(row.owner); } item.append(door); }
    else item.append(el('span', row.label, 'relation-label'));
    for(const mark of row.chips||(row.chip?[row.chip]:[]))item.append(stateChip(mark));
    if (row.note) item.append(el('small', row.note, 'relation-note'));
    list.append(item);
  }
  if (!rows.length && emptyText) list.append(el('li', emptyText, 'relation muted'));
  return list;
}
// A grouped menu (M5 C7 passage menu; repair H3): group headings are presentation, never
// focus targets; the first ENABLED actionable item is the focus target after assembly.
// `groups` is an ordered list of [title, items]; empty groups are skipped. Returns the item to
// focus (or null) so the opener can call focus() on an actual menuitem, not a heading.
export function groupedMenu(menu, groups, {heading = title => {const node = el('div', title, 'manuscript-context-group'); node.setAttribute('role', 'presentation'); return node;}} = {}) {
  let first = null;
  for (const [title, items] of groups) {
    if (!items || !items.length) continue;
    menu.append(heading(title), ...items);
    if (!first) first = items.find(item => item && !item.disabled && (item.tagName === 'BUTTON' || item.tag === 'button' || item.getAttribute?.('role') === 'menuitem')) || null;
  }
  return first;
}
// A deliberate inspect action. Loads once, surfaces its own failure, and never pretends
// the exact read happened before it did.
export function lazySection({label, load = async () => null, render, open = false, hideLabel = 'Hide', cls = '', control = ''} = {}) {
  const section = el('section', '', 'lazy-section ' + cls), toggle = el('button', label, 'act act-read lazy-toggle'), body = el('div', '', 'lazy-body');
  if (control) declareControl(toggle, control);
  toggle.type = 'button'; toggle.setAttribute('aria-expanded', 'false'); body.hidden = true; section.append(toggle, body);
  let loaded = false, loading = false, value;
  async function show() {
    if (loading) return; body.hidden = false; toggle.textContent = hideLabel; toggle.setAttribute('aria-expanded', 'true');
    if (loaded) return;
    loading = true; body.replaceChildren(pendingRead(el('p', 'Loading…', 'muted')));
    try {value = await load(); if (!section.isConnected && section.isConnected !== undefined) return; body.replaceChildren(); await render(body, value); loaded = true;}
    catch (error) {const note = el('p', error.message, 'error'); note.setAttribute('role', 'alert'); body.replaceChildren(note, action({label: 'Retry', run: async () => {loaded = false; await show();}}));}
    finally {loading = false;}
  }
  function hide() {body.hidden = true; toggle.textContent = label; toggle.setAttribute('aria-expanded', 'false');}
  toggle.onclick = () => body.hidden ? show() : hide();
  if (open) void show();
  section.show = show; section.hide = hide;
  Object.defineProperty(section, 'loaded', {get: () => loaded});
  return section;
}
export function clippedText(text, {lines = 12, cls = ''} = {}) {
  const all = String(text ?? '').split('\n'), wrap = el('div', '', 'clipped ' + cls), pre = el('pre', '', 'clipped-text');
  const clipped = all.length > lines;
  pre.textContent = clipped ? all.slice(0, lines).join('\n') : all.join('\n');
  wrap.append(pre);
  if (clipped) {
    const more = el('button', 'Show all ' + all.length + ' lines', 'act act-read clipped-more'); more.type = 'button'; let full = false;
    more.onclick = () => {full = !full; pre.textContent = full ? all.join('\n') : all.slice(0, lines).join('\n'); more.textContent = full ? 'Show first ' + lines + ' lines' : 'Show all ' + all.length + ' lines';};
    wrap.append(more);
  }
  return wrap;
}
// One recorded hunk: the owner's title (file · recorded lines) and before/after text,
// clipped. The owner supplied the text; nothing is diffed or reconstructed here.
export function hunkCard(comparison = {}, {index = null, total = null, lines = 8} = {}) {
  const card = el('article', '', 'hunk-card');
  const head = el('header', '', 'hunk-head');
  head.append(el('strong', comparison.title || 'Recorded change', 'hunk-title'));
  if (index != null && total != null) head.append(el('span', index + ' of ' + total, 'hunk-index muted'));
  card.append(head);
  const columns = el('div', '', 'hunk-columns');
  for (const [key, label] of [['before', 'Before'], ['after', 'After']]) {
    if (comparison[key] === null || comparison[key] === undefined) {if (key === 'before') continue; }
    const side = el('section', '', 'hunk-side'); side.append(el('span', label, 'hunk-side-label'));
    side.append(comparison[key] === '' ? el('p', '[Empty passage]', 'muted') : comparison[key] == null ? el('p', 'Not recorded', 'muted') : clippedText(comparison[key], {lines}));
    columns.append(side);
  }
  if (comparison.before == null && comparison.after != null) data(columns, 'columns', '1');
  card.append(columns);
  if (comparison.note) card.append(el('p', comparison.note, 'hunk-note muted'));
  if (comparison.basis) card.append(el('small', typeof comparison.basis === 'string' ? comparison.basis : JSON.stringify(comparison.basis), 'hunk-basis muted'));
  return card;
}
// Numbered exposition order; the number is reading order only, never dependency.
export function orderedPlan(items = [], {current = null, onSelect = () => {}, onError = null, control = null} = {}) {
  const list = el('ol', '', 'ordered-plan');
  items.forEach((item, position) => {
    const row = el('li', '', 'ordered-plan-item'), button = el('button', '', 'ordered-plan-button');
    if (item.depth) data(row, 'depth', String(Math.min(item.depth, 3)));
    button.type = 'button'; data(button, 'planId', item.id);
    if (control) {button.setAttribute('data-control', control); if (item.owner) button.setAttribute('data-control-owner', item.owner);}
    // accessible name: the object with its order ("Section 3 · Title"), never the number alone
    button.setAttribute('aria-label', 'Section ' + String(item.number ?? position + 1) + ' · ' + (item.title || item.id));
    button.append(el('span', String(item.number ?? position + 1), 'ordered-plan-number'));
    const text = el('span', '', 'ordered-plan-text');
    text.append(el('span', item.title || item.id, 'ordered-plan-title'));
    if (item.purpose) text.append(el('span', item.purpose, 'ordered-plan-purpose'));
    button.append(text);
    if (item.mark) {const mark = stateChip({label: '', tone: item.mark.tone, title: item.mark.title || item.mark.label || ''}); mark.className += ' ordered-plan-mark'; mark.setAttribute('aria-label', item.mark.label || item.mark.title || ''); button.append(mark);}
    if (item.id === current) {button.setAttribute('aria-current', 'true'); data(row, 'current', 'true');}
    button.onclick = async () => {try {await onSelect(item);} catch (error) {if (onError) onError(error); else throw error;}};
    row.append(button); list.append(row);
  });
  return list;
}
// Who is doing what, where: one ladder for parent, children, returns and synthesis.
// Rows are plain descriptors the continuation/dispatch owners' validators prepared;
// nothing here reads a dispatch or infers completion.
export function coordinationLadder(host, {rows = [], compact = false, title = ''} = {}) {
  const ladder = el('section', '', 'coordination' + (compact ? ' coordination-compact' : ''));
  if (title) ladder.append(el('h4', title, 'coordination-title'));
  const paint = (row, depth = 0) => {
    const line = el('div', '', 'coordination-row'); data(line, 'role', row.role || 'row'); data(line, 'depth', String(Math.min(depth, 3)));
    const head = el('div', '', 'coordination-head');
    head.append(el('span', row.who || '', 'coordination-who'));
    if (row.chip) head.append(stateChip(row.chip));
    if (row.what) head.append(el('span', row.what, 'coordination-what'));
    line.append(head);
    if (!compact && row.facts?.length) {const facts = el('div', '', 'coordination-facts'); for (const fact of row.facts) facts.append(el('span', fact, 'coordination-fact')); line.append(facts);}
    for (const error of row.errors || []) {const note = el('p', error, 'coordination-error error'); note.setAttribute('role', 'alert'); line.append(note);}
    if (row.actions?.length) line.append(actionRow(row.actions));
    ladder.append(line);
    for (const child of row.children || []) paint(child, depth + 1);
  };
  for (const row of rows) paint(row);
  host.append(ladder);
  return ladder;
}
export function presentationStyles() {
  // Loads the shared stylesheet once; inert outside a real document (test doubles).
  if (typeof document === 'undefined' || !document.head || typeof document.querySelector !== 'function' || document.querySelector('[data-workspace-presentation]')) return;
  const css = el('link'); css.rel = 'stylesheet'; css.href = '/shared/workspace-presentation.css'; css.setAttribute('data-workspace-presentation', '');
  document.head.append(css);
}
