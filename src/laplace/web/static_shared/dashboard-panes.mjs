// dashboard-panes.mjs — THE DASHBOARD's pane logic (W-DASH), the surface's join to the
// one instrument (engine.mjs).
//
// The dashboard's resting altitude is the composed BRIEF of the WHOLE (delta-and-ask): what
// moved and the single decision or run most consequential NOW, plus the count chips. The
// project cards are the SUMMONABLE inventory — materialised behind one open, never present at
// rest. Opening a card REALLOCATES (the engine's focus geometry) to that project's detail with
// a named return door "back to the brief" and a DESCENT door into its cockpit (/conceptric?
// via=dashboard). A HOT arrival (?project= / ?corpus=) skips the brief and lands pre-focused on
// that project — the brief is the cold-arrival default, never a toll on a hot one (DESIGN B.5).
//
// The lock-step law: the brief is composed server-side (/dashboard/brief) over the SAME read
// model the cards read (/dashboard/data); this module renders it verbatim and re-derives no
// truth. Every card keeps its truth chips (growth SEEDED, verdict position words, release
// verdict) — one producer each; we re-dress geometry, never re-compute state. All network rides
// the store gateway passed in; all colour is a hymn var.

import { injectEngineCSS, createFocusState, HighlightBus, HoverLens, Reallocator, activate, returnDoor }
  from "/shared/engine.mjs";

const esc = (s) => String(s == null ? "" : s)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
const enc = (s) => encodeURIComponent(String(s || ""));
const low = (s) => String(s || "").toLowerCase().replace(/_/g, " ");
const day = (s) => String(s || "").split("T")[0];
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const DASH_CSS = `
#dash{max-width:1200px;margin:0 auto;padding:20px 20px 96px}
#eng-root{min-width:0}
.dash-brief{display:flex;flex-direction:column;gap:16px}
.dash-prose{font-size:14.5px;line-height:1.7;color:var(--ink);max-width:76ch;margin:6px 0 0}
.dash-integrity{max-width:76ch;border:1px solid var(--bad);border-left-width:3px;border-radius:9px;
  background:var(--panel);padding:9px 12px;font:10.5px/1.55 var(--mono);color:var(--bad)}
.dash-conseq{border:1px solid var(--accent);border-left-width:3px;border-radius:11px;background:var(--panel);
  padding:13px 15px;display:flex;flex-direction:column;gap:9px;max-width:76ch}
.dash-conseq .dc-h{font-family:var(--mono);font-size:9px;text-transform:uppercase;letter-spacing:.11em;
  color:var(--accent);font-weight:700}
.dash-conseq .dc-glance{font-size:13px;line-height:1.55;color:var(--ink)}
.dash-conseq .dc-doors{display:flex;gap:8px;flex-wrap:wrap}
.dash-counts{display:flex;flex-wrap:wrap;gap:10px;margin-top:2px}
.dash-count{display:inline-flex;align-items:center;gap:7px;cursor:pointer;background:var(--panel);
  border:1px solid var(--edge2);border-radius:9px;padding:8px 12px;font:inherit;color:var(--ink2);min-width:0}
.dash-count:hover{border-color:var(--accent);color:var(--ink)}
.dash-count:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.dash-count.is-open{border-color:var(--keystone);color:var(--ink);box-shadow:inset 0 0 0 1px var(--keystone)}
/* a count that cannot act (n=0) drops the button shell entirely — a plain census word,
   never a dead button (finding 6: one interactive style, no dead shells). */
.dash-count.is-quiet{background:none;border:1px solid transparent;color:var(--dim);cursor:default}
.dash-count.is-quiet:hover{border-color:transparent;color:var(--dim)}
.dash-count .dc-n{font-family:var(--mono);font-weight:700;color:var(--ink);font-size:14px}
.dash-count.is-quiet .dc-n{color:var(--dim)}
.dash-count .dc-l{font-size:11.5px}
.dash-count.lit{box-shadow:inset 0 0 0 1px var(--warn)}
/* the in-place list a census chip (decisions / orders) clicks through to — no navigation,
   the count opens exactly what it counts, right under the chips. */
.dash-counts-panel:empty{display:none}
/* the in-place census list matches THE PAPERS width (finding 3): the orders/decisions panel
   reads as a peer of the papers card beneath the same chips, not a ~550px stub beside it. */
.dash-counts-panel{border:1px solid var(--edge2);border-left:3px solid var(--keystone);border-radius:11px;
  background:var(--panel);padding:11px 13px;display:flex;flex-direction:column;gap:8px;max-width:960px;margin-top:2px}
.dcp-h{font-family:var(--mono);font-size:9px;text-transform:uppercase;letter-spacing:.11em;color:var(--dim);font-weight:700}
.dcp-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:5px 0;border-top:1px solid var(--edge)}
.dcp-row:first-of-type{border-top:none}
.dcp-proj{font-size:12px;font-weight:650;color:var(--ink);min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dcp-what{font-size:11.5px;color:var(--ink2);flex:1 1 200px;min-width:0}
.dcp-row .hy-door{margin-left:auto}
.dcp-foot{padding-top:8px;border-top:1px solid var(--edge)}
.dcp-empty{font-size:11.5px;color:var(--dim)}
/* ═══ THE PAPERS — the whole, seeable at rest (the sweep, 2026-07-22). His live work
   as a designed picture: one tile per live paper (name + position words, its state on
   the left edge, an amber ask when a decision waits); the scaffolds as a QUIET
   shelf-edge of names beneath — present, never noise. Opening a tile descends into
   the same pinned project focus the inventory serves. ═══ */
.dash-papers{border:1px solid var(--edge2);border-radius:14px;background:var(--panel);
  padding:14px 16px 12px;display:flex;flex-direction:column;gap:11px;max-width:960px}
.dpp-h{font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.12em;
  color:var(--dim);font-weight:700}
.dpp-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:9px}
.dpp-tile{border:1px solid var(--edge2);border-left:3px solid var(--edge2);border-radius:9px;
  background:var(--panel2);padding:9px 12px;display:flex;flex-direction:column;gap:3px;
  cursor:pointer;min-width:0}
.dpp-tile:hover{border-color:var(--accent)}
.dpp-tile:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.dpp-tile.edge-live{border-left-color:var(--accent)}
.dpp-tile.edge-ok{border-left-color:var(--ok)}
.dpp-tile.edge-warn{border-left-color:var(--warn)}
.dpp-tile .pn{font-size:13px;font-weight:650;color:var(--ink);letter-spacing:-.01em;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dpp-tile .pw{font:10px var(--mono);color:var(--ink2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dpp-tile .ask{font:9.5px var(--mono);color:var(--warn)}
.dpp-shelf{display:flex;flex-wrap:wrap;gap:6px;align-items:center;
  border-top:1px dashed var(--edge);padding-top:10px}
.dpp-shelf .sh-l{font:9.5px var(--mono);color:var(--dim);text-transform:uppercase;letter-spacing:.09em}
.dpp-scaf{font:10.5px var(--mono);color:var(--dim);background:none;border:1px dashed var(--edge2);
  border-radius:999px;padding:2px 10px;cursor:pointer}
.dpp-scaf:hover{color:var(--ink2);border-color:var(--accent)}
/* birth discoverable at rest (finding 4): a quiet affordance at the shelf edge that opens
   the existing New Project card — the new-paper door no longer hunted-for inside the inventory. */
.dpp-new{font:10.5px var(--mono);color:var(--accent);background:none;border:1px dashed var(--accent);
  border-radius:999px;padding:2px 11px;cursor:pointer;margin-left:auto}
.dpp-new:hover{color:var(--ink);border-color:var(--accent);background:color-mix(in srgb,var(--accent) 12%,transparent)}
/* the instructive skeleton (belt-and-braces for a slow / degraded serve — the picture
   normally paints in lock-step with the prose from the embedded brief). */
.dpp-tile.is-skel{cursor:default;border-left-color:var(--edge2);pointer-events:none;
  animation:dpp-pulse 1.3s ease-in-out infinite}
.dpp-tile.is-skel .pn{height:12px;width:62%;background:var(--edge2);border-radius:3px}
.dpp-tile.is-skel .pw{height:9px;width:40%;background:var(--edge);border-radius:3px;margin-top:5px}
@keyframes dpp-pulse{0%,100%{opacity:.45}50%{opacity:.8}}
.dash-mat{margin-top:6px}
.dash-mat-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:13px}
.dash-mat-h{font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.1em;color:var(--dim);font-weight:700}
.dash-back{font-family:var(--mono);font-size:10.5px;color:var(--accent);text-decoration:none;border:1px solid var(--edge);
  border-radius:7px;padding:4px 10px;background:var(--bg);cursor:pointer}
.dash-back:hover{border-color:var(--accent);color:var(--ink)}
/* the live inventory — an auto-fit grid at EQUAL heights (finding 3): three live cards no
   longer orphan a third in a two-column grid (a whole empty column beside it), and
   align-items:stretch pins every card to its row's tallest sibling so their bottoms line up. */
.dash-live{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;align-items:stretch}
.card-note{font-size:11px;line-height:1.5;color:var(--dim)}
.card-note b{color:var(--ink)}
.card-ev{display:block;margin-top:5px;font-family:var(--mono);font-size:10px;color:var(--dim)}
.hy-card.is-paper .hy-card-id .caret{margin-left:auto;color:var(--dim);font-size:11px;flex:none;align-self:center;transition:transform .12s ease}
.hy-card.is-open .hy-card-id .caret{transform:rotate(90deg);color:var(--accent)}
.hy-card-facts .fv.fv-wrap{white-space:normal;overflow:visible;text-overflow:clip}
.dash-shelf{margin-top:30px;border-top:1px solid var(--edge);padding-top:16px}
.dash-shelf-h{display:flex;align-items:baseline;gap:9px;margin:0 0 13px}
.dash-shelf-h .sh-t{font-family:var(--mono);font-size:10.5px;text-transform:uppercase;letter-spacing:.14em;color:var(--dim);font-weight:700}
.dash-shelf-h .sh-n{font-family:var(--mono);font-size:10.5px;color:var(--ink2)}
.scaffold-strip{display:flex;flex-wrap:wrap;gap:11px;align-items:stretch}
.scaffold-strip>.hy-card{width:216px}
.scaf-empty{font-size:10.5px;line-height:1.5;color:var(--dim);margin-top:1px}
.hy-newproj .hy-card-name{cursor:pointer;color:var(--accent)}
.np-form{display:flex;flex-direction:column;gap:8px}
/* the input + select wear the shared .hy-input / .hy-select family (finding 6) — declared in
   hymn.css, so the new-project controls read on-family, never the UA's default chrome. */
.np-row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.np-msg{font-family:var(--mono);font-size:10.5px;min-height:1.2em;color:var(--ink2)}
.np-msg.bad{color:var(--bad)}
.np-msg.ok{color:var(--teal)}
.np-form button:disabled{opacity:.5;cursor:default}
.dash-focus-detail{border:1px solid var(--edge2);border-radius:12px;background:var(--panel);padding:16px 18px;
  display:flex;flex-direction:column;gap:13px;margin-top:12px;min-width:0}
.dfd-descent{display:flex;gap:9px;flex-wrap:wrap;padding-top:11px;border-top:1px solid var(--edge)}
.dash-railswitch{display:flex;flex-direction:column;gap:4px}
.dash-railswitch a{font-family:var(--mono);font-size:10.5px;color:var(--ink2);text-decoration:none;padding:2px 0;cursor:pointer;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dash-railswitch a:hover{color:var(--accent)}
.dash-railswitch a.is-here{color:var(--keystone)}
.dash-railcov{font-family:var(--mono);font-size:10px;color:var(--ink2);line-height:1.7}
/* the new-project confirmation TOAST (gap 4) — a page-level mark OUTSIDE .eng-brief, so the
   re-render that repaints the brief + inventory cannot wipe it in the same tick; it fades on
   its own. The confirmation survives the re-render because it does not live inside it. */
.dash-toast{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);z-index:60;
  max-width:min(92vw,560px);border:1px solid var(--teal);border-left:3px solid var(--teal);
  border-radius:11px;background:var(--panel);color:var(--ink);padding:11px 15px;font-size:12.5px;
  line-height:1.5;box-shadow:var(--hy-pop-shadow);display:flex;align-items:baseline;gap:10px;
  opacity:0;transition:opacity .3s ease}
.dash-toast.on{opacity:1}
.dash-toast .dt-h{font-family:var(--mono);font-size:9px;text-transform:uppercase;letter-spacing:.1em;
  color:var(--teal);font-weight:700;flex:none}
/* the fresh card / tile accent (gap 4) — the new paper is scrolled-to and briefly lit so it
   is findable among the inventory, not landing unhighlighted among the rest. */
.hy-card.is-fresh-card,.dpp-tile.is-fresh-tile,.dpp-scaf.is-fresh-tile{border-color:var(--keystone);
  box-shadow:inset 0 0 0 1px var(--keystone);transition:border-color 1.4s ease,box-shadow 1.4s ease}
@media (max-width:640px){ #dash{padding:14px 14px 80px} .dash-live{grid-template-columns:1fr}
  .scaffold-strip>.hy-card{width:100%} }
`;

function injectDashCSS() {
  if (typeof document === "undefined" || document.getElementById("dash-components")) return;
  const st = document.createElement("style"); st.id = "dash-components"; st.textContent = DASH_CSS;
  document.head.appendChild(st);
}

// ── module state (one surface, one model) ───────────────────────────────────────
let STORE = null;
let BRIEF = null;                    // /dashboard/brief payload (the composed whole)
let DATA = null;                     // /dashboard/data payload (the card inventory), lazy
let STATE = createFocusState("index");
let BUS = null, LENS = null, REALLOC = null;
let MAT_OPEN = false;                // is the card inventory materialised?
let COUNTS_PANEL = null;             // null | "orders" | "decisions" — the census chip's in-place list
const SELECTION = {};                // project -> remembered focus (restore-on-reopen, B.3)

// the hover lens must never survive a geometry change (finding 5): descend, close, open,
// scroll and resize all move the shelf out from under a floating lens. One hygiene hook.
function hideLens() { if (LENS) LENS.hide(); }

const cssAttr = (v) => String(v == null ? "" : v).replace(/'/g, "\\'");
let _toastTimer = null;

// the confirmation TOAST (gap 4): a page-level mark appended to #dash (OUTSIDE .eng-brief),
// so paintBrief()'s re-render — which rewrites .eng-brief and #dash-mat — cannot wipe it in
// the same tick the create fires. It carries the composed confirmation and fades on its own.
function showToast(bodyHTML) {
  const host = (typeof document !== "undefined" && document.getElementById("dash")) ||
    (typeof document !== "undefined" && document.body);
  if (!host) return;
  let t = document.getElementById("dash-toast");
  if (!t) { t = document.createElement("div"); t.id = "dash-toast"; t.className = "dash-toast"; host.appendChild(t); }
  t.innerHTML = "<span class='dt-h'>created</span><span class='dt-body'>" + bodyHTML + "</span>";
  if (typeof requestAnimationFrame !== "undefined") requestAnimationFrame(() => t.classList.add("on"));
  else t.classList.add("on");
  if (_toastTimer) clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => {
    t.classList.remove("on");
    setTimeout(() => { if (t.parentNode && !t.classList.contains("on")) t.remove(); }, 400);
  }, 6500);
}

// scroll to the new project's card + its papers-shelf chip and briefly accent both, so a
// fresh paper is findable after the re-render, not lost unhighlighted among the rest (gap 4).
function accentNewCard(name) {
  const card = document.querySelector(".hy-card[data-project='" + cssAttr(name) + "']");
  const shelf = document.querySelector(".dpp-scaf[data-paper='" + cssAttr(name) + "'], .dpp-tile[data-paper='" + cssAttr(name) + "']");
  const target = card || shelf;
  if (target && target.scrollIntoView) target.scrollIntoView({ block: "center", behavior: "smooth" });
  if (card) { card.classList.add("is-fresh-card"); setTimeout(() => card.classList.remove("is-fresh-card"), 2600); }
  if (shelf) { shelf.classList.add("is-fresh-tile"); setTimeout(() => shelf.classList.remove("is-fresh-tile"), 2600); }
}

// ═══════════════ BOOT ═══════════════
export function renderDashboard(store, brief) {
  injectEngineCSS(); injectDashCSS();
  STORE = store; BRIEF = brief;
  BUS = new HighlightBus(document);
  LENS = new HoverLens();
  const root = $("#eng-root");
  if (!root) return;
  REALLOC = new Reallocator(root, STATE, BUS);
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    hideLens();
    // Esc pops one layer, most-focused first: a pinned focus, then the census list, then
    // the materialised inventory. Each close leaves the chip state equal to what is visible.
    if (REALLOC.pinned) REALLOC.close();
    else if (COUNTS_PANEL) closeCountsPanel();
    else if (MAT_OPEN) closeInventory();
  });
  // geometry hygiene: a scroll or resize hides the lens so it never floats over the shelf
  // after a descend/close/open moved the anchor (finding 5).
  window.addEventListener("scroll", hideLens, { passive: true });
  window.addEventListener("resize", hideLens);
  paintBrief();
  // HOT ARRIVAL (B.5, no lobby tax): a selection param lands pre-focused on that project —
  // the brief is skipped as the resting step, never a toll. Cold arrival rests on the brief.
  const hot = store.field("project") || store.field("corpus");
  if (hot) descendInto(hot, { pin: true });
}

// ═══════════════ THE BRIEF — the resting altitude ═══════════════
function paintBrief() {
  const brief = $(".eng-brief"); if (!brief) return;
  MAT_OPEN = false;
  COUNTS_PANEL = null;
  const b = (BRIEF && BRIEF.brief) || {};
  const c = (BRIEF && BRIEF.counts) || {};
  const integrity = (BRIEF && BRIEF.work_order_integrity) || {};
  const residualWhere = (integrity.residuals || []).map((r) =>
    String(r.store || "work-orders") + ":" + String(r.line == null ? "store" : r.line)).join(", ");
  const glance = b.glance || "no project has moved yet.";
  brief.innerHTML =
    "<div class='dash-brief'>" +
      "<p class='dash-prose' data-role='brief-prose'>" + esc(glance) + "</p>" +
      (integrity.cracked
        ? "<div class='dash-integrity' role='status'>WORK-ORDER LEDGER WOUNDED · " +
          esc(integrity.residual_count || (integrity.residuals || []).length) +
          " residual(s) · " + esc(residualWhere) +
          (integrity.residuals_truncated ? " · +" + esc(integrity.residuals_omitted) + " behind " +
            esc(integrity.residual_handle) : "") +
          ". Counts on this surface are lower bounds; repair the named lines before mutation.</div>"
        : "") +
      conseqHTML(b.consequential) +
      "<div class='dash-papers' id='dash-papers'></div>" +
      "<div class='dash-counts'>" +
        countChip("projects", c.projects, "project" + (c.projects === 1 ? "" : "s")) +
        countChip("decisions", c.decisions, "open decision" + (c.decisions === 1 ? "" : "s")) +
        countChip("orders", c.orders, "banked order" + (c.orders === 1 ? "" : "s")) +
      "</div>" +
      "<div class='dash-counts-panel' id='dash-counts-panel'></div>" +
      "<div class='dash-mat' id='dash-mat'></div>" +
    "</div>";
  wireBrief();
  paintPapers();
}

// ── THE PAPERS (the picture at rest): his live work as tiles, scaffolds a quiet edge ──
function stateEdge(p) {
  const s = p.state;
  if (s === "UNDER_CONVERGENCE" || s === "REOPENED") return "edge-live";
  if (s === "RELEASED" || s === "AUTHOR_ACCEPTED" || s === "FINAL_GATES_PASSED") return "edge-ok";
  return "edge-warn";
}
function skeletonPapers() {
  const cell = "<div class='dpp-tile is-skel'><span class='pn'></span><span class='pw'></span></div>";
  return "<div class='dpp-h'>reading the papers…</div><div class='dpp-grid'>" +
    cell + cell + cell + "</div>";
}

async function paintPapers() {
  const host = $("#dash-papers"); if (!host) return;
  // the picture rides the brief (lock-step with the prose — no second fetch on cold load).
  // belt-and-braces: an old / degraded serve without embedded papers shows the instructive
  // skeleton, then reads the inventory once.
  let projects = (BRIEF && BRIEF.papers) || null;
  if (!projects) {
    host.innerHTML = skeletonPapers();
    const data = await ensureData();
    if (!$("#dash-papers")) return;                 // the brief re-rendered while we read
    projects = (data && data.projects) || [];
  }
  if (!projects.length) { host.innerHTML = "<div class='dpp-h'>no papers registered yet</div>"; return; }
  const live = projects.filter((p) => p.live);
  const scaffolds = projects.filter((p) => !p.live);
  const tile = (p) => {
    const pos = (p.verdict && p.verdict.position) || low(p.pipeline_position) || low(p.state) || "";
    const ask = hasDecision(p) ? "<span class='ask'>a decision waits</span>"
      : (p.release_absent ? "<span class='ask'>a recover order is banked</span>" : "");
    return "<div class='dpp-tile " + stateEdge(p) + "' data-paper='" + esc(p.name) + "' tabindex='0' role='button'>" +
      "<span class='pn'>" + esc(p.name) + "</span>" +
      "<span class='pw'>" + esc(pos) + "</span>" + ask + "</div>";
  };
  // the shelf ALWAYS renders (finding 4): scaffolds when present, and the quiet
  // "+ new paper" affordance at its edge — birth discoverable at rest, never hunted-for.
  const shelf =
    "<div class='dpp-shelf'>" +
      (scaffolds.length
        ? "<span class='sh-l'>the shelf · " + scaffolds.length + " seeded</span>" +
          scaffolds.map((p) => "<button type='button' class='dpp-scaf' data-paper='" + esc(p.name) + "'>" +
            esc(p.name) + "</button>").join("")
        : "<span class='sh-l'>the shelf</span>") +
      "<button type='button' class='dpp-new' id='dpp-new'>+ new paper</button>" +
    "</div>";
  host.innerHTML =
    "<div class='dpp-h'>the papers · " + live.length + " live</div>" +
    "<div class='dpp-grid'>" + live.map(tile).join("") + "</div>" +
    shelf;
  $$("#dash-papers [data-paper]").forEach((el) => {
    const p = projects.find((x) => x.name === el.dataset.paper) || {};
    el.addEventListener("mouseenter", () => LENS.show(el,
      "<div class='lens-h'>" + esc(el.dataset.paper) + " — where it stands</div><div>" +
      esc(cardGlance(p)) + "</div>"));
    el.addEventListener("mouseleave", () => LENS.hide());
    activate(el, () => { hideLens(); descendInto(el.dataset.paper, { pin: true }); });
  });
  const nb = $("#dpp-new"); if (nb) activate(nb, () => openNewProject());
}

function conseqHTML(cq) {
  if (!cq) return "";
  const door = cq.href
    ? "<a class='hy-door is-primary' href='" + esc(cq.href) + "' data-role='conseq-door'>" + esc(cq.label || "act") + " ↗</a>"
    : "";
  const descend = "<a class='hy-door' href='/conceptric?corpus=" + enc(cq.name) + "&via=dashboard' data-descent='" + esc(cq.name) + "'>open " + esc(cq.name) + "'s board ↗</a>";
  return "<div class='dash-conseq' data-project='" + esc(cq.name) + "'>" +
    "<div class='dc-h'>the call that matters most now</div>" +
    "<div class='dc-glance'>" + esc(cq.glance) + "</div>" +
    "<div class='dc-doors'>" + door + descend + "</div></div>";
}

// the count chips — EVERY count clicks through to exactly what it counts (finding 3):
// `projects` materialises the inventory; `decisions` and `orders` open their in-place list
// under the chips. A count of zero has nothing to open, so it drops the button shell and
// renders as a plain census word (finding 6: one interactive style, no dead buttons).
function countChip(key, n, label) {
  const num = n == null ? "" : "<span class='dc-n'>" + n + "</span>";
  const inner = num + "<span class='dc-l'>" + esc(label) + "</span>";
  if (!n)   // zero (or null) cannot act — a plain word, never a button that does nothing
    return "<span class='dash-count is-quiet' data-count='" + key + "'>" + inner + "</span>";
  return "<button type='button' class='dash-count' data-count='" + key +
    "' aria-expanded='false'>" + inner + "</button>";
}

function wireBrief() {
  const proj = $("button.dash-count[data-count='projects']");
  if (proj) activate(proj, () => toggleInventory());
  const dec = $("button.dash-count[data-count='decisions']");
  if (dec) activate(dec, () => toggleCountsPanel("decisions"));
  const ord = $("button.dash-count[data-count='orders']");
  if (ord) activate(ord, () => toggleCountsPanel("orders"));
  // the consequential glance's descent door → the project focus (pinned in place, not a jump)
  const cd = $(".dash-conseq [data-descent]");
  if (cd) cd.addEventListener("click", (e) => { e.preventDefault(); descendInto(cd.getAttribute("data-descent"), { pin: true }); });
}

// ── the census lists (decisions / orders): the count opens exactly what it counts, in place ──
function setChipOpen(key, open) {
  $$(".dash-count[data-count='" + key + "']").forEach((c) => {
    c.classList.toggle("is-open", open);
    if (c.tagName === "BUTTON") c.setAttribute("aria-expanded", open ? "true" : "false");
  });
}

function closeCountsPanel() {
  const panel = $("#dash-counts-panel"); if (panel) panel.innerHTML = "";
  if (COUNTS_PANEL) setChipOpen(COUNTS_PANEL, false);
  COUNTS_PANEL = null;
}

function toggleCountsPanel(kind) {
  hideLens();
  if (COUNTS_PANEL === kind) { closeCountsPanel(); return; }
  if (COUNTS_PANEL) setChipOpen(COUNTS_PANEL, false);
  const panel = $("#dash-counts-panel"); if (!panel) return;
  COUNTS_PANEL = kind;
  setChipOpen(kind, true);
  panel.innerHTML = kind === "orders" ? ordersListHTML() : decisionsListHTML();
  if (kind === "decisions") {
    $$("[data-descend]", panel).forEach((btn) =>
      activate(btn, () => { hideLens(); descendInto(btn.getAttribute("data-descend"), { pin: true }); }));
  }
}

function ordersListHTML() {
  const orders = (BRIEF && BRIEF.orders) || [];
  if (!orders.length) return "<div class='dcp-empty'>no banked orders.</div>";
  const rows = orders.map((o) =>
    "<div class='dcp-row'>" +
      "<span class='dcp-proj'>" + esc(o.project) + "</span>" +
      "<span class='dcp-what'>" + esc(o.words) + "</span>" +
      "<a class='hy-door' href='" + esc(o.href) + "'>open in the desk ↗</a>" +
    "</div>").join("");
  return "<div class='dcp-h'>banked orders — named, waiting to run (none run yet)</div>" +
    rows +
    "<div class='dcp-foot'><a class='hy-door is-primary' href='/desk?class=work-orders'>" +
      "open the work-orders cockpit ↗</a></div>";
}

function decisionsListHTML() {
  const decs = (BRIEF && BRIEF.decisions) || [];
  if (!decs.length) return "<div class='dcp-empty'>no open decisions.</div>";
  const rows = decs.map((d) =>
    "<div class='dcp-row'>" +
      "<span class='dcp-proj'>" + esc(d.project) + "</span>" +
      "<span class='dcp-what'>" + esc(d.glance || "a respine waits your ruling") + "</span>" +
      "<button type='button' class='hy-door' data-descend='" + esc(d.project) + "'>rule it →</button>" +
    "</div>").join("");
  return "<div class='dcp-h'>open decisions — your ruling waits</div>" + rows;
}

// birth in ≤2 acts (finding 4): the shelf-edge affordance materialises the inventory (if
// closed) and opens the existing New Project card, focused — the door is never hunted-for.
async function openNewProject() {
  hideLens();
  if (!MAT_OPEN) await openInventory();
  const np = $("#newproj");
  if (!np) return;
  np.classList.add("is-open");
  np.scrollIntoView({ block: "center", behavior: "smooth" });
  const nm = $("#np-name"); if (nm) setTimeout(() => nm.focus(), 80);
}

// ═══════════════ MATERIALISE — the card inventory behind one open ═══════════════
async function toggleInventory() {
  if (MAT_OPEN) { closeInventory(); return; }
  await openInventory();
}

async function ensureData() {
  if (!DATA) DATA = await STORE.fetchJSON("/dashboard/data").catch(() => ({ projects: [] }));
  return DATA;
}

async function openInventory() {
  const mat = $("#dash-mat"); if (!mat) return;
  MAT_OPEN = true;
  setChipOpen("projects", true);
  mat.innerHTML = "<div class='dash-mat-head'><span class='dash-mat-h'>materialising the inventory…</span></div>";
  const data = await ensureData();
  const projects = data.projects || [];
  const live = projects.filter((p) => p.live);
  const scaffolds = projects.filter((p) => !p.live);
  mat.innerHTML =
    "<div class='dash-mat-head'><span class='dash-mat-h'>inventory · " + projects.length + " projects</span>" +
      "<button type='button' class='dash-back' data-role='mat-close'>← back to the brief</button></div>" +
    "<div class='dash-live' id='dash-live'>" + live.map(liveCardHTML).join("") + "</div>" +
    "<section class='dash-shelf'><div class='dash-shelf-h'><span class='sh-t'>scaffolds</span>" +
      "<span class='sh-n'>· " + scaffolds.length + "</span></div>" +
      "<div class='scaffold-strip' id='scaffold-strip'>" + scaffolds.map(scaffoldCardHTML).join("") +
        newProjectHTML() + "</div></section>";
  wireInventory(mat);
}

function closeInventory() {
  const mat = $("#dash-mat"); if (mat) mat.innerHTML = "";
  MAT_OPEN = false;
  setChipOpen("projects", false);
  hideLens();
  BUS.clear();
}

function wireInventory(mat) {
  const close = mat.querySelector("[data-role='mat-close']");
  if (close) activate(close, () => closeInventory());
  $$(".hy-card[data-project]", mat).forEach((el) => wireCard(el));
  wireNewProject(mat);
}

// a card: hover LIGHTS the count chips it sources (its state's home) + reveals its glance in the
// fixed lens (no reflow); click OPENS the project focus (descent into the same object).
function wireCard(el) {
  const name = el.getAttribute("data-project");
  const p = ((DATA && DATA.projects) || []).find((x) => x.name === name) || {};
  el.addEventListener("mouseenter", () => {
    BUS.clear();
    BUS.lit([["count", "projects"]], true);
    if (hasDecision(p)) BUS.lit([["count", "decisions"]], true);
    if (p.orders_n) BUS.lit([["count", "orders"]], true);
    LENS.show(el, "<div class='lens-h'>" + esc(name) + " — where it stands</div><div>" +
      esc(cardGlance(p)) + "</div>");
  });
  el.addEventListener("mouseleave", () => { BUS.clear(); LENS.hide(); });
  activate(el, (e) => {
    if (e && e.target && e.target.closest("a, button, input, select")) return;   // doors act, never toggle
    LENS.hide(); BUS.clear();
    descendInto(name, { pin: true });
  });
}

function hasDecision(p) {
  const g = ((p.verdict || {}).generations) || {};
  return !!g.respine_intent;
}
function cardGlance(p) {
  const bits = [];
  const pos = (p.verdict && p.verdict.position) || low(p.pipeline_position) || low(p.state);
  if (pos) bits.push(pos);
  if (p.rounds_n) bits.push(p.rounds_n + " round" + (p.rounds_n === 1 ? "" : "s"));
  if (hasDecision(p)) bits.push("a RESPINE queued");
  if (p.orders_n) bits.push(p.orders_n + " banked order" + (p.orders_n === 1 ? "" : "s"));
  return bits.join(" · ") || "no run yet";
}

// ═══════════════ DESCEND — the project focus (reallocate) + the cockpit door ═══════════════
// Opening a project REALLOCATES the surface to that project's detail with a named return door
// "back to the brief" and a DESCENT door into its cockpit (/conceptric?via=dashboard). Descent
// materialises ONLY what the focus needs (the project's card body from the read model) — it
// NEVER force-opens the full inventory. So a descent from a tile (or a hot arrival) closes back
// to the RESTING brief, and one from an open inventory card closes back to that same inventory:
// the projects chip's is-open state always equals what is actually visible (finding 1).
async function descendInto(name, opts = {}) {
  hideLens();
  await ensureData();
  const p = ((DATA && DATA.projects) || []).find((x) => x.name === name);
  if (!p) return;
  const title = name + " — the project";
  const destination = "back to the brief — where you were";
  REALLOC.pin(name, {
    title, destination,
    buildRail: (railEl) => buildProjectRail(railEl, p),
    buildFocus: (focusEl) => buildProjectFocus(focusEl, p),
  });
  SELECTION[name] = { pinned: true };
}

function buildProjectRail(railEl, p) {
  const c = (BRIEF && BRIEF.counts) || {};
  const others = ((DATA && DATA.projects) || []).filter((x) => x.live && x.name !== p.name);
  railEl.innerHTML =
    "<div class='eng-railblock'><h5>the brief</h5><div class='dash-railcov'>" +
      (c.live || 0) + " live · " + (c.scaffolds || 0) + " scaffold(s)<br>" +
      (c.decisions || 0) + " open decision(s)<br>" + (c.orders || 0) + " banked order(s)</div></div>" +
    "<div class='eng-railblock'><h5>switch project</h5><div class='dash-railswitch' data-role='switch'>" +
      "<a class='is-here' data-sw='" + esc(p.name) + "'>" + esc(p.name) + "</a>" +
      others.map((x) => "<a data-sw='" + esc(x.name) + "'>" + esc(x.name) + "</a>").join("") +
    "</div></div>";
  $$("[data-role='switch'] a", railEl).forEach((a) => {
    if (a.classList.contains("is-here")) return;
    activate(a, () => descendInto(a.getAttribute("data-sw"), { pin: true }));
  });
}

function buildProjectFocus(focusEl, p) {
  const detail = document.createElement("div");
  detail.className = "dash-focus-detail";
  const cardWrap = document.createElement("div");
  cardWrap.innerHTML = p.live ? liveCardHTML(p) : scaffoldCardHTML(p);
  const cardEl = cardWrap.firstElementChild;
  if (cardEl) { cardEl.classList.add("is-open"); cardEl.classList.remove("is-clickable"); detail.appendChild(cardEl); }
  const descent = document.createElement("div");
  descent.className = "dfd-descent";
  descent.innerHTML =
    "<a class='hy-door is-primary' data-role='descent-door' href='/conceptric?corpus=" + enc(p.name) +
      "&via=dashboard'>descend to the cockpit — " + esc(p.name) + "'s board ↗</a>" +
    (p.artefact_href ? "<a class='hy-door' href='" + esc(p.artefact_href) + "'>open the reader ↗</a>" : "");
  detail.appendChild(descent);
  focusEl.appendChild(detail);
}

// ═══════════════ the card html (truth chips preserved — one producer each) ═══════════════
// Lifted from the pre-W-DASH dashboard, VERBATIM in what it renders (server-authored fields):
// the growth SEEDED chip, the verdict position/generations, the release verdict + recover
// offer. We re-dress geometry (the card now materialises behind the brief), never re-derive.
const revOf = (name) => { const m = /-r(\d+)$/.exec(String(name || "")); return m ? "r" + m[1] : ""; };
function mintChip(art) {
  if (!art || !art.minted_at) return "";
  const rev = revOf(art.name);
  return (rev ? rev + " " : "") + "minted " + day(art.minted_at);
}
function genLine(g) {
  const parts = [];
  if (g.gen) parts.push(g.gen);
  if (g.debt_trajectory && g.debt_trajectory.length) parts.push("debt " + g.debt_trajectory.join("→"));
  return parts.join(" · ");
}
function stateChipClass(state) {
  if (state === "NEVER_RUN") return "is-never";
  if (state === "UNDER_CONVERGENCE" || state === "REOPENED") return "is-live";
  if (state === "RELEASED" || state === "AUTHOR_ACCEPTED" || state === "FINAL_GATES_PASSED") return "is-ok";
  return "is-warn";
}
function doorHTML(cls, href, label, title, extra) {
  return "<a class='hy-door" + (cls ? " " + cls : "") + "'" + (extra || "") +
    " href='" + esc(href) + "' title='" + esc(title || href) + "'>" + esc(label) + " ↗</a>";
}
function deadDoor(label, why) {
  return "<span class='hy-door is-dead' title='" + esc(why) + "'>" + esc(label) + "</span>";
}
const fk = (k, v) => "<span class='fk'>" + esc(k) + "</span><span class='fv'>" + esc(v) + "</span>";
const fkw = (k, v) => "<span class='fk'>" + esc(k) + "</span><span class='fv fv-wrap'>" + esc(v) + "</span>";
function chipRow(chips) {
  if (chips.length <= 3) return "<div class='hy-card-chips'>" + chips.join("") + "</div>";
  return "<div class='hy-card-chips'>" + chips.slice(0, 3).join("") +
    "<span class='hy-chip hy-chip-more' data-more>+" + (chips.length - 3) + "</span>" +
    "<span class='hy-chip-rest' hidden>" + chips.slice(3).join("") + "</span></div>";
}
function primaryDoorHTML(p) {
  const v = p.verdict || {};
  const rs = (v.generations || {}).respine_intent;
  if (rs && rs.href) return doorHTML("is-primary", rs.href, "rule the RESPINE", rs.title || "rule the queued RESPINE");
  const pr = p.primary || {};
  return pr.label ? doorHTML("is-primary", pr.href, pr.label, pr.why)
                  : deadDoor("next move unknown", pr.why || "no derived next move");
}
function liveCardHTML(p) {
  const v = p.verdict || {};
  const g = v.generations || {};
  const art = v.artefact || {};
  const rs = g.respine_intent || null;
  const edge = (p.state === "RELEASED" || p.state === "AUTHOR_ACCEPTED" || p.state === "FINAL_GATES_PASSED") ? "edge-ok"
    : (p.state === "UNDER_CONVERGENCE" || p.state === "REOPENED" || rs) ? "edge-live" : "edge-warn";
  const chips = [];
  if (g.gen) chips.push("<span class='hy-chip is-live'>" + esc(g.gen) + (rs ? " · RESPINE open" : "") + "</span>");
  else { chips.push("<span class='hy-chip " + stateChipClass(p.state) + "'>" + esc(low(v.position || p.state)) + "</span>");
         if (rs) chips.push("<span class='hy-chip is-live'>RESPINE open</span>"); }
  if (p.rounds_n) chips.push("<span class='hy-chip'>" + p.rounds_n + " round" + (p.rounds_n === 1 ? "" : "s") + "</span>");
  const mc = p.release_absent ? "" : mintChip(art);
  if (mc) chips.push("<span class='hy-chip'>" + esc(mc) + "</span>");
  if (p.release_absent && p.recover)
    chips.push("<span class='hy-chip is-warn is-offer' data-fix=\"" + esc(p.recover.reveal) +
      "\" title='reveal the banked recover order + its consume route'>release PDF · absent</span>");
  let facts = fkw("position", v.position || low(p.pipeline_position));
  facts += fk("rounds", String(p.rounds_n || 0));
  const gl = genLine(g);
  if (gl) facts += fkw("generations", gl);
  if (p.release_absent && p.recover) facts += fkw("release", "minted PDF absent — recover order " + p.recover.wo + " banked");
  else if (art.name) facts += fkw("artefact", art.name);
  let doors = primaryDoorHTML(p);
  if (rs && rs.href) {
    const pr = p.primary || {};
    if (pr.href && ["resume", "recover", "advance", "open"].includes(pr.kind)) doors += doorHTML("", pr.href, pr.label, pr.why);
  } else if (p.primary && p.primary.kind === "recover")
    doors += doorHTML("", "/pipeline?project=" + enc(p.name), "resume convergence", "resume convergence");
  if (p.artefact_href)
    doors += doorHTML("", p.artefact_href, "open reader", "/artefact?corpus=" + p.name, " data-door='artefact'");
  let fold;
  if (p.release_absent && p.recover) {
    fold = "<div class='card-note'>The minted release PDF is <b>absent on this box</b>. " +
      "Recover order <b>" + esc(p.recover.wo) + "</b> is banked — the <b>release PDF · absent</b> " +
      "chip reveals its route; it never fires from here.</div>" +
      "<div class='hy-card-doors'>" + deadDoor("release PDF · absent", "no local artefact to open") +
      doorHTML("", "/desk?wo=" + enc(p.recover.wo), "open the recover order", "/desk?wo=" + p.recover.wo) + "</div>";
  } else {
    const ev = (v.position_evidence || []).map((e) => esc(e)).join(" · ");
    fold = "<div class='card-note'>";
    if (rs) fold += "Next move — <b>rule the RESPINE</b>: " + esc(rs.title) + ". ";
    fold += "Position joined server-side by the truth layer (release machine + rounds + generations + finalize)." +
      (ev ? "<span class='card-ev'>" + ev + "</span>" : "") + "</div>";
  }
  return "<div class='hy-card is-paper is-clickable " + edge + "' data-project='" + esc(p.name) + "'>" +
    "<div class='hy-card-id'><span class='hy-card-name'>" + esc(p.name) + "</span>" +
      "<span class='hy-card-kind'>" + esc(p.kind) + "</span>" +
      "<span class='caret' aria-hidden='true'>▸</span></div>" +
    chipRow(chips) +
    (p.release_absent ? "<div class='hy-chip-fix' data-fixbox></div>" : "") +
    "<div class='hy-card-facts'>" + facts + "</div>" +
    "<div class='hy-card-doors'>" + doors + "</div>" +
    "<div class='hy-card-fold'>" + fold + "</div>" +
  "</div>";
}
function scaffoldCardHTML(p) {
  const chips = "<span class='hy-chip is-scaffold'>scaffold" + ((p.growth || {}).state ? " · " + esc(p.growth.state) : "") + "</span>" +
    (p.rounds_n ? "<span class='hy-chip'>" + p.rounds_n + " round" + (p.rounds_n === 1 ? "" : "s") + "</span>" : "");
  return "<div class='hy-card is-muted is-compact is-clickable' data-project='" + esc(p.name) + "'>" +
    "<div class='hy-card-id'><span class='hy-card-name'>" + esc(p.name) + "</span>" +
      "<span class='hy-card-kind'>" + esc(p.kind) + "</span></div>" +
    "<div class='hy-card-chips'>" + chips + "</div>" +
    "<div class='scaf-empty'>no release run yet — first act: " +
      doorHTML("", "/conceptric?project=" + enc(p.name), "seed a conception", "/conceptric?project=" + p.name) +
    "</div>" +
  "</div>";
}

// ═══════════════ the new-project door (J6) — banks a scaffold, SEEDED from birth ═══════════════
function newProjectHTML() {
  return "<div id='newproj' class='hy-card hy-newproj is-compact is-muted'>" +
    "<div class='hy-card-id'><span class='hy-card-name' id='np-open'>+ new project</span></div>" +
    "<div class='hy-card-fold' id='np-fold'><div class='np-form'>" +
      "<input id='np-name' class='hy-input' autocomplete='off' spellcheck='false' placeholder='project-name'>" +
      "<div class='np-row'><select id='np-template' class='hy-select' title='template — conceptric is the one creatable scaffold today'>" +
        "<option value='conceptric'>conceptric</option></select>" +
        "<button id='np-create' type='button' class='hy-door is-primary'>create</button></div>" +
      "<div class='np-msg' id='np-msg' aria-live='polite'></div>" +
    "</div></div></div>";
}
function wireNewProject(mat) {
  const newproj = mat.querySelector("#newproj");
  const open = mat.querySelector("#np-open");
  if (open) open.addEventListener("click", () => newproj.classList.toggle("is-open"));
  const btn = mat.querySelector("#np-create");
  if (!btn) return;
  btn.addEventListener("click", async () => {
    if (btn.disabled) return;
    const name = mat.querySelector("#np-name").value.trim();
    const template = mat.querySelector("#np-template").value;
    const msg = mat.querySelector("#np-msg");
    msg.className = "np-msg"; msg.textContent = "banking scaffold…";
    btn.disabled = true;
    try {
      const res = await STORE.fetchJSON("/dashboard/new", { method: "POST", inject: [], body: { name, template } });
      const woN = (res.work_orders || []).length;
      msg.className = "np-msg ok"; msg.textContent = "created " + res.name + " — " + woN + " work-order(s) banked";
      mat.querySelector("#np-name").value = "";
      // gap 4: the confirmation lives OUTSIDE the re-rendered subtree — a page-level toast —
      // so the re-render below (which rewrites .eng-brief + #dash-mat, wiping #np-msg) never
      // wipes it in the same tick. The ephemeral #np-msg is a courtesy; the toast is the record.
      showToast("<b>" + esc(res.name) + "</b> — " + woN + " work-order(s) banked · a scaffold on the shelf");
      // the new scaffold joins BOTH pictures on refresh, no reload (finding 7): re-read the
      // whole (brief carries the fresh papers + counts + orders), repaint the resting brief so
      // THE PAPERS picture and the chips update, then re-materialise the inventory with the new
      // card. The papers tiles and the inventory grid move in lock-step.
      DATA = null;
      BRIEF = await STORE.fetchJSON("/dashboard/brief").catch(() => BRIEF);
      paintBrief();                                 // refresh the prose + THE PAPERS + the counts
      await openInventory();                        // re-materialise with the new card + refreshed counts
      // gap 4: scroll to + briefly accent the fresh card so it is findable, not lost among the rest.
      accentNewCard(res.name);
    } catch (e) {
      msg.className = "np-msg bad";
      msg.textContent = String((e && e.message) || e).replace(/^fetchJSON.*?→ \d+: /, "");
    } finally {
      const b2 = document.querySelector("#np-create"); if (b2) b2.disabled = false;
    }
  });
}

// chip fold / offer reveal delegation — the +N disclosure and the recover-offer reveal (never fires).
document.addEventListener("click", (e) => {
  const offer = e.target.closest && e.target.closest(".hy-chip.is-offer");
  if (offer) { e.stopPropagation();
    const box = offer.closest(".hy-card").querySelector(".hy-chip-fix");
    const fix = offer.getAttribute("data-fix") || "";
    if (box) { const on = box.classList.contains("is-open") && box.textContent === fix;
      box.textContent = on ? "" : fix; box.classList.toggle("is-open", !on); }
    return; }
  const more = e.target.closest && e.target.closest(".hy-chip-more");
  if (more) { e.stopPropagation();
    const rest = more.parentElement.querySelector(".hy-chip-rest");
    if (rest) rest.hidden = false; more.remove(); }
});

export default { renderDashboard };
