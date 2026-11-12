// READER DEFAULT RESOLUTION — his 2026-07-23 walk finding (RW-20260723-134848): in read mode
// artefact-panes.mjs's currentRevision() fell straight to CTX.current_artefact whenever no
// ?version= rode the URL — and current_artefact resolves to the LIVE editor candidate (main.pdf)
// whenever the release state machine isn't literally "RELEASED", even when a real minted release
// sits right beside it on disk (paper_falqon: finalize.json + paper-falqon-2026-07-21-r2.pdf exist,
// but no release/state.json sidecar, so current_artefact.kind stays "candidate" forever). A bare
// reader arrival then rendered whatever the last probe/editor compile happened to leave in main.pdf
// instead of the real paper.
//
// The fix (currentRevision(), artefact-panes.mjs): when current_artefact.kind !== "release", prefer
// the newest "release"-kind row from the SAME /shared/versions rail (already server-vetted — a row
// only carries a pdf path when shared_ui._release_rows confirmed the file exists on disk) over the
// raw candidate. ?version= still wins outright; the edit posture's live loop (EDIT_PDF_REL) is
// untouched — activePdfRel() checks it FIRST, unconditionally, before ever calling currentRevision().
//
// This harness stubs /artefact/context + /shared/versions deterministically (the exact shape the
// bug reproduces on: kind:"candidate", version_id:null, a newer release row with a real pdf path)
// so the assertion holds regardless of what today's live corpus main.pdf happens to contain.
//
//   run:  node tests/reader_default_resolution.playwright.mjs
//   deps: global playwright, Chromium at /opt/pw-browsers, the repo venv python on PATH.
import { createRequire } from 'module';
import { spawn, execSync } from 'child_process';
import net from 'net';
import http from 'http';

const require = createRequire(import.meta.url);
const { chromium } = require(execSync('npm root -g').toString().trim() + '/playwright');
const CHROME = execSync('ls /opt/pw-browsers/chromium-*/chrome-linux/chrome').toString().trim().split('\n')[0];
const PY = 'python3';
const CORPUS = 'stub-corpus';

let passed = 0;
function ok(cond, msg) { if (!cond) throw new Error('ASSERT FAILED: ' + msg); passed++; console.log('  ok -', msg); }
function freePort() { return new Promise((res) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); }); }
function waitFor(url, tries = 60) {
  return new Promise((res, rej) => { const tick = (n) => { const req = http.get(url, (r) => { r.resume(); res(true); });
    req.on('error', () => n <= 0 ? rej(new Error('server never came up')) : setTimeout(() => tick(n - 1), 250)); }; tick(tries); });
}

// a real, minimal, valid one-page PDF (200x200 blank) so pdf.js can actually render whatever
// /projection/pdf is stubbed to return — the assertion is about WHICH file is requested, but a
// garbage body would make pdf.js retry/error rather than settle, which would make page-count and
// badge assertions racy.
const BLANK_PDF_B64 = 'JVBERi0xLjMKJeLjz9MKMSAwIG9iago8PAovUHJvZHVjZXIgKHB5cGRmKQo+PgplbmRvYmoKMiAwIG9iago8PAovVHlwZSAvUGFnZXMKL0NvdW50IDEKL0tpZHMgWyA0IDAgUiBdCj4+CmVuZG9iagozIDAgb2JqCjw8Ci9UeXBlIC9DYXRhbG9nCi9QYWdlcyAyIDAgUgo+PgplbmRvYmoKNCAwIG9iago8PAovVHlwZSAvUGFnZQovUmVzb3VyY2VzIDw8Cj4+Ci9NZWRpYUJveCBbIDAuMCAwLjAgMjAwIDIwMCBdCi9QYXJlbnQgMiAwIFIKPj4KZW5kb2JqCnhyZWYKMCA1CjAwMDAwMDAwMDAgNjU1MzUgZiAKMDAwMDAwMDAxNSAwMDAwMCBuIAowMDAwMDAwMDU0IDAwMDAwIG4gCjAwMDAwMDAxMTMgMDAwMDAgbiAKMDAwMDAwMDE2MiAwMDAwMCBuIAp0cmFpbGVyCjw8Ci9TaXplIDUKL1Jvb3QgMyAwIFIKL0luZm8gMSAwIFIKPj4Kc3RhcnR4cmVmCjI1NgolJUVPRgo=';
const BLANK_PDF = Buffer.from(BLANK_PDF_B64, 'base64');

// THE BUG SHAPE: a live "candidate" (main.pdf, no version_id — the s8-probe-style stub compile
// case) is current_artefact, while a real minted release sits in the versions rail.
const CTX = {
  corpus: CORPUS, name: CORPUS, kind: 'conceptric',
  current_artefact: { pdf: 'stub/main.pdf', tex: 'stub/main.tex', kind: 'candidate', version_id: null },
  pdf_endpoint: '/projection/pdf', tex_endpoint: '/projection/tex', feedback_endpoint: '/projection/feedback',
};
const VERSIONS = {
  corpus: CORPUS,
  rows: [
    // newest-first, exactly as shared_ui.versions_join orders them.
    { kind: 'editor-save', id: 'save-1', ts: '2026-07-23T12:16:23Z', label: 'editor · author',
      paths: ['stub/editor_saves/save-1', 'stub/editor_saves/save-1/main.tex'], state: 'saved' },
    { kind: 'release', id: 'stub-paper-r2', ts: '2026-07-21T14:26:37', label: 'the real paper (r2)',
      paths: ['stub/release/finalize.json', 'stub/stub-paper-r2.pdf'], state: 'finalized' },
    { kind: 'round', id: 'r1', ts: '2026-07-19T00:00:00Z', label: 'round 1',
      paths: ['stub/rounds/harnessed/mech_r1.json'], state: 'locked' },
    { kind: 'release', id: 'stub-paper-r1', ts: '2026-07-11T00:00:00Z', label: 'stub-paper-r1',
      paths: ['stub/stub-paper-r1.pdf'], state: 'minted' },
  ],
  counts: { total: 4, release: 2, round: 1, 'editor-save': 1 },
  truncated: false, omitted: 0, never_run: false,
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
    const pdfReqs = [];

    await pg.route('**/artefact/context**', (r) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(CTX) }));
    await pg.route('**/shared/plan**', (r) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ sections: [] }) }));
    await pg.route('**/shared/versions**', (r) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(VERSIONS) }));
    await pg.route('**/review/nodemap**', (r) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ present: false, fresh: false }) }));
    await pg.route('**/review/findings**', (r) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ by_node: [], unanchored: [], counts: { hard: 0, soft: 0, deferred: 0, total: 0, nodes_anchored: 0, n_unanchored: 0 } }) }));
    await pg.route('**/review/dismissals**', (r) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ rows: [], counts: { classes: 0, dismissals: 0, stale: 0, machine: 0, author: 0 } }) }));
    await pg.route('**/projection/pdf**', (r) => {
      const u = new URL(r.request().url());
      pdfReqs.push(u.searchParams.get('file'));
      return r.fulfill({ status: 200, contentType: 'application/pdf', body: BLANK_PDF });
    });

    console.log(`\n[reader-default] fresh read-mode arrival, no ?version= — candidate current_artefact + a newer release row`);
    await pg.addInitScript(() => { try { sessionStorage.setItem('art-posture', 'read'); } catch (_e) {} });
    await pg.goto(`http://127.0.0.1:${port}/artefact?corpus=${CORPUS}`, { waitUntil: 'domcontentloaded' });
    await pg.waitForSelector('#art-rev:not(:empty)', { timeout: 12000 });

    // poll pdfReqs (node-side array, filled by the route interceptor above) until the reader
    // has actually fired its /projection/pdf request — a few awaits deep inside renderPdf.
    const start = Date.now();
    while (pdfReqs.length === 0 && Date.now() - start < 10000) await new Promise((r2) => setTimeout(r2, 100));

    ok(pdfReqs.length >= 1, `the reader fired a /projection/pdf request (${JSON.stringify(pdfReqs)})`);
    ok(pdfReqs[0] === 'stub/stub-paper-r2.pdf',
      `the DEFAULT read view requests the newest RELEASE pdf, never the live candidate (${JSON.stringify(pdfReqs)})`);
    ok(!pdfReqs.includes('stub/main.pdf'),
      `the live editor candidate (main.pdf) is never leaked to the reader default (${JSON.stringify(pdfReqs)})`);

    const badge = await pg.$eval('#art-rev', (e) => e.textContent);
    ok(/release/.test(badge), `the badge names the release kind (${JSON.stringify(badge)})`);
    ok(/the real paper \(r2\)/.test(badge), `the badge carries the release row's own label (${JSON.stringify(badge)})`);
    ok(!/release.*release/i.test(badge), `the badge never stutters kind+label (${JSON.stringify(badge)})`);

    ok(!new URL(pg.url()).searchParams.has('version'), 'no ?version= was written by the default resolution itself (it is a display default, not a navigation)');

    // ── the ?version= override still wins outright over the new default ────────────
    console.log('\n[reader-default] ?version=stub-paper-r1 still overrides the default');
    pdfReqs.length = 0;
    await pg.goto(`http://127.0.0.1:${port}/artefact?corpus=${CORPUS}&version=stub-paper-r1`, { waitUntil: 'domcontentloaded' });
    const start2 = Date.now();
    while (pdfReqs.length === 0 && Date.now() - start2 < 10000) await new Promise((r2) => setTimeout(r2, 100));
    ok(pdfReqs.includes('stub/stub-paper-r1.pdf'), `?version= still resolves its own row's pdf (${JSON.stringify(pdfReqs)})`);

    // ── no release row exists at all → falls to current_artefact, badge does not stutter ──
    console.log('\n[reader-default] no release rows on disk → the candidate itself, badge still honest');
    await pg.route('**/shared/versions**', (r) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ...VERSIONS, rows: VERSIONS.rows.filter((row) => row.kind !== 'release'), counts: { total: 2, release: 0, round: 1, 'editor-save': 1 } }) }));
    pdfReqs.length = 0;
    await pg.goto(`http://127.0.0.1:${port}/artefact?corpus=${CORPUS}`, { waitUntil: 'domcontentloaded' });
    const start3 = Date.now();
    while (pdfReqs.length === 0 && Date.now() - start3 < 10000) await new Promise((r2) => setTimeout(r2, 100));
    ok(pdfReqs.includes('stub/main.pdf'), `with no banked release, the live candidate is the only honest choice (${JSON.stringify(pdfReqs)})`);
    const badge2 = await pg.$eval('#art-rev', (e) => e.textContent);
    ok(badge2.trim() === 'a candidate', `the no-release badge reads plainly, no stutter (${JSON.stringify(badge2)})`);

    ok(pageErrors.length === 0, `no page errors across the walk (${JSON.stringify(pageErrors)})`);
    console.log(`\nALL GREEN — ${passed} assertions`);
  } finally { await b.close(); if (scanner) scanner.kill(); }
})().catch((e) => { console.error('\n' + e.message); if (scanner) scanner.kill(); process.exit(1); });
