import {test} from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';
import {proposalActionAllowed,proposalChangeRequest,proposalScopeUnproven,proposalReadURL,selectedProposalBody} from '../src/laplace/web/static_shared/manuscript-editing.mjs';
import {sourceEffectFromError} from '../src/laplace/web/static_shared/source-effect.mjs';
// the proposal review is the proposals owner's (workspace-proposals.mjs, M5 S2 F1), run with its services
const source=readFileSync(new URL('../src/laplace/web/static_shared/workspace-proposals.mjs',import.meta.url),'utf8'),start=source.indexOf('  async function reviewProposal('),end=source.indexOf('\n  return {review:reviewProposal}',start);
const {SERVICE_PRELUDE}=await import('./helpers/shell_services.mjs');
const make=new Function('env',`const {manuscriptReady,api,project,session,title,proposalActionAllowed,proposalChangeRequest,proposalScopeUnproven,proposalReadURL,selectedProposalBody,sourceEffectFromError}=env;let logicalOrigin=null,proposalReviewGeneration=0,currentView='manuscript';const sourceWindow=()=>({walk:env.walk});function openSession(){}function readSavedTurn(){}function notice(){}function inspectProjectArtifact(){}function saved(){};${SERVICE_PRELUDE}const manuscript={ready:manuscriptReady,sourceWindow,saved,editor:()=>null,rememberApplication:()=>{}},projectReview={};${source.slice(start,end)}return reviewProposal;`);
test('domain refusal re-reads the same opaque candidate, retains visible error and never retries a write',async()=>{
 const fixture=JSON.parse(readFileSync(new URL('./fixtures/proposal-human-preview-owner-41034609f.json',import.meta.url),'utf8'));
 const displays=[],requests=[];let previews=0;
 const original=fixture.preview,summary=fixture.summary,edit=original.edits[0];
 const blocked={...original,edits:[{...edit,allowed_actions:['keep-current'],basis_currentness:'STALE',lifecycle:'blocked'}]};
 const walk={proposalDraftConflict:()=>false,showProposal:(data,options)=>displays.push({data,options})};
 const review=make({walk,project:'fixture',title:()=>'',session:{},proposalActionAllowed,proposalChangeRequest,proposalScopeUnproven,proposalReadURL,selectedProposalBody,sourceEffectFromError,manuscriptReady:async()=>walk,api:async(path,payload)=>{requests.push({path,payload});if(payload)throw Object.assign(Error('Consumed source changed; request a fresh proposal.'),{result:{error:'Consumed source changed'}});previews++;return new URL(path,'http://fixture').searchParams.has('edit_id')?(previews<3?original:blocked):summary;}});
 await review(summary.turn_id,{proposalVersion:summary.proposal_version,readHandle:summary.read_handle});
 await assert.rejects(displays[0].options.onDecision(edit.edit_id,'accept',{proposal_version:original.proposal_version}),/Consumed source changed/);
 assert.equal(requests.filter(row=>row.payload).length,1);assert.equal(previews,4);
 const reread=new URL(requests.at(-1).path,'http://fixture').searchParams;assert.equal(reread.get('proposal_version'),original.proposal_version);assert.equal(reread.get('edit_id'),edit.edit_id);
 assert.equal(displays.at(-1).options.decisionError,'Consumed source changed; request a fresh proposal.');assert.deepEqual(displays.at(-1).data.edits[0].allowed_actions,['keep-current']);
});
