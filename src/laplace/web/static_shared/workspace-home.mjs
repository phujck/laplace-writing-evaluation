import {historyQuery,historyTime} from './workspace-history.mjs';
import {taskStateChips} from './workspace-work-navigator.mjs';
import {stateChip,completedTaskChip,declareControl} from './workspace-presentation.mjs';
import {historyTargetUnavailable} from './workspace-activity.mjs';
// WORKSPACE HOME (M5 S2 F1). Purpose: the Home and Settings views of the shell and the project metadata they
// show: the project home (workspace-app's project home and title controllers, the selected or requested Work,
// Next ready, the working argument), Settings (the project home controller, the writing-style panel and the
// page diagnostics), the one project-metadata read with its ticket, and the project library. Ownership:
// metadata, guidance, the writing profile and Work belong to their owners; this controller owns only the
// mounted home, title and writing-style controllers, the overview refresh, the metadata ticket and the
// library read. Public contract: mountHomeView(project, services) -> {renderOverview(host),
// renderSettings(host), acceptMetadata(value), refreshMetadata(), library(), refreshOverview(state),
// refreshHome(), refreshStyle(), release()}. Services: views (current view, show, project info), forms, ui,
// workState, work (selection), manuscript (the frame), inspect, discussion, help (open the guide),
// diagnostics (page counters and diagnostics), navigation (refresh the capability navigation). Lifetime:
// release() destroys the mounted controllers when the view is left; a ticket drops late metadata replies.
import {E,area,field,section} from './workspace-dom.mjs';
import {projectRequest as api} from "/shared/workspace-session.mjs";
import {mountProjectSettings,mountProjectTitle} from "/shared/workspace-project.mjs";
import {mountStorage} from "/shared/workspace-material.mjs";
import {mountWritingStyle as mountWritingStylePanel} from "/shared/workspace-writing-style.mjs";
import {workCountSummary} from "/shared/workspace-work.mjs";

export function homeActivityPresentation(row={}){
 const setup=row.owner==='concept'&&/project scaffolded through the new project door/i.test(row.summary||'');
 const operation={store_artifact:'File save attempt recorded',read_artifact:'File reading attempt recorded',apply_revision:'Writing change attempt recorded',task:'Task update attempt recorded',task_status:'Task status update attempt recorded',literature_import:'Source import attempt recorded'}[row.operation];
 const qualification=({failed:' — failed',error:' — failed',refused:' — refused',denied:' — refused',unknown:' — outcome unknown',partial:' — partial outcome'})[String(row.status||'').toLowerCase()]||'';
 const sentence=row.event_kind==='tool-attempt'?(operation||'Action attempt recorded')+qualification+'.':row.owner==='editor-save'?'Writing saved.':({session:'Conversation event recorded.',manuscript:'Writing event recorded.',research:'Research event recorded.',literature:'Source event recorded.',formal:'Formal-check event recorded.',settings:'Preference event recorded.',notes:'Note recorded.'})[row.category]||'Project event recorded.';
 return {setup,sentence};
}

export function mountHomeView(project,{enc,views,forms,ui,workState,work,manuscript,inspect,discussion,help,diagnostics,navigation,activity:activityOwner}){
  // the domain's own memory (moved out of the shell closure)
  let writingStyleController=null,
    projectHomeController=null,
    projectTitleController=null,
    projectOverviewRefresh=null,
    projectMetadataRead=0,
    library=null;
  function acceptProjectMetadata(value){if(value.project!==project||typeof value.title!=='string')return;projectMetadataRead++;views.info(
    ).title=value.title;if(value.capabilities){views.info().capabilities=value.capabilities;views.info().source_optional=value.source_optional;
    views.info().layout=value.layout;}const row=library?.projects?.find(item=>item.name===project);if(row){row.title=value.title;if(
    value.capabilities)Object.assign(row,{capabilities:value.capabilities,source_optional:value.source_optional,layout:value.layout});}ui.$(
    'h1').textContent=value.title;projectTitleController?.updateSaved(value);if(typeof navigation.refresh==='function')navigation.refresh();}
  async function refreshProjectMetadata(){const ticket=++projectMetadataRead;const value=await api('/projects/metadata?project='+enc);if(
    ticket===projectMetadataRead)acceptProjectMetadata(value);}
  async function projectLibrary(){if(!library)library=await api('/projects/library');return library;}
  async function renderOverview(host){
    let f=workState.get().framing,framing=f.framing||{};
    host.classList.add('project-home');host.replaceChildren();
    // HOME PAGE SHAPE (wave 5). Order: the title and the purpose, whole; Continue writing with the edition line; then
    // groups drawn as a top rule and a heading (what waits for him, the next ready task, observed activity only when
    // the Work summary observes it, what finished); then the routes; then recent events that name a destination.
    // Every count and state word is the Work owner's (counts and rows of the summary read, chips from presentation).
    const group=(label,cls='')=>{const g=E('section','','project-home-group'+(cls?' '+cls:''));g.append(E('h3',label));return g;};
    // wave 6 (H1): a task named on Home opens. Its title is a link to that task in Tasks; a plain click opens it exactly as
    // 'Open next task' does (work.open: the same route and selection, beside the list); the whole row is its target (CSS)
    const taskRow=(task,chip,opens=true)=>{const line=E('div','','project-home-row'),name=task.title||task.id;let title;
      if(opens&&task.id){title=declareControl(E('a',name,'project-home-row-title'),'home:task-title',task.id);title.dataset.workId=task.id;title.setAttribute('aria-label','Open task · '+name);
        try{const uri=new URL(globalThis.location?.href||'http://local/project');uri.searchParams.set('view','work');uri.searchParams.set('work',task.id);title.href=uri.pathname+uri.search;}catch{}
        title.onclick=event=>{if(event?.button||event?.metaKey||event?.ctrlKey||event?.shiftKey||event?.altKey)return;event?.preventDefault?.();work.open(task.id);};}
      else title=E('span',name,'project-home-row-title');
      line.append(title);if(chip)line.append(stateChip(chip));return line;};
    const hero=E('header','','project-home-heading');hero.append(E('div','Project home','eyebrow'));const titleHost=E('div','',
      'project-title-heading');hero.append(titleHost);projectTitleController=mountProjectTitle(titleHost,{project,title:views.info().title||project,
      request:api,onDirty:value=>{forms.setDirty(value||!!writingStyleController?.hasDraft||!!projectHomeController?.hasDraft||
      !!ui.root.querySelector('[data-workspace-form-dirty="true"]'));},onSaved:acceptProjectMetadata});const purpose=E('p',framing.purpose||
      'Set the purpose and intended reader for this project.','project-home-purpose');hero.append(purpose);
    const lead=E('div','','work-actions project-home-lead');if(views.info().capabilities?.manuscript)lead.append(declareControl(ui.button('Continue writing',()=>views.show(
      'manuscript'), 'primary'),'home:continue-writing'));else if(views.info().capabilities?.start_manuscript)lead.append(ui.button('Add manuscript',async()=>{await api(
      '/projects/start',{project,title:views.info().title||project,kind:views.info().source_optional?'paper':workState.get(
      ).form==='book'?'book':'paper'});location.reload();},'primary'));
    // a selected manuscript without a reader-plan owner: the lifecycle owner's own next action, guard included
    // (writing.project_lifecycle start_authoring); the page never composes a guard of its own
    if(views.info().capabilities?.start_planning)lead.append(ui.button('Start reader plan',async()=>{const next=views.info()
      .authoring_lifecycle?.next_action;if(next?.operation!=='structure_change')throw Error('Read the project again: no planning action is offered.');
      await api('/work/structure/change',{project,...next.payload});location.reload();}));
    const edition=E('p',views.info().capabilities?.manuscript?'Working manuscript · '+(views.info().edition||workState.get().form||
      'Document'):views.info().source_optional?'Writing is optional. Tasks, sources and conversations are ready.':'No selected manuscript yet',
      'project-home-edition');lead.append(edition);if(views.info().root){const source=E('details','','project-home-file'),path=E('p',views.info().root,
      'project-source-path');source.append(declareControl(E('summary','Writing file details'),'home:writing-file-details'),path);lead.append(source);}hero.append(lead);host.append(hero);
    const state=workState.get()||{},counts=state.counts||{},known=n=>Number.isInteger(n)&&n>=0,rows=state.tasks||[];
    const groups=E('div','','project-home-groups'),routes=E('div','','work-actions project-home-routes');host.append(groups);
    const openTasks=declareControl(ui.button('Open tasks',()=>views.show('work')),'home:open-tasks');
    // what waits for him: the owner's count, a few of its rows from the summary page, and the door into Tasks, whose
    // list leads with Needs attention (workspace-work-navigator.mjs paintAttention)
    if(known(counts.completed_review_required)&&counts.completed_review_required>0){const waiting=group('Waiting for you','project-home-waiting');
      waiting.append(E('p',counts.completed_review_required+' completed tasks need current review.','project-home-count'));for(const task of rows.filter(
      row=>row.current_acceptance?.review_required===true).slice(0,3))waiting.append(taskRow(task,completedTaskChip(task)));waiting.append(openTasks);
      groups.append(waiting);}else routes.append(openTasks);
    // the selected or requested Work leads; Next ready is offered beside it, never in its place
    const chosen=work.task(),requested=work.requested(),refused=requested?.state==='refused';
    if(chosen||refused||state.next){const next=group(chosen?'Selected task':refused?'Requested task':'Next ready task','project-home-next');
      if(chosen)next.append(E('p',chosen.title,'project-home-task-title'),ui.button('Open selected task',()=>work.open(chosen.id),'primary'));
      else if(refused){const asked=requested.id;next.append(E('p','Requested task '+asked+' is not available: '+requested.reason,'error'),ui.button(
        'Retry requested task',async()=>{await work.admit(asked);if(views.current()==='overview')await views.show('overview',false,{reuseState:true});},
        'primary'),ui.button('Clear request',async()=>{await work.request(null);if(views.current()==='overview')await views.show('overview',false,
        {reuseState:true});}));}
      // V6: the Work owner's next ready task is the owner-issued next step; it alone carries the primary style on Home
      if(state.next){const nextTask=declareControl(ui.button('Open next task',()=>work.open(workState.get().next.id),chosen||requested?'':'primary'),'home:open-next-task');
        if(!chosen&&!requested)nextTask.dataset.ownerNext='work-next';next.append(E('p',chosen||refused?'Next ready task: '+state.next.title:state.next.title,
        'project-home-task-title'),nextTask);}
      if(known(counts.pending))next.append(E('p',counts.pending+' pending tasks.','muted'));groups.append(next);}
    else if(known(counts.pending))routes.append(E('p',counts.pending+' pending tasks.','muted project-home-route-note'));
    // observed activity: only rows the Work summary itself reports running; when none is observed nothing is drawn
    const observed=rows.filter(row=>row.activity?.state==='RUNNING'||(row.standing?.facts||[]).some(f=>f.code==='observed-running'));
    if(observed.length){const running=group('Observed activity','project-home-running');   // the owner's group label (workspace-presentation GROUP_LABELS.active)
      for(const task of observed){const line=taskRow(task,null,false);line.append(...taskStateChips(task).map(stateChip),ui.button('Open task',()=>work.open(task.id)));
        running.append(line);}groups.append(running);}
    // what finished: the owner's count and a few completed rows in the owner's order (the row carries no completion time)
    if(known(counts.completed)&&counts.completed>0){const done=group('Finished','project-home-finished');done.append(E('p',counts.completed+
      ' recorded completions.','project-home-count'));for(const task of rows.filter(row=>row.lifecycle?.completed===true&&row.current_acceptance?.
      review_required!==true).slice(0,3))done.append(taskRow(task,completedTaskChip(task)));groups.append(done);}
    if(!['pending','completed','completed_review_required'].some(key=>known(counts[key])))routes.append(E('p',workCountSummary(state),'muted project-home-route-note'));
    if(views.info().capabilities?.concepts)routes.append(declareControl(ui.button('Open questions',()=>views.show('structure')),'home:open-questions'));
    routes.append(declareControl(ui.button('All activity',()=>activityOwner?.openAll?activityOwner.openAll():views.show('history')),'home:all-activity'),declareControl(ui.button('Open conversation',
      ()=>discussion.open(true)),'home:open-conversation'),declareControl(ui.button('Take the guided tour',()=>help.openGuide()),'home:guided-tour'));host.append(routes);
    // recent saved events that name something to open, one compact line each; the rest stay in All activity
    const recentGroup=E('section','','project-home-group project-home-recent');recentGroup.append(E('h3','Recent activity'));const recent=E('div','',
      'project-recent-records'),note=E('p','Reading recent saved events…','muted');ui.pending?.(note);recentGroup.append(note,recent);host.append(recentGroup);
    const brief=E('details','','project-home-brief');brief.append(declareControl(E('summary','The brief'),'home:brief'));host.append(brief);const facts=E('dl','','project-brief-facts');const paintBrief=()=>{purpose.textContent=framing.purpose||
      'Set the purpose and intended reader for this project.';facts.replaceChildren();for(const [label,value]of [['Reader',framing.audience],[
      'Central question',framing.question],['Form',views.info().source_optional&&!views.info().capabilities?.manuscript?'':workState.get().form]])if(
      value)facts.append(E('dt',label),E('dd',value));};paintBrief();brief.append(facts);projectOverviewRefresh=next=>{f=next.framing;framing=f.framing||{};paintBrief();};
    const editBrief=E('details');editBrief.append(declareControl(E('summary',views.info().source_optional&&!views.info(
      ).capabilities?.manuscript?'Edit purpose and audience':'Edit purpose, reader and form'),'home:edit-brief'));brief.append(editBrief);editBrief.ontoggle=()=>{if(
      !editBrief.open||editBrief.dataset.mounted)return;editBrief.dataset.mounted='true';const formBasis=f;const form=E('form');area(form,'Purpose',
      'purpose',framing.purpose);field(form,'Reader','audience',framing.audience);area(form,'Central question','question',framing.question);if(
      !views.info().source_optional||views.info().capabilities?.manuscript)declareControl(field(form,'Form','form',workState.get().form||'book',[['book','Book'],[
      'article','Article'],['report','Report'],['briefing','Briefing'],['custom','Custom']]),'home:form');form.append(declareControl(E('button','Save framing','primary'),'home:save-framing'));
      forms.wire(form,async data=>{await api('/work/framing',{project,base_revision:formBasis.revision,...data});await forms.changed(
      'Framing saved; structure and future sessions use this version.');});editBrief.append(form);};
    const argument=E('details');argument.append(declareControl(E('summary',f.argument?'Read and edit the working argument':'Develop the working argument'),'home:argument-open'));
      brief.append(argument);argument.ontoggle=async()=>{if(!argument.open||argument.dataset.mounted)return;argument.dataset.mounted='true';if(
      f.argument){const body=E('div','','project-argument-reading');argument.append(body);await inspect.savedMarkdown(body,f.argument);}const edit=E(
      'details');edit.append(declareControl(E('summary','Edit working argument'),'home:edit-argument'));argument.append(edit,declareControl(ui.button('Work through the argument',()=>{
      work.clearSelection();discussion.talk();}),'home:work-argument'));edit.ontoggle=()=>{if(!edit.open||edit.dataset.mounted)return;edit.dataset.mounted='true';
      const argumentBasis=f;const af=E('form');area(af,'Working argument','argument',f.argument||'',10);af.append(declareControl(E('button','Save argument',
      'primary'),'home:save-argument'));forms.wire(af,async data=>{await api('/authoring/argument',{project,base_revision:argumentBasis.revision,...data});
      await forms.changed('Argument saved.');});edit.append(af);};};
    const documentPanel=E('details','','project-home-manuscript');documentPanel.hidden=views.info().source_optional&&!views.info(
      ).capabilities?.manuscript;documentPanel.append(declareControl(E('summary','Manuscript selection and setup'),'home:document-setup'));host.append(documentPanel);
    if(views.info().read_only)documentPanel.append(E('p','This imported source is read-only.','muted'));
    if(views.info().candidates?.length>1){documentPanel.ontoggle=()=>{if(!documentPanel.open||documentPanel.dataset.mounted)return;
      documentPanel.dataset.mounted='true';const ef=E('form','','work-form');const edition=field(ef,'Working edition','root',views.info().root,
      views.info().candidates.map(c=>[c.root||c.path,c.label||c.root||c.path]));ef.append(E('button','Use this edition'));ef.onsubmit=forms.guard(
      async()=>{manuscript.saved();await api('/authoring/edition',{project,root:edition.value});location.reload();});documentPanel.append(ef);};
      }else documentPanel.append(E('p',views.info().root||'No manuscript source has been selected.','project-source-path'));

    if(workState.get().project_protocol?.documents?.length){const guides=E('details','','project-home-guides');guides.append(E('summary',
      'Project instructions and supporting documents'));host.append(guides);guides.ontoggle=()=>{if(!guides.open||guides.dataset.mounted)return;
      guides.dataset.mounted='true';for(const document of workState.get().project_protocol.documents){const role={instructions:'Project instructions',
      handoff:'Handoff',background:'Background'}[document.role]||'Project document';const row=E('div','','project-guide-row');row.append(E('strong',
      role),ui.button(document.path,async()=>{if(typeof document.content==='string'){if(row.dataset.read)return;row.dataset.read='true';const body=E(
      'div','','project-argument-reading');row.append(body);await inspect.savedMarkdown(body,document.content);}else await inspect.projectArtifact(
      document.path,role);}));guides.append(row);}};}
    try{const value=await api(historyQuery(project,{limit:6}));if(!host.isConnected||views.current()!=='overview')return;if(value.project!==undefined&&value.project!==project||!Array.isArray(value.items))throw Error('Activity returned another project or an unsupported page.');
      let shown=0;const seen=new Set();
      for(const row of value.items){const presentation=homeActivityPresentation(row);if(presentation.setup||shown>=5)continue;
        // a row that names nothing to open says only '… recorded.': it stays in All activity, not on Home
        const destinations=[];for(const target of row.targets||[]){const name=target.label||target.artifact_path||target.file||target.id;if(!name||historyTargetUnavailable(target)||!activityOwner?.openTarget)continue;destinations.push(['Open '+name,()=>activityOwner.openTarget({...target,history_id:row.id})]);}
        if(row.conversation?.session_id&&activityOwner?.openConversation)destinations.push(['Open recorded conversation',()=>activityOwner.openConversation(row.conversation)]);
        if(!destinations.length)continue;
        // wave 6 (H2): rows whose sentence, shown time and destinations are identical are shown once; a conversation's title
        // is shown when the owner's event names it
        const when=row.at?historyTime(row.at,{date:true})+' · '+historyTime(row.at):'',talkTitle=typeof row.conversation?.title==='string'?row.conversation.title.trim():'';
        const key=[presentation.sentence,when,talkTitle,row.conversation?.session_id||'',...(row.targets||[]).map(target=>target.id||target.artifact_path||target.file||target.label||''),...destinations.map(([label])=>label)].join('\u241f');
        if(seen.has(key))continue;seen.add(key);shown++;
        const card=E('div','','project-recent-record'),said=E('p',presentation.sentence+(talkTitle?' '+talkTitle:''),'project-recent-said');if(when)said.append(E('small',' · '+when,'muted'));card.append(said);
        const action=(label,run)=>{const button=E('button',label);declareControl(button,'home:recent-open',row.id);button.type='button';let opening=false;button.onclick=async()=>{if(opening)return;opening=true;try{await run();}catch(error){if(host.isConnected&&views.current()==='overview'){note.hidden=false;note.textContent=error.message;}}finally{opening=false;}};card.append(button);return button;};
        for(const [label,run]of destinations)action(label,run);
        const exact=E('details'),summary=declareControl(E('summary','Event details'),'home:event-details',row.id);exact.append(summary);if(row.summary)exact.append(E('p',row.summary));card.append(exact);
        if(row.id){const read=declareControl(E('button','Read event record'),'home:read-event-record',row.id);read.type='button';let opening=false;read.onclick=async()=>{if(opening)return;opening=true;try{await inspect.ownerRead({operation:'author_history',payload:{view:'record',id:row.id},http:{method:'GET',url:historyQuery(project,{},row.id,'record')}},row.summary||'Saved event',{isCurrent:()=>host.isConnected&&views.current()==='overview'});}catch(error){if(host.isConnected&&views.current()==='overview'){note.hidden=false;note.textContent=error.message;}}finally{opening=false;}};exact.append(read);}recent.append(card);}
      note.textContent='';note.hidden=true;recentGroup.hidden=!shown;
    }catch(error){if(host.isConnected&&views.current()==='overview')note.textContent='Recent activity could not be read. Your project and drafts are unchanged. '+error.message;}
  }
  async function renderSettings(host){host.replaceChildren(E('h2','Settings'));const settings=E('section','','work-card'),activity=null;mountStorage(
    host,{project,request:api});host.append(settings);
    if(diagnostics.page)import('./workspace-diagnostics.mjs').then(({mountDiagnostics})=>{if(host.isConnected)mountDiagnostics(host,{read:diagnostics.counters});});
    const controller=await mountProjectSettings(settings,{project,request:api,activityHost:activity,renderText:inspect.savedMarkdown,onDirty:value=>{
      forms.setDirty(value||!!projectTitleController?.hasDraft||!!writingStyleController?.hasDraft||!!ui.root.querySelector(
      '[data-workspace-form-dirty="true"]'));},onEditStyle:mountWritingStyle,onUseStage:text=>{discussion.open(true);const input=discussion.session(
      ).find('[data-message]');if(!input.value.includes(text)){input.value=[input.value.trimEnd(),text].filter(Boolean).join('\n\n');
      discussion.session().persistComposerDraft(input.value);}input.focus();discussion.session().scope();discussion.session().status(
      discussion.session(
      ).active?'Stage request prepared. Send will steer the running conversation; choose another conversation to start separately.':
      'Stage request prepared. Review it, then Send to begin.');},saveDefaults:values=>discussion.session().saveProjectDefaults(values),
      onOpenConversation:async id=>{discussion.open(true);await discussion.session().openConversation(id);},onResearch:()=>views.show('research'),
      onHistory:()=>views.show('history')});if(!host.isConnected){controller.destroy();return;}projectHomeController=controller;
  }
  async function mountWritingStyle(host){
    const card=E('section','','work-card');host.append(card);const controller=await mountWritingStylePanel(card,{project,projectForm:workState.get(
      ).form||'',request:api,renderText:inspect.savedMarkdown,status:ui.notice,onDirty:value=>{forms.setDirty(value||
      !!projectTitleController?.hasDraft||!!projectHomeController?.hasDraft||!!ui.root.querySelector('[data-workspace-form-dirty="true"]'));},
      onChanged:async()=>{await work.reload();await projectHomeController?.refreshStyle();},onDiscuss:text=>discussion.talk(text),
      onGenerate:discussion.generateProfile,onModels:()=>{discussion.open(true);discussion.session().openInspector('settings');discussion.session(
      ).find('[data-model]').focus();}});if(!card.isConnected){controller.destroy();return;}writingStyleController=controller;
  }
  return {
    renderOverview,renderSettings,acceptMetadata:acceptProjectMetadata,refreshMetadata:refreshProjectMetadata,library:projectLibrary,
    refreshOverview:value=>projectOverviewRefresh?.(value),refreshHome:()=>projectHomeController?.refresh(true),
    refreshStyle:()=>projectHomeController?.refreshStyle(),
    release:()=>{projectOverviewRefresh=null;projectTitleController?.destroy();projectTitleController=null;
      projectHomeController?.destroy();projectHomeController=null;writingStyleController?.destroy();writingStyleController=null;},
  };
}
