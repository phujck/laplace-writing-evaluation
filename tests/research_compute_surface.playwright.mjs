// Standalone visual and interaction proof for the Research / Compute surface.
import { createHash } from 'crypto';
import { createRequire } from 'module';
import { execFileSync, execSync } from 'child_process';
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
const modulePath = path.join(repo, 'src/laplace/web/static_shared/research_compute_surface.mjs');
const moduleSource = readFileSync(modulePath, 'utf8');
const shots = path.join(repo, 'artifacts', 'aisthesis', 'research-compute-surface');
mkdirSync(shots, { recursive: true });

let passed = 0;
function ok(value, label) {
  if (!value) throw new Error(`ASSERT FAILED: ${label}`);
  passed += 1;
  console.log('  ok -', label);
}

const fixture = {
  schema_version: 'laplace.aisthesis-research-compute/1',
  semantic_anchor: 'research:compute-surface',
  state: 'UNKNOWN',
  reason: 'One external research query remains unvisited.',
  currentness: { status: 'CURRENT', reason: 'Pinned source tuple and observation agree.' },
  query_path: {
    schema_version: 'laplace.aisthesis-query-evidence-path/1',
    semantic_anchor: 'research:query-path',
    state: 'UNKNOWN',
    reason: 'Non-local literature remains unvisited.',
    query: 'How does typed residue change campaign convergence?',
    declared_parameters: { assumption: 'structural', fibre: 'evidence', grade: 2, budget: 32768, beam: 8 },
    stages: [
      { id: 'question', semantic_anchor: 'research:query-stage:question', label: 'Question', state: 'COMPLETE', reason: 'The selected question conditions this read.', order: 0 },
      { id: 'routing', semantic_anchor: 'research:query-stage:routing', label: 'Atlas routing', state: 'COMPLETE', reason: '18 candidates ranked by the declared operator.', count: 18, latency_ms: 14, order: 1 },
      { id: 'descent', semantic_anchor: 'research:query-stage:descent', label: 'Typed descent', state: 'COMPLETE', reason: 'Six source-bearing leaves materialised.', count: 6, latency_ms: 91, order: 2 },
      { id: 'evidence', semantic_anchor: 'research:query-stage:evidence', label: 'Evidence quarry', state: 'COMPLETE', reason: 'Four typed witnesses admitted.', count: 4, order: 3 },
    ],
    regions: [
      { id: 'genesis-ledger', semantic_anchor: 'research:query-region:genesis-ledger', label: 'Genesis revision ledger', class: 'ACCEPTED', state: 'COMPLETE', source_class: 'synthetics', count: 20, depth: 3, continuation: 'atlas://object/genesis-ledger' },
      { id: 'superseded-prompts', semantic_anchor: 'research:query-region:superseded-prompts', label: 'Superseded prompt generations', class: 'REJECTED', state: 'COMPLETE', source_class: 'synthetics', count: 4, depth: 2, continuation: 'atlas://object/superseded-prompts' },
      { id: 'external-literature', semantic_anchor: 'research:query-region:external-literature', label: 'Non-local literature candidates', class: 'UNVISITED', state: 'UNKNOWN', source_class: 'external research', count: 12, continuation: 'research://literature/query' },
    ],
    fog: [
      { id: 'held-out', semantic_anchor: 'research:fog:held-out', label: 'Held-out goal closure', cause: 'COVERAGE', count: 2, reason: 'Two held-out questions are not covered.', continuation: 'atlas://query/held-out' },
      { id: 'budget', semantic_anchor: 'research:fog:budget', label: 'Budget edge', cause: 'BUDGET_TRUNCATION', count: 7, reason: 'Seven candidates were outside the declared budget.', continuation: 'atlas://query/continue?offset=32768' },
    ],
  },
  experiment_matrix: {
    schema_version: 'laplace.aisthesis-experiment-matrix/1',
    semantic_anchor: 'research:experiment-matrix',
    state: 'COMPLETE',
    columns: [
      { id: 'bare', label: 'Bare model', semantic_anchor: 'research:arm:bare' },
      { id: 'eigen', label: 'Eigen recursive', semantic_anchor: 'research:arm:eigen' },
    ],
    phase_order: ['QUESTION_FROZEN', 'ARMED', 'RUNNING', 'METERED', 'BLIND_GRADING', 'SEALED'],
    rows: [
      {
        id: 'superarc', semantic_anchor: 'research:campaign:superarc', label: 'SuperARC campaign', state: 'COMPLETE', question_count: 100,
        cells: [
          { semantic_anchor: 'research:matrix:superarc:bare', arm_id: 'bare', state: 'COMPLETE', phase: 'SEALED', metrics: { score: 0.41, cost_gbp: 18.2, latency_s: 211 }, run_id: 'superarc-bare', continuation: 'campaign://run/superarc-bare' },
          { semantic_anchor: 'research:matrix:superarc:eigen', arm_id: 'eigen', state: 'COMPLETE', phase: 'SEALED', metrics: { score: 0.73, cost_gbp: 24.6, latency_s: 382 }, run_id: 'superarc-eigen', continuation: 'campaign://run/superarc-eigen' },
        ],
      },
      {
        id: 'rehearsal', semantic_anchor: 'research:campaign:rehearsal', label: 'Self-corpus rehearsal', state: 'IN_FLIGHT', question_count: 12,
        cells: [
          { semantic_anchor: 'research:matrix:rehearsal:bare', arm_id: 'bare', state: 'IN_FLIGHT', phase: 'METERED', metrics: { cost_gbp: 2.4, latency_s: 34 }, run_id: 'rehearsal-bare', continuation: 'campaign://run/rehearsal-bare' },
          { semantic_anchor: 'research:matrix:rehearsal:eigen', arm_id: 'eigen', state: 'UNKNOWN', phase: 'UNKNOWN', metrics: {}, run_id: '', reason: 'No run evidence is joined.', continuation: 'campaign://rehearsal' },
        ],
      },
    ],
    runs: [
      { id: 'superarc-bare', semantic_anchor: 'research:run:superarc-bare', label: 'Bare model sealed run', state: 'COMPLETE', phase: 'SEALED', continuation: 'campaign://run/superarc-bare' },
      { id: 'superarc-eigen', semantic_anchor: 'research:run:superarc-eigen', label: 'Eigen recursive sealed run', state: 'COMPLETE', phase: 'SEALED', continuation: 'campaign://run/superarc-eigen' },
      { id: 'rehearsal-bare', semantic_anchor: 'research:run:rehearsal-bare', label: 'Rehearsal metered run', state: 'IN_FLIGHT', phase: 'METERED', continuation: 'campaign://run/rehearsal-bare' },
    ],
  },
  result_comparison: {
    schema_version: 'laplace.aisthesis-result-comparison/1',
    semantic_anchor: 'research:result-comparison',
    state: 'COMPLETE',
    axes: [
      { id: 'cost_gbp', label: 'Cost Gbp', minimum: 18.2, maximum: 24.6 },
      { id: 'latency_s', label: 'Latency S', minimum: 211, maximum: 382 },
      { id: 'score', label: 'Score', minimum: 0.41, maximum: 0.73 },
    ],
    entries: [
      { id: 'bare', semantic_anchor: 'research:result:bare', label: 'Bare model', state: 'COMPLETE', reason: 'Sealed baseline result.', metrics: { score: 0.41, cost_gbp: 18.2, latency_s: 211 }, provenance: { run_id: 'superarc-bare' }, continuation: 'campaign://result/bare' },
      { id: 'eigen', semantic_anchor: 'research:result:eigen', label: 'Eigen recursive', state: 'COMPLETE', reason: 'Sealed recursive result.', metrics: { score: 0.73, cost_gbp: 24.6, latency_s: 382 }, provenance: { run_id: 'superarc-eigen' }, continuation: 'campaign://result/eigen' },
    ],
  },
  read_only: true,
  authority_effect: 'none',
};

const pageBaseStyle = `
  html { background:#0c110f; color:#eee9dc; font-family:Inter,system-ui,sans-serif; }
  body { margin:0; min-width:0; }
  #mount { width:100%; }
  * { box-sizing:border-box; }
`;

function digest(bytes) {
  return createHash('sha256').update(bytes).digest('hex');
}

function pixelDigest(pngBytes) {
  const rgba = execFileSync('/usr/bin/convert', ['png:-', 'rgba:-'], {
    input: pngBytes,
    maxBuffer: 64 * 1024 * 1024,
  });
  return digest(rgba);
}

async function openRenderedPage(browser, width, { grayscale = false } = {}) {
  const page = await browser.newPage({ viewport: { width, height: width === 375 ? 900 : 980 }, colorScheme: 'dark', reducedMotion: 'reduce' });
  await page.setContent(`<style>${pageBaseStyle}${grayscale ? 'html{filter:grayscale(1)}' : ''}</style><main id="mount"></main>`);
  await page.evaluate(async ({ source, model }) => {
    window.__moves = [];
    const url = URL.createObjectURL(new Blob([source], { type: 'text/javascript' }));
    const module = await import(url);
    window.__researchModule = module;
    window.__researchModel = model;
    window.__renderResearch = (selection = {}) => module.renderResearchComputeSurface(
      document.getElementById('mount'),
      model,
      { selection, move: (patch) => window.__moves.push(patch) },
    );
    window.__renderResearch({ lens: 'work', focus: '', grade: 'mid', exposition: 'E1', edge: null });
  }, { source: moduleSource, model: fixture });
  await page.evaluate(async () => {
    await document.fonts.ready;
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  });
  return page;
}

(async () => {
  ok(!/\bfetch\s*\(/.test(moduleSource), 'renderer has no fetch path');
  ok(!/localStorage|sessionStorage/.test(moduleSource), 'renderer has no browser-local truth store');
  ok(!/\bhistory\s*\./.test(moduleSource), 'renderer does not found its own history path');
  ok(!/sha256:|message:/.test(moduleSource), 'renderer source contains no resting receipt wallpaper');

  const browser = await chromium.launch({ headless: true, executablePath: chrome || undefined });
  const firstPass = new Map();
  try {
    for (const width of [1536, 768, 375]) {
      const page = await openRenderedPage(browser, width, { grayscale: width === 768 });
      const facts = await page.evaluate(() => {
        const surface = document.querySelector('[data-renderer="research-compute-surface"]');
        const controls = [...surface.querySelectorAll('button')];
        const anchors = [...surface.querySelectorAll('[data-semantic-anchor]')].map((node) => node.dataset.semanticAnchor);
        const matrixRow = surface.querySelector('.rc-matrix__row:not(.rc-matrix__header)');
        const comparisonSvg = surface.querySelector('.rc-comparison svg');
        const comparisonNarrow = surface.querySelector('.rc-comparison-narrow');
        return {
          text: surface.innerText,
          state: surface.dataset.state,
          currentness: surface.dataset.currentness,
          readOnly: surface.dataset.readOnly,
          overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
          minControl: Math.min(...controls.map((node) => node.getBoundingClientRect().height)),
          controls: controls.length,
          anchorCount: anchors.length,
          uniqueAnchors: new Set(anchors).size,
          regions: [...surface.querySelectorAll('[data-region-class]')].map((node) => node.dataset.regionClass),
          matrixDisplay: getComputedStyle(matrixRow).display,
          svgDisplay: getComputedStyle(comparisonSvg).display,
          narrowDisplay: getComputedStyle(comparisonNarrow).display,
          transitions: controls.map((node) => getComputedStyle(node).transitionDuration),
        };
      });
      ok(facts.currentness === 'CURRENT' && facts.readOnly === 'true', `${width}: current read-only identity is explicit`);
      ok(facts.text.includes('How does typed residue change campaign convergence?'), `${width}: selected question is the visual origin`);
      ok(facts.text.includes('Atlas routing') && facts.text.includes('Typed descent') && facts.text.includes('Evidence quarry'), `${width}: query-to-evidence path survives`);
      ok(facts.regions.join(',') === 'ACCEPTED,REJECTED,UNVISITED', `${width}: accepted, rejected and unvisited regions remain distinct`);
      ok(facts.text.includes('Budget edge') && facts.text.includes('BUDGET TRUNCATION'), `${width}: typed fog is named rather than decorative haze`);
      ok(facts.text.includes('SuperARC campaign') && facts.text.includes('Self-corpus rehearsal'), `${width}: experiment campaigns survive`);
      ok(facts.text.includes('METERED') && facts.text.includes('SEALED'), `${width}: live run altitude is visible`);
      ok(facts.text.includes('Bare model') && facts.text.includes('Eigen recursive'), `${width}: comparable result identities survive`);
      ok(facts.overflow <= 1, `${width}: no horizontal overflow`);
      ok(facts.minControl >= 43.5, `${width}: native controls meet the 44px target`);
      ok(facts.anchorCount === facts.uniqueAnchors, `${width}: visible semantic anchors remain unique`);
      ok(!facts.text.includes('sha256:') && !facts.text.includes('message:'), `${width}: no receipt identifiers at rest`);
      ok(facts.transitions.every((duration) => duration === '0s'), `${width}: reduced motion removes transitions`);
      if (width === 375) {
        ok(facts.matrixDisplay === 'block', '375: experiment matrix becomes a vertical comparison corridor');
        ok(facts.svgDisplay === 'none' && facts.narrowDisplay === 'grid', '375: result field reflows instead of scaling an unreadable SVG');
      } else {
        ok(facts.matrixDisplay === 'grid', `${width}: experiment matrix uses the available comparison field`);
        ok(facts.svgDisplay === 'block', `${width}: wide result comparison retains its parallel-coordinate grammar`);
      }

      const routing = page.getByRole('button', { name: 'Inspect Atlas routing' });
      await routing.focus();
      await routing.press('Enter');
      const keyboardMove = await page.evaluate(() => window.__moves.at(-1));
      ok(keyboardMove.focus === 'research:query-stage:routing' && keyboardMove.grade === 'near', `${width}: keyboard descent emits one exact carrier selection patch`);

      const result = page.getByRole('button', { name: 'Inspect result Eigen recursive' });
      await result.click();
      const resultMove = await page.evaluate(() => window.__moves.at(-1));
      ok(resultMove.focus === 'research:result:eigen' && resultMove.edge === null, `${width}: result descent uses stable semantic identity`);
      await page.evaluate(() => window.__renderResearch({ lens: 'work', focus: 'research:result:eigen', grade: 'near', exposition: 'E2', edge: null }));
      await page.evaluate(async () => {
        await document.fonts.ready;
        await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      });
      await page.mouse.move(1, 1);
      const detail = await page.locator('.rc-detail').innerText();
      ok(detail.includes('Sealed recursive result') && detail.includes('campaign://result/eigen'), `${width}: selected result expands in place to human meaning and exact continuation`);

      const bytes = await page.screenshot({ fullPage: true });
      const shotPath = path.join(shots, `research-compute-${width}.png`);
      writeFileSync(shotPath, bytes);
      firstPass.set(width, pixelDigest(bytes));
      await page.close();
    }
  } finally {
    await browser.close();
  }

  const secondBrowser = await chromium.launch({ headless: true, executablePath: chrome || undefined });
  try {
    for (const width of [1536, 768, 375]) {
      const page = await openRenderedPage(secondBrowser, width, { grayscale: width === 768 });
      await page.evaluate(() => window.__renderResearch({ lens: 'work', focus: 'research:result:eigen', grade: 'near', exposition: 'E2', edge: null }));
      await page.evaluate(async () => {
        await document.fonts.ready;
        await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      });
      await page.mouse.move(1, 1);
      const bytes = await page.screenshot({ fullPage: true });
      ok(pixelDigest(bytes) === firstPass.get(width), `${width}: screenshot pixels are identical in a fresh browser process`);
      await page.close();
    }
  } finally {
    await secondBrowser.close();
  }

  console.log(`PASS ${passed}/${passed}`);
  console.log(`SCREENSHOTS ${shots}`);
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
