// P2 — THE REVISION-COUNT PARITY CLAUSE (browser tier): the STANDING version rail on the
// artefact surface renders EXACTLY as many rows as the disk holds revisions — so "I can only
// see one of them" is structurally impossible. The disk truth is enumerated SERVER-SIDE (the
// tests/test_versions_join.py idiom, exposed at /artefact/parity), and this harness asserts
// the RENDERED rail-row count matches it (and that the join covers every disk artefact, and
// is not truncated). Real Chromium against a real scanner; exit 0 all-green.
//
// PLUS A1 — THE BACK BUTTON IS HONEST: the W2 judge proved headless that clicking a rail row
// wrote ?version= and swapped the reader, but browser Back only ever moved the URL — the
// badge and the rendered pdf both stayed frozen on the clicked revision. artefact-panes.mjs
// now subscribes to the store (which store.mjs's popstate listener notifies unconditionally),
// so this harness clicks a revision, goes Back, and asserts BOTH the URL AND the rendered
// state (badge text + the pdf actually requested) really returned to the current artefact —
// then goes Forward and asserts the clicked revision is restored the same way.
//
//   run:  node tests/parity_versions.playwright.mjs
//   deps: global `playwright`, Chromium at /opt/pw-browsers, the repo venv python as python3.
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
function ok(cond, msg){ if(!cond) throw new Error('ASSERT FAILED: ' + msg); passed++; console.log('  ok -', msg); }
function freePort(){ return new Promise((res, rej) => {
  const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); s.on('error', rej); }); }
function waitFor(url, tries = 60){ return new Promise((res, rej) => {
  const tick = (n) => { const req = http.get(url, (r) => { r.resume(); res(true); });
    req.on('error', () => n <= 0 ? rej(new Error('server never came up')) : setTimeout(() => tick(n - 1), 250)); }; tick(tries); }); }
function getJSON(port, p){ return new Promise((res) => {
  http.get(`http://127.0.0.1:${port}${p}`, (r) => { let b = ''; r.on('data', d => b += d); r.on('end', () => { try{ res(JSON.parse(b)); }catch(e){ res({}); } }); }).on('error', () => res({})); }); }

let scanner;
(async () => {
  const repoRoot = execSync(`${PY} -c "from laplace.web.scanner import _repo_root; print(_repo_root().resolve())"`).toString().trim();
  const port = await freePort();
  scanner = spawn(PY, ['-m', 'laplace.web.scanner', '--port', String(port)], { cwd: repoRoot, stdio: 'ignore' });
  await waitFor(`http://127.0.0.1:${port}/`);

  // THE DISK TRUTH (server-side, the test_versions_join enumeration idiom, exposed).
  const parity = await getJSON(port, `/artefact/parity?corpus=${CORPUS}`);
  ok(parity && typeof parity.rows_total === 'number', 'the parity read exposes the disk-truth revision count');
  ok(parity.covered === true, `the join COVERS every disk artefact (${JSON.stringify(parity.disk)})`);
  ok(parity.truncated === false, 'the join is not truncated (every revision fits the rail)');
  ok(parity.rows_total > 1, `there is more than one revision to see (${parity.rows_total}) — the clause is non-vacuous`);

  const b = await chromium.launch({ executablePath: CHROME });
  try {
    const pg = await b.newPage({ viewport: { width: 1400, height: 900 } });
    const pageErrors = []; pg.on('pageerror', (e) => pageErrors.push(String(e)));

    console.log(`\n[parity] open /artefact?corpus=${CORPUS} and open the standing rail`);
    await pg.goto(`http://127.0.0.1:${port}/artefact?corpus=${CORPUS}`, { waitUntil: 'domcontentloaded' });
    // the STANDING rail: the collapsed strip carries the count at first paint … (W2 reface:
    // the count rides the strip-head revision chip — `#art-rail-strip-head .hy-chip` renders
    // "<N> revisions" from the SAME versions-join counts.total the parity read enumerates).
    await pg.waitForSelector('#art-rail-strip-head .hy-chip', { timeout: 15000 });
    const strip = await pg.$eval('#art-rail-strip-head .hy-chip', e => e.textContent);
    ok(new RegExp('\\b' + parity.rows_total + '\\b').test(strip),
      `the collapsed rail strip states the revision count (${JSON.stringify(strip)} carries ${parity.rows_total})`);

    // … one click opens the full rail; every revision is a row.
    await pg.click('#art-rail-toggle');
    await pg.waitForSelector('#art-rail-body .hy-rail-row', { timeout: 8000 });
    const rendered = await pg.$$eval('#art-rail-body .hy-rail-row', els => els.length);
    ok(rendered === parity.rows_total,
      `THE PARITY: the rendered rail shows EVERY revision — rendered ${rendered} == disk truth ${parity.rows_total}`);

    // ── A1 — THE BACK BUTTON, PROVEN: click a revision, Back drops it (URL + render both),
    // Forward restores it (URL + render both). Track every /projection/pdf request via
    // page.route (not passive page.on('request')) so a browser-cache hit on the SAME url
    // (going back to the current artefact's pdf, already requested at first paint) still
    // shows up here — route interception sees the request regardless of caching.
    const pdfReqs = [];
    await pg.route('**/projection/pdf*', async (route) => {
      const u = new URL(route.request().url());
      pdfReqs.push(u.searchParams.get('file'));
      await route.continue();
    });
    // the pdf fetch is a few awaits deep inside renderPdf (ensurePdfjs → getDocument), so a
    // request can land AFTER the badge text already updated — poll pdfReqs rather than
    // asserting it right after a badge-change wait (that raced and caught only the stale
    // pre-click request on the first pass of writing this harness).
    function waitForPdfReq(target, timeout = 8000) {
      return new Promise((resolve, reject) => {
        const start = Date.now();
        (function tick() {
          if (pdfReqs.includes(target)) return resolve();
          if (Date.now() - start > timeout)
            return reject(new Error(`timed out waiting for a /projection/pdf request for ${JSON.stringify(target)} (saw ${JSON.stringify(pdfReqs)})`));
          setTimeout(tick, 50);
        })();
      });
    }

    const ctx = await getJSON(port, `/artefact/context?corpus=${CORPUS}`);
    const currentPdf = ctx && ctx.current_artefact && ctx.current_artefact.pdf;
    ok(!!currentPdf, 'the context names the current artefact pdf (the Back-button baseline)');

    const versions = await getJSON(port, `/shared/versions?corpus=${CORPUS}`);
    const candidate = (versions.rows || []).find((r) => {
      const pdf = (r.paths || []).find((p) => /\.pdf$/i.test(p));
      return pdf && pdf !== currentPdf;
    });
    ok(!!candidate, 'a revision other than the current artefact is openable — a real switch to prove Back against');
    const pickPdf = (candidate.paths || []).find((p) => /\.pdf$/i.test(p));

    const beforeBadge = await pg.$eval('#art-rev', (e) => e.textContent);
    // the rail is already open (from the parity check above); its row ids for a
    // snapshot/release row are the bare disk id (round rows alone get the composite _rid —
    // A2 — so this reads the SAME id the /shared/versions JSON just gave us).
    const openSel = `.art-open[data-open="${candidate.id}"]`;
    await pg.waitForSelector(openSel, { timeout: 8000 });
    console.log(`\n[back-button] click revision ${JSON.stringify(candidate.id)} (${candidate.kind})`);
    pdfReqs.length = 0;
    await pg.click(openSel);
    await pg.waitForFunction((prev) => document.querySelector('#art-rev').textContent !== prev,
      beforeBadge, { timeout: 8000 });
    let u = new URL(pg.url());
    ok(u.searchParams.get('version') === candidate.id, `clicking the row wrote ?version=${candidate.id} (${pg.url()})`);
    const clickedBadge = await pg.$eval('#art-rev', (e) => e.textContent);
    ok(clickedBadge !== beforeBadge, `the badge switched to the clicked revision (${JSON.stringify(clickedBadge)})`);
    await waitForPdfReq(pickPdf);
    ok(true, `the reader requested the clicked revision's pdf (${pickPdf})`);

    console.log('[back-button] history.back() — popstate must re-render, not just move the URL');
    pdfReqs.length = 0;
    await pg.evaluate(() => history.back());
    await pg.waitForFunction((prev) => document.querySelector('#art-rev').textContent !== prev,
      clickedBadge, { timeout: 8000 });
    u = new URL(pg.url());
    ok(!u.searchParams.has('version'), `Back drops ?version= from the URL (${pg.url()})`);
    const backBadge = await pg.$eval('#art-rev', (e) => e.textContent);
    ok(backBadge === beforeBadge, `Back restores the badge to the current revision (${JSON.stringify(backBadge)}, was ${JSON.stringify(beforeBadge)})`);
    await waitForPdfReq(currentPdf);
    ok(true, `Back re-renders the reader — the current artefact's pdf was re-requested (${currentPdf})`);

    console.log('[back-button] history.forward() — restores the clicked revision, URL AND render');
    pdfReqs.length = 0;
    await pg.evaluate(() => history.forward());
    await pg.waitForFunction((prev) => document.querySelector('#art-rev').textContent !== prev,
      backBadge, { timeout: 8000 });
    u = new URL(pg.url());
    ok(u.searchParams.get('version') === candidate.id, `Forward restores ?version=${candidate.id} (${pg.url()})`);
    const fwdBadge = await pg.$eval('#art-rev', (e) => e.textContent);
    ok(fwdBadge === clickedBadge, `Forward restores the clicked revision's badge (${JSON.stringify(fwdBadge)})`);
    await waitForPdfReq(pickPdf);
    ok(true, `Forward re-requests the clicked revision's pdf (${pickPdf})`);

    ok(pageErrors.length === 0, `no page errors across the run (${JSON.stringify(pageErrors)})`);
    console.log(`\nALL GREEN — ${passed} assertions`);
  } finally {
    await b.close();
    if (scanner) scanner.kill();
  }
})().catch((e) => { console.error('\n' + e.message); if (scanner) scanner.kill(); process.exit(1); });
