// store.mjs — The one client model (W0.3), the first artefact of the front-end rewrite.
//
// One shared, URL-canonical client model every rebuilt surface reads and writes,
// so no two surfaces can disagree about which project / node / round is in view.
// ESM, ZERO dependencies, small enough to read whole.
//
// ─ THE CONTRACT ──────────────────────────────────────────────────────────────
//
//   state = {
//     project:   string | null,          // the active project (server-canonical id)
//     selection: { corpus, node, beat, section, round, version, asset,
//                  focus, grade, exposition, lens, edge },
//                                                        // each string|null
//     decision:  string | null           // the author-decision context in view (a finding id, a verb)
//   }
//
// URL-CANONICAL — the URL query string IS the model's serialization. Every state
// field is one query param of the same name (project, corpus, node, beat, section,
// round, version, asset, focus, grade, exposition, lens, edge, decision);
// `selection.*` flatten to top-level
// params. On import the
// store reads `location.search`; every `set()` writes it back (history.pushState by
// default, replaceState when `{replace:true}`); `popstate` re-reads it (plain — the
// browser back/forward button moves the model, and subscribers are notified). A field
// set to null / '' is REMOVED from the URL (never a `?corpus=&node=` empty-param lie).
//
//   store.get()                       → a frozen snapshot {project, selection, decision}
//   store.set(patch, opts?)           → merge a FLAT patch (keys are the param names:
//                                       project|corpus|node|beat|section|round|version|
//                                       asset|focus|grade|exposition|lens|edge|decision);
//                                       writes the URL + notifies. opts:
//                                       {replace:true} → replaceState (no history entry).
//   store.subscribe(fn)               → fn(state) on every change; returns an unsubscribe.
//   store.fetchJSON(path, opts?)      → the one fetch gateway. Injects the corpus (and
//                                       any opts.inject selection keys) + opts.params into
//                                       the query, parses JSON, and SINGLE-FLIGHTS per key
//                                       (a second call for the same method+URL in flight
//                                       returns the SAME promise — no duplicate GET).
//                                       opts: {params, inject, method, body, headers, signal}.
//
// STANDALONE — importing the module self-initializes from the URL and (in a browser)
// publishes `window.HymnStore = store`, so a smoke page that loads ONLY this file works.
// In a non-DOM host (a bare `node` import) it degrades: no location → an empty model,
// no history/popstate wiring → set() just updates state + notifies.

/** The selection sub-keys that flatten to top-level URL params. `asset` is the evidence
 *  door; `focus`, `grade`, `exposition`, `lens` and `edge` carry the Aisthesis camera's
 *  exact selection. They share this one model so a reload / Back restores one selection
 *  atomically. The spatial Programme and Continuity cameras own `focus`; legacy
 *  `node` retains its existing meaning for non-spatial cameras.
 *  @type {string[]} */
const SELECTION_KEYS = [
  "corpus", "node", "beat", "section", "round", "version", "asset",
  "focus", "grade", "exposition", "lens", "edge",
];
/** Every URL param the model owns, in canonical order. @type {string[]} */
const PARAMS = ["project", ...SELECTION_KEYS, "decision"];
const CARRIER_LENSES = new Set([
  "now", "programme", "work", "decision", "run", "conversation",
  "exposition", "diagnostics",
]);
const EDGE_COMPATIBLE_LENSES = new Set([
  ...CARRIER_LENSES, "evidence-descent", "continuity",
]);
const FOCUS_LENSES = new Set([...CARRIER_LENSES, "continuity"]);
const EXPOSITION_LENSES = new Set(["conversation", "exposition", "continuity"]);
const CONTINUITY_LENS = "continuity";
const GRADES = new Set(["far", "mid", "near", "audit"]);
const EXPOSITIONS = new Set(["E0", "E1", "E2", "E3", "E4", "E5", "E6", "E7"]);

/** D15 — the sessionStorage key the arrival-echo origin rides under (shared with the
 *  shell's inline fallback, so a surface with the model and one without stamp the same
 *  shape). @type {string} */
const ORIGIN_KEY = "hymn.origin";

const hasWin = typeof window !== "undefined";
const hasHistory = hasWin && typeof window.history !== "undefined"
  && typeof window.history.pushState === "function";

function emptyState() {
  const selection = {};
  for (const k of SELECTION_KEYS) selection[k] = null;
  return { project: null, selection, decision: null };
}

/** Where a flat param name lives in the nested state. */
function routeGet(state, key) {
  if (key === "project") return state.project;
  if (key === "decision") return state.decision;
  return state.selection[key];
}
function routeSet(state, key, val) {
  if (key === "project") state.project = val;
  else if (key === "decision") state.decision = val;
  else if (SELECTION_KEYS.includes(key)) state.selection[key] = val;
}

/** Canonicalize bounded Aisthesis enums at every store ingress. */
function selectionValue(key, raw) {
  const val = (raw === undefined || raw === null || raw === "") ? null : String(raw);
  if (val === null) return null;
  if (key === "grade" && !GRADES.has(val)) return null;
  if (key === "exposition" && !EXPOSITIONS.has(val)) return null;
  return val;
}

/** A deep-frozen snapshot so no subscriber can mutate the model in place. */
function snapshot(state) {
  return Object.freeze({
    project: state.project,
    selection: Object.freeze({ ...state.selection }),
    decision: state.decision,
  });
}

class Store {
  constructor() {
    this._state = emptyState();
    this._subs = new Set();
    this._inflight = new Map();   // key "METHOD url" -> Promise (single-flight)
    this._readURL();
    if (hasWin && typeof window.addEventListener === "function") {
      window.addEventListener("popstate", () => { this._readURL(); this._notify(); });
    }
  }

  // ── reads ──────────────────────────────────────────────────────────────────

  /** A frozen snapshot of the whole model. */
  get() { return snapshot(this._state); }

  /** One field by its flat param name (project|corpus|node|…|decision). */
  field(key) { return routeGet(this._state, key); }

  /** The most specific selection token in view (node ≻ version ≻ section ≻ beat ≻
   *  round), as {key, val}, or null when nothing is selected. The arrival echo names
   *  this — the fine-grained "where I came from", not just the surface. */
  firstSelection() {
    for (const k of ["node", "version", "section", "beat", "round"]) {
      const v = this._state.selection[k];
      if (v != null && v !== "") return { key: k, val: v };
    }
    return null;
  }

  // ── D15 · The arrival-echo origin (the model-side owner) ────────────────────
  // The canonical stamp/read of "where a navigation came from", so the shell's echo
  // renders a door back. The model owns the selection + project; the SURFACE LABEL is
  // left null here and resolved by the shell against the roster at render time (the
  // model does not carry the roster). Degrades to a no-op / null off-DOM.

  /** Stamp the current surface (path+query), project, and selection as the navigation
   *  origin — call on unload, so the NEXT surface can echo the door back. */
  stampOrigin() {
    if (!hasWin || !window.sessionStorage || !window.location) return;
    try {
      window.sessionStorage.setItem(ORIGIN_KEY, JSON.stringify({
        path: (window.location.pathname || "") + (window.location.search || ""),
        surface: null,          // roster label resolved by the shell at render time
        project: this._state.project || this._state.selection.corpus || null,
        selection: this.firstSelection(),
        ts: Date.now(),
      }));
    } catch (_e) { /* private-mode / quota — the echo just doesn't render */ }
  }

  /** Read the stamped origin (or null). Freshness (the <5 min window) + the
   *  same-surface guard are the shell's call, not the model's. */
  readOrigin() {
    if (!hasWin || !window.sessionStorage) return null;
    try {
      const raw = window.sessionStorage.getItem(ORIGIN_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (_e) { return null; }
  }

  // ── writes ───────────────────────────────────────────────────────────────

  /**
   * Merge a FLAT patch into the model, write the URL, and notify subscribers.
   * A value of null / undefined / "" CLEARS the field (drops the param).
   * @param {Object} patch keys ⊂ {project,corpus,node,beat,section,round,version,asset,
   *                                  focus,grade,exposition,lens,edge,decision}
   * @param {{replace?:boolean}} [opts] replace:true → replaceState (no new history entry)
   */
  set(patch, opts = {}) {
    if (!patch || typeof patch !== "object") return this.get();
    const next = { ...patch };
    const owns = (key) => Object.prototype.hasOwnProperty.call(next, key);
    const currentLens = this._state.selection.lens;
    const requestedLens = owns("lens") ? selectionValue("lens", next.lens) : currentLens;
    if (owns("lens")) {
      const crossingLegacyContinuity = currentLens !== requestedLens
        && (currentLens === CONTINUITY_LENS || requestedLens === CONTINUITY_LENS)
        && !(CARRIER_LENSES.has(currentLens) && CARRIER_LENSES.has(requestedLens));
      if (FOCUS_LENSES.has(requestedLens)) {
        // Spatial cameras have an exact focus coordinate; legacy node never aliases it.
        next.node = null;
      } else {
        // Spatial coordinates cannot leak into a non-spatial camera.
        next.focus = null;
        next.exposition = null;
      }
      // The next-generation carrier's rooms are contextual representations of the SAME
      // object, so room switches preserve focus/edge.  The legacy Continuity camera has
      // a different coordinate and retains its fail-closed crossing law.
      if (crossingLegacyContinuity && !owns("focus")) next.focus = null;
      if (crossingLegacyContinuity && !owns("edge")) next.edge = null;
      if (!EDGE_COMPATIBLE_LENSES.has(requestedLens)) next.edge = null;
      if (!EXPOSITION_LENSES.has(requestedLens)) next.exposition = null;
    }
    if (FOCUS_LENSES.has(requestedLens) && owns("node")) next.node = null;
    if (!FOCUS_LENSES.has(requestedLens)) {
      if (owns("focus")) next.focus = null;
    }
    if (!EXPOSITION_LENSES.has(requestedLens) && owns("exposition")) next.exposition = null;
    let changed = false;
    for (const [k, raw] of Object.entries(next)) {
      if (k !== "project" && k !== "decision" && !SELECTION_KEYS.includes(k)) continue;
      const val = selectionValue(k, raw);
      if (routeGet(this._state, k) !== val) { routeSet(this._state, k, val); changed = true; }
    }
    if (changed) { this._writeURL(!!opts.replace); this._notify(); }
    return this.get();
  }

  /**
   * Subscribe to every model change (including popstate). Returns an unsubscribe fn.
   * @param {(state:object)=>void} fn
   */
  subscribe(fn) {
    if (typeof fn !== "function") return () => {};
    this._subs.add(fn);
    return () => this._subs.delete(fn);
  }

  // ── the one fetch gateway ──────────────────────────────────────────────────

  /**
   * The single fetch door: inject the corpus (+ opts.inject selection keys + opts.params)
   * into the query, parse JSON, single-flight per method+URL. Every surface fetches through
   * here so the corpus/selection ride EVERY request from ONE place.
   * @param {string} path a route path (e.g. "/shared/versions")
   * @param {{params?:object, inject?:string[], method?:string, body?:any,
   *          headers?:object, signal?:AbortSignal, raw?:boolean}} [opts]
   * @returns {Promise<any>} the parsed JSON body — or, with `{raw:true}`, the response
   *          TEXT (a route that serves text/plain, e.g. /projection/tex: the one gateway
   *          still owns it, so the artefact editor never opens a raw fetch of its own).
   */
  fetchJSON(path, opts = {}) {
    const url = this._withParams(path, opts);
    const method = (opts.method || "GET").toUpperCase();
    const key = method + " " + url;
    // single-flight: an identical in-flight request shares its promise (GET/HEAD only —
    // a mutating verb always fires, two POSTs are two intents, never one).
    const idempotent = method === "GET" || method === "HEAD";
    if (idempotent && this._inflight.has(key)) return this._inflight.get(key);

    const init = { method, headers: { ...(opts.headers || {}) } };
    // Match scanner's guarded writing routes at the shared same-origin gateway.
    // Reads and other origins never inherit this deliberate-action identity.
    const base = hasWin ? window.location.href : 'http://localhost/';
    const endpoint = new URL(url, base);
    const writingRoute = endpoint.origin === new URL(base).origin &&
      ['/authoring/','/research/','/references/','/formal/','/projects/','/work/','/concepts/','/visuals/']
        .some(prefix => endpoint.pathname.startsWith(prefix));
    if (method === 'POST' && writingRoute) {
      init.headers['X-Laplace-Writing'] = '1';
    }
    if (opts.signal) init.signal = opts.signal;
    if (opts.body !== undefined) {
      init.body = typeof opts.body === "string" ? opts.body : JSON.stringify(opts.body);
      if (!init.headers["Content-Type"]) init.headers["Content-Type"] = "application/json";
    }
    const p = fetch(url, init).catch((error) => {
      if(error?.name==='TypeError' && typeof document!=='undefined' && document.querySelector('#walk.writing-embedded')){
        window.parent.postMessage({type:'laplace:engine-unavailable'},window.location.origin);
      }
      throw error;
    }).then((r) => {
      if (!r.ok) return r.text().then((t) => {
        let msg = t, body = null;
        try {
          body = JSON.parse(t) || null;
          const reason = body?.reason ?? body?.result?.reason;
          msg = typeof body?.error === 'string' ? body.error : typeof reason === 'string' ? reason : t;
        }
        catch (_e) { /* text */ }
        const error = new Error(`fetchJSON ${method} ${url} → ${r.status}: ${msg}`);
        // THE REFUSAL'S BODY, CARRIED (WRITING-CONSOLIDATION-W1). This gateway used to parse
        // the body, lift `error` out of it and THROW THE REST AWAY — so a 409 whose
        // `refused.needed` holds the exact cure arrived at the caller as a sentence, and the
        // one mechanism the identity layer exists to provide (`{**request, **needed}`) could
        // not be used from any surface in this tree. The status and the parsed body ride the
        // Error, so a caller can retry; `refused` is lifted to the top for the same reason the
        // grammar puts `needed` inside the refusal and not beside it: one place to look.
        error.status = r.status;
        error.body = body;
        error.result = body?.source_effect !== undefined ? body : body?.result && typeof body.result === 'object' ? body.result : body;
        error.reason = body?.reason ?? body?.result?.reason;
        error.recovery = body?.recovery ?? body?.result?.recovery;
        error.refused = body?.refused ?? body?.result?.refused ?? null;
        throw error;
      });
      return opts.raw ? r.text() : r.json();
    }).finally(() => { if (idempotent) this._inflight.delete(key); });
    if (idempotent) this._inflight.set(key, p);
    return p;
  }

  /** Build the final URL: path + injected corpus/selection + explicit params. */
  _withParams(path, opts) {
    // Aisthesis selection is URL state, not implicit API arguments; callers must opt in.
    const inject = opts.inject || ["corpus"];   // the corpus rides every request by default
    // Declared route/arguments own their scope. Implicit reading state only fills
    // absent keys; it must never add a second corpus to an exact owner handle.
    const question = path.indexOf('?'), fragment = path.indexOf('#');
    const queryEnd = fragment < 0 ? path.length : fragment;
    const declared = new URLSearchParams(question < 0 ? '' : path.slice(question + 1, queryEnd));
    const scopedKeys=new Set(['corpus','project',...inject]);
    const explicit = Object.entries(opts.params || {}).filter(([k,v])=>v != null && (v !== '' || scopedKeys.has(k)));
    const explicitKeys = new Set(explicit.map(([k])=>k));
    const hasDeclaredProject=['corpus','project'].some(key=>declared.has(key)||explicitKeys.has(key));
    const pairs = [];
    for (const k of inject) {
      const v = routeGet(this._state, k);
      if (v != null && v !== "" && !declared.has(k) && !explicitKeys.has(k) &&
          !(hasDeclaredProject&&['corpus','project'].includes(k))) pairs.push([k, v]);
    }
    for (const [k, v] of explicit) {
      if(declared.has(k)) {
        const values=declared.getAll(k);
        if(values.length!==1 || values[0]!==String(v)) throw new Error('Conflicting explicit request coordinate: '+k);
      } else pairs.push([k, String(v)]);
    }
    if (!pairs.length) return path;
    const qs = pairs.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join("&");
    const base=path.slice(0,queryEnd),hash=fragment<0?'':path.slice(fragment);
    return base + (base.includes("?") ? "&" : "?") + qs + hash;
  }

  // ── URL <-> state ────────────────────────────────────────────────────────

  _readURL() {
    if (!hasWin || !window.location) return;
    const q = new URLSearchParams(window.location.search || "");
    for (const k of PARAMS) {
      const v = q.get(k);
      routeSet(this._state, k, selectionValue(k, v));
    }
    // A URL may carry an old cross-camera selection. Keep the model fail-closed even
    // before its next canonical write; the URL is cleaned on that write without losing
    // unknown parameters.
    if (FOCUS_LENSES.has(this._state.selection.lens)) {
      this._state.selection.node = null;
    } else {
      this._state.selection.focus = null;
      this._state.selection.exposition = null;
    }
    if (!EDGE_COMPATIBLE_LENSES.has(this._state.selection.lens)) {
      this._state.selection.edge = null;
    }
    if (!EXPOSITION_LENSES.has(this._state.selection.lens)) {
      this._state.selection.exposition = null;
    }
  }

  _writeURL(replace) {
    if (!hasHistory) return;
    const q = new URLSearchParams(window.location.search || "");
    for (const k of PARAMS) {
      const v = routeGet(this._state, k);
      if (v == null || v === "") q.delete(k); else q.set(k, v);
    }
    const qs = q.toString();
    const url = window.location.pathname + (qs ? "?" + qs : "") + (window.location.hash || "");
    (replace ? window.history.replaceState : window.history.pushState)
      .call(window.history, window.history.state, "", url);
  }

  _notify() {
    const snap = this.get();
    for (const fn of [...this._subs]) { try { fn(snap); } catch (_e) { /* a bad subscriber never breaks the store */ } }
  }
}

const store = new Store();
if (hasWin) window.HymnStore = store;   // the standalone / smoke-page hook

export default store;
export { store, Store, PARAMS, SELECTION_KEYS, ORIGIN_KEY };
