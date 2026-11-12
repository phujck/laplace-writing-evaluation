import {test} from 'node:test';
import assert from 'node:assert/strict';
import {proposalDraftKey,proposalActionAllowed,proposalSourceChanges} from '../src/laplace/web/static_shared/manuscript-editing.mjs';
test('draft identity cannot bleed across saved versions or conversations',()=>{
 const base=proposalDraftKey('p','t','v1','e');assert.notEqual(base,proposalDraftKey('p','t','v2','e'));assert.notEqual(base,proposalDraftKey('p','other','v1','e'));
});
test('owner actions are mandatory; current bytes alone confer no action',()=>{
 assert.equal(proposalActionAllowed({status:'pending',review_token:'token'},'merge'),false);
 assert.equal(proposalActionAllowed({allowed_actions:['merge']},'merge'),true);
 assert.equal(proposalActionAllowed({allowed_actions:['merge'],resolution_available:false},'merge'),false);
 assert.equal(proposalActionAllowed({allowed_actions:['keep-current'],resolution_available:false},'keep-current'),true);
});
test('long source comparison retains unchanged paragraphs and marks changed mathematics',()=>{
 const paragraphs=Array.from({length:80},(_,i)=>`Paragraph ${i}. A generic premise has a stated consequence.`);
 const before=paragraphs.join('\n\n')+'\n\n\\begin{equation}\nE=mc^2\n\\end{equation}\n',after=before.replace('Paragraph 5.','Paragraph five.').replace('E=mc^2','E=mc^2+\\epsilon');
 const result=proposalSourceChanges(before,after);assert.equal(result.current.map(r=>r.text).join(''),before);assert.equal(result.proposed.map(r=>r.text).join(''),after);
 assert.equal(result.plan.after.filter(spans=>spans.length).length,2);assert.equal(result.plan.before.filter(spans=>spans.length).length,1);
 const equation=result.proposed.findIndex(row=>row.text.includes('\\begin{equation}'));assert.ok(result.plan.after[equation].some(span=>result.proposed[equation].text.slice(span.start,span.end).includes('epsilon')));
});

test('standing draft overlap uses the whole owner target, unrelated draft stays independent',async()=>{
 const {proposalDraftOverlap}=await import('../src/laplace/web/static_shared/manuscript-editing.mjs');
 const target={file:'chapter.tex',current_anchor:{file:'chapter.tex',line_start:10,line_end:40}};
 assert.equal(proposalDraftOverlap([{file:'chapter.tex',line_start:9,line_end:9}],target),false);
 assert.equal(proposalDraftOverlap([{file:'appendix.tex',line_start:12,line_end:12}],target),false);
 assert.equal(proposalDraftOverlap([{file:'sources/p/chapter.tex',line_start:22,line_end:24}],target),true);
 assert.equal(proposalDraftOverlap([{unplaced:true}],target),true);
 assert.equal(proposalActionAllowed({allowed_actions:['merge'],local_draft_overlap:true},'merge'),false);
 assert.equal(proposalActionAllowed({allowed_actions:['keep-current'],local_draft_overlap:true},'keep-current'),true);
});

test('physical target proof remains distinct from stale consumed inputs and mutation authority',async()=>{
 const {proposalScopeUnproven,proposalChangeRequest,applicationSourceStateLabel}=await import('../src/laplace/web/static_shared/manuscript-editing.mjs');
 const stale={file:'appendix.tex',edit_id:'e',status:'conflict',target_proof:{status:'CURRENT'},resolution_available:false,allowed_actions:['keep-current'],basis_currentness:'STALE',lifecycle:'blocked',current_before:'Verified current words',current_anchor:{file:'appendix.tex',line_start:2,line_end:2}};
 assert.equal(proposalScopeUnproven(stale),false);assert.equal(proposalActionAllowed(stale,'merge'),false);
 assert.deepEqual(proposalChangeRequest(stale).selection,{files:['appendix.tex'],quote:'Verified current words',anchor:stale.current_anchor});
 assert.deepEqual(proposalChangeRequest({...stale,local_draft_overlap:true}).selection,{files:['appendix.tex']});
 assert.deepEqual(proposalChangeRequest({...stale,target_proof:{status:'UNPROVEN'}}).selection,{files:['appendix.tex']});
 assert.match(applicationSourceStateLabel('PREIMAGE'),/earlier source/);assert.doesNotMatch(applicationSourceStateLabel('PREIMAGE'),/undo|revert/i);assert.match(applicationSourceStateLabel('DIVERGED'),/changed since/);assert.equal(applicationSourceStateLabel(undefined),'');
});
