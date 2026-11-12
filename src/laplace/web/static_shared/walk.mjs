// THE REDLINE WALK. Purpose: the content-faithful block canvas of the manuscript, the
// rewrite-first composer, the session band and the geometry face behind one door; it runs in the
// Manuscript view's iframe and speaks to the shell through the bridge (HANDLED_BRIDGE_MESSAGES
// in workspace.mjs). Ownership: /walk/doc and the source save routes own the document, pieces,
// blocks and their digests; proposals and citations have their owners (citationReadURL names the
// one citation read). This file is the COMPOSITION ROOT (M5 S2 F8): each walk responsibility has
// one owner module beside it (walk-document, walk-source-client, walk-pieces, walk-blocks,
// walk-media, walk-position, walk-geometry, walk-selection, walk-drafts, walk-edit-history,
// walk-flip, walk-editing, walk-paragraph-ops, walk-edit-input, walk-composer, walk-bank,
// walk-band, walk-card, walk-where, walk-review, walk-controls, over walk-base's dials, handles
// and event sink); docs/writing-source-map.md says where to start, change and test each. Here
// live only the one public api (default export and window.walk, the same instance), the place
// bridge and open(). Public contract: the default export api (the bridge's handlers) and
// citationReadURL (re-exported from walk-source-client.mjs). Inputs: the document read, owner
// receipts, bridge messages; outputs: DOM in the iframe, bridge messages, saves carrying the
// expected digests. Currentness: a refused save is shown through sourceEffectDisposition; the
// shell's conditional summary read covers idle. Storage: sessionStorage laplace:place (reading
// position, memoised for the shell). Colours: the shared tokens through walk.html's aliases.
import {
  manuscriptBlockRows, manuscriptHasDraft, proposalDraftOverlap, recordedProposalAttention
} from "/shared/manuscript-editing.mjs";
import {docEl, emit, emitted, listeners, norm, paper, root, spineNote, text} from './walk-base.mjs';
import {D, blockById, expectedOf, loadContext, loadDoc, paintBadge, reloadBlock} from './walk-document.mjs';
import {
  S, attentionBlockId, blockAtY, buildSpine, captureFocus, fitDocSize, jumpToBlock, jumpToIndex, measure,
  paintZoom, readingY, reallocate, restoreFocus, sectionAtY, setDocSize, setSpan, spanState, updateCurrent
} from './walk-position.mjs';
import {ensureKatex} from './walk-media.mjs';
import {headText} from './walk-pieces.mjs';
import {renderDoc} from './walk-blocks.mjs';
import {G, closeGeometry, openGeometry} from './walk-geometry.mjs';
import {
  C, RULE_SET_ID, arm, armArtefact, armBlockAtReadingLine, armFromSelection, armSpan, autosize,
  compActorInput, compBody, compQuote, disarm, nameActor, renderComposer, setDisposition, setScope, shapeOf,
  updateSuggestion
} from './walk-composer.mjs';
import {anchorForWholeBlock, commentTargetOf, hostText, spliceOf, spliceState, srcOf} from './walk-selection.mjs';
import {
  E, P, clearEdit, loadParks, parkEdit, restoreParked, revertEdit, showOtherVersion
} from './walk-drafts.mjs';
import {
  editorPersistence, rememberExternalApplication, rememberExternalChange, rememberExternalTransaction,
  restoreEditHistory, undoEditorChange
} from './walk-edit-history.mjs';
import {bankDeposit, rewritePayload, undoLast} from './walk-bank.mjs';
import {
  L, RL, admit, checkOrphans, closeLedger, liveRow, openLedger, revokeRow, ruleRow, scopeRow, toggleRedline
} from './walk-band.mjs';
import {F, cancelFlip, flipBlock, focusedBlock, saveFlip} from './walk-flip.mjs';
import {commitAll, commitEdit, editableBlock, ownSavesUnread, prepareForSession} from './walk-editing.mjs';
import {
  armCitationPlacement, caretRange, contextualInsertionPoint, editorInsertionPoint, hideCard,
  insertEditorText, openFindDialog, openReferencePicker, wrapSelection
} from './walk-card.mjs';
import {blockLabels, renderLinkages} from './walk-where.mjs';
import {
  atomicOwner, beginObjectMove, deleteBlock, deleteObject, insertHeading, paragraphTransition
} from './walk-paragraph-ops.mjs';
import {wireEditor} from './walk-edit-input.mjs';
import {wireComposer, wireControls} from './walk-controls.mjs';
import {
  authorChangesEnabled, clearProposal, manuscriptDraftRanges, proposalView, refreshAuthorChanges,
  refreshProposalView, setAuthorChanges, showProposal
} from './walk-review.mjs';
// walk.mjs — the redline walk. The content-faithful block canvas, the rewrite-first
// composer, the session band, and the geometry face behind one door.
//
// The clean room (DESIGN_2026-08-10 §"The clean room", widened by the M5 writing modules): the walk's
// own owner modules (walk-*.mjs, all static) and, among them, 7 shared modules (store.mjs, the one fetch
// gateway; source-effect, manuscript-source-client, reader-restructure, writing-owner-read,
// manuscript-editing, proposal-resolution), writing-artifact.mjs imported lazily for link reads, and the
// vendored pdf.js/KaTeX. It never touches engine.mjs, shell.js, inspector.js, hymn.css or any
// *-panes.mjs; document truth arrives through HTTP owners only (/walk/doc, the source save routes, owner reads).
//
// ─ THE BRIDGE CONTRACT (M5 C2, plan §4 bridge_contract; the same header is in
//   writing-panel.mjs) — what crosses between this iframe and the workspace shell ─────────
//
//   A  messages iframe → shell (window.parent.postMessage, same origin; the shell accepts
//      only event.source === the manuscript iframe and counts every type in
//      window.laplaceBridge). Produced here: laplace:open-owner-read, laplace:open-project-
//      artifact, laplace:place (new: the reading place, debounced 100 ms, embedded only).
//      Produced by writing-panel.mjs: laplace:discuss-selection, laplace:engine-unavailable,
//      laplace:logical-context, laplace:open-document-pdf, laplace:open-document-source, laplace:queued-request,
//      laplace:source-outcome, laplace:source-saved, laplace:source-warning. Produced by
//      store.mjs: laplace:engine-unavailable. Handled by the shell but with NO producer in
//      this tree: laplace:focus-manuscript, laplace:show-sections, laplace:read-origin-turn —
//      retained with counters until root observes them in use or sees zero after pilots;
//      their reachability is UNRESOLVED here, not inferred from a grep.
//   B  messages shell → iframe: none. The shell drives the walk through C.
//   C  direct commands shell → walk (window.walk = api below): the public surface, plus
//      setReturnMode(mode) — 'cross-view' demotes the spine door while the shell holds a
//      cross-view return — and the subscriber/emission ledgers subscribers()/emitted().
//      M5 C7 adds redoEdit beside undoEdit to the shell's set: the editor band
//      (manuscript-editor.mjs) carries Undo/Redo; the iframe menu no longer does.
//   D  events (api.on/off): span, section, ready, bank, attention, edit-settled, document,
//      editor-status, source-change-saved. source-change-saved has NO subscriber in this
//      tree; it is retained and counted in emitted() until root's observation.
//   E  document events: laplace-source-effect, laplace-workspace-navigation,
//      laplace-workspace-connection (window CustomEvents dispatched by the shell) and the
//      storage event for the shared proposal-draft key.
//   F  shared browser keys: the proposal draft key and the three editor preference keys
//      are preserved verbatim; the shell preserves laplace:workspace:nav-closed,
//      laplace:workspace:session-open, conversation-width and composer-height.
//   G  boot: the iframe is /walk?corpus=<project>&embedded=1 (walk.html served by walk.py,
//      which links /shared/tokens.css and never the legacy shell script); the embedded
//      boot path in writing-panel.mjs is bootEmbedded().
//
// ─ THE CANVAS (his representation ruling, 2026-08-10) ────────────────────────────────────
//
//   the pdf is not the working canvas. The working canvas is the content-faithful source
//   PROJECTION: sections and blocks in document order, built server-side from the fragment
//   files and the build artifacts, served at GET /walk/doc. Words, math, figures and order
//   are faithful; geometry — line breaks, page breaks, floats — is deferred to the typeset
//   face, which is the named review pdf behind ONE head door.
//
//   raw tex never appears in the right rail. The composer holds the PASSAGE in his own
//   reading register, editable — the rewrite is the primary gesture. Source appears only
//   IN PLACE, at the block, invited by `s`, and goes away again on Esc.
//
//   the session band holds this walk's deposits and nothing else. It never renders the
//   project's ledger history: a band that shows 392 historical rows as this walk's appends
//   is a broken echo, and the echo law does not bend.
//
// ─ the geometry laws, re-grounded on the block canvas ────────────────────────────────────
//
//   G1 the focal point is pinned. Every layout reallocation (the rail widening, the spine
//      opening, a reading-size change, a block re-rendering under him) captures the block
//      at the reading line and the fraction down it, re-lays out, then SOLVES the scroll so
//      that point sits back at the same viewport position. `captureFocus`/`restoreFocus`.
//   G2 the reading size never changes implicitly. The column's width is stated in `em`, so
//      for a given size it is a FIXED pixel width: reallocation changes the MARGINS around
//      the column, never the column, and the text never reflows mid-read. Past the margins
//      the pane pans. `--doc-size` moves only through his dial.
//   G3 jumps land with context: a plain continuous scroll to the block or section head,
//      landing in the upper third, lit briefly, its spine row staying lit.
//   G4 a jump is a visit: every jump mints the named return door ("back to §Coverage");
//      the door — or Esc — returns along the same continuous path.
//   G5 the spine opens oriented to now: re-opening scrolls the current row into view.
//   G6 panes take what they need within bounded maxima; an empty band claims nothing.
//
// ─ the public surface (a machine walk drives exactly the doors his keys reach) ───────────
//
//   window.walk = { doc(), blocks(), sections(), current(), span(), armed(), bank(), … }

// `historyReplacement` is NOT imported (WRITING-CONSOLIDATION-W1): the storage-latency
// lane's undo calls `historySpan`, and the whole-file view of the same answer has no
// caller in the product any more. It stays exported for `tests/manuscript_editing.test.mjs`,
// which asserts the property that makes the hunk safe -- the door's splice at the span
// equals the whole-file replacement -- and an import nothing calls is the mechanism left
// standing beside its replacement.

// ═════════════════════════════════════════════════════════════════════════════════════════
// 19 · the public surface — a machine walk drives exactly the doors his keys reach
// ═════════════════════════════════════════════════════════════════════════════════════════

// Opt-in keyboard place over the existing scroll bridge. A place contains only
// block identity/version and caret offsets, never a retained DOM node or range.
function capturePlaceFocus({keyboard=false}={}){
  const position=captureFocus();if(!keyboard)return position;
  const point=editorInsertionPoint(),active=document.activeElement,focused=S.blocks.find(block=>block.bodyEl&&(block.bodyEl===active||block.bodyEl.contains(active))),blockId=focused?.id||(!point?.source&&point?.blockId)||null;
  return {...position,keyboard:{version:D.documentVersion,blockId,caret:point&&!point.source&&point.blockId===blockId?{start:point.start,end:point.end}:null}};
}
function restorePlaceFocus(place,{keyboard=false,isCurrent=()=>true}={}){
  const held=place?.keyboard;if(!isCurrent()||keyboard&&held&&(held.version==null||held.version!==D.documentVersion))return false;restoreFocus(place);if(!keyboard||!held)return false;
  const block=held.blockId?blockById.get(held.blockId):null,target=held.blockId?block?.bodyEl:paper;if(!target||target.isConnected===false)return false;
  target.focus({preventScroll:true});if(block&&held.caret&&editableBlock(block)){const selection=document.getSelection();if(selection){selection.removeAllRanges();selection.addRange(caretRange(target,held.caret.start,held.caret.end));}}return true;
}

// THE SAVE LINE (the 5 November brief's A3 and A4; NODE.w3 rulings 1-4; wave 14a/14b): one state for the
// manuscript's own text, in one of five words, derived from the live edit, its parks and the owner's
// last answer. No store and no persistence: the answer is held in memory only (`SAVE_LAST`).
//   Saving           a request is out: the active edit is committing, a flip is saving, or a
//                    submitted draft's request is still open (`awaiting.inflight`)
//   Conflict         the owner holds words as pending (a span the piece map could not place as
//                    prose): they are on the page and in the pending record
//   Not saved        the owner refused (its reason, in plain words) or no answer came; the text is
//                    kept on the page and Keep my text and save it sends it again
//   Unsaved changes  any other unsent words (active edit, parks, flip, proposal draft)
//   Saved            the owner confirmed the bytes: an applied bank event (source effect checked
//                    in `appliedOf`); with the time that confirmation reached the editor
// A save that got no answer reads nothing back (wave 14a ruling 5): it is Not saved, so there is no
// word for an unread outcome.
// A banked comment does not speak for the manuscript (ruling 4).
const SAVE_LAST = {state: '', at: '', reason: ''};
const clockTime = () => { const now = new Date(); return String(now.getHours()).padStart(2, '0') + ':' + String(now.getMinutes()).padStart(2, '0'); };
/** The owner's words, in plain words: no gateway prefix, route, status code or error number. */
function plainReason(reason) {
  if (reason === 'no-answer') return 'The save got no answer and the file does not have this change';
  let text = String(reason || '').replace(/^fetchJSON \S+ \S+ \S+ \d+: /, '').replace(/\[Errno \d+\] /g, '')
    .replace(/: '\/[^']*'/g, '').replace(/ at [\w./-]+:\d+(?:-\d+)?/g, '').replace(/(\.\w+):\d+(?:-\d+)?/g, '$1').replace(/\s+/g, ' ').trim().replace(/[.;:,\s]+$/, '');
  return text ? text[0].toUpperCase() + text.slice(1) : 'The engine did not apply it';
}
/** The owner's last answer, from the walk's own events: an applied bank event, or a save outcome
 *  (sending, not-saved, conflict) that commitEdit emits. */
function noteSaveOutcome(name, event) {
  if (name === 'bank') { if (event && event.applied === true) Object.assign(SAVE_LAST, {state: 'saved', at: clockTime(), reason: ''}); return; }
  Object.assign(SAVE_LAST, {state: event.state, at: event.state === 'saved' ? clockTime() : '', reason: event.reason || ''});
}
for (const name of ['bank', 'save-outcome']) (listeners[name] || (listeners[name] = new Set())).add(event => noteSaveOutcome(name, event));
function saveLine() {
  const entries = [...(E.blockId ? [E] : []), ...P.values()];
  const submitted = entries.filter(entry => entry && entry.awaiting && entry.awaiting.submitted);
  const flipDirty = !!(F.blockId && F.ta && F.ta.value !== (F.baseTex ?? blockById.get(F.blockId)?.tex ?? ''));
  const proposalDirty = [...docEl.querySelectorAll('.proposal-merge-editor')].some(editor => !editor.readOnly && editor.value !== editor.proposalOriginal);
  // `text` is the line itself; `full` adds the owner's longer words (the frame line and the chip's title)
  const line = (word, detail, tone, more = '') => { const text = detail ? word + ' · ' + detail : word; return {word, detail, tone, text, full: more ? text + '. ' + more : text}; };
  if (E.committing || F.saving || submitted.some(entry => entry.awaiting.inflight)) return line('Saving', '', 'running');
  if ([...P.values()].some(entry => entry.pendingRow)) return line('Conflict', 'your text is kept here and the current source in the file', 'blocked',
    SAVE_LAST.state === 'conflict' && SAVE_LAST.reason ? plainReason(SAVE_LAST.reason) : '');
  const unsaved = (E.blockId && E.dirty) || P.size > 0 || flipDirty || proposalDirty || !!paragraphTransition;
  if (unsaved && SAVE_LAST.state === 'not-saved') return line('Not saved', plainReason(SAVE_LAST.reason) + '; your text is kept', 'blocked');
  if (unsaved) return line('Unsaved changes', '', 'attention');
  if (SAVE_LAST.state === 'saved') return line('Saved', SAVE_LAST.at, 'ok');
  return null;
}

const api = {
  dismissEditorCard: hideCard,
  proposalDraftConflict:edit=>proposalDraftOverlap(manuscriptDraftRanges(),edit),
  showProposal,clearProposal,rememberExternalChange,rememberExternalTransaction,deleteObject,beginObjectMove,insertHeading,
  refreshAuthorChanges,setAuthorChanges,authorChangesEnabled:()=>authorChangesEnabled,
  rememberExternalApplication,
  inspection:()=>proposalView?.options?.readOnly&&proposalView.inspectionActive?recordedProposalAttention(proposalView.data):null,
  focusProposal:id=>{let node=[...docEl.querySelectorAll('[data-proposal-ui]')].find(node=>node.dataset.proposalUi===id);if(!node&&
    proposalView?.data.edits?.some(edit=>edit.edit_id===id&&['pending','conflict'].includes(edit.status))){showProposal(proposalView.data,{
    ...proposalView.options,selectedEditId:id});node=[...docEl.querySelectorAll('[data-proposal-ui]')].find(node=>node.dataset.proposalUi===id);}if(
    !node)return false;paper.scrollTop=Math.max(0,node.offsetTop-16);return true;},
  objectKind:id=>atomicOwner(blockById.get(id))?.kind||null,
  editBlock: (id, options={}) => { let b = blockById.get(id); if(options.exact&&(!b||!editableBlock(b)))return false; if (!b || !editableBlock(
    b)) b = S.blocks.find(x => x.sectionId === b?.sectionId && editableBlock(x)); if (!b?.bodyEl) return false; b.bodyEl.focus(); return true; },
  documentVersion:()=>D.documentVersion,
  // The comment target of one paragraph (or a range inside it): an owner-checkable raw interval, never display text.
  commentSelection:(id,range=null)=>{const b=blockById.get(id);return b?commentTargetOf(b,range):{refused:'unmapped',
    reason:'This paragraph is not in the current manuscript view.',choices:[]};},
  // The document's own currentness claim: the owner's revision only while every held section
  // is at its witnessed revision; with a stale held section the claim is withheld (null) and
  // `stale_sections` names them, so a poller re-reads instead of trusting the whole-document token.
  sourceObservation:()=>{const observed=structuredClone(D.sourceObservation);if(observed&&D.staleSections?.size){observed.current_revision=null;
    observed.stale_sections=[...D.staleSections];}return observed;},
  refresh: async (options={}) => {
    const clean=()=>!manuscriptHasDraft(api.editState());
    const version=D.documentVersion;
    if(options.ifClean&&(!clean()||(options.expectedVersion&&options.expectedVersion!==version)))return false;
    if(options.ifClean){await loadContext();if(!clean()||D.documentVersion!==version)return false;}
    if(F.blockId&&F.ta&&F.ta.value!==(F.baseTex??blockById.get(F.blockId)?.tex??'')){emit('editor-status',{
      text:'Source draft preserved. Save or cancel it to refresh the manuscript.'});return false;}
    if(E.blockId&&E.dirty){const current=blockById.get(E.blockId);if(current)parkEdit(current);}
    if(F.blockId)cancelFlip();
    const caret=editorInsertionPoint();
    if(E.blockId&&!E.dirty)clearEdit();
    const focus = captureFocus(), old = focus ? blockById.get(focus.id) : null;
    const anchor = old ? {tex:old.tex, file:srcOf(old).file} : null;
    if(G.pdf){closeGeometry();await G.loadingTask?.destroy?.();G.loadingTask=null;G.pdf=null;G.loaded=false;G.pages=[];}
    if(!options.ifClean)await loadContext();
    if(await loadDoc(options.document)){
      renderDoc();buildSpine();restoreParked();measure();paintBadge();
      if(focus&&anchor){const matches=S.blocks.filter(b=>b.tex===anchor.tex&&srcOf(b).file===anchor.file);if(matches.length===1)focus.id=matches[0].id;}
      restoreFocus(focus);
      if(caret&&!caret.source){const current=blockById.get(caret.blockId);if(current?.bodyEl&&editableBlock(current)){current.bodyEl.focus({
        preventScroll:true});const selection=document.getSelection();selection.removeAllRanges();selection.addRange(caretRange(current.bodyEl,caret.start,caret.end));}}
      await refreshProposalView();
      emit('document',{blocks:S.blocks.length});
      return true;
    }
    return false;
  },
  context: () => S.ctx,
  source: () => S.source,
  doc: () => ({ ok: D.ok, title: D.title, sections: D.sections.length,
                blocks: S.blocks.length, macros: Object.keys(D.macros).length,
                citations: Object.keys(D.citations).length,
                refs: Object.keys(D.refs).length, unknown: D.unknown, note: D.note }),
  // `id` (S2, additive) scopes the projection to one exact block, so a caller that needs one passage's
  // text does not read every block's
  blocks: ({text=true, id=null}={}) => manuscriptBlockRows(id == null ? S.blocks : S.blocks.filter(b => b.id === id),
    text ? b=>b.bodyEl?norm(hostText(b.bodyEl)):'' : null),
  // THE IDENTITY TOKENS THE READ PUBLISHED, per block or all of them: what this canvas will
  // send in `expected`. Exposed as its own accessor rather than folded into `blocks()`,
  // because `manuscriptBlockRows` is the projection the workspace consumes too and a token is
  // not part of a block's FACE. A machine walk asserts the canvas sends a token it READ.
  identities: (id) => (id
    ? expectedOf(blockById.get(id))
    : S.blocks.map((b) => ({ id: b.id, kind: b.kind, tex: b.tex || "",
                             src: { ...srcOf(b), repo_file: (b.src || {}).repo_file || "" },
                             expected: expectedOf(b) }))),
  sections: () => S.sections.map((s) => ({ id: s.id, title: s.title, depth: s.depth,
                                           blocks: s.blocks, cover: s.cover,
                                           dwell: Math.round(s.dwell * 10) / 10 })),
  outline:()=>S.blocks.filter(b=>b.kind==='head').map(b=>({id:b.id,section:b.sectionId,title:b.title||headText(b),label:blockLabels(b)[0]||null,
    number:b.number||blockLabels(b).map(label=>D.refs[label]).find(value=>value!=null&&value!=='')||null,level:b.level,file:b.src.repo_file||srcOf(
    b).file,line_start:srcOf(b).lineStart})),
  current: () => (S.sections[S.current] ? S.sections[S.current].id : null),
  span: () => spanState(),
  clearSpan: () => setSpan(null),
  jumpToSection: (id) => {
    const i = S.sections.findIndex((s) => s.id === id);
    if (i >= 0) jumpToIndex(i);
    return i >= 0;
  },
  jumpToBlock,
  readingPosition: () => {
    const i = S.current >= 0 ? S.current : sectionAtY(readingY());
    const b = blockById.get(attentionBlockId)||S.blocks[blockAtY(readingY())];
    const sec = S.sections.find(section=>section.id===b?.sectionId)||S.sections[i];
    return { sectionId: sec ? sec.id : null, blockId: b ? b.id : null,
             label: sec ? "§" + sec.title : "the top" };
  },
  reallocate,
  captureFocus:capturePlaceFocus, restoreFocus:restorePlaceFocus,
  docSize: () => S.docSize,
  setDocSize,
  ready: () => S.ready,

  // the composer and the band
  actor: () => C.actor,
  nameActor: (v) => { compActorInput.value = String(v || ""); nameActor(); return C.actor; },
  armed: () => (C.armed ? { ...C.armed } : null),
  armSelection: armFromSelection,
  armBlockAtReadingLine,
  armBlock: (id) => { const b = blockById.get(id); if (!b) return false;
                      arm(anchorForWholeBlock(b)); return true; },
  armArtefact, armSpan, disarm,
  setScope: (s, src) => setScope(s, src || "chosen"),
  // the ruling on the passage, through the SAME function the key and the chip both call, so a
  // machine walk asserts the state his hands produce and not a second path to it
  setRuling: (d) => { setDisposition(String(d || "")); return C.disposition; },
  ruling: () => ({ disposition: C.disposition, altitude: C.altitude,
                   expected: C.armed ? expectedOf(blockById.get(C.armed.blockId)) : [] }),
  suggestion: () => C.suggested,
  ruleSet: () => RULE_SET_ID,
  quote: (t) => { if (t != null) { compQuote.value = String(t); renderComposer();
                                   autosize(compQuote, 0.34); } return compQuote.value; },
  body: (t) => { if (t != null) { compBody.value = String(t); updateSuggestion();
                                  renderComposer(); autosize(compBody, 0.26); }
                 return compBody.value; },
  shape: shapeOf,
  bank: bankDeposit,
  undo: undoLast,
  deposits: () => C.rows.map((r) => ({ ...r })),
  // `deposits()` hands out COPIES, so a caller holding one must be resolved back to the
  // live row before a state door touches it — otherwise the door posts and the band never
  // moves, and the echo law is broken for exactly the machine walk that checks it.
  ruleRow: (r, state) => ruleRow(liveRow(r), state),
  revokeRow: (r) => revokeRow(liveRow(r)),
  // the scope-later door, so a machine walk can prove an unscoped row is re-scopable
  // through the SAME append the band's control posts.
  scopeRow: (r, scope) => scopeRow(liveRow(r), scope),
  checkOrphans,

  // click-and-type — the state a machine walk asserts; the gestures themselves are
  // driven as real clicks and keys, exactly the doors his hands reach.
  editState: () => ({ block: E.blockId, dirty: E.dirty||!!(F.blockId&&F.ta&&F.ta.value!==(F.baseTex??blockById.get(F.blockId)?.tex??"")), committing: E.committing||F.saving,
                      scope: E.scope, parked: P.size,transition:!!paragraphTransition,
                      proposal_dirty:[...docEl.querySelectorAll('.proposal-merge-editor')].some(editor=>!editor.readOnly&&editor.value!==editor.proposalOriginal),
                      parkedIds: Array.from(P.keys()), unplaced:[...P.values()].filter(entry=>entry.unplaced).length,
                      // drafts whose source another writer changed while they were away, and paragraphs of his
                      // the file no longer has (walk-drafts.mjs placeDraft, placeOf): facts, never holds
                      moved:[...P.values()].filter(entry=>entry.moved).length,placing:[...P.values()].filter(entry=>entry.place).length,
                      persistence:{...editorPersistence},
                      // words of his own save not yet read back (submitted, awaiting the saved postimage, or a
                      // draft typed on past a save that applied: walk-editing.mjs ownSavesUnread)
                      submitted:[E,...P.values()].filter(entry=>entry&&entry.awaiting).length+ownSavesUnread(),
                      save:saveLine() }),
  commitEdit: () => commitEdit("api"),
  showOtherVersion,
  commitAll,prepareForSession,
  deleteBlock,
  wrapSelection,
  openReferencePicker,contextualInsertionPoint,
  openFind:openFindDialog,
  insertionPoint:editorInsertionPoint,armCitationPlacement,
  insertText:insertEditorText,
  undoEdit:()=>undoEditorChange(false),
  redoEdit:()=>undoEditorChange(true),
  restoreEditHistory,
  revertEdit,
  redline: () => RL,
  toggleRedline,

  // the block source flip
  flip: (id) => flipBlock(id ? blockById.get(id) : focusedBlock()),
  flipState: () => (F.blockId
    ? { open: true, block: F.blockId, source: F.ta ? F.ta.value : "",
        note: F.noteEl ? F.noteEl.textContent : "" }
    : { open: false }),
  setFlipSource: (t) => { if (F.ta) { F.ta.value = String(t); autosize(F.ta, 0.5); }
                          return F.ta ? F.ta.value : ""; },
  saveFlip, cancelFlip, reloadBlock,

  // the splice, exposed so a machine walk can assert the SAME verdict the composer states
  spliceState, spliceOf, rewritePayload,

  // the geometry face
  geometry: () => ({ open: G.open, loaded: G.loaded, pages: G.pages.length,
                     scale: G.scale, source: S.source ? S.source.pdf : "" }),
  openGeometry, closeGeometry,

  // the historical board, one door away and labelled
  ledger: () => ({ open: L.open, loaded: L.loaded, rows: L.rows.length, note: L.note }),
  openLedger, closeLedger,
  // the session cursor and its gate, so a machine walk can prove the echo defect closed
  session: () => S.opened,
  admit,

  on: (name, fn) => { (listeners[name] || (listeners[name] = new Set())).add(fn); },
  off: (name, fn) => { if (listeners[name]) listeners[name].delete(fn); },
  // bridge contract D: who listens, and what has fired — read by root during pilots
  subscribers: () => Object.fromEntries(Object.entries(listeners).map(([name, set]) => [name, set.size])),
  emitted: () => ({ ...emitted }),
  // bridge contract C: the shell holds a cross-view return → the spine door is secondary
  setReturnMode: (mode) => {
    const value = mode === 'cross-view' ? 'cross-view' : '';
    if (value) root.dataset.returnMode = value; else delete root.dataset.returnMode;
    return value;
  },
  returnMode: () => root.dataset.returnMode || '',
};
window.walk = api;

// laplace:place (bridge contract A): the embedded walk tells the shell where the person is,
// so the shell's context() reads a memo instead of rebuilding the place from block rows.
//
// Payload: the place COORDINATES only — section id, block id, label, the owner's opaque
// source revision (71 characters; null while a held section is stale, as sourceObservation()
// says) and the selection the shell used to rebuild. Never the local document model
// (D.documentVersion is the full block model, ~850 KB on the live project; it stays behind
// api.documentVersion() for the guard consumers that need it). Measured on the live
// project's /walk/doc by tests/workspace_shell.test.mjs and $CLAUDE_JOB_DIR measure: a few
// hundred bytes per message.
// Timing: trailing debounce of PLACE_DEBOUNCE_MS after the last section / attention /
// edit-settled / document event, with a PLACE_MAX_WAIT_MS ceiling during a continuous burst
// (scrolling) so the shell is never starved, and no post at all when the coordinates did not
// change since the last post.
const PLACE_DEBOUNCE_MS = 100, PLACE_MAX_WAIT_MS = 500;
function placePayload() {
  const pos = api.readingPosition(), b = blockById.get(pos.blockId);
  const scope = b ? S.blocks.filter((x) => x.sectionId === pos.sectionId && srcOf(x).file === srcOf(b).file) : [];
  const starts = scope.map((x) => srcOf(x).lineStart), ends = scope.map((x) => srcOf(x).lineEnd);
  return { sectionId: pos.sectionId, blockId: pos.blockId, label: pos.label,
           revision: api.sourceObservation()?.current_revision ?? null,
           selection: b ? { files: [srcOf(b).file], section_ids: [pos.sectionId],
                            line_start: starts.length ? Math.min(...starts) : srcOf(b).lineStart,
                            line_end: ends.length ? Math.max(...ends) : srcOf(b).lineEnd } : null };
}
const placeBridge = { timer: null, firstEventAt: 0, sent: 0, suppressed: 0, lastSerialized: '', lastBytes: 0 };
function flushPlace() {
  clearTimeout(placeBridge.timer); placeBridge.timer = null; placeBridge.firstEventAt = 0;
  let message;
  try { message = { type: 'laplace:place', place: placePayload() }; } catch (_e) { return; }
  const serialized = JSON.stringify(message);
  if (serialized === placeBridge.lastSerialized) { placeBridge.suppressed++; return; }
  try { window.parent.postMessage(message, location.origin); placeBridge.sent++; placeBridge.lastSerialized = serialized;
    placeBridge.lastBytes = new TextEncoder().encode(serialized).length; }
  catch (_e) { /* the shell is the only listener; a failed post leaves it on the API path */ }
}
function postPlace() {
  if (!root.classList.contains('writing-embedded') || window.parent === window) return;
  const now = Date.now();
  if (!placeBridge.firstEventAt) placeBridge.firstEventAt = now;
  clearTimeout(placeBridge.timer);
  const wait = Math.max(0, Math.min(PLACE_DEBOUNCE_MS, PLACE_MAX_WAIT_MS - (now - placeBridge.firstEventAt)));
  placeBridge.timer = setTimeout(flushPlace, wait);
}
for (const name of ['section', 'attention', 'edit-settled', 'document']) api.on(name, postPlace);
api.placeSent = () => placeBridge.sent;
api.placeStats = () => ({
  sent: placeBridge.sent, suppressed: placeBridge.suppressed, last_bytes: placeBridge.lastBytes,
  debounce_ms: PLACE_DEBOUNCE_MS, max_wait_ms: PLACE_MAX_WAIT_MS,
});

// ═════════════════════════════════════════════════════════════════════════════════════════
// 20 · THE OPEN
// ═════════════════════════════════════════════════════════════════════════════════════════

async function open() {
  const openStarted=performance.now();
  wireControls();
  wireComposer();
  wireEditor();
  // the context resolves the geometry face's artefact; a failure there NEVER stops the
  // text canvas, and the reverse holds too. Two doors, two verdicts, both said in words.
  await loadContext();
  restoreEditHistory(); // hydrate before ready/onload can replay saved conversation actions
  ensureKatex();
  const ok = await loadDoc();
  paintBadge();
  if (!ok) {
    text(spineNote, "the spine derives from the document model's sections. The door that "
      + "serves that model did not answer, so there are no sections to show."
      + (S.source ? " The geometry face still opens from the head of the bar." : ""));
    S.ready = true;
    emit("ready", { ok: false, sections: 0, blocks: 0 });
    return;
  }
  S.docSize = fitDocSize();
  docEl.style.setProperty("--doc-size", S.docSize.toFixed(2) + "px");
  const renderStarted=performance.now();
  renderDoc();
  buildSpine();
  measure();
  root.dataset.renderMs=String(Math.round(performance.now()-renderStarted));
  S.current = -1;
  updateCurrent();
  S.dwellStamp = performance.now();
  paintZoom();
  loadParks();          // drafts survive the page: parked edits re-place from storage
  S.ready = true;
  root.dataset.readyMs=String(Math.round(performance.now()-openStarted));
  emit("ready", { ok: true, sections: S.sections.length, blocks: S.blocks.length,
                  unknown: D.unknown });
  renderLinkages();
  // the family's deep-link doors: ?block= lands on the block, ?section= on the section —
  // how the artefact surface routes prose editing INTO this canvas (clause 7).
  try {
    const q = new URLSearchParams(window.location.search);
    const blk = (q.get("block") || "").trim();
    const sec = (q.get("section") || "").trim();
    const fil = (q.get("file") || "").trim();
    if (blk && blockById.has(blk)) jumpToBlock(blk, { door: false });
    else if (sec) {
      const i = S.sections.findIndex((s2) => s2.id === sec);
      if (i >= 0) jumpToIndex(i, { door: false });
    } else if (fil) {
      const b = S.blocks.find((b2) => ((b2.src || {}).file || "") === fil);
      if (b) jumpToBlock(b.id, { door: false });
    }
  } catch (_e) { /* a malformed query never blocks the open */ }
}

open();

export default api;
export {citationReadURL} from './walk-source-client.mjs';
