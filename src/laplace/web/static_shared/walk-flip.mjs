// WALK FLIP (S2 F6). Purpose: the block-level source flip: `s` turns one block into its exact source
// in place, saves it through the one request shape, and Esc returns. Owns: F (the flipped block and
// its save state). Public contract: flipBlock, cancelFlip, saveFlip, focusedBlock, flipNote/setFlipNote.
import {el, emit, text} from './walk-base.mjs';
import {D, OWNER_READ, blockById, expectedOf, reloadBlock} from './walk-document.mjs';
import {S, blockAtY, captureFocus, measure, readingY, restoreFocus} from './walk-position.mjs';
import {saveSourceChange, sourceRequest} from './walk-source-client.mjs';
import {renderBlockBody} from './walk-blocks.mjs';
import {C, askActor, autosize, ledgerPath, openRail, paintMarks, renderComposer} from './walk-composer.mjs';
import {closestBlock, liveRange, srcLabel, srcOf} from './walk-selection.mjs';
import {E, P, REVIEW_WORDS, parkEdit, restoreFace} from './walk-drafts.mjs';
import {appliedOf, receiptWords} from './walk-bank.mjs';
import {MINTED, admit, paintDeposits, renderBand} from './walk-band.mjs';
import {openReferencePicker} from './walk-card.mjs';
import {clearObjectSelection} from './walk-paragraph-ops.mjs';

// ═════════════════════════════════════════════════════════════════════════════════════════
// 17 · the block-level source flip — `s`, in place, invited, and gone again on Esc
// ═════════════════════════════════════════════════════════════════════════════════════════
//
// This is the one place raw tex appears in this surface, and it appears exactly where the
// block is: never in the right rail, never as a side editor. Ctrl-S hands off to the SAME
// rewrite door the composer uses, at the block's full span, and the block re-renders alone.

// `baseTex`/`baseSource`/`baseExpected`: the source, span and owner identity the open flip
// edits against, captured together when it opens and advanced together by its own save.
// `awaiting`: the flip's own save was acknowledged and the saved source has not been read
// back by an owner read that delivered this block (`verifyAwaiting` rule); no further save
// is sent from the flip until it is, or the flip is reopened on a read block.
const F = { baseTex:null,baseSource:null,baseExpected:null,awaiting:null,blockId: "", ta: null, noteEl: null, saveBtn: null, saving: false };

function focusedBlock() {
  const active = document.activeElement;
  const viaFocus = active ? closestBlock(active) : null;
  if (viaFocus) return blockById.get(viaFocus.dataset.block) || null;
  if (C.armed && C.armed.blockId) return blockById.get(C.armed.blockId) || null;
  const range = liveRange();
  if (range) {
    const n = closestBlock(range.commonAncestorContainer);
    if (n) return blockById.get(n.dataset.block) || null;
  }
  if (!S.blocks.length) return null;
  return S.blocks[blockAtY(readingY())] || null;
}

function flipNote(b) {
  return srcOf(b).file&&srcOf(b).lineStart ? 'Ctrl / ⌘ S saves · Esc cancels' : 'Source preview only';
}

function flipBlock(b) {
  if (!b) return false;
  clearObjectSelection(true);
  if(b.proposalLocked){emit('editor-status',{text:'Accept or reject the proposed change before editing this passage.'});return false;}
  if (F.blockId === b.id) { if (F.ta) F.ta.focus(); return true; }
  if (F.blockId) cancelFlip();
  // a standing edit on THIS block PARKS first (park-and-open): the flip replaces the
  // face, but the words are held in P and the close re-places them via restoreFace.
  if (E.blockId === b.id && E.dirty) parkEdit(b);
  const host = b.bodyEl;
  if (!host) return false;
  const f = captureFocus();
  F.blockId = b.id; F.saving = false;F.baseTex=b.tex||"";F.baseSource={...srcOf(b)};F.baseExpected=expectedOf(b);F.awaiting=null;
    F.baseSelection=D.sourceObservation?.source_observation?.selection_identity;

  host.textContent = "";
  host.setAttribute("contenteditable","false");   // the flip's textarea owns the keys now
  const wrap = el("div", "flip");
  const head = el("div", "flip-head");
  head.appendChild(el("strong", null, "Edit LaTeX"));
  head.appendChild(el("span", "path", srcLabel(b)));
  wrap.appendChild(head);

  const ta = el("textarea");
  ta.value = b.tex || "";
  ta.setAttribute("aria-label", "LaTeX source for this passage");
  ta.wrap="soft";ta.setAttribute("autocapitalize","off");ta.oninput=()=>autosize(ta,.65);
  ta.spellcheck = false;
  wrap.appendChild(ta);

  const acts = el("div", "flip-acts");
  const save = el("button", "primary", "Save changes");
  save.type = "button";
  save.disabled = !srcOf(b).file || !srcOf(b).lineStart;
  save.addEventListener("click", () => saveFlip());
  const cancel = el("button", null, "Cancel");
  cancel.type = "button";
  cancel.addEventListener("click", () => cancelFlip());
  acts.appendChild(save);
  acts.appendChild(cancel);
  for(const [label,type]of [['Reference…','reference'],['Citation…','citation']]){const insert=el('button',null,label);insert.type='button';
    insert.onmousedown=event=>event.preventDefault();insert.onclick=()=>openReferencePicker(type);acts.appendChild(insert);}
  wrap.appendChild(acts);

  const note = el("div", "flip-note", flipNote(b));
  wrap.appendChild(note);
  host.appendChild(wrap);

  F.ta = ta; F.noteEl = note; F.saveBtn = save;
  b.el.dataset.flip = "1";
  autosize(ta, 0.65);
  measure();
  restoreFocus(f);
  ta.focus();emit('editor-status',{text:'Editing LaTeX source · Ctrl-S saves'});
  return true;
}

function cancelFlip() {
  if (!F.blockId) return false;
  const b = blockById.get(F.blockId);
  F.blockId = ""; F.ta = null; F.noteEl = null; F.saveBtn = null; F.saving = false; F.awaiting = null;
  if (b && b.bodyEl) {
    const f = captureFocus();
    delete b.el.dataset.flip;
    renderBlockBody(b, b.bodyEl);
    paintMarks();
    measure();
    restoreFocus(f);
    b.el.focus({ preventScroll: true });
    if (P.has(b.id)) restoreFace(b);   // park-and-open: the flip closes onto his words
  }
  emit("edit-settled",{});
  return true;
}

function setFlipNote(words, tone) {
  if (!F.noteEl) return;
  text(F.noteEl, words);
  if (tone) F.noteEl.dataset.tone = tone; else delete F.noteEl.dataset.tone;
}

/** The continued flip's authority after its own save: the re-read's tokens only when an
 *  owner read delivered this block after the save (`readSeq`) with bytes equal to the
 *  acknowledged postimage, in the same file, under the same selection identity — the
 *  `verifyAwaiting` rule for the flip. Null means awaiting: no save is sent. */
function settleFlipContinuation(current, awaiting) {
  if (!current || !awaiting) return null;
  if (!(Number(current.readSeq) > Number(awaiting.seq))) return null;
  if ((current.tex || "") !== awaiting.postimage || srcOf(current).file !== awaiting.file) return null;
  if (D.sourceObservation?.source_observation?.selection_identity !== awaiting.selection) return null;
  const tokens = expectedOf(current);
  return tokens.length ? tokens : null;
}

async function saveFlip({keepOpen=false}={}) {
  if (!F.blockId || !F.ta || F.saving) return null;
  const b = blockById.get(F.blockId);
  if (!b) return null;
  // no write without verified issued authority: a flip awaiting its read-back, or one
  // opened on a block the read published no token for, says so and sends nothing
  if (F.awaiting) { setFlipNote(REVIEW_WORDS["awaiting-postimage"], "refused"); if (F.saveBtn) F.saveBtn.disabled = true; return null; }
  if (!Array.isArray(F.baseExpected) || !F.baseExpected.length) {
    setFlipNote("This block carries no identity the read published, so nothing was sent. Reload the manuscript and reopen the source.", "refused"); return null;
  }
  const s = F.baseSource||srcOf(b);
  if (!s.file || !s.lineStart) {
    setFlipNote("this block carries no resolved source span, so there is nothing to write "
      + "back to. Nothing was sent.", "refused");
    return null;
  }
  if (!C.actor) {
    askActor("writing this block back banks a rewrite row, and the door refuses an "
           + "unattributed one. Name who is writing and it saves.", () => { saveFlip(); });
    return null;
  }
  const sourceSelection=F.baseSelection;
  const after = F.ta.value;
  const before = F.baseTex??b.tex??"";
  if (after === before) {
    if(keepOpen)setFlipNote("Saved · Esc returns to the manuscript", "");else cancelFlip();
    return null;
  }
  F.saving = true;
  if (F.saveBtn) { F.saveBtn.disabled = true; text(F.saveBtn, "writing…"); }
  setFlipNote("Saving changes…", "");
  const payload = sourceRequest({
    file: s.file, lineStart: s.lineStart, lineEnd: s.lineEnd,
    before, after, section: b.sectionId || "", block: b.id, source: "block-flip",expectedSelection:sourceSelection,
    expected: F.baseExpected });
  let res;
  try {
    res = await saveSourceChange(payload);
  } catch (e) {
    F.saving = false;
    if (F.saveBtn) { F.saveBtn.disabled = false; text(F.saveBtn, "Save changes"); }
    setFlipNote("REFUSED — nothing was written. " + e.message, "refused");
    return null;
  }
  F.saving = false;
  const rec = (res && res.record) || {};
  const id = rec.id || "(no id returned)";
  const applied = appliedOf(res, rec);
  // the band never holds tex. This gesture's before/after ARE the block's raw source, and
  // the source belongs in place at the block, invited — not in the right rail. The row
  // therefore carries the OUTCOME in words and the provenance, and the changed text itself
  // stays where he changed it: in the paper.
  const row = {
    id, ts: rec.ts || new Date().toISOString(), kind: "rewrite",
    scope: rec.scope || C.scope || "", scope_source: rec.scope_source || C.scopeSource || "",
    suggested_scope: "", grade: "block", comment: "",
    flip: true, where: srcLabel(b),
    before: "", after: "", section: b.sectionId || "", sections: null, blockId: b.id,
    file: s.file, by: C.actor, quote: "", state: "open", mine: true,
    applied, pending: !applied,
  };
  const listed = admit(row, MINTED);
  C.last = listed ? row : null;
  openRail("band");            // the echo moment; a paper click puts the band away
  renderBand();
  paintDeposits();
  emit("bank", { id, shape: "rewrite", applied, pending: !applied, source: "block-flip" });

  if (!applied) {
    setFlipNote("banked " + id + " → " + ledgerPath() + ", but the door did not report a "
      + "splice: " + (receiptWords(res) || "the bytes on disk did not match what this "
      + "block was parsed from") + ". The source you see is unchanged; revoke it from "
      + "the band, or re-open the block after the doc model refreshes.", "refused");
    if (F.saveBtn) { F.saveBtn.disabled = false; text(F.saveBtn, "Save changes"); }
    return row;
  }
  // the block re-renders ALONE: the flip closes, the model takes the door's new source,
  // and nothing else on the canvas moves.
  const sourceTextarea=F.ta;
  F.blockId = ""; F.ta = null; F.saveBtn = null;
  const noteEl = F.noteEl; F.noteEl = null;
  if (b.el) delete b.el.dataset.flip;
  // The block's source is NOT assigned locally here: only the owner read below may carry
  // the saved source onto the canvas, and only that read can verify the postimage.
  const awaiting = { postimage: after, file: s.file, lineStart: s.lineStart, selection: sourceSelection, seq: OWNER_READ.seq };
  const out = await reloadBlock(b.id);
  const continuedSource=sourceTextarea?.value,sourceCaret=[sourceTextarea?.selectionStart,sourceTextarea?.selectionEnd];
  if(continuedSource!=null&&(keepOpen||continuedSource!==after)){
    const current=S.blocks.find(item=>srcOf(item).file===s.file&&srcOf(item).lineStart===s.lineStart)||blockById.get(b.id);
    // The continued flip edits the acknowledged postimage. It takes the re-read's tokens
    // only when an owner read delivered this block after the save with exactly that
    // postimage (`settleFlipContinuation`); otherwise it stays AWAITING and sends nothing.
    const tokens=settleFlipContinuation(current,awaiting);
    if(current&&flipBlock(current)){F.baseTex=after;F.baseSelection=sourceSelection;F.baseSource={...s,lineEnd:s.lineStart+after.split(
      '\n').length-1};F.baseExpected=tokens;F.awaiting=tokens?null:awaiting;F.ta.value=continuedSource;F.ta.setSelectionRange(...sourceCaret);
      autosize(F.ta,.65);if(!tokens&&F.saveBtn)F.saveBtn.disabled=true;setFlipNote(!tokens?REVIEW_WORDS[
      "awaiting-postimage"]:continuedSource===after?'Saved · Esc returns to the manuscript':'Earlier changes saved. Your latest typing is still here.',tokens?'':'refused');}
  }
  const how = !out.ok
    ? " · the source was written, but the doc model door did not answer for the re-render, "
      + "so this block still shows what it was parsed from (" + out.note + ")"
    : out.whole
      ? " · the block count changed, so the whole canvas was rebuilt from the door"
      : " · this block re-rendered alone";
  const words = "wrote " + srcLabel(b) + " · banked " + id + " → " + ledgerPath() + how
    + " · revoke it from the band; a revoke retires the row, not the source edit.";
  C.echo = { text: words, tone: "banked" };
  renderComposer();
  if (noteEl && noteEl.isConnected) { text(noteEl, words); noteEl.dataset.tone = "banked"; }
  return row;
}

export {F, cancelFlip, flipBlock, flipNote, focusedBlock, saveFlip, setFlipNote};
