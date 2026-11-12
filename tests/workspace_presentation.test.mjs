import {test} from 'node:test';
import assert from 'node:assert/strict';
import {installDOM,Node,findButton} from './helpers/evidence_reader_harness.mjs';
import {TONES,stateChip,workChips,continuationChip,childChip,evidenceChip,inputChip,bindingChip,documentChips,templateChips,objectHeader,relationList,lazySection,clippedText,hunkCard,orderedPlan,coordinationLadder,action} from '../src/laplace/web/static_shared/workspace-presentation.mjs';
import {observeWorkspace,guideProgress,mountGuide,journeySteps as journeyStepsOf,stepDone} from '../src/laplace/web/static_shared/workspace-guide.mjs';
import {readFile} from 'node:fs/promises';
// The guide's steps are the help owner's `welcome` journey (G8); this fixture is the owner's
// rendering of its declarations, witnessed against writing_declarations.help_areas by
// tests/test_shared_reads_batch.py.
const HELP_AREAS=JSON.parse(await readFile(new URL('./fixtures/help/areas.json',import.meta.url),'utf8'));
const CONTROLS_READ=JSON.parse(await readFile(new URL('./fixtures/help/controls.json',import.meta.url),'utf8'));// wave 13: the overview no longer lists controls; journey steps read their ids from the controls read
const journeySteps=(areas,id,controls=CONTROLS_READ)=>journeyStepsOf(areas,id,controls);
const GUIDE_STEPS=journeySteps(HELP_AREAS,'welcome');
import {continuationRows,dispatchChildRows} from '../src/laplace/web/static_shared/prepared-work.mjs';

const chips=header=>header.all().filter(n=>n.className.split(' ').includes('state-chip')).map(n=>[n.textContent,n.dataset.tone]);

test('tone tables keep owner facets distinct: recorded lifecycle, readiness and acceptance are separate chips',()=>{
  const dom=installDOM();
  try{
    const task={lifecycle:{status:'in-progress',completed:false,closed:false},readiness:{status:'BLOCKED',reason:'prerequisite open'},current_acceptance:{status:'NOT_REQUIRED',review_required:false},dispatch:{execution_state:'RUNNING'}};
    const rows=workChips(task);
    // Declared progress, unmet prerequisites and observed execution remain distinct.
    assert.deepEqual(rows.map(row=>[row.label,row.tone]),[['In progress (declared) · waiting on prerequisites','neutral'],['Execution owner: running','running']]);
    const completed=workChips({lifecycle:{status:'done',completed:true,closed:true},current_acceptance:{status:'STALE',review_required:true,reason:'source moved'}});
    assert.deepEqual(completed.map(row=>[row.label,row.tone]),[['Completed — evidence needs rechecking','attention']]);
    assert.ok(!completed.some(row=>/current$/i.test(row.label)&&row.tone==='ok'),'stale acceptance is never painted as current');
    for(const row of [...rows,...completed])assert.ok(TONES.includes(row.tone));
    assert.throws(()=>stateChip({label:'x',tone:'green'}),/Unknown presentation tone/);
  }finally{dom.restore();}
});

test('continuation, child, evidence, input and binding chips follow the owner states without inventing acceptance',()=>{
  assert.equal(continuationChip({phase:'WAITING'}).tone,'running');
  assert.match(continuationChip({phase:'READY',review_state:'REJECTED',execution_state:'COMPLETE',synthesis:{}}).label,/review rejected/);
  assert.match(continuationChip({phase:'READY',review_state:'ACCEPTED',execution_state:'FAILED',synthesis:{}}).label,/missing or failed/);
  assert.equal(continuationChip({phase:'READY',review_state:'ACCEPTED',execution_state:'COMPLETE',synthesis:{status:'VALID',attachment:'ATTACHED'}}).tone,'ok');
  assert.equal(continuationChip({phase:'READY',review_state:'ACCEPTED',execution_state:'COMPLETE',synthesis:{status:'MISSING'}}).tone,'attention');
  assert.equal(continuationChip({phase:'PARENT_STOPPED'}).tone,'historical');
  assert.equal(continuationChip({phase:'BLOCKED'}).tone,'blocked');
  assert.equal(childChip({state:'NO-RETURN'}).tone,'neutral');
  assert.equal(childChip({state:'FAILED'}).tone,'blocked');
  assert.equal(childChip({state:'COMPLETE'}).tone,'ok');
  assert.deepEqual(evidenceChip('CHANGED'),{label:'Changed since this record',tone:'attention'});
  assert.deepEqual(evidenceChip('MATCH'),{label:'Matches recorded bytes',tone:'ok'});
  assert.equal(inputChip({status:'UNOBSERVED'}).tone,'attention');
  assert.equal(inputChip(null),null);
  assert.equal(bindingChip({precision:'EXACT_HEADING',heading:{title:'Intro'}}).tone,'ok');
  assert.equal(bindingChip({precision:'INFERRED'}).tone,'attention');
  assert.equal(bindingChip({}),null,'no support dot is guessed when the owner reports no binding');
  assert.deepEqual(documentChips({status:'READY'}).map(row=>row.label),['PDF matches saved document']);
  assert.deepEqual(documentChips({status:'STALE'},true).map(row=>row.tone),['attention','attention']);
  const template=templateChips({currentness:{status:'CURRENT'},build:{state:'done'},application_recording:{status:'NOT_APPLIED'}},{build_job:'BLD-1'});
  assert.deepEqual(template.map(row=>row.label),['Source basis current','Preview built','Exact preview reviewed']);
});

test('object header, relation list and action row render owner words with the primary action beside the object',async()=>{
  const dom=installDOM();
  try{
    const ran=[];
    const header=objectHeader({eyebrow:'Selected work',title:'Resolve findings',chips:[{label:'Readiness blocked',tone:'blocked'}],summary:'Owner summary.',actions:[{label:'Inspect prerequisite',primary:true,run:()=>ran.push('inspect')}]});
    assert.equal(header.querySelector('.object-title').textContent,'Resolve findings');
    assert.deepEqual(chips(header),[['Readiness blocked','blocked']]);
    await findButton(header,'Inspect prerequisite').onclick();assert.deepEqual(ran,['inspect']);
    assert.ok(findButton(header,'Inspect prerequisite').className.includes('primary'));
    const list=relationList([{kind:'Contains',label:'Child A',run:()=>ran.push('A'),chip:{label:'Recorded done',tone:'historical'}},{kind:'Requires',label:'Gate B'}],{emptyText:'None recorded.'});
    assert.equal(list.querySelectorAll('.relation').length,2);
    await findButton(list,'Child A').onclick();assert.deepEqual(ran,['inspect','A']);
    assert.equal(relationList([],{emptyText:'None recorded.'}).textContent,'None recorded.');
    const failing=action({label:'Boom',run:async()=>{throw Error('refused by owner');}});const host=new Node('div');host.append(failing);await failing.onclick();
    assert.match(host.textContent,/refused by owner/);assert.equal(host.querySelector('.act-error').attrs.role,'alert');
  }finally{dom.restore();}
});

test('lazy section loads once on a deliberate action, surfaces its failure and never pretends the read happened',async()=>{
  const dom=installDOM();
  try{
    let loads=0;const section=lazySection({label:'Inspect exact closure',load:async()=>{loads++;if(loads===1)throw Error('owner unavailable');return 'closure text';},render:(body,value)=>body.append(value)});
    assert.equal(section.querySelector('.lazy-body').hidden,true);assert.equal(loads,0);
    await section.show();assert.match(section.textContent,/owner unavailable/);assert.equal(section.loaded,false);
    await findButton(section,'Retry').onclick();assert.match(section.textContent,/closure text/);assert.equal(section.loaded,true);
    section.hide();await section.show();assert.equal(loads,2,'a loaded section is not re-read on reopen');
    assert.equal(section.querySelector('.lazy-toggle').attrs['aria-expanded'],'true');
  }finally{dom.restore();}
});

test('hunk cards clip long text with an explicit expand and show whole-file snapshots as one column',()=>{
  const dom=installDOM();
  try{
    const long=Array.from({length:30},(_,i)=>'line '+i).join('\n');
    const card=hunkCard({title:'chapter.tex · recorded lines 3–33',before:'old',after:long,basis:'exact banked source-change hunk'},{index:2,total:5,lines:8});
    assert.match(card.querySelector('.hunk-title').textContent,/recorded lines 3–33/);assert.match(card.textContent,/2 of 5/);
    const more=findButton(card,'Show all 30 lines');assert.ok(more);assert.ok(!card.textContent.includes('line 29'));
    more.onclick();assert.ok(card.textContent.includes('line 29'));assert.ok(findButton(card,'Show first 8 lines'));
    const snapshot=hunkCard({title:'Banked editor save',before:null,after:'whole file'});
    assert.equal(snapshot.querySelector('.hunk-columns').dataset.columns,'1');assert.ok(!snapshot.textContent.includes('Before'));
    const empty=hunkCard({before:'',after:'new'});assert.match(empty.textContent,/\[Empty passage\]/);
    const clipped=clippedText('a\nb',{lines:5});assert.equal(findButton(clipped,/Show all/),undefined);
  }finally{dom.restore();}
});

test('ordered plan numbers exposition order only, separates title from purpose and marks the mechanical binding',async()=>{
  const dom=installDOM();
  try{
    const picked=[];
    const list=orderedPlan([{id:'s1',title:'Orientation',purpose:'Introduce the purpose.',mark:bindingChip({precision:'EXACT_HEADING'})},{id:'s2',title:'Homes of truth',purpose:'',mark:bindingChip({precision:'UNRESOLVED'})}],{current:'s2',onSelect:item=>picked.push(item.id)});
    const buttons=list.querySelectorAll('.ordered-plan-button');
    assert.equal(buttons.length,2);assert.equal(buttons[0].querySelector('.ordered-plan-number').textContent,'1');
    assert.equal(buttons[0].querySelector('.ordered-plan-title').textContent,'Orientation');assert.equal(buttons[0].querySelector('.ordered-plan-purpose').textContent,'Introduce the purpose.');
    assert.equal(buttons[1].attrs['aria-current'],'true');assert.equal(buttons[1].querySelector('.ordered-plan-purpose'),null);
    assert.equal(buttons[0].querySelector('.ordered-plan-mark').dataset.tone,'ok');assert.equal(buttons[1].querySelector('.ordered-plan-mark').dataset.tone,'neutral');
    await buttons[0].onclick();assert.deepEqual(picked,['s1']);
  }finally{dom.restore();}
});

test('coordination ladder paints the real continuation and dispatched children as rows with exact drilldowns',async()=>{
  const {parentWire}=await import('./helpers/parent_continuation_fixture.mjs');
  const dom=installDOM();
  try{
    const original=parentWire.observation,turns=[],owners=[];
    const judge={packet:'judge',role:'judge',state:'NO-RETURN',reply_status:'completed',return_exists:false,failure_count:1,failure_summary:'store_artifact not permitted',turn_id:'WT-judge',session_id:'WS-judge'};
    const rows=continuationRows({...original,child_outcomes:[judge]},{project:'book',onOwner:(read,label)=>owners.push([read,label]),onTurn:(id,options)=>turns.push([id,options]),onArtifact(){}});
    assert.equal(rows[0].role,'parent');assert.equal(rows[0].chip.tone,'running');assert.match(rows[0].what,/Parent waiting/);
    assert.equal(rows[0].children.length,1);assert.equal(rows[0].children[0].chip.label,'◐ Replied without a typed return');assert.match(rows[0].children[0].errors[0],/store_artifact/);
    const host=new Node('section');const ladder=coordinationLadder(host,{rows});
    const lines=ladder.querySelectorAll('.coordination-row');assert.equal(lines[0].dataset.role,'parent');assert.equal(lines[1].dataset.role,'child');assert.equal(lines[1].dataset.depth,'1');
    await findButton(ladder,'Read judge failed attempts').onclick();assert.deepEqual(turns,[['WT-judge',{focusView:'failures'}]]);
    await findButton(ladder,'Inspect dispatched work').onclick();assert.equal(owners[0][0].id,original.dispatch_id);
    const compact=continuationRows({...original,children_active:2,child_outcomes:[judge]},{project:'book',compact:true,onOwner(){}});
    assert.equal(compact[0].children.length,0,'compact rows keep the ladder to the parent line');assert.match(compact[0].what,/2 dispatched children/);
    const compactHost=new Node('section');coordinationLadder(compactHost,{rows:compact,compact:true});
    assert.equal(compactHost.querySelector('.coordination-facts'),null,'facts stay out of the compact ladder');
    assert.throws(()=>dispatchChildRows([{packet:'',role:'worker'}],{project:'book'}),/invalid child identity/);
  }finally{dom.restore();}
});

test('the guide observes real workspace state and only advances on what it sees; it never drives the app',()=>{
  const dom=installDOM();
  try{
    const root=new Node('div');root.dataset.view='overview';
    const outline=new Node('div');outline.dataset.manuscriptOutline='';outline.hidden=true;
    const back=new Node('button');back.dataset.returnReader='';back.hidden=true;
    const chip=new Node('button');chip.dataset.workScope='';chip.hidden=true;
    const session=new Node('aside');session.dataset.session='';session.hidden=true;
    const inspector=new Node('section');inspector.dataset.inspector='';inspector.hidden=true;
    root.append(outline,back,chip,session,inspector);dom.body.append(root);
    const store=new Map(),storage={getItem:k=>store.get(k)??null,setItem:(k,v)=>store.set(k,v)};
    const guide=mountGuide(root,{project:'book',steps:GUIDE_STEPS,storage,page:globalThis.document});
    const attr=name=>guide.element.getAttribute(name);
    assert.ok(!root.all().includes(guide.element),'the panel is mounted outside the observed workspace root');assert.ok(dom.body.children.includes(guide.element));
    assert.equal(attr('data-step'),'manuscript');assert.equal(attr('data-done'),'false');assert.ok(findButton(guide.element,'Skip'));
    root.dataset.view='manuscript';guide.paint();assert.equal(attr('data-done'),'true');assert.ok(findButton(guide.element,'Next'));
    findButton(guide.element,'Next').onclick();assert.equal(guide.index,1);assert.equal(JSON.parse(store.get('laplace:learning:book')).journeys.welcome.step,1,'progress lives in the learning record');assert.equal(store.get('laplace:guide:book'),undefined,'the retired key is never written');
    outline.hidden=false;guide.paint();assert.equal(attr('data-done'),'true');
    const done=guideProgress(GUIDE_STEPS,observeWorkspace(root,globalThis.document));
    assert.deepEqual(done.slice(0,2),[true,true]);assert.equal(done[GUIDE_STEPS.length-1],false);
    const dialog=new Node('dialog');dialog.className='document-template-dialog';dom.body.append(dialog);
    // C12: only a REAL live inspector counts: open, connected and adopted by the shared inspector
    assert.equal(guideProgress(GUIDE_STEPS,observeWorkspace(root,globalThis.document)).at(-1),false,'a dialog that is not open in the inspector is not observed');
    dialog.open=true;assert.equal(guideProgress(GUIDE_STEPS,observeWorkspace(root,globalThis.document)).at(-1),false,'open but not adopted');
    dialog.dataset.inspector='template-setup';assert.equal(guideProgress(GUIDE_STEPS,observeWorkspace(root,globalThis.document)).at(-1),true);
    assert.equal(root.dataset.view,'manuscript','the guide changed nothing in the app');
    guide.close();assert.equal(guide.element.isConnected,false);assert.equal(JSON.parse(store.get('laplace:learning:book')).journeys.welcome.closed,true);
  }finally{dom.restore();}
});

test('an idle guide never repaints itself: own mutations are ignored, unchanged observations paint nothing, Next keeps its identity and advances on one click',()=>{
  const dom=installDOM();
  const oldObserver=globalThis.MutationObserver,oldRaf=globalThis.requestAnimationFrame,oldCancel=globalThis.cancelAnimationFrame;
  const observers=[];let frames=0;
  globalThis.MutationObserver=class{constructor(callback){this.callback=callback;observers.push(this);}observe(){}disconnect(){this.disconnected=true;}};
  globalThis.requestAnimationFrame=callback=>{frames++;callback();return frames;};globalThis.cancelAnimationFrame=()=>{};
  try{
    const root=new Node('div');root.dataset.view='overview';dom.body.append(root);
    const chip=new Node('button');chip.dataset.workScope='';chip.hidden=true;root.append(chip);
    const guide=mountGuide(root,{project:'book',steps:GUIDE_STEPS,storage:{getItem:()=>null,setItem(){}},page:globalThis.document});
    const next=guide.next,paintsAfterMount=guide.paints;assert.equal(paintsAfterMount,1);
    // Mutations whose target is inside the panel (its own repaint) never schedule a paint.
    for(const observer of observers)observer.callback([{target:guide.element.querySelector('.workspace-guide-state')},{target:guide.element}]);
    assert.equal(frames,0);assert.equal(guide.paints,1);
    // Unrelated workspace mutations (seen by the root observer) with an unchanged observation schedule one frame and paint nothing.
    const rootObserver=observers[0];
    rootObserver.callback([{target:root}]);
    assert.equal(frames,1);assert.equal(guide.paints,1);
    for(let i=0;i<5;i++)guide.paint();assert.equal(guide.paints,1,'repeated observation of the same state is idempotent');
    // A meaningful state change paints once, in place: the Next button is the same node.
    root.dataset.view='manuscript';rootObserver.callback([{target:root,attributeName:'data-view'}]);
    assert.equal(guide.paints,2);assert.equal(guide.next,next);assert.equal(next.textContent,'Next');assert.ok(next.className.includes('primary'));
    next.onclick();assert.equal(guide.index,1);assert.equal(guide.next,next,'advancing keeps the same control');
    assert.equal(guide.element.getAttribute('data-step'),'outline');
    guide.close();assert.ok(observers.every(observer=>observer.disconnected));
  }finally{globalThis.MutationObserver=oldObserver;globalThis.requestAnimationFrame=oldRaf;globalThis.cancelAnimationFrame=oldCancel;dom.restore();}
});

test('the guide runs the help owner\'s declared journey: closed predicate language, declared controls, no local step copy',()=>{
  assert.equal(GUIDE_STEPS.length,10);assert.equal(GUIDE_STEPS[0].id,'manuscript');assert.equal(GUIDE_STEPS[0].control,'nav:manuscript');
  const facts={view:'manuscript',outline:true,returnVisible:false,historyOpen:false,workSelected:true,sessionOpen:false,inspectorOpen:false,templateOpen:false};
  assert.equal(stepDone({fact:'view',equals:'manuscript'},facts),true);assert.equal(stepDone({fact:'view',not_equals:'work'},facts),true);
  assert.equal(stepDone({all:[{fact:'view',equals:'manuscript'},{fact:'outline',truthy:true}]},facts),true);assert.equal(stepDone({all:[]},facts),false);
  assert.equal(stepDone({fact:'unknown',equals:1},facts),false,'an unobserved fact is never done');assert.equal(stepDone({fact:'view'},facts),false,'a predicate without an operator is never done');
  assert.throws(()=>journeySteps(HELP_AREAS,'missing'),/declares no journey/);
  assert.throws(()=>journeySteps(HELP_AREAS,'welcome',{...CONTROLS_READ,controls:[]}),/undeclared control/);
  assert.throws(()=>mountGuide({querySelector:()=>null,querySelectorAll:()=>[],dataset:{}},{project:'book',steps:[]}),/journey steps/);
});
