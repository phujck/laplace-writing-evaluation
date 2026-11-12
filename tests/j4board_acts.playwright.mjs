// j4board — THE BOARD ACTS. SUPERSEDED BY W-SB (2026-07-22): the storyboard JOINED THE ONE
// INSTRUMENT (engine.mjs). The W4 "board acts" grammar this walk asserted — a section-column
// board that owned the centre, the #sb-rank top strip, click-expand columns, the residue
// PIN / RETIRE / restructure editing panes, a run panel wired into a side rail — is retired.
// The resting DOM is now a composed BRIEF; cards materialise on FOCUS and reallocate around
// the examined point (his ruling: the storyboard is "the place where I can most easily see the
// thing that's going to be projected").
//
// WHERE THE OLD COVERAGE MOVED (nothing is weakened, only re-homed):
//   · the full engine grammar (brief-at-rest, materialise, hover-no-shift, pin/reallocate,
//     named return door, grounding-in-place, deep-link pre-pin, scroll law) is walk-proven in
//     tests/engine_storyboard.playwright.mjs + tests/wave4_storyboard.playwright.mjs;
//   · the plan-write acts the old board fired by drag/click (reorder, add-node/pin,
//     set-projection retire, restructure dry-run + apply) stay covered as ENDPOINTS in
//     tests/test_storyboard.py + tests/test_storyboard_endpoints.py — the write doors are
//     untouched by W-SB; only their surface changed.
//
// THIS walk keeps a live acceptance on the new truth: the board no longer renders a
// strip-over-void at rest (the exact chair failure this file was born to fix — section chips
// over a void, a click with zero DOM change — cannot recur when there is no board at rest).
//
//   run:  node tests/j4board_acts.playwright.mjs
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
    await pg.goto(base + '/storyboard?corpus=' + CORPUS, { waitUntil: 'networkidle' });
    await pg.waitForSelector('[data-role="brief-prose"]', { timeout: 8000 });
    await sleep(250);

    // the chair failure cannot recur: there is NO strip-over-void board at rest, only the brief.
    const dom = await pg.evaluate(() => ({
      oldBoard: document.querySelectorAll('#sb-flow, .sb-col, #sb-rank, #sb-side').length,
      cards: document.querySelectorAll('.sb-card').length,
      brief: !!document.querySelector('[data-role="brief-prose"]'),
      chips: document.querySelectorAll('.sb-count[data-materialize]').length,
    }));
    ok(dom.oldBoard === 0, 'the W4 board grammar is retired: no #sb-flow / .sb-col / #sb-rank / #sb-side at rest (no strip-over-void)');
    ok(dom.brief && dom.cards === 0, 'the surface rests at the composed brief — no card until a focus summons it (the click-with-zero-DOM-change failure cannot recur)');
    ok(dom.chips >= 3, `the brief carries its summon chips (sections / weighting / findings / run): ${dom.chips}`);

    // a summon ACTS — opening a count materialises its object-set (the DOM appears on open).
    await pg.click('.sb-count[data-materialize="sections"]');
    await pg.waitForSelector('.sb-card[data-section]', { timeout: 8000 }); await sleep(150);
    ok((await pg.$$eval('.sb-card[data-section]', (e) => e.length)) > 0, 'a summon ACTS: opening the sections count materialised its cards (a real DOM change on click)');

    ok(errs.length === 0, 'zero uncaught page errors across the walk: ' + JSON.stringify(errs));
    console.log(`\nj4board (W-SB engine truth) — ${passed} assertions green.`);
  } finally {
    await b.close();
    if (scanner) scanner.kill('SIGKILL');
  }
})().catch((e) => { console.error('\nWALK FAILED:', e.message); if (scanner) scanner.kill('SIGKILL'); process.exit(1); });
