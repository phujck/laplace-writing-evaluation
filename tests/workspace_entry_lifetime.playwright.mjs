// The workspace entry's lifetime, composed (M5 S2-R2). The real served /shared/workspace.mjs is imported on a
// same-origin probe page of the real HTTP owners (tests/helpers/walk_owner_server.py) and mounted on an attached
// #probe for the synthetic book. Stubs: /authoring/providers answers no provider; a case may fail (HTTP 500) or
// hold one entry read (/projects/metadata, /work/state). The probe page itself is a fixed test document.
// window/document listeners and timers are counted from page start by wrapping addEventListener/removeEventListener
// and setTimeout/clearTimeout/setInterval/clearInterval. "Baseline" is the page after the shell modules were imported
// and before mountWorkspace ran: module singletons (store.mjs's one popstate listener) live as long as the page.
//   L1 a failed metadata entry: the error and Retry stay, the returned control has destroy(); destroy returns the
//      listeners and pending timers to baseline, is idempotent, releases the global handle and keeps saved drafts.
//   L2 a failed Work summary entry: the same.
//   L3 destroy while the entry reads are pending, then a replacement shell on the same root: the first entry's late
//      reads neither repaint nor overwrite the replacement; disposing the replacement returns to baseline.
//   L4 a successful entry: ready, then destroy returns to baseline.
//   L5-L9 the entry's continuations after its initial reads (S2-R2 residual): an old mount's held explicit Work
//      detail (owner success via an exact-coordinate double, or the owner's real refusal) and its held profile read
//      (the owner's real success, or a rejection), released after the old shell was destroyed and a replacement
//      mounted on the SAME connected root: the replacement's URL, Work chip, notice, painted nodes, unsent draft,
//      global handle and navigation signal are unchanged, nothing is composed and nothing is posted.
//   N1-N3 without destroy, the same entry branches still work: an explicit off-page Work is admitted through its
//      exact detail read, its refusal names it, and a valid profile-generation intent is composed for review with
//      its address cleared, never sent.
// Run: node tests/workspace_entry_lifetime.playwright.mjs
import {startOwners} from './helpers/owner_browser.mjs';

let passed = 0;
function ok(condition, message) {
  if (!condition) throw new Error('FAIL: ' + message);
  passed += 1;
  console.log('ok - ' + message);
}
const TRACK = () => {
  const listeners = new Map(), timers = new Map();
  for (const target of [window, document]) {
    const add = target.addEventListener, remove = target.removeEventListener, name = target === window ? 'window' : 'document';
    const key = (type, options) => name + ':' + type + ':' + !!(typeof options === 'boolean' ? options : options?.capture);
    target.addEventListener = function (type, fn, options) {
      if (fn) {const k = key(type, options), set = listeners.get(k) || new Set(); set.add(fn); listeners.set(k, set);}
      return add.call(this, type, fn, options);
    };
    target.removeEventListener = function (type, fn, options) {listeners.get(key(type, options))?.delete(fn); return remove.call(this, type, fn, options);};
  }
  const setT = window.setTimeout, clearT = window.clearTimeout, setI = window.setInterval, clearI = window.clearInterval;
  window.setTimeout = (fn, delay, ...args) => {let id; id = setT(() => {timers.delete(id); if (typeof fn === 'function') fn(...args);}, delay); timers.set(id, 'timeout:' + (delay || 0)); return id;};
  window.clearTimeout = id => {timers.delete(id); clearT(id);};
  window.setInterval = (fn, delay, ...args) => {const id = setI(fn, delay, ...args); timers.set(id, 'interval:' + (delay || 0)); return id;};
  window.clearInterval = id => {timers.delete(id); clearI(id);};
  window.__track = () => ({listeners: Object.fromEntries([...listeners].filter(([, set]) => set.size).map(([k, set]) => [k, set.size]).sort()),
    timers: [...timers.values()].filter(row => row !== 'timeout:0').sort()});
};
const PROBE = '<!doctype html><meta charset="utf-8"><title>probe</title><div id="probe"></div>';

async function probePage(owners, {fail = null, hold = null, query = '', holdWhere = null} = {}) {
  const page = await owners.newPage({viewport: {width: 1280, height: 900}});
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(TRACK);
  await page.route(url => url.pathname === '/__probe', route => route.fulfill({contentType: 'text/html', body: PROBE}));
  await page.route('**/authoring/providers*', route => route.fulfill({contentType: 'application/json', body: '{"providers":[]}'}));
  let release = () => {}, holding = 0;
  if (fail) await page.route(url => url.pathname === fail, route => route.fulfill({status: 500, contentType: 'application/json', body: '{"error":"synthetic entry failure"}'}));
  if (hold) {
    const held = new Promise(resolve => {release = resolve;});
    await page.route(url => url.pathname === hold, async route => {if (holding++ === 0) await held; await route.continue();});
  }
  // holdWhere(url): park the first matching read until release(answer); answer is 'owner' (the real owner) or a
  // fulfilment {status, body} (a supported route double)
  if (holdWhere) {
    const held = new Promise(resolve => {release = resolve;});
    await page.route(holdWhere, async route => {if (holding++ !== 0) return route.continue(); const answer = await held;
      if (answer === 'owner') return route.continue();
      return route.fulfill({status: answer.status || 200, contentType: 'application/json', body: JSON.stringify(answer.body)});});
  }
  page.__posts = [];
  page.on('request', request => {if (request.method() === 'POST') page.__posts.push(request.url().replace(owners.base, ''));});
  await page.goto(owners.base + '/__probe?workspace=writing&corpus=book' + query);
  await page.evaluate(async () => {localStorage.setItem('laplace:probe:saved-draft', 'kept words'); await import('/shared/workspace.mjs');});
  await page.waitForFunction(() => true);   // Playwright's injected script installs its own window listeners once; baseline after it
  const baseline = await page.evaluate(() => window.__track());
  return {page, errors, baseline, release: answer => release(answer), parked: () => holding};
}
const mount = page => page.evaluate(async () => {
  const {mountWorkspace} = await import('/shared/workspace.mjs');
  window.__control = await mountWorkspace(document.getElementById('probe'), 'book');
  return {keys: Object.keys(window.__control).sort(), entry: document.getElementById('probe').dataset.entry};
});
const settle = page => page.waitForTimeout(400);
const tracked = page => page.evaluate(() => window.__track());
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

const owners = await startOwners();
try {
  // L1, L2
  for (const [label, path] of [['L1 failed metadata entry', '/projects/metadata'], ['L2 failed Work summary entry', '/work/state']]) {
    const {page, errors, baseline} = await probePage(owners, {fail: path});
    const control = await mount(page);
    const view = await page.evaluate(() => ({main: document.querySelector('#probe [data-main]')?.textContent || '',
      retry: [...document.querySelectorAll('#probe button')].some(button => button.textContent === 'Retry opening project'),
      notice: document.querySelector('#probe [data-notice]')?.textContent || '', global: window.laplaceWorkspace === window.__control}));
    ok(control.entry === 'failed' && control.keys.includes('destroy'), label + ': the failed entry returns the destroy-capable control (' + control.keys.join(',') + ')');
    ok(/Project could not load/.test(view.main) && view.retry && /drafts are retained/.test(view.notice), label + ': the error, Retry and the drafts notice stay');
    const live = await tracked(page);
    ok(!same(live.listeners, baseline.listeners) && live.timers.length > baseline.timers.length, label + ': before disposal the shell holds listeners and a pending timer');
    await page.evaluate(() => {window.__control.destroy(); window.__control.destroy();});
    await settle(page);
    const after = await tracked(page);
    ok(same(after.listeners, baseline.listeners), label + ': destroy returns window/document listeners to baseline' + (same(after.listeners, baseline.listeners) ? '' : ' ' + JSON.stringify(after.listeners)));
    ok(same(after.timers, baseline.timers), label + ': destroy leaves no pending timer (' + JSON.stringify(after.timers) + ')');
    const kept = await page.evaluate(() => ({global: window.laplaceWorkspace, entry: document.getElementById('probe').dataset.entry,
      draft: localStorage.getItem('laplace:probe:saved-draft')}));
    ok(kept.global === null && kept.entry === 'destroyed' && kept.draft === 'kept words' && view.global, label + ': the global handle is released, destroy is idempotent, saved drafts stay');
    ok(errors.length === 0, label + ': no page error');
    await page.close();
  }

  // L3
  {
    const {page, errors, baseline, release} = await probePage(owners, {hold: '/projects/metadata'});
    await page.evaluate(() => {import('/shared/workspace.mjs').then(({mountWorkspace}) => {
      window.__first = mountWorkspace(document.getElementById('probe'), 'book');});});
    await page.waitForFunction(() => document.getElementById('probe').dataset.entry === 'pending');
    const first = await page.evaluate(() => {const control = window.laplaceWorkspace; window.__firstControl = control; control.destroy();
      return {entry: document.getElementById('probe').dataset.entry, title: document.querySelector('#probe h1')?.textContent};});
    ok(first.entry === 'destroyed', 'L3 a shell destroyed while its entry reads are pending reads destroyed');
    await page.evaluate(async () => {const {mountWorkspace} = await import('/shared/workspace.mjs');
      window.__second = await mountWorkspace(document.getElementById('probe'), 'book');});
    // mark the replacement's own painted nodes: a late repaint would replace them even with identical markup
    const before = await page.evaluate(() => {const main = document.querySelector('#probe [data-main]');
      window.__painted = [...main.children]; for (const node of window.__painted) node.dataset.l3Painted = 'replacement';
      return {entry: document.getElementById('probe').dataset.entry, main: main.innerHTML, painted: window.__painted.length};});
    ok(before.entry === 'ready', 'L3 a replacement shell mounts on the same root and is ready');
    release();
    const late = await page.evaluate(async () => (await window.__first) === window.__firstControl);
    await settle(page);
    const after = await page.evaluate(() => {const main = document.querySelector('#probe [data-main]');
      return {entry: document.getElementById('probe').dataset.entry, main: main?.innerHTML, global: window.laplaceWorkspace === window.__second,
        kept: window.__painted.every(node => node.isConnected && node.parentElement === main) && main.children.length === window.__painted.length};});
    ok(before.painted > 0 && after.kept && after.entry === 'ready' && after.main === before.main && after.global,
      'L3 the first entry\'s late reads neither repaint nor overwrite the replacement (its painted nodes stay)');
    ok(late === true, 'L3 the first mount resolves to the same control it published (destroyed, no second shell)');
    await page.evaluate(() => window.__second.destroy());
    await settle(page);
    const end = await tracked(page);
    ok(same(end.listeners, baseline.listeners) && same(end.timers, baseline.timers), 'L3 disposing both returns listeners and timers to baseline'
      + (same(end.listeners, baseline.listeners) ? '' : ' ' + JSON.stringify(end.listeners)) + ' ' + JSON.stringify(end.timers));
    ok(errors.length === 0, 'L3 no page error (' + errors.slice(0, 2).join(' | ') + ')');
    await page.close();
  }

  // L4
  {
    const {page, errors, baseline} = await probePage(owners);
    const control = await mount(page);
    ok(control.entry === 'ready', 'L4 a successful entry is ready');
    await page.evaluate(() => window.__control.destroy());
    await settle(page);
    const after = await tracked(page);
    ok(same(after.listeners, baseline.listeners) && same(after.timers, baseline.timers), 'L4 destroy after a successful entry returns listeners and timers to baseline'
      + (same(after.listeners, baseline.listeners) ? '' : ' ' + JSON.stringify(after.listeners)) + ' ' + JSON.stringify(after.timers));
    ok(errors.length === 0, 'L4 no page error');
    await page.close();
  }

  // L5-L9: an old entry's later continuation released after destroy + a replacement on the same root
  const isDetail = id => url => url.pathname === '/work/state' && url.searchParams.get('view') === 'detail' && url.searchParams.get('id') === id;
  const isProfile = url => url.pathname === '/work/profiles';
  const OLD_TASK = {project: 'book', view: 'detail', task: {id: 'WORK-old', title: 'Old held Work', project: 'book', section_ids: [],
    work_scope_revision: 'sha256:' + '1'.repeat(64), dependency_revision: 'sha256:' + '2'.repeat(64)}};
  const replacementState = page => page.evaluate(() => {const root = document.getElementById('probe');
    return {url: location.pathname + location.search, chipHidden: root.querySelector('[data-work-scope]')?.hidden, chip: root.querySelector('[data-work-scope]')?.textContent,
      notice: root.querySelector('[data-notice]')?.textContent || '', draft: root.querySelector('[data-message]')?.value ?? null, entry: root.dataset.entry,
      global: window.laplaceWorkspace === window.__second, painted: window.__painted.every(node => node.isConnected) && root.querySelector('[data-main]').children.length === window.__painted.length,
      navigation: window.__navigation};});
  // LAPLACE_ENTRY_CASES=L5,L7 runs only those late cases (used by the per-case failed controls)
  const only = process.env.LAPLACE_ENTRY_CASES?.split(',');
  async function lateContinuation(label, {query, holdWhere, answer}) {
    if (only && !only.includes(label.split(' ')[0])) return;
    const {page, errors, release, parked} = await probePage(owners, {query, holdWhere});
    await page.evaluate(() => {import('/shared/workspace.mjs').then(({mountWorkspace}) => {window.__first = mountWorkspace(document.getElementById('probe'), 'book');});});
    // wait until the route handler has actually parked the old entry's later read (its initial reads have settled)
    for (let waited = 0; parked() < 1; waited += 50) {if (waited > 20000) throw new Error('FAIL: ' + label + ': the held read was never issued'); await page.waitForTimeout(50);}
    const parkedState = await page.evaluate(() => ({entry: document.getElementById('probe').dataset.entry, title: document.querySelector('#probe h1')?.textContent}));
    ok(parked() === 1 && parkedState.entry === 'pending' && parkedState.title, label + ': the old entry is parked on its later read after its initial reads');
    await page.evaluate(async () => {
      window.__firstControl = window.laplaceWorkspace; window.__firstControl.destroy();
      history.replaceState({}, '', '/__probe?workspace=writing&corpus=book');
      const {mountWorkspace} = await import('/shared/workspace.mjs');
      window.__second = await mountWorkspace(document.getElementById('probe'), 'book');
      const root = document.getElementById('probe'), message = root.querySelector('[data-message]');
      if (message) {message.value = 'my unsent replacement draft'; message.dispatchEvent(new Event('input', {bubbles: true}));}
      window.__painted = [...root.querySelector('[data-main]').children];
      window.__navigation = 0; window.addEventListener('laplace-workspace-navigation', () => {window.__navigation++;});
    });
    const before = await replacementState(page), postsBefore = page.__posts.length;
    release(answer);
    const resolved = await page.evaluate(async () => (await window.__first) === window.__firstControl);
    await settle(page);
    const after = await replacementState(page);
    ok(before.entry === 'ready' && before.draft === 'my unsent replacement draft' && resolved, label + ': setup (replacement ready with an unsent draft; old mount resolved)');
    ok(same(after, before), label + ': the replacement is unchanged' + (same(after, before) ? '' : ' ' + JSON.stringify({before, after})));
    ok(page.__posts.length === postsBefore && errors.length === 0, label + ': nothing posted, no page error');
    await page.evaluate(() => window.__second.destroy());
    await page.close();
  }
  await lateContinuation('L5 held Work detail success', {query: '&work=WORK-old', holdWhere: isDetail('WORK-old'), answer: {body: OLD_TASK}});
  await lateContinuation('L6 held Work detail refusal (the owner\'s real 422)', {query: '&work=WORK-old', holdWhere: isDetail('WORK-old'), answer: 'owner'});
  await lateContinuation('L7 held profile read success (the owner\'s real basis)', {query: '&profile_generation=voice&profile_scope=project', holdWhere: isProfile,
    answer: 'owner'});
  await lateContinuation('L8 held profile read rejection', {query: '&profile_generation=voice&profile_scope=project', holdWhere: isProfile,
    answer: {status: 500, body: {error: 'controlled late profile rejection'}}});
  await lateContinuation('L9 held explicit Work detail with a profile intent queued behind it on the same entry', {query: '&work=WORK-old&profile_generation=voice&profile_scope=project',
    holdWhere: isDetail('WORK-old'), answer: {body: OLD_TASK}});

  // N1-N3: the same branches without destroy
  {
    const {page, errors} = await probePage(owners, {query: '&work=WORK-new'});
    await page.route(isDetail('WORK-new'), route => route.fulfill({contentType: 'application/json', body: JSON.stringify({...OLD_TASK,
      task: {...OLD_TASK.task, id: 'WORK-new', title: 'Explicit off-page Work'}})}));
    await mount(page);
    const state = await page.evaluate(() => ({url: location.search, chip: document.querySelector('#probe [data-work-scope]').textContent,
      hidden: document.querySelector('#probe [data-work-scope]').hidden, entry: document.getElementById('probe').dataset.entry}));
    ok(state.entry === 'ready' && !state.hidden && state.chip === 'Explicit off-page Work' && /work=WORK-new/.test(state.url) && page.__posts.length === 0 && errors.length === 0,
      'N1 an explicit off-page Work is admitted through its exact detail read (chip, URL), nothing posted');
    await page.evaluate(() => window.__control.destroy()); await page.close();
  }
  {
    const {page, errors} = await probePage(owners, {query: '&work=WORK-gone'});
    await mount(page);
    const state = await page.evaluate(() => ({notice: document.querySelector('#probe [data-notice]').textContent, hidden: document.querySelector('#probe [data-work-scope]').hidden,
      entry: document.getElementById('probe').dataset.entry}));
    ok(state.entry === 'ready' && state.hidden && /Requested Work WORK-gone was not opened/.test(state.notice) && page.__posts.length === 0 && errors.length === 0,
      'N2 the owner\'s refusal of an explicit Work is named and nothing else is selected');
    await page.evaluate(() => window.__control.destroy()); await page.close();
  }
  {
    const {page, errors} = await probePage(owners, {query: '&profile_generation=voice&profile_scope=project'});
    await mount(page);
    const state = await page.evaluate(() => ({url: location.search, notice: document.querySelector('#probe [data-notice]').textContent,
      draft: document.querySelector('#probe [data-message]')?.value || '', entry: document.getElementById('probe').dataset.entry}));
    ok(state.entry === 'ready' && /Generate a project voice preference suggestion/.test(state.draft) && /prepared in this project conversation\. Review it and Send/.test(state.notice)
      && !/profile_generation|profile_scope/.test(state.url) && page.__posts.length === 0 && errors.length === 0,
      'N3 a valid profile-generation intent is composed for review, its address cleared, and nothing is sent');
    await page.evaluate(() => window.__control.destroy()); await page.close();
  }
} finally {
  await owners.close();
}
console.log('\n' + passed + ' assertions passed');
