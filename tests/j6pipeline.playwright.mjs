// j6pipeline.playwright.mjs — THE PIPELINE SURFACE walk (W6). Walked as HIM.
//
// run:  node tests/j6pipeline.playwright.mjs
//
// The chain renders FROM the real release state machine for subset-sum-itqde
// (UNDER_CONVERGENCE current, the stages before it passed); an organ card expands
// with ITS dials in place; a dial edit round-trips /dials/op and undo restores it —
// against a THROWAWAY profile dir (the real profiles/pipeline/dials-v1.yaml is proven
// byte-identical before/after, never mutated); a fire-class control's FIRST render
// shows the dry-run "what would fire" preview and fires NOTHING (a network observer);
// a heavy launch ARMS then BANKS (the launch door is stubbed, so the real work-order
// store is proven byte-identical too).

import { createRequire } from 'module';
import { spawn, execSync } from 'child_process';
import net from 'net';
import fs from 'fs';
import os from 'os';
import path from 'path';

const require = createRequire(import.meta.url);
const PW_ROOT = execSync('npm root -g').toString().trim() + '/playwright';
const { chromium } = require(PW_ROOT);
const CHROME = execSync('ls /opt/pw-browsers/chromium-*/chrome-linux/chrome').toString().trim().split('\n')[0];
const PY = 'python3';

let passed = 0;
function ok(cond, msg) { if (!cond) throw new Error('ASSERT FAILED: ' + msg); passed++; console.log('  ok -', msg); }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

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

const PROJECT = 'subset-sum-itqde';   // real registry project; release state UNDER_CONVERGENCE
let scanner, tmpProfileDir;

// the BOOT script: redirect the dials owner's ONE write seam (pipeline.dials.profile_dir) to a tmp dir,
// so every /dials/op·/dials/undo write lands in the throwaway copy — never the real
// profiles/pipeline/dials-v1.yaml. The registry / projects stay real (subset-sum is real).
const BOOT = [
  'import sys',
  'from pathlib import Path',
  'from laplace.pipeline import dials as ds',
  'from laplace.web.scanner import make_handler',
  'from http.server import ThreadingHTTPServer',
  'ds.profile_dir = lambda: Path(sys.argv[2])',
  'ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), make_handler()).serve_forever()',
].join('\n');

(async () => {
  const repoRoot = execSync(`${PY} -c "from laplace.web.scanner import _repo_root; print(_repo_root().resolve())"`).toString().trim();
  const REAL_DIALS = path.join(repoRoot, 'profiles', 'pipeline', 'dials-v1.yaml');
  const REAL_WO = path.join(repoRoot, 'corpus_friction', 'work_orders.jsonl');
  const realDialsBefore = fs.readFileSync(REAL_DIALS);
  const realWOBefore = fs.existsSync(REAL_WO) ? fs.readFileSync(REAL_WO) : null;

  tmpProfileDir = fs.mkdtempSync(path.join(os.tmpdir(), 'j6-dials-'));
  fs.copyFileSync(REAL_DIALS, path.join(tmpProfileDir, 'dials-v1.yaml'));

  const SHOTS = process.env.J6_SHOTS || fs.mkdtempSync(path.join(os.tmpdir(), 'j6-shots-'));
  fs.mkdirSync(SHOTS, { recursive: true });

  const port = await freePort();
  scanner = spawn(PY, ['-c', BOOT, String(port), tmpProfileDir], { cwd: repoRoot, stdio: 'ignore' });
  await waitFor(`http://127.0.0.1:${port}/pipeline`);

  const b = await chromium.launch({ executablePath: CHROME });
  const pageErrors = [];
  try {
    const pg = await b.newPage({ viewport: { width: 1400, height: 900 } });
    pg.on('pageerror', (e) => pageErrors.push(e.message));

    // THE NETWORK OBSERVER — stub the launch door so a heavy BANK never mutates the real
    // work-order store; count every POST to it (a dry-run must fire ZERO, a bank exactly one).
    // GET /storyboard/run/launch (the roster) is passed through — only the POST is the fire.
    const launched = [];
    await pg.route('**/storyboard/run/launch', async (route) => {
      const req = route.request();
      if (req.method() === 'POST') {
        launched.push(JSON.parse(req.postData() || '{}'));
        return route.fulfill({ status: 200, contentType: 'application/json',
          body: JSON.stringify({ ok: true, cost_class: 'model-heavy', work_order: { id: 'WO-TEST' }, spawned: false }) });
      }
      return route.continue();
    });

    // ── (a) the chain renders FROM the real state machine, behind the composed brief ──
    // W-PROJECT reface: /pipeline 301s to /project, whose RESTING altitude is now the composed
    // brief (the pipeline readable as sentences). The board — the cockpit state strip + organ
    // cards — is the summonable inventory, MATERIALISED behind one open (the organ-panels count
    // chip). The LAW is unchanged: the ladder is rendered FROM release.STATES, the current rung
    // is the live machine state; a card per organ; each rung names its state on
    // .cockpit-rung-t[title], marks the live rung .is-current and completed rungs .is-passed.
    await pg.goto(`http://127.0.0.1:${port}/pipeline?project=${PROJECT}`, { waitUntil: 'networkidle' });
    await pg.waitForSelector('.pipe-count[data-count="organs"]', { timeout: 12000 });
    // at rest the board is summonable, not resident — no cockpit rung until the open
    ok(await pg.$$eval('.cockpit-rung', (e) => e.length) === 0, 'at rest the board is summonable — no cockpit rung resident (the brief altitude)');
    await pg.click('.pipe-count[data-count="organs"]');   // MATERIALISE the board behind one open
    await pg.waitForSelector('#pipe-cockpit .cockpit-strip .cockpit-rung', { timeout: 12000 });
    const ladder = await pg.$$eval('#pipe-cockpit .cockpit-strip .cockpit-rung', (els) => els.map((e) => {
      const t = e.querySelector('.cockpit-rung-t');
      return { state: t ? (t.getAttribute('title') || '') : '', cls: e.className };
    }));
    ok(ladder.length >= 10, `the chain ladder renders ${ladder.length} release states from release.STATES (>=10)`);
    const cur = ladder.find((s) => /is-current/.test(s.cls));
    ok(cur && /UNDER_CONVERGENCE/.test(cur.state), `the current stage is UNDER_CONVERGENCE (the live state machine): ${cur && cur.state}`);
    const passedSteps = ladder.filter((s) => /is-passed/.test(s.cls));
    ok(passedSteps.length >= 3, `the stages before it render as passed (${passedSteps.length} >= 3: staged·welded·mechanical)`);
    const cards = await pg.$$('#pipe-board .hy-card[data-organ]');
    ok(cards.length >= 10, `the board renders one organ CARD per stage (${cards.length} cards)`);
    await pg.screenshot({ path: path.join(SHOTS, 'w6_pipeline_desktop.png'), fullPage: true });

    // ── (b) opening an organ PINS it into the focus with ITS dials in place ───────────
    // W-PROJECT: opening an organ REALLOCATES into the engine's focus geometry (the real
    // panel re-homed behind focus, not rebuilt); the converge card lands in .eng-focus, open,
    // with its dials in place and the named return door to the project brief.
    const conv = await pg.$('#pipe-board .hy-card[data-organ="converge"]');
    ok(conv, 'the converge organ card is on the board');
    await conv.click();
    await pg.waitForSelector('#eng-root.reallocated', { timeout: 8000 });
    await pg.waitForSelector('.eng-focus .hy-card[data-organ="converge"] .pipe-dial', { timeout: 8000 });
    const doorLabel = (await pg.textContent('[data-role="return-door"] .rd-label')).trim();
    ok(/back to the project brief/i.test(doorLabel), `pinning the organ named the return door back to the brief: ${JSON.stringify(doorLabel)}`);
    const dialCount = await pg.$$eval('.eng-focus .hy-card[data-organ="converge"] .pipe-dial', (r) => r.length);
    ok(dialCount > 0, `the converge organ pins into focus with its dials IN PLACE (${dialCount} knobs)`);
    await pg.screenshot({ path: path.join(SHOTS, 'w6_pipeline_organ.png'), fullPage: true });

    // ── (c) a dial edit round-trips /dials/op and undo restores it (throwaway profile) ─
    // the dial-write idiom reaches the FOCUS card (reload re-pins the organ) — the edit's
    // provenance flips to 'overlay' in place, and undo restores the code default.
    const fixModeSel = '.eng-focus .hy-card[data-organ="converge"] .pipe-dial[data-path="loop.fix_mode"] select.ctl';
    await pg.waitForSelector(fixModeSel, { timeout: 6000 });
    const before = await pg.$eval(fixModeSel, (s) => s.value);
    const target = before === 'harnessed' ? 'loop' : 'harnessed';
    await pg.selectOption(fixModeSel, target);            // fires 'change' -> POST /dials/op (tmp profile)
    await pg.waitForFunction((sel) => {
      const row = document.querySelector(sel);
      return row && /overlay/.test(row.querySelector('.pipe-prov').className);
    }, '.eng-focus .hy-card[data-organ="converge"] .pipe-dial[data-path="loop.fix_mode"]', { timeout: 8000 });
    ok(true, `a dial edit (loop.fix_mode ${before} -> ${target}) round-tripped /dials/op and now reads 'overlay'`);
    // undo restores the default provenance
    await pg.click('.eng-focus .hy-card[data-organ="converge"] .pipe-undo');
    await pg.waitForFunction((sel) => {
      const row = document.querySelector(sel);
      return row && !/overlay/.test(row.querySelector('.pipe-prov').className);
    }, '.eng-focus .hy-card[data-organ="converge"] .pipe-dial[data-path="loop.fix_mode"]', { timeout: 8000 });
    ok(true, 'undo (/dials/undo) restored the code default — the dial reads default again');

    // ── (d) a fire-class control's FIRST render is a DRY-RUN that fires NOTHING; then a
    //        heavy launch ARMS then BANKS. (scoped to the harnessed-round control, since the
    //        converge card carries more than one scoped control.) ─────────────────────────
    const ctrl = '.eng-focus .hy-card[data-organ="converge"] .pipe-launches .rt-ctrl[data-action="harnessed-round"]';
    await pg.waitForSelector(ctrl + ' [data-launch="harnessed-round"]', { timeout: 6000 });
    launched.length = 0;
    await pg.click(ctrl + ' [data-launch="harnessed-round"]');   // FIRST click reveals the dry-run — no fire
    await pg.waitForSelector(ctrl + ' .rt-dry .rt-fire', { timeout: 8000 });
    await sleep(250);
    ok(launched.length === 0, `the fire control's first render shows the dry-run 'what would fire' and fires NOTHING (${launched.length} POSTs)`);
    const dryText = await pg.$eval(ctrl + ' .rt-dry', (e) => e.textContent);
    ok(/what would fire/i.test(dryText), 'the dry-run preview names what would fire (propagate worklist, pure read)');
    // arm then fire — the heavy launch banks
    const armFire = ctrl + ' .rt-dry .rt-fire';
    await pg.click(armFire);                              // ARMS (first click)
    await sleep(200);
    ok(launched.length === 0, 'arming the heavy launch fired NOTHING (arm-to-fire; one click never banks)');
    await pg.click(armFire);                              // FIRES (second click) -> BANKS
    await pg.waitForFunction((sel) => {
      const o = document.querySelector(sel + ' .rt-out');
      return o && /banked/i.test(o.textContent);
    }, ctrl, { timeout: 8000 });
    ok(launched.length === 1 && launched[0].action === 'harnessed-round' && launched[0].armed === true,
      `the second click BANKED the heavy launch exactly once (offer law): ${JSON.stringify(launched[0])}`);

    // ── 375px — single column, no horizontal overflow (brief at rest AND board open) ──
    await pg.setViewportSize({ width: 375, height: 720 });
    await pg.goto(`http://127.0.0.1:${port}/pipeline?project=${PROJECT}`, { waitUntil: 'networkidle' });
    await pg.waitForSelector('.pipe-count[data-count="organs"]', { timeout: 10000 });
    const overflowBrief = await pg.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    ok(overflowBrief <= 2, `no horizontal overflow at 375px on the resting brief (${overflowBrief}px)`);
    await pg.click('.pipe-count[data-count="organs"]');
    await pg.waitForSelector('#pipe-board .hy-card[data-organ]', { timeout: 10000 });
    const overflow = await pg.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    ok(overflow <= 2, `no horizontal overflow at 375px with the board materialised (${overflow}px)`);
    await pg.screenshot({ path: path.join(SHOTS, 'w6_pipeline_375.png'), fullPage: true });

    ok(pageErrors.length === 0, `no page errors (${pageErrors.join(' | ')})`);

    // ── the fixtures never leaked into real state ────────────────────────────────────
    const dialsUntouched = Buffer.compare(fs.readFileSync(REAL_DIALS), realDialsBefore) === 0;
    const woNow = fs.existsSync(REAL_WO) ? fs.readFileSync(REAL_WO) : null;
    const woUntouched = (realWOBefore === null && woNow === null) ||
      (realWOBefore !== null && woNow !== null && Buffer.compare(woNow, realWOBefore) === 0);
    console.log(`\nALL GREEN — ${passed} assertions · screenshots -> ${SHOTS}`);
    await b.close();
    if (scanner) scanner.kill('SIGKILL');
    try { fs.rmSync(tmpProfileDir, { recursive: true, force: true }); } catch (_e) { /* best effort */ }
    if (!dialsUntouched) { console.error('\nREAL dials-v1.yaml was mutated — the throwaway profile leaked'); process.exit(1); }
    if (!woUntouched) { console.error('\nREAL work_orders.jsonl was mutated — the launch stub leaked'); process.exit(1); }
    ok(true, 'the real calibration (profiles/pipeline/dials-v1.yaml) + work-order store are byte-identical (never mutated)');
    process.exit(0);
  } catch (e) {
    console.error('\n' + e.message);
    if (pageErrors.length) console.error('pageerrors: ' + pageErrors.join(' | '));
    await b.close().catch(() => {});
    if (scanner) scanner.kill('SIGKILL');
    try { fs.rmSync(tmpProfileDir, { recursive: true, force: true }); } catch (_e) { /* best effort */ }
    process.exit(1);
  }
})().catch((e) => { console.error('\n' + e.message); if (scanner) scanner.kill('SIGKILL'); process.exit(1); });
