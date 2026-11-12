// WALK CARD (S2 F7). Purpose: the edit card at the caret: its notes, scope and asks, banking a card
// comment, and the text tools it offers (wrapping, insertion points, reference picker and find).
// Owns: CARD and its DOM handles, the pending citation placement. Public contract: showCard/hideCard/
// positionCard, paintCardState, cardFromSelection, bankCardComment, setEditScope, wrapSelection,
// insertEditorText, editorInsertionPoint/contextualInsertionPoint/caretRange, armCitationPlacement,
// openReferencePicker, openFindDialog/findNext, yieldComposer.
import store from "/shared/store.mjs";
import {referenceCommand} from "/shared/manuscript-editing.mjs";
import {clamp, docEl, el, emit, norm, paper, root, text} from './walk-base.mjs';
import {D, blockById} from './walk-document.mjs';
import {S, sectionTitle} from './walk-position.mjs';
import {saveSourceChange, setPayload} from './walk-source-client.mjs';
import {asChrome} from './walk-blocks.mjs';
import {
  C, SCOPES, askActor, autosize, compBody, compQuote, dropArmedMark, ledgerPath, paintMarks, renderComposer,
  settleRail
} from './walk-composer.mjs';
import {
  anchorForWholeBlock, anchorFromRange, closestBlock, figLabelOf, hostText, liveRange, offsetIn, readableDOM,
  sourceForRenderedRange, srcLabel, srcOf
} from './walk-selection.mjs';
import {E, P, paintParked, snapshotEdit} from './walk-drafts.mjs';
import {commentPayload} from './walk-bank.mjs';
import {MINTED, admit, paintDeposits, renderBand} from './walk-band.mjs';
import {F} from './walk-flip.mjs';
import {commitEdit, editableBlock} from './walk-editing.mjs';
import {blockLabels, toggleWhere} from './walk-where.mjs';
import {onEditInput} from './walk-edit-input.mjs';

// ── the edit card — the free-floating point at the caret (his verdict, 2026-08-10 remote:
// the side panel is too far from the hands; the provenance and the altitude of the edit
// were invisible at the point of edit). It floats INVITED — summoned by his caret, the
// focal point, never an occlusion (the "nothing floats uninvited" refinement). It names
// where the text comes from (the source line span), takes the altitude right there (six
// chips; Alt+1–6 still works from anywhere), and says the banking state in place. The
// side panel remains the LEDGER of banked rows; the working surface is this card. ──────

let CARD = null, cardSrc = null, cardScopes = null, cardStatus = null;
let cardNote = null, cardWhere = null, cardWhereBtn = null, cardAsks = null, cardSave = null;

function ensureCard() {
  if (CARD) return CARD;
  CARD = el("div");
  CARD.id = "edit-card";
  CARD.hidden = true;
  // a press on the card never steals the caret he is typing with — EXCEPT the note
  // field, which is the card's own place to type.
  CARD.addEventListener("mousedown", (ev) => {
    if (cardNote && (ev.target === cardNote || cardNote.contains(ev.target))) return;
    ev.preventDefault();
  });
  cardSrc = el("div", "ec-src");
  CARD.appendChild(cardSrc);
  cardScopes = el("div", "ec-scopes");
  cardScopes.appendChild(el("span", "ec-lead", "altitude (sentence unless set):"));
  SCOPES.forEach((s, i) => {
    const c = el("button", "ec-chip", (i + 1) + " " + s);
    c.type = "button";
    c.dataset.scope = s;
    c.setAttribute("aria-pressed", "false");
    c.addEventListener("click", (ev) => {
      ev.preventDefault();
      setEditScope(E.scope === s ? "" : s);
    });
    cardScopes.appendChild(c);
  });
  const options = el("details", "ec-options");
  options.appendChild(el("summary", "", "Feedback scope"));
  options.appendChild(cardScopes);
  CARD.appendChild(options);
  // THE NOTE — a comment from the card, at the point (his ask: "leave a comment in the
  // floating box"). A note alone banks a comment; a note beside a typed edit banks the
  // compound row (replacement + rationale). Enter banks; Shift-Enter is a new line.
  cardNote = el("textarea", "ec-note");
  cardNote.rows = 1;
  cardNote.setAttribute("aria-label", "Optional note about this passage");
  cardNote.placeholder = "Add a note (optional)";
  cardNote.addEventListener("focus", () => {
    // the pending edit WAITS while he writes the note: no pause-bank under his typing
    if (E.timer) { clearTimeout(E.timer); E.timer = 0; }
  });
  cardNote.addEventListener("input", () => {
    autosize(cardNote, 0.2);
    paintCardState();
  });
  cardNote.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey && !ev.altKey && !ev.ctrlKey && !ev.metaKey) {
      ev.preventDefault();
      ev.stopPropagation();
      cardBank();
    }
  });
  CARD.appendChild(cardNote);
  cardSave = el("button", "ec-save", "Save changes / note");
  cardSave.type = "button";
  cardSave.addEventListener("click", () => cardBank());
  CARD.appendChild(cardSave);
  cardAsks = el("div", "ec-asks");
  CARD.appendChild(cardAsks);
  cardWhereBtn = el("button", "ec-where-btn", "where this sits · links");
  cardWhereBtn.type = "button";
  cardWhereBtn.addEventListener("click", (ev) => {
    ev.preventDefault();
    toggleWhere();
  });
  CARD.appendChild(cardWhereBtn);
  cardWhere = el("div", "ec-where");
  cardWhere.hidden = true;
  CARD.appendChild(cardWhere);
  cardStatus = el("div", "ec-status");
  CARD.appendChild(cardStatus);
  paper.appendChild(CARD);
  return CARD;
}

function cardBlock() {
  return CARD && CARD.dataset.block ? blockById.get(CARD.dataset.block) : null;
}

/** What Enter will bank, said before he presses it — the shape truth at the card. */
function paintCardState() {
  if (!CARD || CARD.hidden) return;
  const note = cardNote.value.trim();
  if (E.dirty && note) {
    text(cardStatus, "Unsaved changes and note · Save or Ctrl / ⌘ S · Esc cancels");
  } else if (E.dirty) {
    text(cardStatus, "Unsaved changes · Save or Ctrl / ⌘ S · Esc cancels");
  } else if (note) {
    text(cardStatus, "Save this note with its passage · Enter also saves");
  }
  delete cardStatus.dataset.tone;
}

/** A selection held to the card: the anchor is captured NOW (mouseup) because the
 *  live selection dies the moment the note field takes focus. The persistent mark is
 *  the retrieval cue, exactly as the composer path painted it. */
function cardFromSelection() {
  const range = liveRange();
  if (!range) return false;
  const a = anchorFromRange(range);
  if (!a) return false;
  const b = blockById.get(a.blockId);
  if (!b) return false;
  E.selAnchor = a;
  dropArmedMark();
  if (a.end > a.start) {
    C.marks.push({ blockId: a.blockId, start: a.start, end: a.end, armed: true });
    paintMarks();
  }
  showCard(b, "selection held — a note banks a comment on it; typing over it edits it; "
    + "a chip scopes it", "");
  paintCardState();
  return true;
}

/** Enter at the card: the object he touched decides — note alone banks a comment,
 *  a typed edit banks a rewrite, both bank the compound row. No mode, no extra key. */
function cardBank() {
  const b = cardBlock();
  if (!b) return;
  if (E.dirty && E.blockId === b.id) { commitEdit("card-enter"); return; }
  bankCardComment(b);
}

async function bankCardComment(b, request) {
  const typed = cardNote ? cardNote.value.trim() : "";
  const note = request ? request + (typed ? " — " + typed : "") : typed;
  if (!note) {
    showCard(b, "there is nothing to bank — the note is empty and the paragraph is "
      + "unchanged.", "refused");
    return null;
  }
  if (!C.actor) {
    showCard(b, "this comment needs an actor before it banks", "refused");
    askActor("a comment is actor-attributed and the door defaults nowhere. Name who is "
           + "depositing and it banks.", () => { bankCardComment(b, request); });
    return null;
  }
  // the anchor: the selection the card HOLDS (captured at mouseup — the live one died
  // when the note took focus), else a live selection in this block, else the paragraph
  let a = null;
  if (E.selAnchor && E.selAnchor.blockId === b.id) a = E.selAnchor;
  if (!a) {
    const range = liveRange();
    if (range) {
      const blkEl = closestBlock(range.commonAncestorContainer);
      if (blkEl && blkEl.dataset.block === b.id) a = anchorFromRange(range);
    }
  }
  if (!a) a = anchorForWholeBlock(b);
  const payload = commentPayload(a, note);
  // `setPayload`, not a top-level assignment: this body is a grammar request whenever the
  // gesture has an altitude, and a key written beside `verb`/`concept` there is a restated
  // request field at best and silently dropped at worst.
  setPayload(payload, "surface", "walk");
  setPayload(payload, "source", "card-note");
  if (E.scope) { setPayload(payload, "scope", E.scope);
                 setPayload(payload, "scope_source", "chosen"); }
  else if (request) {
    setPayload(payload, "scope",
               request.indexOf("new section") >= 0 ? "structure" : "delivery");
    setPayload(payload, "scope_source", "chosen");
  }
  let res;
  try {
    res = await saveSourceChange(payload);
  } catch (e) {
    showCard(b, "REFUSED — nothing was banked. " + e.message, "refused");
    return null;
  }
  const rec = (res && res.record) || {};
  const id = rec.id || "(no id returned)";
  const collided = C.mine.has(id);
  // the armed mark becomes the deposit's trace; a fresh anchor paints its own
  let marked = false;
  for (const m of C.marks) if (m.armed) { m.armed = false; m.id = id; marked = true; }
  if (!marked && a.grade === "selection" && a.end > a.start) {
    C.marks.push({ blockId: a.blockId, start: a.start, end: a.end, id });
  }
  paintMarks();
  E.selAnchor = null;
  const row = {
    id, ts: rec.ts || new Date().toISOString(), kind: "comment",
    scope: rec.scope || E.scope
        || (request ? (request.indexOf("new section") >= 0 ? "structure" : "delivery") : ""),
    scope_source: rec.scope_source || (E.scope ? "chosen" : ""),
    suggested_scope: "", grade: res.grade || "block",
    comment: note, before: "", after: "",
    section: b.sectionId || "", sections: null, blockId: b.id,
    file: a.file || "", by: C.actor, quote: a.quote || "", state: "open", mine: true,
    applied: false, pending: false,
  };
  const listed = admit(row, MINTED);
  C.last = (collided || !listed) ? null : row;
  cardNote.value = "";
  autosize(cardNote, 0.2);
  setEditScope("");
  showCard(b, "banked " + id + " → " + ledgerPath()
    + (row.scope ? " · " + row.scope : " · unscoped — scopeable from the band")
    + " · comment · u revokes", "banked");
  renderComposer();
  renderBand();
  paintDeposits();
  emit("bank", { id, shape: "comment", applied: false, pending: false,
                 source: "card-note" });
  return row;
}

function setEditScope(s) {
  E.scope = s;
  if (!CARD) return;
  for (const c of cardScopes.querySelectorAll(".ec-chip")) {
    c.setAttribute("aria-pressed", c.dataset.scope === E.scope ? "true" : "false");
  }
}

/** The card sits at the caret's line — below it, above it when the pane runs out. */
function positionCard(b) {
  if (!CARD || CARD.hidden || root.classList.contains('writing-embedded')) return;
  let rect = null;
  const sel = window.getSelection();
  if (sel && sel.rangeCount && b && b.bodyEl
      && b.bodyEl.contains(sel.getRangeAt(0).startContainer)) {
    const r = sel.getRangeAt(0).cloneRange();
    r.collapse(false);
    rect = r.getBoundingClientRect();
    if (rect && !rect.height && !rect.width) rect = null;
  }
  if (!rect && b && b.el) rect = b.el.getBoundingClientRect();
  if (!rect) return;
  const pr = paper.getBoundingClientRect();
  const cw = CARD.offsetWidth || 300, ch = CARD.offsetHeight || 70;
  let top = rect.bottom - pr.top + paper.scrollTop + 8;
  if (rect.bottom + ch + 14 > pr.bottom) {
    top = rect.top - pr.top + paper.scrollTop - ch - 8;
  }
  const left = clamp(rect.left - pr.left + paper.scrollLeft,
                     paper.scrollLeft + 4,
                     paper.scrollLeft + paper.clientWidth - cw - 8);
  CARD.style.top = Math.max(0, top) + "px";
  CARD.style.left = left + "px";
}

function showCard(b, words, tone) {
  ensureCard();
  if (CARD.dataset.block !== b.id) {
    // a new subject: the note, the held selection, and the links view belong to the
    // block they were opened on, never carried silently onto another. A half-written
    // note is his intermediate — it PARKS with its block instead of dying here.
    if (CARD.dataset.block && cardNote.value) {
      const prevId = CARD.dataset.block;
      const held = P.get(prevId);
      const prevB = blockById.get(prevId);
      if (held) held.note = cardNote.value.trim();
      else if (prevB && prevB.bodyEl) {
        const tprev = hostText(prevB.bodyEl);
        P.set(prevId, { pristine: tprev, text: tprev, scope: E.scope || "",
                        note: cardNote.value.trim(), src: { ...srcOf(prevB) },
                        tex: prevB.tex || "", noteOnly: true });
        if (prevB.el) prevB.el.dataset.parked = "1";
        paintParked();
      }
      cardNote.value = "";
      autosize(cardNote, 0.2);
    }
    if (E.selAnchor && E.selAnchor.blockId !== b.id) {
      E.selAnchor = null;
      dropArmedMark();
      paintMarks();
    }
    cardWhere.hidden = true;
    text(cardWhereBtn, "where this sits · links");
  }
  CARD.dataset.block = b.id;
  text(cardSrc, srcLabel(b));
  paintCardAsks(b);
  text(cardStatus, words);
  if (tone) cardStatus.dataset.tone = tone; else delete cardStatus.dataset.tone;
  CARD.hidden = false;
  positionCard(b);
}

/** The card's quick requests, by what the block IS: prose asks for references, a figure
 *  asks to be remade. Each banks a typed comment row the consuming organ can collect. */
function paintCardAsks(b) {
  if (!cardAsks) return;
  cardAsks.textContent = "";
  const kind = b.kind || "para";
  const ask = (label, request) => {
    const btn = el("button", "ec-ask", label);
    btn.type = "button";
    btn.addEventListener("click", (ev) => {
      ev.preventDefault();
      bankCardComment(b, request);
    });
    cardAsks.appendChild(btn);
  };
  if (kind === "para" || kind === "list") {
    ask("request refs for this passage", "request: find supporting references for this passage");
  }
  if (kind === "figure" || kind === "caption") {
    const fl = figLabelOf(b);
    ask("tag: remake this figure",
        "request: remake this figure" + (fl ? " (" + fl + ")" : ""));
  }
  if (kind === "head") {
    ask("suggest a section after this one",
        "request: a new section after §" + (sectionTitle(b.sectionId) || b.id)
        + " — the note carries the proposal");
  }
  cardAsks.hidden = !cardAsks.childNodes.length;
}

function hideCard() {
  if (CARD) CARD.hidden = true;
  if (E.selAnchor) {
    E.selAnchor = null;
    dropArmedMark();
    paintMarks();
  }
}

/** The docked composer yields when he types in the paper: the paper IS the gesture now.
 *  Lighter than `disarm` — it must not steal the caret he is typing with. */
function yieldComposer() {
  if (!C.armed) return;
  C.armed = null; C.scope = ""; C.scopeSource = ""; C.suggested = ""; C.disposition = ""; C.altitude = "";
  dropArmedMark(); paintMarks();
  compQuote.value = ""; compBody.value = "";
  renderComposer();
  settleRail();
}

/** Whole inline objects can be replaced; partial edits of generated glyphs cannot. */
function rangeTouchesIsland(r, host) {
  const start=offsetIn(host,r.startContainer,r.startOffset),end=offsetIn(host,r.endContainer,r.endOffset);
  for (const n of host.querySelectorAll('[contenteditable="false"]')) {
    if(n.closest('[data-chrome]'))continue;
    const lo=offsetIn(host,n,0),hi=lo+hostText(n).length;
    if(end>lo&&start<hi&&!(start<=lo&&end>=hi))return true;
    if(start===end&&start>lo&&start<hi)return true;
  }
  return false;
}

/** Italic, bold or inline math around the selection — or the word at the caret — WRITTEN
 *  AS TeX into the prose (`\emph{…}`, `\textbf{…}`, `$…$`). The editor is plain text by
 *  design, so the command is the edit: it parks like any typed edit, banks on Ctrl-S, and
 *  renders as italic once the block reloads from its source. Refused across an island. */
function wrapSelection(cmd) {
  const open = cmd === "math" ? "$" : "\\" + cmd + "{";
  const close = cmd === "math" ? "$" : "}";
  const sel = document.getSelection();
  if (!sel || !sel.rangeCount) return { ok: false, why: "click into a paragraph first" };
  const r = sel.getRangeAt(0);
  const startEl = r.startContainer.nodeType === 1 ? r.startContainer : r.startContainer.parentElement;
  const host = startEl && startEl.closest ? startEl.closest('.blk-body[contenteditable="true"]') : null;
  if (!host || !host.contains(r.endContainer)) return { ok: false, why: "click into a paragraph first" };
  const blkEl = closestBlock(host);
  const b = blkEl ? blockById.get(blkEl.dataset.block) : null;
  if (!b) return { ok: false, why: "no block here" };
  if (rangeTouchesIsland(r, host)) {
    showCard(b, "that selection crosses an island (math, a citation or a macro) — atomic here. "
      + "Click it to edit its source.", "refused");
    return { ok: false, why: "island" };
  }
  snapshotEdit(b, host);
  if (r.collapsed && r.startContainer.nodeType === 3) {
    // no selection: take the word under the caret
    const tv = r.startContainer.nodeValue || "";
    let a = r.startOffset, z = r.startOffset;
    while (a > 0 && /[\p{L}\p{N}'’-]/u.test(tv[a - 1])) a -= 1;
    while (z < tv.length && /[\p{L}\p{N}'’-]/u.test(tv[z])) z += 1;
    if (z > a) { r.setStart(r.startContainer, a); r.setEnd(r.startContainer, z); sel.removeAllRanges(); sel.addRange(r); }
  }
  const inner = sourceForRenderedRange(b,offsetIn(host,r.startContainer,r.startOffset),offsetIn(host,r.endContainer,r.endOffset));
  document.execCommand("insertText", false, open + inner + close);
  if (!inner) {
    // an empty wrapper: leave the caret inside it so he types the words next
    const s2 = document.getSelection();
    const r2 = s2 && s2.rangeCount ? s2.getRangeAt(0) : null;
    if (r2 && r2.collapsed && r2.startContainer.nodeType === 3) {
      r2.setStart(r2.startContainer, Math.max(0, r2.startOffset - close.length));
      r2.collapse(true); s2.removeAllRanges(); s2.addRange(r2);
    }
  }
  showCard(b, (cmd === "math" ? "$…$" : "\\" + cmd + "{…}") + " written as TeX — it renders once "
    + "banked · Ctrl-S banks · Esc reverts", "");
  return { ok: true };
}

function editorInsertionPoint(){
  if(F.ta&&F.blockId)return {source:true,blockId:F.blockId,start:F.ta.selectionStart,end:F.ta.selectionEnd};
  const selection=document.getSelection();if(!selection?.rangeCount)return null;
  const range=selection.getRangeAt(0),element=range.startContainer.nodeType===1?range.startContainer:range.startContainer.parentElement;
  const host=element?.closest('.blk-body[contenteditable="true"]');
  if(!host||!host.contains(range.endContainer))return null;
  const block=closestBlock(host);return {blockId:block.dataset.block,start:offsetIn(host,range.startContainer,range.startOffset),end:offsetIn(host,
    range.endContainer,range.endOffset)};
}
function contextualInsertionPoint(node,x,y){
  const block=closestBlock(node),b=blockById.get(block?.dataset.block);if(!b?.bodyEl||!editableBlock(b))return null;
  const object=node.closest?.('.ref,.cite-wrap');
  if(object&&b.bodyEl.contains(object)){const start=offsetIn(b.bodyEl,object,0);return {blockId:b.id,start,end:start+hostText(object).length,
    replace:true,type:object.classList.contains('cite-wrap')?'citation':'reference'};}
  const existing=editorInsertionPoint();if(existing?.blockId===b.id&&existing.start!==existing.end)return existing;
  const position=document.caretPositionFromPoint?.(x,y),range=position?null:document.caretRangeFromPoint?.(x,y),container=position?.offsetNode||
    range?.startContainer,at=position?.offset??range?.startOffset;
  if(container&&b.bodyEl.contains(container)){const offset=offsetIn(b.bodyEl,container,at);return {blockId:b.id,start:offset,end:offset};}
  return existing?.blockId===b.id?existing:null;
}
function caretRange(host,start,end=start){
  const range=document.createRange(),map=readableDOM(host),first=map.point(start),last=map.point(end);
  range.setStart(first.node,first.off);range.setEnd(last.node,last.off);return range;
}

function insertEditorText(value,point=editorInsertionPoint()){
  if(!point)throw Error('Place the caret in the manuscript first.');
  if(point.source){if(F.blockId!==point.blockId||!F.ta)throw Error('Reopen the source where you want to insert this.');F.ta.setRangeText(value,
    point.start,point.end,'end');F.ta.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:value}));F.ta.focus();return;}
  const b=blockById.get(point.blockId),host=b?.bodyEl;if(!host||!editableBlock(b))throw Error('Choose editable manuscript text.');
  host.focus({preventScroll:true});snapshotEdit(b,host);const range=caretRange(host,point.start,point.end);
  if(rangeTouchesIsland(range,host))throw Error('Place the caret beside the equation or reference.');
  const selection=document.getSelection();selection.removeAllRanges();selection.addRange(range);
  document.execCommand('insertText',false,value);onEditInput({target:host});
}
function manuscriptTargets(){
  const targets=[],seen=new Set();
  for(const b of S.blocks)for(const label of blockLabels(b)){if(seen.has(label))continue;seen.add(label);
    targets.push({key:label,type:b.kind==='equation'?'equation':b.kind==='figure'?'figure':'section',title:b.title||sectionTitle(b.sectionId)||label,
      preview:b.math||b.text||(b.bodyEl?norm(hostText(b.bodyEl)):''),number:D.refs[label]||'',blockId:b.id});}
  for(const [key,number]of Object.entries(D.refs))if(!seen.has(key))targets.push({key,number,type:key.startsWith('eq:')?'equation':key.startsWith(
    'fig:')?'figure':'section',title:key,preview:''});
  return targets;
}
let pendingCitationPlacement=null;
function armCitationPlacement(key){
  referenceCommand({type:'citation',key});pendingCitationPlacement?.cancel();
  const bubble=asChrome(el('div','citation-placement-actions')),insert=el('button','primary','Insert citation here'),cancel=el('button',null,
    'Cancel');insert.type=cancel.type='button';bubble.append(insert,cancel);bubble.hidden=true;document.body.append(bubble);let point=null;
  const close=()=>{bubble.remove();docEl.removeEventListener('mouseup',choose);document.removeEventListener('keydown',escape,true);pendingCitationPlacement=null;};
  const choose=event=>{if(bubble.contains(event.target))return;const captured=editorInsertionPoint();if(!captured)return;event.stopPropagation();
    point={...captured,start:captured.end};bubble.hidden=false;bubble.style.left=Math.max(8,Math.min(event.clientX,
    innerWidth-bubble.offsetWidth-8))+'px';bubble.style.top=Math.max(8,event.clientY-48)+'px';};
  const escape=event=>{if(event.key==='Escape'){event.preventDefault();event.stopImmediatePropagation();close();emit('editor-status',{text:'Citation placement cancelled.'});}};
  insert.onmousedown=event=>event.preventDefault();insert.onclick=async()=>{try{if(!point)return;insertEditorText(referenceCommand({type:'citation',
    key}),point);close();if(!point.source)await commitEdit('insert-citation');else emit('editor-status',{
    text:'Citation inserted in the source draft. Ctrl-S saves.'});}catch(error){emit('editor-status',{text:error.message,error:true});}};
  cancel.onclick=()=>{close();emit('editor-status',{text:'Citation placement cancelled.'});};docEl.addEventListener('mouseup',choose);
    document.addEventListener('keydown',escape,true);pendingCitationPlacement={key,cancel:close};emit('editor-status',{
    text:'Click the text where '+key+' belongs, then choose Insert citation here. Esc cancels.'});
}

async function openReferencePicker(type='reference',options={}){
  const captured=options.point||editorInsertionPoint();
  // A highlighted sentence is the context for an insertion. Replacing a reference
  // is explicit; inserting one beside a selection must never erase the prose.
  const point=captured?{...captured,start:options.replace?captured.start:captured.end}:null;if(!point){emit('editor-status',{
    text:'Place the caret where you want the reference.'});return;}
  const dialog=el('dialog','manuscript-insert-dialog'),heading=el('h2',null,type==='citation'?'Insert citation':'Insert reference');
  const search=el('input');search.type='search';search.setAttribute('aria-label',
    type==='citation'?'Find a citation':'Find an equation, figure or section');search.placeholder=type==='citation'?'Author, title or citation key':'Title, equation or label';
  const list=el('div','reference-options'),message=el('p','insert-message'),close=el('button',null,'Cancel');close.type='button';close.onclick=()=>dialog.close();
  dialog.append(heading,search,list,message,close);document.body.append(dialog);dialog.onclose=()=>dialog.remove();dialog.showModal();search.focus();
  let targets=type==='citation'?(D.citation_targets?.length?D.citation_targets.map(row=>({...row,type:'citation'})):Object.entries(D.citations).map(([
    key,value])=>({key,type:'citation',title:value.text||value.title||key,number:value.num||''}))):manuscriptTargets();
  const paint=()=>{list.replaceChildren();const query=search.value.toLowerCase();for(const target of targets.filter(t=>[t.title,t.key,t.preview].join(
    ' ').toLowerCase().includes(query)).slice(0,80)){
    const choice=el('button','reference-choice');choice.type='button';choice.append(el('strong',null,(
      target.number?target.number+' · ':'')+target.title),el('small',null,target.key+(target.preview?' · '+String(target.preview).slice(0,150):'')));
    choice.onclick=()=>{try{const command=referenceCommand(target);dialog.close();insertEditorText((captured.end>captured.start&&
      !options.replace?' ':'')+command,point);if(!point.source)commitEdit('insert-reference');}catch(error){emit('editor-status',{text:error.message,
      error:true});}};list.appendChild(choice);}
    message.textContent=list.childNodes.length?'':type==='citation'?
      'No matching project citations. Attach a source in Research or ask the session to add it.':'No matching labeled target.';};
  search.oninput=paint;paint();
  if(type==='citation')try{const data=await store.fetchJSON('/references/attached',{params:{project:S.corpus}});for(const row of data.associations||[
    ]){if(!row.citekey||targets.some(t=>t.key===row.citekey))continue;targets.push({key:row.citekey,type:'citation',title:row.metadata?.title||
    row.title||row.citekey});}if(dialog.isConnected)paint();}catch(error){if(!targets.length&&dialog.isConnected)message.textContent=error.message;}
}

const manuscriptSearch={query:'',replacement:'',index:-1};
function searchMatches(query){const matches=[];if(!query)return matches;for(const b of S.blocks){if(!b.bodyEl||b.texFace)continue;
  const value=hostText(b.bodyEl),lower=value.toLocaleLowerCase(),needle=query.toLocaleLowerCase();let at=0;while((at=lower.indexOf(needle,at))>=0){
  matches.push({blockId:b.id,start:at,end:at+query.length});at+=Math.max(1,query.length);}}return matches;}
function selectSearchMatch(point){const b=blockById.get(point?.blockId);if(!b?.bodyEl)return; b.el.scrollIntoView({block:'center'});if(editableBlock(
  b))b.bodyEl.focus({preventScroll:true});const selection=document.getSelection();selection.removeAllRanges();selection.addRange(caretRange(b.bodyEl,point.start,point.end));}
function findNext(backward=false){const matches=searchMatches(manuscriptSearch.query);if(!matches.length){emit('editor-status',{text:'No matches.'});
  return;}manuscriptSearch.index=(manuscriptSearch.index+(backward?-1:1)+matches.length)%matches.length;selectSearchMatch(matches[
  manuscriptSearch.index]);emit('editor-status',{text:`Match ${manuscriptSearch.index+1} of ${matches.length}`});}
function openFindDialog(){
  const dialog=el('dialog','manuscript-insert-dialog');dialog.appendChild(el('h2',null,'Find and replace'));
  const query=el('input'),replacement=el('input');query.type='search';query.setAttribute('aria-label','Find in manuscript');
    query.placeholder='Find in manuscript';query.value=manuscriptSearch.query;replacement.setAttribute('aria-label','Replace with');
    replacement.placeholder='Replace with';replacement.value=manuscriptSearch.replacement;
  const count=el('p');
  const next=el('button',null,'Find next');next.dataset.control='editor-frame:find-next';
  const replace=el('button',null,'Replace next');replace.dataset.control='editor-frame:find-replace';
  const cancel=el('button',null,'Close');cancel.dataset.control='editor-frame:find-close';
  const update=()=>{manuscriptSearch.query=query.value;manuscriptSearch.replacement=replacement.value;count.textContent=searchMatches(
    query.value).length+' matches';};query.oninput=()=>{manuscriptSearch.index=-1;update();};replacement.oninput=update;
  next.onclick=()=>{update();dialog.close();findNext();};cancel.onclick=()=>dialog.close();
  replace.onclick=async()=>{update();const matches=searchMatches(query.value);if(!matches.length)return;const index=manuscriptSearch.index>=0&&
    manuscriptSearch.index<matches.length?manuscriptSearch.index:0;dialog.close();try{insertEditorText(replacement.value,matches[index]);
    await commitEdit('replace');manuscriptSearch.index=index-1;}catch(error){emit('editor-status',{text:error.message,error:true});}};
  query.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();next.click();}};dialog.append(query,replacement,count,next,replace,cancel);
    dialog.onclose=()=>dialog.remove();document.body.appendChild(dialog);dialog.showModal();update();query.focus();query.select();
}

export {
  CARD, armCitationPlacement, bankCardComment, cardBlock, cardFromSelection, cardNote, cardWhere,
  cardWhereBtn, caretRange, contextualInsertionPoint, editorInsertionPoint, findNext, hideCard,
  insertEditorText, openFindDialog, openReferencePicker, paintCardState, positionCard, rangeTouchesIsland,
  setEditScope, showCard, wrapSelection, yieldComposer
};
