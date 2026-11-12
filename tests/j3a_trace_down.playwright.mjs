// J3a — TRACE DOWN (spine §6 / DESIGN_2026-07-15_the-spine.md): a conceptric node → its
// "argues in" sections (the QUARRY door) → a real DOOR that lands on /artefact carrying the
// node selection. Walked as HIM, headless, over a real Chromium against a real scanner — so
// the node→beat→section→page chain is ASSERTED, not narrated. Read-only (no ledger writes):
// it navigates the plan's real node_index, and where the nodemap is absent the honest state
// still renders (the paragraph-level hop asserts what EXISTS).
//
//   run:  node tests/j3a_trace_down.playwright.mjs
//   deps: global `playwright` (npm root -g), Chromium at /opt/pw-browsers, python3 on PATH.
//         Exits 0 all-green, non-zero on the first failed assertion.
import { createRequire } from 'module';
import { spawn, execSync } from 'child_process';
import net from 'net';
import http from 'http';

const require = createRequire(import.meta.url);
const PW_ROOT = execSync('npm root -g').toString().trim() + '/playwright';
const { chromium } = require(PW_ROOT);
const CHROME = execSync('ls /opt/pw-browsers/chromium-*/chrome-linux/chrome').toString().trim().split('\n')[0];
const PY = 'python3';
const CORPUS = 'subset-sum-itqde';

let passed = 0;
function ok(cond, msg){ if(!cond) throw new Error('ASSERT FAILED: ' + msg); passed++; console.log('  ok -', msg); }
function freePort(){ return new Promise((res, rej) => {
  const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); s.on('error', rej); }); }
function waitFor(url, tries = 60){ return new Promise((res, rej) => {
  const tick = (n) => { const req = http.get(url, (r) => { r.resume(); res(true); });
    req.on('error', () => n <= 0 ? rej(new Error('server never came up')) : setTimeout(() => tick(n - 1), 250)); }; tick(tries); }); }
function get(port, path){ return new Promise((res, rej) => {
  http.get(`http://127.0.0.1:${port}${path}`, (r) => { let b = ''; r.on('data', d => b += d); r.on('end', () => res({ status: r.statusCode, body: b })); }).on('error', rej); }); }

let scanner;
(async () => {
  const repoRoot = execSync(`${PY} -c "from laplace.web.scanner import _repo_root; print(_repo_root().resolve())"`).toString().trim();
  const port = await freePort();
  scanner = spawn(PY, ['-m', 'laplace.web.scanner', '--port', String(port)], { cwd: repoRoot, stdio: 'ignore' });
  await waitFor(`http://127.0.0.1:${port}/`);

  // the plan's node→section index is the truth the door must reflect (read directly from the API).
  const plan = JSON.parse((await get(port, `/shared/plan?corpus=${CORPUS}`)).body);
  ok(plan && plan.node_index && Object.keys(plan.node_index).length, 'the corpus has a plan with a node_index');

  // pick a node that BOTH argues in a section AND resolves in the conceptric (has content).
  let node = null, section = null;
  for (const [nid, info] of Object.entries(plan.node_index)) {
    const c = JSON.parse((await get(port, `/corpus/content?corpus=${CORPUS}&id=${encodeURIComponent(nid)}`)).body);
    if (c && c.kind) { node = nid; section = info.section; break; }
  }
  ok(node, `the plan yields a conceptric node that argues in a section (${node} → ${section})`);

  const b = await chromium.launch({ executablePath: CHROME });
  try {
    const pg = await b.newPage({ viewport: { width: 1400, height: 900 } });
    const pageErrors = []; pg.on('pageerror', (e) => pageErrors.push(String(e)));

    // deep-link the node into the conceptric read-and-rule MAP (URL-canonical selection:
    // ?node=). E2 rebuild: /conceptric became the growth cockpit; the graded-descent
    // board+inspector (conceptric-panes.mjs — the #cx-board/#cx-right surface this walk
    // traces) is retained at /conceptric/map, reachable as an altitude from the cockpit brief.
    console.log(`\n[j3a] GET /conceptric/map?corpus=${CORPUS}&node=${node}`);
    await pg.goto(`http://127.0.0.1:${port}/conceptric/map?corpus=${CORPUS}&node=${encodeURIComponent(node)}`,
      { waitUntil: 'domcontentloaded' });
    await pg.waitForSelector('#cx-right .hy-ins', { timeout: 10000 });

    // the node card names its id — the selection landed.
    const nid = await pg.$eval('#cx-right .hy-nid', (e) => e.textContent.trim());
    ok(nid === node, `the node card renders the selected node (${nid})`);

    // "ARGUES IN": the section is listed as a real hop. (W3 reface: the argues-in lane is
    // `.cx-lane > .cx-argrow`; each row's `.hy-role.grade` names the section id and its first
    // `a.hy-door` is the "read §<sec> →" QUARRY door onto /artefact — same chair-truth, new DOM.)
    await pg.waitForSelector('.cx-argrow', { timeout: 8000 });
    const argSecs = await pg.$$eval('.cx-argrow .hy-role.grade', (els) => els.map((e) => e.textContent.trim()));
    ok(argSecs.includes(section), `"argues in" lists the plan section ${section} (${JSON.stringify(argSecs)})`);

    // the READ door is a real <a href> carrying the node selection into /artefact (the QUARRY door).
    const readHref = await pg.$eval('.cx-argrow a.hy-door', (a) => a.getAttribute('href'));
    ok(/^\/artefact\?/.test(readHref), `the "read" hop is a real /artefact door (${readHref})`);
    const hrefNode = new URL(readHref, 'http://x').searchParams.get('node');
    ok(hrefNode === node, `the door carries the node selection (?node=${hrefNode})`);

    // FOLLOW the door: it lands on /artefact with the node selection carried through (J3 chain).
    await pg.click('.cx-argrow a.hy-door');
    await pg.waitForURL('**/artefact?**', { timeout: 10000 });
    const landed = new URL(pg.url());
    ok(landed.pathname === '/artefact', 'the door landed on /artefact');
    ok(landed.searchParams.get('node') === node, `the node selection is carried to the reader (?node=${landed.searchParams.get('node')})`);

    // the paragraph-level hop asserts what EXISTS: the reader shell mounts (honest state where the
    // nodemap is absent — the reader renders its own message, never a blank/crash).
    await pg.waitForSelector('#art', { timeout: 10000 });
    ok(await pg.$('#art'), 'the reader shell mounts on landing (honest state renders)');

    ok(pageErrors.length === 0, `no uncaught page errors during the trace-down (${JSON.stringify(pageErrors.slice(0, 3))})`);
    console.log(`\n[j3a] ALL GREEN — ${passed} assertions`);
  } finally {
    await b.close();
    if (scanner) scanner.kill();
  }
})().catch((e) => { console.error('\n' + e.message); if (scanner) scanner.kill(); process.exit(1); });
