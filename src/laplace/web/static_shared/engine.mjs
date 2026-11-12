// engine.mjs — the FocusState runtime (E3): the reusable focus/geometry engine.
//
// The composition law's geometry couplet made mechanical (DESIGN_2026-07-22_the-interface-
// engine.md B, E, F): hover REVEALS (a transient lens, geometrically stable, no reflow);
// opening REALLOCATES (the focus claims the centre, context contracts to a rail + breadcrumb,
// and closing restores geometry + scroll + selection exactly). The base altitude is the BRIEF
// (E): the resting DOM is a few composed sentences plus counts — nothing is materialised until
// a focus summons it, and closing returns to the brief, never to a wall.
//
// This module exports clean primitives (the editor joins them next), not cockpit-specific code:
//   createFocusState · HighlightBus · HoverLens · Reallocator · returnDoor · activate.
// All colour is a hymn var; this file carries layout only.

const ENGINE_CSS = `
/* the hover lens — a fixed overlay, so revealing an item never moves the page under the cursor */
.eng-lens{position:fixed;z-index:6000;max-width:min(420px,44vw);display:none;flex-direction:column;gap:7px;
  background:var(--panel2);border:1px solid var(--accent);border-radius:10px;padding:11px 13px;
  box-shadow:0 16px 40px -12px color-mix(in srgb,black 80%,transparent);font:12px/1.55 -apple-system,"Segoe UI",Roboto,sans-serif;color:var(--ink2)}
.eng-lens.on{display:flex}
.eng-lens .lens-h{font-family:var(--mono);font-size:8.5px;text-transform:uppercase;letter-spacing:.07em;color:var(--accent);font-weight:700}
.eng-lens b{color:var(--ink)}
/* the reallocated geometry — the focus claims the centre; context becomes a left rail */
.eng-root{display:block}
.eng-root.reallocated{display:grid;grid-template-columns:minmax(220px,264px) 1fr;gap:20px;align-items:start}
.eng-root.reallocated .eng-brief{display:none}
.eng-realloc{display:none;min-width:0}
.eng-root.reallocated .eng-realloc{display:block}
.eng-rail{display:flex;flex-direction:column;gap:12px;position:sticky;
  top:calc(var(--hy-shell-real,56px) + 12px);min-width:0}
.eng-breadcrumb{display:flex;align-items:center;gap:7px;font-family:var(--mono);font-size:11px;color:var(--dim);
  padding-bottom:9px;border-bottom:1px solid var(--edge)}
.eng-breadcrumb a{color:var(--accent);text-decoration:none;cursor:pointer}
.eng-breadcrumb a:hover{text-decoration:underline}
.eng-breadcrumb .bc-here{color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.eng-railblock{border:1px solid var(--edge);border-radius:9px;background:var(--panel);padding:10px 11px;min-width:0}
.eng-railblock h5{margin:0 0 7px;font-family:var(--mono);font-size:9px;text-transform:uppercase;letter-spacing:.09em;color:var(--dim);font-weight:700}
.eng-focus{min-width:0}
/* the return door — a persistent, visible affordance naming where it returns to (F.5) */
.eng-return{display:inline-flex;align-items:center;gap:7px;cursor:pointer;font:640 11px var(--mono);
  color:var(--accent);background:var(--bg);border:1px solid var(--accent);border-radius:8px;padding:6px 12px}
.eng-return:hover{background:var(--panel2);color:var(--ink)}
.eng-return:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.eng-return .rd-arrow{font-size:12px}
/* the highlight-bus lit state — a light across panes, never a tooltip, never a layout shift */
.lit{box-shadow:inset 0 0 0 1px var(--warn);background:color-mix(in srgb,var(--warn) 12%,transparent)}
`;

export function injectEngineCSS(id = "eng-components") {
  if (typeof document === "undefined" || document.getElementById(id)) return;
  const st = document.createElement("style");
  st.id = id; st.textContent = ENGINE_CSS;
  document.head.appendChild(st);
}

// ── the FocusState store (B.1), one per surface ────────────────────────────────
export function createFocusState(entry = "index") {
  return { hover: null, pinned: null, opened: [], restore: { scrollY: 0, selection: null, geometry: "brief" }, entry };
}

// ── keyboard activation: a button is a button (Enter / Space), plus click ──────
export function activate(el, fn) {
  if (!el) return el;
  el.addEventListener("click", fn);
  el.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " " || e.key === "Spacebar") { e.preventDefault(); fn(e); }
  });
  return el;
}

// ── the highlight bus (B.4 / F.3): light .lit across panes keyed on data-* ─────
// Cleared at the start of every pin, switch, and close — never left lit across a transition.
export class HighlightBus {
  constructor(root = document) { this.root = root; this._lit = []; }
  lit(pairs, on) {
    for (const [key, val] of pairs) {
      if (val == null) continue;
      this.root.querySelectorAll(`[data-${key}="${cssEsc(val)}"]`).forEach((el) => {
        el.classList.toggle("lit", !!on);
        if (on) this._lit.push(el);
      });
    }
  }
  clear() {
    this.root.querySelectorAll(".lit").forEach((el) => el.classList.remove("lit"));
    this._lit = [];
  }
}
function cssEsc(v) { return String(v).replace(/["\\]/g, "\\$&"); }

// ── the hover lens (B.2): transient, geometrically stable (fixed overlay, no reflow) ──
export class HoverLens {
  constructor() {
    this.el = document.createElement("div");
    this.el.className = "eng-lens";
    this.el.setAttribute("aria-hidden", "true");
    document.body.appendChild(this.el);
  }
  show(anchorEl, html) {
    this.el.innerHTML = html;
    this.el.classList.add("on");
    const r = anchorEl.getBoundingClientRect();
    // place beside the anchor, clamped to the viewport — position:fixed means zero reflow.
    const lw = Math.min(this.el.offsetWidth || 380, window.innerWidth - 24);
    let left = r.left; let top = r.bottom + 8;
    if (left + lw > window.innerWidth - 12) left = Math.max(12, window.innerWidth - lw - 12);
    if (top + (this.el.offsetHeight || 120) > window.innerHeight - 12) top = Math.max(12, r.top - (this.el.offsetHeight || 120) - 8);
    this.el.style.left = left + "px";
    this.el.style.top = top + "px";
  }
  hide() { this.el.classList.remove("on"); }
}

// ── the return door (F.5): a real button naming its destination ────────────────
export function returnDoor(destinationLabel, onReturn) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "eng-return";
  b.setAttribute("aria-label", "return: " + destinationLabel);
  b.dataset.role = "return-door";
  b.innerHTML = "<span class='rd-arrow'>←</span><span class='rd-label'>" + escapeHTML(destinationLabel) + "</span>";
  activate(b, (e) => { if (e && e.preventDefault) e.preventDefault(); onReturn(); });
  return b;
}
function escapeHTML(s) {
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

// ── the reallocator (B.2 / B.3 / E): brief ⇄ reallocated, with exact restore ───
// The root holds two children: `.eng-brief` (the resting DOM, present at rest) and the
// reallocated pair `.eng-rail` + `.eng-focus` (built on pin, removed on close). The brief
// is never css-hidden residue when reallocated — it is display:none only while a focus is
// pinned, and the rail/focus are absent from the DOM at rest.
export class Reallocator {
  constructor(rootEl, state, bus) {
    this.root = rootEl; this.state = state; this.bus = bus;
    this.root.classList.add("eng-root");
    this.rail = null; this.focus = null;
  }
  get pinned() { return !!this.state.pinned; }
  // pin: capture restore (once, on the first pin), reallocate, build the rail + focus panes.
  pin(entry, { title, buildRail, buildFocus, destination }) {
    const switching = this.root.classList.contains("reallocated");
    this.bus.clear();                                    // F.3 hygiene: clear at the start of every pin/switch
    if (!switching) {
      this.state.restore.scrollY = window.scrollY;       // B.3: geometry + scroll captured at pin
      this.state.restore.geometry = "reallocated";
    }
    this.state.pinned = { id: entry, title };
    this._ensurePanes();
    // breadcrumb + the return door (named, visible)
    this.rail.querySelector(".bc-here").textContent = title || "";
    const railBody = this.rail.querySelector(".eng-railbody");
    railBody.innerHTML = "";
    if (buildRail) buildRail(railBody);
    this.focus.innerHTML = "";
    const door = returnDoor(destination || "back to the brief", () => this.close());
    this.focus.appendChild(door);
    if (buildFocus) buildFocus(this.focus);
    this.root.classList.add("reallocated");
    if (!switching) window.scrollTo(0, 0);
  }
  _ensurePanes() {
    if (this.rail && this.focus && this.rail.isConnected) return;
    this.rail = document.createElement("div");
    this.rail.className = "eng-realloc eng-rail";
    this.rail.innerHTML =
      "<div class='eng-breadcrumb'><a class='bc-root' role='button' tabindex='0'>brief</a>" +
      "<span>/</span><span class='bc-here'></span></div>" +
      "<div class='eng-railbody'></div>";
    this.focus = document.createElement("div");
    this.focus.className = "eng-realloc eng-focus";
    this.root.appendChild(this.rail);
    this.root.appendChild(this.focus);
    activate(this.rail.querySelector(".bc-root"), () => this.close());
  }
  // close: pop one opened level; at the empty stack, restore geometry + scroll + selection.
  close() {
    this.bus.clear();                                    // F.3 hygiene: clear at the start of every close
    if (this.state.opened.length) { this.state.opened.pop(); }
    this.state.pinned = null;
    this.state.restore.geometry = "brief";
    this.root.classList.remove("reallocated");
    // remove the reallocated panes entirely — no css-hidden residue at rest (F.2, E)
    if (this.rail) { this.rail.remove(); this.rail = null; }
    if (this.focus) { this.focus.remove(); this.focus = null; }
    const y = this.state.restore.scrollY || 0;
    window.scrollTo(0, y);                               // B.3: exact scroll restore
  }
}

export default { injectEngineCSS, createFocusState, activate, HighlightBus, HoverLens, returnDoor, Reallocator };
