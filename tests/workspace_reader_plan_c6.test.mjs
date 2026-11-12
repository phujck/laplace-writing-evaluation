// C6: the reader plan's list control, relation map from the detail read alone, bounded subject
// reads at paragraph-action open, and the argument record header.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {installDOM,Node,findButton} from './helpers/evidence_reader_harness.mjs';
import {readerRelationTopology,mountReaderPlan} from '../src/laplace/web/static_shared/workspace-spine.mjs';
import {readerSubjectRead,readerSubjectAction} from '../src/laplace/web/static_shared/reader-state.mjs';
import {ownerHumanTarget} from '../src/laplace/web/static_shared/writing-owner-read.mjs';
const owner=JSON.parse(await readFile(new URL('./fixtures/editor_spine/owner-wire.json',import.meta.url),'utf8'));
const readerOwner=JSON.parse(await readFile(new URL('./fixtures/editor_spine/reader-state.json',import.meta.url),'utf8'));
const copy=value=>structuredClone(value);

test('the relation map is one typed array from the detail read: section, source heading, argument, evidence, work',()=>{
 const section={...copy(owner.detail.sections[0]),evidence:[{id:'result:r1',title:'Result one',node_id:owner.detail.sections[0].nodes[0].id}],work:[{id:'WORK-1',title:'Prepare'}]};
 const topology=readerRelationTopology(section,owner.detail,owner.project);
 assert.deepEqual(topology.edges.map(edge=>edge.kind),['bound-to','argues','supported-by','tracked-by']);
 assert.equal(topology.edges[2].source,'argument:'+section.nodes[0].id,'evidence hangs on the argument object it is bound to');
 assert.equal(topology.hints.rank['section:'+section.id],1);assert.ok(topology.nodes.every(node=>node.id.includes(':')));
 assert.deepEqual(readerRelationTopology({id:'bare',title:'Bare'},{},'p').edges,[]);
});

test('subject reads are exact owner coordinates that the owner-read parser admits, and the returned call is checked before use',()=>{
 const read=readerSubjectRead('book','first','paragraph','first-p1');
 assert.deepEqual(read.payload,{view:'detail',section_ids:['first'],projection:'guard',subject:'paragraph',paragraph_id:'first-p1'});
 const url='/work/structure?'+new URLSearchParams({project:'book',view:'detail',section_ids:'["first"]',projection:'guard',subject:'paragraph',paragraph_id:'first-p1'});
 assert.equal(ownerHumanTarget(url)?.kind,'structure');
 assert.equal(ownerHumanTarget('/work/structure?project=book&view=detail&section_ids=%5B%22first%22%5D&subject=create'),null,'a subject without the projection is refused');
 assert.equal(ownerHumanTarget('/work/structure?project=book&view=detail&section_ids=%5B%22first%22%5D&projection=everything'),null);
 assert.throws(()=>readerSubjectRead('book','first','paragraph'),/paragraph_id/);
 const value={schema_version:'laplace.project-structure-guard/1',project:'book',section_id:'first',subject:'paragraph',paragraph:{paragraph_id:'first-p1',edit_action:{operation:'structure_change',payload:{action:'upsert'}},remove_action:{operation:'structure_change',payload:{action:'remove'}}}};
 assert.equal(readerSubjectAction(value,'paragraph',{project:'book',sectionId:'first',paragraphId:'first-p1',kind:'remove'}).payload.action,'remove');
 assert.throws(()=>readerSubjectAction(value,'paragraph',{project:'book',sectionId:'first',paragraphId:'other'}),/different paragraph/);
 assert.throws(()=>readerSubjectAction({...value,subject:'create'},'paragraph',{project:'book',sectionId:'first',paragraphId:'first-p1'}),/different guard subject/);
});

test('the reader plan lists sections as declared controls, offers the relation map lazily and opens a paragraph removal on its bounded subject read',async()=>{
 const dom=installDOM(),host=new Node('main'),calls=[];dom.body.append(host);
 const oldListener=Node.prototype.addEventListener;Node.prototype.addEventListener=function(name,fn){if(name==='close')this.onclose=fn;};
 try{
  const detail=copy(readerOwner.detail);const section=detail.sections[0];const paragraph=section.paragraph_plan.paragraphs.items[0];
  const summary=copy(owner.summary_after);summary.sections.items[0].id=section.id;summary.sections.items[0].title=section.title;
  const controller=await mountReaderPlan(host,{project:'book',request:async url=>{calls.push(url);const q=new URL(url,'http://local').searchParams;
   if(q.get('view')==='summary')return summary;
   if(q.get('projection')==='guard'){assert.equal(q.get('subject'),'paragraph');assert.equal(q.get('paragraph_id'),paragraph.paragraph_id);
    return {schema_version:'laplace.project-structure-guard/1',project:'book',section_id:section.id,subject:'paragraph',paragraph:{paragraph_id:paragraph.paragraph_id,edit_action:paragraph.edit_action,remove_action:{...paragraph.remove_action,payload:{...paragraph.remove_action.payload,expected_narrative_revision:'sha256:'+'f'.repeat(64)}}}};}
   if(q.get('view')==='detail')return detail;throw Error('Unexpected read '+url);},onScope:()=>{},onConcept:()=>{},onEvidence:()=>{},onWork:()=>{}});
  const row=host.all().find(node=>node.attrs['data-control']==='reader-plan:item');assert.ok(row,'ordered plan rows are declared controls');assert.equal(row.attrs['data-control-owner'],'book::'+section.id);
  const toggle=host.all().find(node=>node.attrs['data-control']==='reader-plan:relation-map');assert.ok(toggle);
  const before=calls.length;await toggle.onclick();assert.equal(calls.length,before,'the relation map costs no read');
  const map=host.querySelector('.topology');assert.ok(map);assert.ok(map.textContent.includes('Argues'));
  const remove=host.all().find(node=>node.attrs['data-control']==='reader-plan:paragraph-action'&&node.textContent==='Remove paragraph plan');assert.ok(remove);
  await remove.onclick();
  const subjectRead=calls.find(url=>url.includes('projection=guard'));assert.ok(subjectRead,'the removal opened on a bounded subject read');
  const dialog=dom.dialogs().at(-1);assert.ok(dialog&&dialog.textContent.includes('Remove paragraph plan'));
  controller.destroy();
 }finally{Node.prototype.addEventListener=oldListener;dom.restore();}
});

test('the argument record header is an object header with kind, title and proof/formal chips',async()=>{
 const dom=installDOM();try{
  const {renderConceptRecord}=await import('../src/laplace/web/static_shared/concept-reader.mjs');
  const host=new Node('section');
  await renderConceptRecord(host,{node:{id:'res:one',kind:'result',label:'First result'},state:{mathematical_record:{proof:{status:'RECORDED'},verification:{status:'VERIFIED'}}}});
  const header=host.all().find(node=>node.attrs['data-control']==='argument:record');assert.ok(header);
  assert.ok(header.textContent.includes('First result'));assert.ok(header.textContent.includes('Proof recorded'));assert.ok(header.textContent.includes('Formal verified'));
  const chips=header.all().filter(node=>node.className.includes('state-chip'));assert.equal(chips.length,2);assert.equal(chips[0].attrs['data-tone'],'ok');
 }finally{dom.restore();}
});

// Sol C6-I (2026-10-14): one useful owner page first, exact as_of continuation per collection,
// truthful totals, and an off-page selection that stays exact and keeps its order context.
const guardFixture=JSON.parse(await readFile(new URL('./fixtures/editor_spine/guard-subjects.json',import.meta.url),'utf8'));
function pagedOwner(root,{cut='same-cut',nextCut=null}={}){
 // a 3-section plan served one section and one beat per page, as the owner continuation does:
 // next_read is the query plus one offset, so each continuation re-sends the other collection's first page
 const calls=[];
 const page=(so,bo,asOf)=>{const value=copy(root);value.as_of=asOf;
  value.sections={items:[root.sections.items[so]],offset:so,limit:1,total:root.sections.items.length,...(so+1<root.sections.items.length?{next_read:{operation:'structure',payload:{view:'summary',section_offset:so+1,section_limit:1,spine_offset:0,spine_limit:1,as_of:cut}}}:{})};
  value.spine={items:[{id:'beat-'+bo,term:'Unique narrative '+bo,ord:bo}],offset:bo,limit:1,total:2,...(bo<1?{next_read:{operation:'structure',payload:{view:'summary',section_offset:so,section_limit:1,spine_offset:1,spine_limit:1,as_of:cut}}}:{})};
  return value;};
 const request=async url=>{calls.push(url);const q=new URL(url,'http://local').searchParams;
  if(q.get('view')==='summary'){const continuation=q.has('as_of');return page(Number(q.get('section_offset')||0),Number(q.get('spine_offset')||0),continuation&&nextCut?nextCut:cut);}
  if(q.get('view')==='detail'){const id=JSON.parse(q.get('section_ids'))[0];const detail=copy(owner.detail);const row=root.sections.items.find(row=>row.id===id);
   detail.sections[0].id=id;detail.sections[0].title=row?.title||id;detail.sections[0].number=root.sections.items.indexOf(row)+1;return detail;}
  throw Error('Unexpected read '+url);};
 return {calls,request};
}
test('the reader plan opens on one 6+6 owner page, merges only the paged collection on continuation and counts the plan by the owner total',async()=>{
 const dom=installDOM(),host=new Node('main');dom.body.append(host);
 try{
  const root=copy(owner.summary_after);const {calls,request}=pagedOwner(root);
  const controller=await mountReaderPlan(host,{project:owner.project,request,onScope:()=>{}});
  const first=new URL(calls[0],'http://local').searchParams;
  assert.equal(first.get('section_limit'),'6');assert.equal(first.get('spine_limit'),'6');assert.equal(first.get('object_limit'),'1');assert.equal(first.get('gap_limit'),'1');
  assert.ok(host.textContent.includes('Section 1 of 3'),'the header counts the owner total, not the loaded rows');
  await findButton(host,'More narrative beats').onclick();
  assert.ok(host.textContent.includes('Unique narrative 1'));
  await findButton(host,'More plan items').onclick();
  assert.ok(host.textContent.includes('Unique narrative 1'),'a section continuation keeps the narrative beats already loaded');
  assert.equal(host.all().filter(node=>node.attrs['data-control']==='reader-plan:item').length,2,'two section rows loaded');
  assert.ok(calls.every(url=>!url.includes('section_limit=40')),'no 40-row request remains');
  assert.ok(calls.filter(url=>url.includes('as_of=same-cut')).length===2,'continuations carry the owner cut');
  controller.destroy();
 }finally{dom.restore();}
});
test('a continuation served from another cut is refused and the loaded plan stands',async()=>{
 const dom=installDOM(),host=new Node('main');dom.body.append(host);
 try{
  const root=copy(owner.summary_after);const {request}=pagedOwner(root,{nextCut:'later-cut'});
  const controller=await mountReaderPlan(host,{project:owner.project,request,onScope:()=>{}});
  await findButton(host,'More plan items').onclick();
  assert.ok(host.textContent.includes('The reader plan changed'),'the stale continuation is named');
  assert.equal(host.all().filter(node=>node.attrs['data-control']==='reader-plan:item').length,1,'the loaded page is retained unchanged');
  controller.destroy();
 }finally{dom.restore();}
});
test('a section selected beyond the loaded page is read exactly, keeps its order context and becomes the current row once its page loads',async()=>{
 const dom=installDOM(),host=new Node('main');dom.body.append(host);
 try{
  const root=copy(owner.summary_after);const last=root.sections.items.at(-1);const {calls,request}=pagedOwner(root);
  const controller=await mountReaderPlan(host,{project:owner.project,request,initial:{sectionId:last.id},onScope:()=>{}});
  assert.ok(calls.some(url=>url.includes('view=detail')&&url.includes(encodeURIComponent(JSON.stringify([last.id])))),'the selected section is read by its exact id');
  assert.ok(host.textContent.includes('Section 3 of 3'),'the detail header carries the owner number and total');
  const note=host.querySelector('.spine-offpage');assert.ok(note&&note.textContent.includes('Section 3 of 3')&&note.textContent.includes('beyond the loaded plan items'));
  assert.equal(host.all().find(node=>node.attrs['data-control']==='reader-plan:item'&&node.attrs['aria-current']==='true'),undefined,'no loaded row is wrongly marked current');
  await findButton(host,'More plan items').onclick();await findButton(host,'More plan items').onclick();
  assert.equal(host.querySelector('.spine-offpage'),null,'once loaded, the note goes');
  const current=host.all().find(node=>node.attrs['data-control']==='reader-plan:item'&&node.attrs['aria-current']==='true');assert.ok(current&&current.dataset.planId===last.id);
  assert.ok(host.textContent.includes('Section 3 of 3'));
  controller.destroy();
 }finally{dom.restore();}
});

// Sol guard-consumer (2026-10-14): a saved/nested/recovered projection:guard read opens as the
// exact owner subject it is, read-only, with no further read; a different owner, section,
// subject or paragraph refuses; Close returns focus to the opener.
test('each owner-generated guard subject opens read-only from its one response and a mismatched response refuses',async()=>{
 const dom=installDOM();
 try{
  const {loadReader}=await import('./helpers/evidence_reader_harness.mjs');const api=await loadReader();
  const {project,section_id:sid,paragraph_id:pid}=guardFixture;
  for(const subject of ['contract','paragraph','create','reorder']){
   const calls=[];const value=guardFixture[subject];
   const url='/work/structure?'+new URLSearchParams({project,view:'detail',section_ids:JSON.stringify([sid]),projection:'guard',subject,...(subject==='paragraph'?{paragraph_id:pid}:{})});
   assert.ok(ownerHumanTarget(url),'the saved guard link is an admitted owner read');
   const dialog=await api.openArtifact({project,ownerRead:{http:{method:'GET',url}},label:'Guard '+subject,request:async read=>{calls.push(read);if(new URL(read,'http://local').searchParams.get('projection')==='guard')return value;throw Error('Unexpected '+read);},opener:dom.editor});
   assert.deepEqual(calls,[url],subject+': exactly the saved read, no summary or detail read');
   const text=dialog.textContent;
   const action=subject==='contract'?value.reader_transition.edit_action:subject==='paragraph'?value.paragraph.edit_action:value[subject+'_action'];
   assert.ok(text.includes('Reader-plan guard · '+subject)&&text.includes(action.payload.expected_reader_basis.subject_revision)&&text.includes(action.payload.expected_plan_revision),subject+': exact owner basis rendered');
   assert.ok(text.includes('read-only')&&!text.includes('different owner'),subject+': read-only inspector, not a reader plan');
   assert.ok(dialog.all().some(node=>node.attrs['data-control']==='reader-plan:guard'));
   if(subject==='paragraph')assert.ok(text.includes(pid));
   assert.equal(dialog.all().filter(node=>node.attrs['data-control']==='reader-plan:item').length,0,'no reader plan is mounted');
   await findButton(dialog,'Close').onclick();assert.equal(document.activeElement,dom.editor,subject+': Close returns focus to the opener');
  }
  // repair H5 (2026-10-14): the two subjects C10 added render read-only from their exact returned
  // calls (section: link source, prepare work, review; structure: split, merge, review) through the
  // same qualified route, one read, no edit selected, no plain detail
  const displayOwner=JSON.parse(await readFile(new URL('./fixtures/editor_spine/display-owner.json',import.meta.url),'utf8'));
  for(const subject of ['section','structure']){
   const calls=[];const value=displayOwner[subject+'_subject'];const pid2=value.paragraph?.paragraph_id||null;
   const url='/work/structure?'+new URLSearchParams({project:'book',view:'detail',section_ids:JSON.stringify(['first']),projection:'guard',subject,...(pid2?{paragraph_id:pid2}:{})});
   assert.ok(ownerHumanTarget(url),subject+': admitted owner read');
   const dialog=await api.openArtifact({project:'book',ownerRead:{http:{method:'GET',url}},label:'Guard '+subject,request:async read=>{calls.push(read);if(new URL(read,'http://local').searchParams.get('projection')==='guard')return structuredClone(value);throw Error('Unexpected '+read);},opener:dom.editor});
   assert.deepEqual(calls,[url],subject+': exactly the saved read');
   const text=dialog.textContent;assert.ok(text.includes('Reader-plan guard · '+subject)&&text.includes('read-only'),subject+': read-only inspector');
   const labels=subject==='section'?['Link source heading','Prepare work','Create review work']:['Split planned unit (preview)','Combine planned units (preview)','Create review work'];
   for(const label of labels)assert.ok(text.includes(label),subject+': '+label+' rendered from the returned call');
   assert.ok(text.includes(value.section_calls?.clearing_action?.payload?.expected_revision||value.paragraph?.review_action?.payload?.expected_plan_revision||value.authority.plan_revision),subject+': exact guard facts');
   if(subject==='structure')assert.ok(text.includes(pid2));
   assert.ok(dialog.all().some(node=>node.attrs['data-control']==='reader-plan:guard'));assert.equal(dialog.all().filter(node=>node.attrs['data-control']==='reader-plan:item').length,0);
   await findButton(dialog,'Close').onclick();assert.equal(document.activeElement,dom.editor,subject+': focus returns to the opener');
  }
  // a section response served for a structure link refuses before anything renders
  {const calls=[];const url='/work/structure?'+new URLSearchParams({project:'book',view:'detail',section_ids:JSON.stringify(['first']),projection:'guard',subject:'structure',paragraph_id:'first-p1'});
   const dialog=await api.openArtifact({project:'book',ownerRead:{http:{method:'GET',url}},label:'Guard',request:async read=>{calls.push(read);return structuredClone(displayOwner.section_subject);},opener:dom.editor});
   assert.equal(calls.length,1);assert.ok(dialog.textContent.includes('different guard subject'));await findButton(dialog,'Close').onclick();}
  // wrong subject (a create response for a reorder link) and wrong section both refuse
  for(const [label,url,served] of [['subject','/work/structure?'+new URLSearchParams({project,view:'detail',section_ids:JSON.stringify([sid]),projection:'guard',subject:'reorder'}),guardFixture.create],
    ['section','/work/structure?'+new URLSearchParams({project,view:'detail',section_ids:JSON.stringify(['second']),projection:'guard',subject:'contract'}),guardFixture.contract]]){
   const calls=[];const dialog=await api.openArtifact({project,ownerRead:{http:{method:'GET',url}},label:'Guard',request:async read=>{calls.push(read);return served;},opener:dom.editor});
   assert.equal(calls.length,1,label+': the refusal costs no further read');assert.ok(dialog.textContent.includes('different guard subject'),label+': refused');
   await findButton(dialog,'Close').onclick();
  }
  api.destroy();
 }finally{dom.restore();}
});

// Sol proof-chips (2026-10-14): canonical owner states map explicitly; an absent or unreviewed
// proof is never green, a related receipt keeps its qualifier, an unknown state is neutral.
test('proof and formal chips follow the canonical owner vocabulary and never show a positive tone for an absent or unreviewed proof',async()=>{
 const dom=installDOM();try{
  const {renderConceptRecord,PROOF_STATUS_TONES,FORMAL_STATUS_TONES}=await import('../src/laplace/web/static_shared/concept-reader.mjs');
  const chipsOf=async(kind,proof,formal,reason)=>{const host=new Node('section');await renderConceptRecord(host,{node:{id:'res:one',kind,label:'Controlled result'},state:{mathematical_record:{proof:{status:proof},verification:{status:formal,...(reason?{reason}:{})}}}});
   const header=host.all().find(node=>node.attrs['data-control']==='argument:record');return header.all().filter(node=>node.className.includes('state-chip')).map(node=>({label:node.textContent,tone:node.attrs['data-tone'],title:node.title||''}));};
  const table={};for(const status of ['NOT_RECORDED','SOURCE_UNREVIEWED','AUTHORED_UNREVIEWED','RECORDED','UNPROVED','INCOMPLETE','SOMETHING_NEW'])table[status]=(await chipsOf('result',status,'NOT_CHECKED'))[0];
  assert.deepEqual(Object.fromEntries(Object.entries(table).map(([k,v])=>[k,v.tone])),{NOT_RECORDED:'attention',SOURCE_UNREVIEWED:'neutral',AUTHORED_UNREVIEWED:'neutral',RECORDED:'ok',UNPROVED:'attention',INCOMPLETE:'attention',SOMETHING_NEW:'neutral'});
  assert.equal(table.NOT_RECORDED.label,'Proof not recorded');
  assert.equal((await chipsOf('definition','NOT_RECORDED','NOT_CHECKED')).length,0,'a definition with the owner default carries no proof chip');
  const related=await chipsOf('result','SOURCE_UNREVIEWED','RELATED_FORMAL_RECEIPT','These checks share a result binding; no declaration is explicitly linked to this concept.');
  assert.equal(related[1].tone,'neutral');assert.ok(related[1].title.includes('share a result binding'),'the related receipt keeps its qualifier');
  for(const [formal,tone] of [['STALE','attention'],['UNAVAILABLE','attention'],['CHECKED_DECLARATION','ok'],['PARTIALLY_CHECKED','neutral'],['NOT_ESTABLISHED','neutral'],['NOT_OBSERVED','neutral'],['UNKNOWN_STATE','neutral']])assert.equal((await chipsOf('result','RECORDED',formal))[1].tone,tone,formal);
  assert.ok(!Object.values(PROOF_STATUS_TONES).includes(undefined)&&FORMAL_STATUS_TONES.NOT_CHECKED==='neutral');
 }finally{dom.restore();}
});

// Sol guard-selector-policy (2026-10-14): the qualified human parser admits a guard link only
// with exactly one canonical section_ids entry; an alternative selector is not an owner read,
// so nothing is requested and no inspector opens for it; unprojected detail links keep every selector.
test('a guard link is admitted only with one canonical section_ids entry; alternative selectors are refused before any read',async()=>{
 const dom=installDOM();
 try{
  const {loadReader}=await import('./helpers/evidence_reader_harness.mjs');const api=await loadReader();
  const base={project:'book',view:'detail',projection:'guard'};
  const alternatives={node_ids:{node_ids:'["concept:wide-member-00"]'},node_id:{node_id:'concept:wide-member-00'},files:{files:'["chapters/chapter-01.tex"]'},two:{section_ids:'["first","second"]'},mixed:{section_ids:'["first"]',node_ids:'["x"]'},alias:{sections:'["first"]'},none:{},
   // presence, not truthiness (Sol guard-selector-policy-empty-presence): an empty alternative key beside the canonical id refuses too
   empty_files:{section_ids:'["first"]',files:'[]'},empty_node_ids:{section_ids:'["first"]',node_ids:'[]'},empty_node_id:{section_ids:'["first"]',node_id:''},empty_sections:{section_ids:'["first"]',sections:'[]'}};
  for(const [name,selector] of Object.entries(alternatives))for(const subject of [{},{subject:'contract'},{subject:'create'},{subject:'reorder'},{subject:'paragraph',paragraph_id:'first-p1'}]){
   const url='/work/structure?'+new URLSearchParams({...base,...selector,...subject});
   assert.equal(ownerHumanTarget(url),null,name+' '+JSON.stringify(subject)+': not an admitted owner read');
   const calls=[];
   await assert.rejects(api.openArtifact({project:'book',ownerRead:{http:{method:'GET',url}},label:'Guard',request:async read=>{calls.push(read);return guardFixture.contract;},opener:dom.editor}),/coordinates are invalid/);
   assert.deepEqual(calls,[],name+': no read is issued for a refused guard link');
  }
  // the same selectors remain admitted for ordinary unprojected detail, and the canonical guard stays admitted
  for(const selector of [{node_ids:'["concept:wide-member-00"]'},{files:'["chapters/chapter-01.tex"]'},{section_ids:'["first","second"]'}]){
   const admitted=ownerHumanTarget('/work/structure?'+new URLSearchParams({project:'book',view:'detail',...selector}));assert.ok(admitted&&admitted.kind==='structure'&&admitted.view==='detail');
  }
  const canonical=ownerHumanTarget('/work/structure?'+new URLSearchParams({...base,section_ids:'["first"]',subject:'create'}));
  assert.deepEqual(canonical.sectionIds,['first']);assert.equal(canonical.read_handle.payload.projection,'guard');
  api.destroy();
 }finally{dom.restore();}
});
