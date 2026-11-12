// C12 REACHED REPAIR (Root actual holds, 2026-10-15): the task cue's placement, runs, seen steps and outcomes, the
// template inspector observation and the conversation pane's task door. DOM doubles; the journeys are the help
// owner's declarations (tests/fixtures/help/areas.json).
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {installDOM,Node,findButton} from './helpers/evidence_reader_harness.mjs';
import {mountHelp} from '../src/laplace/web/static_shared/workspace-help.mjs';
import {learningStore,journeyRows,journeyStatus,learningKey} from '../src/laplace/web/static_shared/workspace-journeys.mjs';
import {mountGuide,journeySteps as journeyStepsOf,cuePlacement,seenSteps,stepRects} from '../src/laplace/web/static_shared/workspace-guide.mjs';
const AREAS=JSON.parse(await readFile(new URL('./fixtures/help/areas.json',import.meta.url),'utf8'));
const CONTROLS_READ=JSON.parse(await readFile(new URL('./fixtures/help/controls.json',import.meta.url),'utf8'));// wave 13: the overview no longer lists controls; journey steps read their ids from the controls read
const journeySteps=(areas,id,controls=CONTROLS_READ)=>journeyStepsOf(areas,id,controls);
const memory=()=>{const store=new Map();return {store,storage:{getItem:k=>store.get(k)??null,setItem:(k,v)=>store.set(k,v),removeItem:k=>store.delete(k)}};};
const VERSION=AREAS.version+'#orient-manuscript';
const overlap=(box,size,rect)=>box.left<rect.right&&box.left+size.w>rect.left&&box.top<rect.bottom&&box.top+(box.maxHeight?Math.min(size.h,box.maxHeight):size.h)>rect.top;

function shell(){
  const dom=installDOM(),root=new Node('div');root.dataset.view='manuscript';dom.body.append(root);
  const nav=new Node('button');nav.dataset.control='nav:manuscript';const outlineControl=new Node('button');outlineControl.dataset.control='manuscript:outline';
  const outline=new Node('div');outline.dataset.manuscriptOutline='';outline.hidden=true;
  const setup=new Node('details');setup.dataset.control='manuscript:document-setup';root.append(nav,outlineControl,outline,setup);
  const listeners=[];const old={add:globalThis.addEventListener,remove:globalThis.removeEventListener};
  globalThis.addEventListener=(type,fn)=>listeners.push([type,fn]);globalThis.removeEventListener=(type,fn)=>{const at=listeners.findIndex(row=>row[0]===type&&row[1]===fn);if(at>=0)listeners.splice(at,1);};
  globalThis.document.addEventListener=()=>{};globalThis.document.removeEventListener=()=>{};
  const restore=()=>{globalThis.addEventListener=old.add;globalThis.removeEventListener=old.remove;dom.restore();};
  return {dom,root,outline,setup,listeners,restore};
}
const inspectorDialog=dom=>{const dialog=new Node('dialog');dialog.className='document-template-dialog';dialog.open=true;dialog.dataset.inspector='template-setup';dom.body.append(dialog);return dialog;};

test('a modal template inspector seen during its step stays seen after it closes, so the task can be finished',()=>{
  const s=shell();try{
    const {store,storage}=memory(),steps=journeySteps(AREAS,'orient-manuscript');
    storage.setItem(learningKey('book'),JSON.stringify({schema_version:'laplace.learning/1',journeys:{'orient-manuscript':{step:2,closed:false}}}));
    const guide=mountGuide(s.root,{project:'book',steps,journeyId:'orient-manuscript',version:VERSION,storage,page:globalThis.document});
    assert.equal(guide.index,2);assert.equal(findButton(guide.element,'Skip').textContent,'Skip');
    const dialog=inspectorDialog(s.dom);guide.paint();
    assert.equal(guide.element.getAttribute('data-done'),'true');assert.deepEqual(guide.run.seen,['setup']);
    dialog.open=false;dialog.remove();guide.paint();
    assert.equal(guide.element.getAttribute('data-done'),'false');assert.equal(guide.element.getAttribute('data-seen'),'true');
    assert.match(guide.element.textContent,/Seen earlier in this task/);
    findButton(guide.element,'Finish').onclick();
    const entry=JSON.parse(store.get(learningKey('book'))).journeys['orient-manuscript'];
    assert.deepEqual([entry.closed,entry.outcome],[true,'finished']);
    assert.equal(journeyRows(AREAS,'manuscript',learningStore('book',storage))[0].status,'Finished');
  }finally{s.restore();}
});

test('an inspector that was never opened live, or a dialog seen during another step, marks nothing',()=>{
  const s=shell();try{
    const {storage}=memory(),steps=journeySteps(AREAS,'orient-manuscript');
    const guide=mountGuide(s.root,{project:'book',steps,journeyId:'orient-manuscript',version:VERSION,storage,page:globalThis.document});
    const bare=new Node('dialog');bare.className='document-template-dialog';s.dom.body.append(bare);guide.paint();
    assert.deepEqual(guide.run.seen,['open'],'only the current step (Manuscript open) is seen; a bare dialog is not an inspector');
    inspectorDialog(s.dom);guide.paint();assert.ok(!guide.run.seen.includes('setup'),'the setup step is not current, so it is not seen');
    guide.close();
  }finally{s.restore();}
});

test('Stop, Escape and Skip are never Finished; a pre-outcome entry is only "Closed"',()=>{
  assert.equal(journeyStatus({step:2,closed:true,outcome:'stopped'},3),'Stopped at step 3 of 3');
  assert.equal(journeyStatus({step:2,closed:true,outcome:'skipped'},3),'Skipped step 3 of 3');
  assert.equal(journeyStatus({step:2,closed:true},3),'Closed at step 3 of 3','legacy entry: no completion claim');
  assert.equal(journeyStatus({step:2,closed:true,outcome:'finished'},3),'Finished');
  assert.equal(journeyStatus({step:1,closed:false,outcome:'finished'},3),'Step 2 of 3','an open run is in progress whatever an earlier run recorded');
  assert.equal(journeyStatus(null,3),'Not started');
  const s=shell();try{
    const {store,storage}=memory(),steps=journeySteps(AREAS,'orient-manuscript');
    storage.setItem(learningKey('book'),JSON.stringify({schema_version:'laplace.learning/1',journeys:{'orient-manuscript':{step:2,closed:false,mine:'kept'}}}));
    let guide=mountGuide(s.root,{project:'book',steps,journeyId:'orient-manuscript',version:VERSION,storage,page:globalThis.document});
    findButton(guide.element,'Skip').onclick();   // Skip on the last, unseen step
    let entry=JSON.parse(store.get(learningKey('book'))).journeys['orient-manuscript'];
    assert.deepEqual([entry.closed,entry.outcome,entry.mine],[true,'skipped','kept'],'unknown fields survive');
    guide=mountGuide(s.root,{project:'book',steps,journeyId:'orient-manuscript',version:VERSION,storage,page:globalThis.document});
    findButton(guide.element,'Stop').onclick();
    entry=JSON.parse(store.get(learningKey('book'))).journeys['orient-manuscript'];assert.equal(entry.outcome,'stopped');
    assert.equal(journeyRows(AREAS,'manuscript',learningStore('book',storage))[0].status,'Stopped at step 3 of 3');
  }finally{s.restore();}
});

test('runs: a closed run\'s seen steps are never reused; an unclosed run of the same declaration resumes; seen is bounded',()=>{
  const steps=journeySteps(AREAS,'orient-manuscript');
  assert.deepEqual(seenSteps(steps,['setup','open','nope','open']),['open','setup'],'declared ids only, in order, once');
  const s=shell();try{
    const {storage}=memory(),key=learningKey('book');
    const put=entry=>storage.setItem(key,JSON.stringify({schema_version:'laplace.learning/1',journeys:{'orient-manuscript':entry}}));
    put({step:2,closed:true,outcome:'finished',run:{id:'run-old',version:VERSION,seen:['open','outline','setup']}});
    let guide=mountGuide(s.root,{project:'book',steps,journeyId:'orient-manuscript',version:VERSION,storage,page:globalThis.document});
    assert.notEqual(guide.run.id,'run-old');assert.deepEqual(guide.run.seen,[],'a finished run is not new evidence');
    assert.equal(findButton(guide.element,'Skip').textContent,'Skip','its last step must be seen again');guide.close();
    put({step:2,closed:false,run:{id:'run-live',version:VERSION,seen:['open','setup','forged']}});
    guide=mountGuide(s.root,{project:'book',steps,journeyId:'orient-manuscript',version:VERSION,storage,page:globalThis.document});
    assert.deepEqual([guide.run.id,guide.run.seen],['run-live',['open','setup']],'resume: same run, declared ids only');
    assert.ok(findButton(guide.element,'Finish'));guide.close();
    put({step:2,closed:false,run:{id:'run-live',version:'sha256:older#orient-manuscript',seen:['setup']}});
    guide=mountGuide(s.root,{project:'book',steps,journeyId:'orient-manuscript',version:VERSION,storage,page:globalThis.document});
    assert.deepEqual(guide.run.seen,[],'another declaration version starts a new run');guide.close();
  }finally{s.restore();}
});

test('placement keeps the step control and the requested control inside it reachable, at every width',()=>{
  // Root 720x800: Document setup summary above Template & layout (582..710 x 397..431); cue 360x230
  const summary={left:360,top:150,right:712,bottom:182},template={left:582.02,top:397.09,right:709.94,bottom:430.59};
  const panel={left:352,top:150,right:712,bottom:470};
  const size={w:360,h:230};
  const place=cuePlacement(summary,size,{w:720,h:800},[summary,template]);
  assert.ok(![summary,template].some(rect=>overlap(place,size,rect)),JSON.stringify(place));
  // a tall open panel whose controls fill the column: a bounded band, never over a kept control
  const tall=[{left:8,top:60,right:712,bottom:90},{left:8,top:100,right:712,bottom:300},{left:8,top:520,right:712,bottom:560}];
  const band=cuePlacement(tall[0],{w:360,h:400},{w:720,h:800},tall);
  assert.ok(band.maxHeight>=96&&!tall.some(rect=>overlap(band,{w:360,h:400},rect)),JSON.stringify(band));
  // 1280 (Root: the target moves to 1021.91..1149.83): no room to its right, so below it, not over it
  const wide={left:1021.91,top:397,right:1149.83,bottom:431};
  assert.deepEqual(cuePlacement(wide,size,{w:1280,h:800},[wide]),{left:912,top:443});
  assert.ok(!overlap(cuePlacement(wide,size,{w:1280,h:800},[wide]),size,wide));
  void panel;
});

test('the cue moves with the page: a changed target rect re-places it without a repaint; resize/scroll listeners leave with it',()=>{
  const s=shell();const oldRaf=globalThis.requestAnimationFrame,oldW=globalThis.innerWidth,oldH=globalThis.innerHeight;
  globalThis.requestAnimationFrame=fn=>{fn();return 1;};globalThis.innerWidth=720;globalThis.innerHeight=800;
  try{
    const {storage}=memory(),steps=journeySteps(AREAS,'orient-manuscript');
    let rect={left:360,top:150,right:712,bottom:182,width:352,height:32};
    s.setup.getBoundingClientRect=()=>rect;
    storage.setItem(learningKey('book'),JSON.stringify({schema_version:'laplace.learning/1',journeys:{'orient-manuscript':{step:2,closed:false}}}));
    const guide=mountGuide(s.root,{project:'book',steps,journeyId:'orient-manuscript',version:VERSION,storage,page:globalThis.document});
    const before=[guide.element.style.left,guide.element.style.top],paints=guide.paints,placements=guide.placements;
    assert.ok(s.listeners.some(([type])=>type==='resize')&&s.listeners.some(([type])=>type==='scroll'));
    rect={left:1021.91,top:397,right:1149.83,bottom:431,width:128,height:34};globalThis.innerWidth=1280;
    s.listeners.find(([type])=>type==='resize')[1]();
    assert.notDeepEqual([guide.element.style.left,guide.element.style.top],before,'the cue follows the target');
    assert.equal(guide.paints,paints,'no repaint for layout');assert.equal(guide.placements,placements+1);
    s.listeners.find(([type])=>type==='resize')[1]();assert.equal(guide.placements,placements+1,'an unchanged layout writes nothing');
    // a page mutation that changes no step state (Document setup opening) still re-places the cue, without a repaint
    rect={left:360,top:150,right:712,bottom:182,width:352,height:32};globalThis.innerWidth=720;
    guide.observe([{target:s.root,attributeName:'open'}]);
    assert.equal(guide.placements,placements+2,'re-placed on the mutation burst');assert.equal(guide.paints,paints);
    guide.close();
    assert.ok(!s.listeners.some(([type])=>['resize','scroll','laplace-workspace-navigation'].includes(type)),'no listener outlives the cue');
  }finally{globalThis.requestAnimationFrame=oldRaf;globalThis.innerWidth=oldW;globalThis.innerHeight=oldH;s.restore();}
});

test('stepRects anchors an open disclosure at its summary and keeps its visible declared controls clear',()=>{
  const s=shell();try{
    const summary=new Node('summary'),layout=new Node('button');layout.dataset.control='manuscript:template-layout';
    s.setup.append(summary,layout);s.setup.open=true;s.setup.tagName='DETAILS';
    summary.getBoundingClientRect=()=>({left:360,top:150,right:712,bottom:182,width:352,height:32});
    layout.getBoundingClientRect=()=>({left:582,top:397,right:710,bottom:431,width:128,height:34});
    s.setup.getBoundingClientRect=()=>({left:352,top:150,right:712,bottom:470,width:360,height:320});
    const {anchor,keep}=stepRects(s.setup);
    assert.equal(anchor.top,150);assert.equal(anchor.bottom,182,'the summary, not the whole tall panel');
    assert.deepEqual(keep.map(rect=>rect.top),[150,397],'Template & layout is kept clear');
  }finally{s.restore();}
});

test('Help lists the conversation pane\'s declared task in every view and starts it',async()=>{
  const dom=installDOM(),main=new Node('main');dom.body.append(main);
  try{
    const {storage}=memory(),started=[];
    const help=mountHelp(main,{project:'book',areas:AREAS,view:'manuscript',store:learningStore('book',storage),onJourney:id=>started.push(id)});
    assert.match(help.element.textContent,/In the conversation pane/);
    const row=findButton(help.element,'See what a message will carry');assert.ok(row,'the declared conversation task is reachable');
    assert.equal(row.dataset.journey,'what-a-message-carries');await row.onclick();assert.deepEqual(started,['what-a-message-carries']);
    assert.ok(findButton(help.element,'Find your place in the manuscript'),'the view\'s own task stays first');
    help.close();
  }finally{dom.restore();}
});

// C12 RESIDUAL R5 (Sol, 2026-10-15): no unchecked fallback. Every returned box is inside the viewport and covers no
// kept control; with too little room the cue is compact, with none it is withheld; nothing acts for the person.
const covers=(box,size,rects)=>rects.some(rect=>overlap(box,size,rect));
test('no-fit: compact in a narrow free band, withheld with none, never over a requested control',()=>{
  const size={w:360,h:230};
  // Sol's witness: 720x180 with two full-width controls; the free bands are 16 and 36 px
  const sol=[{left:8,right:712,top:18,bottom:50},{left:8,right:712,top:90,bottom:124}];
  assert.deepEqual(cuePlacement(sol[0],size,{w:720,h:180},sol),{withheld:true});
  // a 50 px free band: the compact cue, inside it
  const two=[{left:8,right:712,top:18,bottom:50},{left:8,right:712,top:124,bottom:150}];
  const compact=cuePlacement(two[0],size,{w:720,h:200},two);
  assert.equal(compact.compact,true);assert.equal(compact.maxHeight,44);
  assert.ok(!covers(compact,{w:360,h:compact.maxHeight},two)&&compact.top>=8&&compact.top+44<=200-8,JSON.stringify(compact));
  // the target scrolled partly above the viewport
  const scrolled={left:300,right:640,top:-20,bottom:12};
  const placed=cuePlacement(scrolled,{w:360,h:160},{w:720,h:400},[scrolled]);
  assert.ok(!covers(placed,{w:360,h:placed.maxHeight||160},[scrolled]),JSON.stringify(placed));
});

test('property: over many seeded layouts no returned box leaves the viewport or covers a kept control',()=>{
  let seed=7;const rnd=()=>{seed=(seed*1103515245+12345)%2147483648;return seed/2147483648;};
  let withheld=0,compact=0,band=0,beside=0;
  for(let n=0;n<2000;n++){
    const viewport={w:320+Math.floor(rnd()*1200),h:120+Math.floor(rnd()*800)},size={w:360,h:80+Math.floor(rnd()*260)};
    const rects=Array.from({length:1+Math.floor(rnd()*5)},()=>{const left=Math.floor(rnd()*viewport.w),top=Math.floor(rnd()*viewport.h)-40;return {left,top,right:left+20+Math.floor(rnd()*viewport.w),bottom:top+12+Math.floor(rnd()*160)};});
    const where=cuePlacement(rects[0],size,viewport,rects);
    if(where.withheld){withheld++;continue;}
    const height=where.compact?44:where.maxHeight?Math.min(size.h,where.maxHeight):size.h;
    where.compact?compact++:where.maxHeight?band++:beside++;
    assert.ok(where.left>=0&&where.top>=0&&where.top+height<=viewport.h,JSON.stringify({where,viewport,size}));
    assert.ok(!covers(where,{w:Math.min(size.w,viewport.w),h:height},rects),JSON.stringify({where,rects,viewport,size}));
  }
  assert.ok(withheld>0&&compact>0&&band>0&&beside>0,JSON.stringify({withheld,compact,band,beside}));
});

test('the live cue becomes compact, then withheld, then returns as the layout changes; it never acts',()=>{
  const s=shell();const oldRaf=globalThis.requestAnimationFrame,oldW=globalThis.innerWidth,oldH=globalThis.innerHeight;
  globalThis.requestAnimationFrame=fn=>{fn();return 1;};globalThis.innerWidth=720;globalThis.innerHeight=200;
  try{
    const {storage}=memory(),steps=journeySteps(AREAS,'orient-manuscript');
    storage.setItem(learningKey('book'),JSON.stringify({schema_version:'laplace.learning/1',journeys:{'orient-manuscript':{step:2,closed:false}}}));
    let rect={left:8,top:18,right:712,bottom:50,width:704,height:32};s.setup.getBoundingClientRect=()=>rect;
    const inner=new Node('button');inner.dataset.control='manuscript:template-layout';s.setup.append(inner);let innerRect={left:8,top:124,right:712,bottom:150,width:704,height:26};inner.getBoundingClientRect=()=>innerRect;
    let clicked=0;inner.onclick=()=>clicked++;
    const guide=mountGuide(s.root,{project:'book',steps,journeyId:'orient-manuscript',version:VERSION,storage,page:globalThis.document});
    assert.equal(guide.element.getAttribute('data-disposition'),'compact');assert.ok(guide.element.classList.contains('is-compact'));assert.equal(guide.element.hidden,false);
    innerRect={left:8,top:90,right:712,bottom:124,width:704,height:34};globalThis.innerHeight=180;s.listeners.find(([type])=>type==='resize')[1]();
    assert.equal(guide.element.getAttribute('data-disposition'),'withheld');assert.equal(guide.element.hidden,true);
    globalThis.innerHeight=800;s.listeners.find(([type])=>type==='resize')[1]();
    assert.equal(guide.element.hidden,false);assert.ok(!guide.element.classList.contains('is-compact'));assert.notEqual(guide.element.getAttribute('data-disposition'),'withheld');
    assert.equal(clicked,0,'the cue never clicks the requested control');
    guide.close();
  }finally{globalThis.requestAnimationFrame=oldRaf;globalThis.innerWidth=oldW;globalThis.innerHeight=oldH;s.restore();}
});
