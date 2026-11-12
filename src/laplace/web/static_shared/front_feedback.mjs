// Shell-level semantic-object feedback for the next-generation Front carrier.
//
// Identity comes only from producer-owned data-semantic-* attributes and the served
// shown/model context.  This module owns interaction ephemera, never durable truth.

export const FEEDBACK_COMMAND_SCHEMA = "laplace.front-feedback-command/1";
export const FEEDBACK_PROJECTION_SCHEMA = "laplace.front-feedback-projection/1";

const ANCHOR_SELECTOR = "[data-semantic-anchor],[data-semantic-handle]";
const MARKER_LAYER_ATTR = "data-front-feedback-markers";
const STYLE_ATTR = "data-front-feedback-style";
let commandOrdinal = 0;

function text(value) {
  return value === undefined || value === null ? "" : String(value).trim();
}

function commandId() {
  commandOrdinal += 1;
  if (globalThis.crypto && typeof globalThis.crypto.randomUUID === "function") {
    return `front-feedback:${globalThis.crypto.randomUUID()}`;
  }
  return `front-feedback:${Date.now()}:${commandOrdinal}`;
}

function viewportClass(win) {
  const width = Number(win?.innerWidth || 0);
  if (width <= 480) return "narrow";
  if (width <= 1000) return "medium";
  return "wide";
}

function semanticElement(target, boundary) {
  const element = target instanceof Element ? target.closest(ANCHOR_SELECTOR) : null;
  return element && boundary.contains(element) ? element : null;
}

function anchorIdentity(element) {
  return text(element?.dataset?.semanticAnchor || element?.dataset?.semanticHandle);
}

function anchorKind(element) {
  const declared = text(element?.dataset?.semanticKind).toLowerCase();
  if (["object", "edge", "omission", "residual"].includes(declared)) return declared;
  if (element?.hasAttribute("data-semantic-edge")) return "edge";
  if (element?.hasAttribute("data-omission")) return "omission";
  if (element?.hasAttribute("data-residual")) return "residual";
  return "object";
}

function anchorLabel(element) {
  return text(
    element?.dataset?.semanticLabel
      || element?.getAttribute("aria-label")
      || element?.querySelector?.("[data-object-title]")?.textContent
      || element?.textContent,
  ).replace(/\s+/g, " ").slice(0, 240);
}

function parseRoute(element) {
  const raw = text(element?.dataset?.feedbackRoute);
  if (!raw) return null;
  try {
    const route = JSON.parse(raw);
    if (!route || typeof route !== "object" || Array.isArray(route)) return null;
    return route;
  } catch (_error) {
    return null;
  }
}

function geometryFor(element) {
  const rect = element.getBoundingClientRect();
  return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
}

function defaultContext(root, win) {
  const carrier = root.matches?.("[data-aisthesis-carrier]")
    ? root : root.querySelector?.("[data-aisthesis-carrier]");
  const data = carrier?.dataset || {};
  const focus = text(data.focusHandle) || null;
  const edge = text(data.selectedEdge || data.edge) || null;
  const currentness = text(data.currentness) || "UNKNOWN";
  return {
    model_handle: text(data.modelHandle),
    shown_handle: text(data.shownHandle),
    selection: {
      lens: text(data.room || data.lens).toLowerCase(),
      focus,
      edge,
      grade: text(data.grade) || "summary",
      exposition: text(data.exposition) || "E0",
      viewport: text(data.viewport) || viewportClass(win),
    },
    source: data.sourceHandle
      ? { source_handle: text(data.sourceHandle) }
      : { status: "UNKNOWN", reason: "the carrier has not exposed a source handle" },
    currentness: { status: currentness },
  };
}

function anchorFrom(element, context, screenshot = null) {
  return {
    schema_version: "laplace.front-semantic-anchor/1",
    semantic_anchor: anchorIdentity(element),
    kind: anchorKind(element),
    label: anchorLabel(element),
    model_handle: text(context.model_handle),
    shown_handle: text(context.shown_handle),
    selection: {
      lens: text(context.selection?.lens),
      focus: text(context.selection?.focus) || null,
      edge: text(context.selection?.edge) || null,
      grade: text(context.selection?.grade),
      exposition: text(context.selection?.exposition),
      viewport: text(context.selection?.viewport),
    },
    source: context.source && typeof context.source === "object" ? context.source : {},
    currentness: context.currentness && typeof context.currentness === "object"
      ? context.currentness : { status: "UNKNOWN" },
    selection_geometry: geometryFor(element),
    screenshot,
    route: parseRoute(element),
  };
}

async function responseJSON(response) {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const reason = body.reason || body.error || `${response.status} ${response.statusText}`;
    throw new Error(reason);
  }
  return body;
}

export function httpFeedbackTransport({ endpoint = "/front/feedback", win = window } = {}) {
  return {
    async read({ visible_anchor_ids = [] } = {}) {
      const url = new URL(endpoint, win.location.href);
      for (const anchor of visible_anchor_ids) url.searchParams.append("visible_anchor", anchor);
      return responseJSON(await win.fetch(url, { headers: { Accept: "application/json" } }));
    },
    async command(command) {
      return responseJSON(await win.fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          "X-Front-Door": "1",
        },
        body: JSON.stringify(command),
      }));
    },
  };
}

function injectStyle(doc) {
  if (doc.head.querySelector(`[${STYLE_ATTR}]`)) return;
  const style = doc.createElement("style");
  style.setAttribute(STYLE_ATTR, "1");
  style.textContent = `
    [data-front-feedback-hover="true"]{outline:2px solid currentColor!important;outline-offset:4px!important}
    .front-feedback-toggle{position:fixed;z-index:2147483000;right:18px;bottom:18px;min-width:52px;min-height:44px;
      border:1px solid color-mix(in srgb,currentColor 42%,transparent);border-radius:999px;padding:.55rem .85rem;
      background:color-mix(in srgb,Canvas 90%,transparent);color:CanvasText;font:600 .78rem/1.1 system-ui;
      box-shadow:0 9px 30px color-mix(in srgb,CanvasText 18%,transparent);backdrop-filter:blur(10px)}
    .front-feedback-toggle[aria-pressed="true"]{outline:3px double currentColor;outline-offset:3px}
    .front-feedback-toggle__count{display:inline-grid;place-items:center;min-width:1.4rem;height:1.4rem;margin-inline-start:.35rem;
      border-radius:999px;background:CanvasText;color:Canvas;font-size:.7rem}
    .front-feedback-marker-layer{position:fixed;inset:0;z-index:2147482997;pointer-events:none}
    .front-feedback-marker{position:absolute;pointer-events:auto;display:grid;place-items:center;width:22px;height:22px;
      border-radius:50%;border:2px solid Canvas;background:CanvasText;color:Canvas;font:700 .68rem/1 system-ui;
      box-shadow:0 2px 12px color-mix(in srgb,CanvasText 28%,transparent)}
    .front-feedback-marker[data-anchor-state="STALE"]{border-style:dashed}
    .front-feedback-composer{position:fixed;z-index:2147483001;width:min(26rem,calc(100vw - 24px));max-height:min(34rem,calc(100vh - 24px));
      overflow:auto;padding:1rem;border:1px solid color-mix(in srgb,currentColor 44%,transparent);border-radius:1rem;
      background:Canvas;color:CanvasText;box-shadow:0 20px 70px color-mix(in srgb,CanvasText 32%,transparent);font:14px/1.45 system-ui}
    .front-feedback-composer h2{margin:0 0 .25rem;font-size:1rem}.front-feedback-composer p{margin:.2rem 0 .8rem}
    .front-feedback-composer [data-feedback-persistence="unavailable"]{padding:.65rem .75rem;border-inline-start:3px solid currentColor;background:color-mix(in srgb,CanvasText 6%,Canvas);font-weight:650}
    .front-feedback-composer textarea{box-sizing:border-box;width:100%;min-height:7rem;resize:vertical;padding:.7rem;border:1px solid currentColor;
      border-radius:.65rem;background:Canvas;color:CanvasText;font:inherit}
    .front-feedback-composer__actions,.front-feedback-existing__actions{display:flex;gap:.5rem;flex-wrap:wrap;margin-top:.65rem}
    .front-feedback-composer button{min-height:44px;padding:.45rem .75rem;border:1px solid currentColor;border-radius:999px;background:Canvas;color:CanvasText}
    .front-feedback-composer button:disabled,.front-feedback-composer textarea:disabled{cursor:not-allowed;border-style:dashed;opacity:.68}
    .front-feedback-existing{margin:.8rem 0;padding:.7rem 0;border-block:1px solid color-mix(in srgb,currentColor 22%,transparent)}
    .front-feedback-existing q{display:block;margin:.2rem 0 .4rem}.front-feedback-status{min-height:1.25rem;margin-top:.5rem;font-weight:650}
    @media(max-width:480px){.front-feedback-toggle{right:10px;bottom:10px}.front-feedback-composer{left:12px!important;right:12px!important;top:auto!important;bottom:68px;width:auto}}
    @media(prefers-reduced-motion:reduce){.front-feedback-toggle,.front-feedback-marker,.front-feedback-composer{transition:none!important;animation:none!important}}
  `;
  doc.head.append(style);
}

function clampPopover(rect, win) {
  const width = Math.min(416, Math.max(280, win.innerWidth - 24));
  const left = Math.max(12, Math.min(rect.left, win.innerWidth - width - 12));
  const top = Math.max(12, Math.min(rect.bottom + 10, win.innerHeight - 360));
  return { left, top, width };
}

function button(doc, label, action) {
  const node = doc.createElement("button");
  node.type = "button";
  node.textContent = label;
  node.dataset.feedbackAction = action;
  return node;
}

/**
 * Mount one event-delegated overlay.
 *
 * `transport` must ultimately bind the canonical Python seam. Passing a test fake is
 * permitted only for safe specimens. `actor` is mandatory at submit time; the module
 * never silently claims the author's identity.
 */
export function mountFrontFeedback({
  root = document,
  win = window,
  transport = httpFeedbackTransport({ win }),
  actor = "",
  getContext = () => defaultContext(root, win),
  captureScreenshot = null,
} = {}) {
  const doc = root.ownerDocument || root;
  const boundary = root.documentElement || root;
  injectStyle(doc);
  const toggle = doc.createElement("button");
  toggle.type = "button";
  toggle.className = "front-feedback-toggle";
  toggle.dataset.feedbackToggle = "1";
  toggle.setAttribute("aria-pressed", "false");
  toggle.setAttribute("aria-label", "Comment on this interface (Alt Shift C)");
  toggle.innerHTML = "<span data-feedback-toggle-label>Comment</span> <span class=\"front-feedback-toggle__count\" aria-label=\"open comments\">0</span>";
  doc.body.append(toggle);

  const markerLayer = doc.createElement("div");
  markerLayer.className = "front-feedback-marker-layer";
  markerLayer.setAttribute(MARKER_LAYER_ATTR, "1");
  markerLayer.setAttribute("aria-live", "polite");
  doc.body.append(markerLayer);

  let enabled = false;
  let pinned = null;
  let composer = null;
  let projection = { schema_version: FEEDBACK_PROJECTION_SCHEMA, annotations: [], counts: {} };
  let persistenceGate = {
    current: false,
    status: "UNKNOWN",
    refusal: "CANONICAL_ADAPTER_UNAVAILABLE",
    reason: "the canonical annotation writer has not established a current projection",
  };
  let destroyed = false;
  let refreshQueued = false;

  const allAnchors = () => [...boundary.querySelectorAll(ANCHOR_SELECTOR)]
    .filter((element) => anchorIdentity(element));
  const annotationList = () => Array.isArray(projection.annotations) ? projection.annotations : [];
  const forAnchor = (id) => annotationList().filter((item) => item.anchor?.semantic_anchor === id);

  function persistenceGateFor(value) {
    const candidate = value && typeof value === "object" ? value : {};
    const persistence = candidate.persistence && typeof candidate.persistence === "object"
      ? candidate.persistence : {};
    const projectionStatus = text(candidate.status).toUpperCase() || "UNKNOWN";
    const status = text(persistence.status || persistence.currentness?.status).toUpperCase()
      || projectionStatus;
    const available = persistence.available === true;
    const current = status === "CURRENT" && available;
    const refusal = current ? "" : (
      text(persistence.refusal || candidate.refusal)
      || (available ? `CANONICAL_ADAPTER_${status}` : "CANONICAL_ADAPTER_UNAVAILABLE")
    );
    const defect = Array.isArray(candidate.defects) ? text(candidate.defects[0]) : "";
    const reason = current ? "" : (
      defect
      || (available
        ? `the canonical annotation projection is ${status.replaceAll("_", " ").toLowerCase()}`
        : "the canonical annotation writer is unavailable")
    );
    return { current, status, refusal, reason };
  }

  function applyPersistenceGate() {
    if (!composer) return;
    const notice = composer.querySelector("[data-feedback-persistence]");
    if (notice) {
      notice.hidden = persistenceGate.current;
      notice.dataset.feedbackPersistence = persistenceGate.current ? "current" : "unavailable";
      notice.dataset.feedbackRefusal = persistenceGate.refusal;
      notice.title = persistenceGate.refusal;
      notice.textContent = persistenceGate.current ? "" : (
        `Writes refused. ${persistenceGate.reason}. No draft will be sent or stored. (${persistenceGate.refusal})`
      );
    }
    composer.querySelectorAll("[data-feedback-write-control]").forEach((control) => {
      control.disabled = !persistenceGate.current;
      control.dataset.feedbackGatewayStatus = persistenceGate.status;
      control.dataset.feedbackRefusal = persistenceGate.refusal;
      if (persistenceGate.current) {
        control.removeAttribute("aria-describedby");
        control.removeAttribute("title");
      } else {
        control.setAttribute("aria-describedby", "front-feedback-persistence-refusal");
        control.title = persistenceGate.refusal;
      }
    });
  }

  function announce(message, isError = false) {
    if (!composer) return;
    const status = composer.querySelector("[data-feedback-status]");
    if (!status) return;
    status.textContent = message;
    status.dataset.state = isError ? "REFUSED" : "OK";
  }

  function closeComposer({ returnFocus = true } = {}) {
    const target = pinned;
    composer?.remove();
    composer = null;
    pinned = null;
    if (returnFocus) target?.focus?.({ preventScroll: true });
  }

  async function send(command) {
    if (!persistenceGate.current) {
      throw new Error(`${persistenceGate.refusal}: ${persistenceGate.reason}`);
    }
    const result = await transport.command(command);
    if (result?.ok !== true) throw new Error(result?.reason || result?.refusal || "feedback refused");
    await refresh();
    return result;
  }

  function existingRow(annotation, currentAnchor) {
    const row = doc.createElement("article");
    row.className = "front-feedback-existing";
    row.dataset.annotationId = annotation.annotation_id;
    const state = text(annotation.state) || "UNKNOWN";
    const anchorState = text(annotation.anchor_currentness?.status) || "UNKNOWN";
    const heading = doc.createElement("strong");
    heading.textContent = `${state} · ${anchorState}`;
    row.append(heading);
    const quote = doc.createElement("q");
    quote.textContent = text(annotation.text);
    row.append(quote);
    if (state === "OPEN") {
      const actions = doc.createElement("div");
      actions.className = "front-feedback-existing__actions";
      const resolve = button(doc, "Resolve", "resolve");
      resolve.dataset.annotationId = annotation.annotation_id;
      resolve.dataset.feedbackWriteControl = "1";
      actions.append(resolve);
      const withdraw = button(doc, "Withdraw", "withdraw");
      withdraw.dataset.annotationId = annotation.annotation_id;
      withdraw.dataset.feedbackWriteControl = "1";
      actions.append(withdraw);
      if (anchorState === "STALE" && currentAnchor) {
        const reconcile = button(doc, "Re-anchor here", "reconcile");
        reconcile.dataset.annotationId = annotation.annotation_id;
        reconcile.dataset.feedbackWriteControl = "1";
        actions.append(reconcile);
      }
      row.append(actions);
    }
    return row;
  }

  async function openComposer(element) {
    closeComposer({ returnFocus: false });
    pinned = element;
    const id = anchorIdentity(element);
    const box = clampPopover(element.getBoundingClientRect(), win);
    composer = doc.createElement("aside");
    composer.className = "front-feedback-composer";
    composer.setAttribute("role", "dialog");
    composer.setAttribute("aria-modal", "false");
    composer.setAttribute("aria-label", `Comment on ${anchorLabel(element)}`);
    composer.style.left = `${box.left}px`;
    composer.style.top = `${box.top}px`;
    composer.style.width = `${box.width}px`;
    const title = doc.createElement("h2");
    title.textContent = anchorLabel(element);
    composer.append(title);
    const identity = doc.createElement("p");
    identity.textContent = `Pinned ${anchorKind(element)} · comments remain attached across rooms.`;
    composer.append(identity);
    const unavailable = doc.createElement("p");
    unavailable.id = "front-feedback-persistence-refusal";
    unavailable.dataset.feedbackPersistence = "unavailable";
    unavailable.setAttribute("role", "alert");
    composer.append(unavailable);
    for (const annotation of forAnchor(id)) composer.append(existingRow(annotation, element));
    const form = doc.createElement("form");
    form.dataset.feedbackComposer = "1";
    const label = doc.createElement("label");
    label.textContent = "What should change here?";
    const area = doc.createElement("textarea");
    area.name = "comment";
    area.required = true;
    area.placeholder = "Describe the problem in human terms…";
    area.dataset.feedbackWriteControl = "1";
    label.append(area);
    form.append(label);
    const actions = doc.createElement("div");
    actions.className = "front-feedback-composer__actions";
    const submit = doc.createElement("button");
    submit.type = "submit";
    submit.textContent = "Bank comment";
    submit.dataset.feedbackWriteControl = "1";
    actions.append(submit, button(doc, "Cancel", "cancel"));
    form.append(actions);
    const status = doc.createElement("div");
    status.className = "front-feedback-status";
    status.dataset.feedbackStatus = "1";
    status.setAttribute("role", "status");
    form.append(status);
    composer.append(form);
    doc.body.append(composer);
    applyPersistenceGate();
    (persistenceGate.current ? area : actions.querySelector('[data-feedback-action="cancel"]'))?.focus();
  }

  async function makeAnchor(element) {
    const context = await getContext(element);
    const shot = typeof captureScreenshot === "function"
      ? await captureScreenshot({ element, context }) : null;
    return anchorFrom(element, context, shot);
  }

  async function onSubmit(event) {
    const form = event.target.closest?.("[data-feedback-composer]");
    if (!form || !composer || !pinned) return;
    event.preventDefault();
    if (!persistenceGate.current) {
      announce(`Refused: ${persistenceGate.reason} (${persistenceGate.refusal}).`, true);
      return;
    }
    if (!text(actor)) {
      announce("Refused: this surface has not established an explicit actor.", true);
      return;
    }
    const area = form.elements.comment;
    try {
      await send({
        schema_version: FEEDBACK_COMMAND_SCHEMA,
        action: "CREATE",
        command_id: commandId(),
        actor: text(actor),
        text: text(area.value),
        anchor: await makeAnchor(pinned),
        annotation_id: null,
        state: null,
        replacement_annotation_id: null,
      });
      area.value = "";
      announce("Comment banked in canonical history.");
      const target = pinned;
      await openComposer(target);
      announce("Comment banked in canonical history.");
    } catch (error) {
      announce(`Refused: ${error.message}`, true);
    }
  }

  async function onAction(event) {
    const action = event.target.closest?.("[data-feedback-action]")?.dataset.feedbackAction;
    if (!action) return;
    if (action === "cancel") {
      closeComposer();
      return;
    }
    if (!persistenceGate.current) {
      announce(`Refused: ${persistenceGate.reason} (${persistenceGate.refusal}).`, true);
      return;
    }
    const annotationId = event.target.closest("[data-annotation-id]")?.dataset.annotationId;
    if (!annotationId || !pinned || !text(actor)) return;
    try {
      if (action === "reconcile") {
        await send({
          schema_version: FEEDBACK_COMMAND_SCHEMA,
          action: "RECONCILE",
          command_id: commandId(),
          actor: text(actor),
          text: null,
          anchor: await makeAnchor(pinned),
          annotation_id: annotationId,
          state: null,
          replacement_annotation_id: null,
        });
      } else {
        await send({
          schema_version: FEEDBACK_COMMAND_SCHEMA,
          action: "TRANSITION",
          command_id: commandId(),
          actor: text(actor),
          text: null,
          anchor: null,
          annotation_id: annotationId,
          state: action === "resolve" ? "RESOLVED" : "WITHDRAWN",
          replacement_annotation_id: null,
        });
      }
      await openComposer(pinned);
    } catch (error) {
      announce(`Refused: ${error.message}`, true);
    }
  }

  function renderMarkers() {
    markerLayer.replaceChildren();
    const byId = new Map(allAnchors().map((element) => [anchorIdentity(element), element]));
    for (const [id, element] of byId) {
      const annotations = forAnchor(id).filter((item) => item.state !== "WITHDRAWN");
      if (!annotations.length) continue;
      const rect = element.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) continue;
      const marker = doc.createElement("button");
      marker.type = "button";
      marker.className = "front-feedback-marker";
      marker.dataset.feedbackMarkerFor = id;
      const stale = annotations.some((item) => item.anchor_currentness?.status === "STALE");
      marker.dataset.anchorState = stale ? "STALE" : "CURRENT";
      marker.textContent = String(annotations.length);
      marker.setAttribute("aria-label", `${annotations.length} comment${annotations.length === 1 ? "" : "s"} on ${anchorLabel(element)}${stale ? "; anchor moved" : ""}`);
      marker.style.left = `${Math.min(win.innerWidth - 26, Math.max(2, rect.right - 11))}px`;
      marker.style.top = `${Math.min(win.innerHeight - 26, Math.max(2, rect.top - 11))}px`;
      marker.addEventListener("click", () => openComposer(element));
      markerLayer.append(marker);
    }
    const open = annotationList().filter((item) => item.state === "OPEN").length;
    toggle.querySelector(".front-feedback-toggle__count").textContent = String(open);
  }

  async function refresh() {
    if (destroyed) return projection;
    const visible = allAnchors().map(anchorIdentity);
    try {
      const next = await transport.read({ visible_anchor_ids: visible });
      projection = next && typeof next === "object" ? next : projection;
      persistenceGate = persistenceGateFor(projection);
      toggle.dataset.feedbackStatus = persistenceGate.status;
      const unavailable = !persistenceGate.current;
      toggle.dataset.feedbackPersistence = unavailable ? "unavailable" : "available";
      toggle.dataset.feedbackRefusal = unavailable ? persistenceGate.refusal : "";
      toggle.querySelector("[data-feedback-toggle-label]").textContent = unavailable
        ? "Comments unavailable" : "Comment";
      toggle.title = unavailable
        ? `${toggle.dataset.feedbackRefusal} — no draft will be stored`
        : "Comment on this interface (Alt Shift C)";
    } catch (error) {
      persistenceGate = {
        current: false,
        status: "REFUSED",
        refusal: "CANONICAL_ADAPTER_UNAVAILABLE",
        reason: `the annotation projection could not be refreshed: ${error.message}`,
      };
      toggle.dataset.feedbackStatus = "REFUSED";
      toggle.dataset.feedbackPersistence = "unavailable";
      toggle.dataset.feedbackRefusal = "CANONICAL_ADAPTER_UNAVAILABLE";
      toggle.querySelector("[data-feedback-toggle-label]").textContent = "Comments unavailable";
      toggle.title = `Feedback unavailable: ${error.message}`;
    }
    applyPersistenceGate();
    renderMarkers();
    return projection;
  }

  function scheduleRefresh() {
    if (refreshQueued || destroyed) return;
    refreshQueued = true;
    win.requestAnimationFrame(() => {
      refreshQueued = false;
      renderMarkers();
    });
  }

  function setEnabled(value) {
    enabled = Boolean(value);
    toggle.setAttribute("aria-pressed", String(enabled));
    boundary.dataset.feedbackMode = enabled ? "comment" : "off";
    if (!enabled) {
      boundary.querySelectorAll('[data-front-feedback-hover="true"]')
        .forEach((element) => element.removeAttribute("data-front-feedback-hover"));
      closeComposer({ returnFocus: false });
    }
  }

  const onKey = (event) => {
    if (event.altKey && event.shiftKey && event.code === "KeyC") {
      event.preventDefault();
      setEnabled(!enabled);
      toggle.focus();
    } else if (event.key === "Escape" && (enabled || composer)) {
      closeComposer();
      setEnabled(false);
    }
  };
  const onOver = (event) => {
    if (!enabled) return;
    semanticElement(event.target, boundary)?.setAttribute("data-front-feedback-hover", "true");
  };
  const onOut = (event) => {
    semanticElement(event.target, boundary)?.removeAttribute("data-front-feedback-hover");
  };
  const onClick = (event) => {
    const element = semanticElement(event.target, boundary);
    if (!enabled || !element || event.target.closest("[data-front-feedback-markers]")) return;
    event.preventDefault();
    event.stopPropagation();
    openComposer(element);
  };
  toggle.addEventListener("click", () => setEnabled(!enabled));
  doc.addEventListener("keydown", onKey);
  boundary.addEventListener("pointerover", onOver);
  boundary.addEventListener("pointerout", onOut);
  boundary.addEventListener("click", onClick, true);
  doc.addEventListener("submit", onSubmit);
  doc.addEventListener("click", onAction);
  win.addEventListener("resize", scheduleRefresh);
  win.addEventListener("scroll", scheduleRefresh, true);
  const observer = new MutationObserver(scheduleRefresh);
  observer.observe(boundary, { childList: true, subtree: true });
  refresh();

  return {
    enable: () => setEnabled(true),
    disable: () => setEnabled(false),
    refresh,
    getProjection: () => projection,
    openFor: (semanticAnchor) => {
      const element = allAnchors().find((item) => anchorIdentity(item) === semanticAnchor);
      if (!element) return false;
      setEnabled(true);
      openComposer(element);
      return true;
    },
    destroy: () => {
      destroyed = true;
      observer.disconnect();
      doc.removeEventListener("keydown", onKey);
      boundary.removeEventListener("pointerover", onOver);
      boundary.removeEventListener("pointerout", onOut);
      boundary.removeEventListener("click", onClick, true);
      doc.removeEventListener("submit", onSubmit);
      doc.removeEventListener("click", onAction);
      win.removeEventListener("resize", scheduleRefresh);
      win.removeEventListener("scroll", scheduleRefresh, true);
      closeComposer({ returnFocus: false });
      markerLayer.remove();
      toggle.remove();
    },
  };
}

export default mountFrontFeedback;
