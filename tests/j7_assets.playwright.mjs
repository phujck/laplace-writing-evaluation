// J7 — THE ASSET SURFACE (W7 → W-ASSETS): every derivation and every figure an ADDRESSABLE
// OBJECT OF WORK. THE FAILURE RECORD's debt paid — and now joined to the ONE INSTRUMENT.
// Open /assets → the composed BRIEF → materialise the figures / derivations suites (the roster,
// per enumeration) → PIN an asset (reallocate to the close-examination cockpit, four zones,
// honest absences) → bank a STEP-anchored finding (STUBBED ledger; the anchor fields asserted
// in the intercepted POST) → the regen door ARMS then BANKS (stubbed WO store; exactly ONE
// banked row) → the deep-links land (/conceptric?node= 200; /artefact 200). Plus eigenengine:
// a hand-tikz figure card renders, the derivations stratum honestly empty (count 0, brief says so).
//
// Walked as HIM in a real Chromium against a real scanner. ASSERTED, not narrated; exit 0
// all-green, non-zero on the first failure. Both WRITE doors are STUBBED (route.fulfill).
//
//   run:  node tests/j7_assets.playwright.mjs
//   deps: global `playwright`, Chromium at /opt/pw-browsers, the repo venv python as python3.
import { createRequire } from 'module';
import { spawn, execSync } from 'child_process';
import net from 'net';
import http from 'http';

const require = createRequire(import.meta.url);
const PW_ROOT = execSync('npm root -g').toString().trim() + '/playwright';
const { chromium } = require(PW_ROOT);
const CHROME = execSync('ls /opt/pw-browsers/chromium-*/chrome-linux/chrome').toString().trim().split('\n')[0];
const PY = 'python3';
const CORPUS = 'subset-sum-itqde';

let passed = 0;
function ok(cond, msg){ if(!cond) throw new Error('ASSERT FAILED: ' + msg); passed++; console.log('  ok -', msg); }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function freePort(){ return new Promise((res, rej) => {
  const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); s.on('error', rej); }); }
function waitFor(url, tries = 60){ return new Promise((res, rej) => {
  const tick = (n) => { const req = http.get(url, (r) => { r.resume(); res(true); });
    req.on('error', () => n <= 0 ? rej(new Error('server never came up')) : setTimeout(() => tick(n - 1), 250)); }; tick(tries); }); }
function status(port, p){ return new Promise((res) => {
  http.get(`http://127.0.0.1:${port}${p}`, (r) => { r.resume(); res(r.statusCode); }).on('error', () => res(0)); }); }

// pin an asset via the engine grammar: brief → materialise its suite → click the card → reallocate.
async function pinAsset(pg, kind, assetId) {
  await pg.click(`.asb-count[data-kind="${kind}"]`);
  const sel = `.asb-mat .asb-cards .asb-card[data-asset="${assetId}"]`;
  await pg.waitForSelector(sel, { timeout: 8000 });
  await pg.$eval(sel, (e) => e.click());
  await pg.waitForSelector('.eng-focus .dk-cockpit .dk-zone', { timeout: 8000 });
}

let scanner;
(async () => {
  const repoRoot = execSync(`${PY} -c "from laplace.web.scanner import _repo_root; print(_repo_root().resolve())"`).toString().trim();
  const port = await freePort();
  scanner = spawn(PY, ['-m', 'laplace.web.scanner', '--port', String(port)], { cwd: repoRoot, stdio: 'ignore' });
  await waitFor(`http://127.0.0.1:${port}/`);

  const b = await chromium.launch({ executablePath: CHROME });
  try {
    const pg = await b.newPage({ viewport: { width: 1400, height: 900 } });
    const pageErrors = []; pg.on('pageerror', (e) => pageErrors.push(String(e)));

    // STUB BOTH WRITE DOORS — the walk exercises the client contract, never the real stores.
    const assessPosts = [];
    const regenPosts = [];
    await pg.route('**/assets/assess*', (route) => {
      const req = route.request();
      if (req.method() === 'POST') { try { assessPosts.push(JSON.parse(req.postData() || '{}')); } catch (e) { assessPosts.push({}); } }
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, record: { id: 'FB-STUB-J7' } }) });
    });
    await pg.route('**/assets/regen*', (route) => {
      const req = route.request();
      if (req.method() === 'POST') { try { regenPosts.push(JSON.parse(req.postData() || '{}')); } catch (e) { regenPosts.push({}); } }
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, banked: true, work_order: { id: 'WO-STUB-J7', action: 'regen-asset' } }) });
    });

    // ── 1. open /assets → the composed BRIEF → both suites materialise as strata of CARDS ──
    console.log(`\n[j7] open /assets?corpus=${CORPUS}`);
    await pg.goto(`http://127.0.0.1:${port}/assets?corpus=${CORPUS}`, { waitUntil: 'networkidle' });
    await pg.waitForSelector('[data-role="brief-prose"]', { timeout: 15000 });
    const figChipN = Number((await pg.textContent('.asb-count[data-kind="figures"] .asb-cn')).trim());
    const derChipN = Number((await pg.textContent('.asb-count[data-kind="derivations"] .asb-cn')).trim());
    ok(figChipN > 0 && derChipN > 0, `the brief carries both suites as count chips (figures ${figChipN}, derivations ${derChipN})`);
    // materialise the figures suite → py-script figure CARDS
    await pg.click('.asb-count[data-kind="figures"]');
    await pg.waitForSelector('.asb-mat .asb-cards .asb-card', { timeout: 8000 });
    const figCards = await pg.$$eval('.asb-mat .asb-cards .asb-card', els => els.map(e => ({
      id: e.getAttribute('data-asset'),
      kind: (e.querySelector('.dk-cls') || {}).textContent || '',
      prod: (e.querySelector('.hy-chip') || {}).textContent || '',
    })));
    ok(figCards.length === figChipN, `MATERIALISE equals enumeration — the figures chip (${figChipN}) opened exactly ${figCards.length} cards`);
    const pyFig = figCards.find(c => c.kind === 'figure' && c.prod === 'py-script');
    ok(pyFig != null, `a py-script figure CARD renders (${pyFig && pyFig.id})`);
    // materialise the derivations suite → a WK-derivation CARD
    await pg.click('.asb-count[data-kind="derivations"]');
    await pg.waitForSelector('.asb-mat .asb-cards .asb-card', { timeout: 8000 });
    const derCards = await pg.$$eval('.asb-mat .asb-cards .asb-card', els => els.map(e => ({
      id: e.getAttribute('data-asset'), kind: (e.querySelector('.dk-cls') || {}).textContent || '',
    })));
    const derCard = derCards.find(c => c.kind === 'derivation');
    ok(derCard != null, `a WK-derivation CARD renders (${derCard && derCard.id})`);

    // ── 2. PIN a FIGURE cockpit → four zones + honest absences ──
    const FIG = 'figure:F1_staircase';
    await pinAsset(pg, 'figures', FIG);
    const zones = await pg.$$eval('.eng-focus .dk-cockpit .dk-zone', els => els.length);
    ok(zones === 4, `the figure cockpit renders the FOUR fixed zones in the reallocated focus (${zones})`);
    const hasImg = await pg.$('.eng-focus .zone-context img.as-fig');
    ok(hasImg !== null, 'CONTEXT renders the rendered figure image (served via /assets/render)');
    // F1_staircase carries no nodemap landing → landings absent, stated honestly (never a fake)
    const linksText = await pg.$eval('.eng-focus .zone-deeplinks .dk-links', e => e.innerText);
    ok(/no landings/i.test(linksText), `DEEP-LINKS states the honest landing absence: ${JSON.stringify(linksText.slice(0,60))}`);
    const conseq = await pg.$eval('.eng-focus .zone-consequences', e => e.innerText);
    ok(/regen/i.test(conseq), 'CONSEQUENCES names what a regen would rebuild');
    // the named return door is present (the reallocation carries its return)
    ok(/back to the brief/i.test((await pg.textContent('[data-role="return-door"] .rd-label')).trim()),
      'the reallocated figure carries the named return door back to the brief');

    // ── 3. PIN the DERIVATION cockpit → steps listed → bank a STEP-anchored finding ──
    await pg.keyboard.press('Escape'); await sleep(250);      // close the figure back to the brief
    await pinAsset(pg, 'derivations', derCard.id);
    const nSteps = await pg.$$eval('.eng-focus .zone-context .as-step', els => els.length);
    ok(nSteps > 0, `CONTEXT lists the derivation's step anchors (${nSteps})`);
    await pg.selectOption('.eng-focus #as-anchor', { index: 0 });
    const stepId = await pg.$eval('.eng-focus #as-anchor', e => e.value);
    ok(stepId && stepId.length > 0, `a STEP anchor is selectable (${stepId})`);
    await pg.fill('.eng-focus #as-comment', 'J7 walk: the shift is absorbed incorrectly at this step.');
    await pg.click('.eng-focus #as-bank');
    await pg.waitForFunction(() => /banked/i.test((document.querySelector('.eng-focus #as-bank-msg') || {}).textContent || ''), { timeout: 8000 });
    ok(assessPosts.length === 1, `exactly one assess POST fired (${assessPosts.length})`);
    const ap = assessPosts[0] || {};
    const aa = (ap.anchor || {}).asset || {};
    ok(aa.asset_id === derCard.id, `the intercepted finding carries its ASSET anchor (asset_id=${aa.asset_id})`);
    ok(aa.step_id === stepId, `the intercepted finding carries its STEP anchor (step_id=${aa.step_id})`);
    ok(aa.kind === 'derivation', `the asset anchor names the kind (${aa.kind})`);
    ok((ap.node_id || '').length > 0 && (ap.comment || '').length > 0, 'the banked finding carries a node_id + comment (feedback_add contract)');

    // ── 4. the REGEN door ARMS then BANKS — offer law made visible (manifest-only) ──
    await pg.keyboard.press('Escape'); await sleep(250);
    await pinAsset(pg, 'figures', FIG);
    await pg.waitForSelector('.eng-focus #as-regen', { timeout: 8000 });
    await pg.click('.eng-focus #as-regen');                     // ARM ONLY — no POST yet
    await pg.waitForTimeout(150);
    ok(regenPosts.length === 0, `arming the regen fired NO work-order (offer-never-fire; ${regenPosts.length})`);
    const armed = await pg.$eval('.eng-focus #as-regen', e => /click again/i.test(e.textContent || ''));
    ok(armed, 'the regen button ARMS (states its consequence, awaits a second click)');
    await pg.click('.eng-focus #as-regen');                     // 2nd click FIRES → BANKS
    await pg.waitForFunction(() => /banked/i.test((document.querySelector('.eng-focus #as-regen-msg') || {}).textContent || ''), { timeout: 8000 });
    ok(regenPosts.length === 1, `the regen banks EXACTLY ONE work-order row (${regenPosts.length})`);
    const rp = regenPosts[0] || {};
    ok(rp.asset_id === FIG && (rp.by || '').length > 0, `the banked WO row is well-formed (asset_id=${rp.asset_id}, by=${rp.by})`);

    // ── 5. the DEEP-LINKS land: /conceptric?node= 200 with focus; /artefact 200 ──
    const nodeHref = await pg.$eval('.eng-focus .zone-deeplinks .dk-links', e => {
      const a = [...e.querySelectorAll('a')].find(x => /\/conceptric\?node=/.test(x.getAttribute('href') || ''));
      return a ? a.getAttribute('href') : null;
    });
    ok(nodeHref && /node=/.test(nodeHref), `a supported node deep-links into /conceptric with focus (${nodeHref})`);
    ok(await status(port, nodeHref) === 200, 'the /conceptric?node= deep-link serves 200');
    const editHref = await pg.$eval('.eng-focus .zone-tools a.compose', e => e.getAttribute('href'));
    ok(editHref && /\/artefact\?/.test(editHref), `the banked-edit door deep-links into /artefact (${editHref})`);
    ok(await status(port, editHref) === 200, 'the /artefact edit-door deep-link serves 200');

    // ── 6. eigenengine: a tikz figure card renders; the derivations stratum honestly empty ──
    console.log(`\n[j7] open /assets?corpus=eigenengine`);
    await pg.goto(`http://127.0.0.1:${port}/assets?corpus=eigenengine`, { waitUntil: 'networkidle' });
    await pg.waitForSelector('[data-role="brief-prose"]', { timeout: 15000 });
    const eigDerChip = Number((await pg.textContent('.asb-count[data-kind="derivations"] .asb-cn')).trim());
    ok(eigDerChip === 0, `eigenengine's derivations stratum is honestly empty (chip count ${eigDerChip})`);
    const eigDerEmpty = await pg.$eval('.asb-count[data-kind="derivations"]', e => e.classList.contains('is-empty'));
    ok(eigDerEmpty, 'the empty derivations chip is marked is-empty (nothing to materialise — never a fabricated card)');
    const eigProse = (await pg.textContent('[data-role="brief-prose"]')).trim();
    ok(/figures?/i.test(eigProse) && !/derivation/i.test(eigProse),
      `the brief names only figures for eigenengine (honest emptiness, never a fake): ${JSON.stringify(eigProse.slice(0, 70))}`);
    await pg.click('.asb-count[data-kind="figures"]');
    await pg.waitForSelector('.asb-mat .asb-cards .asb-card', { timeout: 8000 });
    const eigFigCards = await pg.$$eval('.asb-mat .asb-cards .asb-card', els => els.map(e => (e.querySelector('.hy-chip') || {}).textContent || ''));
    ok(eigFigCards.some(p => p === 'hand-tikz'), 'eigenengine renders a hand-tikz figure card');

    ok(pageErrors.length === 0, `no page errors across the run (${JSON.stringify(pageErrors)})`);
    console.log(`\nALL GREEN — ${passed} assertions`);
  } finally {
    await b.close();
    if (scanner) scanner.kill();
  }
})().catch((e) => { console.error('\n' + e.message); if (scanner) scanner.kill(); process.exit(1); });
