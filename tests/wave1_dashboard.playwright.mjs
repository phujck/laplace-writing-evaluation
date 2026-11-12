// WAVE 1 — THE DASHBOARD, driven in a real browser against a real scanner. Proves the
// mock + DESIGN §2.1 contract on the LIVE registry: two tiers, the primary door DERIVED
// per state (recover ≠ resume ≠ run), expand-in-place with no hitbox motion in the
// pointer's row (L3), the scaffold empty-state door, the D16 rule capture that banks a
// typed fork, and the 375px single-column floor.
//
//   run:  node tests/wave1_dashboard.playwright.mjs
//   deps: global `playwright`, Chromium at /opt/pw-browsers, the repo venv python as
//         python3. Exits 0 all-green, non-zero on the first failure.
//
// The D16 bank POST is INTERCEPTED (fulfilled with a canned record) so the walk proves
// the client wiring + the typed fork payload WITHOUT writing to the real friction ledger.
import { createRequire } from 'module';
import { spawn, execSync } from 'child_process';
import net from 'net';
import http from 'http';

const require = createRequire(import.meta.url);
const PW_ROOT = execSync('npm root -g').toString().trim() + '/playwright';
const { chromium } = require(PW_ROOT);
const CHROME = execSync('ls /opt/pw-browsers/chromium-*/chrome-linux/chrome').toString().trim().split('\n')[0];
const PY = 'python3';

let passed = 0;
function ok(cond, msg){ if(!cond) throw new Error('ASSERT FAILED: ' + msg); passed++; console.log('  ok -', msg); }
function freePort(){ return new Promise((res, rej) => {
  const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); s.on('error', rej); }); }
function waitFor(url, tries = 60){ return new Promise((res, rej) => {
  const tick = (n) => { const req = http.get(url, (r) => { r.resume(); res(true); });
    req.on('error', () => n <= 0 ? rej(new Error('server never came up')) : setTimeout(() => tick(n - 1), 250)); }; tick(tries); }); }
function get(port, path){ return new Promise((res, rej) => {
  http.get(`http://127.0.0.1:${port}${path}`, (r) => { let b = ''; r.on('data', d => b += d); r.on('end', () => res({ status: r.statusCode, body: b })); }).on('error', rej); }); }

let scanner;
(async () => {
  const repoRoot = execSync(`${PY} -c "from laplace.web.scanner import _repo_root; print(_repo_root().resolve())"`).toString().trim();
  const port = await freePort();
  const base = `http://127.0.0.1:${port}`;
  scanner = spawn(PY, ['-m', 'laplace.web.scanner', '--port', String(port)], { cwd: repoRoot, stdio: 'ignore' });
  await waitFor(`${base}/`);

  // the live registry truth the cards must reflect + the derived primary doors
  const data = JSON.parse((await get(port, '/dashboard/data')).body);
  const byName = Object.fromEntries(data.projects.map(p => [p.name, p]));
  const liveNames = data.projects.filter(p => p.live).map(p => p.name);
  const scafNames = data.projects.filter(p => !p.live).map(p => p.name);
  ok(liveNames.length >= 2 && scafNames.length >= 1, `roster has a live tier (${liveNames.length}) and a scaffold tier (${scafNames.length})`);

  const b = await chromium.launch({ executablePath: CHROME });
  try {
    const pg = await b.newPage({ viewport: { width: 1400, height: 900 } });
    const pageErrors = []; pg.on('pageerror', (e) => pageErrors.push(String(e)));

    await pg.goto(`${base}/`, { waitUntil: 'domcontentloaded' });
    await pg.waitForSelector('.dash-live .hy-card[data-project]', { timeout: 10000 });

    // ── (1) TWO TIERS render, distinct ───────────────────────────────────────
    const liveDom = await pg.$$eval('.dash-live .hy-card[data-project]', els => els.map(e => e.getAttribute('data-project')));
    const scafDom = await pg.$$eval('.dash-shelf .hy-card[data-project]', els => els.map(e => e.getAttribute('data-project')));
    ok(liveDom.length === liveNames.length && liveNames.every(n => liveDom.includes(n)),
      `TIER 1 renders every live paper (${liveDom.length})`);
    ok(scafDom.length === scafNames.length && scafNames.every(n => scafDom.includes(n)),
      `TIER 2 renders every scaffold on the shelf (${scafDom.length})`);
    ok(await pg.$('.dash-shelf #newproj') !== null, 'the "+ new project" door is a card at the shelf end (D12)');

    // ── (2) THE PRIMARY DOOR DIFFERS PER STATE (R2) — the machine's ACTUAL next
    // move, derived per project. A queued RESPINE ruling BEATS the state-family move
    // (the truth-layer override the client documents: falqon's "run" lie dies, a
    // converging paper with an open RESPINE offers "rule the RESPINE" first). The live
    // roster exercises three genuinely different derived doors: recover, RESPINE, run.
    async function primary(name){
      return pg.$eval(`.hy-card[data-project="${name}"] a.hy-door.is-primary`,
        a => ({ label: a.textContent.trim(), href: a.getAttribute('href') }));
    }
    const respineOf = p => ((p.verdict || {}).generations || {}).respine_intent;
    // pick one project per derived move from server truth (RESPINE-carrying beats its family)
    const respineP = data.projects.find(p => p.live && respineOf(p));
    const recoverP = data.projects.find(p => p.live && !respineOf(p) && p.primary && p.primary.kind === 'recover');
    const runP = data.projects.find(p => p.live && !respineOf(p) && p.primary && p.primary.kind === 'run');
    ok(recoverP && respineP && runP,
      `the roster exercises three derived moves (recover=${recoverP && recoverP.name}, RESPINE=${respineP && respineP.name}, run=${runP && runP.name})`);
    const dR = await primary(recoverP.name), dRes = await primary(respineP.name), dRun = await primary(runP.name);
    ok(/recover/.test(dR.label) && /^\/desk\?wo=/.test(dR.href),
      `${recoverP.name}: primary door RECOVERS to the banked order (${JSON.stringify(dR)})`);
    ok(/RESPINE/.test(dRes.label) && dRes.href === respineOf(respineP).href,
      `${respineP.name}: an open RESPINE ruling BEATS resume — primary door rules the RESPINE (${JSON.stringify(dRes)})`);
    ok(/run/.test(dRun.label) && /^\/pipeline\?project=/.test(dRun.href),
      `${runP.name}: primary door RUNS the release machine (${JSON.stringify(dRun)})`);
    ok(dR.label !== dRes.label && dRes.label !== dRun.label && dR.label !== dRun.label,
      'the three primary doors are genuinely different (never constant-per-family)');
    // the RESPINE card still OFFERS its demoted state move (resume convergence → /pipeline),
    // beside the primary RESPINE ruling — the forward move is demoted, never dropped.
    const demoted = await pg.$$eval(`.hy-card[data-project="${respineP.name}"] a.hy-door:not(.is-primary)`,
      els => els.map(a => ({ label: a.textContent.trim(), href: a.getAttribute('href') })));
    ok(demoted.some(d => /resume/.test(d.label) && /^\/pipeline\?project=/.test(d.href)),
      `${respineP.name}: the demoted state move (resume convergence → /pipeline) is still offered beside the RESPINE ruling`);
    // the recover card wears the warn is-offer absent chip revealing the recover route (D7)
    const offer = await pg.$(`.hy-card[data-project="${recoverP.name}"] .hy-chip.is-offer`);
    ok(offer !== null, `${recoverP.name}: absent release wears the warn is-offer chip (D7)`);
    await offer.click();
    const reveal = await pg.$eval(`.hy-card[data-project="${recoverP.name}"] .hy-chip-fix`, e => e.textContent);
    ok(/release-recover/.test(reveal) && /\/desk\?wo=/.test(reveal),
      `the offer REVEALS the banked order + its route, never fires (${JSON.stringify(reveal.slice(0,80))})`);

    // ── (3) EXPAND-IN-PLACE: no hitbox motion in the pointer's row (L3) ───────
    // live order is registry order; the 2-col grid puts the first two live papers in row 1.
    const a = liveDom[0], sib = liveDom[1];
    const sibBefore = await pg.$eval(`.hy-card[data-project="${sib}"]`, e => e.getBoundingClientRect().top);
    await pg.click(`.hy-card[data-project="${a}"] .hy-card-name`);
    ok(await pg.$eval(`.hy-card[data-project="${a}"]`, e => e.classList.contains('is-open')),
      `${a} expands IN PLACE on a body click`);
    const sibAfter = await pg.$eval(`.hy-card[data-project="${sib}"]`, e => e.getBoundingClientRect().top);
    ok(Math.abs(sibAfter - sibBefore) < 1,
      `${sib} (same row) did NOT move under the pointer (top ${sibBefore} → ${sibAfter}, L3)`);

    // ── (4) THE SCAFFOLD EMPTY-STATE DOOR names its fix (§3 / D11) ────────────
    const seed = await pg.$eval(`.hy-card[data-project="${scafDom[0]}"] .scaf-empty a.hy-door`,
      a => ({ text: a.textContent.trim(), href: a.getAttribute('href') }));
    ok(/seed a conception/.test(seed.text) && seed.href === `/conceptric?project=${encodeURIComponent(scafDom[0])}`,
      `the scaffold names what would fill it + a real seed door (${JSON.stringify(seed)})`);

    // ── (5) D16 — the ✎ rule capture BANKS a typed fork (POST intercepted) ────
    let banked = null;
    await pg.route('**/corpus/friction', async (route) => {
      banked = JSON.parse(route.request().postData() || '{}');
      await route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ ok: true, record: { id: 'RW-walk-0001' } }) });
    });
    const ruleCard = `.hy-card[data-project="${a}"]`;
    await pg.hover(ruleCard);
    await pg.click(`${ruleCard} .rule-chip`);
    await pg.waitForSelector(`${ruleCard} .rule-cap textarea`, { timeout: 5000 });
    await pg.fill(`${ruleCard} .rule-cap textarea`, 'the primary door should also name the round it resumes');
    await pg.click(`${ruleCard} .rule-cap .rule-bank`);
    await pg.waitForSelector(`${ruleCard} .rule-banked`, { timeout: 5000 });
    ok(banked && banked.kind === 'fork' && banked.owning_layer === 'interface',
      `the capture banks a typed fork, owning_layer=interface (${JSON.stringify(banked && banked.kind)})`);
    ok(banked && banked.node === `project:${a}`,
      `the fork names the card's project node (${JSON.stringify(banked && banked.node)})`);
    ok(await pg.$eval(`${ruleCard} .rule-banked`, e => /banked/.test(e.textContent)),
      'the capture renders "banked ✓" without leaving the surface (D16)');

    // ── (6) 375px — one column, cards stack, never a horizontal scroll (D14) ──
    await pg.setViewportSize({ width: 375, height: 800 });
    const cols = await pg.$eval('.dash-live', e => getComputedStyle(e).gridTemplateColumns);
    ok(cols.trim().split(/\s+/).length === 1, `at 375px the live grid is ONE column (got ${JSON.stringify(cols)})`);
    const noHScroll = await pg.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
    ok(noHScroll, 'no horizontal scroll at 375px (the 375px floor)');

    ok(pageErrors.length === 0, `no page errors across the run (${JSON.stringify(pageErrors)})`);
    console.log(`\nALL GREEN — ${passed} assertions`);
  } finally {
    await b.close();
    if (scanner) scanner.kill();
  }
})().catch((e) => { console.error('\n' + e.message); if (scanner) scanner.kill(); process.exit(1); });
