// WALK BANK (S2 F7). Purpose: the composer's deposits through the review door: comment and rewrite
// payloads at the chosen altitude, the receipt in the same frame, and undo of the last deposit.
// Owns: no state beyond what the request carries. Public contract: scopeFields, commentPayload,
// rewritePayload, bankDeposit, undoLast, appliedOf/pendingOf/receiptWords.
import {sourceEffectDisposition} from './source-effect.mjs';
import store from "/shared/store.mjs";
import {emit, paper} from './walk-base.mjs';
import {blockById, docIdentities, expectedOf, reloadBlock} from './walk-document.mjs';
import {S, takeDoor} from './walk-position.mjs';
import {ADJUDICATE, saveSourceChange, sourceRequest} from './walk-source-client.mjs';
import {
  C, askActor, compBody, compQuote, ledgerPath, openRail, paintMarks, renderComposer, shapeOf, srcSpanWords
} from './walk-composer.mjs';
import {spliceOf, srcOf} from './walk-selection.mjs';
import {MINTED, admit, checkOrphans, paintDeposits, renderBand} from './walk-band.mjs';

function scopeFields(p) {
  if (C.scope) { p.scope = C.scope; p.scope_source = C.scopeSource || "chosen"; }
  if (C.suggested) p.suggested_scope = C.suggested;
  return p;
}

/** The CONTAINER's token for a section- or chapter-altitude ruling: the FILE's, AS READ.
 *
 *  A paragraph ruling's container is the addressed span and the canvas already holds that token
 *  per block. A section or chapter ruling's container is the whole FILE, and until this the
 *  canvas held no file token — so the editor could send a token at ONE of the three altitudes it
 *  rules at, and a section ruling banked against bytes the author may never have read, which is
 *  the thing the gate exists to prevent.
 *
 *  IT COMES FROM THE SAME READ AS THE BLOCKS, and that is the whole point. The first version of
 *  this fetched `/review/fragment` at the moment of banking — which cannot refuse anything: a
 *  token read a millisecond before the gate is current by construction, so the race between
 *  "what he read" and "what is there now" was invisible to it. `/walk/doc?identities=1` now
 *  publishes the file's `section` and `chapter` tokens beside the per-block `prose` ones
 *  (`walk.py`), so the token this sends is the identity of the bytes the page is SHOWING, and a
 *  file another writer moved since the load is refused with `needed`.
 *
 *  The key is matched, never constructed: the home id carries the PROJECT name, which is the
 *  door's spelling and not the canvas's `corpus`, so the canvas looks for its own file's home
 *  rather than guessing a name it does not own.
 */
function containerToken(a, altitude) {
  const src = srcOf(blockById.get(a.blockId)) || {};
  const file = a.file || src.file || "";
  if (!file || (altitude !== "section" && altitude !== "chapter")) return [];
  const want = altitude + ":", tail = "::" + file;
  for (const home of Object.keys(docIdentities)) {
    if (home.indexOf(want) === 0 && home.slice(-tail.length) === tail) {
      const token = docIdentities[home];
      if (typeof token === "string" && token) return [token];
    }
  }
  return [];
}

/** The altitude one comment gesture rules at, or `""` when it rules on no single container.
 *
 *  The three grains the grammar declares a `note@` pair for (`identity_doors.COMMENT_CONTAINER`).
 *  The artefact and span tiers rule on the whole paper or on several sections and have no one
 *  container, which is why `_container_home` answers `None` for them and why there is no
 *  `note@artefact`: those two gestures are not this request with a different altitude, they are
 *  a different act the grammar has not declared. */
function commentAltitude(a) {
  if (C.altitude) return C.altitude;
  if (a.grade === "artefact" || a.grade === "span") return "";
  return a.specId ? "paragraph" : "section";
}

/** One owner-shaped comment body as the grammar request for its altitude.
 *
 *  THE ONE SPELLING (WRITING-CONSOLIDATION-W1, the synthesis). The editor's keep/cut/rework
 *  gesture was the last surface still posting the owner's flat body with the old top-level
 *  discriminator `verb:"comment"`, while every other gesture on this canvas had moved to
 *  verb x concept: the grammar spelling was accepted at this route and proved by test, and
 *  sent by nobody. It is sent from here now, so the route has ONE shape arriving from the
 *  product and the other is reachable only by a recorded row of the corpus.
 *
 *  The body itself is NOT rebuilt --- `commentPayload` is still the one producer of what the
 *  row carries, and `review_http._owner_adjudication` restores the executor's own
 *  discriminator --- so the banked row is identical to the one the flat body banks
 *  (`tests/test_editor_doors.py::test_the_grammar_body_and_the_old_body_bank_the_same_row`).
 *  What moves is where the altitude and the home live: the altitude is half of the concept and
 *  the home id is the `target`, which is what makes `expected` mean something at this door. */
function commentRequest(owner, altitude) {
  if (!altitude) return owner;
  const { verb, by, expected, ...rest } = owner;
  const file = rest.file || rest.source_file || "";
  const span = altitude === "paragraph" && rest.line_start
    ? ":" + rest.line_start + "-" + (rest.line_end || rest.line_start) : "";
  return { verb: "create", concept: "note@" + altitude,
           target: file ? S.corpus + "::" + file + span : "",
           expected: expected || [], by: by || C.actor || "author", payload: rest };
}

function commentPayload(a, note) {
  const p = scopeFields({ verb: "comment", by: C.actor, corpus: S.corpus,
                          comment: note, surface: "walk" });
  if (!note) p.mark_only = true;
  const altitude = commentAltitude(a);
  // THE RULING (WRITING-CONSOLIDATION-W1): keep | cut | rework, in the PAYLOAD. Specialisation
  // lives in the concept's payload and never in a new verb (GRAMMAR.md section 4).
  if (C.disposition) p.disposition = C.disposition;
  // THE ALTITUDE IS NOT WRITTEN HERE, and that is the synthesis's subtraction: it is half of
  // the concept (`commentRequest` below), and `review_http._owner_adjudication` puts it back
  // on the owner body from `request.altitude`. Writing it into the payload as well would be the
  // one value in two places on one request — the thing this campaign exists to stop.
  //
  // THE TOKEN RIDES ON EVERY ALTITUDE AND NOT ONLY ON A RULING. A bare comment is banked
  // against a passage too, and before this synthesis it was banked with nothing compared: the
  // gate runs for `ruling or expected` (review_surface.py:2385), so sending the token the read
  // published is what makes the gesture refusable. ALL THREE ALTITUDES: the container is the
  // addressed span at paragraph altitude and the FILE at section and chapter altitude, so the
  // token comes from two different reads — the canvas's own per-block token for the span,
  // `/review/fragment`'s `identities` for the file (`containerToken` above).
  if (altitude === "paragraph") {
    const token = expectedOf(blockById.get(a.blockId));
    if (token.length) p.expected = token;
  } else if (altitude) {
    const token = containerToken(a, altitude);
    if (token.length) p.expected = token;
  }
  if (a.grade === "artefact") { p.grade = "artefact"; p.section = a.sectionId || ""; }
  else if (a.grade === "span") { p.span = { sections: a.sections }; p.section = a.sections[0]; }
  else {
    p.section = a.sectionId || "";
    p.quote = a.quote;
    p.block = a.blockId;
    // the tier the block actually earns. The door grades on what it is handed:
    // `paragraph` when a precise pid arrives and `coarse` is false, `figure` when a
    // `fig:` label arrives, `section` otherwise. The walk used to hard-code
    // `coarse: true` and send no pid and no figure, so every deposit on this canvas —
    // including every note on a figure — banked at the coarse SECTION beat, and the
    // provenance the dual-faithful canvas exists to carry never reached the ledger.
    if (a.figLabel) p.figure = a.figLabel;
    if (a.specId) { p.paragraph = a.specId; p.coarse = false; }
    else p.coarse = true;
    if (a.file) { p.source_file = a.file; p.file = a.file; }
    if (a.lineStart) { p.source_line = a.lineStart; p.line_start = a.lineStart;
                       p.line_end = a.lineEnd || a.lineStart; }
    if(a.specIdsComplete&&a.specIds?.length&&a.file&&a.lineStart){p.spec_ids=[...a.specIds];if(a.sourceSection)p.source_section=a.sourceSection;}
  }
  if (a.before) p.context_before = a.before;
  if (a.after) p.context_after = a.after;
  return commentRequest(p, altitude);
}

/** The rewrite door, exactly as the block model types it.
 *
 *  `before`/`after` are THE SOURCE, at the block's own line span — that is what the door's
 *  byte guard compares against (`raw.split("\n")[line_start-1 … line_end]`), so the two
 *  sides agree by identity and the splice is deterministic. His passage rides alongside as
 *  `passage_before`/`passage_after`, so the banked row keeps the (before, after) pair at
 *  the grain he actually worked at — the response-function sample, in his reading register.
 *
 *  When the locator cannot place the passage exactly once, the payload carries HIS PASSAGE
 *  as `before` instead. That fails the byte guard on purpose: the door then banks a
 *  pending-rewrite row holding his replacement and says so, and the fix pass applies it.
 *  Nothing is guessed and no deposit is lost — and the composer said which of the two it
 *  would be before he pressed Enter. */
function rewritePayload(a, after, note, expected = expectedOf(blockById.get(a.blockId))) {
  const sp = spliceOf(a, after);
  const extra = {};
  if (a.before) extra.context_before = a.before;
  if (a.after) extra.context_after = a.after;
  return sourceRequest({
    file: a.file, lineStart: a.lineStart, lineEnd: a.lineEnd,
    before: sp ? sp.before : a.quote, after: sp ? sp.after : after,
    passageBefore: a.quote, passageAfter: after,
    section: a.sectionId || "", block: a.blockId, note,
    expected, extra });
}

/** did the door splice? — read off the door's ACTUAL contract, in one place.
 *
 *  `/review/adjudicate {verb:"rewrite"}` answers the applied path with
 *  `{"pending": false, "applied": {section, paragraph, file, lines, block}}` and the
 *  pending path with `{"pending": true, "applied": null}`. It has never returned a
 *  boolean `applied`, and it has no `spliced` key at all. The surface tested
 *  `res.applied === true`, which is false for a dict, so EVERY splice that reached disk
 *  read back as a refusal: the block never re-rendered, its `src` line span went stale,
 *  and the composer told him in red that his edit had not landed when it had.
 *
 *  `pending` is the authority (the door sets it explicitly on both paths); `applied`
 *  being a non-empty object is the corroboration; the record's own `anchor.applied`
 *  flag is the last resort for a caller that only got the row back. */
function appliedOf(res, rec) {
  const effect=sourceEffectDisposition(res);
  if(effect)return effect.acknowledged;
  if (!res || res.pending === true) return false;
  const a = res.applied;
  if (a === true) return true;
  if (a && typeof a === "object") return true;
  const anc = rec && rec.anchor;
  return !!(anc && anc.applied === true);
}

function pendingOf(res, rec) {
  if (res && res.pending === true) return true;
  const anc = rec && rec.anchor;
  return !!(anc && anc.pending === true)
      || String((rec && rec.kind) || "") === "pending-rewrite";
}

function receiptWords(res) {
  const r = res && res.receipt;
  if (!r) return "";
  if (typeof r === "string") return r;
  return String(r.text || r.note || r.words || "");
}

async function bankDeposit() {
  const a = C.armed;
  if (!a) return null;
  if (!C.actor) {
    askActor("this deposit needs an actor. Every row is actor-attributed and the door "
           + "defaults nowhere — name who is depositing and it banks.",
             () => { bankDeposit(); });
    return null;
  }
  const shape = shapeOf();
  const note = compBody.value.trim();
  const after = compQuote.value;
  const payload = shape === "comment" ? commentPayload(a, note)
                                      : rewritePayload(a, after, note);
  let res;
  try {
    res = await saveSourceChange(payload);
  } catch (e) {
    C.echo = { text: "REFUSED — nothing was banked. " + e.message, tone: "refused" };
    renderComposer();
    return null;
  }
  const rec = (res && res.record) || {};
  const id = rec.id || "(no id returned)";
  const collided = C.mine.has(id);
  const applied = appliedOf(res, rec);
  const pending = pendingOf(res, rec);

  // the mark stops being the ARMED cue and becomes the deposit's trace in the paper.
  for (const m of C.marks) if (m.armed) { m.armed = false; m.id = id; }
  paintMarks();

  const row = {
    id, ts: rec.ts || new Date().toISOString(), kind: shape,
    scope: rec.scope || C.scope || "", scope_source: rec.scope_source || C.scopeSource || "",
    suggested_scope: rec.suggested_scope || C.suggested || "",
    grade: res.grade || (a.grade === "selection" ? "block" : a.grade),
    comment: note || (shape === "comment" ? "(mark only — no text)" : ""),
    before: shape === "comment" ? "" : a.quote,
    after: shape === "comment" ? "" : after,
    section: a.sectionId || "", sections: a.sections || null, blockId: a.blockId || "",
    file: a.file || "", by: C.actor, quote: a.quote || "", state: "open", mine: true,
    applied, pending,
    // the ruling, read back off the BANKED row's anchor rather than off the composer's state:
    // the band shows what landed, and what landed is what the door wrote
    disposition: (rec.anchor || {}).disposition || "",
    altitude: (rec.anchor || {}).altitude || "",
  };
  const listed = admit(row, MINTED);
  // the id collision guard. `feedback_add` now suffixes a colliding id (measured: eight
  // deposits on one section inside one second used to read back under ONE id, which broke
  // every door that targets a row by id — see `_unique_feedback_id`). This stays as the
  // client's own fence: if a door ever hands back an id this walk already holds, `u` would
  // revoke the earlier row, so the walk refuses to guess and says which door to use.
  // `u` targets a row the band actually holds: a row the gate refused is in no list, and
  // pointing the undo at it would post a revoke for something he cannot see.
  C.last = (collided || !listed) ? null : row;
  C.armed = null;
  C.needActor = ""; C.pending = null;
  compQuote.value = ""; compBody.value = "";

  const dest = ledgerPath();
  const scopeWords = row.scope ? row.scope + " altitude" : "unscoped";
  const head = "banked " + id + " → " + dest + " · " + scopeWords + " · " + shape;
  let tail;
  if (shape === "comment") tail = " · u revokes it";
  else if (applied) tail = " · spliced into " + srcSpanWords(a) + " · u revokes the row";
  else if (pending) tail = " · the source bytes did not match, so it stands as a PENDING "
    + "rewrite for the fix pass · u revokes it";
  else tail = " · " + (receiptWords(res) || "the door returned no splice verdict") + " · u revokes it";
  C.echo = collided
    ? { text: head + tail + " — but this walk already holds that id, so two rows now share "
             + "it and u would revoke the earlier one. Revoke it from the band instead.",
        tone: "refused" }
    : { text: head + tail, tone: "banked" };

  C.scope = ""; C.scopeSource = ""; C.suggested = ""; C.disposition = ""; C.altitude = "";
  openRail("band");            // the echo moment: the receipt is visible where it landed
  renderComposer();
  renderBand();            // the echo law: it lands at the head, now
  paintDeposits();
  takeDoor();
  paper.focus();
  if (applied && a.blockId) reloadBlock(a.blockId);
  else checkOrphans();
  emit("bank", { id, shape, applied, pending });
  return row;
}

/** `u` — the undo. A revoke is an APPEND that supersedes; no past line is rewritten. */
async function undoLast() {
  if (!C.last) {
    C.echo = { text: "nothing to revoke — this walk has banked no deposit yet.",
               tone: "refused" };
    renderComposer();
    openRail("band");          // the refusal is said where he can read it
    return;
  }
  if (!C.actor) {
    askActor("a revoke is actor-attributed too. Name who is revoking and it appends.",
             () => undoLast());
    return;
  }
  const row = C.last;
  let res;
  try {
    res = await store.fetchJSON(ADJUDICATE, {
      method: "POST",
      body: { verb: "revoke", by: C.actor, corpus: S.corpus, supersedes: row.id,
              reason: "revoked from the walk" },
    });
  } catch (e) {
    C.echo = { text: "REFUSED — " + row.id + " still stands. " + e.message, tone: "refused" };
    renderComposer();
    return;
  }
  C.rows = C.rows.filter((r) => r.id !== row.id);
  C.mine.delete(row.id);
  C.marks = C.marks.filter((m) => m.id !== row.id);
  C.last = C.rows[0] || null;
  paintMarks();
  C.echo = {
    text: "revoked " + row.id + " — a revoke record was appended"
        + (res && res.idempotent ? " (it was already gone)" : "")
        + "; the row is retired, not deleted"
        + (row.kind === "comment" ? "." : ", and a splice already written to source stands: "
          + "revoking is not a rewind."),
    tone: "banked" };
  renderComposer();
  renderBand();
  paintDeposits();
}

export {
  appliedOf, bankDeposit, commentPayload, pendingOf, receiptWords, rewritePayload, scopeFields, undoLast
};
