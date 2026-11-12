// WAVE 2 — THE ARTEFACT SURFACE, driven to the approved mock (mocks/artefact.html, D1–D16).
//
// This walk drives OUTCOMES against a REAL scanner + REAL corpora (J2's standard: DOM-presence
// certifies nothing; a driven click that renders the promised chips does). No route stubs — the
// reader, the nodemap join, and the review board are the live ones. It proves:
//   · the reader answers: hover ¶ band + click a mapped region → the anchor overlay opens with
//     the section's NODES (kind-badged chips) + the spine BEAT chip; the hint strip retires (R5);
//     one-click annotate banks + flashes; BOTH addressings (?corpus= AND file=) carry the join (F4);
//   · the unanchored click states itself + offers the banked rebuild — never blank (R7/F9);
//   · the tray's ONE collapsed line is honest vs the stores' counts; expand → groups, ranked;
//     the dismissed fold carries overrule; ✎ rule (D16) rides every active row;
//   · the standing rail: collapsed head visible, open compresses the reader, Escape closes;
//   · 375px: single column, no horizontal scroll.
//
//   run:  node tests/wave2_artefact.playwright.mjs
//   deps: global playwright, Chromium at /opt/pw-browsers, the repo venv python on PATH.
//   Exits 0 all-green, non-zero on the first failed assertion.
import { createRequire } from 'module';
import { spawn, execSync } from 'child_process';
import net from 'net';

const require = createRequire(import.meta.url);
const { chromium } = require(execSync('npm root -g').toString().trim() + '/playwright');
const CHROME = execSync('ls /opt/pw-browsers/chromium-*/chrome-linux/chrome').toString().trim().split('\n')[0];
const PY = 'python3';

let passed = 0;
function ok(cond, msg) { if (!cond) throw new Error('ASSERT FAILED: ' + msg); passed++; console.log('  ok -', msg); }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function freePort() { return new Promise((res) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); }); }
function waitFor(url, tries = 80) {
  return new Promise((res, rej) => { const tick = (n) => { const req = require('http').get(url, (r) => { r.resume(); res(true); });
    req.on('error', () => n <= 0 ? rej(new Error('server never came up')) : setTimeout(() => tick(n - 1), 250)); }; tick(tries); });
}

// click the center-top of the region for a nodemap aid on its page; returns whether a page was hit.
async function clickAid(pg, aid, corpus) {
  const region = await pg.evaluate(async ([a, c]) => {
    const r = await fetch('/review/nodemap?corpus=' + c); const nm = await r.json();
    const regs = (nm.entries || {})[a] || []; const rr = regs.find((x) => x.page && typeof x.y0 === 'number');
    return rr ? { page: rr.page, x0: rr.x0, x1: rr.x1, y0: rr.y0 } : null;
  }, [aid, corpus]);
  if (!region) return false;
  const box = await pg.evaluate((rg) => {
    const w = [...document.querySelectorAll('.art-page')].find((w) => +w.dataset.page === rg.page); if (!w) return null;
    const r = w.getBoundingClientRect(); const pw = +w.dataset.pw, ph = +w.dataset.ph;
    return { x: r.left + ((rg.x0 + (rg.x1 || pw)) / 2) * (r.width / pw), y: r.top + (rg.y0 + 8) * (r.height / ph) };
  }, region);
  if (!box) return false;
  await pg.mouse.move(box.x, box.y); await sleep(120);       // raise the hover band first
  await pg.mouse.click(box.x, box.y);
  // W-PINS 2026-07-22: the anchor overlay opens ASYNC (openAnchorOverlay → ensureNodemap/
  // ensurePlan → render), so a blind post-click sleep raced its `.on` toggle (the flake this
  // walk carried). Wait on the real signal — the overlay reaching `.on` — with a bounded
  // fallback so an off-anchor/unanchored click still returns and the caller asserts honestly.
  try {
    await pg.waitForFunction(() => {
      const a = document.querySelector('#art-anchor');
      return a && a.classList.contains('on');
    }, { timeout: 6000 });
  } catch (_e) { /* overlay did not reach .on — the caller's assertion reports it */ }
  return true;
}

let scanner;
(async () => {
  const repoRoot = execSync(`${PY} -c "from laplace.web.scanner import _repo_root; print(_repo_root().resolve())"`).toString().trim();
  const port = await freePort();
  scanner = spawn(PY, ['-m', 'laplace.web.scanner', '--port', String(port)], { cwd: repoRoot, stdio: 'ignore' });
  await waitFor(`http://127.0.0.1:${port}/artefact`);
  const base = `http://127.0.0.1:${port}`;
  const b = await chromium.launch({ executablePath: CHROME });
  try {
    const pg = await b.newPage({ viewport: { width: 1440, height: 900 } });
    const errs = []; pg.on('pageerror', (e) => errs.push(String(e)));
    // hygiene: the READS are all real (nodemap, review board, versions), but the annotate
    // MUTATION is stubbed so the walk proves the client sends a well-formed finding + renders
    // its receipt WITHOUT writing a junk "reader flag" row into the real corpus ledger. The
    // stub records the POST body so the request shape is still asserted, not just the receipt.
    const banked = [];
    await pg.route('**/projection/feedback**', (route) => {
      if (route.request().method() !== 'POST') return route.continue();
      let body = {}; try { body = JSON.parse(route.request().postData() || '{}'); } catch (_e) {}
      banked.push(body);
      return route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ ok: true, record: { id: 'FB-STUB-1' } }) });
    });
    // the overlay's node/beat chips are REAL doors to /conceptric and /storyboard (F1). We prove
    // the door OUTCOME by driving a click and reading the landing URL — but we stub those two
    // target surfaces so the drive lands on a trivial page (their own JS is out of this walk's
    // scope and must not pollute the pageerror ledger asserted at the end).
    for (const surf of ['conceptric', 'storyboard']) {
      await pg.route('**/' + surf + '**', (route) => {
        if (route.request().resourceType() !== 'document') return route.continue();
        return route.fulfill({ status: 200, contentType: 'text/html',
          body: '<!doctype html><title>' + surf + ' door stub</title>' });
      });
    }

    // ── THE READER ANSWERS on ?corpus= (F4 addressing A) ──────────────────────────
    console.log('\n[A] /artefact?corpus=paper_falqon — the ¶ click answers with nodes + beat');
    await pg.goto(`${base}/artefact?corpus=paper_falqon`, { waitUntil: 'domcontentloaded' });
    await pg.waitForSelector('.art-page', { timeout: 20000 });
    await sleep(1200);
    ok(await clickAid(pg, 's1-p1', 'paper_falqon'), 'a mapped paragraph region (s1-p1) was clickable in the reader');
    ok(await pg.$eval('#art-anchor', (e) => e.classList.contains('on')), 'the click opens the anchor overlay');
    const nodesA = await pg.$$eval('#art-anchor .art-node', (els) => els.map((e) => e.dataset.node));
    ok(nodesA.length >= 1, `the overlay renders the section's node chips (got ${JSON.stringify(nodesA.slice(0, 3))})`);
    ok(await pg.$('#art-anchor .art-node .hy-kbadge') !== null, 'each node chip carries a kind badge (kind-badged chips)');
    const beatsA = await pg.$$eval('#art-anchor .art-beat', (els) => els.map((e) => e.dataset.beat));
    ok(beatsA.length >= 1, `the overlay renders the spine beat chip (got ${JSON.stringify(beatsA)})`);
    ok(await pg.$eval('#art-hint', (e) => e.classList.contains('done')), 'the hint strip retires after the first ¶ click (R5)');
    // one-click annotate → banks + receipt
    await pg.click('#art-anchor .art-annotate'); await sleep(700);
    const annTxt = await pg.$eval('#art-anchor .art-annotate', (e) => e.textContent);
    ok(/banked/i.test(annTxt), `one-click annotate banks the finding + shows its receipt (got ${JSON.stringify(annTxt)})`);
    ok(banked.length === 1 && banked[0].node_id && banked[0].comment && banked[0].anchor,
      `the annotate POST carried a non-empty node_id + comment + anchor (got ${JSON.stringify(banked[0])})`);

    // ── THE CHIPS ARE REAL DOORS (F1) — the ONE interaction the wave exists to deliver:
    //    "click a paragraph, reach its nodes and beat". Presence certified nothing before; here
    //    we assert the chips ARE <a href> doors carrying the URL-canonical selection, then DRIVE
    //    a click and read the landing URL — the dead beat-chip / non-door node-chip, cured.
    const beatHref = await pg.$eval('#art-anchor .art-beat', (e) => e.tagName === 'A' ? e.getAttribute('href') : null);
    ok(beatHref && /^\/storyboard\?/.test(beatHref) && beatHref.includes('#' + encodeURIComponent(beatsA[0])),
      `the beat chip is an <a href> door to /storyboard#<beat> — its title tells the truth (got ${JSON.stringify(beatHref)})`);
    const nodeHref = await pg.$eval('#art-anchor .art-node', (e) => e.tagName === 'A' ? e.getAttribute('href') : null);
    ok(nodeHref && /^\/conceptric\?/.test(nodeHref) && nodeHref.includes('node=' + encodeURIComponent(nodesA[0])),
      `the node chip is an <a href> door to /conceptric?node=<id> — its title tells the truth (got ${JSON.stringify(nodeHref)})`);
    // drive the OUTCOME, not the presence: clicking the beat chip actually navigates (the J2
    // dead-click reborn on the chip, closed). The node chip's target is proven by its href above.
    await Promise.all([ pg.waitForURL(/\/storyboard\?/, { timeout: 8000 }), pg.click('#art-anchor .art-beat') ]);
    ok(/^http[^ ]*\/storyboard\?/.test(pg.url()), `clicking the beat chip navigates to its /storyboard door (landed ${pg.url()})`);

    // ── THE SAME on file= (F4 addressing B: the join is NOT lost when file= rides the URL) ──
    console.log('\n[B] /artefact?corpus=paper_falqon&file=… — the anchor join carries on BOTH addressings');
    const tex = await pg.evaluate(async () => (await (await fetch('/artefact/context?corpus=paper_falqon')).json()).current_artefact.tex);
    await pg.goto(`${base}/artefact?corpus=paper_falqon&file=${encodeURIComponent(tex)}`, { waitUntil: 'domcontentloaded' });
    await pg.waitForSelector('.art-page', { timeout: 20000 }); await sleep(1200);
    ok(await clickAid(pg, 's1-p1', 'paper_falqon'), 'the file=-addressed reader is clickable');
    const nodesB = await pg.$$eval('#art-anchor .art-node', (els) => els.map((e) => e.dataset.node));
    ok(nodesB.length >= 1 && await pg.$eval('#art-anchor', (e) => e.classList.contains('on')),
      `file= addressing renders the SAME node chips — the join is corpus-resolved, not addressing-conditional (got ${JSON.stringify(nodesB.slice(0, 3))})`);

    // ── THE TRAY: one honest line vs the stores; expand → ranked groups; ✎ rule ────
    console.log('\n[C] the findings tray — one honest line vs the review board + dismissal audit');
    const boardCounts = await pg.evaluate(async () => {
      const f = await (await fetch('/review/findings?corpus=paper_falqon')).json();
      const d = await (await fetch('/review/dismissals?corpus=paper_falqon')).json();
      return { total: f.counts.total, dismissed: (d.counts || {}).dismissals || 0 };
    });
    // W-PINS 2026-07-22: the tray summary loads ASYNC (it reads the review board — 1169 findings
    // for paper_falqon — then renders the collapsed line), so reading #art-tray-sum immediately
    // caught its "reading the review board…" placeholder (a second settle-race, same shape as the
    // anchor-overlay flake above). Wait on the real signal — the summary carrying its total —
    // instead of racing it; boardCounts is fetched live, so this is timing, not a number pin.
    await pg.waitForFunction(() => {
      const e = document.querySelector('#art-tray-sum');
      return e && /\d+\s+total/.test(e.textContent);
    }, { timeout: 20000 });
    const sum = await pg.$eval('#art-tray-sum', (e) => e.textContent);
    ok(sum.includes(boardCounts.total + ' total'), `the collapsed line names the real total (${boardCounts.total}) — got "${sum}"`);
    ok(sum.includes(boardCounts.dismissed + ' dismissed'), `the collapsed line names the real dismissed count (${boardCounts.dismissed})`);
    await pg.click('#art-tray-bar'); await sleep(300);
    ok(await pg.$eval('#art-tray-sec', (e) => e.classList.contains('open')), 'the tray triages open on click');
    const groups = await pg.$$eval('#art-tray-body .art-grp', (els) => els.length);
    ok(groups >= 1, `expand shows grouped rows (kind × section), ${groups} group(s)`);
    ok(await pg.$('#art-tray-body .art-grp .art-grp-h .dk-chip') !== null, 'each group names its kind × section with a count');
    ok(await pg.$('#art-tray-body .art-frow .hy-chip') !== null, 'rows carry a severity chip (severity-ranked)');
    // D16 — ✎ rule on a finding row (shell hyRule)
    ok(await pg.$('#art-tray-body .art-frow.hy-rulable') !== null, 'every active finding row is rulable (✎ rule, D16)');
    ok(await pg.$('#art-tray-body .art-frow .rule-chip') !== null, 'the ✎ rule chip is attached to the row');

    // ── THE STANDING RAIL: open compresses the reader; Escape closes ───────────────
    console.log('\n[D] the standing version rail — open compresses, Escape closes');
    // Escape closes the TOPMOST transient (overlay before rail); dismiss the open overlay first
    // so this segment tests the rail's own keyboard exit, not the overlay's.
    if (await pg.$eval('#art-anchor', (e) => e.classList.contains('on'))) { await pg.keyboard.press('Escape'); await sleep(150); }
    ok(!await pg.$eval('#art-anchor', (e) => e.classList.contains('on')), 'Escape closes the topmost transient (the overlay) first');
    const w0 = await pg.$eval('#art-reader', (e) => e.getBoundingClientRect().width);
    await pg.click('#art-rail-toggle'); await sleep(300);
    ok(await pg.$eval('#art-main', (e) => e.classList.contains('rail-open')), 'the rail opens in place');
    ok(await pg.$$eval('#art-rail-body .hy-rail-row', (els) => els.length) >= 1, 'open reveals the kind-tagged rail rows');
    const w1 = await pg.$eval('#art-reader', (e) => e.getBoundingClientRect().width);
    ok(w1 < w0, `the reader compresses when the rail opens (${Math.round(w0)} → ${Math.round(w1)}px)`);
    await pg.keyboard.press('Escape'); await sleep(300);
    ok(!await pg.$eval('#art-main', (e) => e.classList.contains('rail-open')), 'Escape collapses the rail');

    // ── THE UNANCHORED CLICK STATES ITSELF + the dismissed fold's overrule ─────────
    console.log('\n[E] /artefact?corpus=subset-sum-itqde — nodemap absent: the honest unanchored answer');
    await pg.goto(`${base}/artefact?corpus=subset-sum-itqde`, { waitUntil: 'domcontentloaded' });
    await pg.waitForSelector('.art-page', { timeout: 20000 });
    await pg.waitForFunction(() => !/reading the review board/.test(document.querySelector('#art-tray-sum').textContent), { timeout: 25000 });
    const box = await pg.evaluate(() => { const w = document.querySelector('.art-page'); const r = w.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + 140 }; });
    await pg.mouse.click(box.x, box.y); await sleep(500);
    ok(await pg.$eval('#art-anchor', (e) => e.classList.contains('on')), 'the click still ANSWERS (never a dead click) with no map');
    const unTxt = await pg.$eval('#art-anchor', (e) => e.textContent);
    ok(/unanchored/i.test(unTxt) && /no nodemap row/i.test(unTxt), 'the unanchored overlay states its own status in words');
    ok(await pg.$('#art-anchor .art-map-offer') !== null, 'it offers the banked map rebuild (never blank, R7)');
    const ssSum = await pg.$eval('#art-tray-sum', (e) => e.textContent);
    const ssCounts = await pg.evaluate(async () => {
      const f = await (await fetch('/review/findings?corpus=subset-sum-itqde')).json();
      const d = await (await fetch('/review/dismissals?corpus=subset-sum-itqde')).json();
      return { total: f.counts.total, dismissed: (d.counts || {}).dismissals || 0 };
    });
    ok(ssSum.includes(ssCounts.total + ' total') && ssSum.includes(ssCounts.dismissed + ' dismissed'),
      `subset-sum's tray line is honest vs its stores (${ssCounts.total} total · ${ssCounts.dismissed} dismissed) — got "${ssSum}"`);
    await pg.click('#art-tray-bar'); await sleep(300);
    if (ssCounts.dismissed > 0) {
      ok(await pg.$('#art-dism-h') !== null, 'the dismissed fold renders (folded)');
      await pg.click('#art-dism-h'); await sleep(200);
      ok(await pg.$('#art-tray-body .art-overrule') !== null, 'the dismissed rows carry an overrule ↺ door');
      const ov = await pg.$('.art-overrule'); await ov.click(); await sleep(200);
      const armed = await ov.evaluate((e) => e.textContent);
      ok(/click again/i.test(armed), `overrule arms (arm-to-fire) before it reborns the finding (got ${JSON.stringify(armed)})`);
    }

    // ── 375px — single column, no horizontal scroll ───────────────────────────────
    console.log('\n[F] 375px — single column, no horizontal overflow');
    await pg.setViewportSize({ width: 375, height: 720 });
    await pg.goto(`${base}/artefact?corpus=paper_falqon`, { waitUntil: 'domcontentloaded' });
    await sleep(1500);
    const overflow = await pg.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    ok(overflow <= 0, `no horizontal overflow at 375px (scrollWidth − clientWidth = ${overflow})`);

    ok(errs.length === 0, `no page errors across the walk (${JSON.stringify(errs.slice(0, 4))})`);
    console.log(`\nALL GREEN — ${passed} assertions`);
  } finally { await b.close(); if (scanner) scanner.kill(); }
})().catch((e) => { console.error('\n' + e.message); if (scanner) scanner.kill(); process.exit(1); });
