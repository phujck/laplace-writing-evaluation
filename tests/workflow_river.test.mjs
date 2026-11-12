// Wave 11 (run-view): the run river under a run's drawing on the Workflows page. The model is one array that paints the
// drawing and the text list; marks are placed only where the owner gives a time; a running mark comes only from the
// owner's current observation and stops being called running when a read fails; the card follows only issued reads;
// every control the river and the opened run paint is declared (this is the focused evaluator of workflows/river-run).
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {installDOM,Node} from './helpers/evidence_reader_harness.mjs';
import {workflowRiverModel,workflowRiverWaiting,riverStepSettings,riverLegend,RIVER_MARKS,mountWorkflowRiver,clock,axisLabelFits} from '../src/laplace/web/static_shared/workspace-workflow-river.mjs';
import {ownerStateWord,OWNER_STATE_WORDS,childChip} from '../src/laplace/web/static_shared/workspace-presentation.mjs';
import {turnEventsURL,progressWords} from '../src/laplace/web/static_shared/turn-events.mjs';

const T = s => '2026-11-06T14:' + s + '.000Z', ms = s => Date.parse(T(s));
const reference = {identity: {id: 'WDEF-1'}, kind: 'workflow-definition', version: {definition_revision: 'sha256:' + 'a'.repeat(64)}};
const query = new URLSearchParams({facet: 'river', reference: JSON.stringify(reference), work_id: 'WORK-1', project_lens: 'book'});
const offer = {http: {method: 'GET', url: '/work/workflow-definitions?' + query}, request: {facet: 'river', reference, work_id: 'WORK-1', project_lens: 'book'}};
const conversation = (sid, tid) => ({project: 'book', session_id: sid, turn_id: tid, project_url: '/project?workspace=writing&corpus=book&session=' + sid + '&conversation=open', session_read: {http: {method: 'GET', url: '/authoring/session?project=book&id=' + sid + '&view=summary'}}});
const reply = (sid, tid) => ({identity: {project: 'book', session_id: sid, turn_id: tid, part: 'reply'}, http: {method: 'GET', url: '/authoring/session-turn?project=book&session_id=' + sid + '&part=reply&offset=0&limit=4000&id=' + tid + '&view=message'}});
function river({running = true, observedAt = T('02:07')} = {}) {
  return {schema_version: 'laplace.workflow-operation/1', view: 'river', read_only: true, scope_id: 'scope', reference, work_id: 'WORK-1', coverage: 'RECORDED_MATCHES_ONLY', cut: 'sha256:' + (running ? 'b' : 'c').repeat(64), offset: 0, total: 3, returned: 3,
    prepared_dependencies: {status: 'AVAILABLE', edges: [{prerequisite_step_id: 'draft', dependent_step_id: 'check'}, {prerequisite_step_id: 'compare', dependent_step_id: 'check'}]},
    current_observation: {observed_at: observedAt, items: {}, by_turn: {'WT-a': {observed: 'FINISHED'}, 'WT-b': {observed: running ? 'RUNNING' : 'FINISHED'}, 'WT-c': {observed: 'FINISHED'}}},
    items: [
      {step_id: 'draft', title: 'Write the summary', state: 'NO-RETURN', session_id: 'WS-a', turn_id: 'WT-a', current_attempt: {observed: true}, reads: {reply: reply('WS-a', 'WT-a'), conversation: conversation('WS-a', 'WT-a')},
        turn: {started_at: T('01:02'), replied_at: T('01:32'), reply_status: 'completed', provider_settings: {provider: 'claude', model: 'default', effort: 'medium'}, tool_calls: [{kind: 'read', id: 'READ-1', operation: 'project', status: null, at: T('01:10')}, {kind: 'action', id: 'ACTION-9', operation: 'proposal_submit', status: 'RECORDED', at: null}], tool_calls_total: 2}},
      {step_id: 'compare', title: 'Compare both weeks', state: running ? 'RUNNING' : 'NO-RETURN', session_id: 'WS-b', turn_id: 'WT-b', current_attempt: {observed: true}, reads: {reply: reply('WS-b', 'WT-b'), conversation: conversation('WS-b', 'WT-b')},
        turn: {started_at: T('01:05'), replied_at: running ? null : T('02:30'), reply_status: running ? null : 'completed', tool_calls: [], tool_calls_total: 0}},
      {step_id: 'check', title: 'Check the comparison', state: 'BLOCKED', session_id: 'WS-c', turn_id: 'WT-c', current_attempt: {observed: true}, reads: {conversation: conversation('WS-c', 'WT-c')},
        turn: {started_at: T('01:40'), replied_at: T('01:41'), reply_status: 'failed', reply_error: 'DEPENDENCY-INCOMPLETE: worker return is missing.', tool_calls: [], tool_calls_total: 0}}]};
}
const order = ['draft', 'compare', 'check'];

test('one model: lanes in the drawing order, marks only where the owner gives a time, arrows only from prepared dependencies', () => {
  const model = workflowRiverModel({river: river(), order});
  assert.deepEqual(model.lanes.map(l => l.step_id), order);
  const kinds = model.marks.map(m => m.kind + ':' + m.step_id);
  assert.deepEqual(kinds.filter(k => k.startsWith('turn')).sort(), ['turn:check', 'turn:compare', 'turn:draft']);
  assert.ok(kinds.includes('tool:draft') && kinds.includes('reply:draft') && kinds.includes('reply:check') && !kinds.includes('reply:compare'));
  // the compare -> check dependency has no arrow: compare has not replied; draft -> check has one, said to be a prepared dependency
  const arrows = model.marks.filter(m => m.kind === 'handover');
  assert.deepEqual(arrows.map(a => a.id), ['handover:draft>check']);
  assert.match(arrows[0].text, /prepared dependencies/); assert.match(arrows[0].text, /No hand-over receipt is recorded/);
  // the running bar ends at the owner's observation time, never at the client's clock
  const bar = model.marks.find(m => m.id === 'turn:WT-b');
  assert.equal(bar.running, true); assert.equal(bar.end, ms('02:07')); assert.match(bar.text, /observed running at /);
  assert.equal(model.live, true); assert.equal(model.end, ms('02:07')); assert.equal(model.start, ms('01:02'));
  // a tool call without a time is listed, not placed
  assert.deepEqual(model.untimed.map(m => m.id), ['tool:ACTION-9']);
  assert.equal(model.marks.every(m => typeof m.at === 'number'), true);
});

test('after a failed read nothing is called running: the running bar becomes last known', () => {
  const model = workflowRiverModel({river: river(), order, failed: true, lastGoodAt: ms('02:07')});
  const bar = model.marks.find(m => m.id === 'turn:WT-b');
  assert.equal(bar.running, false); assert.equal(bar.lastKnown, ms('02:07')); assert.match(bar.text, /last known /);
});

test('state words: one table, plain words and a shape, the exact constant kept, unknown values never guessed', () => {
  for (const [field, table] of Object.entries(OWNER_STATE_WORDS)) for (const [value, [words, shape]] of Object.entries(table)) {
    assert.equal(ownerStateWord(field, value).exact, value); assert.ok(shape && words && !/[A-Z]{3,}|_/.test(words), field + ' ' + value + ' -> ' + words);
  }
  assert.equal(ownerStateWord('dispatch-child', 'NO-RETURN').words, 'Replied without a typed return');
  assert.equal(ownerStateWord('dispatch-child', 'NOT_STARTED').words, 'Not started');
  assert.match(ownerStateWord('dispatch-child', 'SOMETHING_NEW').words, /^something new \(no plain words/);
  assert.equal(childChip({state: 'NOT_STARTED'}).label, 'Not started'); assert.equal(childChip({state: 'FAILED'}).tone, 'blocked');
});

test('provider and model say which: admitted, then recorded on the turn, then prepared', () => {
  assert.deepEqual(riverStepSettings({settings: {admitted: {provider: 'codex', model: 'm1'}, prepared: {provider: 'claude', model: 'm0'}}}), {provider: 'codex', model: 'm1', effort: null, source: 'admitted'});
  assert.equal(riverStepSettings({turn: {provider_settings: {provider: 'claude', model: 'default'}}}).source, 'admitted, recorded on its turn');
  assert.deepEqual(riverStepSettings(null, {provider: 'claude', model: 'default', effort: 'medium'}), {provider: 'claude', model: 'default', effort: 'medium', source: 'prepared'});
  assert.equal(riverStepSettings(null, null), null);
});

test('what waits for him is counted only from an owner field', () => {
  assert.deepEqual(workflowRiverWaiting({steps: [{step_id: 'a', continue_action: {permitted: false}}, {step_id: 'b'}]}), []);
  const rows = workflowRiverWaiting({steps: [{step_id: 'check', continue_action: {permitted: true, available: true, label: 'Prepare review continuation message'}}]});
  assert.deepEqual(rows.map(r => [r.step_id, r.field]), [['check', 'continue_action.permitted']]);
});

test('the legend line is generated from the painter table', () => {
  assert.equal(RIVER_MARKS.map(m => m.name).join(','), 'Bar,Square,Circle,Arrow');
  for (const mark of RIVER_MARKS) assert.ok(riverLegend().includes(mark.shape + ' ' + mark.name + ': ' + mark.says));
});

test('the turn stream URL is the owner’s and names the exact turn', () => {
  globalThis.location = {href: 'http://local/project'};
  try { assert.equal(turnEventsURL('/authoring/events?turn=WT-b', 'WT-b').pathname, '/authoring/events'); assert.throws(() => turnEventsURL('/authoring/events?turn=WT-x', 'WT-b'), /does not match this turn/); assert.throws(() => turnEventsURL('http://elsewhere/authoring/events?turn=WT-b', 'WT-b'), /does not match/); }
  finally { delete globalThis.location; }
});

function domWithSvg() {
  const dom = installDOM();
  document.createElementNS = (_ns, tag) => new Node(tag);
  document.addEventListener = () => {}; document.removeEventListener = () => {};
  Node.prototype.addEventListener ||= function (type, fn) { (this.listeners ||= {})[type] = fn; };
  return dom;
}
const CONTROLS = JSON.parse(readFileSync(new URL('./fixtures/help/controls.json', import.meta.url), 'utf8'));
const declared = new Map(CONTROLS.controls.map(row => [row.id, row]));
const controlsIn = host => host.all().filter(n => n.dataset?.control || n.attrs?.['data-control']).map(n => ({id: n.dataset?.control || n.attrs['data-control'], owner: n.dataset?.controlOwner || n.attrs?.['data-control-owner'] || null}));

test('mounted river: lanes, marks, live byline, one card following only issued reads, Identity, failure, Follow', async () => {
  const dom = domWithSvg(), calls = [];
  let value = river(), fail = false;
  const request = async url => { calls.push(url); if (url.startsWith('/work/workflow-definitions')) { if (fail) throw Error('Workflow owner refused (503).'); return structuredClone(value); }
    if (url.includes('view=message')) return {state: 'AVAILABLE', content: 'Stand-in reply for the summary.', next_read: null};
    if (url.includes('view=summary')) return {active: null}; throw Error('unexpected read ' + url); };
  const host = new Node('main'); document.body.append(host);
  const ui = mountWorkflowRiver(host, {offer, run: {steps: []}, order, titles: {draft: 'Write the summary', compare: 'Compare both weeks', check: 'Check the comparison'}, request, interval: 1e9, openConversation: () => {}});
  try {
    await new Promise(r => setTimeout(r, 0)); await new Promise(r => setTimeout(r, 0));
    assert.equal(calls[0], offer.http.url, 'the river is read through the issued offer, unchanged');
    assert.equal(ui.byline.textContent, 'Read ' + clock(ms('02:07')) + ' · every 1000000 s · observed flow (workflow owner, river read)');
    const lanes = host.querySelectorAll('[data-control="workflow:river-step"]');
    assert.deepEqual(lanes.map(b => b.textContent), ['Write the summary', 'Compare both weeks', 'Check the comparison']);
    const marks = host.all().filter(n => n.attrs?.['data-control'] === 'workflow:river-mark');
    assert.ok(marks.length >= 6 && marks.every(n => n.attrs['data-control-owner'] && n.attrs['aria-label']));
    // every rendered control is declared for the opened run
    for (const row of controlsIn(host)) { assert.ok(declared.has(row.id), 'undeclared ' + row.id); assert.ok(declared.get(row.id).states.includes('river-run'), row.id + ' not declared for river-run'); }
    // open the reply mark: one card, a sentence from the owner's facts, its issued reads as buttons, nothing fetched yet
    const before = calls.length; ui.select('reply:WT-a');
    assert.equal(calls.length, before, 'opening a card reads nothing');
    const card = host.querySelector('.workflow-river-card');
    assert.match(card.textContent, /^Write the summary replied · /);
    const open = card.all().find(n => n.tag === 'button' && n.textContent === 'Open reply');
    assert.equal(open.dataset.control, 'workflow:river-read');
    await open.onclick(); await new Promise(r => setTimeout(r, 0));
    assert.equal(calls.at(-1), reply('WS-a', 'WT-a').http.url, 'Open reply follows exactly the issued reply read');
    assert.match(host.querySelector('.workflow-river-card').textContent, /Stand-in reply for the summary\./);
    const identity = host.querySelector('.workflow-river-card').all().find(n => n.tag === 'button' && n.textContent === 'Identity');
    await identity.onclick();
    assert.match(host.querySelector('.workflow-river-card').textContent, /Recorded stateNO-RETURN/);
    // the check step's card prints the owner's sentence for its failed reply
    ui.select('step:check'); assert.match(host.querySelector('.workflow-river-card').textContent, /The owner recorded: DEPENDENCY-INCOMPLETE: worker return is missing\./);
    assert.match(host.querySelector('.workflow-river-card').textContent, /Check the comparison · Blocked/);
    // a card opened pauses following; a later read that adds marks shows "N new" and Follow returns to now
    assert.equal(ui.following, false);
    value = river({running: false, observedAt: T('02:31')}); await ui.load();
    assert.equal(ui.newCount, 1, 'the compare reply is the one new mark');
    const follow = host.querySelector('[data-control="workflow:river-follow"]'); assert.equal(follow.hidden, false); assert.equal(follow.textContent, '1 new · Follow');
    await follow.onclick(); assert.equal(ui.following, true); assert.equal(follow.hidden, true);
    // nothing runs now: no interval in the byline
    assert.equal(ui.byline.textContent, 'Read ' + clock(ms('02:31')) + ' · observed flow (workflow owner, river read)');
    // a failed read while live: the byline says so and the running mark says last known
    value = river(); await ui.load(); fail = true; await ui.load();
    assert.match(ui.byline.textContent, /^Read failed at \d\d:\d\d:\d\d: Workflow owner refused \(503\)\. · last good read /);
    assert.equal(ui.byline.dataset.failed, 'true');
    const bar = host.all().find(n => n.attrs?.['data-control-owner'] === 'turn:WT-b');
    assert.match(bar.attrs['aria-label'], /last known/); assert.ok(!bar.attrs.class.includes('running'));
    assert.equal(ui.model.marks.some(m => m.running), false);
  } finally { ui.destroy(); dom.restore(); }
});

test('the opened run view declares every control it paints, and paints no raw owner state', () => {
  const editor = readFileSync(new URL('../src/laplace/web/static_shared/workspace-workflow-editor.mjs', import.meta.url), 'utf8');
  const riverSource = readFileSync(new URL('../src/laplace/web/static_shared/workspace-workflow-river.mjs', import.meta.url), 'utf8');
  const ids = new Set([...editor.matchAll(/control='(workflow:(?:run|runs|river)-[a-z-]+)'/g), ...editor.matchAll(/'(workflow:run-[a-z-]+)'/g), ...riverSource.matchAll(/'(workflow:river-[a-z-]+)'/g)].map(m => m[1]));
  assert.ok(ids.size >= 25, [...ids].join(' '));
  for (const id of ids) { assert.ok(declared.has(id), 'undeclared ' + id); assert.ok(declared.get(id).states.includes(id === 'workflow:runs-open' ? 'runs' : 'river-run'), id); assert.ok(declared.get(id).does || id === 'workflow:river-read', id + ' has no guide sentence'); }
  assert.ok(!editor.includes("'Admitted · '+(m.state||'state not stated')"), 'the raw owner state no longer follows "Admitted ·"');
  assert.ok(editor.includes("'Admitted · '+state.words"));
  assert.ok(!/'Execution: '\+\(facts\.execution_state/.test(editor));
  assert.ok(!editor.includes("'Open agent run · '+item.recorded_status"), 'the run list words the Work status');
});

// Wave 11b (the judge's D2 to D5): one card per step holding the recorded step; a reply's mark follows its recorded
// status; an axis label is shown only whole; one progress-wording function; the phase and effect words from the table.
test('a step has one card: the caller paints its recorded step into the river card, and a lane label asks for its read', async () => {
  const dom = domWithSvg(), asked = [];
  const request = async url => { if (url.startsWith('/work/workflow-definitions')) return structuredClone(river()); if (url.includes('view=summary')) return {active: null}; throw Error('unexpected read ' + url); };
  const host = new Node('main'); document.body.append(host);
  const stepDetail = (id, place) => { const b = new Node('button'); b.textContent = 'Read full public result and actions'; b.dataset.control = 'workflow:run-step-result'; b.dataset.controlOwner = id;
    const c = new Node('button'); c.textContent = 'Open step conversation'; c.dataset.control = 'workflow:run-step-conversation'; c.dataset.controlOwner = id; place.append(b, c); return {conversation: true}; };
  const ui = mountWorkflowRiver(host, {offer, run: {steps: []}, order, request, interval: 1e9, openConversation: () => {}, stepDetail, onSelectStep: id => asked.push(id)});
  try {
    await new Promise(r => setTimeout(r, 0)); await new Promise(r => setTimeout(r, 0));
    const lane = host.querySelectorAll('[data-control="workflow:river-step"]').find(b => b.dataset.controlOwner === 'check'); await lane.onclick();
    assert.deepEqual(asked, ['check'], 'a lane label asks the caller to read that step');
    const cards = host.querySelectorAll('.workflow-river-card').filter(c => !c.hidden); assert.equal(cards.length, 1);
    const ids = controlsIn(cards[0]).map(r => r.id);
    assert.ok(ids.includes('workflow:run-step-result') && ids.includes('workflow:run-step-conversation'), ids.join(' '));
    assert.ok(!ids.includes('workflow:river-conversation'), 'the step card has one conversation control, the recorded step’s own');
    ui.select('step:draft', {quiet: true}); assert.deepEqual(asked, ['check'], 'a stage click (quiet) does not ask twice');
    // the reply marks: a failed reply is a cross in a ring, a completed one a filled circle
    const shape = id => host.all().find(n => n.attrs?.['data-control-owner'] === id)?.attrs['data-reply-shape'];
    assert.equal(shape('reply:WT-a'), '●'); assert.equal(shape('reply:WT-c'), '✕');
    assert.match(host.all().find(n => n.attrs?.['data-control-owner'] === 'reply:WT-c').attrs.class, /tone-blocked/);
  } finally { ui.destroy(); dom.restore(); }
});

test('the legend names every reply mark; an axis label is shown only when all of it is visible', () => {
  for (const [words, shape] of Object.values(OWNER_STATE_WORDS.reply)) assert.ok(riverLegend().includes(shape + ' '), shape + ' ' + words);
  assert.match(riverLegend(), /✕ failed/); assert.match(riverLegend(), /● replied/);
  assert.equal(axisLabelFits(100, 64, 0, 400), true);
  assert.equal(axisLabelFits(-20, 64, 0, 400), false, 'cut at the left edge');
  assert.equal(axisLabelFits(380, 64, 0, 400), false, 'cut at the right edge');
  assert.equal(axisLabelFits(500, 64, 480, 900), true); assert.equal(axisLabelFits(470, 64, 480, 900), false);
});

test('one progress-wording function and the attempt-phase and continuation-effect words come from the one table', () => {
  assert.equal(progressWords('agentMessage'), 'agent Message'); assert.equal(progressWords('command_execution'), 'command execution');
  const read = name => readFileSync(new URL('../src/laplace/web/static_shared/' + name, import.meta.url), 'utf8');
  for (const name of ['workspace-workflow-river.mjs', 'workspace-sessions.mjs']) { assert.ok(read(name).includes('progressWords('), name); assert.ok(!read(name).includes('replace(/([a-z])([A-Z])/g'), name + ' keeps a second copy'); }
  const editor = read('workspace-workflow-editor.mjs');
  assert.ok(!/attempt\.phase\|\|'phase not stated'\)\.toLowerCase/.test(editor) && editor.includes("ownerStateWord('attempt-phase',attempt.phase)"));
  assert.ok(!/receipt\.effect\|\|'not stated'\)\.toLowerCase/.test(editor) && editor.includes("ownerStateWord('continuation-effect',receipt.effect)"));
  assert.ok(read('workspace-workflow-operation.mjs').includes("ownerStateWord('dispatch-child',raw)"));
  assert.equal(ownerStateWord('attempt-phase', 'RESERVED').words, 'reserved, not launched'); assert.equal(ownerStateWord('continuation-effect', 'UNKNOWN').words, 'unknown');
  assert.equal(childChip({state: 'BLOCKED'}).tone, ownerStateWord('dispatch-child', 'BLOCKED').tone);
  assert.ok(!read('workspace-presentation.mjs').includes('/COMPLETE|DONE/i'), 'childChip keeps no regex tone');
});
