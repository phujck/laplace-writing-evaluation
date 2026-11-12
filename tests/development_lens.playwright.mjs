// Aisthesis: one canonical model, seven visual lenses, walked against the real scanner.
// Run: node tests/development_lens.playwright.mjs
import { createRequire } from 'module';
import { spawn, execSync } from 'child_process';
import { existsSync, mkdirSync } from 'fs';
import net from 'net';
import http from 'http';

const require = createRequire(import.meta.url);
const roots = [
  execSync('npm root -g').toString().trim() + '/playwright',
  `${process.cwd()}/node_modules/playwright`,
  `${process.cwd()}/node_modules/playwright-core`,
  '/home/phujck/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright-core',
  '/usr/lib/chatgpt/resources/cua_node/lib/node_modules/playwright-core',
];
const pwRoot = roots.find(existsSync);
if (!pwRoot) throw new Error(`Playwright is absent; searched ${roots.join(', ')}`);
const { chromium } = require(pwRoot);
const chrome = execSync("find /opt/pw-browsers \"$HOME/.cache/ms-playwright\" -type f -path '*/chrome-linux*/chrome' -print -quit 2>/dev/null || true").toString().trim();
const py = '/usr/bin/python3';
const shots = process.env.LAPLACE_SCREENSHOT_DIR || '/tmp/laplace-aisthesis-evidence';
let passed = 0;
let scanner;

function ok(condition, message) {
  if (!condition) throw new Error('ASSERT FAILED: ' + message);
  passed += 1;
  console.log('  ok -', message);
}
function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.listen(0, '127.0.0.1', () => {
      const port = server.address().port;
      server.close(() => resolve(port));
    });
    server.on('error', reject);
  });
}
function waitFor(url, tries = 100) {
  return new Promise((resolve, reject) => {
    const tick = (remaining) => {
      const request = http.get(url, (response) => { response.resume(); resolve(true); });
      request.on('error', () => remaining <= 0
        ? reject(new Error('scanner never came up'))
        : setTimeout(() => tick(remaining - 1), 250));
    };
    tick(tries);
  });
}

(async () => {
  if (!chrome) throw new Error('Chromium is absent; visual acceptance is UNPROVEN');
  mkdirSync(shots, { recursive: true });
  const repoRoot = process.cwd();
  const port = await freePort();
  const base = `http://127.0.0.1:${port}`;
  scanner = spawn(py, ['-m', 'laplace.web.scanner', '--port', String(port)], {
    cwd: repoRoot,
    env: { ...process.env, PYTHONPATH: `${repoRoot}/src`, LAPLACE_NO_PREWARM: '1', LAPLACE_TEST_PROCESS: '1' },
    stdio: 'ignore',
  });
  await waitFor(`${base}/front/development`);

  const browser = await chromium.launch({ executablePath: chrome });
  try {
    const page = await browser.newPage({ viewport: { width: 1536, height: 1000 }, reducedMotion: 'reduce' });
    const pageErrors = [];
    page.on('pageerror', (error) => pageErrors.push(String(error)));
    await page.goto(`${base}/front/development`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('#development-lens[data-ready="true"]', { timeout: 30000 });

    ok(await page.getAttribute('body', 'data-freshness') === 'CURRENT', 'fresh resting state is worded CURRENT');
    ok(await page.$$eval('.lens-tab', (items) => items.length) === 7, 'all seven lenses are visible in one score');
    ok(await page.$$eval('.lens-tab[aria-selected="true"]', (items) => items.length) === 1, 'exactly one lens is selected');
    ok((await page.textContent('#q-exists')).trim().length > 20, 'cold view answers what exists');
    ok((await page.textContent('#q-matters')).trim().length > 20, 'cold view answers what matters now');
    ok((await page.textContent('#q-blocked')).trim().length > 20, 'cold view answers what is blocked');
    ok((await page.textContent('#q-next')).trim().length > 20, 'cold view names the next admissible inspection');
    ok(/^sha256:[0-9a-f]{64}$/.test((await page.textContent('#shown-handle')).trim()), 'shown state is exact and content addressed');
    ok(/^sha256:[0-9a-f]{64}$/.test((await page.textContent('#model-handle')).trim()), 'one canonical read model is content addressed');
    ok(await page.$$eval('[data-canonical-action]', (items) => items.length) === 0, 'the first slice exposes no canonical mutation action');
    ok(await page.evaluate(() => [...document.styleSheets].some((sheet) => /\/shared\/hymn\.css/.test(sheet.href || ''))), 'the surface consumes the canonical hymn sheet');
    ok(await page.evaluate(async () => {
      const response = await fetch('/shared/continuity_loom.mjs');
      const source = await response.text();
      return response.ok && source.includes('renderContinuityLoom');
    }), 'the served carrier exposes the exact shared Continuity renderer');
    await page.screenshot({ path: `${shots}/aisthesis-programme-1536.png`, fullPage: true });

    const path = ['critical-path', 'live-custody', 'evidence-descent', 'continuity', 'residual-crutch', 'lens-self'];
    for (const id of path) {
      await page.click(`.lens-tab[data-lens="${id}"]`);
      await page.waitForFunction((value) => new URL(location.href).searchParams.get('lens') === value
        && document.querySelector(`.lens-tab[data-lens="${value}"]`)?.getAttribute('aria-selected') === 'true'
        && document.querySelector('#development-lens')?.dataset.ready === 'true', id);
      ok(await page.getAttribute(`.lens-tab[data-lens="${id}"]`, 'aria-selected') === 'true', `${id} is URL-bound and visually selected`);
    }
    await page.goBack();
    await page.waitForFunction(() => new URL(location.href).searchParams.get('lens') === 'residual-crutch' && document.querySelector('#development-lens')?.dataset.ready === 'true');
    ok(await page.getAttribute('.lens-tab[data-lens="residual-crutch"]', 'aria-selected') === 'true', 'Back restores lens state through the shared store');

    await page.focus('.lens-tab[data-lens="residual-crutch"]');
    await page.keyboard.press('ArrowRight');
    ok(await page.evaluate(() => document.activeElement?.dataset?.lens === 'lens-self'), 'keyboard arrows traverse the visual score without changing truth');

    await page.click('.lens-tab[data-lens="programme"]');
    await page.waitForFunction(() => document.querySelector('#development-lens')?.dataset.ready === 'true');
    await page.waitForSelector('.causal-weave[data-schema="laplace.aisthesis-causal-atlas-weave/1"]');
    const programmeObjects = await page.$$eval('.causal-weave__object', (items) =>
      items.map((item) => item.dataset.object));
    ok(programmeObjects.length > 0 && programmeObjects.every(Boolean),
      'Programme is a live causal field with stable object identities');
    ok(!/(?:sha256|message):[0-9a-f]{16,}/i.test(await page.textContent('.causal-weave')),
      'Programme Mid keeps exact identifiers submerged beneath human meaning');
    const programmeGroup = await page.$('.causal-weave__object[data-kind="compressed-group"]');
    ok(Boolean(programmeGroup), 'Programme Mid conserves off-attention context as a visible cut group');
    const programmeGroupHandle = await programmeGroup.getAttribute('data-object');
    await programmeGroup.click();
    await page.waitForFunction((groupHandle) => {
      const q = new URL(location.href).searchParams;
      return q.get('lens') === 'programme' && q.get('grade') === 'near'
        && q.get('focus') && q.get('focus') !== groupHandle
        && document.querySelector('#development-lens')?.dataset.ready === 'true';
    }, programmeGroupHandle);
    ok(await page.$('.causal-weave__object[data-kind="compressed-group"]') === null,
      'cut-group descent expands exact originals rather than retaining duplicate pills');
    const programmeCandidate = await page.$('.causal-weave__object:not([data-kind="compressed-group"])[aria-pressed="false"]');
    ok(Boolean(programmeCandidate), 'Programme Near offers a real object for in-place visual descent');
    const programmeFocus = await programmeCandidate.getAttribute('data-object');
    await programmeCandidate.click();
    await page.waitForFunction((handle) => {
      const q = new URL(location.href).searchParams;
      return q.get('lens') === 'programme' && q.get('focus') === handle
        && document.querySelector('#development-lens')?.dataset.ready === 'true';
    }, programmeFocus);
    ok(await page.$(`.causal-weave__object[data-object="${programmeFocus}"][aria-pressed="true"]`) !== null,
      'Programme selection expands the same semantic object in place');
    const programmeEdge = await page.$('.causal-weave__edge-hit[data-edge]');
    if (programmeEdge) {
      const edgeId = await programmeEdge.getAttribute('data-edge');
      await programmeEdge.click();
      await page.waitForFunction((id) => new URL(location.href).searchParams.get('edge') === id, edgeId);
      ok(Boolean(edgeId), 'selected relation has an exact identity independent of focus');
      await page.click('.lens-tab[data-lens="live-custody"]');
      await page.waitForFunction(() => {
        const q = new URL(location.href).searchParams;
        return q.get('lens') === 'live-custody' && !q.has('edge')
          && document.querySelector('#development-lens')?.dataset.ready === 'true';
      });
      ok(!new URL(page.url()).searchParams.has('edge'),
        'switching to an incompatible lens clears the Programme edge atomically');
    }

    // Continuity is one living causal organ over the same server-supplied model. The
    // resting face is human; exact receipts emerge only under deliberate Audit descent.
    await page.click('.lens-tab[data-lens="continuity"]');
    await page.waitForSelector('.continuity-loom[data-schema="laplace.aisthesis-continuity-loom/1"]', { timeout: 30000 });
    const servedGeometry = await page.getAttribute('.continuity-loom', 'data-geometry');
    ok(servedGeometry === 'wide', `1536px carrier uses the producer-selected wide geometry (got ${servedGeometry})`);
    ok(await page.getAttribute('.lens-tab[data-lens="continuity"]', 'aria-selected') === 'true',
      'Continuity is a camera over the shared carrier, not a separate page');
    ok(await page.$$eval('.continuity-loom__object, .continuity-loom__edge', (items) =>
      items.length > 0 && items.every((item) => item instanceof HTMLButtonElement
        && item.offsetWidth >= 28 && item.offsetHeight >= 28
        && (item.getAttribute('aria-label') || '').trim().length > 3)),
    'every visible causal object and edge is a labelled native control');
    const restingLoom = await page.textContent('.continuity-loom');
    ok(!/(?:sha256|message):[0-9a-f]{16,}/i.test(restingLoom),
      'the resting Continuity face uses human meaning rather than receipt identifiers');
    ok(await page.getAttribute('.grounds', 'hidden') !== null,
      'exact global grounds remain submerged before Audit');

    const cutGroup = await page.$('.continuity-loom__object[data-kind="compressed-group"]');
    if (cutGroup) {
      const cutSearch = new URL(page.url()).search;
      const historyBeforeCut = await page.evaluate(() => history.length);
      const groupHandle = await cutGroup.getAttribute('data-object');
      await cutGroup.click();
      await page.waitForFunction((oldHandle) => {
        const query = new URL(location.href).searchParams;
        return query.get('lens') === 'continuity' && query.get('grade') === 'near'
          && query.get('focus') && query.get('focus') !== oldHandle
          && document.querySelector('#development-lens')?.dataset.ready === 'true';
      }, groupHandle);
      ok(await page.evaluate((before) => history.length === before + 1, historyBeforeCut),
        'a cut group performs one atomic shared-history transition');
      await page.goBack();
      await page.waitForFunction((search) => location.search === search
        && document.querySelector('#development-lens')?.dataset.ready === 'true', cutSearch);
      ok(await page.$('.continuity-loom__object[data-kind="compressed-group"]') !== null,
        'Back restores the exact Mid cut and omission face');
    }

    const focusCandidate = await page.$('.continuity-loom__object[aria-pressed="false"]');
    ok(Boolean(focusCandidate), 'the live field offers a causal object for visual descent');
    const focusHandle = await focusCandidate.getAttribute('data-object');
    const beforeFocus = await focusCandidate.boundingBox();
    await focusCandidate.click();
    await page.waitForFunction((handle) => {
      const query = new URL(location.href).searchParams;
      return query.get('lens') === 'continuity' && query.get('focus') === handle
        && document.querySelector('#development-lens')?.dataset.ready === 'true';
    }, focusHandle);
    const focused = await page.$(`.continuity-loom__object[data-object="${focusHandle}"][aria-pressed="true"]`);
    const afterFocus = await focused.boundingBox();
    ok(afterFocus.width > beforeFocus.width || afterFocus.height > beforeFocus.height,
      'clicking an object expands its supplied context in place');
    ok(await page.$$eval('.continuity-loom__context .continuity-loom__exposition-grade',
      (items) => items.length === 8 && items.every((item) => item instanceof HTMLButtonElement)),
    'E0-E7 unfold around the selected object rather than in a detached help panel');

    const causalEdge = await page.$('.continuity-loom__edge');
    ok(Boolean(causalEdge), 'the live field exposes an independently selectable typed edge');
    const edgeId = await causalEdge.getAttribute('data-edge');
    await causalEdge.click();
    await page.waitForFunction((id) => new URL(location.href).searchParams.get('edge') === id
      && document.querySelector('#development-lens')?.dataset.ready === 'true', edgeId);
    ok(await page.getAttribute(`.continuity-loom__edge[data-edge="${edgeId}"]`, 'aria-pressed') === 'true',
      'typed edge selection is exact and independent of object focus');

    await page.click('.continuity-loom__grade[data-grade="audit"]');
    await page.waitForFunction(() => new URL(location.href).searchParams.get('grade') === 'audit'
      && document.querySelector('#development-lens')?.dataset.ready === 'true');
    ok(await page.getAttribute('.grounds', 'hidden') !== null,
      'global shown-state grounds remain in Lens Self even during Continuity Audit');
    ok(await page.$$eval('.continuity-loom__receipt', (items) => items.length > 0),
      'selected Audit subject reveals exact receipt descent inside its local well');
    ok(await page.$$eval('.continuity-loom__receipt', (items) =>
      items.every((item) => item.closest('.continuity-loom__audit-well'))),
      'no exact identifier escapes the selected Audit well');
    ok(!/(?:sha256:|message:)/.test(await page.$eval('.continuity-loom', (node) => {
      const clone = node.cloneNode(true);
      clone.querySelectorAll('.continuity-loom__audit-well').forEach((well) => well.remove());
      return clone.textContent;
    })), 'Audit remains human-first outside the attention-local evidence well');
    await page.click('.continuity-loom__exposition-grade[data-exposition="2"]');
    await page.waitForFunction(() => new URL(location.href).searchParams.get('exposition') === 'E2'
      && document.querySelector('#development-lens')?.dataset.ready === 'true');
    ok(await page.getAttribute('.continuity-loom__exposition-grade[data-exposition="2"]', 'aria-pressed') === 'true',
      'object-relative exposition is bound into the shared URL selection');

    const exactContinuitySearch = new URL(page.url()).search;
    await page.click('.lens-tab[data-lens="live-custody"]');
    await page.waitForFunction(() => {
      const query = new URL(location.href).searchParams;
      return query.get('lens') === 'live-custody' && !query.has('focus')
        && !query.has('edge') && !query.has('exposition')
        && document.querySelector('#development-lens')?.dataset.ready === 'true';
    });
    ok(!/[?&](?:focus|edge|exposition)=/.test(new URL(page.url()).search),
      'an incompatible camera clears Continuity focus, edge and exposition atomically');
    await page.goBack();
    await page.waitForFunction((search) => location.search === search
      && document.querySelector('#development-lens')?.dataset.ready === 'true', exactContinuitySearch);
    ok(await page.getAttribute(`.continuity-loom__object[data-object="${focusHandle}"]`, 'aria-pressed') === 'true'
      && await page.getAttribute(`.continuity-loom__edge[data-edge="${edgeId}"]`, 'aria-pressed') === 'true',
    'Back restores the exact focused topology and selected edge');
    const reducedMotionDuration = await page.$eval('.continuity-loom__object',
      (item) => getComputedStyle(item).transitionDuration);
    ok(reducedMotionDuration === '0s', `reduced motion removes geometric interpolation (got ${reducedMotionDuration})`);
    await page.screenshot({ path: `${shots}/aisthesis-continuity-1536.png`, fullPage: true });

    const storage = await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length }));
    ok(storage.local === 0 && storage.session === 0, 'no browser-local currentness or acknowledgement store is created');
    const bodyFont = await page.$eval('body', (node) => parseFloat(getComputedStyle(node).fontSize));
    ok(bodyFont >= 16, `essential body copy remains at least 16px (got ${bodyFont})`);
    await page.screenshot({ path: `${shots}/aisthesis-1536.png`, fullPage: true });

    await page.route('**/front/development?*', async (route) => {
      const url = new URL(route.request().url());
      if (url.searchParams.get('format') !== 'currentness') return route.continue();
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          schema_version: 'laplace.development-lens-currentness/1',
          state: 'STALE', actions_enabled: false,
          shown_handle: url.searchParams.get('shown_handle'),
          moved: { cursor: { served: url.searchParams.get('cursor'), live: '999999' } },
          read_only: true,
        }),
      });
    });
    await page.evaluate(() => window.dispatchEvent(new Event('development:check-currentness')));
    await page.waitForSelector('body[data-freshness="STALE"] .stale-banner', { state: 'visible' });
    ok(/last.trusted/i.test(await page.textContent('#stale-reason')), 'moved frontier becomes explicit last-trusted evidence before any action');
    await page.unroute('**/front/development?*');

    for (const [width, height, geometry] of [[768, 900, 'medium'], [375, 900, 'narrow']]) {
      await page.setViewportSize({ width, height });
      await page.goto(`${base}/front/development?lens=continuity&grade=mid&exposition=E0`, { waitUntil: 'domcontentloaded' });
      await page.waitForSelector('#development-lens[data-ready="true"]', { timeout: 30000 });
      await page.waitForSelector(`.continuity-loom[data-geometry="${geometry}"]`, { timeout: 30000 });
      const noOverflow = await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1);
      ok(noOverflow, `${width}px composition has no horizontal overflow`);
      ok(await page.$$eval('.lens-tab', (items) => items.length) === 7, `${width}px composition retains all seven lenses`);
      ok(await page.$$eval('.continuity-loom__object, .continuity-loom__edge', (items) =>
        items.length > 0 && items.every((item) => {
          const box = item.getBoundingClientRect();
          return box.width > 0 && box.height > 0 && box.left >= 0 && box.right <= innerWidth + 1;
        })), `${width}px uses a true ${geometry} causal field with every control discoverable`);
      if (width === 768) {
        ok(await page.$$eval('.continuity-loom__object,.continuity-loom__edge', (items) =>
          items.every((item) => item.scrollWidth <= item.clientWidth + 1
            && item.scrollHeight <= item.clientHeight + 1)),
        '768px preserves every human node and relation label without clipping');
        ok(await page.$$eval('.continuity-loom__edge', (edges) => edges.every((edge) => {
          const box = edge.getBoundingClientRect();
          return ![...document.querySelectorAll('.continuity-loom__object')].some((node) => {
            const other = node.getBoundingClientRect();
            return box.left < other.right && box.right > other.left
              && box.top < other.bottom && box.bottom > other.top;
          });
        })), '768px relation labels occupy a dedicated corridor without node intersections');
      }
      if (width === 375) {
        const allDiscoverable = await page.$$eval('.lens-tab', (items) => items.every((item) => {
          const box = item.getBoundingClientRect();
          return box.left >= 0 && box.right <= innerWidth + 1 && box.width > 0 && box.height > 0;
        }));
        ok(allDiscoverable, '375px composition shows every lens without horizontal gesture lore');
        ok(await page.$$eval('.continuity-loom__object,.continuity-loom__edge', (items) =>
          items.every((item) => {
            const box = item.getBoundingClientRect();
            return box.width >= 44 && box.height >= 44;
          })), '375px causal controls preserve a 44px target floor');
        ok(await page.$$eval('.continuity-loom__edge', (edges) => edges.every((edge) => {
          const box = edge.getBoundingClientRect();
          return ![...document.querySelectorAll('.continuity-loom__object')].some((node) => {
            const other = node.getBoundingClientRect();
            return box.left < other.right && box.right > other.left
              && box.top < other.bottom && box.bottom > other.top;
          });
        })), '375px relation labels occupy a dedicated lane without node collisions');
      }
      await page.screenshot({ path: `${shots}/aisthesis-continuity-${width}.png`, fullPage: true });
      await page.goto(`${base}/front/development?lens=programme&grade=mid`, { waitUntil: 'domcontentloaded' });
      await page.waitForSelector('.causal-weave[data-schema="laplace.aisthesis-causal-atlas-weave/1"]', { timeout: 30000 });
      ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
        `${width}px Programme weave has no horizontal overflow`);
      await page.screenshot({ path: `${shots}/aisthesis-programme-${width}.png`, fullPage: true });
    }

    ok(pageErrors.length === 0, `no browser page errors (${JSON.stringify(pageErrors)})`);
    console.log(`\nALL GREEN — ${passed} assertions`);
    console.log(`screenshots: ${shots}/aisthesis-{continuity,programme}-{1536,768,375}.png`);
  } finally {
    await browser.close();
    if (scanner) scanner.kill();
  }
})().catch((error) => {
  console.error('\n' + error.message);
  if (scanner) scanner.kill();
  process.exit(1);
});
