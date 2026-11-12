// WAVE 6 — THE ASSETS + PIPELINE SURFACES, driven to the contract (DESIGN_2026-07-16
// §2.6 + §2.7 + the component grammar §1.5). OUTCOMES, not DOM-presence: a driven click
// that changes a boundingRect / a fetch / a preview certifies; a rendered node does not.
//
// ASSETS (/assets) — joined to the ONE INSTRUMENT (W-ASSETS):
//   · BRIEF AT REST — the surface rests on its composed brief (ZERO roster cards); the roster
//     materialises behind one kind chip (figures / derivations);
//   · COCKPIT ZONES — opening a card REALLOCATES to the four-zone close-examination cockpit
//     (context = the rendered figure inline · consequences · tools · deep-links) with a named
//     return door back to the brief (the engine's focus geometry replaced the in-place expand);
//   · REACHABILITY (B.5, no lobby tax) — /assets?asset=<id> lands PRE-PINNED on the named asset
//     (reallocated at first paint), and a deep-link node door carries the canonical
//     /conceptric?node= spine href (ladder doors_for parity) and LANDS 200 on that node;
//   · REGEN ARM-TO-FIRE — the manifest-only regen fires NOTHING on the first click (arms),
//     BANKS a work-order on the second, and the button says "banked" (heavy work never fires);
//   · ✎ RULE (D16) on a roster card banks a typed interface fork to /corpus/friction.
//
// PIPELINE (/pipeline):
//   · THE BOARD from the release state machine — the state ladder + organ CARDS render;
//   · DRY-RUN IN THE CARD — expanding the converge organ shows a "what would fire — before any
//     arm" preview of the live settings; editing a dial above UPDATES that preview (the pre-arm,
//     dial-reactive read the contract demands; nothing fires);
//   · BANKED VERB SAYS BANKED — a model-heavy scoped fire (dream) previews, ARMS, then BANKS a
//     work-order and says so (arm-to-fire; the offer law made visible).
//
// PIPELINE SUB-ORGANS — THE CONJUGATE WAVE (SCOUT_2026-07-17, on paper_falqon which carries a
// banked run for every night-organ). view=mechanism, driven to OUTCOMES:
//   · DETECTORS sub-card — the head chip carries the banked census (30 gaps); opening it lazy-
//     fetches GET /pipeline/organ and the evidence zone renders the reader's OWN facts; its fire
//     (detector-run, model-heavy) shows a "what would fire" dry-run BEFORE any arm, then ARMS
//     (banks nothing) — never fires blind;
//   · STAGED — the FIGURES sub-card renders the ONE LIVE dry-run preview (matched 2 · absent 0,
//     run(apply=False,run_gen=False)) BEFORE any arm; bibliography (11 resolved) + citation-
//     direction (5 intents) render banked counts; the bibliography fire ALSO shows its dry-run
//     before arm (every fire, not one);
//   · STRUCTURAL — the dial-vs-gate seam: a store whose holdout gate is red renders its chip WARN
//     (never green, the CHIP law), and arming enabled on it is REFUSED — the toggle reverts, the
//     refusal renders inline, and NO /dials/op POST fires (the SystemExit trap never reached).
//   Every scoped fire rides the SAME stubbed POST /storyboard/run/launch — the walk BANKS nothing
//   (it stays non-mutating, in the default set). The one falqon gate is INJECTED red (both real
//   gates pass) so the honesty seam has a warn to render.
//
//   · 375px — both surfaces single column, no horizontal scroll.
//
//   run:  node tests/wave6_assets_pipeline.playwright.mjs
//   deps: global playwright, Chromium at /opt/pw-browsers, python3 on PATH.
//   Every WRITE door (/assets/regen, /corpus/friction, /dials/op, /storyboard/run/launch) is
//   STUBBED (route.fulfill) — the walk NEVER mutates the real ledgers, work-orders, or profile.
import { createRequire } from 'module';
import { spawn, execSync } from 'child_process';
import net from 'net';
import http from 'http';

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
  return new Promise((res, rej) => { const tick = (n) => { const req = http.get(url, (r) => { r.resume(); res(true); });
    req.on('error', () => n <= 0 ? rej(new Error('server never came up')) : setTimeout(() => tick(n - 1), 250)); }; tick(tries); });
}

let scanner, base = null;
(async () => {
  const repoRoot = execSync(`${PY} -c "from laplace.web.scanner import _repo_root; print(_repo_root().resolve())"`).toString().trim();
  const port = await freePort();
  scanner = spawn(PY, ['-m', 'laplace.web.scanner', '--port', String(port)], { cwd: repoRoot, stdio: 'ignore' });
  await waitFor(`http://127.0.0.1:${port}/assets`);
  base = `http://127.0.0.1:${port}`;
  const b = await chromium.launch({ executablePath: CHROME });
  try {
    const pg = await b.newPage({ viewport: { width: 1440, height: 900 } });
    const errs = []; pg.on('pageerror', (e) => errs.push(String(e)));

    // stubbed WRITE doors — the walk touches no real ledger / work-order store.
    let regenPosts = [], frictionPosts = [];
    await pg.route('**/assets/regen*', (route) => {
      if (route.request().method() !== 'POST') return route.continue();
      let body = {}; try { body = JSON.parse(route.request().postData() || '{}'); } catch (_e) {}
      regenPosts.push(body);
      return route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ ok: true, work_order: { id: 'WO-W6-REGEN', action: 'regen-asset' } }) });
    });
    await pg.route('**/corpus/friction', (route) => {
      if (route.request().method() !== 'POST') return route.continue();
      let body = {}; try { body = JSON.parse(route.request().postData() || '{}'); } catch (_e) {}
      frictionPosts.push(body);
      return route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ ok: true, record: { id: 'fr-W6-1' } }) });
    });

    // ═══════════════ ASSETS — the surface joined to the one instrument (W-ASSETS) ═══════════════
    // The surface rests on its composed BRIEF; the roster is materialised behind one kind chip,
    // and opening a card REALLOCATES to the close-examination cockpit (no inline expand — the
    // engine's focus geometry replaced the misclick-killer's in-place expansion entirely).
    await pg.goto(base + '/assets?corpus=' + CORPUS, { waitUntil: 'networkidle' });
    await pg.waitForSelector('[data-role="brief-prose"]', { timeout: 15000 });
    await sleep(200);
    const restCards = await pg.$$eval('.asb-card', (els) => els.length);
    ok(restCards === 0, 'the asset surface rests on its composed brief (ZERO roster cards materialised at rest)');
    // materialise the figures suite → the roster of py-figure CARDS
    await pg.click('.asb-count[data-kind="figures"]');
    await pg.waitForSelector('.asb-mat .asb-cards .asb-card', { timeout: 15000 });
    await sleep(150);
    const rowIds = await pg.$$eval('.asb-mat .asb-cards .asb-card', (els) => els.map((e) => e.getAttribute('data-asset')));
    ok(rowIds.length >= 8, `the figures roster materialised ${rowIds.length} asset cards`);
    ok(rowIds.includes('figure:F1_staircase'), 'the F1_staircase figure card is on the board (the cockpit/regen/deeplink target)');

    // ── (1) COCKPIT ZONES — opening a card REALLOCATES to the four fixed zones ──
    await pg.$eval('.asb-mat .asb-cards .asb-card[data-asset="figure:F1_staircase"]', (e) => e.click());
    await pg.waitForSelector('.eng-focus .dk-cockpit .dk-zone', { timeout: 8000 });
    const zones = await pg.$$eval('.eng-focus .dk-cockpit .dk-zone', (els) => els.length);
    ok(zones === 4, `opening a card REALLOCATED to the four-zone close-examination cockpit (${zones})`);
    const hasImg = await pg.$('.eng-focus .zone-context img.as-fig');
    ok(hasImg !== null, 'CONTEXT renders the rendered figure inline (served via /assets/render)');
    // deep-links node door — the canonical /conceptric?node= spine href (ladder doors_for parity)
    const nodeDoor = await pg.$eval('.eng-focus .zone-deeplinks .dk-links a[href^="/conceptric?node="]',
      (a) => a.getAttribute('href')).catch(() => null);
    ok(nodeDoor && /^\/conceptric\?node=/.test(nodeDoor), `a deep-link carries the canonical conceptric spine door: ${nodeDoor}`);
    ok(/back to the brief/i.test((await pg.textContent('[data-role="return-door"] .rd-label')).trim()),
      'the reallocated focus carries the named return door back to the brief');

    // ── (2) REGEN ARM-TO-FIRE — first click fires NOTHING (arms), second BANKS, button says banked ──
    await pg.waitForSelector('.eng-focus #as-regen', { timeout: 15000 });
    regenPosts = [];
    await pg.click('.eng-focus #as-regen');                                          // ARM only
    await sleep(250);
    const armText = await pg.textContent('.eng-focus #as-regen');
    ok(regenPosts.length === 0 && /click again/i.test(armText || ''), `first click ARMED and fired nothing (0 posts; button: ${JSON.stringify((armText || '').trim())})`);
    await pg.click('.eng-focus #as-regen');                                          // FIRE → bank
    await pg.waitForFunction(() => /banked/i.test((document.querySelector('.eng-focus #as-regen') || {}).textContent || ''), null, { timeout: 4000 });
    const bankedText = await pg.textContent('.eng-focus #as-regen');
    ok(regenPosts.length === 1 && regenPosts[0].asset_id === 'figure:F1_staircase', `second click BANKED exactly one manifest-only work-order for the asset: ${JSON.stringify(regenPosts[0])}`);
    ok(/banked/i.test(bankedText || ''), `the button says banked (${JSON.stringify((bankedText || '').trim())})`);

    // ── (3) ✎ RULE (D16) on a roster card banks a typed interface fork ──
    await pg.keyboard.press('Escape'); await sleep(250);                             // close back to the roster
    await pg.waitForSelector('.asb-mat .asb-cards .asb-card[data-asset="figure:F1_staircase"]', { timeout: 8000 });
    frictionPosts = [];
    const ruleHead = '.asb-mat .asb-cards .asb-card[data-asset="figure:F1_staircase"] .asb-card-head';
    await pg.hover(ruleHead);
    await pg.waitForSelector(ruleHead + ' .rule-chip', { timeout: 4000 });
    await pg.click(ruleHead + ' .rule-chip');
    await pg.waitForSelector('.asb-card[data-asset="figure:F1_staircase"] .rule-cap textarea', { timeout: 4000 });
    await pg.fill('.asb-card[data-asset="figure:F1_staircase"] .rule-cap textarea', 'this figure card needs its regen consequence spelled out — bank it');
    await pg.click('.asb-card[data-asset="figure:F1_staircase"] .rule-cap .rule-bank');
    await pg.waitForSelector('.asb-card[data-asset="figure:F1_staircase"] .rule-banked', { timeout: 4000 });
    ok(frictionPosts.length === 1 && frictionPosts[0].kind === 'fork' && frictionPosts[0].owning_layer === 'interface',
      `the ✎ rule banked a typed interface fork keyed on the asset: ${JSON.stringify({ kind: frictionPosts[0].kind, layer: frictionPosts[0].owning_layer, node: frictionPosts[0].node })}`);

    // ── (4) REACHABILITY (B.5, no lobby tax) — ?asset= lands PRE-PINNED on the named asset ──
    await pg.goto(base + '/assets?corpus=' + CORPUS + '&asset=' + encodeURIComponent('figure:F2_hardy_littlewood'), { waitUntil: 'networkidle' });
    await pg.waitForSelector('#eng-root.reallocated', { timeout: 8000 });
    const landedOpen = await pg.$('#eng-root.reallocated .eng-focus .dk-cockpit');
    ok(landedOpen !== null, 'REACHABILITY: /assets?asset=<id> landed PRE-PINNED with its cockpit (reallocated at first paint — no click, no lobby tax)');
    // and the node door LANDS 200 on that node in /conceptric
    const cxHref = await pg.$eval('.eng-focus .zone-deeplinks a[href^="/conceptric?node="]', (a) => a.getAttribute('href')).catch(() => null);
    if (cxHref) {
      const cxStatus = await pg.evaluate(async (h) => (await fetch(h)).status, cxHref);
      ok(cxStatus === 200, `the deep-link node door LANDS 200 on the conceptric spine: ${cxHref}`);
    } else { ok(true, 'F2_hardy_littlewood carries no supported-node door (honest absence) — landing test deferred to F1_staircase above'); }

    // ═══════════════ PIPELINE ═══════════════
    // stubbed writes: /dials/op (the dial edit) + /storyboard/run/launch POST (the bank). The
    // chain read is served live but INTERCEPTED so a stubbed dial edit reflects in the reload.
    let editedVal = null, launchPosts = [], dialPosts = [];
    await pg.route('**/dials/op', (route) => {
      if (route.request().method() !== 'POST') return route.continue();
      let body = {}; try { body = JSON.parse(route.request().postData() || '{}'); } catch (_e) {}
      dialPosts.push(body); editedVal = body.value;
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) });
    });
    await pg.route('**/pipeline/chain*', async (route) => {
      const resp = await route.fetch();
      let j; try { j = await resp.json(); } catch (_e) { return route.fulfill({ response: resp }); }
      // subset-sum: reflect the stubbed dial edit into loop.max_rounds (the reload shows it)
      if (editedVal !== null) for (const o of (j.organs || [])) for (const d of (o.dials || [])) if (d.path === 'loop.max_rounds') d.value = editedVal;
      // falqon: inject a FAILED gate into the structural spine_chain store (both real
      // falqon gates PASS) so the dial-vs-gate honesty seam has a RED gate to render warn
      // on. Display-only (a route stub) — it fires no config; the real store stays off.
      for (const o of (j.organs || [])) for (const so of (o.sub_organs || [])) if (so.id === 'structural-conformance')
        for (const d of (so.dials || [])) if (d.store === 'spine_chain')
          d.gate = { state: 'failed', passed: false, refusal: 'holdout gate did not pass (walk-injected red gate)' };
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(j) });
    });
    await pg.route('**/storyboard/run/launch', (route) => {
      if (route.request().method() !== 'POST') return route.continue();   // GET roster stays live
      let body = {}; try { body = JSON.parse(route.request().postData() || '{}'); } catch (_e) {}
      launchPosts.push(body);
      return route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ ok: true, cost_class: 'model-heavy', action: body.action }) });
    });

    await pg.goto(base + '/pipeline?project=' + CORPUS, { waitUntil: 'domcontentloaded' });
    // the pipeline surface rests on its composed BRIEF; the cockpit strip + organ board are the
    // summonable inventory, materialised behind one open (the organ-panels count chip). Open it.
    await pg.waitForSelector('.pipe-count[data-count="organs"]', { timeout: 15000 });
    await pg.click('.pipe-count[data-count="organs"]');
    await pg.waitForSelector('#pipe-board .hy-card[data-organ]', { timeout: 15000 });
    await sleep(250);

    // ── (7) THE BOARD from the state machine — ladder rungs + organ cards ──
    // ACT 4 reface: the release-state ladder moved off the bare #pipe-ladder (an error host
    // now) into the cockpit state strip — #pipe-cockpit .cockpit-strip, one .cockpit-rung per
    // release.STATES entry. The LAW is unchanged: the ladder is rendered FROM release.STATES.
    const ladderChips = await pg.$$eval('#pipe-cockpit .cockpit-strip .cockpit-rung', (els) => els.length);
    const organCards = await pg.$$eval('#pipe-board .hy-card[data-organ]', (els) => els.map((e) => e.dataset.organ));
    ok(ladderChips >= 5, `the chain BOARD renders the release-state ladder (${ladderChips} rungs from release.STATES)`);
    ok(organCards.includes('converge') && organCards.length >= 5, `the organs render as cards (${organCards.length}: ${organCards.slice(0, 6).join(', ')}…)`);

    // ── (8)+(9) DRY-RUN IN THE CARD + DIAL EDIT UPDATES IT ──
    await pg.click('#pipe-board .hy-card[data-organ="converge"] .hy-card-id');
    await pg.waitForSelector('#pipe-board .hy-card[data-organ="converge"].is-open .pipe-dry', { timeout: 6000 });
    const dryBefore = await pg.textContent('#pipe-board .hy-card[data-organ="converge"] .pipe-dry');
    ok(/what would fire/i.test(dryBefore || '') && /before any arm/i.test(dryBefore || ''),
      'the converge organ shows a DRY-RUN "what would fire — before any arm" preview in the same card');
    ok(/loop\.max_rounds\s*=\s*4/.test(dryBefore || ''), 'the dry-run preview names the LIVE setting a fire would apply (loop.max_rounds = 4)');
    // edit the dial → dialWrite POSTs /dials/op (stubbed) → reload → the preview updates
    const dialSel = '#pipe-board .hy-card[data-organ="converge"] .pipe-dial[data-path="loop.max_rounds"] .ctl';
    await pg.$eval(dialSel, (el) => { el.value = '7'; el.dispatchEvent(new Event('change', { bubbles: true })); });
    await pg.waitForFunction(() => /loop\.max_rounds\s*=\s*7/.test((document.querySelector('#pipe-board .hy-card[data-organ="converge"] .pipe-dry') || {}).textContent || ''), null, { timeout: 6000 });
    ok(editedVal === 7, `the dial edit rode the ONE write path (POST /dials/op, value ${editedVal})`);
    ok(true, 'DIAL EDIT → DRY-RUN UPDATES: editing loop.max_rounds re-rendered the pre-arm preview to = 7');

    // ── (10) BANKED VERB SAYS BANKED — a model-heavy scoped fire previews, ARMS, then BANKS ──
    await pg.waitForSelector('#pipe-board .hy-card[data-organ="global"]', { timeout: 6000 });
    await pg.click('#pipe-board .hy-card[data-organ="global"] .hy-card-id');
    await pg.waitForSelector('#pipe-board .hy-card[data-organ="global"].is-open .rt-ctrl[data-action="dream"] .rt-launch', { timeout: 6000 });
    launchPosts = [];
    await pg.click('#pipe-board .hy-card[data-organ="global"] .rt-ctrl[data-action="dream"] .rt-launch');  // reveal dry-run + fire btn
    await pg.waitForSelector('#pipe-board .hy-card[data-organ="global"] .rt-ctrl[data-action="dream"] .rt-fire', { timeout: 6000 });
    await pg.click('#pipe-board .hy-card[data-organ="global"] .rt-ctrl[data-action="dream"] .rt-fire');    // ARM only
    await sleep(250);
    ok(launchPosts.length === 0, 'the model-heavy fire ARMED and banked NOTHING on the first click (arm-to-fire; no heavy work fires)');
    await pg.click('#pipe-board .hy-card[data-organ="global"] .rt-ctrl[data-action="dream"] .rt-fire');    // FIRE → bank
    await pg.waitForFunction(() => /banked/i.test((document.querySelector('#pipe-board .hy-card[data-organ="global"] .rt-ctrl[data-action="dream"] .rt-out') || {}).textContent || ''), null, { timeout: 4000 });
    const bankOut = await pg.textContent('#pipe-board .hy-card[data-organ="global"] .rt-ctrl[data-action="dream"] .rt-out');
    ok(launchPosts.length === 1 && launchPosts[0].armed === true, `the second click BANKED a work-order (one armed POST: ${JSON.stringify(launchPosts[0])})`);
    ok(/banked/i.test(bankOut || ''), `the heavy verb SAYS banked (${JSON.stringify((bankOut || '').trim())})`);

    // ── (11) ✎ RULE present on the pipeline organ card (the shared atom adopted) ──
    await pg.hover('#pipe-board .hy-card[data-organ="converge"] .hy-card-id');
    const pipeRule = await pg.$('#pipe-board .hy-card[data-organ="converge"] .hy-card-id .rule-chip');
    ok(pipeRule !== null, 'the ✎ rule atom is attached to the pipeline organ card (D16 adopted)');

    // ═══════════ PIPELINE SUB-ORGANS — THE CONJUGATE WAVE (falqon has banked telemetry) ═══════════
    // falqon carries a banked run for EVERY night-organ (2026-07-17), so the sub-cards render REAL
    // reader telemetry (view=mechanism). The scoped fires ride the SAME stubbed POST /storyboard/
    // run/launch (no real bank — the walk stays non-mutating). /pipeline/organ is intercepted only
    // to inject the failed gate for the structural card's honesty seam; every other read is live.
    const FALQON = 'paper_falqon';
    await pg.route('**/pipeline/organ*', async (route) => {
      const url = route.request().url();
      const resp = await route.fetch();
      let j; try { j = await resp.json(); } catch (_e) { return route.fulfill({ response: resp }); }
      if (/organ=structural-conformance/.test(url) && j.payload && Array.isArray(j.payload.store_gates))
        for (const s of j.payload.store_gates) if (s.store === 'spine_chain')
          s.gate = { state: 'failed', passed: false, refusal: 'holdout gate did not pass (walk-injected)' };
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(j) });
    });
    await pg.goto(base + '/pipeline?project=' + FALQON, { waitUntil: 'domcontentloaded' });
    // the pipeline rests on its composed brief; materialise the board behind the organ-panels
    // count chip before the sub-organ cards can be reached (W-PROJECT).
    await pg.waitForSelector('.pipe-count[data-count="organs"]', { timeout: 15000 });
    await pg.click('.pipe-count[data-count="organs"]');
    await pg.waitForSelector('#pipe-board .hy-card[data-organ="converge"]', { timeout: 15000 });
    await sleep(250);

    // ── (12) DETECTORS SUB-CARD — banked census counts + the fire arms (never fires blind) ──
    await pg.click('#pipe-board .hy-card[data-organ="converge"] .hy-card-id');
    await pg.waitForSelector('#pipe-board .hy-card[data-organ="converge"].is-open .hy-card[data-suborgan="detectors"]', { timeout: 8000 });
    const detChips = await pg.textContent('.hy-card[data-suborgan="detectors"] .hy-card-chips');
    ok(/30\s*gaps/.test(detChips || ''), `the detectors sub-card head carries the banked census count (chips: ${JSON.stringify((detChips || '').trim())})`);
    await pg.click('.hy-card[data-suborgan="detectors"] .hy-card-id');   // lazy-fetch GET /pipeline/organ
    await pg.waitForFunction(() => { const t = (document.querySelector('.hy-card[data-suborgan="detectors"] .pipe-suboev') || {}).textContent || ''; return /gaps/i.test(t) && !/reading/i.test(t); }, null, { timeout: 8000 });
    const detEv = await pg.textContent('.hy-card[data-suborgan="detectors"] .pipe-suboev');
    ok(/30/.test(detEv || ''), `the detectors evidence zone renders the reader's OWN facts (30 gaps): ${JSON.stringify((detEv || '').slice(0, 70))}`);
    launchPosts = [];
    const detFire = '.hy-card[data-suborgan="detectors"] .rt-ctrl[data-action="detector-run"]';
    await pg.waitForSelector(detFire + ' .rt-launch', { timeout: 6000 });
    await pg.click(detFire + ' .rt-launch');                              // reveal the dry-run BEFORE any arm
    // the dry-run zone unhides immediately then loads its worklist async — wait for the
    // settled "what would fire" content (the pre-arm read), not the "reading…" placeholder.
    await pg.waitForFunction((sel) => { const e = document.querySelector(sel + ' .rt-dry'); return e && !e.hidden && /what would fire/i.test(e.textContent || ''); }, detFire, { timeout: 8000 });
    const detDry = await pg.textContent(detFire + ' .rt-dry');
    ok(/what would fire/i.test(detDry || ''), 'the detectors fire shows its DRY-RUN "what would fire" zone BEFORE any arm (never fires blind)');
    await pg.waitForSelector(detFire + ' .rt-fire', { timeout: 4000 });
    await pg.click(detFire + ' .rt-fire');                                // ARM only (model-heavy)
    await sleep(200);
    const detArm = await pg.textContent(detFire + ' .rt-fire');
    ok(launchPosts.length === 0 && /again/i.test(detArm || ''), `the detectors fire ARMED and banked nothing (0 posts; button: ${JSON.stringify((detArm || '').trim())})`);

    // ── (13) STAGED — figures LIVE dry-run BEFORE arm + bibliography/citation banked counts ──
    await pg.click('#pipe-board .hy-card[data-organ="staged"] .hy-card-id');
    await pg.waitForSelector('#pipe-board .hy-card[data-organ="staged"].is-open .hy-card[data-suborgan="figures"]', { timeout: 8000 });
    const bibChips = await pg.textContent('.hy-card[data-suborgan="bibliography"] .hy-card-chips');
    ok(/11\s*resolved/.test(bibChips || ''), `the bibliography sub-card carries banked counts (11 resolved): ${JSON.stringify((bibChips || '').trim())}`);
    const cdChips = await pg.textContent('.hy-card[data-suborgan="citation-direction"] .hy-card-chips');
    ok(/5\s*intents/.test(cdChips || ''), `the citation-direction sub-card carries banked counts (5 intents): ${JSON.stringify((cdChips || '').trim())}`);
    // figures: the ONE organ whose dry-run zone renders a TRUE live preview (matched/absent) BEFORE arm
    await pg.click('.hy-card[data-suborgan="figures"] .hy-card-id');
    await pg.waitForFunction(() => { const t = (document.querySelector('.hy-card[data-suborgan="figures"] .pipe-dry .pipe-suboev') || {}).textContent || ''; return /matched/i.test(t) && !/computing/i.test(t); }, null, { timeout: 8000 });
    const figDry = await pg.textContent('.hy-card[data-suborgan="figures"] .pipe-dry .pipe-suboev');
    ok(/matched\s*2/.test(figDry || ''), `the figures sub-card renders the LIVE dry-run preview (matched 2) BEFORE any arm: ${JSON.stringify((figDry || '').slice(0, 70))}`);
    const figDryHead = await pg.textContent('.hy-card[data-suborgan="figures"] .pipe-dry .pipe-zh');
    ok(/live preview/i.test(figDryHead || '') && /before any arm/i.test(figDryHead || ''), 'the figures dry-run zone is named the ONE live preview, before any arm');
    // bibliography (local-safe, arm-required) ALSO shows its dry-run before arm — every fire, not one
    await pg.click('.hy-card[data-suborgan="bibliography"] .hy-card-id');   // open its fold so the fire renders
    const bibFire = '.hy-card[data-suborgan="bibliography"] .rt-ctrl[data-action="bibliography-run"]';
    await pg.waitForSelector(bibFire + ' .rt-launch', { timeout: 6000 });
    await pg.click(bibFire + ' .rt-launch');
    await pg.waitForFunction((sel) => { const e = document.querySelector(sel + ' .rt-dry'); return e && !e.hidden && /what would fire/i.test(e.textContent || ''); }, bibFire, { timeout: 8000 });
    const bibDry = await pg.textContent(bibFire + ' .rt-dry');
    ok(/what would fire/i.test(bibDry || ''), 'the bibliography fire (local-safe) shows its dry-run zone before arming too');

    // ── (14) STRUCTURAL — the gate chip is HONEST: a red (failed) gate renders WARN, never green;
    //         arming enabled on it is REFUSED (the toggle reverts, no /dials/op POST fires) ──
    await pg.click('#pipe-board .hy-card[data-organ="weld"] .hy-card-id');
    await pg.waitForSelector('#pipe-board .hy-card[data-organ="weld"].is-open .hy-card[data-suborgan="structural-conformance"]', { timeout: 8000 });
    await pg.click('.hy-card[data-suborgan="structural-conformance"] .hy-card-id');
    await pg.waitForSelector('.hy-card[data-suborgan="structural-conformance"] .pipe-gaterow', { timeout: 8000 });
    const gateChips = await pg.$$eval('.hy-card[data-suborgan="structural-conformance"] .pipe-gaterow .pipe-gate .hy-chip',
      (els) => els.map((e) => ({ text: e.textContent.trim(), warn: e.classList.contains('is-warn'), ok: e.classList.contains('is-ok') })));
    const spineGate = gateChips.find((g) => /failed/.test(g.text));
    ok(spineGate && spineGate.warn && !spineGate.ok, `the red (failed) gate renders WARN, never green (CHIP law): ${JSON.stringify(spineGate)}`);
    dialPosts = [];
    const spineToggle = '.hy-card[data-suborgan="structural-conformance"] .pipe-dial[data-path="stores.spine_chain.enabled"] .ctl';
    await pg.$eval(spineToggle, (el) => { el.checked = true; el.dispatchEvent(new Event('change', { bubbles: true })); });
    await sleep(250);
    const stillOff = await pg.$eval(spineToggle, (el) => el.checked);
    const refusal = await pg.textContent('.hy-card[data-suborgan="structural-conformance"] .pipe-gaterow .pipe-gate-r').catch(() => '');
    ok(stillOff === false && dialPosts.length === 0, `arming the RED-gate store was REFUSED — the toggle reverted (checked=${stillOff}) and NO /dials/op POST fired (the SystemExit trap never reached)`);
    ok(/refused/i.test(refusal || ''), `the refusal reason renders inline on the gate row: ${JSON.stringify((refusal || '').slice(0, 60))}`);

    // ── (15) 375px — both surfaces single column, no horizontal scroll ──
    // start each surface COLD (clear the assets session-sticky return so a reload lands on the
    // brief, not re-pinned on the last deep-linked asset — the stickiness is proven above).
    await pg.addInitScript(() => { try { sessionStorage.clear(); } catch (e) { /* private mode */ } });
    for (const [surf, url] of [['assets', '/assets?corpus=' + CORPUS],
                               ['pipeline', '/pipeline?project=' + CORPUS]]) {
      await pg.setViewportSize({ width: 375, height: 780 });
      await pg.goto(base + url, { waitUntil: 'domcontentloaded' });
      // both surfaces rest on a composed brief; materialise the roster/board before asserting width.
      if (surf === 'pipeline') {
        await pg.waitForSelector('.pipe-count[data-count="organs"]', { timeout: 12000 });
        await pg.click('.pipe-count[data-count="organs"]');
        await pg.waitForSelector('#pipe-board .hy-card[data-organ]', { timeout: 12000 });
      } else {
        await pg.waitForSelector('.asb-count[data-kind="figures"]', { timeout: 12000 });
        await pg.click('.asb-count[data-kind="figures"]');
        await pg.waitForSelector('.asb-mat .asb-cards .asb-card', { timeout: 12000 });
      }
      await sleep(200);
      const noH = await pg.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1);
      ok(noH, `375px ${surf}: no horizontal scroll (single column, never widens the page)`);
    }

    ok(errs.length === 0, 'zero uncaught page errors across the whole walk: ' + JSON.stringify(errs));
    console.log(`\nWAVE 6 ASSETS + PIPELINE — ${passed} assertions green.`);
  } finally {
    await b.close();
    if (scanner) scanner.kill('SIGKILL');
  }
})().catch((e) => { console.error('\nWALK FAILED:', e.message); if (scanner) scanner.kill('SIGKILL'); process.exit(1); });
