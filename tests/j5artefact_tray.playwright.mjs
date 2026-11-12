// THE ARTEFACT FINDINGS TRAY — the OVERRULE branch walked at the DOM (W2 triaged tray).
//
// The Wave 2 rebuild collapses the findings tray to one honest line, then triages into groups
// (kind × section, severity-ranked) with a DISMISSED FOLD at the bottom: the fingerprinted
// suppressions, folded so the live queue reads clean. Each dismissed row carries an OVERRULE ↺
// door — the ONE adjudication verb the tray still fires (confirm/defer/dismiss moved to /desk);
// overrule reborns a silenced finding live via the EXISTING executor at POST /review/adjudicate
// {verb:"revoke", supersedes:<suppression_id>}, arm-to-fire.
//
// This harness walks that branch at the DOM with STUBBED stores (page.route; deterministic
// rows, never a real ledger): the dismissed fold sources its rows + suppression ids from
// GET /review/dismissals; expand it → arm-to-fire the overrule → assert the POST carried
// {verb:"revoke", supersedes:<id>} (network-intercepted; the stub records every call).
//
//   run:  node tests/j5artefact_tray.playwright.mjs
//   deps: global playwright, Chromium at /opt/pw-browsers, the repo venv python on PATH.
//         Exits 0 all-green, non-zero on the first failed assertion.
import { createRequire } from 'module';
import { spawn, execSync } from 'child_process';
import net from 'net';

const require = createRequire(import.meta.url);
const { chromium } = require(execSync('npm root -g').toString().trim() + '/playwright');
const CHROME = execSync('ls /opt/pw-browsers/chromium-*/chrome-linux/chrome').toString().trim().split('\n')[0];
const PY = 'python3';
const CORPUS = 'wp';

let passed = 0;
function ok(cond, msg) { if (!cond) throw new Error('ASSERT FAILED: ' + msg); passed++; console.log('  ok -', msg); }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function freePort() { return new Promise((res) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); }); }
function waitFor(url, tries = 60) {
  return new Promise((res, rej) => { const tick = (n) => { const req = require('http').get(url, (r) => { r.resume(); res(true); });
    req.on('error', () => n <= 0 ? rej(new Error('server never came up')) : setTimeout(() => tick(n - 1), 250)); }; tick(tries); });
}
function waitForActs(acts, n, tries = 40) {
  return new Promise((res, rej) => { const tick = (i) => acts.length >= n ? res(true)
    : i <= 0 ? rej(new Error(`acts never reached length ${n} (got ${acts.length})`)) : setTimeout(() => tick(i - 1), 100); tick(tries); });
}

// the deterministic /artefact/context (the ONE authority): a bare tex source, no built pdf
// (the reader renders its honest no-build message — this walk is about the TRAY).
const CTX = {
  corpus: CORPUS, name: CORPUS, kind: 'paper',
  current_artefact: { pdf: null, tex: 'S1.tex', kind: 'current', version_id: 'current' },
  pdf_endpoint: '/projection/pdf', tex_endpoint: '/projection/tex', feedback_endpoint: '/projection/feedback',
};
// ONE active finding (so the tray has a live group + an honest collapsed line) and ONE
// dismissed class row carrying the suppression id the overrule must echo as `supersedes`.
const FINDING = { id: 'FB-1', record: 'finding', node: 'S1', kind: 'notation-inconsistent', cls: 'hard',
                  section: 'S1', comment: 'the symbol clashes with §V' };
const BOARD = { by_node: [], unanchored: [FINDING],
                counts: { hard: 1, soft: 0, deferred: 0, total: 1, nodes_anchored: 0, n_unanchored: 1 } };
const SUPPRESSION_ID = 'SUP-99';
const DISMISSALS = {
  rows: [{ kind: 'notation-inconsistent', fingerprint: 'fp-1', count: 1,
           nodes: [{ node: 'S1', section: 'S1', suppression_id: SUPPRESSION_ID }] }],
  counts: { classes: 1, dismissals: 1, stale: 0, machine: 1, author: 0 },
};

let scanner;
(async () => {
  const repoRoot = execSync(`${PY} -c "from laplace.web.scanner import _repo_root; print(_repo_root().resolve())"`).toString().trim();
  const port = await freePort();
  scanner = spawn(PY, ['-m', 'laplace.web.scanner', '--port', String(port)], { cwd: repoRoot, stdio: 'ignore' });
  await waitFor(`http://127.0.0.1:${port}/artefact`);

  const b = await chromium.launch({ executablePath: CHROME });
  try {
    const pg = await b.newPage({ viewport: { width: 1400, height: 900 } });
    const pageErrors = []; pg.on('pageerror', (e) => pageErrors.push(String(e)));
    const acts = [];

    await pg.route('**/artefact/context**', (r) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(CTX) }));
    await pg.route('**/shared/plan**', (r) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ sections: [] }) }));
    await pg.route('**/shared/versions**', (r) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ rows: [], counts: { total: 0 }, truncated: false }) }));
    await pg.route('**/review/nodemap**', (r) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ present: false, fresh: false }) }));
    await pg.route('**/review/findings**', (r) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(BOARD) }));
    await pg.route('**/review/dismissals**', (r) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(DISMISSALS) }));
    await pg.route('**/review/adjudicate**', (r) => { let body = {}; try { body = JSON.parse(r.request().postData() || '{}'); } catch (_e) {}
      acts.push(body); return r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, verb: body.verb, record: { id: SUPPRESSION_ID } }) }); });

    console.log(`\n[artefact-tray] /artefact?corpus=${CORPUS} (stubbed context + board + dismissal-audit + adjudicate)`);
    await pg.goto(`http://127.0.0.1:${port}/artefact?corpus=${CORPUS}`, { waitUntil: 'domcontentloaded' });
    await pg.waitForFunction(() => !/reading the review board/.test(document.querySelector('#art-tray-sum').textContent), { timeout: 12000 });

    // ── THE COLLAPSED LINE IS HONEST vs the stubbed stores ──────────────────────────
    const sum = await pg.$eval('#art-tray-sum', (e) => e.textContent);
    ok(/1 total/.test(sum) && /1 dismissed/.test(sum),
      `the tray collapses to one honest line naming total + dismissed from the stores (got "${sum}")`);

    // ── TRIAGE OPEN → a group renders; the dismissed fold is present + folded ────────
    await pg.click('#art-tray-bar'); await sleep(200);
    ok(await pg.$('#art-tray-body .art-grp') !== null, 'triage open shows the grouped live queue');
    const dh = await pg.$('#art-dism-h');
    ok(dh !== null, 'the dismissed fold renders, folded by default');
    ok(!(await pg.$eval('#art-dism', (e) => e.classList.contains('open'))), 'the fold is closed until asked (the live queue reads clean)');
    await dh.click(); await sleep(150);
    ok(await pg.$eval('#art-dism', (e) => e.classList.contains('open')), 'the fold opens on click');

    // ── THE OVERRULE BRANCH: arm-to-fire → POST {verb:revoke, supersedes:<id>} ───────
    const ov = await pg.$('#art-tray-body .art-overrule');
    ok(ov !== null, 'the dismissed row carries an overrule ↺ door');
    await ov.click(); await sleep(200);
    ok(acts.length === 0, `one click on overrule fires no door (arm-only; got ${acts.length} acts)`);
    const armed = await ov.evaluate((e) => e.textContent);
    ok(/click again/i.test(armed), `overrule arms with a "reborns it live — click again" label (got ${JSON.stringify(armed)})`);
    await ov.click();                                        // SECOND click — fires
    await waitForActs(acts, 1);
    ok(acts.length === 1 && acts[0].verb === 'revoke',
      `the second click fires the overrule (revoke) door once (got ${JSON.stringify(acts)})`);
    ok(acts[0].supersedes === SUPPRESSION_ID && acts[0].node === 'S1' && acts[0].by === 'author',
      `the POST carried {verb:"revoke", supersedes:${JSON.stringify(SUPPRESSION_ID)}, node, by} (got ${JSON.stringify(acts[0])})`);

    ok(pageErrors.length === 0, `no page errors across the walk (${JSON.stringify(pageErrors)})`);
    console.log(`\nALL GREEN — ${passed} assertions`);
  } finally { await b.close(); if (scanner) scanner.kill(); }
})().catch((e) => { console.error('\n' + e.message); if (scanner) scanner.kill(); process.exit(1); });
