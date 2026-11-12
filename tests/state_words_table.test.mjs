// Wave 12 (state-words), R6 and R14: every state word on Sessions, Now, prepared work and App settings comes from the one table
// (workspace-presentation.mjs OWNER_STATE_WORDS). The copies are gone, every kind the four modules ask for exists, and the
// provider auth constants the owner can return all have plain words.
import {register} from 'node:module'; register(new URL('./helpers/shared_resolve.mjs', import.meta.url));
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync, readdirSync} from 'node:fs';
const {OWNER_STATE_WORDS, ownerStateWord} = await import('../src/laplace/web/static_shared/workspace-presentation.mjs');
const {stateText} = await import('../src/laplace/web/static_shared/workspace-sessions.mjs');
const {activeWorkRow} = await import('../src/laplace/web/static_shared/workspace-now.mjs');
const {dispatchChildRows} = await import('../src/laplace/web/static_shared/prepared-work.mjs');

const dir = '../src/laplace/web/static_shared/', py = '../src/laplace/writing/';
const read = path => readFileSync(new URL(path, import.meta.url), 'utf8');
const MODULES = ['workspace-sessions.mjs', 'workspace-now.mjs', 'prepared-work.mjs', 'workspace-app.mjs'];
const source = Object.fromEntries(MODULES.map(name => [name, read(dir + name)]));

test('the removed copies are gone from the four edited modules', () => {
  assert.doesNotMatch(source['workspace-now.mjs'], /\bSTATE_WORDS\b/, 'Now has no table of its own');
  assert.doesNotMatch(source['workspace-sessions.mjs'], /const words\s*=|function words\s*\(/, 'Sessions has no words() of its own');
  assert.doesNotMatch(source['workspace-sessions.mjs'], /\bconst MARK\b/, 'Sessions has no mark table of its own');
  assert.doesNotMatch(source['prepared-work.mjs'], /chip\.label\s*=\s*String\(child\.state/, 'prepared work no longer overwrites the chip with the raw state');
  // an object literal keyed by an owner constant (or a state word) is a second table
  const owned = Object.values(OWNER_STATE_WORDS).flatMap(table => Object.keys(table)).filter(key => /^[A-Z][A-Z_-]+$/.test(key) || /^(running|starting|waiting|completed|failed|interrupted|no-reply|no-turn|turn|turn-start|http-mutation)$/.test(key));
  for (const [name, text] of Object.entries(source)) for (const key of new Set(owned)) {
    const literal = new RegExp('[{,]\\s*[\'"]?' + key.replace(/[-_]/g, '[-_]') + '[\'"]?\\s*:\\s*[\'"\\[]');
    assert.doesNotMatch(text, literal, name + ' keeps an object literal keyed by the owner constant ' + key);
  }
});

// S4: no module in static_shared other than workspace-presentation.mjs defines a table keyed by owner state constants. Four
// modules outside this packet's files still do; they are named here and under Not done in the report, each a later-wave change.
// The list is exact: a new copy fails the test, and removing one of these forces the list to shrink.
const LATER_WAVE_COPIES = ['derived-output.mjs', 'manuscript-document-view.mjs', 'publication-editions.mjs', 'research-workbench-run.mjs'];
const STATE_KEY = /(?:^|[{,]\s*)['"]?(PREPARED|RUNNING|STOP_BEFORE_NEXT|NOT_STARTED|NOT_BUILT|READY|STALE|FAILED|COMPLETED|BLOCKED|PENDING|CANCELLED|INTERRUPTED|NO-RETURN|UNVERIFIED|AUTHENTICATED_UNTESTED|running|starting|waiting|completed|failed|interrupted)['"]?\s*:\s*['"\[]/g;
test('every module in static_shared is scanned: only the table and the four named later-wave copies key an object by owner states', () => {
  const holders = [];
  for (const name of readdirSync(new URL(dir, import.meta.url)).filter(file => file.endsWith('.mjs')).sort()) {
    const keys = new Set([...read(dir + name).matchAll(STATE_KEY)].map(match => match[1]));
    if (keys.size >= 3) holders.push(name);
  }
  assert.ok(holders.includes('workspace-presentation.mjs'), 'the scan finds the table itself');
  assert.deepEqual(holders.filter(name => name !== 'workspace-presentation.mjs'), LATER_WAVE_COPIES, 'a second state-word table outside the named later-wave copies');
  for (const name of MODULES) assert.ok(!holders.includes(name), name + ' keeps no table of its own');
});

test('every kind the four modules ask the table for exists in it', () => {
  for (const [name, text] of Object.entries(source)) {
    const kinds = [...text.matchAll(/ownerStateWord\(\s*'([^']+)'/g)].map(match => match[1]);
    assert.ok(name === 'workspace-now.mjs' || kinds.length, name + ' asks the table for its words');
    for (const kind of kinds) assert.ok(OWNER_STATE_WORDS[kind], name + ' asks for the kind ' + kind + ', which the table does not own');
  }
});

test('the table owns every provider auth_state constant the owners can return, with plain words and the exact constant kept', () => {
  const found = new Set();
  for (const file of ['provider.py', 'provider_catalogue.py']) {
    const text = read(py + file);
    for (const match of text.matchAll(/(?:auth_state['"\]]*\s*[:=]\s*|claude_auth\s*=\s*)['"]([A-Z_]+)['"]/g)) found.add(match[1]);
    for (const match of text.matchAll(/claude_auth\s*=\s*'([A-Z_]+)'\s*if\s+\w+\s+else\s*'([A-Z_]+)'/g)) { found.add(match[1]); found.add(match[2]); }
  }
  assert.deepEqual([...found].sort(), ['AUTHENTICATED_UNTESTED', 'READY', 'UNAUTHENTICATED', 'UNAUTHENTICATED_OR_UNVERIFIED', 'UNVERIFIED']);
  for (const constant of found) {
    const word = ownerStateWord('provider-auth', constant);
    assert.equal(word.known, true, constant + ' has words');
    assert.equal(word.exact, constant);
    assert.ok(!word.words.includes('_') && word.words !== word.words.toUpperCase(), constant + ' is shown in plain words');
  }
  assert.equal(ownerStateWord('provider-auth', 'AUTHENTICATED_UNTESTED').words, 'Signed in, not yet tested');
  assert.equal(ownerStateWord('provider-auth', 'UNVERIFIED').words, 'Not checked yet');
  assert.match(source['workspace-app.mjs'], /ownerStateWord\('provider-auth'/);
  assert.doesNotMatch(source['workspace-app.mjs'], /Authentication: '\s*\+\s*\(row\.auth_state\|\|/, 'App settings no longer prints the raw constant');
});

test('the session states the owner can return all have words and a shape; the page sentence is built around the table word', () => {
  const owner = read('../src/laplace/web/authoring_http.py');
  const states = new Set(['running', 'starting', 'no-turn', 'no-reply', 'waiting', ...['completed', 'failed', 'interrupted']]);
  for (const state of ['running', 'starting', 'no-turn', 'no-reply']) assert.match(owner, new RegExp('state = "' + state + '"|"' + state + '"'), state + ' is an owner state');
  for (const state of states) { const word = ownerStateWord('session', state); assert.equal(word.known, true, state); assert.ok(word.shape.length, state + ' has a shape'); }
  const now = new Date('2026-11-06T10:46:00');
  assert.equal(stateText({state: 'starting'}, now), 'Starting a turn');
  assert.equal(stateText({state: 'waiting', last_turn: {}}, now), 'Waiting for you: proposed changes have no decision');
  assert.equal(stateText({state: 'no-turn', created_at: '2026-11-06T09:00:00'}, now), 'No turns yet · opened 09:00');
  assert.match(stateText({state: 'something-new', last_turn: {at: '2026-11-06T09:00:00'}}, now), /^something new \(no plain words for this owner state\) · 09:00$/, 'an unknown state is said to be unknown, never guessed');
});

test('Now words come from the table: a research run states its own state, every other row its kind', () => {
  assert.equal(activeWorkRow({kind: 'turn'}).state, 'Running');
  assert.equal(activeWorkRow({kind: 'http-mutation'}).state, 'Saving');
  assert.equal(activeWorkRow({kind: 'research-run', state: 'RUNNING'}).state, 'Running');
  assert.equal(activeWorkRow({kind: 'research-run', state: 'CLEANUP_UNRESOLVED'}).state, 'Clean-up unresolved');
  assert.equal(activeWorkRow({kind: 'research-run', state: 'CLEANUP_UNRESOLVED'}).exact, 'CLEANUP_UNRESOLVED');
  assert.equal(activeWorkRow({kind: 'turn'}).exactName + activeWorkRow({kind: 'turn'}).exact, 'Owner work kind: turn', 'a turn row names the owner field its constant is');
  assert.equal(activeWorkRow({kind: 'research-run', state: 'RUNNING'}).exactName, 'Owner state: ');
  assert.match(activeWorkRow({kind: 'something-new'}).state, /no plain words for this owner state/);
});

test('a prepared dispatch child chip is the table word and shape, with the exact constant as its title', () => {
  const child = {packet: 'W1', role: 'worker', state: 'NOT_STARTED', failure_count: 0};
  const [row] = dispatchChildRows([child], {project: 'book'});
  assert.equal(row.chip.label, '○ Not started');
  assert.equal(row.chip.title, 'Owner state: NOT_STARTED');
  assert.doesNotMatch(row.chip.label, /NOT_STARTED/);
  const [failed] = dispatchChildRows([{...child, state: 'NO-RETURN', reply_status: 'completed', return_exists: false}], {project: 'book'});
  assert.equal(failed.chip.label, '◐ Replied without a typed return');
  assert.ok(failed.facts.includes('Provider reply: replied · typed return: missing'));
});
