// Real Chromium on the real HTTP owners, for composed walk and shell tests (M5 S2). The owners are
// tests/helpers/walk_owner_server.py (scanner.make_handler on a disposable synthetic book project); nothing is
// stubbed here. A test may stub one supported public owner route itself (e.g. /authoring/providers) on its page.
// startOwners() -> {base, browser, newPage(options), close()}; close() stops the browser and the server, which
// removes its temporary project root.
import {createRequire} from 'module';
import {execSync, spawn} from 'child_process';
import {existsSync} from 'fs';
import path from 'path';
import {fileURLToPath} from 'url';

const require = createRequire(import.meta.url);
export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');

export function playwright() {
  const roots = [
    (() => {try {return execSync('npm root -g', {stdio: ['ignore', 'pipe', 'ignore']}).toString().trim() + '/playwright';} catch {return '';}})(),
    `${ROOT}/node_modules/playwright`, `${ROOT}/node_modules/playwright-core`,
    process.env.LAPLACE_PLAYWRIGHT_MODULE || '',
    '/home/phujck/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright-core',
    '/usr/lib/chatgpt/resources/cua_node/lib/node_modules/playwright-core',
  ].filter(Boolean);
  const found = roots.find(existsSync);
  if (!found) throw new Error(`Playwright is absent; searched ${roots.join(', ')}`);
  return require(found);
}

export async function startOwners() {
  const {chromium} = playwright();
  const chrome = execSync("find /opt/pw-browsers \"$HOME/.cache/ms-playwright\" -type f -path '*/chrome-linux*/chrome' -print -quit 2>/dev/null || true").toString().trim();
  const server = spawn(`${ROOT}/scripts/laplace-python`, [`${ROOT}/tests/helpers/walk_owner_server.py`], {cwd: ROOT, stdio: ['pipe', 'pipe', 'inherit']});
  const info = await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.stdout.once('data', data => resolve(JSON.parse(String(data))));
  });
  const browser = await chromium.launch(chrome ? {executablePath: chrome} : {});
  return {
    base: `http://127.0.0.1:${info.port}`, browser,
    newPage: options => browser.newPage(options),
    async close() {await browser.close(); server.stdin.end(); await new Promise(resolve => server.once('exit', resolve));},
  };
}
