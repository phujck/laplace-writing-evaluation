// WALK PARAGRAPH AND OBJECT OPERATIONS (S2 F6). Purpose: source-addressed structural gestures:
// paragraph transitions (split, join, heading, replace) with their draft carets, block deletion and
// join, atomic objects (select, copy, move, delete) and heading insertion. Owns: paragraphTransition
// (begin/endParagraphTransition are its only writers) and the object selection/clipboard/move state.
// Public contract: beginParagraphTransition/endParagraphTransition, focusSplitParagraph,
// transferParagraphDraft, paragraphAfterHeading, deleteBlock, joinBlocks, wireAtomicObjects,
// insertHeading. Each operation consumes one original preimage; a pending postimage is not writable.
import store from "/shared/store.mjs";
import {findRestructureAnchor} from "/shared/reader-restructure.mjs";
import {captureSourceChange, historySpan} from "/shared/manuscript-editing.mjs";
import {docEl, el, emit, norm, paper} from './walk-base.mjs';
import {RELOAD_INFLIGHT, blockById, expectedOf, reloadBlock} from './walk-document.mjs';
import {S, attentionBlockId, jumpToBlock, noteAttention} from './walk-position.mjs';
import {headText, refreshPieceMap} from './walk-pieces.mjs';
import {
  readEditorSource, saveSourceChange, sourceEffectRequest, sourceRequest
} from './walk-source-client.mjs';
import {C, askActor, settleRail} from './walk-composer.mjs';
import {blockAtSpan, closestBlock, hostText, offsetIn, pieceEdge, srcOf} from './walk-selection.mjs';
import {E, P, REVIEW_WORDS, clearEdit, snapshotEdit} from './walk-drafts.mjs';
import {
  persistEditHistory, savedEditHistory, showStructuralOutcome, undoEditorChange
} from './walk-edit-history.mjs';
import {appliedOf, pendingOf, receiptWords} from './walk-bank.mjs';
import {MINTED, admit, paintDeposits, renderBand} from './walk-band.mjs';
import {F, flipBlock} from './walk-flip.mjs';
import {
  commitAll, commitEdit, editableBlock, headSpan, presentationOwner, savePresentationChange, taggedParagraph
} from './walk-editing.mjs';
import {caretRange, editorInsertionPoint, showCard} from './walk-card.mjs';
import {blockLabels} from './walk-where.mjs';
import {onEditInput} from './walk-edit-input.mjs';
import {authorChangeRecords, proposalView} from './walk-review.mjs';

let paragraphTransition=null;
/** THE PARAGRAPH-TRANSITION OWNER: one split/join/replace/heading transition at a time. Begin
 *  names it; end clears it only if it is still the current one, so a late settle never clears a
 *  newer transition. Readers elsewhere see the live binding. */
function beginParagraphTransition(transition) { paragraphTransition = transition; return transition; }
function endParagraphTransition(transition) { if (paragraphTransition !== transition) return; paragraphTransition = null; }
const paragraphDraftCarets=new WeakMap();
function rememberParagraphCaret(draft){const selection=document.getSelection();if(draft&&selection?.rangeCount&&draft.contains(
  selection.anchorNode))paragraphDraftCarets.set(draft,offsetIn(draft,selection.anchorNode,selection.anchorOffset));}

async function focusSplitParagraph(original, split) {
  const source = srcOf(original);
  if (split.structuralResult) {
    const occurrence = split.structuralResult.remapped_occurrences?.[split.focusPart ?? 1];
    const target = occurrence && findRestructureAnchor({...split.structuralResult,remapped_occurrences:[occurrence],source_scope:null},S.blocks);
    if (!target?.bodyEl) return;
    transferParagraphDraft(target,split.liveDraft,split.draftPristine||'');
    if (!split.liveDraft && split.focusOffset !== undefined) {
      const selected=document.getSelection();selected.removeAllRanges();selected.addRange(caretRange(target.bodyEl,Math.min(split.focusOffset,hostText(target.bodyEl).length)));
    }
    if(split.joinBack)await joinBlocks(target,'prev',{afterSource:hostText(split.liveDraft)===split.draftPristine?split.originalSource:undefined});
    else if(split.joinForward)await joinBlocks(target,'next');
    return;
  }
  const candidates = S.blocks.filter(item => (item.kind || 'para') === 'para'
    && srcOf(item).file === source.file && srcOf(item).lineStart>source.lineStart && item.bodyEl);
  let target = split.empty ? candidates.find(item => hostText(item.bodyEl) === '') : null;
  if (!target && split.tail) target = candidates.find(item => hostText(item.bodyEl) === split.tail);
  // Math may still be awaiting its renderer, so visible-text equality is not a
  // stable locator. A split's next source paragraph is the authoritative target.
  if(!target)target=candidates[0];
  if (!target) return;
  transferParagraphDraft(target,split.liveDraft,split.draftPristine||'');
  if(split.joinBack)await joinBlocks(target,'prev',{afterSource:hostText(split.liveDraft)===split.draftPristine?split.originalSource:undefined});
  else if(split.joinForward)await joinBlocks(target,'next');
}

function transferParagraphDraft(target,draft,draftPristine){
  const draftText=draft?hostText(draft):'';
  const draftSelection=document.getSelection();const draftOffset=draft&&draftSelection?.rangeCount&&draft.contains(
    draftSelection.anchorNode)?offsetIn(draft,draftSelection.anchorNode,draftSelection.anchorOffset):paragraphDraftCarets.get(draft)??draftText.length;
  draft?.remove();
  target.bodyEl.focus({preventScroll:true});
  snapshotEdit(target, target.bodyEl);E.historyGroup=draft?.historyGroup||null;
  const range=caretRange(target.bodyEl,0),selected=document.getSelection();selected.removeAllRanges();selected.addRange(range);
  if(draft&&draftText!==draftPristine){
    let prefix=0,suffix=0;while(prefix<draftText.length&&prefix<draftPristine.length&&draftText[prefix]===draftPristine[prefix])prefix++;
    while(suffix<draftText.length-prefix&&suffix<draftPristine.length-prefix&&draftText.at(-1-suffix)===draftPristine.at(-1-suffix))suffix++;
    const change=caretRange(target.bodyEl,prefix,draftPristine.length-suffix);selected.removeAllRanges();selected.addRange(change);
      document.execCommand('insertText',false,draftText.slice(prefix,draftText.length-suffix));onEditInput({target:target.bodyEl});
  }
  const caret=caretRange(target.bodyEl,Math.min(draftOffset,hostText(target.bodyEl).length));selected.removeAllRanges();selected.addRange(caret);
}

async function paragraphAfterHeading(heading){
  const draft=el('div','pending-paragraph');draft.contentEditable='true';draft.setAttribute('aria-label','New paragraph');heading.el.after(draft);
  const transition={kind:'heading-paragraph',draft,undoRequested:false,joinBack:false};beginParagraphTransition(transition);
  draft.handleBeforeInput=event=>{const selection=document.getSelection();if(!selection?.rangeCount)return;const range=selection.getRangeAt(0);if(
    event.inputType==='deleteContentBackward'&&range.collapsed&&offsetIn(draft,range.startContainer,range.startOffset)===0){event.preventDefault();
    transition.joinBack=true;}else if(event.inputType==='insertParagraph'){event.preventDefault();document.execCommand('insertText',false,'\n\n');}};
  draft.focus({preventScroll:true});const selection=document.getSelection();selection.removeAllRanges();selection.addRange(caretRange(draft,0));
  try{
    if(E.blockId===heading.id&&E.dirty)await commitEdit('heading-enter');if(RELOAD_INFLIGHT)await RELOAD_INFLIGHT;
    heading=blockById.get(heading.id);if(!heading)throw Error('The heading changed while opening a paragraph.');const source=srcOf(heading),
      before=heading.tex,after=before+'\n\n\\par\n';
    const result=await saveSourceChange(sourceRequest({file:source.file,lineStart:source.lineStart,lineEnd:source.lineEnd,before,after,
      source:'heading-paragraph',section:heading.sectionId,block:heading.id,expected:expectedOf(heading)}),null, {tex:before,
      line_start:source.lineStart,offset:hostText(heading.bodyEl).length},{line_start:source.lineEnd+2,offset:0});
    if(!appliedOf(result,result.record||{}))throw Error('The new paragraph could not be saved; its draft is preserved.');await reloadBlock(heading.id);
    const target=S.blocks.find(block=>block.kind==='para'&&srcOf(block).file===source.file&&srcOf(block).lineStart===source.lineEnd+2);if(
      !target)throw Error('The new paragraph could not be located; its draft is preserved.');transferParagraphDraft(target,draft,'');
    if(transition.joinBack){if(E.dirty)await commitEdit('heading-merge');await joinParagraphIntoHeading(blockById.get(target.id)||target);}
    emit('bank',{id:result.record?.id,shape:'rewrite',applied:true,source:'heading-paragraph'});
  }catch(error){draft.classList.add('unsaved');emit('editor-status',{text:error.message,error:true});}finally{endParagraphTransition(transition);if(
    transition.undoRequested)undoEditorChange(false);}
}
async function joinParagraphIntoHeading(block){
  const index=S.blocks.indexOf(block),heading=S.blocks[index-1];if(heading?.kind!=='head'||srcOf(heading).file!==srcOf(block).file)return false;
  const hs=srcOf(heading),ps=srcOf(block),source=await readEditorSource(ps.file),lines=source.split('\n');if(lines.slice(hs.lineEnd,ps.lineStart-1).join('\n').trim())return false;
  let before=lines.slice(hs.lineStart-1,ps.lineEnd).join('\n'),end=ps.lineEnd;const span=headSpan(heading.tex);if(!span)return false;
  const paragraph=block.tex.trim()==='\\par'?'':block.tex,offset=hostText(heading.bodyEl).length,after=heading.tex.slice(0,span[1])+paragraph+heading.tex.slice(span[1]);
  const preceding=savedEditHistory.undo.at(-1);if(!paragraph&&preceding?.source==='heading-paragraph'&&preceding.file===ps.file&&
    preceding.before===heading.tex){const expandedEnd=hs.lineStart+preceding.after.split('\n').length-1;if(lines.slice(hs.lineStart-1,
    expandedEnd).join('\n')===preceding.after){before=preceding.after;end=expandedEnd;}}
  const result=await saveSourceChange(sourceRequest({file:ps.file,lineStart:hs.lineStart,lineEnd:end,before,after,source:'heading-merge',
    section:heading.sectionId,block:heading.id}),null,{tex:block.tex,line_start:ps.lineStart,offset:0},{tex:after,line_start:hs.lineStart,offset});if(
    !appliedOf(result,result.record||{}))throw Error('The heading changed; the paragraphs were preserved.');await reloadBlock(heading.id);
    const target=S.blocks.find(item=>srcOf(item).file===ps.file&&item.tex===after);if(target?.bodyEl){target.bodyEl.focus({preventScroll:true});
    const selection=document.getSelection();selection.removeAllRanges();selection.addRange(caretRange(target.bodyEl,offset));}return true;
}

async function deleteBlock(id) {
  let block = blockById.get(id);
  if (!block || (block.kind || 'para') !== 'para' || !block.bodyEl) {
    emit('editor-status', {text:'Only an editable paragraph can be deleted.'}); return false;
  }
  const deletionHunk=async target=>{
    const src=srcOf(target);if(!src.file)throw Error('This paragraph has no current source file.');
    const current=await readEditorSource(src.file),lines=current.split('\n');
    if(lines.slice(src.lineStart-1,src.lineEnd).join('\n')!==target.tex)throw Error('This paragraph source changed; reinspect it before deleting.');
    const postimage=[...lines.slice(0,src.lineStart-1),'',...lines.slice(src.lineEnd)].join('\n');
    const change=captureSourceChange(postimage,{file:src.file,line_start:src.lineStart,before:target.tex,after:''});
    const inverse=historySpan(postimage,change);
    // The same guarded hunk closes both directions, including its current
    // pass-through neighbour. A paragraph-only guard would omit that context.
    return {file:src.file,lineStart:inverse.line_start,
      lineEnd:inverse.line_start+inverse.after.split('\n').length-1,
      before:inverse.after,after:inverse.before};
  };
  if (RELOAD_INFLIGHT) { try { await RELOAD_INFLIGHT; } catch (_) {} }
  block = blockById.get(id) || block;
  // a paragraph whose draft awaits its read-back or is held for review is not written to
  const held = P.get(block.id), active = E.blockId === block.id ? E : null;
  if (held?.awaiting || held?.review || active?.awaiting || active?.review) {
    const reason = (held?.awaiting || active?.awaiting) ? "awaiting-postimage" : (held?.review || active?.review);
    emit('editor-status', {text: 'Paragraph not deleted. ' + (REVIEW_WORDS[reason] || REVIEW_WORDS["source-changed"]), error: true});
    return false;
  }
  let hunk;
  try{hunk=await deletionHunk(block);}
  catch(error){emit('editor-status',{text:'Paragraph not deleted: '+error.message+' Clear its text and Save an empty paragraph instead.',error:true});return false;}
  if (E.blockId === block.id && E.dirty){
    await commitEdit('delete-block');
    if(E.dirty)return false;
    if(RELOAD_INFLIGHT){try{await RELOAD_INFLIGHT;}catch{}}
    block=blockById.get(id)||block;
    try{hunk=await deletionHunk(block);}catch(error){emit('editor-status',{text:'Paragraph not deleted: '+error.message,error:true});return false;}
  }
  const source = srcOf(block);
  if (!C.actor) {
    askActor('deleting a paragraph banks a rewrite row. Name who is editing and it deletes.', () => deleteBlock(id));return false;
  }
  const index = S.blocks.indexOf(block);
  const neighbour = S.blocks[index + 1] || S.blocks[index - 1] || null;
  const payload = sourceRequest({...hunk,
    passageBefore:hostText(block.bodyEl),passageAfter:'(paragraph deleted)',
    section:block.sectionId||'',block:block.id,source:'delete-block',
    expected:expectedOf(blockAtSpan(hunk.file,hunk.lineStart,hunk.lineEnd))});
  const result = await saveSourceChange(payload);
  const record = (result && result.record) || {};
  if (!appliedOf(result, record)) {
    emit('editor-status', {text:'The paragraph was not applied; its source changed or is pending.', error:true}); return false;
  }
  await reloadBlock(block.id);
  const candidate = neighbour && (blockById.get(neighbour.id)
    || S.blocks.find(item => item.bodyEl && srcOf(item).file === source.file && item.tex === neighbour.tex));
  const target = candidate?.bodyEl ? candidate : S.blocks.find(item => item.bodyEl && srcOf(item).file === source.file);
  if (target?.bodyEl) { target.bodyEl.focus({preventScroll:true}); snapshotEdit(target, target.bodyEl); }
  emit('bank', {id:record.id, shape:'rewrite', applied:true, source:'delete-block'});
  return true;
}

/** The JOIN — backspace at a paragraph's start (or delete at its end): the two
 *  paragraphs become one. A whole-two-block rewrite through the door: before = both
 *  blocks' tex with the assumed "\n\n" separator, after = the same joined by a space.
 *  A separator the source spells differently fails the byte guard and banks PENDING —
 *  the door's own honesty, never a guess. Refused in words across a section head. */
async function joinBlocks(b, dir,options={}) {
  if (E.blockId === b.id && E.dirty) {await commitEdit("join");b=blockById.get(b.id)||b;}
  else if (RELOAD_INFLIGHT) {
    // same reload window as commitEdit: a join must read settled spans
    try { await RELOAD_INFLIGHT; } catch (_e) { /* said elsewhere */ }
    b = blockById.get(b.id) || b;
  }
  const idx = S.blocks.indexOf(b);
  const nb = S.blocks[dir === "prev" ? idx - 1 : idx + 1];
  if(dir==='prev'&&nb?.kind==='head'&&b.kind==='para'){try{if(await joinParagraphIntoHeading(b))return;}catch(error){emit('editor-status',{text:error.message,error:true});return;}}
  if (!nb) { showCard(b, "nothing on that side to join with", "refused"); return; }
  if(b.kind==='para'&&atomicOwner(nb)){selectObject(atomicOwner(nb));return;}
  if ((nb.kind || "para") !== "para" || (b.kind || "para") !== "para") {
    showCard(b, "the block " + (dir === "prev" ? "above" : "below") + " is not a "
      + "paragraph — a join across it is a structural ask; put it on the card", "refused");
    return;
  }
  const first = dir === "prev" ? nb : b;
  const second = dir === "prev" ? b : nb;
  const fs = srcOf(first), ss = srcOf(second);
  if (!fs.file || fs.file !== ss.file) {
    showCard(b, "these paragraphs live in different source files — no splice joins them", "refused");
    return;
  }
  if (!C.actor) {
    askActor("a join banks a rewrite row, and the door refuses an unattributed one. "
           + "Name who is editing and it banks.", () => { joinBlocks(b, dir); });
    return;
  }
  let source;
  try{source=await readEditorSource(fs.file);}catch(error){emit('editor-status',{text:error.message,error:true});return;}
  const lines=source.split('\n'),firstSource=lines.slice(fs.lineStart-1,fs.lineEnd).join('\n'),secondSource=lines.slice(ss.lineStart-1,ss.lineEnd).join('\n');
  const taggedJoin = taggedParagraph(first) || taggedParagraph(second);
  if(firstSource!==first.tex||secondSource!==second.tex||!taggedJoin&&lines.slice(fs.lineEnd,ss.lineStart-1).some(line=>line.trim())){emit(
    'editor-status',{text:'The text between these paragraphs changed. Refresh before joining them.',error:true});return;}
  if (taggedJoin) {try {presentationOwner([first,second]);} catch (error) {emit('editor-status', {text:error.message,error:true});return;}}
  const before=lines.slice(fs.lineStart-1,ss.lineEnd).join('\n');
  const left=first.tex.trim()==='\\par'?'':first.tex,right=second.tex.trim()==='\\par'?'':second.tex;
  const last=savedEditHistory.undo.at(-1);
  const inverse=last?.source==='paragraph-split'&&last.file===fs.file&&last.after===before?last.before:null;
  const joiner=/(^|[^\\])%[^\n]*$/.test(left)?'\n':'';
  const after=options.afterSource??inverse??(left+joiner+right||'\\par');
  const draft=el('div','pending-paragraph');draft.contentEditable='true';draft.setAttribute('aria-label','Joined paragraph');
  const clone=body=>{const range=document.createRange();range.selectNodeContents(body);return range.cloneContents();};
  if(left)draft.appendChild(clone(first.bodyEl));
  if(left&&!/\s$/.test(left)){const text=hostText(draft),end=text.replace(/\s+$/,'').length;if(end<text.length)caretRange(draft,end,text.length).deleteContents();}
  const cursor=hostText(draft).length;if(right)draft.appendChild(clone(second.bodyEl));
  const pristine=hostText(draft),transition={kind:'join',draft,undoRequested:false};beginParagraphTransition(transition);
  first.el.before(draft);first.el.hidden=true;second.el.hidden=true;clearEdit();draft.focus({preventScroll:true});
    const selection=document.getSelection();selection.removeAllRanges();selection.addRange(caretRange(draft,cursor));
  draft.handleBeforeInput=event=>{if(event.inputType==='insertParagraph'){event.preventDefault();document.execCommand('insertText',false,'\n\n');}};
  const payload = sourceRequest({
    file: fs.file, lineStart: fs.lineStart, lineEnd: ss.lineEnd, before, after,
    passageBefore: hostText(first.bodyEl || b.bodyEl) + " ¶ " + hostText(second.bodyEl || b.bodyEl),
    passageAfter: "(the two paragraphs, joined)",
    section: b.sectionId || "", block: first.id, source: "click-type" });
  showCard(b, "joining through the rewrite door…", "");
  let res;
  try {
    if (taggedJoin) {
      const observed = await savePresentationChange('presentation-join', [first,second], after);
      if (!observed.outcome.sourceCommitted) {
        draft.classList.add('unsaved');
        emit('editor-status', {text:'Inspect the structural source outcome before saving this join again. Your draft is retained.', error:true});
        return;
      }
      try {
        const refreshed = await reloadBlock(first.id);
        if (refreshed?.ok === false) throw Error(refreshed.note || 'The source view could not refresh.');
        const merged = S.blocks.find(block => block.src?.repo_file === first.src?.repo_file && block.kind === 'para' && srcOf(block).lineStart >= fs.lineStart);
        if (!merged?.bodyEl) throw Error('The joined paragraph is saved; its editable view is unavailable.');
        transferParagraphDraft(merged, draft, pristine);
      } catch (error) {emit('editor-status', {text:'Joined text was saved. View refresh failed: ' + error.message + ' Do not repeat the join.', error:true});}
      showStructuralOutcome(observed.result);
      emit('bank', {id:observed.result.receipt?.id, shape:'paragraph-restructure', applied:true, source:'paragraph-join'});
      endParagraphTransition(transition);
      return;
    }
    res = await saveSourceChange(payload,null,{tex:second.tex,line_start:ss.lineStart,offset:0},{tex:after,line_start:fs.lineStart,offset:cursor});
  } catch (e) {
    first.el.hidden=false;second.el.hidden=false;draft.classList.add("unsaved");endParagraphTransition(transition);emit("editor-status",{text:e.message,error:true});
    return;
  }
  const rec = (res && res.record) || {};
  const id = rec.id || "(no id returned)";
  const applied = appliedOf(res, rec);
  const pending = pendingOf(res, rec);
  const row = {
    id, ts: rec.ts || new Date().toISOString(), kind: "rewrite", comment: "",
    scope: rec.scope || "", scope_source: rec.scope_source || "",
    suggested_scope: "", grade: "block",
    before: "¶¶ (two paragraphs)", after: "¶ (joined)",
    section: b.sectionId || "", sections: null, blockId: first.id,
    file: fs.file || "", by: C.actor, quote: "", state: "open", mine: true,
    applied, pending,
  };
  admit(row, MINTED);
  C.echo = { text: "join banked " + id + (applied ? " · spliced — one paragraph now"
      : pending ? " · the source spells the gap differently, so it stands PENDING for the fix pass"
                : " · " + (receiptWords(res) || "no splice verdict")),
    tone: applied ? "banked" : "refused" };
  settleRail(); renderBand(); paintDeposits();
  emit("bank", { id, shape: "rewrite", applied, pending, source: "click-type" });
  showCard(b, applied ? "joined · banked " + id + " · u revokes"
                      : "banked " + id + (pending ? " as PENDING (the gap between these "
                        + "paragraphs is not a plain blank line)" : ""),
    applied ? "banked" : "refused");
  if (applied){await reloadBlock(first.id);const target=S.blocks.find(item=>srcOf(item).file===fs.file&&srcOf(item).lineStart===fs.lineStart);if(
    target)transferParagraphDraft(target,draft,pristine);}
  else {first.el.hidden=false;second.el.hidden=false;draft.classList.add('unsaved');emit('editor-status',{
    text:'The join could not be saved. Your typing is preserved.',error:true});}
  endParagraphTransition(transition);if(transition.undoRequested)await undoEditorChange(false);
}

// Whole source-backed objects share one select/move/delete/clipboard lifecycle.
const ATOMIC_KINDS=new Set(['figure','equation','table','custom','theorem','list','raw']);
const OBJECT_MIME='application/x-laplace-manuscript-object';
let objectSelection=null,objectClipboard=null,objectQueue=Promise.resolve(),objectMove=null,objectDrop=null;
function atomicOwner(block){return block?.caption_of?blockById.get(block.caption_of):block&&ATOMIC_KINDS.has(block.kind)?block:null;}
function objectSpec(block){return {file:srcOf(block).file,line_start:srcOf(block).lineStart,line_end:srcOf(block).lineEnd,before:block.tex,
  kind:block.kind,label:block.label||block.labels?.[0]||''};}
function findObject(spec){const candidates=S.blocks.filter(block=>ATOMIC_KINDS.has(block.kind)&&srcOf(block).file===spec.file&&
  block.tex===spec.before);return candidates.find(block=>srcOf(block).lineStart===spec.line_start)||(candidates.length===1?candidates[0]:null);}
function clearObjectSelection(clearRange=false){const had=objectSelection;for(const block of S.blocks)delete block.el?.dataset.objectSelected;
  objectSelection=null;if(clearRange&&had)document.getSelection()?.removeAllRanges();}
function selectObject(block,{scroll=false}={}){block=atomicOwner(block);if(!block||block.proposalLocked)return false;clearObjectSelection();
  objectSelection=objectSpec(block);for(const item of S.blocks)if(item===block||item.caption_of===block.id)item.el.dataset.objectSelected='true';
  docEl.focus({preventScroll:true});const range=document.createRange();range.setStartAfter(block.el);range.collapse(true);
  const selection=document.getSelection();selection.removeAllRanges();selection.addRange(range);if(scroll)paper.scrollTop=Math.max(0,
  block.el.offsetTop-35);emit('editor-status',{text:block.kind.charAt(0).toUpperCase()+block.kind.slice(
  1)+' selected · Delete removes · Enter edits source · drag to move'});return true;}
async function sourceDigest(text){const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text));return [...new Uint8Array(
  digest)].map(value=>value.toString(16).padStart(2,'0')).join('');}
function queueObject(work){const next=objectQueue.catch(()=>{}).then(work);objectQueue=next;return next.catch(error=>{emit('editor-status',{
  text:error.message,error:true});return null;});}
function destinationAt(block,side='after'){const owner=atomicOwner(block)||block;if(!owner)return null;return {file:srcOf(owner).file,tex:owner.tex,
  line_start:srcOf(owner).lineStart,side};}
function destinationAtCaret(){const point=editorInsertionPoint();if(!point||point.source)return null;const block=blockById.get(point.blockId),
  place=destinationAt(block,point.end===0?'before':'after');if(place&&block?.kind==='para'){place.block_id=block.id;place.renderedText=hostText(
  block.bodyEl);place.renderedOffset=point.end;}return place;}
async function checkedDestination(place){const candidates=S.blocks.filter(block=>srcOf(block).file===place.file&&block.tex===place.tex);
  let block=candidates.find(item=>srcOf(item).lineStart===place.line_start)||(candidates.length===1?candidates[0]:null);if(!block&&place.block_id){
  const current=blockById.get(place.block_id);if(current&&srcOf(current).file===place.file&&hostText(
  current.bodyEl)===place.renderedText)block=current;}if(!block)throw Error('The destination changed. Choose its paragraph again.');
  const source=await readEditorSource(place.file),line=place.side==='before'?srcOf(block).lineStart-1:srcOf(block).lineEnd,target={file:place.file,
  line,before:line?source.split('\n')[line-1]:undefined,expected_source_digest:await sourceDigest(source)};
  if(block.kind==='para'&&place.renderedOffset>0&&place.renderedOffset<hostText(block.bodyEl).length){if(hostText(
    block.bodyEl)!==place.renderedText)throw Error('The destination text changed. Choose the current caret again.');refreshPieceMap(block);
    const piece=block.pieceMap?.find(item=>place.renderedOffset>=item.rStart&&place.renderedOffset<item.rEnd),offset=piece&&pieceEdge(piece,block.tex,
    place.renderedOffset,false);if(typeof offset!=='number')throw Error('Place the caret beside the inline mathematical or reference object.');
    target.paragraph={line_start:srcOf(block).lineStart,line_end:srcOf(block).lineEnd,before:block.tex,offset};}
  return target;}
async function objectChange(operation,spec,destination=null,clip=null,{cutId}={}){
  await commitAll();if(E.dirty||P.size||F.blockId&&F.ta?.value!==(F.baseTex??''))throw Error('Save the current text edit before changing an object.');
  let block,beforeBlock;if(operation!=='insert'){block=findObject(spec);if(!block)throw Error(
    'This object changed. Select its current version again.');beforeBlock=objectSpec(block);const source=await readEditorSource(beforeBlock.file);
    beforeBlock.expected_source_digest=await sourceDigest(source);}
  const target=destination?await checkedDestination(destination):null;
  const result=await sourceEffectRequest('/authoring/block-change',{method:'POST',body:{project:S.corpus,operation:operation==='insert'&&
    target?.paragraph?'insert-at-caret':operation,...(beforeBlock?{block:beforeBlock}:{}),...(target?{destination:target}:{}),...(clip?{clip}:{})}});
  if(!result.ok)throw Error(result.error||'The object change did not complete.');
  let afterBlock=result.anchor?{...result.anchor}:null;if(!afterBlock&&(operation==='move'||operation==='insert')){const text=clip?.before||
    beforeBlock.before;const shift=operation==='move'&&beforeBlock.file===target.file&&
    target.line>beforeBlock.line_end?beforeBlock.line_end-beforeBlock.line_start+1:0;afterBlock={file:target.file,line_start:target.line-shift+1,before:text};}
  const entry={history_kind:'block',operation,corrections:result.corrections||[],edits:result.edits,placement:result.placement,
    before_block:beforeBlock,after_block:afterBlock,cut_id:cutId};const previous=savedEditHistory.undo.at(-1);
  if(operation==='insert'&&cutId&&previous?.cut_id===cutId&&previous.operation==='delete'){
    const shared=previous.edits.filter(old=>result.edits.some(edit=>edit.file===old.file));if(shared.every(old=>result.edits.find(edit=>
      edit.file===old.file).before===old.after)){entry.operation='cut-paste';entry.before_block=previous.before_block;entry.edits=[
      ...result.edits.map(edit=>{const old=previous.edits.find(row=>row.file===edit.file);return old?{...edit,before:old.before}:edit;}),
      ...previous.edits.filter(old=>!result.edits.some(edit=>edit.file===old.file))];if(previous.placement&&result.placement&&
      previous.placement.id===result.placement.id)entry.placement={...result.placement,before:previous.placement.before};savedEditHistory.undo.pop();}}
  for(const correction of entry.corrections)authorChangeRecords.set(correction.file,correction.id);
  savedEditHistory.undo.push(entry);savedEditHistory.redo=[];persistEditHistory();clearObjectSelection();await window.walk.refresh();if(afterBlock){
    const moved=findObject(afterBlock);if(moved)selectObject(moved,{scroll:true});}else if(beforeBlock){const next=S.blocks.find(item=>srcOf(
    item).file===beforeBlock.file&&srcOf(item).lineStart>=beforeBlock.line_start&&editableBlock(item));if(next?.bodyEl){next.bodyEl.focus({
    preventScroll:true});const selection=document.getSelection();selection.removeAllRanges();selection.addRange(caretRange(next.bodyEl,0));}}
  emit('bank',{shape:'rewrite',applied:true,source:'object-'+operation});emit('editor-status',{
    text:operation==='delete'?'Object removed. Ctrl-Z restores it.':operation==='move'?'Object moved.':'Object pasted.'});return result;
}
function deleteObject(id){const block=atomicOwner(blockById.get(id))||findObject(objectSelection||{});if(!block)return Promise.resolve(null);
  const spec=objectSpec(block);return queueObject(()=>objectChange('delete',spec));}
function beginObjectMove(id){const block=atomicOwner(blockById.get(id));if(!block||!selectObject(block))return;objectMove=objectSpec(block);emit(
  'editor-status',{text:'Choose the paragraph edge where this object should move. Esc cancels.'});}
function clearObjectDrop(){for(const block of S.blocks){delete block.el?.dataset.objectDrop;}objectDrop=null;}
function wireAtomicObjects(){
  const attention=event=>{if(proposalView?.options?.readOnly&&event.target.closest?.('.proposal-history')&&!event.target.closest?.(
    '[data-close-comparison]')){proposalView.inspectionActive=true;emit('attention',{inspection:true});return;}const selection=document.getSelection(
    ),node=selection?.anchorNode;const review=event.target.closest?.('[data-proposal-ui]');const target=review?.dataset.sourceBlock?blockById.get(
    review.dataset.sourceBlock)?.el:closestBlock(event.target)||closestBlock(node);if(target&&blockById.has(target.dataset.block)){if(
    proposalView)proposalView.inspectionActive=false;noteAttention(target.dataset.block);emit('attention',{block:attentionBlockId});}};
  docEl.addEventListener('pointerup',attention);docEl.addEventListener('keyup',attention);paper.addEventListener('wheel',event=>{if(
    event.target.closest?.('.proposal-history'))return;if(proposalView)proposalView.inspectionActive=false;noteAttention(null);emit('attention',{});},
    {passive:true});paper.addEventListener('pointerdown',event=>{if(event.target===paper){if(proposalView)proposalView.inspectionActive=false;
    noteAttention(null);emit('attention',{});}});

  docEl.addEventListener('click',event=>{if(event.target.closest?.('.flip,textarea,input,select,[data-proposal-ui]'))return;const block=blockById.get(
    closestBlock(event.target)?.dataset.block);if(objectMove&&block){event.preventDefault();event.stopImmediatePropagation();const origin=objectMove;
    objectMove=null;const rect=block.el.getBoundingClientRect(),place=destinationAt(block,event.clientY<rect.top+rect.height/2?'before':'after');
    clearObjectDrop();queueObject(()=>objectChange('move',origin,place));return;}
    const owner=atomicOwner(block),direct=event.target.closest?.('[data-object-handle]')||owner&&owner===block&&(['figure','equation','raw'].includes(
      owner.kind)||owner.custom_kind==='compiled')&&event.target.closest?.('.blk-body');if(direct&&owner&&!owner.proposalLocked){event.preventDefault(
      );event.stopImmediatePropagation();selectObject(owner);}},true);
  docEl.addEventListener('pointerdown',event=>{const block=blockById.get(closestBlock(event.target)?.dataset.block),owner=atomicOwner(block),
    direct=event.target.closest?.('[data-object-handle]')||owner===block&&owner&&(['figure','equation','raw'].includes(owner.kind)||
    owner.custom_kind==='compiled')&&event.target.closest?.('.blk-body');if(!direct||event.target.closest?.('.flip,textarea,input,select'))clearObjectSelection();},true);
  docEl.addEventListener('dblclick',event=>{if(event.target.closest?.('.flip,textarea,input,select,[data-proposal-ui]'))return;
    const owner=atomicOwner(blockById.get(closestBlock(event.target)?.dataset.block));if(owner&&['equation','raw'].includes(owner.kind)){
    event.preventDefault();event.stopImmediatePropagation();clearObjectSelection();flipBlock(owner);}},true);
  document.addEventListener('keydown',event=>{if(event.target?.matches?.('textarea,input,select'))return;if(event.key==='Escape'&&(objectSelection||
    objectMove)){event.preventDefault();objectMove=null;clearObjectDrop();clearObjectSelection();return;}const selected=objectSelection&&findObject(
    objectSelection);if(!selected)return;
    if(event.key==='Enter'){event.preventDefault();event.stopImmediatePropagation();clearObjectSelection(true);flipBlock(selected);return;}
    if(event.key==='Delete'||event.key==='Backspace'){event.preventDefault();event.stopImmediatePropagation();deleteObject(selected.id);return;}
    if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)){event.preventDefault();const before=['ArrowLeft','ArrowUp'].includes(
      event.key),index=S.blocks.indexOf(selected),near=S.blocks.slice(before?0:index+1,before?index:undefined);if(before)near.reverse();
      const target=near.find(editableBlock);clearObjectSelection();if(target?.bodyEl){target.bodyEl.focus({preventScroll:true});
      const selection=document.getSelection();selection.removeAllRanges();selection.addRange(caretRange(target.bodyEl,before?hostText(target.bodyEl).length:0));}}},true);
  for(const type of ['copy','cut'])document.addEventListener(type,event=>{const selected=objectSelection&&findObject(objectSelection);if(!selected||
    event.target?.matches?.('textarea,input'))return;event.preventDefault();event.stopImmediatePropagation();const spec=objectSpec(selected),packet={
    project:S.corpus,clip:{before:spec.before,kind:spec.kind,label:spec.label},...(type==='cut'?{cut_id:crypto.randomUUID()}:{} )};
    objectClipboard=packet;event.clipboardData?.setData(OBJECT_MIME,JSON.stringify(packet));event.clipboardData?.setData('text/plain',spec.before);if(
    type==='cut')queueObject(async()=>{const result=await objectChange('delete',spec,null,null,{cutId:packet.cut_id});if(
    result?.clip)objectClipboard={...packet,clip:result.clip};});else emit('editor-status',{text:'Object source copied with its caption and label.'});},true);
  document.addEventListener('paste',event=>{if(event.target?.matches?.('textarea,input'))return;let packet;try{packet=JSON.parse(
    event.clipboardData?.getData(OBJECT_MIME)||'null');}catch{}if(!packet&&objectClipboard&&event.clipboardData?.getData(
    'text/plain')===objectClipboard.clip.before)packet=objectClipboard;if(!packet)return;event.preventDefault();event.stopImmediatePropagation();if(
    packet.project!==S.corpus){emit('editor-status',{text:'Paste this source into the same manuscript project.',error:true});return;
    }const target=destinationAtCaret();if(!target){emit('editor-status',{text:'Place the caret at the paragraph where the object belongs.',
    error:true});return;}queueObject(()=>objectChange('insert',null,target,packet.clip,{cutId:packet.cut_id}));},true);
  docEl.addEventListener('dragstart',event=>{if(event.target.closest?.('.flip,textarea,input,select,[data-proposal-ui]'))return;
    const block=atomicOwner(blockById.get(closestBlock(event.target)?.dataset.block));if(!block||block.proposalLocked)return;selectObject(block);
    event.dataTransfer.setData(OBJECT_MIME,JSON.stringify({project:S.corpus,move:objectSpec(block)}));event.dataTransfer.effectAllowed='move';});
  docEl.addEventListener('dragover',event=>{if(![...event.dataTransfer.types].includes(OBJECT_MIME))return;const block=blockById.get(closestBlock(
    event.target)?.dataset.block);if(!block)return;event.preventDefault();event.dataTransfer.dropEffect='move';clearObjectDrop();
    const rect=block.el.getBoundingClientRect(),side=event.clientY<rect.top+rect.height/2?'before':'after';block.el.dataset.objectDrop=side;objectDrop=destinationAt(block,side);});
  docEl.addEventListener('drop',event=>{const raw=event.dataTransfer.getData(OBJECT_MIME);if(!raw)return;event.preventDefault();
    event.stopImmediatePropagation();try{const packet=JSON.parse(raw),target=objectDrop;clearObjectDrop();if(packet.project!==S.corpus||!packet.move||
    !target)throw Error('Choose a paragraph edge inside this manuscript.');queueObject(()=>objectChange('move',packet.move,target));}catch(error){
    emit('editor-status',{text:error.message,error:true});}},true);
  docEl.addEventListener('dragend',clearObjectDrop);
}

function insertHeading({point=editorInsertionPoint(),blockId,convert=false}={}){
  const block=blockById.get(blockId||point?.blockId)||blockById.get(attentionBlockId);if(!block){emit('editor-status',{
    text:'Place the caret in the manuscript where the heading belongs.'});return;}
  const converting=convert&&block.kind==='para',reviewedText=norm(hostText(block.bodyEl));const origin={file:srcOf(block).file,tex:block.tex,
    line_start:srcOf(block).lineStart,side:point?.start===0?'before':'after'};
  const dialog=el('dialog','manuscript-insert-dialog');dialog.append(el('h2',null,converting?'Make paragraph a heading':'Insert heading'));
  const label=el('label',null,'Heading text'),input=el('input');input.required=true;input.setAttribute('aria-label','Heading text');if(converting){
    input.value=reviewedText;label.hidden=true;}label.append(input);dialog.append(label);
  const kindLabel=el('label',null,'Level'),kind=el('select');kind.setAttribute('aria-label','Heading level');for(const [value,text]of [['chapter',
    'Chapter'],['section','Section'],['subsection','Subsection'],['subsubsection','Subsubsection']]){const option=el('option',null,text);
    option.value=value;kind.append(option);}kind.value=block.kind==='head'&&block.level==='section'?'subsection':'section';kindLabel.append(kind);dialog.append(kindLabel);
  const placeLabel=el('label',null,'Position'),place=el('select');place.setAttribute('aria-label','Heading position');for(const side of ['before',
    'after']){const option=el('option',null,(side==='before'?'Before':'After')+' this '+(
    block.kind==='head'?'heading':block.kind==='para'?'paragraph':block.kind));option.value=side;place.append(option);}place.value=origin.side;
    placeLabel.hidden=converting;placeLabel.append(place);dialog.append(placeLabel,el('blockquote',null,(hostText(block.bodyEl)||block.title||block.kind).slice(0,180)));
  const status=el('p'),actions=el('div','manuscript-insert-actions'),save=el('button','primary',converting?'Change paragraph style':'Insert heading'),
    cancel=el('button',null,'Cancel');cancel.onclick=()=>dialog.close();save.onclick=async()=>{if(!input.reportValidity())return;save.disabled=true;
    try{await commitAll();if(E.dirty||P.size)throw Error('Save the current paragraph before inserting the heading.');const live=blockById.get(
    block.id);if(!live||srcOf(live).file!==origin.file||norm(hostText(live.bodyEl))!==reviewedText)throw Error(
    'This passage changed. Choose its current text again.');const destination=await checkedDestination({...origin,tex:live.tex,line_start:srcOf(
    live).lineStart,
    side:converting?'before':place.value}),structure=await store.fetchJSON('/work/structure?'+new URLSearchParams({project:S.corpus}));const levels={
    chapter:1,section:2,subsection:3,subsubsection:4},preceding=S.blocks.filter(item=>item.kind==='head'&&srcOf(item).file===destination.file&&srcOf(
    item).lineStart<=destination.line&&levels[item.level]<levels[kind.value]).at(-1),parent=preceding&&(structure.sections||[]).find(section=>
    section.id===preceding.sectionId||section.title===headText(preceding));
      const result=await sourceEffectRequest('/authoring/section-change',{method:'POST',body:{project:S.corpus,
        operation:converting?'convert':'create',source_file:destination.file,after_line:destination.line,after_before:destination.before,
        expected_source_digest:destination.expected_source_digest,expected_plan_revision:structure.revision,title:input.value.trim(),kind:kind.value,
        ...(converting?{replacement:{line_start:srcOf(live).lineStart,line_end:srcOf(live).lineEnd,before:live.tex}}:{}),...(parent?{
        parent_id:parent.id}:{})}});if(!result.ok||!result.undo)throw Error(result.error||'The heading did not return a reversible source change.');
        savedEditHistory.undo.push({history_kind:'section',undo:result.undo,redo:null,correction_id:result.correction_id,file:result.edits?.[
        0]?.file});if(result.correction_id&&result.edits?.[0]?.file)authorChangeRecords.set(result.edits[0].file,result.correction_id);
        savedEditHistory.redo=[];persistEditHistory();dialog.close();await window.walk.refresh();const target=S.blocks.find(item=>item.kind==='head'&&
        blockLabels(item).includes(result.receipt.label));if(target){jumpToBlock(target.id);target.bodyEl.focus({preventScroll:true});
        const selection=document.getSelection();selection.removeAllRanges();selection.addRange(caretRange(target.bodyEl,hostText(
        target.bodyEl).length));}emit('bank',{applied:true,source:'section-create'});emit('editor-status',{
        text:converting?'Paragraph converted to a heading. Ctrl-Z restores the paragraph.':'Heading inserted. Enter starts its paragraph; Ctrl-Z removes the new heading.'});
    }catch(error){status.textContent=error.message;status.className='error';save.disabled=false;}};
  actions.append(save,cancel);dialog.append(actions,status);dialog.onclose=()=>dialog.remove();document.body.append(dialog);dialog.showModal();(converting?kind:input).focus();
}

export {
  ATOMIC_KINDS, atomicOwner, beginObjectMove, beginParagraphTransition, clearObjectSelection, deleteBlock,
  deleteObject, endParagraphTransition, findObject, focusSplitParagraph, insertHeading, joinBlocks,
  paragraphAfterHeading, paragraphTransition, rememberParagraphCaret, selectObject, transferParagraphDraft,
  wireAtomicObjects
};
