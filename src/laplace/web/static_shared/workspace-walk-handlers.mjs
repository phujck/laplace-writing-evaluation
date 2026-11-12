// WORKSPACE WALK HANDLERS (M5 S2 F1). Purpose: the shell side of the walk bridge's nineteen named messages
// (HANDLED_BRIDGE_MESSAGES in workspace-bridge.mjs): the reading place memo, the engine-unavailable signal,
// owner-read and project-artifact links opened in the one inspector only while the same iframe and view are
// current, editor state, Open in TeX with its exact source basis, the compiled PDF, focus and sections,
// logical objects, research results, obligation Work, origin turns, a passage's reader-plan item, the
// request queue, discussing a selection, and source outcomes, warnings and saves. Ownership: installWalkBridge
// owns the message fence and ledger; each door's owner opens what it opens; this controller owns only the
// walk's last place memo. Public contract: mountWalkHandlers(project, services) -> {handlers, place()}.
// Services: views (current view, set current), forms (guard), ui (notice, root), manuscript (the frame),
// inspection, argument, research, work, readerHome, outline, returns, discussion (session, open, talk, saved
// turn), focus (manuscript focus and its restore state), workspaceReturn, onPlace (told when the walk reports a new
// reading place, so the header's where-am-I line can repaint).
import {projectRequest as api,artifactHumanTarget,ownerHumanTarget} from "/shared/workspace-session.mjs";
import {openPdf} from "/shared/writing-pdf.mjs";
import {sourceEffectDisposition} from './source-effect.mjs';

export function mountWalkHandlers(project,{enc,views,forms,ui,manuscript,inspection,argument,research,work,readerHome,outline,returns,discussion,focus,workspaceReturn,onPlace=()=>{}}){
  // the domain's own memory (moved out of the shell closure)
  let placeMemo=null;
  // THE WALK BRIDGE HANDLERS (M5 readability P2): what each admitted manuscript-iframe message does in the
  // shell, one named function per declared type. workspace-bridge.mjs owns the fence (same origin, the current
  // manuscript iframe only), the ledger and the routing; a handler runs only for a message of its declared
  // shape. Producers: walk.mjs, writing-panel.mjs and store.mjs (see "THE BRIDGE CONTRACT" in walk.mjs).
  const walkBridgeHandlers={
    // the iframe's reading place, memoised for the cross-view return; the spine door is demoted while the shell holds one
    place(message,event){
      placeMemo=message.place&&typeof message.place==='object'?{...message.place,source:event.source}:null;
      manuscript.sourceWindow()?.walk?.setReturnMode?.(workspaceReturn.current?'cross-view':'');
      onPlace();
    },
    engineUnavailable(){window.dispatchEvent(new CustomEvent('laplace-workspace-connection',{detail:{available:false}}));},
    // a manuscript link to an owner read opens in the one shared inspector (guarded by the conversation draft)
    openOwnerRead(message){
      const read=ownerHumanTarget(message.url);
      if(!read){ui.notice('The manuscript link has invalid owner reading coordinates.',true);return;}
      discussion.session().guard(()=>inspection.ownerRead(read,message.label||'Manuscript owner link'));
    },
    // a project artifact link: a qualified owner URL opens only while the same iframe and view are current
    openProjectArtifact(message){
      if(typeof message.url!=='string'){
        discussion.session().guard(()=>inspection.projectArtifact(message.path,message.label,{scope:message.scope||'project',notice:message.notice||''}));
        return;
      }
      const target=artifactHumanTarget(message.url,{project});
      if(!target){ui.notice('The manuscript link has invalid artifact reading coordinates.',true);return;}
      const source=manuscript.sourceWindow(),view=views.current(),opener=source?.document?.activeElement,fresh=()=>ui.root.isConnected&&
        manuscript.sourceWindow()===source&&views.current()===view;
      discussion.session().guard(()=>fresh()?inspection.projectArtifact(target.path,message.label||target.path,{...target,opener,isCurrent:fresh}):undefined);
    },
    editorState(){manuscript.editor()?.stateChanged();},
    // Open in TeX: the block's exact repository path and the source basis it was read under (the bridge admits
    // nothing less); openSource refuses a moved selection or changed file instead of opening another source.
    openDocumentSource(message){manuscript.editor()?.openSource(message.file,message.line,false,{selection_identity:message.basis.selection_identity,
      source_digest:message.basis.source_digest}).catch(error=>ui.notice(error.message,true));},
    openDocumentPdf(message){
      if(manuscript.editor()){manuscript.editor().readPdf().catch(error=>ui.notice(error.message,true));return;}
      openPdf('/projection/pdf?file='+encodeURIComponent(message.file)+'&corpus='+enc,'Last compiled document',{onOpenArtifact:((...args)=>inspection.projectArtifact(...args))});
    },
    // no producer in this tree (UNKNOWN_PRODUCER_MESSAGES): kept, counted, not inferred unreachable
    focusManuscript(){focus.manuscript();},
    showSections(){
      if(focus.restoring())focus.manuscript();
      if(innerWidth<=1050)discussion.open(false);
      ui.root.classList.remove('nav-closed');
    },
    logicalObject(message){forms.guard(async()=>{await argument.openConcept(message.node,{origin:message.anchor||null});})();},
    researchResult(message){forms.guard(()=>research.openEvidence(message.id))();},
    obligationWork(message){forms.guard(()=>work.open(message.id))();},
    readOriginTurn(message){forms.guard(()=>discussion.savedTurn(message.id))();},
    // a passage's reader-plan item: one exact automatic section opens; otherwise the reader plan asks the person to choose
    logicalContext(message){
      forms.guard(async()=>{
        argument.setOrigin(message.anchor);
        const context=await api('/concepts/plan/context?'+new URLSearchParams({project,file:message.anchor.file,line_start:message.anchor.line_start,
          line_end:message.anchor.line_end}));
        const matches=context.passage_context?.basis?.automatic_sections||[];
        if(matches.length===1){await readerHome.openSection(matches[0].id);return;}
        returns.remember();
        await readerHome.openUnselected({sectionId:null,beatId:null});
        ui.notice(
          matches.length?'Several reader-plan items cover this passage. Choose the intended item.':
          'No exact reader-plan item is linked to this passage. Choose or create an item, then link its source heading.');
      })();
    },
    queuedRequest(){discussion.session().guard(()=>discussion.session().loadQueue());},
    discussSelection(message){
      views.setCurrent('manuscript');discussion.open(true);
      discussion.talk(message.mode==='revise'?'Help revise this selected passage.':'Let’s discuss this passage.',message.mode||'discuss',message.selection);
    },
    // a saved or refused source effect from the panel: said once, then the shell and editor re-read
    sourceOutcome(message){
      const effect=sourceEffectDisposition(message,{project});
      if(effect){ui.notice(effect.message,!effect.acknowledged);work.reload();manuscript.editor()?.changed();}
    },
    sourceWarning(message){ui.notice(message.text,true);},
    sourceSaved(){work.reload();outline.render();manuscript.editor()?.changed();}
  };
  return {handlers:walkBridgeHandlers,place:()=>placeMemo};
}
