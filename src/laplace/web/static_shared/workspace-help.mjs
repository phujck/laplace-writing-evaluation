// THE HELP LAYER (M5 C10, plan §7). Purpose: contextual help for the current view, from the help
// owner's declarations only: a glance line, the tasks (declared journeys with the person's
// progress), how it works (the area's declared diagram, drawn and listed by workspace-topology),
// the states (chip legend) and the shortcuts. Ownership: the words, journeys, states, diagrams
// and shortcuts are writing_declarations' (AREA/JOURNEY/DIAGRAM_DECLARATIONS) served by
// /authoring/help; this module owns the layer's DOM and nothing else. Public contract:
// helpArea(areas, view) -> the area for a view; mountHelp(main, options) -> {element, show(view),
// close(), dispose(), area}. Inputs: the verified areas payload (once per session), a learning store, a
// readDiagrams function (the `diagrams` help concept, read once when How it works opens).
// Geometry (D1): a non-modal layer at the right edge of the main region (360 px, own scroll),
// never over the nav or the conversation column; <= 1000 px it is a bottom dock (one line plus
// Expand) that opens to a sheet; Close returns focus to the Help door (the shell's onClose); a layout
// change keeps focus on a visible control of the layer (setNarrow).
// Keyboard: Esc inside the layer closes it; the shell binds `?` to open it. No read happens on
// mount beyond what the shell already holds; the diagram is one lazy read. No tutorial starts a
// write, a model or a run: a task row only starts the cue runner (workspace-guide.mjs).
// Controls: help:layer, help:close, help:task, help:diagram.
import {stateChip,lazySection,action,presentationStyles} from './workspace-presentation.mjs';
import {mountTopology} from './workspace-topology.mjs';
import {journeyRows} from './workspace-journeys.mjs';
import {pendingRead} from './pending-read.mjs';
const el=(tag,text='',cls='')=>{const node=document.createElement(tag);node.textContent=text;node.className=cls;return node;};
// R12 (wave 11 census repair R3): a page is helped only by the area the help owner declares for that exact view; a
// view with no declared area gets no other page's help (it used to fall back to the project's Home area).
export function helpArea(areas,view){
  const rows=areas?.areas||[];
  return rows.find(row=>row.view===view)||null;
}
export function mountHelp(main,{project,areas,view,store=null,readDiagrams=async()=>[],readGuides=null,onJourney=()=>{},onClose=()=>{},narrow=false,includeConversationTasks=true}={}){
  if(areas?.schema_version!=='laplace.help-areas/1')throw Error('The help layer needs the help owner\'s areas declaration.');
  presentationStyles();
  const layer=el('aside','','workspace-help'+(narrow?' is-dock':''));layer.dataset.control='help:layer';layer.setAttribute('role','complementary');layer.tabIndex=-1;
  const head=el('div','','workspace-help-head'),title=el('h2','','workspace-help-title'),close=el('button','Close','act workspace-help-close');close.type='button';close.dataset.control='help:close';close.setAttribute('aria-label','Close help');
  const expand=el('button','Expand','act workspace-help-expand');expand.type='button';expand.setAttribute('aria-expanded','false');expand.hidden=!narrow;
  head.append(title,expand,close);
  const body=el('div','','workspace-help-body');layer.append(head,body);
  let area=null,alive=true,visit=0,currentView=view,guides=null,diagrams=null,diagramHost=null,diagramValue=null,diagramToggleNode=null;
  // the diagram draws as a list in the dock and as a graph otherwise; an open diagram redraws when
  // the layout changes (ACTUAL-C10-HELP-RESIZE), keeping its section open
  const drawDiagram=()=>{if(!diagramHost||!diagramValue)return;const diagram=diagramValue;diagramHost.replaceChildren();mountTopology(diagramHost,{title:diagram.title,legend:diagram.description,description:diagram.description,nodes:diagram.nodes,edges:diagram.edges,hints:diagram.layout,listOnly:narrow,ariaLabel:diagram.title,onSelect:()=>{}});};
  const diagramsOnce=async()=>{if(!diagrams)diagrams=await readDiagrams();return diagrams;};
  async function openGuide(ref,opener){
    const ticket=++visit,from=currentView,focused=document.activeElement===opener;
    const status=pendingRead(el('p','Loading guide…','muted'));opener.after(status);
    try{
      if(!guides)guides=await readGuides();
      if(!alive||visit!==ticket)return;
      if(guides?.version!==areas.version||guides.project!==areas.project||!Array.isArray(guides.guides))throw Error('Help changed while opening the guide. Reload this workspace to read the current guides. This page and its current draft have not been changed.');
      const guide=guides.guides.find(row=>row.id===ref.id);if(!guide||ref.section&&!guide.sections.some(row=>row.id===ref.section))throw Error('This guide or section is not declared by the current Help owner.');
      const focusStill=focused&&(!document.activeElement||document.activeElement===document.body||document.activeElement===opener||document.activeElement.isConnected===false);
      body.replaceChildren();title.textContent='Help · '+guide.title;
      const back=el('button','Back to '+(area?.title||from),'act');back.type='button';back.onclick=()=>{const hadFocus=body.contains?.(document.activeElement);paint(from);if(hadFocus){const replacement=[...body.querySelectorAll('[data-guide-key]')].find(n=>n.dataset.guideKey===ref.id+'#'+(ref.section||''));(replacement||close).focus();}};
      body.append(back,el('p',guide.summary||''));let target=null;
      for(const section of guide.sections){const part=el('section','','workspace-help-section'),heading=el('h3',section.title);heading.tabIndex=-1;part.append(heading);if(section.id===ref.section)target=heading;
        for(const paragraph of section.paragraphs||[])part.append(el('p',paragraph));
        if(section.steps?.length){const steps=el('ol');for(const step of section.steps)steps.append(el('li',step));part.append(steps);}
        if(section.references?.length){const references=el('details');references.append(el('summary','Packaged reference documents'));for(const item of section.references)references.append(el('p',item.label+' · '+item.path,'project-source-path'));part.append(references);}body.append(part);
      }
      if(narrow){layer.classList.add('is-expanded');expand.textContent='Collapse';expand.setAttribute('aria-expanded','true');}
      if(focusStill)(target||back).focus();target?.scrollIntoView?.({block:'nearest'});
    }catch(error){if(alive&&visit===ticket){status.textContent=error.message;status.className='error';}}
  }
  function paint(current){
    visit++;currentView=current;area=helpArea(areas,current);
    const name=area?.title||'this page';
    title.textContent='Help · '+name;layer.setAttribute('aria-label','Help · '+name);layer.dataset.area=area?.id||'';
    body.replaceChildren();diagramHost=null;diagramValue=null;diagramToggleNode=null;
    if(!area){body.append(el('p','This page has no guide yet.','muted'));return;}
    body.append(el('p',area.glance||'','workspace-help-glance'));
    // what each part of the page is, one declared sentence each (the Now area declares its four groups)
    if(area.parts?.length){const parts=el('section','','workspace-help-section'),list=el('dl','','workspace-help-parts');parts.append(el('h3','On this page'));for(const part of area.parts)list.append(el('dt',part.name),el('dd',part.says));parts.append(list);body.append(parts);}
    if(area.next_action)body.append(el('p',area.next_action,'workspace-help-next'));
    if(area.effects)body.append(el('p',area.effects,'muted'));
    if(readGuides){const recipes=el('section','','workspace-help-section');recipes.append(el('h3','Guides'));
      const refs=[...(area.guide?[area.guide]:[]),{id:'start',label:'Start here'},{id:'tasks',label:'Task recipes'},{id:'glossary',label:'Glossary'},{id:'reference',label:'Advanced reference'}],seen=new Set();
      for(const ref of refs){const key=ref.id+'#'+(ref.section||'');if(seen.has(key))continue;seen.add(key);const open=el('button',ref.label||ref.id,'act act-read');open.type='button';open.dataset.control='help:read-guide';open.dataset.guideKey=key;open.onclick=()=>openGuide(ref,open);recipes.append(open);}body.append(recipes);}

    // Tasks: the declared journeys with the person's progress; a row starts the cue runner only
    const tasks=el('section','','workspace-help-section');tasks.append(el('h3','Tasks'));
    const taskList=rows=>{const list=el('ul','','workspace-help-tasks');for(const row of rows){const item=el('li');const start=el('button',row.title,'act act-read');start.type='button';start.dataset.control='help:task';start.dataset.journey=row.id;start.setAttribute('aria-label',row.title+' · '+row.status);start.onclick=()=>Promise.resolve(onJourney(row.id,row));item.append(start,el('small',row.status+' · '+row.steps+' steps','muted'));list.append(item);}return list;};
    const rows=journeyRows(areas,area.id,store);
    if(rows.length)tasks.append(taskList(rows));
    else tasks.append(el('p','No guided task for this view yet.','muted'));
    // THE CONVERSATION TASKS (C12, 2026-10-15): Conversation is a pane opened from the top bar in every view,
    // never a main view, so its declared tasks had no door. They are listed here as a second group; the cue
    // observes the live pane itself (sessionOpen, inspectorOpen). No message is sent.
    const pane=includeConversationTasks&&area.id!=='conversation'?helpArea({areas:(areas.areas||[]).filter(row=>row.id==='conversation')},'conversation'):null;
    const paneRows=pane?journeyRows(areas,pane.id,store):[];
    if(paneRows.length){const group=el('h4','In the conversation pane','workspace-help-group');tasks.append(group,taskList(paneRows));}
    // the progress record's truthful standing (H3): unsaved or unsupported progress is said, never reset
    if(store?.status==='unsaved'&&rows.some(row=>row.status!=='Not started'))tasks.append(el('p','This browser did not save your tutorial progress; it is kept while this page stays open.','muted'));
    if(store?.status==='unsupported')tasks.append(el('p','Tutorial progress saved by another version is kept unchanged; progress here is not saved.','muted'));
    body.append(tasks);
    // How it works: the area's declared diagram, read once when opened
    if(area.diagram){const how=lazySection({label:'How it works',hideLabel:'Hide how it works',cls:'workspace-help-diagram',load:async()=>{const found=(await diagramsOnce()).find(row=>row.id===area.id);if(!found)throw Error('The help owner declares no diagram for '+name+'.');return found;},
      render:(host,diagram)=>{diagramHost=host;diagramValue=diagram;drawDiagram();}});
      diagramToggleNode=how.querySelector?.('.lazy-toggle')||null;diagramToggleNode?.setAttribute('data-control','help:diagram');body.append(how);}
    // States: the chip legend
    const states=el('section','','workspace-help-section');states.append(el('h3','States'));
    if(area.states?.length){const legend=el('div','','workspace-help-states');for(const state of area.states)legend.append(stateChip(state));states.append(legend);}
    else states.append(el('p','No state chips in this view.','muted'));
    body.append(states);
    // Shortcuts
    if(area.shortcuts?.length){const keys=el('section','','workspace-help-section');keys.append(el('h3','Shortcuts'));const list=el('dl','','workspace-help-shortcuts');for(const row of area.shortcuts)list.append(el('dt',row.key),el('dd',row.does));keys.append(list);body.append(keys);}
  }
  // dispose (C12 residual R4): the workspace teardown removes the layer without the person's close (no focus move)
  function finish(){if(!alive)return;alive=false;visit++;layer.remove();onClose();}
  function dispose(){if(!alive)return;alive=false;visit++;layer.remove();}
  close.onclick=finish;
  expand.onclick=()=>{returnTo=null;const open=!layer.classList.contains('is-expanded');layer.classList.toggle('is-expanded',open);expand.textContent=open?'Collapse':'Expand';expand.setAttribute('aria-expanded',String(open));};
  layer.onkeydown=event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation?.();finish();}};
  main.append(layer);paint(view);
  // ACTUAL-C10-HELP-RESIZE (2026-10-14): the layout follows the viewport while help stays open. Only the
  // dock class, the Expand control and an open diagram's drawing change; the area, the open sections and the
  // expanded choice stay as they are (the expanded choice applies again in the dock).
  // FOCUS (C12, 2026-10-15; Root saw focus fall to BODY): a focused control the new layout hides or removes
  // moves to the visible control that stands for it. In a collapsed dock the body is not displayed
  // (workspace.css .is-dock:not(.is-expanded) .workspace-help-body), so focus inside it moves to Expand and the
  // control it left is remembered; widening while on Expand (now hidden) returns to that control, or to Close.
  // A control inside an open diagram is removed by the redraw and moves to the diagram's own toggle. Focus
  // outside the layer is never moved, and nothing is opened, expanded or closed for the person.
  let returnTo=null;
  const within=(root,node)=>{for(let n=node;n;n=n.parentElement)if(n===root)return true;return false;};
  const diagramToggle=()=>usable(diagramToggleNode)?diagramToggleNode:null;
  const usable=node=>!!node&&node.isConnected!==false&&within(body,node);
  function setNarrow(next){
    next=!!next;if(!alive||next===narrow)return;
    const active=globalThis.document?.activeElement,inside=!!active&&active!==layer&&within(layer,active);
    const inBody=inside&&within(body,active),inDiagram=inBody&&!!diagramHost&&within(diagramHost,active);
    if(active!==expand)returnTo=null;   // the remembered control serves only the Expand it was handed to
    narrow=next;
    layer.classList.toggle('is-dock',narrow);expand.hidden=!narrow;
    drawDiagram();
    if(!inside)return;
    if(narrow&&!layer.classList.contains('is-expanded')&&inBody){returnTo=inDiagram?diagramToggle():active;expand.focus();return;}
    if(inDiagram){(diagramToggle()||close).focus();return;}
    if(!narrow&&active===expand){const back=usable(returnTo)?returnTo:close;returnTo=null;back.focus();}
  }
  return {get element(){return layer;},get area(){return area;},get alive(){return alive;},get narrow(){return narrow;},show(next){if(alive)paint(next);},setNarrow,close:finish,dispose};
}
