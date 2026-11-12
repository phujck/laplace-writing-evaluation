// THE RESEARCH COMPUTE SURFACE. Purpose: paint the research compute campaign (runs, states
// COMPLETE/IN_FLIGHT/STALE/UNKNOWN/REFUSED, currentness marks) from its owner's projection.
// Ownership: the research compute owner's read; this module owns the surface DOM and its scoped
// style sheet (installed once under STYLE_ID; its --rc-* custom properties derive from the shared
// tokens). Public contract: renderResearchComputeSurface(host, value) (default export). Inputs:
// one projection; outputs: DOM. Currentness: the projection's; nothing is polled. Storage: none.
const STYLE_ID = "aisthesis-research-compute-style";

const STATES = new Set(["COMPLETE", "IN_FLIGHT", "STALE", "UNKNOWN", "REFUSED"]);

function text(value, fallback = "") {
  const rendered = String(value ?? "").replace(/\s+/g, " ").trim();
  return rendered || fallback;
}

function state(value) {
  const rendered = text(value, "UNKNOWN").toUpperCase();
  return STATES.has(rendered) ? rendered : "REFUSED";
}

function element(tag, className, content = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== "") node.textContent = String(content);
  return node;
}

function button(className, label, anchor, currentState) {
  const node = element("button", className);
  node.type = "button";
  node.dataset.semanticAnchor = anchor;
  node.dataset.state = state(currentState);
  node.setAttribute("aria-label", label);
  return node;
}

function compactNumber(value) {
  if (value === null || value === undefined || value === "") return "";
  if (typeof value === "number") {
    if (Math.abs(value) >= 1000) return new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1, notation: "compact" }).format(value);
    if (Number.isInteger(value)) return String(value);
    return new Intl.NumberFormat("en-GB", { maximumFractionDigits: 3 }).format(value);
  }
  return text(value);
}

function prettyMetric(key) {
  return text(key).replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function ensureStyle() {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .research-compute {
      --rc-ink: var(--ink, var(--grey-90-d));
      --rc-muted: color-mix(in srgb, var(--rc-ink) 62%, transparent);
      --rc-faint: color-mix(in srgb, var(--rc-ink) 14%, transparent);
      --rc-ground: color-mix(in srgb, var(--ground, var(--green-10)) 88%, var(--green-10));
      --rc-line: color-mix(in srgb, var(--rc-ink) 30%, transparent);
      --rc-live: var(--lime-80);
      --rc-warn: var(--gold-80-b);
      --rc-refuse: var(--red-60);
      color: var(--rc-ink);
      background:
        radial-gradient(circle at 16% 8%, color-mix(in srgb, var(--rc-live) 10%, transparent), transparent 30rem),
        linear-gradient(145deg, var(--rc-ground), color-mix(in srgb, var(--rc-ground) 90%, var(--bg)));
      border-block: 1px solid var(--rc-line);
      display: grid;
      gap: clamp(1.3rem, 2.6vw, 2.8rem);
      inline-size: 100%;
      max-inline-size: 100%;
      overflow: clip;
      padding: clamp(1.1rem, 2.8vw, 3rem);
      position: relative;
    }
    .research-compute::before {
      background: repeating-linear-gradient(90deg, transparent 0 6.1rem, color-mix(in srgb, var(--rc-ink) 4%, transparent) 6.1rem 6.16rem);
      content: "";
      inset: 0;
      pointer-events: none;
      position: absolute;
    }
    .research-compute > * { min-inline-size: 0; position: relative; }
    .rc-mast {
      align-items: end;
      display: grid;
      gap: 1rem;
      grid-template-columns: minmax(0, 1fr) auto;
    }
    .rc-kicker {
      color: var(--rc-muted);
      font: 650 .72rem/1.2 ui-monospace, SFMono-Regular, Menlo, monospace;
      letter-spacing: .16em;
      margin: 0 0 .4rem;
      text-transform: uppercase;
    }
    .rc-title { font: 420 clamp(1.75rem, 4vw, 3.8rem)/.96 ui-serif, Georgia, serif; margin: 0; max-inline-size: 18ch; }
    .rc-summary { color: var(--rc-muted); font-size: .9rem; margin: .6rem 0 0; max-inline-size: 68ch; }
    .rc-currentness {
      align-items: center;
      border-block: 1px solid var(--rc-line);
      display: flex;
      gap: .65rem;
      min-block-size: 44px;
      padding: .6rem .2rem;
      white-space: nowrap;
    }
    .rc-currentness::before, .rc-state-mark {
      background: currentColor;
      border-radius: 50%;
      block-size: .58rem;
      box-shadow: 0 0 0 .25rem color-mix(in srgb, currentColor 16%, transparent);
      content: "";
      display: inline-block;
      flex: 0 0 auto;
      inline-size: .58rem;
    }
    [data-state="COMPLETE"] { --rc-state: var(--rc-live); }
    [data-state="IN_FLIGHT"] { --rc-state: var(--cyan-70-c); }
    [data-state="STALE"] { --rc-state: var(--rc-warn); }
    [data-state="UNKNOWN"] { --rc-state: var(--rc-warn); }
    [data-state="REFUSED"] { --rc-state: var(--rc-refuse); }
    .rc-currentness, [data-state] .rc-state-mark { color: var(--rc-state, var(--rc-muted)); }
    .rc-section-heading {
      align-items: baseline;
      display: flex;
      gap: 1rem;
      justify-content: space-between;
      margin-block-end: 1rem;
    }
    .rc-section-heading h3 { font: 500 clamp(1.1rem, 2vw, 1.55rem)/1.1 ui-serif, Georgia, serif; margin: 0; }
    .rc-section-heading p { color: var(--rc-muted); font-size: .76rem; margin: 0; text-align: end; }
    .rc-query {
      display: grid;
      gap: clamp(.8rem, 1.8vw, 1.5rem);
      grid-template-columns: minmax(12rem, .9fr) minmax(24rem, 2.1fr);
    }
    .rc-question {
      align-content: space-between;
      background: color-mix(in srgb, var(--rc-live) 8%, transparent);
      border: 0;
      border-inline-start: .28rem solid var(--rc-live);
      color: inherit;
      display: grid;
      min-block-size: 10rem;
      padding: clamp(1rem, 2vw, 1.6rem);
      text-align: start;
    }
    .rc-question__label { color: var(--rc-muted); font: 700 .68rem/1.2 ui-monospace, monospace; letter-spacing: .12em; text-transform: uppercase; }
    .rc-question__text { font: 450 clamp(1.05rem, 2vw, 1.65rem)/1.18 ui-serif, Georgia, serif; max-inline-size: 27ch; }
    .rc-parameters { color: var(--rc-muted); display: flex; flex-wrap: wrap; font: 600 .68rem/1.3 ui-monospace, monospace; gap: .45rem .8rem; margin-block-start: .8rem; }
    .rc-path-field { display: grid; gap: .85rem; min-inline-size: 0; }
    .rc-path {
      align-items: stretch;
      display: grid;
      gap: 1.3rem;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      list-style: none;
      margin: 0;
      padding: 0;
    }
    .rc-path li { min-inline-size: 0; position: relative; }
    .rc-path li:not(:last-child)::after {
      border-block-start: 1px solid var(--rc-line);
      content: "";
      inline-size: 1.3rem;
      inset-block-start: 50%;
      inset-inline-end: -1.3rem;
      position: absolute;
    }
    .rc-path-stage {
      background: color-mix(in srgb, var(--rc-ground) 76%, transparent);
      border: 1px solid var(--rc-line);
      color: inherit;
      display: grid;
      gap: .35rem;
      inline-size: 100%;
      min-block-size: 6.3rem;
      padding: .8rem;
      text-align: start;
    }
    .rc-path-stage:hover, .rc-path-stage:focus-visible, .rc-region:hover, .rc-region:focus-visible,
    .rc-cell:hover, .rc-cell:focus-visible, .rc-run:hover, .rc-run:focus-visible,
    .rc-result-key:hover, .rc-result-key:focus-visible, .rc-question:hover, .rc-question:focus-visible {
      border-color: var(--rc-live);
      outline: 2px solid transparent;
      translate: 0 -1px;
    }
    [data-selected="true"] { box-shadow: 0 0 0 2px var(--rc-live), 0 1rem 3rem color-mix(in srgb, var(--black) 28%, transparent); }
    .rc-path-stage__top { align-items: center; display: flex; gap: .5rem; justify-content: space-between; }
    .rc-path-stage__name { font-weight: 720; }
    .rc-path-stage__measure { color: var(--rc-muted); font: 600 .68rem/1.2 ui-monospace, monospace; }
    .rc-path-stage__reason { color: var(--rc-muted); font-size: .72rem; line-height: 1.35; }
    .rc-regions { display: grid; gap: .55rem; grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .rc-region {
      background: transparent;
      border: 0;
      border-block-start: .23rem solid var(--rc-state, var(--rc-line));
      color: inherit;
      display: grid;
      gap: .28rem;
      min-block-size: 5.3rem;
      padding: .65rem .4rem;
      text-align: start;
    }
    .rc-region[data-region-class="REJECTED"] { border-block-start-style: dashed; opacity: .78; }
    .rc-region[data-region-class="UNVISITED"] {
      background: repeating-linear-gradient(135deg, transparent 0 .38rem, color-mix(in srgb, var(--rc-ink) 6%, transparent) .38rem .45rem);
      border-block-start-style: dotted;
    }
    .rc-region__class { color: var(--rc-muted); font: 700 .62rem/1 ui-monospace, monospace; letter-spacing: .08em; }
    .rc-region__label { font-size: .83rem; font-weight: 680; }
    .rc-region__meta { color: var(--rc-muted); font-size: .68rem; }
    .rc-fog-bank { display: flex; flex-wrap: wrap; gap: .45rem; }
    .rc-fog {
      background: repeating-linear-gradient(120deg, color-mix(in srgb, var(--rc-warn) 7%, transparent) 0 .42rem, transparent .42rem .82rem);
      border-inline-start: 2px dashed var(--rc-warn);
      color: var(--rc-muted);
      font-size: .68rem;
      min-block-size: 44px;
      padding: .6rem .8rem;
    }
    .rc-lab {
      border-block-start: 1px solid var(--rc-line);
      display: grid;
      gap: clamp(1.3rem, 2.4vw, 2.4rem);
      grid-template-columns: minmax(0, 1.22fr) minmax(18rem, .78fr);
      padding-block-start: clamp(1.2rem, 2vw, 2rem);
    }
    .rc-matrix { display: grid; gap: .38rem; min-inline-size: 0; }
    .rc-matrix__row {
      display: grid;
      gap: .38rem;
      grid-template-columns: minmax(9rem, 1.15fr) repeat(var(--rc-arms, 1), minmax(7.8rem, 1fr));
    }
    .rc-matrix__corner, .rc-matrix__head, .rc-campaign-label {
      align-items: center;
      display: flex;
      min-block-size: 44px;
      padding: .5rem .65rem;
    }
    .rc-matrix__head { color: var(--rc-muted); font: 700 .68rem/1.1 ui-monospace, monospace; justify-content: center; letter-spacing: .08em; text-align: center; text-transform: uppercase; }
    .rc-campaign-label { border-inline-start: .2rem solid var(--rc-state, var(--rc-line)); display: grid; }
    .rc-campaign-label strong { font-size: .82rem; }
    .rc-campaign-label span { color: var(--rc-muted); font-size: .66rem; }
    .rc-cell {
      background: color-mix(in srgb, var(--rc-state, var(--rc-line)) 8%, transparent);
      border: 1px solid color-mix(in srgb, var(--rc-state, var(--rc-line)) 45%, transparent);
      color: inherit;
      display: grid;
      gap: .25rem;
      min-block-size: 5.2rem;
      padding: .65rem;
      text-align: start;
    }
    .rc-cell__phase { font: 750 .68rem/1.1 ui-monospace, monospace; letter-spacing: .04em; }
    .rc-cell__metrics { color: var(--rc-muted); display: flex; flex-wrap: wrap; font-size: .66rem; gap: .25rem .55rem; }
    .rc-run-rail { display: grid; gap: .45rem; margin-block-start: 1rem; }
    .rc-run {
      align-items: center;
      background: transparent;
      border: 0;
      color: inherit;
      display: grid;
      gap: .55rem;
      grid-template-columns: minmax(8rem, 1fr) 3fr;
      min-block-size: 44px;
      padding: .2rem 0;
      text-align: start;
    }
    .rc-run__track { background: var(--rc-faint); block-size: .28rem; position: relative; }
    .rc-run__track::before { background: var(--rc-state, var(--rc-line)); content: ""; inline-size: var(--rc-progress, 0%); inset: 0 auto 0 0; position: absolute; }
    .rc-run__track::after { background: var(--rc-state, var(--rc-line)); border-radius: 50%; block-size: .72rem; content: ""; inset-block-start: 50%; inset-inline-start: calc(var(--rc-progress, 0%) - .36rem); position: absolute; translate: 0 -50%; inline-size: .72rem; }
    .rc-comparison { min-inline-size: 0; }
    .rc-comparison svg { block-size: 17rem; display: block; inline-size: 100%; overflow: visible; }
    .rc-axis { stroke: var(--rc-line); stroke-width: 1; }
    .rc-axis-label { fill: var(--rc-muted); font: 650 11px ui-monospace, monospace; text-anchor: middle; }
    .rc-result-line { fill: none; opacity: .78; stroke: var(--rc-state, var(--rc-live)); stroke-linecap: round; stroke-linejoin: round; stroke-width: 3; }
    .rc-result-line[data-index="1"] { stroke-dasharray: 7 5; }
    .rc-result-point { fill: var(--rc-ground); stroke: var(--rc-state, var(--rc-live)); stroke-width: 2.5; }
    .rc-result-keys { display: flex; flex-wrap: wrap; gap: .45rem; }
    .rc-result-key {
      align-items: center;
      background: transparent;
      border: 1px solid var(--rc-line);
      color: inherit;
      display: flex;
      gap: .55rem;
      min-block-size: 44px;
      padding: .55rem .7rem;
    }
    .rc-result-key::before { background: var(--rc-state, var(--rc-live)); block-size: .18rem; content: ""; inline-size: 1.6rem; }
    .rc-comparison-narrow { display: none; }
    .rc-narrow-result { border-inline-start: .22rem solid var(--rc-state, var(--rc-line)); display: grid; gap: .3rem; padding: .6rem .75rem; }
    .rc-narrow-result dl { display: grid; gap: .25rem; grid-template-columns: 1fr auto; margin: 0; }
    .rc-narrow-result dt, .rc-narrow-result dd { color: var(--rc-muted); font-size: .7rem; margin: 0; }
    .rc-detail {
      background: color-mix(in srgb, var(--rc-live) 6%, transparent);
      border-block: 1px solid var(--rc-line);
      display: grid;
      gap: .6rem;
      grid-template-columns: minmax(0, 1fr) auto;
      padding: 1rem 0;
    }
    .rc-detail h4 { font: 540 1.15rem/1.2 ui-serif, Georgia, serif; margin: 0; }
    .rc-detail p { color: var(--rc-muted); font-size: .78rem; margin: .3rem 0 0; max-inline-size: 72ch; }
    .rc-detail__continuation { align-self: center; color: var(--rc-muted); font: 650 .68rem/1.25 ui-monospace, monospace; max-inline-size: 28ch; overflow-wrap: anywhere; text-align: end; }
    .rc-empty { border: 1px dashed var(--rc-line); color: var(--rc-muted); padding: 1rem; }
    @media (max-width: 900px) {
      .rc-query, .rc-lab { grid-template-columns: 1fr; }
      .rc-question { min-block-size: 7.2rem; }
      .rc-comparison svg { block-size: 15rem; }
    }
    @media (max-width: 600px) {
      .research-compute { gap: 1.4rem; padding: 1rem .82rem 1.5rem; }
      .research-compute::before { display: none; }
      .rc-mast { align-items: start; grid-template-columns: 1fr; }
      .rc-currentness { justify-self: stretch; }
      .rc-section-heading { align-items: start; display: grid; gap: .25rem; }
      .rc-section-heading p { text-align: start; }
      .rc-path { grid-template-columns: 1fr; }
      .rc-path li:not(:last-child)::after { block-size: 1.3rem; border-block-start: 0; border-inline-start: 1px solid var(--rc-line); inline-size: 0; inset-block-start: auto; inset-block-end: -1.3rem; inset-inline-start: 1.25rem; }
      .rc-path-stage { min-block-size: 4.6rem; }
      .rc-regions { grid-template-columns: 1fr; }
      .rc-region { min-block-size: 4.3rem; }
      .rc-matrix__header { display: none; }
      .rc-matrix__row { border-block-start: 1px solid var(--rc-line); display: block; padding-block-start: .5rem; }
      .rc-campaign-label { margin-block-end: .35rem; }
      .rc-cell { margin-block-end: .35rem; min-block-size: 4.7rem; padding-inline-start: 2.8rem; position: relative; }
      .rc-cell::before { color: var(--rc-muted); content: attr(data-arm-label); font: 700 .58rem/1 ui-monospace, monospace; inset: .8rem auto auto .65rem; max-inline-size: 1.8rem; overflow-wrap: anywhere; position: absolute; text-transform: uppercase; }
      .rc-run { grid-template-columns: 1fr; }
      .rc-run__track { margin-block: .25rem .55rem; }
      .rc-comparison svg { display: none; }
      .rc-comparison-narrow { display: grid; gap: .45rem; }
      .rc-detail { grid-template-columns: 1fr; }
      .rc-detail__continuation { text-align: start; }
    }
    @media (prefers-reduced-motion: reduce) {
      .research-compute *, .research-compute *::before, .research-compute *::after { scroll-behavior: auto !important; transition: none !important; }
    }
  `;
  document.head.append(style);
}

function selected(selection, anchor) {
  return text(selection?.focus) === text(anchor);
}

function moveTo(move, selection, anchor) {
  return () => move({
    focus: anchor,
    grade: selected(selection, anchor) ? "audit" : "near",
    edge: null,
    exposition: selected(selection, anchor) ? "E6" : text(selection?.exposition, "E2"),
  });
}

function addHeading(root, title, note) {
  const heading = element("header", "rc-section-heading");
  heading.append(element("h3", "", title), element("p", "", note));
  root.append(heading);
}

function renderQuery(root, queryPath, selection, move) {
  const section = element("section", "rc-quarry");
  section.dataset.semanticAnchor = text(queryPath?.semantic_anchor, "research:query-path");
  section.dataset.state = state(queryPath?.state);
  addHeading(section, "Question → evidence", "Reach, refusal and fog remain distinct");
  const field = element("div", "rc-query");

  const questionAnchor = "research:query-stage:question";
  const question = button("rc-question", "Inspect the selected research question", questionAnchor, queryPath?.query ? "COMPLETE" : "UNKNOWN");
  question.dataset.selected = String(selected(selection, questionAnchor));
  question.addEventListener("click", moveTo(move, selection, questionAnchor));
  question.append(
    element("span", "rc-question__label", "Research question"),
    element("span", "rc-question__text", text(queryPath?.query, "No question selected")),
  );
  const parameters = element("span", "rc-parameters");
  for (const [key, value] of Object.entries(queryPath?.declared_parameters || {})) {
    const rendered = typeof value === "object" ? Object.keys(value || {}).join(" · ") : compactNumber(value);
    parameters.append(element("span", "", `${prettyMetric(key)} ${rendered}`));
  }
  if (!parameters.childElementCount) parameters.append(element("span", "", "Planner contract unavailable"));
  question.append(parameters);
  field.append(question);

  const pathField = element("div", "rc-path-field");
  const path = element("ol", "rc-path");
  for (const stage of (queryPath?.stages || []).filter((candidate) => candidate.id !== "question")) {
    const item = document.createElement("li");
    const control = button("rc-path-stage", `Inspect ${text(stage.label, stage.id)}`, stage.semantic_anchor, stage.state);
    control.dataset.selected = String(selected(selection, stage.semantic_anchor));
    control.addEventListener("click", moveTo(move, selection, stage.semantic_anchor));
    const top = element("span", "rc-path-stage__top");
    const name = element("span", "rc-path-stage__name", text(stage.label, stage.id));
    const mark = element("span", "rc-state-mark");
    mark.setAttribute("aria-hidden", "true");
    top.append(name, mark);
    const measures = [
      stage.count !== null && stage.count !== undefined ? `${compactNumber(stage.count)} objects` : "",
      stage.latency_ms !== null && stage.latency_ms !== undefined ? `${compactNumber(stage.latency_ms)} ms` : "",
    ].filter(Boolean).join(" · ");
    control.append(top, element("span", "rc-path-stage__measure", measures || state(stage.state)), element("span", "rc-path-stage__reason", text(stage.reason)));
    item.append(control);
    path.append(item);
  }
  pathField.append(path);

  const regions = element("div", "rc-regions");
  for (const region of queryPath?.regions || []) {
    const control = button("rc-region", `Inspect ${text(region.label, region.id)} ${region.class}`, region.semantic_anchor, region.state);
    control.dataset.regionClass = text(region.class, "UNVISITED");
    control.dataset.selected = String(selected(selection, region.semantic_anchor));
    control.addEventListener("click", moveTo(move, selection, region.semantic_anchor));
    control.append(
      element("span", "rc-region__class", text(region.class, "UNVISITED")),
      element("span", "rc-region__label", text(region.label, region.id)),
      element("span", "rc-region__meta", `${compactNumber(region.count)} ${text(region.source_class, "unknown source")} · depth ${compactNumber(region.depth) || "?"}`),
    );
    regions.append(control);
  }
  if (!regions.childElementCount) regions.append(element("div", "rc-empty", "Region reach is UNKNOWN — continue through the Atlas query receipt."));
  pathField.append(regions);

  const fog = element("div", "rc-fog-bank");
  for (const row of queryPath?.fog || []) {
    const marker = element("div", "rc-fog", `${text(row.label, row.cause)} · ${compactNumber(row.count)} · ${text(row.cause).replace(/_/g, " ")}`);
    marker.dataset.semanticAnchor = row.semantic_anchor;
    marker.dataset.state = "UNKNOWN";
    marker.title = text(row.reason);
    fog.append(marker);
  }
  if (!fog.childElementCount) fog.append(element("div", "rc-fog", "Fog map UNKNOWN · exact typed causes have not joined"));
  pathField.append(fog);
  field.append(pathField);
  section.append(field);
  root.append(section);
}

function renderMatrix(root, matrix, selection, move) {
  const section = element("section", "rc-experiment");
  section.dataset.semanticAnchor = text(matrix?.semantic_anchor, "research:experiment-matrix");
  section.dataset.state = state(matrix?.state);
  addHeading(section, "Experiment matrix", "Campaigns × arms, with the run’s actual altitude");
  const grid = element("div", "rc-matrix");
  grid.style.setProperty("--rc-arms", String(Math.max(1, matrix?.columns?.length || 0)));
  const header = element("div", "rc-matrix__row rc-matrix__header");
  header.append(element("div", "rc-matrix__corner", ""));
  for (const column of matrix?.columns || []) header.append(element("div", "rc-matrix__head", text(column.label, column.id)));
  grid.append(header);
  for (const row of matrix?.rows || []) {
    const line = element("div", "rc-matrix__row");
    const label = element("div", "rc-campaign-label");
    label.dataset.state = state(row.state);
    label.dataset.semanticAnchor = row.semantic_anchor;
    label.append(element("strong", "", text(row.label, row.id)), element("span", "", row.question_count !== null && row.question_count !== undefined ? `${compactNumber(row.question_count)} questions` : state(row.state)));
    line.append(label);
    for (const cell of row.cells || []) {
      const arm = (matrix?.columns || []).find((candidate) => candidate.id === cell.arm_id);
      const control = button("rc-cell", `Inspect ${text(row.label, row.id)} ${text(arm?.label, cell.arm_id)} run`, cell.semantic_anchor, cell.state);
      control.dataset.armLabel = text(arm?.label, cell.arm_id);
      control.dataset.selected = String(selected(selection, cell.semantic_anchor));
      control.addEventListener("click", moveTo(move, selection, cell.semantic_anchor));
      control.append(element("span", "rc-cell__phase", text(cell.phase, "UNKNOWN").replace(/_/g, " ")));
      const metrics = element("span", "rc-cell__metrics");
      for (const [key, value] of Object.entries(cell.metrics || {}).slice(0, 3)) metrics.append(element("span", "", `${prettyMetric(key)} ${compactNumber(value)}`));
      if (!metrics.childElementCount) metrics.append(element("span", "", text(cell.reason, "No observed metrics")));
      control.append(metrics);
      line.append(control);
    }
    grid.append(line);
  }
  if (!(matrix?.rows || []).length) grid.append(element("div", "rc-empty", "Campaign frontier UNKNOWN — no experiment producer is joined."));
  section.append(grid);

  const runs = element("div", "rc-run-rail");
  const phaseOrder = matrix?.phase_order || [];
  for (const run of matrix?.runs || []) {
    const control = button("rc-run", `Inspect run ${text(run.label, run.id)}`, run.semantic_anchor, run.state);
    control.dataset.selected = String(selected(selection, run.semantic_anchor));
    control.addEventListener("click", moveTo(move, selection, run.semantic_anchor));
    control.append(element("strong", "", text(run.label, run.id)));
    const track = element("span", "rc-run__track");
    const phaseIndex = Math.max(-1, phaseOrder.indexOf(run.phase));
    const progress = phaseIndex < 0 ? 0 : ((phaseIndex + 1) / Math.max(1, phaseOrder.length)) * 100;
    track.style.setProperty("--rc-progress", `${progress}%`);
    track.title = `${text(run.phase, "UNKNOWN").replace(/_/g, " ")} · ${state(run.state)}`;
    control.append(track);
    runs.append(control);
  }
  section.append(runs);
  root.append(section);
}

function svgElement(tag, attrs = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  return node;
}

function renderComparison(root, comparison, selection, move) {
  const section = element("section", "rc-comparison");
  section.dataset.semanticAnchor = text(comparison?.semantic_anchor, "research:result-comparison");
  section.dataset.state = state(comparison?.state);
  addHeading(section, "Result field", "Comparable measures only; missing axes stay absent");
  const axes = comparison?.axes || [];
  const entries = comparison?.entries || [];
  if (axes.length && entries.length) {
    const svg = svgElement("svg", { viewBox: "0 0 720 280", role: "img", "aria-label": "Parallel comparison of producer-supplied result metrics" });
    const left = 54;
    const right = 666;
    const top = 42;
    const bottom = 226;
    const xFor = (index) => axes.length === 1 ? 360 : left + (index / (axes.length - 1)) * (right - left);
    axes.forEach((axis, index) => {
      const x = xFor(index);
      svg.append(svgElement("line", { class: "rc-axis", x1: x, y1: top, x2: x, y2: bottom }));
      const label = svgElement("text", { class: "rc-axis-label", x, y: 24 });
      label.textContent = text(axis.label, axis.id);
      svg.append(label);
      const high = svgElement("text", { class: "rc-axis-label", x, y: top + 12 });
      high.textContent = compactNumber(axis.maximum);
      svg.append(high);
      const low = svgElement("text", { class: "rc-axis-label", x, y: bottom + 16 });
      low.textContent = compactNumber(axis.minimum);
      svg.append(low);
    });
    entries.forEach((entry, entryIndex) => {
      const points = [];
      for (let axisIndex = 0; axisIndex < axes.length; axisIndex += 1) {
        const axis = axes[axisIndex];
        if (!(axis.id in (entry.metrics || {}))) continue;
        const value = Number(entry.metrics[axis.id]);
        const span = Number(axis.maximum) - Number(axis.minimum);
        const proportion = span === 0 ? 0.5 : (value - Number(axis.minimum)) / span;
        points.push([xFor(axisIndex), bottom - proportion * (bottom - top)]);
      }
      if (points.length) {
        const line = svgElement("polyline", { class: "rc-result-line", points: points.map((point) => point.join(",")).join(" "), "data-index": entryIndex, "data-state": state(entry.state) });
        svg.append(line);
        for (const [x, y] of points) svg.append(svgElement("circle", { class: "rc-result-point", cx: x, cy: y, r: 5, "data-state": state(entry.state) }));
      }
    });
    section.append(svg);

    const narrow = element("div", "rc-comparison-narrow");
    for (const entry of entries) {
      const row = element("div", "rc-narrow-result");
      row.dataset.state = state(entry.state);
      row.append(element("strong", "", text(entry.label, entry.id)));
      const list = document.createElement("dl");
      for (const axis of axes) {
        const dt = element("dt", "", text(axis.label, axis.id));
        const dd = element("dd", "", axis.id in (entry.metrics || {}) ? compactNumber(entry.metrics[axis.id]) : "UNKNOWN");
        list.append(dt, dd);
      }
      row.append(list);
      narrow.append(row);
    }
    section.append(narrow);

    const keys = element("div", "rc-result-keys");
    for (const entry of entries) {
      const control = button("rc-result-key", `Inspect result ${text(entry.label, entry.id)}`, entry.semantic_anchor, entry.state);
      control.dataset.selected = String(selected(selection, entry.semantic_anchor));
      control.addEventListener("click", moveTo(move, selection, entry.semantic_anchor));
      control.append(element("span", "", text(entry.label, entry.id)));
      keys.append(control);
    }
    section.append(keys);
  } else {
    section.append(element("div", "rc-empty", "Comparable results are UNKNOWN — no shared numeric axis has been admitted."));
  }
  root.append(section);
}

function selectedSubject(model, focus) {
  const candidates = [
    ...(model?.query_path?.stages || []),
    ...(model?.query_path?.regions || []),
    ...(model?.experiment_matrix?.rows || []),
    ...(model?.experiment_matrix?.rows || []).flatMap((row) => row.cells || []),
    ...(model?.experiment_matrix?.runs || []),
    ...(model?.result_comparison?.entries || []),
  ];
  return candidates.find((candidate) => text(candidate.semantic_anchor) === text(focus));
}

function renderDetail(root, model, selection) {
  const subject = selectedSubject(model, selection?.focus);
  if (!subject) return;
  const detail = element("section", "rc-detail");
  detail.dataset.semanticAnchor = `${subject.semantic_anchor}:detail`;
  detail.dataset.state = state(subject.state);
  const copy = element("div", "");
  copy.append(element("h4", "", text(subject.label, subject.id || "Selected evidence")), element("p", "", text(subject.reason, "No further human explanation was supplied.")));
  const metrics = subject.metrics || {};
  if (Object.keys(metrics).length) copy.append(element("p", "", Object.entries(metrics).map(([key, value]) => `${prettyMetric(key)} ${compactNumber(value)}`).join(" · ")));
  detail.append(copy, element("div", "rc-detail__continuation", text(subject.continuation, "Exact continuation unavailable")));
  root.append(detail);
}

export function renderResearchComputeSurface(root, model, options = {}) {
  if (!(root instanceof Element)) throw new TypeError("research/compute renderer requires an Element root");
  ensureStyle();
  root.replaceChildren();
  const selection = options.selection || {};
  const move = typeof options.move === "function" ? options.move : () => {};
  const surface = element("article", "research-compute");
  surface.dataset.renderer = "research-compute-surface";
  surface.dataset.semanticAnchor = text(model?.semantic_anchor, "research:compute-surface");
  surface.dataset.state = state(model?.state);
  surface.dataset.currentness = text(model?.currentness?.status, "UNKNOWN").toUpperCase();
  surface.dataset.readOnly = "true";

  const mast = element("header", "rc-mast");
  const title = element("div", "");
  title.append(
    element("p", "rc-kicker", "Research / Compute"),
    element("h2", "rc-title", "From question to witnessed result"),
    element("p", "rc-summary", "Traverse the quarry, compare experiments, and keep every miss, refusal and unvisited region visible."),
  );
  const currentness = element("div", "rc-currentness", text(model?.currentness?.status, "UNKNOWN"));
  currentness.dataset.state = text(model?.currentness?.status, "UNKNOWN").toUpperCase();
  currentness.title = text(model?.currentness?.reason);
  mast.append(title, currentness);
  surface.append(mast);

  renderQuery(surface, model?.query_path || {}, selection, move);
  const lab = element("div", "rc-lab");
  renderMatrix(lab, model?.experiment_matrix || {}, selection, move);
  renderComparison(lab, model?.result_comparison || {}, selection, move);
  surface.append(lab);
  renderDetail(surface, model, selection);
  root.append(surface);
  return surface;
}

export default renderResearchComputeSurface;
