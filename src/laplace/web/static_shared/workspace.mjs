import {readWorkflowConversationAction,workflowReturnURL} from './workflow-port.mjs';
// THE WRITING WORKSPACE SHELL (M5). Purpose: the one page of a project: top bar (Workspace
// menu, title, context strip with the Work chip and Back to place, Focus, Help, Conversation),
// navigation (fixed, compact or drawer by width: navLayout), the main region that mounts one view
// at a time (Home, Work, Material, Activity, Settings, Argument & evidence, Reader plan, Research,
// Manuscript, Review & notes, Figures & output) and the conversation column. Ownership: every
// view's content belongs to its module and owner (workspace-work, workspace-spine,
// workspace-history, workspace-material, workspace-app/project, concept-explorer, the walk in
// its iframe, workspace-review, workspace-output); the conversation to workspace-session; the
// help layer to workspace-help (areas from /authoring/help, read once per session and verified
// by schema and version); this shell owns navigation, the context strip, view memory, the return
// place, the bridge to the walk (createBridgeLedger) and the help door. Public contract:
// mountWorkspace(root, options) -> {show, session, context, back, destroy}; the view helpers
// (canonicalWorkspaceView, NAV_LABELS, navLayout, manuscriptOutlineTree/Position,
// plannedManuscriptHeading, researchBindingCandidates). Entry rules (plan §3): a cold entry
// opens with the conversation closed unless conversation=open or session= is present. Keyboard:
// ? opens help outside a text field; Esc closes the topmost of cue, help, inspector, form.
// Currentness: each view reads its owner on show; memories are captured per view and never
// re-read for a label. Storage: sessionStorage/localStorage keys named laplace:* per concern
// (nav closed NAV_CLOSED_KEY, conversation width/open, history, reader-plan and argument
// memories, learning progress through workspace-journeys). Retired (C2/C11): the Dependencies
// view (alias to Material), the Conversations nav entry (the library), laplace:guide (migrated).
import {preparedWorkSubmission,preparedWorkReceipt,renderPreparedWork,renderPreparationFailure} from './prepared-work.mjs';
import {createWorkspaceReturn} from './workspace-interaction.mjs';
import {presentationStyles} from './workspace-presentation.mjs';
import {resolutionFinalizationSubmission,validateResolutionFinalization,resolutionPrepareSubmission,validateResolutionPreparation,
  candidateApplicationSubmission} from './proposal-resolution.mjs';
import {inspectArchitecturePrior,readerReviewSubmission,showReaderDialog} from './reader-state.mjs';
import {qualifiedOwnerHTTP,passageHistoryRead} from './writing-owner-read.mjs';
import {createBridgeLedger,installWalkBridge,createProposalDecisionHandler} from './workspace-bridge.mjs';
// THE BRIDGE LEDGER, the message fence and the route table live in workspace-bridge.mjs (M5 readability P2);
// they are re-exported here so existing consumers keep importing them from the shell.
export {UNKNOWN_PRODUCER_MESSAGES,HANDLED_BRIDGE_MESSAGES,UNKNOWN_SAMPLE_LIMIT,createBridgeLedger,messageBytes} from './workspace-bridge.mjs';
import {savedActionPlanPublication,planPublicationDisposition} from './plan-publication.mjs';
import {mountReaderPlan,structureReadURL,spineReadURL,inspectSourceOccurrence,outlineOccurrence,boundPlanHeading,editReaderPlanItem} from './workspace-spine.mjs';
import {sourceEffectDisposition,requireSourceCompletion,sourceEffectFromError,savedActionSourceEffect} from './source-effect.mjs';
import {createManuscriptEditor,hasStoredSourceDraft} from './manuscript-editor.mjs';
import {mountOperatorWork,workCountSummary,operatorHTTP} from '/shared/workspace-work.mjs';
import {appLink,bindAppLink} from '/shared/workspace-app.mjs';
import {mountMaterial,terminalWork,mountStorage,openSavedTurn,workspaceViewAvailable,artifactReaderOptions} from '/shared/workspace-material.mjs';
import {openArtifact as openEvidenceArtifact} from '/shared/writing-artifact.mjs';
import {sharedInspector} from '/shared/workspace-inspector.mjs';
import {createManuscriptRefresh,waitForManuscript,proposalScopeUnproven,proposalChangeRequest,fileOnlyManuscriptSelection,proposalActionAllowed,
  proposalReadURL,selectedProposalBody,proposalDecisionAcknowledged} from '/shared/manuscript-editing.mjs';
import {mountLiterature} from '/shared/workspace-literature.mjs';
import {mountReview,createProjectReview} from '/shared/workspace-review.mjs';
import {mountOutput} from '/shared/workspace-output.mjs';
import {mountWritingStyle as mountWritingStylePanel} from '/shared/workspace-writing-style.mjs';
import {profileGenerationIntent,profileGenerationCoordinates,inspectProfilePreferences} from './profile-preferences.mjs';
import {mountProjectSettings,mountProjectTitle} from '/shared/workspace-project.mjs';
import {renderConceptRecord,mountMathematicsEditor,displayLabel,scientificText,conceptChangeGuard} from '/shared/concept-reader.mjs';
import {mountConceptExplorer,mountArgumentOverview} from '/shared/concept-explorer.mjs';
import {WorkspaceSession,savedActionDestination,projectRequest as api,messageLinkParts,artifactHumanTarget,ownerHumanTarget,markdownProtectedRanges,
  settingsTruthText} from '/shared/workspace-session.mjs';
import {mountEvidence,focusResearchResult} from '/shared/writing-evidence.mjs';
import {openPdf} from '/shared/writing-pdf.mjs';
import {E,slug,title,field,area,section} from './workspace-dom.mjs';
import {pendingRead} from './pending-read.mjs';
import {mountChrome,navLayout} from './workspace-chrome.mjs';
import {mountFrame} from './workspace-frame.mjs';
export {NAV_LABELS,navLayout,NAV_CLOSED_KEY,SESSION_OPEN_KEY} from './workspace-chrome.mjs';
import {mountConversation} from './workspace-conversation.mjs';
import {createFrontendBasis,inspectRefreshCarry,acknowledgeRefreshCarry} from './frontend-basis.mjs';
import {mountWalkHandlers} from './workspace-walk-handlers.mjs';
import {mountContext} from './workspace-context.mjs';
import {mountReturns} from './workspace-returns.mjs';
import {mountHelpDoor} from './workspace-help-door.mjs';
import {mountInspection} from './workspace-inspection.mjs';
export {artifactMarkdownBlocks,artifactInlineParts,renderArtifactMarkdown} from './workspace-inspection.mjs';
import {mountNotices} from './workspace-notices.mjs';
import {mountHomeView} from './workspace-home.mjs';
import {mountWorkView} from './workspace-work-view.mjs';
import {mountActivity} from './workspace-activity.mjs';
export {historyManuscriptRoute,historyScopeForView,historyTargetUnavailable} from './workspace-activity.mjs';
import {mountFiguresView} from './workspace-figures.mjs';
import {mountProposalReview} from './workspace-proposals.mjs';
import {manuscriptPassageTarget,mountManuscript} from './workspace-manuscript.mjs';
export {manuscriptPassageTarget} from './workspace-manuscript.mjs';
import {mountReaderPlanView} from './workspace-reader-plan-view.mjs';
import {mountArgument} from './workspace-argument.mjs';
import {mountManuscriptOutlineView} from './workspace-manuscript-outline.mjs';
export {manuscriptOutlineTree,manuscriptOutlinePosition,plannedManuscriptHeading,currentManuscriptHeading,manuscriptHeadingDeletion,
  mountManuscriptOutline} from './workspace-manuscript-outline.mjs';
import {loadResearchNavigation,mountResearch} from './workspace-research.mjs';
export {researchBindingCandidates,researchNavigation,researchNavigationURL,loadResearchNavigation,saveResearchNavigation,
  focusHistoryResearchTarget} from './workspace-research.mjs';
export function canonicalWorkspaceView(view, structureMode='graph'){
  // entry aliases (M5 C2): the retired Dependencies view is Material at its shared bindings;
  // `turns` stays a routing word for the conversation library and is resolved by show()
  if(view==='dependencies')return 'material';
  return view==='structure'?(structureMode==='plan'?'reader-plan':'argument'):view;
}
export async function mountWorkspace(root,project){
  const legacy=document.querySelector('link[href="/shared/project-work.css"]');if(legacy)legacy.disabled=true;
  const enc=encodeURIComponent(project);const WORK_SUMMARY_READ='/work/state?project='+enc+'&view=summary&limit=12';let state,info={},structure=null,
    activeSection=null,currentView='overview',dirty=false;
  const initialQuery=new URLSearchParams(location.search);
  // A REFRESH CARRY (frontend-basis.mjs, P2S-R1) stays in this tab's storage until its owners restored it: adopted at boot
  // only when this page was issued from the basis the refresh intended (matched); restored by the visit (the first view
  // shown) and the Work view (a controller built from it), then exactly that record is acknowledged. Entry failure,
  // Retry and owner failure keep it; a different or unknown issued basis keeps it, says so, and offers explicit adoption.
  const refreshCarry=inspectRefreshCarry(project);
  let carryState=refreshCarry?(refreshCarry.status==='matched'?'adopting':'kept'):null;
  const carryPending=new Set(carryState==='adopting'?['visit']:[]);   // + 'work' once the Work view names the carried Work it must deliver
  const pageDiagnostics=initialQuery.get('diagnostics')==='1';   // developer counters in Settings (workspace-diagnostics.mjs)
  const researchStart=loadResearchNavigation(project,initialQuery);  let materialController=null,materialDraft=null;
  let localDocumentDraft=null;
  async function addLocalDocument(){
    const target=session.localDocumentTarget(),epoch=session.viewEpoch,intentRevision=session.intentRevision||0;
    const [{openLocalDocumentIntake},{createLocalDocumentDraft}]=await Promise.all([import('/shared/local-document-intake.mjs'),import('/shared/local-document-intake-port.mjs')]);
    if(shellDestroyed)return;localDocumentDraft??=createLocalDocumentDraft({project});
    return openLocalDocumentIntake({project,projectTitle:info?.title||project,request:api,draft:localDocumentDraft,returnTarget:target,isCurrent:()=>!shellDestroyed,
      onMaterial:async()=>{const rendering=show('material',false),version=loadVersion;await rendering;if(shellDestroyed||currentView!=='material'||loadVersion!==version)return null;const heading=$('[data-main]').querySelector('h2');if(heading)heading.tabIndex=-1;return {element:heading,isCurrent:()=>!shellDestroyed&&currentView==='material'&&loadVersion===version};},
      onUse:(read,label,original)=>{session.useLocalDocument(read,label,original||target,{epoch,intentRevision});chrome.openSession(true);const revision=session.intentRevision;return {element:session.find('[data-message]'),isCurrent:()=>!shellDestroyed&&session.viewEpoch===epoch&&(session.session||'')===(original||target).session_id&&session.intentRevision===revision};}});
  }
  let historyStart=null;try{historyStart=JSON.parse(sessionStorage.getItem('laplace:history:'+project)||'null');}catch{}if(initialQuery.get(
    'history_filter')){try{const {telemetryFilter}=await import('/shared/history-telemetry.mjs');historyStart={...(historyStart||{}),
    ...telemetryFilter(JSON.parse(initialQuery.get('history_filter'))),activityTab:'changes',expanded:null,offset:0};}catch{}}if(initialQuery.get(
    'history_record'))historyStart={...(historyStart||{}),activityTab:'changes',expanded:initialQuery.get('history_record'),offset:0,scope:{},as_of:''};
  const workspaceReturn=createWorkspaceReturn(researchStart.returnToResearch&&initialQuery.get('view')==='manuscript'?researchStart.returnPlace:null);
  let loadVersion=0,structureMode=initialQuery.get('structure')==='plan'?'plan':initialQuery.get('structure')==='concept'?'graph':'graph';
  const canGoBack=()=>currentView==='argument'&&argument.canGoBack();
  const navigationChanged=()=>window.dispatchEvent(new CustomEvent('laplace-workspace-navigation',{detail:{graphBack:canGoBack()}}));
  const leaveForm=()=>!dirty||materialController?.hasDraft||work.hasDraft()||confirm('Leave the unsaved form changes?');
  const surfaceLabels={work:'Tasks',material:'Sources',settings:'Settings',overview:'Home',structure:'Reader plan',
    argument:'Argument & evidence','reader-plan':'Reader plan',research:'Research',manuscript:'Writing',
    presentation:'Figures and publication',review:'Review and accumulated feedback',history:'Activity'};
  // ONE TOP BAR (plan §3, accepted): the Workspace menu (Projects, Workspace activity,
  // Workspace dependencies, App settings), the Menu door for the compact/drawer nav, the
  // project title, then the contextual group — current view label, the selected Work as a
  // chip with its Clear, and the one Back to … return — then Focus, Help and Conversation.
  // The separate context strip row is retired; the group lives in the bar.
  root.className='workspace';root.innerHTML=`<a href="#workspace-content" class="workspace-skip" data-skip-main data-control="nav:skip">Skip to content</a><header class="workspace-header"><details class="workspace-menu" data-workspace-menu data-control="workspace:menu"><summary aria-haspopup="true">Workspace</summary><div class="workspace-menu-list" role="menu"></div></details><button data-nav data-control="nav:menu" aria-label="Show or hide project views" aria-expanded="false">Menu</button><h1>Opening project…</h1><div class="workspace-context" data-context data-where aria-label="Where you are: project, view and the open item"><span class="context-view" data-view-label></span><span class="context-open" data-where-open hidden></span><button type="button" data-work-scope data-control="context:work" class="context-work" hidden title="Open pinned task context"></button><button type="button" data-clear-task data-control="context:clear" class="act context-clear" hidden>Clear task context</button><button type="button" data-return-reader data-control="context:return" class="act context-return" hidden></button></div><button data-focus data-control="manuscript:focus" hidden>Focus manuscript</button><button data-guide data-control="help:guide" aria-label="Help for this view" aria-pressed="false" title="Help for this view (?)">Help</button><button data-talk data-control="conversation:toggle" aria-expanded="true">Conversation</button></header><p data-notice class="work-status" role="status"></p><div class="workspace-layout"><nav class="workspace-nav" aria-label="Project views"></nav><main class="workspace-main" id="workspace-content" data-main tabindex="-1" aria-label="Project content"></main><aside data-session aria-label="Project conversation"></aside></div>`;
  root.querySelector('[data-skip-main]').onclick=event=>{event.preventDefault();root.querySelector('[data-main]')?.focus({preventScroll:true});};
  presentationStyles();
  // ONE FRAME (wave 9): the bar every page shares sits above this project's where-am-I line. It takes the shell's own
  // Help, Conversation and Workspace menu (now 'More', with Explore, dependencies, owners and App settings; Sessions,
  // Tasks, Workflows and Projects are plain links in the bar), so their data-control identities and handlers stay.
  // The frame is not optional: if it cannot be built the project does not open as the old app. The error is held and the
  // entry below reports it through the shell's one failure path (root.dataset.entry='failed', 'Project could not load').
  let frame=null,frameFailure=null;
  try{frame=mountFrame({project,title:project,request:api,more:root.querySelector('[data-workspace-menu]'),guide:root.querySelector('[data-guide]'),conversation:root.querySelector('[data-talk]'),
    onMenu:()=>root.querySelector('[data-nav]')?.onclick?.(),menuOpen:()=>!root.classList.contains('nav-closed')});root.insertBefore(frame.bar,root.querySelector('.workspace-header'));}
  catch(error){frame=null;frameFailure=new Error('The workspace frame could not be built: '+(error?.message||error));}
  const {$,notice:sayNotice,clearRefreshWarning,guard,actionAlert,button}=mountNotices(root);
  // A CONFIRMATION LEAVES (wave 7). A confirmation is marked where it is raised: confirm(text), which changed() uses after
  // a saved change. It is removed at the person's next click anywhere outside it, or after 8 seconds, whichever comes first.
  // Every other notice (an error, a warning, a refusal, a pending text) goes through notice() and stays until replaced, as
  // before. When a confirmation leaves, the main area is scrolled up by the line's height where it can be, so what was under
  // his pointer does not move.
  const CONFIRMATION_MS=8000;let confirmation=null;
  const dismissConfirmation=({leave=true}={})=>{const held=confirmation;if(!held)return;confirmation=null;clearTimeout(held.timer);
    held.doc?.removeEventListener?.('click',held.onClick,true);if(!leave)return;const line=$('[data-notice]');
    if(!line||line.textContent!==held.text||line.classList?.contains?.('error'))return;
    const before=line.getBoundingClientRect?.().height||0,main=$('[data-main]'),scrolled=main?.scrollTop||0;sayNotice('');
    const gone=before-(line.getBoundingClientRect?.().height||0);if(main&&gone>0&&scrolled>0)main.scrollTop=Math.max(0,scrolled-gone);};
  // the status line's height, for pages that size a pane to the room left under it (the Tasks page's open task: --notice-h)
  const noticeSize=globalThis.ResizeObserver&&$('[data-notice]')?new ResizeObserver(entries=>{for(const entry of entries)root.style?.setProperty?.('--notice-h',
    Math.round(entry.target.getBoundingClientRect().height)+'px');}):null;noticeSize?.observe($('[data-notice]'));
  const notice=(text,error=false,owner=null)=>{dismissConfirmation({leave:false});sayNotice(text,error,owner);};
  const confirmNotice=text=>{notice(text);if(!text)return;
    const doc=root.ownerDocument||globalThis.document,held={text:$('[data-notice]')?.textContent??String(text),doc};
    held.onClick=event=>{const line=$('[data-notice]');if(line&&event?.target&&line.contains?.(event.target))return;if(confirmation===held)dismissConfirmation();};
    held.timer=setTimeout(()=>{try{if(confirmation===held&&root.isConnected!==false)dismissConfirmation();}catch{}},CONFIRMATION_MS);held.timer?.unref?.();
    confirmation=held;doc?.addEventListener?.('click',held.onClick,true);};
  const inspector=sharedInspector();   // the doors adopt their own dialogs; the shell shares the instance for Back and the ledgers
  const bridge=createBridgeLedger();window.laplaceBridge=bridge.ledger;
  // THE SHELL'S PAGE LISTENERS (C12, 2026-10-15): every window/document listener the shell adds for its own lifetime
  // is added through pageListen, so one owner counts them (diagnostics=1) and workspace.destroy() removes them all.
  // The bridge's message listener is installWalkBridge's and the outline menu's are its controller's.
  const pageListeners=new Set(),listenerCounts={installed:0,removed:0};
  const pageListen=(target,type,fn,options)=>{target.addEventListener(type,fn,options);pageListeners.add({target,type,fn,options});listenerCounts.installed++;};
  const removePageListeners=()=>{for(const row of [...pageListeners]){pageListeners.delete(row);row.target.removeEventListener(row.type,row.fn,
    row.options);listenerCounts.removed++;}};
  // the snapshot the developer readout prints: owners' bounded counters only, copied, nothing retained
  const pageCounters=()=>{const byType={};for(const row of pageListeners)byType[row.type]=(byType[row.type]||0)+1;
    const memory=globalThis.performance?.memory;
    return {schema_version:'laplace.workspace-page-counters/1',read_at_ms:Math.round(globalThis.performance?.now?.()??0),
      bridge:{installed:walkBridge.installed,ledger:structuredClone(bridge.ledger)},
      page_listeners:{installed:listenerCounts.installed,removed:listenerCounts.removed,active:pageListeners.size,active_by_type:byType},
      inspector:{current:inspector.current?.kind||null,trail:inspector.trail.length,cache_entries:inspector.cacheSize,
        cache_limit:inspector.cacheLimit,cache_bytes:inspector.snapshotBytes},
      manuscript_frame:manuscriptView.lifetime(),help_open:help.isOpen(),cue_open:help.cueOpen(),dialogs_open:document.querySelectorAll?.('dialog[open]')?.length??null,
      memory:memory?{reported_by:'browser, coarse and quantised',used_bytes:memory.usedJSHeapSize,total_bytes:memory.totalJSHeapSize}:null};};
  const projectReview=createProjectReview({project,request:api,onReviewProposal:((...args)=>proposals.review(...args)),status:notice,isAlive:()=>root.isConnected});
  // ── THE SHELL'S NAMED SERVICES (S2 F1). Each domain controller receives only the few it uses: the
  // current view and navigation, form dirtiness and the leave guard, notices and controls, and the one
  // logical-structure read the shell holds. Domain memory lives in the controllers, not here.
  const views={current:()=>currentView,show,generation:()=>loadVersion,info:()=>info};
  const forms={dirty:()=>dirty,setDirty:value=>{dirty=value;},leave:leaveForm,guard,wire:wireForm,changed};
  // pending: the shell's V9 helper, so a view that issues a read can say for how long it has waited (pending-read.mjs)
  const ui={notice,confirm:confirmNotice,button,actionAlert,$,root,main:()=>$('[data-main]'),pending:pendingRead};
  const structures={get:()=>structure,set:value=>{structure=value;}};
  // ── the domain controllers, created once per mount ──
  const research=mountResearch(project,{enc,start:researchStart,views,forms,ui,structures,
    argument:{openConcept:(id,options)=>argument.openConcept(id,options)},
    manuscript:{ready:((...args)=>manuscriptView.ready(...args)),saved:(...args)=>manuscriptView.saved(...args),sourceWindow:(...args)=>
      manuscriptView.sourceWindow(...args),inspectPassage:(...args)=>manuscriptView.inspectPassage(...args),openPlacement:(...args)=>manuscriptView.openPlacement(...args)},
    place:{remember:((...args)=>returns.remember(...args)),workspaceReturn},discussion:{talk,session:()=>session},figures:{place:((...args)=>figures.place(...args))}});
  const outline=mountManuscriptOutlineView(project,{enc,views,ui,structures,
    manuscript:{editor:()=>manuscriptView.editor(),ready:((...args)=>manuscriptView.ready(...args)),saved:(...args)=>manuscriptView.saved(...args),
      sourceWindow:(...args)=>manuscriptView.sourceWindow(...args),rememberApplication:(...args)=>manuscriptView.rememberApplication(...args)},
    readerPlan:{openSection:(...args)=>readerHome.openSection(...args),openUnselected:async()=>{await readerHome.openUnselected();}},
    place:{remember:((...args)=>returns.remember(...args))}});
  const argument=mountArgument(project,{enc,initialQuery,ui,structures,
    views:{...views,mode:()=>structureMode,setMode:mode=>{structureMode=mode;},changed:navigationChanged,renderStructure},forms,
    workState:{get:()=>state,reload:((...args)=>work.reload(...args))},readerPlan:{plan:(...args)=>readerHome.plan(...args)},place:{capture:((
      ...args)=>returns.capture(...args)),restore:((...args)=>returns.restore(...args))},
    manuscript:{inspectPassage:(...args)=>manuscriptView.inspectPassage(...args),openPlacement:(...args)=>manuscriptView.openPlacement(...args)},
      research,work:{open:((...args)=>work.open(...args))},inspect:{savedMarkdown:((...args)=>inspection.savedMarkdown(...args))},
    discussion:{talk,session:()=>session}});
  const readerHome=mountReaderPlanView(project,{enc,initialQuery,ui,structures,forms,
    views:{...views,renderStructure},research,argument,work:{open:((...args)=>work.open(...args))},
    manuscript:{editor:()=>manuscriptView.editor(),sourceWindow:(...args)=>manuscriptView.sourceWindow(...args),openBoundSource:(...args)=>manuscriptView.openBoundSource(...args)},
    inspect:{ownerRead:((...args)=>inspection.ownerRead(...args)),projectArtifact:((...args)=>inspection.projectArtifact(...args))},
    discussion:{session:()=>session,open:((...args)=>chrome.openSession(...args)),conversation:openConversation,savedTurn:readSavedTurn,generateProfile},
    place:{remember:((...args)=>returns.remember(...args))}});
  const manuscriptView=mountManuscript(project,{enc,views,forms,ui:{...ui,clearRefresh:clearRefreshWarning},outline,readerHome,
    discussion:{session:()=>session,open:(...args)=>chrome.openSession(...args)},inspect:{projectArtifact:((...args)=>inspection.projectArtifact(...args))},activity:{openOwner:(...args)=>activity.openOwner(...args)},
    place:{remember:((...args)=>returns.remember(...args))},pageListen});
  const proposals=mountProposalReview(project,{views,ui,manuscript:manuscriptView,projectReview,inspect:{ownerRead:((...args)=>inspection.ownerRead(
    ...args)),projectArtifact:((...args)=>inspection.projectArtifact(...args)),savedMarkdown:((...args)=>inspection.savedMarkdown(...args))},
    discussion:{talk,session:()=>session,open:((...args)=>chrome.openSession(...args)),conversation:openConversation,savedTurn:readSavedTurn,
      generateProfile},workState:{get:()=>state,reload:((...args)=>work.reload(...args))}});
  const figures=mountFiguresView(project,{enc,views,forms,ui,manuscript:manuscriptView,research,inspect:{ownerRead:((...args)=>inspection.ownerRead(
    ...args)),projectArtifact:((...args)=>inspection.projectArtifact(...args)),savedMarkdown:((...args)=>inspection.savedMarkdown(...args))},
    discussion:{talk,session:()=>session,open:((...args)=>chrome.openSession(...args)),conversation:openConversation,savedTurn:readSavedTurn,
      generateProfile},workState:{get:()=>state,reload:((...args)=>work.reload(...args))}});
  const activity=mountActivity(project,{enc,start:historyStart,views,forms,ui,manuscript:manuscriptView,research,argument,proposals,work:{open:((...args)=>work.open(...args))},
    inspect:{ownerRead:((...args)=>inspection.ownerRead(...args)),projectArtifact:((...args)=>inspection.projectArtifact(...args)),savedMarkdown:((
      ...args)=>inspection.savedMarkdown(...args))},discussion:{talk,session:()=>session,open:((...args)=>chrome.openSession(...args)),
      conversation:openConversation,savedTurn:readSavedTurn,generateProfile,projectReview},
    workState:{get:()=>state,reload:((...args)=>work.reload(...args))},place:{remember:((...args)=>returns.remember(...args))}});
  const work=mountWorkView(project,{enc,initialQuery,views,forms,ui,workState:{get:()=>state,set:value=>{state=value;},summaryRead:WORK_SUMMARY_READ},
    inspect:{ownerRead:((...args)=>inspection.ownerRead(...args)),projectArtifact:((...args)=>inspection.projectArtifact(...args)),savedMarkdown:((
      ...args)=>inspection.savedMarkdown(...args))},discussion:{talk,session:()=>session,open:((...args)=>chrome.openSession(...args)),
      conversation:openConversation,savedTurn:readSavedTurn,generateProfile,projectReview},activity:activity,place:{remember:((...args)=>returns.remember(
      ...args))},context:(...args)=>contextOwner.read(...args),memory:carryState==='adopting'?refreshCarry.record.carried.work||null:null,
    onCarriedRestored:()=>carryRestored('work')});
  if(carryState==='adopting'&&work.carriedTarget())carryPending.add('work');
  const home=mountHomeView(project,{enc,views,forms,ui,workState:{get:()=>state,reload:(...args)=>work.reload(...args)},work,manuscript:manuscriptView,
    inspect:{ownerRead:((...args)=>inspection.ownerRead(...args)),projectArtifact:((...args)=>inspection.projectArtifact(...args)),savedMarkdown:((
      ...args)=>inspection.savedMarkdown(...args))},discussion:{talk,session:()=>session,open:((...args)=>chrome.openSession(...args)),
      conversation:openConversation,savedTurn:readSavedTurn,generateProfile},help:{openGuide:(...args)=>help.openGuide(...args)},diagnostics:{
      counters:pageCounters,page:pageDiagnostics},
    navigation:{refresh:()=>chrome.refreshNavigation()},activity:{openTarget:(...args)=>activity.openTarget(...args),openConversation:(...args)=>activity.openConversation(...args),openAll:()=>activity.openAll()}});
  const inspection=mountInspection(project,{discussion:{session:()=>session,generateProfile},work,home});
  const help=mountHelpDoor(project,{views,ui,shell:{destroyed:()=>shellDestroyed}});
  const returns=mountReturns(project,{views:{...views,setMode:mode=>{structureMode=mode;}},ui,labels:surfaceLabels,workspaceReturn,argument,readerHome,
    manuscript:manuscriptView,research});
  const contextOwner=mountContext({views,labels:surfaceLabels,work,activity,manuscript:manuscriptView,readerHome,argument,research,
    shellState:{mode:()=>structureMode,activeSection:()=>activeSection,structure:()=>structure,placeMemo:()=>walkHandlers.place()}});
  const walkHandlers=mountWalkHandlers(project,{enc,views:{...views,setCurrent:view=>{currentView=view;}},forms,ui,manuscript:manuscriptView,inspection,
    argument,research,work,readerHome,outline,returns,discussion:{session:()=>session,open:((...args)=>chrome.openSession(...args)),talk,savedTurn:readSavedTurn},
    focus:{manuscript:()=>chrome.focusManuscript(),restoring:()=>chrome.focusRestoring()},workspaceReturn,onPlace:()=>session?session.scope():paintWhere()});
  // ── end of the domain controllers ──
  let session;  session=mountConversation(project,{views,forms,ui,structures,workState:{get:()=>state,set:value=>{state=value;},summaryRead:WORK_SUMMARY_READ},
    initialQuery,contextOwner,projectReview,manuscript:manuscriptView,inspection,activity,work,home,
    discussion:{session:()=>session,open:((...args)=>chrome.openSession(...args)),savedTurn:readSavedTurn,addLocalDocument},
    orientation:{readingMoved:()=>paintWhere()}});   // every scope() repaints the where-am-I line: it follows the reading
  const chrome=mountChrome(project,{views,ui,discussion:{session:()=>session},help,initialQuery,pageListen,outline,onConversationLayout:open=>manuscriptView.syncConversation(open),onReadingReturn:options=>manuscriptView.returnFromConversation(options)});
  // the narrow menu inside a project lists the workspace's places first, then this project's pages (shown in the drawer
  // layout only; wider layouts keep the places in the bar)
  if(frame&&!frameFailure)try{$('.workspace-nav').prepend(frame.railPlaces(event=>{$('[data-guide]')?.onclick?.(event);}));}catch(error){frameFailure=new Error('The narrow menu could not list the places: '+(error?.message||error));}
  $('[data-return-reader]').onclick=guard(()=>returns.back());
  $('[data-clear-task]').onclick=guard(()=>work.request(null));
  $('[data-work-scope]').onclick=guard(()=>work.task()?work.open(work.task().id):undefined);
  // The guide observes the real shell; it never navigates or clicks for the person.
  let shellDestroyed=false;
  $('[data-guide]').onclick=guard(()=>help.toggle());
  // V3 the where-am-I line: project (the h1), then the view, then the open item in words. The open item is the manuscript
  // place the walk reported to the context owner; an open task is already named once, by the Task context control, so it
  // is not repeated here. Painted from the conversation's scope() (orientation.readingMoved), which show(), the walk's
  // section, attention and document events and the walk's place message all call, so 'Reading:' and this line move together.
  // V9 (a pending read says for how long) is owned by pending-read.mjs at each place that issues the read.
  function paintWhere(){const open=$('[data-where-open]');if(!open)return;let text='';try{const here=contextOwner.read()||{};
    if(currentView==='manuscript'&&here.label&&here.label!=='Manuscript')text=here.label;}catch{}
    if(open.textContent!==text)open.textContent=text;open.hidden=!text;}
  function talk(text='',mode='work',selection){chrome.openSession(true);session.compose(text,mode);session.pinMessageTarget({...contextOwner.read(),
    ...(selection?{selection}:{})});}
  function generateProfile(intent){
    if(intent.project!==project)throw Error('Open the explicitly selected project before generating its profile suggestion.');
    if(session.active||session.role==='review'||session.selectedSessionRecord?.dispatch_id){session.find('[data-mode]').value='work';if(
      !session.newConversation())throw Error('The conversation is still opening. Keep this profile request and try again when it is ready.');}
    talk(intent.instruction,'work');
  }
  // after a saved change: its message is a confirmation (it leaves); after is the changed view's own step once the page is
  // drawn and the confirmation said (Add task scrolls the new row into view)
  async function changed(message,{after=null}={}){dirty=false;await work.reload();await show(currentView,false);confirmNotice(message);try{await after?.();}catch{}}
  function wireForm(form,submit){form.classList.add('work-form');form.oninput=()=>{form.dataset.workspaceFormDirty='true';dirty=true;};
    form.onsubmit=guard(async()=>{await submit(Object.fromEntries(new FormData(form)));});}
  // THE VIEW CONTROLLERS of the views that repaint (S2 F2): each captures its own memory and is
  // destroyed once, by a view change or by workspace.destroy(); a destroyed controller ignores its
  // late reads. History/research/argument, which keep their memory across their own repaint, are
  // released by show() itself and by destroy().
  function releaseViewControllers(){
    readerHome.release();
    work.release();
    if(materialController){materialDraft=materialController.capture();materialController.destroy();materialController=null;}
    home.release();
  }
  async function show(view,ask=true,{reuseState=false}={}){
    if(shellDestroyed)return false;   // a destroyed shell never repaints (its root may already hold a replacement)
    const sharedBindings=view==='dependencies';   // the retired view's alias: Material at its shared bindings
    view=canonicalWorkspaceView(view,structureMode);
    if(view==='turns'){chrome.openSession(true);await session.browseConversations();return true;}
    if(ask&&!leaveForm())return false;
    session.setLibrary(false);session.expand(false);
    if(!workspaceViewAvailable(info,view)){notice((surfaceLabels[view]||
      view)+' is unavailable for the current project material. Open Material to inspect or add material.');return false;}
    activity.setReviewActive(view==='review');
    releaseViewControllers();
    if(ask){notice('');research.clearReturn();workspaceReturn.clear();}
    if(currentView==='manuscript'&&view!=='manuscript')manuscriptView.editor()?.capture();
    if(currentView==='manuscript'&&view!=='manuscript')outline.captureScroll();
    if(view==='history'&&ask&&currentView!=='history'){
      const walk=manuscriptView.sourceWindow()?.walk,position=walk?.readingPosition?.(),block=walk?.blocks?.({text:false})?.find(row=>row.id===position?.blockId);
      const logical=currentView==='argument'?argument.logical():null;
      const attention=currentView==='manuscript'?position:['overview','work','material','turns'].includes(currentView)?activity.overviewAttention():research.attention();
      activity.scopeHistory({from:currentView,attention,block,logical});
    }
    if(currentView==='history')activity.releaseHistory();
    if(currentView==='research'&&view!=='research')research.release();
    argument.release();
    dirty=false;currentView=view;root.dataset.view=view;help.show(view);$('[data-manuscript-outline]').hidden=view!=='manuscript';$(
      '[data-focus]').hidden=view!=='manuscript';const returnPlace=workspaceReturn.current;$('[data-return-reader]').hidden=!returnPlace;$(
      '[data-return-reader]').textContent=returnPlace?'Back to '+returnPlace.label:'';manuscriptView.sourceWindow()?.walk?.setReturnMode?.(
      returnPlace?'cross-view':'');const viewLabel=$('[data-view-label]');if(viewLabel)viewLabel.textContent=surfaceLabels[view]||view;
      navigationChanged();const version=++loadVersion;
    for(const b of root.querySelectorAll('[data-view]')){b.setAttribute('aria-selected',String(b.dataset.view===view));if(
      b.dataset.view===view)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');}
    if(navLayout(innerWidth)==='drawer')root.classList.add('nav-closed');   // the drawer closes on every view change; navLayout is the one boundary
    const uri=new URL(location.href);uri.searchParams.set('view',view);uri.searchParams.delete('stage');history.replaceState({},'',research.url(uri,{active:view==='research'}));
    const host=$('[data-main]');
    if(manuscriptView.host()&&view!=='manuscript')manuscriptView.host().hidden=true;
    if(activity.reviewHost())activity.reviewHost().hidden=view!=='review';
    // the kept hosts: the manuscript frame, the review surface and an open Help layer (repainted above by help.show)
    for(const old of [...host.children])if(old!==manuscriptView.host()&&old!==activity.reviewHost()&&old!==help.layer())old.remove();
    host.classList.toggle('frame-view',view==='manuscript');session.scope();
    if(view==='manuscript'){await manuscriptView.render(host);return;}
    if(view==='review'&&activity.reviewHost()){await activity.resumeReview(version);return;}
    const body=E('div');host.append(body);body.append(pendingRead(E('p','Loading '+surfaceLabels[view].toLowerCase()+'…','muted')));
    try{
      if(view==='overview'){await Promise.all([reuseState?Promise.resolve():work.reload(),home.refreshMetadata()]);if(version===loadVersion)await home.renderOverview(body);}
      if(view==='work'){if(!reuseState)await work.reload();if(version===loadVersion)await work.render(body);}
      if(view==='material'){const projects=(await home.library()).projects;if(version!==loadVersion)return;const controller=await mountMaterial(body,{pending:pendingRead,
        project,info,projects,draft:materialDraft,selectedBinding:new URL(location.href).searchParams.get('binding'),onInspectOwner:((...args)=>
        inspection.ownerRead(...args)),isCurrent:()=>version===loadVersion,onDirty:value=>{if(version===loadVersion)dirty=value;},request:api,
        onAddLocalDocument:addLocalDocument,onShow:show,onArtifact:((...args)=>inspection.projectArtifact(...args)),onHistory:((...args)=>activity.openOwner(...args)),onDiscuss:row=>
        talk('Help me understand the project file '+row.path+'. Check its recorded source and current revision.'),onRefresh:()=>show('material',
        false)});if(version===loadVersion)materialController=controller;else controller.destroy();
        if(sharedBindings&&version===loadVersion){const shared=[...body.querySelectorAll('h3')].find(node=>/shared material/i.test(node.textContent));
          if(shared){shared.tabIndex=-1;shared.focus({preventScroll:true});host.scrollTop=Math.max(0,shared.offsetTop-16);}}}
      // Settings and Presentation read their own owners; neither performs the Work summary read.
      if(view==='settings'&&version===loadVersion)await home.renderSettings(body);
      if(view==='argument')await argument.render(body);
      if(view==='reader-plan')await readerHome.render(body,version);
      if(view==='research')await research.render(body);
      if(view==='presentation'&&version===loadVersion)await figures.render(body);
      if(view==='review')await activity.mountReview(body);
      if(view==='history')await activity.renderHistory(body);
      if(version===loadVersion){host.scrollTop=0;const heading=body.querySelector('h2,h3');if(heading&&ask){heading.tabIndex=-1;heading.focus({preventScroll:true});}}
    }catch(error){if(view==='review')activity.forgetReview();if(version===loadVersion){body.replaceChildren(E('h2',surfaceLabels[view]),E('p',
      error.message,'error'),button('Retry',()=>show(view,false)));notice(error.message,true);}}
  }
  async function readSavedTurn(id,options={}){return openSavedTurn({project,turnId:id,...options,request:api,renderMarkdown:((...args)=>
    inspection.savedMarkdown(...args)),onConversation:openConversation,onHistory:((...args)=>activity.openOwner(...args)),onWork:((...args)=>
    work.open(...args)),onOpenArtifact:((...args)=>inspection.projectArtifact(...args))});}
  async function openConversation(id){chrome.openSession(true);const opened=await session.openConversation(id);if(opened&&session.session===id)session.setLibrary(false);}
  function renderStructure(host){return structureMode==='graph'?argument.render(host):readerHome.render(host);}
  pageListen(window,'laplace-source-effect',event=>{
    if(!root.isConnected||event.detail?.project!==project)return;
    const effect=sourceEffectDisposition({source_effect:event.detail},{project});
    if(effect.effect.impact.status!=='NONE'){
      manuscriptView.updates.invalidate();
      manuscriptView.editor()?.changed();
    }
    if(!effect.acknowledged||effect.warnings.length)notice(effect.message,true);
  });
  const walkBridge=installWalkBridge({target:window,origin:()=>location.origin,sourceWindow:(...args)=>manuscriptView.sourceWindow(...args),
    // laplace:review-proposal reaches THIS shell's canonical project Review controller (closure contract 2026-11-02)
    ledger:bridge,handlers:{...walkHandlers.handlers,reviewProposal:createProposalDecisionHandler({project,projectReview,origin:()=>location.origin})}});
  pageListen(window,'beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
  // THE PAGE-ISSUED FRONTEND BASIS (P2, frontend-basis.mjs): this page's issued basis is read once here and compared with
  // the served one at entry, on reconnection and (at most once a minute) on focus. A different served basis offers an
  // explicit refresh; each open owner captures its own state first (the visit, the Work memory with drafts, original
  // guards and unresolved attempts, the stored compose draft) and any missing precondition (an open cross-view return,
  // a manuscript TeX or walk draft, a Material or other unsaved form, an unstored compose draft) refuses and keeps
  // this page. Nothing reloads or resends by itself.
  const frontend=createFrontendBasis({project,request:api});
  const updateLine=E('div','','work-status frontend-update');updateLine.dataset.frontendUpdate='';updateLine.setAttribute('role','status');updateLine.hidden=true;
  $('[data-notice]').after(updateLine);
  const refreshAdapters=()=>[
    {name:'kept',capture:()=>carryState==='kept'?{ok:false,missing:'This tab still keeps Work drafts from an earlier refresh that this page has not restored; restore them here first so a new capture cannot replace them.'}:{ok:true}},
    {name:'visit',capture:()=>workspaceReturn.current?{ok:false,missing:'A "Back to '+(workspaceReturn.current.label||'the previous place')+
      '" return is open and is not carried across a refresh; use it or leave this view first.'}:{ok:true,carry:{view:currentView}}},
    {name:'work',capture:()=>({ok:true,carry:work.capture()})},
    {name:'compose',capture:()=>session.unsavedDrafts?.size?{ok:false,missing:'The conversation draft could not be stored in this browser; copy it before refreshing.'}:{ok:true}},
    {name:'manuscript',capture:()=>{try{manuscriptView.saved();return {ok:true};}catch(error){return {ok:false,missing:error.message};}}},
    {name:'material',capture:()=>materialController?.hasDraft?{ok:false,missing:'The Material form has unsaved changes; save or discard them first.'}:{ok:true}},
    {name:'form',capture:()=>dirty&&currentView!=='work'?{ok:false,missing:'This view has an unsaved form; save or discard it first.'}:{ok:true}}];
  const carryLine=E('div','','work-status frontend-carry');carryLine.dataset.refreshCarry='';carryLine.setAttribute('role','status');carryLine.hidden=!refreshCarry;
  updateLine.after(carryLine);
  const short=value=>value?value.slice(0,12):'none';
  function paintCarry(note=''){
    carryLine.dataset.refreshCarry=carryState||'';carryLine.dataset.issuedBasis=refreshCarry?.status||'';carryLine.replaceChildren();if(!refreshCarry)return;
    const record=refreshCarry.record,lines={
      adopting:'This page was issued from '+short(refreshCarry.issued)+', the version the refresh intended. The carried view and Work drafts are kept in this tab until '+(carryPending.has('work')?'the Work they belong to is shown from its owner (Retry if it was unavailable).':'they are restored.'),
      restored:'The carried view and Work drafts were restored into this page ('+short(refreshCarry.issued)+'). Saves whose outcome was unknown stay unresolved; nothing was resent.',
      superseded:'The carried drafts were restored into this page; a newer refresh capture in this tab was left in place.',
      kept:refreshCarry.status==='unreadable'?'This tab keeps a refresh record this page cannot read; it is kept, not restored, and nothing was resent.':
        'The refresh intended frontend '+short(record.to)+', but this page was issued from '+(refreshCarry.status==='unknown'?'an unreported version':short(refreshCarry.issued)+
        (refreshCarry.issued===record.from?' (the version before the refresh)':''))+'. The carried view and Work drafts are kept in this tab, not restored; nothing was resent.'};
    carryLine.append(E('span',lines[carryState]+note));
    if(carryState==='kept'&&record){const adopt=E('button','Restore the kept Work drafts on this page');adopt.type='button';adopt.dataset.control='frontend:restore-carry';
      adopt.onclick=()=>restoreKept().catch(error=>paintCarry(' Not restored: '+error.message));carryLine.append(adopt);}
  }
  function carryRestored(part){
    if(carryState!=='adopting')return;carryPending.delete(part);if(carryPending.size){paintCarry();return;}
    carryState=acknowledgeRefreshCarry(project,refreshCarry)?'restored':'superseded';paintCarry();
  }
  async function restoreKept(){
    if(carryState!=='kept'||!refreshCarry.record)return;
    const memory=refreshCarry.record.carried.work||null,pending=memory?work.restore(memory):false;   // refuses while this page has its own Work drafts
    carryState='adopting';carryPending.clear();if(pending)carryPending.add('work');paintCarry();
    if(pending)await show('work');else carryRestored('visit');
  }
  function paintFrontend(value){
    updateLine.dataset.frontendBasis=value.status;updateLine.hidden=value.status!=='different-served';updateLine.replaceChildren();
    if(value.status!=='different-served')return;
    const note=E('span',''),go=E('button','Refresh to the served app version');go.type='button';go.dataset.control='frontend:refresh';
    go.onclick=async()=>{go.disabled=true;const result=await frontend.refresh(refreshAdapters());if(result.refreshed)return;go.disabled=false;
      note.textContent=' Not refreshed; this page stays as it is. '+result.missing.join(' ');note.className='error';};
    updateLine.append(E('span','This app is now served from a different frontend version than this page (this page: '+value.issued.slice(0,12)+', served: '+value.served.slice(0,12)+
      '). Refreshing keeps your Work drafts, unresolved saves and this view; nothing is resent. '),go,note);
  }
  let frontendChecked=0;
  const checkFrontend=()=>{frontendChecked=Date.now();return frontend.check().then(value=>{if(!shellDestroyed)paintFrontend(value);return value;});};
  pageListen(window,'laplace-workspace-reconnected',()=>{void checkFrontend();});
  pageListen(window,'focus',()=>{if(Date.now()-frontendChecked>60000)void checkFrontend();});
  // TEARDOWN (C12 residual R4; S2-R2): once, idempotent, and the same object for a successful, a failed or a still
  // pending entry: every controller, poll and listener above is already installed, so it exists before the entry
  // reads. Help and the task cue are disposed (their own owners release their DOM, observers, frames and listeners;
  // the cue's run stays open and resumable, no outcome is written); a help, task or entry read still pending when
  // the shell goes can never mount or repaint afterwards (shellDestroyed); the global handle is released if it is ours.
  const workspace={show,session,context:(...args)=>contextOwner.read(...args),canGoBack,frontendBasis:()=>frontend.state(),checkFrontend,refreshCarry:()=>carryState,destroy(){if(shellDestroyed)return;shellDestroyed=true;dismissConfirmation({leave:false});noticeSize?.disconnect();
    loadVersion++;releaseViewControllers();localDocumentDraft?.releaseFile();
      activity.destroyHistory();research.release();
      argument.destroy();
      manuscriptView.destroy();
      help.dispose();walkBridge.uninstall();removePageListeners();projectReview.destroy();activity.destroyReview();session.destroy();
      if(window.laplaceWorkspace===workspace)window.laplaceWorkspace=null;root.dataset.entry='destroyed';},back:()=>{if(
        canGoBack()){argument.back($('[data-main]').lastElementChild);return true;}return false;}};
  window.laplaceWorkspace=workspace;root.dataset.entry='pending';
  // ENTRY READS (plan budget: Home/entry ≤ 30,000 B): this project's metadata owner (title,
  // capabilities, selected source, bounded candidates) and the Work summary's first page.
  // The whole-library read happens only when Material opens (it lists the other projects).
  // root.dataset.entry names the entry's state for tests and the operator: pending, ready, failed, destroyed.
  try{if(frameFailure)throw frameFailure;[state,info]=await Promise.all([api(WORK_SUMMARY_READ),api('/projects/metadata?project='+enc)]);}catch(error){if(shellDestroyed)return workspace;
    $('h1').textContent=project;const host=$('[data-main]');host.replaceChildren(E('h2','Project could not load'),E('p',error.message,'error'),
      button('Retry opening project',()=>location.reload()));notice('Project data is unavailable. Your saved conversation drafts are retained.',true);
    root.dataset.entry='failed';return workspace;}
  if(shellDestroyed)return workspace;
  $('h1').textContent=info.title||project;frame?.setTitle(info.title||project);chrome.refreshNavigation();
  // THE ENTRY'S LIFETIME FENCE (S2-R2): every later entry step is this mount's only while it is not destroyed. A
  // replacement shell may reuse the same connected root and project, so neither is authority; each await is
  // followed by the fence, and the Work admission carries it into its own owner read.
  const entryCurrent=()=>!shellDestroyed;
  if(initialQuery.has('work')){await work.admit(initialQuery.get('work'),{isCurrent:entryCurrent});if(!entryCurrent())return workspace;}
  const requested=canonicalWorkspaceView(new URLSearchParams(location.search).get('view'),structureMode);if(requested==='turns'){await show('overview',
    false,{reuseState:true});if(!entryCurrent())return workspace;}await show(surfaceLabels[requested]&&workspaceViewAvailable(info,requested)?requested:
    'overview',false,{reuseState:true});if(!entryCurrent())return workspace;if(surfaceLabels[requested]&&!workspaceViewAvailable(info,requested))notice(
    surfaceLabels[requested]+' is unavailable for the current project material. Work and Material remain available.');
  const workflowBack=workflowReturnURL(initialQuery.get('app_return'));
  if(workflowBack){const link=E('a','Return to workflow');link.href=workflowBack;link.dataset.control='workflow:return';root.querySelector('.workspace-header').append(link);}
  if(initialQuery.has('workflow_action_read')){
    const prompt=E('section','','workflow-conversation-request'),retry=button('Prepare retained workflow request',()=>prepareWorkflow());
    prompt.append(E('p','Workflow request: review in the conversation, then Send explicitly.'),retry);root.querySelector('.workspace-header').after(prompt);
    async function prepareWorkflow(){
      try{
        const requested=JSON.parse(initialQuery.get('workflow_action_read')),action=await readWorkflowConversationAction(project,requested,api);
        if(!entryCurrent())return;chrome.openSession(true);await session.useWorkflowAction(action);if(!entryCurrent())return;
        chrome.openSession(true);prompt.replaceChildren(E('p','Workflow request prepared in the conversation. Review it and Send.'));
        const uri=new URL(location.href);uri.searchParams.delete('workflow_action_read');history.replaceState({},'',uri);
      }catch(error){if(entryCurrent())notice('The original workflow request stays in this page address: '+error.message,true);}
    }
    await prepareWorkflow();if(!entryCurrent())return workspace;
  }
  try{
    const coordinates=profileGenerationCoordinates(initialQuery);
    if(coordinates){const basis=await api('/work/profiles?'+new URLSearchParams({project,...coordinates}));if(!entryCurrent())return workspace;
      generateProfile(profileGenerationIntent(project,basis));const uri=new URL(location.href);for(const key of ['profile_generation','profile_scope',
      'profile_path'])uri.searchParams.delete(key);history.replaceState({},'',uri);notice('Profile generation request prepared in this project conversation. Review it and Send.');}
  }catch(error){if(!entryCurrent())return workspace;notice('Profile generation request is retained in this page address: '+error.message,true);}
  if(!entryCurrent())return workspace;
  await openRequestedHelp({query:initialQuery,help,isCurrent:entryCurrent,notice});if(!entryCurrent())return workspace;
  carryRestored('visit');paintCarry();   // the carried view was shown (the address kept it); the Work part waits for its controller
  root.dataset.entry='ready';navigationChanged();void checkFrontend();return workspace;
}
// GUIDE BRIDGE:BEGIN (2026-10-16). The Projects page's "Open the Help guide" link arrives with help=open: after the first
// view is shown, open the existing Help layer (workspace-help-door openHelp: the non-modal guide for the current view)
// once. The parameter is removed from the address first, so a reload or shared link does not reopen it. It never starts
// a journey, task or model, and a shell destroyed meanwhile shows nothing (openHelp and the caller keep their fences).
async function openRequestedHelp({query,help,isCurrent,notice,place=globalThis.location,pages=globalThis.history}){
  if(query.get('help')!=='open')return false;
  const address=new URL(place.href);address.searchParams.delete('help');pages.replaceState(pages.state??{},'',address);
  try{await help.openHelp();}catch(error){if(isCurrent())notice('The Help guide could not open: '+error.message+' Use the Help button.',true);return false;}
  return isCurrent();
}
// GUIDE BRIDGE:END
