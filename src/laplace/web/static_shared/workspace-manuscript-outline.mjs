// WORKSPACE MANUSCRIPT OUTLINE (M5 S2 F1). Purpose: the Manuscript view's source outline: the exact source
// headings read from the structure owner's outline (paged, one observation per read), each opened at its
// exact physical occurrence (rendered block when proven unique, otherwise exact TeX), the plan item linked
// to a heading, section deletion with its owner Undo, and the reading location painted in the outline.
// Ownership: headings, sources and the reader plan belong to /work/structure and the source owners; the
// walk owns rendered blocks; this controller owns only its outline observation, its read ticket and the
// mounted outline tree (expanded rows and scroll). Public contract: mountManuscriptOutlineView(project,
// services) -> {render(refresh, continuation), paintLocation(), openOccurrence(row, options),
// captureScroll()}; the pure helpers manuscriptOutlineTree, manuscriptOutlinePosition,
// plannedManuscriptHeading, currentManuscriptHeading, manuscriptHeadingDeletion and mountManuscriptOutline
// (re-exported by workspace.mjs). Services: views (current view, show, generation), ui (notice, button),
// structures (the shell's one structure read), manuscript (editor, ready, saved, source window, external
// application record), readerPlan (open a section, open with none selected), place (the reader return).
// Lifetime: a read ticket drops replies that arrive after a newer read or after leaving the Manuscript view.
import {E} from './workspace-dom.mjs';
import {projectRequest as api} from "/shared/workspace-session.mjs";
import {boundPlanHeading,inspectSourceOccurrence,outlineOccurrence,spineReadURL,structureReadURL} from './workspace-spine.mjs';
import {waitForManuscript} from "/shared/manuscript-editing.mjs";

export function manuscriptOutlineTree(sections,heads){
  const levels={part:0,chapter:1,section:2,subsection:3,subsubsection:4,paragraph:5,subparagraph:6},roots=[],stack=[];
  for(const section of sections){const headings=heads.filter(head=>head.section===section.id);
    if(!headings.length){roots.push({key:'section:'+section.id,section:section.id,title:section.title||'Manuscript',head:null,children:[]});stack.length=0;continue;}
    for(const head of headings){const node={key:head.outline_key||(head.label?head.file+'#'+head.label:head.id),section:section.id,title:head.title||
      'Untitled '+(head.level||'heading'),number:head.number??'',head,children:[]},level=levels[head.level]??2;while(stack.length&&stack.at(
      -1).level>=level)stack.pop();if(stack.length)stack.at(-1).node.children.push(node);else roots.push(node);stack.push({level,node});}
  }
  return roots;
}
export function manuscriptOutlinePosition(heads,blocks,position,currentSection){
  const index=blocks.findIndex(block=>block.id===position?.blockId),prior=index<0?[]:blocks.slice(0,index+1),ids=new Set(heads.map(head=>head.id));
  return [...prior].reverse().find(block=>ids.has(block.id))?.id||heads.find(head=>head.section===currentSection)?.id||'section:'+currentSection;
}
export function plannedManuscriptHeading(sections,head){
  return boundPlanHeading(sections,head);
}
export function currentManuscriptHeading(head,document){
  const sameFile=block=>{const file=block.src?.repo_file||block.src?.file||'';return file===head.file;};
  const matches=(document.sections||[]).flatMap(section=>(section.blocks||[]).filter(block=>block.kind==='head'&&block.level===head.level&&sameFile(
    block)&&(head.label?[block.label,...(block.labels||[])].includes(head.label):block.src?.line_start===head.line_start&&
    block.title===head.title)).map(block=>({...block,section:section.id})));
  if(matches.length!==1)throw Error('The heading changed or its source identity is ambiguous. Reopen its current manuscript location before deleting.');
  const block=matches[0];return {block,head:{id:block.id,section:block.section,title:block.title,label:block.label||(block.labels||[])[0]||null,
    level:block.level,file:block.src.repo_file||block.src.file,line_start:block.src.line_start}};
}
export function manuscriptHeadingDeletion(heading,source,sections){
  const {head,block}=heading,before=source.split('\n').slice(block.src.line_start-1,block.src.line_end).join('\n');if(before!==block.tex)throw Error(
    'The heading source changed after it was read. Reopen the manuscript before deleting.');
  const planned=plannedManuscriptHeading(sections,head);let id=planned?.id||head.label||head.id;if(!planned)while(sections.some(section=>section.id===id))id+=':source-only';
  return {section_id:id,source_file:head.file,line_start:head.line_start,title:head.title,kind:head.level};
}
export function mountManuscriptOutline(host,{tree,expanded=new Map(),current,onNavigate,actionsFor=()=>[],onError=()=>{},onExpansionChange=()=>{}}){
  const entries=new Map(),branches=new Map();let menu=null,opener=null,active=null;
  const closeMenu=(restore=false)=>{menu?.remove();menu=null;if(opener){opener.setAttribute('aria-expanded','false');if(restore&&
    opener.isConnected)opener.focus({preventScroll:true});}opener=null;};
  const away=event=>{if(menu&&!menu.contains(event.target)&&event.target!==opener)closeMenu();};document.addEventListener('pointerdown',away,true);
    const blur=()=>closeMenu();window.addEventListener('blur',blur);
  const openMenu=(entry,event)=>{closeMenu();opener=entry.more;opener.setAttribute('aria-expanded','true');menu=E('div','','manuscript-outline-menu');
    menu.setAttribute('role','menu');menu.setAttribute('aria-label','Actions for '+entry.node.title);
    for(const action of actionsFor(entry.node)){const item=E('button',action.label);item.type='button';item.setAttribute('role','menuitem');
      item.disabled=!!action.disabled;if(action.reason)item.title=action.reason;item.onclick=async()=>{closeMenu();try{await action.run();}catch(
      error){onError(error.message);}};menu.append(item);}
    const items=[...menu.children].filter(item=>!item.disabled);menu.onkeydown=event=>{const index=items.indexOf(document.activeElement);if(
      event.key==='Escape'){event.preventDefault();closeMenu(true);}else if(event.key==='Tab')closeMenu(true);else if(['ArrowDown','ArrowUp','Home',
      'End'].includes(event.key)){event.preventDefault();const next=event.key==='Home'?0:event.key==='End'?items.length-1:(index+(
      event.key==='ArrowUp'?-1:1)+items.length)%items.length;items[next]?.focus();}};
    document.body.append(menu);const rect=entry.more.getBoundingClientRect(),bounds=menu.getBoundingClientRect(),
      x=event?.type==='contextmenu'?event.clientX:rect.left,y=event?.type==='contextmenu'?event.clientY:rect.bottom;menu.style.left=Math.max(8,
      Math.min(x,window.innerWidth-bounds.width-8))+'px';menu.style.top=Math.max(8,Math.min(y,window.innerHeight-bounds.height-8))+'px';items[0]?.focus();
  };
  const list=E('ul','','manuscript-outline-tree');host.replaceChildren(list);
  const branch=(nodes,parent,ancestors=[])=>{for(const node of nodes){const item=E('li','','outline-item'),row=E('div','','outline-row'),
    toggle=node.children.length?E('button','▸','outline-toggle'):E('span','','outline-toggle-space'),link=E('button','','outline-title'),more=E(
    'button','⋯','outline-more');link.type=more.type='button';link.title=node.title;if(node.number)link.append(E('span',node.number,
    'outline-number'));link.append(E('span',node.title,'outline-name'));link.dataset.outlineKey=node.key;if(
    node.head)link.dataset.outlineBlock=node.head.id;else link.dataset.outlineSection=node.section;
    const entry={node,item,row,link,more,parent,ancestors};entries.set(node.head?.id||node.key,entry);row.append(toggle,link);if(actionsFor(
      node).length){more.setAttribute('aria-label','Actions for '+node.title);more.setAttribute('aria-haspopup','menu');more.setAttribute(
      'aria-expanded','false');more.onclick=()=>openMenu(entry);row.append(more);row.oncontextmenu=event=>{event.preventDefault();openMenu(entry,event);};}
    row.onkeydown=event=>{if(event.target&&event.target!==link&&event.target!==toggle&&event.target!==row)return;if((event.key==='ContextMenu'||
      event.key==='F10'&&event.shiftKey)&&actionsFor(node).length){event.preventDefault();openMenu(entry);}else if(event.key==='ArrowRight'){
      event.preventDefault();if(entry.children?.hidden)entry.setOpen(true,true);else if(node.children.length)entries.get(node.children[0].head?.id||
      node.children[0].key)?.link.focus();}else if(event.key==='ArrowLeft'){event.preventDefault();if(entry.children&&
      !entry.children.hidden)entry.setOpen(false,true);else ancestors.at(-1)?.link.focus();}};
    link.onclick=()=>{closeMenu();try{onNavigate(node);}catch(error){onError(error.message);}};item.append(row);parent.append(item);
    if(node.children.length){const children=E('ul','','outline-children');item.append(children);entry.children=children;const setOpen=(value,
      manual=false)=>{children.hidden=!value;toggle.textContent=value?'▾':'▸';toggle.setAttribute('aria-expanded',String(value));toggle.setAttribute(
      'aria-label',(value?'Collapse ':'Expand ')+node.title);if(manual){expanded.set(node.key,value);onExpansionChange(new Map(expanded));}};
      entry.setOpen=setOpen;toggle.type='button';toggle.onclick=()=>setOpen(children.hidden,true);branches.set(node.key,entry);setOpen(expanded.get(
      node.key)===true);branch(node.children,children,[...ancestors,entry]);}
  }};branch(tree,list);
  const scrollParent=()=>host.closest?.('.workspace-nav');
  const setCurrent=(id,{reveal=true}={})=>{if(id===active)return;const prior=entries.get(active);prior?.link.removeAttribute('aria-current');for(
    const entry of prior?.ancestors||[])delete entry.row.dataset.currentPath;const selected=entries.get(id);selected?.link.setAttribute(
    'aria-current','location');for(const entry of selected?.ancestors||[])entry.row.dataset.currentPath='true';const path=new Set(selected?[
    ...selected.ancestors,selected]:[]);for(const entry of branches.values())entry.setOpen(expanded.has(entry.node.key)?expanded.get(
    entry.node.key):path.has(entry));active=id;if(reveal&&selected){const nav=scrollParent(),visible=selected.ancestors.find(entry=>
    entry.children.hidden)||selected;if(nav){const bounds=nav.getBoundingClientRect(),row=visible.row.getBoundingClientRect();if(
    row.top<bounds.top+8)nav.scrollTop+=row.top-bounds.top-8;else if(row.bottom>bounds.bottom-8)nav.scrollTop+=row.bottom-bounds.bottom+8;}}};setCurrent(current,{reveal:false});
  const captureScroll=()=>{const nav=scrollParent();if(!nav)return null;const top=nav.getBoundingClientRect().top,entry=[...entries.values()].find(
    entry=>!entry.ancestors.some(parent=>parent.children.hidden)&&entry.row.getBoundingClientRect().bottom>top);return {top:nav.scrollTop,
    anchor:entry?.node.key,offset:entry?entry.row.getBoundingClientRect().top-top:0};};
  const restoreScroll=value=>{const nav=scrollParent();if(!nav||!value)return;nav.scrollTop=value.top;const entry=[...entries.values()].find(entry=>
    entry.node.key===value.anchor);if(entry&&!entry.ancestors.some(parent=>parent.children.hidden))nav.scrollTop+=entry.row.getBoundingClientRect(
    ).top-nav.getBoundingClientRect().top-value.offset;};
  return {setCurrent,capture:()=>new Map(expanded),captureScroll,restoreScroll,destroy:()=>{closeMenu();document.removeEventListener('pointerdown',
    away,true);window.removeEventListener('blur',blur);}};
}
export function mountManuscriptOutlineView(project,{enc,views,ui,structures,manuscript,readerPlan,place}){
  // the domain's own memory (moved out of the shell closure)
  let outlineObservation=null,
    outlineReadVersion=0,
    manuscriptOutlineController=null,
    manuscriptOutlineScroll=null;
  function paintManuscriptLocation(){const walk=manuscript.sourceWindow()?.walk;if(!walk?.ready?.())return;const heads=walk.outline(),
    id=manuscriptOutlinePosition(heads,walk.blocks({text:false}),walk.readingPosition(),walk.current()),head=heads.find(row=>row.id===id);
    const matches=(outlineObservation?.headings?.items||[]).filter(row=>row.file===head?.file&&row.line===head?.line_start);
    manuscriptOutlineController?.setCurrent(matches.length===1?'source:'+matches[0].source_order+':'+matches[0].file+':'+matches[0].line:null);}
  const sectionUndoKey='laplace:section-undo:'+project;
  async function undoSectionDelete(){
    const undo=JSON.parse(localStorage.getItem(sectionUndoKey)||'null');if(!undo)return;
    const result=await api('/authoring/section-change',{project,...undo});localStorage.removeItem(sectionUndoKey);
    structures.set(result.state||await api('/work/structure?project='+enc));await manuscript.sourceWindow()?.walk?.refresh?.();
      renderManuscriptOutline();ui.notice('Section restored.');
  }
  async function deleteManuscriptSection(head){
    if(manuscript.editor()?.hasDraft())throw Error('Save or discard your TeX draft before removing its section.');
    const walk=manuscript.sourceWindow()?.walk;await walk?.commitAll?.();
    const held=walk?.editState?.();if(held&&(held.dirty||held.parked))throw Error('An edit could not be saved. Resolve it before removing its section.');
    const [planState,document]=await Promise.all([api('/work/structure?project='+enc),api('/walk/doc?corpus='+enc)]);structures.set(planState);
    const heading=currentManuscriptHeading(head,document),file=heading.head.file;if(!file)throw Error('This heading has no source file.');
    const response=await fetch('/projection/tex?'+new URLSearchParams({file,corpus:project}));if(!response.ok)throw Error('The section source could not be read.');
    const bytes=await response.arrayBuffer();if(head.occurrence){const inspected=await inspectSourceOccurrence(head.occurrence,project);if(
      inspected.content!==new TextDecoder().decode(bytes))throw Error(
      'The source changed during deletion preparation. Refresh the outline; nothing was deleted.');}const target=manuscriptHeadingDeletion(heading,
      new TextDecoder().decode(bytes),structures.get().sections||[]);const digest=[...new Uint8Array(await crypto.subtle.digest('SHA-256',
      bytes))].map(b=>b.toString(16).padStart(2,'0')).join('');
    const result=await api('/authoring/section-change',{project,operation:'delete',...target,expected_source_digest:digest,expected_plan_revision:structures.get().revision});
    if(result.undo_ref)await manuscript.rememberApplication({id:result.receipt.id,undo_ref:result.undo_ref});
    structures.set(result.state||await api('/work/structure?project='+enc));await walk?.refresh?.();renderManuscriptOutline();
    ui.notice('Section deleted. Ctrl-Z restores it.');ui.$('[data-notice]').dataset.manuscriptChange='true';if(result.undo_ref)ui.$(
      '[data-notice]').append(ui.button('Undo latest manuscript change',async()=>{await walk.undoEdit();structures.set(await api(
      '/work/structure?project='+enc));renderManuscriptOutline();}));
  }
  async function openOutlineOccurrence(row,{remember=true,edit=false}={}){
    if(remember&&views.current()!=='manuscript')place.remember();
    const originVersion=views.generation(),originView=views.current();
    const observed=await inspectSourceOccurrence(row,project);
    if(views.generation()!==originVersion||views.current()!==originView)return;
    if(views.current()!=='manuscript')await views.show('manuscript',false);
    const version=views.generation();
    const walk=await waitForManuscript({getWalk:()=>manuscript.sourceWindow()?.walk,isCurrent:()=>views.current()==='manuscript'&&version===views.generation()});
    if(!walk)return;
    const body=walk.sourceObservation?.()?.source_observation,raw=body?.file_revisions?.[row.file];
    const exactBody=body?.selection_identity===row.basis.selection_identity&&typeof raw==='string'&&/^[a-f0-9]{64}$/.test(raw)&&'sha256:'+raw===row.basis.source_digest;
    const candidates=walk.outline().filter(head=>head.file===row.file&&head.line_start===row.line);
    const edits=walk.editState?.(),held=manuscript.editor().hasDraft()||edits?.dirty||edits?.parked;
    if(edit||held||row.shared_occurrences>1||!exactBody||candidates.length!==1||manuscript.editor().mode()==='tex'){
      await manuscript.editor().openSource(row.file,row.line,false,row.basis,observed);
      if(row.shared_occurrences>1)ui.notice('This is the shared physical source; it is included more than once in the document.');
      return;
    }
    manuscript.editor().showWrite();walk.jumpToBlock(candidates[0].id);
  }
  async function editableOutlineHeading(row){
    manuscript.saved();await inspectSourceOccurrence(row,project);
    const walk=await manuscript.ready();if(!walk)return null;
    const body=walk.sourceObservation?.()?.source_observation,raw=body?.file_revisions?.[row.file];
    const heads=walk.outline().filter(head=>head.file===row.file&&head.line_start===row.line);
    if(row.shared_occurrences>1||heads.length!==1||body?.selection_identity!==row.basis.selection_identity||
      'sha256:'+raw!==row.basis.source_digest)throw Error('This heading needs exact source inspection. Use Open exact TeX; no rendered occurrence was chosen.');
    return {walk,head:{...heads[0],occurrence:row}};
  }
  async function openOutlinePlan(row){
    const version=views.generation();
    const detail=await api(spineReadURL(row.structure_read,project));
    if(version!==views.generation())return;
    if(detail.project!==project)throw Error('The source-plan reading belongs to another project.');
    const exact=(detail.sections||[]).filter(section=>section.source?.precision==='EXACT_HEADING'&&section.source.heading?.file===row.file&&section.source.heading.line===row.line);
    if(exact.length===1)return readerPlan.openSection(exact[0].id);
    place.remember();await readerPlan.openUnselected();
    ui.notice(
      exact.length?'Several plan items share this physical source. Choose the intended item.':
      'No exact reader-plan item is linked here. Choose a plan item and link its source heading.');
  }
  async function renderManuscriptOutline(refresh=true,continuation=null){
    if(views.current()!=='manuscript')return;
    const host=ui.$('[data-manuscript-outline]'),ticket=++outlineReadVersion;
    try{
      if(refresh||!outlineObservation){
        // journey H: the first page is 25 headings (measured ≤ 12 KB with its page-scoped sources); More source headings continues at the same cut
        const value=await api(continuation?spineReadURL(continuation,project):structureReadURL(project,{view:'outline',limit:25}));
        if(ticket!==outlineReadVersion||views.current()!=='manuscript')return;
        if(value.schema_version!=='laplace.source-outline/2'||value.project!==project||!Array.isArray(value.headings?.items)||!value.sources||
          !value.read_routes)throw Error('The source outline returned an incompatible owner observation.');
        if(continuation&&value.as_of!==outlineObservation?.as_of)throw Error('The source outline changed. Refresh it before continuing.');
        outlineObservation=continuation?{...value,headings:{...value.headings,items:[...outlineObservation.headings.items,...value.headings.items]}}:value;
      }
      const outlineKey='laplace:manuscript-outline:'+project,scroll=manuscriptOutlineScroll||manuscriptOutlineController?.captureScroll();manuscriptOutlineScroll=null;
      let expanded=manuscriptOutlineController?.capture();if(!expanded){try{expanded=new Map(JSON.parse(sessionStorage.getItem(outlineKey)||'[]'));}catch{expanded=new Map();}}
      manuscriptOutlineController?.destroy();
      // G18b: the trimmed outline row becomes the exact occurrence (basis and owner read handles) through the outline's own sources and read_routes
      const heads=outlineObservation.headings.items.map(row=>({id:'source:'+row.source_order+':'+row.file+':'+row.line,
        outline_key:'source:'+row.source_order+':'+row.file+':'+row.line,section:'source-outline',title:(row.display_title||row.title)+(
        row.shared_occurrences>1?' · shared source':''),level:row.kind,file:row.file,line_start:row.line,label:row.label,occurrence:outlineOccurrence(outlineObservation,row)}));
      const tree=manuscriptOutlineTree([{id:'source-outline'}],heads);
      manuscriptOutlineController=mountManuscriptOutline(host,{tree:heads.length?tree:[],expanded,onError:message=>ui.notice(message,true),
        onExpansionChange:value=>{try{sessionStorage.setItem(outlineKey,JSON.stringify([...value]));}catch{}},onNavigate:node=>{openOutlineOccurrence(
        node.head.occurrence,{remember:false}).catch(error=>ui.notice(error.message,true));},actionsFor:node=>[
        {label:'Open exact TeX',run:()=>openOutlineOccurrence(node.head.occurrence,{remember:false,edit:true})},
        {label:'Reader-plan links',run:()=>openOutlinePlan(node.head.occurrence)},
        {label:'File history',run:()=>manuscript.editor().history(node.head.file)},
        ...(!outlineObservation.selected_source.read_only?[
          {label:'Rename heading',run:async()=>{const ready=await editableOutlineHeading(node.head.occurrence);if(ready){ready.walk.jumpToBlock(
            ready.head.id);if(!ready.walk.editBlock(ready.head.id,{exact:true}))throw Error('This heading is available in exact TeX.');}}},
          {label:'Insert heading after…',run:async()=>{const ready=await editableOutlineHeading(node.head.occurrence);if(
            ready)return ready.walk.insertHeading({blockId:ready.head.id,point:{blockId:ready.head.id,start:1}});}},
          {label:'Delete '+node.head.level+' and contents',run:async()=>{const ready=await editableOutlineHeading(node.head.occurrence);if(
            ready)return deleteManuscriptSection(ready.head);}}
        ]:[])]});
      host.prepend(ui.button('Refresh document outline',()=>renderManuscriptOutline(true)));
      if(!heads.length)host.append(E('p',
        outlineObservation.status==='AVAILABLE'?'No source headings yet. Exact TeX remains available in the editor.':'No selected manuscript source is available.','muted'));
      if(outlineObservation.headings.next_read)host.append(ui.button('More source headings',()=>renderManuscriptOutline(true,outlineObservation.headings.next_read)));
      paintManuscriptLocation();manuscriptOutlineController.restoreScroll(scroll);
    }catch(error){if(ticket===outlineReadVersion&&views.current()==='manuscript'){ui.notice(error.message,true);if(
      !outlineObservation)host.replaceChildren(E('p',error.message,'error'),ui.button('Retry document outline',()=>renderManuscriptOutline(true)));}}
  }
  return {
    render:renderManuscriptOutline,paintLocation:paintManuscriptLocation,openOccurrence:openOutlineOccurrence,
    // leaving the Manuscript view keeps the outline's scroll for the next visit
    captureScroll:()=>{manuscriptOutlineScroll=manuscriptOutlineController?.captureScroll()||null;},
  };
}
