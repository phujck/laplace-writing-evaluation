// C12 REACHED REPAIR (2026-10-15): the two further Root actual holds.
// 1. Nested source identity: Open in TeX carries the block's exact repository path and source basis
//    (manuscript-editing blockSourceLocation); the bridge admits nothing less; there is no relative or basename fallback.
// 2. The passage menu fits the iframe viewport: contextMenuPlacement caps its height so every item stays reachable.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {blockSourceLocation} from '../src/laplace/web/static_shared/manuscript-editing.mjs';
import {contextMenuPlacement} from '../src/laplace/web/static_shared/workspace-presentation.mjs';
import {BRIDGE_ROUTES,createBridgeLedger,installWalkBridge} from '../src/laplace/web/static_shared/workspace-bridge.mjs';

const pin = letter => 'sha256:' + letter.repeat(64);
const walk = (blocks, observation = {selection_identity: pin('b'), file_revisions: Object.fromEntries(blocks.filter(b => b.repo_file).map(b => [b.repo_file, 'a'.repeat(64)]))}) =>
  ({blocks: () => blocks, sourceObservation: () => ({source_observation: observation})});

test('a block location is its exact repository path, line and basis; repeated basenames stay distinct', () => {
  const blocks = [{id: 'c#b3', file: 'chapters/intro.tex', repo_file: 'writing_projects/p/draft/chapters/intro.tex', line_start: 3},
                  {id: 'a#b1', file: 'appendix/intro.tex', repo_file: 'writing_projects/p/draft/appendix/intro.tex', line_start: 9}];
  assert.deepEqual(blockSourceLocation(walk(blocks), 'c#b3'), {file: 'writing_projects/p/draft/chapters/intro.tex', line: 3, basis: {selection_identity: pin('b'), source_digest: pin('a')}});
  assert.equal(blockSourceLocation(walk(blocks), 'a#b1').file, 'writing_projects/p/draft/appendix/intro.tex');
  assert.equal(blockSourceLocation(walk(blocks), 'missing'), null);
  assert.equal(blockSourceLocation(walk(blocks), null), null);
});

test('no published repository file, digest or selection means no location: never the relative name', () => {
  assert.throws(() => blockSourceLocation(walk([{id: 'x', file: 'chapters/chapter-01.tex', line_start: 3}]), 'x'), /no current source location/);
  // even an observation that names the relative path does not make it a location: only the published repository path is
  assert.throws(() => blockSourceLocation(walk([{id: 'x', file: 'chapters/chapter-01.tex', line_start: 3}], {selection_identity: pin('b'), file_revisions: {'chapters/chapter-01.tex': 'a'.repeat(64)}}), 'x'), /no current source location/);
  assert.throws(() => blockSourceLocation(walk([{id: 'x', file: 'c.tex', repo_file: 'p/c.tex', line_start: 3}], {selection_identity: pin('b'), file_revisions: {}}), 'x'), /no current source location/);
  assert.throws(() => blockSourceLocation(walk([{id: 'x', repo_file: 'p/c.tex', line_start: 3}], {selection_identity: 'stale', file_revisions: {'p/c.tex': 'a'.repeat(64)}}), 'x'), /no current source location/);
  assert.throws(() => blockSourceLocation(walk([{id: 'x', repo_file: 'p/c.tex', line_start: 0}]), 'x'), /no current source location/);
});

test('the bridge routes Open in TeX only with an exact location and basis', () => {
  const listeners = [], calls = [], frame = {}, ledger = createBridgeLedger();
  const handlers = Object.fromEntries(BRIDGE_ROUTES.map(route => [route.handler, message => calls.push([route.handler, message])]));
  installWalkBridge({target: {addEventListener: (type, fn) => listeners.push(fn), removeEventListener() {}}, origin: () => 'o', sourceWindow: () => frame, ledger, handlers});
  const send = data => listeners.forEach(fn => fn({origin: 'o', source: frame, data}));
  const basis = {selection_identity: pin('b'), source_digest: pin('a')};
  for (const bad of [{file: 'chapters/chapter-01.tex', line: 3}, {file: '/etc/x.tex', line: 3, basis}, {file: 'p/../x.tex', line: 3, basis},
                     {file: 'p/c.tex', line: 0, basis}, {file: 'p/c.tex', line: 3, basis: {selection_identity: 'x', source_digest: pin('a')}}])
    send({type: 'laplace:open-document-source', ...bad});
  assert.equal(calls.length, 0, 'an inexact location runs nothing');
  assert.equal(ledger.ledger.messages['laplace:open-document-source'], 5, 'every fenced message is still counted');
  send({type: 'laplace:open-document-source', file: 'writing_projects/p/draft/chapters/chapter-01.tex', line: 3, basis});
  assert.deepEqual(calls.map(call => call[0]), ['openDocumentSource']);
});

test('the iframe producer and the shell consumer carry the exact location, never block.file', () => {
  const panel = readFileSync(new URL('../src/laplace/web/static_shared/writing-panel.mjs', import.meta.url), 'utf8');
  // the shell consumer is the walk-handlers owner (workspace-walk-handlers.mjs, M5 S2 F1)
  const shell = readFileSync(new URL('../src/laplace/web/static_shared/workspace-walk-handlers.mjs', import.meta.url), 'utf8');
  assert.match(panel, /item\('Open in TeX',\(\)=>\{let location=null;try\{location=blockSourceLocation\(window\.walk,block\.id\);/);
  assert.doesNotMatch(panel, /open-document-source',\{file:block\.file/);
  assert.match(shell, /openDocumentSource\(message\)\{manuscript\.editor\(\)\?\.openSource\(message\.file,message\.line,false,\{selection_identity:message\.basis\.selection_identity,\s*source_digest:message\.basis\.source_digest\}\)/);
});

test('a menu taller than the frame is capped and scrolls; every item stays inside the frame', () => {
  // Root actual: iframe client height 578, menu bottom item at y 631..670
  const tall = contextMenuPlacement({x: 400, y: 300}, {w: 240, h: 700}, {w: 900, h: 578});
  assert.deepEqual(tall, {left: 400, top: 8, maxHeight: 562});
  assert.ok(tall.top + Math.min(700, tall.maxHeight) <= 578 - 8);
  const low = contextMenuPlacement({x: 880, y: 560}, {w: 240, h: 300}, {w: 900, h: 578});
  assert.deepEqual([low.left, low.top], [652, 270], 'moved left and up to fit');
  const small = contextMenuPlacement({x: 20, y: 30}, {w: 240, h: 200}, {w: 900, h: 578});
  assert.deepEqual([small.left, small.top], [20, 30], 'at the pointer when it fits');
  const panel = readFileSync(new URL('../src/laplace/web/static_shared/writing-panel.mjs', import.meta.url), 'utf8');
  assert.match(panel, /menu\.style\.maxHeight=Math\.max\(0,frameView\.h-16\)\+'px';const place=contextMenuPlacement\(/);
  const css = readFileSync(new URL('../src/laplace/web/static_shared/writing-panel.css', import.meta.url), 'utf8');
  assert.match(css, /#manuscript-context-menu\{position:fixed;[^}]*overflow-y:auto/);
});
