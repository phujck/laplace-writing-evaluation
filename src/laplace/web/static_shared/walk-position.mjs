// WALK POSITION (S2 F5). Purpose: the reading position and everything measured: block tops and
// heights, the focal line, the spine (derived from D's sections), coverage dwell, the one jump
// motion, the span, the reading dial and zoom, scroll/idle handling and the attention block.
// Owns: S (layout, current section, span, jump, dwell and timers) and attentionBlockId.
// Public contract: measure/scheduleRemeasure, blockAtY/readingY, captureFocus/restoreFocus,
// buildSpine/updateCurrent, jumpToBlock/jumpToIndex, setSpan/spanState, reallocate/toggleSpine,
// setDocSize/fitDocSize/zoomIn/zoomOut/zoomFit, onScroll, noteAttention (the attention writer outside
// a jump) and forgetPaintedSection (re-adoption repaints linkages). Reports changes only through
// emit('section'|'span'|'attention'). Lifetime: timers live in S and are cancelled by the jump and
// idle owners here; no perpetual idle work.
import {
  $, DOC_BASE, DOC_MAX, DOC_MIN, DOC_STEP, GUTTER, IDLE_MS, JUMP_MAX_MS, JUMP_MIN_MS, LAND, LIT_MS,
  MEASURE_EM, PROBE, REDUCED, REMEASURE_MS, SCALE_STEP, clamp, docEl, door, el, emit, paper, root, spineList,
  spineNote, text, zoomLevel
} from './walk-base.mjs';
import {D} from './walk-document.mjs';
import {K, repaintFigures} from './walk-media.mjs';
import {headText} from './walk-pieces.mjs';
import {G, geoComputeFit, geoSetScale} from './walk-geometry.mjs';
import {C} from './walk-composer.mjs';
import {paintDeposits} from './walk-band.mjs';
import {renderLinkages} from './walk-where.mjs';

const S = {
  corpus: "", ctx: null, source: null,   // {pdf, label, named} — the geometry face's artefact
  blocks: [], tops: [], heights: [],     // the block canvas's measured layout
  sections: [], current: -1,
  docSize: DOC_BASE,
  span: null,                            // {anchor, from, to} indices into S.sections
  door: null,                            // {scrollTop, label}
  jump: null,                            // the running scroll animation
  dwellIndex: -1, dwellStamp: 0, idleTimer: 0, litTimer: 0, remeasure: 0,
  ready: false,
  // the instant this walk opened, for the words the ledger door says. It is NOT the
  // band's gate — the gate is provenance (`admit` + the mint token), never a clock read
  // in one process and compared against a string minted in another.
  opened: new Date().toISOString(),
};

function measurePx() {
  return Math.round(MEASURE_EM * S.docSize);
}

// ═════════════════════════════════════════════════════════════════════════════════════════
// 5 · layout measurement and the focal point (G1)
// ═════════════════════════════════════════════════════════════════════════════════════════

/** Cache every block's content-space top and height. #paper is the offset parent (it is
 *  position:relative), so offsetTop is exactly the scrollTop that puts a block at the
 *  pane's top edge. Re-run after every layout change. A no-op while the geometry face is
 *  showing: a hidden pane measures zero, and a zero measure is a lie. */
function measure() {
  if (root.dataset.geo === "1") return;
  S.tops = S.blocks.map((b) => ((b.proposalDisplayEl||b.el)?.offsetTop||0));
  S.heights = S.blocks.map((b) => ((b.proposalDisplayEl||b.el)?.offsetHeight||0));
  for (const sec of S.sections) {
    sec.y = sec.headEl ? sec.headEl.offsetTop : 0;
  }
}

function scheduleRemeasure() {
  if (S.remeasure) clearTimeout(S.remeasure);
  S.remeasure = setTimeout(() => {
    S.remeasure = 0;
    const f = captureFocus();
    measure();
    if(!settleJumpAnchor())restoreFocus(f);
    updateCurrent();
  }, REMEASURE_MS);
}

function blockAtY(y) {
  let lo = 0, hi = S.tops.length - 1, best = 0;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (S.tops[mid] <= y) { best = mid; lo = mid + 1; } else { hi = mid - 1; }
  }
  return best;
}

const readingY = () => paper.scrollTop + paper.clientHeight * PROBE;
const maxScroll = () => Math.max(0, paper.scrollHeight - paper.clientHeight);

/** G1 — capture the point he is looking at, as a BLOCK and where in it.
 *
 *  Inside a block the position is a FRACTION, so it rides a reading-size change with the
 *  text. In the gap between two blocks (section heads carry a margin) it is a PIXEL offset
 *  against the next block's top, because that gap is stated in px and does not scale. A
 *  fraction greater than one — the reading line sitting past a block's bottom — was the
 *  drift: it multiplied a changed height by a number that never meant a position inside it. */
function captureFocus() {
  if (!S.blocks.length) return null;
  const y = readingY();
  const i = blockAtY(y);
  const top = S.tops[i] || 0, h = S.heights[i] || 1;
  if (y <= top + h) return { id: S.blocks[i].id, frac: (y - top) / h, gap: 0 };
  const j = i + 1;
  if (j < S.blocks.length) {
    return { id: S.blocks[j].id, frac: 0, gap: y - (S.tops[j] || 0) };
  }
  return { id: S.blocks[i].id, frac: 1, gap: y - (top + h) };
}

/** G1 — solve the scroll so the captured point sits back at the same viewport position.
 *  Zero pixel shift at the anchor; instant, never animated (this is not his gesture). */
function restoreFocus(f) {
  if (!f || !S.blocks.length) return;
  const i = S.blocks.findIndex((b) => b.id === f.id);
  if (i < 0) return;
  const y = (S.tops[i] || 0) + (f.frac || 0) * (S.heights[i] || 1) + (f.gap || 0);
  paper.scrollTop = clamp(y - paper.clientHeight * PROBE, 0, maxScroll());
}

// ═════════════════════════════════════════════════════════════════════════════════════════
// 6 · THE SPINE — derived from the DOC MODEL's sections
// ═════════════════════════════════════════════════════════════════════════════════════════

function buildSpine() {
  S.sections = D.sections.map((sec) => ({
    id: sec.id, title: sec.title, file: sec.file, depth: clamp(sec.depth, 0, 2),
    blocks: sec.blocks.length, headEl: sec.headEl, y: 0,
    dwell: 0, cover: "unwalked", el: null, tintEl: null, rowEl: null, countEl: null,
  }));
  renderSpine();
  const bits = [];
  bits.push("content-faithful: the words, the math, the figures and the order. Geometry — "
    + "line and page breaks, floats — is deferred to the typeset face behind the geometry "
    + "door.");
  if (K.note) bits.push(K.note);
  if (D.unknown) {
    bits.push(D.unknown + " macro" + (D.unknown === 1 ? " is" : "s are")
      + " marked in place: the payload carried no expansion for them.");
  }
  bits.push("tint = measured dwell, not a checkbox. Click a row to jump; shift-click "
    + "another to span from it.");
  text(spineNote, bits.join(" "));
}

function renderSpine() {
  spineList.textContent = "";
  S.sections.forEach((sec, i) => {
    const wrap = el("div", "sec");
    wrap.dataset.depth = String(sec.depth);
    wrap.dataset.cover = sec.cover;

    const bracket = el("div", "sec-bracket");
    const tint = el("div", "sec-tint");

    const row = el("button", "sec-row");
    row.type = "button";
    row.dataset.index = String(i);
    const title = el("span", "sec-title", sec.title);
    const count = el("span", "sec-count");
    const nblocks = el("span", "sec-blocks", sec.blocks + "b");
    row.appendChild(title);
    row.appendChild(count);
    row.appendChild(nblocks);
    row.addEventListener("click", (ev) => onSpineClick(i, ev));

    wrap.appendChild(bracket);
    wrap.appendChild(tint);
    wrap.appendChild(row);
    sec.el = wrap; sec.tintEl = tint; sec.rowEl = row; sec.countEl = count;
    spineList.appendChild(wrap);
    if(root.classList.contains('writing-embedded')){
      const nested=S.blocks.filter(b=>b.sectionId===sec.id&&b.kind==='head'&&['subsection','subsubsection','paragraph','subparagraph'].includes(b.level));
      if(nested.length){const list=el('div','subsection-list');for(const block of nested){const jump=el('button','subsection-jump',block.title||
        headText(block));jump.type='button';jump.dataset.level=block.level;jump.onclick=()=>jumpToBlock(block.id);list.appendChild(jump);}spineList.appendChild(list);}
    }
  });
  paintCurrent();
  paintSpan();
  paintDeposits();
}

function sectionAtY(y) {
  let best = -1;
  for (let i = 0; i < S.sections.length; i++) {
    if (S.sections[i].y <= y + 1) best = i; else break;
  }
  return best;
}

function sectionTitle(id) {
  const sec = S.sections.find((s) => s.id === id);
  return sec ? sec.title : "";
}

function paintCurrent() {
  S.sections.forEach((sec, i) => {
    if (!sec.el) return;
    if (i === S.current) sec.el.dataset.current = "1"; else delete sec.el.dataset.current;
  });
}

let lkPainted = "";
/** A re-adopted document repaints the current section's linkages on the next position update. */
function forgetPaintedSection() { lkPainted = ""; }
function updateCurrent() {
  if (!S.sections.length) return;
  const next = sectionAtY(readingY());
  if (next === S.current) return;
  accrueDwell();                        // book the time before the boundary moves
  S.current = next;
  S.dwellIndex = next;
  paintCurrent();
  if (S.sections[S.current] && lkPainted !== S.sections[S.current].id) {
    lkPainted = S.sections[S.current].id;
    renderLinkages();
  }
  paintCoverage();                      // the OTHER coarse boundary (the first is idle)
  const sec = S.sections[next];
  if (sec && sec.el) keepRowInView(sec.el);
  emit("section", { id: sec ? sec.id : null, index: next });
}

function keepRowInView(node) {
  const spine = $("spine");
  const top = node.offsetTop, bottom = top + node.offsetHeight;
  if (top < spine.scrollTop) spine.scrollTop = top - 8;
  else if (bottom > spine.scrollTop + spine.clientHeight) {
    spine.scrollTop = bottom - spine.clientHeight + 8;
  }
}

// ── coverage: measured dwell, painted at scroll-idle only ────────────────────────────────

function accrueDwell() {
  const now = performance.now();
  if (S.dwellIndex >= 0 && S.dwellStamp && !document.hidden) {
    const sec = S.sections[S.dwellIndex];
    if (sec) sec.dwell += (now - S.dwellStamp) / 1000;
  }
  S.dwellStamp = now;
}

/** What "walked" costs for one section: a floor of four seconds plus five per pane-height
 *  of its extent. Measured, never self-reported; no checkbox exists. */
function dwellNeeded(i) {
  const a = S.sections[i].y;
  const b = (i + 1 < S.sections.length) ? S.sections[i + 1].y : docEl.scrollHeight;
  const panes = Math.max(0.4, (b - a) / Math.max(1, paper.clientHeight));
  return clamp(4 + 5 * panes, 4, 90);
}

function paintCoverage() {
  for (let i = 0; i < S.sections.length; i++) {
    const sec = S.sections[i];
    const cover = sec.dwell >= dwellNeeded(i) ? "walked"
                : sec.dwell > 0.5 ? "partial" : "unwalked";
    if (cover !== sec.cover) {
      sec.cover = cover;
      if (sec.el) sec.el.dataset.cover = cover;
    }
  }
}

// ═════════════════════════════════════════════════════════════════════════════════════════
// 7 · THE JUMP — the one motion, the echo of his gesture (G3, G4)
// ═════════════════════════════════════════════════════════════════════════════════════════

const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

function cancelJump() {
  if (S.jump) { cancelAnimationFrame(S.jump.raf); S.jump = null; }
}

/** Run the scroll CONTINUOUSLY to `target`. Never a teleport: direction and distance are
 *  the orientation cue. Honours prefers-reduced-motion by landing at once. */
function scrollContinuous(target) {
  cancelJump();
  const destination=()=>clamp(typeof target==='function'?target():target,0,maxScroll());
  const to = destination();
  const from = paper.scrollTop;
  const d = to - from;
  if (Math.abs(d) < 2 || (REDUCED && REDUCED.matches)) { paper.scrollTop = to; return; }
  const ms = clamp(180 + Math.abs(d) * 0.05, JUMP_MIN_MS, JUMP_MAX_MS);
  const t0 = performance.now();
  const step = (now) => {
    const t = clamp((now - t0) / ms, 0, 1);
    paper.scrollTop = from + (destination()-from) * easeInOut(t);
    if (t < 1) S.jump.raf = requestAnimationFrame(step); else S.jump = null;
  };
  S.jump = { raf: requestAnimationFrame(step) };
}

function hereLabel() {
  const i = S.current >= 0 ? S.current : sectionAtY(readingY());
  const sec = S.sections[i];
  return sec ? (sec.id==='front'?'':'§') + sec.title : "where you were";
}

/** G4 — the named way home, minted before every jump. */
function mintDoor() {
  const label = "back to " + hereLabel();
  S.door = { scrollTop: paper.scrollTop, label };
  text(door, label);
  door.hidden = false;
}

function takeDoor() {
  if (!S.door) return false;
  const to = S.door.scrollTop;
  S.door = null;
  door.hidden = true;
  scrollContinuous(to);
  return true;
}

function litNode(node) {
  if (S.litTimer) { clearTimeout(S.litTimer); S.litTimer = 0; }
  for (const b of S.blocks) if (b.el) delete b.el.dataset.lit;
  for (const sec of S.sections) if (sec.headEl) delete sec.headEl.dataset.lit;
  if (!node) return;
  node.dataset.lit = "1";
  S.litTimer = setTimeout(() => { delete node.dataset.lit; S.litTimer = 0; }, LIT_MS);
}

function jumpToIndex(i, { door: wantDoor = true } = {}) {
  const sec = S.sections[i];
  if (!sec) return;
  if (wantDoor) mintDoor();
  litNode(sec.headEl);
  S.jumpAnchor=sec.headEl;scrollContinuous(()=>nodeLandingScroll(sec.headEl));
}

function nodeLandingScroll(node){
  const pane=paper.getBoundingClientRect(),bar=$('bar')?.getBoundingClientRect();
  const occluded=bar?Math.max(0,Math.min(paper.clientHeight,bar.bottom-pane.top)):0;
  const landing=occluded+(paper.clientHeight-occluded)*LAND;
  return paper.scrollTop+node.getBoundingClientRect().top-pane.top-paper.clientTop-landing;
}
function settleJumpAnchor(){
  if(!S.jumpAnchor?.isConnected){if(S.jumpAnchor)cancelJump();S.jumpAnchor=null;return false;}
  if(!S.jump)paper.scrollTop=clamp(nodeLandingScroll(S.jumpAnchor),0,maxScroll());
  return true;
}
function releaseJumpAnchor(){S.jumpAnchor=null;cancelJump();}

function jumpToBlock(id, { door: wantDoor = true } = {}) {
  const i = S.blocks.findIndex((b) => b.id === id);
  if (i < 0) return false;
  if (wantDoor) mintDoor();
  attentionBlockId=id;emit('attention',{block:id});
  litNode(S.blocks[i].el);
  S.jumpAnchor=S.blocks[i].el;scrollContinuous(()=>nodeLandingScroll(S.jumpAnchor));
  return true;
}

// ═════════════════════════════════════════════════════════════════════════════════════════
// 8 · THE SPAN — the spine IS the structural surface
// ═════════════════════════════════════════════════════════════════════════════════════════

function spanRows() {
  if (!S.span) return [];
  const [a, b] = [Math.min(S.span.from, S.span.to), Math.max(S.span.from, S.span.to)];
  return S.sections.slice(a, b + 1);
}

function paintSpan() {
  const rows = spanRows();
  const set = new Set(rows.map((r) => r.id));
  S.sections.forEach((sec) => {
    if (!sec.el) return;
    if (!set.has(sec.id)) { delete sec.el.dataset.span; return; }
    const first = rows[0] === sec, last = rows[rows.length - 1] === sec;
    sec.el.dataset.span = (first && last) ? "only" : first ? "head" : last ? "tail" : "1";
  });
}

function setSpan(next) {
  S.span = next;
  paintSpan();
  const detail = spanState();
  emit("span", detail);
  document.dispatchEvent(new CustomEvent("walk:span", { detail }));
}

function spanState() {
  const rows = spanRows();
  return rows.length
    ? { sections: rows.map((r) => r.id),
        rows: rows.map((r) => ({ id: r.id, title: r.title })) }
    : null;
}

function onSpineClick(i, ev) {
  if (ev.shiftKey && S.span) {
    setSpan({ anchor: S.span.anchor, from: S.span.anchor, to: i });
    return;
  }
  setSpan({ anchor: i, from: i, to: i });
  jumpToIndex(i);
}

// ═════════════════════════════════════════════════════════════════════════════════════════
// 9 · reallocation and the reading dial (G1, G2, G5, G6)
// ═════════════════════════════════════════════════════════════════════════════════════════

const RAIL_STRIP = 52, RAIL_BAND = 320, RAIL_ARMED = 420;
const SPINE_W = 244;      // --spine-w at rest, in css px (walk.html :root)
const PAPER_MIN = 360;    // the reading column's pane never narrows past this

/** Every reallocation pins the focal point and leaves the READING SIZE alone (G2) — the
 *  margins absorb the change, and past the margins the pane pans. */
function reallocate(patch = {}) {
  const f = captureFocus();
  if (patch.spine === "open" || patch.spine === "collapsed") root.dataset.spine = patch.spine;
  if (patch.rail !== undefined) {
    root.style.setProperty("--rail-w",
      typeof patch.rail === "number" ? Math.max(0, patch.rail) + "px" : RAIL_STRIP + "px");
  }
  measure();
  restoreFocus(f);
  // G5 — the spine opens oriented to now, never at the document top.
  if (patch.spine === "open") {
    const sec = S.sections[S.current];
    if (sec && sec.el) keepRowInView(sec.el);
  }
  return { spine: root.dataset.spine,
           rail: getComputedStyle(root).getPropertyValue("--rail-w").trim() };
}

function toggleSpine() {
  const spine = root.dataset.spine === "collapsed" ? "open" : "collapsed";
  // the width is solved for the PROSPECTIVE spine state, so the DOM changes exactly once
  // inside reallocate and the focal-point solve (G1) sees one layout change.
  return reallocate({ spine, rail: railPx(C.rail, spine) });
}

/** The rail's width for a mode, CLAMPED so the reading pane never falls below PAPER_MIN.
 *  This is the scroll law's arithmetic: spine + rail + PAPER_MIN ≤ the window, at every
 *  width, so no reallocation can push the grid wider than the viewport. */
function railPx(mode, spineState) {
  const want = mode === "armed" ? RAIL_ARMED : mode === "band" ? RAIL_BAND : RAIL_STRIP;
  const spine = (spineState || root.dataset.spine) === "collapsed" ? 0 : SPINE_W;
  const room = Math.max(RAIL_STRIP, (window.innerWidth || 0) - spine - PAPER_MIN);
  return Math.min(want, room);
}

/** G2's one gate: the reading size moves through HERE and nowhere else. Reallocation and
 *  window resize never call it — the margins absorb those, and past the margins the pane
 *  pans, so the text he is reading never reflows under him. */
function setDocSize(next) {
  const target = clamp(next, DOC_MIN, DOC_MAX);
  if (Math.abs(target - S.docSize) < 0.05) { paintZoom(); return; }
  const f = captureFocus();
  S.docSize = target;
  if(root.classList.contains("writing-enabled")) localStorage.setItem("laplace:walk:font-size", String(target));
  docEl.style.setProperty("--doc-size", target.toFixed(2) + "px");
  measure();
  restoreFocus(f);
  repaintFigures();
  scheduleRemeasure();
  paintZoom();
}

function fitDocSize() {
  const avail = (paper.clientWidth || 0) - 2 * GUTTER;
  return clamp(avail / MEASURE_EM, DOC_MIN, DOC_MAX);
}

function paintZoom() {
  text(zoomLevel, G.open ? Math.round(G.scale * 100) + "%"
                         : Math.round((S.docSize / DOC_BASE) * 100) + "%");
}

const zoomIn = () => (G.open ? geoSetScale(G.scale * SCALE_STEP)
                             : setDocSize(S.docSize * DOC_STEP));
const zoomOut = () => (G.open ? geoSetScale(G.scale / SCALE_STEP)
                              : setDocSize(S.docSize / DOC_STEP));
const zoomFit = () => (G.open ? geoSetScale(geoComputeFit()) : setDocSize(fitDocSize()));

// ═════════════════════════════════════════════════════════════════════════════════════════
// 18 · EVENTS
// ═════════════════════════════════════════════════════════════════════════════════════════

let attentionBlockId=null;
/** The one writer of the attention block outside a jump: proposals and object gestures name it. */
function noteAttention(id) { attentionBlockId = id; }
let scrollRaf = 0;
function onScroll() {
  if (!scrollRaf) {
    scrollRaf = requestAnimationFrame(() => { scrollRaf = 0; updateCurrent(); });
  }
  if (S.idleTimer) clearTimeout(S.idleTimer);
  S.idleTimer = setTimeout(onIdle, IDLE_MS);
}

/** The coarse boundary: the tints (and nothing else) update here. */
function onIdle() {
  S.idleTimer = 0;
  accrueDwell();
  paintCoverage();
}

export {
  S, accrueDwell, attentionBlockId, blockAtY, buildSpine, captureFocus, fitDocSize, forgetPaintedSection,
  jumpToBlock, jumpToIndex, keepRowInView, litNode, measure, measurePx, mintDoor, noteAttention, onScroll,
  paintZoom, railPx, readingY, reallocate, releaseJumpAnchor, restoreFocus, scheduleRemeasure, sectionAtY,
  sectionTitle, setDocSize, setSpan, settleJumpAnchor, spanState, takeDoor, toggleSpine, updateCurrent,
  zoomFit, zoomIn, zoomOut
};
