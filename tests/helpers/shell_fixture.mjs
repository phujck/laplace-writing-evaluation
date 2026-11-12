// The whole writing workspace mounted for source render coverage (repair2 R4, 2026-10-14): the real
// mountWorkspace over the markup-parsing DOM double (html_dom.mjs), with every owner read answered by a
// synthetic fixture shaped like the owner's own contract (shapes taken from the existing owner tests:
// workspace_project_home, workspace_shared_material, workspace_history, visual_readiness, research
// reading and the reader-plan display fixture). Nothing is copied from a real project. `routes`
// overrides one owner answer per state; every request is recorded in `calls`.
import {register} from 'node:module';
import {readFileSync} from 'node:fs';
register(new URL('./shared_resolve.mjs', import.meta.url));
const {installHTMLDocument} = await import('./html_dom.mjs');
const AREAS = JSON.parse(readFileSync(new URL('../fixtures/help/areas.json', import.meta.url), 'utf8'));
const CONTROLS_READ = JSON.parse(readFileSync(new URL('../fixtures/help/controls.json', import.meta.url), 'utf8'));
const DISPLAY = JSON.parse(readFileSync(new URL('../fixtures/editor_spine/display-owner.json', import.meta.url), 'utf8'));
// the real HTTP owners' answers on a synthetic project (tests/fixtures/shell/generate_owner_answers.py)
const OWNERS = JSON.parse(readFileSync(new URL('../fixtures/shell/owner-answers.json', import.meta.url), 'utf8'));
const clone = value => structuredClone(value);
export const METADATA = {project: 'book', title: 'Fixture Book', purpose: 'A test purpose.',
  capabilities: {manuscript: true, research: true, review: true, presentation: true, materials: true, material_references: true, concepts: true, reader_plan: true}};
const TASKS = [{id: 'WORK-a', title: 'Approach A', status: 'blocked', lifecycle: {closed: false}}, {id: 'WORK-b', title: 'Approach B', status: 'ready', lifecycle: {closed: false}, parent_work_id: 'WORK-a'}];
const REF = {id: 'MAT-one', target: {owner: 'artifact', project: 'producer', path: 'notes.txt', scope: 'project'}, consumed_revision: 'consumed-one', current_revision: 'current-two', currentness: 'CHANGED_INPUT'};
const HISTORY_ITEM = i => ({id: 'action:' + i, owner: 'journal', category: 'manuscript', at: '2026-09-30T12:0' + i + ':00Z', actor: {kind: 'agent', label: 'Eigen'}, summary: 'Changed section ' + i, status: 'Applied', targets: [{kind: 'manuscript', label: 'Chapter ' + i, file: 'chapters/ch' + i + '.tex'}], detail_available: true});
const STAGE = {stage: 'voice_integration', title: 'Integrate the author’s voice', purpose: 'Apply the selected voice throughout the argument.'};
const RESULT = {id: 'result-1', title: 'Audit', question: 'One question', summary: 'One finding', usage: [], evidence_files: [], producer: null};
// a route may answer with an owner HTTP status: ownerReply(503, {error}) is a non-2xx JSON reply, not a thrown fetch
const OWNER_STATUS = Symbol('owner status');
export const ownerReply = (status, body) => ({[OWNER_STATUS]: status, body});
export function defaultRoutes() {
  return {
    '/authoring/providers': () => ({providers: [{id: 'codex', name: 'Codex', available: true, models: [{id: 'luna', name: 'Luna', efforts: ['low', 'medium', 'high']}]}]}),
    '/work/session-preferences': () => ({preferences: {provider: 'codex', model: 'luna', effort: 'high'}}),
    '/authoring/state': () => ({project: 'book', sessions: [], session_count: 0}),
    '/work/state': q => q.get('view') === 'detail' ? {project: 'book', view: 'detail', task: {...TASKS.find(t => t.id === q.get('id')) || TASKS[0], goal: 'Authored criterion'}, blockers: [], children: {items: []}, dependants: {items: []}, read_cut: {revision: 'cut'}}
      : q.get('view') === 'queue' ? {project: 'book', view: 'queue', items: []}
      : {project: 'book', view: 'summary', tasks: clone(TASKS), counts: {pending: 2}, framing: {framing: {purpose: 'A test purpose.'}}},
    '/projects/metadata': () => clone(METADATA),
    '/projects/library': () => ({projects: [{name: 'book', title: 'Fixture Book'}]}),
    '/authoring/help': q => ({project: 'book', help: q.get('view') === 'areas' ? clone(AREAS) : q.get('view') === 'controls' ? clone(CONTROLS_READ) : {}}),
    '/authoring/health': () => ({pid: 42, active_work: []}),
    '/work/writing-style': () => ({profile_title: 'Author voice', profile_version: 'v1.2', profile_origin: 'project', profile: 'profiles/voice/author.md', profile_revision: 'voice-r1', genre: 'book', guidance: 'Keep examples concrete.'}),
    '/work/writing-stage': q => q.has('stage') ? clone(STAGE) : {stages: [{id: STAGE.stage, title: STAGE.title, purpose: STAGE.purpose}]},
    '/projects/material-references': () => ({references: [], revision: 'list-registry', total: 0, next_offset: null, owners: {repositories: []}}),
    '/work/materials': () => ({materials: [{id: 'm1', path: 'notes/present.md', scope: 'project', availability: 'present', recorded_revision: 'sha256:' + '1'.repeat(64)}], pagination: {next_offset: null, total: 1}, coverage: 'One recorded file.'}),
    '/authoring/history': q => q.get('view') === 'telemetry' ? {as_of: '2026-09-30T13:00:00Z', totals: {activity: 3, dated: 3, unrecorded_date: 0}, series: {activity: []}, identity_coverage: []}
      : {as_of: '2026-09-30T13:00:00Z', items: [0, 1, 2].map(HISTORY_ITEM), pagination: {total: 3, next_offset: null}, coverage: []},
    '/research/state': () => ({results: [clone(RESULT)], producers: []}),
    '/visuals/state': () => ({specs: []}), '/formal/state': () => ({receipts: []}), '/formal/targets': () => ({targets: []}),
    '/concepts/tree': () => ({project: 'book', items: [], total: 0}),
    '/authoring/proposals': () => ({project: 'book', view: 'queue', proposals: [], as_of: 'queue-cut', total: 0}),
    '/authoring/document': q => clone(q.get('target_kind') === 'derived' ? OWNERS.document_derived : OWNERS.document),
    '/authoring/build': () => ({running: false, present: false}),
    '/work/style/preview': () => ({status: 'UNCONFIGURED'}),
    '/walk/doc': () => ({title: 'Fixture', sections: []}),
    '/work/structure': q => q.get('view') === 'summary' ? clone(DISPLAY.summary) : q.get('projection') === 'display' ? clone(DISPLAY.display) : q.get('projection') === 'guard' && q.get('subject') === 'contract' ? clone(DISPLAY.contract_values) : q.get('view') === 'outline' ? clone(OWNERS.outline) : {},
  };
}
export async function mountShell({query = '', routes = {}, width = 1280, before = null} = {}) {
  const env = installHTMLDocument({width});
  before?.(env);   // a page-side precondition (e.g. the served page's head, this tab's sessionStorage) before the shell mounts
  // the shell's pollers and settle timers are tracked and cleared on restore, so a test run ends
  const timers = new Set(), realTimeout = globalThis.setTimeout, realInterval = globalThis.setInterval, realClear = globalThis.clearTimeout, realClearInterval = globalThis.clearInterval;
  globalThis.setTimeout = (fn, ms, ...args) => {const id = realTimeout(() => {timers.delete(id); fn(...args);}, ms); timers.add(id); return id;};
  globalThis.setInterval = (fn, ms, ...args) => {const id = realInterval(fn, ms, ...args); timers.add(id); return id;};
  globalThis.clearTimeout = id => {timers.delete(id); realClear(id);};
  globalThis.clearInterval = id => {timers.delete(id); realClearInterval(id);};
  env.location.href = 'http://local/project?workspace=writing&corpus=book' + (query ? '&' + query : '');
  const table = {...defaultRoutes(), ...routes}, calls = [];
  globalThis.fetch = async (path, init = {}) => {
    calls.push((init.method || 'GET') + ' ' + path);
    const url = new URL(path, 'http://local'), route = table[url.pathname];
    const answer = route ? route(url.searchParams, init) : {}, status = answer?.[OWNER_STATUS] ?? 200, body = answer?.[OWNER_STATUS] ? answer.body : answer;
    return {ok: status < 300, status, headers: {get: () => 'application/json'}, json: async () => clone(body ?? null), text: async () => JSON.stringify(body)};
  };
  const {mountWorkspace} = await import('../../src/laplace/web/static_shared/workspace.mjs');
  const root = document.createElement('main'); document.body.append(root);
  const workspace = await mountWorkspace(root, 'book');
  const settle = () => new Promise(resolve => realTimeout(resolve, 15));
  await settle();
  return {env, root, workspace, calls, settle, notice: () => root.querySelector('[data-notice]')?.textContent || '',
    restore() {try {workspace?.destroy?.();} catch {} for (const id of timers) {realClear(id); realClearInterval(id);} timers.clear();
      Object.assign(globalThis, {setTimeout: realTimeout, setInterval: realInterval, clearTimeout: realClear, clearInterval: realClearInterval}); env.restore(); delete globalThis.fetch;}};
}
