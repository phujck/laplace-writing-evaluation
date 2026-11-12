// SESSIONS PAGE (wave 9). Purpose: one page lists every in-app writing session across all projects with the state its
// owners state, re-reads itself while visible, and opens, stops and writes to a session beside the list without first
// going into its project. Mounted by workspace-analytics.mjs mountSessionAnalytics when it is given no project and no
// selected scope (app=activity); a project's Activity > Graphs mount never reaches this module.
// Reads: GET /authoring/state?view=all-sessions (authoring_http.read_session_index: the journal fold plus
// turn_jobs.active_work_projection), GET /authoring/session?view=summary (one session's last turns and its active turn
// with capabilities), the turn's /authoring/events stream (events_url from that read, through turn-events.mjs), /projects/library (display names).
// Writes (existing doors only): POST /authoring/interrupt for the exact active turn, POST /authoring/steer to a running
// turn whose owner says it can be steered, POST /authoring/turn for the next turn of an idle session.
// The records the page showed before (Overview, Graphs & analysis, Selected activity, Usage, Feedback, Delivery,
// Coverage) are mounted unchanged by mountRecords under the one control 'Usage and records'.
// Wave 13: a session whose saved turns name a Work gets one 'Development' section in its pane (workspace-development.mjs).
import {openTurnEvents, progressWords} from './turn-events.mjs';
import {mountDevelopment, sessionWorkId} from './workspace-development.mjs';
import {ownerStateWord} from './workspace-presentation.mjs';
export const SESSIONS_READ_INTERVAL_MS = 5000;
// the filter words are the session state words of the one table (workspace-presentation.mjs OWNER_STATE_WORDS.session)
const FILTERS = [['', 'All', 'all'], ...['running', 'waiting', 'failed'].map(key => [key, ownerStateWord('session', key).words, key])];

// SEND WITH NOTHING TYPED (wave 11, census R2a/R2b): one behaviour for the conversation panel's Send and this page's
// pane Send. Send stays enabled; pressed with an empty box it says beside Send why nothing was sent and puts the cursor
// in the box. Nothing is sent and the box is not touched, so a draft is never lost. The line goes when he types.
export const EMPTY_SEND_TEXT = 'Write a message first.';
export function refuseEmptySend(box, send) {
  // the line sits directly under the row that holds Send, outside that row's own layout
  const row = send.parentElement, host = row?.parentElement || row;
  let line = host?.querySelector?.('.send-empty-note');
  if (!line) { line = document.createElement('p'); line.className = 'send-empty-note'; line.setAttribute('data-empty-send', ''); line.setAttribute('role', 'status'); if (row?.after && host !== row) row.after(line); else host.append(line); }
  line.textContent = EMPTY_SEND_TEXT; line.hidden = false; box.focus?.();
  const clear = () => { if (String(box.value || '').trim()) { line.hidden = true; line.textContent = ''; box.removeEventListener?.('input', clear); } };
  box.addEventListener?.('input', clear);
  return line;
}
function el(tag, text = '', cls = '') { const node = document.createElement(tag); if (text) node.textContent = text; if (cls) node.className = cls; return node; }
function button(text, cls = '') { const b = el('button', text, cls); b.type = 'button'; return b; }
export function clockText(iso, now = new Date()) {
  const d = new Date(iso); if (!iso || Number.isNaN(d.getTime())) return '';
  const hm = d.toLocaleTimeString('en-GB', {hour: '2-digit', minute: '2-digit', hour12: false});
  return d.toDateString() === now.toDateString() ? hm : d.toLocaleDateString('en-GB', {day: 'numeric', month: 'short'}) + ' ' + hm;
}
export function secondsText(iso) { const d = new Date(iso); return !iso || Number.isNaN(d.getTime()) ? '' : d.toLocaleTimeString('en-GB', {hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false}); }
export function durationText(iso, now = Date.now()) {
  const start = Date.parse(iso); if (!Number.isFinite(start)) return '';
  const minutes = Math.max(0, Math.floor((now - start) / 60000));
  if (minutes < 1) return 'under 1 min'; if (minutes < 60) return minutes + ' min';
  return Math.floor(minutes / 60) + ' h ' + (minutes % 60) + ' min';
}
// The state in the owner's words with its time. The state word and its shape are the table's (ownerStateWord 'session');
// the sentence around it names the fields of the index read (read_session_index) that give the time and the reason.
export function stateText(row, now = new Date()) {
  const last = row.last_turn || {}, at = t => clockText(t, now), word = ownerStateWord('session', row.state).words;
  switch (row.state) {
    case 'running': return row.active?.since ? word + ' since ' + at(row.active.since) + ' · ' + durationText(row.active.since, now.getTime()) : word + ' (start time not recorded)';
    case 'starting': return word + ' a turn';
    case 'waiting': return word + ': proposed changes have no decision' + (last.ended_at ? ' · ' + at(last.ended_at) : '');
    case 'completed': return last.ended_at ? word + ' ' + at(last.ended_at) : word + ' · turn started ' + at(last.at);
    case 'failed': return word + ' ' + at(last.ended_at || last.at) + (last.error ? ': ' + last.error : ' (no reason recorded)');
    case 'interrupted': return word + ' ' + at(last.ended_at || last.at);
    case 'no-reply': return word + ' · started ' + at(last.at);
    case 'no-turn': return word + ' · opened ' + at(row.created_at);
    default: return word + (last.at ? ' · ' + at(last.at) : '');
  }
}
export function roleText(row, titles = new Map()) {
  if (row.parent) return 'dispatched by ' + (row.parent.title || titles.get(row.parent.session_id) || row.parent.session_id || 'another session');
  return row.role === 'review' ? 'reviewer' : row.role || 'role not recorded';
}
// Who started whom: a session whose parent (the parent_turn_id of one of its turns, resolved to that turn's session by
// the index read) is in the same list is drawn under it. A group sits where its first member falls in the owner's order.
export function sessionTree(rows) {
  const ids = new Set(rows.map(row => row.session_id)), children = new Map(), roots = [];
  for (const row of rows) {
    const parent = row.parent?.session_id;
    if (parent && ids.has(parent) && parent !== row.session_id) { if (!children.has(parent)) children.set(parent, []); children.get(parent).push(row); }
    else roots.push(row);
  }
  const rootOf = new Map(), position = new Map(rows.map((row, i) => [row.session_id, i]));
  const top = row => { let at = row, seen = new Set(); while (at.parent?.session_id && ids.has(at.parent.session_id) && !seen.has(at.session_id)) { seen.add(at.session_id); at = rows[position.get(at.parent.session_id)]; } return at.session_id; };
  for (const row of rows) { const r = top(row); if (!rootOf.has(r) || position.get(row.session_id) < rootOf.get(r)) rootOf.set(r, position.get(row.session_id)); }
  const out = [], walk = (row, depth, seen) => { if (seen.has(row.session_id)) return; seen.add(row.session_id); out.push({row, depth}); for (const child of children.get(row.session_id) || []) walk(child, depth + 1, seen); };
  const seen = new Set();
  for (const row of [...roots].sort((a, b) => (rootOf.get(a.session_id) ?? 0) - (rootOf.get(b.session_id) ?? 0))) walk(row, 0, seen);
  for (const row of rows) if (!seen.has(row.session_id)) walk(row, 0, seen);
  return out;
}
export function sessionIndexQuery({project = '', state = '', limit = 50} = {}) {
  const q = new URLSearchParams({view: 'all-sessions', limit: String(limit)});
  if (project) q.set('project', project); if (state) q.set('state', state);
  return '/authoring/state?' + q;
}
const projectHref = (project, session) => '/project?' + new URLSearchParams({workspace: 'writing', corpus: project, view: 'overview', ...(session ? {session} : {})});

export async function mountSessionsPage(host, {request, mountRecords, onConversation, parameters = null, interval = SESSIONS_READ_INTERVAL_MS} = {}) {
  const params = parameters || new URLSearchParams(globalThis.location?.search || '');
  let alive = true, filter = '', project = params.get('from') || '', data = null, selected = params.get('session') || '', timer = null, epoch = 0, records = null;
  const titles = new Map(), names = new Map(), rowsById = new Map(), drafts = new Map();
  host.classList.add('sessions-page');
  const head = el('header', '', 'sessions-head'), h1 = el('h1', 'Sessions'), readLine = el('p', '', 'sessions-read'), refresh = button('Refresh', 'sessions-refresh');
  readLine.setAttribute('aria-live', 'polite'); const headText = el('div', '', 'sessions-head-text'); headText.append(h1, readLine);
  const views = el('nav', '', 'sessions-views'); views.setAttribute('aria-label', 'Sessions page views');
  const liveTab = button('Sessions', 'sessions-view'), recordsTab = button('Usage and records', 'sessions-view');
  recordsTab.dataset.sessionsRecords = ''; views.append(liveTab, recordsTab, refresh); head.append(headText, views);
  const live = el('section', '', 'sessions-live'), recordsHost = el('section', '', 'sessions-records'); recordsHost.hidden = true;
  const filters = el('div', '', 'sessions-filters'); filters.setAttribute('role', 'group'); filters.setAttribute('aria-label', 'Filter sessions');
  const filterButtons = new Map();
  for (const [key, label] of FILTERS) { const b = button(label, 'sessions-filter'); b.dataset.sessionsFilter = key || 'all'; b.onclick = () => { filter = key; read(); }; filterButtons.set(key, b); filters.append(b); }
  const projectLabel = el('label', '', 'sessions-project'), projectText = el('span', 'Project'), projectSelect = el('select');
  projectSelect.setAttribute('aria-label', 'Project'); projectLabel.append(projectText, projectSelect); filters.append(projectLabel);
  projectSelect.onchange = () => { project = projectSelect.value; read(); };
  const status = el('p', '', 'sessions-status'); status.setAttribute('role', 'status');
  const layout = el('div', '', 'sessions-layout'), list = el('ol', '', 'sessions-list'); list.setAttribute('aria-label', 'Sessions');
  const pane = el('aside', '', 'sessions-pane'); pane.hidden = true; pane.setAttribute('aria-label', 'Open session');
  layout.append(list, pane); live.append(filters, status, layout);
  host.append(head, live, recordsHost);
  const showView = which => {
    const recordsOn = which === 'records'; live.hidden = recordsOn; recordsHost.hidden = !recordsOn;
    liveTab.setAttribute('aria-current', recordsOn ? 'false' : 'page'); recordsTab.setAttribute('aria-current', recordsOn ? 'page' : 'false');
    recordsTab.setAttribute('aria-expanded', String(recordsOn)); h1.textContent = recordsOn ? 'Sessions: usage and records' : 'Sessions';
    readLine.hidden = recordsOn; refresh.hidden = recordsOn;
    if (recordsOn) stopTimer(); else { read(); }
  };
  liveTab.onclick = () => showView('live'); recordsTab.onclick = () => showView('records');
  liveTab.setAttribute('aria-current', 'page'); recordsTab.setAttribute('aria-current', 'false'); recordsTab.setAttribute('aria-expanded', 'false');
  refresh.onclick = () => read();

  const visible = () => alive && host.isConnected !== false && !live.hidden && globalThis.document?.visibilityState !== 'hidden';
  function stopTimer() { if (timer) clearTimeout(timer); timer = null; }
  function schedule() { stopTimer(); if (!visible() || typeof setTimeout !== 'function') return; timer = setTimeout(() => { timer = null; if (visible()) read({quiet: true}); }, interval); timer?.unref?.(); }
  const onVisibility = () => { if (globalThis.document?.visibilityState === 'hidden') stopTimer(); else if (alive && !live.hidden) read({quiet: true}); };
  globalThis.document?.addEventListener?.('visibilitychange', onVisibility);

  function paintProjects() {
    const facet = data?.projects || [], wanted = project;
    const options = [['', 'All projects']].concat(facet.map(row => [row.project, (names.get(row.project) || row.project) + ' (' + row.sessions + ')']));
    if (wanted && !facet.some(row => row.project === wanted)) options.push([wanted, names.get(wanted) || wanted]);
    const key = JSON.stringify(options);
    if (projectSelect.dataset.options !== key) { projectSelect.replaceChildren(...options.map(([value, label]) => { const o = el('option', label); o.value = value; return o; })); projectSelect.dataset.options = key; }
    projectSelect.value = wanted;
  }
  function paintFilters() {
    const counts = data?.counts || {};
    for (const [key, label, count] of FILTERS) { const b = filterButtons.get(key); const n = counts[count];
      b.textContent = label + (Number.isFinite(n) ? ' ' + n : ''); b.setAttribute('aria-pressed', String(filter === key)); }
  }
  function paintRow(li, row, depth) {
    const text = stateText(row), meta = [names.get(row.project) || row.project, roleText(row, titles), [row.provider, row.model].filter(Boolean).join(' · ') || 'provider not recorded',
      row.turn_count + (row.turn_count === 1 ? ' turn' : ' turns'), ...(row.tool_failures ? [row.tool_failures + (row.tool_failures === 1 ? ' tool failure' : ' tool failures')] : [])].join(' · ');
    const key = JSON.stringify([text, meta, row.title, row.state, depth, selected === row.session_id]);
    if (li.dataset.painted === key) return; li.dataset.painted = key;
    li.dataset.state = row.state; li.dataset.depth = String(depth); li.className = 'sessions-row' + (depth ? ' sessions-child' : '');
    if (depth) li.style.setProperty?.('--sessions-depth', String(depth));
    const open = li.firstElementChild || button('', 'sessions-open');
    open.replaceChildren(); open.setAttribute('aria-current', String(selected === row.session_id));
    const owned = ownerStateWord('session', row.state), state = el('span', '', 'sessions-state'), mark = el('span', owned.shape, 'sessions-mark'); mark.setAttribute('aria-hidden', 'true');
    state.append(mark, el('span', text, 'sessions-state-word')); state.title = 'Owner state: ' + String(row.state);
    open.append(el('span', row.title || 'Untitled session', 'sessions-title'), state, el('span', meta, 'sessions-meta'));
    open.onclick = () => openSession(row.session_id);
    if (!li.firstElementChild) li.append(open);
  }
  function paintList() {
    const rows = data?.sessions || [];
    for (const row of rows) titles.set(row.session_id, row.title);
    const tree = sessionTree(rows), keep = new Set(tree.map(item => item.row.session_id));
    for (const [id, li] of rowsById) if (!keep.has(id)) { li.remove(); rowsById.delete(id); }
    const order = tree.map(({row, depth}) => { let li = rowsById.get(row.session_id); if (!li) { li = el('li'); li.dataset.session = row.session_id; rowsById.set(row.session_id, li); } paintRow(li, row, depth); return li; });
    list.querySelector?.('.sessions-empty')?.remove?.();
    const current = [...list.children].filter(node => node.dataset?.session);
    if (current.length !== order.length || current.some((node, i) => node !== order[i])) for (const li of order) list.append(li);
    if (!rows.length) { const empty = el('li', filter === 'waiting' ? 'No session is waiting for you: no saved reply has proposed changes without a recorded decision.' : filter || project ? 'No session matches this filter.' : 'No in-app sessions yet. A session starts when you send a message from a project or a workflow starts one.', 'sessions-empty'); list.append(empty); }
    if (data?.next_offset != null) status.textContent = 'Showing the first ' + rows.length + ' of ' + data.total + ' sessions in this filter.';
  }
  async function read({quiet = false} = {}) {
    const ticket = ++epoch; stopTimer();
    if (!quiet) status.textContent = 'Reading sessions…';
    try {
      const value = await request(sessionIndexQuery({project, state: filter}));
      if (!alive || ticket !== epoch) return;
      if (value?.schema_version !== 'laplace.session-index/1' || !Array.isArray(value.sessions)) throw Error('The session list read returned something else; nothing is shown as running.');
      data = value; status.textContent = ''; status.className = 'sessions-status';
      paintProjects(); paintFilters(); paintList();
      readLine.textContent = 'Read at ' + (secondsText(value.observed_at) || 'an unrecorded time') + ' · re-read every ' + Math.round(interval / 1000) + ' s while this page is visible';
      const chosen = selected && value.sessions.find(row => row.session_id === selected);
      if (selected && !pane.hidden && chosen && paneRow && (chosen.state !== paneRow.state || chosen.last_turn?.turn_id !== paneRow.last_turn?.turn_id)) { paneRow = chosen; readPane({keepStatus: true}); }
      else if (chosen) paneRow = chosen;
    } catch (error) {
      if (!alive || ticket !== epoch) return;
      status.textContent = error.message || 'The session list could not be read.'; status.className = 'sessions-status error';
    } finally { if (alive && ticket === epoch) schedule(); }
  }

  // THE OPEN SESSION beside the list.
  let paneRow = null, paneData = null, stream = null, liveText = '', paneEpoch = 0;
  const paneHead = el('header', '', 'sessions-pane-head'), paneTitle = el('h2', '', 'sessions-pane-title'), close = button('Close', 'sessions-close');
  paneHead.append(paneTitle, close);
  const facts = el('p', '', 'sessions-pane-facts'), projectLink = el('a', '', 'sessions-project-link'), paneState = el('span', '', 'sessions-pane-state');
  facts.append(projectLink, paneState);
  const paneStatus = el('p', '', 'sessions-pane-status'); paneStatus.setAttribute('role', 'status');
  const thread = el('ol', '', 'sessions-thread'); thread.setAttribute('aria-label', 'Last turns');
  const actions = el('div', '', 'sessions-pane-actions'), stop = button('Stop', 'sessions-stop'), inProject = el('a', 'Open in its project', 'sessions-in-project');
  stop.hidden = true; actions.append(stop, inProject);
  const compose = el('form', '', 'sessions-compose'), boxLabel = el('label', 'Message', 'sessions-message-label'), box = el('textarea'), recipient = el('p', '', 'sessions-recipient'), send = el('button', 'Send', 'sessions-send');
  send.type = 'submit'; send.dataset.control = 'sessions:send'; box.rows = 3; box.setAttribute('aria-label', 'Message to this session'); boxLabel.append(box);
  const sendRow = el('div', '', 'sessions-send-row'); sendRow.append(recipient, send); compose.append(boxLabel, sendRow);
  pane.append(paneHead, facts, paneStatus, thread, actions, compose);
  close.onclick = () => closePane();
  inProject.onclick = event => { if (onConversation && paneRow) { event.preventDefault?.(); onConversation({project: paneRow.project, id: paneRow.session_id}); } };

  function closeStream() { if (stream) { stream.close(); stream = null; } }
  // THE DEVELOPMENT SECTION (wave 13): mounted for the Work the session's newest Work-bound turn names, re-read with the pane.
  let development = null;
  function paintDevelopment(row, value) {
    const workId = sessionWorkId(value);
    if (development && (development.sessionId !== row.session_id || development.workId !== workId)) { development.destroy(); development = null; }
    if (!workId) return;
    if (development) development.refresh();
    else development = mountDevelopment(pane, {request, project: row.project, sessionId: row.session_id, workId, clock: clockText, seconds: secondsText});
  }
  function closePane() {
    development?.destroy(); development = null;
    closeStream(); ++paneEpoch; if (selected) drafts.set(selected, box.value); pane.hidden = true; layout.classList.remove('sessions-open-pane'); const was = selected; selected = ''; paneRow = null; paneData = null;
    setURL(''); if (data) paintList(); rowsById.get(was)?.firstElementChild?.focus?.();
  }
  function setURL(session) {
    try { const url = new URL(globalThis.location.href); if (session) url.searchParams.set('session', session); else url.searchParams.delete('session'); globalThis.history?.replaceState?.(globalThis.history.state, '', url); } catch { /* no address bar in this host */ }
  }
  function openSession(id) {
    const row = data?.sessions?.find(item => item.session_id === id); if (!row) return;
    if (selected !== id) { if (selected) drafts.set(selected, box.value); box.value = drafts.get(id) || ''; liveText = ''; closeStream(); }
    selected = id; paneRow = row; pane.hidden = false; layout.classList.add('sessions-open-pane'); setURL(id); paintList(); readPane();
    revealPane = true;
  }
  function turnItem(who, when, text, cls) {
    const li = el('li', '', 'sessions-turn ' + cls), label = el('strong', who + (when ? ' · ' + when : '')), body = el('p', text || '', 'sessions-turn-text');
    li.append(label, body); return {li, body};
  }
  let liveBody = null, revealPane = false;
  // the open session fits the window beside the list: its thread scrolls and the message box stays on screen
  function fitPane() {
    if (pane.hidden || typeof globalThis.innerHeight !== 'number' || !pane.getBoundingClientRect) return;
    if (globalThis.matchMedia?.('(max-width: 900px)')?.matches) { pane.style.maxHeight = ''; return; }
    const top = Math.max(16, pane.getBoundingClientRect().top); pane.style.maxHeight = Math.max(420, Math.floor(globalThis.innerHeight - top - 16)) + 'px';
  }
  const onResize = () => fitPane(); globalThis.addEventListener?.('resize', onResize); globalThis.addEventListener?.('scroll', onResize, {passive: true});
  function paintPane() {
    const row = paneRow, value = paneData; if (!row) return;
    paneTitle.textContent = row.title || 'Untitled session';
    projectLink.textContent = names.get(row.project) || row.project; projectLink.href = projectHref(row.project);
    inProject.href = projectHref(row.project, row.session_id);
    const active = value?.active || null;
    paneState.textContent = ' · ' + (active ? ownerStateWord('session', 'running').words + ' since ' + clockText(row.active?.since || value?.turns?.at(-1)?.ts) + ' · the owner reports this turn active' : stateText(row));
    paneState.title = 'Owner state: ' + String(row.state);
    thread.replaceChildren(); liveBody = null;
    const provider = value?.session?.provider || row.provider, model = value?.session?.model || row.model;
    for (const turn of value?.turns || []) {
      thread.append(turnItem('You', clockText(turn.ts), turn.text, 'sessions-asked').li);
      const answerer = [turn.provider_settings?.provider || provider, value?.session?.actual_model || turn.provider_settings?.model].filter(Boolean).join(' · ');
      if (turn.reply) {
        const reply = turn.reply, said = turnItem(answerer || 'Reply', ownerStateWord('reply', reply.status).words, reply.display_text || '', 'sessions-replied' + (reply.status === 'failed' ? ' sessions-turn-failed' : ''));
        if (reply.status === 'failed' && reply.error && reply.error !== reply.display_text) said.li.append(el('p', 'Recorded reason: ' + reply.error, 'sessions-turn-reason'));
        if (reply.display_text_truncated) said.li.append(el('p', 'Shortened by the owner; the whole reply is in its project.', 'sessions-turn-note'));
        thread.append(said.li);
      } else if (active && active.id === turn.id) {
        const now = turnItem(answerer || 'Reply', 'arriving now', liveText || active.text || '', 'sessions-replied sessions-live-reply'); liveBody = now.body; thread.append(now.li);
      } else thread.append(turnItem(answerer || 'Reply', 'no reply saved', '', 'sessions-replied').li);
    }
    if (!(value?.turns || []).length) thread.append(el('li', 'No turns are saved in this session yet.', 'sessions-turn'));
    const canStop = !!(active && active.capabilities?.can_interrupt);
    stop.hidden = !canStop; stop.disabled = false; stop.textContent = 'Stop';
    const steer = !!(active && active.capabilities?.can_steer);
    send.disabled = !!active && !steer; box.disabled = false;
    send.textContent = active ? (steer ? 'Send to the running turn' : 'Send') : 'Send';
    recipient.textContent = active && !steer ? 'Its owner reports this turn cannot be steered. Send starts the next turn once it ends.'
      : 'Goes to ' + [provider, model].filter(Boolean).join(' · ') + (active ? ', into the running turn' : ' as the next turn') + (value?.session?.actual_model ? ' · last answered by ' + value.session.actual_model : '');
    if (thread.scrollHeight) thread.scrollTop = thread.scrollHeight;
    fitPane();
    if (revealPane) { revealPane = false; if (globalThis.matchMedia?.('(max-width: 900px)')?.matches) pane.scrollIntoView?.({block: 'start'}); }
  }
  async function readPane({keepStatus = false} = {}) {
    const row = paneRow; if (!row) return; const ticket = ++paneEpoch;
    if (!keepStatus) { paneStatus.textContent = 'Reading the session…'; paneStatus.dataset.transient = '1'; }
    try {
      const value = await request('/authoring/session?' + new URLSearchParams({project: row.project, id: row.session_id, view: 'summary', limit: '6'}));
      if (!alive || ticket !== paneEpoch || selected !== row.session_id) return;
      if (value?.session?.id && value.session.id !== row.session_id) throw Error('The session read named a different session.');
      paneData = value; if (!keepStatus || paneStatus.dataset.transient) { paneStatus.textContent = ''; paneStatus.className = 'sessions-pane-status'; } delete paneStatus.dataset.transient; paintPane(); paintDevelopment(row, value);
      if (value.active) connect(row, value.active); else closeStream();
    } catch (error) { if (alive && ticket === paneEpoch) { paneStatus.textContent = error.message || 'The session could not be read.'; paneStatus.className = 'sessions-pane-status error'; } }
  }
  function connect(row, active) {
    if (stream && stream.turnId === active.id) return; closeStream();
    liveText = typeof active.text === 'string' ? active.text : ''; if (liveBody) liveBody.textContent = liveText;
    if (typeof EventSource !== 'function' || !active.capabilities?.events_url) return;
    let source; try { source = openTurnEvents(active.capabilities.events_url, active.id, {after: active.cursor, onEvent, onError}); } catch (error) { paneStatus.textContent = error.message; return; }
    stream = source;
    const mine = () => alive && stream === source && selected === row.session_id;
    function onEvent(item) {
      if (!mine()) return;
      if (item.type === 'delta' && typeof item.text === 'string') { liveText += item.text; if (liveBody) { liveBody.textContent = liveText; thread.scrollTop = thread.scrollHeight; } }
      else if (item.type === 'progress' && item.text) paneStatus.textContent = 'Provider: ' + progressWords(item.text);
      else if (item.type === 'complete' || item.type === 'error') { closeStream(); paneStatus.textContent = item.type === 'error' ? (item.message || 'The turn ended with an error.') : 'The turn ended. Reading what its owner saved…'; read({quiet: true}); readPane({keepStatus: item.type === 'error'}); }
    }
    function onError() { if (!mine()) return; closeStream(); read({quiet: true}); readPane(); }
  }
  // STOP: strict. The session is re-read and Stop is sent only for the turn that read reports active.
  stop.onclick = async () => {
    const row = paneRow, shown = paneData?.active?.id; if (!row || !shown) return; stop.disabled = true;
    try {
      const fresh = await request('/authoring/session?' + new URLSearchParams({project: row.project, id: row.session_id, view: 'summary', limit: '1'}));
      if (fresh?.active?.id !== shown) { paneStatus.textContent = 'The running turn changed or ended before Stop was sent; nothing was stopped.'; await readPane({keepStatus: true}); return; }
      await request('/authoring/interrupt', {project: row.project, turn_id: shown});
      paneStatus.textContent = 'Stop requested for turn ' + shown + '. Waiting for its owner to record how it ended.'; stop.textContent = 'Stop requested';
      await read({quiet: true});
    } catch (error) { paneStatus.textContent = error.message || 'Stop was not accepted.'; paneStatus.className = 'sessions-pane-status error'; stop.disabled = false; }
  };
  compose.onsubmit = async event => {
    event?.preventDefault?.(); const row = paneRow, text = box.value.trim(); if (row && !text && !send.disabled) { refuseEmptySend(box, send); return; } if (!row || !text || send.disabled) return;
    send.disabled = true; paneStatus.className = 'sessions-pane-status';
    try {
      const fresh = await request('/authoring/session?' + new URLSearchParams({project: row.project, id: row.session_id, view: 'summary', limit: '1'}));
      const active = fresh?.active, session = fresh?.session || {};
      if (active) {
        if (!active.capabilities?.can_steer) { paneStatus.textContent = 'A turn is running and its owner reports it cannot be steered; your message is kept here.'; await readPane({keepStatus: true}); return; }
        await request('/authoring/steer', {project: row.project, turn_id: active.id, text, selection: null, workspace_context: {}, delivery_mode: (active.capabilities.input_delivery_modes || [])[0]});
        paneStatus.textContent = 'Sent to the running turn ' + active.id + '.';
      } else {
        const result = await request('/authoring/turn', {project: row.project, session_id: row.session_id, provider: session.provider || row.provider, model: session.model || row.model,
          effort: session.effort ?? row.effort ?? null, text, mode: row.last_turn?.mode || 'discuss', request_id: globalThis.crypto?.randomUUID?.() || String(Date.now())});
        paneStatus.textContent = 'Sent. Turn ' + (result?.turn_id || '') + ' started.';
      }
      box.value = ''; await read({quiet: true}); await readPane({keepStatus: true});
    } catch (error) { paneStatus.textContent = (error.message || 'The message was not accepted.') + ' Your message is kept here.'; paneStatus.className = 'sessions-pane-status error'; }
    finally { if (alive) send.disabled = !!paneData?.active && !paneData.active.capabilities?.can_steer; }
  };

  try { const library = await request('/projects/library'); for (const row of library?.projects || []) names.set(row.name, row.title || row.display_name || row.name); } catch { /* the names stay the project identities */ }
  await read();
  if (selected) { if (data?.sessions?.some(row => row.session_id === selected)) openSession(selected); else selected = ''; }
  if (mountRecords) { try { records = await mountRecords(recordsHost); } catch (error) { recordsHost.append(el('p', error.message || 'The records could not be read.', 'sessions-status error')); } }
  return {
    refresh: () => read(), showRecords: () => showView('records'), showSessions: () => showView('live'), get records() { return records; }, get data() { return data; },
    destroy() { alive = false; stopTimer(); closeStream(); development?.destroy(); globalThis.removeEventListener?.('resize', onResize); globalThis.removeEventListener?.('scroll', onResize); globalThis.document?.removeEventListener?.('visibilitychange', onVisibility); records?.destroy?.(); },
  };
}
