// WORKSPACE ARGUMENT (M5 S2 F1). Purpose: the Argument & evidence view of the shell: the argument map and
// concept tree of the logical structure (mountConceptExplorer / mountArgumentOverview from
// concept-explorer.mjs), one concept record page with its relations, obligations and evidence links,
// creating an argument object, editing a node's details and the optional relationship map. Ownership: the
// logical objects and their revisions belong to /work/structure and /concepts; this controller owns only
// its view memory: the graph query and state, the mounted surface and its captured memory, the concept
// trail for Back, the active node (remembered under laplace:logical-focus:<project>) and the logical
// origin a manuscript passage named. Public contract: mountArgument(project, services) -> {render(host,
// query, options), openConcept(node, {origin, view}), setOrigin(anchor), restoreQuery(query), logical(),
// context(task, structure), returnPlace(), captureSurface(), restoreSurface(place), release(), destroy(),
// canGoBack(), back(host)}. Services: views (current view, show, generation, structure mode, navigation
// change), forms (dirty, leave, guard, wire), ui (notice, button, $), structures, workState (the project
// work state read and its reload), readerPlan (plan), place (capture and restore of the reading place),
// manuscript (passage, placement), research (evidence, literature), work (open), inspect (saved
// markdown), discussion (talk, session). Lifetime: release() captures the surface memory and destroys it
// when leaving the view; destroy() at shell teardown.
import {E,area,field,section,slug,title} from './workspace-dom.mjs';
import {projectRequest as api} from "/shared/workspace-session.mjs";
import {conceptChangeGuard,mountMathematicsEditor,renderConceptRecord} from "/shared/concept-reader.mjs";
import {mountArgumentOverview,mountConceptExplorer} from "/shared/concept-explorer.mjs";
import {openPdf} from "/shared/writing-pdf.mjs";
import {pendingRead} from './pending-read.mjs';
// wave 13 id sweep: control ids by tag and label (begin)
import {declareControl} from './workspace-presentation.mjs';
// wave 13 id sweep: control ids (end)

export function mountArgument(project,{enc,initialQuery,views,forms,ui,structures,workState,readerPlan,place,manuscript,research,work,inspect,discussion}){
  // the domain's own memory (moved out of the shell closure)
  let focusKey='laplace:logical-focus:'+project,
    savedFocus=localStorage.getItem(focusKey),
    activeNode=savedFocus?{id:savedFocus,label:savedFocus}:null,
    conceptTrail=[],
    logicalOrigin=null,
    argumentSurface=null,
    argumentMemory=null,
    graphState=null,
    graphQuery={project,...(initialQuery.get('node')?{node:initialQuery.get('node')}:{})},
    graphVersion=0;
  async function createArgumentObject(){
    const basis=await api('/concepts/state?project='+enc),dialog=E('dialog','','workspace-dialog'),form=E('form','','work-form'),message=E('p');
    dialog.append(E('h2','Add argument object'),form,message);
    field(form,'Name','name').required=true;field(form,'Kind','kind','definition',[['definition','Definition'],['postulate','Assumption'],[
      'derivation-step','Derivation step'],['result','Result'],['theorem','Theorem'],['technique','Method'],['goal','Goal']]);area(form,'Meaning or claim','essence').required=true;
    const create=E('button','Create object','primary');create.type='submit';form.append(create,ui.button('Cancel',()=>dialog.close()));
    form.onsubmit=async event=>{event.preventDefault();create.disabled=true;try{const values=Object.fromEntries(new FormData(form)),id=(
      values.kind==='definition'?'def':values.kind)+':'+slug(values.name);await api('/concepts/change',{project,base_revision:basis.revision,
      operation:'add_node',node:id,node_kind:values.kind,essence:values.essence});dialog.close();graphQuery={project,node:id};views.setMode('graph');
      await views.show('argument',false);}catch(error){message.textContent=error.message;message.className='error';}finally{create.disabled=false;}};
    dialog.onclose=()=>dialog.remove();document.body.append(dialog);dialog.showModal();form.querySelector('input').focus();
  }
  async function renderConceptTree(host,query=graphQuery,options={}){
    if(!forms.leave())return false;
    if(!argumentSurface?.host?.isConnected){
      const shell=E('section','','argument-space'),head=E('div','','argument-space-head'),diagram=E('div','','argument-map-host'),record=E('div','',
        'argument-reader');diagram.hidden=true;
      const overview=declareControl(ui.button('Overview',()=>openRecord({project})),'argument:overview'),map=declareControl(ui.button('Show dependency map',()=>showMap()),'argument:map'),parentMap=ui.button(
        'Map containing object',()=>showMap(graphState?.current?.parent)),reading=ui.button('Return to reading',()=>showReading());reading.hidden=true;
      parentMap.hidden=true;head.append(overview,map,parentMap,reading,declareControl(ui.button('Reader plan',()=>views.show('reader-plan')),'argument:reader-plan'),declareControl(ui.button(
        'Add argument object',createArgumentObject),'argument:add-object'));
      shell.append(head,record,diagram);host.replaceChildren(shell);host.classList.add('argument-host');
      argumentSurface={host:shell,diagram,record,back:overview,mapButton:map,parentMapButton:parentMap,readingButton:reading,reading:true,scope:null,
        controller:null,recordController:null};
    }
    async function showMap(scopeId=null){
      if(!forms.leave())return false;const surface=argumentSurface;if(!scopeId&&graphQuery.node&&graphState?.current?.child_count===0){
        surface.recordController?.openLocalMap();return true;}const selectedScope=scopeId||graphQuery.node||graphState?.current?.id;
      if(!surface.controller){try{surface.controller=await mountArgumentOverview(surface.diagram,{project,request:api,initialState:{...(
        argumentMemory||{}),...(selectedScope?{scopeId:selectedScope}:{})},onSelect:next=>openRecord(next),onScope:scope=>{surface.scope=scope;},
        onOpenSource:async source=>{const value=await api('/references/source?'+new URLSearchParams({project,key:source.key}));if(
        value.pdf_url)openPdf(value.pdf_url,source.label);else ui.notice(value.reason||'No local PDF is available for this source.',true);},
        onError:message=>ui.notice(message,true)});}catch(error){ui.notice('Dependency map could not load: '+error.message,true);return false;}}
      if(selectedScope&&surface.controller.capture().scopeId!==selectedScope)await surface.controller.restore({...surface.controller.capture(),
        scopeId:selectedScope,selected:graphQuery.node,fitted:true,expanded:null,contextTrail:[]});surface.controller.select(graphQuery.node);
        surface.reading=false;surface.diagram.hidden=false;surface.record.hidden=true;surface.mapButton.hidden=true;
        surface.readingButton.hidden=false;surface.host.dataset.reading='false';discussion.session().scope();return true;
    }
    function showReading(){const surface=argumentSurface;surface.reading=true;surface.mapButton.textContent=graphQuery.node&&
      graphState?.current?.child_count===0?'Show local relationships':graphQuery.node?'Map these parts':'Map project relationships';
      surface.parentMapButton.hidden=!(graphQuery.node&&graphState?.current?.parent);surface.parentMapButton.textContent='Map containing '+(
      graphState?.identity_chain?.at(-1)?title(graphState.identity_chain.at(-1)):'object');surface.diagram.hidden=true;surface.record.hidden=false;
      surface.mapButton.hidden=false;surface.readingButton.hidden=true;surface.host.dataset.reading='true';discussion.session().scope();}
    async function openRecord(next,recordOptions={}){const surface=argumentSurface;const ok=await renderConceptRecordPage(surface.record,{project,
      ...next},recordOptions);if(ok===false)return false;surface.reading=true;showReading();surface.controller?.select(next.node);return true;}
    return openRecord(query,options);
  }

  async function renderConceptRecordPage(host,query=graphQuery,{remember=true,consumeTrail=false}={}){
    if(!forms.leave())return false;forms.setDirty(false);
    const version=++graphVersion,previousQuery={...graphQuery},previousState=graphState,previousPlace=place.capture();let resolved,recordState,logicalPlan;
    try{resolved=await api('/concepts/tree?'+new URLSearchParams({...query,project}));[recordState,logicalPlan]=await Promise.all([api(
      '/concepts/state?'+new URLSearchParams({project,node:resolved.current.id})),api('/concepts/plan?'+new URLSearchParams({project,...(query.node?{
      focus:resolved.current.id}:{}),limit:200}))]);}
    catch(error){if(version!==graphVersion)return false;host.querySelector('.concept-navigation-error')?.remove();const note=E('div','',
      'concept-navigation-error');note.append(E('p',error.message+' The current reader has been preserved.','error'),ui.button(
      'Refresh this location',()=>renderConceptTree(host,previousQuery,{remember:false})));host.prepend(note);return false;}
    if(version!==graphVersion||!host.isConnected)return false;
    const overview=argumentSurface?.controller;
    if(overview&&logicalPlan.revision&&overview.revision?.()!==logicalPlan.revision){
      try{await overview.refresh();}catch(error){ui.notice('Logical record is current, but the argument overview could not refresh: '+error.message,true);}
      if(version!==graphVersion||!host.isConnected)return false;
    }

    if(consumeTrail)conceptTrail.pop();
    if(remember&&previousState?.current&&((query.node||'__index__')!==(previousQuery.node||'__index__')))conceptTrail.push({query:previousQuery,
      label:previousQuery.node?title(previousState.current):'Overview',...previousPlace});
    ui.$('[data-main]').scrollTop=0;graphQuery={...query,project};graphState=null;views.changed();
    host.replaceChildren(E('h2','Argument & evidence'));
    const toolbar=E('div','','work-actions');if(logicalOrigin)toolbar.append(ui.button('Back to passage',()=>manuscript.inspectPassage(logicalOrigin)));host.append(toolbar);
    const loading=pendingRead(E('p','Opening logical record…','muted'));host.append(loading);
    try{
      const data=resolved;if(version!==graphVersion||!host.isConnected)return;
      loading.remove();host.querySelector('h2').textContent=query.node?title(data.current):'Argument & evidence';graphState=data;graphQuery={project,
        ...(query.node?{node:data.current.id}:{}),...Object.fromEntries(['goal','offset','dependency_offset','uncontained_offset'].filter(key=>query[
        key]!=null).map(key=>[key,query[key]]))};activeNode=query.node?data.current:null;discussion.session().scope();views.changed();
      const uri=new URL(location.href);uri.searchParams.set('view','argument');uri.searchParams.delete('structure');if(query.node){
        uri.searchParams.set('node',data.current.id);uri.searchParams.delete('logical');}else{uri.searchParams.delete('node');uri.searchParams.set(
        'logical','list');}history.replaceState({},'',uri);
      if(conceptTrail.length){const prior=conceptTrail.at(-1);toolbar.prepend(ui.button('Back to '+prior.label,()=>{const back=conceptTrail.at(-1);
        return renderConceptTree(host,back.query,{remember:false,consumeTrail:true}).then(ok=>{if(ok!==false)return place.restore(back);});}));}
      if(research.returning())toolbar.prepend(ui.button('Back to Research',()=>{research.clearReturn();return views.show('research');}));

      if(!query.node){const purpose=E('section','','logical-purpose'),framing=workState.get()?.framing?.framing||{};purpose.append(E('p',
        framing.purpose||'No concise project purpose has been recorded.','project-home-purpose'));if(framing.question)purpose.append(E('p',
        'Central question: '+framing.question));if(framing.audience)purpose.append(E('p','For: '+framing.audience,'muted'));if(workState.get(
        )?.framing?.argument){const argument=E('details');argument.append(declareControl(E('summary','Read the authored argument'),'argument:read-authored'));const content=E('div');
        argument.append(content);argument.ontoggle=()=>{if(argument.open&&!argument.dataset.loaded){argument.dataset.loaded='true';
        inspect.savedMarkdown(content,workState.get().framing.argument);}};purpose.append(argument);}host.append(purpose);}
      const controller=await mountConceptExplorer(host,{project,data,recordState,logicalPlan,indexMode:!query.node,request:api,navigate:query=>renderConceptTree(host,query),
        onPlacement:manuscript.openPlacement,onWork:work.open,onEvidence:((...args)=>research.openEvidence(...args)),onLiterature:node=>
          research.openLiterature({claim_id:node.id,label:title(node)}),onDirty:value=>{forms.setDirty(value);},onSource:source=>
          manuscript.inspectPassage({file:source.manuscript_file||source.file||source.path,line_start:source.line_start||source.line||1,
          quote:source.quote}),manageQuestion:id=>editNodeDetails(id,host),question:id=>openObligation(id,host),discuss:node=>{activeNode=node;
          discussion.session().scope();discussion.talk();},formalise:(node,record)=>{activeNode=node;discussion.session().clearSelection();
          discussion.session().scope();discussion.talk('Formalise '+title(
          node)+' ('+node.id+
          ') in this project. Read its current proof target, exact statement, hypotheses and source identity; use the existing Lean workspace and relevant library results, check the proof, and bind the receipt to this concept and source revision. Report any remaining obligations and explain how the formal statement aligns with the scientific statement.');
          },
        onFocus:node=>{activeNode=node;graphQuery={...graphQuery,node:node.id};localStorage.setItem(focusKey,node.id);const uri=new URL(
          location.href);uri.searchParams.set('node',node.id);history.replaceState({},'',uri);discussion.session().scope();},onError:message=>ui.notice(message,true)});
      if(argumentSurface)argumentSurface.recordController=controller;
      if(data.hierarchy_gaps?.length){const gaps=section(host,'Containment needs attention');for(const gap of data.hierarchy_gaps)gaps.append(E('p',gap.reason||gap.kind,'error'));}
    }catch(error){host.append(E('p',error.message,'error'));return false;}
  }
  async function inspectNode(id,host){views.setMode('graph');return renderConceptTree(host,{project,node:id});}
  async function editNodeDetails(id,host){
    const data=await api('/concepts/state?project='+enc+'&node='+encodeURIComponent(id));activeNode=data.focus;localStorage.setItem(focusKey,id);
      discussion.session().scope();host.querySelector('[data-node-editor]')?.remove();const card=section(host,title(data.focus));
      card.dataset.nodeEditor='';await renderConceptRecord(card,{node:data.focus,state:data,showTitle:false,resolveReference:(ref,index)=>api(
      '/concepts/source?'+new URLSearchParams({project,node:id,source_index:index,label:ref.key})),onNavigate:node=>renderConceptTree(host,{project,
      node}),onSource:source=>manuscript.inspectPassage({file:source.manuscript_file||source.file||source.path,line_start:source.line_start||
      source.line||1})});if(data.mathematical_record)mountMathematicsEditor(card,{record:data.mathematical_record,node:data.focus,state:data,project,
      request:api,onDirty:value=>{forms.setDirty(value);},onSaved:()=>inspectNode(id,host)});const editing=E('details');editing.append(E('summary',
      'Edit description and relationships'));const editorBody=E('div');editing.append(editorBody);card.append(editing);const f=E('form');area(f,
      'Meaning, definition or claim','essence',data.focus.summary,6);f.append(E('button','Save meaning','primary'));forms.wire(f,async values=>{
      await api('/concepts/change',{project,by:'author',operation:'edit_node',node:id,value:values.essence,...conceptChangeGuard(data,id,
      'edit_node')});forms.setDirty(false);await views.show('structure',false);ui.notice('Concept meaning saved.');});editorBody.append(f,ui.button(
      'Work through this concept',()=>discussion.talk()));
    const obligation=data.focus.projection?.obligation;if(obligation){const status=section(card,'Question state',
      `${obligation.state} · ${obligation.work_kind}. Discharge when: ${obligation.discharge_condition}`);if(
      obligation.evidence?.length)status.append(E('p','Evidence: '+obligation.evidence.join(', ')));if(obligation.disposition)status.append(E('p',
      'Disposition: '+obligation.disposition));{const resolve=E('form');field(resolve,'State','state','addressed',[['addressed',
      'Addressed (not independently verified)'],['withdrawn','Withdrawn'],['open','Keep open']]);area(resolve,'Evidence references, one per line',
      'evidence');area(resolve,'Explained disposition','disposition');resolve.append(E('button','Save question state'));forms.wire(resolve,
      async values=>{const planState=await api('/concepts/plan?project='+enc+'&focus='+encodeURIComponent(id));await api('/concepts/plan/change',{
      project,operation:'update_obligation',base_revision:planState.revision,node:id,state:values.state,evidence:values.evidence.split('\n').map(s=>
      s.trim()).filter(Boolean),disposition:values.disposition,by:'author'});forms.setDirty(false);await views.show('structure',false);ui.notice(
      'Question state saved; this does not award independent verification.');});status.append(resolve,ui.button('Route to project work',async()=>{
      const planState=await api('/concepts/plan?project='+enc+'&focus='+encodeURIComponent(id));await api('/concepts/plan/change',{project,
      operation:'route_obligation',base_revision:planState.revision,node:id,by:'author'});await workState.reload();ui.notice(
      'Question routed with its stable logical identity.');}));}}
    const map=E('details');map.append(E('summary','Show dependency map'));const mapBody=E('div');map.append(mapBody);card.append(map);drawConceptMap(mapBody,data);
    const named=Object.fromEntries([data.focus,...(data.neighbors||[])].map(n=>[n.id,title(n)]));for(const relation of data.relations||[]){
      const row=E('div','','relation-row');const other=relation.source===id?relation.target:relation.source;row.append(E('p',
      `${named[relation.source]||relation.source} → ${named[relation.target]||relation.target} · ${relation.rel}`),ui.button('Inspect '+(named[
      other]||other),()=>inspectNode(other,host)));const edit=E('details');edit.append(E('summary','Edit this relationship'));const form=E('form');
      field(form,'Relationship to '+(named[other]||other),'rel',relation.rel,[['prerequisite','Requires'],['support','Supported by'],[
      'counterevidence','Counterevidence from'],['validated_by','Validated by'],['implementation','Implemented by'],['analogy','Analogous to'],[
      'questions','Questions']]);area(form,'Reason for this relationship','rationale',relation.rationale||'');form.append(E('button',
      'Save relationship'));forms.wire(form,async values=>{await api('/concepts/change',{project,operation:'retype_edge',node:relation.source,
      target:relation.target,rel:values.rel,rationale:values.rationale,base_revision:data.revision,by:'author'});forms.setDirty(false);
      await views.show('structure',false);ui.notice('Relationship saved.');});edit.append(form);row.append(edit);editorBody.append(row);}
    const edge=E('form');const search=field(edge,'Find the related concept','concept_query');const target=field(edge,'Related concept','target','',[
      ]);target.required=true;let searchTimer;search.oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(async()=>{try{
      const found=await api('/concepts/catalog?project='+enc+'&q='+encodeURIComponent(search.value)+'&limit=40');target.replaceChildren();for(
      const node of found.items.filter(n=>n.id!==id)){const o=E('option',title(node));o.value=node.id;target.append(o);}}catch(error){ui.notice(
      error.message,true);}},200);};field(edge,'Relationship','rel','prerequisite',[['prerequisite','Requires'],['support','Supported by'],[
      'counterevidence','Counterevidence from'],['validated_by','Validated by'],['implementation','Implemented by'],['analogy','Analogous to']]);
      const rationale=area(edge,'Why this step follows or bears on the object','rationale');rationale.required=true;edge.append(E('button',
      'Add dependency'));forms.wire(edge,async values=>{await api('/concepts/change',{project,by:'author',operation:'add_edge',node:id,
      target:values.target,rel:values.rel,rationale:values.rationale,base_revision:data.revision});forms.setDirty(false);await views.show('structure',
      false);ui.notice('Typed dependency saved with its reasoning.');});editorBody.append(edge);
    const research=await api('/research/state?project='+enc);if(research.results?.length){const bind=E('form');const result=field(bind,
      'Result linked to this concept','result','',research.results.map(r=>[r.id,r.title||r.id]));bind.append(E('button','Bind this result'));
      bind.onsubmit=forms.guard(async()=>{const row=research.results.find(r=>r.id===result.value);await readerPlan.plan('bind_results',{node:id,
      expected_concept_revision:data.revision,results:[...(data.focus.projection?.result_bindings||[]).filter(r=>r.id!==row.id),{id:row.id,
      revision:row.revision}]});});editorBody.append(bind);}
    const main=ui.$('[data-main]');main.scrollTop+=card.getBoundingClientRect().top-main.getBoundingClientRect().top-20;
  }
  async function openObligation(targetId,host){
    activeNode={id:targetId,label:targetId};localStorage.setItem(focusKey,targetId);discussion.session().scope();host.querySelector(
      '[data-obligation-editor]')?.remove();const card=section(host,'Name an open question',
      'This stays on the canonical logical object. It is not automatically a code ticket and addressing it is not verification.');card.dataset.obligationEditor='';
    const form=E('form');field(form,'Question identity','node','question:'+slug(targetId)+'-'+Date.now().toString(36)).required=true;area(form,
      'Question or missing reasoning','meaning').required=true;field(form,'Owning work','work_kind','concept',[['concept','Conceptual reasoning'],[
      'research','Research'],['literature','Literature'],['computation','Computation'],['formal','Formal proof'],['author-decision',
      'Author decision']]);area(form,'Discharge condition','discharge_condition').required=true;form.append(E('button','Save open question',
      'primary'));forms.wire(form,async values=>{const planState=await api('/concepts/plan?project='+enc+'&focus='+encodeURIComponent(targetId));
      const made=await api('/concepts/plan/change',{project,operation:'add_obligation',base_revision:planState.revision,node:values.node,
      meaning:values.meaning,target:{kind:'node',node_id:targetId},work_kind:values.work_kind,discharge_condition:values.discharge_condition,
      by:'author'});forms.setDirty(false);activeNode=made.state.selected;await renderConceptTree(host,{project,node:targetId});ui.notice(
      'Open question saved on the canonical logical plan.');});card.append(form);form.elements.meaning.focus();
  }
  function drawConceptMap(host,data){
    const panel=E('div','','concept-map');panel.append(E('p',
      'Dependency map · arrows point from a claim to what it requires or draws on. Unknown relations remain unclassified.','muted'));
    const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 760 420');svg.setAttribute('role',
      'img');svg.setAttribute('aria-label','Declared dependencies of '+title(data.focus));
    const defs=document.createElementNS(ns,'defs'),marker=document.createElementNS(ns,'marker');marker.id='concept-arrow';marker.setAttribute(
      'viewBox','0 0 10 10');marker.setAttribute('refX','9');marker.setAttribute('refY','5');marker.setAttribute('markerWidth','6');
      marker.setAttribute('markerHeight','6');marker.setAttribute('orient','auto-start-reverse');const arrow=document.createElementNS(ns,'path');
      arrow.setAttribute('d','M 0 0 L 10 5 L 0 10 z');arrow.setAttribute('fill','var(--accent)');marker.append(arrow);defs.append(marker);svg.append(defs);
    const neighbors=(data.neighbors||[]).slice(0,8),points=new Map([[data.focus.id,{x:380,y:210,node:data.focus}]]);neighbors.forEach((node,i)=>{
      const angle=(i/Math.max(neighbors.length,1))*Math.PI*2-Math.PI/2;points.set(node.id,{x:380+260*Math.cos(angle),y:210+155*Math.sin(angle),node});});
    for(const relation of data.relations||[]){const a=points.get(relation.source),b=points.get(relation.target);if(!a||!b)continue;const dx=b.x-a.x,
      dy=b.y-a.y,len=Math.hypot(dx,dy)||1,t=Math.min(101/(Math.abs(dx)||0.0001),36/(Math.abs(dy)||0.0001));const edge=document.createElementNS(ns,
      'line');edge.setAttribute('x1',String(a.x+dx*t));edge.setAttribute('y1',String(a.y+dy*t));edge.setAttribute('x2',String(b.x-dx*t));
      edge.setAttribute('y2',String(b.y-dy*t));edge.setAttribute('stroke','var(--green-70)');edge.setAttribute('stroke-width','1.5');if(
      relation.rel==='unknown')edge.setAttribute('stroke-dasharray','5 4');edge.setAttribute('marker-end','url(#concept-arrow)');svg.append(edge);}
    for(const {x,y,node}of points.values()){const g=document.createElementNS(ns,'g');g.setAttribute('role','button');g.setAttribute('tabindex','0');
      g.setAttribute('aria-label','Inspect '+title(node));g.style.cursor='pointer';const rect=document.createElementNS(ns,'rect');rect.setAttribute(
      'x',x-95);rect.setAttribute('y',y-30);rect.setAttribute('width','190');rect.setAttribute('height','60');rect.setAttribute('rx','8');
      rect.setAttribute('fill',node.id===data.focus.id?'var(--green-40)':'var(--panel)');rect.setAttribute('stroke','var(--green-60)');g.append(rect);
      const name=document.createElementNS(ns,'text');name.setAttribute('x',String(x));name.setAttribute('y',String(y-3));name.setAttribute(
      'text-anchor','middle');name.setAttribute('fill','var(--ink)');name.setAttribute('font-size','12');name.textContent=title(node).slice(0,26);
      const kind=document.createElementNS(ns,'text');kind.setAttribute('x',String(x));kind.setAttribute('y',String(y+15));kind.setAttribute(
      'text-anchor','middle');kind.setAttribute('fill','var(--accent)');kind.setAttribute('font-size','10');kind.textContent=node.kind||
      'unclassified';g.append(name,kind);const inspect=()=>forms.guard(()=>renderConceptTree(ui.$('[data-main]').lastElementChild,{project,
      node:node.id}))();g.onclick=inspect;g.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();inspect();}};svg.append(g);}
    panel.append(svg);if((data.neighbors?.length||0)>8)panel.append(E('p',
      'The focused map shows eight neighbors; all declared relationships are listed below.','muted'));host.append(panel);
  }
  return {
    render:renderConceptTree,
    // one concept opened from another view (research, reader plan, activity, a manuscript passage)
    openConcept:async(node,{origin,view='structure'}={})=>{if(origin!==undefined)logicalOrigin=origin;views.setMode('graph');
      graphQuery={project,node};await views.show(view,false);},
    setOrigin:anchor=>{logicalOrigin=anchor;},
    restoreQuery:query=>{graphQuery=query;},
    logical:()=>graphState?.current||argumentSurface?.scope||null,
    // the conversation context of this view (the shell supplies the selected work and structure read)
    context:(task,structure)=>{
      if(argumentSurface?.host?.isConnected&&!argumentSurface.reading)return {surface:'structure',label:argumentSurface.scope?.label||'Argument overview',
        node_id:argumentSurface.scope?.id,node_ids:argumentSurface.scope?.node_ids,task_id:task?.id,section_ids:[]};
      if(graphQuery.node&&graphState?.current)return {surface:'structure',label:title(graphState.current),task_id:task?.id,node_id:graphState.current.id,
        section_ids:(structure?.sections||[]).filter(section=>(section.node_ids||[]).includes(graphState.current.id)
          ||(section.beat_ids||[]).includes(graphState.current.id)).map(section=>section.id)};
      return null;},
    returnPlace:()=>({view:'argument',query:{...graphQuery},label:graphState?.current?title(graphState.current):'Argument & evidence'}),
    captureSurface:()=>({recordScroll:argumentSurface?.record?.scrollTop||0,argument:argumentSurface?.controller?.capture()}),
    restoreSurface:place=>{if(argumentSurface?.record)argumentSurface.record.scrollTop=place.recordScroll||0;
      if(place.argument)argumentSurface?.controller?.restore(place.argument);},
    // leaving the view keeps the surface memory for the next visit and forgets the graph state
    release:()=>{if(argumentSurface?.host?.isConnected){argumentMemory=argumentSurface.controller?.capture();argumentSurface.controller?.destroy();
      argumentSurface.resize?.disconnect();argumentSurface=null;}graphState=null;},
    destroy:()=>{argumentSurface?.controller?.destroy();argumentSurface?.resize?.disconnect();argumentSurface=null;},
    canGoBack:()=>conceptTrail.length>0||!!(graphQuery.node&&graphState?.navigation?.ascent?.available),
    back:host=>{if(conceptTrail.length){const back=conceptTrail.at(-1);renderConceptTree(host,back.query,{remember:false,consumeTrail:true})
      .then(ok=>{if(ok!==false)return place.restore(back);});}else renderConceptTree(host,graphState.navigation.ascent.query,{remember:false});},
  };
}
