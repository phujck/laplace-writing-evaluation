import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {installDOM,Node,findButton} from './helpers/evidence_reader_harness.mjs';
import * as codec from '../src/laplace/web/static_shared/writing-owner-read.mjs';
import {openArtifact} from '../src/laplace/web/static_shared/writing-artifact.mjs';
import {walkSource} from './helpers/walk_source.mjs';

// The real writer/read owner emits the URL; the real TeX parser decodes its literal escapes.
const produced=spawnSync('./scripts/laplace-python',['-B','-c',String.raw`
import json,runpy,tempfile
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from laplace.native import tools as writing_tools; from laplace.manuscript import walk; from laplace.web import research_surface
with tempfile.TemporaryDirectory(prefix='laplace-manuscript-artifact-link-') as name:
 root=Path(name);runpy.run_path('tests/test_manuscript_blocks.py')['_fixture'](root)
 value='{"summary":"Exact retained observation","scope":"fixture only"}'
 saved=writing_tools.execute(root,'blocks','work','store_artifact',{'path':'development/observed result.json','scope':'project','content':value,'before':None,'reason':'Public-owner link fixture'})
 read=writing_tools.execute(root,'blocks','work','read_artifact',{'id':saved['id']})
 url=read['human_read']['url'];escaped=url.replace('&',r'\&').replace('%',r'\%').replace('_',r'\_')
 piece=next(p for p in walk.tex_pieces(r'\href{'+escaped+r'}{Observed result}',{}) if p.get('t')=='href')
 query=parse_qs(urlsplit(url).query);query.update(format=['json'],offset=['0'],limit=['32768'])
 status,headers,body=research_surface.handle('/research/artifact',query,'GET',b'',repo_root=root)
 assert status==200,(status,body)
 print(json.dumps({'url':url,'piece':piece,'page':json.loads(body),'text':value}))
`],{cwd:fileURLToPath(new URL('..',import.meta.url)),encoding:'utf8',timeout:30000});
assert.equal(produced.status,0,produced.stderr);const fixture=JSON.parse(produced.stdout);
const walk=walkSource();
const linkCode=walk.slice(walk.indexOf('function manuscriptLink('),walk.indexOf('/** One piece of a paragraph.',walk.indexOf('function manuscriptLink(')));
// the shell's inspection doors and walk handlers are domain modules (workspace-inspection, workspace-walk-handlers; M5 S2 F1)
const workspace=(await import('./helpers/workspace_source.mjs')).workspaceSource();
const readerCode=workspace.slice(workspace.indexOf('  async function inspectProjectArtifact('),workspace.indexOf('  async function inspectOwnerRead('));
const readerFactory=new Function('project','openEvidenceArtifact','api','renderSavedMarkdown',`const inspector={adopt(){return {depth:0};}},bridge={count(){},reject(){}};let placeMemo=null;`+readerCode+'return inspectProjectArtifact;');
// the shell's named open-project-artifact handler, run behind the REAL bridge fence and router (M5 readability
// P2: the handler table is in workspace.mjs, the fence, ledger and routing in workspace-bridge.mjs)
const handlerStart=workspace.indexOf('    openProjectArtifact(message){');
const handlerCode=workspace.slice(handlerStart,workspace.indexOf('    editorState(){',handlerStart));
const {installWalkBridge,BRIDGE_ROUTES}=await import('../src/laplace/web/static_shared/workspace-bridge.mjs');
const handlerFactory=new Function('sourceWindow','project','session','notice','inspectProjectArtifact','artifactHumanTarget','root',
  `let currentView='manuscript';const manuscript={sourceWindow},views={current:()=>currentView},discussion={session:()=>session},ui={notice,root},`
  +`inspection={projectArtifact:inspectProjectArtifact};const handlers={${handlerCode}};return {handler:handlers.openProjectArtifact,setView:value=>{currentView=value;}};`);
const bridgeFactory=(location,sourceWindow,project,session,notice,inspectProjectArtifact,artifactHumanTarget,root)=>{
  let listener=null;
  const owned=handlerFactory(sourceWindow,project,session,notice,inspectProjectArtifact,artifactHumanTarget,root);
  const handlers=Object.fromEntries(BRIDGE_ROUTES.map(route=>[route.handler,()=>{}]));
  handlers.openProjectArtifact=owned.handler;
  installWalkBridge({target:{addEventListener:(type,fn)=>{listener=fn;},removeEventListener(){}},origin:()=>location.origin,sourceWindow,ledger:{count(){},reject(){}},handlers});
  return {handle:event=>listener(event),setView:owned.setView};
};
function dom(){const d=installDOM(),create=document.createElement;document.createElement=tag=>{const n=create(tag);n.listeners={};n.addEventListener=(key,fn)=>n.listeners[key]=fn;n.removeAttribute=key=>{delete n.attrs[key];delete n[key];};return n;};return d;}
function setup(d,{embedded=true,requestOverride=null}={}){
 const posted=[],requests=[],pending=[],options=[],notices=[];let view='manuscript';
 const source={document:{activeElement:null}},window=embedded?{parent:{postMessage:message=>posted.push(message)}}:{};
 if(!embedded)window.parent=window;
 const host=new Node('section');host.scrollTop=93;d.body.append(host);
 const request=async url=>{requests.push(url);return requestOverride?requestOverride(url):structuredClone(fixture.page);};
 const evidence=opts=>{options.push(opts);return openArtifact(opts);};
 const inspect=readerFactory('blocks',evidence,request,()=>{});
 const root=new Node('main'),location={origin:'http://localhost',href:'http://localhost/walk?corpus=blocks'};
 const render=new Function('artifactHumanTarget','ownerHumanTarget','isKnownOwnerReadRoute','isKnownArtifactReadRoute','el','renderPieces','window','location','emit','store','S','blockById','document','readerModule',
  linkCode.replaceAll("await import('/shared/writing-artifact.mjs')",'readerModule')+'return manuscriptLink;')(
   codec.artifactHumanTarget,codec.ownerHumanTarget,codec.isKnownOwnerReadRoute,codec.isKnownArtifactReadRoute,
   (tag,cls,text)=>{const n=document.createElement(tag);n.className=cls;n.textContent=text||'';return n;},()=>{},window,location,()=>{}, {},{corpus:'blocks'},new Map(),document,
   {openArtifact:opts=>evidence({...opts,request})});
 const ownerBridge=bridgeFactory(location,()=>source,'blocks',
  {guard:fn=>pending.push(Promise.resolve().then(fn))},(...args)=>notices.push(args),inspect,codec.artifactHumanTarget,root);
 const bridge=message=>ownerBridge.handle({origin:location.origin,source,data:message});
 return {host,posted,requests,pending,options,notices,source,root,render,bridge,setView:ownerBridge.setView};
}
const event=extra=>({button:0,preventDefault(){this.prevented=true;},stopPropagation(){},...extra});

test('actual owner URL survives TeX parsing, manuscript iframe, parent adapter and pinned shared reader',async()=>{
 assert.equal(fixture.piece.url,fixture.url);
 const d=dom();try{const h=setup(d);h.render(fixture.piece,h.host);const link=h.host.children[0];h.source.document.activeElement=link;link.focus();
 assert.equal(link.href,fixture.url);await link.listeners.click(event());assert.equal(h.posted.length,1);assert.equal(h.posted[0].url,fixture.url);
 h.bridge(h.posted[0]);await Promise.all(h.pending);assert.equal(d.dialogs().length,1);
 const target=codec.artifactHumanTarget(fixture.url,{project:'blocks'}),opts=h.options[0];
 for(const key of ['path','scope','expectedSha256','artifactId','artifactOwner'])assert.equal(opts[key],target[key]);
 const q=new URL(h.requests[0],'http://localhost').searchParams;
 assert.equal(q.get('expected_sha256'),target.expectedSha256);assert.equal(q.get('artifact_id'),target.artifactId);assert.equal(q.get('owner'),'writing-artifact');
 assert.match(d.dialogs()[0].textContent,/Exact retained observation/);
 await findButton(d.dialogs()[0],'Close').click();assert.equal(document.activeElement,link);assert.equal(h.host.scrollTop,93);assert.equal(d.editor.value,'UNSAVED manuscript');
 }finally{d.restore();}
});

test('standalone manuscript uses same pinned reader and modifier clicks retain ordinary href behavior',async()=>{
 const d=dom();try{const h=setup(d,{embedded:false});h.render(fixture.piece,h.host);const link=h.host.children[0];
 for(const extra of [{ctrlKey:true},{metaKey:true},{shiftKey:true},{altKey:true},{button:1}]){const e=event(extra);await link.listeners.click(e);assert.equal(e.prevented,undefined);}
 assert.equal(h.requests.length,0);assert.equal(link.href,fixture.url);
 await link.listeners.click(event());assert.equal(d.dialogs().length,1);await findButton(d.dialogs()[0],'Close').click();assert.equal(document.activeElement,link);
 }finally{d.restore();}
});

test('invalid pinned artifact coordinates have no manuscript href or parent fallback',async()=>{
 const d=dom();try{const h=setup(d);const bad=[];
 for(const [key,value]of [['project','OTHER'],['scope','repository'],['path','../secret'],['path','/outside/file'],['expected_sha256','bad'],['artifact_id','not-an-art'],['owner','other'],['unknown','x'],['expected_sha256','']]){const u=new URL(fixture.url,'http://localhost');u.searchParams.set(key,value);bad.push(u.pathname+u.search);}
 bad.push(fixture.url+'&project=blocks',fixture.url+'#different');
 for(const url of bad){assert.equal(codec.artifactHumanTarget(url,{project:'blocks'}),null,url);h.render({...fixture.piece,url},h.host);const link=h.host.children.at(-1);assert.equal(link.href,undefined,url);h.bridge({type:'laplace:open-project-artifact',url,path:'development/other.json'});}
 await Promise.all(h.pending);assert.equal(h.requests.length,0);assert.equal(d.dialogs().length,0);assert.equal(h.notices.length,bad.length);
 assert.equal(codec.artifactHumanTarget('https://outside.example'+fixture.url,{project:'blocks'}),null);
 }finally{d.restore();}
});

test('changed pins and stale parent selection refuse without replacing the source or stealing focus',async()=>{
 const d=dom();try{const changed=setup(d,{requestOverride:()=>({...fixture.page,sha256:'a'.repeat(64)})});
 changed.render(fixture.piece,changed.host);const link=changed.host.children[0];changed.source.document.activeElement=link;await link.listeners.click(event());changed.bridge(changed.posted[0]);await Promise.all(changed.pending);
 assert.match(d.dialogs()[0].textContent,/changed|different/i);assert.ok(!d.dialogs()[0].textContent.includes('Exact retained observation'));await findButton(d.dialogs()[0],'Close').click();
 const h=setup(d);h.render(fixture.piece,h.host);h.source.document.activeElement=h.host.children[0];await h.host.children[0].listeners.click(event());h.bridge(h.posted[0]);h.setView('history');await Promise.all(h.pending);assert.equal(h.requests.length,0);assert.equal(d.dialogs().length,0);assert.equal(d.editor.value,'UNSAVED manuscript');
 }finally{d.restore();}
});


test('ordinary Work href follows the actual manuscript listener and parent owner inspector',async()=>{
 const d=dom();try{
 const h=setup(d),url='/work/state?project=blocks&view=detail&id=WORK-selected';
 h.render({t:'href',url,s:'Current Work'},h.host);const link=h.host.children[0];
 await link.listeners.click(event());assert.deepEqual(h.posted,[{type:'laplace:open-owner-read',url,label:'Current Work'}]);
 const start=workspace.indexOf('    openOwnerRead(message){');
 const ownerHandlerCode=workspace.slice(start,workspace.indexOf('    // a project artifact link',start));
 const inspectorCode=workspace.slice(workspace.indexOf('  async function inspectOwnerRead('),workspace.indexOf('\n  return {savedMarkdown'));
 const requests=[],pending=[],inspect=new Function('openEvidenceArtifact','api','renderSavedMarkdown','qualifiedOwnerHTTP','project',`const inspector={adopt(){return {depth:0};}},discussion={session:()=>({}),generateProfile:()=>{}},work={reload:async()=>{}},home={refreshStyle:async()=>{}};`+inspectorCode+'return inspectOwnerRead;')(
  openArtifact,async path=>{requests.push(path);return {project:'blocks',view:'detail',task:{id:'WORK-selected',title:'Selected fixture Work',goal:'Read the exact task',status:'ready',recorded_status:'ready',currentness:{status:'CURRENT'},depends_on:[],evidence:[]},allowed_actions:{},blockers:[]};},()=>{},codec.qualifiedOwnerHTTP,'blocks');
 const ownerHandler=new Function('ownerHumanTarget','notice','session','inspectOwnerRead',`const ui={notice},discussion={session:()=>session},inspection={ownerRead:inspectOwnerRead};return {${ownerHandlerCode}}.openOwnerRead;`)(
  codec.ownerHumanTarget,message=>assert.fail(message),{guard:fn=>pending.push(Promise.resolve().then(fn))},inspect);
 const handlers=Object.fromEntries(BRIDGE_ROUTES.map(route=>[route.handler,()=>assert.fail('only openOwnerRead may run')]));handlers.openOwnerRead=ownerHandler;
 let listener=null;installWalkBridge({target:{addEventListener:(type,fn)=>{listener=fn;},removeEventListener(){}},origin:()=>'http://localhost',sourceWindow:()=>h.source,ledger:{count(){},reject(){}},handlers});
 listener({origin:'http://localhost',source:h.source,data:h.posted[0]});
 await Promise.all(pending);assert.deepEqual(requests,[url]);assert.equal(d.dialogs().length,1);assert.match(d.dialogs()[0].textContent,/Selected fixture Work/);await findButton(d.dialogs()[0],'Close').click();
 }finally{d.restore();}
});
