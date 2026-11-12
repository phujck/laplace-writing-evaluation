// J5 — SWITCH PROJECTS, SURFACE KEPT (ACT5/job3 ruling, 2026-07-21): the topbar quick-switch
// is searchable (type-to-filter) and keyboardable (↑↓ + enter). Switching a project changes
// WHICH paper is in view, NOT WHERE in the interface he is standing — it KEEPS the current
// surface (it no longer jumps to the target project's own last-visited place) and DROPS the
// carried selection token (node/asset/version/section/beat/round/anchor is scoped to the
// project it was made in; dragging it into an unrelated paper is the confusion his walk named).
// The per-project place is still RECORDED server-side in .cockpit.json (recordSurface), just no
// longer READ by the switch. Walked as HIM: on /artefact with a node selected, switch project →
// stay on /artefact, new corpus rides, the node token drops.
//
//   run:  node tests/j5_switch.playwright.mjs
//   deps: global `playwright`, Chromium at /opt/pw-browsers, repo venv python as python3.
//
// This writes per-project place into the REAL (gitignored) .cockpit.json; it BACKS IT UP
// and RESTORES it so the author's cockpit is untouched after the walk.
import { createRequire } from 'module';
import { spawn, execSync } from 'child_process';
import net from 'net';
import http from 'http';
import fs from 'fs';
import path from 'path';

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
function getJSON(port, p){ return new Promise((res) => {
  http.get(`http://127.0.0.1:${port}${p}`, (r) => { let b = ''; r.on('data', d => b += d); r.on('end', () => { try{ res(JSON.parse(b)); }catch(e){ res({}); } }); }).on('error', () => res({})); }); }
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

const CORPUS = 'subset-sum-itqde';
const OTHER = 'paper_falqon';        // the switch TARGET — a distinct real project ("falqon")
let scanner, cockpitPath, cockpitBackup = null, cockpitExisted = false;
(async () => {
  const repoRoot = execSync(`${PY} -c "from laplace.web.scanner import _repo_root; print(_repo_root().resolve())"`).toString().trim();
  cockpitPath = path.join(repoRoot, '.cockpit.json');
  cockpitExisted = fs.existsSync(cockpitPath);
  if(cockpitExisted) cockpitBackup = fs.readFileSync(cockpitPath);

  const port = await freePort();
  scanner = spawn(PY, ['-m', 'laplace.web.scanner', '--port', String(port)], { cwd: repoRoot, stdio: 'ignore' });
  await waitFor(`http://127.0.0.1:${port}/`);

  const b = await chromium.launch({ executablePath: CHROME });
  try {
    const pg = await b.newPage({ viewport: { width: 1400, height: 900 } });
    const pageErrors = []; pg.on('pageerror', (e) => pageErrors.push(String(e)));

    // ── VISIT /artefact for subset-sum WITH a node selected → the shell records the place,
    //    and the node token rides the URL (a selection scoped to THIS project). ──
    // (W2: /review + /projection consolidated into the ONE artefact surface.)
    const SELNODE = 'res:itqde-spectral-readout';
    console.log(`\n[j5] visit /artefact?corpus=${CORPUS}&node=${SELNODE}`);
    await pg.goto(`http://127.0.0.1:${port}/artefact?corpus=${CORPUS}&node=${encodeURIComponent(SELNODE)}`, { waitUntil: 'networkidle' });
    await pg.waitForSelector('#hy-shell', { timeout: 10000 });
    ok(new URL(pg.url()).searchParams.get('node') === SELNODE, `the selection token rides the URL on this surface (?node=${new URL(pg.url()).searchParams.get('node')})`);
    // the per-project place is still RECORDED server-side (recordSurface survives; the switch
    // simply no longer READS it — ACT5/job3). Poll the cockpit until the place lands.
    let placed = false;
    for(let i = 0; i < 40 && !placed; i++){
      const st = await getJSON(port, '/cockpit/state');
      placed = !!(st.last_surface && /\/artefact/.test(st.last_surface[CORPUS] || ''));
      if(!placed) await sleep(150);
    }
    ok(placed, `the shell still RECORDS ${CORPUS}'s place as /artefact in .cockpit.json (recorded, though the switch no longer jumps to it)`);

    // ── TYPE-TO-FILTER on THIS surface: typing "falqon" surfaces the OTHER project ──
    await pg.waitForSelector('#hy-switch-input', { timeout: 10000 });
    await pg.click('#hy-switch-input');
    await pg.type('#hy-switch-input', 'falqon', { delay: 20 });
    await pg.waitForSelector('#hy-switch-list .hy-switch-row', { timeout: 4000 });
    const rows = await pg.$$eval('#hy-switch-list .hy-switch-row', els => els.map(e => e.getAttribute('data-corpus')));
    ok(rows.includes(OTHER), `type-to-filter "falqon" finds ${OTHER} (got ${JSON.stringify(rows)})`);
    ok(rows.every(r => /falqon/i.test(r)), 'the filter narrows to matches only (no unrelated projects)');

    // ── KEYBOARD-SELECT: ↓ then enter switches project → KEEPS the current surface (/artefact),
    //    the new corpus rides, and the scoped node selection DROPS (ACT5/job3). ──
    await pg.keyboard.press('ArrowDown');
    await pg.keyboard.press('Enter');
    await pg.waitForURL(new RegExp(`corpus=${OTHER}`), { timeout: 8000 });
    const url = new URL(pg.url());
    ok(url.pathname === '/artefact', `the switch KEPT the current surface — still /artefact (got ${url.pathname})`);
    ok(url.searchParams.get('corpus') === OTHER, `the new corpus rides the switch (${url.searchParams.get('corpus')})`);
    ok(!url.searchParams.get('node'), `the scoped selection token DROPPED on the hop (node=${url.searchParams.get('node')})`);

    ok(pageErrors.length === 0, `no page errors across the run (${JSON.stringify(pageErrors)})`);
    console.log(`\nALL GREEN — ${passed} assertions`);
  } finally {
    await b.close();
    if (scanner) scanner.kill();
    // restore the author's cockpit exactly as it was (the walk leaves no trace)
    try {
      if(cockpitExisted && cockpitBackup !== null) fs.writeFileSync(cockpitPath, cockpitBackup);
      else if(!cockpitExisted && fs.existsSync(cockpitPath)) fs.unlinkSync(cockpitPath);
    } catch(e) { /* best-effort restore */ }
  }
})().catch((e) => { console.error('\n' + e.message); if (scanner) scanner.kill();
  try { if(cockpitExisted && cockpitBackup !== null) fs.writeFileSync(cockpitPath, cockpitBackup);
    else if(!cockpitExisted && fs.existsSync(cockpitPath)) fs.unlinkSync(cockpitPath); } catch(_e) {}
  process.exit(1); });
