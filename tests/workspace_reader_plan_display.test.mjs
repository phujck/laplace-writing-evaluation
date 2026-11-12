// ACTUAL-C6-DETAIL-BYTES (2026-10-14): the Reader plan reads one section as its bounded display,
// expands a paragraph row in place through its own display read, acquires every edit/remove/
// review/structure/link/prepare call on a subject read when the door opens, and the plan-level
// editors read the plan guard instead of the full structure.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {installDOM,Node,findButton} from './helpers/evidence_reader_harness.mjs';
import {mountReaderPlan,planGuardHandle,editReaderPlanItem} from '../src/laplace/web/static_shared/workspace-spine.mjs';
import {readerSubjectRead,readerSubjectAction,readerDisplayHandle,readerDoor} from '../src/laplace/web/static_shared/reader-state.mjs';
import {ownerHumanTarget} from '../src/laplace/web/static_shared/writing-owner-read.mjs';
const fixture=JSON.parse(await readFile(new URL('./fixtures/editor_spine/display-owner.json',import.meta.url),'utf8'));
const copy=value=>structuredClone(value);
const params=url=>new URL(url,'http://local').searchParams;
function displayOwner(){
 const calls=[];
 const request=async(url,payload)=>{calls.push({url,payload});const q=params(url);
  if(q.get('view')==='summary')return copy(fixture.summary);
  if(q.get('view')==='plan')return copy(fixture.plan);
  if(q.get('projection')==='display'&&q.has('spine_offset'))return copy(fixture.spine_pages.find(page=>page.spine_page.offset===Number(q.get('spine_offset'))));
  if(q.get('view')==='detail'&&q.has('node_id'))return copy(fixture.beat_detail);
  if(q.get('projection')==='display')return copy(q.has('paragraph_id')?fixture.paragraph_display:fixture.display);
  if(q.get('projection')==='guard'){const subject=q.get('subject');
   if(subject==='section')return copy(fixture.section_subject);if(subject==='structure')return copy(fixture.structure_subject);
   if(subject==='paragraph'&&q.get('edit_choices')==='true')return copy(fixture.paragraph_choices);
   if(subject==='contract'&&q.get('edit_choices')==='true')return copy(fixture.contract_values);}
  throw Error('Unexpected read '+url);};
 return {calls,request};
}

test('the display handle and the new subjects are admitted owner coordinates; doors are read from display rows only',()=>{
 const display=readerDisplayHandle('book','first',{paragraph_id:'first-p1'});
 assert.deepEqual(display.payload,{view:'detail',section_ids:['first'],paragraph_id:'first-p1',projection:'display'});
 assert.equal(ownerHumanTarget('/work/structure?'+new URLSearchParams({project:'book',...display.payload,section_ids:'["first"]'}))?.kind,'structure');
 assert.equal(ownerHumanTarget('/work/structure?project=book&view=detail&section_ids=%5B%22first%22%5D&projection=display&subject=contract'),null,'a display takes no subject');
 assert.equal(ownerHumanTarget('/work/structure?project=book&view=plan')?.kind,'structure','the plan guard is an admitted read');
 for(const subject of ['section','structure']){const read=readerSubjectRead('book','first',subject,subject==='structure'?'first-p1':null);assert.equal(ownerHumanTarget('/work/structure?'+new URLSearchParams({project:'book',...read.payload,section_ids:'["first"]'}))?.kind,'structure');}
 assert.throws(()=>readerSubjectRead('book','first','structure'),/paragraph_id/);
 assert.equal(readerSubjectRead('book','first','contract',null,{choices:true}).payload.edit_choices,true);
 assert.equal(readerSubjectRead('book','first','reorder',null,{choices:true}).payload.edit_choices,undefined,'reorder carries no descriptors');
 const section=fixture.section_subject;
 assert.equal(readerSubjectAction(section,'section',{project:'book',sectionId:'first',kind:'link_source'}),section.section_calls.clearing_action);
 assert.equal(readerSubjectAction(section,'section',{project:'book',sectionId:'first',kind:'review'}),section.section_calls.review_action);
 const row=fixture.display.sections[0].paragraph_plan.paragraphs.items[0];
 assert.equal(readerSubjectAction(fixture.structure_subject,'structure',{project:'book',sectionId:'first',paragraphId:row.paragraph_id,kind:'split'}),fixture.structure_subject.paragraph.restructure_actions.split);
 assert.ok(readerDoor(row,'edit')&&readerDoor(row,'split')&&!readerDoor({edit_action:{}},'edit'),'a plain detail row has calls, not doors');
 assert.deepEqual(planGuardHandle({operation:'structure',payload:{view:'full'}}).payload,{view:'plan'});
 assert.deepEqual(planGuardHandle(null).payload,{view:'plan'});
 assert.deepEqual(planGuardHandle({operation:'structure',payload:{view:'summary'}}).payload,{view:'summary'},'a handle that is not the full read stands');
});

test('selecting a section reads its display, never the plain detail; a row expands in place through its own display read',async()=>{
 const dom=installDOM(),host=new Node('main');dom.body.append(host);
 try{
  const {calls,request}=displayOwner();
  const controller=await mountReaderPlan(host,{project:'book',request,onScope:()=>{},onConcept:()=>{},onEvidence:()=>{},onWork:()=>{},onPrepareWork:async()=>{}});
  const detailReads=calls.filter(c=>params(c.url).get('view')==='detail');
  assert.ok(detailReads.length>=1&&detailReads.every(c=>params(c.url).get('projection')==='display'),'every section read is the display');
  const cards=host.querySelectorAll('.reader-paragraph');assert.equal(cards.length,6,'one display page of six rows');
  assert.ok(cards[0].textContent.includes('Also authored: how to explain it, limits and qualifications'),'the row names the fields it did not carry');
  const expand=cards[0].all().find(n=>n.attrs['data-control']==='reader-plan:paragraph-expand');assert.ok(expand);
  const before=calls.length;await expand.onclick();
  const last=params(calls.at(-1).url);assert.equal(calls.length,before+1);assert.equal(last.get('projection'),'display');assert.equal(last.get('paragraph_id'),fixture.display.sections[0].paragraph_plan.paragraphs.items[0].paragraph_id);
  const replaced=host.querySelectorAll('.reader-paragraph')[0];
  assert.ok(replaced.textContent.includes('Explanation 0:')&&!replaced.textContent.includes('Also authored'),'the whole row replaced its card in place');
  assert.equal(host.querySelectorAll('.reader-paragraph').length,6,'the other rows stand');
  assert.ok(findButton(host,'Next paragraph plans'),'the owner continuation is offered');
  assert.ok(findButton(host,'Link source heading')&&findButton(host,'Prepare work'),'section doors render without their calls');
  controller.destroy();
 }finally{dom.restore();}
});

test('a display door acquires its exact call on the bounded subject read when it opens: edit, link source, split, review',async()=>{
 const dom=installDOM(),host=new Node('main'),reviewed=[],prepared=[];dom.body.append(host);
 const oldListener=Node.prototype.addEventListener;Node.prototype.addEventListener=function(name,fn){if(name==='close')this.onclose=fn;};
 try{
  const {calls,request}=displayOwner();
  const controller=await mountReaderPlan(host,{project:'book',request,onScope:()=>{},onConcept:()=>{},onEvidence:()=>{},onWork:()=>{},onReview:async(action,subject)=>reviewed.push([action,subject]),onPrepareWork:async(action,section)=>prepared.push([action,section])});
  const card=host.querySelectorAll('.reader-paragraph')[0];
  // edit: one guard read with edit_choices, the dialog opens on the owner's call with its descriptors
  let before=calls.length;await findButton(card,'Edit paragraph plan').onclick();
  const editRead=params(calls[before].url);assert.equal(editRead.get('projection'),'guard');assert.equal(editRead.get('subject'),'paragraph');assert.equal(editRead.get('edit_choices'),'true');
  assert.ok(dom.dialogs().at(-1)?.textContent.includes('Paragraph plan'),'the editor opened');
  assert.equal(calls.length-before,1,'repair H1: a fresh editor open is exactly ONE owner read (the descriptors travel on it; no second choices read)');
  assert.ok(calls.slice(before).every(c=>!params(c.url).get('view')||params(c.url).get('projection')),'no plain detail was read to open the editor');
  dom.dialogs().at(-1).close();
  // review on the row: the structure subject
  before=calls.length;await findButton(card,'Create paragraph review work').onclick();
  assert.equal(params(calls[before].url).get('subject'),'structure');
  assert.deepEqual(reviewed.at(-1)[0].payload,fixture.structure_subject.paragraph.review_action.payload);
  // prepare work: the section subject
  before=calls.length;await findButton(host,'Prepare work').onclick();
  assert.equal(params(calls[before].url).get('subject'),'section');assert.deepEqual(prepared.at(-1)[0],fixture.section_subject.section_calls.prepare_action);
  // review on the transition: the section subject
  before=calls.length;await findButton(host,'Create review work').onclick();
  assert.equal(params(calls[before].url).get('subject'),'section');assert.deepEqual(reviewed.at(-1)[0].payload,fixture.section_subject.section_calls.review_action.payload);
  controller.destroy();
 }finally{Node.prototype.addEventListener=oldListener;dom.restore();}
});

test('a retained draft opens on its original basis and reads the fresh guard once as its explicit stale inspection',async()=>{
 const dom=installDOM(),host=new Node('main');dom.body.append(host);
 const oldListener=Node.prototype.addEventListener;Node.prototype.addEventListener=function(name,fn){if(name==='close')this.onclose=fn;};
 try{
  const {calls,request}=displayOwner();const row=fixture.display.sections[0].paragraph_plan.paragraphs.items[0];
  const held=structuredClone(fixture.paragraph_choices.paragraph.edit_action);held.payload.expected_narrative_revision='sha256:'+'1'.repeat(64);
  const identity=JSON.stringify(['paragraph_plan','first',row.paragraph_id]);
  const store=new Map([['laplace:reader-state-draft:book:'+identity,JSON.stringify({project:'book',identity,action:held,values:{proposition:'kept draft text'}})]]);
  const storage={getItem:k=>store.get(k)??null,setItem:(k,v)=>store.set(k,v),removeItem:k=>store.delete(k)};
  const oldStorage=globalThis.sessionStorage;globalThis.sessionStorage=storage;
  try{
   const controller=await mountReaderPlan(host,{project:'book',request,onScope:()=>{},onConcept:()=>{},onEvidence:()=>{},onWork:()=>{}});
   const before=calls.length;await findButton(host.querySelectorAll('.reader-paragraph')[0],'Edit paragraph plan').onclick();
   const reads=calls.slice(before).map(c=>params(c.url));
   assert.equal(reads.length,2,'the fresh action (one read) plus the explicit stale inspection of the retained draft (one read), nothing else');
   assert.ok(reads.every(q=>q.get('projection')==='guard'&&q.get('edit_choices')==='true'));
   const dialog=dom.dialogs().at(-1);assert.ok(dialog.textContent.includes('retained'),'the draft and its original basis are retained');
   assert.ok(dialog.all().some(n=>n.value==='kept draft text'),'the retained text is shown');
   dialog.close();controller.destroy();
  }finally{globalThis.sessionStorage=oldStorage;}
 }finally{Node.prototype.addEventListener=oldListener;dom.restore();}
});

test('the plan-item editor reads the plan guard, not the full structure, and sends its revision',async()=>{
 const dom=installDOM();const oldListener=Node.prototype.addEventListener;Node.prototype.addEventListener=function(name,fn){if(name==='close')this.onclose=fn;};
 try{
  const {calls,request}=displayOwner();
  const dialog=await editReaderPlanItem({project:'book',section:{id:'first'},fullGuardRead:{operation:'structure',payload:{view:'full'}},request,storage:{getItem:()=>null,setItem(){}}});
  assert.equal(calls.length,1);assert.equal(params(calls[0].url).get('view'),'plan');
  assert.ok(dialog.textContent.includes('Edit reader-plan item'));
 }finally{Node.prototype.addEventListener=oldListener;dom.restore();}
});

// repair2 R2 (2026-10-14): a fresh editor opens on every existing authored value from the ONE exact owner
// read; untouched sends nothing, an edit sends only that field, a clear of an existing field is a change
test('the fresh paragraph editor shows the exact authored values; untouched sends nothing, an edit sends one field, a clear is a change',async()=>{
 const dom=installDOM(),host=new Node('main');dom.body.append(host);
 const oldListener=Node.prototype.addEventListener;Node.prototype.addEventListener=function(name,fn){if(name==='close')this.onclose=fn;};
 try{
  const {calls,request}=displayOwner();const posts=[];
  const wrapped=async(url,payload)=>{if(payload){posts.push(payload);throw Error('stop after capture');}return request(url);};
  const controller=await mountReaderPlan(host,{project:'book',request:wrapped,onScope:()=>{},onConcept:()=>{},onEvidence:()=>{},onWork:()=>{}});
  const open=async()=>{const before=calls.length;await findButton(host.querySelectorAll('.reader-paragraph')[0],'Edit paragraph plan').onclick();assert.equal(calls.length-before,1,'one owner read');return dom.dialogs().at(-1);};
  const values=fixture.paragraph_choices.paragraph.edit_action.values;
  let dialog=await open();const field=name=>dialog.all().find(n=>n.name===name);
  for(const [name,value] of Object.entries(values)){if(typeof value==='string')assert.equal(field(name)?.value,value,name+' opens on its exact authored value');}
  assert.ok(values.proposition.length>200&&field('proposition').value===values.proposition,'the long proposition is whole, not the clipped display text');
  const form=dialog.all().find(n=>n.tag==='form');
  await form.onsubmit({preventDefault(){}});assert.equal(posts.length,0,'untouched: nothing is sent');assert.ok(dialog.textContent.includes('No authored-plan changes.'));
  field('explanation').value='A new explanation.';await form.onsubmit({preventDefault(){}});
  assert.deepEqual(posts.at(-1).changes,{explanation:'A new explanation.'},'an edit sends only that field');
  assert.equal(posts.at(-1).expected_narrative_revision,fixture.paragraph_choices.paragraph.edit_action.payload.expected_narrative_revision,'the exact guard travels');
  dialog.close();
  globalThis.sessionStorage?.clear?.();
  dialog=await open();const f2=name=>dialog.all().find(n=>n.name===name);
  f2('proposition').value='';await dialog.all().find(n=>n.tag==='form').onsubmit({preventDefault(){}});
  assert.ok(Object.hasOwn(posts.at(-1).changes,'proposition')&&posts.at(-1).changes.proposition==='','clearing an existing field is sent as a change');
  dialog.close();controller.destroy();
 }finally{Node.prototype.addEventListener=oldListener;dom.restore();}
});

// repair3 R2 (2026-10-14): every shortened text has a read-only full continuation through the owner's own
// handle: a clipped-only row (authored == []) through paragraphs.row_read + its paragraph_id, the reader
// transition through its values_read. Exact owner/section/revision admission; no write; drafts untouched.
const snapshot=store=>JSON.stringify([...store.entries()].sort());
const draftStore=()=>{const identity=JSON.stringify(['section_contract','first']);const store=new Map([['laplace:reader-state-draft:book:'+identity,JSON.stringify({project:'book',identity,action:{payload:{expected_contract_revision:'sha256:'+'2'.repeat(64)}},values:{entry_state:'kept draft text'}})]]);
 return {store,storage:{getItem:k=>store.get(k)??null,setItem:(k,v)=>store.set(k,v),removeItem:k=>store.delete(k)}};};
test('a shortened reader transition reads its full authored text in place through values_read, read only, keeping drafts and refusing another cut',async()=>{
 const full=fixture.contract_values.reader_transition.edit_action.values,shown=fixture.display.sections[0].reader_transition;
 assert.deepEqual(shown.clipped,['entry_state']);assert.notEqual(shown.fields.entry_state,full.entry_state);
 for(const variant of ['exact','other-revision','other-section','other-project']){
  const dom=installDOM(),host=new Node('main');dom.body.append(host);const {store,storage}=draftStore(),oldStorage=globalThis.sessionStorage;globalThis.sessionStorage=storage;
  try{
   const {calls,request:base}=displayOwner();
   const request=async(url,payload)=>{const value=await base(url,payload);const q=params(url);if(q.get('subject')!=='contract')return value;
    if(variant==='other-revision')value.reader_transition.revision='sha256:'+'9'.repeat(64);
    if(variant==='other-section'){value.section_id='second';value.reader_transition.section_id='second';}
    if(variant==='other-project')value.project='other';return value;};
   const controller=await mountReaderPlan(host,{project:'book',request,onScope:()=>{},onConcept:()=>{},onEvidence:()=>{},onWork:()=>{}});
   const block=host.querySelector('.reader-state');assert.ok(block.textContent.includes('Shortened here: what the reader brings.'));
   const door=block.all().find(n=>n.attrs['data-control']==='reader-plan:transition-expand');assert.ok(door&&door.tag==='button'&&door.textContent==='Read full reader transition','a real button: keyboard and touch reach it');
   const drafts=snapshot(store),before=calls.length;await door.onclick();
   const reads=calls.slice(before);assert.equal(reads.length,1,variant+': one owner read');assert.equal(reads[0].payload,undefined,'a read, never a write');
   const q=params(reads[0].url);assert.deepEqual([q.get('project'),q.get('section_ids'),q.get('subject'),q.get('projection'),q.get('edit_choices')],['book','["first"]','contract','guard','true'],'exactly the owner values_read');
   assert.equal(snapshot(store),drafts,variant+': the retained draft and its basis are untouched');assert.equal(dom.dialogs?.().length||0,0,'no editor opened');
   if(variant==='exact'){
    assert.ok(block.textContent.includes(full.entry_state),'the exact full authored text');assert.ok(!block.textContent.includes(shown.fields.entry_state),'the shortened text is replaced');
    assert.ok(block.textContent.includes('Full authored text (read only).'));assert.ok(!block.all().some(n=>n.attrs['data-control']==='reader-plan:transition-expand'),'the door is spent');
    assert.ok(block.textContent.includes('Authored dependencies'),'dependency text joins its disclosure');
    assert.ok(!block.all().some(n=>['input','textarea','select'].includes(n.tag)),'nothing editable');
   }else{
    assert.ok(host.textContent.includes(variant==='other-revision'?'The reader transition changed since this page was read':'The reader transition is no longer present'),variant+': refused in words');
    assert.ok(!block.textContent.includes(full.entry_state),variant+': nothing painted');
   }
   controller.destroy();
  }finally{globalThis.sessionStorage=oldStorage;dom.restore();}
 }
 // a values_read that is not this section's contract subject is refused without a read
 const dom=installDOM(),host=new Node('main');dom.body.append(host);
 try{const {calls,request:base}=displayOwner();
  const request=async(url,payload)=>{const value=await base(url,payload);if(params(url).get('projection')==='display'&&!params(url).has('paragraph_id'))value.sections[0].reader_transition.values_read.payload.section_ids=['second'];return value;};
  const controller=await mountReaderPlan(host,{project:'book',request,onScope:()=>{},onConcept:()=>{},onEvidence:()=>{},onWork:()=>{}});
  const before=calls.length;await host.all().find(n=>n.attrs['data-control']==='reader-plan:transition-expand').onclick();
  assert.equal(calls.length,before,'no read');assert.ok(host.textContent.includes('offers no full read for this section'));controller.destroy();
 }finally{dom.restore();}
});
test('clipped-only proposition and function rows (authored == []) open their exact whole text through row_read, read only, refusing a newer plan',async()=>{
 const owner=fixture.clipped_only,rows=owner.display.sections[0].paragraph_plan.paragraphs.items;
 assert.deepEqual(rows.map(r=>[r.authored,r.clipped]),[[[],['proposition']],[[],['function']]],'owner rows: clipped, nothing else authored');
 for(const variant of ['exact','newer-plan']){
  const dom=installDOM(),host=new Node('main');dom.body.append(host);const {store,storage}=draftStore(),oldStorage=globalThis.sessionStorage;globalThis.sessionStorage=storage;
  try{
   const calls=[];const request=async(url,payload)=>{calls.push({url,payload});const q=params(url);
    if(q.get('view')==='summary')return copy(fixture.summary);if(q.get('view')==='plan')return copy(fixture.plan);
    if(q.get('projection')==='display'&&!q.has('paragraph_id'))return copy(owner.display);
    if(q.get('projection')==='display'){const whole=copy(owner.whole[q.get('paragraph_id')]);if(variant==='newer-plan')whole.sections[0].paragraph_plan.revision='sha256:'+'8'.repeat(64);return whole;}
    throw Error('Unexpected read '+url);};
   const controller=await mountReaderPlan(host,{project:'book',request,onScope:()=>{},onConcept:()=>{},onEvidence:()=>{},onWork:()=>{}});
   for(const [index,name,label] of [[0,'proposition','point to establish'],[1,'function','what this step does']]){
    // M5 Reader usability: one planned unit is open at a time; select this one first (its compact row's control)
    const row=()=>host.querySelectorAll('.reader-paragraph').find(c=>c.dataset.paragraphId===rows[index].paragraph_id);
    if(row().dataset.focused!=='true')await row().all().find(n=>n.attrs['data-control']==='reader-plan:unit-select').onclick();
    const card=row();assert.equal(card.dataset.focused,'true');
    assert.ok(card.textContent.includes('Shortened here: '+label+'.'),name+': the card says its text is shortened');
    const door=card.all().find(n=>n.attrs['data-control']==='reader-plan:paragraph-expand');assert.ok(door&&door.tag==='button',name+': a whole-text door although authored is empty');
    const drafts=snapshot(store),before=calls.length;await door.onclick();
    const reads=calls.slice(before);assert.equal(reads.length,1);assert.equal(reads[0].payload,undefined,'a read, never a write');
    const q=params(reads[0].url);assert.deepEqual([q.get('project'),q.get('section_ids'),q.get('projection'),q.get('paragraph_id')],['book','["first"]','display',rows[index].paragraph_id],'the owner row_read with only the paragraph_id put in');
    assert.equal(snapshot(store),drafts,'drafts untouched');
    const fullText=owner.whole[rows[index].paragraph_id].sections[0].paragraph_plan.paragraphs.items[0][name];
    const now=host.querySelectorAll('.reader-paragraph').find(c=>c.dataset.paragraphId===rows[index].paragraph_id);
    if(variant==='exact'){assert.notEqual(fullText,rows[index][name]);assert.ok(now.textContent.includes(fullText),name+': the exact whole text');assert.ok(!now.textContent.includes('Shortened here'));}
    else{assert.ok(host.textContent.includes('The paragraph plan changed since this page was read'));assert.ok(!now.textContent.includes(fullText),'a newer plan is not painted into this page');}
   }
   controller.destroy();
  }finally{globalThis.sessionStorage=oldStorage;dom.restore();}
 }
});

// release repair (ACTUAL-C1011-DISPLAY-BYTES, 2026-10-14): the section page carries the beat count and one
// read; the beats load when opened, a compact owner page at a time, admitted for this project, section
// and spine revision; member rows that are beats offer no second "Use as narrative beat".
test('narrative beats are read lazily in owner pages with an exact continuation; beat members are not offered again',async()=>{
 const shown=fixture.display;assert.equal(shown.spine,undefined,'the page lists no beats');assert.equal(shown.spine_page.total,14);
 for(const variant of ['exact','changed-spine','other-section','changed-plan-first','changed-plan-next']){
  const dom=installDOM(),host=new Node('main');dom.body.append(host);
  try{
   const {calls,request:base}=displayOwner();
   const request=async(url,payload)=>{const value=await base(url,payload);if(!params(url).has('spine_offset'))return value;
    if(variant==='changed-spine')value.structure_observation.spine_revision='sha256:'+'7'.repeat(64);if(variant==='other-section')value.section_id='second';
    // RELEASE-SPINE-PLAN-CUT: the section's membership changed (plan revision) while the spine revision stayed the same
    if(variant==='changed-plan-first'||variant==='changed-plan-next'&&params(url).get('spine_offset')==='12'){assert.equal(value.structure_observation.spine_revision,fixture.display.structure_observation.spine_revision);value.structure_observation.plan_revision='sha256:'+'6'.repeat(64);}
    return value;};
   const controller=await mountReaderPlan(host,{project:'book',request,onScope:()=>{},onConcept:()=>{},onEvidence:()=>{},onWork:()=>{}});
   assert.ok(!calls.some(c=>params(c.url).has('spine_offset')),'no beat read before the person opens them');
   assert.ok(!findButton(host,'Use as narrative beat'),'the member rows on this page are beats already');
   const toggle=host.all().find(n=>n.tag==='button'&&n.textContent==='Narrative beats (14)');assert.ok(toggle,'the exact count is on the page');
   let before=calls.length;await toggle.onclick();
   assert.deepEqual(calls.slice(before).map(c=>params(c.url).get('spine_offset')),['0'],'one compact page read');
   // M5 Reader usability: a beat without a term shows its id readable; the exact id stays as the control's title
   const beatButtons=()=>host.querySelector('.spine-beats').all().filter(n=>n.tag==='button'&&/^wide member /.test(n.textContent));
   if(!['exact','changed-plan-next'].includes(variant)){assert.ok(host.textContent.includes(variant==='changed-spine'?'The narrative spine changed since this page was read':variant==='changed-plan-first'?'This section\'s beats changed since this page was read':'These narrative beats belong to another reader-plan item'));assert.equal(beatButtons().length,0,'nothing painted');controller.destroy();continue;}
   assert.equal(beatButtons().length,12);
   const more=findButton(host,'More narrative beats (2 more)');assert.ok(more);before=calls.length;await more.onclick();
   if(variant==='changed-plan-next'){
    assert.deepEqual(calls.slice(before).map(c=>params(c.url).get('spine_offset')),['12'],'one continuation read');assert.ok(calls.slice(before).every(c=>c.payload===undefined),'no write');
    assert.ok(host.textContent.includes('This section\'s beats changed since this page was read. Refresh the reader plan.'),'refused in words');
    assert.deepEqual(beatButtons().map(n=>n.textContent),Array.from({length:12},(_,i)=>'wide member '+String(i).padStart(2,'0')),'the rows already shown stay; nothing from the changed page is appended');
    assert.ok(findButton(host,'More narrative beats (2 more)'),'the continuation stays for an explicit refresh');
    controller.destroy();continue;}
   assert.deepEqual(calls.slice(before).map(c=>params(c.url).get('spine_offset')),['12'],'the owner continuation');
   assert.deepEqual(beatButtons().map(n=>n.textContent),Array.from({length:14},(_,i)=>'wide member '+String(i).padStart(2,'0')),'every beat, in owner order');
   assert.deepEqual(beatButtons().map(n=>n.title),Array.from({length:14},(_,i)=>'concept:wide-member-'+String(i).padStart(2,'0')),'the exact ids stay inspectable');
   assert.ok(!findButton(host,'More narrative beats (2 more)'),'the continuation is spent');
   before=calls.length;await beatButtons()[0].onclick();const q=params(calls[before].url);
   assert.deepEqual([q.get('view'),q.get('node_id')],['detail','concept:wide-member-00'],'a beat opens on the owner row_read');
   assert.ok(host.textContent.includes('Beat 0: the reader meets this step of the argument.'),'its whole narrative is on the beat read');
   controller.destroy();
  }finally{dom.restore();}
 }
});

test('a whole-unit read lands the keyboard on the connected replacement unit head (M5-I2); a late answer to a removed card paints and focuses nothing',async()=>{
 const dom=installDOM(),host=new Node('main');dom.body.append(host);
 try{
  let gate=null;
  const {calls,request}=displayOwner();
  const gated=async(url,payload)=>{const q=params(url);if(q.get('projection')==='display'&&q.has('paragraph_id')&&gate)await gate;return request(url,payload);};
  const controller=await mountReaderPlan(host,{project:'book',request:gated,onScope:()=>{},onConcept:()=>{},onEvidence:()=>{},onWork:()=>{},onPrepareWork:async()=>{}});
  const cards=host.querySelectorAll('.reader-paragraph'),paragraphId=cards[0].dataset.paragraphId;
  const expand=cards[0].all().find(n=>n.attrs['data-control']==='reader-plan:paragraph-expand');
  await expand.click();   // the harness click puts the keyboard on the door, as a person's does
  const replaced=host.querySelectorAll('.reader-paragraph')[0],head=replaced.querySelector('.reader-unit-head');
  assert.ok(replaced!==cards[0]&&replaced.textContent.includes('Explanation 0:'),'the whole row replaced its card in place');
  assert.equal(document.activeElement,head,'the keyboard is on the replacement unit head');
  assert.equal(head.attrs['data-control-owner'],'book::first::'+paragraphId,'the head is the same unit by its coordinate');
  assert.deepEqual(head.focusOptions,{preventScroll:true});
  // the second row: its read answers after the card is gone (the page moved on); nothing is painted or focused
  const second=host.querySelectorAll('.reader-paragraph')[1];await second.querySelector('.reader-unit-head').click();
  const openSecond=host.querySelectorAll('.reader-paragraph')[1],door=openSecond.all().find(n=>n.attrs['data-control']==='reader-plan:paragraph-expand');assert.ok(door);
  let release;gate=new Promise(resolve=>{release=resolve;});
  const pending=door.click();
  const elsewhere=new Node('button');dom.body.append(elsewhere);elsewhere.focus();
  openSecond.remove();const count=calls.length;release();await pending;
  assert.equal(document.activeElement,elsewhere,'a late answer never moves the keyboard');
  assert.ok(!host.querySelectorAll('.reader-paragraph').some(card=>card.dataset.paragraphId===openSecond.dataset.paragraphId),'nothing was painted for the removed card');
  assert.ok(calls.length>=count);
  controller.destroy();
 }finally{dom.restore();}
});
