import {test} from 'node:test';
import assert from 'node:assert/strict';
import {proposalResolutionAvailable,proposalScopeUnproven,proposalChangeRequest,sourceOnlyProposalContext,fileOnlyManuscriptSelection} from '../src/laplace/web/static_shared/manuscript-editing.mjs';
import {readFileSync} from 'node:fs';
// the Send preparation is the conversation wiring's (workspace-conversation.mjs, M5 S2 F1)
const workspace=readFileSync(new URL('../src/laplace/web/static_shared/workspace-conversation.mjs',import.meta.url),'utf8');
const proven={file:'chapter.tex',status:'pending',current_mapping:'proven-current-source-occurrence',current_anchor:{file:'chapter.tex',line_start:3,line_end:5},current_before:'Current owner source',review_token:'token'};
test('resolution requires an owner target; explicit denial defeats cached token',()=>{
 assert.equal(proposalResolutionAvailable(proven),true);
 for(const edit of [{...proven,resolution_available:false},{...proven,current_mapping:'unproven-historical-location'},{...proven,current_anchor:undefined},{...proven,current_anchor:{file:'other.tex',line_start:3,line_end:5}}])assert.equal(proposalResolutionAvailable(edit),false);
 assert.equal(proposalScopeUnproven({...proven,status:'conflict',review_token:undefined}),true);
});
test('fresh reconciliation carries file and candidate provenance, no old words or offsets',()=>{
 const blocked={...proven,status:'conflict',resolution_available:false,edit_id:'EDIT-old',before:'STALE SECRET WORDS',line_start:999,line_end:1010,reason:'stale quote with old instructions'};
 const request=proposalChangeRequest(blocked,{turnId:'WT-old',version:'sha256:old'});
 assert.deepEqual(request.selection,{files:['chapter.tex']});assert.match(request.text,/EDIT-old.*WT-old.*sha256:old/);
 assert.doesNotMatch(request.text,/STALE SECRET WORDS|999|1010|stale quote/);
 assert.equal(fileOnlyManuscriptSelection(request.selection),true);
 const context=sourceOnlyProposalContext({surface:'manuscript',section_ids:['old-section'],node_id:'old-node',selection:{quote:blocked.before,line_start:999}},request.selection);
 assert.deepEqual(context.section_ids,[]);assert.equal(context.surface,'project');assert.equal(context.node_id,undefined);assert.deepEqual(context.selection,request.selection);

});
test('proven request uses current owner text and scope instead of old proposal span',()=>{
 const request=proposalChangeRequest({...proven,before:'Old text',line_start:999,line_end:1000,reason:'Make precise'});
 assert.equal(request.selection.quote,'Current owner source');assert.deepEqual(request.selection.anchor,proven.current_anchor);
});
test('file-only fresh request never settles or autosaves a standing manuscript draft',async()=>{
 const marker='prepareSend:async({context:attention,selection})=>{',start=workspace.indexOf(marker)+marker.length,end=workspace.indexOf('  },onChanged:',start);
 const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
 const prepare=new AsyncFunction('fileOnlyManuscriptSelection','sourceWindow','manuscriptEditor','context','attention','selection','const manuscript={sourceWindow,editor:()=>manuscriptEditor};'+workspace.slice(start,end));
 let calls=0;const win=()=>({walk:{ready:()=>true,prepareForSession:async()=>{calls++;return{draft:{text:'Held source draft'}};}}});
 await prepare(fileOnlyManuscriptSelection,win,null,()=>({}),{surface:'project'},{files:['chapter.tex']});assert.equal(calls,0);
 const result=await prepare(fileOnlyManuscriptSelection,win,null,()=>({}),{surface:'manuscript'},{files:['chapter.tex'],anchor:{file:'chapter.tex',line_start:3,line_end:5}});
 assert.equal(calls,1);assert.equal(result.selection.draft.text,'Held source draft');
});
