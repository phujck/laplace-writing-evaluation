// W-WELD — the one continuous walk. The surfaces were built in waves; this walk
// proves they are ONE instrument: a stranger crosses every surface in a single
// session and the grammar holds at every crossing — the journey lit, the context
// header present, the return doors speaking journey vocabulary (never a raw
// path), the corpus riding every hop, zero page errors end to end, and no
// horizontal scroll anywhere. This is the integration bar his W-WELD commission
// named ("these surfaces need to be integrated. Or are we going to repeat
// history"); it runs on the finished tree, after every wave has landed.
import { spawn, execSync } from 'child_process';
import net from 'net';
import http from 'http';
import {
  resolvePython, resolveChromeExecutable, resolvePlaywrightChromium, scannerSpawnEnv,
} from './_walk_boot.mjs';

// Platform-general resolution (built general, never box-scoped — the dev box is
// Windows with a repo venv and no node-side Playwright; the remote box is Linux with a
// global npm playwright + /opt/pw-browsers). See tests/_walk_boot.mjs.
const chromium = resolvePlaywrightChromium();
const CHROME = resolveChromeExecutable();
const PY = resolvePython();
const CORPUS = 'paper_falqon';

if (!chromium) {
  console.error('ENGINE WELD: no node-side Playwright package resolvable here (checked local');
  console.error('  module resolution and `npm root -g`). That is expected on the Windows dev box —');
  console.error('  it has no node_modules/playwright and no global npm playwright install.');
  console.error('  Run the ported Python walk instead (same four legs, same assertions):');
  console.error('    .venv\\Scripts\\python.exe scripts/run_playwright_walks.py --weld-python');
  process.exit(1);
}

let passed = 0;
function ok(cond, msg) { if (!cond) throw new Error('ASSERT FAILED: ' + msg); passed++; console.log('  ok -', msg); }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function freePort() { return new Promise((res) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); }); }
function waitFor(url, tries = 80) { return new Promise((res, rej) => { const tick = (n) => { const req = http.get(url, (r) => { r.resume(); res(true); });
  req.on('error', () => n <= 0 ? rej(new Error('server never came up')) : setTimeout(() => tick(n - 1), 250)); }; tick(tries); }); }
// a plain out-of-band GET, used to fetch the SERVED /shared/journey feed independent of
// the page's own fetch — proving render == feed rather than trusting the page's copy.
function fetchJSON(url) { return new Promise((res, rej) => { http.get(url, (r) => { let d = '';
  r.on('data', (c) => { d += c; }); r.on('end', () => { try { res(JSON.parse(d)); } catch (e) { rej(e); } }); }).on('error', rej); }); }

let scanner;
(async () => {
  const repoRoot = execSync(`"${PY}" -c "from laplace.web.scanner import _repo_root; print(_repo_root().resolve())"`).toString().trim();
  const port = await freePort();
  scanner = spawn(PY, ['-m', 'laplace.web.scanner', '--port', String(port)], {
    cwd: repoRoot, stdio: 'ignore', env: scannerSpawnEnv(),
  });
  await waitFor(`http://127.0.0.1:${port}/`);
  const base = `http://127.0.0.1:${port}`;

  let b;
  try {
    b = await chromium.launch(CHROME ? { executablePath: CHROME } : {});
  } catch (e) {
    console.error('ENGINE WELD: chromium launch failed'
      + (CHROME ? ` (executablePath=${CHROME})` : ' (no Chromium executable resolved — checked '
        + 'PLAYWRIGHT_BROWSERS_PATH, %LOCALAPPDATA%/ms-playwright, /opt/pw-browsers)') + ':');
    console.error('  ' + e.message);
    scanner.kill();
    process.exit(1);
  }
  const pg = await b.newPage({ viewport: { width: 1440, height: 900 } });
  const errs = []; pg.on('pageerror', (e) => errs.push(String(e)));

  // the grammar every stop must wear — asserted identically at every crossing
  async function grammar(name, { litStage = null, needContext = true } = {}) {
    await pg.waitForSelector('#hy-shell', { timeout: 15000 });
    await sleep(600);
    const g = await pg.evaluate(() => {
      const lit = [...document.querySelectorAll('.hy-stage.on, .hy-stage.on-door')]
        .map((a) => (a.querySelector('.st-t') || a).textContent.trim());
      const ctx = document.querySelector('#hy-context');
      const from = document.querySelector('.hy-from');
      return {
        lit,
        hasContext: !!ctx,
        fromText: from ? from.textContent.trim() : null,
        hymn: !!document.querySelector('link[href*="hymn.css"]'),
        hscroll: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
      };
    });
    ok(g.hymn, `${name}: rides the one hymn sheet`);
    ok(!g.hscroll, `${name}: no horizontal scroll at 1440`);
    if (needContext) ok(g.hasContext, `${name}: the context header is present`);
    if (litStage) ok(g.lit.some((t) => t.includes(litStage)), `${name}: the ${litStage} stage is lit (lit: ${g.lit.join('|') || 'none'})`);
    if (g.fromText) ok(!/\//.test(g.fromText.replace('← from', '')), `${name}: the return door speaks journey vocabulary ("${g.fromText}")`);
    return g;
  }

  // ═══ LEG A — the process spine, crossed in paper order ═══
  console.log('\n=== leg A: the spine, Home through Desk ===');
  await pg.goto(`${base}/?corpus=${CORPUS}`, { waitUntil: 'domcontentloaded' });
  const home = await grammar('Home', { litStage: 'Home', needContext: false });
  const spineWords = await pg.evaluate(() =>
    [...document.querySelectorAll('.hy-stage')].map((a) => ({
      t: (a.querySelector('.st-t') || a).textContent.trim(),
      w: (a.querySelector('.st-w') || {}).textContent || '',
    })));
  ok(spineWords.filter((s) => s.w.trim()).length >= 4, `Home: live state words ride the spine (${spineWords.filter((s) => s.w.trim()).length} stages worded)`);
  // MECHANISM, not data: the Desk word depends on live corpus state (owed_to_author) —
  // asserting it is non-empty was coupled to whatever paper_falqon happens to owe right
  // now (rots green-to-red or red-to-green as the desk empties/fills). Instead fetch the
  // SAME /shared/journey feed the page itself renders from and assert the rendered DOM
  // word agrees with the served word — true whether the desk is empty or full today.
  const journeyFeed = await fetchJSON(`${base}/shared/journey?corpus=${CORPUS}`);
  const deskFeedWord = (journeyFeed.stages.find((s) => s.id === 'desk') || {}).word;
  const deskFeedText = deskFeedWord ? String(deskFeedWord).trim() : '';
  const deskDomText = ((spineWords.find((s) => /Desk/i.test(s.t)) || { w: '' }).w || '').trim();
  ok(deskDomText === deskFeedText, `Home: the Desk stage word agrees with the served journey feed ('${deskDomText}' == '${deskFeedText}')`);

  const spine = [
    ['Grow', 'Grow'], ['Shape', 'Shape'], ['Read', 'Read'], ['Machine', 'Machine'], ['Desk', 'Desk'],
  ];
  for (const [label, lit] of spine) {
    await pg.evaluate((l) => {
      const a = [...document.querySelectorAll('.hy-stage')].find((x) => x.textContent.includes(l));
      if (a) a.click();
    }, label);
    await pg.waitForLoadState('domcontentloaded');
    await grammar(label, { litStage: lit });
    const corpusHeld = await pg.evaluate(() => location.search.includes('corpus=') || !!sessionStorage.length);
    ok(corpusHeld, `${label}: the paper rides the crossing`);
  }

  // ═══ LEG B — the door crossings: Grow's card → Lineage → the editor ═══
  console.log('\n=== leg B: door crossings, Lineage into the editor ===');
  await pg.goto(`${base}/lineage?corpus=${CORPUS}&object=eq:coh-total`, { waitUntil: 'domcontentloaded' });
  await grammar('Lineage (cold object arrival)');
  const lin = await pg.evaluate(() => ({
    focused: !!document.querySelector('[class*="lin-"]'),
    editorDoor: [...document.querySelectorAll('a,button')].some((a) => /open in the editor/i.test(a.textContent)),
  }));
  ok(lin.focused, 'Lineage: the cold ?object= arrival lands in the surface body');
  ok(lin.editorDoor, 'Lineage: the editor crossing is offered at the object');
  await pg.evaluate(() => {
    const a = [...document.querySelectorAll('a,button')].find((x) => /open in the editor/i.test(x.textContent));
    if (a) a.click();
  });
  await pg.waitForLoadState('domcontentloaded');
  await grammar('Read·Judge (arrived from Lineage)', { litStage: 'Read' });

  // ═══ LEG C — the walk back: every return door heals the chain ═══
  console.log('\n=== leg C: the return chain, walked back ===');
  let steps = 0;
  for (; steps < 6; steps++) {
    const from = await pg.evaluate(() => {
      const f = document.querySelector('.hy-from');
      return f ? { text: f.textContent.trim(), ok: !f.textContent.includes('/') } : null;
    });
    if (!from) break;
    ok(from.ok, `walk-back ${steps + 1}: the door names its origin in journey words ("${from.text}")`);
    await pg.evaluate(() => document.querySelector('.hy-from').click());
    await pg.waitForLoadState('domcontentloaded');
    await sleep(500);
  }
  ok(steps >= 1, `the return chain walked back ${steps} crossing(s) without a dead end`);

  // ═══ LEG D — the whole session's health ═══
  console.log('\n=== leg D: the session health ===');
  ok(errs.length === 0, `zero uncaught page errors across the whole walk (${errs.length ? errs[0] : 'clean'})`);

  await b.close(); scanner.kill();
  console.log(`\nENGINE WELD — ${passed} assertions green.`);
})().catch((e) => { console.error(e); if (scanner) scanner.kill(); process.exit(1); });
