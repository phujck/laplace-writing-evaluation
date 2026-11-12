// THE MANUSCRIPT WORK ROOM. Purpose: one source-bearing working field over the immutable
// laplace.aisthesis-manuscript-workbench/1 projection: the passage, its proposed revisions and
// the acknowledgement of a saved source effect. Ownership: the manuscript workbench owner issues
// the projection and the save guards; source-effect decides a refused write's disposition; this
// module owns no fetch, history, retry or revision policy and installs its own scoped styles
// once (installManuscriptWorkSurfaceStyles). Public contract: renderManuscriptWorkSurface(host,
// projection, handlers) (default export), MANUSCRIPT_WORK_SURFACE_SCHEMA. Inputs: one projection;
// outputs: DOM and the handlers' calls. Currentness: the projection's revision; a changed source
// refuses at the owner. Storage: none.
import {sourceEffectDisposition,requireSourceCompletion,sourceEffectFromError} from './source-effect.mjs';
// The manuscript Work room: one source-bearing working field over the immutable
// laplace.aisthesis-manuscript-workbench/1 projection.  It owns no fetch, history,
// storage or writer.  Canonical acts can leave only through an injected shared request
// gateway; every selection transition returns to the carrier's existing URL store.

export const MANUSCRIPT_WORK_SURFACE_SCHEMA = "laplace.aisthesis-manuscript-work-surface/1";

const STYLE_ID = "aisthesis-manuscript-work-surface-style";

const CSS = `
.manuscript-work{--mw-rule:color-mix(in srgb,var(--edge2) 58%,transparent);min-width:0;position:relative;padding:.4rem 0 4rem}
.manuscript-work button,.manuscript-work a,.manuscript-work select{min-height:44px}
.manuscript-work button{font:inherit;color:inherit}
.manuscript-work__heading{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(15rem,.65fr);gap:clamp(1.5rem,5vw,6rem);align-items:end;padding:1rem 0 1.6rem;border-bottom:1px solid var(--mw-rule)}
.manuscript-work__kicker,.manuscript-work__state,.manuscript-work__source,.manuscript-work__count,.manuscript-work__stage-state{font:600 .62rem/1.35 var(--mono,monospace);letter-spacing:.09em;text-transform:uppercase}
.manuscript-work__kicker{color:var(--accent)}
.manuscript-work__heading h2{max-width:28ch;margin:.4rem 0 .55rem;font:620 clamp(1.65rem,3.2vw,3rem)/1.02 var(--serif,serif);letter-spacing:-.025em}
.manuscript-work__heading p{max-width:65ch;margin:0;color:var(--ink2);font:clamp(.9rem,1.15vw,1.05rem)/1.65 var(--serif,serif)}
.manuscript-work__postures{display:grid;grid-template-columns:1fr 1fr;gap:1px;align-self:end;background:var(--mw-rule)}
.manuscript-work__posture{min-height:3.25rem;padding:.55rem .8rem;border:0;background:var(--bg);text-align:left;cursor:pointer}
.manuscript-work__posture span,.manuscript-work__posture b{display:block}
.manuscript-work__posture b{font:570 .86rem/1.2 var(--display,system-ui)}
.manuscript-work__posture span{margin-top:.25rem;color:var(--dim);font:.62rem/1.2 var(--mono,monospace);text-transform:uppercase}
.manuscript-work__posture[aria-pressed=true]{background:linear-gradient(125deg,color-mix(in srgb,var(--accent) 12%,transparent),transparent);box-shadow:inset 0 -2px var(--accent)}
.manuscript-work__field{display:grid;grid-template-columns:minmax(10.5rem,.42fr) minmax(22rem,1.55fr) minmax(13rem,.55fr);gap:clamp(1rem,3vw,3.5rem);min-height:38rem;padding:clamp(1.2rem,3vw,2.8rem) 0 1.5rem}
.manuscript-work__spine{position:relative;padding-left:1.15rem}
.manuscript-work__spine::before{position:absolute;inset:.8rem auto .8rem .25rem;width:1px;content:"";background:linear-gradient(var(--accent),var(--mw-rule) 55%,transparent)}
.manuscript-work__section{width:100%;display:grid;grid-template-columns:.8rem minmax(0,1fr);gap:.65rem;position:relative;padding:.48rem 0;border:0;background:transparent;text-align:left;cursor:pointer}
.manuscript-work__section::before{width:.48rem;height:.48rem;margin-top:.25rem;border:1px solid var(--edge2);border-radius:50%;background:var(--bg);content:"";transform:translateX(-1.12rem)}
.manuscript-work__section span{display:block}
.manuscript-work__section-name{color:var(--ink2);font:.75rem/1.28 var(--display,system-ui)}
.manuscript-work__section-meta{margin-top:.2rem;color:var(--dim);font:.58rem/1 var(--mono,monospace)}
.manuscript-work__section[aria-current=true]::before{border-color:var(--accent);background:var(--accent);box-shadow:0 0 .8rem color-mix(in srgb,var(--accent) 45%,transparent)}
.manuscript-work__section[aria-current=true] .manuscript-work__section-name{color:var(--gold-light);font-size:.9rem}
.manuscript-work__canvas{min-width:0;position:relative;padding:0 clamp(.5rem,2vw,1.5rem)}
.manuscript-work__canvas::before{position:absolute;inset:0 auto 0 0;width:1px;content:"";background:linear-gradient(transparent,var(--mw-rule) 8%,var(--mw-rule) 92%,transparent)}
.manuscript-work__canvas-head{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:1rem;align-items:start;margin-bottom:1.35rem;padding-bottom:.8rem;border-bottom:1px solid var(--mw-rule)}
.manuscript-work__canvas h3{margin:.25rem 0 0;font:610 clamp(1.2rem,2vw,1.75rem)/1.18 var(--serif,serif)}
.manuscript-work__source{color:var(--dim);text-align:right;text-transform:none;letter-spacing:.025em}
.manuscript-work__blocks{display:grid;gap:.1rem}
.manuscript-work__block{width:100%;display:grid;grid-template-columns:1.15rem minmax(0,1fr);gap:.85rem;position:relative;padding:.72rem 0;border:0;border-bottom:1px solid color-mix(in srgb,var(--mw-rule) 64%,transparent);background:transparent;text-align:left;cursor:pointer}
.manuscript-work__block::before{width:.38rem;height:.38rem;margin:.5rem auto 0;border:1px solid var(--edge2);border-radius:50%;content:""}
.manuscript-work__block[data-kind=head]::before{border-radius:0;transform:rotate(45deg)}
.manuscript-work__block[data-kind=figure]::before{border-radius:0;border-style:double}
.manuscript-work__block[aria-current=true]::before{border-color:var(--accent);background:var(--accent)}
.manuscript-work__block-copy{min-width:0}
.manuscript-work__block-kind{display:block;color:var(--dim);font:.56rem/1 var(--mono,monospace);letter-spacing:.08em;text-transform:uppercase}
.manuscript-work__block-words{display:-webkit-box;margin-top:.32rem;overflow:hidden;color:var(--ink2);font:.9rem/1.62 var(--serif,serif);-webkit-box-orient:vertical;-webkit-line-clamp:3}
.manuscript-work__block[aria-current=true]{padding-block:1rem}
.manuscript-work__block[aria-current=true] .manuscript-work__block-words{display:block;color:var(--ink);font-size:1.02rem;line-height:1.75;-webkit-line-clamp:unset}
.manuscript-work__block-source{display:none;margin-top:.65rem;color:var(--dim);font:.62rem/1.35 var(--mono,monospace)}
.manuscript-work__block[aria-current=true] .manuscript-work__block-source{display:block}
.manuscript-work__margin{min-width:0;padding-left:1rem;border-left:1px solid var(--mw-rule)}
.manuscript-work__margin h3{margin:0 0 .8rem;color:var(--dim);font:600 .62rem/1 var(--mono,monospace);letter-spacing:.12em;text-transform:uppercase}
.manuscript-work__signal{width:100%;display:block;position:relative;padding:.7rem .2rem .8rem 1rem;border:0;border-bottom:1px solid var(--mw-rule);background:transparent;text-align:left;cursor:pointer}
.manuscript-work__signal::before{position:absolute;top:1rem;left:0;width:.45rem;height:.45rem;border:1px solid currentColor;border-radius:50%;content:""}
.manuscript-work__signal[data-state=UNKNOWN]::before{border-style:dashed}
.manuscript-work__signal[data-state=REFUSED]::before{border-radius:0;transform:rotate(45deg)}
.manuscript-work__signal b,.manuscript-work__signal span{display:block}
.manuscript-work__signal b{font:560 .78rem/1.25 var(--display,system-ui)}
.manuscript-work__signal span{margin-top:.24rem;color:var(--dim);font:.62rem/1.35 var(--mono,monospace)}
.manuscript-work__unknown{position:relative;min-height:23rem;display:grid;place-items:center;padding:2rem;border-block:1px dashed var(--edge2);background:repeating-linear-gradient(135deg,transparent 0,transparent 12px,color-mix(in srgb,var(--edge2) 9%,transparent) 12px,color-mix(in srgb,var(--edge2) 9%,transparent) 13px);text-align:center}
.manuscript-work__unknown h3{margin:0;font:620 1.4rem/1.2 var(--serif,serif)}
.manuscript-work__unknown p{max-width:45ch;margin:.7rem auto 0;color:var(--ink2)}
.manuscript-work__unknown a{display:inline-flex;align-items:center;margin-top:1rem;padding:.45rem .75rem;border-bottom:1px solid var(--accent)}
.manuscript-work__pipeline{position:relative;margin-top:.7rem;padding:2rem 0;border-top:1px solid var(--mw-rule)}
.manuscript-work__pipeline-head{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(14rem,.85fr);gap:clamp(1.5rem,5vw,5rem);align-items:start}
.manuscript-work__pipeline-head h3{margin:.3rem 0 .4rem;font:620 clamp(1.2rem,2vw,1.8rem)/1.18 var(--serif,serif)}
.manuscript-work__pipeline-head p{margin:0;color:var(--ink2);font:.88rem/1.55 var(--serif,serif)}
.manuscript-work__next{padding-left:1rem;border-left:2px solid var(--keystone);color:var(--ink);font:.82rem/1.45 var(--display,system-ui)}
.manuscript-work__release{display:grid;grid-template-columns:repeat(var(--mw-stages),minmax(5.5rem,1fr));position:relative;margin-top:1.6rem;overflow-x:auto;padding:.25rem 0 1rem}
.manuscript-work__release::before{position:absolute;top:1.08rem;right:0;left:0;height:1px;content:"";background:linear-gradient(90deg,var(--accent),var(--mw-rule) 42%,transparent)}
.manuscript-work__stage{min-width:5.5rem;display:grid;align-content:start;position:relative;padding:0 .6rem;border:0;background:transparent;text-align:left;cursor:pointer}
.manuscript-work__stage::before{width:.68rem;height:.68rem;margin:0 0 .65rem;border:1px solid var(--edge2);border-radius:50%;background:var(--bg);content:"";z-index:1}
.manuscript-work__stage[data-status=PASSED]::before{border-color:var(--ok);background:var(--ok)}
.manuscript-work__stage[data-status=CURRENT]::before{border-color:var(--accent);background:var(--accent);box-shadow:0 0 1rem color-mix(in srgb,var(--accent) 50%,transparent)}
.manuscript-work__stage-name{font:560 .68rem/1.25 var(--display,system-ui)}
.manuscript-work__stage-state{margin-top:.3rem;color:var(--dim);font-size:.54rem}
.manuscript-work__mechanisms{display:flex;flex-wrap:wrap;gap:.2rem 1.2rem;margin-top:1rem;padding-top:.8rem;border-top:1px solid color-mix(in srgb,var(--mw-rule) 60%,transparent)}
.manuscript-work__mechanism{min-height:44px;padding:.35rem 0;border:0;border-bottom:1px solid transparent;background:transparent;color:var(--ink2);cursor:pointer;font:.72rem/1.2 var(--display,system-ui);text-align:left}
.manuscript-work__mechanism[data-state=UNKNOWN]{border-bottom-style:dashed;border-bottom-color:var(--dim)}
.manuscript-work__actions{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(18rem,.55fr);gap:clamp(1.2rem,4vw,4rem);position:relative;margin:1rem 0 2.8rem;padding:clamp(1.2rem,3vw,2.5rem) 0;border-block:1px solid var(--mw-rule)}
.manuscript-work__actions::before{position:absolute;top:-1px;left:0;width:min(18rem,36%);height:2px;content:"";background:var(--accent)}
.manuscript-work__editor-head{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:1rem;align-items:end;margin-bottom:.8rem}
.manuscript-work__editor-head h3,.manuscript-work__version-rail h3,.manuscript-work__launch h4{margin:.25rem 0 0;font:610 clamp(1.05rem,1.8vw,1.5rem)/1.2 var(--serif,serif)}
.manuscript-work__editor-head p{max-width:55ch;margin:.35rem 0 0;color:var(--ink2);font:.82rem/1.5 var(--serif,serif)}
.manuscript-work__file{align-self:start;color:var(--dim);font:.62rem/1.35 var(--mono,monospace);text-align:right}
.manuscript-work__editor{width:100%;min-height:19rem;resize:vertical;padding:1rem 1.15rem;border:1px solid var(--edge2);border-inline-start:3px solid var(--accent);border-radius:0;background:color-mix(in srgb,var(--panel) 72%,var(--bg));color:var(--ink);font:.82rem/1.6 var(--mono,monospace);tab-size:2}
.manuscript-work__editor:disabled{border-inline-start-style:dashed;color:var(--dim);background:repeating-linear-gradient(135deg,transparent 0,transparent 13px,color-mix(in srgb,var(--edge2) 8%,transparent) 13px,color-mix(in srgb,var(--edge2) 8%,transparent) 14px)}
.manuscript-work__action-row{display:flex;flex-wrap:wrap;gap:.45rem;align-items:center;margin-top:.7rem}
.manuscript-work__act{min-width:8.5rem;padding:.55rem .8rem;border:1px solid var(--edge2);background:transparent;text-align:left;cursor:pointer}
.manuscript-work__act[data-primary=true]{border-color:var(--accent);background:linear-gradient(110deg,color-mix(in srgb,var(--accent) 12%,transparent),transparent)}
.manuscript-work__act:disabled{cursor:not-allowed;border-style:dashed;color:var(--dim)}
.manuscript-work__act small{display:block;margin-top:.15rem;color:var(--dim);font:.55rem/1.2 var(--mono,monospace);text-transform:uppercase}
.manuscript-work__act-state{min-height:1.3rem;margin:.55rem 0 0;color:var(--ink2);font:.68rem/1.45 var(--mono,monospace)}
.manuscript-work__gateway-refusal{margin:.7rem 0;padding:.7rem .8rem;border-inline-start:3px dashed var(--edge2);background:repeating-linear-gradient(135deg,transparent 0,transparent 12px,color-mix(in srgb,var(--edge2) 8%,transparent) 12px,color-mix(in srgb,var(--edge2) 8%,transparent) 13px);color:var(--ink2);font:.72rem/1.45 var(--display,system-ui)}
.manuscript-work__gateway-refusal b{display:block;margin-bottom:.15rem;color:var(--ink);font:.58rem/1.2 var(--mono,monospace);letter-spacing:.08em;text-transform:uppercase}
.manuscript-work__version-rail{min-width:0;padding-left:1rem;border-left:1px solid var(--mw-rule)}
.manuscript-work__version-rail>p{margin:.4rem 0 1rem;color:var(--ink2);font:.78rem/1.5 var(--serif,serif)}
.manuscript-work__selectors{display:grid;grid-template-columns:1fr 1fr;gap:.55rem}
.manuscript-work__selector{display:grid;gap:.25rem;color:var(--dim);font:.56rem/1.2 var(--mono,monospace);letter-spacing:.06em;text-transform:uppercase}
.manuscript-work__selector select{min-width:0;width:100%;padding:.45rem;border:1px solid var(--edge2);border-radius:0;background:var(--bg);color:var(--ink);font:.72rem/1.2 var(--display,system-ui);text-transform:none;letter-spacing:0}
.manuscript-work__history{position:relative;margin-top:1rem;padding-left:1.1rem}
.manuscript-work__history::before{position:absolute;inset:.25rem auto .25rem .25rem;width:1px;background:linear-gradient(var(--accent),var(--mw-rule),transparent);content:""}
.manuscript-work__version{display:block;position:relative;padding:.28rem 0 .7rem;color:var(--ink2);font:.7rem/1.4 var(--display,system-ui)}
.manuscript-work__version::before{position:absolute;top:.55rem;left:-1.04rem;width:.42rem;height:.42rem;border:1px solid var(--edge2);border-radius:50%;background:var(--bg);content:""}
.manuscript-work__version b,.manuscript-work__version span{display:block}.manuscript-work__version span{margin-top:.1rem;color:var(--dim);font:.56rem/1.2 var(--mono,monospace)}
.manuscript-work__authority{margin-top:1rem;padding:.65rem .75rem;border-left:2px dashed var(--edge2);color:var(--ink2);font:.68rem/1.45 var(--display,system-ui)}
.manuscript-work__authority b{display:block;color:var(--ink);font:.58rem/1.2 var(--mono,monospace);letter-spacing:.08em;text-transform:uppercase}
.manuscript-work__launch{margin-top:1.4rem;padding-top:1.2rem;border-top:1px solid var(--mw-rule)}
.manuscript-work__launch-head{display:grid;grid-template-columns:minmax(0,1fr) minmax(13rem,.5fr);gap:1rem;align-items:end}
.manuscript-work__launch-head p{margin:.3rem 0 0;color:var(--ink2);font:.78rem/1.5 var(--serif,serif)}
.manuscript-work__launch-roster{display:flex;gap:.3rem;overflow-x:auto;margin-top:1rem;padding:0 0 .7rem;scroll-snap-type:x proximity}
.manuscript-work__launch-choice{min-width:10.5rem;min-height:5.1rem;display:grid;align-content:space-between;position:relative;padding:.65rem .7rem;border:0;border-top:2px solid var(--edge2);background:color-mix(in srgb,var(--panel) 44%,transparent);text-align:left;cursor:pointer;scroll-snap-align:start}
.manuscript-work__launch-choice[data-cost=model-heavy]{border-top-style:double;border-top-width:4px}
.manuscript-work__launch-choice[aria-pressed=true]{border-color:var(--accent);background:linear-gradient(145deg,color-mix(in srgb,var(--accent) 12%,transparent),transparent)}
.manuscript-work__launch-choice b{font:560 .72rem/1.25 var(--display,system-ui)}
.manuscript-work__launch-choice span{color:var(--dim);font:.55rem/1.25 var(--mono,monospace);text-transform:uppercase}
.manuscript-work__launch-detail{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:1rem;align-items:end;padding:1rem 0;border-block:1px solid color-mix(in srgb,var(--mw-rule) 62%,transparent)}
.manuscript-work__launch-detail p{max-width:62ch;margin:.35rem 0 0;color:var(--ink2);font:.8rem/1.5 var(--serif,serif)}
.manuscript-work__preflight{display:flex;flex-wrap:wrap;gap:.3rem .8rem;margin-top:.55rem;color:var(--dim);font:.57rem/1.3 var(--mono,monospace);text-transform:uppercase}
.manuscript-work__preflight span[data-state=UNKNOWN]{text-decoration:underline dashed;text-underline-offset:.22rem}
.manuscript-work__launch-confirm{min-width:10rem;padding:.65rem .85rem;border:1px solid var(--accent);background:transparent;text-align:left;cursor:pointer}
.manuscript-work__launch-confirm:disabled{border-color:var(--edge2);border-style:dashed;color:var(--dim);cursor:not-allowed}
.manuscript-work__launch-confirm small{display:block;color:var(--dim);font:.55rem/1.2 var(--mono,monospace);text-transform:uppercase}
.manuscript-work__audit{margin-top:1rem;padding-top:.8rem;border-top:1px solid var(--mw-rule);color:var(--ink2);font:.7rem/1.55 var(--mono,monospace)}
.manuscript-work__audit b{color:var(--ink)}
@media(max-width:1060px){
 .manuscript-work__heading{grid-template-columns:1fr}.manuscript-work__postures{max-width:28rem}
 .manuscript-work__field{grid-template-columns:minmax(9rem,.35fr) minmax(18rem,1fr);gap:1.2rem}
 .manuscript-work__margin{grid-column:1/-1;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:0 1rem;padding:1rem 0 0;border-left:0;border-top:1px solid var(--mw-rule)}
 .manuscript-work__margin h3{grid-column:1/-1}.manuscript-work__pipeline-head{grid-template-columns:1fr minmax(12rem,.65fr)}.manuscript-work__actions{grid-template-columns:minmax(0,1.2fr) minmax(16rem,.8fr);gap:1.2rem}
}
@media(max-width:620px){
 .manuscript-work{padding-top:0}.manuscript-work__heading{gap:1rem;padding-top:.4rem}.manuscript-work__heading h2{font-size:1.75rem}
 .manuscript-work__postures{width:100%;max-width:none}.manuscript-work__field{display:block;padding-top:1rem}
 .manuscript-work__spine{display:flex;gap:.2rem;overflow-x:auto;padding:0 0 .7rem;scroll-snap-type:x proximity}.manuscript-work__spine::before{display:none}
 .manuscript-work__section{min-width:9.5rem;grid-template-columns:.65rem 1fr;padding:.55rem .4rem;scroll-snap-align:start}.manuscript-work__section::before{transform:none}
 .manuscript-work__section:not([aria-current=true]) .manuscript-work__section-name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
 .manuscript-work__canvas{padding:1rem 0 0}.manuscript-work__canvas::before{display:none}.manuscript-work__canvas-head{grid-template-columns:1fr}.manuscript-work__source{text-align:left}
 .manuscript-work__block{grid-template-columns:.8rem minmax(0,1fr)}.manuscript-work__block-words{-webkit-line-clamp:2}.manuscript-work__block[aria-current=true] .manuscript-work__block-words{font-size:.96rem}
 .manuscript-work__margin{display:grid;grid-template-columns:1fr 1fr;gap:0 .8rem}.manuscript-work__pipeline-head{display:block}.manuscript-work__next{margin-top:1rem}.manuscript-work__actions{display:block}.manuscript-work__version-rail{margin-top:1.2rem;padding:1.2rem 0 0;border-left:0;border-top:1px solid var(--mw-rule)}.manuscript-work__editor-head,.manuscript-work__launch-head,.manuscript-work__launch-detail{display:block}.manuscript-work__file{text-align:left;margin-top:.4rem}.manuscript-work__launch-confirm{width:100%;margin-top:.8rem}
 .manuscript-work__release{display:block;overflow:visible;padding-left:1.2rem}.manuscript-work__release::before{top:.5rem;bottom:1rem;left:.3rem;width:1px;height:auto;background:linear-gradient(var(--accent),var(--mw-rule),transparent)}
 .manuscript-work__stage{min-height:3.5rem;display:grid;grid-template-columns:.8rem minmax(0,1fr);gap:.7rem;padding:.5rem 0}.manuscript-work__stage::before{grid-row:1/3;margin:0;transform:translateX(-1.2rem)}
 .manuscript-work__stage-state{margin-top:0}.manuscript-work__mechanisms{display:grid;grid-template-columns:1fr 1fr}
}
@media(max-width:390px){.manuscript-work__margin,.manuscript-work__mechanisms,.manuscript-work__selectors{grid-template-columns:1fr}.manuscript-work__editor{min-height:15rem}.manuscript-work__act{width:100%}.manuscript-work__launch-choice{min-width:9.7rem}}
@media(prefers-reduced-motion:reduce){.manuscript-work *{scroll-behavior:auto!important;animation:none!important;transition:none!important}}
`;

function plain(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function rows(value) {
  return Array.isArray(value) ? value.filter((item) => item && typeof item === "object") : [];
}

function human(value, fallback = "") {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  if (!text) return fallback;
  return text
    .replace(/(?:sha256:|message:)[0-9a-f]{16,}/gi, "an exact receipt")
    .replace(/region-lease:[0-9a-f]{16,}/gi, "an exact lease");
}

function node(documentRef, tag, className = "", text = "") {
  const item = documentRef.createElement(tag);
  if (className) item.className = className;
  if (text !== "") item.textContent = text;
  return item;
}

function state(value) {
  return human(value, "UNKNOWN").toUpperCase().replaceAll(" ", "_");
}

function requestGatewayFace(gateway, value) {
  const face = plain(value);
  const status = state(face.status ?? face.currentness?.status ?? face.state);
  const request = typeof gateway === "function" ? gateway : null;
  const current = Boolean(request) && status === "CURRENT";
  const refusal = current ? "" : human(
    face.refusal,
    request ? `CANONICAL_REQUEST_GATEWAY_${status}` : "CANONICAL_ADAPTER_UNAVAILABLE",
  );
  const reason = current ? "" : human(
    face.reason,
    request
      ? `the shared request gateway is ${status.replaceAll("_", " ").toLowerCase()}`
      : "the canonical request gateway is unavailable",
  );
  return { request, current, status, refusal, reason };
}

function sourceWords(source) {
  const row = plain(source);
  if (!row.file) return "Source address unavailable";
  if (row.line_start === null || row.line_start === undefined) return human(row.file);
  const end = row.line_end === row.line_start || row.line_end === null || row.line_end === undefined
    ? row.line_start : `${row.line_start}–${row.line_end}`;
  return `${human(row.file)} · lines ${end}`;
}

function isFocused(selection, anchor) {
  return String(selection?.focus || "") === String(anchor || "");
}

function postureFrom(selection) {
  const focus = String(selection?.focus || "");
  return focus.endsWith(":pdf") ? "pdf" : "source";
}

function moveTo(move, patch) {
  if (typeof move === "function") move(patch);
}

function firstSection(manuscript, selection) {
  const sections = rows(manuscript.sections);
  return sections.find((item) => isFocused(selection, item.semantic_anchor))
    || sections.find((item) => rows(item.blocks).some((block) => isFocused(selection, block.semantic_anchor)))
    || sections[0] || null;
}

function focusedBlock(section, selection) {
  return rows(section?.blocks).find((block) => isFocused(selection, block.semantic_anchor)) || null;
}

function renderPostures(documentRef, manuscript, selection, move) {
  const wrap = node(documentRef, "div", "manuscript-work__postures");
  const byId = Object.fromEntries(rows(manuscript.postures).map((item) => [item.id, item]));
  for (const [id, label] of [["source", "Source"], ["pdf", "Typeset"]]) {
    const posture = plain(byId[id]);
    const button = node(documentRef, "button", "manuscript-work__posture");
    button.type = "button";
    button.dataset.semanticAnchor = posture.semantic_anchor || `work:manuscript:posture:${id}`;
    button.dataset.state = state(posture.state);
    button.setAttribute("aria-pressed", String(postureFrom(selection) === id));
    button.append(
      node(documentRef, "b", "", label),
      node(documentRef, "span", "", state(posture.state).replaceAll("_", " ")),
    );
    button.addEventListener("click", () => moveTo(move, {
      focus: posture.semantic_anchor || `work:manuscript:posture:${id}`,
      grade: id === "pdf" ? "near" : (selection?.grade || "mid"),
      edge: null,
    }));
    wrap.append(button);
  }
  return wrap;
}

function renderSpine(documentRef, manuscript, selection, move) {
  const spine = node(documentRef, "nav", "manuscript-work__spine");
  spine.setAttribute("aria-label", "Manuscript sections");
  rows(manuscript.sections).forEach((section) => {
    const selected = firstSection(manuscript, selection)?.semantic_anchor === section.semantic_anchor;
    const button = node(documentRef, "button", "manuscript-work__section");
    button.type = "button";
    button.dataset.semanticAnchor = section.semantic_anchor;
    button.dataset.state = state(section.state);
    button.setAttribute("aria-current", String(selected));
    const copy = node(documentRef, "span");
    copy.append(
      node(documentRef, "span", "manuscript-work__section-name", human(section.title, "Untitled section")),
      node(documentRef, "span", "manuscript-work__section-meta", `${section.block_count ?? rows(section.blocks).length} blocks`),
    );
    button.append(copy);
    button.addEventListener("click", () => moveTo(move, {
      focus: section.semantic_anchor,
      grade: selection?.grade === "far" ? "mid" : (selection?.grade || "mid"),
      edge: null,
    }));
    spine.append(button);
  });
  return spine;
}

function renderSourceCanvas(documentRef, manuscript, selection, move) {
  const canvas = node(documentRef, "section", "manuscript-work__canvas");
  canvas.dataset.posture = "source";
  const section = firstSection(manuscript, selection);
  if (!section) {
    const unknown = node(documentRef, "div", "manuscript-work__unknown");
    unknown.append(
      node(documentRef, "div", "", ""),
    );
    unknown.firstChild.append(
      node(documentRef, "h3", "", "Manuscript source is unavailable"),
      node(documentRef, "p", "", human(manuscript.reason, "The canonical Walk document has not been joined.")),
    );
    canvas.append(unknown);
    return canvas;
  }
  const head = node(documentRef, "header", "manuscript-work__canvas-head");
  const title = node(documentRef, "div");
  title.append(
    node(documentRef, "span", "manuscript-work__kicker", "Content-faithful source"),
    node(documentRef, "h3", "", human(section.title, "Untitled section")),
  );
  head.append(title, node(documentRef, "span", "manuscript-work__source", sourceWords(section.source)));
  canvas.append(head);

  const blocks = node(documentRef, "div", "manuscript-work__blocks");
  for (const block of rows(section.blocks)) {
    const selected = isFocused(selection, block.semantic_anchor);
    const button = node(documentRef, "button", "manuscript-work__block");
    button.type = "button";
    button.dataset.semanticAnchor = block.semantic_anchor;
    button.dataset.kind = human(block.kind, "content").toLowerCase();
    button.dataset.state = block.source?.file ? "COMPLETE" : "UNKNOWN";
    button.setAttribute("aria-current", String(selected));
    const copy = node(documentRef, "span", "manuscript-work__block-copy");
    copy.append(
      node(documentRef, "span", "manuscript-work__block-kind", human(block.kind, "content")),
      node(documentRef, "span", "manuscript-work__block-words", human(block.words, "Content unavailable")),
      node(documentRef, "span", "manuscript-work__block-source", sourceWords(block.source)),
    );
    button.append(copy);
    button.addEventListener("click", () => moveTo(move, {
      focus: block.semantic_anchor,
      grade: selected ? "audit" : "near",
      edge: null,
      exposition: selected ? "E6" : (selection?.exposition || "E2"),
    }));
    blocks.append(button);
  }
  canvas.append(blocks);
  return canvas;
}

function renderTypeset(documentRef, manuscript) {
  const canvas = node(documentRef, "section", "manuscript-work__canvas");
  canvas.dataset.posture = "pdf";
  const pdf = rows(manuscript.postures).find((item) => item.id === "pdf") || {};
  const body = node(documentRef, "div", "manuscript-work__unknown");
  const copy = node(documentRef, "div");
  if (state(pdf.state) === "COMPLETE") {
    copy.append(
      node(documentRef, "span", "manuscript-work__kicker", "Geometry face"),
      node(documentRef, "h3", "", "Typeset manuscript is available"),
      node(documentRef, "p", "", "Open the compiled geometry while retaining the same source-addressed manuscript identity."),
    );
  } else {
    copy.append(
      node(documentRef, "span", "manuscript-work__kicker", state(pdf.state).replaceAll("_", " ")),
      node(documentRef, "h3", "", "Typeset geometry has not joined this view"),
      node(documentRef, "p", "", human(pdf.reason, "The exact PDF and SyncTeX evidence are unavailable.")),
    );
  }
  if (pdf.continuation) {
    const link = node(documentRef, "a", "", state(pdf.state) === "COMPLETE" ? "Open geometry face" : "Inspect the missing PDF evidence");
    link.href = pdf.continuation;
    link.dataset.semanticAnchor = pdf.semantic_anchor || "work:manuscript:posture:pdf";
    copy.append(link);
  }
  body.append(copy);
  canvas.append(body);
  return canvas;
}

function renderMargin(documentRef, manuscript, selection, move) {
  const margin = node(documentRef, "aside", "manuscript-work__margin");
  margin.setAttribute("aria-label", "Manuscript evidence and continuity");
  margin.append(node(documentRef, "h3", "", "Alongside the page"));
  const visible = new Set(["review", "feedback", "versions", "compile", "redline"]);
  for (const item of rows(manuscript.postures).filter((row) => visible.has(row.id))) {
    const button = node(documentRef, "button", "manuscript-work__signal");
    button.type = "button";
    button.dataset.semanticAnchor = item.semantic_anchor;
    button.dataset.state = state(item.state);
    button.setAttribute("aria-current", String(isFocused(selection, item.semantic_anchor)));
    const evidence = plain(item.evidence);
    const count = evidence.open ?? evidence.findings ?? evidence.count ?? evidence.pages;
    const suffix = count === undefined ? state(item.state).replaceAll("_", " ") : `${count} · ${state(item.state).replaceAll("_", " ")}`;
    button.append(
      node(documentRef, "b", "", human(item.label, item.id)),
      node(documentRef, "span", "", suffix),
    );
    button.title = human(item.reason);
    button.addEventListener("click", () => moveTo(move, {
      focus: item.semantic_anchor,
      grade: "near",
      edge: null,
      exposition: "E3",
    }));
    margin.append(button);
  }
  return margin;
}

async function requestThrough(gateway, requestSpec, overrides = {}) {
  if (!gateway?.request) throw new Error(gateway?.refusal || "shared request gateway is unavailable");
  if (overrides.write === true && !gateway.current) {
    throw new Error(`${gateway.refusal}: ${gateway.reason}`);
  }
  const spec = plain(requestSpec);
  if (!spec.route || !spec.method) throw new Error("canonical request specification is incomplete");
  const query = { ...plain(spec.query), ...plain(overrides.query) };
  const hasBody = Object.prototype.hasOwnProperty.call(overrides, "body");
  const body = hasBody ? overrides.body : { ...plain(spec.body) };
  return gateway.request({
    method: String(spec.method).toUpperCase(),
    route: String(spec.route),
    query,
    body,
    body_kind: human(spec.body_kind, "json"),
  });
}

function responseWords(value, fallback) {
  const row = plain(value);
  return human(row.message ?? row.note ?? row.status ?? row.state ?? row.error, fallback);
}

function actionButton(documentRef, {
  anchor, label, detail, disabled = false, primary = false, write = false, gateway = null,
}) {
  const button = node(documentRef, "button", "manuscript-work__act");
  button.type = "button";
  button.dataset.semanticAnchor = anchor;
  button.dataset.primary = String(primary);
  if (write) {
    button.dataset.writeControl = "true";
    button.dataset.requestGatewayState = gateway?.status || "UNKNOWN";
    button.dataset.refusal = gateway?.refusal || "";
    if (!gateway?.current) {
      button.setAttribute("aria-describedby", "manuscript-request-gateway-refusal");
      button.title = gateway?.refusal || "Canonical request gateway unavailable";
    }
  }
  button.disabled = disabled;
  button.append(node(documentRef, "span", "", label));
  if (detail) button.append(node(documentRef, "small", "", detail));
  return button;
}

function renderActionLayer(documentRef, manuscript, selection, gateway) {
  const actions = plain(manuscript.actions);
  const editor = plain(actions.editor);
  // The guard belongs to the displayed owner observation, never textarea text.
  // Only an exact save acknowledgement can advance this fixed-file basis.
  let sourceDigest = editor.expected_source_digest;
  let sourceEffectHold = null;
  const selectionIdentity=editor.selection_identity;
  const section = firstSection(manuscript, selection);
  const block = focusedBlock(section, selection);
  const layer = node(documentRef, "section", "manuscript-work__actions");
  layer.dataset.semanticAnchor = actions.semantic_anchor || "work:manuscript:actions";
  layer.dataset.state = state(actions.state);
  layer.setAttribute("aria-label", "Manuscript editor, versions and source correspondence");

  const editing = node(documentRef, "div", "manuscript-work__editing");
  const editorHead = node(documentRef, "header", "manuscript-work__editor-head");
  const editorCopy = node(documentRef, "div");
  editorCopy.append(
    node(documentRef, "span", "manuscript-work__kicker", "Canonical source action"),
    node(documentRef, "h3", "", "Write, save, compile, descend"),
    node(documentRef, "p", "", state(editor.state) === "COMPLETE"
      ? "The full source stays the object. Saving banks a version through the existing projection door; compile and SyncTeX retain the same file identity."
      : human(editor.reason, "Complete editor source has not been joined.")),
  );
  editorHead.append(editorCopy, node(documentRef, "span", "manuscript-work__file", human(editor.file, "Exact file UNKNOWN")));
  editing.append(editorHead);

  const textarea = node(documentRef, "textarea", "manuscript-work__editor");
  textarea.dataset.semanticAnchor = editor.semantic_anchor || "work:manuscript:editor";
  textarea.dataset.state = state(editor.state);
  textarea.setAttribute("aria-label", "Manuscript source editor");
  textarea.spellcheck = false;
  textarea.value = String(editor.content || "");
  textarea.dataset.writeControl = "true";
  textarea.dataset.requestGatewayState = gateway.status;
  textarea.dataset.refusal = gateway.refusal;
  textarea.disabled = state(editor.state) !== "COMPLETE" || !gateway.current;
  if (!gateway.current) {
    textarea.setAttribute("aria-describedby", "manuscript-request-gateway-refusal");
    textarea.title = gateway.refusal;
  }
  editing.append(textarea);

  if (!gateway.current) {
    const refusal = node(documentRef, "div", "manuscript-work__gateway-refusal");
    refusal.id = "manuscript-request-gateway-refusal";
    refusal.dataset.requestGatewayState = gateway.status;
    refusal.dataset.refusal = gateway.refusal;
    refusal.setAttribute("role", "alert");
    refusal.append(
      node(documentRef, "b", "", `Writes refused · ${gateway.status.replaceAll("_", " ")}`),
      documentRef.createTextNode(`${gateway.reason}. No source edit, compile, restore, comment, or pipeline act will be sent. (${gateway.refusal})`),
    );
    editing.append(refusal);
  }

  const statusLine = node(documentRef, "p", "manuscript-work__act-state", state(editor.state) === "COMPLETE"
    ? "Ready · no request leaves this surface until you choose an exact act."
    : `UNKNOWN · ${human(editor.reason, "editor evidence is absent")}`);
  statusLine.setAttribute("role", "status");
  const actionRow = node(documentRef, "div", "manuscript-work__action-row");
  const save = plain(editor.save);
  const saveButton = actionButton(documentRef, {
    anchor: save.semantic_anchor || "work:manuscript:action:save",
    label: "Save new version",
    detail: "Bank editor save",
    disabled: !gateway.current || textarea.disabled || state(save.state) !== "COMPLETE",
    primary: true,
    write: true,
    gateway,
  });
  saveButton.addEventListener("click", async () => {
    if(sourceEffectHold){statusLine.textContent=sourceEffectHold;return;}
    const submittedDigest = sourceDigest, submittedText = textarea.value;
    saveButton.disabled = true;
    statusLine.textContent = "Saving through the canonical projection door…";
    try {
      const result = await requestThrough(gateway, save.request, {
        query: { expected_source_digest: submittedDigest,expected_selection:selectionIdentity }, body: submittedText, write: true });
      requireSourceCompletion(result,{selectionIdentity});
      if (sourceDigest !== submittedDigest) return;
      if (result?.ok !== true || result.source_committed !== true || result?.file !== editor.file || result.consumed_source_digest !== submittedDigest || result.selection_identity!==selectionIdentity ||
          !/^sha256:[0-9a-f]{64}$/.test(result.expected_source_digest)) {
        throw Error('Save acknowledgement lacks this exact file basis; inspect current source. Draft retained.');
      }
      sourceDigest = result.expected_source_digest;
      statusLine.textContent = responseWords(result, "Saved and banked as a new version.");
      if (result.maintenance_warnings?.length) statusLine.textContent += ' Source committed; maintenance needs inspection.';
    } catch (error) {
      const effect=sourceEffectFromError(error,{selectionIdentity});
      if(effect?.suppressRetry||error.sourceEffectUnverified)sourceEffectHold=effect?.message||error.message;
      statusLine.textContent=sourceEffectHold||`REFUSED · ${human(error?.message, 'save failed')}`;
    } finally {
      saveButton.disabled = !!sourceEffectHold || !gateway.current || textarea.disabled || state(save.state) !== "COMPLETE";
    }
  });

  const compile = plain(actions.compile);
  const compileButton = actionButton(documentRef, {
    anchor: compile.semantic_anchor || "work:manuscript:action:compile",
    label: "Recompile",
    detail: "Local-safe queue",
    disabled: !gateway.current || state(compile.state) !== "COMPLETE",
    write: true,
    gateway,
  });
  compileButton.addEventListener("click", async () => {
    compileButton.disabled = true;
    statusLine.textContent = "Queuing the canonical compile…";
    try {
      const result = await requestThrough(gateway, compile.request, { write: true });
      statusLine.textContent = responseWords(result, "Compile queued; the latest save will carry its result.");
    } catch (error) {
      statusLine.textContent = `REFUSED · ${human(error?.message, "compile failed")}`;
    } finally {
      compileButton.disabled = !gateway.current || state(compile.state) !== "COMPLETE";
    }
  });

  const synctex = plain(actions.synctex);
  const locateButton = actionButton(documentRef, {
    anchor: synctex.semantic_anchor || "work:manuscript:action:synctex",
    label: "Locate in PDF",
    detail: block ? `Line ${block.source?.line_start ?? "UNKNOWN"}` : "Selected section",
    disabled: !gateway.request || state(synctex.state) !== "COMPLETE" || !(block || section),
  });
  locateButton.addEventListener("click", async () => {
    const source = plain((block || section)?.source);
    statusLine.textContent = "Following the exact source address into typeset geometry…";
    try {
      const result = await requestThrough(gateway, synctex.locate, {
        query: { section: human(section?.id), line: source.line_start ?? "" },
      });
      statusLine.textContent = responseWords(result, "SyncTeX location resolved.");
    } catch (error) {
      statusLine.textContent = `UNKNOWN · ${human(error?.message, "SyncTeX location unavailable")}`;
    }
  });
  const followButton = actionButton(documentRef, {
    anchor: "work:manuscript:action:follow",
    label: "Check PDF freshness",
    detail: "Read only",
    disabled: !gateway.request || state(synctex.state) !== "COMPLETE",
  });
  followButton.addEventListener("click", async () => {
    statusLine.textContent = "Checking source and PDF freshness…";
    try {
      const result = await requestThrough(gateway, synctex.follow);
      statusLine.textContent = responseWords(result, "Freshness evidence returned.");
    } catch (error) {
      statusLine.textContent = `UNKNOWN · ${human(error?.message, "freshness unavailable")}`;
    }
  });
  actionRow.append(saveButton, compileButton, locateButton, followButton);
  editing.append(actionRow, statusLine);

  const rail = node(documentRef, "aside", "manuscript-work__version-rail");
  rail.dataset.semanticAnchor = "work:manuscript:version-trail";
  rail.append(
    node(documentRef, "span", "manuscript-work__kicker", "Version trajectory"),
    node(documentRef, "h3", "", "Compare, redline, restore"),
    node(documentRef, "p", "", "Restoring never rewinds history: an explicitly restorable editor save becomes a new save at the tip."),
  );
  const versions = rows(plain(actions.versions).rows);
  const selectors = node(documentRef, "div", "manuscript-work__selectors");
  const makeSelect = (label, index) => {
    const wrap = node(documentRef, "label", "manuscript-work__selector", label);
    const select = node(documentRef, "select");
    select.setAttribute("aria-label", label);
    for (const [rowIndex, version] of versions.entries()) {
      const option = node(documentRef, "option", "", human(version.label, version.version_id || `Version ${rowIndex + 1}`));
      option.value = String(version.version_id || "");
      option.dataset.restorable = String(Boolean(version.restorable));
      select.append(option);
    }
    if (versions[index]) select.value = String(versions[index].version_id || "");
    wrap.append(select);
    return { wrap, select };
  };
  const from = makeSelect("Earlier", 0);
  const to = makeSelect("Later", Math.max(0, versions.length - 1));
  selectors.append(from.wrap, to.wrap);
  rail.append(selectors);

  const versionActions = node(documentRef, "div", "manuscript-work__action-row");
  const compare = plain(actions.redline);
  const compareButton = actionButton(documentRef, {
    anchor: compare.semantic_anchor || "work:manuscript:action:redline",
    label: "Open redline",
    detail: "Read-only comparison",
    disabled: !gateway.request || state(compare.state) !== "COMPLETE" || versions.length < 2,
  });
  compareButton.addEventListener("click", async () => {
    statusLine.textContent = "Aligning the two banked source states…";
    try {
      const result = await requestThrough(gateway, compare.request, { query: { a: from.select.value, b: to.select.value } });
      statusLine.textContent = responseWords(result, "Redline evidence returned.");
    } catch (error) {
      statusLine.textContent = `REFUSED · ${human(error?.message, "redline failed")}`;
    }
  });

  const restore = plain(actions.restore);
  const restoreButton = actionButton(documentRef, {
    anchor: restore.semantic_anchor || "work:manuscript:action:restore",
    label: "Restore as new save",
    detail: "Arm before banking",
    disabled: true,
    write: true,
    gateway,
  });
  const resetRestore = () => {
    const current = versions.find((version) => String(version.version_id || "") === from.select.value);
    restoreButton.dataset.armed = "false";
    restoreButton.firstChild.textContent = "Restore as new save";
    restoreButton.disabled = !!sourceEffectHold || !gateway.current || state(restore.state) !== "COMPLETE" || !current?.restorable;
  };
  from.select.addEventListener("change", resetRestore);
  resetRestore();
  restoreButton.addEventListener("click", async () => {
    if(sourceEffectHold){statusLine.textContent=sourceEffectHold;return;}
    if (restoreButton.dataset.armed !== "true") {
      restoreButton.dataset.armed = "true";
      restoreButton.firstChild.textContent = "Confirm new save";
      statusLine.textContent = "Armed locally · confirm to bank this historical source as a new save.";
      return;
    }
    restoreButton.disabled = true;
    const inspectedDigest = sourceDigest, selectedVersion = from.select.value;
    statusLine.textContent = "Restoring through the canonical version door…";
    try {
      const result = await requestThrough(gateway, restore.request, {
        body: { ...plain(restore.request?.body), version_id: selectedVersion,
          expected_source_digest: inspectedDigest,expected_selection:selectionIdentity }, write: true,
      });
      requireSourceCompletion(result,{selectionIdentity});
      if (result?.ok !== true || result.source_committed !== true || result.file !== editor.file ||
          result.restored_from !== selectedVersion || result.consumed_source_digest !== inspectedDigest) {
        throw Error('Restore acknowledgement does not identify this inspected source and selected version.');
      }
      // The textarea still holds its earlier authored draft; restoring historical
      // bytes must not silently rebind that displayed draft to the restored file.
      sourceDigest = null;
      statusLine.textContent = responseWords(result, "Historical bytes restored and banked as a new save.");
      if (result.maintenance_warnings?.length) statusLine.textContent += ' Source restored; maintenance needs inspection.';
    } catch (error) {
      const effect=sourceEffectFromError(error,{selectionIdentity});
      if(effect?.suppressRetry||error.sourceEffectUnverified)sourceEffectHold=effect?.message||error.message;
      statusLine.textContent=sourceEffectHold||`REFUSED · ${human(error?.message, 'restore failed')}`;
    } finally {
      resetRestore();
    }
  });
  versionActions.append(compareButton, restoreButton);
  rail.append(versionActions);

  const versionTrail = node(documentRef, "div", "manuscript-work__history");
  for (const version of versions.slice(-5)) {
    const item = node(documentRef, "span", "manuscript-work__version");
    item.dataset.semanticAnchor = version.semantic_anchor;
    item.append(
      node(documentRef, "b", "", human(version.label, "Banked state")),
      node(documentRef, "span", "", [human(version.actor, "actor UNKNOWN"), human(version.created_at)].filter(Boolean).join(" · ")),
    );
    versionTrail.append(item);
  }
  if (!versions.length) versionTrail.append(node(documentRef, "p", "manuscript-work__act-state", `UNKNOWN · ${human(plain(actions.versions).reason, "no version evidence joined")}`));
  rail.append(versionTrail);

  const authority = plain(actions.provider_authority);
  const authorityFace = node(documentRef, "div", "manuscript-work__authority");
  authorityFace.dataset.state = state(authority.state);
  authorityFace.append(
    node(documentRef, "b", "", `${state(authority.state).replaceAll("_", " ")} · stronger seat authority`),
    documentRef.createTextNode(`${human(authority.reason, "not supplied")}. The canonical projection endpoints do not require it.`),
  );
  rail.append(authorityFace);
  layer.append(editing, rail);
  return layer;
}

function renderLaunchControls(documentRef, launch, gateway) {
  const section = node(documentRef, "section", "manuscript-work__launch");
  section.dataset.semanticAnchor = launch.semantic_anchor || "work:pipeline:launch";
  section.dataset.state = state(launch.state);
  const head = node(documentRef, "header", "manuscript-work__launch-head");
  const copy = node(documentRef, "div");
  copy.append(
    node(documentRef, "span", "manuscript-work__kicker", "Governed launch"),
    node(documentRef, "h4", "", "Choose one bounded pipeline act"),
    node(documentRef, "p", "", "Local-safe acts stay local. Model-heavy acts bank a work order and spawn nothing here."),
  );
  const authority = plain(launch.provider_authority);
  const authorityNote = node(documentRef, "div", "manuscript-work__authority");
  authorityNote.dataset.state = state(authority.state);
  authorityNote.append(
    node(documentRef, "b", "", `${state(authority.state).replaceAll("_", " ")} · provider authority`),
    documentRef.createTextNode("Not an endpoint precondition"),
  );
  head.append(copy, authorityNote);
  section.append(head);

  const actions = rows(launch.actions);
  const roster = node(documentRef, "div", "manuscript-work__launch-roster");
  const detail = node(documentRef, "div");
  let selectedIndex = 0;
  let armed = false;
  const choices = [];

  const drawDetail = () => {
    const action = plain(actions[selectedIndex]);
    detail.replaceChildren();
    if (!action.action) {
      detail.append(node(documentRef, "p", "manuscript-work__act-state", `UNKNOWN · ${human(launch.reason, "launch roster unavailable")}`));
      return;
    }
    const panel = node(documentRef, "div", "manuscript-work__launch-detail");
    panel.dataset.semanticAnchor = action.semantic_anchor;
    panel.dataset.state = state(action.state);
    const words = node(documentRef, "div");
    words.append(
      node(documentRef, "span", "manuscript-work__kicker", `${human(action.cost_class, "cost UNKNOWN")} · ${human(action.organ, "organ UNKNOWN")}`),
      node(documentRef, "h4", "", human(action.label, action.action)),
      node(documentRef, "p", "", human(action.what, action.effect_on_success)),
    );
    const preflight = node(documentRef, "div", "manuscript-work__preflight");
    const pf = plain(action.preflight);
    for (const [label, value] of [
      ["actor", plain(pf.actor)], ["profile", plain(pf.profile)], ["arming", plain(pf.arming)], ["authority", plain(pf.provider_authority)],
    ]) {
      const item = node(documentRef, "span", "", `${label}: ${human(value.value ?? value.mode ?? (value.required ? "required" : "not required"), state(value.state).replaceAll("_", " "))}`);
      item.dataset.state = state(value.state);
      preflight.append(item);
    }
    words.append(preflight);

    const confirm = node(documentRef, "button", "manuscript-work__launch-confirm");
    confirm.type = "button";
    confirm.dataset.semanticAnchor = `${action.semantic_anchor}:confirm`;
    confirm.dataset.armed = String(armed);
    confirm.dataset.writeControl = "true";
    confirm.dataset.requestGatewayState = gateway.status;
    confirm.dataset.refusal = gateway.refusal;
    confirm.disabled = !gateway.current || state(action.state) !== "COMPLETE";
    if (!gateway.current) {
      confirm.setAttribute("aria-describedby", "manuscript-request-gateway-refusal");
      confirm.title = gateway.refusal;
    }
    const verb = action.model_heavy ? "Bank work order" : "Run local act";
    confirm.append(
      node(documentRef, "span", "", armed ? `Confirm · ${verb}` : verb),
      node(documentRef, "small", "", action.arm_required ? (armed ? "Armed · one exact request" : "First press arms") : "One exact request"),
    );
    const status = node(documentRef, "p", "manuscript-work__act-state", action.model_heavy
      ? "Bank-before-effect · this surface never spawns a model."
      : "Local-safe · effect remains owned by the canonical storyboard endpoint.");
    status.setAttribute("role", "status");
    confirm.addEventListener("click", async () => {
      if (action.arm_required && !armed) {
        armed = true;
        drawDetail();
        return;
      }
      confirm.disabled = true;
      status.textContent = action.model_heavy ? "Banking the exact work order…" : "Calling the exact local action…";
      try {
        const result = await requestThrough(gateway, action.request, {
          body: { ...plain(action.request?.body), armed: Boolean(action.arm_required) },
          write: true,
        });
        status.textContent = responseWords(result, action.model_heavy ? "Work order banked; no model spawned." : "Local action accepted.");
      } catch (error) {
        status.textContent = `REFUSED · ${human(error?.message, "launch failed")}`;
      } finally {
        armed = false;
        confirm.disabled = !gateway.current || state(action.state) !== "COMPLETE";
        confirm.dataset.armed = "false";
      }
    });
    const controls = node(documentRef, "div");
    controls.append(confirm, status);
    panel.append(words, controls);
    detail.append(panel);
  };

  actions.forEach((action, index) => {
    const button = node(documentRef, "button", "manuscript-work__launch-choice");
    button.type = "button";
    button.dataset.semanticAnchor = action.semantic_anchor;
    button.dataset.cost = human(action.cost_class, "unknown");
    button.dataset.state = state(action.state);
    button.setAttribute("aria-pressed", String(index === selectedIndex));
    button.append(
      node(documentRef, "b", "", human(action.label, action.action)),
      node(documentRef, "span", "", `${human(action.organ, "organ UNKNOWN")} · ${human(action.cost_class, "cost UNKNOWN")}`),
    );
    button.addEventListener("click", () => {
      selectedIndex = index;
      armed = false;
      choices.forEach((choice, choiceIndex) => choice.setAttribute("aria-pressed", String(choiceIndex === selectedIndex)));
      drawDetail();
    });
    choices.push(button);
    roster.append(button);
  });
  if (!actions.length) roster.append(node(documentRef, "p", "manuscript-work__act-state", "UNKNOWN · no launch roster is joined."));
  section.append(roster, detail);
  drawDetail();
  return section;
}

function renderPipeline(documentRef, pipeline, selection, move, gateway) {
  const section = node(documentRef, "section", "manuscript-work__pipeline");
  section.dataset.semanticAnchor = pipeline.semantic_anchor || "work:pipeline";
  section.dataset.state = state(pipeline.state);
  const head = node(documentRef, "header", "manuscript-work__pipeline-head");
  const copy = node(documentRef, "div");
  const brief = plain(pipeline.brief);
  const briefBody = plain(brief.brief);
  copy.append(
    node(documentRef, "span", "manuscript-work__kicker", "Build and release journey"),
    node(documentRef, "h3", "", `Pipeline · ${human(pipeline.position, "position unknown")}`),
    node(documentRef, "p", "", human(briefBody.glance ?? brief.glance, human(pipeline.reason, "Pipeline evidence unavailable"))),
  );
  head.append(copy, node(documentRef, "p", "manuscript-work__next", human(briefBody.next_line, "Next action is UNKNOWN until the release projection provides it.")));
  section.append(head);

  const stages = rows(pipeline.release_states);
  const release = node(documentRef, "div", "manuscript-work__release");
  release.style.setProperty("--mw-stages", String(Math.max(1, stages.length)));
  release.setAttribute("aria-label", "Release chain");
  for (const stage of stages) {
    const button = node(documentRef, "button", "manuscript-work__stage");
    button.type = "button";
    button.dataset.semanticAnchor = stage.semantic_anchor;
    button.dataset.status = state(stage.status);
    button.setAttribute("aria-current", String(isFocused(selection, stage.semantic_anchor)));
    button.append(
      node(documentRef, "span", "manuscript-work__stage-name", human(stage.label, "Stage")),
      node(documentRef, "span", "manuscript-work__stage-state", `${state(stage.status).replaceAll("_", " ")} · ${human(stage.next_action, "next UNKNOWN")}`),
    );
    button.addEventListener("click", () => moveTo(move, {
      focus: stage.semantic_anchor,
      grade: "near",
      edge: null,
      exposition: "E2",
    }));
    release.append(button);
  }
  if (!stages.length) {
    release.append(node(documentRef, "p", "", "UNKNOWN · The release chain is not joined."));
  }
  section.append(release);

  const mechanisms = node(documentRef, "div", "manuscript-work__mechanisms");
  mechanisms.setAttribute("aria-label", "Pipeline mechanisms");
  for (const mechanism of rows(pipeline.mechanisms)) {
    const button = node(documentRef, "button", "manuscript-work__mechanism", human(mechanism.label, mechanism.id));
    button.type = "button";
    button.dataset.semanticAnchor = mechanism.semantic_anchor;
    button.dataset.state = state(mechanism.state);
    button.title = human(mechanism.reason);
    button.addEventListener("click", () => moveTo(move, {
      focus: mechanism.semantic_anchor,
      grade: "near",
      edge: null,
      exposition: "E3",
    }));
    mechanisms.append(button);
  }
  section.append(mechanisms, renderLaunchControls(documentRef, plain(pipeline.launch), gateway));
  return section;
}

function renderAudit(documentRef, workbench, selection) {
  if (selection?.grade !== "audit") return null;
  const focus = String(selection?.focus || "");
  const manuscript = plain(workbench.manuscript);
  const section = rows(manuscript.sections).find((item) => item.semantic_anchor === focus);
  const block = rows(manuscript.sections).flatMap((item) => rows(item.blocks)).find((item) => item.semantic_anchor === focus);
  const posture = rows(manuscript.postures).find((item) => item.semantic_anchor === focus);
  const stage = rows(plain(workbench.pipeline).release_states).find((item) => item.semantic_anchor === focus);
  const subject = block || section || posture || stage;
  if (!subject) return null;
  const audit = node(documentRef, "div", "manuscript-work__audit");
  audit.dataset.semanticAnchor = focus;
  audit.append(node(documentRef, "b", "", "Selected evidence · "));
  audit.append(documentRef.createTextNode(
    block || section ? sourceWords(subject.source)
      : human(subject.reason ?? subject.next_action, "Exact evidence remains behind the typed continuation."),
  ));
  return audit;
}

export function installManuscriptWorkSurfaceStyles(documentRef = document) {
  if (documentRef.getElementById(STYLE_ID)) return;
  const style = documentRef.createElement("style");
  style.id = STYLE_ID;
  style.textContent = CSS;
  documentRef.head.append(style);
}

export function renderManuscriptWorkSurface(mount, workModel, options = {}) {
  if (!mount) throw new TypeError("mount is required");
  const documentRef = mount.ownerDocument || document;
  installManuscriptWorkSurfaceStyles(documentRef);
  const model = plain(workModel);
  const workbench = plain(model.workbench);
  const manuscript = plain(workbench.manuscript);
  const pipeline = plain(workbench.pipeline);
  const selection = plain(options.selection);
  const move = options.move;
  const request = requestGatewayFace(options.request, options.requestState ?? options.request_state);

  const root = node(documentRef, "article", "manuscript-work");
  root.dataset.schema = MANUSCRIPT_WORK_SURFACE_SCHEMA;
  root.dataset.semanticAnchor = workbench.semantic_anchor || "work:manuscript-workbench";
  root.dataset.state = state(model.state ?? manuscript.state);
  root.dataset.posture = postureFrom(selection);
  // `data-grade` is reserved by the carrier for actual grade controls.  Keeping
  // descriptive renderer state on that attribute makes every descendant click
  // bubble into the carrier's grade-control delegate and overwrite the intended
  // focus + grade transition.  This is evidence only, never an input control.
  root.dataset.viewGrade = human(selection.grade, "mid");
  root.setAttribute("aria-label", "Manuscript workbench");

  const heading = node(documentRef, "header", "manuscript-work__heading");
  const copy = node(documentRef, "div");
  copy.append(
    node(documentRef, "span", "manuscript-work__kicker", "Manuscript workbench"),
    node(documentRef, "h2", "", human(manuscript.title, model.project || "Manuscript")),
    node(documentRef, "p", "", human(manuscript.fidelity, "Source, geometry, findings and release remain one object.")),
  );
  heading.append(copy, renderPostures(documentRef, manuscript, selection, move));
  root.append(heading);

  const field = node(documentRef, "div", "manuscript-work__field");
  field.append(
    renderSpine(documentRef, manuscript, selection, move),
    postureFrom(selection) === "pdf"
      ? renderTypeset(documentRef, manuscript)
      : renderSourceCanvas(documentRef, manuscript, selection, move),
    renderMargin(documentRef, manuscript, selection, move),
  );
  root.append(
    field,
    renderActionLayer(documentRef, manuscript, selection, request),
    renderPipeline(documentRef, pipeline, selection, move, request),
  );
  const audit = renderAudit(documentRef, workbench, selection);
  if (audit) root.append(audit);

  mount.replaceChildren(root);
  return {
    root,
    schema: MANUSCRIPT_WORK_SURFACE_SCHEMA,
    destroy() { if (root.parentNode === mount) mount.replaceChildren(); },
  };
}

export default renderManuscriptWorkSurface;
