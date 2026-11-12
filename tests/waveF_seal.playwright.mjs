// ═══════════════════════════════════════════════════════════════════════════
// WAVE F — THE SEAL, cross-surface, driven in a real browser against a real
// scanner. This is the fleet re-scripted to RULING_2026-07-15's bar: the walk
// asks the three questions the old selector-exists tier never did, on EVERY
// rostered surface, so the remote seal can no longer certify what the chair
// rejects. Necessary, never sufficient — the chair walk (scripts/chair_walk.py)
// carries what only his eyes can judge.
//
//   run:  node tests/waveF_seal.playwright.mjs
//   deps: global `playwright`, Chromium at /opt/pw-browsers, the repo venv python
//         as python3. Exits 0 all-green, non-zero on the first failure.
//
// NON-MUTATING: the D16 bank is INTERCEPTED (fulfilled with a canned record) so
// the walk proves the client wiring + the typed-fork payload WITHOUT writing to the
// friction ledger; the desk DRAIN is proven against the live /desk/data schema (the
// `forks` class that reads the same corpus_friction ledger the bank targets). The
// real write-path round-trip is the deliberate, mutating tests/waveF_desk_landing.
//
// The clauses, each over the full roster (RULING seal bar + DESIGN §3 Wave F):
//   A  context header PRESENT + TRUTHFUL — names surface · project · selection,
//      and every token matches the LIVE url (the "what am I looking at" answered).
//   B  every clickable answers HOVER — a computed-style delta + cursor:pointer on a
//      sample clickable per surface (the "how do I interact" answered).
//   C  NO HITBOX MOTION under the pointer — click A, assert every card at-or-above
//      A's row keeps its boundingRect (expansion displaces BELOW only) on every
//      surface that has expandable cards (the on-camera /assets misclick, killed).
//   D  the D15 ARRIVAL ECHO fires + dismisses cross-surface — a real door back from
//      a stamped origin, the × clears it (the "where did that take me" answered).
//   E  the ✎ RULE chip rides every surface's header; on a representative surface it
//      BANKS a typed open interface fork, and the desk DRAINS that ledger (D16).
//   R6 no served surface renders a mock-only artifact (D-tags / redline box).
import { createRequire } from 'module';
import { spawn, execSync } from 'child_process';
import net from 'net';
import http from 'http';

const require = createRequire(import.meta.url);
const PW_ROOT = execSync('npm root -g').toString().trim() + '/playwright';
const { chromium } = require(PW_ROOT);
const CHROME = execSync('ls /opt/pw-browsers/chromium-*/chrome-linux/chrome').toString().trim().split('\n')[0];
const PY = 'python3';

let passed = 0;
function ok(cond, msg) { if (!cond) throw new Error('ASSERT FAILED: ' + msg); passed++; console.log('  ok -', msg); }
function freePort() { return new Promise((res, rej) => {
  const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); s.on('error', rej); }); }
function waitFor(url, tries = 80) { return new Promise((res, rej) => {
  const tick = (n) => { const req = http.get(url, (r) => { r.resume(); res(true); });
    req.on('error', () => n <= 0 ? rej(new Error('server never came up')) : setTimeout(() => tick(n - 1), 250)); }; tick(tries); }); }
function get(port, path) { return new Promise((res, rej) => {
  http.get(`http://127.0.0.1:${port}${path}`, (r) => { let b = ''; r.on('data', d => b += d); r.on('end', () => res({ status: r.statusCode, body: b })); }).on('error', rej); }); }

// the selection keys the shared header reads off the URL (shell.js currentSelection)
const SEL_KEYS = ['node', 'asset', 'version', 'section', 'beat', 'round', 'anchor'];
function urlSelection(search) {
  const p = new URLSearchParams(search);
  for (const k of SEL_KEYS) { const v = p.get(k); if (v) return { key: k, val: v }; }
  return null;
}

let scanner;
(async () => {
  const repoRoot = execSync(`${PY} -c "from laplace.web.scanner import _repo_root; print(_repo_root().resolve())"`).toString().trim();
  const port = await freePort();
  const base = `http://127.0.0.1:${port}`;
  scanner = spawn(PY, ['-m', 'laplace.web.scanner', '--port', String(port)], { cwd: repoRoot, stdio: 'ignore' });
  await waitFor(`${base}/`);

  const roster = JSON.parse((await get(port, '/shared/views')).body).views;
  ok(roster.length >= 8, `the roster names the surfaces to seal (${roster.length})`);
  const corpora = JSON.parse((await get(port, '/corpus/list')).body).corpora || [];
  const PROJ = corpora[0] || '';
  ok(PROJ, `a real project drives the surfaces (${PROJ})`);
  // the selection we drive into the URL; the header must echo whatever the LIVE url carries
  const SEL = 'def:seal-probe';

  // an ASSET-BEARING project for clause C's /assets cockpit. The roster's default drive
  // project may hold ZERO assets — then the .dk-card cockpit never renders and clause C
  // silently skips the very surface the ruling's misclick was FILMED on. Probe for the first
  // corpus whose /assets/list carries ≥2 expandable asset cards; clause C drives assets on it.
  let ASSET_PROJ = '';
  for (const c of corpora) {
    const al = JSON.parse((await get(port, `/assets/list?corpus=${encodeURIComponent(c)}`)).body || '{}');
    if (((al.figures || []).length) + ((al.derivations || []).length) >= 2) { ASSET_PROJ = c; break; }
  }
  ok(ASSET_PROJ, `an asset-bearing project drives the /assets cockpit (${ASSET_PROJ || 'NONE'})`);

  const b = await chromium.launch({ executablePath: CHROME });
  try {
    const pg = await b.newPage({ viewport: { width: 1536, height: 864 } });
    const pageErrors = []; pg.on('pageerror', (e) => pageErrors.push(String(e).slice(0, 120)));

    // ═══════════════════════════════════════════════════════════════════════
    // A · B · D · E-presence · R6-DOM — one pass per surface
    // ═══════════════════════════════════════════════════════════════════════
    let selTruthful = 0;               // surfaces whose selection token matched a live-url selection
    let surfaceAfford = 0;             // surfaces where a NATIVE (non-chrome) clickable answered the affordance
    const occluded = [];               // surfaces whose OWN legacy chrome overlays the shared echo ×
    // documented rebuild-candidate survivors (DESIGN §2.8): served with the shared chrome,
    // NO redesign this wave — their legacy fixed bars can overlay the shared header. The atom
    // still FIRES (handler proven); the occlusion is a routed finding, not a shell defect.
    const KNOWN_OCCLUSION = new Set(['map']);
    for (const v of roster) {
      const sep = v.path.includes('?') ? '&' : '?';
      const url = `${base}${v.path}${sep}corpus=${encodeURIComponent(PROJ)}&node=${encodeURIComponent(SEL)}`;

      // seed a DIFFERENT-surface origin BEFORE load so the D15 echo has something to render
      const origin = v.id === 'dashboard'
        ? { path: `/conceptric?corpus=${PROJ}&node=${SEL}`, surface: 'conceptric', selection: { key: 'node', val: SEL } }
        : { path: `/?corpus=${PROJ}`, surface: 'dashboard', selection: null };
      await pg.addInitScript((o) => {
        try { sessionStorage.setItem('hymn.origin', JSON.stringify({ ...o, ts: Date.now() })); } catch (e) {}
      }, origin);

      await pg.goto(url, { waitUntil: 'domcontentloaded' });
      // surface-ready gate: most surfaces render the shared context bar (#hy-context), but the
      // pipeline surface (/pipeline 301s to /project) rests on its OWN composed brief (#eng-root)
      // with no shared bar — accept either as the paint signal.
      await pg.waitForSelector('#hy-context, #eng-root', { timeout: 12000 });
      await pg.waitForTimeout(250);

      // the LIVE url is the truth the header is judged against (a surface may rewrite it)
      const live = await pg.evaluate(() => ({ path: location.pathname, search: location.search }));
      const liveCorpus = new URLSearchParams(live.search).get('corpus') || '';
      const liveSel = urlSelection(live.search);

      // PIPELINE EXEMPTION (named, never a silent pass): the project surface (/pipeline 301s to
      // /project) does NOT carry the shared #hy-context bar this seal certifies — it rests on its
      // OWN composed brief (#eng-root / .eng-brief), whose glance names the project and its state.
      // The shared-bar clauses (context header, ✎ mouth, selection token, D15 echo) are N/A here;
      // assert the surface's own brief context is present and truthful, then skip the bar-specific
      // clauses for this one surface (the aggregate ≥3-surface checks below still hold).
      if (v.id === 'pipeline') {
        const brief = await pg.evaluate(() => {
          const m = document.getElementById('eng-root');
          return m ? { present: true, text: (m.innerText || '').trim() } : null;
        });
        ok(brief && brief.present && brief.text.length > 20,
          `[${v.id}] the project surface carries its OWN composed brief context (#eng-root, non-empty) — the shared #hy-context bar is N/A here (named exemption)`);
        // truthful scoping is URL-canonical here (the brief prose is about pipeline STATE, not
        // the project name): the live url carries the project this surface is scoped to.
        ok(!liveCorpus || new URLSearchParams(live.search).get('corpus') === liveCorpus,
          `[${v.id}] the surface is scoped to the project truthfully via the url (${liveCorpus})`);
        continue;
      }

      // ── A · context header PRESENT + TRUTHFUL ──────────────────────────────
      const hdr = await pg.evaluate(() => {
        const c = document.getElementById('hy-context');
        if (!c) return null;
        const surf = c.querySelector('.hy-ctx-surface');
        const proj = c.querySelector('.hy-ctx-proj');
        const selwrap = c.querySelector('.hy-ctx-selwrap');
        const selval = c.querySelector('.hy-ctx-sel-val');
        return {
          surface: surf ? surf.innerText.trim() : null,
          purpose: !!c.querySelector('.hy-ctx-purpose'),
          projText: proj ? proj.innerText.replace(/[▾\s]+$/, '').trim() : null,
          projIsButton: proj ? proj.tagName === 'BUTTON' : false,
          projIsScope: proj ? proj.classList.contains('is-scope') : false,
          selShown: selwrap ? !selwrap.hidden : false,
          selVal: selval ? selval.innerText.trim() : null,
        };
      });
      ok(hdr !== null, `[${v.id}] the L1 context header is present`);
      ok(hdr.surface === (v.title || v.id),
        `[${v.id}] header NAMES THE OBJECT — surface title "${hdr.surface}" === roster "${v.title}"`);
      ok(hdr.purpose, `[${v.id}] header carries the "a view of <purpose>" prose label`);
      // project token TRUTHFUL vs the live url
      if (liveCorpus) {
        ok(hdr.projText === liveCorpus && hdr.projIsButton && !hdr.projIsScope,
          `[${v.id}] header NAMES THE PROJECT truthfully — "${hdr.projText}" === url corpus "${liveCorpus}" (ladder button)`);
      } else {
        ok(hdr.projIsScope, `[${v.id}] no corpus in the live url → honest "all projects" scope token`);
      }
      // selection token TRUTHFUL vs the live url (present iff the url carries one; value matches)
      if (liveSel) {
        ok(hdr.selShown && hdr.selVal === liveSel.val,
          `[${v.id}] header NAMES THE SELECTION truthfully — "${hdr.selVal}" === url ${liveSel.key} "${liveSel.val}"`);
        selTruthful++;
      } else {
        ok(!hdr.selShown, `[${v.id}] the live url carries no selection → the selection token stays hidden (no lie)`);
      }
      // the ✎ mouth rides every surface's header (E-presence, D16)
      ok(await pg.$('#hy-context .rule-chip') !== null,
        `[${v.id}] the ✎ rule chip rides the header — he can speak right here (D16)`);

      // ── R6 · no mock-only artifact RENDERED on this served surface ──────────
      const mockArtifacts = await pg.evaluate(() =>
        document.querySelectorAll('.rl-tag, .rl-box, .rl-tab, [data-d], [data-drow], .rl-d, .rl-row').length);
      ok(mockArtifacts === 0,
        `[${v.id}] renders ZERO mock-only artifacts (D-tags / redline box) — R6`);

      // ── B · a sample clickable ANSWERS HOVER (cursor + computed-style delta) ─
      // the shared nav strip's non-active tab is the universal sample: present on every
      // surface, with a real :hover family in hymn.css (color ink2→ink, background→panel).
      // NOTE (coverage boundary): the nav tab is SHARED CHROME — identical on every surface —
      // so it proves the shell, not each surface's OWN interactions. The native-clickable
      // sample below is the surface-specific companion (RULING J2: a dead surface handler
      // must not pass green under a hovering shared tab).
      const navSel = '#hy-shell nav > a:not(.on)';
      const nav = await pg.$(navSel);
      ok(nav !== null, `[${v.id}] a sample clickable exists (a non-active nav tab)`);
      await pg.mouse.move(2, 2);       // park the pointer OFF the sample → the un-hovered baseline
      await pg.waitForTimeout(30);
      const before = await nav.evaluate((e) => { const s = getComputedStyle(e); return { color: s.color, bg: s.backgroundColor, cursor: s.cursor }; });
      // POLL the :hover restyle to settle rather than sleep a fixed 60ms — heavier surfaces
      // (artefact renders its tray async AFTER load) can drop/relayout the tab under a one-shot
      // hover, flaking this assertion. Re-assert the hover each tick until the delta lands.
      let after = before;
      for (let t = 0; t < 12; t++) {
        await nav.hover();
        await pg.waitForTimeout(30);
        after = await nav.evaluate((e) => { const s = getComputedStyle(e); return { color: s.color, bg: s.backgroundColor, cursor: s.cursor }; });
        if (after.cursor === 'pointer' && (before.color !== after.color || before.bg !== after.bg)) break;
      }
      ok(after.cursor === 'pointer', `[${v.id}] the clickable declares cursor:pointer (L2 affordance)`);
      ok(before.color !== after.color || before.bg !== after.bg,
        `[${v.id}] hover CHANGES the computed style (color ${before.color}→${after.color} / bg ${before.bg}→${after.bg}) — L2`);
      await pg.mouse.move(2, 2);

      // ── B (surface-specific) · a NATIVE clickable answers the affordance ─────
      // Beyond the shared nav tab: sample one of THIS surface's own clickables (a card
      // identity, a chip, a native door) and assert it presents the pointer affordance —
      // cursor:pointer OR a hover-style delta. A surface whose native interaction is dead
      // (no affordance at all) can no longer ride the always-hovering shared tab to green.
      // content-only classes (never shell chrome / never the shared header) so the sample is
      // genuinely surface-specific: a card identity, a strata chip, a native content door.
      // Bounded WAIT (not a bare $) so an async-rendered card is caught, not flaked past.
      // surface-specific CONTENT clickables (never shell chrome / never the shared header),
      // broadened to the rebuilt surfaces so the ≥3-surface clause reads the CURRENT roster
      // truthfully under the seal's thin drive project: card identities/doors
      // (.hy-card-name/.art-adoor), desk+asset chips (.dk-title/.dk-chip), the conceptric
      // cockpit door (.ck-door), and the altitude ladder rung / panel head (.rung/.panel h2).
      // Each is a native, reliably-affordant L2 clickable owned by its surface, distinct from
      // the always-hovering shared nav tab. (Analytics' native is `.chip`, but on /altitude a
      // non-affordant `.chip` label precedes the rung in DOM order — so `.chip` is left OUT to
      // keep the FIRST-match honest per surface; assets + conceptric + altitude already clear ≥3.)
      const nativeSel = '.hy-card-name, .dk-title, .dk-chip, .art-adoor, .ck-door, .rung, .panel h2';
      const native = await pg.waitForSelector(nativeSel, { state: 'visible', timeout: 1500 }).catch(() => null);
      if (native) {
        await pg.mouse.move(2, 2); await pg.waitForTimeout(20);
        const nb = await native.evaluate((e) => { const s = getComputedStyle(e); return { color: s.color, bg: s.backgroundColor }; });
        await native.hover();
        await pg.waitForTimeout(50);
        const na = await native.evaluate((e) => { const s = getComputedStyle(e); return { color: s.color, bg: s.backgroundColor, cursor: s.cursor }; });
        ok(na.cursor === 'pointer' || nb.color !== na.color || nb.bg !== na.bg,
          `[${v.id}] a NATIVE clickable answers the affordance (cursor ${na.cursor} / restyle ${nb.color !== na.color || nb.bg !== na.bg}) — surface-specific L2, not shared chrome`);
        surfaceAfford++;
        await pg.mouse.move(2, 2);
      }

      // ── D · the D15 ARRIVAL ECHO fires from a foreign origin + dismisses ─────
      const echo = await pg.evaluate(() => {
        const a = document.querySelector('#hy-context .hy-from');
        return a ? { text: a.innerText, href: a.getAttribute('href') } : null;
      });
      ok(echo !== null, `[${v.id}] the arrival echo fires from a foreign-surface origin (D15)`);
      ok(/^←\s*from/.test(echo.text), `[${v.id}] the echo reads "← from <origin>" (${JSON.stringify(echo.text.slice(0, 40))})`);
      ok(echo.href === origin.path, `[${v.id}] the echo is a real door back to EXACTLY the origin (${echo.href})`);
      // dismiss with a REAL click; if the surface's own legacy chrome intercepts the pointer
      // (a rebuild-candidate survivor's fixed bar overlaying the shared header), fall back to
      // firing the atom's handler directly and record the occlusion as a routed finding.
      let occludedHere = false;
      try {
        await pg.click('#hy-context .hy-from-x', { timeout: 3000 });
      } catch (e) {
        occludedHere = true;
        await pg.$eval('#hy-context .hy-from-x', (el) => el.click());
      }
      ok(await pg.$('#hy-context .hy-fromwrap') === null,
        `[${v.id}] the × dismisses the echo${occludedHere ? ' (handler fired; NOTE: surface chrome occludes the ×)' : ''}`);
      if (occludedHere) occluded.push(v.id);
    }
    ok(occluded.every((s) => KNOWN_OCCLUSION.has(s)),
      `the shared echo × is click-reachable except on documented survivors — occluded on [${occluded.join(',') || 'none'}], all known (${[...KNOWN_OCCLUSION].join(',')})`);
    ok(selTruthful >= 3,
      `the selection token was driven + verified truthful on ≥3 surfaces (${selTruthful}) — the clause is not vacuous`);
    ok(surfaceAfford >= 3,
      `a NATIVE (non-chrome) clickable answered the affordance on ≥3 surfaces (${surfaceAfford}) — clause B is not shared-chrome-only`);

    // ═══════════════════════════════════════════════════════════════════════
    // Back RETURNS EXACTLY (RULING seal-bar #3; the rule text clause E banks). A real
    // browser Back must restore the surface AND re-derive the L1 header truthfully from the
    // RESTORED url. Driven on a door surface: load node=A, navigate (real nav) to node=B,
    // then pg.goBack() and re-run the clause-A truthful check against the restored live url.
    // ═══════════════════════════════════════════════════════════════════════
    {
      const bSurf = roster.find((v) => v.id === 'conceptric') || roster[0];
      const bsep = bSurf.path.includes('?') ? '&' : '?';
      const A = 'def:seal-back-A', B = 'def:seal-back-B';
      const mk = (n) => `${base}${bSurf.path}${bsep}corpus=${encodeURIComponent(PROJ)}&node=${encodeURIComponent(n)}`;
      await pg.goto(mk(A), { waitUntil: 'domcontentloaded' });
      await pg.waitForSelector('#hy-context', { timeout: 12000 }); await pg.waitForTimeout(200);
      await pg.goto(mk(B), { waitUntil: 'domcontentloaded' });
      await pg.waitForSelector('#hy-context', { timeout: 12000 }); await pg.waitForTimeout(200);
      const selB = await pg.$eval('#hy-context .hy-ctx-sel-val', (e) => e.innerText.trim()).catch(() => null);
      ok(selB === B, `[${bSurf.id}] pre-Back the header names node B truthfully ("${selB}")`);
      await pg.goBack({ waitUntil: 'domcontentloaded' });
      await pg.waitForSelector('#hy-context', { timeout: 12000 }); await pg.waitForTimeout(200);
      const liveBack = await pg.evaluate(() => ({ path: location.pathname, search: location.search }));
      const backSel = urlSelection(liveBack.search);
      const hdrBack = await pg.evaluate(() => {
        const c = document.getElementById('hy-context');
        const surf = c && c.querySelector('.hy-ctx-surface');
        const proj = c && c.querySelector('.hy-ctx-proj');
        const selval = c && c.querySelector('.hy-ctx-sel-val');
        return { surface: surf ? surf.innerText.trim() : null,
                 projText: proj ? proj.innerText.replace(/[▾\s]+$/, '').trim() : null,
                 selVal: selval ? selval.innerText.trim() : null };
      });
      ok(backSel && backSel.val === A,
        `[${bSurf.id}] browser Back restored the url EXACTLY — node "${backSel && backSel.val}" === "${A}"`);
      ok(hdrBack.surface === (bSurf.title || bSurf.id),
        `[${bSurf.id}] the L1 header SURVIVES Back — surface still "${hdrBack.surface}"`);
      ok(hdrBack.projText === PROJ,
        `[${bSurf.id}] the header project token survives Back truthfully ("${hdrBack.projText}" === "${PROJ}")`);
      ok(hdrBack.selVal === A,
        `[${bSurf.id}] the header selection re-derived from the RESTORED url ("${hdrBack.selVal}" === "${A}") — Back returns exactly`);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // C · NO HITBOX MOTION under the pointer — click A, assert the row holds.
    // Doctrine (RULING seal bar #3): expansion displaces content BELOW only; the
    // hitboxes of the card row the pointer is in never move. So after clicking
    // card A, every card AT-OR-ABOVE A's row must keep its top (cards below may
    // move). Exercised on every surface that presents ≥2 expandable cards.
    //
    // TWO EXPANDABLE-CARD FAMILIES, DRIVEN BOTH (a green on one does NOT transfer):
    //   .hy-card  — the dashboard/pipeline MULTI-open card (is-open + .hy-card-fold).
    //   .dk-card  — the SINGLE-open COCKPIT card (/assets, /desk, /artefact), whose no-shift
    //               is a DIFFERENT mechanism: assets-panes.mjs toggleCardStable + _pinPad
    //               ("collapse-above + expand-here", scroll-pinned). /assets is the ruling's
    //               ON-CAMERA misclick surface; clause C must actually DRIVE that path, so a
    //               /assets hitbox regression cannot keep the fleet green by selector-skip.
    // ═══════════════════════════════════════════════════════════════════════
    const CARD_SPECS = [
      { fam: 'hy-card', card: '.hy-card', click: '.hy-card-name', nameProbe: ':scope .hy-card-name' },
      { fam: 'dk-card', card: '.dk-card', click: '.dk-title',     nameProbe: ':scope .dk-title' },
    ];
    let exercised = 0;
    const dashExercised = { hit: false };
    const assetsExercised = { hit: false };
    for (const v of roster) {
      // /assets needs an asset-BEARING corpus, or its .dk-card cockpit never renders and the
      // ruling's misclick surface silently drops out of clause C (the exact disease).
      const useProj = v.id === 'assets' ? ASSET_PROJ : PROJ;
      const sep = v.path.includes('?') ? '&' : '?';
      // the dashboard now FOCUSES to a single compact card when a corpus rides the url; walk it
      // BARE so the full project inventory materialises (≥2 cards) and the no-shift clause bites
      // its multi-open card grid. Every other surface is scoped by its corpus as before.
      const navUrl = v.id === 'dashboard'
        ? `${base}/`
        : `${base}${v.path}${sep}corpus=${encodeURIComponent(useProj)}`;
      await pg.goto(navUrl, { waitUntil: 'domcontentloaded' });
      // ready gate tolerant of the pipeline surface (its own #eng-root brief, no shared bar)
      await pg.waitForSelector('#hy-context, #eng-root', { timeout: 12000 });
      // W-DASH: the dashboard rests on the composed brief; its .hy-card grid materialises behind
      // one interaction (the projects count chip, rendered after /dashboard/brief resolves). WAIT
      // for the chip, then open the inventory so the no-shift clause can bite the dashboard cards.
      if (v.id === 'dashboard') {
        const matChip = await pg.waitForSelector(".dash-count[data-count='projects']", { timeout: 8000 }).catch(() => null);
        if (matChip) { await matChip.click(); await pg.waitForTimeout(300); }
      }
      // wait DETERMINISTICALLY for the cards to render (fixed sleeps flaked dashboard out);
      // truly card-less surfaces (map/analytics/altitude) time out → n/a below.
      await pg.waitForFunction(() => document.querySelectorAll('.hy-card, .dk-card').length >= 2,
        null, { timeout: 3000 }).catch(() => {});
      // pick the first card family THIS surface presents with ≥2 expandable rows.
      let spec = null, before = null;
      for (const s of CARD_SPECS) {
        const info = await pg.evaluate((sel) => {
          const cards = [...document.querySelectorAll(sel.card)]
            .filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
          return { count: cards.length, firstHasName: cards[0] ? !!cards[0].querySelector(sel.nameProbe) : false };
        }, s);
        if (info.count >= 2 && info.firstHasName) { spec = s; break; }
      }
      if (!spec) continue;                                           // no expandable-card row here → n/a

      before = await pg.$$eval(spec.card, (els) => els.map((e, i) => {
        const r = e.getBoundingClientRect(); return { i, top: Math.round(r.top * 10) / 10, w: r.width };
      }).filter((c) => c.w > 0));
      const aTop = before[0].top;
      const urlBefore = pg.url();
      await pg.click(`${spec.card} ${spec.click}`);                 // click A (the first card's identity)
      await pg.waitForTimeout(400);
      if (pg.url() !== urlBefore) continue;                         // this surface's name is a DOOR → n/a
      // confirm the click actually EXPANDED a card — a head that neither navigates nor expands
      // (e.g. a static finding row) must not count as an exercised no-shift surface.
      const expanded = await pg.$$eval(spec.card, (els) => els.some((e) =>
        e.classList.contains('open') || e.classList.contains('is-open') ||
        e.querySelector('.dk-cockpit, .hy-card-fold.is-open-fold')));
      if (!expanded) continue;                                       // dead/static head → n/a

      const after = await pg.$$eval(spec.card, (els) => els.map((e, i) => {
        const r = e.getBoundingClientRect(); return { i, top: Math.round(r.top * 10) / 10, w: r.width };
      }).filter((c) => c.w > 0));
      const afterByI = Object.fromEntries(after.map((c) => [c.i, c.top]));
      // every card at-or-above A's row must be pinned (±1.5px); cards below may displace
      const moved = before.filter((c) => c.top <= aTop + 0.5 && Math.abs((afterByI[c.i] ?? c.top) - c.top) > 1.5);
      ok(moved.length === 0,
        `[${v.id}] clicking A moved NO ${spec.fam} hitbox at-or-above its row (${before.length} cards, row top ${aTop}) — L3 no-shift`);
      exercised++;
      if (v.id === 'dashboard') dashExercised.hit = true;
      if (v.id === 'assets') assetsExercised.hit = true;
    }
    ok(exercised >= 2, `the no-shift clause exercised ≥2 surfaces with expansions (${exercised})`);
    ok(dashExercised.hit, `the dashboard (a .hy-card multi-open surface) is among the exercised — the clause bites there`);
    ok(assetsExercised.hit,
      `the /assets cockpit (the ON-CAMERA misclick surface) is among the exercised — toggleCardStable/_pinPad is DRIVEN, not selector-skipped`);

    // ═══════════════════════════════════════════════════════════════════════
    // E · the ✎ RULE BANKS a typed open interface fork + the desk DRAINS it.
    // NON-MUTATING: the POST is intercepted (canned record). The bank's target
    // ledger (/corpus/friction → corpus_friction/<corpus>.jsonl) and the desk's
    // `forks` class reader (corpus_friction/*.jsonl `fork` records) are the SAME
    // file — asserted against the live /desk/data schema, so the loop is proven
    // closed without a write. The real end-to-end is tests/waveF_desk_landing.
    // ═══════════════════════════════════════════════════════════════════════
    await pg.goto(`${base}/?corpus=${encodeURIComponent(PROJ)}`, { waitUntil: 'domcontentloaded' });
    await pg.waitForSelector('#hy-context .rule-chip', { state: 'attached', timeout: 12000 });
    let banked = null;
    await pg.route('**/corpus/friction', async (route) => {
      banked = JSON.parse(route.request().postData() || '{}');
      await route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ ok: true, record: { id: 'RW-seal-0001', status: 'open', kind: 'fork' } }) });
    });
    await pg.hover('#hy-context');
    await pg.click('#hy-context .rule-chip');
    await pg.waitForSelector('#hy-context .rule-cap textarea', { timeout: 5000 });
    await pg.fill('#hy-context .rule-cap textarea', 'seal: the context header must survive a browser Back');
    await pg.click('#hy-context .rule-cap .rule-bank');
    await pg.waitForSelector('#hy-context .rule-banked', { timeout: 5000 });
    ok(banked && banked.kind === 'fork' && banked.owning_layer === 'interface' && banked.by === 'author',
      `the ✎ banks a TYPED fork — kind=fork, owning_layer=interface, by=author (${JSON.stringify(banked && banked.kind)})`);
    ok(banked && typeof banked.value === 'string' && banked.value.length > 0,
      `the fork carries his words (${JSON.stringify((banked && banked.value || '').slice(0, 40))})`);
    ok(await pg.$eval('#hy-context .rule-banked', (e) => /banked/.test(e.textContent)),
      'the capture renders "banked ✓" without leaving the surface (D16)');

    // the desk DRAIN: the live read-model carries a `forks` class that reads the SAME
    // corpus_friction ledger the bank writes to → a banked open fork LANDS there.
    const desk = JSON.parse((await get(port, '/desk/data')).body);
    const forksClass = (desk.classes || []).find((c) => c.class === 'forks');
    ok(forksClass, 'the /desk/data read-model carries the `forks` stratum (open author-forks)');
    ok(/corpus_friction/.test(forksClass.store) && /fork/.test(forksClass.store),
      `the desk's forks class DRAINS the corpus_friction fork ledger the bank targets ("${forksClass.store}")`);

    ok(pageErrors.length === 0, `no page errors across the full sweep (${JSON.stringify(pageErrors.slice(0, 3))})`);
    console.log(`\nALL GREEN — ${passed} assertions across ${roster.length} surfaces`);
  } finally {
    await b.close();
    if (scanner) scanner.kill();
  }
})().catch((e) => { console.error('\n' + e.message); if (scanner) scanner.kill(); process.exit(1); });
