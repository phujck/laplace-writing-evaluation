// The long-lived workspace episode, composed (M5 S2 F1/F2, L-FRAME-MENU-HELP-EPISODE, L-HELP-QUALIFICATION).
// The real shell page (/project, mountWorkspace and its domain controllers), the real manuscript frame (/walk:
// the walk composition root, its owner modules and the writing panel) and the real HTTP owners
// (tests/helpers/walk_owner_server.py) run in Chromium. One supported public owner route is stubbed:
// /authoring/providers answers no provider, so no model is reached. The shell's own named diagnostic is read
// the way an operator reads it: Settings -> "Developer counters (diagnostics=1)" -> Refresh counters
// (manuscript_frame generation, live subscriptions and attached/disposed counts, page listeners, help and cue, open dialogs).
//   E1 readiness: the frame's first load is generation 1 with one set of 9 walk subscriptions.
//   E2 the exact passage menu on the article and its body, Open in TeX on the exact chapter, Write return.
//   E3 twenty loaded Home/Manuscript switches: the same frame and generation, the same subscriptions and page
//      listeners, no dialog, menu or extra frame left behind.
//   E4 after the switches: the same article's menu has its actions; the TeX toolbar and Write return still work.
//   E5 an unavailable join inside the shell (the article's id is not in the model): the reload item, then agreement.
//   E6 a frame reload whose document read is delayed: during the read the frame offers the browser menu (no
//      empty popup); after adoption the generation is 2 and the subscriptions are one set (9), not two.
//   E7 Help: open, start a task, Stop (focus returns to Help), reopen docked at 900 px, follow a resize, a view
//      change with Help open keeps the help-open flag and the layer connectivity in agreement, a task still starts.
//   E8 teardown: a Help open whose areas read is still pending when workspace.destroy() runs never mounts; the
//      page listeners and the frame subscriptions go to zero and the frame is detached.
// Run: node tests/workspace_episode.playwright.mjs
import {startOwners} from './helpers/owner_browser.mjs';

let passed = 0;
function ok(condition, message) {
  if (!condition) throw new Error('FAIL: ' + message);
  passed += 1;
  console.log('ok - ' + message);
}
const FRAME = 'iframe[title="Manuscript reader and editor"]';
const SHELL = '/project?workspace=writing&corpus=book&diagnostics=1';

async function openShell(owners, routes = async () => {}) {
  const page = await owners.newPage({viewport: {width: 1280, height: 900}});
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => {if (message.type() === 'error') errors.push(message.text());});
  await page.route('**/authoring/providers*', route => route.fulfill({contentType: 'application/json', body: JSON.stringify({providers: []})}));
  await routes(page);
  await page.goto(owners.base + SHELL);
  await page.waitForFunction(() => document.querySelector('.workspace')?.dataset.entry === 'ready');
  return {page, errors};
}
const nav = async (page, view) => {
  await page.click(`[data-control="nav:${view}"]`);
  await page.waitForFunction(view => document.querySelector(`[data-control="nav:${view}"]`)?.getAttribute('aria-selected') === 'true', view);
};
const openManuscript = async page => {
  await nav(page, 'manuscript');
  await page.waitForFunction(frame => document.querySelector(frame)?.contentWindow?.walk?.ready?.() === true, FRAME, {timeout: 20000});
};
// the operator's readout: Settings, the developer counters, Refresh counters
async function counters(page, {navigate = true} = {}) {
  if (navigate) await nav(page, 'settings');
  await page.waitForSelector('[data-laplace-diagnostics]', {state: 'attached'});
  if (!await page.evaluate(() => document.querySelector('.workspace-diagnostics').open)) await page.click('.workspace-diagnostics summary');
  await page.click('.workspace-diagnostics button');
  return JSON.parse(await page.textContent('[data-laplace-diagnostics]'));
}
const frameState = page => page.evaluate(frame => {
  const view = document.querySelector(frame)?.contentWindow, doc = view?.document;
  const menu = doc?.getElementById('manuscript-context-menu');
  return {frames: document.querySelectorAll('iframe').length, ready: view?.walk?.ready?.(),
    model: view?.walk?.blocks({text: false}).map(row => row.id), dom: [...(doc?.querySelectorAll('#doc .blk[data-block]') || [])].map(node => node.dataset.block),
    menus: doc?.querySelectorAll('#manuscript-context-menu').length, items: menu ? [...menu.querySelectorAll('[role=menuitem]')].map(item => item.textContent) : [],
    disposition: menu?.dataset.disposition || null, diagnostic: JSON.parse(doc?.documentElement.dataset.passageMenu || 'null'),
    dialogs: document.querySelectorAll('dialog[open]').length};
}, FRAME);
const toolbar = page => page.evaluate(() => {
  const pressed = name => [...document.querySelectorAll('button')].find(button => button.textContent === name)?.getAttribute('aria-pressed');
  const files = [...document.querySelectorAll('select')].find(select => [...select.options].some(option => option.value.endsWith('chapters/chapter-01.tex')));
  return {write: pressed('Write'), tex: pressed('TeX'), file: files?.value || null,
    source: document.querySelector('.cm-content')?.textContent.slice(0, 15) || '', frameShown: document.querySelector('iframe')?.offsetParent !== null};
});
const button = (page, name) => page.locator('button', {hasText: new RegExp('^' + name + '$')}).first();

const owners = await startOwners();
try {
  const {page, errors} = await openShell(owners);
  const frame = page.frameLocator(FRAME);

  // E1
  await openManuscript(page);
  const first = await counters(page);
  ok(first.schema_version === 'laplace.workspace-page-counters/1', 'E1 the operator reads the shell counters from Settings');
  ok(first.manuscript_frame.generation === 1 && first.manuscript_frame.subscriptions === 9, 'E1 the frame is generation 1 with one set of 9 subscriptions');
  ok(first.dialogs_open === 0 && first.help_open === false && first.cue_open === false, 'E1 no dialog, Help or cue is open');

  // E2
  await openManuscript(page);
  let state = await frameState(page);
  const target = state.model.find(id => id.endsWith('#b3'));
  const article = `#doc .blk[data-block="${target}"]`;
  ok(!!target && JSON.stringify(state.model) === JSON.stringify(state.dom), 'E2 the model and the rendered articles agree (' + state.model.length + ' blocks)');
  for (const [label, selector] of [['article body', article + ' .blk-body'], ['article', article]]) {
    await frame.locator(selector).click({button: 'right'});
    state = await frameState(page);
    ok(state.menus === 1 && ['Edit this passage', 'Open in TeX', 'Discuss this passage'].every(name => state.items.includes(name))
      && state.diagnostic.block === target && state.diagnostic.matches === 1, 'E2 ' + label + ': the exact passage menu (' + state.items.length + ' items)');
    if (label === 'article') {await frame.locator('#manuscript-context-menu [role=menuitem]', {hasText: 'Open in TeX'}).click();}
    else await frame.locator('#manuscript-context-menu').press('Escape');
  }
  await page.waitForFunction(() => [...document.querySelectorAll('button')].find(button => button.textContent === 'TeX')?.getAttribute('aria-pressed') === 'true');
  let bar = await toolbar(page);
  ok(bar.tex === 'true' && bar.file.endsWith('chapters/chapter-01.tex') && bar.source.startsWith('\\chapter{First}'), 'E2 Open in TeX opens the exact chapter source');
  await button(page, 'Write').click();
  bar = await toolbar(page);
  ok(bar.write === 'true' && bar.frameShown, 'E2 Write returns to the manuscript frame');

  // E3
  for (let cycle = 0; cycle < 20; cycle++) {
    await nav(page, 'overview');
    await openManuscript(page);
    state = await frameState(page);
    if (state.frames !== 1 || state.menus !== 0 || state.dialogs !== 0) throw new Error('FAIL: E3 cycle ' + cycle + ' left ' + JSON.stringify(state));
  }
  ok(true, 'E3 twenty loaded Home/Manuscript switches keep one frame and leave no menu or dialog');
  const after = await counters(page);
  ok(after.manuscript_frame.generation === 1 && after.manuscript_frame.subscriptions === 9 && after.manuscript_frame.attached === 9,
    'E3 the same frame generation and one subscription set after the switches (nothing re-attached)');
  ok(after.page_listeners.active === first.page_listeners.active
    && JSON.stringify(after.page_listeners.active_by_type) === JSON.stringify(first.page_listeners.active_by_type), 'E3 the shell page listeners did not grow (' + after.page_listeners.active + ')');
  ok(after.dialogs_open === 0 && after.help_open === false, 'E3 no dialog or Help left open');

  // E4
  await openManuscript(page);
  for (const selector of [article, article + ' .blk-body']) {
    await frame.locator(selector).click({button: 'right'});
    state = await frameState(page);
    ok(state.menus === 1 && state.items.includes('Edit this passage') && state.diagnostic.matches === 1, 'E4 after the switches the same passage menu has its actions (' + selector.split(' ').at(-1) + ')');
    await frame.locator('#manuscript-context-menu').press('Escape');
  }
  await button(page, 'TeX').click();
  await page.waitForFunction(() => [...document.querySelectorAll('button')].find(button => button.textContent === 'TeX')?.getAttribute('aria-pressed') === 'true');
  bar = await toolbar(page);
  ok(bar.file.endsWith('chapters/chapter-01.tex'), 'E4 the TeX toolbar opens the chapter being read');
  await button(page, 'Write').click();
  ok((await toolbar(page)).write === 'true', 'E4 Write returns again');

  // E5
  await page.evaluate(([frame, selector]) => {document.querySelector(frame).contentDocument.querySelector(selector).dataset.block = 'chapters/chapter-01.tex#gone';}, [FRAME, article]);
  await frame.locator('#doc .blk[data-block="chapters/chapter-01.tex#gone"]').click({button: 'right'});
  state = await frameState(page);
  ok(state.disposition === 'unavailable' && JSON.stringify(state.items) === JSON.stringify(['Reload the manuscript view']), 'E5 an unmatched passage in the shell frame gets the reload disposition');
  await frame.locator('#manuscript-context-menu [role=menuitem]').click();
  await page.waitForFunction(([frame, selector]) => !!document.querySelector(frame).contentDocument.querySelector(selector), [FRAME, article]);
  state = await frameState(page);
  ok(JSON.stringify(state.model) === JSON.stringify(state.dom), 'E5 the reload restores model/DOM agreement');

  // E6
  let release;
  const held = new Promise(resolve => {release = resolve;});
  await page.route(url => url.pathname === '/walk/doc', async route => {await held; await route.continue();});
  await page.evaluate(frame => document.querySelector(frame).contentWindow.location.reload(), FRAME);
  await page.waitForFunction(frame => document.querySelector(frame)?.contentDocument?.readyState === 'complete' && !document.querySelector(frame).contentWindow.walk?.ready?.(), FRAME);
  await page.waitForTimeout(300);
  await page.evaluate(frame => {const view = document.querySelector(frame).contentWindow; view.__prevented = null;
    view.addEventListener('contextmenu', event => {view.__prevented = event.defaultPrevented;}, {once: true});}, FRAME);
  await frame.locator('body').click({button: 'right', position: {x: 640, y: 500}});
  const pending = await page.evaluate(frame => {const view = document.querySelector(frame).contentWindow;
    return {prevented: view.__prevented, menus: view.document.querySelectorAll('#manuscript-context-menu').length, ready: view.walk?.ready?.()};}, FRAME);
  ok(pending.ready === false && pending.prevented === false && pending.menus === 0, 'E6 while the document read is pending the frame keeps the browser menu (no empty popup)');
  release();
  await page.waitForFunction(frame => document.querySelector(frame)?.contentWindow?.walk?.ready?.() === true, FRAME, {timeout: 20000});
  await page.unroute(url => url.pathname === '/walk/doc');
  state = await frameState(page);
  ok(JSON.stringify(state.model) === JSON.stringify(state.dom) && state.model.includes(target), 'E6 the delayed document is adopted with model/DOM agreement');
  const reloaded = await counters(page);
  ok(reloaded.manuscript_frame.generation === 2 && reloaded.manuscript_frame.subscriptions === 9, 'E6 the reloaded frame is generation 2 with one subscription set (9), not two');
  ok(reloaded.manuscript_frame.attached === 18 && reloaded.manuscript_frame.disposed === 9, 'E6 the first generation\'s set was disposed before the second attached (18 attached, 9 disposed)');
  ok(reloaded.page_listeners.active === first.page_listeners.active, 'E6 the frame reload adds no shell page listener');
  await openManuscript(page);
  await frame.locator(article).click({button: 'right'});
  ok((await frameState(page)).items.includes('Edit this passage'), 'E6 the reloaded frame serves the passage menu');
  await frame.locator('#manuscript-context-menu').press('Escape');

  // E7
  const help = () => page.evaluate(() => {const layer = document.querySelector('[data-control="help:layer"]');
    return {layer: !!layer?.isConnected, dock: !!layer?.classList.contains('is-dock'), cue: !!document.querySelector('[data-control="help:cue"]'),
      pressed: document.querySelector('[data-guide]').getAttribute('aria-pressed'), focusGuide: document.activeElement === document.querySelector('[data-guide]'),
      focusInLayer: !!layer?.contains(document.activeElement)};});
  await page.click('[data-control="help:guide"]');
  await page.waitForSelector('[data-control="help:layer"]');
  let shown = await help();
  ok(shown.layer && shown.pressed === 'true' && shown.focusInLayer && !shown.dock, 'E7 Help opens beside the manuscript with focus in the layer');
  await page.click('[data-control="help:task"] >> nth=0');
  await page.waitForSelector('[data-control="help:cue"]');
  shown = await help();
  ok(shown.cue && !shown.layer, 'E7 a Help task starts its cue and closes the layer');
  await page.click('[data-control="help:cue"] .workspace-guide-close');
  shown = await help();
  ok(!shown.cue && shown.focusGuide, 'E7 Stop ends the cue and returns focus to Help');
  await page.setViewportSize({width: 900, height: 900});
  await page.click('[data-control="help:guide"]');
  await page.waitForSelector('[data-control="help:layer"]');
  ok((await help()).dock, 'E7 Help reopened at 900 px is docked');
  await page.setViewportSize({width: 1280, height: 900});
  await page.waitForFunction(() => !document.querySelector('[data-control="help:layer"]')?.classList.contains('is-dock'));
  ok((await help()).layer, 'E7 the open layer follows the resize back to the overlay');
  await nav(page, 'overview');
  const crossed = await counters(page);
  shown = await help();
  ok(crossed.help_open === shown.layer, 'E7 after view changes the help-open flag agrees with the layer connectivity (' + shown.layer + ')');
  ok(shown.layer && shown.pressed === 'true', 'E7 the open layer stays on the page across view changes, pressed');
  await page.click('[data-control="help:layer"] .workspace-help-close');
  await page.click('[data-control="help:guide"]');
  await page.waitForSelector('[data-control="help:layer"]');
  ok((await help()).layer, 'E7 one Help press after the view changes opens Help (never closes an invisible layer)');
  // a layer removed by another owner (as a failed project load replaces the whole main area) reads as closed
  await page.evaluate(() => document.querySelector('[data-control="help:layer"]').remove());
  ok((await counters(page)).help_open === false, 'E7 a removed layer reads as closed in the help-open flag');
  await page.click('[data-control="help:guide"]');
  await page.waitForSelector('[data-control="help:layer"]');
  ok((await help()).layer, 'E7 after another owner removed the layer, one Help press opens a fresh layer');
  await page.click('[data-control="help:task"] >> nth=0');
  await page.waitForSelector('[data-control="help:cue"]');
  ok((await help()).cue, 'E7 on the long-lived page a Help task still starts its cue');
  await page.click('[data-control="help:cue"] .workspace-guide-close');
  ok(errors.length === 0, 'E1-E7 no page or console error (' + errors.slice(0, 2).join(' | ') + ')');
  await page.close();

  // E8
  let releaseAreas;
  const areasHeld = new Promise(resolve => {releaseAreas = resolve;});
  const late = await openShell(owners, page => page.route(url => url.pathname === '/authoring/help' && url.searchParams.get('view') === 'areas',
    async route => {await areasHeld; await route.continue();}));
  await openManuscript(late.page);
  const live = await counters(late.page);
  ok(live.page_listeners.active > 0 && live.manuscript_frame.subscriptions === 9, 'E8 setup: a live shell with page listeners and a frame subscription set');
  await late.page.click('[data-control="help:guide"]');
  await late.page.evaluate(() => window.laplaceWorkspace.destroy());
  releaseAreas();
  await late.page.waitForTimeout(1500);
  const gone = await counters(late.page, {navigate: false});
  const mounted = await late.page.evaluate(() => ({layer: !!document.querySelector('[data-control="help:layer"]'), cue: !!document.querySelector('[data-control="help:cue"]'),
    frames: document.querySelectorAll('iframe').length}));
  ok(!mounted.layer && !mounted.cue, 'E8 a Help import that resolves after destroy mounts nothing');
  ok(gone.page_listeners.active === 0 && gone.page_listeners.removed === gone.page_listeners.installed, 'E8 destroy removes every shell page listener (' + gone.page_listeners.removed + ')');
  ok(gone.manuscript_frame.subscriptions === 0 && gone.manuscript_frame.attached === gone.manuscript_frame.disposed && mounted.frames === 0,
    'E8 destroy disposes every frame subscription it attached (' + gone.manuscript_frame.disposed + ') and detaches the frame');
  ok(late.errors.length === 0, 'E8 no page or console error');
} finally {
  await owners.close();
}
console.log('\n' + passed + ' assertions passed');
