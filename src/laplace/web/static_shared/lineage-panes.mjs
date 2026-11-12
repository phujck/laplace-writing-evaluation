// lineage-panes.mjs — the lineage surface's renderer (W-lineage).
//
// Per-project views of the conceptric and its descendants, joined to the one instrument
// (engine.mjs). The resting DOM is a COMPOSED BRIEF of the paper's lineage health (GET
// /lineage/brief); nothing is materialised until a picker or a cold deep-link summons a
// view. Opening a node / object / the whole graph REALLOCATES through engine.mjs (the view
// claims the centre, its identity becomes a rail, a named return door leads back to the
// brief); closing restores the brief exactly. ESM, joined to store.mjs (the one fetch
// gateway) + engine.mjs — no raw fetch escapes.
//
// The register: a row leads with the term or a composed label; the raw id rides as a small
// mono tail chip (.lin-id), never as the sentence. Colour is meaning only where load-bearing
// (the unresolved band wears the warn hue); everything else is the working gold on midnight.
import store from "/shared/store.mjs";
import { injectEngineCSS, createFocusState, HighlightBus, Reallocator } from "/shared/engine.mjs";

function esc(s){ return String(s == null ? "" : s)
  .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;"); }
const ec = encodeURIComponent;

// the brief glance carries the goal's inline $…$ verbatim (the same prose the growth cockpit
// serves; audit depth keeps the raw string). Render it through the shell's one KaTeX fence —
// the same auto-render the editor uses (conservative delimiters, throwOnError:false → a
// plain-text fallback where katex cannot parse). A no-op if the shell has not booted; each
// view replaces its glance whole on render, so one pass never double-renders.
function paintMath(el){ try{ if(el && window.renderMath) window.renderMath(el); }catch(_e){ /* math is a bonus, never a blocker */ } }

// component styles this surface owns (the hymn owner holds hymn.css; these ride the same
// tokens so a shared input family / zero law lands consistent, never fought). Injected once.
const LIN_CSS = `
/* the unresolved band — thin token dividers between the bits (they ran together on bare
   whitespace). A middot separator, a warn-tinted token, wraps with the bits it parts. */
.lin-banddiv{color:color-mix(in srgb,var(--warn) 55%,var(--dim));font-size:12px;
  user-select:none;margin:0 -2px}
/* the PROJECT switch — appearance:none so no OS-native chrome leaks; a token caret, the
   panel/edge tokens the hymn input family shares (var()-based, so the shared family lands
   consistent). An additive class beside .lin-switch-sel, fully owned here. */
.lin-sel{appearance:none;-webkit-appearance:none;
  background-image:linear-gradient(45deg,transparent 50%,var(--dim) 50%),
    linear-gradient(135deg,var(--dim) 50%,transparent 50%);
  background-position:calc(100% - 15px) center,calc(100% - 11px) center;
  background-size:4px 4px,4px 4px;background-repeat:no-repeat;
  padding-right:30px}
.lin-sel:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
`;
function injectLinCSS(){
  if(typeof document === "undefined" || document.getElementById("lin-components")) return;
  const st = document.createElement("style"); st.id = "lin-components"; st.textContent = LIN_CSS;
  document.head.appendChild(st);
}

let CORPUS = "";
let REAL = null;          // the Reallocator (built once)
let ROOT = null;          // #eng-root
let ROSTER = null;       // the project roster (GET /corpus/list), lazy — the switch's options

// ── URL selection (node / object / view) — managed here so a reload or a cold deep-link
//    re-focuses. The corpus rides store.mjs (the shell reads it); node/object/view are this
//    surface's own params, written without disturbing the corpus. Picking around inside one
//    open view (node ⇄ object ⇄ whole) REPLACES — those aren't destinations worth a back-stop
//    entry each. Leaving a view for the brief PUSHES (pushURL, wired at the close override in
//    initLineage): a real navigation, not a silent overwrite of the entry a cold deep-link
//    landed on, so the browser's own Back button still finds the view it left. ─────────────
function setURL(patch){
  const u = new URL(location.href);
  for(const [k, v] of Object.entries(patch)){
    if(v == null || v === "") u.searchParams.delete(k); else u.searchParams.set(k, v);
  }
  history.replaceState(history.state, "", u.pathname + u.search);
}
function pushURL(patch){
  const u = new URL(location.href);
  for(const [k, v] of Object.entries(patch)){
    if(v == null || v === "") u.searchParams.delete(k); else u.searchParams.set(k, v);
  }
  history.pushState(history.state, "", u.pathname + u.search);
}
function urlParam(k){ return new URLSearchParams(location.search).get(k) || ""; }

// ── the id chip (the register: label leads, id is the mono tail) ────────────────────────
function idChip(id){ return "<span class='lin-id'>" + esc(id) + "</span>"; }
function provChip(list){
  return (list || []).map(p => "<span class='lin-prov'>" + esc(p) + "</span>").join("");
}

// ═══════════════════════════════════════════════════════════════════════════════════════
// THE BRIEF (the base altitude)
// ═══════════════════════════════════════════════════════════════════════════════════════
async function renderBrief(){
  const brief = ROOT.querySelector(".eng-brief");
  if(!brief) return;
  await loadCorpora();
  let data;
  try{ data = await store.fetchJSON("/lineage/brief"); }
  catch(e){
    brief.innerHTML = switchHTML() + "<div class='lin-err'>the lineage brief could not load ("
      + esc(String(e && e.message || e)) + "). This surface reads; reload when the server is up.</div>";
    wireSwitch(brief);
    return;
  }
  if(!data.present){
    brief.innerHTML = switchHTML() + briefEmpty(data);
    wireSwitch(brief);
    return;
  }
  const c = data.counts || {};
  const counts = [
    ["concepts", c.concepts], ["realised into the paper", c.realised],
    ["rendered objects", c.rendered], ["trace their origin", c.resolved],
    ["equations resolved", (c.equations_resolved || 0) + " / " + (c.equations || 0)],
    ["unresolved", c.unresolved],
  ].map(([label, val]) => "<span class='lin-chip'><b>" + esc(val) + "</b>" + esc(label) + "</span>").join("");

  const band = (data.band || []).map(b =>
    "<span class='lin-bandbit'><b>" + esc(b.n) + "</b> " + esc(b.reason) + "</span>")
    .join("<span class='lin-banddiv' aria-hidden='true'>·</span>");

  brief.innerHTML =
    switchHTML() +
    "<div class='lin-glance' data-role='brief-prose'>" + esc(data.glance) + "</div>" +
    "<div class='lin-counts'>" + counts + "</div>" +
    (band ? "<div class='lin-band'><span class='lin-band-h'>the unresolved band</span>" + band + "</div>" : "") +
    staleNote(data.staleness, data.remint) +
    "<div class='lin-pickers'>" +
      "<div class='lin-picker' id='lin-pick-node'>" +
        "<div class='lin-picker-h'>a concept, outward</div>" +
        "<div class='lin-picker-sub'>pick a concept and see everything it became</div>" +
        "<input class='lin-find-input' id='lin-find-node' autocomplete='off' spellcheck='false' placeholder='find a concept…'>" +
        "<div class='lin-find-list' id='lin-list-node'></div>" +
      "</div>" +
      "<div class='lin-picker' id='lin-pick-obj'>" +
        "<div class='lin-picker-h'>a rendered object, backward</div>" +
        "<div class='lin-picker-sub'>pick an equation, figure, or derivation and walk back to its origin</div>" +
        "<input class='lin-find-input' id='lin-find-obj' autocomplete='off' spellcheck='false' placeholder='find an object…'>" +
        "<div class='lin-find-list' id='lin-list-obj'></div>" +
      "</div>" +
      "<div class='lin-picker lin-picker-whole' id='lin-pick-whole'>" +
        "<div class='lin-picker-h'>the whole graph</div>" +
        "<div class='lin-picker-sub'>the sections as regions weighted by realisation, and the unresolved band as its own region</div>" +
        "<button type='button' class='lin-door lin-door-whole' id='lin-open-whole'>see the whole picture →</button>" +
      "</div>" +
    "</div>";

  wireSwitch(brief);
  paintMath(brief.querySelector(".lin-glance[data-role='brief-prose']"));
  wireFinder("lin-find-node", "lin-list-node", "concepts");
  wireFinder("lin-find-obj", "lin-list-obj", "objects");
  const wb = brief.querySelector("#lin-open-whole");
  if(wb) wb.addEventListener("click", () => openWhole());
  const rb = brief.querySelector("#lin-remint");
  if(rb) rb.addEventListener("click", () => remint(rb));
}

// ── the project switch (gap 5): any project's lineage opens from the brief. The roster is
// GET /corpus/list (the same door the chrome's quick-switch reads); switching threads the
// new ?corpus= through every door and drops the view params, so a cold ?corpus=&node= deep
// link still lands the same. Distinct class from .lin-picker (the three view pickers). ──────
async function loadCorpora(){
  if(ROSTER) return ROSTER;
  try{
    const r = await store.fetchJSON("/corpus/list", { inject: [] });
    ROSTER = (r && r.corpora) || [];
  }catch(e){ ROSTER = []; }
  return ROSTER;
}
function switchHTML(){
  const list = ROSTER && ROSTER.length ? ROSTER.slice() : (CORPUS ? [CORPUS] : []);
  if(CORPUS && !list.includes(CORPUS)) list.unshift(CORPUS);
  const opts = list.map(c =>
    "<option value='" + esc(c) + "'" + (c === CORPUS ? " selected" : "") + ">" + esc(c) + "</option>").join("");
  return "<div class='lin-switch' id='lin-switch'>" +
    "<span class='lin-switch-l'>project</span>" +
    "<select class='lin-switch-sel lin-sel' id='lin-switch-sel' title='open another project’s lineage'>" + opts + "</select>" +
    "</div>";
}
function wireSwitch(root){
  const sel = (root || document).querySelector("#lin-switch-sel");
  if(!sel) return;
  sel.addEventListener("change", () => switchProject(sel.value));
}
// switch which project's lineage this surface reads: set the corpus, drop the view params
// (a node/object token is scoped to the project it was picked in), and navigate — the same
// idiom the chrome's quick-switch uses (keep the surface, change WHICH paper is in view).
function switchProject(c){
  if(!c || c === CORPUS) return;
  const u = new URL(location.href);
  u.searchParams.set("corpus", c);
  for(const k of ["node", "object", "view"]) u.searchParams.delete(k);
  location.href = u.pathname + u.search;
}

function briefEmpty(data){
  const e = data.empty || {};
  const shows = (e.what_it_would_show || []).map(s => "<li>" + esc(s) + "</li>").join("");
  return "<div class='lin-glance' data-role='brief-prose'>" + esc(data.glance) + "</div>" +
    "<div class='lin-empty'>" +
      "<div class='lin-empty-h'>what this surface would show</div>" +
      "<ul class='lin-empty-list'>" + shows + "</ul>" +
      "<div class='lin-empty-build'>" + esc(e.what_builds_it || "") + "</div>" +
    "</div>";
}

// the staleness note in place — its own small idiom (the surface reads; the note offers the
// re-mint door but never fires it silently).
function staleNote(st, remint){
  if(!st) return "";
  if(st.fresh) return "<div class='lin-stale is-fresh'><b class='lin-stale-dot'></b>the index matches its sources</div>";
  const remintBtn = remint
    ? "<button type='button' class='lin-door lin-remint' id='lin-remint' title='" + esc(remint.writes) + "'>"
      + esc(remint.label || "re-mint the index") + "</button>"
    : "";
  return "<div class='lin-stale is-stale'>" +
    "<span class='lin-stale-badge'>stale</span>" +
    "<span class='lin-stale-msg'>" + esc(st.reason || "the index is older than its sources") + "</span>" +
    remintBtn + "</div>";
}

async function remint(btn){
  btn.disabled = true; const was = btn.textContent; btn.textContent = "re-minting…";
  try{
    await store.fetchJSON("/lineage/reindex", { method: "POST", body: {} });
    await renderBrief();
  }catch(e){ btn.disabled = false; btn.textContent = was; }
}

// ── the finder (the brief's pickers) ────────────────────────────────────────────────────
function wireFinder(inputId, listId, side){
  const inp = document.getElementById(inputId);
  const list = document.getElementById(listId);
  if(!inp || !list) return;
  let t = null;
  const run = async () => {
    let data;
    try{ data = await store.fetchJSON("/lineage/find", { params: { q: inp.value.trim() } }); }
    catch(e){ list.innerHTML = ""; return; }
    const rows = side === "concepts" ? (data.concepts || []) : (data.objects || []);
    if(!rows.length){ list.innerHTML = "<div class='lin-find-none'>no match</div>"; return; }
    list.innerHTML = rows.slice(0, 18).map(r => {
      if(side === "concepts"){
        const lead = r.label ? r.label.split(/[.;(]/)[0].trim().slice(0, 70) : r.id;
        const meta = (r.kind ? esc(r.kind) : "") + (r.realises ? " · realises " + r.realises : "");
        return "<button type='button' class='lin-find-row' data-id='" + esc(r.id) + "' data-side='concepts'>" +
          "<span class='lin-find-lead'>" + esc(lead || r.id) + "</span>" +
          "<span class='lin-find-meta'>" + meta + "</span>" + idChip(r.id) + "</button>";
      }
      const rez = r.resolved ? "traces its origin" : "unresolved";
      return "<button type='button' class='lin-find-row" + (r.resolved ? "" : " is-unres") +
        "' data-id='" + esc(r.id) + "' data-side='objects'>" +
        "<span class='lin-find-lead'>" + esc(r.kind || "object") + (r.page ? " · page " + esc(r.page) : "") + "</span>" +
        "<span class='lin-find-meta'>" + esc(rez) + "</span>" + idChip(r.id) + "</button>";
    }).join("");
    list.querySelectorAll(".lin-find-row").forEach(el => el.addEventListener("click", () => {
      if(el.dataset.side === "concepts") openNode(el.dataset.id); else openObject(el.dataset.id);
    }));
  };
  inp.addEventListener("input", () => { clearTimeout(t); t = setTimeout(run, 150); });
  inp.addEventListener("focus", () => { if(!list.children.length) run(); });
}

// ═══════════════════════════════════════════════════════════════════════════════════════
// NODE-OUTWARD — a concept and everything it became
// ═══════════════════════════════════════════════════════════════════════════════════════
async function openNode(nid){
  setURL({ node: nid, object: null, view: null });
  let data;
  try{ data = await store.fetchJSON("/lineage/node", { params: { node: nid } }); }
  catch(e){ pinMessage("this concept", "The concept could not be resolved — " + esc(String(e && e.message || e))); return; }
  if(!data.present){ pinMessage(nid, esc(data.glance || "no lineage for this concept")); return; }
  const idn = data.identity || {};
  const title = (idn.label ? idn.label.split(/[.;(]/)[0].trim().slice(0, 60) : nid) || nid;

  REAL.pin("node:" + nid, {
    title: title,
    destination: "the lineage brief",
    buildRail: (rail) => { rail.innerHTML = nodeRail(data); },
    buildFocus: (focus) => {
      const view = document.createElement("div");
      view.className = "lin-view";
      view.innerHTML = nodeView(data);
      focus.appendChild(view);
      paintMath(view);
      wireNodeCrossings(view, data);
    },
  });
}

function nodeRail(data){
  const idn = data.identity || {};
  const d = data.descendants || {};
  const r = data.realises || {};
  const counts = [
    ["descendants", d.n || 0],
    ["paragraphs", (r.paragraphs || []).length],
    ["equations", (r.equations || []).length],
    ["sections", (d.sections || []).length],
  ].map(([l, v]) => "<div class='lin-rail-count'><b>" + esc(v) + "</b>" + esc(l) + "</div>").join("");
  return "<div class='eng-railblock'><h5>concept</h5>" +
      "<div class='lin-rail-id'>" + esc(idn.label ? idn.label.slice(0, 90) : idn.id) + "</div>" +
      "<div class='lin-rail-chips'>" + (idn.kind ? "<span class='lin-kind'>" + esc(idn.kind) + "</span>" : "") +
        idChip(idn.id) + "</div>" +
      (idn.section_title ? "<div class='lin-rail-sec'>carried in " + esc(idn.section_title) + "</div>" : "") +
    "</div>" +
    "<div class='eng-railblock'><h5>reach</h5><div class='lin-rail-counts'>" + counts + "</div></div>" +
    "<div class='eng-railblock'><h5>crossings</h5>" + doorsRow(data.doors) + "</div>";
}

function doorsRow(doors){
  const d = doors || {};
  const out = [];
  if(d.editor) out.push("<a class='lin-door' href='" + esc(d.editor.href) + "'>" + esc(d.editor.label) + " →</a>");
  if(d.grow) out.push("<a class='lin-door' href='" + esc(d.grow.href) + "'>" + esc(d.grow.label) + " →</a>");
  if(d.node_outward) out.push("<button type='button' class='lin-door' data-cross-node='" + esc(d.node_outward.id) + "'>" + esc(d.node_outward.label) + " →</button>");
  return "<div class='lin-doors'>" + out.join("") + "</div>";
}

function nodeView(data){
  const d = data.descendants || {};
  const r = data.realises || {};
  let html = "<div class='lin-view-glance' data-role='brief-prose'>" + esc(data.glance) + "</div>";

  // the objects that realise it — paragraphs, equations, the asset, each with join provenance
  const paras = (r.paragraphs || []).map(p =>
    "<div class='lin-para'>" +
      "<div class='lin-para-h'>" + esc(p.function || "a paragraph") + idChip(p.id) + "</div>" +
      (p.proposition ? "<div class='lin-para-prop'>" + esc(p.proposition) + "</div>" : "") +
      "<div class='lin-prov-row'>" + provChip(p.provenance) + "</div>" +
    "</div>").join("");
  const eqs = (r.equations || []).map(e =>
    "<div class='lin-eq'>" +
      "<div class='lin-eq-h'>" + (e.origin ? esc(e.origin) : "an equation") + idChip(e.id) +
        (e.join ? "<span class='lin-join'>" + esc(e.join) + "</span>" : "") + "</div>" +
      "<div class='lin-prov-row'>" + provChip(e.provenance) + "</div>" +
    "</div>").join("");
  const asset = r.asset
    ? "<div class='lin-asset'><div class='lin-eq-h'>" + esc(r.asset.kind) + idChip(r.asset.id) +
        (r.asset.join ? "<span class='lin-join'>" + esc(r.asset.join) + "</span>" : "") + "</div>" +
        "<div class='lin-prov-row'>" + provChip(r.asset.provenance) + "</div></div>"
    : "";
  const realiseBody = (paras || eqs || asset)
    ? paras + eqs + asset
    : "<div class='lin-dim'>Nothing in the manuscript realises this concept directly yet — its reach is its descendants below.</div>";
  html += "<div class='lin-sec'><h5>realises into the manuscript</h5>" + realiseBody + "</div>";

  // the descendants tree — relation-labelled edges, evidence one act deep
  if(d.n){
    html += "<div class='lin-sec'><h5>descendants — " + esc(d.n) + " below</h5>" +
      "<div class='lin-tree'>" + treeChildren(d.tree) + "</div>";
    const health = d.health || {};
    if((health.cycles_blocked || []).length)
      html += "<div class='lin-tree-note'>" + esc(health.cycles_blocked.length) +
        " back-edge(s) blocked (the graph is authored, not proven acyclic)</div>";
    html += "</div>";
  }

  // sections it touches
  if((d.sections || []).length){
    html += "<div class='lin-sec'><h5>sections it touches</h5><div class='lin-sections'>" +
      d.sections.map(s => "<span class='lin-secchip'>" + esc(s.title) + "</span>").join("") +
      "</div></div>";
  }

  html += "<div class='lin-sec'><h5>crossings</h5>" + doorsRow(data.doors) + "</div>";
  return html;
}

// the tree's children, rendered nested (each edge carries its relation + evidence). A child
// node is itself a crossing — clicking it opens node-outward on it (in-place switch).
function treeChildren(tree){
  const kids = (tree && tree.children) || [];
  if(!kids.length) return "";
  return "<ul class='lin-treelist'>" + kids.map(ch => {
    const lead = ch.label ? ch.label.split(/[.;(]/)[0].trim().slice(0, 64) : ch.id;
    const rel = ch.rel ? "<span class='lin-rel'>" + esc(ch.rel) + "</span>" : "";
    const ev = ch.evidence ? "<span class='lin-ev'>" + esc(String(ch.evidence).slice(0, 90)) + "</span>" : "";
    return "<li class='lin-tree-node'>" +
      "<button type='button' class='lin-tree-open' data-cross-node='" + esc(ch.id) + "'>" +
        rel + "<span class='lin-tree-lead'>" + esc(lead || ch.id) + "</span>" + idChip(ch.id) + "</button>" +
      ev + treeChildren(ch) + "</li>";
  }).join("") + "</ul>";
}

function wireNodeCrossings(view, data){
  view.querySelectorAll("[data-cross-node]").forEach(el =>
    el.addEventListener("click", (e) => { e.preventDefault(); openNode(el.dataset.crossNode); }));
}

// ═══════════════════════════════════════════════════════════════════════════════════════
// OBJECT-BACKWARD — a rendered object walked back through its chain
// ═══════════════════════════════════════════════════════════════════════════════════════
async function openObject(oid){
  setURL({ object: oid, node: null, view: null });
  let data;
  try{ data = await store.fetchJSON("/lineage/object", { params: { object: oid } }); }
  catch(e){ pinMessage(oid, "This object could not be walked back — " + esc(String(e && e.message || e))); return; }
  if(!data.resolved){ pinMessage(oid, esc(data.glance || "nothing resolves this object")); return; }

  REAL.pin("object:" + oid, {
    title: oid,
    destination: "the lineage brief",
    buildRail: (rail) => { rail.innerHTML = objectRail(data); },
    buildFocus: (focus) => {
      const view = document.createElement("div");
      view.className = "lin-view";
      view.innerHTML = objectView(data);
      focus.appendChild(view);
      paintMath(view);
      view.querySelectorAll("[data-cross-node]").forEach(el =>
        el.addEventListener("click", (e) => { e.preventDefault(); openNode(el.dataset.crossNode); }));
    },
  });
}

function objectRail(data){
  return "<div class='eng-railblock'><h5>rendered object</h5>" +
      "<div class='lin-rail-chips'>" + idChip(data.object) +
        (data.join ? "<span class='lin-join'>" + esc(data.join) + " join</span>" : "") + "</div>" +
    "</div>" +
    "<div class='eng-railblock'><h5>how it resolves</h5><div class='lin-prov-row'>" +
      provChip(data.join_provenance) + "</div></div>" +
    "<div class='eng-railblock'><h5>crossings</h5>" + doorsRow(data.doors) + "</div>";
}

function objectView(data){
  let html = "<div class='lin-view-glance' data-role='brief-prose'>" + esc(data.glance) + "</div>";
  const steps = (data.steps || []).map((s, i) => {
    const cross = (s.stage === "concept" && s.id)
      ? "<button type='button' class='lin-step-cross' data-cross-node='" + esc(s.id) + "'>see it outward →</button>" : "";
    const lead = s.label ? String(s.label).split(/[.;(]/)[0].trim().slice(0, 72) : s.stage;
    return "<div class='lin-step lin-stage-" + esc(s.stage) + "'>" +
      "<div class='lin-step-badge'>" + esc(s.stage) + "</div>" +
      "<div class='lin-step-body'>" +
        "<div class='lin-step-lead'>" + esc(lead || "") +
          (s.label && (s.stage === "object" || s.stage === "paragraph") ? idChip(s.label) : "") + "</div>" +
        (s.detail ? "<div class='lin-step-detail'>" + esc(s.detail) + "</div>" : "") +
        (s.note ? "<div class='lin-step-note'>" + esc(s.note) + "</div>" : "") + cross +
      "</div>" +
    "</div>" + (i < data.steps.length - 1 ? "<div class='lin-step-link' aria-hidden='true'>↑</div>" : "");
  }).join("");
  html += "<div class='lin-sec'><h5>walked back to its origin</h5><div class='lin-walk'>" + steps + "</div></div>";
  html += "<div class='lin-sec'><h5>crossings</h5>" + doorsRow(data.doors) + "</div>";
  return html;
}

// ═══════════════════════════════════════════════════════════════════════════════════════
// THE WHOLE — the graph at a coarse altitude: regions weighted, the unresolved band
// ═══════════════════════════════════════════════════════════════════════════════════════
async function openWhole(){
  setURL({ view: "whole", node: null, object: null });
  let data;
  try{ data = await store.fetchJSON("/lineage/whole"); }
  catch(e){ pinMessage("the whole graph", "The whole picture could not load — " + esc(String(e && e.message || e))); return; }

  REAL.pin("whole", {
    title: "the whole graph",
    destination: "the lineage brief",
    buildRail: (rail) => {
      const c = data.counts || {};
      rail.innerHTML = "<div class='eng-railblock'><h5>the graph</h5>" +
        "<div class='lin-rail-counts'>" +
          "<div class='lin-rail-count'><b>" + esc(c.concepts || 0) + "</b>concepts</div>" +
          "<div class='lin-rail-count'><b>" + esc(c.objects || 0) + "</b>objects</div>" +
          "<div class='lin-rail-count'><b>" + esc((data.regions || []).filter(r => r.id).length) + "</b>regions</div>" +
          "<div class='lin-rail-count'><b>" + esc((data.unresolved || {}).n || 0) + "</b>unresolved</div>" +
        "</div></div>";
    },
    buildFocus: (focus) => {
      const view = document.createElement("div");
      view.className = "lin-view";
      view.innerHTML = wholeView(data);
      focus.appendChild(view);
      paintMath(view);
      view.querySelectorAll("[data-cross-obj]").forEach(el =>
        el.addEventListener("click", (e) => { e.preventDefault(); openObject(el.dataset.crossObj); }));
    },
  });
}

function wholeView(data){
  let html = "<div class='lin-view-glance' data-role='brief-prose'>" + esc(data.glance) + "</div>";
  const regions = (data.regions || []).map(r => {
    const w = Math.round((r.weight_frac || 0) * 100);
    return "<div class='lin-region" + (r.id ? "" : " is-unplaced") + "'>" +
      "<div class='lin-region-h'>" + esc(r.title) + "</div>" +
      "<div class='lin-weight'><span class='lin-weight-fill' style='width:" + w + "%'></span></div>" +
      "<div class='lin-region-counts'>" +
        "<span>" + esc(r.concepts) + " concepts</span>" +
        "<span>" + esc(r.realised) + " realise</span>" +
        "<span>" + esc(r.objects) + " objects</span>" +
      "</div></div>";
  }).join("");
  html += "<div class='lin-sec'><h5>the regions — weighted by what realises in each</h5>" +
    "<div class='lin-regions'>" + regions + "</div></div>";

  // the unresolved band — its own region, absence made a first-class citizen
  const u = data.unresolved || {};
  const groups = (u.groups || []).map(g =>
    "<div class='lin-ur-group'>" +
      "<div class='lin-ur-h'><b>" + esc(g.n) + "</b> " + esc(g.kind) + " — " + esc(g.reason) + "</div>" +
      "<div class='lin-ur-samples'>" + (g.sample || []).map(s =>
        "<button type='button' class='lin-ur-chip' data-cross-obj='" + esc(s) + "'>" + esc(s) + "</button>").join("") +
      "</div></div>").join("");
  html += "<div class='lin-sec lin-unresolved'>" +
    "<h5>the unresolved band — " + esc(u.n || 0) + " objects the graph does not yet place</h5>" +
    groups + "</div>";
  return html;
}

// a plain message pin (an unresolved deep-link, a failed fetch) — still a real focus with a
// return door, never a dead wall.
function pinMessage(title, msg){
  REAL.pin("msg", {
    title: title, destination: "the lineage brief",
    buildRail: (rail) => { rail.innerHTML = "<div class='eng-railblock'><h5>nothing resolved</h5></div>"; },
    buildFocus: (focus) => {
      const d = document.createElement("div");
      d.className = "lin-view lin-msg";
      d.innerHTML = "<div class='lin-view-glance'>" + msg + "</div>";
      focus.appendChild(d);
    },
  });
}

// ═══════════════════════════════════════════════════════════════════════════════════════
// boot
// ═══════════════════════════════════════════════════════════════════════════════════════
export async function initLineage(){
  injectEngineCSS();
  injectLinCSS();
  ROOT = document.getElementById("eng-root");
  if(!ROOT) return;
  // a default project so the surface is never a dead corpus-less page (the shell switch
  // changes it); paper_falqon is the folded reference paper.
  if(!store.field("corpus")) store.set({ corpus: "paper_falqon" }, { replace: true });
  CORPUS = store.field("corpus");

  const state = createFocusState("brief");
  const bus = new HighlightBus(ROOT);
  REAL = new Reallocator(ROOT, state, bus);
  // closing a view returns to the brief AND drops the view from the URL — PUSHED, not
  // replaced: a cold deep-link (?object=eq:coh-total from the editor's "see it across the
  // map" door) lands on a real, already-existing history entry, and replacing it on close
  // would silently erase that entry, breaking the browser's own Back button. Pushing the
  // brief as a new entry leaves the view one step back, where Back (popstate, below) finds
  // and re-opens it.
  const origClose = REAL.close.bind(REAL);
  REAL.close = () => { origClose(); pushURL({ node: null, object: null, view: null }); };

  await renderBrief();

  // A cold deep-link — an arrival with ?node= / ?object= / ?view=whole lands pre-focused on
  // that view (the editor sibling's "see it on the map" door lands ?object=). The shell's
  // own arrival echo names where the landing came from; this pins the view it declares.
  // Reused on popstate — Back/Forward through the brief <-> view stack replays the URL's
  // params, closing DOM-only (origClose, no further history write; we already sit on the
  // entry the browser navigated to).
  const openFromURL = () => {
    const node = urlParam("node"), object = urlParam("object"), view = urlParam("view");
    if(object) openObject(object);
    else if(node) openNode(node);
    else if(view === "whole") openWhole();
    else if(REAL.pinned) origClose();
  };
  window.addEventListener("popstate", openFromURL);
  openFromURL();
}

export default { initLineage };
