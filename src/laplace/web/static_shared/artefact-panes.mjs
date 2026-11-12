// THE ARTEFACT PANES (W2, shared). Purpose: the pane logic of the artefact surface: the
// manuscript panes, the proposal and editing panes, their source effects and acknowledgements.
// Ownership: the manuscript source owner (through manuscript-source-client and source-effect),
// manuscript-editing (paragraph identities), the proposal owners; this module owns pane state
// and never a revision policy. Public contract: the exported pane mount. Inputs: owner reads and
// walk messages; outputs: DOM. Currentness: expected digests on every write; a refused write is
// shown through sourceEffectDisposition. Storage: none of its own. Retired path: the writing
// workspace's Manuscript view (walk in an iframe) supersedes the artefact panes for ordinary
// reading and editing; this module stays for the artefact route.
import {paragraphSourceIdentity} from './manuscript-editing.mjs';
import {sourceEffectDisposition,requireSourceCompletion,sourceEffectFromError} from './source-effect.mjs';
// artefact-panes.mjs — The artefact surface's pane logic (W2), a SHARED module.
//
// The approved mock (mocks/artefact.html, D1–D16, PR #72) is the contract this realises over
// the REAL pdf.js reader + the shared shell chrome: the reader stands center-stage, a
// paragraph click raises an ANCHOR OVERLAY (its section nodes as kind-badged chips + the spine
// beat chip + one-click annotate with a flash), the standing VERSION RAIL holds its own column
// and compresses the reader in place, and the FINDINGS TRAY sits at the bottom collapsed to one
// plain line until he triages it. Behaviour lives here so artefact.html stays inside the
// ≤8KB inline-script budget (visual §6.2); all network rides store.fetchJSON (the one gateway).
//
// F4 (the pull-back walk): the anchor/tray JOINS ride the RESOLVED corpus (seeded from
// /artefact/context at init), so BOTH addressings — `?corpus=` and a bare `file=` link the
// storyboard door lands on — carry the same nodemap/findings join. The corpus-conditional
// dead click ("· ?" anchors, nodes that never appear) is closed at the root: one reader path,
// one resolved corpus.
//
// The reading room (2026-07-22, the final authorship — the front end recomposed): ONE
// reading surface. The paper stands centre-stage; the MARGIN at its right is the judge's
// notebook — the findings standing open over the version history. Hover/anchor/annotate
// are always on; editing is an ACT entered from the head, not a mode among modes:
//   read      — the resting surface: the pdf + the margin (judgment + history).
//   edit      — CM6 source LEFT ⇄ the SAME pdf pane RIGHT, a draggable divider, and TWO-WAY
//               synctex coupling wired to the already-tested server routes: a pdf-paragraph
//               click resolves through /projection/synctex to a source file+line (switching
//               the open fragment when synctex names a different one); a debounced cursor move
//               in CM resolves through /projection/locate to a pdf page/x/y and scrolls+flashes
//               it; /projection/follow renders as the pane's quiet status line. save chains
//               into the debounced /projection/recompile loop (POST fires it, GET polls it);
//               on success the pdf pane hot-reloads the FRESH compile (scroll position kept);
//               on error the tex log's line-numbered rows are clickable jumps into the source.
//   Echo guard: a synctex-driven cursor move opens FOLLOW_GUARD's time-boxed suppression window
//   (makeFollowGuard, exposed as window.__pvFollowGuardFactory) so the reverse (CM→pdf) listener
//   does not fire on its own programmatic write — one gesture, one resolve, no ping-pong.

import store from "/shared/store.mjs";
import {readManuscriptSource,saveManuscriptSource,advanceSourceObservation,readHistoricalSource} from "./manuscript-source-client.mjs";
import {mountExactSourceEditor} from "./exact-source-editor.mjs";
let EDIT_SOURCE_OBSERVATION=null;
let EDIT_EFFECT_HOLD=null;
import { injectEngineCSS, createFocusState, HighlightBus, returnDoor, activate } from "/shared/engine.mjs";

// ── tiny helpers ──────────────────────────────────────────────────────────────
const ec = encodeURIComponent;
const esc = (s) => String(s == null ? "" : s)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
  .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const cut = (s, n) => { s = String(s || ""); return s.length > n ? s.slice(0, n - 1) + "…" : s; };

// THE ACTOR (the actor law, banked 2026-07-22): every verdict write carries an EXPLICIT
// actor resolved from the session context — the shell's signed-in identity, or a session /
// url `actor` — and never this author's name baked in as a default. An unresolved actor
// stays empty; the actor-guarded /review/adjudicate door then refuses the write (422) rather
// than mint an unattributed verdict (the click-enumeration incident the guard closed).
function sessionActor() {
  try {
    const g = (typeof window !== "undefined" &&
      ((window.HymnShell && window.HymnShell.sessionActor) || window.__artefactActor)) || "";
    if (g) return String(g).trim();
  } catch (e) { /* no shell identity */ }
  try {
    const u = new URLSearchParams((typeof window !== "undefined" && window.location
      && window.location.search) || "").get("actor");
    if (u) return String(u).trim();
  } catch (e) { /* no url actor */ }
  try {
    const s = sessionStorage.getItem("art-actor");
    if (s) return String(s).trim();
  } catch (e) { /* private mode */ }
  return "";
}

// a finding KIND said in plain words at the decision point (the terse machine kind alone is
// not a judgeable account). Unknown kinds humanise their own dashes rather than guess.
const KIND_WORDS = {
  "eq-unused": "an equation is defined but never referenced",
  "eq-duplicate": "two equations state the same thing",
  "notation-inconsistent": "the notation is used inconsistently",
  "legacy-notation": "notation left from an earlier draft",
  "legacy-term": "a term left from an earlier draft",
  "missing-derivation": "a claimed result has no derivation",
  "missing-simulation": "a claimed result has no simulation",
  "missing-node": "the argument references a node that is absent",
  "missing-content": "promised content is missing",
  "unsupported-claim": "a claim carries no support",
  "naked-claim": "a claim stands without evidence",
  "refute": "the text contradicts itself or a source",
  "matter-scaffold": "scaffolding prose left in the matter",
  "meta-leak": "planning meta has leaked into the prose",
  "note": "a reader note",
  "figure-standard": "a figure does not meet the standard",
};
function kindInWords(kind) {
  const k = String(kind || "").trim();
  if (!k) return "an unclassified finding";
  return KIND_WORDS[k] || k.replace(/[-_]/g, " ");
}

// ── injected COMPONENT CSS (visual §6.2 relocation) ─────────────────────────────
// The COMPONENT atoms — every rule for DOM this module builds (anchor-overlay rows,
// hover/flash bands, rail rows + diff pane, tray groups + dismissed fold, edit pane) —
// live here, not in artefact.html's <style>. That keeps the surface's own island under
// the 4KB per-surface budget (§6.2) while the one-palette clause still reaches this text
// (test_shared_model.py greps this file for colour literals — there are none: every colour
// is a hymn var/color-mix). Injected once at init, before anything renders.
const COMPONENT_CSS = `
.art-hoverband,.art-flashband{position:absolute;pointer-events:none;z-index:3}
.art-hoverband{background:color-mix(in srgb,var(--accent) 10%,transparent);border-left:2px solid var(--accent)}
.art-flashband{background:color-mix(in srgb,var(--accent) 24%,transparent);animation:artflash 1.1s ease-out forwards}
.art-hoverchip{position:absolute;pointer-events:none;z-index:4;font:10px var(--mono);color:var(--accent);
  background:var(--panel);border:1px solid var(--edge);border-radius:4px;padding:1px 6px}
@keyframes artflash{to{opacity:0}}
.art-anchor-head{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin-bottom:8px}
.art-anchor-head b{color:var(--ink);font-size:12.5px}
.art-anchor-x{margin-left:auto;background:none;border:none;color:var(--dim);cursor:pointer;font-size:16px;line-height:1;padding:0 2px}
.art-anchor-x:hover{color:var(--ink)}
.art-anchor-row{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin:6px 0}
.art-anchor-act{margin-top:10px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
/* the comment thread (item 4/5): the anchor overlay opens COLLAPSED — a summary + folds that
   render on expand + the comments block with a visible bank. It rides over the paper, bounded. */
.art-anchor{min-width:0;background:var(--panel);border:1px solid var(--accent);border-radius:11px;
  padding:12px 13px;font-size:12px;box-shadow:0 14px 42px -18px var(--bg);
  max-height:calc(100vh - 130px);overflow:auto}
.art-line-marker{position:absolute;pointer-events:none;z-index:4;
  background:color-mix(in srgb,var(--accent) 14%,transparent);border-left:2px solid var(--accent)}
.art-line-marker-chip{position:absolute;pointer-events:none;z-index:5;font:9.5px var(--mono);
  color:var(--accent);background:var(--panel);border:1px solid var(--accent);border-radius:4px;padding:0 5px}
.art-anchor-anchor{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:4px 0 6px}
.art-anchor-sum{font:10.5px var(--mono);color:var(--ink2);margin:2px 0 8px;display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.art-fold{border-top:1px solid var(--edge2);padding:5px 0}
.art-fold-h{font:11px var(--mono);color:var(--ink2);cursor:pointer;display:flex;align-items:center;gap:6px}
.art-fold-h:hover{color:var(--ink)}
.art-fold-a{color:var(--dim);width:.9em;display:inline-block}
.art-fold-n{color:var(--dim)}
.art-fold-b{display:none;margin-top:7px;flex-wrap:wrap;gap:5px}
.art-fold.open .art-fold-b{display:flex}
.art-thread-comments{border-top:1px solid var(--edge2);margin-top:6px;padding-top:8px}
.art-cmt-title{font:11px var(--mono);color:var(--ink2);margin-bottom:6px;display:flex;gap:6px;align-items:center}
.art-cmt{border-left:2px solid var(--edge2);padding:2px 0 4px 8px;margin:5px 0}
.art-cmt-q{font-style:italic;color:var(--ink2);font-size:11px;line-height:1.4}
.art-cmt-t{color:var(--ink);font-size:12px;line-height:1.5}
.art-cmt-by{font:9.5px var(--mono);color:var(--dim)}
.art-cmt-form{margin-top:8px;display:flex;flex-direction:column;gap:6px}
.art-cmt-form textarea{width:100%;min-height:46px;resize:vertical;font:11.5px var(--mono);color:var(--ink);
  background:var(--bg);border:1px solid var(--edge);border-radius:6px;padding:5px 7px}
.art-cmt-row{display:flex;gap:7px;align-items:center;flex-wrap:wrap}
.art-cmt-msg{font:10px var(--mono);color:var(--dim)}
.art-cmt-msg.is-bad{color:var(--bad)}
.art-cmt-msg.is-ok{color:var(--ok)}
.art-sel-aff{position:fixed;z-index:40;font:10.5px var(--mono);padding:3px 9px;border-radius:7px;
  border:1px solid var(--accent);background:var(--panel);color:var(--accent);cursor:pointer;
  box-shadow:0 8px 24px -10px var(--bg)}
.art-sel-aff:hover{background:color-mix(in srgb,var(--accent) 14%,transparent);color:var(--ink)}
.art-sel-aff.is-note{border-color:var(--warn);color:var(--ink2);cursor:default}
.art-k{font:9.5px var(--mono);text-transform:uppercase;letter-spacing:.08em;color:var(--dim)}
.art-dim{color:var(--dim);font-size:11px;line-height:1.5}
.art-node,.art-beat{cursor:pointer;text-decoration:none}
.art-node:hover,.art-beat:hover{border-color:var(--accent);color:var(--ink)}
#art-rail{border:1px solid var(--edge);border-radius:10px;background:var(--panel);overflow:hidden}
.art-rail-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:9px 11px;
  background:var(--panel2);border-bottom:1px solid var(--edge)}
#art-rail .hy-rail-body{display:none;padding:10px 10px 4px;max-height:calc(100vh - 300px);overflow:auto}
#art-rail.open .hy-rail-body{display:block}
#art-diffbar{font:10.5px var(--mono);margin:6px 10px}
.hy-rail-row.is-sel{border-color:var(--accent)}
.art-diffpick{font-size:10px;color:var(--dim);display:inline-flex;gap:3px;align-items:center;margin-top:3px}
#art-diffpane{display:none;margin:8px 10px 0;border-top:1px solid var(--edge);padding-top:8px}
#art-diffpane.on{display:block}
.art-difflines{max-height:320px;overflow:auto;font:10.5px var(--mono)}
.art-dline{white-space:pre;overflow-x:auto}
.art-dline.opadd{color:var(--ok)}.art-dline.opdel{color:var(--bad)}
.art-dop{display:inline-block;width:1.2em;color:var(--dim)}
.art-tray-ind{font:11px var(--mono);color:var(--dim);transition:transform .15s}
.art-tray.open .art-tray-ind{transform:rotate(90deg);color:var(--accent)}
.art-grp{border:1px solid var(--edge);border-radius:9px;background:var(--panel2);padding:9px 11px;margin:10px 0}
.art-grp-h{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:8px}
.art-frow{margin:5px 0}
.art-frow .dk-card-head{align-items:center;gap:8px}
.art-frow .dk-title{flex:1;min-width:120px;white-space:normal}
.art-unanch{flex:none;font:10px var(--mono);color:var(--warn);border:1px dashed var(--edge2);
  border-radius:6px;padding:2px 8px;cursor:help}
.art-dism{margin-top:14px;border-top:1px dashed var(--edge2);padding-top:10px}
.art-dism-h{font:11px var(--mono);color:var(--dim);cursor:pointer;display:inline-flex;align-items:center;gap:6px}
.art-dism-h:hover{color:var(--ink2)}
.art-dism.open .art-dism-h{color:var(--accent)}
.art-dism-body{display:none;margin-top:9px}
.art-dism.open .art-dism-body{display:block}
.art-dism-cav{font:10px var(--mono);color:var(--dim);margin-bottom:6px}
.art-source-pane{display:none;flex-direction:column;min-width:0;flex:0 0 var(--split-pct,46%);
  max-height:calc(100vh - 190px);overflow:hidden;
  border:1px solid var(--edge);border-radius:8px;background:var(--panel);padding:10px;margin-right:10px}
.art-main[data-mode="edit"] .art-source-pane,.art-main[data-mode="edit"] .art-divider{display:flex}
.art-divider{display:none;flex:none;width:7px;margin:0 -1px 0 -3px;cursor:col-resize;
  border-radius:4px;background:var(--edge);align-items:center;justify-content:center}
.art-divider:hover,.art-divider.is-drag{background:var(--accent)}
@media (max-width:760px){ .art-source-pane{margin-right:0;margin-bottom:10px;flex-basis:var(--split-pct,42vh)}
  .art-divider{width:auto;height:7px;margin:-3px 0 6px;cursor:row-resize} }
.art-source-bar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:8px}
.art-source-bar code{font:10.5px var(--mono);color:var(--ink2)}
.art-edit-doors{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-left:auto}
#art-edit-msg{font:10.5px var(--mono);color:var(--ink2)}
#art-edit-msg.is-bad{color:var(--bad)}
#art-follow-status{font:10px var(--mono)}
#art-cm{flex:1;min-height:220px;height:44vh;border:1px solid var(--edge);border-radius:6px;overflow:hidden}
#art-cm .cm-gutters{background:var(--panel2);color:var(--dim);border-right:1px solid var(--edge)}
#art-cm .cm-activeLineGutter{background:color-mix(in srgb,var(--accent) 14%,transparent)}
#art-cm textarea{height:100%;width:100%;resize:none;font:12px var(--mono);padding:6px;
  background:var(--bg);color:var(--ink);border:none}
#art-compile-log{display:none;margin-top:8px;max-height:22vh;overflow:auto;
  border-top:1px dashed var(--edge2);padding-top:6px}
#art-compile-log.on{display:block}
.art-logrow{display:flex;align-items:center;gap:7px;cursor:pointer;padding:2px 0;font:10.5px var(--mono)}
.art-logrow:hover{color:var(--accent)}
.art-logrow code{color:var(--ink2);white-space:pre;overflow:hidden;text-overflow:ellipsis}
.art-logline{color:var(--dim);font:10px var(--mono);white-space:pre;overflow-x:auto}
.art-essence{margin-top:4px;color:var(--ink2);font-size:12px}
.hy-info{cursor:help;color:var(--dim);font-size:11px}
/* the altitude thread (E4 #1) — the return breadcrumb when arrived from the cockpit tension */
.art-thread{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:0 0 10px;padding:8px 12px;
  background:var(--panel);border:1px solid var(--accent);border-radius:8px}
.art-thread[hidden]{display:none}
.art-rev-kind{font:650 14px/1.4 -apple-system,"Segoe UI",Roboto,sans-serif;color:var(--ink);letter-spacing:-.01em}
.art-rev-id{font:10.5px var(--mono);color:var(--dim)}
.art-thread .art-thread-note{font:10.5px var(--mono);color:var(--dim);min-width:0}
/* the composed-consumption badges on tray rows (E4 #3) */
.art-absent{flex:none;font:9.5px var(--mono);color:var(--dim);border:1px dashed var(--edge2);border-radius:6px;padding:1px 7px;cursor:help}
.art-composed{flex:none;font:9.5px var(--mono);color:var(--teal);border:1px solid var(--edge2);border-radius:6px;padding:1px 7px}
/* the inspection area (E4 #2) — an opened finding claims it; siblings compact; close restores */
.art-inspect{display:none;flex-direction:column;gap:11px;margin:0 0 12px;padding:13px 15px;
  border:1px solid var(--accent);border-radius:11px;background:var(--panel);box-shadow:0 12px 36px -16px var(--bg)}
/* The focus law (his 2026-07-23 chair FAIL, the 2026-07-23 chair ruling: "how the fuck am I
   supposed to read or use any of these panes on the right"): the OPEN pane is the focus —
   it escapes the margin column and takes READING WIDTH as a right-side panel over the room;
   the paper stays visible beside it; close restores exactly. One focus at a time (_soloFocus). */
#art.is-inspecting .art-inspect, #art.is-proving .art-prov, #art.is-threading .art-anchor.on{
  position:fixed; z-index:44; right:14px;
  top:calc(var(--hy-shell-real,86px) + 10px); bottom:14px;
  width:min(640px,46vw); overflow-y:auto;
  background:var(--panel); border:1px solid var(--edge2); border-radius:12px;
  padding:16px 18px;
  box-shadow:0 18px 48px -18px color-mix(in srgb, black 72%, transparent);
  font-size:12.5px}
#art.is-inspecting .art-inspect{display:flex}
/* his ruling — materialize-never-reorganize: the inspection reallocates within the MARGIN's
   own budget (the tray/rail/prov recede); the PAPER column is never crushed. */
#art.is-inspecting .art-rail-col,#art.is-inspecting .art-tray,#art.is-inspecting .art-prov{opacity:.4;transition:opacity .16s}
.art-inspect-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.art-inspect-title{font:700 12.5px var(--mono);color:var(--ink);min-width:0;overflow:hidden;text-overflow:ellipsis}
.art-inspect-k{font:9.5px var(--mono);text-transform:uppercase;letter-spacing:.08em;color:var(--dim)}
.art-inspect-body{display:flex;flex-direction:column;gap:9px;font-size:12.5px;line-height:1.6;color:var(--ink);min-width:0}
.art-inspect-body .art-dim{font-size:11.5px}
.art-inspect-doors{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.art-inspect-audit{font:10px var(--mono);color:var(--dim);border-top:1px solid var(--edge);padding-top:8px}
.art-inspect-audit code{color:var(--ink2)}
.art-frow.is-open{border-color:var(--accent);box-shadow:inset 0 0 0 1px var(--accent)}
/* The same version-rail panel claims a bounded inspection region while open.
   Historical reads, selected pair and comparison algorithm remain the existing owners;
   the fixed geometry reveals loading/result/error instead of burying them below the rail. */
#art.is-diffing .art-tray,#art.is-diffing .art-prov{opacity:.4;transition:opacity .16s}
#art.is-diffing #art-diffpane{position:fixed;z-index:44;right:14px;top:calc(var(--hy-shell-real,86px) + 10px);width:min(900px,calc(100vw - 28px));max-height:calc(100dvh - var(--hy-shell-real,86px) - 24px);overflow:auto;box-sizing:border-box;margin:0;padding:14px 16px;background:var(--panel);border:1px solid var(--edge2);border-radius:12px;box-shadow:0 18px 48px -18px color-mix(in srgb,black 72%,transparent)}
#art-diffpane .art-diffhead{position:sticky;top:-14px;z-index:1;padding:8px 0;background:var(--panel);font-size:12px;line-height:1.6;overflow-wrap:anywhere}
#art-diffpane .art-difflines{max-height:calc(100dvh - 220px);font-size:12px;line-height:1.6}
#art-diffpane .art-dline{white-space:pre-wrap;overflow-wrap:anywhere}
#art-diffpane:focus-visible,.art-difflines:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
@media(max-width:600px){#art.is-diffing #art-diffpane{right:8px;width:calc(100vw - 16px);padding:10px 12px}}
/* P5 — the comment thread (a paragraph's anchor overlay) reallocates around the anchor rather
   than floating beside a fully-lit reader: opening it recedes the reader (the context contracts)
   so the thread — the anchor overlay, a sibling of the reader, left full-opacity — is the focus,
   with its named return door. Closing restores the exact scroll + which thread was open. */
/* the comment thread materialises in the MARGIN (his ruling — the margin thread): it
   reallocates the margin (siblings recede) and the PAPER is never crushed. */
#art.is-threading .art-tray,#art.is-threading .art-rail-col,#art.is-threading .art-prov,#art.is-threading .art-inspect{opacity:.4;transition:opacity .16s}
/* the four verdict doors: composed working account + confirm/dismiss/defer/route, each
   naming its consequence before it fires (arm-then-fire). A verb that needs an authored
   choice (a defer date, a route standing-order) reveals a mini-form in the same row. */
.art-inspect-compose{display:flex;flex-direction:column;gap:7px}
.art-compose-kind{font:10px var(--mono);text-transform:uppercase;letter-spacing:.07em;color:var(--accent)}
.art-compose-line{color:var(--ink);font-size:12.5px;line-height:1.55}
.art-compose-quote{border-left:2px solid var(--edge2);padding-left:9px;color:var(--ink2);font-style:italic}
.art-compose-meta{font:10.5px var(--mono);color:var(--dim)}
.art-verb-form{display:flex;align-items:center;gap:6px;flex-wrap:wrap;width:100%;margin-top:6px}
.art-verb-form input[type=date],.art-verb-form select{font:11px var(--mono);color:var(--ink);
  background:var(--bg);border:1px solid var(--edge);border-radius:5px;padding:2px 6px}
.art-verb-msg{width:100%;margin-top:5px;font:10.5px var(--mono);color:var(--dim)}
.art-verb-msg.is-bad{color:var(--bad)}
.art-verb-msg.is-ok{color:var(--ok)}
.art-mini-door{font:10px var(--mono);padding:1px 7px;border-radius:5px;border:1px solid var(--edge);
  background:var(--panel2);color:var(--ink2);cursor:pointer}
.art-mini-door:hover{border-color:var(--accent);color:var(--ink)}
/* the verdict verbs each wear their consequence in place (item 6): a column of verb blocks,
   each a door + a plain outcome line under it. */
.art-inspect-doors[data-role="verdict-doors"]{flex-direction:column;gap:10px;align-items:stretch}
.art-verb{display:flex;flex-direction:column;gap:3px;min-width:0}
.art-verb>.hy-door{align-self:flex-start}
.art-verb-why{font:10px var(--mono);color:var(--dim);line-height:1.45;overflow-wrap:anywhere}
[data-role="route-mismatch"] b{color:var(--ink)}
.art-follow-note{color:var(--dim)}
.art-logsig{display:flex;align-items:center;gap:7px;padding:2px 0;font:10.5px var(--mono)}
.art-logsig code{color:var(--ink2);white-space:pre;overflow:hidden;text-overflow:ellipsis}
.art-log-full-h{font:10.5px var(--mono);color:var(--dim);cursor:pointer;margin-top:7px}
.art-log-full-h:hover{color:var(--ink2)}
.art-log-full{display:none;margin-top:6px}
.art-log-full.on{display:block}
.art-log-count{margin-bottom:4px}
.art-stale-badge{margin:0 0 8px;padding:6px 10px;border:1px solid var(--warn);border-radius:7px;
  background:color-mix(in srgb,var(--warn) 12%,transparent);color:var(--ink2);font:10.5px var(--mono)}
.art-tray-filter{display:flex;align-items:center;gap:7px;margin:2px 0 9px}
.art-tray-filter input{flex:1;min-width:0;font:11px var(--mono);color:var(--ink);
  background:var(--bg);border:1px solid var(--edge);border-radius:6px;padding:3px 8px}
.art-tray-filter .art-k{white-space:nowrap}
/* The provenance pane — materialised in the margin (the judgment margin's reallocation
   idiom): opening it CLAIMS the margin (the tray + rail recede), it carries a named
   return door, closing restores exactly. Every colour is a hymn var/color-mix. */
.art-prov{display:none;flex-direction:column;gap:11px;min-width:0;
  border:1px solid var(--accent);border-radius:12px;background:var(--panel);
  padding:13px 14px;box-shadow:0 14px 42px -18px var(--bg)}
#art.is-proving .art-prov{display:flex}
#art.is-proving .art-tray{opacity:.4;transition:opacity .16s}
#art.is-proving .art-rail-col{opacity:.4;transition:opacity .16s}
.art-prov-head{display:flex;align-items:center;gap:9px;flex-wrap:wrap}
.art-prov-k{font:9.5px var(--mono);text-transform:uppercase;letter-spacing:.09em;color:var(--accent)}
.art-prov-obj{font:700 11.5px var(--mono);color:var(--ink);overflow-wrap:anywhere;min-width:0}
.art-prov-kind{font:9.5px var(--mono);color:var(--dim);text-transform:uppercase;letter-spacing:.07em}
.art-prov-glance{color:var(--ink);font-size:12.5px;line-height:1.6;overflow-wrap:anywhere}
.art-prov-stations{display:flex;flex-direction:column;gap:9px;margin:2px 0}
.art-prov-station{display:flex;flex-direction:column;gap:3px;padding-left:11px;
  border-left:2px solid var(--edge2)}
.art-prov-station.is-origin{border-left-color:var(--accent)}
.art-prov-st-k{font:9px var(--mono);text-transform:uppercase;letter-spacing:.08em;color:var(--dim)}
.art-prov-st-v{color:var(--ink2);font-size:12px;line-height:1.5;overflow-wrap:anywhere}
.art-prov-st-v .art-prov-id{font:10.5px var(--mono);color:var(--dim);overflow-wrap:anywhere}
.art-prov-st-v .art-prov-term{color:var(--ink)}
.art-prov-link{font:9.5px var(--mono);border-radius:6px;padding:1px 7px;border:1px solid var(--edge2)}
.art-prov-link.is-ok{color:var(--ok)}
.art-prov-link.is-warn{color:var(--warn)}
.art-prov-doors{display:flex;flex-direction:column;gap:8px;border-top:1px solid var(--edge);padding-top:9px}
.art-prov-doorrow{display:flex;gap:7px;flex-wrap:wrap;align-items:center}
.art-prov-finding{font:10.5px var(--mono);color:var(--ink2);border:1px solid var(--edge);
  border-radius:7px;background:var(--panel2);padding:4px 8px;cursor:pointer;text-align:left;
  overflow-wrap:anywhere}
.art-prov-finding:hover{border-color:var(--accent);color:var(--ink)}
.art-prov-comment{display:flex;flex-direction:column;gap:6px;width:100%}
.art-prov-comment textarea{width:100%;min-height:52px;resize:vertical;font:11.5px var(--mono);
  color:var(--ink);background:var(--bg);border:1px solid var(--edge);border-radius:7px;padding:6px 8px}
.art-prov-msg{font:10.5px var(--mono);color:var(--dim)}
.art-prov-msg.is-bad{color:var(--bad)}
.art-prov-msg.is-ok{color:var(--ok)}
.art-prov-audit{font:10px var(--mono);color:var(--dim);border-top:1px solid var(--edge);padding-top:8px}
.art-prov-audit-h{cursor:pointer;color:var(--dim)}
.art-prov-audit-h:hover{color:var(--ink2)}
.art-prov-audit-body{display:none;margin-top:6px;display:none}
.art-prov-audit.open .art-prov-audit-body{display:block}
.art-prov-audit code{color:var(--ink2);overflow-wrap:anywhere}
.art-prov-empty{color:var(--dim);font:11px var(--mono)}
/* the reader's object affordance — the highlight IS the affordance (his ruling: kill the
   verbal chip). Hovering an equation/figure outlines its ACTUAL measured text the way a
   text selection hugs glyphs; it reads interactive (cursor + a whisper of accent); click
   opens the pane. A coarse/missing rect draws NOTHING — never an inaccurate box. */
.art-objsel{position:absolute;z-index:3;cursor:pointer;border-radius:2px;
  background:color-mix(in srgb,var(--accent) 12%,transparent);
  outline:1px solid color-mix(in srgb,var(--accent) 50%,transparent);outline-offset:-1px}
.art-objsel:hover{background:color-mix(in srgb,var(--accent) 17%,transparent)}
/* the source-pane \label affordance in the source bar */
.art-labelprov{font:10px var(--mono);padding:1px 8px;border-radius:6px;border:1px solid var(--accent);
  background:var(--panel2);color:var(--accent);cursor:pointer}
.art-labelprov:hover{background:color-mix(in srgb,var(--accent) 14%,transparent);color:var(--ink)}
/* the his-hand layer — the passages the author edited himself. The toggle chip in the
   source bar, and a faint gold wash + left-edge tick on his CM6 lines (applied as a class
   on .cm-line, re-applied on every view update since the bundle exports no Decoration). */
.art-hishand-chip{font:10px var(--mono);padding:1px 8px;border-radius:6px;border:1px solid var(--edge2);
  background:var(--panel2);color:var(--ink2);cursor:pointer}
.art-hishand-chip:hover{border-color:var(--warn);color:var(--ink)}
.art-hishand-chip.is-on{border-color:var(--warn);color:var(--warn);
  background:color-mix(in srgb,var(--warn) 13%,transparent)}
.art-hishand-chip.is-off{cursor:default;color:var(--dim);border-color:var(--edge2)}
.art-hishand-chip.is-off:hover{border-color:var(--edge2);color:var(--dim)}
.cm-line.art-hishand-line{background:color-mix(in srgb,var(--warn) 12%,transparent);
  box-shadow:inset 2px 0 0 var(--warn)}
/* ── the final polish pass (2026-07-23) ─────────────────────────────────────────
   #1 (worst in the instrument) — the margin is BOUND to the viewport: it no longer
   runs to a black void under the paper. It gets the same viewport-derived cap the
   reader uses, so the three columns END together; the findings tray scrolls WITHIN
   the bounded margin while the version rail stays PINNED at the foot, visible on
   screen. #2 in reading mode (the source folded) the paper is capped to a sensible
   centred column so it fills its room instead of floating in a wide pane. #3 the
   group severity pill is a NON-FILLED small-caps label — clearly distinct from the
   filled per-finding severity badge (the two near-identical pinks separated). #4 the
   source explanation drops to one quiet note line under the state-chip row. */
.art-margin{max-height:calc(100vh - var(--hy-shell-real,86px) - 96px);overflow-y:auto}
.art-margin>.art-tray{display:flex;flex-direction:column;min-height:0;flex:0 1 auto}
.art-tray.open>.art-tray-body{flex:1 1 auto;min-height:0;overflow-y:auto}
.art-margin>.art-rail-col{flex:none}
/* read mode: the paper takes the room (his 2026-07-23 full-bleed ruling); the page
   render itself is bounded by renderPdf's fit ceiling, so no pane cap is needed */
.art-main[data-mode="read"] .art-pdf-pane{margin-left:auto;margin-right:auto}
.art-grp-sev{font:9.5px var(--mono);text-transform:uppercase;letter-spacing:.09em;
  padding:1px 7px;border-radius:6px;border:1px solid currentColor;background:none}
.art-grp-sev.sev-hard{color:var(--bad)}
.art-grp-sev.sev-soft{color:var(--warn)}
.art-grp-sev.sev-deferred{color:var(--dim)}
.art-source-note{display:none}
.art-source-note.on{display:flex;flex-wrap:wrap;align-items:center;gap:6px;
  margin:-2px 0 8px;font:10px var(--mono);color:var(--dim);line-height:1.5}
.art-source-note-x{cursor:pointer;color:var(--dim);border:none;background:none;
  font:11px var(--mono);line-height:1;padding:0 2px;margin-left:2px}
.art-source-note-x:hover{color:var(--ink2)}
/* The PDF zoom (his 2026-07-23 chair FAIL — "not being able to zoom in is kind of criminal"):
   a quiet floating cluster pinned to the top-right of the pdf pane (#art-pdf-pane is
   position:relative). At ZOOM>1 the page runs past the pane and the reader (overflow:auto)
   scrolls it — hugging the left so the left margin is never clipped. Colours are hymn vars only. */
.art-zoom{position:absolute;top:10px;right:14px;z-index:6;display:flex;align-items:center;gap:3px;
  padding:3px 4px;border-radius:9px;border:1px solid var(--edge2);
  background:color-mix(in srgb,var(--panel) 90%,transparent);
  box-shadow:0 6px 20px -10px var(--bg);font:11px var(--mono)}
.art-zoom-b{font:12px var(--mono);line-height:1;color:var(--ink2);background:var(--panel2);
  border:1px solid var(--edge);border-radius:6px;padding:3px 8px;cursor:pointer;min-width:26px}
.art-zoom-b:hover{border-color:var(--accent);color:var(--ink)}
.art-zoom-fit{min-width:0;padding:3px 9px}
.art-zoom-pct{min-width:44px;text-align:center;color:var(--ink2)}
#art-reader.zoomed{align-items:flex-start}
#art-reader.zoomed .art-page,#art-reader.zoomed canvas.pgcv{max-width:none}
/* ── ANCHORED MARKS + MINIMAP (his 2026-07-23 pick — the information lives WHERE IT
   POINTS: findings/comments render as marks in a gutter at their anchor beside the paper,
   a density minimap charts the whole document, the shelf NAMES what has no line to point
   at). Re-placed after every render (percentage-of-page tops → zoom/refit survive). Every
   colour is a hymn var/color-mix — the one-palette clause holds. ──────────────────────── */
.art-gutter{position:absolute;top:0;bottom:0;right:0;width:20px;pointer-events:none;z-index:4}
.art-mark{position:absolute;right:3px;width:13px;height:13px;transform:translateY(-50%);
  pointer-events:auto;cursor:pointer;border-radius:3px;border:1px solid var(--edge2);
  background:var(--panel);color:var(--ink2);font:8px/1 var(--mono);padding:0;
  display:flex;align-items:center;justify-content:center;box-shadow:0 1px 4px -2px var(--bg)}
.art-mark:hover{border-color:var(--accent);color:var(--ink);z-index:5;transform:translateY(-50%) scale(1.2)}
.art-mark.sev-hard{border-color:var(--bad);color:var(--bad);background:color-mix(in srgb,var(--bad) 20%,var(--panel))}
.art-mark.sev-soft{border-color:var(--warn);color:var(--warn);background:color-mix(in srgb,var(--warn) 20%,var(--panel))}
.art-mark.sev-deferred{border-color:var(--edge2);color:var(--dim)}
.art-mark.kind-comment{border-color:var(--accent);color:var(--accent);background:color-mix(in srgb,var(--accent) 16%,var(--panel))}
.art-mark.kind-object{width:8px;height:8px;border-radius:9px;border-color:var(--edge2);
  color:transparent;background:color-mix(in srgb,var(--ink2) 22%,transparent);box-shadow:none}
.art-mark.kind-object:hover{color:transparent;background:color-mix(in srgb,var(--accent) 42%,transparent)}
.art-mark.is-cluster{font-weight:700}
.art-mark-n{font:8px/1 var(--mono)}
/* the minimap — the whole-document chart riding the pdf pane's right edge, beside #art-reader */
.art-minimap{position:absolute;top:8px;bottom:8px;right:3px;width:12px;z-index:6;
  border-radius:6px;border:1px solid var(--edge2);overflow:hidden;cursor:pointer;
  background:color-mix(in srgb,var(--panel) 74%,transparent)}
.art-minimap-rule{position:absolute;left:0;right:0;height:1px;background:var(--edge2);opacity:.55}
.art-minimap-tick{position:absolute;right:1px;width:8px;height:2px;border-radius:1px;
  pointer-events:none;background:var(--dim)}
.art-minimap-tick.sev-hard{background:var(--bad)}
.art-minimap-tick.sev-soft{background:var(--warn)}
.art-minimap-tick.sev-deferred{background:color-mix(in srgb,var(--dim) 70%,transparent)}
.art-minimap-tick.kind-comment{background:var(--accent);width:9px}
.art-minimap-tick.kind-object{width:4px;background:color-mix(in srgb,var(--ink2) 34%,transparent)}
.art-minimap-tick.is-cluster{height:3px}
.art-minimap-view{position:absolute;left:0;right:0;min-height:8px;border-radius:3px;
  background:color-mix(in srgb,var(--accent) 20%,transparent);border:1px solid var(--accent)}
/* the unanchored shelf — NAMED at the minimap's foot, never a silent drop (his ruling) */
.art-shelf{position:absolute;bottom:8px;right:20px;z-index:7;display:flex;flex-direction:column;
  align-items:flex-end;gap:5px}
.art-shelf-chip{font:10px var(--mono);color:var(--warn);cursor:pointer;border:1px dashed var(--warn);
  border-radius:7px;padding:2px 8px;background:color-mix(in srgb,var(--panel) 90%,transparent)}
.art-shelf-chip:hover{color:var(--ink);border-color:var(--accent)}
.art-shelf-list{display:none;flex-direction:column;gap:3px;max-height:46vh;overflow:auto;max-width:280px;
  padding:8px 9px;border:1px solid var(--edge);border-radius:9px;background:var(--panel);
  box-shadow:0 14px 42px -18px var(--bg)}
.art-shelf.on .art-shelf-list{display:flex}
.art-shelf-h{font:9.5px var(--mono);color:var(--dim);text-transform:uppercase;letter-spacing:.08em;margin-bottom:2px}
.art-shelf-row{text-align:left;font:10px var(--mono);color:var(--ink2);cursor:pointer;
  border:1px solid var(--edge2);border-radius:6px;padding:2px 7px;background:var(--panel2)}
.art-shelf-row:hover{border-color:var(--accent);color:var(--ink)}
.art-shelf-row b{color:var(--warn)}
/* the anchor label + show-in-paper in a focus panel head (navigation lands focus, his law) */
.art-inspect-anchor{font:9.5px var(--mono);color:var(--accent);border:1px solid var(--edge2);
  border-radius:6px;padding:1px 7px;white-space:nowrap}
.art-show-in-paper{white-space:nowrap}
`;
function injectStyle() {
  injectEngineCSS();   // the shared engine atoms (.eng-return, .lit) the inspection consumes
  if (typeof document === "undefined" || document.getElementById("art-components")) return;
  const st = document.createElement("style"); st.id = "art-components"; st.textContent = COMPONENT_CSS;
  document.head.appendChild(st);
}

// ── module state (one surface, one model) ──────────────────────────────────────
let CTX = null;        // /artefact/context payload — the authority
let PLAN = null;       // /shared/plan payload — nodes → sections/beats
let VERS = null;       // /shared/versions payload — the rail
let PDFLIB = null;     // pdf.js module
let PDFDOC = null;     // the rendered document
let RENDER_SEQ = 0;    // render ownership token — a resize/fold re-render obsoletes older loops
let ZOOM = 1;          // the reader zoom (his 2026-07-23 chair FAIL the 2026-07-23 chair ruling:
                       // "not being able to zoom in is kind of criminal") — multiplies the fit width
const ZOOM_KEY = "art-zoom";   // the remembered zoom (per session, clamped 0.5–3, restored at wire)
let RAILSEL = [];      // up to two rail row ids (composite _rid) for a diff
const NODEMAP = {};    // corpus → nodemap_state (cached; the anchor truth)
let lastRevKey = null; // A1: the resolved-revision identity last rendered
let hintDone = false;  // R5: the hint strip retires after the first successful ¶ click

// ── ACT 3 state: three modes of one pane set + the live source⇄pdf loop ─────────
let MODE = "read";            // "read" (the source folded) | "edit" (the split — the resting posture)
const POSTURE_KEY = "art-posture";      // the remembered posture (per session)
const MARGIN_KEY = "art-margin";        // the remembered margin fold (per session)
const SPLIT_KEY = "art-split-pct";      // #8 — the remembered source|pdf divider ratio (per session)
function rememberedPosture() {
  try { return sessionStorage.getItem(POSTURE_KEY) || "edit"; } catch (e) { return "edit"; }
}
let EDIT_FILE = null;         // repo-relative tex FRAGMENT (or root) currently open in CM6
let EDIT_SOURCE_DIGEST = null;
let EDIT_LOAD_GENERATION = 0;
let CM_VIEW = null;           // the live CodeMirror EditorView (null on textarea fallback)
let CM_MOD = null;            // the codemirror.bundle.mjs module (EditorView.scrollIntoView)
let EDIT_PDF_REL = null;      // the freshest edit-loop compiled pdf; overrides the reader
let EDIT_PDF_TARGET = null;   // existing rendered asset's declared project/root basis
                               // pane's revision pdf ONLY while MODE === "edit"
let FOLLOW = null;            // last /projection/follow read for EDIT_FILE
let FOLLOW_TIMER = null;      // periodic follow refresh, live only while MODE === "edit"
let RECOMPILE_TIMER = null;   // the recompile-status poll interval
let SRC_DEBOUNCE = 0;         // CM cursor-move → /projection/locate debounce handle
// THE ECHO GUARD, as a factory rather than a bare flag. makeFollowGuard(ms) hands back a
// TIME-BOXED suppression token: suppress() opens the window, isSuppressed() reads it, and
// the window closes on its own after `ms` — a latch (a flag someone forgets to clear) would
// deafen follow for the rest of the session, which is the failure this shape forecloses.
// One live instance guards the wired resolvers below; the FACTORY is exposed on window so
// the headless tier can drive the mechanism in isolation without reaching into module state.
function makeFollowGuard(ms) {
  const span = Math.max(0, Number(ms) || 0);
  let until = 0;
  return {
    windowMs: span,
    suppress() { until = Date.now() + span; },
    isSuppressed() { return Date.now() < until; },
    release() { until = 0; },
  };
}
if (typeof window !== "undefined") window.__pvFollowGuardFactory = makeFollowGuard;
const FOLLOW_GUARD = makeFollowGuard(150);  // the live guard on the wired follow path
const ASSETS_CACHE = {};      // corpus → /assets/list payload (asset door-chips, D-plain)
let ANCHOR_GEN = 0;           // guards a stale async asset-chip append onto a since-closed overlay
let HISHAND = null;           // /review/his-hand payload for EDIT_FILE — the author's own ranges
let HISHAND_ON = false;       // the his-hand highlight toggle (off until he asks for it)

// ── E4: the focus grammar layered onto the editor's own panes (engine.mjs) ──────
// One inspection area: opening a finding REALLOCATES (it claims the area, siblings compact),
// closing RESTORES exactly (geometry + scroll + which finding was open). Every focused state
// carries the visible named return door; the highlight bus is cleared at every open/switch/close.
let INSPECT = createFocusState("artefact");   // {hover,pinned,opened,restore,entry}
let INSPECT_BUS = null;                        // the highlight bus (lit .lit across the tray)
let INSPECT_OPEN = null;                       // the open object's key, or null (base altitude)
let INSPECT_LAST_FID = null;                   // which finding was last open (restore memory)
// P5 — the version-diff + comment-thread focuses get the SAME reallocation grammar: each
// captures the scroll at open and restores it exactly at close, and remembers which one was
// open (the restore memory), so crossing cockpit→editor no longer feels like crossing a border.
let DIFF_RESTORE_Y = 0, DIFF_OPEN = null, DIFF_LAST = null;
let DIFF_GENERATION = 0, DIFF_OPENER = null, DIFF_PROJECT = null;      // the version diff's focus geometry
let THREAD_RESTORE_Y = 0, THREAD_OPEN = null, THREAD_LAST = null; // the comment thread's focus geometry
// One focus at a time (his 2026-07-23 chair FAIL the 2026-07-23 chair ruling: "how the fuck am I
// supposed to read or use any of these panes on the right"). The focus law makes each open pane a
// fixed right-side reading panel; two at once stack and become unreadable. So before an open adds
// its own class, tear down whichever of the OTHER three focuses is live — through its OWN close
// (scroll-restore + restore-memory + pane clear intact), never a bare class strip. `keep` is the
// class the caller is about to add. The close functions are hoisted declarations (order-safe).
function _soloFocus(root, keep) {
  if (!root) return;
  if (keep !== "is-inspecting" && root.classList.contains("is-inspecting")) closeInspection();
  if (keep !== "is-proving"    && root.classList.contains("is-proving"))    closeProvenance();
  if (keep !== "is-threading"  && root.classList.contains("is-threading"))  closeAnchor();
  if (keep !== "is-diffing"    && root.classList.contains("is-diffing"))    closeDiff();
}

// ── pdf.js reader (re-housed from projection_viewer.html) ───────────────────────
async function ensurePdfjs() {
  if (PDFLIB) return PDFLIB;
  const mod = await import("/shared/pdfjs/pdf.min.mjs");
  mod.GlobalWorkerOptions.workerSrc = "/shared/pdfjs/pdf.worker.min.mjs";
  PDFLIB = mod;
  return mod;
}

async function buildTextLayer(wrap, page, viewport) {
  if (!page || wrap.querySelector(".pgtext")) return;
  let tc;
  try { tc = await page.getTextContent(); } catch (e) { return; }
  const layer = document.createElement("div");
  layer.className = "pgtext";
  const vp1 = page.getViewport({ scale: 1 });
  for (const it of tc.items) {
    if (!it.str) continue;
    const tx = PDFLIB.Util.transform(vp1.transform, it.transform);
    const fs = Math.hypot(tx[2], tx[3]) * viewport.scale;
    const sp = document.createElement("span");
    sp.textContent = it.str;
    sp.style.left = (tx[4] * viewport.scale) + "px";
    sp.style.top = ((tx[5] * viewport.scale) - fs) + "px";
    sp.style.fontSize = fs + "px";
    layer.appendChild(sp);
  }
  wrap.appendChild(layer);
}

// resolve the {pdf, tex, label} the reader shows: a selected ?version= row (deep-linkable),
// else — when the server-computed current_artefact is a raw editor candidate, never a minted
// release — the newest banked release row from the SAME versions rail; else the
// current_artefact itself. NEVER a client-side file guess: both branches read server-computed
// facts (registry.project_context's current_artefact, shared_ui.versions_join's rail), this
// only picks WHICH of the two a reader defaults to.
//
// his 2026-07-23 walk finding (the 2026-07-23 chair ruling): current_artefact resolves to main.pdf —
// the live editor candidate — whenever the release state machine isn't literally "RELEASED"
// (paper_falqon has no release/state.json sidecar despite a real minted r2 release sitting
// right beside it), so a bare reader arrival served whatever the last probe/editor compile
// happened to leave in main.pdf. A reader's "current" must be the minted/banked real artefact;
// an editor live-compile is served as current ONLY inside the edit posture that made it —
// activePdfRel() still checks EDIT_PDF_REL FIRST, unconditionally, so the live loop (the save +
// recompile round-trip) is untouched by this — it only changes what "current" defaults to
// BEFORE that loop has minted anything of its own.
function currentRevision() {
  const v = store.field("version");
  if (v && VERS) {
    const rows = VERS.rows || [];
    let row = rows.find((r) => r._rid === v);
    if (!row) {
      row = rows.find((r) => String(r.id) === v);
      if (row) console.warn("artefact: ?version=" + v + " is a bare (pre-disambiguation) id — " +
        "resolved to the first match (" + row._rid + "); re-link with the composite id.");
    }
    if (row) {
      const paths = row.paths || [];
      return { pdf: paths.find((p) => /\.pdf$/i.test(p)) || null,
               tex: paths.find((p) => /\.tex$/i.test(p)) || null,
               label: row.label || row.id, id: row._rid, kind: row.kind };
    }
  }
  const a = (CTX && CTX.current_artefact) || {};
  if (a.kind !== "release" && VERS && Array.isArray(VERS.rows)) {
    const rel = VERS.rows.find((r) => r.kind === "release" &&
      (r.paths || []).some((p) => /\.pdf$/i.test(p)));
    if (rel) {
      const paths = rel.paths || [];
      return { pdf: paths.find((p) => /\.pdf$/i.test(p)) || null,
               tex: a.tex || null,   // the editable tex stays the LIVE main.tex, never a release fossil
               label: rel.label || rel.id, id: rel._rid || rel.id, kind: rel.kind };
    }
  }
  return { pdf: a.pdf || null, tex: a.tex || null,
           label: a.version_id || a.kind || "current", id: null, kind: a.kind };
}

async function renderPdf(pdfRel, into, isCurrent = () => true) {
  const seq = ++RENDER_SEQ;   // a newer render owns the pane; stale loops stop appending
  const current=()=>seq===RENDER_SEQ&&isCurrent();
  if(!current())return;
  into.innerHTML = "<div class='art-msg'>rendering…</div>";
  let lib;
  try { lib = await ensurePdfjs(); } catch (e) {
    if(!current())return;
    into.innerHTML = "<div class='art-msg'>pdf.js failed to load — reader offline.</div>"; return; }
  if(!current())return;
  let doc;
  try {
    doc = await lib.getDocument({ url: CTX.pdf_endpoint + "?file=" + ec(pdfRel) }).promise;
  } catch (e) {
    if(!current())return;
    into.innerHTML = "<div class='art-msg'>could not open the pdf — <code>" +
      esc((e && e.message) || "getDocument failed") + "</code></div>"; return; }
  if (!current()) return;
  PDFDOC = doc;
  into.innerHTML = "";
  // fit the pane, not a fixed column (his 2026-07-23 full-bleed ruling); the ceiling
  // only bounds render cost on ultrawide glass. ZOOM multiplies the fit — at >1 the page
  // overflows the pane and the reader (overflow:auto) scrolls it (the "criminal" no-zoom fix).
  const base = Math.min(1400, (into.clientWidth || 800) - 8);
  const fitW = Math.max(140, Math.round(base * ZOOM));
  into.dataset.fitw = String(fitW);
  into.classList.toggle("zoomed", ZOOM > 1.001);
  const dpr = window.devicePixelRatio || 1;
  for (let i = 1; i <= doc.numPages; i++) {
    if (!current()) return;
    const page = await doc.getPage(i);
    if(!current())return;
    const vp1 = page.getViewport({ scale: 1 });
    const scale = Math.max(0.4, fitW / vp1.width);
    const vp = page.getViewport({ scale });
    const wrap = document.createElement("div");
    wrap.className = "art-page"; wrap.dataset.page = i;
    wrap.dataset.pw = vp1.width; wrap.dataset.ph = vp1.height;
    wrap.style.width = Math.floor(vp.width) + "px";
    const cv = document.createElement("canvas");
    cv.className = "pgcv";
    cv.width = Math.floor(vp.width * dpr); cv.height = Math.floor(vp.height * dpr);
    cv.style.width = Math.floor(vp.width) + "px"; cv.style.height = Math.floor(vp.height) + "px";
    wrap.appendChild(cv);
    into.appendChild(wrap);
    const ctx2 = cv.getContext("2d", { alpha: false });
    ctx2.scale(dpr, dpr);
    await page.render({ canvasContext: ctx2, viewport: vp }).promise;
    if(!current())return;
    // the PAINTED signal: a canvas exists from the moment it is appended, so "the element
    // is there" proves nothing about pixels. `.loaded` lands only once render() resolved —
    // the one honest thing for a watcher (or a headless tier) to wait on.
    cv.classList.add("loaded");
    await buildTextLayer(wrap, page, vp);
    if(!current())return;
  }
}

// ACT 3: while MODE === "edit" and the live loop has minted a fresh compile, the pdf pane
// shows THAT pdf (what synctex resolves against) — never the release revision, which would
// desync the two-way coupling. Every other mode (and edit before its first compile) shows
// the server-resolved current revision, unchanged.
function activePdfRel() {
  if (MODE === "edit" && EDIT_PDF_REL && EDIT_PDF_TARGET?.params.compile_root===compileParams(EDIT_FILE).compile_root && EDIT_PDF_TARGET.params.corpus===_corpus()) return EDIT_PDF_REL;
  return currentRevision().pdf;
}
async function loadReader(isCurrent = () => true) {
  if(!isCurrent())return;
  const rev = currentRevision();
  const badge = $("#art-rev");
  const pdfRel = activePdfRel();
  // the badge stutter (his 2026-07-23 walk finding): rev.label falls back to rev.kind
  // itself when no sharper label is known (e.g. a candidate with no version_id) — rendering
  // BOTH then read "a candidate candidate". Only carry the id/label span when it says
  // something the kind span didn't already say.
  const kindTxt = rev.kind ? "a " + rev.kind : "the current copy";
  const showId = rev.label && rev.label !== rev.kind;
  if (badge) badge.innerHTML = (MODE === "edit" && EDIT_PDF_REL && pdfRel===EDIT_PDF_REL)
    ? "<span class='art-rev-kind'>the live compile</span> <span class='art-rev-id'>" +
      esc(EDIT_PDF_REL.split("/").pop()) + "</span>"
    : "<span class='art-rev-kind'>" + esc(kindTxt) + "</span>" +
      (showId ? " <span class='art-rev-id'>" + esc(rev.label) + "</span>" : "");
  const into = $("#art-reader");
  if (!pdfRel) {
    into.innerHTML = "<div class='art-msg'>" + (MODE === "edit"
      ? "not compiled yet — press <b>save + recompile</b> to build the live pdf."
      : "no built pdf for this revision — the version rail offers the banked rebuild.") +
      "</div>";
    return;
  }
  await renderPdf(pdfRel, into, isCurrent);
  if(!isCurrent())return;
  await ensureNodemap().catch(() => {});   // warm the anchor truth so hover answers immediately
  if(!isCurrent())return;
  refreshMarks();   // the single producer: re-place the gutter marks + re-chart the minimap
                    // after every render pass (zoom/refit/hot-reload all route through here)
}

// ── The page answers (burn-down #2: "the reader must respond to the user") ──────
function _pagePoint(e, wrap) {
  const rect = wrap.getBoundingClientRect();
  const pw = parseFloat(wrap.dataset.pw) || 612, ph = parseFloat(wrap.dataset.ph) || 792;
  return { page: parseInt(wrap.dataset.page, 10),
           px: (e.clientX - rect.left) * (pw / rect.width),
           py: (e.clientY - rect.top) * (ph / rect.height), rect, pw, ph };
}

// the nearest anchor line at/above (page, py); falls back to the LAST anchor of the nearest
// earlier page (a click above a page's first line belongs to the paragraph flowing over).
function anchorAtPoint(pageNo, py, allowPrevPages) {
  const nm = NODEMAP[_corpus()];
  if (!nm || !nm.present || !nm.entries) return null;
  for (let p = pageNo; p >= 1; p--) {
    let best = null;
    for (const [aid, regions] of Object.entries(nm.entries)) {
      for (const r of regions || []) {
        if (r.page !== p || typeof r.y0 !== "number") continue;
        if (p === pageNo && r.y0 > py + 2) continue;
        if (!best || r.y0 > best.y0) best = { aid, y0: r.y0, region: r };
      }
    }
    if (best) {
      let next = null;
      for (const regions of Object.values(nm.entries)) for (const r of regions || [])
        if (r.page === best.region.page && typeof r.y0 === "number" && r.y0 > best.y0 &&
            (next === null || r.y0 < next)) next = r.y0;
      best.yEnd = next !== null ? next : best.y0 + 36;
      return best;
    }
    if (!allowPrevPages) return null;
  }
  return null;
}

function _bandFor(wrap, hit, cls) {
  const rect = wrap.getBoundingClientRect();
  const ph = parseFloat(wrap.dataset.ph) || 792, pw = parseFloat(wrap.dataset.pw) || 612;
  const sy = rect.height / ph, sx = rect.width / pw;
  const r = hit.region;
  const el = document.createElement("div");
  el.className = cls;
  el.style.left = ((r.x0 || 0) * sx) + "px";
  el.style.width = Math.max(0, ((r.x1 || pw) - (r.x0 || 0)) * sx) + "px";
  el.style.top = (hit.y0 * sy - 12) + "px";
  el.style.height = Math.max(14, (hit.yEnd - hit.y0) * sy) + "px";
  return el;
}

let HOVER_EL = null, HOVER_CHIP = null, HOVER_AID = null, hoverRaf = 0, nmWarmed = false;
let HOVER_OBJ_ELS = [], HOVER_OBJ_AID = null;
function clearObjHover() {
  for (const el of HOVER_OBJ_ELS) el.remove();
  HOVER_OBJ_ELS = []; HOVER_OBJ_AID = null;
}
function clearHover() {
  if (HOVER_EL) HOVER_EL.remove(); if (HOVER_CHIP) HOVER_CHIP.remove();
  HOVER_EL = HOVER_CHIP = HOVER_AID = null;
  clearObjHover();
}
// the affordance IS the highlight (his ruling): draw the object's ACTUAL measured rect(s)
// as a selection-style wash that hugs the rendered text — per-line for a multi-line
// equation, the true frame for a figure. No floating label, no band over prose; it reads
// interactive (cursor + a whisper of accent) and the click opens the pane. A coarse or
// missing rect draws NOTHING (his exact complaint — never an inaccurate outline).
function showObjHover(wrap, obj) {
  if (!obj) { clearObjHover(); return; }
  if (HOVER_OBJ_AID === obj.aid && HOVER_OBJ_ELS.length && HOVER_OBJ_ELS[0].parentElement === wrap) return;
  clearObjHover();
  const rects = objectRects(obj.aid);
  if (!rects.length) return;                            // coarse/missing → no highlight at all
  HOVER_OBJ_AID = obj.aid;
  const b = wrap.getBoundingClientRect();
  const ph = parseFloat(wrap.dataset.ph) || 792, pw = parseFloat(wrap.dataset.pw) || 612;
  const sy = b.height / ph, sx = b.width / pw;
  for (const r of rects) {
    const el = document.createElement("div");
    el.className = "art-objsel";
    el.style.left = ((r.x0 || 0) * sx) + "px";
    el.style.top = (Math.min(r.y0, r.y1) * sy) + "px";
    el.style.width = Math.max(4, ((r.x1 || pw) - (r.x0 || 0)) * sx) + "px";
    el.style.height = Math.max(8, Math.abs(r.y1 - r.y0) * sy) + "px";
    el.title = "click to open where this came from";
    wrap.appendChild(el);
    HOVER_OBJ_ELS.push(el);
  }
}
function showHover(e) {
  const wrap = e.target && e.target.closest ? e.target.closest(".art-page") : null;
  if (!wrap) { clearHover(); return; }
  if (!nmWarmed) { nmWarmed = true; ensureNodemap().catch(() => {}); }
  const pt = _pagePoint(e, wrap);
  const obj = objectAtPoint(pt.page, pt.px, pt.py);
  if (obj) {
    // the object affordance takes the point: the highlight IS the affordance. Clear the ¶
    // hover so ONE clear interactive object shows — no floating label, no prose collision.
    if (HOVER_EL) HOVER_EL.remove(); if (HOVER_CHIP) HOVER_CHIP.remove(); HOVER_EL = HOVER_CHIP = HOVER_AID = null;
    showObjHover(wrap, obj);
    return;
  }
  clearObjHover();
  const hit = anchorAtPoint(pt.page, pt.py, false);
  if (!hit) { if (HOVER_EL) HOVER_EL.remove(); if (HOVER_CHIP) HOVER_CHIP.remove(); HOVER_EL = HOVER_CHIP = HOVER_AID = null; return; }
  if (HOVER_AID === hit.aid && HOVER_EL && HOVER_EL.parentElement === wrap) return;
  if (HOVER_EL) HOVER_EL.remove(); if (HOVER_CHIP) HOVER_CHIP.remove();
  HOVER_AID = hit.aid;
  HOVER_EL = _bandFor(wrap, hit, "art-hoverband");
  HOVER_CHIP = document.createElement("div");
  HOVER_CHIP.className = "art-hoverchip";
  const logical=paragraphSourceIdentity(hit.region);
  HOVER_CHIP.textContent = logical.specIds.length>1?"¶ "+logical.specIds.length+" planned units":"¶ "+(logical.specId||"source passage");
  HOVER_CHIP.style.right = "6px";
  HOVER_CHIP.style.top = HOVER_EL.style.top;
  wrap.appendChild(HOVER_EL); wrap.appendChild(HOVER_CHIP);
}

function flashRegion(wrap, hit) {
  const el = _bandFor(wrap, hit, "art-flashband");
  wrap.appendChild(el);
  el.addEventListener("animationend", () => el.remove());
}

// R5 — the hint strip is scaffolding: the first successful ¶ click retires it for good.
function retireHint() {
  if (hintDone) return;
  hintDone = true;
  const h = $("#art-hint"); if (h) h.classList.add("done");
}

async function onPageClick(e) {
  const mkEl = e.target.closest(".art-mark");     // a gutter mark → its focus (navigation lands focus)
  if (mkEl) { openMarkFromEl(mkEl); return; }
  if (e.target.closest(".art-anchor")) return;   // clicks inside the overlay handled below
  const wrap = e.target && e.target.closest ? e.target.closest(".art-page") : null;
  if (!wrap) return;
  const sel = window.getSelection && window.getSelection();
  if (sel && !sel.isCollapsed) return;           // selecting text, not asking a question
  const pt = _pagePoint(e, wrap);
  const nm = await ensureNodemap();
  await ensurePlan();
  const overlayY = e.clientY - $(".art-reader-col").getBoundingClientRect().top;
  // ACT 3: in edit mode EVERY pdf-paragraph click also fires the reverse synctex resolve
  // (it needs no nodemap — synctex is its own truth) so the source pane follows regardless
  // of anchor-overlay coverage.
  if (MODE === "edit") syncClickToSource(pt);
  // The object opener — an equation or figure region under the click opens the provenance
  // pane (where it came from), never the paragraph annotate overlay. Prose around the object
  // still opens the anchor overlay below. This is the reader's "open a pane on an equation".
  const obj = objectAtPoint(pt.page, pt.px, pt.py);
  if (obj) { retireHint(); const ref = await objectRefFor(obj.aid, obj.kind); await openProvenance(ref); return; }
  // Map absent → the click still ANSWERS: the plain unanchored overlay (never a dead click).
  if (!nm || !nm.present) { openUnanchored(overlayY, "map absent"); return; }
  const hit = anchorAtPoint(pt.page, pt.py, true);
  if (!hit) { openUnanchored(overlayY, "off-anchor"); return; }
  const logical = paragraphSourceIdentity(hit.region);
  const sec = logical.sourceSection;
  if(!sec){openUnanchored(overlayY,"source occurrence is not recorded");return;}
  const hitObj = { wrap, hit };
  LAST_HIT = hitObj;
  const quote = lineTextAt(wrap, e.clientY);   // the clicked line's text → the comment quote
  openAnchorOverlay(sec, { para: logical.specId, spec_ids:logical.specIds, page: pt.page, px: pt.px, py: pt.py, quote, hit: hitObj });
  retireHint();
}

function wireReaderResponse() {
  const reader = $("#art-reader");
  if (!reader || reader.dataset.answers) return;
  reader.dataset.answers = "1";
  reader.addEventListener("mousemove", (e) => {
    if (hoverRaf) return;
    hoverRaf = requestAnimationFrame(() => { hoverRaf = 0; showHover(e); });
  });
  reader.addEventListener("mouseleave", clearHover);
  reader.addEventListener("click", onPageClick);
  reader.addEventListener("mouseup", onReaderMouseUp);   // item 5a — the text-selection comment affordance
}

// ── The anchor overlay (D5) — nodes + beat + annotate, pinned near the paragraph ──
let ANCHOR_CTX = null;   // {section, para, node} for the annotate bank
let LAST_HIT = null;     // {wrap, hit} of the last resolved click — the annotate flash target
function positionAnchor() { /* the thread lives in the margin now — no absolute positioning */ }

// the rendered text of the line under a click (from the pdf text layer) — the comment's quote.
function lineTextAt(wrap, clientY) {
  if (!wrap) return "";
  const cand = [];
  for (const s of wrap.querySelectorAll(".pgtext span")) {
    const r = s.getBoundingClientRect();
    if (clientY >= r.top - 2 && clientY <= r.bottom + 2) cand.push([r.left, s.textContent || ""]);
  }
  cand.sort((a, b) => a[0] - b[0]);
  return cand.map((c) => c[1]).join("").replace(/\s+/g, " ").trim().slice(0, 200);
}
// the synctex join (the SAME one the follow feature uses): a pdf (page,x,y) → source file+line.
// Null when synctex is not built for the shown pdf — the thread then falls back to page+quote.
async function resolveSynctexLine(page, px, py) {
  const file = EDIT_FILE || (CTX && CTX.current_artefact && CTX.current_artefact.tex) || currentRevision().tex;
  if (!file || page == null) return null;
  try {
    const res = await store.fetchJSON("/projection/synctex",
      { params: compileParams(file,{page, x: (px || 0).toFixed(2), y: (py || 0).toFixed(2)}) });
    if (res && !res.error && res.line) return { file: res.file || file, line: res.line };
  } catch (e) { /* synctex absent — the plain page+quote fallback carries the anchor */ }
  return null;
}
// the marker in the paper (the ¶ idiom): a quiet persistent band where the comment lands.
let MARKER_ELS = [];
function clearLineMarker() { for (const el of MARKER_ELS) el.remove(); MARKER_ELS = []; }
function drawLineMarker(hitObj) {
  clearLineMarker();
  if (!hitObj || !hitObj.wrap || !hitObj.wrap.isConnected) return;
  const band = _bandFor(hitObj.wrap, hitObj.hit, "art-line-marker");
  const chip = document.createElement("div");
  chip.className = "art-line-marker-chip"; chip.textContent = "¶ comment";
  chip.style.right = "6px"; chip.style.top = band.style.top;
  hitObj.wrap.appendChild(band); hitObj.wrap.appendChild(chip);
  MARKER_ELS.push(band, chip);
}
// the node chip is a REAL door (not a dead <span>): an <a href> to /conceptric?node=… so the
// title tells the truth and the reader→conceptric jump lands. It rides the .art-adoor path
// (wireChrome navigates data-goto), and carries data-node so a HOVER still peeks the essence
// inline (showEssence) — the peek is an addition ON TOP of the door, never instead of it.
function nodeChipHTML(nid) {
  const kind = (nid.split(":")[0] || "").trim();
  const goto = "/conceptric?corpus=" + ec(_corpus()) + "&node=" + ec(nid);
  return "<a href='" + esc(goto) + "' class='hy-chip art-node art-adoor' data-node='" + esc(nid) + "' " +
    "data-goto='" + esc(goto) + "' " +
    "title='" + esc(goto) + " — where this node argues'>" +
    (kind ? "<span class='hy-kbadge " + esc(kind) + "'>" + esc(kind) + "</span>" : "") +
    esc(nid) + "</a>";
}
// E4 #2 — the comment thread (a paragraph's annotate overlay) under engine.mjs: a named return
// door + highlight-bus hygiene at open and close. The overlay stays pinned by the paragraph (its
// spatial home), but it now speaks the engine's focus grammar rather than a bare show/hide.
// P5 — enter the thread's reallocation: capture the scroll once (the first open), recede the
// reader so the thread claims the focus (not floating beside a lit reader), and remember which
// thread is open. Idempotent across a switch (clicking a second paragraph while one is open).
function _enterThreading(ctx) {
  const root = $("#art"); if (!root) return;
  _soloFocus(root, "is-threading");   // one focus at a time — close any other open pane first
  if (!root.classList.contains("is-threading")) THREAD_RESTORE_Y = window.scrollY;
  THREAD_OPEN = ctx || null; if (ctx) THREAD_LAST = ctx;
  root.classList.add("is-threading");
}
function closeAnchor() {
  if (INSPECT_BUS) INSPECT_BUS.clear();
  clearLineMarker(); clearSelAff();
  const a = $("#art-anchor"); if (a) a.classList.remove("on");
  const root = $("#art");
  if (root && root.classList.contains("is-threading")) {   // P5 — leave the reallocation, restore scroll
    root.classList.remove("is-threading");
    window.scrollTo(0, THREAD_RESTORE_Y || 0);
  }
  THREAD_OPEN = null;
}
function _appendAnchorReturn(a) {
  if (!a || a.querySelector(".eng-return")) return;
  const act = a.querySelector(".art-anchor-act") || a;
  act.appendChild(returnDoor("back to the reader", () => closeAnchor()));
}
function beatChipHTML(bt) {
  const goto = "/storyboard?corpus=" + ec(_corpus()) + "#" + ec(bt);
  return "<a href='" + esc(goto) + "' class='hy-chip art-beat art-adoor' data-beat='" + esc(bt) +
    "' data-goto='" + esc(goto) + "' title='" + esc(goto) + " — the spine beat'>" + esc(bt) + "</a>";
}
// every finding / comment the board carries on a section (the thread's live counts + list).
function sectionFindings(sid) {
  if (!BOARD) return [];
  return _allFindings(BOARD).filter((f) => _secLabel(f.section) === sid);
}
function sectionComments(sid) {
  return sectionFindings(sid).filter((f) => { const k = f.kind || ""; return k === "comment" || k === "note"; });
}
// the thread's comments block (item 5): the comments already on this section (from server
// truth) + a VISIBLE comment form. Firing re-reads the board and re-renders here so the new
// row shows immediately, attributed — never an invisible "something".
function renderThreadComments(sid, para, quote) {
  const host = $("#art-anchor [data-role='thread-comments']");
  if (!host) return;
  const cmts = sectionComments(sid);
  let html = "<div class='art-cmt-title'>comments <span class='art-fold-n'>" + cmts.length + "</span></div>";
  if (cmts.length) {
    html += cmts.slice(0, 6).map((c) => "<div class='art-cmt'>" +
      (c.quote || (c.anchor && c.anchor.quote) ? "<div class='art-cmt-q'>“" + esc(cut(c.quote || c.anchor.quote, 120)) + "”</div>" : "") +
      "<div class='art-cmt-t'>" + esc(cut(c.comment || c.kind || "", 160)) + "</div>" +
      "<div class='art-cmt-by'>— " + esc(c.by || "unattributed") + "</div></div>").join("");
  } else {
    html += "<div class='art-dim'>no comments here yet.</div>";
  }
  html += "<div class='art-cmt-form'>" +
    (quote ? "<div class='art-cmt-q'>“" + esc(cut(quote, 140)) + "”</div>" : "") +
    "<textarea data-role='cmt-text' spellcheck='false' placeholder='comment on this " +
      (quote ? "passage" : "paragraph") + "'></textarea>" +
    "<div class='art-cmt-row'><button type='button' class='hy-door is-primary' data-role='cmt-bank'>comment on this " +
      (quote ? "passage" : "paragraph") + "</button><span class='art-cmt-msg' data-role='cmt-msg'></span></div></div>";
  host.innerHTML = html;
  host.dataset.quote = quote || "";
}
async function openAnchorOverlay(sid, opts) {
  const a = $("#art-anchor");
  if (INSPECT_BUS) INSPECT_BUS.clear();   // hygiene: clear at the start of opening a comment thread
  const myGen = ++ANCHOR_GEN;   // guards the async asset-chip append below against a stale reopen
  const sec = (PLAN && PLAN.sections || []).find((s) => s.id === sid);
  const para = (opts && opts.para) || "";
  const quote = (opts && opts.quote) || "";
  const page = (opts && opts.page != null) ? opts.page : null;
  const hitObj = (opts && opts.hit) || LAST_HIT;
  positionAnchor();
  if (!sec) { openUnanchored(opts && opts.y, "no plan section"); return; }
  const nm = await ensureNodemap();
  const nodes = sec.nodes_in_order || [];
  const beats = sec.beats || [];
  // the LINE-PRECISE anchor (his commission): resolve the synctex source line for this spot
  // (the same join follow uses); null → the plain page+quote fallback.
  const src = await resolveSynctexLine(page, opts && opts.px, opts && opts.py);
  // carry a real node for the comment bank (the feedback door requires a non-empty node_id);
  // a section with no mapped node falls back to the section id — never an empty, never a lie.
  ANCHOR_CTX = { section: sid, para, spec_ids:opts?.spec_ids||[], node: nodes[0] || sid, quote, page,
                 source_file: src ? src.file : "", source_line: src ? src.line : null };
  _enterThreading({ section: sid, para });   // the thread reallocates the MARGIN (never crushes the paper)
  drawLineMarker(hitObj);                     // the marker at the line in the paper (the ¶ idiom)
  ESSENCE_NID = null;
  const fresh = nm.present && nm.fresh;
  const nFind = sectionFindings(sid).length, nCmt = sectionComments(sid).length;
  const anchorLine = (page != null ? "<span class='art-k'>page " + page + "</span>" : "") +
    (src ? "<span class='hy-chip is-ok' title='synctex source line'>" + esc((src.file || "").split("/").pop()) + ":" + esc(String(src.line)) + "</span>"
         : "<span class='hy-chip is-warn' title='synctex is not built for this pdf'>source line arrives with a compile</span>");
  // COLLAPSED (item 4 — the disclosure law): a summary line + folds that render ONLY on expand.
  a.innerHTML =
    "<div class='art-anchor-head'><b>" + esc(sid) + "</b> · " + esc(cut(sec.title || "", 26)) +
      (para ? " <span class='hy-chip'>¶ " + esc(para) + "</span>" : "") +
      "<button type='button' class='art-anchor-x' title='close (Esc)'>×</button></div>" +
    (anchorLine ? "<div class='art-anchor-anchor'>" + anchorLine + "</div>" : "") +
    "<div class='art-anchor-sum'>" + beats.length + " beat" + (beats.length === 1 ? "" : "s") + " · " +
      nodes.length + " node" + (nodes.length === 1 ? "" : "s") + " · " + nFind + " finding" + (nFind === 1 ? "" : "s") +
      " · " + nCmt + " comment" + (nCmt === 1 ? "" : "s") +
      " <span class='hy-chip " + (fresh ? "is-ok" : "is-warn") + "' title='node→region map'>" +
      (fresh ? "map fresh" : (nm.present ? "map stale" : "map absent")) + "</span></div>" +
    "<div class='art-fold' data-fold='beats'><div class='art-fold-h'><span class='art-fold-a'>▸</span> beats <span class='art-fold-n'>" + beats.length + "</span></div><div class='art-fold-b'></div></div>" +
    "<div class='art-fold' data-fold='nodes'><div class='art-fold-h'><span class='art-fold-a'>▸</span> nodes <span class='art-fold-n'>" + nodes.length + "</span></div><div class='art-fold-b'></div></div>" +
    "<div class='art-fold' data-fold='assets'><div class='art-fold-h'><span class='art-fold-a'>▸</span> assets <span class='art-fold-n' data-role='assets-n'>…</span></div><div class='art-fold-b'></div></div>" +
    "<div class='art-thread-comments' data-role='thread-comments'></div>" +
    "<div class='art-node-essence' id='art-node-essence'></div>" +
    "<div class='art-anchor-act'></div>";
  a.classList.add("on");
  // lazy fold bodies — nothing beyond the summary renders until he asks (item 4).
  const beatsFold = a.querySelector("[data-fold='beats']");
  if (beatsFold) beatsFold._foldRender = () => beats.length ? beats.map(beatChipHTML).join(" ") : "<span class='art-dim'>none on the spine</span>";
  const nodesFold = a.querySelector("[data-fold='nodes']");
  if (nodesFold) nodesFold._foldRender = () => nodes.length ? nodes.map(nodeChipHTML).join(" ") : "<span class='art-dim'>none mapped here</span>";
  renderThreadComments(sid, para, quote);
  _appendAnchorReturn(a);
  if (quote) {   // arrived from a text selection — put the cursor in the comment box
    const ta = a.querySelector("[data-role='cmt-text']"); if (ta) ta.focus();
  }
  // the assets fold resolves its count + body lazily (declared absence when nothing backs it).
  const assetsPayload = await ensureAssets();
  if (myGen !== ANCHOR_GEN || !a.classList.contains("on")) return;   // a newer click won the race
  const matches = assetsForNodes(assetsPayload, nodes);
  const an = a.querySelector("[data-role='assets-n']"); if (an) an.textContent = String(matches.length);
  const assetsFold = a.querySelector("[data-fold='assets']");
  if (assetsFold) assetsFold._foldRender = () => matches.length
    ? matches.map((m) => assetChipHTML(m, _corpus())).join(" ") : "<span class='art-dim'>none back this section</span>";
}
// a fold opens on demand and renders its body only then (the disclosure law, lazily).
function toggleFold(fold) {
  if (!fold) return;
  const body = fold.querySelector(".art-fold-b");
  const arrow = fold.querySelector(".art-fold-a");
  const open = fold.classList.toggle("open");
  if (open && body && !body.dataset.rendered && typeof fold._foldRender === "function") {
    body.innerHTML = fold._foldRender(); body.dataset.rendered = "1";
  }
  if (arrow) arrow.textContent = open ? "▾" : "▸";
}
function openUnanchored(y, reason) {
  const a = $("#art-anchor");
  if (INSPECT_BUS) INSPECT_BUS.clear();   // hygiene: clear at the start of opening the overlay
  ANCHOR_CTX = null;
  _enterThreading({ section: null, para: null, reason });   // P5 — the unanchored thread reallocates too
  positionAnchor(y);
  a.innerHTML =
    "<div class='art-anchor-head'><b>this span</b> " +
      "<span class='hy-chip is-warn'>¶ unanchored</span>" +
      "<button type='button' class='art-anchor-x' title='close (Esc)'>×</button></div>" +
    "<div class='art-anchor-row art-dim'>unanchored — no nodemap row for this span (" +
      esc(reason) + "). It is inert to node/beat navigation until the instrumented map covers " +
      "it; it never pretends otherwise.</div>" +
    "<div class='art-anchor-act'><button type='button' class='hy-door is-offer art-map-offer' " +
      "title='POST /review/rebuild — rebuilds the instrumented node→region map (a throwaway " +
      "compile, gated on layout equivalence) so this span gets its anchors'>" +
      "rebuild anchor map</button></div>";
  a.classList.add("on");
  _appendAnchorReturn(a);
  retireHint();
}
let ESSENCE_NID = null;   // the node whose essence is showing — one hover, one fetch
async function showEssence(nid) {
  const box = $("#art-node-essence");
  if (!box) return;
  if (ESSENCE_NID === nid) return;   // already peeked this node; don't re-fetch on every mousemove
  ESSENCE_NID = nid;
  box.innerHTML = "<span class='art-dim'>loading " + esc(nid) + "…</span>";
  try {
    const b = await store.fetchJSON("/projection/node", { params: { id: nid } });
    box.innerHTML = "<b>" + esc(nid) + "</b> " + (b.kind ? "<span class='hy-chip'>" + esc(b.kind) + "</span>" : "") +
      "<div class='art-essence'>" + esc(b.essence || b.error || "(no essence)") + "</div>";
  } catch (e) { box.innerHTML = "<span class='art-dim'>essence unavailable for " + esc(nid) + "</span>"; }
}
// item 5b/5c — bank a comment on the paragraph, VISIBLY: the act always reports its result
// where he is looking (the thread refreshes from server truth with the new row, attributed),
// or it reports its refusal in words. Never an invisible "something".
async function bankThreadComment(btn) {
  if (!ANCHOR_CTX) return;
  const host = $("#art-anchor [data-role='thread-comments']");
  const ta = host && host.querySelector("[data-role='cmt-text']");
  const msg = host && host.querySelector("[data-role='cmt-msg']");
  const text = ((ta && ta.value) || "").trim();
  const setMsg = (cls, t) => { if (msg) { msg.className = "art-cmt-msg" + (cls ? " " + cls : ""); msg.textContent = t; } };
  if (!text) { setMsg("is-bad", "the comment needs text"); return; }
  const actor = sessionActor();
  if (!actor) { setMsg("is-bad", "no session actor — the door refuses an unattributed comment (open with ?actor= or a signed-in shell)"); return; }
  const quote = (host && host.dataset.quote) || "";
  setMsg("", "banking…"); if (btn) btn.disabled = true;
  if (LAST_HIT && LAST_HIT.wrap && LAST_HIT.wrap.isConnected) flashRegion(LAST_HIT.wrap, LAST_HIT.hit);
  try {
    await store.fetchJSON("/review/adjudicate", { method: "POST", params: { corpus: _corpus() },
      body: { verb: "comment", by: actor, corpus: _corpus(), section: ANCHOR_CTX.section,
              paragraph: ANCHOR_CTX.para, node: ANCHOR_CTX.node, quote, comment: text,
              page: ANCHOR_CTX.page, source_file: ANCHOR_CTX.source_file, source_line: ANCHOR_CTX.source_line,
              ...(ANCHOR_CTX.spec_ids?.length&&ANCHOR_CTX.source_file&&ANCHOR_CTX.source_line?{spec_ids:ANCHOR_CTX.spec_ids,source_section:ANCHOR_CTX.section,line_start:ANCHOR_CTX.source_line,line_end:ANCHOR_CTX.source_line}:{}) } });
    await loadTriagedTray();                       // refresh the board from server truth
    renderThreadComments(ANCHOR_CTX.section, ANCHOR_CTX.para, "");   // the new row shows, attributed
  } catch (e) { if (btn) btn.disabled = false; setMsg("is-bad", "comment refused — " + cut(cleanErr(e), 100)); }
}

// item 5a — selecting a passage in the PAPER offers a quiet "comment on this passage" affordance
// at the selection; the selected text becomes the anchor.quote. Clicking ¶ still opens the thread.
let SEL_AFF = null;
function clearSelAff() { if (SEL_AFF) { SEL_AFF.remove(); SEL_AFF = null; } }
function onReaderMouseUp() {
  setTimeout(() => {
    const sel = window.getSelection && window.getSelection();
    if (!sel || sel.isCollapsed || !sel.rangeCount) { clearSelAff(); return; }
    const range = sel.getRangeAt(0);
    const anc = range.commonAncestorContainer;
    const el = anc && (anc.nodeType === 3 ? anc.parentElement : anc);
    if (!el || !el.closest || !el.closest(".pgtext")) { clearSelAff(); return; }   // only inside the text layer
    const text = (sel.toString() || "").trim();
    if (text.length < 2) { clearSelAff(); return; }
    const rect = range.getBoundingClientRect();
    clearSelAff();
    SEL_AFF = document.createElement("button");
    SEL_AFF.type = "button"; SEL_AFF.className = "art-sel-aff";
    SEL_AFF.textContent = "comment on this passage";
    SEL_AFF.style.left = Math.round(Math.max(6, rect.left)) + "px";
    SEL_AFF.style.top = Math.round(rect.bottom + 6) + "px";
    SEL_AFF._quote = text;
    SEL_AFF.addEventListener("click", (ev) => { ev.stopPropagation(); openSelComment(SEL_AFF); });
    document.body.appendChild(SEL_AFF);
  }, 10);
}
async function openSelComment(btn) {
  const quote = (btn && btn._quote) || "";
  const sel = window.getSelection && window.getSelection();
  let section = null, para = "", y = 40, wrapHit = null, page = null, px = null, py = null;
  try {
    const range = sel && sel.rangeCount ? sel.getRangeAt(0) : null;
    const rect = range && range.getBoundingClientRect();
    const startEl = range && (range.startContainer.nodeType === 3 ? range.startContainer.parentElement : range.startContainer);
    const wrap = startEl && startEl.closest ? startEl.closest(".art-page") : null;
    if (wrap && rect) {
      const pr = wrap.getBoundingClientRect();
      const pw = parseFloat(wrap.dataset.pw) || 612, ph = parseFloat(wrap.dataset.ph) || 792;
      page = parseInt(wrap.dataset.page, 10);
      px = (rect.left + rect.width / 2 - pr.left) * (pw / pr.width);
      py = ((rect.top + rect.bottom) / 2 - pr.top) * (ph / pr.height);   // the selection's centre resolves more reliably
      await ensureNodemap(); await ensurePlan();
      const hit = anchorAtPoint(page, py, true);
      if (hit) { const logical=paragraphSourceIdentity(hit.region);para=logical.specId;section=logical.sourceSection;wrapHit = { wrap, hit }; }
      const rc = $(".art-reader-col"); if (rc) y = rect.top - rc.getBoundingClientRect().top;
    }
  } catch (e) { /* fall through to the plain message below */ }
  clearSelAff();
  try { if (window.getSelection) window.getSelection().removeAllRanges(); } catch (e) { /* ignore */ }
  if (section) { LAST_HIT = wrapHit; retireHint(); openAnchorOverlay(section, { para, spec_ids:paragraphSourceIdentity(wrapHit?.hit?.region||{}).specIds, y, page, px, py, quote, hit: wrapHit }); }
  else {
    // 5c — never an invisible act: if the selection cannot be anchored, say so where he looked.
    const note = document.createElement("div");
    note.className = "art-sel-aff is-note"; note.textContent = "couldn't anchor that selection — click the ¶ band to comment on the paragraph";
    note.style.left = "12px"; note.style.top = "12px";
    document.body.appendChild(note);
    setTimeout(() => note.remove(), 3200);
  }
}

// the unanchored overlay's ONE live door: POST /review/rebuild rebuilds the instrumented
// node→region map (a throwaway compile, gated on layout equivalence). P3 — it FIRES the
// route and reports the real result; it is never a text-only gesture. On success the cached
// nodemap is dropped and re-warmed so a reopened span shows its freshly-mapped anchors.
async function rebuildNodemap(btn) {
  if (btn.dataset.firing) return;
  btn.dataset.firing = "1";
  btn.textContent = "rebuilding the anchor map…";
  try {
    const res = await store.fetchJSON("/review/rebuild",
      { method: "POST", body: { corpus: _corpus() } });   // store injects ?corpus= itself
    delete NODEMAP[_corpus()];
    const pp = res && res.coverage && res.coverage.paragraphs;
    const cov = (pp && typeof pp.pct === "number")
      ? " · " + pp.mapped + "/" + pp.total + " paragraphs mapped (" + pp.pct + "%)" : "";
    btn.textContent = "anchor map rebuilt ✓" + cov + " — reopen this span to see its anchors";
    ensureNodemap().catch(() => {});
  } catch (e) {
    delete btn.dataset.firing;
    btn.textContent = "rebuild refused — " + cut((e && e.message) || String(e), 90);
  }
}

// ── The version rail, STANDING (D7/D8) ──────────────────────────────────────────
function roundLayoutTag(r) {
  const paths = r.paths || [];
  if (paths.some((p) => /(^|\/)judge_rounds\//.test(p))) return "judge";
  if (paths.some((p) => /(^|\/)rounds\/(harnessed\/|incumbent_r|lock_r)/.test(p))) return "harnessed";
  return "misc";
}
function decorateVersionRows(vers) {
  if (!vers || !Array.isArray(vers.rows)) return vers;
  const seen = new Map();
  for (const r of vers.rows) {
    const base = r.kind === "round" ? "round:" + roundLayoutTag(r) + ":" + r.id : String(r.id);
    const n = seen.get(base) || 0;
    seen.set(base, n + 1);
    r._rid = n ? base + "~" + n : base;
  }
  return vers;
}
function railRowHTML(r) {
  const paths = r.paths || [];
  const pdf = paths.find((p) => /\.pdf$/i.test(p));
  const openable = !!pdf;
  const isSave = r.kind === "editor-save";
  const sel = RAILSEL.includes(r._rid) ? " is-sel" : "";
  const ts = r.ts ? esc(String(r.ts).replace("T", " ").slice(0, 16)) : "—";
  const action = isSave && typeof r.source_file === "string" && r.source_file
    ? "<button type='button' class='hy-rail-open art-restore' data-restore='" + esc(r.version_id || r.id) +
      "' data-source-file='" + esc(r.source_file) + "'>restore</button>" +
      infoTag("restore writes these banked bytes back to the live file THROUGH the save path — a " +
              "restore is a NEW save (a new rail row), never a rewind. POST /projection/restore.")
    : isSave ? "<span class='hy-rail-detail' title='This legacy snapshot has no exact source target; inspect its preserved bytes.'>restore target unproved</span>"
    : openable
      ? "<a href='#' class='hy-rail-open art-open' data-open='" + esc(r._rid) + "'>open ↻</a>"
      : "<span class='hy-rail-detail' title='no built artefact for this row'>rebuild banked</span>";
  return "<div class='hy-rail-row kind-" + esc(r.kind) + sel + "' data-id='" + esc(r._rid) + "'>" +
    "<div class='hy-rail-line'>" +
      "<span class='hy-rail-kind'>" + esc(r.kind) + "</span>" +
      "<span class='hy-rail-label'>" + esc(r.label || r.id) + "</span>" + action +
    "</div>" +
    "<div class='hy-rail-meta'>" + ts + (r.state ? " · <span class='hy-rail-state'>" + esc(r.state) + "</span>" : "") + "</div>" +
    (paths.length ? "<div class='hy-rail-paths'>" + paths.map((p) => "<code>" + esc(p) + "</code>").join(" · ") + "</div>" : "") +
    "<label class='art-diffpick'><input type='checkbox' class='art-diffbox' data-id='" + esc(r._rid) + "'>diff</label>" +
  "</div>";
}
// the collapsed rail head: current version + revision count + the open/close toggle (D7).
function renderRailStrip() {
  const head = $("#art-rail-strip");
  if (!head || !VERS) return;
  const rev = currentRevision();
  const total = (VERS.counts && VERS.counts.total) || 0;
  const open = !!($("#art-main") && $("#art-main").classList.contains("rail-open"));
  void rev;
  head.innerHTML =
    "<span class='art-mg-h'>history — the versions</span>" +
    "<span class='hy-chip'>" + total + " revision" + (total === 1 ? "" : "s") + "</span>" +
    "<button type='button' class='hy-rail-toggle' id='art-rail-toggle' style='margin-left:auto' " +
      "title='open the version rail (Esc folds it)'>" + (open ? "fold" : "open") + "</button>";
}
function revKey(rev) { return (rev.id || "") + " " + (rev.pdf || ""); }
async function syncToRevision() {
  if (DIFF_OPEN && DIFF_PROJECT !== _corpus()) closeDiff({restoreFocus:false, restoreScroll:false});
  renderRailStrip();
  const rev = currentRevision();
  const key = revKey(rev);
  if (key === lastRevKey) return;
  lastRevKey = key;
  await loadReader();
}
function editorDroppedBannerHTML(vers) {
  const dropped = ((vers && vers.sources && vers.sources.editor_saves) || {}).dropped || 0;
  if (!dropped) return "";
  return "<div class='hy-rail-trunc'>" + dropped + " older save" + (dropped === 1 ? "" : "s") +
    " dropped by the 32-bound" +
    infoTag("the editor-save store keeps the newest 32 banked saves; the rest are pruned and " +
            "recorded LOUDLY in the store index.json dropped[] list — never a silent drop.") + "</div>";
}
function renderRailFull() {
  const body = $("#art-rail-body");
  if (!body) return;
  if (!VERS) { body.innerHTML = "<div class='hy-rail-empty'>version history unavailable.</div>"; return; }
  const rows = VERS.rows || [];
  if (VERS.never_run || !rows.length) {
    body.innerHTML = "<div class='hy-rail-empty'>" +
      (VERS.never_run ? "never through the machine — no snapshots, rounds, or releases yet."
                      : "no version history on disk yet.") + "</div>"; return;
  }
  const groups = [["editor-save", "editor saves"], ["snapshot", "snapshots"],
                  ["round", "rounds"], ["release", "releases"]];
  let html = "";
  for (const [kind, title] of groups) {
    const grp = rows.filter((r) => r.kind === kind);
    const banner = kind === "editor-save" ? editorDroppedBannerHTML(VERS) : "";
    if (!grp.length && !banner) continue;
    html += "<div class='hy-rail-group'><div class='hy-rail-gtitle'>" + esc(title) +
      " <span class='hy-rail-gn'>" + grp.length + "</span></div>" + grp.map(railRowHTML).join("") +
      banner + "</div>";
  }
  body.innerHTML = html;
  if (VERS.truncated)
    body.innerHTML += "<div class='hy-rail-trunc'>newest shown — " + (VERS.omitted || 0) + " older omitted (16KB)</div>";
  updateDiffBar();
}
function updateDiffBar() {
  const bar = $("#art-diffbar");
  if (!bar) return;
  bar.innerHTML = RAILSEL.length === 2
    ? "diff <code>" + esc(RAILSEL[0]) + "</code> ↔ <code>" + esc(RAILSEL[1]) +
      "</code> <button type='button' class='hy-door is-primary' id='art-do-diff'>diff ↔</button>"
    : "<span class='art-dim'>tick two rows to diff (" + RAILSEL.length + "/2)</span>";
}
async function extractPdfText(pdfRel, context = CTX) {
  const lib = await ensurePdfjs();
  // Historical exact-file read: corpus would assert this archived PDF is current output.
  const doc = await lib.getDocument({ url: context.pdf_endpoint + "?file=" + ec(pdfRel) }).promise;
  const out = [];
  for (let i = 1; i <= doc.numPages; i++) {
    const tc = await (await doc.getPage(i)).getTextContent();
    let line = [];
    for (const it of tc.items) { line.push(it.str); if (it.hasEOL) { out.push(line.join("")); line = []; } }
    if (line.length) out.push(line.join(""));
  }
  return out.map((l) => l.trim()).filter((l) => l.length);
}
function lineDiff(a, b) {
  const n = a.length, m = b.length;
  const dp = Array.from({ length: n + 1 }, () => new Int32Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--)
    dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const rows = []; let i = 0, j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) { rows.push(["=", a[i]]); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) { rows.push(["-", a[i++]]); }
    else { rows.push(["+", b[j++]]); }
  }
  while (i < n) rows.push(["-", a[i++]]);
  while (j < m) rows.push(["+", b[j++]]);
  return rows;
}
// P5 — close the version diff: restore the exact scroll, leave the diffing geometry, keep the
// pair in RAILSEL (so reopening returns to the same diff — the restore memory). Both the return
// door and the header close button route here.
function closeDiff({restoreFocus = true, restoreScroll = true} = {}) {
  const pane = $("#art-diffpane"), root = $("#art"), opener = DIFF_OPENER;
  const wasOpen = !!DIFF_OPEN || !!root?.classList.contains("is-diffing");
  DIFF_GENERATION++; // the closed observation can never paint a late success or error
  if (INSPECT_BUS) INSPECT_BUS.clear();
  if (pane) pane.classList.remove("on");
  if (root) root.classList.remove("is-diffing");
  DIFF_LAST = DIFF_OPEN; DIFF_OPEN = null; DIFF_PROJECT = null; DIFF_OPENER = null;
  if (wasOpen && restoreScroll) window.scrollTo(0, DIFF_RESTORE_Y || 0);
  if (wasOpen && restoreFocus) {
    const target = opener?.isConnected ? opener : $("#art-do-diff");
    target?.focus({preventScroll:true});
  }
}
async function runDiff(opener = document.activeElement) {
  const pane = $("#art-diffpane"), root = $("#art");
  if (!pane || !root) return;
  if (INSPECT_BUS) INSPECT_BUS.clear();
  _soloFocus(root, "is-diffing");
  const context = CTX, corpus = _corpus(), pair = RAILSEL.slice(0, 2);
  const ticket = ++DIFF_GENERATION;
  if (!root.classList.contains("is-diffing")) {
    DIFF_RESTORE_Y = window.scrollY;
    DIFF_OPENER = opener;
  }
  DIFF_PROJECT = corpus; DIFF_OPEN = pair.join(" ↔ ");
  root.classList.add("is-diffing"); pane.classList.add("on");
  pane.setAttribute("role", "region"); pane.setAttribute("aria-label", "Version comparison");
  pane.setAttribute("tabindex", "-1");
  const current = () => ticket === DIFF_GENERATION && pane.isConnected &&
    root.classList.contains("is-diffing") && CTX === context && _corpus() === corpus &&
    RAILSEL.length === pair.length && RAILSEL.every((id, i) => id === pair[i]);
  const show = (title, content, opening = false) => {
    if (!current()) return;
    const heldFocus = pane === document.activeElement || pane.contains(document.activeElement);
    pane.innerHTML = "<div class='art-diffhead'><b>" + esc(title) + "</b> · " +
      pair.map(esc).join(" ↔ ") + " <button type='button' class='hy-door' id='art-diff-x'>Close comparison</button></div>" + content;
    const head = pane.querySelector(".art-diffhead");
    if (head) head.appendChild(returnDoor("back to the version rail", () => closeDiff()));
    if (opening || heldFocus) pane.focus({preventScroll:true});
  };
  show("Version comparison", "<div class='art-msg'>extracting text from both revisions…</div>", true);
  const rowFor = id => (VERS?.rows || []).find(row => row._rid === id);
  const pathOf = (row, extension) => row?.paths?.find(path => extension.test(path)) || null;
  const A = rowFor(pair[0]), B = rowFor(pair[1]);
  // Capture the selected historical coordinates once. A later selection cannot redirect B.
  const texA = pathOf(A, /\.tex$/i), texB = pathOf(B, /\.tex$/i);
  const pdfA = pathOf(A, /\.pdf$/i), pdfB = pathOf(B, /\.pdf$/i);
  let mode, la, lb;const sourceBasis=[];
  try {
    if (pair.length !== 2 || pair[0] === pair[1] || !A || !B) {
      show("Comparison unavailable", "<div class='art-msg'>Choose two available revisions in this project's version rail.</div>"); return;
    }
    if (texA && texB && A.source_read && B.source_read) {
      mode = "tex";
      const historicalA=await readHistoricalSource(A.source_read,{project:corpus,file:texA,transport:(path,options)=>store.fetchJSON(path,options)});sourceBasis.push(historicalA.archive_identity);la=historicalA.content;
      if (!current()) return;
      const historicalB=await readHistoricalSource(B.source_read,{project:corpus,file:texB,transport:(path,options)=>store.fetchJSON(path,options)});sourceBasis.push(historicalB.archive_identity);lb=historicalB.content;
      if (!current()) return;
      la = String(la).split("\n"); lb = String(lb).split("\n");
    } else if (pdfA && pdfB) {
      mode = "text-layer";
      la = await extractPdfText(pdfA, context);
      if (!current()) return;
      lb = await extractPdfText(pdfB, context);
      if (!current()) return;
    } else {
      show("Comparison unavailable", "<div class='art-msg'>A selected revision has no PDF/TeX to diff.</div>"); return;
    }
  } catch (error) {
    show("Comparison failed", "<div class='art-msg'>diff failed: " + esc(error?.message || error) + "</div>"); return;
  }
  const rows = lineDiff(la, lb);
  const body = rows.map(([op, line]) =>
    "<div class='art-dline op" + (op === "=" ? "eq" : op === "-" ? "del" : "add") + "'>" +
    "<span class='art-dop'>" + (op === "=" ? " " : op) + "</span>" + esc(cut(line, 200)) + "</div>").join("");
  const changed = rows.filter(row => row[0] !== "=").length;
  show(mode + " diff · " + changed + " changed line(s)",
    (sourceBasis.some(value=>value.verification==='OBSERVED_ONLY')?"<p class='art-msg'>Historical snapshot bytes observed now; an independent archived file hash is unavailable.</p>":sourceBasis.length?"<p class='art-msg'>Saved version identities verified.</p>":"")+"<div class='art-difflines' tabindex='0' aria-label='Compared version text'>" + body + "</div>");
}

// ── The findings tray, TRIAGED (D9/D10/D11 · burn-down #3) ───────────────────────
// One plain collapsed line from the REAL store counts; on triage, groups by kind × section,
// severity-ranked, plain anchors as door-chips ("unanchored" in words, never "· ?"), real +N
// doors into /desk, the dismissed fold with overrule. ✎ rule (hyRule) on every active row.
let BOARD = null, DISMISS = null;
const SEV = { hard: 2, soft: 1, deferred: 0 };
const SEVLABEL = { hard: ["high", "is-bad"], soft: ["med", "is-warn"], deferred: ["low", "is-never"] };
function _allFindings(board) {
  const out = [];
  for (const g of board.by_node || []) for (const f of g.findings || []) out.push(f);
  for (const f of board.unanchored || []) out.push(f);
  return out;
}
function _kindFamily(k) { return String(k || "note").split(/[-_]/)[0] || "note"; }
function _secLabel(sec) { return (!sec || sec === "?") ? "" : String(sec); }
function _groupFindings(board) {
  const map = new Map();
  for (const f of _allFindings(board)) {
    const fam = _kindFamily(f.kind);
    const secRaw = _secLabel(f.section);
    const key = fam + "×" + (secRaw || "unanchored");
    let g = map.get(key);
    if (!g) { g = { key, fam, section: secRaw, count: 0, sev: 0, items: [] }; map.set(key, g); }
    g.count++;
    g.sev = Math.max(g.sev, SEV[f.cls] || 0);
    g.items.push(f);
  }
  const groups = [...map.values()];
  for (const g of groups) g.items.sort((a, b) => (SEV[b.cls] || 0) - (SEV[a.cls] || 0));
  groups.sort((a, b) => (b.sev - a.sev) || (b.count - a.count));
  return groups;
}
// E4 #3 — composed consumption (composed.project_altitude semantics, client-side): a finding
// carrying an E1 composed block shows its GLANCE at rest; one without shows its stated absence.
// No synthesis from terse fields — an absent block drops to the audit floor of its raw ids.
const COMPOSED_ABSENCE = "no composed account — minted before the composition layer, or by a writer that predates it";
function composedGlance(rec) {
  const b = rec && rec.composed;
  if (!b || typeof b !== "object") return { absent: true, reason: COMPOSED_ABSENCE };
  return { absent: false, glance: b.glance || "", next: b.next || null, block: b };
}
function _findingByFid(fid) {
  if (!BOARD || !fid) return null;
  return _allFindings(BOARD).find((f, i) => (f.id || (f.kind + "-" + i)) === fid) || null;
}

function frowHTML(f, i, corpus) {
  const [lbl, cls] = SEVLABEL[f.cls] || SEVLABEL.deferred;
  const pa = composedGlance(f);
  // the composed conclusion at rest when the block is present; the plain comment otherwise
  // (never a glance synthesised from the terse comment — that is the read-time reconstruction
  // the composition layer exists to avoid).
  const title = pa.absent ? (f.comment || f.kind || "finding") : (pa.glance || f.comment || f.kind || "finding");
  const badge = pa.absent
    ? "<span class='art-absent' title='" + esc(pa.reason) + "'>no composed account</span>"
    : "<span class='art-composed' title='composed glance — open for the working account'>glance</span>";
  const sec = _secLabel(f.section);
  const node = (f.node && f.node !== "?") ? f.node : "";
  let anchor;
  if (node)
    anchor = "<a href='#' class='hy-door art-adoor' data-goto='/conceptric?corpus=" + ec(corpus) +
      "&node=" + ec(node) + "' title='/conceptric?corpus=" + ec(corpus) + "&node=" + esc(node) +
      "'>· " + esc(cut(node, 22)) + "</a>";
  else if (sec)
    anchor = "<a href='#' class='hy-door art-adoor' data-goto='/storyboard?corpus=" + ec(corpus) +
      "#" + ec(sec) + "' title='/storyboard?corpus=" + ec(corpus) + "#" + esc(sec) +
      "'>· §" + esc(cut(sec, 18)) + "</a>";
  else
    anchor = "<span class='art-unanch' title='no nodemap row for this finding&#39;s span (F4) — " +
      "stated in words, never · ?'>unanchored</span>";
  return "<div class='dk-card art-frow' data-fid='" + esc(f.id || (f.kind + "-" + i)) + "' " +
    "data-node='" + esc(node) + "' data-kind='" + esc(f.kind || "note") + "' data-section='" + esc(sec) + "'>" +
    "<div class='dk-card-head'>" +
      "<span class='hy-chip " + cls + "'>" + lbl + "</span>" +
      "<span class='dk-title'>" + esc(cut(title, 88)) + "</span>" + badge + anchor +
    "</div></div>";
}
// #7 — the tray filter: a search box over the whole board so any finding is reachable
// without hunting past a blind "+ N more groups" wall. Matches kind, section, node, comment,
// id, or composed glance; an active filter drops the 4-group cap and shows every match.
let TRAY_FILTER = "";
function _matchFinding(f, q) {
  const hay = [f.kind, f.section, f.node, f.comment, f.id,
    (f.composed && f.composed.glance) || ""].join(" ").toLowerCase();
  return hay.indexOf(q) !== -1;
}
function renderTriagedTray() {
  const sec = $("#art-tray-sec"), sum = $("#art-tray-sum"), body = $("#art-tray-body");
  if (!sec || !BOARD) return;
  const total = (BOARD.counts && BOARD.counts.total) || 0;
  const dismissed = (DISMISS && DISMISS.counts && DISMISS.counts.dismissals) || 0;
  const groups = _groupFindings(BOARD);
  // the one plain collapsed line (D9): total · groups · dismissed(folded), from the stores.
  sum.textContent = total + " total · " + groups.length + " group" + (groups.length === 1 ? "" : "s") +
    " · " + dismissed + " dismissed (folded)";
  body.innerHTML =
    "<div class='art-tray-filter'><span class='art-k'>find</span>" +
    "<input type='text' id='art-tray-find' spellcheck='false' " +
    "placeholder='filter by kind, section, node, or text' value='" + esc(TRAY_FILTER) + "'></div>" +
    "<div id='art-tray-groups'></div>";
  const inp = $("#art-tray-find");
  if (inp && !inp.dataset.wired) { inp.dataset.wired = "1";
    inp.addEventListener("input", () => { TRAY_FILTER = inp.value || ""; renderTrayGroups(); }); }
  renderTrayGroups();
}
function renderTrayGroups() {
  const host = $("#art-tray-groups");
  if (!host || !BOARD) return;
  const corpus = _corpus();
  const dismissed = (DISMISS && DISMISS.counts && DISMISS.counts.dismissals) || 0;
  const groups = _groupFindings(BOARD);
  const q = TRAY_FILTER.trim().toLowerCase();
  const filtering = q.length > 0;
  const SHOWN_GROUPS = 4, ROWS = 3;
  let html = "";
  if (filtering) {
    const matched = [];
    for (const g of groups) {
      const items = g.items.filter((f) => _matchFinding(f, q));
      if (items.length) matched.push({ g, items });
    }
    if (!matched.length)
      html += "<div class='art-dim'>no finding matches “" + esc(cut(TRAY_FILTER, 40)) + "”.</div>";
    for (const mg of matched) {
      const g = mg.g;
      const sevName = ["deferred", "soft", "hard"][g.sev] || "deferred";
      const [lbl] = SEVLABEL[sevName] || SEVLABEL.deferred;
      const secName = g.section ? "§" + cut(g.section, 20) : "unanchored";
      html += "<div class='art-grp'><div class='art-grp-h'>" +
        "<span class='dk-chip'>" + esc(g.fam) + " × " + esc(secName) + "<b>" + mg.items.length + "/" + g.count + "</b></span>" +
        "<span class='art-grp-sev sev-" + sevName + "'>top " + lbl + "</span></div>";
      for (let i = 0; i < mg.items.length; i++) html += frowHTML(mg.items[i], i, corpus);
      html += "</div>";
    }
  } else {
    for (const g of groups.slice(0, SHOWN_GROUPS)) {
      const sevName = ["deferred", "soft", "hard"][g.sev] || "deferred";
      const [lbl] = SEVLABEL[sevName] || SEVLABEL.deferred;
      const secName = g.section ? "§" + cut(g.section, 20) : "unanchored";
      html += "<div class='art-grp'><div class='art-grp-h'>" +
        "<span class='dk-chip'>" + esc(g.fam) + " × " + esc(secName) + "<b>" + g.count + "</b></span>" +
        "<span class='art-grp-sev sev-" + sevName + "'>top " + lbl + "</span></div>";
      for (let i = 0; i < Math.min(ROWS, g.items.length); i++) html += frowHTML(g.items[i], i, corpus);
      if (g.count > ROWS)
        html += "<a href='#' class='hy-door art-adoor' data-goto='/desk?corpus=" + ec(corpus) +
          "&group=" + ec(g.key) + "' title='/desk?corpus=" + ec(corpus) + "&group=" + esc(g.key) +
          " — the full group, ranked'>+ " + (g.count - ROWS) + " more</a>";
      html += "</div>";
    }
    if (groups.length > SHOWN_GROUPS)
      html += "<div class='art-dim'>" + (groups.length - SHOWN_GROUPS) + " more group" +
        (groups.length - SHOWN_GROUPS === 1 ? "" : "s") + " — type above to find one, or " +
        "<a href='#' class='hy-door art-adoor' data-goto='/desk?corpus=" + ec(corpus) +
        "' title='every group, ranked'>open the desk</a></div>";
  }
  // the dismissed fold (D10): folded so the live queue reads clean; overrule reborns it live.
  const drows = (DISMISS && DISMISS.rows) || [];
  if (dismissed || drows.length) {
    const shown = [];
    for (const r of drows) for (const n of r.nodes || [])
      if (n.suppression_id) shown.push({ kind: r.kind, node: n.node, section: n.section, sid: n.suppression_id });
    html += "<div class='art-dism' id='art-dism'>" +
      "<div class='art-dism-h' id='art-dism-h' title='the fingerprinted suppressions — folded so the live queue reads clean'>" +
        "▸ dismissed · " + dismissed + " (folded)</div><div class='art-dism-body'>" +
      "<div class='art-dism-cav'>showing " + Math.min(shown.length, 6) + " of " + dismissed +
        " — each is a fingerprinted suppression; overrule reborns it live.</div>";
    for (const d of shown.slice(0, 6)) {
      const anc = (d.section && d.section !== "?")
        ? "<span class='hy-door art-adoor' data-goto='/storyboard?corpus=" + ec(corpus) + "#" + ec(d.section) +
          "' title='/storyboard#" + esc(d.section) + "'>· §" + esc(cut(d.section, 16)) + "</span>"
        : "<span class='art-unanch'>unanchored</span>";
      html += "<div class='dk-card art-frow' data-node='" + esc(d.node || "") + "' data-kind='" +
        esc(d.kind || "") + "' data-sid='" + esc(d.sid) + "'><div class='dk-card-head'>" +
        "<span class='hy-chip is-scaffold'>dismissed</span>" +
        "<span class='dk-title'>" + esc(cut((d.kind || "") + " · " + (d.node || d.section || ""), 60)) + "</span>" +
        anc + "<button type='button' class='hy-door art-overrule' title='POST /review/adjudicate " +
        "{verb:revoke} — reborns this finding live (arm-to-fire)'>overrule ↺</button>" +
        "</div></div>";
    }
    html += "</div></div>";
  }
  host.innerHTML = html || "<div class='art-dim'>no active findings — the queue is clean.</div>";
  attachTrayRules();
}
// D16 — the ✎ rule-in-place mouth on every ACTIVE finding row (shell.js owns capture + POST).
function attachTrayRules() {
  const R = window.HymnShell && window.HymnShell.hyRule;
  if (!R) return;
  $$("#art-tray-body .art-frow[data-fid]").forEach((el) => R.attach(el, {
    surface: "artefact", node: el.dataset.node || ("finding:" + el.dataset.kind),
    selection: el.dataset.section ? "§" + el.dataset.section : el.dataset.kind,
    purpose: "the findings tray — rule on this finding in place",
  }));
}
async function loadTriagedTray() {
  const corpus = _corpus();
  try { BOARD = await store.fetchJSON("/review/findings"); }
  catch (e) { BOARD = { counts: { total: 0 }, by_node: [], unanchored: [] }; }
  try { DISMISS = await store.fetchJSON("/review/dismissals"); }
  catch (e) { DISMISS = { counts: { dismissals: 0 }, rows: [] }; }
  renderTriagedTray();
  refreshMarks();   // the board changed → recompute the marks, gutter, minimap, and shelf
}
// fire ONE overrule (revoke) through the EXISTING /review/adjudicate door, arm-to-fire.
let OVERRULE_ARMED = null;
async function overrule(btn) {
  const row = btn.closest(".art-frow");
  const key = row.dataset.sid;
  if (OVERRULE_ARMED !== key) {
    $$(".art-overrule").forEach((b) => { if (b !== btn) b.textContent = "overrule ↺"; });
    OVERRULE_ARMED = key;
    btn.textContent = "this reborns it live — click again";
    return;
  }
  OVERRULE_ARMED = null;
  const actor = sessionActor();
  if (!actor) { btn.textContent = "no session actor — the door refuses it"; return; }
  btn.textContent = "reborning…";
  try {
    await store.fetchJSON("/review/adjudicate", { method: "POST", params: { corpus: _corpus() },
      body: { verb: "revoke", by: actor, corpus: _corpus(), supersedes: key,
              node: row.dataset.node, kind: row.dataset.kind, section: row.dataset.section } });
    await loadTriagedTray();
  } catch (e) { btn.textContent = "overrule failed — " + cut(cleanErr(e), 90); }
}

// ── the four verdict doors (confirm / dismiss / defer / route-conceptric) ────────
// Each door names its consequence, then fires on the second act (arm-then-fire) through the
// EXISTING /review/adjudicate door — the same idiom overrule/armRestore already prove. Defer
// takes a date; route names the standing order. Every write carries the session actor; the
// tray refreshes from server truth after any verdict.
function cleanErr(e) {
  const m = (e && e.message) || String(e);
  const arrow = m.match(/→\s*\d+:\s*(.*)$/);       // strip the "fetchJSON VERB url → NNN:" prefix
  return arrow ? arrow[1] : m;
}
function verdictPayload(verb, f, extra) {
  const node = (f.node && f.node !== "?") ? f.node : "";
  const sec = _secLabel(f.section);
  const base = { verb, by: sessionActor(), corpus: _corpus(), node, kind: f.kind || "", section: sec };
  if (verb === "confirm" || verb === "defer") base.finding_id = f.id;
  if (verb === "route-conceptric") base.finding_id = f.id;
  if (verb === "dismiss") base.reason = (extra && extra.reason) || "dismissed from the finding inspection";
  if (verb === "defer") base.note = (extra && extra.note) || "";
  if (verb === "route-conceptric") { base.intent = (extra && extra.intent) || "other"; base.note = (extra && extra.note) || ("route: " + base.intent); }
  return base;
}
async function fireVerdict(verb, f, extra, msgEl) {
  const actor = sessionActor();
  if (!actor) {
    if (msgEl) { msgEl.className = "art-verb-msg is-bad";
      msgEl.textContent = "no session actor — the door refuses an unattributed verdict (open with ?actor= or a signed-in shell)"; }
    return false;
  }
  if (msgEl) { msgEl.className = "art-verb-msg"; msgEl.textContent = verb + "…"; }
  try {
    const res = await store.fetchJSON("/review/adjudicate",
      { method: "POST", params: { corpus: _corpus() }, body: verdictPayload(verb, f, extra) });
    if (msgEl) { msgEl.className = "art-verb-msg is-ok";
      msgEl.textContent = verb + (res && res.idempotent ? " (already ruled)" : " ✓") + " · by " + actor; }
    await loadTriagedTray();                        // the tray refreshes from server truth
    return true;
  } catch (e) {
    if (msgEl) { msgEl.className = "art-verb-msg is-bad"; msgEl.textContent = verb + " refused — " + cut(cleanErr(e), 120); }
    return false;
  }
}
// the standing-order intents that FIT a finding kind (item 6b): a routing order rewrites the
// CONCEPT MAP, so it fits kinds whose defect is structural (a missing node / edge / content, a
// wrong essence) — never a prose slip. A kind with no fitting order surfaces the plain
// mismatch rather than offering ill-fitting options.
const ROUTE_INTENTS = {
  "missing-node": [["content-missing", "the node's content is absent from the map"]],
  "missing-content": [["content-missing", "the content is absent from the map"]],
  "missing-derivation": [["edge-missing", "the derivation edge is missing"], ["content-missing", "the derivation content is absent"]],
  "missing-simulation": [["edge-missing", "the simulation edge is missing"]],
  "unsupported-claim": [["edge-missing", "an evidence edge is missing"], ["content-missing", "the support is absent"]],
  "naked-claim": [["edge-missing", "an evidence edge is missing"]],
  "refute": [["essence-wrong", "the node's essence is wrong"]],
};
const PROSE_KINDS = new Set(["notation-inconsistent", "legacy-notation", "legacy-term",
  "matter-scaffold", "meta-leak", "figure-standard", "note", "eq-duplicate", "eq-unused"]);
const GENERIC_INTENTS = [["essence-wrong", "the node's essence is wrong"], ["edge-missing", "a missing edge"],
  ["content-missing", "absent content"], ["grade-wrong", "the grade is wrong"], ["other", "other"]];
function routePlanForKind(kind) {
  const k = String(kind || "");
  if (ROUTE_INTENTS[k]) return { fitted: ROUTE_INTENTS[k], prose: false, generic: false };
  if (PROSE_KINDS.has(k)) return { fitted: null, prose: true, generic: false };
  return { fitted: GENERIC_INTENTS, prose: false, generic: true };
}
// each verb's consequence in plain outcome words, from what the adjudicate handler actually
// does (confirm→make_confirmation, dismiss→make_suppression, defer→make_defer, route→
// make_conceptric_intent) — never invented.
const VERB_WHY = {
  confirm: "it stands, and rides the next regeneration round as work.",
  dismiss: "folded as not-a-problem — a fingerprinted suppression, recoverable by overrule.",
  defer: "parked until a date, out of the live rail until then.",
  "route-conceptric": "banks a standing order on the concept so the substrate fixes it, not the prose.",
};
let VERDICT_ARMED = null;
function renderVerdictDoors(f, container, msgEl) {
  const node = (f.node && f.node !== "?") ? f.node : "";
  // each verb wears its consequence IN PLACE (item 6a), in plain outcome words. Arm-then-fire.
  const mkVerb = (verb, label) => {
    const wrap = document.createElement("div"); wrap.className = "art-verb";
    const b = document.createElement("button");
    b.type = "button"; b.className = "hy-door"; b.dataset.verb = verb; b.textContent = label;
    const why = document.createElement("span"); why.className = "art-verb-why"; why.textContent = VERB_WHY[verb] || "";
    wrap.appendChild(b); wrap.appendChild(why); container.appendChild(wrap);
    return b;
  };
  const confirm = mkVerb("confirm", "confirm");
  const dismiss = mkVerb("dismiss", "dismiss");
  const defer = mkVerb("defer", "defer");
  const route = mkVerb("route-conceptric", "route to conceptric →");
  const form = document.createElement("div");
  form.className = "art-verb-form"; form.style.display = "none"; form.dataset.mode = "";
  container.insertAdjacentElement("afterend", form);
  const clearForm = () => { form.style.display = "none"; form.dataset.mode = ""; form.innerHTML = "";
    defer.textContent = "defer"; route.textContent = "route to conceptric →"; };
  const disarm = () => { VERDICT_ARMED = null; confirm.textContent = "confirm"; dismiss.textContent = "dismiss"; };
  confirm.addEventListener("click", async () => {
    if (VERDICT_ARMED !== "confirm") { disarm(); clearForm(); VERDICT_ARMED = "confirm";
      confirm.textContent = "confirm — click again to fire"; return; }
    disarm();
    if (await fireVerdict("confirm", f, null, msgEl)) closeInspection();
  });
  dismiss.addEventListener("click", async () => {
    if (VERDICT_ARMED !== "dismiss") { disarm(); clearForm(); VERDICT_ARMED = "dismiss";
      dismiss.textContent = node ? "dismiss — click again to fold it" : "no node to fingerprint — click again to try"; return; }
    disarm();
    if (await fireVerdict("dismiss", f, null, msgEl)) closeInspection();
  });
  defer.addEventListener("click", () => {
    if (form.dataset.mode === "defer") { clearForm(); return; }
    disarm(); clearForm(); form.dataset.mode = "defer"; form.style.display = "flex";
    const lab = document.createElement("span"); lab.className = "art-k"; lab.textContent = "withhold until";
    const date = document.createElement("input"); date.type = "date";
    const go = document.createElement("button"); go.type = "button"; go.className = "art-mini-door"; go.textContent = "confirm defer";
    go.addEventListener("click", async () => {
      const when = date.value || "";
      const note = when ? ("withheld until " + when) : "deferred";
      if (await fireVerdict("defer", f, { note }, msgEl)) { clearForm(); closeInspection(); }
    });
    [lab, date, go].forEach((n) => form.appendChild(n));
    defer.textContent = "cancel defer";
  });
  route.addEventListener("click", () => {
    if (form.dataset.mode === "route") { clearForm(); return; }
    disarm(); clearForm(); form.dataset.mode = "route"; form.style.display = "flex";
    const plan = routePlanForKind(f.kind);
    const fillSelect = (opts) => {
      const lab = document.createElement("span"); lab.className = "art-k"; lab.textContent = "standing order";
      const sel = document.createElement("select"); sel.dataset.role = "route-intent";
      opts.forEach(([v, t]) => { const o = document.createElement("option"); o.value = v; o.textContent = t; sel.appendChild(o); });
      const go = document.createElement("button"); go.type = "button"; go.className = "art-mini-door"; go.textContent = "confirm route";
      go.addEventListener("click", async () => {
        const intent = sel.value || "other";
        if (await fireVerdict("route-conceptric", f, { intent, note: "route: " + intent }, msgEl)) { clearForm(); closeInspection(); }
      });
      [lab, sel, go].forEach((n) => form.appendChild(n));
    };
    if (plan.prose) {
      // item 6b — a prose-class kind: no conceptric order fits. Surface the plain mismatch.
      const msg = document.createElement("div"); msg.className = "art-verb-msg"; msg.dataset.role = "route-mismatch";
      msg.innerHTML = "routing rewrites the concept map — <b>" + esc(kindInWords(f.kind)) +
        "</b> is usually a prose fix, not a substrate one. <b>Confirm</b> it instead so it rides the next round as prose work.";
      const anyway = document.createElement("button"); anyway.type = "button"; anyway.className = "art-mini-door";
      anyway.textContent = "route anyway (generic order)";
      anyway.addEventListener("click", () => { msg.remove(); anyway.remove(); fillSelect(GENERIC_INTENTS); });
      form.appendChild(msg); form.appendChild(anyway);
    } else {
      if (plan.generic) {
        const note = document.createElement("div"); note.className = "art-verb-msg";
        note.textContent = "routing banks a standing order so the substrate is fixed, not the prose — pick the order this finding names.";
        form.appendChild(note);
      }
      fillSelect(plan.fitted);
    }
    route.textContent = "cancel route";
  });
}

// ── E4 #2 — the inspection area: open REALLOCATES, close RESTORES exactly ────────
// A finding opened from the tray claims the inspection area (#art-inspect); the pdf pane, the
// rail, and the tray compact around it (#art.is-inspecting). Closing pops the focus, restores
// the exact scroll, and remembers which finding was open. It consumes engine.mjs primitives —
// the same focus grammar the growth cockpit runs, layered onto the editor's own panes.
function _inspectHost() { return $("#art-inspect"); }

function openFindingInspection(fid) {
  const host = _inspectHost();
  const root = $("#art");
  if (!host || !root) return;
  const f = _findingByFid(fid);
  if (!f) return;
  _soloFocus(root, "is-inspecting");   // one focus at a time — close prov/thread/diff first
  const switching = root.classList.contains("is-inspecting");
  INSPECT_BUS.clear();                                   // hygiene: clear at the start of every open/switch
  if (!switching) INSPECT.restore.scrollY = window.scrollY;   // geometry + scroll captured at the first open
  INSPECT_OPEN = "finding:" + fid;
  INSPECT_LAST_FID = fid;
  INSPECT.pinned = { id: fid, kind: "finding" };
  $$("#art-tray-body .art-frow").forEach((r) => r.classList.toggle("is-open", r.dataset.fid === fid));
  const corpus = _corpus();
  const pa = composedGlance(f);
  const sec = _secLabel(f.section);
  const node = (f.node && f.node !== "?") ? f.node : "";
  host.innerHTML = "";
  const door = returnDoor("back to the findings tray — where you were", () => closeInspection());
  const head = document.createElement("div");
  head.className = "art-inspect-head";
  head.innerHTML = "<span class='art-inspect-k'>finding</span>" +
    "<span class='art-inspect-title'>" + esc(cut(f.comment || f.kind || "finding", 90)) + "</span>";
  head.appendChild(door);
  // the panel NAMES its anchor + carries "show in the paper" (navigation lands focus, his law):
  // works whether the finding was opened from a gutter mark or the tray lens.
  const anc = resolveFindingAnchor(f);
  if (anc) {
    const chip = document.createElement("span");
    chip.className = "art-inspect-anchor";
    chip.textContent = (anc.label || "anchor") + " · p" + anc.page;
    head.appendChild(chip);
    const show = document.createElement("button");
    show.type = "button"; show.className = "art-mini-door art-show-in-paper";
    show.textContent = "show in the paper";
    show.title = "scroll the paper back to this anchor and flash it";
    activate(show, () => scrollAndFlashPdf(anc.page, (anc.x0 != null ? anc.x0 : 0), anc.y0));
    head.appendChild(show);
  }
  host.appendChild(head);
  const body = document.createElement("div");
  body.className = "art-inspect-body";
  if (pa.absent) {
    // fallback law: when the upstream composition layer never minted a working account,
    // COMPOSE what can be composed from the record's own fields — the kind said in words,
    // its comment, a quote/anchor when present, where it argues — and state plainly when a
    // legacy row carries no more than its bare kind. The raw id stays at audit depth only.
    const parts = ["<div class='art-compose-kind'>" + esc(kindInWords(f.kind)) + "</div>"];
    const comment = (f.comment || "").trim();
    if (comment) parts.push("<div class='art-compose-line'>" + esc(comment) + "</div>");
    const quote = (f.quote || "").trim();
    if (quote) parts.push("<div class='art-compose-quote'>" + esc(cut(quote, 240)) + "</div>");
    const where = [];
    if (sec) where.push("§ " + esc(cut(sec, 40)));
    if (node) where.push("argues " + esc(cut(node, 40)));
    if (f.anchor && typeof f.anchor === "object" && (f.anchor.paragraph || f.anchor.page))
      where.push("¶ " + esc(String(f.anchor.paragraph || f.anchor.page)));
    if (where.length) parts.push("<div class='art-compose-meta'>" + where.join(" · ") + "</div>");
    if (!comment && !quote)
      parts.push("<div class='art-dim'>this legacy row carries no working account beyond its " +
        "kind — the line above is composed from the row's own fields; the composition layer " +
        "postdates it.</div>");
    const audit = [f.id].filter((x) => x && x !== "?");
    body.innerHTML = "<div class='art-inspect-compose'>" + parts.join("") + "</div>" +
      (audit.length ? "<div class='art-inspect-audit'>audit · " +
        audit.map((x) => "<code>" + esc(x) + "</code>").join(" · ") + "</div>" : "");
  } else {
    const b = pa.block;
    const working = (b.working || "").trim();
    const dec = b.decision || null;
    const audit = (b.audit && b.audit.ids) || [];
    body.innerHTML =
      (working ? "<div>" + esc(working) + "</div>" : "") +
      (dec && dec.tension ? "<div class='art-dim'>" + esc(dec.tension) + "</div>" : "") +
      (audit.length ? "<div class='art-inspect-audit'>audit · " +
        audit.map((x) => "<code>" + esc(x) + "</code>").join(" · ") + "</div>" : "");
  }
  // the four verdict doors (the governing failure): confirm / dismiss / defer / route,
  // each naming its consequence before it fires (arm-then-fire), POSTing /review/adjudicate
  // with an explicit session actor; the tray refreshes from server truth after any verdict.
  const verdicts = document.createElement("div");
  verdicts.className = "art-inspect-doors";
  verdicts.dataset.role = "verdict-doors";
  const vmsg = document.createElement("div");
  vmsg.className = "art-verb-msg"; vmsg.dataset.role = "verdict-msg";
  body.appendChild(verdicts);
  renderVerdictDoors(f, verdicts, vmsg);
  body.appendChild(vmsg);
  // the navigation doors (jump the reader to the section, door to the node it argues).
  const doors = document.createElement("div");
  doors.className = "art-inspect-doors";
  if (sec) {
    const show = document.createElement("button");
    show.type = "button"; show.className = "hy-door"; show.textContent = "show §" + cut(sec, 18) + " in the reader";
    activate(show, () => jumpToFindingSection(sec));
    doors.appendChild(show);
  }
  if (node)
    doors.insertAdjacentHTML("beforeend", "<a href='#' class='hy-door art-adoor' data-goto='/conceptric?corpus=" +
      ec(corpus) + "&node=" + ec(node) + "' title='the node this finding argues on'>the node it argues →</a>");
  body.appendChild(doors);
  host.appendChild(body);
  root.classList.add("is-inspecting");
  // light the tray rows sharing this finding's section (a spatial relation across the tray).
  if (sec) INSPECT_BUS.lit([["section", sec]], true);
  if (!switching) host.scrollIntoView({ block: "start", behavior: "smooth" });
}

function closeInspection() {
  const root = $("#art");
  if (!root || !root.classList.contains("is-inspecting")) return;
  INSPECT_BUS.clear();                                   // hygiene: clear at the start of every close
  INSPECT_OPEN = null;
  INSPECT.pinned = null;
  root.classList.remove("is-inspecting");
  const host = _inspectHost(); if (host) host.innerHTML = "";
  $$("#art-tray-body .art-frow").forEach((r) => r.classList.remove("is-open"));
  window.scrollTo(0, INSPECT.restore.scrollY || 0);     // exact scroll restore
}

// ── The provenance pane — "open a pane on an equation/figure and see where it came ──
// from" (the author's banked commission). It materialises in the
// MARGIN (the judgment margin's reallocation idiom): opening CLAIMS the margin (the tray +
// rail recede, #art.is-proving), it carries a named return door back to the tray, closing
// RESTORES the exact scroll. It leads with the SERVED glance sentence, then the chain worded
// as stations, then the feedback verbs AT the object — a comment pre-anchored to the object,
// a door into any open finding it carries, and the "see it across the map" lineage arrival.
// It NEVER invents a chain: every station is present only when the join resolves, and an
// object the index cannot bind opens to the served composed absence.
let PROV_RESTORE_Y = 0, PROV_OPEN = null;

// which object region (a measured equation band, a figure float) sits under a page point.
// The tightest containing region wins (an equation nested in a paragraph's column band is
// the object, not the prose). Distinct from anchorAtPoint (paragraph markers) by design.
function objectAtPoint(pageNo, px, py) {
  const nm = NODEMAP[_corpus()];
  if (!nm || !nm.present || !nm.entries) return null;
  let best = null;
  for (const [aid, regions] of Object.entries(nm.entries)) {
    for (const r of regions || []) {
      if (r.page !== pageNo) continue;
      const k = r.kind;
      if (k !== "equation" && k !== "float") continue;   // object regions carry a real band
      if (typeof r.y0 !== "number") continue;
      const y0 = Math.min(r.y0, typeof r.y1 === "number" ? r.y1 : r.y0);
      const y1 = Math.max(r.y0, typeof r.y1 === "number" ? r.y1 : r.y0);
      if (py < y0 - 3 || py > y1 + 3) continue;
      const x0 = typeof r.x0 === "number" ? r.x0 : 0, x1 = typeof r.x1 === "number" ? r.x1 : 1e4;
      if (px < x0 - 3 || px > x1 + 3) continue;
      if (r.width && r.width !== "measured") continue;   // coarse rect → no reader affordance (his exactness)
      if (y1 - y0 < 2) continue;                          // a zero-height marker is not a text band
      const area = Math.max(1, y1 - y0);
      if (!best || area < best.area) best = { aid, kind: k, region: r, area };
    }
  }
  return best;
}

// every DRAWABLE measured rect for an object (deduped) — an equation spanning lines yields
// per-line rects, a figure its true frame. Coarse/missing rects yield nothing, so the
// highlight only ever hugs text the nodemap actually measured (never an inaccurate box).
function objectRects(aid) {
  const nm = NODEMAP[_corpus()];
  const regions = (nm && nm.entries && nm.entries[aid]) || [];
  const seen = new Set(); const out = [];
  for (const r of regions) {
    if (r.kind !== "equation" && r.kind !== "float") continue;
    if (r.width && r.width !== "measured") continue;
    if (typeof r.y0 !== "number") continue;
    const y1 = typeof r.y1 === "number" ? r.y1 : r.y0;
    if (Math.abs(y1 - r.y0) < 2) continue;
    const key = [r.x0, r.y0, r.x1, r.y1].join(",");
    if (seen.has(key)) continue; seen.add(key);
    out.push(r);
  }
  return out;
}

// resolve a nodemap key to the provenance door's object ref: an equation label resolves
// directly; a figure key maps to its asset id through the /assets/list roster (the same join
// the anchor overlay already trusts), with a mechanical fallback.
async function objectRefFor(aid, kind) {
  if (kind === "equation" || (aid && aid.startsWith("eq:"))) return aid;
  const assets = await ensureAssets();
  const all = [].concat((assets && assets.figures) || [], (assets && assets.derivations) || []);
  const hit = all.find((a) => a.node_id === aid || a.id === aid);
  if (hit && hit.id) return hit.id;
  return "figure:" + String(aid).replace(/:/g, "_");
}

// the best node to pre-anchor a comment on, off the pane's OWN served data (never invented):
// the object's own node, else its isnad origin node, else its first concept node, else empty
// (the server then keys by section or the object ref itself).
function provNodeFor(p) {
  const w = (p && p.working) || {};
  if (w.node_id) return w.node_id;
  if (w.isnad && w.isnad.origin_node) return w.isnad.origin_node;
  const cn = (w.conceptric_nodes || [])[0];
  if (cn && cn.id) return cn.id;
  return "";
}

// the composed body a non-2xx provenance read still carries (the served 404 absence): the
// gateway throws with the body text in its message; recover the JSON so the pane renders the
// SERVED words rather than a re-synthesised absence.
function servedBodyFromError(e) {
  const m = (e && e.message) || "";
  const i = m.indexOf("{");
  if (i === -1) return null;
  try { return JSON.parse(m.slice(i)); } catch (_e) { return null; }
}

function provStationsHTML(payload) {
  const w = (payload && payload.working) || {};
  const rows = [];
  const cn = w.conceptric_nodes || [];
  if (cn.length) {
    rows.push("<div class='art-prov-station'><div class='art-prov-st-k'>descends from the concept</div>" +
      cn.map((n) => "<div class='art-prov-st-v'><span class='art-prov-term'>" +
        esc(cut(n.label || n.id, 90)) + "</span> <span class='art-prov-id'>" + esc(n.id) + "</span></div>").join("") +
      "</div>");
  }
  const para = w.paragraph;
  if (para && (para.spec_ids?.length || para.spec_id || para.function)) {
    const job = (para.function || "").trim();
    rows.push("<div class='art-prov-station'><div class='art-prov-st-k'>realised in the paragraph</div>" +
      "<div class='art-prov-st-v'>" + (job ? esc(job.replace(/\.$/, "")) + " " : "") +
      "<span class='art-prov-id'>" + esc((para.spec_ids || (para.spec_id?[para.spec_id]:[])).join(" · ")) + "</span></div></div>");
  } else if (w.section) {
    rows.push("<div class='art-prov-station'><div class='art-prov-st-k'>carried in section</div>" +
      "<div class='art-prov-st-v'><span class='art-prov-id'>" + esc(w.section) + "</span></div></div>");
  }
  // the dispatch aim that wrote it (present only when the composed head carries it).
  const aim = (w.aim || (para && para.aim) || "").trim();
  const role = (w.role_in_whole || "").trim();
  if (aim) {
    rows.push("<div class='art-prov-station'><div class='art-prov-st-k'>the dispatch that wrote it</div>" +
      "<div class='art-prov-st-v'>" + esc(cut(aim, 140)) + (role ? " <span class='art-prov-id'>" + esc(cut(role, 60)) + "</span>" : "") + "</div></div>");
  }
  // the isnad origin, with its link status.
  const isn = w.isnad;
  if (isn && (isn.origin || isn.origin_node || isn.link)) {
    const linked = cn.length > 0;
    const status = linked ? ["concept-linked", "is-ok"] : (isn.origin_node ? ["derivation-anchored", "is-ok"] : ["origin open", "is-warn"]);
    rows.push("<div class='art-prov-station is-origin'><div class='art-prov-st-k'>where it came from</div>" +
      "<div class='art-prov-st-v'>authored inside the derivation of <span class='art-prov-term'>" +
      esc(cut(isn.origin || "an unnamed derivation", 90)) + "</span>" +
      (isn.link ? " <span class='art-prov-link " + status[1] + "'>" + esc(isn.link) + " · " + status[0] + "</span>" : "") +
      (isn.origin_node ? "<div class='art-prov-id'>" + esc(isn.origin_node) + "</div>" : "") +
      "</div></div>");
  }
  // where it lands: an equation's page, or a figure's landing pages.
  const pages = [...new Set((w.asset_landings || []).map((l) => l.page).filter((x) => x != null))].sort((a, b) => a - b);
  if (pages.length) {
    rows.push("<div class='art-prov-station'><div class='art-prov-st-k'>lands on</div>" +
      "<div class='art-prov-st-v'>page" + (pages.length === 1 ? " " : "s ") + pages.join(", ") +
      " of the rendered artefact</div></div>");
  } else if (w.page != null) {
    rows.push("<div class='art-prov-station'><div class='art-prov-st-k'>lands on</div>" +
      "<div class='art-prov-st-v'>page " + esc(String(w.page)) + " of the rendered artefact</div></div>");
  }
  if (!rows.length)
    return "<div class='art-prov-empty'>no chain resolved for this object — the sentence above " +
      "states its provenance as the door composed it.</div>";
  return "<div class='art-prov-stations'>" + rows.join("") + "</div>";
}

function renderProvPayload(pane, objectRef, payload, resolved, servedAbsence) {
  const w = (payload && payload.working) || {};
  const a = (payload && payload.audit) || {};
  const kind = (w.paragraph ? "paragraph" : (w.isnad ? "equation" : (w.asset_landings && w.asset_landings.length ? "figure" : ((payload && payload.resolved_kind) || ""))));
  const glance = (payload && payload.glance) ||
    (servedAbsence ? servedAbsence
      : ("Nothing named " + objectRef + " resolves in this corpus — it is not a tex label, a concept node, an asset, or a paragraph the index carries."));
  pane.innerHTML =
    "<div class='art-prov-head'><span class='art-prov-k'>provenance</span>" +
      "<span class='art-prov-obj'>" + esc(cut(objectRef, 44)) + "</span>" +
      (kind ? "<span class='art-prov-kind'>" + esc(kind) + "</span>" : "") +
      "<span data-role='prov-return'></span></div>" +
    "<div class='art-prov-glance'>" + esc(glance) + "</div>" +
    (resolved ? provStationsHTML(payload) : "") +
    "<div class='art-prov-doors' data-role='prov-doors'></div>" +
    (resolved ? provAuditHTML(a) : "");
  // the named return door back to the tray (the margin's resting judgment).
  const rd = pane.querySelector("[data-role='prov-return']");
  if (rd) rd.appendChild(returnDoor("back to the findings tray", () => closeProvenance()));
  renderProvDoors(pane, objectRef, payload, resolved);
  wireProvAudit(pane);
  // the prov pane NAMES where the object lands + carries "show in the paper" when the nodemap
  // measures it (opened from a gutter mark): navigation lands focus for objects too (item 3).
  const e = _nmEntries(), preg = e && e[objectRef];
  const pp = preg && (_firstPos(preg.filter((r) => r.width === "measured")) || _firstPos(preg));
  if (pp) {
    const head = pane.querySelector(".art-prov-head");
    if (head) {
      const show = document.createElement("button");
      show.type = "button"; show.className = "art-mini-door art-show-in-paper";
      show.textContent = "show in the paper";
      activate(show, () => scrollAndFlashPdf(pp.page, (pp.x0 != null ? pp.x0 : 0), pp.y0));
      head.appendChild(show);
    }
  }
}

function provAuditHTML(a) {
  const jp = a.join_provenance || [];
  const st = a.staleness || {};
  const ids = a.ids || [];
  const stale = st.fresh === false;
  return "<div class='art-prov-audit' data-role='prov-audit'>" +
    "<div class='art-prov-audit-h' data-role='prov-audit-h'>▸ how this was joined" +
      (stale ? " · <span class='art-prov-link is-warn'>index stale</span>" : "") + "</div>" +
    "<div class='art-prov-audit-body'>" +
      (a.join ? "<div>join · <code>" + esc(a.join) + "</code></div>" : "") +
      (jp.length ? "<div>" + jp.map((p) => "· " + esc(p)).join("<br>") + "</div>" : "") +
      (st.note ? "<div>" + esc(st.note) + (stale && (st.moved || []).length ? " (" + esc((st.moved || []).join(", ")) + " moved)" : "") + "</div>" : "") +
      (ids.length ? "<div>ids · " + ids.map((x) => "<code>" + esc(x) + "</code>").join(" · ") + "</div>" : "") +
    "</div></div>";
}
function wireProvAudit(pane) {
  const h = pane.querySelector("[data-role='prov-audit-h']");
  const box = pane.querySelector("[data-role='prov-audit']");
  if (h && box && !h.dataset.wired) { h.dataset.wired = "1";
    h.addEventListener("click", () => { const on = box.classList.toggle("open");
      h.firstChild.textContent = (on ? "▾" : "▸") + " how this was joined"; }); }
}

// Feedback right there — the detailed-feedback verbs, at the object:
//  (a) a comment door that banks through the review surface's write path, pre-anchored to
//      the object (node_id + anchor.object from the pane's own data); the session-actor law
//      holds (422 without an actor).
//  (b) every open finding the object's node carries → a door into the finding inspection.
//  (c) "see it across the map" → the lineage arrival contract (/lineage?corpus=&object=).
function renderProvDoors(pane, objectRef, payload, resolved) {
  const host = pane.querySelector("[data-role='prov-doors']");
  if (!host) return;
  const corpus = _corpus();
  const a = (payload && payload.audit) || {};
  const findings = a.open_findings || [];
  // (b) open findings on this object's node.
  if (findings.length) {
    const label = document.createElement("div");
    label.className = "art-prov-st-k";
    label.textContent = findings.length + " open finding" + (findings.length === 1 ? "" : "s") + " on this object";
    host.appendChild(label);
    for (const f of findings) {
      const btn = document.createElement("button");
      btn.type = "button"; btn.className = "art-prov-finding";
      btn.textContent = cut(f.comment || f.id || "a finding", 80);
      btn.title = "open this finding's inspection — the four verdict verbs";
      activate(btn, () => { const fid = f.id; closeProvenance(); if (fid) openFindingInspection(fid); });
      host.appendChild(btn);
    }
  }
  // (a) the comment door — pre-anchored to the object.
  const cwrap = document.createElement("div");
  cwrap.className = "art-prov-doorrow";
  const cbtn = document.createElement("button");
  cbtn.type = "button"; cbtn.className = "hy-door is-primary";
  cbtn.textContent = "comment on this object";
  cbtn.title = "bank a finding pre-anchored to " + objectRef + " (node_id + anchor) — POST /review/adjudicate {verb:comment}";
  cwrap.appendChild(cbtn);
  host.appendChild(cwrap);
  cbtn.addEventListener("click", () => {
    if (cwrap.dataset.open) return;
    cwrap.dataset.open = "1"; cbtn.style.display = "none";
    const form = document.createElement("div");
    form.className = "art-prov-comment";
    const ta = document.createElement("textarea");
    ta.placeholder = "the detailed feedback, right here — banked pre-anchored to " + cut(objectRef, 30);
    const row = document.createElement("div"); row.className = "art-prov-doorrow";
    const go = document.createElement("button"); go.type = "button"; go.className = "hy-door is-primary"; go.textContent = "bank the comment";
    const cancel = document.createElement("button"); cancel.type = "button"; cancel.className = "art-mini-door"; cancel.textContent = "cancel";
    const msg = document.createElement("div"); msg.className = "art-prov-msg";
    row.appendChild(go); row.appendChild(cancel);
    form.appendChild(ta); form.appendChild(row); form.appendChild(msg);
    cwrap.appendChild(form); ta.focus();
    cancel.addEventListener("click", () => { form.remove(); cbtn.style.display = ""; delete cwrap.dataset.open; });
    go.addEventListener("click", async () => {
      const text = (ta.value || "").trim();
      if (!text) { msg.className = "art-prov-msg is-bad"; msg.textContent = "the comment needs text"; return; }
      if (await fireProvComment(objectRef, payload, text, msg)) { ta.value = ""; ta.disabled = true; go.disabled = true; }
    });
  });
  // (c) see it across the map — the lineage arrival contract.
  const lref = provNodeFor(payload) || (resolved ? objectRef : "");
  const map = document.createElement("div"); map.className = "art-prov-doorrow";
  map.innerHTML = "<a href='/lineage?corpus=" + ec(corpus) + "&object=" + ec(objectRef) + "' " +
    "class='hy-door' title='the lineage surface — this object and everything it leads to across the map'>see it across the map →</a>";
  host.appendChild(map);
  void lref;
}

async function fireProvComment(objectRef, payload, text, msgEl) {
  const actor = sessionActor();
  if (!actor) { msgEl.className = "art-prov-msg is-bad";
    msgEl.textContent = "no session actor — the door refuses an unattributed comment (open with ?actor= or a signed-in shell)"; return false; }
  const w = (payload && payload.working) || {};
  msgEl.className = "art-prov-msg"; msgEl.textContent = "banking…";
  try {
    const res = await store.fetchJSON("/review/adjudicate", { method: "POST", params: { corpus: _corpus() },
      body: { verb: "comment", by: actor, corpus: _corpus(), object: objectRef,
              node: provNodeFor(payload), section: w.section || "", page: w.page,
              comment: text, coarse: true } });
    msgEl.className = "art-prov-msg is-ok";
    msgEl.textContent = "banked ✓ " + ((res && res.record && res.record.id) || "") + " · by " + actor;
    await loadTriagedTray();               // the flag appears in the tray count
    return true;
  } catch (e) { msgEl.className = "art-prov-msg is-bad"; msgEl.textContent = "comment refused — " + cut(cleanErr(e), 120); return false; }
}

async function openProvenance(objectRef) {
  const pane = $("#art-prov"), root = $("#art");
  if (!pane || !root || !objectRef) return;
  if (INSPECT_BUS) INSPECT_BUS.clear();
  _soloFocus(root, "is-proving");   // one focus at a time — close inspect/thread/diff first
  const main = $("#art-main");
  if (main && main.classList.contains("margin-folded")) {   // the pane must be visible
    main.classList.remove("margin-folded");
    const mt = $("#art-margin-toggle"); if (mt) mt.textContent = "fold the margin";
  }
  if (!root.classList.contains("is-proving")) PROV_RESTORE_Y = window.scrollY;
  PROV_OPEN = objectRef;
  root.classList.add("is-proving");
  pane.innerHTML = "<div class='art-prov-empty'>reading where " + esc(cut(objectRef, 40)) + " came from…</div>";
  pane.scrollIntoView({ block: "nearest", behavior: "smooth" });
  let payload = null, resolved = true, servedAbsence = null;
  try { payload = await store.fetchJSON("/provenance/object", { params: { object: objectRef } }); }
  catch (e) { const b = servedBodyFromError(e); if (b) { payload = b; resolved = false; } else { servedAbsence = cleanErr(e); resolved = false; } }
  if (PROV_OPEN !== objectRef) return;                       // a newer open won the race
  if (payload && payload.resolved === false) resolved = false;
  renderProvPayload(pane, objectRef, payload, resolved, servedAbsence);
}

function closeProvenance() {
  const root = $("#art"), pane = $("#art-prov");
  if (!root || !root.classList.contains("is-proving")) return;
  if (INSPECT_BUS) INSPECT_BUS.clear();
  root.classList.remove("is-proving");
  if (pane) pane.innerHTML = "";
  PROV_OPEN = null;
  window.scrollTo(0, PROV_RESTORE_Y || 0);                   // exact scroll restore
}

// #object — a cold deep link: ?object=<id> opens its provenance pane, mirroring ?finding=.
function openDeepLinkedObject() {
  let ref = null;
  try { ref = new URLSearchParams((window.location && window.location.search) || "").get("object"); }
  catch (e) { return; }
  if (!ref) return;
  openProvenance(ref).catch(() => {});
}

// the source-pane object affordance: when the CM6 cursor lands on a `\label{...}` line, the
// source bar offers the SAME "where this came from" door into the provenance pane.
const _LABEL_RX = /\\label\{((?:eq|fig):[^}]+)\}/;
function updateLabelProv(lineText) {
  const host = $("#art-label-prov");
  if (!host) return;
  const m = _LABEL_RX.exec(lineText || "");
  if (!m) { if (host.dataset.label) { host.innerHTML = ""; host.dataset.label = ""; } return; }
  const label = m[1];
  if (host.dataset.label === label) return;
  host.dataset.label = label;
  host.innerHTML = "<button type='button' class='art-labelprov' data-role='label-prov' " +
    "title='open the provenance pane for " + esc(label) + "'>⟿ " + esc(cut(label, 26)) + " — where it came from</button>";
}

// ── plan + nodemap (the anchor truth) ───────────────────────────────────────────
async function ensurePlan() {
  if (PLAN !== null) return PLAN;
  try { PLAN = await store.fetchJSON("/shared/plan"); } catch (e) { PLAN = false; }
  return PLAN;
}
async function ensureNodemap() {
  const key = _corpus();
  if (key in NODEMAP) return NODEMAP[key];
  try { NODEMAP[key] = await store.fetchJSON("/review/nodemap"); }
  catch (e) { NODEMAP[key] = { present: false, fresh: false, stale_reason: "the node→region map did not load" }; }
  return NODEMAP[key];
}
function _corpus() { return store.field("corpus") || (CTX && CTX.corpus) || ""; }
function compileParams(file, extra = {}) {
  return { file, corpus: _corpus(), compile_root: CTX?.current_artefact?.tex || currentRevision().tex || "", ...extra };
}
function compileTargetCurrent(target) {
  return target.params.file===EDIT_FILE&&target.generation===EDIT_LOAD_GENERATION&&target.params.compile_root===compileParams(EDIT_FILE).compile_root&&target.params.corpus===_corpus();
}

// ── ACT 3 · #5 — asset door-chips (declared absence otherwise) ────────────────────
async function ensureAssets() {
  const c = _corpus();
  if (c in ASSETS_CACHE) return ASSETS_CACHE[c];
  try { ASSETS_CACHE[c] = await store.fetchJSON("/assets/list"); }
  catch (e) { ASSETS_CACHE[c] = null; }
  return ASSETS_CACHE[c];
}
// a paragraph's SECTION nodes back a figure/derivation when that asset's own
// nodes_supported (or singular node_id) intersects them — the SAME join the anchor
// overlay's node chips already trust (sec.nodes_in_order), read straight off the
// /assets/list roster card (no extra route, no invented join).
function assetsForNodes(assetsPayload, nodes) {
  if (!assetsPayload || !nodes || !nodes.length) return [];
  const all = [].concat(assetsPayload.figures || [], assetsPayload.derivations || []);
  const nodeset = new Set(nodes);
  return all.filter((a) => (a.nodes_supported || []).some((n) => nodeset.has(n)) ||
                            (a.node_id && nodeset.has(a.node_id)));
}
function assetChipHTML(a, corpus) {
  const goto = "/assets?corpus=" + ec(corpus) + "&asset=" + ec(a.id);
  return "<a href='" + esc(goto) + "' class='hy-chip art-adoor' data-goto='" + esc(goto) +
    "' title='" + esc(goto) + " — the " + esc(a.kind) + " backing this paragraph'>▤ " +
    esc(cut(a.id, 26)) + "</a>";
}

// ── EDIT mode: CM6 over the tex, TWO-WAY synctex-coupled to the pdf pane ─────────
// (ACT 3 #1–#3) — the source file can SWITCH under the editor: a pdf click resolves
// through /projection/synctex, and when it names a fragment other than the one open,
// loadEditFile re-fetches and re-mounts THAT file before moving the cursor (a paper's
// paragraphs mostly live in \input fragments, not the root the reader shows by default).
async function loadEditFile(file) {
  const host = $("#art-cm");
  if (!host || !file) return;
  const generation = ++EDIT_LOAD_GENERATION;
  let text = "";
  let observed;
  try {
    observed = await readManuscriptSource({project:_corpus(),file,endpoint:CTX.tex_endpoint,transport:(path,options)=>store.fetchJSON(path,options)});
    if (observed.schema_version !== "laplace.projection-source/1" ||
        typeof observed.content !== "string" || !/^sha256:[0-9a-f]{64}$/.test(observed.expected_source_digest)) {
      throw Error("The source owner did not supply an exact inspected guard.");
    }
    text = observed.content;
  }
  catch (e) {
    if (generation !== EDIT_LOAD_GENERATION) return;
    host.innerHTML = "<div class='art-msg'>could not load the tex: " + esc((e && e.message) || e) + "</div>";
    return;
  }
  if (generation !== EDIT_LOAD_GENERATION) return;
  EDIT_FILE = observed.file;
  EDIT_SOURCE_DIGEST = observed.expected_source_digest; EDIT_SOURCE_OBSERVATION=observed; EDIT_EFFECT_HOLD=null;
  const lbl = $("#art-edit-file"); if (lbl) lbl.textContent = observed.file;
  if (CM_VIEW) {
    CM_VIEW.dispatch({ changes: { from: 0, to: CM_VIEW.state.doc.length, insert: String(text) } });
  } else {
    const mounted=await mountExactSourceEditor(host,{content:String(text),onUpdate:onCmUpdate,onSave:saveAndRecompile,label:'LaTeX source'});
    if(generation!==EDIT_LOAD_GENERATION){mounted.destroy();return;}
    CM_VIEW=mounted.view;CM_MOD=mounted.module;
    if(!CM_VIEW)mounted.element.id='art-cm-ta';
  }

  ensureFollow();
  ensureHisHand();   // the author's own edited passages for THIS file (off the rail attribution)
}
function editorText() {
  if (CM_VIEW) return CM_VIEW.state.doc.toString();
  const ta = $("#art-cm-ta"); return ta ? ta.value : "";
}

// ── the his-hand layer — "highlight the text I've edited/added myself" ────────────
// Grounded in the version rail's actor attribution (/review/his-hand): his ranges are the
// diff of the open file against the newest machine-minted baseline. Rendered as quiet gold
// CM6 line decorations behind a toggle chip that names the count; empty cases stated plainly
// in words. The bundle exports no Decoration, so the wash rides a .cm-line class re-applied
// on every view update (the surface's positioned-overlay idiom, one level in).
async function ensureHisHand() {
  if (!EDIT_FILE) { HISHAND = null; renderHisHandChip(); return; }
  let warning = null;
  try { HISHAND = await store.fetchJSON("/review/his-hand", { params: { file: EDIT_FILE } }); }
  catch (e) { HISHAND = null; warning = String(e?.message || e); }
  renderHisHandChip();
  decorateHisHand();
  return { ok: warning === null, warning };
}
function _hishandActionable() {
  return !!(HISHAND && HISHAND.attributed &&
    (HISHAND.whole_file || ((HISHAND.counts && HISHAND.counts.passages) || 0) > 0));
}
function renderHisHandChip() {
  const host = $("#art-hishand");
  if (!host) return;
  if (!HISHAND || !HISHAND.ok) { host.innerHTML = ""; return; }
  const note = HISHAND.note || "";
  if (!HISHAND.attributed) {   // the rail cannot attribute — say so, never invent a hand
    host.innerHTML = "<span class='art-hishand-chip is-off' title='" + esc(note) + "'>your hand · unattributed</span>";
    return;
  }
  const n = (HISHAND.counts && HISHAND.counts.passages) || 0;
  const label = HISHAND.whole_file ? "the whole file"
    : (n === 0 ? "none yet" : (n + " passage" + (n === 1 ? "" : "s")));
  const actionable = _hishandActionable();
  const active = HISHAND_ON && actionable;
  host.innerHTML = "<button type='button' class='art-hishand-chip" + (active ? " is-on" : "") +
    (actionable ? "" : " is-off") + "' data-role='hishand-toggle' title='" + esc(note) +
    (actionable ? " — click to " + (active ? "hide" : "show") : "") + "'>your hand · " + esc(label) + "</button>";
}
function hisHandLineSet() {
  const set = new Set();
  if (!HISHAND || !CM_VIEW) return set;
  if (HISHAND.whole_file) { for (let i = 1; i <= CM_VIEW.state.doc.lines; i++) set.add(i); return set; }
  for (const r of HISHAND.ranges || []) for (let n = r.start; n <= r.end; n++) set.add(n);
  return set;
}
function decorateHisHand() {
  if (!CM_VIEW) return;
  const content = CM_VIEW.contentDOM;
  if (!content) return;
  content.querySelectorAll(".art-hishand-line").forEach((el) => el.classList.remove("art-hishand-line"));
  if (!HISHAND_ON || !_hishandActionable()) return;
  const maxLine = CM_VIEW.state.doc.lines;
  for (const n of hisHandLineSet()) {
    if (n < 1 || n > maxLine) continue;
    let dom;
    try { dom = CM_VIEW.domAtPos(CM_VIEW.state.doc.line(n).from).node; } catch (e) { continue; }
    if (dom && dom.nodeType === 3) dom = dom.parentNode;
    const lineEl = dom && dom.closest ? dom.closest(".cm-line") : null;
    if (lineEl) lineEl.classList.add("art-hishand-line");
  }
}
function toggleHisHand() {
  if (!_hishandActionable()) return;
  HISHAND_ON = !HISHAND_ON;
  renderHisHandChip();
  decorateHisHand();
}
// the forward (CM→pdf) leg: a debounced cursor move resolves /projection/locate. Skipped
// while FOLLOW_GUARD.isSuppressed() — the echo guard against a synctex-driven write
// re-triggering itself — and on plain doc edits (only a SELECTION move chases the pdf).
function onCmUpdate(update) {
  // the his-hand wash rides .cm-line classes CM6 recycles on scroll/edit — re-apply them
  // whenever the viewport, doc, or geometry moves so the highlight tracks the rendered lines.
  if (HISHAND_ON && (update.viewportChanged || update.docChanged || update.geometryChanged)) decorateHisHand();
  if (!update.selectionSet || FOLLOW_GUARD.isSuppressed()) return;
  try { updateLabelProv(update.state.doc.lineAt(update.state.selection.main.head).text); } catch (e) { /* no line */ }
  clearTimeout(SRC_DEBOUNCE);
  SRC_DEBOUNCE = setTimeout(() => {
    const line = update.state.doc.lineAt(update.state.selection.main.head).number;
    locateFromSource(line);
  }, 380);
}
async function locateFromSource(line) {
  if (!EDIT_FILE) return;
  const file=EDIT_FILE,generation=EDIT_LOAD_GENERATION,params=compileParams(file,{line});
  try {
    const res = await store.fetchJSON("/projection/locate", { params });
    if(file!==EDIT_FILE||generation!==EDIT_LOAD_GENERATION||params.compile_root!==compileParams(file).compile_root||params.corpus!==_corpus())return;
    if (res.error) { setFollowNote(res.error); return; }
    scrollAndFlashPdf(res.page, res.x, res.y);
  } catch (e) { /* a locate miss is quiet — not every cursor line resolves */ }
}
// the reverse (pdf→CM) leg: a page-click's (page,x,y) resolves /projection/synctex to a
// {file, line}; when that file differs from what's open, switch fragments first.
async function syncClickToSource(pt) {
  if (!EDIT_FILE) return;
  const file=EDIT_FILE,generation=EDIT_LOAD_GENERATION,params=compileParams(EDIT_FILE,{page:pt.page,x:pt.px.toFixed(2),y:pt.py.toFixed(2)});
  try {
    const res = await store.fetchJSON("/projection/synctex",
      { params });
    if(file!==EDIT_FILE||generation!==EDIT_LOAD_GENERATION||params.compile_root!==compileParams(file).compile_root||params.corpus!==_corpus())return;
    if (res.error) { followFailure(res.error); return; }
    await gotoSourceLine(res.file, res.line);
  } catch (e) { if(file===EDIT_FILE&&generation===EDIT_LOAD_GENERATION&&params.compile_root===compileParams(file).compile_root&&params.corpus===_corpus())followFailure(cleanErr(e)); }
}
async function gotoSourceLine(file, line) {
  if (file && file !== EDIT_FILE) await loadEditFile(file);
  if (!CM_VIEW || !line) return;
  const doc = CM_VIEW.state.doc;
  const ln = Math.max(1, Math.min(doc.lines, line));
  const lo = doc.line(ln);
  FOLLOW_GUARD.suppress();   // the echo guard: this write must not re-fire onCmUpdate's locate
  const effects = CM_MOD ? [CM_MOD.EditorView.scrollIntoView(lo.from, { y: "center" })] : [];
  CM_VIEW.dispatch({ selection: { anchor: lo.from, head: lo.to }, effects });
}
// scroll the pdf pane to (page,x,y) and flash a band there — the shared flashRegion atom,
// fed a synthetic "hit" the same shape anchorAtPoint produces (region + y0/yEnd).
function scrollAndFlashPdf(page, x, y) {
  const reader = $("#art-reader");
  const wrap = reader && $(".art-page[data-page='" + page + "']", reader);
  if (!wrap || !reader) return false;
  const rect = wrap.getBoundingClientRect(), rr = reader.getBoundingClientRect();
  const ph = parseFloat(wrap.dataset.ph) || 792, pw = parseFloat(wrap.dataset.pw) || 612;
  const sy = rect.height / ph;
  const top = reader.scrollTop + (rect.top - rr.top) + y * sy - Math.min(160, reader.clientHeight / 3);
  reader.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
  flashRegion(wrap, { region: { x0: 0, x1: pw }, y0: y, yEnd: y + 26 });
  return true;
}
// ACT 3 #4 — a tray finding's section lands the pdf pane on it, in ANY mode (the pdf
// pane exists in both reading and editing). Plain quiet failure: an unresolved
// section (no compiled pdf yet, stale synctex) just doesn't move anything.
async function jumpToFindingSection(section) {
  const file = (CTX && CTX.current_artefact && CTX.current_artefact.tex) || currentRevision().tex;
  if (!file) return false;
  try {
    const res = await store.fetchJSON("/projection/locate", { params: compileParams(file,{section}) });
    if (res.error) return false;
    return scrollAndFlashPdf(res.page, res.x, res.y);
  } catch (e) { return false; }
}
// the /projection/follow quiet status line (ACT 3 #2).
async function ensureFollow() {
  if (!EDIT_FILE) return;
  const file=EDIT_FILE,generation=EDIT_LOAD_GENERATION,params=compileParams(EDIT_FILE);
  let observed;
  try { observed = await store.fetchJSON("/projection/follow", { params }); }
  catch (e) { observed = null; }
  if(file!==EDIT_FILE||generation!==EDIT_LOAD_GENERATION||params.compile_root!==compileParams(file).compile_root||params.corpus!==_corpus())return;
  FOLLOW=observed;
  renderFollow();
}
// #3 — synctex at rest: when the follow map is absent (but a compiled paper IS on screen)
// the chip and any click serve a COMPOSED sentence + a one-act recompile door, never the raw
// fetch text; when the synctex file already exists on disk the follow works at rest, unforced.
function followDoorHTML() {
  return "<button type='button' class='art-mini-door' data-role='follow-recompile' " +
    "title='build the pdf + synctex here so the split follows both ways'>recompile to enable follow</button>";
}
function wireFollowDoor(el) {
  const b = el && el.querySelector("[data-role='follow-recompile']");
  if (b && !b.dataset.wired) { b.dataset.wired = "1"; b.addEventListener("click", () => startRecompile()); }
}
// item 4 — the source bar's STATE chips (synctex, his-hand) stand on one row; the explanation
// is DEMOTED to one quiet note line under the bar, carrying its one-act door and a dismiss ×.
// A compile (synctex fresh) or the × retires it. The note element is inserted once, after the bar.
function sourceNoteEl() {
  let el = document.getElementById("art-source-note");
  if (el) return el;
  const bar = document.getElementById("art-source-bar");
  if (!bar || !bar.parentNode) return null;
  el = document.createElement("div");
  el.id = "art-source-note"; el.className = "art-source-note";
  bar.parentNode.insertBefore(el, bar.nextSibling);
  return el;
}
function setSourceNote(sentence, withDoor) {
  const el = sourceNoteEl();
  if (!el) return;
  if (!sentence) { el.classList.remove("on"); el.innerHTML = ""; return; }
  el.innerHTML = "<span>" + sentence + "</span>" + (withDoor === false ? "" : followDoorHTML()) +
    "<button type='button' class='art-source-note-x' data-role='source-note-x' title='dismiss this note'>×</button>";
  el.classList.add("on");
  wireFollowDoor(el);
  const x = el.querySelector("[data-role='source-note-x']");
  if (x && !x.dataset.wired) { x.dataset.wired = "1"; x.addEventListener("click", () => setSourceNote("")); }
}
function renderFollow() {
  const el = $("#art-follow-status");
  if (!el) return;
  if (!FOLLOW) { el.innerHTML = ""; setSourceNote(""); return; }
  if (FOLLOW.fresh) {
    el.innerHTML = "<span class='hy-chip is-ok'>synctex fresh</span>";
    setSourceNote("");                       // the compile retires the explanation (item 4)
  } else if (FOLLOW.present) {
    el.innerHTML = "<span class='hy-chip is-warn'>synctex stale</span>";
    setSourceNote("the map lags the source — recompile to realign the split.");
  } else {
    el.innerHTML = "<span class='hy-chip is-warn'>synctex not built here</span>";
    setSourceNote("a compiled paper is on screen, but its follow map is not on disk yet — " +
      "build it here and the split follows both ways.");
  }
}
function showFollowAbsent() {
  const el = $("#art-follow-status");
  if (!el) return;
  el.innerHTML = "<span class='hy-chip is-warn'>synctex not built here</span>";
  setSourceNote("follow needs the paper compiled here first — build it and the click will jump the source.");
}
function setFollowNote(txt) {
  const el = $("#art-follow-status");
  if (el) el.innerHTML = "<span class='hy-chip is-warn'>follow paused</span>";
  setSourceNote(esc(cut(txt, 100)), false);
}
function followFailure(msg) {
  const m = String(msg || "").toLowerCase();
  if (/compil|synctex|\bpdf\b|no .*build|up.?to.?date/.test(m)) { showFollowAbsent(); return; }
  setFollowNote("the source did not resolve for that click");
}
function setEditMsg(txt, isBad) {
  const m = $("#art-edit-msg"); if (!m) return;
  m.textContent = txt; m.classList.toggle("is-bad", !!isBad);
}
async function refreshVersions() {
  let warning = null;
  try { VERS = decorateVersionRows(await store.fetchJSON("/shared/versions")); } catch (e) { warning = String(e?.message || e); }
  renderRailStrip();
  if ($("#art-main").classList.contains("rail-open")) renderRailFull();
  return { ok: warning === null, warning };
}
async function saveTex() {
  if (!EDIT_FILE) return null;
  if (EDIT_EFFECT_HOLD) { setEditMsg(EDIT_EFFECT_HOLD, true); return null; }
  const submission = { file: EDIT_FILE, digest: EDIT_SOURCE_DIGEST,
    generation: EDIT_LOAD_GENERATION, text: editorText() };
  setEditMsg("saving…");
  try {
    const res = await saveManuscriptSource({project:_corpus(),observed:{...EDIT_SOURCE_OBSERVATION,file:submission.file,expected_source_digest:submission.digest},content:submission.text,endpoint:CTX.tex_endpoint,surface:'edit',author:sessionActor(),transport:(path,options)=>store.fetchJSON(path,options)});
    if (submission.generation !== EDIT_LOAD_GENERATION || submission.file !== EDIT_FILE || EDIT_SOURCE_DIGEST !== submission.digest) return res;
    EDIT_SOURCE_DIGEST = res.expected_source_digest;EDIT_SOURCE_OBSERVATION=advanceSourceObservation(EDIT_SOURCE_OBSERVATION,{file:submission.file,content:submission.text,expected_source_digest:submission.digest,expected_selection:EDIT_SOURCE_OBSERVATION?.selection_identity},res);
    const warnings = Array.isArray(res.maintenance_warnings) ? [...res.maintenance_warnings] : [];
    setEditMsg(res.changed===false?"No source changes · no duplicate history banked":"source saved" + (res.version_id ? " · banked " + res.version_id : ""));
    try {
      const versions = await refreshVersions();
      if (versions?.ok === false) warnings.push({ operation: "version history", reason: versions.warning });
      const hand = await ensureHisHand();   // follow-through, never another source effect
      if (hand?.ok === false) warnings.push({ operation: "source attribution", reason: hand.warning });
    } catch (e) {
      warnings.push({ operation: "history refresh", reason: String(e?.message || e) });
    }
    if (warnings.length && submission.generation === EDIT_LOAD_GENERATION && submission.file === EDIT_FILE) {
      setEditMsg("source saved · maintenance needs inspection: " + warnings.map(w => w?.operation || String(w)).join(", "));
    }
    return res;
  } catch (e) {
    if (submission.generation === EDIT_LOAD_GENERATION && submission.file === EDIT_FILE) {
      const effect=sourceEffectFromError(e,{project:_corpus(),selectionIdentity:EDIT_SOURCE_OBSERVATION?.selection_identity});
      if(effect?.suppressRetry||e.sourceEffectUnverified)EDIT_EFFECT_HOLD=effect?.message||e.message;
      setEditMsg(EDIT_EFFECT_HOLD || (e?.body?.reason==='source-revision-conflict'
        ? "Source changed since it was opened. Your draft and original guard are retained; inspect the current source before choosing how to reconcile."
        : "save not confirmed; draft retained. Inspect the current source before retrying: " + ((e && e.message) || e)), true);
    }
    return null;
  }
}
// the live loop (ACT 3 #3): save → recompile → poll the pure status route → render
// compiling/ok/error inline → on success hot-reload the pdf pane (scroll kept) + refresh
// the rail; on error render clickable tex-log rows that jump the source.
async function saveAndRecompile() {
  const file = EDIT_FILE, generation = EDIT_LOAD_GENERATION;
  const saved = await saveTex();
  if (!saved) return;
  if (generation !== EDIT_LOAD_GENERATION || file !== EDIT_FILE || saved.expected_source_digest !== EDIT_SOURCE_DIGEST) return;
  await startRecompile();
}
async function startRecompile() {
  if (!EDIT_FILE) return;
  const target={params:compileParams(EDIT_FILE),generation:EDIT_LOAD_GENERATION};
  setEditMsg("recompile queued…");
  renderCompileLog(null);
  try {
    const res = await store.fetchJSON("/projection/recompile", { method: "POST",
      params: {...target.params, by: "author"} });
    if(target.params.file!==EDIT_FILE||target.generation!==EDIT_LOAD_GENERATION||target.params.compile_root!==compileParams(EDIT_FILE).compile_root||target.params.corpus!==_corpus())return;
    if (res.status === "absent" || res.absent_binary) {
      setEditMsg("recompile refused — " + (res.reason || "the tex toolchain is absent"), true);
      return;
    }
  } catch (e) { if(compileTargetCurrent(target))setEditMsg("recompile failed to queue: " + ((e && e.message) || e), true); return; }
  pollRecompile(target);
}
// #5/#6 — read the AUTHORITATIVE full log (not the 60-line tail): /review/compile-log parses
// main.log's ! error blocks + warnings, so a recoverable error that scrolls past the tail
// (the commonest LaTeX mistake, an undefined macro) surfaces even when latexmk exits 0.
async function fetchCompileLog(target = {params:compileParams(EDIT_FILE)}) {
  if (!EDIT_FILE) return null;
  try { return await store.fetchJSON("/review/compile-log", { params: { file: target.params.compile_root || target.params.file } }); }
  catch (e) { return null; }
}
// #8 — badge the reader when it is showing stale pages after a failed compile.
function markReaderStale(stale) {
  const existing = $("#art-stale-badge");
  if (!stale) { if (existing) existing.remove(); return; }
  if (existing) return;
  const pane = $("#art-pdf-pane");
  if (!pane) return;
  const badge = document.createElement("div");
  badge.id = "art-stale-badge"; badge.className = "art-stale-badge";
  badge.textContent = "showing the last successful build — the current compile failed";
  pane.insertBefore(badge, pane.firstChild);
}
function pollRecompile(target = {params:compileParams(EDIT_FILE),generation:EDIT_LOAD_GENERATION}) {
  clearInterval(RECOMPILE_TIMER);
  RECOMPILE_TIMER = setInterval(async () => {
    const current=()=>compileTargetCurrent(target);
    if(!current()){clearInterval(RECOMPILE_TIMER);RECOMPILE_TIMER=null;return;}
    let row;
    try { row = await store.fetchJSON("/projection/recompile", { params: target.params }); }
    catch (e) { return; }   // a transient poll miss — keep polling, never abandon silently
    if(!current())return;
    if (row.running) { setEditMsg("compiling…"); return; }
    clearInterval(RECOMPILE_TIMER); RECOMPILE_TIMER = null;
    if(row.reason_code){setEditMsg(row.reason+' '+(row.fix||''),true);return;}
    if (row.state === "error" || row.ok === false) {
      const view = await fetchCompileLog(target);
      if(!current())return;
      const n = (view && view.counts && view.counts.problems) || 0;
      setEditMsg(n ? ("compile error — " + n + " problem" + (n === 1 ? "" : "s") + " below")
                   : "compile error — see the log below", true);
      renderCompileLog(view && view.present ? view : (row.log_tail || ""));
      markReaderStale(true);                          // the reader still shows the last good build
    } else if (row.ok) {
      const view = await fetchCompileLog(target);
      if(!current())return;
      const c = (view && view.counts) || {};
      const errs = c.errors || 0, warns = c.warnings || 0;
      if (errs) {
        // never a false green: latexmk exits 0 on a recoverable error, so parse the log and
        // badge the error even at exit 0 (the error that scrolled past the recompile tail).
        setEditMsg("compiled with " + errs + " error" + (errs === 1 ? "" : "s") +
          (warns ? " · " + warns + " warning" + (warns === 1 ? "" : "s") : ""), true);
        renderCompileLog(view);
      } else if (warns) {
        setEditMsg("compiled ✓ · " + warns + " warning" + (warns === 1 ? "" : "s"));
        renderCompileLog(view);                       // the warnings are shown, the badge stays green
      } else {
        setEditMsg("compiled ✓" + (row.built_version_id ? " · built " + row.built_version_id : ""));
        renderCompileLog(null);
      }
      if (row.pdf) {EDIT_PDF_REL = row.pdf;EDIT_PDF_TARGET=target;}
      await hotReloadEditPdf(target);
      if(!current())return;
      await refreshVersions();
      if(!current())return;
      markReaderStale(false);
    }
    if(current())await ensureFollow();
  }, 900);
}
// #6 — lead with the ! error/warning rows (clickable jumps into the open file); the package-
// load noise sits behind a full-log fold. Accepts the structured /review/compile-log view or,
// as a fallback, a raw text tail (an l.NN scan). The jump lands in the currently open file;
// a marker that belongs to a different \input fragment is a plain known limitation.
function renderCompileLog(log) {
  const box = $("#art-compile-log");
  if (!box) return;
  if (!log) { box.innerHTML = ""; box.classList.remove("on"); return; }
  box.classList.add("on");
  if (typeof log === "object") {
    const signal = log.signal || [];
    const c = log.counts || {};
    let html = "";
    if (c.problems)
      html += "<div class='art-k art-log-count'>" + (c.errors || 0) + " error" +
        ((c.errors === 1) ? "" : "s") + " · " + (c.warnings || 0) + " warning" +
        ((c.warnings === 1) ? "" : "s") + " — click a line to jump the source</div>";
    for (const s of signal) {
      const sev = s.sev === "error" ? "is-bad" : "is-warn";
      if (s.line)
        html += "<div class='art-logrow' data-line='" + esc(String(s.line)) + "'>" +
          "<span class='hy-chip " + sev + "'>line " + esc(String(s.line)) + "</span>" +
          "<code>" + esc(cut(s.text, 120)) + "</code></div>";
      else
        html += "<div class='art-logsig'><span class='hy-chip " + sev + "'>" +
          (s.sev === "error" ? "error" : "warn") + "</span><code>" + esc(cut(s.text, 120)) + "</code></div>";
    }
    if (!signal.length) html += "<div class='art-dim'>no error or warning blocks in the log.</div>";
    if (log.full_tail)
      html += "<div class='art-log-full-h' data-role='log-full-toggle' title='the raw log tail — package paths and all'>▸ full log</div>" +
        "<div class='art-log-full' data-role='log-full'>" +
        String(log.full_tail).split("\n").filter((l) => l.trim()).map((l) =>
          "<div class='art-logline'>" + esc(cut(l, 160)) + "</div>").join("") + "</div>";
    box.innerHTML = html;
    return;
  }
  // fallback: a raw text tail — the ! / l.NN rows lead, the rest behind the fold.
  let lead = "", rest = "";
  for (const ln of String(log).split("\n")) {
    const m = ln.match(/^l\.(\d+)\b/);
    if (m) lead += "<div class='art-logrow' data-line='" + m[1] + "'>" +
      "<span class='hy-chip is-bad'>line " + esc(m[1]) + "</span><code>" + esc(cut(ln, 120)) + "</code></div>";
    else if (/^! /.test(ln)) lead += "<div class='art-logsig'><span class='hy-chip is-bad'>error</span><code>" +
      esc(cut(ln, 120)) + "</code></div>";
    else if (ln.trim()) rest += "<div class='art-logline'>" + esc(cut(ln, 160)) + "</div>";
  }
  box.innerHTML = (lead || "<div class='art-dim'>no line-numbered error parsed — the raw tail is below.</div>") +
    (rest ? "<div class='art-log-full-h' data-role='log-full-toggle'>▸ full log</div>" +
      "<div class='art-log-full' data-role='log-full'>" + rest + "</div>" : "");
}
async function hotReloadEditPdf(target = null) {
  const current=()=>!target||compileTargetCurrent(target);
  if(!current())return;
  const into = $("#art-reader");
  const prevTop = into ? into.scrollTop : 0;
  await loadReader(current);
  if(!current())return;
  if (into) into.scrollTop = prevTop;
}
let RESTORE_ARMED = null;
let RESTORE_GENERATION = 0;
async function armRestore(btn) {
  const vid = btn.dataset.restore;
  const file = btn.dataset.sourceFile;
  if (!file) { btn.textContent = "saved target unproved; inspect snapshot"; return; }
  if (!RESTORE_ARMED || RESTORE_ARMED.vid !== vid || RESTORE_ARMED.file !== file) {
    const generation = ++RESTORE_GENERATION;
    RESTORE_ARMED = null;
    $$(".art-restore").forEach((b) => { if (b !== btn) b.textContent = "restore"; });
    btn.textContent = "inspecting current target…";
    try {
      const observed = await readManuscriptSource({project:_corpus(),file,endpoint:CTX.tex_endpoint,transport:(path,options)=>store.fetchJSON(path,options)});
      if (generation !== RESTORE_GENERATION) return;
      if (!/^sha256:[0-9a-f]{64}$/.test(observed.expected_source_digest)) throw Error("No inspected target guard");
      RESTORE_ARMED = { vid, file, target: observed.file, digest: observed.expected_source_digest, selection:observed.selection_identity };
      btn.textContent = "confirm restore over inspected source ↺";
    } catch (e) { if (generation === RESTORE_GENERATION) btn.textContent = "inspect failed; restore unavailable"; }
    return;
  }
  const selected = RESTORE_ARMED;
  RESTORE_ARMED = null;
  btn.textContent = "restoring…";
  try {
    const res = await store.fetchJSON("/projection/restore", { method: "POST", params: {
      file: selected.target,corpus:_corpus(),...(selected.selection?{expected_selection:selected.selection}:{}),version_id: selected.vid, expected_source_digest: selected.digest } });
    requireSourceCompletion(res,{project:_corpus(),selectionIdentity:selected.selection});
    if (res.ok !== true || res.source_committed !== true || res.file !== selected.target || res.restored_from !== selected.vid || res.consumed_source_digest !== selected.digest) {
      throw Error("Restore acknowledgement does not identify the inspected selection");
    }
    btn.textContent = "source restored" + (res.version_id ? " → " + res.version_id : " · snapshot needs inspection");
    try {
      const history = await refreshVersions();
      if (history?.ok === false || res.maintenance_warnings?.length) btn.textContent += " · maintenance needs inspection";
    } catch (e) { btn.textContent += " · history refresh unavailable"; }
  } catch (e) { const effect=sourceEffectFromError(e,{project:_corpus(),selectionIdentity:selected.selection}); btn.textContent=effect?.message||e.message||"restore not confirmed; inspect current target again"; if(effect?.suppressRetry||e.sourceEffectUnverified)btn.disabled=true; }
}

function infoTag(txt) {
  return " <span class='hy-info' title='" + esc(txt) + "' tabindex='0'>ⓘ</span>";
}

// ── ANCHORED MARKS + MINIMAP (his 2026-07-23 author's pick) ─────────────────────
// "The information lives where it points." Each finding/comment resolves to a position
// in the RENDERED pdf through the SAME nodemap the hover/anchor already trust (zero extra
// network — no /projection/locate per finding, no compile): its own eq/float node region,
// else its section's first paragraph anchor (via the plan's node→section bridge), else the
// eq: tail of a compound section label. What no line can hold — a citation with no single
// location, a legacy section-name absent from the map — goes to the NAMED unanchored shelf,
// never silently dropped. Marks re-place after every render (loadReader's single producer
// hook); tops are a PERCENTAGE of the page wrap, so they track zoom/refit exactly.
const TRAY_KEY = "art-tray-open";          // the demoted lens' remembered fold
let MARKS = [];                            // clustered anchored marks {page,y0,members,top}
let UNANCHORED = [];                       // the shelf {fid,kind,cls,title,reason}
let SEC_FIRST = null, NODE2SEC = null, MARK_IDX_KEY = null, MARK_IDX_ENTRIES = null, MARK_IDX_PLAN = null;   // the anchor index (cached)
let _mmRaf = 0;

function _nmEntries() { const nm = NODEMAP[_corpus()]; return (nm && nm.present && nm.entries) ? nm.entries : null; }
function _firstPos(regions, kindFilter) {
  let best = null;
  for (const r of regions || []) {
    if (kindFilter && r.kind !== kindFilter) continue;
    if (r.page == null || typeof r.y0 !== "number") continue;
    if (!best || r.page < best.page || (r.page === best.page && r.y0 < best.y0))
      best = { page: r.page, y0: r.y0, y1: (typeof r.y1 === "number" ? r.y1 : r.y0),
               x0: r.x0, x1: r.x1, kind: r.kind, measured: r.width === "measured" };
  }
  return best;
}
// build (and cache until the nodemap/corpus changes) the two zero-network bridges:
//   SEC_FIRST : explicit source-section → its first paragraph occurrence (page,y0)   [from nm paragraphs]
//   NODE2SEC  : conceptric node → the plan section that carries it       [from PLAN.sections]
function _buildAnchorIndex() {
  const e = _nmEntries();
  const key = _corpus() + ":" + (e ? Object.keys(e).length : 0) + ":" + ((PLAN && PLAN.sections || []).length);
  if (MARK_IDX_KEY === key && MARK_IDX_ENTRIES === e && MARK_IDX_PLAN === PLAN && SEC_FIRST) return;
  SEC_FIRST = new Map(); NODE2SEC = new Map();
  if (e) for (const regs of Object.values(e)) for(const region of regs || []) {
    if(region.kind!=="paragraph"||!region.source_section)continue;
    const sec=region.source_section,fp=_firstPos([region],"paragraph");
    if(!fp)continue;
    const cur=SEC_FIRST.get(sec);
    if(!cur||fp.page<cur.page||(fp.page===cur.page&&fp.y0<cur.y0))SEC_FIRST.set(sec,fp);
  }
  for (const s of (PLAN && PLAN.sections) || [])
    for (const n of s.nodes_in_order || []) if (!NODE2SEC.has(n)) NODE2SEC.set(n, s.id);
  MARK_IDX_KEY = key; MARK_IDX_ENTRIES=e; MARK_IDX_PLAN=PLAN;
}
// resolve one finding to a rendered-pdf position, or null → the shelf. Priority is exact →
// coarse: own object region, then node→plan-section, then section-as-key/prefix/token/eq-tail,
// then a bare page anchor. Every branch reads only NODEMAP + PLAN (already loaded).
function resolveFindingAnchor(f) {
  _buildAnchorIndex();
  const e = _nmEntries();
  if (!e) return null;
  const node = (f.node && f.node !== "?") ? f.node : "";
  const sec = _secLabel(f.section);
  if (node && e[node]) { const regions=e[node],paragraphs=regions.filter(row=>row.kind==="paragraph"),occurrences=new Set(paragraphs.map(row=>JSON.stringify([row.source_file,row.source_section,row.occurrence])));if(occurrences.size>1)return null;const p = _firstPos(regions); if (p) return Object.assign(p, { how: "node", label: node }); }
  if (node && NODE2SEC.has(node) && SEC_FIRST.has(NODE2SEC.get(node)))
    { const s = NODE2SEC.get(node); return Object.assign({}, SEC_FIRST.get(s), { how: "node-sec", label: "§" + s }); }
  if (sec && e[sec]) { const p = _firstPos(e[sec]); if (p) return Object.assign(p, { how: "sec-key", label: sec }); }
  if (sec && SEC_FIRST.has(sec)) return Object.assign({}, SEC_FIRST.get(sec), { how: "sec-para", label: "§" + sec });
  for (const t of sec.split(/[,\s]+/)) { const tt = t.trim();
    if (tt && e[tt]) { const p = _firstPos(e[tt]); if (p) return Object.assign(p, { how: "sec-token", label: tt }); } }
  if (sec.indexOf(":") !== -1) { const tail = sec.split(":").pop();
    for (const c of [tail, "eq:" + tail]) if (e[c]) { const p = _firstPos(e[c]); if (p) return Object.assign(p, { how: "sec-eqtail", label: c }); } }
  if (sec && NODE2SEC.has(sec) && SEC_FIRST.has(NODE2SEC.get(sec)))
    { const s = NODE2SEC.get(sec); return Object.assign({}, SEC_FIRST.get(s), { how: "sec-node", label: "§" + s }); }
  const an = f.anchor;
  if (an && typeof an === "object" && an.paragraph && e[an.paragraph]) { const p = _firstPos(e[an.paragraph]); if (p) return Object.assign(p, { how: "para", label: an.paragraph }); }
  if (an && typeof an === "object" && an.page) return { page: an.page, y0: 24, y1: 24, how: "page", label: "p" + an.page, measured: false };
  if (f.page) return { page: f.page, y0: 24, y1: 24, how: "page", label: "p" + f.page, measured: false };
  return null;
}
function _markKindOf(f) {
  const k = f.kind || "";
  if (k === "comment" || k === "note" || k === "author-read") return { group: "comment", cls: "kind-comment", glyph: "¶" };
  const sev = f.cls === "hard" ? "sev-hard" : f.cls === "soft" ? "sev-soft" : "sev-deferred";
  return { group: "finding", cls: sev, glyph: f.cls === "hard" ? "!" : "" };
}
function _markTitle(f) {
  const g = composedGlance(f);
  return cut(g.absent ? (f.comment || kindInWords(f.kind)) : (g.glance || f.comment || kindInWords(f.kind)), 120);
}
function _shelfReason(f) {
  const k = f.kind || "";
  if (k.indexOf("citation") === 0) return "a citation — no single line in the paper to point at";
  if (k === "unlinked-reliance" || k === "crosslink-vague") return "diffuse across the argument — no single anchor";
  const sec = _secLabel(f.section);
  if (sec) return "section '" + cut(sec, 30) + "' has no anchor in the current map";
  return "no section or node the map can place";
}
function _sevRank(it) { return it.cls === "sev-hard" ? 3 : it.cls === "sev-soft" ? 2 : it.cls === "sev-deferred" ? 1 : 0; }
function _clusterPeek(c) {
  const lines = c.members.slice(0, 5).map((m) => (m.group === "object" ? "◆ " + (m.kind || "object") + " " + (m.objectRef || "")
    : (m.group === "comment" ? "¶ " : "• ") + (m.title || "")));
  if (c.members.length > 5) lines.push("+" + (c.members.length - 5) + " more here");
  return lines.join("\n");
}
// compute MARKS (clustered, anchored) + UNANCHORED (the named shelf) from the current board
// + nodemap. Object marks (measured equations/figures) ride as a quiet secondary layer — they
// are provenance-bearing and already measured, so the gutter reads even where findings are sparse.
function computeMarks() {
  MARKS = []; UNANCHORED = [];
  const items = [];
  let nFinding = 0, nComment = 0;
  if (BOARD) _allFindings(BOARD).forEach((f, i) => {
    const fid = f.id || (f.kind + "-" + i);
    const pos = resolveFindingAnchor(f);
    const mk = _markKindOf(f);
    if (pos) {
      if (mk.group === "comment") nComment++; else nFinding++;
      items.push({ page: pos.page, y0: pos.y0, y1: pos.y1, x0: pos.x0, group: mk.group, cls: mk.cls,
        glyph: mk.glyph, fid, title: _markTitle(f), how: pos.how, label: pos.label });
    } else {
      UNANCHORED.push({ fid, kind: f.kind || "note", cls: f.cls, title: _markTitle(f), reason: _shelfReason(f) });
    }
  });
  const e = _nmEntries();
  let nObject = 0;
  if (e) for (const [aid, regs] of Object.entries(e)) {
    const p = _firstPos((regs || []).filter((r) => (r.kind === "equation" || r.kind === "float") && r.width === "measured"));
    if (!p) continue;
    nObject++;
    items.push({ page: p.page, y0: p.y0, y1: p.y1, x0: p.x0, group: "object", cls: "kind-object", glyph: "◆",
      objectRef: aid, kind: p.kind, title: aid });
  }
  const byKey = new Map();
  for (const it of items) {
    const key = it.page + ":" + Math.round(it.y0 / 6);
    let c = byKey.get(key);
    if (!c) { c = { page: it.page, y0: it.y0, members: [] }; byKey.set(key, c); }
    c.members.push(it); if (it.y0 < c.y0) c.y0 = it.y0;
  }
  const RANK = { finding: 0, comment: 1, object: 2 };
  for (const c of byKey.values()) {
    c.members.sort((a, b) => (RANK[a.group] - RANK[b.group]) || (_sevRank(b) - _sevRank(a)));
    c.top = c.members[0];
    c.key = c.page + ":" + Math.round(c.y0 / 6);
    MARKS.push(c);
  }
  MARKS.sort((a, b) => (a.page - b.page) || (a.y0 - b.y0));
  try {
    window.__marks = { clusters: MARKS.length, findingsAnchored: nFinding, comments: nComment,
      objectMarks: nObject, unanchored: UNANCHORED.length,
      boardTotal: (BOARD && BOARD.counts && BOARD.counts.total) || 0 };
  } catch (e2) { /* no window */ }
}
// place the gutter marks: a slim overlay column on each rendered page's right edge, marks at
// their anchored y as a PERCENTAGE of the page height (survives zoom/refit). Rebuilt each call
// because renderPdf clears and re-creates the .art-page wraps.
function placeGutterMarks() {
  const reader = $("#art-reader");
  if (!reader) return;
  for (const wrap of $$(".art-page", reader)) {
    let g = wrap.querySelector(".art-gutter");
    if (!g) { g = document.createElement("div"); g.className = "art-gutter"; wrap.appendChild(g); }
    g.innerHTML = "";
    const pageNo = parseInt(wrap.dataset.page, 10);
    const ph = parseFloat(wrap.dataset.ph) || 792;
    for (const c of MARKS) {
      if (c.page !== pageNo) continue;
      const b = document.createElement("button");
      b.type = "button";
      b.className = "art-mark " + c.top.cls + (c.members.length > 1 ? " is-cluster" : "");
      b.style.top = (c.y0 / ph * 100).toFixed(3) + "%";
      b.dataset.markKey = c.key;
      b.title = _clusterPeek(c);
      b.innerHTML = c.members.length > 1 ? "<span class='art-mark-n'>" + c.members.length + "</span>"
                                          : esc(c.top.glyph || "");
      g.appendChild(b);
    }
  }
}
// the minimap: page boundaries as faint rules, a density tick per mark at its normalized
// document position, a live viewport window. Needs the pages laid out (offsetTop known).
function renderMinimap() {
  const mm = $("#art-minimap"), reader = $("#art-reader");
  if (!mm || !reader) return;
  const pages = $$(".art-page", reader);
  const total = reader.scrollHeight || 1;
  const geo = {};
  let html = "";
  for (const wrap of pages) {
    geo[wrap.dataset.page] = { top: wrap.offsetTop, h: wrap.offsetHeight, ph: parseFloat(wrap.dataset.ph) || 792 };
    html += "<div class='art-minimap-rule' style='top:" + (wrap.offsetTop / total * 100).toFixed(3) + "%'></div>";
  }
  for (const c of MARKS) {
    const g = geo[c.page];
    if (!g) continue;
    const docY = g.top + (c.y0 / g.ph) * g.h;
    html += "<div class='art-minimap-tick " + c.top.cls + (c.members.length > 1 ? " is-cluster" : "") +
      "' style='top:" + (docY / total * 100).toFixed(3) + "%'></div>";
  }
  html += "<div class='art-minimap-view' id='art-minimap-view'></div>";
  mm.innerHTML = html;
  renderShelf();
  updateMinimapViewport();
}
function updateMinimapViewport() {
  const reader = $("#art-reader"), view = $("#art-minimap-view");
  if (!reader || !view) return;
  const total = reader.scrollHeight || 1;
  view.style.top = (reader.scrollTop / total * 100).toFixed(3) + "%";
  view.style.height = Math.max(3, reader.clientHeight / total * 100).toFixed(3) + "%";
}
// the unanchored shelf — the count + a NAMED breakdown by kind; each kind opens the tray lens
// filtered to it (the capabilities re-homed, nothing hidden). Lives at the pdf pane's foot.
function renderShelf() {
  let host = $("#art-shelf");
  if (!host) { const pane = $("#art-pdf-pane"); if (!pane) return;
    host = document.createElement("div"); host.id = "art-shelf"; host.className = "art-shelf"; pane.appendChild(host); }
  const n = UNANCHORED.length;
  if (!n) { host.innerHTML = ""; host.classList.remove("on"); return; }
  const byKind = new Map();
  for (const u of UNANCHORED) byKind.set(u.kind, (byKind.get(u.kind) || 0) + 1);
  const rows = [...byKind.entries()].sort((a, b) => b[1] - a[1]);
  host.innerHTML =
    "<button type='button' class='art-shelf-chip' data-role='shelf-toggle' " +
      "title='findings with no single line to point at — named here, never dropped; click for the breakdown'>⚑ " +
      n + " unanchored</button>" +
    "<div class='art-shelf-list' data-role='shelf-list'>" +
      "<div class='art-shelf-h'>no line to point at — open one in the lens</div>" +
      rows.map(([k, c]) => "<button type='button' class='art-shelf-row' data-kind='" + esc(k) + "'>" +
        esc(k) + " <b>" + c + "</b></button>").join("") +
    "</div>";
}
// the mark's focus (item 3): navigation LANDS focus — scroll+flash the anchor line, then open
// the reading-width panel beside it (finding/comment → inspection; object → provenance).
function openMark(c) {
  if (!c) return;
  const top = c.top;
  scrollAndFlashPdf(c.page, (top.x0 != null ? top.x0 : 0), c.y0);
  retireHint();
  if (top.group === "object" && top.objectRef) { objectRefFor(top.objectRef, top.kind).then((ref) => openProvenance(ref)).catch(() => {}); return; }
  if (top.fid) openFindingInspection(top.fid);
}
function openMarkFromEl(el) {
  const key = el && el.dataset.markKey;
  const c = MARKS.find((m) => m.key === key);
  if (c) openMark(c);
}
// the tray, now a LENS (item 4): open it filtered to a kind, WITHOUT moving the paper.
function persistTray(open) { try { sessionStorage.setItem(TRAY_KEY, open ? "open" : "closed"); } catch (e) { /* private */ } }
function openTrayWithFilter(kind) {
  const sec = $("#art-tray-sec");
  if (sec) { sec.classList.add("open"); persistTray(true); }
  TRAY_FILTER = kind || "";
  renderTriagedTray();
  const inp = $("#art-tray-find"); if (inp) { inp.value = TRAY_FILTER; inp.focus(); }
  if (sec) sec.scrollIntoView({ block: "nearest", behavior: "smooth" });
}
// one refresh: compute the marks, place the gutter, chart the minimap. The single producer;
// hooked from loadReader (every render), loadTriagedTray (board change), and init.
function refreshMarks() {
  computeMarks();
  placeGutterMarks();
  renderMinimap();
}
function wireMinimap() {
  const mm = $("#art-minimap"), reader = $("#art-reader");
  if (mm && !mm.dataset.wired) {
    mm.dataset.wired = "1";
    let dragging = false;
    const scrollToY = (clientY, smooth) => {
      const rd = $("#art-reader"); if (!rd) return;
      const r = mm.getBoundingClientRect();
      const frac = Math.max(0, Math.min(1, (clientY - r.top) / r.height));
      rd.scrollTo({ top: frac * rd.scrollHeight, behavior: smooth ? "smooth" : "auto" });
    };
    mm.addEventListener("mousedown", (e) => { dragging = true; scrollToY(e.clientY, false); e.preventDefault(); });
    window.addEventListener("mousemove", (e) => { if (dragging) scrollToY(e.clientY, false); });
    window.addEventListener("mouseup", () => { dragging = false; });
  }
  if (reader && !reader.dataset.mmwired) {
    reader.dataset.mmwired = "1";
    reader.addEventListener("scroll", () => {
      if (_mmRaf) return;
      _mmRaf = requestAnimationFrame(() => { _mmRaf = 0; updateMinimapViewport(); });
    });
  }
}

// ── wiring ──────────────────────────────────────────────────────────────────────
function toggleRail() {
  const main = $("#art-main");
  const open = main.classList.toggle("rail-open");
  $("#art-rail").classList.toggle("open", open);
  if (open) renderRailFull();
  renderRailStrip();
}
// THE RECOMPOSITION (2026-07-22, his order — the front end burned down): the mode
// switch is dead. There is ONE reading surface — hover/anchor/annotate always on,
// judgment standing in the margin — and editing is an ACT: "open the source" joins
// the synctex-coupled split beside the paper; closing it returns to reading.
// R5 — the two most useful clauses only (the ¶ click-to-jump + the line-comment); the
// rest (objects-open-their-origin, cursor-jumps-the-pdf, ⌘/Ctrl-S) lives in the tour.
const HINT_TXT = {
  read: "hover a paragraph for its <b>¶ anchor</b> · click it to <b>comment on the line</b>",
  edit: "click a pdf paragraph to <b>jump the source</b> · click a line to <b>comment on it</b>",
};
function updateHint() {
  const h = $("#art-hint");
  if (!h || hintDone) return;
  h.innerHTML = HINT_TXT[MODE] || HINT_TXT.read;
}
function setMode(mode) {
  if (mode === MODE || !HINT_TXT[mode]) return;
  MODE = mode;
  const main = $("#art-main");
  main.dataset.mode = mode;
  const tg = $("#art-edit-toggle");
  if (tg) tg.textContent = mode === "edit" ? "fold the source" : "open the source";
  try { sessionStorage.setItem(POSTURE_KEY, mode); } catch (e) { /* private mode — not remembered */ }
  updateHint();
  if (mode === "edit") {
    restoreSplit();   // #8 — the remembered source|pdf ratio, restored with the posture
    const sv = $("#art-edit-save");
    if (sv && !sv.dataset.taught) { sv.dataset.taught = "1";
      sv.title = "save + recompile — the live loop (⌘/Ctrl-S also saves + recompiles)"; }
    const file = EDIT_FILE || (CTX.current_artefact && CTX.current_artefact.tex) || currentRevision().tex;
    if (!CM_VIEW || EDIT_FILE !== file) loadEditFile(file); else ensureFollow();
    if (!FOLLOW_TIMER) FOLLOW_TIMER = setInterval(ensureFollow, 6000);
    loadReader();   // may switch to EDIT_PDF_REL if a live compile already exists
  } else {
    if (FOLLOW_TIMER) { clearInterval(FOLLOW_TIMER); FOLLOW_TIMER = null; }
    loadReader();   // back to the server-resolved revision
  }
}
function wireDivider() {
  const div = $("#art-divider");
  if (!div || div.dataset.wired) return;
  div.dataset.wired = "1";
  let dragging = false;
  const move = (e) => {
    if (!dragging) return;
    const split = $("#art-split");
    if (!split) return;
    const rect = split.getBoundingClientRect();
    const narrow = window.matchMedia && window.matchMedia("(max-width:760px)").matches;
    const raw = window.TouchEvent && e instanceof TouchEvent ? e.touches[0] : e;
    let pct = narrow ? ((raw.clientY - rect.top) / rect.height) * 100
                      : ((raw.clientX - rect.left) / rect.width) * 100;
    pct = Math.max(20, Math.min(80, pct));
    split.style.setProperty("--split-pct", pct.toFixed(1) + "%");
  };
  div.addEventListener("mousedown", (e) => { dragging = true; div.classList.add("is-drag"); e.preventDefault(); });
  window.addEventListener("mousemove", move);
  window.addEventListener("mouseup", () => {
    if (!dragging) return;
    dragging = false; div.classList.remove("is-drag");
    // #8 — persist the split ratio (the folds already persist; mirror them).
    const split = $("#art-split");
    const pct = split && split.style.getPropertyValue("--split-pct");
    if (pct) { try { sessionStorage.setItem(SPLIT_KEY, pct); } catch (e) { /* not remembered */ } }
    refitReader();   // the drag settled — refit the pages to the new pane width
  });
}
// the pane breathes with the folds (his 2026-07-23 rails ruling): when the pdf pane's
// width settles somewhere new — a rail folded, the divider dragged, the window resized —
// the pages re-render to the new fit. The folds and the divider call refitReader()
// directly (deterministic); the observer only covers window/viewport resizes.
let RESIZE_T = null;
function refitReader() {
  clearTimeout(RESIZE_T);
  RESIZE_T = setTimeout(() => {
    const into = $("#art-reader");
    const last = parseInt((into && into.dataset.fitw) || "0", 10);
    if (!last || !PDFDOC) return;
    // ZOOM-aware, identical to renderPdf — else a fold at zoom≠1 re-renders to the wrong width.
    const base = Math.min(1400, (into.clientWidth || 800) - 8);
    const now = Math.max(140, Math.round(base * ZOOM));
    if (Math.abs(now - last) > 28) loadReader();
  }, 350);
}
function wireReaderResize() {
  const pane = $("#art-pdf-pane");
  if (!pane || pane.dataset.resized || typeof ResizeObserver === "undefined") return;
  pane.dataset.resized = "1";
  new ResizeObserver(refitReader).observe(pane);
}
// ── PDF ZOOM (his 2026-07-23 chair FAIL — the "criminal" one) ───────────────────
// setZoom clamps to 0.5–3, persists per session, and debounces the (costly) re-render so a
// held-down button or a wheel spin coalesces into one loadReader. The floating cluster lives
// in #art-pdf-pane — a SIBLING of #art-reader — so renderPdf's innerHTML clears never remove it.
let ZOOM_T = null;
function updateZoomReadout() {
  const r = document.querySelector(".art-zoom-pct");
  if (r) r.textContent = Math.round(ZOOM * 100) + "%";
}
function setZoom(z) {
  ZOOM = Math.max(0.5, Math.min(3, z));
  try { sessionStorage.setItem(ZOOM_KEY, String(ZOOM)); } catch (e) { /* not remembered */ }
  updateZoomReadout();
  clearTimeout(ZOOM_T);
  ZOOM_T = setTimeout(() => loadReader(), 260);
}
function wireZoom() {
  const pane = $("#art-pdf-pane");
  if (!pane || pane.dataset.zoomwired) return;
  pane.dataset.zoomwired = "1";
  try { const s = parseFloat(sessionStorage.getItem(ZOOM_KEY)); if (s) ZOOM = Math.max(0.5, Math.min(3, s)); }
  catch (e) { /* default 1 */ }
  const cluster = document.createElement("div");
  cluster.className = "art-zoom";
  cluster.innerHTML =
    "<button type='button' class='art-zoom-b' data-z='out' title='zoom out'>−</button>" +
    "<span class='art-zoom-pct' title='the reader zoom'>" + Math.round(ZOOM * 100) + "%</span>" +
    "<button type='button' class='art-zoom-b' data-z='in' title='zoom in'>+</button>" +
    "<button type='button' class='art-zoom-b art-zoom-fit' data-z='fit' title='fit the page to the pane'>fit</button>";
  pane.appendChild(cluster);
  cluster.addEventListener("click", (e) => {
    const b = e.target.closest("[data-z]"); if (!b) return;
    const z = b.dataset.z;
    if (z === "in") setZoom(ZOOM + 0.2);
    else if (z === "out") setZoom(ZOOM - 0.2);
    else setZoom(1);   // fit
  });
  const reader = $("#art-reader");
  if (reader) reader.addEventListener("wheel", (e) => {
    if (!(e.ctrlKey || e.metaKey)) return;   // Ctrl/⌘+wheel zooms; a bare wheel scrolls the reader
    e.preventDefault();
    setZoom(ZOOM + (e.deltaY < 0 ? 0.15 : -0.15));
  }, { passive: false });
}
// #8 — restore the remembered split ratio onto #art-split (mirrors the fold restores).
function restoreSplit() {
  const split = $("#art-split");
  if (!split) return;
  let pct = null;
  try { pct = sessionStorage.getItem(SPLIT_KEY); } catch (e) { /* default */ }
  if (pct) split.style.setProperty("--split-pct", pct);
}
function wireChrome() {
  const root = $("#art");
  wireReaderResponse();
  wireDivider();
  wireReaderResize();
  wireZoom();   // the pdf zoom cluster + Ctrl-wheel (the "criminal" no-zoom fix)
  wireMinimap();   // the whole-document minimap: click/drag to scroll, live viewport window
  // essence-on-hover for the node door: peek the node's essence inline WITHOUT stealing the
  // click (which navigates to /conceptric). Guarded so one hover = one fetch, not a storm.
  root.addEventListener("mouseover", (e) => {
    const nd = e.target.closest(".art-node");
    if (nd && nd.dataset.node) showEssence(nd.dataset.node);
  });
  document.addEventListener("keydown", (e) => {
    // #4 — the keyboard save reflex: Cmd/Ctrl-S saves and recompiles (never the browser's
    // save-page default). Taught in the save button title + the edit hint line.
    if (e.defaultPrevented) return;
    if ((e.metaKey || e.ctrlKey) && (e.key === "s" || e.key === "S")) {
      e.preventDefault();
      if (MODE === "edit") saveAndRecompile();
      return;
    }
    if (e.key !== "Escape") return;
    const root = $("#art");
    if (root && root.classList.contains("is-proving")) { closeProvenance(); return; }   // Esc leaves the provenance pane
    if (root && root.classList.contains("is-inspecting")) { closeInspection(); return; }
    if (root && root.classList.contains("is-diffing")) { closeDiff(); return; }   // P5 — Esc leaves the diff focus
    const a = $("#art-anchor");
    if (a && a.classList.contains("on")) { closeAnchor(); return; }
    const main = $("#art-main");
    if (main && main.classList.contains("rail-open")) { main.classList.remove("rail-open");
      $("#art-rail").classList.remove("open"); renderRailStrip(); }
  });
  root.addEventListener("click", async (e) => {
    if (e.target.closest(".rule-chip, .rule-cap")) return;   // shell.js owns the ✎ + capture
    if (e.target.closest("#art-rail-toggle")) { toggleRail(); return; }
    if (e.target.closest("#art-edit-toggle")) { setMode(MODE === "edit" ? "read" : "edit"); return; }
    if (e.target.closest("#art-margin-toggle")) {
      const main = $("#art-main");
      const folded = main.classList.toggle("margin-folded");
      const mt = $("#art-margin-toggle");
      if (mt) mt.textContent = folded ? "open the margin" : "fold the margin";
      try { sessionStorage.setItem(MARGIN_KEY, folded ? "folded" : "open"); } catch (err) { /* not remembered */ }
      refitReader();   // the fold is a known width-change moment — refit deterministically
      return;
    }
    // the source-pane \label affordance → the provenance pane (the same door as the reader)
    const lp = e.target.closest("[data-role='label-prov']");
    if (lp) { const host = $("#art-label-prov"); const label = host && host.dataset.label;
      if (label) { const ref = await objectRefFor(label, label.startsWith("eq:") ? "equation" : "float"); await openProvenance(ref); } return; }
    // the his-hand toggle → wash the author's own edited passages
    if (e.target.closest("[data-role='hishand-toggle']")) { toggleHisHand(); return; }
    // the anchor overlay (the comment thread) — folds open on demand; the comment banks visibly
    if (e.target.closest(".art-anchor-x")) { closeAnchor(); return; }
    const fh = e.target.closest(".art-fold-h"); if (fh) { toggleFold(fh.closest(".art-fold")); return; }
    const cb = e.target.closest("[data-role='cmt-bank']"); if (cb) { await bankThreadComment(cb); return; }
    // NB: a node chip is a REAL door now (.art-adoor, handled below) — clicking it NAVIGATES to
    // /conceptric. Its essence peek rides HOVER (wired below), not this click, so the door lands.
    const mo = e.target.closest(".art-map-offer");
    if (mo) { await rebuildNodemap(mo); return; }
    // the rail
    const open = e.target.closest(".art-open"); if (open) { e.preventDefault(); closeDiff(); RAILSEL = []; EDIT_PDF_REL = null; store.set({ version: open.dataset.open }); renderRailFull(); return; }
    const rst = e.target.closest(".art-restore"); if (rst) { await armRestore(rst); return; }
    if (e.target.closest("#art-do-diff")) { runDiff(e.target.closest("#art-do-diff")); return; }
    if (e.target.closest("#art-diff-x")) { closeDiff(); return; }
    // the unanchored shelf (the minimap's foot) — its NAMED breakdown; a kind opens the lens
    if (e.target.closest("[data-role='shelf-toggle']")) { const sh = $("#art-shelf"); if (sh) sh.classList.toggle("on"); return; }
    const sr = e.target.closest(".art-shelf-row");
    if (sr) { openTrayWithFilter(sr.dataset.kind); const sh = $("#art-shelf"); if (sh) sh.classList.remove("on"); return; }
    // the tray, now the filter LENS — its fold is remembered (item 4); opening it never moves the paper
    if (e.target.closest("#art-tray-bar")) { const s = $("#art-tray-sec"); const on = s.classList.toggle("open"); persistTray(on); return; }
    const dh = e.target.closest("#art-dism-h"); if (dh) { e.stopPropagation();
      const d = $("#art-dism"); const on = d.classList.toggle("open");
      dh.firstChild.textContent = (on ? "▾" : "▸") + " dismissed · " +
        ((DISMISS && DISMISS.counts && DISMISS.counts.dismissals) || 0) + (on ? " (showing)" : " (folded)"); return; }
    const ov = e.target.closest(".art-overrule"); if (ov) { e.stopPropagation(); await overrule(ov); return; }
    const gd = e.target.closest(".art-adoor"); if (gd) { e.preventDefault();
      const to = gd.dataset.goto; if (to) window.location.href = to; return; }
    // ACT 3 #4 — "comments must take me to them": a finding row's OWN body (not its
    // conceptric/storyboard door, handled above) lands the pdf pane on its section, in
    // every mode. (The companion source-pane jump rides the file-aware /projection/synctex
    // path above; /projection/locate-by-section doesn't name which fragment its line
    // belongs to, so the tray click stays plainly pdf-only rather than guessing a file.)
    // E4 #2 — opening a finding REALLOCATES: it claims the inspection area (its section-jump
    // is a door INSIDE the focus now, never a bare repaint). Dismissed rows carry no fid.
    const frow = e.target.closest("#art-tray-body .art-frow[data-fid]");
    if (frow && frow.dataset.fid) { openFindingInspection(frow.dataset.fid); return; }
    // edit — the live loop
    if (e.target.closest("#art-edit-save")) { saveAndRecompile(); return; }
    if (e.target.closest("#art-edit-recompile")) { startRecompile(); return; }
    const ft = e.target.closest("[data-role='log-full-toggle']");
    if (ft) { const full = $(".art-log-full"); if (full) { const on = full.classList.toggle("on");
      ft.textContent = (on ? "▾" : "▸") + " full log"; } return; }
    const lr = e.target.closest(".art-logrow");
    if (lr && lr.dataset.line) { await gotoSourceLine(EDIT_FILE, parseInt(lr.dataset.line, 10)); return; }
  });
  root.addEventListener("change", (e) => {
    const box = e.target.closest(".art-diffbox");
    if (box) {
      if (DIFF_OPEN) closeDiff({restoreFocus:false});
      const id = box.dataset.id;
      if (box.checked) { if (RAILSEL.length >= 2) { const drop = RAILSEL.shift(); const el = $(".art-diffbox[data-id='" + drop + "']"); if (el) el.checked = false; } RAILSEL.push(id); }
      else RAILSEL = RAILSEL.filter((x) => x !== id);
      $$(".hy-rail-row").forEach((r) => r.classList.toggle("is-sel", RAILSEL.includes(r.dataset.id)));
      updateDiffBar();
    }
  });
}

// E4 #1 — the altitude thread: when arrived from the cockpit's tension decision
// (?via=cockpit-tension), render a visible breadcrumb/return door NAMING the brief it came from.
// Returning navigates to the cockpit URL, which the cockpit banks and lands on the brief — the
// editor is an altitude of the one instrument, reached through a door that returns to where he was.
function renderEntryThread() {
  const host = $("#art-thread");
  if (!host) return;
  const via = new URLSearchParams(window.location.search || "").get("via");
  if (via !== "cockpit-tension") { host.hidden = true; host.innerHTML = ""; return; }
  const corpus = _corpus();
  host.hidden = false;
  host.innerHTML = "";
  const door = returnDoor("back to Grow — " + corpus + ", where you were",
    () => { window.location.href = "/conceptric?corpus=" + ec(corpus); });
  host.appendChild(door);
  const note = document.createElement("span");
  note.className = "art-thread-note";
  note.textContent = "you arrived from a manuscript-realignment decision — this is where the paper is read, judged, and edited.";
  host.appendChild(note);
}

export async function initArtefact() {
  injectStyle();   // the component atoms (§6.2), painted before the first render
  INSPECT_BUS = new HighlightBus(document);   // E4 — the editor's highlight bus (one per surface)
  try { CTX = await store.fetchJSON("/artefact/context"); }
  catch (e) { $("#art-reader").innerHTML = "<div class='art-msg'>could not resolve this project — <code>" + esc((e && e.message) || e) + "</code></div>"; return; }
  // F4 — Seed the resolved corpus: /artefact/context resolves the corpus (named or active);
  // seed it into the store so EVERY corpus-scoped join (nodemap, findings, dismissals, plan)
  // rides the SAME resolved corpus on BOTH addressings — a `file=` link that carries no
  // ?corpus= no longer falls through to a blank key and a dead anchor join (the F4 root fix).
  if (CTX.corpus && store.field("corpus") !== CTX.corpus) store.set({ corpus: CTX.corpus }, { replace: true });
  renderEntryThread();   // E4 #1 — the altitude thread, once the corpus is resolved
  const info = $("#art-reader-info");
  if (info) info.innerHTML = infoTag(CTX.pdf_endpoint + " → projection_viewer.py (registry.project_context)");
  wireChrome();
  // paint the resting POSTURE: the split by default (his promise: Overleaf-class), or the
  // session-remembered fold; the margin fold is remembered the same way.
  const mainEl = $("#art-main");
  if (mainEl) { mainEl.dataset.mode = MODE; }
  const posture = rememberedPosture();
  if (posture === "edit") setMode("edit"); else { if (mainEl) mainEl.dataset.mode = "read"; const tg = $("#art-edit-toggle"); if (tg) tg.textContent = "open the source"; }
  let marginFolded = false;
  try { marginFolded = sessionStorage.getItem(MARGIN_KEY) === "folded"; } catch (e) { /* open */ }
  if (marginFolded && mainEl) { mainEl.classList.add("margin-folded"); const mt = $("#art-margin-toggle"); if (mt) mt.textContent = "open the margin"; }
  // the tray is now a LENS, collapsed by default (item 4) — only its remembered "open" reopens it;
  // the whole-document minimap, not the tray, is now how judgment's location is read.
  try { if (sessionStorage.getItem(TRAY_KEY) === "open") { const s = $("#art-tray-sec"); if (s) s.classList.add("open"); } } catch (e) { /* private */ }
  updateHint();
  try { VERS = decorateVersionRows(await store.fetchJSON("/shared/versions")); } catch (e) { VERS = null; }
  store.subscribe(syncToRevision);
  renderRailStrip();
  lastRevKey = revKey(currentRevision());
  // judgment fills the margin CONCURRENTLY with the (slow) pdf render — the notebook
  // must never wait on the paper's paint.
  const trayReady = loadTriagedTray();
  await loadReader();
  await ensurePlan();
  await trayReady;
  openDeepLinkedFinding();   // #7 — ?finding=<id> opens that inspection cold (mirrors ?version=)
  openDeepLinkedObject();    // ?object=<id> opens its provenance pane cold (the same idiom)
}

// #7 — a finding deep link: ?finding=<id> opens its inspection cold, session-sticky like the
// other deep doors. It reaches ANY finding on the board (not only the rows the tray renders),
// so a Desk/cockpit route can land on one decision without hunting past the group cap.
function openDeepLinkedFinding() {
  let fid = null;
  try { fid = new URLSearchParams((window.location && window.location.search) || "").get("finding"); }
  catch (e) { return; }
  if (!fid || !BOARD) return;
  if (_findingByFid(fid)) openFindingInspection(fid);
}

if (typeof window !== "undefined") window.__artefactInit = initArtefact;
