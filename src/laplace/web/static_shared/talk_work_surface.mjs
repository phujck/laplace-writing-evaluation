// A source-bearing Talk work surface over laplace.aisthesis-talk-work/1.
// It owns no fetch, storage, history or write. Every selection returns to the
// carrier through the supplied move callback.

export const TALK_WORK_SURFACE_SCHEMA = "laplace.aisthesis-talk-work-surface/1";

const STYLE_ID = "aisthesis-talk-work-surface-style";

const CSS = `
.talk-work{--tw-rule:color-mix(in srgb,var(--edge2) 62%,transparent);min-width:0;position:relative;overflow-x:clip;padding:.5rem 0 4rem;isolation:isolate}
.talk-work::before{position:absolute;inset:7rem 6% auto;height:18rem;z-index:-1;content:"";background:radial-gradient(ellipse at 48% 40%,color-mix(in srgb,var(--accent) 9%,transparent),transparent 64%);pointer-events:none}
.talk-work button,.talk-work a{min-height:44px}
.talk-work button{font:inherit;color:inherit}
.talk-work__mast{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(18rem,.55fr);gap:clamp(2rem,7vw,8rem);align-items:end;padding:1rem 0 1.8rem;border-bottom:1px solid var(--tw-rule)}
.talk-work__kicker,.talk-work__state,.talk-work__micro{font:600 .62rem/1.35 var(--mono,monospace);letter-spacing:.09em;text-transform:uppercase}
.talk-work__kicker{color:var(--accent)}
.talk-work__mast h2{max-width:22ch;margin:.45rem 0 .6rem;font:640 clamp(1.8rem,3.6vw,3.35rem)/.98 var(--serif,serif);letter-spacing:-.03em}
.talk-work__mast p{max-width:70ch;margin:0;color:var(--ink2);font:clamp(.92rem,1.15vw,1.05rem)/1.64 var(--serif,serif)}
.talk-work__law{position:relative;padding:.9rem 0 .3rem 1.2rem;border-left:2px solid var(--keystone)}
.talk-work__law b{display:block;font:590 .9rem/1.25 var(--display,system-ui)}
.talk-work__law span{display:block;margin-top:.35rem;color:var(--dim);font:.68rem/1.45 var(--mono,monospace)}
.talk-work__primitives{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));position:relative;margin:1.2rem 0 2rem;padding:.55rem 0}
.talk-work__primitives::before{position:absolute;top:1.42rem;right:0;left:0;height:1px;content:"";background:linear-gradient(90deg,var(--keystone),var(--accent),var(--keystone))}
.talk-work__primitive{min-width:0;display:grid;grid-template-columns:1.1rem minmax(0,1fr);gap:.65rem;position:relative;padding:.35rem clamp(.35rem,2vw,1.25rem);border:0;background:transparent;text-align:left;cursor:pointer}
.talk-work__primitive::before{width:.65rem;height:.65rem;margin-top:.25rem;border:1px solid var(--edge2);border-radius:50%;background:var(--bg);content:"";z-index:1}
.talk-work__primitive[data-state=COMPLETE]::before{border-color:var(--keystone);background:var(--keystone)}
.talk-work__primitive[data-state=UNKNOWN]::before{border-style:dashed}
.talk-work__primitive b,.talk-work__primitive span{display:block}
.talk-work__primitive b{font:570 .76rem/1.2 var(--display,system-ui)}
.talk-work__primitive span{display:-webkit-box;margin-top:.22rem;overflow:hidden;color:var(--dim);font:.68rem/1.35 var(--serif,serif);-webkit-box-orient:vertical;-webkit-line-clamp:2}
.talk-work__story{min-width:0;max-width:100%;position:relative;margin:0 0 1.35rem;padding:1rem 0 1.2rem}
.talk-work__story-head{display:flex;justify-content:space-between;align-items:baseline;gap:1rem;margin-bottom:.85rem}
.talk-work__story-head h3{margin:0;font:620 1rem/1.2 var(--display,system-ui)}
.talk-work__story-head span{color:var(--dim)}
.talk-work__ribbon{width:100%;min-width:0;max-width:100%;display:grid;grid-template-columns:repeat(var(--tw-beats),minmax(6.5rem,1fr));position:relative;overflow-x:auto;contain:inline-size;padding:.2rem 0 .75rem;scrollbar-width:thin}
.talk-work__ribbon::before{position:absolute;top:1.05rem;right:0;left:0;height:2px;content:"";background:linear-gradient(90deg,color-mix(in srgb,var(--accent) 78%,transparent),var(--tw-rule) 58%,transparent)}
.talk-work__beat{min-width:6.5rem;display:grid;grid-template-rows:1.35rem auto;gap:.5rem;position:relative;padding:0 .65rem;border:0;background:transparent;text-align:left;cursor:pointer}
.talk-work__beat::before{width:.74rem;height:.74rem;border:1px solid var(--edge2);border-radius:50%;background:var(--bg);content:"";z-index:1}
.talk-work__beat[data-state=UNKNOWN]::before{border-style:dashed}
.talk-work__beat[aria-current=true]::before{border-color:var(--accent);background:var(--accent);box-shadow:0 0 1.1rem color-mix(in srgb,var(--accent) 48%,transparent)}
.talk-work__beat>span,.talk-work__beat b,.talk-work__beat span{display:block}
.talk-work__beat b{color:var(--ink2);font:560 .7rem/1.28 var(--display,system-ui)}
.talk-work__beat span span{margin-top:.18rem;color:var(--dim);font:.56rem/1.2 var(--mono,monospace)}
.talk-work__stage{display:grid;grid-template-columns:minmax(10rem,.55fr) minmax(20rem,1.25fr) minmax(12rem,.52fr);gap:clamp(1.3rem,4vw,4.5rem);min-height:31rem;position:relative;padding:clamp(1.6rem,4vw,3.5rem) 0;border-block:1px solid var(--tw-rule)}
.talk-work__stage::before{position:absolute;top:3.6rem;bottom:3.6rem;left:calc(29% + 1rem);width:1px;content:"";background:linear-gradient(transparent,var(--accent) 18%,var(--accent) 62%,transparent)}
.talk-work__origin{align-self:center;padding-right:.5rem}
.talk-work__origin h4,.talk-work__cadence h4{margin:0 0 .8rem;color:var(--dim);font:600 .62rem/1 var(--mono,monospace);letter-spacing:.1em;text-transform:uppercase}
.talk-work__origin p{margin:0;color:var(--ink2);font:.9rem/1.6 var(--serif,serif)}
.talk-work__origin-source{display:block;margin-top:1.1rem;padding-top:.75rem;border-top:1px solid var(--tw-rule);color:var(--dim);font:.62rem/1.45 var(--mono,monospace)}
.talk-work__scene{min-width:0;align-self:center;position:relative;padding:clamp(1rem,2vw,1.8rem) 0 clamp(1.6rem,4vw,3rem) clamp(1.4rem,3vw,3rem)}
.talk-work__scene::before{position:absolute;inset:-2rem -2rem -1rem -3rem;border:1px solid color-mix(in srgb,var(--accent) 23%,transparent);border-radius:50%;content:"";transform:rotate(-4deg);pointer-events:none}
.talk-work__ordinal{display:block;color:var(--accent);font:500 clamp(2.4rem,7vw,6rem)/.8 var(--serif,serif);opacity:.33}
.talk-work__scene h3{max-width:18ch;margin:.35rem 0 .9rem;font:640 clamp(1.55rem,3.3vw,3rem)/1.04 var(--serif,serif);letter-spacing:-.025em}
.talk-work__claim{max-width:48ch;margin:0;color:var(--ink);font:clamp(1rem,1.55vw,1.25rem)/1.62 var(--serif,serif)}
.talk-work__visual{display:inline-block;margin-top:1.2rem;padding:.42rem 0;border-bottom:1px solid var(--accent);color:var(--gold-light);font:.74rem/1.35 var(--display,system-ui)}
.talk-work__scene[data-expanded=true] .talk-work__motivation{display:block}
.talk-work__motivation{display:none;max-width:55ch;margin:1rem 0 0;padding-left:1rem;border-left:1px solid var(--keystone);color:var(--ink2);font:.86rem/1.55 var(--serif,serif)}
.talk-work__cadence{align-self:stretch;padding-left:1rem;border-left:1px solid var(--tw-rule)}
.talk-work__cadence-rail{display:grid;gap:0}
.talk-work__pulse{width:100%;display:grid;grid-template-columns:.8rem minmax(0,1fr);gap:.65rem;position:relative;padding:.58rem 0;border:0;background:transparent;text-align:left;cursor:pointer}
.talk-work__pulse::before{width:.5rem;height:.5rem;margin-top:.2rem;border:1px solid var(--edge2);background:var(--bg);content:"";transform:rotate(45deg)}
.talk-work__pulse[data-state=COMPLETE]::before{border-color:var(--ok);background:var(--ok)}
.talk-work__pulse[data-state=REFUSED]::before{border-color:var(--bad)}
.talk-work__pulse b,.talk-work__pulse span{display:block}
.talk-work__pulse b{font:550 .72rem/1.25 var(--display,system-ui)}
.talk-work__pulse span{margin-top:.18rem;color:var(--dim);font:.58rem/1.35 var(--mono,monospace)}
.talk-work__trajectory{position:relative;padding:2rem 0 1.2rem}
.talk-work__trajectory-head{display:grid;grid-template-columns:minmax(0,1fr) minmax(16rem,.6fr);gap:2rem;align-items:end}
.talk-work__trajectory h3{margin:.25rem 0 0;font:620 clamp(1.1rem,2vw,1.6rem)/1.2 var(--serif,serif)}
.talk-work__trajectory p{margin:0;color:var(--ink2);font:.82rem/1.5 var(--serif,serif)}
.talk-work__flow{display:grid;grid-template-columns:repeat(6,minmax(5.5rem,1fr));position:relative;margin-top:1.4rem}
.talk-work__flow::before{position:absolute;top:1.1rem;right:0;left:0;height:1px;content:"";background:linear-gradient(90deg,var(--accent),var(--keystone),var(--tw-rule))}
.talk-work__flow-step{min-width:0;display:grid;grid-template-rows:1.45rem auto;gap:.42rem;position:relative;padding:0 .55rem;border:0;background:transparent;text-align:left;cursor:pointer}
.talk-work__flow-step::before{width:.7rem;height:.7rem;border:1px solid var(--edge2);border-radius:50%;background:var(--bg);content:"";z-index:1}
.talk-work__flow-step[data-state=COMPLETE]::before{border-color:var(--ok);background:var(--ok)}
.talk-work__flow-step[data-state=UNKNOWN]::before{border-style:dashed}
.talk-work__flow-step[data-state=REFUSED]::before{border-color:var(--bad);border-radius:0;transform:rotate(45deg)}
.talk-work__flow-step>span,.talk-work__flow-step b,.talk-work__flow-step span{display:block}
.talk-work__flow-step b{color:var(--ink2);font:560 .68rem/1.28 var(--display,system-ui)}
.talk-work__flow-step span span{margin-top:.2rem;color:var(--dim);font:.55rem/1.25 var(--mono,monospace)}
.talk-work__unknown{min-height:18rem;display:grid;place-items:center;padding:2rem;border-block:1px dashed var(--edge2);background:repeating-linear-gradient(135deg,transparent 0,transparent 14px,color-mix(in srgb,var(--edge2) 8%,transparent) 14px,color-mix(in srgb,var(--edge2) 8%,transparent) 15px);text-align:center}
.talk-work__unknown h3{margin:0;font:620 1.35rem/1.2 var(--serif,serif)}
.talk-work__unknown p{max-width:46ch;margin:.7rem auto 0;color:var(--ink2)}
.talk-work__audit{margin-top:1rem;padding:1rem 0;border-top:1px solid var(--tw-rule);color:var(--ink2);font:.68rem/1.55 var(--mono,monospace)}
.talk-work__audit b{color:var(--ink)}
@media(max-width:980px){
 .talk-work__mast{grid-template-columns:1fr minmax(15rem,.65fr);gap:2rem}.talk-work__stage{grid-template-columns:minmax(9rem,.4fr) minmax(18rem,1fr);gap:1.4rem}.talk-work__stage::before{left:calc(29% + .4rem)}
 .talk-work__cadence{grid-column:1/-1;display:grid;grid-template-columns:8rem repeat(4,minmax(0,1fr));align-items:start;gap:0 .6rem;padding:1rem 0 0;border-left:0;border-top:1px solid var(--tw-rule)}.talk-work__cadence h4{padding-top:.7rem}.talk-work__cadence-rail{display:contents}
 .talk-work__trajectory-head{grid-template-columns:1fr minmax(12rem,.55fr)}
}
@media(max-width:620px){
 .talk-work{padding-top:0}.talk-work::before{inset:15rem 0 auto;height:22rem}.talk-work__mast{display:block;padding-top:.35rem}.talk-work__mast h2{font-size:1.9rem}.talk-work__law{margin-top:1rem}
 .talk-work__primitives{display:block;margin-bottom:1rem;padding-left:.2rem}.talk-work__primitives::before{top:.6rem;bottom:.6rem;left:.52rem;width:1px;height:auto;background:linear-gradient(var(--keystone),var(--accent),var(--keystone))}.talk-work__primitive{grid-template-columns:1rem 1fr;padding:.5rem 0}.talk-work__primitive::before{margin-top:.2rem}
 .talk-work__story{padding-top:.4rem}.talk-work__ribbon{display:block;overflow:visible;padding-left:1rem}.talk-work__ribbon::before{top:.4rem;bottom:.4rem;left:.34rem;width:1px;height:auto;background:linear-gradient(var(--accent),var(--tw-rule),transparent)}.talk-work__beat{min-height:3.3rem;display:grid;grid-template-columns:.8rem minmax(0,1fr);grid-template-rows:auto;gap:.6rem;padding:.45rem 0}.talk-work__beat::before{grid-row:1/3;transform:translateX(-1rem)}
 .talk-work__stage{display:block;min-height:0;padding:1.35rem 0}.talk-work__stage::before{display:none}.talk-work__origin{padding:0 0 1rem}.talk-work__scene{padding:1.6rem .2rem 2.2rem 1.1rem;border-block:1px solid var(--tw-rule)}.talk-work__scene::before{inset:.5rem -.5rem;border-radius:44%}.talk-work__ordinal{font-size:3.3rem}.talk-work__scene h3{font-size:1.8rem}.talk-work__claim{font-size:1.02rem}
 .talk-work__cadence{display:block;margin-top:1rem;padding:.9rem 0 0;border-top:0}.talk-work__cadence-rail{display:grid;grid-template-columns:1fr 1fr;gap:0 1rem}.talk-work__trajectory-head{display:block}.talk-work__trajectory p{margin-top:.65rem}
 .talk-work__flow{display:block;padding-left:1rem}.talk-work__flow::before{top:.4rem;bottom:.4rem;left:.34rem;width:1px;height:auto;background:linear-gradient(var(--accent),var(--keystone),var(--tw-rule))}.talk-work__flow-step{min-height:3.25rem;display:grid;grid-template-columns:.8rem minmax(0,1fr);grid-template-rows:auto;gap:.6rem;padding:.45rem 0}.talk-work__flow-step::before{grid-row:1/3;transform:translateX(-1rem)}
}
@media(max-width:390px){.talk-work__cadence-rail{grid-template-columns:1fr}}
@media(prefers-reduced-motion:reduce){.talk-work *{animation:none!important;transition:none!important;scroll-behavior:auto!important}}
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

function state(value) {
  return human(value, "UNKNOWN").toUpperCase().replaceAll(" ", "_");
}

function node(documentRef, tag, className = "", text = "") {
  const item = documentRef.createElement(tag);
  if (className) item.className = className;
  if (text !== "") item.textContent = text;
  return item;
}

function moveTo(move, patch) {
  if (typeof move === "function") move(patch);
}

function focused(selection, anchor) {
  return String(selection?.focus || "") === String(anchor || "");
}

function installStyle(documentRef) {
  if (documentRef.getElementById(STYLE_ID)) return;
  const style = node(documentRef, "style");
  style.id = STYLE_ID;
  style.textContent = CSS;
  documentRef.head.append(style);
}

function selectedBeat(model, selection) {
  const beats = rows(model?.spine?.beats);
  return beats.find((beat) => focused(selection, beat.semantic_anchor)) || beats[0] || null;
}

function renderPrimitive(documentRef, primitive, selection, move) {
  const button = node(documentRef, "button", "talk-work__primitive");
  button.type = "button";
  button.dataset.semanticAnchor = human(primitive.semantic_anchor);
  button.dataset.state = state(primitive.state);
  button.setAttribute("aria-pressed", String(focused(selection, primitive.semantic_anchor)));
  const copy = node(documentRef, "span");
  copy.append(
    node(documentRef, "b", "", human(primitive.label, "Primitive")),
    node(documentRef, "span", "", human(primitive.value, human(primitive.reason, "Unsettled"))),
  );
  button.append(copy);
  button.addEventListener("click", () => moveTo(move, {
    focus: primitive.semantic_anchor,
    grade: focused(selection, primitive.semantic_anchor) ? "near" : "mid",
    edge: null,
  }));
  return button;
}

function renderRibbon(documentRef, model, selection, move) {
  const section = node(documentRef, "section", "talk-work__story");
  section.dataset.semanticAnchor = human(model?.spine?.semantic_anchor, "talk:spine");
  const head = node(documentRef, "header", "talk-work__story-head");
  head.append(
    node(documentRef, "h3", "", "Storyboard ribbon"),
    node(documentRef, "span", "talk-work__micro", `${model?.spine?.beat_count ?? rows(model?.spine?.beats).length} motivated beats`),
  );
  section.append(head);
  const ribbon = node(documentRef, "nav", "talk-work__ribbon");
  ribbon.setAttribute("aria-label", "Talk beats");
  ribbon.style.setProperty("--tw-beats", String(Math.max(1, rows(model?.spine?.beats).length)));
  rows(model?.spine?.beats).forEach((beat, index) => {
    const button = node(documentRef, "button", "talk-work__beat");
    button.type = "button";
    button.dataset.semanticAnchor = human(beat.semantic_anchor);
    button.dataset.state = state(beat.state);
    button.setAttribute("aria-current", String(focused(selection, beat.semantic_anchor)));
    const copy = node(documentRef, "span");
    copy.append(
      node(documentRef, "b", "", human(beat.title, `Beat ${index + 1}`)),
      node(documentRef, "span", "", `Beat ${index + 1}`),
    );
    button.append(copy);
    button.addEventListener("click", () => moveTo(move, {
      focus: beat.semantic_anchor,
      grade: focused(selection, beat.semantic_anchor) ? "audit" : "near",
      edge: null,
      exposition: focused(selection, beat.semantic_anchor) ? "E6" : (selection?.exposition || "E2"),
    }));
    ribbon.append(button);
  });
  section.append(ribbon);
  return section;
}

function renderStage(documentRef, model, selection, move) {
  const beat = selectedBeat(model, selection);
  if (!beat) {
    const unknown = node(documentRef, "section", "talk-work__unknown");
    const copy = node(documentRef, "div");
    copy.append(
      node(documentRef, "h3", "", "The motivated spine is unavailable"),
      node(documentRef, "p", "", human(model?.spine?.reason, "No canonical beat evidence has been joined.")),
    );
    unknown.append(copy);
    return unknown;
  }
  const stage = node(documentRef, "section", "talk-work__stage");
  stage.dataset.semanticAnchor = human(beat.semantic_anchor);
  stage.dataset.state = state(beat.state);

  const origin = node(documentRef, "aside", "talk-work__origin");
  origin.append(
    node(documentRef, "h4", "", "Why this beat"),
    node(documentRef, "p", "", human(beat.motivation, "Motivation is not yet settled.")),
    node(documentRef, "span", "talk-work__origin-source", human(beat.origin, "Source origin unavailable")),
  );

  const scene = node(documentRef, "article", "talk-work__scene");
  const expanded = ["near", "audit"].includes(String(selection?.grade || "").toLowerCase())
    || focused(selection, beat.semantic_anchor);
  scene.dataset.expanded = String(expanded);
  scene.append(
    node(documentRef, "span", "talk-work__ordinal", String((beat.order ?? 0) + 1).padStart(2, "0")),
    node(documentRef, "h3", "", human(beat.title, "Untitled beat")),
    node(documentRef, "p", "talk-work__claim", human(beat.claim, "The beat claim is unresolved.")),
  );
  if (beat.visual) scene.append(node(documentRef, "span", "talk-work__visual", human(beat.visual)));
  scene.append(node(documentRef, "p", "talk-work__motivation", human(beat.motivation)));

  const cadence = node(documentRef, "aside", "talk-work__cadence");
  cadence.append(node(documentRef, "h4", "", "Rehearsal cadence"));
  const rail = node(documentRef, "div", "talk-work__cadence-rail");
  const postureById = Object.fromEntries(rows(model.postures).map((row) => [row.id, row]));
  for (const ident of ["generation", "ledger", "rehearsal", "export"]) {
    const posture = plain(postureById[ident]);
    const pulse = node(documentRef, "button", "talk-work__pulse");
    pulse.type = "button";
    pulse.dataset.semanticAnchor = human(posture.semantic_anchor, `talk:posture:${ident}`);
    pulse.dataset.state = state(posture.state);
    const copy = node(documentRef, "span");
    copy.append(
      node(documentRef, "b", "", human(posture.label, ident)),
      node(documentRef, "span", "", state(posture.state).replaceAll("_", " ")),
    );
    pulse.append(copy);
    pulse.addEventListener("click", () => moveTo(move, {
      focus: posture.semantic_anchor || `talk:posture:${ident}`,
      grade: "near",
      edge: null,
    }));
    rail.append(pulse);
  }
  cadence.append(rail);
  stage.append(origin, scene, cadence);
  return stage;
}

function renderTrajectory(documentRef, model, selection, move) {
  const section = node(documentRef, "section", "talk-work__trajectory");
  const head = node(documentRef, "header", "talk-work__trajectory-head");
  const title = node(documentRef, "div");
  title.append(
    node(documentRef, "span", "talk-work__kicker", "Projection trajectory"),
    node(documentRef, "h3", "", "From settled beat to a talk that survives the room"),
  );
  head.append(
    title,
    node(documentRef, "p", "", "A slide is a render coordinate. Corrections return to the beat and regenerate the deck."),
  );
  section.append(head);
  const postureById = Object.fromEntries(rows(model.postures).map((row) => [row.id, row]));
  const flowRows = [
    { id: "spine", label: "Motivated spine", state: model?.spine?.state, anchor: "talk:spine" },
    { id: "storyboard", label: "Storyboard", state: model?.spine?.state, anchor: "talk:spine" },
    { id: "generation", label: "Generated deck", ...plain(postureById.generation) },
    { id: "ledger", label: "Rendered ledger", ...plain(postureById.ledger) },
    { id: "rehearsal", label: "Rehearsal", ...plain(postureById.rehearsal) },
    { id: "export", label: "Export + listing", ...plain(postureById.export) },
  ];
  const flow = node(documentRef, "div", "talk-work__flow");
  for (const row of flowRows) {
    const anchor = row.semantic_anchor || row.anchor || `talk:posture:${row.id}`;
    const button = node(documentRef, "button", "talk-work__flow-step");
    button.type = "button";
    button.dataset.semanticAnchor = human(anchor);
    button.dataset.state = state(row.state);
    button.setAttribute("aria-pressed", String(focused(selection, anchor)));
    const copy = node(documentRef, "span");
    copy.append(
      node(documentRef, "b", "", human(row.label, row.id)),
      node(documentRef, "span", "", state(row.state).replaceAll("_", " ")),
    );
    button.append(copy);
    button.addEventListener("click", () => moveTo(move, {
      focus: anchor,
      grade: focused(selection, anchor) ? "audit" : "near",
      edge: null,
    }));
    flow.append(button);
  }
  section.append(flow);
  return section;
}

export function renderTalkWorkSurface(target, input, options = {}) {
  if (!target || !target.ownerDocument) throw new TypeError("a mounted DOM target is required");
  const documentRef = target.ownerDocument;
  installStyle(documentRef);
  const model = plain(input);
  const selection = plain(options.selection);
  const move = options.move;
  target.replaceChildren();

  const root = node(documentRef, "section", "talk-work");
  root.dataset.renderer = "talk-work-surface";
  root.dataset.semanticAnchor = human(model.semantic_anchor, "work:talk");
  root.dataset.state = state(model.state);
  root.dataset.schemaVersion = TALK_WORK_SURFACE_SCHEMA;

  const mast = node(documentRef, "header", "talk-work__mast");
  const intro = node(documentRef, "div");
  intro.append(
    node(documentRef, "span", "talk-work__kicker", `Talk · ${state(model.state).replaceAll("_", " ")}`),
    node(documentRef, "h2", "", human(model.title, "Untitled talk")),
    node(documentRef, "p", "", "Shape the argument at beat grain, stage the visual that lands it, then verify the rendered room."),
  );
  const law = node(documentRef, "div", "talk-work__law");
  law.append(
    node(documentRef, "b", "", "The beat is the editor"),
    node(documentRef, "span", "", "Governed beat regeneration is required before a deck may change. Its producer may be unavailable. The deck never becomes a second truth."),
  );
  mast.append(intro, law);
  root.append(mast);

  const primitives = node(documentRef, "section", "talk-work__primitives");
  primitives.setAttribute("aria-label", "Talk primitives");
  rows(model.primitives).forEach((row) => primitives.append(renderPrimitive(documentRef, row, selection, move)));
  root.append(primitives, renderRibbon(documentRef, model, selection, move));
  root.append(renderStage(documentRef, model, selection, move));
  root.append(renderTrajectory(documentRef, model, selection, move));

  if (String(selection.grade || "").toLowerCase() === "audit") {
    const audit = node(documentRef, "aside", "talk-work__audit");
    const beat = selectedBeat(model, selection);
    audit.dataset.semanticAnchor = beat?.semantic_anchor || model.semantic_anchor || "work:talk";
    audit.append(
      node(documentRef, "b", "", "Selected evidence · "),
      documentRef.createTextNode(human(beat?.origin, "No selected source origin")),
      documentRef.createElement("br"),
      documentRef.createTextNode(`${Array.isArray(beat?.citations) ? beat.citations.length : 0} cited source${Array.isArray(beat?.citations) && beat.citations.length === 1 ? "" : "s"} · ${rows(beat?.assets).length} governed asset${rows(beat?.assets).length === 1 ? "" : "s"}`),
    );
    root.append(audit);
  }
  target.append(root);
  return root;
}

export default renderTalkWorkSurface;
