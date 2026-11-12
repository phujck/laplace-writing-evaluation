// ═══════════════════════════════════════════════════════════════════════════
// chair_walk.mjs — THE CHAIR-LAW WALKER. The mechanical fleet asks the three
// questions where a clause can reach; this walker carries the surfaces the rest
// of the way — to the exact point where only HIS chair can judge. It screenshots
// every rostered surface at 1536×864 (his desktop, above the fold) and 375px (the
// phone column) into evidence/chair_walk_<date>/, and writes an index.md that puts
// the three questions (RULING_2026-07-15) under each surface for his eyes. It
// renders no verdict — a screenshot is evidence, the chair is the seal.
//
//   run:  node scripts/chair_walk.mjs [--corpus NAME] [--out DIR] [--only SUBSTR]
//   deps: global `playwright`, Chromium at /opt/pw-browsers, the repo venv python
//         as python3 (spawns the real scanner, one free port). Stdlib-node only.
//
// It is NON-MUTATING: pure GET navigation + screenshots; it writes ONLY under the
// evidence dir it owns. Exits 0 when every rostered surface was captured, else 1.
import { createRequire } from 'module';
import { spawn, execSync } from 'child_process';
import net from 'net';
import http from 'http';
import fs from 'fs';
import path from 'path';

const require = createRequire(import.meta.url);
const { chromium } = require(execSync('npm root -g').toString().trim() + '/playwright');
const CHROME = execSync('ls /opt/pw-browsers/chromium-*/chrome-linux/chrome').toString().trim().split('\n')[0];
const PY = 'python3';

// ── args ──────────────────────────────────────────────────────────────────
function argOf(name, dflt) { const i = process.argv.indexOf(name); return i >= 0 ? process.argv[i + 1] : dflt; }
const ONLY = argOf('--only', null);
const CORPUS_ARG = argOf('--corpus', null);
const TODAY = new Date().toISOString().slice(0, 10);

function freePort() { return new Promise((res, rej) => {
  const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); s.on('error', rej); }); }
function waitFor(url, tries = 80) { return new Promise((res, rej) => {
  const tick = (n) => { const req = http.get(url, (r) => { r.resume(); res(true); });
    req.on('error', () => n <= 0 ? rej(new Error('server never came up')) : setTimeout(() => tick(n - 1), 250)); }; tick(tries); }); }
function get(port, p) { return new Promise((res, rej) => {
  http.get(`http://127.0.0.1:${port}${p}`, (r) => { let b = ''; r.on('data', d => b += d); r.on('end', () => res(b)); }).on('error', rej); }); }

// the three questions the seal exists to answer (RULING_2026-07-15) — put under
// every surface so his read is structured, never "I don't know where to start".
const THREE_QUESTIONS = [
  '**What am I looking at?** Does the surface state its object, its project, and the one next action — above the fold?',
  '**How do I interact?** Is every clickable obviously clickable (hover, cursor, label)? Is anything inert visibly inert?',
  '**Where did that take me?** Does a door carry the selection and echo where it landed? Does nothing shift under the pointer?',
];

let scanner;
(async () => {
  const repoRoot = execSync(`${PY} -c "from laplace.web.scanner import _repo_root; print(_repo_root().resolve())"`).toString().trim();
  const outDir = path.resolve(argOf('--out', path.join(repoRoot, 'evidence', `chair_walk_${TODAY}`)));
  fs.mkdirSync(outDir, { recursive: true });

  const port = await freePort();
  const base = `http://127.0.0.1:${port}`;
  scanner = spawn(PY, ['-m', 'laplace.web.scanner', '--port', String(port)], { cwd: repoRoot, stdio: 'ignore' });
  await waitFor(`${base}/`);

  let roster = JSON.parse(await get(port, '/shared/views')).views;
  if (ONLY) roster = roster.filter((v) => v.id.includes(ONLY) || v.path.includes(ONLY));
  const corpora = JSON.parse(await get(port, '/corpus/list')).corpora || [];
  const PROJ = CORPUS_ARG || corpora[0] || '';

  console.log(`chair walk → ${outDir}`);
  console.log(`  scanner @ ${base}  ·  project = ${PROJ || '(none)'}  ·  ${roster.length} surfaces\n`);

  const b = await chromium.launch({ executablePath: CHROME });
  const captured = [];
  try {
    for (const v of roster) {
      const sep = v.path.includes('?') ? '&' : '?';
      const url = `${base}${v.path}${sep}corpus=${encodeURIComponent(PROJ)}`;
      const shot = { id: v.id, title: v.title, path: v.path, purpose: v.purpose, header: '(not captured)', desktop: null, phone: null, error: null };

      // ── 1536×864 — his desktop, ABOVE THE FOLD (first paint answers the one question) ──
      const pg = await b.newPage({ viewport: { width: 1536, height: 864 } });
      try {
        await pg.goto(url, { waitUntil: 'domcontentloaded', timeout: 20000 });
        await pg.waitForSelector('#hy-context', { timeout: 12000 });
        await pg.waitForTimeout(1400);
        const c = await pg.$('#hy-context');
        if (c) shot.header = (await c.innerText()).replace(/\s+/g, ' ').trim().slice(0, 200);
        const dName = `${v.id}_1536x864.png`;
        await pg.screenshot({ path: path.join(outDir, dName), fullPage: false });   // the fold
        shot.desktop = dName;
        // ── 375px — the phone column (single column, rails slide in, no h-scroll) ──
        await pg.setViewportSize({ width: 375, height: 812 });
        await pg.waitForTimeout(500);
        const pName = `${v.id}_375.png`;
        await pg.screenshot({ path: path.join(outDir, pName), fullPage: true });     // the whole column
        shot.phone = pName;
      } catch (e) {
        shot.error = String(e.message || e).slice(0, 140);
      } finally {
        await pg.close();
      }
      captured.push(shot);
      console.log(`  ${shot.error ? 'ERR ' : 'ok  '}${v.id.padEnd(11)} ${shot.error || `${shot.desktop} · ${shot.phone}`}`);
    }

    // ── index.md — the three questions per surface, for his eyes ──────────────
    const L = [];
    L.push(`# Chair walk — ${TODAY}`);
    L.push('');
    L.push('The mechanical fleet (`tests/waveF_*.playwright.mjs`) certifies what a clause can');
    L.push('reach: the context header is present + truthful, every clickable answers hover,');
    L.push('nothing shifts under the pointer, the arrival echo fires, the ✎ mouth banks, the');
    L.push('palette holds, no mock artifact leaks, ≤2 accents light. **Those greens are');
    L.push('necessary, never sufficient.** This page is the rest of the walk: each surface');
    L.push('screenshotted where you actually sit, with the three questions under it. A green');
    L.push('fleet + a screen that still fails a question here is a **desk rejection**, exactly');
    L.push('as the ruling holds — the seal is your chair, not the mechanism.');
    L.push('');
    L.push(`Driven against the real scanner · project \`${PROJ || '(none)'}\` · captured at 1536×864`);
    L.push('(your desktop, above the fold) and 375px (the phone column).');
    L.push('');
    L.push('---');
    L.push('');
    for (const s of captured) {
      L.push(`## ${s.title} — \`${s.path}\``);
      L.push('');
      L.push(`*roster purpose:* ${s.purpose || '(none)'}`);
      L.push('');
      if (s.error) {
        L.push(`> ⚠ capture failed: \`${s.error}\``);
        L.push('');
        continue;
      }
      L.push(`*the surface's own L1 line (what it claims you are looking at):*`);
      L.push('');
      L.push('> ' + s.header);
      L.push('');
      L.push(`![${s.id} at 1536×864](./${s.desktop})`);
      L.push('');
      L.push(`<details><summary>375px column</summary>`);
      L.push('');
      L.push(`![${s.id} at 375px](./${s.phone})`);
      L.push('');
      L.push('</details>');
      L.push('');
      L.push('**Judge, in your chair:**');
      for (const q of THREE_QUESTIONS) L.push(`- ${q}`);
      L.push('');
      L.push('---');
      L.push('');
    }
    const indexPath = path.join(outDir, 'index.md');
    fs.writeFileSync(indexPath, L.join('\n'), 'utf-8');

    const failed = captured.filter((s) => s.error);
    console.log(`\nwrote ${indexPath}`);
    console.log(`captured ${captured.length - failed.length}/${captured.length} surfaces` +
      (failed.length ? ` (failed: ${failed.map((s) => s.id).join(', ')})` : ' — all green'));
    process.exitCode = failed.length ? 1 : 0;
  } finally {
    await b.close();
    if (scanner) scanner.kill();
  }
})().catch((e) => { console.error('\n' + (e.message || e)); if (scanner) scanner.kill(); process.exit(1); });
