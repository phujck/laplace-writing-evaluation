// Native workflow canvas/list and inspector. Every control edits the same workflow-port draft;
// only explicit Save/Prepare invokes the owner's action. No provider is started by this module.
import {createWorkflowPort,createWorkflowRunPort,composeWorkflowRequest,composeFailedReviewRequest,readWorkflowConversationAction,workflowConversationURL,workflowReturnURL,workflowRequest,workflowReadURL,workflowSwapBlocker,workflowPatternBlocker,workflowPatternIntent,workflowPatternResult,workflowPatternProbe,WORKFLOW_ENTRY,WORKFLOW_CAPTURE} from './workflow-port.mjs';
import {checkedWorkflowHistoryHandle,workflowHistoryExpectation,checkedWorkflowHistoryPage,savedHistoryExpectation,createSavedWorkflowBody,checkedSavedObjectRead,savedWorkflowWorkspaceURL} from './workspace-workflow-history.mjs';
import {mountWorkflowCapability,mountWorkflowObservation,readWorkflowOperation,issueText,ownerRefusalIssue,workflowPreviewScope,workflowPreviewSteps,findWorkflowOperationOffer,workflowInterventions,workflowConfiguredFlow,workflowContextChoices,workflowHandoffFields,workflowPolicyBounds,workflowPolicyText,workflowPolicyVariant,stopWorkflowRun,mountWorkflowRunStop} from './workspace-workflow-operation.mjs';
import {workflowSettingChoices,workflowSettingLineage,settingOriginWords,WORKFLOW_SETTING_KEYS} from './workflow-setting-choices.mjs';
import {layoutTopology,topologyEdgeGeometry,topologyRanks,CARD} from './workspace-topology.mjs';
import {pendingRead} from './pending-read.mjs';
import {mountWorkflowRiver,workflowRiverWaiting,riverStepSettings,riverRowRunning,riverTime,clock as riverClock} from './workspace-workflow-river.mjs';
import {ownerStateWord,taskStateChips} from './workspace-presentation.mjs';
const el=(tag,text='',cls='')=>{const n=document.createElement(tag);n.textContent=text;n.className=cls;return n;};
// A local id the definition owner accepts (LOCAL_ID: a letter or digit, then up to 79 of [A-Za-z0-9_-]).
const localId=prefix=>prefix+'-'+(globalThis.crypto?.randomUUID?.()||Date.now().toString(36)+Math.random().toString(36).slice(2));
const json=value=>JSON.stringify(value,null,2);
const revision=value=>value?.version||value?.definition_revision||'unavailable';
const textLines=text=>String(text).split('\n').filter(row=>row.trim());
const labelFor=(body,id)=>body.steps.find(row=>row.id===id)?.title||id;
const exactDetails=(label,value,control=null)=>{const d=el('details'),summary=el('summary',label);if(control){summary.dataset.control=control;summary.dataset.controlOwner=label;}d.append(summary,el('pre',json(value)));return d;};
// A control's declared identity (declarations.py CONTROL_DECLARATIONS); `owner` qualifies a repeated one.
const declare=(node,control,owner=null)=>{node.dataset.control=control;if(owner!=null)node.dataset.controlOwner=String(owner);return node;};
const scopeLabel=scope=>scope?.kind==='owned-workspace'?'Workspace workflow':scope?.kind==='project'?'Project workflow':'Scope unavailable';
const savedLabel=owner=>!owner?'Not saved':owner.is_current===true?'Current saved version':owner.is_current===false?'Older saved version':'Saved version';
const ordered=value=>Array.isArray(value)?value.map(ordered):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(key=>[key,ordered(value[key])])):value;
const equal=(a,b)=>JSON.stringify(ordered(a))===JSON.stringify(ordered(b));
// THE TOPOLOGY (wave 9). A workflow reads left to right: a stage's column comes from the arrows that
// pass work forward (control and data), ranked by workspace-topology's cycle-guarded longest path. A
// feedback arrow is a review loop drawn back underneath, never a column. Only the definition's own
// steps and edges are drawn; nothing is inferred.
export function workflowStageLayout(body){
  const steps=Array.isArray(body?.steps)?body.steps:[],edges=Array.isArray(body?.edges)?body.edges:[],known=new Set(steps.map(step=>step.id));
  const forward=edges.filter(edge=>edge.kind!=='feedback'&&edge.from!==edge.to&&known.has(edge.from)&&known.has(edge.to)),loops=edges.filter(edge=>edge.kind==='feedback'&&known.has(edge.from)&&known.has(edge.to));
  const {rank}=topologyRanks(steps.map(step=>({id:step.id})),forward.map(edge=>({source:edge.from,target:edge.to,kind:edge.kind})));
  const byRank=new Map();for(const step of steps){const at=rank.get(step.id)||0;if(!byRank.has(at))byRank.set(at,[]);byRank.get(at).push(step);}
  const columns=[...byRank.keys()].sort((a,b)=>a-b).map(key=>byRank.get(key));
  return {columns,order:columns.flat(),forward,loops};
}
// The order a stacked (narrow) drawing reads in: each step as soon after the step it follows as its arrows allow, so
// a chain stays together (depth-first over the forward arrows, in the definition's order); steps in a cycle follow.
export function workflowReadingOrder(columns,forward){
  const steps=columns.flat(),waiting=new Map(steps.map(step=>[step.id,0])),next=new Map(steps.map(step=>[step.id,[]])),out=[],seen=new Set();
  for(const edge of forward)if(waiting.has(edge.to)&&next.has(edge.from)){waiting.set(edge.to,waiting.get(edge.to)+1);next.get(edge.from).push(edge.to);}
  const stack=steps.filter(step=>!waiting.get(step.id)).reverse(),byId=new Map(steps.map(step=>[step.id,step]));
  while(stack.length){const step=stack.pop();if(seen.has(step.id))continue;seen.add(step.id);out.push(step);for(const id of [...next.get(step.id)].reverse()){waiting.set(id,waiting.get(id)-1);if(!waiting.get(id))stack.push(byId.get(id));}}
  return [...out,...steps.filter(step=>!seen.has(step.id))];
}
// A review loop's bound in words, only from the owner's own policy field (run_policy.max_iterations).
export function workflowLoopWords(body,loop){
  const title=id=>body.steps.find(step=>step.id===id)?.title||id,max=body?.run_policy?.max_iterations;
  return 'Sent back from '+title(loop.from)+' to '+title(loop.to)+(Number.isSafeInteger(max)&&max>0?' · at most '+max+' review round'+(max===1?'':'s'):'');
}
// THE ROUTE MARKS (wave 12): how each kind of arrow is drawn and the words for it, one table for the
// painter (stroke-dasharray on the path) and the legend line under the drawing. Kinds are the owner's
// (workflow_definitions.validate: control, data, feedback).
export const WORKFLOW_EDGE_MARKS=Object.freeze({
  control:Object.freeze({dash:'',legend:'Solid arrow: the result passes forward'}),
  feedback:Object.freeze({dash:'7 5',legend:'Dashed arrow: findings sent back for revision'}),
  data:Object.freeze({dash:'2 5',legend:'Dotted arrow: an intended data input'})});
export const workflowEdgeLegend=()=>Object.values(WORKFLOW_EDGE_MARKS).map(row=>row.legend+'.').join(' ');
// When the next step starts, in the words both of the editor's advance choices use (run_policy.advance).
const ADVANCE_WORDS=Object.freeze({'automatic-review':'Continue to independent review automatically',manual:'Wait for my next-step decision'});
// The run policy in words (P4): only fields the owner's run_policy carries, each advance value in ADVANCE_WORDS (the words
// the advance choices use), and the owner's declared limits for its profile through the one limits formatter
// (workflowPolicyText, workspace-workflow-operation.mjs), which also says who applies changes.
export function workflowPolicyWords(policy,bounds=null){
  if(!policy)return 'This workflow has no review policy, so the owner holds no review rounds, time limit or advance setting for it.';
  const parts=[],variant=bounds?.variants?.find(row=>row.profile===policy.profile)||null;
  if(Number.isSafeInteger(policy.max_iterations))parts.push('Review rounds: at most '+policy.max_iterations);
  if(Number.isSafeInteger(policy.runtime_seconds))parts.push('Time limit: '+policy.runtime_seconds+' seconds per admitted step');
  if(Number.isSafeInteger(policy.deadline_seconds))parts.push('Run deadline: '+policy.deadline_seconds+' seconds');
  if(Number.isSafeInteger(policy.max_admissions))parts.push('Admitted steps: at most '+policy.max_admissions);
  if(policy.advance)parts.push('After a response: '+(ADVANCE_WORDS[policy.advance]||'as the policy’s advance setting says (Technical details)'));
  return parts.join(' · ')+'.'+(variant?' '+workflowPolicyText({variants:[{...variant,profile:'The owner allows'}]}):' Check execution reads who applies changes and the limits the owner allows for this policy.');
}
// The small drawing on a list row: the stages in reading order as labelled nodes with arrows.
export function workflowMiniDrawing(body){
  const {columns,loops}=workflowStageLayout(body),drawing=el('div','','workflow-mini');drawing.setAttribute('role','img');
  drawing.setAttribute('aria-label',columns.length?'Stages: '+columns.map(column=>column.map(step=>step.title||step.id).join(' and ')).join(', then ')+(loops.length?'. '+loops.map(loop=>workflowLoopWords(body,loop)).join('. '):''):'No stages yet');
  if(!columns.length){drawing.append(el('span','No stages yet','workflow-mini-empty'));return drawing;}
  columns.forEach((column,index)=>{if(index)drawing.append(el('span','→','workflow-mini-arrow'));const group=el('span','','workflow-mini-column');for(const step of column)group.append(el('span',step.title||step.id,'workflow-mini-node'));drawing.append(group);});
  for(const loop of loops)drawing.append(el('span','↺ '+workflowLoopWords(body,loop),'workflow-mini-loop'));
  return drawing;
}
// Where one run step stands, as three marks that are never merged: planned (in the consumed saved
// definition), admitted (in this run's prepared step list, with the owner's state word) and observed
// (an attempt whose turn the owner recorded, with its conversation when the owner issues one).
export function workflowRunMarks(fact){
  const observed=fact?.current_attempt?.observed===true;
  return {planned:true,admitted:!!fact,state:fact?.state||null,observed,conversation:observed&&fact.conversation?.project_url?fact.conversation:null};
}
const FINISHED=new Set(['done','verified','cancelled','withdrawn']);
// Runs whose recorded Work status (project_work.STATUSES) is not finished come first; owner order within each group.
export function workflowRunsOrder(items=[]){return [...items.filter(item=>!FINISHED.has(item?.recorded_status)),...items.filter(item=>FINISHED.has(item?.recorded_status))];}
// Two or three plain sentences beside the element they explain (W4); the Guide keeps the long form.
export const WORKFLOW_EXPLAINERS=Object.freeze({
  stage:['What is a step?','A step is one part of the workflow, done by one agent session in the role you give it. Its instructions say what to do, and its arrows say what it passes on. Saving a step does not run it.'],
  role:['What is a role?','The role names the job this step does, such as builder (writes a draft) or adversary (reviews it independently). It is a label for the work and grants no extra permission to read sources or use tools.'],
  handover:['What is a hand-over?','A hand-over is what one step passes to the next: its purpose, the output it should produce and which later steps receive it. Project, system and role context always go with it; the choices here add declared inputs only.'],
  loop:['What is a review loop?','A review loop sends a reviewer’s findings back to the step before it for another round. The workflow’s review policy bounds how many rounds may run. A cycle with no review policy never runs.']});
// The saved reader never dispatches a selection to the authoring port. Its expected
// version comes from the selected owner's issued history row, not the child reply.
export function savedWorkflowExpectation(owner,item){
  const handle=item?.read_handle||item?.read,url=new URL(workflowReadURL(handle),globalThis.location?.href||'http://local/project'),q=url.searchParams;
  const request=Object.fromEntries(q);
  const scope=owner?.scope,knownScope=equal(scope,{kind:'owned-workspace'})||scope?.kind==='project'&&typeof scope.namespace==='string'&&!!scope.namespace&&Object.keys(scope).sort().join(',')==='kind,namespace';
  if(!knownScope||!owner?.scope_id||!owner.definition_id||typeof item?.version!=='string'||!item.version||q.get('definition_id')!==owner.definition_id||q.get('version')!==item.version||[...q.keys()].some(key=>!['definition_id','version','project_lens'].includes(key)||q.getAll(key).length!==1)||handle.request&&!equal(handle.request,request)||handle.native&&(!equal(handle.native.payload?.request,request)||handle.native.operation!=='project'||handle.native.payload?.view!=='workflow-definitions'))throw Error('This saved-version read does not match the selected workflow.');
  return structuredClone({scope_id:owner.scope_id,scope:owner.scope,definition_id:owner.definition_id,version:item.version,handle});
}
export function checkedSavedWorkflow(value,expected){
  if(value?.schema_version!=='laplace.workflow-definition/1'||value.scope_id!==expected.scope_id||!equal(value.scope,expected.scope)||value.definition_id!==expected.definition_id||value.version!==expected.version||value.reference?.owner!=='pipeline.workflow'||value.reference?.kind!=='workflow-definition'||value.reference?.identity?.id!==expected.definition_id||value.reference?.version?.definition_revision!==expected.version||value.definition?.schema_version!=='laplace.workflow-definition/1'||!Array.isArray(value.definition.steps)||!Array.isArray(value.definition.edges))throw Error('The saved reading returned another workflow, version or scope. Its body was not displayed.');
  return structuredClone(value);
}
function stylesheet(){if(document.querySelector('link[data-workflow-editor]'))return;const link=el('link');link.rel='stylesheet';link.href='/shared/workspace-workflow-editor.css';link.setAttribute('data-workflow-editor','');document.head.append(link);}
export async function mountWorkflowEditor(host,{request=workflowRequest,storage=globalThis.sessionStorage,stopRecovery=null,initialReference=null,initialRead=null,initialListingRead=null,initialStep=null,inputChoices=()=>[],manuscriptChoices=null,onInspectRead=null,onOpenSavedObject=null,onCompose=null,helpInDialog=null,onFocus=()=>{},navigate=url=>{globalThis.location.href=url;}}={}){
  stylesheet();host.classList.add('workspace-app');host.classList.add('workflow-editor');
  const status=pendingRead(el('p','Reading workflow definitions…','workflow-status'));status.setAttribute('role','status');host.replaceChildren(el('h1','Workflows'),el('p','Plan a repeatable sequence of research or writing steps. Workflows are optional: you can read sources, write and manage tasks without one.','workflow-introduction'),status);
  let listed;try{listed=await request(initialListingRead?workflowReadURL(initialListingRead):WORKFLOW_ENTRY);if(!listed.scope_id)throw Error('The owner supplied no scope identity.');}catch(error){status.textContent='Workflows unavailable: '+error.message;return {hasDraft:false,destroy(){},leaveGuard(){return false;}};}
  const key='laplace:workflow-drafts:'+listed.scope_id;let initial=null,recoveryError=null;
  try{const saved=storage?.getItem(key);if(saved){initial=JSON.parse(saved);if(initial.schema!==WORKFLOW_CAPTURE||initial.scope_id!==listed.scope_id)throw Error('Saved recovery has an incompatible scope or format.');}}catch(error){initial=null;recoveryError=error.message;}
  const media=globalThis.matchMedia?.('(max-width:850px)');
  const port=createWorkflowPort({request,initial,initialListing:listed}),runPort=createWorkflowRunPort({request,initial:initial?.run});const presentation=initial?.presentation||{};let alive=true,inspectorRegion=null,technicalRegion=null,paintEpoch=0,mode='select',view=presentation.view||'list',stored=true,inspectorTab=presentation.inspectorTab||'step',prepareOpen=false,definitionOpen=false,graphFit=true,userView=!!presentation.view,appOpen=!!presentation.appOpen,appPrepareOpen=!!presentation.appPrepareOpen,safeNavigation=false,composeEpoch=0,editorFocus=presentation.editorFocus||null,runFocus=null,workspaceView=presentation.workspaceView||'design';
  const settingGroups=new Set();
  const shell=el('div','','workflow-shell'),library=el('section','','workflow-library'),detail=el('section','','workflow-detail'),notice=el('p','','workflow-notice');notice.setAttribute('role','alert');shell.append(library,detail);host.append(notice,shell);
  const savedPane=el('section','','workflow-saved-reading');savedPane.hidden=true;savedPane.setAttribute('aria-label','Saved workflow reading');shell.append(savedPane);
  const historyPane=el('section','','workflow-saved-reading workflow-history-reading');historyPane.hidden=true;historyPane.setAttribute('aria-label','Saved workflow history');shell.append(historyPane);
  let savedVisit=null,savedEpoch=0,historyVisit=null,historyEpoch=0,navigationEpoch=0,libraryOpen=false,creationOpen=false,creationScope=null,creationDefinition=null,capabilityUI=null,operationDeclarations=null,roleDeliveryHost=null,observationUIs=[];
  // While a selection given at mount is still being read, the opening list paints but reads nothing.
  let overviewOpen=false,overviewObserver=null,starters={io:'idle'},deferOverviewReads=!!(initialReference?.identity?.id&&initialRead)||!!(initial?.selection&&!initial.selection.id.startsWith('local:'));const overviewReads=new Map();
  if(recoveryError)notice.textContent='Recovery was kept unreadable: '+recoveryError;
  async function act(intent){safeNavigation=false;try{return await port.dispatch(intent);}catch(error){if(alive){notice.textContent=error.message;notice.focus?.();}return null;}}
  // A Runs read error belongs to Runs: leaving that view clears only this read-only notice, never an attempt receipt.
  let runsNoticeText='',creationSource=null;
  let runsVisit=0;
  // The run river outlives repaints of the run view: it is re-attached, never re-mounted, while the same run is open.
  let riverUI=null,runStrip=null;
  function dropRiver(){riverUI?.destroy();riverUI=null;runStrip=null;}
  // A Runs rejection publishes only while the same Runs visit and the same saved subject are still current.
  function runsError(owner){const visit=runsVisit,id=owner?.definition_id,version=owner?.version;return error=>{const now=port.snapshot().read?.value;if(!alive||visit!==runsVisit||workspaceView!=='runs'||now?.definition_id!==id||now?.version!==version)return;notice.textContent=error.message;runsNoticeText=error.message;};}
  // Discard disables its own button. Return focus to the current editor or chooser only if no later intent took it.
  async function discardDraft(){const before=port.snapshot().selection?.id,result=await act({type:'discard'});if(!alive||!result)return result;
    // A fallback to another subject closes only the unadmitted local preparation forms; owner attempts and their wire stay in the port.
    if(result.selection?.id!==before&&(prepareOpen||appPrepareOpen)){prepareOpen=false;appPrepareOpen=false;paint({...port.snapshot(),event:'view'});}
    const now=port.snapshot(),doc=host.ownerDocument,active=doc?.activeElement;if(now.selection?.id!==result.selection?.id||active&&active!==doc.body&&active.isConnected)return result;(now.selection?detail.querySelector('[data-workflow-view="design"]'):library.querySelector('[data-creation-choice]')||library.querySelector('button'))?.focus?.({preventScroll:true});return result;}
  // A verified saved version may seed a NEW local draft through the existing ownership choice; its original identity, version and history stay unchanged.
  const sameSaved=(a,b)=>!!(a&&b&&a.definition_id===b.definition_id&&a.version===b.version&&a.scope_id===b.scope_id&&equal(a.reference,b.reference)&&equal(a.scope,b.scope));
  function adaptable(state){const owner=state.read?.value,ref=owner?.reference,scope=owner?.scope;return !!(owner&&!state.draft&&state.read.io!=='error'&&state.selection&&!state.selection.id.startsWith('local:')&&owner.definition_id===state.selection.id&&owner.scope_id===state.scope_id&&typeof owner.version==='string'&&ref?.identity?.id===owner.definition_id&&ref?.version?.definition_revision===owner.version&&(scope?.kind==='owned-workspace'||scope?.kind==='project'&&typeof scope.namespace==='string'&&!!scope.namespace)&&(owner.read_handle||owner.read)?.http?.method==='GET'&&owner.definition&&state.listing?.creation_choices_read&&state.listing?.actions?.create?.permitted);}
  function adaptButton(state){const owner=state.read.value,node=button('Use as new draft…',()=>{const now=port.snapshot();if(!adaptable(now)||!sameSaved(now.read.value,owner)){notice.textContent='This saved version is no longer the verified selection. Choose it again.';return;}return requestCreation(owner.definition,{definition_id:owner.definition_id,version:owner.version,scope_id:owner.scope_id,reference:structuredClone(owner.reference),scope:structuredClone(owner.scope),title:owner.definition.title||owner.definition_id});},{title:'Copy this saved version into a new local draft. You choose its ownership; Save and preparation stay separate.'});node.dataset.action='adapt';node.dataset.control='workflow:adapt';return node;}
  const button=(label,run,{disabled=false,title=''}={})=>{const b=el('button',label);b.type='button';b.disabled=disabled;b.title=title;b.onclick=run;return b;};
  function remember(detached=port.capture()){try{const capture={...detached,run:runPort.capture(),presentation:{view,inspectorTab,appOpen,appPrepareOpen,editorFocus,workspaceView}};if(port.hasUnresolved()||runPort.snapshot().selection||appOpen||appPrepareOpen){const raw=JSON.stringify(capture);storage?.setItem(key,raw);if(storage?.getItem(key)!==raw)throw Error('Draft storage did not read back.');}else storage?.removeItem(key);stored=true;}catch(error){stored=false;notice.textContent='This tab could not keep recovery: '+error.message+' Keep the page open or export the draft.';}}
  function field(parent,label,value,change,{tag='input',name=label,rows=4}={}){const wrap=el('label',label),input=el(tag);input.value=value??'';input.name=name;input.dataset.field=name;input.setAttribute('aria-label',label);if(tag==='textarea')input.rows=rows;input.oninput=()=>change(input.value);wrap.append(input);parent.append(wrap);return input;}
  function select(parent,label,values,current,change){const wrap=el('label',label),input=el('select');input.setAttribute('aria-label',label);input.dataset.field=label;for(const [value,text]of values){const option=el('option',text);option.value=value;input.append(option);}input.value=current||'';input.onchange=()=>change(input.value);wrap.append(input);parent.append(wrap);return input;}
  function settingChoices(place,state,body,step=null){
    const group=el('fieldset','','workflow-setting-choices'),controls=new Map(),prefix=step?'setting-':'default-',selection=state.selection.id,stepId=step?.id??null;
    group.append(el('legend',step?'Set for this step':'Set for the whole workflow'),el('p',step?'A change here writes this step’s own settings. Inherit removes its value here, so a containing group or the workflow defaults decide.':'A change here writes the workflow defaults, which every step without its own value reads.','workflow-hint workflow-setting-scope'));
    const hint=el('p','','workflow-hint');
    function current(){const fresh=port.snapshot();return alive&&group.isConnected!==false&&fresh.selection?.id===selection&&(!stepId||fresh.step===stepId)?fresh:null;}
    function change(key,value){const fresh=current();if(fresh)return edit(fresh,stepId?{type:'setting',id:stepId,key,value}:{type:'default-setting',key,value},true);}
    for(const key of ['provider','model','effort']){
      const label=key[0].toUpperCase()+key.slice(1),wrap=el('label',label),choice=el('select'),customWrap=el('label','Custom '+key),custom=el('input'),note=el('p','','workflow-hint');
      choice.setAttribute('aria-label',(step?'':'Default ')+label);choice.dataset.field=prefix+key;declare(choice,step?'workflow:setting-step':'workflow:setting-workflow',key);declare(custom,step?'workflow:setting-step':'workflow:setting-workflow',key+'-custom');
      custom.setAttribute('aria-label',(step?'':'Default ')+'custom '+key);custom.dataset.field=prefix+key+'-custom';customWrap.append(custom);
      const control={choice,custom,customWrap,note,mode:null};controls.set(key,control);
      choice.onchange=()=>{if(!current())return;if(choice.value==='custom'){control.mode='custom';customWrap.hidden=false;custom.focus();return;}control.mode=null;change(key,choice.value==='inherit'?'':choice.value.slice(6));};
      custom.oninput=()=>{if(current())change(key,custom.value);};wrap.append(choice);group.append(wrap,customWrap,note);
    }
    group.append(hint);place.append(group);
    const refresh=(fresh,initial=false)=>{
      if(!initial&&group.isConnected===false){settingGroups.delete(refresh);return;}
      const draft=fresh.draft?.definition||fresh.read?.value?.definition;if(!draft)return;
      const local=stepId?draft.steps.find(row=>row.id===stepId)?.assignment?.settings:draft.settings,projection=workflowSettingChoices(draft,stepId,fresh.read?.value?.providers?.providers||fresh.listing?.providers?.providers||[],fresh.read?.value);
      for(const [key,c]of controls){
        const value=local?.[key]??'',options=projection.choices[key],known=options.some(row=>row.value===value),activeCustom=c.mode==='custom'||!!value&&!known;
        const entries=[['inherit',step?'Inherit':'Use role default'],...options.map(row=>['value:'+row.value,row.label===row.value?row.label:row.label+' · '+row.value])];
        if(value&&!known)entries.push(['value:'+value,value+' (not in observed choices)']);entries.push(['custom','Custom…']);
        c.choice.replaceChildren(...entries.map(([value,text])=>{const option=el('option',text);option.value=value;return option;}));c.choice.value=activeCustom?'custom':value?'value:'+value:'inherit';
        if(c.custom.value!==value)c.custom.value=value;c.customWrap.hidden=!activeCustom;
        c.note.textContent=key==='effort'&&projection.model?.supports_effort===false?'This catalogue model does not use reasoning effort.'+(value?' Your authored value is retained.':' Leave it inherited.'):value&&!known?'Current value is not in the observed choices.':'';
      }
      hint.textContent=!projection.known?'Draft inheritance is unavailable; no effective settings are inferred.':projection.values.provider?'Suggestions from '+projection.sources.provider+' · '+projection.values.provider+(projection.values.model?' / '+projection.values.model+' from '+projection.sources.model:'')+'.':'Choose a provider override for model suggestions, or leave it inherited for the role default.';
    };
    refresh.group=group;for(const previous of settingGroups)if(previous.group.isConnected===false)settingGroups.delete(previous);settingGroups.add(refresh);refresh(state,true);return group;
  }
  // WHERE EACH VALUE COMES FROM (wave 12, P2): the selected step's provider, model, effort and input policy, each with
  // the scope its value comes from in the settings owner's words (settingOriginWords over resolve_settings' origins,
  // read with the saved version), or, where this draft changed what decides it, only what the draft declares, marked
  // unchecked. No value is supplied here. The exact origins are one click away (Identity).
  const SETTING_LABELS={provider:'Provider',model:'Model',effort:'Effort',input_policy:'Input policy'},lineageViews=new Set();let identityOpen=false;
  function paintSettingLineage(place,state,step){
    const box=el('section','','workflow-effective workflow-settings-lineage'),selection=state.selection.id;place.append(box);
    const refresh=(fresh,initial=false)=>{
      if(!initial&&box.isConnected===false||fresh.selection?.id!==selection){lineageViews.delete(refresh);return;}
      const body=fresh.draft?.definition||fresh.read?.value?.definition,owner=fresh.read?.value;if(!body)return;
      const line=workflowSettingLineage(body,step.id,owner?.definition?owner:null),rows=WORKFLOW_SETTING_KEYS.map(key=>[key,line.rows[key]]),checked=rows.filter(([,row])=>row.checked==='owner').length;box.replaceChildren();
      for(const [key,row]of rows){const p=el('p','','workflow-setting-row');p.dataset.settingKey=key;p.dataset.settingChecked=row.checked;
        const value=row.checked==='owner'?String(row.value??'Not set'):row.declared?String(row.value):'Not declared here',origin=row.checked==='owner'?settingOriginWords(row.fact,body,step.id):row.declared?settingOriginWords({origin:row.origin},body,step.id)+' · unchecked':'Unchecked: the owner resolves it when you Save';
        p.append(el('span',SETTING_LABELS[key],'workflow-setting-label'),el('span',value,'workflow-setting-value'),el('span',origin,'workflow-setting-origin'));box.append(p);}
      const at=fresh.read?.at?riverClock(Date.parse(fresh.read.at)):null;
      box.append(el('p',checked?'Resolved by the workflow owner in the saved version’s read'+(at?' at '+at:'')+(line.boundary?'; it applies from the '+line.boundary:'')+'.'+(checked<rows.length?' Rows marked unchecked are what this draft declares; Save to have the owner resolve them.':''):owner?.definition?'Unchecked: this draft changed what decides these values, so only what it declares is shown. Save to have the owner resolve them.':'Unchecked: this workflow is not saved yet, so only what the draft declares is shown. Save to have the owner resolve each value.','workflow-hint workflow-settings-read'));
      const draftHint=el('p','Save to resolve changed settings.','workflow-hint workflow-effective-draft');draftHint.hidden=!fresh.draft;box.append(draftHint);
      const unavailable=(line.unavailable||[]).filter(text=>/conversation/.test(text));if(unavailable.length)box.append(el('p','Unavailable for a workflow step, in the owner’s words: '+unavailable.join('; ')+'.','workflow-hint'));
      const exact=el('pre',json({step_id:step.id,settings:Object.fromEntries(rows.map(([key,row])=>[key,row.checked==='owner'?{value:row.fact.value??null,origin:row.fact.origin,lineage:row.fact.lineage,application_boundary:row.fact.application_boundary,observation:row.fact.observation}:{declared_in:row.origin,value:row.declared?row.value:null,checked:false}])),unavailable_scopes:line.unavailable}),'workflow-setting-identity');exact.hidden=!identityOpen;
      const identity=declare(button(identityOpen?'Hide identity':'Identity',()=>{identityOpen=!identityOpen;exact.hidden=!identityOpen;identity.textContent=identityOpen?'Hide identity':'Identity';identity.setAttribute('aria-expanded',String(identityOpen));}),'workflow:setting-identity',step.id);identity.setAttribute('aria-expanded',String(identityOpen));box.append(identity,exact);
    };
    for(const previous of lineageViews)if(previous.box?.isConnected===false)lineageViews.delete(previous);refresh.box=box;lineageViews.add(refresh);refresh(state,true);
  }
  function paintWorkflowDefaults(place,state,body){const group=settingChoices(place,state,body);declare(field(group,'Default input policy',body.settings?.input_policy||'',value=>edit(state,{type:'default-setting',key:'input_policy',value},true),{name:'default-input_policy'}),'workflow:setting-workflow','input_policy');}
  function refreshSettingChoices(state){for(const refresh of settingGroups)refresh(state);for(const refresh of lineageViews)refresh(state);}
  function captureFocus(){const active=document.activeElement;if(!host.contains?.(active))return null;return {field:active.dataset?.field,node:active.dataset?.node,action:active.dataset?.action,start:active.selectionStart,end:active.selectionEnd};}
  const trackEditorFocus=()=>{if(!appOpen){const focus=captureFocus();if(focus?.field||focus?.node)editorFocus=focus;}};host.addEventListener('focusin',trackEditorFocus);
  function restoreFocus(saved){if(!saved)return false;const all=[...detail.querySelectorAll('[data-field]'),...detail.querySelectorAll('[data-node]'),...detail.querySelectorAll('[data-action]')];const found=all.find(n=>saved.field?n.dataset.field===saved.field:saved.node?n.dataset.node===saved.node:saved.action?n.dataset.action===saved.action:false);if(found){found.focus?.({preventScroll:true});if(saved.start!=null)found.setSelectionRange?.(saved.start,saved.end);}return !!found;}
  const trackRunFocus=event=>{if(runFocus&&event.target.dataset?.node!==runFocus.node)runFocus=null;};document.addEventListener('focusin',trackRunFocus);
  function restoreRunFocus(){if(!runFocus)return;const selected=runPort.snapshot().selection;
    if(!appOpen||selected?.work_id!==runFocus.work_id||selected.step_id!==runFocus.step_id||JSON.stringify(selected.reference)!==runFocus.reference){runFocus=null;return;}
    if(restoreFocus(runFocus))runFocus=null;
  }
  // Templates are rows of the opening list (wave 9), read once from the owner's starters_read; using
  // one keeps the existing ownership choice and makes an unsaved draft, as the old dialog did.
  function loadStarters(){
    const handle=port.snapshot().listing?.starters_read;if(starters.io!=='idle'||handle?.http?.method!=='GET'||!handle.http.url)return starters.promise||Promise.resolve();
    const promise=(async()=>{try{const value=await request(handle.http.url);if(value?.schema_version!=='laplace.workflow-definition/1'||!Array.isArray(value.starters))throw Error('The workflow owner returned no compatible starters.');starters={io:'done',value};}catch(error){starters={io:'error',error:error.message};}paintTemplates();})();
    starters={io:'loading',promise};paintTemplates();return promise;
  }
  function paintTemplates(){
    const section=library.querySelector('.workflow-templates');if(!alive||!section)return;const list=el('ul','','workflow-overview-list');
    if(starters.io==='done')for(const definition of starters.value.starters){const item=el('li','','workflow-overview-row workflow-template-row'),head=el('div','','workflow-overview-head'),use=button('Use this template',()=>requestCreation(definition));use.dataset.action='use-template';use.setAttribute('aria-label','Use '+(definition.title||'this template'));head.append(el('h3',definition.title||'Untitled template','workflow-overview-title'),use);item.append(head);if(definition.description)item.append(el('p',definition.description,'workflow-overview-purpose'));const drawing=el('div','','workflow-overview-drawing');drawing.append(workflowMiniDrawing(definition));item.append(drawing);list.append(item);}
    section.replaceChildren(el('h2','Start from a template'),el('p','A template becomes an unsaved draft. Saving it and running it stay separate decisions.','workflow-hint'),...(starters.io==='loading'?[el('p','Reading templates…','workflow-hint')]:starters.io==='error'?[el('p','Templates unavailable: '+starters.error,'workflow-hint')]:[]),list);
  }
  // THE PAGE AS IT OPENS (wave 9): the saved workflows, each a row with its stages drawn, its saved
  // version and its recorded runs, then the templates. A row's stages and runs are read from the owner
  // only once that row is on screen (its definition read and, for a project workflow, its recorded-runs
  // read), so a long library costs no read it does not show; without IntersectionObserver none is made.
  const showingOverview=state=>!state.selection||overviewOpen;
  const overviewKey=row=>row.definition_id+'@'+(row.version||'');
  const runsWords=items=>{const counts=new Map();for(const item of workflowRunsOrder(items)){const word=item.recorded_status||'status not stated';counts.set(word,(counts.get(word)||0)+1);}return [...counts].map(([word,n])=>n+' '+word).join(', ');};
  function fillOverviewRow(item,row){
    const held=overviewReads.get(overviewKey(row)),drawing=item.querySelector('.workflow-overview-drawing'),use=item.querySelector('.workflow-overview-use');if(!drawing||!use)return;
    drawing.replaceChildren(held?.io==='done'?workflowMiniDrawing(held.definition):el('p',held?.io==='error'?'Stages unavailable: '+held.error:held?.io==='loading'?'Reading its stages…':'Its stages are read when this row is on screen.','workflow-hint'));
    const runs=held?.runs;use.textContent=!runs?'':runs.io==='loading'?'Reading recorded runs…':runs.io==='error'?'Recorded runs unavailable: '+runs.error:runs.total===0?'No recorded runs':runs.total+' recorded run'+(runs.total===1?'':'s')+': '+runsWords(runs.items)+(runs.items.length<runs.total?' (first '+runs.items.length+' read)':'');use.hidden=!use.textContent;
  }
  function repaintOverviewRow(row){if(!alive)return;const item=[...library.querySelectorAll('[data-overview-row]')].find(node=>node.dataset.overviewRow===row.definition_id);if(item)fillOverviewRow(item,row);}
  async function readOverviewRow(row){
    const key=overviewKey(row);if(overviewReads.has(key))return;const held={io:'loading'};overviewReads.set(key,held);repaintOverviewRow(row);
    try{const value=await request(workflowReadURL(row.read_handle||row.read));if(value?.definition_id!==row.definition_id||!Array.isArray(value.definition?.steps)||!Array.isArray(value.definition?.edges))throw Error('the owner returned another workflow');held.definition=value.definition;held.title=value.definition.title||row.title;held.io='done';
      if(value.app_runs_read){held.runs={io:'loading'};repaintOverviewRow(row);try{const runs=await request(workflowReadURL(value.app_runs_read));if(!Array.isArray(runs?.items)||!Number.isSafeInteger(runs.total))throw Error('no run list was returned');held.runs={io:'done',items:runs.items,total:runs.total};}catch(error){held.runs={io:'error',error:error.message};}}
    }catch(error){held.io='error';held.error=error.message;}
    repaintOverviewRow(row);
  }
  function watchOverviewRow(item,row){
    if(deferOverviewReads||typeof globalThis.IntersectionObserver!=='function'||overviewReads.has(overviewKey(row)))return;
    if(!overviewObserver)overviewObserver=new IntersectionObserver(entries=>{for(const entry of entries)if(entry.isIntersecting){overviewObserver.unobserve(entry.target);if(alive&&entry.target.overviewRow)readOverviewRow(entry.target.overviewRow);}},{rootMargin:'160px'});
    item.overviewRow=row;overviewObserver.observe(item);
  }
  function paintOverview(state,capture){
    overviewObserver?.disconnect();const content=el('div','','workflow-overview'),top=el('div','','workflow-overview-top'),actions=el('div','','workflow-actions');library.append(content);
    actions.append(button('New workflow',()=>requestCreation(),{disabled:!state.listing?.actions?.create?.permitted,title:state.listing?.actions?.create?.reason||''}),button('Refresh definitions',()=>{overviewReads.clear();return act({type:'list'});}));
    top.append(el('h2','Your workflows'),actions);content.append(top);paintCreationChoices(content,state);
    const rows=state.listing?.definitions||state.listing?.items||[],list=el('ul','','workflow-overview-list');
    for(const row of rows){
      const item=el('li','','workflow-overview-row'),head=el('div','','workflow-overview-head'),open=button(row.title||row.definition?.title||'Untitled workflow',()=>act({type:'select',id:row.definition_id,read:row.read_handle||row.read}));item.dataset.overviewRow=row.definition_id;
      open.dataset.definition=row.definition_id;open.className='workflow-overview-open';open.setAttribute('aria-current',state.selection?.id===row.definition_id?'page':'false');head.append(open);
      if(row.history_read){const history=button('Browse saved versions',()=>openHistory({...row,scope_id:state.listing.scope_id},row.history_read,'library'));history.dataset.control='workflow:history';history.dataset.historyWorkflow=row.definition_id;history.dataset.historyOpener='library';head.append(history);}
      const meta=el('p','','workflow-overview-meta');if(row.scope)meta.append(el('span',scopeLabel(row.scope)));if(row.version){const short=String(row.version).replace(/^sha256:/,'').slice(0,12),version=el('span','Saved version '+short);version.title=row.version;meta.append(version);}if(state.selection?.id===row.definition_id&&state.draft)meta.append(el('span','Unsaved changes in this tab'));
      item.append(head,...(meta.children.length?[meta]:[]),el('div','','workflow-overview-drawing'),el('p','','workflow-overview-use'));list.append(item);fillOverviewRow(item,row);watchOverviewRow(item,row);
    }
    if(!rows.length)list.append(el('li','No saved workflows yet. New workflow, or a template below, keeps an unsaved draft until you choose Save definition.','workflow-overview-empty'));content.append(list);
    if(state.listing?.next)content.append(button('More definitions',()=>act({type:'list',read:state.listing.next})));
    const chooser=select(content,'Workflow chooser',[['','Choose a workflow'],...rows.map(row=>[row.definition_id,row.title||'Untitled workflow'])],state.selection?.id,id=>{const row=rows.find(value=>value.definition_id===id);if(row)act({type:'select',id,read:row.read_handle||row.read});});chooser.parentElement.className='workflow-compact-chooser';
    const held=capture.drafts.filter(row=>!rows.some(value=>value.definition_id===row.id));if(held.length){const drafts=el('section','','workflow-overview-drafts');drafts.append(el('h2','Unsaved drafts'));for(const draft of held)drafts.append(button('Resume draft: '+draft.definition.title,()=>act({type:'select',id:draft.id,read:draft.read})));content.append(drafts);}
    if(state.listing?.starters_read){content.append(el('section','','workflow-templates'));paintTemplates();if(!deferOverviewReads)loadStarters();}
  }
  // Runs with no workflow open: the recorded runs the opening list has already read, one line each.
  function paintOverviewRuns(parent,state){
    const rows=(state.listing?.definitions||[]).map(row=>[row,overviewReads.get(overviewKey(row))]).filter(([,held])=>held?.runs?.io==='done'&&held.runs.total>0),list=el('ul','','workflow-overview-list');
    parent.append(el('p','Choose a saved workflow to see its runs drawn on its stages. Only project workflows have recorded runs; an empty list here does not mean there is no other project activity.','workflow-hint'));
    for(const [row,held]of rows){const item=el('li','','workflow-overview-row'),head=el('div','','workflow-overview-head'),open=button('Open its runs',async()=>{const result=await act({type:'select',id:row.definition_id,read:row.read_handle||row.read});if(result&&alive)chooseWorkspaceView('runs');});open.setAttribute('aria-label','Open the runs of '+(held.title||row.title));head.append(el('h3',held.title||row.title||'Untitled workflow','workflow-overview-title'),open);item.append(head,el('p',held.runs.total+' recorded run'+(held.runs.total===1?'':'s')+': '+runsWords(held.runs.items),'workflow-overview-use'));list.append(item);}
    if(rows.length)parent.append(list);
  }
  async function withdrawOriginal(){
    const initial=port.snapshot(),requestId=initial.attempt?.request_id,origin=document.activeElement;let laterIntent=false;
    const later=event=>{if(event.target!==origin&&event.target!==document.body)laterIntent=true;};for(const type of ['focusin','pointerdown','keydown'])document.addEventListener?.(type,later,true);
    try{const value=await act({type:'withdraw'}),current=port.snapshot();if(!laterIntent&&alive&&current.attempt?.request_id===requestId&&(document.activeElement===origin||document.activeElement===document.body)){const summary=[...detail.querySelectorAll('[data-workflow-attempt]')].find(node=>node.dataset.workflowAttempt===requestId);summary?.focus?.({preventScroll:true});}return value;}
    finally{for(const type of ['focusin','pointerdown','keydown'])document.removeEventListener?.(type,later,true);}
  }
  async function requestCreation(definition=null,source=null){
    const state=port.snapshot();if(!state.listing?.creation_choices_read)return act({type:'create',...(definition?{definition}:{})});
    creationDefinition=definition?structuredClone(definition):null;creationSource=source;creationOpen=true;libraryOpen=true;overviewOpen=true;
    if(!state.creation_choices?.items?.length)await act({type:'creation-choices'});else paint({...port.snapshot(),event:'view'});
    library.querySelector('[data-creation-choice]')?.focus?.({preventScroll:true});return true;
  }
  function paintCreationChoices(parent,state){
    if(!creationOpen)return;const form=el('form','','workflow-creation-choice'),choices=state.creation_choices;
    form.append(el('h3',creationSource?'Keep the new copy of '+creationSource.title+' in…':creationDefinition?'Keep this starter in…':'Keep the new workflow in…'),...(creationSource?[el('p','Copies saved version '+creationSource.version+' only. Unsaved edits are not included. The original keeps its identity and history.','workflow-hint')]:[]),el('p','Choose explicitly: a project workflow can use its admitted project execution route; a reusable workspace design is not automatically a project run. This creates a local draft, not a saved version.','workflow-hint'));
    if(choices?.io==='loading')form.append(el('p','Reading admitted project and workspace choices…'));
    if(choices?.error)form.append(el('p',choices.error,'error'));
    const items=choices?.items||[],choice=select(form,'Workflow ownership',[['','Choose project or reusable design'],...items.map((item,index)=>[String(index),item.title||scopeLabel(item.scope)])],creationScope===null?'':String(items.findIndex(item=>equal(item.scope,creationScope))),value=>{creationScope=items[Number(value)]&&value!==''?structuredClone(items[Number(value)].scope):null;});choice.dataset.creationChoice='';
    const create=el('button','Create local draft');create.type='submit';create.disabled=!items.length;form.append(create,button('Keep browsing',()=>{creationOpen=false;creationDefinition=null;creationSource=null;paint({...port.snapshot(),event:'view'});}));
    if(choices?.value?.next_read)form.append(button('More projects',()=>act({type:'creation-choices',read:choices.value.next_read})));
    form.onsubmit=async event=>{event.preventDefault();const item=items.find(row=>equal(row.scope,creationScope));if(!item){notice.textContent='Choose an offered ownership before creating the draft.';choice.focus?.();return;}const definition=creationDefinition,source=creationSource;creationOpen=false;creationDefinition=null;creationSource=null;if(source){const now=port.snapshot();if(!adaptable(now)||!sameSaved(now.read.value,source)){notice.textContent='The saved version chosen for copying is no longer the verified selection. Nothing was created.';paint({...port.snapshot(),event:'view'});return;}}const result=await act({type:'create',choice:structuredClone(item.scope),...(definition?{definition}: {})});if(!result){creationOpen=true;creationDefinition=definition;creationSource=source;paint({...port.snapshot(),event:'view'});}};
    parent.append(form);
  }
  function paintLibrary(state,capture){library.replaceChildren();if(showingOverview(state)){paintOverview(state,capture);return;}overviewObserver?.disconnect();const content=el('div');
    if(state.selection){const chooser=el('details','','workflow-library-chooser');chooser.open=libraryOpen;chooser.ontoggle=()=>{libraryOpen=chooser.open;};chooser.append(el('summary','Choose another workflow'),content);library.append(chooser);}else library.append(content);
    content.append(el('h2','Your workflows'));
    const actions=el('div','','workflow-actions');actions.append(button('New workflow',()=>requestCreation(),{disabled:!state.listing?.actions?.create?.permitted,title:state.listing?.actions?.create?.reason||''}),button('Refresh definitions',()=>act({type:'list'})));content.append(actions);paintCreationChoices(content,state);
    const list=el('ul');for(const row of state.listing?.definitions||state.listing?.items||[]){const item=el('li');const open=button(row.title||row.definition?.title||'Untitled workflow',()=>act({type:'select',id:row.definition_id,read:row.read_handle||row.read}));open.dataset.definition=row.definition_id;open.setAttribute('aria-current',state.selection?.id===row.definition_id?'page':'false');item.append(open);if(row.history_read){const history=button('Browse saved versions',()=>openHistory({...row,scope_id:state.listing.scope_id},row.history_read,'library'));history.dataset.control='workflow:history';history.dataset.historyWorkflow=row.definition_id;history.dataset.historyOpener='library';item.append(history);}list.append(item);}if(!list.children.length)list.append(el('li','No saved workflows yet. New workflow keeps an unsaved draft until you choose Save definition.'));content.append(list);if(state.listing?.next)content.append(button('More definitions',()=>act({type:'list',read:state.listing.next})));
    const rows=state.listing?.definitions||[],chooser=select(content,'Workflow chooser',[['','Choose a workflow'],...rows.map(row=>[row.definition_id,row.title||'Untitled workflow'])],state.selection?.id,id=>{const row=rows.find(value=>value.definition_id===id);if(row)act({type:'select',id,read:row.read_handle||row.read});});chooser.parentElement.className='workflow-compact-chooser';
    const held=capture.drafts.filter(row=>!(state.listing?.definitions||state.listing?.items||[]).some(value=>value.definition_id===row.id));for(const draft of held)content.append(button('Resume draft: '+draft.definition.title,()=>act({type:'select',id:draft.id,read:draft.read})));
  }
  function versionStatus(state){const owner=state.read?.value,held=state.draft,attempt=state.attempt;
    status.textContent=[savedLabel(owner),held?'Unsaved changes':'No unsaved changes',attempt?.status==='pending'?'Saving…':attempt?.status==='uncertain'?'Action needs recovery':'',stored?'':'Recovery storage unavailable'].filter(Boolean).join(' · ');status.dataset.version=owner?revision(owner):'';status.dataset.currentness=owner?.currentness||'';
  }
  function restoreReadingContext(){const state=port.snapshot(),owner=state.read?.value,body=state.draft?.definition||owner?.definition;onFocus({title:body?.title||'Workflow',reference:owner?.reference,version:owner?.version,draft:!!state.draft,scope:owner?.scope||state.draft?.basis?.payload?.scope});}
  function historyOpener(visit){return [...host.querySelectorAll('[data-history-workflow]')].find(node=>node.dataset.historyWorkflow===visit.owner.definition_id&&node.dataset.historyOpener===visit.origin);}
  function closeHistory({focus=true}={}){
    const visit=historyVisit;if(!visit)return;const active=document.activeElement,mayFocus=historyPane.contains(active)||active===document.body;
    if(savedVisit?.parentHistory===visit)closeSaved({focus:false});++historyEpoch;historyVisit=null;historyPane.hidden=true;historyPane.replaceChildren();detail.hidden=false;library.hidden=false;restoreReadingContext();
    if(focus&&mayFocus&&alive&&port.snapshot().selection?.id===visit.selection){const opener=historyOpener(visit);if(opener){for(let at=opener.parentElement;at&&at!==host;at=at.parentElement)if(at.tagName==='DETAILS')at.open=true;opener.focus?.({preventScroll:true});}}
  }
  function paintHistory(visit){
    if(!alive||historyVisit!==visit)return;const page=visit.page,close=button('Close saved history',()=>closeHistory());close.dataset.historyClose='';historyPane.replaceChildren(close,el('h2','Saved versions · '+(visit.owner.title||'Workflow')));
    const stateLine=el('p','','workflow-hint');stateLine.setAttribute('role','status');stateLine.textContent=visit.error||visit.loading&&'Reading this bounded history page…'||'';historyPane.append(stateLine);
    if(page){historyPane.append(el('p','This page covers '+page.covered+' of '+page.known+' retained version positions at the selected head. '+visit.seen.size+' positions read in this visit. '+(page.at_end?'End of this cut.':'Older positions remain available.')+' No bodies are read by this list.','workflow-hint'));
      const rows=el('ol','','workflow-saved-steps');for(const item of page.items){const row=el('li'),read=button('Read saved version '+item.ordinal,()=>openSavedHistory(visit,item));read.dataset.control='workflow:saved-read';read.dataset.historyVersion=item.version;row.append(read);if(item.recorded_at)row.append(el('p','Recorded locally: '+item.recorded_at,'workflow-hint'));if(item.state==='OVERSIZED')row.append(el('p','This position exceeded the metadata page budget. Its exact saved read remains explicit.','workflow-hint'));if(item.claimed_at)row.append(exactDetails('Original claimed custody time',{claimed_at:item.claimed_at,qualification:item.claimed_at_qualification}));rows.append(row);}historyPane.append(rows);
      const controls=el('div','','workflow-actions');if(page.previous_read)controls.append(button('Newer saved versions',()=>readHistoryPage(visit,page.previous_read)));if(page.next_read){const next=button('Older saved versions',()=>readHistoryPage(visit,page.next_read));next.dataset.control='workflow:history-next';controls.append(next);}if(page.current_head_read)controls.append(button('Read current history',()=>readHistoryPage(visit,page.current_head_read,{restart:true})));historyPane.append(controls,exactDetails('History identity, cut and coverage',{definition_id:page.definition_id,scope:page.scope,scope_id:page.scope_id,head_at_start:page.head_at_start,selected_version:page.selected_version,cut:page.cut,offset:page.offset,covered:page.covered,returned:page.returned,known:page.known,at_end:page.at_end,limits:page.limits,qualification:page.qualification}));}
    if(visit.error&&visit.restart)historyPane.append(button('Restart history explicitly',()=>readHistoryPage(visit,visit.restart,{restart:true})));
    for(const node of historyPane.querySelectorAll('button'))if(node!==close&&visit.loading)node.disabled=true;
  }
  async function readHistoryPage(visit,handle,{restart=false}={}){
    if(!alive||historyVisit!==visit||visit.loading)return false;const ticket=++historyEpoch,origin=document.activeElement;let cancelled=false;
    const later=event=>{if(event.target!==origin&&event.target!==document.body)cancelled=true;};document.addEventListener('focusin',later,true);document.addEventListener('pointerdown',later,true);document.addEventListener('keydown',later,true);
    visit.loading=true;visit.error='';paintHistory(visit);
    try{const page=checkedWorkflowHistoryPage(await request(workflowReadURL(handle)),visit.expected,handle);if(!alive||ticket!==historyEpoch||historyVisit!==visit||savedVisit?.parentHistory===visit)return false;
      if(visit.page&&!restart&&(page.cut!==visit.page.cut||page.head_at_start!==visit.page.head_at_start||page.known!==visit.page.known))throw Error('History inputs changed; held pages were not mixed. Restart explicitly.');
      if(restart)visit.seen.clear();for(const item of page.items)visit.seen.add(item.ordinal);visit.page=page;visit.restart=page.restart_read;visit.loading=false;paintHistory(visit);
      if(!cancelled&&(document.activeElement===document.body||document.activeElement===origin||origin?.isConnected===false)){const heading=historyPane.querySelector('h2');heading.tabIndex=-1;heading.focus?.({preventScroll:true});}return true;
    }catch(error){if(alive&&ticket===historyEpoch&&historyVisit===visit){visit.loading=false;visit.error='History unavailable: '+error.message;paintHistory(visit);}return false;
    }finally{document.removeEventListener('focusin',later,true);document.removeEventListener('pointerdown',later,true);document.removeEventListener('keydown',later,true);}
  }
  async function openHistory(owner,handle,origin){
    let expected;try{expected=workflowHistoryExpectation(owner,handle);}catch(error){notice.textContent=error.message;return false;}if(savedVisit)closeSaved({focus:false});
    const visit={owner:structuredClone(owner),expected,origin,selection:port.snapshot().selection?.id,page:null,seen:new Set(),loading:false,error:'',restart:handle};historyVisit=visit;detail.hidden=true;library.hidden=true;historyPane.hidden=false;paintHistory(visit);historyPane.querySelector('[data-history-close]')?.focus?.();return readHistoryPage(visit,handle);
  }
  function completeSaved(content,reading,value,definition,{assembly=null}={}){
    if(value.object_read)checkedSavedObjectRead(value.object_read,value.reference);
    onFocus({title:definition.title||'Saved workflow',reference:value.reference,version:value.version,draft:false,scope:value.scope,reading:true});reading.textContent=assembly?.qualification||'Saved version · read only. Your draft, save guard and original requests are kept separately.';
    content.replaceChildren(el('h2',definition.title||'Saved workflow'),el('p',value.currentness==='CURRENT'||value.is_current===true?'Current saved version at this read.':'A historical saved version; opening it does not replace the current version.','workflow-hint'));updatePurpose(content,definition.description||'No purpose recorded.');
    const steps=el('ol','','workflow-saved-steps');for(const step of definition.steps){const row=el('li');row.append(el('h3',step.title||step.id),el('p',step.assignment?.role||'No role','workflow-hint'),el('p',step.assignment?.instructions||'No instructions recorded.','workflow-saved-instructions'));steps.append(row);}content.append(steps,exactDetails('Complete saved definition and identity',{reference:value.reference,scope:value.scope,version:value.version,definition}));
    if(assembly?.raw_text)content.append(exactDetails('Original assembled JSON text and retained byte pin',{sha256:assembly.body_sha256,text:assembly.raw_text}));
    if(value.object_read){const open=button('Open this saved version in Workspace',()=>{if(onOpenSavedObject)return requestReturn(()=>onOpenSavedObject(value.object_read,value),{opener:open});return requestNavigation(savedWorkflowWorkspaceURL(value),{opener:open});});open.dataset.control='workflow:saved-workspace';content.insertBefore(open,content.querySelector('.workflow-saved-steps'));content.append(el('p','Opening the saved object is explicit. Add it to handover choices and permit sharing separately. Your authoring draft is not replaced.','workflow-hint'));}
  }
  async function openSavedHistory(parent,item){
    if(!alive||historyVisit!==parent)return false;let expected;try{expected=savedHistoryExpectation(parent.page,item);}catch(error){notice.textContent=error.message;return false;}
    ++historyEpoch;parent.loading=false;const ticket=++savedEpoch,bodyReader=createSavedWorkflowBody(expected);savedVisit={expected,parentHistory:parent,openerKey:item.version};historyPane.hidden=true;savedPane.hidden=false;const back=button('Close saved version',()=>closeSaved());back.dataset.control='workflow:saved-close';const reading=pendingRead(el('p','Reading this exact saved version…')),content=el('div');reading.setAttribute('role','status');savedPane.replaceChildren(back,reading,content);back.focus?.();let busy=false;
    const current=()=>alive&&ticket===savedEpoch&&savedVisit?.expected===expected;
    async function readPart(handle){if(!current()||busy)return false;busy=true;try{const result=await bodyReader.accept(await request(workflowReadURL(handle)),handle,{isCurrent:current});if(!result||!current())return false;
        if(result.complete)completeSaved(content,reading,result.owner,result.definition,{assembly:result});else{reading.textContent=result.qualification;content.replaceChildren(el('h2','Partial saved definition'),el('p',result.characters+' of '+result.total+' Unicode characters read in '+result.pages+' explicit parts. No complete body is displayed.','workflow-hint'));const next=button('Read next saved-body part',()=>readPart(result.next_read));next.dataset.control='workflow:saved-next';content.append(next);}return true;
      }catch(error){if(current()){reading.textContent='Saved version unavailable: '+error.message;content.replaceChildren();}return false;}finally{busy=false;}}
    return readPart(item.read);
  }
  function closeSaved({focus=true}={}){
    const visit=savedVisit;if(!visit)return;const focused=document.activeElement,mayFocus=savedPane.contains(focused)||focused===document.body;++savedEpoch;savedVisit=null;savedPane.hidden=true;savedPane.replaceChildren();if(visit.parentHistory&&historyVisit===visit.parentHistory){historyPane.hidden=false;paintHistory(visit.parentHistory);const page=visit.parentHistory.page;onFocus({title:'Saved history',reference:page.reference,version:page.head_at_start,draft:false,scope:page.scope,reading:true});if(focus&&mayFocus){const opener=[...historyPane.querySelectorAll('[data-history-version]')].find(node=>node.dataset.historyVersion===visit.expected.version);opener?.focus?.({preventScroll:true});}return;}detail.hidden=!!historyVisit;library.hidden=!!historyVisit;const state=port.snapshot(),owner=state.read?.value,body=state.draft?.definition||owner?.definition;onFocus({title:body?.title||'Workflow',reference:owner?.reference,version:owner?.version,draft:!!state.draft,scope:owner?.scope});
    if(focus&&mayFocus&&alive){const opener=[...detail.querySelectorAll('[data-saved-version]')].find(node=>node.dataset.savedVersion===visit.expected.version&&node.dataset.savedWorkflow===visit.expected.definition_id&&node.dataset.savedOpener===visit.openerKey);
      if(opener){for(let parent=opener.parentElement;parent&&parent!==detail;parent=parent.parentElement)if(parent.tagName==='DETAILS')parent.open=true;opener.focus?.({preventScroll:true});}else{const heading=detail.querySelector('h2');if(heading){heading.tabIndex=-1;heading.focus?.();}}}
  }
  async function openSaved(owner,item,openerKey){
    let expected;try{expected=savedWorkflowExpectation(owner,item);}catch(error){notice.textContent=error.message;return false;}
    const ticket=++savedEpoch;savedVisit={expected,openerKey};detail.hidden=true;library.hidden=true;savedPane.hidden=false;
    const back=button('Close saved version',()=>closeSaved());back.dataset.control='workflow:saved-close';
    const content=el('div'),reading=pendingRead(el('p','Reading this exact saved version…'));reading.setAttribute('role','status');savedPane.replaceChildren(back,reading,content);back.focus?.();
    try{const value=checkedSavedWorkflow(await request(workflowReadURL(expected.handle)),expected);
      if(!alive||ticket!==savedEpoch||savedVisit?.expected!==expected)return false;
      completeSaved(content,reading,value,value.definition);
      return true;
    }catch(error){if(alive&&ticket===savedEpoch&&savedVisit?.expected===expected){reading.textContent='Saved version unavailable: '+error.message;content.replaceChildren();}return false;}
  }
  function lineageActionState(id){
    const selected=()=>port.snapshot(),valid=()=>alive&&selected().selection?.id===id;
    return {get disposed(){return !valid();},get storageError(){return stored?'':'Workflow recovery storage is unavailable.';},get recoveryError(){return recoveryError||'';},
      snapshot:()=>({workspace:{value:{scope_id:selected().scope_id}}}),
      draft:key=>valid()?selected().context.lineage_actions?.[key]:null,
      updateDraft(key,patch){if(!valid())return;const held=selected().context.lineage_actions||{};port.dispatch({type:'context',fields:{lineage_actions:{...held,[key]:{...held[key],...structuredClone(patch)}}}}).catch(error=>{if(alive)notice.textContent=error.message;});}
    };
  }
  function lineageSection(parent,owner){
    if(!owner?.lineage_read)return;const box=el('details','','workflow-lineage'),summary=declare(el('summary','Share complete saved lineage'),'workflow:lineage'),content=el('div');box.append(summary,content);parent.append(box);let loading=false,loaded=false;
    box.ontoggle=async()=>{if(!box.open||loading||loaded)return;loading=true;const id=owner.definition_id,version=owner.version,current=()=>alive&&box.isConnected!==false&&port.snapshot().selection?.id===id&&port.snapshot().read?.value?.version===version&&port.snapshot().scope_id===owner.scope_id;
      content.replaceChildren(pendingRead(el('p','Reading the saved lineage descriptor…','workflow-hint')));
      try{const issued=checkedWorkflowHistoryHandle(owner.lineage_read,{facet:'lineage',id,head:version}),value=await request(issued.url);if(!current())return;
        if(value?.schema_version!=='laplace.workflow-definition-lineage/1'||value.definition_id!==id||value.scope_id!==owner.scope_id||!equal(value.scope,owner.scope)||!equal(value.reference,owner.reference)||value.head_at_start!==version||value.selected_version!==version||!Number.isSafeInteger(value.known_versions)||value.known_versions<1||value.body_verification!=='NOT_INSPECTED')throw Error('The lineage descriptor returned another saved workflow, scope or cut.');
        content.replaceChildren(el('p',value.known_versions+' saved versions through this exact saved endpoint. Local unsaved edits are not included.'),el('p','Transfers keep saved definitions and original history. Runtime settings, permissions and provider sessions are not migrated.','workflow-hint'));
        const action=value.handover_action;if(action){const open=button(action.title||'Prepare complete lineage export',async()=>{if(!current())return;const {openWorkbenchAction}=await import('./research-workbench-actions.mjs');if(!current())return;return openWorkbenchAction({action:{...action,id:action.id||'export-lineage'},state:lineageActionState(id),subject:value.reference,request,isCurrent:()=>alive&&port.snapshot().selection?.id===id,helpInDialog});},{disabled:action.permitted!==true,title:action.reason||''});open.dataset.control='workflow:lineage-prepare';content.append(open);if(action.reason)content.append(el('p',action.reason,'workflow-hint'));}
        content.append(exactDetails('Saved lineage endpoint and resource admission',{reference:value.reference,scope:value.scope,scope_id:value.scope_id,cut:value.cut,known_versions:value.known_versions,limits:value.limits,qualification:value.qualification}));loaded=true;
      }catch(error){if(current())content.replaceChildren(el('p','Lineage unavailable: '+error.message,'workflow-hint'));}finally{loading=false;}
    };
  }
  function edit(state,change,quiet=false){return act({type:'edit',target:state.selection.id,edit:change,quiet});}
  function graphLayout(body){
    const layout=layoutTopology(body.steps,body.edges.map(edge=>({source:edge.from,target:edge.to,kind:edge.kind})),{width:600});
    const positions=new Map(body.steps.map(step=>[step.id,body.layout?.[step.id]||layout.positions.get(step.id)||{x:110,y:50}]));
    return {positions,width:Math.max(layout.world.w,...[...positions.values()].map(p=>p.x+CARD.w/2+24)),height:Math.max(layout.world.h,...[...positions.values()].map(p=>p.y+CARD.h/2+24))};
  }
  function paintGraph(place,state,body,selected,{readOnly=false,states=null,onSelect=null}={}){
    const controls=el('div','','workflow-actions workflow-graph-tools');
    if(!readOnly)for(const [value,label]of [['select','Select / move'],['connect','Connect'],['nest','Nest']]){
      const b=button(label,()=>{mode=value;paint({...port.snapshot(),event:'view'});});b.setAttribute('aria-pressed',mode===value?'true':'false');declare(b,'workflow:graph-mode',value);controls.append(b);
    }
    const layout=graphLayout(body),canvas=el('div','','workflow-canvas'),stage=el('div','','workflow-stage'),world=el('div','','workflow-world');
    canvas.setAttribute('aria-label',readOnly?'Recorded run graph':'Workflow graph');world.style.width=layout.width+'px';world.style.height=layout.height+'px';stage.append(world);canvas.append(stage);let scale=1;
    function applyScale(value){scale=value;world.style.transform='scale('+scale+')';stage.style.width=layout.width*scale+'px';stage.style.height=layout.height*scale+'px';canvas.dataset.scale=String(scale);}
    function fit(){graphFit=true;applyScale(Math.min(1,Math.max(100,canvas.clientWidth-28)/layout.width,Math.max(100,canvas.clientHeight-28)/layout.height));canvas.scrollLeft=0;canvas.scrollTop=0;}
    function center(){graphFit=false;applyScale(1);const p=layout.positions.get(selected);if(p){canvas.scrollLeft=Math.max(0,p.x-canvas.clientWidth/2+14);canvas.scrollTop=Math.max(0,p.y-canvas.clientHeight/2+14);}}
    const fitButton=button('Fit workflow',fit),centerButton=button('Center selected',center,{disabled:!selected});if(readOnly){fitButton.dataset.control='workflow:run-fit';centerButton.dataset.control='workflow:run-center';}else{declare(fitButton,'workflow:graph-fit');declare(centerButton,'workflow:graph-center');}controls.append(fitButton,centerButton);place.append(controls);
    if(!readOnly&&mode!=='select')place.append(el('p',mode==='connect'?'Choose a destination for the selected step, or drag between steps.':'Choose the containing step, or drag a step into its parent.','workflow-hint'));
    place.append(canvas);
    if(document.createElementNS){
      const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('width',layout.width);svg.setAttribute('height',layout.height);svg.setAttribute('aria-hidden','true');world.append(svg);
      const defs=document.createElementNS('http://www.w3.org/2000/svg','defs'),marker=document.createElementNS('http://www.w3.org/2000/svg','marker');marker.setAttribute('id','workflow-arrow');marker.setAttribute('viewBox','0 0 10 10');marker.setAttribute('refX','9');marker.setAttribute('refY','5');marker.setAttribute('markerWidth','6');marker.setAttribute('markerHeight','6');marker.setAttribute('orient','auto-start-reverse');const tip=document.createElementNS('http://www.w3.org/2000/svg','path');tip.setAttribute('d','M 0 0 L 10 5 L 0 10 z');tip.setAttribute('fill','var(--accent)');marker.append(tip);defs.append(marker);svg.append(defs);
      for(const edge of [...body.edges,...body.steps.filter(step=>step.parent_id).map(step=>({from:step.parent_id,to:step.id,kind:'contains'}))]){
        const a=layout.positions.get(edge.from),b=layout.positions.get(edge.to);if(!a||!b)continue;
        const line=document.createElementNS('http://www.w3.org/2000/svg','path');line.setAttribute('d',topologyEdgeGeometry(a,b).d);line.setAttribute('class','workflow-edge '+edge.kind);if(edge.kind!=='contains')line.setAttribute('marker-end','url(#workflow-arrow)');
        const title=document.createElementNS('http://www.w3.org/2000/svg','title');title.textContent=labelFor(body,edge.from)+' → '+labelFor(body,edge.to)+' ('+edge.kind+')';line.append(title);svg.append(line);
      }
    }
    const gesture=target=>readOnly?onSelect?.(target):mode==='select'||!selected||selected===target?act({type:'step',id:target}):edit(state,mode==='nest'?{type:'nest',id:selected,parent_id:target}:{type:'connect',from:selected,to:target,kind:'control'});
    for(const step of body.steps){
      const p=layout.positions.get(step.id),node=button('',()=>gesture(step.id));node.append(el('strong',step.title||step.id,'workflow-node-title'),el('small',step.assignment?.role||'No role'));
      node.className='workflow-node';node.dataset.node=step.id;node.setAttribute('aria-pressed',step.id===selected?'true':'false');node.setAttribute('aria-label',(readOnly?'Run step ':'Graph step ')+(step.title||step.id));node.title=step.parent_id?'Inside '+labelFor(body,step.parent_id):'Top level';node.style.left=p.x-CARD.w/2+'px';node.style.top=p.y-CARD.h/2+'px';node.draggable=!readOnly;if(!readOnly)declare(node,'workflow:graph-step',step.id);
      if(readOnly){const fact=states.get(step.id),word=fact?.state?ownerStateWord('dispatch-child',fact.state).words:'Not selected for this run';node.dataset.runState=fact?.state||'unselected';node.dataset.control='workflow:run-step';node.dataset.controlOwner=step.id;node.append(el('span',word,'workflow-node-state'));node.disabled=!fact?.read;node.title=word;}
      if(!readOnly){node.ondragstart=event=>{event.dataTransfer.setData('application/x-laplace-step',step.id);event.dataTransfer.effectAllowed='move';};node.ondragover=event=>event.preventDefault();node.ondrop=event=>{event.preventDefault();event.stopPropagation();const from=event.dataTransfer.getData('application/x-laplace-step');if(mode==='nest')edit(state,{type:'nest',id:from,parent_id:step.id});else if(mode==='connect')edit(state,{type:'connect',from,to:step.id,kind:'control'});};}world.append(node);
    }
    if(!readOnly){world.ondragover=event=>event.preventDefault();world.ondrop=event=>{event.preventDefault();if(mode!=='select')return;const step=event.dataTransfer.getData('application/x-laplace-step'),rect=world.getBoundingClientRect();edit(state,{type:'move',id:step,x:Math.max(CARD.w/2,(event.clientX-rect.left)/scale),y:Math.max(CARD.h/2,(event.clientY-rect.top)/scale)});};}
    requestAnimationFrame(()=>{if(!alive||!canvas.isConnected)return;if(graphFit)fit();else center();});
  }
  // A plain explanation beside the element it explains, opened and closed by a labelled button (W4).
  function explainer(head,key,control=null){
    const [label,text]=WORKFLOW_EXPLAINERS[key],note=el('p',text,'workflow-explain-text'),toggle=button(label,()=>{const open=note.hidden;note.hidden=!open;toggle.textContent=open?'Hide explanation':label;toggle.setAttribute('aria-expanded',String(open));});if(control){toggle.dataset.control=control;toggle.dataset.controlOwner=key;}else declare(toggle,'workflow:explain',key);
    toggle.className='workflow-explain-toggle';toggle.dataset.explain=key;toggle.setAttribute('aria-expanded','false');note.hidden=true;note.dataset.explainText=key;
    const more=button('More in Guide',()=>chooseWorkspaceView('guide'));more.className='workflow-explain-more';if(control){more.dataset.control='workflow:run-guide';more.dataset.controlOwner=key;}else declare(more,'workflow:explain-guide',key);note.append(' ',more);head.append(toggle);return note;
  }
  function sectionHead(place,title,keys=[],level='h3',control=null){const head=el('div','','workflow-section-head');head.append(el(level,title));const notes=keys.map(key=>explainer(head,key,control));place.append(head,...notes);return head;}
  // The topology drawn as the main thing: one node per stage in columns left to right (stacked in
  // reading order below 720 px), arrows for what passes forward, review loops drawn back underneath
  // with their bound in words. With marks it is a run: each node says planned, admitted and observed
  // separately, in words and shapes, and links the session behind an observed stage.
  // One run stage on the drawing: its role and the provider and model it ran with (saying which: admitted, else
  // prepared), then three marks never merged (planned, admitted with the owner's state in plain words and its time,
  // observed with its session) and a separate fourth fact, current liveness, from the river's current_observation.
  function runFact(step,row,river,prepared){
    if(!step&&!row)return undefined;
    return {...(step||{}),state:row?.state??step?.state,current_attempt:row?.current_attempt??step?.current_attempt,conversation:step?.conversation||row?.reads?.conversation||null,read:step?.read,
      turn:row?.turn||null,liveness:row?.turn_id?river?.current_observation?.by_turn?.[row.turn_id]||null:null,running:!!row&&riverRowRunning(river,row),settings:riverStepSettings(row,prepared)};
  }
  // The run's words that the river's re-read changes in place (the header state, the facts line, the graph and list
  // states), from the river read's own observation and rows; after a failed read each says last known.
  function updateRunWords(strip,river,live={}){
    if(!strip||!river)return;const lastKnown=live.failure?' (last known '+riverClock(live.lastGoodAt)+')':'',at=riverClock(live.failure?live.lastGoodAt:live.readAt),obs=river.observation||{},w=strip.words||{};
    if(w.stateLine&&obs.execution_state){const word=ownerStateWord('run-execution',obs.execution_state);w.stateLine.textContent=word.shape+' Run '+word.words.toLowerCase()+lastKnown+' · read '+at+' (observed flow read)';}
    if(w.execution&&obs.execution_state)w.execution.textContent='Execution: '+ownerStateWord('run-execution',obs.execution_state).words+lastKnown;
    if(w.review&&obs.review_state)w.review.textContent='Review: '+ownerStateWord('run-review',obs.review_state).words+lastKnown;
    if(w.task&&obs.recorded_status)w.task.textContent='Task: '+(taskStateChips({lifecycle:{status:obs.recorded_status}})[0]?.label||'not reported')+lastKnown;
    if(w.snapshot)w.snapshot.textContent='These facts and the step states below are from the observed flow read at '+at+(live.failure?'; the latest read failed.':'.');
    for(const row of river.items||[]){const word=ownerStateWord('dispatch-child',row.state).words+lastKnown;
      for(const node of strip.panel.querySelectorAll('[data-node="'+row.step_id+'"],[data-node="list:'+row.step_id+'"]')){const listed=node.dataset.node.startsWith('list:'),holder=listed?node.parentElement:node,span=holder?.querySelector('.workflow-node-state');if(span)span.textContent=(listed?' · ':'')+word;if(holder)holder.dataset.runState=row.state||'';}}
  }
  function fillRunNode(node,step,fact,live={}){
    for(const old of node.querySelectorAll('.workflow-run-marks,.workflow-run-who'))old.remove();
    const m=workflowRunMarks(fact),set=fact?.settings,state=ownerStateWord('dispatch-child',m.state),turn=fact?.turn,replied=riverTime(turn?.replied_at),started=riverTime(turn?.started_at),when=replied!=null?' · replied '+riverClock(replied):started!=null?' · started '+riverClock(started):'';
    const who=el('p',['Role: '+(step.assignment?.role||'none'),set?[set.provider,set.model].filter(Boolean).join(' · ')+' ('+set.source+')':'provider and model not stated'].join(' · '),'workflow-run-who');
    const lines=el('ul','','workflow-run-marks'),mark=(kind,shape,words)=>{const row=el('li','','workflow-run-mark');row.dataset.mark=kind;row.append(el('span',shape,'workflow-run-shape'),el('span',words));return row;};
    lines.append(mark('planned','○','Planned'),m.admitted?mark('admitted',state.shape,'Admitted · '+state.words+(live.failure?' (last known '+riverClock(live.lastGoodAt)+')':'')+when):mark('not-admitted','◇','Not admitted to this run'),m.observed?mark('observed','●','Observed'):mark('not-observed','–','Not observed'));
    if(m.conversation){const link=el('a','Open its session','workflow-run-session');link.href=m.conversation.project_url;link.dataset.control='workflow:run-session';link.dataset.controlOwner=step.id;link.onclick=event=>{event.preventDefault();openConversation(m.conversation).catch(error=>{notice.textContent=error.message;});};lines.lastChild.append(link);}
    const now=fact?.liveness;
    if(now){const word=ownerStateWord('host-liveness',now.observed),row=live.failure&&fact.running?mark('liveness','◌','Last known running '+riverClock(live.lastGoodAt)+' · the latest read failed'):mark('liveness',word.shape,'Now: '+word.words+' · observed '+riverClock(live.failure?live.lastGoodAt:live.readAt)+(fact.running&&live.activity?.get?.(fact.turn_id||fact.current_attempt?.turn_id)?' · '+live.activity.get(fact.turn_id||fact.current_attempt?.turn_id):''));lines.append(row);}
    node.dataset.runAdmitted=String(m.admitted);node.dataset.runObserved=String(m.observed);node.dataset.runState=m.state||'';node.dataset.runRunning=String(!!fact?.running&&!live.failure);node.append(who,lines);
  }
  function paintStrip(place,body,selected,options={}){
    const {marks=null,onSelect=()=>{},nodes=null,live={},widthHint=0}=options;
    const {columns,forward,loops}=workflowStageLayout(body),region=el('div','','workflow-strip');region.dataset.control='workflow:topology';place.append(region);
    if(!columns.length){region.append(el('p',marks?'The consumed definition has no stages to draw.':'No stages yet. Add step puts the first one here.','workflow-hint'));return region;}
    const width=widthHint||region.clientWidth||host.clientWidth||0,vertical=width>0&&width<720,stacked=vertical?workflowReadingOrder(columns,forward):columns.flat(),place_=new Map(stacked.map((step,index)=>[step.id,index])),long=vertical&&forward.some(edge=>place_.get(edge.to)!==place_.get(edge.from)+1),lside=long?40:0,side=vertical&&loops.length?56:0,pad=12,W=vertical?Math.max(200,Math.min(340,width-2*pad-side-lside-8)):(marks?272:216),H=marks?248:96,GX=64,GY=vertical?44:24,LABEL=52,LINE=42;
    // A review loop between two steps of one row is drawn in a band under that row; any other loop goes under the
    // whole drawing. In a band each loop dips a little deeper than the one before, and their words stand in a stack
    // under the deepest curve, so no curve crosses a label and no two labels share a place.
    const order=stacked,at=new Map(),rowOf=new Map(),rowCount=Math.max(1,...columns.map(column=>column.length));
    columns.forEach(column=>column.forEach((step,r)=>rowOf.set(step.id,r)));
    const hosted=loops.map(loop=>!vertical&&rowOf.get(loop.from)===rowOf.get(loop.to)?rowOf.get(loop.from):-1),bands=new Map(),slot=new Map();
    loops.forEach((loop,k)=>{const r=hosted[k];slot.set(k,bands.get(r)||0);bands.set(r,(bands.get(r)||0)+1);});
    const labelsAt=n=>30+21*(n-1),bandHeight=r=>{const n=bands.get(r)||0;return n?labelsAt(n)+n*LINE+4:0;};
    const rowTop=[];for(let r=0,y=pad;r<rowCount;r++){rowTop.push(y);y+=H+GY+bandHeight(r);}
    if(vertical)order.forEach((step,index)=>at.set(step.id,{x:pad+lside,y:pad+index*(H+GY)}));else columns.forEach((column,c)=>column.forEach((step,r)=>at.set(step.id,{x:pad+c*(W+GX),y:rowTop[r]})));
    const below=vertical?loops.length*LABEL:(bands.get(-1)?bandHeight(-1)+12:0);
    const worldW=vertical?pad*2+lside+W+side:pad*2+columns.length*W+(columns.length-1)*GX,bottom=vertical?pad+order.length*H+(order.length-1)*GY:rowTop[rowCount-1]+H+bandHeight(rowCount-1),worldH=bottom+pad+below;
    const loopPlace=k=>{const r=hosted[k],base=r>=0?rowTop[r]+H:bottom+12;return {ctrl:base+32+slot.get(k)*28,label:base+labelsAt(bands.get(r))+slot.get(k)*LINE};};
    const world=el('div','','workflow-strip-world');world.style.width=worldW+'px';world.style.height=worldH+'px';region.append(world);
    if(document.createElementNS){
      const make=(tag,attrs={})=>{const node=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v]of Object.entries(attrs))node.setAttribute(k,v);return node;};
      const svg=make('svg',{width:worldW,height:worldH,'aria-hidden':'true'}),defs=make('defs'),marker=make('marker',{id:'workflow-strip-arrow',viewBox:'0 0 10 10',refX:'9',refY:'5',markerWidth:'7',markerHeight:'7',orient:'auto-start-reverse'});marker.append(make('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:'var(--accent)'}));defs.append(marker);svg.append(defs);world.append(svg);
      const title=id=>body.steps.find(step=>step.id===id)?.title||id;
      for(const edge of forward){const a=at.get(edge.from),b=at.get(edge.to);if(!a||!b)continue;let d;
        // stacked: the next step's arrow goes straight down; an arrow that skips steps runs in the left margin, never behind a step
        if(vertical&&place_.get(edge.to)===place_.get(edge.from)+1){const sx=a.x+W/2,sy=a.y+H,ex=b.x+W/2,ey=b.y;d=`M${sx},${sy} C${sx},${(sy+ey)/2} ${ex},${(sy+ey)/2} ${ex},${ey-2}`;}
        else if(vertical)d=`M${a.x},${a.y+H/2} C${a.x-lside},${a.y+H/2} ${b.x-lside},${b.y+H/2} ${b.x-2},${b.y+H/2}`;
        else{const sx=a.x+W,sy=a.y+H/2,ex=b.x,ey=b.y+H/2;d=`M${sx},${sy} C${(sx+ex)/2},${sy} ${(sx+ex)/2},${ey} ${ex-2},${ey}`;}
        const path=make('path',{d,class:'workflow-strip-edge '+edge.kind,'marker-end':'url(#workflow-strip-arrow)'});if(WORKFLOW_EDGE_MARKS[edge.kind]?.dash)path.setAttribute('stroke-dasharray',WORKFLOW_EDGE_MARKS[edge.kind].dash);const tip=make('title');tip.textContent=title(edge.from)+' passes '+(WORKFLOW_EDGE_MARKS[edge.kind]?.short||'its result')+' to '+title(edge.to);path.append(tip);svg.append(path);}
      loops.forEach((loop,k)=>{const f=at.get(loop.from),t=at.get(loop.to);if(!f||!t)return;const ctrl=loopPlace(k).ctrl;
        const d=vertical?`M${f.x+W},${f.y+H/2} C${f.x+W+side},${f.y+H/2} ${t.x+W+side},${t.y+H/2} ${t.x+W+2},${t.y+H/2}`:`M${f.x+W/2},${f.y+H} C${f.x+W/2},${ctrl} ${t.x+W/2},${ctrl} ${t.x+W/2},${t.y+H+2}`;
        const path=make('path',{d,class:'workflow-strip-edge feedback','marker-end':'url(#workflow-strip-arrow)','stroke-dasharray':WORKFLOW_EDGE_MARKS.feedback.dash});const tip=make('title');tip.textContent=workflowLoopWords(body,loop);path.append(tip);svg.append(path);});
    }
    order.forEach((step,index)=>{
      const p=at.get(step.id),role=step.assignment?.role||'none',node=marks?el('div','','workflow-stage-node workflow-run-stage'):button('',()=>onSelect(step.id));
      if(!marks){node.className='workflow-stage-node';node.dataset.action='stage:'+step.id;declare(node,'workflow:stage',step.id);node.setAttribute('aria-pressed',step.id===selected?'true':'false');node.setAttribute('aria-label','Step '+(index+1)+': '+(step.title||step.id)+', role '+role);node.append(el('span','Step '+(index+1),'workflow-stage-number'),el('strong',step.title||step.id,'workflow-stage-title'),el('span','Role: '+role,'workflow-stage-role'));}
      else{
        const fact=marks.get(step.id),open=button(step.title||step.id,()=>onSelect(step.id),{disabled:!fact?.read,title:fact?.read?'Read this stage of the run':'Not admitted to this run'});open.className='workflow-stage-open';open.dataset.action='stage:'+step.id;open.dataset.control='workflow:run-step';open.dataset.controlOwner=step.id;open.setAttribute('aria-pressed',step.id===selected?'true':'false');
        node.append(open);fillRunNode(node,step,fact,live);nodes?.set(step.id,node);
      }
      node.dataset.stage=step.id;node.style.left=p.x+'px';node.style.top=p.y+'px';node.style.width=W+'px';node.style.height=H+'px';world.append(node);
    });
    loops.forEach((loop,k)=>{const f=at.get(loop.from),t=at.get(loop.to);if(!f||!t)return;const max=body.run_policy?.max_iterations,name=id=>body.steps.find(row=>row.id===id)?.title||id,label=el('p','','workflow-strip-loop');label.append(el('span','Sent back for revision'+(Number.isSafeInteger(max)&&max>0?' · at most '+max+' review round'+(max===1?'':'s'):'')),el('span','from '+name(loop.from)+' to '+name(loop.to)));
      if(vertical){label.style.left=pad+lside+'px';label.style.top=bottom+12+k*LABEL+'px';label.style.width=W+side+'px';}else{const left=Math.min(f.x,t.x),right=Math.max(f.x,t.x)+W;label.style.left=left+'px';label.style.top=loopPlace(k).label+'px';label.style.width=right-left+'px';}world.append(label);});
    place.append(el('p',workflowEdgeLegend(),'workflow-strip-legend'));
    // The page is built before it is on screen, so the width above is the editor's; once the drawing is on screen a
    // stacked drawing wider than its own box is drawn again at that box's width (once), so no step is cut at the edge.
    if(!widthHint&&vertical)globalThis.requestAnimationFrame?.(()=>{if(!alive||region.isConnected===false||!region.clientWidth||region.clientWidth+1>=worldW)return;const again=el('div');paintStrip(again,body,selected,{...options,widthHint:region.clientWidth});const fresh=again.querySelector('.workflow-strip');if(fresh)region.replaceWith(fresh);});
    return region;
  }
  function paintStageTools(place,state,body,selected){
    const {order}=workflowStageLayout(body),index=order.findIndex(step=>step.id===selected),step=order[index],tools=el('div','','workflow-actions workflow-stage-tools');
    const fresh=()=>{const now=port.snapshot();return alive&&now.selection?.id===state.selection.id?now:null;};let blocked=null;
    tools.append(declare(button('Add step',async()=>{inspectorTab='step';const at=await edit(state,{type:'add'});if(at)await act({type:'step',id:at.draft.definition.steps.at(-1).id});}),'workflow:stage-add'));
    if(step){
      const add=button('Add a step after this one',async()=>{const now=fresh();if(!now)return;const id=localId('step');const at=await edit(now,{type:'insert-after',after:step.id,id});if(at)await act({type:'step',id});});add.dataset.action='stage-insert';declare(add,'workflow:stage-insert',step.id);
      // Move is offered only where the moved draft stays one the owner accepts (workflowSwapBlocker).
      const blockEarlier=index>0?workflowSwapBlocker(body,step.id,order[index-1].id):null,blockLater=index<order.length-1?workflowSwapBlocker(body,step.id,order[index+1].id):null;
      const earlier=button('Move earlier',()=>{const now=fresh();if(now)return edit(now,{type:'swap',a:step.id,b:order[index-1].id});},{disabled:index<1||!!blockEarlier,title:blockEarlier||''});earlier.dataset.action='stage-earlier';declare(earlier,'workflow:stage-earlier',step.id);
      const later=button('Move later',()=>{const now=fresh();if(now)return edit(now,{type:'swap',a:step.id,b:order[index+1].id});},{disabled:index>=order.length-1||!!blockLater,title:blockLater||''});later.dataset.action='stage-later';declare(later,'workflow:stage-later',step.id);
      const remove=button('Remove this step',()=>{const now=fresh();if(now)return edit(now,{type:'remove',id:step.id});},{title:'Removes this step. A step that passed forward to it now passes forward to the step after it.'});remove.dataset.action='stage-remove';declare(remove,'workflow:stage-remove',step.id);
      tools.append(add,earlier,later,remove);
      blocked=blockEarlier||blockLater;
    }
    place.append(tools);if(blocked)place.append(el('p','Move is not offered: '+blocked,'workflow-hint'));if(!step&&order.length)place.append(el('p','Choose a step on the drawing to set it, move it, add one after it or add a route pattern beside it.','workflow-hint'));
    if(step)paintPatterns(place,state,body,step);
  }
  // ROUTE PATTERNS (wave 12, P1): each button is one draft edit (workflow-port editWorkflow) inserting only ordinary
  // steps and arrows; what a pattern inserts is its declared guide sentence. Whether a pattern is offered, and the
  // sentence beside a greyed one, come from the owner's execution preview (the offer Check execution follows,
  // listing.execution_preview, a pure read of an unsaved draft) about the draft the pattern makes (workflowPatternProbe):
  // read when a step is chosen or a pattern's choice changes, one read per pattern and draft, and read again on press
  // for a draft it was not read for. A refusal applies nothing and shows the owner's sentences (issueText, the one
  // wording Check execution uses): its execution issues, or the definition check it runs first (ownerRefusalIssue).
  // The page keeps no admission rule of its own; workflowPatternBlocker says only that a draft cannot be built yet.
  // With no offer, or a read that fails without an owner refusal, the button says Check first and does nothing.
  // Nothing about a pattern is stored: its steps are ordinary steps, removed with Remove this step.
  let patternReads=null,patternIds=null;const patternAnswers=new Map();
  const bodyOf=state=>state?.draft?.definition||state?.read?.value?.definition;
  function patternAnswer(state,made){
    const offer=state.listing?.execution_preview;if(!offer)return {value:{unavailable:'The owner has issued no execution check for this list yet.'}};
    const definition=workflowPatternProbe(made),inputs={definition,scope:structuredClone(workflowPreviewScope(state)),step_ids:workflowPreviewSteps(definition)},key=JSON.stringify([state.scope_id,inputs]);
    if(patternAnswers.has(key))return patternAnswers.get(key);
    while(patternAnswers.size>=24)patternAnswers.delete(patternAnswers.keys().next().value);
    const entry={value:null};entry.promise=readWorkflowOperation(offer,inputs,{request,expected:{scope_id:state.scope_id}}).then(
      value=>entry.value=value?{support:value.support,issues:value.issues,coverage:value.issue_coverage||null}:{unavailable:'The read was superseded.'},
      error=>{const refusal=ownerRefusalIssue(error);if(refusal)return entry.value={support:'REFUSED_DEFINITION',issues:[refusal],coverage:null};patternAnswers.delete(key);return entry.value={unavailable:error.message};});
    patternAnswers.set(key,entry);return entry;
  }
  function patternSentence(answer,made){
    const title=id=>made.steps.find(row=>row.id===id)?.title||id,said=[...new Set(answer.issues.map(row=>(row.step_id?title(row.step_id)+': ':'')+issueText(row)))];
    const more=answer.coverage&&answer.coverage.known>answer.coverage.returned?' The owner lists '+(answer.coverage.known-answer.coverage.returned)+' more.':'';
    return said.join(' ')+more;
  }
  function paintPatterns(place,state,body,step){
    const box=el('section','','workflow-patterns'),fresh=()=>{const now=port.snapshot();return alive&&now.selection?.id===state.selection.id?now:null;},title=id=>body.steps.find(row=>row.id===id)?.title||id;
    box.append(el('h4','Add a route pattern beside '+(step.title||step.id)));
    if(!patternIds||patternIds.selection!==state.selection.id||patternIds.step!==step.id)patternIds={selection:state.selection.id,step:step.id,review:{step:localId('step'),edge:localId('edge'),feedback:localId('edge')},reciprocal:{copy:localId('step'),ra:localId('step'),rb:localId('step'),ra_edge:localId('edge'),ra_feedback:localId('edge'),rb_edge:localId('edge'),rb_feedback:localId('edge')},synthesis:{step:localId('step'),reads:{}}};
    const idsFor=(kind,choice)=>kind==='synthesis'?{step:patternIds.synthesis.step,edges:choice.reads.map(id=>patternIds.synthesis.reads[id]||(patternIds.synthesis.reads[id]=localId('edge')))}:patternIds[kind];
    const selectFor=(kind,ids)=>kind==='reciprocal'?ids.ra:ids.step;
    // one pattern's button: whether its draft can be built (workflowPatternBlocker), then the owner's answer for that draft
    const show=(b,label,{blocker=null,answer=null,made=null}={})=>{b.parentElement.querySelector('.workflow-pattern-note')?.remove();const note=text=>b.parentElement.append(el('p',text,'workflow-pattern-note'));
      b.textContent=label;if(blocker){b.disabled=true;note('Not offered: '+blocker);return;}
      if(!answer){b.disabled=true;note('Asking the owner’s execution check about the result…');return;}
      if(answer.unavailable){b.textContent='Check first';b.disabled=true;b.setAttribute('aria-label',label+': check first');note(label+': the owner’s execution check could not be read for the result. '+answer.unavailable);return;}
      b.removeAttribute?.('aria-label');b.disabled=answer.support!=='SUPPORTED_CONFIGURATION';if(b.disabled)note('Not offered: '+patternSentence(answer,made));};
    const judge=(kind,b,label,choice)=>{const ticket=(b.patternTicket=(b.patternTicket||0)+1),now=fresh(),draft=bodyOf(now);if(!now||!draft)return;
      const blocker=workflowPatternBlocker(draft,kind,choice);if(blocker)return show(b,label,{blocker});
      let made;try{made=workflowPatternResult(draft,workflowPatternIntent(kind,{...choice,ids:idsFor(kind,choice)}));}catch(error){return show(b,label,{blocker:error.message});}
      const entry=patternAnswer(now,made);if(entry.value)return show(b,label,{answer:entry.value,made});show(b,label);
      entry.promise.then(answer=>{if(alive&&b.isConnected!==false&&b.patternTicket===ticket)show(b,label,{answer,made});});};
    // a press asks the owner about the draft as it now is (the answer already read for that exact draft is reused) and applies nothing on a refusal
    const press=async(kind,b,label,choice,before=()=>{})=>{const now=fresh(),draft=bodyOf(now);if(!now||!draft)return;const ticket=(b.patternTicket=(b.patternTicket||0)+1);
      const blocker=workflowPatternBlocker(draft,kind,choice);if(blocker)return show(b,label,{blocker});
      const ids=idsFor(kind,choice),intent=workflowPatternIntent(kind,{...choice,ids});let made;try{made=workflowPatternResult(draft,intent);}catch(error){return show(b,label,{blocker:error.message});}
      const entry=patternAnswer(now,made),answer=entry.value||await entry.promise;if(!alive||b.patternTicket!==ticket)return;
      if(answer.unavailable||answer.support!=='SUPPORTED_CONFIGURATION')return show(b,label,{answer,made});
      const again=fresh();if(!again||!equal(bodyOf(again),draft))return judge(kind,b,label,choice);
      before();patternIds=null;const result=await edit(again,intent);if(result)await act({type:'step',id:selectFor(kind,ids)});};
    const row=(kind,control,label,choice,extra=[],before)=>{const line=el('div','','workflow-pattern');const b=declare(button(label,()=>press(kind,b,label,choice(),before)),control,step.id);line.append(...extra,b);box.append(line);judge(kind,b,label,choice());return b;};
    row('review','workflow:pattern-review','Add a review of this step',()=>({step:step.id}));
    // reciprocal review: the chosen step and another step, or a copy of the chosen step; the owner's preview says whether the pair runs
    const partners=body.steps.filter(row=>row.id!==step.id),wrap=el('label','Paired with'),partner=declare(el('select'),'workflow:pattern-partner',step.id);partner.setAttribute('aria-label','Paired with');
    for(const [value,text]of [['','A copy of this step'],...partners.map(row=>[row.id,row.title||row.id])]){const option=el('option',text);option.value=value;partner.append(option);}wrap.append(partner);
    const pair=()=>({step:step.id,partner:partner.value||null});
    const reciprocal=row('reciprocal','workflow:pattern-reciprocal','Make these two review each other',pair,[wrap]);
    partner.onchange=()=>judge('reciprocal',reciprocal,'Make these two review each other',pair());
    // a synthesis: the steps it reads are chosen here; this choice lives only on the screen until the button is pressed
    if(!patternReads||patternReads.selection!==state.selection.id||patternReads.step!==step.id)patternReads={selection:state.selection.id,step:step.id,ids:new Set([step.id])};
    const reads=el('fieldset','','workflow-pattern-reads');reads.append(el('legend','The synthesis reads'));
    const chosen=()=>({reads:body.steps.map(row=>row.id).filter(id=>patternReads?.ids.has(id))});
    let synthesis=null;
    for(const other of body.steps){const label=el('label'),check=declare(el('input'),'workflow:pattern-reads',other.id);check.type='checkbox';check.checked=patternReads.ids.has(other.id);check.onchange=()=>{if(check.checked)patternReads.ids.add(other.id);else patternReads.ids.delete(other.id);judge('synthesis',synthesis,'Add a synthesis that reads these',chosen());};label.append(check,el('span',title(other.id)));reads.append(label);}
    synthesis=row('synthesis','workflow:pattern-synthesis','Add a synthesis that reads these',chosen,[reads],()=>{patternReads=null;});
    place.append(box);
  }
  function paintList(place,state,body,selected,{readOnly=false,states=null,onSelect=null}={}){const list=el('ol','','workflow-step-list');list.setAttribute('aria-label',readOnly?'Recorded run steps':'Workflow steps');
    const depth=step=>{let n=0,cursor=step,seen=new Set();while(cursor?.parent_id&&!seen.has(cursor.id)){seen.add(cursor.id);n++;cursor=body.steps.find(row=>row.id===cursor.parent_id);}return n;};
    for(const step of body.steps){const row=el('li'),open=button(step.title||step.id,()=>readOnly?onSelect?.(step.id):act({type:'step',id:step.id}));open.dataset.node='list:'+step.id;if(!readOnly)declare(open,'workflow:list-step',step.id);open.setAttribute('aria-current',step.id===selected?'step':'false');open.onkeydown=event=>{const keys=['ArrowDown','ArrowUp','Home','End'];if(!keys.includes(event.key))return;event.preventDefault();const nodes=[...list.querySelectorAll('button:not(:disabled)')],at=nodes.indexOf(open),next=event.key==='Home'?0:event.key==='End'?nodes.length-1:Math.max(0,Math.min(nodes.length-1,at+(event.key==='ArrowDown'?1:-1)));nodes[next]?.focus();};row.style.paddingInlineStart=depth(step)*16+'px';row.append(open,el('span',' · '+(step.assignment?.role||'No role')+(step.parent_id?' · inside '+labelFor(body,step.parent_id):''),'workflow-step-role'));if(readOnly){const fact=states.get(step.id);row.dataset.runState=fact?.state||'unselected';open.disabled=!fact?.read;open.dataset.control='workflow:run-step';open.dataset.controlOwner='list:'+step.id;row.append(el('span',' · '+(fact?.state?ownerStateWord('dispatch-child',fact.state).words:'Not selected for this run'),'workflow-node-state'));}list.append(row);}place.append(list);
    if(readOnly)return;
    place.append(el('p','Design only: control means intended order, data means intended input, feedback means intended revision. The execution preview must admit the actual pattern. No drawn edge proves a delivered message.','workflow-hint'));
    const relations=el('details','','workflow-relations-panel');relations.append(declare(el('summary','Relations · '+body.edges.length),'workflow:relations'));const edges=el('ul','','workflow-relations');for(const edge of body.edges){const li=el('li');li.append(el('span',labelFor(body,edge.from)+' → '+labelFor(body,edge.to)+' · '+edge.kind),declare(button('Remove relation from '+labelFor(body,edge.from)+' to '+labelFor(body,edge.to),()=>edit(state,{type:'remove-edge',id:edge.id})),'workflow:relation-remove',edge.id));edges.append(li);}relations.append(edges);place.append(relations);
  }
  // A run's recorded step (the app-run read's step_detail): its result, conversation, continuation, earlier attempts,
  // typed return and exact data. Painted inside the river's step card when the run has a river (one card per step), or
  // as the inspector beside the drawing when the owner issued no river. Returns {conversation} for the river card.
  function paintRunStep(place,state,body,run,{inCard=false}={}){
      const step=run.step_detail;
      if(!step){if(!inCard)place.append(el('h2','Recorded step'),el('p','Choose a selected step to inspect its recorded result and conversation.'));return null;}
      const stepState=ownerStateWord('dispatch-child',step.state);if(!inCard)place.append(el('p','Recorded step · read only','workflow-eyebrow'),el('h2',step.title||step.step_id),el('p',(step.assignment_role||'Assigned role')+' · '+stepState.shape+' '+stepState.words));
      const attempt=step.current_attempt;
      if(attempt)place.append(el('p',attempt.observed?'Current attempt · '+stepState.words:'Current attempt is not observed · '+ownerStateWord('attempt-phase',attempt.phase).words,'workflow-qualification'));
      const continuation=step.continue_action;
      if(step.role==='judge'||step.assignment_role==='adversary'){
        if(continuation?.available&&continuation.permitted){const next=button('Prepare review continuation message',()=>continueInConversation(continuation,state).catch(error=>{notice.textContent=error.message;}));next.dataset.action='continue-review';next.dataset.control='workflow:run-continue';next.dataset.controlOwner=step.step_id;place.append(next);}
        else if(continuation?.reason)place.append(el('p','Review continuation unavailable: '+continuation.reason,'workflow-hint'));
      }
      if(step.continuation_request){const receipt=step.continuation_request;place.append(el('p','Continuation acknowledgement: '+ownerStateWord('continuation-effect',receipt.effect).words+(receipt.effect==='UNKNOWN'?'. Inspect the retained request; no new child is implied.':''),'workflow-hint'),exactDetails('Continuation receipt and exact recovery read',receipt,'workflow:run-exact'));}
      const previous=step.attempt_history||[];
      if(previous.length){const history=el('details','','workflow-attempt-history'),historySummary=el('summary','Earlier attempts · '+previous.length);historySummary.dataset.control='workflow:run-attempts';historySummary.dataset.controlOwner=step.step_id;history.append(historySummary);for(const row of previous){const entry=el('div','','workflow-actions'),earlier=button('Read earlier public result · '+ownerStateWord('reply',row.reply_status).words,()=>fullResult(row.conversation).catch(error=>{notice.textContent=error.message;}));earlier.dataset.control='workflow:run-earlier-result';earlier.dataset.controlOwner=row.turn_id||row.conversation?.turn_id||step.step_id;entry.append(earlier);history.append(entry);}place.append(history);}
      for(const retained of step.reused_outputs||[]){const output=retained.output;const text='Retained worker output · '+(retained.title||retained.packet);if(output?.read?.http?.url){const link=el('a',text);link.href=output.read.http.url;link.target='_blank';link.rel='noopener';link.dataset.control='workflow:run-retained-output';link.dataset.controlOwner=retained.packet||text;place.append(link);}else place.append(el('p',text,'workflow-hint'));}
      if(step.conversation){const actions=el('div','','workflow-actions'),result=button('Read full public result and actions',()=>fullResult(step.conversation).catch(error=>{notice.textContent=error.message;})),conversation=button('Open step conversation',()=>openConversation(step.conversation).catch(error=>{notice.textContent=error.message;}));result.dataset.action='full-result';conversation.dataset.action='step-conversation';result.dataset.control='workflow:run-step-result';conversation.dataset.control='workflow:run-step-conversation';result.dataset.controlOwner=conversation.dataset.controlOwner=step.step_id;actions.append(result,conversation);place.append(actions,el('p','Open this step’s conversation to send a message or stop it.','workflow-hint'));}
      else place.append(el('p',step.binding?.reason||'No actual conversation binding is reported.'));
      const typed=step.typed_return_read;if(typed?.http?.url){const link=el('a','Open exact typed return');link.href=typed.http.url;link.target='_blank';link.rel='noopener';link.dataset.control='workflow:run-typed-return';link.dataset.controlOwner=step.step_id;place.append(link);}else if(typed)place.append(el('p','Typed return is not observed.','workflow-hint'));
      const saved=body.steps.find(row=>row.id===step.step_id);if(saved)place.append(exactDetails('Consumed role and full instructions',saved.assignment,'workflow:run-exact'));
      if(step.return_errors?.length)place.append(exactDetails('Typed return issues · '+step.return_errors.length,step.return_errors,'workflow:run-exact'));place.append(exactDetails('Step observation and exact reads',step,'workflow:run-exact'));return {conversation:!!step.conversation};
  }
  function paintInspector(place,state,body,selected,{run=null}={}){
    if(run){paintRunStep(place,state,body,run);return;}
    // THE COLUMN for the selected step (wave 12): its role, its settings with where each comes from, what it reads and
    // hands on, and its instructions, in that order beside the drawing; every part is shown at once, the four buttons jump.
    place.classList.add('workflow-settings-column');
    const step=body.steps.find(row=>row.id===selected);if(!step){place.append(el('p','Selected step','workflow-eyebrow'),el('h2','No step chosen'),el('p','Choose a step on the drawing to set its role, settings, what it reads and its instructions.'));const defaults=el('section','','workflow-inspector-panel');defaults.dataset.inspectorPanel='settings';sectionHead(defaults,'Workflow defaults');paintWorkflowDefaults(defaults,state,body);place.append(defaults);return;}
    place.append(el('p','Selected step','workflow-eyebrow'),el('h2',step.title||'Untitled step'));
    const tabs=el('nav','','workflow-inspector-tabs');tabs.setAttribute('aria-label','Jump to a part of this step');
    const panels=new Map(),headings={step:'Role',settings:'Provider and model',connections:'Reads and hands on',instructions:'Instructions'};
    for(const [key,label]of [['step','Step'],['settings','Settings'],['connections','Connections'],['instructions','Instructions']]){
      const panel=el('section','','workflow-inspector-panel');panel.dataset.inspectorPanel=key;panels.set(key,panel);sectionHead(panel,headings[key],key==='step'?['role']:key==='connections'?['handover']:[]);
      const tab=button(label,()=>{if(!alive||place!==inspectorRegion||place.isConnected===false)return;const fresh=port.snapshot(),body=fresh.draft?.definition||fresh.read?.value?.definition;if(fresh.selection?.id!==state.selection?.id||fresh.step!==selected||!body)return;inspectorTab=key;const capture=port.capture();paintEpoch++;remember(capture);versionStatus(fresh);place.replaceChildren();paintInspector(place,fresh,body,fresh.step);updateEditorState(fresh);updateTechnical(fresh,capture);restoreFocus({action:'inspector-'+key});place.querySelector?.('[data-inspector-panel="'+key+'"]')?.scrollIntoView?.({block:'nearest'});});tab.setAttribute('aria-current',inspectorTab===key?'page':'false');tab.dataset.action='inspector-'+key;declare(tab,'workflow:inspector-part',key);tabs.append(tab);
    }
    place.append(tabs,...panels.values());const stepPanel=panels.get('step'),instructions=panels.get('instructions'),settings=panels.get('settings'),connections=panels.get('connections');
    field(stepPanel,'Step name',step.title,value=>edit(state,{type:'step',id:step.id,fields:{title:value}},true),{name:'Step title'});
    field(stepPanel,'Role',step.assignment?.role,value=>edit(state,{type:'assignment',id:step.id,fields:{role:value}},true));
    declare(select(stepPanel,'Nest inside',[['','Top level'],...body.steps.filter(row=>row.id!==step.id).map(row=>[row.id,row.title||row.id])],step.parent_id,parent_id=>edit(state,{type:'nest',id:step.id,parent_id})),'workflow:stage-nest',step.id);
    stepPanel.append(el('p','Nesting groups steps and inherits declared settings. It does not spawn a child workflow, inherit a transcript or grant more authority.','workflow-hint'));const positioning=el('details','','workflow-positioning'),positionSummary=declare(el('summary','Canvas position'),'workflow:stage-position',step.id);positioning.append(positionSummary);const moves=el('div','','workflow-actions workflow-nudges'),position=graphLayout(body).positions.get(step.id);
    for(const [label,dx,dy]of [['Move left',-24,0],['Move up',0,-24],['Move down',0,24],['Move right',24,0]]){const b=button(label,()=>edit(state,{type:'move',id:step.id,x:Math.max(CARD.w/2,position.x+dx),y:Math.max(CARD.h/2,position.y+dy)}));b.dataset.action=label;declare(b,'workflow:stage-nudge',label);moves.append(b);}positioning.append(moves);stepPanel.append(positioning);
    paintSettingLineage(settings,state,step);
    const own=settingChoices(settings,state,body,step);declare(field(own,'Input policy',step.assignment?.settings?.input_policy||'',value=>edit(state,{type:'setting',id:step.id,key:'input_policy',value},true),{name:'setting-input_policy'}),'workflow:setting-step','input_policy');own.append(el('p','Inherit leaves this step’s value unset. Save to resolve the role defaults.','workflow-hint'));
    paintWorkflowDefaults(settings,state,body);
    // what it receives and hands on: each arrow in the execution check's own words for its kind (workflowConfiguredFlow)
    const flow=new Map(workflowConfiguredFlow(body).map(row=>[row.id,row])),into=body.edges.filter(row=>row.to===step.id).map(row=>flow.get(row.id)),out=body.edges.filter(row=>row.from===step.id).map(row=>flow.get(row.id));
    connections.append(el('p','Receives: '+(into.length?into.map(row=>row.from+' ('+row.meaning+')').join('; '):'no arrow comes in')+'. Hands on: '+(out.length?out.map(row=>row.to+' ('+row.meaning+')').join('; '):'no arrow goes out')+'.','workflow-reads-line'));
    field(instructions,'Instructions',step.assignment?.instructions,value=>edit(state,{type:'assignment',id:step.id,fields:{instructions:value}},true),{tag:'textarea',rows:15});
    instructions.append(el('p','Applies to this step. Group instructions are kept separately.','workflow-hint'));if(step.assignment?.role!=='group')paintRoleDelivery(connections,state,step);
    const relation=el('form','','workflow-connect');const to=declare(select(relation,'Connect to',body.steps.map(row=>[row.id,row.title||row.id]),'',()=>{}),'workflow:relation-add','to'),kind=declare(select(relation,'Relation kind',[['control','Control'],['data','Data'],['feedback','Feedback']],'control',()=>{}),'workflow:relation-add','kind');relation.append(declare(el('button','Add relation'),'workflow:relation-add','add'));relation.onsubmit=event=>{event.preventDefault();edit(state,{type:'connect',from:step.id,to:to.value,kind:kind.value});};connections.append(relation);
    for(const name of ['inputs','outputs']){
      const values=step[name]||[],complex=values.some(value=>typeof value!=='string'),key=step.id+':'+name,held=state.draft?.text_fields?.[key];
      field(connections,name+' ('+(complex?'JSON array':'one per line')+')',held??(complex?json(values):values.join('\n')),value=>{try{const parsed=complex?JSON.parse(value):textLines(value);if(!Array.isArray(parsed))throw Error('Use an array.');act({type:'text',name:key,value,invalid:false});edit(state,{type:'step',id:step.id,fields:{[name]:parsed}},true);}catch(error){act({type:'text',name:key,value,invalid:true});notice.textContent=name+': '+error.message+' The full text is retained.';}},{tag:'textarea',name,rows:3});
    }
    // Whether the result passes forward by itself or waits: the owner's only field is the workflow's
    // run_policy.advance, which applies after every step; it is shown here and says so.
    const forward=el('section','','workflow-inspector-panel');forward.dataset.inspectorPanel='forward';sectionHead(forward,'When its result passes forward');
    if(body.run_policy){
      const advance=select(forward,'After this step responds',Object.entries(ADVANCE_WORDS),body.run_policy.advance,value=>{const fresh=port.snapshot(),definition=fresh.draft?.definition||fresh.read?.value?.definition;if(fresh.selection?.id!==state.selection.id||!definition?.run_policy)return;edit(fresh,{type:'fields',fields:{run_policy:{...definition.run_policy,advance:value}}},true);});advance.dataset.field='stage-advance';declare(advance,'workflow:policy-advance','step');
      forward.append(el('p','This setting belongs to the whole workflow: the owner keeps one for every step.','workflow-hint'));
    }else forward.append(el('p','This workflow has no review policy, so the owner holds no setting for whether a result passes forward by itself or waits for you.','workflow-hint'));
    const stepIn=el('section','','workflow-inspector-panel');stepIn.dataset.inspectorPanel='step-in';sectionHead(stepIn,'Where you can step in');const points=el('ul','','workflow-step-in');
    const policy=body.run_policy;if(policy?.advance==='manual')points.append(el('li','After each response: the next step waits for your decision.'));if(policy?.advance==='automatic-review')points.append(el('li','After a response: review starts by itself. You can stop the run from Runs.'));if(policy?.apply==='human')points.append(el('li','The manuscript change: you apply it yourself; no step applies it.'));
    points.append(el('li','While it runs: open this step’s session from Runs to send it a message or stop it.'),el('li','Before it runs: Check execution and Save definition are yours. Saving starts nothing.'));stepIn.append(points);place.append(forward,stepIn);
  }
  async function go(url){remember();if(!stored)throw Error('Keep this page open: its workflow return could not be stored.');safeNavigation=true;try{if(typeof url==='function')await url();else await navigate(url);}catch(error){safeNavigation=false;throw error;}}
  async function requestNavigation(raw,{opener=null}={}){
    const here=new URL(globalThis.location?.href||'http://local/project'),url=new URL(raw,here),ticket=++navigationEpoch;
    if(url.origin!==here.origin||url.pathname!=='/project'){notice.textContent='This is not an application destination. Your workflow stays open.';return false;}
    const destination=url.pathname+url.search+url.hash;
    return requestReturn(()=>navigate(destination),{opener});
  }
  async function requestReturn(destination,{opener=null}={}){
    const ticket=++navigationEpoch;
    if(!port.hasUnresolved()){try{await go(destination);return true;}catch(error){notice.textContent=error.message;return false;}}
    const prompt=el('span','','workflow-leave-choice');prompt.append(el('span','Keep this workflow draft and return? Your original save request will not be resent. '));
    const leave=button('Keep draft and leave',async()=>{if(!alive||ticket!==navigationEpoch)return;try{await go(destination);}catch(error){if(alive&&ticket===navigationEpoch)notice.textContent=error.message;}}),stay=button('Stay in workflow',()=>{if(!alive||ticket!==navigationEpoch)return;++navigationEpoch;notice.replaceChildren();if(opener?.isConnected!==false)opener?.focus?.();});
    prompt.append(leave,stay);notice.replaceChildren(prompt);stay.focus?.();return false;
  }

  function openConversation(conversation){
    const url=new URL(conversation?.project_url||'',globalThis.location?.href||'http://local/project');
    if(url.origin!==new URL(globalThis.location?.href||'http://local/project').origin||url.pathname!=='/project'||url.searchParams.get('corpus')!==conversation.project||url.searchParams.get('session')!==conversation.session_id)throw Error('The owner issued no matching conversation destination.');
    url.searchParams.set('app_return',workflowReturnURL(globalThis.location?.href));return go(url.pathname+url.search);
  }
  async function useConversation(action){if(onCompose)return onCompose(action);return go(workflowConversationURL(action,globalThis.location?.href));}
  async function prepareApp(state,fields){
    const owner=state.read?.value,key=state.selection.id,reference=owner.reference,prior=state.context.app_intent;
    const request_id=prior&&JSON.stringify(prior.fields)===JSON.stringify(fields)&&JSON.stringify(prior.reference)===JSON.stringify(reference)?prior.request_id:crypto.randomUUID();
    await act({type:'context',fields:{app_intent:{reference,fields,request_id}}});const ticket=++composeEpoch;
    let action;try{action=await composeWorkflowRequest(owner,{request_id,...fields},{request});}catch(error){const current=port.snapshot();if(!alive||ticket!==composeEpoch||current.selection?.id!==key)return;const issues=error.result?.obligations||[];error.message=[error.message,...issues.map(issue=>{const step=owner.definition.steps.find(row=>row.id===issue.step_id);return (step?.title||issue.step_id||'Selected slice')+': '+(issue.message||issue.code||'Unsupported input');})].join('\n');throw error;}
    const current=port.snapshot();if(!alive||ticket!==composeEpoch||current.selection?.id!==key||JSON.stringify(current.read?.value?.reference)!==JSON.stringify(reference))return;
    await useConversation(action);
  }
  async function startInConversation(action,state){
    const current=runPort.snapshot().selection,ticket=++composeEpoch;
    const resolved=await readWorkflowConversationAction(action.project,action.read.request,request);
    if(!alive||ticket!==composeEpoch||JSON.stringify(runPort.snapshot().selection)!==JSON.stringify(current)||!runPort.matches(port.snapshot().read?.value))return;
    await useConversation(resolved);
  }
  async function continueInConversation(action,state){
    const selected=runPort.snapshot().selection,owner=state.read.value,prior=state.context.continuation_intent;
    const identity={reference:owner.reference,work_id:selected.work_id,step_id:selected.step_id,base:action.native.payload};
    const request_id=prior&&JSON.stringify(prior.identity)===JSON.stringify(identity)?prior.request_id:crypto.randomUUID();
    await act({type:'context',fields:{continuation_intent:{identity,request_id}}});const ticket=++composeEpoch;
    const resolved=await composeFailedReviewRequest(action,request_id,{request});
    if(!alive||ticket!==composeEpoch||JSON.stringify(runPort.snapshot().selection)!==JSON.stringify(selected)||!runPort.matches(port.snapshot().read?.value))return;
    await useConversation(resolved);
  }
  async function fullResult(conversation){
    const selection=runPort.snapshot().selection,fresh=()=>alive&&appOpen&&runPort.matches(port.snapshot().read?.value)&&JSON.stringify(runPort.snapshot().selection)===JSON.stringify(selection);
    const {openSavedTurn}=await import('./workspace-material.mjs');if(!fresh())return;
    await openSavedTurn({project:conversation.project,turnId:conversation.turn_id,ownerRead:conversation.public_content_read,request,isCurrent:fresh,onConversation:id=>{if(id!==conversation.session_id)throw Error('Reinspect the owner before opening a different conversation.');return openConversation(conversation);}});
  }
  function paintAppPreparation(parent,state){
    const owner=state.read.value,action=owner.actions?.use_in_conversation;
    const form=el('form','','workflow-prepare');form.append(el('h3','Prepare an agent run'),el('p','Use this saved version in an author conversation. Review the prepared message, then Send. Start is a separate request.','workflow-hint'));
    if(state.draft)form.append(el('p','Your unsaved definition draft stays here. This request uses the saved version shown above.','workflow-qualification'));
    const savedSteps=owner.definition.steps,choices=el('fieldset','','workflow-prepare-steps');choices.append(el('legend','Saved steps to prepare'));
    const selected=state.context.app_step_ids||[],checks=[];
    for(const step of savedSteps){const label=el('label'),check=declare(el('input'),'workflow:prepare-step','agent:'+step.id);check.type='checkbox';check.value=step.id;check.checked=selected.includes(step.id);checks.push(check);label.append(check,document.createTextNode((step.title||step.id)+' · '+step.assignment.role));choices.append(label);check.onchange=()=>act({type:'context',fields:{app_step_ids:checks.filter(c=>c.checked).map(c=>c.value)}});}
    form.append(choices);const fields=el('div','','workflow-prepare-fields');
    const goal=field(fields,'App completion goal',state.context.app_goal||'',value=>act({type:'context',fields:{app_goal:value}}),{tag:'textarea',rows:3});
    const fan=field(fields,'Maximum parallel children',state.context.app_fan_out||'2',value=>act({type:'context',fields:{app_fan_out:value}}));fan.type='number';fan.min='1';fan.max='8';form.append(fields);
    const allowed=action?.allowed_inputs||action?.required_inputs||[];
    if(allowed.includes('inputs')){const group=el('fieldset');group.append(el('legend','Explicitly selected evidence inputs'));const selectedInputs=state.context.app_inputs||[],offered=inputChoices().map(row=>({descriptor:row.descriptor||row,label:row.label||row.reference?.identity?.node||row.reference?.identity?.path||'Inspected input'}));for(const descriptor of selectedInputs)if(!offered.some(row=>JSON.stringify(row.descriptor)===JSON.stringify(descriptor)))offered.push({descriptor,label:'Previously selected input'});
      offered.forEach((row,index)=>{const label=el('label',row.label),check=declare(el('input'),'workflow:prepare-input',index);check.type='checkbox';check.checked=selectedInputs.some(value=>JSON.stringify(value)===JSON.stringify(row.descriptor));check.onchange=()=>{const values=port.snapshot().context.app_inputs||[],next=values.filter(value=>JSON.stringify(value)!==JSON.stringify(row.descriptor));if(check.checked)next.push(structuredClone(row.descriptor));act({type:'context',fields:{app_inputs:next}});};label.prepend(check);group.append(label);});if(!offered.length)group.append(el('p','Include exact object or source-window readings in the research workspace, then return here. No evidence is included automatically.','workflow-hint'));form.append(group);}
    if(allowed.includes('selection')&&manuscriptChoices){
      const group=el('fieldset');group.append(el('legend','Manuscript to revise'));const selected=state.context.app_target||null,rows=manuscriptChoices().map(row=>structuredClone(row));
      if(selected&&!rows.some(row=>row.id===selected.id&&JSON.stringify(row.selection)===JSON.stringify(selected.selection)))rows.push({...selected,label:(selected.label||'Earlier inspected target')+' · retained selection'});
      const choice=declare(el('select'),'workflow:prepare-target');choice.setAttribute('aria-label','Manuscript to revise');choice.required=true;const empty=el('option','Choose the document or section to revise…');empty.value='';choice.append(empty);
      rows.forEach((row,i)=>{const option=el('option',row.label);option.value=String(i);choice.append(option);});choice.value=selected?String(rows.findIndex(row=>row.id===selected.id&&JSON.stringify(row.selection)===JSON.stringify(selected.selection))):'';
      const inspect=declare(button('Inspect selected manuscript',()=>{const held=port.snapshot().context.app_target,target=rows.find(row=>row.id===held?.id&&JSON.stringify(row.selection)===JSON.stringify(held.selection))||held;if(target?.read&&onInspectRead)Promise.resolve(onInspectRead(target.read,target.read_title||target.label)).catch(error=>{if(alive)notice.textContent=error.message;});},{disabled:!selected?.read||!onInspectRead}),'workflow:inspect-manuscript');
      choice.onchange=()=>{const target=choice.value===''?null:rows[Number(choice.value)];act({type:'context',fields:{app_target:target}});inspect.disabled=!target?.read||!onInspectRead;};group.append(choice,inspect,el('p','The target and its observed source basis are retained separately from the selected evidence. Choosing a new target is explicit.','workflow-hint'));
      if(!rows.length)group.append(el('p','This context has no owner-issued editable manuscript choices. Choose an existing project with a registered editable manuscript.','workflow-qualification'));form.append(group);
    }
    const send=declare(el('button',action?.label||'Prepare in conversation'),'workflow:agent-prepare-submit');send.type='submit';send.disabled=!action?.available||!action?.permitted;form.append(send);
    if(action?.reason)form.append(el('p',action.reason,'workflow-hint'));
    form.onsubmit=event=>{event.preventDefault();prepareApp(port.snapshot(),{step_ids:checks.filter(c=>c.checked).map(c=>c.value),goal:goal.value,fan_out_max:Number(fan.value),...(allowed.includes('inputs')?{inputs:structuredClone(port.snapshot().context.app_inputs||[])}:{}),...(allowed.includes('selection')&&manuscriptChoices&&port.snapshot().context.app_target?{selection:structuredClone(port.snapshot().context.app_target.selection)}:{})}).catch(error=>{if(alive)notice.textContent=error.message;});};
    parent.append(form);
  }
  function paintAppRuns(parent,state){
    const owner=state.read?.value,observed=runPort.snapshot(),selection=observed.selection;
    const panel=el('section','','workflow-prepare workflow-runs-panel');panel.append(el('h3','Agent runs for this saved version'));
    const controls=el('div','','workflow-actions'),back=button('Return to workflow',()=>{workspaceView='design';appOpen=false;paint({...port.snapshot(),event:'view'});restoreFocus(editorFocus);}),refresh=button('Refresh status',()=>runPort.refresh().catch(error=>{notice.textContent=error.message;}));back.dataset.action='return-workflow';refresh.dataset.action='refresh-run';back.dataset.control='workflow:run-return';refresh.dataset.control='workflow:run-refresh';controls.append(back,refresh);
    if(selection?.kind!=='list'){const list=button('Back to runs',()=>runPort.open(owner,'list',owner.app_runs_read).catch(error=>{notice.textContent=error.message;}));list.dataset.action='back-runs';list.dataset.control='workflow:runs-back';controls.prepend(list);}
    // An opened run: these three controls sit in the compact line above it (P5); the run list keeps its heading and row.
    const compact=selection?.kind!=='list'?detail.querySelector('.workflow-run-compact-actions'):null;if(compact){panel.children[0].remove();compact.append(...controls.children);}else panel.append(controls);parent.append(panel);
    if(!runPort.matches(owner)){panel.append(el('p','Choose Agent runs to inspect this exact saved version.'));return;}
    const value=observed.read?.value;
    if(observed.read?.io==='loading')panel.append(el('p','Reading recorded dispatch facts…','workflow-hint'));
    if(observed.read?.io==='error')panel.append(el('p','Observation unavailable: '+observed.read.error+'. The prior observation and draft are retained.','error'));
    if(!value)return;
    if(selection.kind==='list'){
      if(!value.items.length)panel.append(el('p','No agent run is recorded for this saved version.'));
      else panel.append(el('p',(Number.isSafeInteger(value.total)?value.total+' recorded run'+(value.total===1?'':'s')+' for this saved version. ':'')+'Runs whose task is not finished are listed first. Open one to see it drawn on the stages.','workflow-hint'));
      for(const item of workflowRunsOrder(value.items)){const card=el('div','','workflow-result'),open=button('Open agent run · '+(item.recorded_status?taskStateChips({lifecycle:{status:item.recorded_status}})[0]?.label:'status not reported'),()=>runPort.open(owner,'run',item.read,{work_id:item.work_id}).catch(error=>{notice.textContent=error.message;}));open.dataset.control='workflow:runs-open';open.dataset.controlOwner=item.work_id;open.dataset.recordedStatus=item.recorded_status||'';card.append(open);panel.append(card);}
      paintObservations(panel,owner,value.items);paintInterventions(panel,port.snapshot());
      if(value.next)panel.append(button('More agent runs',()=>runPort.open(owner,'list',value.next).catch(error=>{notice.textContent=error.message;})));return;
    }
    if(value.schema_version==='laplace.research-workflow-run/1'){
      // A research run keeps its native view, read only here: its actions and Stop stay with the research workspace that owns the Work. Nothing is converted to an app run.
      const pane=el('div','','workflow-research-run'),epoch=paintEpoch;panel.append(el('p','Research workflow run, read only here. Its actions and Stop are in the research workspace that owns this Work.','workflow-qualification'),pane);
      import('./research-workbench-run.mjs').then(({renderWorkflowRun})=>{if(alive&&epoch===paintEpoch)renderWorkflowRun(pane,{...value,actions:{}},{isCurrent:()=>alive&&epoch===paintEpoch,onRead:(handle,label)=>{if(onInspectRead)Promise.resolve(onInspectRead(handle,label)).catch(error=>{if(alive)notice.textContent=error.message;});else notice.textContent='No reader is attached here for '+label+'.';}});}).catch(error=>{if(alive)notice.textContent=error.message;});
      return;
    }
    const consumed=observed.read.definition?.definition;
    // The run's facts in words (owner state words, preparation, Start, its conversation) follow its drawing.
    const paintRunFacts=()=>{
      const facts=value.observation||{},summary=el('div','','workflow-version-summary'),work=facts.recorded_status?taskStateChips({lifecycle:{status:facts.recorded_status}})[0]?.label:'not reported';
      const execution=el('span','Execution: '+ownerStateWord('run-execution',facts.execution_state).words),review=el('span','Review: '+ownerStateWord('run-review',facts.review_state).words),task=el('span','Task: '+work),snapshot=el('p',facts.observed_at?'Snapshot observed '+new Date(facts.observed_at*1000).toLocaleString()+'. Refresh to inspect again.':'Observation time not reported.','workflow-hint');summary.append(execution,review,task);panel.append(summary,snapshot);runWords={...runWords,execution,review,task,snapshot};
      const parentFacts=el('details'),parentSummary=el('summary','Preparation and launch');parentSummary.dataset.control='workflow:run-preparation';parentSummary.dataset.controlOwner=value.work_id;parentFacts.append(parentSummary,el('p','Prepared in '+value.parent.prepared_by.session_id+' by turn '+value.parent.prepared_by.turn_id),el('p',value.parent.launched_by?'Launched in '+value.parent.launched_by.session_id+' by turn '+value.parent.launched_by.turn_id:'No launch parent is recorded.'),exactDetails('Consumed settings and carrier contract',{settings:value.settings,carrier:value.carrier,deadline:value.deadline},'workflow:run-exact'));panel.append(parentFacts);
      const start=value.actions?.use_in_conversation;if(start?.permitted){const next=button('Prepare start message',()=>startInConversation(start,state).catch(error=>{notice.textContent=error.message;}));next.dataset.control='workflow:run-start';next.dataset.controlOwner=value.work_id;panel.append(next);}else if(start?.reason)panel.append(el('p',start.reason,'workflow-hint'));
      if(value.parent?.conversation?.project_url){const parent=button('Open original conversation',()=>openConversation(value.parent.conversation).catch(error=>{notice.textContent=error.message;}));parent.dataset.control='workflow:run-parent';parent.dataset.controlOwner=value.work_id;panel.append(parent);}
      panel.append(el('p','Exact consumed saved version · '+(value.definition_currentness==='HISTORICAL'?'a newer saved version exists':'saved definition')+'. Your editor draft is retained separately.','workflow-qualification'));
    };
    // THE RUN HEADER (wave 11): its name and state, the river's byline, what waits on him, and Stop and Cancel exactly as
    // issued (workflowInterventions' stop row and the app run's cancel_dispatch offer, moved here, words unchanged).
    const header=el('header','','workflow-run-header'),runState=ownerStateWord('run-execution',value.observation?.execution_state);header.dataset.workflowRunHeader='';let runWords={};
    const title=el('div','','workflow-run-title'),stateLine=el('p',runState.shape+' Run '+runState.words.toLowerCase()+' · read '+(value.observation?.observed_at?riverClock(value.observation.observed_at*1000):'at an unreported time')+' (app-run read)','workflow-run-state');title.append(el('h3',consumed?.title||'Agent run'),stateLine);header.append(title);runWords.stateLine=stateLine;
    const riverOffer=value.observation_reads?.river;
    if(riverOffer&&value.work_id&&(!riverUI||riverUI.work_id!==value.work_id)){dropRiver();}
    if(riverOffer&&value.work_id&&!riverUI){
      const order=consumed?workflowStageLayout(consumed).order.map(step=>step.id):[],titles=Object.fromEntries((consumed?.steps||[]).map(step=>[step.id,step.title||step.id]));
      riverUI=mountWorkflowRiver(el('div'),{offer:riverOffer,run:value,order,titles,dependencies:value.prepared_dependencies,request,expected:{scope_id:owner.scope_id},isCurrent:()=>alive&&workspaceView==='runs'&&runPort.snapshot().read?.value?.work_id===value.work_id,
        openConversation:conversation=>openConversation(conversation),prepared:id=>runPort.snapshot().read?.value?.settings?.[id]?.values||null,
        onModel:(model,live)=>{const strip=runStrip;if(!strip||!model)return;updateRunWords(strip,strip.riverValue(),live);for(const [id,node]of strip.nodes){const step=(runPort.snapshot().read?.value?.steps||[]).find(row=>row.step_id===id),row=[...model.lanes.find(l=>l.step_id===id)?.rows||[]].at(-1);const fact=runFact(step,row,strip.riverValue(),runPort.snapshot().read?.value?.settings?.[id]?.values);const body=strip.body.steps.find(item=>item.id===id);if(body)fillRunNode(node,body,fact,live);}}});
      riverUI.work_id=value.work_id;
    }
    if(riverUI){riverUI.update({run:value});header.append(riverUI.byline,riverUI.waiting);}
    else header.append(el('p','The owner issued no observed-flow read for this run, so nothing here is re-read.','workflow-hint'));
    const stopRow=workflowInterventions({draft:state.draft,attempt:state.attempt,run:value}).find(row=>row.id==='stop'),stop=el('div','','workflow-run-stop-row');stop.dataset.intervention='stop';stop.append(el('strong',stopRow.label),el('span',' · '+(stopRow.available?'available now':'not available now')),el('p',stopRow.meaning,'workflow-hint'));if(stopRow.available)mountWorkflowRunStop(stop,{view:value,request,recovery:stopRecovery,isCurrent:()=>stop.isConnected!==false});header.append(stop);
    const cancel=value.actions?.cancel_dispatch;if(cancel)header.append(el('p',cancel.permitted?'Cancel dispatched work is available on this run’s Work view.':'Cancel dispatched work is not permitted now'+(cancel.reason?': '+cancel.reason:'.'),'workflow-hint'));
    panel.append(header);
    if(consumed){
      const dependencies=value.prepared_dependencies,available=dependencies?.status==='AVAILABLE',states=new Map((value.steps||[]).map(step=>[step.step_id,step]));
      const runBody={...consumed,steps:consumed.steps.map(({parent_id,...step})=>step),edges:available?dependencies.edges.map(edge=>({from:edge.prerequisite_step_id,to:edge.dependent_step_id,kind:'prepared'})):[]};
      // ONE card per step: a stage, a list row or a lane label reads the step's record (the app-run step read) and the
      // river's step card shows it (stepDetail paints paintRunStep into that card). Without a river the inspector does.
      const openStep=id=>{const step=states.get(id);if(step?.read){runFocus={node:view==='graph'?id:'list:'+id,work_id:value.work_id,step_id:id,reference:JSON.stringify(selection.reference)};runPort.open(owner,'step',step.read,{work_id:value.work_id,step_id:id}).catch(error=>{notice.textContent=error.message;});}};
      const choose=id=>{openStep(id);riverUI?.select('step:'+id,{quiet:true});};
      const stepDetail=(id,place)=>{const fresh=runPort.snapshot().read?.value;if(fresh?.step_detail?.step_id===id)return paintRunStep(place,state,consumed,fresh,{inCard:true});if(states.get(id)?.read)place.append(el('p','Reading this step’s recorded result…','workflow-hint'));return null;};
      riverUI?.update({run:value,stepDetail,onSelectStep:openStep});
      // The run on the workflow's own topology (the consumed saved definition and its own arrows), each stage with its
      // marks; the river (observed flow) under it re-reads itself and repaints these marks in place.
      const drawn=el('section','','workflow-run-topology');sectionHead(drawn,'This run on its steps',['stage'],'h3','workflow:run-explain');drawn.append(el('p','○ Planned: in the saved version this run used. Admitted: in this run’s prepared step list, with the owner’s state in words and its time. ● Observed: an attempt whose turn the owner recorded. Now: what the step’s host is doing at the river’s last read.','workflow-strip-legend'));
      const riverValue=()=>riverUI?.value||null,facts=new Map(consumed.steps.map(step=>{const row=riverValue()?.items?.filter(item=>item.step_id===step.id).at(-1);return [step.id,runFact(states.get(step.id),row,riverValue(),value.settings?.[step.id]?.values)];}).filter(([,fact])=>fact));
      const nodes=new Map();paintStrip(drawn,consumed,selection.step_id,{marks:facts,onSelect:choose,nodes,live:riverUI?riverUI.live:{}});runStrip={nodes,body:consumed,riverValue,panel,words:runWords};panel.append(drawn);
      if(riverUI)panel.append(riverUI.node);
      paintRunFacts();runStrip.words=runWords;
      const options={readOnly:true,states,onSelect:choose},grid=el('div','','workflow-grid workflow-run-grid'),map=el('section','','workflow-map'),inspector=el('section','','workflow-inspector'),tools=el('div','','workflow-actions workflow-view-tools');
      for(const [kind,label]of [['graph','Graph view'],['list','List view']]){const b=button(label,()=>{view=kind;userView=true;paint({...port.snapshot(),event:'view'});});b.dataset.action='run-view-'+kind;b.dataset.control='workflow:run-view';b.dataset.controlOwner=kind;b.setAttribute('aria-pressed',view===kind?'true':'false');tools.append(b);}map.append(tools);
      map.append(el('p',available?'Arrows show prepared execution dependencies. Authored containment and other relations are hidden.':'Prepared execution dependencies are unavailable: '+(dependencies?.reason||'The owner returned no qualified dependency mapping')+'. No execution arrows are inferred.','workflow-hint'));
      if(available){const relations=el('ul','','workflow-run-dependencies');relations.setAttribute('aria-label','Prepared execution dependencies');for(const edge of runBody.edges)relations.append(el('li',labelFor(consumed,edge.from)+' → '+labelFor(consumed,edge.to)));if(!runBody.edges.length)relations.append(el('li','The owner reports no prepared execution dependencies.'));map.append(relations);}
      if(view==='graph')paintGraph(map,state,runBody,selection.step_id,options);else paintList(map,state,runBody,selection.step_id,options);
      if(riverUI){grid.classList.add('workflow-run-single');grid.append(map);}else{paintInspector(inspector,state,consumed,selection.step_id,{run:value});grid.append(map,inspector);}panel.append(grid);paintInterventions(panel,port.snapshot(),value,{without:'stop'});if(riverUI?.value)updateRunWords(runStrip,riverUI.value,riverUI.live);
    }else{if(riverUI)panel.append(riverUI.node);paintRunFacts();panel.append(el('p','The exact consumed definition is unavailable; topology cannot be drawn.','workflow-hint'));}
    panel.append(exactDetails('Prepared definition, Work, plan and observation',{reference:value.reference,definition_read:value.definition_read,work:value.work,plan:value.plan,observation:value.observation},'workflow:run-exact'));
  }

  function updateEditorState(state){
    const owner=state.read?.value,body=state.draft?.definition||owner?.definition;if(!body||appOpen&&runPort.matches(owner))return;
    const draftHint=detail.querySelector('.workflow-effective-draft');if(draftHint)draftHint.hidden=!state.draft;
    const unresolved=['pending','uncertain'].includes(state.attempt?.status),save=detail.querySelector('[data-action="save"]'),prepare=detail.querySelector('[data-action="prepare"]'),compare=detail.querySelector('[data-action="compare"]'),discard=detail.querySelector('[data-action="discard"]');
    if(save)save.disabled=!state.draft||unresolved;if(prepare)prepare.disabled=!!state.draft||!owner?.actions?.prepare?.permitted||unresolved;if(compare)compare.disabled=!state.draft||state.selection.id.startsWith('local:');if(discard)discard.disabled=!state.draft;
    const heading=detail.querySelector('.workflow-heading');if(heading){heading.querySelector('h2').textContent=body.title||'Untitled workflow';updatePurpose(heading,body.description);const summary=heading.querySelector('.workflow-version-summary');if(summary?.children[0]){summary.children[0].textContent=savedLabel(owner);summary.children[0].className=state.draft?'':'workflow-saved';}if(summary?.children[1])summary.children[1].textContent=state.draft?'Unsaved changes':'Saved';}
    for(const node of detail.querySelectorAll('[data-node]')){const step=body.steps.find(row=>row.id===node.dataset.node.replace(/^list:/,''));if(!step)continue;const label=node.querySelector('.workflow-node-title');if(label){label.textContent=step.title||step.id;node.setAttribute('aria-label','Graph step '+(step.title||step.id));const role=node.querySelector('small');if(role)role.textContent=step.assignment?.role||'No role';}else{node.textContent=step.title||step.id;const role=node.parentElement?.querySelector('.workflow-step-role');if(role)role.textContent=' · '+(step.assignment?.role||'No role')+(step.parent_id?' · inside '+labelFor(body,step.parent_id):'');}}
    for(const node of detail.querySelectorAll('.workflow-stage-node')){const step=body.steps.find(row=>row.id===node.dataset.stage);if(!step)continue;const title=node.querySelector('.workflow-stage-title'),role=node.querySelector('.workflow-stage-role');if(title)title.textContent=step.title||step.id;if(role)role.textContent='Role: '+(step.assignment?.role||'none');}
    const saveState=detail.querySelector('.workflow-save-state');if(saveState)saveState.textContent=saveWords(state);
  }
  const saveWords=state=>state.draft?'Unsaved changes. They stay a draft in this tab until you choose Save definition.':'No unsaved changes.';

  function updatePurpose(heading,purpose=''){
    const text=String(purpose),prior=heading.querySelector('.workflow-purpose-reading');
    if(prior&&(prior.querySelector('.workflow-purpose-full')||prior.querySelector('.workflow-purpose'))?.textContent===text)return;
    const reading=prior||el('section','','workflow-purpose-reading'),open=reading.querySelector('.workflow-full-purpose')?.open===true;reading.replaceChildren();
    if(text){const paragraph=text.split(/\r?\n[ \t]*\r?\n/)[0],first=paragraph.length>360?paragraph.slice(0,357)+'…':paragraph;reading.append(el('p',first,'workflow-purpose'));if(first!==text){const full=el('details','','workflow-full-purpose');full.open=open;full.append(declare(el('summary','Full workflow purpose'),'workflow:purpose-full'),el('p',text,'workflow-purpose-full'));reading.append(full);}}
    if(!prior)heading.append(reading);
  }

  function updateTechnical(state,capture){
    const technical=technicalRegion;if(!alive||!technical||technical.isConnected===false||!technical.open)return;
    let body=technical.querySelector('.workflow-technical-body');if(!body){body=el('div','','workflow-technical-body');technical.append(body);}
    const owner=state.read?.value;
    body.replaceChildren(el('h3','Owner scope, permissions and providers'),el('pre',json({scope:owner?.scope||state.listing?.scope,permissions:owner?.permissions||state.listing?.permissions,actions:owner?.actions||state.listing?.actions,providers:owner?.providers||state.listing?.providers,coverage:state.listing?.coverage})),el('h3','Version and effective setting bases'),el('pre',json({definition_id:owner?.definition_id,selected_version:owner?.version,head_revision:owner?.head_revision,read_at:state.read?.at,read_handle:owner?.read_handle,current_read_handle:owner?.current_read_handle,pins:owner?.pins,history:owner?.history,effective_settings:owner?.effective_settings,obligations:owner?.obligations})),el('h3','Exact action receipt and recovery'),el('pre',json(state.attempt||{})),el('h3','Full draft and recovery record'),el('pre',json(capture)));
    technical.dataset.renderEpoch=String(paintEpoch);
  }

  // Observation offers are consumed only as issued; absent offers stay absent.
  function paintObservations(panel,owner,items){
    const live=()=>alive&&workspaceView==='runs',uses=findWorkflowOperationOffer(owner,'uses'),river=findWorkflowOperationOffer(owner,'river'),needs=river?((river.read||river).required_inputs||river.required_inputs||[]):[];
    if(uses)observationUIs.push(mountWorkflowObservation(panel,{offer:uses,facet:'uses',request,isCurrent:live,expected:{scope_id:owner.scope_id}}));
    if(river&&needs.length===1&&needs[0]==='work_id')for(const item of items)observationUIs.push(mountWorkflowObservation(panel,{offer:river,facet:'river',label:'Read observed flow · '+(item.title||item.work_id),request,inputs:{work_id:item.work_id},isCurrent:live,expected:{scope_id:owner.scope_id},stopRecovery}));
    if(!uses&&!river)panel.append(el('p','This owner does not yet offer recorded uses or observed message flow for this version. Planned connections are in Design; nothing here is inferred from them.','workflow-hint'));
  }
  function paintInterventions(parent,state,run=runPort.snapshot().read?.value,{without=null}={}){const list=el('ul','','workflow-interventions');for(const row of workflowInterventions({draft:state.draft,attempt:state.attempt,run})){if(row.id===without)continue;const item=el('li');item.dataset.intervention=row.id;item.append(el('strong',row.label),el('span',' · '+(row.available?'available now':'not available now')),el('p',row.meaning));if(row.id==='stop'&&row.available)mountWorkflowRunStop(item,{view:run,request,recovery:stopRecovery,isCurrent:()=>item.isConnected!==false});list.append(item);}parent.append(list);}
  const sameContext=(a,b)=>a?.kind===b?.kind&&(a?.step_id||null)===(b?.step_id||null);
  function freshStep(id){const now=port.snapshot();return (now.draft?.definition||now.read?.value?.definition)?.steps?.find(row=>row.id===id)||null;}
  function paintRoleDelivery(parent,state,step){const box=el('section','','workflow-role-delivery');box.dataset.roleDelivery=step.id;parent.append(box);roleDeliveryHost={box,step:step.id};fillRoleDelivery(box,state,step);}
  // Context and handoff choices come only from the owner's returned declarations.
  function fillRoleDelivery(box,state,step){
    const body=state.draft?.definition||state.read?.value?.definition,steps=body?.steps||[],title=id=>steps.find(row=>row.id===id)?.title||id,choices=workflowContextChoices(operationDeclarations),handoff=workflowHandoffFields(operationDeclarations);
    box.replaceChildren(el('p','Project, system and role context are always delivered. Choices here add declared inputs. They never grant read, tool or source permission, and a group never passes on a conversation or authority.','workflow-hint'));
    if(!choices&&!handoff){box.append(el('p','Choose Check execution to load the context and handoff choices this owner actually supports.','workflow-qualification'));return;}
    if(choices){
      const list=el('fieldset','','workflow-context-choices'),ancestors=[],upstream=[...new Set((body?.edges||[]).filter(row=>row.to===step.id).map(row=>row.from))];list.append(el('legend','Also deliver'));
      for(let cursor=step.parent_id;cursor&&!ancestors.includes(cursor);cursor=steps.find(row=>row.id===cursor)?.parent_id)ancestors.push(cursor);
      for(const choice of choices.rows){
        const sources=!choice.needs_step?[null]:choice.kind==='ancestor-instructions'?ancestors:choice.kind==='upstream-return'?upstream:steps.filter(row=>row.id!==step.id).map(row=>row.id);
        if(!sources.length){list.append(el('p',choice.label+': no '+(choice.kind==='ancestor-instructions'?'containing group':'connected earlier step')+' to draw from.','workflow-hint'));continue;}
        for(const source of sources){
          const wrap=el('label'),input=el('input'),row=source?{kind:choice.kind,step_id:source}:{kind:choice.kind};input.type='checkbox';input.dataset.contextChoice=choice.kind+(source?':'+source:'');declare(input,'workflow:context-choice',choice.kind+(source?':'+source:''));input.checked=(step.assignment?.context||[]).some(item=>sameContext(item,row));
          input.onchange=()=>{const now=freshStep(step.id);if(!now)return;let next=(now.assignment?.context||[]).filter(item=>!sameContext(item,row));if(input.checked)next=[...next,row];if(choices.max!==null&&next.length>choices.max){input.checked=false;notice.textContent='This owner accepts at most '+choices.max+' context choices for one step.';return;}edit(state,{type:'assignment',id:step.id,fields:{context:next.length?next:undefined}},true);};
          wrap.append(input,el('span',choice.label+(source?' · '+title(source):'')));list.append(wrap);
        }
      }
      box.append(list);
    }
    if(handoff){
      const held=step.assignment?.handoff||{},put=fields=>{const now=freshStep(step.id);if(!now)return;const merged={...now.assignment?.handoff,...fields};for(const [name,value]of Object.entries(merged))if(value===''||Array.isArray(value)&&!value.length)delete merged[name];edit(state,{type:'assignment',id:step.id,fields:{handoff:Object.keys(merged).length?merged:undefined}},true);};
      if(handoff.purpose){const input=field(box,'Handoff purpose',held.purpose,value=>put({purpose:value}),{tag:'textarea',rows:3});if(handoff.purpose.max)input.maxLength=handoff.purpose.max;}
      if(handoff.expected_output){const input=field(box,'Expected output',held.expected_output,value=>put({expected_output:value}),{tag:'textarea',rows:4});if(handoff.expected_output.max)input.maxLength=handoff.expected_output.max;}
      if(handoff.downstream){
        const targets=[...new Set((body?.edges||[]).filter(row=>row.from===step.id).map(row=>row.to))],list=el('fieldset','','workflow-handoff-downstream');list.append(el('legend','Hand the result to'));
        if(!targets.length)list.append(el('p','Connect this step to a later step to choose where its result goes.','workflow-hint'));
        for(const target of targets){const wrap=el('label'),input=el('input');input.type='checkbox';input.dataset.handoffTarget=target;declare(input,'workflow:handoff-target',target);input.checked=(held.downstream||[]).includes(target);input.onchange=()=>{const was=freshStep(step.id)?.assignment?.handoff?.downstream||[];put({downstream:input.checked?[...new Set([...was,target])]:was.filter(id=>id!==target)});};wrap.append(input,el('span',title(target)));list.append(wrap);}
        box.append(list);
      }
    }
    box.append(el('p','Check execution again after changing these. Its result shows what the owner actually consumed for each step. Anything it does not return stays in the draft but is not delivered.','workflow-hint'));
  }
  function guideSections(state){
    const body=state.draft?.definition||state.read?.value?.definition,scope=state.read?.value?.scope||state.draft?.basis?.payload?.scope||state.listing?.scope,out=[],section=(title,open=false)=>{const node=el('details','','workflow-guide-section');node.open=open;node.append(el('summary',title));out.push(node);return node;};
    const purpose=section('This workflow',true);purpose.append(el('p',body?(body.title||'Untitled workflow')+(body.description?' — '+body.description:''):'No workflow is selected. Create one, or open a saved design from the library.'),el('p',scope?.kind==='project'?'Belongs to the project '+scope.namespace+'. A run uses that project’s admitted conversation.':scope?.kind==='owned-workspace'?'A reusable workspace design. Use as new draft… makes a project-owned copy that can run in a project.':'Ownership is chosen when you create the workflow.'));
    const origin=state.read?.value?.derived_from||body?.derived_from;if(origin)purpose.append(el('p','Adapted from '+(origin.title||origin.definition_id||'another saved design')+'. The original keeps its own identity and history.'));
    if(body?.steps?.length){const plan=section('Steps and connections'),list=el('ol');for(const step of body.steps){const role=step.assignment?.role,extra=step.assignment?.context?.length||0,expected=step.assignment?.handoff?.expected_output,item=el('li');item.append(el('strong',step.title||step.id),el('span',' · '+(role||'no role')));if(extra)item.append(el('p','Also receives '+extra+' declared input'+(extra===1?'':'s')+'.'));if(expected)item.append(el('p','Expected output: '+expected));list.append(item);}plan.append(list);
      const flow=workflowConfiguredFlow(body);if(flow.length){const edges=el('ul','','workflow-configured-flow');for(const row of flow)edges.append(el('li',row.from+' → '+row.to+' · '+row.meaning));plan.append(el('p','Configured connections are the plan:'),edges);}
      plan.append(el('p','Observed message flow appears in Runs only from recorded receipts. No receipt means not observed, not that nothing happened.','workflow-hint'));}
    section('Review and synthesis').append(el('p','A reviewer judges the exact handoff it receives. It works in a separate session with project context, which is not blind review unless the owner reports a sealed reading. Findings change future configuration, never past acceptance.'),el('p','Synthesis is written in the original parent conversation, under the model, settings and authority that conversation was admitted with. Choosing a different model on a synthesis step does not change that parent.'));
    const bounds=workflowPolicyBounds(operationDeclarations);section('Review rounds and limits').append(el('p',bounds?workflowPolicyText(bounds):'Choose Check execution in Design to load the limits this owner supports. A dependency cycle never runs; only a supported bounded review pattern repeats.'));
    paintInterventions(section('Discard, withdraw and stop are different'),state);
    const first=section('Customise and finish',true),steps=el('ol');for(const text of ['Choose or create a workflow, and choose whether it belongs to this project or to the workspace.','Name each step, write its instructions and choose what it receives and hands on.','Check execution. Repair any refusal; the check saves and starts nothing.','Save definition to record a version you can return to.','Prepare agent run… records one exact request. Start is a separate decision in the conversation.','Follow Runs for recorded uses and observed flow. A run finishes when the original parent publishes its synthesis.'])steps.append(el('li',text));first.append(steps);
    return out;
  }
  function chooseWorkspaceView(next){
    if(next!=='runs'&&runsNoticeText){if(notice.textContent===runsNoticeText)notice.textContent='';runsNoticeText='';}
    if(next!=='design'&&port.snapshot().selection)overviewOpen=false;
    runsVisit++;workspaceView=next;appOpen=next==='runs';
    const state=port.snapshot(),owner=state.read?.value;
    if(next==='runs'&&owner?.app_runs_read&&!runPort.matches(owner)){
      // The explicit Runs decision reads only this saved version's issued list.
      runPort.open(owner,'list',owner.app_runs_read).catch(runsError(owner));
    }
    paint({...port.snapshot(),event:'view'});
    detail.querySelector('[data-workflow-view="'+next+'"]')?.focus?.({preventScroll:true});
  }
  function paintWorkspaceNavigation(parent){
    const nav=el('nav','','workflow-progress');nav.setAttribute('aria-label','Workflow workspace');
    for(const [key,label]of [['design','Design'],['runs','Runs'],['guide','Guide']]){
      const tab=button(label,()=>chooseWorkspaceView(key));tab.dataset.workflowView=key;tab.dataset.control='workflow:'+key;tab.setAttribute('aria-current',workspaceView===key?'page':'false');nav.append(tab);
    }
    parent.append(nav);
  }
  function paintGuide(parent,state){
    const guide=el('section','','workflow-guide');guide.append(el('h3','From a design to an observed result'),el('p','Design describes what should happen. A saved version, a prepared request and an admitted run are different records. Saving does not start work.'));
    const stages=el('ol');
    for(const [title,meaning]of [
      ['Design and validate','Choose the ownership, purpose, steps and settings. An executable preview must admit the actual profile and selected edges before preparation. A drawn arrow is not proof that a message was delivered.'],
      ['Prepare deliberately','Use a supported project workflow and its author conversation. Review the selected saved version and inputs, then Send the offered preparation. Starting execution is a separate decision.'],
      ['Observe actual use','Runs reads recorded uses of the exact saved version. Follow actual step, conversation, return and result reads. Missing observations are unknown; a completed record is not evidence that a process is still running.'],
      ['Intervene with the right action','Discard unsaved edits changes only the local draft. Request withdrawal, pause before the next step and stopping active work have different effects and are available only when their owners offer them. An uncertain request keeps its original identity.'],
      ['Review and finish','Review must judge the exact produced evidence and retain unresolved findings. Synthesis must consume the required returns. Human Apply, task completion and publication remain separate decisions.']
    ]){const row=el('li');row.append(el('strong',title),el('p',meaning));stages.append(row);}guide.append(stages);
    const grouping=el('details');grouping.append(el('summary','Groups, connections and context'),el('p','Nesting organises steps and inherits declared settings. It does not spawn a delegated subworkflow or inherit a conversation, permissions or resource allowance. Local instructions remain local unless an explicit admitted context choice says otherwise.'),el('p','Control describes intended ordering; data describes intended input; feedback describes an intended revision. The execution preview determines which pattern actually runs. A dependency cycle is not an executable feedback loop.'));
    guide.append(grouping,...guideSections(state));if(state.read?.value?.scope?.kind==='owned-workspace')guide.append(el('p','This saved design belongs to the workspace. Project execution needs an explicitly project-owned workflow and the project’s admitted conversation route.','workflow-qualification'));parent.append(guide);
  }

  // THE RUN POLICY IN WORDS (wave 12, P4), under the drawing, from run_policy and the owner's declared bounds; it is
  // edited where the editor already edits it (Workflow details and defaults), one click away.
  let policyLine=null;
  function paintPolicy(place,body){
    const row=el('div','','workflow-policy');policyLine=el('p','','workflow-policy-words');row.append(policyLine);
    if(body.run_policy)row.append(declare(button('Change these limits',()=>{const options=detail.querySelector('.workflow-definition-options');if(!options)return;options.open=true;definitionOpen=true;options.scrollIntoView?.({block:'start'});options.querySelector('fieldset input,fieldset select,fieldset textarea')?.focus?.({preventScroll:true});}),'workflow:policy-edit'));
    place.append(row);refreshPolicy({draft:{definition:body}},true);
  }
  function refreshPolicy(state,initial=false){const body=state.draft?.definition||state.read?.value?.definition;if(policyLine&&(initial||policyLine.isConnected!==false)&&body)policyLine.textContent='Run policy: '+workflowPolicyWords(body.run_policy,workflowPolicyBounds(operationDeclarations));}
  function paint(state){
    if(!alive)return;const focusedOwner=state.read?.value,focusedBody=state.draft?.definition||focusedOwner?.definition;onFocus({title:focusedBody?.title||(state.selection?'New workflow':'Workflows'),reference:focusedOwner?.reference||null,version:focusedOwner?.version||null,draft:!!state.draft,scope:focusedOwner?.scope||state.draft?.basis?.payload?.scope||state.listing?.scope});host.classList.toggle('workflow-step-selected',!!state.step);if(savedVisit&&!savedVisit.parentHistory&&state.selection?.id!==savedVisit.expected.definition_id)closeSaved({focus:false});if(historyVisit&&state.selection?.id!==historyVisit.selection)closeHistory({focus:false});if(state.event==='selection'||state.event==='create'){appOpen=false;workspaceView='design';overviewOpen=false;}if(['selection','create'].includes(state.event))libraryOpen=false;const focus=captureFocus(),capture=port.capture();paintEpoch++;remember(capture);versionStatus(state);host.classList.toggle('workflow-selected',!!state.selection);const overview=showingOverview(state);host.classList.toggle('workflow-overview-mode',overview);host.dataset.workflowView=workspaceView;
    if(state.event==='typing'){
      updateEditorState(state);refreshSettingChoices(state);refreshPolicy(state);capabilityUI?.update();if(!state.comparison)detail.querySelector('.workflow-comparison')?.remove();
      updateTechnical(state,capture);return;
    }
    capabilityUI?.destroy();capabilityUI=null;for(const ui of observationUIs)ui.destroy();observationUIs=[];const technicalOpen=technicalRegion?.isConnected!==false&&technicalRegion?.open===true;technicalRegion=null;inspectorRegion=null;settingGroups.clear();lineageViews.clear();policyLine=null;paintLibrary(state,capture);detail.replaceChildren();if(overview){paintWorkspaceNavigation(detail);if(workspaceView==='guide')paintGuide(detail,state);else if(workspaceView==='runs')paintOverviewRuns(detail,state);return;}
    const owner=state.read?.value,body=state.draft?.definition||owner?.definition;if(!body){detail.append(el('p',state.read?.error||'Reading selected workflow…'));return;}
    const runMode=appOpen&&runPort.matches(owner),runChosen=runMode&&runPort.snapshot().selection?.kind!=='list',headingBody=runChosen?runPort.snapshot().read?.definition?.definition:body;if(!runChosen||runPort.snapshot().read?.value?.schema_version==='laplace.research-workflow-run/1')dropRiver();
    const allWorkflows=button('All workflows',()=>{if(!alive)return;const id=port.snapshot().selection?.id;for(const key of [...overviewReads.keys()])if(key.startsWith(id+'@'))overviewReads.delete(key);overviewOpen=true;workspaceView='design';appOpen=false;paint({...port.snapshot(),event:'view'});library.querySelector('.workflow-overview-open[aria-current="page"]')?.focus?.({preventScroll:true});});allWorkflows.dataset.action='overview';allWorkflows.className='workflow-back';declare(allWorkflows,'workflow:overview');
    // AN OPENED RUN STARTS WITH ITS DRAWING (wave 12, P5): with a run open the page's preamble is one compact line (the
    // workflow's name, Design | Runs | Guide, Back to runs, Return to workflow, Refresh status), so the run header and its
    // drawing are on the first screen; every control the line replaces keeps its declared id there.
    host.classList.toggle('workflow-run-open',!!runChosen);
    const heading=el('header','',runChosen?'workflow-heading workflow-run-compact':'workflow-heading'),scopeWords=scopeLabel(owner?.scope||state.draft?.basis?.payload?.scope||state.listing?.scope);
    if(runChosen)heading.append(allWorkflows,el('strong',headingBody?.title||'Recorded run','workflow-run-compact-title'),el('span',scopeWords+' · Recorded run · read only','workflow-eyebrow'));
    else{const lead=el('div','','workflow-heading-lead');lead.append(allWorkflows,el('p',scopeWords+(runMode?' / Runs':' / Workflow'),'workflow-eyebrow'));heading.append(lead,el('h2',headingBody?.title||'Untitled workflow'));updatePurpose(heading,headingBody?.description);}
    const toolbar=el('div','','workflow-actions workflow-main-actions'),save=button('Save definition',()=>act({type:'save'}),{disabled:!state.draft||['pending','uncertain'].includes(state.attempt?.status)});save.dataset.action='save';save.className='workflow-primary';declare(save,'workflow:save');
    const discard=button('Discard unsaved edits',()=>discardDraft(),{disabled:!state.draft,title:'Discard only this local definition draft. Recorded saves, pending requests and runs are not cancelled.'});discard.dataset.action='discard';discard.dataset.control='workflow:discard';const saveState=el('p',saveWords(state),'workflow-save-state');saveState.setAttribute('role','status');
    // Save, Discard and the unsaved line sit beside the stage drawing; the other actions on this workflow follow the drawing, and what they open (preparation forms, the comparison) opens under them.
    const saveRow=el('div','','workflow-actions workflow-main-actions workflow-save-row'),preparations=el('div','','workflow-preparations');saveRow.append(save,discard,saveState);toolbar.classList.add('workflow-more-actions');toolbar.setAttribute('aria-label','More for this workflow');toolbar.append(declare(button('Compare draft with current',()=>act({type:'compare'}),{disabled:!state.draft||state.selection.id.startsWith('local:')}),'workflow:compare'),declare(button('Reinspect current',()=>act({type:'reinspect'}),{disabled:state.selection.id.startsWith('local:')}),'workflow:reinspect'),declare(button(prepareOpen?'Close preparation':'Prepare external run…',()=>{prepareOpen=!prepareOpen;paint({...port.snapshot(),event:'view'});}),'workflow:prepare-external'));if(owner?.actions?.use_in_conversation?.available)toolbar.append(declare(button(appPrepareOpen?'Close agent preparation':'Prepare agent run…',()=>{appPrepareOpen=!appPrepareOpen;appOpen=false;paint({...port.snapshot(),event:'view'});}),'workflow:prepare-agent'));if(owner?.app_runs_read&&owner?.actions?.app_prepare?.available)toolbar.append(declare(button('Agent runs',()=>{runsVisit++;workspaceView='runs';appOpen=true;runPort.open(owner,'list',owner.app_runs_read).catch(runsError(owner));}),'workflow:agent-runs'));if(adaptable(state))toolbar.append(adaptButton(state));for(const control of toolbar.children)if(control.textContent==='Compare draft with current')control.dataset.action='compare';
    if(runChosen){paintWorkspaceNavigation(heading);heading.append(el('div','','workflow-actions workflow-run-compact-actions'));}
    else{const summary=el('p','','workflow-version-summary');summary.append(el('span',savedLabel(owner),state.draft?'':'workflow-saved'),el('span',state.draft?'Unsaved changes':'Saved'));
      const prepared=owner?.pins?.prepared||[];if(prepared.length){const pin=prepared.at(-1);summary.append(el('span',pin.definition_pin?.definition_revision===owner.version?'Prepared from this version':'Prepared from an older saved version'),el('span','Run status not loaded'));}heading.append(summary);paintWorkspaceNavigation(heading);}
    detail.append(heading);
    if(state.draft?.needs_adoption)detail.append(el('p','Creation finished while you kept editing. Compare before saving the newer draft.','workflow-qualification'));
    if(state.read?.io==='error')detail.append(el('p','Update check failed; retained view: '+state.read.error,'error'));
    if(state.attempt){
      const result=el('section','','workflow-result');result.setAttribute('role','status');result.tabIndex=-1;result.dataset.workflowAttempt=state.attempt.request_id;result.append(el('h3','Action: '+state.attempt.status),el('p',state.attempt.error||[state.attempt.effect,state.attempt.result?.run?.status==='NOT_STARTED'?'Not started':state.attempt.result?.run?.status].filter(Boolean).join(' · ')||'Waiting for owner response'));
      if(state.attempt.postimage_error)result.append(el('p','Effect recorded; readback unavailable. Reinspect to update the view.'));
      if(state.attempt.status==='uncertain')result.append(declare(button('Reinspect exact request',()=>act({type:'recover'})),'workflow:recover'));
      if(['pending','uncertain'].includes(state.attempt.status)&&state.attempt.withdrawal_offer?.prepare_read){const withdraw=button('Withdraw original request',()=>withdrawOriginal(),{disabled:['preparing','pending'].includes(state.attempt.withdraw_status)});withdraw.dataset.action='withdraw';withdraw.dataset.control='workflow:withdraw';result.append(withdraw,el('p','Ask the owner to prevent this exact request before admission. If it already recorded an effect, withdrawal does not undo it. Your later edits are retained.','workflow-hint'));}
      if(state.attempt.status==='withdrawn')result.append(el('p','The owner confirms this original request was not admitted. The saved history and other recorded effects were not undone. Your local draft remains separate.'));
      if(state.attempt.withdraw_status==='recorded-no-undo')result.append(el('p','The original effect was already recorded. It was not undone.'));
      if(state.attempt.withdraw_status==='uncertain')result.append(el('p','Withdrawal is unconfirmed. Keep the original request and use its exact inspection; no replacement is sent.','workflow-hint'));
      if(state.attempt.withdrawal_error)result.append(el('p',state.attempt.withdrawal_error,'workflow-hint'));
      if(!['pending','uncertain'].includes(state.attempt.status))result.append(declare(button('Acknowledge inspected attempt',()=>act({type:'resolve-attempt'})),'workflow:acknowledge'));detail.append(result);
    }
    if(workspaceView==='guide'){paintGuide(detail,state);restoreFocus(focus);return;}
    if(workspaceView==='runs'&&!runPort.matches(owner)){detail.append(el('p',owner?.app_runs_read?'Reading uses of this exact saved version…':owner?.scope?.kind==='owned-workspace'?'A reusable workspace design is not run directly, so it has no recorded agent runs. Use as new draft… can copy this saved version into a project, where a supported design can be checked and prepared.':'No recorded-use read is offered for this selection. Unsaved local edits are not a run.','workflow-qualification'));restoreFocus(focus);return;}
    if(state.comparison&&!runMode){const compare=el('section','','workflow-comparison');compare.dataset.version=state.comparison.version;compare.append(el('h2','Compare with current saved version'),el('p','Review both complete definitions. Adopting keeps your draft and changes its save guard.'),el('h3','Current definition'),el('pre',json(state.comparison.current)),el('h3','Your draft'),el('pre',json(state.comparison.draft)),declare(button('Keep draft and adopt compared guard',()=>act({type:'adopt',basis:state.comparison.basis})),'workflow:adopt-guard'));preparations.append(compare);}
    if(prepareOpen&&!runMode){
      const prepare=el('form','','workflow-prepare');prepare.append(el('h2','Prepare an external / CLI workflow'),el('p',state.draft?'Save your changes before preparing.':'Choose the steps and execution scope. Preparation does not start the run.','workflow-hint'));
      const selected=[],choices=el('div','','workflow-prepare-steps');for(const step of body.steps){const label=el('label',step.title||step.id),check=declare(el('input'),'workflow:prepare-step','external:'+step.id);check.type='checkbox';check.value=step.id;check.name='selected_steps';check.checked=state.context.selected_steps?state.context.selected_steps.includes(step.id):step.assignment?.role!=='group';check.onchange=()=>act({type:'context',fields:{selected_steps:selected.filter(value=>value.checked).map(value=>value.value)}});label.prepend(check);choices.append(label);selected.push(check);}prepare.append(choices);
      const fields=el('div','','workflow-prepare-fields'),node=field(fields,'Execution node',state.context.node||'',value=>act({type:'context',fields:{node:value}})),goal=field(fields,'Execution goal',state.context.goal||'',value=>act({type:'context',fields:{goal:value}}),{tag:'textarea',rows:3}),paths=field(fields,'Write paths (one per line)',state.context.paths||'',value=>act({type:'context',fields:{paths:value}}),{tag:'textarea',rows:3});prepare.append(fields);
      const submit=declare(el('button','Prepare selected steps'),'workflow:prepare-submit');submit.dataset.action='prepare';submit.disabled=!!state.draft||!owner?.actions?.prepare?.permitted||['pending','uncertain'].includes(state.attempt?.status);submit.title=owner?.actions?.prepare?.reason||'';prepare.append(submit);if(owner?.actions?.prepare?.reason)prepare.append(el('p',owner.actions.prepare.reason,'workflow-hint'));
      prepare.onsubmit=event=>{event.preventDefault();act({type:'prepare',fields:{selected_steps:selected.filter(check=>check.checked).map(check=>check.value),profile:'laplace.workflow/1',node:node.value,goal:goal.value,write_paths:textLines(paths.value)}});};preparations.append(prepare);
    }
    if(appPrepareOpen&&owner&&!runMode)paintAppPreparation(preparations,state);
    if(appOpen&&runPort.matches(owner)){paintAppRuns(detail,state);restoreFocus(focus);restoreRunFocus();return;}
    // SET UP: DRAW THE STEPS AND ROUTES (wave 12, screen 1 of the approved design): the drawing is the main thing, with
    // the route patterns and the run policy in words under it, the column for the selected step beside it (under it on
    // a narrow screen), Check execution and the other actions after; the free graph and the list follow.
    const grid=el('div','','workflow-grid workflow-topology-grid workflow-design-grid'),map=el('section','','workflow-map'),inspector=el('section','','workflow-inspector'),tools=el('div','','workflow-actions workflow-view-tools'),checkHost=el('div','','workflow-check-host');
    const {loops}=workflowStageLayout(body),designHead=sectionHead(map,'Set up: draw the steps and routes',loops.length?['stage','loop']:['stage']);designHead.children[0].className='workflow-design-title';designHead.append(saveRow);paintStrip(map,body,state.step,{onSelect:id=>act({type:'step',id})});paintPolicy(map,body);paintStageTools(map,state,body,state.step);map.append(checkHost,toolbar,preparations);
    for(const [value,label]of [['graph','Graph view'],['list','List view']]){const b=button(label,()=>{view=value;userView=true;paint({...port.snapshot(),event:'view'});});b.setAttribute('aria-pressed',view===value?'true':'false');declare(b,'workflow:design-view',value);tools.append(b);}const other=el('section','','workflow-other-views');other.append(el('p','The same steps as a free graph, to drag connections and nesting, or as a list of steps and their relations:','workflow-hint'),tools);
    if(view==='graph'){paintGraph(other,state,body,state.step);const list=el('details','','workflow-graph-list');list.append(declare(el('summary','Step list · '+body.steps.length),'workflow:step-list'));paintList(list,state,body,state.step);other.append(list);}else paintList(other,state,body,state.step);
    inspectorRegion=inspector;paintInspector(inspector,state,body,state.step);grid.append(map,inspector);detail.append(grid,other);
    if(!runMode){
      const next=el('p','','workflow-next');next.dataset.control='workflow:purpose';
      next.textContent=!owner?'Add a title and a step, then Save definition. Saving keeps the workflow; it does not run it.':owner.scope?.kind==='owned-workspace'?'Saved in this workspace. You can edit, save and read it here. App runs require a supported project workflow and its project conversation.':owner.actions?.use_in_conversation?.available?'Save any edits before preparing a run. Prepare agent run opens a message for this project; Send prepares its task. Starting execution is a separate later decision.':'This saved workflow is readable here. App run preparation is not offered in this context.';detail.append(next);
      if(owner?.actions?.use_in_conversation?.reason)detail.append(el('p',owner.actions.use_in_conversation.reason,'workflow-hint'));
      if(owner?.history_read){const browse=button('Browse all saved versions',()=>openHistory(owner,owner.history_read,'detail'));browse.dataset.control='workflow:history';browse.dataset.historyWorkflow=owner.definition_id;browse.dataset.historyOpener='detail';detail.append(browse);}
      if(owner){const read=button('Read this saved version',()=>openSaved(owner,{version:owner.version,read:owner.read_handle||owner.read},'viewed'));read.dataset.savedOpener='viewed';read.dataset.control='workflow:saved-read';read.dataset.savedVersion=owner.version;read.dataset.savedWorkflow=owner.definition_id;detail.append(read);}
      const titleFields=el('section','','workflow-title-fields');field(titleFields,'Workflow title',body.title,value=>edit(state,{type:'fields',fields:{title:value}},true));const purpose=el('details');purpose.append(declare(el('summary','Edit workflow purpose'),'workflow:purpose-edit'));field(purpose,'Workflow description',body.description,value=>edit(state,{type:'fields',fields:{description:value}},true),{tag:'textarea',rows:3});titleFields.append(purpose);detail.append(titleFields);
    }
    if(!runMode&&state.listing?.execution_preview)capabilityUI=mountWorkflowCapability(checkHost,{offer:state.listing.execution_preview,snapshot:()=>port.snapshot(),dispatch:act,request,isCurrent:()=>alive&&workspaceView==='design',onDeclarations:value=>{operationDeclarations=value;refreshPolicy(port.snapshot());const held=roleDeliveryHost,step=held&&freshStep(held.step);if(held&&held.box.isConnected!==false&&step)fillRoleDelivery(held.box,port.snapshot(),step);}});
    const definitions=el('details','','workflow-definition-options');definitions.open=definitionOpen;definitions.ontoggle=()=>{definitionOpen=definitions.open;};definitions.append(declare(el('summary','Workflow details and defaults'),'workflow:details'));
    if(body.run_policy){const policy=el('fieldset');policy.append(el('legend','Review loop and human boundary'),el('p','These are authored limits in this draft. Execution uses the saved, admitted version. Manuscript Apply remains a separate human decision.','workflow-hint'));
      const change=(key,value)=>{const fresh=port.snapshot(),definition=fresh.draft?.definition||fresh.read?.value?.definition;if(fresh.selection?.id!==state.selection.id||!definition?.run_policy)return;edit(fresh,{type:'fields',fields:{run_policy:{...definition.run_policy,[key]:value}}},true);};
      // Fields and limits come from the owner's declared variant for this profile. The legacy
      // v1 limits are only the pre-check fallback for v1; other profiles get no invented limit.
      const variant=workflowPolicyVariant(operationDeclarations,body.run_policy.profile),legacy=!variant&&body.run_policy.profile==='laplace.research-review/1'?{max_iterations:{minimum:1,maximum:3},runtime_seconds:{minimum:1,maximum:3600}}:null,rules=variant?.properties||legacy||Object.fromEntries(Object.keys(body.run_policy).filter(key=>typeof body.run_policy[key]==='number').map(key=>[key,{}]));
      if(!variant)policy.append(el('p',legacy?'Legacy review profile limits. Check execution confirms them with the owner.':'Choose Check execution to load the limits the owner declares for this policy profile. Values are kept as authored.','workflow-qualification'));
      const labels={max_iterations:'Maximum review iterations',runtime_seconds:'Seconds per admitted step',max_admissions:'Maximum admitted steps',deadline_seconds:'Run deadline in seconds',continuation_criteria:'Continue another round when',exit_criteria:'Stop and synthesise when'};
      for(const [key,rule]of Object.entries(rules)){if(['profile','advance','apply'].includes(key))continue;if(rule.type==='string'){const input=field(policy,labels[key]||key,body.run_policy[key],value=>change(key,value),{tag:'textarea',rows:3,name:'run-policy-'+key});if(Number.isSafeInteger(rule.maxLength))input.maxLength=rule.maxLength;continue;}const input=field(policy,labels[key]||key,body.run_policy[key],value=>change(key,value===''?'':Number(value)),{name:'run-policy-'+key});input.type='number';if(Number.isSafeInteger(rule.minimum))input.min=String(rule.minimum);if(Number.isSafeInteger(rule.maximum)&&rule.maximum<Number.MAX_SAFE_INTEGER)input.max=String(rule.maximum);input.step='1';}
      declare(select(policy,'Advance after a response',Object.entries(ADVANCE_WORDS),body.run_policy.advance,value=>change('advance',value)),'workflow:policy-advance','workflow');policy.append(el('p','Manuscript application: '+body.run_policy.apply));definitions.append(policy);}
    // The workflow defaults are set in the column beside the drawing ("Set for the whole workflow").
    definitions.append(el('p','Workflow defaults for provider, model, effort and input policy are set in the column beside the drawing, under Set for the whole workflow.','workflow-hint'));if(state.visit_depth)definitions.append(declare(button('Back to prior workflow',()=>act({type:'back'})),'workflow:back'));for(const control of definitions.children)if(control.textContent==='Discard local draft')control.dataset.action='discard';detail.append(definitions);
    lineageSection(detail,owner);
    if(owner?.history?.length){const history=el('details','','workflow-history');history.append(declare(el('summary','Saved history'),'workflow:saved-history'),el('p','Up to 32 recent saved versions are listed. Open one to read it separately; your authoring draft and save guard stay unchanged.','workflow-hint'));const choices=el('div','','workflow-actions');owner.history.forEach((item,index)=>{const current=item.version===owner.head_revision||(owner.is_current&&item.version===owner.version),label=current?'Current saved version':'Earlier saved version · item '+(index+1)+' in this list',open=button(label,()=>openSaved(owner,item,'history:'+item.version));open.dataset.savedOpener='history:'+item.version;open.dataset.control='workflow:saved-read';open.dataset.savedVersion=item.version;open.dataset.savedWorkflow=owner.definition_id;open.dataset.version=revision(item);open.title=revision(item);choices.append(open);});history.append(choices);detail.append(history);}
    if(owner?.obligations?.length)detail.append(el('p',owner.obligations.length+' preparation '+(owner.obligations.length===1?'issue':'issues')+' to inspect in Technical details.','workflow-hint'));
    const technical=el('details','','workflow-technical');technical.append(declare(el('summary','Technical details'),'workflow:technical'));technicalRegion=technical;technical.open=technicalOpen;
    technical.ontoggle=()=>{if(!alive||technical!==technicalRegion||technical.isConnected===false)return;if(!technical.open){technical.querySelector('.workflow-technical-body')?.remove();return;}if(technical.querySelector('.workflow-technical-body')&&technical.dataset.renderEpoch===String(paintEpoch))return;updateTechnical(port.snapshot(),port.capture());};
    detail.append(technical);updateTechnical(state,capture);restoreFocus(focus);
  }
  const onWidth=()=>{if(!userView){view=media.matches?'list':'graph';paint({...port.snapshot(),event:'view'});}};media?.addEventListener?.('change',onWidth);
  const unsubscribeRun=runPort.subscribe(()=>paint({...port.snapshot(),event:'app-read'}));const unsubscribe=port.subscribe(paint);paint({...port.snapshot(),event:'view'});if(initialReference?.identity?.id&&initialRead)await act({type:'select',id:initialReference.identity.id,read:initialRead});else if(initial?.selection&&!initial.selection.id.startsWith('local:'))await act({type:'select',id:initial.selection.id,read:initial.selection.read,step:initial.step});if(initialStep){const body=port.snapshot().read?.value?.definition;if(!body?.steps?.some(row=>row.id===initialStep))throw Error('The owner-issued local step is not in this exact saved definition.');await act({type:'step',id:initialStep});}if(presentation.appOpen&&runPort.matches(port.snapshot().read?.value)){appOpen=true;workspaceView='runs';await runPort.restore(port.snapshot().read.value).catch(error=>{notice.textContent=error.message;});}
  if(deferOverviewReads){deferOverviewReads=false;if(showingOverview(port.snapshot()))paint({...port.snapshot(),event:'view'});}if(showingOverview(port.snapshot()))await loadStarters();
  return {port,runPort,requestNavigation,requestReturn,get hasDraft(){return port.hasUnresolved();},get recoveryStored(){return stored;},leaveGuard(event){if(safeNavigation)return false;if(!port.hasUnresolved())return false;remember();event?.preventDefault?.();if(event)event.returnValue='';return true;},destroy(){if(!alive)return;remember();alive=false;capabilityUI?.destroy();dropRiver();++savedEpoch;++historyEpoch;++navigationEpoch;host.removeEventListener('focusin',trackEditorFocus);document.removeEventListener('focusin',trackRunFocus);media?.removeEventListener?.('change',onWidth);unsubscribe();unsubscribeRun();runPort.destroy();port.destroy();}};
}
