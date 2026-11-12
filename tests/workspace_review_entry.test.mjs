// M5 (2026-10-20): the composed Review-in-manuscript entry in the real shell: mountReview's queue row ->
// createProjectReview.open (exact version/handle, selection emitted) -> proposals.review -> manuscript.ready ->
// views.show('manuscript'). The transition already exists; this test shows it on the real markup with the owner's
// own queue shape (the census PROPOSAL row), and that a readiness that does not complete (the view did not stay open,
// or could not open) ends in an explicit status, never a silent return. No provider, browser or preview body.
import {test} from 'node:test';
import assert from 'node:assert/strict';
const {mountShell}=await import('./helpers/shell_fixture.mjs');
const PROPOSAL={id:'T',project:'book',proposal_version:'V',read_handle:{http:{method:'GET',url:'/authoring/proposal-preview?'+new URLSearchParams({project:'book',id:'T',proposal_version:'V',record_id:'record-V',view:'summary'})},native_request:{verb:'read',target:'book::T',payload:{id:'T',proposal_version:'V',record_id:'record-V',view:'summary'}}},edit_count:2,files:['chapter.tex'],proposal_state:'ready',turn_ts:'2026-10-20T06:27:48.625Z'};
const queueRoute=()=>({project:'book',view:'queue',as_of:'cut',proposals:[structuredClone(PROPOSAL)],count:1,count_basis:'current rows on this inspected page; total unknown until complete traversal',pagination:{next_read:null,remaining_candidates:0},coverage:{unavailable_candidate_records:[]}});
const find=(root,label)=>root.querySelectorAll('button').find(node=>node.textContent===label);
const click=async node=>{await node.onclick?.({preventDefault(){},stopPropagation(){},target:node});};

test('Review in manuscript: the real queue row emits its exact selection and the shell shows Manuscript; a readiness that does not stay open ends in an explicit status',async()=>{
  const s=await mountShell({query:'view=review',routes:{'/authoring/proposals':queueRoute}});
  try{
    assert.equal(s.root.dataset.view,'review');
    const entry=find(s.root,'Review in manuscript');assert.ok(entry,'the queue row renders its entry on the real markup');
    const pending=click(entry);await s.settle();
    assert.equal(s.root.dataset.view,'manuscript','the explicit show moved the shell to Manuscript');
    assert.match(location.href,/view=manuscript/);
    const provenance=[...s.root.querySelectorAll('details')].find(node=>node.textContent.includes('Selected comparison provenance'));
    assert.ok(provenance,'the selection was emitted before readiness was awaited');assert.match(provenance.textContent,/Turn T/);assert.match(provenance.textContent,/Version V/);
    assert.ok(s.calls.some(call=>call.includes('/authoring/proposals')),'the queue was read from its owner');
    assert.ok(!s.calls.some(call=>call.includes('/authoring/proposal-preview')),'no preview is read before the manuscript is ready');
    assert.equal(s.notice(),'','no refusal was reported while the manuscript frame loads');
    // the person leaves before the frame is ready: readiness answers null and the review says so
    await s.workspace.show('review');await s.settle();await pending;await s.settle();
    assert.equal(s.root.dataset.view,'review');
    assert.match(s.notice(),/did not open or did not stay open, so the saved comparison was not started/);
  }finally{s.restore();}
});

test('a project whose material has no manuscript: the show is refused and the review entry reports it instead of returning silently',async()=>{
  const s=await mountShell({query:'view=review',routes:{'/authoring/proposals':queueRoute,'/projects/metadata':()=>({project:'book',title:'Fixture Book',purpose:'A test purpose.',
    capabilities:{manuscript:false,research:true,review:true,presentation:true,materials:true,material_references:true,concepts:true,reader_plan:true}})}});
  try{
    const entry=find(s.root,'Review in manuscript');assert.ok(entry);
    await click(entry);await s.settle();await s.settle();
    assert.equal(s.root.dataset.view,'review','a refused show leaves the shell where it was');
    assert.match(s.notice(),/Manuscript is unavailable for the current project material/,'the shell\'s own refusal stays the stated reason');
    assert.ok(!/Cannot read properties/.test(s.notice()),'no exception reaches the status');
  }finally{s.restore();}
});
