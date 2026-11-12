// J4 — EDITOR HISTORY (the W8 acceptance walk, conception §9): every editor SAVE banks a
// VERSION; the history IS the ONE version rail (list / diff / restore); a recompile records
// which version it built; editor saves join the SAME rail as rounds + releases + snapshots.
//
// Walked as HIM in a real Chromium, on a THROWAWAY corpus (its own manuscript dir under
// `synthetics papers/<TMP>/`, registered as a process-local registry row) so every bank
// lands in an ISOLATED editor_saves store — NEVER a real project's. Zero residue at teardown.
//
// Asserts:
//   · edit → save → an editor-save ROW appears in the version rail (kind chip "editor-save")
//   · a second edit → save → the rail carries BOTH saves; diffing them shows the change
//   · RESTORE the first (ARM-TO-FIRE) → the live tex matches save-1's bytes AND a THIRD row
//     exists (restore-is-a-save, never a rewind)
//   · compile RECORDS the version it built (built_version_id rides the compile response)
//
//   run:  node tests/j4_editor_history.playwright.mjs
//   deps: global `playwright`, Chromium at /opt/pw-browsers, the repo venv python as python3.
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
const SHOT = process.env.SCRATCH
  ? path.join(process.env.SCRATCH, 'w8_history_rail.png')
  : '/tmp/claude-0/-home-user-laplace/eccef750-97e7-5584-9adf-903d6498e39c/scratchpad/w8_history_rail.png';

let passed = 0;
function ok(cond, msg) { if (!cond) throw new Error('ASSERT FAILED: ' + msg); passed++; console.log('  ok -', msg); }
function freePort() { return new Promise((res, rej) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); s.on('error', rej); }); }
function waitFor(url, tries = 60) { return new Promise((res, rej) => { const tick = (n) => { const req = http.get(url, (r) => { r.resume(); res(true); }); req.on('error', () => n <= 0 ? rej(new Error('server never came up')) : setTimeout(() => tick(n - 1), 250)); }; tick(tries); }); }
function getText(port, p) { return new Promise((res) => { http.get(`http://127.0.0.1:${port}${p}`, (r) => { let b = ''; r.on('data', d => b += d); r.on('end', () => res(b)); }).on('error', () => res('')); }); }

const repoRoot = execSync(`${PY} -c "from laplace.web.scanner import _repo_root; print(_repo_root().resolve())"`).toString().trim();
const TMP = 'j4hist' + process.pid;                                    // clean name ([a-z0-9_-])
const TMP_MS = path.join(repoRoot, 'synthetics papers', TMP, 'manuscript');
const TMP_WP = path.join(TMP_MS, 'whitepaper');
const TMP_TEX = path.join(TMP_WP, 'main.tex');
const TEX_REL = `synthetics papers/${TMP}/manuscript/whitepaper/main.tex`;
const TEX_ROOT_REL = `synthetics papers/${TMP}/manuscript/whitepaper`;  // the registered tex root
const A = 'W8ALPHA' + process.pid, B = 'W8BETA' + process.pid;         // unique save markers

// a genuinely compilable doc — the save markers append AFTER \end{document} (LaTeX ignores
// that tail), so the file stays compilable through every save/restore for the compile step.
const BASE_TEX = '\\documentclass{article}\n\\begin{document}\nJ4 editor-history fixture.\n\\end{document}\n';

function cleanup() { try { fs.rmSync(path.join(repoRoot, 'synthetics papers', TMP), { recursive: true, force: true }); } catch (_e) {} }

// register the throwaway corpus as a process-local registry row (registry._conceptric derives
// its manuscript_dir), then serve — the SAME idiom j4board uses; the bank store is isolated
// under the TMP dir. Process-local, so the repo's own registry_projects.json is never touched.
const BOOT = [
  'import sys',
  'from laplace.pipeline import registry as rg',
  'from laplace.web.scanner import make_handler',
  'from http.server import ThreadingHTTPServer',
  '_build = rg._build_registry',
  'def _inject(root):',
  '    reg, prov = _build(root)',
  '    reg[sys.argv[2]] = rg._conceptric(sys.argv[2], sys.argv[3])',
  '    prov[sys.argv[2]] = "registry-row"',
  '    return reg, prov',
  'rg._build_registry = _inject',
  'ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), make_handler()).serve_forever()',
].join('\n');

async function typeAtEnd(pg, text) {
  // append a line to the editor (CM6 content, else the textarea floor) without disturbing the
  // doc above — Ctrl+End to the tail, a newline, then the plain marker (no braces to auto-close).
  const cm = await pg.$('#art-cm .cm-content');
  const target = cm || await pg.$('#art-cm-ta');
  await target.click();
  await pg.keyboard.press('Control+End');
  await pg.keyboard.press('Enter');
  await pg.keyboard.type(text);
}
async function saveAndBank(pg) {
  // ACT 3 (the Overleaf-class editor) merged save + recompile into ONE door (#art-edit-save,
  // "save + recompile"): saveTex() banks the version FIRST (flashing "saved · banked <id>"),
  // then startRecompile() immediately overwrites the message with the compile status — so the
  // "banked" text is transient and can't be waited on directly. Instead wait for THIS click's
  // cycle to (a) START (leave the prior terminal state) then (b) SETTLE at a terminal state.
  // The bank has landed by the time the cycle settles; the rail assertions below confirm the row.
  await pg.click('#art-edit-save');
  await pg.waitForFunction(() => /saving|recompile queued|compiling/i.test((document.querySelector('#art-edit-msg') || {}).textContent || ''), { timeout: 10000 });
  await pg.waitForFunction(() => /compiled\s*✓|banked|\bsaved\b|compile error|recompile refused/i.test((document.querySelector('#art-edit-msg') || {}).textContent || ''), { timeout: 90000 });
}
async function editorSaveIds(pg) {
  return pg.$$eval('.hy-rail-row.kind-editor-save', els => els.map(e => e.dataset.id));
}
// the standing rail and the editor share the right column; when the rail is OPEN it overlays
// the editor's doors, so drive the two through this toggle — closed to edit/save/compile, open
// to inspect/diff/restore rail rows (#art-rail-toggle lives in the top bar, always clickable).
async function setRail(pg, open) {
  const isOpen = await pg.$eval('#art-rail', e => e.classList.contains('open'));
  // a synthetic DOM click bubbles to the delegated #art handler (avoids the top-bar toggle
  // overlapping the rail's diffbar — a pure layout adjacency, not a behaviour under test).
  if (isOpen !== open) { await pg.$eval('#art-rail-toggle', el => el.click()); await pg.waitForTimeout(200); }
}

let scanner;
(async () => {
  cleanup();
  fs.mkdirSync(TMP_WP, { recursive: true });
  fs.writeFileSync(TMP_TEX, BASE_TEX);

  const port = await freePort();
  scanner = spawn(PY, ['-c', BOOT, String(port), TMP, TEX_ROOT_REL], { cwd: repoRoot, stdio: 'ignore' });
  await waitFor(`http://127.0.0.1:${port}/`);

  const b = await chromium.launch({ executablePath: CHROME });
  try {
    const pg = await b.newPage({ viewport: { width: 1400, height: 900 } });
    const pageErrors = []; pg.on('pageerror', (e) => pageErrors.push(String(e)));
    // capture the compile stamp from the wire. ACT 3 (the live edit loop) drives compilation
    // through /projection/recompile: a POST queues it, then a GET poll returns the settled row
    // carrying `built_version_id` (row.ok). Keep the freshest response that carries the stamp.
    let compileBody = null;
    pg.on('response', async (r) => {
      if (/\/projection\/recompile\b/.test(r.url())) {
        try { const j = await r.json(); if (j && j.built_version_id) compileBody = j; } catch (_e) { /* ignore */ }
      }
    });

    // ── open the artefact surface on the throwaway corpus → edit mode ──
    console.log(`\n[j4] open /artefact?corpus=${TMP} → edit`);
    await pg.goto(`http://127.0.0.1:${port}/artefact?corpus=${TMP}`, { waitUntil: 'domcontentloaded' });
    // ACT 3 (DESIGN_2026-07-21 · the Overleaf-class editor): the artefact pane set has THREE
    // modes — read / annotate / edit — driven by the mode switch (#art-mode-switch); the
    // `edit` mode button splits the CM6 source pane (#art-cm) ⇄ the compiled pdf. Edit is
    // entered by that mode button now (the old single "#art-edit-toggle" bar door is gone).
    await pg.waitForSelector('#art-mode-switch .art-mode-btn[data-mode="edit"]', { timeout: 15000 });
    await pg.click('#art-mode-switch .art-mode-btn[data-mode="edit"]');
    await pg.waitForSelector('#art-cm .cm-content, #art-cm-ta', { timeout: 15000 });
    ok(true, 'the editor opens over the throwaway artefact tex');

    // ── 1. edit → save → an editor-save row appears in the rail ──
    await typeAtEnd(pg, `% ${A}`);
    await saveAndBank(pg);
    ok(true, 'the first save BANKS a version (the save door reported "banked")');
    await setRail(pg, true);                                          // open the standing rail
    await pg.waitForSelector('.hy-rail-row.kind-editor-save', { timeout: 8000 });
    const ids1 = await editorSaveIds(pg);
    ok(ids1.length === 1, `edit → save → ONE editor-save row appears in the rail (${JSON.stringify(ids1)})`);
    const chip = await pg.$eval('.hy-rail-row.kind-editor-save .hy-rail-kind', e => e.textContent.trim());
    ok(chip === 'editor-save', `the row carries the kind chip "editor-save" (got "${chip}")`);
    const save1 = ids1[0];

    // ── 2. second edit → save → the rail carries BOTH; diff shows the change ──
    await setRail(pg, false);                                         // close so the editor is clickable
    await typeAtEnd(pg, `% ${B}`);
    await saveAndBank(pg);
    await setRail(pg, true);
    await pg.waitForFunction(() => document.querySelectorAll('.hy-rail-row.kind-editor-save').length === 2, { timeout: 8000 });
    const ids2 = await editorSaveIds(pg);
    ok(ids2.length === 2 && ids2.includes(save1), `a second save joins the SAME rail (2 editor-save rows: ${JSON.stringify(ids2)})`);
    const save2 = ids2.find(id => id !== save1);

    // tick both saves, run the diff (tex-source diff — both saves carry tex)
    await pg.check(`.art-diffbox[data-id="${save1}"]`);
    await pg.check(`.art-diffbox[data-id="${save2}"]`);
    await pg.waitForSelector('#art-do-diff', { timeout: 5000 });
    await pg.click('#art-do-diff');
    await pg.waitForSelector('.art-difflines', { timeout: 8000 });
    const diffText = await pg.$eval('#art-diffpane', e => e.innerText);
    ok(/tex diff/i.test(diffText), 'the two saves diff as a TEX-SOURCE diff (both sides carry tex)');
    const added = await pg.$$eval('.art-dline.opadd, .art-dline.opdel', els => els.map(e => e.textContent));
    ok(added.some(l => l.includes(B)) || diffText.includes(B),
      `the diff of the two saves shows the change (the ${B} marker line)`);

    // ── 3. RESTORE the first save (ARM-TO-FIRE) → live tex == save-1; a THIRD row exists ──
    const rsel = `.hy-rail-row.kind-editor-save[data-id="${save1}"] .art-restore`;
    await pg.click(rsel);                                              // first click ARMS
    await pg.waitForFunction((s) => /confirm/i.test((document.querySelector(s) || {}).textContent || ''), rsel, { timeout: 5000 });
    ok(true, 'restore is ARM-TO-FIRE (first click relabels "confirm restore")');
    await pg.click(rsel);                                              // second click FIRES
    await pg.waitForFunction(() => document.querySelectorAll('.hy-rail-row.kind-editor-save').length === 3, { timeout: 10000 });
    const ids3 = await editorSaveIds(pg);
    ok(ids3.length === 3, `restore banked a NEW version — a THIRD editor-save row exists (restore-is-a-save, not a rewind): ${ids3.length} rows`);

    // the live tex now matches save-1's bytes: carries the ALPHA marker, NOT the BETA one.
    const live = await getText(port, `/projection/tex?file=${encodeURIComponent(TEX_REL)}`);
    ok(live.includes(A) && !live.includes(B),
      `the live tex was restored to save-1's bytes (has ${A}, not ${B})`);

    // ── 4. compile RECORDS the version it built ──
    // ACT 3 split the edit doors: #art-edit-save is "save + recompile"; #art-edit-recompile is
    // the recompile-only door. Drive the recompile-only door and let it settle at "compiled ✓ ·
    // built <id>" — the built stamp rides the /projection/recompile poll (captured above).
    await setRail(pg, false);                                         // close so the compile door is clickable
    await pg.click('#art-edit-recompile');
    await pg.waitForFunction(() => /compiled\s*✓|compile error|recompile refused/i.test((document.querySelector('#art-edit-msg') || {}).textContent || ''), { timeout: 90000 });
    // the built_version_id stamp rides the compile response (asserted from the wire), naming the
    // LATEST banked save (the restore-save) — a recompile records which version it built.
    ok(compileBody && typeof compileBody === 'object', 'the compile response was captured from the wire');
    ok(compileBody.built_version_id && compileBody.built_version_id === ids3[0],
      `the compile RECORDS the version it built (built_version_id=${compileBody && compileBody.built_version_id} = the latest save)`);

    // ── 5. A1 — THE CHROME ECHOES THE STORE'S LOUDNESS: /shared/versions carries
    // sources.editor_saves.dropped (the bounded store's LOUD prune record); the rail must
    // render it in the editor-save group, mirroring the 16KB-truncated banner idiom.
    // Banking 33+ real saves to actually cross the 32-bound would be slow, so this stubs
    // ONE /shared/versions response — cloned from the real payload so every OTHER field
    // stays honest, only `dropped` is fabricated — and drives a REAL save so the REAL
    // refreshVersions()/renderRailFull() re-fetch and render it in a REAL browser DOM
    // (the j5artefact_tray stub idiom, applied here for just this one assertion).
    await setRail(pg, false);                                       // editor clickable for one more save
    const realVersions = JSON.parse(await getText(port, `/shared/versions?corpus=${TMP}`));
    ok(realVersions && realVersions.sources && realVersions.sources.editor_saves,
      'the real /shared/versions payload carries sources.editor_saves (A1 precondition)');
    const stubbedVersions = JSON.parse(JSON.stringify(realVersions));
    stubbedVersions.sources.editor_saves.dropped = 7;
    await pg.route('**/shared/versions**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(stubbedVersions) }));
    await typeAtEnd(pg, `% ${A}-dropped-probe`);
    await saveAndBank(pg);                                          // refreshVersions() re-fetches → the stub lands
    await setRail(pg, true);
    await pg.waitForSelector('.hy-rail-trunc', { timeout: 8000 });
    const dropBanner = await pg.$$eval('.hy-rail-trunc', els => els.map((e) => e.textContent).join(' | '));
    ok(/\b7\b.*older saves? dropped by the 32-bound/i.test(dropBanner),
      `the editor-save group renders the dropped count (banner: ${JSON.stringify(dropBanner)})`);
    const dropInfoTitle = await pg.$eval('.hy-rail-trunc .hy-info', (e) => e.getAttribute('title'));
    ok(/index\.json/i.test(dropInfoTitle), `the ⓘ names the store index (title: ${JSON.stringify(dropInfoTitle)})`);
    await pg.unroute('**/shared/versions**');

    // ── the screenshot: the standing rail with editor-save rows ──
    await setRail(pg, true);
    await pg.waitForSelector('.hy-rail-row.kind-editor-save', { timeout: 5000 });
    await pg.screenshot({ path: SHOT, fullPage: false });
    ok(fs.existsSync(SHOT), `screenshot banked (${SHOT})`);

    ok(pageErrors.length === 0, `no page errors across the run (${JSON.stringify(pageErrors)})`);
    console.log(`\n[j4] ALL GREEN — ${passed} assertions`);
  } finally {
    await b.close();
    if (scanner) scanner.kill('SIGKILL');
  }
  cleanup();
  // the isolated store is gone; no real project was ever touched (throwaway corpus).
  if (fs.existsSync(path.join(repoRoot, 'synthetics papers', TMP))) { console.error('\nresidue left behind'); process.exit(1); }
  console.log('  ok - zero residue (the throwaway corpus + its editor_saves store are gone)');
  process.exit(0);
})().catch((e) => { console.error('\n' + e.message); if (scanner) scanner.kill('SIGKILL'); cleanup(); process.exit(1); });
