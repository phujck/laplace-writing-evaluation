// Work focus handoff, composed (M5 S2; Root actual D-work-main-keyboard-page and D-work-graph-keyboard-focus).
// The real shell page head (pipeline.html stylesheets) and the REAL mountWorkspace -> Work controller ->
// object header -> topology modules run in Chromium. Only public owner HTTP answers are stubbed (the shell
// fixture's owner table plus a 52-Work owner catalogue); nothing private is called. Real keyboard Enter/Space
// activate controls; document.activeElement is read from the browser, so a focus proof means real focus.
// Cases: C1 main More, C2 graph selection (SVG and compact list), C3 currentness/refusal, C4 overlap and
// lifetime, C5 widths (C1-C5 page the secondary All Work list, opened explicitly), C6 the default navigator and the
// relationships tabs by keyboard at 1280 and 390 px. Run: node tests/workspace_focus.playwright.mjs
import {createRequire} from 'module';
import {execSync} from 'child_process';
import {existsSync, readFileSync} from 'fs';
import http from 'http';
import path from 'path';
import {fileURLToPath} from 'url';
import {defaultRoutes} from './helpers/shell_fixture.mjs';

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const roots = [
  (() => {try {return execSync('npm root -g', {stdio: ['ignore', 'pipe', 'ignore']}).toString().trim() + '/playwright';} catch {return '';}})(),
  `${ROOT}/node_modules/playwright`, `${ROOT}/node_modules/playwright-core`,
  '/home/phujck/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright-core',
  '/usr/lib/chatgpt/resources/cua_node/lib/node_modules/playwright-core',
].filter(Boolean);
const pwRoot = roots.find(existsSync);
if (!pwRoot) throw new Error(`Playwright is absent; searched ${roots.join(', ')}`);
const {chromium} = require(pwRoot);
const chrome = execSync("find /opt/pw-browsers \"$HOME/.cache/ms-playwright\" -type f -path '*/chrome-linux*/chrome' -print -quit 2>/dev/null || true").toString().trim();

let passed = 0;
function ok(condition, message) {
  if (!condition) throw new Error('ASSERT FAILED: ' + message);
  passed += 1;
  console.log('  ok -', message);
}

// ---- the owner fixture: 52 Work rows, pages of 12 under one cut; W50 is the selected off-page Work ----
const PAGE = 12, TOTAL = 52, CUT = 'cut-1';
const id = n => 'W' + String(n).padStart(2, '0');
const row = n => ({id: id(n), title: 'Fixture child ' + String(n).padStart(2, '0'), status: 'open', recorded_status: 'open',
  lifecycle: {status: 'open', completed: false, closed: false}, readiness: {status: 'READY'},
  current_acceptance: {status: 'NOT_REQUIRED', review_required: false}});
const summaryURL = (offset, cut = CUT) => '/work/state?' + new URLSearchParams({project: 'book', view: 'summary', offset: String(offset), limit: String(PAGE), as_of: cut});
function summaryPage(offset, {cut = CUT, nextOffset} = {}) {
  const tasks = [];for (let n = offset + 1; n <= Math.min(offset + PAGE, TOTAL); n++) tasks.push(row(n));
  // page one also carries the selected off-page Work (the owner's retained selection fallback)
  if (offset === 0) tasks.push(row(50));
  const next = nextOffset !== undefined ? nextOffset : offset + PAGE < TOTAL ? offset + PAGE : null;
  return {project: 'book', view: 'summary', tasks, counts: {pending: TOTAL, completed: 0, completed_review_required: 0},
    read_cut: {revision: cut}, framing: {framing: {purpose: 'A test purpose.'}},
    pagination: {total: TOTAL, offset, limit: PAGE, next_offset: next, next_read: next == null ? null : {http: {method: 'GET', url: summaryURL(next, CUT)}}}};
}
const page1 = items => ({items, total: items.length, offset: 0, limit: 20, next_offset: null, next_read: null});
const detail = workId => ({project: 'book', view: 'detail', task: {...row(Number(workId.slice(1))), goal: 'Authored criterion for ' + workId,
  child_count: workId === id(50) ? 2 : 0}, blockers: [], children: page1(workId === id(50) ? [row(3), row(4)] : []), dependants: page1([]),
  requires: page1([]), read_cut: {revision: CUT}});
// the navigator's owner reads (project_work_navigation shapes): one campaign W50 containing W03 and W04, two unfiled roots
const navRow = (n, extra = {}) => ({...row(n), grade: 'task', child_count: 0, purpose: 'Purpose of ' + id(n),
  standing: {group: 'ready', facts: [{code: 'ready', text: 'Ready'}]}, ...extra});
const campaign = () => navRow(50, {grade: 'campaign', child_count: 2, rollup: {descendants: 2, groups: {ready: 2}, next: {id: id(3), title: 'Fixture child 03'}, attention: [], coverage: 'complete'}});
const none = {total: 0, offset: 0, limit: 6, next_offset: null, next_read: null, items: []};
const rootsPage = () => ({project: 'book', view: 'roots', read_cut: {revision: CUT}, roots: [campaign(), navRow(1), navRow(2)],
  pagination: {total: 3, offset: 0, limit: 12, next_offset: null, next_read: null}, counts: {roots: 3, campaigns: 1, unfiled: 2, work: 5}, attention: none});
const branchPage = () => ({project: 'book', view: 'branch', read_cut: {revision: CUT}, node: campaign(), breadcrumbs: [],
  children: [navRow(3, {needs: {siblings: [], outside: 0, open: 0, needed_by_siblings: 1}, parallel: {code: 'no-open-prerequisite', text: 'None of its declared prerequisites is open; conflicts, authority and resources are not assessed.'}}),
    navRow(4, {needs: {siblings: [id(3)], outside: 0, open: 1, needed_by_siblings: 0}})],
  pagination: {total: 2, offset: 0, limit: 12, next_offset: null, next_read: null}, order: {kind: 'authored', cyclic: []}});
const graph = parent => ({project: 'book', view: 'graph', read_cut: {revision: CUT},
  nodes: [row(50), row(3), row(4)].map(r => ({...r, id: r.id})), edges: [{source: id(50), target: id(3), kind: 'contains'}, {source: id(50), target: id(4), kind: 'contains'}],
  boundaries: [], pagination: {next_read: null}, parent_work_id: parent});

// ---- the server: page, shared assets, owner routes; a test can hold one owner reply ----
const types = {'.mjs': 'text/javascript', '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.svg': 'image/svg+xml', '.json': 'application/json'};
const head = readFileSync(`${ROOT}/src/laplace/web/pipeline.html`, 'utf8').match(/<head>([\s\S]*?)<\/head>/)[1];
const page = `<!doctype html><html><head>${head}</head><body><main id="root"></main><script type="module">
import {mountWorkspace} from '/shared/workspace.mjs';
try{window.__ws=await mountWorkspace(document.getElementById('root'),'book');window.__ready=true;}
catch(e){window.__error=e.message+'\\n'+e.stack;}
</script></body></html>`;
const owners = defaultRoutes();
let hold = null, faults = {}, requests = [];
function ownerAnswer(url) {
  const q = url.searchParams;
  if (url.pathname === '/work/state') {
    if (q.get('view') === 'summary') {
      const offset = Number(q.get('offset') || 0);
      if (faults.cut && offset > 0) return summaryPage(offset, {cut: 'moved'});
      if (faults.namespace && offset > 0) return {...summaryPage(offset), project: 'other'};
      // a valid continuation whose only row is already shown: with a further page, or exhausted
      if (faults.repeatOnly && offset > 0) return {...summaryPage(offset, {nextOffset: faults.repeatOnly === 'last' ? null : undefined}), tasks: [row(50)]};
      if (faults.stall && offset > 0) return summaryPage(offset, {nextOffset: offset});
      return summaryPage(offset);
    }
    if (q.get('view') === 'detail') return detail(q.get('id'));
    if (q.get('view') === 'graph') return graph(q.get('parent_work_id'));
    if (q.get('view') === 'roots') return rootsPage();
    if (q.get('view') === 'branch') return branchPage();
    if (q.get('view') === 'attention') return {project: 'book', view: 'attention', read_cut: {revision: CUT}, tasks: [], pagination: none};
    if (q.get('view') === 'observe') return {project: 'book', view: 'observe', token: 'wo1.a.b.c', changed: q.get('since') ? false : null, poll: {after_ms: 5000, max_ms: 60000, backoff: 2}};
  }
  const route = owners[url.pathname];
  return route ? route(q, {}) : {};
}
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://local');
  if (url.pathname === '/project') {res.writeHead(200, {'content-type': 'text/html'});return res.end(page);}
  if (url.pathname.startsWith('/shared/')) {
    const file = path.join(ROOT, 'src/laplace/web/static_shared', path.normalize(url.pathname.slice(8)));
    if (file.startsWith(path.join(ROOT, 'src/laplace/web/static_shared')) && existsSync(file)) {res.writeHead(200, {'content-type': types[path.extname(file)] || 'application/octet-stream'});return res.end(readFileSync(file));}
    res.writeHead(404);return res.end('');
  }
  requests.push(req.method + ' ' + url.pathname + url.search);
  if (hold && hold.match(url)) {const gate = hold;hold = null;gate.waiting = true;await gate.released;}
  res.writeHead(200, {'content-type': 'application/json'});res.end(JSON.stringify(ownerAnswer(url)));
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch(chrome ? {executablePath: chrome} : {});
function holdNext(match) {let release;const gate = {match, released: new Promise(r => {release = r;})};gate.release = release;hold = gate;return gate;}

async function open(width, {work = id(50), flat = true} = {}) {
  faults = {};requests = [];hold = null;
  const context = await browser.newContext({viewport: {width, height: 900}});const tab = await context.newPage();const errors = [];
  tab.on('pageerror', error => errors.push(error.message));
  await tab.goto(`${base}/project?workspace=writing&corpus=book&view=work&work=${work}`);
  await tab.waitForFunction(() => window.__ready || window.__error, null, {timeout: 15000});
  const failure = await tab.evaluate(() => window.__error || null);
  if (failure) throw new Error('shell failed: ' + failure);
  await tab.waitForFunction(() => document.querySelector('.operator-work-catalog [data-work-id]'), null, {timeout: 10000});
  // the flat All Work list is a secondary disclosure of the navigator; the paging cases open it explicitly
  if (flat) {await tab.locator('.work-flat-catalogue > summary').click();await tab.waitForFunction(() => document.querySelector('.operator-work-flat [data-work-id]')?.getBoundingClientRect().height > 0, null, {timeout: 5000});}
  return {tab, context, errors};
}
const active = tab => tab.evaluate(() => {const a = document.activeElement;
  return {tag: a?.tagName, workId: a?.dataset?.workId || null, focusTarget: a?.dataset?.focusTarget || null, text: a?.textContent?.trim()?.slice(0, 60) || '',
    tabIndex: a?.tabIndex, connected: !!a?.isConnected, control: a?.dataset?.control || null};});
const rows = tab => tab.evaluate(() => [...document.querySelectorAll('.operator-work-flat [data-work-id]')].map(b => b.dataset.workId));
const visible = (tab, selector = ':focus') => tab.evaluate(s => {const n = document.querySelector(s);if (!n) return false;const b = n.getBoundingClientRect();
  let p = n.parentElement;while (p && p !== document.body) {const r = p.getBoundingClientRect(), st = getComputedStyle(p);
    if (/(auto|scroll|hidden)/.test(st.overflowY + st.overflowX) && (b.bottom <= r.top || b.top >= r.bottom || b.right <= r.left || b.left >= r.right)) return false;p = p.parentElement;}
  return b.width > 0 && b.height > 0 && b.bottom > 0 && b.top < innerHeight && b.right > 0 && b.left < innerWidth;}, selector);
const settle = tab => tab.waitForTimeout(120);
const moreButton = tab => tab.locator('.operator-work-flat button', {hasText: 'More work'});

try {
  console.log('C1 main More: keyboard paging hands focus to the first genuinely new row');
  {
    const {tab, context, errors} = await open(1280);
    ok((await rows(tab)).length === 13, 'page one: 12 owner rows plus the retained selected W50');
    const url = await tab.evaluate(() => location.href);
    await moreButton(tab).focus();
    ok((await active(tab)).text === 'More work', 'More work holds keyboard focus before activation');
    const gate = holdNext(u => u.searchParams.get('view') === 'summary' && u.searchParams.get('offset') === '12');
    await tab.keyboard.press('Enter');
    await tab.waitForFunction(() => document.querySelector('.operator-work-catalog button[disabled]'), null, {timeout: 5000});
    gate.release();
    await tab.waitForFunction(() => document.querySelector('[data-work-id="W13"]'), null, {timeout: 5000});await settle(tab);
    let now = await active(tab);
    ok(now.workId === 'W13' && now.connected, `focus is on the first new Work row W13 (got ${JSON.stringify(now)})`);
    ok(await visible(tab), 'the focused new row is visible inside the catalogue');
    let shown = await rows(tab);
    ok(shown.length === 25 && new Set(shown).size === 25, `25 unique rows after the first continuation (${shown.length})`);
    ok(await moreButton(tab).count() === 1, 'one More control for the next page');
    ok(await tab.evaluate(() => location.href) === url, 'the selected Work and URL are unchanged by paging');
    ok(await tab.evaluate(() => document.querySelector('.object-title')?.textContent) === 'Fixture child 50', 'the selected detail stays W50');
    for (const first of ['W25', 'W37', 'W49']) {
      await moreButton(tab).focus();await tab.keyboard.press('Enter');
      await tab.waitForFunction(f => document.querySelector(`[data-work-id="${f}"]`), first, {timeout: 5000});await settle(tab);
      now = await active(tab);ok(now.workId === first && await visible(tab), `the next page focuses its first new row ${first}`);
    }
    shown = await rows(tab);
    ok(shown.length === TOTAL && new Set(shown).size === TOTAL, `complete: ${TOTAL} unique rows; the retained W50 is never painted twice`);
    ok(await moreButton(tab).count() === 0, 'the exhausted continuation has no More control');
    ok(!errors.length, 'no page errors: ' + errors.join(' | '));
    await context.close();
  }

  console.log('C1b a valid page that adds no new visible row lands on the next More, else an honest attached fallback');
  for (const mode of ['more', 'last']) {
    const {tab, context, errors} = await open(1280);faults.repeatOnly = mode;
    await moreButton(tab).focus();await tab.keyboard.press('Enter');await settle(tab);await settle(tab);
    const now = await active(tab);
    if (mode === 'more') ok(now.tag === 'BUTTON' && now.text === 'More work' && now.connected, `a further page: focus moves to the new More control (${JSON.stringify(now)})`);
    else ok(now.tag === 'P' && now.tabIndex === -1 && /no new Work rows/.test(now.text) && now.connected, `exhausted: focus is on the declared fallback, never BODY (${JSON.stringify(now)})`);
    ok((await rows(tab)).length === 13, `${mode}: no row was painted twice`);
    ok(!errors.length, `${mode}: no page errors`);
    await context.close();
  }

  console.log('C3 currentness: stale cut, other namespace and a non-advancing continuation refuse and keep the opener');
  for (const fault of ['cut', 'namespace']) {
    const {tab, context, errors} = await open(1280);faults[fault] = true;
    await moreButton(tab).focus();await tab.keyboard.press('Enter');await settle(tab);await settle(tab);
    ok((await rows(tab)).length === 13, `${fault}: page one rows are intact and nothing was appended`);
    const now = await active(tab);
    ok(now.text === 'More work' && now.tag === 'BUTTON', `${fault}: the re-enabled opener keeps keyboard focus (${JSON.stringify(now)})`);
    const said = await tab.evaluate(() => [...document.querySelectorAll(".work-status")].map(n => n.textContent).join(" | "));
    ok(/cut changed|different summary namespace/.test(said), `${fault}: the refusal is stated (${said})`);
    ok(!errors.length, `${fault}: no page errors`);
    await context.close();
  }
  {
    // the owner's second page names a continuation that does not advance past it: refused before any read
    const {tab, context, errors} = await open(1280);faults.stall = true;
    await moreButton(tab).focus();await tab.keyboard.press('Enter');
    await tab.waitForFunction(() => document.querySelector('[data-work-id="W13"]'), null, {timeout: 5000});await settle(tab);
    const reads = requests.filter(r => r.includes('view=summary')).length;
    await moreButton(tab).focus();await tab.keyboard.press('Enter');await settle(tab);await settle(tab);
    ok(requests.filter(r => r.includes('view=summary')).length === reads, 'a non-advancing continuation is refused before any owner read');
    ok((await rows(tab)).length === 25 && /did not advance/.test(await tab.evaluate(() => [...document.querySelectorAll('.work-status')].map(n => n.textContent).join(' | '))), 'the shown rows stay and the refusal is stated');
    ok((await active(tab)).text === 'More work', 'the opener keeps keyboard focus');
    ok(!errors.length, 'stall: no page errors');
    await context.close();
  }

  console.log('C2 graph: Return and Space on a visible SVG node land on the new selected Work heading');
  for (const key of ['Enter', ' ']) {
    const {tab, context, errors} = await open(1280);
    await tab.locator('.operator-work-neighbourhood .lazy-toggle').click();
    await tab.waitForFunction(() => document.querySelector('[data-topology-node="W03"]'), null, {timeout: 5000});
    await tab.locator('g[data-topology-node="W03"]').focus();
    ok((await tab.evaluate(() => document.activeElement?.dataset?.topologyNode)) === 'W03', 'the SVG node for W03 holds focus');
    await tab.keyboard.press(key);
    await tab.waitForFunction(() => document.querySelector('.object-title')?.textContent === 'Fixture child 03', null, {timeout: 5000});await settle(tab);
    const now = await active(tab);
    ok(now.tag === 'H3' && now.focusTarget === 'selected-work' && now.tabIndex === -1 && now.text === 'Fixture child 03', `${key === ' ' ? 'Space' : 'Return'}: focus is on the new heading (${JSON.stringify(now)})`);
    ok(await visible(tab), 'the focused heading is visible');
    ok(await tab.evaluate(() => new URL(location.href).searchParams.get('work')) === 'W03', 'the URL names the selected Work');
    ok(await tab.evaluate(() => document.querySelectorAll('[data-focus-target="selected-work"]').length) === 1, 'one focus target, the selected Work heading');
    ok(!errors.length, 'no page errors');
    await context.close();
  }

  console.log('C2b compact list below 1000 px uses the same Work owner and lands on the same heading');
  {
    const {tab, context, errors} = await open(900);
    await tab.locator('.operator-work-neighbourhood .lazy-toggle').click();
    const item = tab.locator('.operator-work-neighbourhood button', {hasText: 'Fixture child 04'}).first();
    await item.waitFor({timeout: 5000});await item.focus();await tab.keyboard.press('Enter');
    await tab.waitForFunction(() => document.querySelector('.object-title')?.textContent === 'Fixture child 04', null, {timeout: 5000});await settle(tab);
    const now = await active(tab);
    ok(now.focusTarget === 'selected-work' && now.text === 'Fixture child 04', `the compact list selection focuses the new heading (${JSON.stringify(now)})`);
    ok(!errors.length, 'no page errors');
    await context.close();
  }

  console.log('C4 overlap: a person who moves focus during a pending read keeps it');
  {
    const {tab, context, errors} = await open(1280);
    await moreButton(tab).focus();
    const gate = holdNext(u => u.searchParams.get('view') === 'summary' && u.searchParams.get('offset') === '12');
    await tab.keyboard.press('Enter');
    await tab.waitForFunction(() => document.querySelector('.operator-work-catalog button[disabled]'), null, {timeout: 5000});
    const moved = await tab.evaluate(() => {
      for (const field of document.querySelectorAll('input, textarea, select, summary')) {field.focus();if (document.activeElement === field) {window.__moved = field;return field.outerHTML.slice(0, 80);}}
      return null;});
    ok(!!moved, 'the person moved focus to another real control while the read was pending: ' + moved);
    gate.release();
    await tab.waitForFunction(() => document.querySelector('[data-work-id="W13"]'), null, {timeout: 5000});await settle(tab);
    ok(await tab.evaluate(() => document.activeElement === window.__moved), 'the older page appended its rows but did not steal focus');
    ok((await rows(tab)).length === 25, 'the valid page was still appended');
    // a selection read pending while the Work view is left does not focus anything late
    await tab.locator('.operator-work-neighbourhood .lazy-toggle').click();
    await tab.waitForFunction(() => document.querySelector('[data-topology-node="W03"]'), null, {timeout: 5000});
    const pending = holdNext(u => u.searchParams.get('view') === 'detail' && u.searchParams.get('id') === 'W04');
    await tab.locator('g[data-topology-node="W04"]').focus();await tab.keyboard.press('Enter');
    await tab.waitForTimeout(100);
    await tab.evaluate(() => window.__ws.destroy?.());
    pending.release();await settle(tab);await settle(tab);
    ok(await tab.evaluate(() => !document.querySelector('[data-focus-target="selected-work"]:focus')), 'no late heading focus after the workspace was destroyed');
    ok(!errors.length, 'no page errors: ' + errors.join(' | '));
    await context.close();
  }

  console.log('C5 widths: the focused targets stay visible and the page never scrolls sideways');
  for (const width of [1280, 1000, 720, 390]) {
    const {tab, context, errors} = await open(width);
    await moreButton(tab).focus();await tab.keyboard.press('Enter');
    await tab.waitForFunction(() => document.querySelector('[data-work-id="W13"]'), null, {timeout: 5000});await settle(tab);
    ok((await active(tab)).workId === 'W13' && await visible(tab), `${width}px: the new row is focused and visible`);
    ok(await tab.evaluate(() => document.documentElement.scrollWidth) <= width, `${width}px: no horizontal scroll`);
    ok(!errors.length, `${width}px: no page errors`);
    await context.close();
  }

  console.log('C6 navigator and relationships by keyboard: Open and Inspect are separate, tabs keep focus, Return lands on the tab');
  for (const width of [1280, 390]) {
    const {tab, context, errors} = await open(width, {flat: false});
    ok(await tab.locator('.work-flat-catalogue').evaluate(n => !n.open), `${width}px: the flat All Work list is secondary (closed)`);
    const openControl = tab.locator('[data-open-work="W50"]');ok(await openControl.isVisible(), `${width}px: the campaign has its own Open control`);
    await openControl.focus();await tab.keyboard.press('Enter');
    await tab.waitForFunction(() => document.querySelector('.work-nav-heading')?.textContent === 'Fixture child 50', null, {timeout: 5000});await settle(tab);
    let now = await active(tab);ok(now.tag === 'H3' && now.text === 'Fixture child 50' && await visible(tab), `${width}px: Open lands on the opened level heading (${JSON.stringify(now)})`);
    ok(await tab.evaluate(() => /No open declared prerequisite/.test(document.querySelector('.work-navigator-level').textContent)), `${width}px: the owner's narrow parallel fact is shown, not inferred`);
    await tab.locator('[data-work-id="W03"][data-nav-role="inspect"]').focus();await tab.keyboard.press('Enter');
    await tab.waitForFunction(() => document.querySelector('.object-title')?.textContent === 'Fixture child 03', null, {timeout: 5000});await settle(tab);
    now = await active(tab);ok(now.focusTarget === 'selected-work' && now.text === 'Fixture child 03', `${width}px: Inspect selects the child and focuses its heading`);
    await tab.locator('.work-nav-node button', {hasText: 'Inspect this Work'}).focus();await tab.keyboard.press('Enter');
    await tab.waitForFunction(() => document.querySelector('.object-title')?.textContent === 'Fixture child 50', null, {timeout: 5000});await settle(tab);
    ok((await active(tab)).text === 'Fixture child 50', `${width}px: the campaign header inspects the campaign itself`);
    const contains = tab.locator('.operator-work-relations [role="tab"][data-relation-tab="contains"]');
    ok(await contains.getAttribute('aria-selected') === 'true', `${width}px: Contains is the open relationship of a parent with no prerequisites`);
    await contains.focus();await tab.keyboard.press('ArrowLeft');await settle(tab);
    now = await tab.evaluate(() => ({tab: document.activeElement?.dataset?.relationTab, selected: document.activeElement?.getAttribute('aria-selected'),
      hidden: document.querySelector('.operator-work-relations [data-relation-tab="contains"]') && document.getElementById(document.querySelector('.operator-work-relations [data-relation-tab="contains"]').getAttribute('aria-controls')).hidden}));
    ok(now.tab === 'affects' && now.selected === 'true' && now.hidden === true, `${width}px: ArrowLeft moves focus and the shared panel to Affects (${JSON.stringify(now)})`);
    await tab.keyboard.press('End');await settle(tab);
    ok(await tab.evaluate(() => document.activeElement?.dataset?.relationTab) === 'contains', `${width}px: End returns to Contains with focus on the tab`);
    const child = tab.locator('.work-relations-panels button', {hasText: 'Fixture child 04'});ok(await child.isVisible(), `${width}px: Contains is visible in the same container`);
    await child.focus();await tab.keyboard.press('Enter');
    await tab.waitForFunction(() => document.querySelector('.object-title')?.textContent === 'Fixture child 04', null, {timeout: 5000});await settle(tab);
    const back = tab.locator('[data-relation-return="W50"]');ok(await back.isVisible(), `${width}px: the opened Work offers Return to its opener`);
    await back.focus();await tab.keyboard.press('Enter');
    await tab.waitForFunction(() => document.querySelector('.object-title')?.textContent === 'Fixture child 50', null, {timeout: 5000});await settle(tab);
    now = await tab.evaluate(() => ({tab: document.activeElement?.dataset?.relationTab, selected: document.activeElement?.getAttribute('aria-selected')}));
    ok(now.tab === 'contains' && now.selected === 'true' && await visible(tab), `${width}px: Return lands on the same open tab (${JSON.stringify(now)})`);
    ok(await tab.evaluate(() => document.documentElement.scrollWidth) <= width, `${width}px: no horizontal scroll`);
    ok(requests.length > 0 && requests.every(r => r.startsWith('GET ')), `${width}px: every owner request was a read (${requests.length})`);
    ok(!errors.length, `${width}px: no page errors: ` + errors.join(' | '));
    await context.close();
  }
} finally {
  await browser.close();server.close();
}
console.log(`\n${passed} assertions passed`);
