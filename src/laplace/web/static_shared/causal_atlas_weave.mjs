// Causal Atlas Weave — one deterministic focus+context renderer for Programme.
// Python owns identity, topology, compression, ordering and integer geometry.
// This module maps supplied geometry to pixels and emits reversible native controls.

const SCHEMA = "laplace.aisthesis-causal-atlas-weave/1";
const GRADES = Object.freeze(["far", "mid", "near", "audit"]);
const SVG_NS = "http://www.w3.org/2000/svg";

function node(tag, className, copy = null) {
  const value = document.createElement(tag);
  if (className) value.className = className;
  if (copy !== null) value.textContent = String(copy);
  return value;
}

function svgNode(tag, className) {
  const value = document.createElementNS(SVG_NS, tag);
  if (className) value.setAttribute("class", className);
  return value;
}

function index(rows, key) {
  const result = new Map();
  for (const row of Array.isArray(rows) ? rows : []) {
    const value = row && row[key];
    if (!value || result.has(String(value))) throw new Error(`duplicate or absent ${key}`);
    result.set(String(value), row);
  }
  return result;
}

function finiteBox(row) {
  return row && ["x", "y", "width", "height"].every((key) =>
    Number.isInteger(row[key]) && row[key] >= 0
  ) && row.width >= 44 && row.height >= 44;
}

function normalize(options = {}) {
  return {
    focusHandle: options.focusHandle || null,
    selectedEdgeId: options.selectedEdgeId || null,
    grade: GRADES.includes(options.grade) ? options.grade : "mid",
    onObject: options.onObject || null,
    onGroup: options.onGroup || null,
    onEdge: options.onEdge || null,
    onGrade: options.onGrade || null,
    onBack: options.onBack || null,
    onDescend: options.onDescend || null,
  };
}

function stateCopy(value) {
  const raw = String(value || "UNKNOWN");
  return raw === "CURRENT" ? "Current" : raw.replaceAll("_", " ").toLowerCase();
}

export function renderCausalAtlasWeave(container, weave, options = {}) {
  if (!(container instanceof HTMLElement)) throw new TypeError("container must be an HTMLElement");
  let model = weave;
  let view = normalize(options);
  let destroyed = false;

  function call(name, payload) {
    const fn = view[name];
    if (typeof fn === "function") fn(payload);
  }

  function refuse(message) {
    container.replaceChildren();
    const face = node("section", "causal-weave causal-weave--refused");
    face.dataset.state = "REFUSED";
    const title = node("strong", "causal-weave__refusal", "Causal field refused");
    const detail = node("p", "causal-weave__refusal-copy", message);
    face.append(title, detail);
    container.append(face);
  }

  function render() {
    if (destroyed) return;
    try {
      if (!model || model.schema_version !== SCHEMA) throw new Error("exact Causal Atlas Weave schema is absent");
      if (!GRADES.includes(model.grade)) throw new Error("semantic grade is invalid");
      if (!model.layout_receipt_handle) throw new Error("layout receipt is absent");
      const objects = index(model.objects, "object_handle");
      const edges = index(model.edges, "edge_id");
      const layout = model.layout;
      if (!layout || !Number.isInteger(layout.width) || !Number.isInteger(layout.height)) {
        throw new Error("producer geometry is absent");
      }
      for (const geometry of layout.objects || []) {
        if (!objects.has(String(geometry.object_handle)) || !finiteBox(geometry)) {
          throw new Error("object geometry does not match the supplied field");
        }
      }
      for (const geometry of layout.edges || []) {
        if (!edges.has(String(geometry.edge_id)) || !Array.isArray(geometry.points)
          || geometry.points.length < 2 || geometry.points.some((point) =>
            !Array.isArray(point) || point.length !== 2 || point.some((value) => !Number.isInteger(value)))) {
          throw new Error("edge geometry does not match the supplied field");
        }
      }

      container.replaceChildren();
      const root = node("section", "causal-weave");
      root.dataset.schema = SCHEMA;
      root.dataset.state = String(model.state || "UNKNOWN");
      root.dataset.grade = model.grade;
      root.dataset.viewport = String(model.viewport || "unknown");
      root.dataset.layoutReceipt = model.layout_receipt_handle;

      const header = node("header", "causal-weave__header");
      const titleGroup = node("div", "causal-weave__title-group");
      titleGroup.append(
        node("span", "causal-weave__eyebrow", "Live causal field"),
        node("h3", "causal-weave__title", "What moves, what governs it, what remains")
      );
      const status = node("span", "causal-weave__status", stateCopy(model.state));
      status.dataset.state = String(model.state || "UNKNOWN");
      header.append(titleGroup, status);

      const toolbar = node("div", "causal-weave__toolbar");
      toolbar.setAttribute("aria-label", "Semantic zoom");
      for (const grade of GRADES) {
        const button = node("button", "causal-weave__grade", grade[0].toUpperCase() + grade.slice(1));
        button.type = "button";
        button.dataset.grade = grade;
        button.style.minHeight = "44px";
        button.setAttribute("aria-pressed", String(model.grade === grade));
        button.addEventListener("click", () => call("onGrade", { grade }));
        toolbar.append(button);
      }
      const back = node("button", "causal-weave__back", "Back");
      back.type = "button";
      back.style.minHeight = "44px";
      back.disabled = typeof view.onBack !== "function";
      back.addEventListener("click", () => call("onBack"));
      toolbar.append(back);

      const field = node("div", "causal-weave__field");
      const available = Math.max(1, container.clientWidth || layout.width);
      const scale = Math.min(1, available / layout.width);
      const renderedWidth = Math.round(layout.width * scale * 1000) / 1000;
      const renderedHeight = Math.round(layout.height * scale * 1000) / 1000;
      field.style.width = `${renderedWidth}px`;
      field.style.height = `${renderedHeight}px`;
      field.style.setProperty("--weave-scale", String(scale));

      const svg = svgNode("svg", "causal-weave__threads");
      svg.setAttribute("width", String(renderedWidth));
      svg.setAttribute("height", String(renderedHeight));
      svg.setAttribute("viewBox", `0 0 ${renderedWidth} ${renderedHeight}`);
      svg.setAttribute("aria-hidden", "true");
      for (const geometry of layout.edges || []) {
        const edge = edges.get(String(geometry.edge_id));
        const path = svgNode("path", "causal-weave__thread");
        path.dataset.state = String(edge.state || "UNKNOWN");
        path.dataset.edge = String(edge.edge_id);
        path.setAttribute("d", geometry.points.map((point, offset) =>
          `${offset ? "L" : "M"} ${point[0] * scale} ${point[1] * scale}`).join(" "));
        svg.append(path);
        const label = svgNode("text", "causal-weave__thread-label");
        label.setAttribute("x", String(geometry.label_x * scale));
        label.setAttribute("y", String(geometry.label_y * scale - 7));
        label.setAttribute("text-anchor", "middle");
        label.textContent = String(edge.relation || "causes");
        svg.append(label);
      }
      field.append(svg);

      for (const geometry of layout.objects || []) {
        const object = objects.get(String(geometry.object_handle));
        const button = node("button", "causal-weave__object");
        button.type = "button";
        button.dataset.object = String(object.object_handle);
        button.dataset.semanticAnchor = String(object.object_handle);
        button.dataset.kind = String(object.kind || "object");
        button.dataset.family = String(object.family || "unknown");
        button.dataset.state = String(object.state || "UNKNOWN");
        button.dataset.compressed = String(object.kind === "compressed-group");
        button.setAttribute("aria-pressed", String(model.focus_handle === object.object_handle));
        button.setAttribute("aria-label", `${object.label}, ${stateCopy(object.state)}${object.member_count ? `, ${object.member_count} conserved` : ""}`);
        Object.assign(button.style, {
          left: `${geometry.x * scale}px`, top: `${geometry.y * scale}px`,
          width: `${geometry.width * scale}px`, height: `${geometry.height * scale}px`,
        });
        button.append(
          node("span", "causal-weave__object-family", object.family),
          node("strong", "causal-weave__object-label", object.label),
          node("span", "causal-weave__object-summary", object.summary || stateCopy(object.state))
        );
        button.addEventListener("click", () => {
          if (object.kind === "compressed-group") call("onGroup", { group: object });
          else call("onObject", { handle: object.object_handle, object });
        });
        field.append(button);
      }

      for (const geometry of layout.edges || []) {
        const edge = edges.get(String(geometry.edge_id));
        const hit = node("button", "causal-weave__edge-hit", edge.relation || "causal relation");
        hit.type = "button";
        Object.assign(hit.style, { minWidth: "44px", minHeight: "44px" });
        hit.dataset.edge = String(edge.edge_id);
        hit.dataset.semanticAnchor = String(edge.edge_id);
        hit.setAttribute("aria-pressed", String(model.selected_edge_id === edge.edge_id));
        hit.style.left = `${Math.max(0, geometry.label_x * scale - 52)}px`;
        hit.style.top = `${Math.max(0, geometry.label_y * scale - 24)}px`;
        hit.addEventListener("click", () => call("onEdge", { edgeId: edge.edge_id, edge }));
        field.append(hit);
      }

      const selected = objects.get(String(model.focus_handle));
      const context = node("section", "causal-weave__context");
      context.dataset.semanticAnchor = selected ? String(selected.object_handle) : "none";
      if (selected) {
        context.append(
          node("span", "causal-weave__context-kicker", `${selected.family} · ${stateCopy(selected.state)}`),
          node("h3", "causal-weave__context-title", selected.label),
          node("p", "causal-weave__context-copy", selected.summary || "Exact context is present without an additional claim.")
        );
        if (selected.continuation) {
          const descend = node("button", "causal-weave__descend", "Descend in place");
          descend.type = "button";
          descend.style.minHeight = "44px";
          descend.addEventListener("click", () => call("onDescend", { reference: selected.continuation, object: selected }));
          context.append(descend);
        }
        if (model.grade === "audit") {
          const well = node("div", "causal-weave__audit");
          well.append(node("strong", "", "Exact evidence for this attention"));
          for (const receipt of (selected.receipt_ids || []).filter(Boolean)) {
            well.append(node("code", "", receipt));
          }
          context.append(well);
        }
      }

      root.append(header, toolbar, field, context);
      root.addEventListener("keydown", (event) => {
        if (event.key === "Escape") { event.preventDefault(); call("onBack"); return; }
        if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
        const controls = [...root.querySelectorAll(".causal-weave__object")];
        const here = controls.indexOf(event.target.closest(".causal-weave__object"));
        if (here < 0 || !controls.length) return;
        event.preventDefault();
        const next = event.key === "Home" ? 0 : event.key === "End" ? controls.length - 1
          : (here + (["ArrowRight", "ArrowDown"].includes(event.key) ? 1 : -1) + controls.length) % controls.length;
        controls[next].focus();
      });
      container.append(root);
    } catch (error) {
      refuse(error instanceof Error ? error.message : String(error));
    }
  }

  render();
  return {
    update(nextWeave, nextOptions = {}) {
      model = nextWeave;
      view = normalize({ ...view, ...nextOptions });
      render();
    },
    destroy() {
      destroyed = true;
      container.replaceChildren();
    },
  };
}
