// WORKSPACE READER PLAN VIEW (M5 S2 F1). Purpose: the Reader plan view of the shell: it mounts the reader
// plan through workspace-spine's mountReaderPlan and answers its doors: plan operations on the structure
// owner, a reader-plan occurrence or link opened in the manuscript, research, argument or an owner read,
// preparing storyboard work and showing a preparation failure, and opening one plan section from
// elsewhere. Ownership: the plan, its sections and its revisions belong to /work/structure and the spine
// controller; this controller owns only the mounted reader-plan controller, its captured memory (selected
// section, beat and read handle) and the reader-review receipts. Public contract:
// mountReaderPlanView(project, services) -> {render(host), plan(operation, extra), openSection(id, options),
// openUnselected(memory), context(), capture(), restore(memory), release()}. Services: views (current
// view, show, generation, structure rendering), forms (dirty), ui (notice, button, $), structures,
// manuscript (editor, source window, bound source), research, argument, work (open), inspect (owner read,
// project artifact), discussion (session, conversation, saved turn, profile generation), place (the
// reader return). Lifetime: release() captures the plan memory and destroys the mounted controller when
// the view is left; a load generation guards late replies.
import {E} from './workspace-dom.mjs';
import {projectRequest as api,ownerHumanTarget} from "/shared/workspace-session.mjs";
import {editReaderPlanItem,inspectSourceOccurrence,mountReaderPlan,spineReadURL} from './workspace-spine.mjs';
import {inspectArchitecturePrior,readerReviewSubmission,showReaderDialog} from './reader-state.mjs';
import {passageHistoryRead,qualifiedOwnerHTTP} from './writing-owner-read.mjs';
import {planPublicationDisposition} from './plan-publication.mjs';
import {preparedWorkReceipt,preparedWorkSubmission,renderPreparationFailure,renderPreparedWork} from './prepared-work.mjs';
import {waitForManuscript} from "/shared/manuscript-editing.mjs";

export function mountReaderPlanView(project,{enc,initialQuery,views,forms,ui,structures,manuscript,research,argument,work,inspect,discussion,place}){
  // the domain's own memory (moved out of the shell closure)
  let readerReviewReceipts=new WeakMap(),
    readerPlanController=null,
    readerPlanMemory={sectionId:initialQuery.get('section')||null,beatId:initialQuery.get('beat')||null};
  async function openPlanSection(id, {remember=true,handle=null}={}){
    if(remember)place.remember();readerPlanMemory={sectionId:id,beatId:null,readHandle:handle};
    if(views.current()==='reader-plan'&&readerPlanController)return readerPlanController.select(id,handle||undefined);
    return views.show('reader-plan',false);
  }
  async function plan(operation,extra={}){try{const result=await api('/work/structure/change',{project,expected_revision:structures.get().revision,
    operation,...extra});structures.set(result.state);forms.setDirty(false);views.renderStructure(ui.$('[data-main]').lastElementChild);
    discussion.session().scope();ui.notice('Structure saved through its canonical records.');}catch(error){if(error.result?.state){structures.set(
    error.result.state);views.renderStructure(ui.$('[data-main]').lastElementChild);}else{try{structures.set(await api(
    '/work/structure?project='+enc));views.renderStructure(ui.$('[data-main]').lastElementChild);}catch(_){}}throw error;}}
  async function inspectReaderOccurrence(occurrence) {
    const row = {
      file: occurrence.file,
      line: occurrence.line_start,
      line_end: occurrence.line_end,
      basis: occurrence.basis,
      source_read: occurrence.read
    };
    const version = views.generation(),
    observed = await inspectSourceOccurrence(row, project);
    if (version !== views.generation()) return;
    place.remember();
    await views.show('manuscript', false);
    if (views.current() !== 'manuscript') return;
    const shown = views.generation(),
    walk = await waitForManuscript({
      getWalk: () => manuscript.sourceWindow()?.walk,
      isCurrent: () => views.current() === 'manuscript' && views.generation() === shown
    });
    if (!walk) return;
    const body = walk.sourceObservation?.()?.source_observation,
    edits = walk.editState?.();
    const matches = walk.blocks({
      text: false
    }).filter(block => (block.repo_file || block.file) === row.file && block.line_start >= row.line && block.line_end <= row.line_end &&
      JSON.stringify(block.spec_ids || []) === JSON.stringify(occurrence.spec_ids || []));
    const current = body?.selection_identity === row.basis.selection_identity && 'sha256:' + body?.file_revisions?.[row.file] === row.basis.source_digest;
    if (current && matches.length === 1 && !manuscript.editor().hasDraft() && !edits?.dirty && !edits?.parked) {
      manuscript.editor().showWrite();
      walk.jumpToBlock(matches[0].id);
    } else await manuscript.editor().openSource(row.file, row.line, false, row.basis, observed);
    if (occurrence.spec_ids?.length > 1) ui.notice('This source passage realises ' + occurrence.spec_ids.length + ' planned units.');
  }
  async function inspectReaderLink(handle, label = 'Reader-plan input') {
    if (handle?.operation === 'structure') {
      if (handle.payload?.view === 'architecture-profile') return inspectArchitecturePrior({
        value: {
          read_more: handle
        },
        read: read => api(spineReadURL(read, project)),
        opener: document.activeElement
      });
      const target = ownerHumanTarget(spineReadURL(handle, project));
      return inspect.ownerRead(target, label);
    }
    if (handle?.operation === 'author_history') {
      const target = passageHistoryRead(handle, project);
      if (!target) throw Error('The retained record has no exact history address.');
      return inspect.ownerRead(target, label);
    }
    const target = qualifiedOwnerHTTP(handle, project);
    if (!target) throw Error('This input has no supported qualified reader. Refresh the plan item to inspect its current owner links.');
    if (target.owner) return inspect.ownerRead(target.owner, label);
    if (target.artifact) return inspect.projectArtifact(target.artifact.path, label, target.artifact);
    if (target.research) {
      place.remember();
      return research.openEvidence(target.research.id);
    }
    if (target.literature) {
      place.remember();
      return research.openSource({
        key: target.literature.key,
        mode: 'source'
      });
    }
    place.remember();
    await views.show('manuscript', false);
    return manuscript.editor().openSource(target.source.file);
  }
  function inspectPreparationFailure(value) {
    const opener = document.activeElement;
    const dialog = E('dialog', '', 'spine-binding-dialog');
    dialog.append(ui.button('Close', () => dialog.close()));
    renderPreparationFailure(dialog, value, {project,
      onArtifact: inspect.projectArtifact,
      onWork: async id => {dialog.close();await work.open(id);}, status: ui.notice});
    dialog.addEventListener('close', () => {
      dialog.remove();if (opener?.isConnected) opener.focus({preventScroll:true});
    });
    showReaderDialog(dialog, opener);
  }
  async function prepareStoryboardWork(action, section) {
    const view = views.generation();
    const payload = preparedWorkSubmission(action, project, [section.id]);
    let receipt;
    try {
      receipt = preparedWorkReceipt(await api(action.http.route, payload), project);
    } catch (error) {
      if (!error.result?.preparation_publication || !ui.root.isConnected) throw error;
      if (view !== views.generation()) {
        ui.notice(error.message, true);
        ui.$('[data-notice]').append(ui.button('Inspect retained preparation', () => inspectPreparationFailure(error.result)));
      } else inspectPreparationFailure(error.result);
      return null;
    }
    if (view !== views.generation() || !ui.root.isConnected) {
      if (ui.root.isConnected) {
        ui.notice('Reader-plan Work was prepared.');
        ui.$('[data-notice]').append(ui.button('Open prepared Work', () => work.open(receipt.work_id)));
      }
      return receipt;
    }
    const opener = document.activeElement;
    const dialog = E('dialog', '', 'spine-binding-dialog');
    const close = ui.button('Close', () => dialog.close());
    dialog.append(E('h2', 'Work prepared'), E('p', 'Preparation starts no provider.'), close);
    renderPreparedWork(dialog, {
      project, task: receipt.task, preparation: receipt.preparation,
      execution: receipt.execution, artifact: receipt.artifact, action: receipt.run_action,
      onUse: async (run, task) => {
        await discussion.session().usePreparedWork(run, task);
        dialog.close();discussion.open(true);
      },
      onWork: async id => {dialog.close();await work.open(id);},
      onArtifact: inspect.projectArtifact,
      onConversation: async id => {dialog.close();await discussion.conversation(id);},
      onTurn: discussion.savedTurn,
      status: ui.notice
    });
    dialog.addEventListener('close', () => {
      dialog.remove();if (opener?.isConnected) opener.focus({preventScroll:true});
    });
    showReaderDialog(dialog, opener);
    return receipt;
  }
  async function renderReaderPlanHome(host, version = views.generation()) {
    const controller = await mountReaderPlan(host, {
      project,
      request: api,
      initial: readerPlanMemory,
      status: ui.notice,
      onGenerateProfile: discussion.generateProfile,
      onScope: scope => {
        if (views.current() !== 'reader-plan' || version !== views.generation()) return;
        readerPlanMemory.sectionId = scope.beat_id ? null: scope.section_ids?.[0] || null;
        readerPlanMemory.beatId = scope.beat_id || null;
        const uri = new URL(location.href);
        uri.searchParams.set('view', 'reader-plan');
        uri.searchParams.delete ('structure');
        uri.searchParams.delete ('node');
        if (readerPlanMemory.beatId) uri.searchParams.set('beat', readerPlanMemory.beatId);
        else uri.searchParams.delete ('beat');
        if (readerPlanMemory.sectionId) uri.searchParams.set('section', readerPlanMemory.sectionId);
        else uri.searchParams.delete ('section');
        history.replaceState({}, '', uri);
        discussion.session().scope();
      },
      onPrepareWork: prepareStoryboardWork,
      onSource: manuscript.openBoundSource,
      onRead: inspectReaderLink,
      // a claim input opens the existing Literature view situated on that claim (research.openLiterature -> setTarget)
      onLiterature: target => research.openLiterature(target),
      onOccurrence: inspectReaderOccurrence,
      onReview: async prepared => {
        let target = readerReviewReceipts.get(prepared);
        if (!target) {
          let result;
          try {
            result = await api('/work/task', readerReviewSubmission(prepared, project));
          } catch (error) {
            throw Error(error.message + ' Inspect Work before submitting another review request.');
          }
          target = qualifiedOwnerHTTP(result.read_handle, project);
          if (target?.owner?.kind !== 'work' || !target.owner.id) throw Error(
            'Review work was recorded but its exact reading handle is unavailable. Inspect Work before creating another item.');
          readerReviewReceipts.set(prepared, target);
        }
        place.remember();
        try {
          await work.open(target.owner.id);
        } catch (error) {
          throw Error('Review work was created. Its view could not open: ' + error.message + ' Do not create it again.');
        }
      },
      onConcept: async id => {
        place.remember();
        await argument.openConcept(id, {view: 'argument'});
      },
      onEvidence: async id => {
        place.remember();
        await research.openEvidence(id);
      },
      onWork: async id => {
        place.remember();
        await work.open(id);
      },
      onChanged: async result => {
        structures.set(null);
        discussion.session().scope();
        const receipt = planPublicationDisposition(result);
        if (receipt) ui.notice(receipt.message, !!receipt.warnings.length);
      },
      onEdit: (section, detail) => editReaderPlanItem({
        project,
        section,
        isCurrent: () => views.current() === 'reader-plan' && version === views.generation(),
        fullGuardRead: detail.full_guard_read,
        request: api,
        opener: document.activeElement,
        onSaved: async (result, id) => {
          readerPlanMemory.sectionId = id;
          await readerPlanController?.refresh();
          const receipt = planPublicationDisposition(result);
          ui.notice(receipt?.message || 'Reader-plan item saved.', !!receipt?.warnings.length);
        }
      }),
      onCreate: summary => editReaderPlanItem({
        project,
        isCurrent: () => views.current() === 'reader-plan' && version === views.generation(),
        fullGuardRead: summary.full_guard_read,
        request: api,
        opener: document.activeElement,
        onSaved: async (result, id) => {
          readerPlanMemory.sectionId = id;
          await views.show('reader-plan', false);
          const receipt = planPublicationDisposition(result);
          ui.notice((receipt?.message || 'Reader-plan item created.') + ' Link its source heading when ready.', !!receipt?.warnings.length);
        }
      })
    });
    if (version !== views.generation() || views.current() !== 'reader-plan') {
      controller.destroy();
      return;
    }
    readerPlanController = controller;
    readerPlanMemory = controller.capture();
    discussion.session().scope();
  }
  return {
    render:renderReaderPlanHome,plan,openSection:openPlanSection,
    // open the plan with no section selected (a heading or passage with no unique plan item)
    openUnselected:(memory={sectionId:null})=>{readerPlanMemory=memory;return views.show('reader-plan',false);},
    context:()=>readerPlanController?.context()||null,
    capture:()=>readerPlanController?.capture()||readerPlanMemory,
    restore:memory=>{readerPlanMemory=memory;},
    release:()=>{if(readerPlanController){readerPlanMemory=readerPlanController.capture();readerPlanController.destroy();readerPlanController=null;}},
  };
}
