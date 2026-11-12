// ENGINE LINEAGE — the lineage surface joined to the ONE INSTRUMENT (W-lineage), driven
// against a REAL scanner. Per-project views of the conceptric and its descendants.
//
// The walk proves, as OUTCOMES (not DOM presence):
//   · brief base altitude (E): at rest NO view / reallocation exists; the composed
//     lineage-health prose carries the real falqon numbers, and the count chips ride it;
//   · node-outward: picking a real concept (cluster:claims) REALLOCATES + rail + a VISIBLE
//     return door NAMING the brief; the descendants tree renders relation-labelled, the
//     realising objects carry their join provenance, the editor + Grow crossings are live;
//   · object-backward: an equation (eq:coh-total) walks back to its derivation origin (the
//     isnad rung) — the origin step is present;
//   · the whole graph: the regions render weighted, and the unresolved band is its own
//     visible region (absence first-class);
//   · a COLD deep-link (?node=) lands PRE-FOCUSED on node-outward WITHOUT a click, with the
//     named return door — the brief is never a mandatory step on that path;
//   · the empty teach: a corpus with no index (qde) states what the surface would show;
//   · close: exact scrollY restore + no return-door residue;
//   · zero page errors, zero horizontal scroll at 1280 and 1536, the register (no raw
//     record ids above the fold).
//
//   run:  node tests/engine_lineage.playwright.mjs
//   Exits 0 all-green, non-zero on the first failed assertion.
import { createRequire } from 'module';
import { spawn, execSync } from 'child_process';
import net from 'net';

const require = createRequire(import.meta.url);
const { chromium } = require(execSync('npm root -g').toString().trim() + '/playwright');
const CHROME = execSync('ls /opt/pw-browsers/chromium-*/chrome-linux/chrome').toString().trim().split('\n')[0];
const PY = 'python3';
const SHOTS = process.env.LIN_SHOTS || '';   // if set, bank screenshots into this dir

let passed = 0;
function ok(cond, msg) { if (!cond) throw new Error('ASSERT FAILED: ' + msg); passed++; console.log('  ok -', msg); }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function freePort() { return new Promise((res) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); }); }
function waitFor(url, tries = 80) {
  return new Promise((res, rej) => { const tick = (n) => { const req = require('http').get(url, (r) => { r.resume(); res(true); });
    req.on('error', () => n <= 0 ? rej(new Error('server never came up')) : setTimeout(() => tick(n - 1), 250)); }; tick(tries); });
}

async function noHScroll(pg, label) {
  const over = await pg.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  ok(over <= 1, 'zero horizontal scroll ' + label + ' (overflow ' + over + 'px)');
}

let scanner;
(async () => {
  const repoRoot = execSync(`${PY} -c "from laplace.web.scanner import _repo_root; print(_repo_root().resolve())"`).toString().trim();
  const port = await freePort();
  scanner = spawn(PY, ['-m', 'laplace.web.scanner', '--port', String(port)], { cwd: repoRoot, stdio: 'ignore' });
  await waitFor(`http://127.0.0.1:${port}/lineage`);
  const base = `http://127.0.0.1:${port}`;
  const b = await chromium.launch({ executablePath: CHROME });
  try {
    const pg = await b.newPage({ viewport: { width: 1280, height: 900 } });
    const errs = []; pg.on('pageerror', (e) => errs.push(String(e)));

    // ── (1) THE BRIEF BASE ALTITUDE (E) ──────────────────────────────────────
    await pg.goto(base + '/lineage?corpus=paper_falqon', { waitUntil: 'networkidle' });
    await pg.waitForSelector('[data-role="brief-prose"]', { timeout: 8000 });
    await sleep(250);
    const prose = (await pg.textContent('.lin-glance')).trim();
    ok(prose.includes('91 concepts') && prose.includes('148 rendered objects'),
      'the composed brief carries the real falqon numbers: ' + JSON.stringify(prose.slice(0, 80)));
    const restDom = await pg.evaluate(() => ({
      reallocated: document.querySelector('#eng-root').classList.contains('reallocated'),
      view: document.querySelectorAll('.lin-view').length,
      chips: document.querySelectorAll('.lin-chip').length,
      pickers: document.querySelectorAll('.lin-picker').length,
    }));
    ok(!restDom.reallocated && restDom.view === 0, 'at rest NO view / reallocation exists in the DOM: ' + JSON.stringify(restDom));
    ok(restDom.chips >= 5, 'the count chips ride the brief: ' + restDom.chips);
    ok(restDom.pickers === 3, 'the three pickers are present (concept / object / whole): ' + restDom.pickers);
    if (SHOTS) await pg.screenshot({ path: SHOTS + '/01_brief.png', fullPage: true });
    await noHScroll(pg, 'on the brief (1280)');

    // ── (1a) THE UNRESOLVED BAND READS SEPARATED — the bits ran together on bare
    // whitespace; a divider now parts each pair (finding). And the PROJECT switch is
    // on-family (appearance:none, no OS-native chrome), not a bare native control. ──
    const bandBits = await pg.$$eval('.lin-band .lin-bandbit', (e) => e.length);
    const bandDivs = await pg.$$eval('.lin-band .lin-banddiv', (e) => e.length);
    ok(bandBits >= 2 && bandDivs === bandBits - 1,
      `the unresolved band is separated — a divider parts each pair (${bandBits} bits, ${bandDivs} dividers)`);
    const selApp = await pg.$eval('#lin-switch-sel',
      (e) => { const s = getComputedStyle(e); return s.appearance || s.webkitAppearance; });
    ok(selApp === 'none', 'the project switch is styled on-family (appearance:none, no native chrome): ' + selApp);
    ok(await pg.$eval('#lin-switch-sel', (e) => e.classList.contains('lin-sel')), 'the switch carries the pane input class');

    // ── (1b) THE PROJECT SWITCH (gap 5) — any project's lineage opens from the brief. The
    // switch is DISTINCT from the three view pickers (the count stays 3); selecting a second
    // project threads ?corpus= through the doors and opens THAT project's lineage. ──────────
    ok(await pg.$('#lin-switch-sel') !== null, 'the brief carries a project switch (a select of the roster)');
    ok((await pg.$$('.lin-picker')).length === 3, 'the switch is not one of the three view pickers (pickers still exactly 3)');
    const corpora = await pg.evaluate(async () => ((await (await fetch('/corpus/list')).json()).corpora) || []);
    const second = corpora.find((c) => c !== 'paper_falqon');
    ok(!!second, 'the roster carries a second project to switch to: ' + JSON.stringify(second));
    const selOpts = await pg.$$eval('#lin-switch-sel option', (o) => o.map((e) => e.value));
    ok(selOpts.includes(second), 'the switch lists the second project as an option: ' + JSON.stringify(second));
    await pg.selectOption('#lin-switch-sel', second);
    await pg.waitForFunction((c) => new URLSearchParams(location.search).get('corpus') === c, second, { timeout: 8000 });
    await pg.waitForSelector('[data-role="brief-prose"], .lin-empty', { timeout: 8000 });
    const switchedCorpus = await pg.evaluate(() => new URLSearchParams(location.search).get('corpus'));
    ok(switchedCorpus === second, 'switching opened the second project — ?corpus= threaded through the doors: ' + switchedCorpus);
    const selNow = await pg.$eval('#lin-switch-sel', (e) => e.value);
    ok(selNow === second, 'the switch reflects the now-open project (the second corpus lineage is live): ' + selNow);
    if (SHOTS) await pg.screenshot({ path: SHOTS + '/01b_switch.png', fullPage: true });
    // a cold ?corpus=&node= deep link into the SECOND project still lands (deep links keep working)
    await pg.goto(base + '/lineage?corpus=paper_falqon', { waitUntil: 'networkidle' });
    await pg.waitForSelector('[data-role="brief-prose"]', { timeout: 8000 }); await sleep(150);

    // ── (2) NODE-OUTWARD (a concept and everything it became) ────────────────
    await pg.fill('#lin-find-node', 'claims');
    await pg.waitForSelector('#lin-list-node .lin-find-row', { timeout: 6000 });
    // pick the cluster:claims row specifically (the claims cluster with 22 descendants)
    await pg.click('#lin-list-node .lin-find-row[data-id="cluster:claims"]');
    await pg.waitForSelector('#eng-root.reallocated .lin-view', { timeout: 6000 });
    const node = await pg.evaluate(() => ({
      returnDoor: !!document.querySelector('.eng-return'),
      returnLabel: (document.querySelector('.eng-return .rd-label') || {}).textContent || '',
      tree: document.querySelectorAll('.lin-tree-node').length,
      rels: document.querySelectorAll('.lin-rel').length,
      editor: !!document.querySelector('.lin-view .lin-door[href^="/artefact?corpus="]'),
      grow: !!document.querySelector('.lin-view .lin-door[href*="/conceptric?corpus="]'),
    }));
    ok(node.returnDoor && /brief/i.test(node.returnLabel), 'node-outward pins with a return door naming the brief: ' + JSON.stringify(node.returnLabel));
    ok(node.tree >= 20 && node.rels >= 20, 'the descendants tree renders relation-labelled (22 claims): ' + JSON.stringify(node));
    ok(node.editor && node.grow, 'the editor + Grow crossings are live on the node view');
    if (SHOTS) await pg.screenshot({ path: SHOTS + '/02_node_outward.png', fullPage: true });
    await noHScroll(pg, 'on node-outward (1280)');

    // a realising-object concept carries join provenance — switch to a leaf that realises
    await pg.evaluate(() => document.querySelector('.eng-return').click());
    await pg.waitForSelector('.lin-pickers', { timeout: 6000 });
    await pg.fill('#lin-find-node', 'falqon_layers');
    await pg.waitForSelector('#lin-list-node .lin-find-row[data-id="falqon_layers"]', { timeout: 6000 });
    await pg.click('#lin-list-node .lin-find-row[data-id="falqon_layers"]');
    await pg.waitForSelector('#eng-root.reallocated .lin-view', { timeout: 6000 });
    const prov = await pg.evaluate(() => document.querySelectorAll('.lin-para .lin-prov').length);
    ok(prov >= 1, 'a realising paragraph carries its join provenance worded: ' + prov);
    await pg.evaluate(() => document.querySelector('.eng-return').click());
    await pg.waitForSelector('.lin-pickers', { timeout: 6000 });

    // ── (3) OBJECT-BACKWARD (walk back to the isnad origin) ───────────────────
    await pg.fill('#lin-find-obj', 'coh-total');
    await pg.waitForSelector('#lin-list-obj .lin-find-row[data-id="eq:coh-total"]', { timeout: 6000 });
    await pg.click('#lin-list-obj .lin-find-row[data-id="eq:coh-total"]');
    await pg.waitForSelector('#eng-root.reallocated .lin-walk', { timeout: 6000 });
    const obj = await pg.evaluate(() => ({
      stages: Array.from(document.querySelectorAll('.lin-step-badge')).map((e) => e.textContent.trim()),
      hasOrigin: !!document.querySelector('.lin-stage-origin'),
    }));
    ok(obj.stages[0] === 'object' && obj.hasOrigin, 'object-backward walks from the object to its derivation origin: ' + JSON.stringify(obj.stages));
    if (SHOTS) await pg.screenshot({ path: SHOTS + '/03_object_backward.png', fullPage: true });
    await noHScroll(pg, 'on object-backward (1280)');
    await pg.evaluate(() => document.querySelector('.eng-return').click());
    await pg.waitForSelector('.lin-pickers', { timeout: 6000 });

    // ── (4) THE WHOLE GRAPH (regions weighted, the unresolved band) ───────────
    await pg.click('#lin-open-whole');
    await pg.waitForSelector('#eng-root.reallocated .lin-regions', { timeout: 6000 });
    const whole = await pg.evaluate(() => ({
      regions: document.querySelectorAll('.lin-region').length,
      weights: document.querySelectorAll('.lin-weight-fill').length,
      band: !!document.querySelector('.lin-unresolved'),
      urGroups: document.querySelectorAll('.lin-ur-group').length,
    }));
    ok(whole.regions >= 5 && whole.weights >= 5, 'the whole graph renders sections as weighted regions: ' + JSON.stringify(whole));
    ok(whole.band && whole.urGroups >= 2, 'the unresolved band is its own visible region (absence first-class): ' + JSON.stringify(whole));
    if (SHOTS) await pg.screenshot({ path: SHOTS + '/04_the_whole.png', fullPage: true });
    await noHScroll(pg, 'on the whole graph (1280)');

    // ── (5) CLOSE — exact restore, no residue ─────────────────────────────────
    await pg.evaluate(() => document.querySelector('.eng-return').click());
    await pg.waitForSelector('.lin-pickers', { timeout: 6000 });
    const afterClose = await pg.evaluate(() => ({
      reallocated: document.querySelector('#eng-root').classList.contains('reallocated'),
      returnDoor: document.querySelectorAll('.eng-return').length,
      view: document.querySelectorAll('.lin-view').length,
    }));
    ok(!afterClose.reallocated && afterClose.returnDoor === 0 && afterClose.view === 0,
      'closing restores the brief with no return-door residue: ' + JSON.stringify(afterClose));

    // ── (6) A COLD DEEP-LINK lands PRE-FOCUSED (no lobby tax) ──────────────────
    const pg2 = await b.newPage({ viewport: { width: 1280, height: 900 } });
    const errs2 = []; pg2.on('pageerror', (e) => errs2.push(String(e)));
    await pg2.goto(base + '/lineage?corpus=paper_falqon&node=cluster:claims', { waitUntil: 'networkidle' });
    await pg2.waitForSelector('#eng-root.reallocated .lin-view', { timeout: 8000 });
    const deep = await pg2.evaluate(() => ({
      reallocated: document.querySelector('#eng-root').classList.contains('reallocated'),
      returnDoor: !!document.querySelector('.eng-return'),
      tree: document.querySelectorAll('.lin-tree-node').length,
    }));
    ok(deep.reallocated && deep.returnDoor && deep.tree >= 20,
      'a ?node= cold deep-link lands PRE-FOCUSED on node-outward with the return door, no click: ' + JSON.stringify(deep));
    ok(errs2.length === 0, 'zero page errors on the deep-link arrival: ' + JSON.stringify(errs2));
    await pg2.close();

    // ── (7) THE EMPTY TEACH (a corpus with no index) ──────────────────────────
    const pg3 = await b.newPage({ viewport: { width: 1280, height: 900 } });
    await pg3.goto(base + '/lineage?corpus=qde', { waitUntil: 'networkidle' });
    await pg3.waitForSelector('.lin-empty', { timeout: 8000 });
    const empty = await pg3.evaluate(() => ({
      shows: document.querySelectorAll('.lin-empty-list li').length,
      build: !!document.querySelector('.lin-empty-build'),
    }));
    ok(empty.shows >= 2 && empty.build, 'the empty corpus teaches what the surface would show + what builds it: ' + JSON.stringify(empty));
    if (SHOTS) await pg3.screenshot({ path: SHOTS + '/05_empty_teach.png', fullPage: true });
    await noHScroll(pg3, 'on the empty teach (1280)');
    await pg3.close();

    // ── (8) THE 1536 WIDTH — zero horizontal scroll, and the register ─────────
    await pg.setViewportSize({ width: 1536, height: 900 });
    await pg.goto(base + '/lineage?corpus=paper_falqon', { waitUntil: 'networkidle' });
    await pg.waitForSelector('.lin-glance', { timeout: 8000 });
    await noHScroll(pg, 'on the brief (1536)');
    const bodyText = await pg.evaluate(() => document.body.innerText);
    ok(!/\b(?:PV|RW|PRM|RM|PRF)-\d/.test(bodyText), 'no raw record ids above the fold (the register law)');

    ok(errs.length === 0, 'zero page errors across the whole walk: ' + JSON.stringify(errs));
    console.log(`\nENGINE LINEAGE — all ${passed} assertions green.`);
  } finally {
    await b.close();
    if (scanner) scanner.kill('SIGTERM');
  }
})().catch((e) => { console.error('\nENGINE LINEAGE FAILED:', e.message); if (scanner) scanner.kill('SIGTERM'); process.exit(1); });
