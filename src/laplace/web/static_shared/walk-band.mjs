// WALK BAND (S2 F7). Purpose: the session band (this walk's deposits and nothing else, gated by
// provenance), the historical ledger one door away, and the redline marks of deposits in the paper.
// Owns: MINTED (the provenance tokens), L (the ledger view), RL (the redline view). Public contract:
// admit, renderBand/paintDeposits/renderSpanDoor, liveRow/ruleRow/scopeRow/revokeRow, openLedger/
// closeLedger/toggleLedger, checkOrphans, toggleRedline/clearRedline/paintRedline.
import store from "/shared/store.mjs";
import {$, docEl, el, norm, paper, root} from './walk-base.mjs';
import {blockById} from './walk-document.mjs';
import {S, jumpToBlock, measure, sectionTitle, spanState} from './walk-position.mjs';
import {cssEscape} from './walk-pieces.mjs';
import {ADJUDICATE} from './walk-source-client.mjs';
import {renderBlockBody} from './walk-blocks.mjs';
import {
  C, SCOPES, askActor, bandCount, bandList, bandMix, bandNote, bandSpan, ledgerPath, paintMarks, railCount
} from './walk-composer.mjs';
import {closestBlock, hostText, nodeAt} from './walk-selection.mjs';
import {E, P, restoreFace} from './walk-drafts.mjs';
import {renderLinkages} from './walk-where.mjs';
import {inField} from './walk-controls.mjs';

// ═════════════════════════════════════════════════════════════════════════════════════════
// 16 · the session band — this walk's deposits, and nothing else
// ═════════════════════════════════════════════════════════════════════════════════════════

/** the session cursor — the one gate into the band.
 *
 *  The echo defect this closes: the band rendered the project's whole historical ledger as
 *  though those rows were appends he had just made. Keeping history out by never fetching
 *  it is an absence, and an absence is not an invariant — one future `await findings()`
 *  puts it back. So the band has exactly ONE entry point, and it admits a row only when
 *  this walk minted it: the row came back from a POST this walk issued, on this walk's own
 *  bank path, and the mint token proves it. A row offered from anywhere else — a findings
 *  fold-in, a ledger read — is refused and the refusal is said, never quietly listed.
 *
 *  it is not A CLOCK COMPARISON, and it must never become one again. The gate used to
 *  read `row.ts < S.opened`, comparing `manuscript_bridge`'s server-local naive
 *  `datetime.now().isoformat()` against the client's `new Date().toISOString()` — UTC,
 *  with a `Z`. On any host west of UTC every server string sorts BELOW the client string,
 *  so the band refused every deposit this walk banked while the composer echoed that it
 *  had banked: the echo defect inverted and silent. Provenance is knowable exactly;
 *  wall-clock agreement across a process boundary is not, so the gate rides provenance. */
const MINTED = Symbol("minted by this walk");

function admit(row, token) {
  if (!row || !row.id) return false;
  if (token !== MINTED) {
    C.refusal = "a row (" + row.id + ") was offered to this walk's band without this "
      + "walk's mint token, so it is not a deposit from this walk and is not listed here. "
      + "The project's ledger history is behind `l`, never in this list.";
    return false;
  }
  C.rows.unshift(row);
  C.mine.add(row.id);
  C.refusal = "";                 // a new deposit lands: the last refusal is spent
  return true;
}

function rowWhere(r) {
  if (r.grade === "artefact" || r.grade === "handover") return "the whole paper";
  if (r.grade === "span") {
    const n = (r.sections || []).length;
    return "span of " + n + " section" + (n === 1 ? "" : "s");
  }
  const t = sectionTitle(r.section);
  return t ? "§" + t : (r.section || "unanchored");
}

/** An id, or a row object that may be a copy, resolved to THE live row. */
function liveRow(r) {
  if (typeof r === "string") return C.rows.find((x) => x.id === r) || null;
  if (!r) return null;
  return C.rows.find((x) => x.id === r.id) || r;
}

async function ruleRow(row, state) {
  if (!row) return;
  if (!C.actor) {
    askActor("marking a row is actor-attributed. Name who is ruling and it appends.",
             () => ruleRow(row, state));
    return;
  }
  const body = state === "addressed"
    ? { verb: "confirm", finding_id: row.id, section: row.section || "", kind: "comment" }
    : { verb: "defer", finding_id: row.id, section: row.section || "",
        note: "declined — read, judged, not acting" };
  try {
    await store.fetchJSON(ADJUDICATE,
      { method: "POST", body: { ...body, by: C.actor, corpus: S.corpus } });
  } catch (e) {
    bandNote.textContent = "REFUSED — " + row.id + " is unchanged. " + e.message;
    return;
  }
  row.state = state;                 // his own gesture: the row moves in the same frame
  renderBand();
}

/** the scope-later door — the reach back to a row banked without an altitude.
 *
 *  The composer promises "scope it later from the band", and until this existed the band
 *  minted four controls per row and none of them was scope: the promise named a mechanic
 *  the surface did not have, on the one path the design most wants him to take (the
 *  zero-friction unscoped deposit). A promise with no door behind it is the register law
 *  broken, so the door exists.
 *
 *  it is an append, NOT A RELABEL. `/review/adjudicate {verb:"scope"}` writes a NEW
 *  scoping record naming this row and the altitude; the banked line is never rewritten and
 *  the findings board folds the latest scoping record over the row when it reads. The
 *  chip only moves after the door has answered — nothing here is a client-side repaint of
 *  a truth the ledger does not hold. */
async function scopeRow(row, scope) {
  row = liveRow(row);
  if (!row || !scope) return;
  if (!C.actor) {
    askActor("scoping a row is actor-attributed too. Name who is scoping and it appends.",
             () => scopeRow(row, scope));
    return;
  }
  let res;
  try {
    res = await store.fetchJSON(ADJUDICATE, {
      method: "POST",
      body: { verb: "scope", by: C.actor, corpus: S.corpus, finding_id: row.id,
              scope, scope_source: "chosen", section: row.section || "",
              ...(row.suggested_scope ? { suggested_scope: row.suggested_scope } : {}),
              note: "scoped from the walk's session band, after the deposit" },
    });
  } catch (e) {
    bandNote.textContent = "REFUSED — nothing was appended and " + row.id + " is still "
      + "unscoped. " + e.message;
    bandNote.dataset.tone = "refused";
    return;
  }
  row.scope = (res && res.scope) || scope;
  row.scope_source = (res && res.scope_source) || "chosen";
  row.scopedLater = true;
  renderBand();
  refocusRow(row.id);
}

/** A row re-rendered under his hands keeps the focus he had on it — the band is a
 *  keyboard surface and a control that vanishes mid-gesture is a dead click. */
function refocusRow(id) {
  const node = bandList.querySelector('.dep[data-id="' + cssEscape(id) + '"]');
  if (node) node.focus({ preventScroll: true });
}

async function revokeRow(row) {
  if (!row) return;
  if (!C.actor) {
    askActor("a revoke is actor-attributed. Name who is revoking and it appends.",
             () => revokeRow(row));
    return;
  }
  try {
    await store.fetchJSON(ADJUDICATE, {
      method: "POST",
      body: { verb: "revoke", by: C.actor, corpus: S.corpus, supersedes: row.id,
              reason: "revoked from the walk" },
    });
  } catch (e) {
    bandNote.textContent = "REFUSED — " + row.id + " still stands. " + e.message;
    return;
  }
  C.rows = C.rows.filter((r) => r.id !== row.id);
  C.mine.delete(row.id);
  C.marks = C.marks.filter((m) => m.id !== row.id);
  if (C.last && C.last.id === row.id) C.last = C.rows[0] || null;
  paintMarks();
  renderBand();
  paintDeposits();
}

function renderBand() {
  renderBandCore();
  renderLinkages();
  paintRedline();          // banked rows changed: the live redline follows
}

function renderBandCore() {
  bandList.textContent = "";
  for (const r of C.rows) {
    const d = el("div", "dep");
    d.dataset.state = r.state;
    d.dataset.kind = r.kind || "comment";
    d.dataset.id = r.id;
    // -1: reachable PROGRAMMATICALLY, never by Tab. A row that re-renders under his hands
    // (it just took a scope) can be handed its focus back instead of dropping it to the
    // body; the scope door raises this to 0 on the rows that answer the digits.
    d.tabIndex = -1;
    if (C.last && r.id === C.last.id) d.dataset.fresh = "1";
    if (r.orphan) d.dataset.orphan = "1";

    const top = el("div", "dep-top");
    if (r.kind && r.kind !== "comment") {
      top.appendChild(el("span", "dep-kind",
        r.kind + (r.applied ? " · spliced" : r.pending ? " · pending" : "")));
    }
    // THE RULING, BESIDE THE PASSAGE IT RULES ON. First in the row, before the altitude and
    // the provenance, because keep/cut/rework is the only thing in a deposit that tells a
    // later reader what to DO with the passage.
    if (r.disposition) {
      const ruling = el("span", "dep-ruling",
        r.disposition + (r.altitude ? " · " + r.altitude : ""));
      ruling.dataset.ruling = r.disposition;
      top.appendChild(ruling);
    }
    const chip = el("span", "dep-scope", r.scope || "unscoped");
    if (!r.scope) chip.dataset.unscoped = "1";
    top.appendChild(chip);
    if (r.scope && r.scope_source) {
      top.appendChild(el("span", "dep-state", r.scope_source
        + (r.scopedLater ? " · scoped from the band" : "")
        + (r.suggested_scope && r.suggested_scope !== r.scope
           ? " over " + r.suggested_scope : "")));
    }
    const where = el("span", "dep-where", rowWhere(r));
    top.appendChild(where);
    const st = el("span", "dep-state", r.state);
    st.dataset.state = r.state;
    top.appendChild(st);
    d.appendChild(top);

    if (r.flip) {
      // the source flip's own receipt: the outcome in words, never the tex it wrote.
      d.appendChild(el("div", "dep-text",
        (r.applied ? "the whole block's source, written back in place at "
                   : "the whole block's source, banked as a pending rewrite against ")
        + r.where + " — the text you changed is in the paper, not in this list."));
    } else if (r.kind !== "comment") {
      d.appendChild(el("div", "dep-was", "was: " + norm(r.before).slice(0, 160)));
      d.appendChild(el("div", "dep-text", "now: " + norm(r.after).slice(0, 240)));
      if (r.comment) d.appendChild(el("div", "dep-text", norm(r.comment).slice(0, 240)));
    } else {
      d.appendChild(el("div", "dep-text", norm(r.comment).slice(0, 240)));
    }
    if (r.orphan) {
      d.appendChild(el("div", "dep-orphan",
        "orphan — this quote is no longer in the block it names, so its anchor does not "
        + "resolve against the text as it now stands"));
    }
    d.appendChild(el("div", "dep-id", r.id + (r.by ? "  ·  " + r.by : "")));

    // the scope door — GATED ON scope_source, NOT ON scope.
    //
    // The defect this closes: the door was gated on `!r.scope`, and the REWRITE path never
    // reaches that state — the rewrite door applies its own `sentence` default, so a
    // rewrite banked without a digit came back carrying `scope: "sentence"`,
    // `scope_source: "default"`, and was the one row class the band could never re-scope.
    // That is the machine's lean, not his hand, and the whole point of recording
    // `scope_source` was so the two could be told apart. So: default and inferred rows are
    // re-scopable exactly like unscoped ones; a CHOSEN altitude reads as settled, and
    // still offers the door when the row takes focus (keyboard-reachable, never
    // hover-only) — because he is allowed to change his own mind too.
    const src = String(r.scope_source || "");
    const live = r.state !== "declined";
    const open = live && (!r.scope || !src || src === "default" || src === "inferred");
    const settled = live && !open;
    if (open || settled) {
      d.tabIndex = 0;
      d.dataset.scopeDoor = open ? "1" : "settled";
      d.setAttribute("aria-label",
        (open ? (r.scope ? r.scope + " (" + (src || "no source") + ") deposit "
                         : "unscoped deposit ")
              : r.scope + " (chosen) deposit ") + r.id
        + " — press 1 to 6 to " + (open ? "scope it" : "re-scope it"));
      const scopeRowEl = el("div", "dep-scopes");
      if (settled) scopeRowEl.dataset.settled = "1";
      scopeRowEl.appendChild(el("span", "dep-scopes-lead",
        open ? (r.scope ? "the machine's default — set it yourself:" : "scope it:")
             : "settled at " + r.scope + " — re-scope it:"));
      SCOPES.forEach((s, i) => {
        const b = el("button", "chip");
        b.type = "button";
        b.dataset.scope = s;
        if (r.scope === s) b.setAttribute("aria-pressed", "true");
        b.appendChild(el("span", "k", String(i + 1)));
        b.appendChild(el("span", null, s));
        b.addEventListener("click", (ev) => { ev.stopPropagation(); scopeRow(r, s); });
        scopeRowEl.appendChild(b);
      });
      d.appendChild(scopeRowEl);
      d.addEventListener("keydown", (ev) => {
        if (ev.altKey || ev.ctrlKey || ev.metaKey) return;
        if (inField(ev.target)) return;
        if (!/^[1-6]$/.test(ev.key)) return;
        ev.preventDefault();
        ev.stopPropagation();
        scopeRow(r, SCOPES[Number(ev.key) - 1]);
      });
    }

    const acts = el("div", "dep-acts");
    if (r.blockId) {
      const go = el("button", null, "go to it"); go.type = "button";
      go.addEventListener("click", () => jumpToBlock(r.blockId));
      acts.appendChild(go);
    }
    // a declined row is TERMINAL: it keeps its place and is never asked about again.
    if (r.state !== "declined") {
      if (r.state !== "addressed") {
        const b = el("button", null, "addressed"); b.type = "button";
        b.addEventListener("click", () => ruleRow(r, "addressed"));
        acts.appendChild(b);
      }
      const b2 = el("button", null, "declined"); b2.type = "button";
      b2.addEventListener("click", () => ruleRow(r, "declined"));
      acts.appendChild(b2);
      const b3 = el("button", null, "revoke"); b3.type = "button";
      b3.addEventListener("click", () => revokeRow(r));
      acts.appendChild(b3);
    }
    if (acts.childNodes.length) d.appendChild(acts);
    bandList.appendChild(d);
  }
  const rewrites = C.rows.filter((r) => r.kind && r.kind !== "comment").length;
  bandCount.textContent = C.rows.length + " deposit" + (C.rows.length === 1 ? "" : "s")
    + (rewrites ? " · " + rewrites + " in your hand" : "");
  railCount.textContent = String(C.rows.length);
  paintScopeMix();
  // A refusal outlives the render. The gate used to write its refusal straight into
  // `bandNote`, and the very next `renderBand()` — one line later on the bank path —
  // overwrote it with "nothing banked in this walk yet". The refusal is state, not a
  // paint, so it is held on `C` and rendered here, above the standing words.
  bandNote.textContent = (C.refusal ? C.refusal + " " : "")
    + (C.rows.length
    ? "this list is THIS walk's deposits. addressed appends a confirm; declined appends a "
      + "defer and is terminal; revoke supersedes. A row whose altitude is unset, or is "
      + "the door's own default, or the rule's lean carries the six altitudes standing "
      + "open — click one, or focus the row and press 1–6. A row you chose the altitude "
      + "for reads as settled and offers the same six on focus. Either way it appends a "
      + "scoping record. Every one is an append — no past line is rewritten. "
    : "nothing banked in this walk yet. Select a passage to arm the composer, press Enter "
      + "to take the block at the reading mark, or 0 for the whole paper. ")
    + "The project's ledger history — every row banked before this walk — is behind `l`, "
    + "never in this list.";
  bandNote.dataset.tone = C.refusal ? "refused" : "";
  renderSpanDoor();
}

/** the scope-mix line — the altitude spread of this walk, in one plain line.
 *
 *  "3 sentence · 1 structure · 1 artefact · 1 unscoped". It is the one thing the band's
 *  head cannot say by counting rows: whether the walk is all sentence-polish or is
 *  actually reaching the structural altitudes. Glanceable and NOTHING else — no control,
 *  no filter, no link, one line clipped rather than wrapped (G6: it claims one line, never
 *  a growing block).
 *
 *  It updates with the band, which means echo-instant for the row he just banked (the bank
 *  path calls `renderBand` in the frame of the Enter) and at the same coarse boundaries as
 *  everything else otherwise. It is written straight to the DOM: a count moving is
 *  system-initiated, and the no-motion law does not bend for a number. */
function paintScopeMix() {
  if (!bandMix) return;
  const counts = new Map();
  for (const r of C.rows) counts.set(r.scope || "", (counts.get(r.scope || "") || 0) + 1);
  const parts = [];
  for (const s of SCOPES) if (counts.get(s)) parts.push(counts.get(s) + " " + s);
  if (counts.get("")) parts.push(counts.get("") + " unscoped");
  bandMix.hidden = !parts.length;
  bandMix.textContent = parts.join("  ·  ");
}

function renderSpanDoor() {
  const sp = spanState();
  bandSpan.hidden = !sp || !!C.armed;
  if (sp && !C.armed) {
    bandSpan.textContent = "deposit on this span of " + sp.sections.length + " section"
      + (sp.sections.length === 1 ? "" : "s") + " (Enter)";
  }
}

/** The spine's deposit badges. A count moving is system-initiated: written straight to
 *  the DOM, no transition, no motion. */
function paintDeposits() {
  const counts = new Map();
  for (const r of C.rows) {
    if (r.grade === "artefact" || r.grade === "handover") continue;
    for (const id of (r.sections || (r.section ? [r.section] : []))) {
      counts.set(id, (counts.get(id) || 0) + 1);
    }
  }
  for (const sec of S.sections) {
    if (!sec.countEl) continue;
    const n = counts.get(sec.id) || 0;
    sec.countEl.textContent = n ? String(n) : "";
  }
}

// ── the historical board — one door away, and labelled ───────────────────────────────────
//
// The echo defect this door exists to make impossible: the project's ledger rendered inside
// the session band, so 100-odd rows banked in past sessions read as appends he just made.
// The two lists are different questions and they live in different places. The band holds
// THIS walk. This holds the ledger, behind `l`, titled, counted, and read-only — nothing in
// it can be mistaken for something this walk deposited.

const L = { open: false, loaded: false, rows: [], note: "" };
const ledgerEl = $("ledger"), ledgerList = $("ledger-list"), ledgerNote = $("ledger-note");

function ledgerRows(board) {
  const out = [];
  const take = (f, node) => out.push({
    id: String((f && f.id) || ""), kind: String((f && f.kind) || ""),
    cls: String((f && f.cls) || ""), comment: String((f && f.comment) || ""),
    section: String((f && f.section) || ""), by: String((f && f.by) || ""),
    ts: String((f && f.ts) || ""), state: String((f && f.state) || ""),
    node: String(node || (f && f.node) || ""),
    // the ruling the findings read publishes (`review_surface._feedback_findings`), so a
    // keep/cut he left in an earlier session is visible HERE after a refresh — the band holds
    // only this walk, and the ledger is where every past ruling is
    disposition: String((f && f.disposition) || ""),
    altitude: String((f && f.altitude) || ""),
  });
  for (const g of (Array.isArray(board.by_node) ? board.by_node : [])) {
    for (const f of (Array.isArray(g.findings) ? g.findings : [])) take(f, g.node);
  }
  for (const f of (Array.isArray(board.unanchored) ? board.unanchored : [])) take(f, "");
  return out;
}

function renderLedger() {
  ledgerList.textContent = "";
  for (const r of L.rows) {
    const d = el("div", "led");
    const top = el("div", "led-top");
    if (r.cls) { const c = el("span", "led-cls", r.cls); c.dataset.cls = r.cls;
                 top.appendChild(c); }
    if (r.disposition) {
      const ruling = el("span", "dep-ruling",
        r.disposition + (r.altitude ? " · " + r.altitude : ""));
      ruling.dataset.ruling = r.disposition;
      top.appendChild(ruling);
    }
    top.appendChild(el("span", "led-kind", r.kind || "(no kind)"));
    top.appendChild(el("span", "led-where",
      (r.node || r.section || "unanchored") + (r.by ? "  ·  " + r.by : "")
      + (r.ts ? "  ·  " + r.ts.slice(0, 10) : "")));
    if (r.state) top.appendChild(el("span", "led-cls", r.state));
    d.appendChild(top);
    if (r.comment) d.appendChild(el("div", "led-text", norm(r.comment).slice(0, 320)));
    d.appendChild(el("div", "led-id", r.id));
    ledgerList.appendChild(d);
  }
  ledgerNote.textContent = L.note;
}

async function openLedger() {
  L.open = true;
  ledgerEl.hidden = false;
  if (!L.loaded) {
    L.note = "reading the project's ledger…";
    renderLedger();
    let board;
    try {
      board = await store.fetchJSON("/review/findings");
    } catch (e) {
      L.note = "the findings door did not answer, so this project's history cannot be "
             + "shown. This walk's own deposits are unaffected — they are in the band. ("
             + e.message + ")";
      renderLedger();
      return false;
    }
    L.rows = ledgerRows(board || {});
    L.loaded = true;
  }
  const c = C.rows.length;
  L.note = L.rows.length + " row" + (L.rows.length === 1 ? "" : "s")
    + " banked in " + ledgerPath() + " across every session of this project. "
    + "This walk opened at " + S.opened + ", and its band lists ONLY the rows this walk "
    + "itself banked, so none of these can appear there: this walk's "
    + c + " deposit" + (c === 1 ? " is" : "s are") + " in the band, and the two lists are "
    + "never merged. This door is read-only — rule a row from the band, or from the "
    + "artefact surface's findings board.";
  renderLedger();
  $("ledger-close").focus();
  return true;
}

function closeLedger() {
  if (!L.open) return false;
  L.open = false;
  ledgerEl.hidden = true;
  paper.focus();
  return true;
}

const toggleLedger = () => (L.open ? closeLedger() : openLedger());

/** An anchor that no longer resolves is SAID, never silently dropped. On this canvas the
 *  check is deterministic: is the quote still in the block it names? */
function checkOrphans() {
  let changed = false;
  for (const r of C.rows) {
    const q = norm(r.quote || "");
    let orphan = 0;
    if (q && r.blockId) {
      const b = blockById.get(r.blockId);
      if (!b || !b.el) orphan = 1;
      // ONE normaliser on both sides. `norm` keeps the tie's nbsp and a bare
      // `replace(/\s+/g," ")` does not, so the two readings disagreed on every passage
      // holding a `~` and every one of them read as an orphan.
      else if (norm(hostText(b.bodyEl || b.el)).indexOf(q) < 0) orphan = 1;
    }
    if (r.orphan !== orphan) { r.orphan = orphan; changed = true; }
  }
  if (changed) renderBand();
}

// the live redline (his ruling, 2026-08-11: "insertions and deletions should be kept
// live so I can see what's there before the next pass" — with a toggle). `r` flips it.
// Insertions wear a mark on the face; each deletion stands struck-through BESIDE its
// replacement as chrome (data-chrome: no reader, offset, or splice ever counts it).
// It draws from the two stores that ARE the session's delta: the parks (unbanked) and
// this walk's banked rows; a change it cannot place inline gets a loud block badge —
// shown differently or shown as absent, never silently unshown.
let RL = false;

function toggleRedline() {
  RL = !RL;
  root.dataset.redline = RL ? "1" : "";
  if (RL) paintRedline(); else clearRedline();
  C.echo = { text: RL
    ? "redline ON — this walk's insertions marked, deletions struck beside them · r toggles"
    : "redline OFF — the clean face · r brings the marks back", tone: "banked" };
  renderBand();
}

function clearRedline(scopeEl) {
  if (scopeEl) {
    // the ACTIVE block's marks unwrap in place (a re-render would eat the caret);
    // his eyes are on this block, and the park still holds the pre-mark words
    for (const n of scopeEl.querySelectorAll(".rl-del, .rl-badge")) n.remove();
    for (const ins of scopeEl.querySelectorAll(".rl-ins")) {
      const parent = ins.parentNode;
      while (ins.firstChild) parent.insertBefore(ins.firstChild, ins);
      ins.remove();
      if (parent && parent.normalize) parent.normalize();
    }
    return;
  }
  // the whole-face path takes the byte-exact route: every marked block re-renders
  // from source and any standing park is re-placed — no unwrap arithmetic (an unwrap
  // over an extraction-split island measurably ate mid-span bytes, 2026-08-11b)
  const marked = new Set();
  for (const n of docEl.querySelectorAll(".rl-ins, .rl-del, .rl-badge")) {
    const blkEl = closestBlock(n);
    if (blkEl && blkEl.dataset.block) marked.add(blkEl.dataset.block);
  }
  if (!marked.size) return;
  for (const id of marked) {
    const b = blockById.get(id);
    if (!b || !b.bodyEl) continue;
    if (E.blockId === id && E.dirty) { clearRedline(b.el); continue; }
    renderBlockBody(b, b.bodyEl);
    if (P.has(id)) restoreFace(b);
    if (b.el && P.has(id)) b.el.dataset.parked = "1";
  }
  paintMarks();
  measure();
}

function markSpan(b, start, end, delText) {
  const host = b.bodyEl;
  if (!host || !(end >= start)) return false;
  const beforeText = hostText(host);
  const lo = nodeAt(host, start), hi = nodeAt(host, end);
  if (!lo || !hi) return false;
  const r = document.createRange();
  try { r.setStart(lo.node, lo.off); r.setEnd(hi.node, hi.off); }
  catch (_e) { return false; }
  const ins = document.createElement("span");
  ins.className = "rl-ins";
  try {
    ins.appendChild(r.extractContents());
    r.insertNode(ins);
  } catch (_e) {
    // NOTHING may be lost: if the insert failed after the extraction, the words go
    // back at the range point as plain text (chrome-free, same characters)
    if (ins.textContent) {
      try { r.insertNode(document.createTextNode(ins.textContent)); }
      catch (_e2) { host.appendChild(document.createTextNode(ins.textContent)); }
      host.normalize();
    }
    return false;
  }
  if (delText) {
    const del = document.createElement("del");
    del.className = "rl-del";
    del.setAttribute("data-chrome", "1");
    del.setAttribute("contenteditable", "false");
    del.textContent = delText.length > 160 ? delText.slice(0, 157) + "…" : delText;
    del.title = delText;
    ins.parentNode.insertBefore(del, ins);
  }
  // the mark must be INVISIBLE to every reader: a paint that moved one face byte is
  // rolled back whole (the badge says the change instead)
  if (hostText(host) !== beforeText) {
    clearRedline(b.el);
    return false;
  }
  return true;
}

function blockBadge(b, words) {
  if (!b || !b.el || b.el.querySelector(".rl-badge")) return;
  const badge = el("div", "rl-badge", words);
  badge.setAttribute("data-chrome", "1");
  badge.setAttribute("contenteditable", "false");
  b.el.insertBefore(badge, b.el.firstChild);
}

let RL_PAINTING = false;

function paintRedline() {
  if (!RL || RL_PAINTING) return;
  RL_PAINTING = true;
  try { paintRedlineCore(); } finally { RL_PAINTING = false; }
}

function paintRedlineCore() {
  clearRedline();
  // the parks: every standing (non-active) delta, inline
  for (const [id, entry] of P.entries()) {
    if (E.blockId === id && E.dirty) continue;      // the caret owns the active block
    const b = blockById.get(id);
    if (!b || !b.bodyEl || entry.noteOnly) continue;
    if (hostText(b.bodyEl) !== entry.text) continue; // face moved: the band holds it
    const was = entry.pristine || "", now = entry.text || "";
    let p = 0;
    const nl = now.length, wl = was.length;
    while (p < nl && p < wl && now[p] === was[p]) p += 1;
    let s = 0;
    while (s < nl - p && s < wl - p && now[nl - 1 - s] === was[wl - 1 - s]) s += 1;
    markSpan(b, p, nl - s, was.slice(p, wl - s));
  }
  // this walk's banked rows: the applied session delta, kept visible until the pass
  for (const row of C.rows) {
    if (!row.mine || row.state === "revoked") continue;
    if (row.kind !== "rewrite" && row.kind !== "compound") continue;
    const b = row.blockId ? blockById.get(row.blockId) : null;
    if (!b || !b.bodyEl) continue;
    const after = row.after || "";
    let placed = false;
    if (row.applied && after && after.length >= 3 && !after.startsWith("¶")
        && !after.startsWith("(")) {
      const face = hostText(b.bodyEl);
      const at = face.indexOf(after);
      if (at >= 0) placed = markSpan(b, at, at + after.length, row.before || row.quote || "");
    }
    if (!placed) {
      blockBadge(b, (row.applied ? "changed here this walk (" : "a banked change stands "
        + "here (") + row.id + ") — the band holds its before/after");
    }
  }
}

export {
  L, MINTED, RL, admit, checkOrphans, clearRedline, closeLedger, ledgerEl, liveRow, openLedger, paintDeposits,
  paintRedline, renderBand, renderSpanDoor, revokeRow, ruleRow, scopeRow, toggleLedger, toggleRedline
};
