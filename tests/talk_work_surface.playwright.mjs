// Standalone visual and interaction proof for the source-bearing Talk surface.
import { createRequire } from 'module';
import { createHash } from 'crypto';
import { execSync } from 'child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs';
import path from 'path';

const require = createRequire(import.meta.url);
const roots = [
  execSync('npm root -g').toString().trim() + '/playwright',
  `${process.cwd()}/node_modules/playwright`,
  '/home/phujck/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright',
  '/home/phujck/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright-core',
  '/usr/lib/chatgpt/resources/cua_node/lib/node_modules/playwright-core',
];
const pwRoot = roots.find(existsSync);
if (!pwRoot) throw new Error(`Playwright is absent; searched ${roots.join(', ')}`);
const { chromium } = require(pwRoot);
const chrome = execSync("find /opt/pw-browsers \"$HOME/.cache/ms-playwright\" -type f -path '*/chrome-linux*/chrome' -print -quit 2>/dev/null || true").toString().trim();
const repo = process.cwd();
const modulePath = path.join(repo, 'src/laplace/web/static_shared/talk_work_surface.mjs');
const moduleSource = readFileSync(modulePath, 'utf8');
const shots = path.join(repo, 'artifacts', 'aisthesis', 'talk-work-surface');
mkdirSync(shots, { recursive: true });

let passed = 0;
function ok(value, label) {
  if (!value) throw new Error(`ASSERT FAILED: ${label}`);
  passed += 1;
  console.log('  ok -', label);
}

const beatRows = [
  ['problem', 'What stateless tools lose', 'The problem must be felt before the architecture appears.', 'Memory and judgement do not survive the session.', 'EIGEN_ARCHITECTURE.md', 'A broken continuity line'],
  ['compression', 'Learning is compression', 'One idea should carry the architecture.', 'A short model predicts the long description.', 'blueprint.md · core idea', 'Three readings of compression'],
  ['atom', 'Group, then compute', 'The repeating atom makes the larger machine inevitable.', 'A coarse object stands in for the interactions beneath it.', 'DERIVATION_SPINE.md · beat 4', 'A group folding into one node'],
  ['atlas', 'The conceptric', 'The atom needs a durable place to grow.', 'One typed graph can be read at many scales.', 'EIGEN_ARCHITECTURE.md · component 1', 'A live multiscale field'],
  ['judgement', 'Grounded judgement', 'Compression needs an external fitness signal.', 'Every proposal remains checkable and corrigible.', 'EIGEN_DIARY.md · standing law', 'A causal cut and author ruling'],
  ['soul', 'The transmitted centre', 'Some commitments are inherited rather than derived.', 'The soul is a sample grown against.', 'soul transfer · source custody', 'A thread crossing a gap'],
  ['continuity', 'Reconstruction across gaps', 'The memory problem remains after the components.', 'Continuity is faithful reconstruction, not perfect recall.', 'EIGEN_PROTOCOL.md', 'A stitch across sessions'],
  ['frontier', 'The open loop', 'The talk should end at the part still unpaid.', 'The endogenous fitness loop remains the frontier.', 'EIGEN_ARCHITECTURE.md · component 5', 'An open recurrence'],
];

const fixture = {
  schema_version: 'laplace.aisthesis-talk-work/1',
  semantic_anchor: 'work:talk',
  title: 'Eigen: A Machine That Explains Itself',
  state: 'UNKNOWN',
  read_only: true,
  authority_effect: 'none',
  primitives: [
    { id: 'source', semantic_anchor: 'talk:primitive:source', label: 'Source material', value: 'The engine canon, architecture, diary, protocol and literature corpus.', state: 'COMPLETE' },
    { id: 'audience', semantic_anchor: 'talk:primitive:audience', label: 'Audience', value: 'A collaborator deciding whether the architecture is principled.', state: 'COMPLETE' },
    { id: 'message', semantic_anchor: 'talk:primitive:message', label: 'Message', value: 'Compression is learning, applied even to the machine itself.', state: 'COMPLETE' },
  ],
  spine: {
    semantic_anchor: 'talk:spine', label: 'Motivated spine', state: 'COMPLETE', beat_count: beatRows.length,
    beats: beatRows.map(([id, title, motivation, claim, origin, visual], order) => ({
      schema_version: 'laplace.aisthesis-talk-beat/1', id, semantic_anchor: `talk:beat:${id}`,
      title, motivation, claim, origin, visual, state: 'COMPLETE', order,
      citations: id === 'compression' ? ['mehta2014exact', 'tishby2015deep'] : [],
      assets: visual ? [{ id: `${id}-visual`, state: id === 'atlas' ? 'UNKNOWN' : 'COMPLETE' }] : [],
    })),
  },
  postures: [
    { id: 'generation', semantic_anchor: 'talk:posture:generation', label: 'Generate from the spine', state: 'UNKNOWN', reason: 'The deterministic deck backend is not joined.' },
    { id: 'ledger', semantic_anchor: 'talk:posture:ledger', label: 'Rendered talk ledger', state: 'UNKNOWN', reason: 'No rendered-deck receipt is joined.' },
    { id: 'rehearsal', semantic_anchor: 'talk:posture:rehearsal', label: 'Rehearsal cadence', state: 'UNKNOWN', reason: 'No timed rehearsal receipt is joined.' },
    { id: 'export', semantic_anchor: 'talk:posture:export', label: 'Export and listing', state: 'UNKNOWN', reason: 'No exported deck is joined.' },
  ],
  projection_law: {
    source_of_truth: 'primitives + motivated spine + storyboard beats', deck_role: 'generated projection',
    visual_editing: 'governed beat regeneration', direct_slide_truth: false, renderer_executes: false,
  },
};

const pageStyle = `
:root{--bg:#0d1118;--panel:#141a24;--panel2:#192131;--ink:#eef0f4;--ink2:#aeb7c6;--dim:#788496;--edge:#232c3b;--edge2:#465066;--accent:#d5a952;--gold-light:#efd18c;--keystone:#9db0d2;--ok:#7fc6ad;--bad:#e17b7b;--serif:Georgia,serif;--display:system-ui;--mono:monospace}
*{box-sizing:border-box}html,body{margin:0;min-height:100%;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui}body{padding:clamp(12px,3vw,44px)}#mount{max-width:1380px;margin:auto}button:focus-visible,a:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
`;

ok(!/\bfetch\s*\(|XMLHttpRequest|WebSocket|localStorage|sessionStorage|history\./.test(moduleSource),
  'renderer owns no network, browser truth or history');
ok(!/#[0-9a-fA-F]{3,8}\b|\b(?:rgb|hsl)a?\s*\(/.test(moduleSource),
  'renderer owns no private palette');
ok(moduleSource.includes('prefers-reduced-motion'), 'reduced motion is a first-class contract');
ok(moduleSource.toLowerCase().includes('governed beat regeneration'), 'the interface teaches the no-direct-slide-truth law');

async function render(browser, width, { audit = false, iteration = 1 } = {}) {
  const page = await browser.newPage({ viewport: { width, height: 1000 }, colorScheme: 'dark', reducedMotion: 'reduce' });
  const errors = [];
  page.on('pageerror', (error) => errors.push(String(error)));
  await page.setContent(`<style>${pageStyle}</style><main id="mount"></main>`);
  const result = await page.evaluate(async ({ source, model, audit }) => {
    const url = URL.createObjectURL(new Blob([source], { type: 'text/javascript' }));
    const module = await import(url);
    const events = [];
    module.renderTalkWorkSurface(document.getElementById('mount'), model, {
      selection: { lens: 'work', focus: 'talk:beat:compression', grade: audit ? 'audit' : 'near', exposition: 'E2', edge: null },
      move: (patch) => events.push(patch),
    });
    const beat = document.querySelector('[data-semantic-anchor="talk:beat:atlas"]');
    const primitive = document.querySelector('[data-semantic-anchor="talk:primitive:message"]');
    const rehearsal = document.querySelector('[data-semantic-anchor="talk:posture:rehearsal"]');
    beat.click();
    primitive.click();
    rehearsal.focus();
    rehearsal.click();
    const controls = [...document.querySelectorAll('button,a')];
    const selected = document.querySelector('.talk-work__beat[aria-current=true]');
    return {
      errors: [], events,
      bodyWidth: document.documentElement.scrollWidth,
      viewportWidth: document.documentElement.clientWidth,
      widest: [...document.querySelectorAll('*')].map((item) => ({
        name: item.className || item.tagName,
        right: Math.round(item.getBoundingClientRect().right),
        width: Math.round(item.getBoundingClientRect().width),
      })).sort((left, right) => right.right - left.right)[0],
      controls: controls.length,
      minControl: Math.min(...controls.map((item) => item.getBoundingClientRect().height)),
      beats: document.querySelectorAll('.talk-work__beat').length,
      primitives: document.querySelectorAll('.talk-work__primitive').length,
      pulses: document.querySelectorAll('.talk-work__pulse').length,
      flow: document.querySelectorAll('.talk-work__flow-step').length,
      selected: selected?.dataset.semanticAnchor,
      stageAnchor: document.querySelector('.talk-work__stage')?.dataset.semanticAnchor,
      ribbonDisplay: getComputedStyle(document.querySelector('.talk-work__ribbon')).display,
      stageDisplay: getComputedStyle(document.querySelector('.talk-work__stage')).display,
      sceneTransform: getComputedStyle(document.querySelector('.talk-work__scene')).transform,
      text: document.body.innerText,
      fullIds: (document.body.innerText.match(/(?:sha256:|message:)[0-9a-f]{16,}/gi) || []).length,
      audit: document.querySelector('.talk-work__audit')?.innerText || '',
    };
  }, { source: moduleSource, model: fixture, audit });
  result.errors = errors;
  const buffer = await page.screenshot({ fullPage: true });
  if (iteration === 1) writeFileSync(path.join(shots, `talk-work-${width}${audit ? '-audit' : ''}.png`), buffer);
  await page.close();
  return { result, hash: createHash('sha256').update(buffer).digest('hex') };
}

(async () => {
  const browser = await chromium.launch(chrome ? { executablePath: chrome } : {});
  try {
    for (const width of [1536, 768, 375]) {
      const first = await render(browser, width, { iteration: 1 });
      const second = await render(browser, width, { iteration: 2 });
      const result = first.result;
      ok(result.errors.length === 0, `${width}: renderer raises no browser error`);
      ok(result.bodyWidth <= result.viewportWidth, `${width}: no page-level horizontal overflow (${result.bodyWidth}/${result.viewportWidth}; ${JSON.stringify(result.widest)})`);
      ok(result.minControl >= 44, `${width}: every native control is at least 44px`);
      ok(result.beats === 8 && result.primitives === 3, `${width}: primitives and the full storyboard remain visible`);
      ok(result.pulses === 4 && result.flow === 6, `${width}: rehearsal cadence and export trajectory remain coupled`);
      ok(result.selected === 'talk:beat:compression' && result.stageAnchor === 'talk:beat:compression', `${width}: stable beat focus expands in place`);
      ok(result.events.some((row) => row.focus === 'talk:beat:atlas' && row.grade === 'near'), `${width}: beat descent returns one shared carrier transition`);
      ok(result.events.some((row) => row.focus === 'talk:primitive:message'), `${width}: primitive descent uses the same selection contract`);
      ok(result.events.some((row) => row.focus === 'talk:posture:rehearsal'), `${width}: rehearsal posture is keyboard reachable`);
      ok(result.text.toLowerCase().includes('the beat is the editor') && result.text.toLowerCase().includes('why this beat'), `${width}: regeneration law and motivation remain human visible`);
      ok(result.fullIds === 0, `${width}: no receipt or message hash wallpaper at rest`);
      ok(first.hash === second.hash, `${width}: fresh-process screenshot geometry is deterministic`);
      if (width === 375) {
        ok(result.ribbonDisplay === 'block' && result.stageDisplay === 'block', '375: the talk reflows to a vertical narrative corridor');
        ok(result.sceneTransform === 'none', '375: the stage reflows instead of scaling a wide composition');
      } else {
        ok(result.stageDisplay === 'grid', `${width}: the beat stage uses the available field`);
      }
    }

    const audit = await render(browser, 768, { audit: true, iteration: 1 });
    ok(audit.result.audit.includes('blueprint.md · core idea'), 'Audit reveals the selected beat source, not a global receipt wall');
    ok(!audit.result.audit.includes('frontier'), 'Audit remains attention-local to the selected beat');

    const page = await browser.newPage({ viewport: { width: 768, height: 900 }, colorScheme: 'dark', reducedMotion: 'reduce' });
    await page.setContent(`<style>${pageStyle}html{filter:grayscale(1)}</style><main id="mount"></main>`);
    const grayscale = await page.evaluate(async ({ source, model }) => {
      const url = URL.createObjectURL(new Blob([source], { type: 'text/javascript' }));
      const module = await import(url);
      module.renderTalkWorkSurface(document.getElementById('mount'), model, {
        selection: { lens: 'work', focus: 'talk:beat:compression', grade: 'near', exposition: 'E2', edge: null },
        move: () => {},
      });
      return {
        states: [...document.querySelectorAll('[data-state]')].map((item) => item.dataset.state),
        text: document.body.innerText,
      };
    }, { source: moduleSource, model: fixture });
    ok(grayscale.states.includes('UNKNOWN') && grayscale.text.includes('UNKNOWN'), 'grayscale: unknown producer state survives in words and geometry');
    await page.close();
  } finally {
    await browser.close();
  }
  console.log(`PASS ${passed}/${passed}`);
  console.log(`SCREENSHOTS ${shots}`);
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
