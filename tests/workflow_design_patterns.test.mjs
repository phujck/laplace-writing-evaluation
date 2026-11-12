// Wave 12, the Design view (screen 1): route patterns insert only ordinary steps and arrows the definition owner
// accepts, as one draft edit each, and are offered only where the owner's execution preview, asked about the draft each
// makes, runs it (the stand-in owner answers with its own _preview), with the owner's sentence beside a refused one; the selected step's column says where each setting comes from in the owner's words
// and never supplies a value; the run policy is said in words; every control the Design view paints is declared.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {installDOM,Node,findButton} from './helpers/evidence_reader_harness.mjs';
import {feedbackWireDigest} from '../src/laplace/web/static_shared/feedback-route-port.mjs';
import {editWorkflow,workflowPatternBlocker,workflowPatternResult,workflowPatternIntent,workflowPatternProbe,WORKFLOW_PATTERN_PROBE_INSTRUCTION} from '../src/laplace/web/static_shared/workflow-port.mjs';
import {settingOriginWords,workflowSettingLineage,declaredWorkflowSettings} from '../src/laplace/web/static_shared/workflow-setting-choices.mjs';
import {workflowPolicyBounds,workflowPolicyText,issueText} from '../src/laplace/web/static_shared/workspace-workflow-operation.mjs';
import {mountWorkflowEditor,workflowPolicyWords,workflowEdgeLegend,WORKFLOW_EDGE_MARKS,workflowReadingOrder,workflowStageLayout} from '../src/laplace/web/static_shared/workspace-workflow-editor.mjs';
const copy=structuredClone;
const CONTROLS=JSON.parse(readFileSync(new URL('./fixtures/help/controls.json',import.meta.url),'utf8')),declared=new Map(CONTROLS.controls.map(row=>[row.id,row]));
const step=(id,title,role,settings={},extra={})=>({id,title,parent_id:null,assignment:{role,instructions:'Do '+title,settings},inputs:[],outputs:[],targets:[],...extra});
const starter={schema_version:'laplace.workflow-definition/1',title:'Draft, independent review, human Apply',description:'',settings:{},layout:{},
  run_policy:{profile:'laplace.research-review/1',max_iterations:2,runtime_seconds:300,advance:'automatic-review',apply:'human'},
  steps:[step('write','Draft proposal','builder'),step('review','Independent evidence review','adversary',{input_policy:'evidence-packet'})],
  edges:[{id:'draft-review',from:'write',to:'review',kind:'control'},{id:'review-revision',from:'review',to:'write',kind:'feedback'}]};
const two={...copy(starter),run_policy:undefined,steps:[step('a','Draft A','builder',{provider:'claude',model:'opus'}),step('b','Draft B','builder',{provider:'codex'})],edges:[]};
delete two.run_policy;
const shape=body=>body.edges.map(row=>[row.from,row.to,row.kind]);
const one={...copy(starter),steps:[starter.steps[0]],edges:[]};
const root=fileURLToPath(new URL('..',import.meta.url)),python=(code,input)=>execFileSync(root+'scripts/laplace-python',['-c',code],{cwd:root,input:JSON.stringify(input),encoding:'utf8'});

test('Add a review of this step: one adversary after the step, a result arrow in and a findings-back arrow out, no settings of its own',()=>{
  const out=workflowPatternResult(starter,{type:'review-after',after:'write',id:'rw',edge_id:'e-in',feedback_id:'e-back'});
  assert.deepEqual(out.steps.map(row=>row.id),['write','rw','review']);
  const made=editWorkflow(one,{type:'review-after',after:'write',id:'rw',edge_id:'e-in',feedback_id:'e-back'});
  assert.deepEqual(shape(made),[['write','rw','control'],['rw','write','feedback']]);
  const review=out.steps.find(row=>row.id==='rw');assert.equal(review.title,'Review of Draft proposal');assert.equal(review.assignment.role,'adversary');assert.deepEqual(review.assignment.settings,{});
  assert.deepEqual(shape(out),[['rw','review','control'],['review','write','feedback'],['write','rw','control'],['rw','write','feedback']],'what the step passed forward now leaves from its review');
  assert.deepEqual(starter.steps.map(row=>row.id),['write','review'],'the draft given is not changed in place');
  assert.equal(workflowStageLayout(out).loops.length,2);
});

test('Make these two review each other: a reviewer per builder with the other builder\'s settings, four steps and four arrows; no owner profile runs it',()=>{
  const out=workflowPatternResult(two,{type:'reciprocal-review',a:'a',b:'b',ids:{ra:'ra',rb:'rb',ra_edge:'x1',ra_feedback:'x2',rb_edge:'x3',rb_feedback:'x4'}});
  assert.deepEqual(out.steps.map(row=>[row.id,row.assignment.role]),[['a','builder'],['ra','adversary'],['b','builder'],['rb','adversary']]);
  assert.deepEqual(out.steps.find(row=>row.id==='ra').assignment.settings,{provider:'codex'},'B\'s settings review A');
  assert.deepEqual(out.steps.find(row=>row.id==='rb').assignment.settings,{provider:'claude',model:'opus'},'A\'s settings review B');
  assert.deepEqual(shape(out),[['a','ra','control'],['ra','a','feedback'],['b','rb','control'],['rb','b','feedback']]);
  const copied=workflowPatternResult({...two,steps:[two.steps[0]]},{type:'reciprocal-review',a:'a',b:null,ids:{copy:'a2',ra:'ra',rb:'rb'}});
  assert.deepEqual(copied.steps.map(row=>row.id),['a','ra','a2','rb']);const twin=copied.steps.find(row=>row.id==='a2');
  assert.equal(twin.title,'Copy of Draft A');assert.deepEqual(twin.assignment,{role:'builder',instructions:'Do Draft A',settings:{provider:'claude',model:'opus'}},'a copy carries role, instructions and settings only');
  assert.equal(copied.edges.length,4);
});

test('Add a synthesis that reads these: one step with the owner\'s synthesis role and a data arrow from each chosen step, nothing else',()=>{
  const out=editWorkflow(two,{type:'synthesis',reads:['a','b'],id:'syn',edge_ids:['d1','d2']});
  assert.deepEqual(out.steps.at(-1),{id:'syn',title:'Synthesis',parent_id:null,assignment:{role:'synthesis',instructions:'',settings:{}},inputs:[],outputs:[],targets:[]});
  assert.deepEqual(shape(out),[['a','syn','data'],['b','syn','data']]);
  assert.throws(()=>editWorkflow(two,{type:'synthesis',reads:[]}),/Choose the steps the synthesis reads/);
});

test('the page refuses a pattern only where it cannot build the draft; every admission rule is the owner\'s',()=>{
  assert.equal(workflowPatternBlocker(two,'synthesis',{reads:[]}),'Choose the steps the synthesis reads.');
  assert.equal(workflowPatternBlocker(two,'review',{step:null}),'Choose a step on the drawing.');
  assert.equal(workflowPatternBlocker(two,'reciprocal',{step:'a',partner:'a'}),'Choose two different steps.');
  // what the owner decides is not decided here: an upstream-return choice, a group, a role, the 64/256 bound
  const reads={...copy(starter),steps:[step('write','Draft proposal','builder'),step('review','Independent evidence review','adversary',{},{assignment:{role:'adversary',instructions:'x',settings:{},context:[{kind:'upstream-return',step_id:'write'}]}})]};
  const group={...copy(two),steps:[step('g','Group','group'),...two.steps]},full={...copy(two),steps:Array.from({length:64},(_,i)=>step('s'+i,'S'+i,'builder'))};
  for(const [body,kind,args] of [[reads,'review',{step:'write'}],[starter,'reciprocal',{step:'review'}],[group,'review',{step:'g'}],[full,'review',{step:'s0'}],[full,'reciprocal',{step:'s0'}],[starter,'review',{step:'write'}],[two,'reciprocal',{step:'a',partner:'b'}],[two,'synthesis',{reads:['a','b']}]])assert.equal(workflowPatternBlocker(body,kind,args),null,'no owner rule is applied by the page: '+kind);
  assert.equal(editWorkflow(reads,{type:'review-after',after:'write',id:'rw'}).steps.length,3,'the draft edit itself is the pattern; the owner\'s preview is asked before the press applies it');
  assert.equal(editWorkflow(two,{type:'reciprocal-review',a:'a',b:'b'}).steps.length,4);
  const port=readFileSync(new URL('../src/laplace/web/static_shared/workflow-port.mjs',import.meta.url),'utf8'),blocker=port.slice(port.indexOf('export function workflowPatternBlocker('),port.indexOf('// The draft a pattern makes'));
  for(const gone of ['64','256','upstream-return','group','builder','role','PATTERN_GROWTH'])assert.ok(!blocker.includes(gone),gone+' is not in the page\'s blocker');assert.ok(!port.includes('PATTERN_GROWTH'));
});

test('the owner\'s execution preview decides: its _preview is asked about each pattern\'s draft, and the client keeps no copy of its rules',()=>{
  const v2={...copy(starter),run_policy:{profile:'laplace.research-review/2',max_iterations:3,runtime_seconds:300,advance:'manual',apply:'human',max_admissions:4,deadline_seconds:900,continuation_criteria:'c',exit_criteria:'e'}};
  const made=(body,kind,args)=>workflowPatternResult(body,workflowPatternIntent(kind,{...args,ids:{step:'p1',edge:'p2',feedback:'p3',ra:'p4',rb:'p5',copy:'p6',edges:['p7','p8']}}));
  const cases=[[one,'review',{step:'write'}],[starter,'review',{step:'write'}],[starter,'reciprocal',{step:'write'}],[starter,'synthesis',{reads:['write']}],[two,'review',{step:'a'}],[two,'reciprocal',{step:'a',partner:'b'}],[two,'synthesis',{reads:['a','b']}],[v2,'synthesis',{reads:['write']}]];
  const probes=cases.map(([body,kind,args])=>{const result=made(body,kind,args),probe=workflowPatternProbe(result);
    assert.deepEqual(probe.steps.map(row=>({...row,assignment:{...row.assignment,instructions:''}})),result.steps.map(row=>({...row,assignment:{...row.assignment,instructions:''}})),'the probe is the result with only empty instructions filled');
    for(const [index,row] of probe.steps.entries())assert.equal(row.assignment.instructions,result.steps[index].assignment.instructions||WORKFLOW_PATTERN_PROBE_INSTRUCTION);return probe;});
  const owner=JSON.parse(python('import json,sys\nfrom laplace.pipeline import workflow_operations as O\nout=[]\nfor body in json.load(sys.stdin):\n    ids=[s["id"] for s in body["steps"] if s["assignment"]["role"]!="group"]\n    p=O._preview(body,{"step_ids":ids});out.append([p["support"],[i["code"] for i in p["issues"]]])\nprint(json.dumps(out))',probes));
  assert.deepEqual(owner.map(row=>row[0]),['SUPPORTED_CONFIGURATION','REFUSED_CONFIGURATION','REFUSED_CONFIGURATION','REFUSED_CONFIGURATION','REFUSED_CONFIGURATION','REFUSED_CONFIGURATION','SUPPORTED_CONFIGURATION','REFUSED_CONFIGURATION']);
  assert.deepEqual(owner[1][1],['RESEARCH_REVIEWER_PER_WRITER'],'one writer with two reviewers: the owner runs disjoint pairs, so each writer needs its own reviewer');assert.equal(issueText({code:owner[1][1][0]}),'Each writer needs exactly one reviewer of its own, and each reviewer one writer.');
  assert.ok(owner.every(row=>!row[1].includes('INSTRUCTION_REQUIRED')),'no instruction is asked of a pattern before it is added');
  // R14: no second copy of the owner's admission rules, issue codes or profile constants in the pattern code
  const port=readFileSync(new URL('../src/laplace/web/static_shared/workflow-port.mjs',import.meta.url),'utf8'),editor=readFileSync(new URL('../src/laplace/web/static_shared/workspace-workflow-editor.mjs',import.meta.url),'utf8');
  const block=editor.slice(editor.indexOf('// ROUTE PATTERNS (wave 12, P1)'),editor.indexOf('function paintList('));assert.ok(block.length>1000);
  for(const source of [port,block]){for(const gone of ['workflowExecutionIssues','PROFILE_RUNS','patternMisfit','workflowPatternRule','laplace.research-review','RESEARCH_REQUIRES','INSTRUCTION_REQUIRED','SELECT_TWO_TO_EIGHT','UNSUPPORTED_','running step'])assert.ok(!source.includes(gone),gone+' is not in the client');}
});

test('the definition owner accepts every pattern result (workflow_definitions.validate)',()=>{
  const ids={copy:'step-copy',ra:'step-ra',rb:'step-rb',ra_edge:'edge-1',ra_feedback:'edge-2',rb_edge:'edge-3',rb_feedback:'edge-4'};
  const bodies=[workflowPatternResult(starter,{type:'review-after',after:'write',id:'step-rw',edge_id:'edge-a',feedback_id:'edge-b'}),workflowPatternResult(two,{type:'reciprocal-review',a:'a',b:'b',ids}),workflowPatternResult({...two,steps:[two.steps[0]]},{type:'reciprocal-review',a:'a',b:null,ids}),editWorkflow(two,{type:'synthesis',reads:['a','b'],id:'step-syn',edge_ids:['edge-d1','edge-d2']})];
  const code='import json,sys\nfrom laplace.pipeline import workflow_definitions as D\nbodies=json.load(sys.stdin)\nfor body in bodies:\n    D.validate(body)\nprint("accepted",len(bodies))';
  const result=python(code,bodies);
  assert.match(result,/accepted 4/);
});

test('where a setting comes from, in the owner\'s words; a draft change is unchecked and no value is supplied',()=>{
  const body={...copy(two),steps:[step('g','Review group','group',{effort:'high'}),{...step('a','Draft A','builder',{provider:'claude'}),parent_id:'g'},step('b','Draft B','builder')],settings:{model:'opus'}};
  assert.equal(settingOriginWords({origin:'definition'},body,'a'),'Workflow defaults');
  assert.equal(settingOriginWords({origin:'assignment:a'},body,'a'),'This step');
  assert.equal(settingOriginWords({origin:'assignment:g'},body,'a'),'The group Review group');
  assert.equal(settingOriginWords({origin:'worker-tier-default'},body,'a'),'The provider’s default for this role');
  assert.equal(settingOriginWords({origin:'unset'},body,'a'),'No scope sets it');
  assert.equal(settingOriginWords({origin:'assignment:a',lineage:[{origin:'assignment:a',selected:false},{origin:'existing-session-resolver',kind:'normalization',selected:true}]},body,'a'),'This step · Normalised by the provider');
  assert.deepEqual(declaredWorkflowSettings(body,'a').origins,{provider:'assignment:a',effort:'assignment:g',model:'definition'});
  const saved={definition:copy(body),effective_settings:{b:{provider:{value:'codex',origin:'worker-tier-default'},model:{value:'opus',origin:'definition'},effort:{value:'medium',origin:'worker-tier-default'},input_policy:{value:null,origin:'unset'},unavailable_scopes:['project conversation preferences (not consumed by workers)']}}};
  let line=workflowSettingLineage(body,'b',saved);assert.deepEqual(Object.values(line.rows).map(row=>row.checked),['owner','owner','owner','owner']);assert.equal(line.rows.provider.value,'codex');assert.deepEqual(line.unavailable,['project conversation preferences (not consumed by workers)']);
  const changed=copy(body);changed.steps[2].assignment.settings.provider='claude';line=workflowSettingLineage(changed,'b',saved);
  assert.deepEqual([line.rows.provider.checked,line.rows.provider.value,line.rows.provider.origin],['draft','claude','assignment:b']);
  assert.equal(line.rows.model.checked,'draft','a changed provider invalidates the resolved model');assert.equal(line.rows.input_policy.checked,'owner');
  line=workflowSettingLineage(body,'a',null);assert.deepEqual([line.rows.input_policy.declared,line.rows.input_policy.value],[false,null],'nothing declared, nothing supplied');
});

test('the run policy in words, the arrow legend from the painter table, and a stacked drawing that keeps chains together',()=>{
  const bounds=workflowPolicyBounds({run_policy:{oneOf:[{properties:{profile:{const:'laplace.research-review/1'},max_iterations:{minimum:1,maximum:3},runtime_seconds:{minimum:1,maximum:3600},advance:{enum:['automatic-review','manual']},apply:{const:'human'}}}]}});
  assert.equal(workflowPolicyWords(starter.run_policy,bounds),'Review rounds: at most 2 · Time limit: 300 seconds per admitted step · After a response: Continue to independent review automatically. '+workflowPolicyText({variants:[{...bounds.variants[0],profile:'The owner allows'}]}));
  assert.match(workflowPolicyWords(starter.run_policy,bounds),/The owner allows: review rounds 1–3, up to 3600 seconds per step, changes applied by a person\./);
  assert.match(workflowPolicyWords({...starter.run_policy,advance:'manual'}),/After a response: Wait for my next-step decision\. Check execution reads who applies changes/);
  // one wording per advance value and one limits formatter in the editor
  const source=readFileSync(new URL('../src/laplace/web/static_shared/workspace-workflow-editor.mjs',import.meta.url),'utf8');
  for(const words of ['Continue to independent review automatically','Wait for my next-step decision','the owner allows'])assert.ok(source.split(words).length<=2,words+' is worded once');
  assert.ok(!/short:/.test(source),'no second arrow-kind words table beside the painter\'s marks');
  assert.match(workflowPolicyWords(undefined),/no review policy/);
  assert.equal(workflowEdgeLegend(),Object.values(WORKFLOW_EDGE_MARKS).map(row=>row.legend+'.').join(' '));assert.deepEqual(Object.keys(WORKFLOW_EDGE_MARKS),['control','feedback','data']);
  const body=workflowPatternResult(workflowPatternResult(two,{type:'reciprocal-review',a:'a',b:'b',ids:{ra:'ra',rb:'rb'}}),{type:'synthesis',reads:['a','b'],id:'s'}),{columns,forward}=workflowStageLayout(body);
  assert.deepEqual(workflowReadingOrder(columns,forward).map(row=>row.id),['a','ra','b','rb','s']);
});

// The owner's own execution preview, as the stand-in owner's answer to the pure POST the Design view sends.
const OFFER={read:{http:{method:'POST',url:'/work/workflow-definitions',payload:{facet:'execution-preview'}},read_only:true},required_inputs:['definition','scope','step_ids'],meaning:'Pure draft capability preview; no save, preparation, permission or run effect.'};
const ownerPreviews=new Map();
async function ownerPreview(payload,scope_id){
  const key=JSON.stringify(payload);if(!ownerPreviews.has(key))ownerPreviews.set(key,JSON.parse(python('import json,sys\nfrom laplace.pipeline import workflow_operations as O, workflow_definitions as D\np=json.load(sys.stdin)\ntry:\n    D.validate(p["definition"])\nexcept D.Refused as exc:\n    print(json.dumps({"refused":{"error":str(exc),**exc.details}}));raise SystemExit\nr=O._preview(p["definition"],{"step_ids":p["step_ids"]})\nprint(json.dumps({"support":r["support"],"issues":r["issues"]}))',payload)));
  const value=ownerPreviews.get(key);
  // as the door answers an owner refusal (workflow_definitions_surface: 422 with the owner's code) and workflowRequest throws it
  if(value.refused)throw Object.assign(Error(value.refused.error),{result:copy(value.refused),status:422});
  return {schema_version:'laplace.workflow-operation/1',view:'execution-preview',read_only:true,scope_id,scope:copy(payload.scope),reference:null,support:value.support,issues:copy(value.issues),roles:payload.step_ids.map(id=>({step_id:id})),execution_permitted:false,basis:'sha256:'+'0'.repeat(64),definition_digest:'sha256:'+'1'.repeat(64),selected_step_ids:copy(payload.step_ids),transport_request:{encoding:'utf8-exact-request-body',sha256:await feedbackWireDigest(JSON.stringify(payload))}};
}
async function mounted(definition,{offer=OFFER,fail=false,select='a'}={}){
  const dom=installDOM(),oldMedia=globalThis.matchMedia;globalThis.matchMedia=()=>({matches:false,addEventListener(){},removeEventListener(){}});document.addEventListener=()=>{};document.removeEventListener=()=>{};
  const host=new Node('main');host.addEventListener=()=>{};host.removeEventListener=()=>{};document.body.append(host);const writes=[],entries=new Map(),requests=[];const storage={getItem:k=>entries.get(k)??null,setItem:(k,v)=>{writes.push(v);entries.set(k,v);},removeItem:k=>entries.delete(k)};
  const owner={scope_id:'design',scope:{kind:'owned-workspace'},definition_id:'WDEF-design',version:'v1',is_current:true,definition:copy(definition),read_handle:{http:{method:'GET',url:'/design?version=v1'}},
    effective_settings:{a:{provider:{value:'claude',origin:'assignment:a',lineage:[{origin:'assignment:a',selected:true}]},model:{value:'opus',origin:'assignment:a'},effort:{value:'high',origin:'worker-tier-default'},input_policy:{value:null,origin:'unset'},unavailable_scopes:['global/subsystem policy mutation','project conversation preferences (not consumed by workers)']}},
    actions:{save:{permitted:true,http:{method:'POST',url:'/save'},payload:{definition_id:'WDEF-design',expected_revision:'v1'}}}};
  const listing={scope_id:'design',scope:owner.scope,definitions:[{definition_id:'WDEF-design',title:definition.title,read:owner.read_handle}],...(offer?{execution_preview:copy(offer)}:{})};
  const editor=await mountWorkflowEditor(host,{storage,request:async(path,payload)=>{requests.push({path,payload:copy(payload)});
    if(payload){assert.equal(path,'/work/workflow-definitions');assert.equal(payload.facet,'execution-preview','only the owner\'s pure execution preview is sent');if(fail)throw Error('The workflow owner is unavailable.');return ownerPreview(payload,'design');}
    return copy(path==='/work/workflow-definitions'?listing:owner);}});
  await editor.port.dispatch({type:'select',id:'WDEF-design',read:owner.read_handle});await editor.port.dispatch({type:'step',id:select});
  return {host,editor,writes,requests,restore(){editor.destroy();globalThis.matchMedia=oldMedia;dom.restore();}};
}
// the owner's answers arrive after the paint: wait until no pattern is still asking
async function answered(host){for(let i=0;i<400;i++){if(!host.all().some(n=>n.className==='workflow-pattern-note'&&/^Asking the owner/.test(n.textContent)))return;await new Promise(ok=>setTimeout(ok,10));}throw Error('the owner\'s answers did not arrive');}
const OWNED=new Set(['stage','stage-insert','stage-earlier','stage-later','stage-remove','pattern-review','pattern-reciprocal','pattern-partner','pattern-reads','pattern-synthesis','setting-step','setting-workflow','setting-identity','inspector-part','stage-nest','stage-position','stage-nudge','relation-add','design-view','graph-mode','graph-step','list-step','relation-remove','explain','explain-guide','context-choice','handoff-target'].map(id=>'workflow:'+id));
const controls=host=>host.all().filter(n=>n.dataset?.control).map(n=>({id:n.dataset.control,owner:n.dataset.controlOwner??null}));
const note=b=>b.parentElement.all?.().find(n=>n.className==='workflow-pattern-note')?.textContent||[...(b.parentElement.children||[])].find(n=>n.className==='workflow-pattern-note')?.textContent||'';

test('mounted Design: the column says each origin, a pattern is one draft edit that selects what it made, every control is declared',async()=>{
  const s=await mounted(two);try{
    await answered(s.host);
    const rows=s.host.all().filter(n=>n.dataset?.settingKey).map(n=>[n.dataset.settingKey,n.dataset.settingChecked,n.querySelector('.workflow-setting-value').textContent,n.querySelector('.workflow-setting-origin').textContent]);
    assert.deepEqual(rows,[['provider','owner','claude','This step'],['model','owner','opus','This step'],['effort','owner','high','The provider’s default for this role'],['input_policy','owner','Not set','No scope sets it']]);
    assert.match(s.host.textContent,/Unavailable for a workflow step, in the owner’s words: project conversation preferences \(not consumed by workers\)\./);
    assert.ok(s.host.all().some(n=>n.tag==='legend'&&n.textContent==='Set for this step')&&s.host.all().some(n=>n.tag==='legend'&&n.textContent==='Set for the whole workflow'),'the column names the scope a change writes');
    for(const row of controls(s.host)){assert.ok(declared.has(row.id),'undeclared '+row.id);const d=declared.get(row.id);assert.ok(d.does||!['workflow:pattern-review','workflow:pattern-reciprocal','workflow:pattern-synthesis'].includes(row.id));if(OWNED.has(row.id))assert.ok(row.owner!==null,row.id+' carries the step, setting, edge or part it acts on');}
    for(const id of ['workflow:pattern-review','workflow:pattern-reciprocal','workflow:pattern-synthesis','workflow:setting-step','workflow:setting-workflow','workflow:setting-identity','workflow:stage'])assert.ok(controls(s.host).some(row=>row.id===id),id+' is painted');
    assert.match(declared.get('workflow:pattern-review').does,/dashed findings-back arrow/);assert.match(declared.get('workflow:pattern-reciprocal').does,/four steps and four arrows/);assert.match(declared.get('workflow:pattern-synthesis').does,/synthesis role .* dotted data-input arrow from each chosen step/);for(const id of ['review','reciprocal','synthesis'])assert.match(declared.get('workflow:pattern-'+id).does,/Offered only where the owner's execution check, asked about the draft it makes .* runs it; otherwise it is greyed with the owner's sentence beside it and pressing applies nothing\. Reads Check first/);
    // without a review policy the owner runs no findings sent back: the review patterns are greyed with the owner's own sentences
    const previews=s.requests.filter(row=>row.payload);assert.equal(previews.length,3,'one owner preview per pattern');
    for(const label of ['Add a review of this step','Make these two review each other']){const b=findButton(s.host,label);assert.equal(b.disabled,true,label);assert.match(note(b),/^Not offered: .*A selected step has an unsupported or unselected input\./,label);}
    assert.ok(!s.host.all().some(n=>n.className==='workflow-pattern-rule'),'no rule of the page\'s own under the patterns');
    assert.equal(findButton(s.host,'Add a synthesis that reads these').disabled,false);
    assert.match(s.host.all().find(n=>n.className==='workflow-reads-line').textContent,/^Receives: no arrow comes in\. Hands on: no arrow goes out\.$/);
    const before=s.writes.length,asked=s.requests.length;await findButton(s.host,'Add a synthesis that reads these').onclick();
    assert.equal(s.requests.slice(asked).filter(row=>row.payload).length,0,'the press reuses the owner\'s answer for this exact draft');
    const draft=s.editor.port.snapshot().draft.definition;assert.equal(draft.steps.length,3);assert.equal(s.editor.port.snapshot().step,draft.steps[2].id,'the new synthesis is chosen');assert.deepEqual([draft.steps[2].title,draft.steps[2].assignment.role,draft.steps[2].assignment.instructions],['Synthesis','synthesis',''],'the stand-in instruction is never applied');
    const asked2=previews[2].payload.definition;assert.deepEqual(asked2.steps.map(row=>row.id),draft.steps.map(row=>row.id),'the owner was asked about the draft the press applied');assert.deepEqual(asked2.edges,draft.edges);
    assert.equal(s.host.all().find(n=>n.className==='workflow-reads-line').textContent,'Receives: Draft A (intended input). Hands on: no arrow goes out.','the arrow in the words the execution check uses');
    assert.ok(s.writes.length>before);
    await answered(s.host);assert.match(note(findButton(s.host,'Add a synthesis that reads these')),/^Not offered: Choose one original-parent synthesis\./,'a second synthesis is refused in the owner\'s words');
    const after=s.host.all().filter(n=>n.dataset?.settingKey).map(n=>[n.dataset.settingKey,n.dataset.settingChecked,n.querySelector('.workflow-setting-origin').textContent]);
    assert.deepEqual(after[0],['provider','draft','Unchecked: the owner resolves it when you Save'],'an unsaved step has no resolved value and none is supplied');
  }finally{s.restore();}
});

test('mounted Design on the starter: refused patterns carry the owner\'s sentence and a press applies nothing; a review is offered on the one writer',async()=>{
  let s=await mounted(starter,{select:'write'});try{
    await answered(s.host);
    for(const label of ['Add a review of this step','Make these two review each other']){const b=findButton(s.host,label);assert.equal(b.disabled,true);assert.equal(note(b),'Not offered: Each writer needs exactly one reviewer of its own, and each reviewer one writer.',label+': its draft leaves the writer with more than one reviewer');}
    const syn=findButton(s.host,'Add a synthesis that reads these');assert.equal(syn.disabled,true);assert.equal(note(syn),'Not offered: Synthesis: The synthesis reads selected steps through result arrows only.','the pattern draws a dotted data arrow into the synthesis; the review profile reads a synthesis only through solid result arrows (compile_plan refuses the same, UNSUPPORTED_SYNTHESIS_INPUT)');
    const was=copy(s.editor.port.snapshot().draft?.definition||s.editor.port.snapshot().read.value.definition);await findButton(s.host,'Add a review of this step').onclick();
    assert.deepEqual(s.editor.port.snapshot().draft?.definition||s.editor.port.snapshot().read.value.definition,was,'nothing is applied on a refusal');
  }finally{s.restore();}
  s=await mounted(one,{select:'write'});try{
    await answered(s.host);const b=findButton(s.host,'Add a review of this step');assert.equal(b.disabled,false);await b.onclick();
    const draft=s.editor.port.snapshot().draft.definition;assert.deepEqual(draft.steps.map(row=>row.assignment.role),['builder','adversary']);assert.deepEqual(shape(draft).map(row=>row[2]),['control','feedback']);
  }finally{s.restore();}
});

test('mounted Design where the owner\'s definition check refuses a pattern\'s draft: greyed with the owner\'s sentence, nothing applied, no Check first',async()=>{
  // Independent evidence review reads the result of Draft proposal through the arrow a review after Draft would take over;
  // the owner's execution preview runs workflow_definitions.validate first and refuses CONTEXT_NOT_AN_UPSTREAM_RETURN
  const reads={...copy(one),steps:[step('write','Draft proposal','builder'),{...step('review','Independent evidence review','adversary'),assignment:{role:'adversary',instructions:'x',settings:{},context:[{kind:'upstream-return',step_id:'write'}]}}],edges:[{id:'draft-review',from:'write',to:'review',kind:'control'}]};
  const s=await mounted(reads,{select:'write'});try{
    await answered(s.host);const b=findButton(s.host,'Add a review of this step');
    assert.equal(b.textContent,'Add a review of this step','not Check first: the owner answered');assert.equal(b.disabled,true);
    assert.equal(note(b),'Not offered: Independent evidence review: Owner refusal: context not an upstream return');
    assert.equal(issueText({code:'CONTEXT_NOT_AN_UPSTREAM_RETURN'}),'Owner refusal: context not an upstream return','the existing refusal mapping, no sentence of the page\'s own');
    const was=JSON.stringify(s.editor.port.snapshot().draft||null),asked=s.requests.length;await b.onclick();
    assert.equal(JSON.stringify(s.editor.port.snapshot().draft||null),was,'nothing is applied on the owner\'s refusal');assert.equal(s.requests.length,asked,'the refusal read for this exact draft is reused');
    assert.ok(!/would take over that arrow|Change that choice first/.test(s.host.textContent),'no sentence of the page\'s own');
  }finally{s.restore();}
  // the owner's bound, in the owner's own words
  const full={...copy(one),steps:Array.from({length:64},(_,i)=>step('s'+i,'S'+i,'builder')),edges:[]};
  const t=await mounted(full,{select:'s0'});try{
    await answered(t.host);const b=findButton(t.host,'Add a review of this step');assert.equal(b.disabled,true);assert.equal(note(b),'Not offered: At most64steps and256edges');
  }finally{t.restore();}
});

test('mounted Design without the owner\'s execution offer, or when its read fails: each pattern says Check first and does nothing',async()=>{
  for(const options of [{offer:null},{fail:true}]){const s=await mounted(two,options);try{
    await answered(s.host);const buttons=['workflow:pattern-review','workflow:pattern-reciprocal','workflow:pattern-synthesis'].map(id=>s.host.all().find(n=>n.dataset?.control===id));
    for(const b of buttons){assert.equal(b.textContent,'Check first');assert.equal(b.disabled,true);}
    assert.match(note(buttons[2]),/^Add a synthesis that reads these: the owner’s execution check could not be read for the result\./);
    const was=JSON.stringify(s.editor.port.snapshot().draft||null);await buttons[2].onclick();assert.equal(JSON.stringify(s.editor.port.snapshot().draft||null),was,'nothing is applied');
  }finally{s.restore();}}
});
