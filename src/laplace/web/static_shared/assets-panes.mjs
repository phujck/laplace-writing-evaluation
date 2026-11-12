// assets-panes.mjs — the asset surface's pane logic (W-ASSETS), the seventh and LAST
// surface's join to the one instrument (engine.mjs).
//
// The asset instrument's resting altitude is the composed BRIEF (DESIGN_2026-07-22_the-
// interface-engine.md C + E): what this project carries — the real counts BY KIND (never a
// hardcoded figure), which are landed in the artefact and which demonstrate a claim (plain
// words) — and at most one ask. The roster is the summonable inventory: nothing is
// materialised until a count chip opens its suite. Opening an asset REALLOCATES (the engine's
// focus geometry) to the close-examination instrument — the four-zone cockpit re-homed behind
// focus, the triptych responding to entry point — with a named return door back to the brief.
// A HOT arrival (?asset=) skips the brief and lands pre-pinned on that asset (DESIGN B.5, no
// lobby tax); a session-sticky return lands where he was; close restores geometry exactly.
//
// The lock-step law: the brief is composed server-side (GET /assets/brief) over the SAME
// enumerate_assets read the roster (GET /assets/list) reads — one truth; the client renders
// it verbatim and re-derives no count. subset-sum's 41 enumerated assets and eigenengine's 6
// figures compose through the SAME machinery — the renderer names the enumeration, never a
// figure. The cockpit's CONTEXT zone (a figure IMAGE or a STEP list) is THIS module's one
// implementation, exported so the reader-side anchor layer opens the SAME cockpit.
//
// W-FINISH's scroll containment stays INTACT: #assets is the bounded pane (the page never
// scrolls); the engine reallocation happens INSIDE it, and the pane scroll restores exactly
// on close. All network rides store.fetchJSON (the one gateway); all colour is a hymn var.

import store from "/shared/store.mjs";
// the four-zone cockpit reuses the shared arm-to-fire idiom + the explicit actor (never a cousin).
import { armToFire, DESK_ACTOR } from "/shared/desk-panes.mjs";
// the sole focus/geometry runtime — the surface joins the engine, it does not re-fork it.
import { injectEngineCSS, createFocusState, HighlightBus, HoverLens, Reallocator, activate }
  from "/shared/engine.mjs";

// ── ✎ rule (D16) — the shell's rule-in-place atom, attached to a rulable host (the
// card head). A bonus atom: its absence (shell not yet loaded) never breaks the card. ──
function attachRule(host, ctx) {
  if (!host) return;
  try {
    const R = typeof window !== "undefined" && window.HymnShell && window.HymnShell.hyRule;
    if (R && R.attach) R.attach(host, ctx);
  } catch (_e) { /* the ✎ mouth is a bonus atom — never load-bearing */ }
}

// ── tiny helpers (the pane-module idiom, copied verbatim across the surfaces) ──────────
const ec = encodeURIComponent;
const esc = (s) => String(s == null ? "" : s)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
  .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
// THE VISIBLE ⓘ IDIOM (always-rendered glyph naming "endpoint → producing file"), verbatim.
function infoTag(txt) { return " <span class='hy-info' title='" + esc(txt) + "' tabindex='0'>ⓘ</span>"; }
// the display id — the kind prefix (figure:/derivation:) is carried by the kind chip, so the
// mono id reads clean (the register law: the identity shows, the internal prefix does not repeat).
const shortId = (id) => String(id || "").replace(/^(figure|derivation):/, "");

// the finding KINDS the assess selector offers (a small, plain set matching the feedback door).
const _ASSESS_KINDS = ["note", "imprecise", "missing-derivation", "refute", "off-voice"];

// the work-orders desk door (a banked regen order surfaces there for a later session);
// the server carries the same href, this is the fallback when it does not.
const DESK_ORDERS_HREF = "/desk?class=work-orders";

// ── module state (one surface, one model) ───────────────────────────────────────────────
let CORPUS = "";        // the resolved project (server-canonical, read back from the brief)
let BRIEF = null;       // /assets/brief payload (the composed resting altitude)
let LIST = null;        // /assets/list payload (the roster), lazy — materialised behind one open
let ENTRY = "index";    // the entry point (reader | claim | index) — governs the triptych emphasis
let OPEN_MAT = null;    // the materialised suite key ("figures" | "derivations"), or null (brief)
let STATE = createFocusState("index");
let BUS = null, LENS = null, REALLOC = null;
const SELECTION = {};   // asset id -> remembered focus (restore-on-reopen, B.3)
let _paneScrollAtPin = 0;   // #assets scrollTop captured at pin — restored exactly on close
let _closeObs = null;       // one-shot observer that restores the pane scroll after any close

const WHERE_KEY = "as-where";   // session-sticky return: {corpus, mat, asset}

// ── layout-only CSS (behaviour + component colour ride hymn.css + engine.mjs; the cockpit's
// own .dk-* classes live in hymn.css). Namespaced .asb-* — the asset brief chrome. ──────────
const ASSETS_CSS = `
#assets #eng-root{min-width:0}
/* the eng-rail sticks to the BOUNDED pane's top, not 56px below it (the page never scrolls) */
#assets .eng-rail{top:8px}
/* THE BRIEF — the resting altitude: composed prose + one ask + count chips, nothing else */
.asb-prose{font-size:14px;line-height:1.65;color:var(--ink);margin:6px 0 4px;max-width:76ch}
.asb-ask{font-size:12.5px;line-height:1.55;color:var(--ink2);margin:2px 0 6px;max-width:76ch;
  border-left:3px solid var(--accent);padding-left:11px}
/* the miss banner — a bad ?asset= deep-link resolved to no card: worded, transient, candid
   (the fallback law — absence stated with its reason, never a silent landing on the brief) */
.asb-miss{font-size:12px;line-height:1.5;color:var(--ink);background:var(--panel);
  border:1px solid var(--warn);border-left:3px solid var(--warn);border-radius:8px;
  padding:8px 12px;margin:2px 0 10px;max-width:76ch;transition:opacity .5s ease}
.asb-miss .asb-miss-id{font-family:var(--mono);color:var(--warn)}
.asb-miss.is-fading{opacity:0}
.asb-counts{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0 6px}
.asb-count{display:inline-flex;align-items:center;gap:7px;cursor:pointer;background:var(--panel);
  border:1px solid var(--edge2);border-radius:9px;padding:8px 12px;font:inherit;color:var(--ink2);min-width:0}
.asb-count:hover{border-color:var(--accent);color:var(--ink)}
.asb-count:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.asb-count.is-open{border-color:var(--keystone);color:var(--ink);box-shadow:inset 0 0 0 1px var(--keystone)}
.asb-count.is-empty{opacity:.55;cursor:default}
.asb-count .asb-cn{font-family:var(--mono);font-weight:700;color:var(--ink);font-size:14px}
.asb-count .asb-cl{font-size:11.5px}
/* the materialised roster — built on open, removed on close (never present at rest) */
.asb-mat{margin-top:14px}
.asb-mat-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:11px}
.asb-mat-h{font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.1em;color:var(--dim);font-weight:700}
.asb-back{font-family:var(--mono);font-size:10.5px;color:var(--accent);text-decoration:none;border:1px solid var(--edge);
  border-radius:7px;padding:4px 10px;background:var(--bg);cursor:pointer}
.asb-back:hover{border-color:var(--accent);color:var(--ink)}
.asb-cards{display:flex;flex-direction:column;gap:8px;max-width:860px}
.asb-card{border:1px solid var(--edge2);border-radius:10px;background:var(--panel);padding:11px 13px;
  display:flex;flex-direction:column;gap:6px;cursor:pointer;min-width:0}
.asb-card:hover{border-color:var(--accent)}
.asb-card:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.asb-card-head{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap}
.asb-card-head .asb-id{font-family:var(--mono);font-size:12.5px;font-weight:700;color:var(--ink);min-width:0;
  overflow:hidden;text-overflow:ellipsis}
.asb-card-head .asb-open{margin-left:auto;font-family:var(--mono);font-size:9.5px;color:var(--dim)}
.asb-facts{font-size:11.5px;line-height:1.5;color:var(--ink2)}
.as-empty{color:var(--dim);font-size:11.5px;padding:6px 2px}
/* the rail's compact summaries (C.4) — landing / claims / fine-grained / roster / switch */
.asb-entry{font-family:var(--mono);font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:var(--dim);
  margin-bottom:4px}
.asb-railfact{font-family:var(--mono);font-size:10.5px;color:var(--ink2);line-height:1.6}
.asb-switch{display:flex;flex-direction:column;gap:4px}
.asb-switch a{font-family:var(--mono);font-size:10.5px;color:var(--ink2);text-decoration:none;padding:2px 0;cursor:pointer;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.asb-switch a:hover{color:var(--accent)}
.asb-switch a.is-here{color:var(--keystone);cursor:default}
/* the CONTEXT zone's rendered figure — layout only (bounds an <img>, no colour) */
.as-fig{max-width:100%;max-height:340px;border-radius:6px;display:block}
.as-fig-wrap{margin:2px 0 4px}
.as-step{font-family:var(--mono);font-size:10.5px;line-height:1.5;padding:1px 0;
  display:flex;gap:8px;flex-wrap:wrap;align-items:baseline}
.as-assess{display:flex;flex-direction:column;gap:5px;margin-top:6px;width:100%}
.as-assess select,.as-assess textarea{font:inherit;background:var(--panel2);color:var(--ink);
  border:1px solid var(--edge);border-radius:6px;padding:4px 7px;width:100%}
.as-assess textarea{min-height:44px;resize:vertical;font-size:11.5px}
.as-msg{font-family:var(--mono);font-size:10px;color:var(--ink2)}
.as-msg .as-door{color:var(--accent);text-decoration:none;border-bottom:1px dashed var(--accent)}
.as-msg .as-door:hover{color:var(--ink)}
.err{color:var(--bad)}
/* ── the FINDINGS zone (the assess echo): every banked finding on this asset, the just-
   banked one leading and briefly accented — his anchored finding is visible where he looks. ── */
.as-finds{display:flex;flex-direction:column;gap:8px}
.as-find{border:1px solid var(--edge2);border-radius:9px;background:var(--panel);padding:9px 12px;
  display:flex;flex-direction:column;gap:5px;transition:border-color .5s ease,box-shadow .5s ease}
.as-find.is-fresh{border-color:var(--keystone);box-shadow:inset 0 0 0 1px var(--keystone)}
.as-find-head{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap}
.as-find-anchor{font-family:var(--mono);font-size:10.5px;color:var(--ink2)}
.as-find-meta{margin-left:auto;font-family:var(--mono);font-size:9.5px;color:var(--dim)}
.as-find-comment{font-size:12px;line-height:1.55;color:var(--ink)}
.as-find-composed{font-family:var(--mono);font-size:9.5px;color:var(--dim);line-height:1.5}
/* ── the consequences zone's banked regen orders — each a door onto the work-orders desk ── */
.as-orders{display:flex;flex-direction:column;gap:6px;margin-top:9px;border-top:1px dashed var(--edge2);padding-top:9px}
.as-order{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap}
.as-order-door{font-family:var(--mono);font-size:10.5px;color:var(--accent);text-decoration:none;
  border:1px solid var(--edge);border-radius:6px;padding:2px 9px;background:var(--bg)}
.as-order-door:hover{border-color:var(--accent);color:var(--ink)}
.as-order-when{font-family:var(--mono);font-size:9.5px;color:var(--dim)}
`;

function injectAssetsCSS() {
  if (typeof document === "undefined" || document.getElementById("asb-components")) return;
  const st = document.createElement("style"); st.id = "asb-components"; st.textContent = ASSETS_CSS;
  document.head.appendChild(st);
}

// the bounded scroller — #assets (W-FINISH's scroll law: the page never scrolls, this pane does).
function scroller() {
  return (typeof document !== "undefined" && document.getElementById("assets")) ||
    (typeof document !== "undefined" && document.scrollingElement) || null;
}

// ═══════════════ BOOT ═══════════════
export async function initAssets() {
  injectEngineCSS(); injectAssetsCSS();
  BUS = new HighlightBus(document);
  LENS = new HoverLens();
  const root = $("#eng-root");
  if (!root) return;
  REALLOC = new Reallocator(root, STATE, BUS);
  if (typeof document !== "undefined")
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { if (REALLOC.pinned) REALLOC.close(); else if (OPEN_MAT) closeMaterialised(); }
    });
  await load();
  await applyEntry();
}

async function load() {
  CORPUS = store.field("corpus") || "";
  BRIEF = await store.fetchJSON("/assets/brief", { params: CORPUS ? { corpus: CORPUS } : {} }).catch(() => null);
  if (BRIEF && BRIEF.corpus) CORPUS = BRIEF.corpus;
  renderBrief();
}

async function ensureList() {
  if (LIST) return LIST;
  LIST = await store.fetchJSON("/assets/list", { params: CORPUS ? { corpus: CORPUS } : {} })
    .catch(() => ({ figures: [], derivations: [], counts: {} }));
  return LIST;
}
function suiteOf(card) { return card.kind === "figure" ? "figures" : "derivations"; }
function findCard(id) {
  const all = [].concat((LIST && LIST.figures) || [], (LIST && LIST.derivations) || []);
  return all.find((c) => c.id === id) || null;
}

// ═══════════════ THE BRIEF — the resting altitude (E) ═══════════════
function renderBrief() {
  const brief = $(".eng-brief"); if (!brief) return;
  OPEN_MAT = null;
  if (!BRIEF) { brief.innerHTML = "<div class='asb-prose'>no asset roster resolved for this project.</div>"; return; }
  const g = (BRIEF.brief && BRIEF.brief.glance) || "";
  const ask = (BRIEF.brief && BRIEF.brief.ask) || "";
  const c = BRIEF.counts || {};
  brief.innerHTML =
    "<div class='asb-prose' data-role='brief-prose'>" + esc(g) +
      infoTag("GET /assets/brief → assets_surface.brief_payload (composed over pipeline/asset_model.enumerate_assets — one truth)") + "</div>" +
    (ask ? "<div class='asb-ask' data-role='brief-ask'>" + esc(ask) + "</div>" : "") +
    "<div class='asb-counts'>" +
      countChip("figures", c.figures, "figure" + (c.figures === 1 ? "" : "s")) +
      countChip("derivations", c.derivations, "derivation" + (c.derivations === 1 ? "" : "s")) +
    "</div>" +
    "<div class='asb-mat' id='as-mat'></div>";
  wireBrief();
}

function countChip(kind, n, label) {
  const empty = !n;
  const num = n == null ? "" : "<span class='asb-cn'>" + n + "</span>";
  return "<button type='button' class='asb-count" + (empty ? " is-empty" : "") + "' data-kind='" + kind + "'" +
    (empty ? " aria-disabled='true'" : "") + ">" + num + "<span class='asb-cl'>" + esc(label) + "</span></button>";
}

function wireBrief() {
  $$(".asb-count[data-kind]").forEach((chip) => {
    if (chip.classList.contains("is-empty")) return;
    activate(chip, () => materialise(chip.dataset.kind));
  });
}

// ── the miss banner (B.5, the honesty seam): a deep-link (?asset=) or a stale sticky return
// that resolves to no card after materialise must SAY so — a bad id landing silently on the
// brief is indistinguishable from a working landing. Surface a transient worded banner naming
// the id + the corpus, then leave him on the roster (never synthesize a card that isn't there).
let _missTimer = null;
function flashMiss(id) {
  const brief = $(".eng-brief"); if (!brief) return;
  const corpus = CORPUS || "this corpus";
  let banner = $("#as-miss", brief);
  if (!banner) {
    banner = document.createElement("div");
    banner.id = "as-miss"; banner.className = "asb-miss";
    banner.setAttribute("role", "status");
    brief.insertBefore(banner, brief.firstChild);
  }
  banner.classList.remove("is-fading");
  banner.innerHTML = "no such asset here — showing the roster · no <span class='asb-miss-id'>" +
    esc(shortId(id)) + "</span> in " + esc(corpus);
  if (_missTimer) clearTimeout(_missTimer);
  _missTimer = setTimeout(() => {
    banner.classList.add("is-fading");
    setTimeout(() => { if (banner.parentNode) banner.remove(); }, 550);
  }, 6000);
}

// ═══════════════ MATERIALISE — the roster of a suite behind one open (E) ═══════════════
async function materialise(kind) {
  const mat = $("#as-mat"); if (!mat) return;
  if (OPEN_MAT === kind) { closeMaterialised(); return; }
  OPEN_MAT = kind;
  $$(".asb-count").forEach((c) => c.classList.toggle("is-open", c.dataset.kind === kind));
  mat.innerHTML = "<div class='asb-mat-head'><span class='asb-mat-h'>materialising " + esc(kind) + "…</span></div>";
  await ensureList();
  const cards = (LIST[kind] || []);
  mat.innerHTML =
    "<div class='asb-mat-head'><span class='asb-mat-h'>" + esc(kind) + " · " + cards.length + "</span>" +
      "<button type='button' class='asb-back' data-role='mat-close'>← back to the brief</button></div>" +
    "<div class='asb-cards' id='asb-cards'>" +
      (cards.length ? cards.map(assetCardHTML).join("")
        : "<div class='as-empty'>" +
          (kind === "derivations" ? "no derivation walks banked for this project" : "no figures") + "</div>") +
    "</div>";
  wireMat(mat);
  persistWhere();
}

function closeMaterialised() {
  const mat = $("#as-mat"); if (mat) mat.innerHTML = "";
  OPEN_MAT = null;
  $$(".asb-count").forEach((c) => c.classList.remove("is-open"));
  BUS.clear();
  persistWhere();
}

function assetCardHTML(card) {
  const prod = card.producer || {};
  const facts = [
    card.inputs_n ? (card.inputs_n + " input" + (card.inputs_n === 1 ? "" : "s")) : null,
    card.nodes_n ? (card.nodes_n + " node" + (card.nodes_n === 1 ? "" : "s")) : null,
    card.landings_n ? (card.landings_n + " landing" + (card.landings_n === 1 ? "" : "s")) : null,
    card.steps_n ? (card.steps_n + " step anchor" + (card.steps_n === 1 ? "" : "s")) : null,
    card.panels_n ? (card.panels_n + " panel" + (card.panels_n === 1 ? "" : "s")) : null,
  ].filter(Boolean).join(" · ") || "no facts linked yet";
  return "<div class='asb-card' data-asset='" + esc(card.id) + "' tabindex='0' role='button'>" +
    "<div class='asb-card-head'>" +
      "<span class='dk-cls'>" + esc(card.kind) + "</span>" +
      "<span class='asb-id'>" + esc(shortId(card.id)) + "</span>" +
      "<span class='hy-chip'>" + esc(prod.type || "none") + "</span>" +
      "<span class='asb-open'>open →</span>" +
    "</div>" +
    "<div class='asb-facts'>" + esc(facts) + "</div></div>";
}

function wireMat(mat) {
  const close = mat.querySelector("[data-role='mat-close']");
  if (close) activate(close, () => closeMaterialised());
  $$(".asb-card[data-asset]", mat).forEach((el) => {
    const card = findCard(el.dataset.asset) || {};
    // ✎ rule on the card head — bank a typed interface fork about THIS asset (D16).
    attachRule(el.querySelector(".asb-card-head"), {
      surface: "assets", title: card.id, kind: card.kind,
      node: (card.nodes_supported && card.nodes_supported[0]) || card.node_id || card.id,
      project: CORPUS,
    });
    // hover REVEALS a compact glance in the fixed lens (no reflow); click OPENS the asset whole.
    el.addEventListener("mouseenter", () => LENS.show(el,
      "<div class='lens-h'>" + esc(shortId(el.dataset.asset)) + " — at a glance</div><div>" +
      esc((el.querySelector(".asb-facts") || {}).textContent || "") + "</div>"));
    el.addEventListener("mouseleave", () => LENS.hide());
    activate(el, (e) => {
      if (e && e.target && e.target.closest(".rule-chip, .rule-cap")) return;   // the ✎ atom owns its clicks
      LENS.hide(); openAsset(el.dataset.asset);
    });
  });
}

// ═══════════════ open an asset — pin / reallocate to the close-examination instrument (B.2) ═══
// The four-zone cockpit is re-homed behind focus: opening an asset REALLOCATES the surface to
// the whole asset (the figure image / the derivation steps, its consequences, its tools, its
// deep-links) with a named return door. The materialised roster is preserved beneath the focus
// so the return lands on it exactly; the bounded pane's scroll restores on close.
async function openAsset(id, opts = {}) {
  await ensureList();
  const card = findCard(id);
  if (!card) { flashMiss(id); return; }                // unknown asset — say so, land on the roster
  const suite = suiteOf(card);
  if (OPEN_MAT !== suite) await materialise(suite);    // land the return on the roster, exact
  const title = shortId(id) + " — the asset, whole";
  const destination = "back to the brief — where you were";
  _paneScrollAtPin = (scroller() || {}).scrollTop || 0;
  watchClose();
  REALLOC.pin(id, {
    title, destination,
    buildRail: (railEl) => buildAssetRail(railEl, card),
    buildFocus: (focusEl) => buildAssetFocus(focusEl, card),
  });
  SELECTION[id] = { pinned: true };
  persistWhere();
}

// the context rail (C.4): the compact summaries of both relation sets, ORDERED by entry point
// (from a claim → the supported nodes dominate; from the reader/index → the reader landings do),
// plus the fine-grained anchor count, the roster census, and a same-kind switch.
function buildAssetRail(railEl, card) {
  const c = (BRIEF && BRIEF.counts) || {};
  const landBlock = "<div class='eng-railblock'><h5>lands in the reader</h5><div class='asb-railfact'>" +
    (card.landings_n ? card.landings_n + " landing" + (card.landings_n === 1 ? "" : "s") : "no reader landing yet") +
    "</div></div>";
  const nodeBlock = "<div class='eng-railblock'><h5>claims it supports</h5><div class='asb-railfact'>" +
    (card.nodes_n ? card.nodes_n + " node" + (card.nodes_n === 1 ? "" : "s") : "no supported node linked") +
    "</div></div>";
  const fine = card.kind === "figure"
    ? (card.panels_n ? card.panels_n + " panel anchor" + (card.panels_n === 1 ? "" : "s") : "single-panel figure")
    : (card.steps_n ? card.steps_n + " step anchor" + (card.steps_n === 1 ? "" : "s") : "no parsed steps");
  const order = ENTRY === "claim" ? [nodeBlock, landBlock] : [landBlock, nodeBlock];
  const sibs = ((LIST && LIST[suiteOf(card)]) || []).filter((x) => x.id !== card.id).slice(0, 12);
  railEl.innerHTML =
    "<div class='asb-entry'>arrived from the " + esc(ENTRY) + "</div>" +
    order.join("") +
    "<div class='eng-railblock'><h5>fine-grained</h5><div class='asb-railfact'>" + esc(fine) + "</div></div>" +
    "<div class='eng-railblock'><h5>the roster</h5><div class='asb-railfact'>" +
      (c.total || 0) + " asset(s) · " + (c.figures || 0) + " fig · " + (c.derivations || 0) + " der</div></div>" +
    (sibs.length ? "<div class='eng-railblock'><h5>switch asset</h5><div class='asb-switch'>" +
      "<a class='is-here'>" + esc(shortId(card.id)) + "</a>" +
      sibs.map((s) => "<a data-sw='" + esc(s.id) + "'>" + esc(shortId(s.id)) + "</a>").join("") +
      "</div></div>" : "");
  $$("[data-sw]", railEl).forEach((a) => activate(a, () => openAsset(a.getAttribute("data-sw"))));
}

function buildAssetFocus(focusEl, card) {
  const holder = document.createElement("div");
  holder.className = "asb-focus-holder";
  focusEl.appendChild(holder);                          // append AFTER the engine's return door
  renderAssetCockpit(holder, { corpus: CORPUS, id: card.id });
}

// ── session-sticky return + deep-link pre-pin (B.5, no lobby tax) ─────────────────────────
function persistWhere() {
  try {
    if (typeof sessionStorage === "undefined") return;
    sessionStorage.setItem(WHERE_KEY, JSON.stringify({
      corpus: CORPUS, mat: OPEN_MAT || null,
      asset: (REALLOC && REALLOC.pinned && REALLOC.pinned.id) || null }));
  } catch (_e) { /* private mode — stickiness silently degrades */ }
}

// one-shot: after ANY close (return door / breadcrumb / Esc), restore the bounded pane's scroll
// exactly and re-persist the (now unpinned) where. Watches the reallocated class on #eng-root.
function watchClose() {
  if (_closeObs) return;
  const root = $("#eng-root");
  if (!root || typeof MutationObserver === "undefined") return;
  _closeObs = new MutationObserver(() => {
    if (!root.classList.contains("reallocated")) {
      const sc = scroller();
      // B.3: exact restore. The brief (with the materialised roster) has just been re-shown, so
      // set scrollTop only AFTER its layout reflows — an early set clamps against a not-yet-tall
      // pane. Force a reflow read, set now, and re-assert next frame in case the roster's images
      // reflow the height late (a clamp-then-grow would otherwise strand the pane at the top).
      const apply = () => { if (sc) { void sc.scrollHeight; sc.scrollTop = _paneScrollAtPin || 0; } };
      apply();
      if (typeof requestAnimationFrame !== "undefined")
        requestAnimationFrame(() => { apply(); requestAnimationFrame(apply); });
      persistWhere();
      _closeObs.disconnect(); _closeObs = null;
    }
  });
  _closeObs.observe(root, { attributes: true, attributeFilter: ["class"] });
}

async function applyEntry() {
  const q = new URLSearchParams(typeof location !== "undefined" ? location.search : "");
  ENTRY = (q.get("from") || store.field("from") || "index").trim() || "index";
  const asset = (store.field("asset") || q.get("asset") || "").trim();
  if (asset) { await openAsset(asset, { deep: true }); return; }   // ?asset= pre-pins — no lobby tax
  let where = null;
  try { where = JSON.parse((typeof sessionStorage !== "undefined" && sessionStorage.getItem(WHERE_KEY)) || "null"); }
  catch (_e) { where = null; }
  if (where && where.corpus === CORPUS) {                          // returning hot lands where he was
    if (where.asset) { await openAsset(where.asset, { deep: true }); return; }
    if (where.mat) await materialise(where.mat);
  }
}

// ══════════════════════════════════════════════════════════════════════════════════════════
// the asset cockpit — the close-examination instrument. the sole implementation (exported so the
// reader-side anchor layer opens the SAME cockpit in place). Fetches /assets/object, renders
// CONTEXT (image / steps) · CONSEQUENCES · TOOLS (assess + edit + regen) · DEEP-LINKS. Re-homed
// behind focus by W-ASSETS; its body is verbatim the W7 cockpit (the debt already paid).
// ══════════════════════════════════════════════════════════════════════════════════════════
export async function renderAssetCockpit(host, opts) {
  opts = opts || {};
  const corpus = opts.corpus || store.field("corpus") || "";
  const id = opts.id;
  host.innerHTML = "<div class='dk-cockpit'><div class='dk-ref-loading'>loading the asset…</div></div>";
  let o;
  try { o = await store.fetchJSON("/assets/object", { params: { corpus, id } }); }
  catch (e) {
    host.innerHTML = "<div class='dk-cockpit'><div class='dk-absent'>asset unavailable: " +
      esc((e && e.message) || e) + "</div></div>";
    return;
  }
  const a = o.asset || {};
  const isFig = a.kind === "figure";
  host.innerHTML =
    "<div class='dk-cockpit'>" +
      "<div class='dk-zone zone-context'><h4>context — " +
        (isFig ? "the rendered figure" : "the derivation steps") + "</h4>" +
        "<div class='dk-ctx-body'>" + contextZone(o) + "</div></div>" +
      "<div class='dk-zone zone-consequences'><h4>consequences — what a regen rebuilds</h4>" +
        "<div class='dk-conseq-body'>" + consequencesZone(o) + "</div></div>" +
      "<div class='dk-zone dk-zone-full zone-tools'><h4>tools</h4>" +
        toolsZone(o) + "</div>" +
      "<div class='dk-zone dk-zone-full zone-findings'><h4>findings — what has been caught here</h4>" +
        "<div class='dk-find-body' id='as-findings'>" + findingsZone(o) + "</div></div>" +
      "<div class='dk-zone dk-zone-full zone-deeplinks'><h4>deep-links — the spine location</h4>" +
        "<div class='dk-links'>" + deeplinksZone(o) + "</div></div>" +
    "</div>";
  wireCockpit(host, o);
}

// ZONE 1 — CONTEXT: the rendered figure (inline <img> when a raster/svg exists; a door for a
// pdf render; declared absence for tikz-unrendered) OR the derivation step list.
function contextZone(o) {
  const a = o.asset || {};
  if (a.kind === "figure") {
    if (o.render && o.render_kind === "image") {
      return "<div class='as-fig-wrap hy-render'><img class='as-fig' loading='lazy' src='" +
        esc(o.render_href) + "' alt='" + esc(a.id) + "'></div>" +
        "<div class='dk-ref-path'>" + esc(o.render) + "</div>";
    }
    if (o.render && o.render_kind === "pdf") {
      return "<div class='dk-ref-k'>rendered as pdf</div>" +
        "<a class='dk-act compose' href='" + esc(o.render_href) + "' target='_blank'>open the rendered pdf →</a>" +
        "<div class='dk-ref-path'>" + esc(o.render) + "</div>";
    }
    return "<div class='dk-absent'>not yet compiled — the tikz source has no rendered sibling</div>";
  }
  const steps = a.steps || [];
  if (!steps.length) return "<div class='dk-absent'>no equation steps parsed in this walk</div>";
  return steps.map((s) =>
    "<div class='as-step'><span class='dk-title'>" + esc(s.id) + "</span>" +
    "<span class='hy-chip'>" + esc(s.kind) + "</span>" +
    "<span class='art-dim'>L" + esc(s.line_start) + "–" + esc(s.line_end) + "</span></div>").join("");
}

// ZONE 2 — CONSEQUENCES: what a regen would rebuild (plain "no regen model" where none),
// plus the regen orders already banked for this asset — each a door onto the desk's
// work-orders stratum (the echo: a banked order has a place he can open).
function consequencesZone(o) {
  const base = "<div class='dk-conseq'><span class='cv'>regen</span><span class='cw'>" +
    esc(o.regen_what || "no consequence model yet for this asset") + "</span></div>";
  return base + ordersZone(o);
}

// the banked regen orders (o.orders), or nothing when none stand — built on load and
// refreshed in place the moment a regen banks one (the echo where he looks).
function ordersZone(o) {
  const orders = o.orders || [];
  if (!orders.length) return "";
  const href = (o.orders_href || DESK_ORDERS_HREF);
  return "<div class='as-orders' id='as-orders'>" +
    "<div class='dk-ref-k'>banked regen order" + (orders.length === 1 ? "" : "s") + " for this asset</div>" +
    orders.map((w) => orderRowHTML(w, href)).join("") + "</div>";
}

function orderRowHTML(w, href) {
  return "<div class='as-order'>" +
    "<a class='as-order-door' href='" + esc(href) + "'>" + esc(w.id || "work order") + " →</a>" +
    "<span class='as-order-when'>" + esc(w.status || "open") +
      (w.date ? " · " + esc(w.date) : "") + "</span></div>";
}

// ZONE 3 — TOOLS: the assess form (anchor a finding to the STEP/PANEL) + the banked-edit door
// + manifest-only regen (arm-to-fire). Every verb inline; regen ARMS then BANKS.
function toolsZone(o) {
  const a = o.asset || {};
  const isFig = a.kind === "figure";
  const prod = a.producer || {};
  const editDoor = (prod.type && prod.type !== "none")
    ? "<a class='dk-act compose' href='" + esc(o.edit_href) + "'>edit the producer</a>" +
      infoTag("opens " + (prod.path || "the producer") + " in /artefact's editor · banking the edited " +
              "version onto the version spine is W8 — this door deep-links the source")
    : "<span class='dk-absent'>no producer — nothing to edit</span>";
  const regenBtn = o.regenable
    ? "<button type='button' class='dk-act destructive' id='as-regen'>regen · manifest-only</button>" +
      infoTag("POST /assets/regen → bank_work_order idiom (work_orders.jsonl) · The ruled default: " +
              "banks a work-order, the server spends no tokens (design §3)")
    : "<span class='dk-absent'>no producer — nothing to regen</span>";
  return "<div class='dk-tools'>" + editDoor + regenBtn + "</div>" +
    "<div class='dk-result as-msg' id='as-regen-msg'></div>" +
    "<div class='as-assess'>" +
      "<div class='dk-ref-k'>assess — anchor a finding to the " + (isFig ? "panel" : "step") +
        infoTag("POST /assets/assess → manuscript_bridge.feedback_add (the one finding writer the " +
                "artefact tray uses) · the asset anchor rides anchor.asset {asset_id, kind, step|panel}") + "</div>" +
      "<select id='as-anchor'>" + anchorOptions(o) + "</select>" +
      "<select id='as-kind'>" + _ASSESS_KINDS.map((k) => "<option value='" + k + "'>" + k + "</option>").join("") + "</select>" +
      "<textarea id='as-comment' rows='2' placeholder='what needs attention at this " +
        (isFig ? "panel" : "step") + "…'></textarea>" +
      "<button type='button' class='hy-door is-primary' id='as-bank'>bank finding</button>" +
      "<span class='as-msg' id='as-bank-msg'></span>" +
    "</div>";
}

function anchorOptions(o) {
  const a = o.asset || {};
  if (a.kind === "figure") {
    const panels = a.panels || [];
    return "<option value=''>whole figure</option>" +
      panels.map((p) => "<option value='" + esc(p.id) + "'>panel (" + esc(p.id) + ")</option>").join("");
  }
  const steps = a.steps || [];
  if (!steps.length) return "<option value=''>whole derivation</option>";
  return steps.map((s) => "<option value='" + esc(s.id) + "'>" + esc(s.id) + " · " +
    esc(s.kind) + " (L" + esc(s.line_start) + "–" + esc(s.line_end) + ")</option>").join("");
}

// ZONE 4 — DEEP-LINKS: each landing → the reader at its node; each supported node → the
// conceptric. measured/inferred honesty carried through (an inferred box says so). Declared
// absence where a project has no nodemap / no linked node.
function deeplinksZone(o) {
  const parts = [];
  const landings = o.landings || [];
  if (landings.length) {
    parts.push(landings.map((l) => "<a href='" + esc(l.href) + "'>landing p" +
      esc(l.page == null ? "?" : l.page) + " · " + esc(l.kind || "region") +
      (l.measured === false ? " (inferred)" : "") + " →</a>").join(""));
  } else {
    parts.push("<div class='dk-absent'>no landings — no nodemap for this project (its map is a banked work-order)</div>");
  }
  const nodes = o.nodes || [];
  if (nodes.length) {
    parts.push(nodes.map((n) => "<a href='" + esc(n.href) + "'>where " + esc(n.id) + " argues →</a>").join(""));
  } else {
    parts.push("<div class='dk-absent'>no supported node linked yet</div>");
  }
  return parts.join("");
}

// ZONE — FINDINGS: every banked finding on this asset (o.history), the just-banked one
// leading and briefly accented (the echo law — his anchored finding is visible where he
// looks). Each row leads with the worded anchor + kind, carries his comment verbatim, and
// a server-composed glance. The zone states the absence plainly when nothing is banked.
function findingsZone(o, freshId) {
  const hist = (o && o.history) || [];
  if (!hist.length)
    return "<div class='dk-absent'>no findings anchored to this asset yet — bank one above and it lands here</div>";
  return "<div class='as-finds'>" + hist.map((f) => findingRowHTML(f, freshId)).join("") + "</div>";
}

function findingRowHTML(f, freshId) {
  const fresh = freshId && f.id === freshId;
  const meta = [esc(f.by || "an author"), esc(f.date || "")].filter(Boolean).join(" · ");
  return "<div class='as-find" + (fresh ? " is-fresh" : "") + "' data-find='" + esc(f.id || "") + "'>" +
    "<div class='as-find-head'>" +
      "<span class='hy-chip'>" + esc(f.kind || "note") + "</span>" +
      "<span class='as-find-anchor'>" + esc(f.anchor || "") + "</span>" +
      "<span class='as-find-meta'>" + meta + "</span></div>" +
    "<div class='as-find-comment'>" + esc(f.comment || "") + "</div>" +
    (f.composed ? "<div class='as-find-composed'>" + esc(f.composed) + "</div>" : "") +
  "</div>";
}

// re-fetch the asset (its history + orders are the SAME read the cockpit built from) and
// re-render the findings zone with the just-banked row accented + scrolled into view. Re-
// fetch (not a client synthesis) so the echo is the ledger's truth, composed server-side.
async function refreshFindings(host, o, freshId) {
  let fresh;
  try { fresh = await store.fetchJSON("/assets/object", { params: { corpus: o.corpus, id: (o.asset || {}).id } }); }
  catch (_e) { return; }
  o.history = fresh.history || [];
  const body = $("#as-findings", host);
  if (!body) return;
  body.innerHTML = findingsZone(o, freshId);
  const row = freshId ? body.querySelector(".as-find.is-fresh") : null;
  if (row && row.scrollIntoView) row.scrollIntoView({ block: "nearest" });
}

// re-fetch the asset and re-render the CONSEQUENCES zone so a just-banked regen order
// joins the banked-orders list in place (the echo where he looks).
async function refreshOrders(host, o) {
  let fresh;
  try { fresh = await store.fetchJSON("/assets/object", { params: { corpus: o.corpus, id: (o.asset || {}).id } }); }
  catch (_e) { return; }
  o.orders = fresh.orders || [];
  o.orders_href = fresh.orders_href || o.orders_href;
  const body = $(".dk-conseq-body", host);
  if (body) body.innerHTML = consequencesZone(o);
}

// ── wiring: the assess bank + the manifest-only regen (arm-to-fire) ──────────────────────
function wireCockpit(host, o) {
  const bank = $("#as-bank", host);
  if (bank) bank.onclick = (e) => { e.stopPropagation(); bankAssess(host, o); };
  wireRegen(host, o);
}

async function bankAssess(host, o) {
  const a = o.asset || {};
  const isFig = a.kind === "figure";
  const anchorVal = ($("#as-anchor", host) || {}).value || "";
  const kind = ($("#as-kind", host) || {}).value || "note";
  const comment = (($("#as-comment", host) || {}).value || "").trim();
  const msg = $("#as-bank-msg", host);
  if (!comment) { msg.textContent = "a comment is required"; return; }
  // the ASSET ANCHOR (design §2): {asset_id, kind, step_id|panel_id} — additive, rides anchor.asset.
  const assetAnchor = { asset_id: a.id, kind: a.kind };
  if (isFig) { if (anchorVal) assetAnchor.panel_id = anchorVal; }
  else if (anchorVal) { assetAnchor.step_id = anchorVal; }
  // node_id: the supported node (a real conceptric id) when known, else the asset id itself —
  // feedback_add requires a node_id, and it must never be blank.
  const nodeId = (a.nodes_supported && a.nodes_supported[0]) || a.node_id || a.id;
  msg.textContent = "banking…";
  try {
    // actor law: the finding is attributed (the same author actor the desk composers use);
    // this door never defaults an actor silently.
    const res = await store.fetchJSON("/assets/assess", {
      method: "POST", params: { corpus: o.corpus },
      body: { node_id: nodeId, comment, kind, by: DESK_ACTOR, anchor: { asset: assetAnchor, section: "" } },
    });
    const recId = (res && res.record && res.record.id) || "";
    msg.textContent = "banked — it appears in the findings below";
    const ta = $("#as-comment", host); if (ta) ta.value = "";
    // the echo (echo law): the just-banked finding shows in the FINDINGS zone at once.
    await refreshFindings(host, o, recId);
  } catch (e) { msg.textContent = "bank failed: " + ((e && e.message) || e); }
}

function wireRegen(host, o) {
  const btn = $("#as-regen", host);
  if (!btn) return;
  const a = o.asset || {};
  // regen is manifest-only (the ruled default, design §3): arm-to-fire, then BANK one
  // work-order — the button says banked, the server spends no tokens.
  armToFire(btn, "regen · manifest-only",
    "banks a manifest-only work-order — a later session runs it",
    async () => {
      const msg = $("#as-regen-msg", host);
      msg.textContent = "banking…";
      try {
        const res = await store.fetchJSON("/assets/regen", {
          method: "POST", params: { corpus: o.corpus },
          body: { asset_id: a.id, producer: (a.producer && a.producer.path) || "", by: DESK_ACTOR },
        });
        btn.textContent = "banked ✓"; btn.disabled = true;
        const wo = res && res.work_order;
        const href = (o.orders_href || DESK_ORDERS_HREF);
        // gap 3: the banked order NAMES its door — the WO id is a link onto the work-orders
        // desk (where a later session carries it), never a dead id.
        msg.innerHTML = wo
          ? ("banked <a class='as-door' href='" + esc(href) + "'>" + esc(wo.id) +
             "</a> · manifest-only · fires next remote session")
          : "banked · fires next remote session";
        // the echo (echo law): the new order joins the consequences zone in place.
        await refreshOrders(host, o);
      } catch (e) { msg.textContent = "regen bank failed: " + ((e && e.message) || e); }
    });
}

// standalone hook (parity with the other pane modules) for smoke pages / harnesses.
if (typeof window !== "undefined") window.__assetsInit = initAssets;
