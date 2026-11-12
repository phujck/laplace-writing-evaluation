// Wave 0.5 — THE LADDER, the up-loop bank (§4 W-L28). THE MUTATING WALK: it drives the
// panel-head ✎ through the REAL write door (POST /corpus/friction → friction_add), banking
// a fork into corpus_friction/subset-sum-itqde.jsonl, then proves the up-conjugate closed —
// the desk read-model's forks stratum count rose by exactly one. A standing net must not
// rewrite what it guards, so this walk is EXCLUDED from the default run and named in
// scripts/run_playwright_walks.py :data:`MUTATING_WALKS` — run it deliberately.
//
//   run:  node tests/wave05_ladder_bank.playwright.mjs
//   deps: global `playwright`, Chromium at /opt/pw-browsers, python3. Exits 0 all-green.
import { createRequire } from 'module';
import { spawn, execSync } from 'child_process';
import net from 'net';

const require = createRequire(import.meta.url);
const PW_ROOT = execSync('npm root -g').toString().trim() + '/playwright';
const { chromium } = require(PW_ROOT);
const CHROME = execSync('ls /opt/pw-browsers/chromium-*/chrome-linux/chrome')
  .toString().trim().split('\n')[0];
const PY = 'python3';
const RICH = 'subset-sum-itqde';
const NODE = 'goal:perturbation-assisted-itqde';

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
async function forksCount(pg) {
  return pg.evaluate(async () => {
    const r = await fetch('/desk/data');
    const d = await r.json();
    const s = (d.classes || []).find((x) => x.class === 'forks');
    return s ? s.count : -1;
  });
}

let scanner;
(async () => {
  const repoRoot = execSync(`${PY} -c "from laplace.web.scanner import _repo_root; print(_repo_root().resolve())"`)
    .toString().trim();
  const port = await freePort();
  const base = `http://127.0.0.1:${port}`;
  scanner = spawn(PY, ['-m', 'laplace.web.scanner', '--port', String(port)],
    { cwd: repoRoot, stdio: 'ignore' });
  await waitFor(`${base}/shared/shell.js`);

  const b = await chromium.launch({ executablePath: CHROME });
  try {
    // ══ W-L28 · the up-loop: ✎ on the panel head → bank a fork → the desk carries it ══
    const pg = await b.newPage({ viewport: { width: 1000, height: 800 } });
    await pg.goto(`${base}/conceptric?corpus=${RICH}&node=${encodeURIComponent(NODE)}`, { waitUntil: 'domcontentloaded' });

    const before = await forksCount(pg);
    ok(before >= 0, `W-L28 read the desk forks stratum count before banking (${before})`);

    // open the ladder over the node and bank a rule through the panel-head ✎
    await pg.waitForSelector('.hy-ctx-sel.is-ladder', { timeout: 10000 });
    await pg.click('.hy-ctx-sel.is-ladder');
    await pg.waitForFunction(() => {
      const el = document.getElementById('hy-ladder');
      return el && el.classList.contains('open') && el.querySelectorAll('.hy-ladder-rung').length === 6;
    }, { timeout: 8000 });
    await pg.click('#hy-ladder .hy-ladder-head .rule-chip');
    const ta = await pg.waitForSelector('#hy-ladder .rule-cap.on textarea', { timeout: 4000 });
    const ruleText = 'ladder up-loop walk: this target needs a sharper argument beat — safe to retire';
    await ta.fill(ruleText);

    // the bank is a REAL POST /corpus/friction — capture the request + the banked id
    const [req] = await Promise.all([
      pg.waitForRequest((r) => r.method() === 'POST' && r.url().includes('/corpus/friction'), { timeout: 8000 }),
      pg.click('#hy-ladder .rule-bank'),
    ]);
    const postBody = JSON.parse(req.postData() || '{}');
    ok(postBody.node === `ladder:${NODE}`, `W-L28 the bank writes the target through a typed door (node=${postBody.node})`);

    const bankedEl = await pg.waitForSelector('#hy-ladder .rule-banked', { timeout: 8000 });
    const bankedTxt = await bankedEl.evaluate((e) => e.textContent);
    const idMatch = bankedTxt.match(/banked ✓ (\S+)/);
    ok(idMatch !== null, `W-L28 the panel confirms the bank with the record id (${bankedTxt})`);
    const bankedId = idMatch[1];
    ok(/^RW-\d{8}-\d{6}-\d+$/.test(bankedId), `W-L28 the id is a real friction-ledger record id (${bankedId})`);

    // THE UP-LOOP: the desk read-model now carries one more open fork (the stratum count is
    // the honest total, untruncated) — the interface's rule banked where the desk reads.
    const after = await forksCount(pg);
    ok(after === before + 1, `W-L28 the desk forks stratum count rose by exactly one (${before} → ${after})`);

    // and when the row survives the desk's row cap, it carries THIS target verbatim.
    const rowNode = await pg.evaluate(async (id) => {
      const r = await fetch('/desk/data');
      const d = await r.json();
      const row = (d.rows || []).find((x) => x.id === id);
      return row ? { found: true, node: row.title || row.node } : { found: false };
    }, bankedId);
    if (rowNode.found) ok(/ladder:/.test(String(rowNode.node)), `W-L28 the banked fork row carries the ladder target (${rowNode.node})`);
    else ok(true, 'W-L28 the banked fork is beyond the desk row cap — the stratum count carries it (honest total)');

    console.log(`\nALL GREEN — ${passed} assertions`);
  } finally {
    await b.close();
    if (scanner) scanner.kill();
  }
})().catch((e) => { console.error('\n' + e.message); if (scanner) scanner.kill(); process.exit(1); });
