// storyboard-panes.mjs — the storyboard surface's pane logic (W-SB), a SHARED module.
//
// The storyboard in the engine (his ruling 2026-07-22: the storyboard is "the place where I
// can most easily see the thing that's going to be projected"). The surface joins the one
// instrument (engine.mjs). The resting DOM is the composed BRIEF (delta-and-ask: what MOVED
// since he last looked + the one thing that needs him) plus one-line counts — no section
// card, no weighting card, no conveyor exists until a focus materialises it, and closing
// returns to the brief. Materialise on open; hover REVEALS relations (a weighting card lights
// its source nodes); pin REALLOCATES (the examined card claims the centre, siblings to a rail,
// a breadcrumb + a named return door "back to the storyboard brief — where you were"); close
// restores geometry + scroll exactly. Per-card grounding is composed SERVER-SIDE
// (/storyboard/brief → each weighting/section card carries its source nodes + the why); the
// client renders it verbatim and reconstructs nothing. No lobby tax: a deep link
// (?section= / ?card= / ?node=) PRE-PINS its target on load — the brief is the default entry,
// never a toll booth.
//
// The retained one-truth reads stay: the run pane mounts the SHARED run tray (run-tray.mjs)
// over storyboard.launch_roster — the brief composes OVER the same reads, never forking them.
// All network rides store.fetchJSON (the one gateway). All colour is a hymn var().

import store from "/shared/store.mjs";
import { injectEngineCSS, createFocusState, HighlightBus, HoverLens, Reallocator, activate } from "/shared/engine.mjs";
import { mountRunTray } from "/shared/run-tray.mjs";

const esc = (s) => String(s == null ? "" : s)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
const cut = (s, n) => { s = String(s == null ? "" : s); return s.length > n ? s.slice(0, n - 1) + "…" : s; };
// word-boundary truncation: never leave a title cut mid-word at the glance (his board law).
const cutWords = (s, n) => { s = String(s == null ? "" : s); if (s.length <= n) return s;
  return s.slice(0, n).replace(/\s+\S*$/, "").replace(/[ ,;:(-]+$/, "") + "…"; };
const ACTOR = "gerard";              // the plan-write attribution (the endpoint defaults it; we send it explicit)
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const ec = encodeURIComponent;
function cssAttr(v) { return String(v).replace(/["\\]/g, "\\$&"); }

const STORYBOARD_CSS = `
#storyboard-page{max-width:1180px;margin:0 auto;padding:18px 22px 120px}
@media(min-width:1400px){.sb-ctx{max-width:1000px;margin-inline:auto}}
.sb-ctx{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;margin:0 0 4px;padding-bottom:11px;border-bottom:1px solid var(--edge)}
.sb-ctx .sb-surface{font-family:var(--mono);font-size:12px;font-weight:700;color:var(--ink)}
.sb-ctx .sb-purpose{color:var(--ink2);font-size:12.5px}
/* THE BRIEF — the resting altitude: the composed delta-and-ask + counts, nothing else */
.sb-brief-prose{font-size:14px;line-height:1.65;color:var(--ink);margin:18px 0 6px;max-width:76ch}
.sb-brief-prose .sb-next{display:block;margin-top:8px;font-family:var(--mono);font-size:10.5px;color:var(--dim)}
.sb-counts{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0 6px}
.sb-count{display:inline-flex;align-items:center;gap:7px;cursor:pointer;background:var(--panel);border:1px solid var(--edge2);
  border-radius:9px;padding:8px 12px;font:inherit;color:var(--ink2);min-width:0}
.sb-count:hover{border-color:var(--accent);color:var(--ink)}
.sb-count:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.sb-count.is-open{border-color:var(--keystone);color:var(--ink);box-shadow:inset 0 0 0 1px var(--keystone)}
.sb-count .sb-cn{font-family:var(--mono);font-weight:700;color:var(--ink);font-size:14px}
.sb-count .sb-clabel{font-size:11.5px}
.sb-count.is-warn .sb-cn{color:var(--warn)}
.sb-count.is-empty{opacity:.6;cursor:default}
/* ═══ THE BOARD — the whole storyboard, seeable at rest (his correction, 2026-07-22:
   the resting-state law was never absence-of-the-object; the inventory is dead, the
   PICTURE is the working altitude's true form). Sections ride one spatial row in paper
   order, each tile's WIDTH carrying its stock weight, its edge carrying its freshness;
   appendices sit beneath as a quieter shelf; the contribution rank runs under the board
   and hovering a claim LIGHTS the sections its nodes land in — the relation shown
   spatially, never described in a bubble. Hover a tile reveals its job; opening pins. ═══ */
.sbb{border:1px solid var(--edge2);border-radius:14px;background:var(--panel);padding:16px 18px 14px;margin:16px 0 4px}
.sbb-h{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:12px}
.sbb-title{font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.12em;color:var(--dim);font-weight:700}
.sbb-legend{font-family:var(--mono);font-size:9.5px;color:var(--dim);margin-left:auto}
.sbb-legend .w{color:var(--warn)}
.sbb-row{display:flex;gap:8px;align-items:stretch;flex-wrap:wrap}
.sbb-row.is-appendix{margin-top:8px;padding-top:8px;border-top:1px dashed var(--edge)}
/* the board is a DISCIPLINED grid, not a masonry tag-cloud: every main tile shares one
   height, its width carries stock weight through a BOUNDED flex-grow (1..4, set per-tile)
   clamped between a title-safe floor and a row-safe ceiling — so no tile collapses below
   its title (the min-width) and none swallows a row (the max-width; ≥4 fit a row). The
   precise weight is carried by the INNER bar; width is the coarse, bounded echo of it. */
.sbb-sec{position:relative;flex:1 1 0;min-width:148px;max-width:320px;display:flex;flex-direction:column;gap:6px;
  border:1px solid var(--edge2);border-radius:9px;background:var(--panel2);padding:9px 11px 8px;
  cursor:pointer;min-height:80px;overflow:hidden}
.sbb-sec:hover{border-color:var(--accent)}
.sbb-sec:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.sbb-sec.is-stale{border-top:2px solid var(--warn)}
.sbb-sec.lit{box-shadow:inset 0 0 0 1px var(--warn);background:color-mix(in srgb,var(--warn) 10%,transparent)}
/* the title clamps to two lines and breaks only at WORD boundaries (no mid-word cut at
   rest); the server word-truncates a pathologically long title, so the clamp is a floor
   not the truncator. Full title rides the tile's title= tooltip. */
.sbb-sec .st{font-size:11.5px;font-weight:640;color:var(--ink);line-height:1.32;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;
  overflow-wrap:break-word;word-break:normal;hyphens:none}
/* the section id chip (finding 1, stranger-walk 2026-07-23): every board tile visibly
   carries its section id — the id is how the author and the engine name sections to each
   other, so the board is navigable BY NAME (visual position 8 is NOT section s8). A small
   mono chip, self-sized to its id so it never stretches the tile. */
.sbb-sec .sbb-sid{align-self:flex-start;font-family:var(--mono);font-size:8.5px;font-weight:700;
  letter-spacing:.02em;color:var(--dim);background:var(--bg);border:1px solid var(--edge2);
  border-radius:4px;padding:1px 5px;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sbb-sec.is-appendix .sbb-sid{font-size:8px;padding:0 4px}
.sbb-sec.lit .sbb-sid{border-color:var(--warn);color:var(--ink)}
.sbb-sec .sw{margin-top:auto;display:flex;align-items:center;gap:6px}
.sbb-sec .sw .bar{height:4px;border-radius:999px;background:var(--accent);opacity:.75;min-width:3px}
.sbb-sec .sw .n{font-family:var(--mono);font-size:8.5px;color:var(--dim);white-space:nowrap}
.sbb-sec.is-appendix{min-height:56px;background:var(--panel);opacity:.85}
.sbb-sec.is-appendix .st{font-size:10.5px;-webkit-line-clamp:1}
/* the rank strip — the authored weighting under the board; hover lights its landings */
.sbb-rank{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px;padding-top:11px;border-top:1px solid var(--edge)}
.sbb-claim{display:inline-flex;align-items:baseline;gap:7px;max-width:100%;border:1px solid var(--edge2);
  border-radius:999px;background:var(--bg);padding:3px 11px;cursor:pointer;min-width:0}
.sbb-claim:hover{border-color:var(--teal)}
.sbb-claim:focus-visible{outline:2px solid var(--teal);outline-offset:2px}
.sbb-claim .rk{font-family:var(--mono);font-size:10px;font-weight:700;color:var(--teal);flex:none}
.sbb-claim.is-excluded .rk{color:var(--dim)}
.sbb-claim.is-excluded{opacity:.7}
.sbb-claim .cl{font-size:10.5px;color:var(--ink2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sbb-none{font-size:12px;color:var(--dim);font-style:italic;padding:6px 0}
/* the one ASK — a single decision, clickable to summon its count */
.sb-decision{margin:12px 0 4px;padding:11px 13px;border:1px solid var(--keystone);border-left:3px solid var(--keystone);
  border-radius:10px;background:color-mix(in srgb,var(--keystone) 6%,transparent);cursor:pointer;max-width:76ch}
.sb-decision:hover{background:color-mix(in srgb,var(--keystone) 11%,transparent)}
.sb-decision .sb-dh{font-family:var(--mono);font-size:9px;text-transform:uppercase;letter-spacing:.09em;color:var(--keystone);font-weight:700;margin-bottom:4px}
.sb-decision .sb-dg{font-size:12.5px;line-height:1.55;color:var(--ink)}
.sb-doors{display:flex;gap:9px;flex-wrap:wrap;margin-top:10px}
.sb-door{font-family:var(--mono);font-size:10.5px;color:var(--accent);text-decoration:none;border:1px solid var(--edge);
  border-radius:7px;padding:4px 10px;background:var(--bg);cursor:pointer}
.sb-door:hover{border-color:var(--accent);color:var(--ink)}
/* the materialised zone — built on open, removed on close (never present at rest) */
.sb-mat{margin-top:16px}
.sb-mat-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:11px}
.sb-mat-h{font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.1em;color:var(--dim);font-weight:700}
.sb-cards{display:flex;flex-direction:column;gap:10px;max-width:860px}
.sb-card{border:1px solid var(--edge2);border-radius:10px;background:var(--panel);padding:12px 14px;
  display:flex;flex-direction:column;gap:7px;cursor:pointer}
.sb-card:hover{border-color:var(--accent)}
.sb-card.is-weighting{border-left:3px solid var(--teal)}
.sb-card.is-excluded{opacity:.75;border-left-color:var(--dim)}
.sb-card.is-stale{border-left:3px solid var(--warn)}
.sb-card .sb-ctitle{font-size:13px;font-weight:640;color:var(--ink);display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.sb-card .sb-crank{font-family:var(--mono);font-size:11px;font-weight:700;color:var(--teal)}
.sb-card .sb-cwhy{font-size:12px;line-height:1.55;color:var(--ink2)}
.sb-card .sb-cmeta{font-family:var(--mono);font-size:9.5px;color:var(--dim);display:flex;gap:9px;flex-wrap:wrap}
.sb-card .sb-cmeta .warn{color:var(--warn)}
.sb-card .sb-open{font-family:var(--mono);font-size:9px;color:var(--dim);border-top:1px dashed var(--edge2);padding-top:7px}
.sb-tag{font-family:var(--mono);font-size:8px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;
  color:var(--dim);border:1px dashed var(--dim);border-radius:5px;padding:1px 6px}
/* the GROUNDING block — source nodes (working doors) + the why, rendered in place */
.sb-ground{display:flex;flex-direction:column;gap:6px;border:1px solid var(--edge);border-radius:9px;background:var(--bg);padding:10px 12px}
.sb-ground-h{font-family:var(--mono);font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:var(--dim);font-weight:700}
.sb-ground-why{font-size:12.5px;line-height:1.6;color:var(--ink)}
.sb-gnodes{display:flex;flex-wrap:wrap;gap:6px}
.sb-gnode{display:inline-flex;align-items:center;gap:6px;font-family:var(--mono);font-size:10px;color:var(--ink2);
  background:var(--panel);border:1px solid var(--edge);border-left:3px solid var(--teal);border-radius:6px;padding:3px 8px;
  text-decoration:none;cursor:pointer;max-width:100%}
.sb-gnode:hover{border-color:var(--accent);color:var(--ink)}
.sb-gnode .gk{font-size:8px;text-transform:uppercase;color:var(--dim)}
.sb-gnode.lit{box-shadow:inset 0 0 0 1px var(--warn);background:color-mix(in srgb,var(--warn) 12%,transparent)}
.sb-gnone{font-size:10.5px;color:var(--dim);font-style:italic}
/* the reallocated FOCUS — the examined card claims the centre */
.sb-focus-pane{border:1px solid var(--keystone);border-radius:14px;background:var(--panel);overflow:hidden}
.sb-focus-head{padding:12px 16px;border-bottom:1px solid var(--edge);background:linear-gradient(180deg,color-mix(in srgb,var(--keystone) 10%,transparent),transparent)}
.sb-focus-kind{font-family:var(--mono);font-size:10px;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:var(--keystone)}
.sb-focus-title{font-size:14.5px;font-weight:680;color:var(--ink);margin-top:4px}
.sb-focus-body{padding:15px 16px;display:flex;flex-direction:column;gap:14px}
.sb-focus-doors{display:flex;gap:9px;flex-wrap:wrap}
.sb-beats{display:flex;flex-wrap:wrap;gap:6px}
.sb-beat{font-family:var(--mono);font-size:10px;color:var(--ink2);background:var(--bg);border:1px solid var(--edge);
  border-left:3px solid var(--keystone);border-radius:6px;padding:3px 8px}
.sb-railcov{font-family:var(--mono);font-size:10px;color:var(--ink2);line-height:1.7}
.sb-railcov .z{color:var(--warn)}
.sb-rail-list{display:flex;flex-direction:column;gap:5px}
.sb-rail-sec{font-size:10.5px;color:var(--ink2);cursor:pointer;padding:3px 6px;border-radius:6px;border:1px solid transparent}
.sb-rail-sec:hover{border-color:var(--edge2);color:var(--ink)}
.sb-rail-sec.is-here{color:var(--keystone);font-weight:640}
#sb-status{margin-top:14px;font-family:var(--mono);font-size:10px;color:var(--dim);min-height:14px}
/* the action row (P3) — the section's editing acts, each firing its existing /storyboard/plan
   endpoint: reorder (cheap), retitle (cheap), edit-job (expensive), retire a pinned node
   (residue). Every act says what it WRITES before firing; re-renders from server truth. */
.sb-actions{border:1px solid var(--edge2);border-radius:12px;background:var(--panel);padding:13px 15px;
  display:flex;flex-direction:column;gap:12px;margin-top:2px}
.sb-actions-h{font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.1em;color:var(--dim);font-weight:700}
.sb-act{display:flex;flex-direction:column;gap:6px;padding-bottom:11px;border-bottom:1px dashed var(--edge2)}
.sb-act:last-of-type{border-bottom:none;padding-bottom:0}
.sb-act-will{font-family:var(--mono);font-size:9.5px;color:var(--dim);line-height:1.55}
.sb-act-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.sb-act-btn{font-family:var(--mono);font-size:10.5px;color:var(--accent);background:var(--bg);border:1px solid var(--accent);
  border-radius:8px;padding:5px 11px;cursor:pointer}
.sb-act-btn:hover{background:var(--panel2);color:var(--ink)}
.sb-act-btn:disabled{opacity:.4;cursor:not-allowed;border-color:var(--edge2);color:var(--dim)}
.sb-act-btn:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.sb-act-btn.is-danger{color:var(--warn);border-color:var(--warn)}
.sb-act-field{flex:1;min-width:180px;font:12px var(--mono);color:var(--ink);background:var(--bg);
  border:1px solid var(--edge2);border-radius:7px;padding:6px 9px}
.sb-act-field:focus{outline:2px solid var(--accent);outline-offset:1px}
#sb-act-status,#sb-struct-status{font-family:var(--mono);font-size:10px;min-height:13px;color:var(--dim)}
#sb-act-status.is-bad,#sb-struct-status.is-bad{color:var(--warn)}
#sb-act-status.is-ok,#sb-struct-status.is-ok{color:var(--teal)}
/* the structure door group — plan-wide re-shapes, surfaced in the pinned focus */
.sb-structure{border-color:var(--keystone)}
.sb-structure .sb-actions-h{color:var(--keystone)}
.sb-struct-cost{font-family:var(--mono);font-size:8px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;
  border-radius:5px;padding:1px 6px;margin-left:6px;border:1px dashed var(--dim);color:var(--dim)}
.sb-struct-cost.is-cheap{color:var(--teal);border-color:var(--teal)}
.sb-struct-cost.is-exp{color:var(--warn);border-color:var(--warn)}
/* the edit-job field is PROSE (a section's reason to exist) — a textarea sized to the prose,
   never a single line pretending paragraph-scale copy fits on one row. */
textarea.sb-act-field{min-height:64px;resize:vertical;line-height:1.5;width:100%;box-sizing:border-box}
/* the arc composer — the restructure door's editable ordering (his arc, not the identity).
   The fetched arc rendered as a reorderable + renamable section list; the dry-run re-reads
   HIS edited arc; apply arms before it overwrites. Every colour a hymn var. */
.sb-arc-composer{display:flex;flex-direction:column;gap:6px;margin-top:9px;padding:10px 11px;
  border:1px solid var(--edge2);border-radius:9px;background:var(--bg)}
.sb-arc-h{font-family:var(--mono);font-size:9px;text-transform:uppercase;letter-spacing:.06em;color:var(--dim);line-height:1.5}
.sb-arc-row{display:flex;align-items:center;gap:7px}
.sb-arc-rank{font-family:var(--mono);font-size:9.5px;color:var(--dim);min-width:20px}
.sb-arc-title{flex:1;min-width:120px;font:12px var(--mono);color:var(--ink);background:var(--panel);
  border:1px solid var(--edge2);border-radius:6px;padding:4px 8px}
.sb-arc-title:focus{outline:2px solid var(--accent);outline-offset:1px}
.sb-arc-mv{font-family:var(--mono);font-size:11px;color:var(--accent);background:var(--panel);
  border:1px solid var(--edge2);border-radius:6px;padding:3px 9px;cursor:pointer}
.sb-arc-mv:hover:not(:disabled){border-color:var(--accent);color:var(--ink)}
.sb-arc-mv:disabled{opacity:.35;cursor:not-allowed}
.sb-arc-mv:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.sb-arc-moved{font-family:var(--mono);font-size:9.5px;color:var(--accent);margin-top:2px}
`;

function injectStoryboardCSS() {
  if (typeof document === "undefined" || document.getElementById("sb-components")) return;
  const st = document.createElement("style"); st.id = "sb-components"; st.textContent = STORYBOARD_CSS;
  document.head.appendChild(st);
}

// ── module state ────────────────────────────────────────────────────────────────
let CORPUS = null;
let BRIEF = null;                     // the composed brief payload (server-minted)
let STATE = createFocusState("brief");
let BUS = null, LENS = null, REALLOC = null;
let OPEN_MAT = null;                  // the materialised chip kind, or null (brief base altitude)
const CACHE = {};

// ═══════════════ BOOT ═══════════════
export async function initStoryboard() {
  injectEngineCSS(); injectStoryboardCSS();
  BUS = new HighlightBus(document);
  LENS = new HoverLens();
  window.__hymnOpenNode = (id) => openNodeFocus(id);   // shell node-search focuses in-board
  if (!store.field("corpus")) {
    try {
      const list = await store.fetchJSON("/corpus/list", { inject: [] });
      const cp = list.default || (list.corpora || [])[0];
      if (cp) store.set({ corpus: cp }, { replace: true });
    } catch (_e) { /* handled by load's declared empty state */ }
  }
  CORPUS = store.field("corpus");
  const root = $("#eng-root");
  REALLOC = new Reallocator(root, STATE, BUS);
  store.subscribe((s) => {
    const c = s.selection.corpus;
    if (c && c !== CORPUS) { CORPUS = c; STATE = createFocusState("brief"); REALLOC.state = STATE; load().then(entryFromParams); return; }
    const n = s.selection.node;
    if (n) openNodeFocus(n, { fromStore: true });
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") { if (REALLOC.pinned) closePin(); else closeMaterialised(); } });
  await load();
  entryFromParams();                  // No lobby tax: a deep link pre-pins its target
}
if (typeof window !== "undefined") window.__storyboardInit = initStoryboard;

async function load() {
  CORPUS = store.field("corpus");
  BRIEF = await store.fetchJSON("/storyboard/brief").catch(() => null);
  renderBrief();
}

// ═══════════════ THE BRIEF — the resting altitude: the BOARD, captioned ═══════════════
// His correction (2026-07-22, verbatim law): "You've killed any sense of being able to
// see the whole storyboard." The resting state is the WHOLE, seeable as a designed
// picture — the board — with the composed prose as its caption. Detail still materialises;
// the picture never hides.
function renderBrief() {
  const brief = $(".eng-brief"); if (!brief) return;
  OPEN_MAT = null;
  if (!BRIEF) { brief.innerHTML = "<div class='sb-brief-prose'>no plan resolved for this project.</div>"; return; }
  const g = (BRIEF.brief && BRIEF.brief.glance) || "";
  const nxt = (BRIEF.brief && BRIEF.brief.next) || "";
  const c = BRIEF.counts || {};
  const dec = BRIEF.decision;
  brief.innerHTML =
    "<div class='sb-brief-prose' data-role='brief-prose'>" + esc(g) +
      (nxt ? "<span class='sb-next'>" + esc(nxt) + "</span>" : "") + "</div>" +
    // the accented ask-card is reserved for HIS genuine decisions; a machine-owed item
    // (decision.his === false) is a quiet information line, never a false summons.
    (dec ? (dec.his === false
        ? "<div class='sb-brief-prose' style='font-size:12px;margin:2px 0 4px;color:var(--ink2)'>" +
            esc(dec.glance || "") + "</div>"
        : "<div class='sb-decision' data-summon='" + esc(dec.summon || "") + "' tabindex='0' role='button'>" +
            "<div class='sb-dh'>the one thing that needs you</div>" +
            "<div class='sb-dg'>" + esc(dec.glance || "") + "</div></div>") : "") +
    boardHTML() +
    "<div class='sb-counts'>" +
      countChip("findings", c.findings, "prose without stock", c.findings ? "is-warn" : "") +
      countChip("run", null, "run · " + esc(BRIEF.run_label || "—"), "") +
    "</div>" +
    "<div class='sb-doors'>" +
      "<a class='sb-door' href='/artefact?corpus=" + ec(CORPUS) + "'>read the compiled paper →</a>" +
      "<a class='sb-door' href='/conceptric?corpus=" + ec(CORPUS) + "'>the stock it draws from →</a>" +
    "</div>" +
    "<div class='sb-mat' id='sb-mat'></div>";
  wireBrief();
  wireBoard();
}

// ── THE BOARD (the picture at rest) ─────────────────────────────────────────────
// One spatial row in paper order: each tile's flex WIDTH carries its stock weight
// (the paper leans where the tiles are wide), an amber top edge carries prose-stale,
// appendices shelve beneath at lower weight. The contribution rank runs under the
// board; hovering a claim LIGHTS the sections its nodes land in — the relation is
// shown on the board itself, spatially, never narrated in a bubble.
function boardHTML() {
  const cards = (BRIEF && BRIEF.cards) || [];
  if (!cards.length) return "<div class='sbb'><div class='sbb-none'>this plan has no sections yet — the board appears when the spine does.</div></div>";
  const main = cards.filter((s) => !s.appendix);
  const apps = cards.filter((s) => s.appendix);
  const maxN = Math.max(1, ...cards.map((s) => s.n_nodes || 0));
  const anyStale = cards.some((s) => s.dirty);
  const tile = (s) => {
    // width carries stock weight as a BOUNDED echo: flex-grow maps the node count into
    // [1,4] (a ~4x span, not the raw 0..14 that made 58px→full-row chaos), then min/max
    // width clamps it so no tile collapses below its title or swallows a row. The precise
    // weight lives in the inner bar below. The full title rides the title= tooltip; the
    // visible title is word-truncated so the two-line clamp never cuts mid-word.
    const grow = (1 + 3 * ((s.n_nodes || 0) / maxN)).toFixed(2);
    const full = s.title || s.id;
    return "<div class='sbb-sec" + (s.dirty ? " is-stale" : "") + (s.appendix ? " is-appendix" : "") +
      "' data-sec='" + esc(s.id) + "' tabindex='0' role='button'" +
      " title='" + esc(full) + "' style='flex-grow:" + grow + "'>" +
      "<span class='sbb-sid'>" + esc(s.id) + "</span>" +
      "<span class='st'>" + esc(cutWords(full, 68)) + "</span>" +
      "<span class='sw'><span class='bar' style='width:" + Math.round(100 * (s.n_nodes || 0) / maxN) + "%'></span>" +
        "<span class='n'>" + (s.n_nodes || 0) + "</span></span>" +
    "</div>";
  };
  const rank = (BRIEF && BRIEF.weighting) || [];
  // the strip renders the server-composed `display` line (handle prefix masked, shouting
  // sentence-cased at the mint); the raw `claim` stays behind the open (audit depth).
  const claim = (w) =>
    "<button type='button' class='sbb-claim" + (w.excluded ? " is-excluded" : "") + "' data-claim='" + esc(w.id) + "'>" +
      "<span class='rk'>" + (w.excluded ? "not claimed" : "#" + (w.rank != null ? w.rank : "?")) + "</span>" +
      "<span class='cl'>" + esc(cut(w.display || w.claim || "", 72)) + "</span></button>";
  return "<div class='sbb'>" +
    "<div class='sbb-h'><span class='sbb-title'>the board · " + cards.length + " sections in paper order</span>" +
      "<span class='sbb-legend'>width — the stock it pins" + (anyStale ? " · <span class='w'>amber top — prose stale</span>" : "") + "</span></div>" +
    "<div class='sbb-row'>" + main.map(tile).join("") + "</div>" +
    (apps.length ? "<div class='sbb-row is-appendix'>" + apps.map(tile).join("") + "</div>" : "") +
    (rank.length ? "<div class='sbb-rank'>" + rank.map(claim).join("") + "</div>" : "") +
  "</div>";
}

function wireBoard() {
  const cards = (BRIEF && BRIEF.cards) || [];
  $$(".sbb-sec[data-sec]").forEach((el) => {
    const row = cards.find((s) => s.id === el.dataset.sec) || {};
    // hover REVEALS the section's job — the lens, geometrically stable
    el.addEventListener("mouseenter", () => LENS.show(el,
      "<div class='lens-h'>" + esc(row.title || row.id) + " — its job</div>" +
      "<div>" + esc(row.why || "no job set yet.") + "</div>" +
      "<div class='lens-rel'>" + (row.n_nodes || 0) + " node(s) · " + (row.n_beats || 0) + " beat(s) · " +
        (row.dirty ? "<b>prose stale</b>" : "prose in sync") + "</div>"));
    el.addEventListener("mouseleave", () => LENS.hide());
    // opening pins the section IN SITU — the tile is where the section lives
    activate(el, () => { LENS.hide(); pinSection(el.dataset.sec); });
  });
  const rank = (BRIEF && BRIEF.weighting) || [];
  const secTitle = (id) => { const c = cards.find((s) => s.id === id); return (c && c.title) || id; };
  $$(".sbb-claim[data-claim]").forEach((el) => {
    const row = rank.find((w) => w.id === el.dataset.claim) || {};
    const secs = [...new Set((row.nodes || []).map((n) => n.section).filter(Boolean))];
    el.addEventListener("mouseenter", () => {
      BUS.lit(secs.map((s) => ["sec", s]), true);           // the claim's landings, lit on the board
      LENS.show(el, "<div class='lens-h'>" + (row.excluded ? "deliberately not claimed" : "claim #" + (row.rank != null ? row.rank : "?")) +
        "</div><div>" + esc(row.why || row.claim || "") + "</div>" +
        (secs.length ? "<div class='lens-rel'>lands in <b>" + secs.map((s) => esc(secTitle(s))).join(" · ") + "</b> — lit on the board</div>"
          : "<div class='lens-rel'>no board landing is resolved for this claim yet</div>"));
    });
    el.addEventListener("mouseleave", () => { BUS.clear(); LENS.hide(); });
    activate(el, () => { LENS.hide(); BUS.clear(); pinWeighting(el.dataset.claim); });
  });
}

function countChip(kind, n, label, cls) {
  const num = n == null ? "" : "<span class='sb-cn'>" + n + "</span>";
  return "<button type='button' class='sb-count " + cls + "' data-materialize='" + kind + "' " +
    (cls.indexOf("is-empty") >= 0 ? "aria-disabled='true' " : "") + ">" + num +
    "<span class='sb-clabel'>" + esc(label) + "</span></button>";
}

function wireBrief() {
  $$(".sb-count[data-materialize]").forEach((chip) => {
    if (chip.classList.contains("is-empty")) return;
    activate(chip, () => materialise(chip.dataset.materialize));
  });
  const dec = $(".sb-decision[data-summon]");
  if (dec && dec.dataset.summon) activate(dec, () => materialise(dec.dataset.summon));
}

// ═══════════════ MATERIALISE — build the object-set on open ═══════════════
async function materialise(kind) {
  const mat = $("#sb-mat"); if (!mat) return mat;
  if (OPEN_MAT === kind) { closeMaterialised(); return; }
  OPEN_MAT = kind;
  $$(".sb-count").forEach((c) => c.classList.toggle("is-open", c.dataset.materialize === kind));
  BUS.clear();
  mat.innerHTML = "<div class='sb-mat-head'><span class='sb-mat-h'>materialising " + esc(kind) + "…</span></div>";
  if (kind === "sections") return matSections(mat);
  if (kind === "weighting") return renderRank(mat);
  if (kind === "findings") return matFindings(mat);
  if (kind === "run") return matRun(mat);
}
function closeMaterialised() {
  const mat = $("#sb-mat"); if (mat) mat.innerHTML = "";
  OPEN_MAT = null;
  $$(".sb-count").forEach((c) => c.classList.remove("is-open"));
  BUS.clear();
}
function matHead(title) {
  return "<div class='sb-mat-head'><span class='sb-mat-h'>" + esc(title) + "</span>" +
    "<button type='button' class='sb-door' data-role='mat-close'>← back to the brief</button></div>";
}
function wireMatClose(mat) { const b = mat.querySelector("[data-role='mat-close']"); if (b) activate(b, () => closeMaterialised()); }

// ── SECTIONS — the plan's section cards, grounded (source nodes + the why) ────────
function matSections(mat) {
  const cards = (BRIEF && BRIEF.cards) || [];
  mat.innerHTML = matHead("sections · " + cards.length) +
    "<div class='sb-cards'>" + (cards.length ? cards.map(sectionCardHTML).join("")
      : "<div class='sb-brief-prose'>this plan has no sections yet.</div>") + "</div>";
  wireMatClose(mat);
  $$(".sb-card[data-section]", mat).forEach((card) => {
    const row = cards.find((s) => s.id === card.dataset.section) || {};
    card.addEventListener("mouseenter", () => LENS.show(card,
      "<div class='lens-h'>" + esc(row.title || row.id) + " — its job</div><div>" + esc(row.why || "") + "</div>"));
    card.addEventListener("mouseleave", () => LENS.hide());
    activate(card, () => { LENS.hide(); pinSection(card.dataset.section); });
  });
}
function sectionCardHTML(s) {
  const meta = [(s.n_nodes || 0) + " node" + (s.n_nodes === 1 ? "" : "s"),
    (s.n_beats || 0) + " beat" + (s.n_beats === 1 ? "" : "s"),
    (s.dirty ? "<span class='warn'>prose stale</span>" : "in sync")]
    .concat(s.appendix ? ["appendix"] : []);
  return "<div class='sb-card" + (s.dirty ? " is-stale" : "") + "' data-section='" + esc(s.id) + "' tabindex='0' role='button'>" +
    "<div class='sb-ctitle'>" + esc(s.title || s.id) + "</div>" +
    "<div class='sb-cwhy'>" + esc(s.why || "") + "</div>" +
    "<div class='sb-cmeta'>" + meta.join(" · ") + "</div>" +
    "<div class='sb-open'>open → the section claims the centre: its beats, its stock, its doors</div></div>";
}

// ── THE WEIGHTING — the authored contribution rank, GROUNDED per card. The function is
// named renderRank BY CONTRACT (cards-expand-in-place-with-context): opening a weighting
// card REALLOCATES around the examined point (pinWeighting) — it never context-jumps
// (no openNode / no revealSection here). Each card carries its source nodes + the why,
// composed server-side and rendered in place. ─────────────────────────────────────────
function renderRank(mat) {
  const rows = (BRIEF && BRIEF.weighting) || [];
  mat.innerHTML = matHead("narrative weighting · " + rows.length + " · the authored contribution rank") +
    "<div class='sb-brief-prose' style='font-size:12px;margin:0 0 8px'>Ranked by how much the paper leans on each claim. " +
      "#1 is the primary defended contribution; the derived steps below it are the load path; " +
      "excluded items are deliberately NOT claimed — the honesty contract. Open a card to see, in place, " +
      "the nodes it draws from and why.</div>" +
    "<div class='sb-cards'>" + (rows.length ? rows.map(weightingCardHTML).join("")
      : "<div class='sb-brief-prose'>this plan carries no contribution rank yet.</div>") + "</div>";
  wireMatClose(mat);
  $$(".sb-card[data-card]", mat).forEach((card) => {
    const row = rows.find((w) => w.id === card.dataset.card) || {};
    // hover REVEALS: light this card's source nodes across the pane (the bus, never a jump).
    card.addEventListener("mouseenter", () => {
      BUS.lit((row.nodes || []).map((n) => ["gnode", n.id]), true);
      LENS.show(card, "<div class='lens-h'>grounding</div><div>" + esc(row.why || "") + "</div>");
    });
    card.addEventListener("mouseleave", () => { BUS.clear(); LENS.hide(); });
    activate(card, () => { LENS.hide(); BUS.clear(); pinWeighting(card.dataset.card); });
  });
}
function weightingCardHTML(w) {
  const title = w.excluded ? "excluded" : ("#" + (w.rank != null ? w.rank : "?"));
  return "<div class='sb-card is-weighting" + (w.excluded ? " is-excluded" : "") + "' data-card='" + esc(w.id) + "' tabindex='0' role='button'>" +
    "<div class='sb-ctitle'><span class='sb-crank'>" + esc(title) + "</span>" +
      (w.role ? "<span class='sb-tag'>" + esc(w.role) + "</span>" : "") + "</div>" +
    "<div class='sb-cwhy'>" + esc(w.claim || "") + "</div>" +
    groundBlock(w) +
    "<div class='sb-open'>open → this claim claims the centre, its grounding beside it</div></div>";
}

// the GROUNDING block, rendered IN PLACE on every weighting card (the visible floor):
// the why + the source nodes as working doors (label = term; never a raw id above the fold).
function groundBlock(w) {
  const nodes = w.nodes || [];
  const doors = nodes.length
    ? "<div class='sb-gnodes'>" + nodes.map(gnodeHTML).join("") + "</div>"
    : "<div class='sb-gnone'>this claim names no pinned node yet.</div>";
  return "<div class='sb-ground'>" +
    "<div class='sb-ground-h'>grounding · the nodes it draws from</div>" +
    "<div class='sb-ground-why'>" + esc(w.why || "") + "</div>" + doors + "</div>";
}
function gnodeHTML(n) {
  const kind = n.kind ? "<span class='gk'>" + esc(n.kind) + "</span>" : "";
  return "<a class='sb-gnode' data-gnode='" + esc(n.id) + "' href='/conceptric?corpus=" + ec(CORPUS) +
    "&node=" + ec(n.id) + (n.section ? "&section=" + ec(n.section) : "") + "'>" + kind +
    "<span class='gt'>" + esc(n.term || n.id) + "</span></a>";
}

// ── FINDINGS — prose without stock (the coverage inverse), each offender a door ──────
async function matFindings(mat) {
  const data = CACHE.findings || (CACHE.findings = await store.fetchJSON("/storyboard/coverage").catch(() => null));
  const bp = (data && data.prose_by_plan) || { offenders: [] };
  const bf = (data && data.prose_by_fact) || { offenders: [] };
  const offs = (bp.offenders || []).map((o) => ({ ...o, mode: "by-plan" }))
    .concat((bf.offenders || []).map((o) => ({ ...o, mode: "by-fact" })));
  mat.innerHTML = matHead("prose without stock · " + offs.length) +
    "<div class='sb-brief-prose' style='font-size:12px;margin:0 0 8px'>Paragraphs the plan asks for but no node backs " +
      "(by-plan), and realised paragraphs whose provenance traces to nothing (by-fact). Each doors one click into the paper.</div>" +
    "<div class='sb-cards'>" + (offs.length ? offs.slice(0, 80).map((o) =>
      "<a class='sb-card' style='cursor:pointer;text-decoration:none' href='/artefact?corpus=" + ec(CORPUS) + "&section=" + ec(o.section) + "'>" +
      "<div class='sb-ctitle'>" + esc(o.section) + " <span class='sb-tag'>" + esc(o.mode) + "</span></div>" +
      "<div class='sb-cmeta'>" + esc(o.paragraph || "") + (o.function ? " · " + esc(o.function) : "") + " ↗</div></a>").join("")
      : "<div class='sb-brief-prose'>every paragraph traces to stock — the healthy reading.</div>") + "</div>";
  wireMatClose(mat);
}

// ── RUN — the retained one-truth read: the SHARED run tray over launch_roster ────────
async function matRun(mat) {
  mat.innerHTML = matHead("the run · " + (BRIEF && BRIEF.run_label || "")) +
    "<div id='sb-run-host'></div>";
  wireMatClose(mat);
  await mountRunTray($("#sb-run-host", mat), { corpus: CORPUS, actor: "gerard", onStatus: status });
}

// ═══════════════ PIN — reallocate around the examined point ═══════════════
const RETURN_LABEL = "back to the board — where you were";

function pinSection(sid) {
  const cards = (BRIEF && BRIEF.cards) || [];
  const row = cards.find((s) => s.id === sid);
  if (!row) return;
  syncURL("section", sid);
  REALLOC.pin(sid, {
    title: (row.title || row.id) + " — the section",
    destination: RETURN_LABEL,
    buildRail: (railEl) => buildSectionRail(railEl, row, cards),
    buildFocus: (focusEl) => buildSectionFocus(focusEl, row),
  });
}
function buildSectionRail(railEl, row, cards) {
  railEl.innerHTML =
    "<div class='eng-railblock'><h5>freshness</h5><div class='sb-railcov'>" +
      (row.dirty ? "<span class='z'>plan changes need source review</span>" : "prose matches the plan") +
      (row.n_plan != null ? "<br>plan " + row.n_plan + " · prose " + (row.n_tex != null ? row.n_tex : "—") : "") + "</div></div>" +
    "<div class='eng-railblock'><h5>siblings</h5><div class='sb-rail-list'>" +
      cards.map((s) => "<div class='sb-rail-sec " + (s.id === row.id ? "is-here" : "") + "' data-goto='" + esc(s.id) + "'>" +
        esc(s.title || s.id) + "</div>").join("") + "</div></div>";
  $$(".sb-rail-sec[data-goto]", railEl).forEach((el) => activate(el, () => pinSection(el.dataset.goto)));
}
function buildSectionFocus(focusEl, row) {
  const pane = document.createElement("div");
  pane.className = "sb-focus-pane";
  const nodes = row.source_nodes || [];
  pane.innerHTML =
    "<div class='sb-focus-head'><div class='sb-focus-kind'>section · what will be projected here</div>" +
      "<div class='sb-focus-title'>" + esc(row.title || row.id) + "</div></div>" +
    "<div class='sb-focus-body'>" +
      "<div class='sb-ground'><div class='sb-ground-h'>the job · why this section exists</div>" +
        "<div class='sb-ground-why'>" + esc(row.why || "no job set for this section.") + "</div></div>" +
      (row.beats && row.beats.length ? "<div class='sb-ground'><div class='sb-ground-h'>beats · the narrative chain</div>" +
        "<div class='sb-beats'>" + row.beats.map((b) => "<span class='sb-beat'>" + esc(b.term || b.id) + "</span>").join("") + "</div></div>" : "") +
      "<div class='sb-ground'><div class='sb-ground-h'>stock · the nodes it pins (" + nodes.length + ")</div>" +
        (nodes.length ? "<div class='sb-gnodes'>" + nodes.map(gnodeHTML).join("") + "</div>"
          : "<div class='sb-gnone'>no node pinned here yet.</div>") + "</div>" +
      "<div class='sb-focus-doors'>" +
        "<a class='sb-door' href='" + esc(row.doors.artefact) + "'>read in the artefact · " + esc(row.id) + " ↗</a>" +
        "<a class='sb-door' href='" + esc(row.doors.conceptric) + "'>open its stock in conceptric ↗</a>" +
      "</div>" +
    "</div>";
  focusEl.appendChild(pane);
  focusEl.appendChild(buildSectionActions(row));   // P3 — the editing acts, wired to the endpoint
  focusEl.appendChild(buildStructureDoors(row));   // the plan-wide structure routes, surfaced
}

// ═══════════════ the STRUCTURE doors — the plan-wide routes, surfaced in the pinned
// focus (they were live endpoints with no control). Each NAMES what it writes and its
// cost class; the two that OVERWRITE the plan arm before firing (restructure gates
// apply behind its dry-run; edit-spine confirms). Every write re-reads from server
// truth (never optimistic). reconcile is cheap + idempotent, so it fires directly. ═══
function buildStructureDoors(row) {
  const wrap = document.createElement("div");
  wrap.className = "sb-actions sb-structure";
  const cheap = "<span class='sb-struct-cost is-cheap'>cheap · idempotent</span>";
  const exp = "<span class='sb-struct-cost is-exp'>expensive · overwrites</span>";
  wrap.innerHTML =
    "<div class='sb-actions-h'>structure · re-shapes the whole plan (these write beyond this " +
      (row.appendix ? "appendix" : "section") + ")</div>" +
    "<div class='sb-act' data-act='reconcile'>" +
      "<div class='sb-act-will'>reconcile section anchors" + cheap + "· re-derives every node's " +
        "section_ref from the plan and emits only the deltas; a second run writes nothing.</div>" +
      "<div class='sb-act-row'><button type='button' class='sb-act-btn' data-act='reconcile-fire'>reconcile the anchors</button></div></div>" +
    "<div class='sb-act' data-act='restructure'>" +
      "<div class='sb-act-will'>restructure the section arc" + exp + "· regenerates the whole plan " +
        "(sections, base, spine) from a target arc. Preview first; apply only after the dry-run reads clean.</div>" +
      "<div class='sb-act-row'><button type='button' class='sb-act-btn' data-act='restructure-preview'>preview a restructure</button></div></div>" +
    "<div class='sb-act' data-act='edit-spine'>" +
      "<div class='sb-act-will'>Narrative beats have their own order, distinct from sections.</div>" +
      "<a class='sb-door' href='/project?workspace=writing&amp;corpus=" + ec(CORPUS) + "&amp;view=reader-plan'>Open Reader plan to edit the narrative spine →</a></div>" +
    "<div id='sb-struct-status' role='status' aria-live='polite'></div>";

  const sstat = (msg, cls) => { const el = $("#sb-struct-status"); if (el) { el.className = cls || ""; el.textContent = msg || ""; } };
  const reread = async (okMsg) => {
    const fresh = await store.fetchJSON("/storyboard/brief").catch(() => null);
    if (fresh) BRIEF = fresh;
    if ((BRIEF.cards || []).some((s) => s.id === row.id)) pinSection(row.id); else closePin();
    sstat(okMsg, "is-ok");
  };

  activate(wrap.querySelector("[data-act='reconcile-fire']"), async () => {
    sstat("reconciling through /storyboard/plan/reconcile…");
    try {
      const res = await store.fetchJSON("/storyboard/plan/reconcile", { method: "POST", body: { by: ACTOR } });
      if (!res || res.ok === false) { sstat("not reconciled — " + ((res && res.error) || "refused"), "is-bad"); return; }
      await reread((res.emitted || 0) + " anchor(s) reconciled — the board re-read from the server.");
    } catch (e) { sstat("reconcile failed — " + ((e && e.message) || e), "is-bad"); }
  });

  // the restructure door SUMMONS the arc composer (Gap 1+2): the fetched arc rendered as
  // an editable ordering, its dry-run re-reading HIS edited arc, apply arm-then-fire. The
  // door is a switch — a second click closes the composer. The arc fetch lets the corpus
  // RIDE (default inject) — passing { inject: [] } was the dead-preview bug (corpus= dropped
  // → a 400 whose raw fetch text leaked to the decision point). Every error degrades to
  // composed words here (the propagate idiom): the raw HTTP/schema string never surfaces.
  activate(wrap.querySelector("[data-act='restructure-preview']"),
    () => buildArcComposer(wrap, row, sstat, reread));

  return wrap;
}

// ═══════════════ the arc composer (Gap 1+2) — the restructure door's authoring field ═══════
// The restructure endpoint could only ever preview a 0-moved no-op: the door fetched the
// IDENTITY arc and posted it verbatim. Here the fetched arc becomes an EDITABLE ordering —
// each section a renamable row with up/down doors — and the dry-run re-reads HIS arc (the
// permuted/renamed order), reporting how many sections moved. Apply arms before it overwrites
// the plan + base. The arc fetch lets the corpus RIDE (default inject); a failed read/preview
// degrades to composed words (never the raw fetchJSON/HTTP string at the decision point).
async function buildArcComposer(wrap, row, sstat, reread) {
  const host = wrap.querySelector("[data-act='restructure']");
  if (!host) return;
  const existing = host.querySelector(".sb-arc-composer");
  if (existing) { existing.remove(); sstat(""); return; }   // the door is a switch
  sstat("reading the current arc (the editable starting point)…");
  let arc;
  try {
    arc = await store.fetchJSON("/storyboard/arc");          // corpus rides (default inject)
  } catch (_e) {
    sstat("the arc could not be read — nothing is staged; no restructure is composed.", "is-bad");
    return;
  }
  if (!arc || !(arc.sections || []).length) {
    sstat("the arc could not be read — nothing is staged; no restructure is composed.", "is-bad");
    return;
  }
  const orig = (arc.sections || []).map((s) => s.id);
  // the working order — a live array the up/down doors permute; title + seed_from ride each row
  const items = (arc.sections || []).map((s) => ({
    id: s.id, title: s.title || s.id, seed_from: (s.seed_from && s.seed_from.length) ? s.seed_from : [s.id],
  }));
  const appendices = arc.appendices || [];
  const comp = document.createElement("div");
  comp.className = "sb-arc-composer";
  const composedArc = () => ({ corpus: CORPUS,
    sections: items.map((it) => ({ id: it.id, title: it.title, seed_from: it.seed_from })),
    appendices });
  const movedN = () => items.filter((it, i) => it.id !== orig[i]).length;
  // the server refusal is composed prose (the operator's own words) — safe to pass; a THROWN
  // fetch error never reaches here (each POST is caught below into composed words).
  const refusal = (rep) => (rep && rep.error) || "the operator refused the arc";
  let applyArmed = false;
  const preview = async () => {
    applyArmed = false;
    const moved = movedN();
    sstat("reading the dry-run of your arc…");
    let rep;
    try {
      rep = await store.fetchJSON("/storyboard/restructure", { method: "POST", body: composedArc() });
    } catch (_e) {
      sstat("the dry-run could not be read — nothing is staged; your arc is unsaved.", "is-bad");
      return;
    }
    if (!rep || rep.ok === false) {
      sstat("the arc was refused — " + refusal(rep) + " — nothing is staged.", "is-bad");
      return;
    }
    const nSec = (rep.sections || []).length;
    sstat("dry-run of your arc — " + nSec + " section(s), " + moved + " moved from the current order. " +
      "Apply regenerates the plan + base (overwrites). Arm below to apply.", "is-ok");
    // the apply door — arm-then-fire, NAMING what it overwrites; built once per preview
    let applyRow = comp.querySelector(".sb-arc-apply-row");
    if (!applyRow) {
      applyRow = document.createElement("div"); applyRow.className = "sb-act-row sb-arc-apply-row";
      const ab = document.createElement("button");
      ab.type = "button"; ab.className = "sb-act-btn is-danger"; ab.dataset.act = "restructure-apply";
      ab.textContent = "apply — overwrites the whole plan + base";
      applyRow.appendChild(ab);
      comp.appendChild(applyRow);
      activate(ab, async () => {
        if (!applyArmed) {
          applyArmed = true;
          ab.textContent = "confirm — overwrite the plan + base with your arc";
          sstat("armed · applying regenerates the plan + base from your arc (" + movedN() +
            " section(s) moved) and overwrites them. Click confirm to write.", "");
          return;
        }
        sstat("applying the restructure through /storyboard/restructure?apply=1…");
        try {
          const res = await store.fetchJSON("/storyboard/restructure", { method: "POST", body: composedArc(), params: { apply: 1 } });
          if (!res || res.ok === false) { sstat("not applied — " + refusal(res) + " — the plan is unchanged.", "is-bad"); return; }
          await reread("the plan was restructured to your arc — re-read from the server.");
        } catch (_e) { sstat("apply failed — the plan is unchanged (nothing was written).", "is-bad"); }
      });
    }
  };
  const render = () => {
    const moved = movedN();
    comp.innerHTML =
      "<div class='sb-arc-h'>compose the target arc — reorder + rename the sections, then dry-run HIS arc (his arc, never the identity no-op)</div>" +
      items.map((it, i) =>
        "<div class='sb-arc-row' data-arc-id='" + esc(it.id) + "'>" +
          "<span class='sb-arc-rank'>#" + (i + 1) + "</span>" +
          "<input type='text' class='sb-arc-title' value='" + esc(it.title) + "' aria-label='section title'>" +
          "<button type='button' class='sb-arc-mv sb-arc-up'" + (i === 0 ? " disabled" : "") + " aria-label='move up'>&uarr;</button>" +
          "<button type='button' class='sb-arc-mv sb-arc-down'" + (i === items.length - 1 ? " disabled" : "") + " aria-label='move down'>&darr;</button>" +
        "</div>").join("") +
      "<div class='sb-arc-moved' data-role='arc-moved'>" + moved + " of " + items.length + " section(s) moved from the current order" +
        (appendices.length ? " · " + appendices.length + " appendix(es) ride unchanged" : "") + "</div>" +
      "<div class='sb-act-row'><button type='button' class='sb-act-btn' data-act='restructure-dryrun'>dry-run this arc</button></div>";
    $$(".sb-arc-title", comp).forEach((inp, i) => inp.addEventListener("input", () => { items[i].title = inp.value; }));
    $$(".sb-arc-up", comp).forEach((btn, i) => activate(btn, () => {
      if (i > 0) { [items[i - 1], items[i]] = [items[i], items[i - 1]]; render(); }
    }));
    $$(".sb-arc-down", comp).forEach((btn, i) => activate(btn, () => {
      if (i < items.length - 1) { [items[i + 1], items[i]] = [items[i], items[i + 1]]; render(); }
    }));
    activate(comp.querySelector("[data-act='restructure-dryrun']"), () => preview());
  };
  render();
  host.appendChild(comp);
  sstat("the current arc is loaded — reorder or rename below, then dry-run your arc.", "");
}

// ═══════════════ P3 — the action row: the section's editing acts as engine focuses ═══════
// The old board's edits (reorder / retitle / edit-job / residue-retire) MOVED to endpoints
// during W-SB and were never ported as engine focuses — the pinned card read read-only. Here
// they fire from the pinned card through their EXISTING /storyboard/plan endpoint: each act
// says what it writes first, fires exactly one POST, and re-renders the focus from server truth
// (never optimistic — the focus is re-pinned from a freshly-fetched brief); errors in plain words.
async function firePlanOp(op, sid, okWord) {
  const st = $("#sb-act-status");
  if (st) { st.className = ""; st.textContent = "writing through /storyboard/plan…"; }
  try {
    const res = await store.fetchJSON("/storyboard/plan", { method: "POST", body: { ...op, by: ACTOR } });
    if (!res || res.ok === false) {
      const why = (res && (res.note || res.error || (res.new_violations || []).join(", "))) || "the endpoint refused the op";
      if (st) { st.className = "is-bad"; st.textContent = "not written — " + why; }
      return false;
    }
    // SERVER TRUTH: re-fetch the brief DATA and re-pin the focus from it (never an optimistic
    // local mutation). We refresh BRIEF and re-pin only — NOT renderBrief() — so the resting
    // materialised zone (where he'll land on close) keeps its geometry and the exact-scroll
    // restore holds; the focus itself is rebuilt wholesale from the freshly-minted server truth.
    const fresh = await store.fetchJSON("/storyboard/brief").catch(() => null);
    if (fresh) BRIEF = fresh;
    pinSection(sid);       // re-render the focus from the freshly-fetched brief
    const st2 = $("#sb-act-status");
    if (st2) { st2.className = "is-ok"; st2.textContent = okWord || "written — the focus re-read from the server."; }
    return true;
  } catch (e) {
    const st2 = $("#sb-act-status");
    if (st2) { st2.className = "is-bad"; st2.textContent = "write failed — " + ((e && e.message) || e); }
    return false;
  }
}

// the undo door — truncates the last banked plan op through POST /storyboard/plan/undo,
// then re-reads focus from server truth (never optimistic), worded with WHAT it undoes.
async function fireUndo(sid) {
  const st = $("#sb-act-status");
  if (st) { st.className = ""; st.textContent = "undoing through /storyboard/plan/undo…"; }
  try {
    const res = await store.fetchJSON("/storyboard/plan/undo", { method: "POST", body: { by: ACTOR } });
    if (!res || res.ok === false) {
      const st2 = $("#sb-act-status");
      if (st2) { st2.className = "is-bad"; st2.textContent = "nothing undone — " + ((res && res.error) || "nothing to undo"); }
      return false;
    }
    const fresh = await store.fetchJSON("/storyboard/brief").catch(() => null);
    if (fresh) BRIEF = fresh;
    // the undone op may have removed the pinned section — re-pin if it survives, else
    // fall back to the board so the surface never points at a section that is gone.
    if ((BRIEF.cards || []).some((s) => s.id === sid)) pinSection(sid); else closePin();
    const st2 = $("#sb-act-status");
    if (st2) { st2.className = "is-ok"; st2.textContent = "undone — " + (res.remaining_ops || 0) + " plan op(s) remain; re-read from the server."; }
    return true;
  } catch (e) {
    const st2 = $("#sb-act-status");
    if (st2) { st2.className = "is-bad"; st2.textContent = "undo failed — " + ((e && e.message) || e); }
    return false;
  }
}

function buildSectionActions(row) {
  const wrap = document.createElement("div");
  wrap.className = "sb-actions";
  const cards = (BRIEF && BRIEF.cards) || [];
  const isApp = !!row.appendix;
  const group = cards.filter((c) => !!c.appendix === isApp);   // reorder is WITHIN the group
  const idx = group.findIndex((c) => c.id === row.id);
  const reorderKind = isApp ? "reorder-appendices" : "reorder-sections";
  const gWord = isApp ? "appendix" : "section";
  const upTarget = idx > 0 ? group[idx - 1] : null;
  const downTarget = (idx >= 0 && idx < group.length - 1) ? group[idx + 1] : null;
  const nodes = row.source_nodes || [];
  const mv = (BRIEF && BRIEF.movement) || {};
  const canUndo = !!mv.changed;

  wrap.innerHTML =
    "<div class='sb-actions-h'>act on this " + gWord + " · each writes through /storyboard/plan</div>" +
    "<div class='sb-act' data-act='reorder'>" +
      "<div class='sb-act-will'>reorder · writes the " + gWord + " order in the plan; review and apply manuscript changes separately" +
        (upTarget ? "; up moves it above &ldquo;" + esc(cut(upTarget.title, 34)) + "&rdquo;" : "") +
        (downTarget ? "; down moves it below &ldquo;" + esc(cut(downTarget.title, 34)) + "&rdquo;" : "") + ".</div>" +
      "<div class='sb-act-row'>" +
        "<button type='button' class='sb-act-btn' data-act='reorder-up'" + (upTarget ? "" : " disabled") + ">&uarr; move up</button>" +
        "<button type='button' class='sb-act-btn' data-act='reorder-down'" + (downTarget ? "" : " disabled") + ">&darr; move down</button>" +
      "</div></div>" +
    "<div class='sb-act' data-act='retitle'>" +
      "<div class='sb-act-will'>retitle · writes the " + gWord + " title to the plan. Review and apply manuscript changes separately.</div>" +
      "<div class='sb-act-row'>" +
        "<input type='text' class='sb-act-field' data-act='retitle-input' value='" + esc(row.title || "") + "' aria-label='new title'>" +
        "<button type='button' class='sb-act-btn' data-act='retitle-save'>save title</button>" +
      "</div></div>" +
    // edit-job is PARAGRAPH-SCALE prose (why this section exists) — a textarea sized to the prose,
    // pre-filled with the current job, not a single-line input pretending copy fits on one row.
    "<div class='sb-act' data-act='edit-job'>" +
      "<div class='sb-act-will'>edit job · rewrites why this " + gWord + " exists in the plan. Prepare the proposed work, then review changes to authored source.</div>" +
      "<div class='sb-act-row'>" +
        "<textarea class='sb-act-field' data-act='edit-job-input' rows='3' aria-label='the section job'>" + esc(row.job || "") + "</textarea>" +
        "<button type='button' class='sb-act-btn' data-act='edit-job-save'>save job</button>" +
      "</div></div>" +
    (nodes.length ? "<div class='sb-act' data-act='retire'>" +
      "<div class='sb-act-will'>retire a pinned node · unpins it from this " + gWord +
        " (residue — the builder re-runs; the node returns to the un-projected pool).</div>" +
      "<div class='sb-act-row'>" +
        nodes.map((n) => "<button type='button' class='sb-act-btn is-danger' data-act='retire-node' data-node='" +
          esc(n.id) + "'>retire " + esc(cut(n.term || n.id, 22)) + "</button>").join("") +
      "</div></div>" : "") +
    // undo — the last banked plan op, dropped through /storyboard/plan/undo; worded
    // with WHAT it will undo (the last movement), disabled when nothing is banked.
    "<div class='sb-act' data-act='undo'>" +
      "<div class='sb-act-will'>undo · truncates the last banked plan op and re-reads the plan from the server — " +
        (canUndo ? "undoes &ldquo;" + esc(cut(mv.what || "the last edit", 74)) + "&rdquo;"
                 : "nothing is banked yet, so there is nothing to undo") + ".</div>" +
      "<div class='sb-act-row'>" +
        "<button type='button' class='sb-act-btn' data-act='undo-fire'" + (canUndo ? "" : " disabled") +
          ">&#8630; undo last plan op</button>" +
      "</div></div>" +
    "<div id='sb-act-status' role='status' aria-live='polite'></div>";

  const up = wrap.querySelector("[data-act='reorder-up']");
  if (up && upTarget) activate(up, () => {
    const order = group.map((c) => c.id);
    [order[idx - 1], order[idx]] = [order[idx], order[idx - 1]];
    firePlanOp({ kind: reorderKind, order }, row.id, "moved up — the order re-read from the server.");
  });
  const down = wrap.querySelector("[data-act='reorder-down']");
  if (down && downTarget) activate(down, () => {
    const order = group.map((c) => c.id);
    [order[idx + 1], order[idx]] = [order[idx], order[idx + 1]];
    firePlanOp({ kind: reorderKind, order }, row.id, "moved down — the order re-read from the server.");
  });
  activate(wrap.querySelector("[data-act='retitle-save']"), () => {
    const v = (wrap.querySelector("[data-act='retitle-input']").value || "").trim();
    firePlanOp({ kind: "retitle", section: row.id, title: v }, row.id, "title written — the focus re-read from the server.");
  });
  activate(wrap.querySelector("[data-act='edit-job-save']"), () => {
    const v = (wrap.querySelector("[data-act='edit-job-input']").value || "").trim();
    firePlanOp({ kind: "edit-job", section: row.id, job: v }, row.id, "Plan job saved — review the proposed manuscript work.");
  });
  wrap.querySelectorAll("[data-act='retire-node']").forEach((btn) => activate(btn, () =>
    firePlanOp({ kind: "remove-node", section: row.id, node: btn.dataset.node }, row.id,
      "node retired — the focus re-read from the server.")));
  const undo = wrap.querySelector("[data-act='undo-fire']");
  if (undo && canUndo) activate(undo, () => fireUndo(row.id));
  return wrap;
}

function pinWeighting(cid) {
  const rows = (BRIEF && BRIEF.weighting) || [];
  const row = rows.find((w) => w.id === cid);
  if (!row) return;
  syncURL("card", cid);
  REALLOC.pin(cid, {
    title: (row.excluded ? "excluded claim" : "claim #" + (row.rank != null ? row.rank : "?")),
    destination: RETURN_LABEL,
    buildRail: (railEl) => buildWeightingRail(railEl, row, rows),
    buildFocus: (focusEl) => buildWeightingFocus(focusEl, row),
  });
}
function buildWeightingRail(railEl, row, rows) {
  const nPrimary = rows.filter((w) => !w.excluded).length;
  const nExcluded = rows.filter((w) => w.excluded).length;
  railEl.innerHTML =
    "<div class='eng-railblock'><h5>the rank</h5><div class='sb-railcov'>" +
      nPrimary + " defended · " + nExcluded + " excluded</div></div>" +
    "<div class='eng-railblock'><h5>this card</h5><div class='sb-railcov'>" +
      (row.excluded ? "not claimed — the honesty contract" : "position #" + (row.rank != null ? row.rank : "?")) +
      "<br>" + (row.resolved ? "grounds in a named node" : "grounds in the goal") + "</div></div>";
}
function buildWeightingFocus(focusEl, row) {
  const pane = document.createElement("div");
  pane.className = "sb-focus-pane";
  pane.innerHTML =
    "<div class='sb-focus-head'><div class='sb-focus-kind'>weighting · " +
      (row.excluded ? "deliberately not claimed" : "defended contribution #" + (row.rank != null ? row.rank : "?")) + "</div>" +
      "<div class='sb-focus-title'>" + esc(row.claim || "") + "</div></div>" +
    "<div class='sb-focus-body'>" + groundBlock(row) +
      "<div class='sb-focus-doors'>" +
        "<a class='sb-door' href='/conceptric?corpus=" + ec(CORPUS) + "'>trace the whole argument in conceptric ↗</a>" +
      "</div></div>";
  focusEl.appendChild(pane);
}

// a search hit / deep-link may name a SECTION as its bare board id (s8) or in the node-
// namespaced section form (s8 under the section prefix, what /corpus/search returns) —
// resolve either to the board card it names, or null when the id names no section.
function sectionCardFor(id) {
  const cards = (BRIEF && BRIEF.cards) || [];
  const bare = String(id).replace(/^sec:/, "");
  return cards.find((s) => s.id === id) || cards.find((s) => s.id === bare) || null;
}

// land focus on the board itself (finding 2, stranger-walk 2026-07-23): the global search resolved
// "s8" to its section but clicking it was a DEAD click — it only tagged the URL and re-rendered
// the identical, unfiltered board. The author's law is that navigation lands focus (the promised
// object under the eye): bring the board's own tile under the eye and light it with the existing
// highlight idiom, the board staying WHOLE (his ruling: the picture never hides). From here the
// lit, id-named tile is the affordance — clicking it pins the section and its beats. The URL tag
// stays, but as ?section= (the canonical section key), and the navigation is now real.
function revealSection(sid) {
  if (REALLOC.pinned) REALLOC.close();   // the board tile must be visible to land on it
  if (OPEN_MAT) closeMaterialised();     // and no materialised zone steals the eye
  const el = $(".sbb-sec[data-sec='" + cssAttr(sid) + "']");
  if (!el) return;
  BUS.clear();
  BUS.lit([["sec", sid]], true);         // the existing board-highlight idiom (keyed on data-sec)
  el.scrollIntoView({ block: "center" });
  syncURL("section", sid);               // the URL tag may stay — as ?section=
}

// a node-search / deep ?node= landing. A SECTION-named hit (search "s8" → its namespaced
// section node, or a bare section id) lands on the board tile via revealSection; a real node
// pins the section that owns it and flashes its door.
function openNodeFocus(id, opts) {
  if (!id) return;
  const sec = sectionCardFor(id);
  if (sec) { revealSection(sec.id); return; }   // the promised object is a board tile, not a pinned node
  if (!(opts && opts.fromStore)) store.set({ node: id });
  const cards = (BRIEF && BRIEF.cards) || [];
  const owner = cards.find((s) => (s.source_nodes || []).some((n) => n.id === id)
    || (s.beats || []).some((b) => b.id === id));
  if (owner) {
    pinSection(owner.id);
    const door = $(".sb-gnode[data-gnode='" + cssAttr(id) + "']");
    if (door) { door.classList.add("lit"); door.scrollIntoView({ block: "center" }); setTimeout(() => door.classList.remove("lit"), 1600); }
  }
}

// close a pin: restore geometry + scroll exactly, clear the deep-link param.
function closePin() { REALLOC.close(); syncURL(null); }

// ═══════════════ No lobby tax — deep-link entry-point composition (DESIGN B.5) ═══════
// A selection param PRE-PINS its target on load: the brief is the default entry, never a
// toll booth. Returning within a session restores where he was (the URL carries the pin).
function entryFromParams() {
  const p = new URLSearchParams(location.search);
  const section = p.get("section");
  const card = p.get("card") || p.get("weighting");
  const node = p.get("node") || p.get("focus");
  if (section && (BRIEF && BRIEF.cards || []).some((s) => s.id === section)) { pinSection(section); return; }
  if (card && (BRIEF && BRIEF.weighting || []).some((w) => w.id === card)) { pinWeighting(card); return; }
  if (node) openNodeFocus(node);
}
function syncURL(key, val) {
  try {
    const u = new URL(location.href);
    u.searchParams.delete("section"); u.searchParams.delete("card"); u.searchParams.delete("weighting");
    if (key && val) u.searchParams.set(key, val);
    history.replaceState(null, "", u);
  } catch (_e) { /* history is an enhancement */ }
}

function status(msg, cls) { const el = $("#sb-status"); if (el) el.textContent = msg || ""; void cls; }
