// ENGINE COCKPIT — the FocusState runtime + the growth cockpit, driven against a REAL scanner.
//
// The walk proves the resting-state law (E), the geometry couplet (B), and the entry contract (F)
// as OUTCOMES, not DOM presence:
//   · brief base altitude: at rest NO queue / ladder / coverage node exists in the DOM; the
//     composed brief prose is present;
//   · materialise: opening a count builds its object-set (the DOM appears on open);
//   · hover lens: revealing an item shifts no layout (element rects byte-stable across the hover);
//   · pin the authored-goal tension: reallocation + rail + breadcrumb + a VISIBLE return door
//     NAMING its destination;
//   · select REGOAL: the consequence binds to the selected row; the confirm gate shows the
//     reconstructed goal; commit stays disabled until confirmed — the walk asserts the gate and
//     does NOT commit a supersede;
//   · close: exact scrollY restore + the selected verb restored on reopen;
//   · the register law: no raw GT-/DQ-/PV- ids above the fold (ids live at audit depth).
//
//   run:  node tests/engine_cockpit.playwright.mjs
//   Exits 0 all-green, non-zero on the first failed assertion.
import { createRequire } from 'module';
import { spawn, execSync } from 'child_process';
import net from 'net';

const require = createRequire(import.meta.url);
const { chromium } = require(execSync('npm root -g').toString().trim() + '/playwright');
const CHROME = execSync('ls /opt/pw-browsers/chromium-*/chrome-linux/chrome').toString().trim().split('\n')[0];
const PY = 'python3';
const CORPUS = 'paper_falqon';

let passed = 0;
function ok(cond, msg) { if (!cond) throw new Error('ASSERT FAILED: ' + msg); passed++; console.log('  ok -', msg); }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// §C5 write-path proof (gap 2): the node-scoped COMMENT composer is DRIVEN, banking one review
// note into paper_falqon's REAL manuscript feedback ledger (POST /corpus/feedback) — then
// cleaned out surgically in the finally (this walk is MUTATING_WALKS-marked).
const PROBE_COMMENT = 'zzz-probe-comment-' + Date.now();
function cleanupComment() {
  try {
    execSync(`${PY} - <<'PY'
from laplace.web.scanner import _repo_root, _corpus_feedback_ledger
led = _corpus_feedback_ledger(_repo_root(), 'paper_falqon')
if led and led.is_file():
    rows = [l for l in led.read_text().splitlines() if l.strip()]
    keep = [l for l in rows if ${JSON.stringify(PROBE_COMMENT)} not in l]
    led.write_text(('\\n'.join(keep) + '\\n') if keep else '')
    print('  comment cleanup removed', len(rows) - len(keep), 'probe comment(s)')
PY`, { stdio: 'inherit' });
  } catch (e) { console.error('  comment cleanup error:', e.message); }
}
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
  await waitFor(`http://127.0.0.1:${port}/conceptric`);
  const base = `http://127.0.0.1:${port}`;
  const b = await chromium.launch({ executablePath: CHROME });
  try {
    const pg = await b.newPage({ viewport: { width: 1280, height: 380 } });
    const errs = []; pg.on('pageerror', (e) => errs.push(String(e)));
    // stub the map door so an accidental navigation never pollutes the pageerror ledger.
    await pg.route('**/conceptric/map**', (route) => route.request().resourceType() === 'document'
      ? route.fulfill({ status: 200, contentType: 'text/html', body: '<!doctype html><title>map stub</title>' })
      : route.continue());
    // REFUSE every POST /growth/rule — the walk must never bank a supersede.
    await pg.route('**/growth/rule', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: false, error: 'walk: no bank' }) }));
    // REFUSE every POST /growth/route-gap too — the walk asserts the door + its words, never fires it.
    await pg.route('**/growth/route-gap', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: false, error: 'walk: no bank' }) }));

    await pg.goto(base + '/conceptric?corpus=' + CORPUS, { waitUntil: 'networkidle' });
    await pg.waitForSelector('[data-role="brief-prose"]', { timeout: 8000 });
    await sleep(300);

    // ── (1) THE BRIEF BASE ALTITUDE — the SHAPE, captioned (E, as corrected) ──
    // SUPERSEDED 2026-07-22 (his correction: the resting-state law was never
    // absence-of-the-object): the resting state now SHOWS the project's shape —
    // the ladder strip, the coverage axes as worded tiles (zeros red words), and
    // any open tension pinned in the picture. The old zero-DOM assert survives
    // against the INVENTORY (detail rows/cards); the picture must be PRESENT.
    const prose = (await pg.textContent('[data-role="brief-prose"]')).trim();
    ok(prose.length > 40, 'the composed brief prose is present at rest: ' + JSON.stringify(prose.slice(0, 60)));
    await pg.waitForSelector('.ck-shape .ck-srungs, .ck-shape .ck-shape-note', { timeout: 8000 }); await sleep(150);
    const restDom = await pg.evaluate(() => ({
      ladder: document.querySelectorAll('.ck-ladder').length,
      axis: document.querySelectorAll('.ck-axis').length,
      qrow: document.querySelectorAll('.ck-qrow').length,
      tcards: document.querySelectorAll('.ck-card').length,
      shapeRungs: document.querySelectorAll('.ck-srung').length,
      shapeAxes: document.querySelectorAll('.ck-saxis').length,
    }));
    ok(restDom.ladder === 0 && restDom.axis === 0 && restDom.qrow === 0 && restDom.tcards === 0,
      'at rest NO detail row / inventory card exists in the DOM: ' + JSON.stringify(restDom));
    ok(restDom.shapeRungs >= 1, 'THE SHAPE is seeable at rest — the ladder strip is present: ' + restDom.shapeRungs + ' rungs');
    ok(restDom.shapeAxes >= 1, 'THE SHAPE carries the coverage axes as worded tiles: ' + restDom.shapeAxes);
    // honest zeros stay red WORDS on the shape (never a proxy bar)
    const zeroWords = await pg.$$eval('.ck-saxis.is-zero .aw', (els) => els.map((e) => e.textContent.trim()));
    ok(zeroWords.every((w) => /measured zero/.test(w)), 'zero axes speak "measured zero" as words: ' + JSON.stringify(zeroWords));
    // the counts law: the tension marks IN the picture equal the tensions the door serves.
    // POST-REGOAL the count can honestly be zero — then no mark exists (presence by relevance).
    const tCount = await pg.evaluate(async (c) => {
      const b = await (await fetch('/growth/brief?corpus=' + c)).json();
      return (b.counts || {}).tensions || 0;
    }, CORPUS);
    const tMarks = await pg.$$eval('.ck-shape-tension', (e) => e.length);
    ok(tMarks === tCount, `tensions render IN the picture, one mark each (${tMarks} of ${tCount})`);

    // ── (2) MATERIALISE — opening a count builds its object-set ────────────────
    await pg.click('.ck-count[data-materialize="queue"]');
    await pg.waitForSelector('.ck-qrow', { timeout: 8000 }); await sleep(150);
    const qrows = await pg.$$eval('.ck-qrow', (e) => e.length);
    ok(qrows > 0, 'opening the queue count materialised its rows (DOM appears on open): ' + qrows);
    const qChip = Number((await pg.textContent('.ck-count[data-materialize="queue"] .ck-cn')).trim());
    ok(qChip === qrows, `the counts law holds: the queue chip (${qChip}) equals the rows it opened (${qrows})`);

    // ── (2a) QUEUE ROWS ARE REAL BUTTONS — click opens the working account + provenance in place ──
    const qrole = await pg.$eval('.ck-qrow', (e) => e.getAttribute('role'));
    ok(qrole === 'button', 'a queue row is a real button (role=button, keyboard-reachable)');
    ok(await pg.$eval('.ck-qrow', (e) => e.tabIndex >= 0), 'a queue row is tabindex-reachable');
    ok(!(await pg.$eval('.ck-qrow', (e) => e.classList.contains('is-open'))), 'a queue row is closed at rest (its working account is not yet surfaced)');
    await pg.click('.ck-qrow .ck-qmeta'); await sleep(200);   // click a non-interactive part (never the route door)
    ok(await pg.$eval('.ck-qrow', (e) => e.classList.contains('is-open')), 'clicking a queue row OPENS it in place (no navigation)');
    ok(await pg.$eval('.ck-qrow', (e) => e.getAttribute('aria-expanded') === 'true'), 'the opened row reports aria-expanded=true');
    const qworking = (await pg.textContent('.ck-qrow.is-open .ck-qworking')).trim();
    ok(qworking.length > 30, 'the opened row surfaces its composed working account: ' + JSON.stringify(qworking.slice(0, 60)));
    ok(!!(await pg.$('.ck-qrow.is-open .ck-audit')), 'the opened row carries its audit provenance in place (ids at audit depth)');
    // fix 4 — the node-scoped ✎ mouth is present on the queue row (the shell atom, ctx-scoped)
    ok(!!(await pg.$('.ck-qrow.hy-rulable')), 'the queue row is a rulable host (the node-scoped ✎ attaches to it)');
    ok(!!(await pg.$('.ck-qrow .rule-chip')), 'the queue row carries the ✎ rule chip (a rule banks scoped to this claim)');

    // ── (2a·comment) THE NODE-SCOPED COMMENT COMPOSER (gap 2) — the `comment` verb (POST
    // /corpus/feedback): a review note on the manuscript ledger, beside the ✎ and CLEARLY
    // distinguished from it (comment = a review note; ✎ = an interface fork). Banks against the
    // claim the demand names and echoes the banked row IN PLACE. A probe row, cleaned out later.
    const composer = await pg.$('.ck-qrow.is-open .ck-comment');
    ok(!!composer, 'the opened queue row carries the node-scoped comment composer (beside the ✎)');
    const composerNode = await pg.$eval('.ck-qrow.is-open .ck-comment', (e) => e.dataset.cnode);
    ok(!!composerNode, 'the composer is scoped to the claim the demand names: ' + JSON.stringify(composerNode));
    const composerLabel = (await pg.textContent('.ck-qrow.is-open .ck-comment .ck-comment-h')).trim();
    ok(/review note/i.test(composerLabel) && /interface fork/i.test(composerLabel),
      'the composer names itself a review note, distinct from the ✎ interface fork: ' + JSON.stringify(composerLabel.slice(0, 90)));
    await pg.fill('.ck-qrow.is-open .ck-comment .ck-comment-text', PROBE_COMMENT + ' — this claim reads well here');
    await pg.click('.ck-qrow.is-open .ck-comment .ck-comment-bank');
    await pg.waitForSelector('.ck-qrow.is-open .ck-comment .ck-comment-echoed', { timeout: 8000 });
    const echoed = (await pg.textContent('.ck-qrow.is-open .ck-comment .ck-comment-echoed')).trim();
    ok(echoed.includes(PROBE_COMMENT), 'the banked comment ECHOES in place (POST /corpus/feedback landed on the ledger): ' + JSON.stringify(echoed.slice(0, 60)));
    ok(/author/.test(echoed), 'the echoed comment NAMES its actor (author) — the actor law');
    // the row did NOT toggle closed when the composer was used (the composer owns its clicks)
    ok(await pg.$eval('.ck-qrow.is-open', (e) => e.classList.contains('is-open')), 'using the composer did not toggle the queue row shut (it owns its own clicks)');

    // ── (2b) COVERAGE — an axis TILE on the shape opens the detail, doors included ──
    await pg.click('.ck-saxis[data-shape="coverage"]');
    await pg.waitForSelector('.ck-axis', { timeout: 8000 }); await sleep(150);
    const axcount = await pg.$$eval('.ck-axis', (e) => e.length);
    ok(axcount >= 1, 'opening the coverage count materialised its axis rows (DOM appears on open): ' + axcount);
    const rbtn = await pg.$('.ck-axis .ck-routebtn');
    ok(!!rbtn, 'a coverage axis with a gap carries the axis-gap routing button (a real door)');
    const rlabel = (await pg.textContent('.ck-axis .ck-routebtn')).trim();
    ok(/route to (figure|derivation|literature) work/i.test(rlabel), 'the routing button names its door: ' + JSON.stringify(rlabel));
    // the consequence idiom: the button states what it writes (a banked order) in plain words.
    const rconseq = (await pg.textContent('.ck-axis .ax-conseq')).trim();
    ok(/bank/i.test(rconseq) && rconseq.length > 30, 'the routing button states what it writes, a banked order: ' + JSON.stringify(rconseq.slice(0, 60)));
    ok(!(await pg.$eval('.ck-axis .ck-routebtn', (e) => e.classList.contains('is-selected'))), 'the routing door is not pre-selected (a door, not an auto-fire)');
    // fix 4 — the coverage axis TILE on the shape is node-scoped rulable (the ✎ mouth)
    ok(!!(await pg.$('.ck-saxis.hy-rulable .rule-chip')), 'a coverage axis tile carries the node-scoped ✎ rule chip');

    // ── (2c) WORK-ORDERS EMPTY CHIP TEACHES — never inert, never wordless (fix 8) ──
    const woChip = await pg.$('.ck-count[data-materialize="work-orders"]');
    ok(!!woChip, 'the work-orders chip is present');
    ok(!(await pg.$eval('.ck-count[data-materialize="work-orders"]', (e) => e.getAttribute('aria-disabled') === 'true')),
      'the empty work-orders chip is NOT inert (aria-disabled unset) — it opens to teach');
    await pg.click('.ck-count[data-materialize="work-orders"]'); await sleep(300);
    const woTeach = (await pg.textContent('.ck-empty-teach').catch(() => '')) || '';
    ok(/routing a coverage gap/i.test(woTeach) && /banks one here/i.test(woTeach),
      'the empty work-orders chip teaches how an order gets here: ' + JSON.stringify(woTeach.slice(0, 60)));
    await pg.keyboard.press('Escape'); await sleep(250);

    // (the tension counts law moved to (1) — marks in the picture, one per open tension)

    // ── THE REGISTER LAW — no raw ids above the fold (state-independent; run at rest) ─────
    const aboveFold = await pg.evaluate(() => {
      const audit = document.querySelector('.ck-audit');
      const clone = document.body.cloneNode(true);
      clone.querySelectorAll('.ck-audit').forEach((e) => e.remove());   // ids are allowed AT audit depth
      return clone.innerText;
    });
    ok(!/\b(GT|DQ|PV|RW)-[0-9a-f]{4,}/i.test(aboveFold), 'no raw GT-/DQ-/PV- ids above the fold (ids live at audit depth)');

    // ── DECISION-ALTITUDE DRIVE — behind a TENSION-PRESENCE CHECK ─────────────────────────
    // POST-REGOAL (W-TRIAGE 2026-07-22): paper_falqon's authored-goal tension is RECONCILED (the
    // REGOAL's goal supersede now postdates the verdict — /growth/tensions returns zero for
    // AUTHOR-GOAL), so tCount is 0 and no tension card materialises. The full pre-ruling drive below
    // was WALK-PROVEN before the reconciliation and re-arms the day a corpus carries a live
    // authored-goal tension again: (3) hover-lens (reveal with ZERO layout shift) → (4) pin the
    // AUTHOR-GOAL tension (reallocate + context rail + breadcrumb + a VISIBLE 'back to the brief'
    // return door) → (5) select REGOAL (the shown consequence BINDS to the selected row; the
    // confirm-before-supersede gate shows the reconstructed goal; commit stays DISABLED until
    // confirmed) → (6) exact scrollY restore on close → reopen restores the selected REGOAL verb.
    if (tCount >= 1) {
      // ── (3) HOVER LENS — reveal with ZERO layout shift ───────────────────────
      // SUPERSEDED 2026-07-22: the tension lives IN the picture (.ck-shape-tension),
      // not in a materialised card list — the hover-lens + pin drive rides the mark.
      await pg.$eval('.ck-shape-tension', (e) => e.scrollIntoView({ block: 'center' })); await sleep(200);
      const rectsBefore = await pg.$$eval('.ck-shape-tension', (els) => els.map((e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; }));
      await pg.hover('.ck-shape-tension'); await sleep(250);
      const lensOn = await pg.$eval('.eng-lens', (e) => e.classList.contains('on'));
      ok(lensOn, 'hovering the tension mark reveals the fixed lens (the working account)');
      const rectsAfter = await pg.$$eval('.ck-shape-tension', (els) => els.map((e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; }));
      const moved = rectsBefore.filter((rb, i) => { const ra = rectsAfter[i]; return !ra || Math.abs(ra.x - rb.x) > 0.5 || Math.abs(ra.y - rb.y) > 0.5 || Math.abs(ra.w - rb.w) > 0.5 || Math.abs(ra.h - rb.h) > 0.5; });
      ok(moved.length === 0, `hover shifted NO layout (${rectsBefore.length} mark rects byte-stable)`);
      await pg.mouse.move(2, 2); await sleep(150);

      // centre the authored-goal mark so the pin click does NOT itself scroll, then capture the
      // exact scrollY the pin will restore to (a nonzero position — a real restore proof).
      await pg.$eval('.ck-shape-tension[data-signature="AUTHOR-GOAL"]', (e) => e.scrollIntoView({ block: 'center' })); await sleep(200);
      const scrollAtPin = await pg.evaluate(() => Math.round(window.scrollY));
      ok(scrollAtPin > 0, 'the brief is scrolled to a nonzero position before the pin (a real restore proof): ' + scrollAtPin);

      // ── (4) PIN THE AUTHORED-GOAL TENSION — reallocate + rail + return door ───
      await pg.click('.ck-shape-tension[data-signature="AUTHOR-GOAL"]'); await sleep(400);
      ok(await pg.$eval('#eng-root', (e) => e.classList.contains('reallocated')), 'clicking the tension REALLOCATED the surface');
      ok(await pg.$('.eng-rail').then((x) => !!x), 'the context rail is present');
      ok(await pg.$('.eng-breadcrumb').then((x) => !!x), 'the breadcrumb is present');
      const door = await pg.$('[data-role="return-door"]');
      ok(!!door, 'a return door is present in the focused state');
      const doorLabel = (await pg.textContent('[data-role="return-door"] .rd-label')).trim();
      ok(/back to the brief/i.test(doorLabel), 'the return door NAMES its destination: ' + JSON.stringify(doorLabel));
      const doorVisible = await pg.$eval('[data-role="return-door"]', (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
      ok(doorVisible, 'the return door is VISIBLE (a return door that is not visible does not exist)');

      // ── (5) SELECT REGOAL — consequence binds to the row; confirm gate; commit disabled ──
      await pg.click('.ck-verb[data-verb="REGOAL"]'); await sleep(300);
      ok(await pg.$eval('.ck-verb[data-verb="REGOAL"]', (e) => e.classList.contains('is-selected')), 'REGOAL is the selected verb');
      const shownConseq = (await pg.textContent('#ck-conseq')).trim();
      // the consequence shown must be REGOAL's own row consequence (bound by construction).
      const rowConseq = await pg.evaluate(async (c) => {
        const d = await (await fetch('/growth/tensions?corpus=' + c)).json();
        const row = (d.tensions || []).find((t) => t.signature === 'AUTHOR-GOAL');
        const a = row.composed.decision.actions.find((x) => x.verb === 'REGOAL');
        return a.consequence;
      }, CORPUS);
      ok(shownConseq === rowConseq.trim(), 'the shown consequence BINDS to the selected REGOAL row (not a card-level consequence)');
      ok(await pg.$eval('#ck-confirm', (e) => e.classList.contains('on')), 'REGOAL shows the confirm-before-supersede gate');
      const reconstructed = (await pg.inputValue('#ck-confirm-text')).trim();
      ok(/methodological development|mid-circuit/i.test(reconstructed), 'the confirm gate shows the reconstructed goal text: ' + JSON.stringify(reconstructed.slice(0, 50)));
      ok(await pg.$eval('#ck-commit', (e) => e.disabled), 'commit stays DISABLED until the goal text is confirmed (no silent supersede)');
      // confirm → commit enables (but we do NOT click commit).
      await pg.click('#ck-confirm-btn'); await sleep(150);
      ok(await pg.$eval('#ck-commit', (e) => !e.disabled), 'confirming the goal text enables commit (but the walk banks nothing)');

      // ── (6) CLOSE — exact scrollY restore + selection restore on reopen ──────
      await pg.keyboard.press('Escape'); await sleep(300);
      ok(!(await pg.$eval('#eng-root', (e) => e.classList.contains('reallocated'))), 'Esc closed the focus back to the brief');
      const scrollAfter = await pg.evaluate(() => Math.round(window.scrollY));
      ok(Math.abs(scrollAfter - scrollAtPin) <= 1, `exact scrollY restored on close (${scrollAfter} ≈ ${scrollAtPin})`);
      // the return door is absent from the resting DOM (no css-hidden residue).
      ok((await pg.$('[data-role="return-door"]')) === null, 'the return door is ABSENT from the resting DOM (no hidden residue)');
      // reopen → the selected verb is restored (B.3 selection restore).
      await pg.click('.ck-shape-tension[data-signature="AUTHOR-GOAL"]'); await sleep(400);
      ok(await pg.$eval('.ck-verb[data-verb="REGOAL"]', (e) => e.classList.contains('is-selected')), 'reopening the tension RESTORED the selected REGOAL verb');
    } else {
      // THE HONEST ZERO-TENSION BRIEF (post-REGOAL): nothing to pin, nothing to reallocate to.
      ok((await pg.$('.ck-shape-tension')) === null, 'the honest zero-tension shape: paper_falqon reconciled post-REGOAL — no tension mark in the picture');
      ok(!(await pg.$eval('#eng-root', (e) => e.classList.contains('reallocated'))), 'the brief stays at rest — a zero-tension brief has nothing to reallocate to');
      ok((await pg.$('[data-role="return-door"]')) === null, 'no return door in the resting zero-tension brief (nothing pinned)');

      // ── (1b) THE HONEST TENSION STATION — a worded mark at rest (fix 1) ──────────
      // A station is always present: what a tension is, that none is open, and — since
      // paper_falqon RULED one — that the last was ruled and is readable.
      const station = await pg.$('.ck-shape-station');
      ok(!!station, 'the tension station is present at rest (the altitude is marked even when none pulls)');
      const stationText = (await pg.textContent('.ck-shape-station')).trim();
      ok(/a tension is a drift/i.test(stationText) && /none is open now/i.test(stationText),
        'the station states what a tension is and that none is open: ' + JSON.stringify(stationText.slice(0, 80)));
      ok(/the last one was ruled/i.test(stationText),
        'paper_falqon ruled one — the station says the last was ruled (real banked history, no mock)');
      ok(await pg.$eval('.ck-shape-station', (e) => e.classList.contains('is-readable')), 'the ruled station is readable (opens to history)');

      // ── (1b·read) OPEN THE RULED TENSION — read-only banked history ──────────────
      await pg.click('.ck-shape-station');
      // wait for the async /growth/reconciled fetch + render (a fixed sleep raced the fetch).
      await pg.waitForSelector('.ck-history', { timeout: 8000 }); await sleep(120);
      ok(!!(await pg.$('.ck-history')), 'clicking the station opens the read-only history view');
      const ruledTag = await pg.$('.ck-hist-verb.is-ruled .ck-ruled-tag');
      ok(!!ruledTag, 'the four verbs it offered are shown, REGOAL marked as the ruling he took');
      const ruledVerb = (await pg.textContent('.ck-hist-verb.is-ruled .hvn')).trim();
      ok(/REGOAL/.test(ruledVerb), 'the marked ruling is REGOAL (the verb he banked): ' + JSON.stringify(ruledVerb));
      const hisWords = (await pg.textContent('.ck-hist-ruling .hr-words')).trim();
      ok(hisWords.length > 40, 'his ruling commentary is banked, verbatim, in the history: ' + JSON.stringify(hisWords.slice(0, 60)));
      // the register law holds inside the read: no raw ids surface outside audit depth.
      const histAbove = await pg.evaluate(() => {
        const clone = document.querySelector('.ck-history').cloneNode(true);
        clone.querySelectorAll('.ck-audit').forEach((e) => e.remove());
        return clone.innerText;
      });
      ok(!/\b(GT|DQ|PV|RW)-[0-9a-f]{4,}/i.test(histAbove), 'the ruled-tension read keeps raw ids at audit depth');
      await pg.keyboard.press('Escape'); await sleep(400);   // Esc closes the materialised history
      ok((await pg.$('.ck-history')) === null, 'Esc closes the history back to the brief');
    }

    // ── (3) THE COLD ?gt= MISS — a link to a ruled/missing tension is not a silent no-op ──
    await pg.goto(base + '/conceptric?corpus=' + CORPUS + '&gt=GT-nosuchtension0000', { waitUntil: 'networkidle' });
    await pg.waitForSelector('[data-role="brief-prose"]', { timeout: 8000 }); await sleep(300);
    ok(!!(await pg.$('.ck-missnote')), 'a cold ?gt= link to a missing tension surfaces an inline note (never a silent no-op)');
    const missText = (await pg.textContent('.ck-missnote')).trim();
    ok(/already ruled or dismissed/i.test(missText), "the note is the server's composed message: " + JSON.stringify(missText.slice(0, 70)));
    ok(!!(await pg.$('.ck-missnote [data-role="read-ruled"]')), 'a ruled tension is banked — the note offers the read-only history read');
    await pg.click('.ck-missnote [data-role="read-ruled"]'); await sleep(300);
    ok(!!(await pg.$('.ck-history')), 'the miss note routes to the read-only ruled-tension history');

    // ── (4) THE GOAL'S INLINE TeX RENDERS — no raw $…$ leaks into the brief prose ──
    // subset-sum-itqde's composed goal carries inline math ($Z_\tau(s)=…$, $G(t)=…$);
    // the shell's one KaTeX fence renders it in place (the raw string stays at audit depth,
    // never on the rendered face). Drive that corpus and read the visible prose.
    await pg.goto(base + '/conceptric?corpus=subset-sum-itqde', { waitUntil: 'networkidle' });
    await pg.waitForSelector('.ck-brief-prose', { timeout: 8000 });
    await pg.waitForSelector('.ck-brief-prose .katex', { timeout: 8000 });   // the math painted
    const briefVis = (await pg.$eval('.ck-brief-prose', (e) => e.innerText)).trim();
    ok(!briefVis.includes('$'), 'no raw $-wrapped TeX visible in the rendered growth brief: ' + JSON.stringify(briefVis.slice(0, 70)));
    ok(await pg.$$eval('.ck-brief-prose .katex', (e) => e.length) > 0, 'the goal inline math rendered through the shell KaTeX fence');

    ok(errs.length === 0, 'zero uncaught page errors across the whole walk: ' + JSON.stringify(errs));
    console.log(`\nENGINE COCKPIT — ${passed} assertions green.`);
  } finally {
    await b.close();
    if (scanner) scanner.kill('SIGKILL');
    cleanupComment();
  }
})().catch((e) => { console.error('\nWALK FAILED:', e.message); if (scanner) scanner.kill('SIGKILL'); cleanupComment(); process.exit(1); });
