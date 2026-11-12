// conceptric-panes.mjs — The conceptric surface's pane logic (W3), a SHARED module.
//
// The approved mock (mocks/conceptric.html, D1–D16, PR #72) is the contract this realises
// over the REAL /corpus/* data layer + the shared shell chrome:
//   · the BOARD owns the centre; the grade chips are SERVER SLICES — a chip click changes
//     THE FETCH (/corpus/grade?g=) and the board's slice token (the grade proof); a CSS-only
//     re-bucket would be a census defect, so the descent never re-buckets client-side (D4/D5);
//   · node CARDS wear kind badges + `↑ fold` / `↓ open` with the words AT REST (R3/D6); a card
//     select updates the INSPECTOR column with ZERO board reflow (L3/D7);
//   · the INSPECTOR (the .hy-ins idiom): term/id/kind/roles · ALTITUDE (grade + clickable
//     ancestry hops) · essence · GROUNDS lane (derives-from chips w/ provenance + all-attested /
//     N-unconfirmed summary) · ARGUES-IN (a structural sec:* node reads "carries members, argues
//     nothing" — F9; its doors say their scope in words) · cites · DOORS·this-node · ✎ rule (D16);
//   · Find-node never blocks (F1/PSU): a keystroke-instant lexical filter over the built index;
//     when vectors are stale/off the plain warn chip + an is-offer remedy reveal (D9/D10).
// Behaviour lives here so conceptric.html stays inside the per-surface island budget; ALL network
// rides store.fetchJSON (the one gateway) — no raw fetch escapes the model on this surface.

import store from "/shared/store.mjs";

// ── tiny helpers ──────────────────────────────────────────────────────────────
const ec = encodeURIComponent;
const esc = (s) => String(s == null ? "" : s)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
  .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const cut = (s, n) => { s = String(s == null ? "" : s); return s.length > n ? s.slice(0, n - 1) + "…" : s; };
const noMath = (s) => String(s == null ? "" : s).replace(/\$/g, "");

// ── injected COMPONENT CSS (visual §6.2 relocation) ─────────────────────────────
// The COMPONENT atoms — the cx-* layout for DOM this module builds (the ↑/↓ affordances
// with their AT-REST labels, the fold rows, the argues-in door rows, the edge lanes) —
// live here, not in conceptric.html's <style>, so the surface island stays under budget.
// Every hy-* class the cards/chips/doors/echips/ancestry wear comes from hymn.css already;
// this is layout-only and carries NO color literal (every colour is a hymn var — the §6.1
// one-palette clause reaches this text, and there is nothing here to fork it).
const COMPONENT_CSS = `
/* P10 clip law (ACT5/job4): the right rail (#cx-right, conceptric.html's fixed-378px
   inspector column) is a flex item WITHOUT min-width:0 in the page's own layout-only
   <style> — a long unbroken essence/id/label can force it to overflow rather than wrap.
   Injected here (after that <style>, last in <head>) so it wins on the properties it adds
   without touching the page's own layout rules. */
#cx-right{min-width:0}
#cx-right,#cx-right *{overflow-wrap:anywhere}
.cx-asc{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.cx-aff{display:inline-flex;align-items:center;gap:5px;flex:none;cursor:pointer;
  font-family:var(--mono);font-size:11px;color:var(--ink2);
  background:var(--bg);border:1px solid var(--edge);border-radius:6px;padding:2px 8px}
.cx-aff:hover{border-color:var(--accent);color:var(--ink)}
.cx-afflabel{white-space:nowrap;font-family:-apple-system,"Segoe UI",sans-serif;font-size:10px;color:var(--dim)}
.cx-aff:hover .cx-afflabel{color:var(--ink)}
.cx-foldrow{display:flex;align-items:baseline;gap:8px;font-family:var(--mono);font-size:10.5px;color:var(--ink2)}
.cx-foldrow .fr-k{color:var(--dim);flex:none}
.cx-foldrow .fr-v{color:var(--ink2);min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer}
.cx-foldrow:hover .fr-v{color:var(--ink)}
.cx-lane{display:flex;flex-direction:column;gap:7px}
.cx-argrow{display:flex;align-items:center;gap:7px;flex-wrap:wrap}
.cx-argrow .cx-argt{flex:1 1 120px;min-width:0;color:var(--ink2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

/* ── The link-graph chart (his 5th ruling, 2026-07-23: "the conceptric map is defined by its
   links" — so the PRIMARY view draws AS a graph. L3: grade is the vertical axis, apex at top,
   descent downward, orientation conserved. L4: the links are the object — drawn as edges.
   The card list survives as the demoted list lens. Zero color literals — every hue a hymn
   var; the SVG carries the geometry, CSS the palette). ── */
#cx-board.is-graph{overflow:hidden;padding:0;position:relative}
.cxg-wrap{position:absolute;inset:0;overflow:hidden}
svg#cxg{width:100%;height:100%;display:block;touch-action:none;cursor:grab;user-select:none;background:var(--bg)}
svg#cxg.is-panning{cursor:grabbing}
/* --cxg-k (set on the svg per pan/zoom) counters the viewBox scale so text + strokes stay a
   Constant screen size — SVG px are user units, so without this every label balloons on zoom.
   font-size: calc(base * var(--cxg-k)); strokes ride vector-effect:non-scaling-stroke. */
.cxg-band{stroke:var(--edge);stroke-width:1;stroke-dasharray:2 7;vector-effect:non-scaling-stroke}
.cxg-band.is-lit{stroke:var(--accent);stroke-dasharray:none;opacity:.55}
.cxg-bandlbl{fill:var(--dim);font-family:var(--mono);font-size:calc(12px * var(--cxg-k,1));font-weight:700}
.cxg-bandsub{fill:var(--dim);font-family:var(--mono);font-size:calc(8.5px * var(--cxg-k,1));letter-spacing:.09em;text-transform:uppercase}
.cxg-edge{stroke:var(--edge2);stroke-width:1.1;vector-effect:non-scaling-stroke}
.cxg-edge.is-lit{stroke:var(--accent);stroke-width:1.9}
.cxg-edge.is-dim{opacity:.07}
.cxg-loose{fill:var(--dim);opacity:.34;cursor:pointer;r:calc(2.7px * var(--cxg-k,1))}
.cxg-loose:hover{opacity:.85}
.cxg-loose.is-focus{opacity:1;fill:var(--accent)}
.cxg-loose.is-dim{opacity:.09}
.cxg-node{cursor:pointer}
.cxg-node.is-dim{opacity:.12}
.cxg-dot{stroke:var(--bg);stroke-width:1.5;vector-effect:non-scaling-stroke;r:calc(6px * var(--cxg-k,1))}
.cxg-node:hover .cxg-dot{stroke:var(--ink)}
.cxg-node.is-focus .cxg-dot{stroke:var(--ink);stroke-width:2.4}
.cxg-lbl{fill:var(--ink2);font-family:var(--mono);font-size:calc(10px * var(--cxg-k,1));paint-order:stroke;
  stroke:var(--bg);stroke-width:3.2px;stroke-linejoin:round;pointer-events:none;vector-effect:non-scaling-stroke}
.cxg-node:hover .cxg-lbl,.cxg-node.is-focus .cxg-lbl{fill:var(--ink)}
/* the label gate: a dense band hides its labels until the camera gives them room — but a HOVER
   always reveals the one under the pointer (so nothing is ever truly unreadable — L5). */
.cxg-node.no-lbl .cxg-lbl{display:none}
.cxg-node.no-lbl:hover .cxg-lbl{display:block}
.cxg-orient{position:absolute;left:11px;bottom:9px;font:8.5px var(--mono);letter-spacing:.06em;
  color:var(--dim);text-transform:uppercase;pointer-events:none;opacity:.85}
.cxg-hint{position:absolute;right:12px;bottom:9px;font:9px var(--mono);color:var(--dim);
  pointer-events:none;opacity:.7}
/* the view toggle — the graph is PRIMARY; the list is the demoted lens (L5: nothing hidden) */
.cx-vtoggle{display:inline-flex;border:1px solid var(--edge);border-radius:7px;overflow:hidden;margin-right:6px}
.cx-vtoggle button{font:700 10px var(--mono);letter-spacing:.06em;text-transform:uppercase;
  background:var(--bg);color:var(--dim);border:none;padding:5px 11px;cursor:pointer}
.cx-vtoggle button.is-live{background:var(--accent);color:var(--chipink)}
.cx-vtoggle button:not(.is-live):hover{color:var(--ink)}
/* the door back to the growth cockpit — now that THIS graph is the Grow primary, the cockpit
   (the brief, the review composers, the four growth verbs) lives at /conceptric/cockpit. A grower
   reaches it from the top bar: the demoted surface is one clear labelled click away, never hidden
   (L5). It rides the shell's .hy-door idiom (hymn-owned); only its placement is set here. */
.cx-cockpitdoor{flex:none;white-space:nowrap;margin-left:2px}
.cx-cockpitdoor .cx-cockpitsub{color:var(--dim)}
.cx-cockpitdoor:hover .cx-cockpitsub{color:var(--ink2)}
`;
function injectStyle() {
  if (typeof document === "undefined" || document.getElementById("cx-components")) return;
  const st = document.createElement("style"); st.id = "cx-components"; st.textContent = COMPONENT_CSS;
  document.head.appendChild(st);
}

// ── module state (one surface, one model) ──────────────────────────────────────
let CORPUS = null;
let META = null;              // /corpus/meta — grades {g: count}, kinds
let PLAN = null;              // /shared/plan — sections (the argues-in + ancestry source)
let INDEX = [];               // /corpus/map nodes — The built index the find ranks over (all nodes)
let DEGRADED = false;         // router_cache degraded (semantic rank off) — from /shared/staleness
let DEGRADED_FIX = "";        // the runnable remedy the degraded chip reveals (server's own fix line)
const STRATA = {};            // grade → /corpus/grade payload (the cached SERVER SLICE)
const CONTENT = {};           // id → /corpus/content
const NB = {};                // id → /corpus/neighborhood (grounds/consumers, by provenance)
let GRADE = null;             // the active board slice grade (the LIST lens' server slice)
let FOCUS = null;             // the selected node (URL-canonical: ?node=)
const OPEN = {};              // OPEN[id] = "up" | "down" | null — the card fold direction
// ── the link-graph is the PRIMARY view (his 5th ruling); the card list is the demoted lens ──
let EDGES = [];               // /corpus/map edges — the links the graph is DEFINED by (from/to)
let VIEW = "graph";           // "graph" (primary chart) | "list" (the demoted card lens)
let GADJ = null;              // id → [neighbour ids] (undirected), built once per load
let GPOS = null;              // id → {x,y,g,conn} — the fixed world-coordinate layout
let GWORLD = null;            // {w,h,grades,topG,connByG} — the world box + per-band metadata
let GVB = null;               // the live viewBox {x,y,w,h} — pan/zoom mutates this in world units
const GNS = "http://www.w3.org/2000/svg";
// layout constants (world units): grade → y band; connected on the band line, loose as sediment
const G_SPX = 42, G_PADX = 74, G_PADTOP = 58, G_PADBOT = 46, G_BANDGAP = 118, G_LOOSE_DY = 22;

// ── math (shell's KaTeX atom; a no-op if the shell has not booted yet) ──────────
function paintMath(el) { try { if (el && window.renderMath) window.renderMath(el); } catch (_e) { /* math is a bonus, never a blocker */ } }
function kbadge(kind) { return "<span class='hy-kbadge " + esc(kind || "") + "'>" + esc(kind || "node") + "</span>"; }
const isStructural = (id) => typeof id === "string" && id.indexOf("sec:") === 0;

// ═══════════════ BOOT ═══════════════
export async function initConceptric() {
  injectStyle();
  // the SPA in-place selection door: the shell's echo/ladder/openNode drive THIS, not a reload.
  if (typeof window !== "undefined") window.__hymnOpenNode = (id) => selectNode(id);

  if (!store.field("corpus")) {
    try {
      const list = await store.fetchJSON("/corpus/list", { inject: [] });
      const cp = (list && (list.default || (list.corpora || [])[0])) || null;
      if (cp) store.set({ corpus: cp }, { replace: true });
    } catch (_e) { /* no corpus resolvable — the board states it below */ }
  }
  CORPUS = store.field("corpus");
  store.subscribe(reactToStore);   // Back/Forward + store.set re-select through here
  await load();
}

async function load() {
  CORPUS = store.field("corpus");
  const board = $("#cx-board");
  if (!CORPUS) { if (board) board.innerHTML = "<div class='cx-empty'>no corpus resolved — open /conceptric?corpus=&lt;name&gt; to pick one.</div>"; return; }
  // the reads: META (grade counts), PLAN (argues-in/ancestry), the BUILT INDEX (all nodes for
  // find), and the declared staleness verdict (the degraded chip's ONLY truth source).
  const [meta, plan, map, stale] = await Promise.all([
    store.fetchJSON("/corpus/meta").catch(() => null),
    store.fetchJSON("/shared/plan").catch(() => null),
    store.fetchJSON("/corpus/map").catch(() => ({ nodes: [] })),
    store.fetchJSON("/shared/staleness").catch(() => null),
  ]);
  META = meta || { grades: {} }; PLAN = plan; INDEX = (map && map.nodes) || []; EDGES = (map && map.edges) || [];
  const rc = stale && (stale.reads || []).find((r) => r.id === "router_cache");
  DEGRADED = !!(rc && rc.degraded); DEGRADED_FIX = (rc && rc.fix) || "";

  // the focus + active grade: honour ?node= when present; else open on a SPINE node (the
  // narrative chain the ruling names — a meaningful landing, never the lone apex or a leaf).
  FOCUS = store.field("node") || null;
  const keys = gradeKeys();
  if (!FOCUS) { const seed = INDEX.find((n) => n.spine) || INDEX[0] || null; FOCUS = seed ? seed.id : null; }
  const focusGrade = FOCUS ? nodeGrade(FOCUS) : null;
  GRADE = (focusGrade != null && keys.includes(focusGrade)) ? focusGrade : (keys.length ? keys[keys.length - 1] : 0);
  try { await ensureStratum(GRADE); } catch (_e) { /* the board states the slice failure below */ }
  if (FOCUS && !store.field("node")) store.set({ node: FOCUS }, { replace: true });
  renderStrata(); ensureCockpitDoor(); renderCentre();
  if (FOCUS) renderInspector();
  refreshSelToken();
}

// grade keys, ascending ints, from META.grades ({"0":n,"1":n,…}) — the LIST lens' server slices
function gradeKeys() { return Object.keys((META && META.grades) || {}).map(Number).filter((n) => !Number.isNaN(n)).sort((a, b) => a - b); }
function gradeCount(g) { return (META && META.grades && META.grades[String(g)]) || 0; }
// the GRAPH's own bands come from the drawn nodes (/corpus/map), so every band the chart shows is
// framable — META.grades (the slice source) can carry a different grade set than the DAG does.
function graphGradeKeys() { return [...new Set(INDEX.map((n) => (n.grade != null ? n.grade : 0)))].sort((a, b) => a - b); }
function graphGradeCount(g) { return INDEX.filter((n) => (n.grade != null ? n.grade : 0) === g).length; }
function nodeGrade(id) { const n = INDEX.find((x) => x.id === id); return n && n.grade != null ? n.grade : null; }

// ═══════════════ the grade strip — SERVER SLICES (D4) ═══════════════
function renderStrata() {
  const strata = $("#cx-strata"); if (!strata) return;
  const graph = VIEW === "graph";
  const keys = graph ? graphGradeKeys() : gradeKeys();
  // the view toggle (graph is primary; list is the demoted lens) leads the bar; the grade chips
  // FRAME a band in graph mode (a continuous camera move, L2) and SLICE the server in list mode.
  const toggle = "<span class='cx-vtoggle' data-cgroup='view'>" +
    "<button type='button' data-view='graph' class='" + (graph ? "is-live" : "") + "'>graph</button>" +
    "<button type='button' data-view='list' class='" + (!graph ? "is-live" : "") + "'>list</button></span>";
  const label = "<span class='cx-slabel'>" + (graph ? "grade bands" : "graded descent") + "</span>";
  const chips = keys.length
    ? keys.map((g) =>
        "<button type='button' class='hy-chip is-offer" + (!graph && g === GRADE ? " is-live" : "") +
        "' data-grade='" + g + "' title='" + (graph
          ? "frame the g" + g + " band"
          : "server slice — /corpus/grade?corpus=" + esc(CORPUS) + "&g=" + g) +
        "'>g" + g + "<span class='hy-chip-n'>" + (graph ? graphGradeCount(g) : gradeCount(g)) + "</span></button>"
      ).join("")
    : "<span class='cx-slabel'>no graded stock</span>";
  strata.innerHTML = toggle + label + chips;
  renderDegraded();
}
// the degraded chip lives beside find; it RENDERS IFF the server reports degraded (D10 — never
// green painted over a stale read; the fix is an OFFER a click reveals, never a POST/hang).
function renderDegraded() {
  const find = $("#cx-find"); if (!find) return;
  const old = $("#cx-degraded-wrap"); if (old) old.remove();
  if (!DEGRADED) return;
  const wrap = document.createElement("span"); wrap.id = "cx-degraded-wrap";
  wrap.style.cssText = "display:inline-flex;flex-direction:column;gap:5px;align-items:flex-end";
  wrap.innerHTML =
    "<button type='button' class='hy-chip is-warn is-offer' id='cx-degraded' " +
      "title='semantic rank is off — click for the runnable remedy'>vectors stale — semantic rank off</button>" +
    "<div class='hy-chip-fix' id='cx-degraded-fix'>" + esc(DEGRADED_FIX ||
      "re-embed at the supervised close; the local serving path never embeds — lexical search stays instant, semantic rank is an offer.") +
    "</div>";
  find.appendChild(wrap);
}
// the door to the growth cockpit (the brief, the review composers, the four growth verbs). Added
// once to the boardbar, kept net of the innerHTML re-renders (they touch #cx-strata / #cx-find,
// not the bar's own children); the href re-rides the current corpus on every load. It navigates
// (a real .hy-door <a> — the delegated handler lets doors go), so the cockpit page fully arrives.
function ensureCockpitDoor() {
  const bar = $("#cx-boardbar"); if (!bar) return;
  let d = $("#cx-cockpit-door");
  if (!d) {
    d = document.createElement("a");
    d.id = "cx-cockpit-door";
    d.className = "hy-door cx-cockpitdoor";
    d.title = "the growth cockpit — the project brief, the review composers, and the four growth verbs";
    d.innerHTML = "growth cockpit <span class='cx-cockpitsub'>— brief · composers · growth verbs</span> →";
    bar.appendChild(d);
  }
  d.setAttribute("href", "/conceptric/cockpit?corpus=" + ec(CORPUS || ""));
}

// ═══════════════ THE BOARD — the grade slice OR the find result set ═══════════════
async function ensureStratum(g) {
  if (!(g in STRATA)) STRATA[g] = await store.fetchJSON("/corpus/grade", { params: { g } });
  return STRATA[g];
}
// the find rank: keystroke-instant, lexical, over the BUILT INDEX — zero fetch, zero timer,
// zero pretend-latency (F1/D9: nothing the user types can hang the box).
function findIds(q) {
  q = q.trim().toLowerCase();
  if (!q) return null;
  const scored = [];
  for (const n of INDEX) {
    const hay = (n.id + " " + (n.essence || "") + " " + (n.label || "")).toLowerCase();
    const pos = hay.indexOf(q);
    if (pos >= 0) scored.push({ id: n.id, s: (n.id.toLowerCase().indexOf(q) >= 0 ? 0 : 1) * 100000 + pos });
  }
  scored.sort((a, b) => a.s - b.s);
  return scored.map((x) => x.id);
}
function boardNode(id) {
  // a board card's self-describing facts: prefer the slice payload (kind/grade ride it — the
  // grade_view enrichment), fall back to the built index (find results) or a bare id.
  const sl = STRATA[GRADE]; const inSlice = sl && (sl.nodes || []).find((n) => n.id === id);
  if (inSlice) return inSlice;
  const idx = INDEX.find((n) => n.id === id);
  if (idx) return idx;
  return { id, kind: null, essence: null };
}
function renderBoard() {
  const board = $("#cx-board"); if (!board) return;
  const q = ($("#cx-find-in").value || "");
  const found = findIds(q);
  let ids, tok;
  if (found) {
    ids = found;
    tok = "find · " + ids.length + " match" + (ids.length === 1 ? "" : "es") + " over the built index (" + INDEX.length + " nodes)";
  } else {
    const sl = STRATA[GRADE];
    ids = sl ? (sl.nodes || []).map((n) => n.id) : [];
    const cap = sl && sl.capped ? " of " + sl.n_total_at_grade + " (capped)" : "";
    tok = esc(CORPUS) + " · grade g" + GRADE + " · " + ids.length + cap + " node" + (ids.length === 1 ? "" : "s");
  }
  const head = "<div class='cx-sliceid'>" + (found ? "result set" : "stratum") +
    " <span class='cx-slicetok' id='cx-slicetok'>" + tok + "</span></div>";
  const body = ids.length
    ? "<div class='cx-col'>" + ids.map((id, i) => cardHTML(boardNode(id), i === 0)).join("") + "</div>"
    : "<div class='cx-empty'>" + (found ? "no node matches — try fewer letters. (nothing hangs; the filter is lexical and local.)"
                                        : "empty stratum — this grade carries no nodes.") + "</div>";
  board.innerHTML = head + body;
  paintMath(board);
}
function cardHTML(n, first) {
  const id = n.id, open = OPEN[id], struct = isStructural(id);
  const badge = struct ? "<span class='hy-kbadge'>section</span>" : kbadge(n.kind);
  const grade = n.grade != null ? n.grade : GRADE;
  let fold = "";
  if (open === "up") {
    const ups = (NB[id] && NB[id].above) || [];
    fold = ups.length ? ups.map((c) => foldRow("↑ used by", c.id)).join("")
                      : "<div class='hy-none'>no consumers — an apex result.</div>";
  } else if (open === "down") {
    const dns = (NB[id] && NB[id].below) || [];
    fold = dns.length ? dns.map((c) => foldRow("↓ derives-from", c.id)).join("")
                      : "<div class='hy-none'>no derivation dependency (postulate or gap).</div>";
  }
  return "<div class='hy-card is-clickable" + (id === FOCUS ? " is-open" : "") + (struct ? " is-muted" : "") +
      "' data-node='" + esc(id) + "'>" +
    "<div class='hy-card-id'>" + badge + "<span class='hy-card-name'>" + esc(cut(noMath(n.essence || n.label || id), 90)) + "</span>" +
      "<span class='hy-role grade'>g" + grade + "</span></div>" +
    "<div class='hy-card-facts'><span class='fk'>id</span><span class='fv'>" + esc(id) + "</span></div>" +
    "<div class='cx-asc'>" +
      "<button type='button' class='cx-aff' data-aff='up' data-node='" + esc(id) + "' title='fold into parent (used-by)'>↑<span class='cx-afflabel'>fold</span></button>" +
      "<button type='button' class='cx-aff' data-aff='down' data-node='" + esc(id) + "' title='open constituents (derives-from)'>↓<span class='cx-afflabel'>open</span></button>" +
    "</div>" +
    "<div class='hy-card-fold" + (open ? " is-open-fold" : "") + "' style='" + (open ? "display:flex" : "display:none") + "'>" + fold + "</div></div>";
}
function foldRow(k, id) {
  return "<div class='cx-foldrow'><span class='fr-k'>" + esc(k) + "</span><span class='fr-v' data-node='" + esc(id) + "'>" + esc(id) + "</span></div>";
}

// ═══════════════ THE CENTRE — the drawn link-graph (primary) OR the card list (demoted lens) ═══
function renderCentre() {
  const board = $("#cx-board"); if (!board) return;
  if (VIEW === "graph") { renderGraph(); }
  else { board.className = ""; board.style.removeProperty("overflow"); board.style.removeProperty("padding"); renderBoard(); }
}
function setView(v) {
  if (v === VIEW || (v !== "graph" && v !== "list")) return;
  VIEW = v;
  $("#cx-find-in").value = "";       // the overlay is per-lens (graph highlight vs list filter)
  renderStrata(); renderCentre();
}

// the node label, DE-MATHED (his taste, commit 294234a0 "titles de-mathed"): a raw LaTeX essence
// (the equation nodes) reads as its short id handle; a plain-language essence reads as itself.
function cleanLabel(n) {
  const id = n.id || "";
  const s = String(n.essence || n.label || "");
  // a long prose essence reads as its short id handle too (a truncated sentence fragment is
  // noise on a dot); only a genuinely short essence rides as the label.
  const clean = s.replace(/\s+/g, " ").trim();
  if (/[\\^${}]|_\{/.test(s) || clean.length > 16) return cut(id.replace(/^eq:/, "").replace(/^sec:/, ""), 15);
  return cut(clean || id, 15);
}

// the kind → hymn palette var (mirrors hymn.css .hy-kbadge families; SVG fill wants a var name)
function kindFill(kind) {
  const k = String(kind || "").toLowerCase();
  if (k === "definition" || k === "def") return "--accent";
  if (k === "result" || k === "res" || k === "postulate" || k === "pos") return "--ok";
  if (k === "theorem" || k === "thm" || k === "equation") return "--keystone";
  if (k === "lemma" || k === "intermediate-result" || k === "ires" || k === "citation" || k === "ref") return "--teal";
  if (k === "derivation-step" || k === "step") return "--dim";
  if (k === "technique" || k === "tech" || k === "figure" || k === "fig") return "--warn";
  return "--ink2";   // support / unknown
}

// THE LAYOUT (fixed, world coordinates): grade → y band (apex top, descent down — L3); within a
// band the LINKED nodes ride the band line (barycenter-ordered so the edges stay short/legible),
// the loose atoms settle as faint sediment just beneath. Computed once per load; pan/zoom never
// recomputes it — they only move the camera (the viewBox).
export function layoutConceptricGraph(index, edges, {spacing=G_SPX, bandGap=G_BANDGAP, looseDy=G_LOOSE_DY,maxPerBand=Infinity,minWidth=980}={}) {
  const nodes = index.filter((n) => n && n.id != null);
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const adj = new Map();
  const add = (a, b) => { if (!adj.has(a)) adj.set(a, []); adj.get(a).push(b); };
  for (const e of edges) { const a = e.from, b = e.to; if (byId.has(a) && byId.has(b)) { add(a, b); add(b, a); } }

  const band = new Map();       // grade → {conn:[ids], loose:[ids]}
  for (const n of nodes) { const g = (n.grade != null ? n.grade : 0);
    if (!band.has(g)) band.set(g, { conn: [], loose: [] });
    (adj.has(n.id) ? band.get(g).conn : band.get(g).loose).push(n.id); }
  const grades = [...band.keys()].sort((a, b) => a - b);
  const topG = grades.length ? grades[grades.length - 1] : 0;
  // seed order: spine first, then id (stable); fractional position f∈[0,1] normalises band sizes
  const seed = (arr) => arr.slice().sort((a, b) => {
    const na = byId.get(a), nb = byId.get(b), sa = na && na.spine ? 0 : 1, sb = nb && nb.spine ? 0 : 1;
    if (sa !== sb) return sa - sb; return String(a) < String(b) ? -1 : 1; });
  const order = new Map(), frac = new Map();
  for (const g of grades) { const b = band.get(g); const arr = seed(b.conn).concat(seed(b.loose));
    order.set(g, arr); arr.forEach((id, i) => frac.set(id, (i + 0.5) / Math.max(1, arr.length))); }
  // barycenter relaxation: each node chases the mean fractional position of its neighbours
  for (let pass = 0; pass < 6; pass++) {
    const gseq = pass % 2 ? grades.slice().reverse() : grades;
    for (const g of gseq) {
      const key = (id) => { const nb = adj.get(id); if (nb && nb.length) { let s = 0, c = 0;
        for (const m of nb) { const f = frac.get(m); if (f != null) { s += f; c++; } } if (c) return s / c; }
        return frac.get(id); };
      const arr = order.get(g).slice().map((id) => [id, key(id)]).sort((p, q) => p[1] - q[1]).map((p) => p[0]);
      order.set(g, arr); arr.forEach((id, i) => frac.set(id, (i + 0.5) / Math.max(1, arr.length)));
    }
  }
  let maxConn = 1, maxN = 1;
  for (const g of grades) { maxConn = Math.max(maxConn, band.get(g).conn.length || 1); maxN = Math.max(maxN, order.get(g).length); }
  const worldW = Math.max(minWidth, Math.min(maxConn,maxPerBand) * spacing + 2 * G_PADX, Math.min(maxN,70,maxPerBand) * 22 + 2 * G_PADX);
  const pos = new Map(), connByG = {};
  const wrapped=Number.isFinite(maxPerBand),bandY=new Map();let nextY=G_PADTOP;
  if(wrapped)for(const g of grades.slice().reverse()){bandY.set(g,nextY);nextY+=Math.max(1,Math.ceil(order.get(g).length/maxPerBand))*bandGap;}
  for (const g of grades) {
    const y = wrapped?bandY.get(g):G_PADTOP + (topG - g) * bandGap;
    const arr = order.get(g), connSet = new Set(band.get(g).conn);
    const connArr = arr.filter((id) => connSet.has(id)), looseArr = arr.filter((id) => !connSet.has(id));
    connByG[g] = connArr.length;
    connArr.forEach((id, i) => { const f = ((i%maxPerBand) + 0.5) / Math.max(1, Math.min(connArr.length,maxPerBand));
      pos.set(id, { x: G_PADX + f * (worldW - 2 * G_PADX), y:y+(wrapped?Math.floor(i/maxPerBand)*bandGap:0), g, conn: true }); });
    looseArr.forEach((id, i) => { const slot=wrapped?connArr.length+i:i,f=((slot%maxPerBand)+0.5)/Math.max(1,Math.min(wrapped?order.get(g).length:looseArr.length,maxPerBand));
      pos.set(id, { x: G_PADX + f * (worldW - 2 * G_PADX), y:wrapped?y+Math.floor(slot/maxPerBand)*bandGap:y+looseDy, g, conn: false }); });
  }
  const worldH = wrapped?nextY:G_PADTOP + Math.max(0,topG-(grades[0]||0))*bandGap + looseDy + G_PADBOT;
  return {positions:pos, adjacency:adj, world:{w:worldW,h:worldH,grades,topG,connByG}};
}

function computeGraphLayout() {
  const layout=layoutConceptricGraph(INDEX,EDGES);
  GPOS=layout.positions;GADJ=layout.adjacency;GWORLD=layout.world;
}

function renderGraph() {
  const board = $("#cx-board"); if (!board) return;
  board.className = "is-graph";
  if (!INDEX.length) { board.innerHTML = "<div class='cx-empty' style='padding:16px'>no nodes to draw for this corpus.</div>"; return; }
  computeGraphLayout();
  const NBYID = new Map(INDEX.map((n) => [n.id, n]));
  const { w: W, h: H, grades, topG } = GWORLD;
  // the grade axis — a faint guide line + label per band (apex / descent / substrate)
  const gradeName = (g) => g === topG ? "apex" : (g === grades[0] ? "substrate" : "descent");
  let axis = "";
  for (const g of grades) { const y = G_PADTOP + (topG - g) * G_BANDGAP;
    axis += "<line class='cxg-band' data-band='" + g + "' x1='0' y1='" + y + "' x2='" + W + "' y2='" + y + "'></line>" +
      "<text class='cxg-bandlbl' x='12' y='" + (y - 9) + "'>g" + g + "</text>" +
      "<text class='cxg-bandsub' x='12' y='" + (y + 10) + "'>" + esc(gradeName(g)) + "</text>"; }
  // the EDGES — the object the map is defined by (his ruling); drawn as <line> between centres
  let edges = "";
  for (const e of EDGES) { const a = GPOS.get(e.from), b = GPOS.get(e.to); if (!a || !b) continue;
    edges += "<line class='cxg-edge' data-a='" + esc(e.from) + "' data-b='" + esc(e.to) + "' x1='" +
      a.x.toFixed(1) + "' y1='" + a.y.toFixed(1) + "' x2='" + b.x.toFixed(1) + "' y2='" + b.y.toFixed(1) + "'></line>"; }
  // the loose atoms — faint clickable sediment (present, never hidden — L5)
  let loose = "";
  for (const [id, p] of GPOS) { if (p.conn) continue;
    loose += "<circle class='cxg-loose' data-node='" + esc(id) + "' cx='" + p.x.toFixed(1) + "' cy='" + p.y.toFixed(1) + "' r='2.7'></circle>"; }
  // the linked nodes — a kind-coloured dot with a label that surfaces as you zoom (grade motion)
  let nds = "";
  for (const [id, p] of GPOS) { if (!p.conn) continue;
    const n = NBYID.get(id) || {}; const lbl = esc(cleanLabel(n));
    nds += "<g class='cxg-node" + (id === FOCUS ? " is-focus" : "") + "' data-node='" + esc(id) + "' data-g='" + p.g + "'>" +
      "<circle class='cxg-dot' cx='" + p.x.toFixed(1) + "' cy='" + p.y.toFixed(1) + "' r='6' style='fill:var(" + kindFill(n.kind) + ")'></circle>" +
      "<text class='cxg-lbl' x='" + p.x.toFixed(1) + "' y='" + p.y.toFixed(1) + "' dy='-1.15em' text-anchor='middle'>" + lbl + "</text></g>"; }
  board.innerHTML =
    "<div class='cxg-wrap'>" +
      "<svg id='cxg' xmlns='" + GNS + "' viewBox='0 0 " + W + " " + H + "' preserveAspectRatio='xMidYMid meet'>" +
        "<g id='cxg-axis'>" + axis + "</g>" +
        "<g id='cxg-edges'>" + edges + "</g>" +
        "<g id='cxg-loose'>" + loose + "</g>" +
        "<g id='cxg-nodes'>" + nds + "</g>" +
      "</svg>" +
      "<div class='cxg-orient'>apex ↑ · grade · substrate ↓</div>" +
      "<div class='cxg-hint'>scroll = zoom · drag = pan · dbl-click = reset</div>" +
    "</div>";
  fitBase(); wireGraph(); markGraphSelection();
}

// the board pixel box (for camera fitting + label visibility); a safe fallback before layout
function boardPx() { const b = $("#cx-board"); const r = b ? b.getBoundingClientRect() : null;
  return { w: (r && r.width) || 900, h: (r && r.height) || 640 }; }
// fit the whole world into the board, matched to its aspect so `meet` frames it edge-to-edge (L2)
function fitBase() {
  if (!GWORLD) return; const { w: W, h: H } = GWORLD; const bp = boardPx();
  let vw = W * 1.06, vh = H * 1.06; const ar = bp.w / Math.max(1, bp.h);
  if (vw / vh < ar) vw = vh * ar; else vh = vw / ar;
  GVB = { x: (W - vw) / 2, y: (H - vh) / 2, w: vw, h: vh }; applyVB();
}
function applyVB() {
  const svg = $("#cxg"); if (!svg || !GVB) return;
  svg.setAttribute("viewBox", GVB.x.toFixed(1) + " " + GVB.y.toFixed(1) + " " + GVB.w.toFixed(1) + " " + GVB.h.toFixed(1));
  // the zoom-compensation factor: user-units-per-screen-pixel, so calc(base * k) renders constant
  const bp = boardPx(); svg.style.setProperty("--cxg-k", (GVB.w / Math.max(1, bp.w)).toFixed(4));
  applyLabelVis();
}
// labels surface as the camera closes in — a band's labels show once its on-screen node spacing
// clears ~44px (so the sparse apex reads at rest, the dense substrate reveals on zoom). L1/L2.
function applyLabelVis() {
  const svg = $("#cxg"); if (!svg || !GVB || !GWORLD) return;
  const bp = boardPx(); const eff = bp.w / Math.max(1, GVB.w); const innerW = GWORLD.w - 2 * G_PADX;
  // a band's labels show once its on-screen node spacing clears a label-width's room (~86px), so
  // the sparse apex reads at rest and the dense substrate reveals only when you close in on it.
  const show = {};
  for (const g of GWORLD.grades) { const c = (GWORLD.connByG && GWORLD.connByG[g]) || 1; show[g] = (innerW / c) * eff > 104; }
  $$("#cxg-nodes .cxg-node", svg).forEach((el) => {
    const on = show[el.getAttribute("data-g")] || el.classList.contains("is-focus");
    el.classList.toggle("no-lbl", !on);
  });
}

// pan (drag), zoom (wheel, about the cursor), click (a node → the existing node-open door),
// dbl-click (reset). A click is a pointerup that did not travel — so a pan never opens a node.
function wireGraph() {
  const svg = $("#cxg"); if (!svg) return;
  let dragging = false, moved = false, sx = 0, sy = 0, startVB = null, downNode = null;
  svg.addEventListener("wheel", (e) => {
    e.preventDefault(); if (!GVB || !GWORLD) return;
    const r = svg.getBoundingClientRect(); const fx = (e.clientX - r.left) / r.width, fy = (e.clientY - r.top) / r.height;
    const factor = Math.exp(e.deltaY * 0.0016); const minW = GWORLD.w * 0.12, maxW = GWORLD.w * 1.7;
    const nw = Math.min(maxW, Math.max(minW, GVB.w * factor)); const scale = nw / GVB.w; const nh = GVB.h * scale;
    GVB.x += (GVB.w - nw) * fx; GVB.y += (GVB.h - nh) * fy; GVB.w = nw; GVB.h = nh; applyVB();
  }, { passive: false });
  svg.addEventListener("pointerdown", (e) => {
    dragging = true; moved = false; sx = e.clientX; sy = e.clientY; startVB = Object.assign({}, GVB);
    // capture the node UNDER the press now — pointer capture redirects the pointerup target to the
    // svg, so the hit-test must ride the press, not the release (else a click never opens a node).
    downNode = (e.target && e.target.closest) ? e.target.closest("[data-node]") : null;
    svg.classList.add("is-panning"); try { svg.setPointerCapture(e.pointerId); } catch (_e) { /* older UA */ }
  });
  svg.addEventListener("pointermove", (e) => {
    if (!dragging || !startVB) return; const r = svg.getBoundingClientRect();
    if (Math.abs(e.clientX - sx) + Math.abs(e.clientY - sy) > 4) moved = true;
    GVB.x = startVB.x - (e.clientX - sx) * (startVB.w / r.width);
    GVB.y = startVB.y - (e.clientY - sy) * (startVB.h / r.height); applyVB();
  });
  const end = () => {
    if (!dragging) return; dragging = false; svg.classList.remove("is-panning");
    if (!moved && downNode) selectNode(downNode.getAttribute("data-node"));
    downNode = null;
  };
  svg.addEventListener("pointerup", end);
  svg.addEventListener("pointercancel", () => { dragging = false; downNode = null; svg.classList.remove("is-panning"); });
  svg.addEventListener("dblclick", (e) => { e.preventDefault(); fitBase(); });
}

// a grade chip in graph mode is a CAMERA move — frame that band (a continuous map, L2), and light
// its guide line. The layout never re-buckets; only the viewBox moves.
function focusBand(g) {
  if (!GWORLD || !GVB) return; const y = G_PADTOP + (GWORLD.topG - g) * G_BANDGAP;
  const bp = boardPx(); const ar = bp.w / Math.max(1, bp.h);
  let vh = G_BANDGAP * 1.9, vw = vh * ar; if (vw < GWORLD.w * 0.62) { vw = GWORLD.w * 0.62; vh = vw / ar; }
  GVB = { x: (GWORLD.w - vw) / 2, y: y - vh / 2, w: vw, h: vh }; applyVB();
  $$("#cxg-axis .cxg-band").forEach((el) => el.classList.toggle("is-lit", Number(el.getAttribute("data-band")) === g));
}

// the find box in graph mode — HIGHLIGHT the matches, dim the rest (the same lexical predicate the
// list filter uses); an edge lights only when both endpoints match. Empty query clears the dimming.
function graphFindHighlight() {
  const svg = $("#cxg"); if (!svg) return;
  const q = ($("#cx-find-in").value || "").trim().toLowerCase();
  if (!q) { $$(".cxg-node,.cxg-loose,.cxg-edge", svg).forEach((el) => el.classList.remove("is-dim")); applyLabelVis(); return; }
  const NBYID = new Map(INDEX.map((n) => [n.id, n]));
  const hit = (id) => { const n = NBYID.get(id) || {}; return (id + " " + (n.essence || "") + " " + (n.label || "")).toLowerCase().indexOf(q) >= 0; };
  const matched = new Set();
  $$(".cxg-node", svg).forEach((el) => { const id = el.getAttribute("data-node"); const m = hit(id);
    el.classList.toggle("is-dim", !m); if (m) { matched.add(id); el.classList.remove("no-lbl"); } });
  $$(".cxg-loose", svg).forEach((el) => { const id = el.getAttribute("data-node"); const m = hit(id);
    el.classList.toggle("is-dim", !m); if (m) matched.add(id); });
  $$(".cxg-edge", svg).forEach((el) => el.classList.toggle("is-dim",
    !(matched.has(el.getAttribute("data-a")) && matched.has(el.getAttribute("data-b")))));
}

// the graph's selection paint: light the focused node + its incident edges; frame it in only when
// it sits off-camera (an inspector hop from off-screen), so a click on a visible node never lurches.
function markGraphSelection() {
  const svg = $("#cxg"); if (!svg) return;
  $$(".cxg-node,.cxg-loose", svg).forEach((el) => el.classList.toggle("is-focus", el.getAttribute("data-node") === FOCUS));
  $$(".cxg-edge", svg).forEach((el) => el.classList.toggle("is-lit",
    el.getAttribute("data-a") === FOCUS || el.getAttribute("data-b") === FOCUS));
  applyLabelVis();
  const p = GPOS && GPOS.get(FOCUS);
  if (p && GVB && (p.x < GVB.x || p.x > GVB.x + GVB.w || p.y < GVB.y || p.y > GVB.y + GVB.h)) {
    GVB.x = p.x - GVB.w / 2; GVB.y = p.y - GVB.h / 2; applyVB();
  }
}

// ═══════════════ SELECTION — writes ?node=, updates the INSPECTOR only (L3) ═══════════════
function selectNode(id) { if (id && id !== FOCUS) store.set({ node: id }); else if (id) renderInspector(); }
function reactToStore(state) {
  const c = state.selection.corpus;
  if (c && c !== CORPUS) { CORPUS = c; load(); return; }     // a project switch reloads the surface
  const n = state.selection.node;
  if (n && n !== FOCUS) {
    FOCUS = n; markSelection(); renderInspector(); refreshSelToken();
    // 375px: a node change IS a user selection (a card click / a Back) — slide the inspector in.
    // (The initial load renders the inspector WITHOUT this, so first paint never covers the header.)
    if (document.body) document.body.classList.add("insp-open");
  }
}
// toggle ONLY the is-open marker on the existing board cards — never a board re-render, so the
// card hitboxes the pointer is in stay byte-stable (L3/D7: no layout shift under the pointer).
function markSelection() {
  $$("#cx-board .hy-card[data-node]").forEach((el) => el.classList.toggle("is-open", el.dataset.node === FOCUS || !!OPEN[el.dataset.node]));
  if (VIEW === "graph") markGraphSelection();     // the graph carries its own focus paint (L3: centre never reflows)
}
function refreshSelToken() { try { if (window.HymnShell && window.HymnShell.refreshSelToken) window.HymnShell.refreshSelToken(); } catch (_e) { /* the header token is a bonus */ } }

// ═══════════════ THE INSPECTOR ═══════════════
async function renderInspector() {
  const right = $("#cx-right"); if (!right) return;
  if (isStructural(FOCUS)) { renderStructuralInspector(right); return; }
  let c, nb;
  try {
    if (!CONTENT[FOCUS]) CONTENT[FOCUS] = await store.fetchJSON("/corpus/content", { params: { id: FOCUS } });
    if (!NB[FOCUS]) NB[FOCUS] = await store.fetchJSON("/corpus/neighborhood", { params: { id: FOCUS } });
    c = CONTENT[FOCUS]; nb = NB[FOCUS];
  } catch (_e) { right.innerHTML = "<div class='cx-empty' style='padding:18px'>could not load " + esc(FOCUS) + " — the node is absent from this corpus.</div>"; return; }
  const roles = [];
  if (c.spine) roles.push("<span class='hy-role spine'>spine · #" + c.spine.ord + "</span>");
  if (c.postulate) roles.push("<span class='hy-role post'>postulate</span>");
  if (c.retired) roles.push("<span class='hy-role retired'>retired</span>");
  const grade = c.grade != null ? c.grade : "?";
  right.innerHTML =
    "<div class='hy-ins'>" +
    "<div class='hy-ins-head' id='cx-ins-head'>" +
      "<div class='hy-titlerow'>" + kbadge(c.kind) + "<span class='hy-term'>" + esc(cut(noMath(c.essence || c.id), 90)) + "</span>" +
        "<span class='hy-role grade'>grade " + grade + "</span></div>" +
      "<div class='hy-roles'>" + roles.join("") + "</div>" +
      "<div class='hy-nid'>" + esc(FOCUS) + "</div>" +
      // ALTITUDE — the ruling's Phase-2 name: grade + the clickable ancestry hops
      "<div class='hy-sec' style='border:0;padding:9px 0 0'><div class='hy-sec-h'>altitude · grade g" + grade + " · ancestry</div>" +
        ancestryHTML(FOCUS) + "</div>" +
    "</div>" +
    "<div class='hy-sec'><div class='hy-sec-h'>essence</div><div class='hy-ess-body'>" + esc(c.essence || "") + "</div></div>" +
    groundsSection(nb) +
    "<div class='hy-sec'><div class='hy-sec-h'>argues in · where this lands</div>" + arguesLane(FOCUS) + "</div>" +
    citesSection(c) +
    doorsSection(FOCUS, arguesInSections(FOCUS)[0]) +
    "</div>";
  attachRule($("#cx-ins-head"), c);
  paintMath(right);
  markSelection();
}
// the STRUCTURAL section inspector (F9): a sec:* node reached by the ancestry hop reads its true
// nature — it grounds on nothing, carries members, and argues nothing (never "un-mined stock").
function renderStructuralInspector(right) {
  const secId = FOCUS.slice(4);
  const sec = ((PLAN && PLAN.sections) || []).find((s) => s.id === secId) || { id: secId, title: secId, nodes_in_order: [] };
  const members = (sec.nodes_in_order || []).length;
  right.innerHTML =
    "<div class='hy-ins'>" +
    "<div class='hy-ins-head' id='cx-ins-head'>" +
      "<div class='hy-titlerow'><span class='hy-kbadge'>section</span><span class='hy-term'>" + esc(sec.title || secId) + "</span>" +
        "<span class='hy-role grade' style='background:var(--edge);color:var(--ink2)'>structural</span></div>" +
      "<div class='hy-nid'>" + esc(FOCUS) + "</div>" +
      "<div class='hy-sec' style='border:0;padding:9px 0 0'><div class='hy-sec-h'>altitude · section · ancestry</div>" +
        "<div class='hy-anc'><span class='hop'>paper://" + esc(CORPUS) + "</span><span class='sep'>›</span><span class='hop beat'>" + esc(FOCUS) + "</span></div></div>" +
    "</div>" +
    "<div class='hy-sec'><div class='hy-sec-h'>essence</div><div class='hy-ess-body'>" +
      esc(sec.title || secId) + " — the section carries " + members + " member node" + (members === 1 ? "" : "s") + ".</div></div>" +
    "<div class='hy-sec'><div class='hy-sec-h'>grounds · derives-from</div>" +
      "<div class='hy-none'>structural section — grounded on nothing; it carries members.</div></div>" +
    "<div class='hy-sec'><div class='hy-sec-h'>argues in · where this lands</div>" +
      "<div class='hy-none'>structural section — carries members, argues nothing.</div></div>" +
    "<div class='hy-sec'><div class='hy-sec-h'>cites</div><div class='hy-none'>no citations.</div></div>" +
    doorsSection(FOCUS, secId) +
    "</div>";
  attachRule($("#cx-ins-head"), { id: FOCUS, kind: "section" });
}

// ancestry — paper › section › node; the section hop is a real selection into the sec:* node (F9 path)
function ancestryHTML(id) {
  const secId = (arguesInSections(id)[0] || {}).id;
  const paper = "<span class='hop'>paper://" + esc(CORPUS) + "</span>";
  const node = "<span class='hop'>" + esc(id) + "</span>";
  if (!secId) return "<div class='hy-anc'>" + paper + "<span class='sep'>›</span>" + node + "</div>";
  return "<div class='hy-anc'>" + paper + "<span class='sep'>›</span>" +
    "<span class='hop beat' data-node='sec:" + esc(secId) + "'>sec:" + esc(secId) + "</span><span class='sep'>›</span>" + node + "</div>";
}
// GROUNDS — derives-from, from /corpus/neighborhood.below grouped by provenance, with the
// all-attested (ok) vs N-unconfirmed (warn) summary the ruling asks for.
function groundsSection(nb) {
  const below = (nb && nb.below) || [];
  let lane, summary = "";
  if (!below.length) { lane = "<div class='hy-none'>no derivation dependency — a postulate/foundational definition.</div>"; }
  else {
    const unconf = below.filter((d) => d.prov === "semantic" || d.prov === "candidate").length;
    summary = unconf ? "<span class='hy-chip is-warn'>" + unconf + "<span class='hy-chip-n'>unconfirmed</span></span>"
                     : "<span class='hy-chip is-ok'>all attested</span>";
    lane = "<div class='hy-edges'>" + below.map((d) => echip(d.id, d.prov)).join("") + "</div>";
  }
  return "<div class='hy-sec'><div class='hy-sec-h'>grounds · derives-from " + summary + "</div>" + lane + "</div>";
}
function echip(id, prov) {
  return "<span class='hy-echip' data-node='" + esc(id) + "'><span class='eid'>" + esc(cut(id, 40)) + "</span>" +
    (prov ? "<span class='eprov " + esc(prov) + "'>" + esc(prov) + "</span>" : "") + "</span>";
}
// ARGUES-IN — the plan sections this node argues in, each a scoped door (N1: the door says its
// scope IN WORDS — `read §N3 →`). Declared absence when the plan carries the node nowhere.
function arguesLane(id) {
  const secs = arguesInSections(id);
  if (PLAN == null) return "<div class='hy-none'>no projection plan for this corpus — nothing to argue in yet.</div>";
  if (!secs.length) return "<div class='hy-none'>no section carries this node yet — it argues nowhere in the current plan.</div>";
  return "<div class='cx-lane'>" + secs.map((s) => {
    const beat = (s.beats || [])[0];
    const read = "/artefact?corpus=" + ec(CORPUS) + "&node=" + ec(id) + "&section=" + ec(s.id);
    const board = "/storyboard?corpus=" + ec(CORPUS) + "&node=" + ec(id) + (beat ? "#" + ec(beat) : "");
    return "<div class='cx-argrow'><span class='hy-role grade'>" + esc(s.id) + "</span>" +
      "<span class='cx-argt'>" + esc(cut(s.title || "", 40)) + "</span>" +
      "<a class='hy-door' href='" + read + "' title='section-scope: the section this node argues in, in the reader'>read §" + esc(s.id) + " →</a>" +
      "<a class='hy-door' href='" + board + "' title='section-scope: the section on the storyboard'>board §" + esc(s.id) + " →</a></div>";
  }).join("") + "</div>";
}
function arguesInSections(id) {
  if (!PLAN || !Array.isArray(PLAN.sections)) return [];
  return PLAN.sections.filter((s) => (s.nodes_in_order || []).includes(id) || (s.beats || []).includes(id) || (s.figures || []).includes(id));
}
function citesSection(c) {
  const cites = c.cites || [];
  if (!cites.length) return "<div class='hy-sec'><div class='hy-sec-h'>cites</div><div class='hy-none'>no citations.</div></div>";
  return "<div class='hy-sec'><div class='hy-sec-h'>cites <span class='hy-chip'>" + cites.length + "</span></div>" +
    "<div class='hy-edges'>" + cites.map((x) => echip(x.id, "citation")).join("") + "</div></div>";
}
// DOORS · this node (D12/N1) — real <a href> carrying the URL-canonical selection; the DOORS
// zone is node-scope (says `this node`), distinct from the section-scope argues-in doors.
function doorsSection(id, secId) {
  const read = "/artefact?corpus=" + ec(CORPUS) + "&node=" + ec(id) + (secId ? "&section=" + ec(secId) : "");
  const board = "/storyboard?corpus=" + ec(CORPUS) + "&node=" + ec(id) + (secId ? "#" + ec(secId) : "");
  const desk = "/desk?corpus=" + ec(CORPUS) + "&node=" + ec(id);
  return "<div class='hy-sec' style='border:0'><div class='hy-sec-h'>doors · this node</div><div class='hy-links'>" +
    "<a class='hy-door is-primary' href='" + read + "'>read → artefact</a>" +
    "<a class='hy-door' href='" + board + "'>board → storyboard beat</a>" +
    "<a class='hy-door' href='" + desk + "'>desk → decisions</a></div></div>";
}
// ✎ rule in the inspector head (D16) — the shell's rule-in-place atom, banked to /corpus/friction.
function attachRule(head, c) {
  if (!head) return;
  try {
    const R = window.HymnShell && window.HymnShell.hyRule;
    if (R && R.attach) R.attach(head, { surface: "conceptric", title: c.id, project: CORPUS, node: c.id, kind: c.kind });
  } catch (_e) { /* the mouth is a bonus atom; its absence never breaks the inspector */ }
}

// ═══════════════ WIRING — one delegated handler; find is instant (input event, no timer) ═══════
function wire() {
  // Other writing views reuse the layout without mounting this legacy surface.
  if (!$("#cx-board")) return;
  document.body.addEventListener("click", async (e) => {
    const vt = e.target.closest(".cx-vtoggle [data-view]");
    if (vt) { setView(vt.getAttribute("data-view")); return; }
    const grade = e.target.closest("[data-grade]");
    if (grade) {
      const g = Number(grade.dataset.grade);
      if (VIEW === "graph") { focusBand(g); $$("#cx-strata [data-grade]").forEach((b) => b.classList.toggle("is-live", Number(b.dataset.grade) === g)); }
      else { await setGrade(g); }
      return;
    }
    const aff = e.target.closest(".cx-aff");
    if (aff) { e.stopPropagation(); await toggleFold(aff.dataset.node, aff.dataset.aff); return; }
    if (e.target.closest("#cx-degraded")) { const f = $("#cx-degraded-fix"); if (f) f.classList.toggle("is-open"); return; }
    const foldv = e.target.closest(".cx-foldrow .fr-v[data-node]"); if (foldv) { selectNode(foldv.dataset.node); return; }
    const hop = e.target.closest(".hy-anc .hop[data-node]"); if (hop) { selectNode(hop.dataset.node); return; }
    const ech = e.target.closest(".hy-echip[data-node]"); if (ech) { selectNode(ech.dataset.node); return; }
    // real doors (.hy-door with href) NAVIGATE — never intercepted (D12: buttons mutate, doors go).
    if (e.target.closest("a.hy-door")) return;
    const card = e.target.closest(".hy-card[data-node]"); if (card) { selectNode(card.dataset.node); return; }
  });
  // keystroke-instant, synchronous, no fetch: graph mode highlights the matches in place; list
  // mode re-filters the cards. Both ride the same lexical predicate over the built index.
  $("#cx-find-in").addEventListener("input", () => { if (VIEW === "graph") graphFindHighlight(); else renderBoard(); });
  // the camera re-fits on a resize only while framed at base (a mid-zoom camera is left untouched).
  if (typeof window !== "undefined") {
    let rt = null;
    window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(() => { if (VIEW === "graph" && $("#cxg")) applyVB(); }, 160); });
  }
}
async function setGrade(g) {
  if (g === GRADE && !($("#cx-find-in").value || "")) return;
  try { await ensureStratum(g); } catch (_e) { /* the board states the slice failure below */ }
  GRADE = g;
  $$("#cx-strata [data-grade]").forEach((b) => b.classList.toggle("is-live", Number(b.dataset.grade) === g));
  $("#cx-find-in").value = "";   // a slice change clears the find overlay
  renderBoard();                 // re-render the board (the slice token — the grade proof — changes)
}
async function toggleFold(id, dir) {
  OPEN[id] = (OPEN[id] === dir) ? null : dir;
  if (OPEN[id] && !NB[id]) { try { NB[id] = await store.fetchJSON("/corpus/neighborhood", { params: { id } }); } catch (_e) { NB[id] = { above: [], below: [] }; } }
  renderBoard();   // the fold displaces content BELOW only (L3): the card's own header stays put
}

// wire on boot (after the DOM skeleton exists — initConceptric runs from a module script at end of body)
if (typeof document !== "undefined") {
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", wire);
  else wire();
}
