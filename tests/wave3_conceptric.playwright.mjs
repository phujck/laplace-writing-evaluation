// WAVE 3 — THE CONCEPTRIC SURFACE, driven to the approved mock (mocks/conceptric.html, D1–D16).
//
// SURFACE MOVE (E2 rebuild): /conceptric became the growth COCKPIT; the graded-descent
// read-and-rule board+inspector this walk drives (#cx-board / #cx-right, conceptric-panes.mjs)
// is retained at /conceptric/map, reachable as an altitude from the cockpit brief. Every
// navigation below targets /conceptric/map — the same surface, its ruled new route.
//
// This walk drives OUTCOMES against a REAL scanner + REAL corpus (the ruling's standard: DOM
// presence certifies nothing; a driven click that changes the FETCH and the rendered state does).
// No route stubs on the reads — the grade slices, the built index, the plan, and the staleness
// verdict are the live ones. It proves:
//   · the grade chip is a SERVER SLICE (D4): a click FIRES /corpus/grade?g= and the board's slice
//     token (the grade proof) changes — never a CSS-only re-bucket;
//   · a card SELECT updates the inspector column with ZERO board reflow (L3/D7): every board card's
//     boundingRect is byte-stable across the select;
//   · the ↑/↓ affordances carry their words AT REST (R3/D6): `fold` / `open` read without hover;
//   · a structural sec:* node (reached by the ancestry hop) reads the F9 caption — "carries members,
//     argues nothing" — never "un-mined stock";
//   · the degraded chip renders IFF the server reports router_cache degraded (D10) — stubbed BOTH
//     ways to prove the biconditional, and one click reveals the runnable remedy;
//   · ✎ rule (D16) banks a typed draft to /corpus/friction and renders its receipt;
//   · 375px: single column, no horizontal scroll.
//
//   run:  node tests/wave3_conceptric.playwright.mjs
//   deps: global playwright, Chromium at /opt/pw-browsers, python3 on PATH.
//   Exits 0 all-green, non-zero on the first failed assertion.
import { createRequire } from 'module';
import { spawn, execSync } from 'child_process';
import net from 'net';

const require = createRequire(import.meta.url);
const { chromium } = require(execSync('npm root -g').toString().trim() + '/playwright');
const CHROME = execSync('ls /opt/pw-browsers/chromium-*/chrome-linux/chrome').toString().trim().split('\n')[0];
const PY = 'python3';
const CORPUS = 'subset-sum-itqde';

let passed = 0;
function ok(cond, msg) { if (!cond) throw new Error('ASSERT FAILED: ' + msg); passed++; console.log('  ok -', msg); }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function freePort() { return new Promise((res) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); }); }
function waitFor(url, tries = 80) {
  return new Promise((res, rej) => { const tick = (n) => { const req = require('http').get(url, (r) => { r.resume(); res(true); });
    req.on('error', () => n <= 0 ? rej(new Error('server never came up')) : setTimeout(() => tick(n - 1), 250)); }; tick(tries); });
}

let scanner;
(async () => {
  const repoRoot = execSync(`${PY} -c "from laplace.web.scanner import _repo_root; print(_repo_root().resolve())"`).toString().trim();
  const port = await freePort();
  scanner = spawn(PY, ['-m', 'laplace.web.scanner', '--port', String(port)], { cwd: repoRoot, stdio: 'ignore' });
  await waitFor(`http://127.0.0.1:${port}/conceptric/map`);
  const base = `http://127.0.0.1:${port}`;
  const b = await chromium.launch({ executablePath: CHROME });
  try {
    const pg = await b.newPage({ viewport: { width: 1440, height: 900 } });
    const errs = []; pg.on('pageerror', (e) => errs.push(String(e)));
    // record every /corpus/grade fetch — the SERVER-SLICE proof (D4: the chip IS the fetch)
    const gradeFetches = []; pg.on('request', (r) => { const u = r.url(); if (u.includes('/corpus/grade?') || u.includes('/corpus/grade&')) gradeFetches.push(u); });
    // the door target surfaces are stubbed so an accidental navigation never pollutes the
    // pageerror ledger (their own JS is out of this walk's scope); the READS stay live.
    for (const surf of ['artefact', 'storyboard', 'desk']) {
      await pg.route('**/' + surf + '**', (route) => route.request().resourceType() === 'document'
        ? route.fulfill({ status: 200, contentType: 'text/html', body: '<!doctype html><title>' + surf + ' stub</title>' })
        : route.continue());
    }

    await pg.goto(base + '/conceptric/map?corpus=' + CORPUS, { waitUntil: 'networkidle' });
    await pg.waitForSelector('#cx-board .hy-card', { timeout: 8000 });
    await pg.waitForSelector('#cx-right .hy-term', { timeout: 8000 });
    await sleep(300);

    // ── (1) THE GRADE CHIP IS A SERVER SLICE (D4) ─────────────────────────────
    const chips = await pg.$$eval('#cx-strata [data-grade]', (els) => els.map((e) => Number(e.dataset.grade)));
    ok(chips.length >= 2, 'the grade strip carries ≥2 server-slice chips: ' + JSON.stringify(chips));
    const liveNow = await pg.$eval('#cx-strata .is-live', (e) => Number(e.dataset.grade));
    const target = chips.find((g) => g !== liveNow);
    const tokBefore = (await pg.textContent('#cx-slicetok')).trim();
    gradeFetches.length = 0;
    await pg.click(`#cx-strata [data-grade="${target}"]`);
    await sleep(500);
    const firedForTarget = gradeFetches.some((u) => u.includes('g=' + target));
    ok(firedForTarget, `clicking g${target} FIRED /corpus/grade?g=${target} (a server slice, not a CSS re-bucket)`);
    const tokAfter = (await pg.textContent('#cx-slicetok')).trim();
    ok(tokAfter !== tokBefore && tokAfter.includes('g' + target),
      `the board slice token changed to the new grade: ${JSON.stringify(tokBefore)} → ${JSON.stringify(tokAfter)}`);

    // land on a well-populated slice for the reflow + affordance tests
    const g0 = chips.includes(0) ? 0 : chips[0];
    await pg.click(`#cx-strata [data-grade="${g0}"]`); await sleep(500);
    await pg.waitForSelector('#cx-board .hy-card');

    // ── (2) CARD SELECT → INSPECTOR UPDATES, BOARD HITBOXES BYTE-STABLE (L3/D7) ─
    const cardIds = await pg.$$eval('#cx-board .hy-card[data-node]', (els) => els.map((e) => e.dataset.node));
    ok(cardIds.length >= 2, 'the slice board has ≥2 cards to prove no-reflow: ' + cardIds.length);
    const rectsBefore = await pg.$$eval('#cx-board .hy-card[data-node]', (els) => els.map((e) => { const r = e.getBoundingClientRect(); return { n: e.dataset.node, x: r.x, y: r.y, w: r.width, h: r.height }; }));
    const pick = cardIds[1];
    await pg.click(`#cx-board .hy-card[data-node="${pick.replace(/"/g, '\\"')}"] .hy-card-name`);
    await sleep(400);
    const insNid = (await pg.textContent('#cx-right .hy-nid')).trim();
    ok(insNid === pick, `selecting a card updated the inspector to ${pick} (nid: ${insNid})`);
    const rectsAfter = await pg.$$eval('#cx-board .hy-card[data-node]', (els) => els.map((e) => { const r = e.getBoundingClientRect(); return { n: e.dataset.node, x: r.x, y: r.y, w: r.width, h: r.height }; }));
    const moved = rectsBefore.filter((rb, i) => { const ra = rectsAfter[i]; return !ra || ra.n !== rb.n || Math.abs(ra.x - rb.x) > 0.5 || Math.abs(ra.y - rb.y) > 0.5 || Math.abs(ra.w - rb.w) > 0.5 || Math.abs(ra.h - rb.h) > 0.5; });
    ok(moved.length === 0, `NO board hitbox moved under the pointer on select (${rectsBefore.length} cards byte-stable)`);

    // ── (3) THE ↑/↓ AFFORDANCE WORDS ARE IN PLACE AT REST (R3/D6) ──────────────
    const affLabels = await pg.$$eval('#cx-board .cx-aff .cx-afflabel', (els) => [...new Set(els.map((e) => e.textContent.trim()))]);
    ok(affLabels.includes('fold') && affLabels.includes('open'),
      'the ↑/↓ affordances read `fold` / `open` AT REST (no hover): ' + JSON.stringify(affLabels));
    // and ↓ open displaces content BELOW only: the first card's top stays put when the second opens
    const firstTopBefore = (await pg.$eval('#cx-board .hy-card', (e) => e.getBoundingClientRect().y));
    await pg.click('#cx-board .hy-card:nth-of-type(2) .cx-aff[data-aff="down"]'); await sleep(400);
    const firstTopAfter = (await pg.$eval('#cx-board .hy-card', (e) => e.getBoundingClientRect().y));
    const foldOpen = await pg.$eval('#cx-board .hy-card:nth-of-type(2) .hy-card-fold', (e) => getComputedStyle(e).display !== 'none');
    ok(Math.abs(firstTopAfter - firstTopBefore) < 0.5 && foldOpen,
      'opening ↓ on a lower card displaced content below only — the card above did not move');

    // ── (4) THE F9 STRUCTURAL CAPTION (via the ancestry hop) ───────────────────
    // pick a node that argues in a plan section, so its ancestry carries a clickable sec:* hop.
    const secNode = await pg.evaluate(async (c) => {
      const pl = await (await fetch('/shared/plan?corpus=' + c)).json();
      for (const s of (pl.sections || [])) { const n = (s.nodes_in_order || [])[0]; if (n) return { node: n, sec: s.id }; }
      return null;
    }, CORPUS);
    ok(secNode, 'found a node that argues in a plan section (for the F9 ancestry path): ' + JSON.stringify(secNode));
    await pg.goto(base + '/conceptric/map?corpus=' + CORPUS + '&node=' + encodeURIComponent(secNode.node), { waitUntil: 'networkidle' });
    await pg.waitForSelector('#cx-right .hy-anc .hop.beat[data-node]', { timeout: 8000 });
    const hopId = await pg.$eval('#cx-right .hy-anc .hop.beat[data-node]', (e) => e.dataset.node);
    ok(hopId === 'sec:' + secNode.sec, `the ancestry hop names the structural section sec:${secNode.sec}`);
    await pg.click('#cx-right .hy-anc .hop.beat[data-node]'); await sleep(400);
    const argues = (await pg.$$eval('#cx-right .hy-sec', (els) => {
      const sec = els.find((e) => /argues in/.test((e.querySelector('.hy-sec-h') || {}).textContent || ''));
      return sec ? sec.textContent : '';
    }));
    ok(/carries members, argues nothing/.test(argues), 'the sec:* argues-in reads the honest F9 caption: ' + JSON.stringify(argues.trim().slice(0, 70)));
    ok(!/un-mined stock/.test(argues), 'the sec:* argues-in NEVER reads "residue — un-mined stock" (F9)');

    // ── (5) THE DEGRADED CHIP RENDERS IFF THE SERVER REPORTS DEGRADED (D10) ─────
    // (a) the live truth: the chip's presence tracks the real router_cache verdict.
    const liveDeg = await pg.evaluate(async (c) => {
      const st = await (await fetch('/shared/staleness?corpus=' + c)).json();
      const rc = (st.reads || []).find((r) => r.id === 'router_cache');
      return !!(rc && rc.degraded);
    }, CORPUS);
    const chipLive = await pg.$('#cx-degraded').then((x) => !!x);
    ok(chipLive === liveDeg, `the degraded chip presence (${chipLive}) matches the live router_cache verdict (${liveDeg})`);
    // (b) FORCE degraded → the chip renders + one click reveals the runnable remedy.
    await pg.route('**/shared/staleness**', (route) => route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify({ corpus: CORPUS, reads: [{ id: 'router_cache', label: 'router cache', present: true, fresh: false, degraded: true, fix: 'RE-EMBED-AT-THE-CLOSE — the local serving path never embeds' }], degraded: true }) }));
    await pg.goto(base + '/conceptric/map?corpus=' + CORPUS, { waitUntil: 'networkidle' });
    await pg.waitForSelector('#cx-degraded', { timeout: 8000 });
    ok(true, 'with the server reporting degraded, the warn chip renders (vectors stale — semantic rank off)');
    await pg.click('#cx-degraded'); await sleep(200);
    const fixShown = await pg.$eval('#cx-degraded-fix', (e) => e.classList.contains('is-open') && /RE-EMBED-AT-THE-CLOSE/.test(e.textContent));
    ok(fixShown, 'clicking the degraded chip reveals the runnable remedy (an offer, never a hang)');
    // (c) FORCE not-degraded → the chip is absent (the other half of the biconditional).
    await pg.route('**/shared/staleness**', (route) => route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify({ corpus: CORPUS, reads: [{ id: 'router_cache', label: 'router cache', present: true, fresh: true, degraded: false }], degraded: false }) }));
    await pg.goto(base + '/conceptric/map?corpus=' + CORPUS, { waitUntil: 'networkidle' });
    await pg.waitForSelector('#cx-strata [data-grade]'); await sleep(300);
    const chipGone = await pg.$('#cx-degraded').then((x) => !!x);
    ok(!chipGone, 'with the server reporting NOT degraded, the chip is absent (no green over a stale read; the "iff" holds)');
    await pg.unroute('**/shared/staleness**');

    // ── (6) ✎ RULE (D16) BANKS A TYPED DRAFT ──────────────────────────────────
    const banked = [];
    await pg.route('**/corpus/friction', (route) => {
      if (route.request().method() !== 'POST') return route.continue();
      let body = {}; try { body = JSON.parse(route.request().postData() || '{}'); } catch (_e) {}
      banked.push(body);
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, record: { id: 'fr-WALK-1' } }) });
    });
    await pg.goto(base + '/conceptric/map?corpus=' + CORPUS, { waitUntil: 'networkidle' });
    await pg.waitForSelector('#cx-ins-head .rule-chip', { state: 'attached', timeout: 8000 });
    await pg.hover('#cx-ins-head');
    await pg.click('#cx-ins-head .rule-chip'); await sleep(200);
    await pg.fill('#cx-ins-head .rule-cap textarea', 'this altitude read is exactly what I needed — bank it');
    await pg.click('#cx-ins-head .rule-bank'); await sleep(400);
    const receipt = await pg.textContent('#cx-ins-head .rule-banked').catch(() => '');
    ok(/banked/.test(receipt) && /fr-WALK-1/.test(receipt), 'the ✎ rule banked a typed draft and rendered its receipt: ' + JSON.stringify(receipt.trim().slice(0, 50)));
    ok(banked.length === 1 && banked[0].kind === 'fork' && banked[0].owning_layer === 'interface' && banked[0].text,
      'the banked record is a typed interface fork carrying his words: ' + JSON.stringify({ kind: banked[0] && banked[0].kind, layer: banked[0] && banked[0].owning_layer }));
    await pg.unroute('**/corpus/friction');

    // ── (7) 375px — SINGLE COLUMN, NO HORIZONTAL SCROLL ────────────────────────
    await pg.setViewportSize({ width: 375, height: 780 });
    await pg.goto(base + '/conceptric/map?corpus=' + CORPUS, { waitUntil: 'networkidle' });
    await pg.waitForSelector('#cx-board .hy-card'); await sleep(300);
    const noHScroll = await pg.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1);
    ok(noHScroll, '375px: no horizontal scroll (single column; the board keeps the centre)');

    ok(errs.length === 0, 'zero uncaught page errors across the whole walk: ' + JSON.stringify(errs));
    console.log(`\nWAVE 3 CONCEPTRIC — ${passed} assertions green.`);
  } finally {
    await b.close();
    if (scanner) scanner.kill('SIGKILL');
  }
})().catch((e) => { console.error('\nWALK FAILED:', e.message); if (scanner) scanner.kill('SIGKILL'); process.exit(1); });
