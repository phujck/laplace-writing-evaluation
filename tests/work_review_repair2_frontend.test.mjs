// WORK REVIEW RECORDER REPAIR2 (M5 2026-10-16, WR-R4-R1 human side, WR-R5-R1). An exact review reply is admitted only
// as what its handle asked for (phase, obligation, pinned revision, page, cut). Obligation history is reachable page by
// page under one cut through the owner-issued continuation; a stale page or a replaced Work refuses without mixing.
// Explicitly adopting an inspected basis keeps the draft and focuses its enabled submit, never BODY, and posts nothing.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {mountOperatorWork} from '../src/laplace/web/static_shared/workspace-work.mjs';
import {installDOM,Node,findButton} from './helpers/evidence_reader_harness.mjs';
import {reviewAction} from './helpers/work_preparation.mjs';

const handle=extra=>({operation:'project',payload:{namespace:'fixture',view:'review',id:'A',...extra},
  http:{method:'GET',url:'/work/state?'+new URLSearchParams({project:'fixture',view:'review',id:'A',...extra})}});
const facet=(extra={})=>({managed:true,remaining:['o'],reviews_recorded:21,synthesis:null,followups:[],pending_joins:[],
  handoff:{id:'H1',obligations:['o'],object:{kind:'source'},producer:'producer',producer_origin:'human',pins_total:1,evidence_total:0,read:handle({phase_id:'H1',phase_revision:'rev-H1'})},
  next:{kind:'review',obligation_id:'o',says:'Review source'},
  obligations:[{id:'o',scope:'source',label:'Source',required:true,independent:true,status:'HOLD',currentness:'CURRENT',inputs_total:1,satisfied:false,read:handle({obligation_id:'o'})}],...extra});
const detail=(id,guard='sha256:g1')=>({project:'fixture',view:'detail',read_cut:{revision:'cut'},blockers:[],children:{items:[]},dependants:{items:[]},
  task:{id,title:'Work '+id,goal:'Ship',status:'open',recorded_status:'open',review:id==='A'?facet():null},
  allowed_actions:id==='A'?{work_review:reviewAction(id,guard,facet(),['review'])}:{}});
const phase=(id,extra={})=>({project:'fixture',view:'review',work_id:'A',read_cut:{revision:'cut'},
  phase:{id,revision:'rev-'+id,rows:[{id,phase:'handoff',actor:{actor:'producer',origin:'human'},summary:'Exact '+id,object:{kind:'source',checkpoint:'CHECKPOINT-7'},pins:{'src/a.py':'sha256:aa'}}]},...extra});
const steps=(from,to)=>Array.from({length:to-from},(_,i)=>({phase:'review',id:'R'+(from+i),verdict:'HOLD',actor:{actor:'Reviewer'},ts:'t'+(from+i),read:handle({phase_id:'R'+(from+i)})}));
const history=(offset,cut='cut')=>({project:'fixture',view:'review',work_id:'A',read_cut:{revision:cut},obligation:{id:'o',inputs:['src/a.py']},
  history:{items:steps(offset,Math.min(offset+12,21)),total:21,offset,limit:12,next_read:offset+12<21?handle({obligation_id:'o',offset:offset+12,limit:12,as_of:cut}):null}});

async function mount(route,{guard=()=> 'sha256:g1',post}={}){
  const host=new Node('main');globalThis.document.body.append(host);const reads=[],posts=[];
  const request=async(path,payload)=>{if(payload){posts.push(payload);return post?post(payload):{status:'RECORDED'};}
    reads.push(path);const q=new URL(path,'http://local/').searchParams;
    if(q.get('view')==='review')return route(q);return detail(q.get('id')||'A',guard());};
  const controller=await mountOperatorWork(host,{project:'fixture',summary:{tasks:[{id:'A',title:'Work A',status:'open'},{id:'B',title:'Work B',status:'open'}]},initialWork:'A',request});
  return {host,reads,posts,controller};
}
const box=host=>host.all().find(n=>n.dataset?.control==='work:review');

test('the requested phase renders with its object; another same-Work phase, a changed revision and a wrong obligation refuse',async()=>{
  for(const [reply,want] of [[q=>phase(q.get('phase_id')),null],[()=>phase('OTHER'),/different phase than the one requested/],
      [q=>{const v=phase(q.get('phase_id'));v.phase.revision='rev-changed';return v;},/changed since it was inspected/],
      [q=>q.has('obligation_id')?{...history(0),obligation:{id:'other',inputs:[]}}:phase(q.get('phase_id')),/different obligation than the one requested/]]){
    const dom=installDOM();try{
      const {host}=await mount(reply);
      if(want&&String(want).includes('obligation'))await findButton(host,'Inspect declared inputs and history (1 inputs)').click();
      else await findButton(host,'Inspect the handoff record').click();
      if(want){assert.match(box(host).textContent,want);assert.doesNotMatch(box(host).textContent,/Exact OTHER/);}
      else{assert.match(box(host).textContent,/Exact H1/);assert.match(box(host).textContent,/checkpoint: CHECKPOINT-7/);}
    }finally{dom.restore();}
  }
});

test('all 21 history records are reached exactly once through same-cut pages, with focus on the first added record',async()=>{
  const dom=installDOM();try{
    const {host,reads}=await mount(q=>q.has('phase_id')?phase(q.get('phase_id')):history(Number(q.get('offset')||0)));
    await findButton(host,'Inspect declared inputs and history (1 inputs)').click();
    const labels=()=>box(host).all().filter(n=>n.tag==='button'&&/^review · HOLD · Reviewer · t\d+$/.test(n.textContent)).map(n=>n.textContent);
    assert.equal(labels().length,12);
    const more=findButton(host,'Show more history (12 of 21 shown)');assert.ok(more);
    await more.click();
    assert.deepEqual(labels(),Array.from({length:21},(_,i)=>'review · HOLD · Reviewer · t'+i),'every record exactly once, in order');
    assert.equal(globalThis.document.activeElement?.textContent,'review · HOLD · Reviewer · t12','focus lands on the first added record');
    assert.equal(findButton(host,/Show more history/),undefined);assert.match(box(host).textContent,/All 21 history records are shown\./);
    const page=reads.find(path=>path.includes('offset=12'));assert.match(page,/as_of=cut/);assert.match(page,/obligation_id=o/);
  }finally{dom.restore();}
});

test('a stale continuation refuses without mixing pages and focuses the refusal; a late page after replacement is dropped',async()=>{
  const dom=installDOM();try{
    const {host}=await mount(q=>q.has('offset')?history(12,'cut-moved'):history(0));
    await findButton(host,'Inspect declared inputs and history (1 inputs)').click();
    await findButton(host,'Show more history (12 of 21 shown)').click();
    assert.match(box(host).textContent,/changed between history pages; read the record again\. The records shown stay as read; nothing was mixed\./);
    assert.equal(box(host).all().filter(n=>n.tag==='button'&&/Reviewer · t/.test(n.textContent)).length,12,'no page mixed in');
    assert.equal(globalThis.document.activeElement?.attrs?.role,'alert','focus moves to the refusal, never BODY');
  }finally{dom.restore();}
  const late=installDOM();try{
    let release;const {host,controller}=await mount(q=>q.has('offset')?new Promise(resolve=>{release=()=>resolve(history(12));}):history(0));
    await findButton(host,'Inspect declared inputs and history (1 inputs)').click();
    const list=box(host).all().find(n=>n.className==='operator-review-history');
    const more=findButton(host,'Show more history (12 of 21 shown)');const pending=more.click();
    await controller.select('B');release();await pending;
    assert.match(host.textContent,/Work B/);assert.equal(list.children.length,12,'the replaced Work\'s late page is dropped, not appended');
  }finally{late.restore();}
  const wrong=installDOM();try{
    const {host}=await mount(q=>history(0));   // the owner answers the offset-12 continuation with page 0 again
    await findButton(host,'Inspect declared inputs and history (1 inputs)').click();
    await findButton(host,'Show more history (12 of 21 shown)').click();
    assert.match(box(host).textContent,/different history page/);
    assert.equal(box(host).all().filter(n=>n.tag==='button'&&/Reviewer · t/.test(n.textContent)).length,12);
  }finally{wrong.restore();}
});

test('explicitly adopting the inspected basis keeps the draft, focuses its enabled submit and posts nothing',async()=>{
  const dom=installDOM();try{
    let guard='sha256:g1';const {host,posts,controller}=await mount(q=>phase(q.get('phase_id')),{guard:()=>guard});
    const form=()=>box(host).all().find(n=>n.tag==='form');const field=name=>form().all().find(n=>n.name===name);
    field('verdict').value='HOLD';field('findings').value='F1: Retained text';form().oninput();
    guard='sha256:g2';await controller.select('A');
    await findButton(host,'Use this inspected basis for my draft').click();
    const focused=globalThis.document.activeElement;
    assert.equal(focused?.dataset?.reviewSubmit,'true');assert.equal(focused.isConnected,true);assert.notEqual(focused.disabled,true,'the submit is enabled');
    assert.notEqual(focused.tag,'body');assert.ok(form().all().includes(focused),'focus is inside the repainted retained draft');
    assert.equal(field('findings').value,'F1: Retained text');assert.equal(posts.length,0,'adoption never submits');
  }finally{dom.restore();}
});
