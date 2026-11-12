// WORK RELATIONSHIPS (WORK-source-state-work-review-context-20261015). Purpose: the selected Work's three local,
// labelled relationships in ONE panel with ONE visibility controller: Needs (its declared prerequisites), Affects
// (Work that declares it as a prerequisite) and Contains (Work it contains). It replaces the separate Prerequisites
// list and the Contained/Affected families of workspace-work.mjs, keeping their owner reads, paging and refusals.
// Ownership: project_work_views detail owns the rows, their qualified standing and the pages (requires,
// dependants, children; DETAIL_PAGE rows; next_read under the detail's cut); this module paints them and remembers,
// per Work, which tab was open and which Work was opened from here. Public contract: workRelations(ports) ->
// {render(host, task, data)}; ports: project, request, button, remember(row), rows (owner rows held by the
// controller), chip(row), requestSelection, operatorHTTP, current(), generation(). Keyboard: the tablist is one tab
// stop; Left/Right/Home/End move and activate; a tab change updates the mounted panel in place and keeps focus on
// that tab (never a reread, never the heading). Opening a related Work records its opener and tab; the opened Work
// offers Return, which reselects the opener and lands on the same tab (class work-focus-return, honoured by the
// controller's focus handoff). Narrow widths wrap the tabs; the three panels share one container, so Contains is
// shown and hidden exactly like Needs and Affects. Lifetime: a page reply is fenced by generation() and current().
import {relationList,declareControl} from './workspace-presentation.mjs';
const el=(tag,text='',cls='')=>{const n=document.createElement(tag);n.textContent=text;n.className=cls;return n;};
// wave 13 id sweep: control ids by tag and label (begin)
// wave 13 id sweep: control ids (end)
const rowID=row=>typeof row==='string'?row:row?.id;
const TABS=[{id:'needs',label:'Needs',relation:'requires',kind:'Requires',heading:'Prerequisites',cls:'operator-work-family operator-work-prerequisites'},
  {id:'affects',label:'Affects',relation:'dependants',kind:'Affects',heading:'Affected work',cls:'operator-work-family'},
  {id:'contains',label:'Contains',relation:'children',kind:'Contains',heading:'Contained work',cls:'operator-work-family'}];
let serial=0;
export function workRelations(ports){
  const {project,request,button,remember,rows,chip,chips=null,requestSelection,operatorHTTP,current}=ports;
  const tabs=new Map();   // Work id -> the tab last shown for it
  let opener=null,landing=null;   // {id,title,tab}: where a related Work was opened from; landing: {id,tab} after Return
  function render(host,task,data){
    const section=el('section','','operator-work-relations');section.dataset.workRelations=task.id;
    const heading=el('h3','Relationships');section.append(heading);
    if(opener&&opener.id!==task.id&&opener.opened===task.id){
      const from=opener,back=button('Return to '+(from.title||from.id)+' · '+TABS.find(t=>t.id===from.tab).label,activation=>{landing={id:from.id,tab:from.tab};opener=null;return requestSelection(from.id,{activation});},'act');
      back.dataset.relationReturn=from.id;section.append(back);
    }
    const counts={needs:data.requires?.total??(task.depends_on||[]).length,affects:data.dependants?.total??(data.dependants?.items||[]).length,contains:data.children?.total??(data.children?.items||[]).length};
    const chosen=landing?.id===task.id?landing.tab:tabs.get(task.id)||(counts.needs?'needs':counts.contains?'contains':counts.affects?'affects':'needs');
    const list=el('div','','work-relations-tabs');list.setAttribute('role','tablist');list.setAttribute('aria-label','Relationships of this Work');
    const panels=el('div','','work-relations-panels');section.append(list,panels);
    const base='wrel-'+(++serial),controls=[];let active=chosen;
    const activate=(id,{focus=false}={})=>{active=id;tabs.set(task.id,id);for(const {tab,panel,spec}of controls){const on=spec.id===id;
      tab.setAttribute('aria-selected',String(on));tab.tabIndex=on?0:-1;panel.hidden=!on;if(on&&focus)tab.focus?.();}};
    for(const spec of TABS){
      const tab=declareControl(el('button',spec.label+' ('+counts[spec.id]+')','work-relation-tab'),'work:relation-tab',spec.id);tab.type='button';tab.id=base+'-'+spec.id;
      tab.setAttribute('role','tab');tab.setAttribute('aria-controls',base+'-'+spec.id+'-panel');tab.dataset.relationTab=spec.id;
      tab.onclick=()=>activate(spec.id,{focus:true});
      tab.onkeydown=event=>{const at=TABS.findIndex(t=>t.id===spec.id),to={ArrowRight:at+1,ArrowLeft:at-1,Home:0,End:TABS.length-1}[event.key];
        if(to==null)return;event.preventDefault?.();activate(TABS[(to+TABS.length)%TABS.length].id,{focus:true});};
      const panel=family(task,data,spec);panel.id=base+'-'+spec.id+'-panel';panel.setAttribute('role','tabpanel');panel.setAttribute('aria-labelledby',tab.id);
      list.append(tab);panels.append(panel);controls.push({tab,panel,spec});
    }
    activate(active);
    if(landing?.id===task.id){controls.find(c=>c.spec.id===landing.tab).tab.className+=' work-focus-return';landing=null;}
    host.append(section);
    return section;
  }
  // one relationship's rows, paged through the owner's continuation for this Work under the detail's cut (the
  // same rules as before the move: only rows not already shown are appended, the control is replaced by the next
  // page's, a non-advancing page, another Work or a changed cut is refused and the shown rows stay)
  function family(task,data,spec){
    const box=el('section','',spec.cls);if(spec.id==='needs')box.dataset.control='work:prerequisites';box.append(el('h3',spec.heading));
    const owner=task.id,cut=data.read_cut?.revision||null;
    const open=row=>{opener={id:task.id,title:task.title,tab:spec.id,opened:rowID(row)};return requestSelection(rowID(row));};
    const toRow=row=>row&&row.available===false?{kind:spec.kind,label:rowID(row),chip:{label:'unavailable in this namespace',tone:'blocked'},note:'The owner names it; it is not available here.'}
      :{kind:spec.kind,label:row.title||rowID(row),run:()=>open(row),control:'work:relation-open',owner:rowID(row),...(chips?{chips:chips(row)}:{chip:chip(row)})};
    let collection=data[spec.relation];
    if(spec.id==='needs'&&!collection){
      // an owner detail without the requires page: every authored dependency, standing from the rows held here
      const subjects=new Map((data.blockers||[]).map(blocker=>[blocker.subject?.id,blocker.subject]).filter(([id])=>id));
      const items=(task.depends_on||[]).map(id=>{const row=rows.get(id),subject=subjects.get(id),standing=row||subject?.standing,name=row?.title||subject?.title;
        return {kind:'Requires',label:name||id,run:()=>open(id),control:'work:relation-open',owner:id,...(standing?(chips?{chips:chips(standing)}:{chip:chip(standing)}):{chip:{label:'standing not observed',tone:'neutral'}}),note:name?'':'title not in the owner rows held here; the read names it'};});
      box.append(relationList(items,{emptyText:'None recorded.'}));return box;
    }
    const seen=new Set(),first=[];for(const row of collection?.items||[])if(!seen.has(rowID(row))){seen.add(rowID(row));first.push(row);remember(row);}
    const list=relationList(first.map(toRow),{emptyText:'None recorded.'});box.append(list);
    const total=collection?.total,count=el('p','','muted');box.append(count);
    const paintCount=()=>{count.textContent=total!=null&&total>seen.size?seen.size+' of '+total+' shown.':'';};paintCount();
    let next=collection?.next_read||null,control=null;
    const more=()=>{if(!next)return;control=button('More '+spec.heading.toLowerCase(),async()=>{
      const path=operatorHTTP(next),q=new URL(path,'http://local').searchParams;
      if(q.get('project')!==project||q.get('view')!=='detail'||q.get('id')!==owner||cut&&q.get('as_of')!==cut)throw Error('The '+spec.heading.toLowerCase()+' continuation names a different Work, namespace or cut. Reinspect this Work.');
      const ticket=ports.generation(),value=await request(path);if(!current()||ticket!==ports.generation()||!box.isConnected)return;
      if(value.project!==project||value.view!=='detail'||value.task?.id!==owner)throw Error('The Work owner returned a different detail.');
      if(cut&&value.read_cut?.revision!==cut)throw Error('The Work cut changed while paging. Reinspect this Work.');
      const fresh=[];for(const row of value[spec.relation]?.items||[])if(!seen.has(rowID(row))){seen.add(rowID(row));fresh.push(row);remember(row);}
      if(!fresh.length)throw Error('The owner page did not advance. Reinspect this Work.');
      const added=[...relationList(fresh.map(toRow)).children];list.append(...added);
      control.remove();control=null;next=value[spec.relation]?.next_read||null;paintCount();more();
      added[0]?.querySelector?.('button')?.focus?.();
    },'act');box.append(control);};
    more();return box;
  }
  return {render};
}
