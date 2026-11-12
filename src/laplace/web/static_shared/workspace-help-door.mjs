// WORKSPACE HELP DOOR (M5 S2 F1). Purpose: the shell's Help door: the help owner's areas declaration read
// and verified once per mount, the non-modal help layer for the current view (workspace-help's mountHelp,
// docked at <=1000 px, following resize), the help diagrams read, the learning store, and the cue runner
// for a declared journey (workspace-guide's mountGuide). Ownership: areas, journeys and diagrams belong to
// the /authoring/help owner and learning progress to workspace-journeys; this controller owns only the
// verified areas, the open help layer and the running cue. Public contract: mountHelpDoor(project,
// services) -> {openHelp(), openGuide(), startJourney(id), toggle(), show(view), layer(), followLayout(),
// isOpen(), cueOpen(), dispose()}. The open layer lives in the main area across view changes (the shell's
// view sweep keeps layer(); show(view) repaints it for the new view). Services: views (current view), ui
// ($, root), shell (destroyed). Lifetime: an import that resolves after the shell is destroyed mounts
// nothing; dispose() closes the layer and the cue.
import {issuedHTTP} from './research-workbench-state.mjs';
import {projectRequest as api} from "./writing-request.mjs";

export function mountHelpDoor(project,{views,ui,shell}){
  // the domain's own memory (moved out of the shell closure)
  let guideController=null;
  // THE HELP OWNER'S DECLARATIONS (G8): verified against the owner once per workspace mount
  // and reused within it. Nothing is retained across mounts, so a newer server declaration
  // is seen on the next mount at the latest; the guide renders the `welcome` journey from
  // the verified payload, never from a local copy (Sol HELP-CACHE, 2026-10-12).
  let helpAreasVerified=null;
  const helpAreas=async()=>{if(helpAreasVerified)return helpAreasVerified;
    const value=(await api('/authoring/help?'+new URLSearchParams({project,view:'areas'})))?.help;
    if(value?.schema_version!=='laplace.help-areas/1'||typeof value.version!=='string')throw Error('The help owner returned an incompatible areas declaration.');
    helpAreasVerified=value;return value;};
  // THE HELP DOOR (C10): Help opens the non-modal help layer for the current view (glance, tasks,
  // how it works, states, shortcuts); a task row starts the cue runner for that declared journey.
  // `?` opens help outside a text field; Esc inside the layer or the cue closes it to the door.
  let helpController=null;
  const helpDocked=()=>innerWidth<=1000;
  // help that is already open follows the viewport (ACTUAL-C10-HELP-RESIZE): docked at <=1000, an overlay above
  const followHelpLayout=()=>helpController?.setNarrow?.(helpDocked());
  const learning=()=>import('./workspace-journeys.mjs').then(({learningStore})=>learningStore(project));
  const readDiagrams=async()=>(await api('/authoring/help?'+new URLSearchParams({project,view:'diagrams'})))?.help?.diagrams||[];
  const startJourney=async id=>{const {mountGuide,journeySteps,readJourneyControls}=await import('./workspace-guide.mjs');const areas=await helpAreas(),
    steps=journeySteps(areas,id,await readJourneyControls(areas,api)),store=await learning();if(shell.destroyed())return;helpController?.close();guideController?.close();
    guideController=mountGuide(ui.root,{project,steps,journeyId:id,version:areas.version+'#'+id,store,onClose:()=>{guideController=null;ui.$('[data-guide]').focus();}});};
  const openHelp=async()=>{const [{mountHelp},areas,store]=await Promise.all([import('./workspace-help.mjs'),helpAreas(),learning()]);if(
    shell.destroyed())return;helpController?.close();helpController=mountHelp(ui.$('[data-main]'),{project,areas,view:views.current(),store,
    readDiagrams,readGuides:areas.reads?.guides?async()=>{const result=await api(issuedHTTP(areas.reads.guides,{paths:['/authoring/help']}));return result.help;}:null,narrow:helpDocked(),onJourney:id=>startJourney(id),onClose:()=>{helpController=null;ui.$('[data-guide]').setAttribute('aria-pressed',
    'false');ui.$('[data-guide]').focus();}});ui.$('[data-guide]').setAttribute('aria-pressed','true');helpController.element.focus?.();};
  const openGuide=()=>startJourney('welcome');
  return {
    openHelp,openGuide,startJourney,followLayout:followHelpLayout,
    // a layer something else removed from the page (a failed project load replaces the main area) is closed,
    // not open: the next Help press opens a fresh layer instead of closing an invisible one
    toggle:()=>{if(helpController&&!helpController.element.isConnected){helpController.dispose();helpController=null;}
      return helpController?Promise.resolve(helpController.close()):openHelp();},
    show:view=>helpController?.show(view),layer:()=>helpController?.element||null,
    isOpen:()=>!!helpController&&helpController.element.isConnected,cueOpen:()=>!!guideController,
    dispose:()=>{guideController?.dispose();guideController=null;helpController?.dispose();helpController=null;},
  };
}

// The same declared Help layer for workspace-wide destinations. It reads only
// on explicit Help/guide activation and never borrows an editor mutation action.
export function mountGlobalHelp(host,{navigation,view,project=null,shortcut=true,isCurrent=()=>true,request=api}={}){
 const button=document.createElement('button');button.type='button';button.textContent='Help';button.dataset.control='help:guide';button.setAttribute('aria-label','Help for this view');navigation.append(button);
 let alive=true,controller=null,ticket=0,areas=null;
 const active=()=>alive&&host.isConnected!==false&&isCurrent();
 async function open(){
  if(controller?.element.isConnected){controller.close();return;}const token=++ticket,openingFocus=document.activeElement;button.disabled=true;
  try{const [{mountHelp},response]=await Promise.all([import('./workspace-help.mjs'),areas?{help:areas}:request('/authoring/help?'+new URLSearchParams({view:'areas',...(project?{project}:{})}))]);
   if(!active()||token!==ticket)return;areas=response.help;if(areas?.schema_version!=='laplace.help-areas/1'||typeof areas.version!=='string'||areas.project!==(project||''))throw Error('Help is unavailable for this view.');
   controller=mountHelp(host,{areas,view,includeConversationTasks:false,narrow:innerWidth<=1000,
    readDiagrams:async()=>{const reply=await request(issuedHTTP(areas.reads.diagrams,{paths:['/authoring/help']}));return reply.help?.diagrams||[];},
    readGuides:areas.reads?.guides?async()=>{const reply=await request(issuedHTTP(areas.reads.guides,{paths:['/authoring/help']}));return reply.help;}:null,
    onClose:()=>{controller=null;button.setAttribute('aria-pressed','false');if(active())button.focus();}});button.setAttribute('aria-pressed','true');controller.element.classList.add('global-help');if(!document.activeElement||document.activeElement===openingFocus||document.activeElement===document.body||document.activeElement.isConnected===false)controller.element.focus();
  }catch(error){if(active()&&token===ticket){const note=document.createElement('p');note.textContent=error.message;note.setAttribute('role','alert');button.after(note);}}finally{if(active()&&token===ticket)button.disabled=false;}
 }
 const key=event=>{if(event.defaultPrevented||event.key!=='?'||event.ctrlKey||event.metaKey||event.altKey||['INPUT','TEXTAREA','SELECT'].includes(event.target?.tagName)||event.target?.isContentEditable)return;event.preventDefault();open();},resize=()=>controller?.setNarrow(innerWidth<=1000);
 button.onclick=open;if(shortcut)document.addEventListener?.('keydown',key);globalThis.window?.addEventListener?.('resize',resize);
 return {open,dispose(){alive=false;ticket++;controller?.dispose();button.remove();if(shortcut)document.removeEventListener?.('keydown',key);globalThis.window?.removeEventListener?.('resize',resize);}};
}
