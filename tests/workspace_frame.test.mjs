// Wave 9 frame (workspace-frame.mjs) and Now (workspace-now.mjs) over the markup DOM double: no browser geometry claim
// (the geometry is measured by the wave 9 shell scenario in a real browser).
import {register} from 'node:module';register(new URL('./helpers/shared_resolve.mjs',import.meta.url));
import {test} from 'node:test';
import assert from 'node:assert/strict';
const {installHTMLDocument}=await import('./helpers/html_dom.mjs');
const {mountFrame,orderByRecent,switchDestination,rememberProject,recentProjects,RECENT_KEY,PLACES,MORE}=await import('../src/laplace/web/static_shared/workspace-frame.mjs');
const {activeWorkRow,mountNow}=await import('../src/laplace/web/static_shared/workspace-now.mjs');
const text=node=>(node?.textContent||'').trim();
const links=bar=>bar.querySelectorAll('a').map(a=>[text(a),new URL(a.href,'http://local').searchParams.get('app')]);

test('the recent order: most recently opened first, then the library order; at most 24 remembered under one laplace: key',()=>{
  const store=new Map(),storage={getItem:k=>store.get(k)??null,setItem:(k,v)=>store.set(k,v)};
  rememberProject('b',storage,1);rememberProject('c',storage,2);rememberProject('b',storage,3);
  assert.equal(RECENT_KEY,'laplace:frame:recent-projects');
  assert.deepEqual(recentProjects(storage).map(r=>r.name),['b','c']);
  assert.deepEqual(orderByRecent([{name:'a'},{name:'b'},{name:'c'},{name:'d'}],recentProjects(storage)).map(r=>r.name),['b','c','a','d']);
  for(let i=0;i<30;i++)rememberProject('p'+i,storage,10+i);assert.equal(recentProjects(storage).length,24);
  assert.deepEqual(recentProjects({getItem:()=>'not json'}),[]);
});

test('choosing a project opens the same kind of page there: Tasks to Tasks, Writing only where a manuscript exists, otherwise Home',()=>{
  const q=href=>new URL(href,'http://local').searchParams;
  assert.equal(q(switchDestination({name:'b'},{view:'work'})).get('view'),'work');
  assert.equal(q(switchDestination({name:'b'},{view:'manuscript'})).get('view'),'manuscript');
  assert.equal(q(switchDestination({name:'b',source_optional:true},{view:'manuscript'})).get('view'),'overview');
  assert.equal(q(switchDestination({name:'b'},{})).get('view'),'overview');
  assert.equal(q(switchDestination({name:'b c'},{view:'work'})).get('corpus'),'b c');
});

test('a workspace page: Now, the switcher, the four places, Help slot and More with its four pages; the place is marked',()=>{
  const env=installHTMLDocument({width:1440});try{
    location.href='http://local/project?workspace=writing&app=backlog';
    const frame=mountFrame({place:'backlog',request:async()=>({projects:[]}),skip:true});document.body.append(frame.bar);
    const places=frame.bar.querySelector('.frame-places').querySelectorAll('a.frame-place');
    assert.deepEqual(places.map(text),PLACES.map(([,label])=>label));
    assert.deepEqual(places.map(a=>a.getAttribute('aria-current')),[null,null,'page',null,null]);
    assert.equal(places[2].getAttribute('data-control'),'nav:backlog','the global entry keeps the declared Tasks identity');
    assert.equal(text(frame.bar.querySelector('.frame-switch-title')),'Choose a project');
    assert.equal(text(frame.bar.querySelector('.frame-more>summary')),'More');
    assert.deepEqual(frame.bar.querySelector('.frame-more-list').querySelectorAll('a').map(text),MORE.map(([,label])=>label));
    assert.equal(frame.bar.querySelector('[data-control="nav:skip"]')?.textContent,'Skip to content');
    assert.ok(frame.helpSlot&&frame.bar.contains(frame.helpSlot));
    assert.equal(frame.bar.querySelector('[data-talk]'),null,'no Conversation without a project');
    assert.ok(links(frame.bar).some(([label,app])=>label==='App settings'&&app==='settings'));
  }finally{env.restore();}
});

test('inside a project the bar takes the shell\'s own Help, Conversation and Workspace menu identity; the title follows the project',()=>{
  const env=installHTMLDocument({width:1440});try{
    const shell=document.createElement('div');shell.innerHTML='<details data-workspace-menu data-control="workspace:menu"><summary>Workspace</summary><div class="workspace-menu-list"></div></details><button data-guide data-control="help:guide">Help</button><button data-talk data-control="conversation:toggle">Conversation</button>';document.body.append(shell);
    const guide=shell.querySelector('[data-guide]'),talk=shell.querySelector('[data-talk]');
    const frame=mountFrame({project:'book',title:'book',request:async()=>({projects:[]}),more:shell.querySelector('[data-workspace-menu]'),guide,conversation:talk});shell.prepend(frame.bar);
    assert.equal(frame.bar.querySelector('[data-guide]'),guide,'the same Help button, moved');assert.equal(frame.bar.querySelector('[data-talk]'),talk,'the same Conversation button, moved');
    const more=frame.bar.querySelector('[data-control="workspace:menu"]');assert.ok(more);assert.equal(text(more.querySelector('summary')),'More');
    assert.equal(shell.querySelectorAll('[data-control="workspace:menu"]').length,1,'one Workspace menu identity');
    assert.equal(frame.bar.querySelector('[data-control="nav:backlog"]'),null,'inside a project the Tasks link is not the declared project-tools control');
    frame.setTitle('Fixture Book');assert.equal(text(frame.bar.querySelector('.frame-switch-title')),'Fixture Book');assert.equal(frame.switcher.getAttribute('aria-current'),'true');
    assert.equal(recentProjects()[0].name,'book','opening a project page remembers it for this viewer');
    const rail=frame.railPlaces(()=>{});assert.deepEqual(rail.querySelectorAll('a').map(text),[...PLACES,...MORE].map(([,label])=>label));
  }finally{env.restore();}
});

test('the switcher reads the library once, lists recent projects first and filters by title',async()=>{
  const env=installHTMLDocument({width:1440});try{
    location.href='http://local/project?workspace=writing&corpus=b&view=work';
    rememberProject('c');rememberProject('b');let reads=0;
    const frame=mountFrame({project:'b',title:'Beta',request:async path=>{reads++;assert.equal(path,'/projects/library');return {projects:[{name:'a',title:'Alpha'},{name:'b',title:'Beta'},{name:'c',title:'Gamma',source_optional:true}]};}});document.body.append(frame.bar);
    await frame.openSwitcher();
    const rows=()=>frame.panel.querySelectorAll('a.frame-switch-row');
    assert.deepEqual(rows().map(a=>text(a.querySelector('.frame-switch-row-title'))),['Beta','Gamma','Alpha']);
    assert.equal(rows()[0].getAttribute('aria-current'),'page');
    assert.equal(new URL(rows()[1].href,'http://local').searchParams.get('view'),'work','Tasks to Tasks');
    const find=frame.panel.querySelector('input');find.value='alp';find.oninput();assert.deepEqual(rows().map(a=>text(a.querySelector('.frame-switch-row-title'))),['Alpha']);
    frame.closeSwitcher();await frame.openSwitcher();assert.equal(reads,1);
    assert.deepEqual(frame.panel.querySelector('.frame-switch-foot').querySelectorAll('a').map(text),['All projects','Create a project']);
  }finally{env.restore();}
});

test('an active_work row says what it is, its state word and opens its conversation; nothing else is invented',()=>{
  const turn=activeWorkRow({kind:'turn',project:'garden',session_id:'WS-1',turn_id:'WT-1',label:'Compare the pots',provider:'claude'});
  assert.equal(turn.state,'Running');assert.equal(turn.open,'Open conversation');assert.equal(turn.label,'Compare the pots');
  const q=new URL(turn.href,'http://local').searchParams;assert.equal(q.get('session'),'WS-1');assert.equal(q.get('conversation'),'open');assert.equal(q.get('corpus'),'garden');
  assert.equal(activeWorkRow({kind:'turn-start',project:'g'}).state,'Starting');
  assert.equal(new URL(activeWorkRow({kind:'research-run',project:'g',run_id:'R1',state:'RUNNING'}).href,'http://local').searchParams.get('view'),'research');
  assert.equal(activeWorkRow({kind:'turn'}).href,null,'no project, no link');
});

test('Now: running work from the owner read with its time, waiting tasks from the catalogue, recent projects, start; nothing running is one line',async()=>{
  const env=installHTMLDocument({width:1440});try{
    const root=document.createElement('section');root.id='project-work';document.body.append(root);
    let active=[{kind:'turn',project:'garden',session_id:'WS-1',turn_id:'WT-1',label:'Compare the pots',provider:'claude'}];const calls=[];
    const request=async path=>{calls.push(path);const u=new URL(path,'http://local');
      if(u.pathname==='/projects/library')return {projects:[{name:'garden',title:'Garden watering study'},{name:'notes',title:'Notes',source_optional:true}]};
      if(u.pathname==='/authoring/health')return {active_work:active,active_work_omitted:0};
      if(u.searchParams.get('currentness')==='REVIEW_REQUIRED')return {coverage:{matching_work:1},rows:[{namespace:'garden',id:'W1',title:'Compare the notes',lifecycle:{status:'done',completed:true,closed:true},current_acceptance:{status:'REVIEW_REQUIRED',review_required:true}}]};
      return {coverage:{matching_work:3},rows:[],suggested_next:{state:'SUGGESTED',namespace:'garden',id:'W2',title:'Observe both pots'}};};
    const now=await mountNow(root,{request,interval:0});
    const groups=root.querySelectorAll('.now-group');assert.deepEqual(groups.map(g=>text(g.querySelector('h2'))),['Running now','Waiting for you','Continue','Start']);
    const running=groups[0];assert.match(text(running),/Compare the pots/);assert.match(text(running),/Running · Garden watering study · claude · first seen /);assert.match(text(running.querySelector('.now-read')),/^Read at .* from the engine’s live work\.$/);
    assert.match(text(groups[1]),/1 completed task needs current review across all projects\./);assert.match(text(groups[1]),/Completed — evidence needs rechecking/);assert.match(text(groups[1]),/Suggested next to inspect/);
    assert.ok(calls.includes('/work/state?view=catalogue&currentness=REVIEW_REQUIRED&limit=5'));
    const cont=groups[2].querySelectorAll('.now-row-project');assert.equal(cont.length,2);assert.deepEqual(cont[0].querySelectorAll('.now-row-actions a').map(text),['Continue writing','Tasks','Open']);assert.deepEqual(cont[1].querySelectorAll('.now-row-actions a').map(text),['Tasks','Open'],'no Continue writing without a manuscript');
    assert.ok(root.querySelector('.pw-library'),'the desktop readiness selector is on the page the app opens on');
    assert.deepEqual(groups[3].querySelectorAll('a').map(a=>new URL(a.href,'http://local').searchParams.get('start')),['create','existing']);
    active=[];await now.refresh();assert.equal(running.querySelectorAll('.now-row').length,0);assert.match(text(running.querySelector('.now-read')),/^Nothing is running in any project\. Read at /);
    now.destroy();
  }finally{env.restore();}
});

test('on one of More\'s pages the bar names it after More and marks More as the current place',()=>{
  const env=installHTMLDocument({width:1440});try{location.href='http://local/project?workspace=writing&app=settings';
    const frame=mountFrame({place:'settings',request:async()=>({projects:[]})});const summary=frame.bar.querySelector('.frame-more>summary');
    assert.equal(summary.getAttribute('aria-current'),'page');assert.equal(text(summary.querySelector('.frame-more-current')),'App settings');
    assert.equal(frame.bar.querySelectorAll('a.frame-place').filter(a=>a.getAttribute('aria-current')).length,0);
  }finally{env.restore();}
});

// Wave 11 census repair R6 (R5): the workspace place lists tasks across every project and is called 'All tasks'; a
// project's own page keeps 'Tasks'. Control ids do not change.
test('wave 11 R6: the workspace place is All tasks in the bar and the narrow menu; nav:backlog keeps its identity',()=>{
  const env=installHTMLDocument({width:1440});try{
    location.href='http://local/project?workspace=writing&app=now';
    assert.deepEqual(PLACES.find(([id])=>id==='backlog'),['backlog','All tasks']);
    const frame=mountFrame({place:'now',request:async()=>({projects:[]}),skip:true});document.body.append(frame.bar);
    const tasks=frame.bar.querySelector('.frame-places').querySelectorAll('a.frame-place').find(a=>a.getAttribute('data-place')==='backlog');
    assert.equal(text(tasks),'All tasks');assert.equal(tasks.getAttribute('data-control'),'nav:backlog');
    assert.ok(frame.bar.querySelectorAll('.frame-menu-panel a').map(text).includes('All tasks'));
  }finally{env.restore();}
});
