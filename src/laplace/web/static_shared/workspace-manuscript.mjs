// WORKSPACE MANUSCRIPT (M5 S2 F2). Purpose: the Manuscript view's frame and editor: the walk iframe
// (/walk?workspace=writing&embedded=1&editor=workbench) and the manuscript editor band over it
// (createManuscriptEditor), the build-summary refresh poller (createManuscriptRefresh), the passage,
// placement and bound-source doors that open an exact place in the manuscript, the guard against applying a
// revision over a standing draft, and the record of external applications for the walk's Undo history.
// Ownership: source, drafts, Undo and the document belong to the walk and its owners; this controller owns
// the one frame, the one editor, the poller and the frame's walk subscriptions. Public contract:
// mountManuscript(project, services) -> {render(host), currentWindow(), ready(), saved(), editor(), host(),
// capturePlace(), restorePlace(place), hasDraft(), observe(), inspectPassage(anchor, options),
// openPlacement(location), openBoundSource(read), rememberApplication(application), flushExternalHistory(),
// updates, lifetime(), destroy()}. Services: views (current view, show, generation), forms (leave), ui
// (notice, $, refresh-warning clearing), outline, readerHome, discussion (session), inspect (project
// artifact), activity (open an owner history), place (the reader return). Lifetime: each frame load owns
// named walk.on subscriptions with walk.off disposers and a generation; destroy() disposes them, destroys
// the poller and the editor, detaches the frame and removes it.
import {E} from './workspace-dom.mjs';
import {projectRequest as api} from "/shared/workspace-session.mjs";
import {createManuscriptEditor} from './manuscript-editor.mjs';
import {createManuscriptRefresh,waitForManuscript} from "/shared/manuscript-editing.mjs";
import {structureReadURL} from './workspace-spine.mjs';

// One source identity (G1): a target that names its checkout path (`repo_file`) matches a
// block's `repo_file` exactly; a target that only names a manuscript-relative file matches
// `file` exactly or as the tail of a checkout path. A target the owner marked UNPROVED (a
// historical basename) never matches: it must not be placed in a same-named file.
export function manuscriptPassageTarget(blocks=[],anchor={}){
  if(!anchor?.file&&!anchor?.repo_file)return null;
  if(anchor.binding==='UNPROVED')return null;
  // A bound checkout path that no block carries is simply not in this manuscript; it is
  // never retried as a tail match, which could land in another edition's same-named file.
  if(anchor.repo_file&&!blocks.some(block=>block.repo_file===anchor.repo_file))return null;
  const byRepo=anchor.repo_file?blocks.filter(block=>block.repo_file===anchor.repo_file):[];
  const sameFile=block=>block.file===anchor.file||block.repo_file===anchor.file||(!!anchor.file&&String(anchor.file).endsWith('/'+block.file));
  const fileBlocks=byRepo.length?byRepo:anchor.file?blocks.filter(sameFile):[];
  const quoted=anchor.quote&&fileBlocks.find(block=>block.text.includes(anchor.quote));
  if(quoted)return quoted;
  if(anchor.line_start==null)return fileBlocks[0]||null;
  return fileBlocks.find(block=>block.line_start<=anchor.line_start&&block.line_end>=anchor.line_start)||null;
}
export function mountManuscript(project,{enc,views,forms,ui,outline,readerHome,discussion,inspect,activity,place,pageListen}){
  // the domain's own memory (moved out of the shell closure)
  let externalApplications=new Map(),
    historySync=Promise.resolve(),
    manuscript=null,
    manuscriptEditor=null,
    frameGeneration=0,
    frameSubscriptions=null,
    frameCounts={attached:0,disposed:0},sourceCompanion=null,companion=null,sourcePlace=null,sourceButton=null,readingFocus='writing';
  function syncConversation(open=ui.root.classList.contains('session-open')){if(!manuscript)return;const width=ui.$('[data-main]')?.clientWidth||globalThis.innerWidth||1280,foreground=!!companion&&open&&width<900;manuscript.dataset.conversationCompanion=foreground?'conversation':'reading';manuscript.dataset.sourceFocus=foreground?'writing':readingFocus;if(companion){companion.hidden=foreground;companion.inert=foreground;}if(sourceButton)sourceButton.textContent=foreground?'Show source instead':'Sources beside writing';}
  function preferSource(){if(ui.root.classList.contains('session-open')){const width=ui.$('[data-main]')?.clientWidth||globalThis.innerWidth||1280;if(width<900)discussion.open?.(false,{remember:false});}syncConversation();}
  const sourceWindow=()=>manuscript?.querySelector('iframe')?.contentWindow;
  // The idle poll tells the build owner which status projection it already holds (the owner's
  // summary_revision, which covers document revision, build identity, state and publication);
  // an unchanged answer is a few hundred bytes and no document read follows (G17). The token is
  // only sent while the walk's own document claims to be current (no stale held section).
  let buildSummaryRevision='';
  const manuscriptUpdates=createManuscriptRefresh({project,observe:()=>api('/authoring/build?project='+enc+'&view=summary'+((
    typeof buildSummaryRevision==='string'&&buildSummaryRevision&&typeof sourceWindow==='function'&&sourceWindow()?.walk?.sourceObservation?.(
    )?.current_revision)?'&known_revision='+encodeURIComponent(buildSummaryRevision):''),undefined,{allowStateError:true}),read:()=>api(
    '/walk/doc?corpus='+enc),onObservation:value=>{if(typeof value?.summary_revision==='string')buildSummaryRevision=value.summary_revision;},
    getWalk:()=>sourceWindow()?.walk,isCurrent:()=>ui.root.isConnected!==false,visible:()=>views.current()==='manuscript'&&
    document.visibilityState!=='hidden',status:ui.notice,clearStatus:ui.clearRefresh});
  manuscriptUpdates.start();
  pageListen(window,'focus',()=>{manuscriptUpdates.check();});
  pageListen(document,'visibilitychange',()=>{if(document.visibilityState==='visible')manuscriptUpdates.check();});
  const saved=()=>{if(manuscriptEditor?.hasDraft())throw Error('Save or discard your TeX draft before applying another revision.');
    const edits=sourceWindow()?.walk?.editState?.();if(edits&&(edits.dirty||edits.parked))throw Error(
    'Save or discard the standing manuscript edits before applying another revision.');};
  function rememberApplication(application){
    if(!application?.id||(!application.edits?.length&&!application.undo_ref&&!(application.kind==='source-edits'&&
      application.detail)))return Promise.resolve();externalApplications.set(application.id,application);
    return flushExternalHistory();
  }
  function flushExternalHistory(){
    const walk=sourceWindow()?.walk;if(!walk?.ready())return Promise.resolve();
    historySync=historySync.catch(()=>{}).then(async()=>{for(const [id,application]of externalApplications){if(
      application.undo_ref)walk.rememberExternalTransaction(application);else if(application.kind==='source-edits')walk.rememberExternalApplication({
      ...application,project});else for(const [index,edit]of application.edits.entries())await walk.rememberExternalChange({...edit,edit_id:String(
      index),application_id:id,quiet:true});externalApplications.delete(id);}});return historySync;
  }
  async function openBoundSource({sourceRead,source,file},intent){
    place.remember(intent);
    const precise=source?.precision==='EXACT_HEADING'&&source.heading?.file===file;
    const basis=source?.basis?.[file];
    if(!basis)throw Error('This source link has no inspected basis. Refresh the reader-plan item.');
    await views.show('manuscript',false);
    if(views.current()!=='manuscript')return;
    if(precise){
      const row={...source.heading,file,basis,source_read:sourceRead,shared_occurrences:(source.source_orders||source.heading?.source_orders)?.length||1};
      return outline.openOccurrence(row,{remember:false});
    }
    await manuscriptEditor.openSource(file,undefined,false,basis);
    ui.notice(source?.precision==='INFERRED'?'Inspecting a suggested file; no passage binding is established.':'Inspecting the linked file; no specific heading is established.');
  }
  async function openPlacement(location){
    if(!forms.leave())return;
    const id=location.id||location.section_id;
    if(!id)throw Error('This placement has no reader-plan identity.');
    const detail=await api(structureReadURL(project,{view:'detail',section_ids:[id]}));
    if(detail.project!==project)throw Error('The reader-plan response belongs to another project.');
    const section=detail.sections?.find(item=>item.id===id);
    if(!section)throw Error('This reader-plan item is unavailable.');
    const reads=section.source?.source_reads||[];
    if(section.source?.precision==='EXACT_HEADING'&&reads.length===1)return openBoundSource({sourceRead:reads[0],source:section.source,file:reads[0].payload.files[0]});
    await readerHome.openSection(id);
    ui.notice(section.source?.precision==='FILE_ONLY'?'This item links a file. Choose a source heading for a precise passage link.':'Choose or correct this item’s source link.');
  }
  async function manuscriptReady(){
    await views.show('manuscript',false);
    // a refused or superseded show (M5): the shell has said why, or the person went elsewhere; readiness is
    // null, as waitForManuscript answers for a view that is not current, and no frame of an unrendered host is touched
    if(views.current()!=='manuscript'||!manuscript)return null;
    manuscriptEditor?.showWrite();
    const frame=manuscript.querySelector('iframe'),version=views.generation();
    return waitForManuscript({getWalk:()=>frame.contentWindow?.walk,isCurrent:()=>views.current()==='manuscript'&&version===views.generation()&&frame.isConnected,
      onPending:()=>{ui.notice('The manuscript is still loading. This request will continue when it is ready.');ui.$('[data-notice]').dataset.manuscriptWait=String(version);},
      onSettled:()=>{if(ui.$('[data-notice]').dataset.manuscriptWait===String(version))ui.notice('');}});
  }
  async function inspectPassage(anchor,{edit=false}={}){
    place.remember();const walk=await manuscriptReady();if(!walk)return;if(anchor?.show_changes){walk.clearProposal({refreshAuthorOverlay:false});
      await walk.setAuthorChanges(true,{refresh:false});await walk.refreshAuthorChanges({...(anchor.correction_id?{id:anchor.correction_id}:{
      file:anchor.file}),focus:true,force:true});return;}const blocks=walk.blocks();if(anchor?.proposal_edit_id&&walk.focusProposal(
      anchor.proposal_edit_id))return;const hit=manuscriptPassageTarget(blocks,anchor);
    if(hit){walk.jumpToBlock(hit.id);if(edit){const target=hit.kind==='figure'?blocks.find(block=>block.caption_of===hit.id)||hit:hit;if(
      !walk.editBlock(target.id,{exact:true}))walk.flip(target.id);}return hit;}else ui.notice('This source location is not in the currently selected manuscript.',true);
  }
  // THE FRAME LIFETIME (S2 F2). Each load of the walk frame owns one named set of walk.on subscriptions and
  // their walk.off disposers: a new load first disposes the previous set, a handler of an earlier load is
  // inert (its generation is no longer current), and destroy() disposes the set and detaches the frame.
  function frameHandlers(){
    return [
      ['section',()=>{discussion.session().scope();outline.paintLocation();}],
      ['attention',()=>{discussion.session().scope();outline.paintLocation();}],
      ['bank',event=>{if(event.applied&&ui.$('[data-notice]').dataset.manuscriptChange)ui.notice('');}],
      ['ready',(...args)=>outline.render(...args)],
      ['ready',()=>manuscriptUpdates.check()],
      ['edit-settled',()=>{manuscriptUpdates.settled();manuscriptEditor?.changed();}],
      ['bank',event=>{if(event.applied){manuscriptUpdates.settled();manuscriptEditor?.changed();}}],
      ['ready',()=>discussion.session().guard(flushExternalHistory)],
      ['document',()=>{outline.render();discussion.session().scope();}],
    ];
  }
  function disposeFrame(){
    if(!frameSubscriptions)return;
    for(const [name,handler] of frameSubscriptions.handlers)frameSubscriptions.walk.off?.(name,handler);
    frameCounts.disposed+=frameSubscriptions.handlers.length;frameSubscriptions=null;
  }
  function attachFrame(){
    disposeFrame();
    const generation=++frameGeneration,walk=sourceWindow()?.walk;
    if(walk){
      const handlers=frameHandlers().map(([name,handler])=>[name,(...args)=>{if(generation===frameGeneration)return handler(...args);}]);
      for(const [name,handler] of handlers)walk.on(name,handler);
      frameSubscriptions={walk,handlers};frameCounts.attached+=handlers.length;
    }
    outline.render();discussion.session().scope();discussion.session().guard(flushExternalHistory);
  }
  async function renderManuscript(host){
    if(!manuscript){
      manuscript=E('div');manuscript.style.height='100%';
      manuscript.className='writing-native-surface';
      const tools=E('nav','','writing-native-tools'),sources=E('button','Sources beside writing'),returnWriting=E('button','Back to writing'),returnSource=E('button','Return to source');sourceButton=sources;sources.type=returnWriting.type=returnSource.type='button';sources.dataset.control='writing:sources';returnWriting.className=returnSource.className='writing-focus-switch';returnWriting.hidden=returnSource.hidden=true;
      const focusWriting=async()=>{if(views.current()!=='manuscript')return;const generation=views.generation(),frame=manuscript.querySelector('iframe'),intent=document.activeElement;readingFocus='writing';syncConversation();returnWriting.hidden=true;returnSource.hidden=!companion;const isCurrent=()=>views.current()==='manuscript'&&views.generation()===generation&&manuscript?.querySelector('iframe')===frame&&manuscript.dataset.sourceFocus==='writing'&&(document.activeElement===intent||document.activeElement===document.body);if(sourcePlace)await manuscriptEditor?.restorePlace(sourcePlace,{isCurrent});};
      returnWriting.onclick=focusWriting;returnSource.onclick=()=>{sourcePlace=manuscriptEditor?.capturePlace();preferSource();readingFocus='source';syncConversation();returnWriting.hidden=false;returnSource.hidden=true;companion?.querySelector('h3')?.focus?.({preventScroll:true});};
      sources.onclick=async()=>{if(companion&&manuscript.dataset.conversationCompanion==='conversation'){preferSource();readingFocus='source';syncConversation();returnWriting.hidden=false;returnSource.hidden=true;companion.querySelector('h3')?.focus?.({preventScroll:true});return;}if(companion){sourceCompanion?.destroy();sourceCompanion=null;companion.remove();companion=null;manuscript.classList.remove('has-source-companion');syncConversation();returnWriting.hidden=returnSource.hidden=true;readingFocus='writing';syncConversation();await focusWriting();sources.focus({preventScroll:true});return;}sourcePlace=manuscriptEditor?.capturePlace();companion=E('aside','','writing-source-companion');companion.setAttribute('aria-label','Sources beside writing');manuscript.append(companion);manuscript.classList.add('has-source-companion');preferSource();readingFocus='source';syncConversation();returnWriting.hidden=false;returnSource.hidden=true;const {mountWritingSources}=await import('./workspace-material.mjs');if(!companion||views.current()!=='manuscript')return;const companionHost=companion,mounted=await mountWritingSources(companionHost,{project,request:api,isCurrent:()=>views.current()==='manuscript',onClose:()=>sources.onclick(),onReading:()=>{if(companion===companionHost){readingFocus='source';syncConversation();returnWriting.hidden=false;returnSource.hidden=true;}}});if(companion!==companionHost){mounted?.destroy();return;}sourceCompanion=mounted;const focused=document.activeElement;if(focused===sources||focused===document.body||focused?.isConnected===false)companion?.querySelector('h3')?.focus?.({preventScroll:true});};tools.append(sources,returnWriting,returnSource);manuscript.append(tools);
      const canvas=E('section','','writing-editor-host');manuscript.append(canvas);const frame=E('iframe');frame.title='Manuscript reader and editor';
      frame.src='/walk?workspace=writing&corpus='+enc+'&embedded=1&editor=workbench';canvas.append(frame);host.append(manuscript);
      manuscriptEditor=createManuscriptEditor(canvas,{project,frame,request:api,status:ui.notice,onAttention:()=>discussion.session().scope(),
        onChanged:()=>{manuscriptUpdates.invalidate();outline.render();},onOpenArtifact:inspect.projectArtifact,
        onHistory:async scope=>{place.remember();await activity.openOwner(scope);ui.$('[data-return-reader]').hidden=false;
          ui.$('[data-return-reader]').textContent='Back to manuscript';}});
      frame.onload=attachFrame;
    }
    manuscript.hidden=false;sourceWindow()?.dispatchEvent(new Event('resize'));outline.render();
    await manuscriptUpdates.check();await manuscriptEditor?.observe();syncConversation();
  }
  return {
    render:renderManuscript,editor:()=>manuscriptEditor,host:()=>manuscript,currentWindow:sourceWindow,sourceWindow,
    ready:manuscriptReady,saved,inspectPassage,openPlacement,openBoundSource,rememberApplication,flushExternalHistory,
    updates:manuscriptUpdates,syncConversation,returnFromConversation:async({isCurrent=()=>true}={})=>{if(views.current()!=='manuscript'||!isCurrent())return false;if(readingFocus==='source'&&companion&&!companion.hidden){const heading=companion.querySelector('h3');if(heading&&isCurrent()){heading.focus({preventScroll:true});return true;}}const place=manuscriptEditor?.capturePlace();if(!place||!isCurrent())return false;await manuscriptEditor.restorePlace(place,{isCurrent});return document.activeElement!==document.body;},
    capturePlace:()=>manuscriptEditor?.capturePlace(),restorePlace:value=>manuscriptEditor?.restorePlace(value),
    hasDraft:()=>!!manuscriptEditor?.hasDraft(),observe:()=>manuscriptEditor?.observe(),
    // the frame's lifetime as diagnostics and the lifetime tests read it: the generation, the live subscriptions
    // and the cumulative attached/disposed counts (attached - disposed = live whenever every set was disposed)
    lifetime:()=>({generation:frameGeneration,subscriptions:frameSubscriptions?.handlers.length||0,...frameCounts}),
    destroy:()=>{sourceCompanion?.destroy();disposeFrame();manuscriptUpdates.destroy();manuscriptEditor?.destroy?.();
      const frame=manuscript?.querySelector('iframe');if(frame)frame.onload=null;manuscript?.remove();manuscript=null;manuscriptEditor=null;},
  };
}
