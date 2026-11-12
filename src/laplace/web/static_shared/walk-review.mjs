// WALK REVIEW (S2 F7). Purpose: author changes and proposals over the canvas: revision highlights,
// paged author-change history and comparisons, and the one proposal view (recorded/historical and
// current), mounted through proposal-resolution.mjs. Owns: the author-change state and the single
// proposalView with its resolution controllers. Public contract: setAuthorChanges/
// refreshAuthorChanges, showProposal, clearProposal, refreshProposalView, manuscriptDraftRanges,
// proposalView. Read-only historical review never sends or saves; no proposal ledger or cache here.
import {sourceEffectDisposition} from './source-effect.mjs';
import store from "/shared/store.mjs";
import {
  applicationSourceStateLabel, manuscriptChangeAttribution, proposalActionAllowed,
  proposalComparisonAvailable, proposalDecisionAcknowledged, proposalDraftBasis, proposalDraftBasisMatches,
  proposalDraftKey, proposalDraftOverlap, proposalResolutionAvailable, proposalReviewStatus,
  proposalScopeUnproven, proposalSourceChanges, proposalStepHeading, revisionBlockDiff
} from "/shared/manuscript-editing.mjs";
import {
  mountProposalResolution, mountResolutionTarget, resolutionAuthorLabel, validateResolutionPreparation
} from "/shared/proposal-resolution.mjs";
import {docEl, el, emit, paper} from './walk-base.mjs';
import {blockById, normalizeDoc} from './walk-document.mjs';
import {S, attentionBlockId, captureFocus, measure, noteAttention, restoreFocus} from './walk-position.mjs';
import {asChrome, buildBlock} from './walk-blocks.mjs';
import {hostText, nodeTextLen, offsetIn, srcOf} from './walk-selection.mjs';
import {E, P} from './walk-drafts.mjs';
import {F} from './walk-flip.mjs';
import {setEditable} from './walk-editing.mjs';
import {caretRange} from './walk-card.mjs';
import {clearObjectSelection, paragraphTransition} from './walk-paragraph-ops.mjs';

// Human edits use the existing author-history/baseline projection, rendered beside
// their current source. Comparing a passage never replaces its editable DOM.
let authorChangesEnabled=localStorage.getItem('laplace:author-changes')!=='off',authorChangesGeneration=0,authorChangesSuspended=false,authorComparisonBeforeReview=null;
const authorChangeRecords=new Map();
const revisionHighlightRanges={authorAddition:[],authorDeletion:[],proposalAddition:[],proposalDeletion:[]};
const revisionHighlightNames={authorAddition:'author-addition',authorDeletion:'author-deletion',proposalAddition:'proposal-addition',proposalDeletion:'proposal-deletion'};
const revisionAtomClasses={authorAddition:'revision-author-addition',authorDeletion:'revision-author-deletion',
  proposalAddition:'revision-proposal-addition',proposalDeletion:'revision-proposal-deletion'};
function syncRevisionHighlights(kinds=Object.keys(revisionHighlightRanges)){
  if(!globalThis.CSS?.highlights||typeof globalThis.Highlight!=='function')return false;
  for(const kind of kinds){const name=revisionHighlightNames[kind],ranges=revisionHighlightRanges[kind];if(ranges.length)CSS.highlights.set(name,
    new Highlight(...ranges));else CSS.highlights.delete(name);}return true;
}
function clearRevisionHighlights(kinds){for(const kind of kinds)revisionHighlightRanges[kind]=[];syncRevisionHighlights(kinds);}
function revisionAtomKey(node){if(node.classList.contains('mathq'))return 'math:'+String(node.dataset.tex||node.getAttribute('aria-label')||'');if(
  node.classList.contains('cite-wrap'))return 'cite:'+[...node.querySelectorAll('[data-key]')].map(item=>item.dataset.key).join(',');if(
  node.classList.contains('ref'))return 'ref:'+String(node.dataset.label||node.getAttribute('href')||'');return 'atom:'+hostText(node);}
function revisionAtoms(host){const selector='.mathq,.cite-wrap,.ref,.structural-piece',rows=[];for(const node of host?.querySelectorAll(selector)||[
  ]){if(node.parentElement?.closest(selector))continue;const start=offsetIn(host,node,0),end=start+nodeTextLen(node);if(end>start)rows.push({start,
  end,key:revisionAtomKey(node),node});}return rows;}
function revisionRows(blocks){return (blocks||[]).map(block=>{const host=block?.bodyEl||block?.querySelector?.('.blk-body')||
  block?.el?.querySelector?.('.blk-body'),actual=host?hostText(host):'',actualAtoms=host?revisionAtoms(host).sort((a,b)=>a.start-b.start):[],chunks=[
  ];let text='',cursor=0;for(const atom of actualAtoms){if(atom.start>cursor){chunks.push({cStart:text.length,cEnd:text.length+atom.start-cursor,
  aStart:cursor,aEnd:atom.start,atom:false});text+=actual.slice(cursor,atom.start);}const start=text.length;text+='\ufffc';chunks.push({cStart:start,
  cEnd:start+1,aStart:atom.start,aEnd:atom.end,atom:true});atom.cStart=start;atom.cEnd=start+1;cursor=atom.end;}if(cursor<actual.length){chunks.push({
  cStart:text.length,cEnd:text.length+actual.length-cursor,aStart:cursor,aEnd:actual.length,atom:false});text+=actual.slice(cursor);}return {
  kind:block?.kind||block?.el?.dataset.kind||block?.dataset?.kind||'',text,atoms:actualAtoms.map(atom=>({start:atom.cStart,end:atom.cEnd,
  key:atom.key})),actualAtoms,chunks,host,block};});}
function revisionActualSpan(row,span){const boundary=(offset,end)=>{const chunk=row.chunks.find(item=>end?offset>item.cStart&&
  offset<=item.cEnd:offset>=item.cStart&&offset<item.cEnd);if(!chunk)return end?hostText(row.host).length:0;if(
  chunk.atom)return end?chunk.aEnd:chunk.aStart;return chunk.aStart+offset-chunk.cStart;};return {start:boundary(span.start,false),end:boundary(span.end,true)};}
function paintRevisionDifference(beforeBlocks,afterBlocks,beforeKind,afterKind){const before=revisionRows(beforeBlocks),after=revisionRows(
  afterBlocks),plan=revisionBlockDiff(before,after),supported=syncRevisionHighlights([]);for(const [rows,spans,kind]of [[before,plan.before,
  beforeKind],[after,plan.after,afterKind]])for(let index=0;index<rows.length;index++){if(!spans[index]?.length)continue;const row=rows[index],{host,
  block,actualAtoms}=row;if(!supported){(block?.el||block)?.classList?.add('revision-changed-fallback');continue;}for(const canonicalSpan of spans[
  index]){const span=revisionActualSpan(row,canonicalSpan);let textSpans=[span];for(const atom of actualAtoms.filter(atom=>span.start<atom.end&&
  span.end>atom.start)){atom.node.classList.add(revisionAtomClasses[kind]);textSpans=textSpans.flatMap(part=>part.end<=atom.start||
  part.start>=atom.end?[part]:[{start:part.start,end:Math.min(part.end,atom.start)},{start:Math.max(part.start,atom.end),end:part.end}]).filter(part=>
  part.end>part.start);}for(const textSpan of textSpans){const range=caretRange(host,textSpan.start,textSpan.end);if(
  !range.collapsed)revisionHighlightRanges[kind].push(range);}}}return plan;}
function clearAuthorChanges(){clearRevisionHighlights(['authorAddition','authorDeletion']);for(const node of docEl.querySelectorAll(
  '.revision-author-addition,.revision-author-deletion'))node.classList.remove('revision-author-addition','revision-author-deletion');for(
  const block of S.blocks)block.el?.classList.remove('author-changed','revision-changed-fallback');for(const node of docEl.querySelectorAll(
  '[data-author-change-ui]'))node.remove();}
function authorChangeNode(tag,cls,text){const node=asChrome(el(tag,cls,text));node.dataset.authorChangeUi='';node.contentEditable='false';return node;}
function showAuthorComparison(hunk,data,marker){
  docEl.querySelector('.author-change-comparison')?.remove();
  const card=authorChangeNode('section','author-change-comparison');card.setAttribute('aria-label','Saved manuscript change');card.changePreview={hunk,data};
  const head=el('header'),{who}=manuscriptChangeAttribution(data,hunk.deleted);head.append(el('strong',null,who+' · '+(hunk.deleted?'Deleted passage':'Changed passage')));
  const close=el('button',null,'Close comparison');close.type='button';close.onclick=()=>{card.remove();measure();};head.append(close);card.append(head);
  if(data.note)card.append(el('p','author-change-note',data.note));
  const versions=el('div','author-change-versions');for(const [label,models,cls]of [['Before',hunk.before_blocks,'author-change-before'],['Now',
    hunk.after_blocks,'author-change-after']]){const version=el('div',cls);version.append(el('p','proposal-label',label));if(
    models?.length)proposalModels(version,models,'author-'+crypto.randomUUID());else version.append(el('p','author-change-empty',
    label==='Before'?'No previous passage.':'Passage removed.'));versions.append(version);}card.append(versions);
  const detail=el('details'),summary=el('summary',null,'Source and attribution');detail.append(summary,el('p',null,
    `${hunk.anchor.file}:${hunk.anchor.line_start}–${hunk.anchor.line_end}`));if(data.baseline)detail.append(el('p',null,'Compared with '+(
    data.baseline.version_id||data.baseline.id||data.baseline.name||'the recorded baseline')));if(data.whole_file)detail.append(el('p',null,
    'This comparison is recorded at file level; it does not attribute each sentence separately.'));if(data.correction?.created)detail.append(el('p',
    null,'Saved '+new Date(data.correction.created).toLocaleString()));card.append(detail);
  marker.after(card);measure();
}
function paintAuthorHunks(data){
  if(data.locatable===false){emit('editor-status',{text:data.note||'This historical change cannot be safely matched to the current manuscript.',error:true});return 0;}
  let count=0;
  for(const [index,hunk]of (data.hunks||[]).entries()){
    const range=hunk.anchor;if(!range)continue;const sameFile=block=>srcOf(block).file===range.file||String(range.file).endsWith('/'+srcOf(block).file);
    const fileBlocks=S.blocks.filter(sameFile),covered=hunk.deleted?[]:fileBlocks.filter(block=>srcOf(block).lineStart<=range.line_end&&srcOf(block).lineEnd>=range.line_start);
    const anchor=covered[0]||fileBlocks.find(block=>srcOf(block).lineStart>=range.line_start)||fileBlocks.at(-1);if(!anchor?.el)continue;
    const entry=authorChangeNode('div','author-change-entry'),attribution=manuscriptChangeAttribution(data,hunk.deleted),marker=el('button',
      'author-change-marker',attribution.marker);marker.type='button';marker.setAttribute('aria-label',attribution.inspect);marker.onclick=()=>
      showAuthorComparison(hunk,data,marker);marker.changePreview={hunk,data};marker.dataset.changeFile=range.file;marker.dataset.changeIndex=String(
      index);marker.dataset.changeStart=String(range.line_start);marker.dataset.changeEnd=String(range.line_end);entry.append(marker);
    const previous=el('div','author-change-removed');previous.append(el('p','proposal-label','Removed from the saved passage'));
    const previousBlocks=proposalModels(previous,hunk.before_blocks,'author-inline-'+index),plan=paintRevisionDifference(previousBlocks,covered,'authorDeletion','authorAddition');
    if(plan.before.some(spans=>spans.length))entry.append(previous);for(const [blockIndex,block]of covered.entries())if(plan.after[
      blockIndex]?.length&&!data.whole_file)block.el.classList.add('author-changed');
    anchor.el.before(entry);count++;
  }return count;
}
const authorHistoryPages=new Map();
async function refreshAuthorChanges(options={}){
  if(authorChangesSuspended)return;
  if(!authorChangesEnabled&&!options.id&&!options.force)return;
  const generation=++authorChangesGeneration,files=options.file?[options.file]:[...new Set(S.blocks.map(block=>srcOf(block).file).filter(Boolean))],datasets=[],errors=[];
  const read=async queries=>{for(let offset=0;offset<queries.length;offset+=4){if(generation!==authorChangesGeneration)return;
    const results=await Promise.allSettled(queries.slice(offset,offset+4).map(query=>store.fetchJSON('/authoring/change-preview?'+new URLSearchParams(
    {project:S.corpus,...query}))));for(const result of results)if(result.status==='fulfilled')datasets.push(result.value);else errors.push(result.reason);}};
  await read(options.id?[{id:options.id}]:files.map(file=>({file})));if(generation!==authorChangesGeneration)return;
  if(!options.id){
    const missingBaseline=[...new Set([...datasets.filter(data=>data.whole_file||data.attributed===false).map(data=>data.file),...(
      options.historyOlder?files.filter(file=>authorHistoryPages.has(file)):[])])],ids=new Set([...authorChangeRecords].filter(([file])=>files.includes(file)).map(([,id])=>id));
    for(let offset=0;offset<missingBaseline.length;offset+=4){
      const results=await Promise.allSettled(missingBaseline.slice(offset,offset+4).map(async file=>{
        const prior=options.historyOlder?authorHistoryPages.get(file):null;if(prior&&prior.next_offset==null)return;
        const page=await store.fetchJSON('/authoring/history?'+new URLSearchParams({project:S.corpus,file,correction_category:'applied-edits',
          order:'newest',offset:String(prior?.next_offset||0),limit:'25',...(prior?.as_of?{as_of:prior.as_of}:{})}));
        if(generation!==authorChangesGeneration)return;
        const loaded=[...(prior?.ids||[]),...(page.items||[]).map(row=>row.id)];authorHistoryPages.set(file,{ids:[...new Set(loaded)],
          next_offset:page.next_offset,as_of:page.as_of});
      }));if(generation!==authorChangesGeneration)return;for(const result of results)if(result.status==='rejected')errors.push(result.reason);
      if(errors.some(error=>error.refused?.status==='CHANGED_INPUT'||error.body?.status==='CHANGED_INPUT'||error.status===409)){emit('editor-status',{
        text:'Saved change history advanced. Existing comparisons and drafts are preserved; load the latest history to continue.',error:true,retry:(
        )=>refreshAuthorChanges({...options,historyOlder:false})});return;}
    }
    for(const file of missingBaseline)for(const id of authorHistoryPages.get(file)?.ids||[])ids.add(id);
    if(ids.size)await read([...ids].map(id=>({id})));
  }
  if(generation!==authorChangesGeneration)return;
  // Finish all reads before changing geometry. Background comparison loading
  // cannot restore an old scroll position after the author has moved elsewhere.
  const focus=captureFocus(),open=options.restoreComparison||docEl.querySelector('.author-change-comparison')?.changePreview;clearAuthorChanges();let count=0;const seen=new Set();
  for(const data of datasets){if(data.whole_file||data.attributed===false)continue;const hunks=(data.hunks||[]).filter(hunk=>{
    const key=JSON.stringify(hunk.anchor);if(seen.has(key))return false;seen.add(key);return true;});if(hunks.length)count+=paintAuthorHunks({...data,
    hunks});else if(options.id&&data.locatable===false)emit('editor-status',{text:data.note||'This historical change cannot be safely matched to current source.',error:true});}
  const older=options.id?[]:[...authorHistoryPages].filter(([file,page])=>files.includes(file)&&page.next_offset!=null);
  if(older.length){const pager=authorChangeNode('div','author-change-history-pager'),button=el('button',null,'Load older saved changes');
    button.type='button';button.onclick=()=>refreshAuthorChanges({...options,historyOlder:true,focus:false});pager.append(button);docEl.append(pager);}
  syncRevisionHighlights(['authorAddition','authorDeletion']);if(open){const marker=[...docEl.querySelectorAll('.author-change-marker')].find(node=>
    node.changePreview?.hunk.anchor.file===open.hunk.anchor.file&&node.changePreview.hunk.before===open.hunk.before&&
    node.changePreview.hunk.after===open.hunk.after);if(marker)showAuthorComparison(marker.changePreview.hunk,marker.changePreview.data,marker);}
  measure();restoreFocus(focus);if(errors.length)emit('editor-status',{text:'Some change comparisons could not load: '+(errors[0]?.message||
    'connection unavailable'),error:true,retry:()=>refreshAuthorChanges(options)});
  if(options.focus){const marker=docEl.querySelector('[data-author-change-ui].author-change-marker');if(marker){paper.scrollTop=Math.max(0,
    marker.offsetTop-30);marker.click();}else emit('editor-status',{text:'No safely located changes were found at this source.'});}return count;
}
function setAuthorChanges(enabled,{refresh=true}={}){authorChangesEnabled=!!enabled;localStorage.setItem('laplace:author-changes',enabled?'on':'off');
  if(enabled)return refresh?refreshAuthorChanges():undefined;authorChangesGeneration++;clearAuthorChanges();measure();}

function suspendAuthorChanges(){
  if(authorChangesSuspended)return;
  authorChangesSuspended=true;authorChangesGeneration++;
  authorComparisonBeforeReview=docEl.querySelector('.author-change-comparison')?.changePreview||null;
  clearAuthorChanges();
}
function resumeAuthorChanges(refresh=true){
  if(!authorChangesSuspended)return;
  authorChangesSuspended=false;
  const restoreComparison=authorComparisonBeforeReview;authorComparisonBeforeReview=null;
  if(refresh&&authorChangesEnabled)void refreshAuthorChanges({focus:false,restoreComparison}).catch(error=>emit('editor-status',{
    text:'Saved author changes remain in History; their display could not refresh: '+error.message,error:true}));
}

// Saved suggestions live at their manuscript location. The source stays unchanged
// until a decision succeeds; rendering uses the same typed block model as the reader.
let proposalView=null;
const proposalResolutionControllers=new Set();
const proposalUiStates=new Map();
async function refreshProposalView(){
  const view=proposalView;if(!view)return;
  try{const next=await view.options.onRefresh?.();if(proposalView===view)showProposal(next||view.data,{...view.options,focus:false,inspectionActive:view.inspectionActive});}
  catch(error){emit('editor-status',{text:'The saved suggestion could not refresh: '+error.message,error:true});}
}
function clearProposal({restoreAuthorOverlay=true,refreshAuthorOverlay=true}={}){
  for(const controller of proposalResolutionControllers)controller.destroy();proposalResolutionControllers.clear();
  clearRevisionHighlights(['proposalAddition','proposalDeletion']);for(const node of docEl.querySelectorAll(
    '.revision-proposal-addition,.revision-proposal-deletion'))node.classList.remove('revision-proposal-addition','revision-proposal-deletion');for(
    const b of S.blocks){if(b.proposalHome?.isConnected)b.proposalHome.replaceWith(b.el);delete b.proposalHome;delete b.proposalDisplayEl;if(
    !b.proposalLocked)continue;b.proposalLocked=false;b.el?.classList.remove('proposal-before','revision-changed-fallback');b.el?.removeAttribute(
    'data-proposal-label');if(b.bodyEl)setEditable(b,b.bodyEl);const handle=b.el?.querySelector('[data-object-handle]');if(handle)handle.disabled=false;}
  for(const node of docEl.querySelectorAll('[data-proposal-ui]'))node.remove();proposalView=null;
  if(restoreAuthorOverlay)resumeAuthorChanges(refreshAuthorOverlay);
}
function proposalModels(host,models,id){
  const normalized=normalizeDoc({sections:[{id:'proposal-'+id,blocks:models||[]}]}).sections[0]?.blocks||[];
  for(const [index,b]of normalized.entries()){b.id='proposal-'+id+'-'+index;const node=buildBlock(b);delete node.dataset.block;
    node.dataset.proposalBlock='';node.tabIndex=-1;node.querySelectorAll('[contenteditable]').forEach(el=>el.setAttribute('contenteditable','false'));
    host.append(node);}return normalized;
}
function pendingSuccessorLinks(host,edit,options){
  const rows=Array.isArray(edit.pending_successors)?edit.pending_successors:edit.disposition_status==='PENDING'?[edit]:[];
  if(!rows.length||!options.onReadCandidate)return;
  host.append(el('p','proposal-location-warning','A later revision saved this text. Its reconciliation record still needs finishing.'));
  for(const row of rows){if(row.disposition_status!=='PENDING'||!row.successor_read||!row.successor_ref)continue;
    const read=el('button','proposal-refresh','Read saved successor to finish reconciliation record');read.type='button';read.onclick=()=>
      options.onReadCandidate(row.successor_read,row.successor_ref);host.append(read);
  }
}
function showRecordedProposal(data,options){
  const review=el('section','manuscript-proposal proposal-history');review.contentEditable='false';review.dataset.proposalUi='history';
    review.setAttribute('aria-label','Saved manuscript comparison');
  const header=asChrome(el('header','proposal-history-heading')),labels={applied:'Accepted',rejected:'Rejected',
    'applied-elsewhere':'Applied in another turn',superseded:'Superseded',fulfilled:'Already fulfilled',
    'resolved-into-successor':'Resolved in a later revision'};header.append(el('strong',null,labels[data.proposal_state]||'Saved comparison'));
    const close=el('button',null,'Close comparison');close.type='button';close.dataset.closeComparison='true';close.onclick=()=>{
    const back=proposalView?.inspectionActive!==false,place=back?options.returnFocus:captureFocus(),
    attention=back?options.returnAttention:attentionBlockId;clearProposal();noteAttention(attention??null);measure();if(place)restoreFocus(place);
    emit('attention',{block:attentionBlockId});};header.append(close);review.append(header,asChrome(el('p','proposal-label',
    data.candidate_ref?'Saved current-source revision · application and scientific review remain separate':'Recorded text comparison · inspect only')));
  const navigation=data.navigation_edits||data.edits||[];
  if(navigation.length>1&&options.onSelectEdit){const choice=el('select','proposal-edit-choice');choice.setAttribute('aria-label',
    'Read exact historical edit');for(const row of navigation){const item=el('option',null,'Recorded edit '+(navigation.indexOf(
    row)+1)+' · '+row.file);item.value=row.edit_id;choice.append(item);}choice.value=data.edits?.[0]?.edit_id;choice.onchange=async()=>{
    choice.disabled=true;const current=proposalView;try{const next=await options.onSelectEdit(choice.value);if(proposalView!==current)return;
    showProposal(next,{...options,readOnly:true});}catch(error){if(proposalView===current)emit('editor-status',{
    text:'The selected historical body could not be read: '+error.message,error:true});}finally{choice.disabled=false;}};review.append(choice);}

  for(const edit of data.edits||[]){const item=el('section','proposal-history-edit');item.append(asChrome(el('p','proposal-label',edit.file+(
    edit.line_start?' · recorded line '+edit.line_start:''))));const sourceState=applicationSourceStateLabel(edit.application_source_state);if(
    sourceState)item.append(asChrome(el('p','proposal-label',sourceState)));const columns=el('div','proposal-versions'),before=el('div',
    'proposal-current'),after=el('div','proposal-replacement');before.append(asChrome(el('p','proposal-label','Before')));after.append(asChrome(el(
    'p','proposal-label',
    edit.status==='resolved-into-successor'?'Original proposed text · resolved in a later revision':edit.status==='rejected'?'Proposed, not applied':
    edit.status==='pending'||edit.status==='conflict'?'Proposed text':'After')));const oldBlocks=proposalModels(before,edit.before_blocks,
    edit.edit_id+'-history-before'),newBlocks=proposalModels(after,edit.after_blocks,edit.edit_id+'-history-after');paintRevisionDifference(oldBlocks,
    newBlocks,'proposalDeletion','proposalAddition');if(!edit.before_blocks?.length)before.append(el('pre',null,edit.before||'[Empty passage]'));if(
    !edit.after_blocks?.length)after.append(el('pre',null,edit.after||'[Empty passage]'));columns.append(before,after);item.append(columns);if(
    edit.pending_successors?.length||edit.disposition_status==='PENDING')pendingSuccessorLinks(item,edit,options);if(
    edit.status==='resolved-into-successor'){item.append(el('p','proposal-label',
    'Source application belongs to the later revision; this original proposal remains saved history.'));if(edit.successor_read&&edit.successor_ref&&
    options.onReadCandidate){const successor=el('button',null,'Read applied successor');successor.type='button';successor.onclick=()=>
    options.onReadCandidate(edit.successor_read,edit.successor_ref);item.append(successor);}}const draftState=proposalUiStates.get(proposalDraftKey(
    S.corpus,data.candidate_ref?.id||data.turn_id,data.proposal_version,edit.edit_id));let retained=draftState?.draftText;try{
    retained??=localStorage.getItem(proposalDraftKey(S.corpus,data.candidate_ref?.id||data.turn_id,data.proposal_version,edit.edit_id));}catch{}if(
    retained!=null){const local=el('details','proposal-retained-draft');local.dataset.retainedProposalDraft=proposalDraftKey(S.corpus,
    data.candidate_ref?.id||data.turn_id,data.proposal_version,edit.edit_id);local.append(el('summary',null,
    'Retained local proposed text · not an application record'));const textarea=el('textarea','proposal-merge-editor');textarea.readOnly=true;
    textarea.value=retained;textarea.setAttribute('aria-label','Retained local proposed text');local.append(el('p','proposal-label',
    'This local text is preserved separately from the saved candidate and its recorded application.'),textarea);item.append(local);}review.append(item);}
  const source=el('details','proposal-history-source');source.append(el('summary',null,'Exact saved source'));let sourceRead=false;source.ontoggle=(
    )=>{if(!source.open||sourceRead)return;sourceRead=true;for(const edit of data.edits||[]){source.append(el('strong',null,edit.file),el('p',
    'proposal-label','Before'),el('pre',null,edit.before||'[Empty passage]'),el('p','proposal-label','After / proposed'),el('pre',null,edit.after||
    '[Empty passage]'));}};review.append(source);
  if(data.candidate_ref){
    const provenance=el('details','proposal-details');provenance.append(el('summary',null,'Revision authorship and predecessor'),el('p',null,
      resolutionAuthorLabel(data.author)+' · '+data.candidate_ref.id));
    if(data.predecessor_read&&options.onOpenPredecessor){const original=el('button',null,'Read predecessor comparison');original.type='button';
      original.onclick=()=>options.onOpenPredecessor(data.predecessor_read,data.predecessor);provenance.append(original);}
    if(data.origin_turn_id&&options.onInspectOrigin){const origin=el('button',null,'Read originating turn');origin.type='button';origin.onclick=()=>
      options.onInspectOrigin(data.origin_turn_id);provenance.append(origin);}
    for(const obligation of data.review_obligations||[])provenance.append(el('p','proposal-location-warning',
      typeof obligation==='string'?obligation:obligation.reason||obligation.message||JSON.stringify(obligation)));
    review.append(provenance);
    if(data.disposition?.status==='PENDING'){
      review.append(el('p','proposal-location-warning','The text is saved. Only the record resolving its predecessor remains to be finished.'));
      if(data.disposition.recovery_action&&options.onFinishResolution){const finish=el('button','primary','Finish reconciliation record'),status=el(
        'p','proposal-decision-status');finish.type='button';finish.onclick=async()=>{finish.disabled=true;try{await options.onFinishResolution(
        data.disposition.recovery_action,data.candidate_ref,data.disposition);}catch(error){status.textContent=error.message;finish.disabled=false;}};review.append(finish,status);}
    }
    if(data.apply_action?.permitted===false)review.append(el('p','proposal-location-warning',data.apply_action.reason||
      'The retained revision cannot be applied against its current source guard. Resolve it against an inspected current passage.'));
    if(data.apply_action?.permitted!==false&&data.apply_action&&options.onApplyCandidate){const apply=el('button','primary',
      'Apply retained revision'),status=el('p','proposal-decision-status');apply.type='button';apply.onclick=async()=>{apply.disabled=true;try{
      await options.onApplyCandidate(data.apply_action,data.candidate_ref);}catch(error){
      status.textContent=error.message+' The exact resolved revision remains retained.';apply.disabled=false;}};review.append(apply,status);}
  }
  if(data.candidate_ref&&options.allowResolution&&data.read_only!==true&&options.onPrepareResolution&&options.onResolutionRequest){
    for(const edit of data.edits||[]){if(edit.resolution_action?.permitted!==true)continue;
      const host=el('section','proposal-human-resolution'),start=el('button','primary','Resolve against current source'),status=el('p',
        'proposal-decision-status');start.type='button';review.append(start,status,host);let controller=null;
      const stateKey=proposalDraftKey(S.corpus,data.candidate_ref.id,data.proposal_version,edit.edit_id);let state=proposalUiStates.get(stateKey);if(
        !state){state={};proposalUiStates.set(stateKey,state);}state.resolutionDraft??={};
      const alive=()=>proposalView?.data===data&&host.isConnected!==false;
      const prepare=async target=>{const observed=await options.onPrepareResolution(edit,target);if(!alive())return;validateResolutionPreparation(
        observed,{project:S.corpus});if(controller){controller.destroy();proposalResolutionControllers.delete(controller);}host.replaceChildren();
        state.resolutionDraft.needs_inspection=false;
        if(observed.target_required)controller=mountResolutionTarget(host,{project:S.corpus,value:observed,request:options.onResolutionRequest,
          isCurrent:alive,onTarget:prepare,onCancel:()=>host.replaceChildren()});
        else{let storage=null;try{storage=window.sessionStorage;}catch{}controller=mountProposalResolution(host,{project:S.corpus,value:observed,
          state:state.resolutionDraft,storage,storageKey:stateKey+':resolution',request:options.onResolutionRequest,isCurrent:alive,onRefresh:()=>
          prepare(),onReadCandidate:options.onReadCandidate,onFinishResolution:options.onFinishResolution,onApplied:options.onHumanApplied,
          renderPreview:(target,result)=>{if(result.after_blocks?.length)proposalModels(target,result.after_blocks,edit.edit_id+'-resolved');
          else target.append(el('pre','proposal-exact-source',result.resolved_after));}});}
        proposalResolutionControllers.add(controller);
      };
      start.onclick=async()=>{start.disabled=true;try{await prepare();}catch(error){if(alive())status.textContent=error.message;}finally{start.disabled=false;}};
    }
  }
  const firstFile=data.edits?.[0]?.file,anchor=S.blocks.find(block=>srcOf(block).file===firstFile)||S.blocks[0];if(anchor?.el)anchor.el.before(
    review);else docEl.prepend(review);if(proposalView){proposalView.inspectionActive=options.inspectionActive!==false;if(
    proposalView.inspectionActive)noteAttention(anchor?.id||null);}syncRevisionHighlights(['proposalAddition','proposalDeletion']);measure();if(
    options.focus!==false)paper.scrollTop=Math.max(0,review.offsetTop-16);emit('attention',{inspection:true});emit('editor-status',{
    text:data.candidate_ref?'Saved resolved revision · source application and scientific review are separate.':'Saved comparison · inspect only.'});return 0;
}
function manuscriptDraftRanges(){
  const drafts=[];const add=(source,extra={})=>{if(source)drafts.push({file:source.file,line_start:source.lineStart??source.line_start,
    line_end:source.lineEnd??source.line_end,...extra});};
  for(const [id,entry]of P)if(!entry.noteOnly&&entry.text!==entry.pristine)add(entry.src||srcOf(blockById.get(id)||{}),{unplaced:entry.unplaced});
  if(E.dirty)add(srcOf(blockById.get(E.blockId)||{}));
  const flipped=blockById.get(F.blockId);if(flipped&&F.ta&&F.ta.value!==(F.baseTex??flipped.tex??''))add(F.baseSource||srcOf(flipped));
  if(paragraphTransition||E.committing||F.saving)drafts.push({transition:true});return drafts;
}
function showProposal(data,options={}){
  for(const node of docEl.querySelectorAll('[data-proposal-state-key]')){
    const state=proposalUiStates.get(node.dataset.proposalStateKey);if(!state)continue;
    const editor=node.querySelector('.proposal-merge-editor');if(editor){state.caretStart=editor.selectionStart;state.caretEnd=editor.selectionEnd;
      state.editorScroll=editor.scrollTop;state.editorFocused=document.activeElement===editor;}
    state.viewport=node.getBoundingClientRect().top;state.scrollWithin=paper.scrollTop-node.offsetTop;
  }
  const reviewedVersion=data.proposal_version;
  clearObjectSelection(true);const focus=captureFocus();clearProposal({restoreAuthorOverlay:false});suspendAuthorChanges();proposalView={data,
    options};let first=null,firstBlockId=null;
  if(options.readOnly){const saved={...options,returnFocus:options.returnFocus||focus,returnAttention:Object.hasOwn(options,
    'returnAttention')?options.returnAttention:attentionBlockId};proposalView.options=saved;return showRecordedProposal(data,saved);}
  const terminal=data.read_only||['applied','rejected','applied-elsewhere','superseded','fulfilled','resolved-into-successor'].includes(data.proposal_state);
  // M5 approval: an applied, rejected or superseded suggestion is shown as its saved outcome (with its successor when
  // one exists), never as awaiting approval and never as an empty review.
  if(terminal&&data.proposal_state&&data.edits?.length){const saved={...options,returnFocus:options.returnFocus||focus,returnAttention:Object.hasOwn(options,
    'returnAttention')?options.returnAttention:attentionBlockId};proposalView.options=saved;return showRecordedProposal(data,saved);}
  const pending=terminal?[]:(data.edits||[]).filter(edit=>edit.lifecycle!=='retained-history'&&['pending','conflict'].includes(edit.status));
  const selectedEditId=pending.find(edit=>edit.edit_id===options.selectedEditId)?.edit_id||pending[0]?.edit_id;proposalView.options.selectedEditId=selectedEditId;
  for(const original of pending.filter(edit=>edit.edit_id===selectedEditId)){
    const edit={...original,local_draft_overlap:proposalDraftOverlap(manuscriptDraftRanges(),original)};
    const humanAvailable=edit.resolution_action?.permitted===true&&typeof options.onPrepareResolution==='function'&&typeof options.onResolutionRequest==='function';
    const conflict=edit.status==='conflict',unproven=proposalScopeUnproven(edit),stateKey=proposalDraftKey(S.corpus,data.candidate_ref?.id||
      data.turn_id,reviewedVersion,edit.edit_id),ui=proposalUiStates.get(stateKey)||{mode:'changes'},range=conflict&&edit.current_anchor&&
      !unproven?edit.current_anchor:edit.anchor||edit;
    const fileBlocks=S.blocks.filter(b=>srcOf(b).file===range.file);
    const covered=unproven||edit.local_draft_overlap?[]:fileBlocks.filter(b=>srcOf(b).lineStart<=range.line_end&&srcOf(b).lineEnd>=range.line_start);
    const anchor=unproven||edit.local_draft_overlap?fileBlocks[0]||S.blocks[0]:covered[0]||fileBlocks.find(b=>srcOf(b).lineStart>=range.line_start)||
      fileBlocks.at(-1)||S.blocks[0];if(!anchor?.el)continue;
    const review=el('section','manuscript-proposal');review.contentEditable='false';review.dataset.proposalUi=edit.edit_id;
      review.dataset.sourceBlock=anchor.id;review.dataset.conflict=String(conflict);review.dataset.scopeUnproven=String(unproven);
      review.dataset.proposalStateKey=stateKey;proposalUiStates.set(stateKey,ui);review.setAttribute('aria-label',
      conflict?'Compare changed manuscript passage':'Proposed manuscript change');
    // Proven comparisons use current source blocks. An unproven scope renders the
    // retained before snapshot instead and never moves or locks a current block.
    // THE PROPOSAL HEADER (M5 C7; repair H4): task-oriented, its ordinal and total come from the
    // owner's navigation scope and the selected exact edit (proposalStepHeading), never from the
    // loaded bodies; the mode chip and the overlay's exit (return to place) are unchanged.
    const step=proposalStepHeading(data,edit.edit_id,{conflict,unproven,file:range.file}),head=asChrome(el('header','proposal-head'));
    head.append(el('span','proposal-eyebrow',step.eyebrow),el('span','proposal-mode-chip',step.chip));if(step.note)head.append(el('span',
      'proposal-step-note',step.note));review.append(head);
    const versions=el('div','proposal-versions'),current=el('div','proposal-current'),proposed=el('div','proposal-replacement');
    current.append(asChrome(el('p','proposal-label',
      unproven?'Original saved passage · historical comparison':edit.local_draft_overlap?'Saved source · your unsaved text stays in the manuscript':
      'Current manuscript · proposed deletions marked')));
    let comparisonBlocks=covered;
    if(edit.local_draft_overlap&&!unproven){comparisonBlocks=proposalModels(current,edit.current_blocks||[],edit.edit_id+'-saved-current');if(
      !comparisonBlocks.length)current.append(el('pre',null,edit.current_before||edit.before));}
    else if(unproven){comparisonBlocks=proposalModels(current,edit.before_blocks,edit.edit_id+'-historical');if(
      !comparisonBlocks.length)current.append(el('pre',null,edit.before||'[Empty saved passage]'));}
    else for(const block of covered){const home=document.createComment('proposal source location');block.el.before(home);block.proposalHome=home;
      block.proposalLocked=true;block.bodyEl?.setAttribute('contenteditable','false');const handle=block.el.querySelector('[data-object-handle]');if(
      handle)handle.disabled=true;current.append(block.el);}
    proposed.append(asChrome(el('p','proposal-label','Proposed revision · additions marked')));const proposedBlocks=proposalModels(proposed,
      edit.after_blocks,edit.edit_id);if(!proposedBlocks.length){if(typeof edit.after==='string'){proposed.append(asChrome(el('p','proposal-label',
      'Exact proposed LaTeX source · rendered preview unavailable')),el('pre','proposal-exact-source',edit.after||
      '[Empty proposed source; passage removal]'));}else proposed.append(el('p','proposal-location-warning',
      'The proposed text is unavailable. Applying this edit is disabled.'));}if(!covered.length&&!unproven&&!edit.local_draft_overlap){if(
      edit.current_blocks?.length||edit.before_blocks?.length)proposalModels(current,edit.current_blocks||edit.before_blocks,
      edit.edit_id+'-owner-current');else if(typeof (edit.current_before??edit.before)==='string')current.append(asChrome(el('p','proposal-label',
      'Exact owner-returned current LaTeX source')),el('pre','proposal-exact-source',edit.current_before??edit.before));}const comparisonReady=proposalComparisonAvailable(edit);
    const revisionPlan=paintRevisionDifference(comparisonBlocks,proposedBlocks,'proposalDeletion','proposalAddition');for(const [blockIndex,
      block]of covered.entries())if(revisionPlan.before[blockIndex]?.length)block.el.classList.add('proposal-before');
    const selector=asChrome(el('div','proposal-version-choice'));selector.setAttribute('aria-label','Version shown');let mode=ui.mode||'changes';
      const merge=el('div','proposal-merge');merge.hidden=true;
    const views=[];let paintView=next=>{mode=next;ui.mode=mode;current.hidden=!['current','changes'].includes(mode);proposed.hidden=!['proposed',
      'changes'].includes(mode);merge.hidden=mode!=='merge';for(const [button,value]of views)button.setAttribute('aria-pressed',String((
      mode==='merge'?'proposed':mode)===value));for(const block of covered){if(!current.hidden)delete block.proposalDisplayEl;
      else block.proposalDisplayEl=mode==='merge'?merge:proposed;}measure();};
    for(const [label,value]of [[unproven?'Original':edit.local_draft_overlap?'Saved source':'Current','current'],['Proposed','proposed'],['Changes',
      'changes']]){const button=el('button',null,label);button.type='button';button.onclick=()=>paintView(value);selector.append(button);views.push([button,value]);}
    versions.append(selector,current,proposed,merge);
    const controls=asChrome(el('aside','proposal-controls'));controls.append(el('strong',null,edit.file));
    const navigation=data.navigation_edits||pending;if(navigation.length>1){const choice=el('select','proposal-edit-choice');choice.setAttribute(
      'aria-label','Review edit');for(const row of navigation){const item=el('option',null,'Edit '+(navigation.indexOf(row)+1)+' · '+row.file+(
      row.lifecycle==='blocked'?' · needs reconciliation':''));item.value=row.edit_id;choice.append(item);}choice.value=edit.edit_id;
      choice.onchange=async()=>{const selected=choice.value;if(options.onSelectEdit){choice.disabled=true;try{const next=await options.onSelectEdit(
      selected);if(proposalView?.data!==data)return;showProposal(next,{...options,selectedEditId:selected});}catch(error){choice.disabled=false;emit(
      'editor-status',{text:error.message,error:true});}}else showProposal(data,{...options,selectedEditId:selected});};controls.append(choice);
      }controls.append(el('p','proposal-unit',edit.acceptance_unit?.kind==='edit'?(humanAvailable?'Saved edit ':'Selected whole edit ')+(
      navigation.findIndex(row=>row.edit_id===edit.edit_id)+1)+' of '+navigation.length+' loaded edits':'Inspection only'));if(
      edit.basis_currentness&&edit.basis_currentness!=='CURRENT'){controls.append(el('p','proposal-location-warning',
      humanAvailable?'The passage or its supporting inputs changed since this suggestion. The comparison below uses the current passage; approving decides the text only.':'Inputs changed; reconcile this edit.'));if(edit.basis_reason&&
      !humanAvailable)controls.append(el('p','proposal-location-warning',edit.basis_reason));}else if(edit.review_obligations?.length)controls.append(el('p',
      'proposal-scope-note','This edit can be applied: it changes only the source it names. Something it consulted (such as a built PDF) changed since; '+
      'review that after applying. Applying is not acceptance of every claim it touches.'));const metadata=el('details','proposal-details');
      metadata.append(el('summary',null,'Context and provenance'));if(humanAvailable&&edit.basis_reason)metadata.append(el('p',
      'proposal-location-warning',edit.basis_reason));metadata.append(el('p',null,'Saved candidate '+edit.edit_id+' · version '+reviewedVersion));if(
      options.onInspectOrigin){const origin=el('button','proposal-refresh','Read originating turn');origin.type='button';origin.onclick=()=>
      options.onInspectOrigin(data.turn_id);metadata.append(origin);}controls.append(metadata);controls.append(selector);if(edit.local_draft_overlap){
      controls.append(el('p','proposal-location-warning',
      'Your unsaved manuscript text overlaps this whole edit. Save your manuscript edits, then reconcile the suggestion; or request a fresh change. Your text remains editable below.'));
      const save=el('button','proposal-save-standing','Save manuscript edits');save.type='button';save.onclick=async()=>{save.disabled=true;
      status.textContent='Saving manuscript edits…';try{const batch=await window.walk.commitAll();status.textContent=batch?.message||
      'Manuscript save checked.';options.onManuscriptSaved?.(batch);const next=await options.onRefresh?.();if(next)showProposal(next,{...options,
      focus:false,sourceSaveMessage:batch?.message});emit('editor-status',{text:(batch?.message||
      'Manuscript save checked.')+' Review the fresh comparison before any acceptance.',error:!!(batch?.refused?.length||batch?.remaining?.length)});
      }catch(error){status.textContent=error.message;status.classList.add('error');save.disabled=false;}};controls.append(save);}
    if(unproven){controls.append(el('p','proposal-location-warning',
      humanAvailable?'This saved edit’s original location no longer matches the manuscript. The current passage is compared below; you choose a passage only if it cannot be found unambiguously.':
      'The current passage cannot be located safely. Inspect the file and request a fresh change. Rereading this saved comparison will not make its old location valid.'));}
    else if(conflict){controls.append(el('p',null,edit.review_token?'Compare the current passage and proposal, then choose what to keep.':edit.error||
      'This suggestion belongs to a different source version.'));if(edit.current_mapping==='previous-source-location')controls.append(el('p',
      'proposal-location-warning','This candidate uses the former line location. Check that it is the intended passage.'));}
    if(edit.reason){const reason=el('details','proposal-reason');reason.append(el('summary',null,'Why this change'),el('p',null,edit.reason));metadata.append(reason);}
    const basis=edit.basis;if(basis){const section=el('details','proposal-basis'),hasScientificLinks=!!(basis.develops?.length||
      basis.evidence?.length||basis.errors?.length);section.append(el('summary',null,hasScientificLinks?'Scientific basis':'Change context'));
      if(basis.status==='UNATTRIBUTED_LEGACY')section.append(el('p','proposal-basis-note',
        'No explicit scientific links are attached to this suggestion.'));if(basis.errors?.length){const errors=el('div','proposal-basis-errors');
        errors.append(el('strong',null,'Evidence needs review'));for(const error of basis.errors)errors.append(el('p',null,error));controls.append(errors);}
      const show=(heading,items,kind)=>{if(!items?.length)return;section.append(el('strong',null,heading));for(const item of items){const button=el(
        'button','proposal-basis-link',options.displayLabel?options.displayLabel(item):String(item.label||item.id).length<90?item.label||
        item.id:String(item.id||'').replace(/^[^:]+:/,'').replaceAll('-',' '));button.type='button';button.onclick=()=>options.onInspectBasis?.(kind,
        item,edit);section.append(button);if(item.currentness)section.append(el('small',null,String(item.currentness).replaceAll('_',' ').toLowerCase(
        )));if(item.reason)section.append(el('p',null,item.reason));}};
      show('Develops these concepts',basis.develops,'concept');show('Evidence explicitly linked',basis.evidence,'evidence');show('Section context',
        basis.automatic_section_concepts,'concept');if(basis.automatic_section_concepts?.length)section.append(el('p',null,
        'Section context identifies relevant concepts; it does not verify each sentence.'));
      for(const note of basis.limitations||[])section.append(el('p',null,note));metadata.append(section);
    }
    if(edit.pending_successors?.length||edit.disposition_status==='PENDING')pendingSuccessorLinks(controls,edit,options);
    const status=el('p','proposal-decision-status');status.setAttribute('role','status');if(options.decisionError){
      status.textContent=options.decisionError;status.classList.add('error');}else if(
      options.sourceSaveMessage)status.textContent=options.sourceSaveMessage;const buttons=el('div','proposal-decision-actions');
    const draftKey=stateKey,legacyDraftKey='laplace:proposal-draft:'+S.corpus+':'+data.turn_id+':'+edit.edit_id;let heldDraft=null,legacyDraft=null,heldBasis=null;
    try{heldDraft=localStorage.getItem(draftKey);legacyDraft=localStorage.getItem(legacyDraftKey);const rawBasis=localStorage.getItem(
      draftKey+':basis');if(rawBasis)heldBasis=JSON.parse(rawBasis);}catch{
      status.textContent='Local draft storage is unavailable. The open draft stays in memory; keep this review open.';}
    if(!Object.hasOwn(ui,'draftBasis'))ui.draftBasis=ui.draftText!=null||heldDraft!=null?heldBasis:proposalDraftBasis(edit,reviewedVersion);
    let deciding=false;const decide=async(decision,extra={})=>{if(['accept','replace-current','merge'].includes(decision)&&!comparisonReady){
      status.textContent='The exact comparison is unavailable; applying this edit is disabled.';status.classList.add('error');return;}if(
      !proposalActionAllowed(edit,decision)){
      status.textContent='This action is unavailable for the current source and basis. Inspect or request a fresh change.';status.classList.add(
      'error');return;}if(typeof options.onDecision!=='function'){status.textContent='This reader has no decision transport; the draft is retained.';
      return;}if(deciding)return;deciding=true;if(saveCombined)saveCombined.disabled=true;buttons.querySelectorAll('button').forEach(button=>
      button.disabled=true);status.textContent=['reject','keep-current'].includes(decision)?'Keeping the current source…':'Saving…';
      const submittedDraft=ui.draftText,submittedBasis=ui.draftBasis;try{const acknowledged=await options.onDecision(edit.edit_id,decision,{...extra,
      ...(reviewedVersion?{proposal_version:reviewedVersion}:{})});if(['accept','replace-current','merge'].includes(decision)){if(
      proposalDecisionAcknowledged(acknowledged,{project:S.corpus,turnId:data.turn_id,version:reviewedVersion,editId:edit.edit_id})){if(
      ui.draftText!==submittedDraft||ui.draftBasis!==submittedBasis){emit('editor-status',{
      text:'The submitted version was recorded. Your newer proposed draft and its original guard are retained.'});}else{delete ui.draftText;
      delete ui.draftBasis;try{localStorage.removeItem(draftKey);localStorage.removeItem(draftKey+':basis');localStorage.removeItem(legacyDraftKey);
      for(const node of docEl.querySelectorAll('[data-retained-proposal-draft]'))if(node.dataset.retainedProposalDraft===draftKey)node.remove();
      }catch{emit('editor-status',{text:'The exact application was recorded. Local draft cache cleanup failed; the retained cache is historical.'});
      }emit('edit-settled',{proposal:{turn_id:data.turn_id,proposal_version:reviewedVersion,edit_id:edit.edit_id},
      application_id:acknowledged.application.id});}}else {const sourceEffect=sourceEffectDisposition(acknowledged,{project:S.corpus});
      const sameOwner=acknowledged?.project===S.corpus&&acknowledged?.turn_id===data.turn_id&&acknowledged?.proposal_version===reviewedVersion;if(
      sourceEffect&&!sourceEffect.acknowledged)data.reviewable=false;const tracking=sameOwner&&(
      acknowledged?.application_tracking?.status==='UNPROVED'||acknowledged?.application?.application_tracking?.status==='UNPROVED');if(tracking||
      sameOwner&&(acknowledged.preview_unavailable===true||acknowledged.application_maintenance_unproved===true))data.reviewable=false;emit(
      'editor-status',{text:sourceEffect?.message||(sameOwner&&(acknowledged.warning||acknowledged.application?.warning))||
      'No exact application acknowledgement was returned for this draft. Its text and original guard are retained; reinspect the owner record before another action.',
      error:true});}}}catch(error){status.textContent=error.message;status.classList.add('error');buttons.querySelectorAll('button').forEach(button=>
      button.disabled=false);updatePermission();}finally{deciding=false;updatePermission();}};
    let confirmation=null;if(conflict&&edit.review_token&&edit.current_mapping==='previous-source-location'){const label=el('label',
      'proposal-confirm-current');confirmation=el('input');confirmation.type='checkbox';label.append(confirmation,document.createTextNode(
      'This is the current passage I intend to replace.'));controls.append(label);}
    let replace=null,saveCombined=null;let updatePermission=()=>{const reviewable=typeof options.onDecision==='function'&&data.reviewable!==false&&(
      !data.turn_active||!!reviewedVersion);if(!reviewable)buttons.querySelectorAll('button').forEach(button=>button.disabled=true);if(
      !comparisonReady)buttons.querySelectorAll('[data-proposal-decision]').forEach(button=>{if(['accept','replace-current','merge'].includes(
      button.dataset.proposalDecision))button.disabled=true;});const allowed=reviewable&&!deciding&&comparisonReady&&proposalResolutionAvailable(
      edit)&&(!confirmation||confirmation.checked);if(replace)replace.disabled=!allowed||!proposalActionAllowed(edit,'replace-current');if(
      saveCombined)saveCombined.disabled=!allowed||!proposalActionAllowed(edit,'merge');};if(confirmation)confirmation.onchange=updatePermission;
    if(!conflict&&!unproven){for(const [label,decision]of [['Approve change','accept'],['Keep current','reject']].filter(([,action])=>
      proposalActionAllowed(edit,action))){const button=el('button',decision==='accept'?'primary':'',label);button.type='button';
      button.dataset.proposalDecision=decision;button.onclick=()=>decide(decision);buttons.append(button);}}
    else{
      if(proposalActionAllowed(edit,'keep-current')){const keep=el('button',null,'Keep current');keep.type='button';keep.onclick=()=>decide('keep-current');buttons.append(keep);}
      if(proposalActionAllowed(edit,'replace-current')&&proposalResolutionAvailable(edit)){replace=el('button','primary','Replace current passage');
        replace.type='button';replace.dataset.proposalDecision='replace-current';replace.onclick=()=>decide('replace-current',{
        review_token:edit.review_token});buttons.append(replace);}
    }
    // One proposed-text editor occupies this same review surface. Its draft never
    // replaces the immutable saved proposal or a standing manuscript edit.
    if(proposalActionAllowed(edit,'merge')&&proposalResolutionAvailable(edit)){
      const editor=el('textarea','proposal-merge-editor');editor.setAttribute('aria-label','Proposed LaTeX source');editor.spellcheck=false;
        editor.value=ui.draftText??heldDraft??edit.after??'';editor.proposalOriginal=edit.after??'';
      const draftChanged=()=>editor.value!==edit.after;
      const guardCurrent=()=>proposalDraftBasisMatches(ui.draftBasis,edit,reviewedVersion);
      const guardNote=el('p','proposal-location-warning'),adoptGuard=el('button','proposal-refresh','Use this inspected source basis for my draft');adoptGuard.type='button';
      const storeDraft=()=>{ui.draftText=editor.value;try{localStorage.setItem(draftKey,editor.value);localStorage.setItem(draftKey+':basis',
        JSON.stringify(ui.draftBasis));delete editor.dataset.unstored;}catch{editor.dataset.unstored='true';
        status.textContent='Local storage is unavailable. The proposed draft and original guard remain in memory; keep this review open.';}};
      adoptGuard.onclick=()=>{if(!comparisonReady||!proposalResolutionAvailable(edit)){
        status.textContent='An exact inspected current comparison is required before adopting its guard.';return;}ui.draftBasis=proposalDraftBasis(
        edit,reviewedVersion);storeDraft();updatePermission();
        status.textContent='Draft retained against the source comparison you inspected. Apply explicitly to change the manuscript.';};
      merge.append(guardNote,adoptGuard);
      const rememberCaret=()=>{ui.caretStart=editor.selectionStart;ui.caretEnd=editor.selectionEnd;ui.editorScroll=editor.scrollTop;};
        editor.onselect=rememberCaret;editor.onkeyup=rememberCaret;editor.onblur=rememberCaret;editor.onscroll=rememberCaret;
      const sourceChanges=el('div','proposal-source-changes');sourceChanges.hidden=true;versions.append(sourceChanges);
      const paintSourceChanges=()=>{sourceChanges.replaceChildren();const diff=proposalSourceChanges(edit.current_before??edit.before,editor.value);
        for(const [label,rows,spans,kind]of [['Current source',diff.current,diff.plan.before,'removed'],['Proposed draft source',diff.proposed,diff.plan.after,'added']]){
          const column=el('div');column.append(el('p','proposal-label',label));for(const [index,row]of rows.entries()){const text=el('pre',
            'proposal-source-row');let at=0;for(const span of spans[index]||[]){text.append(document.createTextNode(row.text.slice(at,span.start)));
            text.append(el('mark','proposal-source-'+kind,row.text.slice(span.start,span.end)));at=span.end;}text.append(document.createTextNode(
            row.text.slice(at)));column.append(text);}sourceChanges.append(column);
        }};
      const basePaint=paintView;paintView=next=>{basePaint(next);sourceChanges.hidden=true;if(next==='changes'&&draftChanged()){paintSourceChanges();
        current.hidden=true;proposed.hidden=true;sourceChanges.hidden=false;}};
      editor.oninput=()=>{storeDraft();ui.editing=true;updatePermission();};
      merge.append(asChrome(el('p','proposal-label','Edit proposed LaTeX · applies as one whole edit')),editor);
      saveCombined=el('button','primary','Apply edited text');saveCombined.type='button';saveCombined.dataset.proposalDecision='merge';
        saveCombined.onclick=()=>{if(!guardCurrent()){
        status.textContent='The draft retains an older or unknown source guard. Inspect the current comparison before explicitly adopting it.';return;
        }return decide('merge',{review_token:ui.draftBasis.review_token,merged_after:editor.value});};buttons.prepend(saveCombined);
      const accepts=[...buttons.querySelectorAll('button')].filter(button=>button!==saveCombined&&['Approve change','Replace current passage'].includes(button.textContent));
      const permission=updatePermission;updatePermission=()=>{permission();const changed=draftChanged(),same=guardCurrent();
        saveCombined.disabled=saveCombined.disabled||changed&&!same;guardNote.hidden=adoptGuard.hidden=!changed||same;
        guardNote.textContent=
        'The source comparison changed or this draft has no recorded source guard. Your text and original guard are retained. Inspect Current and Changes before explicitly adopting the shown basis.';
        saveCombined.hidden=!changed;for(const button of accepts)button.hidden=draftChanged();};
      editor.onkeydown=event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s'){event.preventDefault();event.stopPropagation();if(
        !saveCombined.disabled&&!saveCombined.hidden)saveCombined.click();}};
      const editProposed=el('button',null,'Edit suggestion');editProposed.type='button';editProposed.onclick=()=>{ui.editing=true;paintView(
        'merge');editor.focus({preventScroll:true});editor.setSelectionRange(ui.caretStart??0,ui.caretEnd??0);};buttons.append(editProposed);
      for(const [button,value]of views)button.onclick=()=>{paintView(value==='proposed'&&ui.editing?'merge':value);if(value==='proposed'&&ui.editing){
        editor.focus({preventScroll:true});editor.setSelectionRange(ui.caretStart??0,ui.caretEnd??0);editor.scrollTop=ui.editorScroll||0;}};
      const nav=el('div','proposal-change-navigation'),position=el('span');let changeIndex=-1;
      const changed=()=>draftChanged()?[...sourceChanges.querySelectorAll('mark')].map(node=>({node,mode:'changes'})):[...comparisonBlocks.filter((
        block,index)=>revisionPlan.before[index]?.length).map(block=>({node:block.el,mode:'current'})),...proposedBlocks.filter((block,index)=>
        revisionPlan.after[index]?.length).map(block=>({node:block.el,mode:'proposed'}))];
      const jump=step=>{paintView('changes');const targets=changed();if(!targets.length)return;changeIndex=changeIndex<0?(step<0?targets.length-1:0):(
        changeIndex+step+targets.length)%targets.length;const target=targets[changeIndex];target.node.scrollIntoView({block:'center'});
        position.textContent='Changed block '+(changeIndex+1)+' of '+targets.length;};
      for(const [label,step]of [['Previous change',-1],['Next change',1]]){const button=el('button',null,label);button.type='button';button.onclick=(
        )=>jump(step);nav.append(button);}position.textContent='Navigate changes · whole edit only';nav.append(position);controls.append(nav);
      if(ui.editing||heldDraft!=null){ui.editing=true;mode=ui.mode==='changes'?'changes':'merge';if(mode==='changes'&&draftChanged()){
        paintSourceChanges();current.hidden=true;proposed.hidden=true;sourceChanges.hidden=false;}}
      editor.setSelectionRange(ui.caretStart??0,ui.caretEnd??0);editor.scrollTop=ui.editorScroll||0;if(ui.editorFocused)queueMicrotask(()=>editor.focus({preventScroll:true}));
    }
    {
        const prior=el('details','proposal-prior');prior.append(el('summary',null,
          unproven?'Exact historical source':conflict?'What changed since the original':'Original proposal basis'));if(edit.current_diff)prior.append(
          el('pre',null,edit.current_diff));prior.append(el('p','proposal-label','Original basis · the exact saved source'),el('pre',null,
          edit.before||'[Empty passage]'));metadata.append(prior);
    }
    if(unproven||edit.local_draft_overlap||legacyDraft!=null||heldDraft!=null&&!proposalActionAllowed(edit,'merge')){const held=heldDraft??
      legacyDraft;if(held!=null){const saved=el('details','proposal-retained-draft');saved.append(el('summary',null,'Retained combined draft'));
      const text=el('textarea','proposal-merge-editor');text.readOnly=true;text.setAttribute('aria-label','Retained combined draft');text.value=held;
      saved.append(el('p',null,'This earlier local draft is retained for inspection. It does not replace the draft of this exact saved candidate.'),
      text);metadata.append(saved);}if(unproven&&options.onInspectCurrentFile){const inspect=el('button',null,'Inspect current source file');
      inspect.type='button';inspect.onclick=()=>options.onInspectCurrentFile(edit);buttons.append(inspect);}}
    if(humanAvailable){
      for(const nav of controls.querySelectorAll('.proposal-change-navigation')){const position=nav.querySelector('span');if(
        position)position.textContent='Navigate the comparison';}
      const host=el('section','proposal-human-resolution');host.hidden=true;versions.append(host);let controller=null;
      // M5 approval: the owner's exact current comparison is prepared automatically and IS the review surface; its
      // Approve change is the primary action. Keep current and Ask Eigen stay beside it; the passage picker appears
      // only when the owner says the target is ambiguous (target_required). The toggle only hides the comparison.
      const legacyButtons=[...buttons.querySelectorAll('button')],resolve=el('button',null,'Hide current comparison');resolve.type='button';buttons.append(resolve);
      const kept=button=>['Keep current','Ask Eigen for help'].includes(button.textContent);
      const hideLegacy=active=>{review.dataset.resolutionEditing=String(active);host.hidden=!active;selector.hidden=active;for(
        const nav of controls.querySelectorAll('.proposal-change-navigation'))nav.hidden=active;for(
        const button of legacyButtons)button.hidden=active&&!kept(button)||button===saveCombined;if(active){current.hidden=proposed.hidden=merge.hidden=true;for(
        const block of covered)block.proposalDisplayEl=host;}else paintView(ui.mode||'changes');};
      const mount=observed=>{
        if(controller){controller.destroy();proposalResolutionControllers.delete(controller);}host.replaceChildren();ui.resolutionValue=observed;
          ui.resolutionEditing=true;ui.resolutionClosed=false;hideLegacy(true);resolve.textContent='Hide current comparison';
        const alive=()=>proposalView?.data===data&&host.isConnected!==false;
        const prepare=async target=>{const next=await options.onPrepareResolution(edit,target);if(!alive())return null;validateResolutionPreparation(
          next,{project:S.corpus});if(ui.resolutionDraft)ui.resolutionDraft.needs_inspection=false;mount(next);return null;};
        if(observed.target_required)controller=mountResolutionTarget(host,{project:S.corpus,value:observed,request:options.onResolutionRequest,
          isCurrent:alive,onTarget:prepare,onCancel:()=>{ui.resolutionEditing=false;ui.resolutionClosed=true;hideLegacy(false);resolve.textContent='Show current comparison';}});
        else{
          ui.resolutionDraft??={};let storage=null;try{storage=window.sessionStorage;}catch{}
          controller=mountProposalResolution(host,{project:S.corpus,value:observed,state:ui.resolutionDraft,request:options.onResolutionRequest,isCurrent:alive,
            storage,storageKey:stateKey+':resolution',onRefresh:()=>prepare(),approve:true,
            renderPreview:(target,result)=>{if(result.after_blocks?.length)proposalModels(target,result.after_blocks,edit.edit_id+'-resolved');
              else target.append(el('pre','proposal-exact-source',result.resolved_after));},
            onReadCandidate:options.onReadCandidate,onFinishResolution:options.onFinishResolution,onApplied:options.onHumanApplied||(()=>{}),
              onChanged:state=>{ui.resolutionDraft=state;}});
        }
        proposalResolutionControllers.add(controller);
      };
      const prepareCurrent=async()=>{preparing=true;resolve.disabled=true;try{const observed=await options.onPrepareResolution(edit);if(proposalView?.data===data){
        validateResolutionPreparation(observed,{project:S.corpus});if(ui.resolutionDraft)ui.resolutionDraft.needs_inspection=false;mount(observed);}}catch(error){
        if(proposalView?.data===data){hideLegacy(false);resolve.textContent='Show current comparison';status.textContent=error.message;status.classList.add('error');}}finally{preparing=false;resolve.disabled=false;}};
      resolve.onclick=async()=>{if(ui.resolutionEditing){ui.resolutionEditing=false;ui.resolutionClosed=true;if(controller){controller.destroy();
        proposalResolutionControllers.delete(controller);}hideLegacy(false);resolve.textContent='Show current comparison';return;
        }await prepareCurrent();};
      let preparing=false;
      const legacyPermission=updatePermission;updatePermission=()=>{legacyPermission();resolve.disabled=deciding||preparing||edit.local_draft_overlap;if(
        ui.resolutionEditing||preparing)hideLegacy(true);else{if(saveCombined)saveCombined.hidden=true;for(const button of legacyButtons)if(
        button.textContent==='Edit suggestion')button.hidden=true;}};
      // prepared automatically (the first view and every refresh), unless the author hid it or unsaved text overlaps
      if(ui.resolutionClosed!==true&&!edit.local_draft_overlap){hideLegacy(true);host.append(el('p',null,ui.resolutionValue?
        'Refreshing the comparison with the current passage…':'Preparing an exact comparison with the current passage…'));void prepareCurrent();}
      else resolve.textContent='Show current comparison';
      if(ui.draftText!=null||heldDraft!=null){const retained=el('details','proposal-retained-draft');retained.append(el('summary',null,
        'Retained earlier custom draft'),el('pre','proposal-exact-source',ui.draftText??heldDraft));metadata.append(retained);}
    }
    const revise=el('button',null,humanAvailable?'Ask Eigen for help':unproven||edit.local_draft_overlap||
      edit.lifecycle==='blocked'?'Request fresh reconciliation':conflict?'Request a fresh placement':'Request changes');revise.type='button';
      revise.onclick=()=>options.onRequestChanges?.(edit);buttons.append(revise);
    const refresh=el('button','proposal-refresh',unproven?'Re-read saved comparison':conflict?'Refresh comparison':'Refresh suggestion');
      refresh.type='button';refresh.onclick=async()=>{try{const next=await options.onRefresh?.();if(next)showProposal(next,{...options,focus:false});
      }catch(error){status.textContent=error.message;}};controls.append(refresh);
    const close=el('button','proposal-refresh','Close review');close.type='button';close.onclick=()=>{const focus=captureFocus();
      ui.scrollWithin=paper.scrollTop-review.offsetTop;clearProposal();restoreFocus(focus);emit('editor-status',{
      text:'Review closed. Local proposed drafts are retained.'});};controls.append(buttons,status,close);review.append(controls,versions);
    const home=covered[0]?.proposalHome;if(home?.isConnected)home.before(review);else anchor.el.before(review);first??=review;
      firstBlockId??=anchor.id;paintView(mode);updatePermission();
  }
  syncRevisionHighlights(['proposalAddition','proposalDeletion']);measure();if(options.focus!==false&&first){noteAttention(firstBlockId);
    paper.scrollTop=Math.max(0,first.offsetTop+(proposalUiStates.get(first.dataset.proposalStateKey)?.scrollWithin??-16));emit('attention',{
    block:firstBlockId});}else{restoreFocus(focus);const state=first&&proposalUiStates.get(first.dataset.proposalStateKey);if(
    state?.viewport!=null)paper.scrollTop+=first.getBoundingClientRect().top-state.viewport;}
  const reviewStatus=proposalReviewStatus(data);emit('editor-status',{text:reviewStatus.text});return pending.length;
}

export {
  authorChangeRecords, authorChangesEnabled, clearProposal, manuscriptDraftRanges, proposalView,
  refreshAuthorChanges, refreshProposalView, setAuthorChanges, showProposal
};
