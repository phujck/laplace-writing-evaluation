// The W0.3 store-model Playwright harness — the ONE client model (store.mjs) driven in
// a real browser. The repo's python-playwright smoke auto-skips where the package is
// absent; this Node driver loads the REAL /shared/store.mjs served by the scanner and
// exercises the contract against the globally-installed playwright + preinstalled
// Chromium (/opt/pw-browsers), so the model is proven green with a real command + exit
// code.
//
//   run:  node tests/store_model.playwright.mjs
//   deps: resolvable `playwright` + its managed Chromium, the repo venv python on PATH
//         as python3. Exits 0 all-green, non-zero on first failure.
//
// A minimal smoke page (served via page.route, SAME origin as the scanner so the ESM
// import of /shared/store.mjs is same-origin) imports the model and publishes it. The
// contract clauses proven: (1) init from URL params; (2) set() writes the URL + pushes
// history; (3) the full Aisthesis selection moves atomically while unknown params survive;
// (4) popstate round-trips; (5) fetchJSON injects corpus, never Aisthesis selection unless
// explicitly requested.
import { createRequire } from 'module';
import { spawn } from 'child_process';
import { fileURLToPath } from 'url';
import { dirname, resolve } from 'path';
import net from 'net';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const CHROME = chromium.executablePath();
const PY = 'python3';

let passed = 0;
function ok(cond, msg) {
  if (!cond) throw new Error('ASSERT FAILED: ' + msg);
  passed++; console.log('  ok -', msg);
}
function freePort() {
  return new Promise((res, rej) => {
    const s = net.createServer();
    s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); });
    s.on('error', rej);
  });
}
function waitFor(url, tries = 60) {
  return new Promise((res, rej) => {
    const tick = (n) => {
      const req = require('http').get(url, (r) => { r.resume(); res(true); });
      req.on('error', () => n <= 0 ? rej(new Error('server never came up')) : setTimeout(() => tick(n - 1), 250));
    };
    tick(tries);
  });
}

// the minimal smoke page — imports the model, publishes it, records notifications.
const SMOKE = `<!doctype html><meta charset="utf-8"><title>store smoke</title>
<script type="module">
  import store from "/shared/store.mjs";
  window.__store = store;
  window.__notifs = [];
  store.subscribe((s) => window.__notifs.push(s));
  window.__ready = true;
</script>`;

let scanner;
(async () => {
  const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
  const port = await freePort();
  scanner = spawn(PY, ['-m', 'laplace.web.scanner', '--port', String(port)],
    { cwd: repoRoot, stdio: 'ignore', env: { ...process.env, PYTHONPATH: resolve(repoRoot, 'src') } });
  await waitFor(`http://127.0.0.1:${port}/shared/store.mjs`);

  const b = await chromium.launch({ executablePath: CHROME });
  try {
    const pg = await b.newPage({ viewport: { width: 1000, height: 700 } });
    const pageErrors = [];
    pg.on('pageerror', (e) => pageErrors.push(String(e)));

    // the smoke page (same origin as the scanner → same-origin ESM import of store.mjs).
    await pg.route('**/__smoke*', (route) =>
      route.fulfill({ status: 200, contentType: 'text/html; charset=utf-8', body: SMOKE }));
    // an echo endpoint: fulfils JSON naming the request URL, so fetchJSON injection is observable.
    await pg.route('**/__echo*', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ echoedUrl: route.request().url() }) }));

    // ── (1) INIT FROM URL PARAMS ─────────────────────────────────────────────
    await pg.goto(`http://127.0.0.1:${port}/__smoke?corpus=alpha&node=S1&project=proj1&lens=programme&edge=sha256%3A${'1'.repeat(64)}&outside=preserved`,
      { waitUntil: 'domcontentloaded' });
    await pg.waitForFunction(() => window.__ready === true, {}, { timeout: 10000 });
    const init = await pg.evaluate(() => window.__store.get());
    ok(init.project === 'proj1', `project initialised from ?project= (got ${JSON.stringify(init.project)})`);
    ok(init.selection.corpus === 'alpha', `selection.corpus initialised from ?corpus= (got ${JSON.stringify(init.selection.corpus)})`);
    ok(init.selection.node === 'S1', `selection.node initialised from ?node= (got ${JSON.stringify(init.selection.node)})`);
    ok(init.selection.lens === 'programme', `selection.lens initialised from ?lens= (got ${JSON.stringify(init.selection.lens)})`);
    ok(init.selection.edge === `sha256:${'1'.repeat(64)}`, `selection.edge initialised from ?edge= (got ${JSON.stringify(init.selection.edge)})`);
    const first = await pg.evaluate(() => window.__store.firstSelection());
    ok(first.key === 'node' && first.val === 'S1', `lens/edge leave firstSelection precedence unchanged (got ${JSON.stringify(first)})`);
    ok(init.decision === null, 'an unset param is null, not "" (no empty-param lie)');

    // ── (2) set() WRITES THE URL + PUSHES HISTORY ────────────────────────────
    const afterSet = await pg.evaluate(() => {
      const before = history.length;
      window.__store.set({ round: 'r3' });
      return { search: location.search, hist: history.length, before, state: window.__store.get() };
    });
    ok(/(^|[?&])round=r3([&]|$)/.test(afterSet.search), `set() wrote round=r3 to the URL (got ${afterSet.search})`);
    ok(afterSet.state.selection.round === 'r3', 'set() updated the in-memory model');
    ok(afterSet.hist === afterSet.before + 1, `set() pushed ONE history entry (${afterSet.before} → ${afterSet.hist})`);
    ok(/corpus=alpha/.test(afterSet.search), 'the prior params survive the set (merge, not replace)');
    ok(/outside=preserved/.test(afterSet.search), 'an unknown query param survives the canonical store write');

    // a replace:true set does NOT grow history (still canonical, no new entry).
    const afterReplace = await pg.evaluate(() => {
      const before = history.length;
      window.__store.set({ beat: 'b7' }, { replace: true });
      return { hist: history.length, before, search: location.search };
    });
    ok(afterReplace.hist === afterReplace.before, `set({replace:true}) added NO history entry (${afterReplace.before} → ${afterReplace.hist})`);
    ok(/beat=b7/.test(afterReplace.search), 'the replace set still wrote the URL');

    // Establish an exact prior Continuity selection without adding a history entry. It
    // also proves Continuity uses focus and clears the legacy node coordinate.
    const priorContinuity = await pg.evaluate(() => {
      const before = history.length;
      window.__store.set({
        lens: 'continuity',
        focus: 'turn:prior',
        edge: `sha256:${'1'.repeat(64)}`,
        grade: 'far',
        exposition: 'E0',
      }, { replace: true });
      return {
        before,
        hist: history.length,
        search: location.search,
        state: window.__store.get(),
        first: window.__store.firstSelection(),
      };
    });
    ok(priorContinuity.hist === priorContinuity.before,
      'preparing the prior Continuity selection with replace adds no history entry');
    ok(priorContinuity.state.selection.node === null
      && priorContinuity.state.selection.focus === 'turn:prior',
      'Continuity uses focus and atomically clears legacy node');
    ok(priorContinuity.first.key === 'beat' && priorContinuity.first.val === 'b7',
      `focus leaves firstSelection precedence unchanged (got ${JSON.stringify(priorContinuity.first)})`);
    ok(!/[?&]node=/.test(priorContinuity.search),
      'the canonical Continuity URL carries no legacy node parameter');

    // One deliberate Aisthesis interaction is one URL/history/notification transition.
    const afterAisthesisSet = await pg.evaluate(() => {
      window.__notifs.length = 0;
      const before = history.length;
      window.__store.set({
        lens: 'continuity',
        focus: 'turn:current',
        edge: `sha256:${'2'.repeat(64)}`,
        grade: 'near',
        exposition: 'E3',
      });
      return {
        hist: history.length,
        before,
        search: location.search,
        state: window.__store.get(),
        notifications: window.__notifs.length,
      };
    });
    ok(afterAisthesisSet.hist === afterAisthesisSet.before + 1,
      `atomic Continuity set pushed ONE history entry (${afterAisthesisSet.before} → ${afterAisthesisSet.hist})`);
    ok(afterAisthesisSet.notifications === 1,
      `atomic Continuity set emitted ONE notification (got ${afterAisthesisSet.notifications})`);
    ok(afterAisthesisSet.state.selection.lens === 'continuity'
      && afterAisthesisSet.state.selection.focus === 'turn:current'
      && afterAisthesisSet.state.selection.edge === `sha256:${'2'.repeat(64)}`
      && afterAisthesisSet.state.selection.grade === 'near'
      && afterAisthesisSet.state.selection.exposition === 'E3',
      'the one notification snapshot carries lens, focus, edge, grade and exposition together');
    ok(/outside=preserved/.test(afterAisthesisSet.search),
      'the atomic Continuity write preserves an unknown query param');

    // Back restores every member of the prior Continuity selection in one popstate notify.
    await pg.evaluate(() => { window.__notifs.length = 0; history.back(); });
    await pg.waitForFunction(() => window.__notifs.length > 0, {}, { timeout: 5000 });
    const afterAisthesisBack = await pg.evaluate(() => ({
      state: window.__store.get(),
      search: location.search,
      notifications: window.__notifs.length,
    }));
    ok(afterAisthesisBack.state.selection.lens === 'continuity'
      && afterAisthesisBack.state.selection.focus === 'turn:prior'
      && afterAisthesisBack.state.selection.edge === `sha256:${'1'.repeat(64)}`
      && afterAisthesisBack.state.selection.grade === 'far'
      && afterAisthesisBack.state.selection.exposition === 'E0',
      'Back restored lens, focus, edge, grade and exposition together');
    ok(afterAisthesisBack.notifications === 1,
      `Back emitted ONE notification for the restored pair (got ${afterAisthesisBack.notifications})`);
    ok(/outside=preserved/.test(afterAisthesisBack.search),
      'the unknown query param survives the Back restoration');

    // A switch away from Continuity clears its focus, edge and exposition in the SAME
    // store/history/notification transition. Grade is the shared semantic altitude.
    const incompatibleSwitch = await pg.evaluate(() => {
      window.__notifs.length = 0;
      const before = history.length;
      const pushState = history.pushState;
      let pushes = 0;
      history.pushState = function (...args) {
        pushes += 1;
        return pushState.apply(this, args);
      };
      try {
        window.__store.set({ lens: 'programme' });
      } finally {
        history.pushState = pushState;
      }
      return {
        before,
        hist: history.length,
        pushes,
        state: window.__store.get(),
        search: location.search,
        notifications: window.__notifs.length,
      };
    });
    ok(incompatibleSwitch.state.selection.lens === 'programme'
      && incompatibleSwitch.state.selection.focus === null
      && incompatibleSwitch.state.selection.edge === null
      && incompatibleSwitch.state.selection.exposition === null,
      'switching to an incompatible lens atomically clears Continuity focus, edge and exposition');
    ok(incompatibleSwitch.state.selection.grade === 'far',
      'switching away from Continuity preserves the shared semantic grade');
    ok(incompatibleSwitch.pushes === 1 && incompatibleSwitch.notifications === 1,
      `incompatible Continuity clearing uses ONE pushState and ONE notification `
      + `(pushes ${incompatibleSwitch.pushes}; notifications ${incompatibleSwitch.notifications})`);
    ok(!/[?&](?:focus|edge|exposition)=/.test(incompatibleSwitch.search),
      'the incompatible Continuity selection is absent from the same canonical URL transition');

    // ── (3) popstate ROUND-TRIP ──────────────────────────────────────────────
    await pg.evaluate(() => { window.__notifs.length = 0; window.__store.set({ version: 'v2' }); });
    const beforeBack = await pg.evaluate(() => window.__store.get());
    ok(beforeBack.selection.version === 'v2', 'version pushed before the back()');
    await pg.evaluate(() => history.back());
    await pg.waitForFunction(() => window.__notifs.length > 0, {}, { timeout: 5000 });
    const afterBack = await pg.evaluate(() => ({ state: window.__store.get(), search: location.search }));
    ok(afterBack.state.selection.version === null, `back() dropped version (popstate re-read the URL; got ${JSON.stringify(afterBack.state.selection.version)})`);
    ok(afterBack.state.selection.round === 'r3', 'back() restored the prior model (round=r3 survives)');
    ok(!/version=v2/.test(afterBack.search), `the URL no longer carries version after back (got ${afterBack.search})`);

    // ── (4) fetchJSON INJECTS THE CORPUS ─────────────────────────────────────
    const echoed = await pg.evaluate(async () => (await window.__store.fetchJSON('/__echo')).echoedUrl);
    ok(/[?&]corpus=alpha([&]|$)/.test(echoed), `fetchJSON injected the corpus into the request (got ${echoed})`);
    ok(!/[?&](?:focus|grade|exposition|lens|edge)=/.test(echoed),
      `fetchJSON did NOT inject Aisthesis selection by default (got ${echoed})`);
    // an explicit param rides alongside the injected corpus.
    const echoed2 = await pg.evaluate(async () =>
      (await window.__store.fetchJSON('/__echo', { params: { round: 'r9' } })).echoedUrl);
    ok(/corpus=alpha/.test(echoed2) && /round=r9/.test(echoed2), `opts.params ride with the injected corpus (got ${echoed2})`);
    const echoed3 = await pg.evaluate(async () => {
      window.__store.set({ lens: 'evidence-descent', edge: `sha256:${'4'.repeat(64)}` }, { replace: true });
      return (await window.__store.fetchJSON('/__echo', { inject: ['corpus', 'lens', 'edge'] })).echoedUrl;
    });
    ok(/corpus=alpha/.test(echoed3) && /lens=evidence-descent/.test(echoed3)
      && /edge=sha256%3A4{64}/.test(echoed3),
      `an explicit inject carries lens and edge through the same fetch gateway (got ${echoed3})`);

    // Invalid bounded enums are cleared rather than serialized into canonical state.
    const invalidEnums = await pg.evaluate(() => {
      window.__store.set({
        lens: 'continuity', focus: 'turn:validated',
        grade: 'close', exposition: 'E8', edge: `sha256:${'5'.repeat(64)}`,
      });
      return { state: window.__store.get(), search: location.search };
    });
    ok(invalidEnums.state.selection.focus === 'turn:validated'
      && invalidEnums.state.selection.grade === null
      && invalidEnums.state.selection.exposition === null,
      'grade and exposition accept only far|mid|near|audit and E0-E7');
    ok(!/[?&](?:grade=close|exposition=E8)(?:[&]|$)/.test(invalidEnums.search),
      'invalid grade and exposition never enter the canonical URL');

    ok(pageErrors.length === 0, `no page errors across the run (${JSON.stringify(pageErrors)})`);
    console.log(`\nALL GREEN — ${passed} assertions`);
  } finally {
    await b.close();
    if (scanner) scanner.kill();
  }
})().catch((e) => { console.error('\n' + e.message); if (scanner) scanner.kill(); process.exit(1); });
