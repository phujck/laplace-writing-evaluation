// WORKSPACE ACTIVITY (M5 S2 F1). Purpose: the Review & notes and History views of the shell: the Review panel
// (workspace-review's mountReview, kept mounted across visits like the manuscript frame, with its pending
// correction focus), the History view (workspace-history's activity controller and the legacy history list)
// with its memory (scope, tab, expanded entry, offsets) kept in sessionStorage, opening an owner's history
// from another view, and opening the project's proposals in Review. Ownership: notes, corrections, proposals
// and history records belong to their owners; this controller owns only the review panel and controller, the
// history controller and memory, and the overview attention that scoped History. Public contract:
// mountActivity(project, services) -> {renderHistory(host), openOwner(scope), openProposals(options),
// setReviewActive(active), reviewHost(), resumeReview(version), mountReview(host), forgetReview(),
// historyContext(task), scopeHistory(options), overviewAttention(), releaseHistory(), destroyHistory(),
// destroyReview()}. Services: views, forms, ui, manuscript (the frame), research, argument, proposals, work
// (open), inspect, discussion, workState, place (the reader return), start (the history memory the shell
// read). Lifetime: releaseHistory() captures the memory and destroys the controller when History is left.
import {E,title} from './workspace-dom.mjs';
import {projectRequest as api} from "/shared/workspace-session.mjs";
import {artifactReaderOptions} from "/shared/workspace-material.mjs";
import {manuscriptPassageTarget} from './workspace-manuscript.mjs';
import {mountReview} from "/shared/workspace-review.mjs";

// Where a History manuscript target goes, decided BEFORE any view transition (root B1):
// an UNPROVED target is known from the owner's binding alone and opens the record where the
// reader stands; a bound path is placed against the loaded manuscript's blocks when they are
// already at hand, and only an unloaded manuscript needs loading to prove placement.
export function historyManuscriptRoute(target={},blocks=null){
  const file=target.repo_file||target.file;
  if(!/\.tex$/i.test(file||''))return {route:'artifact',file};
  if(target.binding==='UNPROVED')return {route:'record',state:'UNPROVED',file,
    notice:'This saved version records '+file+' without a proven checkout binding. Its saved text is shown from the record; no current file is guessed.'};
  if(!Array.isArray(blocks))return {route:'load',file};
  if(manuscriptPassageTarget(blocks,target))return {route:'passage',file};
  return {route:'record',state:'ABSENT',file,
    notice:'The bound source '+file+' is not in the currently selected manuscript. The record\'s saved text is shown instead.'};
}
export function historyScopeForView(view,{attention={},block=null,logical=null}={}){
  attention=attention||{};
  // The manuscript's own coordinate (M5-I1): a block that names its checkout path (`repo_file`,
  // the walk's src.repo_file) is scoped by that path, which is the identity the history owner
  // records on BOUND targets; a block without one keeps its manuscript-relative file, which
  // the owner resolves once through the selected source (author_history.file_scope). The
  // label stays the file the author sees.
  if(view==='manuscript'&&block?.file)return {file:block.repo_file||block.file,label:attention.label||block.file};
  if(view==='structure'&&logical?.id)return {node:logical.id,label:title(logical)};
  if(view==='research'){if(attention.result_id)return {result_id:attention.result_id,label:attention.label||attention.result_id};
    const node=attention.concept_id||attention.claim_id;if(node)return {node,label:attention.label||node};}
  // S3 dispatch-pane: "View in History" on a project-work dispatch card sets
  // `overviewAttention` before switching views; `row` is author_history's own filter key
  // (workspace-history.mjs `historyScope`), so the project-work pane and the History pane
  // agree on what a dispatch's activity is without a second lookup.
  if(['overview','work','material','turns'].includes(view)&&attention.row)return {row:attention.row,label:attention.label||attention.row};
  return {};
}
export function historyTargetUnavailable(target={}){
  if(target.kind==='profile')return target.read_handle?null:'No exact profile owner handle was recorded.';
  if(target.kind==='artifact')return target.artifact_path&&
    target.scope?target.availability==='missing'?'This recorded file is missing. Inspect the saved record here.':null:'No exact scoped artifact handle was recorded.';
  if(target.kind==='manuscript')return target.file?null:'No exact source path was recorded.';
  if(['concept','research','literature','note'].includes(target.kind))return target.id?null:'No exact object identity was recorded.';
  if(target.kind==='formal')return target.concept_id?null:'This receipt has no bound canonical formal target; inspect the receipt here or its linked result.';
  return 'This historical owner has no direct reader link.';
}
export function mountActivity(project,{enc,start,views,forms,ui,manuscript,research,argument,proposals,work,inspect,discussion,workState,place}){
  // the domain's own memory (moved out of the shell closure)
  let historyController=null,
    historyMemory=start,
    reviewCorrection=null,
    historyStorageWarning=false,
    reviewPanel=null,
    reviewController=null,
    reviewReady=null,
    overviewAttention=null;
  async function openProjectReview({turnId}={}){if(await views.show('review')!==false)await reviewController?.showProposals(turnId);}
  async function openOwnerHistory(scope){overviewAttention=scope;historyMemory={...(historyMemory||{}),scope,...(scope.file?{
    overview_expanded:false}:{}),session_id:scope.session_id||'',activityTab:scope.file||scope.node||scope.result_id||scope.row?'changes':'trace',
    analytics:{projection:'trace',scope:{session_id:scope.session_id,turn_id:scope.turn_id,work_id:scope.work_id}},offset:0,as_of:'',expanded:null,
    scrollTop:0};await views.show('history',false);}
  async function openAllHistory(){if(!forms.leave())return false;historyMemory={scope:{},category:'',activityTab:'changes',offset:0,as_of:'',expanded:null,scrollTop:0};return views.show('history',false);}
  async function openHistoryTarget(target,intent){
        if(!forms.leave())return;
        if(target.kind==='manuscript'){
          // An UNPROVED historical file, or one not in the selected manuscript, opens the
          // record's saved text instead of guessing a same-named file (G1). The route is
          // decided before any view transition, so the record inspector opens over History
          // and closing it leaves the filter and expanded row where they were (root B1).
          const openRecord=async route=>{if(!target.history_id){ui.notice(route.notice||'This source location is not in the currently selected manuscript.',true);return;}
            ui.notice(route.notice);const {readAnalyticsRecord}=await import('/shared/workspace-analytics.mjs');await readAnalyticsRecord({
              operation:'author_history',payload:{view:'record',id:target.history_id},http:{method:'GET',
              url:'/authoring/history?'+new URLSearchParams({project,view:'record',id:target.history_id})}},{project,request:api,isCurrent:()=>
              ui.root.isConnected!==false,onOpen:()=>{}});};
          let route=historyManuscriptRoute(target,manuscript.sourceWindow()?.walk?.blocks?.({text:false})||null);
          // the return place is remembered with the record action's own intent (M5-R2), before any transition and
          // never for the record inspector, which opens over History without leaving it
          if(route.route==='artifact'){place.remember(intent);await inspect.projectArtifact(route.file,target.label||route.file);return;}
          const loading=route.route==='load';
          if(loading){
            // Only a bound path with no loaded manuscript needs the manuscript to prove placement.
            place.remember(intent);const walk=await manuscript.ready();if(!walk)return;route=historyManuscriptRoute(target,walk.blocks({text:false}));}
          if(route.route==='passage'){if(!loading)place.remember(intent);await manuscript.inspectPassage({...target,...(target.correction_id?{show_changes:true}:{})});}
          else await openRecord(route);}
        else{place.remember(intent);
        if(target.kind==='profile')await inspect.ownerRead(target.read_handle,target.label||'Profile preferences');
        else if(target.kind==='artifact'){const options=artifactReaderOptions({id:target.id,path:target.artifact_path,scope:target.scope,
          recorded_revision:target.recorded_revision,human_read:target.human_read},{project});await inspect.projectArtifact(options.path||
          target.artifact_path,target.label||target.artifact_path,options);}
        else if(target.kind==='concept'){await argument.openConcept(target.id);}
        else if(target.kind==='research')await research.openEvidence(target.id,{fromHistory:true});
        else if(target.kind==='formal'){await research.openFormal(target.concept_id);}
        else if(target.kind==='literature'){await research.openSource({key:target.id,source_index:0,offset:0,mode:'source'});}
        else if(target.kind==='note'){reviewCorrection=target.id;await views.show('review',false);}}
  }
  async function openHistoryConversation(target){if(typeof target?.session_id!=='string'||!target.session_id||target.project&&target.project!==project)throw Error('No conversation destination was recorded for this project.');discussion.open(true);return discussion.session().openConversation(target.session_id);}
  async function renderReview(host){
    const correctionId=reviewCorrection;reviewCorrection=null;
    return mountReview(host,{project,correctionId,proposalController:discussion.projectReview,request:api,status:ui.notice,
      onReadTurn:discussion.savedTurn,onOpenPassage:((...args)=>manuscript.inspectPassage(...args)),onReviewProposal:((...args)=>proposals.review(
      ...args)),onDiscuss:(text,anchorOrMode)=>{discussion.talk(text,typeof anchorOrMode==='string'?anchorOrMode:'work',anchorOrMode&&
      typeof anchorOrMode==='object'?{files:anchorOrMode.file?[anchorOrMode.file]:[],quote:anchorOrMode.quote,anchor:anchorOrMode}:undefined);},
      onDirty:value=>{if(views.current()==='review')forms.setDirty(value);}});
  }

  // ACTIVITY (M5 C5): Changes is the unconditional default (the owner's activity page with its
  // category filter, manuscript by default); Graphs (session analytics) opens only when chosen
  // or when a remembered analytics scope asks for it. The former overview-by-default is retired.
  async function renderHistory(host){
    if(historyMemory?.activityTab!=='trace'||historyMemory?.expanded||['file','node','result_id','row'].some(key=>historyMemory?.scope?.[key]))return renderLegacyHistory(host);
    const {mountSessionAnalytics}=await import('/shared/workspace-analytics.mjs');if(!host.isConnected)return;
    const analyticsHost=E('section');host.replaceChildren(analyticsHost);const controller=await mountSessionAnalytics(analyticsHost,{project,
      request:api,scope:historyMemory?.analytics?.scope||{session_id:historyMemory?.session_id},initialProjection:historyMemory?.analytics?.projection,
      onState:value=>{historyMemory={...(historyMemory||{}),analytics:value,activityTab:'trace'};},onLibrary:()=>views.show('turns'),
        onLegacy:filters=>{historyController?.destroy();historyMemory={...(historyMemory||{}),...(filters||{}),activityTab:'changes',expanded:null,
        offset:0};return renderLegacyHistory(host);},
      onConversation:target=>{if(target.project!==project)throw Error('This conversation belongs to another project.');return discussion.conversation(
        target.id);},onTurn:target=>{if(target.project!==project)throw Error('This turn belongs to another project.');return discussion.savedTurn(
        target.id);},onWork:target=>{if(target.project!==project)throw Error('This work belongs to another project.');return work.open(target.id);}});
    if(!host.isConnected||!analyticsHost.isConnected){controller.destroy();return;}historyController={capture:()=>({...historyMemory,
      analytics:controller.capture()}),destroy:()=>controller.destroy(),refresh:()=>controller.refresh()};
  }
  async function renderLegacyHistory(host){
    host.replaceChildren();const legacyHost=E('section');host.append(legacyHost);const openGraphs=()=>{historyController?.destroy();historyMemory={
      ...(historyMemory||{}),activityTab:'trace',expanded:null,scope:{}};return renderHistory(host);};
    // Keep older running engines usable while the additive History route/assets
    // await their ordinary idle update; an unavailable tab has its own retry.
    const {mountHistory}=await import('/shared/workspace-history.mjs');if(!host.isConnected)return;
    const controller=await mountHistory(legacyHost,{project,request:api,status:ui.notice,initialState:historyMemory||{},renderText:inspect.savedMarkdown,onGraphs:openGraphs,
      onState:value=>{historyMemory={...value,activityTab:'changes'};try{sessionStorage.setItem('laplace:history:'+project,JSON.stringify(value));
        }catch{if(!historyStorageWarning){historyStorageWarning=true;ui.notice('History position cannot be retained after reload in this browser.',
        true);}}discussion.session().scope();},
      canOpenTarget:historyTargetUnavailable,
      onOpenTarget:openHistoryTarget,
      onOpenConversation:openHistoryConversation,
      onDiscuss:item=>{discussion.open(true);discussion.talk(
        'Inspect the exact project history record '+item.id+
        ' with author_history view=activity. Explain what changed, who recorded it, and how its recorded evidence compares with current source. Preserve the distinction between byte identity and scientific validity.');
        }
    });if(!host.isConnected||!legacyHost.isConnected){controller.destroy();return;}historyController=controller;
  }
  return {
    renderHistory,openTarget:openHistoryTarget,openConversation:openHistoryConversation,openAll:openAllHistory,openOwner:openOwnerHistory,openProposals:openProjectReview,
    // the Review panel stays mounted across visits; show() asks it to hide, resume or mount
    setReviewActive:active=>reviewController?.setActive(active),reviewHost:()=>reviewPanel,
    resumeReview:async version=>{reviewController=await reviewReady;if(version!==views.generation())return;reviewController.setActive(true);
      if(reviewCorrection){const id=reviewCorrection;reviewCorrection=null;await reviewController.focusCorrection(id);}
      forms.setDirty(!!reviewController.hasDraft);},
    mountReview:async body=>{reviewPanel=body;reviewReady=renderReview(body);reviewController=await reviewReady;
      reviewController.setActive(views.current()==='review');forms.setDirty(views.current()==='review'&&reviewController.hasDraft);},
    forgetReview:()=>{reviewPanel=null;reviewReady=null;},
    historyContext:task=>{const scope=historyMemory?.scope||{};return {surface:'review',label:historyMemory?.expanded?(historyMemory.attention?.id===historyMemory.expanded
      ?historyMemory.attention.label:'Selected history entry'):'History'+(scope.label?' · '+scope.label:''),task_id:task?.id,section_ids:[],
      ...(scope.file?{selection:{files:[scope.file]}}:{})};},
    // entering History from another view scopes it to what that view was showing
    scopeHistory:({from,attention,block,logical})=>{historyMemory={...(historyMemory||{}),scope:historyScopeForView(from,{attention,block,logical}),
      offset:0,as_of:'',expanded:null,scrollTop:0};},
    overviewAttention:()=>overviewAttention,
    releaseHistory:()=>{if(historyController){historyMemory=historyController.capture();historyController.destroy();historyController=null;}},
    destroyHistory:()=>{historyController?.destroy();historyController=null;},
    destroyReview:()=>{reviewController?.destroy();},
  };
}
