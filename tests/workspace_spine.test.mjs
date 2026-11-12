import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {sourceOccurrence,outlineOccurrence,inspectSourceOccurrence,bindingSubmission,boundPlanHeading,structureObservation,readerPlanItemOps,narrativeBeatOperation,spineReadURL} from '../src/laplace/web/static_shared/workspace-spine.mjs';
import {passageProvenancePresentation,ownerHumanTarget} from '../src/laplace/web/static_shared/writing-owner-read.mjs';
import {planPublicationDisposition,savedActionPlanPublication,savedFailurePlanPublication} from '../src/laplace/web/static_shared/plan-publication.mjs';
const owner = JSON.parse(await readFile(new URL('./fixtures/editor_spine/owner-wire.json',import.meta.url),'utf8'));
const passages = JSON.parse(await readFile(new URL('./fixtures/editor_spine/passage-records.json',import.meta.url),'utf8'));
const copy = value => structuredClone(value);
// G18b: the outline row is the trimmed list row; the exact occurrence is rebuilt from the outline's own sources and read_routes
const compactRow = owner.outline.headings.items.find(row => row.file===owner.bind_payload.file && row.line===owner.bind_payload.line);
const row = outlineOccurrence(owner.outline, compactRow);
// G18: the list row carries the mark and one detail handle; actions and correspondence come from the section's detail
const listRow = owner.summary_before.sections.items.find(row=>row.id===owner.bind_payload.section_id);
const section = owner.sections_before.find(row=>row.id===owner.bind_payload.section_id);
test('the outline list row expands to the exact occurrence through the owner templates and never by guess',()=>{
 assert.deepEqual(Object.keys(compactRow).sort(),['file','heading_before','heading_line_end','kind','label','line','line_end','shared_occurrences','source_order','title']);
 assert.equal(row.basis.selection_identity,owner.outline.selected_source.selection_identity);assert.equal(row.basis.source_digest,owner.outline.sources[row.file].source_digest);
 assert.deepEqual(row.source_read.payload,{files:[row.file],line_start:row.line,line_end:row.line_end});assert.equal(row.source_read.http.query.file,row.file);assert.deepEqual(row.structure_read.http.query.files,[row.file]);
 assert.throws(()=>outlineOccurrence({...owner.outline,sources:{}},compactRow),/no source basis/);
 assert.deepEqual(Object.keys(listRow).sort(),['binding_status','collection','detail_read','id','job','kind','member_count','number','order','parent_id','precision','title']);
 assert.equal(listRow.precision,section.source.precision);assert.deepEqual(listRow.detail_read,section.detail_read);
});
test('actual source occurrence/action retain all original binding guards',async()=>{
 assert.equal(sourceOccurrence(row),row);
 assert.deepEqual(bindingSubmission(owner.project,section.clearing_action,row,section.id),{project:owner.project,...owner.bind_payload});
 const observed={file:row.file,selection_identity:row.basis.selection_identity,expected_source_digest:row.basis.source_digest};
 assert.equal(await inspectSourceOccurrence(row,owner.project,{read:async()=>observed}),observed);
 await assert.rejects(inspectSourceOccurrence(row,owner.project,{read:async()=>({...observed,expected_source_digest:'sha256:'+'0'.repeat(64)})}),/source changed/);
});
test('cross-owner and altered action handles refuse before effect',()=>{
 const altered=copy(row);altered.source_read.http.query.file='different.tex';assert.throws(()=>sourceOccurrence(altered),/exact source/);
 const action=copy(section.clearing_action);action.payload.project='other';assert.throws(()=>bindingSubmission(owner.project,action,row,section.id),/unobserved/);
 assert.throws(()=>bindingSubmission('other',section.clearing_action,row,section.id),/another project/);
 const read=copy(row.structure_read);read.http.query.project='other';assert.throws(()=>spineReadURL(read,owner.project),/different owner/);
});
test('only exact unique physical correspondence permits linked heading authority',()=>{
 const after=owner.sections_after,heading={file:row.file,line_start:row.line};
 assert.equal(boundPlanHeading(after,heading)?.id,section.id);
 assert.equal(boundPlanHeading(owner.sections_before,heading),null);
 assert.equal(boundPlanHeading(after,{...heading,file:row.file.split('/').at(-1)}),null);
 assert.equal(boundPlanHeading([...after,...after],heading),null);
 for(const precision of ['FILE_ONLY','INFERRED','AMBIGUOUS','UNRESOLVED']){
  const rows=copy(after);rows.find(x=>x.id===section.id).source.precision=precision;assert.equal(boundPlanHeading(rows,heading),null);
 }
});
test('displayed observation preserves raw basis and rejects mismatched selection',()=>{
 const value=structureObservation(owner.detail);
 assert.equal(value.selection_identity,owner.detail.selected_source.selection_identity);
 assert.equal(value.source_files.find(x=>x.file===row.file)?.source_digest,row.basis.source_digest);
 const altered=copy(owner.detail);altered.sections[0].source.basis[row.file].selection_identity='sha256:'+'0'.repeat(64);
 assert.throws(()=>structureObservation(altered),/exact byte observation/);
});
test('plan item save contains changed fields only and never a four-write ritual',()=>{
 const base={id:'one',title:'Independent reader title',job:'Purpose',notes:'Note',kind:'section',parent_id:''};
 assert.deepEqual(readerPlanItemOps(base,base),[]);
 assert.deepEqual(readerPlanItemOps(base,{...base,notes:'Revised'}),[{kind:'edit-notes',section:'one',notes:'Revised'}]);
});
test('spine reorder uses full exact membership and narrative edit preserves order',()=>{
 const full={revision:'sha256:'+'a'.repeat(64),spine:[{id:'a',narrative:'A'},{id:'b',narrative:'B'},{id:'c',narrative:'C'}]};
 assert.deepEqual(narrativeBeatOperation(full,'a','order',2),{kind:'reorder-spine',order:['b','c','a']});
 assert.deepEqual(narrativeBeatOperation(full,'b','narrative','New'),{kind:'set-narrative',node:'b',narrative:'New'});
 assert.equal(narrativeBeatOperation(full,'b','narrative','B'),null);
 assert.throws(()=>narrativeBeatOperation(full,'sec:b','order',0),/no longer/);
 assert.ok(ownerHumanTarget('/work/structure?project=book&view=summary&spine_limit=20&spine_offset=20'));
});
test('actual uncertain empty and stale passage records remain inspectable without asserting membership',()=>{
 for(const passage of Object.values(passages)){
  const view=passageProvenancePresentation(passage,'book');assert.equal(view.uncertain,true);assert.equal(view.links.length,1);
  assert.equal(view.links[0].read.id,'activity:journal:WA-selected');assert.equal(view.links[0].membership,false);
  assert.match(view.message,/could not be tied/);
 }
});
test('plan publication keeps retained/incomplete and saved failure envelope truthful',()=>{
 const receipt={owner:'reader-spine',status:'PARTIAL',complete:false,ledger_append_count:1};
 assert.equal(planPublicationDisposition({plan_publication:receipt}).acknowledged,false);
 assert.equal(savedActionPlanPublication({outcome:{plan_publication:receipt}}).publication,receipt);
 assert.equal(savedFailurePlanPublication({recovery:{plan_publication:receipt}}).publication,receipt);
 assert.throws(()=>planPublicationDisposition({plan_publication:{...receipt,complete:true}}),/could not be verified/);
 assert.throws(()=>planPublicationDisposition({plan_publication:null}),/could not be verified/);
});

test('reader-plan home reads compact summary then selected detail and keeps independent title visible',async()=>{
 const {installDOM,Node,findButton}=await import('./helpers/evidence_reader_harness.mjs');
 const {mountReaderPlan}=await import('../src/laplace/web/static_shared/workspace-spine.mjs');
 const dom=installDOM(),host=new Node('main'),calls=[],scopes=[];dom.body.append(host);
 try{
  const controller=await mountReaderPlan(host,{project:owner.project,request:async url=>{
   calls.push(url);const q=new URL(url,'http://local').searchParams;
   assert.equal(q.get('project'),owner.project);
   if(q.get('view')==='summary')return copy(owner.summary_after);
   if(q.get('view')==='detail')return copy(owner.detail);
   throw Error('Unexpected unbounded read '+url);
  },onScope:value=>scopes.push(value)});
  assert.equal(calls.length,2);assert.ok(!calls.some(url=>url.includes('view=full')));
  const selected=owner.detail.sections[0];assert.ok(host.textContent.includes(selected.title));
  assert.ok(findButton(host,'Change source link'));assert.equal(controller.capture().sectionId,selected.id);
  assert.equal(scopes.at(-1).structure_observation.selection_identity,owner.detail.selected_source.selection_identity);
  controller.destroy();assert.equal(dom.editor.value,'UNSAVED manuscript');
 }finally{dom.restore();}
});

test('local binding chooser inspects one actual occurrence before one guarded confirmation',async()=>{
 const {installDOM,Node,findButton}=await import('./helpers/evidence_reader_harness.mjs');
 const {chooseSourceBinding}=await import('../src/laplace/web/static_shared/workspace-spine.mjs');
 const dom=installDOM(),calls=[];let sourceReads=0,linked=0;
 const oldListener=Node.prototype.addEventListener;
 Node.prototype.addEventListener=function(name,fn){if(name==='close')this.onclose=fn;};
 try{
  const dialog=await chooseSourceBinding({project:owner.project,section,action:section.clearing_action,opener:dom.editor,
   request:async(url,payload)=>{calls.push({url,payload});if(payload){assert.equal(url,'/work/structure/change');return copy(owner.bind_result);}return copy(owner.outline);},
   readSource:async({project,file})=>{sourceReads++;assert.equal(project,owner.project);assert.equal(file,row.file);return {file,selection_identity:row.basis.selection_identity,expected_source_digest:row.basis.source_digest,content:row.heading_before+'\nBody.\n'};},
   onLinked:async()=>{linked++;}});
  const choice=dialog.all().find(node=>node.classList.contains('spine-heading-choice')&&node.textContent.includes(row.title));assert.ok(choice);
  await choice.click();assert.equal(sourceReads,1);assert.equal(calls.filter(call=>call.payload).length,0);
  await findButton(dialog,'Link this heading').click();assert.equal(linked,1);
  assert.deepEqual(calls.find(call=>call.payload).payload,{project:owner.project,...owner.bind_payload});
  assert.equal(dom.editor.value,'UNSAVED manuscript');assert.equal(document.activeElement,dom.editor);
 }finally{Node.prototype.addEventListener=oldListener;dom.restore();}
});

test('actual architecture prior is inspected as shared form guidance without inventing edit permission',async()=>{
 const {installDOM,Node,findButton}=await import('./helpers/evidence_reader_harness.mjs');
 const {renderArchitecturePrior,inspectArchitecturePrior}=await import('../src/laplace/web/static_shared/reader-state.mjs');
 const fixture=JSON.parse(await readFile(new URL('./fixtures/editor_spine/profile-inputs.json',import.meta.url),'utf8'));
 const dom=installDOM(),host=new Node('section');dom.body.append(host);let reads=0;
 const oldListener=Node.prototype.addEventListener;Node.prototype.addEventListener=function(name,fn){if(name==='close')this.onclose=fn;};
 try{
  renderArchitecturePrior(host,fixture.architecture_summary,{onInspect:value=>inspectArchitecturePrior({value,opener:dom.editor,read:async handle=>{reads++;assert.deepEqual(handle,fixture.architecture_summary.read_more);return fixture.architecture_exact;}})});
  assert.equal(reads,0);await findButton(host,'Inspect structural preferences').click();assert.equal(reads,1);
  const dialog=dom.dialogs()[0];assert.match(dialog.textContent,/Use an explicit explanatory sequence/);assert.match(dialog.textContent,/not scientific evidence/);
  assert.equal(findButton(dialog,/Save|Generate/),undefined);await findButton(dialog,'Close').click();assert.equal(document.activeElement,dom.editor);
 }finally{Node.prototype.addEventListener=oldListener;dom.restore();}
});

test('reader dialogs inherit the workspace scope and expose exact label names independent of options',async()=>{
 const {installDOM,Node,findButton}=await import('./helpers/evidence_reader_harness.mjs');
 const {editReaderPlanItem}=await import('../src/laplace/web/static_shared/workspace-spine.mjs');
 const data=JSON.parse(await readFile(new URL('./fixtures/editor_spine/reader-state.json',import.meta.url),'utf8'));
 const dom=installDOM(),workspace=new Node('main');workspace.className='workspace';dom.body.append(workspace);
 const oldListener=Node.prototype.addEventListener;Node.prototype.addEventListener=function(name,fn){if(name==='close')this.onclose=fn;};
 try{
  const dialog=await editReaderPlanItem({project:'book',section:data.full_spine.sections[0],request:async()=>data.full_spine,opener:dom.editor,storage:null});
  assert.equal(dialog.parentElement,workspace);
  for(const name of ['Title','Purpose of this plan item','Working notes','Level','Within']){
   const field=dialog.all().find(node=>node.attrs['aria-label']===name);assert.ok(field,name);assert.ok(field.id);assert.equal(field.parentElement.htmlFor,field.id);
  }
  const disclosure=dialog.all().find(node=>node.tag==='summary');assert.equal(disclosure.onclick,undefined,'native disclosure default is not intercepted');
  await findButton(dialog,'Close').click();
 }finally{Node.prototype.addEventListener=oldListener;dom.restore();}
});

test('contextual reader plan shares the ordinary renderer while exposing no mutation controls',async()=>{
 const {installDOM,Node,findButton}=await import('./helpers/evidence_reader_harness.mjs');
 const {mountReaderPlan}=await import('../src/laplace/web/static_shared/workspace-spine.mjs');
 const dom=installDOM(),host=new Node('section'),calls=[];dom.body.append(host);
 try{
  const controller=await mountReaderPlan(host,{project:owner.project,readOnly:true,request:async(url,payload)=>{
   assert.equal(payload,undefined);calls.push(url);return copy(new URL(url,'http://local').searchParams.get('view')==='summary'?owner.summary_after:owner.detail);
  }});
  assert.ok(host.textContent.includes(owner.detail.sections[0].title));assert.equal(calls.length,2);
  for(const label of ['Change source link','Link source heading','Move reader-plan item','Edit reader transition','Add paragraph plan','Use as narrative beat'])assert.equal(findButton(host,label),undefined,label);
  assert.equal(dom.editor.value,'UNSAVED manuscript');controller.destroy();
 }finally{dom.restore();}
});
