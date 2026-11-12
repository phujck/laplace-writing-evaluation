// J6 — MAKE A NEW PROJECT (conception §9): name + template → the scaffold BANKED and
// ASSERTED on disk (dirs, registry row, conceptric seed, plan skeleton, banked work-orders),
// and the card appears on reload. Walked as HIM, THROUGH THE DOOR (the UI), against a real
// scanner. Writes to the REAL repo and CLEANS UP thoroughly so the tree stays clean.
//
//   run:  node tests/j6_new_project.playwright.mjs
//   deps: global `playwright`, Chromium at /opt/pw-browsers, repo venv python as python3.
import { createRequire } from 'module';
import { spawn, execSync } from 'child_process';
import net from 'net';
import http from 'http';
import fs from 'fs';
import path from 'path';

const require = createRequire(import.meta.url);
const PW_ROOT = execSync('npm root -g').toString().trim() + '/playwright';
const { chromium } = require(PW_ROOT);
const CHROME = execSync('ls /opt/pw-browsers/chromium-*/chrome-linux/chrome').toString().trim().split('\n')[0];
const PY = 'python3';

let passed = 0;
function ok(cond, msg){ if(!cond) throw new Error('ASSERT FAILED: ' + msg); passed++; console.log('  ok -', msg); }
function freePort(){ return new Promise((res, rej) => {
  const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); s.on('error', rej); }); }
function waitFor(url, tries = 60){ return new Promise((res, rej) => {
  const tick = (n) => { const req = http.get(url, (r) => { r.resume(); res(true); });
    req.on('error', () => n <= 0 ? rej(new Error('server never came up')) : setTimeout(() => tick(n - 1), 250)); }; tick(tries); }); }
function get(port, p){ return new Promise((res, rej) => {
  http.get(`http://127.0.0.1:${port}${p}`, (r) => { let b = ''; r.on('data', d => b += d); r.on('end', () => res({ status: r.statusCode, body: b })); }).on('error', rej); }); }

const NAME = 'zzscratch' + Date.now();   // slug-safe (lowercase + digits), unmistakably a scratch
let scanner, repoRoot;

function cleanup(){
  // remove EVERYTHING the door banked (dirs, seed ledger, registry row, work-orders)
  try {
    execSync(`${PY} - <<'PY'
import json, shutil
from pathlib import Path
root = Path(${JSON.stringify(repoRoot)})
name = ${JSON.stringify(NAME)}
shutil.rmtree(root / "synthetics papers" / name, ignore_errors=True)
led = root / "corpus_friction" / (name + ".jsonl")
led.unlink(missing_ok=True)
# G2 birth bridge: the growth sidecar + the transient locks the door writes at birth
for suf in (".jsonl.lock", ".growth.json", ".growth.json.lock"):
    (root / "corpus_friction" / (name + suf)).unlink(missing_ok=True)
reg = root / "registry_projects.json"
if reg.is_file():
    d = json.loads(reg.read_text())
    d["projects"] = [r for r in d.get("projects", []) if r.get("name") != name]
    reg.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\\n")
wo = root / "corpus_friction" / "work_orders.jsonl"
if wo.is_file():
    keep = [l for l in wo.read_text().splitlines() if l.strip() and json.loads(l).get("corpus") != name]
    wo.write_text(("\\n".join(keep) + "\\n") if keep else "")
print("cleaned", name)
PY`, { stdio: 'pipe' });
  } catch(e) { console.error('  cleanup error:', e.message); }
}

(async () => {
  repoRoot = execSync(`${PY} -c "from laplace.web.scanner import _repo_root; print(_repo_root().resolve())"`).toString().trim();
  const port = await freePort();
  scanner = spawn(PY, ['-m', 'laplace.web.scanner', '--port', String(port)], { cwd: repoRoot, stdio: 'ignore' });
  await waitFor(`http://127.0.0.1:${port}/`);

  const b = await chromium.launch({ executablePath: CHROME });
  try {
    const pg = await b.newPage({ viewport: { width: 1400, height: 900 } });
    const pageErrors = []; pg.on('pageerror', (e) => pageErrors.push(String(e)));

    console.log(`\n[j6] GET / → create "${NAME}" through the New Project door`);
    await pg.goto(`http://127.0.0.1:${port}/`, { waitUntil: 'domcontentloaded' });
    await pg.waitForSelector('#newproj', { timeout: 10000 });

    // OPEN the door, fill the name, CREATE (through the UI — the real door)
    await pg.click('#np-open');
    await pg.waitForSelector('#newproj.is-open #np-name', { timeout: 4000 });
    await pg.fill('#np-name', NAME);
    await pg.click('#np-create');
    await pg.waitForSelector('#np-msg.ok', { timeout: 8000 });
    const msg = await pg.$eval('#np-msg.ok', e => e.innerText);
    ok(/created/.test(msg) && msg.includes(NAME), `the door reports success (got ${JSON.stringify(msg)})`);
    ok(/work-order/.test(msg), 'the door banked heavy steps as work-orders (offer law made visible)');

    // ── ASSERT ON DISK ───────────────────────────────────────────────────────
    const ms = path.join(repoRoot, 'synthetics papers', NAME, 'manuscript');
    for (const d of [path.join(ms, 'whitepaper', 'feedback'), path.join(ms, 'briefs'),
                     path.join(ms, 'versions'), path.join(ms, 'evolutions')])
      ok(fs.existsSync(d) && fs.statSync(d).isDirectory(), `scaffold dir on disk: ${path.relative(repoRoot, d)}`);

    const led = path.join(repoRoot, 'corpus_friction', NAME + '.jsonl');
    ok(fs.existsSync(led), 'the conceptric seed ledger is on disk');
    const seed = JSON.parse(fs.readFileSync(led, 'utf-8').split('\n').filter(Boolean)[0]);
    ok(seed.kind === 'seed' && seed.owning_layer === NAME, 'the seed ledger carries a real conceptric seed row');

    const plan = JSON.parse(fs.readFileSync(path.join(ms, 'projection_plan.json'), 'utf-8'));
    ok(plan.meta.project === NAME && Array.isArray(plan.sections) && plan.sections.length === 0,
      'the projection_plan skeleton is on disk (empty sections, project stamped)');

    const reg = JSON.parse(fs.readFileSync(path.join(repoRoot, 'registry_projects.json'), 'utf-8'));
    ok(reg.projects.some(r => r.name === NAME && r.kind === 'conceptric'), 'the registry_projects.json data row is banked');

    const wos = fs.readFileSync(path.join(repoRoot, 'corpus_friction', 'work_orders.jsonl'), 'utf-8')
      .split('\n').filter(Boolean).map(JSON.parse).filter(w => w.corpus === NAME);
    const actions = new Set(wos.map(w => w.action));
    ok(actions.has('first-compile') && actions.has('embeddings-build') && wos.length === 2,
      `the heavy steps are banked as work-orders (never fired): ${[...actions].join(', ')}`);
    ok(wos.every(w => w.status === 'open'), 'the banked work-orders are open (his to run — offer-never-fire)');

    // ── THE BIRTH BRIDGE (W-BIRTH): born ON the ladder, zero dead ends ────────
    // main.tex SOURCE stub (not a compile) so the scaffold resolves through the read chain
    ok(fs.existsSync(path.join(ms, 'main.tex')), 'the scaffold carries a main.tex source stub (resolvable, not a compile)');
    // the GOAL NODE minted into the conceptric, marked machine-scaffolded (never his authored goal)
    const ledRows = fs.readFileSync(led, 'utf-8').split('\n').filter(Boolean).map(JSON.parse);
    const goalRow = ledRows.find(r => r.kind === 'add-node' && r.node_kind === 'goal');
    ok(goalRow && goalRow.node === `goal:scaffold-${NAME}`, `the goal node is minted into the conceptric (${goalRow && goalRow.node})`);
    ok(/scaffolded goal/.test(goalRow.essence || '') && goalRow.by === 'dashboard-new-project',
      'the goal essence is marked machine-scaffolded, pending his edit (never presented as his authored goal)');
    // the GROWTH SIDECAR — born SEEDED with the demand queues populated before any compile
    const side = JSON.parse(fs.readFileSync(path.join(repoRoot, 'corpus_friction', NAME + '.growth.json'), 'utf-8'));
    ok(side.state === 'SEEDED' && side.goal_version === 1, `the growth sidecar is born SEEDED (goal v${side.goal_version})`);
    ok(side.queues && side.queues.counts && side.queues.n_demands > 0,
      `the demand queues are populated at birth (${side.queues && side.queues.n_demands} demands, before any compile)`);
    // /corpus/meta SERVES the scaffold (through the resolved corpus + registry growth read) — no dead end
    const meta = JSON.parse((await get(port, `/corpus/meta?corpus=${encodeURIComponent(NAME)}`)).body);
    ok(meta.n_nodes >= 1 && meta.growth && meta.growth.state === 'SEEDED' && !!meta.growth.queues,
      `/corpus/meta serves the scaffold (n_nodes=${meta.n_nodes}, growth=${meta.growth && meta.growth.state}, queues present)`);
    ok(meta.n_gaps === 0, `the scaffold has zero provenance gaps (goal on the spine, no orphan) — n_gaps=${meta.n_gaps}`);
    // the growth cockpit BRIEF renders with honest counts — /conceptric's cockpit data door
    const brief = JSON.parse((await get(port, `/growth/brief?corpus=${encodeURIComponent(NAME)}`)).body);
    ok(brief.state && brief.state.state === 'SEEDED' && brief.counts,
      `the cockpit brief renders honestly (SEEDED · ${brief.counts && brief.counts.tensions} tensions · ${brief.counts && brief.counts.queue} queue)`);
    ok(/SEEDED rung/.test((brief.brief || {}).glance || ''), 'the brief prose names the SEEDED rung honestly');
    // /conceptric OPENS on the scaffold (the static surface + its data doors all resolve)
    ok((await get(port, `/conceptric?corpus=${encodeURIComponent(NAME)}`)).status === 200, '/conceptric opens on the scaffold (200)');

    // ── CARD APPEARS ON RELOAD ───────────────────────────────────────────────
    await pg.goto(`http://127.0.0.1:${port}/`, { waitUntil: 'domcontentloaded' });
    await pg.waitForSelector(`.hy-card[data-project="${NAME}"]`, { timeout: 10000 });
    const card = await pg.$eval(`.hy-card[data-project="${NAME}"]`, e => e.innerText.toLowerCase());
    // A fresh NEVER_RUN project (0 rounds, no artefact) lands on the Tier-2 SCAFFOLD SHELF —
    // scaffoldCardHTML renders the "scaffold" chip, the growth-ladder rung chip (SEEDED, born at
    // birth), and the empty-state law's "no release run yet — seed a conception" door.
    ok(/scaffold/.test(card) && /no release run yet/.test(card),
      'the new project appears on reload as a scaffold card (scaffold chip + no-release-run-yet empty state)');
    // the birth bridge, MADE VISIBLE on the card: the scaffold chip carries the SEEDED rung
    const scafChip = await pg.$eval(`.hy-card[data-project="${NAME}"] .hy-chip.is-scaffold`, e => e.innerText);
    ok(/scaffold/.test(scafChip) && /SEEDED/.test(scafChip),
      `the card's scaffold chip shows the SEEDED growth rung beside the state (born ON the ladder: ${JSON.stringify(scafChip)})`);
    const cls = await pg.$eval(`.hy-card[data-project="${NAME}"]`, e => e.getAttribute('class'));
    ok(/\bis-muted\b/.test(cls), 'the fresh scaffold renders reduced-emphasis (distinct from live work)');

    ok(pageErrors.length === 0, `no page errors across the run (${JSON.stringify(pageErrors)})`);
    console.log(`\nALL GREEN — ${passed} assertions`);
  } finally {
    await b.close();
    if (scanner) scanner.kill();
    cleanup();
    // prove the cleanup was thorough — nothing of the scratch project survives
    const survivors = [
      path.join(repoRoot, 'synthetics papers', NAME),
      path.join(repoRoot, 'corpus_friction', NAME + '.jsonl'),
      path.join(repoRoot, 'corpus_friction', NAME + '.growth.json'),
    ].filter(p => fs.existsSync(p));
    if (survivors.length) { console.error('  CLEANUP INCOMPLETE:', survivors); process.exit(1); }
    console.log('  cleanup verified — the repo is clean');
  }
})().catch((e) => { console.error('\n' + e.message); if (scanner) scanner.kill(); cleanup(); process.exit(1); });
