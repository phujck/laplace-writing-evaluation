// WAVE 4 — THE STORYBOARD SURFACE. SUPERSEDED BY W-SB (2026-07-22): the storyboard JOINED THE
// ONE INSTRUMENT (engine.mjs). His ruling — the storyboard is "the place where I can most
// easily see the thing that's going to be projected." The W4 board grammar (a strip-over-void
// board that owned the centre, #sb-rank as a top strip, click-reorder / ✎-rule editing, the
// section-column DOM at rest) is retired: the resting DOM is now a composed BRIEF and cards
// materialise on FOCUS, reallocating around the examined point. The full engine grammar is
// walk-proven in tests/engine_storyboard.playwright.mjs (on paper_falqon); the plan-write
// endpoints (reorder / ✎-rule / restructure) stay covered by tests/test_storyboard_endpoints.py
// and tests/test_storyboard.py. THIS walk keeps the coverage on the SECOND corpus
// (subset-sum-itqde, whose authored contribution rank is 3 primary + 1 excluded), proving the
// new truth as OUTCOMES: the brief rests, the counts law holds, and the weighting cards carry
// their grounding (source nodes + the why) rendered IN PLACE.
//
//   run:  node tests/wave4_storyboard.playwright.mjs
//   Exits 0 all-green, non-zero on the first failed assertion.
import { createRequire } from 'module';
import { spawn, execSync } from 'child_process';
import net from 'net';
import http from 'http';

const require = createRequire(import.meta.url);
const { chromium } = require(execSync('npm root -g').toString().trim() + '/playwright');
const CHROME = execSync('ls /opt/pw-browsers/chromium-*/chrome-linux/chrome').toString().trim().split('\n')[0];
const PY = 'python3';
const CORPUS = 'subset-sum-itqde';

let passed = 0;
function ok(cond, msg) { if (!cond) throw new Error('ASSERT FAILED: ' + msg); passed++; console.log('  ok -', msg); }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function freePort() { return new Promise((res) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); }); }
function waitFor(url, tries = 80) {
  return new Promise((res, rej) => { const tick = (n) => { const req = http.get(url, (r) => { r.resume(); res(true); });
    req.on('error', () => n <= 0 ? rej(new Error('server never came up')) : setTimeout(() => tick(n - 1), 250)); }; tick(tries); });
}

let scanner;
(async () => {
  const repoRoot = execSync(`${PY} -c "from laplace.web.scanner import _repo_root; print(_repo_root().resolve())"`).toString().trim();
  const port = await freePort();
  scanner = spawn(PY, ['-m', 'laplace.web.scanner', '--port', String(port)], { cwd: repoRoot, stdio: 'ignore' });
  await waitFor(`http://127.0.0.1:${port}/storyboard`);
  const base = `http://127.0.0.1:${port}`;
  const b = await chromium.launch({ executablePath: CHROME });
  try {
    const pg = await b.newPage({ viewport: { width: 1440, height: 900 } });
    const errs = []; pg.on('pageerror', (e) => errs.push(String(e)));
    for (const surf of ['artefact', 'conceptric', 'pipeline', 'desk']) {
      await pg.route('**/' + surf + '**', (route) => route.request().resourceType() === 'document'
        ? route.fulfill({ status: 200, contentType: 'text/html', body: '<!doctype html><title>' + surf + ' stub</title>' })
        : route.continue());
    }

    await pg.goto(base + '/storyboard?corpus=' + CORPUS, { waitUntil: 'networkidle' });
    await pg.waitForSelector('[data-role="brief-prose"]', { timeout: 8000 });
    await sleep(250);

    // ── (1) THE BRIEF RESTS — no board column at rest (the strip-over-void is retired) ──
    const rest = await pg.evaluate(() => ({
      cards: document.querySelectorAll('.sb-card').length,
      oldBoard: document.querySelectorAll('#sb-flow, .sb-col, #sb-rank').length,
      prose: (document.querySelector('[data-role="brief-prose"]') || {}).textContent || '',
    }));
    ok(rest.cards === 0 && rest.oldBoard === 0, 'the resting DOM is the brief — no section column, no rank strip (the W4 board grammar is retired)');
    ok(rest.prose.trim().length > 60, 'the composed brief prose is present at rest');

    // ── (2) COUNTS LAW — the weighting chip opens exactly its cards ──────────────
    const wChip = Number((await pg.textContent('.sb-count[data-materialize="weighting"] .sb-cn')).trim());
    ok(wChip === 4, `subset-sum-itqde's authored rank is 4 cards (3 primary + 1 excluded): chip reads ${wChip}`);
    await pg.click('.sb-count[data-materialize="weighting"]');
    await pg.waitForSelector('.sb-card[data-card]', { timeout: 8000 }); await sleep(150);
    const wCards = await pg.$$eval('.sb-card[data-card]', (e) => e.length);
    ok(wChip === wCards, `the counts law holds: the weighting chip (${wChip}) opens exactly those cards (${wCards})`);

    // ── (3) GROUNDING VISIBLE — each weighting card carries its why + source nodes IN PLACE ──
    const grounded = await pg.$$eval('.sb-card[data-card]', (els) => els.every((e) =>
      e.querySelector('.sb-ground .sb-ground-why') && e.querySelector('.sb-ground-why').textContent.trim().length > 10));
    ok(grounded, 'EVERY weighting card renders its grounding (the why) in place — not a raw string with one global invite');
    const excluded = await pg.$$eval('.sb-card.is-excluded', (e) => e.length);
    ok(excluded === 1, `the excluded claim is marked as its own card (the honesty contract): ${excluded}`);

    // ── (4) EXPAND IN PLACE — opening a card REALLOCATES around it (no context-free jump) ──
    await pg.click('.sb-card[data-card]'); await sleep(300);
    ok(await pg.$eval('#eng-root', (e) => e.classList.contains('reallocated')), 'opening a weighting card reallocated around the examined point (expand in place)');
    ok(/back to the storyboard brief/i.test((await pg.textContent('[data-role="return-door"] .rd-label')).trim()),
      'the reallocated focus carries the named return door');
    ok((await pg.$$eval('.sb-focus-pane .sb-gnode', (e) => e.length)) >= 1, 'the focus names the source nodes as working doors, in place');
    await pg.keyboard.press('Escape'); await sleep(200);
    ok(!(await pg.$eval('#eng-root', (e) => e.classList.contains('reallocated'))), 'Esc closed the focus back to the brief');

    // ── (5) SECTIONS + THE DOORS CARRY THE SELECTION ────────────────────────────
    await pg.click('.sb-count[data-materialize="weighting"]'); await sleep(120);   // close weighting
    await pg.click('.sb-count[data-materialize="sections"]');
    await pg.waitForSelector('.sb-card[data-section]', { timeout: 8000 }); await sleep(150);
    const richSec = await pg.evaluate(async (c) => {
      const b = await (await fetch('/storyboard/brief?corpus=' + c)).json();
      const s = (b.cards || []).find((x) => (x.source_nodes || []).length);
      return s ? s.id : (b.cards[0] || {}).id;
    }, CORPUS);
    await pg.click(`.sb-card[data-section="${richSec}"]`); await sleep(300);
    const doors = await pg.$$eval('.sb-focus-pane .sb-door[href]', (a) => a.map((x) => x.getAttribute('href')));
    ok(doors.some((h) => h.includes('/artefact') && h.includes('section=' + richSec)), `the section focus /artefact door carries the section: ${doors.find((h) => h.includes('/artefact'))}`);
    ok(doors.some((h) => h.includes('/conceptric') && h.includes('node=')), `the /conceptric door carries a spine node selection: ${doors.find((h) => h.includes('/conceptric'))}`);

    ok(errs.length === 0, 'zero uncaught page errors across the whole walk: ' + JSON.stringify(errs));
    console.log(`\nWAVE 4 STORYBOARD (W-SB engine truth) — ${passed} assertions green.`);
  } finally {
    await b.close();
    if (scanner) scanner.kill('SIGKILL');
  }
})().catch((e) => { console.error('\nWALK FAILED:', e.message); if (scanner) scanner.kill('SIGKILL'); process.exit(1); });
