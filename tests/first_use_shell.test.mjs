// Real shell/Help controllers with a local DOM, no owner effects or browser geometry claim.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {installDOM,Node,findButton} from './helpers/evidence_reader_harness.mjs';
import {mountGlobalHelp} from '../src/laplace/web/static_shared/workspace-help-door.mjs';
import {mountHelp} from '../src/laplace/web/static_shared/workspace-help.mjs';
const root=new URL('../src/laplace/web/static_shared/',import.meta.url),read=name=>readFile(new URL(name,root),'utf8');
import {declareControl} from '../src/laplace/web/static_shared/workspace-presentation.mjs';
const app=await read('workspace-app.mjs'),entry=await read('project-work.mjs');
const navCode=app.slice(app.indexOf('const el='),app.indexOf('export async function mountWorkspaceDependencies')).replaceAll('export function','function');
const {mountAppNavigation,guardAppNavigation}=new Function(navCode+';return {mountAppNavigation,guardAppNavigation};')();
const landCode=entry.slice(entry.indexOf('function renderProjectLanding'),entry.indexOf('// PROJECTS LANDING:END'));
const renderLanding=new Function('declareControl',landCode+';return renderProjectLanding;')(declareControl),E=(tag,text='',cls='')=>{const n=new Node(tag);n.textContent=text;n.className=cls;return n;};
const contains=(parent,node)=>parent.all().includes(node);
Node.prototype.addEventListener=function(key,fn){(this.listeners??={})[key]=fn;};Node.prototype.removeEventListener=function(key){delete this.listeners?.[key];};
Node.prototype.before=function(node){this.parent.insertBefore(node,this);};Node.prototype.after=function(node){const i=this.parent.children.indexOf(this);this.parent.children.splice(i+1,0,node);node.parent=this.parent;};Node.prototype.contains=function(node){return contains(this,node);};Node.prototype.hasAttribute=function(key){return this.getAttribute(key)!==null;};
test('first arrival gives actual task choices without creating a project; populated choices preserve registered project identity',()=>{
 const dom=installDOM();try{const host=new Node('main');dom.body.append(host);let chosen;renderLanding(host,{projects:[]},E,{onCreate:id=>chosen=id});assert.equal(host.querySelector('section').children[0].textContent,'Your projects and writing');findButton(host,'Start writing').onclick();assert.equal(chosen,'write');assert.equal(host.querySelector('input').hidden,true);
 const populated=new Node('main');dom.body.append(populated);renderLanding(populated,{projects:[{name:'garden',title:'Garden Ω'},{name:'notes',title:'Notes',source_optional:true}]},E);findButton(populated,'Read a source').onclick();assert.deepEqual(populated.all().filter(n=>n.tag==='a').map(n=>new URL(n.href,'http://local').searchParams.get('view')),['material','material']);findButton(populated,'Start writing').onclick();assert.deepEqual(populated.all().filter(n=>n.tag==='a').map(n=>new URL(n.href,'http://local').searchParams.get('view')),['manuscript','overview']);
 }finally{dom.restore();}
});
test('primary navigation keeps advanced tools reachable; ordinary same-tab departure goes through draft owner, modified links do not',async()=>{
 const dom=installDOM(),old=globalThis.location;globalThis.location={href:'http://local/project?app=workflows',search:'?app=workflows'};try{
 const host=new Node('header');dom.body.append(host);const nav=mountAppNavigation(host,'workflows'),links=nav.children.filter(n=>n.tag==='a');assert.deepEqual(links.map(n=>n.textContent),['Projects','Workflows']);assert.ok(nav.querySelector('details').textContent.includes('App settings'));
 const listeners={};nav.addEventListener=(key,fn)=>listeners[key]=fn;nav.removeEventListener=()=>{};let calls=[];guardAppNavigation(nav,{requestNavigation:async(...args)=>calls.push(args)});const link=links[0];let prevented=0;listeners.click({target:link,button:0,preventDefault:()=>prevented++});assert.equal(prevented,1);assert.equal(calls.length,1);assert.equal(calls[0][1].opener,link);listeners.click({target:link,button:0,ctrlKey:true,preventDefault:()=>assert.fail('modified link prevented')});assert.equal(calls.length,1);
 }finally{globalThis.location=old;dom.restore();}
});
const areas={schema_version:'laplace.help-areas/1',project:'',version:'v1',areas:[{id:'overview',view:'projects',title:'Projects',glance:'Choose your next task.',guide:{id:'start',section:'create',label:'Create a project'},next_action:'Choose Start writing.',effects:'Help reads only.'},{id:'work',view:'work',title:'Tasks',glance:'Inspect a task.'}],journeys:[]};
const guides={project:'',version:'v1',guides:[{id:'start',title:'Start here',summary:'Read and write locally.',sections:[{id:'create',title:'Open or create a project',paragraphs:['Keep Ω draft.'],steps:['Choose Start writing.'],references:[{label:'Advanced guide',path:'docs/advanced.md'}]}]}]};
test('explicit guide uses declared content and packaged references, Back finds the new opener; later view intent cancels a delayed guide',async()=>{
 const dom=installDOM();try{const main=new Node('main');dom.body.append(main);let reads=0;const help=mountHelp(main,{areas,view:'projects',readGuides:async()=>{reads++;return guides;}});const opener=findButton(help.element,'Create a project');opener.focus();await opener.onclick();assert.equal(reads,1);assert.ok(help.element.textContent.includes('Keep Ω draft.'));assert.equal(help.element.all().filter(n=>n.tag==='a').length,0,'packaged paths are not fabricated reader URLs');const back=findButton(help.element,'Back to Projects');back.focus();back.onclick();const current=findButton(help.element,'Create a project');assert.notEqual(current,opener);assert.equal(document.activeElement,current);
 let release;const held=new Promise(r=>release=r),second=mountHelp(main,{areas,view:'projects',readGuides:()=>held});const pending=findButton(second.element,'Create a project');pending.focus();const job=pending.onclick();second.show('work');release(guides);await job;assert.ok(second.element.textContent.includes('Inspect a task.'));assert.ok(!second.element.textContent.includes('Keep Ω draft.'));
 }finally{dom.restore();}
});

test('global entry Help is the same explicit read-only door and a delayed opening does not steal newer input focus',async()=>{
 const dom=installDOM(),oldWidth=globalThis.innerWidth;globalThis.innerWidth=1280;try{const host=new Node('main'),navigation=new Node('nav');dom.body.append(navigation,host);let calls=[],release;const delayed=new Promise(r=>release=r);const help=mountGlobalHelp(host,{navigation,view:'projects',request:async path=>{calls.push(path);return delayed;}});const opener=findButton(navigation,'Help');assert.equal(opener.dataset.control,'help:guide');assert.equal(calls.length,0);opener.focus();const pending=help.open();const newer=new Node('textarea');newer.value='Retained Ω';host.append(newer);newer.focus();release({help:areas});await pending;assert.equal(document.activeElement,newer);assert.equal(newer.value,'Retained Ω');assert.deepEqual(calls,['/authoring/help?view=areas']);assert.ok(host.querySelector('.workspace-help'));help.dispose();
 }finally{globalThis.innerWidth=oldWidth;dom.restore();}
});

test('global Help refuses a foreign project envelope before its guidance is painted',async()=>{
 const dom=installDOM(),width=globalThis.innerWidth;globalThis.innerWidth=1280;try{const host=new Node('main'),navigation=new Node('nav');dom.body.append(host,navigation);const help=mountGlobalHelp(host,{navigation,view:'projects',request:async()=>({help:{...areas,project:'foreign',areas:[{view:'projects',title:'Foreign',glance:'UNQUALIFIED BODY'}]}})});await help.open();assert.equal(host.querySelector('.workspace-help'),null);assert.ok(!host.textContent.includes('UNQUALIFIED BODY'));assert.ok(navigation.textContent.includes('Help is unavailable'));help.dispose();}finally{globalThis.innerWidth=width;dom.restore();}
});
