// ENGINE DASHBOARD — the dashboard joins the one instrument (W-DASH), driven against a REAL
// scanner in a real Chromium. The walk proves the resting-state law (E), the geometry couplet
// (B), the entry contract (F), and the no-lobby-tax hot-arrival (B.5) as OUTCOMES:
//   · brief base altitude: at rest the composed brief prose + count chips are present and NO
//     card grid exists in the DOM (the inventory is summonable, not resident);
//   · materialise: opening the `projects` count builds the full grid — counts equal the
//     registry (the counts law), every registered project a card;
//   · hover lights a card's state sources: hovering a card lights the count chips it feeds and
//     reveals its glance in the fixed lens (geometrically stable);
//   · descent: opening a project REALLOCATES to its detail with a VISIBLE return door NAMING
//     the brief, and a descent door carrying ?via=dashboard into /conceptric;
//   · the cockpit's return door names the dashboard: after descent the shell arrival echo on
//     /conceptric names the Dashboard (a real door back);
//   · restore exact: close → the brief, exact scrollY, the return door absent from rest;
//   · NO LOBBY TAX: a ?corpus= hot arrival lands PRE-FOCUSED on that project (reallocated),
//     the brief never a mandatory step; the return door is present;
//   · register 0: no raw GT-/DQ-/PV- ids above the fold; body never scrolls sideways at 1280/1536.
//
//   run:  node tests/engine_dashboard.playwright.mjs
//   Exits 0 all-green, non-zero on the first failed assertion.
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
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function freePort() { return new Promise((res) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); }); }
function waitFor(url, tries = 80) {
  return new Promise((res, rej) => { const tick = (n) => { const req = http.get(url, (r) => { r.resume(); res(true); });
    req.on('error', () => n <= 0 ? rej(new Error('server never came up')) : setTimeout(() => tick(n - 1), 250)); }; tick(tries); });
}
function get(port, path) { return new Promise((res, rej) => {
  http.get(`http://127.0.0.1:${port}${path}`, (r) => { let b = ''; r.on('data', (d) => b += d); r.on('end', () => res({ status: r.statusCode, body: b })); }).on('error', rej); }); }

// §C5 write-path proof (gap 4): the New Project door is DRIVEN, creating a real scaffold in the
// registry — the confirmation must survive the re-render — then torn down surgically in the
// finally (this walk is MUTATING_WALKS-marked; the teardown mirrors j6_new_project's).
const NEWPROJ = 'zzz-probe-walk-delete-me';
let scanner, repoRoot;
function cleanupNewProject() {
  if (!repoRoot) return;
  try {
    execSync(`${PY} - <<'PY'
import json, shutil
from pathlib import Path
root = Path(${JSON.stringify(repoRoot)})
name = ${JSON.stringify(NEWPROJ)}
shutil.rmtree(root / "synthetics papers" / name, ignore_errors=True)
for suf in ("", ".jsonl.lock", ".growth.json", ".growth.json.lock"):
    (root / "corpus_friction" / (name + (suf if suf else ".jsonl"))).unlink(missing_ok=True)
reg = root / "registry_projects.json"
if reg.is_file():
    d = json.loads(reg.read_text())
    d["projects"] = [r for r in d.get("projects", []) if r.get("name") != name]
    reg.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\\n")
wo = root / "corpus_friction" / "work_orders.jsonl"
if wo.is_file():
    keep = [l for l in wo.read_text().splitlines() if l.strip() and json.loads(l).get("corpus") != name]
    wo.write_text(("\\n".join(keep) + "\\n") if keep else "")
print("  new-project cleanup:", name)
PY`, { stdio: 'inherit' });
  } catch (e) { console.error('  new-project cleanup error:', e.message); }
}
(async () => {
  repoRoot = execSync(`${PY} -c "from laplace.web.scanner import _repo_root; print(_repo_root().resolve())"`).toString().trim();
  const port = await freePort();
  scanner = spawn(PY, ['-m', 'laplace.web.scanner', '--port', String(port)], { cwd: repoRoot, stdio: 'ignore' });
  await waitFor(`http://127.0.0.1:${port}/`);
  const base = `http://127.0.0.1:${port}`;

  // the live truth the brief + cards must reflect (the lock-step law: one read model)
  const data = JSON.parse((await get(port, '/dashboard/data')).body);
  const brief = JSON.parse((await get(port, '/dashboard/brief')).body);
  const registryN = data.projects.length;
  ok(registryN > 0, 'the live registry carries at least one project (' + registryN + ')');
  ok(brief.counts.projects === registryN, 'the brief count of projects equals the registry (' + registryN + ')');

  const b = await chromium.launch({ executablePath: CHROME });
  try {
    const pg = await b.newPage({ viewport: { width: 1280, height: 800 } });
    const errs = []; pg.on('pageerror', (e) => errs.push(String(e)));
    // track every /dashboard/data fetch — THE PAPERS must paint from the brief (no second
    // serial compute on cold load); the inventory's data fetch is a later, user-triggered read.
    const dataReqs = []; pg.on('request', (r) => { if (r.url().includes('/dashboard/data')) dataReqs.push(Date.now()); });

    // ── (1) THE BRIEF BASE ALTITUDE (E) — cold arrival rests on the composed brief ──────
    await pg.goto(base + '/', { waitUntil: 'domcontentloaded' });
    // the boot brief fetch is async — wait for the rendered count chips (present only after
    // paintBrief runs), never the placeholder <p> that ships in the static shell.
    await pg.waitForSelector('.dash-count[data-count="projects"]', { timeout: 10000 });
    await sleep(200);
    const prose = (await pg.textContent('[data-role="brief-prose"]')).trim();
    ok(prose.length > 40, 'the composed brief prose is present at rest: ' + JSON.stringify(prose.slice(0, 70)));
    ok(prose === brief.brief.glance, 'the resting prose is the server-composed glance VERBATIM (the lock-step law)');
    const restCards = await pg.$$eval('.hy-card[data-project]', (e) => e.length);
    ok(restCards === 0, 'at rest NO card grid exists in the DOM — the inventory is summonable, not resident: ' + restCards);
    const chips = await pg.$$eval('.dash-count[data-count]', (e) => e.map((x) => x.getAttribute('data-count')));
    ok(chips.includes('projects') && chips.includes('decisions') && chips.includes('orders'),
      'the count chips are present (projects / decisions / orders): ' + JSON.stringify(chips));
    ok(await pg.$('.dash-conseq') !== null, 'the ONE most consequential item glance is present at rest');

    // THE PAPERS — the picture paints at rest, in lock-step with the prose, from the brief
    // (no second /dashboard/data fetch on cold load — the killed duplicate compute).
    await pg.waitForSelector('.dash-papers .dpp-h', { timeout: 8000 });
    const livePaperN = brief.papers.filter((p) => p.live).length;
    const paperTiles = await pg.$$eval('.dpp-tile:not(.is-skel)', (e) => e.length);
    ok(paperTiles === livePaperN,
      `THE PAPERS paints one tile per live paper at rest (${paperTiles} tiles = ${livePaperN} live)`);
    // the position words law: a tile serves composed WORDS, never a raw state enum. No
    // underscore-joined caps token (UNDER_CONVERGENCE) may render as a tile's position word.
    const posWords = await pg.$$eval('.dpp-tile:not(.is-skel) .pw', (e) => e.map((x) => x.textContent));
    const rawEnum = posWords.filter((w) => /[A-Z]{2,}_[A-Z]/.test(w));
    ok(rawEnum.length === 0,
      'no raw state enum (underscore-joined caps) serves as a tile position word: ' + JSON.stringify(posWords));
    ok(dataReqs.length === 0,
      'THE PAPERS painted from the brief with NO second /dashboard/data fetch on cold load (' + dataReqs.length + ')');
    // the new-paper door is discoverable AT REST at the shelf edge (birth ≤2 acts, not hunted-for)
    ok(await pg.$('#dpp-new') !== null, 'the "+ new paper" affordance is present at THE PAPERS shelf at rest');

    // body never scrolls sideways at 1280 (the resting brief)
    const hscroll1280 = await pg.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    ok(hscroll1280 <= 1, 'no horizontal body scroll at 1280 (' + hscroll1280 + 'px)');

    // ── (2) MATERIALISE — the inventory behind ONE open; the counts law ─────────────────
    await pg.click('.dash-count[data-count="projects"]');
    await pg.waitForSelector('.hy-card[data-project]', { timeout: 8000 });
    await sleep(200);
    const domNames = await pg.$$eval('.hy-card[data-project]', (e) => e.map((x) => x.getAttribute('data-project')));
    ok(domNames.length === registryN,
      `the counts law holds: the materialised grid (${domNames.length}) equals the registry (${registryN})`);
    for (const p of data.projects) ok(domNames.includes(p.name), 'a card materialised for registered project ' + p.name);
    // the position words law reaches the CARD too: an inventory card's position fact + chips
    // serve composed words, never a raw state enum. No underscore-joined caps token may render
    // in a card's fact values or chips (the position fact is the one this pins; the fold's
    // release-machine evidence line is provenance, out of scope).
    const cardFactWords = await pg.$$eval('.hy-card[data-project] .hy-card-facts .fv', (e) => e.map((x) => x.textContent));
    const cardChipWords = await pg.$$eval('.hy-card[data-project] .hy-card-chips .hy-chip', (e) => e.map((x) => x.textContent));
    const cardEnum = [...cardFactWords, ...cardChipWords].filter((w) => /[A-Z]{2,}_[A-Z]/.test(w));
    ok(cardEnum.length === 0,
      'no raw state enum serves in an inventory card position fact or chip: ' + JSON.stringify(cardEnum));

    // the scaffold SEEDED truth chip still renders (birth landed; W-DASH re-dresses geometry only)
    const scaffold = data.projects.find((p) => !p.live);
    if (scaffold) {
      const scafCard = await pg.$(`.hy-card[data-project="${scaffold.name}"]`);
      ok(/\bis-muted\b/.test(await scafCard.getAttribute('class')), 'a scaffold card is reduced-emphasis (is-muted)');
      ok(await scafCard.$('.hy-chip.is-scaffold') !== null, 'the scaffold keeps its scaffold/SEEDED truth chip');
    }

    // ── (3) HOVER lights a card's state sources (B.4) + the fixed lens ──────────────────
    const liveP = data.projects.find((p) => p.live) || data.projects[0];
    await pg.$eval(`.hy-card[data-project="${liveP.name}"]`, (e) => e.scrollIntoView({ block: 'center' }));
    await sleep(150);
    await pg.hover(`.hy-card[data-project="${liveP.name}"]`);
    await sleep(250);
    ok(await pg.$eval('.eng-lens', (e) => e.classList.contains('on')), 'hovering a card reveals the fixed lens (no reflow)');
    const litProjects = await pg.$$eval('.dash-count[data-count="projects"].lit', (e) => e.length);
    ok(litProjects === 1, 'hover LIGHTS the projects count chip — the card\'s state source is lit');
    await pg.mouse.move(2, 2); await sleep(150);
    ok(await pg.$$eval('.dash-count.lit', (e) => e.length) === 0, 'moving off the card clears the lit sources');

    // ── (4) DESCENT — open a project → reallocate + rail + breadcrumb + named return door ─
    const scrollAtPin = await pg.evaluate(() => { window.scrollTo(0, 0); return Math.round(window.scrollY); });
    await pg.click(`.hy-card[data-project="${liveP.name}"]`); await sleep(350);
    await pg.waitForSelector('#eng-root.reallocated', { timeout: 8000 }).catch(() => {});
    ok(await pg.$eval('#eng-root', (e) => e.classList.contains('reallocated')), 'opening the project REALLOCATED the surface');
    ok(await pg.$('.eng-rail') !== null, 'the context rail is present');
    ok(await pg.$('.eng-breadcrumb') !== null, 'the breadcrumb is present');
    const door = await pg.$('[data-role="return-door"]');
    ok(!!door, 'a return door is present in the focused state');
    const doorLabel = (await pg.textContent('[data-role="return-door"] .rd-label')).trim();
    ok(/back to the brief/i.test(doorLabel), 'the return door NAMES the dashboard brief: ' + JSON.stringify(doorLabel));
    ok(await pg.$eval('[data-role="return-door"]', (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; }),
      'the return door is VISIBLE');
    const descentHref = await pg.$eval('[data-role="descent-door"]', (e) => e.getAttribute('href'));
    ok(descentHref === '/conceptric?corpus=' + encodeURIComponent(liveP.name) + '&via=dashboard',
      'the descent door carries the cockpit route + ?via=dashboard: ' + JSON.stringify(descentHref));

    // ── (5) THE COCKPIT'S RETURN DOOR NAMES THE DASHBOARD (the shell arrival echo) ───────
    await pg.goto(base + descentHref, { waitUntil: 'domcontentloaded' });   // pagehide stamps origin "/"
    await pg.waitForSelector('#hy-shell', { timeout: 10000 });
    const echo = await pg.waitForSelector('.hy-from', { timeout: 8000 }).catch(() => null);
    ok(echo !== null, 'the cockpit shows the arrival echo — a return door back to where the descent came from');
    const echoText = (await pg.textContent('.hy-from')).trim();
    // SUPERSEDED 2026-07-22 (the journey shell): the roster speaks the journey vocabulary —
    // the dashboard's nav name is now "Home" — so the echo names Home, the same door.
    ok(/home/i.test(echoText), 'the cockpit\'s return door NAMES the home surface: ' + JSON.stringify(echoText));
    const echoHref = await pg.$eval('.hy-from', (e) => e.getAttribute('href'));
    ok(new URL(echoHref, base).pathname === '/', 'the return door points back to the dashboard (/): ' + JSON.stringify(echoHref));

    // ── (6) RESTORE EXACT — reopen the dashboard, descend, close, assert the brief ──────
    await pg.goto(base + '/', { waitUntil: 'domcontentloaded' });
    await pg.waitForSelector('.dash-count[data-count="projects"]', { timeout: 10000 }); await sleep(200);
    await pg.click('.dash-count[data-count="projects"]');
    await pg.waitForSelector('.hy-card[data-project]', { timeout: 8000 }); await sleep(150);
    // scroll to a nonzero position, then descend, so close proves an exact restore.
    await pg.$eval(`.hy-card[data-project="${liveP.name}"]`, (e) => e.scrollIntoView({ block: 'center' })); await sleep(150);
    const y0 = await pg.evaluate(() => Math.round(window.scrollY));
    await pg.click(`.hy-card[data-project="${liveP.name}"]`); await sleep(350);
    await pg.waitForSelector('#eng-root.reallocated', { timeout: 8000 }).catch(() => {});
    ok(await pg.$eval('#eng-root', (e) => e.classList.contains('reallocated')), 'descent reallocated (restore leg)');
    await pg.keyboard.press('Escape'); await sleep(300);
    ok(!(await pg.$eval('#eng-root', (e) => e.classList.contains('reallocated'))), 'Esc closed the focus back to the brief');
    ok((await pg.$('[data-role="return-door"]')) === null, 'the return door is ABSENT from the resting DOM (no hidden residue)');
    const y1 = await pg.evaluate(() => Math.round(window.scrollY));
    ok(Math.abs(y1 - y0) <= 2, `exact scrollY restored on close (${y1} ≈ ${y0})`);

    // ── (7) NO LOBBY TAX — a ?corpus= hot arrival lands PRE-FOCUSED (B.5) ────────────────
    await pg.goto(base + '/?corpus=' + encodeURIComponent(liveP.name), { waitUntil: 'domcontentloaded' });
    await pg.waitForSelector('#eng-root.reallocated', { timeout: 10000 });
    ok(await pg.$eval('#eng-root', (e) => e.classList.contains('reallocated')),
      'a hot ?corpus= arrival lands PRE-FOCUSED (reallocated) — the brief is not a toll');
    ok(await pg.$('[data-role="return-door"]') !== null, 'the hot arrival carries the named return door to the brief');
    const hotDescent = await pg.$eval('[data-role="descent-door"]', (e) => e.getAttribute('href'));
    ok(hotDescent.includes('via=dashboard') && hotDescent.includes(encodeURIComponent(liveP.name)),
      'the hot arrival is focused on the named project with its descent door: ' + JSON.stringify(hotDescent));

    // ── (8) REGISTER 0 + no sideways scroll at 1536 ─────────────────────────────────────
    const aboveFold = await pg.evaluate(() => document.querySelector('#dash').innerText);
    ok(!/\b(GT|DQ|PV|RW)-[0-9a-f]{4,}/i.test(aboveFold), 'no raw GT-/DQ-/PV- ids above the fold (register 0)');
    await pg.setViewportSize({ width: 1536, height: 900 }); await sleep(200);
    const hscroll1536 = await pg.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    ok(hscroll1536 <= 1, 'no horizontal body scroll at 1536 (' + hscroll1536 + 'px)');

    // ── (9) TILE DESCEND → Esc → RESTING BRIEF (the exact regression the green suites missed) ──
    // A descent from a PAPERS TILE must materialise only the focus — never dump the full
    // inventory — and Esc must restore the RESTING brief, chip state equal to what is visible.
    await pg.setViewportSize({ width: 1280, height: 800 });
    const livePaper = data.projects.find((p) => p.live);
    if (livePaper) {
      await pg.goto(base + '/', { waitUntil: 'domcontentloaded' });
      await pg.waitForSelector('.dpp-tile:not(.is-skel)', { timeout: 10000 }); await sleep(150);
      // at rest: no inventory materialised, the projects chip is a live button, NOT is-open.
      ok((await pg.$$eval('.hy-card[data-project]', (e) => e.length)) === 0, 'at rest no inventory cards exist before the tile descent');
      ok(await pg.$eval('.dash-count[data-count="projects"]', (e) => e.tagName === 'BUTTON' && !e.classList.contains('is-open')),
        'the projects chip is a live button, not is-open, at rest');
      await pg.click(`.dpp-tile[data-paper="${livePaper.name}"]`); await sleep(350);
      await pg.waitForSelector('#eng-root.reallocated', { timeout: 8000 }).catch(() => {});
      ok(await pg.$eval('#eng-root', (e) => e.classList.contains('reallocated')), 'clicking a PAPERS tile descends (reallocated)');
      // the tile descent did NOT force the full inventory open behind the focus — the
      // inventory container (#dash-mat) stays empty (the focus pane renders only its own card).
      ok((await pg.$$eval('#dash-mat .hy-card[data-project]', (e) => e.length)) === 0, 'the tile descent materialised ONLY the focus — no inventory dumped behind it');
      await pg.keyboard.press('Escape'); await sleep(300);
      ok(!(await pg.$eval('#eng-root', (e) => e.classList.contains('reallocated'))), 'Esc from a tile descent restores the brief');
      ok((await pg.$$eval('.hy-card[data-project]', (e) => e.length)) === 0,
        'Esc from a tile descent restores the RESTING brief exactly — NO 12-card inventory dumped open uninvited');
      ok(!(await pg.$eval('.dash-count[data-count="projects"]', (e) => e.classList.contains('is-open'))),
        'the projects chip is NOT is-open after a tile descent + Esc (chip state = what is visible)');
      // CHIP STATE SYNC: the chip now OPENS the inventory (never the desync where it closed it)
      await pg.click('.dash-count[data-count="projects"]');
      await pg.waitForSelector('.hy-card[data-project]', { timeout: 8000 }); await sleep(150);
      ok(await pg.$eval('.dash-count[data-count="projects"]', (e) => e.classList.contains('is-open')),
        'clicking the projects chip after the descent OPENS the inventory + lights the chip (is-open = visible)');
      await pg.click('.dash-count[data-count="projects"]'); await sleep(200);
      ok((await pg.$$eval('.hy-card[data-project]', (e) => e.length)) === 0
        && !(await pg.$eval('.dash-count[data-count="projects"]', (e) => e.classList.contains('is-open'))),
        'clicking the projects chip again CLOSES the inventory + clears the chip — no desync');
    }

    // ── (10) DEAD COUNTS MADE LIVE — every count clicks through to what it counts (finding 3) ──
    await pg.goto(base + '/', { waitUntil: 'domcontentloaded' });
    await pg.waitForSelector('.dash-count[data-count="orders"]', { timeout: 10000 }); await sleep(150);
    if (brief.counts.orders > 0) {
      ok(await pg.$eval('.dash-count[data-count="orders"]', (e) => e.tagName === 'BUTTON'),
        'the banked-orders count wears the interactive button shell (it can act)');
      await pg.click('.dash-count[data-count="orders"]'); await sleep(150);
      const orderRows = await pg.$$eval('#dash-counts-panel .dcp-row', (e) => e.length);
      ok(orderRows === brief.counts.orders, `the orders count opens an in-place list of exactly its ${brief.counts.orders} banked orders (${orderRows})`);
      const cockpit = await pg.$eval('#dash-counts-panel .dcp-foot a', (e) => e.getAttribute('href'));
      ok(cockpit === '/desk?class=work-orders', 'the orders list carries a door to the work-orders cockpit pre-filtered: ' + JSON.stringify(cockpit));
      ok(await pg.$eval('.dash-count[data-count="orders"]', (e) => e.classList.contains('is-open')), 'the orders chip is is-open while its list is visible');
      // register 0 in the served list — no raw record ids / source paths in the order wording
      const orderText = await pg.$eval('#dash-counts-panel', (e) => e.innerText);
      ok(!/\bWO-\d/i.test(orderText) && !/synthetics papers\//i.test(orderText),
        'the orders list wording is plain — no raw WO- ids or source paths in served copy (register 0)');
      await pg.click('.dash-count[data-count="orders"]'); await sleep(150);
      ok((await pg.$('#dash-counts-panel .dcp-row')) === null, 'clicking the orders chip again closes its list');
    }
    if (brief.counts.decisions > 0) {
      await pg.click('.dash-count[data-count="decisions"]'); await sleep(150);
      const decRows = await pg.$$eval('#dash-counts-panel .dcp-row [data-descend]', (e) => e.length);
      ok(decRows === brief.counts.decisions, `the decisions count opens an in-place list of its ${brief.counts.decisions} open decision(s) (${decRows})`);
      await pg.click('#dash-counts-panel [data-descend]'); await sleep(350);
      await pg.waitForSelector('#eng-root.reallocated', { timeout: 8000 }).catch(() => {});
      ok(await pg.$eval('#eng-root', (e) => e.classList.contains('reallocated')),
        'a decision row descends into that project pre-focused (where the rule-the-respine door lives)');
      const respineDoor = await pg.$$eval('.eng-focus .hy-door', (e) => e.map((x) => x.textContent).join(' | '));
      ok(/respine/i.test(respineDoor), 'the descended focus surfaces the RESPINE ruling door: ' + JSON.stringify(respineDoor.slice(0, 80)));
      await pg.keyboard.press('Escape'); await sleep(250);
    }

    // ── (11) THE NEW-PAPER DOOR — birth discoverable at rest, opens the New Project card ─────
    await pg.goto(base + '/', { waitUntil: 'domcontentloaded' });
    await pg.waitForSelector('#dpp-new', { timeout: 10000 }); await sleep(150);
    await pg.click('#dpp-new');
    await pg.waitForSelector('#newproj.is-open', { timeout: 8000 }); await sleep(150);
    ok(await pg.$('#newproj.is-open') !== null, 'the "+ new paper" affordance opens the existing New Project card (birth ≤2 acts, not hunted-for)');
    ok(await pg.$eval('#np-name', (e) => e.getBoundingClientRect().height > 0), 'the New Project name field is visible after the shelf-edge door');

    // ── (12) HOVER LENS — no residue after a descend/close (finding 5) ───────────────────────
    await pg.goto(base + '/', { waitUntil: 'domcontentloaded' });
    await pg.waitForSelector('.dpp-tile:not(.is-skel)', { timeout: 10000 }); await sleep(150);
    if (livePaper) {
      await pg.hover(`.dpp-tile[data-paper="${livePaper.name}"]`); await sleep(200);
      ok(await pg.$eval('.eng-lens', (e) => e.classList.contains('on')), 'hovering a PAPERS tile reveals the lens');
      await pg.click(`.dpp-tile[data-paper="${livePaper.name}"]`); await sleep(300);
      ok(!(await pg.$eval('.eng-lens', (e) => e.classList.contains('on'))), 'the lens is HIDDEN on descend — no residue floating over the shelf');
    }

    // ── (13) NEW-PROJECT CONFIRMATION SURVIVES THE RE-RENDER (gap 4) — drive the door; the
    // confirmation persists OUTSIDE the re-rendered subtree (a page-level toast) while the
    // ephemeral inline #np-msg is wiped by the re-render, and the fresh card is scrolled-to +
    // briefly accented. A real create against the registry, torn down in the finally.
    await pg.goto(base + '/', { waitUntil: 'domcontentloaded' });
    await pg.waitForSelector('#dpp-new', { timeout: 10000 }); await sleep(150);
    await pg.click('#dpp-new');
    await pg.waitForSelector('#newproj.is-open #np-name', { timeout: 8000 });
    await pg.fill('#np-name', NEWPROJ);
    await pg.click('#np-create');
    // the confirmation TOAST appears — and lives OUTSIDE .eng-brief, so the re-render that
    // repaints the brief + inventory (wiping #np-msg in the same tick) cannot wipe it.
    await pg.waitForSelector('#dash-toast.on', { timeout: 12000 });
    const toastTxt = (await pg.textContent('#dash-toast')).trim();
    ok(toastTxt.includes(NEWPROJ) && /work-order/.test(toastTxt),
      'the create confirmation TOAST names the project + banked orders: ' + JSON.stringify(toastTxt.slice(0, 90)));
    const toastOutside = await pg.evaluate(() => {
      const t = document.getElementById('dash-toast'); const brief = document.querySelector('.eng-brief');
      return !!t && !!brief && !brief.contains(t);
    });
    ok(toastOutside, 'the confirmation lives OUTSIDE the re-rendered .eng-brief subtree — the re-render cannot wipe it in the same tick');
    // after the re-render the inventory is back WITH the new card, scrolled-to + briefly accented.
    await pg.waitForSelector(`.hy-card[data-project="${NEWPROJ}"].is-fresh-card`, { timeout: 4000 });
    ok(true, 'the fresh card lands scrolled-to + briefly accented (findable after the re-render, not lost among the rest)');
    // the ephemeral inline #np-msg (inside the re-rendered inventory) no longer carries the
    // confirmation — the durable toast is what survived (the gap-4 catch, proven).
    const npMsg = (await pg.textContent('#np-msg').catch(() => '')) || '';
    ok(!npMsg.includes(NEWPROJ), 'the re-render cleared the ephemeral inline confirmation — the toast carried it (gap 4 proven)');

    // ── (14) THE WIDE-VIEWPORT BRIEF (finding 1) + EQUAL-HEIGHT INVENTORY (finding 3) at 1440 ──
    // The polish sweep centres the resting brief column (margin-inline:auto over a reading
    // measure) so a ≥1400px screen no longer opens a dead band on the right; and the live
    // inventory grid pins every sibling card to the same height (no ragged bottoms, no orphaned
    // third card in a two-column grid). Both are OUTCOMES, driven against the real layout.
    await pg.setViewportSize({ width: 1440, height: 900 });
    await pg.goto(base + '/', { waitUntil: 'domcontentloaded' });
    await pg.waitForSelector('.dash-count[data-count="projects"]', { timeout: 10000 }); await sleep(250);
    const briefBox = await pg.$eval('.eng-brief', (e) => {
      const r = e.getBoundingClientRect();
      return { left: Math.round(r.left), right: Math.round(window.innerWidth - r.right), width: Math.round(r.width) };
    });
    ok(Math.abs(briefBox.left - briefBox.right) <= 6,
      `the resting brief COLUMN is centred at 1440 (left ${briefBox.left}px ≈ right ${briefBox.right}px, not left-anchored)`);
    ok(briefBox.width <= 1010,
      `the brief column is bounded to a reading measure at 1440 (${briefBox.width}px ≤ ~1000), never spilling into a dead band`);
    const hs1440 = await pg.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    ok(hs1440 <= 1, 'no horizontal body scroll at 1440 with the centred brief (' + hs1440 + 'px)');
    // materialise the inventory and pin equal-height sibling cards (bound the height spread)
    await pg.click('.dash-count[data-count="projects"]');
    await pg.waitForSelector('#dash-live > .hy-card', { timeout: 8000 }); await sleep(250);
    const liveHs = await pg.$$eval('#dash-live > .hy-card', (els) => els.map((e) => Math.round(e.getBoundingClientRect().height)));
    ok(liveHs.length >= 2, 'the live inventory materialised at least two sibling cards to compare (' + liveHs.length + ')');
    const hspread = Math.max(...liveHs) - Math.min(...liveHs);
    ok(hspread <= 2,
      `the inventory's sibling cards are EQUAL height at 1440 — no ragged bottoms (spread ${hspread}px across ${JSON.stringify(liveHs)})`);
    // no live card is orphaned in an empty column: the grid resolves to THREE tracks at 1440
    // (the auto-fit fix), so three live cards fill one row instead of a third sitting alone in
    // a two-column grid beside a whole empty column (the finding-3 orphan).
    const liveCols = await pg.$eval('#dash-live', (e) =>
      getComputedStyle(e).gridTemplateColumns.split(' ').filter(Boolean).length);
    ok(liveCols >= 3,
      `the live inventory grid resolves to ≥3 columns at 1440 — no third card orphaned in a 2-col grid (${liveCols} tracks)`);

    ok(errs.length === 0, 'zero uncaught page errors across the whole walk: ' + JSON.stringify(errs));
    console.log(`\nENGINE DASHBOARD — ${passed} assertions green.`);
  } finally {
    await b.close();
    if (scanner) scanner.kill('SIGKILL');
    cleanupNewProject();
  }
})().catch((e) => { console.error('\nWALK FAILED:', e.message); if (scanner) scanner.kill('SIGKILL'); cleanupNewProject(); process.exit(1); });
