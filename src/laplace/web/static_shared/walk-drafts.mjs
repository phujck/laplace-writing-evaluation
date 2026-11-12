// WALK DRAFTS (S2 F6). Purpose: the one draft owner: the active edit's basis (captureBasis), the
// awaiting-read check, parking per block, putting a retained draft back on a fresh face (placeDraft), the
// paragraphs of his that are no longer in the file, local persistence of parks and capture/discard of the
// active edit. Owns: E (the active edit), P (parked drafts by block), the park persistence state. Public
// contract: captureBasis/assignBasis, snapshotEdit/clearEdit/revertEdit, parkEntry/parkEdit/revertParked/
// paintParked, restoreParked/restoreFace/rekeyRows, showOtherVersion, loadParks.
// Currentness: a draft's basis is the original read it was typed against; a postimage is never
// treated as owner truth until a later read validates it. What he typed is authoritative (wave 14a
// rulings 1 and 5): no draft of his is held from saving. Storage: localStorage walk-parks:<corpus>;
// a failed write keeps the draft and is disclosed.
import {matchHeldDraft, mergeDraftRows, normalizeDraftRows} from "/shared/manuscript-editing.mjs";
import {docEl, el, emit, norm, text} from './walk-base.mjs';
import {D, OWNER_READ, blockById, expectedOf} from './walk-document.mjs';
import {S, captureFocus, measure, restoreFocus} from './walk-position.mjs';
import {asChrome, renderBlockBody} from './walk-blocks.mjs';
import {C, autosize, paintMarks, renderComposer} from './walk-composer.mjs';
import {hostText, nodeAt, srcOf, toSourceRegister} from './walk-selection.mjs';
import {pendingPresentationSplits, storageFailure, storageRecovered} from './walk-edit-history.mjs';
import {paintRedline, renderBand} from './walk-band.mjs';
import {flipBlock} from './walk-flip.mjs';
import {commitAll, commitEdit, ownParagraph} from './walk-editing.mjs';
import {bankCardComment, cardNote, setEditScope, showCard} from './walk-card.mjs';

/** THE DRAFT BASIS — what a typed edit is an edit OF, captured together when editing begins:
 *
 *    tex                the raw source the pristine face was rendered from
 *    src                the canonical file and span of that source
 *    expectedSelection  the document selection identity the read was made under
 *    expected           the identity tokens the read published for that source
 *
 *  The basis lives on `E` for the active edit and on every park (`parkEntry`), persists
 *  with the park (`localDraftRows`) and resumes with it; it is never reconstructed from
 *  `b.tex` after an adoption, because the block holds the owner's CURRENT source and the
 *  draft was made of an earlier one. A draft banks under its basis tokens and nothing else
 *  and nothing else. The basis moves only on proof:
 *
 *    re-address  (`readdressDraft`)  the block's raw bytes equal the basis bytes and the
 *                selection identity is unchanged: the same source at its current span, so
 *                the token the read published for it now is the identity of that source.
 *                Rendered equality is NOT proof (`Alpha \emph{original}.` and
 *                `Alpha original.` render alike), nor is a successful context placement.
 *    own save    a draft whose submitted postimage an owner read delivered (`verifyAwaiting`)
 *                takes that postimage as its basis; an intervening change makes it moved.
 *
 *  AWAITING (`awaiting`): his save is out (`awaiting.submitted`, `markSubmitted`), or a draft an
 *  earlier build persisted while its own save's postimage was unread. It resolves through an
 *  owner read that delivered this block after the save (`verifyAwaiting`, `readdressDraft`).
 *
 *  Anything else — another writer's change under the draft, same-looking markup, a draft from
 *  before the basis was stored — is a MOVED draft (wave 14b, `placeDraft`): his words stand in
 *  their paragraph as an unsaved draft, `moved` says the source changed under them, and his
 *  explicit save (Ctrl-S, Save changes, Keep my text and save it) writes them over the span as
 *  it is now (review_surface.py `_author_editor_write`). Nothing holds it and nothing reviews
 *  it first; Show the other version shows what the file holds (`showOtherVersion`). A draft
 *  whose paragraph nothing locates any more carries `place` (`placeOf`): Keep puts it back at
 *  its own place as a paragraph of its own. No current token is ever borrowed for a draft that
 *  was not made of the current source. */
function captureBasis(b) {
  return { tex: b.tex || "", src: { ...srcOf(b) },
           expectedSelection: D.sourceObservation?.source_observation?.selection_identity,
           expected: expectedOf(b), awaiting: null };
}
function assignBasis(target, basis) {
  target.tex = basis.tex; target.src = basis.src ? { ...basis.src } : null;
  target.expectedSelection = basis.expectedSelection;
  target.expected = Array.isArray(basis.expected) ? basis.expected.slice() : null;
  target.awaiting = basis.awaiting ? { ...basis.awaiting } : null;
  if (basis.supersedes) target.supersedes = { ...basis.supersedes };
  return target;
}
/** A park's basis, or null for a park from before the basis was stored (legacy) or one
 *  still awaiting its postimage. */
function basisOf(entry) {
  if (!entry || entry.awaiting || typeof entry.tex !== "string" || !Array.isArray(entry.expected) || !entry.src) return null;
  return { tex: entry.tex, src: entry.src, expectedSelection: entry.expectedSelection, expected: entry.expected };
}
/** Resolve an awaiting draft against a block an owner read delivered AFTER the save. */
function verifyAwaiting(entry, b) {
  const a = entry && entry.awaiting;
  if (!a) return false;
  if (!(Number(b.readSeq) > Number(a.seq))) return false;
  const selection = D.sourceObservation?.source_observation?.selection_identity;
  if ((b.tex || "") !== a.postimage || srcOf(b).file !== a.file || selection !== a.selection) return false;
  const tokens = expectedOf(b);
  if (!tokens.length) return false;
  entry.tex = a.postimage; entry.src = { ...srcOf(b) }; entry.expectedSelection = selection; entry.expected = tokens; entry.awaiting = null;
  if (E.blockId === b.id) assignBasis(E, entry);
  return true;
}
/** Mark the active edit SUBMITTED before its request goes out: the park carries the submitted
 *  postimage, so a reload, a refresh or a lost reply settles it by an owner read. */
function markSubmitted(b, host, postimage) {
  const id = "sub-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 8);
  E.awaiting = { postimage, file: srcOf(b).file, lineStart: srcOf(b).lineStart, selection: E.expectedSelection,
                 seq: OWNER_READ.seq, submitted: id, inflight: true };
  P.set(b.id, parkEntry(b, host));
  saveParks();
  return id;
}
/** The owner's answer (or its absence) for submission `id`, wherever its draft now is: the
 *  active edit or a park a refresh or re-render made of it. `answered`: the reply was received
 *  and the caller acts on it, so the mark goes and the draft's own basis stands; otherwise
 *  nothing is out any more and an owner read decides (`readdressDraft`). `pendingRow` keeps a
 *  park the owner banked as pending from being re-banked unchanged. */
function settleSubmission(id, {answered = false, pendingRow = "", textAtBank = ""} = {}) {
  if (!id) return 0;
  let n = 0;
  const settle = (target, isPark) => {
    if (!target || target.awaiting?.submitted !== id) return;
    n += 1;
    if (!answered) { target.awaiting = { ...target.awaiting, inflight: false }; return; }
    target.awaiting = null;
    if (isPark && pendingRow) { target.pendingRow = pendingRow; target.text_at_bank = textAtBank; }
  };
  settle(E, false);
  for (const entry of P.values()) settle(entry, true);
  if (n) saveParks();
  return n;
}
/** SUBMITTED, REPLY NOT SEEN (`awaiting.submitted`): the words were sent and no owner answer
 *  has been processed for them (a lost reply, a reply still out, a reload or a re-render before
 *  it came back). The draft keeps its own basis (`tex`, `expected`) and the submitted postimage
 *  beside it, and an owner read delivered after the save decides: bytes equal to the postimage
 *  are the owner's confirmation that they landed (the face that read renders becomes the
 *  baseline, so the next save sends only later words); bytes equal to the draft's own basis,
 *  once no request is still out (`inflight`), show they did not land and the basis stands
 *  re-addressed; anything else is a moved draft (`placeDraft`). */
function readdressDraft(entry, b) {
  if (entry && entry.awaiting && entry.awaiting.submitted) {
    const a = entry.awaiting;
    if (!(Number(b.readSeq) > Number(a.seq))) return false;
    const face = b.bodyEl ? hostText(b.bodyEl) : null;
    if (verifyAwaiting(entry, b)) {
      if (face != null) { entry.pristine = face; if (E.blockId === b.id) E.pristine = face; }
      return true;
    }
    const selection = D.sourceObservation?.source_observation?.selection_identity;
    if (a.inflight || (b.tex || "") !== entry.tex || srcOf(b).file !== a.file || selection !== entry.expectedSelection || !expectedOf(b).length) return false;
    entry.awaiting = null; entry.src = { ...srcOf(b) }; entry.expected = expectedOf(b);
    if (E.blockId === b.id) assignBasis(E, entry);
    return true;
  }
  if (entry && entry.awaiting) return verifyAwaiting(entry, b);
  const basis = basisOf(entry);
  if (!basis) return false;
  const selection = D.sourceObservation?.source_observation?.selection_identity;
  if ((b.tex || "") !== basis.tex || selection !== basis.expectedSelection) return false;
  entry.src = { ...srcOf(b) }; entry.expected = expectedOf(b);
  if (E.blockId === b.id) { E.src = { ...srcOf(b) }; E.expected = expectedOf(b); }
  return true;
}
/** Whether this block has been delivered by an owner read since the draft's save; until
 *  then an awaiting draft is neither verified nor moved — it simply waits. A submitted draft
 *  whose request is still out waits too: a read cannot yet say it did not land. */
function awaitingUnread(entry, b) {
  return !!(entry && entry.awaiting) && (!(Number(b && b.readSeq) > Number(entry.awaiting.seq)) || !!(entry.awaiting.submitted && entry.awaiting.inflight));
}
// The words two modules outside the author's typed save still show: the TeX pane's own save while its
// saved source is unread (walk-flip.mjs saveFlip, F.awaiting) and the paragraph delete while a save of
// that paragraph is out (walk-paragraph-ops.mjs, `awaiting`; `source-changed` is its fallback).
const REVIEW_WORDS = {
  "source-changed": "The source of this paragraph changed under your draft. Your words are kept; save them, or discard them, before deleting the paragraph.",
  "awaiting-postimage":
    "Your earlier change was saved, but this canvas has not read the saved source back yet. Nothing more is saved for this paragraph until it does; your later words are kept. Reload the manuscript to read it back.",
};
// said on the frame's status line when a re-render puts a moved draft back (writing-panel.mjs adds Keep
// my text and save it, then Show the other version)
const MOVED_WORDS = "Another writer changed this paragraph while your draft was open; your text is kept.";

/** Re-read the model and re-render ONE block. When the door's model no longer has the
 *  same blocks (a rewrite that split or merged one), the whole canvas is rebuilt instead —
 *  and the caller is told which happened, rather than a stale canvas being left standing. */
/** A banked row survives A RESHAPE, or it is said to have stopped resolving.
 *
 *  A block id is `<file>#<paragraph-id>` with a POSITIONAL ordinal when one paragraph id
 *  covers several blocks — and it does, often: 29 of this corpus's 76 paragraph ids hold
 *  more than one block, one of them 14. A rewrite that opens or closes a blank line inside
 *  such a paragraph renumbers every later block under that id, so a row banked minutes ago
 *  keeps a `blockId` that now names DIFFERENT prose: "go to it" jumps to the wrong
 *  paragraph and the orphan check compares his quote against the wrong text. The ids
 *  themselves are load-bearing (the door's `block` field, the byte-for-byte span identity),
 *  so they are left alone; instead, after a reshape every row whose block vanished — or
 *  whose block no longer holds its quote — is re-keyed to the one block that does. A row
 *  matching no block, or more than one, is re-keyed to nothing and `checkOrphans` says so
 *  rather than leaving it pointing confidently at the wrong words. */
function rekeyRows() {
  let moved = 0, lost = 0;
  for (const r of C.rows) {
    const q = norm(r.quote || "");
    if (!q || !r.blockId) continue;
    const held = blockById.get(r.blockId);
    if (held && held.el && norm(hostText(held.bodyEl || held.el)).indexOf(q) >= 0) continue;
    let hit = null, n = 0;
    for (const b of S.blocks) {
      if (!b.el) continue;
      if (norm(hostText(b.bodyEl || b.el)).indexOf(q) < 0) continue;
      n += 1;
      if (n > 1) break;
      hit = b;
    }
    if (n === 1 && hit.id !== r.blockId) { r.blockId = hit.id; r.file = (hit.src || {}).file || r.file; moved += 1; }
    else if (n !== 1) { r.blockId = ""; lost += 1; }
  }
  if (moved || lost) {
    C.refusal = "the rewrite changed how many blocks this paper has, so the canvas was "
      + "rebuilt from the door. " + moved + " banked row"
      + (moved === 1 ? " was" : "s were") + " re-keyed to the block that still holds its "
      + "words; " + lost + " no longer resolve" + (lost === 1 ? "s" : "")
      + " to exactly one block and " + (lost === 1 ? "is" : "are") + " marked orphan.";
    renderBand();
  }
}

/** Re-apply a parked diff to a freshly rendered face: the changed span becomes one text
 *  node holding the parked words. An island inside the span (rare: the edit bracketed
 *  one) flattens to its rendered characters until the bank re-renders — the words are
 *  never wrong, only the chrome. */
function applyFace(b, entry) {
  const host = b.bodyEl;
  if (!host) return false;
  const was = entry.pristine, now = entry.text;
  let p = 0;
  const nl = now.length, wl = was.length;
  while (p < nl && p < wl && now[p] === was[p]) p += 1;
  let sfx = 0;
  while (sfx < nl - p && sfx < wl - p && now[nl - 1 - sfx] === was[wl - 1 - sfx]) sfx += 1;
  const lo = nodeAt(host, p), hi = nodeAt(host, wl - sfx);
  if (!lo || !hi) return false;
  const r = document.createRange();
  try { r.setStart(lo.node, lo.off); r.setEnd(hi.node, hi.off); } catch (_e) { return false; }
  r.deleteContents();
  r.insertNode(document.createTextNode(now.slice(p, nl - sfx)));
  host.normalize();
  return true;
}

/** HIS DRAFT ON A FRESH FACE (wave 14b, the record's item 2), for a reload (`restoreParked`), a refresh
 *  that re-rendered the block, or a closed flip (`restoreFace`). Returns what happened:
 *    'saved'     the read holds exactly his words (his submitted save landed, or the face already reads
 *                as his text): nothing is left to save
 *    'draft'     the same source as the draft's basis (proven by bytes), or his own save is still out:
 *                his words over the same face, exactly as before
 *    'moved'     another writer changed the source under the draft: his whole text stands in the
 *                paragraph as an unsaved draft (`moved`), and his explicit save writes it over the span
 *                as it is now, so the file then equals his draft; no hold, no review box
 *    'unplaced'  the words cannot be shown on this paragraph's face (an equation or citation in the way
 *                and no context to place the change by): the caller keeps them above the manuscript */
function placeDraft(entry, b) {
  const fresh = hostText(b.bodyEl);
  const submitted = entry.awaiting && entry.awaiting.submitted ? entry.awaiting.postimage : null;
  const proven = readdressDraft(entry, b);
  if (submitted !== null && proven && entry.tex === submitted && fresh === entry.text) return 'saved';
  if (proven || awaitingUnread(entry, b)) {
    if (fresh !== entry.text && !(fresh === entry.pristine && applyFace(b, entry))) replaceByContext(b, entry, fresh);
    return 'draft';
  }
  if (fresh === entry.text) return 'saved';
  entry.awaiting = null; entry.moved = true; delete entry.review;
  const placed = (fresh === entry.pristine && applyFace(b, entry))
    // a plain paragraph takes his whole text, typed against the face it shows now
    || (b.kind === 'para' && Array.isArray(b.pieceMap) && b.pieceMap.every(piece => piece.t === 'text')
        && (b.bodyEl.textContent = entry.text, entry.pristine = fresh, true))
    || replaceByContext(b, entry, fresh);
  if (!placed) return 'unplaced';
  if (E.blockId === b.id) { E.pristine = entry.pristine; E.awaiting = null; E.moved = true; E.dirty = hostText(b.bodyEl) !== E.pristine; }
  return 'moved';
}

/** The source his draft stands for, for a request that has no paragraph face to diff: the basis source
 *  with his change put where its unchanged neighbours stand (exact for a plain paragraph, and for a change
 *  whose neighbouring words occur once in the source); null when it cannot be placed in the source. */
function draftSource(entry) {
  const tex = typeof entry.tex === 'string' ? entry.tex : '', was = entry.pristine || '', now = entry.text || '';
  if (!tex.trim()) return null;
  if (toSourceRegister(was) === tex) return toSourceRegister(now);
  let p = 0, s = 0;
  while (p < now.length && p < was.length && now[p] === was[p]) p += 1;
  while (s < now.length - p && s < was.length - p && now[now.length - 1 - s] === was[was.length - 1 - s]) s += 1;
  const left = toSourceRegister(was.slice(Math.max(0, p - 24), p)), right = toSourceRegister(was.slice(was.length - s, was.length - s + 24));
  const i = left ? tex.indexOf(left) : 0;
  if (i < 0 || (left && tex.indexOf(left, i + 1) >= 0)) return null;
  const from = i + left.length, to = right ? tex.indexOf(right, from) : tex.length;
  if (to < 0 || tex.slice(from, to) !== toSourceRegister(was.slice(p, was.length - s))) return null;
  return tex.slice(0, from) + toSourceRegister(now.slice(p, now.length - s)) + tex.slice(to);
}
/** Where a draft goes when no paragraph face can take it (`place`): its file, the line its paragraph
 *  stood at (or the line of the paragraph its words locate), the source it was typed against and the
 *  source it stands for. commitEdit sends exactly this with `placement: insert`; the owner replaces
 *  the paragraph its bytes or words locate, or puts his paragraph back at that line. */
function placeOf(entry, target = null) {
  const after = draftSource(entry);
  if (after == null || !entry.src?.file) return null;
  return {file: entry.src.file, line: target ? srcOf(target).lineStart : entry.src.lineStart, before: entry.tex, after, text: entry.text};
}
/** A draft no paragraph face can take: kept above the manuscript (`paintHeldDrafts`) with its place. */
function keepUnplaced(oldId, entry, target = null) {
  const key = oldId.startsWith('held:') ? oldId : 'held:' + oldId;
  P.set(key, {...entry, unplaced: true, moved: false, awaiting: null, place: entry.place || placeOf(entry, target)});
  if (E.blockId === oldId) { E.blockId = ''; E.pristine = ''; E.dirty = false; E.place = null; E.moved = false; }
}

/** Put a parked face back onto a freshly rendered block (`placeDraft`). A draft whose source another
 *  writer changed stays an unsaved draft on its paragraph and the status line says so, with Keep my text
 *  and save it first; words no face can take are kept above the manuscript. */
function restoreFace(b) {
  const entry = P.get(b.id);
  if (!entry || !b.bodyEl) return;
  const already = !!entry.moved;
  const outcome = placeDraft(entry, b);
  if (outcome === 'saved') {
    P.delete(b.id);
    if (b.el) delete b.el.dataset.parked;
    paintParked();
    return;
  }
  if (outcome === 'unplaced') { P.delete(b.id); keepUnplaced(b.id, entry, b); paintParked(); return; }
  if (b.el) b.el.dataset.parked = "1";
  paintParked();
  if (outcome === 'moved' && !already) emit('editor-status', {text: MOVED_WORDS, error: true});
}

/** Show the other version: what the file holds now at a paragraph whose source another writer changed
 *  under his draft, in a panel above the manuscript (the editor frame shows no card); nothing is saved or
 *  changed, his draft stays in its paragraph, and the panel goes when no moved draft is left (`paintParked`). */
function showOtherVersion(id = '') {
  const pick = id || [...P].find(([, entry]) => entry.moved)?.[0] || (E.moved ? E.blockId : '');
  const b = pick ? blockById.get(pick) : null;
  if (!b || !b.bodyEl) return false;
  document.querySelector('[data-other-version]')?.remove();
  const panel = asChrome(el('details', 'held-drafts')); panel.dataset.otherVersion = pick; panel.contentEditable = 'false'; panel.open = true;
  panel.append(el('summary', null, 'The other version of your paragraph at ' + srcOf(b).file + ':' + srcOf(b).lineStart + ', as the file holds it now'));
  const current = el('textarea'); current.readOnly = true; current.value = b.tex || ''; current.setAttribute('aria-label', 'Current source');
  const close = el('button', null, 'Close'); close.type = 'button'; close.onclick = () => panel.remove();
  panel.append(el('p', null, 'Your text stays in its paragraph until you save or discard it; Keep my text and save it writes it over this.'), current, close);
  docEl.before(panel);
  if (panel.scrollIntoView) panel.scrollIntoView({block: 'nearest'});
  return true;
}

/** The context-anchored PREVIEW: the changed span, located by its pristine neighbourhood
 *  in the fresh face, shows the parked words over the current render, and the park's
 *  face coordinates follow the fresh render so the preview can be re-applied. The basis
 *  (`tex`, `src`, `expected`) does not move here: placement is not authorization. */
function replaceByContext(b, entry, fresh) {
  const was = entry.pristine, now = entry.text;
  let p = 0;
  const nl = now.length, wl = was.length;
  while (p < nl && p < wl && now[p] === was[p]) p += 1;
  let s = 0;
  while (s < nl - p && s < wl - p && now[nl - 1 - s] === was[wl - 1 - s]) s += 1;
  const beforeCtx = was.slice(Math.max(0, p - 24), p);
  const afterCtx = was.slice(wl - s, Math.min(wl, wl - s + 24));
  const insert = now.slice(p, nl - s);
  const iB = beforeCtx ? fresh.indexOf(beforeCtx) : 0;
  const iA = afterCtx ? fresh.indexOf(afterCtx, iB < 0 ? 0 : iB + beforeCtx.length) : -1;
  if (iB >= 0 && (afterCtx === "" || iA >= 0)) {
    const start = iB + beforeCtx.length;
    const end = afterCtx === "" ? start + (wl - s - p) : iA;
    if (end >= start) {
      const lo = nodeAt(b.bodyEl, start), hi = nodeAt(b.bodyEl, end);
      if (lo && hi) {
        try {
          const r = document.createRange();
          r.setStart(lo.node, lo.off); r.setEnd(hi.node, hi.off);
          r.deleteContents();
          r.insertNode(document.createTextNode(insert));
          b.bodyEl.normalize();
          entry.pristine = fresh;
          entry.text = hostText(b.bodyEl);
          if (E.blockId === b.id) E.pristine = fresh;
          return true;
        } catch (_e) { /* the loud hold */ }
      }
    }
  }
  return false;
}

/** After a whole re-adopt (a reload, a restored page): every parked draft goes back to its paragraph.
 *  Found by its bytes or its rendered face (`matchHeldDraft`), else by its words (`ownParagraph`, the
 *  owner's rule: the one paragraph of its file clearly its own, never the one merely at its old line);
 *  re-keyed to the re-minted id and put on the face by `placeDraft`, as an unsaved draft whether or not
 *  the source moved under it. A draft nothing locates is kept above the manuscript with its place, and
 *  Keep my text and save it puts it back there; nothing typed is silently lost. */
function restoreParked() {
  if (!P.size) return;
  const entries = Array.from(P.entries());
  P.clear();
  const used = new Set();
  for (const [oldId, entry] of entries) {
    delete entry.review;              // a review hold an earlier build stored: this build holds no draft
    const candidates=S.blocks.filter(block=>!used.has(block.id)&&block.bodyEl).map(block=>({id:block.id,
      tex:block.tex,rendered:hostText(block.bodyEl),file:srcOf(block).file,line_start:srcOf(block).lineStart}));
    // a submitted draft is looked for first where its submitted bytes would stand, then at its own basis
    const ident=entry.conflict?null:(entry.awaiting?.submitted&&matchHeldDraft({...entry,tex:entry.awaiting.postimage},candidates))||matchHeldDraft(entry,candidates);
    let hit=ident?blockById.get(ident):null;
    if(!hit&&!entry.conflict&&!entry.noteOnly&&entry.src?.file&&typeof entry.text==='string'){const own=ownParagraph(entry);if(own?.bodyEl&&!used.has(own.id))hit=own;}
    if(!hit){keepUnplaced(oldId,entry);continue;}
    used.add(hit.id);
    const fresh = hostText(hit.bodyEl);
    if (fresh === entry.text && !entry.note && !entry.pendingRow) continue;
    const placed = { ...entry, unplaced:false, place:null };
    P.set(hit.id, placed);
    if (E.blockId === oldId) E.blockId = hit.id;
    const outcome = placeDraft(placed, hit);
    if (outcome === 'saved' && !placed.note && !placed.pendingRow) { P.delete(hit.id); continue; }
    if (outcome === 'unplaced') { P.delete(hit.id); keepUnplaced(oldId === hit.id ? hit.id : oldId, placed, hit); continue; }
    if (hit.el) hit.el.dataset.parked = "1";
  }
  paintParked();
}

// ═════════════════════════════════════════════════════════════════════════════════════════
// 17b · click-and-type — the canvas is an editor, not a viewer with an edit mode
//
// Usability contract, clause 1. A single click places the caret in a paragraph; typing
// edits, immediately. The edit banks through the EXISTING rewrite door on pause, on blur,
// on Enter, or on Ctrl-S, and the receipt lands in the session band. Math, citations,
// cross-refs and macro marks are atomic islands: the caret walks around them, a deletion
// that would take one is refused in words, and clicking one opens ITS source in place.
// Esc reverts the paragraph to what the source holds. NOTHING here re-serializes rendered
// content: the diff is rendered-text prefix/suffix against a pristine snapshot taken
// before the first keystroke, in the SAME coordinates the piece map was measured in, and
// the splice rides `spliceOf` — the one splice authority. A byte mismatch banks a pending
// rewrite through the door's own honesty; nothing is guessed.
// ═════════════════════════════════════════════════════════════════════════════════════════

const PAUSE_COMMIT_MS = 2200;   // typing pauses this long → the edit banks

const E = {
  blockId: "",      // the block under edit ("" = none)
  pristine: "",     // hostText at the first keystroke — the diff's left side
  // THE BASIS of the active edit (see `captureBasis`): the raw source the pristine renders,
  // its canonical span, the selection identity and the tokens the read published for it.
  tex: "", src: null, expectedSelection: undefined, expected: null,
  awaiting: null,   // {postimage, file, lineStart, selection, seq}: saved, not yet read back (`verifyAwaiting`)
  supersedes: null, // {pendingRow, text_at_bank}: an attempt that replaces an earlier pending row
  moved: false,     // the source changed under this draft while it was away (`placeDraft`); his save writes it
  place: null,      // {file, line, before, after, text}: his paragraph is no longer in the file (`placeOf`)
  dirty: false,
  timer: 0,
  committing: false,
  composing: false, // an IME composition is in flight: the pause timer waits for its end
  scope: "",        // the pending edit's altitude, chosen at the card ("" = door default)
  selAnchor: null,  // the selection the card holds (captured at mouseup: the live
                    // selection dies the moment the note field takes focus)
};

// THE PARK (his ruling 2026-08-11: "I like to work and rework and don't want you to look
// through my intermediates"). Edits park per block and NOTHING banks until his hand says
// so: Ctrl-S banks every standing block, Shift-Enter banks the one under the caret, blur
// and block-change PARK (the safety-net banks they replaced are retired), Esc reverts the
// current block. blockId → {pristine, text, scope, note, src, tex, expectedSelection,
// expected, moved, place}, refreshed on every input — the parked words never live only in the
// DOM, so no re-render can eat them; `tex`/`src`/`expectedSelection`/`expected` are the
// draft's BASIS (`captureBasis`), carried from the active edit and never rebuilt from the
// block; `moved` and `place` are facts about the file under it (`placeDraft`, `placeOf`), never a hold.
const P = new Map();

function parkEntry(b, host, nowText) {
  // the park carries the active edit's basis (captured in `snapshotEdit`), never the
  // block's current source
  return assignBasis({ pristine: E.pristine, text: nowText != null ? nowText : hostText(host),
           scope: E.scope, note: cardNote ? cardNote.value.trim() : "", moved: E.moved || undefined, place: E.place || undefined }, E);
}

/** The changed span of a park, compact — what Esc would take, shown BEFORE he presses it
 *  (his friction #2: the amber edge said something changed, never what). */
function parkDiff(entry) {
  const was = entry.pristine || "", now = entry.text || "";
  let p = 0;
  const nl = now.length, wl = was.length;
  while (p < nl && p < wl && now[p] === was[p]) p += 1;
  let s = 0;
  while (s < nl - p && s < wl - p && now[nl - 1 - s] === was[wl - 1 - s]) s += 1;
  const cut = (t) => (t.length > 44 ? t.slice(0, 21) + "…" + t.slice(-21) : t);
  return { minus: cut(was.slice(p, wl - s)), plus: cut(now.slice(p, nl - s)) };
}

/** Bank ONE parked block from a distance (his friction #6: Ctrl-S banks all or nothing;
 *  the good paragraph and the half-thought deserved separate doors). */
async function bankParked(id) {
  const entry = P.get(id);
  const b = blockById.get(id);
  if (!entry || !b || !b.bodyEl) return;
  if (E.blockId && E.dirty && E.blockId !== id) {
    const cur = blockById.get(E.blockId);
    if (cur) parkEdit(cur);
  }
  if (entry.noteOnly) {
    if (cardNote) { cardNote.value = entry.note || ""; autosize(cardNote, 0.2); }
    await bankCardComment(b);
    P.delete(id);
    if (b.el) { delete b.el.dataset.parked; delete b.el.dataset.editing; }
    paintParked();
    return;
  }
  E.blockId = id; E.pristine = entry.pristine; E.dirty = true; assignBasis(E, entry); E.moved = !!entry.moved; E.place = entry.place || null;
  setEditScope(entry.scope || "");
  if (cardNote) { cardNote.value = entry.note || ""; autosize(cardNote, 0.2); }
  if (hostText(b.bodyEl) === entry.pristine) { clearEdit(b); return; }
  await commitEdit("bank-one");
}

/** Revert ONE parked block from a distance: the park drops, the face shows the source.
 *  For a pending-banked park the ROW still holds the words (u revokes it). */
function revertParked(id) {
  const b = blockById.get(id);
  P.delete(id);
  if (b && b.el) { delete b.el.dataset.parked; delete b.el.dataset.editing; }
  if (E.blockId === id) {
    E.blockId = ""; E.pristine = ""; E.tex = ""; E.src = null; E.expected = null; E.awaiting = null; E.supersedes = null; E.moved = false; E.place = null; E.dirty = false; E.scope = "";
    setEditScope("");
  }
  if (b && b.bodyEl) {
    const f = captureFocus();
    renderBlockBody(b, b.bodyEl);
    paintMarks();
    measure();
    restoreFocus(f);
  }
  paintParked();emit("edit-settled",{});
}

/** The standing count + the per-block rows: the strip carries the number always; the
 *  band names each parked paragraph with its delta and its own bank / revert doors. */
let heldDraftSignature='';
// The held-drafts panel: only his paragraphs that are no longer in the file (wave 14b): a draft no
// paragraph locates (`unplaced`) or one the owner answered passage-not-located for (`place`). Each
// offers, first, Keep my text and save it (commitAll: the owner puts it back at its place, or writes it
// over the paragraph its words locate), then Copy draft and Discard. A draft whose paragraph is located
// is never here: it stands in its paragraph as an unsaved draft (`placeDraft`).
function paintHeldDrafts(){
  const rows=[...P].filter(([,entry])=>entry.unplaced||entry.place),signature=JSON.stringify(rows.map(([id,entry])=>[id,entry.text,!!entry.place]));
  if(signature===heldDraftSignature)return;heldDraftSignature=signature;
  document.querySelector('[data-held-drafts]')?.remove();if(!rows.length)return;
  const panel=asChrome(el('details','held-drafts'));panel.dataset.heldDrafts='';panel.contentEditable='false';panel.open=true;
  panel.append(el('summary',null,rows.length+' paragraph'+(rows.length===1?' of yours is':'s of yours are')+' not in the file'));
  for(const [id,entry]of rows){const card=el('section');card.dataset.heldDraft=id;const place=entry.place;
    card.append(el('p',null,place?'Your paragraph at '+place.file+':'+place.line+' is not in the file as it stands now. Your text is kept here; Keep my text and save it puts it back at its place.':
      'Your paragraph at '+entry.src?.file+':'+entry.src?.lineStart+' is not in the file, and its source could not be rebuilt from this draft. Your text is kept here to copy.'));
    if(entry.supersedes)card.append(el('p',null,
      'These words were banked pending as '+entry.supersedes.pendingRow+'; that record stays until you retire it after verifying the new result.'));
    const words=el('textarea');words.readOnly=true;words.value=entry.text;words.setAttribute('aria-label','Preserved local draft');card.append(el('p',
      null,'Your retained words'),words);
    if(place){const keep=el('button',null,'Keep my text and save it');keep.type='button';keep.onclick=async()=>{keep.disabled=true;try{await commitAll();}
      finally{keep.disabled=false;}};card.append(keep);}
    const copy=el('button',null,'Copy draft');copy.type='button';copy.onclick=async()=>{try{await navigator.clipboard.writeText(entry.text);emit(
      'editor-status',{text:'Draft copied. Place the caret at its current passage to use it.'});}catch(error){words.focus();words.select();emit(
      'editor-status',{text:'Select and copy the preserved text here.',error:true});}};const discard=el('button',null,'Discard this local draft');
      discard.type='button';discard.onclick=()=>revertParked(id);card.append(copy,discard);panel.append(card);}
  docEl.before(panel);emit('editor-status',{text:rows.some(([,entry])=>entry.place)?'A paragraph of yours is not in the file. Your text is kept above the manuscript; Keep my text and save it puts it back at its place.':
    'A paragraph of yours is not in the file. Your text is kept above the manuscript to copy.',error:true});
}

function paintParked() {
  const n = P.size;
  paintHeldDrafts();
  if (!E.moved && ![...P.values()].some(entry => entry.moved)) document.querySelector('[data-other-version]')?.remove();
  saveParks(); // also clear storage when the last standing draft is saved
  const strip = document.getElementById("rail-parked");
  if (strip) {
    strip.hidden = !n;
    text(strip, n + "¶");
    strip.title = n + " paragraph" + (n === 1 ? "" : "s") + " unbanked — Ctrl-S banks all";
  }
  const line = document.getElementById("band-parked");
  if (!line) return;
  line.hidden = !n;
  line.textContent = "";
  if (!n) return;
  const head = el("div", "pk-head",
    n + " paragraph" + (n === 1 ? "" : "s") + " unbanked — Ctrl-S banks all · "
    + "Esc reverts the one under the caret");
  line.appendChild(head);
  for (const [id, entry] of P.entries()) {
    const b = blockById.get(id);
    const row = el("div", "pk-row");
    const d = parkDiff(entry);
    const where = (entry.src && entry.src.file)
      ? entry.src.file + ":" + entry.src.lineStart : id;
    const label = el("button", "pk-jump");
    label.type = "button";
    text(label, (
      entry.pendingRow ? "PENDING · " : entry.awaiting ? "SAVING · " : entry.place || entry.unplaced ? "NOT IN THE FILE · " : entry.moved ? "CHANGED ELSEWHERE · " : entry.supersedes ?
      "replaces pending " + entry.supersedes.pendingRow + " · " : "") + where);
    label.title = "jump to the paragraph";
    label.addEventListener("click", () => {
      const nb = blockById.get(id);
      if (nb && nb.el) nb.el.scrollIntoView({ block: "center" });
    });
    row.appendChild(label);
    const diff = el("div", "pk-diff");
    if (d.minus) diff.appendChild(el("span", "pk-minus", "− " + d.minus));
    if (d.plus) diff.appendChild(el("span", "pk-plus", "+ " + d.plus));
    if (entry.note) diff.appendChild(el("span", "pk-plus", "✎ "
      + (entry.note.length > 60 ? entry.note.slice(0, 57) + "…" : entry.note)));
    if (!d.minus && !d.plus && !entry.note) {
      diff.appendChild(el("span", "pk-plus", "(no delta)"));
    }
    row.appendChild(diff);
    const doors = el("div", "pk-doors");
    if (!entry.pendingRow) {
      const bank = el("button", "pk-btn");
      bank.type = "button";
      text(bank, "bank");
      bank.addEventListener("click", () => { bankParked(id); });
      doors.appendChild(bank);
    }
    const rev = el("button", "pk-btn");
    rev.type = "button";
    text(rev, entry.pendingRow ? "drop face" : "revert");
    rev.title = entry.pendingRow
      ? "the pending row keeps the words; the paragraph shows the source again"
      : "drop this paragraph's unbanked edit";
    rev.addEventListener("click", () => { revertParked(id); });
    doors.appendChild(rev);
    row.appendChild(doors);
    if (b && !b.bodyEl) row.appendChild(el("div", "pk-lost",
      "this paragraph is not on the canvas — the words are held here"));
    line.appendChild(row);
  }
  saveParks();          // the parks survive the page: every state change re-banks them
  paintRedline();       // and the live redline follows the standing deltas
}

// the parks survive the page (his friction: a reload, a crash, a served-page restart
// must not eat drafts). P serializes to the browser's own storage — local, his — and
// re-places on open through the same exact matcher the re-adopt uses.
const PARK_KEY = () => "walk-parks:" + (S.corpus || "");
let parksLoaded=false,parkBaseline=[];
function localDraftRows(){
  const baseline=new Map(parkBaseline);
  return [...P].map(([id,entry])=>{entry.draft_id=entry.draft_id||baseline.get(id)?.draft_id||crypto.randomUUID();return [id,{
    expectedSelection:entry.expectedSelection,draft_id:entry.draft_id,pristine:entry.pristine,text:entry.text,scope:entry.scope||'',note:entry.note||
      '',src:entry.src||null,tex:typeof entry.tex==='string'?entry.tex:null,expected:Array.isArray(entry.expected)?entry.expected:null,
    // an awaiting draft persists WITHOUT its read ordinal: in a later session every read is after the save
    awaiting:entry.awaiting?{postimage:entry.awaiting.postimage,file:entry.awaiting.file,lineStart:entry.awaiting.lineStart,
      selection:entry.awaiting.selection,...(entry.awaiting.submitted?{submitted:entry.awaiting.submitted}:{})}:null,supersedes:entry.supersedes||null,
    moved:!!entry.moved,place:entry.place||null,noteOnly:!!entry.noteOnly,unplaced:!!entry.unplaced,conflict:!!entry.conflict,pendingRow:entry.pendingRow||'',text_at_bank:entry.text_at_bank||''}];});
}
function saveParks(){
  if(!parksLoaded)return false;
  try{
    const remote=normalizeDraftRows(JSON.parse(window.localStorage.getItem(PARK_KEY())||'[]'));
    const merged=mergeDraftRows(parkBaseline,localDraftRows(),remote);
    if(merged.rows.length)window.localStorage.setItem(PARK_KEY(),JSON.stringify(merged.rows));else window.localStorage.removeItem(PARK_KEY());
    // the stored row carries no read ordinal (`seq`) or in-flight mark: they are this page's own,
    // and overwriting the live awaiting with the stored one left `seq` undefined, so no read
    // could ever verify an awaiting draft (save-trace C8, Number(undefined) is NaN)
    for(const [id,entry]of merged.local)if(P.has(id)){const live=P.get(id);P.set(id,{...live,...entry,
      awaiting:live.awaiting&&entry.awaiting?{...live.awaiting}:entry.awaiting});}
    if(merged.conflicts){const localIds=new Set([...P.values()].map(entry=>entry.draft_id));for(const [id,entry]of merged.rows)if(entry.conflict&&
      !localIds.has(entry.draft_id))P.set(id,entry);paintHeldDrafts();emit('editor-status',{
      text:'Different drafts from two tabs were preserved. Review the local draft versions above the manuscript.',error:true});}
    parkBaseline=JSON.parse(JSON.stringify(localDraftRows()));storageRecovered('drafts');return true;
  }catch(error){return storageFailure('drafts',error);}
}
function loadParks(){
  try{
    const rows=normalizeDraftRows(JSON.parse(window.localStorage.getItem(PARK_KEY())||'[]'));parkBaseline=JSON.parse(JSON.stringify(rows));parksLoaded=true;
    // a restored awaiting draft predates every read of this session: `seq` -1 lets the
    // initial owner read verify it (or find it moved, `placeDraft`) — never a stored ordinal
    for(const [id,entry]of rows)P.set(id,entry.awaiting?{...entry,awaiting:{...entry.awaiting,seq:-1}}:entry);
    restoreParked();storageRecovered('drafts');
  }catch(error){storageFailure('drafts',error,'read');}
}

/** Moving away PARKS (never banks): the block keeps his words in the DOM and in P, wears
 *  the amber edge, and the rail carries the standing count. */
function parkEdit(b) {
  if (!b || E.blockId !== b.id || !E.dirty) return;
  if (b.bodyEl) P.set(b.id, parkEntry(b, b.bodyEl));
  if (b.el) { b.el.dataset.parked = "1"; delete b.el.dataset.editing; }
  if (E.timer) { clearTimeout(E.timer); E.timer = 0; }
  E.blockId = ""; E.pristine = ""; E.tex = ""; E.src = null; E.expected = null; E.awaiting = null; E.supersedes = null; E.moved = false; E.place = null; E.dirty = false; E.committing = false;
  setEditScope("");
  // the note parked WITH its block (captured in the entry above); the field clears so
  // the next block never inherits another block's rationale
  if (cardNote && cardNote.value) { cardNote.value = ""; autosize(cardNote, 0.2); }
  paintParked();
}

function clearEdit(b) {
  if (E.timer) { clearTimeout(E.timer); E.timer = 0; }
  const blk = b || (E.blockId ? blockById.get(E.blockId) : null);
  if (blk && blk.el) { delete blk.el.dataset.editing; delete blk.el.dataset.parked; }
  if (blk) P.delete(blk.id);          // a bank or a revert retires the park
  E.blockId = ""; E.pristine = ""; E.tex = ""; E.src = null; E.expected = null; E.awaiting = null; E.supersedes = null; E.moved = false; E.place = null;
    E.dirty = false; E.committing = false;E.historyGroup=null;
  E.scope = "";
  setEditScope("");
  paintParked();
}

/** Esc — the paragraph shows the source's words again; nothing was banked. */
function revertEdit() {
  const b = E.blockId ? blockById.get(E.blockId) : null;
  const structuralDraft = b && pendingPresentationSplits.get(b.id);
  structuralDraft?.split.liveDraft?.remove();
  if (b) pendingPresentationSplits.delete(b.id);
  clearEdit(b);
  if (!b || !b.bodyEl) return;
  const f = captureFocus();
  renderBlockBody(b, b.bodyEl);
  paintMarks();
  measure();
  restoreFocus(f);
  C.echo = { text: "reverted — the paragraph shows the source again; nothing was banked.",
             tone: "banked" };
  showCard(b, "reverted — nothing was banked", "");
  renderComposer();
  emit("edit-settled",{});
}

function snapshotEdit(b, host) {
  if (E.blockId === b.id) return;
  if (E.blockId && E.dirty) {
    // a block-change PARKS the block he is leaving (his ruling; the safety-net bank died)
    const prev = blockById.get(E.blockId);
    if (prev) parkEdit(prev); else clearEdit();
  } else if (E.blockId) {
    // leaving a CLEAN block: reset the cursor without touching any parked entry
    const prev = blockById.get(E.blockId);
    if (prev && prev.el) delete prev.el.dataset.editing;
    E.blockId = ""; E.pristine = ""; E.tex = ""; E.src = null; E.expected = null; E.awaiting = null; E.supersedes = null; E.moved = false; E.place = null; E.dirty = false; E.scope = "";
    setEditScope("");
  }
  // entering a parked block resumes against its original pristine — the diff stays one
  // unbroken span per block however many sittings the edit took — and against the basis
  // that pristine was captured with; a fresh edit captures the basis the block holds now.
  const held = P.get(b.id);
  E.blockId = b.id;
  E.pristine = held ? held.pristine : hostText(host);
  assignBasis(E, held ? held : captureBasis(b)); E.moved = !!held?.moved; E.place = held?.place || null;
  E.dirty = held ? hostText(host) !== held.pristine : false;
  E.scope = held ? held.scope || "" : E.scope;
  if (held && b.el) {
    delete b.el.dataset.parked;
    b.el.dataset.editing = E.dirty ? "1" : "";
  }
  // the parked note comes back with its block
  if (held && held.note && cardNote && !cardNote.value) {
    cardNote.value = held.note;
    autosize(cardNote, 0.2);
  }
}

export {
  E, P, REVIEW_WORDS, assignBasis, captureBasis, clearEdit, loadParks, markSubmitted, settleSubmission,
  paintParked, parkDiff, parkEdit, parkEntry, rekeyRows, restoreFace, restoreParked,
  revertEdit, revertParked, showOtherVersion, snapshotEdit
};
