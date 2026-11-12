// Task-first landing and the existing deliberate Help deep-link bridge.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {Node,installDOM} from './helpers/evidence_reader_harness.mjs';

import {declareControl} from '../src/laplace/web/static_shared/workspace-presentation.mjs';
const source=await readFile(new URL('../src/laplace/web/static_shared/project-work.mjs',import.meta.url),'utf8');
const block=source.slice(source.indexOf('// PROJECTS LANDING:BEGIN'),source.indexOf('// PROJECTS LANDING:END')).replace('export function groupProjects','function groupProjects');
const landing=new Function('declareControl',block+'\nreturn {groupProjects,renderProjectLanding,START_HERE,PROJECT_GROUPS};')(declareControl);
const E=(tag,text='',cls='')=>{const node=document.createElement(tag);node.textContent=text;node.className=cls;return node;};
const MIRROR=['synthetics-foundations','eigen-technical-due-diligence-briefing','writing-system-architecture','cost-of-complexity','law-of-laws',
  'synthetics-statistical-lawhood','adaptive-normal-form-aek9','the-phases-of-hierarchy','operatorial-loss','variational-wrong-object','qde',
  'free-snacks','self-consistent-loss-geometries','self-consistent-loss-geometries-coupled-evaluators','corpus-as-a-state','memory-in-pieces',
  'superarc','equilibrium-from-the-inside-out','dual-representatives-of-mean-force-equilibrium','ground-states-mean-force-and-thermal-geometry',
  'a-little-fun-never-hurt-anybody'];
const row=(name,extra={})=>({name,title:'Title of '+name,status:'resolved',...extra});
function mount(projects){
  const host=new Node('main');globalThis.document.body.append(host);
  const controller=landing.renderProjectLanding(host,{projects},E);
  const featured=host.all().filter(n=>n.className==='pw-feature');
  const groups=host.all().filter(n=>n.className==='pw-group').map(n=>({title:n.children[0].textContent,cards:n.all().filter(c=>c.className==='pw-project')}));
  return {host,controller,featured,groups,text:()=>host.textContent};
}
const names=cards=>cards.map(card=>new URL(card.href,'http://local').searchParams.get('corpus'));

test('task-first landing lists each actual project once and searches across all returned identities',()=>{
 const dom=installDOM();try{
  const {host,controller,text}=mount(MIRROR.map(name=>row(name)));
  assert.equal(host.all().filter(n=>n.tag==='a').length,21);assert.deepEqual(names(host.all().filter(n=>n.tag==='a')).sort(),[...MIRROR].sort());
  controller.query.value='mean-force';controller.paint();assert.deepEqual(names(host.all().filter(n=>n.tag==='a')),['dual-representatives-of-mean-force-equilibrium','ground-states-mean-force-and-thermal-geometry']);assert.match(text(),/2 of 21 projects/);
  controller.query.value='zzz-nothing';controller.paint();assert.match(text(),/No project matches this search/);assert.equal(host.all().filter(n=>n.tag==='a').length,0);
  controller.query.value='';controller.paint();assert.equal(host.all().filter(n=>n.tag==='a').length,21);
 }finally{dom.restore();}
});
test('missing and failed projects are not silently represented as successful writing',()=>{
 const dom=installDOM();try{const {host,text}=mount([row('public',{creation:{status:'failed'}})]);assert.match(text(),/Creation needs attention/);assert.deepEqual(names(host.all().filter(n=>n.tag==='a')),['public']);assert.ok(!text().includes('synthetics-foundations'));}finally{dom.restore();}
});

test('rows are one line each: the whole title is in the title attribute, there is no card heading or per-row sentence, and the count and caption sit with the filter',()=>{
 const dom=installDOM();try{
  const long='There Is Only One Thing: Conjugate Representations in a Machine That Organises Knowledge';
  const {host,controller,text}=mount([row('a',{title:long}),row('b',{title:'Short'}),row('c',{title:''})]);
  const links=host.all().filter(n=>n.tag==='a');
  assert.deepEqual(links.map(n=>n.getAttribute('title')),[long,'Short','c']);
  assert.deepEqual(links.map(n=>n.children.map(c=>c.className)),[['pw-project-title'],['pw-project-title'],['pw-project-title']]);
  assert.ok(!host.all().some(n=>n.tag==='h3'),'no card headings');
  assert.match(text(),/3 of 3 projects/);assert.match(text(),/Clicking a project below:/);
  controller.query.value='short';controller.paint();assert.match(text(),/1 of 3 projects/);
  assert.deepEqual(['Start writing','Read a source','Organise tasks','Open existing project'].map(label=>host.all().some(n=>n.tag==='button'&&n.textContent===label)),[true,true,true,true],'the four live labels are untouched');
 }finally{dom.restore();}
});
test('under Start writing every row says Continue writing or Open project and add writing in the base words, in the row after its title; the chosen choice is marked by aria-pressed',()=>{
 const dom=installDOM();try{
  const {host}=mount([row('a',{source_optional:true}),row('b'),row('c',{creation:{status:'failed'}})]);
  const choose=label=>host.all().find(n=>n.tag==='button'&&n.textContent===label);
  const notes=()=>host.all().filter(n=>n.className.includes('pw-project-note')).map(n=>n.textContent);
  const lines=()=>host.all().filter(n=>n.tag==='a').map(a=>a.children.map(c=>c.className.split(' ').pop()));
  assert.deepEqual(notes(),[]);choose('Start writing').onclick();assert.deepEqual(notes(),['Open project and add writing','Continue writing','Continue writing']);
  assert.deepEqual(lines()[0],['pw-project-title','pw-project-note'],'title and note share the row');assert.deepEqual(lines()[2],['pw-project-title','pw-project-note','pw-project-alert']);
  assert.equal(choose('Start writing').getAttribute('aria-pressed'),'true');assert.equal(choose('Open existing project').getAttribute('aria-pressed'),'false');
  choose('Read a source').onclick();assert.deepEqual(notes(),[]);
 }finally{dom.restore();}
});
test('Create a project sits beside the filter and opens the create form in place; with no projects the form is already open',()=>{
 const dom=installDOM();try{
  const host=new Node('main');globalThis.document.body.append(host);const calls=[];
  const landingA=landing.renderProjectLanding(host,{projects:[row('a')]},E,{onCreate:id=>calls.push(id)});
  assert.equal(landingA.slot.hidden,true);assert.equal(landingA.create.textContent,'Create a project');
  landingA.create.onclick();assert.equal(landingA.slot.hidden,false);assert.equal(landingA.create.textContent,'Hide the create form');assert.equal(landingA.create.getAttribute('aria-expanded'),'true');assert.deepEqual(calls,['open']);
  landingA.create.onclick();assert.equal(landingA.slot.hidden,true);assert.equal(landingA.create.textContent,'Create a project');assert.deepEqual(calls,['open'],'closing asks nothing of the owner');
  const empty=new Node('main');globalThis.document.body.append(empty);
  const landingB=landing.renderProjectLanding(empty,{projects:[]},E,{});
  assert.equal(landingB.slot.hidden,false);assert.equal(landingB.create.hidden,true);
 }finally{dom.restore();}
});

const shell=await readFile(new URL('../src/laplace/web/static_shared/workspace.mjs',import.meta.url),'utf8');
const bridgeSource=shell.slice(shell.indexOf('// GUIDE BRIDGE:BEGIN'),shell.indexOf('// GUIDE BRIDGE:END'));
const openRequestedHelp=new (Object.getPrototypeOf(async function(){}).constructor)('args',bridgeSource+'\nreturn openRequestedHelp(args);');
function bridge({href='http://local/project?workspace=writing&corpus=writing-system-architecture&view=overview&help=open',fail=null,current=()=>true}={}){
  const calls=[],notices=[],replaced=[];
  const help={openHelp:async()=>{calls.push('openHelp');if(fail)throw Error(fail);}};   // no journey/guide entry exists here to call
  const args={query:new URL(href).searchParams,help,isCurrent:current,notice:(text,error)=>notices.push([text,error]),
    place:{href},pages:{state:{kept:true},replaceState:(state,_title,url)=>replaced.push([state,String(url)])}};
  return {run:()=>openRequestedHelp(args),calls,notices,replaced};
}

test('help=open opens the existing Help layer once after entry, cleans the address, and never starts a journey or task',async()=>{
  const opened=bridge();assert.equal(await opened.run(),true);
  assert.deepEqual(opened.calls,['openHelp']);
  assert.deepEqual(opened.replaced,[[{kept:true},'http://local/project?workspace=writing&corpus=writing-system-architecture&view=overview']]);
  const plain=bridge({href:'http://local/project?workspace=writing&corpus=x'});assert.equal(await plain.run(),false);
  assert.deepEqual([plain.calls,plain.replaced],[[],[]]);
  const failed=bridge({fail:'help owner unavailable'});assert.equal(await failed.run(),false);
  assert.match(failed.notices[0][0],/The Help guide could not open: help owner unavailable Use the Help button\./);assert.equal(failed.notices[0][1],true);
  const gone=bridge({fail:'late',current:()=>false});assert.equal(await gone.run(),false);assert.deepEqual(gone.notices,[],'a destroyed shell shows nothing');
  const entry=shell.slice(shell.indexOf("  try{\n    const coordinates=profileGenerationCoordinates"),shell.indexOf('// GUIDE BRIDGE:BEGIN'));
  const call=entry.indexOf('await openRequestedHelp({query:initialQuery,help,isCurrent:entryCurrent,notice})');
  assert.ok(call>=0&&call<entry.indexOf("root.dataset.entry='ready'"),'called once at entry, after the first view and before entry is ready');
  assert.ok(!/openGuide|startJourney/.test(bridgeSource),'the bridge never starts a journey');
});

// wave 6: titles keep the row's first line and wrap before they are cut; the note is a second line; the landing's Workspace menu has no state word
const css=await readFile(new URL('../src/laplace/web/static_shared/project-work.css',import.meta.url),'utf8');
test('a landing title wraps to a second line before it is cut, under every choice, and a note is a second line under it',()=>{
  const title=css.match(/\.pw-project-title\{([^}]*)\}/)[1],row=css.match(/\.pw-project-choices \.pw-project\{([^}]*)\}/)[1];
  assert.match(title,/line-clamp:2/);assert.doesNotMatch(title,/nowrap/);assert.doesNotMatch(title,/flex:1 1 0/);
  assert.match(row,/flex-direction:column/,'the note goes under the title, not beside it');
  assert.doesNotMatch(css.match(/\.pw-project-note\{([^}]*)\}/)[1],/nowrap/);
  assert.match(css,/\.pw-project-note\{[^}]*font-size:var\(--fs-meta\)/,'13 px meta text');
});
test('the landing header reads Workspace with no Show or Hide word, as the same menu inside a project does',()=>{
  assert.match(css,/app-navigation-more>summary::after,\.application-header \.app-navigation-more\[open\]>summary::after\{content:none\}/);
  assert.doesNotMatch(css,/app-navigation-more>summary::after\{content:'Show'/);
});
test('a Sources row has one Show/Hide control and its identity is a heading inside that panel, in the same words',async()=>{
  const material=await readFile(new URL('../src/laplace/web/static_shared/workspace-material.mjs',import.meta.url),'utf8');
  assert.doesNotMatch(material,/rowDisclosure\('(?:Pinned source identity|Source identity)'/);
  assert.match(material,/identityPart\('Pinned source identity'/);assert.match(material,/identityPart\('Source identity'/);
  assert.equal([...material.matchAll(/rowDisclosure\('/g)].length,2,'Manage on a linked row, More on a recorded row');
});
