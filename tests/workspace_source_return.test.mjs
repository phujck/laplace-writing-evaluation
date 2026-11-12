// M5-R2 (2026-10-20): the reader plan's real source doors (FILE_ONLY, INFERRED, EXACT_HEADING) carry a local
// focus coordinate; an explicit action's intent is read before its control is disabled; Back is admitted once,
// at entry, across the awaited view render: a render raced by a later navigation, a refused show or a destroyed
// shell restores neither scroll nor focus; a door that is not painted again falls back to the section's own heading.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {register} from 'node:module';
register(new URL('./helpers/shared_resolve.mjs',import.meta.url));
import {installDOM,Node} from './helpers/evidence_reader_harness.mjs';
const {mountReaderPlan}=await import('../src/laplace/web/static_shared/workspace-spine.mjs');
const {mountReturns,focusCoordinate}=await import('../src/laplace/web/static_shared/workspace-returns.mjs');
const {mountHistory}=await import('../src/laplace/web/static_shared/workspace-history.mjs');
const fixture=JSON.parse(await readFile(new URL('./fixtures/editor_spine/display-owner.json',import.meta.url),'utf8'));
const copy=value=>structuredClone(value);
const FILE=fixture.display.sections[0].source.source_files[0];
const flush=()=>new Promise(resolve=>setTimeout(resolve,5));
Object.defineProperty(Node.prototype,'parentNode',{get(){return this.parent||null;}});
// the double keeps attrs and dataset apart; a DOM reflects data-* attributes into dataset, so the double does here too
const setAttribute=Node.prototype.setAttribute;Node.prototype.setAttribute=function(k,v){setAttribute.call(this,k,v);if(k.startsWith('data-'))this.dataset[k.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=String(v);};
globalThis.requestAnimationFrame??=fn=>setTimeout(fn,0);
const doorLabel={FILE_ONLY:'Inspect linked file',INFERRED:'Inspect suggested file',EXACT_HEADING:'Open in manuscript'};
function owner(precision){
  const display=copy(fixture.display),section=display.sections[0];section.source.precision=precision;
  if(precision==='EXACT_HEADING')section.source.heading={...section.source.heading,file:FILE};
  return async url=>{const q=new URL(url,'http://local').searchParams;if(q.get('view')==='summary')return copy(fixture.summary);if(q.get('projection')==='display')return copy(display);throw Error('Unexpected read '+url);};
}
// one shell: a main region that the reader plan is mounted into, the shell's views with a load generation,
// and a returns controller over them; `gate` defers the real reader-plan render that Back asks for
function shell(){
  const dom=installDOM(),main=new Node('main');main.dataset.main='';dom.body.append(main);
  let generation=1,current='reader-plan',controller=null,gate=null;
  const mount=async request=>{main.replaceChildren();controller=await mountReaderPlan(main,{project:'book',request,onScope(){},onConcept(){},onEvidence(){},onWork(){},onSource:onSourceDoor,onPrepareWork:async()=>{}});return controller;};
  const views={current:()=>current,show:async view=>{generation++;current=view;if(gate)await gate;if(current!==view)return;await mount(views.request);return true;},generation:()=>generation,setMode(){}};
  let place=null;const workspaceReturn={get current(){return place;},remember(value){if(!place)place=value;return place;},take(){const value=place;place=null;return value;},clear(){place=null;}};
  const noop={captureSurface:()=>({}),restoreSurface(){},returnPlace:()=>({view:'argument',label:'Argument'}),restoreQuery(){}};
  const readerHome={capture:()=>({sectionId:controller?.capture?.().sectionId||'first'}),restore(){},context:()=>({label:'Reader plan'})};
  const returns=mountReturns('book',{views,ui:{$:selector=>selector==='[data-main]'?main:null},labels:{'reader-plan':'Reader plan',history:'Activity'},workspaceReturn,argument:noop,readerHome,manuscript:{editor:()=>null},research:{markReturn(){},clearReturn(){}}});
  const opened=[];
  // the production door handler shape (workspace-manuscript openBoundSource): remember the return place with the
  // action's intent, then leave for the manuscript
  async function onSourceDoor(read,intent){opened.push({file:read.file,sectionId:read.sectionId,intent});returns.remember(intent);current='manuscript';generation++;main.replaceChildren(new Node('div'));}
  return {dom,main,views,returns,opened,setGate:value=>{gate=value;},get place(){return place;},get generation(){return generation;},set current(view){current=view;},get current(){return current;},mount,get controller(){return controller;}};
}
const door=(main,label)=>main.all().find(n=>n.tag==='button'&&n.textContent===label);

for(const precision of ['FILE_ONLY','INFERRED','EXACT_HEADING'])test(precision+': the real source door carries its section/file coordinate, the intent is read before the door is disabled, and Back lands on the painted door again',async()=>{
  const s=shell();
  try{
    s.views.request=owner(precision);await s.mount(s.views.request);
    const open=door(s.main,doorLabel[precision]);assert.ok(open,'the door is rendered');
    assert.equal(open.attrs['data-control'],'reader-plan:open-in-manuscript');assert.equal(open.attrs['data-control-owner'],'book::first::'+FILE);
    s.main.scrollTop=230;
    // the person acts from the door; the harness moves the keyboard elsewhere once the door is disabled, as a browser may
    const elsewhere=new Node('button');s.dom.body.append(elsewhere);
    open.onclick=((real)=>async()=>{const pending=real();elsewhere.focus();return pending;})(open.onclick);
    await open.click();
    assert.equal(s.opened.length,1);assert.equal(s.opened[0].intent.active,open,'the action handed its own control as the intent');
    assert.deepEqual(s.place.focus,{control:'reader-plan:open-in-manuscript',owner:'book::first::'+FILE,heading:'reader-plan:first'},'the remembered place names the door and the section heading above it');
    assert.equal(s.place.scrollTop,230);assert.equal(s.place.view,'reader-plan');
    document.activeElement=document.body;
    await s.returns.back();await flush();
    const again=door(s.main,doorLabel[precision]);
    assert.ok(again&&again!==open,'Back painted a new door');
    assert.equal(document.activeElement,again,'the keyboard is on the painted door');
    assert.equal(s.main.scrollTop,230);assert.equal(s.current,'reader-plan');
  }finally{s.controller?.destroy();s.dom.restore();}
});

test('a Back whose render is overtaken by a later navigation restores nothing in the new context; a refused show keeps the place offered',async()=>{
  const s=shell();
  try{
    s.views.request=owner('FILE_ONLY');await s.mount(s.views.request);
    const open=door(s.main,'Inspect linked file');s.main.scrollTop=180;await open.click();
    assert.ok(s.place);
    // Back starts; its reader-plan render waits; the person goes to History before it settles
    let release;s.setGate(new Promise(resolve=>{release=resolve;}));
    const pending=s.returns.back();
    await flush();assert.equal(s.current,'reader-plan','the show was asked');
    s.current='history';s.main.replaceChildren(new Node('section'));s.main.scrollTop=0;document.activeElement=document.body;
    const later=s.generation;s.views.show=async view=>{s.current=view;return true;};   // the later navigation is its own show
    void later;
    release();await pending;await flush();
    assert.equal(s.current,'history');assert.equal(s.main.scrollTop,0,'the old scroll intent did not apply to the later paint');
    assert.equal(document.activeElement,document.body,'nothing was focused in the new context');
    assert.equal(door(s.main,'Inspect linked file'),undefined,'the overtaken render painted nothing');
    // a refused show: the place is not consumed and nothing is restored
    s.setGate(null);s.current='manuscript';s.main.replaceChildren(new Node('div'));
    await s.mount(s.views.request);s.current='reader-plan';const again=door(s.main,'Inspect linked file');s.main.scrollTop=90;await again.click();
    const kept=s.place;s.views.show=async()=>false;document.activeElement=document.body;s.main.scrollTop=0;
    await s.returns.back();await flush();
    assert.equal(s.place,kept,'the refused Back left its place to be offered again');
    assert.equal(s.main.scrollTop,0);assert.equal(document.activeElement,document.body);
  }finally{s.controller?.destroy();s.dom.restore();}
});

test('a door that is not painted again falls back to the selected section heading; a different section shown restores nothing',async()=>{
  const s=shell();
  try{
    s.views.request=owner('FILE_ONLY');await s.mount(s.views.request);
    const open=door(s.main,'Inspect linked file');await open.click();
    // the plan re-renders without the source read: the exact door is gone, the heading is the domain's own place
    const withoutDoor=copy(fixture.display);withoutDoor.sections[0].source.source_reads=[];
    s.views.request=async url=>{const q=new URL(url,'http://local').searchParams;if(q.get('view')==='summary')return copy(fixture.summary);if(q.get('projection')==='display')return copy(withoutDoor);throw Error('Unexpected read '+url);};
    document.activeElement=document.body;
    await s.returns.back();await flush();
    assert.equal(door(s.main,'Inspect linked file'),undefined);
    const heading=s.main.all().find(n=>n.dataset.focusTarget==='reader-plan:first');
    assert.ok(heading,'the section heading names itself');assert.equal(document.activeElement,heading,'the keyboard lands on the section heading');
    // a Return whose intended section is not the one shown restores nothing
    s.current='manuscript';s.main.replaceChildren(new Node('div'));await s.mount(s.views.request);s.current='reader-plan';
    const head=s.main.all().find(n=>n.dataset.focusTarget==='reader-plan:first');head.focus();s.returns.remember();
    const place=s.place;assert.equal(place.readerPlan.sectionId,'first');
    place.readerPlan={...place.readerPlan,sectionId:'second'};   // the remembered place asks for a section that is not the one shown
document.activeElement=document.body;s.main.scrollTop=0;
    await s.returns.back();await flush();
    assert.equal(document.activeElement,document.body,'another section shown: no focus is moved');
  }finally{s.controller?.destroy();s.dom.restore();}
});

test('a History record action hands its own control as the intent, so the coordinate survives the disabled control and a moved keyboard',async()=>{
  const dom=installDOM(),main=new Node('main');main.dataset.main='';dom.body.append(main);
  try{
    const item={id:'activity:editor-save:save-two',owner:'editor-save',category:'manuscript',at:'2026-09-30T10:08:00Z',actor:{kind:'human',label:'Author'},summary:'Saved chapters/one.tex',status:'saved',
      targets:[{kind:'manuscript',file:'chapters/one.tex',repo_file:'sources/book/chapters/one.tex',binding:'BOUND'}]};
    const request=async path=>{const q=new URL(path,'http://fixture').searchParams;if(q.has('id'))return {item,hashes:[],links:item.targets};return {items:[item],pagination:{offset:0,limit:20,total:1,next_offset:null},coverage:[],limitations:[],as_of:item.at,scope:{file:'chapters/one.tex',repo_file:'sources/book/chapters/one.tex',resolution:'selected-source',continuation:{file:'sources/book/chapters/one.tex',file_scope:'{"names":["chapters/one.tex","sources/book/chapters/one.tex"],"repo_file":"sources/book/chapters/one.tex"}'}}};};
    const received=[];let remembered=null;
    const controller=await mountHistory(main,{project:'book',request,scope:{file:'chapters/one.tex'},onOpenTarget:async(target,intent)=>{received.push(target);
      // the production handler remembers the place with the action's intent while the control is already disabled and the keyboard has moved
      document.activeElement=document.body;remembered=focusCoordinate(main,intent.active);}});
    const toggle=main.all().find(n=>n.tag==='button'&&n.textContent==='Saved chapters/one.tex');await toggle.click();await flush();
    const link=main.all().find(n=>n.attrs['data-control']==='history:open-target');assert.ok(link,'the record action is painted');
    assert.equal(link.attrs['data-control-owner'],'activity:editor-save:save-two::0');
    await link.click();
    assert.equal(received.length,1);assert.deepEqual(remembered,{control:'history:open-target',owner:'activity:editor-save:save-two::0'});
    assert.equal(controller.capture().scope.file,'sources/book/chapters/one.tex','the pane continues with the owner\'s resolved coordinate');assert.equal(controller.capture().scope.file_scope,'{"names":["chapters/one.tex","sources/book/chapters/one.tex"],"repo_file":"sources/book/chapters/one.tex"}','and with the whole first-page basis');
    controller.destroy();
  }finally{dom.restore();}
});
