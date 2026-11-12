// Standalone interaction specimen for the shell-level semantic feedback overlay.
// Run: node tests/front_feedback.playwright.mjs

import { createRequire } from 'module';
import { execSync } from 'child_process';
import { existsSync, mkdirSync, readFileSync } from 'fs';
import path from 'path';

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

const modulePath = path.join(process.cwd(), 'src/laplace/web/static_shared/front_feedback.mjs');
const source = readFileSync(modulePath, 'utf8');
const liveURL = process.env.LAPLACE_FEEDBACK_LIVE_URL || '';
const liveOnly = process.env.LAPLACE_FEEDBACK_LIVE_ONLY === '1';
const screenshotRoot = process.env.LAPLACE_FEEDBACK_SCREENSHOT_DIR || '/tmp/laplace-front-feedback-live';
let passed = 0;

function ok(condition, message) {
  if (!condition) throw new Error(`ASSERT FAILED: ${message}`);
  passed += 1;
  console.log('  ok -', message);
}

ok(!/localStorage|sessionStorage/.test(source), 'the overlay contains no browser-local truth store');
ok(!/xpath|dom_path|css_selector/.test(source), 'the overlay never captures a DOM path');
ok(/data-semantic-anchor/.test(source), 'the overlay delegates through semantic data anchors');

const html = `<!doctype html><meta charset="utf-8">
<style>
  html,body{margin:0;min-height:100%;font:16px system-ui;background:#f5f1e8;color:#17202b}
  main{padding:64px 28px;display:grid;gap:48px;max-width:900px;margin:auto}
  .causal-object{min-height:72px;padding:16px;border:1px solid currentColor;border-radius:12px;background:transparent;color:inherit;text-align:left}
</style>
<main data-aisthesis-carrier="1" data-model-handle="front-model:sha256:model"
 data-shown-handle="front-shown:sha256:shown" data-room="work"
 data-focus-handle="work:walk:content-canvas" data-grade="detail" data-exposition="E3"
 data-currentness="CURRENT" data-source-handle="source-v1">
  <button class="causal-object" data-semantic-anchor="work:walk:content-canvas"
    data-semantic-kind="object" data-semantic-label="Manuscript working canvas"
    data-feedback-route='{"owner":"Aisthesis","surface":"Work"}'>
    <strong>Manuscript working canvas</strong><br>Source-faithful text and figures
  </button>
  <button class="causal-object" data-semantic-anchor="work:pipeline:release-chain"
    data-semantic-kind="edge" data-semantic-label="Release chain">
    <strong>Release chain</strong><br>From brief to publication verdict
  </button>
</main>`;

(async () => {
  const browser = await chromium.launch(chrome ? { executablePath: chrome } : {});
  try {
    for (const width of liveOnly ? [] : [1536, 768, 375]) {
      const page = await browser.newPage({ viewport: { width, height: 812 }, reducedMotion: 'reduce' });
      await page.setContent(html);
      await page.evaluate(async ({ source }) => {
        const url = URL.createObjectURL(new Blob([source], { type: 'text/javascript' }));
        const module = await import(url);
        const rows = [];
        let stale = false;
        const clone = (value) => JSON.parse(JSON.stringify(value));
        const transport = {
          async read({ visible_anchor_ids }) {
            return {
              schema_version: 'laplace.front-feedback-projection/1',
              status: 'CURRENT',
              persistence: {
                required_adapter_schema: 'laplace.front-feedback-adapter/1',
                available: true,
                authority_effect: 'none',
              },
              annotations: rows.map((row) => ({
                ...clone(row),
                anchor_currentness: {
                  status: stale ? 'STALE' : 'CURRENT',
                  visibility: visible_anchor_ids.includes(row.anchor.semantic_anchor) ? 'VISIBLE' : 'OFF_CAMERA',
                  reconcile_available: stale,
                  reconcile_candidates: stale ? [clone(row.anchor)] : [],
                },
                routing: { state: 'DERIVED', authority_granted: false, authority_effect: 'none' },
              })),
              counts: { OPEN: rows.filter((row) => row.state === 'OPEN').length },
            };
          },
          async command(command) {
            window.__commands.push(clone(command));
            if (command.action === 'CREATE') {
              rows.push({
                annotation_id: `annotation:${rows.length + 1}`,
                text: command.text,
                state: 'OPEN',
                actor: command.actor,
                anchor: clone(command.anchor),
              });
            } else if (command.action === 'TRANSITION') {
              const row = rows.find((item) => item.annotation_id === command.annotation_id);
              if (row) row.state = command.state;
            } else if (command.action === 'RECONCILE') {
              const row = rows.find((item) => item.annotation_id === command.annotation_id);
              if (row) row.anchor = clone(command.anchor);
              stale = false;
            }
            return { ok: true, status: 'APPENDED' };
          },
          markStale() { stale = true; },
        };
        window.__commands = [];
        window.__transport = transport;
        window.__feedback = module.mountFrontFeedback({
          root: document.querySelector('main'),
          actor: 'gerard',
          transport,
        });
      }, { source });

      await page.waitForSelector('[data-feedback-toggle]');
      const toggle = page.locator('[data-feedback-toggle]');
      const toggleBox = await toggle.boundingBox();
      ok(toggleBox.width >= 44 && toggleBox.height >= 44, `${width}px comment hotkey is a >=44px visible control`);
      ok(/Alt Shift C/.test(await toggle.getAttribute('aria-label')), `${width}px hotkey is discoverable in the control label`);

      await page.keyboard.press('Alt+Shift+C');
      ok(await toggle.getAttribute('aria-pressed') === 'true', `${width}px hotkey enters Comment mode`);
      const canvas = page.locator('[data-semantic-anchor="work:walk:content-canvas"]');
      await canvas.hover();
      ok(await canvas.getAttribute('data-front-feedback-hover') === 'true', `${width}px hover outlines the semantic object`);
      await canvas.click();
      await page.waitForSelector('[data-feedback-composer] textarea');
      ok(await page.locator('[role="dialog"]').getAttribute('aria-label') === 'Comment on Manuscript working canvas',
        `${width}px click pins an in-place composer to human-labelled meaning`);
      await page.locator('[data-feedback-composer] textarea').fill('The equation explanation needs a visual descent here.');
      await page.locator('[data-feedback-composer] button[type="submit"]').click();
      await page.waitForFunction(() => document.querySelector('[data-feedback-toggle] .front-feedback-toggle__count')?.textContent === '1');
      ok(await page.locator('[data-feedback-marker-for="work:walk:content-canvas"]').count() === 1,
        `${width}px canonical response rehydrates one marker`);

      const command = await page.evaluate(() => window.__commands[0]);
      ok(command.anchor.semantic_anchor === 'work:walk:content-canvas', `${width}px command binds stable semantic identity`);
      ok(command.anchor.model_handle && command.anchor.shown_handle, `${width}px command binds model and shown handles`);
      ok(command.anchor.selection.lens === 'work' && command.anchor.selection.grade === 'detail'
        && command.anchor.selection.exposition === 'E3', `${width}px command binds the exact camera selection`);
      ok(command.anchor.selection.viewport === (width <= 480 ? 'narrow' : width <= 1000 ? 'medium' : 'wide'),
        `${width}px command binds the exact viewport class`);
      ok(command.anchor.source.source_handle === 'source-v1' && command.anchor.currentness.status === 'CURRENT',
        `${width}px command binds source and currentness`);
      ok(command.anchor.selection_geometry.width > 0 && command.anchor.selection_geometry.height > 0,
        `${width}px optional selection geometry is captured without a DOM address`);
      ok(command.anchor.route.authority !== true, `${width}px derived route grants no authority`);

      // Re-render the room and move the same semantic identity. The marker must follow it.
      await page.evaluate(() => {
        const old = document.querySelector('[data-semantic-anchor="work:walk:content-canvas"]');
        const replacement = old.cloneNode(true);
        replacement.textContent = 'Manuscript working canvas — Conversation camera';
        old.replaceWith(replacement);
        document.querySelector('main').dataset.room = 'conversation';
      });
      await page.evaluate(() => window.__feedback.refresh());
      ok(await page.locator('[data-feedback-marker-for="work:walk:content-canvas"]').count() === 1,
        `${width}px marker rehydrates after a cross-lens render`);

      // A moved source remains visible as STALE and can be reconciled to the pinned object.
      await page.evaluate(() => { window.__transport.markStale(); return window.__feedback.refresh(); });
      const marker = page.locator('[data-feedback-marker-for="work:walk:content-canvas"]');
      ok(await marker.getAttribute('data-anchor-state') === 'STALE', `${width}px moved anchor remains visibly STALE`);
      await marker.click();
      await page.locator('[data-feedback-action="reconcile"]').click();
      await page.waitForFunction(() => window.__commands.at(-1)?.action === 'RECONCILE');
      ok(await marker.getAttribute('data-anchor-state') === 'CURRENT', `${width}px re-anchor appends a reconcile command and restores current marker`);

      await marker.click();
      await page.locator('[data-feedback-action="resolve"]').click();
      await page.waitForFunction(() => window.__commands.at(-1)?.state === 'RESOLVED');
      ok((await page.evaluate(() => window.__commands.at(-1))).action === 'TRANSITION',
        `${width}px resolution is a canonical lifecycle command`);

      await page.keyboard.press('Escape');
      ok(await toggle.getAttribute('aria-pressed') === 'false', `${width}px Escape exits Comment mode reversibly`);
      ok((await page.evaluate(() => Object.keys(window).filter((key) => /^frontFeedbackTruth/i.test(key)).length)) === 0,
        `${width}px overlay founds no browser truth namespace`);
      await page.close();
    }

    const fencePage = await browser.newPage({
      viewport: { width: 375, height: 812 },
      colorScheme: 'dark',
      reducedMotion: 'reduce',
    });
    await fencePage.setContent(`<style>html{filter:grayscale(1)}${html.match(/<style>([\s\S]*?)<\/style>/)?.[1] || ''}</style>${html.replace(/<!doctype html><meta charset="utf-8">\s*<style>[\s\S]*?<\/style>/, '')}`);
    await fencePage.evaluate(async ({ source }) => {
      const url = URL.createObjectURL(new Blob([source], { type: 'text/javascript' }));
      const module = await import(url);
      const anchor = {
        schema_version: 'laplace.front-semantic-anchor/1',
        semantic_anchor: 'work:walk:content-canvas',
        kind: 'object',
        label: 'Manuscript working canvas',
      };
      let gatewayCurrent = true;
      window.__fenceCommands = [];
      const transport = {
        markNoncurrent() { gatewayCurrent = false; },
        async read() {
          return {
            schema_version: 'laplace.front-feedback-projection/1',
            status: gatewayCurrent ? 'CURRENT' : 'UNKNOWN',
            persistence: {
              available: true,
              refusal: gatewayCurrent ? null : 'CANONICAL_ADAPTER_NOT_CURRENT',
              authority_effect: 'none',
            },
            annotations: [{
              annotation_id: 'annotation:stale', text: 'Keep this attached.', state: 'OPEN', anchor,
              anchor_currentness: { status: 'STALE', visibility: 'VISIBLE', reconcile_available: true },
            }],
            counts: { OPEN: 1 },
          };
        },
        async command(command) {
          window.__fenceCommands.push(command);
          return { ok: true };
        },
      };
      window.__fenceTransport = transport;
      window.__feedbackFence = module.mountFrontFeedback({
        root: document.querySelector('main'),
        actor: 'gerard',
        transport,
      });
    }, { source });
    await fencePage.waitForFunction(() =>
      document.querySelector('[data-feedback-toggle]')?.dataset.feedbackPersistence === 'available');
    await fencePage.keyboard.press('Alt+Shift+C');
    const fenceAnchor = fencePage.locator('[data-semantic-anchor="work:walk:content-canvas"]');
    await fenceAnchor.focus();
    await fencePage.keyboard.press('Enter');
    const fenceComposer = fencePage.locator('.front-feedback-composer');
    await fenceComposer.waitFor();
    ok(await fenceComposer.locator('[data-feedback-write-control]').evaluateAll((items) => items.every((item) => !item.disabled)),
      '375px CURRENT feedback controls begin writable through the exact adapter');
    await fencePage.evaluate(() => {
      window.__fenceTransport.markNoncurrent();
      return window.__feedbackFence.refresh();
    });
    await fencePage.waitForFunction(() =>
      document.querySelector('[data-feedback-toggle]')?.dataset.feedbackRefusal === 'CANONICAL_ADAPTER_NOT_CURRENT');
    const fencedControls = fenceComposer.locator('[data-feedback-write-control]');
    const fencedControlCount = await fencedControls.count();
    const projectedAnnotations = await fencePage.evaluate(() => window.__feedbackFence.getProjection().annotations?.length || 0);
    ok(fencedControlCount === 5 && projectedAnnotations === 1,
      '375px a live current-to-non-current transition fences all five feedback writes in place');
    ok(await fencedControls.evaluateAll((items) => items.every((item) => item.disabled)),
      '375px Bank, draft, resolve, withdraw and re-anchor controls are natively disabled');
    ok((await fenceComposer.locator('[role="alert"]').innerText()).includes('Writes refused')
      && (await fenceComposer.locator('[role="alert"]').innerText()).includes('CANONICAL_ADAPTER_NOT_CURRENT'),
    '375px feedback refusal is visible in human words with the exact cause');
    ok(await fenceComposer.locator('[data-feedback-action="cancel"]').isEnabled(),
      '375px refusal preserves the reversible Cancel control');
    await fencedControls.evaluateAll((items) => items.forEach((item) => item.click()));
    await fenceComposer.locator('form').evaluate((form) =>
      form.dispatchEvent(new SubmitEvent('submit', { bubbles: true, cancelable: true })));
    ok(await fencePage.evaluate(() => window.__fenceCommands.length) === 0,
      '375px scripted activation cannot cross the non-current feedback gate');
    await fenceComposer.locator('[data-feedback-action="cancel"]').focus();
    let keyboardLandedOnWrite = false;
    for (let index = 0; index < 10; index += 1) {
      await fencePage.keyboard.press('Tab');
      keyboardLandedOnWrite ||= await fencePage.evaluate(() =>
        document.activeElement?.hasAttribute('data-feedback-write-control'));
    }
    ok(!keyboardLandedOnWrite, '375px disabled feedback writes are absent from keyboard activation');
    ok(await fencePage.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches),
      '375px refusal preserves the reduced-motion contract');
    ok((await fencePage.evaluate(() => getComputedStyle(document.documentElement).filter)).includes('grayscale'),
      '375px refusal remains explicit without colour');
    ok(await fencePage.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      '375px refusal introduces no horizontal overflow');
    await fencePage.close();

    if (liveURL) {
      mkdirSync(screenshotRoot, { recursive: true });
      for (const width of [1536, 768, 375]) {
        const page = await browser.newPage({ viewport: { width, height: 900 }, reducedMotion: 'reduce' });
        const errors = [];
        let feedbackPosts = 0;
        page.on('pageerror', (error) => errors.push(String(error)));
        page.on('request', (request) => {
          if (request.url().includes('/front/feedback') && request.method() === 'POST') feedbackPosts += 1;
        });
        await page.goto(liveURL, { waitUntil: 'domcontentloaded', timeout: 30000 });
        await page.waitForSelector('[data-aisthesis-carrier="1"][data-ready="true"]', { timeout: 30000 });
        const liveToggle = page.locator('[data-feedback-toggle]');
        await liveToggle.waitFor();
        await page.waitForFunction(() =>
          document.querySelector('[data-feedback-toggle]')?.dataset.feedbackRefusal === 'CANONICAL_ADAPTER_UNAVAILABLE');
        ok((await liveToggle.innerText()).includes('Comments unavailable'),
          `${width}px live carrier names the unavailable comment state in human words`);
        ok((await liveToggle.getAttribute('title')).includes('CANONICAL_ADAPTER_UNAVAILABLE'),
          `${width}px live carrier exposes the exact canonical adapter refusal`);
        await page.keyboard.press('Alt+Shift+C');
        const anchored = page.locator('[data-semantic-anchor]').first();
        await anchored.waitFor();
        ok(Boolean(await anchored.getAttribute('data-semantic-label')),
          `${width}px live carrier exposes stable human-labelled semantic anchors`);
        await anchored.click();
        const composer = page.locator('[role="dialog"][aria-label^="Comment on"]');
        await composer.waitFor();
        ok((await composer.locator('[data-feedback-persistence="unavailable"]').innerText())
          .includes('Writes refused'), `${width}px live composer visibly refuses before the author writes`);
        ok(await composer.locator('textarea').isDisabled()
          && await composer.locator('button[type="submit"]').isDisabled(),
        `${width}px live draft and Bank comment controls are natively disabled`);
        await composer.locator('button[type="submit"]').evaluate((button) => button.click());
        await composer.locator('form').evaluate((form) =>
          form.dispatchEvent(new SubmitEvent('submit', { bubbles: true, cancelable: true })));
        await page.waitForTimeout(20);
        ok(feedbackPosts === 0, `${width}px live writer gate emits no POST or fallback persistence attempt`);
        ok((await composer.locator('.front-feedback-status').innerText()).includes('canonical annotation writer'),
          `${width}px scripted submit retains a visible human refusal`);
        ok(errors.length === 0, `${width}px live overlay emits no page error`);
        await page.screenshot({ path: path.join(screenshotRoot, `feedback-${width}.png`), fullPage: false });
        await page.close();
      }
    }
  } finally {
    await browser.close();
  }
  console.log(`front feedback: ${passed} assertions passed`);
})().catch((error) => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
