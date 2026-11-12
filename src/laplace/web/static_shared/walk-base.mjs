// WALK BASE. Purpose: the walk's shared ground that every owner reads and none owns: the dials
// (reading line, zoom, timing and vendored-library paths), the iframe's DOM handles, the small text
// and element helpers, and the one event sink (emit, listeners, emitted) behind api.on/off.
// Owns: listeners and the emission ledger; nothing else is mutable here. Public contract: the named
// constants, $ and the element handles, clamp/text/norm/el, emit/listeners/emitted, docFail.
// Lifetime: evaluated first; the handles name walk.html's static elements and never change.

// ── constants ────────────────────────────────────────────────────────────────────────────
const PDFJS_SRC = "/shared/pdfjs/pdf.min.mjs";
const WORKER_SRC = "/shared/pdfjs/pdf.worker.min.mjs";
const KATEX_JS = "/shared/katex/katex.min.js";
const KATEX_CSS = "/shared/katex/katex.min.css";

const PROBE = 0.33;          // the reading line: a third down the pane. The focal point.
const LAND = 0.28;           // G3: a jump lands its target in the upper third.
const GUTTER = 26;           // the column's resting margin, each side, in css px
const MEASURE_EM = 33;       // the column's width, in em of the reading size
const DOC_BASE = 16.5, DOC_MIN = 11, DOC_MAX = 30, DOC_STEP = 1.09;
const SCALE_MIN = 0.4, SCALE_MAX = 2.4, SCALE_STEP = 1.12;   // the geometry face's dial
const RENDER_MARGIN = 1.2;   // geometry face: render pages within 1.2 pane-heights
const PURGE_MARGIN = 3.5;    // geometry face: release canvases beyond 3.5 pane-heights
const IDLE_MS = 260;         // scroll-idle: the coarse boundary the tints update at
const DWELL_TICK_MS = 2000;  // while he sits still, dwell still accrues
const LIT_MS = 1100;         // G3: the destination flash
const JUMP_MIN_MS = 240, JUMP_MAX_MS = 400;
const CONTEXT_CHARS = 200;   // the anchor snapshot's context, each side
const REMEASURE_MS = 60;     // figures land asynchronously; the layout re-solves once

const REDUCED = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)");

const listeners = { span: new Set(), section: new Set(), ready: new Set(), bank: new Set() };

// ── dom ──────────────────────────────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);
const root = $("walk"), paper = $("paper"), docEl = $("doc"), docNote = $("doc-note");
const badge = $("badge"), door = $("door"), keymap = $("keymap");
const backDoor = $("back-door");
const spineList = $("spine-list"), spineNote = $("spine-note"), zoomLevel = $("zoom-level");
const geoDoor = $("geo-door"), geometry = $("geometry"), geoScroll = $("geo-scroll");
const geoPages = $("geo-pages"), geoNote = $("geo-note"), geoLabel = $("geo-label");
const geoBack = $("geo-back");

// ── small helpers ────────────────────────────────────────────────────────────────────────
const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);
const text = (node, s) => { node.textContent = s; };
// the tie survives normalisation. `~` renders as U+00A0 and U+00A0 is the one whitespace
// character this canvas carries meaning in: it is the only trace of the source's tie, and
// the locator's inverse map reads it back as `~`. JS `\s` matches it, so a plain
// `replace(/\s+/g," ")` erased every tie before the locator ever saw one — measured: 19/19
// prose runs carrying `Eq.~(\ref{…})` or `word~\cite{…}` failed to splice. This class
// spells "whitespace EXCEPT the tie", and the trim is the same class, so a tie at either
// edge of his selection survives too.
const WS_NOT_TIE = /[^\S\u00a0]+/g;
const norm = (s) => String(s == null ? "" : s)
  .replace(WS_NOT_TIE, " ").replace(/^ +| +$/g, "");
const el = (tag, cls, txt) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (txt !== undefined) n.textContent = txt;
  return n;
};

const emitted = {};   // emissions by event name (bridge contract D): reachability evidence
function emit(name, detail) {
  emitted[name] = (emitted[name] || 0) + 1;
  for (const fn of [...(listeners[name] || [])]) {
    try { fn(detail); } catch (_e) { /* one bad listener never breaks the walk */ }
  }
}

/** Plain words for a failure, where he is looking. The register law: the mechanics once. */
function docFail(message) {
  docNote.hidden = false;
  text(docNote, message);
  docEl.textContent = "";
}

export {
  $, CONTEXT_CHARS, DOC_BASE, DOC_MAX, DOC_MIN, DOC_STEP, DWELL_TICK_MS, GUTTER, IDLE_MS, JUMP_MAX_MS,
  JUMP_MIN_MS, KATEX_CSS, KATEX_JS, LAND, LIT_MS, MEASURE_EM, PDFJS_SRC, PROBE, PURGE_MARGIN, REDUCED,
  REMEASURE_MS, RENDER_MARGIN, SCALE_MAX, SCALE_MIN, SCALE_STEP, WORKER_SRC, backDoor, badge, clamp, docEl,
  docFail, docNote, door, el, emit, emitted, geoBack, geoDoor, geoLabel, geoNote, geoPages, geoScroll, keymap,
  listeners, norm, paper, root, spineList, spineNote, text, zoomLevel
};
