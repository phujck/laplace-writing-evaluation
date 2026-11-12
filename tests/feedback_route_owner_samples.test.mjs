import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {retainFeedbackSubmission,feedbackLookupURL,feedbackRouteReceipt,feedbackHTTP,feedbackTerminalOutcome,bindFeedbackLookup} from '../src/laplace/web/static_shared/feedback-route-port.mjs';
import {installDOM,findButton} from './helpers/evidence_reader_harness.mjs';
import {openFeedbackResponses,openFeedbackWorkReview} from '../src/laplace/web/static_shared/feedback-route.mjs';
const samples=process.env.FEEDBACK_ROUTE_SAMPLES?JSON.parse(await readFile(process.env.FEEDBACK_ROUTE_SAMPLES,'utf8')):null;
test('actual owner request/aggregate sample preserves exact scoped route recovery and rejects redirected lookup',{skip:!samples},async()=>{
 const payload=samples.preview.actions.submit.payload,pending=await retainFeedbackSubmission(payload,samples.preview.request_read);assert.equal(await feedbackLookupURL(pending,'route'),samples.preview.request_read.http.url);assert.equal((await feedbackRouteReceipt(samples.request_recorded,pending,payload.origin)).aggregate.route_id,samples.aggregate.route_id);
 const damaged={...pending,lookup:{http:{method:'GET',url:'/work/delivery?project=p&request='+encodeURIComponent(JSON.stringify({action:'route-status',work_id:payload.work_id,request_id:'different'}))}}};await assert.rejects(()=>feedbackLookupURL(damaged,'route'),/changed its Work/);
 await assert.rejects(()=>feedbackRouteReceipt({...samples.request_recorded,aggregate:{...samples.aggregate,policy:{...samples.aggregate.policy,limits:{...samples.aggregate.policy.limits,max_new_admissions:500}}}},pending,payload.origin),/another authored policy/);
});
test('actual aggregate displays preview as preview, terminal ACK separately and exact complete-response handle',{skip:!samples},async()=>{
 const d=installDOM();try{const a=samples.aggregate,seen=[];const dialog=await openFeedbackResponses({project:a.project,workId:a.work.id,origin:a.origin.origin_ref,read:a.read,request:async path=>{seen.push(path);return a;}});
 assert.match(dialog.textContent,/Response preview/);assert.match(dialog.textContent,/wrote the return/);assert.doesNotMatch(dialog.textContent,/Response previewtrue/);assert.match(dialog.textContent,/TERMINAL/);assert.match(dialog.querySelector('article').textContent,/Awaiting a recorded verdict/);assert.ok(findButton(dialog,'Read complete response'));assert.equal(seen.length,1);dialog.close();
 }finally{d.restore();}
});
test('shared Work review inspector reuses exact existing record qualification',{skip:!samples},async()=>{
 const d=installDOM();try{const edge=samples.aggregate.edges[0],handle=edge.handoff_read,body={project:'p',view:'review',work_id:'review-claim',phase:{id:handle.payload.phase_id,rows:[{id:handle.payload.phase_id,phase:'handoff',summary:'Exact handed input.'}]}};
 const dialog=await openFeedbackWorkReview({project:'p',workId:'review-claim',handle,label:'Handed inputs',request:async path=>{assert.equal(path,feedbackHTTP(handle,{project:'p'}));return body;}});assert.match(dialog.textContent,/Exact handed input/);dialog.close();
 }finally{d.restore();}
});

test('terminal owner control is qualified to the original home/request before new intent is allowed',async()=>{
 const payload={project:'public',request_id:'original-comment',text:'Retained prose',source_basis:{ledger:'public/feedback/feedback.jsonl'}},lookup={http:{method:'GET',route:'/authoring/correction-request',query:{project:'public',ledger:payload.source_basis.ledger}},requires:['request_id']};const bound=bindFeedbackLookup(lookup,payload.request_id),pending=await retainFeedbackSubmission(payload,bound);assert.match(await feedbackLookupURL(pending),/request_id=original-comment/);
 const value={effect:'NOT_ADMITTED',terminal:true,project:'public',request_id:payload.request_id,ledger:payload.source_basis.ledger,intent_sha256:'sha256:'+'a'.repeat(64),receipt:null,settlement:{id:'SET-public',code:'AUTHOR_SETTLED_UNCOMMITTED_REQUEST',by:'author',at:'2026-10-25'},reconcile:bound};
 assert.equal((await feedbackTerminalOutcome(value,pending)).submission.wire,pending.wire);for(const changed of [{...value,terminal:false},{...value,request_id:'another'},{...value,ledger:'foreign/feedback/feedback.jsonl'},{...value,receipt:{id:'not-a-non-admission'}}])await assert.rejects(()=>feedbackTerminalOutcome(changed,pending));
});
