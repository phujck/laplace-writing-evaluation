// THE WRITING PANEL (legacy artefact editor's companion pane). Purpose: bind the walk's passage
// context (current block, selection, points) to the conversation, review and evidence panes of
// the project page. Ownership: the walk (walk.mjs) owns the text and the reading position;
// workspace-review.mjs and writing-evidence.mjs own their panes; passage provenance comes from
// writing-owner-read. Public contract: bindPassageContext(walk, handlers) and the panel mount.
// Inputs: walk messages and owner reads; outputs: DOM. Currentness: per passage read; nothing is
// cached across passages. Copy (plan §10): the typing hint lives inside Reading options only.
// Storage: none of its own.
import {passageProvenancePresentation,passageContinuationURL} from '/shared/writing-owner-read.mjs';
import {mountReview} from '/shared/workspace-review.mjs';
import { mountEvidence } from '/shared/writing-evidence.mjs';
import {groupedMenu,contextMenuPlacement,declareControl} from '/shared/workspace-presentation.mjs';
import {blockSourceLocation} from '/shared/manuscript-editing.mjs';
import {openFeedbackComment} from '/shared/feedback-route.mjs';
import {panelProposalReview} from '/shared/workspace-bridge.mjs';
import {pendingRead} from '/shared/pending-read.mjs';
// A live writing panel in the existing walk. Producers remain in Laplace.
//
// THE BRIDGE CONTRACT (M5 C2, plan §4; the full statement is the header of walk.mjs):
//   A  this module posts to the shell (same origin, embedded only): laplace:discuss-selection,
//      laplace:engine-unavailable, laplace:logical-context, laplace:open-document-pdf,
//      laplace:open-document-source ({file: the block's exact repository path, line, basis:
//      {selection_identity, source_digest}} from manuscript-editing blockSourceLocation),
//      laplace:queued-request, laplace:source-outcome, laplace:source-saved,
//      laplace:source-warning. walk.mjs posts laplace:open-owner-read,
//      laplace:open-project-artifact and laplace:place. The shell handles three more types
//      with no producer here (focus-manuscript, show-sections, read-origin-turn); counted,
//      not retired.
//   B  the shell posts nothing to this frame.   C  the shell drives window.walk directly.
//   D  this module subscribes to walk events attention, section, document, bank
//      (bindPassageContext); source-change-saved is emitted by walk.mjs and unsubscribed.
//   E  document events are the shell's.   F  the proposal draft key is shared verbatim.
//   G  bootEmbedded() runs when ?embedded=1; the frame URL is /walk?corpus=<project>&embedded=1.
const $ = (s, p=document) => p.querySelector(s);
const E = (tag, cls, text) => {const el=document.createElement(tag);if(cls)el.className=cls;if(text!=null)el.textContent=text;return el;};
let project='', state={}, sessionId='', sessionRole='author', activeTurn='', stream=null, selection=null, providers=[];
let providerLoaded=false, argumentDirty=false, argumentBaseRevision=null, currentTab='session', sessionLimit=30;
const q = new URLSearchParams(location.search);
const root=$('#walk');
if (root && q.get('embedded')==='1') bootEmbedded();
else if (root) boot();


// Only a change of passage triggers a context read. Typing/caret events in the
// same block keep the reader and the editor draft untouched.
export function bindPassageContext(walk,{current,select,clear}){
  const follow=()=>{const held=current();if(!held)return;const id=walk.readingPosition().blockId;if(id===held)return;const block=walk.blocks().find(row=>row.id===id);if(block)select(block);else clear();};
  walk.on('attention',follow);walk.on('section',follow);
  for(const name of ['document','bank'])walk.on(name,()=>{if(current())clear();});
}

function bootEmbedded(){
  const css=E('link');css.rel='stylesheet';css.href='/shared/writing-panel.css';document.head.append(css);
  root.classList.add('writing-enabled','writing-embedded');// Walk owns each source-qualified editable block; the wrapper is not an editing host.
  $('#doc').contentEditable='false';$('#doc').setAttribute('aria-label','Manuscript text');root.dataset.spine='collapsed';
  const contents=$('#spine-toggle');if(contents){contents.hidden=true;contents.textContent='Contents';contents.setAttribute('aria-label','Show or hide contents');contents.addEventListener('click',()=>localStorage.setItem('laplace:embedded:contents',root.dataset.spine));}
  const projectId=q.get('corpus');
  const sectionPicker=E('select');sectionPicker.id='manuscript-section-picker';sectionPicker.hidden=true;sectionPicker.setAttribute('aria-label','Go to manuscript section');$('#bar').prepend(sectionPicker);
  sectionPicker.onchange=()=>window.walk?.jumpToBlock(sectionPicker.value);
  const populateSections=()=>{const rows=window.walk.outline();const levels={part:0,chapter:1,section:2,subsection:3,subsubsection:4,paragraph:5,subparagraph:6};const first=Math.min(...rows.map(r=>levels[r.level]??2));sectionPicker.replaceChildren();for(const row of rows){const option=E('option','','  '.repeat(Math.max(0,(levels[row.level]??2)-first))+row.title);option.value=row.id;sectionPicker.append(option);}const current=window.walk.readingPosition();const row=rows.find(r=>r.section===current.sectionId);if(row)sectionPicker.value=row.id;};
  $('#spine-list').addEventListener('click',event=>{if(event.target.closest('button')&&innerWidth<1000){root.dataset.spine='collapsed';window.dispatchEvent(new Event('resize'));}});

  const editorStatus=E('span','','Click to write · select or right-click for passage actions');editorStatus.id='writing-editor-status';editorStatus.setAttribute('role','status');
  const storageStatus=E('span','error','');storageStatus.hidden=true;storageStatus.setAttribute('role','alert');const paintStorage=()=>{const errors=Object.values(window.walk?.editState()?.persistence||{}).filter(Boolean);storageStatus.textContent=errors.join(' ');storageStatus.hidden=!errors.length;};
  const save=E('button','primary','Save edits');save.id='writing-save-edits';save.onclick=async()=>{save.disabled=true;try{const batch=window.walk.flipState().open?(await window.walk.saveFlip(),null):await window.walk.commitAll();const held=window.walk.editState();editorStatus.textContent=batch?.message||(held.dirty||held.parked?($('.ec-status')?.textContent||'Some changes still need attention; inspect the highlighted passage.'):'Saved');}catch(error){editorStatus.textContent=error.message;}finally{save.disabled=false;}};
  $('#bar').append(save,editorStatus,storageStatus);
  let contextFocus=null,contextSelection=null,contextGeneration=0,contextBlockId=null;
  const contextPane=E('aside','manuscript-context');contextPane.hidden=true;contextPane.contentEditable='false';contextPane.setAttribute('aria-label','Manuscript questions and context');document.body.append(contextPane);
  const send=(type,extra={})=>window.parent.postMessage({type,...extra},location.origin);
  const contextAction=(label,fn,id=null)=>{const b=E('button','',label);if(id)declareControl(b,id);b.type='button';b.onclick=fn;return b;};
  const invalidateContext=()=>{contextPane.hidden=true;contextBlockId=null;contextGeneration++;};
  const closeContext=()=>{invalidateContext();const generation=contextGeneration;if(contextFocus)window.walk.restoreFocus(contextFocus);const held=contextSelection;requestAnimationFrame(()=>{if(generation===contextGeneration&&contextPane.hidden&&held?.element?.isConnected){held.element.focus({preventScroll:true});if(held.range){const selection=window.getSelection();selection.removeAllRanges();selection.addRange(held.range);}else if(held.start!=null)held.element.setSelectionRange(held.start,held.end);}});};
  async function openPoints(block=null){
    contextBlockId=block?.id||null;contextFocus=window.walk.captureFocus();const selection=window.getSelection(),active=document.activeElement,range=selection?.rangeCount&&$('#doc').contains(selection.anchorNode)?selection.getRangeAt(0).cloneRange():null;contextSelection={element:active,range,start:active?.selectionStart,end:active?.selectionEnd};const generation=++contextGeneration;
    contextPane.replaceChildren(E('h3','',block?'Questions & context here':'Open points'),contextAction('Close context',closeContext,'editor-frame:context-close'),pendingRead(E('p','','Reading recorded context…')));contextPane.hidden=false;
    try{
      const anchor=block?{file:block.file,line_start:block.line_start,line_end:block.line_end,quote:block.text}:null;
      const data=await request(block?'/concepts/plan/context?'+new URLSearchParams({project:projectId,...anchor}):'/concepts/plan?'+new URLSearchParams({project:projectId,limit:1}));
      if(generation!==contextGeneration)return;
      const passage=data.passage_context,points=passage?.obligations||data.obligations||[];
      contextPane.lastElementChild.remove();
      if(passage){contextPane.append(E('p','writing-muted',passage.precision==='PARAGRAPH_MARKER'?'These points target the exact inputs recorded for this marked paragraph.':passage.precision==='SECTION_ONLY'?'These points target concepts placed in this section. Paragraph placement is not recorded.':'No canonical section is bound to this passage.'));
        for(const concept of (passage.precision==='PARAGRAPH_MARKER'?passage.paragraph_concepts:passage.basis.automatic_section_concepts)||[])contextPane.append(contextAction(concept.label||concept.id,()=>send('laplace:logical-object',{node:concept.id,anchor})));
      }
      const relevant=points.filter(point=>point.state==='open'||point.currentness?.status==='STALE'||point.currentness?.status==='UNPINNED_LEGACY'||point.currentness?.status==='UNKNOWN');
      for(const point of relevant){const card=E('section','writing-card');card.dataset.obligationId=point.id;card.append(E('strong','',point.marker+' · '+(point.meaning||point.id)),E('p','',point.state+(point.currentness?.status==='OPEN'?'':' · '+String(point.currentness?.status||'unknown').toLowerCase().replaceAll('_',' '))),E('p','',point.discharge_condition));
        if(point.currentness?.status!=='OPEN')card.append(E('p','',point.currentness?.reason));
        const detail=E('details');detail.append(E('summary','','Recorded context'),E('p','',point.disposition||'No disposition recorded.'),E('p','writing-muted','Addressed does not establish verification.'));
        if(point.decision_permission)detail.append(E('p','writing-muted','Human author consent is not established by the recorded audit origin.'));for(const evidence of point.live_basis?.evidence||[]){const name=evidence.id||(typeof evidence.reference==='string'?evidence.reference:evidence.reference?.file)||'Unresolved evidence reference';detail.append(E('p','',name+' · '+String(evidence.currentness).toLowerCase()));if(evidence.owner)detail.append(contextAction('Read evidence',()=>send(evidence.owner==='concept'?'laplace:logical-object':'laplace:research-result',evidence.owner==='concept'?{node:evidence.id,anchor}:{id:evidence.id})));}
        for(const work of point.work||[])detail.append(contextAction('Work: '+(work.title||work.id),()=>send('laplace:obligation-work',{id:work.id})));
        detail.append(E('p','writing-muted',point.origin?.reason||'Historical origin is unknown.'));card.append(contextAction('Read question',()=>send('laplace:logical-object',{node:point.id,anchor})),detail);contextPane.append(card);
      }
      if(!relevant.length)contextPane.append(E('p','','No open or stale points in this context.'));
      const recorded = passageProvenancePresentation(passage, projectId),recordedHost=E('section','writing-recorded-context');
      const seenRecords=new Set();
      function appendRecorded(page){
        const presentation=passageProvenancePresentation(page,projectId);
        if(presentation.message&&!recordedHost.querySelector('[data-coverage]')){const note=E('p','writing-muted',presentation.message);note.dataset.coverage='';recordedHost.append(note);}
        for(const item of presentation.links){if(seenRecords.has(item.read.id))continue;seenRecords.add(item.read.id);recordedHost.append(contextAction(item.label,()=>send('laplace:open-owner-read',{url:item.read.http.url,label:item.label})),E('p','writing-muted',item.state));}
        if(presentation.continuation){
          const more=contextAction('More recorded changes',async()=>{more.disabled=true;try{
            const next=await request(passageContinuationURL(presentation.continuation,projectId,passage.anchor));
            if(generation!==contextGeneration)return;
            if(next.project!==projectId||!next.passage_context||['file','line_start','line_end'].some(key=>next.passage_context.anchor?.[key]!==passage.anchor?.[key]))throw Error('The context page belongs to a different passage.');
            more.remove();appendRecorded(next.passage_context);
          }catch(error){if(generation===contextGeneration){recordedHost.append(E('p','error',error.message));more.disabled=false;}}});recordedHost.append(more);
        }
      }
      appendRecorded(passage);if(recordedHost.childNodes.length)contextPane.append(recordedHost);

      if(passage?.document_provenance?.length){const origins=E('details');origins.append(E('summary','','Document origins'));for(const row of passage.document_provenance){if(row.diagnostics?.length)origins.append(E('p','writing-muted',row.diagnostics.join(' ')));origins.append(E('p','',row.status==='UNKNOWN'?(recorded.uncertain?'Paragraph origin is not established; retained candidates remain inspectable above.':'No paragraph origin is recorded in this section’s provenance sidecar.'):row.precision==='PARAGRAPH_MARKER'?'Exact paragraph markers join this passage to its recorded inputs and decisions.':`${row.paragraphs?.length||0} paragraph provenance records and ${row.decisions?.length||0} generation decisions belong to this section; this passage has no exact paragraph join.`));for(const paragraph of row.paragraphs||[]){origins.append(E('p','writing-muted','Recorded paragraph '+(paragraph.spec_ids||[paragraph.spec_id]).filter(Boolean).join(', ')));for(const node of paragraph.nodes_realised||[])origins.append(contextAction('Read input '+node,()=>send('laplace:logical-object',{node,anchor})));}}contextPane.append(origins);}
    }catch(error){if(generation===contextGeneration)contextPane.append(E('p','error',error.message));}
  }
  const points=declareControl(E('button','','Open points'),'editor-frame:open-points');points.onmousedown=event=>event.preventDefault();points.onclick=()=>openPoints();$('#bar').insertBefore(points,editorStatus);
  const here=declareControl(E('button','','Questions & context'),'editor-frame:questions');here.onmousedown=event=>event.preventDefault();here.onclick=()=>{const position=window.walk.readingPosition(),block=window.walk.blocks().find(row=>row.id===position.blockId);if(block)openPoints(block);};$('#bar').insertBefore(here,editorStatus);
  const find=declareControl(E('button','','Find'),'editor-frame:find');find.onclick=()=>window.walk.openFind();$('#bar').insertBefore(find,editorStatus);
  const width=declareControl(E('select'),'editor-frame:width');width.setAttribute('aria-label','Manuscript width');
  for(const [value,label]of [['fill','Fill pane'],['wide','Wide text'],['reading','Reading width']]){const option=E('option','',label);option.value=value;width.append(option);}
  width.value=localStorage.getItem('laplace:manuscript-width')||'fill';root.dataset.manuscriptWidth=width.value;
  width.onchange=()=>{root.dataset.manuscriptWidth=width.value;localStorage.setItem('laplace:manuscript-width',width.value);window.dispatchEvent(new Event('resize'));};$('#bar').insertBefore(width,editorStatus);
  const changes=declareControl(E('button','','Your changes'),'editor-frame:author-changes');changes.setAttribute('aria-pressed',String(localStorage.getItem('laplace:author-changes')!=='off'));changes.onclick=()=>{const enabled=changes.getAttribute('aria-pressed')!=='true';changes.setAttribute('aria-pressed',String(enabled));window.walk.setAuthorChanges(enabled);};$('#bar').insertBefore(changes,editorStatus);
  const autosave=declareControl(E('button','','Autosave'),'editor-frame:autosave');let autosaveOn=false;try{autosaveOn=localStorage.getItem('laplace:editor-autosave')==='on';}catch(_e){}autosave.setAttribute('aria-pressed',String(autosaveOn));autosave.onclick=()=>{const enabled=autosave.getAttribute('aria-pressed')!=='true';try{localStorage.setItem('laplace:editor-autosave',enabled?'on':'off');}catch(_e){}autosave.setAttribute('aria-pressed',String(enabled));editorStatus.textContent=enabled?'Autosave on · the paragraph you are typing in is saved a moment after you stop':'Autosave off · Ctrl-S or Save changes saves your edits';};$('#bar').insertBefore(autosave,editorStatus);
  if($('#geo-door')){$('#geo-door').textContent='PDF';$('#geo-door').setAttribute('aria-label','Open compiled PDF');$('#geo-door').addEventListener('click',event=>{event.preventDefault();event.stopImmediatePropagation();const source=window.walk?.source();if(source?.pdf)window.parent.postMessage({type:'laplace:open-document-pdf',file:source.pdf},location.origin);},true);}
  $('#paper').addEventListener('input',event=>{send('laplace:editor-state');if(event.target.closest('.proposal-merge')&&event.target.matches('[data-unstored]'))return;const held=window.walk?.editState();editorStatus.classList.remove('error');editorStatus.textContent=event.target.closest('.proposal-merge')?'Proposed draft saved locally':!held?'Editor state unavailable; reinspect before saving.':held.save?held.save.full||held.save.text:'No unsaved manuscript edits';});

  const build=E('button','','Build PDF');if(q.get('editor')==='workbench'){root.classList.add('writing-workbench');save.hidden=true;if($('#geo-door'))$('#geo-door').hidden=true;build.hidden=true;}build.onclick=async()=>{build.disabled=true;try{const held=window.walk?.editState();if(held&&(held.dirty||held.parked))throw Error('Save or discard your manuscript edits before building the PDF.');const result=await request('/authoring/build',{project:projectId});pendingRead(build,'Building…');const poll=async()=>{const state=await request('/authoring/build?project='+encodeURIComponent(projectId));if(state.running||state.state==='running'){setTimeout(poll,900);return;}build.disabled=false;build.textContent=state.ok?'PDF built':'Build failed';if(state.ok)await window.walk.refresh();else alert(state.error||state.note||'The PDF build failed; inspect the compile log.');};await poll();}catch(error){build.disabled=false;build.textContent='Build PDF';alert(error.message);}};$('#bar').insertBefore(build,editorStatus);
  if(q.get('editor')==='workbench'){const reading=E('details','writing-reading-options'),summary=declareControl(E('summary','','Reading options'),'editor-frame:reading-options'),options=E('div');reading.append(summary,options);options.append(points,width,changes,autosave);$('#bar').insertBefore(reading,editorStatus);}
  for(const id of ['back-door','ledger-door','keys'])if($('#'+id))$('#'+id).hidden=true;
  const bubble=E('div');bubble.id='writing-selection-actions';bubble.hidden=true;document.body.append(bubble);let selected=null,selectedPoint=null;
  function queueRequest(selection){
    if(!selection?.anchor)return;
    const dialog=E('dialog','manuscript-insert-dialog');dialog.append(E('h2','','Queue a request'),E('blockquote','',selection.quote||''));
    const message=E('textarea');message.setAttribute('aria-label','Request for the session');message.placeholder='Find supporting literature, develop an example, revise this passage…';message.rows=4;
    const add=declareControl(E('button','primary','Queue request'),'editor-frame:queue-submit'),cancel=declareControl(E('button','','Cancel'),'editor-frame:queue-cancel'),status=E('p');cancel.onclick=()=>dialog.close();
    add.onclick=async()=>{const goal=message.value.trim();if(!goal){message.focus();return;}add.disabled=true;try{await request('/work/task',{project:projectId,id:'REQUEST-'+crypto.randomUUID(),title:goal.slice(0,90),goal,kind:'session-request',section_ids:[],anchor:{file:selection.anchor.file,line_start:selection.anchor.line_start,line_end:selection.anchor.line_end,section:selection.anchor.section,quote:selection.quote?.slice(0,10000)}});dialog.close();editorStatus.textContent='Request queued for the session';window.parent.postMessage({type:'laplace:queued-request'},location.origin);}catch(error){status.textContent=error.message;add.disabled=false;}};
    dialog.append(message,add,cancel,status);dialog.onclose=()=>dialog.remove();document.body.append(dialog);dialog.showModal();message.focus();
  }
  function commentBasis(touched,quote,anchor,range=null){
    const dirty=window.walk.editState?.();if(dirty&&(dirty.dirty||dirty.parked))throw Error('Save or discard manuscript edits before anchoring a new comment.');
    if(new Set(touched.map(block=>block.repo_file||block.file)).size!==1)throw Error('Choose a passage in one source file for this comment.');
    const location=blockSourceLocation(window.walk,touched[0].id);
    const base={...anchor,line_start:Math.min(...touched.map(block=>block.line_start)),line_end:Math.max(...touched.map(block=>block.line_end))};
    // One paragraph: the reader's own source/piece map names the exact raw target; displayed text is only an observation.
    // A mapper refusal is not an absent mapping, and a selection across paragraphs is a typed refusal too: both carry
    // explicit qualified whole-paragraph choices and no target of their own, so nothing prepares the rendered quote
    // (review 276bdce0 F1). Only a reader without the mapper keeps the legacy quoted-text comment.
    const mapper=window.walk.commentSelection;
    const target=!mapper?null:touched.length===1?mapper(touched[0].id,range):{refused:'multi-source',reason:'This selection crosses paragraphs; a comment targets one paragraph. Choose the paragraph to comment on, or select text within one paragraph.',choices:[]};
    const lines=block=>'lines '+block.line_start+(block.line_end>block.line_start?'–'+block.line_end:'');
    const choices=touched.length===1?(target?.choices||[]).filter(choice=>choice.selection).map(choice=>({label:choice.label,anchor:{...base,source_selection:choice.selection}}))
      :!mapper?[]:touched.map((block,index)=>{const whole=mapper(block.id);return whole?.selection?{label:'Comment on the whole of paragraph '+(index+1)+' ('+lines(block)+')',
        anchor:{file:block.file,block:block.id,section:block.section,line_start:block.line_start,line_end:block.line_end,source_selection:whole.selection},
        expected:window.walk.identities(block.id),selection_identity:blockSourceLocation(window.walk,block.id).basis.selection_identity}:null;}).filter(Boolean);
    // A range in one paragraph that runs past its body (into the margin) is refused by the mapper without a choice; the
    // paragraph's own qualified whole-block target is offered explicitly, never applied (review 30e422e0 finding 3).
    const overhang=touched.length===1&&!!mapper&&!!target&&!target.selection&&target.refused==='multi-source';
    if(overhang&&!choices.length){const whole=mapper(touched[0].id);if(whole?.selection)choices.push({label:'Comment on the whole paragraph',anchor:{...base,source_selection:whole.selection}});}
    const refusal=overhang?{refused:'outside-paragraph',reason:'This selection runs past the paragraph it starts in. Comment on the whole paragraph, or select text within it.'}:target;
    return {anchor:target?.selection?{...base,source_selection:target.selection}:{...base,quote},expected:touched.flatMap(block=>window.walk.identities(block.id)),selection_identity:location.basis.selection_identity,source_sha256:location.basis.source_digest.slice(7),
      ...(target&&!target.selection?{mapping:{refused:refusal.refused,reason:refusal.reason,choices}}:{})};
  }
  // The selected-passage comment carries the explicit decision capability: Review responses decide through the fenced
  // bridge to the shell's canonical project Review controller (workspace-bridge panelProposalReview); it never inspects here.
  const commentFrom=comment=>{const {mapping=null,...prepare}=comment;return openFeedbackComment({project:projectId,selection:{anchor:structuredClone(prepare.anchor),prepare:structuredClone(prepare),...(mapping?{mapping:structuredClone(mapping)}:{})},request,onSaved:()=>{window.parent.postMessage({type:'laplace:source-saved'},location.origin);},
    openProposal:panelProposalReview({project:projectId,inspect:async()=>{throw Error('This comment route opens only an explicit decision; inspect a comparison from its own control.');}})});};
  for(const [label,mode,id]of [['Comment','comment','editor-frame:bubble-comment'],['Discuss','discuss','editor-frame:bubble-discuss'],['Revise','revise','editor-frame:bubble-revise']]){const button=declareControl(E('button','',label),id);button.onmousedown=event=>event.preventDefault();button.onclick=async()=>{bubble.hidden=true;if(!selected)return;if(mode==='comment'){if(selected.comment_error){editorStatus.textContent=selected.comment_error;return;}await commentFrom(selected.comment);}else window.parent.postMessage({type:'laplace:discuss-selection',mode,selection:selected},location.origin);};bubble.append(button);}
  for(const [label,action,id]of [['Reference',()=>window.walk.openReferencePicker('reference',{point:selectedPoint}),'editor-frame:bubble-reference'],['Citation',()=>window.walk.openReferencePicker('citation',{point:selectedPoint}),'editor-frame:bubble-citation'],['Queue request',()=>queueRequest(selected),'editor-frame:bubble-queue']]){const button=declareControl(E('button','',label),id);button.onmousedown=event=>event.preventDefault();button.onclick=()=>{bubble.hidden=true;action();};bubble.append(button);}
  $('#paper').addEventListener('mouseup',()=>{const pick=window.getSelection();if(!pick?.rangeCount||pick.isCollapsed){bubble.hidden=true;return;}const range=pick.getRangeAt(0),quote=pick.toString().trim();const blocks=window.walk?.blocks()||[];const touched=[...$('#paper').querySelectorAll('.blk[data-block]')].filter(e=>range.intersectsNode(e)).map(e=>blocks.find(b=>b.id===e.dataset.block)).filter(Boolean);if(!touched.length||!quote){bubble.hidden=true;return;}const ids=[...new Set(touched.map(b=>b.section))],scope=blocks.filter(b=>ids.includes(b.section)),files=[...new Set(scope.map(b=>b.file))],first=touched[0];selected={files,section_ids:ids,quote,line_start:files.length===1?Math.min(...scope.map(b=>b.line_start)):undefined,line_end:files.length===1?Math.max(...scope.map(b=>b.line_end)):undefined,anchor:{file:first.file,block:first.id,section:first.section,line_start:first.line_start,line_end:first.line_end}};try{selected.comment=commentBasis(touched,quote,selected.anchor,range.cloneRange());}catch(error){selected.comment_error=error.message;}selectedPoint=window.walk?.insertionPoint?.();const rect=range.getBoundingClientRect();bubble.style.left=Math.max(8,Math.min(innerWidth-bubble.offsetWidth-8,rect.left))+'px';bubble.style.top=Math.max(50,rect.top-40)+'px';bubble.hidden=false;bubble.style.left=Math.max(8,Math.min(innerWidth-bubble.offsetWidth-8,rect.left))+'px';});
  let contextMenu=null;
  const closeMenu=()=>{contextMenu?.remove();contextMenu=null;};
  document.addEventListener('pointerdown',event=>{if(!bubble.contains(event.target))bubble.hidden=true;if(contextMenu&&!contextMenu.contains(event.target))closeMenu();});
  document.addEventListener('keydown',event=>{if(event.key==='Escape'){closeMenu();bubble.hidden=true;}});
  // THE PASSAGE MENU ELIGIBILITY (M5 S2 L-MENU-ELIGIBILITY). The event's own block joins the current walk's model
  // row by its exact id over a text-free projection (never a basename, text or ordinal guess); only a single
  // matched row reads its own text, for the exact quote. A matched passage keeps its eligible actions; a passage
  // the current reading does not hold gets a bounded disposition (loading, or a draft-preserving reload of the
  // view); a background with no action keeps the browser's own menu instead of a blank popup. Each opening
  // overwrites one bounded transient diagnostic (data-passage-menu on the document element): the closest block
  // id, connection, ready, row and match counts, the opaque source revision, insertion availability, item count
  // and disposition. No text, model or history is recorded.
  document.addEventListener('contextmenu',event=>{
    if(event.target.closest('textarea,input'))return;
    bubble.hidden=true;closeMenu();
    const walk=window.walk,blockEl=event.target.closest?.('.blk[data-block]'),blockId=blockEl?.dataset.block||null;
    const blocks=walk?.blocks?.({text:false})||[],matches=blockId?blocks.filter(row=>row.id===blockId):[];
    const block=matches.length===1?{...matches[0],text:walk.blocks({id:blockId})[0]?.text??''}:null;
    const menu=E('div');menu.id='manuscript-context-menu';menu.setAttribute('role','menu');
    // THE MENU GROUPS (M5 C7, plan §4 passage context menu): Edit, Insert, Structure, Ask, each
    // under a group label; the nineteen conditional items keep their conditions. Undo and Redo
    // left the menu once the editor band carried them; they remain on Ctrl/⌘ Z and Shift-Z.
    const groups={edit:[],insert:[],structure:[],ask:[]};
    const groupOf=label=>/^(Edit |Open in TeX)/.test(label)?'edit':/^(Insert |Change |Italic|Bold|Paragraph style)/.test(label)?'insert':/^(Delete |Move )/.test(label)?'structure':'ask';
    const item=(label,action,id=null)=>{const button=E('button','',label);if(id)declareControl(button,id);button.setAttribute('role','menuitem');button.onmousedown=event=>event.preventDefault();button.onclick=()=>{closeMenu();action();};groups[groupOf(label)].push(button);};
    // H3: the heading is presentation; focus lands on the first enabled menuitem (groupedMenu)
    let askTitle='Ask';
    const flush=()=>groupedMenu(menu,[['Edit',groups.edit],['Insert',groups.insert],['Structure',groups.structure],[askTitle,groups.ask]],
      {heading:title=>{const head=E('div','manuscript-context-group',title);head.setAttribute('role','presentation');return head;}});
    const point=window.walk?.contextualInsertionPoint?.(event.target,event.clientX,event.clientY);
    if(point?.replace)item(point.type==='citation'?'Change citation…':'Change reference…',()=>window.walk.openReferencePicker(point.type,{point,replace:true}));
    if(point&&!point.replace){item('Insert reference…',()=>window.walk.openReferencePicker('reference',{point}),'editor-frame:menu-insert-reference');item('Insert citation…',()=>window.walk.openReferencePicker('citation',{point}),'editor-frame:menu-insert-citation');item('Italic',()=>window.walk.wrapSelection('emph'),'editor-frame:menu-italic');item('Bold',()=>window.walk.wrapSelection('textbf'),'editor-frame:menu-bold');}
    if(block)item('Insert heading…',()=>window.walk.insertHeading({point,blockId:block.id}),'editor-frame:menu-insert-heading');if(block?.kind==='para')item('Paragraph style…',()=>window.walk.insertHeading({point,blockId:block.id,convert:true}),'editor-frame:menu-paragraph-style');
    if(block){const selection=selected?.anchor?.block===block.id?selected:{files:[block.file],quote:block.text,anchor:{file:block.file,block:block.id,section:block.section,line_start:block.line_start,line_end:block.line_end}};item('Queue a request…',()=>queueRequest(selection),'editor-frame:menu-queue-request');if(block.kind==='para')item('Delete paragraph now',()=>window.walk.deleteBlock(block.id),'editor-frame:menu-delete-paragraph');const objectKind=window.walk.objectKind(block.id);if(objectKind){item('Delete '+objectKind,()=>window.walk.deleteObject(block.id));item('Move '+objectKind+'…',()=>window.walk.beginObjectMove(block.id));}}
    if(block){const caption=block.kind==='figure'?blocks.find(b=>b.caption_of===block.id):null;const target=caption||block;item(target.kind==='caption'?'Edit caption':'Edit this passage',()=>{if(!window.walk.editBlock(target.id,{exact:true}))window.walk.flip(target.id);},target.kind==='caption'?null:'editor-frame:menu-edit-passage');item('Edit exact source',()=>window.walk.flip(block.id),'editor-frame:menu-edit-source');if(q.get('editor')==='workbench')item('Open in TeX',()=>{let location=null;try{location=blockSourceLocation(window.walk,block.id);}catch(error){editorStatus.textContent=error.message;editorStatus.classList.add('error');return;}if(location)send('laplace:open-document-source',location);},'editor-frame:menu-open-tex');item('Questions & context',()=>openPoints(block),'editor-frame:menu-questions');item('Section concepts',()=>window.parent.postMessage({type:'laplace:logical-context',section_title:window.walk.sections().find(s=>s.id===block.section)?.title,anchor:{file:block.file,line_start:block.line_start,line_end:block.line_end,quote:block.text}},location.origin),'editor-frame:menu-section-concepts');item('Discuss this passage',()=>window.parent.postMessage({type:'laplace:discuss-selection',mode:'discuss',selection:{files:[block.file],section_ids:[block.section],quote:block.text,anchor:{file:block.file,block:block.id,section:block.section,line_start:block.line_start,line_end:block.line_end}}},location.origin),'editor-frame:menu-discuss');}

    if(block)item('Comment on this passage',()=>{try{const comment=selected?.anchor?.block===block.id&&selected.comment?selected.comment:commentBasis([block],block.text,{file:block.file,block:block.id,section:block.section,line_start:block.line_start,line_end:block.line_end});Promise.resolve(commentFrom(comment)).catch(error=>{editorStatus.textContent=error.message;editorStatus.classList.add('error');});}catch(error){editorStatus.textContent=error.message;editorStatus.classList.add('error');}},'editor-frame:menu-comment');
    const items=Object.values(groups).reduce((count,list)=>count+list.length,0),ready=!!walk?.ready?.();
    const diagnostic={block:blockId,connected:!!blockEl?.isConnected,ready,rows:blocks.length,matches:matches.length,
      revision:walk?.sourceObservation?.()?.current_revision??null,insertion:!!point,items,
      disposition:items?'actions':!blockEl?'browser-menu':ready?'unavailable':'loading'};
    document.documentElement.dataset.passageMenu=JSON.stringify(diagnostic);
    if(diagnostic.disposition==='browser-menu')return;
    event.preventDefault();
    if(!items){
      const reload=E('button','',ready?'Reload the manuscript view':'Close');reload.setAttribute('role','menuitem');
      reload.onmousedown=down=>down.preventDefault();
      reload.onclick=()=>{closeMenu();if(ready)walk.refresh?.();};
      groups.ask.push(reload);menu.dataset.disposition=diagnostic.disposition;
      askTitle=ready?'This passage is not in the current reading':'The manuscript is still loading';
    }
    const firstItem=flush();contextMenu=menu;document.body.append(menu);const frameView={w:document.documentElement?.clientWidth||innerWidth,h:document.documentElement?.clientHeight||innerHeight};menu.style.maxHeight=Math.max(0,frameView.h-16)+'px';const place=contextMenuPlacement({x:event.clientX,y:event.clientY},{w:menu.offsetWidth,h:menu.offsetHeight},frameView);menu.style.left=place.left+'px';menu.style.top=place.top+'px';firstItem?.focus();
  });
  // THE KEEP ACTION (wave 14a, his ruling 3; wave 14b): a save warning on this line offers, first, Keep my
  // text and save it: every paragraph he has typed in is saved through commitAll, and the rewrite door applies
  // his text over each span as it is now, or puts a paragraph of his the file no longer has back at its place
  // (review_surface.py _author_editor_write). Show the other version stands beside it when another writer
  // changed a paragraph under his draft: the walk shows what the file holds there (walk.showOtherVersion).
  const offerKeep=()=>{const state=window.walk?.editState?.();if(!state||!(state.dirty||state.parked)||editorStatus.querySelector('[data-control="editor-frame:keep-my-text"]'))return;
    const keep=declareControl(E('button','','Keep my text and save it'),'editor-frame:keep-my-text');keep.type='button';keep.onmousedown=event=>event.preventDefault();
    keep.onclick=async()=>{keep.disabled=true;try{const batch=await window.walk.commitAll();const refused=!!batch?.refused?.length;editorStatus.textContent=batch?.message||'Saved';editorStatus.classList.toggle('error',refused);if(refused)offerKeep();}catch(error){editorStatus.textContent=error.message;editorStatus.classList.add('error');offerKeep();}finally{keep.disabled=false;}};
    editorStatus.append(' ',keep);
    if(state.moved){const other=declareControl(E('button','','Show the other version'),'editor-frame:show-other-version');other.type='button';other.onmousedown=event=>event.preventDefault();other.onclick=()=>window.walk.showOtherVersion();editorStatus.append(' ',other);}};
  const ready=()=>{bindPassageContext(window.walk,{current:()=>contextPane.hidden?null:contextBlockId,select:openPoints,clear:invalidateContext});populateSections();window.walk.restoreEditHistory();window.walk.on('persistence-status',paintStorage);paintStorage();const recovered=window.walk.editState();send('laplace:editor-state');for(const name of ['save-outcome','save-settled','editor-status'])window.walk.on(name,()=>send('laplace:editor-state'));for(const name of ['save-outcome','save-settled'])window.walk.on(name,showSave);if(recovered.placing||recovered.unplaced){editorStatus.textContent='A recovered draft of yours is for a paragraph that is not in the file; your text is kept above the manuscript.';editorStatus.classList.add('error');offerKeep();}else if(recovered.moved){editorStatus.textContent='A recovered draft was typed against text that has changed since; your text is kept in its paragraph.';editorStatus.classList.add('error');offerKeep();}else if(recovered.parked)editorStatus.textContent='Recovered '+recovered.parked+' unsaved draft'+(recovered.parked===1?'':'s')+' · Ctrl-S saves your edits.';window.walk.on('editor-status',event=>{editorStatus.textContent=event.text;editorStatus.classList.toggle('error',!!event.error);if(event.error)offerKeep();if(event.retry){const retry=E('button','','Retry comparisons');retry.type='button';retry.onclick=async()=>{retry.disabled=true;try{await event.retry();}finally{retry.disabled=false;}};editorStatus.append(' ',retry);}});window.walk.on('edit-settled',()=>{send('laplace:editor-state');if(!window.walk.flipState().open){const state=window.walk.editState();editorStatus.classList.remove('error');editorStatus.textContent=state.save?state.save.full||state.save.text:'Click to write · select or right-click for passage actions';}});window.walk.on('source-outcome',event=>window.parent.postMessage({type:'laplace:source-outcome',source_effect:event.source_effect},location.origin));window.walk.on('source-warning',event=>window.parent.postMessage({type:'laplace:source-warning',text:event.text},location.origin));window.walk.on('document',()=>{populateSections();window.walk.refreshAuthorChanges();});window.walk.refreshAuthorChanges();window.walk.on('section',()=>{const row=window.walk.outline().find(r=>r.section===window.walk.current());if(row)sectionPicker.value=row.id;});if(!window.walk.actor())window.walk.nameActor('author');const note=$('#spine-note');if(note){note.textContent='Select a section to read it. Select text to comment or discuss it; click prose to edit.';}const heading=$('#spine-head');if(heading)heading.textContent='Contents';window.walk.setDocSize(Number(localStorage.getItem('laplace:walk:font-size')||17));window.walk.on('bank',event=>{if(event.applied===true||event.pending)showSave();window.parent.postMessage({type:'laplace:source-saved'},location.origin);});};
  // THE FRAME LINE REPEATS THE SAVE LINE (NODE.w3 ruling 4: one place speaks; the shell band's
  // chip row is that place): the same words, in the same style, so the two never disagree
  const showSave=()=>{const state=window.walk?.editState?.();if(!state||window.walk.flipState?.().open)return;editorStatus.classList.remove('error');
    editorStatus.textContent=state.save?state.save.full||state.save.text:'Click to write · select or right-click for passage actions';if(state.save&&/^(Not saved|Conflict)$/.test(state.save.word)){editorStatus.classList.add('error');offerKeep();}send('laplace:editor-state');};
  if(window.walk?.ready())ready();else{const wait=setInterval(()=>{if(window.walk){clearInterval(wait);window.walk.on('ready',ready);if(window.walk.ready())ready();}},50);setTimeout(()=>clearInterval(wait),20000);}
}

async function request(path, payload) {
  let response;try{response=await fetch(path,{method:payload?'POST':'GET',headers:payload?{'Content-Type':'application/json','X-Laplace-Writing':'1'}:{},body:payload?JSON.stringify(payload):undefined});}catch(error){if(q.get('embedded')==='1')window.parent.postMessage({type:'laplace:engine-unavailable'},location.origin);throw error;}
  const data=response.headers.get('content-type')?.includes('application/json')?await response.json():{content:await response.text()};
  if(!response.ok||data.error){
    // THE REFUSAL'S BODY, CARRIED (WRITING-CONSOLIDATION-W1). This helper lifted `error`
    // out of the body and threw the rest away, so a 409 whose `refused.needed` holds the
    // cure arrived here as a sentence. The status and the parsed body ride the Error, the
    // same way `store.fetchJSON` carries them for the canvas.
    const error=new Error(data.error||`Request failed (${response.status})`);
    error.status=response.status;error.result=data;error.refused=data.refused||null;throw error;
  }
  return data;
}
function status(text,error=false){const el=$('#writing-status');el.textContent=text;el.classList.toggle('error',error);}
function operation(fn){return async(e)=>{const button=e?.currentTarget;try{if(button?.tagName==='BUTTON')button.disabled=true;await fn(e);}catch(error){status(error.message,true);}finally{if(button?.tagName==='BUTTON'&&!button.dataset.done)button.disabled=false;}};}
function setOpen(open){localStorage.setItem('laplace:writing:open',String(open));if(open&&innerWidth<700)root.dataset.spine='collapsed';root.classList.toggle('writing-open',open);$('#writing-panel').hidden=!open;$('#writing-toggle').setAttribute('aria-expanded',String(open));window.dispatchEvent(new Event('resize'));}
function field(label,tag,id,value=''){const l=E('label','',label),x=E(tag);x.id=id;x.value=value;l.append(x);return l;}

function boot(){
  const css=E('link');css.rel='stylesheet';css.href='/shared/writing-panel.css';document.head.append(css);
  const toggle=E('button','','Write with Eigen');toggle.id='writing-toggle';toggle.setAttribute('aria-label','Write with Eigen');toggle.setAttribute('aria-controls','writing-panel');toggle.onclick=()=>setOpen(!root.classList.contains('writing-open'));$('#bar').append(toggle);const build=E('button','','Build PDF');build.id='writing-build-pdf';build.onclick=operation(buildPDF);$('#bar').insertBefore(build,toggle);
  const picker=E('select','writing-project');picker.id='writing-project';picker.setAttribute('aria-label','Project');$('#bar').prepend(picker);
  const libraryButton=E('button','','Projects');libraryButton.id='writing-library-open';libraryButton.onclick=operation(showLibrary);$('#bar').prepend(libraryButton);
  const projectDoor=E('a','','Project');projectDoor.id='writing-project-home';projectDoor.href='/project?corpus='+encodeURIComponent(q.get('corpus')||'');projectDoor.className='writing-project-link';$('#bar').prepend(projectDoor);
  picker.onchange=()=>{if((argumentDirty||correctionReview?.hasDraft||[...correctionDrafts.values()].some(row=>row.text))&&!confirm('Leave your unsaved argument changes?')){picker.value=project;return;}const url=new URL(location.href);url.searchParams.set('corpus',picker.value);location.href=url;};
  const panel=E('aside');panel.id='writing-panel';panel.setAttribute('aria-label','Research and writing workspace');
  panel.innerHTML=`<div class="writing-head"><strong>Research & writing</strong><button id="writing-close" aria-label="Close writing panel">×</button></div>
  <nav class="writing-tabs" role="tablist" aria-label="Writing tools"></nav>
  <div class="writing-view" data-view="session" role="tabpanel">
    <details class="writing-settings"><summary id="writing-model-summary">Session settings</summary><div class="writing-settings-row">
      <label>Provider<select id="writing-provider"><option value="codex">Codex</option><option value="claude">Claude</option></select></label>
      <label>Model<select id="writing-model"></select></label>
      <label>Effort<select id="writing-effort"><option>low</option><option selected>medium</option><option>high</option></select></label></div>
      <div class="writing-actions"><select id="writing-sessions" aria-label="Saved writing session"><option value="">New conversation</option></select><button id="writing-new">New</button><button id="writing-more-sessions" hidden>Older conversations</button><button id="writing-refresh-providers">Refresh providers</button></div>
    </details><div class="writing-thread" id="writing-thread" aria-live="polite"></div>
    <form class="writing-composer" id="writing-compose"><div class="writing-selection" id="writing-selection">Current section · context follows your reading position</div>
      <textarea id="writing-message" aria-label="Message to Eigen" placeholder="Work through the argument, ask about the evidence, or develop this passage…" rows="3"></textarea>
      <div class="writing-actions"><button type="button" id="writing-select">Use selection</button><button type="button" id="writing-edit">Edit passage</button><select id="writing-mode" aria-label="Writing action" style="width:auto;font-size:12px;padding:5px"><option value="discuss">Discuss</option><option value="revise">Propose revision</option><option value="work">Work on project</option><option value="review">Independent review</option></select>
      <button type="button" id="writing-stop" hidden>Stop</button><button class="primary push" type="submit" id="writing-send">Send</button></div>
      <div class="writing-muted" style="margin-top:6px">Ctrl / ⌘ Enter to send · revisions stay reviewable</div>
    </form></div>
  <div class="writing-view" data-view="argument" role="tabpanel" hidden></div>
  <div class="writing-view" data-view="sources" role="tabpanel" hidden></div>
  <div class="writing-view" data-view="evidence" role="tabpanel" hidden></div>
  <div class="writing-view" data-view="corrections" role="tabpanel" hidden></div>
  <div class="writing-status" id="writing-status" role="status">Opening your workspace…</div>`;
  root.append(panel);root.classList.add('writing-enabled');wireAnnotations();
  for(const [id,label] of [['session','Session'],['argument','Argument'],['sources','Sources'],['evidence','Evidence'],['corrections','Notes']]){
    const b=E('button','',label);b.setAttribute('role','tab');b.setAttribute('aria-selected',String(id==='session'));b.dataset.tab=id;b.onclick=()=>showTab(id);$('.writing-tabs').append(b);
  }
  $('#writing-more-sessions').onclick=operation(async()=>{sessionLimit+=30;await loadState();status('Older conversations added to the menu');});
  $('#writing-refresh-providers').onclick=operation(()=>loadProviders(true));
  $('#writing-close').onclick=()=>setOpen(false);
  $('#writing-compose').onsubmit=operation(sendMessage);
  $('#writing-message').onkeydown=e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();$('#writing-compose').requestSubmit();}};
  $('#writing-select').onclick=()=>captureSelection(true);
  $('#writing-edit').onclick=()=>{const pos=window.walk?.readingPosition();if(window.walk?.editBlock?.(pos?.blockId)){status('Edit directly in the manuscript. Ctrl / ⌘ S saves; Esc cancels.');if(innerWidth<700)setOpen(false);}else if(pos?.blockId){window.walk.flip(pos.blockId);status('Source editor opened for this block.');}};
  $('#writing-stop').onclick=operation(async()=>{await request('/authoring/interrupt',{turn_id:activeTurn});status('Stopping the current turn…');});
  $('#writing-new').onclick=()=>{localStorage.removeItem('laplace:session:'+project);sessionId='';$('#writing-sessions').value='';renderEmpty();status('New conversation. The project argument and corrections stay available.');};
  $('#writing-sessions').onchange=operation(async()=>{sessionId=$('#writing-sessions').value;localStorage.setItem('laplace:session:'+project,sessionId);if(sessionId)await readSession();else renderEmpty();});
  $('.writing-settings').ontoggle=()=>{if($('.writing-settings').open&&!providerLoaded)loadProviders();};
  $('#writing-provider').onchange=()=>{sessionId='';localStorage.removeItem('laplace:session:'+project);$('#writing-sessions').value='';populateModels();renderEmpty();};
  $('#writing-model').onchange=()=>{sessionId='';$('#writing-sessions').value='';const model=providers.find(p=>p.id===$('#writing-provider').value)?.models.find(m=>m.id===$('#writing-model').value);if(model?.efforts?.length){const previous=$('#writing-effort').value;$('#writing-effort').replaceChildren(...model.efforts.map(x=>E('option','',x)));$('#writing-effort').value=model.efforts.includes(previous)?previous:model.efforts[0];}modelSummary();};
  $('#writing-mode').onchange=()=>{if($('#writing-mode').value==='review'||sessionRole==='review'){sessionId='';localStorage.removeItem('laplace:session:'+project);$('#writing-sessions').value='';renderEmpty();status('Independent review starts a fresh conversation; findings can be saved, reviewed artifacts stay unchanged.');}};
  $('#writing-effort').onchange=()=>{sessionId='';$('#writing-sessions').value='';modelSummary();};
  window.addEventListener('beforeunload',e=>{if(argumentDirty||correctionReview?.hasDraft||[...correctionDrafts.values()].some(row=>row.text)){e.preventDefault();e.returnValue='';}});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&root.classList.contains('writing-open')&&!['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName)){setOpen(false);$('#writing-toggle').focus();}});
  setOpen(localStorage.getItem('laplace:writing:open')!=='false');
  // Existing reader is kept; shorten implementation vocabulary in its controls.
  if($('#spine-toggle')){$('#spine-toggle').textContent='Contents';$('#spine-toggle').setAttribute('aria-label','Show or hide contents');$('#spine-toggle').addEventListener('click',()=>{localStorage.setItem('laplace:writing:contents',root.dataset.spine||'open');if(innerWidth<700&&root.dataset.spine!=='collapsed')setOpen(false);});}if(innerWidth<700||localStorage.getItem('laplace:writing:contents')==='collapsed')root.dataset.spine='collapsed';
  if($('#geo-door'))$('#geo-door').textContent='PDF';if($('#ledger-door'))$('#ledger-door').textContent='History';if($('#back-door'))$('#back-door').textContent='Source editor';
  const start=async()=>{
    project=window.walk?.context()?.corpus||q.get('corpus')||$('meta[name="walk:corpus"]')?.content;
    if(!project)return;
    const projects=await request('/authoring/projects');picker.replaceChildren(...projects.projects.map(p=>{const o=E('option','',p.name);o.value=p.id;return o;}));picker.value=project;
    if(window.walk?.ready())window.walk.setDocSize(Number(localStorage.getItem('laplace:walk:font-size')||17));
    await loadState();if(!window.walk.actor())window.walk.nameActor('author');captureSelection(false);await markAnnotations();const remembered=localStorage.getItem('laplace:session:'+project);if(remembered&&state.sessions.some(s=>s.id===remembered)){sessionId=remembered;$('#writing-sessions').value=sessionId;await readSession();}else renderEmpty();$('#writing-project-home').href='/project?corpus='+encodeURIComponent(project);
    const note=$('#spine-note');if(note&&!note.closest('details')){const detail=E('details','writing-reading-details');detail.append(E('summary','','About this view'));note.before(detail);detail.append(note);}const title=$('#spine .spine-title')||$('#spine h3')||$('#spine-head');if(title)title.textContent='Contents';
    if(q.get('tab'))await showTab(q.get('tab'));
    if(q.get('stage')){const pipeline=await request('/work/pipeline?project='+encodeURIComponent(project));const stage=pipeline.stages.find(s=>s.id===q.get('stage'));if(stage)workOnProject(stage.prompt,stage.id==='manuscript'?'revise':stage.id==='review'?'review':'work');}
    if(q.get('task')){const work=await request('/work/context?project='+encodeURIComponent(project)+'&task='+encodeURIComponent(q.get('task')));$('#writing-message').value=work.prompt;$('#writing-mode').value='work';status('Project task loaded. Choose a provider and continue.');}
  };
  if(window.walk?.ready())start().catch(e=>status(e.message,true));
  else {const wait=setInterval(()=>{if(window.walk){clearInterval(wait);window.walk.on('ready',()=>start().catch(e=>status(e.message,true)));if(window.walk.ready())start().catch(e=>status(e.message,true));}},50);setTimeout(()=>clearInterval(wait),20000);}
}
async function loadState(){state={...state,...await request('/authoring/state?project='+encodeURIComponent(project)+'&view=sessions&session_limit='+sessionLimit)};const sel=$('#writing-sessions');sel.replaceChildren(E('option','','New conversation'));sel.firstChild.value='';for(const s of [...(state.sessions||[])].reverse()){const o=E('option','',`${s.role==='review'?'Review · ':''}${s.title||s.provider+' conversation'} · ${new Date(s.created_at*1000).toLocaleDateString()}`);o.value=s.id;sel.append(o);}if(sessionId)sel.value=sessionId;$('#writing-more-sessions').hidden=state.sessions.length>=state.session_count;status('Ready');}
async function loadProviders(force=false){try{status('Reading connected provider capabilities…');pendingRead($('#writing-status'));const data=await request('/authoring/providers'+(force?'?refresh=1':''));providers=data.providers;providerLoaded=true;for(const o of $('#writing-provider').options){const p=providers.find(x=>x.id===o.value);o.disabled=!p?.available;}populateModels(false);const unavailable=providers.filter(p=>!p.available).map(p=>p.name+': '+(p.auth_state==='UNAUTHENTICATED'?'sign in with claude auth login':p.error||p.auth_state||'unavailable'));status(unavailable.length?unavailable.join(' · '):'Provider capabilities loaded');}catch(e){status(e.message,true);}}
function populateModels(reset=true){const current=$('#writing-model').value,previousEffort=$('#writing-effort').value;const p=providers.find(x=>x.id===$('#writing-provider').value);$('#writing-model').replaceChildren(...(p?.models||[]).map(m=>{const o=E('option');o.value=m.id;o.textContent=m.name;return o;}));const model=(!reset&&current?p?.models.find(x=>x.id===current):null)||p?.models.find(x=>x.default);$('#writing-model').value=(!reset&&current?current:model?.id)||'';const efforts=model?.efforts?.filter(Boolean)||['low','medium','high'];$('#writing-effort').replaceChildren(...efforts.map(x=>E('option','',x)));$('#writing-effort').value=!reset&&efforts.includes(previousEffort)?previousEffort:efforts.includes('medium')?'medium':efforts[0];modelSummary();}
function setSessionBusy(busy){for(const id of ['writing-provider','writing-model','writing-effort','writing-mode','writing-new','writing-sessions','writing-refresh-providers'])$('#'+id).disabled=busy;}
function modelSummary(){const p=$('#writing-provider').value,m=$('#writing-model').value;$('#writing-model-summary').textContent=`${p==='codex'?'Codex':'Claude'} · ${m||'configured model'} · ${$('#writing-effort').value}`;}
function captureSelection(explicit) {
  const pos = window.walk?.readingPosition();
  const blocks = window.walk?.blocks() || [];
  const block = blocks.find(x => x.id === pos?.blockId);
  const selectedText = window.getSelection()?.toString().trim() || '';
  const span = window.walk?.span();
  const ids = span?.sections?.length > 1 ? span.sections : [pos?.sectionId].filter(Boolean);
  const section = blocks.filter(x => ids.includes(x.section));
  const files = [...new Set(section.map(x=>x.file).filter(Boolean))];
  selection = {
    files: files.length ? files : block?.file ? [block.file] : [],
    section_ids: ids,
    line_start: files.length === 1 && section.length ? Math.min(...section.map(x=>x.line_start)) : undefined,
    line_end: files.length === 1 && section.length ? Math.max(...section.map(x=>x.line_end)) : undefined,
    anchor: {file:block?.file || '', section:pos?.sectionId || '', block:block?.id || '',
             line_start:block?.line_start, line_end:block?.line_end},
    quote: explicit ? selectedText : ''
  };
  $('#writing-selection').textContent = selectedText && explicit
    ? `Selected: ${selectedText.slice(0,110)}` : ids.length > 1
      ? `${ids.length} sections · connected context` : `${pos?.label || 'Project framing'} · connected context`;
  return selection;
}
function renderEmpty(){const t=$('#writing-thread');t.replaceChildren();const empty=E('div','writing-empty');empty.append(E('h3','','Think it through. Write it clearly.'),E('p','','Work on the argument with Eigen while the manuscript stays in view. Select a passage to bring it into the conversation.'),E('p','writing-muted','Your framing, evidence and banked corrections travel with the work.'));t.append(empty);}
function message(role,text){$('.writing-empty')?.remove();const row=E('article',`writing-message ${role}`);row.append(E('span','speaker',role==='user'?'You':'Eigen'));row.append(E('div','message-body',text));$('#writing-thread').append(row);return row;}
function scrollBottom(){const t=$('#writing-thread');t.scrollTop=t.scrollHeight;}
function replyText(reply){if(reply.status==='interrupted'&&!reply.text)return 'Stopped before a complete reply.';return reply.display_text||reply.proposal?.answer||(reply.error?(typeof reply.error==='string'?reply.error:reply.error.message||JSON.stringify(reply.error)):reply.text)||'No reply text.';}
async function readSession(){const data=await request('/authoring/session?view=summary&id='+encodeURIComponent(sessionId));sessionRole=data.session.role||'author';$('#writing-mode').value=sessionRole==='review'?'review':data.turns.at(-1)?.mode||'discuss';$('#writing-provider').value=data.session.provider;$('#writing-model').value=data.session.model||'';$('#writing-effort').value=data.session.effort;modelSummary();$('#writing-thread').replaceChildren();for(const t of data.turns){message('user',t.text);for(const s of t.steering||[])message('user',s.text);if(t.reply){const r=message('assistant',replyText(t.reply));proposal(r,t);} }if(!data.turns.length)renderEmpty();historyButton(data.older_cursor);if(data.active){message('assistant',data.active.text);connect(data.active.id,data.active.cursor);}if(data.recovery)status(data.recovery,true);scrollBottom();}
function historyButton(cursor){
  $('#writing-older')?.remove();if(!cursor)return;
  const b=E('button','','Load earlier messages');b.id='writing-older';
  b.onclick=operation(async()=>{const thread=$('#writing-thread'),height=thread.scrollHeight,top=thread.scrollTop;const data=await request('/authoring/session?view=summary&id='+encodeURIComponent(sessionId)+'&before='+encodeURIComponent(cursor));const fragment=document.createDocumentFragment();for(const t of data.turns){fragment.append(message('user',t.text));for(const steer of t.steering||[])fragment.append(message('user',steer.text));if(t.reply){const reply=message('assistant',replyText(t.reply));proposal(reply,t);fragment.append(reply);}}b.remove();thread.prepend(fragment);historyButton(data.older_cursor);thread.scrollTop=top+thread.scrollHeight-height;});
  $('#writing-thread').prepend(b);
}
// Exact saved detail supplies its proposal identity. Applying never reads a newer
// candidate at the click; a refusal preserves the displayed comparison.
function proposal(row,turn){
  const readDetail=async()=>{const data=await request('/authoring/session-turn?'+new URLSearchParams({project,id:turn.id,view:'turn'}));const detail=E('section','writing-card');proposal(detail,data.turn);row.append(detail);return detail;};
  if(!turn.reply?.proposal?.edits?.length&&turn.proposal_edit_count){const inspect=E('button','','Inspect saved manuscript changes');inspect.onclick=operation(async()=>{await readDetail();inspect.remove();});row.append(inspect);return;}
  const edits=turn.reply?.proposal?.edits||[];if(!edits.length)return;
  const proposalVersion=turn.proposal_version,details=E('details','writing-card');details.open=true;details.append(E('summary','',`${edits.length} proposed ${edits.length===1?'edit':'edits'}`));for(const edit of edits)details.append(E('p','',`${edit.file}:${edit.line_start} — ${edit.reason}`),E('pre','',`− ${edit.before}\n\n+ ${edit.after}`));row.append(details);
  const reviewed=['applied','applied-elsewhere','rejected','superseded','fulfilled'].includes(turn.proposal_state),partial=turn.proposal_state==='partial-application',labels={applied:'Applied','applied-elsewhere':'Applied elsewhere',rejected:'Rejected',superseded:'Superseded',fulfilled:'Already fulfilled'};const apply=E('button','primary',labels[turn.proposal_state]|| (partial?'Review required':'Apply revision'));apply.disabled=reviewed||partial||!proposalVersion;
  if(!proposalVersion)row.append(E('p','writing-muted','This detail did not return a proposal version. Re-read its exact saved detail before applying.'));
  apply.onclick=operation(async()=>{requireSavedDrafts();if(!proposalVersion)throw Error('This saved comparison has no owner-issued proposal version.');const result=await request('/authoring/apply',{turn_id:turn.id,project,proposal_version:proposalVersion});if(!result.complete)throw Error('Some edits could not be applied. Inspect the source before continuing.');status('Revision applied · manuscript updated');apply.textContent='Applied';apply.dataset.done='1';apply.disabled=true;await window.walk?.refresh?.();});
  const refresh=E('button','','Re-read saved proposal');refresh.onclick=operation(async()=>{const detail=await readDetail();row.replaceChildren(detail);status('Saved proposal re-read. Inspect the displayed version before deciding.');});row.append(apply,refresh);
}
async function sendMessage(e){e.preventDefault();const input=$('#writing-message');const text=input.value.trim();if(!text)return;if(activeTurn){if($('#writing-provider').value!=='codex')throw new Error('Wait for the Claude reply or stop it before sending another message.');await request('/authoring/steer',{turn_id:activeTurn,text});message('user',text);input.value='';status('Steering sent');return;}if(!selection?.quote)captureSelection(false);const data=await request('/authoring/turn',{project,session_id:sessionId||undefined,provider:$('#writing-provider').value,model:$('#writing-model').value,effort:$('#writing-effort').value,text,mode:$('#writing-mode').value,selection,work_id:q.get('task')||undefined,request_id:crypto.randomUUID()});sessionId=data.session_id;sessionRole=$('#writing-mode').value==='review'?'review':'author';localStorage.setItem('laplace:session:'+project,sessionId);message('user',text);input.value='';message('assistant','');scrollBottom();connect(data.turn_id);}
function connect(id,cursor=0){stream?.close();activeTurn=id;setSessionBusy(true);$('#writing-stop').hidden=false;$('#writing-send').textContent=$('#writing-provider').value==='codex'?'Steer':'Send';status('Eigen is working…');stream=new EventSource('/authoring/events?turn='+encodeURIComponent(id)+'&after='+cursor);let answer=$('#writing-thread').lastElementChild?.querySelector('.message-body');if(!answer)answer=message('assistant','').querySelector('.message-body');stream.onmessage=async(e)=>{const event=JSON.parse(e.data);if(event.type==='delta'){const t=$('#writing-thread'),atEnd=t.scrollHeight-t.scrollTop-t.clientHeight<80;if(['discuss','review'].includes($('#writing-mode').value))answer.textContent+=event.text;if(atEnd)scrollBottom();}else if(event.type==='progress')status(String(event.text).replace(/([a-z])([A-Z])/g,'$1 $2'));else if(event.type==='complete'){stream.close();activeTurn='';setSessionBusy(false);$('#writing-stop').hidden=true;$('#writing-send').textContent='Send';await readSession();await loadState();status(event.result.status==='completed'?'Reply saved':event.result.status==='interrupted'?'Stopped · any partial reply is saved':`Turn ${event.result.status}: ${JSON.stringify(event.result.error||'')}`,event.result.status==='failed');}else if(event.type==='error')status(event.message,true);};stream.onerror=()=>{if(stream.readyState===EventSource.CLOSED){activeTurn='';setSessionBusy(false);$('#writing-stop').hidden=true;status('Connection ended. The saved session can be reopened.');}};}
async function showTab(id){window.walk?.dismissEditorCard?.();currentTab=id;for(const b of document.querySelectorAll('.writing-tabs button'))b.setAttribute('aria-selected',String(b.dataset.tab===id));for(const v of document.querySelectorAll('.writing-view'))v.hidden=v.dataset.view!==id;try{if(id==='argument'){if(!argumentDirty)state={...state,...await request('/authoring/state?'+new URLSearchParams({project,view:'summary'}))};renderArgument();}if(id==='sources')await renderSources();if(id==='evidence')await renderEvidence();if(id==='corrections'){await loadCorrections();}}catch(e){status(e.message,true);}}
function renderArgument(){const view=$('[data-view=argument]');if(argumentDirty&&view.childElementCount)return;argumentBaseRevision=state.revision;view.replaceChildren(E('p','writing-muted','Develop the connected argument before deciding how to divide the prose.'));for(const [key,label]of [['purpose','Purpose'],['audience','Reader'],['question','Central question']])view.append(field(label,'input','argument-'+key,state.framing?.[key]||''));view.append(field('The argument','textarea','argument-text',state.argument_text||state.argument||''));$('#argument-text').rows=14;$('#argument-text').placeholder='What problem creates the need for the next idea? How does the construction resolve it, and what follows?';for(const input of view.querySelectorAll('input,textarea'))input.oninput=()=>{argumentDirty=true;status('Argument has unsaved changes');};const b=E('button','primary','Save argument');b.onclick=operation(async()=>{const data=await request('/authoring/argument',{project,base_revision:argumentBaseRevision,argument:$('#argument-text').value,framing:Object.fromEntries(['purpose','audience','question'].map(k=>[k,$('#argument-'+k).value]))});state={...state,...data};argumentDirty=false;argumentBaseRevision=data.revision;status('Argument saved · future turns will use this version');});view.append(b);}
async function renderSources(){
  const view=$('[data-view=sources]');
  view.replaceChildren(E('p','writing-muted','Find a source, keep the relevant qualification with it, and bring it into the explanation. Zotero metadata alone does not establish a claim.'));
  const search=E('form','writing-search');search.innerHTML='<input id="reference-query" aria-label="Search Zotero" placeholder="Title, author, or topic"><button class="primary">Search</button>';search.onsubmit=operation(async e=>{e.preventDefault();await searchReferences();});view.append(search);
  const feedback=E('p','writing-muted');feedback.id='reference-status';view.append(feedback);const results=E('div');results.id='reference-results';view.append(results);
  const connection=await request('/references/status');feedback.textContent=connection.provider==='unavailable'?(connection.error||connection.note||'Zotero unavailable'):'Connected to local Zotero · original library stays unchanged';
  const attached=await request('/references/attached?project='+encodeURIComponent(project));
  view.append(E('h3','','Attached to this project'));
  for(const row of attached.associations||[]){const c=E('article','writing-card');c.append(E('h4','',row.metadata?.title||row.citekey),E('p','',`${row.citekey} · ${row.state}`));if(row.note)c.append(E('p','',row.note));if(row.claim_id)c.append(E('p','',`Associated claim: ${row.claim_id}`));const use=E('button','','Use in current passage');use.onclick=()=>workOnProject(`Inspect the attached reference ${row.citekey} (Zotero ${row.key}) and its note: ${row.note||'(none)'}. Assess its relevance to the current passage, distinguishing what the source actually supports. Propose an appropriate citation and connected prose revision. Do not invent a quotation or source claim.`, 'revise');c.append(use);const update=E('button','','Update bibliography metadata');update.onclick=operation(async()=>{await request('/references/update',{project,key:row.key});await renderSources();status('Bibliography updated · citation keys and notes preserved');});if(row.state==='STALE')c.append(update);else{const details=E('details');details.append(E('summary','','Metadata actions'),update);c.append(details);}view.append(c);}
  if(!attached.associations?.length)view.append(E('p','writing-muted','No references attached yet. Search Zotero above.'));
  const refresh=E('button','','Check for reference changes');refresh.onclick=operation(async()=>{const r=await request('/references/refresh',{project});await renderSources();status(`${r.checked} sources checked · ${r.stale.length} need review`);});view.append(refresh);
}
async function searchReferences(){
  status('Searching Zotero…');pendingRead($('#writing-status'));const data=await request('/references/search?project='+encodeURIComponent(project)+'&q='+encodeURIComponent($('#reference-query').value));const host=$('#reference-results');host.replaceChildren();const items=data.items||[];
  for(const item of items){const c=E('article','writing-card');c.append(E('h4','',item.title||item.key),E('p','',(item.creators||[]).map(x=>typeof x==='string'?x:x.lastName||x.name||'').join(', ')),E('p','',item.year||''));
    const note=field('Why is this source relevant? (optional)','textarea','ref-note-'+item.key);note.lastChild.rows=2;const extra=E('details');extra.append(E('summary','','Note or claim link'),note);const claim=field('Related claim (optional)','input','ref-claim-'+item.key);extra.append(claim);const cite=field('Citation key (optional)','input','ref-key-'+item.key,item.citation_key||'');extra.append(cite);c.append(extra);
    const row=E('div','writing-actions');const read=E('button','','Read with Eigen');read.onclick=()=>workOnProject(`Read local Zotero item ${item.key}, titled ${item.title}, using reference_text. Distinguish extracted paper text from metadata-only availability. Explain its relevance, qualifications and potential connection to this manuscript without inventing claims.`,'discuss');row.append(read);const attach=E('button','','Attach source');attach.onclick=operation(async()=>{const r=await request('/references/attach',{project,key:item.key,citekey:cite.lastChild.value||undefined,note:note.lastChild.value,claim_id:claim.lastChild.value||undefined});status(`Attached ${r.association.citekey} · ready to use in the manuscript`);attach.textContent='Attached';attach.dataset.done='true';const use=E('button','','Use in current passage');use.onclick=()=>workOnProject(`Use attached source ${r.association.citekey} in the current passage if its contents support the point. The author’s note is: ${note.lastChild.value||'(none)'}. Inspect the source and propose a source-addressed revision including the citation.`,'revise');row.append(use);});row.append(attach);
    const deep=item.deep_link;if(deep&&deep.startsWith('zotero:')){const a=E('a','','Open in Zotero');a.href=deep;row.append(a);}if(item.doi){const a=E('a','','Publisher');a.href='https://doi.org/'+encodeURIComponent(item.doi);a.target='_blank';a.rel='noopener';row.append(a);}c.append(row);host.append(c);
  }
  if(!items.length)host.append(E('p','writing-muted','No matches. Try an author or a shorter title.'));status(`${items.length} references found`);
}
function workOnProject(text, mode='work') {
  if(mode==='review'||sessionRole==='review'){sessionId='';localStorage.removeItem('laplace:session:'+project);$('#writing-sessions').value='';renderEmpty();}
  setOpen(true);showTab('session');captureSelection(false);
  $('#writing-mode').value=mode;$('#writing-message').value=text;$('#writing-message').focus();
  status('Brief ready · review it and send when you are ready');
}
async function renderEvidence(){await mountEvidence($('[data-view=evidence]'),{project,request,pending:pendingRead,status,work:workOnProject,refresh:()=>window.walk.refresh(),comment:spec=>annotate({scope:'project',heading:'Comment on this visual',quote:(spec.title||spec.id)+': '+spec.caption,anchor:{asset_id:'figure:'+spec.id,file:spec.section||''}})});}
function anchoredBlock(anchor={}) {
  const blocks=window.walk.blocks().filter(b=>!anchor.file||b.file===anchor.file||b.file.endsWith('/'+anchor.file));
  const quote=String(anchor.quote||anchor.after||'').replace(/\s+/g,' ').trim();
  if(quote){const matching=blocks.filter(b=>b.text.replace(/\s+/g,' ').includes(quote));if(matching.length===1)return matching[0];return null;}
  return blocks.find(b=>b.id===anchor.block&&(!anchor.line_start||b.line_start===anchor.line_start))||blocks.find(b=>anchor.line_start&&b.line_start<=anchor.line_start&&b.line_end>=anchor.line_start);
}
async function jumpToAnchor(anchor={}) {
  if(anchor.show_changes){await window.walk.setAuthorChanges(true,{refresh:false});await window.walk.refreshAuthorChanges({...(anchor.correction_id?{id:anchor.correction_id}:{file:anchor.file}),focus:true,force:true});return;}
  const block=anchoredBlock(anchor);
  if(block)window.walk.jumpToBlock(block.id);else if(anchor.section){window.walk.jumpToSection(anchor.section);status('The exact passage has changed; its section is open.');}else status('The exact passage has changed. The original text remains in this note.');
  if(innerWidth<700)setOpen(false);
}
let annotationGeneration=0;
async function markAnnotations(){
  const file=selection?.anchor?.file;if(!file)return;const token=++annotationGeneration;
  try{const page=await request('/authoring/history?'+new URLSearchParams({project,file,correction_category:'passage-comments',status:'open',order:'newest',limit:'25'}));if(token!==annotationGeneration)return;
    for(const node of document.querySelectorAll('.writing-annotated'))node.classList.remove('writing-annotated');
    for(const c of page.items||[]){const b=anchoredBlock(c.anchor||{});if(!b)continue;const node=[...document.querySelectorAll('.blk[data-block]')].find(n=>n.dataset.block===b.id);if(node){node.classList.add('writing-annotated');node.title='Feedback available in Notes';}}
    if(page.next_offset!=null)status('Showing markers for the latest 25 comments in this file. Notes retains all '+page.total+' comments.');
  }catch(error){status('Comment markers unavailable: '+error.message,true);}
}
// Panel-local drafts follow their project across tab rebuilds; canonical notes
// remain exclusively at the correction owner after a successful save.
const correctionDrafts=new Map();
let correctionReview=null,correctionReviewProject='';
async function loadCorrections(){
  if(!correctionReview||correctionReviewProject!==project){const frame=await request('/authoring/state?'+new URLSearchParams({project,view:'summary'}));state={...state,...frame};renderCorrections();correctionReview?.destroy();correctionReviewProject=project;correctionReview=await mountReview($('#writing-correction-history'),{project,request,status,initialFilter:'notes',allowNewNote:false,onOpenPassage:jumpToAnchor,proposalActionLabel:'Inspect saved comparison',onReviewProposal:panelProposalReview({project,inspect:async(id,{proposalVersion}={})=>{const preview=await request('/authoring/proposal-preview?'+new URLSearchParams({project,turn_id:id,...(proposalVersion?{proposal_version:proposalVersion}:{})}));window.walk.showProposal(preview,{readOnly:true});status('Saved comparison · inspect only. Whole revision application is available in its conversation.');}}),onDiscuss:(text,anchor)=>workOnProject(text,anchor==='review'?'review':'discuss')});}
}

function renderCorrections(){
  const draftProject=project,draft=correctionDrafts.get(draftProject)||{text:'',scope:'project',base_revision:state.revision};
  const view=$('[data-view=corrections]'),history=$('#writing-correction-history')||E('section');history.id='writing-correction-history';view.replaceChildren(E('p','writing-muted','Comments and direct edits remain connected to the passage they concern. They inform later writing; they do not silently become rules.'));
  const noteField=field('Note','textarea','correction-text',draft.text),note=noteField.lastChild;view.append(noteField);
  const scope=field('Applies to','select','correction-scope'),scopeInput=scope.lastChild;scopeInput.innerHTML='<option value="project">This project</option><option value="passage">Current passage</option>';scopeInput.value=draft.scope;view.append(scope);
  let capturedAnchor=draft.anchor;const remember=()=>{if(scopeInput.value==='passage'&&!capturedAnchor)capturedAnchor=captureSelection(false)?.anchor;correctionDrafts.set(draftProject,{text:note.value,scope:scopeInput.value,base_revision:draft.base_revision,anchor:capturedAnchor});};note.oninput=remember;scopeInput.onchange=remember;
  const save=E('button','primary','Save note');save.onclick=operation(async()=>{const submitted={text:note.value,scope:scopeInput.value};remember();const sel=captureSelection(false);const result=await request('/authoring/correction',{project:draftProject,...submitted,base_revision:draft.base_revision,kind:'note',anchor:submitted.scope==='passage'?(capturedAnchor||sel.anchor):{},by:'author'});if(result?.ok===false)throw Error(result.error||result.reason||'The note was not saved.');const current=correctionDrafts.get(draftProject);if(current?.text===submitted.text&&current?.scope===submitted.scope){correctionDrafts.delete(draftProject);note.value='';scopeInput.value='project';}if(result.revision!=null)state.revision=result.revision;await loadState();renderCorrections();if(correctionReview&&correctionReviewProject===draftProject)await correctionReview.refresh();status(project===draftProject?'Note saved with its scope':'Note saved for '+draftProject);});view.append(save);
  const inspect=E('button','','Review current note revision');inspect.onclick=operation(async()=>{const current=await request('/authoring/state?'+new URLSearchParams({project:draftProject,view:'summary'}));const info=E('section','writing-card');info.append(E('p','','Current authoring revision '+current.revision));const use=E('button','','Use reviewed revision for this note');use.onclick=()=>{draft.base_revision=current.revision;remember();info.remove();status('Note draft retained with the explicitly reviewed revision.');};info.append(use);view.append(info);});view.append(inspect);
  const discard=E('button','','Discard unsaved note');discard.onclick=()=>{correctionDrafts.delete(draftProject);note.value='';scopeInput.value='project';};view.append(discard);
  const distil=E('button','','Review patterns with Eigen');distil.onclick=()=>workOnProject('Review the accumulated author comments and direct edits in this project. Identify recurring, well-supported preferences and corrections, keeping local choices distinct from proposed general guidance. Show concrete examples and contradictions. Propose a concise summary for my review; do not promote it into global law.','discuss');view.append(distil);
  view.append(history);
}

async function showLibrary() {
  let dialog = $('#writing-library');
  if (!dialog) {
    dialog = E('dialog'); dialog.id = 'writing-library';
    dialog.setAttribute('aria-label', 'Project library');
    document.body.append(dialog);
  }
  dialog.replaceChildren();
  const header = E('header');
  header.append(E('h2', '', 'Your projects'));
  const close = E('button', '', 'Close'); close.onclick = () => dialog.close();
  header.append(close); dialog.append(header);
  const bar = E('div', 'library-tools');
  const search = E('input'); search.placeholder = 'Find a manuscript or project';
  search.setAttribute('aria-label', 'Filter projects');
  const create = E('button', 'primary', 'New project');
  const discover = E('button', '', 'Add existing manuscript');
  bar.append(search, create, discover); dialog.append(bar);
  const feedback = E('p', 'writing-muted'); feedback.setAttribute('role', 'status');
  const list = E('div', 'library-grid'); dialog.append(feedback, list);
  dialog.showModal();
  const navigate = (name,created=false) => { location.href = '/project?workspace=writing&corpus=' + encodeURIComponent(name)+(created?'&view=overview&conversation=open':''); };
  let library = await request('/projects/library');
  function paint() {
    list.replaceChildren();
    for (const p of library.projects.filter(x => `${x.title} ${x.name}`.toLowerCase().includes(search.value.toLowerCase()))) {
      const card = E('button', 'library-card');
      card.append(E('strong', '', p.title || p.name), E('span', '', p.creation?.status === 'failed' ? 'Creation needs attention' : p.source_optional ? 'Open project' : p.status === 'resolved' ? 'Open project' : 'Manuscript pending'));
      card.onclick = () => navigate(p.name); list.append(card);
    }
  }
  search.oninput = paint; paint();
  create.onclick = () => {
    list.replaceChildren(); feedback.textContent = 'Create a project for work and material. Add a manuscript when needed.';
    const form = E('form', 'library-form');
    form.append(field('Working title', 'input', 'new-project-title'));
    const type = field('Project category', 'select', 'new-project-kind');
    type.lastChild.innerHTML = '<option value="general">General project</option><option value="software">Software</option><option value="company">Company</option><option value="transcript">Transcript</option><option value="campaign">Campaign</option><option value="book">Book / master document</option><option value="paper">Paper</option>';
    form.append(type, field('Purpose', 'textarea', 'new-project-purpose'), field('Intended reader', 'input', 'new-project-audience'));
    const button = E('button', 'primary', 'Create project'); form.append(button);
    form.onsubmit = async e => {
      e.preventDefault(); button.disabled = true;
      try {
        const title = $('#new-project-title').value.trim();
        const name = title.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
        const result = await request('/projects/create', {name, title, kind:$('#new-project-kind').value,
          purpose:$('#new-project-purpose').value, audience:$('#new-project-audience').value});
        navigate(result.project || result.name || name,true);
      } catch(error) { feedback.textContent = error.message; button.disabled = false; }
    };
    list.append(form); $('#new-project-title').focus();
  };
  discover.onclick = async () => {
    try {
      pendingRead(feedback, 'Looking for manuscripts already in this workspace…');
      const found = await request('/projects/discover');
      const candidates = found.candidates || found.manuscripts || [];
      list.replaceChildren();
      for (const item of candidates) {
        const card = E('article', 'library-card');
        card.append(E('strong', '', item.title || item.root), E('span', '', item.root));
        const editable=E('input');editable.type='checkbox';const permission=E('label','library-permission','Allow editing this source');permission.prepend(editable);card.append(permission);
        const button = E('button', '', 'Add to projects');
        button.onclick = async () => {
          try {
            const title = item.title || item.root.split('/').slice(-3,-1).join(' ');
            const name = title.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'').slice(0,55)+'-'+Math.random().toString(36).slice(2,6);
            const result = await request('/projects/import', {name,title,root:item.root,editable:editable.checked});
            navigate(result.project || name);
          } catch(error) { feedback.textContent = error.message; }
        };
        card.append(button); list.append(card);
      }
      feedback.textContent = candidates.length ? 'Existing sources are preserved. Choose the manuscript you want to organise.' : 'All discovered manuscripts are already registered.';
    } catch(error) { feedback.textContent = error.message; }
  };
}

function wireAnnotations() {
  const bubble = E('div'); bubble.id = 'writing-selection-actions'; bubble.hidden = true;
  bubble.setAttribute('role', 'toolbar'); bubble.setAttribute('aria-label', 'Selected passage');
  let frozen = null;
  for (const [label, action] of [['Comment','comment'], ['Discuss','discuss'], ['Revise','revise']]) {
    const button = E('button', '', label);
    button.onmousedown = e => e.preventDefault();
    button.onclick = () => {
      bubble.hidden = true;
      if (!frozen) return;
      selection = frozen;
      if (action === 'comment') annotate(frozen);
      else {
        setOpen(true); showTab('session');
        $('#writing-mode').value = action === 'revise' ? 'revise' : 'discuss';
        $('#writing-selection').textContent = `Selected: ${frozen.quote.slice(0,110)}`;
        $('#writing-message').focus();
      }
    };
    bubble.append(button);
  }
  document.body.append(bubble);
  function offer() {
    const selected = window.getSelection();
    if (!selected?.rangeCount || selected.isCollapsed) { bubble.hidden = true; return; }
    const node = selected.anchorNode?.nodeType === 1 ? selected.anchorNode : selected.anchorNode?.parentElement;
    const blockEl = node?.closest?.('.blk[data-block]');
    if (!blockEl || !$('#paper').contains(blockEl)) { bubble.hidden = true; return; }
    const block = window.walk?.blocks().find(b => b.id === blockEl.dataset.block);
    if (!block) return;
    const quote = selected.toString().trim();
    if (!quote) return;
    const range = selected.getRangeAt(0);
    const blocks = window.walk.blocks();
    const touched = [...$('#paper').querySelectorAll('.blk[data-block]')]
      .filter(el=>range.intersectsNode(el)).map(el=>blocks.find(b=>b.id===el.dataset.block)).filter(Boolean);
    const ids = [...new Set(touched.map(b=>b.section))];
    const section = blocks.filter(b=>ids.includes(b.section));
    const files = [...new Set(section.map(b=>b.file).filter(Boolean))];
    frozen = {files, section_ids:ids, quote,
      line_start:files.length===1?Math.min(...section.map(b=>b.line_start)):undefined,
      line_end:files.length===1?Math.max(...section.map(b=>b.line_end)):undefined,
      anchor:{file:block.file, section:block.section, block:block.id, quote,
              line_start:block.line_start,line_end:block.line_end}};
    const rect = selected.getRangeAt(0).getBoundingClientRect();
    bubble.style.left = Math.max(8,Math.min(innerWidth-bubble.offsetWidth-8,rect.left)) + 'px';
    bubble.style.top = Math.max(54,rect.top-42) + 'px'; bubble.hidden = false;
  }
  $('#paper').addEventListener('mouseup', offer);
  $('#paper').addEventListener('keyup', e => { if(e.shiftKey)offer(); });
  $('#paper').addEventListener('scroll', () => { bubble.hidden = true; }, {passive:true});
}

function annotate(passage) {
  let dialog = $('#writing-annotation');
  if (!dialog) { dialog=E('dialog');dialog.id='writing-annotation';document.body.append(dialog); }
  dialog.replaceChildren(E('h3','',passage.heading||'Comment on this passage'));
  dialog.append(E('blockquote','',passage.quote));
  const form=E('form');
  const text=E('textarea');text.rows=4;text.placeholder='What should change, or what needs attention?';text.setAttribute('aria-label','Comment');
  const row=E('div','writing-actions');
  const cancel=E('button','','Cancel');cancel.type='button';cancel.onclick=()=>dialog.close();
  const save=E('button','primary','Save comment');save.type='submit';
  const feedback=E('p','writing-muted');feedback.setAttribute('role','status');
  row.append(cancel,save);form.append(text,row,feedback);dialog.append(form);
  form.onsubmit=async event=>{
    event.preventDefault();if(!text.value.trim())return;save.disabled=true;
    try {
      await request('/authoring/correction',{project,text:text.value,kind:'note',scope:passage.scope||'passage',anchor:passage.anchor,by:'author'});
      dialog.close();await loadState();status('Comment saved with its target and context');
      const block=[...document.querySelectorAll('.blk[data-block]')].find(n=>n.dataset.block===passage.anchor.block);
      block?.classList.add('writing-annotated');
      if(block){block.title='You left a comment on this passage';}
    } catch(error){feedback.textContent=error.message;save.disabled=false;}
  };
  dialog.showModal();text.focus();
}

function requireSavedDrafts(){const edit=window.walk?.editState();if(edit?.dirty||edit?.parked)throw Error('Save or discard your direct edits before applying another source change or building the PDF.');}
async function buildPDF() {
  requireSavedDrafts();
  await request('/authoring/build', {project});status('Building the current PDF…');pendingRead($('#writing-status'));
  while(true){
    await new Promise(resolve=>setTimeout(resolve,900));
    const result=await request('/authoring/build?project='+encodeURIComponent(project));
    if(result.running||result.state==='running')continue;
    if(result.ok){await window.walk.refresh();status('PDF built from the current source · open PDF to review it');return;}
    const row=message('assistant','The manuscript did not compile.');const log=E('details','writing-card');log.append(E('summary','','Build log'),E('pre','',result.log_tail||result.reason||JSON.stringify(result)));row.append(log);setOpen(true);showTab('session');throw Error(result.reason||'Build failed. See the log in the session.');
  }
}
