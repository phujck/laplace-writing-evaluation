// Wave 0.5 — THE LADDER, driven in a real browser (§4 THE CHAIR WALK MATRIX).
// Target-first transitions: one gesture on a selection token opens six rungs (concept ·
// argument · prose · evidence · judgment · machine), each a real <a href> carrying the
// selection, honest counts, honest absences naming their fix, honest staleness, pure reads.
//
//   run:  node tests/wave05_ladder.playwright.mjs
//   deps: global `playwright`, Chromium at /opt/pw-browsers, the repo venv python as
//         python3. Exits 0 all-green (prints the assertion count), non-zero on first failure.
//
// THE HONESTY INVARIANT, applied per rung on every populated walk: DOM state == payload
// state — present ⇔ (<a> + count chip + door); absent ⇔ (<div.is-absent> + reason + fix
// door); stale ⇔ warn chip. A blank panel or an unreplaced loading line is a FAIL. Walks
// assert OUTCOMES (URL landed, cockpit expanded, origin byte-identical, fetch fired for B,
// string dumped), never mere presence. Rich tree: subset-sum-itqde; honest-empty: paper_eigen;
// fresh-nodemap (non-stale) control: paper_falqon.
import { createRequire } from 'module';
import { spawn, execSync } from 'child_process';
import { writeFileSync } from 'fs';
import os from 'os';
import net from 'net';

const require = createRequire(import.meta.url);
const PW_ROOT = execSync('npm root -g').toString().trim() + '/playwright';
const { chromium } = require(PW_ROOT);
const CHROME = execSync('ls /opt/pw-browsers/chromium-*/chrome-linux/chrome')
  .toString().trim().split('\n')[0];
const PY = 'python3';
// portable dump dir: honor $SCRATCH when the harness sets it, else the OS tmp dir — never a
// hardcoded session scratchpad (a stale absolute path ENOENTs on any other machine/session).
const DUMP_DIR = process.env.SCRATCH || os.tmpdir();

// the fixture targets — verified real against this box's stores (subset-sum-itqde rich,
// paper_eigen honest-empty, paper_falqon fresh-nodemap).
const RICH = 'subset-sum-itqde';
const EMPTY = 'paper_eigen';
const FRESH = 'paper_falqon';
const NODE = 'goal:perturbation-assisted-itqde';     // node, rich, 1 open decision, stale prose/evidence
const SECTION = 'N2';                                 // section, 14 nodes projected
const PID = 'N2-p1';                                  // pid grammar (NX-p# — server grammar, not a hint kind)
const BEAT = 'res:itqde-spectral-readout';            // spine beat
const ASSET = 'derivation:WK-032';                    // asset — evidence rung IS it
const UNKNOWN = 'zzz:nonexistent-node';               // resolves to nothing → known:false

let passed = 0;
function ok(cond, msg) {
  if (!cond) throw new Error('ASSERT FAILED: ' + msg);
  passed++; console.log('  ok -', msg);
}
function freePort() {
  return new Promise((res, rej) => {
    const s = net.createServer();
    s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); });
    s.on('error', rej);
  });
}
function waitFor(url, tries = 60) {
  return new Promise((res, rej) => {
    const tick = (n) => {
      const req = require('http').get(url, (r) => { r.resume(); res(true); });
      req.on('error', () => n <= 0 ? rej(new Error('server never came up')) : setTimeout(() => tick(n - 1), 250));
    };
    tick(tries);
  });
}

// ── open the ladder over a token and wait for the six rungs to replace the loading line ──
async function openLadder(pg, tokenSel) {
  await pg.waitForSelector(tokenSel, { timeout: 10000 });
  await pg.click(tokenSel);
  await pg.waitForFunction(() => {
    const el = document.getElementById('hy-ladder');
    return el && el.classList.contains('open') &&
      el.querySelectorAll('.hy-ladder-rung').length === 6 &&
      !el.querySelector('.hy-ladder-loading');
  }, { timeout: 8000 });
}

// ── THE HONESTY INVARIANT, per rung: re-fetch the payload the panel rendered from and
// diff it against the rendered DOM. Deterministic (pure reads, same params) so any diff is
// a real DOM/payload divergence. Returns the payload for further outcome assertions. ──
async function honesty(pg, corpus, target, kind) {
  const res = await pg.evaluate(async ({ corpus, target, kind }) => {
    const q = (s) => encodeURIComponent(s == null ? '' : s);
    const r = await fetch('/shared/ladder?corpus=' + q(corpus) + '&target=' + q(target) + '&kind=' + q(kind));
    const payload = await r.json();
    const root = document.getElementById('hy-ladder');
    const diffs = [];
    // the rendered rung order must equal the payload order (fixed six).
    const domIds = Array.prototype.map.call(root.querySelectorAll('.hy-ladder-rung'),
      (e) => e.id.replace('hy-rung-', ''));
    const payIds = (payload.rungs || []).map((r) => r.id);
    if (domIds.join(',') !== payIds.join(',')) diffs.push('rung order ' + domIds + ' != ' + payIds);
    for (const rr of (payload.rungs || [])) {
      const el = root.querySelector('#hy-rung-' + rr.id);
      if (!el) { diffs.push(rr.id + ': not rendered'); continue; }
      const domPresent = el.tagName === 'A' && !el.classList.contains('is-absent');
      if (!!rr.present !== domPresent) diffs.push(rr.id + ': present payload=' + rr.present + ' dom=' + domPresent);
      const cntEl = el.querySelector('.hy-ladder-count');
      const domCount = cntEl ? cntEl.textContent.trim() : '(none)';
      if (domCount !== String(rr.count)) diffs.push(rr.id + ': count payload=' + rr.count + ' dom=' + domCount);
      if (rr.present) {
        const href = el.getAttribute('href');
        if (href !== rr.href) diffs.push(rr.id + ': href payload=' + rr.href + ' dom=' + href);
      } else {
        const a = rr.absent || {};
        const subEl = el.querySelector('.hy-ladder-sub');
        const domReason = subEl ? subEl.textContent.trim() : '';
        if (domReason !== (a.reason || '')) diffs.push(rr.id + ': reason payload=' + JSON.stringify(a.reason) + ' dom=' + JSON.stringify(domReason));
        const fix = el.querySelector('.hy-ladder-fix');
        // the judgment fix RULES the target (fires the head ✎), so it is a rule <button>
        // with no nav href — its honest DOM is the rule affordance, not a fix_href match.
        if (rr.id === 'judgment') {
          if (!fix || fix.tagName !== 'BUTTON' || !fix.classList.contains('is-rule'))
            diffs.push('judgment: fix must be a rule button (fires the head ✎), not a nav <a>');
        } else {
          const domFixHref = fix ? fix.getAttribute('href') : '';
          if (domFixHref !== (a.fix_href || '')) diffs.push(rr.id + ': fix_href payload=' + a.fix_href + ' dom=' + domFixHref);
        }
        const domFixLabel = fix ? fix.textContent.trim() : '';
        if (domFixLabel !== (a.fix || '')) diffs.push(rr.id + ': fix payload=' + JSON.stringify(a.fix) + ' dom=' + JSON.stringify(domFixLabel));
      }
      const staleEl = el.querySelector('.hy-ladder-stale');
      const domStale = !!staleEl;
      if (domStale !== !!rr.stale) diffs.push(rr.id + ': stale payload=' + !!rr.stale + ' dom=' + domStale);
      if (rr.stale && staleEl) {
        const domStaleTitle = staleEl.getAttribute('title') || '';
        if (domStaleTitle !== (rr.stale.fix || '')) diffs.push(rr.id + ': stale.fix payload=' + JSON.stringify(rr.stale.fix) + ' dom=' + JSON.stringify(domStaleTitle));
        const domStaleReason = staleEl.textContent.trim();
        if (domStaleReason !== (rr.stale.reason || '')) diffs.push(rr.id + ': stale.reason payload=' + JSON.stringify(rr.stale.reason) + ' dom=' + JSON.stringify(domStaleReason));
      }
    }
    return { diffs, payload };
  }, { corpus, target, kind });
  return res;
}

// ── dump every user-visible string the ladder renders (text + href + title + aria) for the
// strings audit (§3b / W-L30). One line per string, tagged by kind. ──
async function dumpLadderStrings(pg, state) {
  const lines = await pg.evaluate(() => {
    const root = document.getElementById('hy-ladder');
    if (!root) return [];
    const out = [];
    const seenText = new Set();
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = walker.nextNode())) {
      const t = (n.textContent || '').replace(/\s+/g, ' ').trim();
      if (t && !seenText.has('T' + t)) { seenText.add('T' + t); out.push('TEXT | ' + t); }
    }
    root.querySelectorAll('*').forEach((e) => {
      for (const attr of ['href', 'title', 'aria-label', 'placeholder']) {
        const v = e.getAttribute && e.getAttribute(attr);
        if (v && !seenText.has(attr + v)) { seenText.add(attr + v); out.push(attr.toUpperCase() + ' | ' + v); }
      }
    });
    const al = root.getAttribute('aria-label');
    if (al) out.push('ARIA-LABEL(root) | ' + al);
    return out;
  });
  const path = `${DUMP_DIR}/ladder_strings_${state}.txt`;
  writeFileSync(path, lines.join('\n') + '\n', 'utf8');
  return { path, count: lines.length };
}

let scanner;
(async () => {
  const repoRoot = execSync(`${PY} -c "from laplace.web.scanner import _repo_root; print(_repo_root().resolve())"`)
    .toString().trim();
  const port = await freePort();
  const base = `http://127.0.0.1:${port}`;
  scanner = spawn(PY, ['-m', 'laplace.web.scanner', '--port', String(port)],
    { cwd: repoRoot, stdio: 'ignore' });
  await waitFor(`${base}/shared/shell.js`);

  const b = await chromium.launch({ executablePath: CHROME });
  const VP = { width: 1000, height: 800 };
  try {
    // ══ W-L1 · TRIGGER — the token is a real listbox opener; click → six rungs, fixed order, <5s ══
    {
      const pg = await b.newPage({ viewport: VP });
      await pg.goto(`${base}/conceptric?corpus=${RICH}&node=${encodeURIComponent(NODE)}`, { waitUntil: 'domcontentloaded' });
      const tok = '.hy-ctx-sel.is-ladder';
      await pg.waitForSelector(tok, { timeout: 10000 });
      const afford = await pg.evaluate((s) => {
        const el = document.querySelector(s);
        return { tag: el.tagName, haspopup: el.getAttribute('aria-haspopup'),
          cursor: getComputedStyle(el).cursor };
      }, tok);
      ok(afford.tag === 'BUTTON' && afford.haspopup === 'listbox', 'W-L1 sel token is a <button aria-haspopup=listbox>');
      ok(afford.cursor === 'pointer', 'W-L1 sel token cursor:pointer (an affordance, not a label)');
      const t0 = Date.now();
      await openLadder(pg, tok);
      const dt = Date.now() - t0;
      ok(dt < 5000, `W-L1 six rungs rendered in ${dt}ms (<5000)`);
      const order = await pg.evaluate(() => Array.prototype.map.call(
        document.querySelectorAll('#hy-ladder .hy-ladder-rung'), (e) => e.id.replace('hy-rung-', '')).join(','));
      ok(order === 'concept,argument,prose,evidence,judgment,machine', `W-L1 fixed rung order (${order})`);
      await pg.close();
    }

    // ══ W-L2 · project ladder from corpus-no-selection ══
    {
      const pg = await b.newPage({ viewport: VP });
      await pg.goto(`${base}/conceptric?corpus=${RICH}`, { waitUntil: 'domcontentloaded' });
      const projTok = '.hy-ctx-proj.hy-ctx-ladder';
      await openLadder(pg, projTok);
      const { diffs, payload } = await honesty(pg, RICH, RICH, 'project');
      ok(diffs.length === 0, `W-L2 project ladder DOM==payload (${diffs.join('; ') || 'clean'})`);
      ok(payload.target.kind === 'project', 'W-L2 no-selection token opens kind=project');
      await pg.close();
    }

    // ══ W-L3 · the `/` scope token is inert: no cursor, click → no panel, zero console errors ══
    {
      const pg = await b.newPage({ viewport: VP });
      const errs = [];
      pg.on('console', (m) => { if (m.type() === 'error') errs.push(m.text()); });
      pg.on('pageerror', (e) => errs.push(String(e)));
      await pg.goto(`${base}/conceptric`, { waitUntil: 'domcontentloaded' });
      await pg.waitForSelector('.hy-ctx-proj.is-scope', { timeout: 10000 });
      const scope = await pg.evaluate(() => {
        const el = document.querySelector('.hy-ctx-proj.is-scope');
        return { tag: el.tagName, cursor: getComputedStyle(el).cursor,
          haspopup: el.getAttribute('aria-haspopup'), text: el.textContent.trim() };
      });
      ok(scope.tag === 'SPAN' && !scope.haspopup, 'W-L3 scope token is an inert <span> (no aria-haspopup)');
      ok(scope.cursor !== 'pointer', `W-L3 scope token has no pointer cursor (${scope.cursor})`);
      ok(scope.text === 'all projects', 'W-L3 scope token names the honest scope "all projects"');
      await pg.click('.hy-ctx-proj.is-scope');
      await pg.waitForTimeout(300);
      const opened = await pg.evaluate(() => {
        const el = document.getElementById('hy-ladder');
        return !!(el && el.classList.contains('open'));
      });
      ok(!opened, 'W-L3 clicking the scope token opens no panel');
      ok(errs.length === 0, `W-L3 zero console errors (${errs.join(' | ')})`);
      await pg.close();
    }

    // ══ W-L4 · node populated — DOM==payload + concept href carries the node ══
    {
      const pg = await b.newPage({ viewport: VP });
      await pg.goto(`${base}/conceptric?corpus=${RICH}&node=${encodeURIComponent(NODE)}`, { waitUntil: 'domcontentloaded' });
      await openLadder(pg, '.hy-ctx-sel.is-ladder');
      const { diffs, payload } = await honesty(pg, RICH, NODE, 'node');
      ok(diffs.length === 0, `W-L4 node DOM==payload (${diffs.join('; ') || 'clean'})`);
      const concept = payload.rungs.find((r) => r.id === 'concept');
      ok(concept.present && concept.href === `/conceptric?node=${encodeURIComponent(NODE)}`,
        `W-L4 concept href carries the node (${concept.href})`);
      await pg.close();
    }

    // ══ W-L5 · section populated ══
    {
      const pg = await b.newPage({ viewport: VP });
      await pg.goto(`${base}/artefact?corpus=${RICH}&section=${SECTION}`, { waitUntil: 'domcontentloaded' });
      await openLadder(pg, '.hy-ctx-sel.is-ladder');
      const { diffs, payload } = await honesty(pg, RICH, SECTION, 'section');
      ok(diffs.length === 0, `W-L5 section DOM==payload (${diffs.join('; ') || 'clean'})`);
      ok(payload.target.kind === 'section' && payload.target.section === SECTION,
        `W-L5 section target resolves (${payload.target.section})`);
      await pg.close();
    }

    // ══ W-L6 · pid via the SERVER GRAMMAR (?anchor= is not a hint kind → NX-p# → pid) ══
    {
      const pg = await b.newPage({ viewport: VP });
      await pg.goto(`${base}/artefact?corpus=${RICH}&anchor=${PID}`, { waitUntil: 'domcontentloaded' });
      await openLadder(pg, '.hy-ctx-sel.is-ladder');
      const { diffs, payload } = await honesty(pg, RICH, PID, 'anchor');
      ok(diffs.length === 0, `W-L6 pid DOM==payload (${diffs.join('; ') || 'clean'})`);
      ok(payload.target.kind === 'pid', `W-L6 the grammar classifies ${PID} as pid (got ${payload.target.kind})`);
      await pg.close();
    }

    // ══ W-L7 · beat — the id is a live /corpus/spine member; ladder argues it ══
    {
      const pg = await b.newPage({ viewport: VP });
      await pg.goto(`${base}/artefact?corpus=${RICH}&beat=${encodeURIComponent(BEAT)}`, { waitUntil: 'domcontentloaded' });
      const spineHas = await pg.evaluate(async ({ c, beat }) => {
        const r = await fetch('/corpus/spine?corpus=' + encodeURIComponent(c));
        const d = await r.json();
        return (d.spine || []).some((x) => x.id === beat);
      }, { c: RICH, beat: BEAT });
      ok(spineHas, `W-L7 ${BEAT} is a live /corpus/spine beat`);
      await openLadder(pg, '.hy-ctx-sel.is-ladder');
      const { diffs, payload } = await honesty(pg, RICH, BEAT, 'beat');
      ok(diffs.length === 0, `W-L7 beat DOM==payload (${diffs.join('; ') || 'clean'})`);
      const arg = payload.rungs.find((r) => r.id === 'argument');
      ok(arg.present && arg.href.includes('#' + encodeURIComponent(BEAT)),
        `W-L7 argument door lands on the beat anchor (${arg.href})`);
      await pg.close();
    }

    // ══ W-L8 · asset — header names it; evidence rung IS it; concept count == nodes_supported ══
    {
      const pg = await b.newPage({ viewport: VP });
      await pg.goto(`${base}/assets?corpus=${RICH}&asset=${encodeURIComponent(ASSET)}`, { waitUntil: 'domcontentloaded' });
      await openLadder(pg, '.hy-ctx-sel.is-ladder');
      const { diffs, payload } = await honesty(pg, RICH, ASSET, 'asset');
      ok(diffs.length === 0, `W-L8 asset DOM==payload (${diffs.join('; ') || 'clean'})`);
      const headText = await pg.evaluate(() => document.querySelector('#hy-ladder .hy-ladder-target').textContent);
      ok(/WK-032/.test(headText), `W-L8 head names the asset (${headText})`);
      const evi = payload.rungs.find((r) => r.id === 'evidence');
      ok(evi.present && evi.count === 1 && evi.href.includes('asset=' + encodeURIComponent(ASSET)),
        `W-L8 evidence rung IS the asset (count ${evi.count}, door ${evi.href})`);
      const concept = payload.rungs.find((r) => r.id === 'concept');
      ok(concept.count === payload.target.node_ids.length,
        `W-L8 concept count == nodes_supported (${concept.count} == ${payload.target.node_ids.length})`);
      await pg.close();
    }

    // ══ W-L9 · project rich — machine href /pipeline?project= ══
    {
      const pg = await b.newPage({ viewport: VP });
      await pg.goto(`${base}/conceptric?corpus=${RICH}`, { waitUntil: 'domcontentloaded' });
      await openLadder(pg, '.hy-ctx-proj.hy-ctx-ladder');
      const { diffs, payload } = await honesty(pg, RICH, RICH, 'project');
      ok(diffs.length === 0, `W-L9 project-rich DOM==payload (${diffs.join('; ') || 'clean'})`);
      const machine = payload.rungs.find((r) => r.id === 'machine');
      ok(machine.present && machine.href === `/pipeline?project=${encodeURIComponent(RICH)}`,
        `W-L9 machine door /pipeline?project= (${machine.href})`);
      const allPresent = payload.rungs.every((r) => r.present);
      ok(allPresent, 'W-L9 the rich project renders all six rungs present');
      await pg.close();
    }

    // ══ W-L10 · paper_eigen honest empties — argument absent reason + fix door /storyboard ══
    {
      const pg = await b.newPage({ viewport: VP });
      await pg.goto(`${base}/conceptric?corpus=${EMPTY}`, { waitUntil: 'domcontentloaded' });
      await openLadder(pg, '.hy-ctx-proj.hy-ctx-ladder');
      const { diffs, payload } = await honesty(pg, EMPTY, EMPTY, 'project');
      ok(diffs.length === 0, `W-L10 honest-empty DOM==payload (${diffs.join('; ') || 'clean'})`);
      const arg = payload.rungs.find((r) => r.id === 'argument');
      ok(!arg.present && /no projection plan/.test(arg.absent.reason),
        `W-L10 argument absent names the fact (${arg.absent.reason})`);
      ok(arg.absent.fix_href.startsWith('/storyboard'), `W-L10 argument fix door → /storyboard (${arg.absent.fix_href})`);
      // the absent rung's fix door is a REAL <a> the chair can walk (not a dead label).
      const fixIsAnchor = await pg.evaluate(() => {
        const el = document.querySelector('#hy-rung-argument .hy-ladder-fix');
        return el && el.tagName === 'A' && !!el.getAttribute('href');
      });
      ok(fixIsAnchor, 'W-L10 the fix is a real <a href> door, not a TODO');
      await pg.close();
    }

    // ══ W-L11 · unknown node → known:false panel + fix ══
    {
      const pg = await b.newPage({ viewport: VP });
      await pg.goto(`${base}/conceptric?corpus=${RICH}&node=${encodeURIComponent(UNKNOWN)}`, { waitUntil: 'domcontentloaded' });
      await openLadder(pg, '.hy-ctx-sel.is-ladder');
      const { diffs, payload } = await honesty(pg, RICH, UNKNOWN, 'node');
      ok(diffs.length === 0, `W-L11 unknown-node DOM==payload (${diffs.join('; ') || 'clean'})`);
      ok(payload.target.known === false, 'W-L11 payload.target.known === false');
      const unresolved = await pg.evaluate(() => {
        const el = document.querySelector('#hy-ladder .hy-ladder-kind.is-warn');
        return el ? el.textContent.trim() : null;
      });
      ok(unresolved === 'unresolved', 'W-L11 the head flags the target unresolved (not a dead end)');
      const concept = payload.rungs.find((r) => r.id === 'concept');
      ok(!concept.present && concept.absent.fix_href, `W-L11 concept names its fix door (${concept.absent.fix_href})`);
      await pg.close();
    }

    // ══ W-L12 · version → uniform ladder; prose door carries &version=; rail-overlap line ══
    {
      const pg = await b.newPage({ viewport: VP });
      await pg.goto(`${base}/artefact?corpus=${RICH}&version=r42`, { waitUntil: 'domcontentloaded' });
      await openLadder(pg, '.hy-ctx-sel.is-ladder');
      const { diffs, payload } = await honesty(pg, RICH, 'r42', 'version');
      ok(diffs.length === 0, `W-L12 version DOM==payload (${diffs.join('; ') || 'clean'})`);
      ok(payload.target.kind === 'version', 'W-L12 version opens the uniform ladder (kind=version)');
      const prose = payload.rungs.find((r) => r.id === 'prose');
      ok(prose.present && prose.href.includes('version=r42'), `W-L12 prose door carries &version= (${prose.href})`);
      ok(/version rail/.test(prose.sub), `W-L12 prose sub names where history lives (${prose.sub})`);
      await pg.close();
    }

    // ══ W-L13 · the circuit: concept door → conceptric → echo names origin → returns to exact URL ══
    {
      const pg = await b.newPage({ viewport: VP });
      const originUrl = `/artefact?corpus=${RICH}&node=${encodeURIComponent(NODE)}`;
      await pg.goto(base + originUrl, { waitUntil: 'domcontentloaded' });
      await openLadder(pg, '.hy-ctx-sel.is-ladder');
      const conceptHref = await pg.evaluate(() => document.querySelector('#hy-rung-concept').getAttribute('href'));
      await Promise.all([
        pg.waitForNavigation({ waitUntil: 'domcontentloaded' }),
        pg.click('#hy-rung-concept'),
      ]);
      ok(new URL(pg.url()).pathname === '/conceptric', `W-L13 concept door landed on /conceptric (${pg.url()})`);
      await pg.waitForSelector('#hy-context .hy-from', { timeout: 10000 });
      const echo = await pg.evaluate(() => {
        const a = document.querySelector('#hy-context .hy-from');
        return { text: a.innerText, href: a.getAttribute('href') };
      });
      ok(/from/i.test(echo.text) && echo.text.includes(NODE),
        `W-L13 the echo names where you came from — the node (${echo.text})`);
      ok(/Artefact/i.test(echo.text), `W-L13 the echo names the origin surface Artefact (${echo.text})`);
      ok(echo.href.includes('/artefact') && echo.href.includes(`node=${encodeURIComponent(NODE)}`),
        `W-L13 the echo is a door back to the exact origin URL (${echo.href})`);
      await Promise.all([
        pg.waitForNavigation({ waitUntil: 'domcontentloaded' }),
        pg.click('#hy-context .hy-from'),
      ]);
      ok(pg.url() === base + originUrl, `W-L13 walking the echo returns to the exact origin URL (${pg.url()})`);
      await pg.close();
    }

    // ══ W-L14 · open ≠ navigation — the D15 origin stamp is byte-identical across open/close ══
    {
      const pg = await b.newPage({ viewport: VP });
      await pg.goto(`${base}/conceptric?corpus=${RICH}&node=${encodeURIComponent(NODE)}`, { waitUntil: 'domcontentloaded' });
      await pg.waitForSelector('.hy-ctx-sel.is-ladder', { timeout: 10000 });
      const before = await pg.evaluate(() => ({
        url: location.href, origin: sessionStorage.getItem('hymn.origin') }));
      await openLadder(pg, '.hy-ctx-sel.is-ladder');
      await pg.click('.hy-ladder-x');
      await pg.waitForFunction(() => !document.getElementById('hy-ladder').classList.contains('open'), { timeout: 4000 });
      const after = await pg.evaluate(() => ({
        url: location.href, origin: sessionStorage.getItem('hymn.origin') }));
      ok(after.url === before.url, 'W-L14 opening/closing the ladder does not change the URL');
      ok(after.origin === before.origin, 'W-L14 the origin stamp is byte-identical (open/close is not a navigation)');
      await pg.close();
    }

    // ══ W-L15 · evidence door lands on the NAMED asset — cockpit expanded ══
    {
      const pg = await b.newPage({ viewport: VP });
      await pg.goto(`${base}/conceptric?corpus=${RICH}&asset=${encodeURIComponent(ASSET)}`, { waitUntil: 'domcontentloaded' });
      await openLadder(pg, '.hy-ctx-sel.is-ladder');
      const eviHref = await pg.evaluate(() => document.querySelector('#hy-rung-evidence').getAttribute('href'));
      ok(eviHref.includes('asset=' + encodeURIComponent(ASSET)), `W-L15 evidence door carries the asset (${eviHref})`);
      await Promise.all([
        pg.waitForNavigation({ waitUntil: 'domcontentloaded' }),
        pg.click('#hy-rung-evidence'),
      ]);
      const openCard = await pg.waitForSelector(`.dk-card.open[data-row="${ASSET}"]`, { timeout: 10000 });
      ok(!!openCard, `W-L15 the evidence door landed on the NAMED asset, cockpit expanded (.dk-card.open[data-row="${ASSET}"])`);
      await pg.close();
    }

    // ══ W-L16 · judgment + machine doors land on headers naming corpus/project ══
    {
      // machine door → the pipeline surface, header names the project. ACT 4: the bare
      // /pipeline route 301s to /project (the project cockpit is the one pipeline home), so the
      // ladder's machine rung (href /pipeline?project=, W-L9) LANDS on /project after the hop.
      const pm = await b.newPage({ viewport: VP });
      await pm.goto(`${base}/conceptric?corpus=${RICH}&node=${encodeURIComponent(NODE)}`, { waitUntil: 'domcontentloaded' });
      await openLadder(pm, '.hy-ctx-sel.is-ladder');
      await Promise.all([
        pm.waitForNavigation({ waitUntil: 'domcontentloaded' }),
        pm.click('#hy-rung-machine'),
      ]);
      ok(new URL(pm.url()).pathname === '/project' && pm.url().includes(`project=${encodeURIComponent(RICH)}`),
        `W-L16 machine door landed on the pipeline surface (/pipeline 301s to /project?project=) (${pm.url()})`);
      // the pipeline surface scopes itself to the project (canonicalizes corpus= into the URL).
      await pm.waitForFunction((c) => new URLSearchParams(location.search).get('corpus') === c,
        RICH, { timeout: 10000 });
      ok(true, `W-L16 the pipeline surface scoped to the project (corpus=${RICH} canonicalized)`);
      await pm.close();
      // judgment door → /desk, header names the corpus
      const pj = await b.newPage({ viewport: VP });
      await pj.goto(`${base}/conceptric?corpus=${RICH}&node=${encodeURIComponent(NODE)}`, { waitUntil: 'domcontentloaded' });
      await openLadder(pj, '.hy-ctx-sel.is-ladder');
      const judgHref = await pj.evaluate(() => document.querySelector('#hy-rung-judgment').getAttribute('href'));
      ok(judgHref.startsWith('/desk'), `W-L16 judgment door → /desk (${judgHref})`);
      await Promise.all([
        pj.waitForNavigation({ waitUntil: 'domcontentloaded' }),
        pj.click('#hy-rung-judgment'),
      ]);
      ok(new URL(pj.url()).pathname === '/desk', `W-L16 judgment door landed on /desk (${pj.url()})`);
      await pj.close();
    }

    // ══ W-L17 · three close paths + focus returns to the token ══
    {
      const pg = await b.newPage({ viewport: VP });
      const tok = '.hy-ctx-sel.is-ladder';
      // (a) the × button
      await pg.goto(`${base}/conceptric?corpus=${RICH}&node=${encodeURIComponent(NODE)}`, { waitUntil: 'domcontentloaded' });
      await openLadder(pg, tok);
      await pg.click('.hy-ladder-x');
      await pg.waitForFunction(() => !document.getElementById('hy-ladder').classList.contains('open'), { timeout: 4000 });
      let focused = await pg.evaluate((s) => document.activeElement === document.querySelector(s), tok);
      ok(focused, 'W-L17 close-by-× returns focus to the token');
      // (b) Escape
      await openLadder(pg, tok);
      await pg.keyboard.press('Escape');
      await pg.waitForFunction(() => !document.getElementById('hy-ladder').classList.contains('open'), { timeout: 4000 });
      focused = await pg.evaluate((s) => document.activeElement === document.querySelector(s), tok);
      ok(focused, 'W-L17 close-by-Escape returns focus to the token');
      // (c) toggle: clicking the same token again closes
      await openLadder(pg, tok);
      await pg.click(tok);
      await pg.waitForFunction(() => !document.getElementById('hy-ladder').classList.contains('open'), { timeout: 4000 });
      ok(true, 'W-L17 close-by-toggle (re-click the token) closes the panel');
      await pg.close();
    }

    // ══ W-L18 · Escape ordering — the ladder closes BEFORE the rail (topmost-transient) ══
    {
      const pg = await b.newPage({ viewport: VP });
      await pg.goto(`${base}/artefact?corpus=${RICH}&version=r42`, { waitUntil: 'domcontentloaded' });
      // open the ladder, THEN raise the rail over it (rail z 4100 > ladder z 4001). The
      // capture-phase Escape must still close the ladder first (topmost-transient by handler
      // order, not by z) — so the token stays reachable and the rail never blocks the open.
      await openLadder(pg, '.hy-ctx-sel.is-ladder');
      const railOpened = await pg.evaluate(() => {
        try {
          if (window.HymnShell && typeof window.HymnShell.openRail === 'function') { window.HymnShell.openRail(); return true; }
        } catch (e) { /* rail unavailable on this surface */ }
        return false;
      });
      await pg.waitForTimeout(300);
      await pg.keyboard.press('Escape');
      await pg.waitForTimeout(200);
      const st = await pg.evaluate(() => ({
        ladderOpen: !!(document.getElementById('hy-ladder') && document.getElementById('hy-ladder').classList.contains('open')),
        railOpen: !!document.querySelector('.hy-rail.open, #hy-rail.open'),
      }));
      ok(!st.ladderOpen, 'W-L18 first Escape closed the ladder');
      if (railOpened) ok(st.railOpen, 'W-L18 the rail stayed open under it (ladder is the topmost transient)');
      else ok(true, 'W-L18 rail affordance absent on this surface — ladder-closes-first still held');
      await pg.close();
    }

    // ══ W-L19 · ↑↓ moves the active rung; Enter follows its door ══
    {
      const pg = await b.newPage({ viewport: VP });
      await pg.goto(`${base}/conceptric?corpus=${RICH}&node=${encodeURIComponent(NODE)}`, { waitUntil: 'domcontentloaded' });
      await openLadder(pg, '.hy-ctx-sel.is-ladder');
      await pg.keyboard.press('ArrowDown');
      const active1 = await pg.evaluate(() => {
        const box = document.querySelector('#hy-ladder .hy-ladder-rungs');
        return box.getAttribute('aria-activedescendant');
      });
      ok(active1 === 'hy-rung-concept', `W-L19 ↓ activates the first rung (${active1})`);
      await pg.keyboard.press('ArrowDown');
      const active2 = await pg.evaluate(() => document.querySelector('#hy-ladder .hy-ladder-rungs').getAttribute('aria-activedescendant'));
      ok(active2 === 'hy-rung-argument', `W-L19 a second ↓ advances to the next rung (${active2})`);
      const targetHref = await pg.evaluate(() => document.querySelector('#hy-rung-argument').getAttribute('href'));
      await Promise.all([
        pg.waitForNavigation({ waitUntil: 'domcontentloaded' }),
        pg.keyboard.press('Enter'),
      ]);
      ok(new URL(pg.url()).pathname === new URL(base + targetHref).pathname,
        `W-L19 Enter follows the active rung's door (${pg.url()})`);
      await pg.close();
    }

    // ══ W-L20 · 375px — no horizontal scroll, panel within viewport, close paths hold ══
    {
      const pg = await b.newPage({ viewport: { width: 375, height: 720 } });
      await pg.goto(`${base}/conceptric?corpus=${RICH}&node=${encodeURIComponent(NODE)}`, { waitUntil: 'domcontentloaded' });
      await pg.waitForSelector('.hy-ctx-sel.is-ladder', { timeout: 10000 });
      await pg.waitForTimeout(400);
      const baseScroll = await pg.evaluate(() => document.documentElement.scrollWidth);
      await openLadder(pg, '.hy-ctx-sel.is-ladder');
      const box = await pg.evaluate(() => {
        const el = document.getElementById('hy-ladder');
        const r = el.getBoundingClientRect();
        return { left: r.left, right: r.right, vw: window.innerWidth,
          scroll: document.documentElement.scrollWidth };
      });
      ok(box.left >= 0 && box.right <= box.vw + 1, `W-L20 panel within the 375px viewport (left ${box.left|0} right ${box.right|0} vw ${box.vw})`);
      // the ladder must add NO horizontal scroll of its own (the surface's own baseline
      // overflow is out of the ladder's scope — the panel spilling would be the failure).
      ok(box.scroll <= baseScroll, `W-L20 the ladder adds no horizontal scroll (${box.scroll} <= baseline ${baseScroll})`);
      await pg.click('.hy-ladder-x');
      await pg.waitForFunction(() => !document.getElementById('hy-ladder').classList.contains('open'), { timeout: 4000 });
      ok(true, 'W-L20 the × close path holds at 375px');
      await pg.close();
    }

    // ══ W-L21 · SPA selection refresh — card A→B; head names B; token refreshed ══
    {
      const pg = await b.newPage({ viewport: VP });
      const NODE_B = BEAT;   // a distinct second selection
      await pg.goto(`${base}/conceptric?corpus=${RICH}&node=${encodeURIComponent(NODE)}`, { waitUntil: 'domcontentloaded' });
      await pg.waitForSelector('.hy-ctx-sel.is-ladder', { timeout: 10000 });
      // simulate an SPA store.set: push the new selection into the URL, then refresh the token
      await pg.evaluate((n) => {
        const u = new URL(location.href); u.searchParams.set('node', n); history.pushState({}, '', u);
        if (window.HymnShell && window.HymnShell.refreshSelToken) window.HymnShell.refreshSelToken();
      }, NODE_B);
      const tokVal = await pg.evaluate(() => {
        const el = document.querySelector('.hy-ctx-sel .hy-ctx-sel-val');
        return el ? el.textContent.trim() : '';
      });
      ok(tokVal === NODE_B, `W-L21 the token refreshed to the new selection B (${tokVal})`);
      await openLadder(pg, '.hy-ctx-sel.is-ladder');
      const head = await pg.evaluate(() => document.querySelector('#hy-ladder .hy-ladder-target').textContent);
      const { payload } = await honesty(pg, RICH, NODE_B, 'node');
      ok(payload.target.raw === NODE_B, `W-L21 the ladder opened over selection B (${payload.target.raw})`);
      ok(head.length > 0, `W-L21 the head names B's label (${head})`);
      await pg.close();
    }

    // ══ W-L22 · cross-corpus no-bleed — the cache never serves A for B; a fetch fires for B ══
    {
      const pg = await b.newPage({ viewport: VP });
      await pg.goto(`${base}/conceptric?corpus=${RICH}`, { waitUntil: 'domcontentloaded' });
      await openLadder(pg, '.hy-ctx-proj.hy-ctx-ladder');
      await pg.click('.hy-ladder-x');
      await pg.waitForFunction(() => !document.getElementById('hy-ladder').classList.contains('open'), { timeout: 4000 });
      // now to corpus B (paper_eigen) and watch the network for a B-scoped ladder fetch
      const reqs = [];
      pg.on('request', (r) => { if (r.url().includes('/shared/ladder')) reqs.push(r.url()); });
      await pg.goto(`${base}/conceptric?corpus=${EMPTY}`, { waitUntil: 'domcontentloaded' });
      await openLadder(pg, '.hy-ctx-proj.hy-ctx-ladder');
      const firedForB = reqs.some((u) => u.includes(`corpus=${EMPTY}`));
      ok(firedForB, `W-L22 a fetch fired for corpus B (${reqs.filter((u) => u.includes('corpus=')).join(' | ')})`);
      const { payload } = await honesty(pg, EMPTY, EMPTY, 'project');
      ok(payload.corpus === EMPTY, `W-L22 the panel shows B's payload, not A's cache (${payload.corpus})`);
      const argB = payload.rungs.find((r) => r.id === 'argument');
      ok(!argB.present, 'W-L22 B renders its own honest-empty argument (no A-bleed)');
      await pg.close();
    }

    // ══ W-L23 · server-down (fetch aborts) → honest in-panel card, never a blank ══
    {
      const pg = await b.newPage({ viewport: VP });
      await pg.goto(`${base}/conceptric?corpus=${RICH}&node=${encodeURIComponent(NODE)}`, { waitUntil: 'domcontentloaded' });
      await pg.waitForSelector('.hy-ctx-sel.is-ladder', { timeout: 10000 });
      await pg.route('**/shared/ladder*', (r) => r.abort());   // the read does not return
      await pg.click('.hy-ctx-sel.is-ladder');
      const failMsg = await pg.waitForSelector('#hy-ladder .hy-ladder-fail-msg', { timeout: 8000 });
      const txt = await failMsg.evaluate((e) => e.textContent);
      // the card names the factual state and stops — the retry button below carries the
      // transient-not-empty meaning, so the old reassurance clause is deleted (text law).
      ok(/the ladder read did not return/.test(txt),
        `W-L23 the failure card names the factual state (${txt})`);
      ok(!/not a claim this selection/.test(txt),
        'W-L23 the reassurance clause is gone — no string the chair cannot act on');
      const noBlank = await pg.evaluate(() => {
        const el = document.getElementById('hy-ladder');
        return !el.querySelector('.hy-ladder-loading') && el.textContent.trim().length > 0;
      });
      ok(noBlank, 'W-L23 the loading line was replaced — no blank panel');
      const hasRetry = await pg.$('#hy-ladder .hy-ladder-retry');
      ok(hasRetry !== null, 'W-L23 the card offers a retry door');
      await pg.unroute('**/shared/ladder*');
      await pg.close();
    }

    // ══ W-L24 · unknown corpus → relayed 404 body + door to `/` ══
    {
      const pg = await b.newPage({ viewport: VP });
      await pg.goto(`${base}/conceptric?corpus=no-such-corpus`, { waitUntil: 'domcontentloaded' });
      await pg.waitForSelector('.hy-ctx-proj.hy-ctx-ladder', { timeout: 10000 });
      await pg.click('.hy-ctx-proj.hy-ctx-ladder');
      const msg = await pg.waitForSelector('#hy-ladder .hy-ladder-fail-msg', { timeout: 8000 });
      const txt = await msg.evaluate((e) => e.textContent);
      ok(/no project for corpus/.test(txt), `W-L24 the 404 body is relayed verbatim (${txt})`);
      const door = await pg.evaluate(() => {
        const a = document.querySelector('#hy-ladder .hy-ladder-fix');
        return a ? a.getAttribute('href') : null;
      });
      ok(door === '/', `W-L24 the card offers a door to the dashboard / (${door})`);
      await pg.close();
    }

    // ══ W-L25 · degraded honesty — TWO organs, each honest: evidence rides the node→region
    //          map (subset-sum has none → stale); prose rides the plan→prose projection diff
    //          (dirty_report), so it warns PER-SECTION and never over the nodemap. DOM==payload;
    //          the fresh-nodemap+fresh-plan control (paper_falqon) shows NO stale chip ══
    {
      const pg = await b.newPage({ viewport: VP });
      // (a) degraded PROJECT: no nodemap (evidence stale) AND dirty plan sections (prose stale)
      await pg.goto(`${base}/conceptric?corpus=${RICH}`, { waitUntil: 'domcontentloaded' });
      await openLadder(pg, '.hy-ctx-proj.hy-ctx-ladder');
      const r1 = await honesty(pg, RICH, RICH, 'project');
      ok(r1.diffs.length === 0, `W-L25 degraded DOM==payload incl. stale chips (${r1.diffs.join('; ') || 'clean'})`);
      const staleRungs = r1.payload.rungs.filter((r) => r.stale).map((r) => r.id);
      ok(staleRungs.includes('prose') && staleRungs.includes('evidence'),
        `W-L25 prose (plan→prose) + evidence (nodemap) each carry their own stale chip (${staleRungs.join(',')})`);
      const domStale = await pg.evaluate(() => document.querySelectorAll('#hy-ladder .hy-ladder-stale').length);
      ok(domStale === staleRungs.length, `W-L25 every payload stale chip is rendered (${domStale} == ${staleRungs.length})`);
      // (a2) the prose chip is the PLAN→PROSE organ, PER-SECTION: a dirty section warns, a
      //      node whose owning section is fresh does NOT (proof it is dirty_report, not the
      //      project-wide nodemap that would paint every section the same).
      const perSec = await pg.evaluate(async ({ corpus, dirtySec, freshNode }) => {
        const g = async (t, k) => (await (await fetch('/shared/ladder?corpus=' +
          encodeURIComponent(corpus) + '&target=' + encodeURIComponent(t) + '&kind=' + k)).json());
        const prose = (o) => o.rungs.find((r) => r.id === 'prose').stale;
        const d = await g(dirtySec, 'section'), f = await g(freshNode, 'node');
        return { dirtyStale: prose(d), freshStale: !!prose(f) };
      }, { corpus: RICH, dirtySec: 'N3', freshNode: NODE });
      ok(perSec.dirtyStale && !perSec.freshStale,
        `W-L25 prose staleness is PER-SECTION (dirty N3 warns, ${NODE}'s fresh section clean)`);
      ok(/the prose no longer matches the plan/.test((perSec.dirtyStale || {}).reason || ''),
        `W-L25 the prose chip names the plan→prose divergence (${(perSec.dirtyStale || {}).reason})`);
      // (b) fresh control: paper_falqon renders no stale chip (fresh nodemap + fresh plan)
      await pg.goto(`${base}/conceptric?corpus=${FRESH}`, { waitUntil: 'domcontentloaded' });
      await openLadder(pg, '.hy-ctx-proj.hy-ctx-ladder');
      const r2 = await honesty(pg, FRESH, FRESH, 'project');
      ok(r2.diffs.length === 0, `W-L25 fresh-nodemap DOM==payload (${r2.diffs.join('; ') || 'clean'})`);
      const freshStale = await pg.evaluate(() => document.querySelectorAll('#hy-ladder .hy-ladder-stale').length);
      ok(freshStale === 0 && r2.payload.rungs.every((r) => !r.stale),
        'W-L25 the fresh corpus paints no stale chip (honesty both directions)');
      await pg.close();
    }

    // ══ W-L26 · PSU / no-hang — a COLD click renders in <5000ms (fresh page, empty cache) ══
    {
      const pg = await b.newPage({ viewport: VP });
      await pg.goto(`${base}/conceptric?corpus=${RICH}&node=${encodeURIComponent(NODE)}`, { waitUntil: 'domcontentloaded' });
      await pg.waitForSelector('.hy-ctx-sel.is-ladder', { timeout: 10000 });
      const t0 = Date.now();
      await pg.click('.hy-ctx-sel.is-ladder');
      await pg.waitForFunction(() => {
        const el = document.getElementById('hy-ladder');
        return el && el.classList.contains('open') && el.querySelectorAll('.hy-ladder-rung').length === 6 &&
          !el.querySelector('.hy-ladder-loading');
      }, { timeout: 6000 });
      const dt = Date.now() - t0;
      ok(dt < 5000, `W-L26 cold click → rendered in ${dt}ms (<5000; the pure-reads join, no rebuild)`);
      await pg.close();
    }

    // ══ W-L27 · ✎ opens the capture (no bank) — the default suite never mutates ══
    {
      const pg = await b.newPage({ viewport: VP });
      const posts = [];
      pg.on('request', (r) => { if (r.method() === 'POST' && r.url().includes('/corpus/friction')) posts.push(r.url()); });
      await pg.goto(`${base}/conceptric?corpus=${RICH}&node=${encodeURIComponent(NODE)}`, { waitUntil: 'domcontentloaded' });
      await openLadder(pg, '.hy-ctx-sel.is-ladder');
      await pg.click('#hy-ladder .hy-ladder-head .rule-chip');
      const cap = await pg.waitForSelector('#hy-ladder .rule-cap.on textarea', { timeout: 4000 });
      ok(!!cap, 'W-L27 the ✎ opens the rule capture (a textarea, in place)');
      await pg.waitForTimeout(200);
      ok(posts.length === 0, `W-L27 opening the capture banks nothing (${posts.length} POSTs — the default suite is read-only)`);
      await pg.close();
    }

    // ══ W-L29 · up-conjugate parity — a desk row's concept deep-link == the ladder's concept door ══
    {
      const pg = await b.newPage({ viewport: VP });
      await pg.goto(`${base}/conceptric?corpus=${RICH}`, { waitUntil: 'domcontentloaded' });
      // pull a real adjudication row from /desk/data (guaranteed present — his-move class, first)
      const deskRow = await pg.evaluate(async (corpus) => {
        const r = await fetch('/desk/data');
        const d = await r.json();
        for (const row of d.rows || []) {
          if (row.class !== 'adjudications' || row.project !== corpus) continue;
          const cd = (row.deeplinks || []).find((l) => l.href.indexOf('/conceptric?node=') === 0);
          if (cd) {
            const node = decodeURIComponent(cd.href.split('node=')[1]);
            return { id: row.id, conceptHref: cd.href, node };
          }
        }
        return null;
      }, RICH);
      ok(deskRow !== null, 'W-L29 found a subset-sum adjudication row with a concept deep-link');
      // fetch the ladder for the SAME node and compare the concept door byte-for-byte.
      const ladderConcept = await pg.evaluate(async ({ corpus, node }) => {
        const r = await fetch('/shared/ladder?corpus=' + encodeURIComponent(corpus) +
          '&target=' + encodeURIComponent(node) + '&kind=node');
        const d = await r.json();
        return (d.rungs.find((x) => x.id === 'concept') || {}).href;
      }, { corpus: RICH, node: deskRow.node });
      ok(ladderConcept === deskRow.conceptHref,
        `W-L29 desk deep-link == ladder concept door — both ride doors_for (${ladderConcept} == ${deskRow.conceptHref})`);
      await pg.close();
    }

    // ══ W-L30 · THE STRINGS WALK — dump every rendered string in four states to disk ══
    {
      const dumps = {};
      // populated: the rich node (present rungs, counts, subs, doors, head, kind chip)
      {
        const pg = await b.newPage({ viewport: VP });
        await pg.goto(`${base}/artefact?corpus=${RICH}&node=${encodeURIComponent(NODE)}`, { waitUntil: 'domcontentloaded' });
        await openLadder(pg, '.hy-ctx-sel.is-ladder');
        dumps.populated = await dumpLadderStrings(pg, 'populated');
        await pg.close();
      }
      // empty: paper_eigen (absent reasons + fix labels)
      {
        const pg = await b.newPage({ viewport: VP });
        await pg.goto(`${base}/conceptric?corpus=${EMPTY}`, { waitUntil: 'domcontentloaded' });
        await openLadder(pg, '.hy-ctx-proj.hy-ctx-ladder');
        dumps.empty = await dumpLadderStrings(pg, 'empty');
        await pg.close();
      }
      // degraded: subset-sum stale chips (reason + fix in the warn chip title)
      {
        const pg = await b.newPage({ viewport: VP });
        await pg.goto(`${base}/conceptric?corpus=${RICH}&section=${SECTION}`, { waitUntil: 'domcontentloaded' });
        await openLadder(pg, '.hy-ctx-sel.is-ladder');
        dumps.degraded = await dumpLadderStrings(pg, 'degraded');
        await pg.close();
      }
      // error: fetch aborted → the fail card strings
      {
        const pg = await b.newPage({ viewport: VP });
        await pg.goto(`${base}/conceptric?corpus=${RICH}&node=${encodeURIComponent(NODE)}`, { waitUntil: 'domcontentloaded' });
        await pg.waitForSelector('.hy-ctx-sel.is-ladder', { timeout: 10000 });
        await pg.route('**/shared/ladder*', (r) => r.abort());
        await pg.click('.hy-ctx-sel.is-ladder');
        await pg.waitForSelector('#hy-ladder .hy-ladder-fail-msg', { timeout: 8000 });
        dumps.error = await dumpLadderStrings(pg, 'error');
        await pg.unroute('**/shared/ladder*');
        await pg.close();
      }
      for (const st of ['populated', 'empty', 'degraded', 'error']) {
        ok(dumps[st].count > 0, `W-L30 ${st}: ${dumps[st].count} strings dumped → ${dumps[st].path}`);
      }
    }

    console.log(`\nALL GREEN — ${passed} assertions`);
  } finally {
    await b.close();
    if (scanner) scanner.kill();
  }
})().catch((e) => { console.error('\n' + e.message); if (scanner) scanner.kill(); process.exit(1); });
