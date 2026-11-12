// WALK COMPOSER (S2 F7). Purpose: the rewrite-first, actor-attributed composer: scopes and rulings,
// the actor, the rail, arming a block, selection, span or artefact, the frozen scope suggestion and
// the composer's face and routing words. Owns: C (the composer state: armed anchor, scope, ruling,
// disposition), HL (the persistent marks) and the composer's DOM handles. Public contract: arm and
// its variants, disarm, renderComposer, setScope/setDisposition, the actor (loadActor/askActor/
// nameActor) and the rail (openRail/settleRail/toggleRail). Deposits go through walk-bank.mjs.
import {$, el, norm, paper, root} from './walk-base.mjs';
import {blockById, expectedOf} from './walk-document.mjs';
import {
  S, blockAtY, mintDoor, railPx, readingY, reallocate, sectionAtY, spanState, takeDoor
} from './walk-position.mjs';
import {
  anchorForWholeBlock, anchorFromRange, liveRange, rangeInBlock, spliceState
} from './walk-selection.mjs';
import {inField} from './walk-controls.mjs';

// ═════════════════════════════════════════════════════════════════════════════════════════
// 11 · THE COMPOSER — rewrite-first, actor-attributed, and it never shows raw tex
// ═════════════════════════════════════════════════════════════════════════════════════════
//
//   the actor law. No baked default anywhere in this file: the actor comes from ?actor= or
//   a one-time prompt persisted in localStorage, and the door refuses an unattributed write.
//
//   the echo law. Enter banks and the SAME frame carries the receipt: the row id and its
//   destination in the composer footer, the section's badge moving on the spine, the row
//   landing at the head of the session band — a band that holds THIS walk and nothing else.
//
//   the register law. Every string states the mechanics plainly, once.

/** The altitude vocabulary — ONE producer: `schema.FEEDBACK_SCOPES`, the six already typed
 *  in his own ledger rows. The order is the key order (1..6), not alphabetical. */
const SCOPES = ["sentence", "structure", "voice", "artefact", "meta", "delivery"];

/** the frozen rule set. Cheap, per-session STATIC, never retrained under him. It lights a
 *  SUGGESTION and nothing else: it never selects a chip, never pre-fills, never banks. */
const RULE_SET_ID = "walk-rules-2026-08-10-r2";
const RULES = Object.freeze([
  ["sentence", /\b(word|wording|phrase|phrasing|comma|clause|typo|spelling|grammar|tense|sentence|awkward|clunky|redundant)\b/gi],
  ["structure", /\b(order|ordering|arc|structure|structural|section|paragraph|belongs|reorder|split|merge|sequence|scaffold|storyboard)\b/gi],
  ["voice", /\b(voice|tone|register|hedge|hedging|jargon|pompous|breathless|salesy|overclaim|overclaims|purple|slop)\b/gi],
  ["artefact", /\b(whole paper|the paper|overall|throughout|title|abstract|framing|thesis|contribution|the claim)\b/gi],
  ["meta", /\b(process|pipeline|engine|the loop|workflow|the machine|organ|this tool|the walk)\b/gi],
  ["delivery", /\b(figure|caption|table|citation|references|bibliograph|format|layout|typeset|release|submit|submission|journal|arxiv|handover|deliver)\b/gi],
]);

/** the three gestureless scopes, absorbed by the gestures that exist
 *  (GAP-20260810-altitude-gestures, decided — the fork law: not-asking is not deferring).
 *
 *  voice, meta and delivery have no native deposit gesture, while sentence, structure and
 *  artefact each own one (the rewrite, the spine span, key 0). The alternative not taken
 *  was three novel gestures for the three RAREST scopes — mode surface without frequency,
 *  which is the coded-vocabulary lesson. Instead the existing gestures absorb them through
 *  the frozen guesser, keyed on WHERE the deposit was made as well as what it says:
 *
 *    · a selection + note with NO rewrite — the pure comment, his "this reads wrong"
 *      gesture — leans VOICE when the note carries register vocabulary;
 *    · a whole-paper deposit (key 0) leans DELIVERY when its text carries handover
 *      vocabulary — the shape of his own highest-value rows;
 *    · a spine-span deposit leans META when it carries apparatus vocabulary, beside the
 *      STRUCTURE that a span otherwise naturally is.
 *
 *  These are SUGGESTIONS and nothing else: the chip is marked, never pre-selected, never
 *  pre-filled, and every banked row records `suggested_scope` so the override rate of each
 *  rule stays derivable from the ledger. The set is frozen per session (RULE_SET_ID) and a
 *  rule whose override rate exceeds ~1/3 is retired, not tuned. */
const GRADE_RULES = Object.freeze([
  // [the gesture it keys on, the scope it leans, the vocabulary]
  ["note-without-rewrite", "voice",
   /\b(sounds?|sounded|reads?|read like|tone|register|voice|stiff|stilted|flowery|florid|purple|wordy|verbose|long-winded|clunky|awkward|pompous|breathless|salesy|hedge|hedging|jargon|dry|flat|clipped|overwritten)\b/gi],
  ["whole-paper", "delivery",
   /\b(name|named|naming|file|filename|pdf|version|revision|rev|deliver|delivery|delivered|hand|handover|handed|send|sending|ship|release|released|submit|submission|attach|export|arxiv|journal)\b/gi],
  ["span", "meta",
   /\b(claim|claims|evidence|apparatus|figure count|counts?|ordering|order of the argument|argument|method|methods|methodology|protocol|provenance|reproduc\w*|process|pipeline|workflow)\b/gi],
]);

/** Which grade rule, if any, this gesture is eligible for. ONE reader, so the suggestion,
 *  the ? map's "where this scope naturally lives" lines, and the fences agree. */
function gradeRuleFor(grade, shape) {
  if (grade === "artefact" || grade === "handover") return GRADE_RULES[1];
  if (grade === "span") return GRADE_RULES[2];
  if (grade === "selection" && shape === "comment") return GRADE_RULES[0];
  return null;
}

const ACTOR_KEY = "walk.actor";

const C = {
  actor: "",
  armed: null,
  scope: "", scopeSource: "", suggested: "",
  echo: null,
  needActor: "",
  pending: null,
  rail: "strip",
  rows: [],               // THIS WALK'S deposits. The ledger's history is never rendered.
  mine: new Set(),
  last: null,
  marks: [],              // {blockId, start, end, armed, id}
  refusal: "",            // the last band refusal, in words — it OUTLIVES the next render
  // THE RULING ON THE PASSAGE (WRITING-CONSOLIDATION-W1): keep | cut | rework, and the
  // altitude it is ruled at. Neither is defaulted: a comment with no ruling is a comment,
  // which is what every row in his ledger already is, and the altitude is read off what the
  // gesture addressed unless he names one.
  disposition: "", altitude: "",
};

//: the three rulings and the keys that set them. 7/8/9 because 1-6 are the six altitudes
//: (`SCOPES`) and a bare digit in a field types — the boundary the composer already holds.
const DISPOSITIONS = ["keep", "cut", "rework"];

const composer = $("composer"), compWhere = $("comp-where"), compQuote = $("comp-quote");
const compQuoteLbl = $("comp-quote-lbl"), compBodyLbl = $("comp-body-lbl");
const compBody = $("comp-body"), compScopes = $("comp-scopes"), compSuggest = $("comp-suggest");
const compRulings = $("comp-rulings");
const compShape = $("comp-shape"), compRoute = $("comp-route"), compHint = $("comp-hint");
const compEcho = $("comp-echo");
const compActor = $("comp-actor"), compActorNote = $("comp-actor-note");
const compActorInput = $("comp-actor-input"), compActorOk = $("comp-actor-ok");
const bandList = $("band-list"), bandCount = $("band-count"), bandNote = $("band-note");
const bandSpan = $("band-span"), railCount = $("rail-count"), bandMix = $("band-mix");

// ── the actor ────────────────────────────────────────────────────────────────────────────

function loadActor() {
  let q = "";
  try { q = (new URLSearchParams(window.location.search).get("actor") || "").trim(); }
  catch (_e) { q = ""; }
  if (q) {
    try { window.localStorage.setItem(ACTOR_KEY, q); } catch (_e) { /* private mode */ }
    return q;
  }
  try { return (window.localStorage.getItem(ACTOR_KEY) || "").trim(); } catch (_e) { return ""; }
}

function askActor(why, then) {
  C.needActor = why;
  C.pending = then || null;
  openRail(C.armed ? "armed" : "band");
  renderComposer();
  compActorInput.value = "";
  compActorInput.focus();
}

function nameActor() {
  const v = compActorInput.value.trim();
  if (!v) return;
  C.actor = v;
  try { window.localStorage.setItem(ACTOR_KEY, v); } catch (_e) { /* private mode */ }
  C.needActor = "";
  const then = C.pending; C.pending = null;
  renderComposer();
  if (then) then();
}

// ── the rail ─────────────────────────────────────────────────────────────────────────────

function openRail(mode, { force = false } = {}) {
  if (C.rail === mode && !force) return;
  C.rail = mode;
  root.dataset.rail = mode;
  reallocate({ rail: railPx(mode) });   // G1: the focal point does not move by one pixel
}

function restMode() {
  if (C.armed || C.needActor) return "armed";
  // HIS RULING (2026-08-10 remote): the band never claims width on its own — once open
  // it stuck for the whole session with no mouse way off. It opens on a bank's echo
  // moment and on his click (the strip, `b`); a click back into the paper puts it away.
  return "strip";
}

const settleRail = () => openRail(restMode());

function toggleRail() {
  if (C.armed) return;                 // the armed composer owns the width
  openRail(C.rail === "strip" ? "band" : "strip");
}

// ── the marks that persist in the paper ──────────────────────────────────────────────────

const HL = { ok: !!(window.Highlight && window.CSS && CSS.highlights), reg: {} };

function setHighlight(name, ranges) {
  if (!HL.ok) return;
  try {
    let h = HL.reg[name];
    if (!h) { h = new Highlight(); HL.reg[name] = h; CSS.highlights.set(name, h); }
    h.clear();
    for (const r of ranges) h.add(r);
  } catch (_e) { HL.ok = false; }
}

/** The block's own rule always carries the cue; the exact range carries it too wherever
 *  the browser gives the Highlight API. Neither depends on the other. */
function paintMarks() {
  for (const b of S.blocks) if (b.el) delete b.el.dataset.mark;
  const armed = [], banked = [];
  for (const m of C.marks) {
    const b = blockById.get(m.blockId);
    if (!b || !b.el) continue;
    b.el.dataset.mark = m.armed ? "armed" : "banked";
    const r = rangeInBlock(b, m.start, m.end);
    if (r) (m.armed ? armed : banked).push(r);
  }
  setHighlight("walk-armed", armed);
  setHighlight("walk-mark", banked);
}

const dropArmedMark = () => { C.marks = C.marks.filter((m) => !m.armed); };

// ═════════════════════════════════════════════════════════════════════════════════════════
// 13 · ARMING
// ═════════════════════════════════════════════════════════════════════════════════════════

function arm(a) {
  C.armed = a;
  C.echo = null;
  C.scope = ""; C.scopeSource = ""; C.suggested = ""; C.disposition = ""; C.altitude = "";
  dropArmedMark();
  if (a.grade === "selection" && a.end > a.start) {
    C.marks.push({ blockId: a.blockId, start: a.start, end: a.end, armed: true });
  }
  paintMarks();
  mintDoor();                       // G4 — the named way home, visible before he types
  openRail("armed");
  // raw tex never reaches this rail. The quote field is prefilled from the block's
  // RENDERED text, which for a raw block (a table, a tabular, an enumerate) or a formula
  // the renderer refused IS the LaTeX source — so arming there used to fill the docked
  // composer with tex, editable, and print it again in the band. The source shows in ONE
  // place: in place at the block, invited, behind `s`. Here the field simply does not open.
  compQuote.value = quotable(a) ? a.quote : "";
  compBody.value = "";
  updateSuggestion();
  renderComposer();
  sizeFields();                     // after the render: a hidden textarea measures 0
  if (quotable(a)) compQuote.focus(); else compBody.focus();
}

function armFromSelection() {
  const range = liveRange();
  if (!range) return false;
  const a = anchorFromRange(range);
  if (!a) return false;
  arm(a);
  return true;
}

/** THE KEYBOARD'S SELECTION. Enter with nothing selected takes the BLOCK at the reading
 *  mark — selected for real, so the mark, the quote, the context and the source span are
 *  the same ones a pointer would have produced. Without this the deposit loop has one
 *  mandatory mouse step; with it the chain closes. */
function armBlockAtReadingLine() {
  if (!S.blocks.length) return false;
  const b = S.blocks[blockAtY(readingY())];
  if (!b || !b.el) return false;
  const host = b.bodyEl || b.el;
  try {
    const range = document.createRange();
    range.selectNodeContents(host);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  } catch (_e) { /* a block with no text still arms, mark-only */ }
  b.el.focus({ preventScroll: true });
  arm(anchorForWholeBlock(b));
  return true;
}

/** The whole-paper composer (`0`). His own highest-value rows anchor here; a structural
 *  verdict is never faked onto a paragraph. */
function armArtefact() {
  const sec = S.sections[S.current >= 0 ? S.current : sectionAtY(readingY())];
  arm({ grade: "artefact", blockId: "", kind: "", sectionId: sec ? sec.id : "",
        sectionTitle: sec ? sec.title : "", file: "", lineStart: 0, lineEnd: 0,
        quote: "", start: 0, end: 0, before: "", after: "", tex: "" });
}

/** The span composer — a deposit across sections keeps a span anchor and never pretends
 *  to be one node. */
function armSpan() {
  const sp = spanState();
  if (!sp) return;
  arm({ grade: "span", sections: sp.sections, rows: sp.rows, blockId: "", kind: "",
        sectionId: sp.sections[0], sectionTitle: sp.rows[0].title,
        file: "", lineStart: 0, lineEnd: 0, quote: "", start: 0, end: 0,
        before: "", after: "", tex: "" });
}

function disarm() {
  C.armed = null; C.echo = null; C.needActor = ""; C.pending = null;
  C.scope = ""; C.scopeSource = ""; C.suggested = ""; C.disposition = ""; C.altitude = "";
  dropArmedMark(); paintMarks();
  compQuote.value = ""; compBody.value = "";
  renderComposer();
  settleRail();
  takeDoor();
  paper.focus();
}

// ── the frozen suggestion ────────────────────────────────────────────────────────────────

function suggestScope(hay, grade, shape) {
  const s = String(hay || "");
  if (s.trim().length < 3) return "";
  // the grade rule first — it is the more specific claim (this vocabulary, made with THIS
  // gesture), and it is the only path the three gestureless scopes have.
  const gr = gradeRuleFor(String(grade || ""), String(shape || ""));
  if (gr) {
    gr[2].lastIndex = 0;
    if ((s.match(gr[2]) || []).length > 0) return gr[1];
  }
  let bestScope = "", best = 0, tied = false;
  for (const [scope, re] of RULES) {
    re.lastIndex = 0;
    const n = (s.match(re) || []).length;
    if (n > best) { best = n; bestScope = scope; tied = false; }
    else if (n === best && n > 0) tied = true;
  }
  if (best > 0 && !tied) return bestScope;
  // a span with no apparatus vocabulary IS a structural deposit — the spine is the
  // structural surface, and that is the default the meta rule leans away from.
  if (String(grade || "") === "span") return "structure";
  return "";
}

function updateSuggestion() {
  const a = C.armed;
  const next = suggestScope(compBody.value + " " + (a ? a.quote : ""),
                            a ? a.grade : "", shapeOf());
  if (next === C.suggested) return false;
  C.suggested = next;
  return true;
}

// ═════════════════════════════════════════════════════════════════════════════════════════
// 14 · THE COMPOSER'S FACE
// ═════════════════════════════════════════════════════════════════════════════════════════

const ledgerPath = () =>
  (S.ctx && S.ctx.feedback_ledger) || "the project's feedback ledger";

function autosize(node, maxFrac) {
  node.style.height = "auto";
  node.style.height = Math.min(node.scrollHeight + 2,
    Math.round(window.innerHeight * maxFrac)) + "px";
}

function sizeFields() {           // G6 — each takes its lines, within a bounded maximum
  if (!compQuote.hidden) autosize(compQuote, 0.34);
  if (!compBody.hidden) autosize(compBody, 0.26);
}

/** which row shape enter will bank. The object he touched decides: no mode, no extra key.
 *  Named before Enter, in the composer, where he is looking. */
/** Does this anchor put an EDITABLE PASSAGE in the composer? Only a real selection whose
 *  rendered face is prose. A block that shows its own source has no prose to type over,
 *  and its rewrite gesture is the in-place flip, not this rail. */
function quotable(a) {
  return !!(a && a.grade === "selection" && !a.texFace);
}

function shapeOf() {
  const a = C.armed;
  if (!a) return "comment";
  if (!quotable(a)) return "comment";
  const changed = norm(compQuote.value) !== norm(a.quote);
  const note = compBody.value.trim();
  if (changed && note) return "compound";
  if (changed) return "rewrite";
  return "comment";
}

function whereWords(a) {
  if (!a) return "";
  if (a.grade === "artefact") return "the whole paper";
  if (a.grade === "span") {
    return "a span of " + a.sections.length + " section"
         + (a.sections.length === 1 ? "" : "s") + ": " + a.rows.map((r) => r.title).join(" · ");
  }
  return (a.sectionTitle ? "§" + a.sectionTitle : "an unnamed section")
       + " · " + (a.kind || "para") + " block";
}

function hintWords() {
  const home = S.door ? S.door.label : "the paper";
  return "Alt+1–6 sets the scope from anywhere, the passage and the note included. A bare "
    + "digit there TYPES — and the passage says so the moment it does. Tab to a scope "
    + "chip, this line, or the line above, and a bare 1–6 sets it. "
    + "7/8/9 rules the passage keep · cut · rework. "
    + "Enter banks. Shift-Enter is a new line. Esc → " + home + ".";
}

/** What the RULING will do, said before Enter — the same law the scope line holds: the
 *  promise he reads before the key and the row that lands are one truth. */
function rulingWords() {
  if (!C.disposition) return "";
  const a = C.armed;
  const altitude = C.altitude
    || (a && (a.grade === "artefact" || a.grade === "span") ? ""
        : (a && a.specId ? "paragraph" : "section"));
  const token = a && expectedOf(blockById.get(a.blockId)).length;
  return " It carries your RULING — " + C.disposition.toUpperCase()
    + (altitude ? " at " + altitude + " altitude" : " (no single passage, so no altitude)")
    + (altitude === "paragraph" && token
       ? ", compared against this passage's own identity: if it moved while you were reading, "
         + "the door refuses and says so rather than banking a ruling on text you never saw."
       : ".");
}

function shapeWords() {
  const a = C.armed;
  if (!a) return null;
  const shape = shapeOf();
  if (shape === "comment") {
    if (a.grade === "artefact") return { lead: "Enter banks a ", kind: "COMMENT",
      tail: " on the whole paper — an artefact-grade row with no source span."
          + rulingWords() };
    if (a.grade === "span") return { lead: "Enter banks a ", kind: "COMMENT",
      tail: " on the span — a span-grade row over " + a.sections.length + " sections."
          + rulingWords() };
    if (a.texFace) return { lead: "Enter banks a ", kind: "COMMENT",
      tail: " against " + srcSpanWords(a) + ". This block shows its own LaTeX source, so "
          + "there is no prose here to type over and none is put in this rail. Press `s` "
          + "at the block to open its source in place and write it back from there." };
    return { lead: "Enter banks a ", kind: "COMMENT",
      tail: " against " + srcSpanWords(a) + ". Edit the passage above and it becomes a "
          + "rewrite instead." + rulingWords() };
  }
  const where = spliceState(a);
  const how = where === "once"
    ? " and splices " + srcSpanWords(a) + ": the passage sits there exactly once, and only "
      + "those characters change — the rest of the block's source is written back untouched."
    : where === "in-math"
      ? " against " + srcSpanWords(a) + ". This selection lies inside RENDERED MATH, and "
        + "rendered math is not addressable as prose: the glyphs on the page are not in "
        + "the source, so writing your text back there would be a guess. It banks a "
        + "pending rewrite and says so. Press `s` at the block to edit its source in place."
      : where === "in-piece"
      ? " against " + srcSpanWords(a) + ". This selection lies inside a rendered CITATION "
        + "or MACRO — the number you see is resolved from the built bibliography, not "
        + "written in the source — so it banks a pending rewrite and says so. Select the "
        + "prose around it to splice, or press `s` to edit the block's source in place."
    : where === "twice"
      ? " against " + srcSpanWords(a) + ". These words appear more than once in that block, "
        + "so the door would be choosing which one you meant: it banks a pending rewrite "
        + "instead and says so. Select a longer passage to make it splice."
      : " against " + srcSpanWords(a) + ". The passage does not sit in that source as one "
        + "run (math, a citation, or a macro runs through it), so the door banks a pending "
        + "rewrite and says so — nothing is guessed.";
  return shape === "compound"
    ? { lead: "Enter banks a ", kind: "COMPOUND ROW", tail: " — the replacement and the "
        + "rationale together" + how }
    : { lead: "Enter banks a ", kind: "REWRITE", tail: how };
}

function srcSpanWords(a) {
  if (!a.file) return "no resolved source span";
  return a.file + (a.lineStart ? ":" + a.lineStart
    + (a.lineEnd > a.lineStart ? "–" + a.lineEnd : "") : "");
}

/** the altitude the rewrite door applies when the gesture names none — the mirror of
 *  `review_surface._REWRITE_DEFAULT_SCOPE` / `_REWRITE_DEFAULT_SCOPE_SOURCE`. It is stated
 *  here so the composer can say the truth BEFORE Enter; the value that reaches the ledger
 *  is still the door's own (the echo reads `rec.scope` back off the server's record). */
const DOOR_DEFAULT_SCOPE = "sentence";
const DOOR_DEFAULT_SOURCE = "default";

/** ONE TRUTH, stated before enter. The pre-Enter line and the banked row have to agree.
 *
 *  This line used to say "banks UNSCOPED" for every shape, and for a REWRITE that was
 *  false in the same frame: the rewrite door applies its own `sentence` default, so the
 *  receipt one keystroke later read "sentence altitude" for the gesture the composer had
 *  just promised would bank unscoped. A comment with no digit does bank unscoped — that
 *  path is first-class and the band can scope it afterwards. So the line branches on the
 *  shape Enter will actually take, and names whichever of the two actually happens. */
function routeLine() {
  const dest = ledgerPath();
  if (C.scope) {
    return { lead: C.scope + " → ", dest,
             tail: "; it reads back at " + C.scope + " altitude on the findings board." };
  }
  if (shapeOf() !== "comment") {
    return { lead: "no scope chosen — the rewrite door banks it at its own "
                 + DOOR_DEFAULT_SCOPE + " default → ", dest,
             tail: ", recorded scope_source " + DOOR_DEFAULT_SOURCE + " so it never reads "
                 + "as an altitude you picked"
                 + (C.suggested ? ", with the rule's lean (" + C.suggested + ") banked "
                     + "beside it as suggested_scope" : "")
                 + ". A digit sets it yourself." };
  }
  if (C.suggested) {
    return { lead: "no scope chosen — banks UNSCOPED → ", dest,
             tail: "; the rule's lean (" + C.suggested + ") is banked beside it as "
                 + "suggested_scope, so its override rate stays derivable." };
  }
  return { lead: "no scope chosen — banks UNSCOPED → ", dest,
           tail: "; scope it later from the band, where an unscoped row carries the six "
               + "altitudes as its own control." };
}

/** The ruling chips, beside the altitude chips and built the same way — one row source, so a
 *  ruling the door would refuse cannot be offered. The second line of each chip is what the
 *  ruling MEANS for the passage, because `cut` on a paragraph of his own manuscript is not a
 *  word to guess at from a three-letter chip. */
function setDisposition(value) {
  C.disposition = C.disposition === value ? "" : value;
  if (!C.disposition) C.altitude = "";
  renderComposer();
}

function renderRulingChips() {
  if (!compRulings) return;
  compRulings.textContent = "";
  DISPOSITIONS.forEach((d, i) => {
    const b = el("button", "chip");
    b.type = "button";
    b.dataset.ruling = d;
    b.setAttribute("aria-pressed", C.disposition === d ? "true" : "false");
    b.appendChild(el("span", "k", String(i + 7)));
    b.appendChild(el("span", null, d));
    b.addEventListener("click", () => setDisposition(d));
    compRulings.appendChild(b);
  });
}

function rulingKey(ev) {
  if (ev.ctrlKey || ev.metaKey) return false;
  if (!/^[789]$/.test(ev.key)) return false;
  if (!ev.altKey && inField(ev.target)) return false;    // in a field a bare digit TYPES
  if (!C.armed) return false;
  setDisposition(DISPOSITIONS[Number(ev.key) - 7]);
  return true;
}

function renderScopeChips() {
  compScopes.textContent = "";
  SCOPES.forEach((s, i) => {
    const b = el("button", "chip");
    b.type = "button";
    b.dataset.scope = s;
    b.setAttribute("aria-pressed", C.scope === s ? "true" : "false");
    if (C.suggested === s) b.dataset.suggested = "1";
    b.appendChild(el("span", "k", String(i + 1)));
    b.appendChild(el("span", null, s));
    b.addEventListener("click", () => setScope(s, "chosen"));
    compScopes.appendChild(b);
  });
}

function renderComposer() {
  const a = C.armed;
  const show = !!(a || C.echo || C.needActor);
  composer.hidden = !show;
  if (!show) return;
  // the armed and actor-ask states claim the rail; a BARE ECHO does not (his ruling:
  // the band never claims width on its own) — a typed edit's echo lives on the card,
  // and a composer bank opens the band itself in the frame of the bank.
  if ((a || C.needActor) && C.rail === "strip") openRail("armed");

  const armedNow = !!a;
  const hasQuote = quotable(a);
  compWhere.hidden = !armedNow;
  compQuote.hidden = !hasQuote;
  compQuoteLbl.hidden = !hasQuote;
  compBody.hidden = !armedNow;
  compBodyLbl.hidden = !armedNow;
  compScopes.hidden = !armedNow;
  // the ruling chips ride with the altitude chips: both are properties of a DEPOSIT, and a
  // rewrite gesture (an edited passage) is not a ruling about the passage, it IS the new one
  if (compRulings) compRulings.hidden = !armedNow;
  compShape.hidden = !armedNow;
  compRoute.hidden = !armedNow;
  compHint.hidden = !armedNow;
  compSuggest.hidden = !(armedNow && C.suggested && C.suggested !== C.scope);

  // the passage says when it has been edited, at the field, in the frame of the keystroke.
  // One bare digit typed here IS the rewrite gesture — the felt boundary says a digit in a
  // field types — so the surface names the conversion rather than letting it be discovered
  // at the receipt. `data-edited` carries the same fact to the field's own border.
  const edited = hasQuote && norm(compQuote.value) !== norm(a.quote);
  if (hasQuote) {
    compQuote.dataset.edited = edited ? "1" : "";
    compQuoteLbl.textContent = edited
      ? "the passage — EDITED, so Enter banks a rewrite. Alt+1–6 sets the altitude; a bare "
        + "digit here types."
      : "the passage — edit it and Enter banks a rewrite";
  }

  if (armedNow) {
    compWhere.textContent = "";
    compWhere.appendChild(el("b", null, whereWords(a)));
    compWhere.appendChild(el("span", "grade",
      "  ·  anchor grade " + (a.grade === "selection" ? "block" : a.grade)));
    if (a.grade === "selection") {
      compWhere.appendChild(el("span", "path", "  " + srcSpanWords(a)));
    }
    renderScopeChips();
    renderRulingChips();
    if (!compSuggest.hidden) compSuggest.textContent = "suggests " + C.suggested + " — take it";
    const sh = shapeWords();
    compShape.textContent = "";
    if (sh) {
      compShape.appendChild(el("span", null, sh.lead));
      compShape.appendChild(el("b", null, sh.kind));
      compShape.appendChild(el("span", null, sh.tail));
    }
    const r = routeLine();
    compRoute.textContent = "";
    compRoute.appendChild(el("span", null, r.lead));
    compRoute.appendChild(el("span", "dest", r.dest));
    compRoute.appendChild(el("span", null, r.tail));
    compHint.textContent = hintWords();
  }

  compActor.hidden = !C.needActor;
  if (C.needActor) {
    compActorNote.textContent = C.needActor;
    compActorInput.placeholder = "who is depositing";
  }
  compEcho.hidden = !C.echo;
  if (C.echo) {
    compEcho.textContent = C.echo.text;
    compEcho.dataset.tone = C.echo.tone || "banked";
  }
}

function setScope(scope, source) {
  C.scope = C.scope === scope ? "" : scope;
  C.scopeSource = C.scope ? source : "";
  renderComposer();
}

export {
  C, DISPOSITIONS, RULE_SET_ID, SCOPES, arm, armArtefact, armBlockAtReadingLine, armFromSelection, armSpan,
  askActor, autosize, bandCount, bandList, bandMix, bandNote, bandSpan, compActorInput, compActorOk, compBody,
  compQuote, compSuggest, composer, disarm, dropArmedMark, ledgerPath, loadActor, nameActor, openRail,
  paintMarks, railCount, renderComposer, rulingKey, setDisposition, setScope, settleRail, shapeOf,
  srcSpanWords, toggleRail, updateSuggestion
};
