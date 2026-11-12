// DEVELOPMENT (wave 13, lane-checks). Purpose: in the Sessions page's open pane, a session whose saved turns name a Work
// shows that Work's development lane and its checks as the development owner states them, and offers only that owner's
// actions: cut a lane, discard it, run one of its fixed check profiles. Mounted by workspace-sessions.mjs paintPane.
// Reads: the work_id the owner saved on the session's turns (GET /authoring/session?view=summary, read by the pane) and
// POST /work/development {action:'status', work_id, session_id} with no limit, so the owner's own page size applies (development_source.status: development (its grants,
// candidates, effects and checks pages, newest first, continued only through next_read), status_notes, page_meaning, work,
// lane (with its grant: id, state, paths, operations, parent_session_id, expires_at, revoked_at), session_id and offers).
// Writes: exactly the request an offer carries (offers[].request), sent unchanged to POST /work/development; a check offer
// that declares targets also carries the file names typed beside it, which the owner checks against its own globs.
// Nothing here maps an owner constant: state words come from the one table (workspace-presentation.mjs ownerStateWord).
// PREVIEW and ADOPT (wave 13, adopt): beside the lane and its checks, card 3 Preview reads POST /work/development
// {action:'preview', work_id, session_id} on his press (development_adoption.preview: files, checks with newly failing
// names, reviews that will no longer be current, the close carry, the scratch copy, and the adopt offer or its refusals);
// card 4 Adopt sends exactly the request that offer carries, and after Adopt reads {action:'adoption', work_id}
// (development_adoption.adoption: the commit, its trailer, and the review owner's standing of the reviews it moved).
import {ownerStateWord, inputChip} from './workspace-presentation.mjs';

// The page size is the owner's: the status request carries no limit, and the checks page of the reply states the size it
// applied as requested_limit (development_source._fitted: 'requested_limit': requested). A failed check's names are
// shown up to that same count and the rest stay one labelled press away; with no stated size every listed name is shown.
export function failingShown(page) { return Number.isInteger(page?.requested_limit) && page.requested_limit > 0 ? page.requested_limit : Infinity; }
export const DEVELOPMENT_DOOR = '/work/development';
const TARGET_DRAFT_KEY = 'laplace:development-targets:';

function el(tag, text = '', cls = '') { const node = document.createElement(tag); if (text) node.textContent = text; if (cls) node.className = cls; return node; }
function control(text, id, owner = '') { const b = el('button', text, 'development-action'); b.type = 'button'; b.dataset.control = id; if (owner) b.dataset.controlOwner = owner; return b; }

// The Work a session is on: the newest of its saved turns that names one (the turn owner's work_id; never inferred).
export function sessionWorkId(summary) {
  const turns = Array.isArray(summary?.turns) ? summary.turns : [];
  for (let i = turns.length - 1; i >= 0; i--) if (typeof turns[i]?.work_id === 'string' && turns[i].work_id) return turns[i].work_id;
  return '';
}
export function statusRequest(project, workId, sessionId) { return {project, action: 'status', work_id: workId, session_id: sessionId}; }
export function previewRequest(project, workId, sessionId) { return {project, action: 'preview', work_id: workId, session_id: sessionId}; }
export function adoptionRequest(project, workId) { return {project, action: 'adoption', work_id: workId}; }
const short = sha => String(sha || '').slice(0, 7);
export function targetsFromText(text) { return String(text || '').split(/[\s,]+/).filter(Boolean); }
export function bytesText(n) { return Number.isFinite(n) ? 'about ' + Math.max(1, Math.round(n / (1024 * 1024))) + ' MB' : ''; }
function stateLine(field, value, cls) {
  const owned = ownerStateWord(field, value), line = el('span', '', cls), mark = el('span', owned.shape, 'development-mark');
  mark.setAttribute('aria-hidden', 'true'); line.append(mark, el('span', owned.words, 'development-state-word')); line.title = 'Owner state: ' + String(value);
  return line;
}
function draft(storage, key, value) {
  try { if (value === undefined) return storage?.getItem?.(TARGET_DRAFT_KEY + key) || ''; if (value) storage?.setItem?.(TARGET_DRAFT_KEY + key, value); else storage?.removeItem?.(TARGET_DRAFT_KEY + key); }
  catch { /* no storage in this host: the typed names stay in the box only */ }
  return '';
}

export function mountDevelopment(host, {request, project, sessionId, workId, clock = iso => iso || '', seconds = iso => iso || '', storage = globalThis.localStorage} = {}) {
  let alive = true, value = null, readAt = '', older = [], epoch = 0, armed = false;   // readAt: when this page received the status
  let preview = null, adoptOffer = null, adoptArmed = false, adoption = null;            // the adoption owner's last preview and adoption reads
  const section = el('section', '', 'development-section'); section.setAttribute('aria-label', 'Development'); section.dataset.development = workId;
  const head = el('div', '', 'development-head'), h3 = el('h3', 'Development', 'development-title'), again = control('Read again', 'development:read');
  head.append(h3, again);
  const readLine = el('p', '', 'development-read'); readLine.setAttribute('aria-live', 'polite');
  const laneGroup = el('div', '', 'development-group development-lane'), checkGroup = el('div', '', 'development-group development-checks'), runGroup = el('div', '', 'development-group development-run');
  const previewGroup = el('div', '', 'development-group development-preview'), adoptGroup = el('div', '', 'development-group development-adopt');
  section.append(head, readLine, laneGroup, checkGroup, runGroup, previewGroup, adoptGroup);
  host.append(section);
  again.onclick = () => read();

  const said = (near, text, error = false) => {
    let line = near.parentElement?.querySelector?.('.development-said');
    if (!line) { line = el('p', '', 'development-said'); line.setAttribute('role', 'status'); near.parentElement?.append(line); }
    line.textContent = text; line.className = 'development-said' + (error ? ' error' : '');
    return line;
  };
  async function send(button, payload, {pending, done} = {}) {
    button.disabled = true; const label = button.textContent; if (pending) { button.textContent = pending.label; said(button, pending.text); }
    try {
      const result = await request(DEVELOPMENT_DOOR, {project, ...payload});
      if (!alive) return null;
      await read({keep: true});
      if (done) said(runGroup.querySelector('[data-control-owner="' + payload.name + '"]') || button, done(result));
      return result;
    } catch (error) {
      // a check that ran and FAILED, TIMED OUT or was refused answers ok:false with its recorded row (writing-request.mjs
      // puts the owner's answer on error.result): that is the check's outcome, not a refusal of the request
      if (alive && done && error.result?.check) { await read({keep: true}); said(runGroup.querySelector('[data-control-owner="' + payload.name + '"]') || button, done(error.result)); return error.result; }
      if (alive) { button.textContent = label; button.disabled = false; said(button, (error.message || 'The development owner did not accept this.') + (pending?.kept ? ' ' + pending.kept : ''), true); }
      return null;
    }
  }

  // The lane's grant exactly as the owner's status read states it (lane.grant): who holds it, its state, and its own
  // operations and paths; nothing here knows which paths or operations a lane is granted.
  function grantLines(grant) {
    const who = grant.parent_session_id === sessionId ? 'this session' : 'session ' + (grant.parent_session_id || 'not recorded');
    const head = el('p', '', 'development-line development-grant');
    head.append(el('span', 'Grant to ' + who + ': ', 'development-meta-word'), stateLine('development-grant', grant.state, 'development-state'),
      el('span', ' · ' + [grant.id, grant.state === 'ACTIVE' && grant.expires_at ? 'until ' + clock(grant.expires_at) : '', grant.revoked_at ? 'revoked ' + clock(grant.revoked_at) : ''].filter(Boolean).join(' · '), 'development-meta-word'));
    const list = values => (Array.isArray(values) && values.length ? values.join(', ') : 'not stated');
    return [head, el('p', 'Operations: ' + list(grant.operations) + ' · Paths: ' + list(grant.paths), 'development-line development-meta development-scope')];
  }
  function paintLane() {
    laneGroup.replaceChildren(el('h4', 'Lane', 'development-subtitle'));
    const lane = value?.lane, offers = value?.offers || [];
    if (!lane) laneGroup.append(el('p', 'No lane has been cut for this Work.', 'development-line'));
    else {
      const main = el('p', '', 'development-line development-lane-main');
      main.append(stateLine('development-lane', lane.state, 'development-state'), el('span', ' · branch ', 'development-meta-word'), el('code', lane.branch || 'not recorded', 'development-branch'));
      laneGroup.append(main);
      const facts = ['cut ' + clock(lane.cut_at) + ' from commit ' + String(lane.base || '').slice(0, 12)];
      if (lane.bytes) facts.push(bytesText(lane.bytes));
      if (lane.discarded_at) facts.push('discarded ' + clock(lane.discarded_at));
      laneGroup.append(el('p', facts.join(' · '), 'development-line development-meta'));
      if (lane.grant) laneGroup.append(...grantLines(lane.grant));
      if (lane.state === 'ACTIVE') {
        const path = el('p', '', 'development-line development-path'); path.append(el('span', 'Folder ', 'development-meta-word'), el('code', lane.checkout || '', 'development-code')); laneGroup.append(path);
      } else if (lane.removal?.worktree === 'REMOVED') laneGroup.append(el('p', 'Its folder was removed (' + lane.checkout + ').', 'development-line development-meta'));
      for (const item of lane.profiles_withheld || []) laneGroup.append(el('p', 'Not granted to this lane: ' + item.name + '. ' + item.reason, 'development-line development-meta'));
      if (lane.removal?.error) laneGroup.append(el('p', 'Removing the folder failed: ' + lane.removal.error, 'development-line error'));
    }
    const actions = el('div', '', 'development-actions');
    const cut = offers.find(offer => offer.action === 'lane'), discard = offers.find(offer => offer.action === 'discard');
    if (cut?.request) {
      const b = control('Cut a lane', 'development:cut-lane');
      b.onclick = () => send(b, cut.request, {pending: {label: 'Cutting the lane…', text: 'Cutting a lean copy of the app source; this takes a few seconds.'}});
      actions.append(b);
    } else if (cut?.refused) actions.append(el('p', 'Cut a lane is not offered: ' + cut.refused, 'development-line development-meta'));
    if (discard?.request) {
      const b = control(armed ? 'Discard now' : 'Discard the lane', 'development:discard-lane');
      b.dataset.armed = String(armed);
      b.onclick = () => {
        if (!armed) { armed = true; paintLane(); said(laneGroup.querySelector('[data-control="development:discard-lane"]'), 'Discard removes the lane folder and anything in it that was not adopted. Press Discard now to go ahead.'); return; }
        armed = false; return send(b, discard.request, {pending: {label: 'Discarding…', text: 'Revoking the lane grant and removing its folder.'}});
      };
      actions.append(b);
      if (armed) { const keep = control('Keep the lane', 'development:keep-lane'); keep.onclick = () => { armed = false; paintLane(); }; actions.append(keep); }
    }
    if (actions.children.length) laneGroup.append(actions);
  }

  function checkRow(row, shown) {
    const li = el('li', '', 'development-check'); li.dataset.check = row.id || ''; li.title = 'Check ' + row.id + ' · owner state ' + row.state;
    const top = el('p', '', 'development-line development-check-head');
    top.append(el('strong', row.name, 'development-check-name'), el('span', ' · ', 'development-meta-word'), stateLine('development-check', row.state, 'development-state'),
      el('span', ' · ' + [clock(row.ts), Number.isFinite(row.wall_ms) ? (row.wall_ms / 1000).toFixed(1) + ' s' : '', Number.isFinite(row.exit_code) ? 'exit code ' + row.exit_code : ''].filter(Boolean).join(' · '), 'development-meta-word'));
    li.append(top);
    if (row.targets?.length) li.append(el('p', 'Files: ' + row.targets.join(', '), 'development-line development-meta'));
    if (Number.isFinite(row.failing_total)) {
      if (!row.failing_total) li.append(el('p', 'No failing test names in its output.', 'development-line development-meta'));
      else {
        li.append(el('p', 'Failing tests (' + row.failing_total + '):', 'development-line'));
        const names = el('ul', '', 'development-failing'), listed = row.failing || [];
        const draw = all => names.replaceChildren(...listed.slice(0, all ? listed.length : shown).map(name => el('li', name, 'development-failing-name')));
        draw(false); li.append(names);
        if (listed.length > shown) {
          const all = control('Show all ' + listed.length + ' listed names', 'development:failing-all', row.id); all.setAttribute('aria-expanded', 'false');
          all.onclick = () => { const open = all.getAttribute('aria-expanded') !== 'true'; draw(open); all.setAttribute('aria-expanded', String(open)); all.textContent = open ? 'Show the first ' + shown : 'Show all ' + listed.length + ' listed names'; };
          li.append(all);
        }
        if (row.failing_total > (row.failing || []).length) li.append(el('p', (row.failing_total - row.failing.length) + ' more are not listed by the owner.', 'development-line development-meta'));
      }
      // the profile owner's measured sandbox-only failures (row.sandbox_differences), repeated only when this run failed them
      const known = (row.sandbox_differences || []).filter(item => item.failed);
      if (known.length) {
        li.append(el('p', 'The check profile declares ' + (known.length === 1 ? 'one of these' : known.length + ' of these') + ' as failing only inside the check sandbox:', 'development-line development-meta'));
        const list = el('ul', '', 'development-failing development-sandbox'), byCause = new Map();
        for (const item of known) byCause.set(item.cause, [...(byCause.get(item.cause) || []), item.name]);
        for (const [cause, names] of byCause) { const entry = el('li', '', 'development-failing-name'); entry.append(el('span', cause + ': ', 'development-meta-word development-sandbox-cause'), el('span', names.join(' · '))); list.append(entry); }
        li.append(list);
      }
      if (row.failing_complete === false) li.append(el('p', 'Its output was cut short, so this list may be incomplete.', 'development-line development-meta'));
    }
    return li;
  }
  function paintChecks() {
    checkGroup.replaceChildren(el('h4', 'Checks', 'development-subtitle'));
    const page = value?.development?.checks, rows = [...(page?.items || []), ...older];
    if (!rows.length) { checkGroup.append(el('p', 'No check has run for this Work.', 'development-line')); return; }
    const list = el('ol', '', 'development-check-list'); list.setAttribute('aria-label', 'Checks, newest first');
    const shown = failingShown(page);
    for (const row of rows) list.append(checkRow(row, shown));
    checkGroup.append(list);
    const total = page?.total ?? rows.length, next = older.length ? olderNext : page?.next_read;
    if (total > rows.length) checkGroup.append(el('p', 'Showing ' + rows.length + ' of ' + total + ' checks, newest first.', 'development-line development-meta'));
    if (next?.payload) {
      const more = control('Show older checks', 'development:more-checks');
      more.onclick = async () => {
        more.disabled = true;
        try { const result = await request(DEVELOPMENT_DOOR, {project, ...next.payload}); if (!alive) return; const part = result?.development?.checks; older = [...older, ...(part?.items || [])]; olderNext = part?.next_read || null; paintChecks(); }
        catch (error) { more.disabled = false; said(more, error.message || 'The older checks could not be read.', true); }
      };
      checkGroup.append(more);
    }
  }
  let olderNext = null;
  function paintRun() {
    runGroup.replaceChildren();
    const offers = (value?.offers || []).filter(offer => offer.action === 'check' && offer.request);
    if (!offers.length) { runGroup.hidden = true; return; }
    runGroup.hidden = false; runGroup.append(el('h4', 'Run a check', 'development-subtitle'));
    for (const offer of offers) {
      const row = el('div', '', 'development-run-row'), key = offer.grant_id + ':' + offer.name;
      const b = control('Run ' + offer.name, 'development:run-check', offer.name);
      let box = null;
      if (offer.targets) {
        const label = el('label', '', 'development-targets'); label.append(el('span', 'Files' + (offer.targets.required ? '' : ' (optional)'), 'development-targets-word'));
        box = el('input'); box.type = 'text'; box.dataset.control = 'development:check-targets'; box.dataset.controlOwner = offer.name; box.value = draft(storage, key);
        box.setAttribute('aria-label', 'Files for ' + offer.name); box.setAttribute('spellcheck', 'false');
        box.oninput = () => draft(storage, key, box.value);
        label.append(box); row.append(label);
        row.append(el('p', 'Names matching ' + offer.targets.globs.join(', ') + ', separated by spaces.', 'development-line development-meta'));
      }
      b.onclick = () => {
        const names = box ? targetsFromText(box.value) : [];
        const payload = {...offer.request, ...(names.length ? {targets: names} : {})};
        return send(b, payload, {pending: {label: 'Running ' + offer.name + '…', text: 'Started ' + seconds(new Date().toISOString()) + '. The owner answers when the check ends.', kept: box ? 'The file names are kept.' : ''},
          done: result => 'Finished: ' + ownerStateWord('development-check', result?.check?.state).words + '.' + (result?.check?.reason ? ' ' + result.check.reason : '') + ' It is the newest check above.'});
      };
      row.prepend(b); runGroup.append(row);
    }
  }
  // ---- card 3, Preview: every fact is the adoption owner's preview read; pressing Preview only reads ----
  const line = (text, cls = 'development-line development-meta') => el('p', text, cls);
  // names (files, tests, inputs) are a mono list; sentences (refusals, reviews) are interface-font lines
  function list(items, draw) { const ul = el('ul', '', 'development-failing development-adopt-list'); for (const item of items) { const li = el('li', '', 'development-failing-name'); li.append(...draw(item)); ul.append(li); } return ul; }
  const sentences = (items, draw) => items.map(item => { const p = el('p', '', 'development-line development-adopt-item'); p.append(...draw(item)); return p; });
  const plural = (n, word) => n + ' ' + word + (n === 1 ? '' : 's');
  function paintPreview() {
    previewGroup.replaceChildren();
    const lane = value?.lane;
    if (!lane || lane.state !== 'ACTIVE') { previewGroup.hidden = true; return; }
    if (preview && preview.lane?.branch !== lane.branch) { preview = null; adoptOffer = null; }
    previewGroup.hidden = false; previewGroup.append(el('h4', 'Preview', 'development-subtitle'));
    if (!preview) previewGroup.append(line('See what Adopt would change in the live tree before you press it: the files, the checks and any newly failing tests, the reviews and the publication inputs it moves. Nothing changes.', 'development-line'));
    const b = control(preview ? 'Preview again' : 'Preview Adopt', 'development:adopt-preview'), actions = el('div', '', 'development-actions');
    b.onclick = async () => {
      b.disabled = true; b.textContent = 'Previewing…'; adoptArmed = false;
      said(b, 'Each current check runs once more on a scratch copy of the live commit, to find newly failing tests; this takes about as long as those checks took.');
      try {
        const result = await request(DEVELOPMENT_DOOR, previewRequest(project, workId, sessionId));
        if (!alive) return;
        if (!result?.preview) throw Error('The preview read returned something else; nothing is shown.');
        preview = result.preview; adoptOffer = (result.offers || []).find(offer => offer.action === 'adopt') || null; paintPreview(); paintAdopt();
      } catch (error) { if (alive) { b.disabled = false; b.textContent = preview ? 'Preview again' : 'Preview Adopt'; said(b, error.message || 'The preview could not be read.', true); } }
    };
    actions.append(b); previewGroup.append(actions);
    if (!preview) return;
    previewGroup.append(line('Read at ' + seconds(preview.observed_at) + ' from the adoption owner · live tree at ' + short(preview.live_head) + ' · lane cut from ' + short(preview.lane?.base)
      + (Number.isFinite(preview.wall_ms) ? ' · took ' + (preview.wall_ms / 1000).toFixed(1) + ' s' : '')));
    const files = preview.files || [];
    previewGroup.append(line('Files Adopt would change (' + files.length + '):', 'development-line'));
    if (files.length) previewGroup.append(list(files, f => [el('code', f.path, 'development-code'), el('span', ' · ' + f.change + (Number.isFinite(f.added) ? ' · +' + f.added + ' −' + f.removed : ''), 'development-meta-word'),
      ...(f.flagged ? [el('span', ' · ⚑ tool or profile file', 'development-flag')] : [])]));
    previewGroup.append(line('Checks (' + (preview.checks || []).length + '):', 'development-line'));
    for (const c of preview.checks || []) {
      const head = el('p', '', 'development-line development-check-head');
      head.append(el('strong', c.name, 'development-check-name'), el('span', ' · ', 'development-meta-word'), stateLine('development-check', c.state, 'development-state'),
        el('span', ' · run ' + clock(c.ts) + ' · ' + (c.current ? 'it read the lane files as they are now' : 'the lane files changed after it ran'), 'development-meta-word'));
      head.title = 'Check ' + c.id; previewGroup.append(head);
      const n = c.newly || {};
      if (n.known && n.total) { previewGroup.append(line('Newly failing tests (' + n.total + '): they pass on the live commit and fail in the lane.', 'development-line error')); previewGroup.append(list(n.names, name => [el('span', name)])); }
      else if (n.known) previewGroup.append(line('No newly failing tests. The same check on the live commit fails ' + plural(n.base_failing_total, 'test') + '; in the lane ' + n.lane_failing_total + '.'));
      else previewGroup.append(line('Newly failing tests are not known: ' + (n.reason || 'the owner did not say why') + '.'));
    }
    const stale = preview.reviews_stale || [], changed = inputChip('STALE')?.label || '';
    previewGroup.append(line(stale.length ? 'After Adopt these reviews will read “' + changed + '” (' + stale.length + '):' : 'No review read a changed file at another version, so no review will read “' + changed + '”.', 'development-line'));
    if (stale.length) previewGroup.append(...sentences(stale, r => [el('span', (r.work_title || r.work_id) + ' · review ' + r.review_id + ' · '), el('span', r.reason, 'development-meta-word')]));
    const carry = preview.carry || {};
    if (carry.unavailable) previewGroup.append(line('The close carry could not be read: ' + carry.unavailable));
    else if ((carry.inputs || []).length) {
      previewGroup.append(line('Publication inputs the close carries: ' + carry.inputs_total + '. These ' + carry.inputs.length + ' pin a changed file. ' + (carry.note || ''), 'development-line'));
      previewGroup.append(list(carry.inputs, i => [el('code', i.node_id.slice(0, 22) + '…', 'development-code'), el('span', ' · ' + i.changed_files.join(', ') + ' · today: ' + i.today_reason, 'development-meta-word')]));
    } else previewGroup.append(line(carry.note || ('None of the ' + carry.inputs_total + ' publication inputs the close carries pins a changed file.')));
    if (preview.scratch) previewGroup.append(line('Scratch copy of the live commit ' + short(preview.scratch.commit) + ' (' + bytesText(preview.scratch.bytes) + ', ' + preview.scratch.paths.join(', ') + '): '
      + (preview.applies === true ? 'the lane diff applies to it' : 'the lane diff does not apply to it') + '; ' + (preview.scratch.removed ? 'it was removed.' : 'it was NOT removed.')));
  }
  // ---- card 4, Adopt: the offer's request, sent unchanged after a second press; afterwards the adoption read ----
  function paintAdopt() {
    adoptGroup.replaceChildren();
    const lane = value?.lane, done = adoption?.adoption;
    if (lane?.state === 'ADOPTED' && done) {
      adoptGroup.hidden = false; adoptGroup.append(el('h4', 'Adopt', 'development-subtitle'));
      const after = el('p', '', 'development-line development-adopted'); after.title = 'Adoption ' + done.id + ' · commit ' + done.commit;
      after.append(stateLine('development-lane', lane.state, 'development-state'), el('span', ' as ' + short(done.commit) + '. Reload the window to run it.'));
      adoptGroup.append(after);
      adoptGroup.append(line('Committed ' + clock(done.committed_at) + ' on ' + short(done.base) + ' · Work-Id ' + (done.trailer || {})['Work-Id'] + ' · ' + plural((done.files || []).length, 'file') + ' · read at ' + seconds(adoption.observed_at) + ' from the adoption owner'));
      if (adoption.in_live_history === false) adoptGroup.append(line('The adoption commit is no longer in the live history.', 'development-line error'));
      const reviews = adoption.reviews || [], changed = inputChip('STALE')?.label || '';
      const stale = reviews.filter(r => inputChip(r.currentness)?.label === changed), other = reviews.filter(r => !stale.includes(r) && !inputChip(r.currentness));
      adoptGroup.append(line(stale.length ? 'Reviews now reading “' + changed + '” (' + stale.length + '):' : 'No review moved by this adoption reads “' + changed + '”.', 'development-line'));
      const review = r => [el('span', (r.work_title || r.work_id) + ' · review ' + r.review_id + ' · '), el('span', r.reason || '', 'development-meta-word')];
      if (stale.length) adoptGroup.append(...sentences(stale, review));
      if (other.length) adoptGroup.append(line('Reviews whose standing the review owner cannot state (' + other.length + '):', 'development-line'), ...sentences(other, review));
      return;
    }
    if (lane?.state !== 'ACTIVE' || !preview || !adoptOffer) { adoptGroup.hidden = true; return; }
    adoptGroup.hidden = false; adoptGroup.append(el('h4', 'Adopt', 'development-subtitle'));
    const actions = el('div', '', 'development-actions');
    if (!adoptOffer.request) {
      const b = control('Adopt', 'development:adopt'); b.disabled = true; actions.append(b); adoptGroup.append(actions);
      adoptGroup.append(line('Adopt is refused for this preview:', 'development-line'));
      adoptGroup.append(...sentences(adoptOffer.refused || [], text => [el('span', text)]));
      return;
    }
    adoptGroup.append(line('Adopt applies the ' + plural((preview.files || []).length, 'file') + ' above to the live tree at ' + short(preview.live_head) + ' and makes one local commit with Work-Id ' + (preview.work?.id || workId) + '. The lane folder is then removed.', 'development-line'));
    const b = control(adoptArmed ? 'Adopt now' : 'Adopt', 'development:adopt'); b.dataset.armed = String(adoptArmed);
    b.onclick = async () => {
      if (!adoptArmed) { adoptArmed = true; paintAdopt(); said(adoptGroup.querySelector('[data-control="development:adopt"]'), 'Press Adopt now to commit these files to the live tree.'); return; }
      b.disabled = true; b.textContent = 'Adopting…'; said(b, 'Applying the lane diff to the live tree and committing it.');
      try {
        const result = await request(DEVELOPMENT_DOOR, {project, ...adoptOffer.request});
        if (!alive) return;
        adoptArmed = false; preview = null; adoptOffer = null;
        await read({keep: true});
      } catch (error) { if (alive) { b.disabled = false; b.textContent = 'Adopt now'; said(b, error.message || 'The adoption owner did not accept this.', true); } }
    };
    actions.append(b);
    if (adoptArmed) { const keep = control('Not now', 'development:adopt-cancel'); keep.onclick = () => { adoptArmed = false; paintAdopt(); }; actions.append(keep); }
    adoptGroup.append(actions);
  }
  function paint() {
    const work = value?.work || {};
    readLine.textContent = 'Read at ' + seconds(readAt) + ' from the development owner, for the Work “' + (work.title || work.id || workId) + '” · read again after each action here and when the session changes.';
    paintLane(); paintChecks(); paintRun(); paintPreview(); paintAdopt();
  }
  async function read({keep = false} = {}) {
    const ticket = ++epoch;
    if (!keep) readLine.textContent = 'Reading the development status…';
    try {
      const result = await request(DEVELOPMENT_DOOR, statusRequest(project, workId, sessionId));
      if (!alive || ticket !== epoch) return;
      if (!result || !('development' in result) || !('offers' in result)) throw Error('The development status read returned something else; nothing is shown.');
      // an adopted lane: the adoption owner's read is taken with every status read (it is cheap: no check runs)
      if (result.lane?.state === 'ADOPTED') {
        try { adoption = await request(DEVELOPMENT_DOOR, adoptionRequest(project, workId)); } catch { adoption = null; }
        if (!alive || ticket !== epoch) return;
      } else adoption = null;
      value = result; readAt = new Date().toISOString(); older = []; olderNext = null; paint();
    } catch (error) {
      if (!alive || ticket !== epoch) return;
      readLine.textContent = (error.message || 'The development status could not be read.') + ' What was shown before is no longer current.'; readLine.className = 'development-read error';
      return;
    }
    readLine.className = 'development-read';
  }
  const ready = read();
  return {section, ready, refresh: () => read({keep: true}), get value() { return value; }, workId, sessionId,
    destroy() { alive = false; section.remove(); }};
}
