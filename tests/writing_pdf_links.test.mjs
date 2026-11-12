import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {installDOM,Node,findButton} from './helpers/evidence_reader_harness.mjs';
import {openArtifact} from '../src/laplace/web/static_shared/writing-artifact.mjs';
import {pdfAnnotationAction,pdfAnnotationRect,appendPdfAnnotations,pdfDestination,pdfCompanionNotice} from '../src/laplace/web/static_shared/writing-pdf.mjs';

const base='http://127.0.0.1:8771/project?corpus=book',pdf='/research/artifact?project=book&path=%2Frepo%2Fbook%2Fexports%2Fed.pdf&scope=project';
const pin='a'.repeat(64),artifactURL='/research/artifact?'+new URLSearchParams({project:'book',path:'development/proof.json',scope:'project',owner:'writing-artifact',artifact_id:'ART-proof',expected_sha256:pin}),ownerURL='/projects/material-references?'+new URLSearchParams({project:'book',view:'source',id:'edition-map'});

test('PDF owner annotations preserve exact scoped artifact pins and addressed material coordinates',()=>{
 const artifact=pdfAnnotationAction({unsafeUrl:artifactURL},pdf,base);
 assert.deepEqual(artifact,{kind:'artifact',project:'book',path:'development/proof.json',scope:'project',artifactOwner:'writing-artifact',artifactId:'ART-proof',expectedSha256:pin,label:'development/proof.json'});
 const owner=pdfAnnotationAction({unsafeUrl:ownerURL},pdf,base);assert.equal(owner.kind,'owner-read');assert.equal(owner.ownerRead.http.url,ownerURL);assert.equal(owner.ownerRead.id,'edition-map');
 assert.deepEqual(pdfAnnotationAction({url:new URL(artifactURL,base).href},pdf,base),artifact);
 for(const raw of [artifactURL+'&unexpected=yes',artifactURL+'&project=book',artifactURL.replace('book','foreign'),artifactURL.replace(pin,'bad'),artifactURL.replace('ART-proof','bad'),artifactURL.replace('development%2Fproof.json','..%2Fprivate'),ownerURL.replace('book','foreign'),ownerURL+'&view=source','/unknown/read'])assert.equal(pdfAnnotationAction({unsafeUrl:raw},pdf,base),null,raw);
});

test('PDF follow composes actual workspace artifact callback and shared owner reader without file-route fallback',async()=>{
 const source=await readFile(new URL('../src/laplace/web/static_shared/writing-pdf.mjs',import.meta.url),'utf8');
 const followCode=source.slice(source.indexOf('  async function follow(action)'),source.indexOf('  function width()')).replace("await import('/shared/writing-artifact.mjs')",'await readerModule');
 const workspace=(await import('./helpers/workspace_source.mjs')).workspaceSource();   // the inspection doors: workspace-inspection.mjs (M5 S2 F1)
 const adapterCode=workspace.slice(workspace.indexOf('  async function inspectProjectArtifact('),workspace.indexOf('  async function inspectOwnerRead('));
 const d=installDOM(),oldFetch=globalThis.fetch,oldLocation=globalThis.location,requests=[];
 globalThis.location={href:base,origin:new URL(base).origin};
 const content='{"summary":"Pinned PDF evidence"}',sha=createHash('sha256').update(content).digest('hex');
 const artifactLink=artifactURL.replace(pin,sha);
 const api=async url=>{requests.push(url);const q=new URL(url,base).searchParams;
  if(url.startsWith('/projects/material-references?'))return {schema_version:'laplace.material-reference-source/1',project:'book',id:'edition-map',target:{owner:'repository',repository:'laplace',path:'edition-map.json'},owner_result:{content:'EXACT ADDRESSED EDITION MAP'}};
  assert.equal(new URL(url,base).pathname,'/research/artifact');assert.equal(q.get('project'),'book');assert.equal(q.get('path'),'development/proof.json');assert.equal(q.get('artifact_id'),'ART-proof');assert.equal(q.get('owner'),'writing-artifact');assert.equal(q.get('expected_sha256'),sha);
  return {project:'book',path:q.get('path'),scope:'project',content,sha256:sha,bytes:Buffer.byteLength(content),total_chars:content.length,offset:0,next_offset:null};
 };
 globalThis.fetch=async url=>({ok:true,json:()=>api(url)});
 const callback=new Function('project','openEvidenceArtifact','api','renderSavedMarkdown',`const inspector={adopt(){return {depth:0};}},bridge={count(){},reject(){}};let placeMemo=null;`+adapterCode+'return inspectProjectArtifact;')('book',openArtifact,api,()=>{});
 const status=new Node('p'),pdfDialog=new Node('dialog'),layer=new Node('section');pdfDialog.append(layer);d.body.append(pdfDialog);pdfDialog.showModal();pdfDialog.scrollTop=417;
 const {sharedInspector,resetSharedInspector}=await import('../src/laplace/web/static_shared/workspace-inspector.mjs');resetSharedInspector();const inspector=sharedInspector();
 let reopenedPdf=0;const reopenPdf=()=>{reopenedPdf++;pdfDialog.showModal();inspector.adopt(pdfDialog,{kind:'pdf',title:'Book',reopen:reopenPdf});return pdfDialog;};inspector.adopt(pdfDialog,{kind:'pdf',title:'Book',reopen:reopenPdf});
 const factory=new Function('document','status','onOpenArtifact','readerModule','inspector','dialog','token','let closed=false;'+followCode+'return {follow,close:()=>{closed=true;}};');
 // a real viewer builds its follow once per opening with its own token; a reopened PDF is a fresh viewer
 let reader=factory(document,status,callback,Promise.resolve({openArtifact}),inspector,pdfDialog,inspector.tokenOf(pdfDialog));const pending=[];
 try{
  appendPdfAnnotations(layer,[{rect:[1,1,21,11],unsafeUrl:artifactLink},{rect:[1,21,21,31],unsafeUrl:ownerURL}],{convertToViewportPoint:(x,y)=>[x,y]},{url:pdf,base,onAction:action=>pending.push(reader.follow(action))});
  // the lifetime contract: the linked reader REPLACES the PDF (one modal); the reader stays current
  // because it is bound to the PDF's lineage; Close on the reader is Back, reopening the PDF
  for(const [index,expected]of [[0,/Pinned PDF evidence/],[1,/EXACT ADDRESSED EDITION MAP/]]){
   await layer.children[index].click();await pending.at(-1);const dialog=d.dialogs().at(-1);assert.notEqual(dialog,pdfDialog);assert.match(dialog.textContent,expected,'the actual owner door read and rendered');
   assert.equal(pdfDialog.open,false,'the PDF was replaced, not kept underneath');assert.equal(pdfDialog.dataset.inspectorReplaced,'true');assert.equal(inspector.current.dialog,dialog);assert.deepEqual(inspector.trail.map(e=>e.title),['Book']);assert.equal(dialog.children[0].textContent,'Back to Book');
   await findButton(dialog,'Close').click();assert.equal(reopenedPdf,index+1,'Close on the nested reader reopened the PDF through its descriptor');assert.equal(pdfDialog.open,true);assert.equal(inspector.current.dialog,pdfDialog);assert.equal(d.dialogs().filter(n=>n.open).length,1);
   reader=factory(document,status,callback,Promise.resolve({openArtifact}),inspector,pdfDialog,inspector.tokenOf(pdfDialog));
  }
  assert.equal(requests.length,2,'one owner read per follow');assert.equal(requests[1],ownerURL,'owner URL must never become an artifact path');
  // STALE ASYNC after a GENUINE close: the PDF is closed at the trail root while the reader import is pending
  let releaseImport;const late=factory(document,status,callback,new Promise(resolve=>{releaseImport=resolve;}),inspector,pdfDialog,inspector.tokenOf(pdfDialog));
  const action=pdfAnnotationAction({unsafeUrl:ownerURL},pdf,base),lateRead=late.follow(action);pdfDialog.close();assert.equal(inspector.current,null);releaseImport({openArtifact});await lateRead;assert.equal(requests.length,2,'no owner read after the genuine close');assert.equal(d.dialogs().filter(n=>n.open).length,0,'closed PDF cannot create a late owner dialog');
 }finally{resetSharedInspector();d.restore();globalThis.fetch=oldFetch;globalThis.location=oldLocation;}
});

test('PDF links keep exact origin identity for owner resolution, including projection roots',()=>{
 const action=pdfAnnotationAction({unsafeUrl:'source%20package.zip'},pdf,base);
 assert.equal(action.kind,'companion');const query=new URL(action.url,base).searchParams;
 assert.equal(query.get('path'),'/repo/book/exports/ed.pdf');assert.equal(query.get('uri'),'source%20package.zip');assert.equal(query.get('resolve'),'pdf-link');assert.equal(query.get('project'),'book');
 const compiled=pdfAnnotationAction({unsafeUrl:'notes.md#Proof'},'/projection/pdf?file=book%2Fchapter.tex&corpus=book',base);
 assert.equal(new URL(compiled.url,base).searchParams.get('path'),'book/chapter.tex','the owner resolves root, not a client directory guess');
 assert.equal(pdfAnnotationAction({unsafeUrl:'notes.md'},'/references/source?project=book&key=external',base).kind,'unavailable');
});

test('internal and external PDF destinations stay distinct from unsafe URI actions',()=>{
 assert.deepEqual(pdfAnnotationAction({dest:'section.2'},pdf,base),{kind:'destination',destination:'section.2'});
 assert.deepEqual(pdfAnnotationAction({unsafeUrl:'#section.2'},pdf,base),{kind:'destination',destination:'section.2'});
 assert.equal(pdfAnnotationAction({action:'NextPage'},pdf,base).kind,'page-action');
 assert.deepEqual(pdfAnnotationAction({url:'https://example.org/paper'},pdf,base),{kind:'external',url:'https://example.org/paper'});
 assert.equal(pdfAnnotationAction({unsafeUrl:'appendix.pdf'},'https://example.org/papers/main.pdf',base).url,'https://example.org/papers/appendix.pdf');
 for(const raw of ['javascript:alert(1)','data:text/html,bad','file:///etc/passwd','//outside/file','/private/path','..\\outside','#%xx'])assert.equal(pdfAnnotationAction({unsafeUrl:raw},pdf,base),null);
});

test('rotated page annotation rectangles stay in the same viewport as the page',()=>{
 const viewport={convertToViewportPoint:(x,y)=>[100-y,x]};
 assert.deepEqual(pdfAnnotationRect([10,20,30,40],viewport),{left:60,top:10,width:20,height:20});
 assert.equal(pdfAnnotationRect([NaN,0,1,2],viewport),null);
});

test('visible annotations are keyboard links, use safe external navigation and activate exact destinations',()=>{
 const original=globalThis.document,activated=[];globalThis.document={createElement:()=>({style:{},attributes:{},setAttribute(key,value){this.attributes[key]=value;}})};
 try{const host={children:[],append(node){this.children.push(node);}},viewport={convertToViewportPoint:(x,y)=>[x,y]};
 appendPdfAnnotations(host,[{rect:[1,2,11,22],dest:'thm.bound',contentsObj:{str:'Theorem 4'}},{rect:[20,2,30,22],url:'https://example.org/source'},{rect:[1,2,11,22],unsafeUrl:'javascript:bad'}],viewport,{url:pdf,base,onAction:action=>activated.push(action)});
 assert.equal(host.children.length,2);const internal=host.children[0],external=host.children[1];assert.equal(internal.attributes['aria-label'],'Theorem 4');assert.equal(internal.href,'#');assert.equal(internal.style.width,'10px');let prevented=false;internal.onclick({preventDefault(){prevented=true;}});assert.ok(prevented);assert.deepEqual(activated,[{kind:'destination',destination:'thm.bound'}]);assert.equal(external.target,'_blank');assert.equal(external.rel,'noopener noreferrer');
 }finally{globalThis.document=original;}
});

test('named and reference PDF destinations resolve exact pages without guessing',async()=>{
 const ref={num:27,gen:0},pdf={numPages:102,getDestination:async name=>name==='section.2'?[ref,{name:'XYZ'},0,720,null]:null,getPageIndex:async value=>{assert.deepEqual(value,ref);return 28;}};
 assert.equal((await pdfDestination(pdf,'section.2')).page,29);
 assert.equal((await pdfDestination(pdf,[0,{name:'Fit'}])).page,1);
 await assert.rejects(pdfDestination(pdf,'missing'),/unavailable/);await assert.rejects(pdfDestination(pdf,[102,{name:'Fit'}]),/outside/);
});

test('continuous reader adds visible-page text and links, follows a companion, and cancels evicted page resources',async()=>{
 const {readFile}=await import('node:fs/promises');const source=(await readFile(new URL('../src/laplace/web/static_shared/writing-pdf.mjs',import.meta.url),'utf8')).replace("from './writing-owner-read.mjs'",`from '${new URL('../src/laplace/web/static_shared/writing-owner-read.mjs',import.meta.url).href}'`).replace("from './workspace-inspector.mjs'",`from '${new URL('../src/laplace/web/static_shared/workspace-inspector.mjs',import.meta.url).href}'`).replace("await import('/shared/pdfjs/pdf.min.mjs')",'globalThis.__pdfTestLibrary');
 const {openPdf}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
 const original={};for(const key of ['document','window','location','devicePixelRatio','getComputedStyle','IntersectionObserver','fetch','__pdfTestLibrary'])original[key]=globalThis[key];
 class Node{
  constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.attributes={};this.style={setProperty(key,value){this[key]=value;}};this.clientWidth=800;this.clientHeight=850;this.offsetHeight=100;this.scrollTop=0;this.handlers={};}
  set innerHTML(_){this.controls=new Map();for(const selector of ['.wp-back','.wp-forward','h2','.wp-pages','.wp-status','.wp-download','.wp-tools','.wp-page','.wp-count','.wp-zoom','.wp-prev','.wp-next','.wp-minus','.wp-plus','.wp-fit','.wp-close','.wp-go']){const child=new Node(selector);this.controls.set(selector,child);this.append(child);}}
  querySelector(selector){return this.controls?.get(selector)||this.children.find(row=>'.'+row.className===selector)||null;}
  querySelectorAll(){return [];}
  setAttribute(key,value){this.attributes[key]=value;}getAttribute(key){return this.attributes[key];}
  append(...nodes){for(const node of nodes){node.parent=this;this.children.push(node);}}after(node){this.parent?.append(node);}remove(){if(this.parent)this.parent.children=this.parent.children.filter(row=>row!==this);}
  addEventListener(type,callback){(this.handlers[type]??=[]).push(callback);}removeEventListener(type,callback){this.handlers[type]=(this.handlers[type]||[]).filter(fn=>fn!==callback);}showModal(){this.open=true;}close(){this.open=false;for(const fn of [...(this.handlers.close||[])])fn();}getBoundingClientRect(){return {top:100,bottom:900};}getContext(){return {};}focus(){}click(){this.onclick?.({preventDefault(){}});}
 }
 let observer,destroyed=0,textCancelled=0;const body=new Node('body'),head=new Node('head'),annotations=[{rect:[10,20,110,35],unsafeUrl:'notes.md'},{rect:[120,20,170,35],dest:[1,{name:'XYZ'},0,700,null]},{rect:[10,40,110,55],unsafeUrl:artifactURL}];
 const page={getViewport:({scale})=>({width:600*scale,height:800*scale,scale,rawDims:{pageWidth:600,pageHeight:800},convertToViewportPoint:(x,y)=>[x,y].map(value=>value*scale)}),render:()=>({promise:Promise.resolve(),cancel(){}}),getTextContent:async()=>({items:[{str:'Actual PDF statement'}]}),getAnnotations:async()=>annotations};
 globalThis.document={activeElement:null,head,body,createElement:tag=>new Node(tag),querySelector:()=>null};globalThis.location={href:base,origin:'http://127.0.0.1:8771'};globalThis.window={addEventListener(){},removeEventListener(){}};globalThis.devicePixelRatio=2;globalThis.getComputedStyle=()=>({paddingTop:'0',paddingBottom:'0'});globalThis.IntersectionObserver=class{constructor(callback){this.callback=callback;observer=this;this.items=[];}observe(node){this.items.push(node);}disconnect(){}};
 globalThis.__pdfTestLibrary={GlobalWorkerOptions:{},getDocument:()=>({promise:Promise.resolve({numPages:2,getPage:async()=>page,getMetadata:async()=>({info:{}})}),destroy:async()=>{destroyed++;}}),TextLayer:class{constructor({container,textContentSource}){this.container=container;this.text=textContentSource.items[0].str;}async render(){this.container.textContent=this.text;}cancel(){textCancelled++;}}};
 const tick=()=>new Promise(resolve=>setImmediate(resolve));
 try{
  const opened=[];globalThis.fetch=async()=>({ok:true,json:async()=>({url:'/research/artifact?project=book&path=notes.md&scope=project',kind:'text',path:'notes.md',label:'Notes'})});
  await openPdf(pdf,'Book',{onOpenArtifact:async(...args)=>opened.push(args)});const dialog=body.children[0],sheet=observer.items[0];observer.callback([{target:sheet,isIntersecting:true}]);await tick();await tick();
  assert.equal(sheet.querySelector('.wp-text-layer').textContent,'Actual PDF statement');const links=sheet.querySelector('.wp-annotation-layer');assert.equal(links.children.length,3);links.children[1].click();await tick();await tick();assert.equal(dialog.querySelector('.wp-page').value,2);assert.equal(dialog.querySelector('.wp-back').textContent,'Back to page 1');await dialog.querySelector('.wp-back').onclick();assert.equal(dialog.querySelector('.wp-page').value,1);assert.equal(dialog.querySelector('.wp-forward').textContent,'Forward to page 2');await dialog.querySelector('.wp-forward').onclick();assert.equal(dialog.querySelector('.wp-page').value,2);await dialog.querySelector('.wp-back').onclick();assert.equal(dialog.querySelector('.wp-page').value,1);assert.ok(Math.abs(parseFloat(links.children[0].style.width)-129.33333333333334)<1e-8,'link uses CSS pixels, not doubled raster dimensions');
  dialog.scrollTop=417;document.activeElement=links.children[2];links.children[2].click();await tick();await tick();
  const linkedGuards=opened.map(row=>row[2].isCurrent);assert.equal(opened[0][2].opener,links.children[2]);assert.equal(linkedGuards[0](),true);assert.equal(opened[0][0],'development/proof.json');assert.equal(opened[0][2].expectedSha256,pin);assert.equal(opened[0][2].artifactId,'ART-proof');assert.equal(opened[0][2].artifactOwner,'writing-artifact');assert.equal(opened[0][2].project,'book');assert.equal(dialog.scrollTop,417);assert.equal(dialog.open,true);assert.equal(destroyed,0);opened.length=0;
  observer.callback([{target:sheet,isIntersecting:false}]);assert.equal(sheet.querySelector('.wp-text-layer'),null);assert.equal(sheet.querySelector('.wp-annotation-layer'),null);assert.equal(textCancelled,1);
  observer.callback([{target:sheet,isIntersecting:true}]);await tick();await tick();sheet.querySelector('.wp-annotation-layer').children[0].click();await tick();await tick();assert.deepEqual(opened,[['notes.md','Notes',{notice:pdfCompanionNotice({})}]]);assert.match(dialog.querySelector('.wp-status').textContent,/match to this PDF edition has not been recorded/);assert.equal(destroyed,0);assert.equal(dialog.open,true,'the companion reader preserves the PDF passage underneath');dialog.querySelector('.wp-close').click();assert.equal(destroyed,1);assert.equal(body.children.length,0);assert.ok(linkedGuards.every(isCurrent=>!isCurrent()),'late linked reader must refuse after PDF closure');
 }finally{for(const [key,value]of Object.entries(original)){if(value===undefined)delete globalThis[key];else globalThis[key]=value;}}
});

test('companion notices separate current-file identity from demonstrated PDF inclusion, including older resolvers',()=>{
 assert.match(pdfCompanionNotice({basis:'verified-export-source'}),/current project file/);
 assert.match(pdfCompanionNotice({basis:'verified-export-source'}),/match to this PDF edition has not been recorded/);
 const notice='Current project package · this exact PDF was found during inspection. Other members and later file changes are unverified.';
 assert.equal(pdfCompanionNotice({companion_identity:'CURRENT_PROJECT_FILE',edition_match:'EXACT_PDF_INCLUDED',notice}),notice);
});

test('PDF companion navigation REPLACES the viewer through the inspector trail, which carries the parent passage; no competing return chain',async()=>{
 const source=await readFile(new URL('../src/laplace/web/static_shared/writing-pdf.mjs',import.meta.url),'utf8');
 const followCode=source.slice(source.indexOf('  async function follow(action)'),source.indexOf('  function width()'));
 const opened=[],oldLocation=globalThis.location,oldFetch=globalThis.fetch;let closedCount=0,lastPosition=null;
 globalThis.location={href:base,origin:new URL(base).origin};globalThis.fetch=async()=>({ok:true,json:async()=>({kind:'pdf',url:'/research/artifact?project=book&path=companion.pdf',label:'Companion',notice:'Current companion'})});
 try{const run=new Function('env',`const {url,title,notice,onOpenArtifact,readingPosition,close,openPdf,status,pdfCompanionNotice,inspector,dialog}=env;let closed=false,lastPosition=null;${followCode};return {follow,position:()=>lastPosition};`)({url:pdf,title:'Manuscript',notice:'Saved edition',onOpenArtifact:null,readingPosition:()=>({page:7,fraction:.35}),close:()=>{closedCount++;},openPdf:async(...args)=>opened.push(args),status:{},pdfCompanionNotice,inspector:{lineage:()=>()=>true},dialog:{dataset:{}}});
 await run.follow({kind:'companion',url:'/research/artifact?project=book&resolve=pdf-link'});
 assert.equal(closedCount,0,'the parent is not closed first: the companion adopts and replaces it');assert.equal(opened[0][1],'Companion');assert.ok(!('returnTo' in opened[0][2]),'no separate return chain');assert.deepEqual(run.position(),{page:7,fraction:.35},'the parent position is captured for its trail reopen descriptor');
 assert.ok(!source.includes('returnTo')&&!source.includes('Back to previous PDF'),'the PDF door has one return mechanism: the inspector trail');
 assert.ok(source.includes("options.isCurrent=inspector.lineage(token)")&&!source.includes("isCurrent=()=>!closed"),'nested readers are bound to the trail lineage, not the viewer\'s closed flag');
 }finally{globalThis.location=oldLocation;globalThis.fetch=oldFetch;}
});

test('two REAL openPdf calls compose through shared adoption: the companion replaces the parent, Back reopens the parent at its passage, no singleton pre-close',async()=>{
 const {readFile}=await import('node:fs/promises');const source=(await readFile(new URL('../src/laplace/web/static_shared/writing-pdf.mjs',import.meta.url),'utf8')).replace("from './writing-owner-read.mjs'",`from '${new URL('../src/laplace/web/static_shared/writing-owner-read.mjs',import.meta.url).href}'`).replace("from './workspace-inspector.mjs'",`from '${new URL('../src/laplace/web/static_shared/workspace-inspector.mjs',import.meta.url).href}'`).replace("await import('/shared/pdfjs/pdf.min.mjs')",'globalThis.__pdfTestLibrary');
 const {openPdf}=await import('data:text/javascript;base64,'+Buffer.from(source+'\n// two-openings').toString('base64'));
 const {sharedInspector,resetSharedInspector}=await import('../src/laplace/web/static_shared/workspace-inspector.mjs');
 const original={};for(const key of ['document','window','location','devicePixelRatio','getComputedStyle','IntersectionObserver','fetch','__pdfTestLibrary'])original[key]=globalThis[key];
 class Node{
  constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.attributes={};this.style={setProperty(key,value){this[key]=value;}};this.clientWidth=800;this.clientHeight=850;this.offsetHeight=100;this.scrollTop=0;this.handlers={};this.classList={add:()=>{}};}
  set innerHTML(_){this.controls=new Map();for(const selector of ['.wp-back','.wp-forward','h2','.wp-pages','.wp-status','.wp-download','.wp-tools','.wp-page','.wp-count','.wp-zoom','.wp-prev','.wp-next','.wp-minus','.wp-plus','.wp-fit','.wp-close','.wp-go']){const child=new Node(selector);this.controls.set(selector,child);this.append(child);}}
  querySelector(selector){return this.controls?.get(selector)||this.children.find(row=>'.'+row.className===selector)||null;}
  querySelectorAll(){return [];}
  setAttribute(key,value){this.attributes[key]=value;}getAttribute(key){return this.attributes[key];}
  append(...nodes){for(const node of nodes){node.parent=this;this.children.push(node);}}prepend(...nodes){for(const node of nodes)node.parent=this;this.children.unshift(...nodes);}after(node){this.parent?.append(node);}remove(){if(this.parent)this.parent.children=this.parent.children.filter(row=>row!==this);}
  addEventListener(type,callback){(this.handlers[type]??=[]).push(callback);}removeEventListener(type,callback){this.handlers[type]=(this.handlers[type]||[]).filter(fn=>fn!==callback);}showModal(){this.open=true;}close(){if(!this.open)return;this.open=false;for(const fn of [...(this.handlers.close||[])])fn();}getBoundingClientRect(){return {top:100,bottom:900};}getContext(){return {};}focus(){}click(){this.onclick?.({preventDefault(){}});}
 }
 const observers=[],body=new Node('body'),head=new Node('head');
 const page={getViewport:({scale})=>({width:600*scale,height:800*scale,scale,rawDims:{pageWidth:600,pageHeight:800},convertToViewportPoint:(x,y)=>[x,y].map(value=>value*scale)}),render:()=>({promise:Promise.resolve(),cancel(){}}),getTextContent:async()=>({items:[{str:'Statement'}]}),getAnnotations:async()=>[{rect:[10,20,110,35],unsafeUrl:'companion.pdf'}]};
 globalThis.document={activeElement:null,head,body,createElement:tag=>new Node(tag),querySelector:()=>null,querySelectorAll:()=>[]};globalThis.location={href:base,origin:'http://127.0.0.1:8771'};globalThis.window={addEventListener(){},removeEventListener(){}};globalThis.devicePixelRatio=2;globalThis.getComputedStyle=()=>({paddingTop:'0',paddingBottom:'0'});globalThis.IntersectionObserver=class{constructor(callback){this.callback=callback;observers.push(this);this.items=[];}observe(node){this.items.push(node);}disconnect(){}};
 let destroyed=0;globalThis.__pdfTestLibrary={GlobalWorkerOptions:{},getDocument:()=>({promise:Promise.resolve({numPages:3,getPage:async()=>page,getMetadata:async()=>({info:{}})}),destroy:async()=>{destroyed++;}}),TextLayer:class{constructor({container,textContentSource}){this.container=container;this.text=textContentSource.items[0].str;}async render(){this.container.textContent=this.text;}cancel(){}}};
 globalThis.fetch=async()=>({ok:true,json:async()=>({kind:'pdf',url:'/research/artifact?project=book&path=companion.pdf&scope=project',label:'Companion',notice:'Current companion'})});
 const tick=()=>new Promise(resolve=>setImmediate(resolve));
 resetSharedInspector();const inspector=sharedInspector();
 try{
  await openPdf(pdf,'Parent');const parent=body.children.at(-1);const sheet=observers.at(-1).items[0];observers.at(-1).callback([{target:sheet,isIntersecting:true}]);await tick();await tick();
  assert.equal(inspector.current.kind,'pdf');assert.equal(inspector.current.title,'Parent');assert.equal(parent.dataset.inspector,'pdf');
  parent.querySelector('.wp-page').value=2;parent.scrollTop=300;   // the person is on page 2
  const link=sheet.querySelector('.wp-annotation-layer').children[0];link.click();await tick();await tick();await tick();
  const companion=body.children.at(-1);
  assert.notEqual(companion,parent,'the companion is a second REAL viewer');assert.equal(parent.open,false,'the parent was replaced through adoption');assert.equal(parent.dataset.inspectorReplaced,'true');assert.equal(destroyed,1,'the replaced parent released its loading task');
  assert.equal(inspector.current.title,'Companion');assert.deepEqual(inspector.trail.map(e=>[e.title,e.descriptor,e.retainsDialog]),[['Parent','factory',false]]);assert.ok(inspector.trail[0].pin?.position,'the parent pinned its reading position to its trail entry');
  assert.equal(companion.children[0].className,'inspector-back');assert.equal(companion.children[0].textContent,'Back to Parent');
  const parentPosition=inspector.trail[0].pin.position;
  await companion.children[0].onclick();await tick();await tick();await tick();
  const reopened=body.children.at(-1);assert.notEqual(reopened,parent);assert.notEqual(reopened,companion);assert.equal(companion.open,false);assert.equal(inspector.current.title,'Parent');assert.deepEqual(inspector.trail,[]);
  assert.equal(reopened.controls.get('h2').textContent,'Parent');assert.equal(destroyed,2);
  assert.ok(source.includes('initialPosition:pin?.position||args.initialPosition||null'),'the factory reopens at the pinned position');assert.deepEqual(parentPosition,{page:parentPosition.page,fraction:parentPosition.fraction});
  reopened.querySelector('.wp-close').click();assert.equal(inspector.current,null);
 }finally{resetSharedInspector();for(const [key,value]of Object.entries(original)){if(value===undefined)delete globalThis[key];else globalThis[key]=value;}}
});

