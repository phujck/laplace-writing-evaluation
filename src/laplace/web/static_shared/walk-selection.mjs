// WALK SELECTION (S2 F5 helper shared with editing). Purpose: the source-to-DOM algorithms: a
// block's readable DOM, rendered offsets and ranges, the anchor a gesture carries, the TeX register
// map and the piecewise-exact splice (spliceOf is the one splice authority). Owns: no state.
// Public contract: closestBlock, readableDOM/hostText/offsetIn/rangeInBlock/nodeAt, srcOf/srcLabel,
// anchorFromBlock/anchorFromRange/anchorForWholeBlock/anchorFromPristine, liveRange/liveRangeFrom,
// toSourceRegister, pieceSpanOf/pieceEdge/pieceTypeAt, spliceOf/spliceState,
// sourceForRenderedRange, blockAtSpan.
import {commentSourceSelection, paragraphSourceIdentity} from "/shared/manuscript-editing.mjs";
import {CONTEXT_CHARS, docEl, norm} from './walk-base.mjs';
import {blockById} from './walk-document.mjs';
import {S, sectionTitle} from './walk-position.mjs';
import {caretRange} from './walk-card.mjs';

// ═════════════════════════════════════════════════════════════════════════════════════════
// 12 · THE ANCHOR — a block's provenance, riding every gesture made inside it
// ═════════════════════════════════════════════════════════════════════════════════════════

function closestBlock(node) {
  let n = node && node.nodeType === 1 ? node : (node && node.parentElement);
  while (n && !(n.classList && n.classList.contains("blk"))) n = n.parentElement;
  return n;
}

/** The block's rendered text, read the SAME way for capture and for re-location, so an
 *  offset taken now still names the same characters after a re-render. */
/** ONE READER of a block's text, for capture, for re-location, and for the marks — and it
 *  skips the canvas's OWN CHROME. The badge above a raw block ("raw source — the parser
 *  could not type this block") and a figure's "names no served image route" note are the
 *  surface talking, not the paper: they were being tree-walked into his quote, so a deposit
 *  on a raw block banked the surface's own sentence as if he had selected it. Anything the
 *  canvas mints about a block carries `data-chrome`, and no reader here ever sees it. */
const isChrome = (t) => {
  const p = t && t.parentElement;
  return !!(p && p.closest("[data-chrome]"));
};

/** The text length of a subtree as this surface reads it — chrome excluded, so an offset
 *  counted over children agrees with one counted over `textWalker`. */
function readableDOM(host) {
  let text = '';
  const segments = [], boundaries = new WeakMap(), starts = new WeakMap();
  const atoms = '.mathq,.cite-wrap,.ref,.structural-piece,.katex';
  const append = (value, before, after, node = null) => {
    const start = text.length;text += value;
    if (value) segments.push({node,start,end:text.length,before,after});
  };
  const visit = (node, atomic = false) => {
    const start = text.length;starts.set(node,start);
    if (node.nodeType === 3) {
      if (isChrome(node)) {starts.delete(node);boundaries.set(node,[start]);return;}
      append(node.nodeValue || '',{node,off:0},{node,off:(node.nodeValue || '').length},node);
      return;
    }
    if (node.nodeType !== 1 || node.matches('[data-chrome]')) return;
    atomic ||= !!node.matches(atoms);
    const children = Array.from(node.childNodes);
    const readable=child=>(child.nodeType===1||child.nodeType===3)&&!(child.nodeType===1&&child.matches('[data-chrome]'));
    const visible=children.filter(readable);
    const offsets = [text.length];boundaries.set(node,offsets);
    let prior = null,visibleIndex=0;
    for (let index=0;index<children.length;index++) {
      const child=children[index];
      const block=!atomic&&child.nodeType===1&&!child.matches(atoms)&&['DIV','P'].includes(child.tagName);
      if (readable(child)) {
        const gap=block&&prior ? (child.tagName==='P'?2:1) : prior?.block&&!block ? (prior.paragraph?2:1) : 0;
        if(gap)append('\n'.repeat(gap),{node,off:index},{node:child,off:0});
        if(child.nodeType===1&&child.tagName==='BR') {
          // A sole BR is the browser's empty editing line, not authored text.
          const next=visible[visibleIndex+1];
          const nextLine=next?.nodeType===1&&['DIV','P'].includes(next.tagName)&&!next.matches(atoms);
          if(!atomic&&!nextLine&&visible.length>1)
            append('\n',{node,off:index},{node,off:index+1});
          starts.set(child,text.length);boundaries.set(child,[text.length]);
        } else visit(child,atomic);
        prior={block,paragraph:child.tagName==='P'};
        visibleIndex++;
      }
      offsets.push(text.length);
    }
  };
  visit(host,host.nodeType===1&&!!host.closest(atoms));
  return {text,segments,
    offset(node,off) {
      if(node?.nodeType===3&&starts.has(node))return starts.get(node)+Math.max(0,Math.min(Number(off)||0,(node.nodeValue||'').length));
      const values=boundaries.get(node);return values ? values[Math.max(0,Math.min(Number(off)||0,values.length-1))] : text.length;
    },
    point(offset) {
      const at=Math.max(0,Math.min(Number(offset)||0,text.length));
      for(const span of segments)if(at<=span.end)return span.node ? {node:span.node,off:Math.max(0,at-span.start)} : at<=span.start?span.before:span.after;
      return {node:host,off:host.childNodes.length};
    }};
}

function nodeTextLen(node) {return node ? readableDOM(node).text.length : 0;}
function hostText(host) {return readableDOM(host).text;}

/** Native paste uses DIV/BR editing lines. Text, selection offsets and restored
 * caret ranges share this one map, while inline source atoms stay indivisible. */
function offsetIn(host,node,off) {return readableDOM(host).offset(node,off);}

function rangeInBlock(b,start,end) {
  const host=b.bodyEl||b.el;
  return host&&end>start ? caretRange(host,start,end) : null;
}

function srcOf(b) {
  const s = (b && b.src) || {};
  return { file: s.file || "", lineStart: Number(s.line_start || 0),
           lineEnd: Number(s.line_end || s.line_start || 0) };
}

function srcLabel(b) {
  const s = srcOf(b);
  if (!s.file) return "no resolved source span";
  return s.file + (s.lineStart ? ":" + s.lineStart
    + (s.lineEnd > s.lineStart ? "–" + s.lineEnd : "") : "");
}

/** The `fig:` label a block IS, when it is one — the door's figure tier keys on this, and
 *  the re-authoring session runs off exactly those figure-standard rows. A block that is
 *  not a figure (or a figure carrying no `fig:` label) names none, and no label is
 *  invented for it. */
function figLabelOf(b) {
  const kind = String((b && b.kind) || "");
  if (kind !== "figure" && kind !== "caption") return "";
  const all = [].concat(b.label || [], Array.isArray(b.labels) ? b.labels : []);
  return all.find((l) => typeof l === "string" && l.startsWith("fig:")) || "";
}

function anchorFromBlock(b, start, end, quote) {
  const s = srcOf(b);
  const host = b.bodyEl || b.el;
  const full = host ? hostText(host) : "";
  return {
    grade: "selection", blockId: b.id, kind: b.kind || "para",
    sectionId: b.sectionId, sectionTitle: sectionTitle(b.sectionId),
    // the provenance the dual-faithful canvas exists to carry. `spec_id` is the
    // paragraph id the fragment's own `% <SEC>-pN` marker names; the labels are the
    // block's own. Both were parsed by the door, dropped by `normalizeDoc`, and so never
    // reached the ledger — every walk comment banked at coarse SECTION grade.
    ...paragraphSourceIdentity(b), label: b.label || "",
    figLabel: figLabelOf(b),
    file: s.file, lineStart: s.lineStart, lineEnd: s.lineEnd,
    // the block's face IS source (a raw block, or math the renderer refused): its text is
    // never offered to the right rail as prose.
    texFace: !!b.texFace,
    quote: quote, start, end,
    before: norm(full.slice(Math.max(0, start - CONTEXT_CHARS), start)),
    after: norm(full.slice(end, end + CONTEXT_CHARS)),
    tex: b.tex || "",
  };
}

function anchorFromRange(range) {
  if (!docEl.contains(range.commonAncestorContainer)) return null;
  const blkEl = closestBlock(range.commonAncestorContainer);
  if (!blkEl) return null;
  const b = blockById.get(blkEl.dataset.block);
  if (!b) return null;
  const host = b.bodyEl || blkEl;
  const quote = norm(range.toString());
  if (!quote) return null;
  const start = offsetIn(host, range.startContainer, range.startOffset);
  const end = offsetIn(host, range.endContainer, range.endOffset);
  return anchorFromBlock(b, Math.min(start, end), Math.max(start, end), quote);
}

function anchorForWholeBlock(b) {
  const host = b.bodyEl || b.el;
  const full = host ? hostText(host) : "";
  return anchorFromBlock(b, 0, full.length, norm(full));
}

/** The live selection, ONLY when it lies inside the document canvas. One reader, so the
 *  composer and the source flip can never disagree about what is selected. */
function liveRange() {
  const sel = window.getSelection && window.getSelection();
  if (!sel || sel.isCollapsed || !sel.rangeCount) return null;
  const range = sel.getRangeAt(0);
  if (!docEl.contains(range.commonAncestorContainer)) return null;
  return range;
}

/** THE LOCATOR — the inverse of ONE known transform, never a fuzzy match.
 *
 *  A block's rendered prose is `walk._text_norm` of its source: `~` → nbsp, `---`/`--` →
 *  the dashes, ``` `` ```/`''` → the quotes, and every run of source whitespace (the
 *  fragment's own line wrapping) collapsed to the single space TeX itself sets. That
 *  transform is deterministic and total, so locating his passage back in the source is
 *  its inverse: one regex, each rendered character standing for the source that produced
 *  it. It is taken ONLY when it matches exactly once — zero matches or two are not a
 *  confidence score to threshold, they are "this door does not know where to write", and
 *  the deposit goes down the pending path with the reason said in words. */
// written as escapes, not glyphs: this table is the one place the surface depends on
// byte-exact non-ascii, and an editor or a transport that re-encoded it would silently
// turn every splice into a pending rewrite.
const SOURCE_OF = { " ": "~", "—": "---", "–": "--",
                    "“": "``", "”": "''" };
// TeX'S ESCAPED CHARACTERS. The rendered face of `\%` is `%`; of `\&`, `&`. The locator
// must match EITHER form, and the write-back must produce the ESCAPED one — a bare `%`
// spliced into a LaTeX line comments out the rest of it. Measured on this corpus: five
// prose runs carry `\%` (`20\%`, `81.4\%`, `6\%`), and each one was un-invertible without
// this, which is exactly the piece the piecewise locator has to place characters inside.
const TEX_ESCAPED = "%&_$#{}";
const RE_ESC = /[.*+?^${}()|[\]\\]/g;

function locatorRe(quote) {
  let out = "";
  let space = false;
  for (const ch of String(quote || "")) {
    // SOURCE_OF FIRST. U+00A0 is a whitespace character to `\s`, so testing whitespace
    // first swallowed every tie into the run-of-whitespace branch and the `~` it stands
    // for was never written into the pattern — the one mapping that carries meaning was
    // dead code. The table is consulted before the whitespace test, so a rendered tie
    // matches the `~` that produced it and nothing else.
    const src = SOURCE_OF[ch];
    if (src === undefined) {
      if (/\s/.test(ch)) { if (!space) { out += "[ \\t\\r\\n]+"; space = true; } continue; }
    }
    space = false;
    if (src === undefined && TEX_ESCAPED.indexOf(ch) >= 0) {
      out += "\\\\?" + ch.replace(RE_ESC, "\\$&");   // the escaped form or the bare one
      continue;
    }
    out += (src || ch).replace(RE_ESC, "\\$&");
  }
  return out ? new RegExp(out, "g") : null;
}

/** the map run the other way — his replacement, re-encoded into the source's register.
 *
 *  `locatorRe` uses SOURCE_OF to FIND the passage; without this the surface used it only
 *  in that direction, so a splice wrote the RENDERED register straight back into an ASCII
 *  LaTeX file: an em dash he typed (or one carried through from the prefilled quote, which
 *  is the rendered text) landed as a literal U+2014 where the file's own convention is
 *  `---`. Measured on this corpus: every fragment is 100% ASCII and `sec_r2_resolving.tex`
 *  alone carries 11 `---`. The composer states to his face that "only those characters
 *  change — the rest of the block's source is written back untouched"; that sentence is
 *  only true with this inverse applied. */
function toSourceRegister(s) {
  // Typed inline TeX rides through VERBATIM (his ruling 2026-09-29: "I want the editor. I
  // just want it to work" — he could not italicise, because `\emph{word}` typed into the
  // prose came back as `\emph\{word\}`). A well-formed inline command with balanced braces
  // (one level of nesting), an already-escaped special (`\%`), or a `$…$` run is source
  // he wrote on purpose; everything else is prose and goes back through the register map.
  const src = String(s == null ? "" : s);
  let out = "";
  let i = 0;
  while (i < src.length) {
    INLINE_TEX.lastIndex = i;
    const m = INLINE_TEX.exec(src);
    if (m && m.index === i) { out += m[0]; i += m[0].length; continue; }
    const ch = src[i];
    i += 1;
    if (ch === "\u00a0") {
      // A no-break space is TYPED by the browser, not by him: it stands in for a space that
      // would otherwise collapse (beside another space, or at the end of a text node). Only
      // a no-break space fenced by non-spaces on both sides can be a rendered `~` riding
      // through from the source; the rest go back as the plain space he pressed (his
      // appendix edit 2026-09-29 landed as `construction ~of`).
      const prev = src[i - 2], next = src[i];
      const fenced = prev !== undefined && next !== undefined && !/\s/.test(prev) && !/\s/.test(next);
      out += fenced ? "~" : " ";
      continue;
    }
    if (SOURCE_OF[ch] !== undefined) { out += SOURCE_OF[ch]; continue; }
    // and the TeX specials go back ESCAPED. A bare `%` written into a LaTeX line comments
    // out the rest of that line, so an unescaped write-back of a passage reading `20%`
    // would silently delete the remainder of the sentence from the built paper.
    out += (TEX_ESCAPED.indexOf(ch) >= 0 ? "\\" + ch : ch);
  }
  return out;
}
// `\cmd*[opt]{…}{…}` with one level of nested braces · `\%`-style escaped specials · `$…$`.
const INLINE_TEX = /\\[A-Za-z]+\*?(?:\[[^\]\n]*\])?(?:\{(?:[^{}\n]|\{[^{}\n]*\})*\})*|\\[%&_$#{}]|\$(?:[^$\n\\]|\\.)+\$/y;

// ── the piecewise-exact source map (GAP-20260810-piece-source-offsets) ──────────────────
//
// The narrowing this closes: the locator above inverts ONE transform over a WHOLE block,
// so it can only place a passage that is a single unbroken run of prose in the source. A
// selection touching inline math, a citation or a macro has no such run — the rendered
// `[12]` of a `\cite{…}` and the glyphs KaTeX draws are nowhere in the fragment — so every
// such rewrite fell to the pending path, and that is his DOMINANT gesture on a physics
// paper where nearly every sentence carries one.
//
// The door now emits `{o_start, o_end}` on every piece, with the invariant
// `tex[o_start:o_end]` IS that piece's source (fenced server-side). The renderer records
// each piece's RENDERED span as it draws it. The two together make the rendered-char →
// source-char map piecewise-exact: inside a prose piece the one transform is inverted as
// before; at a piece BOUNDARY the offset is read straight off the map, whatever kind of
// piece sits on the other side.
//
// What it still refuses, and says: a boundary landing STRICTLY INSIDE a math, cite or
// macro piece (rendered math is not addressable as prose — typing over `ω` cannot be
// written back into `\omega` without guessing), a span holding no prose piece at all, and
// a span crossing pieces with UN-RENDERED source between them (a `\label` between two
// runs: splicing over it would delete markup he never saw).

/** How many SOURCE characters, starting at `at`, produced `rendered`. -1 = the transform
 *  does not invert here (a comment or a silent macro inside the run), and the caller must
 *  fall back rather than guess. */
function stickySpan(tex, at, rendered) {
  if (!rendered) return 0;
  const pat = locatorRe(rendered);
  if (!pat) return -1;
  let m = null;
  try {
    const re = new RegExp(pat.source, "y");
    re.lastIndex = at;
    m = re.exec(tex);
  } catch (_e) { return -1; }
  return m ? m[0].length : -1;
}

/** One boundary → its source offset. A number when it maps; `{refused}` when the boundary
 *  is inside a piece that is not prose; null when the inverse does not hold. */
function pieceEdge(p, tex, at, tail) {
  if (at === (tail ? p.rEnd : p.rStart)) return tail ? p.oEnd : p.oStart;
  if (p.t !== "text") return { refused: p.t === "math" ? "math" : "piece" };
  const n = stickySpan(tex, p.oStart, String(p.rText || "").slice(0, at - p.rStart));
  return n < 0 ? null : p.oStart + n;
}

/** the map inverted. `{at:[srcStart, srcEnd]}` when the rendered span [start,end) has an
 *  exact source span; `{refused:"math"|"piece"}` when it is not addressable as prose and
 *  the reason is to be said; null when this locator has no answer and the whole-block
 *  locator should try. Pure — the fences run this function itself. */
function pieceSpanOf(map, tex, start, end, acrossGaps = false) {
  if (!Array.isArray(map) || !map.length || !tex || !(end > start)) return null;
  let si = -1, ei = -1;
  for (let i = 0; i < map.length; i++) {
    const p = map[i];
    if (si < 0 && start >= p.rStart && start < p.rEnd) si = i;
    if (end > p.rStart && end <= p.rEnd) ei = i;
  }
  if (si < 0 || ei < 0 || ei < si) return null;         // the map does not cover it
  let prose = false, math = false;
  for (let i = si; i <= ei; i++) {
    if (map[i].t === "text") prose = true;
    else if (map[i].t === "math") math = true;
  }
  // A complete inline object can be replaced or deleted like any selected text.
  // pieceEdge still refuses edits into the middle of its generated display.
  // Un-rendered source between two pieces (the `\emph{` and `}` around an emphasised word: the map holds
  // the word, not its wrapper) is no answer for a split, but a typed edit that spans it is spliced
  // anyway (`acrossGaps`, spliceOf): the caller rebuilds the region piece by piece (sourceAcrossPieces).
  let gapped = false;
  for (let i = si; i < ei; i++) {
    if (map[i + 1].oStart !== map[i].oEnd) { if (!acrossGaps) return null; gapped = true; }
  }
  const lo = pieceEdge(map[si], tex, start, false);
  if (lo && typeof lo === "object") return { at: null, refused: lo.refused };
  const hi = pieceEdge(map[ei], tex, end, true);
  if (hi && typeof hi === "object") return { at: null, refused: hi.refused };
  if (typeof lo !== "number" || typeof hi !== "number" || !(hi > lo)) return null;
  return { at: [lo, hi], refused: "", ...(gapped ? { inner: map.slice(si + 1, ei), edges: [map[si], map[ei]] } : {}) };
}

/** The source for a typed region whose span crosses un-rendered source between pieces (an inline wrapper
 *  such as `\emph{...}`): every inner piece whose rendered text still stands in the typed text, in order,
 *  keeps its exact source and the un-rendered source on either side of it; the text between kept pieces is
 *  the author's, in source register. An inner piece he typed over is gone, with its wrapper. So his edit
 *  around an emphasised word keeps the emphasis, and a citation or reference inside the region survives. */
function sourceAcrossPieces(tex, pl, after) {
  const [si, ei] = pl.edges;
  const gap = (a, b) => tex.slice(a.oEnd, b.oStart);     // un-rendered source between two adjacent pieces
  let out = "", cursor = 0, prev = si, prevKept = true;
  for (const piece of pl.inner) {
    const face = String(piece.rText || "");
    const idx = face ? after.indexOf(face, cursor) : -1;
    if (idx < 0) { prev = piece; prevKept = false; continue; }     // typed over: the piece and its wrapper go
    out += toSourceRegister(after.slice(cursor, idx)) + (prevKept ? gap(prev, piece) : "") + tex.slice(piece.oStart, piece.oEnd);
    cursor = idx + face.length; prev = piece; prevKept = true;
  }
  return out + (prevKept && prev !== si ? gap(prev, ei) : "") + toSourceRegister(after.slice(cursor));
}

/** The block's source as it now stands — the model's, not the anchor's snapshot: a splice
 *  earlier in this walk moved the lines under it, and a stale slice is a wrong write. */
function texOf(a) {
  // an anchor that names the source its draft was typed against (`basis`, commitEdit's stale park) is read
  // against that source, not the block's newer one: the owner relocates the paragraph from it (ruling 1)
  if (a && typeof a.basis === "string" && a.basis) return a.basis;
  const b = a && a.blockId ? blockById.get(a.blockId) : null;
  return (b && b.tex) || (a && a.tex) || "";
}

/** The piecewise-exact verdict for THIS anchor, or null when the block carries no map
 *  (an older payload with no piece offsets, an equation block, a raw block). */
function pieceLocate(a, acrossGaps = false) {
  const b = a && a.blockId ? blockById.get(a.blockId) : null;
  if (!b || !b.pieceMap) return null;
  return pieceSpanOf(b.pieceMap, texOf(a), Number(a.start), Number(a.end), acrossGaps);
}

/** Where his passage sits in that source: `{before, after, at}` for exactly one match,
 *  null otherwise. `before` is the WHOLE line span — that is the byte guard the door
 *  compares against `raw.split("\n")[line_start-1 … line_end]`, so the two sides agree by
 *  identity. Everything outside his passage rides through untouched, so the citations,
 *  macros and math in the rest of the block survive his edit exactly. */
function spliceOf(a, after) {
  const tex = texOf(a);
  const quote = a ? a.quote : "";
  if (!tex) return null;
  // the piece map first. It is exact where it answers, and it answers on selections the
  // whole-block locator cannot touch at all — anything adjacent to or spanning across
  // inline math, a citation or a cross-ref.
  // the block's piece map describes its CURRENT source; a draft spliced into its own older basis has no map
  const pl = a && a.basis ? null : pieceLocate(a, true);
  if (pl && pl.at) {
    return { before: tex,
             after: tex.slice(0, pl.at[0]) + (pl.inner ? sourceAcrossPieces(tex, pl, after) : toSourceRegister(after)) + tex.slice(pl.at[1]),
             at: pl.at, via: pl.inner ? "pieces-across-gaps" : "pieces" };
  }
  if (pl && pl.refused) return null;      // not addressable as prose: say so, bank pending
  if (!quote) return null;
  const re = locatorRe(quote);
  if (!re) return null;
  let m, hit = null, n = 0;
  while ((m = re.exec(tex))) {
    if (!m[0].length) { re.lastIndex += 1; continue; }
    n += 1;
    if (n > 1) return null;
    hit = [m.index, m.index + m[0].length];
  }
  if (n !== 1) return null;
  return { before: tex,
           after: tex.slice(0, hit[0]) + toSourceRegister(after) + tex.slice(hit[1]),
           at: hit, via: "quote" };
}

// Preserve unchanged rendered inline objects when several edits surround them.
// Their DOM hosts and source spans are known; no Unicode-to-TeX inference is made.
function sourceForRenderedRange(b,start,end){
  const host=b.bodyEl,text=hostText(host),kept=[];
  for(const piece of b.pieceMap||[]){
    const nodes=(piece.nodes||[]).filter(n=>n.isConnected&&host.contains(n));
    if(!nodes.length||!nodes.some(n=>n.nodeType===1&&n.matches('.mathq,.cite-wrap,.ref,.structural-piece')))continue;
    const lo=offsetIn(host,nodes[0],0),hi=lo+nodes.map(n=>n.nodeType===3?n.nodeValue:hostText(n)).join('').length;
    if(lo>=start&&hi<=end&&hi>lo)kept.push({lo,hi,tex:b.tex.slice(piece.oStart,piece.oEnd)});
  }
  let out='',cursor=start;
  for(const piece of kept.sort((a,b)=>a.lo-b.lo)){if(piece.lo<cursor)continue;out+=toSourceRegister(text.slice(cursor,piece.lo))+piece.tex;cursor=piece.hi;}
  return out+toSourceRegister(text.slice(cursor,end));
}

/** Why the splice is or is not deterministic, for the line he reads BEFORE Enter.
 *  "once" · "absent" (the passage does not sit in that source as one run) · "twice" (the
 *  same words appear more than once in this block) · "in-math" / "in-piece" (the piece map
 *  placed the selection inside rendered math, or inside a citation or macro, which is not
 *  addressable as prose). */
function spliceState(a) {
  const pl = pieceLocate(a);
  if (pl && pl.at) return "once";
  if (pl && pl.refused === "math") return "in-math";
  if (pl && pl.refused === "piece") return "in-piece";
  const tex = texOf(a);
  if (!a || !a.quote || !tex) return "absent";
  const re = locatorRe(a.quote);
  if (!re) return "absent";
  let m, n = 0;
  while ((m = re.exec(tex))) {
    if (!m[0].length) { re.lastIndex += 1; continue; }
    n += 1;
    if (n > 1) break;
  }
  return n === 1 ? "once" : n === 0 ? "absent" : "twice";
}

/** The block whose OWN addressed span is exactly `file:line_start-line_end`, or undefined.
 *
 *  The bridge between the two lanes: `historySpan` answers a hunk, `expectedOf` answers the
 *  token of a block the read published. A `prose` token is minted over the bytes of the span
 *  the request names (`review_surface._span_identities`, home id
 *  `<project>::<file>:<a>-<b>`), so a token is only ever the right one when the hunk IS that
 *  block's span -- a token for a wider or narrower span is a home the door does not address,
 *  and sending it would be a refusal the retry cannot cure. Exact match or nothing; nothing
 *  is the path `expectedOf` already documents, where the door's byte guard decides. */
function blockAtSpan(file, line_start, line_end) {
  return S.blocks.find((b) => { const s = srcOf(b);
    return s.file === file && s.lineStart === line_start && s.lineEnd === line_end; });
}

/** The comment target of a rendered block, or of a range inside ONE block: the pure mapper over this block's own
 *  source and piece map, with rendered offsets read by the same chrome-skipping reader as every gesture here. A range
 *  crossing blocks is not mapped (one source block per comment target). */
function commentTargetOf(b, range = null) {
  const host = b && (b.bodyEl || b.el);
  const display = host ? hostText(host) : "";
  if (!range) return commentSourceSelection({ tex: b && b.tex, pieceMap: b && b.pieceMap, display });
  if (!host || !host.contains(range.startContainer) || !host.contains(range.endContainer))
    return { refused: "multi-source", reason: "This selection crosses paragraphs; comment on one paragraph at a time.", choices: [] };
  const start = offsetIn(host, range.startContainer, range.startOffset);
  const end = offsetIn(host, range.endContainer, range.endOffset);
  return commentSourceSelection({ tex: b.tex, pieceMap: b.pieceMap, display, start: Math.min(start, end), end: Math.max(start, end) });
}

/** The rendered-offset → text-node address, chrome-skipped like every reader here. */
function nodeAt(host, at) {return readableDOM(host).point(at);}

function liveRangeFrom(sr) {
  try {
    const r = document.createRange();
    r.setStart(sr.startContainer, sr.startOffset);
    r.setEnd(sr.endContainer, sr.endOffset);
    return r;
  } catch (_e) { return null; }
}

/** The piece whose rendered span holds the character at `at`, or "". */
function pieceTypeAt(map, at) {
  for (const p of map) if (at >= p.rStart && at < p.rEnd) return p.t;
  return "";
}

/** The anchor for a typed edit — `anchorFromBlock`'s shape, sliced from the PRISTINE
 *  snapshot: the piece map was measured against exactly that text, so `start`/`end`
 *  address it without any re-read of the now-edited DOM. */
function anchorFromPristine(b, full, start, end) {
  const s = srcOf(b);
  return {
    grade: "selection", blockId: b.id, kind: b.kind || "para",
    sectionId: b.sectionId, sectionTitle: sectionTitle(b.sectionId),
    ...paragraphSourceIdentity(b), label: b.label || "", figLabel: figLabelOf(b),
    file: s.file, lineStart: s.lineStart, lineEnd: s.lineEnd,
    texFace: !!b.texFace,
    quote: norm(full.slice(start, end)), start, end,
    before: norm(full.slice(Math.max(0, start - CONTEXT_CHARS), start)),
    after: norm(full.slice(end, end + CONTEXT_CHARS)),
    tex: b.tex || "",
  };
}

export {
  anchorForWholeBlock, anchorFromPristine, anchorFromRange, blockAtSpan, closestBlock, commentTargetOf, figLabelOf, hostText,
  liveRange, liveRangeFrom, nodeAt, nodeTextLen, offsetIn, pieceEdge, pieceSpanOf, pieceTypeAt, rangeInBlock,
  readableDOM, sourceForRenderedRange, spliceOf, spliceState, srcLabel, srcOf, toSourceRegister
};
