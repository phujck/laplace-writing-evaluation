// The legB-altitude TOWER harness — the browser-driven proof that one substrate
// renders at four rising altitudes, opened AT an anchor, shiftable up/down, with
// the grade-shells navigable and the wiring-back transparent at every rung.
//
// It drives the REAL served surface (altitude.html + the /altitude routes)
// against the LIVE subset-sum-itqde corpus. The altitude view is READ-ONLY — it
// never writes a byte — so there is no fixture to build and nothing to tear down
// beyond the scanner process (unlike the /review harnesses, which stage a
// throwaway ledger).
//
//   run:  node tests/legB_altitude.playwright.mjs
//   deps: global `playwright`, Chromium at /opt/pw-browsers, repo venv python3.
// Exits 0 all-green, non-zero on the first failed assertion.
import { createRequire } from 'module';
import { spawnSync, spawn } from 'child_process';
import { execSync } from 'child_process';
import net from 'net';

const require = createRequire(import.meta.url);
const PW_ROOT = execSync('npm root -g').toString().trim() + '/playwright';
const { chromium } = require(PW_ROOT);
const CHROME = execSync('ls /opt/pw-browsers/chromium-*/chrome-linux/chrome')
  .toString().trim().split('\n')[0];
const PY = 'python3';
const CORPUS = 'subset-sum-itqde';

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

let scanner, repoRoot;
(async () => {
  repoRoot = spawnSync(PY, ['-c', 'from laplace.web.scanner import _repo_root; print(_repo_root().resolve())'],
    { encoding: 'utf-8' }).stdout.trim();
  const port = await freePort();
  scanner = spawn(PY, ['-m', 'laplace.web.scanner', '--port', String(port)],
    { cwd: repoRoot, stdio: 'ignore' });
  await waitFor(`http://127.0.0.1:${port}/altitude`);

  const b = await chromium.launch({ executablePath: CHROME });
  try {
    const pg = await b.newPage({ viewport: { width: 1400, height: 950 } });
    const bad = [];
    pg.on('response', (r) => {
      const st = r.status();
      if (st >= 400 && !r.url().endsWith('/favicon.ico') && !r.url().includes('/shared/'))
        bad.push([st, r.url()]);
    });
    pg.on('pageerror', (e) => bad.push(['PAGEERROR', String(e)]));

    // ── land AT a pid anchor — the exact /altitude?corpus=&anchor= contract ───
    console.log(`\n[altitude] /altitude?corpus=${CORPUS}&anchor=N5-p2`);
    await pg.goto(`http://127.0.0.1:${port}/altitude?corpus=${CORPUS}&anchor=N5-p2`,
      { waitUntil: 'networkidle' });

    // ── the four altitudes render as one navigation ──────────────────────────
    await pg.waitForSelector('.panel[data-alt="nodes"]', { timeout: 12000 });
    const panels = await pg.$$eval('.panel', (ps) => ps.map((p) => p.dataset.alt));
    ok(JSON.stringify(panels) === JSON.stringify(['plan_prose', 'spine', 'grade_shells', 'nodes']),
      `the tower renders four altitudes, skin-on-top -> substrate-at-the-floor (${panels})`);
    const rungs = await pg.$$('#ladder .rung');
    ok(rungs.length === 4, `the altitude ladder has four rungs (got ${rungs.length})`);

    // the anchor opened at its own altitude (a pid opens at NODES), and is marked
    ok(await pg.isVisible('.panel[data-alt="nodes"].on'), 'the pid anchor opens AT the NODES altitude');
    const anchorRung = await pg.$eval('#ladder .rung.anchor', (r) => r.dataset.k);
    ok(anchorRung === 'nodes', `the ladder marks NODES as the anchor altitude (${anchorRung})`);
    ok((await pg.textContent('#h-anchor')).includes('N5-p2'), 'the header names the anchor pid N5-p2');

    // ── the wiring-back is transparent at every rung (concrete values) ────────
    const wk = await pg.$$eval('#wiring .wk', (es) => es.map((e) => e.textContent));
    ok(wk.length === 6, `six wiring-back join keys render (got ${wk.length})`);
    ok(wk.some((t) => /52 ids/.test(t)), 'the pid->nodes key shows the 52-node membership');
    ok(wk.some((t) => /N5/.test(t)), 'the beats->section key shows the owning section N5');
    ok(wk.some((t) => /N5\.tex/.test(t)), 'the section->artefact key shows N5.tex');

    // ── the NODES altitude shows the anchor's node cards ─────────────────────
    const cards = await pg.$$('.panel[data-alt="nodes"].on .ncard');
    ok(cards.length >= 10, `the anchor's node cards render at NODES (got ${cards.length})`);

    // ── SHIFT DOWN to grade-shells — grading made load-bearing ───────────────
    await pg.click('#ladder .rung[data-k="grade_shells"]');
    await pg.waitForSelector('.panel[data-alt="grade_shells"].on', { timeout: 6000 });
    const shells = await pg.$$('.panel[data-alt="grade_shells"].on #shells .shell');
    ok(shells.length >= 30, `the grade-shells render (0..g_max, got ${shells.length})`);
    // the anchor's nodes are highlighted in their shells
    const anchorShells = await pg.$$('.shell.has-anchor');
    ok(anchorShells.length >= 1, `the anchor's nodes are highlighted in their shells (${anchorShells.length} lit)`);
    // the floor is grade 0; the spine tier is g_max
    const floorGrade = await pg.$eval('#shells .shell.floor .gl', (e) => e.textContent);
    ok(floorGrade === '0', 'the floor shell is grade 0 (atoms/postulates)');
    ok(await pg.$('#shells .shell.spine'), 'the spine tier shell (g_max) is present');

    // ── CLICK a shell -> its nodes ───────────────────────────────────────────
    await anchorShells[0].click();
    await pg.waitForSelector('#shell-detail.on', { timeout: 6000 });
    ok(await pg.isVisible('#shell-detail.on'), 'clicking a shell reveals its nodes');
    const shellText = await pg.textContent('#shell-detail');
    ok(/shell g=/.test(shellText), 'the shell detail names the grade and its members');

    // ── CLICK through to a node (from the shell's nodes) -> the drawer ───────
    await pg.click('#shell-detail .ncard');               // an anchor node in this shell
    await pg.waitForSelector('#alt-detail.on', { timeout: 6000 });
    ok(await pg.isVisible('#alt-detail.on'), 'clicking a node opens its detail drawer');
    const drawer = await pg.textContent('#d-body');
    ok(/wiring-back/.test(drawer), 'the drawer exposes the node\'s wiring-back join keys');
    ok(/grade/.test(drawer) && /section/.test(drawer),
      'the wiring-back names the grade and the owning section for THIS node');
    // the grade derivation is exposed — the load-bearing-as-derived view (one of:
    // a derived node's grade-setting deps, a dependency-free floor node, or a
    // postulate whose cited deps are references, not grade-setting)
    ok(/derives from|dependency-free|postulate/.test(drawer),
      'the drawer exposes the derivation (grade-setting deps, floor, or postulate)');
    await pg.keyboard.press('Escape');                    // close the drawer
    await pg.waitForSelector('#alt-detail:not(.on)', { timeout: 4000 });

    // ── trace up / drill down shift the focused altitude ─────────────────────
    await pg.click('.panel[data-alt="nodes"] h2');          // focus the floor
    await pg.click('#up');                                   // one altitude up
    ok(await pg.isVisible('.panel[data-alt="grade_shells"].on'),
      'trace-up raises the focus one altitude (nodes -> grade-shells)');
    await pg.click('#up'); await pg.click('#up');            // up to the skin
    ok(await pg.isVisible('.panel[data-alt="plan_prose"].on'),
      'trace-up climbs to the PLAN/PROSE skin');
    // the skin is honestly marked materialized/stale-aware
    const skin = await pg.textContent('.panel[data-alt="plan_prose"]');
    ok(/in sync|rebuild to refresh|materialized/.test(skin),
      'the prose skin is marked materialized / stale-aware (never a live-reflow pretense)');
    // ACT5/job5: /review and /projection are retired doors (both 301 → /artefact, losing
    // their file=/corpus= mapping on the hop). The skin now links straight to /artefact (the
    // consolidated destination, carrying corpus + section + the node anchor) and /storyboard.
    ok(/open in \/artefact/.test(skin) && /open \/storyboard/.test(skin),
      'the skin links back into /artefact (the consolidated /review+/projection door) and /storyboard at the anchor');

    ok(bad.length === 0, `no failed requests / page errors across the tower (${JSON.stringify(bad)})`);
    console.log(`\nALL GREEN — ${passed} assertions passed`);
  } finally {
    await b.close();
  }
})().then(() => {
  cleanup(); process.exit(0);
}).catch((e) => {
  console.error('\nFAILED:', e.message);
  cleanup(); process.exit(1);
});

function cleanup() {
  try { if (scanner) scanner.kill('SIGKILL'); } catch {}
}
