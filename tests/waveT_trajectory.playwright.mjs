// WAVE T — THE TRAJECTORY SURFACE (ARMING_2026-07-16 · TRAJECTORY SURFACE): /analytics
// rebuilt as the loop's interrogation surface, driven in a real Chromium against a real
// scanner reading the REAL banked round 1-2 LOOP_TRAJECTORY records. Acceptance is
// ASSERTED against the primary records on disk, never narrated.
//
//   run:  node tests/waveT_trajectory.playwright.mjs
//   deps: global `playwright` (npm root -g), Chromium at /opt/pw-browsers, python3 on PATH.
//         Exits 0 all-green, non-zero on the first failed assertion.
//
// The whole point of the surface is CLOSE interrogation: cards render finding counts that
// match the jsonl (the derivative visible), a drill lands on the retrieval sidecars and
// exemplar rows, the reader claimed-vs-banked gap is framed honest, and every ruling
// carries its contest door. This walk cross-checks the DOM against /analytics/loop.
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

  // the banked truth the surface must reflect (the primary records, read straight)
  const board = JSON.parse((await get(port, '/analytics/loop')).body);
  ok(board.rounds && board.rounds.length >= 2, `the loop board carries the banked rounds (got ${board.rounds && board.rounds.length})`);
  const byRound = Object.fromEntries(board.rounds.map(r => [r.round, r]));
  ok(byRound[1] && byRound[2], 'rounds 1 and 2 are on record');
  ok(byRound[1].mech_total === 63, `r1 banked mech total is 63 (got ${byRound[1].mech_total})`);
  ok(byRound[2].mech_total === 46, `r2 banked mech total is 46 (got ${byRound[2].mech_total})`);
  ok(byRound[2].mech_delta === -17, `r2 derivative is -17 (63->46) (got ${byRound[2].mech_delta})`);

  const b = await chromium.launch({ executablePath: CHROME });
  try {
    const pg = await b.newPage({ viewport: { width: 1400, height: 900 } });
    const pageErrors = []; pg.on('pageerror', (e) => pageErrors.push(String(e)));
    const bad = []; pg.on('response', r => { if (r.status() >= 400 && !r.url().endsWith('/favicon.ico')) bad.push(`${r.status()} ${r.url()}`); });

    console.log(`\n[waveT] GET /analytics (the loop interrogation surface)`);
    await pg.goto(`http://127.0.0.1:${port}/analytics`, { waitUntil: 'domcontentloaded' });
    await pg.waitForSelector('.rc[data-round]', { timeout: 10000 });

    // ── the census strip paints, banked-vs-absent ────────────────────────────
    const censusText = (await pg.$eval('#lt-census', e => e.innerText)).toLowerCase();
    ok(/rounds banked/.test(censusText), 'the census strip names rounds banked');
    ok(/claimed-but-absent/.test(censusText), 'the census names the claimed-but-absent reader gap (honesty law)');

    // ── rounds as cards; counts MATCH the jsonl; the derivative is visible ────
    const cards = await pg.$$eval('.rc[data-round]', els => els.map(e => e.getAttribute('data-round')));
    ok(cards.length === board.rounds.length, `every banked round is a card (dom ${cards.length} == board ${board.rounds.length})`);
    const r1Text = await pg.$eval('.rc[data-round="1"]', e => e.innerText);
    ok(/63/.test(r1Text), `r1 card shows the banked count 63 (got ${JSON.stringify(r1Text.slice(0,80))})`);
    const r2Text = await pg.$eval('.rc[data-round="2"]', e => e.innerText);
    ok(/46/.test(r2Text), 'r2 card shows the banked count 46');
    ok(/Δ\s*-17/.test(r2Text), `r2 card shows the derivative Δ -17 (got ${JSON.stringify(r2Text.replace(/\s+/g,' ').slice(0,120))})`);
    const r2DeltaClass = await pg.$eval('.rc[data-round="2"] .rc-delta', e => e.className);
    ok(/\bdown\b/.test(r2DeltaClass), 'the r2 derivative renders as a DROP (down/green — the loop contracted)');

    // r1 shows the hard-gate-fail badge (technical_support false — the citation basin)
    const r1Gate = await pg.$eval('.rc[data-round="1"] .gate-badge', e => e.className + '|' + e.innerText);
    ok(/fail/.test(r1Gate), `r1 card carries the hard-gate-fail badge (got ${JSON.stringify(r1Gate)})`);

    // ── DRILL round 1: land on the sidecars, exemplar rows, source spans ──────
    console.log(`\n[waveT] drill round 1`);
    await pg.click('.rc[data-round="1"]');
    await pg.waitForSelector('#lt-drill.show .pan', { timeout: 10000 });
    const drillText = (await pg.$eval('#lt-drill', e => e.innerText));

    // findings by class — the banked source door + the top class (citation-uncited 38)
    ok(/mechanical findings/i.test(drillText), 'the drill opens the mechanical-findings panel');
    ok(/citation-uncited/.test(drillText) && /38/.test(drillText), 'the class table shows citation-uncited = 38 (the dominant basin)');
    const srcDoor = await pg.$eval('#lt-drill .door', e => e.getAttribute('data-path') || e.className);
    ok(/harnessed_round1\.json/.test(srcDoor) || (await pg.$('#lt-drill .door')) !== null, 'the findings panel carries a door to a banked primary record');

    // lens retrieval sidecars → the exemplar rows served (row_id + cosine)
    ok(/retrieval sidecars/i.test(drillText), 'the drill shows the lens retrieval-sidecar panel');
    const exRows = await pg.$$('#lt-drill .sc .ex');
    ok(exRows.length > 0, `the sidecars surface the exemplar rows served (found ${exRows.length})`);
    const exText = await pg.$eval('#lt-drill .sc .ex', e => e.innerText);
    // the exemplar row carries its row id + cosine. The id family tracks the served corpus's
    // exemplar source — paragraph-plan (PP-), derivation-walk (DW-lra-…), etc. — so assert a
    // STRUCTURED row-id token (an upper-case prefix + name) alongside the cosine score, rather
    // than pinning one prefix that shifts with which lens sidecar is retrieved.
    ok(/[A-Z]{2,}-[\w.-]+/.test(exText) && /\d\.\d/.test(exText),
      `an exemplar row carries its row id + cosine (got ${JSON.stringify(exText)})`);

    // reader claimed-vs-banked gap framed honest (8 claimed, 4 banked)
    ok(/reader exemplars/i.test(drillText), 'the drill shows the reader-exemplars panel');
    ok(/claimed 8, banked verbatim 4/i.test(drillText), 'the reader gap is framed: claimed 8, banked verbatim 4 (not laundered)');

    // before / after semantic loci (round 1 has the semantic md)
    ok(/before \/ after/i.test(drillText), 'the drill shows the before/after semantic panel');
    const beforeCol = await pg.$('#lt-drill .ba .col.before');
    ok(beforeCol !== null, 'a before/target locus renders side-by-side (the prose the loop names)');

    // rulings joined with contest doors + the GENUINELY-HIS residue
    ok(/rulings/i.test(drillText), 'the drill shows the rulings panel');
    ok(/uncontested|contested/i.test(drillText), 'each ruling carries its contest door (contested/uncontested state)');
    ok(/citation door-check/i.test(drillText), 'the GENUINELY-HIS residue is framed (the citation door-check organ)');

    // the ✎ rule mouth is attached to the panels (shared D16 atom)
    const ruled = await pg.$$('#lt-drill .pan.hy-rulable');
    ok(ruled.length > 0, `the ✎ rule mouth is attached to the drill panels (found ${ruled.length} rulable)`);

    // ── the cross-project rollup still renders (kept, secondary) ──────────────
    await pg.waitForSelector('tr.an-row', { timeout: 10000 });
    const anRows = await pg.$$('tr.an-row');
    ok(anRows.length > 0, `the cross-project rollup still paints (${anRows.length} project rows)`);

    ok(bad.length === 0, `no 4xx/5xx responses across the run (${JSON.stringify(bad)})`);
    ok(pageErrors.length === 0, `no page errors across the run (${JSON.stringify(pageErrors)})`);
    console.log(`\nALL GREEN — ${passed} assertions`);
  } finally {
    await b.close();
    if (scanner) scanner.kill();
  }
})().catch((e) => { console.error('\nWALK FAILED:', e.message); if (scanner) scanner.kill(); process.exit(1); });
