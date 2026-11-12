// The save line (wave WRITING-FRONTEND-REPAIRS-W3, packet save-line; the 5 November brief's A2, A3, A4).
// These tests drive the REAL walk functions, sliced verbatim from the walk's owner modules: commitEdit and the
// draft owner's park, basis and settlement functions (as tests/save_safety.test.mjs does), plus the save line
// itself (walk.mjs noteSaveOutcome and saveLine), against a stand-in owner that keeps one source line per
// paragraph. Every event commitEdit emits reaches the line exactly as the walk's own listener sends it. The
// browser proof is the packet's scenarios (scenario-states.mjs walks all six states on screen).
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {continuedEdit, emptyParagraphSource, matchHeldDraft, mergeDraftRows, normalizeDraftRows, createManuscriptRefresh} from '../src/laplace/web/static_shared/manuscript-editing.mjs';
import {sourceEffectDisposition} from '../src/laplace/web/static_shared/source-effect.mjs';
import {documentChips} from '../src/laplace/web/static_shared/workspace-presentation.mjs';
import {walkDeclarations} from './helpers/walk_source.mjs';

const code = walkDeclarations('expectedOf', 'captureBasis', 'assignBasis', 'basisOf', 'verifyAwaiting', 'markSubmitted',
  'settleSubmission', 'readdressDraft', 'awaitingUnread', 'REVIEW_WORDS', 'MOVED_WORDS', 'placeDraft', 'draftSource', 'placeOf', 'keepUnplaced',
  'restoreFace', 'restoreParked',
  'parkEntry', 'parkEdit', 'clearEdit', 'snapshotEdit', 'PARK_KEY', 'parksLoaded', 'localDraftRows', 'saveParks', 'loadParks',
  'spanOf', 'ownerView', 'appliedOf', 'pendingOf', 'INFLIGHT', 'NOT_SAVED', 'sayNotSaved', 'NOT_LOCATED', 'NOT_LOCATED_LINE', 'keepPlace', 'commitEdit', 'ownParagraph',
  'SAVE_LAST', 'clockTime', 'plainReason', 'noteSaveOutcome', 'saveLine');
const NAMES = ['E', 'P', 'D', 'F', 'S', 'C', 'OWNER_READ', 'blockById', 'hostText', 'srcOf', 'applyFace', 'replaceByContext', 'showCard', 'hideCard', 'emit',
  'paintParked', 'setEditScope', 'autosize', 'cardNote', 'window', 'crypto', 'storageRecovered', 'storageFailure', 'paintHeldDrafts',
  'matchHeldDraft', 'mergeDraftRows', 'normalizeDraftRows', 'continuedEdit', 'emptyParagraphSource', 'sourceEffectDisposition',
  'RELOAD_INFLIGHT', 'structuralSourceHolds', 'showStructuralOutcome', 'pendingPresentationSplits', 'taggedParagraph', 'offsetIn', 'askActor',
  'sourceForRenderedRange', 'pieceTypeAt', 'anchorFromPristine', 'sourceRequest', 'toSourceRegister', 'headSpan', 'rewritePayload',
  'setPayload', 'commitPresentationSplit', 'saveSourceChange', 'reloadBlock', 'admit', 'MINTED', 'ledgerPath', 'srcSpanWords', 'receiptWords',
  'settleRail', 'renderComposer', 'renderBand', 'paintDeposits', 'focusSplitParagraph', 'captureFocus', 'renderBlockBody', 'paintMarks',
  'measure', 'restoreFocus', 'dropArmedMark', 'docEl', 'paragraphTransition', 'armAutosave'];

const BASE = 'Compare watering observations and write a short, evidence-based account.';
const tok = tex => 'tok:' + tex;
const TIME = /^\d\d:\d\d$/;

// The stand-in owner (as in save_safety.test.mjs): one source line per paragraph, an identity token per exact
// bytes; `unapplied` answers without applying or holding, `pending` holds the words as a pending row whose
// retry was refused with the owner's real state-not-reached sentence.
function owner(storage = new Map()) {
  const server = {tex: new Map([['p1', BASE]]), mode: 'apply', down: false, posts: [], held: [], ids: 0};
  server.save = async payload => {
    server.posts.push(structuredClone(payload));
    if (server.down || server.mode === 'fail') throw new TypeError('Failed to fetch');
    if (server.mode === 'refuse') throw Object.assign(Error("fetchJSON POST /review/adjudicate?corpus=garden-study → 422: cannot stage the rewrite of chapters/chapter-01.tex: [Errno 13] Permission denied: '/tmp/x/chapter-01.tex.rewriteswap'"),
      {status: 422, body: {error: "cannot stage the rewrite of chapters/chapter-01.tex: [Errno 13] Permission denied: '/tmp/x/chapter-01.tex.rewriteswap'", reason: 'stage-failed'}});
    server.ids += 1;
    if (server.mode === 'unapplied') return {ok: true, pending: false, applied: null, record: {id: 'FB-' + server.ids, ts: '2026-11-05T22:00:00', kind: 'author-rewrite'}};
    if (server.mode === 'pending') return {ok: true, pending: true, applied: null, record: {id: 'FB-' + server.ids, kind: 'pending-rewrite'},
      retry_refused: 'The source at chapters/chapter-01.tex:4-4 changed where you were editing, so nothing was written: your edit and the other one touch the same characters.'};
    server.tex.set(payload.blockId, payload.after);
    const answer = {ok: true, pending: false, applied: {file: 'chapter.tex'}, record: {id: 'FB-' + server.ids, ts: '2026-11-05T22:00:00', anchor: {after: payload.after}}};
    if (server.mode === 'lose') throw new TypeError('Failed to fetch');
    if (server.mode === 'hold') return new Promise(release => server.held.push(() => release(answer)));
    return answer;
  };
  server.release = () => { for (const release of server.held.splice(0)) release(); };
  return {server, storage};
}

function page({server, storage}) {
  const faces = new Map(), events = [], arms = [];
  const blocks = [...server.tex.keys()].map((id, i) => ({id, kind: 'para', tex: server.tex.get(id), expected: [tok(server.tex.get(id))], readSeq: 1,
    src: {file: 'chapter.tex', line_start: 4 + 2 * i, line_end: 4 + 2 * i}, el: {dataset: {}}, pieceMap: []}));
  for (const b of blocks) { b.bodyEl = {id: b.id}; faces.set(b.id, b.tex); }
  const E = {blockId: '', pristine: '', tex: '', src: null, expectedSelection: undefined, expected: null, awaiting: null, supersedes: null,
    moved: false, place: null, dirty: false, timer: 0, committing: false, composing: false, scope: '', selAnchor: null, historyGroup: null};
  const bindings = {E, P: new Map(), D: {sourceObservation: {source_observation: {selection_identity: 'sel-1'}}}, F: {blockId: '', saving: false},
    S: {blocks, corpus: 'garden-study'}, C: {actor: 'author', mine: new Set()}, OWNER_READ: {seq: 1}, blockById: new Map(blocks.map(b => [b.id, b])),
    hostText: host => faces.get(host.id), srcOf: b => ({file: b.src.file, lineStart: b.src.line_start, lineEnd: b.src.line_end}),
    applyFace: (b, entry) => { faces.set(b.id, entry.text); return true; }, replaceByContext: () => false,
    showCard() {}, hideCard() {}, emit: (name, detail) => { events.push([name, detail]); if (name === 'bank' || name === 'save-outcome') api.noteSaveOutcome(name, detail); },
    paintParked: () => bindings.saveParks(), setEditScope() {}, autosize() {}, cardNote: null,
    window: {localStorage: {getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key)}},
    crypto: {randomUUID: () => 'draft-' + Math.random().toString(36).slice(2)}, storageRecovered() {}, storageFailure: (_, error) => { throw error; },
    paintHeldDrafts() {}, matchHeldDraft, mergeDraftRows, normalizeDraftRows, continuedEdit, emptyParagraphSource, sourceEffectDisposition,
    RELOAD_INFLIGHT: null, structuralSourceHolds: new Map(), showStructuralOutcome() {}, pendingPresentationSplits: new Map(), taggedParagraph: () => false,
    offsetIn: () => 0, askActor() {}, sourceForRenderedRange: (b, start, end) => faces.get(b.id).slice(start, end), pieceTypeAt: () => 'text',
    anchorFromPristine: (b, full, start, end) => ({file: b.src.file, lineStart: b.src.line_start, lineEnd: b.src.line_end, blockId: b.id, sectionId: '',
      quote: full.slice(start, end), start, end, full}),
    sourceRequest: parts => parts, toSourceRegister: value => value, headSpan: () => null,
    rewritePayload: (a, typed, note, expected) => ({file: a.file, lineStart: a.lineStart, lineEnd: a.lineEnd, blockId: a.blockId,
      before: a.full, after: a.full.slice(0, a.start) + typed + a.full.slice(a.end), note, expected}),
    setPayload: (body, key, value) => { body[key] = value; return body; }, commitPresentationSplit: async () => null,
    saveSourceChange: payload => server.save(payload),
    admit: () => true, MINTED: new Set(), ledgerPath: () => 'ledger', srcSpanWords: () => 'chapter.tex', receiptWords: () => '', settleRail() {},
    renderComposer() {}, renderBand() {}, paintDeposits() {}, focusSplitParagraph: async () => {}, captureFocus: () => null,
    renderBlockBody: b => faces.set(b.id, b.tex), paintMarks() {}, measure() {}, restoreFocus() {}, dropArmedMark() {},
    docEl: {querySelectorAll: () => []}, paragraphTransition: null,
    // the autosave's 900 ms timer (walk-edit-input.mjs armAutosave): counted, never fired on its own; since wave 14a
    // nothing in the save path arms it (it is armed only by his input, and only when he turned Autosave on)
    armAutosave: () => arms.push(faces.get(E.blockId))};
  const read = b => { b.tex = server.tex.get(b.id); b.expected = [tok(b.tex)]; b.readSeq = bindings.OWNER_READ.seq; };
  // walk-document.mjs `_reloadBlock`, in-place path (as in save_safety.test.mjs)
  bindings.reloadBlock = async id => {
    if (server.down) return {ok: false, note: 'the doc model door did not answer for the re-render. Failed to fetch'};
    if (server.readGate) await server.readGate;
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
    return {captureBasis, assignBasis, restoreFace, parkEdit, snapshotEdit, saveParks, loadParks, commitEdit, parkEntry,
      noteSaveOutcome, saveLine, plainReason, SAVE_LAST};`)(bindings);
  const self = {
    ...api, E, P: bindings.P, F: bindings.F, faces, events, arms, server, storage,
    type(id, words) {
      const b = bindings.blockById.get(id);
      if (E.blockId !== id) api.snapshotEdit(b, b.bodyEl);
      faces.set(id, faces.get(id) + words);
      E.dirty = faces.get(id) !== E.pristine;
      if (E.dirty) bindings.P.set(id, api.parkEntry(b, b.bodyEl, faces.get(id))); else bindings.P.delete(id);
      bindings.saveParks();
    },
    load() { bindings.OWNER_READ.seq += 1; for (const b of blocks) { read(b); faces.set(b.id, b.tex); } api.loadParks(); },
    word: () => api.saveLine()?.word ?? null,
    line: () => api.saveLine(),
  };
  self.load();
  return self;
}
const tick = () => new Promise(ok => setTimeout(ok, 0));

test('Saved is shown only after the owner confirms those bytes', async () => {
  const o = owner(), p = page(o);
  assert.equal(p.word(), null, 'nothing is claimed before any edit');
  p.type('p1', ' Rain fell on Tuesday.');
  assert.equal(p.word(), 'Unsaved changes');
  o.server.mode = 'hold';
  const saving = p.commitEdit('autosave'); await tick();
  assert.equal(p.word(), 'Saving', 'a request is out: the bytes may be on disk, but the owner has not confirmed them');
  assert.notEqual(p.word(), 'Saved');
  o.server.release(); await saving;
  assert.equal(p.word(), 'Saved');
  assert.match(p.line().detail, TIME, 'Saved carries hours and minutes');
  assert.equal(o.server.tex.get('p1'), BASE + ' Rain fell on Tuesday.');

  // an answer that neither applied nor held the words is not Saved, and the words stay (ruling 5)
  p.type('p1', ' Wind on Friday.');
  o.server.mode = 'unapplied';
  await p.commitEdit('autosave');
  assert.equal(p.word(), 'Not saved');
  assert.equal(p.faces.get('p1'), BASE + ' Rain fell on Tuesday. Wind on Friday.', 'his words stay on the paragraph');
  assert.equal(p.E.dirty, true);
  assert.equal(p.P.get('p1').text, BASE + ' Rain fell on Tuesday. Wind on Friday.', 'and in the park, as an unsaved draft');
  assert.deepEqual(p.E.expected, [tok(BASE + ' Rain fell on Tuesday.')], 'on its own basis, so the next save sends it');
  o.server.mode = 'apply';
  await p.commitEdit('autosave');
  assert.equal(o.server.tex.get('p1'), BASE + ' Rain fell on Tuesday. Wind on Friday.');
  assert.equal(p.word(), 'Saved');

  // a banked comment does not speak for the manuscript (ruling 4)
  p.type('p1', ' Sun.');
  p.noteSaveOutcome('bank', {shape: 'comment', applied: false, pending: false});
  assert.equal(p.word(), 'Unsaved changes');
});

test('reload restores an unsaved draft and says it is unsaved', async () => {
  const o = owner(), before = page(o);
  before.type('p1', ' Rain fell on Tuesday.');
  const after = page(o);   // the same browser storage, a fresh page
  assert.equal(after.P.size, 1);
  assert.equal(after.P.get('p1').text, BASE + ' Rain fell on Tuesday.');
  assert.equal(after.word(), 'Unsaved changes');
  assert.equal(o.server.tex.get('p1'), BASE);
});

test('Unsaved changes: unsent words in the active edit or a park', () => {
  const p = page(owner());
  p.type('p1', ' Rain.');
  assert.equal(p.E.dirty, true);
  assert.deepEqual(p.line(), {word: 'Unsaved changes', detail: '', tone: 'attention', text: 'Unsaved changes', full: 'Unsaved changes'});
});

test('Saving: E.committing, a flip saving, or a submitted draft whose request is still open', async () => {
  const o = owner(), p = page(o);
  p.type('p1', ' Rain.');
  o.server.mode = 'hold';
  const saving = p.commitEdit('autosave'); await tick();
  assert.equal(p.E.committing, true);
  assert.equal(p.word(), 'Saving');
  // a refresh parks the edit while the request is out (save-trace C7): still Saving
  p.parkEdit({id: 'p1', el: {dataset: {}}, bodyEl: {id: 'p1'}});
  assert.equal(p.E.committing, false);
  assert.equal(p.P.get('p1').awaiting.inflight, true);
  assert.equal(p.word(), 'Saving');
  o.server.release(); await saving;
  p.F.saving = true; assert.equal(p.word(), 'Saving'); p.F.saving = false;
});

test('no answer (wave 14a): Not saved in plain words with the text kept and nothing read back; his next save writes it once, then Saved', async () => {
  const o = owner(), p = page(o);
  p.type('p1', ' Rain fell on Tuesday.');
  o.server.mode = 'lose';
  await p.commitEdit('autosave');
  assert.equal(p.word(), 'Not saved');
  assert.equal(p.line().detail, 'No answer from the engine; your text is kept');
  assert.equal(p.faces.get('p1'), BASE + ' Rain fell on Tuesday.');
  assert.equal(p.E.awaiting, null, 'no read-back is pending (save-trace C1 is gone for the author path)');
  o.server.mode = 'apply';
  p.type('p1', ' Wind on Friday.');
  await p.commitEdit('ctrl-s');
  assert.equal(o.server.tex.get('p1'), BASE + ' Rain fell on Tuesday. Wind on Friday.');
  assert.equal(p.word(), 'Saved');
  assert.match(p.line().detail, TIME);
});

test('a stopped engine: Not saved, never Saving or Saved; the text is kept and saved by his next save', async () => {
  const o = owner(), p = page(o);
  p.type('p1', ' Rain fell on Tuesday.');
  o.server.down = true;
  await p.commitEdit('autosave');
  assert.equal(p.word(), 'Not saved');
  assert.equal(p.faces.get('p1'), BASE + ' Rain fell on Tuesday.');
  o.server.down = false; o.server.mode = 'apply';
  p.type('p1', ' Wind on Friday.');
  await p.commitEdit('ctrl-s');
  assert.equal(o.server.tex.get('p1'), BASE + ' Rain fell on Tuesday. Wind on Friday.');
  assert.equal(p.word(), 'Saved');
});

test('Not saved: the owner refused, in its own plain words; the text is kept', async () => {
  const o = owner(), p = page(o);
  p.type('p1', ' Wind on Friday.');
  o.server.mode = 'refuse';
  await p.commitEdit('autosave');
  const line = p.line();
  assert.equal(line.word, 'Not saved');
  assert.equal(line.detail, 'Cannot stage the rewrite of chapters/chapter-01.tex: Permission denied; your text is kept');
  assert.doesNotMatch(line.text, /fetchJSON|adjudicate|422|Errno|\/tmp/, 'no route, status code or internal term');
  assert.equal(p.faces.get('p1'), BASE + ' Wind on Friday.');
  // no answer at all is Not saved too, said as that
  const q = page(owner());
  q.type('p1', ' Rain.');
  q.server.save = async () => { throw new TypeError('Failed to fetch'); };   // nothing reached the file
  await q.commitEdit('autosave');
  assert.equal(q.word(), 'Not saved');
  assert.match(q.line().detail, /^No answer from the engine; your text is kept/);
});

test('Conflict: his words held as pending beside the current source, with the owner reason', async () => {
  const o = owner(), p = page(o);
  p.type('p1', ' Rain.');
  o.server.mode = 'pending';
  await p.commitEdit('autosave');
  assert.equal(p.P.get('p1').pendingRow, 'FB-1');
  const line = p.line();
  assert.equal(line.word, 'Conflict');
  assert.equal(line.text, 'Conflict · your text is kept here and the current source in the file');
  assert.match(line.full, /your edit and the other one touch the same characters$/);
  assert.doesNotMatch(line.full, /:4-4/);
  assert.equal(p.faces.get('p1'), BASE + ' Rain.');
  assert.equal(o.server.tex.get('p1'), BASE, 'the current source is kept in the file');
});

test('later words typed while a save was out stay an unsaved draft until his next save; nothing is armed or sent on its own (wave 14a, ruling 2)', async () => {
  const o = owner(), p = page(o);
  p.type('p1', ' Rain fell on Tuesday.');
  o.server.mode = 'hold';
  const first = p.commitEdit('ctrl-s'); await tick();
  p.type('p1', ' Wind on Friday.');
  o.server.release(); await first;
  const settled = p.events.filter(([name]) => name === 'save-settled');
  assert.equal(settled.length, 1, 'the settled save announces itself');
  assert.equal(p.E.blockId, 'p1'); assert.equal(p.E.dirty, true); assert.equal(p.E.committing, false);
  assert.equal(p.faces.get('p1'), BASE + ' Rain fell on Tuesday. Wind on Friday.', 'the reply does not touch the later words');
  assert.deepEqual(p.arms, [], 'the save path arms nothing');
  assert.equal(o.server.posts.length, 1, 'and sends nothing more on its own');
  assert.equal(p.word(), 'Unsaved changes');
  o.server.mode = 'apply';
  await p.commitEdit('ctrl-s');
  assert.equal(o.server.posts.at(-1).before_content, BASE + ' Rain fell on Tuesday.', 'guarded by what the first save wrote');
  assert.equal(o.server.tex.get('p1'), BASE + ' Rain fell on Tuesday. Wind on Friday.', 'each sentence once, in typed order');
});

test('a read issued before a newer adopted read is stale (walk-document.mjs issueRead/staleRead)', () => {
  const OWNER_READ = {seq: 0};
  const {issueRead, staleRead, adoptedRead} = new Function('OWNER_READ', walkDeclarations('issueRead', 'staleRead', 'adoptedRead')
    + ';return {issueRead, staleRead, adoptedRead};')(OWNER_READ);
  const refresh = issueRead(), readBack = issueRead();
  adoptedRead(readBack);
  assert.equal(staleRead(refresh), true, 'the refresh read was issued before the read-back now on the page');
  assert.equal(staleRead(readBack), false);
  assert.equal(staleRead(0), false, 'a document handed in by the host is not ordered here');
});

test('the chip row carries the save line in place of the old Unsaved edits chip', () => {
  const save = {word: 'Saved', detail: '22:56', tone: 'ok', text: 'Saved · 22:56', full: 'Saved · 22:56'};
  assert.deepEqual(documentChips({status: 'NOT_BUILT'}, save).map(chip => chip.label), ['No verified PDF', 'Saved · 22:56']);
  assert.deepEqual(documentChips({status: 'NOT_BUILT'}, true).map(chip => chip.label), ['No verified PDF', 'Unsaved changes']);
  assert.deepEqual(documentChips({status: 'NOT_BUILT'}, null).map(chip => chip.label), ['No verified PDF']);
});

test('his own save read back is not a change elsewhere (save-trace C10)', async () => {
  const statuses = [];
  let walkRevision = 'R0', state = {dirty: true, committing: true, parked: 1, submitted: 1};
  const walk = {ready: () => true, documentVersion: () => 'v-' + walkRevision, sourceObservation: () => ({current_revision: walkRevision}), editState: () => state};
  const answers = [{project: 'p', current_revision: 'R1', source_observation: {schema_version: 'laplace.manuscript-source-observation/1'}},
    {project: 'p', unchanged: true, summary_revision: 'S1'}];
  const refresh = createManuscriptRefresh({read: async () => ({ok: false}), observe: async () => answers.shift(), project: 'p', getWalk: () => walk,
    visible: () => true, status: text => statuses.push(text), schedule: () => 0, cancel() {}});
  await refresh.check();
  assert.deepEqual(statuses, [], 'while his save is out the reading view waits without the notice');
  walkRevision = 'R1'; state = {dirty: true, committing: false, parked: 1, submitted: 0};   // read back; later words remain
  await refresh.check();
  assert.deepEqual(statuses, [], 'the owner has not moved since and the canvas holds that revision');
});

test('the frame line repeats the save line and says nothing for a comment (save-trace C4, C4b; ruling 4)', () => {
  const panel = readFileSync(new URL('../src/laplace/web/static_shared/writing-panel.mjs', import.meta.url), 'utf8');
  const handler = panel.slice(panel.indexOf("window.walk.on('bank',"), panel.indexOf("window.parent.postMessage({type:'laplace:source-saved'}", panel.indexOf("window.walk.on('bank',")));
  const shown = [];
  const run = new Function('showSave', 'event', handler.slice(handler.indexOf('{') + 1));
  run(() => shown.push('comment'), {applied: false, pending: false, shape: 'comment'});
  run(() => shown.push('unapplied'), {applied: false, pending: false, shape: 'rewrite'});
  run(() => shown.push('applied'), {applied: true, pending: false, shape: 'rewrite'});
  run(() => shown.push('pending'), {applied: false, pending: true, shape: 'rewrite'});
  assert.deepEqual(shown, ['applied', 'pending']);
  assert.doesNotMatch(panel, /textContent='Saved'/, 'no bare Saved without a receipt');
  assert.doesNotMatch(panel, /'Saving…'/, 'no Saving before anything is sent');
});

test('a refused save is not re-sent on its own: the autosave stays unarmed until the next input (ruling 3)', async () => {
  const o = owner(), p = page(o);
  p.type('p1', ' Rain fell on Tuesday.');
  o.server.mode = 'refuse';
  await p.commitEdit('autosave');
  assert.equal(o.server.posts.length, 1);
  assert.equal(p.events.filter(([name]) => name === 'save-settled').length, 1, 'the refusal settles the save');
  assert.equal(p.E.dirty, true, 'his words stay on the page');
  assert.equal(p.faces.get('p1'), BASE + ' Rain fell on Tuesday.');
  assert.match(p.word(), /^Not saved/);
  assert.deepEqual(p.arms, [], 'the refused words alone do not arm the autosave');
  // a word typed while a save was out arms nothing either (wave 14a: only his input arms the opt-in autosave)
  o.server.mode = 'hold';
  const second = p.commitEdit('autosave'); await tick();
  p.type('p1', ' Wind.');
  o.server.release(); await second;
  assert.deepEqual(p.arms, []);
  assert.equal(o.server.posts.length, 2, 'no further request on its own');
});

test('a no-answer save is not re-sent on its own (ruling 3)', async () => {
  const o = owner(), p = page(o);
  p.type('p1', ' Rain fell on Tuesday.');
  o.server.mode = 'fail';
  await p.commitEdit('autosave');
  assert.equal(o.server.posts.length, 1);
  assert.equal(o.server.tex.get('p1'), BASE, 'the file does not have the change');
  assert.equal(p.events.filter(([name]) => name === 'save-settled').length, 1);
  assert.equal(p.E.dirty, true);
  assert.equal(p.faces.get('p1'), BASE + ' Rain fell on Tuesday.', 'his words stay on the page');
  assert.match(p.word(), /^Not saved/);
  assert.deepEqual(p.arms, [], 'the not-landed words alone do not arm the autosave');
});
