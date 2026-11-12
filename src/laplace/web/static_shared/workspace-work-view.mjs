// WORKSPACE WORK VIEW (M5 S2 F1). Purpose: the shell's Work selection and the Work view: the one selected
// Work (task) with its explicit intent and revisions, admitting a requested Work from the URL, refreshing the
// selection when a conversation observes Work, the paged Work choices for the authoring selectors, the Work
// summary reload, and mounting the Work controller (workspace-work's mountWork) with its memory. Ownership:
// Work records and their lifecycle belong to /work/state and /work/task; this controller owns only the
// selection (task, intent, requested Work), the choice pages and the mounted Work controller and memory.
// Public contract: mountWorkView(project, services) -> {render(host), reload(), select(row), admit(id),
// request(id, options), refresh(observation), open(id), task(), requested(), choices(), lookup(id),
// clearSelection(), hasDraft(), capture(), restore(memory), release()}; services.memory is a carried Work memory to start from and
// services.onCarriedRestored is called once, when the mounted controller's own select delivered the carried qualified Work
// (the carry's acknowledgement point; carriedTarget() names it while pending). Services: views, forms, ui, workState (the shell's Work summary
// read: get, set), inspect, discussion (session, conversation, saved turn), activity (open an owner history),
// place (the reader return), context (the conversation context). The mounted controller opens on the Work
// navigator (roots and branches; the flat list is secondary) and runs one observer (workspace-work-observer.mjs:
// the owner's semantic token, bounded backoff, paused while hidden) whose change hints the controller rereads.
// Lifetime: release() stops the observer, captures the Work memory and destroys the controller when the view is
// left; intent revisions drop late selections.
import {E,area,field} from './workspace-dom.mjs';
import {pendingRead} from './pending-read.mjs';
import {projectRequest as api,settingsTruthText} from "/shared/workspace-session.mjs";
import {mountOperatorWork,operatorHTTP} from "/shared/workspace-work.mjs";
import {observeWork} from "/shared/workspace-work-observer.mjs";
// wave 13 id sweep: control ids by tag and label (begin)
import {declareControl} from './workspace-presentation.mjs';
// wave 13 id sweep: control ids (end)

export function mountWorkView(project,{enc,initialQuery,views,forms,ui,workState,inspect,discussion,activity,place,context,memory:carried=null,onCarriedRestored=null}){
  // the domain's own memory (moved out of the shell closure)
  let task=null,
    explicitWorkIntent=initialQuery.has('work'),
    workIntentRevision=0,
    workRefreshRevision=0,
    requestedWork=null,
    workChoices=null,
    workChoicesLoading=null,
    workController=null,
    workMemory=carried&&typeof carried==='object'?carried:{},   // a page refresh's carried Work memory (frontend-basis.mjs), else empty
    carriedPending=workMemory===carried&&!!carriedTarget(carried),   // true until the carried Work's own selection is delivered
    renderTicket=0;
  // THE ADDED TASK (wave 7): the task just added (its id and containing path, root first) for the next render to show in the list;
  // its row once that render drew it (scrolled into view after the shell draws the page, which resets its scroll); and the Add task
  // form's 'Open now' line and choice, redrawn when the open task changes
  let pendingReveal=null,revealed=null,offerOpenNow=null;
  // THE WORK CATALOGUE for the authoring selectors (Sol 2026-10-12): the owner's summary pages
  // under one as_of. The first read is bounded (WORK_CHOICE_PAGES pages of 100) and keeps the
  // owner's continuation handle, so "More work choices" continues from exactly where it stopped
  // instead of discarding it; a typed exact id is looked up at the owner (view=detail) and
  // offered as a choice; the memo (rows + continuation) is reused on reopen and invalidated by
  // any Work change (reloadState). A CHANGED_INPUT refusal on a continuation restarts from the
  // first page once, re-reading at least as many rows as were already offered.
  const WORK_CHOICE_PAGES=6,WORK_CHOICE_LIMIT=100;  const firstChoicesPage=()=>'/work/state?'+new URLSearchParams({project,view:'summary',limit:WORK_CHOICE_LIMIT});
  const choiceRow=row=>({id:row.id,title:row.title||row.id,status:row.status||null});
  async function readChoicePages(memo,pages){
    let read=0;
    while(memo.next&&read<pages){const page=await api(memo.next);read++;memo.pages++;for(const row of page.tasks||[])if(row?.id&&!memo.seen.has(
      row.id)){memo.seen.add(row.id);memo.rows.push(choiceRow(row));}memo.next=page.pagination?.next_read?operatorHTTP(page.pagination.next_read):null;}
    return memo;
  }
  const freshChoices=()=>({rows:[],seen:new Set(),pages:0,next:firstChoicesPage(),get truncated(){return !!this.next;}});
  async function loadWorkChoices({more=false}={}){
    if(workChoicesLoading)await workChoicesLoading;
    if(workChoices&&!more)return workChoices;
    const target=more&&workChoices?Math.ceil((workChoices.rows.length+1)/WORK_CHOICE_LIMIT):WORK_CHOICE_PAGES;
    workChoicesLoading=(async()=>{
      try{
        if(more&&workChoices){try{return workChoices=await readChoicePages(workChoices,1);}catch(error){if(!/CHANGED_INPUT/.test(error.message))throw error;}}
        try{return workChoices=await readChoicePages(freshChoices(),target);}
        catch(error){if(!/CHANGED_INPUT/.test(error.message))throw error;return workChoices=await readChoicePages(freshChoices(),target);}
      }finally{workChoicesLoading=null;}
    })();
    return workChoicesLoading;
  }
  async function lookupWorkChoice(id){
    const value=await api('/work/state?'+new URLSearchParams({project,view:'detail',id}));
    if(value?.project!==project||value.view!=='detail'||value.task?.id!==id)throw Error('The Work owner has no item with that exact id.');
    const row=choiceRow(value.task);if(workChoices&&!workChoices.seen.has(row.id)){workChoices.seen.add(row.id);workChoices.rows.push(row);}
    return row;
  }
  async function reloadState(){const intent=workIntentRevision,id=task?.id;workChoices=null;workState.set(await api(workState.summaryRead));if(
    intent!==workIntentRevision||id!==task?.id)return;if(task){let owned=workState.get().tasks.find(row=>row.id===task.id);if(!owned){try{owned=(
    await api('/work/state?'+new URLSearchParams({project,view:'detail',id:task.id}))).task;}catch(error){ui.notice(
    'Selected work could not be recovered: '+error.message,true);}}if(intent===workIntentRevision&&id===task?.id)selectWork(owned||null);}}
  // One project selection owner: user intent requests a read; controller onSelect commits it.
  function selectWork(item){task=item;ui.root.querySelector('[data-control="tasks:add-open"]')?.classList.toggle('primary',!item);requestedWork=null;if(item&&workState.get()?.tasks){const index=workState.get().tasks.findIndex(row=>
    row.id===item.id);if(index<0)workState.get().tasks.push(item);else workState.get().tasks[index]=item;}ui.$('[data-clear-task]').hidden=!task;ui.$(
    '[data-work-scope]').hidden=!task;ui.$('[data-work-scope]').textContent=task?'Task context: '+task.title:'';offerOpenNow?.();ui.$('[data-work-scope]').setAttribute('aria-label',
    task?'Work · '+task.title:'');const uri=new URL(location.href);if(task)uri.searchParams.set('work',task.id);else if(
    explicitWorkIntent)uri.searchParams.set('work','');else uri.searchParams.delete('work');history.replaceState({},'',uri);for(
    const row of ui.root.querySelectorAll('[data-work-id]'))row.dataset.selectedWork=String(row.dataset.workId===task?.id);discussion.session()?.scope();}
  // REQUESTED WORK (M5 D, Root actual: an off-page ?work= link lost to the first pending Work). The
  // entry summary is one page of 12; a requested id outside it is NOT missing. It stays the request
  // (URL kept, nothing else selected) until the exact owner detail read admits it; a refusal
  // (unknown, other namespace, unavailable) is shown as that request's recovery, never a substitute.
  async function admitRequestedWork(id,{isCurrent=()=>true}={}){
    if(!id){selectWork(null);return null;}
    const listed=workState.get()?.tasks?.find(row=>row.id===id);if(listed){selectWork(listed);return listed;}
    const intent=workIntentRevision,fresh=()=>intent===workIntentRevision&&isCurrent();requestedWork={id,state:'reading'};
    try{const value=await api('/work/state?'+new URLSearchParams({project,view:'detail',id}));if(!fresh())return null;
      if(value.project!==project||value.view!=='detail'||value.task?.id!==id)throw Error('the Work owner returned different coordinates');
      selectWork(value.task);workMemory={...workMemory,selected:id};return value.task;}
    catch(error){if(!fresh())return null;requestedWork={id,state:'refused',reason:error.message};discussion.session()?.scope();
      ui.notice('Requested Work '+id+' was not opened: '+error.message+'. Nothing else was selected; open Work to choose, or clear the request.',true);return null;}
  }
  async function requestWorkSelection(id,{isCurrent=()=>true,activation=null}={}){
    explicitWorkIntent=true;
    const intent=++workIntentRevision,view=views.generation(),controller=workController;
    const fresh=()=>ui.root.isConnected!==false&&intent===workIntentRevision&&view===views.generation()&&isCurrent();
    if(controller&&views.current()==='work')return controller.select(id,null,{isCurrent:fresh,activation});
    if(!id){if(!fresh())return false;workMemory={...workMemory,selected:null};selectWork(null);return true;}
    try{const value=await api('/work/state?'+new URLSearchParams({project,view:'detail',id}));if(!fresh())return false;if(value.project!==project||
      value.view!=='detail'||value.task?.id!==id)throw Error('Work owner returned different coordinates.');selectWork(value.task);workMemory={
      ...workMemory,selected:id};return true;}
    catch(error){if(fresh())ui.notice('Work selection was not changed: '+error.message,true);return false;}
  }
  async function refreshSelectedWork(event,isCurrent=()=>true){
    if(event?.project!==project||![event.turn_id,event.session_id].every(value=>typeof value==='string'&&value)||
      event.session_id!==discussion.session()?.session||event.turn_id!==discussion.session()?.origin?.turnId||event.work_id!==(discussion.session(
      )?.origin?.workId??null)||!isCurrent())return false;
    const intent=workIntentRevision,view=views.generation(),id=task?.id||null,ticket=++workRefreshRevision,controller=workController;
    const fresh=()=>ui.root.isConnected!==false&&intent===workIntentRevision&&view===views.generation()&&id===(task?.id||null)&&ticket===workRefreshRevision&&isCurrent();
    // Request-local phase result: an attempted read coalesces even on refusal/dirty conflict.
    // It is not a cached Work status and never crosses a changed selection or view.
    const observation={fresh,attempted:false};
    if(!id||!fresh())return observation;
    observation.attempted=true;
    if(controller&&views.current()==='work'){await controller.select(id,null,{isCurrent:fresh,observation:true});return observation;}
    try{const value=await api('/work/state?'+new URLSearchParams({project,view:'detail',id}));if(!fresh())return observation;if(
      value.project!==project||value.view!=='detail'||value.task?.id!==id)throw Error('Work owner returned different coordinates.');selectWork(value.task);}
    catch(error){if(fresh())ui.notice('Selected Work needs reinspection: '+error.message,true);}
    return observation;
  }
  // THE CARRIED WORK (P2S-R1a): the qualified Work a refresh carry was captured for - its selection, else the Work its
  // draft or attempt belongs to. Restoration is that Work's selection delivered by the mounted controller's own select
  // (owner admitted, live generation painted), on first mount or on the existing Retry; allocation, a refused or
  // unavailable read, another Work or a replaced render never count.
  function carriedTarget(memory){const port=memory?.port,id=memory?.selected||port?.drafts?.[0]?.id||port?.attempts?.[0]?.work_id;
    return id?{project:(memory.selected?null:port?.drafts?.[0]?.project||port?.attempts?.[0]?.project)||project,id}:null;}
  let workObserver=null;   // the one observer of the mounted controller (stopped on release or remount)
  async function openWork(id){if(!id)return;if(views.current()!=='work')place.remember();const shown=await views.show('work',false);if(
    shown===false)return;return requestWorkSelection(id);}
  async function renderWork(host){
    const ticket=++renderTicket,target=carriedPending?carriedTarget(workMemory):null;
    const delivered=ref=>{if(!carriedPending||!target||ticket!==renderTicket||ref.project!==target.project||ref.id!==target.id)return;carriedPending=false;onCarriedRestored?.();};
    const controller=await mountOperatorWork(host,{project,summary:workState.get(),onSelectionDelivered:delivered,request:api,
      // the shell's canonical project Review controller (workspace.mjs Work discussion): Review responses decide through it
      openProposal:discussion?.projectReview?((turnId,choice)=>discussion.projectReview.open(turnId,choice)):null,initialWork:task?.id||new URL(
      location.href).searchParams.get('work')||null,memory:{...workMemory,...(explicitWorkIntent&&!task?{selected:null}:{})},
      navigation:true,page:true,onSelect:selectWork,onRequest:(id,{activation}={})=>requestWorkSelection(id,{activation}),onUseForMessage:owned=>{discussion.open(true);
        discussion.session().pinMessageTarget(context(),owned);},onUsePrepared:async(action,owned)=>{await discussion.session().usePreparedWork(
        action,owned);discussion.open(true);},
      onDirty:value=>{forms.setDirty(value);},
      // the selected actor's exact turn travels with the conversation open (Work Now → session owner): the session confirms the
      // current turn before offering Stop and never retargets a newer turn in the same conversation from this link
      onConversation:(sessionId,target=null)=>{if(target?.turnId)discussion.session()?.targetTurn?.({project,workId:target.workId||task?.id||null,sessionId,turnId:target.turnId,observedState:target.observedState||null,observedAt:target.observedAt||null});// the named turn belongs to this one open attempt: a refused or failed open drops it, so it never applies to a later visit
        const drop=()=>{if(target?.turnId)discussion.session()?.dropTurnTarget?.({sessionId,turnId:target.turnId});};let opened;
        try{opened=discussion.conversation(sessionId);}catch(error){drop();throw error;}
        if(opened&&typeof opened.then==='function')return opened.then(value=>{if(value===false)drop();return value;},error=>{drop();throw error;});
        if(opened===false)drop();return opened;},onTurn:discussion.savedTurn,onHistory:((...args)=>
        activity.openOwner(...args)),onArtifact:inspect.projectArtifact,onInspectOwner:inspect.ownerRead,
      onPrepare:async(action,owned)=>{if(!await requestWorkSelection(owned.id))return;discussion.talk(
        'Inspect the current owner basis for '+owned.id+' before considering this clearing action. The inspected action was '+action.operation+
        ' with payload '+JSON.stringify(action.payload||{})+'. '+(action.purpose||
        '')+' Preserve the original guards and retained history; do not infer scientific verification.','work');discussion.session().pinMessageTarget(
        context(),workController.detail.task);},
      settingsText:session=>settingsTruthText(session,null)});
    if(!host.isConnected){controller.destroy();return;}workController=controller;
    workObserver?.stop();workObserver=observeWork({project,request:api,selected:()=>task?.id||null,onChange:value=>controller.observed(value),basis:()=>controller.observeBasis(),
      isCurrent:()=>workController===controller&&host.isConnected!==false&&views.current()==='work'});
    const create=E('details','','operator-work-create');create.id='add-task';create.dataset.control='tasks:add';create.append(declareControl(E('summary','Add task'),'tasks:add-summary'));const add=E('form');field(add,'Next task',
      'title').required=true;area(add,'Completion condition','goal').required=true;
    // THE FORM'S FIRST SCREEN (wave 7): title, completion condition and the form's own Add task; Type, Containing work and
    // Prerequisites (with their search tools) follow under one labelled Show/Hide control, closed unless a value in them is
    // not the default. A new task is filed at the project root unless he chooses a containing task: the task open now is
    // offered first after Project root, and said in one line, but never pre-selected.
    const submit=declareControl(E('button','Add task','primary'),'tasks:add-submit');const more=E('details','','task-add-more');more.append(declareControl(E('summary','Type, containing work and prerequisites'),'tasks:add-more'));
    const moreBody=E('div','','task-add-more-body');more.append(moreBody);add.append(submit,more);
    declareControl(field(moreBody,'Type','kind','research',[['research','Research'],[
      'numerics','Numerics'],['formal','Formal result'],['visual','Visual'],['writing','Connected writing'],['review','Review']]),'tasks:add-type');
      const parentField=declareControl(field(moreBody,'Containing work','parent_work_id','',[['','Project root'],...(workState.get().tasks||[]).map(row=>[
      row.id,row.title])]),'tasks:add-parent');const openNow=E('p','','muted task-add-open-now');openNow.hidden=true;parentField.parentElement.after(openNow);
      const deps=declareControl(field(moreBody,'Prerequisites','depends_on','',(workState.get().tasks||[]).map(row=>[row.id,row.title])),'tasks:add-prerequisites');
      deps.multiple=true;const choicesNote=E('p','','muted work-choices-note');choicesNote.setAttribute('role','status');moreBody.append(choicesNote);
    const offerOpen=()=>{const keep=parentField.value,keepText=String(parentField.selectedOptions?.[0]?.textContent||'').replace(/^Open now: /,'');
      for(const option of [...parentField.querySelectorAll('[data-open-now]')])option.remove();const open=task?.id?task:null;
      openNow.hidden=!open;openNow.textContent=open?'Open now: '+(open.title||open.id)+'. The new task goes inside it only if you choose it here.':'';
      if(open){const option=E('option','Open now: '+(open.title||open.id));option.value=open.id;option.dataset.openNow='';parentField.options[0]?.after(option);}
      // what he had chosen stays chosen when the task open beside the list changes
      parentField.value=keep;if(parentField.value!==keep&&keep){const option=E('option',keepText||keep);option.value=keep;parentField.append(option);parentField.value=keep;}};
    offerOpenNow=offerOpen;offerOpen();
    // THE CHOICES (Sol 2026-10-12): the entry summary is one bounded page (limit 12) and must stay so;
    // the selectors are filled from the owner's catalogue pages only when the form opens.
    const fillChoices=rows=>{const keepParent=parentField.value,keepDeps=new Set([...deps.selectedOptions].map(o=>o.value));const options=rows.map(
      row=>[row.id,row.title+(row.status&&row.status!=='open'?' · '+row.status:'')]);const rebuild=(select,extra)=>{select.replaceChildren();for(
      const [v,t]of [...extra,...options]){const option=E('option',t);option.value=v;select.append(option);}};rebuild(parentField,[['',
      'Project root']]);offerOpen();parentField.value=keepParent;if(parentField.value!==keepParent&&keepParent){const option=E('option',
      keepParent+' (not in the current catalogue)');option.value=keepParent;parentField.append(option);parentField.value=keepParent;}rebuild(deps,[]);
      for(const option of deps.options)option.selected=keepDeps.has(option.value);for(const id of keepDeps)if(![...deps.options].some(o=>
      o.value===id)){const option=E('option',id+' (not in the current catalogue)');option.value=id;option.selected=true;deps.append(option);}};
    const choiceTools=E('div','','work-actions work-choice-tools');const findField=E('input');findField.type='search';
      findField.placeholder='Narrow by title or id';findField.setAttribute('aria-label','Narrow the work choices by title or id');const exactField=E(
      'input');exactField.placeholder='Exact work id';exactField.setAttribute('aria-label','Exact work id to add as a choice');
    const moreChoices=ui.button('More work choices',async()=>{const choices=await loadWorkChoices({more:true});if(!add.isConnected)return;fillChoices(
      choices.rows);sayChoices(choices);});moreChoices.hidden=true;
    const addExact=declareControl(ui.button('Add by exact id',async()=>{const id=exactField.value.trim();if(!id)throw Error('Type the exact work id first.');
      const row=await lookupWorkChoice(id);if(!add.isConnected)return;fillChoices(workChoices?.rows||[row]);for(const option of deps.options)if(
      option.value===row.id)option.selected=true;exactField.value='';sayChoices(workChoices||{rows:[row],pages:0,truncated:false});}),'tasks:add-exact');
    choiceTools.append(findField,moreChoices,exactField,addExact);choicesNote.before(choiceTools);
    const narrow=()=>{const needle=findField.value.trim().toLowerCase();for(const select of [parentField,deps])for(const option of select.options){
      const keep=!needle||option.selected||option.value===''||option.textContent.toLowerCase().includes(needle)||option.value.toLowerCase().includes(
      needle);option.hidden=!keep;}};findField.oninput=narrow;
    const sayChoices=choices=>{moreChoices.hidden=!choices.truncated;
      choicesNote.textContent=choices.rows.length+' work items offered (owner catalogue, '+choices.pages+' page'+(choices.pages===1?'':'s')+(
      choices.truncated?'; more exist — More work choices continues from the owner\'s continuation, or add an exact id':'')+').';narrow();};
    create.ontoggle=async()=>{if(create.open)offerOpen();if(!create.open||create.dataset.choicesLoaded)return;create.dataset.choicesLoaded='loading';
      pendingRead(choicesNote,'Loading the work catalogue…');try{const choices=await loadWorkChoices();if(!add.isConnected)return;fillChoices(
      choices.rows);sayChoices(choices);create.dataset.choicesLoaded='true';}catch(error){delete create.dataset.choicesLoaded;
      choicesNote.textContent='';ui.actionAlert(choicesNote,'Work choices could not be loaded: '+error.message);}};forms.wire(add,async values=>{
      const reply=await api('/work/task',{project,...values,depends_on:[...deps.selectedOptions].map(o=>o.value)});createDraft=null;
      // the confirmation names the task (the title just submitted, else the owner's) and the containing task the owner recorded
      // (its reply's parent_work_id; the title from the new task's own detail read, reference.location.path), and the list then
      // shows the new task's row
      const id=reply?.id||null,parentId=reply?.parent_work_id||null,named=String(values.title||reply?.title||id||'').trim().replace(/[.\s]+$/,'');let path=[],whole=false;
      if(id&&parentId){try{const detail=await api('/work/state?'+new URLSearchParams({project,view:'detail',id}));if(detail?.task?.id===id){path=
        detail.reference?.location?.path||[];whole=!detail.reference?.location?.omitted;}}catch(error){path=[];}}
      const parent=parentId?path.at(-1)?.id===parentId?path.at(-1):(workState.get()?.tasks||[]).find(row=>row.id===parentId)||workChoices?.rows?.find(row=>
        row.id===parentId)||{id:parentId}:null;
      pendingReveal=id?{id,path:!parentId?[]:whole&&path.at(-1)?.id===parentId?path.map(step=>step.id):null}:null;
      await forms.changed('Task added: '+named+(parent?', inside '+String(parent.title||parent.id).replace(/[.\s]+$/,''):'')+'.',{after:()=>{
        const row=revealed;revealed=null;if(row?.isConnected)row.scrollIntoView?.({block:'nearest'});}});});
      const createFields=['title','goal','kind','parent_work_id'];let createDraft=workMemory.createDraft||null;if(
      createDraft){for(const name of createFields){const input=add.querySelector('[name="'+name+'"]');if(input&&createDraft.fields?.[
      name]!=null)input.value=createDraft.fields[name];}
      // a chosen containing task that this render does not offer (the task open then, or one from a later catalogue page) is
      // offered again under the title he saw, so the draft keeps what he had chosen
      const keptParent=createDraft.fields?.parent_work_id||'';if(keptParent&&parentField.value!==keptParent){const option=E('option',
        createDraft.parent_title||keptParent);option.value=keptParent;parentField.append(option);parentField.value=keptParent;}for(const option of deps.options)option.selected=(createDraft.depends_on||[]).includes(
      option.value);}more.open=parentField.value!==''||add.querySelector('[name="kind"]').value!=='research'||deps.selectedOptions.length>0;
      const inputChanged=add.oninput;add.oninput=()=>{inputChanged?.();createDraft={fields:Object.fromEntries(new FormData(add)),
      depends_on:[...deps.selectedOptions].map(o=>o.value),parent_title:parentField.value?String(parentField.selectedOptions?.[0]?.textContent||'').replace(
      /^Open now: /,''):null,dirty:true};};const capture=controller.capture,hasDraft=()=>Object.values(capture(
      ).drafts||{}).some(row=>row.dirty);controller.capture=()=>({...capture(),createDraft});Object.defineProperty(controller,'hasDraft',{get:()=>
      !!createDraft?.dirty||hasDraft()});create.append(add);const entry=E('button','Add task',task?'task-add-entry':'primary task-add-entry');entry.type='button';entry.dataset.control='tasks:add-open';entry.onclick=()=>{create.open=true;offerOpen();add.querySelector('[name=title]')?.focus();};const head=host.querySelector('.task-page-head');if(head)head.append(entry);else host.prepend(entry);host.append(create);if(new URL(location.href).hash==='#add-task'){create.open=true;create.querySelector('summary')?.focus();}
    // after Add task: the new task's row, shown in the list this render drew (the containing task groups opened in place)
    const reveal=pendingReveal;pendingReveal=null;if(reveal?.path&&controller.reveal)revealed=await controller.reveal(reveal.id,reveal.path).catch(()=>null);
  }
  return {
    render:renderWork,reload:reloadState,select:selectWork,admit:admitRequestedWork,request:requestWorkSelection,refresh:refreshSelectedWork,
    open:openWork,lookup:lookupWorkChoice,choices:loadWorkChoices,
    task:()=>task,requested:()=>requestedWork,clearSelection:()=>{task=null;},hasDraft:()=>!!workController?.hasDraft,
    // the Work memory as the mounted controller would capture it on release (selection, drafts with their original guards,
    // the port's attempts and unresolved outcomes); the controller stays mounted
    capture:()=>structuredClone(workController?workController.capture():workMemory),
    // adopt a kept refresh carry explicitly; refused while this page holds Work drafts or unresolved saves of its own
    restore:memory=>{const own=workController?workController.hasDraft:Object.values(workMemory.drafts||{}).some(row=>row?.dirty)||!!workMemory.port?.drafts?.length||
        !!workMemory.port?.attempts?.some(row=>row.status==='pending'||row.status==='uncertain')||!!workMemory.createDraft?.dirty;
      if(own)throw Error('This page already holds Work drafts or unresolved saves; save or discard them before restoring the kept ones.');
      workObserver?.stop();workObserver=null;workController?.destroy();workController=null;workMemory=structuredClone(memory||{});carriedPending=!!carriedTarget(workMemory);return carriedPending;},
    carriedTarget:()=>carriedPending?carriedTarget(workMemory):null,
    release:()=>{renderTicket++;workObserver?.stop();workObserver=null;if(workController){workMemory=workController.capture();workController.destroy();workController=null;}},
  };
}
