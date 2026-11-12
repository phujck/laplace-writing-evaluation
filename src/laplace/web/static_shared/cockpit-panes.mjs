// cockpit-panes.mjs — the growth cockpit's pane logic (E3), a SHARED module.
//
// /conceptric's first engine surface (DESIGN_2026-07-22_the-interface-engine.md E/F): the
// resting DOM is the composed BRIEF plus one-line counts — no queue, ladder, or coverage node
// exists until a focus materialises it, and closing returns to the brief. The tension card opens
// to the decision altitude (the composed conflict → the four verbs → the consequence preview →
// the REGOAL confirm gate → commit with commentary), all driven by engine.mjs. Every payload is
// composed server-side (/growth/*); the client renders it verbatim and reconstructs no meaning.
// The ladder strip + queue headers + verb roster render FROM /surface/contract (conjugate views).
//
// All network rides store.fetchJSON (the one gateway). All colour is a hymn var.

import store from "/shared/store.mjs";
import { injectEngineCSS, createFocusState, HighlightBus, HoverLens, Reallocator, activate } from "/shared/engine.mjs";

const esc = (s) => String(s == null ? "" : s)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

// the composed brief prose carries the goal's inline $…$ verbatim (audit depth keeps the
// raw string). Render it through the shell's one KaTeX fence — the same auto-render the
// editor uses (conservative delimiters, throwOnError:false → a plain-text fallback where
// katex cannot parse). A no-op if the shell has not booted; the innerHTML is replaced whole
// on every render, so a single pass never double-renders an already-rendered span.
function paintMath(el) { try { if (el && window.renderMath) window.renderMath(el); } catch (_e) { /* math is a bonus, never a blocker */ } }

const COCKPIT_CSS = `
#cockpit-page{max-width:1180px;margin:0 auto;padding:18px 22px 120px}
@media(min-width:1400px){.ck-ctx{max-width:1000px;margin-inline:auto}}
.ck-ctx{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;margin:0 0 4px;padding-bottom:11px;border-bottom:1px solid var(--edge)}
.ck-ctx .ck-surface{font-family:var(--mono);font-size:12px;font-weight:700;color:var(--ink)}
.ck-ctx .ck-purpose{color:var(--ink2);font-size:12.5px}
/* THE BRIEF — the resting altitude: composed prose + counts, nothing else */
.ck-brief-prose{font-size:14px;line-height:1.65;color:var(--ink);margin:18px 0 6px;max-width:74ch}
.ck-brief-prose .ck-next{display:block;margin-top:8px;font-family:var(--mono);font-size:10.5px;color:var(--dim)}
.ck-counts{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0 6px}
.ck-count{display:inline-flex;align-items:center;gap:7px;cursor:pointer;background:var(--panel);border:1px solid var(--edge2);
  border-radius:9px;padding:8px 12px;font:inherit;color:var(--ink2);min-width:0}
.ck-count:hover{border-color:var(--accent);color:var(--ink)}
.ck-count:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.ck-count.is-open{border-color:var(--keystone);color:var(--ink);box-shadow:inset 0 0 0 1px var(--keystone)}
.ck-count .ck-cn{font-family:var(--mono);font-weight:700;color:var(--ink);font-size:14px}
.ck-count .ck-clabel{font-size:11.5px}
.ck-count.is-tension .ck-cn{color:var(--keystone)}
.ck-count.is-empty{opacity:var(--hy-zero-dim,.6);cursor:default}
/* the zero-count law (aligned to the engine's shared dimming idiom): a zero count reads
   dim through the token, not merely a faded ink — so an empty chip states its zero the
   same way the ladder/coverage zeros do. Rides var(--dim), so a shared zero-chip law lands
   consistent, never fought. */
.ck-count.is-empty .ck-cn{color:var(--dim)}
.ck-count.is-empty.is-teachable{cursor:pointer}
.ck-count.is-empty.is-teachable:hover{opacity:.85;border-color:var(--accent);color:var(--ink)}
/* ═══ THE SHAPE — the project, seeable at rest (his correction, 2026-07-22: the
   resting-state law was never absence-of-the-object). One panel: the ladder as a
   small connected strip with you-are-here lit, the coverage axes as worded tiles
   (zero axes stay red words, never bars), and — when one exists — the tension
   pinned IN the picture, where it pulls, opening to its ruling in place. ═══ */
.ck-shape{border:1px solid var(--edge2);border-radius:14px;background:var(--panel);
  padding:15px 17px 13px;margin:16px 0 4px;display:flex;flex-direction:column;gap:13px}
.ck-shape-h{font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.12em;
  color:var(--dim);font-weight:700;display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.ck-shape-h .sub{margin-left:auto;text-transform:none;letter-spacing:0;font-weight:400;font-size:9.5px}
.ck-shape-tension{display:flex;flex-direction:column;gap:4px;border:1px solid var(--keystone);
  border-left:3px solid var(--keystone);border-radius:10px;padding:10px 13px;cursor:pointer;
  background:color-mix(in srgb,var(--keystone) 6%,transparent)}
.ck-shape-tension:hover{background:color-mix(in srgb,var(--keystone) 11%,transparent)}
.ck-shape-tension:focus-visible{outline:2px solid var(--keystone);outline-offset:2px}
.ck-shape-tension .th{font-family:var(--mono);font-size:9px;font-weight:700;letter-spacing:.09em;
  text-transform:uppercase;color:var(--keystone)}
.ck-shape-tension .tg{font-size:12.5px;line-height:1.55;color:var(--ink)}
.ck-srungs{display:flex;align-items:stretch;gap:0;border:1px solid var(--edge);border-radius:10px;
  overflow:hidden;background:var(--bg);flex-wrap:wrap}
.ck-srung{flex:1 1 0;min-width:74px;padding:7px 10px;border-right:1px solid var(--edge);
  display:flex;flex-direction:column;gap:2px;cursor:pointer}
.ck-srung:last-child{border-right:none}
.ck-srung:hover{background:var(--panel2)}
.ck-srung .rn{font-family:var(--mono);font-size:10px;font-weight:700;color:var(--dim);letter-spacing:.04em}
.ck-srung .rs{font-family:var(--mono);font-size:8px;color:var(--dim);text-transform:uppercase;letter-spacing:.05em}
.ck-srung.is-here{background:color-mix(in srgb,var(--keystone) 9%,transparent)}
.ck-srung.is-here .rn{color:var(--keystone)}
.ck-srung.is-behind .rn{color:var(--ink2)}
.ck-shape-note{font-size:11px;color:var(--dim);line-height:1.5}
/* the tension station at rest — when none pulls, a quiet worded mark (fix 1a): what a
   tension is, that none is open, and — when history holds one — that the last was ruled
   and is readable. The station reads calm (dim edge), not urgent (keystone). */
.ck-shape-station{display:flex;flex-direction:column;gap:4px;border:1px dashed var(--edge2);
  border-radius:10px;padding:9px 13px;background:var(--bg)}
.ck-shape-station.is-readable{cursor:pointer}
.ck-shape-station.is-readable:hover{border-color:var(--accent)}
.ck-shape-station.is-readable:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.ck-shape-station .sh{font-family:var(--mono);font-size:9px;font-weight:700;letter-spacing:.09em;
  text-transform:uppercase;color:var(--dim)}
.ck-shape-station .sg{font-size:11.5px;line-height:1.55;color:var(--ink2)}
.ck-shape-station .sread{font-family:var(--mono);font-size:9.5px;color:var(--accent)}
.ck-saxes{display:flex;gap:8px;flex-wrap:wrap}
.ck-saxis{flex:1 1 150px;min-width:130px;border:1px solid var(--edge);border-radius:9px;
  background:var(--bg);padding:8px 11px;display:flex;flex-direction:column;gap:3px;cursor:pointer}
.ck-saxis:hover{border-color:var(--accent)}
.ck-saxis .an{font-family:var(--mono);font-size:10.5px;font-weight:700;color:var(--ink)}
.ck-saxis .aw{font-family:var(--mono);font-size:9.5px;color:var(--ink2)}
.ck-saxis.is-zero .aw{color:var(--bad)}
.ck-saxis.is-partial .aw{color:var(--warn)}
.ck-doors{display:flex;gap:9px;flex-wrap:wrap;margin-top:8px}
.ck-door{font-family:var(--mono);font-size:10.5px;color:var(--accent);text-decoration:none;border:1px solid var(--edge);
  border-radius:7px;padding:4px 10px;background:var(--bg)}
.ck-door:hover{border-color:var(--accent);color:var(--ink)}
/* the materialised zone — built on open, removed on close (never present at rest).
   A short reveal on open/close (fix 7): fade+slide, a stable min-height so the page
   below does not jump, reduced-motion honoured (no animation, instant). */
.ck-mat{margin-top:16px}
.ck-mat.is-open{min-height:120px}
.ck-mat.is-revealing{animation:ckReveal .22s ease both}
.ck-mat.is-closing{animation:ckConceal .16s ease both}
@keyframes ckReveal{from{opacity:0;transform:translateY(7px)}to{opacity:1;transform:none}}
@keyframes ckConceal{from{opacity:1;transform:none}to{opacity:0;transform:translateY(5px)}}
@media (prefers-reduced-motion:reduce){
  .ck-mat.is-revealing,.ck-mat.is-closing{animation:none}
  .ck-history-reveal{animation:none}
}
/* the ✎ mouth, node-scoped (fix 4): the shell owns .rule-chip/.rule-cap; the cockpit
   hosts just need to be flex so the quiet chip can sit at the row's end on hover. */
.ck-shape-tension,.ck-saxis,.ck-qrow{flex-wrap:wrap}
.ck-shape-tension .rule-cap,.ck-saxis .rule-cap,.ck-qrow .rule-cap{margin-top:6px}
/* the transient miss note (fix 3) — a cold ?gt= link to a ruled/missing tension lands here */
.ck-missnote{border:1px solid var(--warn);border-left:3px solid var(--warn);border-radius:10px;
  background:color-mix(in srgb,var(--warn) 7%,transparent);padding:11px 14px;margin:14px 0 4px;
  font-size:12px;line-height:1.6;color:var(--ink);animation:ckReveal .22s ease both}
.ck-missnote .mn-h{font-family:var(--mono);font-size:9px;font-weight:700;letter-spacing:.08em;
  text-transform:uppercase;color:var(--warn);display:block;margin-bottom:4px}
.ck-missnote .mn-read{font-family:var(--mono);font-size:10px;color:var(--accent);cursor:pointer;
  display:inline-block;margin-top:7px;border:1px solid var(--edge);border-radius:6px;padding:3px 9px;background:var(--bg)}
.ck-missnote .mn-read:hover{border-color:var(--accent)}
/* the empty-project TEACH (fix 5) — an unbriefable project states its absence and its doors */
.ck-teach{border:1px solid var(--edge2);border-radius:14px;background:var(--panel);padding:16px 18px;margin:16px 0 4px;
  display:flex;flex-direction:column;gap:11px}
.ck-teach .tc-h{font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.12em;color:var(--dim);font-weight:700}
.ck-teach .tc-reason{font-size:13px;line-height:1.65;color:var(--ink);max-width:74ch}
.ck-teach .tc-sub{font-family:var(--mono);font-size:9.5px;color:var(--dim);text-transform:uppercase;letter-spacing:.06em}
.ck-teach ul{margin:0;padding-left:18px;display:flex;flex-direction:column;gap:5px}
.ck-teach li{font-size:12px;line-height:1.55;color:var(--ink2)}
/* the reconciled tension read-only HISTORY (fix 1b) — the ruled tension, banked whole */
.ck-history{border:1px solid var(--edge2);border-radius:14px;background:var(--panel);overflow:hidden;margin-top:12px}
.ck-history-reveal{animation:ckReveal .22s ease both}
.ck-hist-head{padding:12px 16px;border-bottom:1px solid var(--edge);background:linear-gradient(180deg,color-mix(in srgb,var(--teal) 9%,transparent),transparent)}
.ck-hist-kind{font-family:var(--mono);font-size:10px;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:var(--teal)}
.ck-hist-title{font-size:14px;font-weight:660;color:var(--ink);margin-top:4px}
.ck-hist-body{padding:15px 16px;display:flex;flex-direction:column;gap:13px}
.ck-hist-body .ck-conflict .cw{display:block;margin-top:8px;color:var(--ink2);font-size:12px}
.ck-hist-verbs{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}
.ck-hist-verb{border:1px solid var(--edge2);border-radius:10px;background:var(--panel2);padding:10px 12px;display:flex;flex-direction:column;gap:4px}
.ck-hist-verb.is-ruled{border-color:var(--teal);background:color-mix(in srgb,var(--teal) 6%,transparent)}
.ck-hist-verb .hvn{font-family:var(--mono);font-size:11.5px;font-weight:700;color:var(--ink);display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.ck-hist-verb .hvc{font-size:10.5px;color:var(--ink2);line-height:1.5}
.ck-ruled-tag{font-family:var(--mono);font-size:8px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;
  color:var(--teal);border:1px solid var(--teal);border-radius:5px;padding:1px 6px}
.ck-hist-ruling{border:1px solid var(--teal);border-radius:11px;background:color-mix(in srgb,var(--teal) 5%,transparent);padding:13px 15px;display:flex;flex-direction:column;gap:7px}
.ck-hist-ruling .hr-h{font-family:var(--mono);font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:var(--teal);font-weight:700}
.ck-hist-ruling .hr-meta{font-family:var(--mono);font-size:9.5px;color:var(--dim)}
.ck-hist-ruling .hr-words{font-size:12px;line-height:1.65;color:var(--ink);border-left:2px solid var(--teal);padding-left:11px;white-space:pre-wrap}
.ck-hist-ruling .hr-goal{font-size:11.5px;line-height:1.55;color:var(--ink2)}
/* the queue row OPEN (fix 2) — a real button opening its working account + provenance in place */
.ck-qrow{cursor:pointer}
.ck-qrow[role='button']:hover{border-color:var(--accent)}
.ck-qrow[role='button']:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.ck-qopen{display:none;flex-direction:column;gap:9px;margin-top:9px;border-top:1px dashed var(--edge2);padding-top:9px}
.ck-qrow.is-open .ck-qopen{display:flex}
.ck-qworking{font-size:11.5px;line-height:1.6;color:var(--ink2);max-width:74ch}
.ck-qnodes{display:flex;flex-direction:column;gap:3px}
.ck-qnodes .qn-h{font-family:var(--mono);font-size:9px;text-transform:uppercase;letter-spacing:.06em;color:var(--dim);font-weight:700}
.ck-qnodes .qn-list{font-family:var(--mono);font-size:10px;color:var(--ink2);line-height:1.6;word-break:break-word}
.ck-qopen .ck-audit{margin-top:2px}
/* work-order attribution + empty state (fix 8) */
.ck-wo .wo-attr{font-family:var(--mono);font-size:9.5px;color:var(--dim);margin-top:5px}
.ck-wo .wo-attr.is-machine{color:var(--warn)}
.ck-empty-teach{font-size:12.5px;line-height:1.6;color:var(--ink2);border:1px dashed var(--edge2);border-radius:10px;padding:11px 14px;background:var(--bg)}
.ck-mat-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:11px}
.ck-mat-h{font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.1em;color:var(--dim);font-weight:700}
.ck-cards{display:flex;flex-direction:column;gap:10px;max-width:820px}
.ck-card{border:1px solid var(--edge2);border-radius:10px;background:var(--panel);padding:12px 14px;
  display:flex;flex-direction:column;gap:7px;cursor:pointer}
.ck-card:hover{border-color:var(--accent)}
.ck-card .ck-glance{font-size:12.5px;line-height:1.55;color:var(--ink)}
.ck-card .ck-open{font-family:var(--mono);font-size:9px;color:var(--dim);border-top:1px dashed var(--edge2);padding-top:7px}
.ck-card.is-tension{border-color:var(--keystone)}
.ck-axis,.ck-qrow,.ck-wo{border:1px solid var(--edge);border-radius:9px;background:var(--panel);padding:10px 13px}
.ck-qmeta{display:flex;gap:6px;margin-bottom:5px}
.ck-qtype,.ck-qstate{font-size:10.5px;padding:1px 7px;border-radius:4px;border:1px solid var(--edge);color:var(--ink2)}
.ck-qstate{color:var(--warn);border-color:color-mix(in srgb,var(--warn) 40%,transparent);background:color-mix(in srgb,var(--warn) 8%,transparent)}
.ck-axis .ax-h{font-family:var(--mono);font-size:11px;font-weight:700;color:var(--ink);display:flex;gap:8px;align-items:baseline}
.ck-axis .ax-state{margin-left:auto;font-family:var(--mono);font-size:9px;text-transform:uppercase;letter-spacing:.05em;
  padding:1px 6px;border-radius:4px;color:var(--bad);border:1px solid color-mix(in srgb,var(--bad) 40%,transparent);background:color-mix(in srgb,var(--bad) 8%,transparent)}
.ck-axis .ax-words{font-size:11.5px;color:var(--ink2);line-height:1.5;margin-top:6px}
/* the axis-gap routing door — a button that names what it banks; never pre-selected */
.ax-route{margin-top:9px;border-top:1px dashed var(--edge2);padding-top:9px;display:flex;flex-direction:column;gap:6px}
.ck-routebtn{align-self:flex-start;font:700 10.5px var(--mono);color:var(--bg);background:var(--accent);border:none;border-radius:7px;padding:5px 12px;cursor:pointer;max-width:100%}
.ck-routebtn:hover{background:var(--keystone)}
.ck-routebtn:focus-visible{outline:2px solid var(--keystone);outline-offset:2px}
.ck-routebtn[disabled]{opacity:.5;cursor:default}
.ax-conseq{font-size:11px;color:var(--ink2);line-height:1.5;max-width:72ch}
.ax-routedone{font-family:var(--mono);font-size:10px;color:var(--teal);line-height:1.5;max-width:72ch}
/* the ladder strip — rendered from /surface/contract states (conjugate views) */
.ck-ladder{display:flex;gap:0;border:1px solid var(--edge2);border-radius:11px;background:var(--panel);overflow:hidden;flex-wrap:wrap}
.ck-rung{flex:1 1 0;min-width:120px;padding:10px 12px;border-right:1px solid var(--edge);display:flex;flex-direction:column;gap:4px}
.ck-rung:last-child{border-right:none}
.ck-rung .rn{font-family:var(--mono);font-size:11px;font-weight:700;color:var(--ink2);letter-spacing:.04em}
.ck-rung.is-here .rn{color:var(--keystone)}
.ck-rung .rbar{font-family:var(--mono);font-size:8px;text-transform:uppercase;letter-spacing:.06em;color:var(--dim)}
.ck-rung .rdoes{font-size:10px;color:var(--dim);line-height:1.4}
/* the decision altitude — the composed conflict + the four verbs */
.ck-focus-pane{border:1px solid var(--keystone);border-radius:14px;background:var(--panel);overflow:hidden;margin-top:12px}
.ck-focus-head{padding:12px 16px;border-bottom:1px solid var(--edge);background:linear-gradient(180deg,color-mix(in srgb,var(--keystone) 10%,transparent),transparent)}
.ck-focus-kind{font-family:var(--mono);font-size:10px;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:var(--keystone)}
.ck-focus-title{font-size:14.5px;font-weight:680;color:var(--ink);margin-top:4px}
.ck-focus-body{padding:15px 16px;display:flex;flex-direction:column;gap:14px}
.ck-conflict{border:1px solid var(--edge2);border-radius:10px;background:var(--bg);padding:13px 15px;font-size:13px;line-height:1.6;color:var(--ink)}
.ck-conflict .cw{display:block;margin-top:8px;color:var(--ink2);font-size:12px}
.ck-verbs{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.ck-verb{position:relative;display:flex;flex-direction:column;gap:5px;border:1px solid var(--edge2);border-radius:11px;
  background:var(--panel2);padding:11px 12px;cursor:pointer;min-width:0}
.ck-verb:hover{border-color:var(--accent)}
.ck-verb:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.ck-verb .vn{font-family:var(--mono);font-size:12px;font-weight:700;color:var(--ink);display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.ck-verb .vresolves{font-family:var(--mono);font-size:9.5px;color:var(--dim);line-height:1.45}
.ck-lean{font-family:var(--mono);font-size:8px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;
  color:var(--keystone);border:1px dashed var(--keystone);border-radius:5px;padding:1px 6px}
.ck-verb.is-selected{border-color:var(--keystone);background:var(--panel);box-shadow:inset 0 0 0 1px var(--keystone)}
.ck-ruling{display:none;flex-direction:column;gap:12px;border:1px solid var(--keystone);border-radius:11px;background:color-mix(in srgb,var(--keystone) 5%,transparent);padding:14px 15px}
.ck-ruling.on{display:flex}
.ck-ruling .rl-h{font-family:var(--mono);font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:var(--keystone);font-weight:700}
.ck-conseq{font-size:12.5px;line-height:1.6;color:var(--ink)}
.ck-writes{font-family:var(--mono);font-size:10px;color:var(--dim)}
.ck-writes b{color:var(--teal)}
.ck-confirm{display:none;flex-direction:column;gap:7px;border:1px solid var(--warn);border-radius:9px;background:color-mix(in srgb,var(--warn) 6%,transparent);padding:11px 12px}
.ck-confirm.on{display:flex}
.ck-confirm .cf-h{font-family:var(--mono);font-size:9px;text-transform:uppercase;letter-spacing:.06em;color:var(--warn);font-weight:700}
.ck-confirm .cf-mark{font-family:var(--mono);font-size:9.5px;color:var(--dim);line-height:1.5}
.ck-confirm textarea{width:100%;min-height:74px;background:var(--bg);color:var(--ink);border:1px solid var(--edge2);border-radius:8px;padding:8px 10px;font:11.5px var(--mono);line-height:1.5;resize:vertical}
.ck-confirm textarea:focus{outline:none;border-color:var(--warn)}
.ck-confirm .cf-btn{align-self:flex-start;font:640 10.5px var(--mono);color:var(--bg);background:var(--warn);border:none;border-radius:7px;padding:5px 13px;cursor:pointer}
.ck-confirm.confirmed .cf-btn{background:var(--ok)}
.ck-commentary{display:flex;flex-direction:column;gap:6px}
.ck-commentary label{font-family:var(--mono);font-size:9px;text-transform:uppercase;letter-spacing:.07em;color:var(--dim);font-weight:700}
.ck-commentary .sub{font-family:var(--mono);font-size:9.5px;color:var(--dim)}
.ck-commentary textarea{width:100%;min-height:56px;background:var(--bg);color:var(--ink);border:1px solid var(--edge2);border-radius:9px;padding:9px 11px;font:11.5px var(--mono);line-height:1.5;resize:vertical}
.ck-commentary textarea:focus{outline:none;border-color:var(--keystone)}
.ck-commit-row{display:flex;align-items:center;gap:11px;flex-wrap:wrap}
.ck-commit{font:700 11px var(--mono);color:var(--bg);background:var(--keystone);border:none;border-radius:8px;padding:7px 15px;cursor:pointer}
.ck-commit[disabled]{opacity:.45;cursor:default}
.ck-commit-hint{font-family:var(--mono);font-size:9.5px;color:var(--dim);flex:1;min-width:150px}
.ck-done{font-family:var(--mono);font-size:10.5px;color:var(--teal)}
.ck-audit{font-family:var(--mono);font-size:9px;color:var(--dim);border-top:1px solid var(--edge);padding-top:10px}
.ck-audit summary{cursor:pointer;color:var(--dim)}
.ck-railcov{font-family:var(--mono);font-size:10px;color:var(--ink2);line-height:1.7}
.ck-railcov .z{color:var(--bad)}
/* the node-scoped COMMENT composer (a review note on the manuscript's feedback ledger,
   distinct from the ✎ interface fork) — on the hosts that carry a node (queue rows, axis
   tiles). Banks POST /corpus/feedback and echoes the banked row in place. */
.ck-comment{display:flex;flex-direction:column;gap:6px;margin-top:9px;border-top:1px dashed var(--edge2);padding-top:9px}
.ck-comment-h{font-family:var(--mono);font-size:9px;text-transform:uppercase;letter-spacing:.06em;
  color:var(--dim);font-weight:700;display:flex;flex-direction:column;gap:2px}
.ck-comment-h .sub{text-transform:none;letter-spacing:0;font-weight:400;font-size:9.5px;color:var(--dim)}
.ck-comment textarea{width:100%;min-height:44px;background:var(--bg);color:var(--ink);border:1px solid var(--edge2);
  border-radius:8px;padding:7px 9px;font:11.5px var(--mono);line-height:1.5;resize:vertical}
.ck-comment textarea:focus{outline:none;border-color:var(--accent)}
.ck-comment-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.ck-comment-bank{font:700 10.5px var(--mono);color:var(--bg);background:var(--accent);border:none;border-radius:7px;padding:5px 12px;cursor:pointer}
.ck-comment-bank:hover{background:var(--keystone)}
.ck-comment-bank[disabled]{opacity:.5;cursor:default}
.ck-comment-msg{font-family:var(--mono);font-size:9.5px;color:var(--ink2)}
.ck-comment-echo{display:flex;flex-direction:column;gap:5px}
.ck-comment-echoed{border:1px solid var(--teal);border-radius:8px;background:color-mix(in srgb,var(--teal) 6%,transparent);
  padding:7px 10px;display:flex;flex-direction:column;gap:3px}
.ck-comment-echoed-meta{font-family:var(--mono);font-size:9px;color:var(--dim)}
.ck-comment-echoed-text{font-size:11.5px;line-height:1.55;color:var(--ink)}
@media (max-width:900px){.ck-verbs{grid-template-columns:1fr}}
`;

function injectCockpitCSS() {
  if (typeof document === "undefined" || document.getElementById("ck-components")) return;
  const st = document.createElement("style"); st.id = "ck-components"; st.textContent = COCKPIT_CSS;
  document.head.appendChild(st);
}

// ── module state ───────────────────────────────────────────────────────────────
let CORPUS = null;
let BRIEF = null;
let CONTRACT = null;
const CACHE = {};                    // kind -> door payload
const SELECTION = {};                // gt_id -> { verb } (restore-on-close, B.3)
let STATE = createFocusState("index");
let BUS = null, LENS = null, REALLOC = null;
let OPEN_MAT = null;                  // the materialised chip kind, or null (brief base altitude)

// ═══════════════ BOOT ═══════════════
export async function initCockpit() {
  injectEngineCSS(); injectCockpitCSS();
  BUS = new HighlightBus(document);
  LENS = new HoverLens();
  if (!store.field("corpus")) store.set({ corpus: "paper_falqon" }, { replace: true });
  CORPUS = store.field("corpus");
  const root = $("#eng-root");
  REALLOC = new Reallocator(root, STATE, BUS);
  store.subscribe((s) => { const c = s.selection.corpus; if (c && c !== CORPUS) { CORPUS = c; STATE = createFocusState("index"); REALLOC.state = STATE; load(); } });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") { if (REALLOC.pinned) REALLOC.close(); else closeMaterialised(); } });
  await load();
  await applyEntry();
}

async function load() {
  CORPUS = store.field("corpus");
  BRIEF = await store.fetchJSON("/growth/brief").catch(() => null);
  renderBrief();
}

// ═══════════════ THE BRIEF — the resting altitude: the SHAPE, captioned ═══════════════
// His correction (2026-07-22): the resting state is the project's shape, SEEABLE — the
// ladder and coverage as a small designed picture with the tension pinned where it pulls —
// never counts alone, never an inventory. Detail still materialises on open.
function renderBrief() {
  const brief = $(".eng-brief"); if (!brief) return;
  OPEN_MAT = null;
  // the empty-project TEACH (fix 5): a project the surface cannot brief states its
  // absence in words, what GROW would show, and the doors that still work — never one
  // bare sentence. The server serves this composed when the corpus is unbriefable; a
  // hard null (a failed read) falls back to a plain teach that still names the door.
  if (!BRIEF || BRIEF.empty) { renderTeach(brief); return; }
  const g = (BRIEF.brief && BRIEF.brief.glance) || "";
  const c = BRIEF.counts || {};
  brief.innerHTML =
    "<div class='ck-brief-prose' data-role='brief-prose'>" + esc(g) + "</div>" +
    "<div class='ck-missnote-host' id='ck-missnote'></div>" +
    "<div class='ck-shape' id='ck-shape'></div>" +
    "<div class='ck-counts'>" +
      countChip("queue", c.queue, "below the floor", c.queue ? "" : "is-empty") +
      // fix 8: the work-orders chip is NEVER inert — even at zero it opens to teach how an
      // order gets here (dimmed but openable), so it is never wordless.
      countChip("work-orders", c.work_orders, "work order" + (c.work_orders === 1 ? "" : "s"), c.work_orders ? "" : "is-empty is-teachable") +
    "</div>" +
    "<div class='ck-doors'>" +
      "<a class='ck-door' href='/conceptric/map?corpus=" + encodeURIComponent(CORPUS) + "'>read the stock — the graded descent →</a>" +
    "</div>" +
    "<div class='ck-mat' id='ck-mat'></div>";
  wireBrief();
  paintMath($(".ck-brief-prose", brief));
  renderShape();
}

// the empty-project TEACH (fix 5) — server-composed when reachable, else a plain fallback
// that still names the surface, the absence, and the stock-map door (never dead-ends).
function renderTeach(brief) {
  const g = (BRIEF && BRIEF.brief && BRIEF.brief.glance) || "";
  const reason = (BRIEF && BRIEF.reason) || "";
  const would = (BRIEF && BRIEF.would_show) || [];
  const doors = (BRIEF && BRIEF.doors) || [];
  const mapHref = "/conceptric/map?corpus=" + encodeURIComponent(CORPUS);
  const doorLinks = (doors.length
    ? doors.map((d) => "<a class='ck-door' href='" + esc(d.href || mapHref) + "'>" + esc(d.label || "read the stock map") + " →</a>").join("")
    : "<a class='ck-door' href='" + mapHref + "'>read the stock — the graded descent →</a>");
  brief.innerHTML =
    "<div class='ck-brief-prose' data-role='brief-prose'>" +
      esc(g || ("There is no growth brief for this project — the growth surface has nothing to gauge here yet.")) + "</div>" +
    "<div class='ck-teach'>" +
      "<div class='tc-h'>GROW · the growth cockpit</div>" +
      (reason ? "<div class='tc-reason'>" + esc(reason) + "</div>" : "") +
      "<div class='tc-sub'>what GROW would show once this project is on the surface</div>" +
      "<ul>" + (would.length ? would : [
        "the SHAPE — the ladder position and the coverage axes measured against the goal",
        "any open tension pinned where it pulls, opening to the four verbs for your ruling",
        "the queue of requirements below the floor, and the open work orders",
      ]).map((w) => "<li>" + esc(w) + "</li>").join("") + "</ul>" +
      "<div class='tc-sub'>the doors that still work</div>" +
      "<div class='ck-doors'>" + doorLinks + "</div>" +
    "</div>";
  paintMath(brief.querySelector(".ck-brief-prose"));
}

// ── THE SHAPE (the picture at rest) ────────────────────────────────────────────
// Server truths only: the ladder rungs from /surface/contract (the law), the current
// rung from the brief, the axes from /growth/coverage (worded, zeros red), the open
// tensions from /growth/tensions — each tension a keystone mark IN the picture that
// opens to its ruling in place. Every read degrades to a stated absence.
async function renderShape() {
  const host = $("#ck-shape"); if (!host) return;
  const c = (BRIEF && BRIEF.counts) || {};
  const state = (BRIEF && BRIEF.state) || {};
  const wantTensions = (c.tensions || 0) > 0;
  const [contract, coverage, tensions] = await Promise.all([
    CONTRACT ? Promise.resolve(CONTRACT)
      : store.fetchJSON("/surface/contract", { inject: [], params: { surface: "conceptric" } }).catch(() => null),
    CACHE.coverage ? Promise.resolve(CACHE.coverage)
      : store.fetchJSON("/growth/coverage").catch(() => null),
    wantTensions
      ? (CACHE.tensions ? Promise.resolve(CACHE.tensions) : store.fetchJSON("/growth/tensions").catch(() => null))
      : Promise.resolve(null),
  ]);
  if (contract) CONTRACT = contract;
  if (coverage) CACHE.coverage = coverage;
  if (tensions) CACHE.tensions = tensions;
  if (!$("#ck-shape")) return;                    // the brief re-rendered while we read
  const here = state.state || null;
  const states = (CONTRACT && CONTRACT.states) || [];
  const hereIdx = states.findIndex((s) => s.name === here);
  const rungs = states.length
    ? "<div class='ck-srungs'>" + states.map((s, i) =>
        "<div class='ck-srung" + (s.name === here ? " is-here" : (hereIdx >= 0 && i < hereIdx ? " is-behind" : "")) +
          "' data-shape='ladder' tabindex='0' role='button'>" +
          "<span class='rn'>" + esc(s.name) + (s.name === here ? " ●" : "") + "</span>" +
          "<span class='rs'>" + esc(s.bar || "") + "</span></div>").join("") + "</div>" +
      (!here ? "<div class='ck-shape-note'>" +
        (state.pre_ladder
          ? "This project was grown before the ladder — the strip is the law a re-pour would climb, not a position it holds."
          : "Not on the ladder yet — the strip is what birth onto it would open.") + "</div>" : "")
    : "<div class='ck-shape-note'>the ladder law is unreadable right now — open the counts below for the plain reads.</div>";
  const axes = (CACHE.coverage && CACHE.coverage.axes) || [];
  const axisTiles = axes.length
    ? "<div class='ck-saxes'>" + axes.map((a) => {
        const zero = a.total && !a.covered;
        const cls = zero ? "is-zero" : (a.covered < a.total ? "is-partial" : "");
        // fix 6: a zero tile names the scale — "0 of N — measured zero", never the bare word.
        const words = zero ? "0 of " + a.total + " — measured zero" : a.covered + " of " + a.total + " covered";
        return "<div class='ck-saxis " + cls + "' data-shape='coverage' data-axis='" + esc(a.axis) + "' tabindex='0' role='button'>" +
          "<span class='an'>" + esc(a.axis) + "</span><span class='aw'>" + esc(words) + "</span></div>";
      }).join("") + "</div>"
    : "";
  const tRows = wantTensions ? ((CACHE.tensions && CACHE.tensions.tensions) || []) : [];
  // the tension station — one station always present (fix 1). When a live tension pulls it
  // is pinned exactly where it sits (1c); when none does, a calm worded mark says what a
  // tension is and — when banked history holds a ruled one (BRIEF.reconciled) — that the
  // last was ruled and is readable (1a/1b). No fabricated row when nothing is open.
  const reconciled = !!(BRIEF && BRIEF.reconciled);
  const tensionMarks = tRows.length
    ? tRows.map((t) =>
        "<div class='ck-shape-tension' data-gt='" + esc(t.id) + "' data-signature='" + esc(t.signature || "") +
          "' tabindex='0' role='button'>" +
          "<span class='th'>a tension pulls here — your call</span>" +
          "<span class='tg'>" + esc((t.composed && t.composed.glance) || "") + "</span></div>").join("")
    : ("<div class='ck-shape-station" + (reconciled ? " is-readable" : "") + "' data-role='tension-station'" +
        (reconciled ? " tabindex='0' role='button'" : "") + ">" +
        "<span class='sh'>tensions · your call</span>" +
        "<span class='sg'>A tension is a drift the machine cannot rule on its own — it pins here for your ruling when one opens. " +
          (reconciled
            ? "None is open now; the last one was ruled."
            : "None is open now.") + "</span>" +
        (reconciled ? "<span class='sread'>read the ruled tension — its verbs and how it was ruled →</span>" : "") +
      "</div>");
  host.innerHTML =
    "<div class='ck-shape-h'>the project's shape" +
      "<span class='sub'>the ladder · coverage vs the goal" + (tRows.length ? " · the open call" : " · the tension station") + "</span></div>" +
    tensionMarks + rungs + axisTiles;
  wireShape(tRows, axes);
}

function wireShape(tRows, axes) {
  const R = (typeof window !== "undefined" && window.HymnShell && window.HymnShell.hyRule) || null;
  // fix 4: the node-scoped ✎ mouth — attach to the tension marks and axis tiles so a rule
  // banks scoped to the claim it is about (ctx names the node); the chip appears on hover.
  const attach = (el, node, extra) => {
    if (!R || !R.attach || !el) return;
    try { R.attach(el, Object.assign({ surface: "conceptric", project: CORPUS, node }, extra || {})); }
    catch (_e) { /* the mouth is a bonus atom — never load-bearing */ }
  };
  // the resting tension station reads its ruled history in place (fix 1b)
  const station = $(".ck-shape-station.is-readable[data-role='tension-station']");
  if (station) activate(station, (e) => {
    if (e && e.target && e.target.closest(".rule-chip, .rule-cap")) return;
    materialise("history");
  });
  // a tension opens to its ruling IN PLACE (the pin), from where it sits in the picture;
  // hovering it reveals the working account in the lens (geometrically stable)
  $$(".ck-shape-tension[data-gt]").forEach((el) => {
    const row = tRows.find((t) => t.id === el.dataset.gt) || {};
    el.addEventListener("mouseenter", () => LENS.show(el,
      "<div class='lens-h'>working — the causal account</div><div>" +
      esc((row.composed && row.composed.working) || "") + "</div>"));
    el.addEventListener("mouseleave", () => LENS.hide());
    activate(el, (e) => {
      if (e && e.target && e.target.closest(".rule-chip, .rule-cap")) return;   // the ✎ owns its clicks
      LENS.hide(); openTension(el.dataset.gt);
    });
    attach(el, row.node_id || el.dataset.gt, { title: "tension · " + (row.signature || el.dataset.gt), kind: "tension" });
  });
  // a rung opens the full ladder account; an axis opens the coverage detail (its rows,
  // routing doors included) — the picture is the door to its own depths
  $$("[data-shape='ladder']").forEach((el) => activate(el, () => materialise("ladder")));
  $$(".ck-saxis[data-shape='coverage']").forEach((el) => {
    const row = axes.find((a) => a.axis === el.dataset.axis) || {};
    el.addEventListener("mouseenter", () => LENS.show(el,
      "<div class='lens-h'>" + esc(el.dataset.axis) + " — vs the goal</div>" +
      "<div>" + esc((row.composed && row.composed.glance) || "") + "</div>"));
    el.addEventListener("mouseleave", () => LENS.hide());
    activate(el, (e) => {
      if (e && e.target && e.target.closest(".rule-chip, .rule-cap")) return;   // the ✎ owns its clicks
      LENS.hide(); materialise("coverage");
    });
    attach(el, "coverage:" + el.dataset.axis, { title: "coverage · " + el.dataset.axis, kind: "coverage-axis" });
  });
}

function countChip(kind, n, label, cls) {
  const num = n == null ? "" : "<span class='ck-cn'>" + n + "</span>";
  const inert = cls.indexOf("is-empty") >= 0 && cls.indexOf("is-teachable") < 0;
  return "<button type='button' class='ck-count " + cls + "' data-materialize='" + kind + "' " +
    (inert ? "aria-disabled='true' " : "") + ">" + num +
    "<span class='ck-clabel'>" + label + "</span></button>";
}

function wireBrief() {
  $$(".ck-count[data-materialize]").forEach((chip) => {
    // an empty chip is inert UNLESS it is teachable (fix 8: an empty work-orders chip
    // still opens to its instructive empty state).
    if (chip.classList.contains("is-empty") && !chip.classList.contains("is-teachable")) return;
    activate(chip, () => materialise(chip.dataset.materialize));
  });
}

// ═══════════════ MATERIALISE — build the object-set on open (E) ═══════════════
const WHERE_KEY = "ck-where";
function persistWhere() {
  try {
    if (typeof sessionStorage === "undefined") return;
    sessionStorage.setItem(WHERE_KEY, JSON.stringify({ corpus: CORPUS, mat: OPEN_MAT || null,
      gt: (REALLOC && REALLOC.pinned && REALLOC.pinned.id) || null }));
  } catch (e) { /* private mode - stickiness silently degrades */ }
}
async function applyEntry() {
  const q = new URLSearchParams(typeof location !== "undefined" ? location.search : "");
  const open = (q.get("open") || "").trim();
  const gt = (q.get("gt") || "").trim();
  if (gt) { await openTension(gt); return; }         // a deep link pre-pins (B.5) - no lobby tax
  if (open) { await materialise(open); return; }
  let where = null;
  try { where = JSON.parse((typeof sessionStorage !== "undefined" && sessionStorage.getItem(WHERE_KEY)) || "null"); }
  catch (e) { where = null; }
  if (where && where.corpus === CORPUS) {            // returning hot lands where he was
    if (where.gt) { await openTension(where.gt); return; }
    if (where.mat) await materialise(where.mat);
  }
}
let MAT_CLOSE_TIMER = null;
function prefersReducedMotion() {
  try { return typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches; }
  catch (_e) { return false; }
}
// fix 7: the materialised zone reveals on open — fade+slide, a stable min-height so the
// page below does not jump, reduced-motion honoured (the class is a no-op animation there).
function revealMat(mat) {
  if (!mat) return;
  mat.classList.add("is-open"); mat.classList.remove("is-closing", "is-revealing");
  if (prefersReducedMotion()) return;
  void mat.offsetWidth;                       // restart the animation on re-open
  mat.classList.add("is-revealing");
}
async function materialise(kind) {
  const mat = $("#ck-mat"); if (!mat) return;
  if (MAT_CLOSE_TIMER) { clearTimeout(MAT_CLOSE_TIMER); MAT_CLOSE_TIMER = null; }
  if (OPEN_MAT === kind) { closeMaterialised(); return; }
  OPEN_MAT = kind;
  $$(".ck-count").forEach((c) => c.classList.toggle("is-open", c.dataset.materialize === kind));
  BUS.clear();
  revealMat(mat);
  mat.innerHTML = "<div class='ck-mat-head'><span class='ck-mat-h'>materialising " + esc(kind) + "…</span></div>";
  persistWhere();
  if (kind === "tensions") return matTensions(mat);
  if (kind === "queue") return matQueue(mat);
  if (kind === "coverage") return matCoverage(mat);
  if (kind === "work-orders") return matWorkOrders(mat);
  if (kind === "ladder") return matLadder(mat);
  if (kind === "history") return matHistory(mat);
}
function closeMaterialised() {
  const mat = $("#ck-mat");
  OPEN_MAT = null;
  persistWhere();
  $$(".ck-count").forEach((c) => c.classList.remove("is-open"));
  BUS.clear();
  if (!mat) return;
  const clear = () => { mat.innerHTML = ""; mat.classList.remove("is-open", "is-closing", "is-revealing"); };
  if (prefersReducedMotion() || !mat.innerHTML) { clear(); return; }
  mat.classList.remove("is-revealing"); mat.classList.add("is-closing");
  MAT_CLOSE_TIMER = setTimeout(() => { MAT_CLOSE_TIMER = null; if (OPEN_MAT === null) clear(); }, 170);
}
function matHead(title) {
  return "<div class='ck-mat-head'><span class='ck-mat-h'>" + esc(title) + "</span>" +
    "<button type='button' class='ck-door' data-role='mat-close'>← back to the brief</button></div>";
}
function wireMatClose(mat) { const b = mat.querySelector("[data-role='mat-close']"); if (b) activate(b, () => closeMaterialised()); }

async function matTensions(mat) {
  const data = CACHE.tensions || (CACHE.tensions = await store.fetchJSON("/growth/tensions").catch(() => ({ tensions: [] })));
  const rows = data.tensions || [];
  mat.innerHTML = matHead("tensions · " + rows.length) +
    "<div class='ck-cards'>" + (rows.length ? rows.map(tensionCard).join("")
      : "<div class='ck-brief-prose'>no open tension on this project.</div>") + "</div>";
  wireMatClose(mat);
  $$(".ck-card.is-tension", mat).forEach((card) => {
    const row = rows.find((t) => t.id === card.dataset.gt) || {};
    const working = (row.composed && row.composed.working) || "";
    // hover REVEALS: the working account in the fixed lens — geometrically stable, no reflow.
    card.addEventListener("mouseenter", () => LENS.show(card, "<div class='lens-h'>working — the causal account</div><div>" + esc(working) + "</div>"));
    card.addEventListener("mouseleave", () => LENS.hide());
    activate(card, () => { LENS.hide(); openTension(card.dataset.gt); });
  });
}
function tensionCard(row) {
  const g = (row.composed && row.composed.glance) || "";
  return "<div class='ck-card is-tension' data-gt='" + esc(row.id) + "' data-signature='" + esc(row.signature || "") + "' tabindex='0' role='button'>" +
    "<div class='ck-glance'>" + esc(g) + "</div>" +
    "<div class='ck-open'>open → the composed conflict and the four verbs, as the work area</div></div>";
}

async function matQueue(mat) {
  const data = CACHE.queue || (CACHE.queue = await store.fetchJSON("/growth/queue").catch(() => ({ rows: [] })));
  const rows = data.rows || [];
  mat.innerHTML = matHead("below the floor · " + rows.length) +
    "<div class='ck-cards'>" + (rows.length ? rows.map(queueRowHTML).join("")
      : "<div class='ck-brief-prose'>nothing below the floor.</div>") + "</div>";
  wireMatClose(mat);
  wireRouteButtons(mat);
  wireQueueRows(mat, rows);
  wireCommentComposers(mat);
}
// fix 2: every queue row is a REAL button. Clicking it opens, in place, its composed
// working account and its audit provenance (the same pin idiom the tension cards use).
// A routable row keeps its axis-gap door; a non-routable demand surfaces its own nodes
// and an in-place ✎/comment (via the node-scoped mouth) — no row is a dead end.
function queueRowHTML(r) {
  const nodes = r.node_ids || [];
  const routable = !!r.route;
  const nodesBlock = (!routable && nodes.length)
    ? "<div class='ck-qnodes'><span class='qn-h'>the nodes it names</span>" +
        "<span class='qn-list'>" + nodes.map((n) => esc(String(n))).join(" · ") + "</span></div>"
    : "";
  return "<div class='ck-qrow' data-demand='" + esc(r.demand_id || "") + "' tabindex='0' role='button' " +
      "aria-expanded='false'>" +
    "<div class='ck-qmeta'><span class='ck-qtype'>" + esc((r.friction_type || "").toLowerCase()) + "</span>" +
    "<span class='ck-qstate'>" + esc(r.verdict || "") + "</span></div>" +
    "<div class='ck-glance'>" + esc((r.composed && r.composed.glance) || "") + "</div>" +
    "<div class='ck-qopen'>" +
      "<div class='ck-qworking'>" + esc((r.composed && r.composed.working) || "") + "</div>" +
      nodesBlock +
      auditHTML(r.composed && r.composed.audit) +
      // the comment composer on the claim this demand names — a review note on the ledger.
      commentComposerHTML(nodes[0]) +
    "</div>" +
    // the routing door appears only where the row's axis is derivable (server-enriched).
    (routable ? routeButtonHTML(r.route_axis, r.route) : "") + "</div>";
}
function wireQueueRows(mat, rows) {
  const R = (typeof window !== "undefined" && window.HymnShell && window.HymnShell.hyRule) || null;
  $$(".ck-qrow", mat).forEach((row) => {
    activate(row, (e) => {
      if (e && e.target && e.target.closest(".rule-chip, .rule-cap, .ck-routebtn, .ck-audit, .ck-comment, a")) return;
      const on = row.classList.toggle("is-open");
      row.setAttribute("aria-expanded", on ? "true" : "false");
    });
    // fix 4: the node-scoped ✎ — a rule banks about THIS demand's claim (ctx names it).
    if (R && R.attach) {
      try { R.attach(row, { surface: "conceptric", project: CORPUS, node: "demand:" + (row.dataset.demand || ""),
        title: "queue · " + (row.dataset.demand || ""), kind: "demand" }); }
      catch (_e) { /* the mouth is a bonus atom — never load-bearing */ }
    }
  });
}
// ── the node-scoped COMMENT composer (the `comment` verb — POST /corpus/feedback) ──────────
// A node comment is a REVIEW NOTE on the manuscript's one feedback ledger — distinct from the
// ✎ mouth, which banks an interface fork to the friction ledger. The composer rides the hosts
// that carry a node (queue rows, coverage axis tiles); it banks scoped to that node and echoes
// the banked row in place (the echo law). No node, no composer.
function commentComposerHTML(node) {
  if (!node) return "";
  return "<div class='ck-comment' data-cnode='" + esc(node) + "'>" +
    "<div class='ck-comment-h'>comment — a review note on this claim" +
      "<span class='sub'>a note on the manuscript's feedback ledger, not an interface fork (the ✎)</span></div>" +
    "<textarea class='ck-comment-text' placeholder='a review note on this claim — banks to the manuscript feedback ledger'></textarea>" +
    "<div class='ck-comment-row'><button type='button' class='ck-comment-bank'>bank comment</button>" +
      "<span class='ck-comment-msg'></span></div>" +
    "<div class='ck-comment-echo'></div></div>";
}
function commentEchoHTML(rec) {
  const meta = [esc(rec.by || "an author"), esc(String(rec.ts || "").split("T")[0])].filter(Boolean).join(" · ");
  return "<div class='ck-comment-echoed'>" +
    "<div class='ck-comment-echoed-meta'>" + meta + "</div>" +
    "<div class='ck-comment-echoed-text'>" + esc(rec.comment || "") + "</div></div>";
}
function wireCommentComposers(root) {
  $$(".ck-comment", root).forEach((box) => {
    const node = box.dataset.cnode;
    const btn = box.querySelector(".ck-comment-bank");
    const ta = box.querySelector(".ck-comment-text");
    const msg = box.querySelector(".ck-comment-msg");
    const echo = box.querySelector(".ck-comment-echo");
    if (!btn || !ta) return;
    activate(btn, async () => {
      const comment = (ta.value || "").trim();
      if (!comment) { msg.textContent = "a comment is required"; return; }
      btn.disabled = true; msg.textContent = "banking…";
      try {
        // actor law: the comment is attributed (author actor); inject:[] keeps the corpus in
        // the BODY, not doubled into the query — the door reads corpus + node_id from the body.
        const res = await store.fetchJSON("/corpus/feedback", { inject: [], method: "POST",
          body: { corpus: CORPUS, node_id: node, comment, kind: "note", by: "author" } });
        const rec = (res && res.record) || null;
        if (!rec) { msg.textContent = "refused: " + ((res && res.error) || "unknown"); btn.disabled = false; return; }
        msg.textContent = "banked — it appears below";
        ta.value = "";
        if (echo) echo.insertAdjacentHTML("afterbegin", commentEchoHTML(rec));
        btn.disabled = false;
      } catch (e) { msg.textContent = "refused: " + String(e.message || e); btn.disabled = false; }
    });
  });
}

async function matCoverage(mat) {
  const data = CACHE.coverage || (CACHE.coverage = await store.fetchJSON("/growth/coverage").catch(() => ({ axes: [] })));
  const axes = data.axes || [];
  mat.innerHTML = matHead("coverage · " + axes.length + " axes") +
    "<div class='ck-cards'>" + axes.map((a) => {
      const zero = a.total && !a.covered;
      const act = a.composed && a.composed.decision && (a.composed.decision.actions || [])[0];
      const un0 = (a.uncovered || [])[0];
      const unNode = un0 && (typeof un0 === "string" ? un0 : (un0.id || un0.node || ""));
      return "<div class='ck-axis' data-axis='" + esc(a.axis) + "'><div class='ax-h'>" + esc(a.axis) +
        (zero ? "<span class='ax-state'>measured zero</span>" : "<span class='ax-state' style='color:var(--warn);border-color:color-mix(in srgb,var(--warn) 40%,transparent);background:color-mix(in srgb,var(--warn) 8%,transparent)'>" + a.covered + " / " + a.total + "</span>") +
        "</div><div class='ax-words'>" + esc((a.composed && a.composed.glance) || "") + "</div>" +
        // the routing door — present only on an axis with a live gap (a routing action served)
        (act ? routeButtonHTML(a.axis, act) : "") +
        // the comment composer on the first uncovered claim this axis names (review note).
        commentComposerHTML(unNode) + "</div>";
    }).join("") + "</div>";
  wireMatClose(mat);
  wireRouteButtons(mat);
  wireCommentComposers(mat);
}
// the axis-gap routing button — names the door (its verb) and what it writes (its plain
// consequence); the button is a door, never pre-selected. It posts the served fingerprint
// so the server can refuse a stale surface (the same seat the tension doors carry).
function routeButtonHTML(axis, act) {
  return "<div class='ax-route'>" +
    "<button type='button' class='ck-routebtn' data-axis='" + esc(axis) +
      "' data-fp='" + esc(act.fingerprint || "") + "'>" + esc(act.verb || "route this gap") + "</button>" +
    "<div class='ax-conseq'>" + esc(act.consequence || "") + "</div>" +
    "<div class='ax-routedone' data-role='route-done' style='display:none'></div></div>";
}
function wireRouteButtons(mat) {
  $$(".ck-routebtn", mat).forEach((btn) => activate(btn, () => routeGap(btn)));
}
async function routeGap(btn) {
  const axis = btn.dataset.axis, fp = btn.dataset.fp;
  const done = btn.parentElement.querySelector("[data-role='route-done']");
  btn.disabled = true;
  try {
    const res = await store.fetchJSON("/growth/route-gap", { inject: [], method: "POST",
      body: { corpus: CORPUS, axis, fingerprint: fp, by: "gerard" } });
    if (done) {
      done.style.display = "block";
      const wo = res && res.work_order;
      done.textContent = res && res.ok
        ? "banked — " + ((wo && wo.composed && wo.composed.glance) || res.glance || "one order in the friction channel")
        : "refused: " + ((res && res.error) || "unknown");
    }
    // a banked order changes the open-orders count — refresh the brief's counts.
    delete CACHE["work-orders"]; BRIEF = await store.fetchJSON("/growth/brief").catch(() => BRIEF);
  } catch (e) {
    if (done) { done.style.display = "block"; done.textContent = "refused: " + String(e.message || e); }
    btn.disabled = false;
  }
}
async function matWorkOrders(mat) {
  const data = CACHE["work-orders"] || (CACHE["work-orders"] = await store.fetchJSON("/growth/work-orders").catch(() => ({ orders: [] })));
  const rows = data.orders || [];
  // fix 8: an empty chip TEACHES how an order gets here; a present order names WHO asked —
  // his ask, or a machine-session waiter (never dressed as his ask).
  mat.innerHTML = matHead("work orders · " + rows.length) +
    "<div class='ck-cards'>" + (rows.length ? rows.map(workOrderHTML).join("")
      : "<div class='ck-empty-teach'>No banked order stands on this project. Routing a coverage gap " +
        "(from the coverage detail) banks one here for a later session to carry.</div>") + "</div>";
  wireMatClose(mat);
}
// his ask reads as his ask; a machine-requested order reads as a machine-session waiter,
// never as a demand on his hand (the class his ruling names).
function workOrderHTML(r) {
  const by = String(r.requested_by || "").trim();
  const his = by.toLowerCase() === "gerard";
  const attr = his
    ? "your ask — banked for a later session to carry"
    : "waits for a machine session — nothing here needs your hand" + (by ? " (requested by " + esc(by) + ")" : "");
  return "<div class='ck-wo'>" +
    "<div class='ck-glance'>" + esc((r.composed && r.composed.glance) || (r.what || "")) + "</div>" +
    "<div class='wo-attr" + (his ? "" : " is-machine") + "'>" + attr + "</div></div>";
}
// the ladder strip — rendered from /surface/contract states (conjugate views, deliverable 5)
async function matLadder(mat) {
  if (!CONTRACT) CONTRACT = await store.fetchJSON("/surface/contract", { inject: [], params: { surface: "conceptric" } }).catch(() => null);
  const states = (CONTRACT && CONTRACT.states) || [];
  const st = (BRIEF && BRIEF.state) || {};
  const here = st.state || null;
  // a pre-ladder project says so plainly — otherwise the strip reads as a position
  // when it is only the law (his ruling: the current state beats the definitions).
  const preNote = (!here && st.pre_ladder)
    ? "<div class='ck-brief-prose' style='font-size:12px;margin:0 0 10px'>This project predates the ladder — the rungs below are the law a re-pour would climb, not a position it holds today.</div>"
    : (!here ? "<div class='ck-brief-prose' style='font-size:12px;margin:0 0 10px'>This project is not on the ladder yet — the rungs below are what birth onto it would open.</div>" : "");
  mat.innerHTML = matHead("the growth ladder") + preNote +
    "<div class='ck-ladder'>" + states.map((s) =>
      "<div class='ck-rung " + (s.name === here ? "is-here" : "") + "'><span class='rn'>" + esc(s.name) + "</span>" +
      "<span class='rbar'>" + esc(s.bar || "") + "</span><span class='rdoes'>" + esc(s.does || "") + "</span></div>").join("") + "</div>";
  wireMatClose(mat);
}

// ═══════════════ the reconciled tension — read-only banked history (fix 1b) ═══════════════
async function loadReconciled(gt) {
  const key = "reconciled" + (gt ? ":" + gt : "");
  if (CACHE[key]) return CACHE[key];
  const data = await store.fetchJSON("/growth/reconciled", { params: gt ? { gt } : {} }).catch(() => null);
  if (data) CACHE[key] = data;
  return data;
}
// the ruled tension, whole: the composed conflict, the four verbs it offered (REGOAL
// marked as the one he took), and the real ruling banked — his words, the new goal, when
// and by whom — plus the audit provenance. A read; no verb fires here.
async function matHistory(mat) {
  const data = await loadReconciled();
  const rec = data && data.reconciled;
  if (!rec) {
    mat.innerHTML = matHead("the ruled tension") +
      "<div class='ck-brief-prose'>" + esc((data && data.miss_note) ||
        "no ruled tension is banked on this project.") + "</div>";
    wireMatClose(mat);
    return;
  }
  mat.innerHTML = matHead("the ruled tension · read-only history") +
    reconciledHistoryHTML(rec);
  wireMatClose(mat);
}
function reconciledHistoryHTML(rec) {
  const block = rec.composed || {};
  const dec = block.decision || {};
  const ruling = rec.ruling || {};
  const verbs = (dec.actions || []).map((a) => {
    const ruled = a.verb === rec.verb;
    return "<div class='ck-hist-verb" + (ruled ? " is-ruled" : "") + "'>" +
      "<div class='hvn'>" + esc(a.verb) + (ruled ? " <span class='ck-ruled-tag'>the ruling</span>" : "") + "</div>" +
      "<div class='hvc'>" + esc(a.consequence || "") + "</div></div>";
  }).join("");
  const meta = [ruling.by ? "ruled by " + esc(ruling.by) : "", ruling.ts ? "on " + esc(ruling.ts) : ""]
    .filter(Boolean).join(" · ");
  const goalLine = ruling.new_goal_essence
    ? "<div class='hr-goal'>the new goal it banked: " + esc(ruling.new_goal_essence) + "</div>" : "";
  return "<div class='ck-history ck-history-reveal'>" +
    "<div class='ck-hist-head'><div class='ck-hist-kind'>tension · ruled, banked as history</div>" +
      "<div class='ck-hist-title'>" + esc(shortTitle(block.glance)) + "</div></div>" +
    "<div class='ck-hist-body'>" +
      "<div class='ck-conflict'>" + esc(dec.tension || "") + "<span class='cw'>" + esc(block.working || "") + "</span></div>" +
      "<div class='ck-hist-verbs'>" + verbs + "</div>" +
      "<div class='ck-hist-ruling'>" +
        "<div class='hr-h'>the ruling — banked, his words</div>" +
        (meta ? "<div class='hr-meta'>" + meta + "</div>" : "") +
        (ruling.commentary ? "<div class='hr-words'>" + esc(ruling.commentary) + "</div>" : "") +
        goalLine +
      "</div>" +
      auditHTML(block.audit) +
    "</div></div>";
}

// fix 3: a cold ?gt= link to a missing/ruled tension is no longer a silent no-op. The
// server's own composed "no open tension — it may be already ruled or dismissed" surfaces
// as an inline transient note on the brief; when a ruled tension is banked, the note offers
// the read-only history view (fix 1b).
async function openTensionMiss(gt) {
  const scoped = await loadReconciled(gt);
  const note = (scoped && scoped.miss_note) ||
    "This tension is not open — it may be already ruled or dismissed.";
  let anyRec = !!(scoped && scoped.reconciled);
  if (!anyRec) { const all = await loadReconciled(); anyRec = !!(all && all.reconciled); }
  const host = $("#ck-missnote");
  if (!host) { if (anyRec) return materialise("history"); return; }
  host.innerHTML =
    "<div class='ck-missnote'><span class='mn-h'>no open tension</span>" + esc(note) +
    (anyRec ? "<span class='mn-read' data-role='read-ruled' tabindex='0' role='button'>read the ruled tension →</span>" : "") +
    "</div>";
  const read = host.querySelector("[data-role='read-ruled']");
  if (read) activate(read, () => { host.innerHTML = ""; materialise("history"); });
}

// ═══════════════ the decision altitude — pin / reallocate (B.2) ═══════════════
async function openTension(gt) {
  const data = CACHE.tensions || (CACHE.tensions = await store.fetchJSON("/growth/tensions").catch(() => ({ tensions: [] })));
  const row = (data.tensions || []).find((t) => t.id === gt);
  if (!row) return openTensionMiss(gt);
  const title = "a tension — your call";
  const destination = "back to the brief — where you were";
  REALLOC.pin(gt, {
    title,
    destination,
    buildRail: (railEl) => buildTensionRail(railEl, row),
    buildFocus: (focusEl) => buildTensionFocus(focusEl, row),
  });
  // restore a remembered selection (B.3)
  const sel = SELECTION[gt];
  if (sel && sel.verb) { const v = $(".ck-verb[data-verb='" + cssAttr(sel.verb) + "']"); if (v) v.click(); }
}
function cssAttr(v) { return String(v).replace(/'/g, "\\'"); }

function buildTensionRail(railEl, row) {
  const cov = (BRIEF && BRIEF.counts) || {};
  const state = (BRIEF && BRIEF.state) || {};
  railEl.innerHTML =
    "<div class='eng-railblock'><h5>ladder</h5><div class='ck-railcov'>" +
      esc(state.state || (state.pre_ladder ? "pre-ladder" : "unseeded")) + "</div></div>" +
    "<div class='eng-railblock'><h5>coverage · vs goal</h5><div class='ck-railcov'>" +
      "<span class='z'>" + (cov.zero_axes || 0) + " axis at zero</span></div></div>" +
    "<div class='eng-railblock'><h5>other counts</h5><div class='ck-railcov'>" +
      (cov.queue || 0) + " below the floor<br>" + (cov.work_orders || 0) + " work order(s)</div></div>";
}

function buildTensionFocus(focusEl, row) {
  const block = row.composed || {}; const dec = block.decision || {};
  const pane = document.createElement("div");
  pane.className = "ck-focus-pane";
  pane.innerHTML =
    "<div class='ck-focus-head'><div class='ck-focus-kind'>tension · your call</div>" +
      "<div class='ck-focus-title'>" + esc(shortTitle(block.glance)) + "</div></div>" +
    "<div class='ck-focus-body'>" +
      "<div class='ck-conflict'>" + esc(dec.tension || "") + "<span class='cw'>" + esc(block.working || "") + "</span></div>" +
      "<div class='ck-verbs'>" + (dec.actions || []).map(verbCard).join("") + "</div>" +
      rulingAreaHTML() +
      auditHTML(block.audit) +
    "</div>";
  focusEl.appendChild(pane);
  wireVerbs(pane, row);
}
function shortTitle(glance) { const s = String(glance || ""); const i = s.indexOf(";"); return (i > 0 ? s.slice(0, i) : s).slice(0, 90); }

function verbCard(a) {
  const lean = a.recommended ? "<span class='ck-lean'>machine's lean</span>" : "";
  return "<div class='ck-verb' data-verb='" + esc(a.verb) + "' data-fp='" + esc(a.fingerprint || "") + "'" +
    (a.confirm ? " data-confirm='1'" : "") + " tabindex='0' role='button'>" +
    "<div class='vn'>" + esc(a.verb) + " " + lean + "</div>" +
    "<div class='vresolves'>" + esc(a.resolves || "") + "</div></div>";
}
function rulingAreaHTML() {
  return "<div class='ck-ruling' id='ck-ruling'>" +
    "<div class='rl-h'>you are ruling <span id='ck-rule-verb'></span></div>" +
    "<div class='ck-conseq' id='ck-conseq'></div>" +
    "<div class='ck-writes' id='ck-writes'></div>" +
    "<div class='ck-confirm' id='ck-confirm'>" +
      "<span class='cf-h'>confirm before supersede</span>" +
      "<span class='cf-mark'>reconstructed from the goal material and your restatement; confirm or correct it — the new goal saves only from your confirmed text.</span>" +
      "<textarea id='ck-confirm-text'></textarea>" +
      "<button type='button' class='cf-btn' id='ck-confirm-btn'>confirm this goal text</button>" +
    "</div>" +
    "<div class='ck-commentary'><label>your reason</label><div class='sub'>optional — banks on the same record as the ruling, one write.</div>" +
      "<textarea id='ck-note' placeholder='say why, if you want to — it stays attached to this decision'></textarea>" +
      "<div class='ck-commit-row'><button type='button' class='ck-commit' id='ck-commit' disabled>bank <span id='ck-commit-verb'></span></button>" +
      "<span class='ck-commit-hint'>one write through the actor-guarded door</span></div>" +
      "<div class='ck-done' id='ck-done' style='display:none'></div></div>" +
  "</div>";
}
function auditHTML(audit) {
  const ids = (audit && audit.ids) || [];
  if (!ids.length) return "";
  return "<details class='ck-audit'><summary>provenance · ids (audit depth)</summary>" +
    ids.map((x) => "<div>" + esc(x) + "</div>").join("") + "</details>";
}

function wireVerbs(pane, row) {
  const verbs = $$(".ck-verb", pane);
  verbs.forEach((vb) => {
    // hover: preview the consequence in the fixed lens (no reflow) + light this verb's clause
    const action = (row.composed.decision.actions || []).find((a) => a.verb === vb.dataset.verb) || {};
    vb.addEventListener("mouseenter", () => {
      if (pane.classList.contains("mode-ruling")) return;
      LENS.show(vb, "<div class='lens-h'>" + esc(vb.dataset.verb) + " — what this does</div><div>" + esc(action.consequence || "") + "</div>");
    });
    vb.addEventListener("mouseleave", () => LENS.hide());
    activate(vb, () => selectVerb(pane, row, vb, action));
  });
}

function selectVerb(pane, row, vb, action) {
  LENS.hide();
  $$(".ck-verb", pane).forEach((x) => x.classList.remove("is-selected"));
  vb.classList.add("is-selected");
  pane.classList.add("mode-ruling");
  SELECTION[row.id] = { verb: vb.dataset.verb };
  const ruling = $("#ck-ruling"); ruling.classList.add("on");
  $("#ck-rule-verb").textContent = vb.dataset.verb;
  $("#ck-commit-verb").textContent = vb.dataset.verb;
  $("#ck-conseq").textContent = action.consequence || "";
  $("#ck-writes").innerHTML = "writes: <b>" + esc((action.writes || []).join(" · ")) + "</b>" +
    // E4 seam — REALIGN/RESPINE names manuscript work; its consequence doors to the editor
    // altitude (?via=cockpit-tension so /artefact renders the return door back to this brief).
    (vb.dataset.verb === "REALIGN/RESPINE"
      ? " <a class='ck-door' data-role='realign-door' href='/artefact?corpus=" +
        encodeURIComponent(CORPUS) + "&via=cockpit-tension'>open Read · Judge — realign the paper there →</a>"
      : "");
  $("#ck-done").style.display = "none";
  const confirm = $("#ck-confirm"); const commit = $("#ck-commit");
  const needsConfirm = !!vb.dataset.confirm;
  confirm.classList.toggle("on", needsConfirm);
  confirm.classList.remove("confirmed");
  if (needsConfirm) {
    $("#ck-confirm-text").value = String(action.confirm || "").replace(/^Reconstructed goal \(confirm or correct this before it is saved\): /, "");
    commit.disabled = true;                     // commit stays disabled until his explicit confirm (never silent)
    const cb = $("#ck-confirm-btn");
    cb.onclick = () => { confirm.classList.add("confirmed"); cb.textContent = "✓ goal text confirmed"; commit.disabled = false; };
  } else {
    commit.disabled = false;
  }
  commit.onclick = () => bankRuling(row, action);
}

async function bankRuling(row, action) {
  const commit = $("#ck-commit"); if (commit.disabled) return;
  const note = ($("#ck-note").value || "").trim();
  const body = { corpus: CORPUS, gt_id: row.id, verb: action.verb, fingerprint: action.fingerprint, by: "gerard", note };
  if (action.confirm) body.confirmed_goal_text = ($("#ck-confirm-text").value || "").trim();
  const done = $("#ck-done");
  try {
    const res = await store.fetchJSON("/growth/rule", { inject: [], method: "POST", body });
    done.style.display = "block";
    done.textContent = res && res.ok ? "✓ banked — " + esc(action.verb) + ", one write through the actor-guarded door." : "refused: " + esc((res && res.error) || "unknown");
    // a banked ruling clears the tension cache so the brief re-reads the true state.
    delete CACHE.tensions; BRIEF = await store.fetchJSON("/growth/brief").catch(() => BRIEF);
  } catch (e) {
    done.style.display = "block"; done.textContent = "refused: " + esc(String(e.message || e));
  }
}
