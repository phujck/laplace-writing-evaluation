// WORKSPACE FIGURES (M5 S2 F1). Purpose: the Figures & output view of the shell (workspace-output's
// mountOutput with the document-draft admission of the manuscript editor) and placing one visual spec into
// the manuscript through the figure placement owner with exact source guards. Ownership: figures, specs,
// builds and source belong to their owners; this controller owns no state. Public contract:
// mountFiguresView(project, services) -> {render(host), place(spec)}. Services: views (show), forms (dirty),
// ui (notice, button), manuscript (the frame), research (evidence), inspect (project artifact), discussion
// (talk), workState (reload).
import {E,field} from './workspace-dom.mjs';
import {projectRequest as api} from "/shared/workspace-session.mjs";
import {hasStoredSourceDraft} from './manuscript-editor.mjs';
import {mountOutput} from "/shared/workspace-output.mjs";
import {requireSourceCompletion} from './source-effect.mjs';

// The placement owner's own currentness when it refuses a stale drawing or evidence basis, as one reader sentence and
// the single next step. Pure (no request, no retry); a refusal without currentness keeps the owner message unchanged.
export function figurePlacementRefusal(error){
  const currentness=error?.result?.currentness,words=value=>String(value||'not reported').toLowerCase().replaceAll('_',' ');
  if(!currentness)return String(error?.message??error);
  // Each fact is tri-state: a REPORTED stale drawing or unbound evidence keeps its specific repair; an absent or unknown
  // fact is a request to inspect the owner's current status, never an instruction to re-render or rebind on a guess.
  const drawing=String(currentness.drawing_freshness||currentness.status||'').toUpperCase(),evidence=String(currentness.evidence_binding_status||'').toUpperCase();
  const unknown=value=>!value||value==='UNKNOWN'||value==='NOT_REPORTED';
  const drawingStale=!unknown(drawing)&&drawing!=='CURRENT',evidenceUnbound=!unknown(evidence)&&!['CURRENT','THEORY_ONLY'].includes(evidence);
  const missing=[unknown(drawing)&&'drawing freshness',unknown(evidence)&&'evidence binding'].filter(Boolean);
  const fixes=drawingStale&&evidenceUnbound?'Render the figure again and bind its current result':drawingStale?'Render the figure again':evidenceUnbound?'Bind the figure to its current research result':'';
  const inspect=missing.length?'The placement owner did not report the '+missing.join(' or ')+'; inspect the figure\'s current status before changing it':'';
  const next=fixes&&inspect?fixes+'. '+inspect+', then place it.':fixes?fixes+', then place it.':inspect?inspect+'.':'Inspect the figure before placing it.';
  return error.message+' Drawing '+words(currentness.drawing_freshness||currentness.status)+', evidence '+words(currentness.evidence_binding_status)+'. '+next;
}

export function mountFiguresView(project,{enc,views,forms,ui,manuscript,research,inspect,discussion,workState}){
  async function placeVisual(spec){
    manuscript.saved();const document=await api('/walk/doc?corpus='+enc);
    const options=(document.sections||[]).filter(s=>s.id!=='front'&&s.blocks?.some(b=>b.src?.file));
    if(!options.length)throw Error('Create a manuscript section before placing a visual.');
    const dialog=E('dialog','','workspace-dialog');dialog.append(E('h3','Place '+(spec.title||spec.id)),E('p',
      'Choose the section whose explanation this figure belongs to. Its source and caption will be included through the manuscript versioning door.'));
    const form=E('form','','work-form');const select=field(form,'Manuscript section','section','',[['','Choose a section'],...options.map(s=>[s.id,
      s.title])]);select.required=true;const actions=E('div','','work-actions');actions.append(E('button','Place figure','primary'),ui.button(
      'Cancel',()=>dialog.close()));form.append(actions);dialog.append(form);const message=E('p');dialog.append(message);
    form.onsubmit=async event=>{event.preventDefault();try{manuscript.saved();const section=options.find(s=>s.id===select.value),
      blocks=section.blocks.filter(b=>b.src?.file);const files=[...new Set(blocks.map(b=>b.src.file))];if(files.length!==1)throw Error(
      'This section spans several source files. Choose a more specific section.');if(!document.source_file_revisions?.[files[0]])throw Error(
      'Reload the manuscript source before placing this figure.');const result=await api('/visuals/place',{project,id:spec.id,file:files[0],
      expected_source_revision:document.source_revision,base_revision:document.source_file_revisions?.[files[0]],after_line:Math.max(...blocks.map(b=>
      b.src.line_end))});requireSourceCompletion(result,{project});dialog.close();if(manuscript.sourceWindow()?.walk?.ready(
      ))await manuscript.sourceWindow().walk.refresh();ui.notice(
      result.reused?'This visual is already present; no duplicate was inserted.':'Figure placed in '+section.title+(result.repo_file?' ('+result.repo_file+')':'')+'. Its caption is now authored manuscript text; build the PDF to see it on the page.');}catch(error){
      message.textContent=figurePlacementRefusal(error);message.className='error';}};
    dialog.onclose=()=>dialog.remove();window.document.body.append(dialog);dialog.showModal();select.focus();
  }
  async function renderPresentation(host){
    return mountOutput(host,{project,request:api,status:ui.notice,hasDocumentDraft:document=>manuscript.editor()?manuscript.editor().hasAnyDraft(
      document):hasStoredSourceDraft(project,document),admitDocumentBuild:document=>{if(manuscript.editor()?manuscript.editor().hasAnyDraft(
      document):hasStoredSourceDraft(project,document))throw Error('Save the current manuscript edits before building the PDF.');},
      onDocumentSetup:async()=>{await views.show('manuscript',false);manuscript.editor().openSetup();},
      onOpenSource:async()=>{await views.show('manuscript',false);},onOpenPassage:((...args)=>
      manuscript.inspectPassage(...args)),onOpenArtifact:inspect.projectArtifact,onDiscuss:text=>discussion.talk(text),onPlace:placeVisual,
      onEvidence:((...args)=>research.openEvidence(...args)),onDirty:value=>{forms.setDirty(value);},onChanged:async()=>{await workState.reload();if(
      manuscript.sourceWindow()?.walk?.ready())await manuscript.sourceWindow().walk.refresh();}});
  }
  return {render:renderPresentation,place:placeVisual};
}
