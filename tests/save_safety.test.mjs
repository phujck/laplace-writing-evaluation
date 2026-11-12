// Save safety (wave WRITING-FRONTEND-REPAIRS-W2, packet save-safety; the 5 November brief's A2 and A4).
// These tests drive the REAL walk functions, sliced verbatim from the walk's owner modules
// (commitEdit, the draft owner's park/basis/settlement functions and the park persistence), against
// a stand-in owner that keeps one source line per paragraph. The stand-in reproduces what the save
// trace measured on the real owner: an edit sent with a stale identity is merged with the bytes
// already on disk, and two insertions at the same place put the sent one first (save-trace C1,
// review_surface.py:1521). Its owner read (`reloadBlock`) mirrors the in-place path of
// walk-document.mjs `_reloadBlock` (park the active edit, re-render, restoreFace, carry the edit
// back); its refresh mirrors walk.mjs `refresh` (park a dirty edit, read the whole document,
// re-render, restoreParked). The browser proof is the packet's scenarios, not these doubles.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {continuedEdit, emptyParagraphSource, matchHeldDraft, mergeDraftRows, normalizeDraftRows} from '../src/laplace/web/static_shared/manuscript-editing.mjs';
import {sourceEffectDisposition} from '../src/laplace/web/static_shared/source-effect.mjs';
import {walkDeclarations} from './helpers/walk_source.mjs';

const code = walkDeclarations('expectedOf', 'captureBasis', 'assignBasis', 'basisOf', 'verifyAwaiting', 'markSubmitted',
  'settleSubmission', 'readdressDraft', 'awaitingUnread', 'REVIEW_WORDS', 'MOVED_WORDS', 'placeDraft', 'draftSource', 'placeOf', 'keepUnplaced',
  'restoreFace', 'restoreParked', 'showOtherVersion',
  'parkEntry', 'parkEdit', 'clearEdit', 'snapshotEdit', 'PARK_KEY', 'parksLoaded', 'localDraftRows', 'saveParks', 'loadParks',
  'spanOf', 'ownerView', 'appliedOf', 'pendingOf', 'INFLIGHT', 'NOT_SAVED', 'sayNotSaved', 'NOT_LOCATED', 'NOT_LOCATED_LINE', 'keepPlace', 'commitEdit', 'commitAll', 'ownSavesUnread', 'ownParagraph');
const NAMES = ['E', 'P', 'D', 'F', 'S', 'C', 'OWNER_READ', 'blockById', 'hostText', 'srcOf', 'applyFace', 'replaceByContext', 'showCard', 'hideCard', 'emit',
  'paintParked', 'setEditScope', 'autosize', 'cardNote', 'window', 'crypto', 'storageRecovered', 'storageFailure', 'paintHeldDrafts',
  'matchHeldDraft', 'mergeDraftRows', 'normalizeDraftRows', 'continuedEdit', 'emptyParagraphSource', 'sourceEffectDisposition',
  'RELOAD_INFLIGHT', 'structuralSourceHolds', 'showStructuralOutcome', 'pendingPresentationSplits', 'taggedParagraph', 'offsetIn', 'askActor',
  'sourceForRenderedRange', 'pieceTypeAt', 'anchorFromPristine', 'sourceRequest', 'toSourceRegister', 'headSpan', 'rewritePayload',
  'setPayload', 'commitPresentationSplit', 'saveSourceChange', 'reloadBlock', 'admit', 'MINTED', 'ledgerPath', 'srcSpanWords', 'receiptWords',
  'settleRail', 'renderComposer', 'renderBand', 'paintDeposits', 'focusSplitParagraph', 'captureFocus', 'renderBlockBody', 'paintMarks',
  'measure', 'restoreFocus', 'dropArmedMark', 'bankCardComment', 'parkDiff', 'document', 'docEl', 'el', 'asChrome'];

const BASE = 'Compare watering observations and write a short, evidence-based account.';
const OTHER = 'A second paragraph.';
const tok = tex => 'tok:' + tex;

// The stand-in owner: one source line per paragraph, an identity token per exact bytes.
function owner(storage = new Map(), lines = {p1: BASE, p2: OTHER}) {
  const server = {tex: new Map(Object.entries(lines)), mode: 'apply', down: false, posts: [], held: [], ids: 0, superseded: [], inserted: []};
  const apply = payload => {
    // wave 14b: a paragraph the stand-in no longer has is put back (`placement: insert`) under its own id
    const id = payload.blockId && server.tex.has(payload.blockId) ? payload.blockId : 'inserted-' + (server.inserted.length + 1);
    if (!server.tex.has(id)) { assert.equal(payload.placement, 'insert', 'only an insert writes a paragraph the file does not have'); server.inserted.push(payload.after); server.tex.set(id, payload.before_content ?? payload.before); }
    const current = server.tex.get(id);
    // the author's typed edit (wave 14a, review_surface.py _author_editor_write): his text is applied over the
    // span as it is now, whatever identity or guard it carries; replaced bytes are kept as `superseded`
    assert.equal(payload.source, 'click-type', 'the editor sends its typed edits as the author path');
    const superseded = (payload.before_content ?? payload.before) === current ? undefined : current;
    server.tex.set(id, payload.after);
    if (superseded !== undefined) server.superseded.push(superseded);
    server.ids += 1;
    return {ok: true, pending: false, applied: {file: 'chapter.tex'}, record: {id: 'FB-' + server.ids, ts: '2026-11-05T22:00:00', anchor: {after: server.tex.get(id), ...(superseded !== undefined ? {superseded} : {})}}};
  };
  server.save = async payload => {
    server.posts.push(structuredClone(payload));
    if (server.down || server.mode === 'fail') throw new TypeError('Failed to fetch');
    if (server.mode === 'refuse') throw Object.assign(Error('fetchJSON POST /review/adjudicate → 422: cannot stage the rewrite'), {status: 422, body: {error: 'cannot stage the rewrite'}});
    // review_surface.py: nothing in the file locates his paragraph (another writer deleted it); only an
    // explicit insert (Keep my text and save it after this answer) writes it, back at its place
    if (server.mode === 'gone' && payload.placement !== 'insert') throw Object.assign(Error('fetchJSON POST /review/adjudicate → 409: your paragraph could not be located in the file any more'),
      {status: 409, body: {error: 'your paragraph could not be located in the file any more', reason: 'passage-not-located', refused: {kind: 'unknown-home', needed: {read: 'GET /walk/doc'}}}});
    if (server.mode === 'gone') { server.tex.delete(payload.blockId); payload = {...payload, blockId: ''}; }
    const answer = apply(payload);
    if (server.mode === 'lose') throw new TypeError('Failed to fetch');
    if (server.mode === 'hold') return new Promise(release => server.held.push(() => release(answer)));
    return answer;
  };
  server.release = () => { for (const release of server.held.splice(0)) release(); };
  return {server, storage};
}

// One page: the paragraphs, their rendered faces (render = identity), and the sliced walk.
function page({server, storage}) {
  const faces = new Map(), events = [], cards = [], panels = [];
  const blocks = [...server.tex.keys()].map((id, i) => ({id, kind: 'para', tex: server.tex.get(id), expected: [tok(server.tex.get(id))], readSeq: 1,
    src: {file: 'chapter.tex', line_start: 4 + 2 * i, line_end: 4 + 2 * i}, el: {dataset: {}, scrollIntoView() {}}, pieceMap: []}));
  for (const b of blocks) { b.bodyEl = {id: b.id, get textContent() { return faces.get(b.id); }, set textContent(value) { faces.set(b.id, value); }}; faces.set(b.id, b.tex); }
  const E = {blockId: '', pristine: '', tex: '', src: null, expectedSelection: undefined, expected: null, awaiting: null, supersedes: null,
    moved: false, place: null, dirty: false, timer: 0, committing: false, composing: false, scope: '', selAnchor: null, historyGroup: null};
  const bindings = {E, P: new Map(), D: {sourceObservation: {source_observation: {selection_identity: 'sel-1'}}}, F: {blockId: ''},
    S: {blocks, corpus: 'garden-study'}, C: {actor: 'author', mine: new Set()}, OWNER_READ: {seq: 1}, blockById: new Map(blocks.map(b => [b.id, b])),
    hostText: host => faces.get(host.id), srcOf: b => ({file: b.src.file, lineStart: b.src.line_start, lineEnd: b.src.line_end}),
    applyFace: (b, entry) => { faces.set(b.id, entry.text); return true; }, replaceByContext: () => false,
    showCard: (b, words, tone) => cards.push({id: b.id, words, tone}), hideCard: () => cards.push({hidden: true}), emit: (name, detail) => events.push([name, detail]),
    paintParked: () => bindings.saveParks(), setEditScope() {}, autosize() {}, cardNote: null,
    window: {localStorage: {getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key)}},
    crypto: {randomUUID: () => 'draft-' + Math.random().toString(36).slice(2)}, storageRecovered() {}, storageFailure: (_, error) => { throw error; },
    paintHeldDrafts() {}, matchHeldDraft, mergeDraftRows, normalizeDraftRows, continuedEdit, emptyParagraphSource, sourceEffectDisposition,
    RELOAD_INFLIGHT: null, structuralSourceHolds: new Map(), showStructuralOutcome() {}, pendingPresentationSplits: new Map(), taggedParagraph: () => false,
    offsetIn: () => 0, askActor() {}, sourceForRenderedRange: (b, start, end) => faces.get(b.id).slice(start, end), pieceTypeAt: () => 'text',
    anchorFromPristine: (b, full, start, end) => ({file: b.src.file, lineStart: b.src.line_start, lineEnd: b.src.line_end, blockId: b.id, sectionId: '',
      quote: full.slice(start, end), start, end, full}),
    sourceRequest: parts => ({...parts, ...(parts.extra || {})}), toSourceRegister: value => value, headSpan: () => null,
    // the line postimage the real `rewritePayload` sends: the draft's pristine line with the typed span spliced in
    rewritePayload: (a, typed, note, expected) => ({file: a.file, lineStart: a.lineStart, lineEnd: a.lineEnd, blockId: a.blockId,
      before: a.full, after: a.full.slice(0, a.start) + typed + a.full.slice(a.end), note, expected}),
    setPayload: (body, key, value) => { body[key] = value; return body; }, commitPresentationSplit: async () => null,
    saveSourceChange: payload => server.save(payload),
    admit: () => true, MINTED: new Set(), ledgerPath: () => 'ledger', srcSpanWords: () => 'chapter.tex', receiptWords: () => '', settleRail() {},
    renderComposer() {}, renderBand() {}, paintDeposits() {}, focusSplitParagraph: async () => {}, captureFocus: () => null,
    renderBlockBody: b => faces.set(b.id, b.tex), paintMarks() {}, measure() {}, restoreFocus() {}, dropArmedMark() {},
    // the panel showOtherVersion puts above the manuscript, as plain nodes
    document: {querySelector: () => null}, asChrome: node => node, panels,
    el: (tag, cls, text) => ({tag, cls, text, value: '', dataset: {}, kids: [], append(...kids) { this.kids.push(...kids); }, setAttribute() {}, remove() {}}),
    docEl: {before: node => panels.push(node)}};
  const read = b => { b.tex = server.tex.get(b.id); b.expected = [tok(b.tex)]; b.readSeq = bindings.OWNER_READ.seq; };
  // walk-document.mjs `_reloadBlock`, in-place path: park the active edit, adopt the owner's block, re-render, restore, carry back
  bindings.reloadBlock = async id => {
    if (server.down) return {ok: false, note: 'the doc model door did not answer for the re-render. Failed to fetch'};
    const b = bindings.blockById.get(id), activeHere = E.blockId === b.id && E.dirty;
    if (activeHere) api.parkEdit(b);
    bindings.OWNER_READ.seq += 1; read(b); faces.set(b.id, b.tex);
    if (bindings.P.has(b.id)) api.restoreFace(b);
    if (activeHere) {
      const held = bindings.P.get(b.id);
      E.blockId = b.id; E.pristine = held ? held.pristine : faces.get(b.id);
      api.assignBasis(E, held ? held : api.captureBasis(b)); E.moved = !!held?.moved; E.place = held?.place || null;
      E.dirty = held ? faces.get(b.id) !== held.pristine : false;
    }
    return {ok: true};
  };
  const api = new Function('bindings', `let {${NAMES.join(',')}} = bindings;
    ${code}
    bindings.saveParks = saveParks;
    return {expectedOf, captureBasis, assignBasis, readdressDraft, restoreFace, restoreParked, showOtherVersion, parkEdit, clearEdit,
      snapshotEdit, saveParks, loadParks, localDraftRows, commitEdit, commitAll, parkEntry, ownSavesUnread};`)(bindings);
  const E_ = bindings.E, P = bindings.P;
  const self = {
    ...api, E: E_, P, C: bindings.C, faces, events, cards, panels, server, storage, blocks, byId: bindings.blockById, OWNER_READ: bindings.OWNER_READ,
    // one keystroke run, as walk-edit-input.mjs onEditInput records it: the face changes, dirty is the
    // difference from pristine and the park rides every keystroke
    type(id, words) {
      const b = bindings.blockById.get(id);
      if (E_.blockId !== id) api.snapshotEdit(b, b.bodyEl);
      faces.set(id, faces.get(id) + words);
      E_.dirty = faces.get(id) !== E_.pristine;
      if (E_.dirty) P.set(id, api.parkEntry(b, b.bodyEl, faces.get(id))); else P.delete(id);
      bindings.saveParks();
    },
    // walk.mjs refresh: park a dirty edit, read the whole document, re-render, restore the parks
    async refresh() {
      if (E_.blockId && E_.dirty) api.parkEdit(bindings.blockById.get(E_.blockId));
      if (E_.blockId && !E_.dirty) api.clearEdit();
      bindings.OWNER_READ.seq += 1;
      for (const b of blocks) { read(b); faces.set(b.id, b.tex); }
      api.restoreParked();
    },
    load() { bindings.OWNER_READ.seq += 1; for (const b of blocks) { read(b); faces.set(b.id, b.tex); } api.loadParks(); },
    stored: () => JSON.parse(storage.get('walk-parks:garden-study') || '[]'),
    savedNow: () => events.filter(([name, detail]) => name === 'bank' && detail.applied === true).length,
  };
  self.load();   // opening the page: the first owner read, then the stored parks (walk-drafts.mjs loadParks)
  return self;
}
function start(lines) {
  const app = owner(new Map(), lines);
  const p = page(app);
  return {app, p};
}

test('typed text survives a refused save, a lost reply, a timeout and a changed source, word for word', async () => {
  // refused: the owner answers 422; nothing is written and his words stay on the paragraph, in the park and in storage
  {
    const {app, p} = start();
    app.server.mode = 'refuse';
    p.type('p1', ' Wind on Friday.');
    assert.equal(await p.commitEdit('autosave'), null);
    assert.equal(app.server.tex.get('p1'), BASE);
    assert.equal(p.faces.get('p1'), BASE + ' Wind on Friday.');
    assert.equal(p.P.get('p1').text, BASE + ' Wind on Friday.');
    assert.equal(p.stored()[0][1].text, BASE + ' Wind on Friday.');
    assert.equal(p.E.awaiting, null, 'a refusal is an answer: the draft keeps its own basis');
    assert.deepEqual(p.E.expected, [tok(BASE)], 'its own basis tokens: no hold, no other authority');
    assert.equal(p.savedNow(), 0);
  }
  // lost reply (wave 14a): the owner applied, the reply never came. Nothing is read back while he types
  // (save-trace C1 is gone for the author path): his words stay an unsaved draft, the line says no answer,
  // and his next save writes his whole text over the span once: the sentence is not written twice
  {
    const {app, p} = start();
    app.server.mode = 'lose';
    p.type('p1', ' Rain fell on Tuesday.');
    assert.equal(await p.commitEdit('autosave'), null);
    assert.equal(app.server.tex.get('p1'), BASE + ' Rain fell on Tuesday.');
    assert.equal(p.E.dirty, true, 'no answer: his text is kept as unsaved, not claimed saved');
    assert.equal(p.E.awaiting, null, 'no settle read is pending');
    assert.deepEqual(p.events.filter(([name]) => name === 'save-outcome').at(-1)[1], {state: 'not-saved', reason: 'No answer from the engine'});
    assert.equal(p.savedNow(), 0, 'no reply was received, so no bank event claims Saved');
    app.server.mode = 'apply';
    p.type('p1', ' Wind on Friday.');
    await p.commitEdit('ctrl-s');
    assert.equal(app.server.tex.get('p1'), BASE + ' Rain fell on Tuesday. Wind on Friday.');
    assert.equal(app.server.tex.get('p1').split('Rain fell on Tuesday.').length, 2, 'written once');
  }
  // no reply because the engine is down: the draft is kept word for word; his next save sends it, once
  {
    const {app, p} = start();
    app.server.down = true;
    p.type('p1', ' Rain fell on Tuesday.');
    await p.commitEdit('autosave');
    assert.equal(p.E.awaiting, null);
    p.type('p1', ' Wind on Friday.');
    assert.equal(p.faces.get('p1'), BASE + ' Rain fell on Tuesday. Wind on Friday.');
    assert.equal(p.P.get('p1').text, BASE + ' Rain fell on Tuesday. Wind on Friday.');
    app.server.down = false; app.server.mode = 'apply';
    p.type('p1', ' Calm.');
    await p.commitEdit('ctrl-s');
    assert.equal(app.server.tex.get('p1'), BASE + ' Rain fell on Tuesday. Wind on Friday. Calm.');
  }
  // timeout: the reply is held; Saving holds, his words are kept as submitted, and the late reply settles them
  {
    const {app, p} = start();
    app.server.mode = 'hold';
    p.type('p1', ' Rain fell on Tuesday.');
    const pending = p.commitEdit('autosave');
    await new Promise(ok => setTimeout(ok, 0));
    assert.equal(p.E.committing, true);
    assert.equal(p.stored()[0][1].awaiting.postimage, BASE + ' Rain fell on Tuesday.');
    assert.equal(p.stored()[0][1].text, BASE + ' Rain fell on Tuesday.');
    app.server.release();
    await pending;
    assert.equal(app.server.tex.get('p1'), BASE + ' Rain fell on Tuesday.');
    assert.equal(p.E.dirty, false);
    assert.equal(p.P.size, 0);
    assert.equal(p.savedNow(), 1);
  }
  // changed source (wave 14a, ruling 1): another writer changed the line; his text is authoritative and
  // replaces it, and the replaced bytes are kept by the owner as `superseded`
  {
    const {app, p} = start();
    p.type('p1', ' Rain fell on Tuesday.');
    app.server.tex.set('p1', BASE + ' (Revised.)');
    await p.commitEdit('ctrl-s');
    assert.equal(app.server.tex.get('p1'), BASE + ' Rain fell on Tuesday.');
    assert.deepEqual(app.server.superseded, [BASE + ' (Revised.)']);
    assert.equal(p.cards.filter(card => card.tone === 'refused').length, 0, 'no refusal is shown');
  }
});

test('an async refresh or selection change during a pending save neither drops nor overwrites the pending text', async () => {
  // refresh while the reply is held (save-trace C7): the later words stay on the paragraph
  {
    const {app, p} = start();
    app.server.mode = 'hold';
    p.type('p1', ' Rain fell on Tuesday.');
    const pending = p.commitEdit('autosave');
    await new Promise(ok => setTimeout(ok, 0));
    p.type('p1', ' And more.');
    await p.refresh();
    assert.equal(p.faces.get('p1'), BASE + ' Rain fell on Tuesday. And more.', 'the newer words stay on the paragraph');
    assert.equal(p.P.get('p1').pristine, BASE + ' Rain fell on Tuesday.', 'the read holds the submitted words: they are the baseline');
    assert.equal(p.P.get('p1').unplaced, false);
    app.server.release();
    await pending;
    assert.equal(p.faces.get('p1'), BASE + ' Rain fell on Tuesday. And more.', 'the older reply does not take the newer words off');
    assert.equal(p.P.get('p1').text, BASE + ' Rain fell on Tuesday. And more.');
    app.server.mode = 'apply';
    p.snapshotEdit(p.byId.get('p1'), p.byId.get('p1').bodyEl);
    await p.commitEdit('ctrl-s');
    assert.equal(app.server.tex.get('p1'), BASE + ' Rain fell on Tuesday. And more.');
  }
  // selection change while the reply is held: moving to another paragraph parks the edit; the late
  // reply settles that park and touches nothing else
  {
    const {app, p} = start();
    app.server.mode = 'hold';
    p.type('p1', ' Rain fell on Tuesday.');
    const pending = p.commitEdit('autosave');
    await new Promise(ok => setTimeout(ok, 0));
    p.type('p1', ' And more.');
    p.type('p2', ' Elsewhere.');
    app.server.release();
    await pending;
    assert.equal(p.faces.get('p1'), BASE + ' Rain fell on Tuesday. And more.');
    assert.equal(p.P.get('p1').text, BASE + ' Rain fell on Tuesday. And more.');
    assert.equal(p.P.get('p1').awaiting, null, 'the late reply settles the park');
    assert.ok(!p.P.get('p1').review, 'his own save is not a change under his draft');
    assert.equal(p.E.blockId, 'p2');
    assert.equal(p.faces.get('p2'), OTHER + ' Elsewhere.');
    assert.equal(p.E.dirty, true);
    // Save changes: both paragraphs; p1's guard is the text this editor wrote, so nothing is superseded
    app.server.mode = 'apply';
    await p.commitAll();
    assert.equal(app.server.tex.get('p1'), BASE + ' Rain fell on Tuesday. And more.');
    assert.equal(app.server.tex.get('p2'), OTHER + ' Elsewhere.');
    assert.deepEqual(app.server.superseded, []);
  }
});

test('one save in flight per paragraph: a save asked for meanwhile goes once with the latest text when the reply lands (ruling 4)', async () => {
  const {app, p} = start();
  app.server.mode = 'hold';
  p.type('p1', ' Rain fell on Tuesday.');
  const first = p.commitEdit('autosave');
  await new Promise(ok => setTimeout(ok, 0));
  p.type('p1', ' Wind on Friday.');
  assert.equal(await p.commitEdit('ctrl-s'), null, 'no second request while the first is out');
  assert.equal(await p.commitEdit('autosave'), null);
  assert.equal(app.server.posts.length, 1);
  app.server.release();
  await new Promise(ok => setTimeout(ok, 0));
  assert.equal(app.server.posts.length, 2, 'the reply landed and exactly one further save went');
  assert.equal(app.server.posts[1].after, BASE + ' Rain fell on Tuesday. Wind on Friday.', 'carrying the latest text');
  assert.equal(app.server.posts[1].before_content, BASE + ' Rain fell on Tuesday.', 'guarded by what the first save wrote');
  assert.equal(p.faces.get('p1'), BASE + ' Rain fell on Tuesday. Wind on Friday.', 'the older reply does not touch the newer text');
  app.server.release();
  await first;
  assert.equal(app.server.tex.get('p1'), BASE + ' Rain fell on Tuesday. Wind on Friday.');
  assert.equal(p.E.dirty, false);
  assert.equal(p.P.size, 0);
  assert.deepEqual(app.server.superseded, []);
  // the persisted row keeps no read ordinal, the live park does
  {
    const {app: two, p: q} = start();
    two.server.mode = 'hold';
    q.type('p1', ' Rain.');
    const out = q.commitEdit('autosave');
    await new Promise(ok => setTimeout(ok, 0));
    q.type('p1', ' Wind.');
    q.saveParks();
    assert.equal(typeof q.P.get('p1').awaiting.seq, 'number');
    assert.equal(q.stored()[0][1].awaiting.seq, undefined);
    two.server.release(); await out;
  }
});

test('reload restores an unsaved draft and says it is unsaved', async () => {
  // an unsaved draft (no save attempted): restored with its words and its own basis, still unsaved
  {
    const app = owner();
    const before = page(app);
    before.type('p1', ' Wind on Friday.');
    const after = page(app);
    assert.equal(after.faces.get('p1'), BASE + ' Wind on Friday.');
    assert.equal(after.P.size, 1, 'the restored draft is counted as unsaved');
    assert.equal(after.P.get('p1').moved, false, 'its source did not move: an ordinary unsaved draft');
    assert.deepEqual(after.P.get('p1').expected, [tok(BASE)]);
  }
  // reloaded while a save's reply was held and the bytes are on disk (save-trace C6): settled as saved
  {
    const app = owner();
    const before = page(app);
    app.server.mode = 'hold';
    before.type('p1', ' Wind on Friday.');
    before.commitEdit('autosave');
    await new Promise(ok => setTimeout(ok, 0));
    assert.equal(app.server.tex.get('p1'), BASE + ' Wind on Friday.');
    const after = page(app);
    assert.equal(after.P.size, 0, 'the owner read shows exactly the submitted bytes: no draft is left');
    assert.equal(after.faces.get('p1'), BASE + ' Wind on Friday.');
  }
  // reloaded while a save's reply was held, with later words: the later words stay as an unsaved draft on the saved text
  {
    const app = owner();
    const before = page(app);
    app.server.mode = 'hold';
    before.type('p1', ' Wind on Friday.');
    before.commitEdit('autosave');
    await new Promise(ok => setTimeout(ok, 0));
    before.type('p1', ' Calm.');
    const after = page(app);
    assert.equal(after.faces.get('p1'), BASE + ' Wind on Friday. Calm.');
    assert.equal(after.P.get('p1').pristine, BASE + ' Wind on Friday.');
    assert.deepEqual(after.P.get('p1').expected, [tok(BASE + ' Wind on Friday.')]);
    assert.equal(!!after.P.get('p1').moved, false);
  }
  // reloaded after a save that never reached the owner: the draft is unsaved, on its own basis
  {
    const app = owner();
    const before = page(app);
    app.server.mode = 'fail';
    before.type('p1', ' Wind on Friday.');
    app.server.down = true;
    await before.commitEdit('autosave');
    app.server.down = false;
    const after = page(app);
    assert.equal(after.faces.get('p1'), BASE + ' Wind on Friday.');
    assert.equal(after.P.get('p1').awaiting, null);
    assert.deepEqual(after.P.get('p1').expected, [tok(BASE)]);
  }
});

test('the frame says Saved only for an applied edit (save-trace C4b)', () => {
  const panel = readFileSync(new URL('../src/laplace/web/static_shared/writing-panel.mjs', import.meta.url), 'utf8');
  const handler = panel.slice(panel.indexOf("window.walk.on('bank',"), panel.indexOf("window.parent.postMessage({type:'laplace:source-saved'}", panel.indexOf("window.walk.on('bank',")));
  assert.match(handler, /event\.applied===true/);
  // wave 3 (save-line): the frame repeats the save line (`showSave`) instead of its own bare words
  const status = {textContent: 'Unsaved changes'};
  const showSave = () => { status.textContent = 'the save line'; };
  const run = new Function('showSave', 'event', handler.slice(handler.indexOf('{') + 1));
  run(showSave, {applied: false, pending: false, shape: 'rewrite'});
  assert.equal(status.textContent, 'Unsaved changes', 'a row recorded without confirmed application is not called Saved');
  run(showSave, {applied: false, pending: false, shape: 'comment'});
  assert.equal(status.textContent, 'Unsaved changes', 'a banked comment does not put Saved in the frame (NODE.w3 ruling 4)');
  run(showSave, {applied: true, pending: false, shape: 'rewrite'});
  assert.equal(status.textContent, 'the save line');
  status.textContent = 'Unsaved changes';
  run(showSave, {applied: false, pending: true, shape: 'rewrite'});
  assert.equal(status.textContent, 'the save line');
});

// judge-r1 D1: a save that applied while he typed on moved the file because HE saved. walk.editState().submitted
// counts that paragraph (walk.mjs, walk-editing.mjs ownSavesUnread), and the shell's refresh poller
// (manuscript-editing.mjs deferDraft) says nothing about a change elsewhere while it is non-zero.
test('words typed on past his own applied save count as his own unread save until the paragraph is saved clean or re-read', async () => {
  const {app, p} = start();
  app.server.mode = 'hold';
  p.type('p1', ' Rain fell');
  const first = p.commitEdit('ctrl-s');
  await new Promise(ok => setTimeout(ok, 0));
  p.type('p1', ' on Tuesday.');
  app.server.release();
  await first;
  assert.equal(app.server.tex.get('p1'), BASE + ' Rain fell', 'the first save applied');
  assert.equal(p.E.dirty, true, 'the later words are an unsaved draft');
  assert.equal(p.ownSavesUnread(), 1, 'the file moved by his own save: not a change elsewhere');
  app.server.mode = 'apply';
  await p.commitEdit('ctrl-s');
  assert.equal(app.server.tex.get('p1'), BASE + ' Rain fell on Tuesday.');
  assert.equal(p.ownSavesUnread(), 0, 'saved clean: nothing of his is unread');
  // an applied save typed past, then re-read by a refresh: the canvas now holds that revision
  app.server.mode = 'hold';
  p.type('p2', ' More.');
  const second = p.commitEdit('ctrl-s');
  await new Promise(ok => setTimeout(ok, 0));
  p.type('p2', ' Again.');
  app.server.release();
  await second;
  assert.equal(p.ownSavesUnread(), 1);
  await p.refresh();
  assert.equal(p.ownSavesUnread(), 0, 'after a re-read the moved file is no longer his unread save');
});

// judge-r1 D3: a failed or unanswered save raises no orange card; its one warning is the frame line, where
// writing-panel.mjs offerKeep puts Keep my text and save it first (his ruling 3).
test('a failed save shows no refused card; its warning is the frame line and Keep my text and save it is its first control', async () => {
  const {installHTMLDocument} = await import('./helpers/html_dom.mjs');
  const {declareControl} = await import('../src/laplace/web/static_shared/workspace-presentation.mjs');
  const panel = readFileSync(new URL('../src/laplace/web/static_shared/writing-panel.mjs', import.meta.url), 'utf8');
  const cut = (from, to) => panel.slice(panel.indexOf(from), panel.indexOf(to, panel.indexOf(from)));
  for (const mode of ['refuse', 'fail', 'lose']) {
    const {app, p} = start();
    app.server.mode = mode;
    p.type('p1', ' Rain fell on Tuesday.');
    assert.equal(await p.commitEdit('ctrl-s'), null);
    assert.deepEqual(p.cards.filter(card => card.tone === 'refused'), [], mode + ': no orange card without Keep');
    assert.ok(p.cards.some(card => card.hidden), mode + ': the saving card is taken down');
    const warning = p.events.filter(([name, detail]) => name === 'editor-status' && detail.error).map(([, detail]) => detail.text);
    assert.equal(warning.length, 1, mode + ': one warning, on the frame line');
    const env = installHTMLDocument({width: 1280});
    try {
      const E = (tag, cls, text) => { const node = document.createElement(tag); if (cls) node.className = cls; if (text != null) node.textContent = text; return node; };
      const editorStatus = E('span', '', warning[0]);
      document.body.append(editorStatus);
      const offerKeep = new Function('E', 'declareControl', 'editorStatus', 'window', 'document', cut('  const offerKeep=', '  const ready=()=>{') + ';return offerKeep;')(
        E, declareControl, editorStatus, {walk: {editState: () => ({dirty: true, parked: 1}), commitAll: async () => ({message: 'Saved'})}}, document);
      offerKeep();
      const first = editorStatus.querySelector('button');
      assert.equal(first?.textContent, 'Keep my text and save it', mode + ': Keep is the first control of the warning');
      assert.equal(first.dataset.control, 'editor-frame:keep-my-text');
    } finally { env.restore(); }
  }
});

// judge-r1 D2: Keep for an unplaced draft never places it by line number alone (walk-editing.mjs ownParagraph,
// the owner's rule in review_surface.py _author_paragraph).
test('an unplaced draft goes to the paragraph whose words are its own, never to the paragraph now at its old line', () => {
  const ownParagraph = new Function('S', 'srcOf', walkDeclarations('ownParagraph') + ';return ownParagraph;');
  const srcOf = b => ({file: b.src.file, lineStart: b.src.line_start, lineEnd: b.src.line_end});
  const para = (id, line, tex) => ({id, kind: 'para', tex, bodyEl: {}, src: {file: 'chapter.tex', line_start: line, line_end: line}});
  const mine = 'The quick brown fox jumps over the lazy dog.';
  const entry = {tex: mine, pristine: mine, src: {file: 'chapter.tex', lineStart: 5, lineEnd: 5}};
  const inserted = para('b2', 5, 'An inserted paragraph by someone else.');
  const his = para('b3', 7, 'The quick brown fox jumps over the lazy dog, said the agent.');
  const other = para('b4', 9, 'The lazy dog sleeps here in the afternoon sun.');
  assert.equal(ownParagraph({blocks: [inserted, his, other]}, srcOf)(entry), his, 'his own paragraph, at its new line');
  const rewritten = para('b3', 7, 'Entirely different words now stand here.');
  assert.equal(ownParagraph({blocks: [inserted, rewritten, other]}, srcOf)(entry), null, 'none clearly his: not placed at line 5');
  // near-repeated paragraphs: the tie of words is broken by its own line; a near-repeat elsewhere is not chosen
  const edited = para('b5', 5, mine.replace('dog.', 'dog, said the agent.')), repeat = para('b6', 9, mine.replace('dog.', 'dog again.'));
  assert.equal(ownParagraph({blocks: [edited, repeat]}, srcOf)(entry), edited);
  assert.equal(ownParagraph({blocks: [para('b7', 3, 'An inserted paragraph by someone else.'), repeat, para('b8', 11, mine + ' Too.')]}, srcOf)(
    {...entry, src: {file: 'chapter.tex', lineStart: 3, lineEnd: 3}}), null, 'the line alone never chooses');
});

// ── wave 14b ─────────────────────────────────────────────────────────────────────────────────────────
// The record's item 1 and judge-r2 D5: his paragraph deleted by another writer. The owner's one refusal
// (passage-not-located) keeps his text with its place; Keep my text and save it sends ONE request that asks
// the owner to put the paragraph back (`placement: insert`), never the refused payload again.
test('passage-not-located keeps his text with its place, and the next save puts the paragraph back instead of repeating the refusal', async () => {
  const {app, p} = start();
  p.type('p1', ' I counted forty bees.');
  app.server.mode = 'gone';
  assert.equal(await p.commitEdit('ctrl-s'), null);
  assert.equal(app.server.posts.length, 1);
  assert.equal(app.server.posts[0].placement, undefined, 'the first save is an ordinary save');
  const place = p.P.get('p1').place;
  assert.deepEqual({file: place.file, line: place.line, before: place.before, after: place.after},
    {file: 'chapter.tex', line: 4, before: BASE, after: BASE + ' I counted forty bees.'}, 'the draft keeps its place and the source it stands for');
  assert.equal(p.stored()[0][1].place.after, BASE + ' I counted forty bees.', 'the place is persisted with the draft (same storage key)');
  const lines = p.events.filter(([name, detail]) => name === 'editor-status' && detail.error).map(([, detail]) => detail.text);
  assert.match(lines.at(-1), /^Not saved: your paragraph is not in the file .* Keep my text and save it puts it back at its place\.$/);
  // the record's item 4: the band's receipt says it did not apply, in the warning tone, and names Keep
  assert.equal(p.C.echo.tone, 'refused');
  assert.match(p.C.echo.text, /^Not saved: .*Keep my text and save it/);
  assert.deepEqual(p.cards.filter(card => card.tone === 'refused'), [], 'no card without Keep');
  // Keep my text and save it (commitAll): one request, with the insert, and it applies
  const batch = await p.commitAll();
  assert.equal(app.server.posts.length, 2, 'Keep sent one request');
  assert.equal(app.server.posts[1].placement, 'insert', 'not the refused payload again');
  assert.deepEqual(app.server.inserted, [BASE + ' I counted forty bees.'], 'his paragraph is back');
  assert.equal(batch.applied.length, 1);
  assert.equal(batch.refused.length, 0);
  assert.equal(p.P.size, 0, 'nothing is left held');
});

// The record's item 1 across a reload: the paragraph is not in the file and the canvas has no face for it.
// The draft is kept above the manuscript with its place, and Keep sends its stored source once.
test('a draft whose paragraph is gone after a reload is kept with its place, and Keep puts it back with one request', async () => {
  const app = owner();
  const before = page(app);
  before.type('p1', ' I counted forty bees.');
  app.server.tex.delete('p1');                                    // another writer deleted the paragraph
  const after = page(app);
  assert.equal(after.P.has('p1'), false);
  const [key, entry] = [...after.P].find(([, row]) => row.unplaced);
  assert.equal(key, 'held:p1');
  assert.deepEqual({line: entry.place.line, before: entry.place.before, after: entry.place.after}, {line: 4, before: BASE, after: BASE + ' I counted forty bees.'});
  const batch = await after.commitAll();
  assert.equal(app.server.posts.length, 1, 'one request');
  assert.equal(app.server.posts[0].placement, 'insert');
  assert.equal(app.server.posts[0].source, 'click-type', 'the author path, through the same door');
  assert.deepEqual(app.server.inserted, [BASE + ' I counted forty bees.']);
  assert.equal(batch.applied.length, 1);
  assert.equal(after.P.size, 0);
});

// The record's item 2: a retained draft whose paragraph another writer rewrote meanwhile is shown IN its
// paragraph as unsaved, not held in a review box; his explicit save writes it over the current span.
test('a reloaded draft whose source another writer rewrote stands in its paragraph as unsaved, and one save makes the file equal it', async () => {
  const app = owner();
  const before = page(app);
  before.type('p1', ' Wind on Friday.');
  app.server.tex.set('p1', BASE.replace('short, evidence-based', 'brief') + ' (Revised elsewhere.)');
  const after = page(app);
  const entry = after.P.get('p1');
  assert.ok(entry, 'found in its own paragraph by its words');
  assert.equal(entry.moved, true);
  assert.equal(!!entry.unplaced, false, 'not in the held-drafts box');
  assert.equal(entry.review, undefined, 'no review hold');
  assert.equal(after.faces.get('p1'), BASE + ' Wind on Friday.', 'his whole draft is on the face');
  // the opt-in autosave does not write it; his explicit save does, once
  after.snapshotEdit(after.byId.get('p1'), after.byId.get('p1').bodyEl);
  assert.equal(after.E.moved, true);
  assert.equal(await after.commitEdit('autosave'), null);
  assert.equal(app.server.posts.length, 0);
  await after.commitAll();
  assert.equal(app.server.posts.length, 1);
  assert.equal(app.server.tex.get('p1'), BASE + ' Wind on Friday.', 'the file equals his draft');
  assert.equal(app.server.posts[0].before, BASE.replace('short, evidence-based', 'brief') + ' (Revised elsewhere.)', 'written over the span as the file holds it now');
  // Show the other version: the current source beside the paragraph, nothing saved
  const second = page(owner(new Map(after.storage), {p1: BASE + ' (Revised.)', p2: OTHER}));
  assert.equal(second.showOtherVersion(), false, 'no moved draft, nothing to show');
});

// The record's item 2, the storage shape: a row the BASE client (60c376fe9) persisted, keys exactly as its
// localDraftRows wrote them (captured in wave14b/editor-saves-finish/before/base-draft.json), including the
// review hold an earlier build stored, loads into this build as a moved draft in its paragraph.
test('a draft row in the base client\'s storage shape, with its stored review hold, loads as an unsaved draft in its paragraph', async () => {
  const storage = new Map([['walk-parks:garden-study', JSON.stringify([['p1', {expectedSelection: 'sel-1', draft_id: '56caa91c-base', pristine: BASE,
    text: BASE + ' A fourth turning.', scope: '', note: '', src: {file: 'chapter.tex', lineStart: 4, lineEnd: 4}, tex: BASE, expected: [tok(BASE)],
    awaiting: null, supersedes: null, review: 'source-changed', noteOnly: false, unplaced: false, conflict: false, pendingRow: '', text_at_bank: ''}]])]]);
  const app = owner(storage, {p1: BASE + ' (Rewritten by an agent.)', p2: OTHER});
  const p = page(app);
  const entry = p.P.get('p1');
  assert.equal(entry.moved, true);
  assert.equal(entry.review, undefined);
  assert.equal(p.faces.get('p1'), BASE + ' A fourth turning.');
  assert.equal(p.showOtherVersion(), true);
  const panel = p.panels.at(-1);
  assert.match(panel.kids[0].text, /^The other version of your paragraph at chapter\.tex:4, as the file holds it now$/);
  assert.equal(panel.kids.find(node => node.tag === 'textarea').value, BASE + ' (Rewritten by an agent.)', 'what the file holds now, beside his kept text');
  assert.equal(p.faces.get('p1'), BASE + ' A fourth turning.', 'nothing saved or changed: his draft stays in its paragraph');
  assert.deepEqual(p.cards.filter(card => card.tone === 'refused'), []);
  await p.commitAll();
  assert.equal(app.server.tex.get('p1'), BASE + ' A fourth turning.');
  const stored = p.stored();
  assert.deepEqual(stored, [], 'saved: the row is gone from the same key');
});

// 9 November, his retained paragraph: a park carried across a reload keeps the source it was typed against
// (`entry.tex`), and the frame line's Keep my text and save it (commitAll, no click into the paragraph) sends it
// WITHOUT a fresh snapshot. The splice must then be made against that older source, not the block's newer one:
// against the newer one his quote has no home, the save falls back to the bare quote, is labelled unplaced and
// is refused at the byte gate (the 409 he met after the restart). Spliced against his own basis, `before` is
// the paragraph he edited, the owner relocates it and his text wins, the newer bytes superseded (ruling 1).
test('Keep on the frame line saves a reloaded draft over a paragraph another writer rewrote, as the author path', async () => {
  const storage = new Map([['walk-parks:garden-study', JSON.stringify([['p1', {expectedSelection: 'sel-1', draft_id: '7e1a-keep', pristine: BASE,
    text: BASE + ' It occurs to me a year has passed.', scope: '', note: '', src: {file: 'chapter.tex', lineStart: 4, lineEnd: 4}, tex: BASE, expected: [tok(BASE)],
    awaiting: null, supersedes: null, review: '', noteOnly: false, unplaced: false, conflict: false, pendingRow: '', text_at_bank: ''}]])]]);
  const rewritten = BASE.replace('short, evidence-based', 'brief') + ' (Saved earlier by the editor itself.)';
  const app = owner(storage, {p1: rewritten, p2: OTHER});
  const p = page(app);
  // the park as a build before this one left it on the page: his words on the face, pristine and basis still the
  // source he typed against (not re-based onto the block's newer source), standing on its paragraph
  const carried = p.P.get('p1') || p.P.get('held:p1');
  assert.ok(carried, 'the draft is on the page');
  p.P.delete('held:p1'); p.P.set('p1', {...carried, pristine: BASE, tex: BASE, moved: false, unplaced: false, place: null});
  p.faces.set('p1', BASE + ' It occurs to me a year has passed.'); p.byId.get('p1').bodyEl.textContent = BASE + ' It occurs to me a year has passed.';
  const batch = await p.commitAll();       // the frame line's Keep, no snapshot of the paragraph first
  assert.equal(app.server.posts.length, 1, 'one request');
  assert.equal(app.server.posts[0].source, 'click-type', 'the author path, not click-type-unplaced');
  assert.equal(app.server.posts[0].before, BASE, 'spliced against the source he typed against');
  assert.equal(app.server.posts[0].blockId, 'p1', 'the paragraph id rides for the owner to relocate by');
  assert.equal(app.server.tex.get('p1'), BASE + ' It occurs to me a year has passed.', 'the file equals his draft');
  assert.deepEqual(app.server.superseded, [rewritten], 'the newer bytes are recorded as superseded, not a refusal');
  assert.equal(batch.applied.length, 1);
  assert.equal(batch.refused.length, 0);
  assert.equal(p.P.size, 0);
});
