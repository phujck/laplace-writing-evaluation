// j3b — TRACE UP, from the storyboard brief (the reverse of j3a).
//
// RE-AIMED TO CURRENT TRUTH (W-PINS 2026-07-22): the old walk drove the STATIC storyboard
// board (.sb-col / .beat / __sbBeatOwner / the shared inspector's "open in conceptric" door).
// W-SB re-conceived /storyboard as THE STORYBOARD IN THE ENGINE — a JS boot shell
// (storyboard-panes.mjs / initStoryboard) whose resting DOM is the composed BRIEF + one-line
// counts; the section/weighting cards and their GROUNDING NODES materialise behind a focus.
// The LAW this walk guards is UNCHANGED: a node's door into conceptric carries that exact node
// URL-canonically (?node=), and following it lands on the conceptric growth cockpit (#eng-root)
// with the selection carried cross-surface. The MECHANISM moved from the inspector door to the
// grounding-node door (sb-gnode, href='/conceptric?...&node='): materialise the weighting →
// a grounding-node door → /conceptric?node=. One selection, URL-canonical, cross-surface.
// j3a walks conceptric-node → board; this walks brief-grounding-node → conceptric-node.
//
// Read-only walk on the real crank corpus (no mutation → no ledger to protect).

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
function ok(cond, msg) { if (!cond) throw new Error('ASSERT FAILED: ' + msg); passed++; console.log('  ok -', msg); }
function freePort() { return new Promise((res, rej) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); s.on('error', rej); }); }
function waitFor(url, tries = 60) { return new Promise((res, rej) => { const tick = (n) => { const req = http.get(url, (r) => { r.resume(); res(true); }); req.on('error', () => n <= 0 ? rej(new Error('server never came up')) : setTimeout(() => tick(n - 1), 250)); }; tick(tries); }); }
const q = (s) => String(s).replace(/"/g, '\\"');

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

    // 1) the storyboard in the engine — the resting brief + one-line count chips
    await pg.goto(`http://127.0.0.1:${port}/storyboard?corpus=${CORPUS}`, { waitUntil: 'networkidle' });
    await pg.waitForSelector('#eng-root', { timeout: 12000 });
    // the weighting count chip (the authored contribution rank; its cards ground in named nodes)
    const wchip = await pg.waitForSelector('.sb-count[data-materialize="weighting"]:not(.is-empty)', { timeout: 12000 });
    ok(!!wchip, 'the storyboard brief resolves with a non-empty weighting count chip');

    // 2) materialise the weighting → the ranked cards, each rendering its grounding nodes
    //    (groundBlock) as sb-gnode doors in place.
    await wchip.click();
    await pg.waitForSelector('.sb-gnode[data-gnode]', { timeout: 10000 });
    const gnodeId = await pg.$eval('.sb-gnode[data-gnode]', (e) => e.dataset.gnode);
    ok(gnodeId, `the materialised weighting lists its grounding-node doors (first: ${gnodeId})`);

    // 3) the reverse door — the grounding node's door into conceptric — carries that exact
    //    node URL-canonically (?node=), the LAW this walk guards.
    const doorSel = `.sb-gnode[data-gnode="${q(gnodeId)}"]`;
    const door = await pg.waitForSelector(doorSel, { timeout: 10000 });
    const doorHref = await door.getAttribute('href');
    ok(new URL(doorHref, 'http://x').searchParams.get('node') === gnodeId,
       `the grounding-node's conceptric door embeds the exact node (?node=${new URL(doorHref, 'http://x').searchParams.get('node')})`);

    // 4) following it lands on the conceptric GROWTH COCKPIT (#eng-root) with the selection
    //    carried cross-surface in the URL (URL-canonical). The graded-descent node board that
    //    focuses that ?node= is retained at /conceptric/map (proven node-focusable by j3a),
    //    reachable as an altitude from the cockpit brief.
    await door.click();
    await pg.waitForURL('**/conceptric?**', { timeout: 10000 });
    await pg.waitForSelector('#eng-root', { timeout: 10000 });
    ok(new URL(pg.url()).searchParams.get('node') === gnodeId, 'the ?node= selection carried cross-surface to the conceptric cockpit (URL-canonical)');

    ok(pageErrors.length === 0, `no page errors (${pageErrors.join('; ')})`);
    console.log(`\n[j3b] ALL GREEN — ${passed} assertions`);
  } finally {
    await b.close();
    if (scanner) scanner.kill();
  }
})().catch((e) => { console.error('\n' + e.message); if (scanner) scanner.kill(); process.exit(1); });
