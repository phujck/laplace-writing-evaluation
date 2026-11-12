// Standalone acceptance for the deterministic Continuity Loom renderer.
// Run: node tests/continuity_loom.playwright.mjs
import { createRequire } from 'module';
import { execFileSync, execSync } from 'child_process';
import { existsSync, readFileSync } from 'fs';
import { createHash } from 'crypto';
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
const modulePath = path.join(repo, 'src/laplace/web/static_shared/continuity_loom.mjs');
const moduleSource = readFileSync(modulePath, 'utf8');
let passed = 0;

function ok(condition, message) {
  if (!condition) throw new Error('ASSERT FAILED: ' + message);
  passed += 1;
  console.log('  ok -', message);
}

function stableJSON(value) {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableJSON).join(',')}]`;
  return `{${Object.keys(value).toSorted().map((key) =>
    `${JSON.stringify(key)}:${stableJSON(value[key])}`).join(',')}}`;
}

const digest = (value) => `sha256:${createHash('sha256').update(stableJSON(value)).digest('hex')}`;

function exposition(label) {
  return Array.from({ length: 8 }, (_, grade) => ({
    grade,
    state: 'AVAILABLE',
    claim: grade === 7 ? `${label} safe specimen; no production effect.` : `${label} exposition E${grade}.`,
    authority: grade === 7 ? 'ZERO' : 'READ_ONLY',
    source_references: [`receipt:${label.toLowerCase().replaceAll(' ', '-')}:e${grade}`],
    descend: { label: 'Descend to exact source', reference: `source:${label.toLowerCase().replaceAll(' ', '-')}` },
  }));
}

const objects = [
  { object_handle: 'turn:author', kind: 'author-turn', label: 'Gerard asks for review', state: 'BANKED', receipt_ids: ['receipt:turn'], exposition: exposition('Author turn') },
  { object_handle: 'event:sent', kind: 'receipt', label: 'Review sent', state: 'ROUTED', receipt_ids: ['receipt:sent'], exposition: exposition('Sent event') },
  { object_handle: 'seat:reviewer', kind: 'logical-seat', label: 'Review seat', state: 'OCCUPIED', receipt_ids: ['receipt:lease-generation-7'], exposition: exposition('Review seat') },
  { object_handle: 'event:pull', kind: 'receipt', label: 'Review received', state: 'RECEIVED', receipt_ids: ['receipt:pull'], exposition: exposition('Pull event') },
  { object_handle: 'proof:reconstruction', kind: 'receipt', label: 'Review reconstructed', state: 'RECONSTRUCTED', receipt_ids: ['receipt:reconstruction'], exposition: exposition('Reconstruction') },
  { object_handle: 'boundary:moved', kind: 'receipt', label: 'Candidate moved', state: 'LAST-TRUSTED', receipt_ids: ['receipt:currentness-mismatch'], exposition: exposition('Moved boundary') },
  { object_handle: 'bundle:quiet-context', group_handle: 'bundle:quiet-context', kind: 'compressed-group', label: 'Earlier completed context', state: 'BUDGET', member_count: 3, member_digest: 'sha256:compressed-members', ordered_member_handles: ['hidden:1','hidden:2','hidden:3'], boundary_member: 'hidden:3', exceptional_states: [], continuation: { focus_handle: 'hidden:3', grade: 'near' }, receipt_ids: [], exposition: exposition('Compressed context') },
];
objects.at(-1).member_digest = digest(objects.at(-1).ordered_member_handles);

const edges = [
  ['edge:turn-sent', 'turn:author', 'event:sent', 'sent as', 'receipt:sent'],
  ['edge:sent-seat', 'event:sent', 'seat:reviewer', 'routed to', 'receipt:route'],
  ['edge:seat-pull', 'seat:reviewer', 'event:pull', 'received as', 'receipt:pull'],
  ['edge:pull-recon', 'event:pull', 'proof:reconstruction', 'reconstructed as', 'receipt:reconstruction'],
  ['edge:recon-break', 'proof:reconstruction', 'boundary:moved', 'refused at', 'receipt:currentness-mismatch'],
  ['edge:context-turn', 'bundle:quiet-context', 'turn:author', 'precedes', 'receipt:context'],
].map(([edge_id, source_handle, target_handle, label, receipt]) => ({
  edge_id, source_handle, target_handle, label, relation: label, state: edge_id === 'edge:recon-break' ? 'REFUSED' : 'COMPLETE', receipt_ids: [receipt],
}));
const cutEdge = edges.at(-1);
cutEdge.kind = 'cut-edge';
cutEdge.ordered_member_edge_ids = ['hidden-edge:1'];
cutEdge.member_digest = digest(cutEdge.ordered_member_edge_ids);

function geometry(width, height, coordinates) {
  const sizes = Object.fromEntries(objects.map((object) => [object.object_handle,
    width === 720
      ? (object.kind === 'compressed-group' ? [300, 80] : [300, 72])
      : (object.kind === 'compressed-group' ? [170, 54] : [150, 56])]));
  const objectRows = objects.map((object) => {
    const [x, y] = coordinates[object.object_handle];
    const [w, h] = sizes[object.object_handle];
    return { object_handle: object.object_handle, x, y, width: w, height: h,
      compressed: object.kind === 'compressed-group' };
  });
  const centres = Object.fromEntries(objectRows.map((row) => [row.object_handle,
    [row.x + Math.floor(row.width / 2), row.y + Math.floor(row.height / 2)]]));
  const edgeRows = edges.map((edge, ordinal) => {
    const a = centres[edge.source_handle];
    const b = centres[edge.target_handle];
    return {
      edge_id: edge.edge_id,
      points: [a, b],
      control_x: width <= 350 ? 272 : (width === 720 ? 372 : Math.floor((a[0] + b[0]) / 2) - 34),
      control_y: width <= 350 ? 16 + ordinal * 52 : (width === 720 ? 18 + ordinal * 60 : Math.floor((a[1] + b[1]) / 2) - 22),
      control_width: width <= 350 ? 70 : (width === 720 ? 324 : 68),
      control_height: width === 720 ? 48 : 44,
      label_slot: true,
    };
  });
  return { width, height, objects: objectRows, edges: edgeRows };
}

const geometries = {
  wide: geometry(1440, 620, {
    'bundle:quiet-context': [24, 500], 'turn:author': [90, 55], 'event:sent': [300, 170],
    'seat:reviewer': [510, 280], 'event:pull': [720, 280], 'proof:reconstruction': [930, 280],
    'boundary:moved': [1160, 280],
  }),
  medium: geometry(720, 880, {
    'bundle:quiet-context': [24, 700], 'turn:author': [24, 28], 'event:sent': [24, 140],
    'seat:reviewer': [24, 252], 'event:pull': [24, 364], 'proof:reconstruction': [24, 476],
    'boundary:moved': [24, 588],
  }),
  narrow: geometry(350, 940, {
    'bundle:quiet-context': [90, 820], 'turn:author': [100, 25], 'event:sent': [100, 145],
    'seat:reviewer': [100, 265], 'event:pull': [100, 385], 'proof:reconstruction': [100, 505],
    'boundary:moved': [100, 625],
  }),
};
const compression = {
  schema_version: 'laplace.aisthesis-continuity-compression/1',
  canonical_order: ['hidden:1','hidden:2','hidden:3', ...objects.filter((object) => object.kind !== 'compressed-group').map((object) => object.object_handle)],
  visible_original_handles: objects.filter((object) => object.kind !== 'compressed-group').map((object) => object.object_handle),
  groups: [{ group_handle: 'bundle:quiet-context', ordered_member_handles: ['hidden:1','hidden:2','hidden:3'], member_digest: objects.at(-1).member_digest, boundary_member: 'hidden:3', exceptional_states: [] }],
  cut_edges: [{ edge_id: cutEdge.edge_id, ordered_member_edge_ids: cutEdge.ordered_member_edge_ids, member_digest: cutEdge.member_digest }],
};
compression.compression_receipt_handle = digest(compression);

function layoutReceipt(selected, focus = 'turn:author', edge = null) {
  const selectedAuditSubject = edge ? `edge:${edge}` : `object:${focus}`;
  const selectedGeometry = geometries[selected];
  const preimage = {
    schema_version: 'laplace.aisthesis-continuity-layout/1',
    version: 'fixture-v2',
    options: {
      selected_viewport: selected,
      selected_audit_subject: selectedAuditSubject,
      compression_receipt_handle: compression.compression_receipt_handle,
    },
    canonical_order: compression.canonical_order,
    compression: Object.fromEntries(Object.entries(compression).filter(([key]) => key !== 'compression_receipt_handle')),
    display_edges: edges,
    geometry: geometries,
    node_geometry: selectedGeometry.objects,
    endpoint_geometry: selectedGeometry.edges.map((row) => ({
      edge_id: row.edge_id,
      source: { x: row.points[0][0], y: row.points[0][1] },
      target: { x: row.points.at(-1)[0], y: row.points.at(-1)[1] },
    })),
  };
  return { ...preimage, layout_receipt_handle: digest(preimage) };
}

const loom = {
  schema_version: 'laplace.aisthesis-continuity-loom/1',
  state: 'CURRENT',
  currentness: { state: 'CURRENT', shown_handle: 'sha256:shown' },
  selected_viewport: 'medium',
  focus_handle: 'turn:author',
  selected_edge_id: null,
  selected_audit_subject: 'object:turn:author',
  objects,
  edges,
  ordered_visible_handles: objects.map((object) => object.object_handle),
  compression,
  layout_receipt: layoutReceipt('medium'),
  layout_receipt_handle: layoutReceipt('medium').layout_receipt_handle,
  geometry: geometries,
  omission_residual: [{
    class: 'BODIES-OMITTED', state: 'BUDGET', count: 2,
    label: 'Message bodies remain exact descent', digest: 'sha256:omitted-bodies',
    continuation: { reference: 'source:message-bodies' },
  }],
};

const style = `
  html,body{margin:0;background:#0a0e1a;color:#e8e6e3;font:16px system-ui}
  #mount{width:100%}.continuity-loom{position:relative}.continuity-loom__header,.continuity-loom__grades,.continuity-loom__exposition{display:flex;gap:8px;flex-wrap:wrap;padding:8px}
  button{min-height:28px;background:#18202f;color:#e8e6e3;border:1px solid #2d3547}
  button[aria-pressed=true]{outline:2px solid #c9a96e}.continuity-loom__field{position:relative;border-block:1px solid #2d3547;overflow:hidden}
  .continuity-loom__weft{position:absolute;inset:0}.continuity-loom__edge-path{fill:none;stroke:#9ca3af;stroke-width:2}.continuity-loom__edge-path[data-state=REFUSED]{stroke-dasharray:7 5}
  .continuity-loom__object,.continuity-loom__edge{overflow:hidden}.continuity-loom__object-label,.continuity-loom__object-state,.continuity-loom__compression,.continuity-loom__receipt{display:block}
  .continuity-loom__context,.continuity-loom__omissions{padding:12px;border-top:1px solid #2d3547}.continuity-loom__currentness,.continuity-loom__object-state{font-family:monospace}
  @media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;animation:none!important;transition:none!important}}
`;

// Exact shared-serving assertion without starting a scanner or service.
const serveProof = execFileSync('/usr/bin/python3', ['-c', [
  'from laplace.web import shared_ui',
  'status, ctype, body = shared_ui.handle("/shared/continuity_loom.mjs", {})',
  'assert status == 200',
  'assert ctype == "text/javascript; charset=utf-8"',
  'assert b"renderContinuityLoom" in body',
  'print(len(body))',
].join(';')], {
  cwd: repo,
  env: { ...process.env, PYTHONPATH: `${repo}/src` },
}).toString().trim();
ok(Number(serveProof) === Buffer.byteLength(moduleSource), 'the exact allowlisted module is served as ESM');
ok(!/\bfetch\s*\(|XMLHttpRequest|WebSocket|localStorage|sessionStorage|history\.|\.sort\s*\(/.test(moduleSource),
  'renderer contains no fetch, shadow store, history owner or topology sort');
ok(!/#[0-9a-fA-F]{3,8}\b|\b(?:rgb|hsl)a?\s*\(/.test(moduleSource), 'renderer restates no palette');

(async () => {
  const browser = await chromium.launch(chrome ? { executablePath: chrome } : {});
  try {
    for (const [viewportWidth, expectedGeometry] of [[1536, 'wide'], [768, 'medium'], [375, 'narrow']]) {
      const page = await browser.newPage({ viewport: { width: viewportWidth, height: 1100 }, reducedMotion: 'reduce' });
      const errors = [];
      page.on('pageerror', (error) => errors.push(String(error)));
      await page.setContent(`<style>${style}</style><main id="mount"></main>`);
      await page.evaluate(async ({ source, fixture, edgeFixture }) => {
        const url = URL.createObjectURL(new Blob([source], { type: 'text/javascript' }));
        const module = await import(url);
        const events = [];
        const mount = document.getElementById('mount');
        let controller;
        const options = {
          focusHandle: fixture.focus_handle,
          onObject: (event) => events.push(['object', event.handle]),
          onGroup: (event) => events.push(['group', event.group.boundary_member]),
          onEdge: (event) => events.push(['edge', event.edgeId]),
          onGrade: (event) => events.push(['grade', event.grade]),
          onExposition: (event) => events.push(['exposition', event.grade, event.objectHandle]),
          onDescend: (event) => events.push(['descend', event.reference]),
          onBack: () => events.push(['back']),
        };
        controller = module.renderContinuityLoom(mount, fixture, options);
        window.loomFixture = fixture;
        window.edgeFixture = edgeFixture;
        window.loomController = controller;
        window.loomEvents = events;
      }, {
        source: moduleSource,
        fixture: {
          ...loom,
          selected_viewport: expectedGeometry,
          layout_receipt: layoutReceipt(expectedGeometry),
          layout_receipt_handle: layoutReceipt(expectedGeometry).layout_receipt_handle,
        },
        edgeFixture: {
          ...loom,
          selected_viewport: expectedGeometry,
          focus_handle: 'boundary:moved',
          selected_edge_id: 'edge:recon-break',
          selected_audit_subject: 'edge:edge:recon-break',
          layout_receipt: layoutReceipt(expectedGeometry, 'boundary:moved', 'edge:recon-break'),
          layout_receipt_handle: layoutReceipt(expectedGeometry, 'boundary:moved', 'edge:recon-break').layout_receipt_handle,
        },
      });
      await page.waitForSelector('.continuity-loom');

      ok(await page.getAttribute('.continuity-loom', 'data-geometry') === expectedGeometry,
        `${viewportWidth}px selects only the supplied ${expectedGeometry} geometry`);
      ok(await page.$$eval('button.continuity-loom__object', (rows) => rows.length) === objects.length,
        `${viewportWidth}px retains every supplied object as a native control`);
      ok(await page.$$eval('button.continuity-loom__edge', (rows) => rows.length) === edges.length,
        `${viewportWidth}px retains every supplied edge as a native control`);
      ok(await page.$$eval('.continuity-loom__object,.continuity-loom__edge', (rows) => rows.every((row) => row.tagName === 'BUTTON' && row.getAttribute('aria-label'))),
        `${viewportWidth}px labels every visible object and edge control`);
      ok(await page.$$eval('.continuity-loom__receipt', (rows) => rows.length) === 0,
        `${viewportWidth}px resting Mid face exposes no receipt-id wallpaper`);
      ok(await page.getAttribute('.continuity-loom', 'data-reduced-motion') === 'true',
        `${viewportWidth}px exposes the reduced-motion contract`);
      ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
        `${viewportWidth}px has no horizontal overflow`);

      const before = await page.$eval('.continuity-loom__object[data-object="turn:author"]', (node) => ({ left: node.style.left, top: node.style.top }));
      await page.evaluate(() => window.loomController.update(window.loomFixture, {}));
      const after = await page.$eval('.continuity-loom__object[data-object="turn:author"]', (node) => ({ left: node.style.left, top: node.style.top }));
      ok(JSON.stringify(before) === JSON.stringify(after), `${viewportWidth}px repeated update maps integer anchors deterministically`);

      await page.$eval('#mount', (node) => { node.style.width = '320px'; });
      await page.waitForTimeout(50);
      ok(await page.getAttribute('.continuity-loom', 'data-geometry') === expectedGeometry,
        `${viewportWidth}px container resize cannot choose a different topology`);
      await page.$eval('#mount', (node) => { node.style.width = ''; });
      await page.waitForTimeout(50);

      await page.click('.continuity-loom__object[data-object="boundary:moved"]');
      ok(await page.getAttribute('.continuity-loom', 'data-focus') === 'boundary:moved',
        `${viewportWidth}px click expands exact object context in place`);
      ok(await page.$$eval('.continuity-loom__context', (rows) => rows.length) === 1,
        `${viewportWidth}px renders one object-relative context`);
      await page.click('.continuity-loom__edge[data-edge="edge:recon-break"]');
      ok(await page.getAttribute('.continuity-loom__edge[data-edge="edge:recon-break"]', 'aria-pressed') === 'true',
        `${viewportWidth}px selects an exact edge independently of focus`);

      await page.click('.continuity-loom__grade[data-grade="audit"]');
      ok((await page.$$eval('.continuity-loom__receipt', (rows) => rows.length)) === 0,
        `${viewportWidth}px Audit with an un-rederived selection exposes no identifier wallpaper`);
      await page.evaluate(() => {
        const next = structuredClone(window.edgeFixture);
        window.loomController.update(next, { focusHandle: 'boundary:moved', selectedEdgeId: 'edge:recon-break', grade: 'audit' });
      });
      ok((await page.$$eval('.continuity-loom__receipt', (rows) => rows.length)) > 0,
        `${viewportWidth}px selected Audit relation alone exposes exact identifiers`);
      ok(!(await page.textContent('.continuity-loom__omissions')).includes('sha256:omitted-bodies'),
        `${viewportWidth}px omission stays human-readable without digest wallpaper`);
      ok((await page.textContent('.continuity-loom__object[data-object="bundle:quiet-context"]')).includes('3 conserved'),
        `${viewportWidth}px compressed context keeps exact member count`);
      await page.click('.continuity-loom__object[data-object="bundle:quiet-context"]');
      ok((await page.evaluate(() => window.loomEvents)).some((event) => event[0] === 'group' && event[1] === 'hidden:3'),
        `${viewportWidth}px compressed group emits its exact boundary continuation`);

      await page.click('.continuity-loom__exposition-grade[data-exposition="7"]');
      ok(await page.getAttribute('.continuity-loom__exposition-copy', 'data-authority') === 'ZERO',
        `${viewportWidth}px E7 is an explicit zero-authority specimen`);
      await page.click('.continuity-loom__descend');
      await page.click('.continuity-loom__back');
      const eventKinds = await page.evaluate(() => window.loomEvents.map((event) => event[0]));
      ok(['object', 'edge', 'grade', 'exposition', 'descend', 'back'].every((kind) => eventKinds.includes(kind)),
        `${viewportWidth}px emits only the documented integration callbacks`);

      await page.focus('.continuity-loom__grade[data-grade="audit"]');
      await page.keyboard.press('Home');
      ok(await page.evaluate(() => document.activeElement?.dataset?.grade === 'far'),
        `${viewportWidth}px keyboard traverses grade controls`);
      await page.keyboard.press('Escape');
      ok((await page.evaluate(() => window.loomEvents.filter((event) => event[0] === 'back').length)) >= 2,
        `${viewportWidth}px Escape invokes reversible Back`);

      await page.evaluate(() => {
        const next = structuredClone(window.loomFixture);
        next.state = 'LAST-TRUSTED';
        next.currentness.state = 'LAST-TRUSTED';
        window.loomController.update(next, {});
        document.documentElement.style.filter = 'grayscale(1)';
      });
      ok(await page.getAttribute('.continuity-loom', 'data-state') === 'LAST-TRUSTED'
          && (await page.textContent('.continuity-loom__currentness')).includes('LAST-TRUSTED'),
        `${viewportWidth}px last-trusted truth survives without colour`);
      ok(errors.length === 0, `${viewportWidth}px has no browser errors (${JSON.stringify(errors)})`);
      await page.close();
    }

    const page = await browser.newPage({ viewport: { width: 768, height: 800 } });
    await page.setContent(`<style>${style}</style><main id="mount"></main>`);
    await page.evaluate(async ({ source, fixture }) => {
      const url = URL.createObjectURL(new Blob([source], { type: 'text/javascript' }));
      const { renderContinuityLoom } = await import(url);
      const broken = structuredClone(fixture);
      delete broken.geometry.medium;
      renderContinuityLoom(document.getElementById('mount'), broken);
    }, { source: moduleSource, fixture: loom });
    ok(await page.getAttribute('.continuity-loom', 'data-state') === 'UNKNOWN',
      'missing supplied geometry refuses UNKNOWN rather than inventing layout');
    ok((await page.textContent('.continuity-loom__currentness')).includes('supplied medium geometry is absent'),
      'geometry refusal names the exact missing boundary');
    await page.close();

    const forged = await browser.newPage({ viewport: { width: 768, height: 800 } });
    await forged.setContent(`<style>${style}</style><main id="mount"></main>`);
    await forged.evaluate(async ({ source, fixture }) => {
      const url = URL.createObjectURL(new Blob([source], { type: 'text/javascript' }));
      const { renderContinuityLoom } = await import(url);
      const broken = structuredClone(fixture);
      broken.objects.find((object) => object.kind === 'compressed-group').member_count = 2;
      renderContinuityLoom(document.getElementById('mount'), broken, { focusHandle: broken.focus_handle });
    }, { source: moduleSource, fixture: loom });
    ok(await forged.getAttribute('.continuity-loom', 'data-state') === 'UNKNOWN',
      'forged compressed membership refuses rather than rendering a false cut');
    await forged.close();

    const hostileCases = [
      { kind: 'geometry-coordinate', label: 'geometry coordinate moved outside its receipt' },
      { kind: 'geometry-row', label: 'visible object geometry row removed' },
      { kind: 'cut-membership', label: 'cut-edge membership and digest mirrored but unreceipted', digest: digest(['forged-edge:1']) },
      { kind: 'group-membership', label: 'group order, digest and boundary mirrored but unreceipted', digest: digest(['hidden:3','hidden:2','hidden:1']) },
    ];
    for (const hostile of hostileCases) {
      const page = await browser.newPage({ viewport: { width: 768, height: 800 } });
      await page.setContent(`<style>${style}</style><main id="mount"></main>`);
      await page.evaluate(async ({ source, fixture, hostileCase }) => {
        const url = URL.createObjectURL(new Blob([source], { type: 'text/javascript' }));
        const { renderContinuityLoom } = await import(url);
        const broken = structuredClone(fixture);
        if (hostileCase.kind === 'geometry-coordinate') {
          broken.geometry.medium.objects[0].x += 1;
        } else if (hostileCase.kind === 'geometry-row') {
          broken.geometry.medium.objects.pop();
        } else if (hostileCase.kind === 'cut-membership') {
          const edge = broken.edges.find((item) => item.kind === 'cut-edge');
          const cut = broken.compression.cut_edges[0];
          edge.ordered_member_edge_ids = ['forged-edge:1'];
          edge.member_digest = hostileCase.digest;
          cut.ordered_member_edge_ids = ['forged-edge:1'];
          cut.member_digest = hostileCase.digest;
        } else if (hostileCase.kind === 'group-membership') {
          const groupObject = broken.objects.find((item) => item.kind === 'compressed-group');
          const group = broken.compression.groups[0];
          const members = ['hidden:3','hidden:2','hidden:1'];
          groupObject.ordered_member_handles = members;
          groupObject.member_digest = hostileCase.digest;
          groupObject.boundary_member = 'hidden:1';
          group.ordered_member_handles = members;
          group.member_digest = hostileCase.digest;
          group.boundary_member = 'hidden:1';
        }
        renderContinuityLoom(document.getElementById('mount'), broken, { focusHandle: broken.focus_handle });
      }, { source: moduleSource, fixture: loom, hostileCase: hostile });
      ok(await page.getAttribute('.continuity-loom', 'data-state') === 'UNKNOWN',
        `${hostile.label} refuses UNKNOWN`);
      await page.close();
    }

    console.log(`\nALL GREEN — ${passed} assertions`);
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error('\n' + error.stack);
  process.exit(1);
});
