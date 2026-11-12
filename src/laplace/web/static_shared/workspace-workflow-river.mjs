// THE RUN RIVER (wave 11). Under a run's drawing on the Workflows page: one lane per step, time left to right, the
// step's turns, tool calls and replies, and the prepared dependencies between steps, read from the workflow owner and
// re-read by itself while a step is observed running. Every mark is painted from ONE array (workflowRiverModel) that
// also paints the text list, as workspace-topology.mjs paints its drawing and its list from one layout.
// Reads (all issued by owners; this module composes no URL):
//   the run's observed flow: the app-run read's observation_reads.river, followed through readWorkflowOperation
//     (workflow_operations river facet: rows with their turn's times and tool-call identities, current_observation)
//   on a mark's card, only when asked: a row's reads.reply / reads.proposal / reads.typed_return (GET as issued) and
//     reads.conversation.project_url (the project page with ?session=, through the editor's openConversation)
//   for a running step: its reads.conversation.session_read, then the turn's own events_url (turn-events.mjs)
// State words come from workspace-presentation.mjs ownerStateWord; the exact constant stays behind Identity.
import {ownerStateWord, OWNER_STATE_WORDS} from './workspace-presentation.mjs';
import {readWorkflowOperation} from './workspace-workflow-operation.mjs';
import {openTurnEvents, progressWords} from './turn-events.mjs';

export const RIVER_READ_INTERVAL_MS = 5000;
export const RIVER_LANE_PX = 48;
const AXIS = 48, PAD = 24, HIT = 40, MIN_PPS = 20;
// The marks the painter draws, in the order of the legend. The legend line on the page is generated from this table.
export const RIVER_MARKS = Object.freeze([
  {kind: 'turn', shape: '▬', name: 'Bar', says: 'a turn, from its start to its reply (open at the right while it runs)'},
  {kind: 'tool', shape: '■', name: 'Square', says: 'a tool call'},
  {kind: 'reply', shape: '●', name: 'Circle', says: 'a reply; its mark is its recorded status: ' + replyShapes().map(([shape, words]) => shape + ' ' + words).join(', ')},
  {kind: 'handover', shape: '→', name: 'Arrow', says: 'a prepared dependency, from a reply to the start of the step that waits on it'}]);
// The reply marks, one per distinct shape of the owner's reply-status words (workspace-presentation.mjs 'reply').
function replyShapes() { const seen = new Map(); for (const [words, shape] of Object.values(OWNER_STATE_WORDS.reply)) if (!seen.has(shape)) seen.set(shape, words); return [...seen].concat([['?', 'status not stated']]); }
export const riverLegend = () => RIVER_MARKS.map(mark => mark.shape + ' ' + mark.name + ': ' + mark.says).join(' · ');

const el = (tag, text = '', cls = '') => { const node = document.createElement(tag); if (text) node.textContent = text; if (cls) node.className = cls; return node; };
const button = (label, run, control, owner = null) => { const node = el('button', label); node.type = 'button'; node.onclick = run; node.dataset.control = control; if (owner) node.dataset.controlOwner = owner; return node; };
const svgNode = (tag, attrs = {}) => { const node = document.createElementNS('http://www.w3.org/2000/svg', tag); for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v)); return node; };
// A label's drawn width; 13 px digits are about 8 px wide where the browser cannot measure (tests, a detached box).
export const axisLabelFits = (x0, wide, left, right) => x0 >= left && x0 + wide <= right;
const axisWidth = label => { try { const w = label.getComputedTextLength?.(); if (w > 0) return w; } catch {} return 8 * String(label.textContent || '').length; };
// The reply mark for one shape of the owner's reply words: ● filled circle, ✕ a cross in a ring, ⊘ a ring with a slash,
// ? (status not stated) a dashed ring.
function replyGlyph(shape, cx, cy) {
  const ring = cls => svgNode('circle', {cx, cy, r: 8, class: 'workflow-river-shape ' + cls});
  if (shape === '●') return [ring('reply-done')];
  if (shape === '✕') return [ring('reply-ring'), svgNode('path', {d: `M${cx - 5},${cy - 5} L${cx + 5},${cy + 5} M${cx + 5},${cy - 5} L${cx - 5},${cy + 5}`, class: 'workflow-river-glyph'})];
  if (shape === '⊘') return [ring('reply-ring'), svgNode('path', {d: `M${cx - 6},${cy + 6} L${cx + 6},${cy - 6}`, class: 'workflow-river-glyph'})];
  return [ring('reply-ring reply-unknown')];
}
export const riverTime = value => { if (typeof value === 'number' && Number.isFinite(value)) return value > 1e12 ? value : value * 1000; if (typeof value !== 'string' || !value) return null; const t = Date.parse(value); return Number.isFinite(t) ? t : null; };
const two = n => String(n).padStart(2, '0');
export const clock = ms => { if (ms == null) return 'time not recorded'; const d = new Date(ms); return two(d.getHours()) + ':' + two(d.getMinutes()) + ':' + two(d.getSeconds()); };
const liveness = (river, row) => river?.current_observation?.by_turn?.[row?.turn_id] || null;
export const riverRowRunning = (river, row) => ['RUNNING', 'STARTING'].includes(liveness(river, row)?.observed);

// The settings a step ran with, in the order the owner ranks them: admitted (row settings), then the provider settings
// recorded on its turn (what the admitted turn was started with), then prepared (row settings, else the run's pinned
// preparation). Each answer says which.
export function riverStepSettings(row, prepared = null) {
  const pick = value => value && (value.provider || value.model) ? {provider: value.provider || null, model: value.model || null, effort: value.effort || null} : null;
  const admitted = pick(row?.settings?.admitted), recorded = pick(row?.turn?.provider_settings), planned = pick(row?.settings?.prepared) || pick(prepared);
  if (admitted) return {...admitted, source: 'admitted'};
  if (recorded) return {...recorded, source: 'admitted, recorded on its turn'};
  if (planned) return {...planned, source: 'prepared'};
  return null;
}

// What waits on the author, from owner fields only. One kind is stated by this owner today: an app-run step whose
// continue_action is permitted (workflow_dispatch.run steps[].continue_action.permitted).
export function workflowRiverWaiting(run) {
  return (Array.isArray(run?.steps) ? run.steps : []).filter(step => step?.continue_action?.permitted === true && step.continue_action.available !== false)
    .map(step => ({step_id: step.step_id, field: 'continue_action.permitted', words: (step.continue_action.label || 'A continue action') + ' is offered to you'}));
}

// The one array: lanes in the drawing's order and every mark with its text row.
export function workflowRiverModel({river, order = [], titles = {}, dependencies = null, failed = false, lastGoodAt = null} = {}) {
  const rows = Array.isArray(river?.items) ? river.items : [], readAt = riverTime(river?.current_observation?.observed_at) ?? riverTime(river?.observed_at);
  const ids = [...order.filter(id => typeof id === 'string'), ...rows.map(row => row.step_id).filter(id => typeof id === 'string' && !order.includes(id))].filter((id, i, all) => all.indexOf(id) === i);
  const title = id => titles[id] || rows.find(row => row.step_id === id)?.title || id;
  const lanes = ids.map(id => ({step_id: id, title: title(id), rows: rows.filter(row => row.step_id === id)}));
  const marks = [], untimed = [], notes = [];
  for (const row of rows) {
    const name = title(row.step_id), turn = row.turn, running = riverRowRunning(river, row);
    if (!turn) { if (row.turn_id) untimed.push({id: 'turn:' + row.turn_id, kind: 'turn', step_id: row.step_id, row, text: name + ': turn ' + row.turn_id + ' · time not recorded'}); continue; }
    const start = riverTime(turn.started_at), replied = riverTime(turn.replied_at), stale = failed && running;
    const end = replied ?? (running ? (stale ? lastGoodAt : readAt) : null);
    const said = replied != null ? ', replied ' + clock(replied) : running ? (stale ? ', running when last read · last known ' + clock(lastGoodAt) : ', observed running at ' + clock(readAt)) : ', no reply recorded';
    const turnMark = {id: 'turn:' + row.turn_id, kind: 'turn', step_id: row.step_id, row, at: start, end, running: running && !stale, lastKnown: stale ? lastGoodAt : null, text: name + ': turn started ' + clock(start) + said};
    (start == null ? untimed : marks).push(start == null ? {...turnMark, text: name + ': turn ' + row.turn_id + said + ' · start time not recorded'} : turnMark);
    if (replied != null) marks.push({id: 'reply:' + row.turn_id, kind: 'reply', step_id: row.step_id, row, at: replied, text: name + ': ' + ownerStateWord('reply', turn.reply_status).words + ' at ' + clock(replied)});
    for (const call of Array.isArray(turn.tool_calls) ? turn.tool_calls : []) {
      const at = riverTime(call.at), mark = {id: 'tool:' + (call.id || row.turn_id + ':' + call.operation + ':' + call.at), kind: 'tool', step_id: row.step_id, row, call, at, text: name + ': tool call, ' + ownerStateWord('tool-call', call.kind).words + ' through ' + (call.operation || 'an unnamed operation') + ' · ' + clock(at)};
      (at == null ? untimed : marks).push(mark);
    }
    if (Number.isSafeInteger(turn.tool_calls_total) && turn.tool_calls_total > (turn.tool_calls || []).length) notes.push(name + ': ' + (turn.tool_calls_total - turn.tool_calls.length) + ' more tool calls are recorded than the owner lists here.');
  }
  const deps = dependencies || river?.prepared_dependencies;
  // An arrow is drawn only where the waiting step started at or after the reply it waits on.
  if (deps?.status === 'AVAILABLE') for (const edge of deps.edges || []) {
    const from = marks.filter(m => m.kind === 'reply' && m.step_id === edge.prerequisite_step_id).sort((a, b) => b.at - a.at)[0];
    const to = marks.filter(m => m.kind === 'turn' && m.step_id === edge.dependent_step_id).sort((a, b) => a.at - b.at)[0];
    if (from && to && from.at <= to.at) marks.push({id: 'handover:' + edge.prerequisite_step_id + '>' + edge.dependent_step_id, kind: 'handover', step_id: edge.dependent_step_id, from, to, at: to.at, source: 'prepared_dependencies',
      text: title(edge.prerequisite_step_id) + ' → ' + title(edge.dependent_step_id) + ': ' + title(edge.dependent_step_id) + ' waits on ' + title(edge.prerequisite_step_id) + ' in this run’s prepared dependencies; it started ' + clock(to.at) + '. No hand-over receipt is recorded for it.'});
  }
  const times = marks.flatMap(m => [m.at, m.end]).filter(t => t != null), live = rows.some(row => riverRowRunning(river, row));
  const start = times.length ? Math.min(...times) : null, end = times.length ? Math.max(...times, live && !failed && readAt ? readAt : -Infinity) : null;
  marks.sort((a, b) => a.at - b.at || a.id.localeCompare(b.id));
  return {lanes, marks, untimed, notes, start, end, live, readAt};
}

// The sentence a card opens with, from the owner's facts of one mark or one step.
export function riverMarkSentence(mark, model) {
  if (!mark) return '';
  if (mark.kind === 'handover') return mark.text;
  const lane = model.lanes.find(l => l.step_id === mark.step_id), name = lane?.title || mark.step_id;
  if (mark.kind === 'reply') { const waiting = model.marks.filter(m => m.kind === 'handover' && m.from === mark).map(m => model.lanes.find(l => l.step_id === m.step_id)?.title); return name + ' ' + ownerStateWord('reply', mark.row.turn?.reply_status).words + ' · ' + clock(mark.at) + (waiting.length ? ' · started after it: ' + waiting.join(', ') + ' (prepared dependency)' : ''); }
  if (mark.kind === 'tool') return name + ' made a tool call · ' + ownerStateWord('tool-call', mark.call.kind).words + ' through ' + (mark.call.operation || 'an unnamed operation') + ' · ' + clock(mark.at);
  return mark.text;
}

export function mountWorkflowRiver(host, {offer, run = null, order = [], titles = {}, dependencies = null, request, expected = {}, isCurrent = () => true, interval = RIVER_READ_INTERVAL_MS,
  onModel = () => {}, openConversation = null, prepared = () => null, stepDetail = null, onSelectStep = null} = {}) {
  // stepDetail(stepId, place): the caller paints the step's recorded detail (its result, conversation, continuation,
  // earlier attempts, typed return and exact data) into this card, so a step has ONE card; it returns
  // {conversation: true} when it painted the step's own conversation control. onSelectStep(stepId) is told when a step
  // card opens here (a lane label, the waiting pill), so the caller can read that step's record.
  const root = el('section', '', 'workflow-river'); root.dataset.workflowRiver = '';
  const byline = el('p', 'Reading the observed flow…', 'workflow-river-byline'); byline.setAttribute('role', 'status');
  const waitingSlot = el('div', '', 'workflow-river-waiting');
  const head = el('div', '', 'workflow-river-head'), legend = el('p', riverLegend(), 'workflow-river-legend');
  head.append(el('h3', 'Observed flow'));
  const body = el('div', '', 'workflow-river-body'), box = el('div', '', 'workflow-river-box'), labels = el('div', '', 'workflow-river-labels'), scroller = el('div', '', 'workflow-river-scroll');
  labels.setAttribute('aria-label', 'Steps of this run'); scroller.tabIndex = 0; scroller.setAttribute('aria-label', 'Observed flow, time running left to right');
  box.append(labels, scroller);
  const card = el('section', '', 'workflow-river-card'); card.hidden = true; card.setAttribute('aria-live', 'polite');
  body.append(box, card);
  const tools = el('div', '', 'workflow-river-tools'), follow = button('Follow now', () => resume(), 'workflow:river-follow'); follow.hidden = true;
  const listToggle = button('List every mark', () => { list.hidden = !list.hidden; listToggle.textContent = list.hidden ? 'List every mark' : 'Hide the list of marks'; listToggle.setAttribute('aria-expanded', String(!list.hidden)); }, 'workflow:river-list');
  listToggle.setAttribute('aria-expanded', 'false');
  const notesLine = el('p', '', 'workflow-river-notes'); notesLine.hidden = true;
  const list = el('ol', '', 'workflow-river-list'); list.hidden = true; list.setAttribute('aria-label', 'Every mark of the observed flow, in time order');
  tools.append(follow, listToggle);
  root.append(head, legend, body, tools, notesLine, list);
  host.append(root);

  let alive = true, value = null, model = null, readAt = null, lastGoodAt = null, failure = null, timer = null, epoch = 0, busy = false;
  let following = true, frozenPps = null, newCount = 0, known = null, selected = null, identityOpen = false, reading = null, programmatic = false;
  const streams = new Map(), activity = new Map();
  const current = () => alive && root.isConnected !== false && isCurrent();
  const visible = () => !globalThis.document?.hidden;
  const onVisibility = () => { if (!current()) return; if (visible() && wantLive()) { clearTimeout(timer); timer = null; load(); } else if (!visible()) { clearTimeout(timer); timer = null; } };
  document.addEventListener?.('visibilitychange', onVisibility);
  scroller.addEventListener?.('scroll', () => { fitAxis(); if (programmatic) return; if (scroller.scrollLeft + scroller.clientWidth < scroller.scrollWidth - 8 && following) pause(); });
  const wantLive = () => !!model?.live;
  // The scroller's visible width changes when the card opens beside it or the window is resized: labels are refitted.
  const resized = typeof ResizeObserver === 'function' ? new ResizeObserver(() => fitAxis()) : null; resized?.observe(scroller);

  function pause() { if (!following) return; following = false; frozenPps = lastPps; newCount = 0; paintTools(); }
  function resume() { following = true; frozenPps = null; newCount = 0; paint(); }
  function schedule() { clearTimeout(timer); timer = null; if (current() && wantLive() && visible()) timer = setTimeout(() => load(), interval); }

  async function load() {
    if (!current() || busy) return false; busy = true; const ticket = ++epoch;
    try {
      const fresh = await readWorkflowOperation(offer, {}, {request, expected, isCurrent: () => ticket === epoch && current()});
      if (!fresh || ticket !== epoch || !current()) return false;
      value = fresh; failure = null; readAt = riverTime(fresh.current_observation?.observed_at) ?? riverTime(fresh.observed_at) ?? Date.now(); lastGoodAt = readAt;
      model = workflowRiverModel({river: fresh, order, titles, dependencies: dependencies || fresh.prepared_dependencies});
      const ids = new Set([...model.marks, ...model.untimed].map(m => m.id));
      if (known && !following) newCount += [...ids].filter(id => !known.has(id)).length;
      known = ids; paint(); syncStreams(); return true;
    } catch (error) {
      if (ticket !== epoch || !current()) return false;
      failure = {at: Date.now(), message: error?.message || 'The read failed.'};
      if (value) model = workflowRiverModel({river: value, order, titles, dependencies: dependencies || value.prepared_dependencies, failed: true, lastGoodAt});
      paint(); return false;
    } finally { busy = false; if (ticket === epoch) schedule(); }
  }

  // A running step's activity word, from that turn's own event stream (turn-events.mjs).
  function syncStreams() {
    const running = new Map((value?.items || []).filter(row => riverRowRunning(value, row) && row.turn_id).map(row => [row.turn_id, row]));
    for (const [turn, source] of streams) if (!running.has(turn)) { source?.close?.(); streams.delete(turn); activity.delete(turn); }
    for (const [turn, row] of running) {
      if (streams.has(turn)) continue; const read = row.reads?.conversation?.session_read?.http;
      if (!read?.url || (read.method || 'GET') !== 'GET' || typeof EventSource !== 'function') continue;
      streams.set(turn, null);
      request(read.url).then(summary => {
        if (!current() || !streams.has(turn) || streams.get(turn)) return;
        const active = summary?.active; if (active?.id !== turn || !active.capabilities?.events_url) { streams.delete(turn); return; }
        const source = openTurnEvents(active.capabilities.events_url, turn, {after: active.cursor, onError: () => { source?.close?.(); if (streams.get(turn) === source) streams.set(turn, false); },
          onEvent: item => { if (!current() || streams.get(turn) !== source) return;
            const word = item.type === 'progress' && item.text ? 'working · ' + progressWords(item.text).toLowerCase() : ownerStateWord('stream-event', item.type).words;
            activity.set(turn, word); paintActivity();
            if (item.type === 'complete' || item.type === 'error') { source.close(); streams.set(turn, false); load(); } }});
        streams.set(turn, source || false);
      }).catch(() => { streams.set(turn, false); });
    }
  }
  function paintActivity() { onModel(model, {activity, failure, readAt, lastGoodAt}); if (selected) paintCard(); }

  let lastPps = null;
  function paint() {
    if (!current()) return;
    paintByline(); paintWaiting();
    labels.replaceChildren(); list.replaceChildren();
    const keepLeft = scroller.scrollLeft;
    scroller.replaceChildren();
    if (!model) { onModel(model, {activity, failure, readAt, lastGoodAt}); return; }
    for (const lane of model.lanes) {
      const label = button(lane.title, () => select('step:' + lane.step_id), 'workflow:river-step', lane.step_id);
      label.style.height = RIVER_LANE_PX + 'px'; label.setAttribute('aria-pressed', String(selected === 'step:' + lane.step_id)); labels.append(label);
    }
    labels.style.paddingTop = AXIS + 'px';
    const width = Math.max(240, scroller.clientWidth || 0), span = model.start == null ? 0 : Math.max(1, (model.end - model.start) / 1000);
    const fit = (width - 2 * PAD) / Math.max(span, 1), pps = following ? Math.max(fit, Math.min(MIN_PPS, (6 * width) / Math.max(span, 1))) : (frozenPps || fit);
    lastPps = pps;
    const worldW = Math.max(width, Math.ceil(2 * PAD + span * pps + (model.marks.some(m => m.lastKnown) ? 180 : 0))), worldH = AXIS + model.lanes.length * RIVER_LANE_PX;
    const x = t => PAD + ((t - model.start) / 1000) * pps, laneY = id => AXIS + Math.max(0, model.lanes.findIndex(l => l.step_id === id)) * RIVER_LANE_PX + RIVER_LANE_PX / 2;
    const svg = svgNode('svg', {width: worldW, height: worldH, class: 'workflow-river-svg', role: 'group', 'aria-label': 'Observed flow marks'});
    const defs = svgNode('defs'), marker = svgNode('marker', {id: 'workflow-river-arrow', viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 8, markerHeight: 8, orient: 'auto-start-reverse'});
    marker.append(svgNode('path', {d: 'M 0 0 L 10 5 L 0 10 z', class: 'workflow-river-arrowhead'})); defs.append(marker); svg.append(defs);
    model.lanes.forEach((lane, i) => svg.append(svgNode('line', {x1: 0, x2: worldW, y1: AXIS + (i + 1) * RIVER_LANE_PX, y2: AXIS + (i + 1) * RIVER_LANE_PX, class: 'workflow-river-lane-rule'})));
    if (model.start != null) {
      const step = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200].find(s => s * pps >= 96) || 7200;
      for (let t = Math.ceil(model.start / 1000 / step) * step * 1000; t <= model.end + 1; t += step * 1000) {
        svg.append(svgNode('line', {x1: x(t), x2: x(t), y1: AXIS - 4, y2: worldH, class: 'workflow-river-tick'}));
        const label = svgNode('text', {x: x(t) + 4, y: AXIS - 10, class: 'workflow-river-axis', 'data-axis': ''}); label.textContent = clock(t); svg.append(label);
      }
      if (model.live && !failure && model.readAt != null) {
        svg.append(svgNode('line', {x1: x(model.readAt), x2: x(model.readAt), y1: 0, y2: worldH, class: 'workflow-river-now'}));
        const now = svgNode('text', {x: x(model.readAt) - 6, y: 15, class: 'workflow-river-axis workflow-river-now-label', 'text-anchor': 'end', 'data-axis': 'end'}); now.textContent = 'now ' + clock(model.readAt); svg.append(now);
      }
    }
    const order = ['handover', 'turn', 'tool', 'reply'];
    for (const mark of [...model.marks].sort((a, b) => order.indexOf(a.kind) - order.indexOf(b.kind))) {
      const g = svgNode('g', {class: 'workflow-river-mark ' + mark.kind + (mark.running ? ' running' : '') + (mark.lastKnown ? ' last-known' : '') + (selected === mark.id ? ' selected' : ''), role: 'button', tabindex: 0, 'aria-label': mark.text, 'data-control': 'workflow:river-mark', 'data-control-owner': mark.id, 'data-mark': mark.id});
      const y = laneY(mark.step_id);
      if (mark.kind === 'turn') {
        const x1 = x(mark.at), x2 = mark.end != null ? Math.max(x1 + 4, x(mark.end)) : x1 + 10;
        g.append(svgNode('rect', {x: x1 - 2, y: y - HIT / 2, width: Math.max(HIT, x2 - x1 + 4), height: HIT, class: 'workflow-river-hit'}));
        g.append(svgNode('rect', {x: x1, y: y - 8, width: x2 - x1, height: 16, rx: 3, class: 'workflow-river-shape' + (mark.end == null ? ' open' : '')}));
        if (mark.running) g.append(svgNode('path', {d: `M${x2},${y - 11} L${x2 + 11},${y} L${x2},${y + 11} z`, class: 'workflow-river-running-tip'}));
        if (mark.lastKnown) { const note = svgNode('text', {x: x2 + 8, y: y + 5, class: 'workflow-river-axis'}); note.textContent = 'last known ' + clock(mark.lastKnown); g.append(note); }
      } else if (mark.kind === 'reply') {
        const word = ownerStateWord('reply', mark.row.turn?.reply_status); g.setAttribute('data-reply-shape', word.shape); g.setAttribute('class', g.getAttribute('class') + ' tone-' + word.tone);
        g.append(svgNode('rect', {x: x(mark.at) - HIT / 2, y: y - HIT / 2, width: HIT, height: HIT, class: 'workflow-river-hit'}), ...replyGlyph(word.shape, x(mark.at), y));
      } else if (mark.kind === 'tool') {
        g.append(svgNode('rect', {x: x(mark.at) - HIT / 2, y: y - HIT / 2, width: HIT, height: HIT, class: 'workflow-river-hit'}), svgNode('rect', {x: x(mark.at) - 6, y: y - 6, width: 12, height: 12, class: 'workflow-river-shape'}));
      } else {
        const ax = x(mark.from.at), ay = laneY(mark.from.step_id), bx = x(mark.to.at), by = laneY(mark.to.step_id), mx = (ax + bx) / 2, my = (ay + by) / 2;
        g.append(svgNode('rect', {x: mx - HIT / 2, y: my - HIT / 2, width: HIT, height: HIT, class: 'workflow-river-hit'}), svgNode('path', {d: `M${ax},${ay} C${mx},${ay} ${mx},${by} ${bx - 2},${by}`, class: 'workflow-river-shape', 'marker-end': 'url(#workflow-river-arrow)'}));
      }
      g.addEventListener('click', () => select(mark.id));
      g.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select(mark.id); } });
      svg.append(g);
    }
    scroller.append(svg);
    programmatic = true;
    scroller.scrollLeft = following ? scroller.scrollWidth : keepLeft;
    fitAxis();
    setTimeout(() => { programmatic = false; }, 0);
    for (const mark of [...model.marks, ...model.untimed]) { const li = el('li'), open = button(mark.text, () => select(mark.id), 'workflow:river-mark', mark.id); if (mark.at == null) open.textContent = mark.text.includes('time not recorded') ? mark.text : mark.text + ' · time not recorded'; li.append(open); list.append(li); }
    notesLine.textContent = model.notes.join(' '); notesLine.hidden = !model.notes.length;
    paintTools(); onModel(model, {activity, failure, readAt, lastGoodAt});
    if (selected) paintCard();
  }
  // An axis label is shown only when the whole of it is inside the scroller's visible part; its tick always stays.
  function fitAxis() {
    const left = scroller.scrollLeft || 0, right = left + (scroller.clientWidth || Infinity);
    for (const label of scroller.querySelectorAll?.('[data-axis]') || []) {
      const at = Number(label.getAttribute('x')), wide = axisWidth(label), x0 = label.getAttribute('data-axis') === 'end' ? at - wide : at;
      label.setAttribute('visibility', axisLabelFits(x0, wide, left, right) ? 'visible' : 'hidden');
    }
  }
  function paintTools() { follow.hidden = following; follow.textContent = newCount ? newCount + ' new · Follow' : 'Follow now'; }
  function paintByline() {
    const name = 'observed flow (workflow owner, river read)', every = model?.live ? ' · every ' + Math.round(interval / 1000) + ' s' : '';
    if (failure) { byline.textContent = 'Read failed at ' + clock(failure.at) + ': ' + failure.message + (lastGoodAt ? ' · last good read ' + clock(lastGoodAt) : '') + every + ' · ' + name; byline.dataset.failed = 'true'; }
    else { byline.textContent = readAt ? 'Read ' + clock(readAt) + every + ' · ' + name : 'Reading the observed flow…'; delete byline.dataset.failed; }
  }
  function paintWaiting() {
    waitingSlot.replaceChildren(); const waiting = workflowRiverWaiting(run);
    if (!waiting.length) { waitingSlot.append(el('span', 'Waiting for you · 0', 'workflow-river-waiting-none')); return; }
    const pill = button('Waiting for you · ' + waiting.length, () => select('step:' + waiting[0].step_id), 'workflow:river-waiting'); pill.title = waiting.map(row => row.words + ' (' + row.field + ')').join('; '); waitingSlot.append(pill);
  }
  function select(id, {quiet = false} = {}) { selected = id; reading = reading?.mark === id ? reading : null; identityOpen = false; pause(); paint(); card.hidden = false; fitAxis(); card.querySelector('h4')?.focus?.({preventScroll: true});
    if (!quiet && id.startsWith('step:') && typeof onSelectStep === 'function') onSelectStep(id.slice(5)); }
  function stepFacts(stepId) {
    const rows = (value?.items || []).filter(row => row.step_id === stepId), row = rows.at(-1) || null, lane = model?.lanes.find(l => l.step_id === stepId);
    return {row, title: lane?.title || stepId};
  }
  function paintCard() {
    card.replaceChildren(); if (!selected || !model) { card.hidden = true; return; }
    let mark = [...model.marks, ...model.untimed].find(m => m.id === selected), row, sentence;
    if (selected.startsWith('step:')) {
      const stepId = selected.slice(5), facts = stepFacts(stepId); row = facts.row;
      const state = ownerStateWord('dispatch-child', row?.state), live = liveness(value, row), set = riverStepSettings(row, prepared(stepId)), turn = row?.turn;
      sentence = facts.title + ' · ' + (row ? state.words : 'no row in this read') + (set ? ' · ' + [set.provider, set.model].filter(Boolean).join(' · ') + ' (' + set.source + ')' : '') + (turn ? ' · started ' + clock(riverTime(turn.started_at)) + (turn.replied_at ? ' · replied ' + clock(riverTime(turn.replied_at)) : '') : '') + (live && riverRowRunning(value, row) ? (failure ? ' · last known running ' + clock(lastGoodAt) : ' · observed running at ' + clock(readAt)) : '');
      mark = {id: selected, kind: 'step', step_id: stepId, row};
    } else if (mark) { row = mark.row || mark.to?.row; sentence = riverMarkSentence(mark, model); }
    else { card.append(el('p', 'This mark is not in the latest read.', 'workflow-hint')); return; }
    const heading = el('h4', sentence); heading.tabIndex = -1; card.append(heading);
    const act = row?.turn_id ? activity.get(row.turn_id) : null; if (act && riverRowRunning(value, row) && !failure) card.append(el('p', 'Now: ' + act + ' (its event stream)', 'workflow-hint'));
    const refusal = row?.error || row?.known_refusal || row?.turn?.reply_error; if (refusal) card.append(el('p', 'The owner recorded: ' + (typeof refusal === 'string' ? refusal : JSON.stringify(refusal)), 'workflow-river-refusal'));
    let detail = null, painted = null;
    if (mark.kind === 'step' && typeof stepDetail === 'function') { detail = el('div', '', 'workflow-river-step-detail'); painted = stepDetail(mark.step_id, detail) || null; }
    const actions = el('div', '', 'workflow-actions');
    if (row && mark.kind !== 'handover') {
      for (const [key, label] of [['reply', 'Open reply'], ['proposal', 'Open proposal'], ['typed_return', 'Open typed return']]) {
        const read = row.reads?.[key]; if (!read?.http?.url || (read.http.method || 'GET') !== 'GET') continue;
        actions.append(button(label, () => follow_(key, label, read, mark.id), 'workflow:river-read', (row.turn_id || row.step_id) + ':' + key));
      }
      const conversation = row.reads?.conversation;
      if (conversation?.project_url && typeof openConversation === 'function' && !painted?.conversation) actions.append(button('Open conversation', () => { Promise.resolve(openConversation(conversation)).catch(error => { reading = {mark: mark.id, label: 'Open conversation', error: error.message}; paintCard(); }); }, 'workflow:river-conversation', row.session_id || row.step_id));
    }
    const identity = button(identityOpen ? 'Hide identity' : 'Identity', () => { identityOpen = !identityOpen; paintCard(); }, 'workflow:river-identity', mark.id); identity.setAttribute('aria-expanded', String(identityOpen)); actions.append(identity);
    actions.append(button('Close', () => { selected = null; reading = null; card.hidden = true; paint(); fitAxis(); }, 'workflow:river-card-close', mark.id));
    card.append(actions);
    if (detail) card.append(detail);
    if (identityOpen) {
      const facts = el('dl', '', 'workflow-river-identity'), add = (k, v) => { facts.append(el('dt', k), el('dd', v == null || v === '' ? 'not recorded' : String(v))); };
      add('Step', mark.step_id); add('Session', row?.session_id); add('Turn', row?.turn_id); add('Event', row?.event_id); add('Packet', row?.packet); add('Recorded state', row?.state);
      add('Current liveness', liveness(value, row)?.observed); if (mark.call) { add('Tool call', mark.call.id); add('Operation', mark.call.operation); add('Call status', mark.call.status); add('Recorded as', mark.call.kind); }
      if (mark.kind === 'handover') { add('Source', 'prepared_dependencies'); add('From turn', mark.from.row?.turn_id); add('To turn', mark.to.row?.turn_id); }
      card.append(facts);
    }
    if (reading?.mark === mark.id) {
      const box = el('div', '', 'workflow-river-reading'); box.append(el('h5', reading.label));
      if (reading.pending) box.append(el('p', 'Reading what the owner saved…', 'workflow-hint'));
      else if (reading.error) box.append(el('p', 'The owner refused or the read failed: ' + reading.error, 'workflow-river-refusal'));
      else { box.append(el('p', reading.text, 'workflow-river-text')); if (reading.next) box.append(button('Read more of it', () => follow_(reading.key, reading.label, reading.next, mark.id, true), 'workflow:river-reply-more', mark.id)); }
      card.append(box);
    }
  }
  async function follow_(key, label, read, markId, more = false) {
    const ticket = ++readEpoch; const before = more ? reading?.text || '' : '';
    reading = {mark: markId, key, label, pending: true, text: before}; paintCard();
    try {
      const got = await request(read.http.url); if (!current() || ticket !== readEpoch || selected !== markId) return;
      const text = typeof got?.content === 'string' ? got.content : typeof got?.text === 'string' ? got.text : got?.state === 'ABSENT' ? 'The owner holds no saved text for it (' + (got.reason || 'absent') + ').' : JSON.stringify(got, null, 2).slice(0, 4000);
      reading = {mark: markId, key, label, text: before + text, next: got?.next_read?.http?.url ? got.next_read : null};
    } catch (error) { if (ticket !== readEpoch) return; reading = {mark: markId, key, label, error: error?.message || 'The read failed.'}; }
    paintCard();
  }
  let readEpoch = 0;
  // The first read starts once the caller has placed the river on the page (a detached river is not current).
  Promise.resolve().then(() => load());
  return {node: root, byline, waiting: waitingSlot, load, select, resume,
    update({run: nextRun = run, stepDetail: nextDetail = stepDetail, onSelectStep: nextSelect = onSelectStep} = {}) { run = nextRun; stepDetail = nextDetail; onSelectStep = nextSelect; paintWaiting(); if (selected && !card.hidden) paintCard(); },
    get selected() { return selected; },
    get model() { return model; }, get value() { return value; }, get live() { return {activity, failure, readAt, lastGoodAt}; }, get following() { return following; }, get newCount() { return newCount; }, get failure() { return failure; },
    destroy() { alive = false; epoch++; clearTimeout(timer); document.removeEventListener?.('visibilitychange', onVisibility); resized?.disconnect(); for (const source of streams.values()) source?.close?.(); streams.clear(); }};
}
