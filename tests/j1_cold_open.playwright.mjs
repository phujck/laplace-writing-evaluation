// J1 — COLD OPEN (conception §9): land on / → project cards with TRUE state → the
// one journey walked as HIM. This drives the real dashboard in a real Chromium against
// a real scanner (its own scratch port), so acceptance is ASSERTED, not narrated.
//
//   run:  node tests/j1_cold_open.playwright.mjs
//   deps: global `playwright` (npm root -g), Chromium at /opt/pw-browsers, the repo venv
//         python on PATH as python3. Exits 0 all-green, non-zero on the first failure.
//
// The dashboard reads the LIVE registry (no stubbing) — J1's whole point is that the
// cards carry the real state, so the asserts cross-check the DOM against /dashboard/data.
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
  scanner = spawn(PY, ['-m', 'laplace.web.scanner', '--port', String(port)], { cwd: repoRoot, stdio: 'ignore' });
  await waitFor(`http://127.0.0.1:${port}/`);

  // the live registry truth the cards must reflect
  const data = JSON.parse((await get(port, '/dashboard/data')).body);
  const byName = Object.fromEntries(data.projects.map(p => [p.name, p]));
  const scaffold = data.projects.find(p => p.scaffold);
  ok(byName['subset-sum-itqde'], 'the live roster carries subset-sum-itqde');
  ok(scaffold, 'the live roster carries at least one NEVER_RUN scaffold');

  const b = await chromium.launch({ executablePath: CHROME });
  try {
    const pg = await b.newPage({ viewport: { width: 1400, height: 900 } });
    const pageErrors = []; pg.on('pageerror', (e) => pageErrors.push(String(e)));

    console.log(`\n[j1] GET / (the dashboard, live registry)`);
    await pg.goto(`http://127.0.0.1:${port}/`, { waitUntil: 'domcontentloaded' });
    // W-DASH: the cold open lands on the composed BRIEF (delta-and-ask), NOT a card wall — the
    // cards are the summonable inventory behind one open. Wait for the rendered count chips
    // (present only after the brief paints), assert the brief-at-rest, then materialise.
    await pg.waitForSelector('.dash-count[data-count="projects"]', { timeout: 10000 });
    const restCards0 = await pg.$$eval('.hy-card[data-project]', els => els.length);
    ok(restCards0 === 0, 'the cold open rests on the brief — NO card grid resident at rest');
    const briefProse = (await pg.textContent('[data-role="brief-prose"]')).trim();
    ok(briefProse.length > 40, 'the composed brief prose is present at rest (the whole, delta-and-ask)');
    // OPEN THE INVENTORY — the cards materialise behind one interaction.
    await pg.click('.dash-count[data-count="projects"]');
    await pg.waitForSelector('.hy-card[data-project]', { timeout: 10000 });

    // ── cards render with REAL registry names ────────────────────────────────
    const domNames = await pg.$$eval('.hy-card[data-project]', els => els.map(e => e.getAttribute('data-project')));
    ok(domNames.length === data.projects.length,
      `every registered project is a card (dom ${domNames.length} == roster ${data.projects.length})`);
    for (const n of Object.keys(byName)) ok(domNames.includes(n), `card present for real project ${n}`);

    // ── subset-sum shows UNDER_CONVERGENCE + 5 rounds ────────────────────────
    const ssText = (await pg.$eval('.hy-card[data-project="subset-sum-itqde"]', e => e.innerText)).toLowerCase();
    ok(/under convergence/.test(ssText), `subset-sum card shows UNDER_CONVERGENCE (got: ${JSON.stringify(ssText.slice(0,120))})`);
    ok(/5 rounds?/.test(ssText), 'subset-sum card shows 5 rounds');

    // ── a NEVER_RUN scaffold is VISUALLY DISTINCT (muted class + scaffold chip) ─
    const scafCard = await pg.$(`.hy-card[data-project="${scaffold.name}"]`);
    const scafClass = await scafCard.getAttribute('class');
    ok(/\bis-muted\b/.test(scafClass), `the NEVER_RUN scaffold ${scaffold.name} is reduced-emphasis (is-muted)`);
    const scafChip = await scafCard.$('.hy-chip.is-scaffold');
    ok(scafChip !== null, 'the scaffold carries a "scaffold" chip (peer-of-real-work disease killed)');
    const liveCard = await pg.$('.hy-card[data-project="subset-sum-itqde"]');
    ok(!/\bis-muted\b/.test(await liveCard.getAttribute('class')), 'a LIVE paper is NOT muted (distinct from scaffolds)');

    // ── latest-artefact link answers 200 ─────────────────────────────────────
    const href = await pg.$eval('.hy-card[data-project="subset-sum-itqde"] a.hy-door[data-door="artefact"]', a => a.getAttribute('href'));
    ok(href === '/artefact?corpus=subset-sum-itqde', `the artefact door deep-links /artefact (W2 consolidation; got ${JSON.stringify(href)})`);
    const artResp = await get(port, href);
    ok(artResp.status === 200, `the latest-artefact link answers 200 (got ${artResp.status})`);

    // ── the Dashboard copy law, re-baselined to W-DASH: the resting surface is the composed
    // BRIEF of the whole (exactly one [data-role="brief-prose"] line — the server-composed
    // delta-and-ask glance, which replaced the static onboarding mission line), and the project
    // CARDS still carry NO explanatory prose. The original "zero <p> in cards" intent (cards must
    // never regress into verbose per-card copy) is preserved as the card-level check.
    const proseLines = await pg.$$eval('#dash [data-role="brief-prose"]', els => els.length);
    ok(proseLines === 1, `the dashboard carries the one composed brief line (found ${proseLines} brief-prose)`);
    const cardParas = await pg.$$eval('#dash .hy-card p', els => els.length);
    ok(cardParas === 0, `no explanatory copy inside project cards (found ${cardParas} <p>)`);

    ok(pageErrors.length === 0, `no page errors across the run (${JSON.stringify(pageErrors)})`);
    console.log(`\nALL GREEN — ${passed} assertions`);
  } finally {
    await b.close();
    if (scanner) scanner.kill();
  }
})().catch((e) => { console.error('\n' + e.message); if (scanner) scanner.kill(); process.exit(1); });
