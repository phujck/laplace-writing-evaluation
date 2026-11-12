import test from 'node:test';
import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
import {installDOM} from './helpers/evidence_reader_harness.mjs';
import {renderLiteratureMetadataForm} from '../src/laplace/web/static_shared/literature-metadata.mjs';
const output=process.env.RETAINED_LITERATURE_OUTPUT;
test('one metadata form keeps manual path and explicit human fields while retained mode locks original identity',async()=>{
 const dom=installDOM();try{const host=document.createElement('section');document.body.append(host);const draft={title:'Public transcript α 中 🌱',description:'Author-supplied public transcript',creators:'A. Author\nB. Reader',item_type:'unpublished',path:'inputs/legacy.txt'},changes=[],saved=[];
 const manual=renderLiteratureMetadataForm(host,{values:draft,onChange:(key,value)=>changes.push([key,value]),onSave:value=>saved.push(value)});assert.equal(manual.controls.path.value,draft.path);assert.equal(manual.controls.url.type,'url');assert.equal(manual.controls.item_type.value,'unpublished');await manual.form.onsubmit({preventDefault(){}});assert.deepEqual(saved[0],manual.snapshot());
 const identity={project:'public',artifact_id:'ART-original',sha256:'a'.repeat(64)},retained=renderLiteratureMetadataForm(host,{values:draft,retainedSource:identity,onChange:(key,value)=>changes.push([key,value]),onSave:value=>saved.push(value)});assert.equal(retained.controls.path,undefined);assert.equal(retained.form.children[0].textContent,'Title');assert.equal(retained.form.children[1].textContent,'Source provenance');const details=retained.form.children.filter(node=>node.tag==='details');assert.equal(details.length,2);assert.ok(details.every(node=>node.open!==true));assert.match(details[0].textContent,/ART-original/);assert.equal(retained.form.children.indexOf(retained.save)<retained.form.children.indexOf(details[1]),true);
 retained.setBusy(true);assert.equal(retained.save.disabled,true);assert.equal(retained.controls.title.disabled,false);retained.controls.title.value+=' later authored text';retained.controls.title.oninput();retained.setBusy(false);await retained.form.onsubmit({preventDefault(){}});assert.equal(saved[1].title,'Public transcript α 中 🌱 later authored text');assert.equal(saved[1].description,draft.description);assert.equal(saved[1].path,undefined);assert.deepEqual(changes.at(-1),['title',saved[1].title]);assert.equal(draft.title,'Public transcript α 中 🌱');
 if(output)await writeFile(output+'/metadata-form-proof.json',JSON.stringify({manual:saved[0],retained:saved[1],identity,exact_details_default_closed:true,later_typing_preserved:true,meaning:'Production form only; local DOM, no owner fields guessed or transport/provider'},null,2));
 }finally{dom.restore();}
});
