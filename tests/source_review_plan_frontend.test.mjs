// Read-only offered Source plan presentation; no owner policy or completion inference.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {renderSourceReviewPlan,renderWorkReviewPhaseRows} from '../src/laplace/web/static_shared/workspace-work-review.mjs';
import {ownerHumanTarget} from '../src/laplace/web/static_shared/writing-owner-read.mjs';
import {installDOM,Node,findButton} from './helpers/evidence_reader_harness.mjs';
const pin='sha256:'+'a'.repeat(64);
const target={owner:'repository',repository:'selected',path:'src/answer.py'};
const read={operation:'repository',payload:{action:'read',repository:'selected',path:'src/answer.py',expected_sha256:pin,offset:4,limit:12},
  http:{method:'GET',url:'/projects/material-references?'+new URLSearchParams({project:'public',view:'preview',target:JSON.stringify(target),expected_sha256:pin,offset:'4',limit:'12'})}};
const plan=()=>({schema_version:'laplace.development-review-plan/1',plan_id:'DRP-public-fixture',state:'COMPLETE',source_identity:{project:'public',repository:'selected'},
  pins:{'src/answer.py':pin},candidate_files:[{path:'src/answer.py',changed:true}],inputs:[{path:'src/answer.py',changed:true,state:'COMPLETE',reasons:[],
    requested_context:[{id:'window-1',line_start:2,line_end:3}],initial_reads:[{path:'src/answer.py',offset:4,chars:12,stop_before_offset:16,read}],
    selected_context:[{offset:4,chars:12,end_offset:16}],uninspected_extents:[{offset:0,chars:4}],uncovered_edit_ids:[],verified_edits:{edits:[{id:'edit-1',before:{text:'old α'},after:{text:'new 中'}}]}}]});

test('offered reading leads with coverage and exact handle; technical JSON stays lazy and data unchanged',async()=>{
 const dom=installDOM();try{const body=new Node('section');document.body.append(body);const value=plan(),before=JSON.stringify(value),calls=[];
   renderWorkReviewPhaseRows(body,{phase:{rows:[{phase:'handoff',summary:'Public source change',actor:{actor:'Public holder',origin:'native'},source_review_plan:value}]}},{onRead:(...args)=>calls.push(args)});
   assert.match(body.textContent,/Suggested review reading/);assert.match(body.textContent,/1 changed files · 1 required inputs · 1 starting excerpts/);
   assert.match(body.textContent,/not observed reads/);assert.match(body.textContent,/stop before 16/);assert.match(body.textContent,/4 characters outside/);
   await findButton(body,'Read src/answer.py · 12 characters').click();assert.equal(calls[0][0],read);assert.equal(calls[0][2].stop_before_offset,16);
   const exact=body.all().find(n=>n.tag==='details'&&n.children[0]?.textContent==='Exact plan and source details');assert.ok(!exact.open);assert.equal(exact.children.at(-1).textContent,'');
   exact.open=true;exact.ontoggle();assert.match(exact.children.at(-1).textContent,/selected_context/);assert.equal(JSON.stringify(value),before);
 }finally{dom.restore();}
});

test('missing context is explicit without a synthesized full read; existing Material negatives remain strict',()=>{
 const dom=installDOM();try{const body=new Node('section'),value=plan();value.state='INCOMPLETE';value.inputs[0].initial_reads=[];value.inputs[0].reasons=['No context windows were offered.'];value.inputs[0].uncovered_edit_ids=['edit-1'];
   renderSourceReviewPlan(body,value,{onRead:()=>assert.fail('automatic read')});assert.match(body.textContent,/Some required context is missing/);assert.match(body.textContent,/No context windows/);assert.equal(body.all().filter(n=>n.tag==='button').length,0);
   assert.ok(ownerHumanTarget(read.http.url));
   assert.equal(ownerHumanTarget(read.http.url+'&expected_sha256='+pin),null);
   assert.equal(ownerHumanTarget(read.http.url.replace('view=preview','view=unknown')),null);
   assert.equal(ownerHumanTarget(read.http.url+'&pointer=not-a-pointer'),null);
   assert.equal(ownerHumanTarget(read.http.url.replace(encodeURIComponent(pin),'bad-pin')),null);
   assert.ok(ownerHumanTarget(read.http.url+'&pointer=%2Fpart'));
 }finally{dom.restore();}
});
