import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {ownerHumanTarget,qualifiedOwnerHTTP,passageContinuationURL} from '../src/laplace/web/static_shared/writing-owner-read.mjs';
import {structureObservation,spineReadURL} from '../src/laplace/web/static_shared/workspace-spine.mjs';
import {readerMetadataSubmission,readerAcknowledgementMatches,readerReviewSubmission,sameReaderActionBasis,sameReaderSubjectGuard,readerLiteratureTarget} from '../src/laplace/web/static_shared/reader-state.mjs';
import {installDOM,loadReader,findButton} from './helpers/evidence_reader_harness.mjs';
const state=JSON.parse(await readFile(new URL('./fixtures/editor_spine/reader-state.json',import.meta.url),'utf8'));
const bib=JSON.parse(await readFile(new URL('./fixtures/editor_spine/bibliography-entry.json',import.meta.url),'utf8'));
test('actual native requests and replies preserve original subject and consumed input identity',()=>{
 for(const [request,result]of [[state.contract_request,state.contract_write],[state.paragraph_request,state.paragraph_write]]){
  assert.equal(readerAcknowledgementMatches(result,{project:'book',...request}),true);
  const corrupt=structuredClone(result);corrupt.read_handle.http.query.project='other';assert.equal(readerAcknowledgementMatches(corrupt,{project:'book',...request}),false);
 }
 const observation=structureObservation(state.detail);assert.deepEqual(observation,state.detail.structure_observation);assert.ok(observation.reader_subjects.length);
 const target=qualifiedOwnerHTTP(state.review_write.read_handle,'book');assert.equal(target.owner.kind,'work');assert.equal(target.owner.project,'book');
 const prepared=state.detail.sections[0].reader_transition.review_action;assert.deepEqual(readerReviewSubmission(prepared,'book').reader_basis,prepared.payload.reader_basis);
});
test('a reader input situated on an owner concept read hands exactly that claim to Literature, nothing else',()=>{
 assert.deepEqual(readerLiteratureTarget({label:'Assumption A',read:{operation:'concept',payload:{node:'claim:assumption-A'}}}),{claim_id:'claim:assumption-A',label:'Assumption A'});
 for(const item of [{read:{operation:'references_attached',payload:{citekey:'k'}}},{read:{operation:'concept',payload:{}}},{label:'x'},null])
  assert.equal(readerLiteratureTarget(item),null);
 for(const link of state.detail.sections[0].reader_transition.links){const target=readerLiteratureTarget(link);
  if(link.read?.operation==='concept')assert.equal(target.claim_id,link.read.payload.node);else assert.equal(target,null);}
});
test('actual exact paragraph and lazy-choice reads roundtrip without treating IDs as ordinals',()=>{
 const section=state.detail.sections[0],paragraph=section.paragraph_plan.paragraphs.items[0];
 const target=ownerHumanTarget(spineReadURL(paragraph.read_handle,'book'));
 assert.equal(target.read_handle.payload.paragraph_id,paragraph.paragraph_id);
 const choice=ownerHumanTarget(spineReadURL(section.reader_transition.edit_action.choices_read,'book'));assert.equal(choice.read_handle.payload.edit_choices,true);
 for(const link of section.reader_transition.links)assert.ok(qualifiedOwnerHTTP(link.read,'book'),link.kind);
 const original=section.reader_transition.edit_action,changed=structuredClone(original),key=Object.keys(changed.payload.expected_reader_basis.inputs)[0];changed.payload.expected_reader_basis.inputs[key]='sha256:'+'0'.repeat(64);
 assert.equal(sameReaderActionBasis(original,changed),false);assert.equal(sameReaderSubjectGuard(original,changed),true);
 const payload=readerMetadataSubmission(original,{...original.values,entry_state:'A small revised entry state'},'book');assert.deepEqual(payload.expected_reader_basis,original.payload.expected_reader_basis);
});
test('actual Bib-only owner entry is readable without inventing an external literature source',async()=>{
 const dom=installDOM(),reader=await loadReader(),calls=[];
 try{
  const query=bib.available.read_handle.http.query,url='/references/attached?'+new URLSearchParams(query);
  const target=ownerHumanTarget(url);assert.equal(target.kind,'bibliography-entry');
  const dialog=await reader.openArtifact({project:'fixture',ownerRead:target,label:'Citation',request:async path=>{calls.push(path);if(path===url)return bib.available;throw Error('No external lookup or source rewrite is permitted in this read');}});
  assert.match(dialog.textContent,/A fixture source/);assert.match(dialog.textContent,/not evidence that the cited source was read/);assert.deepEqual(calls,[url]);
  assert.ok(findButton(dialog,'Read bibliography source'));dialog.close();
 }finally{reader.destroy();dom.restore();}
});

test('a structure owner link opens the shared plan reader locally and preserves manuscript state',async()=>{
 const owner=JSON.parse(await readFile(new URL('./fixtures/editor_spine/owner-wire.json',import.meta.url),'utf8'));
 const dom=installDOM(),reader=await loadReader(),calls=[];
 const url='/work/structure?'+new URLSearchParams({project:owner.project,view:'detail',section_ids:JSON.stringify([owner.detail.sections[0].id])});
 try{
  const dialog=await reader.openArtifact({ownerRead:ownerHumanTarget(url),label:'Inspected plan item',request:async(path,payload)=>{
   assert.equal(payload,undefined);calls.push(path);return structuredClone(new URL(path,'http://local').searchParams.get('view')==='summary'?owner.summary_after:owner.detail);
  }});
  assert.ok(dialog.textContent.includes(owner.detail.sections[0].title));assert.ok(dialog.textContent.includes('Open Reader plan for actions'));assert.ok(!dialog.textContent.includes('Owner reading unavailable'));
  assert.ok(calls.every(path=>path.includes('/work/structure?')&&!path.includes('view=full')));assert.equal(dom.editor.value,'UNSAVED manuscript');dialog.close();assert.equal(dom.editor.value,'UNSAVED manuscript');
 }finally{reader.destroy();dom.restore();}
});
