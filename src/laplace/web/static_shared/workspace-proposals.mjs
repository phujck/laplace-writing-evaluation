// WORKSPACE PROPOSALS (M5 S2 F1). Purpose: reviewing one agent proposal from the shell: read the exact
// proposal (candidate, version, edits) from its owner, show it over the manuscript (walk.showProposal) or as a
// saved comparison, and carry the human's decision (keep, apply, reject, resolve) through the proposal and
// resolution owners with their exact guards, recovering the known outcome when follow-up maintenance fails.
// Ownership: proposals, candidates, resolutions and source belong to their owners and the walk; this
// controller owns only the review generation that makes a late answer inert. Public contract:
// mountProposalReview(project, services) -> {review(target, options)}. Services: views (current view), ui
// (notice), manuscript (the frame: window, ready, saved, editor, external application record), projectReview,
// inspect (owner read, project artifact), discussion (open, saved turn, talk), workState (reload).
import {projectRequest as api} from "/shared/workspace-session.mjs";
import {candidateApplicationSubmission,resolutionFinalizationSubmission,resolutionPrepareSubmission,validateResolutionFinalization,
  validateResolutionPreparation} from './proposal-resolution.mjs';
import {proposalActionAllowed,proposalChangeRequest,proposalDecisionAcknowledged,proposalReadURL,proposalScopeUnproven,selectedProposalBody} from "/shared/manuscript-editing.mjs";
import {qualifiedOwnerHTTP} from './writing-owner-read.mjs';
import {sourceEffectDisposition,sourceEffectFromError} from './source-effect.mjs';
import {title} from './workspace-dom.mjs';

export function mountProposalReview(project,{views,ui,manuscript,projectReview,inspect,discussion,workState}){
  // the domain's own memory (moved out of the shell closure)
  let proposalReviewGeneration=0;
  // Returns the truthful opening outcome (closure contract 2026-11-02): {opened:false, state, reason} when nothing was
  // shown (SUPERSEDED, NOT_SHOWN, VERSION_CHANGED), or {opened:true, decision, state, project, turn_id, proposal_version}
  // after walk.showProposal. Callers that ignored the former undefined keep their meaning; a decision caller requires
  // opened && decision for its exact target. Opening is never an application or any other source effect.
  async function reviewProposal(turnId,{readOnly=false,proposalVersion=null,readHandle=null,decision=false}={}){
    if(!proposalVersion||!readHandle)throw Error('Choose an exact saved version in project Review before opening its comparison.');
    const generation=++proposalReviewGeneration,walk=await manuscript.ready();
    if(generation!==proposalReviewGeneration)return {opened:false,state:'SUPERSEDED',reason:'A newer review superseded this one; nothing was shown here.'};   // it speaks for itself
    // THE EXPLICIT OUTCOME (M5): manuscript.ready() answers null when the Manuscript view did not open (refused) or did not
    // stay open until its frame was ready (superseded by a later navigation). The person chose Review in manuscript, so
    // the status says what did not happen instead of nothing; no second transition is attempted and no guard is bypassed.
    if(!walk){const standing=ui.$?.('[data-notice]')?.textContent||'';   // a refusal the shell already stated stays the reason
      if(views.current()==='manuscript')ui.notice('The manuscript did not finish loading, so the saved comparison was not opened. Choose Review in manuscript again once the manuscript is ready.',true);
      else if(!standing)ui.notice('The Manuscript view did not open or did not stay open, so the saved comparison was not started. Open Manuscript and choose Review in manuscript again.',true);
      return {opened:false,state:'NOT_SHOWN',reason:standing||'The Manuscript view did not open or stay open; nothing was shown.'};}
    const isCurrent=(
      )=>generation===proposalReviewGeneration&&views.current()==='manuscript'&&manuscript.sourceWindow()?.walk===walk;
    let preview=await api(readHandle?proposalReadURL(readHandle,{project,turnId,
      version:proposalVersion}):'/authoring/proposal-preview?'+new URLSearchParams({project,turn_id:turnId,...(proposalVersion?{proposal_version:proposalVersion}:{})}));
    if(!isCurrent())return {opened:false,state:'SUPERSEDED',reason:'The manuscript review changed while the proposal was read; nothing was shown.'};
    if(decision===true&&preview.proposal_version!==proposalVersion)return {opened:false,state:'VERSION_CHANGED',reason:'The proposal owner returned another version; nothing was shown.'};
    discussion.open(false,{remember:false});const selectedVersion=preview.proposal_version;
    const shown=(state,decisionView)=>({opened:true,decision:decisionView,state,project,turn_id:turnId,proposal_version:selectedVersion});let summary=preview,
      selectedEdit=preview.edits?.find(edit=>['pending','conflict'].includes(edit.status))||preview.edits?.[0];
    const loadEdit=async editId=>{const row=summary.edits?.find(edit=>edit.edit_id===editId);if(!row?.preview_read&&!row?.read_handle)throw Error(
      'The owner supplied no exact edit body read. Refresh the proposal summary.');const body=await api(proposalReadURL(row.preview_read||
      row.read_handle,{project,turnId,version:selectedVersion,editId}));if(!isCurrent())throw Error(
      'The selected review changed while its body was read. No action was started.');preview=selectedProposalBody(summary,body,editId);selectedEdit=body.edits[0];return preview;};
    if(readHandle&&selectedEdit&&(selectedEdit.preview_read||selectedEdit.read_handle))await loadEdit(selectedEdit.edit_id);
    const refresh=async({afterDecision=false}={})=>{if(readHandle){summary=await api(proposalReadURL(readHandle,{project,turnId,
      version:selectedVersion}));if(afterDecision&&selectedEdit&&!['pending','conflict'].includes(summary.edits?.find(row=>
      row.edit_id===selectedEdit.edit_id)?.status))selectedEdit=summary.edits?.find(row=>['pending','conflict'].includes(row.status))||
      summary.edits?.find(row=>row.edit_id===selectedEdit.edit_id);if(selectedEdit?.edit_id&&summary.edits?.some(row=>
      row.edit_id===selectedEdit.edit_id))return loadEdit(selectedEdit.edit_id);preview=summary;return preview;}preview=await api(
      '/authoring/proposal-preview?'+new URLSearchParams({project,turn_id:turnId,proposal_version:selectedVersion}));return preview;};
    const selectEdit=readHandle?editId=>loadEdit(editId):null;
    const inspectBasis=async(_kind,item)=>{if(!isCurrent())return;const target=qualifiedOwnerHTTP(item.read,project);if(!target?.owner)throw Error(
      'The proposal owner supplied no exact supporting input read. Refresh the comparison.');return inspect.ownerRead(target.owner,'Proposal supporting input',{isCurrent});};
    const requestChanges=edit=>{const request=proposalChangeRequest({...edit,...(walk.proposalDraftConflict?.(edit)?{lifecycle:'blocked',
      local_draft_overlap:true}:{})},{turnId,version:preview.proposal_version,readHandle:edit.read_handle||preview.read_handle});discussion.talk(
      request.text,'revise',request.selection);};
    const inspectCurrentFile=edit=>inspect.projectArtifact(edit.file,'Current manuscript source',{scope:'manuscript',
      notice:'Current file bytes. Historical offsets are not a validated target; this read does not enable replacement.'});
    const manuscriptSaved=batch=>{const edits=walk.editState?.();if(!batch?.remaining?.length&&!batch?.refused?.length&&!edits?.dirty&&!edits?.parked)ui.notice('');};
    const openCandidate=async(handle,ref)=>{if(!isCurrent())return;return projectReview.open(ref.id,{proposalVersion:ref.version,readHandle:handle});};
    const openPredecessor=async(handle,subject)=>{if(!isCurrent())return;const ref=subject.candidate_ref||{id:subject.turn_id,
      version:subject.proposal_version};return projectReview.open(ref.id,{proposalVersion:ref.version,readHandle:handle,readOnly:true});};
    const humanApplied=async(result,receipt={})=>{
      if(!isCurrent())return;
      const effect=sourceEffectDisposition(result,{project});
      if(effect&&!effect.acknowledged){ui.notice(effect.message,true);return;}
      await projectReview.settled();if(!isCurrent())return;
      if(result.application?.complete&&!result.metadata_only){manuscript.saved();await manuscript.rememberApplication({...result.application,
        project});if(!isCurrent())return;if(!receipt.newerDraft){await walk.refresh();if(!isCurrent())return;}}
      if(receipt.newerDraft){ui.notice('Revision applied. Your newer resolution draft remains in this review; inspect its saved receipt before another action.');return;}
      if(result.read_handle&&result.candidate_ref)await openCandidate(result.read_handle,result.candidate_ref);
    };
    const humanOptions={
      allowResolution:!readOnly,
      onPrepareResolution:async(edit,target)=>{
        const submission=resolutionPrepareSubmission(edit.resolution_action,project,target);
        const result=await api(submission.url,submission.payload);if(!isCurrent())throw Error('The selected candidate changed. Your resolution draft is retained.');
        const subject=Object.fromEntries(['turn_id','proposal_version','candidate_ref','edit_id'].filter(key=>submission.payload[
          key]!==undefined).map(key=>[key,submission.payload[key]]));
        validateResolutionPreparation(result,{project,subject});
        if(result.target&&walk.proposalDraftConflict?.({file:result.target.file,current_anchor:result.target}))throw Error(
          'Your unsaved manuscript text overlaps this current passage. Save it before resolving the revision; your text is retained.');
        return result;
      },
      onResolutionRequest:async(path,payload)=>{if(!isCurrent())throw Error('The selected candidate changed. No resolution action was started.');if(
        payload?.target&&walk.proposalDraftConflict?.({file:payload.target.file,current_anchor:payload.target}))throw Error(
        'Your unsaved manuscript text overlaps this current target. Save it before applying; your resolution choices are retained.');return api(path,payload);},
      onReadCandidate:openCandidate,onOpenPredecessor:openPredecessor,onHumanApplied:humanApplied,
      onFinishResolution:readOnly?null:async(action,ref,disposition)=>{if(!isCurrent())throw Error(
        'The selected saved revision changed. No reconciliation record was started.');const submission=resolutionFinalizationSubmission(action,
        project,ref,disposition);const result=validateResolutionFinalization(await api(submission.url,submission.payload),{project,ref,disposition});
        await humanApplied(result);return result;},
      onApplyCandidate:readOnly?null:async(action,ref)=>{const submission=candidateApplicationSubmission(action,project,ref);if(!isCurrent(
        ))throw Error('The selected resolved revision changed.');const result=await api(submission.url,submission.payload);await humanApplied(result);return result;}
    };
    if(preview.candidate_ref){walk.showProposal(preview,{...humanOptions,readOnly:true,onRefresh:()=>api(proposalReadURL(readHandle,{project,turnId,
      version:selectedVersion})),onInspectOrigin:discussion.savedTurn,displayLabel:title});return shown('INSPECT_ONLY',false);}
    const decide=async(editId,decision,extra={})=>{
      if(['accept','replace-current','merge'].includes(decision))manuscript.saved();
      const edit=preview.edits.find(row=>row.edit_id===editId);
      if(!proposalActionAllowed(edit,decision))throw Error('This action is unavailable for the current source and basis. Inspect the source or request a fresh change.');
      if(['accept','replace-current','merge'].includes(decision)&&walk.proposalDraftConflict?.(edit))throw Error(
        'Your unsaved manuscript text overlaps this edit. Save that manuscript edit or request a fresh reconciliation; your draft is preserved.');
      // THE SUGGESTION'S IDENTITY, SENT (WRITING-CONSOLIDATION-W1). `/authoring/proposal-decision`
      // compares the proposal's token, and this is the surface that issues every decision. The token
      // is the one `preview` was READ with (`manuscript_proposals.py:293` publishes it in
      // `identities`), captured at the read and not at the click: re-reading it here would hand the
      // gate whatever the session has since proposed, which is the race the gate exists to catch.
      // On refusal the cure is to RE-READ and say so --- never `{...request, ...needed}`, which would
      // decide a suggestion the reviewer never saw.
      const expected=Object.values(preview.identities||{});let next;
      try{next=await api('/authoring/proposal-decision',{project,turn_id:turnId,edit_id:editId,decision,...(expected.length?{expected}:{}),...extra});}
      catch(error){
        const effect=sourceEffectFromError(error,{project});
        if(effect){
          if(isCurrent()){
            ui.notice(effect.message,true);
            walk.showProposal({...preview,reviewable:false},{...humanOptions,onRefresh:refresh,onInspectCurrentFile:inspectCurrentFile,
              onInspectOrigin:discussion.savedTurn,displayLabel:title,focus:false,decisionError:effect.message});
            await manuscript.editor()?.changed();
          }
          throw error;
        }
        if(!error.result)throw error;
        await refresh();
        walk.showProposal(preview,{...humanOptions,onDecision:decide,onRequestChanges:requestChanges,onRefresh:refresh,onSelectEdit:selectEdit,
          onInspectBasis:inspectBasis,onInspectCurrentFile:inspectCurrentFile,onInspectOrigin:discussion.savedTurn,onManuscriptSaved:manuscriptSaved,
          displayLabel:title,focus:false,decisionError:error.message});
        throw Error(error.message+(preview.edits?.some(
          proposalScopeUnproven)?
          ' The saved comparison has been re-read. Historical offsets remain unproven; inspect the current source or request a fresh reconciliation.':
          ' The suggestion has been re-read; decide again on the version now shown.'));
      }
      // The effect receipt is settled before any optional view maintenance.
      // A failed history/sidebar/document read must never discard that exact ack
      // or invite an effect retry. Late results do not repaint another review.
      preview=next;
      const sourceEffect=sourceEffectDisposition(next,{project});
      if(sourceEffect&&!sourceEffect.acknowledged){
        if(isCurrent()){
          ui.notice(sourceEffect.message,true);
          walk.showProposal({...next,reviewable:false},{...humanOptions,onRefresh:refresh,onInspectCurrentFile:inspectCurrentFile,
            onInspectOrigin:discussion.savedTurn,displayLabel:title,focus:false});
          await manuscript.editor()?.changed();
        }
        return next;
      }
      if(next.project===project&&next.turn_id===turnId&&next.proposal_version===selectedVersion&&(next.application_tracking?.status==='UNPROVED'||
        next.application?.application_tracking?.status==='UNPROVED'||next.application?.status==='SOURCE_INCOMPLETE'||next.preview_unavailable===true||
        next.application_maintenance_unproved===true)){
        if(isCurrent()){
          ui.notice(next.warning||next.application?.warning||
            'Source changed; application tracking is unproved. Keep your draft and inspect source feedback before another action; do not repeat the effect.',true);
          try{
            if(next.preview_unavailable)walk.clearProposal();else walk.showProposal({...next,reviewable:false},{...humanOptions,onRefresh:refresh,
              onInspectCurrentFile:inspectCurrentFile,onInspectOrigin:discussion.savedTurn,displayLabel:title,focus:false});
            await walk.refresh();
          }catch(error){if(isCurrent())ui.notice((next.warning||next.application?.warning||
            'Source outcome retained.')+' View maintenance is unavailable: '+error.message+' Do not repeat the effect.',true);}
        }
        return next;
      }
      const applied=proposalDecisionAcknowledged(next,{project,turnId,version:selectedVersion,editId});
      if(isCurrent())try{
        await projectReview.settled();
        if(!isCurrent())return next;
        // Fresh exact parent metadata plus demanded body: child.remaining is not a total.
        preview=await refresh({afterDecision:true});
        if(!isCurrent())return next;
        walk.showProposal(preview,{...humanOptions,onDecision:decide,onRequestChanges:requestChanges,onRefresh:refresh,onSelectEdit:selectEdit,
          onInspectBasis:inspectBasis,onInspectCurrentFile:inspectCurrentFile,onInspectOrigin:discussion.savedTurn,onManuscriptSaved:manuscriptSaved,
          displayLabel:title,focus:false});
        if(applied){
          if(next.application?.edits?.length)await manuscript.rememberApplication(next.application);
          else ui.notice('The application was recorded, but its undo source snapshot is unavailable. Inspect the exact owner receipt.',true);
          if(!isCurrent())return next;
          await walk.refresh();
        }
        if(isCurrent())await workState.reload();
      }catch(error){if(isCurrent())ui.notice((
        applied?'Application recorded; ':'Decision recorded; ')+'refresh/history is unavailable: '+error.message+' Reinspect the owner record; do not repeat the effect.',true);}
      return next;
    };
    readOnly=readOnly||preview.read_only||['applied','rejected','applied-elsewhere','superseded','fulfilled','resolved-into-successor'].includes(
      preview.proposal_state);walk.showProposal(preview,{readOnly,onDecision:readOnly?undefined:decide,
      onRequestChanges:readOnly?undefined:requestChanges,onRefresh:refresh,onSelectEdit:selectEdit,onInspectBasis:inspectBasis,
      onInspectCurrentFile:inspectCurrentFile,onInspectOrigin:discussion.savedTurn,onManuscriptSaved:manuscriptSaved,displayLabel:title,...humanOptions});
    return shown(readOnly?'READ_ONLY':'DECISION',!readOnly);
  }
  return {review:reviewProposal};
}
