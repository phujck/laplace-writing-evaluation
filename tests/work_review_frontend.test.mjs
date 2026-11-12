// WORK REVIEW LIFECYCLE, FRONTEND (M5 2026-10-16, WL-T6). The selected review-managed Work shows one surface from the
// owner's facet (outcome, currentness, independence, the owner's next step, pending joins) and ONE phase recorder whose
// phases, guard and HTTP door all come from allowed_actions.work_review. A draft keeps a stable request_id so a retry
// replays (the owner never records twice); the pending-join recovery is the owner-issued request; read-only records nothing.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {mountOperatorWork} from '../src/laplace/web/static_shared/workspace-work.mjs';
import {installDOM,Node,findButton} from './helpers/evidence_reader_harness.mjs';
import {reviewAction} from './helpers/work_preparation.mjs';

const facet=(extra={})=>({managed:true,remaining:['source','guide'],reviews_recorded:1,synthesis:null,followups:[],pending_joins:[],
  handoff:{id:'PHASE-h1',obligations:['source','guide'],object:{kind:'source'},producer:'codex:fixture-model',producer_origin:'native'},
  next:{kind:'review',obligation_id:'guide',says:'Record the guide review of "Guide review".'},
  obligations:[{id:'source',scope:'source',label:'Source review',required:true,independent:true,status:'ACCEPTED',currentness:'CURRENT',independence:'SELF',review_id:'PHASE-r1',reviewer:'codex:fixture-model',satisfied:false,currentness_reason:'Every reviewed pin matches current bytes.'},
    {id:'guide',scope:'guide',label:'Guide review',required:true,independent:true,status:'AWAITING_REVIEW',currentness:'UNKNOWN',satisfied:false}],...extra});
const detail=(review=facet(),phases=['handoff','review','synthesis','followup'])=>({project:'fixture',view:'detail',read_cut:{revision:'cut'},blockers:[],children:{items:[]},dependants:{items:[]},
  task:{id:'A',title:'Lifecycle',goal:'Ship',status:'open',recorded_status:'open',review},
  allowed_actions:{work_review:reviewAction('A','sha256:guard-1',review,phases)}});
async function mount(read,{readOnly=false}={}){
  const host=new Node('main');globalThis.document.body.append(host);
  const posts=[];const request=async(path,payload)=>{if(payload){posts.push({path,payload});return read.post?.(payload)??{status:'RECORDED'};}return read.detail();};
  await mountOperatorWork(host,{project:'fixture',summary:{tasks:[{id:'A',title:'Lifecycle',status:'open'}]},initialWork:'A',readOnly,request});
  return {host,posts};
}
const section=host=>host.all().find(n=>n.dataset?.control==='work:review');
const options=select=>select.children.filter(n=>n.tag==='option').map(n=>n.value);

test('one review surface: outcome, self-assessment named as such, the owner next step and only the allowed phases',async()=>{
  const dom=installDOM();try{
    const {host}=await mount({detail:()=>detail(facet(),['review','followup'])});
    const box=section(host);assert.ok(box,'the work:review control renders for review-managed Work');
    assert.match(box.textContent,/0 of 2 required review obligations satisfied · 1 reviews recorded/);
    assert.match(box.textContent,/Handed off by codex:fixture-model \(native\)/);
    assert.match(box.textContent,/self-assessment, does not satisfy/);
    assert.match(box.textContent,/Record the guide review of "Guide review"\./,'the owner\'s next step, verbatim');
    const choose=box.all().find(n=>n.tag==='select');
    assert.deepEqual(options(choose),['review','followup'],'review mode: no handoff or synthesis is offered');
    assert.equal(choose.value,'review','the recorder opens on the owner\'s next step');
  }finally{dom.restore();}
});

test('a recorded phase posts the owner guard to its door once; a failed post keeps the draft and the same request',async()=>{
  const dom=installDOM();try{
    let fail=true;const {host,posts}=await mount({detail:()=>detail(),post:()=>{if(fail){fail=false;throw Error('connection lost');}return {status:'RECORDED'};}});
    let box=section(host);const form=box.all().find(n=>n.tag==='form');
    const field=name=>form.all().find(n=>n.name===name);
    field('obligation_id').value='guide';field('verdict').value='HOLD';field('findings').value='F1: Missing narrow check';form.oninput();
    await form.onsubmit({preventDefault(){}});
    assert.equal(posts.length,1);assert.equal(posts[0].path,'/work/review');
    const sent=posts[0].payload;
    assert.deepEqual([sent.project,sent.id,sent.phase,sent.expected_work_revision,sent.handoff_id,sent.obligation_id,sent.verdict],['fixture','A','review','sha256:guard-1','PHASE-h1','guide','HOLD']);
    assert.deepEqual(sent.findings,[{id:'F1',summary:'Missing narrow check'}]);
    assert.match(sent.request_id,/^ui-review-[0-9a-f-]{18}$/);
    assert.match(form.textContent,/Your draft and its request are retained; the same request never records twice/);
    await form.onsubmit({preventDefault(){}});
    assert.equal(posts[1].payload.request_id,sent.request_id,'a retry replays the same request');
    assert.match(host.textContent,/Review phase recorded\./);
  }finally{dom.restore();}
});

test('a pending follow-up join is completed with the owner-issued request and the current guard',async()=>{
  const dom=installDOM();try{
    const recover={id:'A',phase:'followup',request_id:'req-follow-1',finding:'F1 guard',closure:'required',child:{id:'WORK-followup-1',title:'Guard',goal:'Refuse'}};
    const {host,posts}=await mount({detail:()=>detail(facet({pending_joins:[{child_id:'WORK-followup-1',closure:'required',finding:'F1 guard',request_id:'req-follow-1',recover}],next:{kind:'recover-join',says:'Recover the pending follow-up join with the same request.'}})),
      post:()=>({status:'RECOVERED'})});
    assert.match(section(host).textContent,/The follow-up for “F1 guard” is created, but its required join is pending/);
    await findButton(host,'Complete the pending follow-up').click();
    assert.deepEqual(posts[0].payload,{project:'fixture',...recover,expected_work_revision:'sha256:guard-1'});
    assert.match(host.textContent,/The pending follow-up join was completed\./);
  }finally{dom.restore();}
});

test('read-only Work shows the review standing and records nothing; legacy Work shows no review surface',async()=>{
  const dom=installDOM();try{
    const {host,posts}=await mount({detail:()=>detail()},{readOnly:true});
    assert.ok(section(host));assert.equal(section(host).all().some(n=>n.tag==='form'),false);assert.equal(posts.length,0);
    const legacy=detail(null);delete legacy.allowed_actions.work_review;
    const plain=await mount({detail:()=>legacy});
    assert.equal(section(plain.host),undefined);
  }finally{dom.restore();}
});
