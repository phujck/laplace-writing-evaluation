// WORK (plan §5). Purpose: see what waits, why, and clear it: the catalogue (with navigation:true the
// Work navigator of workspace-work-navigator.mjs, roots and branches level by level, and the flat owner
// list projection as a secondary All Work disclosure; without it the flat list alone, paged with More),
// the selected Work as an object (header with Part of parent, chips, summary, its qualified activity),
// Why waiting (blocker cards with the owner's clearing action), Progress and next action (the owner's continuity summary,
// workspace-work-review.mjs continuitySection), acceptance condition, the review
// lifecycle (workspace-work-review.mjs), the relationships panel Needs/Affects/Contains
// (workspace-work-relations.mjs), the neighbourhood map (one paged graph read, drawn and listed by
// workspace-topology with folded wide levels), coordination ladder, recorded evidence, actions, Work
// basis (exact ids, revisions, the parent's exact id), the owner's action/context descriptor and the
// guarded authored-work and disposition forms. The authored title/purpose draft, its original guard, its attempts
// and owner results belong to the Work port (work-port.mjs): this card is that port's current-view adapter and
// keeps only the separate containing-work control. Ownership: project_work (/work/state summary|detail|
// graph|roots|branch|attention, /work/task, task_status, work_review, dispatch) owns rows, standing
// facets, guards and pages; prepared-work.mjs owns the continuation ladder; this module paints, keeps
// drafts and lends its closures to its sections. Public contract: mountOperatorWork (controller with
// capture()/select()/observed()/refreshNavigation()/destroy()), renderWorkNeighbourhood, operatorHTTP,
// workStandingLabel/Tone, workCountSummary. observed(hint) takes the observer's change hint
// (workspace-work-observer.mjs): it rereads the open navigator level, paints an activity-only change in
// place, and rereads the selected Work only without a dirty draft (whose status then says whether its
// own consumed guard changed) and without focus inside the detail. Currentness: the read_cut revision on every
// continuation; a changed cut refuses. Copy: the parent's loaded title is shown and its exact id
// stays under Work basis; no read is issued for a label. Errors: inline beside the action; drafts
// and guards retained across reinspection. Storage: drafts in the controller's memory (captured
// by the shell per view). Controls: work:item, work:next-step, work:prerequisites,
// work:neighbourhood, work:disposition, work:review.
import {renderPreparedWork,renderParentContinuation,renderDispatchChildren,parentContinuation,parentContinuationLabel} from './prepared-work.mjs';
import {ownerHumanTarget,isKnownOwnerReadRoute} from './writing-owner-read.mjs';
import {renderMaterialObservation} from './workspace-material-observation.mjs';
import {objectHeader,stateChip,actionRow,lazySection,relationList,presentationStyles,declareControl} from './workspace-presentation.mjs';
import {mountTopology} from './workspace-topology.mjs';
import {workReviewSection,continuitySection} from './workspace-work-review.mjs';
import {workRelations} from './workspace-work-relations.mjs';
import {mountWorkNavigator,standingChip,completedTaskChip,taskStateChips,taskStatusName,taskStatusMeaning} from './workspace-work-navigator.mjs';
import {createWorkPort,WORK_PORT_CAPTURE} from './work-port.mjs';
import {createLifetime} from './selected-lifetime.mjs';
import {pendingRead} from './pending-read.mjs';
// Focused operator reader over project_work. It stores drafts/place, never work truth.
//
// Owner contract consumed (project_work_views): the catalogue is the summary LIST
// projection (identity, structure, standing facets, read_handle; no revision pins), paged
// by the owner's next_read under one read_cut; the selected Work is one detail read (FULL
// projection with blockers, allowed actions, acceptance, relations, evidence reads), and
// every guarded action or message target takes its pins from that detail, never a row.
// Blockers arrive with subject.title/standing, relation, an id-free sentence and kinded
// next_actions; this module prints them and never derives a title from an id.
// Presentation: the selected Work leads with its title, state chips, the owner's current
// summary and the one next step; exact pins, cuts and forms stay behind deliberate reads.
// C4 (M5, 2026-10-14): after Why waiting come the acceptance condition, the Prerequisites
// relation list (every depends_on with its current standing from the owner rows this view
// holds), the Neighbourhood map (one paged graph read per selected Work, deliberate, drawn
// and listed by workspace-topology from the same page, continued under the owner cut) and
// the coordination ladder; the campaign-relationships dialog is retired, its one other
// consumer (writing-artifact's graph panel) renders the same neighbourhood.
// Controls declared in writing_declarations CONTROL_DECLARATIONS: work:item (catalogue
// row), work:next-step (the blocker's primary action), work:prerequisites,
// work:neighbourhood, work:disposition.
const el=(tag,text='',cls='')=>{const n=document.createElement(tag);n.textContent=text;n.className=cls;return n;};
const query=(project,view,values={})=>'/work/state?'+new URLSearchParams({project,view,...values});
export function operatorHTTP(handle,{method='GET',base=globalThis.location?.href||'http://local/'}={}){
  const h=handle?.http;if(!h||h.method!==method||typeof h.url!=='string')throw Error('The owner has not supplied a '+method+' route for this action.');
  const url=new URL(h.url,base);if(url.origin!==new URL(base).origin||!url.pathname.startsWith('/'))throw Error('Owner route is outside this local engine.');
  return url.pathname+url.search;
}
const title=row=>row?.title||row?.id||'Unavailable work';
export function workStandingLabel(row={}){
  const completed=completedTaskChip(row);if(completed)return completed.label;
  if(!row.lifecycle)return row.status||row.effective_status||'Not observed';
  const recorded='Recorded '+String(row.lifecycle.status||'unknown').replaceAll('_',' ').replaceAll('-',' ');
  const continuation=row.parent_continuation||row.dispatch?.parent_continuation;
  if(continuation){try{return recorded+' · '+parentContinuationLabel(parentContinuation(continuation,{project:row.project}));}catch{return recorded+' · continuation needs reinspection';}}
  if(row.current_acceptance?.review_required===true)return recorded+' · current review required';
  return recorded+(row.lifecycle.closed===false&&row.readiness?.status?' · readiness '+row.readiness.status.toLowerCase().replaceAll('_',' '):'');
}
// Tone for the catalogue badge; the label stays the owner's standing sentence.
export function workStandingTone(row={}){
  const completed=completedTaskChip(row);if(completed)return completed.tone;
  if(row.readiness?.status==='BLOCKED'||/blocked/i.test(row.status||''))return 'neutral';
  if(row.current_acceptance?.review_required===true)return 'attention';
  if(row.lifecycle?.completed===true||/^(done|verified|cancelled)$/i.test(row.status||''))return 'historical';
  if(row.readiness?.status==='READY')return 'ok';
  const continuation=row.parent_continuation||row.dispatch?.parent_continuation;
  if(continuation?.phase==='WAITING')return 'running';
  return 'neutral';
}
export function workCountSummary(value={}){
  const counts=value.counts||{},known=n=>Number.isInteger(n)&&n>=0,parts=[];
  if(known(counts.pending))parts.push(counts.pending+' pending tasks');
  if(known(counts.completed))parts.push(counts.completed+' recorded completions');
  if(known(counts.completed_review_required))parts.push(counts.completed_review_required+' completed tasks need current review');
  if(!parts.length)return 'Counts unavailable from the owner.';
  return parts.join(' · ')+'.';
}
const labelState=workStandingLabel;
const workGroup=row=>row.lifecycle?.completed===true&&row.current_acceptance?.review_required===true?'review':row.lifecycle?.closed===true?'history':row.lifecycle?.closed===false?'pending':'unknown';
const groupNames={pending:'Unfinished tasks',review:'Completed — evidence needs rechecking',history:'Completed and other closed records',unknown:'Lifecycle not reported'};
// A selected detail already carries bounded, typed relationship rows. Join only
// that admitted observation to its same-cut graph page; never fetch a name or
// promote an unavailable row into a readable node.
export function selectedWorkNeighbourhood(value,{detail,project,selected}={}){
 if(value?.project!==project||value.view!=='graph'||!Array.isArray(value.nodes)||!Array.isArray(value.edges))throw Error('The Work owner returned different neighbourhood coordinates.');
 if(!detail)return value;
 const cut=detail.read_cut?.revision;if(detail.project!==project||detail.view!=='detail'||detail.task?.id!==selected||typeof cut!=='string'||!cut||value.read_cut?.revision!==cut)throw Error('Task relationships changed since this task was inspected. Reinspect the task before opening its related tasks; no observations were mixed.');
 const metadata=row=>Object.fromEntries(['id','title','title_complete','task_kind','status','recorded_status','lifecycle','readiness','current_acceptance','activity','standing','qualified_id','read_handle','available'].filter(key=>Object.hasOwn(row,key)).map(key=>[key,structuredClone(row[key])]));
 const exactRead=row=>{const read=row.read_handle,payload=read?.payload;let path;try{path=operatorHTTP(read);}catch{return false;}const q=new URL(path,'http://local').searchParams;return (!read.project||read.project===project)&&read.operation==='project'&&payload?.namespace===project&&payload.view==='detail'&&payload.id===row.id&&Object.keys(payload).every(key=>['namespace','view','id'].includes(key))&&new URL(path,'http://local').pathname==='/work/state'&&[...q.keys()].every(key=>['project','view','id'].includes(key)&&q.getAll(key).length===1)&&q.get('project')===project&&q.get('view')==='detail'&&q.get('id')===row.id;};
 const nodes=new Map(value.nodes.map(row=>[row.id,{...row}])),boundaries=new Map((value.boundaries||[]).map(row=>[row.id,{...row}])),edges=new Map(value.edges.map(row=>[JSON.stringify([row.kind,row.source,row.target]),{...row}]));
 const admit=row=>{if(!row||typeof row.id!=='string'||!row.id||row.qualified_id!==undefined&&row.qualified_id!==project+'::'+row.id)throw Error('The task relationship row names another namespace.');if(row.available===false){if(!nodes.has(row.id))boundaries.set(row.id,{...metadata(row),available:false});return;}if(!exactRead(row))throw Error('The task relationship has no matching owner-issued detail read.');nodes.set(row.id,{...nodes.get(row.id),...metadata(row),projection_source:'selected-task-detail'});boundaries.delete(row.id);};
 admit(detail.task);let known=0;const relations=[];
 for(const [field,kind,incoming]of [['requires','requires',false],['dependants','requires',true],['children','contains',false]]){const collection=detail[field];if(!collection)continue;if(!Array.isArray(collection.items))throw Error('The owner did not supply a relationship page.');relations.push({kind:field,returned:collection.items.length,total:collection.total??null,more:!!collection.next_read});for(const row of collection.items){admit(row);known++;const edge={kind,source:incoming?row.id:selected,target:incoming?selected:row.id};const key=JSON.stringify([edge.kind,edge.source,edge.target]);if(!edges.has(key))edges.set(key,edge);}}
 return {...value,nodes:[...nodes.values()],edges:[...edges.values()],boundaries:[...boundaries.values()].filter(row=>!nodes.has(row.id)),detail_relationships:{known_rows:known,pages:relations},qualification:'Shows this graph page and the task relationships already inspected above. Other graph and relationship pages are not loaded automatically.'};
}
// The Work neighbourhood: one owner graph page (contains/requires/targets-logical-node),
// painted as a typed topology and continued under the same cut. It never chooses the first
// Work, changes lifecycle or promotes a logical edge; boundary ids read through their owner
// handle only.
export function renderWorkNeighbourhood(map,value,{project,request,onSelect,onRead,isCurrent=()=>true,parentWorkId=null,selected=null,listOnly=false,detail=null}={}){
 const validate=page=>{if(page.project!==project||page.view!=='graph'||!Array.isArray(page.nodes)||!Array.isArray(page.edges))throw Error('The Work owner returned different neighbourhood coordinates.');};validate(value);
 const button=(label,run)=>{const node=el('button',label,'act act-read');node.type='button';node.onclick=async()=>{try{await run();}catch(error){if(isCurrent()){const note=el('p',error.message,'error');note.setAttribute('role','alert');map.append(note);note.tabIndex=-1;note.focus?.();note.scrollIntoView?.({block:'nearest'});}}};return node;};
 const cut=value.read_cut?.revision,projection=selectedWorkNeighbourhood(value,{detail,project,selected}),boundaries=new Map(),shown=new Set(projection.nodes.map(row=>row.id)),edgeKey=row=>JSON.stringify([row.kind,row.source,row.target]),seenEdges=new Set(projection.edges.map(edgeKey));
 // a Work id outside the page reads through the owner handle it published, else through the
 // owner's own detail read of that exact id (which refuses an unknown id itself)
 const expand=boundary=>boundary?.read_handle?onRead(boundary.read_handle,'Read related work outside this page: '+boundary.id):onSelect(boundary.id);
 const chip=node=>taskStateChips(node)[0];
 if(projection.qualification)map.append(el('p',projection.qualification,'muted'));
 const view=mountTopology(map,{title:'Related tasks',legend:'Contains is membership. Requires gates work. Targets is a logical relationship, not an execution prerequisite. The owner supplies every edge.',
   nodes:projection.nodes,edges:projection.edges,boundaries:projection.boundaries||[],selected,listOnly,chip,onSelect:(id,row)=>row?.projection_source==='selected-task-detail'&&row.read_handle?onRead(row.read_handle,'Read related task: '+(row.title||row.id)):onSelect(id),onExpand:expand,ariaLabel:'Task relationships'});
 map.querySelector?.('.topology')?.setAttribute('data-control','work:neighbourhood');
 for(const row of projection.boundaries||[])boundaries.set(row.id,row);
 const diagnostics=el('div');map.append(diagnostics);
 const paintDiagnostics=page=>{for(const row of page.diagnostics||[])diagnostics.append(el('p',row.message||row.reason||row.issue||JSON.stringify(row),'error'));};paintDiagnostics(value);
 let page=value;const more=()=>{if(!page.pagination?.next_read)return;const control=button('More related tasks',async()=>{const path=operatorHTTP(page.pagination.next_read),route=ownerHumanTarget(path),params=new URL(path,'http://local').searchParams;if(route?.kind!=='work'||route.view!=='graph'||route.project!==project||(route.parentWorkId||null)!==parentWorkId||cut&&params.get('as_of')!==cut)throw Error('The neighbourhood continuation changed its selected namespace or cut.');const next=await request(path);if(!isCurrent()||!map.isConnected)return;validate(next);if(cut&&next.read_cut?.revision!==cut)throw Error('The neighbourhood cut changed. Reinspect the selected Work.');const joined=selectedWorkNeighbourhood(next,{detail,project,selected}),focused=globalThis.document?.activeElement===control;control.remove();for(const row of joined.boundaries||[])boundaries.set(row.id,row);for(const row of joined.nodes)shown.add(row.id);const freshEdges=joined.edges.filter(row=>{const key=edgeKey(row);if(seenEdges.has(key))return false;seenEdges.add(key);return true;});view.update({nodes:joined.nodes,edges:freshEdges,boundaries:[...boundaries.values()].filter(row=>!shown.has(row.id))});paintDiagnostics(next);page=next;const replacement=more();
   // keyboard continuity: the next page's control, else the map's own region keeps focus
   if(focused)(replacement||view).focus?.();});map.append(control);return control;};more();
 return view;
}
export async function mountOperatorWork(host,{project,summary,request,initialWork=null,initialDetail=null,detailOnly=false,catalogue=true,memory={},onSelect=()=>{},onSelectionDelivered=null,onRequest=null,onDirty=()=>{},onConversation=null,onTurn=null,onHistory=()=>{},onPrepare=()=>{},onUseForMessage=null,onUsePrepared=null,onArtifact=null,onInspectOwner=null,onResultPdf=null,settingsText=()=>'',readOnly=false,navigation=false,openProposal=null,page=false}){
  // openProposal (closure contract 2026-11-02): the shell's canonical project Review controller open. Supplied, the Work
  // Review responses decide through it; absent (nested, read-only or unbound callers), they inspect and say so.
  if(detailOnly&&!readOnly)throw Error('A detail-only Work peek is read-only.');
  presentationStyles();
  host.className=[host.className,'operator-work-space'].filter(Boolean).join(' ');
  if(detailOnly)host.className+=' operator-detail-only';
  let inspection=null;
  // the controller's lifetime (selected-lifetime.mjs): currentness is this controller's identity and paint generation,
  // not DOM attachment, so a valid first preparation into a detached fragment is not dropped; destroy() disposes it
  const life=createLifetime();
  let catalogGeneration=0,nested=[],detail=null,selected=initialWork||memory.selected||null;
  const groups=new Map();
  // Current owner rows by id, from the catalogue and the selected detail's relations; the
  // blocker card names a prerequisite by its current title from these reads, never a guess.
  const rows=new Map();const remember=row=>{if(row?.id)rows.set(row.id,row);};
  const drafts=new Map(Object.entries(memory.drafts||{})),current=()=>!life.disposed;
  // what the owner recorded after a containing-work save, said on the redrawn card (wave 11, census R10): task id -> time;
  // kept across the redraws a save causes, until he edits the field again
  const containmentSaved=new Map();
  // THE WORK PORT (P1): the sole owner of the title/purpose draft, its original issued guard, attempts and owner
  // results for this project's Work. Restore: memory.port (the port's own lossless qualified capture, attempts and
  // unresolved uncertainty included) wins; the legacy {fields:{title,goal,parent_work_id},editBasis} envelope is
  // still read for anything that capture lacks. Containing work keeps its OWN draft and basis: an existing
  // containment entry is never replaced by the title/purpose basis; only a legacy-only parent_work_id field takes it.
  const captured=memory.port?.schema===WORK_PORT_CAPTURE?structuredClone(memory.port):{schema:WORK_PORT_CAPTURE,next_attempt:0,drafts:[],attempts:[]};
  const capturedIds=new Set(captured.drafts.filter(item=>item.project===project).map(item=>item.id));
  for(const [id,held]of drafts){
    if(!held?.fields||!held.editBasis)continue;
    const fields=Object.fromEntries(['title','goal'].filter(name=>typeof held.fields[name]==='string').map(name=>[name,held.fields[name]]));
    if(Object.keys(fields).length&&!capturedIds.has(id))captured.drafts.push({project,id,fields,basis:{payload:held.editBasis.payload,http:held.editBasis.http,operation:'task'}});
    const rest={...held};delete rest.fields;delete rest.editBasis;
    if(!rest.containment&&held.fields.parent_work_id!=null)rest.containment={value:held.fields.parent_work_id,basis:held.editBasis};
    if(rest.containment||rest.evidence!=null||rest.review)drafts.set(id,{...rest,dirty:true});else drafts.delete(id);
  }
  const port=createWorkPort({request,project,initial:captured});
  // THE ATTEMPT PRESENTER (P1-R2a): one controller-owned port subscription paints the selected Work's attempt as the
  // port holds it - pending, recorded with its postimage, refused, uncertain (restored or not) and any later read-only
  // observation - into the current editor's result line, on mount, after restore and on every later delivery. The
  // target is identity, not attachment: the controller's current line (replaced when an editor is built, cleared by
  // destroy) for the selected qualified Work. A line still being prepared in a detached fragment is painted too, so it
  // carries the attempt when attached. It decides nothing and is unsubscribed by destroy.
  let attemptLine=null;
  function presentAttempt(snap=port.snapshot()){
    if(!attemptLine)return;
    const own=snap.selection?.project===project&&snap.selection?.id===attemptLine.id?snap:null,attempt=own?.attempt,node=attemptLine.node;
    node.dataset.attempt=attempt?.status||'';
    if(!attempt){node.textContent='';node.className='work-status work-attempt';return;}
    const lines=['Attempt '+attempt.id+' ('+attempt.at+'): '+attempt.status+'. '+(attempt.effect||''),
      'Written against work revision '+(attempt.basis?.payload?.expected_work_revision||'not reported')+'.'];
    if(attempt.status==='refused')lines.push('Owner refusal: '+[attempt.refusal?.code,attempt.error].filter(Boolean).join(' ')+'. Your draft and original work guard are retained.');
    if(attempt.postimage)lines.push('Observed after saving: '+(attempt.postimage.fields.title??'title not returned')+'.');
    if(attempt.observed)lines.push(attempt.observed.matches_attempt?'A later owner read ('+attempt.observed.at+') shows the fields you attempted; that is an observation, not a receipt.'
      :'A later owner read ('+attempt.observed.at+') does not show the fields you attempted.');
    if(attempt.status==='recorded'&&own.draft)lines.push('Your newer draft is retained; reinspect the saved work before applying it.');
    node.textContent=lines.join(' ');node.className='work-status work-attempt'+(attempt.status==='refused'||attempt.status==='uncertain'?' error':'');
  }
  const unsubscribeAttempts=port.subscribe(snap=>presentAttempt(snap));
  let navigator=null,listHost=null,activityLine=null;const formHooks=new Map();
  // THE TASKS PAGE (frontend redesign wave 5; page:true from the project Tasks view only): the title with the owner's
  // 'N tasks · N task groups' line and Add task at its right; the navigator's filters and the owner's count sentence; the
  // list always on the page (no chooser disclosure); the selected task opened beside the list with Close at its top right.
  // Whether there is room beside the list is decided by the page's own width (workspace.css, page: Tasks).
  const taskPage=!!page&&navigation&&!readOnly&&!detailOnly&&catalogue;
  const pageCounts=taskPage?el('p','','muted task-page-counts'):null,pageSummary=taskPage?el('p',workCountSummary(summary||{}),'muted task-page-summary'):null;
  if(taskPage){const head=el('div','','task-page-head'),titles=el('div','','task-page-titles');titles.append(el('h2','Tasks'),pageCounts);head.append(titles);host.replaceChildren(head);host.classList.add('task-page');}
  else host.replaceChildren(el('h2',readOnly?'Tasks · '+project:'Tasks'));
  if(readOnly)host.append(stateChip({label:'Read-only',tone:'historical'}));const status=el('p','','work-status');status.setAttribute('role','status');const layout=el('div','','operator-work-layout'),catalog=el('section','','operator-work-catalog'),reader=el('section','','operator-work-detail'),catalogueBrowser=el(taskPage?'section':'details','','task-catalogue-browser'),catalogueTitle=el('summary',selected?'Choose another task':'Browse tasks');let chooserIntent=0;catalogueBrowser.open=!selected;catalogueTitle.onclick=()=>{chooserIntent++;};if(!taskPage)catalogueBrowser.append(catalogueTitle);catalogueBrowser.append(catalog);if(taskPage)reader.setAttribute('aria-label','Open task');reader.hidden=!selected;layout.append(...(detailOnly||!catalogue?[reader]:[catalogueBrowser,reader]));host.append(status,layout);listHost=catalog;
  // FOCUS HANDOFF (S2, Root actual: main More and graph Return left focus on BODY). An explicit
  // activation is captured BEFORE its control is disabled or replaced; once the current
  // generation has painted its result, focus moves to that attached result only while the person
  // has not moved focus elsewhere. Initial mount and background observation never take focus.
  const activationOf=origin=>({origin,hadFocus:!!origin&&globalThis.document?.activeElement===origin});
  const mayHandOff=activation=>{
    const doc=globalThis.document;if(!activation||!doc)return false;
    const active=doc.activeElement;
    return !active||active===doc.body||active===activation.origin||active.isConnected===false;
  };
  const handOff=(target,activation)=>{
    if(!target||target.isConnected===false||!mayHandOff(activation))return false;
    target.focus?.({preventScroll:true});target.scrollIntoView?.({block:'nearest'});return true;
  };
  const button=(label,run,cls='',id=null,owner=null)=>{const b=el('button',label,cls);if(id)declareControl(b,id,owner);b.type='button';
    b.onclick=async()=>{
      const activation=activationOf(b);b.disabled=true;let failed=false;
      try{await run(activation);}
      catch(error){failed=true;if(current()){status.textContent=error.message;status.className='work-status error';}}
      finally{b.disabled=false;if(failed&&current()&&activation.hadFocus&&b.isConnected!==false)handOff(b,activation);}
    };return b;};
  const requestSelection=(id,{activation=activationOf(globalThis.document?.activeElement)}={})=>
    onRequest?onRequest(id,{activation}):select(id,null,{activation});
  const dirty=()=>onDirty([...drafts.values()].some(d=>d.dirty)||port.hasUnresolved());
  const clearDraft=(id,keys)=>{const held={...(drafts.get(id)||{})};for(const key of keys)delete held[key];if(held.containment||held.evidence!=null||held.review||held.completionSupport||held.continuity||held.continuityProof){held.dirty=true;drafts.set(id,held);}else drafts.delete(id);dirty();};
  // the review lifecycle section (workspace-work-review.mjs) runs on this controller's own closures
  // the relationships panel (workspace-work-relations.mjs): Needs, Affects and Contains under one controller
  const chipOf=row=>standingChip(row,owned=>({label:labelState(owned),tone:workStandingTone(owned)}));
  const relations=workRelations({project,request,button,remember,rows,chip:chipOf,chips:row=>taskStateChips(row,owned=>({label:labelState(owned),tone:workStandingTone(owned)})),requestSelection:(...args)=>requestSelection(...args),operatorHTTP,current,generation:()=>life.generation});
  const {reviewLifecycle}=workReviewSection({project,request,status,reader,select:(...args)=>select(...args),drafts,dirty,clearDraft,button,readOnly,
    requestSelection:(...args)=>requestSelection(...args),operatorHTTP,current,generation:()=>life.generation,selected:()=>selected,formHooks});
  // Progress and next action: the owner's continuity summary of the selected Work; its sent wire lives in this Work's draft
  const continuity=continuitySection({project,request,drafts,dirty,clearDraft,button,readOnly,operatorHTTP,readLink:(...args)=>readLink(...args),select:(...args)=>select(...args),
    handOff:(...args)=>handOff(...args),current,generation:()=>life.generation,selected:()=>selected});
  function groupRows(kind){
    if(!groups.has(kind)){const section=el('section','','operator-work-group'),list=el('div');section.dataset.workGroup=kind;section.append(el('h4',groupNames[kind]),list);groups.set(kind,list);listHost.append(section);}
    return groups.get(kind);
  }
  function badge(row){const chip=stateChip({label:labelState(row),tone:workStandingTone(row)});chip.className='state-chip work-badge';chip.dataset.workState=labelState(row);return chip;}
  function navigationRow(row){const item=el('article','','operator-work-row'),b=button(title(row),activation=>requestSelection(row.id,{activation}));
    b.dataset.workId=row.id;b.dataset.control='work:item';b.dataset.controlOwner=project+'::'+row.id;b.setAttribute('aria-label','Work · '+title(row));
    item.dataset.selectedWork=String(row.id===selected);item.append(b,...taskStateChips(row,r=>({label:labelState(r),tone:workStandingTone(r)})).map(stateChip));
    if(row.review_evidence_read){const evidence=button('Inspect review evidence',()=>inspectReviewEvidence(row.review_evidence_read,row.id));evidence.dataset.control='review-evidence:read';item.append(evidence);}
    // ACTUAL-C4-PARENT-COPY: the parent's title when its row is already loaded (catalogue or a
    // detail's relations), else its exact id; no read is issued for a label
    if(row.parent_work_id)item.append(el('small','Part of '+(rows.get(row.parent_work_id)?.title||row.parent_work_id),'muted'));return item;}
  function syncCatalog(task){navigator?.mark(selected);for(const b of listHost.querySelectorAll?.('[data-work-id]')||[]){const chosen=b.dataset.workId===selected;b.setAttribute('aria-current',String(chosen));b.parentElement.dataset.selectedWork=String(chosen);if(b.dataset.workId===task?.id){b.textContent=title(task);const old=b.parentElement.querySelector('.work-badge');if(old){old.textContent=labelState(task);old.dataset.workState=labelState(task);old.dataset.tone=workStandingTone(task);}const group=groupRows(workGroup(task));if(b.parentElement.parentElement!==group)group.append(b.parentElement);}}}
  // The catalogue is the owner's LIST projection: page one paints the groups; a
  // continuation page (owner next_read, same cut) appends its rows to the existing groups
  // and moves the More control, so every delivered row stays visible.
  let moreWork=null,catalogCut=null,catalogOffset=0;
  // A handle with offset>0 is a continuation of the painted catalogue; any other handle (or
  // the mount summary) is page one and repaints it, which is also how a refresh after a
  // disposition re-reads the whole first page.
  const offsetOf=handle=>Number(new URL(operatorHTTP(handle),'http://local').searchParams.get('offset')||0);
  const continuationOf=handle=>!!handle&&offsetOf(handle)>0;
  const shownWork=id=>[...(listHost.querySelectorAll?.('[data-work-id]')||[])].some(b=>b.dataset.workId===id);
  async function loadCatalog(handle=null,{activation=null}={}){
    const ticket=++catalogGeneration;const continuation=continuationOf(handle);
    if(continuation&&offsetOf(handle)<=catalogOffset)throw Error('The Work owner continuation did not advance. Reinspect the catalogue.');
    const data=handle?await request(operatorHTTP(handle)):summary;if(!current()||ticket!==catalogGeneration)return;
    if(handle&&(data.project!==project||data.view!=='summary'))throw Error('The Work owner returned a different summary namespace.');
    if(continuation&&catalogCut&&data.read_cut?.revision&&data.read_cut.revision!==catalogCut)throw Error('The Work cut changed while paging. Reinspect the catalogue.');
    const scroll=catalog.scrollTop,added=[];
    if(!continuation&&pageSummary)pageSummary.textContent=workCountSummary(data);
    if(!continuation){groups.clear();catalogCut=data.read_cut?.revision||null;listHost.replaceChildren(el(navigator?'h4':'h3',navigator?'All task records':'Project tasks'),el('p',workCountSummary(data),'muted'));}
    else{moreWork?.remove();moreWork=null;}
    catalogOffset=continuation?offsetOf(handle):0;
    for(const row of data.tasks||[])remember(row);
    // a row already shown (e.g. the retained off-page selected Work) is never painted twice
    for(const kind of ['pending','review','history','unknown']){
      const rows=(data.tasks||[]).filter(row=>workGroup(row)===kind&&!(continuation&&shownWork(row.id)));
      if(rows.length){const list=groupRows(kind);for(const row of rows){const item=navigationRow(row);list.append(item);added.push(item);}}
    }
    const page=data.pagination;
    if(page?.next_read){moreWork=declareControl(button('More work',next=>loadCatalog(page.next_read,{activation:next})),'work:more-work');listHost.append(moreWork);}
    else if(page?.next_offset!=null)listHost.append(el('p','More work exists, but the owner has not supplied its continuation route.','muted'));
    if(!continuation)observers();catalog.scrollTop=scroll;
    if(continuation&&activation){
      // first genuinely new row, else the next More, else an honest attached fallback
      let target=added[0]?.querySelector?.('button')||moreWork;
      if(!target){target=el('p','This owner page added no new Work rows; every row it returned is already shown.','muted');target.tabIndex=-1;listHost.append(target);}
      handOff(target,activation);
    }
  }
  function observers(){
    for(const [view,label,control] of [['namespaces','Existing work namespaces','work:namespaces'],['workflows','Recorded development workflows','work:dev-workflows']]){
      const box=el('details','','operator-observer'),body=el('div');box.append(declareControl(el('summary',label),control),body);let loaded=false;
      box.ontoggle=async()=>{if(!box.open||loaded)return;loaded=true;body.replaceChildren(pendingRead(el('p','Reading existing owner…','muted')));try{
        const value=await request(query('',view));if(!current()||!box.isConnected)return;body.replaceChildren();
        if(view==='workflows')body.append(el('p','Recorded workflow runs (read-only)','muted'));
        for(const row of value.items||value.workflows||[]){const item=el('article','','material-row');item.append(el('p',row.id||row.run_id));
          if(row.registration_gap)item.append(el('p',row.registration_gap,'muted'));
          if(row.status)item.append(el('p','Recorded status: '+row.status));
          if(row.read_handle)item.append(declareControl(readLink(row.read_handle,view==='workflows'?'Read exact recorded workflow':'Read this exact work namespace'),'work:namespace-read',row.id||row.run_id));body.append(item);
        }
        if(!(value.items||value.workflows||[]).length)body.append(el('p','No rows in this bounded owner observation.','muted'));
        if(value.pagination?.next_read||value.next_read)body.append(readLink(value.pagination?.next_read||value.next_read,'Read next owner page'));
        if(value.error||value.reason)body.append(el('p',value.error||value.reason,'muted'));
      }catch(error){if(current()&&box.isConnected){loaded=false;body.replaceChildren(el('p','Owner observation unavailable: '+error.message,'error'));}}};listHost.append(box);
    }
  }
  const blockerBasis=blocker=>JSON.stringify([blocker.kind||'',blocker.relation||'',blocker.subject?.owner||'',blocker.subject?.project||'',blocker.subject?.namespace||'',blocker.subject?.scope??null,blocker.subject?.scope_id||'',blocker.subject?.id||'',blocker.subject?.qualified_id||'',blocker.subject?.path||'',blocker.subject?.repository||'',blocker.consumed_revision||'']);
  async function readSelfBasis(id,basis,activation){
    const expected=life.generation+1;let cancelled=false;
    const gesture=event=>{if(event.target!==activation?.origin)cancelled=true;},focused=event=>{if(event.target!==activation?.origin&&event.target!==document.body)cancelled=true;};
    document.addEventListener('pointerdown',gesture,true);document.addEventListener('keydown',gesture,true);document.addEventListener('focusin',focused,true);
    try{
      // Keep the issued read and the ordinary selection/guard owners. Only its
      // admitted current paint may reveal the same recorded completion basis.
      const accepted=await requestSelection(id,{activation:null});
      if(!accepted||!current()||life.generation!==expected||selected!==id||detail?.project!==project||detail.task?.id!==id||cancelled||!mayHandOff(activation))return;
      const matches=[...reader.querySelectorAll('[data-work-basis]')].filter(node=>node.dataset.workBasis===basis.key);
      if(!matches.length)return;
      for(const node of matches)node.open=true;
      const completion=reader.querySelector('.operator-completion-basis');if(completion)completion.open=true;
      handOff(matches[0].querySelector('summary'),activation);
    }finally{document.removeEventListener('pointerdown',gesture,true);document.removeEventListener('keydown',gesture,true);document.removeEventListener('focusin',focused,true);}
  }
  function readLink(handle,label='Read owner basis',basis=null){
    return button(label,async activation=>{const url=operatorHTTP(handle),q=new URL(url,'http://local');if(q.pathname==='/research/artifact'){
      const ownerProject=q.searchParams.get('project'),path=q.searchParams.get('path'),scope=q.searchParams.get('scope');
      if(!ownerProject||!path||!['project','manuscript'].includes(scope))throw Error('Artifact owner coordinates are incomplete; reinspect the Work evidence handle.');
      if(onArtifact)return onArtifact(path,label,{project:ownerProject,scope,expectedSha256:q.searchParams.get('expected_sha256'),
        artifactId:q.searchParams.get('artifact_id'),artifactOwner:q.searchParams.get('owner')});
      const fallback=el('section');fallback.append(el('p','Embedded artifact inspection is unavailable in this view. Open the exact owner route.','muted'));
      const link=el('a','Open recorded artifact owner');link.href=url;link.target='_blank';link.rel='noopener';fallback.append(link);reader.append(fallback);return;
    }if(q.pathname==='/work/state'&&q.searchParams.get('view')==='detail'&&q.searchParams.get('project')===project&&q.searchParams.get('id')&&ownerHumanTarget(url)){const id=q.searchParams.get('id');return basis?.id===id&&selected===id?readSelfBasis(id,basis,activation):requestSelection(id);}const known=ownerHumanTarget(url);if(known?.kind==='work-continuity')return continuity.readChild(handle,label,activation);if(known)return inspect(handle,label,{workEvidence:true,consumedRevision:handle.consumed_revision});if(isKnownOwnerReadRoute(url)&&!(q.pathname==='/work/state'&&q.searchParams.get('view')==='workflows'))throw Error('The selected owner read has invalid typed coordinates. Reinspect the Work handle.');return readGeneric(handle,label,url,q,activation);});
  }
  // ONE generic owner reading place (Work-view async handling). The read lives in its own stable slot (workPart owner-reading)
  // that a same-selection background update keeps; the opener is released as soon as the row is mounted. Cancel ends only this
  // GET (aborted through the request signal where supported; a late reply or rejection is dropped) and returns focus to the
  // opener only while the row still owns it. A failure is reported once, in place, with Retry issuing the identical read into a
  // fresh row and carrying focus to its Cancel; a settled row keeps its heading as the focus destination. A newer selection, a
  // disposed controller or a detached row makes any later reply silent. Drafts, selection and scroll are never touched.
  function readGeneric(handle,label,url=operatorHTTP(handle),q=new URL(url,'http://local'),activation=null){
      const target=el('section','','operator-owner-reading');target.dataset.workRead='pending';target.dataset.workPart='owner-reading';reader.append(target);
      const workId=selected,abort=typeof AbortController==='function'?new AbortController():null,opener=activation?.origin||null;let cancelled=false;
      const heading=el('h4',label);heading.tabIndex=-1;
      const pending=el('p','','muted work-read-pending');pending.setAttribute('role','status');const cancel=el('button','Cancel this read','act');cancel.type='button';
      cancel.onclick=()=>{cancelled=true;target.dataset.workRead='cancelled';const owned=focusWithin(target);abort?.abort();target.remove?.();if(owned){const back=opener&&opener.isConnected!==false&&!opener.disabled?opener:reader.querySelector?.('.work-focus-return')||reader.querySelector?.('[data-focus-target="selected-work"]');back?.focus?.({preventScroll:true});}};
      pending.append(pendingRead(el('span','Reading the owner… ')),cancel);target.append(heading,pending);
      const live=()=>!cancelled&&current()&&selected===workId&&target.isConnected!==false;
      target.settled=(async()=>{let value;
        try{value=await request(url,undefined,abort?{signal:abort.signal}:undefined);}
        catch(error){if(!live())return;target.dataset.workRead='failed';const owned=focusWithin(target);
          const retry=el('button','Retry this read','act');retry.type='button';retry.onclick=()=>{const had=focusWithin(target);const fresh=readGeneric(handle,label,url,q,activation);target.remove?.();if(had)(fresh.querySelector?.('button')||fresh).focus?.({preventScroll:true});};
          target.replaceChildren(heading,el('p','Owner read failed: '+error.message,'error'),retry);if(owned)retry.focus?.({preventScroll:true});return;}
        if(!live())return;
        try{
        const owned=focusWithin(target);target.dataset.workRead='read';target.replaceChildren(heading);if(owned)heading.focus?.({preventScroll:true});
        const ticket=life.generation;
        if(q.pathname==='/work/state'&&q.searchParams.get('view')==='summary'&&value.project){const controller=await mountOperatorWork(target,{project:value.project,summary:value,request,readOnly:true,onArtifact,initialWork:value.tasks?.find(row=>!row.parent_work_id)?.id||value.tasks?.[0]?.id});if(!live()){controller.destroy();return;}nested.push(controller);return;}if(value.view==='workflows'){target.append(el('p','Recorded status: '+(value.recorded_status||value.status||'not reported')),el('p','Activity: '+(value.activity||'unknown; saved carrier records are not a live execution observation')),el('p','Accepted: '+String(value.accepted??'not reported')));if(value.continuation?.gap)target.append(el('p',value.continuation.gap,'error'));for(const problem of value.current_return_problems||[])target.append(el('p',typeof problem==='string'?problem:JSON.stringify(problem),'error'));}
      if(value.owner_result||typeof value.content==='string'){
        const observation=el('section');target.append(observation);
        renderMaterialObservation(observation,value,{request,isCurrent:live,   // the reading lives with its retained slot and Work selection, not one paint: a same-selection repaint keeps its continuation

          initialHandle:handle,consumedRevision:handle.consumed_revision,workEvidence:true});
      }else target.append(el('pre',JSON.stringify(value,null,2)));
      if(value.read_cut)target.append(el('p','Owner cut: '+(value.read_cut.revision||value.read_cut.ledger_revision||'not reported'),'muted'));
        }catch(error){if(live()){target.dataset.workRead='failed';target.append(el('p','Owner read failed: '+error.message,'error'));}}
      })();return target;
  }
  function dispatch(host,task,allowed){const d=task.dispatch;if(!d)return;const box=el('section','','work-dispatch');box.append(el('h3','Dispatch'),el('p','Execution: '+(d.execution_state||'not observed')+' · Exact accepted reviews: '+(d.review_state||'not observed')));
    const painted=life.generation;
    // B002 additive run fields, consumed exactly as issued and optional; parent_contract/parent_continuation remain
    const synthesis=d.parent_synthesis;
    if(synthesis&&typeof synthesis==='object'){const words=value=>String(value??'not reported').toLowerCase().replaceAll('_',' ').replaceAll('-',' ');
      const part=el('div','','work-dispatch-synthesis');
      part.append(el('p','Parent synthesis “'+(synthesis.title||synthesis.step_id||'original-parent step')+'”: '+words(synthesis.status)+(synthesis.authored?' · authored':' · not authored yet')+(synthesis.consumed?' · consumed':'')+'. It is written in the original parent session; it is not a review or acceptance.'));
      if(synthesis.execution_location&&synthesis.execution_location!=='original-parent')part.append(el('p','The owner places this synthesis outside the original parent ('+words(synthesis.execution_location)+'). Inspect it before relying on it.','error'));
      for(const issue of synthesis.errors||[])part.append(el('p',typeof issue==='string'?issue:(issue?.message||issue?.code||'Owner reported a synthesis error.'),'error'));
      if(synthesis.return_read?.http?.method==='GET')part.append(readLink(synthesis.return_read,'Read the parent synthesis return'));
      if(!readOnly&&synthesis.attach_action?.permitted&&synthesis.attach_action.http?.method==='GET')part.append(readLink(synthesis.attach_action,'Read how to attach the synthesis'));
      else if(synthesis.attach_action&&!synthesis.attach_action.permitted)part.append(el('p',synthesis.attach_action.reason||'Attaching the synthesis is not offered now.','muted'));
      else if(synthesis.attach_action&&!readOnly)part.append(el('p','The owner offers attaching this synthesis as '+(synthesis.attach_action.operation||'an agent action')+'; this view does not send that form. Attach it from the original parent session.','muted'));
      const exact=el('details','','operator-exact');exact.append(el('summary','Synthesis identities'),el('p','Parent session '+(synthesis.parent_session_id||'not recorded')+' · step '+(synthesis.step_id||'not recorded')+' · phase '+(synthesis.continuation_phase||'not recorded')+' · kind '+(synthesis.kind||'not recorded')+(synthesis.attachment?' · attachment '+(synthesis.attachment.id||synthesis.attachment.path||'recorded'):''),'muted'));
      part.append(exact);box.append(part);}
    const observing=d.observation_reads&&typeof d.observation_reads==='object'?d.observation_reads:{};
    for(const [key,label] of [['uses','Read recorded uses'],['river','Read the activity record']]){const handle=observing[key];if(!handle)continue;
      if(handle.http?.method==='GET')box.append(readLink(handle,label));else box.append(el('p',label+' is an agent read only ('+(handle.operation||'owner read')+'); this view has no human route for it.','muted'));}
    // the owner's exact cancel descriptor (dispatch_parent.cancel_action) replaces the older task-status route when issued
    const ownCancel=d.actions?.cancel_dispatch;
    if(ownCancel){
      if(readOnly||task.recorded_status==='cancelled'){}
      else if(!ownCancel.permitted)box.append(el('p','Cancel is not offered now: '+(ownCancel.reason||'the owner gave no reason.'),'muted'));
      else if(ownCancel.http?.method==='POST'&&typeof ownCancel.http.url==='string'){
        box.append(el('p','Cancel dispatched work asks the owner to stop this dispatch’s children. It is a request; inspect child execution for what actually ended.','muted'));
        box.append(button('Cancel dispatched work',async()=>{if(!current()||painted!==life.generation||selected!==task.id)throw Error('The selected Work changed. Reinspect this dispatch before cancelling it.');
          await request(operatorHTTP(ownCancel,{method:'POST'}),ownCancel.http.payload!==undefined?ownCancel.http.payload:{project,...(ownCancel.payload||{})});
          if(current()&&painted===life.generation&&selected===task.id){await select(task.id);status.textContent='Cancellation requested. Inspect child execution for its cleanup standing.';}},'act act-danger'));
      }else box.append(el('p','The owner issued a cancel action without a human route; it is not sent from here.','muted'));
    }
    const cancellation=allowed?.task_status;
    if(!readOnly&&!ownCancel&&!d.parent_continuation?.dispatch_cancel_action?.permitted&&task.recorded_status!=='cancelled'&&cancellation?.permitted&&cancellation.statuses?.includes('cancelled')&&cancellation.operation==='task_status'&&cancellation.payload?.id===task.id&&cancellation.http?.method==='POST'&&cancellation.http.url==='/work/transition'){
      box.append(el('p','Cancel dispatched work stops this dispatch’s children. Parent Stop only ends its observation.','muted'));
      box.append(button('Cancel dispatched work',async()=>{if(!current()||painted!==life.generation||selected!==task.id)throw Error('The selected Work changed. Reinspect this dispatch before cancelling it.');await request(operatorHTTP(cancellation,{method:'POST'}),{project,...cancellation.payload,status:'cancelled',summary:'Author cancelled this exact dispatched work and its children.'});if(current()&&painted===life.generation&&selected===task.id){await select(task.id);status.textContent='Dispatch cancellation requested. Inspect child execution for cleanup standing.';}},'act act-danger'));
    }
    if(d.uncovered_workers?.length)box.append(el('p','Workers without exact accepted review: '+d.uncovered_workers.join(', ')));
    renderDispatchChildren(box,d.children,{project,onTurn:readChildTurn,onConversation:readOnly?null:onConversation,
      onOwner:(read,label)=>inspect({http:read.http},label),settingsText,
      status:(text,error)=>{if(current()){status.textContent=text;status.className='work-status'+(error?' error':'');}}});host.append(box);
  }
  // a mounted form whose consumed basis changed under a background owner update: kept, disabled, explicit adoption
  function staleForm({save,note,form,consumed,current_,adopt,says}){
    if(JSON.stringify(consumed()?.payload)===JSON.stringify(current_?.payload))return false;
    save.disabled=true;form.dataset.stale='true';note.textContent=says;
    if(!form.querySelector?.('[data-adopt-basis]')){const control=button('Use this inspected basis for my draft',()=>{adopt(current_);save.disabled=false;delete form.dataset.stale;
      note.textContent='Draft retained against the work you inspected. Submit explicitly to apply it.';control.remove();});control.dataset.adoptBasis='true';form.append(control);}
    return true;
  }
  function editor(host,data){if(readOnly){host.append(stateChip({label:'Read-only',tone:'historical'}));return;}const task=data.task,allowed=data.allowed_actions||{},saved=drafts.get(task.id);const row=allowed.task;
    const held=port.draftFor(task.id);
    if(row?.permitted||held){const box=el('details','','operator-work-editor');box.append(declareControl(el('summary','Edit authored work'),'work:authored-open'));const form=el('form'),fields={};
      for(const [name,label,value]of [['title','Title',task.title],['goal','Completion condition',task.goal]]){const wrap=el('label',label),input=el(name==='goal'?'textarea':'input');input.name=name;input.value=held?.fields?.[name]??value??'';fields[name]=input;wrap.append(input);form.append(wrap);}
      const save=declareControl(el('button','Save authored work'),'work:save-authored');save.type='submit';const note=el('p','','work-status');form.append(save,note);
      const result=el('p','','work-status work-attempt');result.dataset.control='work:attempt';form.append(result);attemptLine={id:task.id,node:result};presentAttempt();
      // typing is a port edit intent: only changed title/goal travel, the port keeps the original guard
      form.oninput=()=>{const changed={};for(const [name,input]of Object.entries(fields))if(input.value!==(port.draftFor(task.id)?.fields?.[name]??task[name]??''))changed[name]=input.value;
        if(Object.keys(changed).length)port.dispatch({type:'edit',fields:changed,target:{project,id:task.id}}).catch(error=>{note.textContent=error.message;});dirty();};
      // staleness and the comparison are the PORT's: this card paints them and adopts only the displayed basis
      const own=()=>{const snap=port.snapshot();return snap.selection?.project===project&&snap.selection?.id===task.id?snap:null;};
      const shown=el('div','','operator-work-compare');shown.dataset.control='work:compare';shown.dataset.controlOwner=project+'::'+task.id;
      const paintComparison=()=>{const c=own()?.comparison;shown.replaceChildren();if(!c)return;
        shown.append(el('p',c.same_basis?'Your draft was written against the current work.':'The work changed since your draft was written.'),
          el('p','Current title: '+(c.current.fields.title??'not returned')),el('p','Your title: '+(c.draft.fields.title??'(unchanged)')),
          el('p','Current completion condition: '+(c.current.fields.goal??'not returned')),el('p','Your completion condition: '+(c.draft.fields.goal??'(unchanged)')),
          el('p','Current revision: '+(c.current.work_revision??'not returned'),'muted'));
        const adopt=button('Use the displayed current work as my basis',async()=>{const displayed=c.current.basis;
          try{await port.dispatch({type:'adopt-current',basis:displayed});}catch(error){paintComparison();note.textContent=error.message+' Your text and original guard are kept.';return;}
          save.disabled=false;delete form.dataset.stale;shown.replaceChildren();note.textContent='Draft retained against the work you compared. Save explicitly to apply it.';});
        adopt.dataset.adoptBasis='true';shown.append(adopt);};
      const markStale=()=>{save.disabled=true;form.dataset.stale='true';note.textContent='The work guard your authored-work draft consumed changed. Your text and original guard are kept; compare with the current work, then adopt the displayed basis explicitly before saving.';
        if(!form.querySelector?.('[data-compare-basis]')){const control=button('Compare with the current work',async()=>{await port.dispatch({type:'compare'});paintComparison();});control.dataset.compareBasis='true';form.append(control,shown);}
        paintComparison();};
      if(held&&own()?.draft?.stale)markStale();
      formHooks.set('edit',{line:result,stale:()=>{if(!own()?.draft?.stale){paintComparison();return false;}markStale();return true;}});
      form.onsubmit=async event=>{event.preventDefault();if(form.dataset.stale)return;save.disabled=true;form.dataset.submitting='true';form.oninput();const ticket=life.generation;
        try{await port.dispatch({type:'submit'});}catch(error){if(current()&&ticket===life.generation)note.textContent=error.message+' Your draft and original work guard are retained.';save.disabled=false;delete form.dataset.submitting;return;}
        // the attempt's outcome is painted by the attempt presenter; this continuation only navigates after a recorded save
        const attempt=port.attemptFor(task.id),kept=!!port.draftFor(task.id);dirty();
        try{
          if(attempt?.status==='recorded'&&current()&&ticket===life.generation&&selected===task.id){
            if(!kept){await select(task.id);try{await refreshLists();}catch(error){if(current()&&selected===task.id){status.textContent='The change was saved, but the task list could not reload: '+error.message;status.className='work-status error';}return;}}
            status.textContent='Authored work saved.';}
        }finally{save.disabled=!!form.dataset.stale;delete form.dataset.submitting;}};
      box.append(form);host.append(box);
      if(row?.permitted)containment(host,task,row,data.parent);
    }else{host.append(el('p','Editing is unavailable: '+(row?.reason||'the owner has not exposed an edit action.'),'muted'));}
    const completion=allowed.task_status;
    if(completion?.permitted&&completion.statuses?.length){const box=el('details','','operator-work-editor');box.dataset.control='work:disposition';box.append(declareControl(el('summary','Update task status'),'work:disposition-open'));const form=el('form'),standing=el('select'),standingLabel=el('label','Task status');for(const value of completion.statuses){const option=el('option',taskStatusName(value));option.value=value;standing.append(option);}standing.value=saved?.standing??task.recorded_status??task.status??'open';declareControl(standing,'work:status-choice');standingLabel.append(standing);form.append(el('p','Current saved status: '+String(task.recorded_status||task.lifecycle?.status||task.status||'not reported').replaceAll('-',' ').replaceAll('_',' '),'muted'),standingLabel);const input=el('textarea'),label=el('label','Completion evidence files, one path per line');input.value=saved?.evidence??(task.evidence||[]).map(x=>typeof x==='string'?x:x.path||x.id).join('\n');label.append(input);const advanced=el('details');advanced.append(declareControl(el('summary','Advanced: exact evidence paths'),'work:evidence-paths'),label);form.append(advanced);const evidenceChoices=el('div','','task-evidence-choices');form.append(evidenceChoices);const explanation=el('textarea'),explanationLabel=el('label','Reason or completion summary');explanation.value=saved?.summary??task.blocked_reason??task.summary??'';explanationLabel.append(explanation);form.append(explanationLabel);const save=declareControl(el('button','Save task status'),'work:save-status');save.type='submit';const note=el('p','','work-status');const meaning=el('p',taskStatusMeaning(standing.value),'muted');standing.onchange=()=>{meaning.textContent=taskStatusMeaning(standing.value);};form.append(meaning,save,note);let basis=saved?.completionBasis||completion;
      let supportChoice=saved?.completionSupport||null,choiceEpoch=0;
      const choicesRead=completion.evidence_choices_read||task.evidence_choices_read;
      if(choicesRead){const choose=declareControl(button('Choose saved evidence',async activation=>{
        const mine=++choiceEpoch,ticket=life.generation;choose.disabled=true;let cancelled=false;
        const gesture=event=>{if(event.target!==choose)cancelled=true;},focused=event=>{if(event.target!==choose&&event.target!==document.body)cancelled=true;};document.addEventListener('pointerdown',gesture,true);document.addEventListener('keydown',gesture,true);document.addEventListener('focusin',focused,true);
        try{const {mountTaskEvidenceChoices}=await import('./workspace-task-trail.mjs');if(!current()||ticket!==life.generation||mine!==choiceEpoch)return;
          await mountTaskEvidenceChoices(evidenceChoices,{handle:choicesRead,namespace:project,workId:task.id,request,isCurrent:()=>current()&&ticket===life.generation&&mine===choiceEpoch&&selected===task.id,
            selected:()=>input.value.split('\n').filter(Boolean),onSelect:(value,checked)=>{const entries=new Set(input.value.split('\n').filter(Boolean));checked?entries.add(value):entries.delete(value);input.value=[...entries].join('\n');form.oninput();},
            onManifest:reference=>{supportChoice=reference;form.oninput();note.textContent='Support manifest proposed. Its schema, pinned bytes and required items will be checked only when marking Done.';}});
        }catch(error){if(current()&&ticket===life.generation)note.textContent=error.message;}finally{document.removeEventListener('pointerdown',gesture,true);document.removeEventListener('keydown',gesture,true);document.removeEventListener('focusin',focused,true);if(current())choose.disabled=false;if(!cancelled&&activation?.hadFocus&&current()&&ticket===life.generation&&mine===choiceEpoch&&selected===task.id)handOff(choose,activation);}
      }),'work:choose-evidence');form.insertBefore(choose,advanced);}
      const clearManifest=button('Clear proposed manifest choice',()=>{supportChoice=null;form.oninput();note.textContent='Proposed manifest choice cleared. The current saved task record has not changed.';});form.append(clearManifest);clearManifest.hidden=!supportChoice;
      if(supportChoice)note.textContent='A proposed retained-support manifest is kept in this draft.';
      // the owner's refusals (project_work.disposition_policy, the same decision _transition enforces)
      for(const [value,reason] of Object.entries(completion.refused||{}))if(value!=='verified')form.append(el('p','Not available now: '+taskStatusName(value)+' — '+reason,'muted work-refused'));
      formHooks.set('disposition',{stale:next=>!!drafts.get(task.id)?.dirty&&staleForm({save,note,form,consumed:()=>basis,current_:next.task_status,adopt:fresh=>{basis=fresh;drafts.set(task.id,{...drafts.get(task.id),completionBasis:fresh});},
        says:'Task or prerequisite details changed after this status draft. Your evidence text and selected status are kept; explicitly use the current details before saving.'})});
      if(saved?.dirty&&saved.completionBasis&&JSON.stringify(saved.completionBasis.payload)!==JSON.stringify(completion.payload)){note.textContent='The completion draft retains its original work/dependency guards.';form.append(button('Use this inspected completion basis',()=>{basis=completion;drafts.set(task.id,{...drafts.get(task.id),completionBasis:completion});note.textContent='Evidence draft retained against the inspected work/dependency basis. Record completion explicitly.';}));}
      form.oninput=()=>{drafts.set(task.id,{...drafts.get(task.id),evidence:input.value,standing:standing.value,summary:explanation.value,completionBasis:basis,completionSupport:supportChoice,dirty:true});clearManifest.hidden=!supportChoice;dirty();};form.onsubmit=async event=>{event.preventDefault();if(form.dataset.stale)return;save.disabled=true;form.dataset.submitting='true';form.oninput();const submitted=drafts.get(task.id),ticket=life.generation;try{await request(operatorHTTP(basis,{method:'POST'}),{project,...basis.payload,status:submitted.standing,summary:submitted.summary,evidence:submitted.evidence.split('\n').map(x=>x.trim()).filter(Boolean),...(submitted.standing==='done'&&submitted.completionSupport?{completion_support:submitted.completionSupport}:{})});const unchanged=drafts.get(task.id)===submitted;if(unchanged)clearDraft(task.id,submitted.standing==='done'||!submitted.completionSupport?['evidence','standing','summary','completionBasis','completionSupport']:['evidence','standing','summary']);if(current()&&ticket===life.generation&&selected===task.id){if(unchanged){await select(task.id);try{await refreshLists();}catch(error){if(current()&&selected===task.id){status.textContent='The change was saved, but the task list could not reload: '+error.message;status.className='work-status error';}return;}}else note.textContent='The submitted disposition was recorded. Your newer draft is retained; reinspect its current basis before applying it.';status.textContent='Task status saved.';}}catch(error){if(current()&&ticket===life.generation)note.textContent=error.message+' Evidence draft and original guards are retained.';}finally{save.disabled=!!form.dataset.stale;delete form.dataset.submitting;}};box.append(form);host.append(box);
    }
  }
  // CONTAINING WORK: the one authored field outside the port's title/purpose contract, kept on this card's own guarded
  // closure (the same owner action and guard, its own draft, the same stale-basis adoption).
  function containment(host,task,row,parent=null){
    const saved=drafts.get(task.id)?.containment,box=el('details','','operator-work-containment');box.append(declareControl(el('summary','Change containing work'),'work:containment-open'));
    const form=el('form'),wrap=el('label','Containing work'),input=el('input');input.name='parent_work_id';input.value=saved?.value??task.parent_work_id??'';wrap.append(input);
    const save=el('button','Save containing work');save.type='submit';save.dataset.control='work:containment-save';const note=el('p','','work-status');note.setAttribute('role','status');form.append(wrap,save,note);let basis=saved?.basis||row;
    // after a real save the card is redrawn from the owner's detail read: say what that read now records, and the time the
    // owner's save reply recorded (its ts); a reply that states no time shows no time (wave 11b, R8)
    const recorded=containmentSaved.get(task.id);if(recorded){box.open=true;const at=recorded.ts?new Date(recorded.ts):null;note.textContent=(at&&!Number.isNaN(at.getTime())?'Saved at '+at.toLocaleTimeString()+'.':'Saved.')+' This task is now part of '+(task.parent_work_id?(parent?.id===task.parent_work_id?'“'+title(parent)+'”':task.parent_work_id):'no other task')+'.';}
    form.oninput=()=>{containmentSaved.delete(task.id);drafts.set(task.id,{...drafts.get(task.id),containment:{value:input.value,basis},dirty:true});dirty();};
    formHooks.set('containment',{stale:next=>!!drafts.get(task.id)?.containment&&staleForm({save,note,form,consumed:()=>basis,current_:next.task,adopt:fresh=>{basis=fresh;drafts.set(task.id,{...drafts.get(task.id),containment:{value:input.value,basis:fresh},dirty:true});},
      says:'The work guard your containing-work draft consumed changed. Your value and original guard are kept; use the inspected basis explicitly before saving.'})});
    form.onsubmit=async event=>{event.preventDefault();if(form.dataset.stale)return;
      // nothing changed: say so beside Save and send nothing (wave 11, census R10)
      if(input.value.trim()===String(task.parent_work_id??'')){note.textContent='Nothing changed: this task is already part of '+(task.parent_work_id?(parent?.id===task.parent_work_id?'“'+title(parent)+'”':task.parent_work_id):'no other task')+'. Nothing was sent.';return;}
      save.disabled=true;form.dataset.submitting='true';form.oninput();const submitted=drafts.get(task.id),ticket=life.generation;
      try{const reply=await request(operatorHTTP(basis,{method:'POST'}),{project,...basis.payload,parent_work_id:submitted.containment.value});const unchanged=drafts.get(task.id)===submitted;if(unchanged)clearDraft(task.id,['containment']);
        if(current()&&ticket===life.generation&&selected===task.id){if(unchanged){containmentSaved.set(task.id,{ts:typeof reply?.ts==='string'?reply.ts:null});await select(task.id);await refreshLists().catch(()=>{});}else note.textContent='The submitted containing work was saved. Your newer value is retained; reinspect before applying it.';}}
      catch(error){if(current()&&ticket===life.generation)note.textContent=error.message+' Your value and original work guard are retained.';}
      finally{save.disabled=!!form.dataset.stale;delete form.dataset.submitting;}};
    box.append(form);host.append(box);
  }
  async function refreshLists(){if(!catalogue)return;await loadCatalog({http:{method:'GET',url:query(project,'summary')}});await navigator?.refresh();}
  // one observer change hint (workspace-work-observer.mjs): bounded owner rereads of what may have changed; the
  // selected Work is reread without moving focus, replacing a draft or crossing a newer selection
  // A failed reread THROWS, so the observer keeps its prior token and delivers the same hint again (repair1 WI-R3); a
  // hint superseded by the person's own navigation is applied by that navigation and is not a failure.
  async function observed(value){
    if(!current())return;
    await navigator?.refresh();
    if(selected)await backgroundUpdate();
  }
  const focusWithin=node=>{for(let at=globalThis.document?.activeElement;at;at=at.parentElement)if(at===node)return true;return false;};
  const FORM_PARTS={'operator-work-editor':['edit',[]],'operator-work-containment':['containment',['containment']],'work:disposition':['disposition',['evidence','standing','summary']],'work:review':['review',['review']],'work-continuity':['continuity',['continuity','continuityProof']]};
  // the parts a background update must keep mounted: a focused part, a form part with its own dirty draft, an in-flight submit
  function keepPart(node,held){
    const form=FORM_PARTS[node.dataset.workPart];
    return focusWithin(node)||!!node.querySelector?.('[data-submitting="true"]')||(form&&held?.dirty&&form[1].some(key=>held[key]!=null))||
      (form?.[0]==='edit'&&!!port.draftFor(selected))||false;
  }
  // THE BACKGROUND OWNER UPDATE (repair1 WI-R3): read the selected Work's detail; with no dirty draft and no focus inside,
  // repaint it; otherwise replace every read-only part in place (standing, activity, blockers, review status, relations,
  // reference) and keep each focused, dirty or submitting part mounted with its text, target, guard and request id. A kept
  // form whose own consumed basis changed is disabled with explicit adoption; nothing is posted.
  async function backgroundUpdate(isCurrent=()=>true){
    const id=selected,ticket=life.generation;
    const value=await request(query(project,'detail',{id}));
    if(!current()||!isCurrent()||ticket!==life.generation||selected!==id)return;
    if(value.project!==project||value.view!=='detail'||value.task?.id!==id)throw Error('The Work owner did not return this focused detail.');
    // inline owner readings (pending, failed or read) live in their own stable slot: a same-selection background update keeps them
    const held=drafts.get(id),readings=[...reader.children].filter(node=>node.dataset.workPart==='owner-reading'),old=[...reader.children].filter(node=>node.dataset.workPart!=='owner-reading');
    if(!old.some(node=>keepPart(node,held))&&!readings.some(node=>focusWithin(node))){life.advance();detail=value;await onSelect(value.task);if(!current()||selected!==id)return;paint(value);for(const node of readings)reader.append(node);syncCatalog(value.task);
      status.textContent='Work updated from its owner '+new Date().toLocaleTimeString()+'.';status.className='work-status';return;}
    const prior=new Map(formHooks);const fresh=el('div');paint(value,fresh);const next=[...fresh.children];
    if(next.map(node=>node.dataset.workPart).join('|')!==old.map(node=>node.dataset.workPart).join('|')){
      for(const [name,hook] of prior)formHooks.set(name,hook);
      status.textContent='Task details changed. Your draft is kept; reopen the task before saving.';status.className='work-status error';return;}
    const kept=[];
    old.forEach((node,index)=>{
      if(!keepPart(node,held)){node.replaceWith?.(next[index]);return;}
      kept.push(node.dataset.workPart);
      if(node.dataset.workPart==='work-continuity')continuity.keep(node);   // its later outcomes paint into this mounted node
      const recorder=node.querySelector?.('.operator-review-recorder');
      if(node.dataset.workPart==='work:review'&&recorder&&!(focusWithin(node)&&!focusWithin(recorder))){
        // the review status refreshes beside its kept recorder (unless the person is inside the status itself)
        const incoming=next[index];
        for(const child of [...node.children])if(child!==recorder)child.remove();
        for(const child of [...incoming.children])if(!String(child.className||'').includes('operator-review-recorder'))node.insertBefore(child,recorder);
      }
    });
    for(const part of kept){const name=FORM_PARTS[part]?.[0];if(name&&prior.has(name))formHooks.set(name,prior.get(name));}
    if(formHooks.get('edit')?.line)attemptLine={id,node:formHooks.get('edit').line};presentAttempt();
    const stale=kept.map(part=>FORM_PARTS[part]?.[0]).filter(name=>name&&formHooks.get(name)?.stale(value.allowed_actions||{}));
    detail=value;await onSelect(value.task);if(!current()||selected!==id)return;syncCatalog(value.task);
    status.textContent=stale.length?'Task updated. Your draft is kept; review the changed details before saving.':'Task updated. Your draft is unchanged.';
    status.className='work-status'+(stale.length?' error':'');
  }
  // what the mounted reads consumed, for the observer's first (baseline) comparison
  const observeBasis=()=>detail?.observe_basis||navigator?.basis()||null;
  async function readChildTurn(id,options={}){
    if(onTurn)return onTurn(id,options);
    const ticket=life.generation,fresh=()=>current()&&ticket===life.generation;
    const {openSavedTurn}=await import('./workspace-material.mjs');if(!fresh())return;
    return openSavedTurn({project,turnId:id,...options,request,isCurrent:fresh,onConversation:readOnly?null:onConversation,onHistory:readOnly?null:onHistory,
      onOpen:dialog=>{inspection?.close();inspection=dialog;},onOpenArtifact:onArtifact});
  }
  async function inspect(read,label,extra={}){
    const ticket=life.generation;
    // leased to the Work selection that opened it, never to one paint: a same-selection owner repaint keeps the open evidence
    // reading and its continuation; another Work, a cleared selection or disposal ends it (select() closes the open inspection)
    const workId=selected,options={...extra,isCurrent:()=>current()&&selected===workId,onOpen:dialog=>{inspection?.close();inspection=dialog;}};
    if(onInspectOwner)return onInspectOwner(read,label,options);
    const {openArtifact}=await import('./writing-artifact.mjs');
    if(!options.isCurrent())return;
    return openArtifact({ownerRead:read,label,request,...options});
  }
  async function inspectReviewEvidence(handle,workId){
    const ticket=life.generation,{openReviewEvidence}=await import('./workspace-review-evidence.mjs');
    if(!current()||ticket!==life.generation)return;
    return openReviewEvidence({handle,namespace:project,workId,request,isCurrent:()=>current()&&ticket===life.generation,onOpen:dialog=>{inspection=dialog;}});
  }
  // One blocker, in the owner's words: the subject it waits on (owner-supplied title and
  // standing, never a title looked up from an id or parsed out of a message), the relation
  // kind, the owner's id-free sentence, the clearing action first, then the exact message,
  // pins and revisions behind one Exact disclosure.
  const relationLabel={prerequisite:'Waiting on',hold:'Held',containment:'Contained by','completion-proof':'Completion proof'};
  function blockerCard(blocker,task,{alreadyExplained=''}={}){
    const card=el('article','','operator-blocker'),subject=blocker.subject||{};
    // A lead names another Work this one waits on; a blocker about this Work itself (hold,
    // containment, completion proof) is already under this Work's own header.
    const otherWork=subject.owner==='project_work'&&subject.id&&subject.id!==task.id;
    if(otherWork){
      const lead=el('div','','operator-blocker-lead');lead.append(el('span',relationLabel[blocker.relation]||'Blocked by','relation-kind'));
      lead.append(declareControl(button(subject.title||subject.id,()=>requestSelection(subject.id),'act'),'work:blocker-subject',subject.id));
      if(subject.standing)lead.append(badge(subject.standing));
      card.append(lead);
    }
    const sentence=blocker.sentence||blocker.message;if(sentence!==alreadyExplained)card.append(el('p',sentence,'operator-blocker-message'));
    const actions=el('div','','action-row');let primary=null;
    for(const action of blocker.next_actions||[]){
      if(!action.permitted){card.append(el('p',action.purpose||'This action is not currently permitted.','muted'));continue;}
      const label=action.kind==='read-basis'?'See what changed':action.kind==='inspect-prerequisite'?'Open prerequisite':action.payload?.status==='done'?'Review completion update':action.operation==='task_status'?'Review task status update':action.operation==='task'?'Edit task details':action.purpose||'Read recorded details';
      const node=action.http?.method==='GET'?readLink(action,label,action.kind==='read-basis'?{id:task.id,key:blockerBasis(blocker)}:null):readOnly?null:button(label,()=>onPrepare(action,task));if(node&&action.purpose)node.title=action.purpose;
      if(!node)continue;if(!primary){primary=node;node.className+=' primary';node.dataset.control='work:next-step';}else declareControl(node,'work:blocker-action',task.id+'::'+(action.kind||action.operation||action.purpose||'action'));actions.append(node);
    }
    for(const handle of blocker.read_handles||[])if(!(blocker.next_actions||[]).some(action=>action.permitted&&action.http?.method==='GET'&&action.http.url===handle.http?.url))actions.append(declareControl(readLink(handle,'Read recorded details'),'work:blocker-read',handle.http?.url||handle.purpose||'read'));
    if(actions.children.length)card.append(actions);
    const exact=el('details','','operator-exact');exact.dataset.workBasis=blockerBasis(blocker);exact.append(declareControl(el('summary','Exact reason and required conditions'),'work:blocker-exact',task.id));if(sentence===alreadyExplained)exact.append(el('p',sentence));
    if(blocker.clear_when)exact.append(el('p','To clear: '+(typeof blocker.clear_when==='string'?blocker.clear_when:blocker.clear_when.description||'Inspect the owner condition before acting.')));
    if(blocker.current_coverage_ready!=null)exact.append(el('p','Current source coverage ready: '+String(blocker.current_coverage_ready)+'. This does not replace the consumed scope.','muted'));
    if(blocker.historical_diff)exact.append(el('p',blocker.historical_diff,'muted'));
    if(blocker.sentence&&blocker.message&&blocker.sentence!==blocker.message)exact.append(el('p',blocker.message));
    exact.append(el('p',[subject.owner,subject.qualified_id||subject.id||subject.path].filter(Boolean).join(' · ')),el('p','Consumed: '+(blocker.consumed_revision||'not recorded')),el('p','Observed: '+(blocker.observed_revision||subject.revision||'not reported')));
    if(typeof blocker.clear_when==='object')exact.append(el('pre',JSON.stringify(blocker.clear_when,null,2)));
    card.append(exact);
    return card;
  }
  // The neighbourhood map is a deliberate read (one paged graph page per selected Work),
  // never part of the detail read's cost; the list form stands in below 1000 px.
  function neighbourhood(host,task,data){
    const root=data.parent?.id||task.id;let view=null;
    const section=lazySection({label:'Show related tasks',hideLabel:'Hide neighbourhood map',cls:'operator-work-neighbourhood',
      load:async()=>{const ticket=life.generation;const page=await request(query(project,'graph',{parent_work_id:root}));if(!current()||ticket!==life.generation)throw Error('The selected Work changed while reading its neighbourhood.');return page;},
      render:(body,page)=>{view=renderWorkNeighbourhood(body,page,{project,request,selected:task.id,parentWorkId:root,detail:data,isCurrent:()=>current()&&host.isConnected!==false,listOnly:(globalThis.innerWidth||1280)<1000,
        onSelect:id=>requestSelection(id),onRead:(handle,label)=>{const url=operatorHTTP(handle),q=new URL(url,'http://local');if(q.pathname==='/work/state'&&q.searchParams.get('view')==='detail'&&q.searchParams.get('project')===project&&q.searchParams.get('id'))return requestSelection(q.searchParams.get('id'));return inspect(handle,label);}});}});
    section.querySelector?.('.lazy-toggle')?.setAttribute('data-control','work:neighbourhood');
    host.append(section);
  }
  // NOW: who acts on this Work at this read and what Stop would touch. The subject is the owner's current observation: an
  // in-app turn names its exact conversation turn (Stop belongs to that one turn, requested in its conversation); an external
  // actor names its observer and expiry. requested/running/completed/failed/cancelled and "unknown now" are the owner's words.
  function nowSection(host,task){
    const activity=task.activity||{},seen=activity.observations||[],lead=seen.find(item=>item.current)||seen[0]||null;
    const now=el('section','','work-now');now.dataset.workNow='';now.setAttribute('aria-label','Now');now.append(el('h3','Now'));
    if(!lead){now.append(el('p',activity.qualification||'No in-app or attested external execution is observed for this task.','muted'));host.append(now);return;}
    const subject=lead.subject||{},inApp=lead.source==='in-app';
    const actor=inApp?'This app'+(subject.kind&&subject.kind!=='turn'?' · '+subject.kind:'')+(subject.turn_id?' · turn '+subject.turn_id:''):(subject.actor||'External actor')+(subject.session_id?' · '+subject.session_id:'');
    const state=lead.current?String(lead.observed_state||'unknown')+' · observed '+(lead.observed_at||'at an unrecorded time')+(lead.expires_at?' · expires '+lead.expires_at:''):'unknown now · last '+(lead.observed_state||'state')+' observed '+(lead.observed_at||'at an unrecorded time')+(lead.expires_at?', expired '+lead.expires_at:'');
    now.append(el('p',actor,'work-now-actor'),el('p',state,'work-now-state'));if(activity.qualification)now.append(el('p',activity.qualification,'muted'));
    const active=lead.current&&['requested','starting','waiting','running'].includes(lead.observed_state);
    // the exact turn travels with the conversation open: the session owner confirms it as the current turn before offering Stop
    // and never retargets a newer turn in the same conversation from this link
    if(inApp&&active&&subject.turn_id&&subject.session_id){now.append(el('p','Stop applies to turn '+subject.turn_id+' only; it is requested in that conversation once that turn is confirmed as current, and ends no other work.','muted'));
      if(!readOnly&&onConversation)now.append(button('Open the conversation of turn '+subject.turn_id,()=>onConversation(subject.session_id,{project,workId:task.id,sessionId:subject.session_id,turnId:subject.turn_id,observedState:lead.observed_state||null,observedAt:lead.observed_at||null}),'act'));}
    else if(!inApp&&active)now.append(el('p','No Stop from here: this actor is observed externally by '+(lead.observer||'an observer')+'; the observation expires '+(lead.expires_at||'at an unrecorded time')+'.','muted'));
    if(seen.length>1)now.append(el('p',(seen.length-1)+' further observation'+(seen.length===2?'':'s')+' under Activity sources.','muted'));
    host.append(now);
  }
  // NEXT: the owner's permitted actions as usable controls of their kind. A GET is an inspect-only read opened in the generic
  // reading place; task, task_status and work_review open the forms this view already mounts; an action carrying the owner's
  // complete payload is shown as the issued template and is never sent from here. One primary; nothing is promoted from a
  // readiness word, which stays a fact under Status details.
  function resultAction(task){
    const routes=task.feedback_routes?.routes||[],total=task.feedback_routes?.routes_total??routes.length;
    if(!completedTaskChip(task)||!routes.length)return null;
    if(routes.length===1&&total===1&&(!routes[0].read||!routes[0].origin_ref))return null;
    const box=el('div','','work-result'),single=routes.length===1&&total===1;box.dataset.workResult=single?'offered':'ambiguous';
    if(!single){box.append(el('p','This task is complete. '+total+' comment routes are recorded for it, so one result cannot be chosen here; read each under Review responses below.','muted'));return box;}
    const route=routes[0],note=el('p','This task is complete. Its result is the PDF built from the change it applied; it is checked with its owners when you open it.','work-result-note muted');note.setAttribute('role','status');
    const evidence=el('details','','operator-exact work-result-evidence');evidence.append(el('summary','Result evidence and receipts'));evidence.hidden=true;
    const fallback=el('div','','action-row work-result-fallback');fallback.hidden=true;let checking=false;
    const open=button('Open the result',async()=>{if(checking)return;checking=true;open.disabled=true;try{await openResult(task,route,{note,evidence,fallback});}finally{checking=false;open.disabled=false;}},'act primary');
    open.dataset.control='work:result';open.dataset.controlOwner=project+'::'+task.id;box.append(open,note,evidence,fallback);return box;
  }
  // THE RESULT of a completed writing Work, offered once and checked only on the person's click, from existing owner reads:
  // the selected Work's one issued comment route -> its one committed, complete source application of the exact candidate
  // version -> that application's own BUILT job -> the build owner's fresh status of that same job -> the document owner's
  // VERIFIED_BUILD output of that same job and output pin. Stale, foreign, incomplete or ambiguous coordinates are refused in
  // plain words and the existing typed responses reading is offered instead. Completion JSON is never read for this, and the
  // receipts stay under the evidence disclosure.
  async function openResult(task,route,{note,evidence,fallback}){
    const workId=task.id,live=()=>current()&&selected===workId&&note.isConnected!==false,digest=value=>String(value||'').replace(/^sha256:/,'');
    const say=(text,tone='muted')=>{note.textContent=text;note.className='work-result-note '+tone;};
    const refuse=reason=>{const error=Error(reason);error.resultRefusal=true;throw error;};
    say('Checking the recorded result with its owners…');pendingRead(note);fallback.hidden=true;fallback.replaceChildren();
    try{
      const [port,view]=await Promise.all([import('./feedback-route-port.mjs'),import('./manuscript-document-view.mjs')]);if(!live())return;
      const value=await request(port.feedbackHTTP(route.read,{project,paths:['/work/delivery']}));if(!live())return;
      const aggregate=value?.aggregate||value;
      if(aggregate?.schema_version!=='laplace.feedback-route/1'||aggregate.project!==project||aggregate.work?.id!==workId||!port.sameFeedbackValue(aggregate.origin?.origin_ref,route.origin_ref))refuse('The comment owner returned another comment or task, so no result is opened.');
      const applications=[],builds=[];
      for(const edge of aggregate.edges||[]){const revision=edge.revision;if(revision==null)continue;
        const chain=port.feedbackRevisionSummary(revision,{project,turnId:edge.event?.admitted?.turn_id||null});
        for(const row of chain.builds)if(!builds.some(item=>item.url===row.url))builds.push(row);
        for(const proposal of revision.proposals||[]){
          for(const application of proposal.applications||[])applications.push({application,ref:{id:proposal.id??null,version:proposal.version??null}});
          for(const item of proposal.resolved_successors?.items||[])for(const application of item.applications||[])applications.push({application,ref:item.candidate_ref||{}});}}
      if(!applications.length)refuse('No applied change is recorded for the review of this task, so there is no built result to open.');
      if(applications.length>1)refuse(applications.length+' applied changes are recorded for this task, so one result cannot be chosen here.');
      const {application,ref}=applications[0],effect=application.source_effect||{},build=application.build||{},job=build.build_job||{},named=application.candidate_ref;
      // the reached result contract is strict: a complete candidate identity and version on both sides, an explicitly complete
      // application and source effect, a manuscript build and positively current inputs and outputs. Anything missing refuses.
      if(!named||typeof named.id!=='string'||!named.id||typeof named.version!=='string'||!named.version||typeof ref.version!=='string'||!ref.version)refuse('The applied change does not carry a complete candidate identity and version, so its result is not opened.');
      if((ref.id!=null&&named.id!==ref.id)||named.version!==ref.version)refuse('The applied change names another candidate version than the one this review resolved.');
      if(effect.schema_version!=='laplace.source-effect/1'||effect.state!=='COMMITTED'||effect.complete!==true||application.complete!==true||(effect.required||[]).some(item=>item.status!=='COMPLETE'))refuse('The applied change is not a committed, complete source application; inspect it before relying on a result.');
      if(build.state!=='BUILT'||job.schema_version!=='laplace.build-job/1'||job.project!==project||typeof job.id!=='string'||!job.id||job.target_kind!=='manuscript')refuse('No recorded manuscript build shows the applied change yet. Build the document in Figures & output, then open the result again.');
      const rows=builds.filter(item=>item.application===String(application.id||'')&&item.id===job.id);
      if(rows.length!==1||builds.length!==1)refuse('The applied change does not name exactly one build status read, so its result is not opened.');
      const built=await request(rows[0].url);if(!live())return;
      if(!port.feedbackBuildFreshness(built,{project}).fresh||built.state!=='done'||built.build_job?.id!==job.id||built.last_successful_build?.build_job?.id!==job.id)refuse('The build that showed this change is no longer the current build of the source as it is today. Rebuild in Figures & output to read a current PDF.');
      const doc=await request('/authoring/document?'+new URLSearchParams({project}));if(!live())return;
      const now=doc?.current_build||{},identity=doc?.pdf_identity||{},pin=digest(identity.content_revision),outputs=Object.values(built.last_successful_build?.outputs?.files||{}).map(digest);
      if(doc?.project!==project||now.build_job?.id!==job.id||now.fresh!==true||now.state!=='done'||now.inputs_current!==true||now.outputs_current!==true||identity.verification!=='VERIFIED_BUILD'||!/^[0-9a-f]{64}$/.test(pin)||!outputs.includes(pin))
        refuse('The current document output is no longer the verified PDF of the build of this task. Rebuild in Figures & output to read a current PDF.');
      const url=view.documentPdfURL(doc);if(!url)refuse('The document owner issued no PDF read for its current output.');
      evidence.replaceChildren(el('summary','Result evidence and receipts'),el('p','Comment route: '+String(aggregate.route_id||'not reported'),'muted'),
        el('p','Applied change: '+String(application.id)+' · candidate '+String(named?.id||ref.id||'not reported')+' · version '+String(named?.version||ref.version||'not reported')+' · source effect committed and complete','muted'),
        el('p','Build: '+job.id+' · fresh, on the source as it is today','muted'),el('p','PDF: '+String(identity.file||'')+' · '+String(identity.content_revision)+' · '+identity.verification,'muted'),
        el('p','Application, build and PDF are owner facts; none is review or scientific acceptance.','muted'));evidence.hidden=false;
      say('Opened the PDF built from the change this task applied. Reading it is not acceptance.');
      const heading=title(task)+' · result PDF',notice=view.documentPdfNotice(doc)+' · Built from applied change '+String(application.id)+'.';
      if(onResultPdf)return await onResultPdf(url,heading,{notice});
      const {openPdf}=await import('./writing-pdf.mjs');if(!live())return;
      return await openPdf(url,heading,{notice,onOpenArtifact:onArtifact});
    }catch(error){if(!live())return;
      say((error.resultRefusal?error.message:'The result could not be checked: '+error.message)+' The recorded responses stay readable.','error');
      fallback.replaceChildren(button('Read the recorded responses',async()=>{const {openFeedbackResponses}=await import('./feedback-route.mjs');if(live())return openFeedbackResponses({project,workId,origin:route.origin_ref,read:route.read,request,isCurrent:live,openProposal:readOnly?null:openProposal});},'act act-read'));fallback.hidden=false;}
  }
  function nextSection(host,task,data){
    const allowed=data.allowed_actions||{},named=data.action_context?.actions||Object.keys(allowed).map(name=>({name,operation:allowed[name]?.operation||name,permitted:!!allowed[name]?.permitted}));
    const next=el('section','','work-next');next.dataset.workNext='';next.setAttribute('aria-label','Next');next.append(el('h3','Next'));const row=el('div','','action-row');let primary=null;
    const openPart=(selector,focus)=>()=>{if(!current()||selected!==task.id)return;const box=reader.querySelector?.(selector);if(!box)return;if('open' in box)box.open=true;const inner=focus?box.querySelector?.(focus):null;(inner||box.querySelector?.('summary')||box).focus?.({preventScroll:true});box.scrollIntoView?.({block:'nearest'});};
    for(const item of named){const action=allowed[item.name];if(!action?.permitted)continue;const name=String(item.name||'').replaceAll('_',' '),method=action.http?.method||'';let control=null,kind='';
      if(method==='GET'&&action.http?.url){control=declareControl(button(name+' · inspect',activation=>readGeneric(action,name+' · inspect',undefined,undefined,activation),'act act-read'),'work:action-inspect',name);kind='inspect';}
      else if(readOnly){row.append(el('p',name+' · read-only here; act in the full Work tab.','muted'));continue;}
      else if(item.name==='task'){control=declareControl(button('Edit title and completion condition',openPart('.operator-work-editor','input[name="title"]'),'act'),'work:edit-open');kind='form';}
      else if(item.name==='task_status'){control=declareControl(button('Update task status',openPart('[data-control="work:disposition"]','select'),'act'),'work:status-open');kind='form';}
      else if(item.name==='work_review'){control=button('Record a review phase',openPart('[data-control="work:review"]'),'act','work:review-open');kind='form';}
      else if(action.http?.payload||action.payload){const box=el('details','','work-next-template');box.append(declareControl(el('summary',name+' · owner-issued template (not sent from here)'),'work:action-template',name),el('pre',JSON.stringify(action.http?.payload||action.payload,null,2)));row.append(box);continue;}
      else{row.append(el('p',name+': '+(action.requires||'needs a form this view does not mount')+'.','muted'));continue;}
      control.dataset.nextKind=kind;row.append(control);}
    // one primary only for an owner form this view mounts; an inspect-only read is never promoted by its position in owner order
    primary=[...row.children].find(node=>node.dataset?.nextKind==='form')||null;const result=resultAction(task);   // a permitted form is an available action, not an owner recommendation: its place in the list promotes nothing

    // the owner's continuity recommendation, its direct Continue/inspection/template handlers and the truthful result/receipt line
    // stay in the existing Progress and next action part (workspace-work-review.mjs continuitySection); Next hands over to it
    const progress=declareControl(button('Progress and next action',()=>{if(!current()||selected!==task.id)return;const part=reader.querySelector?.('[data-work-part="work-continuity"]');if(!part)return;const first=part.querySelector?.('button, summary, [tabindex]');(first||part).focus?.({preventScroll:true});part.scrollIntoView?.({block:'nearest'});},'act act-read'),'work:progress-open');progress.dataset.nextKind='continuity';row.append(progress);
    if(!row.children.length)next.append(el('p',data.action_context?'No action is permitted at this read.':'The owner issued no action context for this read.','muted'));
    // ONE plain lead above the owner controls: the completed Work's real result, else the step this task waits on, else the
    // form the owner permits, else an honest sentence that no step is issued. The row below keeps every owner control.
    if(result)next.append(result);
    else{const waiting=(data.blockers||[]).flatMap(blocker=>(blocker.next_actions||[]).filter(action=>action.permitted).map(action=>action.purpose||blocker.sentence||blocker.message)).filter(Boolean),lead=el('div','','work-next-lead');lead.dataset.workNextLead=waiting.length?'waiting':primary?'available':'none';
      if(waiting.length){lead.append(el('p','Next step: '+waiting[0]+(waiting.length>1?' ('+(waiting.length-1)+' more under what this task needs.)':'')));
        lead.append(button('Go to this step',()=>{if(!current()||selected!==task.id)return;const step=reader.querySelector?.('.operator-work-blockers [data-control="work:next-step"]')||reader.querySelector?.('.operator-work-blockers h3');if(!step)return;if(!step.dataset?.control)step.tabIndex=-1;step.focus?.({preventScroll:true});step.scrollIntoView?.({block:'center'});},'act','work:next-go'));}
      else if(primary)lead.append(el('p','No next step is issued for this task at this read. The actions below are available to you; none of them is recommended over another.','muted'));
      else lead.append(el('p',completedTaskChip(task)?'No next step is issued: this task is recorded as complete and nothing here is waiting for you.':'No next step is issued for this task at this read. Nothing here is waiting for you; the controls below only inspect or show progress.','muted'));
      next.append(lead);}
    next.append(row);host.append(next);
  }
  // the selected Work's qualified activity in one sentence: the owner's qualification, never a guess from status
  function paintActivity(activity,standing){
    if(!activityLine)return;const facts=(standing?.facts||[]).filter(fact=>/^(observed-|activity-unknown|declared-in-progress|requested)/.test(fact.code)).map(fact=>fact.text);
    activityLine.textContent=activity?.state?activity.qualification+(activity.coverage?.partial?' (in-app coverage partial)':''):(facts.length?facts.join(' · '):activity?.coverage?.partial?'Execution observation is incomplete.':'');
    activityLine.hidden=!activityLine.textContent;
  }
  // THE REFERENCE (repair1 WI-R1): the owner's resolution of this Work in its project. Codes stay in the authored title;
  // the exact qualified identity, location (with any deeper omission and the root to descend from), recorded names and
  // history, and the recorded follow-up origin/children are shown; an unrecorded relation says so.
  function reference(host,data){
    const ref=data.reference;if(!ref)return;const task=data.task;
    const box=el('section','','work-reference');box.append(el('h4','Reference'),el('p',ref.qualified_id,'muted work-qualified-id'));
    const where=el('p','','work-location');const path=ref.location?.path||[];
    if(ref.location?.omitted&&ref.location.root){where.append(declareControl(button(ref.location.root.title||ref.location.root.id,activation=>requestSelection(ref.location.root.id,{activation}),'act'),'work:location-open',ref.location.root.id),
      el('span',' › … '+ref.location.omitted+' more containing Work … › '));
      if(navigator)where.append(declareControl(button('Open the deeper levels',activation=>navigator.show(path[0]?.id||ref.location.root.id,{activation}),'act'),'work:location-deeper'));}
    if(path.length){for(const step of path)where.append(declareControl(button(step.title||step.id,activation=>requestSelection(step.id,{activation}),'act'),'work:location-open',step.id),el('span',' › '));where.append(el('span',task.title||task.id));}
    else where.append(el('span',ref.location?.containment_cycle?'Its containment has a cycle.':'A root Work (no containing Work).'));
    box.append(where);
    const origin=ref.origin||{};
    if(origin.recorded){const line=el('p','','work-origin');line.append(el('span','Follow-up of '),origin.parent?.available===false?el('span',origin.parent.id+' (unavailable)')
      :button(origin.parent.title||origin.parent.id,activation=>requestSelection(origin.parent.id,{activation}),'act'),el('span',' for finding “'+origin.finding+'” ('+origin.closure+').'));box.append(line);
      if(origin.record)box.append(readLink(origin.record,'Inspect the follow-up record'));}
    else box.append(el('p',origin.says||'No recorded follow-up origin.','muted'));
    if(ref.followups?.length){box.append(el('h5','Recorded follow-ups'));box.append(relationList(ref.followups.map(row=>({kind:row.closure,label:(row.child.title||row.child.id)+' · '+row.finding,
      run:row.child.available===false?null:()=>requestSelection(row.child.id),chip:{label:row.joined?(row.standing||'joined'):'join pending',tone:row.joined?'neutral':'attention'}}))));}
    const history=ref.history||{};
    box.append(el('p',(history.specification||0)+' specification records, '+(history.standing||0)+' standing changes, '+(history.review_phases||0)+' review phases'+((history.planning||0)>0?', '+history.planning+' planning records':'')+
      ((history.names||[]).length>1?' · earlier names: '+history.names.slice(0,-1).join(' · '):'')+'.','muted'));
    if(history.read)box.append(lazySection({label:'Show recorded history',hideLabel:'Hide recorded history',cls:'work-history',control:'work:history-read',
      load:async()=>{const ticket=life.generation,value=await request(operatorHTTP(history.read));if(!current()||ticket!==life.generation||selected!==task.id)throw Error('The selected Work changed while reading its history.');
        if(value.project!==project||value.view!=='history'||value.work?.id!==task.id)throw Error('The Work owner returned a different history.');return value;},
      render:(body,value)=>{const list=el('ol','','work-history-list');const add=entries=>{for(const entry of entries)list.append(el('li',[entry.at,entry.record,entry.title,entry.status,entry.phase,entry.verdict,entry.state,
        entry.changed?.length?'changed: '+entry.changed.join(', '):'',entry.child_id?'follow-up '+entry.child_id:''].filter(Boolean).join(' · ')));};add(value.entries||[]);body.append(list);
        let page=value.pagination;const more=()=>{if(!page?.next_read)return;const control=button('More history',async activation=>{const next=await request(operatorHTTP(page.next_read));
          if(next.view!=='history'||next.work?.id!==task.id||next.read_cut?.revision!==value.read_cut?.revision)throw Error('The Work changed between history pages; show the history again.');
          const before=list.children.length;add(next.entries||[]);control.remove();page=next.pagination;more();handOff(list.children[before],activation);},'act');body.append(control);};more();}}));
    host.append(box);
  }
  // what each allowed action consumes, does and how it recovers: the descriptor names the actions; the one carrier
  // (allowed_actions) holds their handles, guards, admitted statuses/refusals, effects and recovery
  function actionContext(host,data){
    const context=data.action_context;if(!context)return;
    const box=el('details','','operator-exact work-action-context');box.append(declareControl(el('summary','Actions and context ('+context.grade+')'),'work:action-context'));
    const relationships=context.relationships||{};
    box.append(el('p',['Needs '+(relationships.needs?.total??0)+(relationships.needs?.open?' ('+relationships.needs.open+' open)':''),'affects '+(relationships.affects?.total??0),'contains '+(relationships.contains?.total??0)].join(' · '),'muted'));
    for(const named of context.actions||[]){const action=data.allowed_actions?.[named.name]||{};box.append(el('h5',named.operation+(named.permitted?'':' · not permitted here')));
      box.append(el('p','Consumes '+((named.consumes||[]).join(', ')||'no guard')+'. Effects: '+((action.effects||[]).join(', ')||'none declared')+'.'));
      for(const [value,reason] of Object.entries(action.refused||{}))box.append(el('p','Refused now: '+value+' — '+reason,'muted'));
      for(const [phase,prep] of Object.entries(action.preparation?.phases||{}))if(prep.refused)box.append(el('p','Phase '+phase+' unavailable: '+prep.refused,'muted'));
      if(action.recovery?.refusal)box.append(el('p',action.recovery.refusal,'muted'));}
    if(context.summary)box.append(el('p','This summary preserves '+context.summary.preserves.join('; ')+'. '+context.summary.descend,'muted'));
    box.append(el('p',context.basis?.scope||'','muted'));host.append(box);
  }
  // the in-harness join (2026-10-20): the development-source facet and the recipient delivery facet are the SAME owner facts
  // the native tools read (project view:detail -> task.development / task.deliveries); shown, never re-derived here
  function developmentAndDelivery(host,task){
    const dev=task.development,del=task.deliveries;if(!dev&&!del)return;
    const box=el('section','','work-development');box.append(el('h3',del?'Reviewers and responses':'Development'));
    const exact=el('details','','operator-exact');exact.append(el('summary','Delivery and development details'));
    // every list is the owner's bounded page (items + total); a further page is the owner's own next_read, named, never fetched here
    const more=(page,what)=>page?.next_read?el('p',what+': '+page.total+' in all; next page '+page.next_read.operation+' '+JSON.stringify(page.next_read.payload),'muted'):null;
    for(const grant of dev?.grants?.items||[])exact.append(el('p',['Grant '+grant.id,grant.state,grant.repository+' @ '+String(grant.base||'').slice(0,12),'paths '+(grant.paths||[]).join(', '),
      'operations '+(grant.operations||[]).join(', '),grant.checks?.length?'checks '+grant.checks.join(', '):'no checks','by '+(grant.grantor||'unknown'),'expires '+(grant.expires_at||'')].join(' · '),'muted'));
    for(const effect of dev?.effects?.items||[]){const line=el('p','Applied '+effect.candidate_id+' · '+effect.state+' · '+(effect.files||[]).map(f=>f[0]+' '+f[1]).join(', '),effect.state==='COMMITTED'?'':'work-review-needed');exact.append(line);if(effect.state!=='COMMITTED')box.append(el('p','A development change needs inspection: '+effect.state+'.','work-review-needed'));}
    for(const check of dev?.checks?.items||[]){exact.append(el('p','Check '+check.name+' · '+check.state+(check.exit_code==null?'':' · exit '+check.exit_code)+(check.wall_ms==null?'':' · '+check.wall_ms+' ms')+(check.truncated?' · output truncated':''),check.state==='COMPLETE'?'':'work-review-needed'));if(check.state!=='COMPLETE')box.append(el('p','Check '+check.name+': '+check.state+'.','work-review-needed'));}
    for(const page of [[dev?.grants,'grants'],[dev?.effects,'effects'],[dev?.checks,'checks']]){const note=more(page[0],page[1]);if(note)exact.append(note);}
    const settings=recipient=>['Role: '+(recipient.role||'not reported'),recipient.kind==='app-owned'?'App-owned reviewer':recipient.kind==='external'?'External reviewer':recipient.kind,recipient.provider,recipient.model,recipient.effort?'Effort: '+recipient.effort:''].filter(Boolean).join(' · ');
    const expiry=value=>{const date=new Date(value);return Number.isNaN(date.getTime())?value:date.toLocaleString();};
    if(del?.recipients?.length)box.append(el('h4','Saved reviewer settings'));
    for(const recipient of del?.recipients||[]){const row=el('article','','work-reviewer');row.append(el('h5',recipient.label||'Unnamed reviewer'),el('p',settings(recipient)),el('p','Recorded approval: '+String(recipient.state||'not reported').toLowerCase()+(recipient.expires_at?' · expires '+expiry(recipient.expires_at):' · expiry not reported'),'muted'));box.append(row);
      exact.append(el('p','Recipient '+recipient.id+' · revision '+recipient.revision+' · '+recipient.kind+(recipient.model?' · '+recipient.provider+':'+recipient.model:'')+' · '+recipient.state+' · '+(recipient.attachment||'')+(recipient.expires_at?' · expires '+recipient.expires_at:''),'muted'));}
    if(del?.recipients_total!=null)box.append(el('p',(del.recipients||[]).length+' of '+del.recipients_total+' saved reviewer settings shown. Effective approval and renewal are in Set up reviews.','muted'));
    if(del?.events?.length)box.append(el('h4','Review requests'));
    for(const event of del?.events||[]){
      const facts=Object.entries(event.facts||{}).map(([k,v])=>k+' '+v).join(' · ');
      const a=event.acceptance||{};
      // the acceptance shown is the Work's CANONICAL obligation status (review facet), with its currentness; a stale or
      // foreign review is said so, never announced as accepted
      const acceptance=a.status?('obligation '+a.status+' · '+(a.currentness||'UNKNOWN')+(a.by_this_delivery?' · by this delivery':' · not by this delivery')+(a.satisfied?' · satisfied':'')):'';
      const derived=[event.running?'running':'',event.result?.available?'result '+event.result.status:'',event.admitted?'recipient ack '+(event.admitted.recipient_ack||'UNKNOWN'):'',acceptance,
        event.continuation_work_id?'continuation '+event.continuation_work_id:'',event.parent_return?.state?'parent return '+event.parent_return.state+(event.parent_return.continuation_turn?' · turn '+event.parent_return.continuation_turn.turn_id:''):''].filter(Boolean).join(' · ');
      const line=el('article','','work-delivery-event'),recipient=event.recipient||{},question=(task.review?.obligations||[]).find(row=>row.id===event.obligation_id);
      line.append(el('h5',recipient.label||'Unnamed reviewer'),el('p',question?.label||'Review question not available on this page.'),el('p',settings(recipient),'muted'));
      const progress=event.result?.available?'Response available.':event.admitted?'Review started; waiting for its response.':['SUBMITTED','UNCONFIRMED','DELIVERING'].includes(event.state)?'Review start is unconfirmed.':event.state==='STALE'?'Review inputs or settings changed.':event.state==='UNSUPPORTED'?'This review setup is unavailable.':event.state==='EXPIRED'?'Time allowed to start this review has expired.':event.state==='CANCELLED'?'Review stopped.':'Waiting for a confirmed review start.';
      line.append(el('p',progress));if(event.running)line.append(el('p','Execution is still reported active.'));
      if(a.status){const decision=a.status==='AWAITING_REVIEW'?'Review decision pending.':a.status==='UNDECLARED'?'No review obligation is declared for this request.':'Review decision: '+String(a.status).toLowerCase().replaceAll('_',' ')+'.';line.append(el('p',decision+(a.status==='UNDECLARED'?'':a.currentness==='CURRENT'?' Current for the inspected inputs.':a.currentness==='STALE'?' Inputs changed; inspect this decision.':' Decision currentness is unknown.')+(a.review_id&&!a.by_this_delivery?' This decision was recorded by another request.':''),a.status&&a.currentness!=='CURRENT'?'work-review-needed':''));}
      if(a.currentness_reason&&a.currentness!=='CURRENT')line.append(el('p',a.currentness_reason,'muted'));
      if(event.reason)line.append(el('p',event.reason,'muted'));
      if(event.turn_read&&event.admitted?.turn_id)line.append(button('Read review turn',()=>readChildTurn(event.admitted?.turn_id,{sessionId:event.admitted?.session_id}),'act act-read'));
      const details=el('details','','operator-exact');details.append(el('summary','Original request and approval'),el('p','Recorded approval for this request'+(recipient.expires_at?' expires '+expiry(recipient.expires_at):'')+'.'),el('pre',JSON.stringify({recipient,delivery:event.id,state:event.state,obligation:event.obligation_id,attempts:event.attempts,max_attempts:event.max_attempts,facts:event.facts},null,2)),el('p',facts+(derived?' · '+derived:'')));
      if(event.recovery)details.append(el('p','Recovery: '+event.recovery.operation+' '+JSON.stringify(event.recovery.payload),'muted'));line.append(details);
      box.append(line);
    }
    if(del?.events_total!=null)box.append(el('p',(del.events||[]).length+' of '+del.events_total+' review requests shown.','muted'));
    const routes=task.feedback_routes?.routes||[];for(const route of routes){if(!route.read||!route.origin_ref)continue;const ticket=life.generation;box.append(button('Review responses',async()=>{const {openFeedbackResponses}=await import('./feedback-route.mjs');if(current()&&ticket===life.generation&&selected===task.id)return openFeedbackResponses({project,workId:task.id,origin:route.origin_ref,read:route.read,request,isCurrent:()=>current()&&ticket===life.generation&&selected===task.id,openProposal:readOnly?null:openProposal});},'act act-read'));}
    if(task.feedback_routes?.routes_total>routes.length)box.append(el('p',routes.length+' of '+task.feedback_routes.routes_total+' comment response routes shown.','muted'));
    if(del?.next_read)box.append(readLink(del.next_read,'Read more review requests'));
    box.append(exact);
    host.append(box);
  }
  // Close at the open task's top right (Tasks page): it clears the selection, as the header's Clear task context does,
  // and the list is shown alone again with the closed task's row focused
  function closeBar(task){const bar=el('div','','task-open-bar'),close=button('Close',async activation=>{const id=task.id;await requestSelection(null,{activation});
      const back=[...(catalog.querySelectorAll?.('[data-work-id]')||[])].find(n=>n.dataset.workId===id&&n.dataset.navRole==='inspect')||catalog.querySelector?.('[data-work-id]');
      if(current()&&!selected&&back)handOff(back,activation);},'task-close');
    close.setAttribute('aria-label','Close task · '+title(task));close.dataset.control='work:close';bar.append(close);return bar;}
  function paint(data,target=reader){const task=data.task;target.replaceChildren();if(target===reader){host.classList.add('task-selected');reader.hidden=false;}
    if(taskPage)target.append(closeBar(task));
    if(data?.view==='detail'&&data.project===project)port.dispatch({type:'observe',value:data}).catch(()=>{});
    remember(task);remember(data.parent);for(const row of data.children?.items||[])remember(row);for(const row of data.dependants?.items||[])remember(row);
    const header=objectHeader({eyebrow:data.parent?'Part of '+title(data.parent):'Selected work',title:title(task),focusTarget:'selected-work'});
    const goalText=data.acceptance?.goal||task.goal||'',paragraph=String(goalText).split(/\r?\n[ \t]*\r?\n/)[0];
    header.append(el('p',paragraph||'No authored task brief recorded.','operator-work-purpose'));
    if(paragraph!==goalText){const brief=el('details','','operator-work-brief');brief.append(el('summary','Full task brief'),el('p',goalText,'operator-work-purpose'));header.append(brief);}
    header.append(...taskStateChips(task,row=>({label:workStandingLabel(row),tone:workStandingTone(row)})).map(stateChip));
    const completionReason=completedTaskChip(task)&&task.current_acceptance?.status!=='CURRENT'?(task.current_acceptance?.reason||task.currentness?.reason||''):'';
    if(completionReason)header.append(el('p',completionReason,'operator-work-currentness'));
    if(completedTaskChip(task)&&task.current_acceptance?.status!=='CURRENT'){const changed=el('details','','operator-completion-basis');changed.append(declareControl(el('summary','Exact completion evidence and changed inputs'),'work:completion-evidence',task.id),el('pre',JSON.stringify(task.currentness||{},null,2)));header.append(changed);}
    if(!readOnly&&data.allowed_actions?.task_status?.permitted&&data.allowed_actions.task_status.statuses?.length)header.append(declareControl(button('Update task status',()=>{if(!current()||selected!==task.id)return;const box=reader.querySelector('[data-control="work:disposition"]');if(box){box.open=true;box.querySelector('select')?.focus();box.scrollIntoView?.({block:'nearest'});}}),'work:status-open'));
    if(task.summary){const first=String(task.summary).split(/\r?\n[ \t]*\r?\n/)[0],outcome=el('section','','operator-work-summary');outcome.append(el('h3','Recorded task outcome'),el('p',first,'operator-work-purpose'));if(first!==task.summary){const rest=el('details');rest.append(el('summary','Full recorded outcome'),el('p',task.summary));outcome.append(rest);}header.append(outcome);}
    header.setAttribute('aria-label','Work · '+title(task));
    header.className+=' operator-work-heading';target.append(header);
    if(task.provenance_read||data.provenance_read){const trail=el('button','What led here');trail.type='button';trail.dataset.control='task:trail';trail.dataset.controlOwner=project+'::'+task.id;let opening=false;trail.onclick=async()=>{if(opening)return;opening=true;const ticket=life.generation;try{const {openTaskTrail}=await import('./workspace-task-trail.mjs');if(current()&&ticket===life.generation)return await openTaskTrail({handle:task.provenance_read||data.provenance_read,namespace:project,workId:task.id,request,onConversation:readOnly?null:onConversation,isCurrent:()=>current()&&ticket===life.generation,rootReturn:{root:reader,coordinate:{control:'task:trail',owner:project+'::'+task.id},isCurrent:()=>current()&&selected===task.id}});}catch(error){if(current())status.textContent=error.message;}finally{opening=false;}};header.append(trail);}
    if(task.review_evidence_read||data.review_evidence_read){const evidence=button('Inspect review evidence',()=>inspectReviewEvidence(task.review_evidence_read||data.review_evidence_read,task.id));evidence.dataset.control='review-evidence:read';header.append(evidence);}
    {const actions=el('div','','task-primary-actions'),buttons=[...header.children].filter(n=>n.tagName==='BUTTON');let primary=null;if(task.current_acceptance?.review_required||data.blockers?.length){primary=button(completedTaskChip(task)?'See what needs rechecking':'See what this task needs',()=>{const heading=reader.querySelector('.operator-work-blockers h3');if(heading){heading.tabIndex=-1;heading.focus({preventScroll:true});heading.scrollIntoView?.({block:'nearest'});}},'','work:needs-open');actions.append(primary);}else primary=buttons.find(n=>completedTaskChip(task)?n.dataset.control==='task:trail':n.textContent==='Update task status')||buttons[0];for(const b of buttons){b.remove();actions.append(b);};if(primary)primary.classList.add('task-primary-action');header.append(actions);}
    activityLine=el('p','','work-activity muted');activityLine.setAttribute('role','status');paintActivity(task.activity,task.standing);target.append(activityLine);
    {const observations=task.activity?.observations||[],sources=el('details','','operator-exact work-activity-sources');sources.hidden=!observations.length;sources.append(el('summary','Activity sources ('+(task.activity?.subjects_total??observations.length)+')'));
      for(const item of observations){const subject=item.subject||{};sources.append(el('p',[item.source==='in-app'?'In-app '+(subject.kind||'execution'):'External '+(subject.actor||'actor')+(subject.session_id?' · '+subject.session_id:''),
        item.observed_state,(item.current?'current':'not current'),'observed '+(item.observed_at||'time not recorded'),item.expires_at?'expires '+item.expires_at:'',item.observer?'by '+item.observer:'',item.authority||''].filter(Boolean).join(' · ')));
        if(item.evidence?.length)sources.append(el('p','Evidence: '+item.evidence.map(e=>e.path).join(', '),'muted'));else if(item.evidence_absent)sources.append(el('p','No evidence: '+item.evidence_absent,'muted'));}
      const coverage=task.activity?.coverage||{};if(coverage.partial)sources.append(el('p','In-app coverage is partial: '+coverage.in_app.omitted+' further live executions were not read.','work-review-needed'));
      if(coverage.in_app?.not_covered)sources.append(el('p','Not observed here: '+coverage.in_app.not_covered+'.','muted'));target.append(sources);}
    nowSection(target,task);nextSection(target,task,data);
    const painted=life.generation,onAttach=readOnly?null:async attachment=>{
      if(!current()||painted!==life.generation||selected!==task.id)throw Error('The selected Work changed. Reinspect the retained synthesis before attaching it.');
      await request(attachment.url,attachment.payload);
      if(current()&&painted===life.generation&&selected===task.id){await select(task.id);status.textContent='Retained synthesis attached through its Work owner. Current acceptance is shown separately.';}
    };
    const onCancel=readOnly?null:async cancellation=>{
      if(!current()||painted!==life.generation||selected!==task.id)throw Error('The selected Work changed. Reinspect this dispatch before cancelling it.');
      await request(cancellation.url,cancellation.payload);
      if(current()&&painted===life.generation&&selected===task.id){await select(task.id);status.textContent='Dispatch cancellation requested. Inspect child execution for cleanup standing.';}
    };
    const onContinuationOwner=(read,label)=>read.kind==='work'&&read.project===project?requestSelection(read.id):inspect({http:read.http},label);
    // Why waiting, or what stands: the one next step comes first.
    const blocked=!!(data.blockers||[]).length;
    const why=el('section','','operator-work-blockers');why.append(el('h3',completedTaskChip(task)?'What changed and what to recheck':blocked?'What this task is waiting for':'Status and evidence'));
    for(const blocker of data.blockers||[])why.append(blockerCard(blocker,task,{alreadyExplained:completionReason}));
    if(!blocked){why.hidden=!task.current_acceptance?.review_required&&task.readiness?.status!=='BLOCKED';if(!why.hidden){const reason=task.current_acceptance?.review_required?task.current_acceptance.reason||'The recorded completion needs current review.':task.readiness.reason||'Current prerequisites are not satisfied.';if(reason!==completionReason)why.append(el('p',reason,'muted'));}}
    target.append(why);
    continuity.render(target,task,data);
    const acceptance=el('details','','operator-acceptance operator-exact');acceptance.append(declareControl(el('summary','Completion basis'),'work:completion-basis'));
    for(const check of data.acceptance?.mechanical||[])acceptance.append(el('p',typeof check==='string'?check:JSON.stringify(check),'muted'));
    if(data.acceptance?.scientific_verification===false)acceptance.append(el('p','These mechanical checks do not establish scientific verification.','muted'));target.append(acceptance);
    reviewLifecycle(target,task,data);
    developmentAndDelivery(target,task);
    relations.render(target,task,data);
    neighbourhood(target,task,data);
    const continuation=task.parent_continuation||task.dispatch?.parent_continuation;
    if(continuation&&!task.preparation)renderParentContinuation(target,continuation,{project,showChildren:!task.dispatch,
      onOwner:onContinuationOwner,onArtifact,onTurn:readChildTurn,onAttach,onCancel,onConversation:readOnly?null:onConversation,status:(text,error)=>{status.textContent=text;status.className='work-status'+(error?' error':'');}});
    if(task.preparation)renderPreparedWork(target,{project,task,preparation:task.preparation,
      execution:task.prepared_execution,action:task.run_action,
      onUse:readOnly?null:onUsePrepared,onArtifact,onConversation:readOnly?null:onConversation,
      onOwner:onContinuationOwner,
      onAttach,
      onCancel,
      onTurn:readChildTurn,status:(text,error)=>{status.textContent=text;status.className='work-status'+(error?' error':'');}});
    dispatch(target,task,data.allowed_actions);
    // legacy completion evidence, distinct from review-phase evidence (which is read under Review lifecycle)
    const evidence=el('section','','operator-work-evidence-list');evidence.append(el('h3','Completion evidence'));
    for(const handle of task.evidence_reads||data.read_handles||[]){
      const item=el('div','','operator-work-evidence'),path=typeof handle.path==='string'?handle.path:'';
      // Name the owner's source before opening it; equal basenames remain distinguishable.
      if(path){const name=path.split(/[\\/]/).pop(),parent=path.slice(0,path.length-name.length).replace(/[\\/]+$/,'');item.append(el('code',name));if(parent)item.append(el('p',parent,'muted'));}
      if(handle.http){const action=declareControl(readLink(handle,handle.purpose||'Read evidence'),'work:evidence-read',path||handle.http?.url||'evidence');if(path)action.setAttribute('aria-label',(handle.purpose||'Read evidence')+': '+path);item.append(action);if(handle.native_capability_gap)item.append(el('p',handle.native_capability_gap,'muted'));}
      else item.append(el('p',(handle.capability_gap||'No human owner read route is available.')+(handle.local_read?' Local owner route: '+(typeof handle.local_read==='string'?handle.local_read:JSON.stringify(handle.local_read)):''),'muted'));
      evidence.append(item);
    }
    if(!(task.evidence_reads||data.read_handles||[]).length)evidence.append(el('p','No completion evidence recorded yet.'+(task.review?.managed?' Review handoff and review evidence is under Review questions.':''),'muted'));target.append(evidence);
    const actions=[];
    if(onUseForMessage&&!readOnly&&!task.prepared_storyboard)actions.push(declareControl(button('Use for next message',()=>onUseForMessage(task),'act act-write'),'work:use-for-message'));
    if(data.parent)actions.push(declareControl(button('Part of '+title(data.parent),()=>requestSelection(data.parent.id),'act'),'work:open-parent',data.parent.id));
    if(navigator&&task.child_count)actions.push(button('Open its contained Work',activation=>navigator.show(task.id,{activation}),'act','work:open-contained',task.id));
    if(!readOnly)actions.push(declareControl(button('View related turns',()=>onHistory({work_id:task.id,label:title(task)}),'act'),'work:related-turns'));
    actions.push(declareControl(button('Reinspect this work',()=>requestSelection(task.id),'act'),'work:reinspect'));
    target.append(actionRow(actions));
    if(task.lifecycle){const facts=el('details','','operator-work-facets operator-exact');facts.append(declareControl(el('summary','Status details'),'work:status-details'),el('h4','Recorded lifecycle'),el('p',task.lifecycle.status||'not reported'),el('h4','Current acceptance'),el('p',task.current_acceptance?.status||'UNKNOWN'),el('p',task.current_acceptance?.reason||'No current acceptance reason reported.','muted'),el('h4','Prerequisite readiness'),el('p',task.readiness?.status||'not reported'),el('p',task.readiness?.reason||'No readiness reason reported.','muted'));facts.append(el('h4','Observed activity'),el('p',task.activity?.qualification||'No in-app or attested external execution observed.'));if(task.current_acceptance?.review_required)facts.append(el('p','Recorded completion is retained. It needs current review; it is not a new pending job.','work-review-needed'));if(task.readiness?.blocked_by?.length)facts.append(el('p','Blocked by: '+task.readiness.blocked_by.join(', ')));facts.append(el('p','Actual runtime execution: '+(task.dispatch?.execution_state||'not reported in this owner observation'),'muted'));if(data.parent)facts.append(el('h4','Part of'),el('code',data.parent.id));facts.append(el('p','Work cut: '+(data.read_cut?.revision||'not reported'),'muted'));target.append(facts);}
    else target.append(el('p','Work cut: '+(data.read_cut?.revision||'not reported'),'muted'));
    reference(target,data);
    actionContext(target,data);
    editor(target,data);
    // every top-level part names itself, so a background owner update can replace read-only parts in place
    for(const node of target.children)node.dataset.workPart=node.dataset.control||String(node.className||node.tag).split(' ')[0];
  }
  async function select(id,observed=null,{isCurrent=()=>true,observation=false,activation=null}={}){
    if(!current()||!isCurrent())return false;
    if(observation&&!observed&&id&&id===selected){
      // an observation of the selected Work is a background owner update: facts refresh, mounted drafts stay
      try{await backgroundUpdate(isCurrent);return true;}
      catch(error){if(current()&&isCurrent()){status.textContent='Work observation unavailable: '+error.message+' Prior selection and drafts are retained.';status.className='work-status error';}return false;}
    }
    const prior=selected,ticket=life.advance(),intent=chooserIntent;   // a click on the chooser heading during this read is the person's newer intent

    if(!observation){inspection?.close();inspection=null;for(const controller of nested)controller.destroy();nested=[];
      for(const row of catalog.querySelectorAll?.('[data-added-work]')||[])delete row.dataset.addedWork;
      for(const tag of catalog.querySelectorAll?.('.work-nav-added')||[])tag.remove();}   // choosing a task ends the 'just added' mark
    const fresh=()=>current()&&ticket===life.generation&&isCurrent();
    if(!id){selected=null;detail=null;host.classList.remove('task-selected');catalogueBrowser.open=true;catalogueTitle.textContent='Browse tasks';reader.hidden=true;await onSelect(null);if(!fresh())return false;reader.replaceChildren(el('p','No next Work selected. Select Work explicitly when ready.','muted'));for(const row of catalog.querySelectorAll?.('[data-work-id]')||[])row.setAttribute('aria-current','false');for(const row of catalog.querySelectorAll?.('.operator-work-row')||[])row.dataset.selectedWork='false';status.textContent=taskPage?'':'Work selection cleared.';return true;}
    pendingRead(status,observation?'Inspecting selected Work owner…':'Reading exact Work and blockers…');status.className='work-status';
    try{
      const value=observed||await request(query(project,'detail',{id}));if(!fresh())return false;
      if(value.project!==project||value.view!=='detail'||value.task?.id!==id)throw Error('The Work owner did not return this focused detail.');
      selected=id;detail=value;await onSelect(value.task);if(!fresh())return false;
      paint(value);if(!observation){if(intent===chooserIntent||!catalogueBrowser.open)catalogueBrowser.open=false;catalogueTitle.textContent='Choose another task';}syncCatalog(value.task);status.textContent=taskPage?'':'Task details loaded.';   // the Tasks page shows the opened task itself
      // when the open task takes the page (phone width, or the conversation panel open) and the list was scrolled, the task
      // starts at the top of the main area with its Close band, not part-way down its title
      // beside the list the open task scrolls on its own: a newly chosen task opens at its top, under the Close band (an owner
      // repaint of the same task keeps where the person was)
      if(taskPage&&!observation&&prior!==id)reader.scrollTop=0;
      if(taskPage&&!observation){const scroller=reader.closest?.('.workspace-main'),top=reader.getBoundingClientRect?.().top,edge=scroller?.getBoundingClientRect?.().top;if(Number.isFinite(top)&&Number.isFinite(edge)&&top<edge-1)reader.scrollIntoView?.({block:'start'});}
      onSelectionDelivered?.({project,id});   // THE one success point: the owner admitted and this live generation painted this exact Work
      status.title='Owner cut: '+(value.read_cut?.revision||'not reported');status.className='work-status';
      // an explicit navigation lands on the newly admitted Work's own heading
      if(activation&&!observation)handOff(reader.querySelector?.('.work-focus-return')||reader.querySelector?.('[data-focus-target="selected-work"]'),activation);
      return true;
    }catch(error){if(fresh()){selected=prior;status.textContent='Work observation unavailable: '+error.message+' Prior selection and drafts are retained.';status.className='work-status error';if(!detail)reader.replaceChildren(el('p',status.textContent,'error'),button('Retry focused work',()=>requestSelection(id)));}return false;}
  }
  if(navigation&&!detailOnly&&catalogue){
    // the navigator is the default catalogue; the flat page-one list is a secondary disclosure of the same owner
    const flat=el('details','','work-flat-catalogue'),body=el('div','','operator-work-flat');flat.append(declareControl(el('summary','All task records and advanced namespace views'),'work:flat-catalogue'),body);
    navigator=mountWorkNavigator(catalog,{project,request,button,requestSelection:(...args)=>requestSelection(...args),handOff,current,selected:()=>selected,
      page:taskPage?{counts:text=>{pageCounts.textContent=text;},summary:pageSummary}:null});
    catalog.append(flat);listHost=body;
  }
  if(!detailOnly&&catalogue)await loadCatalog();if(navigator)await navigator.show(null).catch(()=>{});if(selected)await select(selected,initialDetail);else reader.append(el('p','Select work to inspect its source, blockers and permitted next action.','muted'));
  // THE ADDED TASK (wave 7): show the new task's row in the list (workspace-work-navigator.mjs reveal). When the open task takes
  // the page and the list is not drawn (phone width, or the conversation panel open), the open task is closed first, as its Close does.
  async function reveal(id,path=[]){
    if(!navigator||!taskPage||!current()||!id)return null;
    if(selected&&!catalogueBrowser.getClientRects?.().length){await requestSelection(null);if(!current())return null;}
    return navigator.reveal(id,path);
  }
  return {select,reveal,observed,observeBasis,refreshNavigation:()=>navigator?.refresh(),capture:()=>{const out=Object.fromEntries(drafts),own=port.capture();for(const held of own.drafts.filter(item=>item.project===project)){const id=held.id,legacy=out[id]||{};out[id]={...legacy,fields:{...held.fields,...(legacy.containment?{parent_work_id:legacy.containment.value}:{})},editBasis:held.basis,dirty:true};}return {selected,drafts:out,port:own};},port,get hasDraft(){return [...drafts.values()].some(d=>d.dirty)||port.hasUnresolved();},destroy(){if(life.disposed)return;unsubscribeAttempts();attemptLine=null;port.dispatch({type:'dispose'});inspection?.close();life.dispose();catalogGeneration++;for(const controller of nested)controller.destroy();nested=[];},get detail(){return detail;}};
}
