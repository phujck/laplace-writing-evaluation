// WORK NAVIGATOR (WORK-source-state-work-review-context-20261015; repair1 WI-R4). Purpose: the Work view's default
// catalogue: the project's root Work (campaigns and unfiled Work), then any campaign or branch opened level by level, each
// row with its code-bearing title, purpose preview, qualified standing, complete subtree rollup and next ready Work; an
// Attention list that keeps done Work whose acceptance is not current visible. The flat All Work list stays a secondary
// disclosure of the controller. Ownership: project_work_views roots/branch/attention (project_work_navigation) owns rows,
// standing, rollups, ordering, the narrow parallel qualification, byte-bounded whole-row pages and their continuations
// under one cut; this module paints them and keeps only the open level. Public contract: mountWorkNavigator(host, ports)
// -> {show(id, options), reveal(id, path), refresh(), mark(id), level(), basis()}; standingChip(row, fallback); GROUP_LABELS. Ports:
// project, request, button, requestSelection, handOff, current(), selected().
// Every parent is Work: its title inspects it (the controller's selection), a separate Open control opens its contained
// Work, and a breadcrumb opens that level; deeper ancestry is disclosed with the root to descend from.
// Continuations (repair1 WI-R4; repair2 WI-R4a: ONE admission, nextPage, for explicit More, level refresh and attention
// refresh): before a request the owner route must be a GET of /work/state naming this project, this view, this level's id
// (branch) or none, this list's cut and exactly the next offset; the reply must be that view, level, cut and offset before
// any coverage counts, and only rows not already shown are appended. A position the owner could not show (a row larger
// than the page line) is painted as its explicit notice. Any refusal keeps every shown row, states why and offers Reload this level, which takes
// focus when the person was on the control; a valid page that adds nothing says so truthfully. refresh() rereads the open
// level page by page under one cut until it covers every row shown (and the attention rows shown), restarts once if the cut
// moves, and replaces the level atomically keeping focus on the same Work control; a failed refresh throws and leaves the
// shown rows (the observer retries). It never writes.
// THE TASKS PAGE (frontend redesign wave 5, ports.page): the project Tasks page passes page={counts(text), summary}. Then the
// navigator draws one row of filters in the owner's group words (GROUP_LABELS), each with the owner's count of that group
// (roots counts.groups, every Work counted once, so the numbers add up to the task total), task groups first and standalone
// tasks after them at the root, and each "View subtasks (n)" opens that Work's owner branch page in place under its row
// ("Hide subtasks (n)" while shown) instead of replacing the list. All tasks is the nested list; every other filter is the
// owner's list of that group at every depth (view:group, wave 8), read under the page's cut, paged with More through
// nextPage, each row with its containing path; the nested list stays as it was left underneath. Without page the level
// navigation is unchanged (nested and read-only callers, and "Open its contained Work").
import {stateChip,GROUP_LABELS,standingChip,taskStateChips} from './workspace-presentation.mjs';
import {pendingRead} from './pending-read.mjs';
const el=(tag,text='',cls='')=>{const n=document.createElement(tag);n.textContent=text;n.className=cls;return n;};
export {GROUP_LABELS,completedTaskChip,taskActivityChip,taskStateChips,taskFacetRow,taskStatusName,taskStatusMeaning,standingChip} from './workspace-presentation.mjs';
const GRADES={campaign:'Campaign',branch:'Branch'};
const ROLLUP={attention:'need attention',active:'active',awaiting:'awaiting review',blocked:'waiting','in-progress':'in progress',ready:'ready',settled:'settled'};
function rollupText(rollup){
  const parts=[rollup.descendants+' contained'];
  for(const group of Object.keys(ROLLUP))if(rollup.groups?.[group])parts.push(rollup.groups[group]+' '+ROLLUP[group]);
  if(rollup.next)parts.push('next: '+(rollup.next.title||rollup.next.id));
  return parts.join(' · ');
}
const inside=(node,root)=>{for(let at=node;at;at=at.parentElement)if(at===root)return true;return false;};
const ITEMS={roots:'roots',branch:'children',attention:'tasks',group:'tasks'};
const FILTER_ORDER=['attention','active','in-progress','ready','awaiting','blocked','settled'];
export function mountWorkNavigator(host,{project,request,button,requestSelection,handOff,current,selected,page=null}){
  const root=el('div','','work-navigator'),attention=el('details','','work-navigator-attention'),levelBox=el('section','','work-navigator-level');
  const filterBar=page?el('div','','work-nav-filters'):null,groupBox=page?el('section','','work-navigator-group'):null;
  if(page){filterBar.setAttribute('role','group');filterBar.setAttribute('aria-label','Show tasks by state');root.dataset.filter='all';groupBox.hidden=true;
    root.append(filterBar,...(page.summary?[page.summary]:[]));}
  root.append(attention,levelBox,...(groupBox?[groupBox]:[]));host.append(root);
  let level=null,ticket=0,cut=null,attentionCut=null,lastBasis=null,parallelSays='',attentionTotal=null,filter='all';
  // the chosen group's owner list (page mode): its own ticket, so reading it never stales the nested list, and its cut
  let groupTicket=0,groupCounts=null,groupList=null;const groupSubtaskBoxes=new Map();
  const expanded=new Map();   // Work (id -> row) whose subtasks the person opened in place (page mode); reopened after a repaint
  const items=new Map();   // every row painted in this navigator (id -> the owner's row), so reveal() can open a task group by id
  const shown={level:new Set(),attention:new Set()};
  const read=values=>request('/work/state?'+new URLSearchParams({project,...values}));
  // THE ONE CONTINUATION ADMISSION (repair2 WI-R4a). Explicit More, every level-refresh page and every attention-refresh
  // page read a next page only through this helper. BEFORE the read: method, path, project, view, level id (branch) or
  // no id, the list's cut and exactly the next offset (strictly advancing, by the positions the previous page covered).
  // AFTER the read and BEFORE any coverage counts: the reply's project, view, level, cut and offset; only rows not seen are
  // returned. A moved cut is marked so a refresh may restart once; every other refusal is final for that list.
  async function nextPage(page,{view,levelId=null,group=null,at,seen,live}){
    const http=page?.next_read?.http,url=new URL(http?.url||'','http://local'),q=url.searchParams,offset=Number(q.get('offset'));
    if(http?.method!=='GET'||url.pathname!=='/work/state'||q.get('project')!==project||q.get('view')!==view||
      (view==='branch'?q.get('id')!==levelId:q.has('id'))||(view==='group'?q.get('group')!==group:q.has('group'))||!at||q.get('as_of')!==at)
      throw Error('The continuation names another project, view, level or cut. Reload this level; the rows shown stay as read.');
    const covered=page.covered??page.returned;
    if(!Number.isInteger(offset)||!(offset>page.offset)||offset!==page.offset+covered)throw Error('The continuation does not advance from the rows shown. Reload this level.');
    const value=await request(url.pathname+url.search);
    if(!live())return null;
    if(value?.project!==project||value.view!==view)throw Error('The Work owner returned another project or view. Reload this level; the rows shown stay as read.');
    if(view==='branch'&&value.node?.id!==levelId)throw Error('The Work owner returned another branch than the one open. Reload this level; the rows shown stay as read.');
    if(view==='group'&&value.group!==group)throw Error('The Work owner returned another group than the one chosen. Reload this level; the rows shown stay as read.');
    if(value.read_cut?.revision!==at)throw Object.assign(Error('The Work changed while paging (its cut moved). Reload this level; the rows shown stay as read.'),{moved:true});
    if(value.pagination?.offset!==offset)throw Error('The Work owner returned another page than the one requested. Reload this level.');
    const fresh=[],ids=new Set(seen);for(const item of value[ITEMS[view]]||[])if(!ids.has(item.id)){ids.add(item.id);fresh.push(item);}
    return {value,pagination:value.pagination,fresh};
  }
  // a position the owner could not show because its row alone exceeds the page line (repair2 WI-R5b)
  function oversizedNotices(pagination){
    return (pagination?.oversized||[]).map(notice=>{const item=el('article','','operator-work-row work-nav-row work-nav-oversized');
      item.append(el('p','Not shown (position '+(notice.position+1)+'): '+notice.says,'muted'));
      if(notice.id)item.append(button('Open this task',activation=>requestSelection(notice.id,{activation}),'act'));
      else item.append(el('p','Identity digest '+notice.id_sha256+' ('+notice.id_bytes+' bytes).','muted work-qualified-id'));return item;});
  }
  function inspectControl(item){
    const name=item.title||item.id,control=button(name,activation=>requestSelection(item.id,{activation}),'work-nav-title');
    control.dataset.workId=item.id;control.dataset.control='work:item';control.dataset.controlOwner=project+'::'+item.id;control.dataset.navRole='inspect';
    control.setAttribute('aria-label','Open task · '+name+(item.title_complete===false?' (title continues in its detail)':''));control.setAttribute('aria-current',String(item.id===selected()));
    if(page){control.replaceChildren(el('span',name,'work-nav-title-text'));control.title=name;}   // the title is shown whole inside its own row
    return control;
  }
  function row(item){
    items.set(item.id,item);
    const article=el('article','','operator-work-row work-nav-row');article.dataset.selectedWork=String(item.id===selected());
    const line=el('div','','work-nav-line');line.append(inspectControl(item),...taskStateChips(item).map(stateChip));
    if(GRADES[item.grade])line.append(el('small',GRADES[item.grade],'work-nav-grade muted'));
    article.append(line);
    if(item.needs?.open)article.append(el('small','Waiting on '+item.needs.open+' prerequisite'+(item.needs.open===1?'':'s'),'work-nav-needs muted'));
    if(page){
      // the row's owner facts stay on the row as plain lines; its purpose is read with the task, opened beside the list
      article.dataset.group=item.standing?.group||'';if(item.child_count)article.dataset.grade='group';
      // prerequisite words only when the owner reports an open prerequisite (item.needs.open, the line above); the narrow
      // 'no open declared prerequisite' qualification is not repeated on every row here: the open task states its
      // prerequisites either way (workspace-work.mjs, the Prerequisites relation list)
      if(item.rollup)article.append(el('small',rollupText(item.rollup),'work-nav-rollup muted'));
      if(item.path?.length)article.append(el('small','In '+item.path.map(step=>step.title||step.id).join(' › '),'work-nav-path muted'));
    }else{
    const facts=el('details','','work-nav-item-details');facts.append(el('summary','Task details'));if(item.parallel)facts.append(el('p','No open declared prerequisite','work-nav-parallel muted'));if(item.purpose)facts.append(el('p',item.purpose));if(item.rollup)facts.append(el('p',rollupText(item.rollup),'muted'));if(item.path?.length)facts.append(el('p','In '+item.path.map(step=>step.title||step.id).join(' › '),'muted'));article.append(facts);
    }
    if(item.child_count){const open=button('View subtasks ('+item.child_count+')',activation=>page?subtasks(item,article,open,activation):show(item.id,{activation}),'act work-nav-open');
      open.dataset.openWork=item.id;open.dataset.navRole='open';open.dataset.control='work:subtasks';open.dataset.controlOwner=project+'::'+item.id;open.setAttribute('aria-label','View subtasks of '+(item.title||item.id));if(page)open.setAttribute('aria-expanded','false');article.append(open);}
    return article;
  }
  // refusal stays attached to the list it concerns, with one Reload of the level
  function refuse(box,error,activation){
    let note=box.querySelector?.('.work-nav-refusal');if(!note){note=el('p','','work-status error work-nav-refusal');note.setAttribute('role','alert');box.append(note);}
    note.textContent=error.message;
    let reload=box.querySelector?.('.work-nav-reload');
    if(!reload){reload=button('Reload this level',next=>show(level,{activation:next}),'act work-nav-reload');box.append(reload);}
    handOff(reload,activation);
  }
  // the owner's next page of one list, admitted only through nextPage
  function continuation(list,box,page,view,set,at,levelId=view==='attention'||view==='group'?null:level,group=null){
    if(!page?.next_read)return null;
    const mine=view==='group'?groupTicket:ticket,live=()=>current()&&mine===(view==='group'?groupTicket:ticket)&&control.isConnected;
    const control=button(view==='attention'?'More needing attention':levelId?'More subtasks':'More tasks',async activation=>{
      try{
        const result=await nextPage(page,{view,levelId,group,at,seen:set,live});
        if(!result)return;
        control.remove();list.append(...oversizedNotices(result.pagination));
        if(!result.fresh.length){const note=el('p','This owner page added no new Work; every row it returned is already shown.','muted work-nav-none');note.tabIndex=-1;box.append(note);
          const again=continuation(list,box,result.pagination,view,set,at,levelId,group);handOff(again||note,activation);return;}
        const added=result.fresh.map(item=>{set.add(item.id);return row(item);});place(list,added);
        const next=continuation(list,box,result.pagination,view,set,at,levelId,group);
        handOff(added[0]?.querySelector?.('button')||next,activation);
      }catch(error){if(live())refuse(box,error,activation);}
    },'act work-nav-more');
    control.dataset.control='work:more-tasks';control.dataset.controlOwner=project+'::'+(levelId||view);
    box.append(control);return control;
  }
  // a row goes into the root's group or task section (page mode), else at the end of its list
  function place(list,rows){
    const sorted=list.classList?.contains?.('work-nav-sorted');
    for(const item of rows){const target=sorted?list.querySelector(item.dataset.grade==='group'?'.work-nav-groups':'.work-nav-tasks'):list;if(target.hidden)target.hidden=false;target.append(item);}
  }
  // THE SUBTASKS IN PLACE (page mode): one owner branch page read under its own cut, shown under the row; More subtasks
  // continues through nextPage; Hide keeps what was read and says so on the same control.
  const subtaskBoxes=new Map();
  function sayOpen(control,item,open){control.textContent=(open?'Hide subtasks (':'View subtasks (')+item.child_count+')';control.setAttribute('aria-expanded',String(open));
    control.setAttribute('aria-label',(open?'Hide subtasks of ':'View subtasks of ')+(item.title||item.id));}
  async function subtasks(item,article,control,activation=null){
    // inside a group's list the subtasks are that list's own: the nested list's open groups are not changed by them
    const local=!!groupBox&&inside(article,groupBox),boxes=local?groupSubtaskBoxes:subtaskBoxes,keep=local?new Map():expanded;
    const held=boxes.get(item.id);
    if(held?.isConnected&&held.parentElement===article){const open=!!held.hidden;held.hidden=!open;sayOpen(control,item,open);if(open)keep.set(item.id,item);else keep.delete(item.id);return;}
    const mine=ticket,box=el('div','','work-nav-children');box.dataset.subtasksOf=item.id;article.append(box);boxes.set(item.id,box);keep.set(item.id,item);sayOpen(control,item,true);
    box.append(pendingRead(el('p','Reading the subtasks…','muted work-nav-pending')));
    const live=()=>current()&&mine===ticket&&box.isConnected;
    try{
      const value=await read({view:'branch',id:item.id});if(!live())return;
      if(value?.project!==project||value.view!=='branch'||value.node?.id!==item.id)throw Error('The Work owner returned a different navigation level.');
      const seen=new Set(),list=el('div','','work-nav-list work-nav-sublist');
      for(const child of value.children||[])if(!seen.has(child.id)){seen.add(child.id);list.append(row(child));}
      list.append(...oversizedNotices(value.pagination));
      box.replaceChildren(list);if(!seen.size)box.append(el('p','This Work contains no Work.','muted'));
      if(value.order?.cyclic?.length)box.append(el('p',value.order.cyclic.length+' contained Work form a prerequisite cycle; they keep their authored order.','work-review-needed'));
      continuation(list,box,value.pagination,'branch',seen,value.read_cut?.revision||null,item.id);
      if(activation)handOff(list.querySelector?.('[data-nav-role="inspect"]')||control,activation);
    }catch(error){if(!live())return;box.replaceChildren();refuse(box,error,activation);}
  }
  // THE FILTERS (page mode): All tasks, then the owner's groups in its own words, each with the owner's count of that group
  // (roots counts.groups: every Work once, so the numbers add up to the task total). All tasks is the nested list; any other
  // filter shows that group's owner list at every depth (view:group) in place of it, read when chosen and again when the page
  // refreshes; the nested list is kept as it was left. Observed activity is offered while the owner counts any, or while chosen.
  function paintFilters(){
    if(!page)return;const focused=inside(globalThis.document?.activeElement,filterBar)?globalThis.document.activeElement.dataset.filter:null;
    const count=key=>groupCounts?(groupCounts[key]||0):key==='attention'&&Number.isInteger(attentionTotal)?attentionTotal:null;
    const keys=['all',...FILTER_ORDER.filter(key=>key!=='active'||count('active')||filter==='active')];
    filterBar.replaceChildren(...keys.map(key=>{
      const label=key==='all'?'All tasks':GROUP_LABELS[key]+(count(key)!==null?' ('+count(key)+')':'');
      const b=button(label,activation=>choose(key,activation),'act work-nav-filter');b.dataset.filter=key;b.dataset.control='work:nav-filter';b.dataset.controlOwner=key;b.setAttribute('aria-pressed',String(filter===key));return b;}));
    if(focused)[...filterBar.children].find(n=>n.dataset.filter===focused)?.focus?.({preventScroll:true});
  }
  function applyFilter(){
    if(!page)return;root.dataset.filter=filter;
    for(const b of filterBar.children)b.setAttribute('aria-pressed',String(b.dataset.filter===filter));
    levelBox.hidden=filter!=='all';groupBox.hidden=filter==='all';attention.hidden=true;
  }
  // choosing a filter: All tasks shows the nested list where it was left; a group reads its first owner page under the page's cut
  async function choose(key,activation=null){
    if(!page)return;const again=key===filter&&groupList?.key===key&&groupBox.querySelector?.('.work-nav-list');filter=key;applyFilter();
    if(key==='all'||again)return;
    const mine=++groupTicket,live=()=>current()&&mine===groupTicket&&filter===key;
    groupList=null;groupSubtaskBoxes.clear();
    groupBox.replaceChildren(pendingRead(el('p','Reading the tasks in '+GROUP_LABELS[key]+'…','muted work-nav-pending')));
    try{
      const value=await read({view:'group',group:key,...(cut?{as_of:cut}:{})});if(!live())return;
      if(value?.project!==project||value.view!=='group'||value.group!==key)throw Error('The Work owner returned another group than the one chosen.');
      paintGroup(key,[value]);
    }catch(error){if(!live())return;groupBox.replaceChildren();refuse(groupBox,error,activation);}
  }
  function paintGroup(key,pages){
    const first=pages[0];groupList={key,cut:first.read_cut?.revision||null,shown:new Set()};groupSubtaskBoxes.clear();
    const list=el('div','','work-nav-list work-nav-group-list');
    for(const value of pages){for(const item of value.tasks||[])if(!groupList.shown.has(item.id)){groupList.shown.add(item.id);list.append(row(item));}list.append(...oversizedNotices(value.pagination));}
    groupBox.replaceChildren(list);
    if(!first.pagination?.total)groupBox.append(el('p','No task is in '+GROUP_LABELS[key]+' at this read.','muted work-nav-none'));
    continuation(list,groupBox,pages.at(-1).pagination,'group',groupList.shown,groupList.cut,null,key);
  }
  function paintAttention(pages){
    attention.replaceChildren();shown.attention=new Set();const first=pages[0];attentionTotal=first?.total??null;if(!first||!first.total)return;
    attention.append(el('summary','Needs attention ('+first.total+')'),el('p','Includes completed tasks needing a new evidence check and unresolved reviews or task relationships.','muted'));
    const list=el('div','','work-nav-list');for(const page of pages){for(const item of page.items||[])if(!shown.attention.has(item.id)){shown.attention.add(item.id);list.append(row(item));}list.append(...oversizedNotices(page));}
    attention.append(list);continuation(list,attention,pages.at(-1),'attention',shown.attention,attentionCut);
  }
  function paintLevel(pages){
    const value=pages[0],last=pages.at(-1);levelBox.replaceChildren();shown.level=new Set();parallelSays=value.parallel_says||'';
    let heading;
    if(level){
      const crumbs=el('nav','','work-nav-crumbs');crumbs.setAttribute('aria-label','Containing Work');
      crumbs.append(button('All tasks',activation=>show(null,{activation}),'act work-nav-crumb'));
      if(value.breadcrumbs_omitted&&value.breadcrumbs_root){crumbs.append(button(value.breadcrumbs_root.title||value.breadcrumbs_root.id,activation=>show(value.breadcrumbs_root.id,{activation}),'act work-nav-crumb'),
        el('span','… '+value.breadcrumbs_omitted+' more containing Work …','muted work-nav-omitted'));}
      for(const crumb of value.breadcrumbs||[])crumbs.append(button(crumb.title||crumb.id,activation=>show(crumb.id,{activation}),'act work-nav-crumb'));
      levelBox.append(crumbs);
      const node=value.node,card=el('div','','work-nav-node');heading=el('h3',node.title||node.id,'work-nav-heading');heading.tabIndex=-1;
      card.append(heading,el('p',node.qualified_id||'','muted work-qualified-id'),...taskStateChips(node).map(stateChip));if(node.purpose)card.append(el('p',node.purpose,'work-nav-purpose muted'));
      if(node.rollup)card.append(el('p',rollupText(node.rollup),'work-nav-rollup muted'));
      const inspect=inspectControl(node);inspect.textContent='Open this task';card.append(inspect);levelBox.append(card);
      if(value.order?.cyclic?.length)levelBox.append(el('p',value.order.cyclic.length+' contained Work form a prerequisite cycle; they keep their authored order.','work-review-needed'));
    }else{
      const counts=value.counts||{},line=[(counts.work||0)+' task'+(counts.work===1?'':'s'),counts.campaigns+' task group'+(counts.campaigns===1?'':'s')].join(' · ');
      if(page){page.counts?.(line);heading=filterBar;}
      else{heading=el('h3','Tasks','work-nav-heading');heading.tabIndex=-1;levelBox.append(heading,el('p',line,'muted'));}
    }
    const list=el('div','','work-nav-list');const view=level?'branch':'roots';
    if(page&&!level){
      // the root: task groups first, then standalone tasks, each kept in the owner's order
      const groups=el('div','','work-nav-section work-nav-groups'),tasks=el('div','','work-nav-section work-nav-tasks');
      groups.append(el('h3','Task groups','work-nav-section-heading'));tasks.append(el('h3','Tasks','work-nav-section-heading'));list.classList.add('work-nav-sorted');list.append(groups,tasks);}
    for(const page_ of pages){place(list,(page_[ITEMS[view]]||[]).filter(item=>!shown.level.has(item.id)).map(item=>{shown.level.add(item.id);return row(item);}));list.append(...oversizedNotices(page_.pagination));}
    if(!shown.level.size&&!list.querySelectorAll?.('.work-nav-row').length)list.append(el('p',level?'This Work contains no Work.':'No Work recorded yet.','muted'));
    if(page&&!level)for(const section of list.querySelectorAll?.('.work-nav-section')||[])section.hidden=!section.querySelectorAll?.('.work-nav-row').length;
    levelBox.append(list);continuation(list,levelBox,last.pagination,view,shown.level,cut);
    return heading;
  }
  // every page of one list under one cut, from its first page until `want` rows are covered (or the owner has no more);
  // each further page is read only through nextPage. `first` is a page already read (the attention preview) or null.
  async function pagesOf(view,id,want,mine,first=null,group=null){
    const live=()=>current()&&mine===ticket;
    if(!first){first=await read({view,...(id?{id}:{}),...(group?{group}:{})});if(!live())return null;
      if(first?.project!==project||first.view!==view||(view==='branch'&&first.node?.id!==id)||(view==='group'&&first.group!==group))throw Error('The Work owner returned a different navigation level.');}
    const at=first.read_cut?.revision??first.at,pages=[first],seen=new Set((first[ITEMS[view]]||first.items||[]).map(item=>item.id));
    let page=first.pagination||first;
    while(seen.size<want&&page?.next_read){
      const result=await nextPage(page,{view,levelId:id,group,at,seen,live});if(!result)return null;
      for(const item of result.fresh)seen.add(item.id);pages.push(result.value);page=result.pagination;
    }
    return pages;
  }
  async function show(id,{activation=null,keep=false}={}){
    if(!current())return false;
    const mine=keep?ticket:++ticket,doc=globalThis.document;
    if(page&&id&&!keep&&filter!=='all'){filter='all';applyFilter();}   // an opened level is shown, not hidden under a filter
    const want=keep?shown.level.size:0,wantAttention=keep?shown.attention.size:0;
    const focused=keep&&inside(doc?.activeElement,root)?{id:doc.activeElement.dataset?.workId||doc.activeElement.dataset?.openWork,role:doc.activeElement.dataset?.navRole}:null;
    let pages=null,attentionPages=null,nextAttentionCut=attentionCut,groupPages=null;const chosen=page&&filter!=='all'?filter:null;
    for(let attempt=0;attempt<2&&!pages;attempt++){
      try{pages=await pagesOf(id?'branch':'roots',id,want,mine);if(pages===null)return false;
        if(!id||keep){
          const asItems=page=>({...page.pagination,items:page.tasks});
          if(!id){const preview=pages[0].attention;
            const more=preview?await pagesOf('attention',null,wantAttention,mine,{...preview,at:pages[0].read_cut?.revision}):[];if(more===null)return false;
            attentionPages=preview?[preview,...more.slice(1).map(asItems)]:[];nextAttentionCut=pages[0].read_cut?.revision||null;}
          else if(shown.attention.size){const value=await pagesOf('attention',null,wantAttention,mine);if(value===null)return false;
            attentionPages=value.map(asItems);nextAttentionCut=value[0].read_cut?.revision||null;}}
        // the chosen group's list again under this read's cut, as far as he had paged it
        if(chosen){const at=pages[0].read_cut?.revision||null;
          groupPages=await pagesOf('group',null,groupList?.key===chosen?groupList.shown.size:0,mine,null,chosen);if(groupPages===null)return false;
          if(groupPages[0].read_cut?.revision!==at)throw Object.assign(Error('The Work changed while reading (its cut moved). Reload this level; the rows shown stay as read.'),{moved:true});}
      }catch(error){pages=null;groupPages=null;if(!error.moved||attempt===1){
        if(current()&&mine===ticket&&!keep){levelBox.replaceChildren(el('p','Work navigation unavailable: '+error.message+' The flat Work list remains below.','error'),button('Retry',next=>show(id,{activation:next}),'act'));}
        // a refused refresh keeps every shown row and attaches the refusal and reload to the level; focus is not moved
        else if(current()&&mine===ticket&&keep)refuse(levelBox,error,null);
        throw error;}}
    }
    if(!current()||mine!==ticket)return false;
    level=id;cut=pages[0].read_cut?.revision||null;attentionCut=nextAttentionCut;lastBasis=pages[0].observe_basis||null;
    if(page&&!id&&pages[0].counts)groupCounts=pages[0].counts.groups||null;
    // the page's filters are the owner's group lists; the attention preview only gives its total there
    if(attentionPages){if(page)attentionTotal=attentionPages[0]?.total??null;else paintAttention(attentionPages);}
    const heading=paintLevel(pages);
    // Do not repeat a complete attention preview above the same visible rows.
    // An explicitly opened preview or unseen attention rows remain available.
    attention.hidden=!attention.open&&attentionTotal!==null&&attentionTotal===shown.attention.size&&[...shown.attention].every(id=>shown.level.has(id));
    if(page){paintFilters();applyFilter();subtaskBoxes.clear();if(groupPages&&filter===chosen){++groupTicket;paintGroup(chosen,groupPages);}
      // subtasks the person opened stay open across a repaint of the same list (each is read again from its owner)
      for(const [id,item] of [...expanded]){const control=[...(levelBox.querySelectorAll?.('[data-open-work]')||[])].find(n=>n.dataset.openWork===id);
        if(control)subtasks(item,control.parentElement,control).catch(()=>{});else expanded.delete(id);}}
    if(focused?.id){const box=page&&filter!=='all'?groupBox:levelBox;const again=[...(box.querySelectorAll?.('button')||[]),...(root.querySelectorAll?.('button')||[])].find(n=>(n.dataset.workId||n.dataset.openWork)===focused.id&&n.dataset.navRole===focused.role);again?.focus?.({preventScroll:true});}
    else if(activation)handOff(heading,activation);
    return true;
  }
  function mark(id){for(const control of root.querySelectorAll?.('[data-work-id]')||[]){const chosen=control.dataset.workId===id;control.setAttribute('aria-current',String(chosen));
    const article=control.parentElement?.parentElement;if(article?.className?.includes?.('work-nav-row'))article.dataset.selectedWork=String(chosen);}}
  // THE ADDED TASK (wave 7, page mode at the root): after Add task the list shows the new task's row. `path` is the owner's
  // containing Work, root first (the new task's detail read, reference.location.path). Each containing task group is opened in
  // place through its own View subtasks (its owner branch page), a row beyond a page is reached through that list's own More
  // control, and the row is scrolled into view and marked: as a chosen row is at the root, and in words ('Task added') everywhere. Reads nothing of its own; returns the row or null.
  async function reveal(id,path=[]){
    if(!page||level||!current()||!id)return null;
    if(filter!=='all'){filter='all';applyFilter();}
    const rowIn=(box,want)=>[...(box?.querySelectorAll?.('.work-nav-row')||[])].find(n=>[...n.children].some(c=>c.classList?.contains?.('work-nav-line')&&
      c.querySelector?.('[data-nav-role="inspect"]')?.dataset.workId===want));
    const more=box=>[...(box?.querySelectorAll?.('.work-nav-more')||[])].find(n=>n.parentElement===box);
    // the row, reading further pages of this one list with its own More control while the owner offers them
    const find=async(box,want)=>{let found=rowIn(box,want);for(let next=more(box);!found&&next&&current();next=more(box)){await next.onclick?.();if(more(box)===next)break;found=rowIn(box,want);}return found;};
    let box=levelBox;
    for(const step of path){const article=await find(box,step);if(!article||!current())return null;
      const control=[...article.children].find(n=>n.dataset?.openWork===step);if(!control)return null;
      const held=subtaskBoxes.get(step);if(!(held?.isConnected&&held.parentElement===article&&!held.hidden))await subtasks(items.get(step)||{id:step,child_count:0},article,control);
      box=subtaskBoxes.get(step);if(!box||!current())return null;}
    const article=await find(box,id);if(!article||!current())return null;
    for(const n of root.querySelectorAll?.('[data-added-work]')||[])delete n.dataset.addedWork;
    for(const n of root.querySelectorAll?.('.work-nav-added')||[])n.remove();
    // the mark is in words as well as colour: the notice's own 'Task added', next to the row's title
    // on its own line under the row's title line, so the state words keep their place
    article.dataset.addedWork='true';const line=[...article.children].find(c=>c.classList?.contains?.('work-nav-line'));
    if(line){const tag=document.createElement('span');tag.className='work-nav-added';tag.textContent='Task added';line.after(tag);}
    article.scrollIntoView?.({block:'nearest'});
    return article;
  }
  // the page's filter: choosing one changes the list in place (exposed for the shell's own use and tests)
  return {show,reveal,refresh:()=>show(level,{keep:true}),mark,level:()=>level,basis:()=>lastBasis,filter:key=>{if(key!==undefined&&page&&(key==='all'||GROUP_LABELS[key]))return choose(key).then(()=>filter);return filter;}};
}
