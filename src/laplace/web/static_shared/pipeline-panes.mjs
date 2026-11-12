// pipeline-panes.mjs — The pipeline surface's logic (W6). The live chain as a BOARD
// rendered FROM the release state machine (conception §7; visual §5 W6): the ladder of
// release states (which passed / current / ahead), each organ a CARD whose expansion
// carries ITS DIALS in place (his ruling: "dials are useful but they need to be
// integrated into the pipeline"), its scoped arm/fire controls (each with a DRY-RUN
// preview before any commitment), the live run tray, and the regrade-health read.
//
// NO drawn diagram: the ladder is release.STATES, the organ→dial mapping is derived by
// group name, every value renders from the live profile — all from /pipeline/chain.
// Dial edits ride the EXISTING /dials/op + /dials/undo (dials_surface, the one write
// path); scoped fires ride /storyboard/run/launch; the dry-run is /storyboard/propagate.
// All network rides store.fetchJSON (the one gateway); no raw fetch, no color literal.

import store from "/shared/store.mjs";
import { mountRunTray, launchControl } from "/shared/run-tray.mjs";
import { injectEngineCSS, createFocusState, HighlightBus, HoverLens, Reallocator, activate }
  from "/shared/engine.mjs";

const esc = (s) => String(s == null ? "" : s)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
  .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const infoTag = (t) => "<span class='pipe-i' title='" + esc(t) + "'>ⓘ</span>";

const STATUS_CHIP = { passed: "is-ok", current: "is-live", ahead: "is-never", reopened: "is-warn" };

// ── ✎ rule (D16) — the shell's rule-in-place atom on a rulable host (the organ head).
// A bonus atom: its absence (shell not yet loaded) never breaks the card. ──
function attachRule(host, ctx) {
  if (!host) return;
  try {
    const R = typeof window !== "undefined" && window.HymnShell && window.HymnShell.hyRule;
    if (R && R.attach) R.attach(host, ctx);
  } catch (_e) { /* the ✎ mouth is a bonus atom — never load-bearing */ }
}

let CHAIN = null, PROJECT = null, PROFILE = "dials-v1.yaml", OPEN = null;
// W-PROJECT — the engine layer: the composed brief (server-minted over the SAME chain +
// verdict read models — the lock-step law), the focus runtime, and whether the board is
// materialised. The brief is the resting altitude; the cockpit strip + organ cards are the
// summonable inventory, materialised behind one open and pinned into the focus geometry.
let BRIEF = null;                 // /pipeline/brief payload (the composed brief of THIS project)
let STATE = createFocusState("index");
let BUS = null, LENS = null, REALLOC = null;
let MAT_OPEN = false;             // is the board (cockpit strip + organ cards) materialised?
// ACT 4 — The project cockpit: the one typed verdict (GET /pipeline/verdict →
// project_state.project_verdict) the state strip + generation panel + RESPINE read.
let VERDICT = null;
// the generation rows for the panel (R10 + SEL draft/ruling per generation), read from
// the selection organ's full payload — newest-first, exactly as the sheet orders them.
let GEN_ROWS = [];
// the per-state next_action (the backend computes it per rung; E4b: the frontend
// never read it — the literal answer to "what do I do at this stage" was thrown away
// before the page). Rebuilt from CHAIN.states on every load; the primary door on
// every rung's organ card leads with it.
let NEXT_ACTION = {};
// the conjugate wave — nested sub-organ cards: which are open, and a cache of each
// sub-organ's lazily-fetched /pipeline/organ payload (cleared on every board reload).
let OPEN_SUBS = new Set();
let SUB_EV = {};
const GATE_CHIP = { passed: "is-ok", failed: "is-warn", absent: "is-warn" };
// the evolution desk's queue-row status chip — open is HIS pending move (is-warn),
// held/applied/rejected are settled (never a green on a still-open ask).
const EVO_STATUS_CHIP = { open: "is-warn", held: "", applied: "is-ok",
  rejected: "is-never", "orphan-draft": "is-never" };
// the selection face — the three gates shortened for the chip, the gate-pass →
// chip-state map (null NEVER reads green — an absent reading is is-warn, silence
// never certifies), and the verdict → chip-state map (retire is destructive).
const SEL_GATE_LABEL = { gate_self_consistency: "self-consistency",
  gate_cost: "cost", gate_representation_stability: "representation",
  gate_reach: "reach" };
const selGateChip = (pass) => (pass === true ? "is-ok" : (pass === false ? "is-warn" : ""));
const SEL_VERD_CHIP = { promote: "is-ok", hold: "", retire: "is-never" };

// the derivation face — a link's attestation-kind → chip state: an attested link is
// forged (derived/computed/cited, teal), a GAP is the named residual (warn, never
// green — silence never certifies a claim reached).
const DER_KIND_CHIP = { derived: "is-ok", computed: "is-ok", cited: "is-ok" };

// FINDING 4 — the PSU/cost chip a derivation act's arm zone wears, matching the
// converge organ's rendering: the arm zones named their write but dropped the PSU
// class the backend declares. rescope + contest are RECORD-ONLY (local-safe); forge
// BANKS a model-heavy work-order. Rendered inline in the arm-what so the chair reads
// the cost before the second (banking) click.
const derPsuChip = (cls, note) =>
  "<span class='pipe-der-psu hy-chip " + (cls === "model-heavy" ? "is-warn" : "is-ok") +
  "'>" + esc(cls) + (note ? " · " + esc(note) : "") + "</span>";

// layout CSS injected once — every color is a hymn var / hymn class (the one-palette
// clause): the ladder steps reuse hymn's hy-chip state classes, so NO color literal here.
const PP_CSS = `
.pipe-arrow{color:var(--dim);font-size:10px}
.pipe-i{cursor:help;color:var(--dim);font-size:10px;margin-left:4px}
.pipe-blurb{font-size:11px;color:var(--ink2);line-height:1.45}
.pipe-prod{font-family:var(--mono);font-size:9.5px;color:var(--dim);margin-top:2px;word-break:break-word}
.pipe-zone{border-top:1px solid var(--edge);padding-top:8px;margin-top:2px}
.pipe-zh{font-family:var(--mono);font-size:9.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--dim);
  margin-bottom:6px;display:flex;align-items:center;gap:8px}
.pipe-zh .pipe-undo{margin-left:auto;font-family:var(--mono);font-size:10px;color:var(--accent);
  background:var(--panel2);border:1px solid var(--edge2);border-radius:5px;padding:2px 8px;cursor:pointer}
.pipe-zh .pipe-undo:hover{border-color:var(--accent);color:var(--ink)}
.pipe-zh .pipe-undo[disabled]{opacity:.4;cursor:default}
.pipe-dials{display:flex;flex-direction:column;gap:5px}
.pipe-dial{display:grid;grid-template-columns:1fr 150px 70px 54px;gap:9px;align-items:center}
.pipe-dial .dpath{font-family:var(--mono);font-size:10.5px;color:var(--ink);min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pipe-dial .dctl input,.pipe-dial .dctl select{width:100%;background:var(--panel2);color:var(--ink);
  border:1px solid var(--edge2);border-radius:5px;padding:2px 6px;font-family:var(--mono);font-size:11px}
.pipe-dial .dctl input[type=checkbox]{width:15px;height:15px;accent-color:var(--accent)}
.pipe-prov{font-size:9px;text-transform:uppercase;letter-spacing:.05em;padding:1px 7px;border-radius:999px;
  border:1px solid var(--edge2);color:var(--dim);text-align:center}
.pipe-prov.overlay{color:var(--accent);border-color:var(--accent)}
.pipe-reset{font-family:var(--mono);font-size:10px;color:var(--ink2);background:var(--panel2);
  border:1px solid var(--edge2);border-radius:5px;padding:2px 6px;cursor:pointer}
.pipe-reset:hover:not([disabled]){border-color:var(--accent);color:var(--ink)}
.pipe-reset[disabled]{opacity:.35;cursor:default}
.pipe-derr{font-size:10.5px;color:var(--bad);font-family:var(--mono);margin-top:3px}
/* HIS COMMISSION (9a) — the dial meaning + history IN PLACE. The wrap groups a knob's
   row, its worded meaning, its gate line, and its ledger-history fold. */
.pipe-dial-wrap{display:flex;flex-direction:column;gap:4px;padding:6px 0;border-bottom:1px solid var(--edge)}
.pipe-dial-wrap:last-child{border-bottom:none}
.pipe-dial-meaning{font-size:10.5px;color:var(--ink2);line-height:1.5}
.pipe-dm-what{color:var(--ink)}
.pipe-dm-effect{color:var(--ink2);margin-top:1px}
.pipe-dm-none{color:var(--dim);font-style:italic}
.pipe-dm-meta{font-family:var(--mono);font-size:9.5px;color:var(--dim);margin-top:3px}
.pipe-dm-meta b{color:var(--ink2);font-weight:600}
.pipe-dm-changed{color:var(--accent)}
.pipe-dm-atdef{color:var(--dim)}
.pipe-dial-hist{font-size:10px;color:var(--ink2)}
.pipe-dial-hist summary{cursor:pointer;color:var(--dim);font-family:var(--mono);font-size:9px;
  text-transform:uppercase;letter-spacing:.05em}
.pipe-dial-hist-body{margin-top:4px;display:flex;flex-direction:column;gap:2px}
.pipe-dial-hrow{font-family:var(--mono);font-size:10px;color:var(--ink2)}
.pipe-dial-hrow .ek{color:var(--dim)}
.pipe-dial-hrow b{color:var(--accent);font-weight:600}
/* HIS COMMISSION (9b) — the prompts view (real dispatch templates + override provenance),
   mono at audit depth. */
.pipe-zh .pipe-prompts-btn{margin-left:auto;font-family:var(--mono);font-size:10px;color:var(--accent);
  background:var(--panel2);border:1px solid var(--edge2);border-radius:5px;padding:2px 8px;cursor:pointer}
.pipe-zh .pipe-prompts-btn:hover:not([disabled]){border-color:var(--accent);color:var(--ink)}
.pipe-zh .pipe-prompts-btn[disabled]{opacity:.5;cursor:default}
.pipe-prompts-body{display:flex;flex-direction:column;gap:6px}
.pipe-pr-site{font-size:10.5px;color:var(--ink2);line-height:1.5}
.pipe-pr-h{font-family:var(--mono);font-size:9.5px;text-transform:uppercase;letter-spacing:.05em;
  color:var(--dim);margin-top:6px}
.pipe-pr-roles{display:flex;flex-wrap:wrap;gap:4px 12px}
.pipe-pr-role{font-family:var(--mono);font-size:10px;color:var(--ink2)}
.pipe-pr-role b{color:var(--ink)}
.pipe-pr-w summary,.pipe-pr-t summary{cursor:pointer;font-family:var(--mono);font-size:10px;color:var(--ink2)}
.pipe-pr-w summary b,.pipe-pr-t summary b{color:var(--ink)}
.pipe-pr-src{color:var(--dim);font-size:9px}
.pipe-pr-fold{font-size:10.5px;color:var(--ink2);line-height:1.5;margin-top:4px}
.pipe-pr-fold .ek{color:var(--dim);font-family:var(--mono);text-transform:uppercase;font-size:9px;letter-spacing:.05em}
.pipe-pr-text{margin-top:4px;padding:8px 10px;border:1px dashed var(--edge2);border-radius:6px;background:var(--bg);
  font-family:var(--mono);font-size:10px;color:var(--ink2);white-space:pre-wrap;max-height:340px;overflow:auto;line-height:1.5}
.pipe-pr-rule{font-size:10.5px;color:var(--ink2);line-height:1.5}
.pipe-pr-note{font-size:10px;color:var(--dim);font-style:italic;line-height:1.4}
.pipe-none{font-size:10.5px;color:var(--dim);font-style:italic}
/* The fire made legible (r2 stranger-walk fix) — the reproject control on the staged card,
   greeting by the generation name with the cost in plain words and the brief a real door.
   Every color a hymn var (the one-palette clause). */
.pipe-reproject{display:flex;flex-direction:column;gap:5px;border:1px solid var(--accent);
  border-left-width:3px;border-radius:9px;background:var(--panel);padding:9px 11px;min-width:0}
.pipe-rp-head{font-size:12px;font-weight:640;color:var(--ink);line-height:1.4}
.pipe-rp-cost{font-family:var(--mono);font-size:10px;color:var(--ink2);line-height:1.5}
.pipe-rp-doors{display:flex;flex-wrap:wrap;gap:8px;align-items:center;min-width:0}
.pipe-rp-brief{white-space:normal;overflow-wrap:anywhere;max-width:100%;height:auto;line-height:1.4}
.pipe-rp-briefabsent{font-family:var(--mono);font-size:10px;color:var(--dim);font-style:italic;overflow-wrap:anywhere}
.pipe-regrade{font-family:var(--mono);font-size:10.5px;color:var(--ink2);line-height:1.6}
.pipe-regrade .rk{color:var(--dim)}
.pipe-ev{font-family:var(--mono);font-size:10px;color:var(--ink2);display:flex;flex-direction:column;gap:2px}
.pipe-ev .ek{color:var(--dim)}
.pipe-dry .pipe-dry-lead{font-size:11px;color:var(--ink2);line-height:1.5;margin-bottom:6px}
.pipe-dry .pipe-dry-sets{display:flex;flex-wrap:wrap;gap:4px 14px}
.pipe-dry .pipe-dry-set{font-family:var(--mono);font-size:10px;color:var(--ink2)}
.pipe-dry .pipe-dry-set code{color:var(--dim)}
.pipe-dry .pipe-dry-set b{color:var(--accent);font-weight:600}
.pipe-suborgans{display:flex;flex-direction:column;gap:8px}
.pipe-subcard{padding:9px 11px}
.pipe-gaterow{display:flex;flex-direction:column;gap:3px}
.pipe-gate{font-family:var(--mono);font-size:10px;color:var(--dim);display:flex;align-items:center;gap:7px;flex-wrap:wrap;padding-left:2px}
.pipe-gate-r{color:var(--bad);font-size:10px}
.pipe-suboev .ek{color:var(--dim)}
.pipe-suboev .pipe-stale{color:var(--warn);font-size:10px;line-height:1.4}
.pipe-law{font-size:10px;color:var(--dim);font-style:italic;margin-top:8px;line-height:1.4}
.pipe-evo-list{display:flex;flex-direction:column;gap:8px}
.pipe-evo-row{border:1px solid var(--edge);border-radius:7px;padding:8px 10px;display:flex;flex-direction:column;gap:5px}
.pipe-evo-head{display:flex;align-items:center;gap:8px;font-family:var(--mono);font-size:10px;color:var(--dim)}
.pipe-evo-id{color:var(--ink2)}
/* FINDING 6 — the demoted id tail: a small mono chip pushed to the row's end (the
   substance leads), the raw CI- id in its tooltip (the derivation node-chip idiom). */
.pipe-evo-idtail{margin-left:auto;color:var(--dim);font-family:var(--mono);font-size:9px;
  max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pipe-evo-sub{font-size:11.5px;color:var(--ink);line-height:1.5;font-style:italic}
.pipe-evo-ctx{font-size:10.5px;color:var(--ink2)}
.pipe-evo-ctx summary{cursor:pointer;color:var(--dim);font-family:var(--mono);font-size:9.5px;text-transform:uppercase;letter-spacing:.05em}
.pipe-evo-ctx-body{margin-top:4px;line-height:1.5;white-space:pre-wrap}
.pipe-evo-meta{font-family:var(--mono);font-size:10px;color:var(--ink2)}
.pipe-evo-meta .ek{color:var(--dim)}
.pipe-evo-actions{display:flex;gap:6px;margin-top:2px}
.pipe-evo-btn{font-family:var(--mono);font-size:10px;color:var(--ink2);background:var(--panel2);
  border:1px solid var(--edge2);border-radius:5px;padding:3px 9px;cursor:pointer}
.pipe-evo-btn:hover:not([disabled]){border-color:var(--accent);color:var(--ink)}
.pipe-evo-btn[disabled]{opacity:.5;cursor:default}
.pipe-evo-btn.armed{border-color:var(--bad);color:var(--bad)}
.pipe-evo-btn.destructive{border-color:var(--warn)}
.pipe-evo-btn.is-primary{border-color:var(--accent);color:var(--accent)}
.pipe-evo-note{display:flex;gap:6px;align-items:center;margin-top:2px}
.pipe-evo-note-in{flex:1;background:var(--panel2);color:var(--ink);border:1px solid var(--edge2);
  border-radius:5px;padding:3px 7px;font-family:var(--mono);font-size:10.5px}
.pipe-evo-dry{margin-top:4px;padding:6px 8px;border:1px dashed var(--edge2);border-radius:6px;
  background:var(--bg);font-size:10.5px;color:var(--ink2)}
.pipe-evo-dry-what{font-family:var(--mono);font-size:9.5px;color:var(--dim);text-transform:uppercase;letter-spacing:.05em;margin-bottom:3px}
.pipe-evo-dry-sub{font-style:italic;margin-bottom:3px}
.pipe-evo-dry-mint{font-family:var(--mono);font-size:9.5px;color:var(--dim)}
.pipe-evo-err{font-size:10px;color:var(--bad);font-family:var(--mono)}
.pipe-evo-bulk{display:flex;flex-direction:column;gap:4px;margin-bottom:8px;padding:8px 10px;
  border:1px dashed var(--edge2);border-radius:7px}
.pipe-evo-bulk-btn{align-self:flex-start}
.pipe-fit-traj-wrap{overflow-x:auto}
.pipe-fit-traj{border-collapse:collapse;font-family:var(--mono);font-size:10px;color:var(--ink2);width:100%}
.pipe-fit-traj th,.pipe-fit-traj td{padding:2px 8px 2px 0;text-align:left;border-bottom:1px solid var(--edge)}
.pipe-fit-traj th{color:var(--dim);font-weight:600;text-transform:uppercase;font-size:9px;letter-spacing:.05em}
.pipe-recon{font-size:10px;color:var(--dim);margin-top:3px;line-height:1.4}
.pipe-recon .ek{color:var(--ink2)}
.pipe-fit-line{font-family:var(--mono);font-size:10.5px;color:var(--ink2);margin-top:6px}
.pipe-fit-line .ek{color:var(--dim)}
.pipe-sel-top{font-family:var(--mono);font-size:10px;color:var(--ink2);margin-bottom:8px;line-height:1.5}
.pipe-sel-top .ek{color:var(--dim)}
.pipe-sel-await.is-open{color:var(--warn)}
.pipe-sel-list{display:flex;flex-direction:column;gap:8px}
.pipe-sel-row{border:1px solid var(--edge);border-radius:7px;padding:8px 10px;display:flex;flex-direction:column;gap:5px}
.pipe-sel-head{display:flex;align-items:center;gap:8px;font-family:var(--mono);font-size:10px;color:var(--dim)}
.pipe-sel-n{color:var(--ink);font-weight:600}
.pipe-sel-id{color:var(--ink2)}
.pipe-sel-date{margin-left:auto}
.pipe-sel-traj{font-family:var(--mono);font-size:10.5px;color:var(--ink2)}
.pipe-sel-traj .ek{color:var(--dim)}
.pipe-sel-delta{color:var(--accent)}
.pipe-sel-gates{display:flex;flex-wrap:wrap;gap:5px}
.pipe-sel-reasons{font-size:10.5px;color:var(--ink2)}
.pipe-sel-reasons summary{cursor:pointer;color:var(--dim);font-family:var(--mono);font-size:9.5px;text-transform:uppercase;letter-spacing:.05em}
.pipe-sel-reasons-body{margin-top:4px;line-height:1.5;display:flex;flex-direction:column;gap:2px}
.pipe-sel-draft{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.pipe-sel-draftchip{border-style:dashed;color:var(--dim)}
.pipe-sel-draftverd{font-weight:600}
.pipe-sel-ret{font-family:var(--mono);font-size:10px;color:var(--ink2)}
.pipe-sel-ret .ek{color:var(--dim)}
.pipe-sel-actions{display:flex;gap:6px;margin-top:2px}
.pipe-sel-nextact{font-size:10.5px;color:var(--warn);line-height:1.45;margin-top:2px}
.pipe-sel-nextact .ek{color:var(--dim);font-family:var(--mono)}
.pipe-sel-ruled{display:flex;align-items:center;gap:6px;margin-top:2px;flex-wrap:wrap}
.pipe-sel-hischip{font-weight:600}
.pipe-sel-arm{margin-top:4px;padding:6px 8px;border:1px dashed var(--edge2);border-radius:6px;background:var(--bg);font-size:10.5px;color:var(--ink2)}
.pipe-sel-arm-what{font-family:var(--mono);font-size:9.5px;color:var(--dim);text-transform:uppercase;letter-spacing:.05em;margin-bottom:3px}
.pipe-sel-arm-draft{margin-bottom:2px}
.pipe-sel-arm-dig{font-family:var(--mono);font-size:10px;color:var(--ink2);margin-bottom:3px}
.pipe-sel-arm-note{font-style:italic;color:var(--dim);font-size:10px;line-height:1.4}
/* the reasoning field (his psi/phi — the backend banks it as reason): required when his
   verdict differs from the draft (an override IS the calibration signal, so its grounds
   are owed), optional when he ratifies. Sized for a sentence or two, not a single line. */
.pipe-sel-reasonlbl{font-family:var(--mono);font-size:9px;color:var(--dim);text-transform:uppercase;letter-spacing:.05em;margin:5px 0 3px}
.pipe-sel-reasonlbl .req{color:var(--warn)}
.pipe-sel-reason{width:100%;box-sizing:border-box;background:var(--panel2);color:var(--ink);
  border:1px solid var(--edge2);border-radius:5px;padding:4px 7px;font-family:var(--mono);
  font-size:10.5px;min-height:48px;resize:vertical;line-height:1.5}
.pipe-sel-reason:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.pipe-sel-reason.is-owed{border-color:var(--warn)}
.pipe-sel-err{font-size:10px;color:var(--bad);font-family:var(--mono)}
.pipe-der-top{font-family:var(--mono);font-size:10px;color:var(--ink2);margin-bottom:8px;line-height:1.5}
.pipe-der-top .ek{color:var(--dim)}
.pipe-der-frontier.is-open{color:var(--warn)}
.pipe-der-claim{border:1px solid var(--accent);border-left-width:3px;border-radius:7px;padding:9px 11px;margin-bottom:8px;background:var(--panel2)}
.pipe-der-claim-h{font-family:var(--mono);font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:var(--accent);margin-bottom:5px}
.pipe-der-claim-body{font-size:11.5px;color:var(--ink);line-height:1.55}
.pipe-der-axes{display:flex;flex-direction:column;gap:2px;margin-top:6px}
.pipe-der-axis{font-size:10.5px;color:var(--ink2);line-height:1.45}
.pipe-der-axis .ek{color:var(--dim);font-family:var(--mono);text-transform:uppercase;font-size:9px;letter-spacing:.05em}
.pipe-der-demo{font-size:10.5px;color:var(--ink2);margin-bottom:8px}
.pipe-der-demo summary{cursor:pointer;color:var(--dim);font-family:var(--mono);font-size:9.5px;text-transform:uppercase;letter-spacing:.05em}
.pipe-der-demo-body{margin-top:5px;display:flex;flex-direction:column;gap:4px;line-height:1.5}
.pipe-der-list{display:flex;flex-direction:column;gap:8px}
.pipe-der-row{border:1px solid var(--edge);border-radius:7px;padding:8px 10px;display:flex;flex-direction:column;gap:5px}
.pipe-der-row.is-gap{border-left:3px solid var(--warn)}
.pipe-der-row.is-attested{border-left:3px solid var(--teal)}
.pipe-der-head{display:flex;align-items:center;gap:8px;font-family:var(--mono);font-size:10px;color:var(--dim);flex-wrap:wrap}
.pipe-der-id{color:var(--ink)}
.pipe-der-node{font-family:var(--mono);font-size:9px;max-width:190px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-decoration:none}
.pipe-der-node:hover{border-color:var(--accent);color:var(--ink)}
.pipe-der-listhead{font-family:var(--mono);font-size:9.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--dim);margin-bottom:2px}
.pipe-der-flow{font-size:10.5px;color:var(--ink2);line-height:1.45}
.pipe-der-flow .arrow{color:var(--dim)}
.pipe-der-why{font-size:10.5px;color:var(--warn);line-height:1.45;font-style:italic}
.pipe-der-attest{font-family:var(--mono);font-size:10px;color:var(--ink2);line-height:1.4}
.pipe-der-contests{display:flex;flex-direction:column;gap:2px}
.pipe-der-contest{font-family:var(--mono);font-size:10px;color:var(--warn)}
.pipe-der-actions{display:flex;gap:6px;margin-top:2px;flex-wrap:wrap}
.pipe-der-btn{font-family:var(--mono);font-size:10px;color:var(--ink2);background:var(--panel2);
  border:1px solid var(--edge2);border-radius:5px;padding:3px 9px;cursor:pointer}
.pipe-der-btn:hover:not([disabled]){border-color:var(--accent);color:var(--ink)}
.pipe-der-btn[disabled]{opacity:.5;cursor:default}
.pipe-der-btn.armed{border-color:var(--bad);color:var(--bad)}
.pipe-der-btn.destructive{border-color:var(--warn)}
.pipe-der-frag{margin-top:4px;padding:6px 8px;border:1px dashed var(--edge2);border-radius:6px;background:var(--bg);
  font-family:var(--mono);font-size:10px;color:var(--ink2);white-space:pre-wrap;max-height:260px;overflow:auto;line-height:1.5}
.pipe-der-arm{margin-top:4px;padding:6px 8px;border:1px dashed var(--edge2);border-radius:6px;background:var(--bg);font-size:10.5px;color:var(--ink2)}
.pipe-der-arm-what{font-family:var(--mono);font-size:9.5px;color:var(--dim);text-transform:uppercase;letter-spacing:.05em;margin-bottom:3px}
.pipe-der-arm-note{font-style:italic;color:var(--dim);font-size:10px;line-height:1.4;margin-top:2px}
.pipe-der-in{width:100%;box-sizing:border-box;background:var(--panel2);color:var(--ink);border:1px solid var(--edge2);
  border-radius:5px;padding:4px 7px;font-family:var(--mono);font-size:10.5px;margin-bottom:4px}
textarea.pipe-der-in{min-height:56px;resize:vertical;line-height:1.5}
.pipe-der-err{font-size:10px;color:var(--bad);font-family:var(--mono)}
.pipe-der-psu{margin-left:6px;vertical-align:middle}

/* ── FINDING 3 — visible keyboard focus (it was outline:none everywhere). A
   :focus-visible ring in the accent token across every board control: buttons, doors,
   rungs, and card headers. Keyboard-only (mouse clicks don't ring); the accent token is
   the one-palette signal, offset so it reads as a ring not a fill. ── */
.pipe-der-btn:focus-visible,.pipe-evo-btn:focus-visible,.pipe-sel-btn:focus-visible,
.pipe-reset:focus-visible,.pipe-zh .pipe-undo:focus-visible,.pipe-prompts-btn:focus-visible,
.pipe-der-in:focus-visible,.pipe-dial .dctl input:focus-visible,
.pipe-dial .dctl select:focus-visible,.hy-door:focus-visible,
.cockpit-rung:focus-visible,.hy-card:focus-visible,.hy-card-id:focus-visible,
.pipe-dial-hist:focus-visible,.pipe-dial-meaning summary:focus-visible{
  outline:2px solid var(--accent);outline-offset:2px;border-radius:5px}

/* ── ACT 4 — The project cockpit (state strip · generation panel · RESPINE). Every
   color a hymn var / hy- class (the one-palette clause) — no literal here. ── */
.cockpit-pos{display:flex;flex-direction:column;gap:5px;border:1px solid var(--edge2);
  border-radius:10px;background:var(--panel);padding:11px 13px;margin-bottom:16px}
.cockpit-pos-h{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap}
.cockpit-pos-t{font-size:14px;font-weight:640;color:var(--ink)}
.cockpit-pos-ev{font-family:var(--mono);font-size:10.5px;color:var(--ink2);line-height:1.55}
.cockpit-pos-ev .ek{color:var(--dim)}
.cockpit-nextact{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:3px}
.cockpit-nextact .lbl{font-family:var(--mono);font-size:9px;color:var(--dim);
  text-transform:uppercase;letter-spacing:.06em}
.cockpit-strip{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  gap:8px;margin-bottom:20px}
.cockpit-rung{border:1px solid var(--edge2);border-radius:9px;background:var(--panel);
  padding:9px 10px;display:flex;flex-direction:column;gap:6px;min-width:0}
.cockpit-rung.is-current{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent) inset}
.cockpit-rung.is-passed{border-color:color-mix(in srgb,var(--teal) 35%,transparent)}
.cockpit-rung.is-next{border-color:var(--keystone);box-shadow:0 0 0 1px var(--keystone) inset}
.cockpit-rung-h{display:flex;align-items:center;gap:6px}
.cockpit-rung-n{font-family:var(--mono);font-size:9px;color:var(--dim)}
.cockpit-rung-t{font-size:11.5px;font-weight:600;color:var(--ink);min-width:0;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cockpit-rung-ev{font-family:var(--mono);font-size:9.5px;color:var(--ink2);line-height:1.5;min-height:1px}
.cockpit-rung-next{margin-top:auto;padding-top:6px;border-top:1px dashed var(--edge2)}
.cockpit-rung-next .lbl{font-family:var(--mono);font-size:8.5px;color:var(--dim);
  text-transform:uppercase;letter-spacing:.05em;display:block;margin-bottom:3px}
/* FINDING 1 — the heredity banner (machine never driven) + the muted 'then' chip on
   ahead rungs (a downstream offer, not the live move — so exactly one next move reads). */
.cockpit-ladbanner{font-size:11px;color:var(--warn);line-height:1.5;margin:0 0 10px;
  padding:7px 11px;border:1px dashed color-mix(in srgb,var(--warn) 45%,transparent);
  border-radius:8px;background:var(--panel)}
.cockpit-rung-next.is-ahead .lbl{opacity:.7}
.cockpit-rung-thenchip{font-family:var(--mono);font-size:9.5px;color:var(--dim);
  padding:1px 7px;border:1px solid var(--edge2);border-radius:999px;display:inline-block}
.cockpit-sec{display:flex;align-items:baseline;gap:9px;margin:0 0 10px}
.cockpit-sec .st{font-family:var(--mono);font-size:11px;text-transform:uppercase;
  letter-spacing:.1em;color:var(--dim);font-weight:700}
.cockpit-sec .sn{font-family:var(--mono);font-size:10.5px;color:var(--ink2)}
.cockpit-debt{display:flex;align-items:center;gap:5px;font-family:var(--mono);
  font-size:11.5px;margin:0 0 12px;flex-wrap:wrap}
.cockpit-debt .lbl{color:var(--dim);margin-right:3px}
.cockpit-debt-n{padding:3px 9px;border-radius:6px;background:var(--panel2);
  border:1px solid var(--edge2);color:var(--ink2)}
.cockpit-debt-n.zero{color:var(--ok);border-color:color-mix(in srgb,var(--ok) 40%,transparent)}
.cockpit-debt-arrow{color:var(--dim)}
.cockpit-reach{font-family:var(--mono);font-size:11px;color:var(--ink2);margin:0 0 14px;line-height:1.5}
.cockpit-reach b{color:var(--ink)}
.cockpit-reach .gap{color:var(--warn)}
.cockpit-gens{display:flex;flex-direction:column;gap:7px;margin-bottom:20px}
.cockpit-gen{display:grid;grid-template-columns:auto 1fr auto;gap:10px;align-items:center;
  border:1px solid var(--edge2);border-radius:9px;background:var(--panel);padding:8px 11px}
.cockpit-gen.is-current{border-color:var(--accent)}
.cockpit-gen-id{font-family:var(--mono);font-size:12px;font-weight:700;color:var(--ink)}
.cockpit-gen-facts{font-family:var(--mono);font-size:10px;color:var(--ink2);
  display:flex;gap:10px;flex-wrap:wrap;min-width:0}
.cockpit-gen-facts .fk{color:var(--dim)}
/* the gen row's right column — the draft/ruling chip + the RULE door (Gap 5): the hand to
   rule a generation lived two expands deep; the door lands on the pre-expanded selection
   sub-organ (the deep-link resolver), so the ruling is one click from the panel. */
.cockpit-gen-tail{display:flex;align-items:center;gap:7px;flex-wrap:wrap;justify-content:flex-end}
.cockpit-gen-ruledoor{font-family:var(--mono);font-size:9.5px;color:var(--accent);
  background:var(--panel2);border:1px solid var(--edge2);border-radius:6px;padding:3px 9px;cursor:pointer;white-space:nowrap}
.cockpit-gen-ruledoor:hover{border-color:var(--accent);color:var(--ink)}
.cockpit-gen-ruledoor:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.respine{border:1px solid var(--keystone);border-radius:12px;background:var(--panel);
  padding:13px 15px;margin-bottom:22px}
.respine-h{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin-bottom:8px}
.respine-t{font-size:14px;font-weight:700;color:var(--keystone)}
.respine-note{font-size:12.5px;line-height:1.55;color:var(--ink2);margin-bottom:9px}
.respine-note b{color:var(--ink)}
.respine-meta{font-family:var(--mono);font-size:10px;color:var(--dim);margin-bottom:10px;line-height:1.5}
.respine-act{display:flex;align-items:center;gap:9px;flex-wrap:wrap}
.cockpit-none{font-size:11px;color:var(--dim);font-style:italic;margin-bottom:16px}
.pipe-nextdoor{margin-left:auto;min-width:0}
/* The scroll law (P10): zero horizontal overflow. The next-act + RESPINE doors carry
   a long legible label (the ratify-the-RESPINE clause); they must WRAP inside the pane,
   never spill the viewport sideways. Long unbroken tokens break anywhere. */
.cockpit-nextact .hy-door,.respine-act .hy-door,.pipe-nextdoor .hy-door{
  white-space:normal;overflow-wrap:anywhere;max-width:100%;height:auto;line-height:1.4}
.cockpit-nextact,.respine-act{min-width:0}
/* COMPACTION (scroll law ~1.75x): trim the generous inter-panel margins, and bound the
   ORGAN BOARD — a genuinely long list (12 stage cards) — to scroll inside its OWN pane,
   so the page height stays bounded while every card stays reachable. */
.cockpit-strip{margin-bottom:12px}
.cockpit-gens{margin-bottom:12px}
.respine{margin-bottom:14px}
.cockpit-reach{margin-bottom:9px}
#pipe-board{max-height:58vh;overflow-y:auto;overflow-x:hidden;
  border:1px solid var(--edge2);border-radius:10px;padding:8px;
  scrollbar-gutter:stable}
/* ── W-PROJECT — the composed brief (the resting altitude, joined to engine.mjs) ────── */
#eng-root{min-width:0}
.pipe-brief{display:flex;flex-direction:column;gap:16px}
.pipe-prose{font-size:14.5px;line-height:1.7;color:var(--ink);max-width:80ch;margin:6px 0 0}
.pipe-conseq{border:1px solid var(--accent);border-left-width:3px;border-radius:11px;background:var(--panel);
  padding:13px 15px;display:flex;flex-direction:column;gap:9px;max-width:80ch;min-width:0}
.pipe-conseq .pc-h{font-family:var(--mono);font-size:9px;text-transform:uppercase;letter-spacing:.11em;
  color:var(--accent);font-weight:700}
.pipe-conseq .pc-glance{font-size:13px;line-height:1.55;color:var(--ink);overflow-wrap:anywhere}
.pipe-conseq .pc-cost{font-family:var(--mono);font-size:10px;color:var(--ink2)}
.pipe-conseq .pc-doors{display:flex;gap:8px;flex-wrap:wrap}
.pipe-conseq .hy-door{white-space:normal;overflow-wrap:anywhere;max-width:100%;height:auto;line-height:1.4}
.pipe-counts{display:flex;flex-wrap:wrap;gap:10px;margin-top:2px}
.pipe-count{display:inline-flex;align-items:center;gap:7px;cursor:pointer;background:var(--panel);
  border:1px solid var(--edge2);border-radius:9px;padding:8px 12px;font:inherit;color:var(--ink2);min-width:0}
.pipe-count:hover{border-color:var(--accent);color:var(--ink)}
.pipe-count:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.pipe-count.is-open{border-color:var(--keystone);color:var(--ink);box-shadow:inset 0 0 0 1px var(--keystone)}
.pipe-count.is-static{cursor:default}
.pipe-count.is-static:hover{border-color:var(--edge2);color:var(--ink2)}
.pipe-count .pc-n{font-family:var(--mono);font-weight:700;color:var(--ink);font-size:14px}
.pipe-count .pc-l{font-size:11.5px}
.pipe-count.lit{box-shadow:inset 0 0 0 1px var(--warn)}
/* the reallocated board focus — the rail's brief summary + the board head line */
.pipe-boardhead{font-family:var(--mono);font-size:10.5px;color:var(--dim);line-height:1.5;margin-bottom:11px}
.pipe-railcov{font-family:var(--mono);font-size:10px;color:var(--ink2);line-height:1.7}
.pipe-railcost{color:var(--accent)}
.eng-focus #pipe-board{max-height:66vh}
/* the scroll law at narrow widths: the reallocated 2-col grid (rail + focus) collapses to a
   single column so the board's dial grid keeps its full width and never spills sideways. */
@media (max-width:760px){ #eng-root.reallocated{grid-template-columns:1fr} .eng-rail{position:static} }
@media (max-width:640px){ .pipe-prose{font-size:13.5px} }
`;
function ensureCSS() {
  if (document.getElementById("pipe-css")) return;
  const st = document.createElement("style"); st.id = "pipe-css"; st.textContent = PP_CSS;
  document.head.appendChild(st);
}

// ── The chain ladder — release.STATES marked from the mechanism. ─────────────────────
function renderLadder() {
  // the duplicate stage rail dies (fix wave, scroll law): the cockpit STATE STRIP
  // (stateStrip) is the one release ladder now — richer, with each rung's status +
  // next_action. Rendering the old chip rail here too was the duplicate 'bottom stage
  // rail' the walk flagged. #pipe-ladder stays as the error host only (emptied on load).
  const host = $("#pipe-ladder");
  if (host) host.innerHTML = "";
  const cur = $("#pipe-cur");
  // C1 — the release ladder tracks the RELEASE machine (NEVER_RUN until it first
  // transitions); heredity tracks scored generations independently. When generations
  // exist, name the reconcile so a NEVER_RUN ladder beside a GEN-3 sheet doesn't read
  // as a contradiction. (generations_n + newest_n + debt ride the selection summary
  // already in the chain payload — no extra fetch.)
  const sel = selSummary();
  const gN = sel.generations_n || 0;
  let recon = "";
  if (gN > 0) {
    const nn = sel.newest_n != null ? sel.newest_n : gN;
    const debt = (sel.debt_before != null && sel.debt_after != null)
      ? " · debt " + esc(sel.debt_before) + "→" + esc(sel.debt_after) : "";
    recon = "<div class='pipe-recon'><span class='ek'>release state</span> tracks the release machine; " +
      "<span class='ek'>heredity</span> tracks generations — this project: <b>GEN-" + esc(nn) + "</b>" + debt + "</div>";
  }
  // one truth on one page (fix wave): the header speaks the truth-layer POSITION the
  // backend carries (CHAIN.position — project_state's plain words), never the bare
  // machine token, so it can't say "never run" beside a GEN-3/r2-minted body. A raw
  // ALL_CAPS machine state gets the human transform; plain prose ("pre-release — …")
  // passes through as authored. Falls back to current_state when the join is absent.
  let word = CHAIN.position || CHAIN.current_state || "";
  if (/^[A-Z][A-Z_]*$/.test(word)) word = word.toLowerCase().replace(/_/g, " ");
  if (cur) cur.innerHTML = "state <b>" + esc(word) + "</b>" + recon;
}

// the selection sub-organ's LIGHT summary, dug from the chain payload (the converge
// stage's sub-organ band) — the one place the ladder reconcile + any cross-card read
// pulls heredity's headline without a second fetch.
function selSummary() {
  for (const o of (CHAIN.organs || []))
    for (const so of (o.sub_organs || []))
      if (so.id === "selection") return so.summary || {};
  return {};
}

// a sub-organ LIGHT summary by id, dug from the chain payload (no second fetch) —
// the generalisation of selSummary the cockpit reach line + gen rows lean on.
function subSummaryById(id) {
  for (const o of (CHAIN.organs || []))
    for (const so of (o.sub_organs || []))
      if (so.id === id) return so.summary || {};
  return {};
}

// ── ACT 4 — The project cockpit. One page per project: the truthful state strip
// (per-stage evidence + next_action on every rung, pre-machine history labeled
// plainly), the generation panel (debt 30→20→3→0 as a first-class series, reach, R10
// per generation), and the RESPINE card ("gen-4's opener"). Injected ABOVE the organ
// board, all from GET /pipeline/verdict + /pipeline/chain — no drawn diagram. ──────────
function ensureCockpitMount() {
  let m = $("#pipe-cockpit");
  if (!m) {
    m = document.createElement("div"); m.id = "pipe-cockpit";
    const ladder = $("#pipe-ladder");
    if (ladder && ladder.parentNode) ladder.parentNode.insertBefore(m, ladder);
  }
  return m;
}

function renderCockpit() {
  const m = ensureCockpitMount();
  if (!m) return;
  m.innerHTML = "";
  const V = VERDICT || {};
  m.appendChild(positionBanner(V));
  m.appendChild(stateStrip());
  m.appendChild(generationPanel(V));
  const rc = respineCard(V);
  if (rc) m.appendChild(rc);
}

// the plain POSITION banner (P7): a NEVER_RUN release machine beside a minted r2 is
// labeled "pre-release — GEN-3, r2 minted", with the evidence that predates the machine
// spelled out — never bare "never run". The verdict's next_act is the primary door.
function positionBanner(V) {
  const el = document.createElement("div"); el.className = "cockpit-pos";
  const na = V.next_act || {};
  const ev = (V.position_evidence || []).map((e) => esc(e)).join(" · ");
  const naDoor = na.label
    ? "<div class='cockpit-nextact'><span class='lbl'>next act — the machine's real next move</span>" +
      (na.href
        ? "<a class='hy-door is-keystone' href='" + esc(na.href) + "'>" + esc(na.label) + " →</a>"
        : "<span class='hy-chip is-warn'>" + esc(na.label) + "</span>") +
      "</div>"
    : "";
  // artefact declared-absence (P7): the strip must not present a recorded artefact name
  // as live when the bytes are gone (a reopened project past an old mint). project_state
  // resolves disk truth into V.artefact.exists; exists===false names the absence
  // ("recorded, absent on disk") on an is-warn chip — appearance predicts behaviour.
  const art = V.artefact;
  const artChip = (art && art.name)
    ? (art.exists === false
        ? "<span class='hy-chip is-warn' title='" + esc(art.path || "") + "'>" +
            esc(art.name) + " · recorded, absent on disk</span>"
        : "<span class='hy-chip is-live'>" + esc(art.name) + "</span>")
    : "";
  // a raw ALL_CAPS machine state (UNDER_CONVERGENCE) is humanised for the headline —
  // the same transform the header applies — so the banner reads as prose, never a token;
  // plain prose ("pre-release — GEN-3, r2 minted") passes through untouched.
  let posWord = V.position || "not started";
  if (/^[A-Z][A-Z_]*$/.test(posWord)) posWord = posWord.toLowerCase().replace(/_/g, " ");
  el.innerHTML =
    "<div class='cockpit-pos-h'><span class='cockpit-pos-t'>" +
      esc(posWord) + "</span>" + artChip +
    "</div>" +
    (ev ? "<div class='cockpit-pos-ev'><span class='ek'>evidence</span> " + ev + "</div>" : "") +
    naDoor;
  return el;
}

// the STATE STRIP — the release ladder from the mechanism (release.STATES), each rung
// its status + its next_action rendered as a door (E4b: the backend computed it per
// rung and the page threw it away — here it leads every rung). The current rung is
// live, the machine's real next move (the verdict's next_act target) is keystone.
function stateStrip() {
  const wrap = document.createElement("div");
  const sec = document.createElement("div"); sec.className = "cockpit-sec";
  // FINDING 1 — exactly ONE next move reads: the current rung leads with its next_action;
  // passed rungs do not re-advertise a forward move (that move is history).
  sec.innerHTML = "<span class='st'>release ladder</span><span class='sn'>· view = mechanism (release.STATES); the current rung leads with its next move</span>";
  wrap.appendChild(sec);
  // FINDING 1 — the heredity banner: when the release MACHINE was never driven but
  // generations/a minted artefact exist, an explicit worded line names that the position
  // is tracked by heredity (never ten identical 'ahead' rungs contradicting a GEN-3 body).
  if (CHAIN.ladder_banner) {
    const ban = document.createElement("div"); ban.className = "cockpit-ladbanner";
    ban.textContent = CHAIN.ladder_banner;
    wrap.appendChild(ban);
  }
  const strip = document.createElement("div"); strip.className = "cockpit-strip";
  const states = CHAIN.states || [];
  for (const s of states) {
    const rung = document.createElement("div");
    const cls = s.status === "current" ? " is-current"
      : s.status === "passed" ? " is-passed" : "";
    rung.className = "cockpit-rung" + cls;
    const label = esc(s.state.toLowerCase().replace(/_/g, " "));
    const na = s.next_action;
    // exactly ONE next move: only the CURRENT rung shows its next_action as the live
    // move. Passed rungs are done (no forward chip); an ahead rung shows its next_action
    // MUTED (a downstream offer, not the live move) so the eye lands on the one that reads.
    const naBlock = na
      ? (s.status === "current"
          ? "<div class='cockpit-rung-next'><span class='lbl'>next move</span>" +
              "<span class='hy-chip is-live'>" + esc(na) + "</span></div>"
          : s.status === "passed"
            ? ""
            : "<div class='cockpit-rung-next is-ahead'><span class='lbl'>then</span>" +
                "<span class='cockpit-rung-thenchip'>" + esc(na) + "</span></div>")
      : "";
    rung.innerHTML =
      "<div class='cockpit-rung-h'><span class='cockpit-rung-n'>" + esc((s.index != null ? s.index + 1 : "")) + "</span>" +
        "<span class='cockpit-rung-t' title='" + esc(s.state) + "'>" + label + "</span></div>" +
      "<div class='cockpit-rung-h'><span class='hy-chip " + (STATUS_CHIP[s.status] || "") + "'>" + esc(s.status) + "</span></div>" +
      naBlock;
    strip.appendChild(rung);
  }
  wrap.appendChild(strip);
  return wrap;
}

// the generation panel (P6) — the debt trajectory 30→20→3→0 as a FIRST-CLASS series
// (from project_state, not recomputed-and-discarded), the reach story from the
// derivation organ, and each scored generation with its R10 verdict + SEL draft.
function generationPanel(V) {
  const wrap = document.createElement("div");
  const g = V.generations || {};
  const traj = g.debt_trajectory || [];
  const sec = document.createElement("div"); sec.className = "cockpit-sec";
  sec.innerHTML = "<span class='st'>generations</span><span class='sn'>· " +
    esc((g.gen || "—")) + (g.present ? " current" : " — none scored yet") + "</span>";
  wrap.appendChild(sec);
  if (traj.length) {
    const dt = document.createElement("div"); dt.className = "cockpit-debt";
    let html = "<span class='lbl'>debt trajectory</span>";
    traj.forEach((n, i) => {
      html += "<span class='cockpit-debt-n" + (n === 0 ? " zero" : "") + "'>" + esc(n) + "</span>";
      if (i < traj.length - 1) html += "<span class='cockpit-debt-arrow'>→</span>";
    });
    dt.innerHTML = html;
    wrap.appendChild(dt);
  }
  // the reach line — from the derivation sub-organ's LIGHT summary (already in the
  // chain payload); the named frontier gap stays warn, never silently complete (P7).
  const der = subSummaryById("derivation");
  if (der.aspiration_present) {
    const rl = document.createElement("div"); rl.className = "cockpit-reach";
    const gapN = der.frontier_n || 0;
    rl.innerHTML = "reach <b>" + esc(der.links_attested || 0) + " / " + esc(der.links_total || 0) +
      "</b> attested · depth <b>" + esc(der.depth_attested || 0) + "</b> · " +
      (gapN > 0
        ? "<span class='gap'>" + esc(gapN) + " named frontier gap" + (gapN === 1 ? "" : "s") + " — mechanism attested, scale named not hidden</span>"
        : "<span>no open frontier gap</span>");
    wrap.appendChild(rl);
  }
  // the generation rows — R10 per generation + the SEL draft/ruling, from the
  // selection organ's full payload (lazy-fetched into GEN_ROWS by renderCockpit).
  const rows = GEN_ROWS || [];
  if (rows.length) {
    const list = document.createElement("div"); list.className = "cockpit-gens";
    const curN = (rows[0] && rows[0].n);        // newest-first
    for (const r of rows) list.appendChild(genRow(r, curN));
    wrap.appendChild(list);
  } else if (!traj.length) {
    const none = document.createElement("div"); none.className = "cockpit-none";
    none.textContent = "no scored generations for " + PROJECT +
      " yet — heredity banks a generation per reprojection; the panel fills as they land";
    wrap.appendChild(none);
  }
  return wrap;
}

function genRow(r, curN) {
  const el = document.createElement("div");
  el.className = "cockpit-gen" + (r.n === curN ? " is-current" : "");
  const r10 = r.r10 || {};
  const r10chip = r10.clean === true
    ? "<span class='hy-chip is-ok'>R10 clean</span>"
    : (r10.clean === false ? "<span class='hy-chip is-warn'>R10 not clean</span>"
       : "<span class='hy-chip'>R10 —</span>");
  const rul = r.ruling || {};
  const draft = (r.draft_verdict || {}).verdict;
  const selChip = rul.verdict
    ? "<span class='hy-chip " + (SEL_VERD_CHIP[rul.verdict] || "") + "'>SEL: " + esc(rul.verdict) + "</span>"
    : "<span class='hy-chip pipe-sel-draftchip'>draft: " + esc(draft || "—") + "</span>";
  const db = r.debt_before, da = r.debt_after;
  // the RULE door (Gap 5) — the gen row showed the draft/ruling chip but no hand to rule;
  // the ruling face lived two expands deep. The door lands on the pre-expanded selection
  // sub-organ (expandSubOrgan — the deep-link resolver already opens the parent stage + the
  // selection sub-card + scrolls to it). "already ruled" reads a settled, arm-less state.
  const ruled = !!(r.ruling && r.ruling.verdict);
  const ruleDoor = "<button type='button' class='cockpit-gen-ruledoor' data-role='gen-rule'" +
    " title='open the selection sub-organ, pre-expanded, to rule this generation'>" +
    (ruled ? "ruling →" : "rule →") + "</button>";
  el.innerHTML =
    "<span class='cockpit-gen-id'>GEN-" + esc(r.n == null ? "?" : r.n) + "</span>" +
    "<span class='cockpit-gen-facts'>" +
      "<span><span class='fk'>debt</span> " + esc(db == null ? "—" : db) + "→" + esc(da == null ? "—" : da) + "</span>" +
      (r.stamped_at ? "<span><span class='fk'>stamped</span> " + esc(r.stamped_at) + "</span>" : "") +
      r10chip +
    "</span>" +
    "<span class='cockpit-gen-tail'>" + selChip + ruleDoor + "</span>";
  const door = el.querySelector("[data-role='gen-rule']");
  if (door) door.addEventListener("click", (e) => { e.stopPropagation(); expandSubOrgan("selection"); });
  return el;
}

// the respine card (P6) — the open RESPINE intent as a legible, named, singly-
// ratifiable act labeled "gen-4's opener". The R10 finding IS the note; the door is a
// REAL navigable link to the spine plan (never a fabricated live ratify).
function respineCard(V) {
  const r = (V.generations || {}).respine_intent;
  if (!r) return null;
  const el = document.createElement("div"); el.className = "respine";
  el.innerHTML =
    "<div class='respine-h'>" +
      "<span class='respine-t'>RESPINE — gen-4's opener</span>" +
      "<span class='hy-chip is-keystone'>" + esc(r.id || "") + "</span>" +
      "<span class='hy-chip'>verb: " + esc(r.verb || "RESPINE") + "</span>" +
      (r.object_key ? "<span class='hy-chip'>object: " + esc(r.object_key) + "</span>" : "") +
    "</div>" +
    "<div class='respine-note'>" + esc(r.title || "") + "</div>" +
    "<div class='respine-meta'>the open structural finding R10 raised — promoting a generation past it would be verdict-shopping; ruling it is gen-4's opener</div>" +
    "<div class='respine-act'>" +
      (r.href ? "<a class='hy-door is-keystone' href='" + esc(r.href) + "'>read the spine plan · rule the RESPINE →</a>" : "") +
    "</div>";
  return el;
}

// ── The organ board — one CARD per stage. ────────────────────────────────────────────
function renderBoard() {
  const host = $("#pipe-board");
  host.innerHTML = "";
  for (const o of (CHAIN.organs || [])) host.appendChild(organCard(o));
  host.appendChild(organCard(CHAIN.global, true));       // the cross-cutting calibration card
  host.appendChild(regradeCard());                        // the rehoused regrade-health read
}

function organCard(o, isGlobal) {
  const key = "organ::" + o.id;
  const open = OPEN === key;
  const status = o.status || (isGlobal ? "" : "");
  const el = document.createElement("div");
  el.className = "hy-card is-clickable" + (open ? " is-open" : "") +
    (status === "current" ? " edge-live" : status === "passed" ? " edge-ok" : "");
  el.dataset.organ = o.id;
  const chips = [];
  if (status) chips.push("<span class='hy-chip " + (STATUS_CHIP[status] || "") + "'>" + esc(status) + "</span>");
  if ((o.dials || []).length) chips.push("<span class='hy-chip'>" + o.dials.length + " dial" + (o.dials.length > 1 ? "s" : "") + "</span>");
  if ((o.controls || []).length) chips.push("<span class='hy-chip'>" + o.controls.length + " control" + (o.controls.length > 1 ? "s" : "") + "</span>");
  // E4b — the PRIMARY door on every rung's card: the next_action the backend computes
  // per state (NEXT_ACTION, from CHAIN.states). It leads the card, never thrown away.
  const na = o.state ? NEXT_ACTION[o.state] : null;
  const naDoor = na
    ? "<span class='pipe-nextdoor'><span class='hy-door is-primary' title='the next action at " +
      esc(o.state) + " (release._NEXT_ACTION — offer, never fired here)'>next: " + esc(na) + " →</span></span>"
    : "";
  el.innerHTML =
    "<div class='hy-card-id'>" +
      "<span class='hy-card-name'>" + esc(o.label) + "</span>" +
      (o.state ? "<span class='hy-card-kind'>" + esc(o.state) + "</span>" : "<span class='hy-card-kind'>global</span>") +
      naDoor +
    "</div>" +
    "<div class='hy-card-chips'>" + chips.join("") + "</div>" +
    "<div class='pipe-blurb'>" + esc(o.blurb || "") + (o.producer ? infoTag(o.producer) : "") + "</div>" +
    // the producer rode this card TWICE — as the blurb's ⓘ hover AND a raw dim line.
    // the raw echo is dropped (fix wave: referents whole, no redundant raw text; the ⓘ
    // carries it) — this also shrinks every closed card, part of the scroll-law compaction.
    "<div class='hy-card-fold'></div>";
  // ✎ rule on the organ head — bank a typed interface fork about THIS organ (D16).
  attachRule(el.querySelector(".hy-card-id"), {
    surface: "pipeline", title: o.label, kind: "organ",
    node: "organ:" + o.id, project: PROJECT,
  });
  el.onclick = (e) => {
    // the expansion + the ✎ rule chip/capture own their clicks — they never toggle the card.
    if (e.target.closest(".hy-card-fold, .rule-chip, .rule-cap")) return;
    OPEN = open ? null : key; renderBoard();
  };
  // FINDING 3 — the card head is keyboard-focusable (tabindex + role) so its focus ring
  // is reachable, and Enter/Space toggles it exactly as a click does.
  const head = el.querySelector(".hy-card-id");
  if (head) { head.tabIndex = 0; head.setAttribute("role", "button");
    head.setAttribute("aria-expanded", open ? "true" : "false");
    head.addEventListener("keydown", (e) => {
      if ((e.key === "Enter" || e.key === " ") && !e.target.closest(".rule-chip, .rule-cap")) {
        e.preventDefault(); OPEN = open ? null : key; renderBoard(); }
    });
  }
  if (open) fillFold($(".hy-card-fold", el), o);
  return el;
}

function fillFold(host, o) {
  // ZONE — the evidence (the current organ's live run artifacts / the release records).
  if (o.evidence) host.appendChild(evidenceZone(o));
  // ZONE — the DIALS in place (this organ's knobs, editable through the one write path).
  host.appendChild(dialsZone(o));
  // ZONE — the DRY-RUN preview: what firing this organ would do, rendered from the live
  // profile BEFORE any arm. Edit a dial above → the board reloads → this preview updates.
  host.appendChild(dryRunZone(o));
  // ZONE — the scoped arm/fire controls (each also previews its worklist on arm).
  if ((o.controls || []).length) host.appendChild(controlsZone(o));
  // ZONE — the run tray (the converge organ mounts the shared run panel).
  if (o.run_tray) {
    const z = document.createElement("div"); z.className = "pipe-zone";
    z.innerHTML = "<div class='pipe-zh'>run tray" + infoTag(o.producer || "") + "</div><div class='pipe-runtray'></div>";
    host.appendChild(z);
    mountRunTray($(".pipe-runtray", z), { corpus: PROJECT, actor: "gerard" });
  }
  // ZONE — The sub-organ band (the night-organs that run WITHIN this stage): one
  // nested sub-card each, reusing the four zones; heavy telemetry lazy-fetches per card.
  if ((o.sub_organs || []).length) host.appendChild(subOrganBand(o));
  // ZONE — HIS COMMISSION (9b): the PROMPTS VIEW door, on the GLOBAL roles/prompts card
  // (the roles + prompts dial group live here). Reached in ≤2 acts: open the global card,
  // open this fold. The real dispatch templates + override provenance render mono in place.
  if (o.id === "global") host.appendChild(promptsZone());
}

// ── The sub-organ band — the night-organs as nested sub-cards under a stage. ──────────
function subOrganBand(o) {
  const z = document.createElement("div"); z.className = "pipe-zone";
  z.innerHTML = "<div class='pipe-zh'>sub-organs · " + (o.sub_organs.length) +
    infoTag("the night-organs this stage consumes — each a card reading its own organ's " +
            "reader (view=mechanism, GET /pipeline/organ); a fire rides /storyboard/run/launch") +
    "</div><div class='pipe-suborgans'></div>";
  const host = $(".pipe-suborgans", z);
  for (const so of o.sub_organs) host.appendChild(subCard(so, o.id));
  return z;
}

// the summary chips a sub-card head carries — real banked counts, the declared-absence
// line when the organ has never run (the TEXT LAW: every chip carries a count/state).
function subChips(so) {
  const s = so.summary || {}, chips = [];
  const c = (label, n) => chips.push("<span class='hy-chip'>" + esc(n) + " " + esc(label) + "</span>");
  if (!s.present) { chips.push("<span class='hy-chip is-never'>never run</span>"); return chips.join(""); }
  const id = so.id;
  if (id === "detectors") { c("gaps", s.gaps); c("leaks", s.meta_leak); c("promise-absent", s.promise); }
  else if (id === "bibliography") { c("dangling", s.dangling); c("resolved", s.resolved); if (s.renders != null) chips.push("<span class='hy-chip " + (s.renders ? "is-ok" : "is-warn") + "'>" + (s.renders ? "renders" : "no-render") + "</span>"); }
  else if (id === "citation-direction") { c("intents", s.intents); c("needs-judge", s.needs_judge); c("admitted", s.admitted); }
  else if (id === "figures") { c("placed", s.placed); c("of", s.total); if (s.absent) c("absent", s.absent); }
  else if (id === "structural-conformance") { c("patches", s.patch_count); chips.push("<span class='hy-chip " + (s.stale ? "is-warn" : "") + "'>" + esc(s.verdict) + "</span>"); if ((s.stores_fed || []).length) c("stores fed", s.stores_fed.length); if (s.stale) chips.push("<span class='hy-chip is-warn'>stale · dials moved</span>"); }
  else if (id === "proxy") { chips.push("<span class='hy-chip is-warn'>engine-wide</span>"); c("adjudicated", s.adjudicated); c("his", s.genuinely_his); if (s.contested) c("contested", s.contested); }
  else if (id === "growth") { c("discovered", s.discovered); c("substrate-absent", s.substrate_absent); }
  else if (id === "evolution") {
    // open is HIS pending move — is-warn whenever there's anything waiting on him.
    chips.push("<span class='hy-chip" + (s.open > 0 ? " is-warn" : "") + "'>" + esc(s.open || 0) + " open</span>");
    c("held", s.held); c("applied", s.applied); c("rejected", s.rejected);
  } else if (id === "fitness") {
    chips.push("<span class='hy-chip'>debt " + esc(s.debt == null ? "—" : s.debt) + "</span>");
    chips.push("<span class='hy-chip " + (s.freeze_pass == null ? "" : (s.freeze_pass ? "is-ok" : "is-warn")) + "'>freeze " +
      (s.freeze_pass == null ? "—" : (s.freeze_pass ? "ok" : "FAIL")) + "</span>");
    chips.push("<span class='hy-chip'>mech Δ " + esc(s.mech_derivative == null ? "—" : s.mech_derivative) + "</span>");
    chips.push("<span class='hy-chip'>red floor " + esc(s.named_red == null ? "—" : s.named_red) + "</span>");
  } else if (id === "selection") {
    // generations scored, the newest DRAFT verdict, and how many still await HIS ruling
    // (awaiting is his pending move — is-warn whenever anything is unruled).
    c("generations", s.generations_n);
    chips.push("<span class='hy-chip'>draft " + esc(s.latest_draft_verdict == null ? "—" : s.latest_draft_verdict) + "</span>");
    chips.push("<span class='hy-chip" + (s.awaiting_ruling_n > 0 ? " is-warn" : "") + "'>" + esc(s.awaiting_ruling_n || 0) + " awaiting</span>");
  } else if (id === "derivation") {
    // reach: how far UP the aspiration the attested isnad got (attested/total ·
    // depth), and the NAMED frontier gaps (warn whenever anything is still unforged).
    chips.push("<span class='hy-chip" + (s.aspiration_present ? " is-ok" : " is-warn") + "'>" + (s.aspiration_present ? "aspiration" : "no aspiration") + "</span>");
    chips.push("<span class='hy-chip'>reach " + esc(s.links_attested || 0) + "/" + esc(s.links_total || 0) + "</span>");
    chips.push("<span class='hy-chip'>depth " + esc(s.depth_attested || 0) + "</span>");
    chips.push("<span class='hy-chip" + (s.frontier_n > 0 ? " is-warn" : "") + "'>" + esc(s.frontier_n || 0) + " gap" + (s.frontier_n === 1 ? "" : "s") + "</span>");
  }
  if ((so.dials || []).length) chips.push("<span class='hy-chip'>" + so.dials.length + " dial" + (so.dials.length > 1 ? "s" : "") + "</span>");
  return chips.join("");
}

function subCard(so, parentId) {
  const key = "sub::" + parentId + "::" + so.id;
  const open = OPEN_SUBS.has(key);
  const el = document.createElement("div");
  el.className = "hy-card is-clickable pipe-subcard" + (open ? " is-open" : "") +
    (so.summary && so.summary.present ? (so.summary.stale ? " edge-warn" : " edge-ok") : "");
  el.dataset.suborgan = so.id;
  el.innerHTML =
    "<div class='hy-card-id'><span class='hy-card-name'>" + esc(so.label) + "</span>" +
      "<span class='hy-card-kind'>" + esc(so.id) + "</span></div>" +
    "<div class='hy-card-chips'>" + subChips(so) + "</div>" +
    "<div class='pipe-blurb'>" + esc(so.blurb || "") + (so.producer ? infoTag(so.producer) : "") + "</div>" +
    "<div class='pipe-prod'>" + esc(so.producer || "") + "</div>" +
    "<div class='hy-card-fold'></div>";
  // ✎ rule on the sub-organ head — bank a typed interface fork about THIS sub-organ.
  attachRule(el.querySelector(".hy-card-id"), {
    surface: "pipeline", title: so.label, kind: "sub-organ",
    node: "sub-organ:" + so.id, project: PROJECT,
  });
  el.onclick = (e) => {
    // the ✎ rule chip/capture own their clicks. A click inside THIS sub-card's OWN fold
    // (its evidence/dials/controls) must not toggle it — but the sub-card lives INSIDE the
    // parent organ's .hy-card-fold, so a bare closest(".hy-card-fold") matches the PARENT's
    // fold and the head could never open the sub-card. Scope the fold guard to this card's
    // own fold (el.contains) so a head click toggles, a fold click does not.
    if (e.target.closest(".rule-chip, .rule-cap")) return;
    const fold = e.target.closest(".hy-card-fold");
    if (fold && el.contains(fold)) return;
    if (open) OPEN_SUBS.delete(key); else OPEN_SUBS.add(key);
    renderBoard();
  };
  // FINDING 3 — the sub-card head is keyboard-focusable + Enter/Space toggles it.
  const shead = el.querySelector(".hy-card-id");
  if (shead) { shead.tabIndex = 0; shead.setAttribute("role", "button");
    shead.setAttribute("aria-expanded", open ? "true" : "false");
    shead.addEventListener("keydown", (e) => {
      if ((e.key === "Enter" || e.key === " ") && !e.target.closest(".rule-chip, .rule-cap")) {
        e.preventDefault();
        if (OPEN_SUBS.has(key)) OPEN_SUBS.delete(key); else OPEN_SUBS.add(key);
        renderBoard(); }
    });
  }
  if (open) subFold($(".hy-card-fold", el), so);
  return el;
}

function subFold(host, so) {
  const canFire = (so.controls || []).length || (so.dials || []).length;
  // ZONE — the evidence, lazy-fetched from the sub-organ's own reader (GET /pipeline/organ).
  host.appendChild(subEvidenceZone(so));
  // ZONE — the dials in place (only the structural organ carries the store kill-switches).
  if ((so.dials || []).length) host.appendChild(dialsZone(so));
  // ZONE — the dry-run preview (the live dial settings a fire would apply, no re-execution);
  // shown only where a fire exists (a read-only organ names its door in noFireZone instead).
  if (canFire) host.appendChild(dryRunZone(so));
  // ZONE — the scoped fire control (local-safe fires, model-heavy BANKS a work-order).
  if ((so.controls || []).length) host.appendChild(controlsZone(so));
  else host.appendChild(noFireZone(so));
}

// a read-only sub-organ (proxy/growth): no scoped storyboard fire — name where its
// action lives (the desk door / the cross-round /analytics view) instead of a dead button.
function noFireZone(so) {
  const z = document.createElement("div"); z.className = "pipe-zone";
  let where;
  if (so.id === "proxy")
    where = "the live bank is desk-supervised (POST /desk/act, class proxy-drafts); the parked forks above are the dry-run frames' subjects (fork_adjudicator.drive frames them — GET /pipeline/organ?organ=proxy&dryrun=1).";
  else if (so.id === "evolution")
    where = "no single scoped fire — ratify / hold / reject render per queue row above (POST /evolution/ratify · /evolution/hold · /evolution/reject, each armed + attributed).";
  else if (so.id === "fitness")
    where = "no scoped fire — this panel only reads; fire the converge organ above to bank a fresh round.";
  else if (so.id === "derivation")
    where = "no single scoped fire — re-scope the boundary claim, forge a gap, and contest a link render inline per link above (POST /derivation/rescope · /derivation/forge · /derivation/contest, each armed + attributed).";
  else
    where = "no scoped fire — the closure vs discovery metric is the cross-round view on /analytics/loop.";
  z.innerHTML = "<div class='pipe-zh'>scoped controls · none" +
    infoTag(so.producer || "") + "</div><div class='pipe-none'>" + esc(where) + "</div>";
  return z;
}

// the sub-organ evidence zone — lazily fetches the organ's full reader payload once,
// caches it, and renders the facts as key/value rows (no re-parse: the reader is truth).
function subEvidenceZone(so) {
  const z = document.createElement("div"); z.className = "pipe-zone";
  z.innerHTML = "<div class='pipe-zh'>evidence" + infoTag(so.producer || "") +
    "</div><div class='pipe-ev pipe-suboev'></div>";
  const host = $(".pipe-suboev", z);
  const cached = SUB_EV[so.id];
  if (cached !== undefined) renderSubEv(host, so, cached);
  else {
    host.innerHTML = "<span class='pipe-none'>reading " + esc(so.id) + "…</span>";
    loadSubEv(host, so);
  }
  return z;
}

async function loadSubEv(host, so) {
  try {
    const data = await store.fetchJSON("/pipeline/organ", { inject: [],
      params: { project: PROJECT, organ: so.id } });
    SUB_EV[so.id] = (data && data.payload) || {};
    renderSubEv(host, so, SUB_EV[so.id]);
  } catch (e) {
    host.innerHTML = "<span class='pipe-none'>reader unavailable — " + esc((e && e.message) || e) + "</span>";
  }
}

// render the reader payload as fact rows — the declared-absence line when the organ has
// no banked run, else the per-organ facts the chair acts on.
function renderSubEv(host, so, p) {
  if (!p || p.present === false) {
    // the absence string must name the REAL fix (TEXT LAW): a read-only organ has no
    // "fire it below" — name its actual route; a fire control only promises "(dry-run
    // first)" when it truly arms-to-fire (an arm_to_fire:false control fires on click).
    const ctrls = so.controls || [];
    let tail;
    if (ctrls.length) tail = "fire it below" + (ctrls[0].arm_to_fire ? " (dry-run first)" : "");
    else if (so.id === "proxy") tail = "the live bank is desk-supervised — POST /desk/act, class proxy-drafts";
    else if (so.id === "growth") tail = "closure vs discovery is the cross-round view on /analytics/loop";
    else if (so.id === "evolution") tail = "nothing drafted — a route-to-conceptric intent (G-3) needs to land before the consumer drafts a contract";
    else if (so.id === "fitness") tail = "no banked run records yet — fire the converge organ above to establish a baseline";
    else if (so.id === "selection") tail = "no scored generations yet — heredity banks a generation row per reprojection; the sheet (and its DRAFT verdicts) fills as they land";
    else if (so.id === "derivation") tail = "no aspiration banked yet — Phase 0 of the derivation organ asserts the maximal claim + the isnad chain; re-scope banks the first one";
    else tail = "no scoped fire here";
    host.innerHTML = "<span class='pipe-none'>" + esc(so.label) +
      " — no banked run for " + esc(PROJECT) + " yet · " + esc(tail) + "</span>";
    return;
  }
  if (so.id === "evolution") { renderEvolutionQueue(host, p); return; }
  if (so.id === "fitness") { renderFitnessPanel(host, p); return; }
  if (so.id === "selection") { renderSelectionSheet(host, p); return; }
  if (so.id === "derivation") { renderDerivationSheet(host, p); return; }
  const rows = [];
  const kv = (k, v) => rows.push("<span><span class='ek'>" + esc(k) + "</span> " + esc(v) + "</span>");
  const id = so.id;
  if (id === "detectors") {
    kv("round", p.date); kv("gaps", (p.gaps || {}).gaps + " (" + (p.gaps || {}).research_intents + " research · " + (p.gaps || {}).conceptric_intents + " conceptric)");
    kv("meta-leak", (p.meta_leak || {}).n); kv("source-delta", (p.source_delta || {}).n);
    kv("promise-absent", (p.promise || {}).n + " · " + Object.entries((p.promise || {}).by_class || {}).map(([k, v]) => k.replace("promise-", "") + " " + v).join(" · "));
  } else if (id === "bibliography") {
    kv("cited", p.cited_n); kv("resolved", p.resolved_n); kv("dangling", p.dangling_n);
    kv("wired", p.wired ? "yes" : "no"); kv("renders", p.renders == null ? "not probed" : (p.renders ? "yes" : "no"));
    if ((p.dangling_keys || []).length) kv("dangling keys", p.dangling_keys.join(", "));
  } else if (id === "citation-direction") {
    kv("intents", p.intents_n); kv("candidates", p.candidates_total);
    kv("buckets", Object.entries(p.buckets || {}).map(([k, v]) => k + " " + v).join(" · "));
    kv("manifests pending", p.manifests_pending + " · admitted " + p.admitted);
    kv("network leg", p.network_leg == null ? "n/a" : (p.network_leg ? "reachable" : "attested-available"));
  } else if (id === "structural-conformance") {
    // the banked verdict, PLUS the reconcile against the live dials (so.summary.stale):
    // a 'patched' banked under a prior dial state names why a refire changes it.
    if (so.summary && so.summary.stale) rows.push("<span class='pipe-stale'>stale · " + esc(so.summary.reconcile) + "</span>");
    kv("verdict", p.verdict); kv("patches", p.patch_count);
    kv("conformant", p.conformant); kv("unscored", p.unscored);
    for (const s of (p.store_gates || [])) rows.push("<span><span class='ek'>" + esc(s.store) + "</span> dial " + (s.value ? "on" : "off") + " · gate <span class='hy-chip " + (GATE_CHIP[s.gate.state] || "") + "'>" + esc(s.gate.state) + "</span></span>");
  } else if (id === "figures") {
    // the BANKED manifest facts (last real materialize); the LIVE matched/absent
    // preview is the dry-run zone below (figuresDryZone, GET …&dryrun=1).
    kv("placed", p.figures_placed + " of " + p.promises_total);
    kv("promised-but-absent", p.promises_absent); kv("intents", p.intents_banked);
  } else if (id === "proxy") {
    // SCOPE FIRST (finding: the counts are ROOT-scoped, not this project's) — the
    // adjudicated/his/parked counts + the listed forks are engine-wide, identical on
    // every project; name that so the chair does not read a per-project adjudication.
    kv("scope", (p.scope || "engine-global") + " · not " + PROJECT + " (identical on every project)");
    kv("adjudicated", p.adjudicated); kv("GENUINELY-HIS", p.genuinely_his);
    kv("contested", p.contested); kv("parked forks", p.parked);
    for (const f of (p.forks || [])) rows.push("<span><span class='ek'>" + esc(f.source) + "</span> " + esc(f.node || f.key) + "</span>");
  } else if (id === "growth") {
    kv("discovered", p.discovered + " (capped " + p.capped + ")");
    kv("research intents", p.research_intents); kv("substrate-absent", p.substrate_absent);
    kv("spine-critical", p.spine_critical); kv("closure", p.closure);
  }
  host.innerHTML = rows.join("");
}

// ── The evolution desk — the ratify queue rendered in place (2026-07-20). Each
// drafted contract is a small card: the mined substance quoted, the source context
// behind a fold, the mint id + section target + status chip, and — for an OPEN row —
// ratify (server-mediated arm-to-fire) / hold / reject, each firing through the one
// lawful door (POST /evolution/*, armed + attributed). Any action refetches + re-
// renders through the board's own reload() (the dial-write idiom, verbatim). ──────
function renderEvolutionQueue(host, p) {
  host.innerHTML = "";
  const rows = p.queue || [];
  if (!rows.length) {
    // an empty panel must read "wrong corpus selected", never "dead feature":
    // name THIS corpus, and point at whoever actually has open intents.
    const elsewhere = Object.entries(p.elsewhere || {});
    const hint = elsewhere.length
      ? " · " + elsewhere.map(([c, n]) => esc(c) + " has " + n + " open").join(" · ") +
        " — switch corpus in the header to see them"
      : "";
    host.innerHTML = "<span class='pipe-none'>the ratify queue is empty for " +
      esc(PROJECT) + " — nothing drafted yet" + hint + "</span>";
  } else {
    const openRows = rows.filter((q) => q.status === "open");
    // the bulk door (evolution.ratify_mode: bulk-arm, his 2026-07-21 ruling):
    // one attributed word applied item-by-item server-side; offered only when
    // the dial opens it and more than one intent is open (a single intent's
    // per-item door is already the minimal act).
    if (p.ratify_mode === "bulk-arm" && openRows.length > 1)
      host.appendChild(evoBulkDoor(openRows.length));
    const list = document.createElement("div"); list.className = "pipe-evo-list";
    for (const q of rows) list.appendChild(evoRow(q));
    host.appendChild(list);
  }
  if (p.law) {
    const law = document.createElement("div"); law.className = "pipe-law";
    law.textContent = "Read-only panel; actions on these numbers happen at their own doors.";
    host.appendChild(law);
  }
}

// the bulk door — the same server-mediated arm-to-fire as per-item ratify (the
// unarmed POST returns the full preview of every application; the armed re-POST
// applies, stop-on-first-failure), with the same visible disarm countdown.
function evoBulkDoor(n) {
  const wrap = document.createElement("div"); wrap.className = "pipe-evo-bulk";
  wrap.innerHTML =
    "<button type='button' class='pipe-evo-btn pipe-evo-bulk-btn'>ratify all (" + n + ")</button>" +
    "<div class='pipe-evo-dry' style='display:none'></div>" +
    "<div class='pipe-evo-err'></div>";
  const btn = $(".pipe-evo-bulk-btn", wrap);
  const dry = $(".pipe-evo-dry", wrap);
  const err = $(".pipe-evo-err", wrap);
  const resting = "ratify all (" + n + ")";
  let armed = false, disarm = null, escH = null;
  const teardown = () => {
    if (disarm) disarm.clear();
    if (escH) { document.removeEventListener("keydown", escH); escH = null; }
    armed = false; dry.style.display = "none"; dry.innerHTML = "";
    btn.classList.remove("armed"); btn.disabled = false; btn.textContent = resting;
  };
  disarm = evoDisarmer(btn, teardown);
  btn.onclick = async (e) => {
    e.stopPropagation();
    err.textContent = ""; btn.disabled = true;
    let data;
    try {
      data = await store.fetchJSON("/evolution/ratify-all", { inject: [], method: "POST",
        body: { corpus: PROJECT, by: "gerard", armed } });
    } catch (ex) { err.textContent = (ex && ex.message) || String(ex); teardown(); return; }
    if (data && data.ok) { teardown(); await reload(); return; }
    if (data && data.needs_arming) {
      armed = true;
      dry.style.display = "";
      dry.innerHTML = "<div class='pipe-evo-dry-what'>" + esc(data.what || "") + "</div>" +
        (data.preview || []).map((q) =>
          "<div class='pipe-evo-dry-sub'>" + esc(q.intent_id) + " — “" + esc(q.substance || "") + "”</div>").join("");
      btn.classList.add("armed"); btn.disabled = false;
      disarm.start(resting + " — click again to apply");
      escH = (ev) => { if (ev.key === "Escape") teardown(); };
      document.addEventListener("keydown", escH);
      return;
    }
    teardown();
    // a stopped bulk apply reports exactly what landed and where it stopped.
    if (data && data.applied && data.failed) {
      err.textContent = "stopped at " + ((data.failed || {}).intent_id || "?") + " — applied " +
        data.applied.length + " first; the rest stay open";
      await reload(); return;
    }
    err.textContent = (data && data.error) || "ratify-all refused";
  };
  return wrap;
}

// the visible disarm (ergonomics, 2026-07-21): an armed button never lingers —
// a countdown ticks on the label and the button falls back to its resting state
// when it runs out. Client-side only (the server door stays two POSTs); 30s.
function evoDisarmer(btn, onDisarm) {
  const resting = btn.textContent;
  let timer = null;
  const clear = () => { if (timer) { clearInterval(timer); timer = null; } };
  const start = (armedLabel) => {
    clear();
    let left = 30;
    btn.textContent = armedLabel + " · " + left + "s";
    timer = setInterval(() => {
      left -= 1;
      if (left <= 0) {
        clear();
        btn.textContent = resting; btn.classList.remove("armed"); btn.disabled = false;
        if (onDisarm) onDisarm();
        return;
      }
      btn.textContent = armedLabel + " · " + left + "s";
    }, 1000);
  };
  return { start, clear };
}

function evoRow(q) {
  const row = document.createElement("div"); row.className = "pipe-evo-row";
  const cls = EVO_STATUS_CHIP[q.status] || "";
  const mints = (q.mint_ids || []).join(", ");
  const opsTxt = Object.entries(q.ops || {}).map(([k, v]) => k + " " + v).join(", ");
  // FINDING 6 — lead with the composed substance, not the raw CI- id. The status chip
  // rides beside the substance; the intent_id + mint slugs are DEMOTED to the mono
  // tail/tooltip idiom the derivation node-chip already uses (a small mono chip that
  // carries the raw id in its title, not the row's headline).
  row.innerHTML =
    "<div class='pipe-evo-head'>" +
      "<span class='hy-chip " + cls + "'>" + esc(q.status) + "</span>" +
      "<span class='pipe-evo-idtail' title='intent " + esc(q.intent_id) + "'>" + esc(q.intent_id) + "</span>" +
    "</div>" +
    "<div class='pipe-evo-sub'>“" + esc(q.substance || "(no substance mined)") + "”</div>" +
    (q.context_present
      ? "<details class='pipe-evo-ctx'><summary>source context</summary><div class='pipe-evo-ctx-body'>" +
        esc(q.context) + "</div></details>"
      : "") +
    "<div class='pipe-evo-meta'><span class='ek'>mint</span> " + esc(mints || "—") +
      (q.section_target ? " · <span class='ek'>section</span> " + esc(q.section_target) : "") +
      (opsTxt ? " · <span class='ek'>ops</span> " + esc(opsTxt) : "") +
    "</div>" +
    (q.hold_reason ? "<div class='pipe-evo-meta'><span class='ek'>reason</span> " + esc(q.hold_reason) + "</div>" : "") +
    (q.status === "open"
      ? "<div class='pipe-evo-actions'>" +
          "<button type='button' class='pipe-evo-ratify pipe-evo-btn' data-verb='ratify'>ratify</button>" +
          "<button type='button' class='pipe-evo-hold pipe-evo-btn' data-verb='hold'>hold</button>" +
          "<button type='button' class='pipe-evo-reject pipe-evo-btn destructive' data-verb='reject'>reject</button>" +
        "</div>" +
        "<div class='pipe-evo-note' style='display:none'></div>" +
        "<div class='pipe-evo-dry' style='display:none'></div>"
      : "") +
    "<div class='pipe-evo-err'></div>";
  if (q.status === "open") wireEvoActions(row, q.intent_id);
  return row;
}

function wireEvoActions(row, intentId) {
  wireEvoRatify(row, intentId);
  wireEvoNote(row, intentId, "hold", "note", "why hold (optional)…");
  wireEvoNote(row, intentId, "reject", "reason", "why reject (optional)…");
}

// RATIFY — the door itself is the arm-to-fire (evolution_surface.ratify): the first
// POST (armed omitted) returns 200 {ok:false, needs_arming:true, what, substance,
// mint_ids} — render that as the preview inline; the second POST carries armed:true
// and actually applies. Mirrors run-tray's needs_arming line, but server-mediated
// (two real network round-trips, not a client-only timer).
function wireEvoRatify(row, intentId) {
  const btn = $("[data-verb='ratify']", row);
  const dry = $(".pipe-evo-dry", row);
  const err = $(".pipe-evo-err", row);
  // Esc disarms (the selection/derivation idiom — his law: Esc disarms everywhere;
  // evolution ratify was the one armed door without it).
  let armed = false, disarm = null, escH = null;
  const teardown = () => {
    if (disarm) disarm.clear();
    if (escH) { document.removeEventListener("keydown", escH); escH = null; }
    armed = false; dry.style.display = "none"; dry.innerHTML = "";
    btn.classList.remove("armed"); btn.disabled = false; btn.textContent = "ratify";
  };
  disarm = evoDisarmer(btn, teardown);
  btn.onclick = async (e) => {
    e.stopPropagation();
    err.textContent = ""; btn.disabled = true;
    let data;
    try {
      data = await store.fetchJSON("/evolution/ratify", { inject: [], method: "POST",
        body: { corpus: PROJECT, intent_id: intentId, by: "gerard", armed } });
    } catch (ex) { err.textContent = (ex && ex.message) || String(ex); teardown(); return; }
    if (data && data.ok) { teardown(); await reload(); return; }
    if (data && data.needs_arming) {
      armed = true;
      dry.style.display = "";
      dry.innerHTML = "<div class='pipe-evo-dry-what'>" + esc(data.what || "") + "</div>" +
        (data.substance ? "<div class='pipe-evo-dry-sub'>“" + esc(data.substance) + "”</div>" : "") +
        ((data.mint_ids || []).length ? "<div class='pipe-evo-dry-mint'>mints " + esc(data.mint_ids.join(", ")) + "</div>" : "");
      btn.classList.add("armed"); btn.disabled = false;
      disarm.start("ratify — click again to apply");
      escH = (ev) => { if (ev.key === "Escape") teardown(); };
      document.addEventListener("keydown", escH);
      return;
    }
    teardown();
    err.textContent = (data && data.error) || "ratify refused";
  };
}

// HOLD / REJECT — an optional note/reason via a small inline input (the assess-
// comment idiom from assets-panes.mjs, letter for letter: an input revealed on
// click, a confirm button that fires the door). Click again to close, unfired.
function wireEvoNote(row, intentId, verb, field, placeholder) {
  const btn = $("[data-verb='" + verb + "']", row);
  const zone = $(".pipe-evo-note", row);
  const err = $(".pipe-evo-err", row);
  let open = false;
  btn.onclick = (e) => {
    e.stopPropagation();
    if (open) { zone.style.display = "none"; zone.innerHTML = ""; open = false; return; }
    open = true;
    zone.style.display = "";
    zone.innerHTML = "<input type='text' class='pipe-evo-note-in' placeholder='" + esc(placeholder) + "'>" +
      "<button type='button' class='pipe-evo-confirm pipe-evo-btn is-primary'>confirm " + esc(verb) + "</button>";
    const go = $(".pipe-evo-confirm", zone);
    const inp = $(".pipe-evo-note-in", zone);
    go.onclick = async (ev) => {
      ev.stopPropagation();
      go.disabled = true;
      const body = { corpus: PROJECT, intent_id: intentId, by: "gerard" };
      body[field] = inp.value || "";
      try {
        const data = await store.fetchJSON("/evolution/" + verb, { inject: [], method: "POST", body });
        if (data && data.ok) { await reload(); return; }
        err.textContent = (data && data.error) || (verb + " refused"); go.disabled = false;
      } catch (ex) { err.textContent = (ex && ex.message) || String(ex); go.disabled = false; }
    };
  };
}

// ── The fitness panel — selection's instrument, read-only (2026-07-20): the debt
// trajectory as a compact table (no charting idiom exists elsewhere in the chrome —
// a table is the declared default), the freeze verdict, the mechround pre/post/Δ, the
// suite floor, and the law string as a muted footer. Readings only — psi/phi stay his. ──
function renderFitnessPanel(host, p) {
  host.innerHTML = "";
  const wrap = document.createElement("div"); wrap.className = "pipe-fit";
  const traj = p.debt_trajectory || [];
  const trajHTML = traj.length
    ? "<div class='pipe-fit-traj-wrap'><table class='pipe-fit-traj'><thead><tr><th>at</th><th>n</th><th>source</th></tr></thead><tbody>" +
      traj.map((t) => "<tr><td>" + esc(t.at || "—") + "</td><td>" + esc(t.n == null ? "—" : t.n) +
        "</td><td>" + esc(t.source || "") + "</td></tr>").join("") + "</tbody></table></div>"
    : "<span class='pipe-none'>no debt trajectory banked for " + esc(PROJECT) + " yet</span>";
  const fz = p.freeze;
  const freezeHTML = fz
    ? "<div class='pipe-fit-line'><span class='ek'>freeze</span> " +
        "<span class='hy-chip " + (fz.pass ? "is-ok" : "is-warn") + "'>" + (fz.pass ? "pass" : "FAIL") + "</span>" +
        " · substance " + esc(fz.substance_pass == null ? "—" : (fz.substance_pass ? "pass" : "fail")) +
        " · mechanical " + esc(fz.mechanical_pass == null ? "—" : (fz.mechanical_pass ? "pass" : "fail")) +
        (fz.classes ? " · classes " + esc(JSON.stringify(fz.classes)) : "") +
      "</div>"
    : "<div class='pipe-fit-line pipe-none'>no freeze verdict banked yet</div>";
  const mr = p.mechround || {};
  const mechHTML = "<div class='pipe-fit-line'><span class='ek'>mechround</span> pre " +
    esc(mr.pre == null ? "—" : mr.pre) + " · post " + esc(mr.post == null ? "—" : mr.post) +
    " · Δ " + esc(mr.derivative == null ? "—" : mr.derivative) + "</div>";
  const sb = p.suite_baseline;
  const suiteHTML = sb
    ? "<div class='pipe-fit-line'><span class='ek'>suite floor</span> named-red " +
        esc(sb.named_red == null ? "—" : sb.named_red) +
        (sb.captured_at ? " · captured " + esc(sb.captured_at) : "") + "</div>"
    : "<div class='pipe-fit-line pipe-none'>no suite baseline captured yet</div>";
  wrap.innerHTML = trajHTML + freezeHTML + mechHTML + suiteHTML;
  host.appendChild(wrap);
  if (p.law) {
    const law = document.createElement("div"); law.className = "pipe-law";
    law.textContent = "Verdicts shown here are proposals from the versioned draft rule; your ruling is what gets recorded.";
    host.appendChild(law);
  }
}

// ── The selection sheet — heredity's ratify face (2026-07-21). Each scored
// generation is a card: the n/id/date header, a compact debt trajectory, the three
// gate chips (pass/fail/null, reasons behind a fold), the unmistakable DRAFT verdict
// badge, the retention line, and — for an UNRULED generation — the three rule doors
// (promote/hold/retire). The ruling is arm-then-bank through the one lawful door
// (POST /selection/rule): the first click previews the draft it would override + the
// readings digest ADJACENT to the button, the second banks it (30s disarm; Esc too).
// ψ/φ stay HIS — his overrides ARE the calibration signal. Any ruling refetches
// through the board's reload() (the dial-write idiom), so the new ruling row shows. ──
function renderSelectionSheet(host, p) {
  host.innerHTML = "";
  const wrap = document.createElement("div"); wrap.className = "pipe-sel";
  const gens = p.generations || [];
  const counts = p.counts || {};
  const rule = p.rule || {};
  const awaiting = p.awaiting_ruling_n || 0;
  const genN = counts.generations == null ? gens.length : counts.generations;
  // HIS rulings are distinct from the DRAFT tally (counts = the draft rule's proposal);
  // in the resting/all-ruled state the reader must not read the draft tally AS his ruling.
  const rulings = p.rulings || {};
  const his = { promote: 0, hold: 0, retire: 0 };
  for (const k in rulings) { const v = (rulings[k] || {}).verdict; if (his[v] != null) his[v] += 1; }
  const ruledN = Object.keys(rulings).length;
  // the await clause reads CALM when nothing is pending — a finished sheet says so,
  // it does not shout "0 awaiting"; it shouts only when his ruling is genuinely owed.
  const awaitClause = awaiting > 0
    ? "<span class='pipe-sel-await is-open'>" + esc(awaiting) + " awaiting his ruling</span>"
    : (genN > 0 ? "<span class='pipe-sel-await'>all " + esc(genN) + " ruled</span>" : "");
  const top = document.createElement("div"); top.className = "pipe-sel-top";
  top.innerHTML =
    "<span class='ek'>rule</span> <b>" + esc(rule.version || "draft-psi-v2") + "</b>" +
    " · <span class='ek'>generations</span> " + esc(genN) +
    " · <span class='ek'>draft</span> promote " + esc(counts.promote || 0) + " · hold " + esc(counts.hold || 0) + " · retire " + esc(counts.retire || 0) +
    (ruledN > 0 ? " · <span class='ek'>ruled</span> promote " + esc(his.promote) + " · hold " + esc(his.hold) + " · retire " + esc(his.retire) : "") +
    (awaitClause ? " · " + awaitClause : "");
  wrap.appendChild(top);
  if (!gens.length) {
    const none = document.createElement("div"); none.className = "pipe-none";
    none.textContent = "no scored generations for " + PROJECT +
      " yet — the sheet fills as heredity banks a generation per reprojection";
    wrap.appendChild(none); host.appendChild(wrap); return;
  }
  const list = document.createElement("div"); list.className = "pipe-sel-list";
  for (const g of gens) list.appendChild(selRow(g, p));          // newest-first (server order)
  wrap.appendChild(list);
  host.appendChild(wrap);
  // the rule's law line — the muted footer (the fitness p.law idiom).
  if (rule.law) {
    const law = document.createElement("div"); law.className = "pipe-law";
    law.textContent = "Draft verdicts come from the rule file named on the DRAFT chip; your ruling supersedes and is recorded.";
    host.appendChild(law);
  }
}

// one generation card — readings + the DRAFT verdict, then either HIS banked ruling
// (with the overrode/ratified flag) or the three rule doors.
function selRow(g, p) {
  const row = document.createElement("div"); row.className = "pipe-sel-row";
  const genId = String(g.id == null ? "" : g.id);
  const dv = g.draft_verdict || {};
  const gates = dv.gates || {};
  const ruling = (p.rulings || {})[genId];
  const ruled = !!ruling;
  const db = g.debt_before, da = g.debt_after, delta = g.debt_delta;
  const deltaStr = (delta == null) ? "—" : (delta > 0 ? "+" + delta : String(delta));
  const src = g.debt_before_source === "prev-generation" ? " (before = prev gen's after)" : "";
  const gateChips = Object.keys(gates).map((k) => {
    const gp = gates[k].pass;
    const st = gp === true ? "pass" : (gp === false ? "fail" : "null");
    return "<span class='hy-chip " + selGateChip(gp) + "'>" + esc(SEL_GATE_LABEL[k] || k) + " " + st + "</span>";
  }).join("");
  const reasons = [];
  for (const k of Object.keys(gates)) for (const r of (gates[k].reasons || [])) reasons.push(r);
  const reasonsHTML = reasons.length
    ? "<details class='pipe-sel-reasons'><summary>gate reasons · " + reasons.length + "</summary>" +
        "<div class='pipe-sel-reasons-body'>" + reasons.map((r) => "<div>" + esc(r) + "</div>").join("") + "</div></details>"
    : "";
  // the queued next act — an unclean R10 self-consistency finding names a structural
  // move (the mechanism's own MISMATCH_TABLE verb, joined server-side): e.g. a
  // contribution mismatch → RESPINE. Surfaced on the row so the resting sheet shows
  // not just the ruling but what it hands to the release machine next.
  const r10 = g.r10 || {};
  const nextActs = r10.restart_intents || [];
  const nextActHTML = (r10.clean === false && nextActs.length)
    ? "<div class='pipe-sel-nextact'><span class='ek'>R10</span> " +
        nextActs.map((a) => esc(a.mismatch) + " mismatch → <b>" + esc(a.verb) + "</b>").join(" · ") +
        " — the queued structural act</div>"
    : "";
  const ret = g.retention || {};
  const byFate = Object.entries(ret.by_fate || {}).map(([k, v]) => esc(k) + " " + esc(v)).join(" · ");
  const ruledHTML = ruled
    ? "<div class='pipe-sel-ruled'>" +
        "<span class='pipe-sel-hischip hy-chip " + (SEL_VERD_CHIP[ruling.verdict] || "") + "'>ruled · " + esc(ruling.verdict || "—") + "</span>" +
        (ruling.overrode_draft
          ? "<span class='hy-chip is-warn'>overrode draft · calibration signal</span>"
          : "<span class='hy-chip is-ok'>ratified draft</span>") +
      "</div>"
    : "<div class='pipe-sel-actions'>" +
        "<button type='button' class='pipe-sel-vbtn pipe-evo-btn' data-verd='promote'>promote</button>" +
        "<button type='button' class='pipe-sel-vbtn pipe-evo-btn' data-verd='hold'>hold</button>" +
        "<button type='button' class='pipe-sel-vbtn pipe-evo-btn destructive' data-verd='retire'>retire</button>" +
      "</div><div class='pipe-sel-arm' style='display:none'></div>";
  row.innerHTML =
    "<div class='pipe-sel-head'><span class='pipe-sel-n'>gen " + esc(g.n == null ? "?" : g.n) + "</span>" +
      "<span class='pipe-sel-id'>" + esc(genId || "—") + "</span>" +
      "<span class='pipe-sel-date'>" + esc(g.stamped_at || "") + "</span></div>" +
    "<div class='pipe-sel-traj'><span class='ek'>debt</span> " + esc(db == null ? "—" : db) + "→" + esc(da == null ? "—" : da) +
      " <span class='pipe-sel-delta'>Δ " + esc(deltaStr) + "</span>" + esc(src) + "</div>" +
    "<div class='pipe-sel-gates'>" + gateChips + "</div>" + reasonsHTML +
    "<div class='pipe-sel-draft'>" +
      "<span class='hy-chip pipe-sel-draftchip'>DRAFT · " + esc(dv.rule || (p.rule || {}).version || "draft-psi-v2") + "</span>" +
      "<span class='hy-chip " + (SEL_VERD_CHIP[dv.verdict] || "") + " pipe-sel-draftverd'>" + esc(dv.verdict || "—") + "</span></div>" +
    "<div class='pipe-sel-ret'><span class='ek'>retention</span> keys " + esc(ret.keys || 0) +
      " · author-ruled " + esc(ret.author_ruled || 0) + " · machine-superseded " + esc(ret.machine_superseded || 0) +
      (byFate ? " · " + byFate : "") + "</div>" +
    ruledHTML + nextActHTML +
    "<div class='pipe-sel-err'></div>";
  if (!ruled) wireSelectionRuling(row, genId);
  return row;
}

// arm-then-bank the ruling. Three real <button>s in DOM order (promote/hold/retire);
// only one is armed at a time (a shared row arm-state). The FIRST click POSTs unarmed
// → the server returns 200 {needs_arming, draft_verdict, readings_digest, what} which
// renders inline ADJACENT to the button; the SECOND click POSTs armed:true and banks.
// A typed refusal (400/404/409/422) renders inline at the button, never console-only.
// evoDisarmer runs the 30s countdown; Escape (scoped to the armed state) also disarms.
function wireSelectionRuling(row, genId) {
  const btns = $$(".pipe-sel-vbtn", row);
  const arm = $(".pipe-sel-arm", row);
  const err = $(".pipe-sel-err", row);
  let armedVerd = null, disarm = null, escH = null;
  const teardown = () => {
    if (disarm) { disarm.clear(); disarm = null; }
    if (escH) { document.removeEventListener("keydown", escH); escH = null; }
    armedVerd = null;
    arm.style.display = "none"; arm.innerHTML = "";
    for (const b of btns) { b.classList.remove("armed"); b.disabled = false; b.textContent = b.dataset.verd; }
  };
  for (const btn of btns) {
    const verd = btn.dataset.verd;
    btn.onclick = async (e) => {
      e.stopPropagation();
      err.textContent = "";
      const applying = armedVerd === verd;
      // his reasoning (banked as `reason`): read from the armed zone's textarea. REQUIRED
      // when his verdict differs from the draft (the override is the calibration signal, so
      // its grounds are owed) — block the bank + prompt when it is empty; optional when he
      // ratifies. Empty on the unarmed preview POST (the field does not exist yet).
      let reason = "";
      if (applying) {
        const ta = $(".pipe-sel-reason", arm);
        reason = ta ? (ta.value || "").trim() : "";
        if (ta && ta.dataset.owed === "1" && !reason) {
          err.textContent = "a reason is required when your verdict differs from the draft — the override is the calibration signal";
          ta.classList.add("is-owed"); ta.focus();
          return;                                     // stays armed; nothing posted
        }
      }
      if (armedVerd && !applying) teardown();     // switching verbs disarms the prior one
      btn.disabled = true;
      let data;
      try {
        data = await store.fetchJSON("/selection/rule", { inject: [], method: "POST",
          body: { corpus: PROJECT, generation_id: genId, verdict: verd, by: "gerard", armed: applying, reason } });
      } catch (ex) { err.textContent = (ex && ex.message) || String(ex); teardown(); return; }
      if (data && data.ok) { teardown(); await reload(); return; }
      if (data && data.needs_arming) {
        armedVerd = verd;
        const dg = data.readings_digest || {}, debt = dg.debt || [];
        const owed = !!(data.draft_verdict && verd !== data.draft_verdict);   // override → reason owed
        arm.style.display = "";
        arm.innerHTML =
          "<div class='pipe-sel-arm-what'>" + esc(data.what || "") + "</div>" +
          "<div class='pipe-sel-arm-draft'>draft verdict <b>" + esc(data.draft_verdict || "—") + "</b> · your <b>" + esc(verd) + "</b></div>" +
          "<div class='pipe-sel-arm-dig'>readings · debt " + esc(debt[0] == null ? "—" : debt[0]) + "→" + esc(debt[1] == null ? "—" : debt[1]) +
            " · freeze " + esc(dg.freeze_pass == null ? "—" : (dg.freeze_pass ? "pass" : "fail")) +
            " · r10 " + esc(dg.r10_clean == null ? "—" : (dg.r10_clean ? "clean" : "unclean")) + "</div>" +
          "<div class='pipe-sel-reasonlbl'>your reasoning" +
            (owed ? " <span class='req'>· required — your verdict differs from the draft</span>"
                  : " <span>· optional — you are ratifying the draft</span>") + "</div>" +
          "<textarea class='pipe-sel-reason" + (owed ? " is-owed" : "") + "' data-owed='" + (owed ? "1" : "0") +
            "' placeholder='" + (owed ? "why you differ from the draft (required)…" : "why (optional)…") + "'></textarea>" +
          "<div class='pipe-sel-arm-note'>agreeing ratifies, differing overrides — both banked, override is calibration signal</div>";
        btn.classList.add("armed"); btn.disabled = false;
        const ta0 = $(".pipe-sel-reason", arm);
        if (ta0) { ta0.addEventListener("input", () => { if (ta0.value.trim()) { ta0.classList.remove("is-owed"); err.textContent = ""; } }); ta0.focus(); }
        disarm = evoDisarmer(btn, teardown);
        disarm.start(verd + " — click again to bank");
        escH = (ev) => { if (ev.key === "Escape") teardown(); };
        document.addEventListener("keydown", escH);
        return;
      }
      teardown();
      err.textContent = (data && data.error) || (verd + " refused");
    };
  }
}

// ── The derivation face — the aspiration-first reach organ (2026-07-21). INSPECTION:
// the maximal TRUE claim rendered plainly at the top (it IS the boundary condition —
// styled like one), the reach axes + demonstrandum behind folds, the isnad chain
// link-by-link with attestation chips (derived/computed/cited teal vs GAP warn, its
// why visible), the reach headline, forged fragments openable (GET /derivation/
// fragment), the law as the muted footer. INTERACTION: re-scope the boundary claim
// (arm-then-bank), forge a GAP link (banks a work-order), contest any link (a later
// record) — each arm-then-bank through the derivation face's OWN doors, ≤3 clicks,
// adjacent previews, Esc disarms, inline refusals, reload-in-place. ──────────────────
function renderDerivationSheet(host, p) {
  host.innerHTML = "";
  const wrap = document.createElement("div"); wrap.className = "pipe-der";
  const asp = p.aspiration || {};
  const reach = p.reach || {};
  const chain = p.chain || [];
  const frontierN = reach.frontier_n || 0;
  // the reach headline — how far UP the aspiration the attested isnad got.
  const top = document.createElement("div"); top.className = "pipe-der-top";
  top.innerHTML =
    "<span class='ek'>reach</span> <b>" + esc(reach.links_attested || 0) + "/" + esc(reach.links_total || 0) + "</b> attested" +
    " · <span class='ek'>depth</span> " + esc(reach.depth_attested || 0) +
    " · <span class='pipe-der-frontier" + (frontierN > 0 ? " is-open" : "") + "'>" + esc(frontierN) + " named gap" + (frontierN === 1 ? "" : "s") + "</span>";
  wrap.appendChild(top);
  // the boundary condition — claim_maximal rendered plainly, styled AS a boundary.
  const claim = document.createElement("div"); claim.className = "pipe-der-claim";
  const axes = asp.reach_axes || {};
  const axesHTML = Object.keys(axes).length
    ? "<div class='pipe-der-axes'>" + ["reach", "scope", "impact"].filter((k) => axes[k]).map((k) =>
        "<div class='pipe-der-axis'><span class='ek'>" + esc(k) + "</span> " + esc(axes[k]) + "</div>").join("") + "</div>"
    : "";
  claim.innerHTML =
    "<div class='pipe-der-claim-h'>boundary condition · the maximal true claim (asserted before achievability)</div>" +
    "<div class='pipe-der-claim-body'>" + esc(asp.claim_maximal || "(no aspiration banked — re-scope to assert the boundary condition)") + "</div>" +
    axesHTML;
  wrap.appendChild(claim);
  // the re-scope door (arm-then-bank a new boundary claim).
  wrap.appendChild(rescopeDoor(asp));
  // the demonstrandum behind a fold.
  const demo = asp.demonstrandum || [];
  if (demo.length) {
    const d = document.createElement("details"); d.className = "pipe-der-demo";
    d.innerHTML = "<summary>demonstrandum · " + demo.length + "</summary>" +
      "<div class='pipe-der-demo-body'>" + demo.map((s) => "<div>" + esc(s) + "</div>").join("") + "</div>";
    wrap.appendChild(d);
  }
  // the chain link-by-link — headed with a two-word gloss (first use of "isnad" on
  // the card: the attested chain of derivation from substrate toward the claim).
  if (chain.length) {
    const lh = document.createElement("div"); lh.className = "pipe-der-listhead";
    lh.textContent = "the isnad — the attested chain of derivation";
    wrap.appendChild(lh);
    const list = document.createElement("div"); list.className = "pipe-der-list";
    for (const l of chain) list.appendChild(derRow(l));
    wrap.appendChild(list);
  } else {
    const none = document.createElement("div"); none.className = "pipe-none";
    none.textContent = "no isnad chain (the attested chain of derivation) banked for " +
      PROJECT + " yet — re-scope the boundary claim above, then forge its first link";
    wrap.appendChild(none);
  }
  host.appendChild(wrap);
  // the law line — the muted footer (the fitness p.law idiom).
  if (p.law) {
    const law = document.createElement("div"); law.className = "pipe-law";
    law.textContent = "Verified links carry their derivation or computation; unverified links are listed as open.";
    host.appendChild(law);
  }
}

// one isnad link — the attestation chip (attested/GAP), the from→to flow, the named
// why for a gap + any contests, then the acts: an attested link opens its forged .tex
// and can be contested; a gap link is forged (banks a work-order) and can be contested.
function derRow(l) {
  const row = document.createElement("div");
  const gap = l.status === "gap";
  row.className = "pipe-der-row " + (gap ? "is-gap" : "is-attested");
  const chip = gap
    ? "<span class='hy-chip is-warn'>GAP</span>"
    : "<span class='hy-chip " + (DER_KIND_CHIP[l.kind] || "is-ok") + "'>" + esc(l.kind || "attested") + "</span>";
  const contests = l.contests || [];
  const contestsHTML = contests.length
    ? "<div class='pipe-der-contests'>" + contests.map((c) =>
        "<div class='pipe-der-contest'>contested by " + esc(c.by || "?") + " — " + esc(c.reason || "") + "</div>").join("") + "</div>"
    : "";
  const acts = [];
  if (!gap && l.fragment_available)
    acts.push("<button type='button' class='pipe-der-btn' data-act='fragment'>open derivation</button>");
  if (gap)
    acts.push("<button type='button' class='pipe-der-btn' data-act='forge'>forge</button>");
  acts.push("<button type='button' class='pipe-der-btn destructive' data-act='contest'>contest</button>");
  // the node_id join chip (the isnad↔conceptric link made explicit) — a small mono
  // chip that IS a door to the applied conceptric node (/conceptric?node=…), the
  // artefact-panes node-chip idiom. Present only once the ratified intent has joined.
  const nodeChip = l.node_id
    ? "<a href='/conceptric?corpus=" + esc(PROJECT) + "&node=" + esc(l.node_id) +
      "' class='hy-chip pipe-der-node' title='conceptric node " + esc(l.node_id) + "'>" +
      esc(String(l.node_id).replace(/^derivation:/, "")) + "</a>"
    : "";
  row.innerHTML =
    "<div class='pipe-der-head'>" + chip +
      "<span class='pipe-der-id'>" + esc(l.id) + "</span>" + nodeChip + "</div>" +
    "<div class='pipe-der-flow'>" + esc(l.from || "?") + " <span class='arrow'>→</span> " + esc(l.to || "?") + "</div>" +
    (gap && l.why ? "<div class='pipe-der-why'>" + esc(l.why) + "</div>" : "") +
    (!gap && l.attestation ? "<div class='pipe-der-attest'>" + esc(l.attestation) + "</div>" : "") +
    contestsHTML +
    "<div class='pipe-der-actions'>" + acts.join("") + "</div>" +
    "<div class='pipe-der-frag' style='display:none'></div>" +
    "<div class='pipe-der-arm' style='display:none'></div>" +
    "<div class='pipe-der-err'></div>";
  wireDerRow(row, l);
  return row;
}

function wireDerRow(row, l) {
  const err = $(".pipe-der-err", row);
  const frag = $(".pipe-der-frag", row);
  const fb = $("[data-act='fragment']", row);
  if (fb) {
    let shown = false;
    fb.onclick = async (e) => {
      e.stopPropagation();
      if (shown) { frag.style.display = "none"; shown = false; fb.textContent = "open derivation"; return; }
      fb.disabled = true;
      try {
        const data = await store.fetchJSON("/derivation/fragment", { inject: [],
          params: { corpus: PROJECT, link: l.id } });
        frag.textContent = (data && data.tex) || "(empty fragment)";
        frag.style.display = ""; shown = true; fb.textContent = "hide derivation";
      } catch (ex) { err.textContent = (ex && ex.message) || String(ex); }
      fb.disabled = false;
    };
  }
  const forgeBtn = $("[data-act='forge']", row);
  if (forgeBtn) wireDerArm(row, forgeBtn, "/derivation/forge",
    () => ({ corpus: PROJECT, link_id: l.id, by: "gerard" }), "forge");
  const contestBtn = $("[data-act='contest']", row);
  if (contestBtn) wireDerContest(row, contestBtn, l);
}

// the shared arm-then-bank for a derivation act (forge): first click POSTs unarmed →
// the server returns needs_arming + a `what`/`brief` preview rendered ADJACENT to the
// button; the second click POSTs armed:true and banks. evoDisarmer runs the 30s
// countdown; Escape (scoped to the armed state) also disarms. Any bank reload()s.
function wireDerArm(row, btn, url, bodyFn, verb) {
  const arm = $(".pipe-der-arm", row);
  const err = $(".pipe-der-err", row);
  let armed = false, disarm = null, escH = null;
  const teardown = () => {
    if (disarm) { disarm.clear(); disarm = null; }
    if (escH) { document.removeEventListener("keydown", escH); escH = null; }
    armed = false; arm.style.display = "none"; arm.innerHTML = "";
    btn.classList.remove("armed"); btn.disabled = false; btn.textContent = verb;
  };
  btn.onclick = async (e) => {
    e.stopPropagation();
    err.textContent = ""; btn.disabled = true;
    let data;
    try {
      data = await store.fetchJSON(url, { inject: [], method: "POST",
        body: Object.assign(bodyFn(), { armed }) });
    } catch (ex) { err.textContent = (ex && ex.message) || String(ex); teardown(); return; }
    if (data && data.ok) { teardown(); await reload(); return; }
    if (data && data.needs_arming) {
      armed = true;
      arm.style.display = "";
      // FINDING 4 — the PSU class the backend declares (forge banks a model-heavy
      // work-order); render it as the converge organ does, inline before the bank click.
      const psu = data.cost_class || "model-heavy";
      arm.innerHTML = "<div class='pipe-der-arm-what'>" + esc(data.what || "") +
        " " + derPsuChip(psu, psu === "model-heavy" ? "banks a work-order" : "") + "</div>" +
        (data.brief ? "<div class='pipe-der-arm-note'>" + esc(data.brief) + "</div>" : "");
      btn.classList.add("armed"); btn.disabled = false;
      disarm = evoDisarmer(btn, teardown);
      disarm.start(verb + " — click again to bank");
      escH = (ev) => { if (ev.key === "Escape") teardown(); };
      document.addEventListener("keydown", escH);
      return;
    }
    teardown();
    err.textContent = (data && data.error) || (verb + " refused");
  };
}

// contest — a reason is required (a contest must state its grounds), so the button
// reveals an inline reason field + its own arm-then-bank. reveal(1) + arm(2) + bank(3)
// = ≤3 clicks. The unarmed POST previews (status carried unchanged); the armed banks.
function wireDerContest(row, btn, l) {
  const arm = $(".pipe-der-arm", row);
  const err = $(".pipe-der-err", row);
  let open = false, armed = false, disarm = null, escH = null;
  const teardown = () => {
    if (disarm) { disarm.clear(); disarm = null; }
    if (escH) { document.removeEventListener("keydown", escH); escH = null; }
    open = false; armed = false; arm.style.display = "none"; arm.innerHTML = "";
    btn.classList.remove("armed"); btn.disabled = false; btn.textContent = "contest";
  };
  btn.onclick = (e) => {
    e.stopPropagation();
    if (open) { teardown(); return; }
    open = true; err.textContent = "";
    arm.style.display = "";
    arm.innerHTML =
      "<div class='pipe-der-arm-what'>contest link " + esc(l.id) + " — its status (" + esc(l.status) + ") stays unchanged; the contest rides as a later record " +
        derPsuChip("local-safe", "record-only") + "</div>" +
      "<input type='text' class='pipe-der-in pipe-der-reason' placeholder='why contest this link (required)…'>" +
      "<button type='button' class='pipe-der-btn destructive pipe-der-cbank'>contest</button>";
    const bank = $(".pipe-der-cbank", arm);
    const inp = $(".pipe-der-reason", arm);
    bank.onclick = async (ev) => {
      ev.stopPropagation();
      err.textContent = ""; bank.disabled = true;
      let data;
      try {
        data = await store.fetchJSON("/derivation/contest", { inject: [], method: "POST",
          body: { corpus: PROJECT, link_id: l.id, by: "gerard", reason: inp.value || "", armed } });
      } catch (ex) { err.textContent = (ex && ex.message) || String(ex); bank.disabled = false; return; }
      if (data && data.ok) { teardown(); await reload(); return; }
      if (data && data.needs_arming) {
        armed = true;
        bank.classList.add("armed"); bank.disabled = false;
        disarm = evoDisarmer(bank, () => { armed = false; });
        disarm.start("contest — click again to bank");
        escH = (evk) => { if (evk.key === "Escape") teardown(); };
        document.addEventListener("keydown", escH);
        return;
      }
      bank.disabled = false;
      err.textContent = (data && data.error) || "contest refused";
    };
  };
}

// re-scope the boundary claim — a textarea for the new maximal claim + arm-then-bank.
// The prior banks to aspiration_history.jsonl; aspiration.json stays the latest-pointer.
function rescopeDoor(asp) {
  const z = document.createElement("div");
  z.innerHTML =
    "<div class='pipe-der-actions'><button type='button' class='pipe-der-btn' data-act='rescope'>re-scope the boundary claim</button></div>" +
    "<div class='pipe-der-arm' style='display:none'></div>" +
    "<div class='pipe-der-err'></div>";
  const btn = $("[data-act='rescope']", z);
  const arm = $(".pipe-der-arm", z);
  const err = $(".pipe-der-err", z);
  let open = false, armed = false, disarm = null, escH = null;
  const teardown = () => {
    if (disarm) { disarm.clear(); disarm = null; }
    if (escH) { document.removeEventListener("keydown", escH); escH = null; }
    open = false; armed = false; arm.style.display = "none"; arm.innerHTML = "";
    btn.classList.remove("armed"); btn.disabled = false; btn.textContent = "re-scope the boundary claim";
  };
  btn.onclick = (e) => {
    e.stopPropagation();
    if (open) { teardown(); return; }
    open = true; err.textContent = "";
    arm.style.display = "";
    arm.innerHTML =
      "<div class='pipe-der-arm-what'>re-scope: banks the prior claim to aspiration_history.jsonl, then rewrites the aspiration.json pointer " +
        derPsuChip("local-safe", "record-only") + "</div>" +
      "<textarea class='pipe-der-in pipe-der-claiminp' placeholder='the new maximal true claim (the boundary condition)…'></textarea>" +
      "<input type='text' class='pipe-der-in pipe-der-reasoninp' placeholder='why re-scope (optional)…'>" +
      "<button type='button' class='pipe-der-btn pipe-der-rbank'>re-scope</button>";
    const bank = $(".pipe-der-rbank", arm);
    const claimInp = $(".pipe-der-claiminp", arm);
    const reasonInp = $(".pipe-der-reasoninp", arm);
    bank.onclick = async (ev) => {
      ev.stopPropagation();
      err.textContent = ""; bank.disabled = true;
      let data;
      try {
        data = await store.fetchJSON("/derivation/rescope", { inject: [], method: "POST",
          body: { corpus: PROJECT, by: "gerard", claim: claimInp.value || "",
                  reason: reasonInp.value || "", armed } });
      } catch (ex) { err.textContent = (ex && ex.message) || String(ex); bank.disabled = false; return; }
      if (data && data.ok) { teardown(); await reload(); return; }
      if (data && data.needs_arming) {
        armed = true;
        const sup = data.supersedes ? "<div class='pipe-der-arm-note'>supersedes: " + esc(data.supersedes) + "</div>" : "";
        if (sup && !$(".pipe-der-arm-note", arm)) bank.insertAdjacentHTML("beforebegin", sup);
        bank.classList.add("armed"); bank.disabled = false;
        disarm = evoDisarmer(bank, () => { armed = false; });
        disarm.start("re-scope — click again to bank");
        escH = (evk) => { if (evk.key === "Escape") teardown(); };
        document.addEventListener("keydown", escH);
        return;
      }
      bank.disabled = false;
      err.textContent = (data && data.error) || "re-scope refused";
    };
  };
  return z;
}

function evidenceZone(o) {
  const z = document.createElement("div"); z.className = "pipe-zone";
  const ev = o.evidence || {};
  let body = "";
  if (ev.phase !== undefined) {
    body = "<div class='pipe-ev'>" +
      "<span><span class='ek'>phase</span> " + esc(ev.phase) + "</span>" +
      "<span><span class='ek'>round</span> " + esc(ev.current_round == null ? "—" : ev.current_round) + " · " + esc(ev.rounds_so_far || 0) + " so far</span>" +
      (ev.open_findings != null ? "<span><span class='ek'>open findings</span> " + esc(ev.open_findings) + "</span>" : "") +
      ((ev.artifacts || []).length ? ev.artifacts.map((a) => "<span><span class='ek'>" + esc(a.kind) + "</span> " + esc(a.path) + "</span>").join("") : "") +
      "</div>";
  } else {
    // E4b — five DISTINCT terminal-stage evidence objects (never one shared blob):
    // each renders exactly the record IT banks, keyed by ev.kind, and names its P7
    // filler when the machine has not reached the stage (truthful-empty, not blank).
    const rows = [];
    const fills = ev.fills
      ? "<span class='pipe-none'>waiting on: " + esc(ev.fills) + "</span>" : "";
    if (ev.kind === "review") {
      const snaps = ev.snapshots || [];
      rows.push(snaps.length
        ? "<span><span class='ek'>review snapshots</span> " + esc(snaps.join(", ")) + "</span>"
        : "<span class='pipe-none'>no AUTHOR_REVIEWED snapshot yet</span>");
    } else if (ev.kind === "final_build") {
      const fin = ev.finalize;
      rows.push(fin
        ? "<span><span class='ek'>finalize</span> " + esc(fin.slug || "") + " r" + esc(fin.revision || "?") + " · " + esc(fin.pdf_path || "") + "</span>"
        : "<span class='pipe-none'>no finalize record yet</span>");
    } else if (ev.kind === "final_gates") {
      rows.push(ev.finalize_slug
        ? "<span><span class='ek'>gates over</span> " + esc(ev.finalize_slug) + "</span>"
        : "<span class='pipe-none'>no finalised build to gate yet</span>");
    } else if (ev.kind === "accept") {
      rows.push(ev.bundle
        ? "<span><span class='ek'>accept bundle</span> " + esc(ev.bundle) + "</span>"
        : "<span class='pipe-none'>no bundle bound yet</span>");
    } else {                                    // release
      const arts = ev.bundles || [];
      rows.push(arts.length
        ? "<span><span class='ek'>bundles</span> " + esc(arts.join(", ")) + "</span>"
        : "<span class='pipe-none'>no release bundle yet</span>");
      if (ev.artefact)
        rows.push("<span><span class='ek'>artefact</span> " + esc(ev.artefact.pdf || ev.artefact.version_id || "") + " (" + esc(ev.artefact.kind || "") + ")</span>");
    }
    if (ev.present === false && fills) rows.push(fills);
    body = "<div class='pipe-ev'>" + rows.join("") + "</div>";
  }
  z.innerHTML = "<div class='pipe-zh'>evidence" + infoTag(o.producer || "") + "</div>" + body;
  return z;
}

// ── The dry-run preview (in the same card, BEFORE any arm) — "what would fire": the live
// settings a fire at this stage would apply (read from the profile). It re-renders on every
// board reload, so editing a dial above visibly updates the preview (the pre-arm read the
// contract demands — nothing fires here). The scoped controls below add their /storyboard/
// propagate worklist on arm; this zone is the always-present, dial-reactive half. ──
function dryVal(k) {
  if (k.kind === "bool") return k.value ? "on" : "off";
  if (k.kind === "list") return ((k.value || []).join(", ")) || "—";
  return (k.value === "" || k.value == null) ? "—" : String(k.value);
}
function dryRunZone(o) {
  // Lane 4 — the one live dry-run: the figures sub-organ renders a TRUE preview
  // (matched/absent) fetched from its &dryrun=1 door, not the generic dial settings.
  if (o.live_dry_run_door) return liveDryZone(o);
  const z = document.createElement("div"); z.className = "pipe-zone pipe-dry";
  const dials = o.dials || [], ctrls = o.controls || [];
  let body;
  if (dials.length) {
    body = "<div class='pipe-dry-lead'>firing <b>" + esc(o.label) +
      "</b> would run with these live settings — edit a dial above and this preview updates:</div>" +
      "<div class='pipe-dry-sets'>" + dials.map((k) =>
        "<span class='pipe-dry-set'><code>" + esc(k.path) + "</code> = <b>" + esc(dryVal(k)) +
        "</b></span>").join("") + "</div>";
  } else if (ctrls.length) {
    // the immediate effect depends on cost: a model-heavy fire BANKS a work-order the
    // pickup loop runs; a local-safe fire applies the release defaults now (offer law).
    const heavy = ctrls.some((c) => c.cost_class === "model-heavy");
    body = "<div class='pipe-dry-lead'>no calibration knobs at this stage — firing <b>" +
      esc(o.label) + "</b> " + (heavy
        ? "banks a work-order the pickup loop runs (offer law)"
        : "applies the release defaults") +
      "; each scoped fire below previews its worklist on arm.</div>";
  } else {
    body = "<div class='pipe-none'>nothing to fire here — this stage advances on the machine's " +
      "own transition (no scoped verb, no dial).</div>";
  }
  z.innerHTML = "<div class='pipe-zh'>dry-run · what would fire — before any arm" +
    infoTag("the pre-arm read: the live settings a fire at this stage would apply (from the " +
            "profile, GET /pipeline/chain) + the worklist each scoped arm reveals (GET " +
            "/storyboard/propagate, pure read). Nothing fires until a verb is armed.") +
    "</div>" + body;
  return z;
}

// ── The live dry-run zone (Lane 4, figures) — the one organ whose dry-run is a real
// live preview: fetch the &dryrun=1 door (run(apply=False, run_gen=False), proven
// non-mutating) and render the matched/absent verdict per promise BEFORE any arm. ──
function liveDryZone(o) {
  const z = document.createElement("div"); z.className = "pipe-zone pipe-dry";
  z.innerHTML = "<div class='pipe-zh'>dry-run · live preview — before any arm" +
    infoTag("the one live dry-run: run(apply=False, run_gen=False) computes promises/" +
            "matches and mutates nothing (GET " + esc(o.live_dry_run_door) + "). A full " +
            "materialize runs the generators — banks a work-order.") +
    "</div><div class='pipe-ev pipe-suboev'></div>";
  const host = $(".pipe-suboev", z);
  const cached = SUB_EV[o.id + "::dry"];
  if (cached !== undefined) renderLiveDry(host, cached);
  else { host.innerHTML = "<span class='pipe-none'>computing live preview…</span>"; loadLiveDry(host, o); }
  return z;
}

async function loadLiveDry(host, o) {
  try {
    const data = await store.fetchJSON("/pipeline/organ", { inject: [],
      params: { project: PROJECT, organ: o.id, dryrun: 1 } });
    SUB_EV[o.id + "::dry"] = (data && data.payload) || {};
    renderLiveDry(host, SUB_EV[o.id + "::dry"]);
  } catch (e) {
    host.innerHTML = "<span class='pipe-none'>live preview unavailable — " + esc((e && e.message) || e) + "</span>";
  }
}

function renderLiveDry(host, p) {
  if (!p || p.present === false) {
    host.innerHTML = "<span class='pipe-none'>" + esc((p && p.note) ||
      "no banked manifest names a generator script — fire figure-materialize (banks a work-order) to establish one") + "</span>";
    return;
  }
  const rows = ["<span><span class='ek'>live</span> matched " + esc(p.matched_count) +
                " · absent " + esc(p.unmatched_count) + "</span>"];
  for (const f of (p.placed || []))
    rows.push("<span><span class='ek'>" + esc(f.promise) + "</span> " +
      (f.matched ? "matched → " + esc(f.placed_at || f.generator || "?")
                 : "promised-but-absent") + "</span>");
  host.innerHTML = rows.join("");
}

// ── Dials in place — each knob a control; edit → /dials/op, reset → /dials/op, undo → /dials/undo. ──
function dialsZone(o) {
  const z = document.createElement("div"); z.className = "pipe-zone";
  const knobs = o.dials || [];
  const head = "<div class='pipe-zh'>dials in place · <span style='font-weight:700'>" + esc(CHAIN.profile) + "</span>" +
    infoTag("edit → POST /dials/op · reset → POST /dials/op (reset-leaf) · undo → POST /dials/undo — the one write path (dials_surface)") +
    "<button type='button' class='pipe-undo'" + (CHAIN.dials_base_present ? "" : " disabled title='nothing banked to undo'") + ">undo last</button></div>";
  if (!knobs.length) { z.innerHTML = head + "<div class='pipe-none'>no dials — this organ reads no calibration knob.</div>"; wireUndo(z); return z; }
  z.innerHTML = head + "<div class='pipe-dials'></div>";
  const dh = $(".pipe-dials", z);
  for (const k of knobs) dh.appendChild(dialRow(k));
  wireUndo(z);
  return z;
}

function wireUndo(z) {
  const u = $(".pipe-undo", z);
  if (u && !u.disabled) u.onclick = (e) => { e.stopPropagation(); dialUndo(u); };
}

// ── HIS COMMISSION (9b) — the PROMPTS VIEW: the REAL prompt text the dispatch layer
// composes (schema constants + override provenance), per worker role. A read-only door on
// the global roles/prompts card; the genuine template renders, a dispatch-time-composed
// prompt shows the template + a fold note (never a fabricated specimen). Mono at depth. ──
function promptsZone() {
  const z = document.createElement("div"); z.className = "pipe-zone";
  z.innerHTML = "<div class='pipe-zh'>the actual prompts" +
    infoTag("GET /pipeline/prompts → the genuine dispatch templates (schema constants) + " +
            "override provenance, per worker role. A prompt only fully composed at dispatch " +
            "(with a live packet / voice profile / node graph) shows the template + a worded " +
            "fold note, never a fabricated specimen composition.") +
    "<button type='button' class='pipe-prompts-btn'>view the real prompts →</button></div>" +
    "<div class='pipe-prompts-body'></div>";
  const btn = $(".pipe-prompts-btn", z);
  const body = $(".pipe-prompts-body", z);
  let open = false;
  btn.onclick = async (e) => {
    e.stopPropagation();
    if (open) { body.innerHTML = ""; open = false; btn.textContent = "view the real prompts →"; return; }
    open = true; btn.textContent = "hide the prompts"; btn.disabled = true;
    body.innerHTML = "<span class='pipe-none'>reading the dispatch templates…</span>";
    try {
      const data = await store.fetchJSON("/pipeline/prompts", { inject: [], params: { project: PROJECT } });
      renderPrompts(body, data);
    } catch (ex) { body.innerHTML = "<span class='pipe-none'>prompts unavailable — " + esc((ex && ex.message) || ex) + "</span>"; }
    btn.disabled = false;
  };
  return z;
}

function renderPrompts(host, p) {
  const parts = ["<div class='pipe-pr-site'>" + esc(p.composition_site || "") + "</div>"];
  const roles = Object.entries(p.roles || {});
  if (roles.length) parts.push("<div class='pipe-pr-h'>roles · model / effort tiers (the roles dial group)</div>" +
    "<div class='pipe-pr-roles'>" + roles.map(([r, v]) =>
      "<span class='pipe-pr-role'><b>" + esc(r) + "</b> " + esc(v.model) + " · " + esc(v.effort) + "</span>").join("") + "</div>");
  if ((p.workers || []).length) parts.push("<div class='pipe-pr-h'>workers · the composed prompt per dispatch role</div>" +
    (p.workers).map((w) =>
      "<details class='pipe-pr-w'><summary><b>" + esc(w.worker) + "</b> · " + esc(w.model) + " · " + esc(w.effort) + "</summary>" +
        "<div class='pipe-pr-fold'><span class='ek'>folded at dispatch</span> " + esc(w.folded_at_dispatch) + "</div></details>").join(""));
  const tpl = p.templates || {};
  if (Object.keys(tpl).length) parts.push("<div class='pipe-pr-h'>the genuine static templates (the composer's own constants)</div>" +
    Object.entries(tpl).map(([name, t]) =>
      "<details class='pipe-pr-t'><summary>" + esc(name) + " · <span class='pipe-pr-src'>" + esc(t.source) + "</span></summary>" +
        "<pre class='pipe-pr-text'>" + esc(t.text) + "</pre></details>").join(""));
  const ov = p.overrides || {};
  parts.push("<div class='pipe-pr-h'>prompt overrides · " + esc(ov.dir || "") + "</div>" +
    "<div class='pipe-pr-rule'>" + esc(ov.rule || "") + "</div>" +
    ((ov.present || []).length
      ? (ov.present).map((f) =>
          "<details class='pipe-pr-t'><summary>" + esc(f.name) + "." + esc(f.ext) +
            " · <span class='pipe-pr-src'>" + esc(f.path) + " · " + esc(f.bytes) + " bytes</span></summary>" +
            "<pre class='pipe-pr-text'>" + esc(f.text) + "</pre></details>").join("")
      : "<div class='pipe-none'>no override files present — every built-in template stands.</div>") +
    (ov.note ? "<div class='pipe-pr-note'>" + esc(ov.note) + "</div>" : ""));
  if (p.law) parts.push("<div class='pipe-law'>" + esc(p.law) + "</div>");
  host.innerHTML = parts.join("");
}

function dialRow(k) {
  const row = document.createElement("div"); row.className = "pipe-dial"; row.dataset.path = k.path;
  const inOverlay = k.source === "overlay";
  row.innerHTML =
    "<div class='dpath' title='" + esc(k.path) + "'>" + esc(k.path) + "</div>" +
    "<div class='dctl'>" + controlHTML(k) + "</div>" +
    "<span class='pipe-prov " + (inOverlay ? "overlay" : "") + "'>" + (inOverlay ? "overlay" : "default") + "</span>" +
    "<button type='button' class='pipe-reset'" + (inOverlay ? "" : " disabled") + ">reset</button>";
  const ctl = $(".dctl .ctl", row);
  const commit = (e) => { if (e) e.stopPropagation();
    const v = parseVal(k.kind, ctl, row); if (v === null) return;
    // the dial-cannot-override-the-gate law (Lane 3 / RISK 2): arming enabled=on for a
    // store whose holdout gate is absent/failed would SystemExit at run — surface the
    // refusal inline and REVERT the toggle instead of POSTing a config that will crash.
    if (k.gate && v === true && !k.gate.passed) {
      gateRefuse(row, k); if (ctl.type === "checkbox") ctl.checked = false; return;
    }
    dialWrite({ kind: "set-leaf", path: k.path, value: v }, row); };
  if (ctl) {
    ctl.addEventListener("change", commit);
    // FINDING 5 — Enter in a text/number/list dial input commits (it was a silent
    // no-op; commit fired only on blur/change). Bind Enter to the SAME commit handler.
    ctl.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); commit(e); }
    });
  }
  const rb = $(".pipe-reset", row);
  if (rb && !rb.disabled) rb.onclick = (e) => { e.stopPropagation(); dialWrite({ kind: "reset-leaf", path: k.path }, row); };

  // HIS COMMISSION (9a) — the worded meaning + stage effect IN PLACE, current-vs-default,
  // the consuming organ named, and the ledger history one act deep. The wrap always holds
  // the row; the gate line (CHIP law) rides it as before (pipe-gaterow class preserved so
  // gateRefuse still finds it). Where the meaning is not in code/docs, we SAY so.
  const wrap = document.createElement("div");
  wrap.className = "pipe-dial-wrap" + (k.gate ? " pipe-gaterow" : "");
  wrap.appendChild(row);
  wrap.appendChild(dialMeaning(k));
  if (k.gate) {
    const g = document.createElement("div"); g.className = "pipe-gate";
    g.innerHTML = "gate <span class='hy-chip " + (GATE_CHIP[k.gate.state] || "") + "'>" + esc(k.gate.state) + "</span>" +
      (k.gate.passed ? "" : "<span class='pipe-gate-r'>arming refused: " + esc(k.gate.refusal || "gate not passed") + "</span>");
    wrap.appendChild(g);
  }
  const hist = k.history || [];
  if (hist.length) wrap.appendChild(dialHistory(k, hist));
  return wrap;
}

// the value of a dial leaf as a plain word (bool→on/off, list→comma-join, else the raw).
function fmtVal(kind, v) {
  if (kind === "bool") return v ? "on" : "off";
  if (kind === "list") return ((v || []).join(", ")) || "—";
  return (v === "" || v == null) ? "—" : String(v);
}

// HIS COMMISSION (9a) — the meaning block: what the dial does + its stage effect, then
// current-vs-default + the consuming organ. Honest-absent when undocumented (no invention).
function dialMeaning(k) {
  const el = document.createElement("div"); el.className = "pipe-dial-meaning";
  const hasDef = ("default" in k);
  const changed = hasDef && JSON.stringify(k.value) !== JSON.stringify(k.default);
  const meta = "<div class='pipe-dm-meta'>" +
    (hasDef ? "default <b>" + esc(fmtVal(k.kind, k.default)) + "</b>" : "") +
    (changed ? " · <span class='pipe-dm-changed'>now " + esc(fmtVal(k.kind, k.value)) + "</span>"
             : (hasDef ? " · <span class='pipe-dm-atdef'>at default</span>" : "")) +
    (k.consumer ? " · consumed by <b>" + esc(k.consumer) + "</b>" : "") + "</div>";
  if (k.meaning) {
    el.innerHTML = "<div class='pipe-dm-what'>" + esc(k.meaning.what) + "</div>" +
      "<div class='pipe-dm-effect'>" + esc(k.meaning.effect) + "</div>" + meta;
  } else {
    el.innerHTML = "<div class='pipe-dm-what pipe-dm-none'>meaning not documented in " +
      "code/docs — inspect dials.py or the consuming organ</div>" + meta;
  }
  return el;
}

// the ledger history, one act deep (a fold): the friction rows that touched this leaf,
// newest first — who moved it, when, to what (the derivation-chip mono idiom).
function dialHistory(k, hist) {
  const d = document.createElement("details"); d.className = "pipe-dial-hist";
  d.innerHTML = "<summary>ledger history · " + hist.length + "</summary>" +
    "<div class='pipe-dial-hist-body'>" + hist.slice().reverse().map((r) =>
      "<div class='pipe-dial-hrow'><span class='ek'>" +
        esc(String(r.ts || "").replace("T", " ").slice(0, 16)) + "</span> " +
        esc(r.by || "?") + " · " + esc(r.kind === "reset-leaf" ? "reset" : "set") +
        (("value" in r) ? " → <b>" + esc(fmtVal(k.kind, r.value)) + "</b>" : "") +
      "</div>").join("") + "</div>";
  return d;
}

function gateRefuse(row, k) {
  const wrap = row.closest(".pipe-gaterow"); if (!wrap) return;
  let r = $(".pipe-gate-r", wrap);
  if (!r) { r = document.createElement("span"); r.className = "pipe-gate-r"; $(".pipe-gate", wrap).appendChild(r); }
  r.textContent = "arming refused: " + (k.gate.refusal || "gate not passed") + " — flip it only once the holdout gate passes.";
}

function controlHTML(k) {
  if (k.kind === "enum")
    return "<select class='ctl' data-kind='enum'>" + (k.enum || []).map((o) =>
      "<option value='" + esc(o) + "'" + (o === k.value ? " selected" : "") + ">" + esc(o) + "</option>").join("") + "</select>";
  if (k.kind === "bool")
    return "<input type='checkbox' class='ctl' data-kind='bool'" + (k.value ? " checked" : "") + ">";
  if (k.kind === "num")
    return "<input type='number' step='any' class='ctl' data-kind='num' value='" + esc(k.value) + "'>";
  if (k.kind === "list")
    return "<input type='text' class='ctl' data-kind='list' value='" + esc((k.value || []).join(", ")) + "' placeholder='comma,separated'>";
  return "<input type='text' class='ctl' data-kind='text' value='" + esc(k.value) + "'>";
}

function parseVal(kind, el, row) {
  if (kind === "bool") return el.checked;
  if (kind === "enum") return el.value;
  if (kind === "list") return el.value.split(",").map((s) => s.trim()).filter(Boolean);
  if (kind === "num") {
    const raw = el.value.trim(), n = Number(raw);
    if (raw === "" || !isFinite(n)) { rowErr(row, "not a number: " + el.value); return null; }
    return n;
  }
  return el.value;
}

function rowErr(row, msg) {
  let e = $(".pipe-derr", row);
  if (!e) { e = document.createElement("div"); e.className = "pipe-derr"; row.appendChild(e); }
  e.textContent = msg;
}

async function dialWrite(op, row) {
  try {
    // The actor law: this is his surface and his confirmed dial edit — pass him
    // EXPLICITLY (the door defaults nowhere; his name is never a server default).
    const data = await store.fetchJSON("/dials/op", { inject: [], method: "POST",
      body: Object.assign({ profile: CHAIN.profile, by: "gerard" }, op) });
    if (data && data.ok) { await reload(); }
    else { rowErr(row, (data && data.error) || "write refused"); }
  } catch (e) { rowErr(row, (e && e.message) || String(e)); }
}

async function dialUndo(btn) {
  btn.disabled = true;
  try {
    const data = await store.fetchJSON("/dials/undo", { inject: [], method: "POST", body: { profile: CHAIN.profile } });
    if (data && data.ok) { await reload(); }
    else { btn.disabled = false; }
  } catch (e) { btn.disabled = false; }
}

// ── SCOPED CONTROLS — arm/fire THIS organ, each with a dry-run preview (run-tray's shared control). ──
function controlsZone(o) {
  const z = document.createElement("div"); z.className = "pipe-zone";
  z.innerHTML = "<div class='pipe-zh'>scoped controls · arm / fire" +
    infoTag("each fire-class control renders a dry-run 'what would fire' (GET /storyboard/propagate, pure read) BEFORE any arm; local-safe fires, model-heavy BANKS a work-order (offer law)") +
    "</div><div class='pipe-launches' style='display:flex;flex-wrap:wrap;gap:8px'></div>";
  const lh = $(".pipe-launches", z);
  for (const c of (o.controls || [])) {
    // The fire made legible (r2 stranger-walk fix) — a control the backend threaded a
    // reproject-fire onto (the staged card's re-projection, where "open the gen-4
    // reprojection" lands) greets the author by the generation name, names the cost in
    // plain words, and carries the brief as a REAL door — never a bare 're-projection ·
    // banks' button. Every other control renders as the plain launch atom, unchanged.
    if (c.reproject) { lh.appendChild(reprojectControl(c)); continue; }
    lh.appendChild(launchControl(c.action, { cost_class: c.cost_class, arm_to_fire: !!c.arm_to_fire, what: c.what }, { corpus: PROJECT, actor: "gerard" }));
  }
  return z;
}

// ── The reproject fire, named — the fire the author presses HIMSELF on the staged card.
// The generic launchControl atom (its arm / dry-run / bank machinery intact) is wrapped so
// it GREETS him by the generation name, states the cost in the backend's plain words (the
// truth of run_launch's model-heavy path — banks a work order, runs nothing, a shepherded
// session runs it), and carries the brief as a REAL door: the SAME _brief_door the brief's
// consequential card names, so the two surfaces speak identically. An unresolved brief
// degrades to a plain truthful label (never a dead link). ──
function reprojectControl(c) {
  const rp = c.reproject || {};
  const wrap = document.createElement("div");
  wrap.className = "pipe-reproject";
  wrap.dataset.action = c.action;
  const head = "<div class='pipe-rp-head'>" + esc(rp.fire_label || "fire the reprojection") + "</div>";
  const cost = rp.cost_plain
    ? "<div class='pipe-rp-cost'>what it costs — " + esc(rp.cost_plain) + "</div>" : "";
  wrap.innerHTML = head + cost + "<div class='pipe-rp-doors'></div>";
  const doors = $(".pipe-rp-doors", wrap);
  doors.appendChild(launchControl(c.action, { cost_class: c.cost_class, arm_to_fire: !!c.arm_to_fire, what: c.what }, { corpus: PROJECT, actor: "gerard" }));
  const bd = rp.brief_door;
  if (bd && bd.href) {
    doors.insertAdjacentHTML("beforeend",
      "<a class='hy-door pipe-rp-brief' href='" + esc(bd.href) + "'" +
      (bd.path ? " title='" + esc(bd.path) + "'" : "") +
      ">read " + esc(bd.label || "the brief") + " ↗</a>");
  } else if (rp.brief) {
    doors.insertAdjacentHTML("beforeend",
      "<span class='pipe-rp-briefabsent' title='" + esc(rp.brief) + "'>brief " + esc(rp.brief) +
      " — not reachable on disk</span>");
  }
  return wrap;
}

// ── The regrade-health read (the W3 fork, rehoused) — a conceptric-health card. ──────
function regradeCard() {
  const el = document.createElement("div");
  el.className = "hy-card is-clickable" + (OPEN === "regrade" ? " is-open" : "");
  el.dataset.organ = "regrade";
  el.innerHTML =
    "<div class='hy-card-id'><span class='hy-card-name'>regrade health</span><span class='hy-card-kind'>conceptric read</span></div>" +
    "<div class='pipe-blurb'>the per-node content-weight stats — the power law watched, never imposed" +
    infoTag("GET /corpus/grade_stats → corpus_stats.grade_stats (the W3 regrade panel rehoused here as a conceptric-health read among the organ ops; his overrule = move it back to /conceptric)") + "</div>" +
    "<div class='hy-card-fold'></div>";
  el.onclick = (e) => { if (e.target.closest(".hy-card-fold")) return; OPEN = OPEN === "regrade" ? null : "regrade"; renderBoard(); };
  if (OPEN === "regrade") loadRegrade($(".hy-card-fold", el));
  return el;
}

async function loadRegrade(host) {
  host.innerHTML = "<div class='pipe-none'>reading grade stats…</div>";
  let g;
  try { g = await store.fetchJSON("/corpus/grade_stats", { inject: [], params: { corpus: PROJECT } }); }
  catch (e) { host.innerHTML = "<div class='pipe-none'>grade stats unavailable — " + esc((e && e.message) || e) + "</div>"; return; }
  const grades = (g.grades || []).map((r) => "<span class='rk'>" + esc(r.label) + "</span> " + esc(r.count)).join(" · ");
  const ratios = (g.count_ratios || []).filter((x) => x != null).map((x) => esc(x)).join(" · ");
  host.innerHTML = "<div class='pipe-zone'><div class='pipe-regrade'>" +
    "nodes " + esc(g.n_live || 0) + " live / " + esc(g.n_nodes || 0) + " total · beats " + esc(g.n_beats || 0) + "<br>" +
    grades + "<br>ratios " + (ratios || "—") + "<br>" +
    "<span class='rk'>split candidates</span> " + esc((g.outliers && g.outliers.split_candidates || []).length) +
    " · <span class='rk'>content-free</span> " + esc((g.outliers && g.outliers.content_free || []).length) +
    "</div></div>";
}

// ── W-PROJECT — the composed brief (the resting altitude) ─────────────────────────────
// The dashboard's join, mirrored: the resting DOM is the server-composed brief (delta-and-
// ask over the SAME chain + verdict read models — the lock-step law), rendered verbatim.
// The board is the summonable inventory, materialised behind one open.
const hz = (w) => { const s = String(w || ""); return /^[A-Z][A-Z_]*$/.test(s) ? s.toLowerCase().replace(/_/g, " ") : s; };

async function loadBrief() {
  try { BRIEF = await store.fetchJSON("/pipeline/brief", { inject: [], params: { project: PROJECT } }); }
  catch (e) { BRIEF = null; }
}

function paintBrief() {
  const brief = $(".eng-brief"); if (!brief) return;
  MAT_OPEN = false; OPEN = null;
  const b = (BRIEF && BRIEF.brief) || {};
  const c = (BRIEF && BRIEF.counts) || {};
  const glance = b.glance || "resolving the pipeline…";
  brief.innerHTML =
    "<div class='pipe-brief'>" +
      "<p class='pipe-prose' data-role='brief-prose'>" + esc(glance) + "</p>" +
      conseqHTML(b.consequential) +
      "<div class='pipe-counts'>" +
        countChip("organs", c.organs, "organ panel" + (c.organs === 1 ? "" : "s"), false) +
        countChip("stages", c.stages, "stage" + (c.stages === 1 ? "" : "s"), false) +
        countChip("orders", c.orders, "banked order" + (c.orders === 1 ? "" : "s"), true) +
        countChip("rounds", c.rounds, "round" + (c.rounds === 1 ? "" : "s"), true) +
      "</div>" +
    "</div>";
  wireBrief();
  const cur = $("#pipe-cur");
  if (cur) cur.innerHTML = "state <b>" + esc(hz((BRIEF && BRIEF.position) || "")) + "</b>";
}

// the single consequential move (at most one decision), with its cost/PSU visible before it
// fires (his P1 amendment — what-will-this-do stays visible), plus a door into the board
// focus (the owning organ) so the one decision is one click from where it is ruled.
function conseqHTML(cq) {
  if (!cq) return "";
  const cost = [];
  if (cq.cost_class) cost.push(cq.cost_class);
  if (cq.psu && cq.psu !== "none") cost.push(cq.psu);
  const costLine = cost.length
    ? "<div class='pc-cost'>what it costs — " + esc(cost.join(" · ")) + "</div>" : "";
  // the door FACE is the verb; the raw brief path (cq.title) rides the tooltip at audit
  // depth, never on the amber face — and the face never repeats the card's glance.
  const door = cq.href
    ? "<a class='hy-door is-primary' href='" + esc(cq.href) + "'" +
      (cq.title ? " title='" + esc(cq.title) + "'" : "") +
      " data-role='conseq-door'>" + esc(cq.label || "act") + " ↗</a>"
    : "";
  const open = cq.organ
    ? "<button type='button' class='hy-door' data-role='conseq-open' data-organ='" + esc(cq.organ) + "'>open the " + esc(cq.organ) + " organ ↗</button>"
    : "";
  // FIX #4 — the brief made a REAL door on the consequential card, the SAME _brief_door
  // the staged fire control names: the "open the gen-4 reprojection" move and the fire it
  // lands on both point at one reachable brief (never the unreachable span the r2 walk hit).
  const bd = cq.brief_door;
  const brief = (bd && bd.href)
    ? "<a class='hy-door pipe-rp-brief' href='" + esc(bd.href) + "'" +
      (bd.path ? " title='" + esc(bd.path) + "'" : "") +
      " data-role='conseq-brief'>read " + esc(bd.label || "the brief") + " ↗</a>"
    : "";
  return "<div class='pipe-conseq'>" +
    "<div class='pc-h'>the move that matters most now</div>" +
    "<div class='pc-glance'>" + esc(cq.glance) + "</div>" +
    costLine +
    "<div class='pc-doors'>" + door + open + brief + "</div></div>";
}

function countChip(key, n, label, staticChip) {
  const num = n == null ? "" : "<span class='pc-n'>" + n + "</span>";
  return "<button type='button' class='pipe-count" + (staticChip ? " is-static" : "") +
    "' data-count='" + key + "'" + (staticChip ? " aria-disabled='true'" : "") + ">" + num +
    "<span class='pc-l'>" + esc(label) + "</span></button>";
}

function wireBrief() {
  $$(".pipe-count[data-count='organs'], .pipe-count[data-count='stages']").forEach((btn) =>
    activate(btn, () => toggleBoard()));
  const co = $(".pipe-conseq [data-role='conseq-open']");
  if (co) co.addEventListener("click", async (e) => {
    e.preventDefault(); await openBoard(); expandOrgan(co.getAttribute("data-organ"));
  });
}

// ── MATERIALISE = REALLOCATE — the board (cockpit strip + organ cards) behind one open ─
// The REAL panels that exist today — the cockpit state strip, the generation story, the
// organ cards — re-homed behind the engine's FOCUS geometry, not rebuilt: opening a count
// chip REALLOCATES the surface to the board (the summonable inventory), with the named return
// door "back to the project brief — where you were" and the brief summary in the rail. Within
// the board the organ cards keep their expand-in-place richness (dials in place, the dry-run
// + cost/PSU before any fire — the what-will-this-do law intact). Close → the brief, exact
// scroll (the Reallocator owns the restore; a close-wrap resets the surface's own flags).
async function toggleBoard() {
  if (MAT_OPEN) { REALLOC.close(); return; }
  await openBoard();
}

async function openBoard() {
  if (MAT_OPEN) return;
  MAT_OPEN = true;
  $$(".pipe-count[data-count='organs'], .pipe-count[data-count='stages']").forEach((c) => c.classList.add("is-open"));
  REALLOC.pin("board", {
    title: (PROJECT || "project") + " — the board",
    destination: "back to the project brief — where you were",
    buildRail: (railEl) => buildBoardRail(railEl),
    buildFocus: (focusEl) => {
      // mount the hosts the existing render functions target; reload() fills them.
      focusEl.insertAdjacentHTML("beforeend",
        "<div class='pipe-boardhead'>the whole chain from the state machine — organs expand in place, dials + dry-run before any fire</div>" +
        "<div id='pipe-cockpit'></div><div id='pipe-ladder'></div><div id='pipe-board'></div>");
    },
  });
  await reload();          // fills #pipe-cockpit + #pipe-board (the existing render functions)
}

function findOrgan(id) {
  if (id === "global") return CHAIN && CHAIN.global;
  return ((CHAIN && CHAIN.organs) || []).find((o) => o.id === id) || null;
}

function buildBoardRail(railEl) {
  const c = (BRIEF && BRIEF.counts) || {};
  const pos = (BRIEF && BRIEF.position) || (CHAIN && CHAIN.position) || "";
  const b = (BRIEF && BRIEF.brief) || {};
  const conseq = b.consequential;
  const conseqLine = conseq
    ? "<div class='eng-railblock'><h5>the move that matters</h5><div class='pipe-railcov'>" + esc(conseq.glance) +
        (conseq.cost_class ? "<br><span class='pipe-railcost'>" + esc(conseq.cost_class) + (conseq.psu && conseq.psu !== "none" ? " · " + esc(conseq.psu) : "") + "</span>" : "") +
      "</div></div>"
    : "";
  railEl.innerHTML =
    "<div class='eng-railblock'><h5>the brief</h5><div class='pipe-railcov'>" +
      esc(hz(pos)) + "<br>" +
      (c.stages || 0) + " stages · " + (c.organs || 0) + " organs<br>" +
      (c.rounds || 0) + " round(s) · " + (c.orders || 0) + " banked order(s)</div></div>" +
    conseqLine;
}

// expand ONE organ card in place within the materialised board (the deep-link pre-pin lands
// on it; a plain materialise leaves every card closed).
function expandOrgan(organId) {
  if (!findOrgan(organId)) return;
  OPEN = "organ::" + organId;
  if ($("#pipe-board")) renderBoard();
  const card = $("#pipe-board .hy-card[data-organ='" + String(organId).replace(/'/g, "\\'") + "']");
  if (card) card.scrollIntoView({ block: "center" });
}

// FINDING 2 — the parent state-organ that owns a sub-organ id (evolution/selection/
// derivation/…), dug from the chain payload. A sub-organ deep link resolves through here.
function findSubParent(subId) {
  for (const o of ((CHAIN && CHAIN.organs) || []))
    for (const so of (o.sub_organs || []))
      if (so.id === subId) return o.id;
  return null;
}

// FINDING 2 — a hot ?organ=<sub-organ> arrival lands OPEN, zero lobby tax: open the
// parent stage, open the sub-card, scrollIntoView it. Every contract verb (evolution
// ratify, selection rule, derivation rescope) was three clicks deep; now it is one
// deep-link away, the named return door already pinned by openBoard.
function expandSubOrgan(subId) {
  const parentId = findSubParent(subId);
  if (!parentId) return false;
  OPEN = "organ::" + parentId;
  OPEN_SUBS.add("sub::" + parentId + "::" + subId);
  if ($("#pipe-board")) renderBoard();
  const q = (s) => String(s).replace(/'/g, "\\'");
  const sub = $("#pipe-board .hy-card[data-organ='" + q(parentId) + "'] .pipe-subcard[data-suborgan='" + q(subId) + "']");
  if (sub) sub.scrollIntoView({ block: "center" });
  return true;
}

// ── boot / reload ────────────────────────────────────────────────────────────────────
async function reload() {
  try {
    SUB_EV = {};                                     // the sub-organ evidence cache is per-load
    const data = await store.fetchJSON("/pipeline/chain", { inject: [], params: { project: PROJECT, profile: PROFILE } });
    const lad = $("#pipe-ladder");
    if (data && data.error) { if (lad) lad.innerHTML = "<span class='err'>" + esc(data.error) + "</span>"; return; }
    CHAIN = data;
    // the per-rung next_action lookup (state → next_action) the cockpit + every organ
    // card lead with — the backend computes it per rung; E4b: no longer thrown away.
    NEXT_ACTION = {};
    for (const s of (CHAIN.states || [])) if (s.state) NEXT_ACTION[s.state] = s.next_action;
    if ($("#pipe-ladder")) renderLadder();
    if ($("#pipe-board")) renderBoard();
    // ACT 4 — the cockpit's own reads (the truth-layer verdict + the generation rows),
    // fetched after the board so a slow/absent verdict never blocks the chain paint.
    await loadCockpit();
  } catch (e) { const lad = $("#pipe-ladder"); if (lad) lad.innerHTML = "<span class='err'>failed to load the chain: " + esc((e && e.message) || e) + "</span>"; }
}

// fetch the truth-layer verdict + the selection organ's full generation rows, then
// paint the cockpit. Degrades plainly: an absent verdict leaves VERDICT null and the
// banner reads "not started", never a crash of the board below it.
async function loadCockpit() {
  try {
    VERDICT = await store.fetchJSON("/pipeline/verdict", { inject: [], params: { project: PROJECT } });
  } catch (e) { VERDICT = null; }
  try {
    const sel = await store.fetchJSON("/pipeline/organ", { inject: [], params: { project: PROJECT, organ: "selection" } });
    const p = (sel && sel.payload) || {};
    const rulings = p.rulings || {};
    GEN_ROWS = (p.generations || []).map((g) => Object.assign({}, g, { ruling: rulings[String(g.id)] }));
  } catch (e) { GEN_ROWS = []; }
  renderCockpit();
}

export async function initPipeline() {
  injectEngineCSS(); ensureCSS();
  const q = new URLSearchParams(location.search || "");
  PROJECT = store.field("corpus") || q.get("project") || q.get("corpus") || null;
  PROFILE = q.get("profile") || "dials-v1.yaml";
  BUS = new HighlightBus(document);
  LENS = new HoverLens();
  const root = $("#eng-root");
  if (!root) return;
  REALLOC = new Reallocator(root, STATE, BUS);
  // wrap the Reallocator's close so EVERY path back to the brief (the return door, the
  // breadcrumb, Escape) resets the surface's own materialise flags — the board is gone at
  // rest, and the count chip re-summons it cleanly.
  const _close = REALLOC.close.bind(REALLOC);
  REALLOC.close = () => {
    _close();
    MAT_OPEN = false; OPEN = null;
    $$(".pipe-count.is-open").forEach((c) => c.classList.remove("is-open"));
    if (BUS) BUS.clear();
  };
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && REALLOC.pinned) REALLOC.close();
  });
  const brief = $(".eng-brief");
  if (!PROJECT) {
    if (brief) brief.innerHTML = "<p class='pipe-prose'>no project — pick one in the bar above (or open /project?project=&lt;name&gt;).</p>";
    return;
  }
  store.set({ corpus: PROJECT }, { replace: true });     // ride the corpus through every read
  await loadBrief();
  paintBrief();
  // no lobby tax (B.5): a ?organ= / ?stage= / ?suborgan= hot arrival lands pre-focused —
  // the board is summoned and the target expanded in place; the brief is the cold-arrival
  // default, never a toll on a hot one.
  const dOrgan = q.get("organ");
  const dStage = q.get("stage");
  const dSub = q.get("suborgan") || q.get("sub");
  if (dOrgan || dStage || dSub) {
    await openBoard();
    // FINDING 2 — a sub-organ id resolves to its parent stage + open sub-card. An
    // explicit ?suborgan= wins; otherwise a ?organ= that is NOT a top-level organ but IS
    // a known sub-organ (evolution/selection/derivation/…) is treated as a sub deep-link.
    let subTarget = dSub;
    if (!subTarget && dOrgan && !findOrgan(dOrgan) && findSubParent(dOrgan)) subTarget = dOrgan;
    if (subTarget && expandSubOrgan(subTarget)) {
      // landed open on the sub-card — zero lobby tax.
    } else {
      let target = dOrgan;
      if (!target && dStage) {
        const st = String(dStage).toUpperCase();
        const o = ((CHAIN && CHAIN.organs) || []).find((x) => String(x.state || "").toUpperCase() === st);
        target = o ? o.id : null;
      }
      if (target && findOrgan(target)) expandOrgan(target);
    }
  }
  // follow a project switch from the shell/store.
  store.subscribe((s) => {
    const c = s.selection.corpus;
    if (c && c !== PROJECT) {
      PROJECT = c; OPEN = null;
      if (REALLOC && REALLOC.pinned) REALLOC.close();
      loadBrief().then(paintBrief);
    }
  });
}

if (typeof window !== "undefined") window.__pipelineInit = initPipeline;
