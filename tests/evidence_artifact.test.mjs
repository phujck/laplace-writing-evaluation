import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {renderEngineeringSupport} from '../src/laplace/web/static_shared/engineering-support.mjs';
import {createHash} from 'node:crypto';
import {readArtifact,argumentSnapshot,artifactKind,checkArtifactPage,ARGUMENT_SCHEMA,VISUAL_SCHEMA,STRUCTURED_LIMIT,openArtifact} from '../src/laplace/web/static_shared/writing-artifact.mjs';
import {walkSource} from './helpers/walk_source.mjs';

function transport(text,{changeAt=-1}={}){
 const chars=Array.from(text),sha=createHash('sha256').update(text).digest('hex'),calls=[];
 return {calls,request:async url=>{
  calls.push(url);const q=new URL(url,'http://local').searchParams,offset=Number(q.get('offset')),limit=Number(q.get('limit'));
  assert.equal(q.get('format'),'json');const content=chars.slice(offset,offset+limit).join(''),end=offset+Array.from(content).length;
  return {path:q.get('path'),scope:q.get('scope'),content,offset,total_chars:chars.length,bytes:Buffer.byteLength(text),sha256:calls.length===changeAt?'b'.repeat(64):sha,next_offset:end<chars.length?end:null};
 }};
}
test('large Unicode JSON assembles exact complete bytes using code-point offsets',async()=>{
 const value={schema_version:VISUAL_SCHEMA,project:'p',figures:[],padding:'é😀'.repeat(40000)},text=JSON.stringify(value),t=transport(text);
 assert.ok(Buffer.byteLength(text)>65536);let progress=0;
 const loaded=await readArtifact({request:t.request,project:'p',path:'blueprint/index.json',onProgress:()=>progress++});
 assert.deepEqual(JSON.parse(loaded.text),value);assert.ok(progress>1);assert.equal(loaded.complete,true);
});
test('changing identity, missing content and broken continuation refuse a structured snapshot',async()=>{
 const t=transport(JSON.stringify({text:'a'.repeat(90000)}),{changeAt:2});
 await assert.rejects(readArtifact({request:t.request,project:'p',path:'x.json'}),/changed while reading/);
 assert.throws(()=>checkArtifactPage({content:'x'},0),/Invalid artifact page/);
 assert.throws(()=>checkArtifactPage({content:'x',offset:0,total_chars:2,bytes:2,sha256:'a'.repeat(64),next_offset:null},0),/incomplete/);
});
test('oversized evidence stops after one bounded page and retains continuation',async()=>{
 const t=transport('x'.repeat(STRUCTURED_LIMIT+1));const data=await readArtifact({request:t.request,project:'p',path:'x.json'});
 assert.equal(data.complete,false);assert.equal(t.calls.length,1);assert.ok(data.page.next_offset);assert.match(data.reason,/2 MiB/);
});
test('explicit schemas and endpoint direction, never project-name dispatch',()=>{
 const value={schema_version:ARGUMENT_SCHEMA,project:'p',nodes:[{id:'A',kind:'definition'},{id:'B',kind:'claim'}],
 relations:[['B','prerequisite','A'],['B','support','ref:paper']],chapters:[]};
 const snapshot=argumentSnapshot(value,'p','sha');assert.deepEqual(snapshot.edges,[{from:'B',to:'A'}]);
 assert.equal(snapshot.relations[1].rel,'support');assert.equal(snapshot.nodes[2].id,'B');
 assert.equal(artifactKind({schema_version:'unknown/1',project:'writing-system-architecture'}),'generic');
 assert.throws(()=>argumentSnapshot({...value,project:'other'},'p','sha'),/project/);
 assert.throws(()=>argumentSnapshot({...value,relations:[['B','prerequisite','missing']]},'p','sha'),/absent/);
 assert.throws(()=>argumentSnapshot({...value,relations:[['B','invented','A']]},'p','sha'),/unsupported/);
});
test('versioned representative snapshots preserve schema, identities and support without campaign setup',async()=>{
 const map=JSON.parse(await readFile(new URL('./fixtures/evidence/argument-map.v1.json',import.meta.url),'utf8'));
 const visual=JSON.parse(await readFile(new URL('./fixtures/evidence/visual-index.v1.json',import.meta.url),'utf8'));
 for(const fixture of [map,visual]){
  assert.equal(fixture.fixture.version,1);
  assert.equal(fixture.fixture.kind,'minimised-historical-representative');
  assert.match(fixture.fixture.source_sha256,/^[a-f0-9]{64}$/);
 }
 const snapshot=argumentSnapshot(map,map.project,map.fixture.source_sha256);
 assert.equal(snapshot.recorded,map);
 assert.equal(snapshot.edges.length,map.relations.filter(r=>r[1]==='prerequisite').length);
 assert.ok(snapshot.edges.some(e=>e.from==='res:diamond-identity-boundary'&&e.to==='res:local-guard-basis'));
 const support=snapshot.relations.find(r=>r.rel==='support');
 assert.ok(support);assert.ok(!snapshot.edges.some(e=>e.from===support.source&&e.to===support.target));
 assert.ok(map.nodes.some(n=>n.kind==='goal'));
 assert.ok(snapshot.obligations.some(q=>q.id==='question:formal-target-repair'&&q.target.node_id==='res:formal-target-gap'));
 for(const node of map.nodes){
  assert.match(node.revision,/^[a-f0-9]{64}$/);
  assert.equal(snapshot.nodes.find(n=>n.id===node.id).revision,node.revision);
  assert.ok(map.chapters.some(c=>c.nodes.includes(node.id)),'recorded chapter placement '+node.id);
 }
 assert.ok(map.documentary_bindings.length>0);
 for(const [claim,key,reference,reading] of map.documentary_bindings){
  assert.ok(map.nodes.some(n=>n.id===claim));assert.ok(map.source_registry[key]);
  assert.match(map.source_registry[key].sha256,/^[a-f0-9]{64}$/);
  assert.ok(reference&&reading);
 }
 assert.equal(map.research_bindings.length,2);
 for(const binding of map.research_bindings){
  assert.ok(map.nodes.some(n=>n.id===binding.claim));
  assert.match(map.results[binding.result].revision,/^sha256:[a-f0-9]{64}$/);
 }
 assert.equal(artifactKind(visual),'visual-index');assert.equal(visual.figures.length,7);
 assert.equal(new Set(visual.figures.map(f=>f.id)).size,7);
 for(const figure of visual.figures){
  assert.ok(figure.caption&&figure.question&&figure.title);assert.ok(figure.proposed_chapter_ids.length);
  for(const format of ['pdf','svg']){
   const output=figure.render.outputs.find(o=>o.format===format);assert.ok(output);
   assert.equal(output.scope,'manuscript');assert.match(output.sha256,/^[a-f0-9]{64}$/);
  }
 }
});
class Node{
 constructor(tag){this.tag=tag;this.children=[];this.style={};this.dataset={};this._text='';this.isConnected=true;this.value='';}
 set textContent(v){this._text=String(v||'');this.children=[];}get textContent(){return this._text+this.children.map(n=>n.textContent||'').join('');}
 get childNodes(){return this.children;}
 append(...nodes){for(const n of nodes){n.parent=this;this.children.push(n);}}prepend(...nodes){for(const n of nodes)n.parent=this;this.children.unshift(...nodes);}
 replaceChildren(...nodes){this.children=[];this._text='';this.append(...nodes);}setAttribute(k,v){this[k]=v;}
 showModal(){this.open=true;}close(){this.open=false;this.onclose?.();}remove(){if(this.parent)this.parent.children=this.parent.children.filter(n=>n!==this);this.isConnected=false;}
 focus(){globalThis.document.activeElement=this;}all(){return [this,...this.children.flatMap(n=>n.all?.()||[])];}
}
function dom(){
 const saved=globalThis.document,body=new Node('body'),head=new Node('head'),editor=new Node('textarea'),iframe=new Node('iframe');
 editor.value='UNSAVED manuscript';body.append(editor,iframe);
 globalThis.document={body,head,activeElement:editor,createElement:t=>new Node(t),createTextNode:t=>{const n=new Node('#text');n.textContent=t;return n;},querySelector:()=>null};
 return {body,editor,iframe,restore:()=>globalThis.document=saved};
}
test('opening and closing generic evidence preserves the live editor and its unsaved value',async()=>{
 const d=dom();try{
 const t=transport(JSON.stringify({schema_version:'future/99',value:42}));
 const dialog=await openArtifact({project:'p',path:'record.json',request:t.request});
 assert.match(dialog.textContent,/No specialised viewer for schema future\/99/);
 assert.equal(d.body.children[0],d.editor);assert.equal(d.body.children[1],d.iframe);assert.equal(d.editor.value,'UNSAVED manuscript');
 dialog.close();assert.deepEqual(d.body.children,[d.editor,d.iframe]);assert.equal(document.activeElement,d.editor);
 }finally{d.restore();}
});
test('pinned source mismatch fails visibly and does not render the changed source as the snapshot',async()=>{
 const d=dom();try{
 const t=transport('{"changed":true}');const dialog=await openArtifact({project:'p',path:'source.json',expectedSha256:'c'.repeat(64),request:t.request});
 assert.match(dialog.textContent,/Linked source identity changed/);assert.match(dialog.textContent,/No structured view was accepted/);
 dialog.close();
 }finally{d.restore();}
});
test('served entrypoints use the common dialog and explicit current-object actions',async()=>{
 const root=new URL('../src/laplace/web/static_shared/',import.meta.url);
 const [workspace,pdf,evidence,reader]=await Promise.all(['workspace.mjs','writing-pdf.mjs','writing-evidence.mjs','writing-artifact.mjs'].map(f=>readFile(new URL(f,root),'utf8'))),walk=walkSource();
 for(const s of [workspace,pdf,walk,evidence])assert.match(s,/\/shared\/writing-artifact\.mjs/);
 assert.match(reader,/Open current canonical object/);assert.match(reader,/Open current result inspector/);
 const inspect=workspace.slice(workspace.indexOf('  async function inspectProjectArtifact'),workspace.indexOf('  async function inspectOwnerRead'));
 assert.doesNotMatch(inspect,/show\(|loadDocument|leaveForm|discard|save/);
 assert.match(reader,/snapshot,onSelect/);
});

test('saved map dialog keeps recorded identities and only opens current data on an explicit action',async()=>{
 const d=dom(),saved=globalThis.__artifactGraphTest;try{
 const source=await readFile(new URL('../src/laplace/web/static_shared/writing-artifact.mjs',import.meta.url),'utf8').then(code=>code.replace(/from (['"])\.\/([^'"]+)\1/g,(_match,_quote,path)=>'from '+JSON.stringify(new URL('../src/laplace/web/static_shared/'+path,import.meta.url).href)));
 const code=source.replace("await import('/shared/concept-explorer.mjs')","globalThis.__artifactGraphTest")
  .replace("await import('/shared/concept-reader.mjs')","({renderConceptRecord:async(host,{node,onNavigate})=>{host.append(document.createTextNode('CURRENT '+node.id));const b=document.createElement('button');b.textContent='Follow current relation';b.onclick=()=>onNavigate('claim:next');host.append(b);}})");
 let model=null;globalThis.__artifactGraphTest={mountArgumentOverview:async(_host,options)=>{model=options.snapshot;return {destroy(){}};}};
 const {openArtifact:open}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
 const map={schema_version:ARGUMENT_SCHEMA,project:'p',authority:{concept_network_revision:'saved-network'},
  nodes:[{id:'goal:one',title:'Recorded goal',kind:'goal',revision:'recorded-revision',sources:[]}],
  relations:[],chapters:[],documentary_bindings:[],research_bindings:[]};
 const pages=transport(JSON.stringify(map)),current=[];
 const request=async url=>{if(url.startsWith('/concepts/state?')){current.push(url);return {focus:{id:'goal:one',title:'Current changed title'},content_revision:'new-revision'};}return pages.request(url);};
 const dialog=await open({project:'p',path:'argument-map.json',request});
 assert.ok(model);assert.equal(model.recorded.nodes[0].title,'Recorded goal');
 assert.match(dialog.textContent,/recorded-revision/);assert.equal(current.length,0);
 const openCurrent=dialog.all().find(n=>n.tag==='button'&&n.textContent==='Open current canonical object');
 assert.ok(openCurrent);await openCurrent.onclick();assert.equal(current.length,1);
 assert.match(dialog.textContent,/new-revision/);assert.match(dialog.textContent,/recorded-revision/);
 const follow=dialog.all().find(n=>n.textContent==='Follow current relation'&&n.tag==='button');await follow.onclick();assert.match(current.at(-1),/node=claim%3Anext/);
 assert.equal(d.editor.value,'UNSAVED manuscript');assert.equal(d.body.children[1],d.iframe);
 dialog.close();assert.deepEqual(d.body.children,[d.editor,d.iframe]);
 }finally{globalThis.__artifactGraphTest=saved;d.restore();}
});


// Review C1-C5: real research-card caching, declared saved paths, retained shapes,
// pinned media routing and accessible asynchronous dialog semantics.
const harness=await import('./helpers/evidence_reader_harness.mjs');

test('typed guide Work peek uses the existing detail renderer once without catalogue or mutations',async()=>{
 const d=harness.installDOM();try{
 const project='other-namespace',id='WORK-exact',url='/work/state?'+new URLSearchParams({project,view:'detail',id,limit:'1'}),calls=[];
 const request=async route=>{calls.push(route);assert.equal(route,url);return {project,view:'detail',task:{id,title:'Exact observed work',status:'done',recorded_status:'done',goal:'The actual owner criterion',dispatch:{children:[]}},blockers:[],children:{items:[]},dependants:{items:[]},allowed_actions:{task_status:{permitted:true,statuses:['done'],http:{method:'POST',url:'/work/transition'}}},read_cut:{revision:'observed'}};};
 const dialog=await openArtifact({ownerRead:{http:{method:'GET',url}},label:'Work observation',request});
 assert.deepEqual(calls,[url]);assert.equal(d.dialogs().length,1);assert.match(harness.bodyOf(dialog).textContent,/Exact observed work/);
 const panel=dialog.querySelector('.artifact-current');assert.equal(document.activeElement,panel);assert.equal(panel.tabIndex,-1);assert.deepEqual(panel.focusOptions,{preventScroll:true});assert.equal(panel.revealOptions,undefined,'Do not scroll dialog ancestors');assert.equal(panel.revealed,undefined,'Do not scroll dialog ancestors');
 assert.equal(dialog.querySelectorAll('form').length,0);assert.equal(dialog.querySelectorAll('.operator-work-catalog').length,0);assert.equal(dialog.querySelectorAll('.work-dispatch').length,1,'Read-only Work includes the owner dispatch diagnostics.');
 const full=dialog.querySelectorAll('a').find(n=>n.textContent==='Open the full Work tab for actions');const q=new URL(full.href,'http://localhost').searchParams;assert.equal(q.get('corpus'),project);assert.equal(q.get('work'),id);
 assert.equal(d.editor.value,'UNSAVED manuscript');assert.equal(d.body.children[1],d.iframe);dialog.close();assert.equal(d.dialogs().length,0);assert.equal(document.activeElement,d.editor);
 }finally{d.restore();}
});
test('owner reading refuses non-GET, malformed and foreign coordinates before request',async()=>{
 const d=harness.installDOM();try{
 for(const read of [{http:{method:'POST',url:'/work/state?project=p&view=detail&id=W'}},{http:{method:'GET',url:'/work/state?project=p&view=detail&id=W&id=other'}},{http:{method:'GET',url:'https://foreign.test/work/state?project=p&view=detail&id=W'}}])await assert.rejects(openArtifact({ownerRead:read,request:()=>assert.fail('No rejected owner request')}));
 assert.equal(d.dialogs().length,0);
 }finally{d.restore();}
});
test('native material preview reaches existing source reader and compares unordered qualified fields',async()=>{
 const d=harness.installDOM();try{
 const target={owner:'repository',repository:'laplace',path:'src/atlas/store.py'},url='/projects/material-references?'+new URLSearchParams({project:'consumer',view:'preview',target:JSON.stringify(target)}),calls=[];
 const dialog=await openArtifact({ownerRead:{http:{method:'GET',url}},label:'Source observation',request:async route=>{calls.push(route);return {schema_version:'laplace.material-reference-source/1',project:'consumer',id:null,target:{owner:'repository',path:target.path,repository:'laplace'},currentness:'UNBOUND',current_revision:'sha256:source',consumed_revision:null,units:'Unicode characters',owner_result:{content:'Exact observed Atlas source',source:{sha256:'source'},next_offset:null}};}});
 assert.deepEqual(calls,[url]);assert.match(harness.bodyOf(dialog).textContent,/UNBOUND/);assert.match(harness.bodyOf(dialog).textContent,/Exact observed Atlas source/);assert.match(harness.bodyOf(dialog).textContent,/repository=laplace/);assert.equal(d.editor.value,'UNSAVED manuscript');dialog.close();
 }finally{d.restore();}
});
test('closed owner reading shell rejects late success without changing editor or another panel',async()=>{
 const d=harness.installDOM();try{
 let release;const pending=openArtifact({ownerRead:{http:{method:'GET',url:'/work/state?project=p&view=detail&id=W'}},label:'Late work',request:async()=>new Promise(resolve=>{release=resolve;})});
 assert.equal(d.dialogs().length,1);d.dialogs()[0].close();release({project:'p',view:'detail',task:{id:'W',title:'LATE OWNER'}});await pending;
 assert.equal(d.dialogs().length,0);assert.ok(!d.body.textContent.includes('LATE OWNER'));assert.equal(d.editor.value,'UNSAVED manuscript');
 assert.equal(document.activeElement,d.editor);
 }finally{d.restore();}
});
test('guide owner panel replacement discards late Work failure and keeps one material controller',async()=>{
 const d=harness.installDOM();try{
 let callbacks,rejectWork;const work='/work/state?project=p&view=detail&id=W',target={owner:'repository',repository:'laplace',path:'criterion.md'},source='/projects/material-references?'+new URLSearchParams({project:'p',view:'preview',target:JSON.stringify(target)});
 const t=harness.transport('# Guide'),request=async url=>url===work?new Promise((_resolve,reject)=>{rejectWork=reject;}):url===source?{schema_version:'laplace.material-reference-source/1',project:'p',id:null,target,currentness:'UNBOUND',current_revision:'observed',consumed_revision:null,owner_result:{content:'CURRENT SOURCE',next_offset:null}}:t.request(url);
 const dialog=await openArtifact({project:'p',path:'guide.md',request,renderMarkdown:async(_host,_text,options)=>{callbacks=options;}});
 const late=callbacks.onInspectOwner({http:{method:'GET',url:work}});await Promise.resolve();await callbacks.onInspectOwner({http:{method:'GET',url:source}});rejectWork(Error('STALE WORK ERROR'));await late;
 assert.equal(dialog.querySelectorAll('.artifact-current').length,1);assert.match(harness.bodyOf(dialog).textContent,/CURRENT SOURCE/);assert.ok(!harness.bodyOf(dialog).textContent.includes('STALE WORK ERROR'));assert.equal(d.editor.value,'UNSAVED manuscript');dialog.close();
 }finally{d.restore();}
});
test('current owner failure is revealed, and superseded success never steals focus or reveals again',async()=>{
 const d=harness.installDOM();try{
 let callbacks,release;const work='/work/state?project=p&view=detail&id=W',target={owner:'repository',repository:'laplace',path:'criterion.md'},source='/projects/material-references?'+new URLSearchParams({project:'p',view:'preview',target:JSON.stringify(target)}),t=harness.transport('# Long guide');
 const request=async url=>url===work?new Promise(resolve=>{release=resolve;}):url===source?Promise.reject(Error('CURRENT OWNER FAILURE')):t.request(url);
 const dialog=await openArtifact({project:'p',path:'guide.md',request,renderMarkdown:async(_host,_text,options)=>{callbacks=options;}});
 const late=callbacks.onInspectOwner({http:{method:'GET',url:work}});await Promise.resolve();await callbacks.onInspectOwner({http:{method:'GET',url:source}});
 const panel=dialog.querySelector('.artifact-current');assert.equal(document.activeElement,panel);assert.equal(panel.revealed,undefined,'Do not scroll dialog ancestors');assert.match(panel.textContent,/CURRENT OWNER FAILURE/);
 release({project:'p',view:'detail',task:{id:'W',title:'STALE SUCCESS'}});await late;
 assert.equal(document.activeElement,panel);assert.equal(panel.revealed,undefined,'Do not scroll dialog ancestors');assert.ok(!panel.textContent.includes('STALE SUCCESS'));assert.match(panel.textContent,/CURRENT OWNER FAILURE/);dialog.close();assert.equal(document.activeElement,d.editor);
 }finally{d.restore();}
});

test('research-card actual inspectOnce caller can close and reopen a removable JSON reader',async()=>{
 const d=harness.installDOM(),r=await harness.loadReader();try{
 const record={id:'result:test',kind:'result',title:'Result',scope:'project',result:'output.json',
  evidence_files:[{path:'output.json',scope:'project',role:'Recorded output'}]};
 const t=harness.transport('{"answer":42}'),host=new harness.Node('section');d.body.append(host);
 const card=r.cards.renderResearchCard(host,record,{project:'p',
  inspect:(_parent,label,path,scope)=>r.inspectArtifactDialog({project:'p',path,scope,label,request:t.request}),
  onError:message=>assert.fail(message)});
 const output=harness.findButton(card,/^Outputs/);assert.ok(output);
 await output.click();const first=d.dialogs()[0];assert.ok(first?.open);first.close();
 assert.equal(document.activeElement,output);assert.equal(d.dialogs().length,0);
 await output.click();const second=d.dialogs()[0];assert.ok(second?.open);assert.notEqual(second,first);
 assert.equal(d.editor.value,'UNSAVED manuscript');assert.equal(d.body.children[1],d.iframe);second.close();
 assert.equal(document.activeElement,output);assert.equal(t.calls.length,2);
 // The actual writing-evidence callback imports the non-cacheable wrapper.
 const source=await readFile(new URL('../src/laplace/web/static_shared/writing-evidence.mjs',import.meta.url),'utf8');
 assert.match(source,/inspectArtifactDialog as openEvidenceArtifact/);
 }finally{r.destroy();d.restore();}
});

test('recorded and current nested result cards also reopen through their actual callbacks',async()=>{
 const d=harness.installDOM(),r=await harness.loadReader();try{
 const record={id:'result:test',kind:'result',title:'Nested result',scope:'project',result:'output.json',evidence_files:[{path:'output.json',scope:'project',role:'Recorded output'}]};
 const saved=JSON.stringify({schema_version:'laplace.research-result-detail/1',project:'p',result:record});
 const parentPages=harness.transport(saved),outputPages=harness.transport('{"answer":42}');
 const request=async url=>url.startsWith('/research/result?')?{project:'p',result:record}:new URL(url,'http://local').searchParams.get('path')==='output.json'?outputPages.request(url):parentPages.request(url);
 const dialog=await r.openArtifact({project:'p',path:'saved.json',request}),body=harness.bodyOf(dialog);
 // one modal (M5 C3): the nested output reader REPLACES the result reader and carries Back to it;
 // Back reopens the parent through its own door, so the card is rendered again
 const exercise=async(current,select)=>{const b=harness.findButton(select(current),/^Outputs/);await b.click();assert.equal(d.dialogs().length,1,'the nested reader replaced the parent');const nested=d.dialogs()[0];assert.equal(nested.dataset.inspector,'artifact');assert.equal(nested.children[0].className,'inspector-back');assert.equal(nested.children[0].textContent,'Back to saved.json');await nested.children[0].onclick();assert.equal(nested.open,false);assert.equal(d.dialogs().length,1);const reopened=d.dialogs()[0];assert.ok(harness.findButton(select(harness.bodyOf(reopened)),/^Outputs/),'Back re-rendered the parent card');return reopened;};
 let current=await exercise(body,b=>b.querySelector('.research-result'));
 await harness.findButton(harness.bodyOf(current),'Open current result result:test').click();
 current=await exercise(harness.bodyOf(current),b=>b.querySelectorAll('.research-result').at(-1));
 assert.equal(d.editor.value,'UNSAVED manuscript');current.close();assert.equal(document.activeElement,d.editor,'the user Close returns focus to the opener recorded at the trail start');
 }finally{r.destroy();d.restore();}
});

test('argument renderer exposes declared @formal ranges and recorded run/output/source navigation',async()=>{
 const d=harness.installDOM(),r=await harness.loadReader();try{
 const text=await readFile(new URL('./fixtures/evidence/argument-map.v1.json',import.meta.url),'utf8'),map=JSON.parse(text),t=harness.transport(text);
 const dialog=await r.openArtifact({project:map.project,path:'map.json',request:t.request});
 const snapshot=r.snapshots[0],detail=new harness.Node('section');harness.bodyOf(dialog).append(detail);
 await snapshot.renderNode(detail,'res:formal-target-gap');
 assert.match(detail.textContent,/Recorded lines 104–131/);assert.ok(detail.textContent.includes(map.mechanism_source.sha256));
 assert.doesNotMatch(detail.textContent,/Source identity absent/);
 assert.ok(harness.findButton(detail,'Read pinned source snapshot @formal'));
 const binding=map.research_bindings.find(b=>b.claim==='res:formal-target-gap'),result=map.results[binding.result];
 assert.ok(detail.textContent.includes(result.run));assert.ok(detail.textContent.includes(result.output_sha256));
 const paths=r.recordedResultFiles(result);assert.ok(paths.some(f=>f.role==='recorded output'));
 for(const f of paths){assert.ok(detail.textContent.includes(f.path));assert.ok(harness.findButton(detail,'Open '+f.role+' '+f.path));}
 assert.ok(harness.findButton(detail,'Open current result inspector'));dialog.close();
 }finally{r.destroy();d.restore();}
});

test('recorded line-range reader verifies the whole file then displays the declared excerpt',async()=>{
 const d=harness.installDOM(),r=await harness.loadReader();try{
 const text='one\ntwo\nthree\nfour\n',t=harness.transport(text);
 const dialog=await r.openArtifact({project:'p',path:'trace.md',expectedSha256:harness.sha(text),lineRange:[2,3],request:t.request});
 assert.equal(new URL(t.calls[0],'http://local').searchParams.get('expected_sha256'),harness.sha(text));
 const body=harness.bodyOf(dialog);assert.match(body.textContent,/2 \| two\n3 \| three/);assert.doesNotMatch(body.textContent,/1 \| one/);
 const download=dialog.all().find(n=>n.tag==='a');assert.equal(new URL(download.href,'http://local').searchParams.get('expected_sha256'),harness.sha(text));
 dialog.close();
 }finally{r.destroy();d.restore();}
});

test('both documented visual-index representations produce visible pinned vector controls',async()=>{
 const d=harness.installDOM(),r=await harness.loadReader();try{
 for(const name of ['visual-index.v1.json','visual-index.paths.v1.json']){
  const text=await readFile(new URL('./fixtures/evidence/'+name,import.meta.url),'utf8'),value=JSON.parse(text),t=harness.transport(text);
  const dialog=await r.openArtifact({project:value.project,path:name,request:t.request}),body=harness.bodyOf(dialog);
  const outputs=value.figures.flatMap(f=>r.visualOutputs(f)).filter(o=>['pdf','svg'].includes(o.format));
  assert.equal(body.all().filter(n=>n.tag==='button'&&/^Open recorded (pdf|svg)$/.test(n.textContent)).length,outputs.length);
  for(const out of outputs)assert.ok(body.textContent.includes(out.sha256));
  for(const f of value.figures)if(f.placement){assert.ok(body.textContent.includes(f.placement.source));assert.ok(body.textContent.includes('PDF page '+f.placement.pdf_page));}
  await harness.findButton(body,'Open recorded pdf').click();
  assert.equal(new URL(r.pdfCalls.at(-1)[0],'http://local').searchParams.get('expected_sha256'),outputs.find(o=>o.format==='pdf').sha256);
  dialog.close();
 }
 const valid={id:'x',render:{outputs:['x.pdf'],output_digests:{'x.pdf':'a'.repeat(64)}}};
 assert.throws(()=>r.visualOutputs({...valid,render:{outputs:['x.pdf',{path:'y.svg'}]}}),/Mixed/);
 assert.throws(()=>r.visualOutputs({...valid,render:{outputs:['x.pdf'],output_digests:{}}}),/identity/);
 assert.throws(()=>r.visualOutputs({id:'x',render:{outputs:[{path:'x.pdf',format:'pdf',scope:'manuscript',sha256:'a'.repeat(64)}],output_digests:{'x.pdf':'b'.repeat(64)}}}),/Conflicting/);
 }finally{r.destroy();d.restore();}
});

test('pinned PDF/image routes keep byte guards and image failure never silently opens current data',async()=>{
 const d=harness.installDOM(),r=await harness.loadReader();try{
 const pin='a'.repeat(64);
 await r.openArtifact({project:'p',path:'old.pdf',expectedSha256:pin});
 assert.equal(new URL(r.pdfCalls[0][0],'http://local').searchParams.get('expected_sha256'),pin);
 for(const path of ['old.svg','old.png']){
  const dialog=await r.openArtifact({project:'p',path,expectedSha256:pin}),body=harness.bodyOf(dialog),img=body.querySelector('img');
  assert.equal(new URL(img.src,'http://local').searchParams.get('expected_sha256'),pin);
  assert.equal(new URL(dialog.all().find(n=>n.tag==='a').href,'http://local').searchParams.get('expected_sha256'),pin);
  img.onerror();assert.equal(body.querySelector('img'),null);assert.equal(harness.statusOf(dialog).getAttribute('role'),'alert');
  assert.equal(d.dialogs().length,1);
  await harness.findButton(body,'Open current image (unverified against record)').click();
  const current=d.dialogs().at(-1);assert.equal(new URL(harness.bodyOf(current).querySelector('img').src,'http://local').searchParams.has('expected_sha256'),false);
  current.close();dialog.close();
 }
 }finally{r.destroy();d.restore();}
});

test('each nested dialog is named and completion/failure is announced without claiming accessibility certification',async()=>{
 const d=harness.installDOM(),r=await harness.loadReader();try{
 const t=harness.transport('{"x":1}');
 const first=await r.openArtifact({project:'p',path:'one.json',label:'First evidence',request:t.request});
 const second=await r.openArtifact({project:'p',path:'two.json',label:'Second evidence',request:t.request});
 const firstId=first.getAttribute('aria-labelledby'),secondId=second.getAttribute('aria-labelledby');
 assert.ok(firstId&&secondId&&firstId!==secondId);
 assert.equal(first.children.find(n=>n.id===firstId).textContent,'First evidence');
 assert.equal(second.children.find(n=>n.id===secondId).textContent,'Second evidence');
 assert.equal(harness.statusOf(first).getAttribute('role'),'status');
 assert.equal(harness.statusOf(first).getAttribute('aria-live'),'polite');
 assert.equal(harness.bodyOf(first).getAttribute('aria-busy'),'false');
 second.close();first.close();
 const failed=await r.openArtifact({project:'p',path:'bad.json',request:async()=>{throw Error('read failed');}});
 assert.equal(harness.statusOf(failed).getAttribute('role'),'alert');assert.match(harness.statusOf(failed).textContent,/read failed/);
 assert.equal(harness.bodyOf(failed).getAttribute('aria-busy'),'false');failed.close();
 }finally{r.destroy();d.restore();}
});

test('PDF companion actions preserve a pinned origin identity',async()=>{
 const {pdfAnnotationAction}=await import('../src/laplace/web/static_shared/writing-pdf.mjs');
 const pin='a'.repeat(64),origin='/research/artifact?'+new URLSearchParams({project:'p',path:'old.pdf',scope:'manuscript',expected_sha256:pin});
 const action=pdfAnnotationAction({unsafeUrl:'../blueprint/argument-map.json'},origin,'http://local/project');
 const query=new URL(action.url,'http://local').searchParams;
 assert.equal(query.get('expected_sha256'),pin);assert.equal(query.get('path'),'old.pdf');assert.equal(query.get('resolve'),'pdf-link');
});

test('observed argument-map/2 renders its recorded meaning and exact mechanism lookup without current substitution',async()=>{
 const d=harness.installDOM(),r=await harness.loadReader();try{
 const text=await readFile(new URL('./fixtures/evidence/argument-map.v2.json',import.meta.url),'utf8'),value=JSON.parse(text);
 assert.equal(value.schema_version,'writing-system-architecture.argument-map/2');
 const t=harness.transport(text),dialog=await r.openArtifact({project:value.project,path:'argument-map-v2.json',request:t.request});
 assert.equal(r.snapshots.length,1);const detail=new harness.Node('section');harness.bodyOf(dialog).append(detail);
 const node=value.nodes.find(n=>n.id==='res:formal-target-gap');await r.snapshots[0].renderNode(detail,node.id);
 assert.ok(detail.textContent.includes(node.meaning));assert.ok(detail.textContent.includes(node.revision));
 assert.ok(harness.findButton(detail,'Read pinned source snapshot @formal'));
 assert.equal(r.artifactKind({...value,schema_version:'writing-system-architecture.argument-map/3'}),'generic');
 dialog.close();
 }finally{r.destroy();d.restore();}
});

test('same declared schema rejects observed native-shaped support rather than projecting an empty map',async()=>{
 const malformed=JSON.parse(await readFile(new URL('./fixtures/evidence/argument-map.malformed-v1.json',import.meta.url),'utf8'));
 assert.equal(artifactKind(malformed),'argument');
 assert.throws(()=>argumentSnapshot(malformed,malformed.project,'sha'),/Incompatible argument snapshot: results.*dictionary/);
 const research={...malformed,results:{}};
 assert.throws(()=>argumentSnapshot(research,research.project,'sha'),/research_bindings\[0\].*claim and result/);
 const source={...research,research_bindings:[{claim:'res:scope',result:'observed-result'}]};
 assert.throws(()=>argumentSnapshot(source,source.project,'sha'),/nodes\[1\].*sources.*required/);
 const question={...source,nodes:source.nodes.map(n=>({...n,sources:n.id==='res:scope'?['scope']:[]}))};
 assert.throws(()=>argumentSnapshot(question,question.project,'sha'),/question:scope.*target/);
});

test('question fields and malformed used support fields fail before graph projection',async()=>{
 const valid=JSON.parse(await readFile(new URL('./fixtures/evidence/argument-map.v1.json',import.meta.url),'utf8'));
 for(const key of ['target','state','discharge']){
  const map=structuredClone(valid),question=map.nodes.find(n=>n.kind==='question');delete question[key];
  assert.throws(()=>argumentSnapshot(map,map.project,'sha'),new RegExp('Incompatible argument snapshot: nodes.*\\.'+key));
 }
 for(const [change,pattern]of [
  [m=>m.nodes.find(n=>n.kind==='question').target='unknown:target',/target/],
  [m=>m.nodes.find(n=>n.kind==='question').state='resolved-invented',/state/],
  [m=>m.nodes[0].sources={key:'scope'},/sources.*array/],
  [m=>m.source_registry=[],/source_registry.*dictionary/],
  [m=>m.chapters[0].nodes='goal:explain-writing-system',/chapters.*nodes.*array/],
  [m=>delete m.chapters[0].source,/chapters.*chapter and source/],
  [m=>m.documentary_bindings=[{claim:'goal:one'}],/documentary_bindings/],
  [m=>m.research_bindings={},/research_bindings.*array/],
  [m=>Object.values(m.results)[0].dependencies={path:'some.json'},/dependencies.*array/],
  [m=>Object.values(m.results)[0].limitations='Scope only',/limitations.*array/],
  [m=>m.nodes[0].result_bindings=[{id:'unmapped-result'}],/result_bindings.*corresponding/]
 ]){const map=structuredClone(valid);change(map);assert.throws(()=>argumentSnapshot(map,map.project,'sha'),pattern);}
});

test('malformed snapshot dialog retains raw JSON and pinned download, without graph or zero-attention claim',async()=>{
 const d=harness.installDOM(),r=await harness.loadReader();try{
 const text=await readFile(new URL('./fixtures/evidence/argument-map.malformed-v1.json',import.meta.url),'utf8'),map=JSON.parse(text),t=harness.transport(text);
 const dialog=await r.openArtifact({project:map.project,path:'malformed.json',request:t.request});
 assert.equal(r.snapshots.length,0);
 assert.match(harness.statusOf(dialog).textContent,/Incompatible argument snapshot: results/);
 assert.equal(harness.statusOf(dialog).getAttribute('role'),'alert');
 assert.doesNotMatch(dialog.textContent,/0 points needing attention|No points need attention/);
 const raw=dialog.querySelector('.artifact-raw');assert.equal(raw.hidden,false);assert.equal(raw.textContent,text);
 assert.ok(harness.findButton(dialog,'Show raw JSON / text'));
 const download=dialog.all().find(n=>n.tag==='a');assert.equal(new URL(download.href,'http://local').searchParams.get('expected_sha256'),harness.sha(text));
 assert.ok(t.calls.every(url=>url.startsWith('/research/artifact?')));
 assert.equal(d.editor.value,'UNSAVED manuscript');dialog.close();assert.equal(document.activeElement,d.editor);
 }finally{r.destroy();d.restore();}
});

test('valid minimal historical maps can omit undeclared support; explicitly unavailable details remain inspectable',async()=>{
 const minimal={schema_version:ARGUMENT_SCHEMA,project:'p',nodes:[{id:'goal:one',kind:'goal'}],relations:[],chapters:[]};
 assert.equal(argumentSnapshot(minimal,'p','sha').obligations.length,0);
 const d=harness.installDOM(),r=await harness.loadReader();try{
 const map={...minimal,nodes:[{id:'goal:one',kind:'goal',sources:['unavailable-history']}],
  research_bindings:[{claim:'goal:one',result:'unavailable-result'}]};
 const dialog=await r.openArtifact({project:'p',path:'minimal.json',request:harness.transport(JSON.stringify(map)).request});
 assert.equal(r.snapshots.length,1);assert.match(dialog.textContent,/Source identity absent from this snapshot: unavailable-history/);
 assert.ok(harness.findButton(dialog,'Open current result inspector'));dialog.close();
 }finally{r.destroy();d.restore();}
});


test('engineering currentness and explicit adoption use the owner handle',async()=>{
 const d=dom();try{
  const host=new Node('section'),handle={operation:'concept_change',payload:{node:'claim:body',base_revision:'L',value:{engineering_support:[{work_id:'WORK-one',completion_revision:'C',meaning_revision:'P',covered_scope:'Custody only'}]}}};
  let adopted=null;
  const support={status:'REVIEW_REQUIRED',adoption_handle:handle,bindings:[{status:'ACK_REQUIRED',reason:'New completion requires acknowledgement',covered_scope:'Custody only',completion_revision:'C-old',current_completion_revision:'C',meaning_revision:'P',current_meaning_revision:'P',read_handle:{payload:{namespace:'p',id:'WORK-one'}}}]};
  renderEngineeringSupport(host,support,{onAdopt:async value=>{adopted=value;}});
  assert.match(host.textContent,/Review required/);assert.match(host.textContent,/Custody only/);
  assert.match(host.textContent,/Independent verification is not asserted/);
  assert.equal(adopted,null);
  await host.all().find(node=>node.tag==='button').onclick();
  assert.deepEqual(adopted,handle);
  const historical=new Node('section');renderEngineeringSupport(historical,{status:'HISTORICAL_ARTIFACT',reason:'Recorded bytes do not renew support'});
  assert.match(historical.textContent,/Recorded bytes do not renew/);assert.doesNotMatch(historical.textContent,/Current scoped/);
 }finally{d.restore();}
});

test('ordinary guide artifact renders engineering state before its prose',async()=>{
 const d=dom();try{
  const t=transport('Guide custody statement.'),request=async url=>({...await t.request(url),engineering_support:{status:'REVIEW_REQUIRED',claims:[{node:'claim:body',bindings:[{status:'STALE',covered_scope:'Custody only',reason:'Source changed before trust',read_handle:{payload:{namespace:'p',id:'WORK-one'}}}]}]},custody_degradation:{status:'INLINE_RETAINED',failed_attempts:1,inline_bytes:99}});
  const dialog=await openArtifact({project:'p',path:'BACKGROUND.md',request});
  assert.match(dialog.textContent,/Source changed before trust/);assert.match(dialog.textContent,/Guide custody statement/);
  assert.match(dialog.textContent,/Saved inline: body-store verification unavailable/);
  assert.match(dialog.textContent,/99 inline bytes/);dialog.close();
 }finally{d.restore();}
});

test('guide support opens the canonical owner while prose retains one read-only claim preview',async()=>{
 const d=dom();try{
 const source=await readFile(new URL('../src/laplace/web/static_shared/writing-artifact.mjs',import.meta.url),'utf8').then(code=>code.replace(/from (['"])\.\/([^'"]+)\1/g,(_match,_quote,path)=>'from '+JSON.stringify(new URL('../src/laplace/web/static_shared/'+path,import.meta.url).href)));
 const code=source.replace("await import('/shared/concept-reader.mjs')","({renderConceptRecord:async(host,{node})=>host.append(document.createTextNode('READABLE CLAIM '+node.id))})");
 const {openArtifact:open}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
 const project='other-project',node='res:retention-and-projection',uri='/concepts/state?'+new URLSearchParams({project,node});
 const t=transport('[Current custody observation]('+uri+')'),reads=[];
 const request=async url=>{if(url.startsWith('/concepts/state?')){reads.push(url);return {focus:{id:node},content_revision:'current'};}return {...await t.request(url),engineering_support:{status:'CURRENT',claims:[{node,read_handle:{http:{method:'GET',url:uri}},bindings:[{status:'CURRENT',covered_scope:'Body custody only'}]}]}};};
 let proseRead;
 const dialog=await open({project:'selected-project',path:'BACKGROUND.md',request,renderMarkdown:async(host,_text,options)=>{proseRead=()=>options.onInspectClaim({project,node});host.append(document.createTextNode('Recorded guide prose'));}});
 const link=dialog.all().find(n=>n.tag==='a'&&n.textContent==='Open in Argument & evidence (opens separately)');
 const q=new URL(link.href,'http://localhost').searchParams;
 assert.equal(q.get('corpus'),project);assert.equal(q.get('node'),node);assert.equal(q.get('view'),'argument');assert.equal(q.get('structure'),null);
 assert.equal(link.target,'_blank');assert.equal(link.rel,'noopener noreferrer');assert.equal(link.onclick,undefined,'Ordinary anchor is not intercepted into the artifact preview');
 assert.equal(reads.length,0);assert.equal(dialog.all().filter(n=>n.className==='artifact-current').length,0);
 assert.equal(dialog.all().filter(n=>n.className?.includes('engineering-support')).length,1);
 await proseRead();const currentPanel=dialog.all().find(n=>n.className==='artifact-current');await proseRead();
 assert.equal(dialog.all().filter(n=>n.className==='artifact-current').length,1);
 assert.equal(dialog.all().find(n=>n.className==='artifact-current'),currentPanel);
 assert.match(currentPanel.textContent,/Read-only claim preview/);
 const owner=currentPanel.all().find(n=>n.tag==='a');assert.equal(owner.href,link.href);assert.equal(owner.target,'_blank');assert.equal(owner.rel,'noopener noreferrer');
 assert.equal(reads.length,2);for(const url of reads){const q=new URL(url,'http://localhost').searchParams;assert.equal(q.get('project'),project);assert.equal(q.get('node'),node);}
 assert.match(dialog.textContent,/READABLE CLAIM res:retention-and-projection/);
 assert.equal(globalThis.document.activeElement.className,'artifact-current');
 assert.equal(d.editor.value,'UNSAVED manuscript');assert.equal(d.body.children[1],d.iframe);dialog.close();
 }finally{d.restore();}
});

test('one artifact current-node inspector isolates switched fetches, renders, errors and closure',async()=>{
 const d=dom(),previous=globalThis.__artifactCurrentTest;try{
 let releaseRender,renderStarted;
 const started=new Promise(resolve=>{renderStarted=resolve;});
 globalThis.__artifactCurrentTest=async(host,{node})=>{if(node.id==='slow-render'){renderStarted();await new Promise(resolve=>{releaseRender=resolve;});}host.append(document.createTextNode('CURRENT '+node.id));};
 const source=await readFile(new URL('../src/laplace/web/static_shared/writing-artifact.mjs',import.meta.url),'utf8').then(code=>code.replace(/from (['"])\.\/([^'"]+)\1/g,(_match,_quote,path)=>'from '+JSON.stringify(new URL('../src/laplace/web/static_shared/'+path,import.meta.url).href)));
 const code=source.replace("await import('/shared/concept-reader.mjs')","({renderConceptRecord:globalThis.__artifactCurrentTest})");
 const {openArtifact:open}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
 const t=transport('Underlying guide stays.'),waiting=new Map();let sourceReads=0;
 const state=node=>({focus:{id:node},content_revision:'revision-'+node});
 const request=url=>{if(!url.startsWith('/concepts/state?'))return t.request(url);sourceReads++;const node=new URL(url,'http://local').searchParams.get('node');return node.startsWith('slow-fetch')||node==='slow-error'?new Promise((resolve,reject)=>waiting.set(node,{resolve,reject})):Promise.resolve(state(node));};
 let inspect;
 const dialog=await open({project:'guide-project',path:'BACKGROUND.md',request,renderMarkdown:async(host,_text,options)=>{inspect=options.onInspectClaim;host.append(document.createTextNode('Underlying guide stays.'));}});
 const body=dialog.all().find(n=>n.className==='artifact-body'),reading=dialog.all().find(n=>n.className==='artifact-reading-region'),guide=body.children[0];reading.scrollTop=71;
 const late=inspect({project:'old-project',node:'slow-fetch'});
 await inspect({project:'new-project',node:'latest'});
 const panel=dialog.all().find(n=>n.className==='artifact-current');
 waiting.get('slow-fetch').resolve(state('OLD_FETCH'));await late;
 const error=inspect({project:'old-project',node:'slow-error'});await inspect({project:'new-project',node:'latest'});waiting.get('slow-error').reject(Error('OLD_ERROR'));await error;
 const rendering=inspect({project:'old-project',node:'slow-render'});await started;
 await inspect({project:'new-project',node:'latest'});releaseRender();await rendering;
 await inspect({project:'new-project',node:'latest'});
 assert.equal(dialog.all().filter(n=>n.className==='artifact-current').length,1);assert.equal(dialog.all().find(n=>n.className==='artifact-current'),panel);
 assert.match(panel.textContent,/new-project · latest/);assert.match(panel.textContent,/CURRENT latest/);
 assert.ok(!dialog.textContent.includes('OLD_FETCH')&&!dialog.textContent.includes('OLD_ERROR')&&!dialog.textContent.includes('CURRENT slow-render'));
 assert.match(dialog.textContent,/Underlying guide stays/);assert.equal(globalThis.document.activeElement,panel);
 assert.equal(body.children[0],guide);assert.equal(reading.scrollTop,71);
 const closing=inspect({project:'old-project',node:'slow-fetch-close'});dialog.close();waiting.get('slow-fetch-close').resolve(state('CLOSED_FETCH'));await closing;
 assert.equal(globalThis.document.activeElement,d.editor);assert.equal(d.editor.value,'UNSAVED manuscript');assert.deepEqual(d.body.children,[d.editor,d.iframe]);
 const finalReads=sourceReads;await inspect({project:'new-project',node:'latest'});assert.equal(sourceReads,finalReads);
 }finally{globalThis.__artifactCurrentTest=previous;d.restore();}
});


test('engineering claim owner links refuse malformed methods, routes and duplicate or missing coordinates',()=>{
 const d=dom();try{
 const valid='/concepts/state?project=P&node=res%3Aclaim';
 for(const [url,method]of [[valid,'POST'],['/research/result?project=P&node=res%3Aclaim','GET'],[valid+'&project=OTHER','GET'],['/concepts/state?project=P','GET'],[valid+'&path=private','GET'],['https://elsewhere/concepts/state?project=P&node=res%3Aclaim','GET']]){
  const host=new Node('section');renderEngineeringSupport(host,{status:'REVIEW_REQUIRED',claims:[{read_handle:{http:{method,url}},bindings:[{status:'ACK_REQUIRED'}]}]});
  assert.equal(host.all().filter(n=>n.tag==='a'&&n.textContent.startsWith('Open in Argument & evidence')).length,0);assert.match(host.textContent,/exact project and node coordinates/);
 }
 }finally{d.restore();}
});


test('current evidence owner read stays contextual and refuses namespace or result substitution',async()=>{
 const {ownerHumanTarget,qualifiedOwnerHTTP}=await import('../src/laplace/web/static_shared/writing-owner-read.mjs');
 const handle={operation:'research',payload:{view:'result',id:'result:one'},http:{method:'GET',route:'/research/result',query:{project:'p',id:'result:one'}}};
 const target=qualifiedOwnerHTTP(handle,'p');assert.equal(target.owner.kind,'research-result');assert.equal(qualifiedOwnerHTTP({...handle,payload:{view:'result',id:'other'}},'p'),null);assert.equal(ownerHumanTarget(target.url+'&id=other'),null);
 const d=harness.installDOM(),r=await harness.loadReader();try{
  let calls=0;const dialog=await r.openArtifact({ownerRead:target.owner,request:async()=>{calls++;return {schema_version:'laplace.research-result-detail/1',project:'other',result:{id:'result:one'}};}});
  assert.equal(calls,1);assert.match(dialog.textContent,/different coordinates/);assert.equal(d.editor.value,'UNSAVED manuscript');dialog.close();
 }finally{r.destroy();d.restore();}
});

// M5 C9: the research result card header carries the currentness word as a state chip
test('research result card header shows currentness as a state chip with the owner word',async()=>{
 const d=harness.installDOM(),r=await harness.loadReader();try{
  const host=new harness.Node('section');d.body.append(host);
  r.cards.renderResearchCard(host,{id:'result:chip',kind:'result',title:'Chipped',scope:'project',currentness:'CHANGED_INPUT',evidence_files:[]},{project:'p',inspect:()=>{}});
  const chip=host.all().find(n=>n.className.includes('state-chip'));assert.ok(chip);assert.equal(chip.textContent,'changed input');assert.equal(chip.attrs['data-tone'],'attention');
 }finally{d.restore();}
});
