// run-tray.mjs — The shared run panel (W6), lifted so ONE implementation serves both
// the storyboard's run pane AND the pipeline board's converge organ (conception §7:
// "the run panel's live state joins both this surface and the storyboard's run pane").
//
// It renders the run's LIVE STATE (phase/rounds/artifacts — pure reads over the run's
// own artifacts on disk), the open work orders (banked model-heavy launches awaiting a
// later session), and the SCOPED LAUNCH controls (from storyboard.launch_roster). Every
// fire-class control renders a DRY-RUN "what would fire" preview FIRST (the pure-read
// propagate worklist) and fires NOTHING until it is armed (arm-to-fire; the offer law
// made visible: model-heavy BANKS a work-order and the button says "banked").
//
// Reuses armToFire from desk-panes.mjs (the one arm-to-fire idiom) and store.fetchJSON
// (the one gateway); no raw fetch, no color literal (the one-palette clause).

import store from "/shared/store.mjs";
import { armToFire } from "/shared/desk-panes.mjs";

const esc = (s) => String(s == null ? "" : s)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
  .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

// layout-only CSS, injected once (idempotent); every color is a hymn var (§6.1).
const RT_CSS = `
.rt-state{display:flex;flex-wrap:wrap;gap:5px;align-items:center;margin-bottom:6px}
.rt-note{font-family:var(--mono);font-size:10.5px;color:var(--ink2);margin:4px 0}
.rt-note b{color:var(--ink)}
.rt-dim{color:var(--dim)}
.rt-warn{color:var(--warn)}
.rt-conv{margin:8px 0;padding:7px 9px;border:1px solid var(--edge);border-left:3px solid var(--teal);
  border-radius:7px;background:var(--bg)}
.rt-conv-h{font-size:9.5px;text-transform:uppercase;letter-spacing:.08em;color:var(--dim);font-weight:700;margin-bottom:4px}
.rt-arts{margin:8px 0;display:flex;flex-direction:column;gap:3px}
.rt-art{display:flex;gap:8px;font-family:var(--mono);font-size:9.5px}
.rt-art .ak{flex:none;color:var(--teal);width:92px}
.rt-art .ap{color:var(--dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rt-wos{margin:9px 0 4px}
.rt-wo-h{font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:var(--dim);font-weight:700;margin-bottom:5px}
.rt-wo-h b{font-family:var(--mono);color:var(--ink2)}
.rt-wo{display:flex;align-items:center;gap:6px;padding:5px 7px;border:1px solid var(--edge);
  border-left:3px solid var(--warn);border-radius:6px;margin-bottom:4px;background:var(--bg);font-size:10px}
.rt-wo-what{flex:1;min-width:0;color:var(--ink2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rt-wo-id{font-family:var(--mono);font-size:8.5px;color:var(--dim)}
.rt-wo-new{border-left-color:var(--teal);background:var(--panel2)}
.rt-sec{margin:9px 0 4px}
.rt-slab{font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:var(--dim);font-weight:700;margin-bottom:5px}
.rt-launches{display:flex;flex-wrap:wrap;gap:6px}
.rt-ctrl{display:flex;flex-direction:column;gap:4px;min-width:0}
.rt-dry{margin:2px 0 6px;padding:8px 10px;border:1px dashed var(--edge2);border-radius:7px;
  background:var(--bg);font-size:11px;color:var(--ink2)}
.rt-dry .rt-dryh{font-family:var(--mono);font-size:9.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--dim);margin-bottom:5px}
.rt-dry ul{margin:4px 0 6px;padding-left:16px}
.rt-dry li{font-family:var(--mono);font-size:10px;color:var(--ink2)}
.rt-dry .rt-fire{margin-top:4px}
.rt-launch.is-bank{border-style:dashed}
.rt-launch.armed{border-color:var(--bad);color:var(--bad)}
.rt-out{font-family:var(--mono);font-size:10.5px;margin-top:6px}
.rt-out.ok{color:var(--teal)}
.rt-out.err{color:var(--warn)}
.rt-more{margin-top:6px;display:inline-flex}
.rt-profile-sec .rt-profile{background:var(--panel2);color:var(--ink);border:1px solid var(--edge2);
  border-radius:5px;padding:3px 8px;font-family:var(--mono);font-size:11px}
`;
function ensureCSS() {
  if (typeof document === "undefined") return;
  if (document.getElementById("rt-css")) return;
  const st = document.createElement("style");
  st.id = "rt-css"; st.textContent = RT_CSS;
  document.head.appendChild(st);
}

const PHASE_CLS = {
  finalized: "is-ok", locked: "is-ok", verified: "is-live", fixing: "is-warn",
  detecting: "is-warn", recorded: "", "never-run": "is-never", "not-yet-travelled": "is-never",
};

// the harnessed-ladder rung as a plain STEP verb — a process descriptor, never a
// release verdict. Rendered under the "this convergence" label so the word "finalize"
// reads as a step the round reached, not a terminal state contradicting the position.
const PHASE_STEP = {
  finalized: "reached the finalize step", locked: "locked", verified: "verified this round",
  fixing: "fixing this round", detecting: "detecting this round", recorded: "recorded",
  "never-run": "not started", "not-yet-travelled": "round records not on disk yet",
};

// ── the run STATE chips (pure) — reused by both surfaces at first paint. The artifact
// list is a TRAY column: it shows a capped VISIBLE set and, when more exist, a plain
// `+N more` door to the pipeline surface (the full run chain) — never a silent slice. ──
const ART_CAP = 8;
export function runStateHTML(run, opts) {
  if (!run) return "<div class='rt-note'>run state unavailable</div>";
  opts = opts || {};
  const chip = (cls, txt) => "<span class='hy-chip " + cls + "'>" + esc(txt) + "</span>";
  // ── One state word — the release position the dashboard + cockpit render (run.position,
  // joined server-side from project_state.project_verdict). A single authoritative pill:
  // NEVER a phase pill beside a release_state pill (the 'finalized | NEVER_RUN | round 7'
  // contradiction the critic caught). Falls back to release_state on an older payload. ──
  const position = run.position || run.release_state || "state unavailable";
  let h = "<div class='rt-state sb-run-head'>" +
    chip(PHASE_CLS[run.phase] || "", position) +
    (run.in_flight ? chip("is-live", "converging") : "") + "</div>";
  const ev = run.position_evidence || [];
  if (ev.length) h += "<div class='rt-note'>" + ev.map(esc).join(" · ") + "</div>";
  // ── the CONVERGENCE LADDER — a DIFFERENT mechanic than the release position, named so
  // its round/finding counts never read as the release verdict (the critic's 3-vs-5 and
  // '10 vs 290' finds: every count states WHAT it counts and which store owns it). ──
  const step = PHASE_STEP[run.phase] || run.phase || "—";
  h += "<div class='rt-conv'><div class='rt-conv-h'>this convergence · the harnessed ladder</div>" +
    "<div class='rt-note'>" +
    (run.current_round != null
      ? "round " + esc(run.current_round) + " of " + esc(run.rounds_so_far) + " — " + esc(step)
      : esc(run.rounds_so_far) + " round(s) — " + esc(step)) +
    "</div>";
  if (run.open_findings != null)
    h += "<div class='rt-note'>open findings · this round's detect pass: <b>" + esc(run.open_findings) +
      "</b> <span class='rt-dim'>(this round's own count — the artefact triage door counts the full findings store)</span></div>";
  const kinds = new Set((run.artifacts || []).map((a) => a.kind));
  if (run.phase === "finalized" && !kinds.has("minted_pdf"))
    h += "<div class='rt-note rt-warn'>a finalize record is on disk, but no minted PDF is present here yet</div>";
  h += "</div>";
  const arts = run.artifacts || [];
  if (arts.length) {
    const hidden = arts.length - ART_CAP;
    h += "<div class='rt-arts sb-run-arts'>" +
      "<div class='rt-wo-h'>artifacts <b>" + esc(arts.length) + "</b></div>" +
      arts.slice(0, ART_CAP).map((a) =>
        "<div class='rt-art'><span class='ak'>" + esc(a.kind) + "</span><span class='ap'>" +
        esc(a.path) + "</span></div>").join("") +
      (hidden > 0 && opts.corpus
        ? "<a class='hy-door rt-more' href='/pipeline?corpus=" + encodeURIComponent(opts.corpus) +
          "'>+" + hidden + " more · open the pipeline ↗</a>"
        : (hidden > 0 ? "<div class='rt-note'>+" + hidden + " more (not shown)</div>" : "")) +
      "</div>";
  }
  return h;
}

// ── the DRY-RUN "what would fire" preview (pure read of propagate's worklist). ───────
async function dryRunHTML(corpus) {
  let prop;
  // degrade to COMPOSED words on ANY error (a bad fetch, a non-2xx, an intake refusal):
  // the decision point never shows raw HTTP / schema text. Arming still banks only the order.
  try { prop = await store.fetchJSON("/storyboard/propagate", { inject: [], params: { corpus } }); }
  catch (_e) { return "<div class='rt-dryh'>dry-run — what would fire</div>" +
    "<div class='rt-note'>the preview could not be read — nothing is staged; arming still banks only the order.</div>"; }
  if (!prop || typeof prop !== "object") return "<div class='rt-dryh'>dry-run — what would fire</div>" +
    "<div class='rt-note'>the preview could not be read — nothing is staged; arming still banks only the order.</div>";
  const md = prop.minimum_dispatch || [];
  const wl = prop.worklist || [];
  const cr = prop.comments_routed || 0;
  let h = "<div class='rt-dryh'>dry-run — what would fire (GET /storyboard/propagate → propagate.propagate, pure read)</div>";
  h += "<div class='rt-note'>changeset " + esc(prop.changeset || 0) + " · " + esc(wl.length) +
    " work item(s) · " + esc(md.length) + " section(s) need a builder</div>";
  if (cr) h += "<div class='rt-note rt-dim'>" + esc(cr) +
    " read/verdict record(s) routed as comments — observations, not staged work.</div>";
  if (md.length) h += "<ul>" + md.slice(0, 8).map((s) => "<li>" + esc(s) + "</li>").join("") + "</ul>";
  if (wl.length) h += "<ul>" + wl.slice(0, 6).map((w) =>
    "<li>" + esc(w.kind || "?") + " · " + esc(w.target || w.section || "") + "</li>").join("") + "</ul>";
  if (!md.length && !wl.length) h += "<div class='rt-note'>nothing dirty — a fire would rebuild nothing.</div>";
  return h;
}

// ── ONE scoped fire control (shared): a launch button that, on first click, reveals the
// DRY-RUN preview + an arm-to-fire button that fires NOTHING until armed. Model-heavy
// BANKS a work-order (the offer law); local-safe fires the real executor. ────────────
// the composed verb each launch wears — the slug stays at audit depth (the tooltip).
// An unmapped action de-slugs to plain words rather than serving a machine token.
const LAUNCH_WORDS = {
  "harnessed-round": "converge the round",
  "storyboard-rebuild": "prepare storyboard work",
  "bibliography-run": "prepare derived bibliography",
  "projection-compile": "re-projection",
  "nodemap-rebuild": "rebuild the nodemap",
  "structural-conformance-run": "check structural conformance",
  "citation-direction-run": "run citation direction",
  "figure-materialize": "materialize the figures",
  "detector-run": "run the detectors",
  "dream": "dream",
};
function launchWords(action) {
  return LAUNCH_WORDS[action] || String(action).replace(/[-_]+/g, " ");
}

export function launchControl(action, meta, opts) {
  ensureCSS();
  opts = opts || {};
  // no default actor: his name rides only when a caller names him on his own
  // confirmed act; an absent actor is refused by the server (the actor law)
  const corpus = opts.corpus, actor = opts.actor;
  const isBank = meta.cost_class === "model-heavy";
  const wrap = document.createElement("div");
  wrap.className = "rt-ctrl";
  wrap.dataset.action = action;   // a stable hook: the control + its dry-run + its result
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "hy-door sb-launch rt-launch" + (isBank ? " is-bank" : "");
  btn.dataset.launch = action;
  btn.title = esc((meta.what || "") + (meta.what ? " · " : "") + action);
  btn.textContent = launchWords(action) + (isBank ? " · banks" : (meta.arm_to_fire ? " ⚠" : ""));
  const dry = document.createElement("div");
  dry.className = "rt-dry"; dry.hidden = true;
  const out = document.createElement("div");
  out.className = "rt-out"; out.style.display = "none";
  wrap.append(btn, dry, out);

  let opened = false;
  btn.onclick = async (e) => {
    e.stopPropagation();
    if (opened) { dry.hidden = !dry.hidden; return; }   // toggle the preview
    opened = true; dry.hidden = false;
    dry.innerHTML = "<div class='rt-note'>reading the dry-run…</div>";
    dry.innerHTML = await dryRunHTML(corpus);           // PURE READ — fires nothing
    const fire = document.createElement("button");
    fire.type = "button";
    fire.className = "hy-door is-primary rt-fire";
    fire.textContent = isBank ? "bank " + action : "fire " + action;
    dry.appendChild(fire);
    const doFire = async () => {
      out.style.display = ""; out.className = "rt-out"; out.textContent = (isBank ? "banking " : "firing ") + action + "…";
      if (opts.onStatus) opts.onStatus((isBank ? "banking " : "firing ") + action + "…", "busy");
      let j = {};
      // the profile selector (#75, run-tray only): opts.getProfile is a live read of
      // the tray's <select> — omitted (undefined) or "" (v1/default chosen) means the
      // field is left OFF the body entirely, so every other launchControl caller (the
      // pipeline board's per-organ scoped fires) stays byte-identical to before.
      const body = { corpus, action, by: actor, armed: true };
      const pv = opts.getProfile ? opts.getProfile() : "";
      if (pv) body.profile = pv;
      try {
        j = await store.fetchJSON("/storyboard/run/launch", { inject: [], method: "POST", body });
      } catch (err) { out.className = "rt-out err"; out.textContent = "✗ " + action + ": " + ((err && err.message) || err);
        if (opts.onStatus) opts.onStatus(action + " failed", "bad"); return; }
      if (j.cost_class === "model-heavy") { out.className = "rt-out ok";
        // forward-pointing (ergonomics 2026-07-21): banked is not run — say where
        // the record went and when it fires, and hand onFired the WO id so the
        // open-orders slot can highlight the row this click just created.
        out.textContent = "✓ banked a work-order · " + action +
          " → listed in open work-orders above · fires next remote session (no tokens spent now)"; }
      else if (j.ok === false && j.needs_arming) { out.className = "rt-out"; out.textContent = "armed — re-fire to run " + action; }
      else { out.className = "rt-out ok"; out.textContent = "✓ " + action + " fired · " + esc(corpus); }
      if (opts.onStatus) opts.onStatus(action + " done", "");
      if (opts.onFired) opts.onFired(j);
    };
    // model-heavy + arm-required local-safe ARM before firing; a plain local-safe fires.
    if (isBank || meta.arm_to_fire) armToFire(fire, isBank ? "bank" : "fire", (isBank ? "banks a work-order" : meta.what), doFire);
    else fire.onclick = (ev) => { ev.stopPropagation(); doFire(); };
  };
  return wrap;
}

// ── the OPEN work orders (read) — a banked launch is never invisible. ────────────────
function workOrdersHTML(orders, highlightId) {
  const list = (orders && (orders.handles || orders.open || orders.work_orders)) || null;
  if (!list) return "";
  if (!list.length) return "<div class='rt-wos'><div class='rt-note'>no open work orders — a model-heavy launch banks one here.</div></div>";
  return "<div class='rt-wos'><div class='rt-wo-h'>open work orders <b>" + list.length + "</b></div>" +
    list.map((w) => "<div class='rt-wo sb-wo" + (highlightId && w.id === highlightId ? " rt-wo-new" : "") +
      "' data-wo='" + esc(w.id || "") + "'><span class='hy-chip is-warn'>" + esc(w.cost_class || "model-heavy") + "</span>" +
      "<span class='rt-wo-what'>" + esc(w.what || w.action || "") + "</span>" +
      "<span class='rt-wo-id'>" + esc(w.id || "") + "</span></div>").join("") + "</div>";
}

// ── The full run panel — state + work orders + all launch doors (with dry-run + arm-to-
// fire). Storyboard's run pane AND the pipeline board's converge organ mount this. ───
export async function mountRunTray(host, opts) {
  ensureCSS();
  opts = opts || {};
  const corpus = opts.corpus || store.field("corpus");
  host.innerHTML = "<div class='rt-note'>reading the run…</div>";
  let run, roster;
  try {
    [run, roster] = await Promise.all([
      store.fetchJSON("/storyboard/run", { inject: [], params: { corpus } }),
      store.fetchJSON("/storyboard/run/launch", { inject: [] }),
    ]);
  } catch (e) { host.innerHTML = "<div class='rt-note'>run state unavailable — " + esc((e && e.message) || e) + "</div>"; return; }

  host.innerHTML = runStateHTML(run, { corpus }) + "<div class='rt-woslot'></div>" +
    "<div class='rt-sec rt-profile-sec'><div class='rt-slab'>profile · rides every launch below</div>" +
    "<select class='rt-profile'>" +
      "<option value=''>dials-v1.yaml (default)</option>" +
      "<option value='dials-v2.yaml'>dials-v2.yaml</option>" +
      "<option value='dials-h.yaml'>dials-h.yaml</option>" +
    "</select></div>" +
    "<div class='rt-sec'><div class='rt-slab'>local-safe · fires the real executor (dry-run then arm)</div>" +
    "<div class='rt-launches' data-cost='local'></div></div>" +
    "<div class='rt-sec'><div class='rt-slab'>model-heavy · BANKS a work-order (offer law)</div>" +
    "<div class='rt-launches' data-cost='heavy'></div></div>";

  // a LIVE read of the select at fire time (never a snapshot) — the same element the
  // whole panel's launches share, so changing it before a later fire changes THAT fire.
  const profileSel = $(".rt-profile", host);
  const getProfile = () => (profileSel && profileSel.value) || "";

  const localHost = $(".rt-launches[data-cost='local']", host);
  const heavyHost = $(".rt-launches[data-cost='heavy']", host);
  // the linkback: a banked fire hands its fresh WO id through, so the slot
  // re-renders with THAT row highlighted + scrolled into view — "banked ✓" is
  // never an invisible act.
  const fired = (j) => refreshWO(j && j.work_order && j.work_order.id);
  for (const a of (roster.local_safe || []))
    localHost.appendChild(launchControl(a.action, { cost_class: "local-safe", arm_to_fire: !!a.arm_to_fire, what: a.what }, { corpus, actor: opts.actor, onStatus: opts.onStatus, onFired: fired, getProfile }));
  for (const a of (roster.model_heavy || []))
    heavyHost.appendChild(launchControl(a.action, { cost_class: "model-heavy", what: a.what }, { corpus, actor: opts.actor, onStatus: opts.onStatus, onFired: fired, getProfile }));

  async function refreshWO(highlightId) {
    let orders = null;
    try { orders = await store.fetchJSON("/storyboard/run/orders", { inject: [] }); } catch (_e) { orders = null; }
    const slot = $(".rt-woslot", host); if (slot) slot.innerHTML = workOrdersHTML(orders, highlightId);
    if (highlightId && slot) {
      const row = $("[data-wo='" + highlightId + "']", slot);
      if (row && row.scrollIntoView) row.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }
  refreshWO();
}
