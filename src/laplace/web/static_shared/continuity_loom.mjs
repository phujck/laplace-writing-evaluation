// Deterministic read-only renderer for laplace.aisthesis-continuity-loom/1.
//
// The producer owns topology, ordering, compression membership, omissions, labels and
// integer geometry.  This module only maps the selected supplied geometry to pixels and
// emits native controls.  It has no fetch, store, history, acknowledgement or authority
// path.  The host owns Hymn styling and canonical navigation callbacks.

const SCHEMA = "laplace.aisthesis-continuity-loom/1";
const GRADES = Object.freeze(["far", "mid", "near", "audit"]);
const GEOMETRIES = Object.freeze(["wide", "medium", "narrow"]);
const CURRENTNESS = new Set(["CURRENT", "LAST-TRUSTED", "STALE", "UNKNOWN", "REFUSED"]);
const SVG_NS = "http://www.w3.org/2000/svg";

const DEFAULT_OPTIONS = Object.freeze({
  focusHandle: null,
  selectedEdgeId: null,
  grade: "mid",
  expositionGrade: 0,
  onObject: null,
  onGroup: null,
  onEdge: null,
  onGrade: null,
  onExposition: null,
  onDescend: null,
  onBack: null,
});

function element(tag, className, value = null) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (value !== null) node.textContent = String(value);
  return node;
}

function svgElement(tag, className) {
  const node = document.createElementNS(SVG_NS, tag);
  if (className) node.setAttribute("class", className);
  return node;
}

function finiteInteger(value) {
  return Number.isInteger(value) && Number.isFinite(value);
}

function stableJSON(value) {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableJSON).join(",")}]`;
  return `{${Object.keys(value).toSorted().map((key) =>
    `${JSON.stringify(key)}:${stableJSON(value[key])}`).join(",")}}`;
}

function sha256Hex(value) {
  const constants = [
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2,
  ];
  const bytes = new TextEncoder().encode(value);
  const total = Math.ceil((bytes.length + 9) / 64) * 64;
  const padded = new Uint8Array(total);
  padded.set(bytes); padded[bytes.length] = 0x80;
  const bits = BigInt(bytes.length) * 8n;
  for (let offset = 0; offset < 8; offset += 1) {
    padded[total - 1 - offset] = Number((bits >> BigInt(offset * 8)) & 255n);
  }
  const hash = new Uint32Array([
    0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,
    0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19,
  ]);
  const words = new Uint32Array(64);
  const rotate = (word, count) => (word >>> count) | (word << (32 - count));
  for (let chunk = 0; chunk < total; chunk += 64) {
    const view = new DataView(padded.buffer, chunk, 64);
    for (let index = 0; index < 16; index += 1) words[index] = view.getUint32(index * 4);
    for (let index = 16; index < 64; index += 1) {
      const left = words[index - 15];
      const right = words[index - 2];
      const sigma0 = rotate(left, 7) ^ rotate(left, 18) ^ (left >>> 3);
      const sigma1 = rotate(right, 17) ^ rotate(right, 19) ^ (right >>> 10);
      words[index] = (words[index - 16] + sigma0 + words[index - 7] + sigma1) >>> 0;
    }
    let [a,b,c,d,e,f,g,h] = hash;
    for (let index = 0; index < 64; index += 1) {
      const sum1 = rotate(e, 6) ^ rotate(e, 11) ^ rotate(e, 25);
      const choice = (e & f) ^ (~e & g);
      const temp1 = (h + sum1 + choice + constants[index] + words[index]) >>> 0;
      const sum0 = rotate(a, 2) ^ rotate(a, 13) ^ rotate(a, 22);
      const majority = (a & b) ^ (a & c) ^ (b & c);
      const temp2 = (sum0 + majority) >>> 0;
      h=g; g=f; f=e; e=(d+temp1)>>>0; d=c; c=b; b=a; a=(temp1+temp2)>>>0;
    }
    hash[0]=(hash[0]+a)>>>0; hash[1]=(hash[1]+b)>>>0;
    hash[2]=(hash[2]+c)>>>0; hash[3]=(hash[3]+d)>>>0;
    hash[4]=(hash[4]+e)>>>0; hash[5]=(hash[5]+f)>>>0;
    hash[6]=(hash[6]+g)>>>0; hash[7]=(hash[7]+h)>>>0;
  }
  return [...hash].map((word) => word.toString(16).padStart(8, "0")).join("");
}

function jsonDigest(value) {
  return `sha256:${sha256Hex(stableJSON(value))}`;
}

function selectedGeometry(loom) {
  const selected = String(loom && loom.selected_viewport || "");
  if (!GEOMETRIES.includes(selected)) {
    throw new Error("producer-selected viewport geometry is absent or invalid");
  }
  const receipted = loom && loom.layout_receipt && loom.layout_receipt.options
    ? String(loom.layout_receipt.options.selected_viewport || "") : "";
  if (receipted && receipted !== selected) {
    throw new Error("producer-selected viewport disagrees with its layout receipt");
  }
  return selected;
}

function normalOptions(options) {
  const out = { ...DEFAULT_OPTIONS, ...(options || {}) };
  if (!GRADES.includes(out.grade)) out.grade = "mid";
  const exposition = Number(out.expositionGrade);
  out.expositionGrade = Number.isInteger(exposition) && exposition >= 0 && exposition <= 7
    ? exposition : 0;
  out.focusHandle = out.focusHandle == null ? null : String(out.focusHandle);
  out.selectedEdgeId = out.selectedEdgeId == null ? null : String(out.selectedEdgeId);
  return out;
}

function indexBy(rows, key) {
  const out = new Map();
  for (const row of Array.isArray(rows) ? rows : []) {
    if (row && typeof row === "object" && row[key] != null) out.set(String(row[key]), row);
  }
  return out;
}

function suppliedLayout(loom, kind) {
  const geometry = loom && loom.geometry;
  const layout = geometry && geometry[kind];
  if (!layout || typeof layout !== "object") {
    throw new Error(`supplied ${kind} geometry is absent`);
  }
  if (!finiteInteger(layout.width) || layout.width <= 0
      || !finiteInteger(layout.height) || layout.height <= 0) {
    throw new Error(`supplied ${kind} geometry has invalid integer bounds`);
  }
  if (!Array.isArray(layout.objects) || !Array.isArray(layout.edges)) {
    throw new Error(`supplied ${kind} geometry omits ordered objects or edges`);
  }
  return layout;
}

function validateCompression(loom, objects, edges) {
  const compression = loom && loom.compression;
  const canonical = Array.isArray(compression && compression.canonical_order)
    ? compression.canonical_order.map(String) : null;
  const originals = Array.isArray(compression && compression.visible_original_handles)
    ? compression.visible_original_handles.map(String) : null;
  const groups = Array.isArray(compression && compression.groups) ? compression.groups : null;
  if (!canonical || !originals || !groups || new Set(canonical).size !== canonical.length) {
    throw new Error("compression coverage is absent or malformed");
  }
  const seen = new Set();
  for (const handle of originals) {
    if (seen.has(handle)) throw new Error("visible originals overlap compression membership");
    seen.add(handle);
  }
  for (const group of groups) {
    const handle = String(group && group.group_handle || "");
    const members = Array.isArray(group && group.ordered_member_handles)
      ? group.ordered_member_handles.map(String) : null;
    if (!handle || !objects.has(handle) || !members || !members.length
        || Number(objects.get(handle).member_count) !== members.length
        || String(objects.get(handle).member_digest || "") !== String(group.member_digest || "")
        || String(group.member_digest || "") !== jsonDigest(members)
        || !members.includes(String(group.boundary_member || ""))) {
      throw new Error("compressed group does not match its exact coverage face");
    }
    for (const member of members) {
      if (seen.has(member)) throw new Error("compressed groups are not disjoint");
      seen.add(member);
    }
  }
  if (seen.size !== canonical.length || canonical.some((handle) => !seen.has(handle))) {
    throw new Error("compression does not exactly cover canonical order");
  }
  const visible = Array.isArray(loom.ordered_visible_handles)
    ? loom.ordered_visible_handles.map(String) : [];
  if (visible.length !== objects.size || visible.some((handle) => !objects.has(handle))) {
    throw new Error("visible object order disagrees with compression projection");
  }
  const expectedSubject = loom.selected_edge_id
    ? `edge:${loom.selected_edge_id}`
    : (loom.focus_handle ? `object:${loom.focus_handle}` : null);
  if ((loom.selected_audit_subject || null) !== expectedSubject) {
    throw new Error("selected audit subject disagrees with focus and edge selection");
  }
  const options = loom.layout_receipt && loom.layout_receipt.options;
  if (!options || (options.selected_audit_subject || null) !== expectedSubject
      || String(options.compression_receipt_handle || "")
        !== String(compression.compression_receipt_handle || "")) {
    throw new Error("layout receipt does not bind compression and audit subject");
  }
  for (const edge of edges.values()) {
    if (!objects.has(String(edge.source_handle)) || !objects.has(String(edge.target_handle))) {
      throw new Error("display edge escapes the exact compressed object set");
    }
  }
  for (const cut of Array.isArray(compression.cut_edges) ? compression.cut_edges : []) {
    const edge = edges.get(String(cut && cut.edge_id || ""));
    const members = Array.isArray(cut && cut.ordered_member_edge_ids)
      ? cut.ordered_member_edge_ids.map(String) : null;
    if (!edge || !members || !members.length
        || stableJSON(edge.ordered_member_edge_ids) !== stableJSON(members)
        || String(edge.member_digest || "") !== String(cut.member_digest || "")
        || String(cut.member_digest || "") !== jsonDigest(members)) {
      throw new Error("cut edge does not match its exact member preimage");
    }
  }
  const compressionPreimage = { ...compression };
  delete compressionPreimage.compression_receipt_handle;
  if (jsonDigest(compressionPreimage) !== compression.compression_receipt_handle) {
    throw new Error("compression receipt does not bind exact group and cut membership");
  }
}

function validateObjectGeometry(row, objects) {
  const handle = String(row && row.object_handle || "");
  if (!handle || !objects.has(handle)) throw new Error(`geometry cites unknown object ${handle || "<empty>"}`);
  for (const key of ["x", "y", "width", "height"]) {
    if (!finiteInteger(row[key]) || row[key] < 0) {
      throw new Error(`object ${handle} has non-integer ${key}`);
    }
  }
  return handle;
}

function validateEdgeGeometry(row, edges) {
  const edgeId = String(row && row.edge_id || "");
  if (!edgeId || !edges.has(edgeId)) throw new Error(`geometry cites unknown edge ${edgeId || "<empty>"}`);
  if (!Array.isArray(row.points) || row.points.length < 2
      || row.points.some((point) => !Array.isArray(point) || point.length !== 2
        || !finiteInteger(point[0]) || !finiteInteger(point[1]))) {
    throw new Error(`edge ${edgeId} has invalid integer points`);
  }
  for (const key of ["control_x", "control_y", "control_width", "control_height"]) {
    if (!finiteInteger(row[key]) || row[key] < 0) {
      throw new Error(`edge ${edgeId} has non-integer ${key}`);
    }
  }
  if (row.label_slot !== true || row.control_width < 44 || row.control_height < 44) {
    throw new Error(`edge ${edgeId} lacks a dedicated readable label slot`);
  }
  return edgeId;
}

function rectanglesIntersect(a, b) {
  return a.x < b.x + b.width && a.x + a.width > b.x
    && a.y < b.y + b.height && a.y + a.height > b.y;
}

function validateLabelLanes(layout, kind) {
  for (const edge of layout.edges) {
    const label = { x: edge.control_x, y: edge.control_y, width: edge.control_width, height: edge.control_height };
    if (layout.objects.some((object) => rectanglesIntersect(label, object))) {
      throw new Error(`${kind} relation label ${edge.edge_id} intersects a node`);
    }
  }
}

function validateReceiptedLayout(loom, kind, layout, objects, edges) {
  const receipt = loom && loom.layout_receipt;
  const receipted = receipt && receipt.geometry && receipt.geometry[kind];
  if (!receipted || stableJSON(layout) !== stableJSON(receipted)) {
    throw new Error(`selected ${kind} geometry disagrees with its layout receipt`);
  }
  const objectHandles = layout.objects.map((row) => String(row.object_handle));
  const edgeIds = layout.edges.map((row) => String(row.edge_id));
  if (objectHandles.length !== objects.size || new Set(objectHandles).size !== objects.size
      || [...objects.keys()].some((handle) => !objectHandles.includes(handle))) {
    throw new Error("selected geometry does not exactly cover visible objects");
  }
  if (edgeIds.length !== edges.size || new Set(edgeIds).size !== edges.size
      || [...edges.keys()].some((edgeId) => !edgeIds.includes(edgeId))) {
    throw new Error("selected geometry does not exactly cover visible edges");
  }
  if (stableJSON(receipt.node_geometry) !== stableJSON(layout.objects)) {
    throw new Error("selected object geometry disagrees with receipted node geometry");
  }
  const endpoints = layout.edges.map((row) => ({
    edge_id: row.edge_id,
    source: { x: row.points[0][0], y: row.points[0][1] },
    target: { x: row.points[row.points.length - 1][0], y: row.points[row.points.length - 1][1] },
  }));
  if (stableJSON(receipt.endpoint_geometry) !== stableJSON(endpoints)) {
    throw new Error("selected edge geometry disagrees with receipted endpoints");
  }
  const receiptPreimage = { ...receipt };
  delete receiptPreimage.layout_receipt_handle;
  if (jsonDigest(receiptPreimage) !== receipt.layout_receipt_handle) {
    throw new Error("layout receipt handle does not bind its exact preimage");
  }
}

function px(value, scale) {
  return `${Math.round(value * scale * 1000) / 1000}px`;
}

function receiptRows(parent, ids) {
  for (const receipt of Array.isArray(ids) ? ids : []) {
    parent.append(element("code", "continuity-loom__receipt", receipt));
  }
}

function expositionFace(object, grade) {
  return (Array.isArray(object && object.exposition) ? object.exposition : [])
    .find((face) => {
      const value = face && face.grade;
      return Number(String(value).replace(/^E/, "")) === grade;
    }) || null;
}

function currentnessState(loom) {
  const nested = loom && loom.currentness && loom.currentness.state;
  const raw = String(nested || (loom && loom.state) || "UNKNOWN");
  return CURRENTNESS.has(raw) ? raw : "UNKNOWN";
}

function relationLabel(edge) {
  return String(edge.label || edge.relation || "causal relation");
}

/**
 * Mount one deterministic Continuity Loom.
 *
 * @param {HTMLElement} container host element owned by the Aisthesis page
 * @param {object} loom exact laplace.aisthesis-continuity-loom/1 projection
 * @param {object} options controlled selection and callbacks:
 *   {focusHandle, selectedEdgeId, grade, expositionGrade,
 *    onObject({handle, object}), onGroup({group}), onEdge({edgeId, edge}), onGrade({grade}),
 *    onExposition({grade, objectHandle}),
 *    onDescend({reference, objectHandle, grade}), onBack()}
 * @returns {{update(nextLoom: object, nextOptions?: object): void, destroy(): void}}
 */
export function renderContinuityLoom(container, loom, options = {}) {
  if (!(container instanceof HTMLElement)) throw new TypeError("container must be an HTMLElement");

  let model = loom;
  let view = normalOptions(options);
  let destroyed = false;
  let renderedWidth = -1;
  let observer = null;

  function announce(root, message) {
    const live = root.querySelector(".continuity-loom__announcement");
    if (live) live.textContent = message;
  }

  function callback(name, payload) {
    const fn = view[name];
    if (typeof fn === "function") fn(payload);
  }

  function selectObject(root, handle, object) {
    if (object.kind === "compressed-group") {
      callback("onGroup", { group: object });
      announce(root, `Opening ${object.label}`);
      return;
    }
    view.focusHandle = handle === view.focusHandle ? null : handle;
    render();
    callback("onObject", { handle: view.focusHandle, object });
    announce(root, view.focusHandle ? `Focused ${object.label}` : `Returned from ${object.label}`);
  }

  function selectEdge(root, edgeId, edge) {
    view.selectedEdgeId = edgeId === view.selectedEdgeId ? null : edgeId;
    render();
    callback("onEdge", { edgeId: view.selectedEdgeId, edge });
    announce(root, view.selectedEdgeId ? `Selected ${relationLabel(edge)}` : `Cleared ${relationLabel(edge)}`);
  }

  function renderRefusal(message, state = "UNKNOWN") {
    container.replaceChildren();
    const root = element("section", "continuity-loom");
    root.dataset.schema = SCHEMA;
    root.dataset.state = state;
    root.dataset.grade = view.grade;
    root.dataset.geometry = "unavailable";
    const status = element("p", "continuity-loom__currentness", `${state} · ${message}`);
    status.dataset.state = state;
    status.setAttribute("role", "alert");
    root.append(status, element("div", "continuity-loom__announcement"));
    root.lastElementChild.setAttribute("aria-live", "polite");
    container.append(root);
  }

  function renderHeader(root, state) {
    const header = element("header", "continuity-loom__header");
    const status = element("span", "continuity-loom__currentness", state);
    status.dataset.state = state;
    status.setAttribute("role", "status");
    const back = element("button", "continuity-loom__back", "Back");
    back.type = "button";
    back.disabled = typeof view.onBack !== "function";
    back.addEventListener("click", () => callback("onBack"));
    header.append(status, back);

    const grades = element("div", "continuity-loom__grades");
    grades.setAttribute("aria-label", "Visual descent");
    for (const grade of GRADES) {
      const button = element("button", "continuity-loom__grade", grade[0].toUpperCase() + grade.slice(1));
      button.type = "button";
      button.dataset.grade = grade;
      button.setAttribute("aria-pressed", String(view.grade === grade));
      button.addEventListener("click", () => {
        view.grade = grade;
        render();
        callback("onGrade", { grade });
      });
      grades.append(button);
    }
    root.append(header, grades);
  }

  function renderField(root, layout, kind, objects, edges) {
    const field = element("div", "continuity-loom__field");
    field.dataset.geometry = kind;
    const available = Math.max(1, container.clientWidth || layout.width);
    const scale = available / layout.width;
    field.style.height = px(layout.height, scale);

    const svg = svgElement("svg", "continuity-loom__weft");
    svg.setAttribute("width", String(available));
    svg.setAttribute("height", String(Math.round(layout.height * scale * 1000) / 1000));
    svg.setAttribute("viewBox", `0 0 ${available} ${Math.round(layout.height * scale * 1000) / 1000}`);
    svg.setAttribute("aria-hidden", "true");

    for (const geometry of layout.edges) {
      const edgeId = validateEdgeGeometry(geometry, edges);
      const edge = edges.get(edgeId);
      const path = svgElement("path", "continuity-loom__edge-path");
      path.dataset.edge = edgeId;
      path.dataset.state = String(edge.state || edge.evidence_state || "UNKNOWN");
      path.setAttribute("d", geometry.points.map((point, index) =>
        `${index ? "L" : "M"} ${Math.round(point[0] * scale * 1000) / 1000} ${Math.round(point[1] * scale * 1000) / 1000}`
      ).join(" "));
      svg.append(path);
    }
    field.append(svg);

    for (const geometry of layout.edges) {
      const edgeId = String(geometry.edge_id);
      const edge = edges.get(edgeId);
      const button = element("button", "continuity-loom__edge");
      button.type = "button";
      button.dataset.edge = edgeId;
      button.dataset.state = String(edge.state || edge.evidence_state || "UNKNOWN");
      button.setAttribute("aria-pressed", String(view.selectedEdgeId === edgeId));
      button.setAttribute("aria-label", `${relationLabel(edge)}, ${button.dataset.state}`);
      button.style.position = "absolute";
      button.style.left = px(geometry.control_x, scale);
      button.style.top = px(geometry.control_y, scale);
      button.style.width = px(geometry.control_width, scale);
      button.style.height = px(geometry.control_height, scale);
      button.append(element("span", "continuity-loom__edge-label", relationLabel(edge)));
      if (view.grade === "audit") {
        button.append(element("span", "continuity-loom__evidence-count", `${(edge.receipt_ids || []).length} evidence`));
      }
      button.addEventListener("click", () => selectEdge(root, edgeId, edge));
      field.append(button);
    }

    for (const geometry of layout.objects) {
      const handle = validateObjectGeometry(geometry, objects);
      const object = objects.get(handle);
      const compressed = Boolean(geometry.compressed || object.kind === "compressed-group");
      const button = element("button", "continuity-loom__object");
      button.type = "button";
      button.dataset.object = handle;
      button.dataset.kind = String(object.kind || "object");
      button.dataset.state = String(object.state || "UNKNOWN");
      button.dataset.compressed = String(compressed);
      button.setAttribute("aria-pressed", String(view.focusHandle === handle));
      button.setAttribute("aria-label", `${object.label || "Unnamed object"}, ${button.dataset.state}${compressed ? ", compressed context" : ""}`);
      button.style.position = "absolute";
      button.style.left = px(geometry.x, scale);
      button.style.top = px(geometry.y, scale);
      button.style.width = px(geometry.width, scale);
      button.style.height = px(geometry.height, scale);
      button.append(element("span", "continuity-loom__object-label", object.label || "Unnamed object"));
      button.append(element("span", "continuity-loom__object-state", button.dataset.state));
      if (compressed) {
        const count = Number.isInteger(object.member_count) ? object.member_count : "UNKNOWN";
        button.append(element("span", "continuity-loom__compression", `${count} conserved`));
      }
      if (view.grade === "audit") {
        button.append(element("span", "continuity-loom__evidence-count", `${(object.receipt_ids || []).length} evidence`));
      }
      button.addEventListener("click", () => selectObject(root, handle, object));
      field.append(button);
    }
    root.append(field);
  }

  function renderContext(root, object, auditSubject) {
    if (!object) return;
    const context = element("section", "continuity-loom__context");
    context.dataset.object = String(object.object_handle);
    context.append(element("h3", "continuity-loom__context-title", object.label || "Unnamed object"));
    context.append(element("span", "continuity-loom__context-state", object.state || "UNKNOWN"));

    const grades = element("div", "continuity-loom__exposition");
    grades.setAttribute("aria-label", "Object-relative exposition");
    for (let grade = 0; grade <= 7; grade += 1) {
      const button = element("button", "continuity-loom__exposition-grade", `E${grade}`);
      button.type = "button";
      button.dataset.exposition = String(grade);
      button.setAttribute("aria-pressed", String(view.expositionGrade === grade));
      button.addEventListener("click", () => {
        view.expositionGrade = grade;
        render();
        callback("onExposition", { grade, objectHandle: object.object_handle });
      });
      grades.append(button);
    }
    context.append(grades);

    const face = expositionFace(object, view.expositionGrade);
    const safeSpecimenInvalid = view.expositionGrade === 7
      && face && String(face.authority || "") !== "ZERO";
    const faceState = safeSpecimenInvalid ? "REFUSED" : String(face && face.state || "UNKNOWN");
    const copy = element(
      "p",
      "continuity-loom__exposition-copy",
      safeSpecimenInvalid
        ? "REFUSED · the specimen does not declare zero production authority"
        : (face && face.claim) || `${faceState} · no source-bearing exposition face was supplied`,
    );
    copy.dataset.state = faceState;
    copy.dataset.authority = String(face && face.authority || "NONE");
    context.append(copy);
    if (view.grade === "audit" && auditSubject === `object:${object.object_handle}`) {
      const well = element("div", "continuity-loom__audit-well");
      well.append(element("strong", "continuity-loom__audit-title", "Exact evidence for this object"));
      receiptRows(well, object.receipt_ids);
      receiptRows(well, face && face.source_references);
      if (object.kind === "compressed-group") {
        receiptRows(well, object.ordered_member_handles);
        if (object.member_digest) well.append(element("code", "continuity-loom__receipt", object.member_digest));
      }
      context.append(well);
    }

    const descent = (face && face.descend) || object.descend;
    if (descent && descent.reference) {
      const button = element("button", "continuity-loom__descend", descent.label || "Descend to canonical source");
      button.type = "button";
      button.disabled = typeof view.onDescend !== "function";
      button.addEventListener("click", () => callback("onDescend", {
        reference: descent.reference,
        objectHandle: object.object_handle,
        grade: view.expositionGrade,
      }));
      context.append(button);
    }
    root.append(context);
  }

  function renderEdgeContext(root, edge, auditSubject) {
    if (!edge) return;
    const context = element("section", "continuity-loom__context continuity-loom__edge-context");
    context.dataset.edge = String(edge.edge_id);
    context.append(element("h3", "continuity-loom__context-title", relationLabel(edge)));
    context.append(element("p", "continuity-loom__context-meaning", `${edge.state || "UNKNOWN"} · ${(edge.receipt_ids || []).length} exact evidence item${(edge.receipt_ids || []).length === 1 ? "" : "s"}`));
    if (view.grade === "audit" && auditSubject === `edge:${edge.edge_id}`) {
      const well = element("div", "continuity-loom__audit-well");
      well.append(element("strong", "continuity-loom__audit-title", "Exact evidence for this relation"));
      receiptRows(well, edge.receipt_ids);
      if (edge.kind === "cut-edge") {
        receiptRows(well, edge.ordered_member_edge_ids);
        if (edge.member_digest) well.append(element("code", "continuity-loom__receipt", edge.member_digest));
      }
      context.append(well);
    }
    root.append(context);
  }

  function renderOmissions(root) {
    const rows = Array.isArray(model && model.omission_residual) ? model.omission_residual : [];
    const section = element("section", "continuity-loom__omissions");
    section.setAttribute("aria-label", "Conserved omissions");
    for (const omission of rows) {
      const button = element("button", "continuity-loom__omission");
      button.type = "button";
      button.dataset.class = String(omission.class || "UNRESOLVED");
      button.dataset.state = String(omission.state || "UNKNOWN");
      const count = Number.isInteger(omission.count) ? `${omission.count} · ` : "";
      button.textContent = `${count}${omission.label || omission.class || "omission"}`;
      button.setAttribute("aria-label", `${button.textContent}, ${button.dataset.state}`);
      const continuation = omission.continuation;
      button.disabled = !(continuation && continuation.reference && typeof view.onDescend === "function");
      button.addEventListener("click", () => callback("onDescend", {
        reference: continuation.reference,
        objectHandle: null,
        grade: view.expositionGrade,
      }));
      section.append(button);
    }
    root.append(section);
  }

  function wireKeyboard(root) {
    root.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && typeof view.onBack === "function") {
        event.preventDefault();
        callback("onBack");
        return;
      }
      if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
      const target = event.target.closest("button");
      if (!target) return;
      const selector = target.matches(".continuity-loom__object, .continuity-loom__edge")
        ? ".continuity-loom__object, .continuity-loom__edge"
        : target.matches(".continuity-loom__grade")
          ? ".continuity-loom__grade"
          : target.matches(".continuity-loom__exposition-grade")
            ? ".continuity-loom__exposition-grade" : null;
      if (!selector) return;
      const controls = [...root.querySelectorAll(selector)].filter((button) => !button.disabled);
      const here = controls.indexOf(target);
      if (here < 0 || !controls.length) return;
      event.preventDefault();
      const next = event.key === "Home" ? 0 : event.key === "End" ? controls.length - 1
        : (here + (["ArrowRight", "ArrowDown"].includes(event.key) ? 1 : -1) + controls.length) % controls.length;
      controls[next].focus();
    });
  }

  function render() {
    if (destroyed) return;
    if (!model || model.schema_version !== SCHEMA) {
      renderRefusal("exact Continuity Loom schema is absent", "UNKNOWN");
      return;
    }
    const state = currentnessState(model);
    const objects = indexBy(model.objects, "object_handle");
    const edges = indexBy(model.edges, "edge_id");
    const width = Math.max(1, container.clientWidth || 1);
    let layout;
    let kind;
    try {
      kind = selectedGeometry(model);
      layout = suppliedLayout(model, kind);
      validateCompression(model, objects, edges);
      for (const row of layout.objects) validateObjectGeometry(row, objects);
      for (const row of layout.edges) validateEdgeGeometry(row, edges);
      validateReceiptedLayout(model, kind, layout, objects, edges);
      if (kind !== "wide") validateLabelLanes(layout, kind);
    } catch (error) {
      renderRefusal(error.message, "UNKNOWN");
      return;
    }

    container.replaceChildren();
    const root = element("section", "continuity-loom");
    root.dataset.schema = SCHEMA;
    root.dataset.state = state;
    root.dataset.grade = view.grade;
    root.dataset.geometry = kind;
    root.dataset.focus = view.focusHandle || "";
    root.dataset.reducedMotion = typeof matchMedia === "function"
      && matchMedia("(prefers-reduced-motion: reduce)").matches ? "true" : "false";
    renderHeader(root, state);
    renderField(root, layout, kind, objects, edges);
    renderContext(root, objects.get(view.focusHandle), model.selected_audit_subject || null);
    renderEdgeContext(root, edges.get(view.selectedEdgeId), model.selected_audit_subject || null);
    renderOmissions(root);
    const live = element("div", "continuity-loom__announcement");
    live.setAttribute("aria-live", "polite");
    root.append(live);
    wireKeyboard(root);
    container.append(root);
    renderedWidth = width;
  }

  const controller = {
    update(nextLoom, nextOptions = {}) {
      if (destroyed) return;
      model = nextLoom;
      view = normalOptions({ ...view, ...nextOptions });
      render();
    },
    destroy() {
      if (destroyed) return;
      destroyed = true;
      if (observer) observer.disconnect();
      container.replaceChildren();
    },
  };

  if (typeof ResizeObserver === "function") {
    observer = new ResizeObserver(() => {
      const width = Math.max(1, container.clientWidth || 1);
      if (Math.abs(width - renderedWidth) >= 1) render();
    });
    observer.observe(container);
  }
  render();
  return controller;
}
