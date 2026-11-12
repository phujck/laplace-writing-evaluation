// Standalone visual and interaction proof for the manuscript Work surface.
import { createRequire } from 'module';
import { execFileSync, execSync } from 'child_process';
import { existsSync, mkdirSync, readFileSync } from 'fs';
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
const modulePath = path.join(repo, 'src/laplace/web/static_shared/manuscript_work_surface.mjs');
const moduleSource = readFileSync(modulePath, 'utf8');
const carrierSource = readFileSync(path.join(repo, 'src/laplace/web/static_shared/front_carrier.mjs'), 'utf8');
const shots = path.join(repo, 'artifacts', 'aisthesis', 'manuscript-work-surface');
mkdirSync(shots, { recursive: true });

let passed = 0;
function ok(value, label) {
  if (!value) throw new Error(`ASSERT FAILED: ${label}`);
  passed += 1;
  console.log('  ok -', label);
}

const fixture = {
  schema_version: 'laplace.aisthesis-work-room/1',
  project: 'paper_eigen',
  state: 'UNKNOWN',
  workbench: {
    schema_version: 'laplace.aisthesis-manuscript-workbench/1',
    semantic_anchor: 'work:manuscript-workbench',
    read_only: true,
    authority_effect: 'none',
    manuscript: {
      schema_version: 'laplace.aisthesis-manuscript-surface/1',
      semantic_anchor: 'work:manuscript',
      state: 'COMPLETE',
      title: 'There Is Only One Thing',
      fidelity: 'Content-faithful words, mathematics, figures and document order; geometry remains on the typeset face.',
      counts: { sections: 3, blocks: 8, citations: 4, refs: 3 },
      postures: [
        { id: 'source', semantic_anchor: 'work:manuscript:posture:source', label: 'Source manuscript', state: 'COMPLETE', reason: 'joined from Walk', continuation: '/walk/doc?corpus=paper_eigen' },
        { id: 'pdf', semantic_anchor: 'work:manuscript:posture:pdf', label: 'Typeset PDF geometry', state: 'UNKNOWN', reason: 'Compiled PDF and SyncTeX evidence have not been joined', continuation: '/projection/pdfinfo' },
        { id: 'review', semantic_anchor: 'work:manuscript:posture:review', label: 'Findings and author hand', state: 'COMPLETE', evidence: { findings: 3, parked: 1 }, continuation: '/review/findings?corpus=paper_eigen' },
        { id: 'feedback', semantic_anchor: 'work:manuscript:posture:feedback', label: 'Durable anchored feedback', state: 'UNKNOWN', reason: 'Atlas routing not yet joined', continuation: '/projection/feedback' },
        { id: 'versions', semantic_anchor: 'work:manuscript:posture:versions', label: 'Version history', state: 'COMPLETE', evidence: { count: 5, latest: 'v5' }, continuation: '/review/states?corpus=paper_eigen' },
        { id: 'compile', semantic_anchor: 'work:manuscript:posture:compile', label: 'Compile and hot reload', state: 'COMPLETE', evidence: { state: 'clean' }, continuation: '/projection/recompile' },
        { id: 'redline', semantic_anchor: 'work:manuscript:posture:redline', label: 'Live redline', state: 'COMPLETE', evidence: { before: 'v4', after: 'v5' }, continuation: '/review/compare?corpus=paper_eigen' },
      ],
      sections: [
        {
          id: 'front', semantic_anchor: 'work:manuscript:section:front', title: 'Front matter', state: 'COMPLETE', block_count: 2,
          source: { file: 'main.tex', line_start: 28, line_end: 60 },
          blocks: [
            { id: 'main#quote', semantic_anchor: 'work:manuscript:block:main#quote', kind: 'quote', words: 'To see a World in a Grain of Sand and a Heaven in a Wild Flower.', source: { file: 'main.tex', line_start: 28, line_end: 31 } },
            { id: 'main#abstract', semantic_anchor: 'work:manuscript:block:main#abstract', kind: 'abstract', words: 'A knowledge-organising machine inherits a conjugacy between whole-path meaning and the local generator.', source: { file: 'main.tex', line_start: 34, line_end: 60 } },
          ],
        },
        {
          id: 'two-descriptions', semantic_anchor: 'work:manuscript:section:two-descriptions', title: 'Two descriptions of one dynamics', state: 'COMPLETE', block_count: 3,
          source: { file: 'main.tex', line_start: 63, line_end: 121 },
          blocks: [
            { id: 'main#head', semantic_anchor: 'work:manuscript:block:main#head', kind: 'head', words: 'Two descriptions of one dynamics', source: { file: 'main.tex', line_start: 63, line_end: 63 } },
            { id: 'main#argument', semantic_anchor: 'work:manuscript:block:main#argument', kind: 'para', words: 'The first weighs whole paths. The second steps states. Both are exact, and the craft is moving to the representation where the problem becomes mechanical.', source: { file: 'main.tex', line_start: 66, line_end: 88 } },
            { id: 'main#figure', semantic_anchor: 'work:manuscript:block:main#figure', kind: 'figure', words: 'One dynamics, two complete descriptions: the variational principle and the generator.', source: { file: 'main.tex', line_start: 90, line_end: 98 } },
          ],
        },
        {
          id: 'atlas', semantic_anchor: 'work:manuscript:section:atlas', title: 'The organising machine', state: 'COMPLETE', block_count: 3,
          source: { file: 'main.tex', line_start: 140, line_end: 205 },
          blocks: [
            { id: 'main#atlas-head', semantic_anchor: 'work:manuscript:block:main#atlas-head', kind: 'head', words: 'The organising machine', source: { file: 'main.tex', line_start: 140, line_end: 140 } },
            { id: 'main#atlas-para', semantic_anchor: 'work:manuscript:block:main#atlas-para', kind: 'para', words: 'The Atlas keeps one explodable graph while every interface remains a lens over the same object.', source: { file: 'main.tex', line_start: 143, line_end: 164 } },
            { id: 'main#atlas-equation', semantic_anchor: 'work:manuscript:block:main#atlas-equation', kind: 'equation', words: 'The pullback returns the smallest sufficient neighbourhood for the goal.', source: { file: 'main.tex', line_start: 167, line_end: 174 } },
          ],
        },
      ],
      actions: {
        schema_version: 'laplace.aisthesis-manuscript-action-layer/1',
        semantic_anchor: 'work:manuscript:actions', state: 'COMPLETE', actor: 'gerard', profile: 'profiles/paper.json',
        provider_authority: { state: 'UNKNOWN', reason: 'no stronger provider or seat authority receipt was supplied', required_by_endpoint: false },
        editor: {
          semantic_anchor: 'work:manuscript:editor', state: 'COMPLETE', file: 'paper/main.tex',
          expected_source_digest: 'sha256:' + 'a'.repeat(64), selection_identity:'sha256:'+'e'.repeat(64),
          content: '\\section{Two descriptions of one dynamics}\nThe first weighs whole paths. The second steps states.\n',
          save: {
            semantic_anchor: 'work:manuscript:action:save', state: 'COMPLETE',
            request: { method: 'POST', route: '/projection/tex', query: { file: 'paper/main.tex', corpus: 'paper_eigen', bank: 'editor', author: 'gerard', surface: 'front-work' }, body: {}, body_kind: 'raw-text' },
          },
        },
        compile: {
          semantic_anchor: 'work:manuscript:action:compile', state: 'COMPLETE',
          request: { method: 'POST', route: '/projection/recompile', query: {}, body: { file: 'paper/main.tex', corpus: 'paper_eigen', by: 'gerard' }, body_kind: 'json' },
          status_request: { method: 'GET', route: '/projection/recompile', query: { file: 'paper/main.tex', corpus: 'paper_eigen' }, body: {}, body_kind: 'json' },
        },
        synctex: {
          semantic_anchor: 'work:manuscript:action:synctex', state: 'COMPLETE',
          follow: { method: 'GET', route: '/projection/follow', query: { file: 'paper/main.tex', corpus: 'paper_eigen' }, body: {}, body_kind: 'json' },
          locate: { method: 'GET', route: '/projection/locate', query: { file: 'paper/main.tex', corpus: 'paper_eigen', section: '', line: '' }, body: {}, body_kind: 'json' },
          reverse: { method: 'GET', route: '/projection/synctex', query: { file: 'paper/main.tex', corpus: 'paper_eigen', page: '', x: '', y: '' }, body: {}, body_kind: 'json' },
        },
        versions: {
          semantic_anchor: 'work:manuscript:action:versions', state: 'COMPLETE', rows: [
            { semantic_anchor: 'work:manuscript:version:git-base', version_id: 'git-base', label: 'Committed baseline', actor: 'git', created_at: '09:00', restorable: false },
            { semantic_anchor: 'work:manuscript:version:editor-v1', version_id: 'editor-v1', label: 'Clarify the opening', actor: 'gerard', created_at: '10:00', restorable: true },
            { semantic_anchor: 'work:manuscript:version:editor-v2', version_id: 'editor-v2', label: 'Add the exact mechanism', actor: 'gerard', created_at: '11:00', restorable: true },
          ],
        },
        redline: {
          semantic_anchor: 'work:manuscript:action:redline', state: 'COMPLETE',
          request: { method: 'GET', route: '/review/compare', query: { corpus: 'paper_eigen', a: '', b: '' }, body: {}, body_kind: 'json' },
        },
        restore: {
          semantic_anchor: 'work:manuscript:action:restore', state: 'COMPLETE', restore_as_new_save: true, ui_arm_required: true,
          request: { method: 'POST', route: '/projection/restore', query: {}, body: { file: 'paper/main.tex', version_id: '', corpus: 'paper_eigen' }, body_kind: 'json' },
        },
      },
    },
    pipeline: {
      schema_version: 'laplace.aisthesis-manuscript-pipeline/1', semantic_anchor: 'work:pipeline', state: 'COMPLETE', project: 'paper_eigen', position: 'UNDER CONVERGENCE',
      brief: { brief: { glance: 'The manuscript is under convergence. The last bounded round reduced one named debt.', next_line: 'Next: inspect the selected finding before another round.' } },
      release_states: [
        ['staged', 'Staged', 'PASSED', 'inspect'], ['welded', 'Welded', 'PASSED', 'converge'],
        ['mechanical', 'Mechanically valid', 'PASSED', 'converge'], ['convergence', 'Under convergence', 'CURRENT', 'review candidate'],
        ['locked', 'Candidate locked', 'AHEAD', 'author review'], ['reviewed', 'Author reviewed', 'AHEAD', 'final build'],
        ['clean', 'Final clean build', 'AHEAD', 'final gates'], ['gates', 'Final gates', 'AHEAD', 'accept'],
        ['accepted', 'Author accepted', 'AHEAD', 'release'], ['released', 'Released', 'AHEAD', 'released'],
      ].map(([id, label, status, next_action], order) => ({ id, semantic_anchor: `work:pipeline:stage:${id}`, label, status, next_action, order })),
      mechanisms: [
        ['bibliography', 'Bibliography', 'COMPLETE'], ['figures', 'Figures', 'UNKNOWN'], ['selection', 'Selection', 'COMPLETE'],
        ['derivation', 'Derivation', 'UNKNOWN'], ['evolution', 'Evolution', 'COMPLETE'], ['fitness', 'Fitness', 'UNKNOWN'],
      ].map(([id, label, state]) => ({ id, semantic_anchor: `work:pipeline:mechanism:${id}`, label, state, reason: state === 'COMPLETE' ? 'banked summary is present' : 'mechanism evidence has not been joined' })),
      launch: {
        semantic_anchor: 'work:pipeline:launch', state: 'COMPLETE',
        provider_authority: { state: 'UNKNOWN', reason: 'no stronger provider or seat authority receipt was supplied', required_by_endpoint: false },
        actions: [
          {
            semantic_anchor: 'work:pipeline:launch:storyboard-rebuild', action: 'storyboard-rebuild', label: 'Rebuild the staged spine', what: 'Rebuild only the changed narrative structure.',
            state: 'COMPLETE', organ: 'staged', cost_class: 'local-safe', local_safe: true, model_heavy: false, actor: 'gerard', profile: 'profiles/paper.json', profile_mode: 'EXPLICIT', arm_required: true,
            request: { method: 'POST', route: '/storyboard/run/launch', query: {}, body: { corpus: 'paper_eigen', action: 'storyboard-rebuild', by: 'gerard', armed: false, mode: null, profile: 'profiles/paper.json' }, body_kind: 'json' },
            preflight: { actor: { state: 'COMPLETE', value: 'gerard' }, profile: { state: 'COMPLETE', value: 'profiles/paper.json', mode: 'EXPLICIT' }, arming: { state: 'COMPLETE', required: true }, provider_authority: { state: 'UNKNOWN', required_by_endpoint: false } },
          },
          {
            semantic_anchor: 'work:pipeline:launch:re-projection', action: 're-projection', label: 'Re-project the manuscript', what: 'Bank the model-heavy re-projection request.',
            state: 'COMPLETE', organ: 'staged', cost_class: 'model-heavy', local_safe: false, model_heavy: true, actor: 'gerard', profile: 'profiles/paper.json', profile_mode: 'EXPLICIT', arm_required: true, banks: 'work-order', bank_before_effect: true,
            request: { method: 'POST', route: '/storyboard/run/launch', query: {}, body: { corpus: 'paper_eigen', action: 're-projection', by: 'gerard', armed: false, mode: null, profile: 'profiles/paper.json' }, body_kind: 'json' },
            preflight: { actor: { state: 'COMPLETE', value: 'gerard' }, profile: { state: 'COMPLETE', value: 'profiles/paper.json', mode: 'EXPLICIT' }, arming: { state: 'COMPLETE', required: true }, provider_authority: { state: 'UNKNOWN', required_by_endpoint: false } },
          },
        ],
      },
    },
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
ok(moduleSource.includes('prefers-reduced-motion'), 'reduced motion is a first-class layout contract');
const served = execFileSync('/usr/bin/python3', ['-c', [
  'from laplace.web import shared_ui',
  'status, ctype, body = shared_ui.handle("/shared/manuscript_work_surface.mjs", {})',
  'assert status == 200',
  'assert ctype == "text/javascript; charset=utf-8"',
  'assert b"renderManuscriptWorkSurface" in body',
  'print(len(body))',
].join(';')], {
  cwd: repo,
  env: { ...process.env, PYTHONPATH: `${repo}/src` },
}).toString().trim();
ok(Number(served) === Buffer.byteLength(moduleSource), 'the exact manuscript renderer is served from the shared allowlist');
ok(carrierSource.includes('import { renderManuscriptWorkSurface } from "/shared/manuscript_work_surface.mjs";'),
  'the live carrier imports the manuscript renderer through the shared door');
ok(carrierSource.includes('gradeFromState(activeState) !== "far"')
  && carrierSource.includes('renderManuscriptWorkSurface(live, part'),
  'Picture, Detail and Audit use the real workbench while Summary retains orientation');

(async () => {
  const browser = await chromium.launch(chrome ? { executablePath: chrome } : {});
  try {
    for (const width of [1536, 768, 375]) {
      const page = await browser.newPage({ viewport: { width, height: 1000 }, reducedMotion: 'reduce' });
      const errors = [];
      page.on('pageerror', (error) => errors.push(String(error)));
      await page.setContent(`<style>${pageStyle}</style><main id="mount"></main>`);
      const result = await page.evaluate(async ({ source, model }) => {
        const url = URL.createObjectURL(new Blob([source], { type: 'text/javascript' }));
        const module = await import(url);
        const events = [];
        const requests = [];
        module.renderManuscriptWorkSurface(document.getElementById('mount'), model, {
          selection: { lens: 'work', focus: 'work:manuscript:section:two-descriptions', grade: 'mid', exposition: 'E1', edge: null },
          move: (patch) => events.push(patch),
          request: async (request) => { requests.push(request); return { ok: true, message: 'Fixture request accepted' }; },
          requestState: { status: 'CURRENT' },
        });
        const bodyWidth = document.documentElement.scrollWidth;
        const viewportWidth = document.documentElement.clientWidth;
        const selected = document.querySelector('.manuscript-work__section[aria-current=true]');
        const block = document.querySelector('[data-semantic-anchor="work:manuscript:block:main#argument"]');
        const pdf = document.querySelector('[data-semantic-anchor="work:manuscript:posture:pdf"]');
        const stage = document.querySelector('[data-semantic-anchor="work:pipeline:stage:convergence"]');
        block.click();
        pdf.click();
        stage.focus();
        stage.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
        stage.click();
        return {
          bodyWidth, viewportWidth,
          selected: selected?.dataset.semanticAnchor,
          blocks: document.querySelectorAll('.manuscript-work__block').length,
          sections: document.querySelectorAll('.manuscript-work__section').length,
          stages: document.querySelectorAll('.manuscript-work__stage').length,
          mechanisms: document.querySelectorAll('.manuscript-work__mechanism').length,
          launchChoices: document.querySelectorAll('.manuscript-work__launch-choice').length,
          versionRows: document.querySelectorAll('.manuscript-work__version').length,
          editorDisabled: document.querySelector('.manuscript-work__editor')?.disabled,
          editorWidth: document.querySelector('.manuscript-work__editor')?.getBoundingClientRect().width || 0,
          minControl: Math.min(...[...document.querySelectorAll('button,a')].map((item) => item.getBoundingClientRect().height)),
          blockWidth: document.querySelector('.manuscript-work__block-copy')?.getBoundingClientRect().width || 0,
          canvasWidth: document.querySelector('.manuscript-work__canvas')?.getBoundingClientRect().width || 0,
          text: document.body.innerText,
          events,
          requests,
          unknownAuthority: document.querySelectorAll('.manuscript-work__authority[data-state="UNKNOWN"]').length,
          fieldDisplay: getComputedStyle(document.querySelector('.manuscript-work__field')).display,
          releaseDisplay: getComputedStyle(document.querySelector('.manuscript-work__release')).display,
          hashAtRest: /(?:sha256:|message:)[0-9a-f]{16,}/i.test(document.body.innerText),
        };
      }, { source: moduleSource, model: fixture });

      ok(errors.length === 0, `${width}: renderer raises no browser error`);
      ok(result.bodyWidth <= result.viewportWidth, `${width}: no page-level horizontal overflow`);
      ok(result.selected === 'work:manuscript:section:two-descriptions', `${width}: exact section focus expands in place`);
      ok(result.blocks === 3 && result.sections === 3, `${width}: attended section expands while the full spine remains`);
      ok(result.stages === 10 && result.mechanisms === 6, `${width}: release journey and mechanism continuations remain visible`);
      ok(result.launchChoices === 2 && result.versionRows === 3, `${width}: governed launch and version trajectory remain legible`);
      ok(result.editorDisabled === false && result.editorWidth >= Math.min(290, result.viewportWidth - 32), `${width}: exact source editor is usable without a scaled-away canvas`);
      ok(result.minControl >= 44, `${width}: every control is at least 44px`);
      ok(result.blockWidth >= Math.min(220, result.canvasWidth * .72), `${width}: manuscript prose owns readable canvas width`);
      ok(!result.hashAtRest, `${width}: no exact handle wallpaper at rest`);
      ok(result.text.includes('Typeset') && result.text.includes('Findings') && result.text.includes('Live redline'), `${width}: source, geometry, findings and redline are one working field`);
      ok(result.text.includes('Save new version') && result.text.includes('Restore as new save') && result.text.includes('Model-heavy acts bank a work order'), `${width}: save, restore and model-heavy posture are human-explicit`);
      ok(result.unknownAuthority === 2 && result.text.includes('Not an endpoint precondition'), `${width}: missing stronger authority remains visible but nonblocking`);
      ok(result.requests.length === 0, `${width}: rendering and navigation cause no request`);
      ok(result.events.some((event) => event.focus === 'work:manuscript:block:main#argument' && event.grade === 'near'), `${width}: block descent uses the carrier selection contract`);
      ok(result.events.some((event) => event.focus === 'work:manuscript:posture:pdf'), `${width}: source-to-PDF posture is reversible URL selection`);
      ok(result.events.some((event) => event.focus === 'work:pipeline:stage:convergence'), `${width}: keyboard-reachable release-stage descent emits exact focus`);
      if (width === 375) {
        ok(result.fieldDisplay === 'block' && result.releaseDisplay === 'block', '375: the workbench reflows to a manuscript corridor rather than scaling a wide board');
      } else {
        ok(result.fieldDisplay === 'grid', `${width}: source, canvas and margin use the available field`);
      }
      await page.screenshot({ path: path.join(shots, `manuscript-work-${width}.png`), fullPage: true });
      await page.close();
    }

    const actionPage = await browser.newPage({ viewport: { width: 1024, height: 1000 }, reducedMotion: 'reduce' });
    await actionPage.setContent(`<style>${pageStyle}</style><main id="mount"></main>`);
    const actionResult = await actionPage.evaluate(async ({ source, model }) => {
      const url = URL.createObjectURL(new Blob([source], { type: 'text/javascript' }));
      const module = await import(url);
      const requests = [];
      let sourceSaves = 0;
      const gateway = async (request) => {
        requests.push(JSON.parse(JSON.stringify(request)));
        if (request.route === '/projection/tex' && ++sourceSaves === 3) throw Error('409 fixture stale source');
        return { ok: true, source_committed:true, selection_identity:'sha256:'+'e'.repeat(64), file:'paper/main.tex', restored_from:request.body?.version_id, consumed_source_digest:request.query.expected_source_digest || request.body?.expected_source_digest, expected_source_digest:'sha256:'+(sourceSaves===1?'b':'c').repeat(64), message: `accepted ${request.route}` };
      };
      module.renderManuscriptWorkSurface(document.getElementById('mount'), model, {
        selection: { lens: 'work', focus: 'work:manuscript:block:main#argument', grade: 'near', exposition: 'E2', edge: null },
        move: () => {},
        request: gateway,
        requestState: { status: 'CURRENT' },
      });
      const tick = () => new Promise((resolve) => setTimeout(resolve, 0));
      const editor = document.querySelector('.manuscript-work__editor');
      editor.value += '% exact local fixture edit\n';
      document.querySelector('[data-semantic-anchor="work:manuscript:action:save"]').click();
      await tick();
      editor.value += '% second exact fixture edit\n';
      document.querySelector('[data-semantic-anchor="work:manuscript:action:save"]').click();
      await tick();
      editor.value += '% retained after refusal\n';
      const heldText = editor.value;
      document.querySelector('[data-semantic-anchor="work:manuscript:action:save"]').click();
      await tick();
      const refusedDraftRetained = editor.value === heldText;
      document.querySelector('[data-semantic-anchor="work:manuscript:action:compile"]').click();
      await tick();
      document.querySelector('[data-semantic-anchor="work:manuscript:action:synctex"]').click();
      await tick();
      document.querySelector('[data-semantic-anchor="work:manuscript:action:follow"]').click();
      await tick();
      document.querySelector('[data-semantic-anchor="work:manuscript:action:redline"]').click();
      await tick();

      const from = document.querySelectorAll('.manuscript-work__selector select')[0];
      from.value = 'editor-v1';
      from.dispatchEvent(new Event('change', { bubbles: true }));
      const restore = document.querySelector('[data-semantic-anchor="work:manuscript:action:restore"]');
      restore.click();
      const restoreArmedWithoutRequest = requests.filter((request) => request.route === '/projection/restore').length === 0;
      restore.click();
      await tick();

      const localChoice = document.querySelector('.manuscript-work__launch-choice[data-semantic-anchor="work:pipeline:launch:storyboard-rebuild"]');
      localChoice.click();
      let confirm = document.querySelector('[data-semantic-anchor="work:pipeline:launch:storyboard-rebuild:confirm"]');
      confirm.click();
      const localArmedWithoutRequest = requests.filter((request) => request.route === '/storyboard/run/launch').length === 0;
      confirm = document.querySelector('[data-semantic-anchor="work:pipeline:launch:storyboard-rebuild:confirm"]');
      confirm.click();
      await tick();

      document.querySelector('.manuscript-work__launch-choice[data-semantic-anchor="work:pipeline:launch:re-projection"]').click();
      confirm = document.querySelector('[data-semantic-anchor="work:pipeline:launch:re-projection:confirm"]');
      const heavyWords = confirm.closest('.manuscript-work__launch-detail').innerText;
      const heavyCost = document.querySelector('.manuscript-work__launch-choice[data-semantic-anchor="work:pipeline:launch:re-projection"]').dataset.cost;
      const heavyConfirm = confirm.innerText;
      confirm.click();
      const heavyArmedWithoutRequest = requests.filter((request) => request.route === '/storyboard/run/launch').length === 1;
      confirm = document.querySelector('[data-semantic-anchor="work:pipeline:launch:re-projection:confirm"]');
      confirm.click();
      await tick();
      return {
        requests,
        refusedDraftRetained,
        restoreArmedWithoutRequest,
        localArmedWithoutRequest,
        heavyArmedWithoutRequest,
        heavyWords,
        heavyCost,
        heavyConfirm,
        status: document.querySelector('.manuscript-work__act-state[role=status]')?.innerText || '',
      };
    }, { source: moduleSource, model: fixture });
    const requestAt = (route, ordinal = 0) => actionResult.requests.filter((request) => request.route === route)[ordinal];
    ok(requestAt('/projection/tex').query.expected_source_digest === 'sha256:'+'a'.repeat(64)
      && requestAt('/projection/tex',1).query.expected_source_digest === 'sha256:'+'b'.repeat(64)
      && requestAt('/projection/tex',2).query.expected_source_digest === 'sha256:'+'c'.repeat(64),
      'successive saves use only their exact acknowledged physical basis');
    ok(actionResult.refusedDraftRetained && requestAt('/projection/restore').body.expected_source_digest === 'sha256:'+'c'.repeat(64),
      'failed save retains draft and leaves the latest acknowledged basis unchanged');
    ok(actionResult.restoreArmedWithoutRequest, 'restore first press arms locally and performs no request');
    ok(actionResult.localArmedWithoutRequest, 'local-safe first press honours exact arming without a request');
    ok(actionResult.heavyArmedWithoutRequest, 'model-heavy first press honours exact arming without a duplicate action');
    ok(requestAt('/projection/tex').body.endsWith('% exact local fixture edit\n'), 'save sends exact edited bytes as the raw canonical body');
    ok(requestAt('/projection/tex').body_kind === 'raw-text' && requestAt('/projection/tex').query.bank === 'editor' && requestAt('/projection/tex').query.author === 'gerard', 'save retains editor banking, actor and raw-body contract');
    ok(requestAt('/projection/recompile').body.by === 'gerard' && requestAt('/projection/recompile').body.file === 'paper/main.tex', 'compile carries exact file and actor');
    ok(requestAt('/projection/locate').query.line === 66 && requestAt('/projection/locate').query.section === 'two-descriptions', 'SyncTeX descends from the selected exact source span');
    ok(requestAt('/projection/follow').method === 'GET', 'PDF freshness remains a read-only canonical request');
    ok(requestAt('/review/compare').query.a === 'git-base' && requestAt('/review/compare').query.b === 'editor-v2', 'redline compares two exact banked state identifiers');
    ok(requestAt('/projection/restore').body.version_id === 'editor-v1', 'restore targets only the explicitly selected restorable editor save');
    ok(requestAt('/storyboard/run/launch', 0).body.action === 'storyboard-rebuild' && requestAt('/storyboard/run/launch', 0).body.armed === true, 'local-safe launch carries exact action and armed preflight');
    ok(requestAt('/storyboard/run/launch', 1).body.action === 're-projection' && requestAt('/storyboard/run/launch', 1).body.profile === 'profiles/paper.json', 'model-heavy launch carries exact action and profile');
    ok(actionResult.heavyConfirm.includes('Bank work order'), 'model-heavy preview names the banked work-order act');
    ok(actionResult.heavyCost === 'model-heavy', 'model-heavy preview carries the exact cost class');
    ok(actionResult.heavyWords.toLowerCase().includes('staged'), 'model-heavy preview names the owning pipeline organ');
    await actionPage.close();

    const fencePage = await browser.newPage({
      viewport: { width: 375, height: 900 }, colorScheme: 'dark', reducedMotion: 'reduce',
    });
    await fencePage.setContent(`<style>${pageStyle}html{filter:grayscale(1)}</style><main id="mount"></main>`);
    await fencePage.evaluate(async ({ source, model }) => {
      const url = URL.createObjectURL(new Blob([source], { type: 'text/javascript' }));
      const module = await import(url);
      window.__fencedRequests = [];
      module.renderManuscriptWorkSurface(document.getElementById('mount'), model, {
        selection: { lens: 'work', focus: 'work:manuscript:block:main#argument', grade: 'near', exposition: 'E2', edge: null },
        move: () => {},
        request: async (request) => { window.__fencedRequests.push(request); return { ok: true }; },
        requestState: {
          status: 'STALE',
          refusal: 'CANONICAL_ADAPTER_NOT_CURRENT',
          reason: 'the shared request gateway does not match the served manuscript model',
        },
      });
      const from = document.querySelectorAll('.manuscript-work__selector select')[0];
      from.value = 'editor-v1';
      from.dispatchEvent(new Event('change', { bubbles: true }));
    }, { source: moduleSource, model: fixture });
    const refusal = fencePage.locator('#manuscript-request-gateway-refusal');
    const refusalText = await refusal.innerText();
    const refusalRole = await refusal.getAttribute('role');
    ok(refusalRole === 'alert'
      && refusalText.toLowerCase().includes('writes refused')
      && refusalText.includes('CANONICAL_ADAPTER_NOT_CURRENT'),
    '375px manuscript refusal is visible in human words with the exact cause');
    const coreWrites = fencePage.locator('[data-write-control="true"]');
    ok(await coreWrites.count() === 5 && await coreWrites.evaluateAll((items) => items.every((item) => item.disabled)),
      '375px editor, save, compile, restore and selected launch are natively disabled');
    ok(await coreWrites.evaluateAll((items) => items.every((item) => item.getAttribute('aria-describedby') === 'manuscript-request-gateway-refusal')),
      '375px every disabled manuscript write control descends to the visible refusal');
    await coreWrites.evaluateAll((items) => items.forEach((item) => item.click()));
    await fencePage.locator('[data-semantic-anchor="work:pipeline:launch:re-projection"]').click();
    const heavyFence = fencePage.locator('[data-semantic-anchor="work:pipeline:launch:re-projection:confirm"]');
    ok(await heavyFence.isDisabled() && await heavyFence.getAttribute('aria-describedby') === 'manuscript-request-gateway-refusal',
      '375px model-heavy work-order banking is fenced by the same non-current gateway');
    await heavyFence.evaluate((button) => button.click());
    ok(await fencePage.evaluate(() => window.__fencedRequests.length) === 0,
      '375px scripted and armed manuscript writes cannot cross a stale gateway');
    let keyboardWriteLandings = 0;
    await fencePage.locator('body').focus();
    for (let index = 0; index < 24; index += 1) {
      await fencePage.keyboard.press('Tab');
      keyboardWriteLandings += await fencePage.evaluate(() =>
        document.activeElement?.hasAttribute('data-write-control') ? 1 : 0);
    }
    ok(keyboardWriteLandings === 0, '375px keyboard traversal skips every disabled manuscript write');
    ok(await fencePage.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches),
      '375px manuscript refusal preserves reduced motion');
    ok((await fencePage.evaluate(() => getComputedStyle(document.documentElement).filter)).includes('grayscale'),
      '375px manuscript refusal remains legible in grayscale');
    ok(await fencePage.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      '375px manuscript refusal preserves the narrow corridor');
    ok(await fencePage.locator('button:not(:disabled),a').evaluateAll((items) =>
      items.every((item) => item.getBoundingClientRect().height >= 44)),
    '375px remaining navigational and read-only controls stay at least 44px');
    await fencePage.close();

    const page = await browser.newPage({ viewport: { width: 768, height: 900 }, colorScheme: 'dark', reducedMotion: 'reduce' });
    await page.setContent(`<style>${pageStyle}html{filter:grayscale(1)}</style><main id="mount"></main>`);
    const grayscale = await page.evaluate(async ({ source, model }) => {
      const url = URL.createObjectURL(new Blob([source], { type: 'text/javascript' }));
      const module = await import(url);
      module.renderManuscriptWorkSurface(document.getElementById('mount'), model, {
        selection: { lens: 'work', focus: 'work:manuscript:posture:pdf', grade: 'near', exposition: 'E2', edge: null },
        move: () => {},
      });
      return {
        stateWords: [...document.querySelectorAll('[data-state]')].map((item) => item.dataset.state),
        text: document.body.innerText,
        unknown: document.querySelector('.manuscript-work__unknown')?.innerText || '',
      };
    }, { source: moduleSource, model: fixture });
    ok(grayscale.stateWords.includes('UNKNOWN') && grayscale.unknown.includes('has not joined'),
      'grayscale: state remains explicit in words and geometry, not colour alone');
    ok(grayscale.text.includes('Inspect the missing PDF evidence'),
      'typeset posture refuses honestly with the exact continuation instead of a fake canvas');
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
