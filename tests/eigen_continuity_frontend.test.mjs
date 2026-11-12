// Eigen continuity in the selected Task (WORK-eigen-continuity-human-guides-20261030): Progress and next action.
// Controller tests over ACTUAL public owner DTOs captured from real controlled owners (admission, accounting and provider
// start stubbed; NOT live Main handles, model runs or browser observations):
//   ART-6419764618904a499dab1d01b8abda72 sha256:67ee7cdd2930045966c9134594c53029d6ab071c02fa45c13fecf0269ff5cff2
//     /summary_ready, /summary_awaiting/{basis,next,completion/intents/0/readiness}, /continue_request, /continue_result
//   ART-26edc7db74be48fbbbc89423a53e49c7 sha256:ea08a9f2c5ed786860f27ae14b72ea4decebc30959643d17bcac72315e3b260a
//     the issued selected-detail continuity_read with its Scope companion, and its summary
// Where a test changes one actual member it is named VARIANT (for example A's declared human POST route, which the actual
// summary's Continue action does not carry). The DOM is the existing local double; this is not runtime or acceptance proof.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {installDOM,Node,findButton} from './helpers/evidence_reader_harness.mjs';
import {mountOperatorWork} from '../src/laplace/web/static_shared/workspace-work.mjs';
import {admitContinuityRead,admitContinuitySummary,continuityModel,continuityNext,continuityCut} from '../src/laplace/web/static_shared/workspace-work-review.mjs';
import {writingOwnerResponse} from '../src/laplace/web/static_shared/writing-request.mjs';
import {ownerHumanTarget,qualifiedOwnerHTTP} from '../src/laplace/web/static_shared/writing-owner-read.mjs';

test('closure facts keep owner currentness, original-parent receipt, adoption and stage disposition as separate owner facts',()=>{
  const base={subject:{namespace:'p',id:'W',qualified_id:'p::W'},
    standing:{lifecycle:{status:'done',completed:true},readiness:{status:'ready'},
      current_acceptance:{status:'REVIEW_REQUIRED',currentness:'CURRENT',kind:'PREREQUISITE_CHANGED',review_required:true}},
    production:{grants:1,candidates:1,effects:{total:1,committed:1},checks:{total:2,states:{PASSED:2},cleanup:{REMOVED:1,UNKNOWN:1}}},
    completion:{intents:[]},review:{obligations:[],remaining:0},delivery:{events:[]},execution:{accounts:[]},coverage:{},next:{},
    closeout:{handoff:'PHASE-h',handoffs_total:1,reviews:[{id:'PHASE-r',verdict:'ACCEPT',obligation_id:'source'}],synthesis:null,
      review_required:'REQUIRED',adoption:'NOT_RECORDED',live:'NOT_RECORDED',publication:'NOT_RECORDED',latest_synthesis_covers_latest_handoff:false}};
  const facts=continuityModel(base).closure.join('\n');
  // the owner's status, currentness and kind verbatim: local evidence CURRENT beside prerequisite REVIEW_REQUIRED
  assert.match(facts,/Evidence currentness \(owner\): REVIEW_REQUIRED · CURRENT · PREREQUISITE_CHANGED · review required/);
  assert.match(facts,/Recorded review PHASE-r/);assert.match(facts,/No same-Work synthesis is recorded\./);
  assert.doesNotMatch(facts,/Received by the original parent|showing the latest/);
  for(const label of ['Adopted','Live','Published'])assert.match(facts,new RegExp(label+': not recorded by the Work owner'));
  assert.match(facts,/Check stages: /);
  const received=continuityModel({...base,closeout:{...base.closeout,synthesis:'PHASE-s',latest_synthesis_covers_latest_handoff:true}}).closure.join('\n');
  assert.match(received,/Same-Work synthesis recorded: PHASE-s/);assert.match(received,/names the latest handoff directly/);
  assert.doesNotMatch(received,/No same-Work synthesis|Received by the original parent/);
  assert.deepEqual(continuityModel({...base,closeout:null,production:{}}).closure,['Evidence currentness (owner): REVIEW_REQUIRED · CURRENT · PREREQUISITE_CHANGED · review required.']);
});

test('closure facts disclose the latest k of N reviews, held and remaining, and never call a same-Work synthesis the original parent\'s receipt',()=>{
  const reviews=Array.from({length:8},(_,n)=>({id:'PHASE-r'+n,verdict:n?'ACCEPT':'HOLD',obligation_id:'source'}));
  const base={subject:{namespace:'p',id:'W',qualified_id:'p::W'},
    standing:{lifecycle:{status:'open',completed:false},readiness:{status:'ready'},current_acceptance:{status:'NOT_REQUIRED'}},
    production:{},completion:{intents:[]},review:{obligations:[],remaining:1,read:{operation:'project',payload:{namespace:'p',view:'review',id:'W'}}},
    delivery:{events:[]},execution:{accounts:[]},coverage:{},next:{},
    closeout:{handoff:'PHASE-h2',handoffs_total:2,reviews,reviews_total:11,synthesis:'PHASE-human',syntheses_total:1,review_required:'REQUIRED',
      held:['source'],remaining:['source'],missing_next:'review',adoption:'NOT_RECORDED',live:'NOT_RECORDED',publication:'NOT_RECORDED',
      latest_synthesis_covers_latest_handoff:false}};
  // a human or other same-Work synthesis among more than eight reviews, with a held remainder
  const facts=continuityModel(base).closure.join('\n');
  assert.match(facts,/showing the latest 8 of 11/);assert.match(facts,/its issued review read/);
  assert.match(facts,/Held by the owner: source \(a bounded list from the owner; no total is reported\)/);assert.match(facts,/Still to be satisfied \(owner\): source/);assert.match(facts,/Next recorded step \(owner\): review/);
  assert.match(facts,/Same-Work synthesis recorded: PHASE-human/);assert.doesNotMatch(facts,/Received by the original parent/);
  assert.match(facts,/may still cover it through a consumed review/);assert.doesNotMatch(facts,/does not cover the latest handoff/);
  // a review-only consumes chain beside an actual continued parent delivery: the admission is not receipt, nor is absence of a direct link
  const chain=continuityModel({...base,delivery:{events:[{id:'WD-1',state:'CONTINUED',obligation_id:'source',handoff_id:'PHASE-h2',
      admitted:{session_id:'WS-review',turn_id:'WT-review'},prepared_completion:'CI-1',dispatcher_origin:'human',reason:null,
      read:{operation:'work_delivery',payload:{action:'status',event_id:'WD-1'}}}]},
    closeout:{...base.closeout,reviews:reviews.slice(0,1),reviews_total:1,held:[],remaining:[],missing_next:null,synthesis:'PHASE-parent'}}).closure.join('\n');
  assert.doesNotMatch(chain,/showing the latest|Held by the owner|Received by the original parent/);
  assert.match(chain,/Same-Work synthesis recorded: PHASE-parent/);assert.match(chain,/delivery and phase records/);
  assert.match(chain,/may still cover it through a consumed review/);
});

const copy=value=>structuredClone(value);
const flush=async()=>{for(let i=0;i<10;i++)await new Promise(resolve=>setImmediate(resolve));};
const escape=text=>text.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
const WR='sha256:62eea46d39f174f3b472545db5c74c3cbc53efb6ca6a1351d652bea1ce009048',SR='sha256:47f288cf379cba3428ea04dee5abf2ac7aede97d18880f43ab12b2cd67315501';
const INTENT='CI-aaddb011300a6ac5825851e5',READY_BASIS='sha256:0fec4507259f6bda3aece9477a9d5e2ee7f25b6e434440b78235d9f6a43db8a3';
const PROOF={id:'ART-1cb4c5af6c39474eade31b2b41a97b3d',expected_sha256:'6666388f2f1b9612b6eddba765f00a86ee255a7dbe05a2b82d693d62a3796f86'};
const DEVELOPMENT_READ={operation:'development_source',payload:{action:'status',work_id:'work'}};
const REVIEW_READ={operation:'project',payload:{namespace:'public',view:'review',id:'work'},http:{method:'GET',url:'/work/state?project=public&view=review&id=work'}};
const READS={detail:{operation:'project',payload:{namespace:'public',view:'detail',id:'work'},http:{method:'GET',url:'/work/state?project=public&view=detail&id=work'}},
  development:copy(DEVELOPMENT_READ),delivery:{operation:'work_delivery',payload:{action:'status',work_id:'work'}}};
const SUBJECT={namespace:'public',id:'work',qualified_id:'public::work',work_revision:WR,scope_revision:SR,containment_issue:null};
const STANDING={status:'ready',recorded_status:'open',lifecycle:{status:'open',completed:false,closed:false},readiness:{status:'READY',blocked_by:[],reason:'task is not complete',satisfies_prerequisites:false},
  current_acceptance:{status:'NOT_REQUIRED',currentness:'NOT_REQUIRED',reason:'task is not complete',kind:null,blocked_by:[],review_required:false}};
const AWAITING_HANDOFF=[{id:'source',status:'AWAITING_HANDOFF',currentness:'UNKNOWN',satisfied:false,review_id:null},{id:'guide',status:'AWAITING_HANDOFF',currentness:'UNKNOWN',satisfied:false,review_id:null}];
const COVERAGE_MEANING='Selected owner metadata only; no message bodies, transcripts or unrelated Work were read.';
const QUALIFICATION='Live account observation outside the basis token; recorded admissions and current host execution are separate.';
// ea08 /continuity_read: the actual issued selected-detail entry
const ENTRY={operation:'project',payload:{namespace:'public',view:'continuity',id:'work',request:{part:'summary'}},
  http:{method:'GET',url:'/work/state?project=public&view=continuity&id=work&request=%7B%22part%22%3A%22summary%22%7D'},
  scope:{kind:'owned-workspace',door:'http',says:'The local owned workspace: every namespace this root holds is readable here.'}};
// ea08 /summary
const ENTRY_SUMMARY={schema_version:'laplace.work-continuity/1',part:'summary',subject:copy(SUBJECT),title:'Public source change',goal:'Change exact source and review it',standing:copy(STANDING),
  basis:{work_revision:WR,scope_revision:SR,dependency_revision:'sha256:4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945',development_cut:'sha256:f20cec7d88d64ae26a86104a1b6548aa0bd40d13535d57e1e69904f6e65a8271',
    delivery_cut:'sha256:9eca464076c043563f32b6473d4f4dbddd84492cfe5ec46c92b31ba587dcc55e',token:'sha256:2b9ed834d54a554e2059d06856a1d9c9df0e1ed18fae7b68a0328135e36d76f5'},
  production:{grants:1,candidates:0,effects:{total:0,committed:0},checks:{total:0,states:{}},read:copy(DEVELOPMENT_READ)},completion:{total:0,intents:[]},
  review:{obligations:copy(AWAITING_HANDOFF),remaining:2,next:'handoff',read:copy(REVIEW_READ)},delivery:{total:0,events:[]},
  execution:{accounts:[],observed_at:'2026-10-30T13:09:35.604721+00:00',qualification:QUALIFICATION},
  next:{kind:'record-handoff',callable:false,template:true,fill:['payload.request_id'],reason:'Records the implementation and its exact file pins for scoped review. Nothing is launched, and a handoff satisfies no obligation.',
    action:{operation:'work_review',payload:{id:'work',phase:'handoff',request_id:'<stable request id>',expected_work_revision:WR}},
    preparation:{title:'Hand off for review',says:'Records the implementation and its exact file pins for scoped review. Nothing is launched, and a handoff satisfies no obligation.',basis:{expected_work_revision:WR},
      inputs:[{path:'obligations',name:'obligations',input:'lines',label:'Obligations handed off (ids, one per line)',required:false,default:'source\nguide'},{path:'object.kind',name:'kind',input:'text',label:'What is handed off',required:false,default:'source'},
        {path:'object.base',name:'base',input:'text',label:'Base',required:false},{path:'object.checkpoint',name:'checkpoint',input:'text',label:'Checkpoint',required:false},
        {path:'object.aggregate',name:'aggregate',input:'text',label:'Aggregate digest (when files are not pinned)',required:false},{path:'pins',name:'pins',input:'pins',label:'Exact file pins: "path sha256:<digest>" per line',required:false},
        {path:'summary',name:'summary',input:'area',label:'Summary',required:false},{path:'evidence',name:'evidence',input:'evidence',label:'Public evidence: "path sha256:<digest>" per line',required:false}]}},
  reads:copy(READS),coverage:{intents_selected:0,intents_omitted:0,events_selected:0,events_omitted:0,meaning:COVERAGE_MEANING},mode:'human'};
// 67ee /summary_ready
const SUMMARY_READY={schema_version:'laplace.work-continuity/1',part:'summary',subject:copy(SUBJECT),title:'Public source change',goal:'Change exact source and review it',standing:copy(STANDING),
  basis:{work_revision:WR,scope_revision:SR,dependency_revision:'sha256:4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945',development_cut:'sha256:58b4556950a949f5691ac2332818e37c1db60364f59911722f1d0bb03a364593',
    delivery_cut:'sha256:dd8e2af72fba92fc864ac0bdb0e89787c62e452209aeefbde9757900ca939eec',token:'sha256:0781b517ec04d280f56a8c718d0f50d292286cf500922895633afc7f84b9bf24'},
  production:{grants:2,candidates:2,effects:{total:2,committed:2},checks:{total:0,states:{}},read:copy(DEVELOPMENT_READ)},
  completion:{total:1,intents:[{id:INTENT,state:'ARMED',work_id:'work',grant_id:'DG-7b31cadd6684d651df7da954',obligation_id:'source',request_id:'public-continuity-arm',ts:'2026-10-30T13:01:54.100Z',
    origin:{actor:'unknown:unknown',session_id:'WS-59c72c4f750e4473812c53e69ca69d55',turn_id:'WT-allowance',commission_id:'SC-986f9dfd812b867240936890',depth:0},
    production:{candidate_id:'DC-94ef9426d3051c272c630bd7',effect_id:'DE-a3fab04f2df15394a57c33ec',effects:['DE-0122be42cf4d11291f709244','DE-a3fab04f2df15394a57c33ec'],changed:['guide.md','src/answer.py'],
      pins:{'src/answer.py':'sha256:b756b64da03191d05b456656a606e52b3189ce5ca5c5101170a5092e32640b66','evaluator.py':'sha256:049dee85e1be1fb30c515d7ea748b6479abaa82399877488387688b143adf876','guide.md':'sha256:fbb3c585266e31940ddd73bc6674cd188dfce731ac46832cc3dbf0c8f27c31bb'}},
    policy:{recipient_binding_id:'RB-7e629219aa8bb4d4379e92a5',recipient_binding_revision:'sha256:7e629219aa8bb4d4379e92a52578e5fe23b1c34e3ca45c017b6f1c9ded60d47c',
      return_policy:{review_deadline_s:3600,max_attempts:1,parent_return:{admit_idle:true,max_attempts:1,max_depth:2}},planned:{apps:2,sessions:1}},
    proof_slots:[{id:'a-functional',label:'Independent fixed-runtime functional proof'}],
    work:{scope_revision:SR,work_revision:WR,intent_digest:'sha256:c7975e98f298286f7ebb7ccb7336300a0c9fe1e014e809ac5513d372b67678b1'},
    meaning:'Prepared continuation only: one handoff and the approved review/return under this frozen basis. It is not a review, acceptance or completion.',
    readiness:{state:'READY',basis:READY_BASIS,slots:[{id:'a-functional',label:'Independent fixed-runtime functional proof',filled:true,integrity:'VERIFIED',reference:copy(PROOF)}],
      facts:{source:'CURRENT',scope_revision:SR,producer_stopped:false,account:{state:'ACTIVE',capacity:'SUFFICIENT'}},reasons:[],reasons_total:0}}]},
  review:{obligations:copy(AWAITING_HANDOFF),remaining:2,next:'handoff',read:copy(REVIEW_READ)},delivery:{total:0,events:[]},
  execution:{accounts:[{commission_id:'SC-986f9dfd812b867240936890',state:'ACTIVE',admitted:0,remaining:40,active:0,denied:0,app_admissions:1,app_remaining:2,sessions:1,session_remaining:1,
    deadline_at:'2026-10-30T13:21:53.823451+00:00',stop_reason:null,read:{operation:'development_source',payload:{action:'status',work_id:'work'},http:{method:'POST',url:'/work/development',payload:{project:'public',action:'status',work_id:'work'}}}}],
    observed_at:'2026-10-30T13:01:54.189925+00:00',qualification:QUALIFICATION},
  next:{kind:'continue',callable:true,reason:'Declared peer proof has arrived and every predicate holds: one owner Continue records the handoff and the approved delivery once.',
    action:{operation:'work_delivery',payload:{action:'continue',intent_id:INTENT,expected_basis:READY_BASIS}}},
  reads:copy(READS),coverage:{intents_selected:1,intents_omitted:0,events_selected:0,events_omitted:0,meaning:COVERAGE_MEANING},mode:'human'};
// 67ee /continue_request
const CONTINUE_REQUEST={action:'continue',intent_id:INTENT,expected_basis:READY_BASIS};
// 67ee /continue_result: its continued record and the event members this view reads
const CONTINUE_RESULT={ok:true,reused:false,continued:{id:'CC-7ee43227f2b6988e95f49350',intent_id:INTENT,handoff_id:'PHASE-8c8322072cda10522902b763',event_id:'WD-912c6593734259d2c8cd341f',basis:READY_BASIS,
    proofs:[{slot_id:'a-functional',reference:copy(PROOF)}],ts:'2026-10-30T13:01:54.266397+00:00',dispatcher:{actor:'unknown:unknown',origin:'native',session_id:'WS-59c72c4f750e4473812c53e69ca69d55',turn_id:'WT-allowance'}},
  event:{id:'WD-912c6593734259d2c8cd341f',state:'ADMITTED',work_id:'work',handoff_id:'PHASE-8c8322072cda10522902b763',obligation_id:'source',
    admitted:{session_id:'WS-7eb9795f8e8345269a2b1410724d234b',turn_id:'WT-7431b00730244a56bfff00708382a3ec',request_id:'WD-912c6593734259d2c8cd341f',reused:false,recovered:false,recipient_ack:'UNKNOWN'},
    dispatcher:{actor:'unknown:unknown',origin:'native',session_id:'WS-59c72c4f750e4473812c53e69ca69d55',turn_id:'WT-allowance'},prepared_completion:{intent_id:INTENT,basis:READY_BASIS},reason:null},
  read:{operation:'project',payload:{namespace:'public',view:'continuity',id:'work',request:{part:'completion',intent_id:INTENT}},
    http:{method:'GET',url:'/work/state?project=public&view=continuity&id=work&request=%7B%22part%22%3A%22completion%22%2C%22intent_id%22%3A%22CI-aaddb011300a6ac5825851e5%22%7D'}}};
// summary_awaiting assembled ONLY from actually read 67ee pointers (/basis, /next, /completion/intents/0/readiness); its other
// members are the same fixture's summary_ready members for the same Work, intent and account
const AWAITING=(()=>{const value=copy(SUMMARY_READY);
  value.basis={...value.basis,development_cut:'sha256:96cfeacacd053cf864d34f745363ba893c798b3fbe9e948f92eff004a636c76c',delivery_cut:'sha256:dd8e2af72fba92fc864ac0bdb0e89787c62e452209aeefbde9757900ca939eec',token:'sha256:0b8e0c015a772f499886c33848759f52dcc120280ee1a55500e7ddffc2b51219'};
  value.completion.intents[0].readiness={state:'AWAITING_PROOF',basis:'sha256:4156a711a2c0f75e309e8480466f5a41c07c986c29dda12041074e2435106ab0',slots:[{id:'a-functional',label:'Independent fixed-runtime functional proof',filled:false,integrity:null}],
    facts:{source:'CURRENT',scope_revision:SR,producer_stopped:false,account:{state:'ACTIVE',capacity:'SUFFICIENT'}},reasons:[{code:'PROOF_ABSENT',slot_id:'a-functional',reason:'Declared peer proof a-functional has not arrived.'}],reasons_total:1};
  value.next={kind:'attach-proof',callable:false,template:true,fill:['payload.reference'],reason:'Waiting for declared peer proof a-functional; its exact retained Artifact is attached when it arrives (arrival only).',
    action:{operation:'development_source',payload:{action:'proof',intent_id:INTENT,slot_id:'a-functional',reference:{id:'<ART-id>',expected_sha256:'<sha256>'}},
      http:{method:'POST',url:'/work/development',payload:{project:'public',action:'proof',intent_id:INTENT,slot_id:'a-functional',reference:{id:'<ART-id>',expected_sha256:'<sha256>'}}}}};
  return value;})();
// VARIANT: the actual summary_ready plus A's declared human door (POST /work/delivery), which the actual Continue does not carry
const withRoute=value=>{const routed=copy(value);routed.next.action.http={method:'POST',url:'/work/delivery'};return routed;};
// VARIANT after Continue: B's documented CONTINUED readiness with the actual continue_result event projected to summary members
const continuedSummary=()=>{const value=copy(SUMMARY_READY),event=CONTINUE_RESULT.event;value.completion.intents[0].readiness.state='CONTINUED';
  value.delivery={total:1,events:[{id:event.id,state:event.state,obligation_id:event.obligation_id,handoff_id:event.handoff_id,admitted:copy(event.admitted),prepared_completion:copy(event.prepared_completion),dispatcher_origin:copy(event.dispatcher),reason:null}]};
  value.next={kind:'await-delivery',callable:false,reason:'The approved review was requested once; its response is awaited.',read:copy(READS.delivery)};return value;};
// 67ee /proof_attached: the actual proof arrival result
const PROOF_RESULT={ok:true,reused:false,proof:{id:'CP-84e7da14849ed4b0bc67da3e',intent_id:INTENT,slot_id:'a-functional',reference:copy(PROOF),artifact_id:PROOF.id,path:'proofs/a-functional.json',scope:'project',
    observed_sha256:PROOF.expected_sha256,ts:'2026-10-30T13:01:54.158326+00:00',meaning:'Arrival of declared peer proof; not a review, acceptance or PASS.',attached_by:'author',attached_origin:'human'},
  read:{operation:'project',payload:{namespace:'public',view:'continuity',id:'work',request:{part:'completion',intent_id:INTENT}},
    http:{method:'GET',url:'/work/state?project=public&view=continuity&id=work&request=%7B%22part%22%3A%22completion%22%2C%22intent_id%22%3A%22CI-aaddb011300a6ac5825851e5%22%7D'}}};

function detail(id='work',{cut='cut-1',entry=true,extra={}}={}){
  const own=id==='work';
  return {project:'public',view:'detail',read_cut:{revision:cut},observe_basis:{records:'r-'+cut,selected:'s-'+cut,activity:'a-'+cut},
    task:{id,title:own?'Public source change':'Other public task',goal:own?'Change exact source and review it':'Something else',status:'open',recorded_status:'open',
      lifecycle:{status:'open',closed:false,completed:false},readiness:{status:'READY',reason:'Declared prerequisites met.'},current_acceptance:{status:'NOT_REQUIRED',review_required:false,reason:'task is not complete'},
      activity:{state:null,qualification:'No in-app or attested external execution observed.',coverage:{partial:false}},...(own?{work_revision:WR,work_scope_revision:SR}:{})},
    blockers:[],allowed_actions:{},acceptance:{goal:null,mechanical:[],scientific_verification:false},children:{items:[]},dependants:{items:[]},requires:{items:[]},
    ...(own&&entry?{continuity_read:copy(ENTRY),continuity_read_gap:null}:{}),...extra};
}
function owner({summary,cut=()=>'cut-1',post=null,continuity=null,detailOf=null}={}){
  const calls=[];
  const request=async(path,payload)=>{calls.push({path,payload:payload===undefined?undefined:copy(payload)});
    if(payload!==undefined){if(!post)throw Error('unexpected POST '+path);return copy(await post(path,payload));}
    const q=new URL(path,'http://local').searchParams,view=q.get('view');
    if(view==='detail')return detailOf?detailOf(q.get('id'),cut()):detail(q.get('id'),{cut:cut()});
    if(view==='continuity')return copy(continuity?await continuity(q):typeof summary==='function'?summary():summary);
    throw Error('unexpected read '+path);};
  const viewOf=call=>new URL(call.path,'http://local').searchParams.get('view');
  return {calls,request,reads:view=>calls.filter(call=>call.payload===undefined&&viewOf(call)===view),posts:()=>calls.filter(call=>call.payload!==undefined),views:()=>[...new Set(calls.map(viewOf))].sort()};
}
async function mount(transport,{initial='work',memory={},dom=installDOM()}={}){
  const host=new Node('main');dom.body.append(host);
  const controller=await mountOperatorWork(host,{project:'public',summary:{tasks:[detail('work').task,detail('other').task]},initialWork:initial,request:transport.request,memory});
  await flush();return {dom,host,controller};
}
const section=host=>host.querySelector('.work-continuity');
const lineOf=host=>host.querySelector('.work-continuity-attempt');
const unknown=()=>Object.assign(Error('The local engine is unavailable. Your draft is preserved; reconnect to continue.'),{transport:'connection',effect:'unknown'});

test('the actual issued entry is admitted exactly; another namespace, Work, request, carrier, route or scope is refused before any read',()=>{
  assert.equal(admitContinuityRead(copy(ENTRY),{project:'public',workId:'work'}),ENTRY.http.url);
  const bare=copy(ENTRY);delete bare.scope;
  assert.equal(admitContinuityRead(bare,{project:'public',workId:'work'}),ENTRY.http.url,'a bare wrapper handle is read without inventing a scope');
  const variants=[h=>{h.payload.namespace='other';},h=>{h.payload.id='other';},h=>{h.payload.request={part:'completion',intent_id:INTENT};},h=>{h.payload.extra=true;},h=>{h.extra=true;},
    h=>{h.operation='work_delivery';},h=>{h.http.url=h.http.url.replace('view=continuity','view=detail');},h=>{h.http.url+='&id=work';},h=>{h.http.url='http://elsewhere'+h.http.url;},
    h=>{h.http.url=h.http.url.replace('summary','completion');},h=>{h.http.method='POST';},h=>{delete h.http;},h=>{h.scope={kind:'project',door:'native',namespace:'other'};}];
  for(const change of variants){const handle=copy(ENTRY);change(handle);assert.throws(()=>admitContinuityRead(handle,{project:'public',workId:'work'}),/nothing was read|no human route|progress read/);}
  assert.throws(()=>admitContinuityRead(copy(ENTRY),{project:'other',workId:'work'}),/another work namespace/);
  assert.throws(()=>admitContinuityRead(null,{project:'public',workId:'work'}),/did not carry/);
  assert.equal(admitContinuitySummary(copy(ENTRY_SUMMARY),{project:'public',workId:'work'}).subject.qualified_id,'public::work');
  for(const change of [v=>{v.subject.id='other';},v=>{v.subject.qualified_id='other::work';},v=>{v.basis.work_revision='sha256:'+'0'.repeat(64);},v=>{v.schema_version='laplace.work-continuity/0';},v=>{v.part='completion';}]){
    const value=copy(ENTRY_SUMMARY);change(value);assert.throws(()=>admitContinuitySummary(value,{project:'public',workId:'work'}),/not shown/);}
});

test('the actual entry summary paints in the selected Task: produced and awaiting-handoff facts, no invented activity, the issued handoff step opens only an existing form',async()=>{
  const transport=owner({summary:ENTRY_SUMMARY}),s=await mount(transport);
  try{const box=section(s.host),text=box.textContent;
    assert.match(text,/Progress and next action/);assert.match(text,/Recorded lifecycle: open/);assert.match(text,/Evidence currentness: not required yet/);
    assert.match(box.querySelector('.work-continuity-open').textContent,/No Source change applied yet \(1 grant, 0 candidates · no checks recorded\)\./);
    assert.match(box.querySelector('.work-continuity-delivered').textContent,/Nothing is recorded as produced, handed off, reviewed or delivered yet\./,'review R2: awaited items no longer fill Delivered');
    assert.match(box.querySelector('.work-continuity-open').textContent,/Review “source”: awaiting handoff/);
    assert.match(text,/Review “source”: awaiting handoff · not satisfied\./);assert.match(text,/Review “guide”: awaiting handoff · not satisfied\./);
    assert.match(text,/No admitted execution is recorded in this summary\. In progress is a declared standing, not an observed running process\./);
    assert.match(text,new RegExp(escape(ENTRY_SUMMARY.next.reason)));assert.match(text,/Read scope: The local owned workspace/);
    assert.match(text,/Source production for agents: development_source/);
    assert.equal(box.querySelector('.work-continuity-next').dataset.continuityNext,'record-handoff');
    assert.equal(transport.reads('continuity').length,1);assert.equal(transport.reads('continuity')[0].path,ENTRY.http.url);
    assert.deepEqual(transport.views(),['continuity','detail'],'evidence and review records stay behind deliberate reads');
    assert.equal(findButton(box,'Open review form'),undefined,'no permitted recorder on this read, so no review control is mounted');
    assert.match(text,/The review form for this phase is not offered on this read\./);assert.equal(transport.posts().length,0);
  }finally{s.controller.destroy();s.dom.restore();}
});

test('an issued Continue without a human route is named and never sent; a changed task revision or an incomplete offer withholds it',async()=>{
  const transport=owner({summary:SUMMARY_READY}),s=await mount(transport);
  try{const box=section(s.host),text=box.textContent;
    assert.match(box.querySelector('.work-continuity-delivered').textContent,/Prepared completion armed 2026-10-30T13:01:54\.100Z by its producing session for 2 changed files\./);
    assert.match(box.querySelector('.work-continuity-open').textContent,/Prepared completion: ready to continue\./);
    assert.match(box.querySelector('.work-continuity-delivered').textContent,/arrived \(verified\)/);
    assert.match(box.querySelector('.work-continuity-exact').textContent,/session WS-59c72c4f750e4473812c53e69ca69d55 · turn WT-allowance/);
    assert.doesNotMatch(box.querySelector('.work-continuity-delivered').textContent+box.querySelector('.work-continuity-activity').textContent,/CI-|WS-|WT-|SC-/,'exact identities stay under Exact');
    assert.match(text,/Declared proof “Independent fixed-runtime functional proof” arrived \(verified\)\. Arrival is not a review or acceptance\./);
    assert.match(text,/Source account: active · 0 admitted calls, 40 remaining · 2 app turns and 1 sessions remaining/);
    assert.match(text,/without a human route, so it is not sent from here/);assert.match(text,/request public-continuity-arm · grant DG-7b31cadd6684d651df7da954/);
    assert.equal(findButton(box,'Continue to the approved review'),undefined);assert.equal(transport.posts().length,0);
    assert.doesNotMatch(text,/\baccepted\b/i);
  }finally{s.controller.destroy();s.dom.restore();}
  const moved={...detail('work').task,work_revision:'sha256:'+'0'.repeat(64)},model=continuityModel(copy(SUMMARY_READY),{task:moved,project:'public'});
  assert.equal(model.cut.same,false);assert.match(model.next.withheld,/different work revision/);assert.ok(model.uncertain.some(row=>/different work revision/.test(row)));
  const routed=withRoute(SUMMARY_READY),next=continuityNext(routed,{project:'public',cut:continuityCut(routed,detail('work').task)});
  assert.equal(next.route,'/work/delivery');assert.deepEqual(next.body,{project:'public',...CONTINUE_REQUEST});
  for(const change of [v=>{v.next.action.payload.expected_basis='sha256:'+'1'.repeat(64);},v=>{v.next.callable=false;},v=>{v.completion.intents[0].readiness.state='HELD';},
    v=>{v.next.action.http.url='http://elsewhere/work/delivery';},v=>{v.next.action.payload.extra=1;},v=>{v.next.action.http.payload={project:'other',...CONTINUE_REQUEST};}]){
    const value=copy(routed);change(value);const offer=continuityNext(value,{project:'public',cut:{same:true}});assert.ok(offer.withheld||offer.gap);assert.equal(offer.route,null);}
});

test('VARIANT routed Continue: a lost acknowledgement keeps the original wire through observation and remount; Check reads the issued summary and never resends',async()=>{
  let summaryNow=withRoute(SUMMARY_READY),cut='cut-1';
  const transport=owner({summary:()=>summaryNow,cut:()=>cut,post:async()=>{throw unknown();}}),s=await mount(transport);let again=null;
  try{
    await findButton(section(s.host),'Continue to the approved review').click();await flush();
    assert.equal(transport.posts().length,1);assert.equal(transport.posts()[0].path,'/work/delivery');assert.deepEqual(transport.posts()[0].payload,{project:'public',...CONTINUE_REQUEST});
    assert.match(lineOf(s.host).textContent,/outcome is UNKNOWN, which does not mean no effect/);assert.equal(s.controller.hasDraft,true);
    assert.equal(findButton(section(s.host),'Continue to the approved review'),undefined,'nothing new is offered while the original is unresolved');
    assert.match(section(s.host).textContent,/An earlier request for this task is unresolved/);
    const kept=section(s.host);await s.controller.observed({changed:true});await flush();
    assert.equal(section(s.host),kept,'a background observation keeps the unresolved section mounted');assert.match(lineOf(s.host).textContent,/UNKNOWN/);
    const memory=s.controller.capture();assert.deepEqual(memory.drafts.work.continuity.body,{project:'public',...CONTINUE_REQUEST});assert.equal(memory.drafts.work.continuity.url,'/work/delivery');
    s.controller.destroy();s.host.remove();
    again=await mount(transport,{memory:copy(memory),dom:s.dom});
    assert.match(lineOf(again.host).textContent,/UNKNOWN/);assert.match(lineOf(again.host).textContent,/Original request/);
    assert.equal(findButton(section(again.host),'Continue to the approved review'),undefined);assert.equal(again.controller.hasDraft,true);
    summaryNow=continuedSummary();cut='cut-2';const before=transport.reads('continuity').length;
    await findButton(section(again.host),'Check the original outcome').click();await flush();
    assert.ok(transport.reads('continuity').length>before);assert.equal(transport.posts().length,1,'checking never resends');
    assert.match(lineOf(again.host).textContent,/shows the original Continue request \(.*\) recorded\. Nothing was resent\./);assert.equal(again.controller.hasDraft,false);
    const text=section(again.host).textContent;
    assert.match(text,/Review request for “source”: admitted · from the prepared completion · dispatched by unknown:unknown \(native\), recorded apart from the producer\./);
    assert.match(text,/A review turn was admitted\. Admission is not an observed running process\./);
    assert.match(text,/Review request WD-912c6593734259d2c8cd341f · handoff PHASE-8c8322072cda10522902b763 · prepared completion CI-aaddb011300a6ac5825851e5 · review session WS-7eb9795f8e8345269a2b1410724d234b · turn WT-7431b00730244a56bfff00708382a3ec/);
    assert.match(text,/acknowledgement is UNKNOWN: not an error, and not proof that it started\./);
  }finally{(again?.controller||s.controller).destroy();s.dom.restore();}
});

test('VARIANT routed Continue: a check showing no effect permits one explicit resend of the identical original wire, recorded with the actual continue_result',async()=>{
  let fail=true,cut='cut-1';
  const transport=owner({summary:()=>withRoute(SUMMARY_READY),cut:()=>cut,post:async()=>{if(fail){fail=false;throw unknown();}cut='cut-2';return CONTINUE_RESULT;}}),s=await mount(transport);
  try{
    await findButton(section(s.host),'Continue to the approved review').click();await flush();
    assert.equal(findButton(section(s.host),'Resend the original Continue unchanged'),undefined,'no resend before the original outcome is checked');
    await findButton(section(s.host),'Check the original outcome').click();await flush();
    assert.match(lineOf(s.host).textContent,/shows no effect of the original Continue request/);assert.equal(transport.posts().length,1);
    await findButton(section(s.host),'Resend the original Continue unchanged').click();await flush();
    const posts=transport.posts();assert.equal(posts.length,2);assert.equal(posts[1].path,posts[0].path);assert.deepEqual(posts[1].payload,posts[0].payload);
    assert.match(lineOf(s.host).textContent,/Continue recorded\. Handoff PHASE-8c8322072cda10522902b763 and review request WD-912c6593734259d2c8cd341f \(admitted\)\. A handoff and request are not a review or acceptance\./);
    assert.equal(s.controller.hasDraft,false);
  }finally{s.controller.destroy();s.dom.restore();}
});

test('awaiting declared proof (actual pointers): the template fills only its reference, the typed draft survives remount, arrival is recorded as arrival',async()=>{
  let summaryNow=AWAITING,cut='cut-1';
  const transport=owner({summary:()=>summaryNow,cut:()=>cut,post:async()=>{cut='cut-2';summaryNow=SUMMARY_READY;return PROOF_RESULT;}}),s=await mount(transport);let again=null;
  try{let box=section(s.host);
    assert.match(box.textContent,/Prepared completion: awaiting declared proof\./);
    assert.match(box.textContent,/Awaiting declared proof “Independent fixed-runtime functional proof”\./);assert.doesNotMatch(box.textContent,/\bheld\b/);
    let form=box.querySelector('.work-continuity-proof'),[artifact,digest]=form.querySelectorAll('input');
    artifact.value=PROOF.id;digest.value=PROOF.expected_sha256;form.oninput();
    const memory=s.controller.capture();assert.deepEqual(memory.drafts.work.continuityProof,{intent_id:INTENT,slot_id:'a-functional',id:PROOF.id,sha:PROOF.expected_sha256});assert.equal(s.controller.hasDraft,true);
    s.controller.destroy();s.host.remove();again=await mount(transport,{memory:copy(memory),dom:s.dom});
    box=section(again.host);form=box.querySelector('.work-continuity-proof');[artifact,digest]=form.querySelectorAll('input');
    assert.equal(artifact.value,PROOF.id);assert.equal(digest.value,PROOF.expected_sha256);assert.equal(transport.posts().length,0,'restoring a draft sends nothing');
    await form.onsubmit({preventDefault(){}});await flush();
    const posts=transport.posts();assert.equal(posts.length,1);assert.equal(posts[0].path,'/work/development');assert.deepEqual(posts[0].payload,{...AWAITING.next.action.http.payload,reference:PROOF});
    assert.match(lineOf(again.host).textContent,/Proof arrival recorded as CP-84e7da14849ed4b0bc67da3e\. Arrival of declared peer proof; not a review, acceptance or PASS\./);
    const text=section(again.host).textContent;assert.match(text,/arrived \(verified\)\. Arrival is not a review or acceptance\./);assert.doesNotMatch(text,/\baccepted\b/i);
    assert.equal(again.controller.hasDraft,false);
  }finally{(again?.controller||s.controller).destroy();s.dom.restore();}
});

// B 625cc2cc replay: the real shared writingOwnerResponse turns an HTTP error body into Error.result; that body is no
// owner no-effect receipt, so the original wire must stay UNKNOWN (the earlier 'refused' settlement was wrong)
test('a thrown owner error body through the real shared adapter (HTTP 400, 409, 500) keeps the original UNKNOWN, never refused',async()=>{
 for(const status of [400,409,500]){
  const refusal='TEST server failure after a possible owner write ('+status+')';
  const transport=owner({summary:AWAITING,post:async(path,payload)=>writingOwnerResponse({ok:false,status,value:{error:refusal}},path,payload)}),s=await mount(transport);
  try{const form=section(s.host).querySelector('.work-continuity-proof'),[artifact,digest]=form.querySelectorAll('input');
    artifact.value=PROOF.id;digest.value='not-a-digest';form.oninput();await form.onsubmit({preventDefault(){}});
    assert.equal(transport.posts().length,0,'a malformed digest is not sent');
    digest.value=PROOF.expected_sha256;form.oninput();await form.onsubmit({preventDefault(){}});await flush();
    assert.equal(transport.posts().length,1);const line=lineOf(s.host).textContent;
    assert.match(line,new RegExp('answered the original proof request .* with an error: '+escape(refusal)));assert.match(line,/does not show whether it took effect, so the outcome stays UNKNOWN/);
    assert.doesNotMatch(line,/The owner refused/);assert.ok(findButton(section(s.host),'Check the original outcome'),'the original can be checked, never silently cleared');
    const memory=s.controller.capture();assert.equal(memory.drafts.work.continuity.status,'uncertain');assert.deepEqual(memory.drafts.work.continuity.body,{...AWAITING.next.action.http.payload,reference:PROOF});
    assert.equal(memory.drafts.work.continuityProof.id,PROOF.id);assert.equal(s.controller.hasDraft,true);
  }finally{s.controller.destroy();s.dom.restore();}
 }
});

test('a late progress reply for an earlier selection is dropped; returning reuses that observation without another read',async()=>{
  let release;const gate=new Promise(resolve=>{release=resolve;});
  const transport=owner({summary:SUMMARY_READY,continuity:async()=>{await gate;return SUMMARY_READY;}}),s=await mount(transport);
  try{assert.match(section(s.host).textContent,/Reading this task's progress/);
    await s.controller.select('other');release();await flush();
    assert.equal(section(s.host),null,'a Work whose owner issues no continuity read shows no progress section');assert.doesNotMatch(s.host.textContent,/Delivered so far/);
    await s.controller.select('work');await flush();
    assert.equal(transport.reads('continuity').length,1,'an unchanged detail cut and observe basis reuse the one read');
    assert.match(section(s.host).textContent,/Delivered so far/);
  }finally{s.controller.destroy();s.dom.restore();}
});

test('a refused entry shows its gap; historical HOLD, unrecorded verdicts and expired accounts keep their owner words',async()=>{
  const gap='No actual admitted caller Scope for this namespace; no continuity read is issued.';   // B correction cut 508f refused-entry text
  const transport=owner({summary:SUMMARY_READY}),dom=installDOM(),host=new Node('main');dom.body.append(host);
  const value=detail('work',{entry:false,extra:{continuity_read:null,continuity_read_gap:gap}});
  const controller=await mountOperatorWork(host,{project:'public',summary:{tasks:[value.task]},initialWork:'work',initialDetail:value,request:transport.request});await flush();
  try{assert.match(section(host).textContent,new RegExp('No progress summary was issued for this task: '+escape(gap)));assert.equal(transport.reads('continuity').length,0);}
  finally{controller.destroy();dom.restore();}
  // VARIANT of the actual summary carrying historical owner states (a recorded HOLD, a verdict never recorded, an expired account)
  const old=copy(SUMMARY_READY);
  old.review.obligations=[{id:'source21',status:'HOLD',currentness:'CURRENT',satisfied:false,review_id:'PHASE-hold'},{id:'source8',status:'AWAITING_REVIEW',currentness:'UNKNOWN',satisfied:false,review_id:null}];
  old.execution.accounts[0].state='EXPIRED';old.completion.intents[0].readiness={...old.completion.intents[0].readiness,state:'CLOSED',reasons:[{code:'ACCOUNT_CLOSED',reason:'The Source account expired.'}]};
  const model=continuityModel(old,{task:detail('work').task,project:'public'}),all=[...model.delivered,...model.open,...model.activity,...model.uncertain].join('\n');
  assert.ok(model.delivered.some(row=>/source21/.test(row))&&model.open.some(row=>/source8/.test(row)),'a recorded HOLD is delivered; an unrecorded verdict is still open');
  assert.match(all,/Review “source21”: hold · not satisfied · decision currentness current\./);assert.match(all,/Review “source8”: awaiting review · not satisfied\./);
  assert.match(all,/Source account: expired/);assert.match(all,/Prepared completion closed: The Source account expired\./);
  assert.doesNotMatch(all,/accept(ed)?\b/i);assert.ok(model.next.withheld,'Continue is withheld once its prepared completion is closed');
});

// A 79b0705a / B Stop interface 880388c4: a durable Stop REQUEST withdraws continuation; it does not prove the process ended
test('a recorded Stop request is worded as a request that withdraws continuation, never as a stopped process',()=>{
  const value=copy(SUMMARY_READY),ready=value.completion.intents[0].readiness;   // VARIANT: actual READY summary with B's documented PRODUCER_STOPPED closure
  Object.assign(ready,{state:'CLOSED',facts:{...ready.facts,producer_stopped:true},reasons:[{code:'PRODUCER_STOPPED',reason:'The producing turn was stopped.'}]});
  const model=continuityModel(value,{task:detail('work').task,project:'public'}),all=[...model.delivered,...model.open,...model.uncertain].join('\n');
  assert.match(all,/A Stop was requested for the producing turn, so this prepared completion is withdrawn from continuing\. The request is recorded; it does not show that the turn's process has ended\./);
  assert.match(all,/Prepared completion closed: a Stop request for the producing turn is recorded; it does not show that the turn's process has ended/);
  assert.doesNotMatch(all,/turn was stopped/i);assert.ok(model.next.withheld,'Continue is withheld');
});

// Replays of the early peer findings on checkpoint b3d4 (A ART-31755efe A-C1; B ART-353e0def F1, F2)
test('peer A-C1 and B-F1 replay: a live deferred proof request stays pending, not UNKNOWN, and its reply keeps newer typing',async()=>{
  let release;const gate=new Promise(resolve=>{release=resolve;});let cut='cut-1',summaryNow=AWAITING;
  const transport=owner({summary:()=>summaryNow,cut:()=>cut,post:async()=>{await gate;cut='cut-2';summaryNow=SUMMARY_READY;return PROOF_RESULT;}}),s=await mount(transport);
  try{const form=section(s.host).querySelector('.work-continuity-proof'),[artifact,digest]=form.querySelectorAll('input');
    artifact.value=PROOF.id;digest.value=PROOF.expected_sha256;form.oninput();const sent=form.onsubmit({preventDefault(){}});await flush();
    assert.equal(s.controller.capture().drafts.work.continuity.status,'pending');assert.match(lineOf(s.host).textContent,/Sending the issued proof request/);assert.doesNotMatch(lineOf(s.host).textContent,/UNKNOWN/);
    artifact.value='ART-later-unsent';digest.value='a'.repeat(64);form.oninput();   // typing continues in the form the person was using
    release();await sent;await flush();
    assert.equal(transport.posts().length,1);assert.match(lineOf(s.host).textContent,/Proof arrival recorded as CP-84e7da14849ed4b0bc67da3e/);
    const kept=s.controller.capture().drafts.work;assert.equal(kept.continuity,undefined);
    assert.deepEqual(kept.continuityProof,{intent_id:INTENT,slot_id:'a-functional',id:'ART-later-unsent',sha:'a'.repeat(64)});assert.equal(s.controller.hasDraft,true);
  }finally{s.controller.destroy();s.dom.restore();}
});

test('peer B-F2 replay: a 2xx reply naming another proof slot, reference, Work or prepared completion leaves the original UNKNOWN and unresolved',async()=>{
  for(const change of [r=>{r.proof.intent_id='CI-'+'0'.repeat(24);},r=>{r.proof.slot_id='other-slot';},r=>{r.proof.reference.id='ART-'+'0'.repeat(32);},r=>{r.read.payload.namespace='other';},r=>{delete r.proof;}]){
    const reply=copy(PROOF_RESULT);change(reply);const transport=owner({summary:AWAITING,post:async()=>reply}),s=await mount(transport);
    try{const form=section(s.host).querySelector('.work-continuity-proof'),[artifact,digest]=form.querySelectorAll('input');
      artifact.value=PROOF.id;digest.value=PROOF.expected_sha256;form.oninput();await form.onsubmit({preventDefault(){}});await flush();
      assert.match(lineOf(s.host).textContent,/does not name the original proof request .*The original stays UNKNOWN/);
      const held=s.controller.capture().drafts.work;assert.equal(held.continuity.status,'uncertain');assert.equal(held.continuityProof.id,PROOF.id);
      assert.ok(findButton(section(s.host),'Check the original outcome'));assert.equal(transport.posts().length,1);
    }finally{s.controller.destroy();s.dom.restore();}
  }
  // VARIANT routed Continue whose 2xx reply names another prepared completion
  const reply=copy(CONTINUE_RESULT);reply.continued.intent_id='CI-'+'0'.repeat(24);
  const transport=owner({summary:withRoute(SUMMARY_READY),post:async()=>reply}),s=await mount(transport);
  try{await findButton(section(s.host),'Continue to the approved review').click();await flush();
    assert.match(lineOf(s.host).textContent,/does not name the original Continue request \(another prepared completion\)/);assert.equal(s.controller.capture().drafts.work.continuity.status,'uncertain');
  }finally{s.controller.destroy();s.dom.restore();}
});

// Control identities (data-control / data-control-owner) on the existing controls, over the real mounted Work controller and
// the existing DOM double. Assertions cover only conditions reached here; declaration rows and states are A's registry.
test('control identities mount on the existing controls only under their reached conditions; the passive heading has none',async()=>{
  const ids=host=>host.all().filter(n=>String(n.dataset?.control||'').startsWith('work:continuity')).map(n=>[n.dataset.control,n.textContent,n.dataset.controlOwner]);
  const close=s=>{s.controller.destroy();s.dom.restore();};
  // the actual READY summary carries no human Continue route: nothing actionable is mounted
  let s=await mount(owner({summary:SUMMARY_READY}));
  try{assert.deepEqual(ids(section(s.host)),[]);assert.equal(section(s.host).querySelector('h3').dataset.control,undefined);}finally{close(s);}
  // VARIANT routed READY summary: Continue; transport loss then Check; the owner shows no effect then Resend
  let fail=true;const routed=owner({summary:()=>withRoute(SUMMARY_READY),post:async()=>{if(fail){fail=false;throw unknown();}return CONTINUE_RESULT;}});
  s=await mount(routed);
  try{assert.deepEqual(ids(section(s.host)),[['work:continuity-continue','Continue to the approved review','public::work']]);
    await findButton(section(s.host),'Continue to the approved review').click();await flush();
    assert.deepEqual(ids(section(s.host)),[['work:continuity-check','Check the original outcome','public::work']]);
    await findButton(section(s.host),'Check the original outcome').click();await flush();
    assert.deepEqual(ids(section(s.host)),[['work:continuity-check','Check the original outcome','public::work'],['work:continuity-resend','Resend the original Continue unchanged','public::work']]);
    assert.equal(routed.posts().length,1,'mounting and checking send nothing new');
  }finally{close(s);}
  // VARIANT routed summary read at another task revision: Continue is withheld, so no Continue control
  const moved=withRoute(SUMMARY_READY);moved.subject.work_revision=moved.basis.work_revision='sha256:'+'0'.repeat(64);
  s=await mount(owner({summary:moved}));try{assert.deepEqual(ids(section(s.host)),[]);}finally{close(s);}
  // read-only controller: no actionable control even with a routed offer
  {const dom=installDOM(),host=new Node('main');dom.body.append(host);const value=detail('work');
    const controller=await mountOperatorWork(host,{project:'public',summary:{tasks:[value.task]},initialWork:'work',readOnly:true,request:owner({summary:withRoute(SUMMARY_READY)}).request});await flush();
    try{assert.deepEqual(ids(section(host)),[]);}finally{controller.destroy();dom.restore();}}
  // review R4: a read-only viewer keeps the pure read of what the step waits on (VARIANT continued summary)
  {const dom=installDOM(),host=new Node('main');dom.body.append(host);const value=detail('work');
    const controller=await mountOperatorWork(host,{project:'public',summary:{tasks:[value.task]},initialWork:'work',readOnly:true,request:owner({summary:continuedSummary()}).request});await flush();
    try{assert.match(section(host).querySelector('.work-continuity-next').textContent,/Agent read: work_delivery/);assert.deepEqual(ids(section(host)),[]);}finally{controller.destroy();dom.restore();}}
  // the awaiting summary's fillable proof template
  s=await mount(owner({summary:AWAITING}));
  try{assert.deepEqual(ids(section(s.host)),[['work:continuity-proof','Attach arrived proof','public::work']]);}finally{close(s);}
  // an actual summary GET failure, then a successful explicit retry (GET only)
  let failRead=true;const reading=owner({summary:SUMMARY_READY,continuity:async()=>{if(failRead){failRead=false;throw Error('TEST summary read failure');}return SUMMARY_READY;}});
  s=await mount(reading);
  try{assert.deepEqual(ids(section(s.host)),[['work:continuity-retry','Read progress again','public::work']]);
    await findButton(section(s.host),'Read progress again').click();await flush();
    assert.deepEqual(ids(section(s.host)),[]);assert.match(section(s.host).textContent,/Delivered so far/);assert.equal(reading.posts().length,0);
  }finally{close(s);}
  // VARIANT detail with the existing permitted recorder (managed review facet and allowed_actions.work_review in the live
  // detail's shape, phase preparation from the actual entry summary) and the actual entry summary's handoff step
  const reviewing=()=>{const value=detail('work');
    value.task.review={managed:true,remaining:['source'],obligations:[{id:'source',scope:'source',label:'Source change',required:true,independent:true,inputs_total:3,status:'AWAITING_HANDOFF',currentness:'UNKNOWN',satisfied:false}],
      handoff:null,synthesis:null,followups:[],phases_total:0,pending_joins:[],reviews_recorded:0,next:{kind:'handoff',says:'Submit the implementation for scoped review (metadata only; nothing is launched).'}};
    value.allowed_actions={work_review:{operation:'work_review',permitted:true,payload:{id:'work',expected_work_revision:WR},phases:['handoff'],http:{method:'POST',url:'/work/review'},
      preparation:{phases:{handoff:copy(ENTRY_SUMMARY.next.preparation)},initial:'handoff'}}};return value;};
  const recording=owner({summary:ENTRY_SUMMARY,detailOf:id=>id==='work'?reviewing():detail(id)});s=await mount(recording);
  try{assert.deepEqual(ids(section(s.host)),[['work:continuity-review','Open form: Hand off for review','public::work']]);
    const recorder=s.host.querySelector('.operator-review-recorder');assert.ok(recorder?.querySelector('form'));assert.ok(!recorder.open);
    assert.ok(findButton(s.host,'Open review form'),'the lifecycle keeps its own control');assert.equal(s.host.all().filter(n=>n.tag==='button'&&n.textContent==='Open form: Hand off for review').length,1,'review R5: labels are distinct');
    await findButton(section(s.host),'Open form: Hand off for review').click();assert.equal(recorder.open,true);assert.equal(recording.posts().length,0,'opening the form records nothing');
  }finally{close(s);}
});

// C007 frozen independent countercase (ART-da7ae67487184b58a8e88a20eea01242; original child-read-check.mjs
// sha256:1ee01639f6aa2b7782995e86ec657badc9a04e5f222b35577539971f03549dbd), appended unchanged: actual issued handle, real readLink
test('independent actual issued continuity completion child reaches GET through production Work readLink',async()=>{
 const actualRead=CONTINUE_RESULT.read;
 const current=copy(SUMMARY_READY);current.next={kind:'inspect',callable:false,reason:'Inspect the original prepared completion.',read:actualRead};
 const transport=owner({summary:current}),s=await mount(transport);
 try{const before=transport.reads('continuity').length;const link=findButton(section(s.host),'Read what this step waits on');assert.ok(link);
  await link.onclick();await flush();const after=transport.reads('continuity').length;
  const proof={before,after,read:actualRead,status:s.host.textContent,qualification:'Actual owner-issued continue_result.read handle, current summary next placement is a controlled variant; real mountOperatorWork/readLink, no stubbed readLink, no owner/model/browser effect.'};
  // The operator retains the proof outside the source checkout.
  assert.equal(after,before+1,'the valid issued completion child must be read, rather than rejected before GET');
 }finally{s.controller.destroy();s.dom.restore();}
});

test('the resolver types a continuity read only under the owner\'s closed request contract',()=>{
  const at=request=>'/work/state?'+new URLSearchParams({project:'public',view:'continuity',id:'work',request:JSON.stringify(request)});
  for(const request of [{part:'summary'},{part:'completion',intent_id:INTENT},{part:'summary',as_of:READY_BASIS},{part:'preflight',payload:{}},{}])
    assert.equal(ownerHumanTarget(at(request))?.kind,'work-continuity',JSON.stringify(request));
  for(const request of [{part:'completion'},{part:'completion',intent_id:'CI-short'},{part:'preflight'},{part:'other'},{part:'summary',extra:1},{part:'summary',as_of:'latest'},{part:'preflight',payload:[]},[]])
    assert.equal(ownerHumanTarget(at(request)),null,JSON.stringify(request));
  assert.equal(ownerHumanTarget(at({part:'summary'})+'&offset=1'),null,'an unknown query member is refused');
  assert.equal(ownerHumanTarget('/work/state?project=public&view=continuity&id=work'),null,'the request is required');
  assert.deepEqual(ownerHumanTarget(CONTINUE_RESULT.read.http.url).read_handle,{operation:'project',payload:CONTINUE_RESULT.read.payload});
  assert.equal(qualifiedOwnerHTTP(CONTINUE_RESULT.read,'public')?.owner?.kind,'work-continuity');assert.equal(qualifiedOwnerHTTP(CONTINUE_RESULT.read,'other'),null);
  const changed=copy(CONTINUE_RESULT.read);changed.payload.request.intent_id='CI-'+'0'.repeat(24);
  assert.equal(qualifiedOwnerHTTP(changed,'public'),null,'the payload and its route must name the same request');
});

test('a continuity child for another namespace, another task or outside the request contract is refused before any GET; a mismatched reply is not shown',async()=>{
  const route=(handle,request,{project='public',id='work'}={})=>{handle.payload.request=request;handle.payload.namespace=project;handle.payload.id=id;
    handle.http.url='/work/state?'+new URLSearchParams({project,view:'continuity',id,request:JSON.stringify(request)});return handle;};
  const cases=[[h=>route(h,h.payload.request,{project:'other'}),/another work namespace/],[h=>route(h,h.payload.request,{id:'other'}),/Only this task's own progress reads open here/],
    [h=>route(h,{part:'completion'}),/invalid typed coordinates/],[h=>route(h,{part:'completion',intent_id:'CI-short'}),/invalid typed coordinates/],
    [h=>{h.http.url=h.http.url.replace('completion','summary');},/does not match its request/]];
  for(const [change,refusal] of cases){
    const read=copy(CONTINUE_RESULT.read);change(read);const current=copy(SUMMARY_READY);current.next={kind:'inspect',callable:false,reason:'Inspect the original prepared completion.',read};
    const transport=owner({summary:current}),s=await mount(transport);
    try{const before=transport.reads('continuity').length;await findButton(section(s.host),'Read what this step waits on').onclick();await flush();
      assert.equal(transport.reads('continuity').length,before,'refused before any read: '+refusal);assert.match(s.host.textContent,refusal);assert.equal(transport.posts().length,0);
    }finally{s.controller.destroy();s.dom.restore();}
  }
  // the countercase transport answers a completion request with the summary: it is read once and never shown as the completion
  const current=copy(SUMMARY_READY);current.next={kind:'inspect',callable:false,reason:'Inspect the original prepared completion.',read:copy(CONTINUE_RESULT.read)};
  const transport=owner({summary:current}),s=await mount(transport);
  try{await findButton(section(s.host),'Read what this step waits on').onclick();await flush();
    assert.match(section(s.host).querySelector('.work-continuity-child').textContent,/This read is not shown: The Work owner returned a different progress record than this read asked for\./);
  }finally{s.controller.destroy();s.dom.restore();}
});

// VARIANT faithful owner: the completion part assembled from the actual summary_ready intent/readiness and proof_attached members
test('VARIANT faithful completion reply: the issued child is read once, shown in owner words beside the progress, and offers no second action',async()=>{
  const current=copy(SUMMARY_READY);current.next={kind:'inspect',callable:false,reason:'Inspect the original prepared completion.',read:copy(CONTINUE_RESULT.read)};
  const {readiness,...intent}=copy(SUMMARY_READY.completion.intents[0]);
  const completion={schema_version:'laplace.work-continuity/1',part:'completion',subject:copy(SUBJECT),intent,readiness,proofs:[{id:PROOF_RESULT.proof.id,slot_id:'a-functional',reference:copy(PROOF)}],
    next:{kind:'inspect',callable:false,reason:'READY'},execution:{account:{state:'ACTIVE',capacity:'SUFFICIENT'},observed_at:'2026-10-30T13:01:54.189925+00:00',qualification:'Live account observation; it is not part of the readiness basis beyond its state and capacity.'}};
  const transport=owner({summary:current,continuity:async q=>JSON.parse(q.get('request')).part==='completion'?completion:current}),s=await mount(transport);
  try{await findButton(section(s.host),'Read what this step waits on').onclick();await flush();
    assert.deepEqual(transport.reads('continuity').map(call=>JSON.parse(new URL(call.path,'http://local').searchParams.get('request'))),[{part:'summary'},{part:'completion',intent_id:INTENT}]);
    const child=section(s.host).querySelector('.work-continuity-child'),text=child.textContent,exact=child.querySelector('.operator-exact').textContent;
    assert.match(text,/Prepared completion: ready to continue\./);assert.match(text,/arrived \(verified\)\. Arrival is not a review or acceptance\./);
    assert.match(text,/It is not a review, acceptance or completion\./);assert.match(text,/Source account: active · capacity sufficient\./);
    assert.match(exact,/Prepared completion CI-aaddb011300a6ac5825851e5/);assert.match(exact,/Proof CP-84e7da14849ed4b0bc67da3e · slot a-functional/);
    assert.doesNotMatch(text.replace(exact,''),/CI-|WS-|WT-|CP-/,'exact identities stay under Exact');
    assert.equal(child.all().filter(n=>n.tag==='button').length,0,'a child read offers no second action');assert.equal(transport.posts().length,0);
    assert.doesNotMatch(text,/\baccepted\b/i);
  }finally{s.controller.destroy();s.dom.restore();}
});

// Independent finding C-child-slot-supersession (ART-0517b60cb60d422ba0ddbbadc72e2a73; probe child-slot-race.mjs
// sha256:25d31a2e539c69e2d8ef6589548dfef09eaf198913b9cfc00512504494e46480): two actual distinct enabled production controls
// read the same issued handle into the one child slot; the operator-only proof file write is omitted, assertions kept.
for(const late of ['success','error'])test('connected completion slot discards older '+late+' after newer distinct control observation',async()=>{
 const read=copy(CONTINUE_RESULT.read),current=copy(SUMMARY_READY);current.next={kind:'inspect',callable:false,reason:'Inspect prepared completion.',read};let count=0,release;
 const child=marker=>({schema_version:'laplace.work-continuity/1',part:'completion',subject:copy(SUBJECT),intent:copy(SUMMARY_READY.completion.intents[0]),readiness:{...copy(SUMMARY_READY.completion.intents[0].readiness),state:'HELD',reasons:[marker]},proofs:[],next:{reason:marker},execution:{}});
 const transport=owner({summary:current,continuity:async q=>{
  const request=JSON.parse(q.get('request'));if(request.part==='summary')return current;
  if(++count===1)return new Promise((resolve,reject)=>{release=()=>late==='error'?reject(Error('OLD_FIRST_ERROR')):resolve(child('OLD_FIRST_OBSERVATION'));});
  return child('FRESH_SECOND_OBSERVATION');
 },detailOf:id=>detail(id,{extra:{blockers:[{kind:'OWNER_INSPECTION_REQUIRED',message:'Inspect current prepared completion.',read_handles:[read]}]}})});
 const s=await mount(transport);
 try{
  const first=findButton(s.host,'Read recorded details'),second=findButton(section(s.host),'Read what this step waits on');assert.ok(first&&second&&first!==second,'two actual distinct production read controls');
  const pending=first.onclick();await flush();assert.ok(release);await second.onclick();await flush();assert.match(s.host.querySelector('.work-continuity-child').textContent,/FRESH_SECOND_OBSERVATION/);release();await pending;await flush();
  const shown=s.host.querySelector('.work-continuity-child').textContent;
  assert.match(shown,/FRESH_SECOND_OBSERVATION/,'the newer connected-slot observation must survive an older response or error');
  assert.doesNotMatch(shown,/OLD_FIRST/);assert.equal(transport.posts().length,0);
 }finally{s.controller.destroy();s.dom.restore();}
});

// VARIANT owner-shaped B002 dispatch run fields (parent_synthesis, actions.cancel_dispatch) on the selected Work's dispatch
test('dispatch card states a synthesis outside the original parent, its errors and an unpermitted attach; an unpermitted cancel offers no control',async()=>{
  const withDispatch=id=>{const value=detail(id);if(id==='work')value.task.dispatch={execution_state:'running',review_state:'none',children:[],
    parent_synthesis:{title:'Parent synthesis step',status:'PENDING',authored:false,consumed:false,execution_location:'child-session',kind:'synthesis',parent_session_id:'WS-parent',step_id:'synthesis-1',continuation_phase:'waiting',
      errors:[{code:'ORIGINAL_PARENT_SYNTHESIS_REQUIRED',message:'This synthesis must run in the original parent.'}],attach_action:{permitted:false,reason:'Nothing to attach until the synthesis is authored.'}},
    actions:{cancel_dispatch:{permitted:false,reason:'Every child has settled.'}}};return value;};
  const transport=owner({summary:SUMMARY_READY,detailOf:id=>withDispatch(id)}),s=await mount(transport);
  try{const card=s.host.querySelector('.work-dispatch');assert.ok(card,'the dispatch card is painted');const text=card.textContent;
    assert.match(text,/Parent synthesis “Parent synthesis step”: pending · not authored yet\./);assert.match(text,/outside the original parent \(child session\)/);
    assert.match(text,/This synthesis must run in the original parent\./);assert.match(text,/Nothing to attach until the synthesis is authored\./);
    assert.match(text,/Cancel is not offered now: Every child has settled\./);assert.equal(findButton(card,'Cancel dispatched work'),undefined);
    assert.match(card.querySelector('.operator-exact').textContent,/Parent session WS-parent · step synthesis-1/);assert.equal(transport.posts().length,0);
    // the card's only acceptance statement is the owner's own review count; the synthesis line infers none
    assert.match(text,/Exact accepted reviews: none/);assert.match(text,/it is not a review or acceptance\./);
    assert.doesNotMatch(text.replace('Exact accepted reviews: none',''),/\baccepted\b/i);
  }finally{s.controller.destroy();s.dom.restore();}
});
