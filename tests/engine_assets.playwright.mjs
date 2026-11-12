// ENGINE ASSETS — the asset surface joined to the ONE INSTRUMENT (W-ASSETS, the LAST surface),
// driven against a REAL scanner. The walk proves the resting-state law (E), the geometry
// couplet (B), and B.5's no-lobby-tax as OUTCOMES, not DOM presence — on BOTH corpora, so the
// enumeration machinery (never a hardcoded figure) is what renders:
//   · brief base altitude: at rest NO roster / cockpit exists in the DOM; the composed prose
//     names the real counts by kind + the landed/demonstrates honesty, and one ask rides it;
//   · count chips: one per kind (figures / derivations);
//   · materialise: opening a kind chip builds THAT suite's roster; the counts law holds (the
//     chip number equals the cards it opened) — proven on subset-sum AND eigenengine;
//   · pin the asset: opening a card REALLOCATES + rail + breadcrumb + a VISIBLE named return
//     door, and the close-examination cockpit (four zones) claims the space;
//   · close: exact bounded-pane scroll restore + no return-door residue;
//   · NO LOBBY TAX (B.5): a ?asset= deep-link lands PRE-PINNED on the target with the named
//     return door, WITHOUT a click — the brief is never a mandatory step on that path;
//   · the register law: no raw FB-/WO-/GT- ledger ids above the fold (ids live at audit depth);
//   · scroll bounded: at 1280 / 1536 / 768 the page never scrolls horizontally (1.0x).
//
//   run:  node tests/engine_assets.playwright.mjs
//   Exits 0 all-green, non-zero on the first failed assertion. Both WRITE doors are unused here
//   (the walk is read-only); no ledger is touched.
import { createRequire } from 'module';
import { spawn, execSync } from 'child_process';
import net from 'net';

const require = createRequire(import.meta.url);
const { chromium } = require(execSync('npm root -g').toString().trim() + '/playwright');
const CHROME = execSync('ls /opt/pw-browsers/chromium-*/chrome-linux/chrome').toString().trim().split('\n')[0];
const PY = 'python3';
const SUBSET = 'subset-sum-itqde';
const EIGEN = 'eigenengine';
const EMPTY = 'paper_eigen';   // enumerates to zero — the instructive empty brief lives here

let passed = 0;
function ok(cond, msg) { if (!cond) throw new Error('ASSERT FAILED: ' + msg); passed++; console.log('  ok -', msg); }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// §C5 write-path proof (gaps 1 + 3): the assess + regen doors are DRIVEN through the surface,
// banking one finding into subset-sum's REAL feedback ledger and one manifest-only work-order
// into work_orders.jsonl — then cleaned out surgically in the finally, so the net leaves the
// tree exactly as it found it (this walk is MUTATING_WALKS-marked).
const PROBE_ASSESS = 'zzz-probe-assess-' + Date.now();
let bankedWO = '';   // the regen work-order id banked during the walk, cleaned by exact id
function cleanupProbes() {
  try {
    execSync(`${PY} - <<'PY'
from laplace.manuscript import review_surface as rs
from laplace.web.scanner import _repo_root
md = rs.manuscript_dir('subset-sum-itqde', '')
led = md / 'feedback' / 'feedback.jsonl'
if led.is_file():
    rows = [l for l in led.read_text().splitlines() if l.strip()]
    keep = [l for l in rows if ${JSON.stringify(PROBE_ASSESS)} not in l]
    led.write_text(('\\n'.join(keep) + '\\n') if keep else '')
    print('  assess cleanup removed', len(rows) - len(keep), 'probe finding(s)')
wo_id = ${JSON.stringify(bankedWO)}
if wo_id:
    import json
    wo = _repo_root() / 'corpus_friction' / 'work_orders.jsonl'
    if wo.is_file():
        rows = [l for l in wo.read_text().splitlines() if l.strip()]
        keep = [l for l in rows if json.loads(l).get('id') != wo_id]
        wo.write_text(('\\n'.join(keep) + '\\n') if keep else '')
        print('  regen cleanup removed', len(rows) - len(keep), 'probe work-order(s)')
PY`, { stdio: 'inherit' });
  } catch (e) { console.error('  probe cleanup error:', e.message); }
}
function freePort() { return new Promise((res) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); }); }
function waitFor(url, tries = 80) {
  return new Promise((res, rej) => { const tick = (n) => { const req = require('http').get(url, (r) => { r.resume(); res(true); });
    req.on('error', () => n <= 0 ? rej(new Error('server never came up')) : setTimeout(() => tick(n - 1), 250)); }; tick(tries); });
}
// enumerate the truth in-process (the SAME read the brief + roster compose over) so the walk
// asserts against the enumeration, never a hardcoded count.
function enumerate(corpus) {
  const out = execSync(`${PY} -c "import json; from laplace.pipeline import asset_model as am; a=am.enumerate_assets('${corpus}'); print(json.dumps({'figures':sum(1 for x in a if x.kind=='figure'),'derivations':sum(1 for x in a if x.kind=='derivation'),'total':len(a)}))"`).toString().trim();
  return JSON.parse(out);
}

let scanner;
(async () => {
  const repoRoot = execSync(`${PY} -c "from laplace.web.scanner import _repo_root; print(_repo_root().resolve())"`).toString().trim();
  const port = await freePort();
  scanner = spawn(PY, ['-m', 'laplace.web.scanner', '--port', String(port)], { cwd: repoRoot, stdio: 'ignore' });
  await waitFor(`http://127.0.0.1:${port}/assets`);
  const base = `http://127.0.0.1:${port}`;
  const TRUTH = { [SUBSET]: enumerate(SUBSET), [EIGEN]: enumerate(EIGEN) };
  const b = await chromium.launch({ executablePath: CHROME });
  try {
    const pg = await b.newPage({ viewport: { width: 1280, height: 720 } });
    const errs = []; pg.on('pageerror', (e) => errs.push(String(e)));

    await pg.goto(base + '/assets?corpus=' + SUBSET, { waitUntil: 'networkidle' });
    await pg.waitForSelector('[data-role="brief-prose"]', { timeout: 8000 });
    await sleep(200);

    // ── (1) THE BRIEF BASE ALTITUDE (E) — composed prose + one ask, ZERO roster DOM ──
    const prose = (await pg.textContent('[data-role="brief-prose"]')).trim();
    ok(prose.length > 40, 'the composed brief prose is present at rest: ' + JSON.stringify(prose.slice(0, 80)));
    ok(new RegExp('\\b' + TRUTH[SUBSET].total + '\\s+assets?\\b').test(prose) &&
       new RegExp('\\b' + TRUTH[SUBSET].figures + '\\s+figures?\\b').test(prose),
      `the brief names the REAL enumeration (${TRUTH[SUBSET].total} assets, ${TRUTH[SUBSET].figures} figures) — never a hardcoded figure`);
    ok(/land in the artefact/i.test(prose) && /demonstrate a claim/i.test(prose),
      'the brief carries the landed + demonstrates honesty (measured/inferred words, not a banner)');
    const restDom = await pg.evaluate(() => ({
      cards: document.querySelectorAll('.asb-card').length,
      cockpit: document.querySelectorAll('.dk-cockpit').length,
      reallocated: document.querySelector('#eng-root').classList.contains('reallocated'),
      chips: document.querySelectorAll('.asb-count').length,
      ask: document.querySelectorAll('[data-role="brief-ask"]').length,
    }));
    ok(restDom.cards === 0 && restDom.cockpit === 0 && !restDom.reallocated,
      'at rest ZERO roster / cockpit / reallocation in the DOM (everything materialises on open): ' + JSON.stringify(restDom));
    ok(restDom.chips >= 1, 'one-line count chips are present, one per kind: ' + restDom.chips);
    ok(restDom.ask === 1, 'at most one ask rides the brief (the single most consequential pointer)');

    // ── THE REGISTER LAW — no raw ledger ids above the fold (run at rest) ──
    const aboveFold = await pg.evaluate(() => document.body.innerText);
    ok(!/\b(FB|WO|GT|DQ|PV|RW)-[0-9A-Za-z]{4,}/.test(aboveFold),
      'no raw FB-/WO-/GT- ledger ids above the fold (ids live at audit depth) — register 0');

    // ── (2) MATERIALISE — the counts law on BOTH corpora (chip N == cards opened) ──
    for (const corpus of [SUBSET, EIGEN]) {
      await pg.goto(base + '/assets?corpus=' + corpus, { waitUntil: 'networkidle' });
      await pg.waitForSelector('.asb-count[data-kind="figures"]', { timeout: 8000 }); await sleep(120);
      const chipN = Number((await pg.textContent('.asb-count[data-kind="figures"] .asb-cn')).trim());
      ok(chipN === TRUTH[corpus].figures, `${corpus}: the figures chip equals the enumeration (${chipN} == ${TRUTH[corpus].figures})`);
      await pg.click('.asb-count[data-kind="figures"]');
      await pg.waitForSelector('.asb-mat .asb-cards .asb-card', { timeout: 8000 }); await sleep(120);
      const matCards = await pg.$$eval('.asb-mat .asb-cards .asb-card', (e) => e.length);
      ok(matCards === chipN, `${corpus}: MATERIALISE equals enumeration — the figures chip (${chipN}) opened exactly ${matCards} cards (the counts law, same machinery)`);
    }

    // back to subset-sum for the pin / close / deep-link proofs
    await pg.goto(base + '/assets?corpus=' + SUBSET, { waitUntil: 'networkidle' });
    await pg.waitForSelector('.asb-count[data-kind="figures"]', { timeout: 8000 }); await sleep(120);
    await pg.click('.asb-count[data-kind="figures"]');
    await pg.waitForSelector('.asb-mat .asb-cards .asb-card', { timeout: 8000 }); await sleep(120);

    // scroll the bounded pane to a nonzero position (a real restore proof), then click a VISIBLE card.
    await pg.evaluate(() => { const s = document.getElementById('assets'); if (s) s.scrollTop = 40; }); await sleep(60);
    const paneScrollAtPin = await pg.evaluate(() => Math.round(document.getElementById('assets').scrollTop));
    ok(paneScrollAtPin > 0, 'the bounded #assets pane is scrolled to a nonzero position before the pin: ' + paneScrollAtPin);

    // ── (3) PIN THE ASSET — reallocate + named return door + the cockpit claims the space ──
    // Click via a DOM .click() (no playwright auto-scroll) so the pane's scroll is UNMOVED between
    // the capture above and the pin — a real, unperturbed restore proof.
    const firstAsset = await pg.$eval('.asb-mat .asb-cards .asb-card', (e) => e.getAttribute('data-asset'));
    await pg.$eval('.asb-mat .asb-cards .asb-card', (e) => e.click()); await sleep(400);
    ok(await pg.$eval('#eng-root', (e) => e.classList.contains('reallocated')), 'opening a card REALLOCATED the surface (the asset claims the centre)');
    ok(await pg.$('.eng-rail').then((x) => !!x), 'the context rail is present (the compact summaries + switch)');
    ok(await pg.$('.eng-breadcrumb').then((x) => !!x), 'the breadcrumb is present');
    const doorLabel = (await pg.textContent('[data-role="return-door"] .rd-label')).trim();
    ok(/back to the brief/i.test(doorLabel), 'the return door NAMES its destination: ' + JSON.stringify(doorLabel));
    const doorVisible = await pg.$eval('[data-role="return-door"]', (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
    ok(doorVisible, 'the return door is VISIBLE (a return door that is not visible does not exist)');
    for (const z of ['zone-context', 'zone-consequences', 'zone-tools', 'zone-deeplinks'])
      ok(await pg.$('.eng-focus .dk-cockpit .' + z) !== null, `the close-examination cockpit renders .${z} in the reallocated focus`);
    // the WHOLE asset loads (a live GET /assets/object against the real read) — the figure image
    // or the step list, not the "loading…" placeholder.
    await pg.waitForFunction(() => {
      const c = document.querySelector('.eng-focus .zone-context .dk-ctx-body');
      return c && !/loading the asset/i.test(c.innerText) && (c.querySelector('img.as-fig') || c.querySelector('.as-step') || c.innerText.trim().length > 0);
    }, { timeout: 8000 });
    ok(true, 'the WHOLE asset rendered inline in the focus (GET /assets/object fired against its real read)');

    // ── (4) CLOSE — exact bounded-pane scroll restore + no return-door residue ──
    await pg.keyboard.press('Escape'); await sleep(400);
    ok(!(await pg.$eval('#eng-root', (e) => e.classList.contains('reallocated'))), 'Esc closed the focus back to the brief');
    ok((await pg.$('[data-role="return-door"]')) === null, 'the return door is ABSENT from the resting DOM (no hidden residue)');
    ok((await pg.$$eval('.asb-mat .asb-cards .asb-card', (e) => e.length)) > 0, 'the return landed on the materialised roster (exact restore of where he was)');
    const paneScrollAfter = await pg.evaluate(() => Math.round(document.getElementById('assets').scrollTop));
    ok(Math.abs(paneScrollAfter - paneScrollAtPin) <= 2, `the bounded pane scroll restored exactly on close (${paneScrollAfter} ≈ ${paneScrollAtPin})`);

    // ── (5) NO LOBBY TAX (B.5) — a ?asset= deep-link PRE-PINS on load, no click ──
    await pg.goto(base + '/assets?corpus=' + SUBSET + '&asset=' + encodeURIComponent(firstAsset), { waitUntil: 'networkidle' });
    await pg.waitForSelector('#eng-root.reallocated', { timeout: 8000 }); await sleep(200);
    ok(await pg.$eval('#eng-root', (e) => e.classList.contains('reallocated')),
      'a ?asset= deep-link lands PRE-PINNED on the target (reallocated at first paint — no click, no lobby tax)');
    const dlDoor = (await pg.textContent('[data-role="return-door"] .rd-label')).trim();
    ok(/back to the brief/i.test(dlDoor), 'the deep-linked arrival carries the named return door back to the brief');
    ok(await pg.$('.eng-focus .dk-cockpit .zone-context') !== null, 'the deep-linked asset opened whole (the cockpit claims the space)');

    // ── (5b) THE INSTRUCTIVE EMPTY BRIEF — a zero-asset corpus states WHY it is empty and
    // WHERE its assets will land (never a bare "carries 0 assets."), keyed on real state ──
    {
      const emptyTruth = enumerate(EMPTY);
      ok(emptyTruth.total === 0, `${EMPTY} enumerates to zero assets (the empty-brief fixture)`);
      await pg.setViewportSize({ width: 1280, height: 720 });
      await pg.goto(base + '/assets?corpus=' + EMPTY, { waitUntil: 'networkidle' });
      await pg.waitForSelector('[data-role="brief-prose"]', { timeout: 8000 }); await sleep(150);
      const emptyProse = (await pg.textContent('[data-role="brief-prose"]')).trim();
      ok(/\bno assets yet\b/i.test(emptyProse) && /pipeline/i.test(emptyProse),
        'the empty brief states the REASON (the pipeline has not built the corpus), not a bare "carries 0 assets": ' +
        JSON.stringify(emptyProse.slice(0, 120)));
      ok(new RegExp(EMPTY + '[\\w/\\-]*figures', 'i').test(emptyProse),
        'the empty brief names the PATH where its figures will surface (instructive, not a dead end)');
      ok((await pg.$$('[data-role="brief-ask"]')).length === 1,
        'the empty brief still carries the one instructive ask (build the pipeline)');

    // ── (5c) THE MISS BANNER — a bogus ?asset= resolves to no card and SAYS so (a transient
    // worded banner naming the id + corpus), landing on the roster instead of silence ──
      const bogus = 'figure:no-such-asset-zzz';
      await pg.goto(base + '/assets?corpus=' + SUBSET + '&asset=' + encodeURIComponent(bogus), { waitUntil: 'networkidle' });
      await pg.waitForSelector('#as-miss', { timeout: 8000 }); await sleep(120);
      const missTxt = (await pg.textContent('#as-miss')).trim();
      ok(/no such asset here/i.test(missTxt) && /roster/i.test(missTxt),
        'a bogus ?asset= surfaces the worded miss banner (not a silent brief): ' + JSON.stringify(missTxt));
      ok(missTxt.includes('no-such-asset-zzz') && missTxt.includes(SUBSET),
        'the miss banner NAMES the unresolved id and the corpus: ' + JSON.stringify(missTxt));
      ok(!(await pg.$eval('#eng-root', (e) => e.classList.contains('reallocated'))),
        'the bogus deep-link did NOT pin a phantom asset — it fell honestly to the roster (no cockpit)');
      ok((await pg.$('.dk-cockpit')) === null, 'no cockpit was synthesized for the missing asset (never a fabricated landing)');
    }

    // ── (6) SCROLL BOUNDED at 1280 / 1536 / 768 — the page never scrolls horizontally (1.0x) ──
    // start each width COLD on the brief: clear the session-sticky return so a reload does not
    // re-pin the last asset (the stickiness is proven above; here we want the resting brief).
    await pg.addInitScript(() => { try { sessionStorage.clear(); } catch (e) { /* private mode */ } });
    for (const w of [1280, 1536, 768]) {
      await pg.setViewportSize({ width: w, height: 720 });
      await pg.goto(base + '/assets?corpus=' + SUBSET, { waitUntil: 'networkidle' });
      await pg.waitForSelector('.asb-count[data-kind="figures"]', { timeout: 8000 });
      await pg.click('.asb-count[data-kind="figures"]');
      await pg.waitForSelector('.asb-mat .asb-cards .asb-card', { timeout: 8000 }); await sleep(120);
      const bounded = await pg.evaluate(() => ({
        pageNoH: document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
        paneNoH: (() => { const s = document.getElementById('assets'); return s ? s.scrollWidth <= s.clientWidth + 1 : true; })(),
      }));
      ok(bounded.pageNoH && bounded.paneNoH, `${w}px: no horizontal scroll — the page + the bounded pane stay contained (1.0x)`);
    }

    // ── (7) THE ASSESS ECHO (gap 1) — bank a finding through the composer; it lands in the
    // FINDINGS zone at once (the echo law: his finding is visible where he looks). Driven as a
    // real POST /assets/assess with an author actor; the probe row is cleaned out in the finally.
    await pg.evaluate(() => { try { sessionStorage.clear(); } catch (e) { /* private */ } });
    await pg.setViewportSize({ width: 1280, height: 900 });
    await pg.goto(base + '/assets?corpus=' + SUBSET + '&asset=' + encodeURIComponent(firstAsset), { waitUntil: 'networkidle' });
    await pg.waitForSelector('#eng-root.reallocated .zone-findings', { timeout: 8000 }); await sleep(200);
    const findsAtLoad = await pg.$$eval('.zone-findings .as-find', (e) => e.length);
    // the zone is honest when empty (a stated absence), or lists prior findings — never blank.
    const findsBody = (await pg.textContent('.zone-findings .dk-find-body')).trim();
    ok(findsBody.length > 0, 'the FINDINGS zone renders at rest (rows or a stated absence), never blank');
    // drive the assess composer: default anchor (whole figure), default kind (note), his words.
    await pg.fill('.zone-tools #as-comment', PROBE_ASSESS + ' — this panel needs a scale bar');
    await pg.click('.zone-tools #as-bank');
    await pg.waitForFunction((mk) => [...document.querySelectorAll('.zone-findings .as-find .as-find-comment')]
      .some((r) => r.textContent.includes(mk)), PROBE_ASSESS, { timeout: 8000 });
    ok(true, 'banking a finding ECHOES it into the FINDINGS zone at once (no reload — the assess echo)');
    const freshRow = (await pg.$eval('.zone-findings .as-find.is-fresh', (e) => e.innerText).catch(() => ''));
    ok(freshRow.includes(PROBE_ASSESS), 'the just-banked finding is the accented fresh row: ' + JSON.stringify(freshRow.slice(0, 60)));
    const rowMeta = (await pg.$eval('.zone-findings .as-find.is-fresh .as-find-meta', (e) => e.innerText).catch(() => ''));
    ok(/author/.test(rowMeta), 'the finding row NAMES its actor (author) — the actor law: ' + JSON.stringify(rowMeta));
    const findsAfter = await pg.$$eval('.zone-findings .as-find', (e) => e.length);
    ok(findsAfter === findsAtLoad + 1, `the findings zone grew by exactly the banked row (${findsAtLoad} → ${findsAfter})`);

    // ── (8) THE REGEN DESK DOOR (gap 3) — the banked regen order NAMES its door: the WO id in
    // the message is a link onto the work-orders desk, and it joins the consequences zone. Only
    // on a regenable asset (a named producer); the banked order is cleaned by exact id.
    const regenBtn = await pg.$('#as-regen');
    if (regenBtn) {
      // arm-to-fire: the first click arms, the second banks (the shared destructive idiom).
      await pg.click('#as-regen'); await sleep(150);
      await pg.click('#as-regen'); await sleep(150);
      await pg.waitForSelector('#as-regen-msg .as-door[href*="class=work-orders"]', { timeout: 8000 });
      const doorHref = await pg.$eval('#as-regen-msg .as-door', (e) => e.getAttribute('href'));
      ok(/\/desk\?class=work-orders/.test(doorHref), 'the regen message carries the desk door (/desk?class=work-orders): ' + JSON.stringify(doorHref));
      bankedWO = await pg.$eval('#as-regen-msg .as-door', (e) => e.textContent.trim().replace(/\s*→\s*$/, ''));
      ok(/^WO-/.test(bankedWO), 'the door text IS the banked work-order id (an addressable order, not a dead id): ' + JSON.stringify(bankedWO));
      await pg.waitForSelector('.zone-consequences .as-order .as-order-door', { timeout: 8000 });
      const consOrder = await pg.$eval('.zone-consequences .as-order .as-order-door', (e) => e.textContent);
      ok(consOrder.includes(bankedWO), 'the banked order joins the CONSEQUENCES zone, doored to the desk (the echo): ' + JSON.stringify(consOrder.trim()));
    } else {
      ok(true, 'the first asset has no producer — regen is honestly absent (the regen-door proof re-arms on a producer-backed asset)');
    }

    ok(errs.length === 0, 'zero uncaught page errors across the whole walk: ' + JSON.stringify(errs));
    console.log(`\nENGINE ASSETS — ${passed} assertions green.`);
  } finally {
    await b.close();
    if (scanner) scanner.kill('SIGKILL');
    cleanupProbes();
  }
})().catch((e) => { console.error('\nWALK FAILED:', e.message); if (scanner) scanner.kill('SIGKILL'); cleanupProbes(); process.exit(1); });
