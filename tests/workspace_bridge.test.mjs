// THE WALK BRIDGE, SHELL SIDE (M5 readability P2, 2026-10-14): the route table, the fence, the ledger, the
// shape gate, install/uninstall ownership, and that the real shell supplies one named handler per route and
// removes its listener on destroy.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {BRIDGE_ROUTES,HANDLED_BRIDGE_MESSAGES,UNKNOWN_PRODUCER_MESSAGES,createBridgeLedger,installWalkBridge,routeBridgeMessage,messageBytes} from '../src/laplace/web/static_shared/workspace-bridge.mjs';
// workspace.mjs imports /shared/ paths: the shell fixture registers the resolve hook before it is loaded
await import('./helpers/shell_fixture.mjs');
const shell = await import('../src/laplace/web/static_shared/workspace.mjs');

const ORIGIN = 'http://local';
function harness() {
  const listeners = [], calls = [], frame = {name: 'manuscript iframe'}, ledger = createBridgeLedger();
  const target = {addEventListener: (type, fn) => listeners.push([type, fn]), removeEventListener: (type, fn) => {const at = listeners.findIndex(row => row[0] === type && row[1] === fn); if (at >= 0) listeners.splice(at, 1);}};
  const handlers = Object.fromEntries(BRIDGE_ROUTES.map(route => [route.handler, (message, event) => calls.push([route.handler, message, event])]));
  const bridge = installWalkBridge({target, origin: () => ORIGIN, sourceWindow: () => frame, ledger, handlers});
  const send = (data, extra = {}) => listeners.filter(row => row[0] === 'message').forEach(([, fn]) => fn({origin: ORIGIN, source: frame, data, ...extra}));
  return {listeners, calls, frame, ledger, bridge, send};
}

test('the route table declares the 19 handled messages once each, in ledger order, with distinct handler names', () => {
  assert.equal(BRIDGE_ROUTES.length, 19);
  assert.deepEqual(HANDLED_BRIDGE_MESSAGES, BRIDGE_ROUTES.map(route => route.type));
  assert.equal(new Set(HANDLED_BRIDGE_MESSAGES).size, 19);
  assert.equal(new Set(BRIDGE_ROUTES.map(route => route.handler)).size, 19);
  assert.ok(UNKNOWN_PRODUCER_MESSAGES.every(type => HANDLED_BRIDGE_MESSAGES.includes(type)));
  assert.ok(Object.isFrozen(BRIDGE_ROUTES) && BRIDGE_ROUTES.every(Object.isFrozen), 'the table cannot be edited at runtime');
  assert.equal(shell.HANDLED_BRIDGE_MESSAGES, HANDLED_BRIDGE_MESSAGES, 'the shell re-exports the same declaration');
  assert.equal(shell.createBridgeLedger, createBridgeLedger);
});

test('the fence rejects other origins and other windows; admitted messages are counted and routed to one handler', () => {
  const h = harness();
  h.send({type: 'laplace:source-saved'}, {origin: 'http://elsewhere'});
  h.send({type: 'laplace:source-saved'}, {source: {name: 'another window'}});
  assert.equal(h.ledger.ledger.rejected, 2);
  assert.equal(h.calls.length, 0, 'nothing from outside the current manuscript iframe runs');
  h.send({type: 'laplace:source-saved'});
  assert.deepEqual(h.calls.map(call => call[0]), ['sourceSaved']);
  assert.equal(h.ledger.ledger.messages['laplace:source-saved'], 1);
  const place = {type: 'laplace:place', place: {block: 'b1'}};
  h.send(place);
  assert.equal(h.ledger.ledger.place, 1);
  assert.equal(h.ledger.ledger.place_bytes.last, messageBytes(place));
  assert.equal(h.calls.at(-1)[2].source, h.frame, 'the handler receives the event (the place handler memoises its source)');
});

test('a declared message without its declared shape is counted but runs nothing; undeclared types are bounded samples', () => {
  const h = harness();
  for (const data of [{type: 'laplace:open-owner-read'}, {type: 'laplace:open-document-pdf', file: 7}, {type: 'laplace:logical-object'},
                      {type: 'laplace:research-result', id: null}, {type: 'laplace:obligation-work'}, {type: 'laplace:read-origin-turn'},
                      {type: 'laplace:open-project-artifact'}])
    h.send(data);
  assert.equal(h.calls.length, 0);
  assert.equal(h.ledger.ledger.messages['laplace:open-owner-read'], 1);
  assert.equal(h.ledger.ledger.unknown_producer['laplace:read-origin-turn'], 1, 'unknown-producer types stay instrumented');
  h.send({type: 'laplace:open-project-artifact', path: 'notes.md'});
  assert.deepEqual(h.calls.map(call => call[0]), ['openProjectArtifact'], 'a path alone is the declared shape too');
  for (let i = 0; i < 12; i++) h.send({type: 'laplace:mystery-' + i});
  h.send(null); h.send('laplace:source-saved');
  assert.equal(h.ledger.ledger.unknown.count, 14);
  assert.equal(h.ledger.ledger.unknown.samples.length, 8);
  assert.equal(h.calls.length, 1, 'undeclared or malformed payloads never reach a handler');
  assert.equal(routeBridgeMessage({type: 'laplace:mystery'}, {}), null);
});

test('install refuses an incomplete handler set; uninstall removes exactly its listener, once', () => {
  assert.throws(() => installWalkBridge({target: {addEventListener() {}}, sourceWindow: () => null, ledger: createBridgeLedger(), handlers: {place() {}}}),
    /missing handlers: engineUnavailable, openOwnerRead/);
  const h = harness();
  assert.equal(h.listeners.length, 1);
  assert.equal(h.bridge.installed, true);
  h.bridge.uninstall();
  assert.equal(h.listeners.length, 0);
  assert.equal(h.bridge.installed, false);
  h.bridge.uninstall();
  h.send({type: 'laplace:source-saved'});
  assert.equal(h.calls.length, 0, 'an uninstalled bridge handles nothing');
});

test('the shell supplies one named handler per route in its handler table', () => {
  const source = readFileSync(new URL('../src/laplace/web/static_shared/workspace.mjs', import.meta.url), 'utf8');
  // the handler table is the walk-handlers owner's (workspace-walk-handlers.mjs, M5 S2 F1); the shell installs it
  const handlers = readFileSync(new URL('../src/laplace/web/static_shared/workspace-walk-handlers.mjs', import.meta.url), 'utf8');
  assert.match(source, /installWalkBridge\(\{[^}]*handlers:walkHandlers\.handlers\}\)/, 'the shell installs the owner\'s table');
  const start = handlers.indexOf('  const walkBridgeHandlers={'), end = handlers.indexOf('  return {handlers:walkBridgeHandlers', start);
  assert.ok(start > 0 && end > start);
  const table = handlers.slice(start, end);
  for (const route of BRIDGE_ROUTES) assert.match(table, new RegExp('\\n    ' + route.handler + '\\('), route.handler);
  assert.ok(!source.includes("window.addEventListener('message'"), 'the shell no longer adds its own message listener');
  assert.match(source, /destroy\(\)\{if\(shellDestroyed\)return;shellDestroyed=true;[^}]*walkBridge\.uninstall\(\);removePageListeners\(\);/, 'workspace.destroy (once) removes the bridge listener and the page listeners');
});

test('the mounted shell installs the bridge and removes it on destroy', async () => {
  const {mountShell} = await import('./helpers/shell_fixture.mjs');
  const s = await mountShell();
  try {
    const ledger = window.laplaceBridge;
    window.dispatchEvent({type: 'message', origin: 'http://elsewhere', source: null, data: {type: 'laplace:source-saved'}});
    assert.equal(ledger.rejected, 1, 'the installed listener fences a foreign message');
    s.workspace.destroy();
    window.dispatchEvent({type: 'message', origin: 'http://elsewhere', source: null, data: {type: 'laplace:source-saved'}});
    assert.equal(ledger.rejected, 1, 'after destroy no listener remains');
  } finally {s.restore();}
});
