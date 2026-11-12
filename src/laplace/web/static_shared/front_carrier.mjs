// THE FRONT CARRIER (legacy artefact page). Purpose: the page shell of the artefact/manuscript
// workbench route: store-backed state, the front feedback band and the manuscript work surface.
// Ownership: store.mjs owns state; front_feedback.mjs and manuscript_work_surface.mjs own their
// panes and the owner calls they make; this carrier composes them and routes page events. Public
// contract: the page's mount (module side effect on import). Inputs: the route and owner reads;
// outputs: DOM. Currentness: per owner read; no cache of its own. Storage: the store's.
// Retired path: the writing workspace (workspace.mjs) is the project's primary page; this carrier
// remains for the artefact route and migrates no further in M5.
import store from "/shared/store.mjs";
import { mountFrontFeedback } from "/shared/front_feedback.mjs";
import { renderManuscriptWorkSurface } from "/shared/manuscript_work_surface.mjs";

const ROOMS = [
  { id: "now", name: "Now", title: "What needs you", purpose: "The consequential present, with everything else held nearby." },
  { id: "programme", name: "Programme", title: "The shape of the work", purpose: "Dependencies, sequence and consequence across the active programme." },
  { id: "work", name: "Work", title: "Work under custody", purpose: "What is being made, reviewed or held, and what each object needs next." },
  { id: "decision", name: "Decision", title: "Your judgment", purpose: "Questions that genuinely require the author, with their consequence in view." },
  { id: "run", name: "Run", title: "What is happening", purpose: "Execution as a time-bearing sequence, not a wall of telemetry." },
  { id: "conversation", name: "Conversation", title: "The causal conversation", purpose: "From authored turn through delivery and reconstruction to a rooted reply." },
  { id: "exposition", name: "Exposition", title: "Understand this object", purpose: "Purpose, mechanism, mathematics and evidence around the object in attention." },
  { id: "diagnostics", name: "Diagnostics", title: "Where trust breaks", purpose: "Currentness, omissions and unavailable evidence, kept out of the resting face." },
];

const ROOM_IDS = new Set(ROOMS.map((room) => room.id));
const GRADES = ["far", "mid", "near", "audit"];
const GRADE_LABEL = { far: "summary", mid: "picture", near: "detail", audit: "audit" };
const LENS_CAMERA = {
  now: "critical-path",
  programme: "programme",
  work: "live-custody",
  decision: "residual-crutch",
  run: "lens-self",
  conversation: "continuity",
  exposition: "evidence-descent",
  diagnostics: "lens-self",
};

const $ = (selector, root = document) => root.querySelector(selector);
const els = {
  carrier: $("[data-aisthesis-carrier=\"1\"]"),
  rooms: $("#rooms"),
  roomField: $("#room-field"),
  field: $("#field"),
  context: $("#context-body"),
  contextShell: $("#context"),
  contextHome: $("#context-home"),
  back: $("#back"),
  roomKicker: $("#room-kicker"),
  roomTitle: $("#room-title"),
  roomPurpose: $("#room-purpose"),
  orientationTitle: $("#orientation-title"),
  orientationPurpose: $("#orientation-purpose"),
  currentness: $("#currentness"),
  orientationFocus: $("#orientation-focus"),
  orientationBreak: $("#orientation-break"),
  orientationPredecessor: $("#orientation-predecessor"),
  orientationSuccessor: $("#orientation-successor"),
  orientationOmitted: $("#orientation-omitted"),
  status: $("#status-live"),
  help: $("#help"),
};

let model = null;
let activeState = store.get();
let renderEpoch = 0;
let refreshTimer = 0;
let stream = null;
let firstState = true;

function el(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== "") node.textContent = text;
  return node;
}

function own(value, key) {
  return value && Object.prototype.hasOwnProperty.call(value, key);
}

function asArray(value) {
  if (Array.isArray(value)) return value;
  if (value && typeof value === "object") return Object.values(value);
  return [];
}

function plain(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function humanText(value, fallback = "") {
  if (value === null || value === undefined) return fallback;
  let text = String(value).replace(/\s+/g, " ").trim();
  if (!text) return fallback;
  text = text
    .replace(/(?:sha256:|message:)[0-9a-f]{16,}/gi, "an exact receipt")
    .replace(/region-lease:[0-9a-f]{16,}/gi, "an exact lease");
  return text;
}

function bindFeedbackAnchors(root) {
  for (const node of root.querySelectorAll("[data-semantic-handle],[data-semantic-edge]")) {
    const semanticAnchor = humanText(node.dataset.semanticHandle || node.dataset.semanticEdge);
    if (!semanticAnchor) continue;
    node.dataset.semanticAnchor = semanticAnchor;
    node.dataset.semanticKind = node.dataset.semanticEdge
      ? "edge"
      : node.hasAttribute("data-omission") ? "omission"
        : node.hasAttribute("data-residual") ? "residual" : "object";
    if (!node.dataset.semanticLabel) {
      node.dataset.semanticLabel = humanText(
        node.getAttribute("aria-label") || node.querySelector(
          ".object-title,.node-title,.phase-band-name,.phase-name,.moment-title,.decision-title",
        )?.textContent || node.textContent,
        "Semantic object",
      ).slice(0, 240);
    }
  }
}

function rawHandle(object) {
  if (!object || typeof object !== "object") return "";
  return String(
    object.handle ?? object.object_handle ?? object.node_handle ?? object.focus_handle
    ?? object.turn_handle ?? object.room_handle ?? object.semantic_memory_handle
    ?? object.binding_observatory_handle ?? object.id ?? object.edge_id ?? "",
  );
}

function labelOf(object, fallback = "Object") {
  if (typeof object === "string") return humanText(object, fallback);
  const source = plain(object);
  return humanText(
    source.human_label ?? source.label ?? source.title ?? source.noun ?? source.name
    ?? source.face ?? source.display_name,
    fallback,
  );
}

function sayOf(object, fallback = "") {
  const source = plain(object);
  return humanText(
    source.why ?? source.purpose ?? source.summary ?? source.description ?? source.say
    ?? source.reason ?? source.gloss ?? source.next_act,
    fallback,
  );
}

function stateOf(object, fallback = "UNKNOWN") {
  const source = plain(object);
  return humanText(
    source.currentness ?? source.state ?? source.status ?? source.capture_state
    ?? source.freshness ?? fallback,
    fallback,
  ).toUpperCase();
}

function stateTone(state) {
  const word = String(state || "").toUpperCase();
  if (/CURRENT|COMPLETE|BOUND|READY|ACTIVE|PASS|CLEAR/.test(word)) return "ok";
  if (/REFUS|FAIL|ERROR|BLOCK|DISPLACED|QUARANTIN/.test(word)) return "bad";
  if (/STALE|LAST.TRUSTED|BUDGET|TRUNCAT|PENDING|OPEN|LAPSED/.test(word)) return "warn";
  return "unknown";
}

function roomFromState(state) {
  const candidate = state?.selection?.lens;
  return ROOM_IDS.has(candidate) ? candidate : "now";
}

function gradeFromState(state) {
  const candidate = state?.selection?.grade;
  return GRADES.includes(candidate) ? candidate : "far";
}

function expositionFromState(state) {
  const candidate = state?.selection?.exposition;
  return /^E[0-7]$/.test(candidate || "") ? candidate : "E0";
}

function viewportClass() {
  if (window.matchMedia("(max-width: 720px)").matches) return "narrow";
  if (window.matchMedia("(max-width: 1060px)").matches) return "medium";
  return "wide";
}

function selectionPatch(patch = {}) {
  const current = store.get().selection;
  return {
    lens: own(patch, "lens") ? patch.lens : (current.lens || "now"),
    focus: own(patch, "focus") ? patch.focus : current.focus,
    grade: own(patch, "grade") ? patch.grade : (current.grade || "far"),
    edge: own(patch, "edge") ? patch.edge : current.edge,
    exposition: own(patch, "exposition") ? patch.exposition : (current.exposition || "E0"),
  };
}

function move(patch, options = {}) {
  return store.set(selectionPatch(patch), options);
}

function announce(message, timeout = 2600) {
  els.status.textContent = message;
  els.status.hidden = false;
  window.clearTimeout(els.status._timer);
  els.status._timer = window.setTimeout(() => { els.status.hidden = true; }, timeout);
}

function renderRoomDoors() {
  const restore = document.activeElement?.dataset?.roomDoor ?? null;
  els.rooms.replaceChildren();
  ROOMS.forEach((room, index) => {
    const button = el("button", "room-door");
    button.type = "button";
    button.dataset.roomDoor = room.id;
    button.dataset.primaryControl = "";
    button.dataset.anchor = `room-${room.id}`;
    button.setAttribute("aria-current", roomFromState(activeState) === room.id ? "page" : "false");
    button.append(el("span", "room-key", String(index + 1)));
    const copy = el("span");
    copy.append(el("span", "room-name", room.name), el("span", "room-purpose", room.purpose));
    button.append(copy);
    button.addEventListener("click", () => move({ lens: room.id }));
    els.rooms.append(button);
  });
  if (restore) els.rooms.querySelector(`[data-room-door="${restore}"]`)?.focus();
}

function setCurrentness(value, reason = "") {
  let word = stateOf({ state: value });
  if (word === "LAST_TRUSTED") word = "LAST-TRUSTED";
  const key = /CURRENT|READY|CLEAR/.test(word) ? "current"
    : /LAST.TRUSTED/.test(word) ? "last-trusted"
      : /STALE/.test(word) ? "stale"
        : /REFUS|FAIL|ERROR/.test(word) ? "refused" : "unknown";
  els.currentness.dataset.state = key;
  const label = $("span", els.currentness);
  if (label) label.textContent = humanText(word.replaceAll("_", " "), "Unknown");
  els.currentness.title = humanText(reason, "");
  document.body.dataset.currentness = key;
  els.carrier.dataset.currentness = word;
}

function modelStatus(payload) {
  const carrier = carrierModel(payload);
  const status = payload?.currentness?.status ?? payload?.currentness?.state ?? payload?.currentness
    ?? carrier?.semantic_memory?.state ?? carrier?.active_room?.status
    ?? payload?.status ?? carrier?.status ?? "UNKNOWN";
  const reason = payload?.currentness?.reason ?? payload?.reason ?? payload?.error ?? "";
  setCurrentness(status, reason);
}

function withObjectIdentity(object, index) {
  const source = plain(object);
  const handle = rawHandle(source) || `visible-object-${index + 1}`;
  return { ...source, _handle: handle, _index: index };
}

function carrierModel(payload) {
  return plain(payload?.model ?? payload);
}

function firstUseful(...values) {
  for (const value of values) {
    const items = asArray(value).filter((item) => item && typeof item === "object");
    if (items.length) return items.map(withObjectIdentity);
  }
  return [];
}

function roomPayload(payload, room) {
  const carrier = carrierModel(payload);
  const row = asArray(carrier.rooms).find((item) =>
    String(item?.room_id || "").toLowerCase() === room);
  if (row) return plain(row.payload ?? row);
  const active = plain(carrier.active_room);
  if (String(active.room_id || "").toLowerCase() === room) return plain(active.payload ?? active);
  return plain(carrier.rooms?.[room] ?? carrier.foreground_room ?? carrier.room_model?.[room]
    ?? carrier?.[room]);
}

function roomFace(payload, room) {
  const carrier = carrierModel(payload);
  return asArray(carrier.rooms).find((item) =>
    String(item?.room_id || "").toLowerCase() === room) ?? plain(carrier.active_room);
}

function admittedOrRoom(payload, room, ...values) {
  const found = firstUseful(...values);
  const focus = activeState?.selection?.focus;
  if (focus && !found.some((item) => rawHandle(item) === focus)) {
    const exact = plain(payload?.focused_object ?? payload?.focus_object);
    found.unshift(rawHandle(exact) === focus ? withObjectIdentity(exact, -1) : {
      handle: focus,
      human_label: "Attended object",
      summary: "This room preserves its identity but has not supplied a richer object-relative face.",
      state: "UNKNOWN",
      _handle: focus,
      _index: -1,
    });
  }
  if (found.length) return found;
  const face = roomFace(payload, room);
  return face && Object.keys(face).length ? [withObjectIdentity(face, 0)] : [];
}

function modelObjects(payload, room) {
  const part = roomPayload(payload, room);
  if (room === "now") {
    const coordination = plain(carrierModel(payload).coordination_phase);
    const coordinationObjects = asArray(coordination.phase_bands).map((band) => ({
      ...band,
      handle: `coordination-phase:${humanText(band.phase, "unknown")}`,
      human_label: band.label,
      summary: band.condition ?? "Operational consumption evidence has not established this phase.",
      state: band.status ?? "UNKNOWN",
      evidence: band.evidence,
      continuation: band.continuation,
      object_kind: "coordination-phase",
    }));
    return admittedOrRoom(payload, room,
      [...asArray(part.objects), ...coordinationObjects], part.items, payload?.attention, payload?.critical_path,
      payload?.development?.critical_path, payload?.development?.objects,
      payload?.apex?.asks, payload?.apex?.campaign?.stages,
    );
  }
  if (room === "programme") {
    return admittedOrRoom(payload, room,
      part.objects, part.nodes, payload?.programme?.objects,
      payload?.development?.causal_atlas_weave?.objects,
      payload?.development?.programme_field,
    );
  }
  if (room === "work") {
    return admittedOrRoom(payload, room, part.objects, part.work, payload?.work, payload?.development?.objects);
  }
  if (room === "decision") {
    return admittedOrRoom(payload, room, part.objects, part.decisions, payload?.decisions, payload?.apex?.asks);
  }
  if (room === "run") {
    return admittedOrRoom(payload, room, part.objects, part.events, part.moments, payload?.run, payload?.events);
  }
  if (room === "conversation") {
    const field = payload?.development?.continuity_field;
    return admittedOrRoom(payload, room, part.objects, part.phases, payload?.conversation?.objects, field?.objects);
  }
  if (room === "diagnostics") {
    return admittedOrRoom(payload, room, part.objects, part.diagnostics, payload?.places?.places, payload?.residuals);
  }
  return admittedOrRoom(payload, room, part.objects, payload?.development?.objects);
}

function selectedObject(payload, state) {
  const focus = state?.selection?.focus;
  const room = roomFromState(state);
  const objects = modelObjects(payload, room);
  const found = objects.find((object) => rawHandle(object) === focus)
    ?? plain(payload?.focused_object ?? payload?.focus_object ?? roomPayload(payload, room).focused_object);
  if (Object.keys(found).length) return found;
  const carrier = carrierModel(payload);
  if (focus && focus === carrier.model_handle) {
    const active = roomFace(payload, room);
    return {
      handle: carrier.model_handle,
      human_label: "Eigen's current field",
      summary: active?.purpose ?? "The exact read model shared by every contextual room.",
      state: carrier.semantic_memory?.state ?? active?.status ?? "UNKNOWN",
    };
  }
  return found;
}

function exactEndpointModel() {
  const selection = store.get().selection;
  const room = roomFromState(store.get());
  const grade = gradeFromState(store.get());
  const camera = LENS_CAMERA[room];
  const common = {
    focus: selection.focus,
    edge: selection.edge,
    grade,
    exposition: expositionFromState(store.get()),
    viewport: viewportClass(),
  };
  return Promise.allSettled([
    store.fetchJSON("/front/places", { params: { format: "json" } }),
    store.fetchJSON("/front/apex", { params: { format: "json" } }),
    store.fetchJSON("/front/development", { params: { ...common, format: "json", lens: camera } }),
  ]).then(([places, apex, development]) => {
    const payload = {
      schema_version: "laplace.aisthesis-carrier-fallback/1",
      status: "UNKNOWN",
      reason: "The joined front model is unavailable; exact endpoint projections are shown independently.",
    };
    if (places.status === "fulfilled") payload.places = places.value;
    if (apex.status === "fulfilled") payload.apex = apex.value;
    if (development.status === "fulfilled") {
      payload.development = development.value;
      payload.status = development.value?.status ?? "UNKNOWN";
    }
    const failures = [places, apex, development].filter((item) => item.status === "rejected");
    payload.endpoint_failures = failures.map((item) => humanText(item.reason?.message, "Endpoint refused"));
    if (!payload.places && !payload.apex && !payload.development) {
      throw new Error(payload.endpoint_failures.join(" · ") || "No exact front endpoint answered");
    }
    return payload;
  });
}

async function fetchModel(signal) {
  const selection = store.get().selection;
  try {
    return await store.fetchJSON("/front/model", {
      inject: ["project", "corpus", "focus", "grade", "exposition", "lens", "edge"],
      params: { viewport: viewportClass() },
      signal,
    });
  } catch (error) {
    if (signal.aborted) throw error;
    return exactEndpointModel();
  }
}

function notice(title, copy, kind = "unknown") {
  const box = el("div", "notice");
  box.dataset.kind = kind;
  box.append(el("h3", "", title), el("p", "", humanText(copy, "No further evidence was supplied.")));
  return box;
}

function focusPatchFor(object, requestedGrade = null) {
  const continuation = plain(object?.continuation);
  const compressed = object?.kind === "compressed-group" || object?.object_kind === "compressed-group";
  const focus = compressed
    ? humanText(continuation.focus_handle ?? object?.boundary_member, rawHandle(object))
    : rawHandle(object);
  const grade = requestedGrade ?? (compressed
    ? humanText(continuation.grade, "near")
    : (gradeFromState(activeState) === "far" ? "mid" : gradeFromState(activeState)));
  return { focus, edge: null, grade: GRADES.includes(grade) ? grade : "near" };
}

function objectButton(object) {
  const button = el("button", "object-row");
  button.type = "button";
  button.dataset.object = rawHandle(object);
  button.dataset.semanticObject = "";
  button.dataset.semanticHandle = rawHandle(object);
  button.dataset.anchor = "visible-object";
  button.dataset.selected = String(rawHandle(object) === activeState.selection.focus);
  const copy = el("span");
  copy.append(el("span", "object-title", labelOf(object)));
  const say = sayOf(object);
  if (say) copy.append(el("span", "object-say", say));
  const state = stateOf(object);
  button.dataset.state = state.toLowerCase();
  button.dataset.tone = stateTone(state);
  const stateNode = el("span", "object-state", humanText(state.replaceAll("_", " ")));
  stateNode.dataset.tone = stateTone(state);
  button.append(copy, stateNode);
  if (object?.member_count !== undefined) button.dataset.memberCount = String(object.member_count);
  if (object?.continuation) button.dataset.hasContinuation = "true";
  button.addEventListener("click", () => move(focusPatchFor(object)));
  return button;
}

function renderObjectList(objects, emptyCopy = "No objects were admitted to this view.") {
  if (!objects.length) return notice("Nothing confidently shown", emptyCopy, "unknown");
  const list = el("div", "object-list attention-field");
  list.dataset.anchor = "object-list";
  list.dataset.visibleCount = String(objects.length);
  const head = el("div", "attention-field-head");
  head.append(
    el("span", "coordination-kicker", "Context held around attention"),
    el("span", "attention-count", `${objects.length} ${objects.length === 1 ? "object" : "objects"} · names and states conserved`),
  );
  list.append(head);
  for (const object of objects) list.append(objectButton(object));
  return list;
}

function countValue(value) {
  if (typeof value === "number") return String(value);
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return humanText(value, "Unknown");
}

function renderNow(payload) {
  const part = roomPayload(payload, "now");
  const wrapper = el("div", "now-world");
  wrapper.dataset.anchor = "now-attention-world";
  const brief = el("div", "brief");
  brief.dataset.anchor = "now-brief";
  const copy = el("div", "brief-copy");
  copy.append(
    el("h3", "", labelOf(part, "The present state")),
    el("p", "", sayOf(part, "Eigen has reconstructed the current read face. Choose the object that deserves attention.")),
  );
  const facts = el("div", "brief-facts");
  const factSource = plain(part.facts ?? payload?.summary ?? payload?.apex?.account);
  const candidates = Object.entries(factSource).filter(([, value]) =>
    ["string", "number", "boolean"].includes(typeof value),
  ).slice(0, 5);
  for (const [key, value] of candidates) {
    const fact = el("div", "fact");
    fact.append(
      el("span", "fact-label", humanText(key.replaceAll("_", " "))),
      el("span", "fact-value", countValue(value)),
    );
    facts.append(fact);
  }
  brief.append(copy, facts);
  const presentObjects = modelObjects(payload, "now").filter((item) => item.object_kind !== "coordination-phase");
  const orbit = renderObjectList(
    presentObjects,
    "No ranked present object was supplied; this is absence, not a clear account.",
  );
  orbit.classList.add("now-orbit");
  wrapper.append(brief, renderCoordinationPhase(payload), orbit);
  return wrapper;
}

function renderCoordinationPhase(payload) {
  const face = plain(carrierModel(payload).coordination_phase);
  const wrap = el("section", "coordination-ribbon");
  wrap.dataset.anchor = "coordination-phase";
  const intro = el("div", "coordination-copy");
  intro.append(
    el("span", "coordination-kicker", "Coordination phase"),
    el("h3", "", humanText(face.current_phase, "UNKNOWN").replaceAll("-", " ")),
    el("p", "", face.status === "CURRENT"
      ? "The current phase is bound to an operational consumption receipt."
      : "No operational consumption receipt is present; the phase remains UNKNOWN."),
  );
  const bands = el("div", "phase-bands");
  for (const band of asArray(face.phase_bands)) {
    const button = el("button", "phase-band");
    button.type = "button";
    button.dataset.state = humanText(band.status, "UNKNOWN").toLowerCase();
    button.dataset.semanticObject = "";
    button.dataset.semanticHandle = `coordination-phase:${humanText(band.phase, "unknown")}`;
    button.append(
      el("span", "phase-band-name", humanText(band.label, band.phase)),
      el("span", "phase-band-state", humanText(band.status, "UNKNOWN")),
    );
    button.addEventListener("click", () => move({
      focus: button.dataset.semanticHandle,
      grade: gradeFromState(activeState) === "far" ? "mid" : gradeFromState(activeState),
      edge: null,
    }));
    bands.append(button);
  }
  wrap.append(intro, bands);
  return wrap;
}

function geometryFor(payload) {
  const part = roomPayload(payload, "programme");
  const weave = plain(part.weave ?? part.field ?? payload?.programme?.field
    ?? payload?.development?.causal_atlas_weave);
  const layout = plain(weave.layout ?? weave.geometry ?? weave.layout_receipt?.geometry);
  const objects = firstUseful(weave.objects, weave.nodes, layout.objects);
  const edges = firstUseful(weave.edges, layout.edges);
  return { weave, layout, objects, edges };
}

function geometryRow(layout, object) {
  const rows = asArray(layout.objects);
  const handle = rawHandle(object);
  return plain(rows.find((row) => rawHandle(row) === handle) ?? object.geometry);
}

function geometryEdge(layout, edge) {
  const rows = asArray(layout.edges);
  const handle = rawHandle(edge);
  return plain(rows.find((row) => rawHandle(row) === handle) ?? edge.geometry);
}

function renderProgramme(payload) {
  const { layout, objects, edges } = geometryFor(payload);
  if (!objects.length) return renderObjectList(modelObjects(payload, "programme"), "No programme topology was admitted.");
  const placed = objects.map((object) => ({ object, row: geometryRow(layout, object) }));
  const exact = placed.every(({ row }) => [row.x, row.y, row.width ?? row.w, row.height ?? row.h]
    .every((value) => Number.isFinite(Number(value))));
  if (!exact) {
    const wrapper = el("div");
    wrapper.append(
      notice("Spatial receipt unavailable", "The objects are listed without inventing layout; geometry must come from the producer.", "unknown"),
      renderObjectList(objects),
    );
    return wrapper;
  }
  const maxX = Math.max(...placed.map(({ row }) => Number(row.x) + Number(row.width ?? row.w)));
  const maxY = Math.max(...placed.map(({ row }) => Number(row.y) + Number(row.height ?? row.h)));
  const width = Number(layout.width) || maxX + 32;
  const height = Number(layout.height) || maxY + 32;
  const holder = el("div", "causal-field");
  holder.dataset.anchor = "programme-causal-field";
  holder.dataset.spatialField = "";
  holder.dataset.layoutAxis = viewportClass() === "narrow" ? "vertical" : "layered";
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("role", "group");
  svg.setAttribute("aria-label", "Programme causal field");
  svg.dataset.grade = gradeFromState(activeState);
  for (const edge of edges) {
    const row = geometryEdge(layout, edge);
    const pathValue = row.path ?? row.d;
    let path = null;
    if (typeof pathValue === "string" && pathValue.trim()) {
      path = document.createElementNS(ns, "path");
      path.setAttribute("d", pathValue);
    } else if ([row.x1, row.y1, row.x2, row.y2].every((value) => Number.isFinite(Number(value)))) {
      path = document.createElementNS(ns, "line");
      path.setAttribute("x1", row.x1); path.setAttribute("y1", row.y1);
      path.setAttribute("x2", row.x2); path.setAttribute("y2", row.y2);
    } else if (asArray(row.points).length > 1) {
      path = document.createElementNS(ns, "polyline");
      path.setAttribute("points", asArray(row.points)
        .map((point) => `${Number(point?.[0])},${Number(point?.[1])}`).join(" "));
    }
    if (!path) continue;
    path.setAttribute("class", "causal-edge");
    path.dataset.state = stateOf(edge).toLowerCase();
    path.dataset.anchor = "causal-edge";
    svg.append(path);
    if (Number.isFinite(Number(row.label_x)) && Number.isFinite(Number(row.label_y))) {
      const label = document.createElementNS(ns, "text");
      label.setAttribute("class", "causal-edge-label");
      label.setAttribute("x", Number(row.label_x));
      label.setAttribute("y", Number(row.label_y));
      label.setAttribute("text-anchor", "middle");
      label.textContent = humanText(edge.relation ?? edge.label, "relation");
      svg.append(label);
    }
  }
  for (const { object, row } of placed) {
    const group = document.createElementNS(ns, "g");
    group.setAttribute("class", "causal-node");
    group.dataset.selected = String(rawHandle(object) === activeState.selection.focus);
    group.dataset.anchor = "causal-object";
    group.dataset.object = rawHandle(object);
    group.dataset.semanticObject = "";
    group.dataset.semanticHandle = rawHandle(object);
    group.setAttribute("role", "button");
    group.setAttribute("tabindex", "0");
    group.setAttribute("aria-label", `${labelOf(object)}. ${stateOf(object)}`);
    const rect = document.createElementNS(ns, "rect");
    rect.setAttribute("x", row.x); rect.setAttribute("y", row.y);
    rect.setAttribute("width", row.width ?? row.w); rect.setAttribute("height", row.height ?? row.h);
    const title = document.createElementNS(ns, "text");
    title.setAttribute("x", Number(row.x) + 12); title.setAttribute("y", Number(row.y) + 23);
    title.textContent = labelOf(object).slice(0, 46);
    const state = document.createElementNS(ns, "text");
    state.setAttribute("class", "node-state");
    state.setAttribute("x", Number(row.x) + 12); state.setAttribute("y", Number(row.y) + 42);
    state.textContent = stateOf(object).replaceAll("_", " ").slice(0, 30);
    group.append(rect, title, state);
    const activate = () => move(focusPatchFor(object));
    group.addEventListener("click", activate);
    group.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); activate(); }
    });
    svg.append(group);
  }
  holder.append(svg);
  const corridor = el("div", "narrow-causal-corridor");
  corridor.dataset.anchor = "programme-narrow-corridor";
  corridor.setAttribute("aria-label", "Programme causal corridor");
  const objectByHandle = new Map(objects.map((object) => [rawHandle(object), object]));
  objects.forEach((object, index) => {
    const station = el("div", "corridor-station");
    station.dataset.station = String(index + 1);
    const ordinal = el("span", "corridor-ordinal", String(index + 1).padStart(2, "0"));
    const button = objectButton(object);
    button.classList.add("corridor-object");
    station.append(ordinal, button);
    corridor.append(station);
  });
  if (edges.length) {
    const relations = el("div", "corridor-relations");
    relations.append(el("span", "coordination-kicker", "Exact relations crossing this view"));
    for (const edge of edges) {
      const source = objectByHandle.get(String(edge.source_handle));
      const target = objectByHandle.get(String(edge.target_handle));
      const control = el(
        "button",
        "corridor-relation",
        `${labelOf(source, "Source")} ${humanText(edge.relation, "relates to")} ${labelOf(target, "target")}`,
      );
      control.type = "button";
      control.dataset.semanticEdge = rawHandle(edge);
      control.dataset.anchor = "causal-edge";
      control.addEventListener("click", () => move({
        focus: rawHandle(target) || rawHandle(source),
        edge: rawHandle(edge) || null,
        grade: "near",
      }));
      relations.append(control);
    }
    corridor.append(relations);
  }
  holder.append(corridor);
  const index = el("nav", "programme-index");
  index.setAttribute("aria-label", "Programme objects");
  for (const object of objects) {
    const control = el("button", "", labelOf(object));
    control.type = "button";
    control.dataset.semanticObject = "";
    control.dataset.semanticHandle = rawHandle(object);
    control.dataset.object = rawHandle(object);
    control.dataset.selected = String(rawHandle(object) === activeState.selection.focus);
    control.addEventListener("click", () => move(focusPatchFor(object)));
    index.append(control);
  }
  if (activeState.selection.focus
      && !objects.some((object) => rawHandle(object) === activeState.selection.focus)) {
    const control = el("button", "", "Attended object");
    control.type = "button";
    control.dataset.semanticObject = "";
    control.dataset.semanticHandle = activeState.selection.focus;
    control.dataset.object = activeState.selection.focus;
    control.dataset.selected = "true";
    control.addEventListener("click", () => move({ focus: activeState.selection.focus }));
    index.prepend(control);
  }
  holder.append(index);
  return holder;
}

function capabilityObject(capability) {
  return {
    ...capability,
    handle: capability.semantic_anchor,
    human_label: capability.label,
    summary: `${humanText(capability.disposition)} · ${humanText(capability.reason)}`,
  };
}

function renderWalkJourney(organ) {
  const capabilities = asArray(organ.capabilities).filter((item) => item.disposition !== "RETIRE");
  const canvas = capabilities.find((item) => item.id === "content-canvas");
  const canvasEvidence = plain(canvas?.evidence);
  const counts = plain(canvasEvidence.counts);
  const journey = el("div", "manuscript-journey");
  journey.dataset.anchor = "manuscript-walk-journey";
  const paper = el("div", "manuscript-presence");
  paper.append(
    el("span", "coordination-kicker", "Living manuscript"),
    el("h4", "", humanText(canvasEvidence.title, "The selected manuscript")),
    el("p", "", [
      counts.sections === undefined ? null : `${counts.sections} sections`,
      counts.blocks === undefined ? null : `${counts.blocks} blocks`,
      counts.citations === undefined ? null : `${counts.citations} citations`,
      counts.refs === undefined ? null : `${counts.refs} references`,
    ].filter(Boolean).join(" · ") || "Exact manuscript counts unavailable"),
    el("p", "manuscript-fidelity", humanText(canvasEvidence.fidelity, "Content identity is preserved; typeset geometry is a separate face.")),
  );
  const route = el("div", "manuscript-route");
  capabilities.forEach((capability, index) => {
    const station = el("div", "manuscript-station");
    station.dataset.station = String(index + 1);
    station.append(el("span", "manuscript-station-number", String(index + 1).padStart(2, "0")));
    const control = objectButton(capabilityObject(capability));
    control.classList.add("manuscript-control");
    const omissions = asArray(capability.omissions);
    if (omissions.length) {
      control.append(el(
        "span",
        "manuscript-omission",
        `${omissions.reduce((total, item) => total + Number(item.count || 0), 0)} omitted · continuation held`,
      ));
    }
    station.append(control);
    route.append(station);
  });
  journey.append(paper, route);
  return journey;
}

function renderPipelineJourney(organ) {
  const capabilities = asArray(organ.capabilities).filter((item) => item.disposition !== "RETIRE");
  const briefCapability = capabilities.find((item) => item.id === "composed-brief");
  const chainCapability = capabilities.find((item) => item.id === "release-chain");
  const brief = plain(briefCapability?.evidence?.brief);
  const chain = plain(chainCapability?.evidence);
  const journey = el("div", "pipeline-journey");
  journey.dataset.anchor = "pipeline-release-journey";
  const account = el("div", "pipeline-account");
  account.append(
    el("span", "coordination-kicker", "Project trajectory"),
    el("h4", "", humanText(brief.glance, "The exact pipeline brief is unavailable.")),
    el("p", "", humanText(brief.next_line, "No next pipeline act is supplied.")),
  );
  const chainNode = el("div", "pipeline-chain");
  const states = asArray(chain.states);
  for (const state of states) {
    const rung = el("button", "pipeline-rung");
    rung.type = "button";
    rung.dataset.status = humanText(state.status, "unknown").toLowerCase();
    rung.append(
      el("span", "pipeline-rung-state", humanText(state.state, "Unknown").replaceAll("_", " ")),
      el("span", "pipeline-rung-act", humanText(state.next_action, "No next act supplied")),
    );
    rung.addEventListener("click", () => move(focusPatchFor(capabilityObject(chainCapability ?? briefCapability))));
    chainNode.append(rung);
  }
  const other = el("div", "pipeline-organs");
  for (const capability of capabilities.filter((item) =>
    !["composed-brief", "release-chain"].includes(item.id))) {
    other.append(objectButton(capabilityObject(capability)));
  }
  journey.append(account, states.length ? chainNode : notice(
    "Release chain unavailable",
    "No exact rung sequence was supplied; no synthetic process is shown.",
    "unknown",
  ), other);
  return journey;
}

function renderWork(payload) {
  const part = roomPayload(payload, "work");
  const wrapper = el("div", "work-quarry");
  wrapper.dataset.anchor = "work-quarry";
  const projects = asArray(part.projects);
  const selectedProject = humanText(part.selected_project, "");
  if (!selectedProject) {
    const intro = el("div", "work-intro");
    intro.append(
      el("h3", "", "Choose the work, not a substitute page"),
      el("p", "", "Each project opens its real manuscript Walk/editor and governed Pipeline mechanisms around one stable object identity."),
    );
    const shelf = el("div", "project-shelf");
    for (const project of projects) {
      const door = objectButton(project);
      door.dataset.project = project.project;
      door.addEventListener("click", (event) => {
        event.stopImmediatePropagation();
        store.set({ project: project.project, ...selectionPatch({ focus: null, edge: null }) });
      });
      shelf.append(door);
    }
    wrapper.append(intro, shelf);
    return wrapper;
  }
  const heading = el("header", "work-heading");
  const change = el("button", "organ-door", "Choose another project");
  change.type = "button";
  change.addEventListener("click", () => store.set({
    project: null,
    ...selectionPatch({ focus: null, edge: null }),
  }));
  if (gradeFromState(activeState) !== "far"
      && plain(part.workbench).schema_version === "laplace.aisthesis-manuscript-workbench/1") {
    const live = el("div", "manuscript-work-live");
    live.dataset.anchor = "manuscript-work-live";
    live.dataset.renderer = "manuscript-work-surface";
    change.classList.add("manuscript-work-project-return");
    wrapper.append(change, live);
    renderManuscriptWorkSurface(live, part, {
      selection: activeState.selection,
      move: (patch) => move(patch),
    });
    return wrapper;
  }
  const headingCopy = el("div");
  headingCopy.append(
    el("span", "coordination-kicker", "Work under custody"),
    el("h3", "", selectedProject),
  );
  heading.append(headingCopy, change);
  wrapper.append(heading);
  const journey = el("div", "work-journey");
  asArray(part.organs).forEach((organ, organIndex) => {
    const section = el("section", "work-organ");
    section.dataset.organ = humanText(organ.id, "work-organ");
    const stageMark = el("span", "work-stage-mark", String(organIndex + 1).padStart(2, "0"));
    const head = el("div", "work-organ-head");
    const headCopy = el("div");
    headCopy.append(
      el("h3", "", labelOf(organ)),
      el("p", "", sayOf(organ, "Exact producer mechanisms retained here.")),
    );
    head.append(headCopy, el("span", "object-state", humanText(organ.state, "UNKNOWN")));
    let sequence = null;
    if (organ.id === "walk") sequence = renderWalkJourney(organ);
    else if (organ.id === "pipeline") sequence = renderPipelineJourney(organ);
    else {
      sequence = el("div", "work-capability-sequence");
      for (const capability of asArray(organ.capabilities).filter((item) => item.disposition !== "RETIRE")) {
        sequence.append(objectButton(capabilityObject(capability)));
      }
    }
    section.append(stageMark, head, sequence);
    journey.append(section);
  });
  wrapper.append(journey);
  return wrapper;
}

function renderDecision(payload) {
  const decisions = modelObjects(payload, "decision");
  if (!decisions.length) return notice("No decision confidently waiting", "An empty or unavailable decision projection is not presented as a clear queue.", "unknown");
  const list = el("div", "decision-cut");
  list.dataset.anchor = "decision-list";
  decisions.forEach((decision, index) => {
    const row = el("button", "decision-line");
    row.type = "button";
    row.dataset.object = rawHandle(decision);
    row.dataset.semanticObject = "";
    row.dataset.semanticHandle = rawHandle(decision);
    row.dataset.anchor = "decision-object";
    row.style.setProperty("--decision-index", String(index));
    const copy = el("div");
    copy.append(el("h3", "", labelOf(decision)), el("p", "", sayOf(decision, "Open the exact grounds before ruling.")));
    row.append(copy, el("span", "decision-state", humanText(stateOf(decision).replaceAll("_", " "))));
    row.addEventListener("click", () => move({ focus: rawHandle(decision), edge: null, grade: "near" }));
    list.append(row);
  });
  return list;
}

function renderRun(payload) {
  const events = modelObjects(payload, "run");
  if (!events.length) return notice("No exact run sequence", "Run evidence was unavailable or omitted; no synthetic activity is shown.", "unknown");
  const timeline = el("div", "timeline");
  timeline.dataset.anchor = "run-timeline";
  for (const event of events) {
    const moment = el("button", "moment");
    moment.type = "button";
    moment.dataset.object = rawHandle(event);
    moment.dataset.semanticObject = "";
    moment.dataset.semanticHandle = rawHandle(event);
    moment.dataset.anchor = "run-event";
    moment.append(el("h3", "", labelOf(event)), el("p", "", sayOf(event, stateOf(event).replaceAll("_", " "))));
    moment.addEventListener("click", () => move({ focus: rawHandle(event), edge: null }));
    timeline.append(moment);
  }
  return timeline;
}

function renderFabricObservatory(payload) {
  const fabric = plain(carrierModel(payload).fabric_observatory ?? payload?.fabric_observatory);
  const organ = el("section", "organ");
  organ.dataset.organ = "fabric-observatory";
  organ.dataset.anchor = "fabric-observatory";
  const canonical = plain(fabric.canonical);
  const head = el("div", "organ-head");
  const copy = el("div");
  copy.append(
    el("h3", "", "Coordination and delivery"),
    el("p", "", "Canonical delivery, watcher attention and direct fallback remain separate kinds of evidence."),
  );
  const state = el("span", "observatory-state", humanText(canonical.state, "UNKNOWN"));
  head.append(copy, state);
  organ.append(head);

  const lanes = el("div", "fabric-lanes");
  lanes.dataset.anchor = "fabric-lanes";
  const canonicalLane = el("section", "fabric-lane fabric-canonical-flow");
  canonicalLane.dataset.fabricLane = "canonical";
  canonicalLane.append(el("h4", "", "Canonical delivery"));
  const phases = asArray(canonical.phases);
  const phaseList = el("div", "braid");
  for (const item of phases) {
    const phase = el("div", "phase");
    phase.dataset.state = humanText(item.state, "UNKNOWN").toLowerCase();
    phase.append(el("span", "phase-name", humanText(item.phase, "phase")));
    phase.append(el("span", "phase-thread"));
    const phaseCopy = el("span", "phase-copy");
    phaseCopy.append(
      el("h3", "", humanText(item.state, "UNKNOWN")),
      el("p", "", item.latency_ms == null ? "Latency UNKNOWN" : `${item.latency_ms} ms`),
    );
    phase.append(phaseCopy);
    phaseList.append(phase);
  }
  canonicalLane.append(phaseList || notice("Canonical receipts unavailable", "UNKNOWN", "unknown"));

  const watcher = plain(fabric.watcher_attention);
  const watcherLane = el("aside", "fabric-lane fabric-subordinate");
  watcherLane.dataset.fabricLane = "watcher";
  watcherLane.append(
    el("h4", "", "Watcher attention"),
    el("p", "", `${humanText(watcher.state, "UNKNOWN")} · attention only · NO DELIVERY CLAIM`),
    el("p", "", `Implementation ${humanText(watcher.implementation_state, "UNKNOWN")}`),
  );

  const fallback = plain(fabric.external_direct_fallback);
  const fallbackLane = el("aside", "fabric-lane fabric-subordinate");
  fallbackLane.dataset.fabricLane = "fallback";
  fallbackLane.append(
    el("h4", "", "External direct coordination"),
    el("p", "", `${humanText(fallback.state, "UNKNOWN")} · NO FABRIC DELIVERY OR ACKNOWLEDGEMENT CLAIM`),
    el("p", "", fallback.message_ref && fallback.body_digest
      ? "Task, message and body provenance are exact."
      : "Task is known; canonical message/body provenance remains UNKNOWN."),
    el("p", "", `Provenance ${humanText(fallback.provenance_state, "UNKNOWN")}`),
    el("p", "", `${humanText(fallback.transport, "External task transport")} · ${humanText(fallback.message_count, "message count UNKNOWN")}`),
    el("p", "", `Retires when ${humanText(fallback.retirement_predicate, "the first exact canonical round trip is visible")}.`),
  );
  lanes.append(canonicalLane, watcherLane, fallbackLane);
  organ.append(lanes);

  const counts = plain(fabric.counts);
  const metrics = el("div", "diagnostic-meta");
  for (const [key, label] of [
    ["batch", "batches"], ["process", "processes"], ["replay", "replays"],
    ["consumed", "consumed"], ["inert", "inert after compaction"],
  ]) metrics.append(el("span", "", `${countValue(counts[key])} ${label}`));
  metrics.append(el("span", "", `event delta ${countValue(canonical.event_delta)}`));
  metrics.append(el("span", "", `queue ${countValue(canonical.queue)}`));
  metrics.append(el("span", "", `backpressure ${countValue(canonical.backpressure)}`));
  metrics.append(el("span", "", humanText(canonical.binding_summary, "seat binding UNKNOWN")));
  organ.append(metrics);
  const loss = plain(fabric.loss_budget);
  const boundary = el("div", "fabric-loss-boundary");
  boundary.dataset.anchor = "fabric-loss-budget";
  boundary.append(
    el("p", "", `Recoverable: ${asArray(loss.recoverable).map((item) => humanText(item)).join(" · ") || "UNKNOWN"}`),
    el("p", "", `Never accepted: ${asArray(loss.forbidden).map((item) => humanText(item)).join(" · ") || "UNKNOWN"}`),
  );
  const fix = plain(fabric.fix_forward);
  boundary.append(el("p", "", `Fix-forward ${humanText(fix.state, "UNKNOWN")} · ${humanText(fix.next, "checkpoint → act → observe → traceback → bounded fix-forward")}`));
  organ.append(boundary);
  return organ;
}

function renderConversation(payload) {
  const phases = modelObjects(payload, "conversation");
  const wrapper = el("div");
  if (!phases.length) {
    wrapper.append(notice("Conversation evidence unavailable", "No turn-to-reply chain was supplied. Attention is not treated as delivery.", "unknown"));
    wrapper.append(renderFabricObservatory(payload));
    return wrapper;
  }
  const braid = el("div", "braid");
  braid.dataset.anchor = "conversation-braid";
  for (const phaseObject of phases) {
    const phase = el("button", "phase");
    phase.type = "button";
    phase.dataset.state = stateOf(phaseObject).toLowerCase();
    phase.dataset.object = rawHandle(phaseObject);
    phase.dataset.semanticObject = "";
    phase.dataset.semanticHandle = rawHandle(phaseObject);
    phase.dataset.anchor = "conversation-phase";
    phase.style.border = "0";
    phase.style.background = "transparent";
    phase.style.color = "inherit";
    phase.style.textAlign = "left";
    phase.style.cursor = "pointer";
    phase.append(el("span", "phase-name", humanText(phaseObject.phase ?? phaseObject.kind ?? stateOf(phaseObject))));
    phase.append(el("span", "phase-thread"));
    const copy = el("span", "phase-copy");
    copy.append(el("h3", "", labelOf(phaseObject)), el("p", "", sayOf(phaseObject, stateOf(phaseObject).replaceAll("_", " "))));
    phase.append(copy);
    phase.addEventListener("click", () => move({ focus: rawHandle(phaseObject), edge: null }));
    braid.append(phase);
  }
  wrapper.append(braid, renderFabricObservatory(payload));
  return wrapper;
}

function expositionSections(payload, focus) {
  const part = roomPayload(payload, "exposition");
  const source = plain(part.object ?? focus ?? payload?.focused_object);
  const sections = [
    ["Purpose", source.purpose ?? source.why ?? part.purpose],
    ["Present state", source.present_state ?? source.state_explanation ?? part.present_state],
    ["Inputs and consequences", source.causality ?? source.inputs_outputs ?? part.causality],
    ["Refusal conditions", source.invariants ?? source.refusal_conditions ?? part.invariants],
    ["Mechanism", source.mechanism ?? part.mechanism],
    ["Mathematics", source.mathematics ?? source.math ?? part.mathematics],
    ["Evidence and residuals", source.evidence_summary ?? source.residual_summary ?? part.evidence],
    ["Safe specimen", source.specimen ?? part.specimen],
  ];
  const gradeIndex = Number(expositionFromState(activeState).slice(1));
  return sections.slice(0, Math.max(1, Math.min(8, gradeIndex + 1)));
}

function renderSemanticMemory(payload) {
  const memory = plain(carrierModel(payload).semantic_memory ?? payload?.semantic_memory);
  const baseline = plain(memory.baseline);
  const organ = el("section", "organ");
  organ.dataset.organ = "semantic-memory";
  organ.dataset.anchor = "semantic-memory";
  const head = el("div", "organ-head");
  const copy = el("div");
  const state = humanText(baseline.status ?? memory.display_state ?? memory.operational_state
    ?? memory.state ?? "UNKNOWN").replaceAll("_", " ");
  copy.append(
    el("h3", "", "Semantic Memory"),
    el("p", "", `${state} · source-to-meaning coverage and the exact gaps that remain.`),
  );
  const expositionGrade = Number(expositionFromState(activeState).slice(1));
  const expanded = gradeFromState(activeState) === "near"
    || gradeFromState(activeState) === "audit" || expositionGrade >= 3;
  const door = el("button", "organ-door", expanded ? "Close memory descent" : "Descend into memory");
  door.type = "button";
  door.dataset.memoryExpand = "";
  door.setAttribute("aria-expanded", String(expanded));
  head.append(copy, door);
  organ.append(head);

  const detail = el("div", "memory-detail");
  detail.dataset.memoryDetail = "";
  detail.hidden = !expanded;
  const measures = el("div", "memory-measures");
  const coverage = plain(memory.coverage);
  const runtime = plain(memory.runtime);
  const vectors = plain(baseline.vectors);
  const hello = plain(baseline.semantic_hello);
  const rows = [
    ["Baseline", state],
    ["Nodes", baseline.nodes ?? coverage.node?.count ?? coverage.node_count ?? "UNKNOWN"],
    ["Embedded", vectors.embedded ?? vectors.embedded_count ?? "UNKNOWN"],
    ["Content-identical cache", vectors.content_identical_cached ?? vectors.cached ?? "UNKNOWN"],
    ["Deferred", vectors.deferred ?? "UNKNOWN"],
    ["Pruned", vectors.pruned ?? "UNKNOWN"],
    ["Vector total", vectors.total ?? coverage.vector?.count ?? coverage.vector_count ?? "UNKNOWN"],
    ["Duration", baseline.duration_seconds === null || baseline.duration_seconds === undefined
      ? "UNKNOWN" : `${baseline.duration_seconds}s`],
    ["Compute", baseline.gpu ?? runtime.device ?? runtime.backend ?? "UNKNOWN"],
    ["Metric", baseline.metric_redistilled === true ? "redistilled" : baseline.metric_redistilled ?? "UNKNOWN"],
    ["Semantic hello", hello.passed !== undefined
      ? `${hello.passed}/${hello.total ?? hello.passed} PASS`
      : baseline.semantic_hello ?? "UNKNOWN"],
    ["Operational health", `${humanText(memory.health_status, "UNKNOWN")} · ${humanText(memory.state, "UNKNOWN")}`],
  ];
  for (const [label, value] of rows) {
    const fact = el("div", "memory-measure");
    fact.append(el("b", "", label), el("span", "", humanText(value, "UNKNOWN")));
    measures.append(fact);
  }
  detail.append(measures);

  const classes = asArray(memory.source_classes);
  if (classes.length) {
    const list = el("div", "focus-links");
    for (const item of classes) {
      const row = el("span", "focus-link", `${labelOf(item, humanText(item.source_class, "Source"))}: ${humanText(item.status, "UNKNOWN")}`);
      row.dataset.memorySourceClass = "";
      row.dataset.state = humanText(item.status, "UNKNOWN").toUpperCase();
      list.append(row);
    }
    detail.append(list);
  }

  const specimen = el("button", "organ-door memory-specimen", "Show missing-dependency specimen");
  specimen.type = "button";
  specimen.dataset.memorySpecimen = "missing-dependency";
  const missing = el("p", "notice", "UNKNOWN · This safe specimen has no admitted source dependency, so no explanatory claim is made.");
  missing.dataset.memoryDependency = "";
  missing.dataset.state = "UNKNOWN";
  missing.hidden = expositionGrade < 7;
  specimen.addEventListener("click", () => move({
    lens: "exposition",
    grade: "audit",
    exposition: "E7",
    edge: null,
  }));
  detail.append(specimen, missing);
  door.addEventListener("click", () => move({
    lens: "exposition",
    grade: expanded ? "mid" : "near",
    exposition: expanded ? "E0" : "E3",
    edge: null,
  }));
  organ.append(detail);
  return organ;
}

function observatoryField(name, label, value, state = null) {
  const node = el("div", "observatory-field");
  node.dataset.observatoryField = name;
  const exactState = humanText(state ?? (value === null || value === undefined ? "UNKNOWN" : "CURRENT")).toUpperCase();
  node.dataset.state = exactState;
  const words = value === null || value === undefined
    ? "UNKNOWN · no exact observation supplied"
    : humanText(value, "UNKNOWN");
  node.append(el("b", "", label), el("span", "", exactState === "UNKNOWN" && !/UNKNOWN/i.test(words)
    ? `UNKNOWN · ${words}` : words));
  return node;
}

function renderObservatoryDetail(observatory, kind) {
  const detail = el("div", "observatory-detail");
  detail.dataset.observatoryDetail = "";
  detail.dataset.subjectKind = kind;
  detail.hidden = true;
  const selected = plain(observatory.selected);
  const fields = el("div", "observatory-fields");
  const complete = descentComplete(observatory);
  const routed = asArray(observatory.routed_handles);
  const regions = plain(observatory.regions);
  const budget = plain(observatory.budget);
  const fog = asArray(observatory.fog);
  const descent = plain(observatory.last_enforced_descent);
  const subject = selected[kind];
  fields.append(
    observatoryField("routed", "Routed", routed.length ? `${routed.length} exact ${routed.length === 1 ? "route" : "routes"}` : null),
    observatoryField("reached", "Reached", Array.isArray(regions.reached) ? `${regions.reached.length} regions` : null),
    observatoryField("admitted", "Admitted", Array.isArray(regions.admitted) ? `${regions.admitted.length} regions` : null),
    observatoryField("rejected", "Rejected", Array.isArray(regions.rejected) ? `${regions.rejected.length} regions` : null),
    observatoryField("unvisited", "Unvisited", Array.isArray(regions.unvisited) ? `${regions.unvisited.length} regions` : null),
    observatoryField("depth", "Depth", observatory.depth),
    observatoryField("budget", "Budget", Object.keys(budget).length
      ? Object.entries(budget).map(([key, value]) => `${value} ${key}`).join(" · ") : null),
    observatoryField("fog", "Typed fog", fog.length
      ? fog.map((row) => `${humanText(row.class, "UNKNOWN")}: ${countValue(row.count)}`).join(" · ") : null),
    observatoryField("currentness", "Injected context", observatory.injected_context_currentness,
      observatory.injected_context_currentness),
  );
  const descentField = observatoryField(
    "descent",
    "Enforced descent",
    complete ? `SUCCEEDED · ${humanText(descent.time, "observed time unavailable")}` : "ROUTING-ONLY / UNKNOWN",
    complete ? "SUCCEEDED" : "UNKNOWN",
  );
  if (complete) {
    descentField.dataset.descendedReceipt = "";
    descentField.dataset.state = "SUCCEEDED";
  }
  fields.append(descentField);
  detail.append(el("p", "focus-purpose", `${kind} · ${humanText(subject, "UNKNOWN")}`), fields);
  return detail;
}

function renderReconstructionObservatory(payload) {
  const observatory = plain(carrierModel(payload).binding_observatory
    ?? payload?.binding_observatory ?? payload?.reconstruction_observatory);
  const organ = el("section", "organ");
  organ.dataset.organ = "reconstruction-observatory";
  organ.dataset.anchor = "reconstruction-observatory";
  const head = el("div", "organ-head");
  const copy = el("div");
  copy.append(
    el("h3", "", "Reconstruction Observatory"),
    el("p", "", descentComplete(observatory)
      ? "One enforced descent is receipted; inspect its admitted and omitted field."
      : "ROUTING-ONLY / UNKNOWN · no successful descended context is claimed."),
  );
  head.append(copy);
  organ.append(head);
  const controls = el("div", "observatory-subjects");
  for (const kind of ["seat", "turn", "task"]) {
    const button = el("button", "subject-door", `Inspect ${kind}`);
    button.type = "button";
    button.dataset.observatorySubject = kind;
    const detail = renderObservatoryDetail(observatory, kind);
    const subjectFocus = `reconstruction-observatory:${kind}`;
    const selected = activeState.selection.focus === subjectFocus;
    button.setAttribute("aria-expanded", String(selected));
    detail.hidden = !selected;
    button.addEventListener("click", () => move({
      focus: subjectFocus,
      edge: null,
      grade: selected ? "mid" : "near",
    }));
    controls.append(button);
    organ.append(detail);
  }
  organ.prepend(head, controls);
  return organ;
}

function renderExposition(payload) {
  const focus = selectedObject(payload, activeState);
  if (!rawHandle(focus) && !labelOf(focus, "")) {
    return notice("Choose an object first", "Exposition grows around the attended object; it is not a detached help page.", "unknown");
  }
  const wrapper = el("div", "exposition");
  wrapper.dataset.anchor = "exposition-path";
  wrapper.append(renderSemanticMemory(payload));
  for (const [title, value] of expositionSections(payload, focus)) {
    const section = el("section");
    section.dataset.anchor = `exposition-${title.toLowerCase().replaceAll(" ", "-")}`;
    section.append(el("h3", "", title), el("p", "", humanText(value, "No source-bearing account was supplied at this grade.")));
    wrapper.append(section);
  }
  const observatoryData = plain(
    focus?.reconstruction_observatory ?? roomPayload(payload, "exposition").reconstruction_observatory
    ?? payload?.reconstruction_observatory,
  );
  const observatory = el("div", "observatory");
  observatory.dataset.anchor = "reconstruction-observatory";
  const head = el("div", "observatory-head");
  head.append(
    el("span", "observatory-title", "Reconstruction Observatory"),
    el("span", "observatory-state", humanText(stateOf(observatoryData).replaceAll("_", " "))),
  );
  observatory.append(head, el("p", "", sayOf(
    observatoryData,
    "No goal-conditioned reconstruction specimen is attached to this object.",
  )));
  wrapper.append(observatory);
  return wrapper;
}

function renderDiagnostics(payload) {
  const diagnostics = modelObjects(payload, "diagnostics");
  const failures = asArray(payload?.endpoint_failures).map((error, index) => ({
    id: `endpoint-failure-${index}`,
    label: "Endpoint refused",
    summary: error,
    status: "REFUSED",
  }));
  const items = diagnostics.concat(failures);
  const wrapper = el("div");
  wrapper.append(renderReconstructionObservatory(payload));
  if (!items.length) {
    wrapper.append(notice("No additional diagnostic projection", "Absence is not a clean bill of health.", "unknown"));
    return wrapper;
  }
  const strata = [
    { id: "broken", label: "Broken trust", copy: "Refusal and corruption boundaries", tones: new Set(["bad"]) },
    { id: "unsettled", label: "Unsettled", copy: "Stale, omitted or incomplete evidence", tones: new Set(["warn"]) },
    { id: "fog", label: "Unknown field", copy: "Absence remains visible and descendable", tones: new Set(["unknown"]) },
    { id: "ground", label: "Trusted ground", copy: "Current evidence supporting this face", tones: new Set(["ok"]) },
  ];
  const field = el("div", "trust-field");
  field.dataset.anchor = "diagnostic-trust-field";
  for (const stratum of strata) {
    const admitted = items.filter((item) => stratum.tones.has(stateTone(stateOf(item))));
    if (!admitted.length) continue;
    const layer = el("section", "trust-stratum");
    layer.dataset.stratum = stratum.id;
    const label = el("div", "trust-stratum-label");
    label.append(
      el("h3", "", stratum.label),
      el("p", "", `${admitted.length} ${admitted.length === 1 ? "object" : "objects"} · ${stratum.copy}`),
    );
    const grid = el("div", "diagnostic-grid");
    for (const item of admitted) {
      const box = el("button", "diagnostic");
      box.type = "button";
      box.dataset.object = rawHandle(item);
      box.dataset.semanticObject = "";
      box.dataset.semanticHandle = rawHandle(item);
      box.dataset.anchor = "diagnostic-object";
      const state = stateOf(item);
      box.append(el("h3", "", labelOf(item)), el("p", "", sayOf(item, state.replaceAll("_", " "))));
      const meta = el("span", "diagnostic-meta");
      meta.append(el("span", "", humanText(state.replaceAll("_", " "))));
      for (const chip of asArray(item.chips).slice(0, 3)) {
        meta.append(el("span", "", `${countValue(chip.n)} ${humanText(chip.unit)}`));
      }
      box.append(meta);
      box.addEventListener("click", () => move(focusPatchFor(item)));
      grid.append(box);
    }
    layer.append(label, grid);
    field.append(layer);
  }
  wrapper.append(field);
  return wrapper;
}

function foreground(payload, room) {
  const renderer = {
    now: renderNow,
    programme: renderProgramme,
    work: renderWork,
    decision: renderDecision,
    run: renderRun,
    conversation: renderConversation,
    exposition: renderExposition,
    diagnostics: renderDiagnostics,
  }[room];
  return renderer(payload);
}

function focusEvidence(object) {
  return firstUseful(
    object?.evidence_edges, object?.evidence, object?.sources, object?.relations,
    object?.edges, object?.continuations,
  );
}

function bindingObservatory(payload, object) {
  const handle = rawHandle(object);
  const carrier = carrierModel(payload);
  const global = plain(carrier.binding_observatory ?? payload?.binding_observatory
    ?? payload?.reconstruction_observatory);
  const indexed = plain(global.by_focus ?? global.by_object ?? global.bindings);
  return plain(
    object?.binding_observatory ?? object?.descent_observatory
    ?? object?.reconstruction_observatory ?? indexed[handle] ?? global.current ?? global,
  );
}

function descentComplete(observatory) {
  const receipt = plain(observatory.last_enforced_descent ?? observatory.descent_receipt
    ?? observatory.receipt ?? observatory.last_descent);
  const receiptState = stateOf(receipt, stateOf(observatory));
  const injected = stateOf({ state: observatory.injected_context_currentness
    ?? observatory.context_currentness ?? receipt.injected_context_currentness });
  return Boolean(rawHandle(receipt) || receipt.receipt || receipt.receipt_handle
      || receipt.observed_at || receipt.time)
    && /DESCENDED|COMPLETE|CURRENT|SUCCESS|ACCEPT/.test(receiptState)
    && /CURRENT|COMPLETE/.test(injected);
}

function regionCount(observatory, key) {
  const regions = plain(observatory.regions ?? observatory.descent_regions);
  const value = observatory[key] ?? regions[key];
  if (Array.isArray(value)) return value.length;
  if (value && typeof value === "object") return Object.keys(value).length;
  return value ?? "Unknown";
}

function renderBindingObservatory(payload, object) {
  const observatory = bindingObservatory(payload, object);
  if (!Object.keys(observatory).length) return null;
  const complete = descentComplete(observatory);
  const box = el("section", "binding-observatory");
  box.dataset.anchor = "binding-observatory";
  box.dataset.state = complete ? "complete" : "unknown";
  const head = el("div", "binding-head");
  head.append(
    el("h3", "", "Binding Observatory"),
    el("span", "binding-verdict", complete ? "Descended context current" : "ROUTING-ONLY / UNKNOWN"),
  );
  box.append(head);

  const routed = asArray(observatory.routed_handles ?? observatory.route ?? observatory.routing);
  const source = labelOf(observatory.source ?? observatory.source_region, "Source");
  const fibre = labelOf(observatory.fibre ?? observatory.assumption_fibre, "Fibre not supplied");
  const routeText = routed.length
    ? `${source} → ${fibre} · ${routed.length} routed ${routed.length === 1 ? "handle" : "handles"}`
    : `${source} → ${fibre} · no routed handle count supplied`;
  box.append(el("p", "binding-route", routeText));

  const measures = el("div", "binding-measures");
  const depth = observatory.depth ?? observatory.max_depth ?? observatory.descent_depth;
  const budget = observatory.budget ?? observatory.content_budget ?? observatory.byte_budget;
  const facts = [
    [regionCount(observatory, "reached"), "regions reached"],
    [regionCount(observatory, "admitted"), "admitted"],
    [regionCount(observatory, "rejected"), "rejected"],
    [regionCount(observatory, "unvisited"), "unvisited"],
    [depth ?? "Unknown", "descent depth"],
    [budget ?? "Unknown", "declared budget"],
  ];
  for (const [value, label] of facts) {
    const fact = el("div", "binding-measure");
    fact.append(el("b", "", countValue(value)), el("span", "", label));
    measures.append(fact);
  }
  box.append(measures);

  const fog = asArray(observatory.fog ?? observatory.fog_regions ?? observatory.residuals);
  if (fog.length) {
    const fogList = el("div", "fog-list");
    fogList.dataset.anchor = "typed-semantic-fog";
    for (const item of fog.slice(0, 6)) {
      const row = el("div", "fog-item");
      row.append(
        el("span", "fog-kind", humanText(item.kind ?? item.class ?? item.cause, "UNKNOWN")),
        el("span", "", sayOf(item, `${countValue(item.count)} affected`)),
      );
      fogList.append(row);
    }
    box.append(fogList);
  }

  const receipt = plain(observatory.last_enforced_descent ?? observatory.descent_receipt
    ?? observatory.receipt ?? observatory.last_descent);
  const lastAt = receipt.observed_at ?? receipt.at ?? receipt.time ?? observatory.last_descent_time;
  const currentness = observatory.injected_context_currentness
    ?? observatory.context_currentness ?? receipt.injected_context_currentness ?? "UNKNOWN";
  const foot = el("p", "focus-purpose", `Last descended ${humanText(lastAt, "time unknown")} · injected context ${humanText(currentness).toUpperCase()}`);
  box.append(foot);
  return box;
}

function renderContext(payload) {
  const object = selectedObject(payload, activeState);
  const handle = rawHandle(object);
  els.back.hidden = !activeState.selection.focus;
  els.context.replaceChildren();
  if (!activeState.selection.focus && !handle) {
    els.context.append(el("p", "focus-empty", "Choose an object to expand its purpose, consequences, evidence and next descent without leaving the room."));
    return;
  }
  els.context.append(el("h3", "focus-title", labelOf(object, "Selected object")));
  els.context.append(el("p", "focus-purpose", sayOf(object, "No human account was supplied for this object.")));

  const consequences = humanText(object?.consequence ?? object?.next_act ?? object?.inspect_next, "");
  if (consequences) {
    const section = el("section", "focus-section");
    section.dataset.anchor = "focus-consequence";
    section.append(el("h3", "", "Consequence"), el("p", "", consequences));
    els.context.append(section);
  }

  const evidence = focusEvidence(object);
  const evidenceSection = el("section", "focus-section");
  evidenceSection.dataset.anchor = "focus-descent";
  evidenceSection.append(el("h3", "", "Next descent"));
  if (!evidence.length) {
    evidenceSection.append(el("p", "", "No evidence continuation was supplied."));
  } else {
    const links = el("div", "focus-links");
    for (const item of evidence.slice(0, 6)) {
      const button = el("button", "focus-link", labelOf(item, "Evidence"));
      button.type = "button";
      button.addEventListener("click", () => move({
        focus: rawHandle(item) || handle,
        edge: rawHandle(item) || null,
        grade: "near",
      }));
      links.append(button);
    }
    evidenceSection.append(links);
  }
  els.context.append(evidenceSection);

  const observatory = renderBindingObservatory(payload, object);
  if (observatory) els.context.append(observatory);

  const memory = plain(object?.semantic_memory ?? object?.memory ?? object?.reconstruction);
  if (Object.keys(memory).length) {
    const section = el("section", "focus-section");
    section.dataset.anchor = "semantic-memory";
    section.append(
      el("h3", "", "Semantic memory"),
      el("p", "", sayOf(memory, "A source-bearing memory face is attached.")),
    );
    const open = el("button", "focus-link", "Understand this object");
    open.type = "button";
    open.addEventListener("click", () => move({ lens: "exposition", focus: handle, grade: "near", exposition: "E3", edge: null }));
    section.append(open);
    els.context.append(section);
  }

  if (gradeFromState(activeState) === "audit") {
    const well = el("dl", "audit-well");
    well.dataset.anchor = "selected-audit-well";
    well.dataset.auditWell = "";
    well.dataset.selected = "true";
    const carrier = carrierModel(payload);
    const exact = [
      ["Selected object", handle],
      ["Selected edge", activeState.selection.edge],
      ["Model", carrier.model_handle ?? payload?.development?.model_handle],
      ["Shown state", carrier.shown_state?.shown_handle ?? payload?.shown_handle
        ?? payload?.development?.shown_state?.shown_handle],
      ["Layout receipt", carrier.layout_receipt_handle
        ?? carrier.shown_state?.layout_receipt_handle
        ?? payload?.development?.shown_state?.layout_receipt_handle],
    ];
    for (const [name, value] of exact) {
      if (!value) continue;
      well.append(el("dt", "", name), el("dd", "", String(value)));
    }
    els.context.append(well);
  }
}

function restoreContextHome() {
  if (!els.contextHome || !els.contextShell) return;
  if (els.contextShell.parentElement !== els.contextHome) els.contextHome.append(els.contextShell);
  els.contextShell.dataset.dock = "home";
}

function dockContext(room) {
  if (!els.contextShell || !els.contextHome) return;
  restoreContextHome();
  if (!activeState.selection.focus || gradeFromState(activeState) === "far") return;
  if (room === "exposition") return;
  const candidates = [...els.field.querySelectorAll("[data-object]")]
    .filter((node) => node instanceof HTMLElement && node.getClientRects().length > 0);
  const target = candidates.find((node) => node.dataset.object === activeState.selection.focus);
  if (!target) return;
  const host = target.closest(
    ".manuscript-station, .corridor-station, .phase, .moment, .decision-line, .diagnostic",
  ) ?? target;
  if (host.closest(".programme-index")) host.closest(".programme-index").after(els.contextShell);
  else host.after(els.contextShell);
  els.contextShell.dataset.dock = "inline";
  els.contextShell.dataset.attentionRoom = room;
}

function updateOrientation(payload) {
  const room = ROOMS.find((item) => item.id === roomFromState(activeState)) || ROOMS[0];
  const focus = selectedObject(payload, activeState);
  const carrier = carrierModel(payload);
  const active = roomFace(payload, room.id);
  const shown = plain(carrier.shown_state);
  const omissions = asArray(active?.omissions).concat(asArray(carrier.selection_omissions));
  const breakText = humanText(
    focus?.causal_break ?? focus?.blocking_reason ?? omissions[0]?.reason
      ?? (stateOf(active) === "CURRENT" ? "No active break supplied" : `${stateOf(active)} evidence boundary`),
    "Evidence boundary unknown",
  );
  const predecessor = focus?.predecessor ?? focus?.before ?? focus?.upstream?.[0];
  const successor = focus?.successor ?? focus?.after ?? focus?.downstream?.[0] ?? focus?.next_act;
  els.roomKicker.textContent = room.name;
  els.roomTitle.textContent = room.title;
  els.roomPurpose.textContent = room.purpose;
  els.orientationTitle.textContent = activeState.selection.focus ? labelOf(focus, room.title) : room.title;
  els.orientationPurpose.textContent = activeState.selection.focus
    ? sayOf(focus, room.purpose) : room.purpose;
  els.orientationFocus.textContent = labelOf(focus, room.title);
  els.orientationBreak.textContent = breakText;
  els.orientationPredecessor.textContent = labelOf(predecessor, "Unknown predecessor");
  els.orientationSuccessor.textContent = labelOf(successor, "Unknown successor");
  els.orientationOmitted.textContent = shown.omitted_handles?.length || omissions.length
    ? `${shown.omitted_handles?.length ?? omissions.length} typed omissions held nearby`
    : "No omitted context declared";
  document.title = `Eigen · ${room.name}`;
  for (const button of document.querySelectorAll("[data-grade]")) {
    button.setAttribute("aria-pressed", String(button.dataset.grade === gradeFromState(activeState)));
  }
  modelStatus(payload);
}

const RENDERER = {
  now: ["priority-brief", "attention-frontier"],
  programme: ["layered-causal-field", "producer-geometry"],
  work: ["manuscript-workbench", "source-bearing-work-field"],
  decision: ["decision-cut", "consequence-first"],
  run: ["temporal-run", "receipt-sequence"],
  conversation: ["causal-braid", "turn-to-reply"],
  exposition: ["progressive-exposition", "object-relative-grades"],
  diagnostics: ["trust-observatory", "typed-refusal-field"],
};

function bindCarrierReceipt(payload, room) {
  const carrier = carrierModel(payload);
  const shown = plain(carrier.shown_state);
  const [renderer, composition] = RENDERER[room];
  const mode = humanText(shown.viewport, viewportClass()).toLowerCase();
  els.carrier.dataset.ready = "true";
  els.carrier.dataset.room = room;
  els.carrier.dataset.focusHandle = activeState.selection.focus || shown.focus || "";
  els.carrier.dataset.selectedEdge = activeState.selection.edge || shown.selected_edge || "";
  els.carrier.dataset.grade = GRADE_LABEL[gradeFromState(activeState)];
  els.carrier.dataset.exposition = expositionFromState(activeState);
  els.carrier.dataset.viewport = humanText(shown.viewport, viewportClass()).toLowerCase();
  els.carrier.dataset.modelHandle = carrier.model_handle ?? "";
  els.carrier.dataset.shownHandle = shown.shown_handle ?? payload?.shown_handle ?? "";
  els.carrier.dataset.omittedDigest = shown.omitted_digest ?? "";
  els.carrier.dataset.layoutReceipt = shown.layout_receipt_handle
    ?? carrier.layout_receipt_handle ?? shown.shown_handle ?? "";
  els.carrier.dataset.layoutMode = ["wide", "medium", "narrow"].includes(mode)
    ? mode : viewportClass();
  els.carrier.dataset.motion = "receipt-driven";
  els.roomField.dataset.room = room;
  els.roomField.dataset.foreground = "true";
  els.roomField.dataset.renderer = renderer;
  els.roomField.dataset.composition = composition;
  els.roomField.dataset.spatialField = "";
  els.roomField.dataset.layoutAxis = els.carrier.dataset.layoutMode === "narrow" ? "vertical" : "layered";
}

function feedbackContext() {
  const carrier = carrierModel(model || {});
  const shown = plain(carrier.shown_state);
  const memory = plain(carrier.semantic_memory);
  const source = {
    active_room_handle: plain(carrier.active_room).room_handle ?? null,
    semantic_memory_handle: memory.semantic_memory_handle ?? null,
    S: memory.S ?? null,
    F: memory.F ?? null,
    active_source: memory.active_source ?? null,
    semantic_ref: memory.semantic_ref ?? null,
    source_currentness: plain(memory.source_currentness),
  };
  return {
    model_handle: carrier.model_handle ?? els.carrier.dataset.modelHandle,
    shown_handle: shown.shown_handle ?? els.carrier.dataset.shownHandle,
    selection: {
      lens: roomFromState(activeState),
      focus: activeState.selection.focus || null,
      edge: activeState.selection.edge || null,
      grade: GRADE_LABEL[gradeFromState(activeState)],
      exposition: expositionFromState(activeState),
      viewport: els.carrier.dataset.layoutMode || viewportClass(),
    },
    source,
    currentness: {
      status: els.carrier.dataset.currentness || "UNKNOWN",
      semantic_memory_state: memory.state ?? "UNKNOWN",
      source_tuple_status: memory.source_tuple_status ?? "UNKNOWN",
    },
  };
}

async function render(state) {
  activeState = state;
  els.carrier.dataset.ready = "false";
  restoreContextHome();
  renderRoomDoors();
  const room = roomFromState(state);
  const epoch = ++renderEpoch;
  const controller = new AbortController();
  if (els.field._controller) els.field._controller.abort();
  els.field._controller = controller;
  els.field.setAttribute("aria-busy", "true");
  els.field.replaceChildren();
  try {
    const next = await fetchModel(controller.signal);
    if (epoch !== renderEpoch) return;
    model = next;
    const carrier = carrierModel(next);
    const firstObject = modelObjects(next, room)[0];
    const exactFocus = carrier.shown_state?.focus ?? (firstObject ? rawHandle(firstObject) : null);
    if (!activeState.selection.focus && exactFocus) {
      move({ focus: exactFocus }, { replace: true });
      return;
    }
    bindCarrierReceipt(next, room);
    updateOrientation(next);
    els.field.replaceChildren(foreground(next, room));
    renderContext(next);
    dockContext(room);
    bindFeedbackAnchors(els.carrier);
  } catch (error) {
    if (controller.signal.aborted || epoch !== renderEpoch) return;
    model = null;
    setCurrentness("REFUSED", error?.message);
    els.orientationTitle.textContent = ROOMS.find((item) => item.id === room)?.title || "Eigen";
    els.orientationPurpose.textContent = "The exact read model did not answer.";
    els.field.replaceChildren(notice("The room refused to open", error?.message, "refused"));
    els.context.replaceChildren(el("p", "focus-empty", "No context is shown because the source projection refused."));
    els.carrier.dataset.ready = "true";
  } finally {
    if (epoch === renderEpoch) els.field.setAttribute("aria-busy", "false");
  }
}

function scheduleRefresh(reason, certainty = "last-trusted") {
  setCurrentness(certainty === "unknown" ? "UNKNOWN" : "LAST-TRUSTED", reason);
  window.clearTimeout(refreshTimer);
  refreshTimer = window.setTimeout(() => render(store.get()), 120);
}

function startStream() {
  if (stream || typeof EventSource === "undefined") return;
  stream = new EventSource("/front/stream?sources=atlas,talk,journal,campaign");
  stream.addEventListener("atlas:changed", () => scheduleRefresh("Atlas moved; rederiving the shown object."));
  stream.addEventListener("source:changed", () => scheduleRefresh("A source moved; rederiving the shown object."));
  stream.addEventListener("rolled", () => scheduleRefresh("A source rolled; prior continuity is not current.", "unknown"));
  stream.addEventListener("skipped", () => scheduleRefresh("The stream skipped an oversized event; continuity is unknown.", "unknown"));
  stream.addEventListener("atlas:unavailable", () => scheduleRefresh("Atlas is unavailable.", "unknown"));
  stream.addEventListener("empty", () => scheduleRefresh("No exact invalidation source was admitted.", "unknown"));
  stream.onerror = () => scheduleRefresh("Live invalidation is interrupted; the displayed object is last trusted.");
}

function closeHelp() {
  if (els.help.hidden) return false;
  els.help.hidden = true;
  return true;
}

function moveVisible(delta) {
  const visible = [...document.querySelectorAll("[data-object]")]
    .filter((node) => !node.hidden && node.getClientRects().length);
  if (!visible.length) return;
  let index = visible.indexOf(document.activeElement);
  index = index < 0 ? (delta > 0 ? 0 : visible.length - 1)
    : Math.max(0, Math.min(visible.length - 1, index + delta));
  visible[index].focus();
}

document.addEventListener("click", (event) => {
  const grade = event.target.closest("[data-grade]");
  if (grade) move({ grade: grade.dataset.grade });
});

els.back.addEventListener("click", () => window.history.back());
els.help.addEventListener("click", (event) => { if (event.target === els.help) closeHelp(); });

document.addEventListener("keydown", (event) => {
  const target = event.target;
  const typing = target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName);
  if (event.key === "Escape") {
    if (closeHelp()) return;
    if (gradeFromState(store.get()) === "audit") move({ grade: "near" });
    return;
  }
  if (typing || event.metaKey || event.ctrlKey || event.altKey) return;
  if (/^[1-8]$/.test(event.key)) {
    event.preventDefault();
    const room = ROOMS[Number(event.key) - 1];
    move({ lens: room.id });
    return;
  }
  if (event.key === "?") { event.preventDefault(); els.help.hidden = !els.help.hidden; return; }
  if (event.key.toLowerCase() === "j") { event.preventDefault(); moveVisible(1); return; }
  if (event.key.toLowerCase() === "k") { event.preventDefault(); moveVisible(-1); return; }
  if (event.key === "Enter" && document.activeElement?.matches("[data-object]")) {
    document.activeElement.click(); return;
  }
  if (event.key === "[" || event.key === "]") {
    event.preventDefault();
    const index = GRADES.indexOf(gradeFromState(store.get()));
    move({ grade: GRADES[Math.max(0, Math.min(GRADES.length - 1, index + (event.key === "]" ? 1 : -1)))] });
    return;
  }
  if (event.key === "Backspace" && store.get().selection.focus) {
    event.preventDefault(); window.history.back();
  }
});

const initial = store.get();
if (!ROOM_IDS.has(initial.selection.lens) || !GRADES.includes(initial.selection.grade)) {
  move({
    lens: ROOM_IDS.has(initial.selection.lens) ? initial.selection.lens : "now",
    focus: initial.selection.focus,
    edge: initial.selection.edge,
    grade: GRADES.includes(initial.selection.grade) ? initial.selection.grade : "far",
    exposition: /^E[0-7]$/.test(initial.selection.exposition || "") ? initial.selection.exposition : "E0",
  }, { replace: true });
}

const feedback = mountFrontFeedback({
  root: els.carrier,
  actor: els.carrier.dataset.feedbackActor || "",
  getContext: feedbackContext,
});

store.subscribe((state) => render(state));
render(store.get());
startStream();

window.addEventListener("beforeunload", () => {
  if (stream) stream.close();
  feedback.destroy();
});
