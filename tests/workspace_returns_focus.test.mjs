// M5-I2 / M5-I3 (2026-10-20): the shell's Back restores the keyboard to the control it was on, by its
// coordinate (data-control + data-control-owner) and never by an element kept across the view change;
// only an explicit Back whose load generation still stands focuses anything. The Document outline
// button drives the outline CONTROLLER the shell passes in; its host element is only where it paints.
// The drawer geometry is keyed to data-nav-layout, the shell's one width decision (navLayout).
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {register} from 'node:module';
register(new URL('./helpers/shared_resolve.mjs',import.meta.url));
import {installHTMLDocument,Element} from './helpers/html_dom.mjs';
const {focusCoordinate,focusTarget,mountReturns}=await import('../src/laplace/web/static_shared/workspace-returns.mjs');
const {mountChrome,navLayout,NAV_LABELS}=await import('../src/laplace/web/static_shared/workspace-chrome.mjs');
const css=await readFile(new URL('../src/laplace/web/static_shared/workspace.css',import.meta.url),'utf8');
const el=(tag,attrs={},text='')=>{const node=document.createElement(tag);for(const [key,value] of Object.entries(attrs))node.setAttribute(key,value);if(text)node.textContent=text;return node;};
const flush=()=>new Promise(resolve=>setTimeout(resolve,5));

test('a focus coordinate names the control, not the element: it is found again in a new paint, never outside main, never when ambiguous',()=>{
  const dom=installHTMLDocument();
  try{
    const main=el('main',{'data-main':''});document.body.append(main);
    const head=el('button',{'data-control':'reader-plan:unit-select','data-control-owner':'book::first::first-p2'});const label=el('span',{},'Point');head.append(label);main.append(head);
    label.focus?.();document.activeElement=label;
    assert.deepEqual(focusCoordinate(main),{control:'reader-plan:unit-select',owner:'book::first::first-p2'},'the coordinate is read from the nearest control around the focused node');
    const outside=el('button',{'data-control':'nav:history'});document.body.append(outside);document.activeElement=outside;
    assert.equal(focusCoordinate(main),null,'a control outside main is no reader place');
    document.activeElement=main;assert.equal(focusCoordinate(main),null);
    // a new paint: the same unit by its coordinate, a different element
    main.replaceChildren();const again=el('button',{'data-control':'reader-plan:unit-select','data-control-owner':'book::first::first-p2'});main.append(again);
    assert.equal(focusTarget(main,{control:'reader-plan:unit-select',owner:'book::first::first-p2'}),again);
    assert.equal(focusTarget(main,{control:'reader-plan:unit-select',owner:'book::first::first-p1'}),null,'another unit is another coordinate');
    assert.equal(focusTarget(main,{control:'reader-plan:unit-select'}),null,'the owner is part of the coordinate');
    main.append(el('button',{'data-control':'reader-plan:unit-select','data-control-owner':'book::first::first-p2'}));
    assert.equal(focusTarget(main,{control:'reader-plan:unit-select',owner:'book::first::first-p2'}),null,'two elements at one coordinate: no target');
    main.replaceChildren();const gone=el('button',{'data-control':'history:open-target','data-control-owner':'activity:editor-save:one::0',hidden:''});main.append(gone);
    assert.equal(focusTarget(main,{control:'history:open-target',owner:'activity:editor-save:one::0'}),null,'a hidden control is not focused');
  }finally{dom.restore();}
});

test('Back restores the remembered focus after the view rendered, in the generation that asked, and a moved generation restores nothing',async()=>{
  const dom=installHTMLDocument();
  try{
    const main=el('main',{'data-main':''});document.body.append(main);main.scrollTop=0;
    const draft=el('textarea',{'data-composer':''});draft.value='an unsent reply';document.body.append(draft);
    let generation=1,current='history';const shown=[];
    const paint=()=>{main.replaceChildren();const record=el('article',{'data-control':'history:entry'});const action=el('button',{'data-control':'history:open-target','data-control-owner':'activity:editor-save:save-two::0'},'Open chapters/one.tex');record.append(action);main.append(record);return action;};
    const first=paint();first.focus();main.scrollTop=140;
    const views={current:()=>current,show:async(view)=>{shown.push(view);current=view;generation++;paint();return true;},generation:()=>generation,setMode(){}};
    const noop={captureSurface:()=>({}),restoreSurface(){},returnPlace:()=>({view:'argument',label:'Argument'}),restoreQuery(){}};
    let place=null;const workspaceReturn={get current(){return place;},remember(value){if(!place)place=value;return place;},take(){const value=place;place=null;return value;},clear(){place=null;}};
    const returns=mountReturns('book',{views,ui:{$:selector=>document.querySelector(selector)},labels:{history:'Activity'},workspaceReturn,argument:noop,
      readerHome:{capture:()=>null,restore(){},context:()=>null},manuscript:{editor:()=>null},research:{markReturn(){},clearReturn(){}}});
    returns.remember();
    assert.equal(place.view,'history');assert.equal(place.scrollTop,140);
    assert.deepEqual(place.focus,{control:'history:open-target',owner:'activity:editor-save:save-two::0'},'the return place carries the focus coordinate, not the element');
    // the door opened another view; its paint moved the keyboard elsewhere
    current='manuscript';main.replaceChildren(el('div',{},'manuscript'));document.activeElement=document.body;
    await returns.back();await flush();
    assert.deepEqual(shown,['history']);
    const restored=main.querySelector('[data-control="history:open-target"]');
    assert.notEqual(restored,first,'the new paint made a new element');
    assert.equal(document.activeElement,restored,'the keyboard is on the connected record action again');
    assert.equal(main.scrollTop,140);assert.equal(draft.value,'an unsent reply','an unsent draft is untouched by Back');
    assert.equal(place,null,'the return place was consumed');
    // a stale restore: the generation moved on after Back asked
    const again=main.querySelector('[data-control="history:open-target"]');again.focus();returns.remember();
    current='manuscript';document.activeElement=document.body;
    const late=returns.restore({...workspaceReturn.take(),focus:{control:'history:open-target',owner:'activity:editor-save:save-two::0'}});
    generation++;await late;await flush();
    assert.equal(document.activeElement,document.body,'a restore whose generation moved on focuses nothing');
  }finally{dom.restore();}
});

test('the Document outline button renders through the outline controller the shell passes in; the host element is only where it paints',async()=>{
  const dom=installHTMLDocument({width:1280});
  try{
    const root=el('div',{class:'workspace'});document.body.append(root);
    const nav=el('nav',{class:'workspace-nav'});root.append(nav);
    for(const name of ['data-nav','data-focus','data-talk','data-guide','data-session'])root.append(el(name==='data-session'?'aside':'button',{[name]:''}));
    const ui={root,$:selector=>root.querySelector(selector),button:(label,run)=>{const b=el('button',{},label);b.onclick=run;return b;}};
    let current='overview';const shown=[],rendered=[];
    const views={current:()=>current,show:async view=>{shown.push(view);current=view;return true;},info:()=>({capabilities:{manuscript:true,work:true,materials:true,history:true,settings:true}})};
    const session={catalogueOpened(){},setLibrary(){},expand(){}};
    const outline={render:async refresh=>{rendered.push(refresh);}};
    mountChrome('book',{views,ui,discussion:{session:()=>session},help:{followLayout(){}},initialQuery:new URLSearchParams(''),pageListen(){},outline});
    const host=nav.querySelector('[data-manuscript-outline]'),control=nav.querySelector('[data-document-outline-control]');
    assert.ok(host&&control,'the host and the button are in the navigation');
    assert.equal(host.localName,'div');assert.equal(typeof host.render,'undefined','the host is an element; it renders nothing itself');
    assert.equal(host.hidden,true);
    await control.onclick();
    assert.deepEqual(shown,['manuscript'],'the button first shows the Manuscript view');
    assert.deepEqual(rendered,[true],'then asks the real controller for a refreshed outline');
    assert.equal(host.hidden,false);
    // a refused view change (a dirty form kept the person where they were) renders nothing
    views.show=async()=>{return false;};current='overview';host.hidden=true;
    await control.onclick();
    assert.deepEqual(rendered,[true]);assert.equal(host.hidden,true,'no outline is shown for a view that did not open');
    assert.equal(NAV_LABELS.find(([id])=>id==='manuscript')[1],'Manuscript');
  }finally{dom.restore();}
});

test('one width boundary: navLayout decides 719/720/721/1000 and the drawer geometry is keyed to data-nav-layout, not to a second 720 media query',()=>{
  assert.deepEqual([719,720,721,1000,1050,1051].map(navLayout),['drawer','compact','compact','compact','compact','fixed']);
  // every @media(max-width:720px) block that remains touches no layout geometry of the nav, the grid or the conversation column
  const blocks=[...css.matchAll(/@media\(max-width:720px\)\{((?:[^{}]*\{[^{}]*\})*)\}/g)].map(m=>m[1]);
  assert.ok(blocks.length>=1,'narrow-width typography rules remain');
  for(const block of blocks)for(const needle of ['.workspace-nav{','.workspace-layout{','.workspace-layout,','.workspace-session{','.workspace-nav{top'])
    assert.ok(!block.includes(needle),'no 720 media rule positions the nav, the grid or the conversation column: '+block.slice(0,80));
  assert.ok(!/@media\(max-width:720px\)\{[^}]*\.workspace-nav\{/.test(css));
  // the drawer rules: the nav is absolute inside the layout (its containing block), the grid is one column, the conversation overlays
  assert.match(css,/\.workspace\[data-nav-layout="drawer"\] \.workspace-nav\{position:absolute;top:0;left:0;bottom:0;width:min\(86vw,260px\);z-index:5/);
  assert.match(css,/\.workspace\[data-nav-layout="drawer"\] \.workspace-layout,\.workspace\[data-nav-layout="drawer"\]\.session-open \.workspace-layout\{grid-template-columns:minmax\(0,1fr\)\}/);
  assert.match(css,/\.workspace\[data-nav-layout="drawer"\]\.session-open \.workspace-session\{position:absolute;inset:0;z-index:6/);
  assert.match(css,/\.workspace\[data-nav-layout="drawer"\]\[data-view="manuscript"\] \.workspace-nav\{width:min\(86vw,290px\)\}/);
  assert.match(css,/\.workspace-layout\{position:relative\}/);
  assert.equal((css.match(/\.workspace-header h1\{font-size:var\(--fs-body\)\}/g)||[]).length,1,'one drawer heading size, under the drawer layout: the where-am-I line at the body size (wave 4 type scale)');
  // the compact layout at exactly 720 keeps its nav column (the 1050 block governs ≤1050 and agrees with navLayout's compact bound)
  assert.match(css,/@media\(max-width:1050px\)\{\.workspace\.session-open \.workspace-layout\{grid-template-columns:minmax\(0,1fr\) var\(--session-width,440px\)\}/);
});
