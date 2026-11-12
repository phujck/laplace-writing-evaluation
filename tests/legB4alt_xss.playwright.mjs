// legB4alt XSS probe — renders the REAL served altitude.html in Chromium with a
// POISONED /altitude/data payload (route-intercepted, so no ledger / live corpus
// is touched) and proves every injected sink is inert: node essence / kind / id,
// section title, derivation rule, grade-mismatch note, and the wiring-back values.
//
// The recurring session class is the single-quote-attr / <img onerror> break-out.
// This asserts: (a) no injected <img>/<svg>/<script> element exists in the DOM
// (esc() turned them to text), (b) no request went out for the poison image srcs,
// (c) no dialog fired, (d) no window.__xss* sentinel got set.
//
//   run:  node tests/legB4alt_xss.playwright.mjs
// Exits 0 all-green, non-zero on the first failed assertion.
import { createRequire } from 'module';
import { spawnSync, spawn } from 'child_process';
import { execSync } from 'child_process';
import net from 'net';

const require = createRequire(import.meta.url);
const PW_ROOT = execSync('npm root -g').toString().trim() + '/playwright';
const { chromium } = require(PW_ROOT);
const CHROME = execSync('ls /opt/pw-browsers/chromium-*/chrome-linux/chrome')
  .toString().trim().split('\n')[0];
const PY = 'python3';
const CORPUS = 'subset-sum-itqde';

let passed = 0;
function ok(cond, msg) { if (!cond) throw new Error('ASSERT FAILED: ' + msg); passed++; console.log('  ok -', msg); }
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

// a full altitude payload with an XSS bomb in every string sink the surface renders
const IMG = '<img src=xss-essence onerror="window.__xss_essence=1">';
const KIND = '"><svg onload="window.__xss_kind=1">';
const NID = '<img src=xss-nid onerror="window.__xss_nid=1">';
const TITLE = '<img src=xss-title onerror="window.__xss_title=1">';
const NOTE = '<script>window.__xss_note=1</script>';
const SECREF = '<img src=xss-beat onerror="window.__xss_beat=1">';

function poison() {
  const nodeCard = {
    id: NID, kind: KIND, grade: 2, missing: false, essence: IMG,
    section_ref: SECREF, latex_label: null, retired: false,
  };
  const deriv = {
    id: NID, grade: 2, dep_depth: 2, stored_grade: 0, is_postulate: false,
    spine_elevated: false,
    rule: '<img src=xss-rule onerror="window.__xss_rule=1">',
    deps: [{ id: '<img src=xss-dep onerror="window.__xss_dep=1">', grade: 1, kind: KIND, is_grade_setter: true }],
  };
  return {
    corpus: CORPUS, open_at: 'nodes', g_max: 4, n_nodes: 1,
    grade_derivation_exposed: true,
    anchor: { raw: NID, kind: 'node', section: TITLE, node: NID },
    ladder: ['nodes', 'grade_shells', 'spine', 'plan_prose'],
    altitudes: {
      nodes: { anchor_ids: [NID], nodes: [nodeCard], neighborhood: {
        below: [{ id: NID, grade: 1 }], above: [], lateral: [] },
        join_down: 'jd' },
      grade_shells: {
        g_max: 4,
        shells: [{ grade: 0, global_count: 1, is_floor: true, is_spine_tier: false,
                   anchor_ids: [], anchor_nodes: [], global_sample: [{ id: NID, kind: KIND }], global_truncated: 0 },
                 { grade: 2, global_count: 1, is_floor: false, is_spine_tier: false,
                   anchor_ids: [NID], anchor_nodes: [nodeCard], global_sample: [{ id: NID, kind: KIND }], global_truncated: 0 }],
        anchor_grades: { [NID]: 2 },
        derivation: { [NID]: deriv },
        grade_mismatch: { count: 1, rows: [{ id: NID, stored: 0, derived: 2 }],
          stored_grade_histogram: { 0: 1 }, note: NOTE },
        join_down: 'jd',
      },
      spine: { rail: [{ id: NID, ord: 0, grade: 4, anchor: true, term: TITLE, narrative: NOTE }],
        anchor_beats: [SECREF], storyboard_link: '/storyboard?corpus=' + CORPUS, join_down: 'jd' },
      plan_prose: {
        section: { id: TITLE, title: TITLE, job: IMG, nodes_in_order: [NID] },
        owning_section_id: TITLE,
        artefact: { compiled: true, state: KIND, revision: 1, created: TITLE,
          staleness: { stale: true, n_newer: 1, newer_sources: [NID], note: NOTE } },
        links: { projection: '/projection', review: '/review', storyboard: '/storyboard' },
        join_down: 'jd',
      },
    },
    wiring_back: {
      pid: NID, pid_to_nodes: { join: 'j', section: TITLE, node_ids: [NID] },
      nodes_to_grades: { join: 'j', grades: { [NID]: 2 } },
      grades_to_beats: { join: 'j', beats: [SECREF] },
      beats_to_section: { join: 'j', section: TITLE },
      section_to_artefact: { join: 'j', tex: NID + '.tex', pdf: 'main.pdf' },
    },
  };
}

let scanner;
(async () => {
  const repoRoot = spawnSync(PY, ['-c', 'from laplace.web.scanner import _repo_root; print(_repo_root().resolve())'],
    { encoding: 'utf-8' }).stdout.trim();
  const port = await freePort();
  scanner = spawn(PY, ['-m', 'laplace.web.scanner', '--port', String(port)], { cwd: repoRoot, stdio: 'ignore' });
  await waitFor(`http://127.0.0.1:${port}/altitude`);

  const b = await chromium.launch({ executablePath: CHROME });
  const badRequests = [];
  const dialogs = [];
  try {
    const pg = await b.newPage({ viewport: { width: 1400, height: 950 } });
    pg.on('dialog', d => { dialogs.push(d.message()); d.dismiss().catch(() => {}); });
    pg.on('request', req => { const u = req.url(); if (/xss-/.test(u)) badRequests.push(u); });

    // intercept the data fetch and serve the poison — the surface render path is real
    await pg.route('**/altitude/data**', route => route.fulfill({
      status: 200, contentType: 'application/json; charset=utf-8', body: JSON.stringify(poison()),
    }));

    await pg.goto(`http://127.0.0.1:${port}/altitude?corpus=${CORPUS}&anchor=x`, { waitUntil: 'networkidle' });
    // focus each altitude so its panel body renders, and open the node drawer + a shell
    for (const k of ['plan_prose', 'spine', 'grade_shells', 'nodes']) {
      await pg.evaluate(kk => window.focusPanel && window.focusPanel(kk), k).catch(() => {});
    }
    // click a node card to open the derivation drawer, and a shell to expand it
    await pg.evaluate(() => { const el = document.querySelector('[data-node]'); if (el) el.click(); });
    await pg.evaluate(() => { const el = document.querySelector('.shell'); if (el) el.click(); });
    await pg.waitForTimeout(300);

    // (a) the poison strings are present as TEXT somewhere (proves they rendered, escaped)
    const bodyText = await pg.evaluate(() => document.body.textContent);
    ok(bodyText.includes('onerror') || bodyText.includes('onload') || bodyText.includes('<img'),
       'the injected markup rendered as TEXT (escaped), not as live DOM');

    // (b) NO injected element instantiated in the DOM
    const injected = await pg.evaluate(() => {
      const imgs = [...document.images].filter(i => /xss-/.test(i.getAttribute('src') || ''));
      const svgOnload = [...document.querySelectorAll('svg')].filter(s => s.getAttribute('onload'));
      const scripts = [...document.querySelectorAll('script')].filter(s => /__xss/.test(s.textContent || ''));
      return { imgs: imgs.length, svgs: svgOnload.length, scripts: scripts.length };
    });
    ok(injected.imgs === 0, 'no injected <img> element was instantiated (essence/id/title/etc.)');
    ok(injected.svgs === 0, 'no injected <svg onload> element was instantiated (kind sink)');
    ok(injected.scripts === 0, 'no injected <script> element was instantiated (note sink)');

    // (c) no sentinel fired
    const sentinels = await pg.evaluate(() => Object.keys(window).filter(k => k.startsWith('__xss')));
    ok(sentinels.length === 0, 'no window.__xss* sentinel was set — every handler stayed inert');

    // (d) no network request for a poison image src, no dialog
    ok(badRequests.length === 0, 'the browser made NO request for any poison image src');
    ok(dialogs.length === 0, 'no dialog/alert fired');

    console.log(`\nALL ${passed} XSS assertions green — altitude surface is inert.`);
  } finally {
    await b.close();
    if (scanner) scanner.kill('SIGKILL');
  }
})().catch(e => { console.error(e); if (scanner) scanner.kill('SIGKILL'); process.exit(1); });
