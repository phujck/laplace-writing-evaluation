// Focused browser contract for the deterministic Programme Causal Atlas Weave.
import { createRequire } from 'module';
import { execFileSync, execSync } from 'child_process';
import { existsSync, readFileSync } from 'fs';
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
const modulePath = path.join(repo, 'src/laplace/web/static_shared/causal_atlas_weave.mjs');
const moduleSource = readFileSync(modulePath, 'utf8');
let passed = 0;
function ok(value, label) { if (!value) throw new Error(`ASSERT FAILED: ${label}`); passed += 1; console.log('  ok -', label); }

const objects = [
  { object_handle: 'source:current', kind: 'source', family: 'programme', label: 'Current Eigen work', state: 'CURRENT', summary: '2 open · 8 recent proofs', continuation: '/front/development?lens=lens-self', receipt_ids: ['sha256:source'] },
  { object_handle: 'message:work', kind: 'work', family: 'programme', label: 'Visual rescue', state: 'OPEN', summary: 'Needs perception', continuation: '/front/development?lens=evidence-descent', receipt_ids: ['message:work'] },
  { object_handle: 'group:conversation', kind: 'compressed-group', family: 'continuity', label: 'Conversation flow', state: 'COMPLETE', summary: '5 conserved · COMPLETE', member_count: 5, ordered_member_handles: ['turn','sent','pull','reconstruct','ack'], member_digest: 'sha256:members', boundary_member: 'turn', continuation: { focus_handle: 'turn', grade: 'near' }, receipt_ids: [] },
  { object_handle: 'authority:sensorium', kind: 'authority', family: 'authority', label: 'Aisthesis authority', state: 'BOUND', summary: 'routing authority', continuation: '/front/development?lens=live-custody', receipt_ids: ['sha256:binding'] },
  { object_handle: 'residual:omission', kind: 'residual', family: 'residual', label: 'Conserved omissions', state: 'PRESENT', summary: '3 omitted with continuation', continuation: '/front/development?lens=residual-crutch', receipt_ids: ['sha256:omission'] },
];
const edges = objects.slice(1).map((object, index) => ({
  edge_id: `edge:${index}`, source_handle: 'source:current', target_handle: object.object_handle,
  relation: ['admits','compresses with exact continuation','is governed by','conserves'][index], state: index === 3 ? 'UNKNOWN' : 'COMPLETE',
}));
const objectGeometry = objects.map((object, index) => ({ object_handle: object.object_handle, x: 40 + (index % 2) * 260, y: 36 + Math.floor(index / 2) * 150, width: 220, height: index === 0 ? 112 : 76 }));
const centres = Object.fromEntries(objectGeometry.map((row) => [row.object_handle, [row.x + row.width / 2, row.y + row.height / 2]]));
const edgeGeometry = edges.map((edge, index) => ({ edge_id: edge.edge_id, points: [centres[edge.source_handle], centres[edge.target_handle]].map((point) => point.map(Math.round)), label_x: 300, label_y: 120 + index * 55 }));
const fixture = {
  schema_version: 'laplace.aisthesis-causal-atlas-weave/1', state: 'CURRENT', grade: 'mid', viewport: 'medium',
  focus_handle: 'source:current', selected_edge_id: null, objects, edges, compressed_groups: [objects[2]],
  omitted_object_handles: objects[2].ordered_member_handles, canonical_order: ['source:current','message:work',...objects[2].ordered_member_handles,'authority:sensorium','residual:omission'],
  layout: { width: 620, height: 520, objects: objectGeometry, edges: edgeGeometry }, layout_receipt_handle: 'sha256:layout', selected_audit_subject: null, read_only: true,
};

const served = execFileSync('/usr/bin/python3', ['-c', [
  'from laplace.web import front_door',
  'status, ctype, body = front_door.handle("/front/development/causal_atlas_weave.mjs", {}, "GET", b"")',
  'assert status == 200',
  'assert ctype == "text/javascript; charset=utf-8"',
  'assert b"renderCausalAtlasWeave" in body',
  'print(len(body))',
].join(';')], { cwd: repo, env: { ...process.env, PYTHONPATH: `${repo}/src` } }).toString().trim();
ok(Number(served) === Buffer.byteLength(moduleSource), 'front door serves the exact renderer module');
ok(!/\bfetch\s*\(|XMLHttpRequest|WebSocket|localStorage|sessionStorage|history\./.test(moduleSource), 'renderer owns no fetch, browser truth or history');
ok(!/#[0-9a-fA-F]{3,8}\b|\b(?:rgb|hsl)a?\s*\(/.test(moduleSource), 'renderer contains no private palette');

(async () => {
  const browser = await chromium.launch(chrome ? { executablePath: chrome } : {});
  try {
    for (const width of [1536, 768, 375]) {
      const page = await browser.newPage({ viewport: { width, height: 900 }, reducedMotion: 'reduce' });
      await page.setContent('<style>html,body{margin:0;background:#10131a;color:#eee;font:16px system-ui}#mount{max-width:1180px}.causal-weave__field{position:relative;overflow:hidden}.causal-weave__threads{position:absolute}.causal-weave__object,.causal-weave__edge-hit{position:absolute;min-height:44px}.causal-weave__object span,.causal-weave__object strong{display:block}.causal-weave__thread{fill:none;stroke:#999}.causal-weave__toolbar{display:flex}.causal-weave__context{padding:10px}</style><main id="mount"></main>');
      const result = await page.evaluate(async ({ source, fixtureValue }) => {
        const url = URL.createObjectURL(new Blob([source], { type: 'text/javascript' }));
        const module = await import(url);
        const events = [];
        module.renderCausalAtlasWeave(document.getElementById('mount'), fixtureValue, {
          onObject: (event) => events.push(['object', event.handle]),
          onGroup: (event) => events.push(['group', event.group.boundary_member]),
          onGrade: (event) => events.push(['grade', event.grade]),
          onBack: () => events.push(['back']),
        });
        document.querySelector('[data-object="message:work"]').click();
        document.querySelector('[data-object="group:conversation"]').click();
        document.querySelector('[data-grade="near"]').click();
        return {
          objects: document.querySelectorAll('.causal-weave__object').length,
          anchors: [...document.querySelectorAll('[data-semantic-anchor]')].map((row) => row.dataset.semanticAnchor),
          minHeights: [...document.querySelectorAll('button')].map((row) => row.getBoundingClientRect().height),
          text: document.body.innerText,
          receiptVisible: document.body.innerText.includes('sha256:source'),
          events,
          state: document.querySelector('.causal-weave').dataset.state,
        };
      }, { source: moduleSource, fixtureValue: fixture });
      ok(result.objects === objects.length, `${width}: every supplied visible object renders exactly once`);
      ok(result.anchors.includes('message:work') && result.anchors.includes('edge:0'), `${width}: object and edge carry stable semantic anchors`);
      ok(result.minHeights.every((height) => height >= 44), `${width}: every interactive control is at least 44px`);
      ok(!result.receiptVisible, `${width}: exact receipt identifiers stay out of resting Mid`);
      ok(result.state === 'CURRENT', `${width}: currentness remains visible`);
      ok(JSON.stringify(result.events) === JSON.stringify([['object','message:work'],['group','turn'],['grade','near']]), `${width}: focus, group continuation and semantic zoom emit exact events`);
      await page.close();
    }

    const page = await browser.newPage({ viewport: { width: 768, height: 900 } });
    const forged = await page.evaluate(async ({ source, fixtureValue }) => {
      const url = URL.createObjectURL(new Blob([source], { type: 'text/javascript' }));
      const module = await import(url);
      const copy = structuredClone(fixtureValue);
      copy.layout.objects[0].object_handle = 'forged:object';
      module.renderCausalAtlasWeave(document.body, copy);
      return { state: document.querySelector('.causal-weave').dataset.state, text: document.body.innerText };
    }, { source: moduleSource, fixtureValue: fixture });
    ok(forged.state === 'REFUSED' && forged.text.includes('geometry does not match'), 'forged producer geometry refuses before rendering a field');
    await page.close();
  } finally { await browser.close(); }
  console.log(`PASS ${passed}/${passed}`);
})().catch((error) => { console.error(error); process.exitCode = 1; });
