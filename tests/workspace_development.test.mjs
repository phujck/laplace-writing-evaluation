// The Development section (wave 13, lane-checks): the open session's pane on the Sessions page shows the Work's lane and
// checks from the development owner's status read and sends only the requests that read offers.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {installDOM} from './helpers/evidence_reader_harness.mjs';
import {mountDevelopment, sessionWorkId, statusRequest, previewRequest, adoptionRequest, failingShown, targetsFromText, bytesText, DEVELOPMENT_DOOR} from '../src/laplace/web/static_shared/workspace-development.mjs';
import {mountSessionAnalytics} from '../src/laplace/web/static_shared/workspace-analytics.mjs';

const tick = () => new Promise(ok => setTimeout(ok, 0));
const LANE = {id: 'lane:WORK-1', state: 'ACTIVE', work_id: 'WORK-1', checkout: '/tmp/lanes/WORK-1', base: 'abcdef0123456789', branch: 'app-dev/WORK-1-20261108T200000Z',
  cut_at: '2026-11-08T20:00:00+00:00', expires_at: '2026-11-09T20:00:00+00:00', bytes: 80 * 1024 * 1024, parent_session_id: 'WS-1',
  profiles_withheld: [{name: 'python-tests', reason: 'development_source: no registered runtime is declared for this root.'}], grants: ['DG-1'],
  grant: {id: 'DG-1', state: 'ACTIVE', paths: ['src/**', 'tests/**'], operations: ['read', 'check'], parent_session_id: 'WS-1', expires_at: '2026-11-09T20:00:00+00:00', revoked_at: null}};
const CHECKS = [
  {id: 'DK-2', grant_id: 'DG-1', name: 'node-tests', state: 'FAILED', exit_code: 1, wall_ms: 2300, ts: '2026-11-08T20:05:00Z', targets: ['tests/a.test.mjs'], failing: ['a deliberately failing case', 'tests/a.test.mjs'], failing_total: 2, failing_complete: true},
  {id: 'DK-1', grant_id: 'DG-1', name: 'syntax', state: 'COMPLETE', exit_code: 0, wall_ms: 400, ts: '2026-11-08T20:04:00Z', targets: ['src/app.py']}];
const OFFERS = [{action: 'discard', request: {action: 'discard', work_id: 'WORK-1', branch: LANE.branch}},
  {action: 'check', grant_id: 'DG-1', name: 'node-suite', request: {action: 'check', grant_id: 'DG-1', name: 'node-suite'}, targets: null},
  {action: 'check', grant_id: 'DG-1', name: 'node-tests', request: {action: 'check', grant_id: 'DG-1', name: 'node-tests'}, targets: {globs: ['tests/*.test.mjs'], required: true}}];
// requested_limit is the owner's page size (development_source._fitted); the page asks for none, so the reply states it
const status = ({lane = LANE, checks = CHECKS, offers = OFFERS, total = checks.length, next = null, requested = 8} = {}) => ({work: {id: 'WORK-1', title: 'Change the app'}, lane, offers,
  development: {cut: 'c', checks: lane || checks.length ? {total, offset: 0, limit: requested, requested_limit: requested, items: checks, next_read: next} : null}, status_notes: []});

function fixture(responses) {
  const d = installDOM(), host = document.createElement('section'), posts = [], store = new Map();
  d.body.append(host);
  const request = async (path, payload) => { posts.push({path, payload}); const answer = responses(payload, posts.length); if (answer instanceof Error) throw answer; return answer; };
  const storage = {getItem: k => store.get(k) ?? null, setItem: (k, v) => store.set(k, v), removeItem: k => store.delete(k)};
  return {d, host, posts, store, mount: () => mountDevelopment(host, {request, project: 'garden', sessionId: 'WS-1', workId: 'WORK-1', clock: iso => 'at ' + iso, seconds: () => '20:06:00', storage})};
}
const byControl = (host, id, owner) => host.querySelectorAll('[data-control="' + id + '"]').filter(n => !owner || n.dataset.controlOwner === owner);

test('the session is on the Work its newest Work-bound turn names, and the status read is the owner request', () => {
  assert.equal(sessionWorkId({turns: [{id: 'a', work_id: 'WORK-0'}, {id: 'b'}, {id: 'c', work_id: 'WORK-1'}, {id: 'd'}]}), 'WORK-1');
  assert.equal(sessionWorkId({turns: [{id: 'a'}]}), '');
  assert.deepEqual(statusRequest('garden', 'WORK-1', 'WS-1'), {project: 'garden', action: 'status', work_id: 'WORK-1', session_id: 'WS-1'});
  assert.ok(!('limit' in statusRequest('garden', 'WORK-1', 'WS-1')), 'the page sends no limit: the owner page size applies');
  assert.equal(failingShown({requested_limit: 5}), 5); assert.equal(failingShown({requested_limit: 0}), Infinity); assert.equal(failingShown({}), Infinity); assert.equal(failingShown(null), Infinity);
  assert.deepEqual(targetsFromText(' tests/a.test.mjs,  tests/b.test.mjs\n'), ['tests/a.test.mjs', 'tests/b.test.mjs']);
  assert.equal(bytesText(77 * 1024 * 1024), 'about 77 MB');
});

test('with no lane, Cut a lane sends the offered request unchanged and the section re-reads', async () => {
  const offer = {action: 'lane', request: {action: 'lane', work_id: 'WORK-1', expected_work_revision: 'sha256:r', parent_session_id: 'WS-1'}};
  let cut = false;
  const f = fixture(payload => payload.action === 'lane' ? (cut = true, {ok: true, lane: LANE}) : cut ? status() : status({lane: null, checks: [], offers: [offer]}));
  try {
    const view = f.mount(); await view.ready;
    assert.equal(f.posts[0].path, DEVELOPMENT_DOOR);
    assert.deepEqual(f.posts[0].payload, {project: 'garden', action: 'status', work_id: 'WORK-1', session_id: 'WS-1'});
    assert.match(f.host.textContent, /No lane has been cut for this Work\./);
    assert.match(f.host.textContent, /No check has run for this Work\./);
    assert.match(f.host.textContent, /Read at 20:06:00 from the development owner, for the Work “Change the app”/);
    const [button] = byControl(f.host, 'development:cut-lane');
    await button.click(); await tick();
    assert.deepEqual(f.posts[1].payload, {project: 'garden', ...offer.request});
    assert.equal(f.posts[2].payload.action, 'status');
    assert.match(f.host.textContent, /app-dev\/WORK-1-20261108T200000Z/);
    assert.equal(byControl(f.host, 'development:cut-lane').length, 0, 'the owner no longer offers a lane once one is ACTIVE');
  } finally { f.d.restore(); }
});

test('the lane and its checks are drawn from the owner read: facts, newest-first checks, failing names, withheld profiles', async () => {
  const f = fixture(() => status());
  try {
    const view = f.mount(); await view.ready;
    const text = f.host.textContent;
    assert.match(text, /branch app-dev\/WORK-1-20261108T200000Z/);
    assert.match(text, /cut at 2026-11-08T20:00:00\+00:00 from commit abcdef012345 · about 80 MB/);
    assert.match(text, /Grant to this session: ●Active · DG-1 · until at 2026-11-09T20:00:00\+00:00/);
    assert.match(text, /Operations: read, check · Paths: src\/\*\*, tests\/\*\*/);
    assert.doesNotMatch(text, /no plain words for this owner state/);
    assert.match(text, /Not granted to this lane: python-tests\. development_source: no registered runtime/);
    const rows = f.host.querySelectorAll('li').filter(n => n.dataset.check);
    assert.deepEqual(rows.map(n => n.dataset.check), ['DK-2', 'DK-1']);
    assert.match(rows[0].textContent, /node-tests/); assert.match(rows[0].textContent, /Failing tests \(2\):/);
    assert.deepEqual(rows[0].querySelectorAll('li').map(n => n.textContent), ['a deliberately failing case', 'tests/a.test.mjs']);
    assert.match(rows[0].textContent, /2\.3 s · exit code 1/);
    assert.doesNotMatch(rows[1].textContent, /Failing/);
    assert.equal(rows[0].title, 'Check DK-2 · owner state FAILED');
    for (const state of f.host.querySelectorAll('.development-state')) assert.match(state.title, /^Owner state: /);
    assert.deepEqual(byControl(f.host, 'development:run-check').map(b => b.textContent), ['Run node-suite', 'Run node-tests']);
    assert.equal(byControl(f.host, 'development:check-targets').length, 1, 'only the profile that declares targets takes file names');
    assert.match(f.host.textContent, /Names matching tests\/\*\.test\.mjs, separated by spaces\./);
  } finally { f.d.restore(); }
});

test('Run sends the offered check with the typed file names; a refusal is the owner sentence beside it and the names stay', async () => {
  let refuse = true;
  const f = fixture(payload => payload.action !== 'check' ? status() : refuse ? new Error('development_source: target src/app.py does not match check node-tests targets tests/*.test.mjs.')
    : Object.assign(Error('Operation did not complete (200)'), {result: {ok: false, check: {id: 'DK-3', name: 'node-tests', state: 'FAILED'}}}));
  try {
    const view = f.mount(); await view.ready;
    const [box] = byControl(f.host, 'development:check-targets', 'node-tests');
    box.value = 'src/app.py'; box.oninput();
    assert.equal(f.store.get('laplace:development-targets:DG-1:node-tests'), 'src/app.py');
    const [run] = byControl(f.host, 'development:run-check', 'node-tests');
    await run.click(); await tick();
    assert.deepEqual(f.posts.at(-1).payload, {project: 'garden', action: 'check', grant_id: 'DG-1', name: 'node-tests', targets: ['src/app.py']});
    const said = run.parentElement.querySelector('.development-said');
    assert.match(said.textContent, /^development_source: target src\/app\.py does not match check node-tests targets tests\/\*\.test\.mjs\. The file names are kept\.$/);
    assert.equal(box.value, 'src/app.py'); assert.equal(run.disabled, false);
    refuse = false; box.value = 'tests/a.test.mjs'; box.oninput();
    await run.click(); await tick(); await tick();
    assert.deepEqual(f.posts.find(p => p.payload.targets?.[0] === 'tests/a.test.mjs').payload, {project: 'garden', action: 'check', grant_id: 'DG-1', name: 'node-tests', targets: ['tests/a.test.mjs']});
    const after = byControl(f.host, 'development:run-check', 'node-tests')[0].parentElement.querySelector('.development-said');
    assert.match(after.textContent, /^Finished: .+\. It is the newest check above\.$/, 'a FAILED check (ok:false with its row) is an outcome, not a refusal');
    assert.equal(f.posts.at(-1).payload.action, 'status', 'the section re-read after the check');
    const [suite] = byControl(f.host, 'development:run-check', 'node-suite');
    await suite.click(); await tick();
    assert.deepEqual(f.posts.find(p => p.payload.name === 'node-suite').payload, {project: 'garden', action: 'check', grant_id: 'DG-1', name: 'node-suite'});
  } finally { f.d.restore(); }
});

test('Discard asks again on the first press and then sends the offered discard request unchanged', async () => {
  const f = fixture(payload => payload.action === 'discard' ? {ok: true, lane: {...LANE, state: 'DISCARDED'}} : status());
  try {
    const view = f.mount(); await view.ready;
    await byControl(f.host, 'development:discard-lane')[0].click();
    assert.equal(f.posts.filter(p => p.payload.action === 'discard').length, 0, 'the first press sends nothing');
    assert.match(f.host.textContent, /Discard removes the lane folder and anything in it that was not adopted/);
    await byControl(f.host, 'development:keep-lane')[0].click();
    assert.equal(byControl(f.host, 'development:discard-lane')[0].textContent, 'Discard the lane');
    await byControl(f.host, 'development:discard-lane')[0].click();
    const now = byControl(f.host, 'development:discard-lane')[0]; assert.equal(now.textContent, 'Discard now');
    await now.click(); await tick();
    assert.deepEqual(f.posts.find(p => p.payload.action === 'discard').payload, {project: 'garden', ...OFFERS[0].request});
  } finally { f.d.restore(); }
});

test('a discarded lane says its grant was revoked and its folder removed, and no longer claims a grant', async () => {
  const gone = {...LANE, state: 'DISCARDED', discarded_at: '2026-11-08T20:10:00+00:00', revoked_grants: ['DG-1'], removal: {worktree: 'REMOVED', branch: 'REMOVED'},
    grant: {...LANE.grant, state: 'REVOKED', revoked_at: '2026-11-08T20:10:00+00:00'}};
  const f = fixture(() => status({lane: gone, offers: [{action: 'lane', request: {action: 'lane', work_id: 'WORK-1', expected_work_revision: 'r', parent_session_id: 'WS-1'}}]}));
  try {
    const view = f.mount(); await view.ready;
    assert.match(f.host.textContent, /Grant to this session: ⊘Revoked · DG-1 · revoked at 2026-11-08T20:10:00\+00:00/);
    assert.doesNotMatch(f.host.textContent, /until/, 'a revoked grant states no end time');
    assert.match(f.host.textContent, /Its folder was removed \(\/tmp\/lanes\/WORK-1\)\./);
    assert.match(f.host.textContent, /discarded at 2026-11-08T20:10:00\+00:00/);
    assert.equal(byControl(f.host, 'development:cut-lane').length, 1);
  } finally { f.d.restore(); }
});

test('the grant line follows the grant in the owner read: other paths, other operations, another session, a revoked grant', async () => {
  const other = {...LANE, grant: {...LANE.grant, paths: ['docs/**'], operations: ['read'], parent_session_id: 'WS-9'}};
  let f = fixture(() => status({lane: other}));
  try {
    const view = f.mount(); await view.ready;
    assert.match(f.host.textContent, /Grant to session WS-9: ●Active/);
    assert.match(f.host.textContent, /Operations: read · Paths: docs\/\*\*/);
    assert.doesNotMatch(f.host.textContent, /this session|src\/\*\*/);
  } finally { f.d.restore(); }
  f = fixture(() => status({lane: {...LANE, grant: {...LANE.grant, state: 'REVOKED', revoked_at: '2026-11-08T20:07:00+00:00'}}}));
  try {
    const view = f.mount(); await view.ready;
    const line = f.host.querySelector('.development-grant');
    assert.match(line.textContent, /^Grant to this session: ⊘Revoked · DG-1 · revoked at 2026-11-08T20:07:00\+00:00$/);
    assert.equal(line.querySelector('.development-state').title, 'Owner state: REVOKED');
  } finally { f.d.restore(); }
  // the module holds no lane paths or operation names of its own: the scope is only what the read states
  const source = readFileSync(new URL('../src/laplace/web/static_shared/workspace-development.mjs', import.meta.url), 'utf8');
  for (const literal of ["'src/**'", "src, tests", "'candidate'", "'apply'", 'read, write']) assert.ok(!source.includes(literal), 'the module writes ' + literal);
});

test('a declared sandbox-only failure is repeated beside the names only when the run failed it', async () => {
  const suite = {id: 'DK-3', grant_id: 'DG-1', name: 'node-suite', state: 'FAILED', exit_code: 1, wall_ms: 99000, ts: '2026-11-08T20:06:00Z', failing: ['tests/manuscript_dom.test.mjs', 'a real failure', 'tests/t1.test.mjs', 'tests/t2.test.mjs'],
    failing_total: 4, failing_complete: true, sandbox_differences: [{name: 'tests/manuscript_dom.test.mjs', cause: 'a browser test', failed: true}, {name: 'tests/other.test.mjs', cause: 'not this run', failed: false},
      {name: 'tests/t1.test.mjs', cause: 'a TeX build', failed: true}, {name: 'tests/t2.test.mjs', cause: 'a TeX build', failed: true}]};
  const f = fixture(() => status({checks: [suite]}));
  try {
    const view = f.mount(); await view.ready;
    const row = f.host.querySelector('li[data-check="DK-3"]');
    assert.match(row.textContent, /The check profile declares 3 of these as failing only inside the check sandbox:/);
    assert.deepEqual(row.querySelector('.development-sandbox').querySelectorAll('li').map(n => n.textContent), ['a browser test: tests/manuscript_dom.test.mjs', 'a TeX build: tests/t1.test.mjs · tests/t2.test.mjs'], 'one line per cause');
    assert.doesNotMatch(row.textContent, /not this run/);
    assert.match(row.textContent, /Failed/); assert.doesNotMatch(row.textContent, /no plain words/);
  } finally { f.d.restore(); }
});

test('a long failing list shows the owner page size of names and the rest one labelled press away', async () => {
  const names = Array.from({length: 12}, (_, i) => 'case ' + i);
  const f = fixture(() => status({checks: [{id: 'DK-9', name: 'node-suite', state: 'FAILED', ts: 'x', failing: names, failing_total: 30, failing_complete: true}]}));
  try {
    const view = f.mount(); await view.ready;
    const row = f.host.querySelectorAll('li').find(n => n.dataset.check === 'DK-9'), listed = () => row.querySelectorAll('li').map(n => n.textContent);
    assert.deepEqual(listed(), names.slice(0, 8));
    const [all] = byControl(f.host, 'development:failing-all', 'DK-9');
    assert.equal(all.textContent, 'Show all 12 listed names'); assert.equal(all.getAttribute('aria-expanded'), 'false');
    await all.click(); assert.deepEqual(listed(), names); assert.equal(all.textContent, 'Show the first 8');
    assert.match(row.textContent, /18 more are not listed by the owner\./);
    await all.click(); assert.equal(listed().length, 8);
  } finally { f.d.restore(); }
});

test('the count of failing names shown is the requested_limit of the owner reply, not a page constant', async () => {
  const names = Array.from({length: 12}, (_, i) => 'case ' + i), check = {id: 'DK-9', name: 'node-suite', state: 'FAILED', ts: 'x', failing: names, failing_total: 12, failing_complete: true};
  for (const [requested, expected] of [[3, 3], [5, 5], [20, 12]]) {
    const f = fixture(() => status({checks: [check], requested}));
    try {
      const view = f.mount(); await view.ready;
      const row = f.host.querySelectorAll('li').find(n => n.dataset.check === 'DK-9'), listed = () => row.querySelectorAll('li').map(n => n.textContent);
      assert.equal(f.posts[0].payload.limit, undefined, 'the request names no limit');
      assert.deepEqual(listed(), names.slice(0, expected), 'requested_limit ' + requested);
      const [all] = byControl(f.host, 'development:failing-all', 'DK-9');
      if (expected < names.length) { assert.equal(all.textContent, 'Show all 12 listed names'); await all.click(); assert.equal(all.textContent, 'Show the first ' + requested); } else assert.equal(all, undefined, 'a page size above the list needs no Show all');
    } finally { f.d.restore(); }
  }
  // a reply that states no page size: nothing is invented, every listed name is shown
  const f = fixture(() => { const reply = status({checks: [check]}); delete reply.development.checks.requested_limit; return reply; });
  try {
    const view = f.mount(); await view.ready;
    const row = f.host.querySelectorAll('li').find(n => n.dataset.check === 'DK-9');
    assert.equal(row.querySelectorAll('li').length, 12); assert.equal(byControl(f.host, 'development:failing-all', 'DK-9').length, 0);
  } finally { f.d.restore(); }
});

test('older checks continue only through the owner next_read', async () => {
  const next = {operation: 'development_source', payload: {action: 'status', work_id: 'WORK-1', offset: 2, limit: 8, cut: 'c'}};
  const f = fixture(payload => payload.offset === 2 ? {development: {checks: {total: 3, items: [{id: 'DK-0', name: 'syntax', state: 'COMPLETE', ts: 'x'}], next_read: null}}} : status({total: 3, next}));
  try {
    const view = f.mount(); await view.ready;
    assert.match(f.host.textContent, /Showing 2 of 3 checks, newest first\./);
    await byControl(f.host, 'development:more-checks')[0].click(); await tick();
    assert.deepEqual(f.posts.at(-1).payload, {project: 'garden', ...next.payload});
    assert.deepEqual(f.host.querySelectorAll('li').filter(n => n.dataset.check).map(n => n.dataset.check), ['DK-2', 'DK-1', 'DK-0']);
    assert.equal(byControl(f.host, 'development:more-checks').length, 0);
  } finally { f.d.restore(); }
});

test('a failed read says so and stops showing the old status as current', async () => {
  let fail = false;
  const f = fixture(() => fail ? new Error('Work WORK-1 is unavailable.') : status());
  try {
    const view = f.mount(); await view.ready; fail = true; await view.refresh();
    assert.match(f.host.querySelector('.development-read').textContent, /^Work WORK-1 is unavailable\. What was shown before is no longer current\.$/);
  } finally { f.d.restore(); }
});

test('every control the section draws is declared with its label and states', () => {
  const declarations = readFileSync(new URL('../src/laplace/native/declarations.py', import.meta.url), 'utf8');
  const source = readFileSync(new URL('../src/laplace/web/static_shared/workspace-development.mjs', import.meta.url), 'utf8');
  const ids = [...new Set([...source.matchAll(/'development:([a-z-]+)'/g)].map(m => m[1]))];
  assert.deepEqual(ids.sort(), ['adopt', 'adopt-cancel', 'adopt-preview', 'check-targets', 'cut-lane', 'discard-lane', 'failing-all', 'keep-lane', 'more-checks', 'read', 'run-check']);
  for (const id of ids) assert.equal([...declarations.matchAll(new RegExp('\\("' + id + '", "', 'g'))].length, 2, id + ' is declared once with its label and once with its states');
});

test('the Sessions pane mounts Development only for a session whose saved turns name a Work', async () => {
  const d = installDOM(), host = document.createElement('section'), posts = []; d.body.append(host);
  const sessions = [{session_id: 'WS-1', project: 'garden', title: 'On a task', role: 'author', provider: 'claude', model: 'default', turn_count: 1, state: 'completed', created_at: 'x', last_turn: {turn_id: 'WT-1', at: 'x', ended_at: 'x'}},
    {session_id: 'WS-2', project: 'garden', title: 'Plain', role: 'author', provider: 'claude', model: 'default', turn_count: 1, state: 'completed', created_at: 'x', last_turn: {turn_id: 'WT-2', at: 'x', ended_at: 'x'}}];
  const request = async (path, payload) => {
    if (payload) { posts.push({path, payload}); return status(); }
    if (path === '/projects/library') return {projects: []};
    if (path.startsWith('/authoring/state?')) return {schema_version: 'laplace.session-index/1', counts: {}, projects: [], total: 2, sessions, observed_at: new Date().toISOString()};
    const id = new URL(path, 'http://local').searchParams.get('id');
    return {session: {id, project: 'garden'}, turns: [{id: 'WT-' + id, ts: 'x', text: 'hello', ...(id === 'WS-1' ? {work_id: 'WORK-1'} : {}), reply: {status: 'completed', display_text: 'ok'}}], active: null};
  };
  try {
    const page = await mountSessionAnalytics(host, {request, parameters: new URLSearchParams()});
    const open = id => host.querySelectorAll('li').find(n => n.dataset.session === id).firstElementChild.click();
    await open('WS-2'); await tick(); await tick();
    assert.equal(host.querySelectorAll('.development-section').length, 0);
    await open('WS-1'); await tick(); await tick(); await tick();
    assert.equal(host.querySelectorAll('.development-section').length, 1);
    assert.deepEqual(posts[0], {path: DEVELOPMENT_DOOR, payload: {project: 'garden', action: 'status', work_id: 'WORK-1', session_id: 'WS-1'}});
    await open('WS-2'); await tick(); await tick();
    assert.equal(host.querySelectorAll('.development-section').length, 0, 'switching to a session on no Work removes the section');
    page.destroy();
  } finally { d.restore(); }
});

// ---- wave 13, adopt: card 3 Preview and card 4 Adopt (development_adoption.preview / adopt / adoption) ----
const PREVIEW = {id: 'DP-0123456789abcdef01234567', observed_at: '2026-11-08T20:10:00Z', work: {id: 'WORK-1', title: 'Change the app'},
  lane: {id: 'lane:WORK-1', branch: LANE.branch, base: LANE.base, checkout: LANE.checkout}, live_head: LANE.base, live_root: '/live', wall_ms: 4200, active_turns: 0, applies: true,
  files: [{path: 'src/app.py', change: 'modified', flagged: false, added: 1, removed: 1}, {path: 'scripts/tool.py', change: 'added', flagged: true, added: 4, removed: 0}],
  checks: [{id: 'DK-2', name: 'node-tests', state: 'FAILED', ts: '2026-11-08T20:05:00Z', current: true, newly: {known: true, names: [], total: 0, base_failing_total: 1, lane_failing_total: 1}}],
  reviews_stale: [{review_id: 'R-1', work_id: 'WORK-0', work_title: 'An older change', reason: 'it reviewed src/app.py at another version than this adoption writes'}],
  carry: {inputs_total: 0, inputs: [], note: 'This root records no publication inputs, so the close carries none.'},
  scratch: {commit: LANE.base, bytes: 50 * 1024 * 1024, paths: ['scripts', 'src', 'tests'], removed: true}};
const OFFER = {action: 'adopt', refused: [], request: {action: 'adopt', work_id: 'WORK-1', branch: LANE.branch, preview_id: PREVIEW.id, preview_sha256: 'sha256:' + 'a'.repeat(64)}};
const ADOPTED = {...LANE, state: 'ADOPTED', removal: {worktree: 'REMOVED', branch: 'REMOVED'}, grant: {...LANE.grant, state: 'REVOKED', revoked_at: '2026-11-08T20:11:00Z'}};
const ADOPTION = {work: {id: 'WORK-1', title: 'Change the app'}, lane: ADOPTED, observed_at: '2026-11-08T20:11:05Z', in_live_history: true,
  adoption: {id: 'DA-1', state: 'COMMITTED', commit: 'a1b2c3d4e5f6a7b8', base: LANE.base, branch: LANE.branch, files: PREVIEW.files, committed_at: '2026-11-08T20:11:00Z', trailer: {'Work-Id': 'WORK-1', 'Adoption-Id': 'DA-1'}},
  reviews: [{review_id: 'R-1', work_id: 'WORK-0', work_title: 'An older change', currentness: 'STALE', reason: 'consumed source bytes changed'}]};

test('the preview and adoption reads are the owner requests; Preview is offered only beside an active lane', async () => {
  assert.deepEqual(previewRequest('garden', 'WORK-1', 'WS-1'), {project: 'garden', action: 'preview', work_id: 'WORK-1', session_id: 'WS-1'});
  assert.deepEqual(adoptionRequest('garden', 'WORK-1'), {project: 'garden', action: 'adoption', work_id: 'WORK-1'});
  const f = fixture(() => status({lane: null, checks: [], offers: []}));
  try { const view = f.mount(); await view.ready; assert.equal(byControl(f.host, 'development:adopt-preview').length, 0); assert.ok(f.host.querySelector('.development-preview').hidden); }
  finally { f.d.restore(); }
});

test('Preview draws every fact from the preview read: files with the flagged tool file, checks with newly failing, reviews, carry and scratch', async () => {
  const f = fixture(payload => payload.action === 'preview' ? {preview: PREVIEW, offers: [OFFER]} : status());
  try {
    const view = f.mount(); await view.ready;
    assert.match(f.host.textContent, /See what Adopt would change in the live tree before you press it/);
    const [button] = byControl(f.host, 'development:adopt-preview');
    assert.equal(button.textContent, 'Preview Adopt');
    await button.click(); await tick();
    assert.deepEqual(f.posts.at(-1).payload, {project: 'garden', action: 'preview', work_id: 'WORK-1', session_id: 'WS-1'});
    const text = f.host.querySelector('.development-preview').textContent;
    assert.match(text, /Read at 20:06:00 from the adoption owner · live tree at abcdef0 · lane cut from abcdef0 · took 4\.2 s/);
    assert.match(text, /Files Adopt would change \(2\):src\/app\.py · modified · \+1 −1scripts\/tool\.py · added · \+4 −0 · ⚑ tool or profile file/);
    assert.match(text, /node-tests · ✕Failed · run at 2026-11-08T20:05:00Z · it read the lane files as they are now/);
    assert.match(text, /No newly failing tests\. The same check on the live commit fails 1 test; in the lane 1\./);
    assert.match(text, /After Adopt these reviews will read “Inputs changed” \(1\):An older change · review R-1 · it reviewed src\/app\.py at another version/);
    assert.match(text, /This root records no publication inputs, so the close carries none\./);
    assert.match(text, /Scratch copy of the live commit abcdef0 \(about 50 MB, scripts, src, tests\): the lane diff applies to it; it was removed\./);
    assert.doesNotMatch(text, /STALE|COMMITTED|FAILED/, 'no raw owner constant is drawn');
    assert.equal(byControl(f.host, 'development:adopt-preview')[0].textContent, 'Preview again');
  } finally { f.d.restore(); }
});

test('Adopt asks again, then sends the offered request unchanged; afterwards the commit, the reload sentence and the reviews now reading Inputs changed', async () => {
  let adopted = false;
  const f = fixture(payload => payload.action === 'preview' ? {preview: PREVIEW, offers: [OFFER]} : payload.action === 'adopt' ? (adopted = true, {ok: true, ...ADOPTION})
    : payload.action === 'adoption' ? ADOPTION : adopted ? status({lane: ADOPTED, offers: [{action: 'lane', request: {action: 'lane', work_id: 'WORK-1', expected_work_revision: 'r', parent_session_id: 'WS-1'}}]}) : status());
  try {
    const view = f.mount(); await view.ready;
    await byControl(f.host, 'development:adopt-preview')[0].click(); await tick();
    assert.match(f.host.querySelector('.development-adopt').textContent, /Adopt applies the 2 files above to the live tree at abcdef0 and makes one local commit with Work-Id WORK-1\. The lane folder is then removed\./);
    const posted = f.posts.length;
    await byControl(f.host, 'development:adopt')[0].click(); await tick();
    assert.equal(f.posts.length, posted, 'the first press sends nothing');
    assert.equal(byControl(f.host, 'development:adopt')[0].textContent, 'Adopt now');
    assert.equal(byControl(f.host, 'development:adopt-cancel')[0].textContent, 'Not now');
    assert.match(f.host.querySelector('.development-adopt').textContent, /Press Adopt now to commit these files to the live tree\./);
    await byControl(f.host, 'development:adopt')[0].click(); await tick(); await tick();
    assert.deepEqual(f.posts[posted].payload, {project: 'garden', ...OFFER.request});
    assert.deepEqual(f.posts.slice(posted + 1).map(p => p.payload.action), ['status', 'adoption']);
    const card = f.host.querySelector('.development-adopt').textContent;
    assert.match(card, /✓Adopted as a1b2c3d\. Reload the window to run it\./);
    assert.match(card, /Committed at 2026-11-08T20:11:00Z on abcdef0 · Work-Id WORK-1 · 2 files · read at 20:06:00 from the adoption owner/);
    assert.match(card, /Reviews now reading “Inputs changed” \(1\):An older change · review R-1 · consumed source bytes changed/);
    assert.equal(byControl(f.host, 'development:adopt-preview').length, 0, 'an adopted lane offers no preview');
    assert.match(f.host.querySelector('.development-lane').textContent, /Its folder was removed/);
  } finally { f.d.restore(); }
});

test('a refused preview shows the owner sentences beside a disabled Adopt; a refused Adopt is the owner sentence beside the button', async () => {
  const refusedOffer = {action: 'adopt', request: null, refused: ['node-tests has 1 newly failing test; Adopt refuses while a check is newly failing.']};
  let refuse = true;
  const f = fixture(payload => payload.action === 'preview' ? {preview: PREVIEW, offers: [refuse ? refusedOffer : OFFER]}
    : payload.action === 'adopt' ? new Error('A close (sew up) is publishing right now and holds the publication lock: Adopt refuses rather than waits.') : status());
  try {
    const view = f.mount(); await view.ready;
    await byControl(f.host, 'development:adopt-preview')[0].click(); await tick();
    const [adopt] = byControl(f.host, 'development:adopt');
    assert.equal(adopt.disabled, true);
    assert.match(f.host.querySelector('.development-adopt').textContent, /Adopt is refused for this preview:node-tests has 1 newly failing test/);
    refuse = false;
    await byControl(f.host, 'development:adopt-preview')[0].click(); await tick();
    await byControl(f.host, 'development:adopt')[0].click(); await tick();
    await byControl(f.host, 'development:adopt')[0].click(); await tick();
    const said = f.host.querySelector('.development-adopt').querySelector('.development-said');
    assert.match(said.textContent, /holds the publication lock: Adopt refuses rather than waits/);
    assert.ok(said.className.includes('error'));
    assert.equal(byControl(f.host, 'development:adopt')[0].textContent, 'Adopt now', 'the button stays to press again');
  } finally { f.d.restore(); }
});
