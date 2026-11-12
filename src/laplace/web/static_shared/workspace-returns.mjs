// WORKSPACE RETURNS (M5 S2 F1). Purpose: the shell's one cross-view return place: capturing where the reader
// was (main scroll, argument surface and relationship map, reader-plan memory, manuscript place) before a
// door opens another view, remembering it once as the return place (createWorkspaceReturn), and Back to that
// place: restoring the view's memory, showing it and restoring the scroll and surfaces once it has rendered.
// Ownership: each view's memory belongs to its controller; this controller owns no state beyond the shared
// workspaceReturn it is given. Public contract: mountReturns(project, services) -> {capture(), restore(place),
// remember(), back()}; focusCoordinate(main) and focusTarget(main, coordinate), the semantic focus place a
// capture records and Back restores. Services: views (current view, show, generation, structure mode), ui ($),
// labels (view labels), workspaceReturn, argument, readerHome, manuscript, research. Lifetime: a restore whose
// load generation moved on does nothing.

// THE FOCUS COORDINATE (M5-I2): where the keyboard was, named by the control it was on and never by the
// element. A control names itself with data-control, and a per-object control (a reader unit's head, a
// History record's action) adds data-control-owner; the pair is the coordinate. It is captured only from
// inside the main region, and restored only by an explicit Back, after the view's own render, in the same
// frame as its scroll, while the load generation that asked still stands. A stale, background or destroyed
// caller never reaches it. The element found after Back is the one that IS that control in the new paint.
const within=(host,node)=>{for(let at=node;at;at=at.parentNode||at.parentElement||null)if(at===host)return true;return false;};
const parentOf=node=>node.parentNode||node.parentElement||null;
// a data attribute however the element exposes it (setAttribute or dataset)
const datum=(node,name,camel)=>node?.getAttribute?.(name)??node?.dataset?.[camel]??null;
const CONTROL=['data-control','control'],OWNER=['data-control-owner','controlOwner'],HEADING=['data-focus-target','focusTarget'];
export function focusCoordinate(main,active=globalThis.document?.activeElement){
  if(!main||!active||active===main||!within(main,active))return null;
  let control=active;while(control&&!datum(control,...CONTROL))control=parentOf(control);
  if(!control||!within(main,control))return null;
  const coordinate={control:datum(control,...CONTROL)};
  const owner=datum(control,...OWNER);if(owner)coordinate.owner=owner;
  // the domain's own heading above the control (objectHeader focusTarget): the meaningful place when the exact
  // control is not painted again, found by the nearest enclosing object that names one
  for(let at=parentOf(control);at&&at!==main;at=parentOf(at)){const heading=at.querySelector?.('[data-focus-target]');if(heading){coordinate.heading=datum(heading,...HEADING);break;}}
  return coordinate;
}
export function focusTarget(main,coordinate){
  if(!main||!coordinate?.control)return null;
  const one=nodes=>nodes.length===1?nodes[0]:null;   // an ambiguous coordinate is no target; focus stays where the view put it
  const exact=one([...main.querySelectorAll('[data-control]')].filter(node=>datum(node,...CONTROL)===coordinate.control&&
    (datum(node,...OWNER)||null)===(coordinate.owner||null)&&!node.hidden&&!node.disabled));
  if(exact||!coordinate.heading)return exact;
  return one([...main.querySelectorAll('[data-focus-target]')].filter(node=>datum(node,...HEADING)===coordinate.heading&&!node.hidden));
}

export function mountReturns(project,{views,ui,labels,workspaceReturn,argument,readerHome,manuscript,research}){
  // `intent.active` is the control an explicit action was taken from, read by that action before it disabled or
  // removed its control (M5-R2); without one the keyboard's current place inside main is the intent
  function captureReaderPlace({active=null}={}){
    const main=ui.$('[data-main]'),map=main.querySelector('.concept-optional-map'),mapBody=main.querySelector('.concept-relationship-map');
    return {scrollTop:main.scrollTop,...argument.captureSurface(),mapOpen:!!map?.open,mapLeft:mapBody?.scrollLeft||0,mapTop:mapBody?.scrollTop||0,
      focus:focusCoordinate(main,active||globalThis.document?.activeElement),
      ...(views.current()==='reader-plan'?{readerPlan:readerHome.capture()}:{}),
      ...(views.current()==='manuscript'?{manuscript:manuscript.editor()?.capturePlace()}: {})};
  }
  // `generation` is the load generation the caller admitted for this restore; a caller that gives none restores
  // into the generation current at entry (the argument's own restore)
  async function restoreReaderPlace(place,{generation=null}={}){
    const version=generation??views.generation();
    if(version!==views.generation())return;
    const main=ui.$('[data-main]'),map=main.querySelector('.concept-optional-map');if(map&&place.mapOpen)map.open=true;
    if(place.manuscript)await manuscript.editor()?.restorePlace(place.manuscript);
    if(version!==views.generation())return;
    requestAnimationFrame(()=>{if(version!==views.generation())return;const body=main.querySelector('.concept-relationship-map');if(body){
      body.scrollLeft=place.mapLeft||0;body.scrollTop=place.mapTop||0;}main.scrollTop=place.scrollTop||0;argument.restoreSurface(place);
      const target=focusTarget(main,place.focus);if(target)target.focus({preventScroll:true});});
  }
  function rememberReaderReturn(intent={}){
    if(workspaceReturn.current)return;
    if(views.current()==='reader-plan')workspaceReturn.remember({view:'reader-plan',label:readerHome.context()?.label||'Reader plan',...captureReaderPlace(intent)});
    else if(views.current()==='argument')workspaceReturn.remember({...argument.returnPlace(),...captureReaderPlace(intent)});
    else if(views.current()!=='work')workspaceReturn.remember({view:views.current(),label:labels[views.current()],...captureReaderPlace(intent)});
    if(views.current()==='research')research.markReturn();
  }
  return {
    capture:captureReaderPlace,restore:restoreReaderPlace,remember:rememberReaderReturn,
    // Back to the remembered place: its view memory first, then the view, then scroll and surfaces.
    // THE RETURN IS ADMITTED ONCE, AT ENTRY (M5-R2): the generation it was asked in is held across the awaited show.
    // One show advances the generation exactly once, so a later navigation (another view, the same view shown again,
    // a destroyed shell) is a further generation, a refused show is no generation, and in neither case does this
    // Return scroll or focus anything; the intended view and, for the reader plan, the intended section must be the
    // ones actually shown.
    back:async()=>{const back=workspaceReturn.take();if(!back)return;
      const asked=views.generation();
      if(back.view==='research')research.clearReturn();
      if(back.view==='structure'||back.view==='argument'){views.setMode('graph');argument.restoreQuery(back.query);}
      if(back.readerPlan)readerHome.restore(back.readerPlan);
      const shown=await views.show(back.view,false);
      if(shown===false){workspaceReturn.remember(back);return;}   // refused (a guarded form kept the person): the place stays offered
      const settled=views.generation();
      if(settled!==asked+1||views.current()!==back.view)return;
      if(back.readerPlan?.sectionId&&readerHome.capture()?.sectionId!==back.readerPlan.sectionId)return;
      await restoreReaderPlace(back,{generation:settled});},
  };
}

// Explicit nested inspector return. The coordinate survives a parent repaint;
// later input cancels it, and only the newly rendered qualified opener is used.
export function inspectorReturnFocus({dialog,close,key,attribute,isCurrent=()=>true}){
  if(!key)return {finish(){},dispose(){}};let cancelled=false,done=false;
  const dispose=()=>{document.removeEventListener('pointerdown',cancel,true);document.removeEventListener('keydown',cancel,true);document.removeEventListener('focusin',focused,true);};
  const cancel=()=>{cancelled=true;dispose();},focused=e=>{if(e.target!==close&&e.target!==document.body)cancel();};
  document.addEventListener('pointerdown',cancel,true);document.addEventListener('keydown',cancel,true);document.addEventListener('focusin',focused,true);
  return {dispose,finish(){if(done)return;done=true;dispose();if(cancelled||!isCurrent()||document.activeElement!==close)return;const matches=[...dialog.querySelectorAll('['+attribute+']')].filter(n=>n.getAttribute(attribute)===key);if(matches.length!==1)return;const target=matches[0];if(target.isConnected===false||target.disabled)return;for(let at=target.parentElement;at&&at!==dialog;at=at.parentElement)if(at.tagName==='DETAILS')at.open=true;target.focus({preventScroll:true});}};
}
