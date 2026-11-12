// WALK SOURCE CLIENT (S2 F3). Purpose: the walk's writes and owner reads of source, as thin
// wrappers over the existing owners: the one request shape for the review door (sourceRequest and
// its field/payload helpers), the source save route with its exact wire options and source-effect
// handling (saveSourceChange, sourceEffectRequest, retrySaveOnce), the editor-source read and the
// citation read (citationReadURL is part of walk.mjs's public contract). Owns: no state. store.mjs
// remains the fetch gateway; refusals keep the owner's status, needed fields and source_effect.
import {requireSourceCompletion, sourceEffectDisposition, sourceEffectFromError} from './source-effect.mjs';
import store from "/shared/store.mjs";
import {ownerHumanTarget} from "/shared/writing-owner-read.mjs";
import {captureSourceChange} from "/shared/manuscript-editing.mjs";
import {emit} from './walk-base.mjs';
import {D} from './walk-document.mjs';
import {S} from './walk-position.mjs';
import {C} from './walk-composer.mjs';
import {srcOf} from './walk-selection.mjs';
import {persistEditHistory, restoreEditHistory, savedEditHistory} from './walk-edit-history.mjs';
import {appliedOf, scopeFields} from './walk-bank.mjs';
import {editorInsertionPoint} from './walk-card.mjs';
import {islandSource} from './walk-edit-input.mjs';
import {authorChangeRecords} from './walk-review.mjs';

/** A citation renders as [n] resolved from the payload. It is an ATOMIC ISLAND (usability
 *  contract, clause 1): one wrapper element the caret walks around, undeletable by typing.
 *  An ordinary click READS: it opens the exact bibliography entry through the existing
 *  owner read (/references/attached?project&citekey, the same route the reference picker
 *  and the artifact inspector already consume), never the editor. Editing the citation's
 *  own TeX is the explicit gesture: Shift+click, or Enter with Shift, flips the block with
 *  the exact source span selected (islandSource). Reading must not become editing
 *  (m5-blind-ui-baseline M5-B06). */
export function citationReadURL(corpus, key) {
  if (!corpus || !key) return null;
  return '/references/attached?' + new URLSearchParams({project: corpus, citekey: key});
}
function readCitation(wrap, key) {
  const url = citationReadURL(S.corpus, key);
  if (!url) { islandSource(wrap, key); return; }
  const label = 'Citation ' + key;
  if (window.parent !== window) { window.parent.postMessage({type: 'laplace:open-owner-read', url, label}, location.origin); return; }
  import('/shared/writing-artifact.mjs').then(({openArtifact}) => {
    const owner = ownerHumanTarget(url);
    if (!owner) throw Error('The citation has no valid owner reading coordinates.');
    return openArtifact({project: owner.project, ownerRead: owner, label, opener: wrap});
  }).catch(error => emit('editor-status', {text: error.message, error: true}));
}
// ═════════════════════════════════════════════════════════════════════════════════════════
// 15 · THE BANK — one POST, the receipt in the same frame
// ═════════════════════════════════════════════════════════════════════════════════════════

const ADJUDICATE = "/review/adjudicate";

// ═════════════════════════════════════════════════════════════════════════════════════════
// THE ONE REQUEST SHAPE (WRITING-CONSOLIDATION-W1)
//
// Four gestures write source through this door — a typed edit (`commitEdit`), a block-flip
// save (`saveFlip`), a composer deposit (`bankDeposit`) and Undo/Redo (`undoEditorChange`) —
// and they used to build four payloads by hand. The last of them sent `line_start:1,
// line_end:<whole file>` with the WHOLE FILE as `before` and `after`, which is why 90 of the
// author's 129 feedback rows are whole-file pairs and his ledger is 24 MB.
//
// They now all build ONE body through `sourceRequest`, in the grammar's own shape:
//   {verb, concept, target, expected, payload, by}
// `target` is the home the act is about (`<project>::<file>:<a>-<b>`), so the span is stated
// once instead of once per key; `expected` is the identity tokens the canvas PUBLISHED for
// that block (`/walk/doc?identities=1`), never a digest computed here; and the byte guard
// travels as `before_content`, the grammar's uniform spelling for a text guard
// (`writing_verbs.CARRIERS`), which is also the key the door's own refusal serves the current
// span under — so a retry is literally `{**request, **refused.needed}`.
//
// The old flat payload still works and is what every other surface still sends; this walk
// sends the new one, and both reach the same executor (`review_http._owner_adjudication`).
// ═════════════════════════════════════════════════════════════════════════════════════════

/** The six request fields. A `needed` key that is one of these is a FIELD; anything else is a
 *  payload key. One list, so `withNeeded` cannot put a token in the payload by accident. */
const REQUEST_FIELDS = ["verb", "concept", "target", "expected", "payload", "by"];

function sourceRequest(parts) {
  const payload = scopeFields({
    corpus: S.corpus, surface: "walk",
    before_content: parts.before, after: parts.after,
    section: parts.section || "", block: parts.block || "",
  });
  const selection=parts.expectedSelection??(typeof D!=="undefined"?D.sourceObservation?.source_observation?.selection_identity:undefined);
  if(selection!==undefined)payload.expected_selection=selection;
  if (parts.passageBefore != null) payload.passage_before = parts.passageBefore;
  if (parts.passageAfter != null) payload.passage_after = parts.passageAfter;
  if (parts.source) payload.source = parts.source;
  if (parts.note) payload.note = parts.note;
  if (parts.extra) Object.assign(payload, parts.extra);
  return { verb: "change", concept: "prose@paragraph",
           target: S.corpus + "::" + parts.file + ":" + parts.lineStart + "-" + parts.lineEnd,
           expected: parts.expected || [], by: C.actor || "author", payload };
}

/** The file and span one body addresses, from EITHER spelling — the grammar's `target` or the
 *  owner's three keys. Used by the history capture, which keeps its entries in the owner's
 *  shape because they are persisted in localStorage and outlive this build. */
function spanOf(body) {
  const target = body && body.target;
  const m = typeof target === "string"
    ? /^(.*?)::(.+):(\d+)-(\d+)$/.exec(target) : null;
  if (m) return { file: m[2], line_start: Number(m[3]), line_end: Number(m[4]) };
  return { file: (body && body.file) || "",
           line_start: Number((body && body.line_start) || 0),
           line_end: Number((body && body.line_end) || 0) };
}

/** The owner-shaped view of a body: what the saved history entry and the receipt words read. */
function ownerView(body) {
  const inner = (body && body.payload) || {};
  const picked = (key) => (body && body[key] !== undefined ? body[key] : inner[key]);
  return { ...spanOf(body),
           before: picked("before") !== undefined ? picked("before") : inner.before_content,
           after: picked("after"), by: (body && body.by) || inner.by };
}

/** `{**request, **refused.needed}` — the grammar's own retry, routed by field.
 *
 *  `needed` is keyed by GRAMMAR fields (`expected`) and by payload carriers
 *  (`before_content`), so the merge is one loop over one list and not a per-key decision at
 *  each call site. The resolver keys that are not values to re-send — `read`, `until`,
 *  `unresolved`, `missing` — are what a refusal a fresher token cannot cure says instead, and
 *  they are skipped: a retry built from them would be a retry of the same request. */
function withNeeded(body, needed) {
  if (!needed || typeof needed !== "object") return null;
  const out = { ...body, payload: { ...((body && body.payload) || {}) } };
  let moved = 0;
  for (const [key, value] of Object.entries(needed)) {
    if(key==="expected_selection"){if(value!==body?.payload?.expected_selection&&value!==body?.expected_selection)return null;continue;}
    if (["read", "until", "unresolved", "missing"].includes(key)) continue;
    if (REQUEST_FIELDS.includes(key)) out[key] = value;
    else out.payload[key] = value;
    moved += 1;
  }
  if(body?.payload?.expected_selection!==undefined)out.payload.expected_selection=body.payload.expected_selection;
  return moved ? out : null;
}

/** Set one payload key on a body in EITHER spelling — the grammar's nested payload or the
 *  owner's flat one. Four gestures choose their `source` and their altitude after the body is
 *  built, and a key written at the top level of a grammar request would be refused as a
 *  restated request field or silently ignored. One setter, so no call site has to know. */
function setPayload(body, key, value) {
  if (body && body.payload) body.payload[key] = value;
  else if (body) body[key] = value;
  return body;
}

function repoSourceFile(file){const b=S.blocks.find(b=>srcOf(b).file===file&&b.src.repo_file);return b?.src.repo_file||[S.source?.manuscript_dir,file].filter(Boolean).join('/');}
async function readEditorSource(file){const response=await fetch('/projection/tex?'+new URLSearchParams({file:repoSourceFile(file),corpus:S.corpus}));
  if(!response.ok)throw Error('The source could not be read. Your edits are preserved.');return response.text();}
async function saveSourceChange(payload,historyGroup=null,caretBefore=null,caretAfter=null){
  restoreEditHistory();
  const owner=ownerView(payload);
  const liveCaret=historyGroup?editorInsertionPoint():null;if(!caretAfter&&liveCaret&&!liveCaret.source)caretAfter={tex:owner.after,
    line_start:owner.line_start,offset:liveCaret.end};
  // THE ONE RETRY (WRITING-CONSOLIDATION-W1). A refusal whose `needed` carries values is
  // retried ONCE with `{**request, **refused.needed}` and NOTHING ELSE — no local guess at a
  // revision, no re-read, no second decision. It fires on both shapes a refusal arrives in:
  // a 409 (the body rides the Error since `store.fetchJSON` stopped discarding it) and the
  // rewrite door's in-band pending receipt, which banks the author's words and says what
  // would have applied. One attempt, because a second would be a loop: if the retry is also
  // refused, the refusal's own words are what he reads.
  const result=await retrySaveOnce(payload);
  if((payload.verb==='rewrite'||payload.concept==='prose@paragraph')&&appliedOf(result,result?.record||{})){
    try{const source=await readEditorSource(owner.file),change=captureSourceChange(source,{...owner,line_start:owner.line_start,
      line_end:owner.line_end});if(change){change.correction_id=result.record?.id;change.by=owner.by;change.history_group=historyGroup;
      change.caret_before=caretBefore;change.caret_after=caretAfter;const previous=savedEditHistory.undo.at(-1);if(historyGroup&&
      previous?.history_group===historyGroup&&previous.file===change.file&&previous.after===change.before){change.before=previous.before;
      change.caret_before=previous.caret_before;savedEditHistory.undo[savedEditHistory.undo.length-1]=change;}else savedEditHistory.undo.push(change);
      savedEditHistory.redo=[];persistEditHistory();}}
    catch(error){emit('editor-status',{text:'Saved. Undo history could not be recorded: '+error.message,error:true});}
  }
  if(result.receipt?.plan_sync_note)emit('source-warning',{text:result.receipt.plan_sync_note});
  if(appliedOf(result,result?.record||{})){if(result.record?.id)authorChangeRecords.set(owner.file,result.record.id);emit('source-change-saved',{
    id:result.record?.id,file:owner.file,by:owner.by});}
  return result;
}

// Source effects are acknowledged before undo, draft settlement or a retry.
// Semantic metadata remains in the owner's ordinary result even for UNCHANGED.
async function sourceEffectRequest(route, options) {
  const expected = {project:S.corpus, selectionIdentity:options.body?.expected_selection ?? options.body?.payload?.expected_selection};
  try {
    const result = await store.fetchJSON(route, options);
    const effect = requireSourceCompletion(result, expected);
    if (effect?.warnings.length) emit('source-warning', {text:effect.message});
    return result;
  } catch (error) {
    const effect = sourceEffectFromError(error, expected);
    if (effect) {
      emit('editor-status', {text:effect.message, error:!effect.acknowledged});
      if (effect.effect.impact.status !== 'NONE') emit('source-outcome', {source_effect:effect.effect});
      error.message = effect.message;
    }
    throw error;
  }
}

/** One POST, and at most one retry built from the refusal's own `needed`. */
async function retrySaveOnce(payload){
  let result;
  try{
    result=await sourceEffectRequest(ADJUDICATE,{method:'POST',body:payload});
  }catch(error){
    if(sourceEffectFromError(error)||error.sourceEffectUnverified)throw error;
    const again=withNeeded(payload,error&&error.refused&&error.refused.needed);
    if(!again)throw error;
    emit('editor-status',{text:'The passage had moved; retrying with the identity the door served.'});
    return await sourceEffectRequest(ADJUDICATE,{method:'POST',body:again});
  }
  if(sourceEffectDisposition(result))return result;
  const served=result&&result.receipt&&result.receipt.refused&&result.receipt.refused.needed;
  const again=served?withNeeded(payload,served):null;
  if(!again)return result;
  const witness=result.receipt?.rewrite_retry;
  if(witness){
    if(result.pending!==true||result.record?.kind!=='pending-rewrite'||result.record?.id!==result.receipt.row_id||
      witness.pending_id!==result.receipt.row_id){emit('editor-status',{
      text:'Pending retry identity disagrees; reinspect the original row before continuing.',error:true});return result;}
    setPayload(again,'rewrite_retry',witness);
  }
  let retried;
  try{retried=await sourceEffectRequest(ADJUDICATE,{method:'POST',body:again});}
  // the pending row still stands; it is not lost. The retry's refusal (a 409 state-not-reached: both
  // edits touch the same characters) rides beside it, so the editor can say Conflict in the owner's words (save-trace C9)
  catch(_e){if(sourceEffectFromError(_e)||_e.sourceEffectUnverified)throw _e;return typeof _e?.body?.error==='string'?{...result,retry_refused:_e.body.error}:result;}
  if(appliedOf(retried,retried?.record||{})){if(retried.receipt?.retry_warning)emit('editor-status',{text:retried.receipt.retry_warning,error:true});return retried;}
  return result;
}

export {
  ADJUDICATE, ownerView, readCitation, readEditorSource, retrySaveOnce, saveSourceChange, setPayload,
  sourceEffectRequest, sourceRequest
};
