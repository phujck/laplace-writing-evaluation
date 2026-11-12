// WALK EDIT INPUT (S2 F6). Purpose: the editing host's input: beforeinput handling (typing,
// paragraph split, structural keys), input bookkeeping into the active edit, island sources and the
// editor's event wiring. Owns: no state. Public contract: wireEditor, onEditInput, eventEditingHost,
// islandSource.
import {paragraphSplitInsertion} from "/shared/manuscript-editing.mjs";
import {docEl, el, emit, root} from './walk-base.mjs';
import {D, blockById} from './walk-document.mjs';
import {C, openRail} from './walk-composer.mjs';
import {closestBlock, figLabelOf, hostText, liveRange, liveRangeFrom, offsetIn} from './walk-selection.mjs';
import {E, P, paintParked, parkDiff, parkEdit, parkEntry, snapshotEdit} from './walk-drafts.mjs';
import {undoEditorChange} from './walk-edit-history.mjs';
import {RL, clearRedline} from './walk-band.mjs';
import {F, flipBlock, flipNote, setFlipNote} from './walk-flip.mjs';
import {commitEdit, crossBlockRewrite} from './walk-editing.mjs';
import {
  CARD, cardNote, cardWhere, hideCard, paintCardState, positionCard, rangeTouchesIsland, showCard,
  wrapSelection, yieldComposer
} from './walk-card.mjs';
import {blockLabels, toggleWhere} from './walk-where.mjs';
import {
  beginParagraphTransition, endParagraphTransition, joinBlocks, paragraphAfterHeading, wireAtomicObjects
} from './walk-paragraph-ops.mjs';

/** Click on an island: ITS source opens in place — the block flips with the island's
 *  exact source span selected. For a citation the flip note also names what the key
 *  resolves to, so the reading affordance the click used to carry is not lost. */
function islandSource(node, citeKey) {
  const blkEl = closestBlock(node);
  if (!blkEl) return;
  const b = blockById.get(blkEl.dataset.block);
  if (!b) return;
  const go = () => {
    let span = null;
    if (b.pieceMap && b.bodyEl && b.bodyEl.contains(node)) {
      const at = offsetIn(b.bodyEl, node, 0);
      for (const pc of b.pieceMap) {
        if (pc.t !== "text" && at >= pc.rStart && at < Math.max(pc.rEnd, pc.rStart + 1)
            && Number.isFinite(pc.oStart) && Number.isFinite(pc.oEnd)) {
          span = [pc.oStart, pc.oEnd];
          break;
        }
      }
    }
    if (!flipBlock(b)) return;
    if (span && F.ta) { F.ta.focus(); F.ta.setSelectionRange(span[0], span[1]); }
    if (citeKey) {
      const rec = D.citations[citeKey];
      setFlipNote((rec && rec.entry
        ? citeKey + " resolves to: " + rec.entry + " — "
        : citeKey + " resolves to no entry in the built bibliography — ") + flipNote(b), "");
    }
    // an EQUATION opened for editing shows what uses it, where (his ask): the card
    // rides beside the flip with the links view open — every "referenced by" a jump door.
    if (b.kind === "equation") {
      const labels = blockLabels(b);
      showCard(b, labels.length
        ? "the links view lists what references " + labels.join(", ")
        : "this equation carries no label, so nothing can reference it by name", "");
      if (cardWhere.hidden) toggleWhere();
    }
  };
  // an island click with a standing edit parks and opens (his friction #3: fixing the
  // equation mid-sentence must not demand banking the half-formed prose around it).
  // The words are held in P; the flip closes back onto them via restoreFace.
  if (E.blockId === b.id && E.dirty) parkEdit(b);
  go();
}

function eventEditingHost(ev){
  if(ev.target?.matches?.('textarea,input,select'))return null;
  const selection=document.getSelection(),range=selection?.rangeCount?selection.getRangeAt(0):null;
  const node=range?.startContainer,element=node?.nodeType===1?node:node?.parentElement;
  return ev.target?.closest?.('.blk-body[contenteditable="true"]')||element?.closest?.('.blk-body[contenteditable="true"]');
}
function onBeforeInput(ev) {
  if(ev.target?.matches?.('textarea,input,select'))return;
  const selection=document.getSelection(),range=selection?.rangeCount?selection.getRangeAt(0):null,node=range?.startContainer,element=node?.nodeType===1?node:node?.parentElement;
  const draft=element?.closest?.('.pending-paragraph');if(draft){draft.handleBeforeInput?.(ev);return;}
  const first=range&&closestBlock(range.startContainer),last=range&&closestBlock(range.endContainer);
  if(first&&last&&first!==last&&(/^(insertText|insertReplacementText|insertFromPaste)$/.test(ev.inputType)||String(ev.inputType).startsWith(
    'delete'))){ev.preventDefault();const typed=String(ev.inputType).startsWith('delete')?'':ev.data??ev.dataTransfer?.getData('text/plain')??'';
    crossBlockRewrite(range.cloneRange(),typed);return;}
  const host=eventEditingHost(ev);
  if(!host){if(ev.target===docEl)ev.preventDefault();return;}
  const blkEl = closestBlock(host);
  const b = blkEl ? blockById.get(blkEl.dataset.block) : null;
  if (!b) return;
  const it = String(ev.inputType || "");

  if (it === "insertCompositionText") { snapshotEdit(b, host); return; }  // IME: never blocked
  if (it.startsWith("format")) {                                          // plain text only:
    ev.preventDefault();                                                   // a format gesture
    if (it === "formatItalic") wrapSelection("emph");                      // becomes typed TeX
    else if (it === "formatBold") wrapSelection("textbf");
    return;
  }
  if (it === "insertFromPaste" || it === "insertFromDrop") {
    ev.preventDefault();
    const dt = ev.dataTransfer || ev.clipboardData;
    const plain = dt ? dt.getData("text/plain") : "";
    if (!plain) return;
    if (/\n\s*\n/.test(plain)) {
      // a MULTI-PARAGRAPH paste is structural (his friction #4): the breaks ride into
      // the source as real paragraph gaps and the splice banks at once, like the split
      // — pasting two paragraphs makes two paragraphs, not one glued block.
      const sel = document.getSelection();
      const r = sel && sel.rangeCount ? sel.getRangeAt(0) : null;
      if (!r || !host.contains(r.startContainer)) return;
      if (rangeTouchesIsland(r, host)) {
        showCard(b, "that is an island — atomic here. Click it to edit its source.", "refused");
        return;
      }
      snapshotEdit(b, host);
      r.deleteContents();
      const tn = document.createTextNode(plain.replace(/\r\n/g, "\n"));
      r.insertNode(tn);
      r.setStartAfter(tn);
      r.collapse(true);
      sel.removeAllRanges();
      sel.addRange(r);
      host.dispatchEvent(new InputEvent("input",
        { bubbles: true, inputType: "insertText", data: plain }));
      commitEdit("paste");
      return;
    }
    snapshotEdit(b, host);
    document.execCommand("insertText", false, plain);
    return;
  }
  if (it === "insertParagraph" || it === "insertLineBreak") {
    // His chair, twice over (2026-08-11, mid-walk): "I can't carriage return or insert
    // a new paragraph if I need to" — so Enter splits the paragraph at the caret
    // ("\n\n" into the source), a carriage return being TYPING, not a banking gesture;
    // and "you can make shift enter the bank" — so Shift-Enter IS the bank, beside
    // Ctrl-S. The split banks IMMEDIATELY through the same rewrite door (structural
    // intent wants instant feedback), and the applied splice re-renders as two blocks
    // through reloadBlock's shape-change path. A pending verdict is marked pending, as
    // everywhere. Heads stay single-line: either key banks there.
    ev.preventDefault();
    if (b.kind==='head'&&it==='insertParagraph'){paragraphAfterHeading(b);return;}
    if (it === "insertLineBreak") {
      if (E.blockId === b.id && E.dirty) commitEdit("shift-enter");
      return;
    }
    const sel = document.getSelection();
    const r = sel && sel.rangeCount ? sel.getRangeAt(0) : null;
    if (!r || !host.contains(r.startContainer)) return;
    if (rangeTouchesIsland(r, host)) {
      showCard(b, "that is an island — atomic here. Click it to edit its source.", "refused");
      return;
    }
    snapshotEdit(b, host);
    if(b.kind!=='para'){document.execCommand('insertText',false,'\n\n');onEditInput({target:host});return;}
    const offset = offsetIn(host, r.startContainer, r.startOffset);
    const split = paragraphSplitInsertion(hostText(host), offset);split.originalSource=b.tex;split.offset=offset;
    const brk = split.insert;
    r.deleteContents();
    const tn = document.createTextNode(brk);
    r.insertNode(tn);
    r.setStartAfter(tn);
    r.collapse(true);
    sel.removeAllRanges();
    sel.addRange(r);
    host.dispatchEvent(new InputEvent("input",
      { bubbles: true, inputType: "insertText", data: brk }));
    // Create the next paragraph in the same gesture. Its live DOM receives
    // keystrokes while the structural source change is being saved.
    const tailRange=document.createRange();tailRange.selectNodeContents(host);tailRange.setStartAfter(tn);
    const draft=el('div','pending-paragraph');draft.contentEditable='true';draft.setAttribute('aria-label','New paragraph');draft.appendChild(tailRange.cloneContents());
    const hiddenTail=el('span');hiddenTail.hidden=true;hiddenTail.appendChild(tailRange.extractContents());host.appendChild(hiddenTail);
    const marker=el('span');marker.hidden=true;tn.replaceWith(marker);marker.appendChild(tn);
    b.el.after(draft);split.liveDraft=draft;split.draftPristine=hostText(draft);
    const transition={kind:'split',draft,undoRequested:false};beginParagraphTransition(transition);
    draft.handleBeforeInput=event=>{const selection=document.getSelection();if(!selection?.rangeCount)return;const range=selection.getRangeAt(0),
      at=offsetIn(draft,range.startContainer,range.startOffset);
      if(range.collapsed&&event.inputType==='deleteContentBackward'&&at===0){event.preventDefault();split.joinBack=true;return;}
      if(range.collapsed&&event.inputType==='deleteContentForward'&&at===hostText(draft).length){event.preventDefault();split.joinForward=true;return;}
      if(event.inputType==='insertParagraph'){event.preventDefault();document.execCommand('insertText',false,'\n\n');}
    };
    const saving=commitEdit('split',split);draft.focus({preventScroll:true});const nextRange=document.createRange();nextRange.selectNodeContents(
      draft);nextRange.collapse(true);sel.removeAllRanges();sel.addRange(nextRange);
    saving.then(row=>{if(!row?.applied){draft.classList.add('unsaved');if(row)emit('editor-status',{
      text:'Your new paragraph is preserved here. Save the preceding change to continue.',error:true});}}).finally(()=>{endParagraphTransition(
      transition);if(transition.undoRequested)undoEditorChange(false);});
    return;
  }
  if (it === "deleteContentBackward" || it === "deleteContentForward") {
    // at a block EDGE these are structural (his frame ruling, 2026-08-11: "should you
    // not think of this like a text editor?"): backspace at the start joins this
    // paragraph onto the previous one; delete at the end pulls the next one up. The
    // inverse of the Enter split, through the same door, tracked the same way.
    const sel0 = document.getSelection();
    const r0 = sel0 && sel0.rangeCount ? sel0.getRangeAt(0) : null;
    if(r0&&!r0.collapsed&&b.kind==='para'&&host.contains(r0.startContainer)&&host.contains(r0.endContainer)&&offsetIn(host,r0.startContainer,
      r0.startOffset)===0&&offsetIn(host,r0.endContainer,r0.endOffset)===hostText(host).length){
      // An explicit whole-paragraph text selection includes its inline islands.
      // Let native deletion/Undo run; snapshot before mutation and input parks it.
      // Save/Autosave controls persistence, unlike an explicit object Delete action.
      snapshotEdit(b,host);return;
    }
    if (r0 && r0.collapsed && host.contains(r0.startContainer)) {
      const off = offsetIn(host, r0.startContainer, r0.startOffset);
      if (it === "deleteContentBackward" && off === 0) {
        ev.preventDefault(); joinBlocks(b, "prev"); return;
      }
      if (it === "deleteContentForward" && off === hostText(host).length) {
        ev.preventDefault(); joinBlocks(b, "next"); return;
      }
    }
  }
  if (it.startsWith("delete") || it === "insertText" || it === "insertReplacementText") {
    const ranges = ev.getTargetRanges ? ev.getTargetRanges() : [];
    for (const sr of ranges) {
      const r = liveRangeFrom(sr);
      if (r && rangeTouchesIsland(r, host)) {
        ev.preventDefault();
        showCard(b, "that is an island — atomic here. Click it to edit its source.", "refused");
        return;
      }
    }
    snapshotEdit(b, host);
  }
}

function onEditInput(ev) {
  if(ev.target?.matches?.('textarea,input,select'))return;
  const host=eventEditingHost(ev);if(!host)return;
  const blkEl = closestBlock(host);
  const b = blkEl ? blockById.get(blkEl.dataset.block) : null;
  if (!b || E.blockId !== b.id) return;
  const nowText = hostText(host);
  E.dirty = nowText !== E.pristine;
  b.el.dataset.editing = E.dirty ? "1" : "";
  // the caret owns the active block: its redline marks clear so typing never fights
  // the mark wrappers (the marks return when the block parks or banks)
  if (RL && E.dirty) clearRedline(b.el);
  // the park rides every keystroke: the standing words live in P, not only in the DOM
  if (E.dirty) P.set(b.id, parkEntry(b, host, nowText)); else P.delete(b.id);
  paintParked();
  if (!E.dirty) { if (E.timer) { clearTimeout(E.timer); E.timer = 0; }
                  showCard(b, "Saved · Ctrl-S saves · Esc cancels the current edit", "");
                  return; }
  yieldComposer();
  showCard(b, "Unsaved changes · Ctrl-S saves · Esc cancels this edit", "");
  paintCardState();          // a note beside the edit makes it the compound truth
  positionCard(b);
  // the pause-bank is DEAD (his ruling 2026-08-11: "I like to work and rework and
  // don't want you to look through my intermediates") — hesitation is not consent,
  // and moving away PARKS now (the parking model): nothing banks until his hand says.
  if (E.timer) { clearTimeout(E.timer); E.timer = 0; }
  armAutosave();
}
/** THE AUTOSAVE, OFF UNLESS HE TURNS IT ON (wave 14a, his ruling 2: a save is his act; Ctrl-S or Save
 *  changes). With `laplace:editor-autosave` set to 'on' by the frame's Autosave control, 900 ms after the
 *  last input the active paragraph's edit is sent through the same commitEdit as Ctrl-S: that block's
 *  span only, and never a second request while one is out (commitEdit queues it and sends the latest
 *  text once when the reply lands). Off, the draft stays in the editor and in its stored park (R8). */
function armAutosave() {
  let on = false;
  try { on = localStorage.getItem('laplace:editor-autosave') === 'on'; } catch (_e) { on = false; }
  if(on && document.getElementById('walk')?.classList.contains('writing-embedded') && !E.composing){
    if (E.timer) { clearTimeout(E.timer); E.timer = 0; }
    E.timer=setTimeout(()=>{E.timer=0;if(E.dirty&&!E.composing&&!cardNote?.value.trim())commitEdit('autosave');},900);
  }
}

function wireEditor() {
  wireAtomicObjects();
  docEl.addEventListener("beforeinput", onBeforeInput);
  docEl.addEventListener("input", onEditInput);
  docEl.addEventListener("compositionstart", () => {
    E.composing = true;
    if (E.timer) { clearTimeout(E.timer); E.timer = 0; }
  });
  docEl.addEventListener("compositionend", (ev) => {
    E.composing = false;
    onEditInput(ev);
  });
  // blur PARKS (the parking model; the blur-bank is retired): focus leaving the edited
  // paragraph holds the words and the amber edge — banking stays his hand's act.
  // A press on the edit card is not a leave — the card IS the edit's own surface.
  docEl.addEventListener("focusout", (ev) => {
    if (!E.blockId || !E.dirty || E.committing) return;
    // The leaving block is the established E snapshot. A selection that has
    // already moved must not make blur park a different/new block.
    const host=ev.target?.closest?.('.blk-body[contenteditable="true"]')
      ||(ev.target===docEl?blockById.get(E.blockId)?.bodyEl:null);
    if (!host) return;
    const to = ev.relatedTarget;
    if (to && (host.contains(to) || (CARD && CARD.contains(to)))) return;
    const blkEl = closestBlock(host);
    const b = blkEl ? blockById.get(blkEl.dataset.block) : null;
    if (b && b.id === E.blockId) parkEdit(b);
  });
  // leaving the page with standing parks is the one dialog that is earned: his drafts.
  window.addEventListener("beforeunload", (ev) => {
    if (document.querySelector('.pending-paragraph.unsaved') || document.querySelector('.proposal-merge-editor[data-unstored]') || P.size || (
      E.blockId && E.dirty) || (F.blockId && F.ta && F.ta.value !== (F.baseTex??blockById.get(F.blockId)?.tex??""))) { ev.preventDefault(); ev.returnValue = ""; }
  });
  // CUT and PASTE across paragraphs (the browser cannot serve either over split
  // hosts): cut = the copy plus the cross-paragraph delete; paste = the
  // cross-paragraph rewrite carrying the clipboard's text (its paragraph breaks land
  // as real breaks). Within one block both keep their native paths.
  document.addEventListener("cut", (ev) => {
    const sel = document.getSelection();
    if (!sel || sel.isCollapsed || !sel.rangeCount) return;
    const r = sel.getRangeAt(0);
    const a = closestBlock(r.startContainer), z = closestBlock(r.endContainer);
    if (!a || !z || a === z) return;
    ev.preventDefault();
    if (ev.clipboardData) ev.clipboardData.setData("text/plain", sel.toString());
    crossBlockRewrite(r, "");
  });
  document.addEventListener("paste", (ev) => {
    const sel = document.getSelection();
    if (!sel || sel.isCollapsed || !sel.rangeCount) return;
    const r = sel.getRangeAt(0);
    const a = closestBlock(r.startContainer), z = closestBlock(r.endContainer);
    if (!a || !z || a === z) return;
    const plain = ev.clipboardData ? ev.clipboardData.getData("text/plain") : "";
    ev.preventDefault();
    if (plain) crossBlockRewrite(r, plain.replace(/\r\n/g, "\n"));
  });
  // the caret placed in a paragraph summons the card: the provenance and the altitude
  // are visible BEFORE the first keystroke — that is the free-floating point.
  docEl.addEventListener("focusin", (ev) => {
    const host=eventEditingHost(ev);
    if (!host) return;
    const blkEl = closestBlock(host);
    const b = blkEl ? blockById.get(blkEl.dataset.block) : null;
    if (!b) return;
    snapshotEdit(b, host);
    if (E.blockId !== b.id || !E.dirty) {
      const held = P.get(b.id);
      if (held) {
        // the delta said BEFORE Esc is pressed — an informed revert, never a gamble
        const d = parkDiff(held);
        showCard(b, "unbanked here: " + (d.minus ? "− " + d.minus + " " : "")
          + (d.plus ? "+ " + d.plus : "")
          + (held.pendingRow ? " · banked PENDING " + held.pendingRow : "")
          + " · Ctrl-S banks · Esc reverts", "");
      } else {
        showCard(b, "typing edits · parks until you bank · Ctrl-S banks · Esc reverts", "");
      }
    }
  });
  // the card follows the caret as he types and moves — the echo of his own gesture
  let caretRaf = 0;
  document.addEventListener("selectionchange", () => {
    if (!CARD || CARD.hidden || root.classList.contains('writing-embedded')) return;
    const active = document.activeElement;
    const host = active && active.closest
      ? active.closest('.blk-body[contenteditable="true"]') : null;
    if (!host) return;
    const blkEl = closestBlock(host);
    const b = blkEl ? blockById.get(blkEl.dataset.block) : null;
    if (!b) return;
    if (!caretRaf) {
      caretRaf = requestAnimationFrame(() => { caretRaf = 0; positionCard(b); });
    }
  });
  // a press outside the paragraphs and the card puts the card away — and a return to
  // the paper puts the BAND away too (the echo was seen; the reading resumes).
  docEl.addEventListener("mousedown", (ev) => {
    if (C.rail === "band" && !C.armed && !C.needActor) openRail("strip");
    if (!CARD || CARD.hidden) return;
    const t = ev.target;
    if (CARD.contains(t)) return;
    if (t && t.closest && t.closest('.blk-body[contenteditable="true"]')) return;
    hideCard();
  });
  // click on an island (outside the cite buttons, which wire themselves): its source,
  // in place. A drag that ENDS on an island is a selection, not a click — skipped.
  docEl.addEventListener("click", (ev) => {
    if (liveRange()) return;
    const t = ev.target;
    const island = t && t.closest ? t.closest(".mathq, .ref, .unknown") : null;
    if (island && docEl.contains(island) && !island.closest(".flip")) {
      islandSource(island, "");
      return;
    }
    // a figure or caption clicked: the card opens with its asks — tag-for-remake, a note
    const blkEl = closestBlock(t);
    const b = blkEl ? blockById.get(blkEl.dataset.block) : null;
    if (b && (b.kind === "figure" || b.kind === "caption") && !F.blockId) {
      showCard(b, (figLabelOf(b) ? figLabelOf(b) + " — " : "")
        + "a note banks a comment on this figure; the tag banks a remake request", "");
    }
  });
}

export {eventEditingHost, islandSource, onEditInput, wireEditor};
