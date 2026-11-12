// ENGINE EDITOR (E4) — the editor pulled into the one instrument, driven against a REAL scanner.
//
// The walk proves the altitude thread (the cockpit↔editor seam), the focus grammar layered onto
// the editor's own panes, and the assets both-directions door, as OUTCOMES:
//   · the cockpit's REALIGN/RESPINE decision doors to the editor altitude (?via=cockpit-tension);
//   · /artefact arrives carrying a VISIBLE return door NAMING the cockpit brief it came from;
//   · opening a finding REALLOCATES (the inspection area is claimed, the pdf sibling compacts) and
//     carries its own visible named return door; closing RESTORES the exact scroll with no residue;
//   · the entry return door lands on the cockpit BRIEF (not a wall) — the focus restored;
//   · the asset cockpit doors a node to the conceptric AND the conceptric node doors back to the
//     named asset in /assets (the mechanical both-directions seal).
//
//   run:  node tests/engine_editor.playwright.mjs
//   Exits 0 all-green, non-zero on the first failed assertion.
import { createRequire } from 'module';
import { spawn, execSync } from 'child_process';
import net from 'net';

const require = createRequire(import.meta.url);
const { chromium } = require(execSync('npm root -g').toString().trim() + '/playwright');
const CHROME = execSync('ls /opt/pw-browsers/chromium-*/chrome-linux/chrome').toString().trim().split('\n')[0];
const PY = 'python3';
const CORPUS = 'paper_falqon';
const ASSET_CORPUS = 'subset-sum-itqde';
const ASSET_ID = 'figure:F1_staircase';

let passed = 0;
function ok(cond, msg) { if (!cond) throw new Error('ASSERT FAILED: ' + msg); passed++; console.log('  ok -', msg); }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function freePort() { return new Promise((res) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); }); }
function waitFor(url, tries = 80) {
  return new Promise((res, rej) => { const tick = (n) => { const req = require('http').get(url, (r) => { r.resume(); res(true); });
    req.on('error', () => n <= 0 ? rej(new Error('server never came up')) : setTimeout(() => tick(n - 1), 250)); }; tick(tries); });
}

const PROBE_ACTOR = 'probe-eigen';
let scanner;
// #cleanup — the falqon tree is left byte-clean: snapshot the files the drive touches
// (the ledger, the tex, the tracked compile residue) and restore them; remove the untracked
// compile residue + the editor-save bank the walk mints.
const fs = require('fs');
let MD = '', SNAP = new Map(), ORIG_MAIN = '';
function cleanupFalqon() {
  try { for (const [p, buf] of SNAP) fs.writeFileSync(p, buf); } catch (e) { /* best-effort */ }
  for (const n of ['main.pdf', 'main.aux', 'main.synctex.gz', 'main.fls', 'main.fdb_latexmk',
                   'main.out', 'main.toc', 'main.bbl', 'main.blg']) {
    try { fs.unlinkSync(MD + '/' + n); } catch (e) { /* not present */ }
  }
  try { fs.rmSync(MD + '/editor_saves', { recursive: true, force: true }); } catch (e) { /* none */ }
}
(async () => {
  const repoRoot = execSync(`${PY} -c "from laplace.web.scanner import _repo_root; print(_repo_root().resolve())"`).toString().trim();
  MD = repoRoot + '/paper_falqon/manuscript';
  for (const rel of ['main.tex', 'feedback/feedback.jsonl', 'main.log', 'mainNotes.bib', 'node_index.json']) {
    try { SNAP.set(MD + '/' + rel, fs.readFileSync(MD + '/' + rel)); } catch (e) { /* absent */ }
  }
  ORIG_MAIN = (SNAP.get(MD + '/main.tex') || Buffer.from('')).toString();
  const port = await freePort();
  scanner = spawn(PY, ['-m', 'laplace.web.scanner', '--port', String(port)], { cwd: repoRoot, stdio: 'ignore' });
  await waitFor(`http://127.0.0.1:${port}/conceptric`);
  const base = `http://127.0.0.1:${port}`;
  const b = await chromium.launch({ executablePath: CHROME });
  try {
    const pg = await b.newPage({ viewport: { width: 1280, height: 720 } });
    // the session actor rides the shell identity the surface reads (never this author's name
    // hard-coded): seed it so every verdict write is attributed to the probe actor.
    await pg.addInitScript((a) => { window.__artefactActor = a; }, PROBE_ACTOR);
    const errs = []; pg.on('pageerror', (e) => errs.push(String(e)));
    // stub the map door + refuse every bank — the walk must never navigate off or bank a supersede.
    await pg.route('**/conceptric/map**', (route) => route.request().resourceType() === 'document'
      ? route.fulfill({ status: 200, contentType: 'text/html', body: '<!doctype html><title>map stub</title>' })
      : route.continue());
    await pg.route('**/growth/rule', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: false, error: 'walk: no bank' }) }));

    // ── (1) THE COCKPIT → the REALIGN door to the editor altitude ──────────────
    await pg.goto(base + '/conceptric?corpus=' + CORPUS, { waitUntil: 'networkidle' });
    await pg.waitForSelector('[data-role="brief-prose"]', { timeout: 8000 });
    // POST-REGOAL (W-TRIAGE 2026-07-22): paper_falqon's authored-goal tension is RECONCILED (the
    // REGOAL's goal supersede postdates the verdict), so the cockpit brief carries no tension card and
    // the tensions chip is disabled. The tension→REALIGN-door ORIGIN (open the tensions set → pick the
    // AUTHOR-GOAL tension → select REALIGN/RESPINE → a door to /artefact?via=cockpit-tension) was
    // WALK-PROVEN before the reconciliation and rides behind a tension-presence check. When there is
    // no live tension we enter the editor altitude by the SAME url that door builds
    // (/artefact?corpus=…&via=cockpit-tension — cockpit-panes.mjs), so every editor-altitude proof
    // below (the named return door, the finding tray reallocation + scroll restore, the assets seam)
    // stays exercised end-to-end.
    // SUPERSEDED 2026-07-22 (the shape at rest): the tension count reads from the brief
    // payload and the tension lives as a MARK in the picture (.ck-shape-tension), not a
    // chip-opened card list. The REALIGN-door origin rides the mark when one exists.
    const tCount = await pg.evaluate(async (c) => {
      const b = await (await fetch('/growth/brief?corpus=' + c)).json();
      return (b.counts || {}).tensions || 0;
    }, CORPUS);
    if (tCount >= 1) {
      await pg.waitForSelector('.ck-shape-tension[data-signature="AUTHOR-GOAL"]', { timeout: 8000 });
      await pg.click('.ck-shape-tension[data-signature="AUTHOR-GOAL"]'); await sleep(400);
      await pg.click('.ck-verb[data-verb="REALIGN/RESPINE"]'); await sleep(300);
      const rdoor = await pg.$('[data-role="realign-door"]');
      ok(!!rdoor, 'selecting REALIGN/RESPINE reveals a door to the editor altitude');
      const rhref = await pg.getAttribute('[data-role="realign-door"]', 'href');
      ok(/\/artefact\?/.test(rhref) && /via=cockpit-tension/.test(rhref),
        'the REALIGN door targets /artefact with ?via=cockpit-tension: ' + JSON.stringify(rhref));
      // click it — end-to-end nav into the editor altitude
      await Promise.all([pg.waitForNavigation({ waitUntil: 'networkidle' }), pg.click('[data-role="realign-door"]')]);
    } else {
      // reconciled: no tension to pick, so no REALIGN door to click — enter by the door's own url.
      ok((await pg.$('.ck-shape-tension')) === null,
        'the honest zero-tension shape: no tension mark in the picture, so no REALIGN-to-editor door to pick (post-REGOAL)');
      await pg.goto(base + '/artefact?corpus=' + encodeURIComponent(CORPUS) + '&via=cockpit-tension', { waitUntil: 'networkidle' });
    }
    ok(/\/artefact\?/.test(pg.url()) && /via=cockpit-tension/.test(pg.url()),
      'arrived at the editor altitude carrying ?via=cockpit-tension: ' + pg.url());

    // ── (2) /artefact arrives carrying the NAMED return door back to the brief ─
    await pg.waitForSelector('#art-thread:not([hidden]) [data-role="return-door"]', { timeout: 10000 });
    const threadLabel = (await pg.textContent('#art-thread [data-role="return-door"] .rd-label')).trim();
    // SUPERSEDED 2026-07-22 (one journey vocabulary): the door names the STAGE it returns to.
    ok(/back to grow/i.test(threadLabel) && threadLabel.includes(CORPUS),
      'the entry thread NAMES the Grow stage it came from: ' + JSON.stringify(threadLabel));
    const threadVisible = await pg.$eval('#art-thread [data-role="return-door"]', (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
    ok(threadVisible, 'the entry return door is VISIBLE (a return door that is not visible does not exist)');
    // no horizontal overflow at 1280 on /artefact
    const of1280 = await pg.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
    ok(of1280, 'zero horizontal overflow at 1280 on /artefact');

    // ── (3) OPEN A FINDING — reallocation asserted ─────────────────────────────
    // SUPERSEDED 2026-07-22 (the reading room): judgment STANDS OPEN in the margin at
    // rest — no opening click; the rows are present the moment the board loads.
    await pg.waitForSelector('#art-tray-body .art-frow[data-fid]', { timeout: 8000 });
    ok(await pg.$eval('#art-tray-sec', (e) => e.classList.contains('open')),
      'judgment stands open in the margin at rest (the judge\'s notebook, always present)');
    // centre a LOWER finding row so there is a real nonzero scroll to restore. The margin is
    // viewport-bounded now (finding #1), so the findings TRAY — not the window — is the scroller;
    // capture BOTH so the restore proof holds whichever moved. Open THAT row (in-page click, no auto-scroll).
    const fidRows = await pg.$$eval('#art-tray-body .art-frow[data-fid]', (els) => els.length);
    const openIdx = Math.min(Math.max(fidRows - 1, 0), 6);
    await pg.$$eval('#art-tray-body .art-frow[data-fid] .dk-title', (els, i) => els[i] && els[i].scrollIntoView({ block: 'center' }), openIdx); await sleep(250);
    const scrollAtOpen = await pg.evaluate(() => ({ win: Math.round(window.scrollY), tray: Math.round((document.querySelector('#art-tray-body') || {}).scrollTop || 0) }));
    ok(scrollAtOpen.win > 0 || scrollAtOpen.tray > 0,
      'a real restore proof — a nonzero scroll before opening (window, or the viewport-bounded findings tray): ' + JSON.stringify(scrollAtOpen));
    // the row at rest carries the composed-consumption badge (this finding has no composed block).
    const badgeText = await pg.$eval('#art-tray-body .art-frow[data-fid] .art-absent, #art-tray-body .art-frow[data-fid] .art-composed',
      (e) => e.textContent).catch(() => '');
    ok(/no composed account|glance/i.test(badgeText), 'the finding row renders its composed-consumption badge: ' + JSON.stringify(badgeText));

    // item 3 — capture the paper column width BEFORE opening: an overlay must never crush it.
    const paperW0 = await pg.$eval('.art-reader-col', (e) => Math.round(e.getBoundingClientRect().width));
    await pg.$$eval('#art-tray-body .art-frow[data-fid] .dk-title', (els, i) => els[i] && els[i].click(), openIdx); await sleep(450);
    ok(await pg.$eval('#art', (e) => e.classList.contains('is-inspecting')), 'opening a finding REALLOCATED the surface (#art.is-inspecting)');
    const inspectH = await pg.$eval('#art-inspect', (e) => e.getBoundingClientRect().height);
    ok(inspectH > 0, 'the inspection area claimed space in the MARGIN (visible): h=' + Math.round(inspectH));
    ok((await pg.$('#art-inspect [data-role="return-door"]')) !== null, 'the focused finding carries a visible named return door');
    ok((await pg.$('#art-tray-body .art-frow.is-open')) !== null, 'the opened finding is marked open (the object of thought)');
    // item 3 (BLOCKING) — the PAPER column is NOT crushed; the inspection reallocates the margin.
    const paperW1 = await pg.$eval('.art-reader-col', (e) => Math.round(e.getBoundingClientRect().width));
    ok(Math.abs(paperW1 - paperW0) <= 2, `the paper column width is unchanged while inspecting (${paperW1} ≈ ${paperW0}) — never crushed`);
    const inspectInMargin = await pg.evaluate(() => { const i = document.querySelector('#art-inspect'), m = document.querySelector('.art-margin'); const ir = i.getBoundingClientRect(), mr = m.getBoundingClientRect(); return ir.left >= mr.left - 2 && ir.right <= mr.right + 2; });
    ok(inspectInMargin, 'the inspection materialises in the MARGIN column (not over/into the paper)');
    // item 6a — each verb wears a non-empty, distinct consequence in plain words, in place.
    const whys = await pg.$$eval("#art-inspect [data-role='verdict-doors'] .art-verb .art-verb-why", (els) => els.map((e) => (e.textContent || '').trim()));
    ok(whys.length === 4 && whys.every((w) => w.length > 12) && new Set(whys).size === 4,
      'each verb door wears a non-empty, distinct consequence in plain outcome words (item 6a): ' + JSON.stringify(whys.map((w) => w.slice(0, 22))));
    const idoorLabel = (await pg.textContent('#art-inspect [data-role="return-door"] .rd-label')).trim();
    ok(/back to the findings tray/i.test(idoorLabel), 'the inspection return door NAMES its destination: ' + JSON.stringify(idoorLabel));

    // ── (4) CLOSE — exact restore, no residue ──────────────────────────────────
    await pg.click('#art-inspect [data-role="return-door"]'); await sleep(350);
    ok(!(await pg.$eval('#art', (e) => e.classList.contains('is-inspecting'))), 'closing the finding left the inspecting state');
    const scrollAfter = await pg.evaluate(() => ({ win: Math.round(window.scrollY), tray: Math.round((document.querySelector('#art-tray-body') || {}).scrollTop || 0) }));
    ok(Math.abs(scrollAfter.win - scrollAtOpen.win) <= 2 && Math.abs(scrollAfter.tray - scrollAtOpen.tray) <= 3,
      `exact scroll restored on close (${JSON.stringify(scrollAfter)} ≈ ${JSON.stringify(scrollAtOpen)})`);
    ok((await pg.$('#art-inspect [data-role="return-door"]')) === null, 'the return door is ABSENT from the resting inspection area (no hidden residue)');
    ok((await pg.$('#art-tray-body .art-frow.is-open')) === null, 'no finding is marked open at rest');

    // ── (4b) P5 — THE VERSION DIFF reallocates: it claims the inspection area; the rail keeps working ──
    // The prediction killed: the diff no longer carries the return-door grammar without the geometry.
    // Opening it CLAIMS the inspection area (the pdf compacts, its named door present); the SEAM that
    // also honours the diff-rail contract is that the rail — where the diff lives — is NOT dimmed:
    // the rail rides the compacted pane. Closing restores the exact scroll.
    await pg.click('#art-rail-toggle'); await sleep(350);
    await pg.waitForSelector('#art-rail-body .hy-rail-row', { timeout: 8000 });
    const snapIds = await pg.$$eval('#art-rail-body .hy-rail-row.kind-snapshot .art-diffbox', (els) => els.slice(0, 2).map((e) => e.dataset.id));
    ok(snapIds.length === 2, 'two diffable snapshot rows are available in the rail (tex-source diff): ' + JSON.stringify(snapIds));
    for (const id of snapIds) await pg.check(`.art-diffbox[data-id="${id}"]`);
    await pg.waitForSelector('#art-do-diff', { timeout: 5000 });
    await pg.$eval('#art-diffbar', (e) => e.scrollIntoView({ block: 'center' })); await sleep(150);
    const diffScrollAtOpen = await pg.evaluate(() => Math.round(window.scrollY));
    const paperWdiff0 = await pg.$eval('.art-reader-col', (e) => Math.round(e.getBoundingClientRect().width));
    await pg.click('#art-do-diff');
    await pg.waitForSelector('.art-difflines', { timeout: 15000 });
    ok(await pg.$eval('#art', (e) => e.classList.contains('is-diffing')), 'opening the diff reallocated the margin (#art.is-diffing)');
    // item 3 — the paper column is not crushed by the diff either.
    const paperWdiff1 = await pg.$eval('.art-reader-col', (e) => Math.round(e.getBoundingClientRect().width));
    ok(Math.abs(paperWdiff1 - paperWdiff0) <= 2, `the paper column width is unchanged while diffing (${paperWdiff1} ≈ ${paperWdiff0})`);
    const railOp = await pg.$eval('.art-rail-col', (e) => parseFloat(getComputedStyle(e).opacity));
    ok(railOp > 0.9, 'THE SEAM — the rail (its host, where the diff lives) is NOT dimmed: rail opacity=' + railOp);
    ok((await pg.$('#art-diffpane [data-role="return-door"]')) !== null, 'the diff carries a VISIBLE named return door');
    const ddoorLabel = (await pg.textContent('#art-diffpane [data-role="return-door"] .rd-label')).trim();
    ok(/back to the version rail/i.test(ddoorLabel), 'the diff return door NAMES its destination: ' + JSON.stringify(ddoorLabel));
    await pg.click('#art-diffpane [data-role="return-door"]'); await sleep(350);
    ok(!(await pg.$eval('#art', (e) => e.classList.contains('is-diffing'))), 'closing the diff LEFT the diffing reallocation');
    const diffScrollAfter = await pg.evaluate(() => Math.round(window.scrollY));
    ok(Math.abs(diffScrollAfter - diffScrollAtOpen) <= 2, `exact scroll restored on diff close (${diffScrollAfter} ≈ ${diffScrollAtOpen})`);
    ok(!(await pg.$eval('#art-diffpane', (e) => e.classList.contains('on'))), 'the diff pane is closed at rest (no residue)');
    await pg.click('#art-rail-toggle'); await sleep(250);   // collapse the rail again

    // ── (4c) THE COMMENT THREAD — a MARGIN panel (his ruling), COLLAPSED, the paper never crushed ──
    await pg.waitForSelector('.art-page', { timeout: 20000 }); await sleep(400);
    await pg.$eval('.art-page', (e) => e.scrollIntoView({ block: 'start' })); await sleep(300);
    const pbox = await pg.evaluate(() => { const w = document.querySelector('.art-page'); const r = w.getBoundingClientRect(); return { x: Math.round(r.left + r.width / 2), y: Math.round(Math.max(r.top, 0) + 120) }; });
    const paperWt0 = await pg.$eval('.art-reader-col', (e) => Math.round(e.getBoundingClientRect().width));
    const threadScrollAtOpen = await pg.evaluate(() => Math.round(window.scrollY));
    await pg.mouse.click(pbox.x, pbox.y); await sleep(600);
    ok(await pg.$eval('#art-anchor', (e) => e.classList.contains('on')), 'a paragraph click opens the comment thread');
    ok(await pg.$eval('#art', (e) => e.classList.contains('is-threading')), 'the thread reallocated the margin (#art.is-threading)');
    // item 3 (BLOCKING) — the paper column is NOT crushed; the thread is a MARGIN panel.
    const paperWt1 = await pg.$eval('.art-reader-col', (e) => Math.round(e.getBoundingClientRect().width));
    ok(Math.abs(paperWt1 - paperWt0) <= 2, `the paper column width is unchanged while the thread is open (${paperWt1} ≈ ${paperWt0})`);
    const threadInMargin = await pg.evaluate(() => { const a = document.querySelector('#art-anchor'), m = document.querySelector('.art-margin'); const ar = a.getBoundingClientRect(), mr = m.getBoundingClientRect(); return ar.left >= mr.left - 2 && ar.right <= mr.right + 2; });
    ok(threadInMargin, 'the comment thread materialises in the MARGIN column (not over the paper)');
    ok((await pg.$('.art-line-marker')) !== null, 'a marker sits at the line in the paper (the ¶ idiom)');
    // item 4 (BLOCKING) — the thread opens COLLAPSED: a summary + folds; detail is NOT rendered until asked.
    ok((await pg.$('#art-anchor .art-anchor-sum')) !== null, 'the thread opens with a summary line (the counts)');
    const foldsClosed = await pg.$$eval('#art-anchor .art-fold', (els) => els.length > 0 && els.every((e) => !e.classList.contains('open') && e.querySelector('.art-fold-b').childElementCount === 0));
    ok(foldsClosed, 'item 4 — the folds are COLLAPSED, their detail not rendered until expanded (the disclosure law)');
    await pg.click('#art-anchor .art-fold[data-fold="nodes"] .art-fold-h'); await sleep(250);
    ok(await pg.$eval('#art-anchor .art-fold[data-fold="nodes"]', (e) => e.classList.contains('open') && e.querySelector('.art-fold-b').childElementCount > 0),
      'expanding a fold renders its detail in place (nothing beyond the summary until asked)');
    ok((await pg.$('#art-anchor [data-role="return-door"]')) !== null, 'the thread carries a VISIBLE named return door');
    const tdoorLabel = (await pg.textContent('#art-anchor [data-role="return-door"] .rd-label')).trim();
    ok(/back to the reader/i.test(tdoorLabel), 'the thread return door NAMES its destination: ' + JSON.stringify(tdoorLabel));
    await pg.keyboard.press('Escape'); await sleep(350);
    ok(!(await pg.$eval('#art-anchor', (e) => e.classList.contains('on'))), 'closing the thread left the overlay');
    ok(!(await pg.$eval('#art', (e) => e.classList.contains('is-threading'))), 'closing the thread LEFT the threading reallocation');
    ok((await pg.$('.art-line-marker')) === null, 'the line marker is cleared on close (no residue)');
    const threadScrollAfter = await pg.evaluate(() => Math.round(window.scrollY));
    ok(Math.abs(threadScrollAfter - threadScrollAtOpen) <= 2, `exact scroll restored on thread close (${threadScrollAfter} ≈ ${threadScrollAtOpen})`);

    // ── (4d) THE PROVENANCE PANE — "open a pane on an equation and see where it came from" ──
    // (the author's banked commission PV-20260722T224720Z). Hover the eq:coh-total region on
    // its page → the object affordance chip appears → clicking opens the pane in the margin
    // with the REAL served chain (its isnad origin words).
    await pg.waitForSelector('.art-page', { timeout: 20000 }); await sleep(300);
    const EQ = { page: 12, x0: 128.24, x1: 300.25, y0: 250.16, y1: 281.36 };   // eq:coh-total, off the served nodemap
    ok((await pg.$(`.art-page[data-page="${EQ.page}"]`)) !== null,
      'the reader rendered the page eq:coh-total lands on (page ' + EQ.page + ')');
    await pg.$eval(`.art-page[data-page="${EQ.page}"]`, (e) => e.scrollIntoView({ block: 'center' })); await sleep(350);
    const eqPt = await pg.evaluate((reg) => {
      const w = document.querySelector(`.art-page[data-page="${reg.page}"]`);
      const r = w.getBoundingClientRect();
      const pw = parseFloat(w.dataset.pw) || 612, ph = parseFloat(w.dataset.ph) || 792;
      const sx = r.width / pw, sy = r.height / ph;
      return { x: Math.round(r.left + ((reg.x0 + reg.x1) / 2) * sx), y: Math.round(r.top + ((reg.y0 + reg.y1) / 2) * sy) };
    }, EQ);
    await pg.mouse.move(eqPt.x - 5, eqPt.y - 5); await sleep(80);
    await pg.mouse.move(eqPt.x, eqPt.y); await sleep(300);
    // the affordance IS the highlight (his ruling): a selection-style wash on the equation, no verbal chip.
    ok((await pg.$('.art-objsel')) !== null, 'hovering the equation raises the selection-style highlight (the affordance is the highlight)');
    ok((await pg.$('.art-objchip')) === null, 'no verbal "where this came from" chip exists (his ruling — killed)');
    // the highlight hugs the ACTUAL measured rect: it intersects the equation's nodemap rect and
    // does not extend beyond it by more than a small tolerance (his exact complaint about inaccuracy).
    const selFit = await pg.evaluate((reg) => {
      const w = document.querySelector(`.art-page[data-page="${reg.page}"]`);
      const wr = w.getBoundingClientRect();
      const pw = parseFloat(w.dataset.pw) || 612, ph = parseFloat(w.dataset.ph) || 792;
      const sx = wr.width / pw, sy = wr.height / ph;
      const ex = { l: wr.left + reg.x0 * sx, t: wr.top + reg.y0 * sy, r: wr.left + reg.x1 * sx, b: wr.top + reg.y1 * sy };
      const s = document.querySelector('.art-objsel').getBoundingClientRect();
      const ox = Math.max(0, Math.min(ex.r, s.right) - Math.max(ex.l, s.left));
      const oy = Math.max(0, Math.min(ex.b, s.bottom) - Math.max(ex.t, s.top));
      const selArea = (s.right - s.left) * (s.bottom - s.top);
      const coverage = selArea ? (ox * oy) / selArea : 0;   // fraction of the highlight inside the equation rect
      const beyond = Math.max(0, ex.l - s.left, s.right - ex.r, ex.t - s.top, s.bottom - ex.b);
      return { coverage: Number(coverage.toFixed(2)), beyond: Math.round(beyond) };
    }, EQ);
    ok(selFit.coverage > 0.7 && selFit.beyond <= 6,
      'the highlight hugs the equation rect — mostly inside it, no overhang beyond a small tolerance: ' + JSON.stringify(selFit));
    await pg.mouse.click(eqPt.x, eqPt.y); await sleep(500);
    ok(await pg.$eval('#art', (e) => e.classList.contains('is-proving')), 'clicking the equation opened the provenance pane (#art.is-proving)');
    await pg.waitForSelector('#art-prov .art-prov-glance', { timeout: 8000 });
    const provObj = (await pg.textContent('#art-prov .art-prov-obj')).trim();
    ok(provObj.includes('eq:coh-total'), 'the pane names the object it opened on: ' + JSON.stringify(provObj));
    const provText = await pg.textContent('#art-prov');
    ok(/coherent circuit volume/i.test(provText),
      'the pane renders the SERVED chain — the isnad origin words for eq:coh-total: ' + JSON.stringify(provText.match(/authored inside[^.]*/i)));
    ok((await pg.$('#art-prov [data-role="return-door"]')) !== null, 'the provenance pane carries a visible named return door');
    const provScrollAtOpen = await pg.evaluate(() => Math.round(window.scrollY));
    // no horizontal overflow at 1280 with the pane open
    ok(await pg.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
      'zero horizontal overflow at 1280 with the provenance pane open');

    // (4d-2) THE COMMENT DOOR, pre-anchored to the object — one comment by the probe actor.
    await pg.click('#art-prov .art-prov-doorrow button.hy-door.is-primary'); await sleep(150);
    await pg.fill('#art-prov .art-prov-comment textarea', 'PROVENANCE PROBE — a comment banked at the equation');
    await pg.click('#art-prov .art-prov-comment button.hy-door.is-primary');
    await pg.waitForFunction(() => { const m = document.querySelector('#art-prov .art-prov-msg'); return m && /banked ✓/.test(m.textContent || ''); }, { timeout: 12000 });
    const fbRow = JSON.parse(execSync(`${PY} -c "import json;from pathlib import Path;from laplace.pipeline.ledger import read_jsonl;recs=read_jsonl(Path('paper_falqon/manuscript/feedback/feedback.jsonl'));r=[x for x in recs if x.get('by')=='${PROBE_ACTOR}' and (x.get('anchor') or {}).get('object')=='eq:coh-total'];last=r[-1] if r else {};print(json.dumps({'by':last.get('by'),'node_id':last.get('node_id'),'obj':(last.get('anchor') or {}).get('object')}))"`, { cwd: repoRoot }).toString().trim());
    ok(fbRow.by === PROBE_ACTOR && !!fbRow.node_id && fbRow.obj === 'eq:coh-total',
      'the comment banked a ledger row pre-anchored to the object (probe actor + node_id + anchor.object): ' + JSON.stringify(fbRow));

    // (4d-3) close — the proving reallocation left, the exact scroll restored, no residue.
    await pg.click('#art-prov [data-role="return-door"]'); await sleep(350);
    ok(!(await pg.$eval('#art', (e) => e.classList.contains('is-proving'))), 'closing the provenance pane left the proving reallocation');
    const provScrollAfter = await pg.evaluate(() => Math.round(window.scrollY));
    ok(Math.abs(provScrollAfter - provScrollAtOpen) <= 2, `exact scroll restored on provenance close (${provScrollAfter} ≈ ${provScrollAtOpen})`);
    ok((await pg.$eval('#art-prov', (e) => e.innerHTML.trim())) === '', 'the provenance pane is empty at rest (no hidden residue)');

    // (4d-4) a COLD ?object= deep link lands with the pane open on the same chain.
    await pg.goto(base + '/artefact?corpus=' + encodeURIComponent(CORPUS) + '&object=' + encodeURIComponent('eq:coh-total'), { waitUntil: 'networkidle' });
    await pg.waitForSelector('#art.is-proving #art-prov .art-prov-glance', { timeout: 12000 });
    ok(/coherent circuit volume/i.test(await pg.textContent('#art-prov')),
      'the ?object= cold deep link opened the provenance pane on eq:coh-total (no hunting)');

    // (4d-5) an UNRESOLVED object opens the pane to the SERVED composed absence — never an invented chain.
    await pg.goto(base + '/artefact?corpus=' + encodeURIComponent(CORPUS) + '&object=' + encodeURIComponent('eq:not-a-real-label-EIGENAUDIT'), { waitUntil: 'networkidle' });
    await pg.waitForSelector('#art.is-proving #art-prov .art-prov-glance', { timeout: 12000 });
    const absText = await pg.textContent('#art-prov .art-prov-glance');
    ok(/nothing named|does not|resolve/i.test(absText) && !/coherent circuit volume/i.test(await pg.textContent('#art-prov')),
      'an unresolved object opens to the honest served absence, no fabricated chain: ' + JSON.stringify(absText.slice(0, 90)));
    // return to the clean falqon reader for the sections that follow.
    await pg.goto(base + '/artefact?corpus=' + encodeURIComponent(CORPUS) + '&via=cockpit-tension', { waitUntil: 'networkidle' });
    await pg.waitForSelector('#art-thread:not([hidden]) [data-role="return-door"]', { timeout: 10000 });

    // ── (5) THE ENTRY RETURN DOOR lands on the cockpit BRIEF (the focus restored) ──
    await Promise.all([pg.waitForNavigation({ waitUntil: 'networkidle' }), pg.click('#art-thread [data-role="return-door"]')]);
    ok(/\/conceptric/.test(pg.url()) && pg.url().includes(CORPUS), 'the entry return door lands on the cockpit URL: ' + pg.url());
    await pg.waitForSelector('[data-role="brief-prose"]', { timeout: 8000 });
    const backProse = (await pg.textContent('[data-role="brief-prose"]')).trim();
    ok(backProse.length > 40, 'returning landed on the cockpit BRIEF, not a wall: ' + JSON.stringify(backProse.slice(0, 50)));

    // ── (6) THE ASSETS BOTH-DIRECTIONS DOOR (the flipped mechanical seal) ───────
    const objNode = await pg.evaluate(async ({ c, a }) => {
      const d = await (await fetch('/assets/object?corpus=' + encodeURIComponent(c) + '&id=' + encodeURIComponent(a))).json();
      return d.nodes && d.nodes[0];
    }, { c: ASSET_CORPUS, a: ASSET_ID });
    ok(objNode && /\/conceptric/.test(objNode.href), 'FORWARD: the asset cockpit doors its node to the conceptric: ' + JSON.stringify(objNode));
    const back = await pg.evaluate(async ({ c, nid }) => {
      const d = await (await fetch('/corpus/node?corpus=' + encodeURIComponent(c) + '&id=' + encodeURIComponent(nid))).json();
      return d.assets;
    }, { c: ASSET_CORPUS, nid: objNode.id });
    ok(Array.isArray(back) && back.some((x) => /\/assets\?/.test(x.href) && String(x.id).includes('figure')),
      'BACK: the conceptric node doors back to the named asset in /assets: ' + JSON.stringify(back));

    // ── (7) THE JUDGE VERDICT DOORS — the governing fix, driven end-to-end ──────
    // pick a dismissable legacy finding (node + kind) off the REAL board.
    const target = await pg.evaluate(async (c) => {
      const b = await (await fetch('/review/findings?corpus=' + encodeURIComponent(c))).json();
      const all = [].concat(...(b.by_node || []).map((g) => g.findings || []), b.unanchored || []);
      const f = all.find((x) => x.node && x.node !== '?' && x.kind && x.id);
      return f ? { id: f.id, node: f.node, kind: f.kind } : null;
    }, CORPUS);
    ok(target, 'the board offers a dismissable legacy finding (node + kind): ' + JSON.stringify(target));
    const readD = () => pg.evaluate(async (c) =>
      (await (await fetch('/review/dismissals?corpus=' + encodeURIComponent(c))).json()).counts.dismissals, CORPUS);

    // (7a) the ?finding= cold deep link opens THAT inspection with no hunting.
    await pg.goto(base + '/artefact?corpus=' + encodeURIComponent(CORPUS) + '&finding=' + encodeURIComponent(target.id), { waitUntil: 'networkidle' });
    await pg.waitForSelector('#art-tray-body .art-frow[data-fid]', { timeout: 10000 });
    await pg.waitForSelector('#art.is-inspecting', { timeout: 10000 });
    ok(await pg.$eval('#art', (e) => e.classList.contains('is-inspecting')), 'the ?finding= deep link opened its inspection COLD (no hunting)');

    // (7b) the four verdict doors stand on the live finding, arm-then-fire.
    const verbs = await pg.$$eval("#art-inspect [data-role='verdict-doors'] button[data-verb]", (els) => els.map((e) => e.dataset.verb));
    ok(['confirm', 'dismiss', 'defer', 'route-conceptric'].every((v) => verbs.includes(v)),
      'the four verdict doors (confirm/dismiss/defer/route) stand on the live finding: ' + JSON.stringify(verbs));
    const dismissSel = "#art-inspect button[data-verb='dismiss']";
    const restLabel = await pg.textContent(dismissSel);
    await pg.click(dismissSel); await sleep(180);
    const armedLabel = await pg.textContent(dismissSel);
    ok(armedLabel !== restLabel && /click again/i.test(armedLabel),
      'dismiss ARMS on the first click (names its consequence, does not fire): ' + JSON.stringify(armedLabel));

    // (7c) fire — a suppression lands, attributed to the probe actor; the tray refreshes.
    const dBefore = await readD();
    await pg.click(dismissSel);
    let dAfter = dBefore;
    for (let i = 0; i < 40 && dAfter < dBefore + 1; i++) { await sleep(250); dAfter = await readD(); }
    ok(dAfter === dBefore + 1, `the dismiss landed one suppression through the real door (dismissals ${dBefore} -> ${dAfter})`);
    const sup = JSON.parse(execSync(`${PY} -c "import json;from pathlib import Path;from laplace.pipeline import suppress as s;l=Path('paper_falqon/manuscript/feedback/feedback.jsonl');sup=s.load_suppressions(l);print(json.dumps(sup[-1] if sup else {}))"`, { cwd: repoRoot }).toString().trim());
    ok(sup && sup.source === PROBE_ACTOR,
      'the suppression ledger row carries the PROBE actor from the session (not a hard-coded name): ' + JSON.stringify(sup.source));
    const sumTxt = await pg.textContent('#art-tray-sum');
    ok(/1 dismissed/.test(sumTxt), 'the tray refreshed from server truth after the verdict: ' + JSON.stringify(sumTxt));

    // (7d) overrule it back through the real door (the dismissed fold) — the ledger nets a reversed pair.
    await pg.click('#art-dism-h'); await sleep(250);
    const ovSel = `#art-tray-body .art-frow[data-sid='${sup.id}'] .art-overrule`;
    await pg.waitForSelector(ovSel, { timeout: 6000 });
    await pg.click(ovSel); await sleep(180);           // arm
    await pg.click(ovSel);                              // fire
    let dFinal = dAfter;
    for (let i = 0; i < 40 && dFinal > dBefore; i++) { await sleep(250); dFinal = await readD(); }
    ok(dFinal === dBefore, `overrule reverted the suppression through the real door (dismissals ${dAfter} -> ${dFinal})`);
    const net = JSON.parse(execSync(`${PY} -c "import json;from pathlib import Path;from laplace.pipeline import suppress as s;from laplace.pipeline.ledger import read_jsonl;l=Path('paper_falqon/manuscript/feedback/feedback.jsonl');recs=read_jsonl(l);print(json.dumps({'active':len(s.load_suppressions(l)),'sup':sum(1 for r in recs if r.get('record')==s.RECORD_KIND and r.get('source')=='${PROBE_ACTOR}'),'rev':sum(1 for r in recs if r.get('record')==s.REVOKE_KIND and r.get('source')=='${PROBE_ACTOR}')}))"`, { cwd: repoRoot }).toString().trim());
    ok(net.active === 0 && net.sup === 1 && net.rev === 1,
      'the ledger nets to a reversed pair by the probe actor (one dismiss, one overrule): ' + JSON.stringify(net));

    // ── (7e) ITEM 6b — routing FITS the finding kind, or surfaces the honest mismatch ──
    const notf = await pg.evaluate(async (c) => {
      const b = await (await fetch('/review/findings?corpus=' + encodeURIComponent(c))).json();
      const all = [].concat(...(b.by_node || []).map((g) => g.findings || []), b.unanchored || []);
      const f = all.find((x) => x.kind === 'notation-inconsistent' && x.id);
      return f ? f.id : null;
    }, CORPUS);
    if (notf) {
      await pg.goto(base + '/artefact?corpus=' + encodeURIComponent(CORPUS) + '&finding=' + encodeURIComponent(notf), { waitUntil: 'networkidle' });
      await pg.waitForSelector('#art.is-inspecting', { timeout: 12000 });
      await pg.click("#art-inspect [data-role='verdict-doors'] button[data-verb='route-conceptric']"); await sleep(300);
      ok((await pg.$("#art-inspect [data-role='route-mismatch']")) !== null,
        'item 6b — routing a notation-inconsistent finding surfaces the honest kind mismatch, not ill-fitting conceptric options');
      const mismTxt = (await pg.textContent("#art-inspect [data-role='route-mismatch']")).trim();
      ok(/prose fix/i.test(mismTxt) && /confirm/i.test(mismTxt),
        'the mismatch explains routing rewrites the concept map and points to confirm instead: ' + JSON.stringify(mismTxt.slice(0, 90)));
      // a kind whose defect IS structural gets fitted intents instead (the other half of 6b).
      const misf = await pg.evaluate(async (c) => {
        const b = await (await fetch('/review/findings?corpus=' + encodeURIComponent(c))).json();
        const all = [].concat(...(b.by_node || []).map((g) => g.findings || []), b.unanchored || []);
        const f = all.find((x) => (x.kind === 'unsupported-claim' || x.kind === 'missing-derivation' || x.kind === 'naked-claim') && x.id);
        return f ? f.id : null;
      }, CORPUS);
      if (misf) {
        await pg.goto(base + '/artefact?corpus=' + encodeURIComponent(CORPUS) + '&finding=' + encodeURIComponent(misf), { waitUntil: 'networkidle' });
        await pg.waitForSelector('#art.is-inspecting', { timeout: 12000 });
        await pg.click("#art-inspect [data-role='verdict-doors'] button[data-verb='route-conceptric']"); await sleep(300);
        ok((await pg.$("#art-inspect select[data-role='route-intent']")) !== null,
          'item 6b — a structural-defect finding is offered kind-fitted conceptric intents (a real order that fits)');
      }
    } else {
      ok(true, 'no notation-inconsistent finding on the board to test kind-fitted routing (skipped honestly)');
    }

    // ── (8) SYNCTEX AT REST — a composed sentence + a one-act door, never a raw fetch url ──
    await pg.goto(base + '/artefact?corpus=' + encodeURIComponent(CORPUS), { waitUntil: 'networkidle' });
    await pg.waitForSelector('#art-follow-status .hy-chip', { timeout: 10000 });
    // item 4 — the STATE chip sits on the source-bar row (grouped with his-hand); the
    // explanation is DEMOTED to the quiet note line, which carries the one-act door + a ×.
    const followTxt = await pg.textContent('#art-follow-status');
    ok(/not built here|stale|fresh/i.test(followTxt) && !/fetchjson/i.test(followTxt),
      'the synctex STATE chip sits on the source-bar row (composed, not a raw fetch url): ' + JSON.stringify(followTxt.slice(0, 70)));
    await pg.waitForSelector('#art-source-note.on', { timeout: 8000 });
    const noteTxt = await pg.textContent('#art-source-note');
    ok(/follow|compiled paper|map/i.test(noteTxt) && !/fetchjson/i.test(noteTxt),
      'the explanation is demoted to one quiet note line, composed not raw: ' + JSON.stringify(noteTxt.slice(0, 70)));
    ok((await pg.$("#art-source-note [data-role='follow-recompile']")) !== null,
      'the demoted note line offers the one-act recompile-to-enable-follow door');
    ok((await pg.$("#art-source-note [data-role='source-note-x']")) !== null,
      'the demoted note line carries a dismiss × that a compile (or a click) retires (item 4)');

    // ── (8b) THE HIS-HAND LAYER — "highlight the text I've edited/added myself" ──
    // default (clean main.tex == the machine baseline): the honest empty state, in words.
    await pg.waitForFunction(() => { const el = document.querySelector('#art-edit-file'); return el && (el.textContent || '').includes('main.tex'); }, { timeout: 12000 });
    await pg.waitForSelector('#art-hishand .art-hishand-chip', { timeout: 10000 });
    const emptyChip = (await pg.textContent('#art-hishand .art-hishand-chip')).trim();
    ok(/none yet/i.test(emptyChip), 'his-hand honestly states the empty case when the file matches the machine baseline: ' + JSON.stringify(emptyChip));
    // plant a distinctive edit in the author's hand on disk; reload → his-hand attributes it.
    fs.writeFileSync(MD + '/main.tex', ORIG_MAIN.replace('\\maketitle', '\\maketitle\n\\emph{HISHAND PROBE - a passage in the authors own hand}'));
    await pg.goto(base + '/artefact?corpus=' + encodeURIComponent(CORPUS), { waitUntil: 'networkidle' });
    await pg.waitForFunction(() => { const el = document.querySelector('#art-edit-file'); return el && (el.textContent || '').includes('main.tex'); }, { timeout: 12000 });
    await pg.waitForSelector('#art-hishand .art-hishand-chip', { timeout: 10000 });
    const handChip = (await pg.textContent('#art-hishand .art-hishand-chip')).trim();
    ok(/\d+ passage/i.test(handChip), 'his-hand attributes the planted edit as passages (off the rail, not a style heuristic): ' + JSON.stringify(handChip));
    const hhNote = await pg.getAttribute('#art-hishand .art-hishand-chip', 'title');
    ok(/baseline/i.test(hhNote), 'the chip names the machine baseline it diffed against: ' + JSON.stringify(hhNote));
    // toggle ON → the planted line's OWN CM6 line carries the gold his-hand wash.
    await pg.click('#art-hishand [data-role="hishand-toggle"]'); await sleep(350);
    ok(await pg.$eval('#art-hishand .art-hishand-chip', (e) => e.classList.contains('is-on')), 'the toggle turns the his-hand highlight on');
    const hl = await pg.evaluate(() => {
      const lines = [...document.querySelectorAll('#art-cm .cm-line')];
      const hit = lines.find((l) => (l.textContent || '').includes('HISHAND PROBE'));
      return hit ? { found: true, washed: hit.classList.contains('art-hishand-line') } : { found: false };
    });
    ok(hl.found && hl.washed, 'the planted passage renders with the gold his-hand wash on its OWN line: ' + JSON.stringify(hl));
    // toggle OFF → the wash clears with no residue.
    await pg.click('#art-hishand [data-role="hishand-toggle"]'); await sleep(250);
    ok((await pg.$('#art-cm .cm-line.art-hishand-line')) === null, 'toggling off clears the his-hand wash (no residue)');
    fs.writeFileSync(MD + '/main.tex', ORIG_MAIN);   // restore clean for the sections that follow

    // ── (8c) LINE-PRECISE COMMENT ON THE PROJECTED ARTEFACT (the heart of his commission) ──
    // build synctex (a clean compile), then select a line → comment → the ledger row carries
    // the synctex source line + the quote, and the MARGIN thread shows it, attributed.
    await pg.goto(base + '/artefact?corpus=' + encodeURIComponent(CORPUS), { waitUntil: 'networkidle' });
    await pg.waitForFunction(() => { const el = document.querySelector('#art-edit-file'); return el && (el.textContent || '').includes('main.tex'); }, { timeout: 12000 });
    await pg.click('#art-cm'); await sleep(150);
    await pg.keyboard.press('Control+s');
    await pg.waitForFunction(() => { const m = document.querySelector('#art-edit-msg'); const t = (m && m.textContent) || ''; return /compiled|refused/i.test(t) && !/queued|compiling|saving/i.test(t); }, { timeout: 180000 });
    await pg.waitForSelector('.art-page .pgtext span', { timeout: 20000 }); await sleep(600);
    const syn = await pg.evaluate(async () => {
      const w = document.querySelector('.art-page[data-page="1"]') || document.querySelector('.art-page');
      const page = parseInt(w.dataset.page, 10);
      const file = (document.querySelector('#art-edit-file').textContent || '').trim();
      try { return await (await fetch('/projection/synctex?file=' + encodeURIComponent(file) + '&page=' + page + '&x=120&y=220')).json(); } catch (e) { return { error: String(e) }; }
    });
    // select a line of prose on that page → the affordance rises (item 5a).
    const selText = await pg.evaluate(() => {
      const page = document.querySelector('.art-page[data-page="1"]') || document.querySelector('.art-page');
      const pr = page.getBoundingClientRect();
      // pick prose in the BODY of the page (below the title/authors band) so it resolves to a paragraph.
      const spans = [...page.querySelectorAll('.pgtext span')]
        .filter((s) => { const r = s.getBoundingClientRect(); return (s.textContent || '').trim().length > 4 && (r.top - pr.top) > pr.height * 0.35; });
      if (spans.length < 2) return null;
      const a = spans[0], b = spans[Math.min(3, spans.length - 1)];
      const range = document.createRange();
      range.setStart(a.firstChild || a, 0); range.setEnd(b.firstChild || b, (b.textContent || '').length);
      const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range);
      document.querySelector('#art-reader').dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
      return (sel.toString() || '').trim().slice(0, 60);
    });
    ok(selText, 'selected a line of prose on the projected artefact');
    await pg.waitForSelector('.art-sel-aff', { timeout: 5000 });
    ok((await pg.$('.art-sel-aff')) !== null, 'item 5a — selecting a passage offers a quiet "comment on this passage" affordance at the selection');
    await pg.click('.art-sel-aff'); await sleep(600);
    ok(await pg.$eval('#art-anchor', (e) => e.classList.contains('on')), 'clicking the affordance opens the comment thread at that anchor (in the margin)');
    const anchorTxt = (await pg.textContent('#art-anchor .art-anchor-anchor').catch(() => '')) || '';
    ok(/:\d+/.test(anchorTxt) || /arrives with a compile/i.test(anchorTxt),
      'the thread names the anchor — the synctex source line, or the honest compile-fallback: ' + JSON.stringify(anchorTxt.trim().slice(0, 60)));
    await pg.fill('#art-anchor [data-role="cmt-text"]', 'LINE COMMENT PROBE - feedback targeted to this exact line');
    await pg.click('#art-anchor [data-role="cmt-bank"]');
    await pg.waitForFunction(() => /LINE COMMENT PROBE/.test((document.querySelector('#art-anchor') || {}).textContent || ''), { timeout: 12000 });
    ok(/LINE COMMENT PROBE/.test(await pg.textContent('#art-anchor')), 'item 5b — the fired comment appears IMMEDIATELY in the margin thread at the anchor, attributed');
    const lc = JSON.parse(execSync(`${PY} -c "import json;from pathlib import Path;from laplace.pipeline.ledger import read_jsonl;recs=read_jsonl(Path('paper_falqon/manuscript/feedback/feedback.jsonl'));r=[x for x in recs if x.get('by')=='${PROBE_ACTOR}' and 'LINE COMMENT PROBE' in (x.get('comment') or '')];last=r[-1] if r else {};a=last.get('anchor') or {};print(json.dumps({'by':last.get('by'),'quote':bool(a.get('quote')),'src_line':a.get('source_line'),'page':a.get('page')}))"`, { cwd: repoRoot }).toString().trim());
    if (syn && syn.line) {
      ok(lc.by === PROBE_ACTOR && lc.quote === true && lc.src_line != null,
        'item 5 (heart) — the ledger row carries the comment attributed, with the quote + the SYNCTEX source line: ' + JSON.stringify(lc));
    } else {
      ok(lc.by === PROBE_ACTOR && lc.quote === true && lc.page != null,
        'item 5 — synctex not built for this pdf; the ledger row carries the attributed comment with the quote + page fallback: ' + JSON.stringify(lc));
    }
    await pg.keyboard.press('Escape'); await sleep(200);

    // ── (9) KEYBOARD SAVE + THE HONEST COMPILE BADGE (a planted recoverable error) ──
    // plant an undefined macro on disk so the loaded editor carries it; Ctrl-S saves + recompiles.
    fs.writeFileSync(MD + '/main.tex', ORIG_MAIN.replace('\\maketitle', '\\maketitle\n\\undefinedcmdEIGENAUDIT'));
    await pg.goto(base + '/artefact?corpus=' + encodeURIComponent(CORPUS), { waitUntil: 'networkidle' });
    await pg.waitForFunction(() => { const el = document.querySelector('#art-edit-file'); return el && (el.textContent || '').indexOf('main.tex') !== -1; }, { timeout: 12000 });
    await pg.click('#art-cm'); await sleep(150);
    await pg.keyboard.press('Control+s');               // #4 — the keyboard save reflex
    await pg.waitForFunction(() => { const m = document.querySelector('#art-edit-msg'); const t = (m && m.textContent) || '';
      return /compiled|error|refused/i.test(t) && !/queued|compiling|saving/i.test(t); }, { timeout: 90000 });
    const badge = await pg.textContent('#art-edit-msg');
    const badgeBad = await pg.$eval('#art-edit-msg', (e) => e.classList.contains('is-bad'));
    ok(/refused/i.test(badge) || (/error/i.test(badge) && badgeBad),
      'Ctrl-S saved + recompiled and the badge is truthful about the recoverable error (never a false green): ' + JSON.stringify(badge));
    if (!/refused/i.test(badge)) {
      ok((await pg.$('#art-compile-log .art-logrow')) !== null,
        'the compile log leads with a clickable error row (the ! block lifted from the full log, not buried in package noise)');
      const logHasErr = await pg.$$eval('#art-compile-log .art-logrow', (els) => els.some((e) => /line 11|Undefined control sequence/i.test(e.textContent || '')));
      ok(logHasErr, 'the error row names the undefined control sequence at its source line');
    }
    fs.writeFileSync(MD + '/main.tex', ORIG_MAIN);   // restore clean before the layout section

    // ── (10) THE FINAL POLISH — the geometry bound, at BOTH widths (his usability pass) ──
    // #1 (worst in the instrument): the margin is BOUND to the viewport — no black void under
    // the paper, the version rail visible at the margin's foot; the three columns END together.
    // #2: reading mode caps the paper to a sensible centred column. Verified at 1440 and 1280.
    for (const [W, H] of [[1440, 1024], [1280, 900]]) {
      await pg.setViewportSize({ width: W, height: H });
      await pg.goto(base + '/artefact?corpus=' + encodeURIComponent(CORPUS), { waitUntil: 'networkidle' });
      await pg.waitForSelector('#art-tray-body .art-frow[data-fid]', { timeout: 12000 });
      await pg.waitForSelector('.art-rail-col #art-rail', { timeout: 8000 }); await sleep(500);
      // the margin's rendered height is bounded against the viewport (never the ~1655px void).
      const geo = await pg.evaluate(() => {
        const r = (s) => { const e = document.querySelector(s); if (!e) return null; const b = e.getBoundingClientRect(); return { top: Math.round(b.top), bottom: Math.round(b.bottom), height: Math.round(b.height), width: Math.round(b.width), left: Math.round(b.left), right: Math.round(b.right) }; };
        return { vh: window.innerHeight, margin: r('.art-margin'), reader: r('#art-reader'), source: r('.art-source-pane'), rail: r('.art-rail-col'), readerCol: r('.art-reader-col') };
      });
      ok(geo.margin && geo.margin.height <= geo.vh + 2,
        `#1 the margin is BOUND to the viewport at ${W} (h=${geo.margin && geo.margin.height} <= vh=${geo.vh}) — no black void`);
      // the three columns end within a tolerance of each other (bottoms aligned, no stranded margin).
      const bottoms = [geo.margin.bottom, geo.reader.bottom, geo.source.bottom];
      const spread = Math.max(...bottoms) - Math.min(...bottoms);
      ok(spread <= 90, `#1 the three columns (source · paper · margin) END within tolerance at ${W} (bottom spread=${spread}px): ${JSON.stringify(bottoms)}`);
      // the version rail is visible without scrolling past the fold (its foot within the viewport).
      ok(geo.rail && geo.rail.top >= 0 && geo.rail.bottom <= geo.vh + 8,
        `#1 the version rail is VISIBLE without scrolling past the fold at ${W} (rail top=${geo.rail && geo.rail.top}, bottom=${geo.rail && geo.rail.bottom}, vh=${geo.vh})`);
      // #2 — reading mode caps the paper column to a sensible centred column (~820px).
      await pg.click('#art-edit-toggle'); await sleep(700);
      const read = await pg.evaluate(() => {
        const p = document.querySelector('.art-pdf-pane').getBoundingClientRect();
        const c = document.querySelector('.art-reader-col').getBoundingClientRect();
        return { mode: document.querySelector('#art-main').dataset.mode, paneW: Math.round(p.width), colW: Math.round(c.width), gutterL: Math.round(p.left - c.left), gutterR: Math.round(c.right - p.right) };
      });
      ok(read.mode === 'read' && read.paneW <= 840,
        `#2 reading mode CAPS the paper column at ${W} (paneW=${read.paneW} <= 840, colW=${read.colW})`);
      ok(read.gutterL > 20 && Math.abs(read.gutterL - read.gutterR) <= 6,
        `#2 the capped paper column is CENTRED at ${W} (gutters L=${read.gutterL} ≈ R=${read.gutterR})`);
      await pg.click('#art-edit-toggle'); await sleep(300);   // restore the split posture
    }
    await pg.setViewportSize({ width: 1280, height: 720 });

    ok(errs.length === 0, 'zero uncaught page errors across the whole walk: ' + JSON.stringify(errs));
    console.log(`\nENGINE EDITOR — ${passed} assertions green.`);
  } finally {
    await b.close();
    if (scanner) scanner.kill('SIGKILL');
    cleanupFalqon();
  }
})().catch((e) => { console.error('\nWALK FAILED:', e.message); if (scanner) scanner.kill('SIGKILL'); cleanupFalqon(); process.exit(1); });
