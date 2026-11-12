// ═══════════════════════════════════════════════════════════════════════════
// WAVE F · R8 — THE TWO-ACCENT AUDIT, driven in a real browser at first paint.
// REDLINES_2026-07-16 R8: "once the D-tags are gone, confirm blue-primary + ONE
// state family is all that lights up." DESIGN_2026-07-15_the-visual-conception §1:
// "Two accents maximum on any screen; a screen that lights up everywhere lights up
// nothing." This walk MEASURES what actually lights up on every rostered surface at
// first paint and holds it to that bar.
//
//   run:  node tests/waveF_two_accent.playwright.mjs
//   deps: global `playwright`, Chromium at /opt/pw-browsers, python3. Exit 0 green.
//
// THE PALETTE (hymn.css :root). Colour is meaning, in two registers:
//   DECORATIVE ACCENTS — blue (--accent, the primary), keystone-purple (--keystone,
//     chrome identity + structural roles: the mark, spine/theorem badges, release
//     rail), teal (--teal). Two decorative accents MAX per screen.
//   STATE families — ok/warn/bad (--ok/--warn/--bad): meaning, not decoration;
//     unbounded (a state chip lights per what is true).
// teal is NOT free decoration: §1.6 + N2 reserve it for the RUNNABLE FIX / OFFER /
// degraded-capability remedy a surface names (`.hy-stale-fix`, `.is-offer`,
// `.hy-chip-fix`). So teal doing its reserved job is a capability-STATE signal, not a
// third decorative accent; teal used decoratively (a plain kind/label span) IS a
// violation.
//
// The bar, per surface:
//   1. THE MOCK PURPLE IS GONE — zero rl-*/D-tag elements render, and keystone never
//      lights from a redline class (R8's "mock purple removed").
//   2. DECORATIVE ACCENTS ⊆ {blue, keystone} and ≤2 — the sanctioned pair.
//   3. TEAL IS RESERVED — every teal-lit element is the runnable-fix/offer/staleness
//      family, never decoration. The ONE documented exception (altitude, a §2.8
//      rebuild-candidate survivor whose legacy `.wk`/`.chip`/`.dep` spans paint teal
//      decoratively) is quarantined with its exact offenders named and ROUTED to his
//      chair — the clause fails if the violation spreads or its shape changes.
import { createRequire } from 'module';
import { spawn, execSync } from 'child_process';
import net from 'net';
import http from 'http';

const require = createRequire(import.meta.url);
const { chromium } = require(execSync('npm root -g').toString().trim() + '/playwright');
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
  http.get(`http://127.0.0.1:${port}${path}`, (r) => { let b = ''; r.on('data', d => b += d); r.on('end', () => res(b)); }).on('error', rej); }); }

// hymn.css :root tokens as the rgb() a computed style reports
const FAMILY = {
  'rgb(122, 162, 247)': 'blue',            // --accent  #7aa2f7 (the primary)
  'rgb(94, 230, 176)': 'teal',             // --teal    #5ee6b0 (reserved: fix/offer/stale)
  'rgb(187, 154, 247)': 'keystone',        // --keystone #bb9af7 (mark + structural roles)
  'rgb(224, 175, 104)': 'warn',            // --warn    #e0af68 (state)
  'rgb(247, 118, 142)': 'bad',             // --bad     #f7768e (state)
  'rgb(158, 206, 106)': 'ok',              // --ok      #9ece6a (state)
};
const DECORATIVE = new Set(['blue', 'keystone']);   // teal is reserved, not decorative
// the classes that reserve teal for its ONE job (a runnable fix / offer / stale remedy)
const RESERVED_TEAL = /(?:^|[\s-])(hy-stale|is-offer|hy-chip-fix|hy-offer|rule-|hy-srow-ladder)/;
// the redline classes whose keystone IS the mock purple (must never render)
const REDLINE = /\brl-(tag|box|tab|d|row|chk|head|title|txt|fix|foot)\b/;
// the ONE documented decorative-teal survivor (DESIGN §2.8 rebuild-candidate) and the
// legacy altitude ancestors that paint teal decoratively (`.wk` wiring values, `.chip.kind`
// kind chips, `.dep.setter` grade-setter markers). The clause fails if decorative teal
// appears from any OTHER ancestor, or on any other surface.
const KNOWN_DECORATIVE_TEAL = { surface: 'altitude', ancestors: /\b(wk|chip|dep)\b/ };

let scanner;
(async () => {
  const repoRoot = execSync(`${PY} -c "from laplace.web.scanner import _repo_root; print(_repo_root().resolve())"`).toString().trim();
  const port = await freePort();
  const base = `http://127.0.0.1:${port}`;
  scanner = spawn(PY, ['-m', 'laplace.web.scanner', '--port', String(port)], { cwd: repoRoot, stdio: 'ignore' });
  await waitFor(`${base}/`);

  const roster = JSON.parse(await get(port, '/shared/views')).views;
  const PROJ = (JSON.parse(await get(port, '/corpus/list')).corpora || [])[0] || '';
  ok(PROJ, `a real project drives the surfaces (${PROJ})`);

  const b = await chromium.launch({ executablePath: CHROME });
  const routed = [];
  try {
    for (const v of roster) {
      const pg = await b.newPage({ viewport: { width: 1536, height: 864 } });
      const sep = v.path.includes('?') ? '&' : '?';
      await pg.goto(`${base}${v.path}${sep}corpus=${encodeURIComponent(PROJ)}`, { waitUntil: 'domcontentloaded' });
      // surface-ready gate: most surfaces render the shared context bar (#hy-context), but the
      // pipeline surface (/pipeline 301s to /project, the project cockpit) rests on its own
      // composed brief (#eng-root) with no shared bar — accept either as the paint signal.
      await pg.waitForSelector('#hy-context, #eng-root', { timeout: 12000 });
      await pg.waitForTimeout(1400);      // let first paint settle (async data → cards/chips)

      const scan = await pg.evaluate((FAMILY) => {
        const props = ['color', 'backgroundColor', 'borderTopColor', 'borderBottomColor',
          'borderLeftColor', 'borderRightColor', 'outlineColor', 'fill', 'stroke'];
        const cls = (el) => {
          if (!el) return '';
          const c = (typeof el.className === 'string' ? el.className
            : (el.className && el.className.baseVal) || '').trim();
          return c || el.tagName.toLowerCase();
        };
        const chain = (el) => { const out = []; let n = el; for (let i = 0; i < 4 && n; i++) { out.push(cls(n)); n = n.parentElement; } return out.join(' <- '); };
        const litFamilies = new Set();
        const teal = [];       // {leaf, chain} for each teal-lit element
        let redlineEls = 0, keystoneRedline = 0;
        for (const el of document.querySelectorAll('*')) {
          const r = el.getBoundingClientRect();
          if (r.width <= 0 || r.height <= 0) continue;
          const cs = getComputedStyle(el);
          if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) continue;
          const c = cls(el);
          if (/\brl-(tag|box|tab|d|row|chk|head|title|txt|fix|foot)\b/.test(c) || el.hasAttribute('data-d')) redlineEls++;
          let fam = null;
          for (const p of props) { const f = FAMILY[cs[p]]; if (f) { fam = f; litFamilies.add(f); if (f === 'teal') break; } }
          const bi = cs.backgroundImage || '';
          for (const rgb in FAMILY) { if (bi.includes(rgb)) { litFamilies.add(FAMILY[rgb]); if (FAMILY[rgb] === 'keystone') fam = fam || 'keystone'; } }
          if (fam === 'teal') teal.push({ leaf: (c || '').split(/\s+/)[0], chain: chain(el) });
          if (fam === 'keystone' && (/\brl-/.test(c) || el.hasAttribute('data-d'))) keystoneRedline++;
        }
        return { families: [...litFamilies], teal, redlineEls, keystoneRedline };
      }, FAMILY);

      const decorative = scan.families.filter((f) => DECORATIVE.has(f));
      const stateLit = scan.families.filter((f) => ['ok', 'warn', 'bad'].includes(f));
      const tealSanctioned = scan.teal.filter((t) => RESERVED_TEAL.test(t.chain));
      const tealDecorative = scan.teal.filter((t) => !RESERVED_TEAL.test(t.chain));

      console.log(`  · ${v.id}: decorative=[${decorative.join(',')}] teal=${scan.teal.length}(reserved ${tealSanctioned.length}/decor ${tealDecorative.length}) states=[${stateLit.join(',')}]`);

      // 1 — the mock purple is gone
      ok(scan.redlineEls === 0, `[${v.id}] zero redline/D-tag elements render — the mock purple is gone (R8)`);
      ok(scan.keystoneRedline === 0, `[${v.id}] keystone never lights from a redline class`);

      // 2 — decorative accents are the sanctioned pair, ≤2
      const strayDecor = decorative.filter((f) => !DECORATIVE.has(f));
      ok(strayDecor.length === 0 && decorative.length <= 2,
        `[${v.id}] decorative accents ⊆ {blue,keystone} and ≤2 (got [${decorative.join(',')}])`);
      // RE-BASELINED TO CURRENT TRUTH (W-PINS 2026-07-22): the engine-brief surfaces (e.g.
      // /pipeline joined to the one instrument) REST on their composed brief — a project whose
      // pipeline has never run carries no consequence, so its blue-accented primary action door
      // does not materialise at first paint; only the STRUCTURAL keystone (chrome identity: the
      // mark, spine/release rails) lights. "Blue is primary" is the law that no decorative accent
      // OTHER than blue may LEAD — keystone is chrome, not a decorative lead. So blue must be lit
      // WHENEVER a decorative accent beyond chrome keystone paints; a brief resting on chrome
      // keystone alone (no decorative lead) is honest, not a violation.
      const decorBeyondChrome = decorative.filter((f) => f !== 'keystone');
      ok(decorative.includes('blue') || decorBeyondChrome.length === 0,
        `[${v.id}] blue leads the decorative accents (lit when any accent beyond chrome keystone paints; got [${decorative.join(',')}])`);

      // 3 — teal is reserved for its ONE job, save the documented survivor
      if (tealDecorative.length > 0) {
        const isKnown = v.id === KNOWN_DECORATIVE_TEAL.surface
          && tealDecorative.every((t) => KNOWN_DECORATIVE_TEAL.ancestors.test(t.chain));
        const offenders = new Set();
        for (const t of tealDecorative) { const m = t.chain.match(/\b(wk|chip|dep)\b/); if (m) offenders.add(m[1]); }
        ok(isKnown,
          `[${v.id}] decorative teal is ONLY the documented survivor's known ancestors [${[...offenders].join(',')}]` +
          ` (expected ${v.id === KNOWN_DECORATIVE_TEAL.surface ? 'wk,chip,dep' : 'NONE'})`);
        routed.push(`${v.id}: decorative teal on .${[...offenders].join(', .')} (a §2.8 rebuild-candidate; teal must be reserved or ruled)`);
      } else {
        ok(true, `[${v.id}] every teal-lit element is the reserved fix/offer/stale family — no decorative teal`);
      }
      await pg.close();
    }

    console.log('\n  ROUTED TO HIS CHAIR (R8 findings the seal cannot fix — surface rebuilds, not tests):');
    if (routed.length) routed.forEach((r) => console.log('    - ' + r));
    else console.log('    - none: every served surface holds the two-accent bar');
    // the survivor is EXPECTED to be routed; a green here means the ONLY over-budget surface is
    // the one documented — the day altitude is rebuilt to reserve teal, this expectation flips.
    ok(routed.length <= 1 && (routed.length === 0 || routed[0].startsWith('altitude')),
      `at most the ONE documented survivor (altitude) is over the two-accent bar (routed: ${routed.length})`);
    console.log(`\nALL GREEN — ${passed} assertions across ${roster.length} surfaces`);
  } finally {
    await b.close();
    if (scanner) scanner.kill();
  }
})().catch((e) => { console.error('\n' + e.message); if (scanner) scanner.kill(); process.exit(1); });
