// CR-R1 human route (M5 2026-10-15; repair1 AR-R3 2026-10-16): a saved refusal that names changed_reads_page offers
// "Inspect every changed consulted read", which opens the proposal owner's changed-read pages in the existing read-only
// inspector and walks them with the owner's own continuation. A returned page must be the exact requested candidate
// (record and version, not only the turn) and a continuation must keep its observation cut; a refusal before any
// observation and a partial traversal never read as complete. The real saved-failure renderer and inspector run over
// the DOM double the recovery-navigation tests use; only the HTTP owner reads are stubbed.
import test from 'node:test';
import assert from 'node:assert/strict';
import {installDOM,Node} from './helpers/evidence_reader_harness.mjs';
import {WorkspaceSession} from '../src/laplace/web/static_shared/workspace-session.mjs';
import {inspectRecoveryRead} from '../src/laplace/web/static_shared/workspace-analytics.mjs';
import {ownerHumanTarget} from '../src/laplace/web/static_shared/writing-owner-read.mjs';

const pageURL=(extra={})=>'/authoring/proposal-preview?'+new URLSearchParams({project:'P',id:'WT-original',record_id:'PROP-expected',view:'changed-reads',...extra});
const failure=(extra={})=>({record:'writing-tool-failure',id:'TOOLFAIL-original',project:'P',turn_id:'WT-original',operation:'apply_revision',error:'Consulted project evidence changed.',resolved_later:false,
  recovery:{consumed_read_recovery:{next_reads:[],changed_reads_page:{operation:'authoring/proposal-preview',payload:{id:'WT-original',record_id:'PROP-expected',view:'changed-reads',...extra},http:{method:'GET',url:pageURL(extra)}}}}});
const row=n=>({read_id:'READ-'+n,operation:'read_artifact',currentness:'CHANGED',read_detail:{operation:'author_history',payload:{view:'record',id:'activity:journal:READ-'+n}},renew:null,payload_omitted:true,changed_selectors:{changed:['content']}});
const page=(rows,from,to,of,next,extra={})=>({schema_version:'laplace.changed-consulted-reads/2',status:'OBSERVED',project:'P',turn_id:'WT-original',record_id:'PROP-expected',proposal_version:'sha256:a',
  observation:{cut:'sha256:cut-1',consulted:6,replayed:6,changed:of},changed:{from,to,of},changed_reads:rows,complete:!next,
  next:next?{http:{method:'GET',url:pageURL({proposal_version:'sha256:a',cursor:next,limit:'2'})}}:null,note:'Read-only diagnostics.',...extra});
const find=(node,label)=>node.all().find(n=>n.tag==='button'&&n.textContent===label);
const disclose=(node,label)=>{const detail=node.all().find(n=>n.tag==='details'&&n.children[0]?.textContent===label);assert.ok(detail,label);detail.open=true;detail.ontoggle?.();return detail;};

function open(d,request,row=failure()){
  const host=new Node('article');d.body.append(host);
  const session=Object.assign(Object.create(WorkspaceSession.prototype),{project:'P',session:'WS-original',viewEpoch:1,guard:fn=>fn(),compose(){},
    onOpenOwner:(read,label,options)=>inspectRecoveryRead(read,{request,project:'P',...options})});
  session.failures(host,{id:'WT-original',tool_failures:[row]});
  disclose(host,'1 operation failed without a recorded successful retry');disclose(host,'Error and follow-up');
  return host;
}

test('the page route keeps its exact candidate and continuation coordinates and refuses malformed ones',()=>{
  const target=ownerHumanTarget(pageURL({proposal_version:'sha256:a',cursor:'abc',limit:'4'}));
  assert.deepEqual([target.kind,target.project,target.id,target.recordId,target.version,target.cursor,target.limit],['changed-reads','P','WT-original','PROP-expected','sha256:a','abc',4]);
  for(const bad of [pageURL({limit:'21'}),pageURL({limit:'0'}),pageURL({file:'x'}),pageURL()+'&cursor=a&cursor=b',pageURL({cursor:''}),'/authoring/proposal-preview?'+new URLSearchParams({project:'P',view:'changed-reads'})])
    assert.equal(ownerHumanTarget(bad),null,bad);
});

test('a saved refusal walks one observation cut through the owner pages, read-only, and says when it is complete',async()=>{
  const d=installDOM();try{
    const calls=[];const request=async path=>{calls.push(path);const q=new URL(path,'http://localhost').searchParams;
      if(q.get('view')==='changed-reads')return q.get('cursor')==='c2'?page([row(3)],2,3,3,null):page([row(1),row(2)],0,2,3,'c2');
      throw Error('unexpected '+path);};
    const host=open(d,request);
    await find(host,'Inspect every changed consulted read').click();
    const dialog=d.dialogs()[0];
    assert.match(dialog.textContent,/candidate PROP-expected · changed reads 0–2 of 3 · 6 consulted reads observed/);
    assert.match(dialog.textContent,/READ-1/);assert.doesNotMatch(dialog.textContent,/listed\./,'a partial page claims no completion');
    await find(dialog,'Next changed reads').click();
    assert.match(dialog.textContent,/READ-3/);assert.match(dialog.textContent,/All 3 changed consulted reads of this observation are listed/);
    assert.equal(find(dialog,'Next changed reads'),undefined);
    assert.deepEqual(calls.map(path=>new URL(path,'http://localhost').searchParams.get('cursor')),[null,'c2']);
    assert.ok(calls.every(path=>path.startsWith('/authoring/proposal-preview?')),'only GET owner reads; nothing is applied or renewed');
  }finally{d.restore();}
});

for(const [name,first,second] of [
  ['another candidate of the same turn',page([row(1)],0,1,1,null,{record_id:'PROP-WRONG'}),null],
  ['another version of the requested candidate',page([row(1)],0,1,1,null,{proposal_version:'sha256:b'}),null,{proposal_version:'sha256:a'}],
  ['a continuation for another record',page([row(1)],0,1,2,'c2',{next:{http:{method:'GET',url:pageURL({record_id:'PROP-WRONG',proposal_version:'sha256:a',cursor:'c2'})}}}),null],
  ['a continuation for another version',page([row(1)],0,1,2,'c2',{next:{http:{method:'GET',url:pageURL({proposal_version:'sha256:b',cursor:'c2'})}}}),null],
  ['a continuation for another turn',page([row(1)],0,1,2,'c2',{next:{http:{method:'GET',url:pageURL({id:'WT-other',proposal_version:'sha256:a',cursor:'c2'})}}}),null],
  ['a continuation with another observation cut',page([row(1)],0,1,2,'c2'),page([row(2)],1,2,2,null,{observation:{cut:'sha256:cut-2',consulted:6,replayed:6,changed:2}})],
]){
  test('the inspector refuses '+name,async()=>{
    const d=installDOM();try{
      const request=async path=>new URL(path,'http://localhost').searchParams.get('cursor')?second:first;
      const host=open(d,request,name.includes('version of the requested')?failure({proposal_version:'sha256:a'}):failure());
      await find(host,'Inspect every changed consulted read').click();
      let dialog=d.dialogs()[0];
      if(second){await find(dialog,'Next changed reads').click();dialog=d.dialogs()[0];}
      assert.match(dialog.textContent,/different (changed-read page|candidate|observation cut)/);
      assert.doesNotMatch(dialog.textContent,/READ-2|listed\./);
    }finally{d.restore();}
  });
}

test('a refusal before any observation is shown as stopped, never as an empty or complete observation',async()=>{
  const d=installDOM();try{
    const request=async()=>({schema_version:'laplace.changed-consulted-reads/2',status:'REFUSED',project:'P',turn_id:'WT-original',proposal_version:'sha256:a',
      currentness:'STALE',reason:'The candidate source pins disagree.',observation:null,changed_reads:[],complete:false,next:null,note:'nothing was observed'});
    const host=open(d,request);
    await find(host,'Inspect every changed consulted read').click();
    const text=d.dialogs()[0].textContent;
    assert.match(text,/Stopped before observing: The candidate source pins disagree/);assert.match(text,/nothing is listed or complete/);
    assert.doesNotMatch(text,/All \d+ changed consulted reads|No consulted read changed in this observation/);
  }finally{d.restore();}
});

test('an invalid page limit is never requested',async()=>{
  const d=installDOM();try{
    const calls=[];const host=open(d,async path=>{calls.push(path);return page([],0,0,0,null);},failure({limit:'0'}));
    assert.equal(find(host,'Inspect every changed consulted read'),undefined);assert.deepEqual(calls,[]);
  }finally{d.restore();}
});
