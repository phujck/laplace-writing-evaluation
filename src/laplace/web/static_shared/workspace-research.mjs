// WORKSPACE RESEARCH (M5 S2 F1). Purpose: the Research view of the shell: the evidence tabs (numerics and
// formal proof, mounted through writing-evidence's mountEvidence), the literature view (workspace-literature's
// mountLiterature), connecting a result to a claim, and the research navigation memory (subview, literature
// target and reader, return to research) kept in the URL and sessionStorage. Ownership: research records,
// literature and claims belong to their owners (writing-evidence, /concepts, /work/structure); this
// controller owns only its view memory and the one literature controller. Public contract:
// mountResearch(project, services) -> {render(host), openLiterature(target), openEvidence(id, options),
// openSource(reader), openFormal(id), discuss(text, target), attention(), returning(), markReturn(),
// clearReturn(), url(href, {active}), release()}; the pure navigation helpers researchNavigation,
// researchNavigationURL, loadResearchNavigation, saveResearchNavigation, researchBindingCandidates and
// focusHistoryResearchTarget (re-exported by workspace.mjs). Services: start (the loaded navigation), info,
// views (current view, show), forms (dirty, leave), ui (notice, button, main), structures (the shell's one
// structure read), argument (openConcept), manuscript (ready, saved, source window, passage, placement),
// place (the reader return), discussion (talk, session), figures (place). Lifetime: a research generation
// guards late evidence callbacks; release() destroys the literature controller.
import {E,field,title} from './workspace-dom.mjs';
import {projectRequest as api} from "/shared/workspace-session.mjs";
import {focusResearchResult,mountEvidence} from "/shared/writing-evidence.mjs";
import {pendingRead} from "/shared/pending-read.mjs";
import {mountLiterature} from "/shared/workspace-literature.mjs";
import {workspaceViewAvailable} from "/shared/workspace-material.mjs";
// wave 13 id sweep: control ids by tag and label (begin)
import {declareControl} from './workspace-presentation.mjs';
// wave 13 id sweep: control ids (end)

export function researchBindingCandidates(nodes,query=''){
  const kinds=new Set(['goal','definition','postulate','derivation-step','lemma','intermediate-result','result','theorem','support','technique']);
  const needle=query.trim().toLowerCase();
  return nodes.filter(node=>kinds.has(node.kind)&&(!needle||[node.id,title(node),node.summary].join(' ').toLowerCase().includes(needle))).sort((a,b)=>
    title(a).localeCompare(title(b))||a.id.localeCompare(b.id));
}
export function researchNavigation(query,saved={}){
  if(!saved||typeof saved!=='object')saved={};
  const views=new Set(['numerics','formal','literature']),explicit=views.has(query.get('research')),subview=explicit?query.get('research'):views.has(
    saved.subview)?saved.subview:'numerics';
  let target=saved.literatureTarget&&(saved.literatureTarget.claim_id||saved.literatureTarget.anchor)?saved.literatureTarget:null;
  if(explicit&&subview==='literature'){
    const claim=query.get('research_claim');
    if(claim)target=target?.claim_id===claim?target:{claim_id:claim,label:claim};
    else if(query.get('research_scope')!=='passage'||!target?.anchor||target.claim_id)target=null;
  }
  let reader=saved.literatureReader||null;if(explicit&&subview==='literature'){const key=query.get('research_source');reader=key?{key,
    title:reader?.key===key?reader.title:key,source_index:Math.max(0,Number(query.get('research_source_index'))||0),offset:Math.max(0,Number(
    query.get('research_source_offset'))||0),mode:query.get('research_source_mode')==='text'?'text':'source'}:null;}
  return {subview,literatureTarget:target,literatureReader:reader,returnPlace:saved.returnPlace?.view==='research'?saved.returnPlace:null,
    returnToResearch:query.get('research_return')==='1'};
}
export function researchNavigationURL(url,{subview,literatureTarget,literatureReader=null,returnToResearch=false},{active=true}={}){
  const next=new URL(url);for(const key of ['research','research_claim','research_scope','research_return','research_source','research_source_index',
    'research_source_offset','research_source_mode'])next.searchParams.delete(key);
  if(active||returnToResearch){next.searchParams.set('research',subview);if(subview==='literature'){next.searchParams.set('research_scope',
    literatureTarget?.claim_id?'claim':literatureTarget?.anchor?'passage':'project');if(literatureTarget?.claim_id)next.searchParams.set(
    'research_claim',literatureTarget.claim_id);if(literatureReader?.key){next.searchParams.set('research_source',literatureReader.key);
    next.searchParams.set('research_source_index',String(literatureReader.source_index||0));if(literatureReader.offset)next.searchParams.set(
    'research_source_offset',String(literatureReader.offset));if(literatureReader.mode==='text')next.searchParams.set('research_source_mode','text');
    }}if(returnToResearch)next.searchParams.set('research_return','1');}
  if(active){next.searchParams.delete('node');next.searchParams.delete('structure');next.searchParams.delete('logical');}
  return next;
}
export function loadResearchNavigation(project,query){let saved={};try{saved=JSON.parse(globalThis.sessionStorage?.getItem(
  'laplace:research-navigation:'+project)||'{}');}catch{}return researchNavigation(query,saved);}
export function saveResearchNavigation(project,state){try{globalThis.sessionStorage?.setItem('laplace:research-navigation:'+project,JSON.stringify({
  subview:state.subview,literatureTarget:state.literatureTarget||null,literatureReader:state.literatureReader||null,returnPlace:state.returnPlace||null}));}catch{}}

export function focusHistoryResearchTarget(main,card){
  // The target is newly rendered; its reader starts at the top independently of
  // the History page whose own scroll was captured before navigation.
  main.scrollTop=0;
  if(card){card.tabIndex=-1;card.focus({preventScroll:true});}
}
export function mountResearch(project,{enc,start,views,forms,ui,structures,argument,manuscript,place,discussion,figures}){
  // the domain's own memory (moved out of the shell closure)
  let returnToResearch=start.returnToResearch,
    researchAttention=null,
    literatureTarget=start.literatureTarget,
    literatureReader=start.literatureReader,
    literatureController=null,
    researchTab=start.subview;
  function rememberResearch(){saveResearchNavigation(project,{subview:researchTab,literatureTarget,literatureReader,
    returnPlace:place.workspaceReturn.current?.view==='research'?place.workspaceReturn.current:null});history.replaceState({},'',
    researchNavigationURL(location.href,{subview:researchTab,literatureTarget,literatureReader,returnToResearch},{active:views.current()==='research'}));}
  function discussResearch(text,target=null){researchAttention=target;discussion.session().scope();discussion.talk(text,'work',target?.anchor?{files:[
    target.anchor.file].filter(Boolean),quote:target.anchor.quote||target.anchor.text,anchor:target.anchor}:undefined);}
  async function openLiterature(target=null){literatureTarget=target;literatureReader=null;researchTab='literature';saveResearchNavigation(project,{
    subview:researchTab,literatureTarget,literatureReader});await views.show('research',false);}
  async function renderResearch(host){
    host.replaceChildren(E('div','Literature · experiments · results · proof','eyebrow'),E('h2','Establish the evidence'));
    const tabs=E('div','','inner-tabs'),body=E('div');host.append(tabs,body);let researchGeneration=0;
    const evidence=async(view='numerics')=>{const generation=++researchGeneration;literatureController?.destroy();literatureController=null;
      researchTab=view;researchAttention=null;rememberResearch();discussion.session().scope();const pane=E('div');body.replaceChildren(pane);for(
      const tab of tabs.children)tab.setAttribute('aria-pressed',String(tab.dataset.researchTab===view));return mountEvidence(pane,{view,pending:pendingRead,
      onAttention:attention=>{if(generation!==researchGeneration||!pane.isConnected)return;researchAttention=attention;discussion.session().scope();},
      bindResult:workspaceViewAvailable(views.info(),'argument')?bindResearchResult:null,onOpenUsage:async usage=>{if(!forms.leave())return;
      const nextStructure=await api('/work/structure?project='+enc);if(generation!==researchGeneration||!pane.isConnected)return;
      returnToResearch=true;structures.set(nextStructure);if(usage.location){await manuscript.openPlacement(usage.location);}else{
      await argument.openConcept(usage.concept.id);}},project,request:api,status:(text,error)=>{if(generation===researchGeneration&&
      pane.isConnected)ui.notice(text,error);},work:discussResearch,onDiscussResult:record=>discussResearch(
      'Inspect research record '+record.id+' at revision '+record.revision+
      '. Explain what was tested, the measured findings, the assumptions and limitations, and the exact claims supported by this evidence.',{
      label:record.title||record.id,result_id:record.id}),navigate:view=>views.show(view),place:spec=>figures.place(spec),refresh:async()=>{
      await manuscript.sourceWindow()?.walk?.refresh?.();},comment:spec=>discussResearch('Review this figure: '+spec.id,{label:spec.title||spec.id})});};
    const literature=()=>{researchGeneration++;researchTab='literature';rememberResearch();const pane=E('div');body.replaceChildren(pane);for(
      const tab of tabs.children)tab.setAttribute('aria-pressed',String(tab.dataset.researchTab==='literature'));return renderLiterature(pane);};
    for(const [id,label]of [['numerics','Numerics & results'],['formal','Formal proof'],['literature','Literature']]){const tab=declareControl(ui.button(label,()=>{
      if(!forms.leave())return;forms.setDirty(false);return id==='literature'?literature():evidence(id);}),'research:tab',id);tab.dataset.researchTab=id;tabs.append(
      tab);}if(researchTab==='literature')await literature();else await evidence(researchTab);
  }
  async function bindResearchResult(result,onSaved=async()=>{}){
    const joined=await api('/work/structure?project='+enc),candidates=researchBindingCandidates(joined.logical_objects||[]);
    const dialog=E('dialog','','workspace-dialog');dialog.append(E('h3','Connect result to a claim'),E('p',result.title||result.id));
    const form=E('form');const query=field(form,'Find a claim','query'),choose=field(form,'Claim supported by this result','node','',[]);choose.required=true;choose.size=7;
    const identity=E('p','','muted'),message=E('p'),actions=E('div','','work-actions'),save=E('button','Save binding','primary');save.disabled=true;
      actions.append(save,ui.button('Cancel',()=>dialog.close()));form.append(identity,actions);dialog.append(form,message);
    const refreshSelection=()=>{const selected=candidates.find(node=>node.id===choose.value);save.disabled=!selected;
      identity.textContent=selected?selected.kind.replaceAll('-',' ')+' · '+selected.id:'';};
    const search=()=>{const previous=choose.value,found=researchBindingCandidates(candidates,query.value),placeholder=E('option','Choose a claim');
      placeholder.value='';placeholder.disabled=true;placeholder.selected=true;choose.replaceChildren(placeholder);for(const node of found){
      const option=E('option',title(node)+' — '+node.kind.replaceAll('-',' '));option.value=node.id;option.title=node.id;choose.append(option);
      }choose.value=found.some(node=>node.id===previous)?previous:'';refreshSelection();
      message.textContent=found.length?'':query.value?'No matching logical claims. Try another name or identity.':
      'This project has no logical claims to connect yet. Create the claim in Logical structure first.';};
    query.oninput=search;choose.onchange=refreshSelection;
    form.onsubmit=async event=>{event.preventDefault();const node=choose.value;if(!candidates.some(item=>item.id===node))return;save.disabled=true;
      try{const [focused,current]=await Promise.all([api('/concepts/state?project='+enc+'&node='+encodeURIComponent(node)),api(
      '/work/structure?project='+enc)]);const bindings=focused.focus.projection?.result_bindings||[];await api('/work/structure/change',{project,
      operation:'bind_results',expected_revision:current.revision,expected_concept_revision:focused.revision,node,results:[...bindings.filter(row=>
      row.id!==result.id),{id:result.id,revision:result.revision}]});dialog.close();ui.notice('Result connected to '+title(candidates.find(item=>
      item.id===node))+'.');try{await onSaved();}catch(error){ui.notice(
      'The result was connected, but its displayed usage could not refresh: '+error.message,true);}}catch(error){message.textContent=error.message;
      message.className='error';refreshSelection();}};
    dialog.onclose=()=>dialog.remove();document.body.append(dialog);dialog.showModal();search();query.focus();
  }

  async function renderLiterature(host){
    literatureController?.destroy();const requestedClaim=literatureTarget?.claim_id;if(requestedClaim&&literatureTarget.label===requestedClaim){try{
      const focused=await api('/concepts/state?'+new URLSearchParams({project,node:requestedClaim}));if(host.isConnected&&
      literatureTarget?.claim_id===requestedClaim&&focused.focus?.id===requestedClaim)literatureTarget={...literatureTarget,label:title(
      focused.focus)};}catch(error){if(host.isConnected&&literatureTarget?.claim_id===requestedClaim)ui.notice(
      'The selected claim could not be refreshed: '+error.message,true);}}if(!host.isConnected)return;researchAttention=literatureTarget;
      rememberResearch();discussion.session().scope();
    literatureController=mountLiterature(host,{project,request:api,status:(text,error)=>{if(host.isConnected)ui.notice(text,error);},
      target:literatureTarget,reader:literatureReader,onReaderChange:reader=>{if(!host.isConnected)return;literatureReader=reader;rememberResearch();},
      onTargetChange:target=>{if(!host.isConnected)return;literatureTarget=target;literatureReader=null;researchAttention=target;rememberResearch();discussion.session().scope();},
      onOpenPassage:span=>manuscript.inspectPassage({...span,quote:span.text}),
      onOpenConcept:async node=>{returnToResearch=true;await argument.openConcept(node.id);},
      onInsertCitation:async value=>{if(!forms.leave())return;manuscript.saved();place.remember();const walk=await manuscript.ready();if(!walk)return;
        if(value.anchor)await manuscript.inspectPassage(value.anchor);walk.armCitationPlacement(value.citekey);return {state:'armed',citekey:value.citekey};},
      onDiscuss:discussResearch,onDirty:value=>{forms.setDirty(value);}});
    await literatureController.ready;
  }
  async function openEvidence(id,{fromHistory=false}={}){focusResearchResult(project,id,'numerics');researchTab='numerics';saveResearchNavigation(
    project,{subview:researchTab,literatureTarget,literatureReader});await views.show('research',false);const main=ui.main(),card=[
    ...main.querySelectorAll('[data-research-id]')].find(node=>node.dataset.researchId===id);if(card){if(fromHistory)focusHistoryResearchTarget(main,
    card);else{main.scrollTop+=card.getBoundingClientRect().top-main.getBoundingClientRect().top-16;card.focus({preventScroll:true});}}else ui.notice(
    'This result is not available in the current research records.',true);}
  return {
    render:renderResearch,openLiterature,openEvidence,discuss:discussResearch,
    // a literature source or a formal target opened from another view (reader plan, activity)
    openSource:reader=>{literatureTarget=null;literatureReader=reader;researchTab='literature';return views.show('research',false);},
    openFormal:async id=>{focusResearchResult(project,id,'formal');researchTab='formal';await views.show('research',false);
      focusHistoryResearchTarget(ui.main(),ui.main().querySelector('.formal-target'));},
    attention:()=>researchAttention,returning:()=>returnToResearch,
    markReturn:()=>{returnToResearch=true;rememberResearch();},clearReturn:()=>{returnToResearch=false;},
    url:(href,{active})=>researchNavigationURL(href,{subview:researchTab,literatureTarget,literatureReader,returnToResearch},{active}),
    release:()=>{literatureController?.destroy();literatureController=null;},
  };
}
