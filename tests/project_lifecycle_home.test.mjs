// The human door of the project authoring lifecycle on Home (M5 bootstrap, writing.project_lifecycle): a selected
// manuscript without a reader-plan owner offers "Start reader plan", which posts exactly the lifecycle owner's own
// next action (its guard included) to POST /work/structure/change. The real renderOverview is sliced from the shell
// source and run over the same small DOM double the project-home tests use; only the HTTP request is captured.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {workCountSummary} from '../src/laplace/web/static_shared/workspace-work.mjs';
import {declareControl} from '../src/laplace/web/static_shared/workspace-presentation.mjs';
import {mountProjectTitle} from '../src/laplace/web/static_shared/workspace-project.mjs';

class Node {
  constructor(tag = 'div') {
    this.tag = tag; this.children = []; this.attrs = {}; this.dataset = {}; this.className = ''; this._text = ''; this.value = '';
    this.hidden = false; this.isConnected = true; this.classList = {add: value => {this.className += ' ' + value;}};
  }
  set textContent(value) {this._text = String(value || ''); this.children = [];}
  get textContent() {return this._text + this.children.map(node => node.textContent).join('');}
  append(...nodes) {for (const node of nodes) {node.parentElement = this; this.children.push(node);}}
  replaceChildren(...nodes) {this.children = []; this.append(...nodes);}
  setAttribute(name, value) {this.attrs[name] = String(value);}
  all() {return [this, ...this.children.flatMap(node => node.all ? node.all() : [])];}
  querySelector() {return null;}
  querySelectorAll() {return [];}
}

let renders = 0;
async function renderHome(info) {
  const source = (await import('./helpers/workspace_source.mjs')).workspaceSource();
  const {SERVICE_PRELUDE} = await import('./helpers/shell_services.mjs');
  const implementation = source.slice(source.indexOf('  async function renderOverview(host){'), source.indexOf('  async function mountWritingStyle('));
  const calls = [], reloads = [];
  const E = (tag, text = '', cls = '') => {const node = new Node(tag); node.textContent = text; node.className = cls; return node;};
  const section = (parent, label) => {const node = E('section'); node.append(E('h3', label)); parent.append(node); return node;};
  globalThis.document = {createElement: tag => new Node(tag)};
  globalThis.window = {addEventListener() {}, removeEventListener() {}};
  globalThis.location = {reload: () => reloads.push(1)};
  globalThis.__lifecycleHome = {declareControl, workCountSummary, mountStorage: () => {}, mountProjectTitle, project: 'dd', E, section,
    state: {framing: {revision: 'r', framing: {purpose: 'Assess the company.', audience: 'Board'}}, form: 'paper', tasks: []}, info,
    button: (label, fn) => {const b = E('button', label); b.onclick = fn; return b;}, field: () => new Node('input'), area: () => new Node('textarea'),
    wireForm: () => {}, api: async (path, payload) => {calls.push({path, payload}); return {status: 'PLAN_OWNED'};}, changed: async () => {},
    renderSavedMarkdown: async () => {}, mountWritingStyle: async () => {}, session: {scope() {}, find: () => new Node('textarea')},
    openSession: () => {}, show: async () => {}, root: new Node(), mountProjectSettings: async () => ({destroy() {}})};
  const names = ['declareControl', 'workCountSummary', 'state', 'info', 'project', 'E', 'section', 'button', 'field', 'area', 'wireForm', 'api', 'changed',
    'renderSavedMarkdown', 'mountWritingStyle', 'session', 'openSession', 'show', 'root', 'mountProjectSettings', 'mountProjectTitle', 'mountStorage'];
  const dependencies = 'const {' + names.join(',') + '}=globalThis.__lifecycleHome;const acceptProjectMetadata=()=>{};'
    + 'let projectOverviewRefresh=null,projectHomeController=null,projectTitleController=null,writingStyleController=null,dirty=false,'
    + 'task=null,requestedWork=null;const pageDiagnostics=false,pageCounters=()=>null;';
  // a unique module per render: ES modules are cached by URL, and each render binds its own fixture at load
  const unique = '\n// render ' + (++renders);
  const module = dependencies + SERVICE_PRELUDE + 'const manuscript={editor:()=>null};' + implementation + '\nexport {renderOverview};' + unique;
  const {renderOverview} = await import('data:text/javascript;base64,' + Buffer.from(module).toString('base64'));
  const host = new Node();
  await renderOverview(host);
  delete globalThis.__lifecycleHome;
  return {host, calls, reloads, button: label => host.all().find(node => node.tag === 'button' && node.textContent === label)};
}

const lifecycle = {state: 'MANUSCRIPT_WITHOUT_PLAN', revision: 'sha256:' + 'a'.repeat(64),
  next_action: {operation: 'structure_change', payload: {operation: 'start_authoring', expected_project_lifecycle: 'sha256:' + 'a'.repeat(64)}}};

test('a selected manuscript without a plan owner offers Start reader plan and posts the owner\'s exact next action', async () => {
  const home = await renderHome({title: 'Due diligence', status: 'resolved', source_optional: true, authoring_lifecycle: lifecycle,
    capabilities: {manuscript: true, start_planning: true}});
  assert.ok(home.button('Continue manuscript'), 'the manuscript stays reachable');
  await home.button('Start reader plan').onclick();
  assert.deepEqual(home.calls, [{path: '/work/structure/change', payload: {project: 'dd', operation: 'start_authoring',
    expected_project_lifecycle: lifecycle.revision}}]);
  assert.equal(home.reloads.length, 1);
});

test('without an offered action the page refuses instead of composing a guard of its own', async () => {
  const home = await renderHome({title: 'Due diligence', status: 'resolved', authoring_lifecycle: {state: 'MANUSCRIPT_WITHOUT_PLAN', next_action: null},
    capabilities: {manuscript: true, start_planning: true}});
  await assert.rejects(home.button('Start reader plan').onclick(), /no planning action is offered/);
  assert.deepEqual(home.calls, []);
});

test('a project that owns its plan, or has no manuscript, shows no Start reader plan', async () => {
  for (const capabilities of [{manuscript: true, start_planning: false}, {manuscript: false, start_manuscript: true}]) {
    const home = await renderHome({title: 'Due diligence', status: 'resolved', capabilities, source_optional: true});
    assert.equal(home.button('Start reader plan'), undefined, JSON.stringify(capabilities));
  }
});
