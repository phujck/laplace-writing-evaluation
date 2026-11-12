// THE FRAME (wave 9). Purpose: the one top bar every page of the Writing app sits under, with or without a project:
// left to right 'Now', the project switcher, the workspace's places as plain links (Sessions, All tasks, Workflows,
// Projects), then Help, Conversation (project pages only) and one labelled 'More' holding the four rarer workspace
// pages. Below 720 px the bar is Menu, the project's name and Conversation; Menu lists the places, then (inside a
// project) the project's pages.
// Ownership: the bar, the switcher panel and the narrow menu panel are this module's. The project shell keeps its
// own Help and Conversation buttons ([data-guide], [data-talk]) and its Workspace menu identity
// (data-control workspace:menu) and hands them to the bar, so every data-control id and its behaviour is unchanged.
// nav:backlog (declared for the global entry and, inside a project, only while project tools are open) stays on the
// workspace pages' All tasks link; inside a project the bar's All tasks link is the same destination without that identity.
// Reads: /projects/library (the landing's read) only when the switcher is first opened.
// Storage: one per-viewer convenience, localStorage RECENT_KEY ('laplace:frame:recent-projects'): the projects this
// viewer opened, most recent first, at most 24 names with the time each was opened. Nothing else is stored.
// Public contract: mountFrame(options) -> {bar, helpSlot, menuButton, setTitle(title), railPlaces(onHelp), destroy()};
// rememberProject(name, storage); recentProjects(storage); orderByRecent(projects, recent); switchDestination(row,
// {view}); PLACES; MORE; RECENT_KEY.
import {bindAppLink,projectReturnURL} from '/shared/workspace-app.mjs';
export const RECENT_KEY='laplace:frame:recent-projects';
// 'All tasks' (wave 11, census R6): the workspace place lists tasks across every project; a project's own page stays 'Tasks'
export const PLACES=[['now','Now'],['activity','Sessions'],['backlog','All tasks'],['workflows','Workflows'],['projects','Projects']];
export const MORE=[['research','Explore across projects'],['dependencies','Workspace dependencies'],['owners','System owners'],['settings','App settings']];
const el=(tag,text='',cls='')=>{const n=document.createElement(tag);if(text)n.textContent=text;if(cls)n.className=cls;return n;};
const defaultStorage=()=>{try{return globalThis.localStorage||null;}catch{return null;}};

export function recentProjects(storage=defaultStorage()){
  try{const rows=JSON.parse(storage?.getItem(RECENT_KEY)||'[]');return Array.isArray(rows)?rows.filter(row=>row&&typeof row.name==='string'&&row.name):[];}catch{return [];}
}
export function rememberProject(name,storage=defaultStorage(),now=Date.now()){
  if(!name||typeof name!=='string')return;
  try{const rows=[{name,at:now},...recentProjects(storage).filter(row=>row.name!==name)].slice(0,24);storage?.setItem(RECENT_KEY,JSON.stringify(rows));}catch{}
}
// Most recently opened first; projects never opened here keep the library's own order after them.
export function orderByRecent(projects=[],recent=[]){
  const rank=new Map(recent.map((row,index)=>[row.name,index]));
  return projects.map((row,index)=>({row,index})).sort((a,b)=>{const ra=rank.has(a.row.name)?rank.get(a.row.name):Infinity,rb=rank.has(b.row.name)?rank.get(b.row.name):Infinity;return ra-rb||a.index-b.index;}).map(item=>item.row);
}
// The same kind of page in the chosen project: Writing only when that project has a manuscript, otherwise Home.
export function switchDestination(row,{view=null}={}){
  let target=view||'overview';
  if(target==='manuscript'&&row.source_optional)target='overview';
  return '/project?'+new URLSearchParams({workspace:'writing',corpus:row.name,view:target});
}
const appHref=(id,extra={})=>'/project?'+new URLSearchParams({workspace:'writing',app:id,...extra});

export function mountFrame({place=null,project=null,title=null,request,more=null,guide=null,conversation=null,onMenu=null,menuOpen=()=>false,skip=false,storage=defaultStorage()}={}){
  const bar=el('header','','app-frame');bar.dataset.frame='';bar.setAttribute('aria-label','Workspace');
  if(project)bar.dataset.frameProject='';
  const listeners=[];const listen=(target,type,fn)=>{target?.addEventListener?.(type,fn);listeners.push([target,type,fn]);};
  if(skip){const link=el('a','Skip to content','workspace-skip');link.href='#project-work';link.dataset.control='nav:skip';
    link.onclick=event=>{event.preventDefault();const main=document.querySelector('#project-work');if(main){main.tabIndex=-1;main.focus({preventScroll:true});}};bar.append(link);}
  // Menu: the narrow door. Inside a project it opens the project's navigation (which then lists the places first);
  // on a workspace page it opens the frame's own menu panel.
  const menuButton=el('button','Menu','frame-menu');menuButton.type='button';menuButton.dataset.frameMenu='';menuButton.dataset.control='frame:menu';menuButton.setAttribute('aria-expanded','false');
  const nav=el('nav','','frame-places');nav.setAttribute('aria-label','Workspace places');
  const link=(id,label,cls='frame-place')=>{const a=el('a',label,cls);bindAppLink(a,id);a.dataset.place=id;if(id==='backlog'&&cls==='frame-place'&&!project)a.dataset.control='nav:backlog';else{a.dataset.control=cls==='frame-place'?'frame:place':cls==='frame-more-link'?'frame:more-page':'frame:menu-place';a.dataset.controlOwner=id;}if(place===id)a.setAttribute('aria-current','page');return a;};
  const [nowId,nowLabel]=PLACES[0];nav.append(link(nowId,nowLabel));
  // THE PROJECT SWITCHER: the current project's title, or 'Choose a project'; a panel, not a native select.
  const switchHost=el('div','','frame-switch-host'),switcher=el('button','','frame-switch');switcher.type='button';switcher.dataset.frameSwitch='';switcher.dataset.control='frame:switch';
  switcher.setAttribute('aria-haspopup','dialog');switcher.setAttribute('aria-expanded','false');
  const switchTitle=el('span','','frame-switch-title'),switchWord=el('span','Switch','frame-switch-word');switcher.append(switchTitle,switchWord);
  const panel=el('div','','frame-switch-panel');panel.id='frame-switch-panel';panel.setAttribute('role','dialog');panel.setAttribute('aria-label','Switch project');panel.hidden=true;switcher.setAttribute('aria-controls',panel.id);
  const find=el('input');find.type='search';find.placeholder='Find a project';find.setAttribute('aria-label','Find a project');
  const status=el('p','','frame-switch-status');status.setAttribute('role','status');
  const list=el('ul','','frame-switch-list');list.setAttribute('aria-label','Projects, most recently opened first');
  const foot=el('div','','frame-switch-foot'),all=el('a','All projects','frame-switch-foot-link'),create=el('a','Create a project','frame-switch-foot-link');all.href=appHref('projects');create.href=appHref('projects',{start:'create'});all.dataset.control='frame:switch-all';create.dataset.control='frame:switch-create';foot.append(all,create);
  panel.append(find,status,list,foot);switchHost.append(switcher,panel);nav.append(switchHost);
  for(const [id,label]of PLACES.slice(1))nav.append(link(id,label));
  const end=el('div','','frame-end');
  const back=projectReturnURL(new URLSearchParams(globalThis.location?.search||''));
  if(back&&!project){const a=el('a','Return to project','frame-return app-return');a.dataset.control='frame:return';a.href=back;end.append(a);}
  const helpSlot=el('span','','frame-help');helpSlot.dataset.frameHelp='';end.append(helpSlot);
  if(guide)helpSlot.append(guide);
  if(conversation)end.append(conversation);
  // More: the four rarer workspace pages. Inside a project it carries the shell's Workspace menu identity.
  const moreBox=el('details','','frame-more'),moreSummary=el('summary','More'),moreList=el('div','','frame-more-list');moreList.setAttribute('role','menu');
  moreSummary.setAttribute('aria-haspopup','true');moreSummary.dataset.control='frame:more';moreBox.append(moreSummary,moreList);
  if(more){moreBox.dataset.workspaceMenu='';moreBox.dataset.control=more.dataset?.control||more.getAttribute?.('data-control')||'workspace:menu';more.remove?.();}
  for(const [id,label]of MORE){const a=link(id,label,'frame-more-link');a.setAttribute('role','menuitem');moreList.append(a);}
  // when the page he is on is one of More's, the bar says so: the page's name after More, and More marked as current
  const morePlace=MORE.find(([id])=>id===place);if(morePlace){moreSummary.append(el('span',morePlace[1],'frame-more-current'));moreSummary.setAttribute('aria-current','page');}
  end.append(moreBox);
  // the narrow panel (workspace pages): places, More's pages, Help
  const menuPanel=el('div','','frame-menu-panel');menuPanel.id='frame-menu-panel';menuPanel.hidden=true;menuPanel.setAttribute('aria-label','Workspace menu');
  function placesBlock(onHelp){
    const block=el('div','','frame-menu-places');block.append(el('p','Workspace','frame-menu-label'));
    for(const [id,label]of PLACES)block.append(link(id,label,'frame-menu-link'));
    for(const [id,label]of MORE)block.append(link(id,label,'frame-menu-link'));
    if(back&&!project){const a=el('a','Return to project','frame-menu-link');a.dataset.control='frame:return';a.href=back;block.append(a);}
    const help=el('button','Help','frame-menu-link frame-menu-help');help.type='button';help.dataset.control='frame:menu-help';help.onclick=event=>{onHelp?.(event);};block.append(help);
    return block;
  }
  const helpButton=()=>helpSlot.querySelector?.('button');
  if(!project){menuPanel.append(placesBlock(()=>{closeMenu();helpButton()?.click?.();}));menuButton.setAttribute('aria-controls',menuPanel.id);}
  bar.append(menuButton,nav,end,menuPanel);
  function setTitle(value){const text=value||'Choose a project';switchTitle.textContent=text;switcher.title=value?value+' · switch project':'Choose a project';if(value)switcher.setAttribute('aria-current','true');else switcher.removeAttribute('aria-current');switcher.setAttribute('aria-label',(value?'Project: '+value:'No project open')+'. Switch project');}
  setTitle(project?(title||project):null);
  if(project)rememberProject(project,storage);
  // ---- the switcher panel ----
  let library=null,reading=null;
  async function readLibrary(){if(library)return library;if(!reading){status.textContent='Reading your projects…';reading=request('/projects/library').then(value=>{library=value?.projects||[];return library;}).finally(()=>{reading=null;});}return reading;}
  function currentView(){const q=new URLSearchParams(globalThis.location?.search||'');return project?(q.get('view')||'overview'):null;}
  function paintList(){
    if(!library)return;list.replaceChildren();const needle=find.value.trim().toLowerCase(),view=currentView();
    const rows=orderByRecent(library,recentProjects(storage)).filter(row=>((row.title||'')+' '+row.name).toLowerCase().includes(needle));
    for(const row of rows){const item=el('li'),a=el('a','','frame-switch-row');a.href=switchDestination(row,{view});const whole=row.title||row.name;a.title=whole;
      a.append(el('span',whole,'frame-switch-row-title'));if(row.name===project){a.setAttribute('aria-current','page');a.append(el('span','Open now','frame-switch-row-note'));}
      a.onclick=()=>rememberProject(row.name,storage);a.dataset.control='frame:switch-row';a.dataset.controlOwner=row.name;item.append(a);list.append(item);}
    status.textContent=rows.length?(needle?rows.length+' of '+library.length+' projects match':library.length+' projects, most recently opened first'):(library.length?'No project matches this search.':'No projects yet.');
  }
  async function openSwitcher(){
    closeMenu();panel.hidden=false;switcher.setAttribute('aria-expanded','true');bar.classList.add('frame-switch-open');find.focus({preventScroll:true});
    try{await readLibrary();if(!panel.hidden)paintList();}catch(error){status.textContent='Projects could not be read: '+error.message;}
  }
  function closeSwitcher(focus=false){if(panel.hidden)return;panel.hidden=true;switcher.setAttribute('aria-expanded','false');bar.classList.remove('frame-switch-open');if(focus)switcher.focus({preventScroll:true});}
  switcher.onclick=()=>panel.hidden?openSwitcher():closeSwitcher();
  find.oninput=paintList;
  find.onkeydown=event=>{if(event.key==='ArrowDown'){const first=list.querySelector('a');if(first){event.preventDefault();first.focus();}}};
  list.onkeydown=event=>{const links=[...list.querySelectorAll('a')],at=links.indexOf(document.activeElement);if(event.key==='ArrowDown'&&at<links.length-1){event.preventDefault();links[at+1].focus();}if(event.key==='ArrowUp'){event.preventDefault();(at>0?links[at-1]:find).focus();}};
  // ---- the narrow menu ----
  function closeMenu(){if(project||menuPanel.hidden)return;menuPanel.hidden=true;menuButton.setAttribute('aria-expanded','false');}
  menuButton.onclick=event=>{closeSwitcher();if(project){onMenu?.(event);menuButton.setAttribute('aria-expanded',String(!!menuOpen()));return;}
    const open=menuPanel.hidden;menuPanel.hidden=!open;menuButton.setAttribute('aria-expanded',String(open));if(open)menuPanel.querySelector('a,button')?.focus({preventScroll:true});};
  // one place closes what the frame opened: Escape (back to its door) and a click elsewhere
  listen(document,'keydown',event=>{if(event.key!=='Escape'||event.defaultPrevented)return;
    if(!panel.hidden&&bar.contains(event.target)){event.preventDefault();closeSwitcher(true);return;}
    if(!project&&!menuPanel.hidden){event.preventDefault();closeMenu();menuButton.focus({preventScroll:true});return;}
    if(moreBox.open&&moreBox.contains(event.target)){event.preventDefault();moreBox.open=false;moreSummary.focus({preventScroll:true});}});
  listen(document,'pointerdown',event=>{const t=event.target;if(!panel.hidden&&!switchHost.contains(t))closeSwitcher();if(!project&&!menuPanel.hidden&&!menuPanel.contains(t)&&t!==menuButton&&!menuButton.contains?.(t))closeMenu();if(moreBox.open&&!moreBox.contains(t))moreBox.open=false;});
  listen(moreBox,'focusout',event=>{if(!moreBox.contains(event.relatedTarget))moreBox.open=false;});
  // Inside a project: the places, More's pages and Help at the top of the project's navigation (shown as the narrow
  // menu only; wider layouts keep them in the bar).
  function railPlaces(onHelp){const block=placesBlock(onHelp);block.className='frame-rail-places';return block;}
  return {bar,helpSlot,menuButton,switcher,panel,setTitle,railPlaces,openSwitcher,closeSwitcher,
    destroy(){for(const [target,type,fn]of listeners)target?.removeEventListener?.(type,fn);bar.remove?.();}};
}
