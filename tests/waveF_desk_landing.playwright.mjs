// ═══════════════════════════════════════════════════════════════════════════
// WAVE F — THE ✎ RULE LANDS OPEN ON THE DESK, the REAL write-path round-trip.
// tests/waveF_seal proves the D16 bank + the desk drain WITHOUT writing (the POST
// intercepted, the drain proven by schema). This walk closes the loop for real:
// it drives the ✎ mouth in the browser, banks a typed fork through the ONE
// sanctioned friction gate, and proves the record LANDS OPEN on the live
// /desk/data forks stratum — the "lands open on the desk payload" clause, driven.
//
//   run:  node tests/waveF_desk_landing.playwright.mjs
//   deps: global `playwright`, Chromium at /opt/pw-browsers, python3.
//
// MUTATING — it appends a real record to the friction ledger, so it is EXCLUDED
// from the default fleet (scripts/run_playwright_walks.py MUTATING_WALKS) and run
// deliberately when the write-path proof is what you want. It writes to a UNIQUE
// throwaway corpus ledger (`corpus_friction/wavef-seal-probe.jsonl`) it owns and
// removes in `finally` — it never touches a real project's ledger, so the forks
// COUNT delta of exactly +1 is an airtight proof that THIS bank is what landed.
import { createRequire } from 'module';
import { spawn, execSync } from 'child_process';
import net from 'net';
import http from 'http';
import fs from 'fs';
import path from 'path';

const require = createRequire(import.meta.url);
const { chromium } = require(execSync('npm root -g').toString().trim() + '/playwright');
const CHROME = execSync('ls /opt/pw-browsers/chromium-*/chrome-linux/chrome').toString().trim().split('\n')[0];
const PY = 'python3';

// the throwaway corpus this walk owns — a fresh, unique ledger so the count delta is ours
const PROBE_CORPUS = 'wavef-seal-probe';

let passed = 0;
function ok(cond, msg) { if (!cond) throw new Error('ASSERT FAILED: ' + msg); passed++; console.log('  ok -', msg); }
function freePort() { return new Promise((res, rej) => {
  const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); s.on('error', rej); }); }
function waitFor(url, tries = 80) { return new Promise((res, rej) => {
  const tick = (n) => { const req = http.get(url, (r) => { r.resume(); res(true); });
    req.on('error', () => n <= 0 ? rej(new Error('server never came up')) : setTimeout(() => tick(n - 1), 250)); }; tick(tries); }); }
function get(port, p) { return new Promise((res, rej) => {
  http.get(`http://127.0.0.1:${port}${p}`, (r) => { let b = ''; r.on('data', d => b += d); r.on('end', () => res(b)); }).on('error', rej); }); }
function forksCount(desk) { const c = (desk.classes || []).find((x) => x.class === 'forks'); return c ? c.count : -1; }

let scanner, ledgerPath, ledgerExisted = false;
(async () => {
  const repoRoot = execSync(`${PY} -c "from laplace.web.scanner import _repo_root; print(_repo_root().resolve())"`).toString().trim();
  ledgerPath = path.join(repoRoot, 'corpus_friction', `${PROBE_CORPUS}.jsonl`);
  ledgerExisted = fs.existsSync(ledgerPath);

  const port = await freePort();
  const base = `http://127.0.0.1:${port}`;
  scanner = spawn(PY, ['-m', 'laplace.web.scanner', '--port', String(port)], { cwd: repoRoot, stdio: 'ignore' });
  await waitFor(`${base}/`);

  const b = await chromium.launch({ executablePath: CHROME });
  try {
    // baseline: the desk's open-fork count BEFORE the bank
    const before = forksCount(JSON.parse(await get(port, '/desk/data')));
    ok(before >= 0, `the /desk/data forks stratum reads a baseline count (${before})`);

    // drive the ✎ mouth on the desk header (any surface's header carries it; the desk
    // is where these land) and bank a REAL typed fork — no interception this time.
    const pg = await b.newPage({ viewport: { width: 1400, height: 900 } });
    const pageErrors = []; pg.on('pageerror', (e) => pageErrors.push(String(e).slice(0, 120)));
    await pg.goto(`${base}/desk?corpus=${encodeURIComponent(PROBE_CORPUS)}`, { waitUntil: 'domcontentloaded' });
    await pg.waitForSelector('#hy-context .rule-chip', { state: 'attached', timeout: 12000 });

    let posted = null;
    pg.on('request', (r) => { if (r.url().endsWith('/corpus/friction') && r.method() === 'POST') { try { posted = JSON.parse(r.postData() || '{}'); } catch (e) {} } });

    await pg.hover('#hy-context');
    await pg.click('#hy-context .rule-chip');
    await pg.waitForSelector('#hy-context .rule-cap textarea', { timeout: 5000 });
    const ruleText = 'seal round-trip: this fork must land OPEN on my desk';
    await pg.fill('#hy-context .rule-cap textarea', ruleText);
    await pg.click('#hy-context .rule-cap .rule-bank');
    await pg.waitForSelector('#hy-context .rule-banked', { timeout: 8000 });

    const bankedText = await pg.$eval('#hy-context .rule-banked', (e) => e.textContent);
    const idMatch = bankedText.match(/banked ✓\s*(RW-[\w-]+)/);
    ok(idMatch, `the capture rendered a real banked id (${JSON.stringify(bankedText.slice(0, 60))})`);
    const bankedId = idMatch[1];
    ok(posted && posted.kind === 'fork' && posted.owning_layer === 'interface' && posted.by === 'author',
      `the REAL POST carried a typed interface fork (kind=${posted && posted.kind}, layer=${posted && posted.owning_layer})`);
    ok(posted && posted.corpus === PROBE_CORPUS,
      `the fork was banked onto the throwaway corpus this walk owns (${posted && posted.corpus})`);

    // the ledger this walk owns now exists and carries exactly our record
    ok(fs.existsSync(ledgerPath), `the friction ledger was written on disk (${path.basename(ledgerPath)})`);
    const lines = fs.readFileSync(ledgerPath, 'utf-8').trim().split('\n').filter(Boolean);
    ok(lines.some((l) => l.includes(bankedId) && l.includes('"status": "open"') && l.includes('"kind": "fork"')),
      `the ledger row is a typed OPEN fork carrying the banked id (${bankedId})`);

    // THE LANDING: the live desk read-model's forks stratum grew by exactly our one bank
    const after = forksCount(JSON.parse(await get(port, '/desk/data')));
    ok(after === before + 1,
      `the banked fork LANDS OPEN on the desk — forks stratum ${before} → ${after} (+1, ours)`);

    ok(pageErrors.length === 0, `no page errors during the round-trip (${JSON.stringify(pageErrors)})`);
    console.log(`\nALL GREEN — ${passed} assertions (real write-path round-trip)`);
  } finally {
    await b.close();
    if (scanner) scanner.kill();
    // cleanup — this walk owns the probe ledger: if it did not pre-exist, remove it;
    // if it did (it should not), strip only the lines this run appended is unsafe to
    // reason about, so leave a pre-existing file untouched and warn.
    try {
      if (ledgerPath && fs.existsSync(ledgerPath)) {
        if (!ledgerExisted) { fs.unlinkSync(ledgerPath); console.log(`cleanup: removed ${path.basename(ledgerPath)}`); }
        else console.log(`cleanup: ${path.basename(ledgerPath)} pre-existed — left untouched (inspect manually)`);
      }
    } catch (e) { console.error('cleanup error:', e.message); }
  }
})().catch((e) => { console.error('\n' + (e.message || e)); if (scanner) scanner.kill(); process.exit(1); });
