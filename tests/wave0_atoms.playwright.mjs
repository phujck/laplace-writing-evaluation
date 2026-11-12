// Wave 0 — THE UNIVERSAL ATOMS, driven in a real browser. Follows the store_model
// harness idiom: spawn the REAL scanner, load a REAL rostered surface, and prove the
// shared-chrome atoms shell.js injects actually render.
//
//   run:  node tests/wave0_atoms.playwright.mjs
//   deps: global `playwright`, Chromium at /opt/pw-browsers, the repo venv python as
//         python3. Exits 0 all-green, non-zero on first failure.
//
// The four clauses proven live: (1) the L1 context header renders under the bar naming
// the surface + the honest scope; (2) with ?corpus=&node= it names project + selection;
// (3) the D15 arrival echo renders a door back from a stamped origin and dismisses; (4)
// the D16 rule chip rides the header (the first consumer).
import { createRequire } from 'module';
import { spawn, execSync } from 'child_process';
import net from 'net';

const require = createRequire(import.meta.url);
const PW_ROOT = execSync('npm root -g').toString().trim() + '/playwright';
const { chromium } = require(PW_ROOT);
const CHROME = execSync('ls /opt/pw-browsers/chromium-*/chrome-linux/chrome')
  .toString().trim().split('\n')[0];
const PY = 'python3';

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
    // ── (1) L1 — the context header on a rostered surface, honest scope, no project ──
    const pg = await b.newPage({ viewport: { width: 1000, height: 700 } });
    await pg.goto(`${base}/conceptric`, { waitUntil: 'domcontentloaded' });
    await pg.waitForSelector('#hy-context', { timeout: 10000 });
    const h1 = await pg.evaluate(() => document.getElementById('hy-context').innerText);
    // RE-BASELINED TO CURRENT TRUTH (W-PINS 2026-07-22): /conceptric is the growth cockpit now, and
    // the shell header prose label moved from "a view of <purpose>" to the em-dash "— <purpose>"
    // idiom (shell.js hy-ctx-purpose). The surface's roster TITLE is being renamed live under the
    // interface rebuild (Conceptric → Cockpit → Grow …), so we resolve the expected title from the
    // LIVE ROSTER rather than pinning a literal that churn keeps invalidating. The ATOM is unchanged:
    // the L1 header names the surface (roster title) + carries its "— <purpose>" label + the honest
    // no-project scope "all projects" (shell.js R1 token, stable).
    const cxRow = await pg.evaluate(async () => {
      const r = await (await fetch('/shared/views')).json();
      const row = (r.views || []).find((v) => (v.path || '').replace(/\?.*/, '') === '/conceptric');
      return row ? { title: row.title || row.id, purpose: row.purpose || '' } : null;
    });
    ok(cxRow && h1.includes(cxRow.title),
       `header names the surface by its roster title ("${cxRow && cxRow.title}"; got ${JSON.stringify(h1)})`);
    ok(/—\s*\S/.test(h1), 'header carries the "— <purpose>" prose label (superseded "a view of")');
    ok(/all projects/.test(h1), 'no project in view → the honest scope "all projects" (R1)');
    ok(await pg.$('#hy-context .rule-chip') !== null, 'D16 rule chip rides the header (first consumer)');

    // ── (2) L1 — with ?corpus=&node= the header names project + selection ──
    await pg.goto(`${base}/conceptric?corpus=demo-corpus&node=def:spectral-surface`,
      { waitUntil: 'domcontentloaded' });
    await pg.waitForSelector('#hy-context', { timeout: 10000 });
    const h2 = await pg.evaluate(() => document.getElementById('hy-context').innerText);
    ok(/demo-corpus/.test(h2), `header names the project from ?corpus= (got ${JSON.stringify(h2)})`);
    ok(/def:spectral-surface/.test(h2), 'header names the selection from ?node=');

    // ── (3) D15 — the arrival echo from a stamped origin (fresh page: no prior pagehide
    //         stamp to overwrite; addInitScript seeds the origin before shell.js reads it) ──
    const ep = await b.newPage({ viewport: { width: 1000, height: 700 } });
    await ep.addInitScript(() => {
      try {
        sessionStorage.setItem('hymn.origin', JSON.stringify({
          path: '/artefact?corpus=demo-corpus&node=def:spectral-surface',
          surface: 'artefact',
          selection: { key: 'node', val: 'def:spectral-surface' },
          ts: Date.now(),
        }));
      } catch (e) { /* opaque origin (about:blank) — ignored */ }
    });
    await ep.goto(`${base}/conceptric?corpus=demo-corpus`, { waitUntil: 'domcontentloaded' });
    await ep.waitForSelector('#hy-context .hy-from', { timeout: 10000 });
    const echo = await ep.evaluate(() => {
      const a = document.querySelector('#hy-context .hy-from');
      return { text: a.innerText, href: a.getAttribute('href') };
    });
    ok(/from/.test(echo.text) && /def:spectral-surface/.test(echo.text),
      `the echo names where you came FROM (got ${JSON.stringify(echo.text)})`);
    // RE-BASELINED TO CURRENT TRUTH (W-PINS 2026-07-22): the echo names the origin surface by its
    // LIVE ROSTER TITLE (shell.js renderEcho: fromRow.title), which the surface roster now authors
    // as "Read · Judge" for /artefact (superseding the literal "Artefact"). The ATOM is unchanged —
    // the echo is roster-resolved — so we resolve the expected title from the live roster instead of
    // pinning a literal that surface renames churn; the assertion tracks the roster, not a fixed word.
    const artefactTitle = await ep.evaluate(async () => {
      const r = await (await fetch('/shared/views')).json();
      const row = (r.views || []).find((v) => (v.path || '').replace(/\?.*/, '') === '/artefact');
      return row ? (row.title || row.id) : null;
    });
    ok(artefactTitle && echo.text.includes(artefactTitle),
      `the echo names the origin surface by its roster title (roster-resolved; title="${artefactTitle}", got ${JSON.stringify(echo.text)})`);
    ok(/\/artefact/.test(echo.href), `the echo is a real door back to the origin (href ${echo.href})`);
    await ep.click('#hy-context .hy-from-x');
    ok(await ep.$('#hy-context .hy-fromwrap') === null, 'the × dismisses the echo');

    // ── (4) same-surface origin does NOT echo (Back stays honest) ──
    const sp = await b.newPage({ viewport: { width: 1000, height: 700 } });
    await sp.addInitScript(() => {
      try {
        sessionStorage.setItem('hymn.origin', JSON.stringify({
          path: '/conceptric?corpus=demo-corpus&node=other', surface: 'conceptric',
          selection: { key: 'node', val: 'other' }, ts: Date.now(),
        }));
      } catch (e) {}
    });
    await sp.goto(`${base}/conceptric?corpus=demo-corpus`, { waitUntil: 'domcontentloaded' });
    await sp.waitForSelector('#hy-context', { timeout: 10000 });
    await sp.waitForTimeout(200);
    ok(await sp.$('#hy-context .hy-from') === null,
      'a same-surface origin renders NO echo (the echo is an addition, never a hijack)');

    console.log(`\nALL GREEN — ${passed} assertions`);
  } finally {
    await b.close();
    if (scanner) scanner.kill();
  }
})().catch((e) => { console.error('\n' + e.message); if (scanner) scanner.kill(); process.exit(1); });
