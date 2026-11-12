// WORK REVIEW RECORDER REPAIR (M5 2026-10-16, repair1 WR-R4/WR-R5). A review draft carries the exact basis it was written
// against; after a reinspection moves the guard it posts nothing until the author explicitly adopts the inspected basis
// (a new request). A completed request is never re-offered; newer typing during a post is a new operation; a pending
// outcome keeps its request. Success focuses the review heading; a replaced Work is not repainted. The exact review
// records are read lazily through the owner's view:review handles and a different record is refused.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {mountOperatorWork} from '../src/laplace/web/static_shared/workspace-work.mjs';
import {installDOM,Node,findButton} from './helpers/evidence_reader_harness.mjs';
import {reviewAction} from './helpers/work_preparation.mjs';

const reviewRead=phase=>({operation:'project',payload:{namespace:'fixture',view:'review',id:'A',phase_id:phase},
  http:{method:'GET',url:'/work/state?project=fixture&view=review&id=A&phase_id='+phase}});
const facet=()=>({managed:true,remaining:['guide'],reviews_recorded:1,synthesis:null,followups:[],pending_joins:[],
  handoff:{id:'PHASE-h1',obligations:['guide'],object:{kind:'source'},producer:'codex:fixture-model',producer_origin:'native',pins_total:2,evidence_total:0,read:reviewRead('PHASE-h1')},
  next:{kind:'review',obligation_id:'guide',says:'Record the guide review of "Guide review".'},
  obligations:[{id:'guide',scope:'guide',label:'Guide review',required:true,independent:true,status:'HOLD',currentness:'CURRENT',independence:'UNKNOWN',
    review_id:'PHASE-r1',reviewer:'claude:fixture',reviewer_verified:false,satisfied:false,review_read:reviewRead('PHASE-r1')}]});
const detail=(id,guard)=>({project:'fixture',view:'detail',read_cut:{revision:'cut'},blockers:[],children:{items:[]},dependants:{items:[]},
  task:{id,title:'Lifecycle '+id,goal:'Ship',status:'open',recorded_status:'open',review:id==='A'?facet():null},
  allowed_actions:id==='A'?{work_review:reviewAction(id,guard,facet(),['review'])}:{}});
const phaseRecord=(work='A')=>({project:'fixture',view:'review',work_id:work,read_cut:{revision:'cut'},phase:{id:'PHASE-r1',revision:'sha256:p',
  rows:[{id:'PHASE-r1',phase:'review',verdict:'HOLD',actor:{actor:'claude:fixture',origin:'external',verified:false},findings:[{id:'F1',summary:'Missing narrow check'}],
    pins:{'paper/a.tex':'sha256:aa'},ts:'2026-10-16T10:00:00Z',basis:{work_revision:'sha256:guard-1'}}]}});

async function mount(state){
  const host=new Node('main');globalThis.document.body.append(host);
  const posts=[],reads=[];
  const request=async(path,payload)=>{
    if(payload){posts.push({path,payload});return state.post?state.post(payload):{status:'RECORDED'};}
    reads.push(path);const q=new URL(path,'http://local/').searchParams;
    if(q.get('view')==='review')return state.review?state.review(q):phaseRecord();
    return detail(q.get('id')||'A',state.guard);};
  const controller=await mountOperatorWork(host,{project:'fixture',summary:{tasks:[{id:'A',title:'Lifecycle A',status:'open'},{id:'B',title:'Lifecycle B',status:'open'}]},initialWork:'A',request});
  return {host,posts,reads,controller};
}
const section=host=>host.all().find(n=>n.dataset?.control==='work:review');
const formOf=host=>section(host).all().find(n=>n.tag==='form');
const field=(form,name)=>form.all().find(n=>n.name===name);
const type=(host,text)=>{const form=formOf(host);field(form,'verdict').value='HOLD';field(form,'findings').value=text;form.oninput();return form;};
const submit=host=>formOf(host).onsubmit({preventDefault(){}});

test('a draft written before a reinspection posts nothing until its inspected basis is adopted, then posts that guard as a new request',async()=>{
  const dom=installDOM();try{
    const state={guard:'sha256:guard-1'};const {host,posts,controller}=await mount(state);
    type(host,'F1: Written against guard one');
    const first=controller.capture().drafts.A.review.request_id;
    state.guard='sha256:guard-2';await controller.select('A');
    assert.match(formOf(host).textContent,/written against an earlier inspection/);
    assert.equal(field(formOf(host),'findings').value,'F1: Written against guard one','the text is retained');
    await submit(host);assert.equal(posts.length,0,'a stale draft posts nothing');
    await findButton(host,'Use this inspected basis for my draft').click();
    await submit(host);
    assert.equal(posts.length,1);assert.equal(posts[0].payload.expected_work_revision,'sha256:guard-2');
    assert.notEqual(posts[0].payload.request_id,first,'adopting a new basis is a new request');
    assert.deepEqual(posts[0].payload.findings,[{id:'F1',summary:'Written against guard one'}]);
  }finally{dom.restore();}
});

test('a completed request is never re-offered: the next record uses a new id; a pending outcome keeps the same id',async()=>{
  const dom=installDOM();try{
    const outcomes=['RECORDED','PENDING_RECEIPT'];const state={guard:'sha256:guard-1',post:()=>({status:outcomes.shift()||'RECORDED'})};
    const {host,posts,controller}=await mount(state);
    type(host,'F1: One');await submit(host);
    assert.equal(controller.capture().drafts.A,undefined,'success clears the draft');
    assert.equal(field(formOf(host),'findings').value,'','the repainted form never re-offers the completed text');
    type(host,'F2: Two');await submit(host);
    assert.notEqual(posts[1].payload.request_id,posts[0].payload.request_id,'a second record is a new operation');
    assert.equal(controller.capture().drafts.A.review.request_id,posts[1].payload.request_id,'a pending outcome keeps its request');
    await submit(host);assert.equal(posts[2].payload.request_id,posts[1].payload.request_id,'the pending request is retried as itself');
  }finally{dom.restore();}
});

test('newer typing during an in-flight post survives with a fresh request; success focuses the review heading',async()=>{
  const dom=installDOM();try{
    let release;const state={guard:'sha256:guard-1',post:()=>new Promise(resolve=>{release=()=>resolve({status:'RECORDED'});})};
    const {host,posts,controller}=await mount(state);
    type(host,'F1: Submitted');const pending=submit(host);
    type(host,'F2: Typed while posting');release();await pending;
    const held=controller.capture().drafts.A.review;
    assert.equal(held.fields.findings,'F2: Typed while posting');
    assert.notEqual(held.request_id,posts[0].payload.request_id,'the newer text is a new operation');
    assert.equal(field(formOf(host),'findings').value,'F2: Typed while posting','the repainted form shows the retained newer text');
    const focused=globalThis.document.activeElement;
    assert.equal(focused?.dataset?.focusTarget,'work-review');assert.equal(focused.tabIndex,-1);assert.equal(focused.textContent,'Review lifecycle');
  }finally{dom.restore();}
});

test('a Work replaced while its post is in flight is not repainted and nothing posts again',async()=>{
  const dom=installDOM();try{
    let release;const state={guard:'sha256:guard-1',post:()=>new Promise(resolve=>{release=()=>resolve({status:'RECORDED'});})};
    const {host,posts,reads,controller}=await mount(state);
    type(host,'F1: Submitted');const pending=submit(host);
    await controller.select('B');const before=reads.length;
    release();await pending;
    assert.equal(reads.length,before,'no repaint read of the replaced Work');assert.equal(posts.length,1);
    assert.equal(section(host),undefined,'Work B remains shown');assert.match(host.textContent,/Lifecycle B/);
  }finally{dom.restore();}
});

test('the exact review record is read lazily through view:review and renders findings, identity and pins; a different record is refused',async()=>{
  const dom=installDOM();try{
    let work='A';const state={guard:'sha256:guard-1',review:()=>phaseRecord(work)};
    const {host,reads}=await mount(state);
    assert.equal(reads.some(path=>path.includes('view=review')),false,'nothing is read until asked');
    assert.match(section(host).textContent,/Reviewer: claude:fixture \(claimed, unverified\)/);
    await findButton(host,'Inspect the review record').click();
    const path=reads.find(p=>p.includes('view=review'));assert.match(path,/view=review/);assert.match(path,/phase_id=PHASE-r1/);
    const text=section(host).textContent;
    assert.match(text,/F1: Missing narrow check/);assert.match(text,/claude:fixture \(external, claimed through a session, unverified\)/);assert.match(text,/paper\/a\.tex · sha256:aa/);
    work='OTHER';await findButton(host,'Inspect the handoff record').click();
    assert.match(section(host).textContent,/The Work owner returned a different review record\./);
  }finally{dom.restore();}
});

test('legacy completion evidence is named as such beside the review lifecycle',async()=>{
  const dom=installDOM();try{
    const {host}=await mount({guard:'sha256:guard-1'});
    assert.ok(host.all().some(n=>n.tag==='h3'&&n.textContent==='Completion evidence'));
    assert.match(host.textContent,/No completion evidence recorded yet\. Review handoff and review evidence is under Review lifecycle\./);
  }finally{dom.restore();}
});

test('a late success after replacement settles only its own draft; a late refusal keeps it; a destroyed view posts and paints nothing',async()=>{
  const dom=installDOM();try{
    let release,reject;const state={guard:'sha256:guard-1',post:()=>new Promise((resolve,fail)=>{release=()=>resolve({status:'RECORDED'});reject=()=>fail(Error('refused'));})};
    const late=await mount(state);
    type(late.host,'F1: Admitted late');const pending=submit(late.host);
    await late.controller.select('B');release();await pending;
    assert.equal(late.controller.capture().drafts.A,undefined,'the admitted outcome clears the draft it completed');
    assert.match(late.host.textContent,/Lifecycle B/);assert.doesNotMatch(late.host.textContent,/Review phase recorded/,'no outcome text is bound to Work B');
    const refused=await mount(state);
    type(refused.host,'F1: Refused late');const held=refused.controller.capture().drafts.A.review.request_id;const failing=submit(refused.host);
    await refused.controller.select('B');reject();await failing;
    assert.equal(refused.controller.capture().drafts.A.review.request_id,held,'a refusal keeps the draft and its request');
    assert.doesNotMatch(refused.host.textContent,/refused/,'the refusal note is not painted into Work B');
    const gone=await mount(state);
    type(gone.host,'F1: Destroyed');const dying=submit(gone.host);const reads=gone.reads.length;
    gone.controller.destroy();release();await dying;
    assert.equal(gone.posts.length,1);assert.equal(gone.reads.length,reads,'a destroyed view reads and repaints nothing');
  }finally{dom.restore();}
});
