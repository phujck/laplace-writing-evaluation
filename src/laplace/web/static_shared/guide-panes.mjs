// guide-panes.mjs — The structural guide's renderer (W-guide).
//
// Renders /guide from GET /guide/data (the one read): the structural account of the engine
// (a), the surface census from the contract yamls (b), the session story (c), and the open
// promises (d). ESM, joined to store.mjs (the one fetch gateway) — no raw fetch escapes it.
//
// It DESCRIBES; it fires nothing. The one write door anywhere near it is the shell's shared
// "? rule" atom (draft-only), which this module does not touch.
import store from "/shared/store.mjs";

function esc(s){ return String(s == null ? "" : s)
  .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;"); }

// The PSU class named inside a verb's "does" line — so the card can chip it. We read the
// authored word, never invent one: local-safe -> local, model-heavy -> heavy, else none.
function psuOf(does){
  const d = String(does || "").toLowerCase();
  if(d.includes("model-heavy")) return {cls:"heavy", label:"model-heavy"};
  if(d.includes("local-safe"))  return {cls:"local", label:"local-safe"};
  return null;
}

function setHTML(id, html){ const el = document.getElementById(id); if(el) el.innerHTML = html; }

// ── (a) the structural account ──────────────────────────────────────────────
function renderEngine(engine){
  if(!engine) return;
  setHTML("gd-onething", esc(engine.one_thing || ""));

  const stages = engine.pipeline || [];
  setHTML("gd-pipe", stages.map(s => {
    const heavy = /heavy/i.test(s.cost || "");
    return "<div class='gd-stage'>"+
      "<div class='st-t'>"+esc(s.title || s.id)+"</div>"+
      "<div class='st-w'>"+esc(s.what || "")+"</div>"+
      (s.cost ? "<div class='st-cost"+(heavy ? " heavy" : "")+"'>"+esc(s.cost)+"</div>" : "")+
    "</div>";
  }).join("") || "<div class='dim'>no pipeline account.</div>");

  const gloss = engine.glossary || [];
  setHTML("gd-gloss", gloss.map(g =>
    "<div class='gd-term'><div class='tm'>"+esc(g.term)+"</div>"+
      "<div class='df'>"+esc(g.def)+"</div></div>"
  ).join("") || "<div class='dim'>no glossary.</div>");
}

// ── (b) the surface census, from the yamls ──────────────────────────────────
function verbCard(v){
  const does = v.does || "";
  const psu = psuOf(does);
  const nm = v.name || v.class || "verb";
  const cls = v.class && v.name ? (v.class + " · " + v.name) : nm;
  const state = v.state
    ? "<span class='gd-verb-state'>"+esc(v.state)+"</span>" : "";
  // Every surface now declares a "does" per verb (the desk/pipeline seam is backfilled).
  // The renderer still degrades cleanly if a future verb ever lands without one — it
  // states that plainly rather than inventing a line.
  const doesEl = does
    ? "<div class='gd-verb-does'>"+esc(does)+
        (psu ? " <span class='gd-psu "+psu.cls+"'>"+esc(psu.label)+"</span>" : "")+"</div>"
    : "<div class='gd-verb-does pending'>what this does is not yet declared for this verb.</div>";
  return "<div class='gd-verb'>"+
    "<div class='gd-verb-top'>"+
      "<span class='gd-verb-nm'>"+esc(cls)+"</span>"+
      (v.route ? "<span class='gd-verb-route'>"+esc(v.route)+"</span>" : "")+
      state+
    "</div>"+doesEl+
  "</div>";
}

function surfaceCard(s){
  const tag = s.in_roster
    ? (s.group === "more"
        ? "<span class='stag more'>more</span>"
        : (s.group === "primary" ? "<span class='stag'>primary</span>" : ""))
    : "<span class='stag engine'>engine view · off the nav</span>";
  const reads = (s.reads || []).length
    ? "<div class='gd-reads'>reads: "+s.reads.map(r =>
        "<span class='rd'>"+esc(r)+"</span>").join("")+"</div>"
    : "";
  let verbs;
  if(!s.declared){
    verbs = "<div class='gd-undeclared'>this surface has no contract file yet — its verbs are "+
      "not declared. (Nothing is asserted about what it writes.)</div>";
  } else if((s.verbs || []).length){
    verbs = "<div class='gd-verbs'>"+s.verbs.map(verbCard).join("")+"</div>";
  } else {
    verbs = "<div class='gd-noverbs'>read-only surface — no verb here writes anything.</div>";
  }
  return "<div class='gd-surf"+(s.in_roster ? "" : " notrostered")+"' id='guide-surf-"+esc(s.id)+"'>"+
    "<div class='gd-surf-h'>"+
      "<span class='snm'>"+esc(s.title || s.surface || s.id)+"</span>"+
      "<a class='spath' href='"+esc(s.path || ("/"+s.id))+"'>"+esc(s.path || ("/"+s.id))+"</a>"+
      tag+
    "</div>"+
    "<div class='gd-purpose'>"+esc(s.purpose || "")+"</div>"+
    reads+verbs+
  "</div>";
}

function renderSurfaces(surfaces){
  setHTML("gd-surfaces", (surfaces || []).map(surfaceCard).join("") ||
    "<div class='dim'>no surfaces declared.</div>");
}

// ── (c) the session story ───────────────────────────────────────────────────
function renderStory(story){
  setHTML("gd-story", (story || []).map(b =>
    "<div class='gd-beat'><div class='bt'>"+esc(b.title)+"</div>"+
      "<div class='bb'>"+esc(b.body)+"</div></div>"
  ).join("") || "<div class='dim'>no session story.</div>");
}

// A plain-words one-line summary of a promise's verbatim ask. The raw ask is his own
// words — often codename-laden, id-stamped, and shouted — which floods a stranger. This
// derives a calm one-liner for the row's face WITHOUT inventing meaning: it strips raw
// record/ruling ids, keeps the first sentence, de-shouts ALLCAPS runs, and trims. The
// exact ask is never lost — it rides verbatim behind the row's disclosure.
function plainSummary(ask){
  let s = String(ask == null ? "" : ask).trim();
  if(!s) return "(no ask recorded — see the row id)";
  // drop raw record/ruling ids shown mid-prose (PV-/RW-/PRM-/RM-/PRF-…)
  s = s.replace(/\b(?:PV|RW|PRM|RM|PRF)-[0-9A-Za-z._-]+/g, "").trim();
  // keep the first sentence when the ask runs long (a real stop past a short lead-in)
  const stop = s.search(/[.!?](?:\s|$)/);
  if(stop >= 24) s = s.slice(0, stop + 1);
  // de-shout a run of 2+ ALL-CAPS words to a calm sentence lead
  s = s.replace(/\b[A-Z]{2,}(?:[ -][A-Z]{2,})+\b/g,
    run => run.charAt(0) + run.slice(1).toLowerCase());
  // collapse whitespace + strip stray leading/trailing quote scaffolding
  s = s.replace(/\s+/g, " ").replace(/^['"“”‘’]+|['"“”‘’]+$/g, "").trim();
  const MAX = 160;
  if(s.length > MAX) s = s.slice(0, MAX - 1).replace(/\s+\S*$/, "") + "…";
  return s || "(see the exact ask below)";
}

// ── (d) the promises ledger ─────────────────────────────────────────────────
function renderPromises(promises){
  const p = promises || {};
  const c = p.counts || {open:0, eigen:0, his:0};
  setHTML("gd-prom-counts",
    "<span class='pc'><b>"+esc(c.open||0)+"</b> open</span>"+
    "<span class='pc'><b>"+esc(c.eigen||0)+"</b> the engine owes him</span>"+
    "<span class='pc'><b>"+esc(c.his||0)+"</b> he owes the engine</span>");
  const rows = p.open || [];
  setHTML("gd-promises", rows.length ? rows.map(r => {
    const dir = r.dir === "his" ? "his" : "eigen";
    const dirLabel = dir === "his" ? "his → engine" : "engine → him";
    const summary = plainSummary(r.ask);
    // the plain summary is the row's face; the verbatim ask (his words) rides behind a
    // plainly-labelled disclosure, so nothing is hidden and nobody is flooded by default.
    const ask = String(r.ask == null ? "" : r.ask).trim();
    const askDisclosure = ask
      ? "<details class='gd-prom-more' style='margin-top:5px'>"+
          "<summary style='font-size:10.5px;color:var(--dim);cursor:pointer'>"+
            "the exact ask — his words, verbatim</summary>"+
          "<div class='gd-prom-ask' style='margin-top:5px;padding-left:9px;"+
            "border-left:2px solid var(--edge2);white-space:pre-wrap'>"+esc(ask)+"</div>"+
        "</details>"
      : "";
    return "<div class='gd-prom "+dir+"'>"+
      "<div class='gd-prom-h'>"+
        "<span class='pid'>"+esc(r.id)+"</span>"+
        "<span class='pdir "+dir+"'>"+esc(dirLabel)+"</span>"+
        (r.date ? "<span class='pdate'>"+esc(r.date)+"</span>" : "")+
      "</div>"+
      "<div class='gd-prom-sum'>"+esc(summary)+"</div>"+
      askDisclosure+
      (r.owner ? "<div class='gd-prom-owner'>owner: <b>"+esc(r.owner)+"</b></div>" : "")+
    "</div>";
  }).join("") : "<div class='dim'>no open promises — the ledger is clear.</div>");
}

// ── boot ────────────────────────────────────────────────────────────────────
export async function initGuide(){
  let data;
  try{
    data = await store.fetchJSON("/guide/data");
  }catch(e){
    const msg = "<div class='err'>the guide could not load its data ("+esc(String(e && e.message || e))+
      "). This page describes; it fires nothing — reload when the server is up.</div>";
    setHTML("gd-onething", msg);
    ["gd-pipe","gd-gloss","gd-surfaces","gd-story","gd-promises"].forEach(id => setHTML(id, ""));
    return;
  }
  renderEngine(data.engine);
  renderSurfaces(data.surfaces);
  renderStory(data.session_story);
  renderPromises(data.promises);
}

export default { initGuide };
