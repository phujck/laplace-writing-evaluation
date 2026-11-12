// WORKSPACE CONVERSATION (M5 S2 F1). Purpose: the shell's conversation column: one WorkspaceSession
// (workspace-session.mjs) wired to the shell's context and doors: the attached context, proposals and
// reviews, passage inspection and the external-application record, artifact and owner reads, saved turns,
// Work observation and selection, the Send preparation that attaches the exact TeX draft, and the effects an
// acknowledged turn had on the open views (structure, Work summary, manuscript, project home). Ownership: the
// conversation, its turns and their effects belong to the session owner; this module owns nothing: it builds
// the one session the shell keeps. Public contract: mountConversation(project, services) -> WorkspaceSession.
// Services: views (current view, show), forms (dirty), ui (notice, $), structures, workState (get, set, summary
// read), initialQuery, context, projectReview, manuscript, inspection, activity, work, home, discussion
// (session, open, saved turn), orientation (readingMoved: the shell's where-am-I line, repainted from every scope()).
import {WorkspaceSession,projectRequest as api,savedActionDestination} from "/shared/workspace-session.mjs";
import {fileOnlyManuscriptSelection} from "/shared/manuscript-editing.mjs";
import {savedActionPlanPublication} from './plan-publication.mjs';
import {savedActionSourceEffect} from './source-effect.mjs';

export function mountConversation(project,{views,forms,ui,structures,workState,initialQuery,contextOwner,projectReview,manuscript,inspection,activity,work,home,discussion,orientation=null}){
return new WorkspaceSession(ui.$('[data-session]'),{project,initialSession:initialQuery.get('session')||'',getContext:((...args)=>contextOwner.read(
  ...args)),onAddLocalDocument:discussion.addLocalDocument,onClose:()=>discussion.open(false),onReviewProposal:(id,options)=>projectReview.open(id,options),onOpenReview:((...args)=>
  activity.openProposals(...args)),onProposalChanged:()=>projectReview.settled(),onInspectPassage:((...args)=>manuscript.inspectPassage(...args)),
  onApplication:((...args)=>manuscript.rememberApplication(...args)),onOpenArtifact:((...args)=>inspection.projectArtifact(...args)),onOpenOwner:((
  ...args)=>inspection.ownerRead(...args)),renderFinalMessage:((...args)=>inspection.savedMarkdown(...args)),onReadTurn:discussion.savedTurn,
  onOpenWork:((...args)=>work.open(...args)),onScope:()=>orientation?.readingMoved?.(),onActivity:scope=>activity.openOwner({...scope,label:discussion.session().selectedConversationTitle||
  "Conversation"}),onWorkObservation:((...args)=>work.refresh(...args)),prepareSend:async({context:attention,selection})=>{
    const sourceDraft=(attention.surface==='manuscript'||selection)?manuscript.editor()?.prepareForSession(selection||attention.selection||{}):null;
      if(sourceDraft?.selection?.draft)return sourceDraft;
    if(fileOnlyManuscriptSelection(selection))return;
    if(attention.surface!=='manuscript'&&!selection)return;
    const walk=manuscript.sourceWindow()?.walk;if(!walk?.ready())return;
    const prepared=await walk.prepareForSession(selection||attention.selection||{},{save:false});
    const fresh=selection||attention.selection;
    return prepared.draft?{selection:{...fresh,draft:prepared.draft}}:undefined;
  },onChanged:async(actions,observation=null)=>{
    if(!actions.length)return;
    const sourceEffects=actions.map(action=>savedActionSourceEffect(action,{project})).filter(Boolean);
    const planPublications=actions.map(savedActionPlanPublication).filter(Boolean);
    const changedViews=new Set(actions.flatMap(action=>action.outcome?.views||[]));
    if(sourceEffects.some(effect=>effect.effect.impact.status!=='NONE')){changedViews.add('manuscript');manuscript.editor()?.changed();}
    for(const action of actions){const effect=savedActionSourceEffect(action,{project});const outcome=action.outcome||{};if(effect&&
      !effect.acknowledged||!effect&&outcome.source_effect_retained===true&&outcome.source_applied!==true)continue;if(
      outcome.undo_ref)await manuscript.rememberApplication({id:action.id,undo_ref:outcome.undo_ref});else if(outcome.application_id&&
      outcome.edits?.length)await manuscript.rememberApplication({id:outcome.application_id,edits:outcome.edits});}
    const changes=actions.map(a=>a.operation.replaceAll('_',' '));
    const sourceAttention=sourceEffects.find(effect=>!effect.acknowledged)||planPublications.find(effect=>!effect.acknowledged)||sourceEffects.find(
      effect=>effect.warnings.length)||planPublications.find(effect=>effect.warnings.length);
    ui.notice(sourceAttention?.message||'Project updated: '+[...new Set(changes)].join(', ')+'.',!!sourceAttention);
    const metadataChanged=actions.some(action=>action.operation==='project_metadata_change');
    if(views.current()==='work'){
      if(metadataChanged)await home.refreshMetadata();
      // An acknowledged effect may alter prerequisites or evidence without naming this Work.
      // The owner decides impact. Reuse this phase's read attempt, never a JS dependency guess.
      if(observation){if(!observation.fresh())return;if(observation.attempted)return;}
      const selectedSession=discussion.session()?.session,turn=discussion.session()?.origin?.turnId;
      await work.refresh({project,session_id:selectedSession,turn_id:turn,work_id:discussion.session()?.origin?.workId??null,phase:'known-change'},(
        )=>selectedSession===discussion.session()?.session&&turn===discussion.session()?.origin?.turnId);
      return;
    }
    if(metadataChanged||changedViews.has('project'))await home.refreshMetadata();
    workState.set(await api(workState.summaryRead));
    if(views.current()==='overview')home.refreshOverview(workState.get());
    if(forms.dirty()){ui.notice('The project changed. Your unsaved form is preserved; save or refresh before continuing.');return;}
    if(planPublications.length||actions.some(a=>(a.outcome?.views||[]).some(v=>['structure','concepts'].includes(v)))){structures.set(null);discussion.session().scope();}
    if(changedViews.has('manuscript'))await manuscript.updates.invalidate();
    if(views.current()==='manuscript')return;
    if(views.current()==='overview'&&metadataChanged&&!actions.some(action=>['argument','task','task_status','project_guidance_change'].includes(
      action.operation))){await home.refreshHome();return;}
    if(views.current()==='research'&&changedViews.has('research')){await views.show('research',false);return;}
    await views.show(views.current(),false);
  },onInspect:async action=>{const destination=savedActionDestination(action);if(destination?.kind==='artifact'){await inspection.projectArtifact(
    destination.path,destination.path,{scope:destination.scope,expectedSha256:destination.expectedSha256,artifactId:destination.artifactId,
    artifactOwner:destination.artifactOwner});return;}if(destination?.kind==='work'){await work.open(destination.id);return;}ui.notice(
    'This saved action has no qualified inspection route. Open its exact recorded turn to inspect the outcome.',true);if(discussion.session(
    ).selectedTurnRecord?.id)await discussion.savedTurn(discussion.session().selectedTurnRecord.id);}});
}
