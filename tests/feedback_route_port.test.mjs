import test from 'node:test';
import assert from 'node:assert/strict';
import {createFeedbackDraft,retainFeedbackSubmission,retainedFeedbackPayload,feedbackHTTP,feedbackRevisionSummary,feedbackBuildFreshness} from '../src/laplace/web/static_shared/feedback-route-port.mjs';
const store=()=>{const values=new Map();return {getItem:key=>values.get(key)||null,setItem:(key,value)=>values.set(key,value)};};
const payload=()=>({project:'public',request_id:'comment-original',text:'A claim — κόσμος 🧪',source_basis:{opaque:'original'},review_route:{request_id:'route-original',policy_id:'author-policy'}});
test('retained Unicode submission roundtrips byte-for-byte; damaged wire never substitutes a new intent',async()=>{
 const wire=await retainFeedbackSubmission(payload(),{http:{method:'GET',url:'/authoring/correction-request?project=public&request_id=comment-original'}});
 assert.equal(JSON.stringify(await retainedFeedbackPayload(wire)),wire.wire);
 const damaged={...wire,wire:wire.wire.replace('original','changed')};await assert.rejects(()=>retainedFeedbackPayload(damaged),/damaged/);
});
test('reload preserves pending exact wire and newer authored text; no automatic read or retry',async()=>{
 const storage=store(),backup=store(),draft=createFeedbackDraft({project:'public',key:'selection',initial:{text:'original'},storage,backup});
 await draft.retain(payload(),{http:{method:'GET',url:'/exact'}});draft.observe('NONE');draft.update({text:'New typing retained separately'});
 const reloaded=createFeedbackDraft({project:'public',key:'selection',storage,backup});assert.equal(reloaded.snapshot().text,'New typing retained separately');assert.equal(reloaded.snapshot().pending.observation,'NONE');assert.equal((await reloaded.pendingPayload()).text,payload().text);await assert.rejects(()=>reloaded.retain(payload(),{}),/original comment request/);
});
test('fallback storage is used before selected submission refuses durable custody',async()=>{
 const denied={getItem(){throw Error('unavailable');},setItem(){throw Error('unavailable');}},backup=store();
 const good=createFeedbackDraft({project:'public',key:'selection',storage:denied,backup});await good.retain(payload(),{});assert.equal((await good.pendingPayload()).request_id,'comment-original');
 const bad=createFeedbackDraft({project:'public',key:'other',storage:denied,backup:denied});await assert.rejects(()=>bad.retain(payload(),{}),/durable recovery copy/);assert.equal(bad.snapshot().pending.request_id,'comment-original');
});
test('owner handles keep same origin, project and method without copying transport metadata into payload',()=>{
 const handle={http:{method:'GET',url:'/work/delivery?project=public&request=%7B%7D'}};assert.match(feedbackHTTP(handle,{project:'public',paths:['/work/delivery']}),/^\/work\/delivery/);
 for(const bad of [{http:{method:'POST',url:'/work/delivery?project=public'}},{http:{method:'GET',url:'https://other.invalid/work/delivery?project=public'}},{http:{method:'GET',url:'/work/delivery?project=foreign'}}])assert.throws(()=>feedbackHTTP(bad,{project:'public',paths:['/work/delivery']}));
});
test('owner revision join presents exact proposal/application/build reads, refuses foreign joins and never infers a link',()=>{
 const get=url=>({http:{method:'GET',url}});
 const built={schema_version:'laplace.feedback-revision-join/1',project:'public',turn_id:'WT-producer',state:'BUILT',
  links:{produced:true,applied:true,built:true,incomplete_applications:1,unattributed_applications:1},
  next_read:get('/authoring/build?project=public&build_job=%7B%7D'),
  proposals:[{version:'sha256:'+'1'.repeat(64),read:get('/authoring/proposal-preview?project=public&id=WT-producer&proposal_version=v&view=summary'),applications:[
   {id:'WA-good',read:get('/authoring/session-turn?project=public&id=WT-producer&view=application&item_id=WA-good'),
    source_effect:{state:'COMMITTED',complete:true},build:{state:'BUILT',build_job:{id:'BLD-1'},job_status_read:get('/authoring/build?project=public&build_job=%7B%7D')}},
   {id:'WA-partial',read:{http:{method:'POST',url:'/authoring/session-turn?project=public'}},source_effect:{state:'PARTIAL',complete:false},
    build:{state:'NOT_APPLICABLE',reason:'Source effect PARTIAL: no build can show this application.'}}]}],
  unattributed_applications:[{id:'WA-legacy'}]};
 const shown=feedbackRevisionSummary(built,{project:'public',turnId:'WT-producer'});
 assert.equal(shown.state,'BUILT');assert.ok(shown.produced&&shown.applied&&shown.built);
 assert.deepEqual(shown.links.map(link=>link.kind),['proposal','application','build']);   // the POST handle is never linked; next_read duplicates the build read
 assert.ok(shown.lines.some(line=>line.includes('WA-partial: source effect partial (incomplete)')));
 assert.ok(shown.lines.some(line=>line.includes('WA-legacy is not attributed')));
 assert.ok(shown.lines.at(-1).includes('none is your disposition'));
 // the produced version is offered once for read-only inspection of this exact producer turn; no apply is minted
 assert.deepEqual(shown.inspect,[{turnId:'WT-producer',version:'sha256:'+'1'.repeat(64),label:'Inspect proposal '+'1'.repeat(12)+' in manuscript',
  read:get('/authoring/proposal-preview?project=public&id=WT-producer&proposal_version=v&view=summary')}]);
 const foreignRead={...built,proposals:[{...built.proposals[0],read:get('/authoring/proposal-preview?project=foreign&id=WT-producer')}]};
 assert.equal(feedbackRevisionSummary(foreignRead,{project:'public',turnId:'WT-producer'}).inspect[0].read,null);   // a foreign read is never carried
 assert.deepEqual(feedbackRevisionSummary({...built,turn_id:undefined},{project:'public'}).inspect,[]);   // no producer turn: nothing to inspect
 assert.throws(()=>feedbackRevisionSummary({...built,project:'foreign'},{project:'public'}),/another project/);
 assert.throws(()=>feedbackRevisionSummary(built,{project:'public',turnId:'WT-other'}),/producer turn/);
 assert.throws(()=>feedbackRevisionSummary({...built,state:'ACCEPTED'},{project:'public'}),/unknown state/);
 assert.throws(()=>feedbackRevisionSummary({...built,schema_version:'other'},{project:'public'}),/another project/);
 const none=feedbackRevisionSummary({schema_version:'laplace.feedback-revision-join/1',project:'public',turn_id:'WT-producer',state:'NOT_PRODUCED',
  links:{produced:false,applied:false,built:false},next_read:get('/authoring/session-turn?project=foreign&id=WT-producer&view=turn'),proposals:[]},{project:'public',turnId:'WT-producer'});
 assert.equal(none.lines[0],'No proposal was produced by this review.');assert.deepEqual(none.links,[]);assert.ok(!none.produced&&!none.built);
 assert.deepEqual(none.inspect,[]);
 assert.equal(feedbackRevisionSummary(undefined,{project:'public'}),null);
});
test('a chain build fact is checked through the build owner job status; freshness is never inferred from BUILT',()=>{
 const get=url=>({http:{method:'GET',url}}),statusURL='/authoring/build?project=public&build_job=%7B%22id%22%3A%22BLD-9%22%7D';
 const rev={schema_version:'laplace.feedback-revision-join/1',project:'public',turn_id:'WT-p',state:'BUILT',links:{produced:true,applied:true,built:true},
  proposals:[{version:'sha256:'+'2'.repeat(64),applications:[{id:'WA-1',source_effect:{state:'COMMITTED',complete:true},build:{state:'BUILT',build_job:{id:'BLD-9'},job_status_read:get(statusURL)}},
   {id:'WA-2',source_effect:{state:'COMMITTED',complete:true},build:{state:'NOT_BUILT',reason:'No recorded build shows these bytes.'}},
   {id:'WA-3',source_effect:{state:'COMMITTED',complete:true},build:{state:'BUILT',build_job:{id:'BLD-x'},job_status_read:get('/authoring/build?project=foreign&build_job=%7B%7D')}}]}]};
 const shown=feedbackRevisionSummary(rev,{project:'public',turnId:'WT-p'});
 assert.deepEqual(shown.builds,[{id:'BLD-9',application:'WA-1',url:statusURL}]);   // NOT_BUILT and a foreign handle offer no check
 const fresh=feedbackBuildFreshness({project:'public',state:'idle',fresh:true,job_basis_current:true},{project:'public'});
 assert.equal(fresh.fresh,true);assert.match(fresh.lines[0],/fresh: yes · job basis is today's source: yes/);
 const moved=feedbackBuildFreshness({project:'public',state:'idle',fresh:true,job_basis_current:false},{project:'public'});
 assert.equal(moved.fresh,false);assert.match(moved.lines[1],/would not show these exact bytes/);
 const silent=feedbackBuildFreshness({state:'idle'},{project:'public'});assert.equal(silent.fresh,false);assert.match(silent.lines[0],/fresh: not reported/);
 assert.throws(()=>feedbackBuildFreshness({project:'foreign',fresh:true,job_basis_current:true},{project:'public'}),/another project/);
 assert.ok(fresh.lines.at(-1).includes('not review or scientific acceptance'));
});
test('unreadable retained recovery is preserved and cannot silently become a fresh submission',async()=>{
 const damaged={getItem:()=>'{broken pending request',setItem(){throw Error('must preserve unreadable bytes');}},draft=createFeedbackDraft({project:'public',key:'selection',storage:damaged,backup:store(),initial:{text:'New draft'}});
 assert.match(draft.recoveryError,/unreadable/);assert.equal(draft.recoveryRaw[0],'{broken pending request');await assert.rejects(()=>draft.retain(payload(),{}),/unreadable/);assert.throws(()=>draft.reset({text:'replacement'}),/unreadable/);
});
