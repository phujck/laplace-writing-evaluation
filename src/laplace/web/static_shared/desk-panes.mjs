// desk-panes.mjs — The desk, joined to the one instrument (W-DESK), a SHARED module.
//
// The desk rides engine.mjs like the growth cockpit (DESIGN_2026-07-22_the-interface-
// engine.md B, E, F). Its resting state is NOT an inventory of eleven classes but a
// COMPOSED BRIEF of what needs HIM now (server-minted in desk.py): the genuinely-his rows
// as glances with the plain reason each needs him, plus one-line counts for every
// summonable class. Nothing is materialised until a chip — or a deep-link (B.5, no lobby
// tax) — summons it. Opening a row REALLOCATES: the four-zone cockpit claims the centre,
// context contracts to a rail, and a named return door leads back to the brief.
//
// The cockpit itself is UNCHANGED (the four zones — CONTEXT / CONSEQUENCES / TOOLS /
// DEEP-LINKS — and every write path: arm-to-fire, the evidence compose, POST /desk/act to
// the real executor). This wave re-dresses the GEOMETRY around it; it never touches the
// mutation doors. renderCockpit is still a SHARED component (/artefact's tray reuses it).
// All network rides store.fetchJSON (the one gateway); no raw fetch escapes the model.

import store from "/shared/store.mjs";
import { injectEngineCSS, createFocusState, HighlightBus, HoverLens, Reallocator, activate } from "/shared/engine.mjs";

// ── tiny helpers ────────────────────────────────────────────────────────────────
const esc = (s) => String(s == null ? "" : s)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
  .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
// word-boundary ellipsis (finding 7): a truncation backs up to the last whole word rather
// than clipping mid-word ("…autho…"), then trims trailing punctuation before the ellipsis.
const cut = (s, n) => {
  s = String(s || "");
  if (s.length <= n) return s;
  let t = s.slice(0, n - 1);
  const sp = t.lastIndexOf(" ");
  if (sp > n * 0.6) t = t.slice(0, sp);
  return t.replace(/[\s.,;:—–-]+$/, "") + "…";
};
// THE VISIBLE ⓘ IDIOM (A3 — the W5 judge): /desk's mechanism transparency used to ride
// hover-only chip `title` tooltips alone — invisible until a mouse happens to land on a
// chip. /artefact's findings tray already carries this as a VISIBLE glyph (the same
// `infoTag` in artefact-panes.mjs / conceptric-panes.mjs / storyboard-panes.mjs): an
// always-rendered ⓘ span whose OWN title names "endpoint → producing file". Matched here,
// verbatim, so the idiom is the same one letter for letter — never a re-invented cousin.
function infoTag(txt) { return " <span class='hy-info' title='" + esc(txt) + "' tabindex='0'>ⓘ</span>"; }

// the explicit actor every desk write carries (mirrors /review's ACTOR). The door refuses
// (422) any unattributed write BEFORE any executor runs, so this is never blank — a missing
// actor renders the door's plain 422.
export const DESK_ACTOR = "author";

// verbs that DISCARD / REVOKE / REFUSE / APPLY-A-BATCH — they ARM on the first click
// (relabel "this will X") and fire only on a second click within the window; a click
// elsewhere (or the timeout) disarms. The client guard is the affordance; the door is the
// real guard (an unwired verb 422s regardless).
export const DESTRUCTIVE = {
  "ratify": "apply EVERY open plan intent for this project — the C3.5 bridge is a batch, not just this row",
  "dismiss": "discard this finding — a fingerprinted suppression silences it",
  "defer": "defer this finding — it leaves the active queue",
  "revoke-intent": "revoke this queued intent — it will not be applied",
  "revoke": "revoke this suppression — the finding can re-surface",
  "widen": "silence ALL kinds on this node",
  "reject": "reject this proxy ruling",
  "refuse": "refuse this lift",
  "contest-ruling": "contest this ruling",
  "resolve-cluster": "resolve the WHOLE recurrence cluster",
  "consume": "consume this work-order — it leaves the open set",
};
// verbs that need an authored choice (free text / a plan verb / an intent) — they do NOT
// fire blindly; the button opens the working surface where the compose UI lives. ``consume``
// is here for the CONTRACT (the evidence-compose clause greps this set) but is handled by the
// EVIDENCE path below (an inline evidence editor that then fires), never a bare nav link.
export const COMPOSE = new Set(["comment", "route-plan", "route-conceptric", "amend", "edit-in-place", "consume"]);

// verbs whose executor REQUIRES evidence (the store refuses an evidence-less resolution):
// the button opens an inline evidence editor and fires the door WITH the refs the chair
// attaches — never evidence_refs=[] into a door that always 422s (the E3 consume dead-end).
export const EVIDENCE = new Set(["consume", "resolve", "resolve-cluster"]);

// AUTHORING verbs (PV the-ruling-needs-a-composer): a verb whose write carries HIS WORDS — a
// ruling, an objection. The button opens a COMPOSER (the question restated, an optional quick-
// choice, a REQUIRED ruling field, an optional commentary) and fires the door with his words;
// a bare confirm is refused (an authoring act must have an authoring field). The door 422s an
// empty ruling regardless (desk.py::_AUTHORING_VERBS), so this is the affordance, not the guard.
export const AUTHORING = new Set(["bank-ruling", "contest-ruling", "reject"]);

// ── Arm-to-fire (the overrule idiom): the FIRST click only ARMS; a second click within the
// window fires; a click elsewhere or the timeout disarms. Pure over its injected timers so a
// DOM harness proves one click never fires a destructive door. ─────────────────────────────
export function armToFire(btn, verb, label, onFire, opts) {
  opts = opts || {};
  const setT = opts.setTimeout || setTimeout, clearT = opts.clearTimeout || clearTimeout;
  const armMs = opts.armMs || 4000;
  const arming = label || ("this will " + verb);
  let armed = false, t = null;
  const disarm = () => { armed = false; btn.classList.remove("armed"); btn.textContent = verb;
    if (t) { clearT(t); t = null; } };
  btn._deskDisarm = disarm;
  btn.onclick = (e) => {
    e.stopPropagation();
    if (!armed) { armed = true; btn.classList.add("armed");
      btn.textContent = arming + " — click again"; t = setT(disarm, armMs); return; }  // ARM ONLY
    disarm(); onFire();                                                                 // 2nd click FIRES
  };
  return btn;
}

// ── The architecture profile, rendered (Part 2, W-CRAP). The typed profile made visible:
// the reconstructed status prominent; each field's summary as prose at glance; the evidence
// (store sources + measured observation) behind a <details> door, never the foreground; the
// two confirmed-corrected fields marked as his. Plain register; every block wraps (no h-scroll).
function renderArchitectureProfile(ap) {
  const bits = [];
  const st = ap.reconstructed ? " dk-arch-reco" : "";
  bits.push("<div class='dk-arch-status" + st + "'>" + esc(ap.status || "status unstated") + "</div>");
  bits.push("<div class='dk-arch-head'>" + esc(ap.title || "paper architecture profile") +
    (ap.version ? " · <span class='dk-arch-ver'>" + esc(ap.version) + "</span>" : "") + "</div>");
  if (ap.his_correction_count) {
    bits.push("<div class='dk-arch-lede'>" + esc(String(ap.his_correction_count)) +
      " field" + (ap.his_correction_count === 1 ? "" : "s") +
      " he has already corrected are marked HIS; the rest are the reconstruction awaiting his confirmation.</div>");
  }
  for (const f of (ap.fields || [])) {
    const ev = f.evidence || {};
    const srcs = ev.sources || [];
    const nEv = srcs.length + (ev.observation ? 1 : 0);
    bits.push(
      "<div class='dk-arch-field" + (f.his ? " dk-arch-his-field" : "") + "'>" +
        "<div class='dk-arch-fname'>" + esc(f.name || f.key || "") +
          (f.his ? "<span class='dk-arch-his'>HIS · confirmed-corrected</span>" : "") + "</div>" +
        "<div class='dk-arch-summary'>" + esc(f.summary || "") + "</div>" +
        (nEv ?
          "<details class='dk-arch-ev'><summary>the evidence — " +
            esc(String(srcs.length)) + " store source" + (srcs.length === 1 ? "" : "s") +
            (ev.observation ? " + the measured observation" : "") + "</summary>" +
            (srcs.length ? "<div class='dk-arch-ev-src'>" + esc(srcs.join("\n")) + "</div>" : "") +
            (ev.observation ? "<div class='dk-arch-ev-obs'>" + esc(ev.observation) + "</div>" : "") +
          "</details>" : "") +
      "</div>");
  }
  // the secondary blocks — who consumes it, what it was derived from, the stated gaps —
  // each a door, collapsed at rest (the field prose is the glance; these are the footing).
  const doorList = (title, rows) => rows && rows.length ?
    "<details class='dk-arch-ev'><summary>" + esc(title) + " (" + rows.length + ")</summary>" +
      "<div class='dk-arch-ev-src'>" + esc(rows.join("\n")) + "</div></details>" : "";
  bits.push(doorList("who this is typed for",
    (ap.consumes || []).map((c) => (c.stage || "") + " — " + (c.use || ""))));
  bits.push(doorList("derived from",
    (ap.derived_from || []).map((d) => (d.source || "") + " (" + (d.scope || "") + ")")));
  const au = ap.authorship || {};
  bits.push(doorList("authorship — first-author papers this speaks for",
    (au.first_author_lead || [])));
  bits.push(doorList("gaps, not hidden",
    (ap.gaps || []).map((g) => (g.id || "") + " — " + (g.note || ""))));
  return "<div class='dk-arch'>" + bits.join("") + "</div>";
}

// ── ZONE 1 — CONTEXT: render the full renderable referent, inline. Never a truncation:
// a source document (heading + verbatim body), the exact ledger row, the node's manuscript
// prose, or — where no richer referent is wired — the row's own record, plainly. ──────────
function renderReferent(ref) {
  if (!ref || (ref.error && !ref.ledger_row && !ref.source_doc)) {
    return "<div class='dk-absent'>" + esc((ref && ref.error) || "no referent for this decision") + "</div>";
  }
  const parts = [];
  // FINDING 6 — anchor the context: lead with the finding's own text (the note body / the
  // plan directive), then the passage he marked, then the manuscript prose, then the source
  // doc as the EXCERPT around the anchor (the whole body behind an expand door). The reader
  // no longer hunts an 18KB dump for the paragraph the ruling concerns.
  if (ref.intent_directive) {
    parts.push("<div class='dk-ref-k'>the plan directive you're ruling on</div>" +
      "<div class='dk-ref-row dk-ref-lead'>" + esc(ref.intent_directive) + "</div>");
  }
  if (ref.finding_text && ref.finding_text !== ref.intent_directive) {
    parts.push("<div class='dk-ref-k'>" + (ref.intent_directive ? "its note" : "the finding you're ruling on") +
      "</div><div class='dk-ref-row dk-ref-lead'>" + esc(ref.finding_text) + "</div>");
  }
  if (ref.marked_passage) {
    parts.push("<div class='dk-ref-k'>the passage he marked</div>" +
      "<div class='dk-ref-row dk-ref-mark'>" + esc(ref.marked_passage) + "</div>");
  }
  if (ref.node_text) {
    parts.push("<div class='dk-ref-k'>the prose this node concerns</div>" +
      "<div class='dk-ref-row'>" + esc(ref.node_text) + "</div>");
  }
  const sd = ref.source_doc;
  if (sd && (sd.body || sd.heading)) {
    const ex = sd.excerpt || null;
    const excerptText = ex ? ex.text : (sd.body || "");
    const anchoredNote = ex && ex.anchored ? " — anchored to this finding"
      : (sd && sd.resolved === false ? " — the latest review document (not anchored to this finding)" : "");
    parts.push("<div class='dk-ref-doc'>" +
      (sd.heading ? "<div class='dk-ref-heading'>" + esc(sd.heading) + esc(anchoredNote) + "</div>" : "") +
      (sd.path ? "<div class='dk-ref-path'>" + esc(sd.path) + "</div>" : "") +
      "<div class='dk-ref-body'>" + esc(excerptText) + "</div>" +
      // the WHOLE document rides behind an expand door — present without dominating (finding 6).
      ((ex && ex.whole) ? "<details class='dk-ref-whole'><summary>the whole document</summary>" +
        "<div class='dk-ref-body'>" + esc(sd.body || "") + "</div></details>" : "") +
      "</div>");
  }
  if (ref.ledger_row) {
    // the exact ledger row rides at AUDIT depth (a door, not the foreground): it carries the
    // raw id + the annotation rects — noise above the finding's substance (the register law).
    parts.push("<details class='dk-audit dk-ref-whole'><summary>the raw ledger row (audit)</summary>" +
      "<div class='dk-ref-row'>" + esc(JSON.stringify(ref.ledger_row, null, 2)) + "</div></details>");
  }
  // FINDING 1 — the FULL dream-lift proposal, composed IN the cockpit so authorize/refuse is
  // decide-in-seconds: the coherence essence leads, the region + members + judgment follow.
  if (ref.lift) {
    const L = ref.lift;
    parts.push("<div class='dk-ref-doc'>" +
      "<div class='dk-ref-heading'>" + esc(L.essence || L.slug || "a proposed coarse node") + "</div>" +
      (L.region ? "<div class='dk-ref-path'>region · " + esc(L.region) + "</div>" : "") +
      "<div class='dk-ref-body'>" +
        esc((L.coherent ? "a coherent lift" : "an incoherent proposal") +
            " — proposed as " + (L.slug || "?") +
            (L.members ? " over " + L.members.length + " member" + (L.members.length === 1 ? "" : "s") : "")) +
      "</div></div>");
    if (L.why) parts.push("<div class='dk-ref-k'>why it coheres</div><div class='dk-ref-row'>" + esc(L.why) + "</div>");
    if (L.parent_hint) parts.push("<div class='dk-ref-k'>where it belongs</div><div class='dk-ref-row'>" + esc(L.parent_hint) + "</div>");
    if (Array.isArray(L.members) && L.members.length) {
      parts.push("<div class='dk-ref-k'>the members it lifts (" + L.members.length + ")</div>" +
        "<div class='dk-ref-row'>" + esc(L.members.join("\n")) + "</div>");
    }
  }
  // FINDING 2 — the open friction's live record (kind/node + the friction body, its owning
  // surface, the proposal it carries), so a resolve reads what it resolves.
  if (ref.friction) {
    const fr = ref.friction;
    const rk = (k, val) => val ? "<div class='dk-ref-k'>" + esc(k) + "</div>" +
      "<div class='dk-ref-row'>" + esc(val) + "</div>" : "";
    parts.push("<div class='dk-ref-doc'>" +
      "<div class='dk-ref-heading'>" + esc((fr.kind || "friction") + (fr.node ? " · " + fr.node : "")) + "</div>" +
      (ref.surface ? "<div class='dk-ref-path'>on · " + esc(ref.surface) + "</div>" : "") +
      (fr.value ? "<div class='dk-ref-body'>" + esc(fr.value) + "</div>" : "") + "</div>");
    parts.push(rk("the proposed fix", fr.proposal));
    parts.push(rk("cost of leaving it", fr.cost));
    parts.push(rk("owning layer", fr.owning_layer));
    parts.push(rk("target", fr.target));
  }
  // FINDING 2 — the recurrence cluster's member witnesses under the shared root: what one
  // evidence-carrying resolve-cluster retires, listed so the whole set is visible.
  if (ref.cluster) {
    const cl = ref.cluster;
    const ms = cl.members || [];
    parts.push("<div class='dk-ref-doc'>" +
      "<div class='dk-ref-heading'>" + esc(cl.heading || "a recurring root") + "</div>" +
      "<div class='dk-ref-body'>" + esc(ms.length + " witness" + (ms.length === 1 ? "" : "es") +
        " share this recurring root — one evidence-carrying resolve retires them all.") + "</div></div>");
    if (ms.length) {
      parts.push("<div class='dk-ref-k'>the witnesses</div><div class='dk-ref-row'>" +
        esc(ms.map((m) => (m.node ? m.node + " — " : "") + (m.value || "") +
          (m.surface ? "  (" + m.surface + ")" : "")).join("\n")) + "</div>");
    }
  }
  // FINDING 2 — the pending holdout prediction: the banked note + session context lead, the
  // mechanical checks it will run are listed, behavioral claims stay IDS-ONLY (the covenant).
  if (ref.holdout) {
    const ho = ref.holdout;
    parts.push("<div class='dk-ref-doc'>" +
      "<div class='dk-ref-heading'>holdout prediction — pending scoring</div>" +
      (ho.note ? "<div class='dk-ref-body'>" + esc(ho.note) + "</div>" : "") + "</div>");
    if (ho.session) parts.push("<div class='dk-ref-k'>the holdout he banked</div><div class='dk-ref-row'>" + esc(ho.session) + "</div>");
    if (Array.isArray(ho.mechanical) && ho.mechanical.length) {
      parts.push("<div class='dk-ref-k'>the mechanical checks it will run (" + ho.mechanical.length + ")</div>" +
        "<div class='dk-ref-row'>" + esc(ho.mechanical.map((m) => m.id + " → expect " + (m.expect || "?")).join("\n")) + "</div>");
    }
    if (ho.behavioral_n) {
      parts.push("<div class='dk-ref-k'>behavioral claims — ids only (reading them early breaks your blindness)</div>" +
        "<div class='dk-ref-row'>" + esc((ho.behavioral_ids || []).join("\n")) + "</div>");
    }
  }
  if (ref.work_order) {
    const w = ref.work_order;
    // REFERENTS WHOLE (E3 · P4): the work-order body rendered as prose — what / why / fix /
    // blocks in full sentences, never a truncated one-liner and never raw JSON at the ruling.
    const wk = (k, val) => val ? "<div class='dk-ref-k'>" + esc(k) + "</div>" +
      "<div class='dk-ref-row'>" + esc(val) + "</div>" : "";
    parts.push("<div class='dk-ref-doc'>" +
      "<div class='dk-ref-heading'>" + esc((w.action || "work-order") + " · " + (w.corpus || "")) + "</div>" +
      (w.what ? "<div class='dk-ref-body'>" + esc(w.what) + "</div>" : "") +
      // FINDING 7a — the BANKED status where the consume decision is made (not a hover title):
      // a work-order is model-heavy work banked for a later machine session, never his hand now.
      "<div class='dk-ref-mark'>" + esc("[" + (w.cost_class || "model-heavy") +
        "] banked for a later machine session to run — nothing here needs your hand now.") + "</div>" +
      "</div>");
    parts.push(wk("why", w.why));
    parts.push(wk("fix", w.fix));
    parts.push(wk("blocks", Array.isArray(w.blocks) ? w.blocks.join("\n") : w.blocks));
    parts.push(wk("blocked by", Array.isArray(w.blocked_by) ? w.blocked_by.join("\n") : w.blocked_by));
    parts.push(wk("cost", w.cost_class));
  }
  // The profile made visible (Part 2, W-CRAP): the confirm-architecture-profile order's
  // referent opens the rendered profile — his charge "how am I supposed to see this
  // profile". Composed per the composition law: each field's summary is the prose at
  // glance; the evidence rides behind a door (<details>); the confirmed-corrected fields
  // are marked as his; the reconstructed status is prominent. No horizontal overflow.
  if (ref.architecture_profile && !ref.architecture_profile.error) {
    parts.push(renderArchitectureProfile(ref.architecture_profile));
  } else if (ref.architecture_profile && ref.architecture_profile.error) {
    parts.push("<div class='dk-absent'>" + esc(ref.architecture_profile.error) + "</div>");
  }
  // REFERENTS WHOLE (E3 · P4): the FULL author-fork — title, trigger/context, and its
  // evidence refs — rendered as prose, never ``{}`` and never a title truncated at 80.
  if (ref.fork) {
    const f = ref.fork;
    parts.push("<div class='dk-ref-doc'>" +
      "<div class='dk-ref-heading'>" + esc(String(f.title || f.id || "").replace(/\*\*/g, "")) + "</div>" +
      (f.context || f.trigger ? "<div class='dk-ref-body'>" + esc(f.context || f.trigger) + "</div>" : "") +
      "</div>");
    if (Array.isArray(f.refs) && f.refs.length) {
      parts.push("<div class='dk-ref-k'>the evidence refs</div><div class='dk-ref-row'>" +
        esc(f.refs.join("\n")) + "</div>");
    }
    if (f.opened || f.recurrence) {
      parts.push("<div class='dk-ref-k'>provenance</div><div class='dk-ref-row'>" +
        esc([f.opened ? "opened " + f.opened : "", f.recurrence ? "recurrence " + f.recurrence : ""]
          .filter(Boolean).join(" · ")) + "</div>");
    }
  }
  if (ref.release_state) {
    parts.push("<div class='dk-ref-k'>the release state</div><div class='dk-ref-row'>" +
      esc(JSON.stringify(ref.release_state, null, 2)) + "</div>");
  }
  // the proxy adjudicator's OWN output, surfaced whole — the question it ruled on, its
  // ruling, the reasoning/evidence it stood on, its confidence + when it banked. This is
  // the context that makes confirm/amend/reject a decide-in-seconds call (the text law).
  if (ref.proxy_verdict) {
    const v = ref.proxy_verdict;
    const kv = (k, val) => val ? "<div class='dk-ref-k'>" + esc(k) + "</div>" +
      "<div class='dk-ref-row'>" + esc(val) + "</div>" : "";
    parts.push("<div class='dk-ref-doc'>" +
      (v.question ? "<div class='dk-ref-heading'>" + esc(v.question) + "</div>" : "") +
      (v.ruling ? "<div class='dk-ref-body'>the proxy ruled: " + esc(v.ruling) + "</div>" : "") +
      "</div>");
    // FINDING 7b — CONFIDENCE, COMPOSED: the stored token is often "genuinely-his" (a
    // provenance marker, not a confidence). Compose it to plain words; show a real
    // confidence level as a level; suppress the line when neither (never a placeholder
    // masquerading as a confidence in the confirm/reject call).
    const cf = String(v.confidence == null ? "" : v.confidence).trim().toLowerCase();
    if (cf === "genuinely-his" || cf === "genuinely his") {
      parts.push("<div class='dk-ref-row dk-ref-lead'>banked as a genuinely his ruling — the proxy stood in for his own call.</div>");
    } else if (/^(high|medium|low)$/.test(cf) || /^0?\.\d+$/.test(cf) || /^\d+%$/.test(cf)) {
      parts.push(kv("confidence", v.confidence));
    }
    parts.push(kv("the reasoning", v.reasoning || v.rationale || v.why));
    if (Array.isArray(v.evidence) && v.evidence.length) {
      parts.push("<div class='dk-ref-k'>the evidence it stood on</div><div class='dk-ref-row'>" +
        esc(v.evidence.join("\n")) + "</div>");
    }
    parts.push(kv("banked", v.date));
  }
  if (!parts.length && ref.record) {
    parts.push("<div class='dk-ref-row'>" + esc(JSON.stringify(ref.record, null, 2)) + "</div>");
    if (ref.note) parts.push("<div class='dk-absent'>" + esc(ref.note) + "</div>");
  }
  return parts.join("") || "<div class='dk-absent'>no referent for this decision</div>";
}

// ── ZONE 2 — CONSEQUENCES ────────────────────────────────────────────────────────────────
function renderConsequences(verbs, consequences) {
  const cq = consequences || {};
  const rows = (verbs || []).filter((v) => cq[v]).map((v) =>
    "<div class='dk-conseq'><span class='cv'>" + esc(v) + "</span><span class='cw'>" +
    esc(cq[v]) + "</span></div>").join("");
  return rows || "<div class='dk-absent'>no consequence model yet for this class</div>";
}

// ── ZONE 4 — DEEP-LINKS ──────────────────────────────────────────────────────────────────
// FINDING 7d — the absence stated in WORDS the class earns: a project-scoped decision lands on
// its manuscript; an engine-wide author-fork names no single spine surface (it is ruled here,
// on the register), so its cockpit says THAT instead of a bare "no spine location".
function deeplinksAbsence(row) {
  const cls = (row && row.class) || "";
  if (cls === "forks")
    return "this author-fork names no single manuscript location — it is ruled here, on the register (OPEN_STACK), not on a spine surface.";
  return "no spine location for this decision — it is decided here, in the cockpit.";
}
function renderDeepLinks(deeplinks, row) {
  const dl = (deeplinks || []).filter((d) => d && d.href);
  if (!dl.length) return "<div class='dk-absent'>" + esc(deeplinksAbsence(row)) + "</div>";
  return dl.map((d) => "<a href='" + esc(d.href) + "'>" + esc(d.label || d.href) + " →</a>").join("");
}

// ── THE COCKPIT — the four zones, in place. A SHARED renderer: /desk and /artefact both call
// it. opts.doFire(verb) does the network (the door differs per surface); opts.loadReferent()
// fetches the CONTEXT (or returns a pre-loaded object); opts.consequences + opts.deeplinks
// feed zones 2 + 4. Every zone renders, with a declared absence where no model exists. ───────
export function renderCockpit(host, opts) {
  const row = opts.row || {};
  const verbs = row.verbs || [];
  host.innerHTML =
    "<div class='dk-cockpit'>" +
      "<div class='dk-zone zone-context'><h4>context — the referent</h4>" +
        "<div class='dk-ctx-body'><div class='dk-ref-loading'>loading the full referent…</div></div></div>" +
      "<div class='dk-zone zone-consequences'><h4>consequences</h4>" +
        "<div class='dk-conseq-body'>" + renderConsequences(verbs, opts.consequences) + "</div></div>" +
      "<div class='dk-zone dk-zone-full zone-tools'><h4>tools</h4>" +
        "<div class='dk-tools'></div><div class='dk-result' style='display:none'></div></div>" +
      "<div class='dk-zone dk-zone-full zone-deeplinks'><h4>deep-links — the spine location</h4>" +
        "<div class='dk-links'>" + renderDeepLinks(row.deeplinks, row) + "</div></div>" +
    "</div>";

  // ZONE 1 — fetch the full referent (lazy) and render it inline (never a truncation).
  const ctx = $(".dk-ctx-body", host);
  Promise.resolve()
    .then(() => (opts.loadReferent ? opts.loadReferent() : null))
    .then((ref) => { ctx.innerHTML = renderReferent(ref); })
    .catch((e) => { ctx.innerHTML = "<div class='dk-absent'>referent unavailable: " + esc((e && e.message) || e) + "</div>"; });

  // ZONE 3 — the tools: every verb inline, arm-to-fire on destructive.
  const tools = $(".dk-tools", host);
  const result = $(".dk-result", host);
  for (const verb of verbs) tools.appendChild(verbButton(row, verb, opts, result));
}

// the batch-ratify footgun (E3): desk.py reconstructed evolution_consumer.apply_plan_
// proposals — it has NO per-id target, it batch-applies EVERY open plan-op intent for
// the corpus in one call. Since the door genuinely cannot fire one id, "ratify" must
// NAME every sibling id it will actually fire, both resting and while armed — never a
// per-row face on a batch door. ``row.ratify_all_ids`` rides the read-model (desk.py),
// display-only (never sent — ``fireDeskVerb`` posts only ``row.fields``).
function ratifyAllIds(row) {
  return (row.class === "plan-ops" && Array.isArray(row.ratify_all_ids) && row.ratify_all_ids.length)
    ? row.ratify_all_ids : null;
}
function restVerbLabel(row, verb) {
  const ids = verb === "ratify" ? ratifyAllIds(row) : null;
  if (!ids) return verb;
  // the resting face NAMES what it fires (appearance predicts behaviour): a batch door
  // that applies every OPEN plan intent says so at rest, matching the armed label's words.
  return "ratify ALL " + ids.length + " open intent" + (ids.length === 1 ? "" : "s");
}
function armVerbLabel(row, verb) {
  const ids = verb === "ratify" ? ratifyAllIds(row) : null;
  if (!ids) return DESTRUCTIVE[verb];
  return "ratify ALL " + ids.length + " open intent" + (ids.length === 1 ? "" : "s") +
    ": " + ids.join(", ");
}

// ── the ruling composer (PV the-ruling-needs-a-composer): an authoring verb offers a field
// for his words, not a bare confirm. The fork's question is restated as the prompt; where the
// question is genuinely binary/enumerable, quick-choice chips sit ABOVE the text (choosing one
// pre-fills, his text extends); the ruling field is REQUIRED (non-empty guard); commentary is
// optional. The armed fire banks {ruling, choice, commentary, by} through the existing door,
// and the banked row's id echoes back in place. Same shape for bank-ruling / contest-ruling /
// (proxy) reject — the labels differ, the authoring field does not. ─────────────────────────
function authoringConfig(row, verb) {
  if (verb === "reject")
    return { lead: "the proxy ruled:", question: String(row.title || "").trim(),
             fieldLabel: "your objection — why you reject this ruling",
             fire: "reject — bank the objection" };
  if (verb === "contest-ruling")
    return { lead: "this fork asks:", question: forkQuestion(row),
             fieldLabel: "your objection to this fork",
             fire: "contest — bank the objection" };
  return { lead: "this fork asks:", question: forkQuestion(row),
           fieldLabel: "your ruling on this fork", fire: "bank the ruling" };
}
function forkQuestion(row) {
  const t = String(row.title || "").replace(/\*\*/g, "").trim();
  const c = String(row.context || "").trim();
  return c && c !== t ? (t + " — " + c) : t;
}
// quick-choice chips only where the question is genuinely binary/enumerable (a "does it X"
// landing question → yes/no; an "A vs B" question → the two poles). Otherwise none — a chip
// forced onto an open question is a false affordance.
function quickChoices(question) {
  const q = String(question || "");
  let m = q.match(/\bdoes it\b/i);
  if (m) return ["yes — it does", "no — it does not"];
  m = q.match(/([A-Za-z][\w-]*(?:\s[\w-]+)?)\s+vs\.?\s+([A-Za-z][\w-]*(?:\s[\w-]+)?)/i);
  if (m) return [m[1].trim(), m[2].trim()];
  return [];
}
function rulingComposerButton(row, verb, opts, result) {
  const cfg = authoringConfig(row, verb);
  const wrap = document.createElement("span");
  wrap.className = "dk-act-authwrap";
  const trigger = document.createElement("button");
  trigger.type = "button"; trigger.className = "dk-act compose dk-act-authoring";
  trigger.dataset.verb = verb;
  trigger.textContent = verb + " — compose" + (verb === "bank-ruling" ? " your ruling" : " your objection");
  trigger.title = "an authoring act: this opens a field for your words — a bare confirm never banks an empty ruling";

  const panel = document.createElement("div");
  panel.className = "dk-ruling-composer"; panel.style.display = "none";
  const prompt = document.createElement("div");
  prompt.className = "dk-ruling-prompt";
  prompt.innerHTML = "<span class='dk-ruling-lead'>" + esc(cfg.lead) + "</span> " + esc(cfg.question || "(the question is in the referent beside this)");
  panel.appendChild(prompt);

  let choice = "";
  const choices = quickChoices(cfg.question);
  const text = document.createElement("textarea");
  text.className = "dk-ruling-text"; text.rows = 3;
  text.placeholder = cfg.fieldLabel + " (required — the substance of your ruling)";
  if (choices.length) {
    const chipRow = document.createElement("div");
    chipRow.className = "dk-ruling-chips";
    for (const ch of choices) {
      const chip = document.createElement("button");
      chip.type = "button"; chip.className = "dk-ruling-chip"; chip.textContent = ch;
      chip.onclick = (e) => {
        e.stopPropagation();
        choice = ch;
        [...chipRow.children].forEach((x) => x.classList.toggle("sel", x === chip));
        if (!text.value.trim()) { text.value = ch; }   // pre-fill; his text can extend
        text.classList.remove("bad"); text.focus();
      };
      chipRow.appendChild(chip);
    }
    panel.appendChild(chipRow);
  }
  panel.appendChild(text);
  const commentary = document.createElement("input");
  commentary.type = "text"; commentary.className = "dk-ruling-commentary";
  commentary.placeholder = "commentary (optional)";
  panel.appendChild(commentary);

  const fireBtn = document.createElement("button");
  fireBtn.type = "button"; fireBtn.className = "dk-act destructive dk-ruling-fire";
  fireBtn.textContent = cfg.fire;
  const cancel = document.createElement("button");
  cancel.type = "button"; cancel.className = "dk-act dk-ruling-cancel"; cancel.textContent = "cancel";
  const btns = document.createElement("div");
  btns.className = "dk-ruling-btns"; btns.appendChild(fireBtn); btns.appendChild(cancel);
  panel.appendChild(btns);

  trigger.onclick = (e) => { e.stopPropagation(); panel.style.display = ""; trigger.style.display = "none"; text.focus(); };
  cancel.onclick = (e) => { e.stopPropagation(); panel.style.display = "none"; trigger.style.display = ""; };
  fireBtn.onclick = (e) => {
    e.stopPropagation();
    const ruling = text.value.trim();
    if (!ruling) { text.classList.add("bad"); text.focus(); return; }   // NO empty authored record
    doFire(row, verb, fireBtn, opts, result, { ruling, choice, commentary: commentary.value.trim() });
  };
  wrap.appendChild(trigger); wrap.appendChild(panel);
  return wrap;
}

// the evidence compose path (E3 — the consume dead-end): a verb whose executor REQUIRES
// evidence (consume/resolve/resolve-cluster) never fires evidence_refs=[]. The button opens
// an inline editor; the chair attaches refs (comma-separated), and only THEN does the door
// fire, carrying evidence_refs. Deferred/dead executors never reach here.
function evidenceButton(row, verb, opts, result) {
  const wrap = document.createElement("span");
  wrap.className = "dk-act-evwrap";
  const b = document.createElement("button");
  b.type = "button"; b.className = "dk-act compose"; b.dataset.verb = verb;
  b.textContent = verb + " — attach evidence";
  b.title = "needs evidence — the store refuses an evidence-less " + verb;
  const editor = document.createElement("span");
  editor.className = "dk-ev-editor"; editor.style.display = "none";
  const input = document.createElement("input");
  input.type = "text"; input.className = "dk-ev-input";
  input.placeholder = "evidence — a commit / dir / round ref (comma-separated)";
  const fireBtn = document.createElement("button");
  fireBtn.type = "button"; fireBtn.className = "dk-act destructive"; fireBtn.textContent = verb + " →";
  const cancel = document.createElement("button");
  cancel.type = "button"; cancel.className = "dk-act"; cancel.textContent = "cancel";
  editor.appendChild(input); editor.appendChild(fireBtn); editor.appendChild(cancel);
  b.onclick = (e) => { e.stopPropagation(); editor.style.display = ""; b.style.display = "none"; input.focus(); };
  cancel.onclick = (e) => { e.stopPropagation(); editor.style.display = "none"; b.style.display = ""; };
  fireBtn.onclick = (e) => {
    e.stopPropagation();
    const refs = input.value.split(",").map((s) => s.trim()).filter(Boolean);
    if (!refs.length) { input.classList.add("bad"); input.focus(); return; }
    doFire(row, verb, fireBtn, opts, result, { evidence_refs: refs });
  };
  wrap.appendChild(b); wrap.appendChild(editor);
  return wrap;
}

// the standing machine-waiting reason a not-his (engine) verb wears — no live fire face,
// so a "read-only exhaust" row never carries a write button (finding 3). The one hymn token.
const MACHINE_WAITING_VERB = "runs at the next machine session — nothing here needs your hand";

function verbButton(row, verb, opts, result) {
  const deferredEarly = opts.deferred && opts.deferred[verb];
  // FINDING 3 — MACHINE-OWED rows are read-only exhaust for him: EVERY verb renders as quiet
  // text naming that it runs mechanically at the next session, never a live write button.
  // (The act door stays live for a direct machine call — this governs only what HE is shown.)
  if (opts.machineOwed) {
    const span = document.createElement("span");
    span.className = "dk-absent dk-act-deferred dk-act-machine";
    span.textContent = verb + " — " + (deferredEarly || MACHINE_WAITING_VERB);
    return span;
  }
  // AUTHORING (PV the-ruling-needs-a-composer): a verb that banks HIS WORDS opens a composer
  // with a REQUIRED ruling field, never a bare confirm/arm that could bank an empty record.
  if (!deferredEarly && AUTHORING.has(verb)) return rulingComposerButton(row, verb, opts, result);
  // DECORATIVE VERBS first (E3, P3): a deferred verb is quiet text naming its reason — a
  // non-button, never a live face (checked before COMPOSE so a deferred compose verb like
  // ``amend`` still renders as its plain compose link, never a dead button).
  if (!deferredEarly && EVIDENCE.has(verb)) return evidenceButton(row, verb, opts, result);
  if (COMPOSE.has(verb)) {
    const a = document.createElement("a");
    a.className = "dk-act compose"; a.textContent = verb;
    a.href = (opts.composeHref ? opts.composeHref(verb) : row.href) ||
             ("/artefact?corpus=" + encodeURIComponent(row.project || ""));
    a.title = "needs an authored choice — opens the working surface to compose";
    return a;
  }
  // DECORATIVE VERBS (E3, P3 — a verb is live or it is absent): a verb the backend
  // names DEFERRED (its door 422s "not wired this wave") renders as quiet text naming
  // the stated reason, never a button wearing a live face. ``opts.deferred`` rides the
  // stratum's own table (desk.py's ``_DEFERRED_VERBS`` — ONE producer, no front-end copy).
  const deferredReason = opts.deferred && opts.deferred[verb];
  if (deferredReason) {
    const span = document.createElement("span");
    span.className = "dk-absent dk-act-deferred";
    span.textContent = verb + " — " + deferredReason;
    return span;
  }
  const b = document.createElement("button");
  const destructive = Object.prototype.hasOwnProperty.call(DESTRUCTIVE, verb);
  b.className = "dk-act" + (destructive ? " destructive" : "");
  b.type = "button"; b.dataset.verb = verb;
  const restLabel = restVerbLabel(row, verb);
  b.textContent = restLabel;
  const fire = () => doFire(row, verb, b, opts, result);
  if (destructive) armToFire(b, restLabel, armVerbLabel(row, verb), fire, opts.armOpts);
  else b.onclick = (e) => { e.stopPropagation(); fire(); };
  return b;
}

// ── The echo law (the 2026-07-23 echo-law ruling) ─────────────────────────
// His ruling: "not enough live feedback when I submit … no sense where it's gone and what's
// happened … the ticker doesn't go down." So every authoring act on /desk must echo in place,
// without a reload: name the minted record + the ledger it went to, in plain words, AT the item
// (the cockpit's result node, under the fired button) — never a corner toast. ONE composer over
// the POST /desk/act response, applied UNIFORMLY to every verb (the law is per-act, not per-verb).
// The response is heterogeneous (forks/lifts/proxy carry ``record.id``; ratify carries ``applied``;
// resolve carries ``ledger``+``resolution``; clusters carry ``resolved``; holdout ``archive``), so
// the composer reads WHICHEVER shape rode back and always lands a truthful line — an unknown shape
// degrades to the disposition + destination, never a silent nothing.

// the disposition WORD per verb — the executor names it on forks/lifts (``disposition``); this is
// the fallback for verbs whose executor does not. Display copy (like DESTRUCTIVE), not data.
const ECHO_DISPOSITION = {
  "bank-ruling": "banked", "contest-ruling": "contested", "reject": "objection banked",
  "confirm": "confirmed", "authorize": "authorized", "refuse": "refused",
  "resolve": "resolved", "resolve-cluster": "resolved the cluster", "consume": "consumed",
  "ratify": "applied", "score": "scored", "dismiss": "dismissed", "defer": "deferred",
  "widen": "widened", "revoke": "revoked", "revoke-intent": "revoked", "comment": "commented",
  "route-conceptric": "routed", "route-plan": "routed", "calibrate": "calibrated",
  "amend": "amended", "edit-in-place": "spliced",
};
// the plain-words ledger PHRASE per class (the "→ the fork ledger" the arrow points at). The PATH
// itself always rides the server (``ledger``/``archive``) or the /desk read-model's own ``store``
// string (``opts.storeLabel``) — never a hardcoded path here; this map is only the human phrase.
const ECHO_LEDGER = {
  "forks": "the author-fork ledger", "lifts": "the lift-rulings ledger",
  "proxy-drafts": "the proxy-verdicts ledger", "open-frictions": "the friction ledger",
  "recurrence-clusters": "the friction ledgers", "work-orders": "the work-order ledger",
  "adjudications": "the feedback ledger", "plan-ops": "the feedback ledger",
  "holdout": "the holdout archive",
};

// read the minted record id + a batch summary + the destination out of whatever shape returned.
function echoFacts(out, row, verb, opts) {
  const data = (out && out.data) || {};
  const cls = (row && row.class) || data.class || "";
  const rec = data.record || data.resolution || null;
  const id = (rec && (rec.id || rec.record_id)) || data.id ||
             (typeof data.resolved === "string" ? data.resolved : "") || data.order || "";
  const batch = Array.isArray(data.applied) ? { n: data.applied.length, noun: "intent" }
    : Array.isArray(data.resolved) ? { n: data.resolved.length, noun: "witness" }
    : (typeof data.n === "number" ? { n: data.n, noun: "record" } : null);
  const disposition = (data.disposition && String(data.disposition).trim()) ||
                      ECHO_DISPOSITION[verb] || "recorded";
  // the destination PATH: a clean server path first (ledger/archive), then the read-model store.
  const dest = data.ledger || data.archive || (opts && opts.storeLabel) || (row && row.store) || "";
  return { id, batch, disposition, dest, ledgerPhrase: ECHO_LEDGER[cls] || "its ledger",
           idempotent: !!data.idempotent };
}
// the success echo, hymn-styled, rendered AT the item (the cockpit's result node).
function echoSuccessHTML(out, row, verb, opts) {
  const f = echoFacts(out, row, verb, opts);
  const head = f.idempotent
    ? "already recorded — no change"
    : (esc(f.disposition) + " → <span class='dk-echo-ledger'>" + esc(f.ledgerPhrase) + "</span>");
  const idBit = f.batch
    ? esc(f.batch.n + " " + f.batch.noun + (f.batch.n === 1 ? "" : "s") + " " + f.disposition)
    : (f.id ? "<span class='dk-echo-id'>" + esc(f.id) + "</span>" : "");
  const destBit = f.dest ? "<span class='dk-echo-dest'>" + esc(f.dest) + "</span>" : "";
  const prov = [idBit, destBit].filter(Boolean).join(" · ");
  return "<div class='dk-echo-head'><span class='dk-echo-tick'>✓</span> " + head + "</div>" +
    (prov ? "<div class='dk-echo-prov'>" + prov + "</div>" : "") +
    "<div class='dk-echo-back'>the desk tally has moved — ← back to the brief to see it</div>";
}
// the failure echo: the server's OWN message, at the item, never a silent nothing (E-law · 4).
function echoFailHTML(out, verb) {
  let msg = (out && out.text) || "the door refused this act";
  // store.fetchJSON throws "fetchJSON POST <url> → 422: <server msg>" — surface the human part.
  const m = String(msg).match(/→\s*\d+:\s*(.*)$/);
  if (m) msg = m[1];
  return "<div class='dk-echo-head'><span class='dk-echo-cross'>✗</span> " + esc(verb) +
    " refused</div><div class='dk-echo-prov'>" + esc(msg) + "</div>";
}

async function doFire(row, verb, btn, opts, result, extra) {
  btn.classList.add("busy"); btn.disabled = true;
  let out;
  try { out = await opts.doFire(verb, extra || null); }
  catch (e) { out = { ok: false, text: (e && e.message) || String(e) }; }
  btn.classList.remove("busy");
  result.style.display = "";
  if (out && out.ok) {
    // E-law · 1 — IMMEDIATELY on success: the rich echo naming the minted record + its ledger,
    // hymn-styled, at the item (``ok`` kept so the .dk-result.ok contract holds).
    result.className = "dk-result ok dk-echo";
    result.innerHTML = echoSuccessHTML(out, row, verb, opts);
    btn.disabled = true;                       // the fired button locks
    // E-law · 2 — The item moves: the fired tools collapse behind the echo (the affordance is
    // spent), and the origin row is marked leaving before the list re-renders from server truth.
    const toolsZone = btn.closest(".dk-tools"); if (toolsZone) toolsZone.classList.add("dk-spent");
    if (opts.markItemDone) opts.markItemDone(out);
    // E-law · 3 — The counts move: re-fetch + re-render every dependent count, without a reload.
    if (opts.onFired) opts.onFired(out);
  } else {
    // E-law · 4 — Failure echoes too: the server's message at the item, never a silent nothing.
    result.className = "dk-result err dk-echo";
    result.innerHTML = echoFailHTML(out, verb);
    btn.disabled = false;
  }
}

// ═══ /desk — the surface bootstrap, under the one instrument (W-DESK) ═════════════════════
// The brief-specific chrome (dkb-*) is injected here; the cockpit's own classes (.dk-cockpit
// / .dk-zone / .dk-ref-* / .dk-act / .dk-result / .dk-arch-*) live in hymn.css and are shared
// with /artefact's tray — never re-declared. Colour is a hymn var; this carries layout.
const DESK_CSS = `
.dkb-prose{font-size:14px;line-height:1.65;color:var(--ink);margin:18px 0 6px;max-width:76ch}
/* the his-glances — the genuinely-his rows the brief leads with, each a door to its cockpit */
.dkb-his{display:flex;flex-direction:column;gap:9px;margin:14px 0 4px;max-width:820px}
.dkb-glance{border:1px solid var(--edge2);border-radius:10px;background:var(--panel);padding:11px 13px;
  display:flex;flex-direction:column;gap:5px;cursor:pointer;min-width:0}
.dkb-glance:hover{border-color:var(--accent)}
.dkb-glance:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.dkb-glance.who-him{border-left:3px solid var(--accent)}
.dkb-glance.who-engine{border-left:3px solid var(--dim)}
.dkb-glance-cls{font-family:var(--mono);font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:var(--dim);font-weight:700}
.dkb-glance-g{font-size:13px;line-height:1.5;color:var(--ink)}
.dkb-glance-why{font-size:11.5px;line-height:1.5;color:var(--ink2)}
.dkb-glance-open{font-family:var(--mono);font-size:9px;color:var(--dim);border-top:1px dashed var(--edge2);padding-top:6px}
/* the count chips — one line per summonable class; the number is the filter (P2). FINDING 4:
   chips carry NO genuinely-his accent (that is the who-him glances above); the owner meaning
   rides the group divider, and the standing-queue marker is a neutral dashed edge, not accent. */
.dkb-counts{display:flex;flex-direction:column;gap:12px;margin:16px 0 6px;padding-top:12px;border-top:1px solid var(--edge2)}
.dkb-counts-group{display:flex;flex-direction:column;gap:8px}
.dkb-counts-divider{font-family:var(--mono);font-size:9.5px;text-transform:uppercase;letter-spacing:.09em;color:var(--dim);font-weight:700}
.dkb-counts-row{display:flex;flex-wrap:wrap;gap:8px}
.dkb-counts-info{font-family:var(--mono);font-size:10px;color:var(--dim)}
.dkb-count{display:inline-flex;align-items:center;gap:7px;cursor:pointer;background:var(--panel);border:1px solid var(--edge2);
  border-radius:9px;padding:7px 12px;font:inherit;color:var(--ink2);min-width:0}
.dkb-count:hover{border-color:var(--accent);color:var(--ink)}
.dkb-count:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.dkb-count.is-open{border-color:var(--keystone);color:var(--ink);box-shadow:inset 0 0 0 1px var(--keystone)}
.dkb-count.standing{border-left:3px dashed var(--edge)}
.dkb-count.zero{opacity:var(--hy-zero-dim);cursor:default}
.dkb-count .dkb-cn{font-family:var(--mono);font-weight:700;color:var(--ink);font-size:14px}
.dkb-count .dkb-clabel{font-size:11.5px}
/* the materialised zone — a class's rows, built on open, removed on close (absent at rest) */
.dkb-mat{margin-top:16px}
.dkb-mat-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:11px}
.dkb-mat-h{font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.1em;color:var(--dim);font-weight:700}
.dkb-mat-close{font-family:var(--mono);font-size:10.5px;color:var(--accent);cursor:pointer;border:1px solid var(--edge);
  border-radius:7px;padding:4px 10px;background:var(--bg)}
.dkb-mat-close:hover{border-color:var(--accent);color:var(--ink)}
.dkb-glances{display:flex;flex-direction:column;gap:9px;max-width:820px}
.dkb-more{display:inline-block;margin-top:10px;font-family:var(--mono);font-size:10.5px;color:var(--accent);
  text-decoration:none;border:1px solid var(--edge);border-radius:7px;padding:4px 10px;background:var(--panel2)}
.dkb-more:hover{border-color:var(--accent);color:var(--ink)}
.dkb-railcov{font-family:var(--mono);font-size:10.5px;color:var(--ink2);line-height:1.6}
/* the anchored referent (finding 6): the finding's own text leads, the marked passage /
   banked status stand out, the whole document rides behind an expand door — never a raw dump */
.dk-ref-lead{border-left:2px solid var(--accent);padding-left:9px}
.dk-ref-mark{border-left:2px solid var(--keystone);padding-left:9px;color:var(--ink2);font-style:italic}
.dk-ref-whole > summary{font-family:var(--mono);font-size:10.5px;color:var(--accent);cursor:pointer;padding:4px 0}
.dk-ref-whole[open] > summary{color:var(--ink2)}
/* finding 3: a machine-owed verb reads as quiet machine-waiting text, never a live face */
.dk-act-machine{display:inline-block;font-style:italic}
/* the ruling composer (an authoring verb carries a field for his words, never a bare confirm) */
.dk-act-authwrap{display:inline-flex;flex-direction:column;gap:8px;min-width:0;width:100%}
.dk-ruling-composer{display:flex;flex-direction:column;gap:9px;max-width:560px;padding:11px 12px;
  border:1px solid var(--edge2);border-left:3px solid var(--accent);border-radius:9px;background:var(--panel)}
.dk-ruling-prompt{font-size:12.5px;line-height:1.5;color:var(--ink)}
.dk-ruling-lead{font-family:var(--mono);font-size:9.5px;text-transform:uppercase;letter-spacing:.08em;color:var(--dim);font-weight:700;margin-right:5px}
.dk-ruling-chips{display:flex;flex-wrap:wrap;gap:6px}
.dk-ruling-chip{font:inherit;font-size:11px;cursor:pointer;background:var(--bg);border:1px solid var(--edge2);
  border-radius:14px;padding:4px 11px;color:var(--ink2)}
.dk-ruling-chip:hover{border-color:var(--accent);color:var(--ink)}
.dk-ruling-chip.sel{border-color:var(--accent);color:var(--ink);box-shadow:inset 0 0 0 1px var(--accent)}
.dk-ruling-text{font:inherit;font-size:12px;line-height:1.5;padding:7px 9px;border-radius:7px;resize:vertical;
  border:1px solid var(--edge2);background:var(--bg);color:var(--ink);width:100%;box-sizing:border-box}
.dk-ruling-text:focus{outline:none;border-color:var(--accent)}
.dk-ruling-text.bad{border-color:var(--bad)}
.dk-ruling-commentary{font:inherit;font-size:11.5px;padding:6px 9px;border-radius:7px;
  border:1px solid var(--edge2);background:var(--bg);color:var(--ink);width:100%;box-sizing:border-box}
.dk-ruling-commentary:focus{outline:none;border-color:var(--accent)}
.dk-ruling-btns{display:flex;gap:8px}
/* the inline evidence editor (consume/resolve attach evidence before firing) */
.dk-act-evwrap{display:inline-flex;align-items:center;gap:6px}
.dk-ev-editor{display:inline-flex;align-items:center;gap:6px;flex-wrap:wrap}
.dk-ev-input{font:inherit;font-size:11px;min-width:220px;padding:4px 8px;border-radius:6px;
  border:1px solid var(--edge2);background:var(--bg);color:var(--ink)}
.dk-ev-input:focus{outline:none;border-color:var(--accent)}
.dk-ev-input.bad{border-color:var(--bad)}
/* The echo law (the 2026-07-23 echo-law ruling): the in-place act echo — at the item, hymn-styled,
   naming the minted record + the ledger it went to; never a corner toast. .dk-result base (mono,
   spacing) lives in hymn.css; these overlay the echo block on top of it. */
.dk-echo{padding:9px 11px;border-radius:8px;border:1px solid var(--edge2);
  border-left:3px solid var(--ok);background:color-mix(in srgb,var(--ok) 8%,transparent);
  animation:dk-echo-in .18s ease-out}
.dk-echo.err{border-left-color:var(--bad);background:color-mix(in srgb,var(--bad) 8%,transparent)}
.dk-echo-head{font-size:11.5px;color:var(--ink);font-weight:640;line-height:1.5}
.dk-echo-tick{color:var(--ok);font-weight:700}
.dk-echo-cross{color:var(--bad);font-weight:700}
.dk-echo-ledger{color:var(--keystone)}
.dk-echo-prov{font-size:10.5px;color:var(--ink2);margin-top:4px;line-height:1.5;word-break:break-word}
.dk-echo-id{color:var(--accent)}
.dk-echo-dest{color:var(--dim)}
.dk-echo-back{font-size:10px;color:var(--dim);margin-top:5px}
@keyframes dk-echo-in{from{opacity:0;transform:translateY(-3px)}to{opacity:1;transform:none}}
/* The item moves: the fired tools collapse behind the echo; the origin row fades as it leaves,
   its echo remaining briefly before the list re-renders from server truth. */
.dk-tools.dk-spent{opacity:.4;pointer-events:none;filter:saturate(.4);transition:opacity .3s ease}
.dkb-glance-done{opacity:0;max-height:0;padding-top:0;padding-bottom:0;margin:0;border-width:0;
  overflow:hidden;transition:opacity .35s ease,max-height .45s ease,padding .35s ease,margin .35s ease}
`;
function injectDeskCSS() {
  if (typeof document === "undefined" || document.getElementById("dkb-components")) return;
  const st = document.createElement("style"); st.id = "dkb-components"; st.textContent = DESK_CSS;
  document.head.appendChild(st);
}

// ── module state ─────────────────────────────────────────────────────────────────────────
let BRIEF = null;              // the composed brief payload (/desk/brief)
const CLASS_CACHE = {};        // class -> /desk/class payload (rows + verbs + consequences + deferred)
let STATE = createFocusState("brief");
let BUS = null, LENS = null, REALLOC = null;
let OPEN_MAT = null;           // the materialised class chip, or null (brief base altitude)
let PINNED = null;             // {class, id, key} the pinned row, or null
const WHERE_KEY = "desk:where";

const ownerOf = (r) => (r && r.owner) || "engine";

// ═══════════════ BOOT ═══════════════
export async function initDesk() {
  injectEngineCSS(); injectDeskCSS();
  BUS = new HighlightBus(document);
  LENS = new HoverLens();
  const root = $("#eng-root");
  if (!root) return;
  REALLOC = new Reallocator(root, STATE, BUS);
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (REALLOC.pinned) closePin();
    else if (OPEN_MAT) closeMaterialised();
  });
  await load();
  // no lobby tax (B.5): a deep-link pre-pins its target on load; otherwise restore where he
  // was this session. The brief is the DEFAULT entry, never a mandatory toll on the way in.
  await applyEntry();
  if (typeof window !== "undefined" && window.HymnShell && HymnShell.setDeskBadge)
    HymnShell.setDeskBadge(((BRIEF && BRIEF.his) || []).length);
}

async function load() {
  BRIEF = await store.fetchJSON("/desk/brief", { inject: [] }).catch(() => null);
  renderBrief();
}

// ═══════════════ THE BRIEF — the resting altitude (delta-and-ask, never inventory) ═══════
function renderBrief() {
  const brief = $(".eng-brief"); if (!brief) return;
  OPEN_MAT = null;
  if (!BRIEF || BRIEF.error) {
    brief.innerHTML = "<div class='dkb-prose'>" + esc((BRIEF && BRIEF.error) || "no desk brief resolved.") + "</div>";
    return;
  }
  // The echo law (E-law · 3): the counts live in their own ``#dkb-chrome`` container, SEPARATE
  // from the materialised pane (``#dkb-mat``), so an act can re-render the tallies in place
  // (refreshBriefAfterAct) without tearing down an open class pane or the pin beneath it.
  brief.innerHTML =
    "<div id='dkb-chrome'>" + briefChromeHTML() + "</div>" +
    "<div class='dkb-mat' id='dkb-mat'></div>";
  wireBrief();
}

// the brief's count chrome (prose + his-cards + class-count chips), as HTML. Rebuilt on its own
// by refreshBriefAfterAct so the ticker moves the moment an act lands — no page reload.
function briefChromeHTML() {
  const g = (BRIEF.brief && BRIEF.brief.glance) || "";
  const his = BRIEF.his || [];
  const classes = BRIEF.classes || [];
  // FINDING 4 — one definition of his: the genuinely-his set (badge + brief prose + the
  // who-him accent) is the ``his`` glances above. The count chips are class TOTALS, grouped
  // under plain dividers — the him-owned classes are his STANDING QUEUE (summonable), the
  // engine classes await a machine session; neither wears the genuinely-his accent, so a
  // stranger never reads "228 need you now" against a badge that says "2".
  const himChips = classes.filter((c) => c.owner === "him");
  const engChips = classes.filter((c) => c.owner !== "him");
  const chipGroup = (label, arr) => arr.length
    ? "<div class='dkb-counts-group'><div class='dkb-counts-divider'>" + esc(label) + "</div>" +
      "<div class='dkb-counts-row'>" + arr.map(countChip).join("") + "</div></div>"
    : "";
  return "<div class='dkb-prose' data-role='brief-prose'>" + esc(g) + "</div>" +
    (his.length ? "<div class='dkb-his'>" + his.map(hisCard).join("") + "</div>" : "") +
    "<div class='dkb-counts'>" +
      chipGroup("your standing queue — summonable, not owed right now", himChips) +
      chipGroup("engine — awareness, waits on a machine session", engChips) +
      "<div class='dkb-counts-info'>" +
        infoTag("GET /desk/brief → desk.py — the composed what-needs-you-now; each chip's hover title names the real store it joins") +
      "</div>" +
    "</div>";
}

function hisCard(row) {
  const key = row.class + "::" + String(row.id);
  return "<div class='dkb-glance who-him' data-openrow='" + esc(key) + "' data-refclass='" + esc(row.class) +
    "' tabindex='0' role='button'>" +
    "<div class='dkb-glance-cls'>" + esc(row.class) + "</div>" +
    "<div class='dkb-glance-g'>" + esc(row.glance || row.title || "") + "</div>" +
    (row.why ? "<div class='dkb-glance-why'>" + esc(row.why) + "</div>" : "") +
    "<div class='dkb-glance-open'>open → its cockpit, in place</div></div>";
}

function countChip(c) {
  // FINDING 4: a count chip is a class TOTAL, never the genuinely-his accent — the owner is
  // carried by the group divider it sits under (standing queue vs engine awareness), so the
  // chip itself wears no "his" border. ``standing`` is a neutral grouping marker, not accent.
  const zero = !c.count, open = OPEN_MAT === c.class;
  const standing = c.owner === "him";
  const capped = (c.more || 0) > 0;
  const titleAttr = (c.store || "") + (capped
    ? (" — showing " + c.shown + " of " + c.count + "; the +" + c.more + " door opens the whole class") : "");
  return "<button type='button' class='dkb-count" + (standing ? " standing" : "") + (zero ? " zero" : "") +
    (open ? " is-open" : "") + "' data-materialize='" + esc(c.class) + "' data-refclass='" + esc(c.class) +
    "' title='" + esc(titleAttr) + "'" + (zero ? " aria-disabled='true'" : "") + ">" +
    "<span class='dkb-cn'>" + esc(c.count) + "</span>" +
    "<span class='dkb-clabel'>" + esc(c.label) + "</span></button>";
}

function wireBrief() {
  $$(".dkb-his .dkb-glance[data-openrow]").forEach((card) => wireGlance(card, () => {
    const r = (BRIEF.his || []).find((x) => (x.class + "::" + String(x.id)) === card.dataset.openrow) || {};
    return "<div class='lens-h'>" + esc(r.class || "") + " — why it needs you</div><div>" + esc(r.why || r.context || "") + "</div>";
  }, () => openRowByKey(card.dataset.openrow)));
  $$(".dkb-count[data-materialize]").forEach((chip) => {
    if (chip.getAttribute("aria-disabled")) return;
    chip.addEventListener("mouseenter", () => BUS.lit([["refclass", chip.dataset.refclass]], true));
    chip.addEventListener("mouseleave", () => BUS.clear());
    activate(chip, () => materialise(chip.dataset.materialize));
  });
}

// a glance card's hover/click wiring: hover REVEALS the lens + lights the row's referent
// CLASS chip (B.4 highlight bus); click opens the row's cockpit (REALLOCATE). One idiom for
// the his-glances and the materialised class rows alike.
function wireGlance(card, lensHTML, onOpen) {
  card.addEventListener("mouseenter", () => { LENS.show(card, lensHTML()); BUS.lit([["refclass", card.dataset.refclass]], true); });
  card.addEventListener("mouseleave", () => { LENS.hide(); BUS.clear(); });
  activate(card, () => { LENS.hide(); BUS.clear(); onOpen(); });
}

// ═══════════════ MATERIALISE — build ONE class's rows on open (E) ═════════════════════════
async function materialise(cls) {
  const mat = $("#dkb-mat");
  if (OPEN_MAT === cls) { closeMaterialised(); return (CLASS_CACHE[cls] && CLASS_CACHE[cls].rows) || []; }
  OPEN_MAT = cls; persistWhere();
  $$(".dkb-count").forEach((c) => c.classList.toggle("is-open", c.dataset.materialize === cls));
  BUS.clear();
  if (mat) mat.innerHTML = "<div class='dkb-mat-head'><span class='dkb-mat-h'>materialising " + esc(cls) + "…</span></div>";
  const d = await ensureClassMeta(cls);
  const rows = d.rows || [];
  if (!mat) return rows;
  renderMatPane(mat, cls, d, rows);
  wireMat(mat, cls, rows);
  return rows;
}

// the materialised class pane's HTML, painted into ``mat``. Extracted so an act can REPAINT it
// from server truth (refreshMaterialised) without duplicating the render (E-law · 3, one producer).
function renderMatPane(mat, cls, d, rows) {
  mat.innerHTML =
    "<div class='dkb-mat-head'><span class='dkb-mat-h'>" + esc(d.label || cls) + " · " +
      esc(d.count != null ? d.count : rows.length) + "</span>" +
      "<button type='button' class='dkb-mat-close' data-role='mat-close'>← back to the brief</button></div>" +
    (rows.length ? "<div class='dkb-glances'>" + rows.map((r) => matGlanceCard(r, cls)).join("") + "</div>"
                 : "<div class='dk-absent'>nothing open in this class.</div>") +
    (d.more_href ? "<a class='dkb-more' href='" + esc(d.more_href) + "'>+" + esc(d.more) + " beyond this door →</a>" : "");
}

// E-law · 3: after an act, if a class pane is open, invalidate its cache and REPAINT its rows +
// count from a fresh /desk/class — the acted row leaves the list (server truth), the count moves.
async function refreshMaterialised(cls) {
  const mat = $("#dkb-mat");
  if (!mat || OPEN_MAT !== cls) return;
  delete CLASS_CACHE[cls];
  const d = await ensureClassMeta(cls);
  const rows = d.rows || [];
  if (OPEN_MAT !== cls) return;                  // he closed/switched while we fetched — leave it
  renderMatPane(mat, cls, d, rows);
  wireMat(mat, cls, rows);
}

function matGlanceCard(r, cls) {
  const key = cls + "::" + String(r.id);
  const him = ownerOf(r) === "him";
  return "<div class='dkb-glance " + (him ? "who-him" : "who-engine") + "' data-openrow='" + esc(key) +
    "' data-refclass='" + esc(cls) + "' tabindex='0' role='button'>" +
    "<div class='dkb-glance-g'>" + esc(r.title || "") + "</div>" +
    (r.context ? "<div class='dkb-glance-why'>" + esc(r.context) + "</div>" : "") +
    "<div class='dkb-glance-open'>open → its cockpit, in place</div></div>";
}

function wireMat(mat, cls, rows) {
  const close = mat.querySelector("[data-role='mat-close']");
  if (close) activate(close, () => closeMaterialised());
  $$(".dkb-glance[data-openrow]", mat).forEach((card) => {
    const row = rows.find((r) => (cls + "::" + String(r.id)) === card.dataset.openrow) || {};
    wireGlance(card,
      () => "<div class='lens-h'>" + esc(cls) + " — the referent</div><div>" + esc(row.context || row.title || "") + "</div>",
      () => openRow(row));
  });
}

function closeMaterialised() {
  const mat = $("#dkb-mat"); if (mat) mat.innerHTML = "";
  OPEN_MAT = null; persistWhere();
  $$(".dkb-count").forEach((c) => c.classList.remove("is-open"));
  BUS.clear();
}

// ═══════════════ OPEN A ROW — the referent REALLOCATES (B.2), the cockpit claims centre ═══
async function ensureClassMeta(cls) {
  return CLASS_CACHE[cls] || (CLASS_CACHE[cls] =
    await store.fetchJSON("/desk/class", { inject: [], params: { class: cls } })
      .catch((e) => ({ rows: [], error: (e && e.message) || String(e) })));
}

async function openRowByKey(key) {
  const sep = key.indexOf("::");
  const cls = sep >= 0 ? key.slice(0, sep) : "";
  const id = sep >= 0 ? key.slice(sep + 2) : key;
  let row = (BRIEF && BRIEF.his || []).find((r) => r.class === cls && String(r.id) === id);
  if (!row) { const d = CLASS_CACHE[cls]; row = d && (d.rows || []).find((r) => String(r.id) === id); }
  if (!row && cls) { const rows = await materialise(cls); row = (rows || []).find((r) => String(r.id) === id); }
  if (row) openRow(row);
}

async function openRow(row, o) {
  o = o || {};
  if (!row || !row.class) return;
  const meta = await ensureClassMeta(row.class);
  const key = row.class + "::" + String(row.id);
  PINNED = { class: row.class, id: row.id, key }; persistWhere();
  REALLOC.pin(key, {
    title: row.class + " · " + cut(row.title || row.glance || String(row.id), 60),
    destination: "back to the brief — what needs you",
    buildRail: (railEl) => buildRowRail(railEl, row, meta),
    buildFocus: (focusEl) => {
      const host = document.createElement("div");
      focusEl.appendChild(host);
      renderCockpit(host, deskCockpitOpts(row, meta));
    },
  });
  // the return door restores geometry (engine.mjs); hook our own cleanup so PINNED + the
  // session pointer clear when he returns (highlight hygiene rides the bus's own clear).
  const door = REALLOC.focus && REALLOC.focus.querySelector("[data-role='return-door']");
  if (door) door.addEventListener("click", () => afterClose());
  nameHeaderDecision(row);
  // an AMEND deep-link (proxy compose) lands with the replacement-ruling compose door focused.
  if (o.amend) { const a = REALLOC.focus && REALLOC.focus.querySelector(".dk-act.compose"); if (a && a.focus) a.focus(); }
}

function buildRowRail(railEl, row, meta) {
  const him = ownerOf(row) === "him";
  // FINDING 3 — appearance predicts behaviour: a not-his row wears the standing machine-
  // waiting wording (the same hymn token the wake's work-order attribution uses), never
  // "read-only exhaust" sitting under a live button. FINDING 7c — the "why it needs you"
  // block populates for EVERY his row (row.why for the brief-top pair, the class-level why
  // for a row opened from a chip), not only the two the brief composed a per-row why for.
  const why = him ? (row.why || (meta && meta.why) || "") : "";
  railEl.innerHTML =
    "<div class='eng-railblock'><h5>whose call</h5><div class='dkb-railcov'>" +
      (him ? "yours — owed to the author"
           : "waits for a machine session — nothing here needs your hand") + "</div></div>" +
    "<div class='eng-railblock'><h5>class</h5><div class='dkb-railcov'>" + esc(row.class) +
      (meta && meta.count != null ? " · " + meta.count + " open" : "") + "</div></div>" +
    (why ? "<div class='eng-railblock'><h5>why it needs you</h5><div class='dkb-railcov'>" +
      esc(why) + "</div></div>" : "");
}

function deskCockpitOpts(row, meta) {
  meta = meta || {};
  return {
    row,
    // FINDING 3 — a not-his (engine) row is machine-owed: the cockpit shows no live write
    // affordance, only the machine-waiting wording (appearance predicts behaviour).
    machineOwed: ownerOf(row) === "engine",
    consequences: meta.consequences || {},
    // DECORATIVE VERBS (E3, P3): the class's own deferred-verb table (desk.py's
    // ``_DEFERRED_VERBS`` — ONE producer) — verbButton renders these as quiet text.
    deferred: meta.deferred || {},
    // ZONE 1 — the full referent, fetched lazily (keeps the brief bounded, Law I).
    loadReferent: () => store.fetchJSON("/desk/referent", {
      inject: [], params: Object.assign(
        { class: row.class, project: row.project, id: row.id }, row.fields || {}) }),
    // ZONE 3 — the door: POST /desk/act (UNCHANGED write path), always the actor + the row's
    // door-ready fields; ``extra`` carries the evidence the compose editor attached.
    doFire: (verb, extra) => fireDeskVerb(row, verb, extra),
    // The echo law: the destination ledger named in the echo prefers a server path, then this
    // read-model store string (ONE producer, never a hardcoded path); the item leaves the list;
    // the counts re-render from server truth. All three fire on a successful act.
    storeLabel: meta.store || "",
    markItemDone: () => markRowLeaving(row),
    onFired: () => refreshBriefAfterAct(),
    // COMPOSE routing: a proxy AMEND re-lands on this decision PRE-PINNED (no lobby tax) with
    // the replacement-ruling compose door focused — never a misleading jump to a reader.
    composeHref: (verb) => (row.class === "proxy-drafts" && verb === "amend")
      ? ("/desk?item=proxy-drafts::" + encodeURIComponent(String(row.id)) + "&amend=1")
      : (row.href || null),
  };
}

// fire ONE verb through the W5 door (POST /desk/act) — UNCHANGED. Always sends `by`; the
// read-model's per-row `fields` ride straight into the payload. Returns {ok, text}.
async function fireDeskVerb(row, verb, extra) {
  const payload = Object.assign({ class: row.class, verb, by: DESK_ACTOR, project: row.project },
    row.fields || {}, extra || {});
  try {
    const data = await store.fetchJSON("/desk/act", { inject: [], method: "POST", body: payload });
    const idem = data && data.idempotent ? " (already done — no change)" : "";
    const applied = data && Array.isArray(data.applied) ? " applied " + data.applied.length : "";
    // the banked row's id echoes back in place (PV the-ruling-needs-a-composer): a composed
    // ruling confirms with the record it wrote, so his authoring act reads as landed, not lost.
    const bankedId = data && data.record && data.record.id ? "banked as " + data.record.id : "";
    return { ok: true, text: (idem || applied || bankedId || "").trim(), data };
  } catch (e) {
    return { ok: false, text: (e && e.message) || String(e) };
  }
}

// E-law · 2 — mark the acted-on row LEAVING: fade/collapse the origin glance in the brief DOM so
// it visibly leaves in place, its echo held in the cockpit, before the list re-renders from server
// truth. (While pinned the brief is display:none, so this is truth-on-return; it is also correct
// for any surface where the row is visible — build general, not scoped to the pinned path.)
function markRowLeaving(row) {
  if (!row || !row.class) return;
  const key = row.class + "::" + String(row.id);
  $$(".dkb-glance").forEach((el) => { if (el.dataset.openrow === key) el.classList.add("dkb-glance-done"); });
}

// E-law · 3 — The counts move: a fired verb changes the tallies, so re-fetch /desk/brief and
// RE-RENDER every dependent count in place — the his-cards, the class-count chips, the shell's
// Desk badge/word (HymnShell.setDeskBadge, shell.js) — without a page reload and WITHOUT tearing
// down the pin or an open class pane. This upgrades the former refreshBriefQuiet, which updated
// the data + badge but left the VISIBLE chips stale — the exact cause of "the ticker doesn't go
// down" (the author's ruling the 2026-07-23 ruling); the restore-where-he-was contract still
// holds for the pinned cockpit itself (the geometry is untouched — only the tallies repaint).
async function refreshBriefAfterAct() {
  try {
    const b = await store.fetchJSON("/desk/brief", { inject: [] });
    if (b && !b.error) BRIEF = b;
  } catch (e) { /* best-effort — the inline echo already told the truth */ }
  if (typeof window !== "undefined" && window.HymnShell && HymnShell.setDeskBadge)
    HymnShell.setDeskBadge(((BRIEF && BRIEF.his) || []).length);
  const chrome = $("#dkb-chrome");
  if (chrome && BRIEF && !BRIEF.error) { chrome.innerHTML = briefChromeHTML(); wireBrief(); }
  if (OPEN_MAT) await refreshMaterialised(OPEN_MAT);
}

// ── close a pin: engine.mjs restores geometry + scroll + the bus's lit state; we clear our
// own PINNED pointer and re-persist where he is (an open class pane, or the bare brief). ────
function closePin() { REALLOC.close(); afterClose(); }
function afterClose() { PINNED = null; persistWhere(); }

// ── the L1 header atom (shared): name the pinned decision so the arrival answers "what am I
// on" with the decision itself. Retried briefly — shell.js injects #hy-context on boot. ────
function nameHeaderDecision(row, tries) {
  tries = tries == null ? 8 : tries;
  const val = document.querySelector("#hy-context .hy-ctx-sel-val");
  const wrap = document.querySelector("#hy-context .hy-ctx-selwrap");
  if (val) { val.textContent = row.class + " · " + cut(row.title || row.glance || "", 48); if (wrap) wrap.hidden = false; return; }
  if (tries > 0) setTimeout(() => nameHeaderDecision(row, tries - 1), 60);
}

// ═══════════════ no lobby tax (B.5) — deep-link pre-pin + session restore ═════════════════
function persistWhere() {
  try {
    if (typeof sessionStorage === "undefined") return;
    sessionStorage.setItem(WHERE_KEY, JSON.stringify({
      mat: OPEN_MAT || null,
      pin: PINNED ? { class: PINNED.class, id: PINNED.id } : null,
    }));
  } catch (e) { /* private-mode / disabled storage — restore silently degrades */ }
}

async function applyEntry() {
  const p = new URLSearchParams(typeof location !== "undefined" ? location.search : "");
  const item = (p.get("item") || p.get("decision") || p.get("open") || "").trim();
  const cls = (p.get("class") || "").trim();
  const amend = p.get("amend") === "1";
  if (item) return prePinItem(item, cls, amend);
  if (cls) return materialise(cls);
  // no deep-link — restore where he was this session (the brief is the default, not a toll).
  return restoreWhere();
}

async function prePinItem(token, clsHint, amend) {
  let cls = clsHint || "", id = token;
  const sep = token.indexOf("::");
  if (sep >= 0) { cls = token.slice(0, sep); id = token.slice(sep + 2); }
  // a his-row deep-link resolves straight off the brief — no materialise needed.
  let row = (BRIEF && BRIEF.his || []).find((r) => String(r.id) === id && (!cls || r.class === cls));
  if (row) return openRow(row, { amend });
  if (!cls) { const found = await resolveRowClass(id); cls = found || ""; }
  if (!cls) return;                               // unresolvable id — the brief stands, plainly
  const rows = await materialise(cls);
  row = (rows || []).find((r) => String(r.id) === id);
  if (row) openRow(row, { amend });
}

// resolve a bare ?decision=<id> to its class via the full read-model (legacy deep-links).
async function resolveRowClass(id) {
  try {
    const d = await store.fetchJSON("/desk/data", { inject: [] });
    const row = (d.rows || []).find((r) => String(r.id) === id) ||
                (d.top || []).find((r) => String(r.id) === id);
    return row ? row.class : null;
  } catch (e) { return null; }
}

async function restoreWhere() {
  let where = null;
  try { where = JSON.parse((typeof sessionStorage !== "undefined" && sessionStorage.getItem(WHERE_KEY)) || "null"); }
  catch (e) { where = null; }
  if (!where) return;
  if (where.pin && where.pin.class) return openRowByKey(where.pin.class + "::" + where.pin.id);
  if (where.mat) return materialise(where.mat);
}

// standalone hook (parity with the other pane modules) for smoke pages / harnesses.
if (typeof window !== "undefined") window.__deskInit = initDesk;
