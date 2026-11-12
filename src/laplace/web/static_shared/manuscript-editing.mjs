// manuscript-editing.mjs — editor history, navigation coordinates and the idle refresh policy.
// Purpose: source-aware undo (one change, never a whole old file), proposal read URLs and the
//   conditional manuscript refresh (G17) the shell runs while the Manuscript view is visible.
// Public contract: createManuscriptRefresh({read,observe,project,getWalk,visible,...}) ->
//   {check,start,stop,invalidate,settled,destroy}; manuscriptChangeAttribution; waitForManuscript;
//   proposalReadURL; fileOnlyManuscriptSelection; sourceOnlyProposalContext.
// Currentness and cost: every tick (5 s, visible only) sends ONE conditional read of
//   /authoring/build view=summary with known_revision; an unchanged answer carries the identity
//   only ({unchanged:true}); a changed one carries the source observation and then the document
//   body is read once; dirty drafts defer the repaint and keep their original guard. Hidden
//   views tick nothing; no document read happens while idle and unchanged.
// Errors/recovery: an owner failure is one status line; the next visible focus retries.
// Storage: reads the shared laplace:proposal-draft:<corpus>:<turn>:<edit> key (with version)
//   that walk.mjs also writes; it writes no key of its own.
// Retired (C7): the whole-document reload on every refresh (walk.reloadBlock reads one section,
//   G14; the whole read remains only when the section structure changed).
import {sourceEffectDisposition,requireSourceCompletion,sourceEffectFromError} from './source-effect.mjs';
// Source-aware editor history. It reverts one change, never an entire old file.
// Navigation needs source coordinates, not a DOM text walk through every block.
// A caller that actually reads prose supplies readText explicitly.
export function proposalResolutionAvailable(edit={}) {
  const anchor=edit.current_anchor;
  return edit.resolution_available!==false&&edit.current_mapping!=='unproven-historical-location'
    &&typeof edit.review_token==='string'&&!!edit.review_token
    &&typeof edit.current_before==='string'&&anchor?.file===edit.file
    &&Number.isInteger(anchor.line_start)&&anchor.line_start>0
    &&Number.isInteger(anchor.line_end)&&anchor.line_end>=anchor.line_start;
}
export function proposalScopeUnproven(edit={}) {
  if(edit.target_proof?.status==='CURRENT')return false;
  if(edit.target_proof?.status==='UNPROVEN')return true;
  return edit.resolution_available===false||edit.current_mapping==='unproven-historical-location'
    ||edit.status==='conflict'&&!proposalResolutionAvailable(edit);
}
export function fileOnlyManuscriptSelection(selection) {
  return !!selection?.files?.length&&!selection.anchor&&!selection.quote
    &&selection.line_start==null&&selection.line_end==null&&!selection.draft;
}
export function sourceOnlyProposalContext(context,selection) {
  if(!fileOnlyManuscriptSelection(selection))return context;
  return {surface:'project',label:'Current manuscript source · '+selection.files.join(', '),
    task_id:context.task_id,section_ids:[],selection:{files:[...selection.files]}};
}
export function proposalReadURL(handle,{project,turnId,version,editId,queue=false}={}){
  const base=globalThis.location?.href||'http://localhost/',url=new URL(handle?.http?.url||'',base),q=url.searchParams,native=handle?.native_request;
  if(handle?.http?.method!=='GET'||url.origin!==new URL(base).origin||url.pathname!==(queue?'/authoring/proposals':'/authoring/proposal-preview')||q.get('project')!==project||[...q.keys()].some(key=>q.getAll(key).length>1))throw Error('Proposal read handle does not match this project or owner route.');
  const id=q.get('id')||q.get('turn_id');if(!queue&&(id!==turnId||version&&q.get('proposal_version')!==version||editId&&q.get('edit_id')!==editId))throw Error('Proposal read handle changed the selected turn, version or edit.');
  if(native){if(native.verb!=='read'||!native.payload||native.target!==(queue?project:project+'::'+turnId))throw Error('Native proposal handle does not match its HTTP owner target.');for(const key of ['id','record_id','proposal_version','edit_id','view','session_id','work_id','file','cursor','as_of','limit'])if(native.payload[key]!=null&&String(native.payload[key])!==(q.get(key)||''))throw Error('Proposal handle transports disagree.');}
  return url.pathname+url.search;
}
export function proposalComparisonAvailable(edit={}){const before=edit.current_before??edit.before;return (typeof before==='string'||!!edit.current_blocks?.length||!!edit.before_blocks?.length)&&(typeof edit.after==='string'||!!edit.after_blocks?.length);}
export function selectedProposalBody(summary,body,editId){if(body.turn_id!==summary.turn_id||body.proposal_version!==summary.proposal_version||body.edits?.length!==1||body.edits[0].edit_id!==editId||summary.validation_basis?.record_id&&body.validation_basis?.record_id!==summary.validation_basis.record_id)throw Error('The selected proposal body identity changed. No action was started.');return {...body,navigation_edits:summary.edits,candidate_summary:{turn_id:summary.turn_id,proposal_version:summary.proposal_version,remaining:summary.remaining,read_handle:summary.read_handle,remaining_scope:'candidate'}};}
// THE PROPOSAL STEP HEADING (M5 C7; repair H4): the ordinal and total come from the owner's
// candidate navigation scope (navigation_edits, every edit of the candidate with its identity
// and standing) and the selected exact edit identity, never from how many comparison bodies
// are loaded. Without an owner scope the heading says what it can prove: the loaded count.
export function proposalStepHeading(data={},selectedEditId,{conflict=false,unproven=false,file=''}={}){
  const navigation=Array.isArray(data.navigation_edits)?data.navigation_edits:null;
  const loaded=(data.edits||[]).filter(edit=>edit.lifecycle!=='retained-history'&&['pending','conflict'].includes(edit.status));
  const verb=conflict?'Compare change':'Review change';
  const name=file?' · '+String(file).split('/').pop():'';
  const chip=conflict?'Needs comparison':unproven?'Historical':'Proposed';
  if(navigation&&navigation.length){
    const ordinal=navigation.findIndex(row=>row.edit_id===selectedEditId)+1;
    const remaining=navigation.filter(row=>['pending','conflict',undefined].includes(row.status)&&row.lifecycle!=='retained-history').length;
    if(ordinal>0)return {eyebrow:verb+' '+ordinal+' of '+navigation.length+name,chip,scope:'candidate',ordinal,total:navigation.length,loaded:loaded.length,remaining,
      note:(data.read_scope?.kind==='selected-edit'?'one comparison loaded; ':'')+(remaining!==navigation.length?remaining+' awaiting review':'')};
  }
  const ordinal=loaded.findIndex(edit=>edit.edit_id===selectedEditId)+1;
  return {eyebrow:verb+' '+Math.max(1,ordinal)+' of '+Math.max(1,loaded.length)+' loaded'+name,chip,scope:'loaded',ordinal:Math.max(1,ordinal),total:loaded.length,loaded:loaded.length,remaining:null,note:'candidate count not asserted'};
}
// Counts come from the owner observation, not the number of hydrated edit bodies.
export function proposalReviewStatus(data={}){
  const parent=data.candidate_summary,scope=parent?'candidate':data.read_scope?.kind;
  const remaining=parent?parent.remaining:data.remaining;
  if(!Number.isInteger(remaining)||remaining<0||!['candidate','selected-edit'].includes(scope))return {text:'Selected comparison loaded; whole candidate count is not asserted.',remaining:null};
  if(scope==='selected-edit')return {text:remaining+' returned edit'+(remaining===1?'':'s')+' awaiting review in the selected edit scope; whole candidate count is not inspected.',remaining};
  return {text:remaining?remaining+' change'+(remaining===1?'':'s')+' awaiting review in the inspected candidate summary.':'No changes awaiting review in the inspected candidate summary.',remaining};
}

export function proposalReadIntent(handle){const native=handle?.native_request;if(native?.verb==='read'&&native.payload&&typeof native.target==='string')return 'Inspect the exact owner-provided generic read request '+JSON.stringify(native)+'. ';if(handle?.operation&&handle.payload)return 'Inspect the exact owner-provided read/navigation handle '+JSON.stringify(handle)+'. ';return 'Use an owner-provided saved-proposal read/navigation handle when available. If current queue or eligibility cannot be read, report that gap instead of guessing counts or states. ';}

export function proposalChangeRequest(edit,{turnId,version,readHandle}={}) {
  const guidance=' This EDIT identity names a saved proposal edit, not an author_changes correction/history record. '+proposalReadIntent(readHandle)+'Read current source with source '+JSON.stringify({files:[edit.file]})+' as a lookup only. Use the canonical file identity returned by the successful owner source read in every fresh edit, with its current source and read receipts. Never use the old file alias or former line coordinates as new authority. Prepare a fresh proposal for author review; do not apply either new or old edits or alter manuscript/reference source unless the user explicitly requested application.';
  if(!edit.local_draft_overlap&&edit.target_proof?.status==='CURRENT'&&(edit.lifecycle==='blocked'||edit.basis_currentness&&edit.basis_currentness!=='CURRENT'))return {
    selection:{files:[edit.file],quote:edit.current_before,anchor:edit.current_anchor},
    text:'Please reconcile this saved suggestion '+(edit.edit_id||'')+(turnId?' from turn '+turnId:'')+(version?' at version '+version:'')+' with the current argument, evidence and source. Its input basis changed. The attached passage is the owner-verified current target; read the current inputs before proposing a fresh change. Do not apply the old suggestion.'+guidance};
  if(edit.local_draft_overlap||proposalScopeUnproven(edit)||edit.lifecycle==='blocked'||edit.basis_currentness&&edit.basis_currentness!=='CURRENT')return {
    selection:{files:[edit.file]},
    text:'Please reconcile the retained suggestion '+(edit.edit_id||'')+
      (turnId?' from turn '+turnId:'')+(version?' at version '+version:'')+
      ' against the current manuscript source file '+edit.file+'. Read its current owner-issued source and choose the intended target before proposing a fresh change. The historical offsets and quoted passage are not a current target; do not apply or merge the old suggestion.'+guidance};
  const anchor=edit.current_anchor||{file:edit.file,line_start:edit.line_start,line_end:edit.line_end};
  return {selection:{files:[edit.file],quote:edit.current_before??edit.before,anchor},
    text:'Please revise this proposed change: '+(edit.reason||'')+guidance};
}
export function paragraphSourceIdentity(block) {
  const complete=Array.isArray(block.spec_ids);
  const ids=[...new Set((complete?block.spec_ids:typeof block.spec_id==='string'&&block.spec_id?[block.spec_id]:[]).filter(id=>typeof id==='string'&&id))];
  return {specIds:ids,specId:complete&&ids.length===1?ids[0]:'',specIdsComplete:complete,
    sourceSection:typeof block.source_section==='string'?block.source_section:''};
}
// THE SOURCE LOCATION OF ONE RENDERED BLOCK (C12 nested source identity, 2026-10-15). The exact repository
// file the document read published for the block (src.repo_file, e.g. writing_projects/<p>/<draft>/chapters/
// chapter-01.tex) — never its manuscript-relative name, which the repository source owner would resolve from the
// repository root and miss — with its first line and the source basis it was read under: the read's selection
// identity and that file's raw-byte digest. manuscript-editor openSource refuses when either moved. A block with
// no published repository file or no current digest has no location: there is no basename or relative fallback.
// Consumers: manuscript-editor writeSourceLocation (Write -> TeX) and writing-panel "Open in TeX".
export function blockSourceLocation(walk, id) {
  if(!id)return null;
  const block=walk?.blocks?.({text:false})?.find(row=>row.id===id);
  if(!block)return null;
  const file=block.repo_file,observed=walk.sourceObservation?.()?.source_observation,digest=file?observed?.file_revisions?.[file]:null;
  if(!file||!/^sha256:[a-f0-9]{64}$/.test(observed?.selection_identity||'')||!/^[a-f0-9]{64}$/.test(digest||'')||!Number.isInteger(block.line_start)||block.line_start<1)
    throw Error('This passage has no current source location. Refresh the manuscript before opening its TeX.');
  return {file,line:block.line_start,basis:{selection_identity:observed.selection_identity,source_digest:'sha256:'+digest}};
}
export function manuscriptBlockRows(blocks, readText = null) {
  return blocks.map(block => ({id:block.id, kind:block.kind, section:block.sectionId,
    caption_of:block.caption_of, file:block.src?.file||'',...(block.src?.repo_file?{repo_file:block.src.repo_file}:{}),
    ...(block.spec_ids?{spec_ids:[...block.spec_ids]}:{}),...(block.source_section?{source_section:block.source_section}:{}),
    line_start:block.src?.line_start||0, line_end:block.src?.line_end||0,
    ...(readText ? {text:readText(block)} : {})}));
}
export function recordedProposalAttention(data={}){
  const edits=data.edits||[],files=[...new Set(edits.map(edit=>edit.file).filter(file=>typeof file==='string'&&file))],elsewhere=[...(data.applied_elsewhere||[]),...edits.flatMap(edit=>edit.fulfilled_elsewhere||[])];let turn=data.turn_id,applications=[];
  const refs=edits.filter(edit=>edit.application_id).map(edit=>({id:edit.application_id,turn_id:edit.application_turn_id||elsewhere.find(row=>row.id===edit.application_id)?.turn_id||(!['applied_elsewhere','superseded'].includes(edit.status)?data.turn_id:null)}));if(!refs.length)refs.push(...elsewhere);
  if(refs.length&&refs.every(row=>row.turn_id)&&new Set(refs.map(row=>row.turn_id)).size===1){turn=refs[0].turn_id;applications=[...new Set(refs.map(row=>row.id).filter(Boolean))];}
  const posture={applied:'Accepted',rejected:'Rejected','applied-elsewhere':'Applied',superseded:'Superseded',fulfilled:'Fulfilled','resolved-into-successor':'Resolved in a later revision'}[data.proposal_state]||'Saved';
  return {surface:'review',label:posture+' comparison'+(files.length?' · '+files[0].split('/').at(-1)+(files.length>1?' +'+(files.length-1)+' files':''):''),selection:{files},section_ids:[],...(turn?{review:{turn_id:turn,application_ids:applications}}:{})};
}

export function captureSourceChange(source, change) {
  const lines = source.split('\n');
  const offset = lines.slice(0, change.line_start - 1).reduce((n, line) => n + line.length + 1, 0);
  const expected = String(change.after);
  if (source.slice(offset, offset + expected.length) !== expected) return null;
  return {...change, prefix: source.slice(Math.max(0, offset - 160), offset),
    suffix: source.slice(offset + expected.length, offset + expected.length + 160)};
}

// A lazy agent inverse must be anchored in its recorded postimage, never in the
// document that happens to exist when the author presses Undo.
export function captureApplicationChange(application,index){
  const edits=application?.edits||[],edit=edits[index];
  if(application?.complete!==true||!edit?.file||!Number.isInteger(edit.line_start)||typeof edit.before!=='string'||typeof edit.after!=='string')return null;
  const anchors=(application.receipts||[]).map(receipt=>receipt.record?.anchor).filter(anchor=>anchor?.file===edit.file&&Array.isArray(anchor.lines)&&Number.isInteger(anchor.lines[0])&&Number.isInteger(anchor.lines[1])&&anchor.lines[0]<=edit.line_start&&anchor.lines[1]>=(Number.isInteger(edit.line_end)?edit.line_end:edit.line_start)&&typeof anchor.after==='string');
  if(anchors.length!==1)return null;
  const anchor=anchors[0],postimage=anchor.after,sameFile=edits.filter(other=>other.file===edit.file&&Number.isInteger(other.line_start)&&other.line_start>=anchor.lines[0]&&other.line_start<=anchor.lines[1]),postLine=target=>target.line_start+sameFile.filter(other=>other.line_start<target.line_start).reduce((sum,other)=>sum+String(other.after).split('\n').length-(Number.isInteger(other.line_end)?other.line_end-other.line_start+1:String(other.before).split('\n').length),0),localLine=target=>postLine(target)-anchor.lines[0]+1;
  const captured=captureSourceChange(postimage,{...edit,line_start:localLine(edit)});if(!captured)return null;captured.line_start=postLine(edit);
  const offset=target=>postimage.split('\n').slice(0,localLine(target)-1).reduce((sum,line)=>sum+line.length+1,0),start=offset(edit),end=start+edit.after.length,others=sameFile.filter(other=>other!==edit).map(other=>({start:offset(other),end:offset(other)+String(other.after).length}));
  if(others.some(other=>other.start<end&&other.end>start))return null;
  // Other edits in this same application are independently undoable. The guard
  // therefore uses only the unchanged text between those edits, not their bodies.
  const lower=Math.max(0,start-160,...others.filter(other=>other.end<=start).map(other=>other.end)),upper=Math.min(postimage.length,end+160,...others.filter(other=>other.start>=end).map(other=>other.start));
  captured.prefix=postimage.slice(lower,start);captured.suffix=postimage.slice(end,upper);
  const needle=captured.prefix+edit.after+captured.suffix;if(!needle||postimage.indexOf(needle)!==postimage.lastIndexOf(needle))return null;
  return {...captured,require_context:true};
}

// THE ONE LOCATOR for Undo and Redo. It finds the saved edit in the document that
// exists now and answers the HUNK SPAN: the whole lines the inverse touches, with the
// source at that span and the source the span becomes. `historyReplacement` is this
// same answer spliced back into the whole file, so there is one search and one
// definition of where the edit is, not two that can disagree.
//
// The span is what the door is addressed with. /review/adjudicate splices
// `lines[:line_start-1] + after.split('\n') + lines[line_end:]`
// (src/laplace/review_surface.py:2265) and guards those bytes against `before` at
// :2158-2172 (`bytes_guards=["before"]` on :2170), so a caller that sends the real span
// gets the identical splice -- and the row it banks carries that span instead of the whole
// chapter. The span's own current bytes are read one function earlier, at :2147.
// THESE COORDINATES ARE THIS BRANCH'S (WRITING-CONSOLIDATION-W1, the synthesis): the
// storage-latency lane wrote :1912/:1859/:1879 and said review_surface.py was
// byte-identical on the base and on its branch, which was true of THAT branch and is
// false here -- the editor-doors lane put the identity gate and the span read into the
// same file, moving every statement below them by 353 lines. `grep -n 'line_start - 1'
// src/laplace/manuscript/review_surface.py` prints 1200, 2147 and 2265 on this head.
// Undo used to send `line_start:1, line_end:<every line>` with the whole file in
// `before` and `after`, which the door banks three times over in `anchor.before`,
// `anchor.after` and `anchor.quote` (:2134): 357 KB of ledger for a one-line undo,
// measured at 191.6x the save that preceded it.
export function historySpan(source, change, undo = true) {
  const replaced = undo ? change.after : change.before;
  const replacement = undo ? change.before : change.after;
  const prefix = change.prefix || '', suffix = change.suffix || '';
  const needle = prefix + replaced + suffix;
  let offset = needle ? source.indexOf(needle) : -1;
  const contextMatched=offset>=0&&source.indexOf(needle,offset+1)<0;
  if (contextMatched) offset += prefix.length;
  else {
    if(change.require_context)throw Error('This passage has changed. Undo could not safely locate its recorded context.');
    offset = replaced ? source.indexOf(replaced) : -1;
    if (offset < 0 || source.indexOf(replaced, offset + 1) >= 0)
      throw Error('This passage has changed. Undo could not safely locate the saved edit.');
  }
  const end = offset + replaced.length;
  let lineStart = offset===0?0:source.lastIndexOf('\n', offset - 1) + 1;   // 0 when on line 1
  const nextBreak = source.indexOf('\n', end);
  let lineEnd = nextBreak < 0 ? source.length : nextBreak;    // exclusive of the break
  if(!source.slice(lineStart,lineEnd).trim()){
    // A deletion leaves a blank line. The rewrite owner deliberately refuses an
    // empty byte guard. The retained fragment proves the insertion point; the
    // current complete neighbour is identical pass-through guarded at the owner.
    // Bytes beyond that fragment are current observations, not historical proof.
    if(!contextMatched||!(prefix+suffix).trim())throw Error('Undo has no uniquely recorded nonempty context for this blank source span.');
    const candidates=[];let left=lineStart,right=lineEnd;
    while(left>0){const finish=left-1,start=finish===0?0:source.lastIndexOf('\n',finish-1)+1;if(source.slice(start,finish).trim()){candidates.push({start,end:lineEnd,distance:lineStart-start});break;}left=start;}
    while(right<source.length){const start=right+1,at=source.indexOf('\n',start),finish=at<0?source.length:at;if(source.slice(start,finish).trim()){candidates.push({start:lineStart,end:finish,distance:finish-lineEnd});break;}right=finish;}
    const nearest=candidates.sort((a,b)=>a.distance-b.distance)[0];
    if(!nearest)throw Error('Undo has no nonempty neighbouring source line for a byte guard; the blank source was not changed.');
    lineStart=nearest.start;lineEnd=nearest.end;
  }
  const line_start = source.slice(0, lineStart).split('\n').length;
  const whole = source.slice(lineStart, lineEnd);
  return {line_start, line_end: line_start + whole.split('\n').length - 1,
          before: whole,
          after: whole.slice(0, offset - lineStart) + replacement + whole.slice(end - lineStart),
          replaced, replacement, span_start: lineStart, span_end: lineEnd};
}

export function historyReplacement(source, change, undo = true) {
  const span = historySpan(source, change, undo);
  return source.slice(0, span.span_start) + span.after + source.slice(span.span_end);
}

export function referenceCommand(target) {
  const key = String(target.key || target.label || '');
  if (!key || /[{}\\\s]/.test(key)) throw Error('This reference has an invalid label.');
  return `\\${target.type === 'citation' ? 'cite' : target.type === 'equation' ? 'eqref' : 'ref'}{${key}}`;
}

// A save commits one submitted face while the author may continue typing in the
// live DOM.  The newer face must be re-applied over the freshly saved face; it
// must never be cleared merely because the earlier request completed.
export function continuedEdit(submitted, current) {
  submitted = String(submitted ?? ''); current = String(current ?? '');
  return current === submitted ? null : {pristine: submitted, text: current};
}

export function paragraphSplitInsertion(text, offset) {
  text = String(text ?? ''); offset = Number(offset);
  if (!Number.isInteger(offset) || offset < 0 || offset > text.length) throw Error('Invalid paragraph split position.');
  const tail = text.slice(offset);
  const empty=!tail.trim();
  return {insert: empty ? '\n\n\\par' : offset === 0 ? '\\par\n\n' : '\n\n',
          tail, empty};
}

export function emptyParagraphSource(text){
  return String(text).split(/\n[ \t]*\n/).map(part=>part.trim()?part:'\\par').join('\n\n');
}

// Ordinal block IDs alone are not semantic identities after a source edit.
export function canRefreshBlockInPlace(current,next,requestedId){
  if(current.length!==next.length)return false;
  const visual=block=>JSON.stringify([block.kind,block.tex,block.src?.file,block.src?.repo_file,block.level,block.env,block.number,block.theorem_label,block.theorem_optional_title,block.theorem_numbered,block.pieces,block.items,block.rows,block.math,block.title,block.title_pieces,block.tail_pieces,block.caption_pieces,block.caption_of,block.preview_image,block.image,block.images,block.presentation]);
  return current.every((block,index)=>{const fresh=next[index];return block.id===fresh.id&&block.sectionId===fresh.sectionId&&block.kind===fresh.kind&&(block.id===requestedId||visual(block)===visual(fresh));});
}

export function matchHeldDraft(entry,blocks){
  const sameFile=blocks.filter(block=>block.file===entry.src?.file);
  const exact=typeof entry.tex==='string'?sameFile.filter(block=>block.tex===entry.tex):[];
  const atOriginal=exact.filter(block=>block.line_start===entry.src?.lineStart);
  if(atOriginal.length===1)return atOriginal[0].id;
  // Empty paragraphs have no semantic identity away from their reviewed location.
  if(entry.tex?.trim()==='\\par'||!entry.pristine?.trim())return null;
  if(exact.length===1)return exact[0].id;
  const rendered=sameFile.filter(block=>block.rendered===entry.pristine);
  return rendered.length===1?rendered[0].id:null;
}

// Browser draft snapshots are shared by tabs. Merge only this tab's changes
// relative to the snapshot it actually held, never overwrite an unseen draft.
export function normalizeDraftRows(rows){
  if(!Array.isArray(rows))throw Error('Saved manuscript drafts have an unreadable format.');
  return rows.map(row=>{if(!Array.isArray(row)||typeof row[0]!=='string'||!row[1]||typeof row[1].pristine!=='string'||typeof row[1].text!=='string')throw Error('A saved manuscript draft has an unreadable format.');return [row[0],{...row[1],draft_id:row[1].draft_id||'legacy:'+row[0]}];});
}
export function mergeDraftRows(beforeRows,localRows,remoteRows,newId=()=>crypto.randomUUID()){
  const before=normalizeDraftRows(beforeRows),local=normalizeDraftRows(localRows),remote=normalizeDraftRows(remoteRows);
  const index=rows=>new Map(rows.map(([key,entry])=>[entry.draft_id,{key,entry}]));
  const baseline=index(before),mine=index(local),stored=index(remote);
  const stable=value=>value&&typeof value==='object'?Array.isArray(value)?value.map(stable):Object.fromEntries(Object.keys(value).sort().map(key=>[key,stable(value[key])])):value;
  const same=(a,b)=>!!a&&!!b&&JSON.stringify(stable(a.entry))===JSON.stringify(stable(b.entry));
  let conflicts=0;
  for(const [id,previous]of baseline)if(!mine.has(id)&&same(stored.get(id),previous))stored.delete(id);
  const updated=[];
  for(const [id,change]of mine){const previous=baseline.get(id),other=stored.get(id);if(same(change,previous)){updated.push([change.key,change.entry]);continue;}
    if(other&&!same(other,previous)&&!same(other,change)){
      conflicts++;const replacement=newId();other.entry={...other.entry,conflict:true,unplaced:true};stored.set(id,other);
      change.entry={...change.entry,draft_id:replacement,conflict:true,unplaced:true};stored.set(replacement,change);
    }else if(!other&&previous){change.entry={...change.entry,draft_id:newId()};stored.set(change.entry.draft_id,change);}
    else stored.set(id,change);
    updated.push([change.key,change.entry]);
  }
  const keys=new Set(),rows=[];
  for(const {key,entry}of stored.values()){let slot=entry.conflict?'held:'+entry.draft_id:key;if(keys.has(slot))slot='held:'+entry.draft_id;keys.add(slot);rows.push([slot,entry]);}
  return {rows,local:updated,conflicts};
}

// Compare saved source and built presentation, not view state or wall-clock time.
export function manuscriptPresentationVersion(value={}){
  return JSON.stringify([value.macros||{},value.refs||{},value.ref_pages||{},value.citations||{},value.citation_targets||[]]);
}
export function manuscriptDocumentVersion(value={}){
  return JSON.stringify([value.root||'',value.source_revision||'',value.source_file_revisions||{},value.current_revision||'',value.title||'',manuscriptPresentationVersion(value),value.sections||[]]);
}
// A scoped reload (G14) delivers one or more sections plus the owner's section_index
// (id, file, blocks, file_revision for EVERY section). Freshness is per section: a held
// section stays current only while its file witness equals the index's file_revision.
// This plan says whether the section list itself changed (whole read required) and which
// held, undelivered sections are stale and must be fetched before the document can call
// itself current. It never equates the whole-document revision with undelivered sections.
export function planScopedReload({heldIndex=[],heldWitness={},delivered={}}={}){
  const index=Array.isArray(delivered.section_index)?delivered.section_index:[];
  const sameList=index.length===heldIndex.length&&index.every((row,position)=>row.id===heldIndex[position]?.id);
  if(!sameList)return {structureChanged:true,staleSections:[],witness:{}};
  const selected=new Set(Array.isArray(delivered.selected_sections)?delivered.selected_sections:[]);
  const staleSections=index.filter(row=>!selected.has(row.id)&&heldWitness[row.id]!==row.file_revision).map(row=>row.id);
  return {structureChanged:false,staleSections,witness:Object.fromEntries(index.map(row=>[row.id,row.file_revision]))};
}
export function manuscriptHasDraft(state={}){
  return !!(state.dirty||state.parked||state.committing||state.transition||state.proposal_dirty);
}
// A head read is metadata-only; a full source model is demand-driven. All
// revisions below are owner-issued observations, never browser-computed hashes.
export function createManuscriptRefresh({read,observe=null,project=null,getWalk,visible,isCurrent=()=>true,status=()=>{},clearStatus=()=>{},onObservation=()=>{},schedule=setTimeout,cancel=clearTimeout,pollEvery=5000}){
  let pending=false,inflight=null,alive=true,warned='',warningOwner=null,failureOwner=null,sequence=0,timer=null,monitoring=false,ownerRevision='';
  const scoped=walk=>alive&&isCurrent()&&visible()&&getWalk()===walk;
  // An unchanged answer (`known_revision` matched) carries the identity only; a changed
  // one carries the full source observation.
  // H2 (M5 C7-C9 repair): an unchanged answer is the condition token only ({project, unchanged,
  // summary_revision, document_status, as_of}); it names no source revision, because the token
  // the poller sent already covers the whole delivered status projection. A changed answer
  // carries the source observation and its current_revision.
  // copy (repair2 R5): draft-safe recovery words. The check retries on its own and offers Try again now;
  // a page reload is never advised while an edit is unsaved or its save failed; the exact owner message
  // is one Details control away (failureOwner.detail), never a tooltip.
  const refreshFailureCopy=state=>{
    const draft=manuscriptHasDraft(state||{}),unsaved=state?.persistence?.status==='failed'||state?.persistence?.status==='unproved';
    return 'The manuscript could not be refreshed. '+(unsaved?'Your edits are still on this page but are not saved yet; keep this page open and save them before leaving. ':draft?'Your unsaved edits are kept in the editor; keep this page open until they are saved. ':'What you see is the last version read. ')+'The check tries again on its own.';
  };
  const unchangedAnswer=value=>value?.project===project&&value.unchanged===true&&typeof value.summary_revision==='string'&&!!value.summary_revision;
  const ownerObservation=value=>{
    if(value?.project!==project||typeof value.current_revision!=='string'||!value.current_revision)throw Error('The document owner returned incompatible source observation coordinates.');
    if(value.source_observation?.schema_version!=='laplace.manuscript-source-observation/1')throw Error('The document owner returned incompatible source observation coordinates.');
    return value.current_revision;
  };
  const clearFailure=()=>{if(failureOwner)clearStatus(failureOwner);failureOwner=null;};
  const clearWarning=walk=>{
    if(manuscriptHasDraft(walk?.editState?.()))return false;
    if(warningOwner)clearStatus(warningOwner);
    warned='';warningOwner=null;return true;
  };
  const deferDraft=(walk,revision)=>{
    const held=walk.editState?.();
    if(!manuscriptHasDraft(held))return false;
    // his own save is not a change elsewhere (save-trace C10): while a save is out or its
    // words await their read-back, the reading view waits without the notice
    if(held?.committing||held?.submitted)return true;
    if(warned!==revision){warned=revision;warningOwner={kind:'manuscript-refresh-draft-warning'};status('The saved manuscript changed elsewhere. Your local draft is preserved with its original guard; the reading view updates after it is saved or discarded.',false,warningOwner);}
    return true;
  };
  async function perform(){
    const walk=getWalk();if(!alive||!isCurrent()||!visible()||!walk?.ready?.()||!walk.documentVersion)return {checked:false};
    const prior=walk.documentVersion(),version=++sequence;let observed=null;
    let tokenOnly=false;
    if(observe){
      observed=await observe();if(!scoped(walk)||version!==sequence)return {checked:false};
      if(unchangedAnswer(observed)){
        onObservation(observed);
        // R5: the owner's unchanged token proves its status projection did not move since the
        // poller's last full answer, NOT that the canvas applied that answer. With no outstanding
        // target the idle shortcut stands (no body read); with a target still pending (deferred
        // under a draft, a failed body read, a race) the body is read and reconciled through the
        // same version guards, or stays deferred while the draft is dirty.
        if(!pending){clearFailure();clearWarning(walk);return {checked:true,changed:false,unchanged:true,observation:observed};}
        // the owner has not moved since its last full answer, and the canvas has already read that
        // revision (his own save, read back): nothing changed elsewhere (save-trace C10)
        if(ownerRevision&&walk.sourceObservation?.()?.current_revision===ownerRevision){pending=!!warningOwner&&manuscriptHasDraft(walk.editState?.());clearWarning(walk);
          return {checked:true,changed:false,unchanged:true,observation:observed};}
        if(deferDraft(walk,warned||observed.summary_revision))return {checked:true,changed:true,deferred:true,observation:observed};
        tokenOnly=true;observed=null;
      }else{
      const revision=ownerObservation(observed);ownerRevision=revision;clearFailure();onObservation(observed);
      if(walk.sourceObservation?.()?.current_revision===revision){pending=!!warningOwner&&manuscriptHasDraft(walk.editState?.());clearWarning(walk);return {checked:true,changed:false,observation:observed};}
      pending=true;
      if(walk.documentVersion()!==prior)return {checked:true,deferred:true};
      if(deferDraft(walk,revision))return {checked:true,changed:true,deferred:true,observation:observed};
      }
    }
    const raw=await read();if(!scoped(walk)||version!==sequence)return {checked:false};
    if(raw?.ok===false)throw Error(raw.error||raw.note||'The current manuscript could not be read.');
    // ONE body admission (R5): whenever a head observation is configured, every body — after an
    // ordinary changed answer or during token-only pending recovery — passes the same
    // ownerObservation guard (project, non-empty current_revision, source-observation schema)
    // before any version comparison, refresh, or clearance of failure and pending
    const bodyRevision=observe?ownerObservation(raw):null;
    if(!observe||tokenOnly)clearFailure();
    if(observed&&bodyRevision!==observed.current_revision){pending=true;return {checked:true,deferred:true,reason:'Source advanced between its metadata and body reads.'};}
    const next=manuscriptDocumentVersion(raw),current=walk.documentVersion();
    if(current===next){pending=!!warningOwner&&manuscriptHasDraft(walk.editState?.());clearWarning(walk);return {checked:true,changed:false};}
    if(current!==prior){pending=true;return {checked:true,deferred:true};}
    pending=true;if(deferDraft(walk,observed?.current_revision||next))return {checked:true,changed:true,deferred:true};
    const applied=await walk.refresh({document:raw,ifClean:true,expectedVersion:current});
    if(!scoped(walk)||version!==sequence)return {checked:false};
    if(applied===false){pending=true;return {checked:true,changed:true,deferred:true};}
    pending=false;clearWarning(walk);return {checked:true,changed:true,refreshed:true};
  }
  function check(){
    if(inflight)return inflight;const origin=getWalk();
    // copy (ACTUAL-C7-REFRESH-ERROR-COPY): the banner says what happened and what stands in the
    // reader's words; the owner's exact message stays on the failure owner (detail) for inspection
    inflight=perform().catch(error=>{pending=true;if(scoped(origin)){failureOwner ||= {kind:'manuscript-refresh-failure'};failureOwner.detail=error.message;failureOwner.at=Date.now();failureOwner.retry=()=>check();status(refreshFailureCopy(origin?.editState?.()),true,failureOwner);}return {checked:false,error:error.message};}).finally(()=>{inflight=null;});return inflight;
  }
  function tick(){timer=null;if(!alive||!isCurrent()){destroy();return;}check().finally(()=>{if(monitoring&&alive)timer=schedule(tick,pollEvery);});}
  function stop(){monitoring=false;if(timer!==null)cancel(timer);timer=null;}
  function destroy(){stop();alive=false;++sequence;}
  return {check,start(){if(monitoring||!alive)return;monitoring=true;timer=schedule(tick,pollEvery);},stop,invalidate(){pending=true;return visible()?check():Promise.resolve({checked:false});},settled(){const walk=getWalk();if(pending&&warningOwner&&scoped(walk)&&walk?.sourceObservation?.()?.current_revision===warned&&!manuscriptHasDraft(walk.editState?.())){pending=false;clearWarning(walk);return Promise.resolve({checked:true,changed:false,settled:true});}return pending?check():Promise.resolve({checked:false});},destroy,get pending(){return pending;}};
}

// Only an exact correction actor can assign a change to the current author.
export function manuscriptChangeAttribution(data={},deleted=false){
  const by=String(data.correction?.by||data.correction?.actor||'');let who='Recorded edits',name='Saved change';
  if(by==='author'){who='You';name='Your change';}
  else if(by.startsWith('author:accepted-model')){who='Accepted agent edit';name='Accepted agent change';}
  else if(by.startsWith('eigen')){who='Eigen'+(by.startsWith('eigen:')?' · '+by.slice(6):'');name='Eigen’s change';}
  else if(by.startsWith('machine')){who='Agent';name='Agent change';}
  else if(by.startsWith('pipeline')){who='Pipeline';name='Pipeline change';}
  else if(by){who=by;name='Saved change';}
  return {who,marker:data.whole_file?'Saved source · no comparison baseline':deleted?'− Deleted passage':'+ '+name,
    inspect:deleted?'Inspect deleted passage':name==='Your change'?'Inspect your change':name==='Eigen’s change'?'Inspect Eigen’s change':'Inspect saved change'};
}

// Readiness follows the live iframe, including a replaced document. Slow opening
// is progress, not a failed operation; leaving the requested view cancels it.
export function waitForManuscript({getWalk,isCurrent=()=>true,onPending=()=>{},onSettled=()=>{},schedule=setTimeout,cancel=clearTimeout,pendingAfter=15000,interval=100}){
  return new Promise((resolve,reject)=>{
    let watched=null,tick=null,slow=null,finished=false,pending=false;
    const cleanup=()=>{if(tick!=null)cancel(tick);if(slow!=null)cancel(slow);watched?.off?.('ready',check);if(pending)onSettled();};
    const finish=(value,error)=>{if(finished)return;finished=true;cleanup();if(error)reject(error);else resolve(value);};
    function check(){
      if(finished)return;if(tick!=null){cancel(tick);tick=null;}
      if(!isCurrent()){finish(null);return;}
      const walk=getWalk();
      if(watched!==walk){watched?.off?.('ready',check);watched=walk;watched?.on?.('ready',check);}
      if(walk?.ready?.()){
        const doc=walk.doc?.();if(doc?.ok===false){finish(null,Error(doc.note||'The manuscript could not be loaded. Check the editor’s source message.'));return;}
        finish(walk);return;
      }
      tick=schedule(check,interval);
    }
    slow=schedule(()=>{if(!finished&&isCurrent()){pending=true;onPending();}},pendingAfter);
    check();
  });
}

export function pdfFigureRoute(route){return /\.pdf(?=[?#&]|$)|[?&]format=pdf(?:&|$)/i.test(String(route));}
export function compiledEnvironmentPreviewRoute(route){
  return String(route).startsWith('/walk/figure-preview?')?String(route).replace(/([?&]format=)png(?=&|$)/,'$1pdf'):route;
}
export function dominantPreviewFont(items=[]){
  const weights=new Map();
  for(const item of items){const weight=String(item.str||'').replace(/\s/g,'').length,transform=item.transform||[],size=Math.round(Math.hypot(Number(transform[2])||0,Number(transform[3])||0)*100)/100;if(weight&&size>0)weights.set(size,(weights.get(size)||0)+weight);}
  return [...weights].sort((a,b)=>b[1]-a[1])[0]?.[0]||null;
}
export function compiledPreviewWidth({pageWidth,availableWidth,readerFontPx,bodyFontPt}){
  const scale=bodyFontPt>0&&readerFontPx>0?readerFontPx/bodyFontPt:96/72;
  return Math.max(1,Math.min(availableWidth,pageWidth*scale));
}

const REVISION_WORDS=typeof Intl?.Segmenter==='function'?new Intl.Segmenter(undefined,{granularity:'word'}):null;
const REVISION_GRAPHEMES=typeof Intl?.Segmenter==='function'?new Intl.Segmenter(undefined,{granularity:'grapheme'}):null;
function revisionSegments(text,segmenter){const value=String(text??'');if(segmenter)return [...segmenter.segment(value)].map(row=>({value:row.segment,start:row.index,end:row.index+row.segment.length}));const rows=[];let offset=0;for(const part of value.match(/\s+|[\p{L}\p{N}\p{M}]+|./gu)||[]){rows.push({value:part,start:offset,end:offset+part.length});offset+=part.length;}return rows;}
function mergeRevisionSpans(spans){const sorted=spans.filter(row=>row&&row.end>row.start).sort((a,b)=>a.start-b.start||a.end-b.end),out=[];for(const row of sorted){const last=out.at(-1);if(last&&row.start<=last.end)last.end=Math.max(last.end,row.end);else out.push({start:row.start,end:row.end});}return out;}
function mergeRevisionWhitespace(spans,text){const rows=mergeRevisionSpans(spans),out=[];for(const row of rows){const last=out.at(-1);if(last&&/^\s*$/u.test(String(text).slice(last.end,row.start)))last.end=row.end;else out.push({...row});}return out;}
export function expandRevisionSpans(spans,atoms=[]){let result=mergeRevisionSpans(spans),changed=true;while(changed){changed=false;const expanded=[];for(const span of result){let next={...span};for(const atom of atoms)if(atom?.end>atom?.start&&next.start<atom.end&&next.end>atom.start){const start=Math.min(next.start,atom.start),end=Math.max(next.end,atom.end);if(start!==next.start||end!==next.end)changed=true;next={start,end};}expanded.push(next);}result=mergeRevisionSpans(expanded);}return result;}
function broadRevisionDiff(before,after){const a=revisionSegments(before,REVISION_GRAPHEMES),b=revisionSegments(after,REVISION_GRAPHEMES);let prefix=0;while(prefix<a.length&&prefix<b.length&&a[prefix].value===b[prefix].value)prefix++;let suffix=0;while(suffix<a.length-prefix&&suffix<b.length-prefix&&a.at(-1-suffix).value===b.at(-1-suffix).value)suffix++;const beforeStart=prefix<a.length?a[prefix].start:String(before).length,beforeEnd=suffix?a[a.length-suffix].start:String(before).length,afterStart=prefix<b.length?b[prefix].start:String(after).length,afterEnd=suffix?b[b.length-suffix].start:String(after).length;return {before:beforeEnd>beforeStart?[{start:beforeStart,end:beforeEnd}]:[],after:afterEnd>afterStart?[{start:afterStart,end:afterEnd}]:[]};}
function revisionTokenDiff(before,after){const a=revisionSegments(before,REVISION_WORDS),b=revisionSegments(after,REVISION_WORDS);if(a.length>700||b.length>700)return broadRevisionDiff(before,after);const width=b.length+1,table=Array.from({length:a.length+1},()=>new Uint16Array(width));for(let i=a.length-1;i>=0;i--)for(let j=b.length-1;j>=0;j--)table[i][j]=a[i].value===b[j].value?table[i+1][j+1]+1:Math.max(table[i+1][j],table[i][j+1]);const removed=[],added=[];let i=0,j=0;while(i<a.length||j<b.length){if(i<a.length&&j<b.length&&a[i].value===b[j].value){i++;j++;continue;}if(j<b.length&&(i===a.length||table[i][j+1]>table[i+1][j])){added.push({start:b[j].start,end:b[j].end});j++;}else if(i<a.length){removed.push({start:a[i].start,end:a[i].end});i++;}}return {before:mergeRevisionWhitespace(removed,before),after:mergeRevisionWhitespace(added,after)};}
export function revisionTextDiff(before,after,beforeAtoms=[],afterAtoms=[]){const atomKeys=rows=>rows.filter(row=>row?.key).map(row=>row.key);if(String(before??'')===String(after??'')&&JSON.stringify(atomKeys(beforeAtoms))===JSON.stringify(atomKeys(afterAtoms)))return {before:[],after:[]};const result=revisionTokenDiff(String(before??''),String(after??'')),semanticBefore=beforeAtoms.filter(row=>row?.key),semanticAfter=afterAtoms.filter(row=>row?.key),width=semanticAfter.length+1,table=Array.from({length:semanticBefore.length+1},()=>new Uint16Array(width));for(let i=semanticBefore.length-1;i>=0;i--)for(let j=semanticAfter.length-1;j>=0;j--)table[i][j]=semanticBefore[i].key===semanticAfter[j].key?table[i+1][j+1]+1:Math.max(table[i+1][j],table[i][j+1]);let i=0,j=0;while(i<semanticBefore.length||j<semanticAfter.length){if(i<semanticBefore.length&&j<semanticAfter.length&&semanticBefore[i].key===semanticAfter[j].key){i++;j++;continue;}if(j<semanticAfter.length&&(i===semanticBefore.length||table[i][j+1]>table[i+1][j])){result.after.push({start:semanticAfter[j].start,end:semanticAfter[j].end});j++;}else if(i<semanticBefore.length){result.before.push({start:semanticBefore[i].start,end:semanticBefore[i].end});i++;}}return {before:expandRevisionSpans(result.before,beforeAtoms),after:expandRevisionSpans(result.after,afterAtoms)};}
function revisionBlocksMatch(before,after){const keys=row=>(row.atoms||[]).filter(atom=>atom?.key).map(atom=>atom.key);return before.kind===after.kind&&before.text===after.text&&JSON.stringify(keys(before))===JSON.stringify(keys(after));}
export function revisionBlockDiff(beforeRows=[],afterRows=[]){const before=beforeRows.map(row=>({...row,text:String(row?.text??''),kind:String(row?.kind??'')})),after=afterRows.map(row=>({...row,text:String(row?.text??''),kind:String(row?.kind??'')})),width=after.length+1,table=Array.from({length:before.length+1},()=>new Uint16Array(width));for(let i=before.length-1;i>=0;i--)for(let j=after.length-1;j>=0;j--)table[i][j]=revisionBlocksMatch(before[i],after[j])?table[i+1][j+1]+1:Math.max(table[i+1][j],table[i][j+1]);const matches=[];let i=0,j=0;while(i<before.length&&j<after.length){if(revisionBlocksMatch(before[i],after[j])){matches.push([i,j]);i++;j++;}else if(table[i][j+1]>table[i+1][j])j++;else i++;}matches.push([before.length,after.length]);const result={before:before.map(()=>[]),after:after.map(()=>[])};let bi=0,ai=0;for(const [bm,am]of matches){const paired=Math.min(bm-bi,am-ai);for(let k=0;k<paired;k++){const diff=revisionTextDiff(before[bi+k].text,after[ai+k].text,before[bi+k].atoms,after[ai+k].atoms);result.before[bi+k]=diff.before;result.after[ai+k]=diff.after;}for(let k=bi+paired;k<bm;k++)result.before[k]=before[k].text?[{start:0,end:before[k].text.length}]:[];for(let k=ai+paired;k<am;k++)result.after[k]=after[k].text?[{start:0,end:after[k].text.length}]:[];bi=bm+1;ai=am+1;}return result;}

// Local author draft identity follows the immutable candidate, not the conversation
// currently open in the sidebar. This stores text only, never proposal authority.
export function proposalActionAllowed(edit,action) {
  return Array.isArray(edit?.allowed_actions)&&edit.allowed_actions.includes(action)
    &&(!['accept','replace-current','merge'].includes(action)||!proposalScopeUnproven(edit)&&!edit.local_draft_overlap);
}
// A local proposed-text draft retains the opaque source guard it began with.
// This metadata never grants an action or changes candidate/application truth.
export function proposalDecisionAcknowledged(result,{project,turnId,version,editId}){
  if(result?.project!==project||result.turn_id!==turnId||result.proposal_version!==version)return false;
  const effect=sourceEffectDisposition(result,{project});
  if(effect&&!effect.acknowledged)return false;
  const rows=(result.edits||[]).filter(row=>row.edit_id===editId),app=result.application;
  if(rows.length!==1||!['accepted','merged'].includes(rows[0].status)||!app?.id||app.project!==project||app.turn_id!==turnId||rows[0].application_id!==app.id||app.candidate_version!==version||!Array.isArray(app.candidate_edit_ids)||!app.candidate_edit_ids.includes(editId))return false;
  return !!rows[0].application_turn_id&&rows[0].application_turn_id===app.turn_id;
}
export function proposalDraftBasis(edit={},version){
  return typeof edit.review_token==='string'&&!!edit.review_token&&typeof edit.edit_id==='string'&&typeof version==='string'&&!!version
    ?{schema_version:'laplace.proposal-draft-basis/1',review_token:edit.review_token,edit_id:edit.edit_id,proposal_version:version}:null;
}
export function proposalDraftBasisMatches(basis,edit,version){
  const current=proposalDraftBasis(edit,version);
  return !!current&&basis?.schema_version===current.schema_version&&basis.review_token===current.review_token&&basis.edit_id===current.edit_id&&basis.proposal_version===current.proposal_version;
}
export function proposalDraftKey(project,turn,version,edit) {
  return 'laplace:proposal-draft:'+project+':'+turn+':'+version+':'+edit;
}
export function proposalSourceRows(text) {
  const rows=[];let offset=0;
  for(const part of String(text??'').split(/(\n\s*\n)/)){
    if(!part)continue;rows.push({kind:'source',text:part,start:offset,end:offset+part.length});offset+=part.length;
  }return rows;
}
export function proposalSourceChanges(before,after) {
  const current=proposalSourceRows(before),proposed=proposalSourceRows(after),plan=revisionBlockDiff(current,proposed);
  return {current,proposed,plan};
}

export function proposalDraftOverlap(drafts=[],edit={}) {
  const target=edit.current_anchor||edit.anchor||edit;
  const sameFile=(a,b)=>a===b||String(a||'').endsWith('/'+b)||String(b||'').endsWith('/'+a);
  return drafts.some(draft=>draft.unplaced||draft.transition||sameFile(draft.file,target.file)
    &&draft.line_start<=target.line_end&&draft.line_end>=target.line_start);
}

// Reader comment target (laplace.comment-source-selection/1): the exact raw interval of a rendered block selection in
// that block's OWN source, read from the renderer's piece map. Pure; the comment owner revalidates every field at
// prepare, Save and inspect. Offsets are Unicode code points (the tokenizer's units), so a partial selection in a
// source holding astral characters refuses rather than mixing UTF-16 and code-point offsets. The displayed text is an
// observation only, never the source target, and no TeX is stripped or inferred from rendered glyphs.
export const COMMENT_SOURCE_SELECTION='laplace.comment-source-selection/1';
export function commentSourceSelection({tex='',pieceMap=null,display='',start=null,end=null}={}){
  const source=String(tex||''),shown=String(display||''),flat=value=>String(value).replace(/\s+/g,' ').trim().slice(0,10000);
  if(!source)return {refused:'unmapped',reason:'This passage has no addressed source text; comment on a manuscript paragraph.',choices:[]};
  const whole={schema:COMMENT_SOURCE_SELECTION,kind:'whole-block',units:'unicode-codepoints',start:0,end:[...source].length,display_quote:flat(shown)};
  const lo=Number(start),hi=Number(end);
  if(start==null||end==null||(lo<=0&&hi>=shown.length))return {selection:whole};
  const choices=[{label:'Comment on the whole paragraph',selection:whole}],refuse=(refused,reason)=>({refused,reason,choices});
  if(!(hi>lo))return refuse('unmapped','Select some text in one paragraph.');
  if(/[\uD800-\uDFFF]/.test(source))return refuse('unicode','This paragraph holds characters whose browser and source positions differ; comment on the whole paragraph.');
  const map=(Array.isArray(pieceMap)?pieceMap:[]).filter(p=>[p?.rStart,p?.rEnd,p?.oStart,p?.oEnd].every(Number.isInteger)).sort((a,b)=>a.rStart-b.rStart);
  if(!map.length)return refuse('unmapped','This paragraph has no recorded source map for a partial selection; comment on the whole paragraph.');
  const edge=(at,tail)=>{
    const piece=map.find(p=>tail?at>p.rStart&&at<=p.rEnd:at>=p.rStart&&at<p.rEnd);
    if(!piece)return {refused:'unmapped'};
    if(at===(tail?piece.rEnd:piece.rStart))return tail?piece.oEnd:piece.oStart;
    if(piece.t!=='text')return {refused:piece.t==='math'?'inside-math':'inside-piece'};
    const k=at-piece.rStart;
    return String(piece.rText||'').slice(0,k)===source.slice(piece.oStart,piece.oStart+k)?piece.oStart+k:{refused:'unmapped'};
  };
  const from=edge(lo,false),to=edge(hi,true);
  for(const value of [from,to])if(typeof value==='object')return refuse(value.refused,value.refused==='inside-math'
    ?'This selection starts or ends inside rendered math; comment on the whole paragraph or select the whole formula.'
    :value.refused==='inside-piece'?'This selection starts or ends inside a citation, macro or code piece; comment on the whole paragraph.'
    :'This selection has no exact source position; comment on the whole paragraph.');
  const spanned=map.filter(p=>p.rEnd>lo&&p.rStart<hi);
  for(let i=1;i<spanned.length;i++)if(spanned[i].oStart!==spanned[i-1].oEnd)return refuse('gap','This selection spans source that is not displayed; comment on the whole paragraph.');
  if(!(to>from))return refuse('unmapped','This selection has no exact source position; comment on the whole paragraph.');
  return {selection:{schema:COMMENT_SOURCE_SELECTION,kind:'piece-span',units:'unicode-codepoints',start:from,end:to,display_quote:flat(shown.slice(lo,hi))}};
}

export function applicationSourceStateLabel(value) {
  return {POSTIMAGE:'Current files match this saved application.',PREIMAGE:"Current files match this application's earlier source.",DIVERGED:'Current files have changed since this application.',UNKNOWN:'Current files have not been compared with this application.'}[value]||'';
}
