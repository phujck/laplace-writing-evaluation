// tests/_walk_boot.mjs — platform-general boot helpers shared by the *.playwright.mjs
// walks. Built general (never scoped to one box): the dev box is Windows with a repo
// venv and no node-side Playwright install; the remote box is Linux with a global npm
// `playwright` and Chromium under /opt/pw-browsers. Every walk needs the SAME
// resolution logic for "which python", "which chrome binary", "which playwright
// package (if any)" — it lives here once instead of forked per walk.
//
// Currently imported by tests/engine_weld.playwright.mjs. The other tests/*.playwright.mjs
// walks still carry their own copy of the old Linux-locked resolution inline (out of
// scope for the pass that created this file — see PSU-safety note in HANDOFF-adjacent
// friction if migrating them later).
import { createRequire } from 'module';
import { execSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const require = createRequire(import.meta.url);
const HERE = path.dirname(fileURLToPath(import.meta.url));
export const REPO_ROOT = path.resolve(HERE, '..');

// ─── python ──────────────────────────────────────────────────────────────
// Windows dev box: the repo's own venv at .venv/Scripts/python.exe. Remote Linux box:
// no venv is checked in; `python3` on PATH is the historical contract there. Never spawn
// a literal 'python3' — resolve once, use everywhere a walk needs a python child.
export function resolvePython() {
  const winVenv = path.join(REPO_ROOT, '.venv', 'Scripts', 'python.exe');
  if (process.platform === 'win32' && fs.existsSync(winVenv)) return winVenv;
  const posixVenv = path.join(REPO_ROOT, '.venv', 'bin', 'python');
  if (fs.existsSync(posixVenv)) return posixVenv;
  return 'python3';
}

// ─── chromium executable ────────────────────────────────────────────────
// PLAYWRIGHT_BROWSERS_PATH overrides when set (playwright's own contract, honored
// first). Otherwise glob the platform's default cache: Windows ships chrome-win64 (and
// older installs chrome-win) under %LOCALAPPDATA%/ms-playwright; the remote Linux box
// installs to /opt/pw-browsers/chromium-*/chrome-linux/chrome (also checks
// ~/.cache/ms-playwright, Playwright's own posix default). Highest chromium-<build>
// wins when several are installed. Returns null (never throws) when nothing is found —
// callers fall back to bare chromium.launch() and let Playwright's own error surface.
export function resolveChromeExecutable() {
  const bases = [];
  if (process.env.PLAYWRIGHT_BROWSERS_PATH) bases.push(process.env.PLAYWRIGHT_BROWSERS_PATH);
  if (process.platform === 'win32') {
    if (process.env.LOCALAPPDATA) bases.push(path.join(process.env.LOCALAPPDATA, 'ms-playwright'));
  } else {
    if (process.env.HOME) bases.push(path.join(process.env.HOME, '.cache', 'ms-playwright'));
    bases.push('/opt/pw-browsers');
  }
  const subdirs = ['chrome-win64', 'chrome-win', 'chrome-linux', 'chrome-mac'];
  const exeName = process.platform === 'win32' ? 'chrome.exe' : 'chrome';
  const found = [];
  for (const base of bases) {
    if (!base || !fs.existsSync(base)) continue;
    let entries;
    try { entries = fs.readdirSync(base); } catch { continue; }
    for (const entry of entries) {
      const m = /^chromium-(\d+)$/.exec(entry);
      if (!m) continue;
      for (const sub of subdirs) {
        const exe = path.join(base, entry, sub, exeName);
        if (fs.existsSync(exe)) found.push({ exe, build: Number(m[1]) });
      }
    }
  }
  if (!found.length) return null;
  found.sort((a, b) => b.build - a.build);
  return found[0].exe;
}

// ─── node-side playwright package ──────────────────────────────────────
// Tries normal module resolution first (works the day the repo gains its own
// node_modules/playwright), then the historical global-npm contract the remote Linux
// box actually runs on. Returns null — never throws — so callers can fail with an
// actionable message instead of an opaque MODULE_NOT_FOUND.
export function resolvePlaywrightChromium() {
  try {
    return require('playwright').chromium;
  } catch {}
  try {
    const globalRoot = execSync('npm root -g', { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim();
    if (globalRoot) return require(path.join(globalRoot, 'playwright')).chromium;
  } catch {}
  return null;
}

// ─── scanner spawn env ───────────────────────────────────────────────────
// LAPLACE_EMBED_BUDGET=0 explicit in the child env (never assumed inherited) — no walk
// may trip an embedding run against the live tree. 0 is the documented OFF posture
// (embed_router._env_budget / the local launcher default).
export function scannerSpawnEnv(extra = {}) {
  return { ...process.env, LAPLACE_EMBED_BUDGET: '0', ...extra };
}
