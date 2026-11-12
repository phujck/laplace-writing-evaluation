// HUMAN CHANGE APPROVAL (M5 2026-10-16, WORK-editor-human-change-approval-20261015). The author's steer: "I should
// just be able to approve a change." The shared resolution controller offers Approve change on the owner's exact
// comparison (the proposal's hunks proposed, later author edits kept, a genuine overlap waits for an explicit
// choice), runs the owner's preview then apply exactly once, and says in plain words what changed evidence does and
// does not mean. The real walk renderer prepares that comparison automatically, keeps Keep current beside it, asks for
// a passage only when the owner says the target is ambiguous, and shows terminal suggestions as saved outcomes.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import * as editing from '../src/laplace/web/static_shared/manuscript-editing.mjs';
import {approvalChoices,mountProposalResolution,validateResolutionPreparation} from '../src/laplace/web/static_shared/proposal-resolution.mjs';
import {installDOM,Node,findButton} from './helpers/evidence_reader_harness.mjs';
import {humanWire} from './helpers/human_resolution_fixture.mjs';
import {walkDeclarations} from './helpers/walk_source.mjs';

const [first,overlap,third]=humanWire.prepared.hunks.map(hunk=>hunk.id);
const mount=(value,posts,extra={})=>{const host=new Node('section'),state={};const controller=mountProposalResolution(host,{project:'fixture',value,state,approve:true,
  request:async(path,payload)=>{posts.push(payload);return payload.decision==='preview-resolution'?humanWire.preview:humanWire.receipt;},...extra});return {host,state,controller};};

test('approval takes the proposal, keeps later author edits and never resolves an overlap on the author\'s behalf',()=>{
  const choices=approvalChoices(humanWire.prepared);
  assert.deepEqual(choices,[{hunk_id:first,choice:'proposed'},null,{hunk_id:third,choice:'proposed'}],'a conflict hunk has no implied choice');
  const later=structuredClone(humanWire.prepared);later.hunks[1].kind='current';
  assert.deepEqual(approvalChoices(later)[1],{hunk_id:overlap,choice:'current'},'an edit made after the suggestion is kept');
  assert.deepEqual(approvalChoices(humanWire.prepared,{[overlap]:{choice:'custom',text:'Mine'}})[1],{hunk_id:overlap,choice:'custom',text:'Mine'});
});

test('Approve change waits for an explicit choice on the overlapping change, then previews and applies exactly once',async()=>{
  const dom=installDOM(),posts=[],applied=[];
  try{
    const {host}=mount(humanWire.prepared,posts,{onApplied:(...args)=>applied.push(args)});dom.body.append(host);
    const approve=findButton(host,'Approve change');
    assert.equal(approve.disabled,true);assert.match(host.textContent,/One change overlaps manuscript edits made after this suggestion\. Choose Keep current, Use proposed or Custom for it before approving/);
    await approve.click();assert.equal(posts.length,0,'nothing is sent while the overlap is undecided');
    await findButton(host,'Next change').click();await findButton(host,'Use proposed').click();
    assert.equal(findButton(host,'Approve change').disabled,false);assert.match(host.textContent,/Your choices are set/);
    await findButton(host,'Approve change').click();
    assert.deepEqual(posts.map(row=>row.decision),['preview-resolution','apply-resolution'],'one preview, one application');
    assert.deepEqual(posts[1].choices,[{hunk_id:first,choice:'proposed'},{hunk_id:overlap,choice:'proposed'},{hunk_id:third,choice:'proposed'}]);
    assert.equal(applied.length,1);assert.match(host.textContent,/Resolved revision applied\. Scientific review obligations remain separate/);
    assert.equal(findButton(host,'Approve change').disabled,true,'an applied change cannot be approved again');
  }finally{dom.restore();}
});

test('changed supporting evidence is named as such and approval decides only the displayed text',()=>{
  const dom=installDOM(),posts=[];
  try{
    const value=structuredClone(humanWire.prepared);value.hunks[1].kind='current';value.review_obligations=[{reason:'Cited result table changed after this suggestion.'}];
    const {host}=mount(value,posts);dom.body.append(host);
    assert.match(host.textContent,/Supporting inputs changed since this suggestion\. Approving decides the displayed text only; it does not renew that evidence or record scientific acceptance/);
    assert.match(host.textContent,/One later manuscript edit outside the suggestion is kept as it is/);
    assert.doesNotMatch(host.textContent,/overlaps/);assert.equal(findButton(host,'Approve change').disabled,false);
  }finally{dom.restore();}
});

test('Edit suggestion starts from the proposal and approves the edited text through the same owner',async()=>{
  const dom=installDOM(),posts=[];
  try{
    const value=structuredClone(humanWire.prepared);value.hunks[1].kind='proposal';
    const {host,state}=mount(value,posts);dom.body.append(host);
    await findButton(host,'Edit suggestion').click();
    const complete=host.querySelectorAll('textarea').at(-1);assert.equal(complete.value,value.proposed,'a clean suggestion is edited from its own text');
    complete.value=value.proposed.replace('Rose','Crimson');complete.oninput();
    assert.equal(state.full_text,true);await findButton(host,'Approve edited text').click();
    assert.deepEqual(posts.map(row=>row.decision),['preview-resolution','apply-resolution']);assert.match(posts[1].resolved_after,/Crimson statement/);
  }finally{dom.restore();}
});

// ---- the real walk renderer (walk-review.mjs showProposal) over the DOM-free double the scope tests use

class Stub {
  constructor(tag,cls,text=''){this.tag=tag;this.className=cls;this.textContent=text;this.children=[];this.dataset={};this.attrs={};this.offsetTop=10;this.hidden=false;this.isConnected=true;
    this.classList={add(){},remove(){}};}
  append(...nodes){this.children.push(...nodes);}
  prepend(...nodes){this.children.unshift(...nodes);}
  replaceChildren(...nodes){this.children=[...nodes];}
  before(){}
  setAttribute(k,v){this.attrs[k]=v;}
  all(){return [this,...this.children.flatMap(n=>n.all?n.all():[])];}
  querySelectorAll(selector){return this.all().filter(n=>n.tag===selector);}
}
const helpers=Object.fromEntries(readFileSync(new URL('../src/laplace/web/static_shared/walk-review.mjs',import.meta.url),'utf8')
  .match(/import \{([^}]*)\} from "\/shared\/manuscript-editing\.mjs";/)[1].split(',').map(n=>n.trim()).filter(Boolean).map(n=>[n,editing[n]]));
function walk({prepared,mounts}){
  let inserted=null;const block={id:'current-block',src:{file:'chapter.tex',lineStart:50,lineEnd:60},el:{before:n=>inserted=n,classList:{add(){}}},bodyEl:{setAttribute(){}}};
  const ctx={docEl:{querySelectorAll:()=>[],prepend:n=>inserted=n},proposalUiStates:new Map(),manuscriptDraftRanges:()=>[],S:{corpus:'fixture',blocks:[block]},proposalView:null,
    clearObjectSelection(){},captureFocus:()=>({}),clearProposal(){},suspendAuthorChanges(){},srcOf:b=>b.src,el:(...a)=>new Stub(...a),asChrome:n=>n,
    proposalModels:(host,models,id)=>{const bs=(models||[]).map((text,i)=>({id:id+i,el:new Stub('p','',text)}));host.append(...bs.map(b=>b.el));return bs;},
    paintRevisionDifference:()=>({before:[],after:[]}),syncRevisionHighlights(){},measure(){},restoreFocus(){},emit(){},paper:{scrollTop:0},attentionBlockId:null,noteAttention(){},
    localStorage:{getItem:()=>null,removeItem(){},setItem(){}},proposalResolutionControllers:new Set(),validateResolutionPreparation,
    mountProposalResolution:(host,options)=>{mounts.push(['comparison',options]);host.append(new Stub('p','','comparison'));return {destroy(){}};},
    mountResolutionTarget:(host,options)=>{mounts.push(['picker',options]);host.append(new Stub('p','','Choose the current passage'));return {destroy(){}};},
    resolutionAuthorLabel:()=>'author',pendingSuccessorLinks(){},...helpers};
  vm.createContext(ctx);vm.runInContext(walkDeclarations('showRecordedProposal','showProposal')+';this.render=showProposal',ctx);
  return {ctx,inserted:()=>inserted};
}
const conflictEdit=()=>({edit_id:'e',file:'chapter.tex',line_start:999,line_end:1002,status:'conflict',allowed_actions:['keep-current'],resolution_available:false,
  current_mapping:'unproven-historical-location',before:'Historical words',before_blocks:['Historical words'],after:'Proposed words',after_blocks:['Proposed words'],
  resolution_action:{permitted:true},basis_currentness:'STALE',basis_reason:'inputs changed'});
const settle=()=>new Promise(resolve=>setImmediate(resolve));

for(const [name,prepared,kind] of [['an unambiguous current passage',humanWire.prepared,'comparison'],['a genuinely ambiguous target',humanWire.target_required,'picker']]){
  test('the walk prepares the owner comparison automatically for '+name+' and keeps Keep current beside it',async()=>{
    const mounts=[],prepares=[];const {ctx,inserted}=walk({mounts});
    ctx.render({turn_id:'t',proposal_version:'version',reviewable:true,edits:[conflictEdit()]},{onDecision:async()=>({}),onRequestChanges(){},onInspectCurrentFile(){},
      onPrepareResolution:async(edit,target)=>{prepares.push([edit.edit_id,target]);return structuredClone(prepared);},onResolutionRequest:async()=>({})});
    await settle();
    assert.deepEqual(prepares,[['e',undefined]],'prepared without any click, with no guessed target');
    assert.equal(mounts.length,1);assert.equal(mounts[0][0],kind,'a passage is chosen only when the owner says the target is ambiguous');
    if(kind==='comparison')assert.equal(mounts[0][1].approve,true);
    const buttons=inserted().all().filter(n=>n.tag==='button'),visible=label=>buttons.find(n=>n.textContent===label&&!n.hidden);
    assert.ok(visible('Keep current'));assert.ok(visible('Hide current comparison'));
    assert.equal(buttons.some(n=>n.textContent==='Resolve individual changes'),false);
    assert.match(inserted().all().map(n=>n.textContent).join(' '),/original location no longer matches the manuscript\. The current passage is compared below; you choose a passage only if it cannot be found unambiguously/);
  });
}

test('an applied or superseded suggestion is shown as its saved outcome, never as awaiting approval',()=>{
  for(const [state,label] of [['applied','Accepted'],['superseded','Superseded'],['resolved-into-successor','Resolved in a later revision']]){
    const mounts=[];const {ctx,inserted}=walk({mounts});
    ctx.render({turn_id:'t',proposal_version:'version',proposal_state:state,edits:[{...conflictEdit(),status:state==='applied'?'applied':state}]},{onDecision:async()=>({})});
    const text=inserted().all().map(n=>n.textContent);
    assert.ok(text.includes(label),state);
    assert.equal(text.some(t=>/^(Approve change|Keep current|Replace current passage)$/.test(t)),false,state);
    assert.equal(mounts.length,0);
  }
});
