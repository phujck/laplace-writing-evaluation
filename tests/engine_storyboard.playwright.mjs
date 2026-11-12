// ENGINE STORYBOARD — the storyboard joined to the FocusState runtime (W-SB), driven against
// a REAL scanner. His ruling 2026-07-22: the storyboard is "the place where I can most easily
// see the thing that's going to be projected". The walk proves the surface-in-the-engine as
// OUTCOMES, not DOM presence:
//   · BRIEF BASE ALTITUDE (delta-and-ask): at rest NO section / weighting card exists in the
//     DOM; the composed brief prose is present and reads as a delta + an ask (not inventory);
//   · MATERIALISE: opening a count builds its object-set (the DOM appears on open);
//   · COUNTS LAW: the sections / weighting / findings chip equals the rows its door opens;
//   · GROUNDING VISIBLE (weighting-card-grounding-visible floor): every weighting card renders
//     its grounding IN PLACE (the why + its source nodes as working doors);
//   · HOVER LENS: revealing a card shifts no layout (rects byte-stable across the hover);
//   · PIN / REALLOCATE (cards-expand-in-place-with-context floor): opening a section OR a
//     weighting card reallocates AROUND the examined point — rail + breadcrumb + a VISIBLE
//     return door NAMING its destination ("back to the storyboard brief — where you were");
//   · CLOSE: exact scrollY restore; the return door absent from the resting DOM;
//   · NO LOBBY TAX (entry-point composition): a deep link (?section=) PRE-PINS its target on
//     load — reallocated with the return door, the brief NOT a mandatory step in that path;
//   · REGISTER LAW: no raw kind:hash node ids above the fold; SCROLL LAW at 1280 + 1536.
//
//   run:  node tests/engine_storyboard.playwright.mjs
//   Exits 0 all-green, non-zero on the first failed assertion.
import { createRequire } from 'module';
import { spawn, execSync } from 'child_process';
import net from 'net';

const require = createRequire(import.meta.url);
const fs = require('fs');
const { chromium } = require(execSync('npm root -g').toString().trim() + '/playwright');
const CHROME = execSync('ls /opt/pw-browsers/chromium-*/chrome-linux/chrome').toString().trim().split('\n')[0];
const PY = 'python3';
const CORPUS = 'paper_falqon';

let passed = 0;
function ok(cond, msg) { if (!cond) throw new Error('ASSERT FAILED: ' + msg); passed++; console.log('  ok -', msg); }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function freePort() { return new Promise((res) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); }); }
function waitFor(url, tries = 80) {
  return new Promise((res, rej) => { const tick = (n) => { const req = require('http').get(url, (r) => { r.resume(); res(true); });
    req.on('error', () => n <= 0 ? rej(new Error('server never came up')) : setTimeout(() => tick(n - 1), 250)); }; tick(tries); });
}

let scanner;
let planSnap = null;   // P3 — the fixture plan+ledger snapshot, restored in finally (clean tree)
const PLAN_JSON = execSync(`${PY} -c "from laplace.pipeline import registry; print(registry.plan_path_for('${CORPUS}'))"`).toString().trim();
const FRICTION = PLAN_JSON.replace(/projection_plan\.json$/, 'projection_plan.friction.jsonl');
(async () => {
  const repoRoot = execSync(`${PY} -c "from laplace.web.scanner import _repo_root; print(_repo_root().resolve())"`).toString().trim();
  const port = await freePort();
  scanner = spawn(PY, ['-m', 'laplace.web.scanner', '--port', String(port)], { cwd: repoRoot, stdio: 'ignore' });
  await waitFor(`http://127.0.0.1:${port}/storyboard`);
  const base = `http://127.0.0.1:${port}`;
  const b = await chromium.launch({ executablePath: CHROME });
  try {
    const pg = await b.newPage({ viewport: { width: 1280, height: 820 } });
    const errs = []; pg.on('pageerror', (e) => errs.push(String(e)));
    // stub the door TARGET surfaces so a click navigates instantly and never pollutes the
    // pageerror ledger with another surface's JS. The storyboard READS stay live.
    for (const surf of ['artefact', 'conceptric', 'pipeline', 'desk']) {
      await pg.route('**/' + surf + '**', (route) => route.request().resourceType() === 'document'
        ? route.fulfill({ status: 200, contentType: 'text/html', body: '<!doctype html><title>' + surf + ' stub</title>' })
        : route.continue());
    }

    await pg.goto(base + '/storyboard?corpus=' + CORPUS, { waitUntil: 'networkidle' });
    await pg.waitForSelector('[data-role="brief-prose"]', { timeout: 8000 });
    await sleep(250);

    // ── (1) THE BRIEF BASE ALTITUDE — the BOARD, captioned; no inventory at rest ──
    // SUPERSEDED 2026-07-22 (his correction: "You've killed any sense of being able to
    // see the whole storyboard"): the resting state now SHOWS the board — every section
    // as a spatial tile in paper order — with the brief prose as its caption. The old
    // assert (zero cards at rest) survives against the INVENTORY (.sb-card lists); the
    // picture (.sbb-sec tiles) must now be PRESENT at rest, tiles == the plan's sections.
    const prose = (await pg.textContent('[data-role="brief-prose"]')).trim();
    ok(prose.length > 60, 'the composed brief prose is present at rest: ' + JSON.stringify(prose.slice(0, 64)));
    ok(/since you last looked|has not|nothing has moved|generation|round/i.test(prose),
      'the brief reads as DELTA-AND-ASK (movement + generation), not inventory prose');
    const restDom = await pg.evaluate(() => ({
      cards: document.querySelectorAll('.sb-card').length,
      focus: document.querySelectorAll('.sb-focus-pane').length,
      tiles: document.querySelectorAll('.sbb-sec').length,
      claims: document.querySelectorAll('.sbb-claim').length,
      reallocated: document.querySelector('#eng-root').classList.contains('reallocated'),
    }));
    ok(restDom.cards === 0 && restDom.focus === 0 && !restDom.reallocated,
      'at rest NO inventory card exists in the DOM; the surface is at the brief: ' + JSON.stringify(restDom));
    const planN = await pg.evaluate(async (c) => {
      const b = await (await fetch('/storyboard/brief?corpus=' + c)).json();
      return { sections: (b.cards || []).length, weighting: (b.weighting || []).length };
    }, CORPUS);
    ok(restDom.tiles === planN.sections,
      `THE BOARD is seeable at rest — one tile per section (${restDom.tiles} of ${planN.sections})`);
    ok(restDom.claims === planN.weighting,
      `the contribution rank rides under the board (${restDom.claims} of ${planN.weighting} claims)`);

    // ── (1b) THE #1 RANK CHIP is a COMPOSED headline, never the raw ALL-CAPS goal body.
    // (finding: weighting[0].display was the verbatim shouting goal — the loudest thing at
    // rest.) The chip must read as a sentence-cased headline with NO 3+ word ALL-CAPS run
    // (the register law) — the same law audit_register enforces on served text.
    const topChip = ((await pg.textContent('.sbb-claim .cl')) || '').trim();
    ok(topChip.length > 8, 'the #1 rank chip carries a composed display line: ' + JSON.stringify(topChip));
    ok(!/\b[A-Z]{2,}(?:[ -][A-Z]{2,}){2,}\b/.test(topChip),
      'the #1 rank chip has NO 3+ word ALL-CAPS run (register law, no served shouting): ' + JSON.stringify(topChip));

    // ── (3) HOVER LENS — reveal with ZERO layout shift (board tiles) ─────────────
    await pg.$eval('.sbb-sec[data-sec]', (e) => e.scrollIntoView({ block: 'center' })); await sleep(150);
    const rB = await pg.$$eval('.sbb-sec[data-sec]', (els) => els.map((e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; }));
    await pg.hover('.sbb-sec[data-sec]'); await sleep(200);
    ok(await pg.$eval('.eng-lens', (e) => e.classList.contains('on')), 'hovering a board tile reveals the fixed lens (the section\'s job)');
    const rA = await pg.$$eval('.sbb-sec[data-sec]', (els) => els.map((e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; }));
    const moved = rB.filter((rb, i) => { const ra = rA[i]; return !ra || Math.abs(ra.x - rb.x) > 0.5 || Math.abs(ra.y - rb.y) > 0.5 || Math.abs(ra.w - rb.w) > 0.5 || Math.abs(ra.h - rb.h) > 0.5; });
    ok(moved.length === 0, `hover shifted NO layout (${rB.length} board-tile rects byte-stable)`);
    await pg.mouse.move(2, 2); await sleep(120);

    // ── (3b) THE RANK LIGHTS ITS LANDINGS — the relation shown ON the board ──────
    // (finding: every weighting node was composed with section:null, so hover lit ZERO
    // tiles and the lens dropped its "lands in" line.) Pick a claim whose nodes resolve a
    // board section and prove hover lights >0 tiles AND the lens carries the landing line.
    const litProbe = await pg.evaluate(async (c) => {
      const b = await (await fetch('/storyboard/brief?corpus=' + c)).json();
      const w = (b.weighting || []).find((x) => (x.nodes || []).some((n) => n.section));
      return w ? w.id : null;
    }, CORPUS);
    ok(litProbe, 'at least one contribution claim resolves a board landing (section populated, not null)');
    if (litProbe) {
      await pg.$eval(`.sbb-claim[data-claim="${litProbe}"]`, (e) => e.scrollIntoView({ block: 'center' })); await sleep(120);
      await pg.hover(`.sbb-claim[data-claim="${litProbe}"]`); await sleep(220);
      const nLit = await pg.evaluate(() => document.querySelectorAll('.sbb-sec.lit').length);
      ok(nLit > 0, `hovering the claim LIGHTS the board tiles where it lands (${nLit} tile(s) lit, not zero)`);
      ok(await pg.$eval('.eng-lens', (e) => /lands in/i.test(e.textContent)), 'the lens carries the restored "lands in" landing line');
      await pg.mouse.move(2, 2); await sleep(150);
    }

    // ── (4) PIN A SECTION FROM THE BOARD — reallocate + rail + named return door ──
    // pick a section that carries stock, so its grounding is a real node set.
    const richSec = await pg.evaluate(async (c) => {
      const b = await (await fetch('/storyboard/brief?corpus=' + c)).json();
      const s = (b.cards || []).find((x) => (x.source_nodes || []).length);
      return s ? s.id : (b.cards[0] || {}).id;
    }, CORPUS);
    await pg.$eval(`.sbb-sec[data-sec="${richSec}"]`, (e) => e.scrollIntoView({ block: 'center' })); await sleep(150);
    const scrollAtPin = await pg.evaluate(() => Math.round(window.scrollY));
    await pg.click(`.sbb-sec[data-sec="${richSec}"]`); await sleep(350);
    ok(await pg.$eval('#eng-root', (e) => e.classList.contains('reallocated')), 'clicking the section card REALLOCATED the surface');
    ok(await pg.$('.eng-rail').then((x) => !!x), 'the context rail is present');
    ok(await pg.$('.eng-breadcrumb').then((x) => !!x), 'the breadcrumb is present');
    ok(await pg.$eval('.eng-brief', (e) => getComputedStyle(e).display === 'none'), 'the brief is display:none while reallocated (the focus claims the centre — expand in place)');
    const doorLabel = (await pg.textContent('[data-role="return-door"] .rd-label')).trim();
    ok(/back to the board/i.test(doorLabel), 'the return door NAMES its destination (the board — the resting picture): ' + JSON.stringify(doorLabel));
    ok(await pg.$eval('[data-role="return-door"]', (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; }),
      'the return door is VISIBLE');
    // the section focus renders its grounding: the job (why) + its stock as working doors.
    const secGround = await pg.$$eval('.sb-focus-pane .sb-gnode', (e) => e.length);
    ok(secGround >= 1, `the section focus renders its stock as working doors (${secGround} source-node doors in place)`);

    // ── (4a) THE UNDO DOOR — plan/undo had a live endpoint but no control ─────────
    // (finding: POST /storyboard/plan/undo was live, no door existed.) It rides the action
    // row, worded with WHAT it undoes, re-reading from server truth after firing.
    ok(await pg.$('.sb-actions [data-act="undo-fire"]').then((x) => !!x),
      'the action row carries the UNDO door (undo last plan op) — the homeless plan/undo route, surfaced');
    const undoWill = (await pg.$$eval('.sb-actions .sb-act-will', (els) => els.map((e) => e.textContent).join(' '))).toLowerCase();
    ok(/undo/.test(undoWill) && /truncates the last banked plan op/.test(undoWill),
      'the undo door says what it undoes (the last banked plan op)');

    // ── (4b0) THE STRUCTURE DOORS — restructure / edit-spine / reconcile, surfaced ──
    // (finding: all three routes were live, neither the run tray nor the pinned focus
    // offered them.) A structure door group in the pinned focus, each naming what it
    // writes + its cost class, the plan-overwriting ones armed before firing.
    ok(await pg.$('.sb-structure').then((x) => !!x), 'the pinned focus carries the STRUCTURE door group');
    ok(await pg.$('.sb-structure [data-act="reconcile-fire"]').then((x) => !!x)
       && await pg.$('.sb-structure [data-act="restructure-preview"]').then((x) => !!x)
       && await pg.$('.sb-structure [data-act="edit-spine"] a[href*="view=reader-plan"]').then((x) => !!x),
      'the structure group offers reconcile + restructure + edit-spine (the three homeless routes)');
    const structText = (await pg.textContent('.sb-structure')).toLowerCase();
    ok(/idempotent/.test(structText) && /overwrites/.test(structText),
      'each structure door names its cost class (reconcile idempotent · the plan-overwriting ones marked)');

    // ── (4b0a) THE ARC COMPOSER — restructure previews HIS arc, not the identity no-op ──
    // (Gap 1+2: the preview always 400'd — the arc fetch passed { inject: [] }, dropping
    // corpus=; and even previewable it could only dry-run a 0-moved identity. Here the door
    // summons an EDITABLE ordering: reorder + rename, then dry-run HIS arc. We drive a
    // reorder, prove the preview reports the MOVE in composed words, and do NOT apply.)
    await pg.click('.sb-structure [data-act="restructure-preview"]');
    await pg.waitForSelector('.sb-arc-composer .sb-arc-row', { timeout: 8000 }); await sleep(150);
    const arcRows = await pg.$$eval('.sb-arc-composer .sb-arc-row', (e) => e.length);
    ok(arcRows >= 2, `the restructure door summons an EDITABLE arc composer (${arcRows} section rows, reorderable)`);
    ok((await pg.textContent('#sb-struct-status')).length > 8
       && !/→ 400|corpus= required|fetchJSON/i.test(await pg.textContent('#sb-struct-status')),
      'the arc loaded — NO raw "→ 400 / corpus= required / fetchJSON" leaks to the decision point (Gap 1 degrade)');
    // the composer pre-fills each section's title (his arc, not a blank form)
    const firstTitle = await pg.$eval('.sb-arc-composer .sb-arc-row .sb-arc-title', (e) => e.value);
    ok(firstTitle.length > 0, 'the arc composer pre-fills the section titles from the current arc: ' + JSON.stringify(firstTitle.slice(0, 40)));
    // DRIVE A REORDER — move the first section down; the moved counter must climb off zero
    await pg.click('.sb-arc-composer .sb-arc-row .sb-arc-down'); await sleep(150);
    const movedLine = (await pg.textContent('.sb-arc-composer [data-role="arc-moved"]')).trim();
    ok(/[1-9]\d* of \d+ section\(s\) moved/.test(movedLine),
      'reordering in the composer moves ≥1 section off the identity: ' + JSON.stringify(movedLine));
    // DRY-RUN his arc — the preview reports the move in composed words, and does NOT apply
    await pg.click('.sb-arc-composer [data-act="restructure-dryrun"]'); await sleep(500);
    const dryStruct = (await pg.textContent('#sb-struct-status')).trim();
    ok(/dry-run of your arc/i.test(dryStruct) && /[1-9]\d* moved/.test(dryStruct),
      'the dry-run re-reads HIS arc and reports the move (not "0 moved"): ' + JSON.stringify(dryStruct.slice(0, 100)));
    ok(!/→ \d{3}|fetchJSON|schema\./i.test(dryStruct),
      'the dry-run degrades to composed words — no raw HTTP/fetch text at the decision point');
    // the apply door is ARMED-BEHIND-a-preview, present but NOT fired (we never overwrite the plan)
    ok(await pg.$('.sb-arc-composer [data-act="restructure-apply"]').then((x) => !!x),
      'a clean dry-run reveals the apply door (arm-then-fire) — present, deliberately NOT fired');
    // close the composer (the door is a switch) so the P3 round-trip below reads a clean focus
    await pg.click('.sb-structure [data-act="restructure-preview"]'); await sleep(150);

    // ── (4b) P3 — THE ACTION ROW: the pinned card's edits FIRE from the card ──────
    // The prediction killed: reaching to ACT on the pinned card no longer meets a read-only
    // surface. The acts fire through their EXISTING /storyboard/plan endpoint. We snapshot the
    // plan+ledger, drive ONE non-destructive act (a retitle changed then changed back through the
    // same endpoint — byte-identical after), and prove the re-render is from SERVER TRUTH.
    planSnap = { plan: fs.readFileSync(PLAN_JSON), fricThere: fs.existsSync(FRICTION),
                 fric: fs.existsSync(FRICTION) ? fs.readFileSync(FRICTION) : null };
    ok(await pg.$('.sb-actions').then((x) => !!x), 'the pinned section carries the ACTION ROW (P3 — the card is no longer read-only)');
    ok(await pg.$('.sb-actions [data-act="retitle-input"]').then((x) => !!x)
       && await pg.$('.sb-actions [data-act="retitle-save"]').then((x) => !!x),
      'the action row offers RETITLE (an inline field saved through the endpoint)');
    ok(await pg.$('.sb-actions [data-act="reorder-up"]').then((x) => !!x)
       && await pg.$('.sb-actions [data-act="reorder-down"]').then((x) => !!x),
      'the action row offers REORDER up/down (within the section order)');
    ok(await pg.$('.sb-actions [data-act="edit-job-save"]').then((x) => !!x),
      'the action row offers EDIT-JOB (an inline field saved through the endpoint)');
    // Gap 4 — edit-job is PARAGRAPH-SCALE prose: a TEXTAREA (not a single-line input),
    // pre-filled from the server job, sized honestly.
    const jobField = await pg.$eval('.sb-actions [data-act="edit-job-input"]', (e) => ({ tag: e.tagName, val: e.value }));
    ok(jobField.tag === 'TEXTAREA', 'EDIT-JOB is a textarea (paragraph-scale prose), not a single-line input: ' + jobField.tag);
    const serverJob = await pg.evaluate(async ({ c, s }) => {
      const bd = await (await fetch('/storyboard/brief?corpus=' + c)).json();
      return ((bd.cards || []).find((x) => x.id === s) || {}).job || '';
    }, { c: CORPUS, s: richSec });
    ok(jobField.val === serverJob, 'the edit-job textarea is PRE-FILLED with the server job (never blank when a job exists)');
    const willText = (await pg.$$eval('.sb-actions .sb-act-will', (els) => els.map((e) => e.textContent).join(' '))).toLowerCase();
    ok(/writes the section (order|title)/.test(willText) && /rewrites/.test(willText),
      'each act says what it WRITES before firing (what-will-this-do words present)');
    ok(/\/storyboard\/plan/.test((await pg.textContent('.sb-actions-h')).toLowerCase()),
      'the acts name the endpoint they fire through (/storyboard/plan)');

    const titleOf = (sid) => pg.evaluate(async ({ c, s }) => {
      const bd = await (await fetch('/storyboard/brief?corpus=' + c)).json();
      return ((bd.cards || []).find((x) => x.id === s) || {}).title;
    }, { c: CORPUS, s: sid });
    const origTitle = await titleOf(richSec);
    const sentinel = origTitle + ' ⟿P3';
    // fire the retitle THROUGH the endpoint (one POST) → the focus re-renders from server truth
    await pg.fill('.sb-actions [data-act="retitle-input"]', sentinel);
    await pg.click('.sb-actions [data-act="retitle-save"]');
    await pg.waitForFunction((s) => { const el = document.querySelector('.sb-focus-title'); return el && el.textContent.includes(s); },
      sentinel, { timeout: 8000 });
    ok((await titleOf(richSec)) === sentinel,
      'the retitle fired ONE POST through /storyboard/plan and the SERVER carries the new title (never optimistic)');
    ok((await pg.$eval('.sb-actions [data-act="retitle-input"]', (e) => e.value)) === sentinel,
      'the focus RE-RENDERED from server truth (the action field reflects the server value)');
    // change it BACK through the SAME endpoint — the projected title is byte-identical (no residue)
    await pg.fill('.sb-actions [data-act="retitle-input"]', origTitle);
    await pg.click('.sb-actions [data-act="retitle-save"]');
    await pg.waitForFunction((s) => { const el = document.querySelector('.sb-focus-title');
      return el && el.textContent.includes(s) && !el.textContent.includes('⟿P3'); }, origTitle, { timeout: 8000 });
    ok((await titleOf(richSec)) === origTitle,
      'changed back through the same endpoint — the section title is byte-identical to the original (no residue)');

    // ── (5) CLOSE — exact scrollY restore + return door absent at rest ───────────
    await pg.keyboard.press('Escape'); await sleep(300);
    ok(!(await pg.$eval('#eng-root', (e) => e.classList.contains('reallocated'))), 'Esc closed the focus back to the brief');
    const scrollAfter = await pg.evaluate(() => Math.round(window.scrollY));
    ok(Math.abs(scrollAfter - scrollAtPin) <= 1, `exact scrollY restored on close (${scrollAfter} ≈ ${scrollAtPin})`);
    ok((await pg.$('[data-role="return-door"]')) === null, 'the return door is ABSENT from the resting DOM (no hidden residue)');

    // ── (6+7) THE WEIGHTING — SUPERSEDED 2026-07-22: the rank rides UNDER the board
    // at rest (one claim chip per weighting row, counts law held in (1)); opening a
    // claim reallocates around it with the grounding IN the focus. The old chip-then-
    // card-list flow died with the inventory.
    const resolvedCard = await pg.evaluate(async (c) => {
      const b = await (await fetch('/storyboard/brief?corpus=' + c)).json();
      const w = (b.weighting || []).find((x) => x.resolved) || b.weighting[0];
      return w.id;
    }, CORPUS);
    await pg.$eval(`.sbb-claim[data-claim="${resolvedCard}"]`, (e) => e.scrollIntoView({ block: 'center' })); await sleep(120);
    await pg.click(`.sbb-claim[data-claim="${resolvedCard}"]`); await sleep(350);
    ok(await pg.$eval('#eng-root', (e) => e.classList.contains('reallocated')), 'clicking the weighting card REALLOCATED around it (expand in place, not a jump)');
    ok(/back to the board/i.test((await pg.textContent('[data-role="return-door"] .rd-label')).trim()),
      'the weighting focus carries the named return door (the board)');
    const wFocusWhy = (await pg.textContent('.sb-focus-pane .sb-ground-why')).trim();
    ok(wFocusWhy.length > 20, 'the weighting focus renders the WHY in place: ' + JSON.stringify(wFocusWhy.slice(0, 56)));
    ok((await pg.$$eval('.sb-focus-pane .sb-gnode', (e) => e.length)) >= 1, 'the weighting focus names its source nodes as working doors, in place');
    await pg.keyboard.press('Escape'); await sleep(250);

    // ── (8) NO LOBBY TAX — a deep link PRE-PINS its target on load ───────────────
    const pg2 = await b.newPage({ viewport: { width: 1280, height: 820 } });
    const errs2 = []; pg2.on('pageerror', (e) => errs2.push(String(e)));
    for (const surf of ['artefact', 'conceptric']) {
      await pg2.route('**/' + surf + '**', (route) => route.request().resourceType() === 'document'
        ? route.fulfill({ status: 200, contentType: 'text/html', body: '<!doctype html><title>' + surf + ' stub</title>' }) : route.continue());
    }
    await pg2.goto(base + '/storyboard?corpus=' + CORPUS + '&section=' + richSec, { waitUntil: 'networkidle' });
    await pg2.waitForSelector('#eng-root.reallocated', { timeout: 8000 }); await sleep(200);
    ok(await pg2.$eval('#eng-root', (e) => e.classList.contains('reallocated')), 'a ?section= deep link LANDS reallocated on its target (entry-point composition, no toll booth)');
    ok(await pg2.$('[data-role="return-door"]').then((x) => !!x), 'the deep-link landing carries the return door (the brief is one click back, not a mandatory step)');
    ok(await pg2.$eval('.eng-brief', (e) => getComputedStyle(e).display === 'none'), 'the brief did NOT render as a mandatory step in the deep-link path (it is display:none behind the pinned target)');
    const focusTitle = (await pg2.textContent('.sb-focus-title')).trim();
    ok(focusTitle.length > 0, 'the pinned target is the deep-linked section: ' + JSON.stringify(focusTitle.slice(0, 40)));
    await pg2.close();

    // ── (9) THE REGISTER LAW — no raw kind:hash ids above the fold ───────────────
    const aboveFold = await pg.evaluate(() => {
      const clone = document.body.cloneNode(true);
      // node ids are allowed inside href/data-* (machine attrs), not as visible register text
      clone.querySelectorAll('a, [data-gnode], [data-section], [data-card]').forEach((e) => {
        e.removeAttribute('href'); e.removeAttribute('data-gnode'); e.removeAttribute('data-section'); e.removeAttribute('data-card');
      });
      return clone.innerText;
    });
    ok(!/\b(res|thm|def|eq|derivation|goal|irf|ires):[a-z0-9]{4,}/i.test(aboveFold),
      'no raw kind:hash node ids in the visible register above the fold (terms carry the meaning)');

    // ── (10) THE SCROLL LAW at 1280 + 1536 ──────────────────────────────────────
    for (const w of [1280, 1536]) {
      await pg.setViewportSize({ width: w, height: 860 });
      await pg.goto(base + '/storyboard?corpus=' + CORPUS, { waitUntil: 'networkidle' });
      await pg.waitForSelector('.sbb-sec[data-sec]', { timeout: 8000 }); await sleep(150);
      const noH = await pg.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1);
      ok(noH, `the scroll law holds at ${w}px with the board seeable: the page body never scrolls horizontally`);
    }

    // ── (11) THE DRY-RUN DEGRADES TO COMPOSED WORDS on a propagate error ─────────
    // (finding: GET /storyboard/propagate 400'd on falqon and the run tray surfaced the raw
    // fetchJSON/schema text beside the arm button.) Driven against a STUBBED 400 carrying
    // raw schema text: the tray's dry-run must degrade to composed words — never the raw
    // HTTP/schema string at the decision point — while arming still banks only the order.
    const pg3 = await b.newPage({ viewport: { width: 1280, height: 900 } });
    const errs3 = []; pg3.on('pageerror', (e) => errs3.push(String(e)));
    for (const surf of ['artefact', 'conceptric', 'pipeline', 'desk']) {
      await pg3.route('**/' + surf + '**', (route) => route.request().resourceType() === 'document'
        ? route.fulfill({ status: 200, contentType: 'text/html', body: '<!doctype html><title>' + surf + ' stub</title>' }) : route.continue());
    }
    await pg3.route('**/storyboard/propagate**', (route) => route.fulfill({
      status: 400, contentType: 'application/json',
      body: JSON.stringify({ error: "feedback kind 'author-read' has no routing in schema.KIND_TO_WORK" }) }));
    await pg3.goto(base + '/storyboard?corpus=' + CORPUS, { waitUntil: 'networkidle' });
    await pg3.waitForSelector('[data-role="brief-prose"]', { timeout: 8000 }); await sleep(200);
    await pg3.click(".sb-count[data-materialize='run']"); await sleep(400);
    await pg3.waitForSelector('.rt-launch[data-launch]', { timeout: 8000 });
    await pg3.click('.rt-launch[data-launch]'); await sleep(500);
    const dryText = ((await pg3.textContent('.rt-dry')) || '').trim();
    ok(/could not be read|nothing is staged/i.test(dryText),
      'the dry-run degrades to COMPOSED words on a propagate 400: ' + JSON.stringify(dryText.slice(0, 90)));
    ok(!/KIND_TO_WORK|schema\.|fetchJSON|→ 400|has no routing/.test(dryText),
      'NO raw HTTP / schema text leaks to the decision point: ' + JSON.stringify(dryText.slice(0, 90)));
    await pg3.close();

    ok(errs.length === 0 && errs2.length === 0 && errs3.length === 0,
      'zero uncaught page errors across the whole walk: ' + JSON.stringify(errs.concat(errs2).concat(errs3)));
    console.log(`\nENGINE STORYBOARD — ${passed} assertions green.`);
  } finally {
    await b.close();
    if (scanner) scanner.kill('SIGKILL');
    // P3 — restore the fixture plan + ledger so the non-destructive round-trip leaves a CLEAN tree.
    try {
      if (planSnap) {
        fs.writeFileSync(PLAN_JSON, planSnap.plan);
        if (planSnap.fricThere) fs.writeFileSync(FRICTION, planSnap.fric);
        else if (fs.existsSync(FRICTION)) fs.unlinkSync(FRICTION);
      }
    } catch (_e) { /* best-effort fixture restore */ }
  }
})().catch((e) => { console.error('\nWALK FAILED:', e.message); if (scanner) scanner.kill('SIGKILL'); process.exit(1); });
