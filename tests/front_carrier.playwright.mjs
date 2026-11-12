// Independent acceptance harness for the one-stop Aisthesis /front carrier.
//
// This is intentionally not a compatibility test for either predecessor shell. It
// walks only the actual served /front, through native human controls, and refuses a
// technically correct carrier that still presents a dashboard/card wall or hides the
// attended object below explanatory furniture.
//
// Run: node tests/front_carrier.playwright.mjs

import { createRequire } from 'module';
import { spawn, execFileSync, execSync } from 'child_process';
import { existsSync, mkdirSync, readFileSync } from 'fs';
import http from 'http';
import net from 'net';

const require = createRequire(import.meta.url);
const roots = [
  `${process.cwd()}/node_modules/playwright`,
  `${process.cwd()}/node_modules/playwright-core`,
  execSync('npm root -g').toString().trim() + '/playwright',
  '/home/phujck/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright-core',
  '/usr/lib/chatgpt/resources/cua_node/lib/node_modules/playwright-core',
];
const pwRoot = roots.find(existsSync);
if (!pwRoot) throw new Error(`Playwright is absent; searched ${roots.join(', ')}`);
const { chromium } = require(pwRoot);
const chrome = execSync("find /opt/pw-browsers \"$HOME/.cache/ms-playwright\" -type f -path '*/chrome-linux*/chrome' -print -quit 2>/dev/null || true").toString().trim();

const PY = '/usr/bin/python3';
const SHOTS = process.env.LAPLACE_SCREENSHOT_DIR || '/tmp/laplace-front-carrier-evidence';
const ROOMS = ['now', 'programme', 'work', 'decision', 'run', 'conversation', 'exposition', 'diagnostics'];
const GRADES = ['summary', 'picture', 'detail', 'audit'];
const VIEWPORTS = [
  { width: 1536, height: 900, mode: 'wide' },
  { width: 768, height: 900, mode: 'medium' },
  { width: 375, height: 812, mode: 'narrow' },
];
const HASH_WALLPAPER = /(?:sha256:|message:|region-lease:)[0-9a-f]{16,}/i;
const MAX_CHROMIUM_RASTER_VARIANCE_PIXELS = 8;

let scanner;
let passed = 0;

function ok(condition, message) {
  if (!condition) throw new Error(`ASSERT FAILED: ${message}`);
  passed += 1;
  console.log('  ok -', message);
}

function refuse(kind, message) {
  throw new Error(`${kind}: ${message}`);
}

function screenshotDifferencePixels(firstPath, secondPath) {
  if (readFileSync(firstPath).equals(readFileSync(secondPath))) return 0;
  try {
    execFileSync('compare', ['-metric', 'AE', firstPath, secondPath, 'null:'], {
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    return 0;
  } catch (error) {
    const metric = String(error?.stderr || '').trim();
    const pixels = Number(metric);
    if (!Number.isFinite(pixels)) throw error;
    return pixels;
  }
}

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.listen(0, '127.0.0.1', () => {
      const port = server.address().port;
      server.close(() => resolve(port));
    });
    server.on('error', reject);
  });
}

function waitFor(url, tries = 120) {
  return new Promise((resolve, reject) => {
    const tick = (remaining) => {
      const request = http.get(url, (response) => { response.resume(); resolve(true); });
      request.on('error', () => remaining <= 0
        ? reject(new Error('scanner never came up'))
        : setTimeout(() => tick(remaining - 1), 250));
    };
    tick(tries);
  });
}

async function waitReady(page, expectedRoom = null) {
  await page.waitForSelector('[data-aisthesis-carrier="1"][data-ready="true"]', { timeout: 30000 });
  if (expectedRoom) {
    await page.waitForFunction((room) => {
      const carrier = document.querySelector('[data-aisthesis-carrier="1"]');
      return carrier?.dataset.ready === 'true' && carrier?.dataset.room === room;
    }, expectedRoom);
  }
}

async function visibleTextWithoutAudit(page) {
  return page.evaluate(() => {
    const clone = document.body.cloneNode(true);
    clone.querySelectorAll('[data-audit-well], [hidden], [aria-hidden="true"]').forEach((node) => node.remove());
    clone.style.cssText = 'position:fixed;left:-100000px;top:0;width:1000px;';
    document.documentElement.append(clone);
    const words = clone.innerText;
    clone.remove();
    return words;
  });
}

async function carrierState(page) {
  return page.$eval('[data-aisthesis-carrier="1"]', (root) => ({
    room: root.dataset.room || null,
    focus: root.dataset.focusHandle || null,
    grade: root.dataset.grade || null,
    shown: root.dataset.shownHandle || null,
    omitted: root.dataset.omittedDigest || null,
    layout: root.dataset.layoutReceipt || null,
    currentness: root.dataset.currentness || null,
  }));
}

function sameState(actual, expected) {
  return JSON.stringify(actual) === JSON.stringify(expected);
}

async function assertOneForegroundRoom(page, expectedRoom) {
  const rooms = await page.$$eval('[data-room][data-foreground]', (nodes) => nodes.map((node) => {
    const rect = node.getBoundingClientRect();
    return {
      room: node.dataset.room,
      foreground: node.dataset.foreground,
      visible: rect.width > 0 && rect.height > 0 && getComputedStyle(node).visibility !== 'hidden',
    };
  }));
  const foreground = rooms.filter((room) => room.visible && room.foreground === 'true');
  ok(foreground.length === 1 && foreground[0].room === expectedRoom,
    `exactly one foreground room is visible (${expectedRoom})`);
  ok(rooms.filter((room) => room.visible).length === 1,
    'contextual rooms do not collapse into a simultaneous dashboard');
}

async function assertNoPredecessorShell(page) {
  ok(await page.locator('[data-aisthesis-carrier="1"]').count() === 1,
    'the served page declares one Aisthesis carrier');
  ok(await page.locator('iframe[src*="/front/development"], [data-predecessor-shell]').count() === 0,
    'the carrier does not embed or wrap a predecessor shell');
  const visibleLegacyPanels = await page.$$eval('#apex,#campaign,#run,#organ,#explore', (nodes) =>
    nodes.filter((node) => {
      const rect = node.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    }).length);
  ok(visibleLegacyPanels <= 1, 'the predecessor dashboard panels are not composed as the carrier');
}

async function assertColdOrientation(page, viewport, startedAt) {
  ok(Date.now() - startedAt <= 5000, `${viewport.width}px carrier becomes orientable within five seconds`);
  const required = ['currentness', 'focus', 'causal-break', 'predecessor', 'successor', 'omitted-context'];
  const facts = await page.$$eval('[data-orientation]', (nodes) => nodes.map((node) => {
    const rect = node.getBoundingClientRect();
    return {
      name: node.dataset.orientation,
      text: (node.innerText || '').trim(),
      rect: { top: rect.top, bottom: rect.bottom, left: rect.left, right: rect.right },
    };
  }));
  for (const name of required) {
    const fact = facts.find((item) => item.name === name);
    ok(Boolean(fact) && fact.text.length >= 2, `${viewport.width}px cold face states ${name} in human words`);
    ok(fact.rect.top >= 0 && fact.rect.bottom <= viewport.height
      && fact.rect.left >= 0 && fact.rect.right <= viewport.width,
    `${viewport.width}px ${name} is visible without scrolling`);
    ok(!HASH_WALLPAPER.test(fact.text), `${viewport.width}px ${name} does not require a receipt id`);
  }
  const currentness = facts.find((item) => item.name === 'currentness').text;
  ok(/CURRENT|LAST.TRUSTED|STALE|UNKNOWN|REFUSED/i.test(currentness),
    'currentness is a word, not a colour or freshness age');
  const foreground = await page.locator('[data-room][data-foreground="true"]').boundingBox();
  ok(Boolean(foreground) && foreground.y < viewport.height * 0.42,
    `${viewport.width}px attended work is not buried beneath a hero/preamble`);
}

async function assertNativeControls(page, viewport) {
  const controls = await page.$$eval(
    '[data-room-door],[data-primary-control],[data-semantic-object],[data-semantic-edge],[data-descent-grade]',
    (nodes) => nodes.map((node) => {
      const rect = node.getBoundingClientRect();
      return {
        tag: node.tagName,
        label: node.getAttribute('aria-label') || node.innerText || '',
        tabIndex: node.tabIndex,
        primary: node.hasAttribute('data-primary-control') || node.hasAttribute('data-room-door'),
        visible: rect.width > 0 && rect.height > 0,
        width: rect.width,
        height: rect.height,
      };
    }).filter((item) => item.visible),
  );
  ok(controls.length > 0, `${viewport.width}px exposes native interaction controls`);
  ok(controls.every((item) => ['A', 'BUTTON'].includes(item.tag) && item.label.trim().length > 0 && item.tabIndex >= 0),
    `${viewport.width}px visible objects and doors are labelled keyboard controls`);
  ok(controls.filter((item) => item.primary).every((item) => item.width >= 44 && item.height >= 44),
    `${viewport.width}px primary controls preserve a 44px target floor`);
}

async function openRoom(page, room) {
  const door = page.locator(`[data-room-door="${room}"]`);
  ok(await door.count() === 1, `${room} has one discoverable room door`);
  await door.click();
  await waitReady(page, room);
  await assertOneForegroundRoom(page, room);
}

async function assertRoomsAndRendererFitness(page) {
  const roomDoors = await page.$$eval('[data-room-door]', (nodes) => nodes.map((node) => node.dataset.roomDoor));
  ok(roomDoors.length === ROOMS.length && ROOMS.every((room) => roomDoors.includes(room)),
    'all eight contextual rooms are discoverable from the one carrier');
  const initialFocus = (await carrierState(page)).focus;
  ok(Boolean(initialFocus), 'the carrier has one stable attended-object identity');
  const renderers = [];
  for (const room of ROOMS) {
    await openRoom(page, room);
    const state = await carrierState(page);
    ok(state.focus === initialFocus, `${room} rehydrates the same semantic focus`);
    const foreground = page.locator(`[data-room="${room}"][data-foreground="true"]`);
    const renderer = await foreground.getAttribute('data-renderer');
    const composition = await foreground.getAttribute('data-composition');
    ok(Boolean(renderer), `${room} declares its job-appropriate renderer`);
    ok(!/generic|dashboard|card-grid|box-wall/i.test(`${renderer} ${composition || ''}`),
      `${room} refuses the generic dashboard/card-wall grammar`);
    renderers.push(renderer);
  }
  const unique = new Set(renderers);
  const mostUsed = Math.max(...[...unique].map((renderer) => renderers.filter((item) => item === renderer).length));
  ok(unique.size >= 5 && mostUsed <= 3,
    `eight rooms use job-appropriate renderers rather than one carrier-wide diagram (${[...unique].join(', ')})`);
}

async function ensureFocus(page) {
  let state = await carrierState(page);
  if (state.focus) return state.focus;
  const subject = page.locator('[data-semantic-object]').first();
  ok(await subject.count() === 1, 'a semantic object is available for visual descent');
  const handle = await subject.getAttribute('data-semantic-handle');
  ok(Boolean(handle), 'the selectable object carries stable semantic identity');
  await subject.click();
  await page.waitForFunction((expected) =>
    document.querySelector('[data-aisthesis-carrier="1"]')?.dataset.focusHandle === expected,
  handle);
  state = await carrierState(page);
  return state.focus;
}

async function assertDescentAndBack(page) {
  await openRoom(page, 'programme');
  const focus = await ensureFocus(page);
  const records = [];
  for (let index = 0; index < GRADES.length; index += 1) {
    const grade = GRADES[index];
    const control = page.locator(`[data-descent-grade="${grade}"]`);
    ok(await control.count() === 1, `${grade} is a named, reversible visual altitude`);
    const before = await carrierState(page);
    if (before.grade !== grade) {
      const beforeHistory = await page.evaluate(() => history.length);
      await control.click();
      await page.waitForFunction(({ grade, focus }) => {
        const root = document.querySelector('[data-aisthesis-carrier="1"]');
        return root?.dataset.ready === 'true' && root?.dataset.grade === grade
          && root?.dataset.focusHandle === focus;
      }, { grade, focus });
      const afterHistory = await page.evaluate(() => history.length);
      ok(afterHistory === beforeHistory + 1, `${grade} is one atomic URL/history transition`);
    } else {
      ok(index === 0, 'the resting selected object begins at Summary altitude');
    }
    const state = await carrierState(page);
    ok(state.focus === focus && state.grade === grade && Boolean(state.shown) && Boolean(state.layout),
      `${grade} binds stable focus, shown state and layout receipt`);
    records.push(state);
  }

  const selected = page.locator(`[data-semantic-object][data-semantic-handle="${focus}"]`);
  ok(await selected.count() === 1, 'Audit retains the selected object in the same spatial field');
  const auditWell = page.locator('[data-audit-well][data-selected="true"]');
  ok(await auditWell.count() === 1 && (await auditWell.innerText()).trim().length > 20,
    'Audit exposes one attention-local evidence well');
  ok(HASH_WALLPAPER.test(await auditWell.innerText()),
    'full identifiers are available for the selected Audit subject');
  ok(!HASH_WALLPAPER.test(await visibleTextWithoutAudit(page)),
    'full identifiers do not escape the selected Audit well');

  for (let index = records.length - 2; index >= 0; index -= 1) {
    await page.goBack();
    await page.waitForFunction((expected) => {
      const root = document.querySelector('[data-aisthesis-carrier="1"]');
      return root?.dataset.ready === 'true' && root?.dataset.shownHandle === expected.shown;
    }, records[index]);
    const restored = await carrierState(page);
    ok(sameState(restored, records[index]),
      `Back restores exact ${records[index].grade} room/focus/grade/shown/omission/layout state`);
  }
}

async function assertSemanticMemory(page) {
  await openRoom(page, 'exposition');
  const memory = page.locator('[data-organ="semantic-memory"]');
  ok(await memory.count() === 1, 'Semantic Memory is an organ inside the carrier');
  ok(await memory.locator('[data-memory-expand]').count() === 1,
    'Semantic Memory has a native in-place expansion door');
  await memory.locator('[data-memory-expand]').click();
  await page.waitForSelector('[data-organ="semantic-memory"] [data-memory-detail]:visible');
  ok(await page.locator('[data-room][data-foreground="true"] [data-organ="semantic-memory"]').count() === 1,
    'Semantic Memory expands inside the foreground context rather than as a detached app');

  const specimen = memory.locator('[data-memory-specimen="missing-dependency"]');
  ok(await specimen.count() === 1, 'Semantic Memory exposes a safe missing-dependency specimen');
  await specimen.click();
  const unknown = memory.locator('[data-memory-dependency][data-state="UNKNOWN"]');
  await unknown.waitFor({ state: 'visible' });
  const words = (await unknown.innerText()).trim();
  ok(/unknown/i.test(words) && words.length > 20 && !HASH_WALLPAPER.test(words),
    'missing Semantic Memory dependency remains honestly UNKNOWN in human words');
}

async function assertReconstructionObservatory(page) {
  await openRoom(page, 'diagnostics');
  const observatory = page.locator('[data-organ="reconstruction-observatory"]');
  ok(await observatory.count() === 1,
    'Reconstruction Observatory is a contextual organ inside the carrier');

  for (const subjectKind of ['seat', 'turn', 'task']) {
    const subject = observatory.locator(`[data-observatory-subject="${subjectKind}"]`).first();
    ok(await subject.count() === 1, `Observatory exposes a selected ${subjectKind} expansion`);
    ok(await subject.evaluate((node) => ['A', 'BUTTON'].includes(node.tagName)
      && (node.getAttribute('aria-label') || node.innerText || '').trim().length > 0),
    `${subjectKind} expansion is a labelled native control`);
    await subject.click();
    const detail = observatory.locator(`[data-observatory-detail][data-subject-kind="${subjectKind}"]`);
    await detail.waitFor({ state: 'visible' });

    for (const field of [
      'routed', 'reached', 'admitted', 'rejected', 'unvisited',
      'depth', 'budget', 'fog', 'currentness', 'descent',
    ]) {
      const node = detail.locator(`[data-observatory-field="${field}"]`);
      ok(await node.count() === 1, `${subjectKind} expansion carries ${field}`);
      const words = (await node.innerText()).trim();
      ok(words.length > 0, `${subjectKind} ${field} is present rather than implied empty`);
      const state = await node.getAttribute('data-state');
      if (state === 'UNKNOWN') {
        ok(/UNKNOWN/i.test(words), `${subjectKind} ${field} says UNKNOWN when evidence is absent`);
      }
    }

    const successfulDescent = await detail.locator(
      '[data-descended-receipt][data-state="SUCCEEDED"]',
    ).count();
    if (successfulDescent === 0) {
      const descentWords = (await detail.locator('[data-observatory-field="descent"]').innerText()).trim();
      ok(/ROUTING-ONLY|UNKNOWN/i.test(descentWords),
        `${subjectKind} separates routing from an unproven descended context`);
      ok(!/context loaded/i.test(await detail.innerText()),
        `${subjectKind} never says context loaded without a successful descended receipt`);
    }
  }
}

async function assertKeyboard(page) {
  await openRoom(page, 'now');
  await page.locator('body').click({ position: { x: 2, y: 2 } });
  let found = false;
  for (let index = 0; index < 30; index += 1) {
    await page.keyboard.press('Tab');
    found = await page.evaluate(() => document.activeElement?.hasAttribute('data-room-door'));
    if (found) break;
  }
  ok(found, 'keyboard Tab discovers the contextual room switcher');
  const focusedRoom = await page.evaluate(() => document.activeElement?.getAttribute('data-room-door'));
  await page.keyboard.press('Enter');
  await waitReady(page, focusedRoom);
  const focusStyle = await page.evaluate(() => {
    const style = getComputedStyle(document.activeElement);
    return `${style.outlineStyle} ${style.outlineWidth} ${style.boxShadow}`;
  });
  ok(!/^none 0px none$/.test(focusStyle), 'keyboard focus has a visible working-ink treatment');
}

async function assertReflowAndAestheticFloor(page, viewport) {
  const root = page.locator('[data-aisthesis-carrier="1"]');
  ok(await root.getAttribute('data-layout-mode') === viewport.mode,
    `${viewport.width}px uses the producer-selected ${viewport.mode} composition`);
  ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
    `${viewport.width}px has no horizontal overflow`);
  if (viewport.mode === 'narrow') {
    ok(await page.locator('[data-spatial-field][data-layout-axis="vertical"]').count() >= 1,
      '375px reflows to a genuine vertical causal corridor rather than scaling a wide field');
  }

  const field = page.locator('[data-room][data-foreground="true"] [data-spatial-field]').first();
  if (await field.count()) {
    const rect = await field.boundingBox();
    ok(rect.width >= viewport.width * 0.62 && rect.height >= viewport.height * 0.28,
      `${viewport.width}px spatial picture has consequence-bearing visual presence`);
  }

  const units = await page.$$eval('[data-room][data-foreground="true"] [data-visual-unit]', (nodes) =>
    nodes.map((node) => {
      const rect = node.getBoundingClientRect();
      return [Math.round(rect.width / 8), Math.round(rect.height / 8)];
    }).filter(([width, height]) => width > 0 && height > 0));
  if (units.length >= 6) {
    const buckets = new Map();
    for (const pair of units) {
      const key = pair.join('x');
      buckets.set(key, (buckets.get(key) || 0) + 1);
    }
    const repeated = Math.max(...buckets.values()) / units.length;
    if (repeated >= 0.6) {
      refuse('AESTHETIC-DEAD', `${Math.round(repeated * 100)}% of foreground units repeat one box geometry`);
    }
    ok(true, `${viewport.width}px foreground refuses a repeated-box wall`);
  }

  const hierarchy = await page.evaluate(() => {
    const breakNode = document.querySelector('[data-orientation="causal-break"] span');
    const tertiary = document.querySelector('[data-tertiary] span');
    if (!breakNode || !tertiary) return null;
    const a = getComputedStyle(breakNode);
    const b = getComputedStyle(tertiary);
    return { breakSize: parseFloat(a.fontSize), tertiarySize: parseFloat(b.fontSize),
      breakWeight: parseFloat(a.fontWeight), tertiaryWeight: parseFloat(b.fontWeight) };
  });
  ok(Boolean(hierarchy)
    && (hierarchy.breakSize >= hierarchy.tertiarySize * 1.12
      || hierarchy.breakWeight >= hierarchy.tertiaryWeight + 150),
  `${viewport.width}px dominant causal break has a visible attention hierarchy`);
}

async function assertGrayscaleAndReducedMotion(page) {
  await page.addStyleTag({ content: 'html { filter: grayscale(1) !important; }' });
  const stateWords = await page.locator('[data-orientation="currentness"]').innerText();
  ok(/CURRENT|LAST.TRUSTED|STALE|UNKNOWN|REFUSED/i.test(stateWords),
    'grayscale preserves currentness as an explicit word');
  const moving = await page.$$eval('[data-motion]', (nodes) => nodes.map((node) => {
    const style = getComputedStyle(node);
    return [style.animationDuration, style.transitionDuration];
  }));
  ok(moving.every(([animation, transition]) => animation === '0s' && transition === '0s'),
    'reduced motion removes decorative and geometric interpolation');
}

async function walkViewport(base, viewport, shotPath) {
  const browser = await chromium.launch({ executablePath: chrome });
  const context = await browser.newContext({
    viewport: { width: viewport.width, height: viewport.height },
    reducedMotion: 'reduce',
    colorScheme: 'light',
  });
  const page = await context.newPage();
  const writes = [];
  const errors = [];
  page.on('request', (request) => {
    if (!['GET', 'HEAD'].includes(request.method())) writes.push(`${request.method()} ${request.url()}`);
  });
  page.on('pageerror', (error) => errors.push(String(error)));
  const startedAt = Date.now();
  await page.goto(`${base}/front`, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await waitReady(page);
  await assertNoPredecessorShell(page);
  await assertOneForegroundRoom(page, (await carrierState(page)).room);
  await assertColdOrientation(page, viewport, startedAt);
  await assertNativeControls(page, viewport);
  await assertReflowAndAestheticFloor(page, viewport);
  ok(!HASH_WALLPAPER.test(await visibleTextWithoutAudit(page)),
    `${viewport.width}px resting face has no hash wallpaper`);
  const screenshot = await page.screenshot({ path: shotPath, fullPage: true, animations: 'disabled' });

  if (viewport.width === 1536) {
    await assertRoomsAndRendererFitness(page);
    await assertDescentAndBack(page);
    await assertSemanticMemory(page);
    await assertReconstructionObservatory(page);
    await assertKeyboard(page);
    await assertGrayscaleAndReducedMotion(page);
  }

  const storage = await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length }));
  ok(storage.local === 0 && storage.session === 0,
    `${viewport.width}px carrier founds no local/session browser truth`);
  ok(writes.length === 0, `${viewport.width}px read-only walk makes no POST/write request (${writes.join(', ')})`);
  ok(errors.length === 0, `${viewport.width}px walk has no page errors (${JSON.stringify(errors)})`);
  await browser.close();
  return screenshot;
}

async function deterministicScreenshot(base, viewport, shotPath) {
  const browser = await chromium.launch({ executablePath: chrome });
  const context = await browser.newContext({
    viewport: { width: viewport.width, height: viewport.height },
    reducedMotion: 'reduce',
    colorScheme: 'light',
  });
  const page = await context.newPage();
  await page.goto(`${base}/front`, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await waitReady(page);
  const screenshot = await page.screenshot({ path: shotPath, fullPage: true, animations: 'disabled' });
  await browser.close();
  return screenshot;
}

async function assertLiveManuscriptWork(base, viewport, shotPath) {
  const browser = await chromium.launch({ executablePath: chrome });
  const context = await browser.newContext({
    viewport: { width: viewport.width, height: viewport.height },
    reducedMotion: 'reduce',
    colorScheme: 'light',
  });
  const page = await context.newPage();
  const writes = [];
  const errors = [];
  page.on('request', (request) => {
    if (!['GET', 'HEAD'].includes(request.method())) writes.push(`${request.method()} ${request.url()}`);
  });
  page.on('pageerror', (error) => errors.push(String(error)));
  await page.goto(`${base}/front?lens=work&project=paper_eigen&grade=mid`, {
    waitUntil: 'domcontentloaded', timeout: 30000,
  });
  await waitReady(page, 'work');

  const surface = page.locator('[data-renderer="manuscript-work-surface"] .manuscript-work');
  ok(await surface.count() === 1,
    `${viewport.width}px Work Picture mounts one real manuscript work surface`);
  ok(await surface.locator('.manuscript-work__section').count() > 0
    && await surface.locator('.manuscript-work__block').count() > 0,
  `${viewport.width}px Work exposes a navigable manuscript spine and source content`);
  ok(await surface.locator('.manuscript-work__stage').count() > 0,
    `${viewport.width}px Work carries the real build and release journey`);
  ok(await page.locator('.work-journey').count() === 0,
    `${viewport.width}px Picture replaces the capability ledger instead of stacking beneath it`);
  ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
    `${viewport.width}px manuscript Work reflows without page overflow`);

  const before = await carrierState(page);
  const block = surface.locator('.manuscript-work__block').first();
  const anchor = await block.getAttribute('data-semantic-anchor');
  const historyBefore = await page.evaluate(() => history.length);
  await block.click();
  await page.waitForFunction((expected) => {
    const root = document.querySelector('[data-aisthesis-carrier="1"]');
    return root?.dataset.ready === 'true'
      && root?.dataset.focusHandle === expected
      && root?.dataset.grade === 'detail';
  }, anchor);
  ok((await page.evaluate(() => history.length)) === historyBefore + 1,
    `${viewport.width}px source descent is one shared URL/history transition`);
  ok(new URL(page.url()).searchParams.get('focus') === anchor,
    `${viewport.width}px source descent carries the semantic anchor in the shared URL`);
  await page.goBack();
  await page.waitForFunction((expected) => {
    const root = document.querySelector('[data-aisthesis-carrier="1"]');
    return root?.dataset.ready === 'true'
      && root?.dataset.shownHandle === expected.shown;
  }, before);
  ok(sameState(await carrierState(page), before),
    `${viewport.width}px Back restores exact Work focus/grade/shown/omission/layout state`);
  ok(!HASH_WALLPAPER.test(await visibleTextWithoutAudit(page)),
    `${viewport.width}px manuscript Work keeps receipt ids out of the resting human face`);
  await page.screenshot({ path: shotPath, fullPage: true, animations: 'disabled' });
  ok(writes.length === 0,
    `${viewport.width}px manuscript Work remains read-only (${writes.join(', ')})`);
  ok(errors.length === 0,
    `${viewport.width}px manuscript Work has no page errors (${JSON.stringify(errors)})`);
  await browser.close();
}

(async () => {
  if (!chrome) throw new Error('Chromium is absent; carrier acceptance is UNPROVEN');
  mkdirSync(SHOTS, { recursive: true });
  const repoRoot = process.cwd();
  const port = await freePort();
  const base = `http://127.0.0.1:${port}`;
  scanner = spawn(PY, ['-m', 'laplace.web.scanner', '--port', String(port)], {
    cwd: repoRoot,
    env: {
      ...process.env,
      PYTHONPATH: `${repoRoot}/src`,
      LAPLACE_NO_PREWARM: '1',
      LAPLACE_TEST_PROCESS: '1',
    },
    stdio: 'ignore',
  });
  await waitFor(`${base}/front`);

  try {
    for (const viewport of VIEWPORTS) {
      const firstPath = `${SHOTS}/front-carrier-${viewport.width}-a.png`;
      const secondPath = `${SHOTS}/front-carrier-${viewport.width}-b.png`;
      await walkViewport(base, viewport, firstPath);
      await deterministicScreenshot(base, viewport, secondPath);
      const changedPixels = screenshotDifferencePixels(firstPath, secondPath);
      ok(changedPixels <= MAX_CHROMIUM_RASTER_VARIANCE_PIXELS,
        `${viewport.width}px fresh-process screenshot geometry is deterministic (Chromium raster variance ${changedPixels}/${MAX_CHROMIUM_RASTER_VARIANCE_PIXELS} pixels)`);
      await assertLiveManuscriptWork(
        base,
        viewport,
        `${SHOTS}/front-work-${viewport.width}.png`,
      );
    }
    console.log(`\nALL GREEN — ${passed} assertions`);
    console.log(`screenshots: ${SHOTS}/front-carrier-{1536,768,375}-{a,b}.png`);
    console.log(`Work screenshots: ${SHOTS}/front-work-{1536,768,375}.png`);
  } finally {
    if (scanner) scanner.kill();
  }
})().catch((error) => {
  console.error(`\n${error.message}`);
  if (scanner) scanner.kill();
  process.exit(1);
});
