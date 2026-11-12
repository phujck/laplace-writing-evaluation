// ENGINE DESK — the desk joined to the ONE INSTRUMENT (W-DESK), driven against a REAL scanner.
//
// The walk proves the resting-state law (E), the geometry couplet (B), the entry contract
// (F), and B.5's no-lobby-tax as OUTCOMES, not DOM presence:
//   · brief base altitude: at rest NO class pane / cockpit exists in the DOM; the composed
//     what-needs-him-now prose is present, and the genuinely-his rows ride as glances;
//   · count chips: one per summonable class;
//   · materialise: opening a chip builds that class's rows (the DOM appears on open); the
//     counts law holds (the chip number equals the rows it opened, no +N door);
//   · pin the referent: opening a row REALLOCATES + rail + breadcrumb + a VISIBLE return door
//     NAMING its destination, and the FULL referent renders (a live GET /desk/referent against
//     the real executor — the read-only, non-destructive live-door proof);
//   · the write door is live: a non-destructive verb (adjudications.confirm) is a real button
//     wired to POST /desk/act (intercepted here so the walk banks NOTHING) — never decorative;
//   · close: exact scrollY restore + no return-door residue;
//   · NO LOBBY TAX (B.5): a ?item= deep-link lands PRE-PINNED on the target with the named
//     return door, WITHOUT a click — the brief is never a mandatory step on that path; a
//     ?class= deep-link lands materialised on that class;
//   · the register law: no raw GT-/DQ-/PV-/RW- ids above the fold.
//
//   run:  node tests/engine_desk.playwright.mjs
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

let scanner;
(async () => {
  const repoRoot = execSync(`${PY} -c "from laplace.web.scanner import _repo_root; print(_repo_root().resolve())"`).toString().trim();
  const port = await freePort();
  scanner = spawn(PY, ['-m', 'laplace.web.scanner', '--port', String(port)], { cwd: repoRoot, stdio: 'ignore' });
  await waitFor(`http://127.0.0.1:${port}/desk`);
  const base = `http://127.0.0.1:${port}`;
  const b = await chromium.launch({ executablePath: CHROME });
  try {
    const pg = await b.newPage({ viewport: { width: 1280, height: 420 } });
    const errs = []; pg.on('pageerror', (e) => errs.push(String(e)));
    // REFUSE-TO-BANK: intercept POST /desk/act so a verb drive PROVES the door is wired
    // without the walk ever mutating a real ledger (GET /desk/referent is left REAL — the
    // read-only live-door proof rides the true executor).
    let actPosts = [];
    await pg.route('**/desk/act', (route) => {
      const rq = route.request();
      if (rq.method() === 'POST') {
        let body = {}; try { body = JSON.parse(rq.postData() || '{}'); } catch (e) { body = {}; }
        actPosts.push(body);
        // echo a record id (+ the ruling posted) so the walk can prove the id echoes back in
        // place, and the composer wired his words — without ever banking a real ledger record.
        return route.fulfill({ status: 200, contentType: 'application/json',
          body: JSON.stringify({ ok: true, record: { id: 'FR-intercepted-' + actPosts.length, ruling: body.ruling || '' } }) });
      }
      return route.continue();
    });
    // the OPEN_STACK store path — for cleaning out the ONE real scratch-fork ruling the walk
    // banks (there is no un-bank reversal; a scratch fork id is the established cleanup).
    const openStackStore = execSync(`${PY} -c "from laplace.engine import open_stack_store; from laplace.web.scanner import _repo_root; print((_repo_root()/open_stack_store.STORE_REL).resolve())"`).toString().trim();
    const SCRATCH = 'SCRATCH-desk-walk-probe';

    await pg.goto(base + '/desk', { waitUntil: 'networkidle' });
    await pg.waitForSelector('[data-role="brief-prose"]', { timeout: 8000 });
    await sleep(250);

    // ── (1) THE BRIEF BASE ALTITUDE (E) ────────────────────────────────────────
    const prose = (await pg.textContent('[data-role="brief-prose"]')).trim();
    ok(prose.length > 40, 'the composed what-needs-you-now prose is present at rest: ' + JSON.stringify(prose.slice(0, 70)));
    const restDom = await pg.evaluate(() => ({
      matHead: document.querySelectorAll('.dkb-mat-head').length,
      cockpit: document.querySelectorAll('.dk-cockpit').length,
      reallocated: document.querySelector('#eng-root').classList.contains('reallocated'),
      hisGlances: document.querySelectorAll('.dkb-his .dkb-glance').length,
      chips: document.querySelectorAll('.dkb-count').length,
    }));
    ok(restDom.matHead === 0 && restDom.cockpit === 0 && !restDom.reallocated,
      'at rest NO class pane / cockpit / reallocation exists in the DOM: ' + JSON.stringify(restDom));
    ok(restDom.hisGlances >= 1, 'the genuinely-his rows ride the brief as glances (delta-and-ask, not a class wall): ' + restDom.hisGlances);
    ok(restDom.chips >= 1, 'one-line count chips are present, one per summonable class: ' + restDom.chips);
    // the brief is delta-and-ask: it names a decision and WHY, not a recital of class counts.
    ok(/—/.test(prose) && /(need|waiting|ruling|authoriz|confirm|quiet)/i.test(prose),
      'the brief reads as what-needs-him-and-why (delta-and-ask), never a count recital');

    // ── THE REGISTER LAW — no raw ids above the fold (run at rest) ───────────────
    const aboveFold = await pg.evaluate(() => {
      const clone = document.body.cloneNode(true);
      clone.querySelectorAll('.dk-audit').forEach((e) => e.remove());   // ids are allowed AT audit depth
      return clone.innerText;
    });
    ok(!/\b(GT|DQ|PV|RW)-[0-9a-f]{4,}/i.test(aboveFold), 'no raw GT-/DQ-/PV-/RW- ids above the fold (ids live at audit depth)');

    // ── ONE DEFINITION OF HIS (finding 4) — badge, brief prose, and the accent count the
    // SAME genuinely-his set. The who-him accent marks exactly the owed rows; NO count chip
    // wears the genuinely-his accent (a chip is a class total, grouped under a plain divider,
    // never "228 need you now" against a badge of 2).
    const hisLaw = await pg.evaluate(async () => {
      const d = await (await fetch('/desk/brief')).json();
      return {
        hisN: (d.his || []).length,
        whoHim: document.querySelectorAll('.dkb-his .dkb-glance.who-him').length,
        chipHisAccent: document.querySelectorAll('.dkb-count.him').length,
        standingDivider: !!document.querySelector('.dkb-counts-divider'),
      };
    });
    ok(hisLaw.whoHim === hisLaw.hisN,
      'the genuinely-his accent (who-him) marks EXACTLY the badge/brief his-count — one definition: ' + JSON.stringify(hisLaw));
    ok(hisLaw.chipHisAccent === 0,
      'NO count chip wears the genuinely-his accent (chips are class totals, not the owed set): ' + hisLaw.chipHisAccent);
    ok(hisLaw.standingDivider,
      'the him-owned chips sit under a labeled standing-queue divider, distinct from needs-you-now');

    // ── (2) MATERIALISE — opening a chip builds that class's rows; the counts law ──
    // SUPERSEDED 2026-07-22 (the churning-tree flake): the probe no longer hardcodes
    // stale-reads (whose count moves with the tree and reads zero/disabled some days) —
    // it picks the SMALLEST live class at runtime, which keeps the counts-law assertion
    // exact (no +N door on a small class) whatever the tree holds today.
    const probe = await pg.evaluate(() => {
      const chips = [...document.querySelectorAll('.dkb-count[data-materialize]')]
        .map((c) => ({ cls: c.dataset.materialize,
                       cn: Number((c.querySelector('.dkb-cn') || {}).textContent || 0),
                       disabled: c.getAttribute('aria-disabled') === 'true' }))
        .filter((c) => !c.disabled && c.cn > 0);
      chips.sort((a, b) => a.cn - b.cn);
      return chips[0] || null;
    });
    ok(probe !== null, 'a live (non-zero) class chip exists to probe the counts law: ' + JSON.stringify(probe));
    const chipCn = probe.cn;
    await pg.click(`.dkb-count[data-materialize="${probe.cls}"]`);
    await pg.waitForSelector('.dkb-mat-head', { timeout: 8000 }); await sleep(150);
    const matRows = await pg.$$eval('.dkb-mat .dkb-glances .dkb-glance', (e) => e.length);
    ok(matRows > 0, `opening the ${probe.cls} chip materialised its rows (DOM appears on open): ` + matRows);
    const hasMoreDoor = await pg.$('.dkb-mat .dkb-more');
    ok(hasMoreDoor ? matRows < chipCn
                   : chipCn === matRows,
      `the counts law holds on ${probe.cls}: chip ${chipCn} vs rows ${matRows}` +
      (hasMoreDoor ? ' with the +N door naming the rest' : ', no +N door'));
    // close the class pane back to the brief (the materialise ⇄ brief round-trip).
    await pg.click('.dkb-mat [data-role="mat-close"]'); await sleep(120);
    ok((await pg.$('.dkb-mat-head')) === null, 'closing the class pane returns to the brief (the pane leaves the DOM, no residue)');

    // ── (3) PIN THE REFERENT — reallocate + named return door + the WHOLE referent ──
    // open the first genuinely-his glance. Scroll to a nonzero position and click IN-PAGE
    // (playwright's own click re-scrolls the target into view, which would move the scrollY
    // the pin captures) — so the restore-on-close proof rides a real, unmoved position.
    await pg.evaluate(() => window.scrollTo(0, 60)); await sleep(60);
    const scrollAtPin = await pg.evaluate(() => Math.round(window.scrollY));
    ok(scrollAtPin > 0, 'the brief is scrolled to a nonzero position before the pin (a real restore proof): ' + scrollAtPin);
    await pg.$eval('.dkb-his .dkb-glance', (e) => e.click()); await sleep(400);
    ok(await pg.$eval('#eng-root', (e) => e.classList.contains('reallocated')), 'opening a row REALLOCATED the surface (the referent claims the centre)');
    ok(await pg.$('.eng-rail').then((x) => !!x), 'the context rail is present');
    ok(await pg.$('.eng-breadcrumb').then((x) => !!x), 'the breadcrumb is present');
    const door = await pg.$('[data-role="return-door"]');
    ok(!!door, 'a return door is present in the reallocated state');
    const doorLabel = (await pg.textContent('[data-role="return-door"] .rd-label')).trim();
    ok(/back to the brief/i.test(doorLabel), 'the return door NAMES its destination: ' + JSON.stringify(doorLabel));
    const doorVisible = await pg.$eval('[data-role="return-door"]', (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
    ok(doorVisible, 'the return door is VISIBLE (a return door that is not visible does not exist)');
    // the four cockpit zones render, and the FULL referent loads (a live GET against the real
    // executor — the read-only, non-destructive live-door proof named in the wave order).
    for (const z of ['zone-context', 'zone-consequences', 'zone-tools', 'zone-deeplinks'])
      ok(await pg.$('.eng-focus .dk-cockpit .' + z) !== null, `the cockpit renders .${z} in the reallocated focus`);
    await pg.waitForFunction(() => {
      const c = document.querySelector('.eng-focus .zone-context .dk-ctx-body');
      return c && !/loading the full referent/i.test(c.innerText) && c.innerText.trim().length > 0;
    }, { timeout: 8000 });
    ok(true, 'the WHOLE referent rendered inline (GET /desk/referent fired against its real executor — the live read-only door)');

    // ── (4) CLOSE — exact scrollY restore + no return-door residue ───────────────
    await pg.keyboard.press('Escape'); await sleep(300);
    ok(!(await pg.$eval('#eng-root', (e) => e.classList.contains('reallocated'))), 'Esc closed the focus back to the brief');
    const scrollAfter = await pg.evaluate(() => Math.round(window.scrollY));
    ok(Math.abs(scrollAfter - scrollAtPin) <= 1, `exact scrollY restored on close (${scrollAfter} ≈ ${scrollAtPin})`);
    ok((await pg.$('[data-role="return-door"]')) === null, 'the return door is ABSENT from the resting DOM (no hidden residue)');

    // ── (5) THE WRITE DOOR IS LIVE — a non-destructive verb wired to POST /desk/act ──
    // materialise adjudications, open a row, drive its confirm (non-destructive; the POST is
    // intercepted so nothing banks). A live door fires the real endpoint with the actor.
    await pg.click('.dkb-count[data-materialize="adjudications"]');
    await pg.waitForSelector('.dkb-mat .dkb-glances .dkb-glance', { timeout: 8000 }); await sleep(150);
    await pg.click('.dkb-mat .dkb-glances .dkb-glance'); await sleep(400);
    const confirmBtn = await pg.$('.eng-focus .dk-cockpit .dk-act[data-verb="confirm"]');
    ok(!!confirmBtn && await confirmBtn.evaluate((e) => e.tagName === 'BUTTON'),
      'the adjudications cockpit carries a LIVE confirm button (a real door, not a decorative deferred span)');
    actPosts = [];
    await confirmBtn.click();
    await pg.waitForSelector('.eng-focus .dk-cockpit .dk-result.ok', { timeout: 4000 });
    ok(actPosts.length === 1, 'clicking confirm fired exactly ONE POST /desk/act (the wired write door)');
    ok(actPosts[0].by === 'author' && actPosts[0].class === 'adjudications' && actPosts[0].verb === 'confirm',
      'the door carried the actor + class + verb into the real endpoint: ' + JSON.stringify({ by: actPosts[0].by, class: actPosts[0].class, verb: actPosts[0].verb }));
    // ARM-TO-FIRE: a DESTRUCTIVE verb (dismiss) ARMS on the first click and does NOT fire —
    // one click never banks a suppression (the door is the real guard; this is the affordance).
    const dismiss = await pg.$('.eng-focus .dk-cockpit .dk-act.destructive[data-verb="dismiss"]');
    ok(!!dismiss, 'the cockpit carries the destructive dismiss verb (arm-to-fire)');
    await dismiss.click(); await sleep(120);
    ok(actPosts.length === 1, 'one click on a destructive verb did NOT fire (still exactly the one confirm POST) — it only armed');
    ok(/click again/i.test(await dismiss.evaluate((e) => e.textContent)) && await dismiss.evaluate((e) => e.classList.contains('armed')),
      'the destructive verb ARMED with a "… — click again" face (the second click would fire)');
    await pg.keyboard.press('Escape'); await sleep(200);

    // ── (6) NO LOBBY TAX (B.5) — a ?item= deep-link PRE-PINS on load ─────────────
    const hisTarget = await pg.evaluate(async () => {
      const d = await (await fetch('/desk/brief')).json();
      const h = (d.his || [])[0]; return h ? (h.class + '::' + h.id) : null;
    });
    ok(!!hisTarget, 'resolved a genuinely-his row to deep-link into: ' + JSON.stringify(hisTarget));
    await pg.goto(base + '/desk?item=' + encodeURIComponent(hisTarget), { waitUntil: 'networkidle' });
    await pg.waitForSelector('#eng-root.reallocated', { timeout: 8000 }); await sleep(200);
    ok(await pg.$eval('#eng-root', (e) => e.classList.contains('reallocated')),
      'a ?item= deep-link lands PRE-PINNED on the target (reallocated at first paint — no click, no lobby tax)');
    const dlDoor = (await pg.textContent('[data-role="return-door"] .rd-label')).trim();
    ok(/back to the brief/i.test(dlDoor), 'the deep-linked arrival carries the named return door back to the brief');

    // ── (7) a ?class= deep-link lands MATERIALISED on that class ─────────────────
    // (the same runtime-probed class as (2) — never a class the tree may hold at zero)
    await pg.goto(base + '/desk?class=' + encodeURIComponent(probe.cls), { waitUntil: 'networkidle' });
    await pg.waitForSelector('.dkb-mat-head', { timeout: 8000 }); await sleep(150);
    const dlMat = await pg.$$eval('.dkb-mat .dkb-glances .dkb-glance', (e) => e.length);
    ok(dlMat > 0, 'a ?class= deep-link lands with that class materialised on load (no lobby tax to reach it): ' + dlMat);

    // ── (8) EVERY CLASS WITH ROWS CARRIES REAL, COMPOSED REFERENT CONTEXT (findings 1 + 2) ──
    // the blocking defect: the lifts (and frictions / clusters / holdout) cockpit rendered
    // literally "{}" + "no richer referent wired for this class yet". Open the first row of
    // EVERY non-zero class and assert its CONTEXT zone renders composed content — never the
    // empty-referent placeholder. lifts is asserted by name (the blocking finding).
    const classesToProbe = await pg.evaluate(async () => {
      const d = await (await fetch('/desk/brief')).json();
      return (d.classes || []).filter((c) => c.count > 0).map((c) => c.class);
    });
    ok(classesToProbe.includes('lifts'), 'the lifts class has rows to prove the blocking fix against: ' + JSON.stringify(classesToProbe));
    for (const cls of classesToProbe) {
      await pg.goto(base + '/desk?class=' + encodeURIComponent(cls), { waitUntil: 'networkidle' });
      await pg.waitForSelector('.dkb-mat .dkb-glances .dkb-glance', { timeout: 8000 });
      await pg.click('.dkb-mat .dkb-glances .dkb-glance'); await sleep(300);
      await pg.waitForFunction(() => {
        const c = document.querySelector('.eng-focus .zone-context .dk-ctx-body');
        return c && !/loading the full referent/i.test(c.innerText);
      }, { timeout: 8000 });
      const ctx = (await pg.textContent('.eng-focus .zone-context .dk-ctx-body')).trim();
      ok(ctx.length > 5 && ctx !== '{}' && !/no richer referent wired for this class yet/i.test(ctx),
        `the ${cls} cockpit renders REAL composed context (not the empty-referent placeholder): ` + JSON.stringify(ctx.slice(0, 60)));
      await pg.keyboard.press('Escape'); await sleep(120);
    }

    // ── (9) READ-ONLY (ENGINE) ROWS CARRY NO WRITE AFFORDANCE (finding 3) ────────────────
    // a machine-owed row is read-only exhaust for him: its cockpit shows NO live write button,
    // and the rail wears the standing machine-waiting wording — never "read-only exhaust" under
    // a live fire face. Pick a live engine-owned class at runtime (never a hardcoded one).
    const engineCls = await pg.evaluate(async () => {
      const d = await (await fetch('/desk/brief')).json();
      const c = (d.classes || []).find((x) => x.owner !== 'him' && x.count > 0);
      return c ? c.class : null;
    });
    ok(engineCls !== null, 'a live engine-owned class exists to prove the read-only law against: ' + engineCls);
    await pg.goto(base + '/desk?class=' + encodeURIComponent(engineCls), { waitUntil: 'networkidle' });
    await pg.waitForSelector('.dkb-mat .dkb-glances .dkb-glance', { timeout: 8000 });
    await pg.click('.dkb-mat .dkb-glances .dkb-glance'); await sleep(350);
    const engView = await pg.evaluate(() => ({
      writeButtons: document.querySelectorAll('.eng-focus .dk-cockpit .zone-tools button.dk-act').length,
      machineText: document.querySelectorAll('.eng-focus .dk-cockpit .zone-tools .dk-act-machine').length,
      rail: (document.querySelector('.eng-rail') || {}).innerText || '',
    }));
    ok(engView.writeButtons === 0,
      `a read-only (engine) row carries NO live write button in its cockpit (${engineCls}): ` + engView.writeButtons);
    ok(engView.machineText > 0,
      'the engine row names its verb as machine-waiting quiet text (appearance predicts behaviour): ' + engView.machineText);
    ok(/machine session/i.test(engView.rail) && !/read-only exhaust/i.test(engView.rail),
      'the engine rail wears the standing machine-waiting wording, not "read-only exhaust": ' + JSON.stringify(engView.rail.slice(0, 90)));
    await pg.keyboard.press('Escape'); await sleep(150);

    // ── (10) THE RULING COMPOSER (PV the-ruling-needs-a-composer) — an authoring verb offers
    // a FIELD for his words, never a bare confirm; the door refuses a wordless ruling. ────────
    await pg.goto(base + '/desk?class=forks', { waitUntil: 'networkidle' });
    await pg.waitForSelector('.dkb-mat .dkb-glances .dkb-glance', { timeout: 8000 });
    await pg.click('.dkb-mat .dkb-glances .dkb-glance'); await sleep(400);
    // bank-ruling renders as a COMPOSER trigger, not a bare fire button
    const bankTrigger = await pg.$('.eng-focus .dk-cockpit .zone-tools .dk-act-authoring[data-verb="bank-ruling"]');
    ok(!!bankTrigger, 'the forks cockpit renders bank-ruling as a COMPOSER trigger (an authoring field), not a bare confirm');
    const bareBank = await pg.$('.eng-focus .dk-cockpit .zone-tools button.dk-act[data-verb="bank-ruling"]:not(.dk-act-authoring)');
    ok(!bareBank, 'there is NO bare bank-ruling button that could fire an empty ruling');
    actPosts = [];
    await bankTrigger.click(); await sleep(150);
    ok(await pg.$('.eng-focus .dk-ruling-composer') !== null, 'clicking bank-ruling opens the ruling composer (the question + a field for his words)');
    const promptTxt = (await pg.textContent('.eng-focus .dk-ruling-prompt')).trim();
    ok(promptTxt.length > 5, 'the composer restates the fork question as the prompt: ' + JSON.stringify(promptTxt.slice(0, 60)));
    ok(await pg.$('.eng-focus .dk-ruling-text') !== null, 'the composer carries a required ruling field');
    // EMPTY refusal (client): firing with no text does NOT POST — no bare button banks an empty record
    await pg.click('.eng-focus .dk-ruling-fire'); await sleep(150);
    ok(actPosts.length === 0, 'firing the composer with an EMPTY ruling does not POST (no empty authored record banks)');
    ok(await pg.$eval('.eng-focus .dk-ruling-text', (e) => e.classList.contains('bad')), 'the empty ruling field is marked bad on the refused fire');
    // fill his words and fire → the door carries his ruling + actor, and the id echoes back
    const probeText = 'PROBE the register lands and plain reads true';
    await pg.fill('.eng-focus .dk-ruling-text', probeText);
    await pg.click('.eng-focus .dk-ruling-fire'); await sleep(300);
    ok(actPosts.length === 1 && (actPosts[0].ruling || '').includes('PROBE the register lands'),
      'the composed ruling fires through the door carrying his words: ' + JSON.stringify(actPosts[0].ruling));
    ok(actPosts[0].by === 'author' && actPosts[0].class === 'forks' && actPosts[0].verb === 'bank-ruling',
      'the ruling door carried actor + class + verb: ' + JSON.stringify({ by: actPosts[0].by, class: actPosts[0].class, verb: actPosts[0].verb }));
    const echo = (await pg.textContent('.eng-focus .dk-cockpit .dk-result')).trim();
    ok(/FR-|banked/i.test(echo), 'the banked ruling id echoes back in place as confirmation: ' + JSON.stringify(echo.slice(0, 40)));
    await pg.keyboard.press('Escape'); await sleep(150);

    // the SWEEP (same class of verbs): proxy reject composes his objection too, never a bare arm
    await pg.goto(base + '/desk?class=proxy-drafts', { waitUntil: 'networkidle' });
    await pg.waitForSelector('.dkb-mat .dkb-glances .dkb-glance', { timeout: 8000 });
    await pg.click('.dkb-mat .dkb-glances .dkb-glance'); await sleep(400);
    ok(await pg.$('.eng-focus .dk-cockpit .zone-tools .dk-act-authoring[data-verb="reject"]') !== null,
      'proxy reject renders as a composer (his objection carries a field), not a bare arm-to-fire');
    await pg.keyboard.press('Escape'); await sleep(150);

    // ── (11) THE DOOR REFUSES A WORDLESS RULING (server guard, unintercepted) ────────────────
    await pg.unroute('**/desk/act');
    const emptyDoor = await pg.evaluate(async (b) => {
      const r = await fetch(b + '/desk/act', { method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ class: 'forks', verb: 'bank-ruling', by: 'desk-walk-probe', id: 'SCRATCH-desk-walk-probe', ruling: '' }) });
      return { status: r.status, body: await r.json() };
    }, base);
    ok(emptyDoor.status === 422 && emptyDoor.body.needs === 'ruling',
      'the door 422s a wordless fork-ruling (empty ruling refused, the actor-guard idiom): ' + JSON.stringify({ status: emptyDoor.status, needs: emptyDoor.body.needs }));
    // fire for real on a SCRATCH fork with a probe actor — the row lands with his text + echoes id
    const banked = await pg.evaluate(async (b) => {
      const r = await fetch(b + '/desk/act', { method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ class: 'forks', verb: 'bank-ruling', by: 'desk-walk-probe', id: 'SCRATCH-desk-walk-probe',
          ruling: 'PROBE the register lands and plain reads true', choice: 'yes — it does', commentary: 'probe commentary' }) });
      return { status: r.status, body: await r.json() };
    }, base);
    ok(banked.status === 200 && banked.body.record && banked.body.record.ruling.includes('PROBE the register lands'),
      'the door banks the ruling WITH his words and echoes the record: ' + JSON.stringify(banked.body.record && { id: banked.body.record.id, ruling: banked.body.record.ruling }));
    ok(banked.body.record.by === 'desk-walk-probe' && /^FR-/.test(banked.body.record.id || ''),
      'the banked ruling carries the probe actor and a real record id that echoes back: ' + JSON.stringify({ by: banked.body.record.by, id: banked.body.record.id }));
    // CLEAN OUT the scratch ruling (no un-bank reversal exists — remove the scratch line the walk banked)
    try {
      const fs = require('fs');
      const kept = fs.readFileSync(openStackStore, 'utf8').split('\n').filter((l) => !l.includes(SCRATCH));
      fs.writeFileSync(openStackStore, kept.join('\n'));
    } catch (e) { console.log('  (scratch cleanup note: ' + e.message + ')'); }

    // ── THE WIDE-VIEWPORT BRIEF (finding 1) at 1440 — the resting desk brief COLUMN is centred
    // (margin-inline:auto over a reading measure) instead of left-anchored in a dead right band,
    // and the surface header shares that same centred column (no header sitting left of the body).
    await pg.setViewportSize({ width: 1440, height: 900 });
    await pg.goto(base + '/desk', { waitUntil: 'domcontentloaded' });
    await pg.waitForSelector('.dkb-count, .dkb-glance', { timeout: 12000 }).catch(() => {}); await sleep(400);
    const dBrief = await pg.$eval('.eng-brief', (e) => {
      const r = e.getBoundingClientRect();
      return { left: Math.round(r.left), right: Math.round(window.innerWidth - r.right), width: Math.round(r.width) };
    });
    ok(Math.abs(dBrief.left - dBrief.right) <= 6,
      `the resting desk brief COLUMN is centred at 1440 (left ${dBrief.left}px ≈ right ${dBrief.right}px)`);
    ok(dBrief.width <= 1010, `the desk brief column is bounded to a reading measure at 1440 (${dBrief.width}px ≤ ~1000)`);
    const dHdr = await pg.$eval('.dk-ctx', (e) => Math.round(e.getBoundingClientRect().left));
    ok(Math.abs(dHdr - dBrief.left) <= 2,
      `the desk surface header shares the centred brief column (header left ${dHdr}px ≈ brief left ${dBrief.left}px)`);
    const dhs = await pg.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    ok(dhs <= 1, 'no horizontal body scroll on the desk at 1440 (' + dhs + 'px)');

    ok(errs.length === 0, 'zero uncaught page errors across the whole walk: ' + JSON.stringify(errs));
    console.log(`\nENGINE DESK — ${passed} assertions green.`);
  } finally {
    await b.close();
    if (scanner) scanner.kill('SIGKILL');
  }
})().catch((e) => { console.error('\nWALK FAILED:', e.message); if (scanner) scanner.kill('SIGKILL'); process.exit(1); });
