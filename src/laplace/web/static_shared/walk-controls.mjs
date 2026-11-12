// WALK CONTROLS (S2 F8). Purpose: the walk's key map and control wiring: the global key handler,
// the composer's keys, and the DOM listeners of the controls and composer. Owns: the geometry frame
// handle. Public contract: wireControls, wireComposer, inField. Wired once by open() in walk.mjs.
import {
  $, DWELL_TICK_MS, clamp, docEl, door, geoBack, geoDoor, geoScroll, keymap, listeners, paper, root
} from './walk-base.mjs';
import {blockById, paintBackDoor} from './walk-document.mjs';
import {
  S, accrueDwell, captureFocus, jumpToIndex, measure, onScroll, railPx, readingY, releaseJumpAnchor,
  restoreFocus, scheduleRemeasure, sectionAtY, setSpan, settleJumpAnchor, takeDoor, toggleSpine, zoomFit,
  zoomIn, zoomOut
} from './walk-position.mjs';
import {repaintFigures} from './walk-media.mjs';
import {G, closeGeometry, geoMeasure, geoRenderVisible, toggleGeometry} from './walk-geometry.mjs';
import {
  C, SCOPES, armArtefact, armBlockAtReadingLine, armFromSelection, armSpan, autosize, bandSpan,
  compActorInput, compActorOk, compBody, compQuote, compSuggest, composer, disarm, loadActor, nameActor,
  openRail, renderComposer, rulingKey, setScope, toggleRail, updateSuggestion
} from './walk-composer.mjs';
import {closestBlock, hostText, offsetIn} from './walk-selection.mjs';
import {E, P, revertEdit, revertParked} from './walk-drafts.mjs';
import {undoEditorChange} from './walk-edit-history.mjs';
import {bankDeposit, undoLast} from './walk-bank.mjs';
import {
  L, closeLedger, ledgerEl, renderBand, renderSpanDoor, toggleLedger, toggleRedline
} from './walk-band.mjs';
import {F, cancelFlip, flipBlock, focusedBlock, saveFlip} from './walk-flip.mjs';
import {commitAll, crossBlockRewrite} from './walk-editing.mjs';
import {
  CARD, cardFromSelection, cardNote, findNext, hideCard, openFindDialog, paintCardState, setEditScope,
  showCard, wrapSelection
} from './walk-card.mjs';
import {joinBlocks, paragraphTransition} from './walk-paragraph-ops.mjs';
import {eventEditingHost} from './walk-edit-input.mjs';

function inField(t) {
  return !!(t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable));
}

function onKey(ev) {
  const t = ev.target;

  // A nearer handler that already acted owns the key. The composer's own chain runs first
  // (it is inside this document and the event bubbles up through it); without this, an
  // Alt+digit taken there would be taken again here and `setScope`'s toggle would put the
  // altitude straight back off in the same keystroke.
  if (ev.defaultPrevented) return;
  if(paragraphTransition&&(ev.ctrlKey||ev.metaKey)&&String(ev.key).toLowerCase()==='z'&&!ev.shiftKey){ev.preventDefault();paragraphTransition.undoRequested=true;return;}

  // ALT+digit is the scope key from anywhere — the paper, a flipped block's source
  // textarea, the band, the composer. It is the one gesture that never depends on where
  // the caret is, which is why it is checked before the modifier bail below.
  if (ev.altKey && scopeKey(ev)) { ev.preventDefault(); return; }
  // ... and 7/8/9 the same way: the RULING on the passage, reachable wherever the caret is,
  // because it is set in the same breath as the altitude and from the same gesture.
  if (ev.altKey && rulingKey(ev)) { ev.preventDefault(); return; }

  // Ctrl-S anywhere while a block is flipped, a typed edit is in flight, or ANY block
  // stands parked: the browser's save dialog never opens here — the key banks everything
  // standing (the parking model: Ctrl-S is THE bank, and it banks all).
  if ((ev.ctrlKey || ev.metaKey) && String(ev.key).toLowerCase() === "s"
      && (F.blockId || (E.blockId && E.dirty) || P.size)) {
    ev.preventDefault();
    if (F.blockId) saveFlip({keepOpen:true}); else commitAll();
    return;
  }
  // Ctrl-Z GUARDED (the divergence class): native undo outside an in-flight edit can
  // resurrect a pre-bank face over a source that has moved — silently wrong. Inside
  // the current unbanked edit it is native and welcome; everywhere else the words say
  // what undo means here (u revokes rows, Esc reverts parks).
  if ((ev.ctrlKey || ev.metaKey) && !ev.altKey
      && (String(ev.key).toLowerCase() === "z" || String(ev.key).toLowerCase() === "y")) {
    const host = t && t.closest ? t.closest('.blk-body[contenteditable="true"]') : null;
    if (host) {
      const blkEl = closestBlock(host);
      const b = blkEl ? blockById.get(blkEl.dataset.block) : null;
      if (b && !(E.blockId === b.id && E.dirty)) {ev.preventDefault();undoEditorChange(ev.shiftKey||String(ev.key).toLowerCase()==='y');return;}
    }
    if(!host&&t?.tagName!=='TEXTAREA'&&t?.tagName!=='INPUT'){ev.preventDefault();undoEditorChange(ev.shiftKey||String(ev.key).toLowerCase()==='y');return;}
  }

  // Ctrl/⌘ I, B, M inside an editable paragraph: italic, bold, inline math as typed TeX
  // (his ruling 2026-09-29). Anywhere else these keys keep their browser meaning.
  if ((ev.ctrlKey || ev.metaKey) && !ev.altKey && !ev.shiftKey) {
    const k = String(ev.key).toLowerCase();
    if(k==='f'){ev.preventDefault();openFindDialog();return;}
    if(k==='g'){ev.preventDefault();findNext();return;}
    const cmd = k === "i" ? "emph" : k === "b" ? "textbf" : k === "m" ? "math" : "";
    const host = cmd && t && t.closest ? t.closest('.blk-body[contenteditable="true"]') : null;
    if (host) { ev.preventDefault(); wrapSelection(cmd); return; }
  }

  if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
  if(ev.key==='Backspace'||ev.key==='Delete'){
    const selection=document.getSelection(),range=selection?.rangeCount?selection.getRangeAt(0):null,host=eventEditingHost(ev);
    if(range?.collapsed&&host&&host.contains(range.startContainer)){const offset=offsetIn(host,range.startContainer,range.startOffset),
      back=ev.key==='Backspace';if(back&&offset===0||!back&&offset===hostText(host).length){ev.preventDefault();const block=blockById.get(
      closestBlock(host)?.dataset.block);if(block)joinBlocks(block,back?'prev':'next');return;}}
  }

  // A selection across paragraphs + an edit key IS a rewrite (his friction #1,
  // 2026-08-11: the commonest rework gesture — grab the end of one paragraph and the
  // start of the next, retype the transition). The hosts are separate editors, so the
  // browser cannot do it; the door can, as one spliced rewrite. Never when a real
  // field owns the caret.
  if (ev.key.length === 1 || ev.key === "Backspace" || ev.key === "Delete") {
    const sel = document.getSelection();
    if (sel && !sel.isCollapsed && sel.rangeCount) {
      const r = sel.getRangeAt(0);
      const a = closestBlock(r.startContainer), z = closestBlock(r.endContainer);
      if (a && z && a !== z
          && !(t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA"))) {
        ev.preventDefault();
        crossBlockRewrite(r, ev.key.length === 1 ? ev.key : "");
        return;
      }
    }
  }

  if (ev.key === "Escape") {
    // one order, said once in the key map: the most recently opened thing closes first.
    if (!keymap.hidden) { keymap.hidden = true; ev.preventDefault(); return; }
    if (L.open) { closeLedger(); ev.preventDefault(); return; }
    if (CARD && !CARD.hidden && cardNote && cardNote.value) {
      cardNote.value = ""; autosize(cardNote, 0.2); paintCardState();
      ev.preventDefault(); return;
    }
    if (E.selAnchor) { hideCard(); ev.preventDefault(); return; }
    if (E.blockId && E.dirty) { revertEdit(); ev.preventDefault(); return; }
    if (F.blockId) { cancelFlip(); ev.preventDefault(); return; }
    {
      // Esc on a PARKED block he has clicked into but not yet typed in: same meaning,
      // same key — the park drops and the source shows (the informed revert; the card
      // said the delta at focus). Below the flip rung: with a flip open on a parked
      // block, Esc closes the flip back onto the park; the NEXT Esc reverts it.
      const pb = focusedBlock();
      if (pb && P.has(pb.id)) {
        revertParked(pb.id);
        showCard(pb, "reverted — the paragraph shows the source; nothing stands here", "");
        ev.preventDefault();
        return;
      }
    }
    if (G.open) { closeGeometry(); ev.preventDefault(); return; }
    if (C.armed) { disarm(); ev.preventDefault(); return; }
    if (takeDoor()) { ev.preventDefault(); return; }
    if (S.span) { setSpan(null); ev.preventDefault(); }
    return;
  }
  if (inField(t)) return;              // the composer's own keys are wired to the composer
  if (ev.key === "?") { keymap.hidden = !keymap.hidden; ev.preventDefault(); return; }
  if (!keymap.hidden) return;
  // the ledger history is modal too: while it is open the only key that acts is the one
  // that closes it, so nothing behind it moves under an overlay he cannot see through.
  if (L.open) {
    if (ev.key === "l") { closeLedger(); ev.preventDefault(); }
    return;
  }

  if (ev.key === "0") { armArtefact(); ev.preventDefault(); return; }
  if (rulingKey(ev)) { ev.preventDefault(); return; }
  if (ev.key === "u") { undoLast(); ev.preventDefault(); return; }
  if (ev.key === "s") { flipBlock(focusedBlock()); ev.preventDefault(); return; }
  if (ev.key === "g") { toggleGeometry(); ev.preventDefault(); return; }
  if (ev.key === "l") { toggleLedger(); ev.preventDefault(); return; }
  if (ev.key === "Enter") {
    // a focused button is being ACTIVATED by this Enter; the walk does not also act on it.
    if (t && (t.tagName === "BUTTON" || t.tagName === "A")) return;
    if (S.span) { armSpan(); ev.preventDefault(); return; }
    if (armFromSelection() || armBlockAtReadingLine()) { ev.preventDefault(); return; }
    return;
  }
  if (ev.key === "r") { toggleRedline(); ev.preventDefault(); return; }
  if (ev.key === "b") { toggleRail(); ev.preventDefault(); return; }
  if (ev.key === "o") { toggleSpine(); ev.preventDefault(); return; }
  if (ev.key === "n" || ev.key === "p") {
    if (!S.sections.length) return;
    const here = S.current >= 0 ? S.current : sectionAtY(readingY());
    const next = clamp(ev.key === "n" ? here + 1 : here - 1, 0, S.sections.length - 1);
    if (next !== here || ev.key === "p") jumpToIndex(next);
    ev.preventDefault();
    return;
  }
  if (ev.key === "+" || ev.key === "=") { zoomIn(); ev.preventDefault(); return; }
  if (ev.key === "-" || ev.key === "_") { zoomOut(); ev.preventDefault(); return; }
  if (ev.key === "f") { zoomFit(); ev.preventDefault(); }
}

/** the felt mode boundary — ONE DECISION, in one place, for every surface the key lands on.
 *
 *  Three lines, and they hold everywhere:
 *
 *    · inside ANY text field a bare digit TYPES. Period. The passage, the note, the actor
 *      box, a flipped block's source. The caret is the whole rule and he can see it.
 *    · on composer CHROME — a scope chip, the shape line, the routing line, an unscoped
 *      row in the band: places with nothing to type into — a bare digit sets the scope.
 *    · Alt+digit sets the scope from ANYWHERE, fields included.
 *
 *  The history this closes, in order. The first boundary was "the note is empty and holds
 *  the caret" — a state the dominant gesture never reaches, because arming puts the caret
 *  in the PASSAGE: a bare `1` typed a stray digit into the frozen quote and Enter banked a
 *  rewrite of his paragraph with a `1` in it. The second boundary fixed the field case and
 *  left Alt+digit reachable ONLY from inside the composer element, so the one key promised
 *  to work "wherever the caret is" did nothing in the paper or in a flipped block. This is
 *  the third: `scopeKey` is called from the composer's chain AND from the document's, and
 *  the document's chain bails on any key a nearer handler already took.
 *
 *  And the digit that DOES type is never silent: the quote's input handler re-renders the
 *  composer in the same frame, the passage's own label flips to say it is now edited, and
 *  the shape line reads REWRITE — the conversion is stated where he is looking, not
 *  discovered at the receipt. */
function scopeKey(ev) {
  if (ev.ctrlKey || ev.metaKey) return false;
  if (!/^[1-6]$/.test(ev.key)) return false;
  if (!ev.altKey && inField(ev.target)) return false;   // in a field a bare digit TYPES
  const s = SCOPES[Number(ev.key) - 1];
  if (C.armed) { setScope(s, "chosen"); return true; }
  // no composer armed but the edit card is live: the digits set THAT altitude —
  // same keys, same six, at the point of the edit.
  if (E.blockId && CARD && !CARD.hidden) {
    setEditScope(E.scope === s ? "" : s);
    return true;
  }
  return false;
}

function onComposerKey(ev) {
  if (ev.key === "Escape") {
    // stopped here: the document's Escape chain would otherwise run a SECOND rung on the
    // same key press (the span would clear behind the disarm he actually asked for).
    ev.stopPropagation();
    disarm();
    ev.preventDefault();
    return;
  }
  if (scopeKey(ev)) { ev.preventDefault(); return; }
  if (rulingKey(ev)) { ev.preventDefault(); return; }
  if (ev.target === compActorInput) {
    if (ev.key === "Enter") { nameActor(); ev.preventDefault(); }
    return;
  }
  if (!C.armed) return;
  if (ev.key === "Enter" && !ev.shiftKey && !ev.altKey && !ev.ctrlKey && !ev.metaKey) {
    // A focused button is being activated by this enter, not banking with it. The hint
    // line sends him to a scope chip for the bare digits; swallowing Enter there would
    // bank the deposit instead of setting the altitude he had just tabbed to — the
    // document's own key chain has held this rule since the beginning, and the composer
    // has to hold it too now that the chips are a named destination.
    const t2 = ev.target;
    if (t2 && (t2.tagName === "BUTTON" || t2.tagName === "A")) return;
    ev.preventDefault();
    bankDeposit();
  }
}

function wireControls() {
  paintBackDoor();          // the way back is live before any door has answered
  $("zoom-in").addEventListener("click", zoomIn);
  $("zoom-out").addEventListener("click", zoomOut);
  $("zoom-fit").addEventListener("click", zoomFit);
  $("spine-toggle").addEventListener("click", toggleSpine);
  $("keys").addEventListener("click", () => { keymap.hidden = !keymap.hidden; });
  keymap.addEventListener("click", (ev) => { if (ev.target === keymap) keymap.hidden = true; });
  door.addEventListener("click", () => takeDoor());
  geoDoor.addEventListener("click", () => toggleGeometry());
  geoBack.addEventListener("click", () => closeGeometry());
  $("ledger-door").addEventListener("click", () => toggleLedger());
  $("ledger-close").addEventListener("click", () => closeLedger());
  $("ledger-x").addEventListener("click", () => closeLedger());
  // the rail's mouse doors: the strip opens the band, the band's ✕ collapses it.
  $("rail-strip").addEventListener("click", () => openRail("band"));
  $("band-collapse").addEventListener("click", () => openRail("strip"));
  ledgerEl.addEventListener("click", (ev) => { if (ev.target === ledgerEl) closeLedger(); });
  paper.addEventListener("scroll", onScroll, { passive: true });
  paper.addEventListener('wheel',releaseJumpAnchor,{passive:true});
  paper.addEventListener('touchstart',releaseJumpAnchor,{passive:true});
  root.addEventListener('pointerdown',releaseJumpAnchor,{capture:true});
  document.addEventListener('keydown',releaseJumpAnchor,{capture:true});
  if('ResizeObserver' in window){const toolbarResize=new ResizeObserver(scheduleRemeasure);toolbarResize.observe($('bar'));}
  geoScroll.addEventListener("scroll", () => {
    if (!geoRaf) geoRaf = requestAnimationFrame(() => { geoRaf = 0; geoRenderVisible(); });
  }, { passive: true });
  document.addEventListener("keydown", onKey);

  // a click in a block focuses it, so `s` has a subject without a pointer convention.
  let focusedBlock = null;
  docEl.addEventListener("mousedown", (ev) => {
    const n = closestBlock(ev.target);
    if (!n || n === focusedBlock) return;
    if (focusedBlock) delete focusedBlock.dataset.focus;
    n.dataset.focus = "1";
    focusedBlock = n;
  });

  // a window resize is NOT a rescale (G2): the margins absorb it, the focal point holds.
  let resizeTimer = 0;
  window.addEventListener("resize", () => {
    if (resizeTimer) clearTimeout(resizeTimer);
    const f = captureFocus();
    resizeTimer = setTimeout(() => {
      resizeTimer = 0;
      root.style.setProperty("--rail-w", railPx(C.rail) + "px");
      measure(); if(!settleJumpAnchor())restoreFocus(f);
      repaintFigures();
      if (G.open && G.loaded) { geoMeasure(); geoRenderVisible(); }
    }, 120);
  });

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) accrueDwell(); else S.dwellStamp = performance.now();
  });
  // dwell accrues on the timer; the tints do not repaint on it. Time has to keep being
  // booked while he sits still — that IS the measurement. But `paintCoverage()` rode this
  // same tick, so a section flipped partial → walked under his eye every two seconds while
  // he was motionless: a render outside his gesture and outside the coarse boundaries, and
  // the no-motion law does not bend for a tint. The tints update at scroll-idle (`onIdle`)
  // and at a section change (`updateCurrent`) — nowhere else.
  setInterval(() => {                 // dwell accrues while he sits still and reads
    if (document.hidden || S.idleTimer || G.open) return;
    accrueDwell();
  }, DWELL_TICK_MS);
}

let geoRaf = 0;

function wireComposer() {
  C.actor = loadActor();
  composer.addEventListener("keydown", onComposerKey);
  // every keystroke in the passage re-renders the composer, in the same frame. A bare
  // digit typed here (the felt boundary: in a field, a digit types) turns the deposit from
  // a comment into a REWRITE, and that conversion has to be VISIBLE at the moment it
  // happens — the passage's label flips to say it is edited, the shape line reads REWRITE,
  // and the routing line names the altitude the rewrite door will actually apply.
  compQuote.addEventListener("input", () => {
    autosize(compQuote, 0.34);
    updateSuggestion();
    renderComposer();
  });
  compBody.addEventListener("input", () => {
    autosize(compBody, 0.26);
    updateSuggestion();
    renderComposer();
  });
  compSuggest.addEventListener("click", () => {
    if (C.suggested) setScope(C.suggested, "inferred");   // he took the machine's lean
  });
  compActorOk.addEventListener("click", nameActor);
  bandSpan.addEventListener("click", armSpan);

  // a selection in the text summons the CARD at the text (his ruling 2026-08-10: the
  // rail claimed too much width for too little beside the card). The keyboard Enter
  // path still arms the docked composer; the whole-paper (0) and span composers too.
  let armTimer = 0;
  const maybeArm = () => {
    if (root.classList.contains("writing-enabled")) return;
    if (armTimer) clearTimeout(armTimer);
    armTimer = setTimeout(() => { armTimer = 0; if (!F.blockId) cardFromSelection(); }, 40);
  };
  paper.addEventListener("mouseup", maybeArm);
  paper.addEventListener("keyup", (ev) => { if (ev.shiftKey) maybeArm(); });
  listeners.span.add(() => renderSpanDoor());   // what api.on("span", …) does
  renderBand();
}

export {inField, wireComposer, wireControls};
