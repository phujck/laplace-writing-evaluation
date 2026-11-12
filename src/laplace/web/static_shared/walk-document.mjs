// WALK DOCUMENT (S2 F3). Purpose: the one document model of the canvas and its owner reads: the
// project context behind the geometry door, GET /walk/doc read defensively, adoption of a whole
// document and of owner-delivered sections, and the scoped re-read after a save (_reloadBlock),
// which re-adopts identity witnesses and re-places parked drafts. Owns: D (the model), OWNER_READ
// (the owner-read sequence that alone advances a block's readSeq), docIdentities, blockById and the
// in-flight reload. Public contract: loadContext, loadDoc, normalizeDoc, adopt/adoptBlockModel,
// expectedOf, reloadBlock (awaitable through RELOAD_INFLIGHT), paintBackDoor/paintBadge. Currentness:
// only an actual owner response advances readSeq; a locally assigned postimage never verifies a
// draft; merge-held sections keep their original witnesses. Transport is store.mjs and the source
// client; no second model clone or cache lives here.
import store from "/shared/store.mjs";
import {
  canRefreshBlockInPlace, manuscriptDocumentVersion, manuscriptPresentationVersion, planScopedReload
} from "/shared/manuscript-editing.mjs";
import {backDoor, badge, docFail, docNote, el, emit, geoDoor, text} from './walk-base.mjs';
import {
  S, buildSpine, captureFocus, forgetPaintedSection, litNode, measure, restoreFocus
} from './walk-position.mjs';
import {renderBlockBody, renderDoc} from './walk-blocks.mjs';
import {autosize, paintMarks} from './walk-composer.mjs';
import {hostText, nodeAt, offsetIn, srcOf} from './walk-selection.mjs';
import {
  E, P, assignBasis, captureBasis, paintParked, parkEdit, rekeyRows, restoreFace, restoreParked
} from './walk-drafts.mjs';
import {showStructuralOutcome} from './walk-edit-history.mjs';
import {checkOrphans, paintDeposits} from './walk-band.mjs';
import {editableBlock} from './walk-editing.mjs';
import {cardNote, caretRange, editorInsertionPoint} from './walk-card.mjs';
import {LK, blockLabels} from './walk-where.mjs';
import {paragraphTransition, rememberParagraphCaret} from './walk-paragraph-ops.mjs';
import {refreshProposalView} from './walk-review.mjs';

// ── the document model, exactly the shape /walk/doc serves ───────────────────────────────
/** @type {{ok:boolean, corpus:string, title:string, macros:object, citations:object,
 *           refs:object, sections:Array, unknown:number, note:string}} */
const D = { ok: false, corpus: "", title: "", macros: {}, citations: {}, refs: {},
            sections: [], unknown: 0, note: "" };

//: `{home: token}` for every fragment FILE of the document, exactly as `/walk/doc?identities=1`
//: published it: the `section` and `chapter` homes a ruling at those altitudes is gated on. It
//: is refreshed by every read of the document and by nothing else, so it always names the bytes
//: the canvas is showing. Empty for a document handed in by a host (no read, no tokens).
let docIdentities = {};

const blockById = new Map();

// ═════════════════════════════════════════════════════════════════════════════════════════
// 1 · the context and the named artefact behind the geometry door
// ═════════════════════════════════════════════════════════════════════════════════════════

/** The corpus in view: the URL model first, then walk.py's echo of the ?corpus= query.
 *  Neither RESOLVES a default — /artefact/context does that, server-side, and names it. */
function seedCorpus() {
  const fromUrl = store.field("corpus");
  if (fromUrl) return fromUrl;
  const meta = document.querySelector('meta[name="walk:corpus"]');
  return (meta && meta.getAttribute("content")) || "";
}

/** the handover law, resolved server-side: the geometry face is the newest NAMED, dated,
 *  revisioned release; falling back to the working pdf SAYS SO. */
function resolveSource(ctx) {
  const working = ctx.current_artefact || {};
  if (working.pdf && working.kind !== "release") {
    return {pdf: working.pdf, named: false, label: "last compiled PDF"};
  }
  const named = ctx.named_release || {};
  if (named.present && named.pdf) {
    // the context's own label is phrased for a surface that READS the pdf ("reading: …").
    // Here the pdf is the geometry face, not the reading canvas, so the artefact is named
    // and the phrasing is this surface's: one fact, said once, in the right register.
    const stem = named.stem || named.name
              || String(named.pdf).split("/").pop().replace(/\.pdf$/i, "");
    return { pdf: named.pdf, named: true, label: "the typeset " + stem };
  }
  const cur = ctx.current_artefact || {};
  if (cur.pdf) {
    return { pdf: cur.pdf, named: false,
             label: "the typeset " + String(cur.pdf).split("/").pop() + " (no named release)" };
  }
  return null;
}

async function loadContext() {
  S.corpus = seedCorpus();
  if (S.corpus) store.set({ corpus: S.corpus }, { replace: true });
  let ctx = null;
  try {
    ctx = await store.fetchJSON("/artefact/context");
  } catch (e) {
    text(badge, "no artefact context — the geometry face has nothing to open. (" + e.message + ")");
    geoDoor.disabled = true;
    paintBackDoor();          // the way back is never a casualty of a door that refused
    return null;
  }
  S.ctx = ctx;
  if (ctx.corpus && ctx.corpus !== S.corpus) {
    S.corpus = ctx.corpus;
    store.set({ corpus: ctx.corpus }, { replace: true });
  }
  S.source = resolveSource(ctx);
  geoDoor.disabled = !S.source;
  paintBackDoor();
  return ctx;
}

/** the named return door, carrying the corpus in view. A LINK, never an import: the clean
 *  room's allowlist governs what this module imports, and it imports nothing new for this.
 *  With no corpus resolved the door stays bare and the artefact surface resolves its own —
 *  one authority, not two guesses. */
function paintBackDoor() {
  if (!backDoor) return;
  backDoor.href = S.corpus ? "/artefact?corpus=" + encodeURIComponent(S.corpus)
                           : "/artefact";
}

function paintBadge() {
  badge.textContent = "";
  const head = el("b", null, D.title || S.corpus || "this project");
  badge.appendChild(head);
  const tail = el("span", null, "  ·  the text, content-faithful"
    + (S.source ? "  ·  geometry face: " + S.source.label : "  ·  no typeset face on disk"));
  tail.style.color = "var(--ink-faint)";
  badge.appendChild(tail);
}

// ═════════════════════════════════════════════════════════════════════════════════════════
// 3 · the document model — GET /walk/doc, read defensively
// ═════════════════════════════════════════════════════════════════════════════════════════

/** Normalise whatever the door returns into the block model this canvas codes to. Every
 *  field is optional at the wire and total in here: a payload missing a piece list, a
 *  source span, or a whole section list renders what's there rather than crashing. */
function normalizeDoc(raw) {
  const d = (raw && typeof raw === "object") ? raw : {};
  const macros = {};
  for (const [k, v] of Object.entries(d.macros || {})) {
    if (typeof v !== "string") continue;
    macros[String(k).startsWith("\\") ? String(k) : "\\" + k] = v;
  }
  const citations = {};
  for (const [k, v] of Object.entries(d.citations || {})) {
    if (v && typeof v === "object") citations[k] = { num: v.num, entry: v.entry || "" };
    else citations[k] = { num: v, entry: "" };
  }
  const refs = {};
  for (const [k, v] of Object.entries(d.refs || {})) refs[k] = v;

  const sections = [];
  const rawSections = Array.isArray(d.sections) ? d.sections : [];
  rawSections.forEach((s, si) => {
    const sid = String((s && s.id) || ("section-" + (si + 1)));
    const blocks = [];
    (Array.isArray(s && s.blocks) ? s.blocks : []).forEach((b, bi) => {
      if (!b || typeof b !== "object") return;
      const src = b.src && typeof b.src === "object" ? b.src : {};
      blocks.push({
        id: String(b.id || (sid + "#b" + (bi + 1))),
        kind: String(b.kind || "para"),suggestion:b.suggestion===true||b.change_preview===true,
        level: String(b.level || ""),
        tex: typeof b.tex === "string" ? b.tex : "",
        src: { file: String(src.file || (s && s.file) || ""),
               repo_file: String(src.repo_file || ""),
               line_start: Number(src.line_start || 0),
               line_end: Number(src.line_end || src.line_start || 0) },
        // THE IDENTITY TOKENS THE READ PUBLISHED, carried whole and never recomputed
        // (WRITING-CONSOLIDATION-W1). The field is the one the request takes, so a save is a
        // copy; the array is empty when the read was asked without `identities=1`, and the
        // door's byte guard decides exactly as it did before.
        expected: (Array.isArray(b.expected) ? b.expected : [])
          .filter((t) => typeof t === "string" && t),
        // THE PIECES, CARRIED WHOLE. Each one holds `{o_start, o_end}` — its char span
        // inside `tex` — and that pair is what makes the rendered-char → source-char map
        // piecewise-exact. Copying only the render fields here would leave the locator
        // prose-only again, which is the narrowing this closes.
        pieces: Array.isArray(b.pieces) ? b.pieces : null,
        presentation_only: b.presentation_only===true,
        items: Array.isArray(b.items) ? b.items : null,
        rows: Array.isArray(b.rows) ? b.rows : null,
        ordered: b.ordered === true || String(b.env || "") === "enumerate",
        math: typeof b.math === "string" ? b.math : "",
        equation_labels: Array.isArray(b.equation_labels) ? b.equation_labels : [],
        number: (typeof b.number === "string" || typeof b.number === "number") ? String(b.number) : "",
        env: String(b.env || ""),
        custom_kind: String(b.custom_kind || ""),
        presentation: b.presentation || {},
        title_prefix: String(b.title_prefix || ""), title_suffix: String(b.title_suffix || ""),
        theorem_label:String(b.theorem_label||""),theorem_optional_title:b.theorem_optional_title===true,theorem_numbered:b.theorem_numbered===true,
        image: String(b.image || ""),
        images: Array.isArray(b.images) ? b.images : [],
        preview_image: String(b.preview_image || ""),
        caption: typeof b.caption === "string" ? b.caption : "",
        caption_separate: b.caption_separate===true,
        caption_of: b.caption_of||null,
        caption_pieces: Array.isArray(b.caption_pieces) ? b.caption_pieces : null,
        title: typeof b.title === "string" ? b.title : "",
        title_pieces: Array.isArray(b.title_pieces) ? b.title_pieces : null,
        tail_pieces: Array.isArray(b.tail_pieces) ? b.tail_pieces : null,
        tail: String(b.tail || ''),
        text: typeof b.text === "string" ? b.text : "",
        // Preserve all planned units of this rendered occurrence. The scalar remains
        // legacy data; it cannot stand in for a merged occurrence's provenance.
        spec_id: typeof b.spec_id === "string" ? b.spec_id : "",
        spec_ids: Array.isArray(b.spec_ids) ? b.spec_ids.filter(id=>typeof id==="string") : undefined,
        source_section: typeof b.source_section === "string" ? b.source_section : "",
        restructure_preview: b.restructure_preview || null,
        label: typeof b.label === "string" ? b.label : "",
        labels: Array.isArray(b.labels) ? b.labels : [],
        sectionId: sid,
        el: null, bodyEl: null, texFace: false,
      });
    });
    sections.push({ id: sid, title: String((s && s.title) || "(untitled section)"),
                    file: String((s && s.file) || ""),
                    depth: Number((s && (s.depth != null ? s.depth : s.level)) || 0),
                    blocks });
  });
  return { ok: d.ok !== false, corpus: String(d.corpus || ""), title: String(d.title || ""),
           macros, citations, refs, sections, documentVersion:manuscriptDocumentVersion(d),presentationVersion:manuscriptPresentationVersion(d),
             sourceObservation:{project:d.project,source_observation:d.source_observation,presentation_revision:d.presentation_revision,
             current_revision:d.current_revision},citation_targets:Array.isArray(d.citation_targets)?d.citation_targets:[],
           pending_restructures: Array.isArray(d.pending_restructures) ? d.pending_restructures : [],
           // the owner's per-section witnesses (G14): every section's id, file, block count and
           // source file revision, whatever subset of sections this answer delivered
           sectionIndex: Array.isArray(d.section_index) ? d.section_index : [],
           selectedSections: Array.isArray(d.selected_sections) ? d.selected_sections : null,
           note: String(d.note || d.error || "") };
}

async function loadDoc(providedDocument) {
  docNote.hidden = false;
  text(docNote, "building the content-faithful projection…");
  let raw, issued = 0;
  try {
    // `identities=1` asks for the tokens this canvas sends back in `expected`: one `prose`
    // token per block and the `section`/`chapter` token of each fragment FILE.
    //
    // EVERY WALK LOAD SETS IT, READER OR EDITOR, and that is the measured cost of this packet:
    // the walk is also how the author READS, and there is no read-only canvas to gate it on, so
    // the parameter is an editor's ask only in the sense that the editor is the one who needs
    // it. On his own manuscript (1,271 blocks, 4 fragment files) the read goes from 1,466,581 to
    // 1,661,568 bytes --- +194,987 (+13.3 per cent), of which the file-level tokens are 1,564 ---
    // while the TIME is below this measurement's noise floor: two medians of five runs each gave
    // 181.0 -> 183.1 ms and then 204.5 -> 190.0 ms, so the cost is bytes and not latency. The
    // other callers of this door
    // (the PDF leg, the front carrier, a host handing in a document) do NOT set it and pay
    // nothing; an embedded document arrives without tokens and the byte guard decides, exactly
    // as before. Whether that 13 per cent is worth paying on a read is the measure and storage
    // lanes' call against guarantees B and C, and it is a residual of this packet, not a claim.
    issued = providedDocument ? 0 : issueRead();
    raw = providedDocument || await store.fetchJSON("/walk/doc", {params: {identities: 1}});
    // A READ NEVER REPLACES CONTENT NEWER THAN ITSELF: a read answered before a save's write but
    // delivered after a later read was adopted (a refresh racing a save and its read-back) would
    // put the old bytes and their tokens back on the page; it is read again instead.
    if (staleRead(issued)) return loadDoc();
    docIdentities = (raw && raw.identities && typeof raw.identities === "object")
      ? raw.identities : {};
  } catch (e) {
    docFail("the document model door did not answer. The walk's canvas is built server-side "
      + "from the fragment files and the build artifacts, and served at GET /walk/doc; until "
      + "that door answers there is nothing content-faithful to render. The geometry face — "
      + "the typeset pdf — still opens from the head of the bar. (" + e.message + ")");
    return false;
  }
  if(paragraphTransition)rememberParagraphCaret(paragraphTransition.draft);
  const caretBefore=editorInsertionPoint(),caretBlock=caretBefore?blockById.get(caretBefore.blockId):null;
  const caretFollowing=caretBlock?S.blocks[S.blocks.indexOf(caretBlock)+1]:null;
  const caretSource=caretBlock?{...srcOf(caretBlock)}:null;
  const caretAtEnd=caretBefore&&caretBlock?.bodyEl&&caretBefore.start===caretBefore.end&&caretBefore.end>=hostText(caretBlock.bodyEl).trimEnd().length;
  const next = normalizeDoc(raw);
  if (!next.ok) {
    docFail("the document model door answered, but refused: "
      + (next.note || "it reported no reason.") + " Nothing is rendered rather than "
      + "something half-built. The geometry face still opens from the head of the bar.");
    return false;
  }
  if (!next.sections.length) {
    docFail("the document model door answered with no sections. Either this project's "
      + "fragment files are not where the door looks, or the parse found nothing it could "
      + "type. The geometry face still opens from the head of the bar."
      + (next.note ? " The door said: " + next.note : ""));
    return false;
  }
  adopt(next, issued);
  return true;
}

// THE OWNER-READ WITNESS. Every block the canvas holds was delivered by some owner read;
// `readSeq` on a block is the ordinal of the read that delivered it. A draft awaiting its
// saved postimage (`verifyAwaiting`) resolves only against a block delivered by a read made
// AFTER the save — a locally assigned `tex` is not a read and never verifies anything.
const OWNER_READ = { seq: 0 };
// The order reads were ISSUED in (`issued`), beside the adoption ordinal `seq`: `newest` is the
// issue number of the latest read whose content the canvas adopted. A read issued before that one
// carries older content however late it arrives (`staleRead`).
function issueRead() { OWNER_READ.issued = (OWNER_READ.issued || 0) + 1; return OWNER_READ.issued; }
function staleRead(issued) { return !!issued && issued < (OWNER_READ.newest || 0); }
function adoptedRead(issued) { if (issued) OWNER_READ.newest = Math.max(OWNER_READ.newest || 0, issued); }
function adopt(next, issued = 0) {
  adoptedRead(issued);
  OWNER_READ.seq += 1;
  for (const s of next.sections) for (const b of s.blocks) b.readSeq = OWNER_READ.seq;
  D.ok = next.ok; D.corpus = next.corpus; D.title = next.title;
  D.macros = next.macros; D.citations = next.citations; D.refs = next.refs;D.citation_targets=next.citation_targets;
  D.sections = next.sections; D.note = next.note;D.documentVersion=next.documentVersion;D.presentationVersion=next.presentationVersion;
    D.sourceObservation=next.sourceObservation;D.pending_restructures=next.pending_restructures;
  D.labelTargets=new Map(next.sections.flatMap(s=>s.blocks.flatMap(b=>blockLabels(b).map(label=>[label,b]))));
  // A whole adoption holds every delivered section at the owner's witness: nothing is stale.
  D.sectionIndex=next.sectionIndex||[];D.sectionWitness=Object.fromEntries(D.sectionIndex.map(row=>[row.id,row.file_revision]));D.staleSections=new Set();
  D.unknown = 0;
}

/** The identity tokens the READ published for this block, ready to copy into `expected`.
 *
 *  Read, never derived: `/walk/doc?identities=1` mints the `prose` token of each block's own
 *  addressed span server-side, over the same bytes the door compares. A surface that hashed
 *  the text it happens to hold would be a second producer of one identity, which is the
 *  twenty-names defect with the names hidden inside two functions. A block the read published
 *  no token for sends none, and the door's byte guard still decides. */
function expectedOf(b) {
  const tokens = b && b.expected;
  return Array.isArray(tokens) ? tokens.filter((t) => typeof t === "string" && t) : [];
}

/** THE ONE ADOPTION SEAM for owner-issued block data on a live block. A scoped re-read
 *  (`_reloadBlock`, same shape) carries the door's fresh model onto the blocks already on
 *  the canvas: source text, spans, piece maps and the identity witnesses the read published
 *  move TOGETHER, so no field the owner issues can lag another. The served snapshot adopted
 *  tex/src/pieces here and left `expected` behind, so the very next ordinary edit sent the
 *  token of the bytes the author had just replaced and the door refused its own author
 *  (root B6, 2026-10-12). Local editing state (`el`, `bodyEl`, `pieceMap`, `texFace`,
 *  `sectionId`) is not the owner's and is not touched here. */
function adoptBlockModel(b, n) {
  b.tex = n.tex; b.src = n.src; b.pieces = n.pieces; b.expected = expectedOf(n); b.readSeq = OWNER_READ.seq;
  b.presentation_only = n.presentation_only; b.math = n.math; b.equation_labels = n.equation_labels; b.number = n.number; b.env = n.env;
  b.custom_kind = n.custom_kind; b.presentation = n.presentation; b.preview_image = n.preview_image;
  b.title_prefix = n.title_prefix; b.title_suffix = n.title_suffix; b.theorem_label = n.theorem_label;
    b.theorem_optional_title = n.theorem_optional_title; b.theorem_numbered = n.theorem_numbered;
  b.title_pieces = n.title_pieces; b.tail_pieces = n.tail_pieces; b.tail = n.tail; b.items = n.items; b.rows = n.rows; b.ordered = n.ordered;
  b.image = n.image; b.images = n.images; b.caption = n.caption; b.caption_separate = n.caption_separate; b.caption_of = n.caption_of; b.caption_pieces = n.caption_pieces;
  b.title = n.title; b.text = n.text; b.kind = n.kind; b.level = n.level; b.suggestion = n.suggestion;
  b.spec_id = n.spec_id; b.spec_ids = n.spec_ids; b.source_section = n.source_section; b.restructure_preview = n.restructure_preview; b.label = n.label; b.labels = n.labels;
  return b;
}

/** Every reload is tracked: commit-class gestures await the in-flight one before reading
 *  spans (the reload window the 2026-08-11 chair measured). */
async function reloadBlock(blockId) {
  const p = _reloadBlock(blockId);
  RELOAD_INFLIGHT = p;
  try { return await p; }
  finally { if (RELOAD_INFLIGHT === p) RELOAD_INFLIGHT = null; }
}

// A section-scoped reload (G14): the owner delivers the edited block's section plus the
// document-level fields and `section_index`, the per-section witnesses. The plan
// (`planScopedReload`) compares those witnesses with the ones this canvas holds: a changed
// section list means a whole read; held sections whose file revision moved (an external
// edit elsewhere, or a splice that shifted later spans in the same file) are fetched in one
// more scoped read so every held section is reconciled, not only the edited one. Only
// when the merged model can be refreshed in place does the merge stand; otherwise the
// whole document is read. The document calls itself current only when no held section is
// stale (see `sourceObservation`), so the idle poll can never miss an undelivered change.
async function fetchDocForBlock(blockId) {
  const held = blockById.get(blockId), sectionId = held?.sectionId;
  if (sectionId && D.sections.length && Array.isArray(D.sectionIndex) && D.sectionIndex.length) {
    const partial = await store.fetchJSON("/walk/doc", {params: {identities: 1, sections: sectionId}});
    if (partial?.ok === false) return {raw: partial, merged: false};
    if (partial?.ok && partial.partial) {
      const plan = planScopedReload({heldIndex: D.sectionIndex, heldWitness: D.sectionWitness || {}, delivered: partial});
      if (!plan.structureChanged) {
        let delivered = partial;
        if (plan.staleSections.length) {
          // Reconcile the other held sections whose source moved, in one scoped read.
          const more = await store.fetchJSON("/walk/doc", {params: {identities: 1, sections: [sectionId, ...plan.staleSections].join(",")}});
          if (!(more?.ok && more.partial) || planScopedReload({heldIndex: D.sectionIndex, heldWitness: D.sectionWitness || {}, delivered: more}).structureChanged) {
            return {raw: await store.fetchJSON("/walk/doc", {params: {identities: 1}}), merged: false};
          }
          delivered = more;
        }
        return {raw: delivered, merged: true, plan};
      }
    }
  }
  return {raw: await store.fetchJSON("/walk/doc", {params: {identities: 1}}), merged: false};
}
function mergeHeldSections(next) {
  const fresh = new Map(next.sections.map(section => [section.id, section]));
  return {...next, sections: D.sections.map(section => fresh.get(section.id) || section)};
}
// After an in-place scoped merge: the delivered sections take the owner's witness; any held
// section the index still shows at another revision stays marked stale.
function adoptWitnesses(next) {
  const delivered = new Set(next.selectedSections || []);
  const witness = {...(D.sectionWitness || {})};
  for (const row of next.sectionIndex || []) if (delivered.has(row.id)) witness[row.id] = row.file_revision;
  D.sectionIndex = next.sectionIndex || D.sectionIndex; D.sectionWitness = witness;
  D.staleSections = new Set((next.sectionIndex || []).filter(row => witness[row.id] !== row.file_revision).map(row => row.id));
}

async function _reloadBlock(blockId) {
  let raw, merged = false;
  const issued = OWNER_READ.issued = (OWNER_READ.issued || 0) + 1;
  try {
    ({raw, merged} = await fetchDocForBlock(blockId));
    // older than content already adopted (see `staleRead`): read again rather than put it back
    if (issued < (OWNER_READ.newest || 0)) return _reloadBlock(blockId);
    docIdentities = (raw && raw.identities && typeof raw.identities === "object")
      ? {...(merged ? docIdentities : {}), ...raw.identities} : (merged ? docIdentities : {});
  } catch (e) {
    return { ok: false, whole: false,
             note: "the doc model door did not answer for the re-render. " + e.message };
  }
  if(paragraphTransition)rememberParagraphCaret(paragraphTransition.draft);
  const caretBefore=editorInsertionPoint(),caretBlock=caretBefore?blockById.get(caretBefore.blockId):null;
  const caretFollowing=caretBlock?S.blocks[S.blocks.indexOf(caretBlock)+1]:null;
  const caretSource=caretBlock?{...srcOf(caretBlock)}:null;
  const caretAtEnd=caretBefore&&caretBlock?.bodyEl&&caretBefore.start===caretBefore.end&&caretBefore.end>=hostText(caretBlock.bodyEl).trimEnd().length;
  let next = normalizeDoc(raw);
  if (!next.ok || !next.sections.length) {
    return { ok: false, whole: false, note: next.note || "the door returned no sections." };
  }
  if (merged) next = mergeHeldSections(next);
  const shapeOf = model => D.presentationVersion===model.presentationVersion&&canRefreshBlockInPlace(S.blocks,model.sections.flatMap(section=>section.blocks),blockId);
  if (merged && !shapeOf(next)) {
    // The section's structure changed: a whole read, so re-adoption starts from one model.
    try {
      raw = await store.fetchJSON("/walk/doc", {params: {identities: 1}});
      docIdentities = (raw && raw.identities && typeof raw.identities === "object") ? raw.identities : {};
    } catch (e) {
      return { ok: false, whole: false, note: "the doc model door did not answer for the re-render. " + e.message };
    }
    next = normalizeDoc(raw); merged = false;
    if (!next.ok || !next.sections.length) return { ok: false, whole: false, note: next.note || "the door returned no sections." };
  }
  const nextById = new Map();
  for (const sec of next.sections) for (const b of sec.blocks) nextById.set(b.id, b);
  const sameShape = shapeOf(next);
  D.macros = next.macros; D.citations = next.citations; D.refs = next.refs;D.citation_targets=next.citation_targets;
  D.labelTargets=new Map(next.sections.flatMap(s=>s.blocks.flatMap(b=>blockLabels(b).map(label=>[label,b]))));
  if (!sameShape) {
    if(E.blockId&&E.dirty){const editing=blockById.get(E.blockId);if(editing)parkEdit(editing);}
    const f = captureFocus();
    adopt(next, issued);
    renderDoc();
    buildSpine();
    LK.facts.clear();
    forgetPaintedSection();
    restoreParked();          // parked faces survive the re-adopt; nothing typed is lost
    measure();
    restoreFocus(f);
    rekeyRows();
    paintDeposits();
    checkOrphans();
    if(caretBefore&&!caretBefore.source&&caretAtEnd&&caretSource){const limit=caretFollowing?S.blocks.find(item=>srcOf(item).file===srcOf(
      caretFollowing).file&&item.tex===caretFollowing.tex):null;const candidates=S.blocks.filter(item=>srcOf(item).file===caretSource.file&&srcOf(
      item).lineStart>=caretSource.lineStart&&(!limit||srcOf(item).lineStart<srcOf(limit).lineStart)&&editableBlock(item));const target=candidates.at(
      -1);if(target?.bodyEl){target.bodyEl.focus({preventScroll:true});const selection=document.getSelection();selection.removeAllRanges();
      selection.addRange(caretRange(target.bodyEl,hostText(target.bodyEl).length));}}
    await refreshProposalView();
    if (D.pending_restructures?.length) showStructuralOutcome(D.pending_restructures[0]);
    emit('document',{blocks:S.blocks.length});
    return { ok: true, whole: true, note: "" };
  }
  D.documentVersion=next.documentVersion;D.presentationVersion=next.presentationVersion;D.sourceObservation=next.sourceObservation;D.pending_restructures=next.pending_restructures;
  if (merged) adoptWitnesses(next); else { D.sectionIndex=next.sectionIndex||[]; D.sectionWitness=Object.fromEntries(D.sectionIndex.map(row=>[row.id,
    row.file_revision])); D.staleSections=new Set(); }
  // carry the door's new source spans and content onto the live blocks: a splice shifts
  // every later line number, and a stale span is a wrong write next time.
  //
  // ONLY THE BLOCKS THIS OWNER RESPONSE DELIVERED take its read witness. A merged model
  // (`mergeHeldSections`) carries the held sections' blocks — the live objects themselves —
  // beside the delivered ones; stamping those would make a draft awaiting its read-back look
  // read back by a response that never carried its block (Sol, 2026-10-12). Held blocks keep
  // their previous witnesses untouched; `selectedSections` is the owner's own statement of
  // what this response delivered.
  OWNER_READ.newest = Math.max(OWNER_READ.newest || 0, issued);
  OWNER_READ.seq += 1;
  const deliveredSections = merged ? new Set(next.selectedSections || []) : null;
  for (const b of S.blocks) {
    const n = nextById.get(b.id);
    if (!n || n === b) continue;
    if (deliveredSections && !deliveredSections.has(n.sectionId)) continue;
    adoptBlockModel(b, n);
    b.el.toggleAttribute('data-presentation-only', !!n.presentation_only);
  }
  const b = blockById.get(blockId);
  if (b && b.bodyEl) {
    // an ACTIVE edit RIDES the re-render (a skipped render left b.tex fresh over a
    // stale pieceMap — a mixed state whose next bank mapped face offsets into the
    // wrong source and refused at the door; measured 2026-08-11b): park it for the
    // swap, re-render, restore the face, resume with the caret where it stood.
    const activeHere = E.blockId === b.id && E.dirty && !(b.el && b.el.dataset.flip);
    let carry = null;
    if (activeHere) {
      const sel0 = document.getSelection();
      let caretAt = null;
      if (sel0 && sel0.rangeCount
          && b.bodyEl.contains(sel0.getRangeAt(0).startContainer)) {
        const r0 = sel0.getRangeAt(0);
        caretAt = offsetIn(b.bodyEl, r0.startContainer, r0.startOffset);
      }
      carry = { caretAt };
      parkEdit(b);
    }
    const f = captureFocus();
    b.el.dataset.kind = b.kind || "para";
    renderBlockBody(b, b.bodyEl);
    paintMarks();
    measure();
    restoreFocus(f);
    litNode(b.el);
    if (P.has(b.id)) restoreFace(b);
    if (carry) {
      const held = P.get(b.id);
      E.blockId = b.id;
      E.pristine = held ? held.pristine : hostText(b.bodyEl);
      assignBasis(E, held ? held : captureBasis(b)); E.review = held ? held.review || "" : "";
      E.dirty = held ? hostText(b.bodyEl) !== held.pristine : false;
      E.scope = held ? held.scope || "" : "";
      if (held && b.el) {
        delete b.el.dataset.parked;
        b.el.dataset.editing = E.dirty ? "1" : "";
      }
      if (held && held.note && cardNote && !cardNote.value) {
        cardNote.value = held.note;
        autosize(cardNote, 0.2);
      }
      if (carry.caretAt != null && b.bodyEl) {
        const at = nodeAt(b.bodyEl, carry.caretAt);
        if (at) {
          try {
            const rr = document.createRange();
            rr.setStart(at.node, at.off);
            rr.collapse(true);
            const s2 = document.getSelection();
            s2.removeAllRanges();
            s2.addRange(rr);
            b.bodyEl.focus();
          } catch (_e) { /* his click recovers the caret */ }
        }
      }
      paintParked();
    }
  }
  if(caretBefore&&!caretBefore.source){const target=blockById.get(caretBefore.blockId);if(target?.bodyEl&&editableBlock(target)){target.bodyEl.focus({
    preventScroll:true});const point=caretAtEnd?hostText(target.bodyEl).length:caretBefore.start;const selection=document.getSelection();
    selection.removeAllRanges();selection.addRange(caretRange(target.bodyEl,point,caretAtEnd?point:caretBefore.end));}}
  checkOrphans();
  await refreshProposalView();
  if (D.pending_restructures?.length) showStructuralOutcome(D.pending_restructures[0]);
  emit('document',{blocks:S.blocks.length});
  return { ok: true, whole: false, note: "" };
}

// The in-flight post-splice reload. A commit-class gesture fired inside the reload window
// read a stale line span and banked PENDING (measured by the chair, 2026-08-11, both
// viewports); commit paths now await this before reading spans.
let RELOAD_INFLIGHT = null;

export {
  D, OWNER_READ, RELOAD_INFLIGHT, blockById, docIdentities, expectedOf, loadContext, loadDoc, normalizeDoc,
  paintBackDoor, paintBadge, reloadBlock
};
