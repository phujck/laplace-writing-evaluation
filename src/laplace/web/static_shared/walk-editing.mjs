// WALK EDITING (S2 F6). Purpose: the editor owner's commit chain: which blocks are editable, the
// presentation-owned paragraph structure, committing a typed edit, presentation splits, cross-block
// rewrites, commitAll and prepareForSession (the exact scope, quote and drafts a session receives).
// Owns: no long-lived state; each commit consumes one original basis from walk-drafts.mjs. Public
// contract: setEditable/editableBlock/sealIslands/headSpan, commitEdit, commitAll,
// savePresentationChange, crossBlockRewrite, prepareForSession, presentationOwner, structuralRequest.
import store from "/shared/store.mjs";
import {readManuscriptSource} from "/shared/manuscript-source-client.mjs";
import {
  restructureApplySubmission, restructurePreviewSubmission, validateRestructureEffect,
  validateRestructurePreview
} from "/shared/reader-restructure.mjs";
import {continuedEdit, emptyParagraphSource} from "/shared/manuscript-editing.mjs";
import {el, emit} from './walk-base.mjs';
import {D, RELOAD_INFLIGHT, blockById, reloadBlock} from './walk-document.mjs';
import {S, captureFocus, measure, restoreFocus} from './walk-position.mjs';
import {ownerView, saveSourceChange, setPayload, sourceRequest} from './walk-source-client.mjs';
import {renderBlockBody} from './walk-blocks.mjs';
import {
  C, askActor, autosize, dropArmedMark, ledgerPath, paintMarks, renderComposer, settleRail, srcSpanWords
} from './walk-composer.mjs';
import {
  anchorFromPristine, closestBlock, hostText, offsetIn, pieceSpanOf, pieceTypeAt, sourceForRenderedRange,
  srcOf, toSourceRegister
} from './walk-selection.mjs';
import {
  E, P, assignBasis, captureBasis, clearEdit, markSubmitted, paintParked, parkEdit, parkEntry, settleSubmission, snapshotEdit
} from './walk-drafts.mjs';
import {
  pendingPresentationSplits, recordStructuralOutcome, rememberStructuralChange, showStructuralOutcome,
  structuralSourceHolds, undoEditorChange
} from './walk-edit-history.mjs';
import {appliedOf, pendingOf, receiptWords, rewritePayload} from './walk-bank.mjs';
import {MINTED, admit, paintDeposits, renderBand} from './walk-band.mjs';
import {F} from './walk-flip.mjs';
import {bankCardComment, cardNote, caretRange, hideCard, setEditScope, showCard} from './walk-card.mjs';
import {
  beginParagraphTransition, endParagraphTransition, focusSplitParagraph, paragraphTransition,
  transferParagraphDraft
} from './walk-paragraph-ops.mjs';
import {onEditInput} from './walk-edit-input.mjs';

/** The head command's brace group, located anywhere in the block's tex and balanced-
 *  brace scanned — `\section{Title}` followed by a `\label{...}` line is this corpus's
 *  normal head shape, and an end-anchored read refused every such head (his report:
 *  "I can't edit section titles"). Returns [contentStart, contentEnd] or null. */
function headSpan(tex) {
  const m = /\\(?:sub)*(?:section|paragraph|chapter)\*?\s*\{/.exec(tex || "");
  if (!m) return null;
  const open = m.index + m[0].length - 1;
  let depth = 0;
  for (let i = open; i < tex.length; i++) {
    if (tex[i] === "{" && tex[i - 1] !== "\\") depth += 1;
    else if (tex[i] === "}" && tex[i - 1] !== "\\") {
      depth -= 1;
      if (!depth) return [open + 1, i];
    }
  }
  return null;
}

/** Which blocks type. Paragraphs with a usable piece map and a resolved source span —
 *  the exact splice is what makes typing safe; a block without one keeps the selection
 *  and flip gestures it already has. */
function editableBlock(b) {
  if(b.proposalLocked)return false;
  const s = srcOf(b);
  if (!s.file || !s.lineStart || b.texFace) return false;
  if (["para","caption","theorem","custom","list","table"].includes(b.kind || "para")) return !!b.pieceMap;
  // a section head edits when its title is PLAIN text — the rendered face and the brace
  // content are then the same characters, so the write-back is exact. A title carrying
  // math or a macro keeps the flip (click it open with s), stated rather than hidden.
  if (b.kind === "head") {
    const sp = headSpan(b.tex || "");
    if (!sp) return false;
    const content = b.tex.slice(sp[0], sp[1]);
    return !!(content && !b.tail?.trim() && !/[\\${}]/.test(content));
  }
  return false;
}

function setEditable(b, host) {
  if (editableBlock(b)) {
    host.setAttribute("contenteditable", "true");
    host.spellcheck = true;
  } else {
    host.setAttribute("contenteditable","false");
  }
}

/** The islands, sealed atomic: the caret walks around them, never into them. */
function sealIslands(host) {
  for (const n of host.querySelectorAll(".mathq, .cite-wrap, .ref, .unknown, .structural-piece")) {
    n.setAttribute("contenteditable", "false");
  }
}

function taggedParagraph(block) {
  return !!(block?.spec_ids?.length || block?.spec_id);
}

function presentationOwner(blocks) {
  const tagged = blocks.filter(taggedParagraph);
  if (!tagged.length) return null;
  if (tagged.some(block => !Array.isArray(block.spec_ids) || !block.restructure_preview)) {
    throw Error('Inspect this paragraph’s complete planned-unit links before changing its layout.');
  }
  const actions = tagged.map(block => block.restructure_preview);
  if (actions.some(action => action.payload?.section_id !== actions[0].payload?.section_id)) {
    throw Error('These paragraphs belong to different planned sections. Inspect their structural links before combining them.');
  }
  return actions[0];
}

async function structuralRequest(request) {
  try {
    return await store.fetchJSON(request.url, {method:'POST', inject:[], body:request.payload});
  } catch (error) {
    const retained = error.result || error.body?.result || error.body;
    if (retained?.schema_version === 'laplace.paragraph-restructure/1') return retained;
    throw error;
  }
}

async function savePresentationChange(kind, blocks, after, parts = null) {
  const action = presentationOwner(blocks);
  if (!action) throw Error('This layout change has no declared structural owner.');
  const file = blocks[0].src?.repo_file;
  if (!file || blocks.some(block => block.src?.repo_file !== file)) {
    throw Error('A paragraph layout change needs one exact source file.');
  }
  if (structuralSourceHolds.has(file)) {showStructuralOutcome(structuralSourceHolds.get(file));throw Error(
    'Inspect the retained structural source outcome before another text change.');}
  const selection = E.blockId && blocks.some(block => block.id === E.blockId)
    ? E.expectedSelection : D.sourceObservation?.source_observation?.selection_identity;
  const emitted = action.payload;
  let sourceDigest = emitted.source_guards?.[file], sourceSelection = emitted.expected_selection, sourceLines = null;
  if (!sourceDigest || !sourceSelection) {
    const observed = await readManuscriptSource({project:S.corpus, file});
    if (observed.file !== file) throw Error('The source read returned a different file. Your draft is retained.');
    sourceDigest = observed.expected_source_digest;sourceSelection = observed.selection_identity;
    sourceLines = observed.content.split('\n');
  }
  if (selection !== undefined && sourceSelection !== selection) {
    throw Error('The selected manuscript changed. Your paragraph draft is retained.');
  }
  const edits = blocks.map((block, index) => {
    const span = srcOf(block);
    if (sourceLines && sourceLines.slice(span.lineStart - 1, span.lineEnd).join('\n') !== block.tex) {
      throw Error('The paragraph source changed. Refresh its comparison; your draft is retained.');
    }
    return {file, line_start:span.lineStart, line_end:span.lineEnd, before:block.tex,
      after:index === 0 ? after : '', expected_source_digest:sourceDigest,
      expected_selection:sourceSelection};
  });
  const draft = {paragraph_ids:[...new Set(blocks.flatMap(block => block.spec_ids || []))], source_edits:edits,
    ...(parts ? {parts} : {})};
  const preview = validateRestructurePreview(await structuralRequest(
    restructurePreviewSubmission(action, S.corpus, kind, draft)), {project:S.corpus, kind, draft});
  const result = await structuralRequest(restructureApplySubmission(preview, S.corpus));
  const outcome = validateRestructureEffect(result, {project:S.corpus, preview});
  recordStructuralOutcome(result, outcome);
  if (outcome.sourceCommitted) rememberStructuralChange(result);
  showStructuralOutcome(result);
  return {result, outcome};
}

async function commitPresentationSplit(block, payload, split, submitted, pristine) {
  const body = ownerView(payload), span = srcOf(block), lines = block.tex.split('\n');
  const start = body.line_start - span.lineStart, end = body.line_end - span.lineStart + 1;
  if (start < 0 || end > lines.length || lines.slice(start, end).join('\n') !== body.before) {
    throw Error('The paragraph split could not retain its exact source mapping. Your draft remains here.');
  }
  const after = [...lines.slice(0, start), ...body.after.split('\n'), ...lines.slice(end)].join('\n');
  const at = after.indexOf('\n\n');
  if (at < 0) throw Error('The paragraph split has no exact source break. Your draft is retained.');
  const {result, outcome} = await savePresentationChange('presentation-split', [block], after,
    after.split('\n\n'));
  if (!outcome.sourceCommitted) {
    E.committing = false;
    emit('editor-status', {text:'Inspect the structural outcome before saving this paragraph again. Your draft is retained.', error:true});
    return {id:result.receipt?.id, applied:false, structural:true};
  }
  pendingPresentationSplits.delete(block.id);
  split.structuralResult = result;
  const continued = continuedEdit(submitted, hostText(block.bodyEl));
  if (E.blockId === block.id) clearEdit(block);
  else {P.delete(block.id);delete block.el?.dataset.editing;delete block.el?.dataset.parked;}
  if (continued) {
    P.set(block.id, {pristine:continued.pristine, text:continued.text, scope:E.scope || '',
      src:{...srcOf(block)}, tex:block.tex || ''});
  }
  try {
    const refreshed = await reloadBlock(block.id);
    if (refreshed?.ok === false) throw Error(refreshed.note || 'The source view could not refresh.');
    await focusSplitParagraph(block, split);
  } catch (error) {emit('editor-status', {text:'Paragraph text was saved. View refresh failed: ' + error.message + ' Do not repeat the text change.', error:true});}
  showStructuralOutcome(result);
  emit('bank', {id:result.receipt?.id, shape:'paragraph-restructure', applied:true, source:'paragraph-split'});
  emit('editor-status', {text:outcome.complete ? 'Paragraph layout and reader-plan record saved.' :
    'Paragraph layout saved. Finish its reader-plan record without repeating the text change.', error:!outcome.complete});
  return {id:result.receipt?.id, applied:true, structural:true};
}

// THE AUTHOR'S SAVE (wave 14a, his rulings of 9 November 2026). What he types is authoritative: the
// rewrite door applies it over the span as it is now (review_surface.py `_author_editor_write`), so this
// path holds no review state of its own and reads nothing back while he types.
// INFLIGHT: the blocks with a save out. One at a time: a save asked for while one is out (Ctrl-S, Save
// changes, the opt-in autosave) is remembered in QUEUE and sent ONCE when the reply lands, carrying the
// latest text, so no earlier request can land after a later one (ruling 4). parkEdit clears E.committing
// when focus leaves the paragraph, so the in-flight fact lives here and not on E.
// SENT: {read, sent} per block: the source this editor last wrote (`sent`) over the read it was typed
// against (`read`, b.tex then). The face, its piece map and b.tex stay those of the last read until the
// paragraph is clean, so nothing he types is re-rendered away mid-sentence; `sent` is what the file holds,
// and the next save's byte guard. Once the block is re-read (b.tex is no longer `read`) the entry is spent.
const INFLIGHT = new Set(), SENT = new Map(), QUEUE = {why: ''};
// A SAVE THAT DID NOT APPLY, SAID ONCE IN EACH PLACE (his ruling 3; the record's item 4): the frame's status
// line, where writing-panel.mjs offerKeep puts Keep my text and save it first, and the band's receipt
// (`C.echo`) in the warning tone, naming that same Keep. No card: a card would carry no Keep (judge-r1 D3).
// the last such reason, in plain words, for the batch's own line (commitAll): the owner's words, not a "Refused"
const NOT_SAVED = {why: ''};
function sayNotSaved(reason, line = '') {
  NOT_SAVED.why = (line || 'Not saved: ' + reason + '. Your text is kept.').replace(/^Not saved: (.)/, (_, first) => first.toUpperCase());
  emit('save-outcome', {state: 'not-saved', reason});
  C.echo = {text: 'Not saved: ' + reason + '. Your text is kept; Keep my text and save it, on the status line above the manuscript, saves it.', tone: 'refused'};
  renderBand();
  hideCard();
  emit('editor-status', {text: line || 'Not saved: ' + reason + '. Your text is kept.', error: true});
}
const NOT_LOCATED = 'your paragraph is not in the file as it stands now (another writer may have removed it)';
const NOT_LOCATED_LINE = 'Not saved: ' + NOT_LOCATED + '. Your text is kept; Keep my text and save it puts it back at its place.';
/** His paragraph the owner answered passage-not-located for: the draft keeps the request's place (file,
 *  line, the source it was typed against, the source it stands for) so Keep my text and save it can put
 *  it back there, from this canvas or after a reload; it is shown above the manuscript (walk-drafts.mjs
 *  paintHeldDrafts) with Keep first. */
function keepPlace(b, host, payload, now) {
  const view = ownerView(payload);
  const place = {file: srcOf(b).file, line: srcOf(b).lineStart, before: view.before, after: view.after, text: now};
  if (E.blockId === b.id) { E.place = place; P.set(b.id, parkEntry(b, host)); }
  else if (P.has(b.id)) P.get(b.id).place = place;
  paintParked();
}
/** The typed edit, banked. Diff the host's text against the pristine snapshot (common
 *  prefix/suffix), widen a pure insertion by one prose character so the span is real,
 *  and hand the span to the SAME payload the composer's rewrite uses. */
async function commitEdit(why, split=null) {
  if (!E.blockId) return null;
  if (INFLIGHT.size) { if (QUEUE.why !== 'all') QUEUE.why = why; return null; }
  // the opt-in autosave never writes over a paragraph whose source another writer changed under his
  // draft, nor puts back a paragraph the file no longer has: those wait for his explicit act (Keep my text
  // and save it, Ctrl-S, Save changes)
  if (why === 'autosave' && (E.moved || E.place || E.awaiting)) return null;
  // the reload window (chair-measured 2026-08-11): a commit inside an in-flight
  // post-splice reload reads a stale line span and banks PENDING. Wait it out first.
  if (RELOAD_INFLIGHT) { try { await RELOAD_INFLIGHT; } catch (_e) { /* said elsewhere */ } }
  const b = blockById.get(E.blockId);
  const host = b && b.bodyEl;
  if ((!b || !host) && E.place && typeof E.place.after === 'string' && typeof E.place.before === 'string') {
    // HIS PARAGRAPH WITH NO FACE ON THIS CANVAS (wave 14b, the record's item 1): a draft kept above the
    // manuscript with its place (walk-drafts.mjs placeOf). One request through the same door and the same
    // author path: the owner writes it over the paragraph its bytes or words locate, or puts it back at its
    // line as a paragraph of its own (`placement: insert`) and records which on the applied row.
    const id = E.blockId, place = E.place;
    const payload = sourceRequest({file: place.file, lineStart: place.line, lineEnd: place.line + place.before.split('\n').length - 1,
      before: place.before, after: place.after, passageBefore: E.pristine, passageAfter: place.text, block: '', source: 'click-type',
      extra: {placement: 'insert'}});
    E.committing = true; INFLIGHT.add(id);
    emit('save-outcome', {state: 'sending'});
    let res;
    try { res = await saveSourceChange(payload); }
    catch (e) { E.committing = false; QUEUE.why = ''; sayNotSaved(e && e.status ? e.message : 'No answer from the engine'); return null; }
    finally { INFLIGHT.delete(id); }
    const rec = (res && res.record) || {};
    if (!appliedOf(res, rec)) { E.committing = false; sayNotSaved(res.error || receiptWords(res) || 'the engine did not apply it'); return null; }
    P.delete(id); clearEdit();
    C.echo = {text: 'Saved ' + (rec.id || '') + ' · ' + (receiptWords(res) || ''), tone: 'banked'};
    renderBand(); paintDeposits();
    emit('bank', {id: rec.id, shape: 'rewrite', applied: true, pending: false, source: 'click-type'});
    const near = S.blocks.find(x => srcOf(x).file === place.file) || S.blocks[0];
    if (near) await reloadBlock(near.id);
    emit('save-settled', {block: id, sent: place.text});
    const lines = res.applied?.lines || [place.line, place.line];
    return {id: rec.id, kind: 'rewrite', applied: true, pending: false, file: place.file, line_start: lines[0], line_end: lines[1]};
  }
  if (!b || !host) { clearEdit(); return null; }
  const structuralHold = b.src?.repo_file ? structuralSourceHolds.get(b.src.repo_file) : null;
  if (structuralHold) {showStructuralOutcome(structuralHold);emit('editor-status', {
    text:'Inspect the retained structural outcome before saving this paragraph again. Your draft remains here.', error:true});return null;}
  if (E.timer) { clearTimeout(E.timer); E.timer = 0; }
  const was = E.pristine;
  const now = hostText(host);
  // Pasted breaks and typing in an in-flight next-paragraph draft must use the
  // same owner as Enter. Extra parts may be refused, but never saved as an
  // unmarked tail through the ordinary text door.
  if (!split && !pendingPresentationSplits.has(b.id) && taggedParagraph(b) && (now.match(/\n[ \t]*\n/g) || []).length > (was.match(/\n[ \t]*\n/g) || []).length) {
    const offset = now.search(/\n[ \t]*\n/);
    const selection = typeof document === 'undefined' ? null : document.getSelection();
    const caret = selection?.anchorNode && host.contains(selection.anchorNode) ? offsetIn(host,selection.anchorNode,selection.anchorOffset) : now.length;
    const prefix = now.slice(0,caret), lastBreak = prefix.lastIndexOf('\n\n');
    split = {offset, originalSource:b.tex, tail:now.slice(offset + now.slice(offset).match(/^\n[ \t]*\n/)[0].length),
      focusPart:prefix.split('\n\n').length-1, focusOffset:caret-(lastBreak<0?0:lastBreak+2)};
  }
  if (split && taggedParagraph(b)) pendingPresentationSplits.set(b.id, {split, retryRequired:false});
  const structuralDraft = pendingPresentationSplits.get(b.id);
  if (structuralDraft) {
    if (structuralDraft.retryRequired && why === 'autosave') return null;
    split = structuralDraft.split;
  }
  if (now === was) { clearEdit(b); return null; }
  if (!C.actor) {
    showCard(b, "this edit needs an actor before it banks", "refused");
    askActor("a typed edit banks a rewrite row, and the door refuses an unattributed "
           + "one. Name who is editing and it banks.", () => { commitEdit(why, split); });
    return null;
  }

  let p = 0;
  const nl = now.length, wl = was.length;
  while (p < nl && p < wl && now[p] === was[p]) p += 1;
  let sfx = 0;
  while (sfx < nl - p && sfx < wl - p && now[nl - 1 - sfx] === was[wl - 1 - sfx]) sfx += 1;
  let start = p, end = wl - sfx;
  let typed = sourceForRenderedRange(b,p,nl-sfx);
  if (start === end) {
    // a pure insertion: take one neighbouring character into the span — prose side
    // preferred — so the splice replaces something real. The door's byte guard holds
    // either way; a widening that lands in an island simply banks pending.
    const m = b.pieceMap || [];
    if (start > 0 && pieceTypeAt(m, start - 1) === "text") { start -= 1; typed = was[start] + typed; }
    else if (end < wl && pieceTypeAt(m, end) === "text") { typed = typed + was[end]; end += 1; }
    else if (start > 0) { start -= 1; typed = was[start] + typed; }
    else if (end < wl) { typed = typed + was[end]; end += 1; }
  }

  const a = anchorFromPristine(b, was, start, end);
  // the source this draft was typed against is older than the block's and its face was NOT re-based onto the
  // block (a `moved` park has its pristine re-based by placeDraft and splices against the block as usual)
  const staleBasis = !E.moved && typeof E.tex === 'string' && E.tex !== '' && E.tex !== (b.tex || '');
  const note = cardNote ? cardNote.value.trim() : "";
  // the tokens of the read this draft was typed against (none for a draft from before they were stored):
  // the door applies the author's own edit whatever their age; they name the home for the row's readers
  const expected = Array.isArray(E.expected) ? E.expected.filter(Boolean) : [];
  const supersedes = E.supersedes;
  let payload;
  if(b.kind==='para'&&!now.trim()){
    // Keep an editable empty paragraph through the existing draft/source mapper.
    // Its nonempty \par postimage remains guarded and undoable like ordinary typing.
    payload=sourceRequest({file:a.file,lineStart:a.lineStart,lineEnd:a.lineEnd,
      before:b.tex,after:emptyParagraphSource(toSourceRegister(now)),passageBefore:was,passageAfter:now,
      section:b.sectionId||'',block:b.id,note,expected});
  } else if ((b.tex || '').trim() === '\\par' && was === '') {
    payload = sourceRequest({ file: a.file, lineStart: a.lineStart, lineEnd: a.lineEnd,
      before: b.tex, after: emptyParagraphSource(toSourceRegister(now)),
      passageBefore: '', passageAfter: now,
      section: b.sectionId || "", block: b.id, expected });
  } else if (b.kind === "head") {
    // the whole title is the unit: rebuild the brace content around the typed text and
    // send the block-span rewrite — the trailing \label line and every comment ride
    // through untouched; the door's byte guard holds it exact.
    const sp = headSpan(b.tex || "");
    if (sp) {
      const after = b.tex.slice(0, sp[0]) + toSourceRegister(now.trim())
                  + b.tex.slice(sp[1]);
      payload = sourceRequest({ file: a.file, lineStart: a.lineStart, lineEnd: a.lineEnd,
        before: b.tex, after, passageBefore: was, passageAfter: now.trim(),
        section: b.sectionId || "", block: b.id, expected });
    } else {
      payload = rewritePayload(a, typed, "", expected);
    }
  } else {
    // THE DRAFT'S OWN BASIS (9 Nov, his retained paragraph after a reload): a draft typed against an older
    // source than the block now holds is spliced into THAT source, so `before` is the paragraph he edited and
    // the owner's author path relocates it by bytes, id or words and replaces it, recording the newer bytes
    // as superseded (review_surface.py `_author_paragraph`). Spliced against the newer source instead, his
    // quote has no home there, the splice falls back to the bare quote, and the save is mislabelled unplaced
    // and refused at the byte gate: the refusal he met twice today.
    payload = rewritePayload(staleBasis ? {...a, basis: E.tex} : a, typed, note, expected);
  }
  if(E.expectedSelection!==undefined)setPayload(payload,"expected_selection",E.expectedSelection);
  // a typed span the piece map could not place as prose (an edge inside an equation or citation) is not
  // the author path: the door keeps its byte guard and holds the words as a pending row, never a guess
  setPayload(payload, "source", ownerView(payload).before !== (staleBasis ? E.tex : (b.tex || '')) ? 'click-type-unplaced' : why==='split'?'paragraph-split':"click-type");
  // his paragraph the owner could not locate (it answered passage-not-located): this save asks it to put
  // the paragraph back at its place when nothing locates it still (review_surface.py `_insertion_line`)
  if (E.place) setPayload(payload, "placement", "insert");
  // the byte guard is what the file holds: the source this editor last wrote for the block, else its read
  if (SENT.has(b.id) && SENT.get(b.id).read !== (b.tex || '')) SENT.delete(b.id);
  const sentBefore = SENT.get(b.id)?.sent;
  if (sentBefore != null && ownerView(payload).before === (b.tex || '')) {
    setPayload(payload, "before_content", sentBefore);
    const lines = sentBefore.split('\n').length, m = /^(.*):(\d+)-(\d+)$/.exec(payload.target || '');
    if (m && Number(m[3]) - Number(m[2]) + 1 !== lines) payload.target = m[1] + ':' + m[2] + '-' + (Number(m[2]) + lines - 1);
  }
  if (E.scope) { setPayload(payload, "scope", E.scope);
                 setPayload(payload, "scope_source", "chosen"); }
  const chosenScope = E.scope;
  E.committing = true;
  INFLIGHT.add(b.id);
  emit('save-outcome', {state: 'sending'});
  showCard(b, "saving…", "");
  let res, sentText = null, submission = "";
  const draftOf = () => E.blockId === b.id ? E : P.get(b.id) || null;
  try {
    if (split && taggedParagraph(b)) return await commitPresentationSplit(b, payload, split, now, was);
    sentText = ownerView(payload).after || '';
    // the words are marked submitted (with their postimage) before they go out, so a refresh or a reload
    // while the request is out recognises the saved text as his own save and not as a change under his draft
    submission = markSubmitted(b, host, sentText);
    res = await saveSourceChange(payload,E.historyGroup,split?{tex:b.tex,line_start:a.lineStart,offset:split.offset}:null,split?{
      line_start:a.lineStart+sentText.slice(0,sentText.indexOf('\n\n')+2).split('\n').length-1,offset:0}:null);
  } catch (e) {
    if (pendingPresentationSplits.has(b.id)) {
      pendingPresentationSplits.get(b.id).retryRequired = true;
      pendingPresentationSplits.get(b.id).refusal = {message:e.message,reason:e.reason};
      E.committing = false;
      emit('editor-status', {text:e.message + ' Your paragraph draft remains here; inspect or save explicitly before retrying.', error:true});
      return null;
    }
    // His text stays in the editor exactly as typed, and stays unsaved. An HTTP answer is the owner's
    // refusal in its own words; no answer (a lost reply, a stopped engine) is said as that. Nothing is
    // sent again on its own (R9); Keep my text and save it, Ctrl-S or Save changes sends it again, which
    // is safe because the door applies his text over whatever the span holds.
    if (E.blockId === b.id) E.committing = false;
    settleSubmission(submission, {answered: true});
    const answered = !!(e && e.status);
    const reason = answered ? (e.body && (typeof e.body.error === 'string' ? e.body.error : e.body.reason)) || e.message
      : 'No answer from the engine';
    // the one refusal his rulings leave (ruling 1): nothing in the file locates his paragraph. The draft
    // keeps its place, so Keep my text and save it puts it back there; it never re-sends the refused edit
    const notLocated = answered && e.body && e.body.reason === 'passage-not-located';
    if (notLocated) keepPlace(b, host, payload, now);
    sayNotSaved(notLocated ? NOT_LOCATED : answered ? e.message : reason, notLocated ? NOT_LOCATED_LINE : '');
    QUEUE.why = '';
    emit('save-settled', {block: b.id, sent: now});
    return null;
  } finally {
    INFLIGHT.delete(b.id);
  }
  const rec = (res && res.record) || {};
  const id = rec.id || "(no id returned)";
  const collided = C.mine.has(id);
  const applied = appliedOf(res, rec);
  const pending = pendingOf(res, rec);
  const keepFace = pending && !applied;
  settleSubmission(submission, {answered: true});
  const draft = draftOf();
  const face = b.bodyEl ? hostText(b.bodyEl) : now;
  const later = face !== now;          // he typed on while the save was out
  if (keepFace) {
    // pending is reached only by a span the piece map could not place (click-type-unplaced): his words
    // stay on the page and in the pending row; the block stays amber, so Ctrl-S will not re-send it unchanged
    emit('save-outcome', {state: 'conflict', reason: res.retry_refused || ''});
    P.set(b.id, assignBasis({ pristine: E.pristine, text: now, scope: E.scope || "",
                  pendingRow: id, text_at_bank: now }, E));
    if (b.el) { b.el.dataset.parked = "1"; delete b.el.dataset.editing; }
    if (E.timer) { clearTimeout(E.timer); E.timer = 0; }
    E.blockId = ""; E.pristine = ""; E.dirty = false; E.committing = false; E.scope = "";
    setEditScope("");
    paintParked();
  } else if (applied && later) {
    // SAVED, AND HE TYPED ON. The file now holds what was sent; the later words stay an unsaved draft on
    // the same face, untouched: no re-read, no re-render, no hold. SENT is the next save's byte guard.
    SENT.set(b.id, {read: b.tex || '', sent: typeof rec?.anchor?.after === "string" ? rec.anchor.after : sentText});
    if (E.blockId === b.id) { E.committing = false; E.dirty = true; if (b.el) { delete b.el.dataset.parked; b.el.dataset.editing = "1"; } }
    paintParked();
  } else if (!applied) {
    // ANSWERED, NEITHER APPLIED NOR HELD (NODE.w3 ruling 5): his words stay on the page as an unsaved
    // draft; Keep my text and save it, Ctrl-S or Save changes sends them again (A2: never dropped)
    E.committing = false;
    E.dirty = hostText(host) !== E.pristine;
    if (E.dirty) P.set(b.id, parkEntry(b, host, hostText(host)));
    if (b.el) { delete b.el.dataset.parked; b.el.dataset.editing = E.dirty ? "1" : ""; }
    const notLocated = res.reason === 'passage-not-located';
    if (notLocated) keepPlace(b, host, payload, now); else paintParked();
    sayNotSaved(notLocated ? NOT_LOCATED : res.error || receiptWords(res) || 'the engine did not apply it', notLocated ? NOT_LOCATED_LINE : '');
  } else {
    SENT.delete(b.id);
    if (E.blockId === b.id) clearEdit(b); else { P.delete(b.id); if (b.el) { delete b.el.dataset.parked; delete b.el.dataset.editing; } paintParked(); }
  }

  const row = {
    id, ts: rec.ts || new Date().toISOString(),
    kind: (b.kind !== "head" && note) ? "compound" : "rewrite",
    comment: (b.kind !== "head" && note) ? note : "",
    scope: rec.scope || chosenScope || "",
    scope_source: rec.scope_source || (chosenScope ? "chosen" : ""),
    suggested_scope: "", grade: "block",
    before: a.quote, after: typed,
    section: b.sectionId || "", sections: null, blockId: b.id,
    file: a.file || "", by: C.actor, quote: a.quote, state: "open", mine: true,
    applied, pending,
    ...(res.receipt?.retry_warning?{retry_warning:res.receipt.retry_warning}:{}),
  };
  const listed = admit(row, MINTED);
  C.last = (collided || !listed) ? null : row;
  if (cardNote && b.kind !== "head") { cardNote.value = ""; autosize(cardNote, 0.2); }
  E.selAnchor = null;
  dropArmedMark();

  const head = "typed edit banked " + id + " → " + ledgerPath()
    + (applied &&
      supersedes?.pendingRow ? " · replaces the words banked pending as " + supersedes.pendingRow +
      "; that record stays recorded until you verify this result and retire it explicitly" : "");
  if (applied && supersedes?.pendingRow) emit('editor-status', {
    text: 'Saved ' + id + '. The earlier pending record ' + supersedes.pendingRow + ' remains recorded; verify this result, then retire it explicitly.'});
  const tail = applied
    ? " · spliced into " + srcSpanWords(a) + " · u revokes the row"
    : pending
      ? " · the source bytes did not match, so it stands as a PENDING rewrite for the "
        + "fix pass — your words stay here on the page and in the row · u revokes it"
      : " · " + (receiptWords(res) || "the door returned no splice verdict") + " · u revokes it";
  // a save that neither applied nor banked a row was said by sayNotSaved; the receipt keeps those words
  if (collided) C.echo = { text: head + tail + " — but this walk already holds that id; revoke from the band.", tone: "refused" };
  else if (applied || pending) C.echo = { text: head + tail, tone: applied ? "banked" : "refused" };
  // the same words at the point of the edit — the card is where his eyes are. A save that did not apply
  // is a warning, and a warning is said on the frame line beside Keep my text and save it (ruling 3,
  // judge-r1 D3), never in a card without it
  if (applied) showCard(b, "banked " + id + (row.scope ? " · " + row.scope : " · sentence (default)") + " · u revokes", "banked");
  else hideCard();
  settleRail();
  renderComposer();
  renderBand();            // the echo law: the receipt lands in the side panel, now
  paintDeposits();
  emit("bank", { id, shape: "rewrite", applied, pending, source: "click-type" });

  if (applied && !later) {
    // the paragraph is clean: read it back now, when there is nothing typed on it to lose
    if (F.blockId !== b.id) await reloadBlock(b.id);
    if (split) await focusSplitParagraph(b, split);
  }
  emit('save-settled', {block: b.id, sent: now});
  // a save asked for while this one was out goes now, once, with the latest text (ruling 4)
  const queued = QUEUE.why; QUEUE.why = '';
  if (queued === 'all') await commitAll();
  else if (queued && E.blockId === b.id && E.dirty) await commitEdit(queued);
  return row;
}

/** the cross-paragraph rewrite (his friction #1, 2026-08-11): a selection spanning
 *  paragraphs + an edit key replaces the span through the door as ONE rewrite — the
 *  selected tail of the first paragraph, every whole paragraph between, and the selected
 *  head of the last become the typed text (nothing, for a bare delete). Structural
 *  class: banks at once like the split and the join; PENDING-honest across odd
 *  separators; refused in words when the span crosses a non-paragraph block, spans
 *  files, lands an edge inside an island, or covers a standing unbanked edit. */
async function crossBlockRewrite(r, typed) {
  let aEl=closestBlock(r.startContainer),zEl=closestBlock(r.endContainer);
  let first=aEl?blockById.get(aEl.dataset.block):null,last=zEl?blockById.get(zEl.dataset.block):null;
  if(!first||!last)return;
  let i0=S.blocks.indexOf(first),i1=S.blocks.indexOf(last);
  if(i0<i1&&offsetIn(first.bodyEl,r.startContainer,r.startOffset)>=hostText(first.bodyEl).length){first=S.blocks[++i0];r.setStart(first.bodyEl,0);}
  if(i1>i0&&offsetIn(last.bodyEl,r.endContainer,r.endOffset)===0){last=S.blocks[--i1];r.setEnd(last.bodyEl,last.bodyEl.childNodes.length);}
  if(i0<0||i1<i0)return;
  if(i0===i1){const selection=document.getSelection();selection.removeAllRanges();selection.addRange(r);snapshotEdit(first,first.bodyEl);
    document.execCommand('insertText',false,typed);onEditInput({target:first.bodyEl});return;}
  const run = S.blocks.slice(i0, i1 + 1);
  const notPara = run.find((b) => (b.kind || "para") !== "para" || !b.bodyEl);
  if (notPara) {
    showCard(first, "the selection crosses a " + (notPara.kind || "block")
      + " — a rewrite across it is a structural ask; put it on the card", "refused");
    return;
  }
  const fs = srcOf(first), ls = srcOf(last);
  if (!fs.file || fs.file !== ls.file) {
    showCard(first, "these paragraphs live in different source files — no single "
      + "splice rewrites across them", "refused");
    return;
  }
  const standing = run.find((b) => P.has(b.id) || (E.blockId === b.id && E.dirty));
  if (standing) {
    showCard(first, "the selection covers an unbanked edit — Ctrl-S banks it or Esc "
      + "reverts it first, so nothing of yours is overwritten unseen", "refused");
    return;
  }
  if (!C.actor) {
    askActor("a rewrite across paragraphs banks a row, and the door refuses an "
           + "unattributed one. Name who is editing and it banks.", () => {});
    return;
  }
  if (RELOAD_INFLIGHT) { try { await RELOAD_INFLIGHT; } catch (_e) { /* said elsewhere */ } }
  // the two edges, face → source through the piece maps; an edge inside an island is
  // not addressable as prose and refuses in words, as everywhere.
  const texA = first.tex || "", texZ = last.tex || "";
  const offA = offsetIn(first.bodyEl, r.startContainer, r.startOffset);
  const offZ = offsetIn(last.bodyEl, r.endContainer, r.endOffset);
  let srcStart, srcEnd;
  if (offA <= 0) srcStart = 0;
  else {
    const sp = pieceSpanOf(first.pieceMap, texA, 0, offA);
    if (!sp || !sp.at) {
      showCard(first, "the selection's left edge sits "
        + (sp && sp.refused ? "inside rendered " + sp.refused : "on an unmapped span")
        + " — not addressable as prose; move it into the text", "refused");
      return;
    }
    srcStart = sp.at[1];
  }
  const lenZ = hostText(last.bodyEl).length;
  if (offZ >= lenZ) srcEnd = texZ.length;
  else {
    const sp = pieceSpanOf(last.pieceMap, texZ, offZ, lenZ);
    if (!sp || !sp.at) {
      showCard(last, "the selection's right edge sits "
        + (sp && sp.refused ? "inside rendered " + sp.refused : "on an unmapped span")
        + " — not addressable as prose; move it into the text", "refused");
      return;
    }
    srcEnd = sp.at[0];
  }
  // the separators are COMPUTED from the line spans, not assumed: this corpus writes
  // two blank lines between paragraphs, others write one — "\n".repeat(gap) covers
  // both, and a gap that holds anything but blank lines pends by the byte guard.
  let before = "";
  for (let i = 0; i < run.length; i++) {
    if (i) {
      const prev = srcOf(run[i - 1]), cur = srcOf(run[i]);
      before += "\n".repeat(Math.max(1, (cur.lineStart || 0) - (prev.lineEnd || 0)));
    }
    before += run[i].tex || "";
  }
  const after = texA.slice(0, srcStart) + toSourceRegister(typed) + texZ.slice(srcEnd)||'\\par';
  const draft=el('div','pending-paragraph');draft.contentEditable='true';draft.setAttribute('aria-label','Replacement paragraph');
  const prefix=caretRange(first.bodyEl,0,offA),suffix=caretRange(last.bodyEl,offZ,lenZ);draft.append(prefix.cloneContents(),document.createTextNode(
    typed));const cursor=hostText(draft).length;draft.append(suffix.cloneContents());const pristine=hostText(draft);
  const transition={kind:'replace',draft,undoRequested:false};draft.historyGroup=crypto.randomUUID();beginParagraphTransition(transition);
    first.el.before(draft);for(const block of run)block.el.hidden=true;clearEdit();draft.focus({preventScroll:true});
    const selection=document.getSelection();selection.removeAllRanges();selection.addRange(caretRange(draft,cursor));
  draft.handleBeforeInput=event=>{if(event.inputType==='insertParagraph'){event.preventDefault();document.execCommand('insertText',false,'\n\n');}};
  // A span across several paragraphs is one act over one addressed region, so it carries no
  // single block's token: the byte guard decides, exactly as it did before this build.
  const payload = sourceRequest({
    file: fs.file, lineStart: fs.lineStart, lineEnd: ls.lineEnd, before, after,
    passageBefore: run.map((b) => hostText(b.bodyEl)).join(" ¶ "),
    passageAfter: typed || "(the selected span, deleted)",
    section: first.sectionId || "", block: first.id, source: "click-type" });
  showCard(first, "rewriting across " + run.length + " paragraphs through the door…", "");
  let res;
  try {
    res = await saveSourceChange(payload,draft.historyGroup,{tex:first.tex,line_start:fs.lineStart,offset:offA,selection_end:{tex:last.tex,
      line_start:ls.lineStart,offset:offZ}},{tex:after,line_start:fs.lineStart,offset:cursor});
  } catch (e) {
    for(const block of run)block.el.hidden=false;draft.classList.add("unsaved");endParagraphTransition(transition);emit("editor-status",{text:e.message,error:true});
    return;
  }
  const rec = (res && res.record) || {};
  const id = rec.id || "(no id returned)";
  const applied = appliedOf(res, rec);
  const pending = pendingOf(res, rec);
  admit({
    id, ts: rec.ts || new Date().toISOString(), kind: "rewrite", comment: "",
    scope: rec.scope || "", scope_source: rec.scope_source || "",
    suggested_scope: "", grade: "block",
    before: "¶×" + run.length + " (a span across paragraphs)",
    after: typed || "(deleted)",
    section: first.sectionId || "", sections: null, blockId: first.id,
    file: fs.file || "", by: C.actor, quote: "", state: "open", mine: true,
    applied, pending,
  }, MINTED);
  C.echo = { text: "cross-paragraph rewrite banked " + id
      + (applied ? " · spliced — the span is one paragraph now"
        : pending ? " · the source spells a gap differently, so it stands PENDING for the fix pass"
                  : " · " + (receiptWords(res) || "no splice verdict")),
    tone: applied ? "banked" : "refused" };
  settleRail(); renderBand(); paintDeposits();
  emit("bank", { id, shape: "rewrite", applied, pending, source: "click-type" });
  showCard(first, applied ? "rewritten · banked " + id + " · u revokes"
    : "banked " + id + (pending ? " as PENDING (a paragraph gap is not a plain blank line)" : ""),
    applied ? "banked" : "refused");
  if(applied){await reloadBlock(first.id);const target=S.blocks.find(item=>srcOf(item).file===fs.file&&srcOf(item).lineStart===fs.lineStart);if(
    target)transferParagraphDraft(target,draft,pristine);}
  else{for(const block of run)block.el.hidden=false;draft.classList.add('unsaved');}
  endParagraphTransition(transition);if(transition.undoRequested)await undoEditorChange(false);
}

/** Settle only drafts in the requested manuscript attention. Other parked
 * passages stay where the author left them. Raw source remains a draft until its
 * explicit save, and is delivered separately from persisted source guards. */
async function prepareForSession(selection={}, {save=true}={}){
  const sameFile=(a,b)=>a===b||String(a||'').endsWith('/'+b)||String(b||'').endsWith('/'+a);
  const anchor=selection.anchor||{},files=selection.files||[anchor.file].filter(Boolean);
  const lo=anchor.line_start??selection.line_start,hi=anchor.line_end??selection.line_end??lo;
  const inScope=b=>{const src=srcOf(b);return (!files.length||files.some(file=>sameFile(file,src.file)))&&(!lo||src.lineEnd>=lo)&&(!hi||src.lineStart<=hi);};
  // Finish already submitted source operations before deciding what remains local.
  const deadline=Date.now()+5000;
  while((E.committing||F.saving||paragraphTransition)&&Date.now()<deadline)await new Promise(resolve=>setTimeout(resolve,25));
  if(RELOAD_INFLIGHT)await RELOAD_INFLIGHT;
  const attempted=new Set();
  for(let pass=0;pass<(save?2:0);pass++){
    const ids=[...new Set([E.blockId,...P.keys()].filter(Boolean))];
    for(const id of ids){
      const block=blockById.get(id),park=P.get(id);
      if(!block?.bodyEl||!inScope(block)||E.committing||F.saving||paragraphTransition||F.blockId===id||park?.noteOnly||park?.pendingRow||
        attempted.has(id+':'+hostText(block.bodyEl)))continue;
      attempted.add(id+':'+hostText(block.bodyEl));
      if(E.blockId&&E.blockId!==id&&E.dirty)parkEdit(blockById.get(E.blockId));
      if(E.blockId!==id){E.blockId=id;E.pristine=park?.pristine??hostText(block.bodyEl);assignBasis(E,park||captureBasis(block));
        E.moved=!!park?.moved;E.place=park?.place||null;E.dirty=hostText(block.bodyEl)!==E.pristine;setEditScope(park?.scope||'');}
      if(E.dirty)await commitEdit('session-send');
    }
  }
  const drafts=[];
  const active=blockById.get(E.blockId);
  if(!save&&active&&E.dirty&&inScope(active)&&!P.has(E.blockId)){const src=srcOf(active);drafts.push({format:'rendered',text:hostText(active.bodyEl),
    anchor:{file:src.file,line_start:src.lineStart,line_end:src.lineEnd},reason:'Attached local draft; sending does not save the manuscript.'});}
  for(const [id,park]of P){const block=blockById.get(id);if(!block||!inScope(block)||park.noteOnly||park.text===park.pristine)continue;
    const src=srcOf(block);drafts.push({format:'rendered',text:hostText(block.bodyEl)||park.text,anchor:{file:src.file,line_start:src.lineStart,
    line_end:src.lineEnd},reason:park.pendingRow?'The source guard did not match; these words remain local.':'Typing continued while the earlier change was saving.'});}
  const flipped=blockById.get(F.blockId);
  if(flipped&&inScope(flipped)&&F.ta&&F.ta.value!==(F.baseTex??flipped.tex??'')){const src=F.baseSource||srcOf(flipped);drafts.push({format:'tex',
    text:F.ta.value,anchor:{file:src.file,line_start:src.lineStart,line_end:src.lineEnd},reason:'The source editor has unsaved text. It has not been validated or written.'});}
  if(paragraphTransition?.draft){const draft=paragraphTransition.draft;drafts.push({format:'rendered',text:hostText(draft),anchor,
    reason:'This paragraph transition has not finished saving.'});}
  if(!drafts.length)return {};
  const draft=drafts.length===1?drafts[0]:{format:'rendered',anchor:drafts[0].anchor,text:drafts.map(item=>
    item.anchor.file+':'+item.anchor.line_start+' ('+item.format+')\n'+item.text).join('\n\n'),
    reason:'These scoped passages remain unsaved; each location and source format is identified in the text.'};
  emit('editor-status',{text:'The session will receive the unsaved draft separately from saved source.'});
  return {draft:{status:'UNSAVED',...draft}};
}

/** The paragraphs holding a draft over words of his own save that this editor has not read back. The
 *  shell's refresh poller reads this through walk.editState().submitted: the file moved because HE saved,
 *  so it says nothing about a change elsewhere (save-trace C10; judge-r1 D1). */
function ownSavesUnread() {
  let n = 0;
  for (const [id, entry] of SENT) if (blockById.get(id)?.tex === entry.read && ((E.blockId === id && E.dirty) || P.has(id))) n += 1;
  return n;
}

/** Where an unplaced draft's paragraph stands now: the one paragraph of its file sharing at least 0.6 of the
 *  words it was typed against (Dice over word multisets) and leading every other by at least 0.2; when
 *  several are that like it, the one still at its own line if that one reaches 0.6 and the best by less than
 *  0.2 (its line breaks a tie of words, never chooses alone); null otherwise. The same rule as the owner's
 *  (review_surface.py `_author_paragraph`). */
function ownParagraph(entry) {
  const words = text => { const m = new Map(); for (const w of String(text || '').toLowerCase().match(/[\p{L}\p{N}_]+/gu) || []) m.set(w, (m.get(w) || 0) + 1); return m; };
  const like = (a, b) => { let n = 0, common = 0; for (const [w, c] of a) { n += c; common += Math.min(c, b.get(w) || 0); } for (const c of b.values()) n += c; return n ? 2 * common / n : 0; };
  const basis = words(typeof entry.tex === 'string' && entry.tex ? entry.tex : entry.pristine);
  const scored = S.blocks.filter(x => x.bodyEl && x.kind === 'para' && srcOf(x).file === entry.src.file)
    .map(x => [like(basis, words(x.tex)), x]).sort((a, b) => b[0] - a[0]);
  if (!scored.length || scored[0][0] < 0.6) return null;
  if (scored.length === 1 || scored[0][0] - scored[1][0] >= 0.2) return scored[0][1];
  const line = entry.src.lineStart, atLine = scored.find(([score, x]) => srcOf(x).lineStart <= line && line <= srcOf(x).lineEnd
    && score >= 0.6 && scored[0][0] - score < 0.2);
  return atLine ? atLine[1] : null;
}

/** Ctrl-S — THE bank (the parking model): the active edit first, then every parked
 *  block, one row each, through the one door, sequentially. A parked block whose
 *  paragraph no longer exists is never silently dropped: its words stay in the map and
 *  the echo says so loudly. */
async function commitAll() {
  const batch={applied:[],pending:[],comments:[],recorded:[],refused:[],remaining:[],retained_pending:[],superseded:[]};
  // a save is out: this one goes when its reply lands, once, with the latest text (ruling 4)
  if(INFLIGHT.size||E.committing){QUEUE.why='all';const message='An edit is already being saved; your latest text is saved as soon as its reply lands.';emit('editor-status',{text:message});return {...batch,inflight:true,message};}
  const seen = new Set();
  const seenDrafts = new Set();
  const attempt=async b=>{
    const src=srcOf(b),target={block_id:b.id,file:src.file,line_start:src.lineStart,line_end:src.lineEnd};
    const supersedes=E.supersedes;   // a reconciled attempt names the pending record it replaces
    const row=await commitEdit("ctrl-s");
    if(row)batch[row.applied?'applied':row.pending?'pending':row.kind==='comment'?'comments':'recorded'].push({...target,id:row.id,...(
      row.retry_warning?{retry_warning:row.retry_warning}:{})});
    if(row?.applied&&supersedes?.pendingRow)batch.superseded.push({...target,id:supersedes.pendingRow,applied_id:row.id});
    // a save that applied while he typed on is saved, not refused: the later words are an unsaved draft
    else if(!row&&E.blockId===b.id&&E.dirty)batch.refused.push({...target,reason:pendingPresentationSplits.get(b.id)?.refusal?.message||NOT_SAVED.why});
    const held=P.get(b.id);if(held?.draft_id)seenDrafts.add(held.draft_id);
  };
  if (E.blockId && E.dirty) {const id=E.blockId;seen.add(id);const b=blockById.get(id);if(b)await attempt(b);else batch.refused.push({block_id:id,unplaced:true});}
  let guard = 128;
  while (guard-- > 0) {
    const id = Array.from(P.keys()).find((k) => !seen.has(k)&&(!P.get(k)?.draft_id||!seenDrafts.has(P.get(k).draft_id)));
    if (!id) break;
    seen.add(id);
    const entry = P.get(id);
    const b = blockById.get(id);
    if(entry?.draft_id)seenDrafts.add(entry.draft_id);
    if ((!b || !b.bodyEl) && entry?.unplaced && entry.place && !entry.noteOnly && typeof entry.text === 'string') {
      // HIS PARAGRAPH NOT IN THE FILE (wave 14b, the record's item 1): kept above the manuscript with its
      // place; commitEdit sends it once, and the owner writes it over the paragraph its words locate or
      // puts it back at its place as a paragraph of its own
      if (E.blockId && E.dirty && E.blockId !== id) parkEdit(blockById.get(E.blockId));
      E.blockId = id; E.pristine = entry.pristine; E.dirty = true; assignBasis(E, entry); E.moved = false; E.place = entry.place;
      const row = await commitEdit("ctrl-s");
      const target = {block_id: id, file: entry.place.file, line_start: row?.line_start ?? entry.place.line, line_end: row?.line_end ?? entry.place.line};
      if (row?.applied) batch.applied.push({...target, id: row.id});
      else { batch.refused.push({...target, reason: 'Your paragraph was not put back; its text is kept above the manuscript.'});
        if (E.blockId === id) { E.blockId = ''; E.pristine = ''; E.dirty = false; E.place = null; E.committing = false; } }
      continue;
    }
    if (!b || !b.bodyEl) {
      C.echo = { text: "a draft of yours is not in the file and its source could not be rebuilt from it — its "
        + "words are kept above the manuscript to copy: “" + String(entry && entry.text || "").slice(0, 120)
        + "…”", tone: "refused" };
      renderBand(); paintDeposits();
      continue;
    }
    // a pending-banked park whose face is unchanged is already in a row — the fix pass
    // owns it; re-banking it here would mint duplicates. Edited further, it re-banks.
    if (entry.pendingRow && hostText(b.bodyEl) === entry.text_at_bank) continue;
    if (entry.noteOnly) {
      // a parked note banks as the comment it always was
      if (cardNote) { cardNote.value = entry.note || ""; autosize(cardNote, 0.2); }
      const row=await bankCardComment(b);
      if(row){batch.comments.push({block_id:id,file:srcOf(b).file,id:row.id});P.delete(id);
        if (b.el) { delete b.el.dataset.parked; delete b.el.dataset.editing; }}
      else batch.refused.push({block_id:id,file:srcOf(b).file});
      continue;
    }
    // the active edit parks only now, when another paragraph needs E (his caret stays live until then)
    if (E.blockId && E.blockId !== id && E.dirty) {const prev=E.blockId;parkEdit(blockById.get(prev));const held=P.get(prev);if(seen.has(prev)&&held?.draft_id)seenDrafts.add(held.draft_id);}
    E.blockId = id; E.pristine = entry.pristine; E.dirty = true; assignBasis(E, entry); E.moved = !!entry.moved; E.place = entry.place || null;
    setEditScope(entry.scope || "");
    if (cardNote) { cardNote.value = entry.note || ""; autosize(cardNote, 0.2); }
    if (hostText(b.bodyEl) === entry.pristine) { clearEdit(b); continue; }
    await attempt(b);
  }
  paintParked();
  batch.remaining=[...P].filter(([id,entry])=>!entry.pendingRow||!blockById.get(id)?.bodyEl||hostText(blockById.get(id).bodyEl)!==entry.text_at_bank)
    .map(([id,entry])=>({block_id:id,file:entry.src?.file||srcOf(blockById.get(id)||{}).file,unplaced:!!entry.unplaced}));
  const remainingIds=new Set(batch.remaining.map(row=>row.block_id)),pendingIds=new Set(batch.pending.map(row=>row.id));
  batch.retained_pending=[...P].filter(([id,entry])=>entry.pendingRow&&!remainingIds.has(id)&&!pendingIds.has(entry.pendingRow))
    .map(([id,entry])=>({block_id:id,file:entry.src?.file||srcOf(blockById.get(id)||{}).file,id:entry.pendingRow}));
  if(E.dirty&&!batch.remaining.some(row=>row.block_id===E.blockId))batch.remaining.push({block_id:E.blockId,file:srcOf(blockById.get(E.blockId)||{
    }).file,unplaced:!blockById.has(E.blockId)});
  const paths=rows=>[...new Set(rows.map(row=>row.file?row.file+(row.line_start?':'+row.line_start+'-'+row.line_end:''):'unplaced manuscript draft'))].join(', ');
  const parts=[];
  if(batch.applied.length)parts.push('Saved '+batch.applied.length+' edit'+(batch.applied.length===1?'':'s')+' in '+paths(batch.applied)+'.');
  if(batch.comments.length)parts.push('Recorded '+batch.comments.length+' comment'+(batch.comments.length===1?'':'s')+'.');
  if(batch.recorded.length)parts.push('Recorded '+batch.recorded.length+' edit'+(batch.recorded.length===1?'':'s')+' without confirmed source application.');
  if(batch.pending.length)parts.push('Recorded '+batch.pending.length+' pending edit'+(batch.pending.length===1?'':'s')+'; source application remains pending.');
  if(batch.retained_pending.length)parts.push(batch.retained_pending.length+' pending recorded edit'+(batch.retained_pending.length===1?' remains':'s remain')+' unapplied.');
  if(batch.refused.length)parts.push('Not saved: '+batch.refused.length+' edit'+(batch.refused.length===1?'':'s')+' in '+paths(batch.refused)+'.');
  const refusalReasons=[...new Set(batch.refused.map(row=>row.reason).filter(Boolean))];
  parts.push(...refusalReasons.slice(0,3));
  if(refusalReasons.length>3)parts.push((refusalReasons.length-3)+' additional refusal reasons are retained with the affected drafts.');
  if(batch.remaining.length)parts.push('Kept '+batch.remaining.length+' unsaved draft'+(batch.remaining.length===1?'':'s')+' in '+paths(batch.remaining)+'.');
  const retryWarnings=batch.applied.map(row=>row.retry_warning).filter(Boolean);parts.push(...retryWarnings);
  for(const row of batch.superseded)parts.push('The earlier pending record '+row.id+' remains recorded; verify the new result '+row.applied_id+', then retire it explicitly.');
  batch.message=parts.join(' ')||'No unsaved edits to save.';
  // later words typed while a save was out are an ordinary unsaved draft, not a warning
  C.echo={text:batch.message,tone:batch.refused.length||retryWarnings.length?'refused':'banked'};
  renderBand();emit('editor-status',{text:batch.message,error:!!(batch.refused.length||retryWarnings.length),save_batch:batch});
  return batch;
}

export {
  commitAll, commitEdit, crossBlockRewrite, editableBlock, headSpan, ownParagraph, ownSavesUnread, prepareForSession, presentationOwner,
  savePresentationChange, sealIslands, setEditable, structuralRequest, taggedParagraph
};
