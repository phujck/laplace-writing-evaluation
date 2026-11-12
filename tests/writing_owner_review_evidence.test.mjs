import test from 'node:test';
import assert from 'node:assert/strict';
import {ownerHumanTarget,qualifiedOwnerHTTP,continuityRequest} from '../src/laplace/web/static_shared/writing-owner-read.mjs';

test('owner-issued continuity subject pages are typed exactly and malformed ones are refused',()=>{
  const read=request=>({operation:'project',payload:{namespace:'public',view:'continuity',id:'work',request},
    http:{method:'GET',url:'/work/state?'+new URLSearchParams({project:'public',view:'continuity',id:'work',request:JSON.stringify(request)})}});
  for(const payload of [{phase_id:'PHASE-abc',section:'readonly_carry',offset:0},{phase_id:'PHASE-abc',section:'hunks',path:'src/a.py',offset:4},
    {phase_id:'PHASE-abc',section:'inputs',obligation_id:'source',offset:0},{phase_id:'PHASE-abc',section:'initial_reads',obligation_id:'source',offset:0,limit:8},
    // the issued cut-pinned next and a NOT_EXPANDED row's exact descent (project_work_continuity.subject_page_handle)
    {phase_id:'PHASE-abc',section:'changed_files',offset:7,cut:'sha256:'+'c'.repeat(64)},
    {phase_id:'PHASE-abc',section:'changed_files',offset:7,cut:'sha256:'+'c'.repeat(64),item_sha256:'sha256:'+'d'.repeat(64),item_offset:12000}]){
    const issued=read({part:'subject',payload}),target=qualifiedOwnerHTTP(issued,'public');
    assert.equal(target.owner.kind,'work-continuity');assert.equal(target.owner.part,'subject');
    assert.deepEqual(target.owner.read_handle.payload,issued.payload);
    assert.equal(qualifiedOwnerHTTP(issued,'foreign'),null);
  }
  for(const payload of [undefined,{phase_id:'PHASE-abc'},{phase_id:'other',section:'effects'},{phase_id:'PHASE-abc',section:'hunks'},
    {phase_id:'PHASE-abc',section:'inputs'},{phase_id:'PHASE-abc',section:'effects',offset:-1},{phase_id:'PHASE-abc',section:'effects',limit:257},
    {phase_id:'PHASE-abc',section:'effects',file:'x'},{phase_id:'PHASE-abc',section:'write'},
    {phase_id:'PHASE-abc',section:'effects',cut:'stale'},{phase_id:'PHASE-abc',section:'effects',item_offset:0},
    {phase_id:'PHASE-abc',section:'effects',item_sha256:'sha256:'+'d'.repeat(64)},
    {phase_id:'PHASE-abc',section:'effects',item_sha256:'sha256:'+'d'.repeat(64),item_offset:-1}]){
    assert.equal(continuityRequest(payload===undefined?{part:'subject'}:{part:'subject',payload}),null);
    assert.equal(ownerHumanTarget(read({part:'subject',payload}).http.url),null);
  }
});

const pin='sha256:'+'a'.repeat(64),page='sha256:'+'b'.repeat(64);
function handle(request){return {operation:'project',payload:{namespace:'public',view:'review-evidence',id:'work',request},
  http:{method:'GET',url:'/work/state?'+new URLSearchParams({project:'public',view:'review-evidence',id:'work',request:JSON.stringify(request)})}};}

test('project review-evidence handles retain the exact demand and observation',()=>{
  for(const request of [{demand:'aggregate',selector:'all'},
    {demand:'enumerate',selector:'remaining-required',observation:pin,offset:0,limit:6},
    {demand:'support',selector:'required',observation:pin,enumeration:page,offset:0,limit:6,ids:['a','b']}]){
    const read=handle(request),target=qualifiedOwnerHTTP(read,'public');
    assert.equal(target.owner.kind,'work-review-evidence');
    assert.deepEqual(target.owner.read_handle.payload,read.payload);
    assert.equal(qualifiedOwnerHTTP(read,'foreign'),null);
    for(const changed of [{namespace:'foreign'},{id:'other'},{operation:'task'},
      {request:{...request,selector:request.selector==='all'?'required':'all'}}]){
      const bad=structuredClone(read);
      if(changed.operation)bad.operation=changed.operation;else Object.assign(bad.payload,changed);
      assert.equal(qualifiedOwnerHTTP(bad,'public'),null);
    }
  }
});

test('malformed or effect-shaped review-evidence URLs never become generic reads',()=>{
  for(const request of [{demand:false},{selector:false},{demand:'publish'},
    {demand:'aggregate',observation:pin},{demand:'enumerate'},
    {demand:'enumerate',observation:pin,limit:true},
    {demand:'enumerate',observation:pin,offset:-1},
    {demand:'support',observation:pin,enumeration:page,ids:['a','a']},
    {demand:'support',observation:pin,enumeration:page,ids:[false]},
    {demand:'support',observation:pin,enumeration:page,ids:['a'],scope:'owned-workspace'}]){
    assert.equal(ownerHumanTarget(handle(request).http.url),null);
  }
  const valid=handle({demand:'aggregate',selector:'all'});
  assert.equal(ownerHumanTarget(valid.http.url+'&id=other'),null);
  assert.equal(ownerHumanTarget(valid.http.url+'&action=planning'),null);
});

test('guarded phase reads preserve the exact observed row-set guard',()=>{
  const payload={namespace:'public',view:'review',id:'work',phase_id:'phase',phase_revision:pin};
  const read={operation:'project',payload,http:{method:'GET',url:'/work/state?'+new URLSearchParams({project:'public',view:'review',id:'work',phase_id:'phase',phase_revision:pin})}};
  const target=qualifiedOwnerHTTP(read,'public');
  assert.equal(target.owner.kind,'work-review-phase');
  assert.deepEqual(target.owner.read_handle.payload,payload);
  for(const changed of [{phase_revision:page},{phase_id:'other'},{namespace:'foreign'},{request:{action:'write'}}]){
    assert.equal(qualifiedOwnerHTTP({...read,payload:{...payload,...changed}},'public'),null);
  }
  assert.equal(ownerHumanTarget(read.http.url+'&phase_revision='+page),null);
  // An owner-issued body page of a header-only phase is the same pinned read at an exact offset, never a looser one.
  const body={...read,payload:{...payload,offset:12000},http:{method:'GET',url:read.http.url+'&offset=12000'}};
  assert.deepEqual(qualifiedOwnerHTTP(body,'public').owner.read_handle.payload,body.payload);
  for(const changed of [{offset:0},{offset:'12000'},{phase_revision:page},{phase_id:'other'},{namespace:'foreign'}]){
    assert.equal(qualifiedOwnerHTTP({...body,payload:{...body.payload,...changed}},'public'),null);
  }
  assert.equal(qualifiedOwnerHTTP({...read,payload:{...payload,offset:5}},'public'),null);   // an offset the URL never issued
  for(const bad of ['&offset=x','&offset=1.5','&offset=12000&offset=0'])assert.equal(ownerHumanTarget(read.http.url+bad),null);
});

test('selected obligation inspection stays exact and separate from guarded phases',()=>{
  const payload={namespace:'public',view:'review',id:'work',obligation_id:'source'};
  const read={operation:'project',payload,http:{method:'GET',url:'/work/state?'+new URLSearchParams({project:'public',view:'review',id:'work',obligation_id:'source'})}};
  assert.equal(qualifiedOwnerHTTP(read,'public').owner.kind,'work-review-obligation');
  for(const changed of [{obligation_id:'other'},{namespace:'foreign'},{phase_id:'phase'},{request:{demand:'support'}}]){
    assert.equal(qualifiedOwnerHTTP({...read,payload:{...payload,...changed}},'public'),null);
  }
  assert.equal(ownerHumanTarget(read.http.url+'&phase_revision='+pin),null);
  const next={...read,payload:{...payload,offset:1,limit:2,as_of:pin},
    http:{method:'GET',url:read.http.url+'&offset=1&limit=2&as_of='+pin}};
  assert.deepEqual(qualifiedOwnerHTTP(next,'public').owner.read_handle.payload,next.payload);
  assert.equal(qualifiedOwnerHTTP({...next,payload:{...next.payload,as_of:page}},'public'),null);
});
