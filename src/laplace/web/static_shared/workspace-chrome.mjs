// WORKSPACE CHROME (M5 S2 F1). Purpose: the shell's frame around the views: the navigation (fixed, compact or
// drawer by width through navLayout, its buttons from NAV_LABELS with their capability visibility and the
// Material readers group), the conversation column's open and closed state (remembered in localStorage, never
// forced open on a cold entry unless conversation=open or session= asked), Focus (a manuscript-only reading
// mode that remembers what it closed), the ? key for Help outside a text field, and following resize.
// Ownership: views belong to their controllers; the conversation to workspace-session; this controller owns
// only the focus restore state. Public contract: mountChrome(project, services) -> {openSession(open,
// options), focusManuscript(), focusRestoring(), applyLayout(), refreshNavigation()}. Services: views (current
// view, show, project info), ui ($, button, root), discussion (session), help, initialQuery, pageListen,
// outline (the manuscript outline controller: render(refresh)). Lifetime: its listeners are page
// listeners, removed with the shell's.
import {E} from './workspace-dom.mjs';
import {workspaceViewAvailable} from "/shared/workspace-material.mjs";

// THE NAVIGATION LAYOUT (plan §2 viewport_1000/720, §3 header decisions): fixed at ≥1050
// (200px, Menu hidden), compact at ≤1050 (120px, short labels, the nav-closed preference
// applies here only), drawer below 720 (opened by Menu, never persisted).
export const NAV_LABELS=[['overview','Home','Home'],['manuscript','Writing','Writing'],['material','Sources','Sources'],['work','Tasks','Tasks'],['review','Review & notes','Review'],['history','Activity','Activity'],[
  'settings','Settings','Settings'],['argument','Argument & evidence','Argument'],['reader-plan','Reader plan','Plan'],['research','Research',
  'Research'],['presentation','Figures & output','Output']];
export function navLayout(width){return width<720?'drawer':width<=1050?'compact':'fixed';}
export const NAV_CLOSED_KEY='laplace:workspace:nav-closed',SESSION_OPEN_KEY='laplace:workspace:session-open';
export function mountChrome(project,{views,ui,discussion,help,initialQuery,pageListen,outline,onConversationLayout=()=>{},onReadingReturn=()=>false}){
  let panelIntent=0;
  let overlayInert=null;
  function conversationLayout(){const open=ui.root.classList.contains('session-open'),overlay=open&&innerWidth<=900;ui.root.dataset.conversationOverlay=String(overlay);const regions=[ui.$('[data-main]'),ui.$('.workspace-nav')].filter(Boolean);if(overlay&&!overlayInert){overlayInert=regions.map(node=>[node,node.inert]);for(const node of regions)node.inert=true;}else if(!overlay&&overlayInert){for(const [node,was]of overlayInert)node.inert=was;overlayInert=null;}onConversationLayout(open);}
  function openSession(open,{remember=true}={}){const aside=ui.$('[data-session]'),active=document.activeElement,returning=!open&&remember&&ui.root.classList.contains('session-open')&&aside.contains(active);if(remember)panelIntent++;if(open)discussion.session().catalogueOpened();else{discussion.session().setLibrary(false);
    discussion.session().expand(false);}ui.root.classList.toggle('session-open',open);ui.$('[data-session]').hidden=!open;ui.$(
    '[data-talk]').setAttribute('aria-expanded',String(open));if(remember)localStorage.setItem(SESSION_OPEN_KEY,String(open));conversationLayout();window.dispatchEvent(new Event('resize'));if(returning){const isCurrent=()=>ui.root.isConnected!==false&&!ui.root.classList.contains('session-open')&&(document.activeElement===document.body||aside.contains(document.activeElement));Promise.resolve(onReadingReturn({isCurrent})).then(restored=>{if(!restored&&isCurrent())ui.$('[data-talk]').focus({preventScroll:true});}).catch(()=>{});}}
  let focusRestore=null;
  function focusManuscript(){if(focusRestore){ui.root.classList.toggle('nav-closed',focusRestore.nav);openSession(focusRestore.session);
    focusRestore=null;ui.$('[data-focus]').textContent='Focus manuscript';}else{focusRestore={nav:ui.root.classList.contains('nav-closed'),
    session:ui.root.classList.contains('session-open')};ui.root.classList.add('nav-closed');openSession(false);ui.$(
    '[data-focus]').textContent='Restore panels';}window.dispatchEvent(new Event('resize'));}
  // the frame's Menu (workspace-frame.mjs) is the narrow door to this navigation; it states the same open/closed truth
  const frameDoor=()=>ui.root.querySelector?.('[data-frame-menu]')||null;
  function applyNavLayout(){
    const layout=navLayout(innerWidth);ui.root.dataset.navLayout=layout;ui.$('[data-nav]').hidden=layout==='fixed';
    if(!focusRestore){if(layout==='fixed')ui.root.classList.remove('nav-closed');else if(layout==='compact')ui.root.classList.toggle('nav-closed',
      localStorage.getItem(NAV_CLOSED_KEY)==='true');else ui.root.classList.add('nav-closed');}
    for(const b of ui.root.querySelectorAll('.workspace-nav [data-view]'))if(b.dataset.label)b.textContent=layout==='compact'&&b.dataset.short?b.dataset.short:b.dataset.label;
    ui.$('[data-nav]').setAttribute('aria-expanded',String(!ui.root.classList.contains('nav-closed')));frameDoor()?.setAttribute('aria-expanded',String(!ui.root.classList.contains('nav-closed')));
    conversationLayout();
  }
  ui.$('[data-focus]').onclick=focusManuscript;
  // THE SHELL'S ONE PAGE KEY LISTENER: ? opens Help outside a text field; ESCAPE CLOSES THE OPEN DRAWER (M5, 719): only
  // the drawer layout, only while it is open, and only from the Menu or from inside the navigation it opened; the keyboard
  // returns to Menu and aria-expanded tells the truth. An overlay that owns Escape (Help's layer, a dialog, the outline's
  // menu, the editor) has already handled or prevented the event before it reaches the page, and anything focused outside
  // the drawer is not the drawer's to close. Nothing is persisted: the drawer never writes the nav preference.
  const within=(host,node)=>{for(let at=node;at;at=at.parentNode||at.parentElement||null)if(at===host)return true;return false;};
  pageListen(document,'keydown',event=>{
    if(event.key==='Escape'){if(event.defaultPrevented||ui.root.dataset.navLayout!=='drawer'||ui.root.classList.contains('nav-closed'))return;
      const menu=ui.$('[data-nav]'),nav=ui.$('.workspace-nav'),door=frameDoor();if(event.target!==menu&&event.target!==door&&!within(nav,event.target))return;
      event.preventDefault();ui.root.classList.add('nav-closed');menu.setAttribute('aria-expanded','false');door?.setAttribute('aria-expanded','false');(door||menu).focus?.({preventScroll:true});return;}
    if(event.key!=='?'||event.ctrlKey||event.metaKey||event.altKey)return;const tag=event.target?.tagName;if([
    'INPUT','TEXTAREA','SELECT'].includes(tag)||event.target?.isContentEditable)return;event.preventDefault();ui.$('[data-guide]').onclick(event);});
  // Empty context starts closed. Explicit open preferences and authored/pending
  // conversation state remain visible; a later panel choice wins over loading.
  const hasAuthoredConversation=()=>{const session=discussion.session();return !!(session.find?.('[data-message]')?.value?.trim()||session.messageIntent?.submission||session.controlPending||session.active||session.conversationDraft?.(session.session));};
  ui.$('[data-talk]').onclick=()=>openSession(!ui.root.classList.contains('session-open'));const createdConversation=initialQuery.get(
    'conversation')==='open'||!!initialQuery.get('session'),preferred=localStorage.getItem(SESSION_OPEN_KEY)==='true';openSession(createdConversation||preferred||hasAuthoredConversation(),{remember:false});
  const openingIntent=panelIntent;discussion.session().ready?.then(()=>{if(panelIntent===openingIntent&&ui.root.isConnected!==false&&hasAuthoredConversation())openSession(true,{remember:false});}).catch(()=>{});
  if(createdConversation){
    const url=new URL(location.href);url.searchParams.delete('conversation');url.searchParams.delete('session');history.replaceState({},'',url);}
  ui.$('[data-nav]').onclick=()=>{const visible=!ui.root.classList.contains('nav-closed')&&!(innerWidth<=1050&&ui.root.classList.contains(
    'session-open'));if(!visible&&innerWidth<=1050)openSession(false);ui.root.classList.toggle('nav-closed',visible);if(
    ui.root.dataset.navLayout==='compact')localStorage.setItem(NAV_CLOSED_KEY,String(ui.root.classList.contains('nav-closed')));ui.$(
    '[data-nav]').setAttribute('aria-expanded',String(!ui.root.classList.contains('nav-closed')));};
  const more=E('details','','workspace-nav-more'),moreTitle=E('summary','More project tools'),moreBody=E('div');moreTitle.dataset.control='nav:more-tools';more.append(moreTitle,moreBody);ui.$('.workspace-nav').append(more);
  for(const [id,label,short] of NAV_LABELS){const primary=['overview','manuscript','material','work','research'].includes(id),destination=primary?ui.$('.workspace-nav'):moreBody;const b=ui.button(label,()=>views.show(id));b.dataset.view=id;b.dataset.control='nav:'+id;
    b.dataset.label=label;b.dataset.short=short;b.title=label;b.hidden=!workspaceViewAvailable(views.info(),id);b.disabled=true;b.setAttribute(
    'aria-selected','false');if(primary)more.before(b);else destination.append(b);if(id==='manuscript'){
    // THE OUTLINE HOST AND THE OUTLINE CONTROLLER ARE TWO THINGS (M5-I3): the host is the nav
    // element the controller paints into ([data-manuscript-outline]); the controller is the
    // outline service the shell passes in (workspace-manuscript-outline.mjs, the one that
    // reads the owner's source outline). The Document outline button shows the host and asks
    // the controller to render; it never calls a method on the element.
    const host=E('div','','manuscript-outline');host.dataset.manuscriptOutline='';host.setAttribute('aria-label','Document outline');host.hidden=true;
    const control=ui.button('Document outline',async()=>{if(views.current()!=='manuscript')await views.show('manuscript');
      if(views.current()!=='manuscript')return;host.hidden=false;await outline.render(true);});
    control.dataset.documentOutlineControl='';control.dataset.control='manuscript:outline';control.hidden=!workspaceViewAvailable(views.info(),
    'manuscript');control.className='workspace-outline-control';moreBody.append(control,host);}}
  moreBody.prepend(E('p','Planning, research and settings','workspace-nav-group'));
  // CURRENT TASK AND ACTIVE CONVERSATION (brief V4, ruling D4): entries at the top of the navigation, painted only from the
  // conversation owner's running observations for this project (WorkspaceSession.observeRunning: health nominates,
  // GET /authoring/session confirms, with the observation's time). Nothing is shown when nothing is observed running.
  // The Current task entry names the Work the running turn is bound to (the Work owner's own title) and opens it; the
  // Active conversation entry opens that conversation. The entries are declared controls (nav:live-task and nav:live-conversation, with
  // the Work or conversation as data-control-owner); data-nav-live-entry still locates them for tests.
  const live=E('div','','workspace-nav-live');live.dataset.navLive='';live.setAttribute('aria-label','Running now');live.hidden=true;ui.$('.workspace-nav').prepend(live);
  const clock=value=>{if(!value)return null;const at=new Date(value);return Number.isFinite(at.getTime())?at.toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit',hourCycle:'h23'}):null;};
  function paintRunning(rows=discussion.session()?.runningObservations?.()||[]){
    live.replaceChildren();const shown=rows.filter(row=>row.session&&clock(row.at));live.hidden=!shown.length;if(!shown.length)return;
    const works=[...new Map(shown.filter(row=>row.workId).map(row=>[row.workId,row])).values()];
    if(works.length){live.append(E('p','Current task','workspace-nav-group'));for(const row of works){const b=ui.button(row.workTitle||row.workId,()=>discussion.session()?.onOpenWork?.(row.workId));b.dataset.navLiveEntry='current-task';b.dataset.control='nav:live-task';b.dataset.controlOwner=row.workId;b.title=row.workTitle||row.workId;live.append(b);}}
    live.append(E('p','Active conversation','workspace-nav-group'));
    for(const row of shown){const b=ui.button(row.title||row.session,()=>{const session=discussion.session();openSession(true);return session?.guard?session.guard(()=>session.openConversation(row.session)):session?.openConversation?.(row.session);});b.dataset.navLiveEntry='active-conversation';b.dataset.control='nav:live-conversation';b.dataset.controlOwner=row.session;b.title=row.title||row.session;
      live.append(b,E('small','running, observed '+clock(row.at),'workspace-nav-live-state'));}
  }
  const conversation=discussion.session();if(conversation)conversation.onRunningObserved=rows=>{if(ui.root.isConnected!==false)paintRunning(rows);};paintRunning();
  // The book outline nav (a second plan outline painted on structure changes, shown only for
  // the pre-canonical view name 'structure') is retired: its visibility predicate was
  // unreachable after canonical view rewriting; tests/workspace_shell.test.mjs pins this.
  applyNavLayout();pageListen(window,'resize',applyNavLayout);pageListen(window,'resize',((...args)=>help.followLayout(...args)));
  function refreshCapabilityNavigation(){for(const b of ui.root.querySelectorAll('.workspace-nav [data-view]')){b.hidden=!workspaceViewAvailable(
    views.info(),b.dataset.view);b.disabled=b.hidden;}const outlineControl=ui.root.querySelector('[data-document-outline-control]');if(
    outlineControl)outlineControl.hidden=!workspaceViewAvailable(views.info(),'manuscript');const group=ui.root.querySelector('.workspace-nav-group');
    if(group)group.hidden=!['argument','reader-plan','research','manuscript','review','presentation'].some(view=>workspaceViewAvailable(views.info(),view));}
  return {openSession,focusManuscript,focusRestoring:()=>focusRestore,applyLayout:applyNavLayout,refreshNavigation:refreshCapabilityNavigation};
}
