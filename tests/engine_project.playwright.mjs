// ENGINE PROJECT — the /project surface joins the one instrument (W-PROJECT), driven against
// a REAL scanner in a real Chromium. His ruling (2026-07-22): "I need the full pipeline
// information so I can understand exactly what is happening and see how interventions change
// it." The walk proves the resting-state law (E), the geometry couplet (B), the entry
// contract (F), and the no-lobby-tax hot arrival (B.5) as OUTCOMES:
//   · brief base altitude: at rest the composed brief prose (the pipeline readable as
//     sentences) + count chips are present and NO board DOM exists (no cockpit rung, no organ
//     card) — the board is summonable, not resident;
//   · the brief text is delta-and-ask shaped: where the pipeline stands, what ran, the next
//     action, at most one decision — and the ONE consequential move carries its cost VISIBLE;
//   · materialise = reallocate: opening the organ-panels count REALLOCATES the surface to the
//     board (the summonable inventory) with a VISIBLE return door NAMING the project brief
//     ("back to the project brief — where you were"); the cockpit strip's rungs equal
//     release.STATES (the stages chip), every chain organ a card (the organs chip);
//   · expand in place: an organ card opens IN PLACE within the board — its dials + dry-run
//     ("what would fire — before any arm") visible before any fire (the what-will-this-do law);
//   · restore exact: Esc → the brief, exact scrollY, the return door + board absent from rest;
//   · NO LOBBY TAX: a ?organ= hot arrival lands PRE-FOCUSED (reallocated) with that organ
//     expanded, the brief never a mandatory step; the organ carries its dials + verbs' cost;
//   · counts law: the stages/organs chips equal the DOM rows they filter to;
//   · register 0: no raw GT-/DQ-/PV-/RW- ids above the fold; body never scrolls sideways at
//     1280/1536 (this pane historically ran 1.71-2.9x — the brief altitude kills the wall).
//
//   run:  node tests/engine_project.playwright.mjs
//   Exits 0 all-green, non-zero on the first failed assertion.
import { createRequire } from 'module';
import { spawn, execSync } from 'child_process';
import net from 'net';
import http from 'http';

const require = createRequire(import.meta.url);
const { chromium } = require(execSync('npm root -g').toString().trim() + '/playwright');
const CHROME = execSync('ls /opt/pw-browsers/chromium-*/chrome-linux/chrome').toString().trim().split('\n')[0];
const PY = 'python3';
const PROJECT = 'subset-sum-itqde';   // real registry project; release state UNDER_CONVERGENCE

let passed = 0;
function ok(cond, msg) { if (!cond) throw new Error('ASSERT FAILED: ' + msg); passed++; console.log('  ok -', msg); }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function freePort() { return new Promise((res) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); }); }
function waitFor(url, tries = 80) {
  return new Promise((res, rej) => { const tick = (n) => { const req = http.get(url, (r) => { r.resume(); res(true); });
    req.on('error', () => n <= 0 ? rej(new Error('server never came up')) : setTimeout(() => tick(n - 1), 250)); }; tick(tries); });
}
function get(port, path) { return new Promise((res, rej) => {
  http.get(`http://127.0.0.1:${port}${path}`, (r) => { let b = ''; r.on('data', (d) => b += d); r.on('end', () => res({ status: r.statusCode, body: b })); }).on('error', rej); }); }
function post(port, path, obj) { return new Promise((res, rej) => {
  const data = Buffer.from(JSON.stringify(obj || {}));
  const req = http.request(`http://127.0.0.1:${port}${path}`, { method: 'POST',
    headers: { 'content-type': 'application/json', 'content-length': data.length } },
    (r) => { let b = ''; r.on('data', (d) => b += d); r.on('end', () => res({ status: r.statusCode, body: b })); });
  req.on('error', rej); req.write(data); req.end(); }); }
const FALQON = 'paper_falqon';   // real registry project; release NEVER_RUN but GEN-3, r2 minted

let scanner;
(async () => {
  const repoRoot = execSync(`${PY} -c "from laplace.web.scanner import _repo_root; print(_repo_root().resolve())"`).toString().trim();
  const port = await freePort();
  scanner = spawn(PY, ['-m', 'laplace.web.scanner', '--port', String(port)], { cwd: repoRoot, stdio: 'ignore' });
  await waitFor(`http://127.0.0.1:${port}/`);
  const base = `http://127.0.0.1:${port}`;

  // the live truth the brief + board must reflect (the lock-step law: one read model)
  const brief = JSON.parse((await get(port, `/pipeline/brief?project=${PROJECT}`)).body);
  const chain = JSON.parse((await get(port, `/pipeline/chain?project=${PROJECT}`)).body);
  const organIds = (chain.organs || []).map((o) => o.id);
  ok(organIds.length > 0, 'the chain read model carries at least one organ (' + organIds.length + ')');
  ok(brief.counts.organs === organIds.length, 'the brief organs count equals the chain organs (' + organIds.length + ')');
  ok(brief.counts.stages === (chain.states || []).length, 'the brief stages count equals release.STATES (' + brief.counts.stages + ')');

  const b = await chromium.launch({ executablePath: CHROME });
  try {
    const pg = await b.newPage({ viewport: { width: 1280, height: 800 } });
    const errs = []; pg.on('pageerror', (e) => errs.push(String(e)));

    // ── (1) THE BRIEF BASE ALTITUDE (E) — cold arrival rests on the composed brief ──────
    await pg.goto(base + `/project?project=${PROJECT}`, { waitUntil: 'domcontentloaded' });
    await pg.waitForSelector('.pipe-count[data-count="organs"]', { timeout: 10000 });
    await sleep(200);
    const prose = (await pg.textContent('[data-role="brief-prose"]')).trim();
    ok(prose.length > 40, 'the composed brief prose is present at rest: ' + JSON.stringify(prose.slice(0, 70)));
    // the lock-step pin (DOM === the live server glance) — it composes plain words: any
    // next-act brief path lives at audit depth, never frozen into the sentence here.
    ok(prose === brief.brief.glance, 'the resting prose is the server-composed glance VERBATIM (the lock-step law)');
    // delta-and-ask shaped: where it stands + the next action (at most one decision)
    ok(/stands at|no release run/i.test(prose), 'the brief names where the pipeline STANDS (a state line, in plain words)');
    ok(/Next:/.test(prose), 'the brief names the NEXT action (the ask half of delta-and-ask)');
    // NO board DOM at rest — the board is summonable, not resident
    const restRungs = await pg.$$eval('.cockpit-rung', (e) => e.length);
    ok(restRungs === 0, 'at rest NO cockpit rung exists in the DOM — the board is summonable, not resident: ' + restRungs);
    const restCards = await pg.$$eval('.hy-card[data-organ]', (e) => e.length);
    ok(restCards === 0, 'at rest NO organ card exists in the DOM: ' + restCards);
    const chips = await pg.$$eval('.pipe-count[data-count]', (e) => e.map((x) => x.getAttribute('data-count')));
    for (const k of ['organs', 'stages', 'orders', 'rounds'])
      ok(chips.includes(k), 'the count chip ' + k + ' is present at rest');
    // the ONE consequential move + its cost VISIBLE before it fires (the what-will-this-do law)
    ok(await pg.$('.pipe-conseq') !== null, 'the ONE most consequential move glance is present at rest');
    if (brief.brief.consequential && brief.brief.consequential.cost_class)
      ok(await pg.$('.pipe-conseq .pc-cost') !== null, 'the consequential move carries its cost VISIBLE (what-will-this-do)');
    const hscroll1280 = await pg.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    ok(hscroll1280 <= 1, 'no horizontal body scroll at 1280 (' + hscroll1280 + 'px)');

    // ── (2) MATERIALISE = REALLOCATE — the board behind ONE open; the counts law ────────
    const scrollAtPin = await pg.evaluate(() => Math.round(window.scrollY));   // the pin captures this
    await pg.click('.pipe-count[data-count="organs"]');
    await pg.waitForSelector('#eng-root.reallocated', { timeout: 10000 });
    await pg.waitForSelector('#pipe-board .hy-card[data-organ]', { timeout: 10000 });
    await pg.waitForSelector('#pipe-cockpit .cockpit-strip .cockpit-rung', { timeout: 10000 });
    await sleep(200);
    ok(await pg.$eval('#eng-root', (e) => e.classList.contains('reallocated')), 'opening the board REALLOCATED the surface');
    ok(await pg.$('.eng-rail') !== null, 'the context rail is present (the brief summary)');
    const door = await pg.$('[data-role="return-door"]');
    ok(!!door, 'a return door is present in the reallocated board');
    const doorLabel = (await pg.textContent('[data-role="return-door"] .rd-label')).trim();
    ok(/back to the project brief — where you were/i.test(doorLabel), 'the return door NAMES the project brief: ' + JSON.stringify(doorLabel));
    ok(await pg.$eval('[data-role="return-door"]', (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; }),
      'the return door is VISIBLE');
    const rungN = await pg.$$eval('#pipe-cockpit .cockpit-strip .cockpit-rung', (e) => e.length);
    ok(rungN === brief.counts.stages, `the counts law holds: cockpit rungs (${rungN}) equal the stages chip (${brief.counts.stages})`);
    const cur = await pg.$$eval('#pipe-cockpit .cockpit-rung.is-current .cockpit-rung-t', (e) => e.map((x) => x.getAttribute('title')));
    ok(cur.some((t) => /UNDER_CONVERGENCE/.test(t)), 'the current rung is the live machine state (UNDER_CONVERGENCE): ' + JSON.stringify(cur));
    const boardOrganIds = await pg.$$eval('#pipe-board .hy-card[data-organ]', (e) => e.map((x) => x.getAttribute('data-organ')));
    for (const id of organIds) ok(boardOrganIds.includes(id), 'a card materialised for chain organ ' + id);
    const stageCards = boardOrganIds.filter((id) => organIds.includes(id)).length;
    ok(stageCards === brief.counts.organs, `the counts law holds: stage organ cards (${stageCards}) equal the organs chip (${brief.counts.organs})`);

    // ── (3) EXPAND IN PLACE — an organ card opens with its dials + dry-run before any fire ─
    await pg.click('#pipe-board .hy-card[data-organ="converge"] .hy-card-id'); await sleep(300);
    await pg.waitForSelector('#pipe-board .hy-card[data-organ="converge"].is-open .pipe-dial', { timeout: 8000 });
    ok(await pg.$('#pipe-board .hy-card[data-organ="converge"].is-open .pipe-dial') !== null,
      'the converge organ expands IN PLACE with its dials (the real panel, re-homed behind focus)');
    const dryTxt = await pg.$eval('#pipe-board .hy-card[data-organ="converge"] .pipe-dry', (e) => e.textContent).catch(() => '');
    ok(/what would fire/i.test(dryTxt), 'the expanded organ shows the DRY-RUN "what would fire" before any arm (what-will-this-do)');

    // ── (4) RESTORE EXACT — Esc → the brief, exact scrollY, the door + board absent ─────
    await pg.keyboard.press('Escape'); await sleep(300);
    ok(!(await pg.$eval('#eng-root', (e) => e.classList.contains('reallocated'))), 'Esc closed the board back to the brief');
    ok((await pg.$('[data-role="return-door"]')) === null, 'the return door is ABSENT from the resting DOM (no hidden residue)');
    ok((await pg.$('#pipe-board')) === null, 'the board is ABSENT from the resting DOM — summonable, not resident');
    const y1 = await pg.evaluate(() => Math.round(window.scrollY));
    ok(Math.abs(y1 - scrollAtPin) <= 2, `exact scrollY restored on close (${y1} ≈ ${scrollAtPin})`);

    // ── (5) NO LOBBY TAX — a ?organ= hot arrival lands PRE-FOCUSED (B.5) ─────────────────
    await pg.goto(base + `/project?project=${PROJECT}&organ=converge`, { waitUntil: 'domcontentloaded' });
    await pg.waitForSelector('#eng-root.reallocated', { timeout: 12000 });
    ok(await pg.$eval('#eng-root', (e) => e.classList.contains('reallocated')),
      'a hot ?organ= arrival lands PRE-FOCUSED (reallocated) — the brief is not a toll');
    ok(await pg.$('[data-role="return-door"]') !== null, 'the hot arrival carries the named return door to the brief');
    await pg.waitForSelector('#pipe-board .hy-card[data-organ="converge"].is-open .pipe-dial', { timeout: 8000 });
    ok(await pg.$('#pipe-board .hy-card[data-organ="converge"].is-open .pipe-dial') !== null,
      'the hot arrival lands with the named organ expanded in place, its dials visible');
    // the what-will-this-do law — a scoped verb keeps its cost class VISIBLE before firing
    const ctrlTxt = await pg.$eval('#pipe-board .hy-card[data-organ="converge"]', (e) => e.textContent).catch(() => '');
    ok(/local-safe|model-heavy|dry-run|what would fire/i.test(ctrlTxt),
      'a scoped verb keeps its writes/cost/PSU visible before firing (the what-will-this-do law intact)');

    // ── (6) REGISTER 0 + no sideways scroll at 1536 ─────────────────────────────────────
    await pg.goto(base + `/project?project=${PROJECT}`, { waitUntil: 'domcontentloaded' });
    await pg.waitForSelector('.pipe-count[data-count="organs"]', { timeout: 10000 }); await sleep(200);
    const aboveFold = await pg.evaluate(() => document.querySelector('#eng-root').innerText);
    ok(!/\b(GT|DQ|PV|RW)-[0-9a-f]{4,}/i.test(aboveFold), 'no raw GT-/DQ-/PV-/RW- ids above the fold (register 0)');
    await pg.setViewportSize({ width: 1536, height: 900 }); await sleep(200);
    const hscroll1536 = await pg.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    ok(hscroll1536 <= 1, 'no horizontal body scroll at 1536 (' + hscroll1536 + 'px)');
    // and the board materialised at 1536 stays bounded sideways too
    await pg.click('.pipe-count[data-count="organs"]');
    await pg.waitForSelector('#pipe-board .hy-card[data-organ]', { timeout: 10000 }); await sleep(200);
    const hscrollBoard = await pg.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    ok(hscrollBoard <= 1, 'the materialised board never scrolls the body sideways at 1536 (' + hscrollBoard + 'px)');

    // ── (7) THE HEREDITY LADDER + THE ACTOR LAW + THE PROMPTS DOOR (falqon) ──────────────
    // FINDING 1 — a release-machine-never-driven project with GEN-3 / r2 minted shows
    // EXACTLY ONE current rung and carries the explicit heredity banner (never ten 'ahead').
    const fchain = JSON.parse((await get(port, `/pipeline/chain?project=${FALQON}`)).body);
    const curStates = (fchain.states || []).filter((s) => s.status === 'current');
    ok(curStates.length === 1, 'FINDING 1 — falqon ladder shows EXACTLY ONE current rung (' + curStates.length + '): ' + JSON.stringify(curStates.map((s) => s.state)));
    ok(fchain.states.filter((s) => s.status === 'ahead').length < fchain.states.length,
      'FINDING 1 — the ladder is NOT ten identical ahead rungs (some passed/current now)');
    ok(/heredity/i.test(fchain.ladder_banner || ''), 'FINDING 1 — the ladder carries the heredity banner: ' + JSON.stringify(fchain.ladder_banner));

    // FINDING 8 — the dials door defaults NOWHERE: an unattributed /dials/op is a 422.
    const noActor = await post(port, '/dials/op', { profile: 'dials-v1.yaml', kind: 'set-leaf', path: 'mech.overfull_floor_pt', value: 8.0 });
    ok(noActor.status === 422, 'FINDING 8 — /dials/op with no actor is a 422 (his name never a default): ' + noActor.status);
    ok(/by \(explicit actor\) is required/i.test(noActor.body), 'FINDING 8 — the 422 names the actor law: ' + noActor.body.slice(0, 90));

    // Gap 6 — THE FRICTION DOOR defaults NOWHERE either: a /corpus/friction capture with no
    // explicit actor is a 422 (it used to default by:'eigen' — his name silently minted). The
    // door REFUSES before friction_add, so this probe banks nothing (a clean-tree assertion).
    const fricNoActor = await post(port, '/corpus/friction',
      { kind: 'fork', node: 'surface:test', owning_layer: 'interface', value: 'x' });
    ok(fricNoActor.status === 422, 'Gap 6 — /corpus/friction with no actor is a 422 (by:eigen is no longer a default): ' + fricNoActor.status);
    ok(/actor.*is required|by \(explicit actor\)/i.test(fricNoActor.body), 'Gap 6 — the 422 names the actor law: ' + fricNoActor.body.slice(0, 90));

    // FINDING 9b — the prompts door serves the REAL template text + override provenance.
    const prompts = JSON.parse((await get(port, `/pipeline/prompts?project=${FALQON}`)).body);
    ok(/prose realiser/i.test(((prompts.templates || {}).prose_stage_preamble || {}).text || ''),
      'FINDING 9b — the prompts door serves the REAL prose-stage template (schema.PROSE_STAGE_PREAMBLE)');
    ok((prompts.workers || []).some((w) => w.worker === 'prose' && w.folded_at_dispatch),
      'FINDING 9b — each worker names what is folded in at dispatch (no fabricated specimen)');
    ok((prompts.overrides.present || []).some((f) => f.text && f.text.length > 20),
      'FINDING 9b — a present override file serves its REAL text (provenance named)');

    // FINDING 2 — a ?organ=<sub-organ> hot arrival lands the sub-card OPEN (zero lobby tax),
    // and the heredity banner is visible in the reallocated cockpit.
    await pg.goto(base + `/project?project=${FALQON}&organ=evolution`, { waitUntil: 'domcontentloaded' });
    await pg.waitForSelector('#eng-root.reallocated', { timeout: 12000 });
    await pg.waitForSelector('#pipe-board .pipe-subcard[data-suborgan="evolution"].is-open', { timeout: 10000 });
    ok(await pg.$('#pipe-board .pipe-subcard[data-suborgan="evolution"].is-open') !== null,
      'FINDING 2 — ?organ=evolution (a sub-organ) lands the evolution sub-card OPEN in place');
    ok(await pg.$('[data-role="return-door"]') !== null, 'FINDING 2 — the sub-organ deep link carries the named return door');
    await pg.waitForSelector('.cockpit-ladbanner', { timeout: 8000 });
    const banTxt = (await pg.textContent('.cockpit-ladbanner')).trim();
    ok(/heredity/i.test(banTxt), 'FINDING 1 — the heredity banner renders in the cockpit: ' + JSON.stringify(banTxt.slice(0, 60)));
    const curRungs = await pg.$$eval('#pipe-cockpit .cockpit-rung.is-current', (e) => e.length);
    ok(curRungs === 1, 'FINDING 1 — exactly one current rung renders on the falqon board (' + curRungs + ')');

    // ── (8) THE SELECTION RULING — the gen-row rule door + the reasoning field (Gaps 3 + 5) ─
    // falqon's generations are all ruled, so we FIRE ON NOTHING: intercept the selection
    // organ read to present ONE unruled generation (draft promote), and intercept /selection/
    // rule so the arm flow drives without banking. This pins (5) the gen-row "rule →" door
    // lands on the pre-expanded selection sub-organ, and (3) his verdict-differs-from-draft
    // reasoning is REQUIRED, optional otherwise, and rides the POST as `reason`.
    const SEL_PAYLOAD = { present: true, corpus: FALQON,
      generations: [{ id: 'GEN-TEST-1', n: 9,
        draft_verdict: { verdict: 'promote', rule: 'draft-psi-v2', gates: {
          gate_self_consistency: { pass: true, reasons: [] },
          gate_cost: { pass: true, reasons: [] } } },
        debt_before: 3, debt_after: 0, debt_delta: -3,
        retention: { keys: 4, author_ruled: 0, machine_superseded: 0, by_fate: {} },
        r10: { clean: true, restart_intents: [] }, stamped_at: '2026-07-23' }],
      counts: { generations: 1, promote: 1, hold: 0, retire: 0 },
      rule: { version: 'draft-psi-v2', law: 'the honesty contract' },
      awaiting_ruling_n: 1, rulings: {} };
    await pg.route('**/pipeline/organ**', (route) => (/organ=selection/.test(route.request().url())
      ? route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ payload: SEL_PAYLOAD }) })
      : route.continue()));
    let armedCount = 0, armedBody = null;
    await pg.route('**/selection/rule', (route) => {
      const body = JSON.parse(route.request().postData() || '{}');
      if (body.armed === true) {
        armedCount += 1; armedBody = body;
        return route.fulfill({ status: 200, contentType: 'application/json',
          body: JSON.stringify({ ok: true, generation_id: body.generation_id, verdict: body.verdict,
            overrode_draft: true, draft_verdict: 'promote', rule_version: 'draft-psi-v2', readings_digest: {}, id: 'FB-TEST' }) });
      }
      return route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ ok: false, needs_arming: true, generation_id: body.generation_id, verdict: body.verdict,
          draft_verdict: 'promote', readings_digest: { debt: [3, 0], freeze_pass: true, r10_clean: true },
          what: 'banks your ' + body.verdict + ' ruling (record-only — mutates no artifact)' }) });
    });
    // land on the plain falqon board (no sub-organ deep link) so the selection sub-card is CLOSED
    await pg.goto(base + `/project?project=${FALQON}`, { waitUntil: 'domcontentloaded' });
    await pg.waitForSelector('.pipe-count[data-count="organs"]', { timeout: 10000 });

    // ── THE MACHINE DOOR FACE CARRIES NO FILE PATH — falqon's reproject next-act door reads
    // as the verb ("open the gen-4 reprojection"); the raw brief .md path drops to the door's
    // title (audit depth), and the face never repeats the card's glance (no duplication). ──
    ok(await pg.$('.pipe-conseq [data-role="conseq-door"]') !== null, 'the falqon consequential move renders its door');
    const cFace = (await pg.$eval('.pipe-conseq [data-role="conseq-door"]', (e) => e.textContent)).trim();
    const cTitle = await pg.$eval('.pipe-conseq [data-role="conseq-door"]', (e) => e.getAttribute('title') || '');
    const cGlance = (await pg.$eval('.pipe-conseq .pc-glance', (e) => e.textContent)).trim();
    ok(!/\.md\b/.test(cFace) && !/\(brief:/.test(cFace), 'the Machine door FACE carries no file path: ' + JSON.stringify(cFace));
    ok(/\.md\b/.test(cTitle), 'the raw brief path rides the door title at audit depth: ' + JSON.stringify(cTitle));
    ok(cFace.replace(/\s*↗\s*$/, '').trim() !== cGlance, 'the door face is not a verbatim repeat of the card glance: ' + JSON.stringify(cFace));
    // the NARRATIVE glance composes plain words too — the reproject next-act names that a
    // briefing note is banked; the raw .md path dropped to audit depth (the door title carries
    // it). SUPERSEDES the path-bearing sentence the glance once composed (2026-07-23): this
    // lock-step pin exists to catch drift, never to freeze that defect — it still holds
    // verbatim (DOM === the live server glance), now over the plain-words sentence.
    const fbrief = JSON.parse((await get(port, `/pipeline/brief?project=${FALQON}`)).body);
    const fprose = (await pg.textContent('[data-role="brief-prose"]')).trim();
    ok(fprose === fbrief.brief.glance, 'falqon: the resting prose is the server-composed glance VERBATIM (the lock-step law, over the plain-words sentence)');
    ok(!/\.md\b/.test(fprose) && !/\(brief:/.test(fprose), 'falqon: the narrative glance carries no file path (plain words; the path at audit depth): ' + JSON.stringify(fprose.slice(-90)));

    await pg.click('.pipe-count[data-count="organs"]');
    await pg.waitForSelector('#pipe-cockpit .cockpit-gen [data-role="gen-rule"]', { timeout: 12000 }); await sleep(150);
    ok(await pg.$('.pipe-subcard[data-suborgan="selection"].is-open') === null,
      'Gap 5 — the selection sub-card is CLOSED before the gen-row door is used (the hand was two expands deep)');
    ok(await pg.$('#pipe-cockpit .cockpit-gen [data-role="gen-rule"]') !== null,
      'Gap 5 — the gen row carries a "rule →" door (no longer just a verdict chip)');
    await pg.click('#pipe-cockpit .cockpit-gen [data-role="gen-rule"]');
    await pg.waitForSelector('.pipe-subcard[data-suborgan="selection"].is-open', { timeout: 8000 }); await sleep(150);
    ok(await pg.$('.pipe-subcard[data-suborgan="selection"].is-open') !== null,
      'Gap 5 — the gen-row rule door lands on the PRE-EXPANDED selection sub-organ (one click, not two)');

    // the unruled row shows the three rule doors; retire DIFFERS from the draft (promote)
    const selBtn = '.pipe-subcard[data-suborgan="selection"] .pipe-sel-vbtn[data-verd="retire"]';
    await pg.waitForSelector(selBtn, { timeout: 8000 });
    await pg.click(selBtn); await sleep(300);
    // the arm zone renders with the reasoning field, marked REQUIRED (his verdict ≠ the draft)
    await pg.waitForSelector('.pipe-subcard[data-suborgan="selection"] .pipe-sel-reason', { timeout: 8000 });
    const owed = await pg.$eval('.pipe-subcard[data-suborgan="selection"] .pipe-sel-reason', (e) => e.getAttribute('data-owed'));
    ok(owed === '1', 'Gap 3 — the reasoning field is REQUIRED when his verdict differs from the draft (data-owed=1)');
    const lbl = (await pg.textContent('.pipe-subcard[data-suborgan="selection"] .pipe-sel-reasonlbl')).toLowerCase();
    ok(/required/.test(lbl), 'Gap 3 — the field labels itself required on an override: ' + JSON.stringify(lbl.slice(0, 60)));
    // click BANK with an empty reason — blocked, nothing armed-posts, the err names the law
    await pg.click(selBtn); await sleep(250);
    ok(armedCount === 0, 'Gap 3 — an empty required reason BLOCKS the bank (no armed POST fired): ' + armedCount);
    ok(/reason is required/i.test((await pg.textContent('.pipe-subcard[data-suborgan="selection"] .pipe-sel-err')) || ''),
      'Gap 3 — the block names the law (a reason is required on an override)');
    // fill the reason, bank — the armed POST carries `reason` verbatim
    await pg.fill('.pipe-subcard[data-suborgan="selection"] .pipe-sel-reason', 'the reach gate is not truly met — retire, not promote');
    await pg.click(selBtn); await sleep(400);
    ok(armedCount === 1, 'Gap 3 — with a reason present the bank fires exactly one armed POST: ' + armedCount);
    ok(armedBody && armedBody.reason === 'the reach gate is not truly met — retire, not promote',
      'Gap 3 — the ruling POST carries his reasoning as `reason` (the backend banks make_selection_ruling(reason=…)): ' + JSON.stringify((armedBody || {}).reason));
    ok(armedBody && armedBody.armed === true && armedBody.verdict === 'retire',
      'Gap 3 — the armed body is his differing verdict (retire), armed to bank');
    await pg.unroute('**/pipeline/organ**'); await pg.unroute('**/selection/rule');

    ok(errs.length === 0, 'zero uncaught page errors across the whole walk: ' + JSON.stringify(errs));
    console.log(`\nENGINE PROJECT — ${passed} assertions green.`);
  } finally {
    await b.close();
    if (scanner) scanner.kill('SIGKILL');
  }
})().catch((e) => { console.error('\nWALK FAILED:', e.message); if (scanner) scanner.kill('SIGKILL'); process.exit(1); });
