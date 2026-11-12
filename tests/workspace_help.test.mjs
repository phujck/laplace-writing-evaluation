// M5 C10 (2026-10-14): the help layer, the learning record and its migration from the retired
// laplace:guide key, the task rows, the anchored cue runner, and source coverage of the controls
// the help surfaces render against the help owner's declarations.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {installDOM,Node,findButton} from './helpers/evidence_reader_harness.mjs';
import {mountHelp,helpArea} from '../src/laplace/web/static_shared/workspace-help.mjs';
import {learningStore,journeyRows,learningKey,legacyGuideKey} from '../src/laplace/web/static_shared/workspace-journeys.mjs';
import {mountGuide,journeySteps as journeyStepsOf,stepTarget,cuePlacement} from '../src/laplace/web/static_shared/workspace-guide.mjs';
const AREAS=JSON.parse(await readFile(new URL('./fixtures/help/areas.json',import.meta.url),'utf8'));
const CONTROLS_READ=JSON.parse(await readFile(new URL('./fixtures/help/controls.json',import.meta.url),'utf8'));// wave 13: the overview no longer lists controls; journey steps read their ids from the controls read
const journeySteps=(areas,id,controls=CONTROLS_READ)=>journeyStepsOf(areas,id,controls);
const DECLARED=new Set(CONTROLS_READ.controls.map(row=>row.id));
const controlsIn=host=>host.all().map(n=>n.dataset?.control||n.attrs?.['data-control']).filter(Boolean);
const memory=()=>{const store=new Map();return {store,storage:{getItem:k=>store.get(k)??null,setItem:(k,v)=>store.set(k,v),removeItem:k=>store.delete(k)}};};

test('the learning record migrates the retired laplace:guide value once and removes the old key; rows say the person\'s progress',()=>{
 const {store,storage}=memory();
 store.set(legacyGuideKey('book'),JSON.stringify({step:3,closed:false}));
 const learning=learningStore('book',storage);
 assert.deepEqual(learning.journey('welcome'),{step:3,closed:false},'the welcome tour progress is carried over');
 assert.equal(store.has(legacyGuideKey('book')),false,'the retired key is removed');
 assert.equal(JSON.parse(store.get(learningKey('book'))).migrated_from,legacyGuideKey('book'));
 learning.update('why-waiting',{step:1});
 const again=learningStore('book',storage);
 assert.deepEqual(again.journey('why-waiting'),{step:1,closed:false});assert.equal(again.journey('missing'),null);
 const rows=journeyRows(AREAS,'work',again);
 assert.deepEqual(rows.map(row=>[row.id,row.status,row.steps]),[['why-waiting','Step 2 of 3',3]]);
 assert.equal(journeyRows(AREAS,'overview',again)[0].status,'Step 4 of 10');
 assert.deepEqual(journeyRows(AREAS,'settings',again),[],'an area without a declared journey lists nothing');
 // a malformed record is replaced, never trusted
 store.set(learningKey('book'),'{broken');assert.deepEqual(learningStore('book',storage).read().journeys,{});
});

test('the help layer renders one area from the declarations: glance, tasks, how it works (one lazy diagram read), states, shortcuts; Esc closes to the door',async()=>{
 const dom=installDOM(),main=new Node('main');dom.body.append(main);
 try{
  const {storage}=memory();let reads=0,closed=0,started=[];
  const diagrams=[{id:'work',title:'Work: facets and the dispatch tree',description:'A work item carries four separate facets.',nodes:[{id:'item',title:'Work item'},{id:'lifecycle',title:'Recorded lifecycle'}],edges:[{kind:'contains',source:'item',target:'lifecycle'}],layout:{rank:{item:0,lifecycle:1},groups:[]}}];
  const help=mountHelp(main,{project:'book',areas:AREAS,view:'work',store:learningStore('book',storage),readDiagrams:async()=>{reads++;return diagrams;},onJourney:id=>started.push(id),onClose:()=>closed++});
  const layer=help.element;
  assert.equal(layer.dataset.control,'help:layer');assert.equal(layer.attrs['aria-label'],'Help · Work');assert.equal(layer.attrs.role,'complementary');assert.ok(main.children.includes(layer),'the layer lives inside main');
  assert.ok(layer.textContent.includes(helpArea(AREAS,'work').glance));
  const task=layer.all().find(n=>n.dataset.control==='help:task');assert.ok(task);assert.equal(task.textContent,'Find why work is waiting');assert.ok(task.parent.textContent.includes('Not started · 3 steps'));
  await task.onclick();assert.deepEqual(started,['why-waiting']);
  const how=findButton(layer,'How it works');assert.equal(how.attrs['data-control'],'help:diagram');assert.equal(reads,0,'the diagram is not read on mount');
  await how.onclick();assert.equal(reads,1);
  const map=layer.querySelector('.topology');assert.ok(map&&map.textContent.includes('Work item')&&map.textContent.includes('Contains'),'the diagram is drawn and listed from the declaration');
  await findButton(layer,'Hide how it works').onclick();await findButton(layer,'How it works').onclick();assert.equal(reads,1,'one read per layer');
  assert.ok(layer.all().some(n=>n.className.split(' ').includes('state-chip')&&n.textContent==='Readiness blocked'),'the state legend');
  // another view repaints the same layer without a read
  help.show('reader-plan');assert.equal(layer.attrs['aria-label'],'Help · Reader plan');assert.ok(layer.textContent.includes('From the reader plan to the source and back'));
  help.show('overview');assert.ok(layer.textContent.includes('Open help for this view'),'shortcuts render');
  help.show('settings');assert.ok(layer.textContent.includes('No guided task for this view yet.'));
  for(const control of controlsIn(layer))assert.ok(DECLARED.has(control),'undeclared control '+control);
  layer.onkeydown({key:'Escape',preventDefault(){}});assert.equal(closed,1);assert.equal(layer.isConnected,false);assert.equal(help.alive,false);
  assert.throws(()=>mountHelp(main,{project:'book',areas:{},view:'work'}),/areas declaration/);
 }finally{dom.restore();}
});

test('a task cue anchors beside its declared control, highlights it, records progress in the learning record and stops on Esc',()=>{
 const dom=installDOM();
 try{
  const root=new Node('div');root.dataset.view='overview';dom.body.append(root);
  const nav=new Node('button');nav.setAttribute('data-control','nav:work');nav.dataset.control='nav:work';const chip=new Node('button');chip.dataset.workScope='';chip.hidden=true;root.append(nav,chip);
  const keys=[];dom.body.addEventListener=undefined;globalThis.document.addEventListener=(name,fn)=>keys.push([name,fn]);globalThis.document.removeEventListener=()=>{};
  const {store,storage}=memory();
  const steps=journeySteps(AREAS,'why-waiting');assert.equal(steps.length,3);
  const guide=mountGuide(root,{project:'book',steps,journeyId:'why-waiting',storage,page:globalThis.document});
  assert.equal(guide.element.dataset.control,'help:cue');assert.equal(guide.element.dataset.journey,'why-waiting');assert.ok(findButton(guide.element,'Stop'));
  assert.equal(guide.target,nav,'the first visible declared control is the anchor');assert.ok(nav.classList.contains('is-help-target'));
  assert.equal(guide.element.attrs['aria-describedby'],nav.id);
  assert.equal(stepTarget(root,'missing:control',globalThis.document),null);
  root.dataset.view='work';guide.paint();assert.equal(guide.element.getAttribute('data-done'),'true');
  findButton(guide.element,'Next').onclick();assert.equal(guide.index,1);
  const entry=JSON.parse(store.get(learningKey('book'))).journeys['why-waiting'];
  assert.deepEqual([entry.step,entry.closed,entry.outcome,entry.run.seen],[1,false,undefined,['open']],'the run records the step it saw');
  assert.ok(!nav.classList.contains('is-help-target'),'the previous target loses its highlight');
  const esc=keys.find(([name])=>name==='keydown')[1];esc({key:'Escape',preventDefault(){}});
  assert.equal(guide.element.isConnected,false);const stopped=JSON.parse(store.get(learningKey('book'))).journeys['why-waiting'];
  assert.deepEqual([stopped.step,stopped.closed,stopped.outcome],[1,true,'stopped'],'Escape is a stop, never a finish');
  for(const control of controlsIn(guide.element))assert.ok(DECLARED.has(control),'undeclared control '+control);
  // placement: beside the target when there is room, below when there is not, never over it
  assert.deepEqual(cuePlacement({left:100,top:50,right:200,bottom:80},{w:360,h:160},{w:1280,h:800}),{left:212,top:50});
  assert.deepEqual(cuePlacement({left:1000,top:50,right:1200,bottom:80},{w:360,h:160},{w:1280,h:800}),{left:912,top:92});
  assert.equal(cuePlacement(null,{w:1,h:1},{w:1,h:1}),null);
 }finally{dom.restore();}
});

// repair H3 (2026-10-14): the migration is a user-state operation: carried whole, written and read back
// before the retired key goes, a failed write keeps the original, a foreign record is never overwritten
test('learning migration preserves unknown fields, survives a failed write with the original intact, keeps mixed new progress and never overwrites a foreign record',()=>{
 const make=({failWrites=false,lie=false}={})=>{const m=new Map();return {m,storage:{getItem:k=>m.get(k)??null,setItem:(k,v)=>{if(failWrites)throw Error('quota');m.set(k,lie?'{}':v);},removeItem:k=>m.delete(k)}};};
 const old={step:3,closed:false,custom:'keep unknown preference',future:{enabled:true}};
 // unknown fields travel whole; the old key goes only after the read-back matches
 {const {m,storage}=make();m.set(legacyGuideKey('p'),JSON.stringify(old));const s=learningStore('p',storage);
  assert.deepEqual(s.journey('welcome'),old);assert.equal(s.status,'saved');assert.equal(m.has(legacyGuideKey('p')),false);
  assert.deepEqual(learningStore('p',storage).journey('welcome'),old,'reload sees the carried record');}
 // quota failure: the original stays, nothing is half-written, status is truthful, a later reload migrates again
 {const failing=make({failWrites:true});failing.m.set(legacyGuideKey('p'),JSON.stringify(old));const s=learningStore('p',failing.storage);
  assert.deepEqual(s.journey('welcome'),old,'in memory the progress is carried');assert.equal(s.status,'unsaved');
  assert.equal(failing.m.get(legacyGuideKey('p')),JSON.stringify(old),'the retired key is untouched');assert.equal(failing.m.has(learningKey('p')),false);
  s.update('welcome',{step:4});assert.equal(s.status,'unsaved','a later failed save stays unsaved');assert.equal(failing.m.get(legacyGuideKey('p')),JSON.stringify(old));
  const recovered={m:failing.m,storage:{getItem:k=>failing.m.get(k)??null,setItem:(k,v)=>failing.m.set(k,v),removeItem:k=>failing.m.delete(k)}};
  assert.deepEqual(learningStore('p',recovered.storage).journey('welcome'),old,'once storage works the original migrates');assert.equal(failing.m.has(legacyGuideKey('p')),false);}
 // a storage that accepts but does not keep the write is not a save
 {const lying=make({lie:true});lying.m.set(legacyGuideKey('p'),JSON.stringify(old));const s=learningStore('p',lying.storage);assert.equal(s.status,'unsaved');assert.equal(lying.m.has(legacyGuideKey('p')),true);}
 // mixed: existing new progress for welcome wins; other journeys and fields are kept; the old key is retired after a verified save
 {const {m,storage}=make();m.set(learningKey('p'),JSON.stringify({schema_version:'laplace.learning/1',journeys:{welcome:{step:7,closed:true,note:'mine'},'why-waiting':{step:1,closed:false}},migrated_from:null,extra:'kept'}));m.set(legacyGuideKey('p'),JSON.stringify(old));
  const s=learningStore('p',storage);assert.deepEqual(s.journey('welcome'),{step:7,closed:true,note:'mine'});assert.deepEqual(s.journey('why-waiting'),{step:1,closed:false});
  assert.equal(JSON.parse(m.get(learningKey('p'))).extra,'kept','unknown top-level fields survive');assert.equal(m.has(legacyGuideKey('p')),false);}
 // a foreign or unreadable record is never overwritten; progress is read-only; the old key stays
 for(const foreign of [JSON.stringify({schema_version:'laplace.learning/2',journeys:{welcome:{step:9}}}),'{broken']){
  const {m,storage}=make();m.set(learningKey('p'),foreign);m.set(legacyGuideKey('p'),JSON.stringify(old));const s=learningStore('p',storage);
  assert.equal(s.status,'unsupported');s.update('welcome',{step:1});assert.equal(m.get(learningKey('p')),foreign,'the foreign record is untouched');assert.equal(m.get(legacyGuideKey('p')),JSON.stringify(old));}
 // an unreadable retired value stays where it is
 {const {m,storage}=make();m.set(legacyGuideKey('p'),'not json');const s=learningStore('p',storage);assert.deepEqual(s.read().journeys,{});assert.equal(m.get(legacyGuideKey('p')),'not json');}
});

// repair2 R3 (2026-10-14): mixed old/new state loses nothing; malformed containers are refused untouched
test('a mixed migration keeps the retired record whole while newer progress wins; arrays and malformed entries are never overwritten',()=>{
 const make=()=>{const m=new Map();return {m,storage:{getItem:k=>m.get(k)??null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k)}};};
 const old={step:3,closed:false,oldUnknown:{keep:true}};
 // mixed: newer welcome progress wins; the old record is kept whole, opaque; reload keeps both
 {const {m,storage}=make();m.set(learningKey('p'),JSON.stringify({schema_version:'laplace.learning/1',journeys:{welcome:{step:7,closed:true,newUnknown:'keep new'}},extra:'keep top-level'}));m.set(legacyGuideKey('p'),JSON.stringify(old));
  const s=learningStore('p',storage);assert.deepEqual(s.journey('welcome'),{step:7,closed:true,newUnknown:'keep new'});assert.equal(s.status,'saved');
  const stored=JSON.parse(m.get(learningKey('p')));assert.deepEqual(stored.legacy_records[legacyGuideKey('p')],old,'the retired record survives whole');assert.equal(stored.extra,'keep top-level');
  assert.equal(m.has(legacyGuideKey('p')),false,'retired only after the verified write');
  const again=learningStore('p',storage);assert.deepEqual(again.read().legacy_records[legacyGuideKey('p')],old);assert.deepEqual(again.journey('welcome').newUnknown,'keep new');}
 // a later different retired value (conflict) is kept beside the first, not over it
 {const {m,storage}=make();m.set(learningKey('p'),JSON.stringify({schema_version:'laplace.learning/1',journeys:{welcome:{step:1}},legacy_records:{[legacyGuideKey('p')]:old}}));const other={step:9,note:'second'};m.set(legacyGuideKey('p'),JSON.stringify(other));
  learningStore('p',storage).read();const kept=JSON.parse(m.get(learningKey('p'))).legacy_records;assert.deepEqual(kept[legacyGuideKey('p')],old);assert.ok(Object.values(kept).some(v=>v.note==='second'),'both conflicting records are kept');}
 // a journeys array (and any non-plain container) is foreign: not overwritten, the retired key stays
 for(const journeys of [[],'text',null,7]){const {m,storage}=make();const stored=JSON.stringify({schema_version:'laplace.learning/1',journeys,extra:1});m.set(learningKey('p'),stored);m.set(legacyGuideKey('p'),JSON.stringify(old));
  const s=learningStore('p',storage);assert.equal(s.status,'unsupported');s.update('welcome',{step:4});assert.equal(m.get(learningKey('p')),stored,JSON.stringify(journeys)+' container untouched');assert.ok(m.has(legacyGuideKey('p')));}
 // a malformed entry is kept; its progress is not written; other journeys still save
 {const {m,storage}=make();m.set(learningKey('p'),JSON.stringify({schema_version:'laplace.learning/1',journeys:{welcome:5}}));const s=learningStore('p',storage);
  assert.equal(s.journey('welcome'),null);assert.equal(s.update('welcome',{step:2}),null);assert.equal(JSON.parse(m.get(learningKey('p'))).journeys.welcome,5);
  s.update('why-waiting',{step:1});assert.deepEqual(JSON.parse(m.get(learningKey('p'))).journeys['why-waiting'],{step:1,closed:false});assert.equal(JSON.parse(m.get(learningKey('p'))).journeys.welcome,5);}
});
// repair3 R3 (2026-10-14): legacy_records never loses a value already there. An opaque value under the
// reserved field makes the record read-only before any write or removal; a conflicting retired record
// takes a verified unused key (noncontiguous keys included); repeated migrations and reloads keep all.
test('legacy_records: an opaque reserved value is never overwritten and kept records survive conflicting, noncontiguous and repeated migrations',()=>{
 const key=legacyGuideKey('book');
 for(const opaque of [['opaque existing preference'],'a string',7,null,[{nested:true}]]){
  const {store,storage}=memory();const before={schema_version:'laplace.learning/1',journeys:{welcome:{step:7}},legacy_records:opaque,extra:'keep'};
  const text=JSON.stringify(before);store.set(learningKey('book'),text);store.set(key,JSON.stringify({step:3,custom:'keep old'}));
  const learning=learningStore('book',storage);learning.read();
  assert.equal(learning.status,'unsupported',JSON.stringify(opaque)+': classified before any write');
  assert.equal(store.get(learningKey('book')),text,'the stored record is byte-identical');assert.equal(store.get(key),JSON.stringify({step:3,custom:'keep old'}),'the retired key stays');
  assert.equal(learning.journey('welcome').step,7,'the recorded progress is still read');
  learning.update('welcome',{step:9});assert.equal(store.get(learningKey('book')),text,'progress is not written over an unsupported record');
  const reload=learningStore('book',storage);assert.equal(reload.status,'unsupported');assert.equal(store.get(learningKey('book')),text);
 }
 // a valid map with noncontiguous keys: the base key and #3 are taken; a conflicting record takes #2, the next #4
 const {store,storage}=memory();const A={step:1,unknown:'record A'},C3={step:2,unknown:'protected record at #3'},odd=['opaque entry'];
 store.set(learningKey('book'),JSON.stringify({schema_version:'laplace.learning/1',journeys:{welcome:{step:7}},legacy_records:{[key]:A,[key+'#3']:C3,'someone-else':odd}}));
 store.set(key,JSON.stringify({step:4,unknown:'record D'}));
 let learning=learningStore('book',storage);learning.read();assert.equal(learning.status,'saved');assert.equal(store.has(key),false,'removed only after the read-back');
 let kept=JSON.parse(store.get(learningKey('book'))).legacy_records;
 assert.deepEqual(kept,{[key]:A,[key+'#3']:C3,'someone-else':odd,[key+'#2']:{step:4,unknown:'record D'}});
 // the same record arriving again (a removal that failed earlier) is not kept twice
 store.set(key,JSON.stringify({unknown:'record D',step:4}));learning=learningStore('book',storage);learning.read();
 kept=JSON.parse(store.get(learningKey('book'))).legacy_records;assert.equal(Object.keys(kept).length,4,'an identical record (any key order) is not duplicated');
 // another conflicting record: #2 and #3 are taken, so #4
 store.set(key,JSON.stringify({step:5,unknown:'record E'}));learning=learningStore('book',storage);learning.read();
 kept=JSON.parse(store.get(learningKey('book'))).legacy_records;assert.deepEqual(kept[key+'#4'],{step:5,unknown:'record E'});
 assert.deepEqual([kept[key],kept[key+'#2'],kept[key+'#3'],kept['someone-else']],[A,{step:4,unknown:'record D'},C3,odd],'every earlier record is intact');
 // newer progress still wins and a reload reads every record back
 const reload=learningStore('book',storage);assert.equal(reload.journey('welcome').step,7);assert.equal(Object.keys(reload.read().legacy_records).length,5);
 reload.update('welcome',{step:8});assert.equal(Object.keys(JSON.parse(store.get(learningKey('book'))).legacy_records).length,5,'a progress write keeps every kept record');
});
// ACTUAL-C10-HELP-RESIZE (2026-10-14): help that is already open follows the viewport. The same layer
// changes dock class and Expand control only; area, open diagram (redrawn for the width), the person's
// expanded choice and task progress stay.
test('an open help layer switches between overlay and dock in place, keeping its area, open diagram and expanded choice',async()=>{
 const dom=installDOM(),main=new Node('main');dom.body.append(main);
 try{document.createElementNS=(_ns,tag)=>new Node(tag);
  const {storage}=memory();let reads=0;
  const diagrams=[{id:'work',title:'Work: facets',description:'A work item carries four separate facets.',nodes:[{id:'item',title:'Work item'},{id:'lifecycle',title:'Recorded lifecycle'}],edges:[{kind:'contains',source:'item',target:'lifecycle'}]}];
  const help=mountHelp(main,{project:'book',areas:AREAS,view:'work',store:learningStore('book',storage),readDiagrams:async()=>{reads++;return diagrams;},narrow:false});
  const layer=help.element,expand=layer.all().find(n=>n.className.includes('workspace-help-expand'));
  const classes=()=>layer.className.split(' ');
  assert.ok(!classes().includes('is-dock')&&expand.hidden,'wide: an overlay with no Expand');
  await findButton(layer,'How it works').onclick();assert.ok(layer.querySelector('.topology').all().some(n=>n.tag==='svg'),'wide: the diagram is drawn as a graph');
  help.setNarrow(true);
  assert.ok(classes().includes('is-dock')&&!expand.hidden,'narrow: the same layer docks and offers Expand');
  assert.equal(help.area.id,'work');assert.ok(findButton(layer,'Hide how it works'),'the diagram section stays open');assert.equal(reads,1,'no further read');
  assert.ok(!layer.querySelector('.topology').all().some(n=>n.tag==='svg'),'narrow: the open diagram is redrawn as its list');assert.ok(layer.textContent.includes('Work item'));
  expand.onclick();assert.ok(classes().includes('is-expanded'));
  help.setNarrow(false);assert.ok(!classes().includes('is-dock')&&expand.hidden,'wide again: overlay');
  help.setNarrow(true);assert.ok(classes().includes('is-dock')&&classes().includes('is-expanded')&&expand.textContent==='Collapse','the expanded choice applies again in the dock');
  assert.ok(main.children.includes(layer)&&help.alive,'one layer throughout');
  help.close();help.setNarrow(false);assert.equal(help.alive,false,'a closed layer ignores later resizes');
 }finally{dom.restore();}
});
// C12 HELP FOCUS (Root actual, 2026-10-15): focus on "Hide how it works" at 1280, then 1000/720, fell to BODY because
// the collapsed dock does not display the body. Focus now moves to the visible control that stands for it and
// comes back; focus outside the layer is never moved; nothing is expanded or closed for the person.
test('a layout change keeps focus on a visible help control and returns it; outside focus is untouched',async()=>{
 const dom=installDOM(),main=new Node('main');dom.body.append(main);
 try{document.createElementNS=(_ns,tag)=>new Node(tag);
  const {storage}=memory();
  const diagrams=[{id:'work',title:'Work: facets',description:'d',nodes:[{id:'item',title:'Work item'}],edges:[]}];
  const help=mountHelp(main,{project:'book',areas:AREAS,view:'work',store:learningStore('book',storage),readDiagrams:async()=>diagrams,narrow:false});
  const layer=help.element,expand=layer.all().find(n=>n.className.includes('workspace-help-expand')),close=layer.all().find(n=>n.className.includes('workspace-help-close'));
  const toggle=findButton(layer,'How it works');await toggle.onclick();
  toggle.focus();assert.equal(document.activeElement,toggle);
  help.setNarrow(true);
  assert.equal(document.activeElement,expand,'collapsed dock: focus is on Expand, not BODY');assert.equal(expand.getAttribute('aria-expanded'),'false','nothing expanded for the person');
  assert.ok(findButton(layer,'Hide how it works'),'the open section stays open');
  help.setNarrow(false);
  assert.equal(document.activeElement,toggle,'wide again: focus returns to the control it left');
  // Expand chosen in the dock keeps the body visible: focus inside it stays where it is
  help.setNarrow(true);expand.onclick();toggle.focus();help.setNarrow(false);help.setNarrow(true);
  assert.equal(document.activeElement,toggle,'an expanded dock displays the body; focus stays');
  // widening while on Expand with nothing remembered goes to Close
  expand.focus();help.setNarrow(false);assert.equal(document.activeElement,close);
  // focus outside the layer is never taken
  const outside=new Node('button');main.append(outside);outside.focus();help.setNarrow(true);help.setNarrow(false);
  assert.equal(document.activeElement,outside);
  // a focused node inside the open diagram is removed by the redraw: focus goes to the diagram toggle
  const drawn=layer.querySelector('.topology').all().find(n=>n.tag!=='#text')||layer.querySelector('.topology');drawn.focus();
  layer.classList.add('is-expanded');help.setNarrow(true);
  assert.equal(document.activeElement,toggle,'redrawn diagram: focus on its toggle');
 }finally{dom.restore();}
});


test('document and reference help is an orientation over observed navigation, with explicit real actions',async()=>{
 const dom=installDOM(),main=new Node('main');dom.body.append(main);
 try{
  const {storage}=memory();let starts=[];
  const help=mountHelp(main,{project:'book',areas:AREAS,view:'material',store:learningStore('book',storage),onJourney:id=>starts.push(id),onClose(){}});
  assert.match(help.element.textContent,/Add a local PDF or text document/);
  await findButton(help.element,'Find document and reference actions').onclick();
  assert.deepEqual(starts,['document-reference-actions']);
  help.show('research');assert.match(help.element.textContent,/Link to claim|link a located passage/);
  assert.ok(findButton(help.element,'Find document and reference actions'));
  const steps=journeySteps(AREAS,'document-reference-actions');
  assert.deepEqual(steps.map(step=>step.control),['nav:material','conversation:toggle','conversation:context','nav:research']);
  const states=[{view:'material'},{sessionOpen:true},{sessionOpen:true,inspectorOpen:true},{view:'research'}];
  steps.forEach((step,index)=>assert.equal(step.done(states[index]),true));
  assert.equal(steps[2].done({sessionOpen:true,inspectorOpen:false}),false);
  assert.ok(CONTROLS_READ.controls.some(row=>row.id==='material:add-document'));
  assert.ok(CONTROLS_READ.controls.some(row=>row.id==='material:add-literature'));
  assert.ok(CONTROLS_READ.controls.some(row=>row.id==='conversation:add-document'));
  assert.deepEqual(AREAS.observation_facts,['view','outline','returnVisible','historyOpen','workSelected','sessionOpen','inspectorOpen','templateOpen','researchFocus','researchRepresentation','researchFocal','researchReading','researchInputs','reviewPanel'],'no file, save, upload or claim completion is inferred');
  help.close();
 }finally{dom.restore();}
});

// Wave 11 census repair R3 (R12): a page is helped only by its own declared area. Now opened Help · Projects because the
// door was handed view 'projects' and an unknown view fell back to the project's Home area.
// Wave 11b E3: project-work.mjs hands Now's door its own view 'now'; the host-place correction is gone, so a page is helped
// only by the area declared for the view it was handed.
test('wave 11 R3: Now is helped by its own declared area; a view with no area borrows nothing; parts are listed',()=>{
 const dom=installDOM();try{
  const areas={...AREAS,areas:[...AREAS.areas.filter(row=>row.view!=='now'),{id:'now',view:'now',title:'Now',glance:'What is running, what waits for you, and where to continue.',
   parts:[{name:'Running now',says:'Work the engine reports running.'},{name:'Start',says:'Create a project.'}],states:[],shortcuts:[],journeys:[]}]};
  assert.equal(helpArea(areas,'no-such-view'),null,'no fallback to another page\'s area');
  const now=new Node('main');now.dataset.place='now';dom.body.append(now);
  const help=mountHelp(now,{areas,view:'now'});
  assert.match(help.element.textContent,/Help · Now/);assert.match(help.element.textContent,/On this page/);assert.match(help.element.textContent,/Running now/);
  assert.ok(!help.element.textContent.includes('Help · Projects'));help.dispose();
  const handed=mountHelp(now,{areas,view:'projects'});assert.ok(!handed.element.textContent.includes('Help · Now'),'the host place no longer overrides the view it was handed');handed.dispose();
  const other=new Node('main');dom.body.append(other);const bare=mountHelp(other,{areas,view:'no-such-view'});
  assert.match(bare.element.textContent,/Help · this page/);assert.match(bare.element.textContent,/This page has no guide yet\./);bare.dispose();
 }finally{dom.restore();}
});
