import test from 'node:test';import assert from 'node:assert/strict';import {readFile} from 'node:fs/promises';
// the Markdown note renderer lives in workspace-inspection.mjs (M5 S2 F1); the callbacks below are the inspection owner's
const source=(await import('./helpers/workspace_source.mjs')).workspaceSource(),inspectionSource=await readFile(new URL('../src/laplace/web/static_shared/workspace-inspection.mjs',import.meta.url),'utf8');const code=inspectionSource.slice(inspectionSource.indexOf('export function artifactMarkdownBlocks('),inspectionSource.indexOf('export function mountInspection('));const dependencies=`import {messageLinkParts,artifactHumanTarget,ownerHumanTarget,markdownProtectedRanges} from '${new URL('../src/laplace/web/static_shared/workspace-session.mjs',import.meta.url).href}';const E=(tag,text='')=>{const node=document.createElement(tag);node.textContent=text;return node;};`;const {artifactMarkdownBlocks,artifactInlineParts,renderArtifactMarkdown}=await import('data:text/javascript;base64,'+Buffer.from(dependencies+code).toString('base64'));
test('research notes retain headings, paragraphs, lists, complete formula blocks and code',()=>{const blocks=artifactMarkdownBlocks('# Reading record\n\nThe conclusion.\n\n\\[\nH(W\\mid C)\\ge0\n\\]\n\n- Assumption one\n- Assumption two\n\n```python\nprint("not executed")\n```');assert.deepEqual(blocks.map(block=>block.kind),['heading','paragraph','paragraph','list','code']);assert.equal(blocks[2].text,'\\[\nH(W\\mid C)\\ge0\n\\]');assert.equal(blocks[3].items.length,2);assert.equal(blocks[4].text,'print("not executed")');});

const literalText=parts=>parts.map(part=>part.children?literalText(part.children):part.text).join('');
test('actual reflexivity note symbols remain literal outside explicit math delimiters',()=>{
 const line='If μ*=T(μ*) and h*=ℛ(π_*μ*), then μ*=μ_h*...';const parts=artifactInlineParts(line);assert.equal(literalText(parts),line);assert.ok(parts.every(part=>part.kind==='text'));
 const scale='C(ε)...~V_d...';assert.equal(literalText(artifactInlineParts(scale)),scale);assert.ok(!literalText(artifactInlineParts(scale)).includes('\u00a0'));
});
test('Markdown flanking preserves notation and still permits separated emphasis and code',()=>{
 const parts=artifactInlineParts('**A premise** and *an emphasis*, with `μ*=T(μ*)` and μ* = μ_h*.');assert.equal(parts[0].kind,'strong');assert.ok(parts.some(part=>part.kind==='em'));assert.ok(parts.some(part=>part.kind==='code'&&part.text==='μ*=T(μ*)'));assert.ok(literalText(parts).endsWith('μ* = μ_h*.'));
 assert.equal(literalText(artifactInlineParts('a*b*c and V_d and plain ~ range')),'a*b*c and V_d and plain ~ range');
});
test('only explicit mathematics is sent to the math renderer in Markdown notes',()=>{
 const parts=artifactInlineParts(String.raw`Plain \mu* ~ V_d, then $\mu^*=T(\mu^*)$ and \[ C(\epsilon) \sim V_d \].`);assert.equal(parts.filter(part=>part.kind==='math').length,2);assert.equal(parts[0].text,String.raw`Plain \mu* ~ V_d, then `);assert.ok(parts.filter(part=>part.kind==='math').every(part=>part.text.startsWith('$')||part.text.startsWith('\\[')));
});

const domNode=(tag,text='')=>({tag,textContent:text,children:[],style:{},attrs:{},setAttribute(k,v){this.attrs[k]=v;},append(...nodes){this.children.push(...nodes);},replaceChildren(...nodes){this.children=nodes;}});
const allNodes=node=>[node,...node.children.flatMap(allNodes)];
test('native owner links in a real guide table share safe inline rendering and exact namespaces',async()=>{
 const original=globalThis.document;try{globalThis.document={createElement:domNode,createTextNode:text=>domNode('#text',text)};
 const target={owner:'repository',repository:'laplace',path:'src/atlas/store.py'};
 const work='/work/state?'+new URLSearchParams({project:'writing-system-architecture',view:'detail',id:'WORK-atlas-receipt-reconciliation-20261008',limit:'1'});
 const material='/projects/material-references?'+new URLSearchParams({project:'writing-system-architecture',view:'preview',target:JSON.stringify(target),limit:'16000',offset:'0'});
 const text=`Prior paragraph\n\n| Reading | Result |\n| :--- | ---: |\n| [**Work**](${work}) | **PASS** |\n| [Source](${material}) | \`a|b\` and escaped \\| |\nFollowing paragraph`;
 const blocks=artifactMarkdownBlocks(text);assert.deepEqual(blocks.map(b=>b.kind),['paragraph','table','paragraph']);assert.equal(blocks[1].rows.length,2);
 const host=domNode('div'),opened=[];await renderArtifactMarkdown(host,text,{project:'selected',renderMath:async()=>{},onInspectOwner:(...args)=>opened.push(args),onOpenArtifact:()=>assert.fail('Owner route is never a filename')});
 const nodes=allNodes(host),table=nodes.find(n=>n.tag==='table');assert.ok(table);assert.equal(nodes.filter(n=>n.tag==='th').length,2);assert.equal(nodes.filter(n=>n.tag==='td').length,4);
 assert.equal(nodes.find(n=>n.tag==='th').attrs.scope,'col');assert.ok(nodes.some(n=>n.tag==='strong'&&literalText([{text:n.children[0].textContent}])==='PASS'));
 const links=nodes.filter(n=>n.tag==='a');await links[0].onclick({preventDefault(){}});await links[1].onclick({preventDefault(){}});
 assert.equal(opened[0][0].kind,'work');assert.equal(opened[0][0].project,'writing-system-architecture');assert.equal(opened[0][0].id,'WORK-atlas-receipt-reconciliation-20261008');assert.equal(opened[0][0].http.url,work);
 assert.equal(opened[1][0].kind,'material-source');assert.deepEqual(opened[1][0].target,target);assert.equal(opened[1][0].http.url,material);
 assert.equal(nodes.find(n=>n.tag==='code').textContent,'a|b');assert.equal(nodes.filter(n=>n.tag==='th')[1].style.textAlign,'right');
 }finally{globalThis.document=original;}
});
test('table recognition keeps malformed source literal and protects code and escaped cells',()=>{
 for(const text of ['A | B\n--- | --- | ---\nx | y','A | B\n--- | ---\nx | y | hidden'])assert.ok(artifactMarkdownBlocks(text).every(b=>b.kind!=='table'),text);
 assert.equal(artifactMarkdownBlocks('```md\n| A | B |\n| --- | --- |\n| x | y |\n```')[0].kind,'code');
 const table=artifactMarkdownBlocks('| A | B |\n| :---: | --- |\n| ``x|y`` | `a\\|b` and \\| |')[0];assert.equal(table.kind,'table');assert.equal(table.align[0],'center');assert.deepEqual(table.rows,[['``x|y``','`a|b` and \\|']]);
});
test('active A reader traverses Work B to B Markdown and a relative B artifact without borrowing A',async()=>{
 const harness=await import('./helpers/evidence_reader_harness.mjs'),d=harness.installDOM();try{
 const scope={conversation:'WS-A',selection:'chapter-A',draft:'UNSENT A'},calls=[];
 const workURL='/work/state?project=B&view=detail&id=WORK-B';
 const guide=harness.transport('[Evidence](evidence.md)'),evidence=harness.transport('B EVIDENCE');
 const request=async url=>{calls.push(url);const parsed=new URL(url,'http://localhost');assert.equal(parsed.searchParams.get('project'),'B');
  if(parsed.pathname==='/work/state')return {project:'B',view:'detail',task:{id:'WORK-B',title:'B work',status:'done',evidence_reads:[{purpose:'Read B guide',http:{method:'GET',url:'/research/artifact?project=B&path=guide.md&scope=project'}}]},blockers:[],children:{items:[]},dependants:{items:[]},allowed_actions:{},read_cut:{revision:'cut'}};
  return parsed.searchParams.get('path')==='guide.md'?guide.request(url):evidence.request(url);
 };
 // Execute the production workspace callback contract, bound to active A.
 const callbacks=source.slice(source.indexOf('  function renderSavedMarkdown('),source.indexOf('\n  return {savedMarkdown'));
 const readerURL=new URL('../src/laplace/web/static_shared/writing-artifact.mjs',import.meta.url).href;
 const ownerURL=new URL('../src/laplace/web/static_shared/writing-owner-read.mjs',import.meta.url).href;
 const moduleCode=`import {openArtifact as openEvidenceArtifact} from '${readerURL}';import {qualifiedOwnerHTTP} from '${ownerURL}';const project='A';let pending;const session={guard:fn=>pending=Promise.resolve(fn())};const inspector={adopt(){return {depth:0};}};const api=globalThis.__guideNamespaceRequest;const renderArtifactMarkdown=globalThis.__guideNamespaceRenderer;const discussion={session:()=>session,generateProfile:()=>{}},work={reload:async()=>{}},home={refreshStyle:async()=>{}};${callbacks};export {inspectOwnerRead,inspectProjectArtifact};export const last=()=>pending;`;
 globalThis.__guideNamespaceRequest=request;globalThis.__guideNamespaceRenderer=(host,text,options)=>renderArtifactMarkdown(host,text,{...options,renderMath:async()=>{}});
 const current=await import('data:text/javascript;base64,'+Buffer.from(moduleCode).toString('base64'));
 await current.inspectProjectArtifact(workURL,'Work B',{ownerRead:{http:{method:'GET',url:workURL}}});await harness.findButton(d.dialogs()[0],'Read B guide').click();
 const link=d.dialogs().at(-1).querySelectorAll('a').find(n=>n.textContent==='Evidence');await link.click();await current.last();
 assert.match(harness.bodyOf(d.dialogs().at(-1)).textContent,/B EVIDENCE/);assert.equal(calls.filter(url=>new URL(url,'http://localhost').pathname==='/work/state').length,1);
 assert.deepEqual(scope,{conversation:'WS-A',selection:'chapter-A',draft:'UNSENT A'});assert.equal(d.editor.value,'UNSAVED manuscript');
 while(d.dialogs().length)d.dialogs().at(-1).close();
 }finally{delete globalThis.__guideNamespaceRequest;delete globalThis.__guideNamespaceRenderer;d.restore();}
});
test('guide claim links retain exact namespaces and reach the existing readable concept view',async()=>{
 const original=globalThis.document;try{
 globalThis.document={createElement:domNode,createTextNode:text=>domNode('#text',text)};
 const host=domNode('div'),inspected=[],artifacts=[];
 const project='other project',node='res:retention-and-projection';
 const uri='/concepts/state?'+new URLSearchParams({project,node});
 await renderArtifactMarkdown(host,`[Current custody observation](${uri})`,{project:'selected',renderMath:async()=>{},onOpenArtifact:(...args)=>artifacts.push(args),onInspectClaim:target=>inspected.push(target)});
 const link=allNodes(host).find(n=>n.tag==='a'),q=new URL(link.href,'http://localhost').searchParams;
 assert.equal(new URL(link.href,'http://localhost').pathname,'/project');
 assert.equal(q.get('workspace'),'writing');assert.equal(q.get('corpus'),project);assert.equal(q.get('view'),'argument');assert.equal(q.get('structure'),null);assert.equal(q.get('node'),node);
 assert.equal(link.target,undefined);await link.onclick({preventDefault(){}});
 assert.deepEqual(inspected,[{project,node,href:link.href}]);assert.deepEqual(artifacts,[]);
 for(const bad of ['/concepts/state?node=claim:one','/concepts/state?project=p','/concepts/state?project=p&node=a&node=b','/concepts/state?project=p&node=a&project=q','/concepts/state?project=p&node=a#other','javascript:alert(1)']){
  const refused=domNode('div');await renderArtifactMarkdown(refused,`[claim](${bad})`,{project:'selected',renderMath:async()=>{}});
  assert.equal(allNodes(refused).filter(n=>n.tag==='a').length,0,bad);
 }
 }finally{globalThis.document=original;}
});
test('whole inline owner URLs are readable without relying on provider Markdown formatting',async()=>{
 const original=globalThis.document;try{globalThis.document={createElement:domNode,createTextNode:text=>domNode('#text',text)};
 const pin='e'.repeat(64),url='/research/artifact?'+new URLSearchParams({project:'book',scope:'project',path:'result with spaces.txt',expected_sha256:pin,owner:'writing-artifact'}),host=domNode('div'),opened=[];
 await renderArtifactMarkdown(host,'Read `'+url+'`.',{project:'book',renderMath:async()=>{},onOpenArtifact:(...args)=>opened.push(args)});
 const link=allNodes(host).find(n=>n.tag==='a');assert.equal(link.href,url);assert.equal(link.children[0].textContent,url);
 link.onclick({preventDefault(){}});assert.equal(opened[0][0],'result with spaces.txt');assert.equal(opened[0][2].expectedSha256,pin);assert.equal(opened[0][2].artifactOwner,'writing-artifact');
 for(const text of ['```text\n'+url+'\n```','`prefix '+url+'`','`'+url+' '+url+'`','`ordinary code`','`https://outside.invalid'+url+'`','`'+url.replace('project=book','project=other')+'`','`'+url.replace('&expected_sha256='+pin,'')+'`','`'+url.replace(pin,'bad')+'`','`'+url+'&project=other`']){
  const node=domNode('div');await renderArtifactMarkdown(node,text,{project:'book',renderMath:async()=>{}});assert.equal(allNodes(node).filter(n=>n.tag==='a').length,0,text);
 }
 }finally{globalThis.document=original;}
});
test('the shared final-reply reader renders prose, lists, explicit math and guarded links without changing bare science',async()=>{
 const original=globalThis.document;try{globalThis.document={createElement:domNode,createTextNode:text=>domNode('#text',text)};const host=domNode('div'),math=[],opened=[];
 const text=String.raw`## Findings

If μ*=T(μ*) and h*=ℛ(π_*μ*), then μ*=μ_h*. C(ε)~V_d.

- **Premise** with \(H(W\mid C)\ge0\).
- Inspect [reading record](<research/source reading.md>) and [primary source](https://example.org/paper).

${'`literal μ* ~ V_d`'}

[unsafe](javascript:alert(1)) <script>bad()</script>`;
 await renderArtifactMarkdown(host,text,{project:'book',onOpenArtifact:(...args)=>opened.push(args),renderMath:(node,tex)=>{math.push(tex);node.append(domNode('math',tex));}});
 const nodes=allNodes(host);assert.equal(nodes.filter(node=>node.tag==='h3').length,1);assert.equal(nodes.filter(node=>node.tag==='li').length,2);assert.ok(nodes.some(node=>node.tag==='strong'));assert.deepEqual(math,[String.raw`\(H(W\mid C)\ge0\)`]);assert.ok(nodes.some(node=>node.textContent.includes('μ*=T(μ*) and h*=ℛ(π_*μ*), then μ*=μ_h*. C(ε)~V_d.')));assert.ok(nodes.some(node=>node.tag==='code'&&node.textContent==='literal μ* ~ V_d'));
 const links=nodes.filter(node=>node.tag==='a');assert.equal(links.length,2);assert.match(links[0].href,/^\/research\/artifact\?/);assert.equal(new URL(links[0].href,'http://localhost').searchParams.get('project'),'book');let prevented=false;links[0].onclick({preventDefault(){prevented=true;}});assert.ok(prevented);assert.deepEqual(opened,[['research/source reading.md','reading record']]);assert.equal(links[1].rel,'noopener noreferrer');assert.ok(!nodes.some(node=>node.tag==='script'));
 }finally{globalThis.document=original;}
});

test('owner artifact URLs open in the in-app reader with exact decoded scope, digest and receipt',async()=>{
 const original=globalThis.document;try{globalThis.document={createElement:domNode,createTextNode:text=>domNode('#text',text)};const host=domNode('div'),opened=[],pin='a'.repeat(64);
 const url='/research/artifact?'+new URLSearchParams({project:'p',scope:'manuscript',path:'result notes/check α.txt',expected_sha256:pin,artifact_id:'ART-proof'});
 await renderArtifactMarkdown(host,`[exact saved result](${url})`,{project:'p',renderMath:async()=>{},onOpenArtifact:(...args)=>opened.push(args)});
 const link=allNodes(host).find(n=>n.tag==='a');let prevented=false;link.onclick({preventDefault(){prevented=true;}});
 assert.equal(prevented,true);assert.equal(link.target,undefined);assert.equal(link.href,url);
 assert.deepEqual(opened,[['result notes/check α.txt','exact saved result',{path:'result notes/check α.txt',scope:'manuscript',expectedSha256:pin,artifactId:'ART-proof'}]]);
 }finally{globalThis.document=original;}
});

test('only exact retained result aliases resolve; invented provider cwd links remain untouched',async()=>{
 const original=globalThis.document;try{globalThis.document={createElement:domNode,createTextNode:text=>domNode('#text',text)};const host=domNode('div'),opened=[],pin='b'.repeat(64),canonical='/research/artifact?'+new URLSearchParams({project:'p',scope:'project',path:'results/note.txt',expected_sha256:pin,artifact_id:'ART-result'}),bad='/made-up/session/project/results/note.txt';
 await renderArtifactMarkdown(host,`[saved](results/note.txt) and [original invented path](${bad})`,{project:'p',renderMath:async()=>{},resultLinks:[{url:canonical,aliases:['ART-result','results/note.txt','owned project/results/note.txt']}],onOpenArtifact:(...args)=>opened.push(args)});
 const links=allNodes(host).filter(n=>n.tag==='a');links[0].onclick({preventDefault(){}});links[1].onclick({preventDefault(){}});
 assert.equal(links[0].href,canonical);assert.equal(opened[0][2].expectedSha256,pin);assert.equal(opened[1][0],bad);assert.equal(opened[1][2],undefined);
 }finally{globalThis.document=original;}
});

// These controls run the actual selected-read doors and shared inspection host.
const selectedHarness=await import('./helpers/evidence_reader_harness.mjs');
const {openArtifact:openSelectedArtifact}=await import('../src/laplace/web/static_shared/writing-artifact.mjs');
const {mountOperatorWork:mountSelectedWork}=await import('../src/laplace/web/static_shared/workspace-work.mjs');
const {mountSharedReferences:mountSelectedReferences}=await import('../src/laplace/web/static_shared/workspace-material.mjs');
const {mountHistory:mountSelectedHistory}=await import('../src/laplace/web/static_shared/workspace-history.mjs');
const selectedURL='/projects/material-references?'+new URLSearchParams({project:'P',view:'preview',target:JSON.stringify({owner:'repository',repository:'declared',path:'atlas/store.py'}),limit:16000});
const selectedSource=(text='OBSERVED SOURCE')=>({schema_version:'laplace.material-reference-source/1',project:'P',id:null,target:{owner:'repository',repository:'declared',path:'atlas/store.py'},currentness:'UNBOUND',current_revision:'pin',owner_result:{content:text}});
const selectedDetail=id=>({project:'P',view:'detail',task:{id,title:id,status:'done',evidence_reads:[{path:'atlas/store.py',consumed_revision:'pin',http:{method:'GET',url:selectedURL}}]},blockers:[],children:{items:[]},dependants:{items:[]}});
for(const end of ['close','selection','destroy'])for(const outcome of ['success','error'])test(`actual Work door discards delayed ${outcome} after ${end}`,async()=>{
 const d=selectedHarness.installDOM();try{
 const host=new selectedHarness.Node('section');d.body.append(host);let finish;const calls=[];
 const request=async path=>{calls.push(path);if(path.startsWith('/work/state'))return selectedDetail(new URL(path,'http://local').searchParams.get('id'));return new Promise((resolve,reject)=>{finish=()=>outcome==='success'?resolve(selectedSource('STALE RESULT')):reject(Error('STALE ERROR'));});};
 const controller=await mountSelectedWork(host,{project:'P',summary:{tasks:[selectedDetail('A').task]},initialWork:'A',request});
 const opener=selectedHarness.findButton(host,'Read evidence');assert.ok(opener,host.textContent);const pending=opener.click();await new Promise(resolve=>setImmediate(resolve));
 assert.equal(d.dialogs().length,1);const dialog=d.dialogs()[0];assert.match(dialog.textContent,/Reading the exact owner/);assert.equal(document.activeElement.tag,'h2');
 if(end==='close')dialog.close();else if(end==='selection')await controller.select('B');else controller.destroy();
 finish();await pending;assert.equal(d.dialogs().length,0);assert.ok(!d.body.textContent.includes('STALE RESULT'));assert.ok(!d.body.textContent.includes('STALE ERROR'));assert.equal(calls.filter(path=>path===selectedURL).length,1);
 controller.destroy();
 }finally{d.restore();}
});
test('actual Work evidence reveals exact matched observation and Close restores opener and scroll',async()=>{
 const d=selectedHarness.installDOM();try{
 const host=new selectedHarness.Node('section');host.scrollTop=613;d.body.append(host);
 const c=await mountSelectedWork(host,{project:'P',summary:{tasks:[selectedDetail('A').task]},initialWork:'A',request:async path=>path.startsWith('/work/state')?selectedDetail('A'):selectedSource()});
 const opener=selectedHarness.findButton(host,'Read evidence');await opener.click();const dialog=d.dialogs()[0],panel=dialog.querySelector('.artifact-current');
 assert.match(panel.textContent,/Work evidence: recorded revision matches observed source/);assert.equal(panel.revealed,undefined,'No ancestor scrollIntoView');assert.equal(document.activeElement,panel);host.scrollTop=0;
 await selectedHarness.findButton(dialog,'Close').click();assert.equal(d.dialogs().length,0);assert.equal(document.activeElement,opener);assert.equal(host.scrollTop,613);c.destroy();assert.equal(d.editor.value,'UNSAVED manuscript');
 }finally{d.restore();}
});
test('same shared panel traverses graph, selected Work and evidence without duplicate dialogs or first-row selection',async()=>{
 const d=selectedHarness.installDOM();try{
 const calls=[],graph='/work/state?project=P&view=graph&parent_work_id=A';
 const dialog=await openSelectedArtifact({ownerRead:{http:{method:'GET',url:graph}},label:'Relationships',request:async path=>{calls.push(path);if(path===graph)return {project:'P',view:'graph',read_cut:{revision:'cut'},nodes:[{id:'A',title:'A',status:'done'}],edges:[{source:'A',target:'B',kind:'requires'}]};if(path.startsWith('/work/state'))return selectedDetail('B');return selectedSource();}});
 await selectedHarness.findButton(dialog,'B').click();assert.match(dialog.textContent,/B/);await selectedHarness.findButton(dialog,'Read evidence').click();
 assert.equal(d.dialogs().length,1);assert.equal(dialog.querySelectorAll('.artifact-current').length,1);assert.match(dialog.textContent,/OBSERVED SOURCE/);assert.equal(calls.length,3);dialog.close();
 }finally{d.restore();}
});
test('neighbourhood continuation refuses a different namespace/parent/cut before fetching it',async()=>{
 const d=selectedHarness.installDOM();try{
 for(const bad of ['/work/state?project=OTHER&view=graph&parent_work_id=A&as_of=cut','/work/state?project=P&view=graph&parent_work_id=OTHER&as_of=cut','/work/state?project=P&view=graph&parent_work_id=A&as_of=OTHER']){
 let reads=0;const dialog=await openSelectedArtifact({ownerRead:{http:{method:'GET',url:'/work/state?project=P&view=graph&parent_work_id=A'}},label:'Relationships',request:async()=>{reads++;return {project:'P',view:'graph',read_cut:{revision:'cut'},nodes:[],edges:[],pagination:{next_read:{http:{method:'GET',url:bad}}}};}});
 await selectedHarness.findButton(dialog,'More neighbourhood').click();assert.equal(reads,1);assert.match(dialog.textContent,/continuation changed/);dialog.close();
 }
 }finally{d.restore();}
});
for(const missing of [false,true])test('Material deep-link reads only its addressed binding, including '+(missing?'missing target':'off-page target'),async()=>{
 const d=selectedHarness.installDOM();try{
 const host=new selectedHarness.Node('section');d.body.append(host);const calls=[];
 const controller=await mountSelectedReferences(host,{project:'P',selectedBinding:'MAT-exact',draft:{path:'UNSENT PATH',owner:'declared'},request:async path=>{calls.push(path);const q=new URL(path,'http://local').searchParams;if(q.get('view')==='source'){assert.equal(q.get('id'),'MAT-exact');if(missing)throw Error('Choose an exact material reference id');return {...selectedSource(),id:'MAT-exact'};}return {revision:'membership',references:[],owners:{repositories:[{id:'declared'}]},total:500,next_offset:20};}});
 assert.equal(calls.length,2);assert.equal(calls.filter(path=>path.includes('view=source')).length,1);assert.equal(calls.filter(path=>path.includes('offset=20')).length,0);assert.equal(d.dialogs().length,1);
 assert.match(d.dialogs()[0].textContent,missing?/exact material reference id/:/OBSERVED SOURCE/);assert.equal(controller.capture().path,'UNSENT PATH');controller.destroy();assert.equal(d.dialogs().length,0);
 }finally{d.restore();}
});
test('Material shared host rejects a delayed old namespace and mismatched binding/consumer',async()=>{
 const d=selectedHarness.installDOM();try{
 let current=true,finish;const host=new selectedHarness.Node('section');d.body.append(host);
 const pending=mountSelectedReferences(host,{project:'P',selectedBinding:'MAT-exact',isCurrent:()=>current,request:path=>path.includes('view=source')?new Promise(resolve=>{finish=()=>resolve({...selectedSource('OLD NAMESPACE'),id:'MAT-exact'});}):Promise.resolve({references:[],owners:{repositories:[]},total:0})});
 await new Promise(resolve=>setImmediate(resolve));assert.equal(d.dialogs().length,1);current=false;finish();const c=await pending;assert.equal(d.dialogs().length,0);assert.ok(!d.body.textContent.includes('OLD NAMESPACE'));c.destroy();
 for(const change of [{id:'MAT-other'},{project:'OTHER'}]){const dialog=await openSelectedArtifact({ownerRead:{http:{method:'GET',url:'/projects/material-references?project=P&view=source&id=MAT-exact'}},request:async()=>({...selectedSource(),id:'MAT-exact',...change}),label:'Selected binding'});assert.match(dialog.textContent,/different|incompatible/);dialog.close();}
 }finally{d.restore();}
});
test('browser return closes the inspector and detached opener has a safe connected fallback',async()=>{
 const d=selectedHarness.installDOM(),oldWindow=globalThis.window,listeners=new Map();try{
 globalThis.window={addEventListener:(name,fn)=>listeners.set(name,fn),removeEventListener:(name,fn)=>{if(listeners.get(name)===fn)listeners.delete(name);}};
 const opener=new selectedHarness.Node('button');d.body.append(opener);opener.focus();const dialog=await openSelectedArtifact({ownerRead:{http:{method:'GET',url:selectedURL}},request:async()=>selectedSource(),label:'Evidence'});opener.remove();listeners.get('popstate')();assert.equal(d.dialogs().length,0);assert.equal(document.activeElement,d.body);assert.equal(listeners.size,0);assert.ok(!dialog.open);
 }finally{globalThis.window=oldWindow;d.restore();}
});
test('actual History door presents exact failure arguments/recovery in the shared host and never retries',async()=>{
 const d=selectedHarness.installDOM();try{
 const host=new selectedHarness.Node('section');host.closest=()=>host;d.body.append(host);const calls=[];
 const item={id:'activity:journal:TOOLFAIL-one',summary:'Source read failed',actor:'Agent',category:'session',detail_available:true};
 const c=await mountSelectedHistory(host,{project:'P',request:async path=>{calls.push(path);const q=new URL(path,'http://local').searchParams;if(q.get('view')==='record')return {project:'P',record_kind:'writing-tool-failure',text:'Original error',record:{id:'TOOLFAIL-one',project:'P',turn_id:'WT-one',operation:'author_history',payload:{view:'activity',http:true},error:'Unexpected http',recovery:{help:{operation:'help',payload:{operation:'author_history'}}}}};if(q.has('id'))return {item};if(q.get('view')==='telemetry')throw Error('No historical telemetry');return {items:[item],pagination:{total:1}};}});
 await selectedHarness.findButton(host,'Source read failed').click();assert.equal(calls.some(path=>path.includes('view=record')),false);await selectedHarness.findButton(host,'Read complete saved record').click();const dialog=d.dialogs()[0];
 assert.match(dialog.textContent,/Recorded arguments/);assert.match(dialog.textContent,/author_history/);assert.match(dialog.textContent,/Unexpected http/);assert.match(dialog.textContent,/Historical instructions, not a current contract/);assert.equal(calls.filter(path=>path.includes('view=record')).length,1);assert.ok(calls.every(path=>path.startsWith('/authoring/history?')));c.destroy();assert.equal(d.dialogs().length,0);
 }finally{d.restore();}
});

test('failure current-help click uses original project/turn and stays separate from its recorded outcome',async()=>{
 const d=selectedHarness.installDOM();try{
 const calls=[],recordURL='/authoring/history?project=P&view=record&id=activity%3Ajournal%3AF';
 const record={project:'P',record_kind:'writing-tool-failure',record:{id:'F',project:'P',turn_id:'WT-original',operation:'author_history',error:'RECORDED FAILURE',recovery:{help:{operation:'help',payload:{operation:'author_history',context:{view:'activity',limit:3}}}}}};
 const dialog=await openSelectedArtifact({ownerRead:{http:{method:'GET',url:recordURL}},label:'Failure',request:async path=>{calls.push(path);if(path===recordURL)return record;const q=new URL(path,'http://local').searchParams;assert.equal(q.get('project'),'P');assert.equal(q.get('turn_id'),'WT-original');assert.deepEqual(JSON.parse(q.get('context')),{view:'activity',limit:3});return {project:'P',inspection:{binding:'recorded-turn',turn_id:'WT-original',mode:'research'},help:{schema_version:'current-owner',digest:'current-digest',requested_operation:'author_history',action:{input:{type:'object'},permitted:true}}};}});
 assert.match(dialog.textContent,/RECORDED FAILURE/);await selectedHarness.findButton(dialog,'Inspect current tool help').click();assert.match(dialog.textContent,/Current recovery contract/);assert.match(dialog.textContent,/no retry or resolution is inferred/);assert.equal(d.dialogs().length,1);assert.equal(dialog.querySelectorAll('.artifact-current').length,1);
 await selectedHarness.findButton(dialog,'Back to recorded failure').click();assert.match(dialog.textContent,/RECORDED FAILURE/);assert.equal(calls.length,3);assert.ok(calls.every(path=>path.startsWith('/authoring/history?')||path.startsWith('/authoring/help?')));assert.equal(record.record.error,'RECORDED FAILURE');dialog.close();
 }finally{d.restore();}
});
test('current-help transport refuses unbound/ambiguous selectors and mismatched owner scope',async()=>{
 const {currentHelpRead,ownerHumanTarget}=await import('../src/laplace/web/static_shared/writing-owner-read.mjs');
 const record={project:'P',turn_id:'WT-original',recovery:{help:{operation:'help',payload:{operation:'source'}}}};
 assert.equal(currentHelpRead({...record,turn_id:null}),null);assert.equal(currentHelpRead({...record,recovery:{help:{operation:'help',payload:{operation:'source',project:'OTHER'}}}}),null);assert.equal(currentHelpRead({...record,recovery:{help:{operation:'help',payload:{operation:'source',context:[]}}}}),null);
 for(const url of ['/authoring/help?project=P&mode=research&operation=source','/authoring/help?project=P&turn_id=WT&turn_id=OTHER','/authoring/help?project=P&turn_id=WT&context=[]','/authoring/help?project=P&turn_id=WT&arbitrary=yes'])assert.equal(ownerHumanTarget(url),null,url);
 const d=selectedHarness.installDOM();try{for(const change of [{project:'OTHER'},{inspection:{binding:'unbound-human',turn_id:null,mode:'research'}},{inspection:{binding:'recorded-turn',turn_id:'OTHER',mode:'research'}},{help:{requested_operation:'OTHER'}}]){
 const dialog=await openSelectedArtifact({ownerRead:currentHelpRead(record),label:'Current contract',request:async()=>({project:'P',inspection:{binding:'recorded-turn',turn_id:'WT-original',mode:'research'},help:{requested_operation:'source'},...change})});assert.match(dialog.textContent,/different/);dialog.close();
 }}finally{d.restore();}
});
test('delayed current-help success or error cannot resurrect a closed inspector',async()=>{
 for(const error of [false,true]){const d=selectedHarness.installDOM();try{
 let finish,opened;const pending=openSelectedArtifact({ownerRead:{http:{method:'GET',url:'/authoring/help?project=P&turn_id=WT-original&operation=source'}},label:'Current contract',onOpen:dialog=>{opened=dialog;},request:()=>new Promise((resolve,reject)=>{finish=()=>error?reject(Error('OLD HELP ERROR')):resolve({project:'P',inspection:{binding:'recorded-turn',turn_id:'WT-original',mode:'research'},help:{requested_operation:'source',action:{prose:'OLD HELP'}}});})});
 opened.close();finish();await pending;assert.equal(d.dialogs().length,0);assert.ok(!d.body.textContent.includes('OLD HELP'));
 }finally{d.restore();}}
});

test('selected owner success/error settles aria-busy and a switched exact-history door never opens',async()=>{
 const d=selectedHarness.installDOM();try{
 for(const error of [false,true]){const dialog=await openSelectedArtifact({ownerRead:{http:{method:'GET',url:selectedURL}},label:'Source',request:async()=>{if(error)throw Error('CURRENT ERROR');return selectedSource();}});assert.equal(selectedHarness.bodyOf(dialog).getAttribute('aria-busy'),'false');dialog.close();}
 const {readAnalyticsRecord}=await import('../src/laplace/web/static_shared/workspace-analytics.mjs');let reads=0;
 await readAnalyticsRecord({http:{method:'GET',url:'/authoring/history?project=P&view=record&id=F'}},{project:'P',isCurrent:()=>false,request:async()=>{reads++;}});assert.equal(reads,0);assert.equal(d.dialogs().length,0);
 }finally{d.restore();}
});

test('shared long result/error reveals only the inner reading region and retains shell controls',async()=>{
 for(const error of [false,true]){
 const d=selectedHarness.installDOM();try{
 let activeDialog;const originalCreate=document.createElement;
 document.createElement=tag=>{const node=originalCreate(tag);node.scrollIntoView=()=>assert.fail('Ancestor scrolling would clip the Close/header');node.getBoundingClientRect=()=>{const reading=activeDialog?.querySelector('.artifact-reading-region');return {top:node.className==='artifact-current'?120+400-(reading?.scrollTop||0):120};};return node;};
 const dialog=await openSelectedArtifact({ownerRead:{http:{method:'GET',url:selectedURL}},label:'Full accessible evidence title',onOpen:node=>{activeDialog=node;node.scrollTop=0;node.querySelector('.artifact-reading-region').scrollTop=75;},request:async()=>{if(error)throw Error('CURRENT ERROR '.repeat(400));return selectedSource('LONG SOURCE\n'.repeat(1400));}});
 const reading=dialog.querySelector('.artifact-reading-region'),panel=dialog.querySelector('.artifact-current'),close=selectedHarness.findButton(dialog,'Close');
 assert.equal(reading.scrollTop,400);assert.equal(dialog.scrollTop,0);assert.equal(document.activeElement,panel);assert.deepEqual(panel.focusOptions,{preventScroll:true});assert.equal(close.parentElement.parentElement,dialog);assert.equal(dialog.querySelector('h2').parentElement,dialog);assert.equal(selectedHarness.bodyOf(dialog).parentElement,reading);assert.equal(dialog.querySelector('.artifact-raw').parentElement,reading);assert.equal(reading.getAttribute('role'),'region');assert.equal(reading.tabIndex,0);assert.equal(selectedHarness.bodyOf(dialog).getAttribute('aria-busy'),'false');
 await close.click();assert.equal(d.dialogs().length,0);
 }finally{d.restore();}
 }
});
test('raw record toggles stay in the same inner region and retain a single external Close',async()=>{
 const d=selectedHarness.installDOM();try{
 const value=selectedHarness.transport(JSON.stringify({rows:Array.from({length:1500},(_,i)=>({i,value:'x'.repeat(20)}))}));
 const dialog=await openSelectedArtifact({project:'P',path:'record.json',label:'Recorded evidence',request:value.request});
 const reading=dialog.querySelector('.artifact-reading-region'),body=selectedHarness.bodyOf(dialog),raw=dialog.querySelector('.artifact-raw');reading.scrollTop=700;
 await selectedHarness.findButton(dialog,'Show raw JSON / text').click();assert.equal(reading.scrollTop,0);assert.equal(body.hidden,true);assert.equal(raw.hidden,false);assert.equal(raw.parentElement,reading);assert.equal(d.dialogs().length,1);assert.equal(dialog.querySelectorAll('button').filter(node=>node.textContent==='Close').length,1);
 await selectedHarness.findButton(dialog,'Return to evidence view').click();assert.equal(raw.hidden,true);assert.equal(body.hidden,false);dialog.close();
 }finally{d.restore();}
});

// Browsers clear focus when a focused control is disabled; a plain property double hides this race.
function blurOnDisableDOM(){
 const d=selectedHarness.installDOM(),create=document.createElement;
 document.createElement=tag=>{const node=create(tag);if(tag==='button'){let disabled=false;Object.defineProperty(node,'disabled',{get:()=>disabled,set:value=>{disabled=value;if(value&&document.activeElement===node)d.body.focus();}});}return node;};
 return d;
}
async function historyOpenerFixture(requestRecord){
 const host=new selectedHarness.Node('section');host.closest=()=>host;host.scrollTop=611;document.body.append(host);
 const item={id:'activity:journal:F',summary:'Exact failed read',actor:'Agent',category:'session',detail_available:true};
 const controller=await mountSelectedHistory(host,{project:'P',request:async path=>{const q=new URL(path,'http://local').searchParams;if(q.get('view')==='record')return requestRecord();if(q.has('id'))return {item};if(q.get('view')==='telemetry')throw Error('No telemetry');return {items:[item],pagination:{total:1}};}});
 await selectedHarness.findButton(host,'Exact failed read').click();host.scrollTop=611;return {host,controller,opener:selectedHarness.findButton(host,'Read complete saved record')};
}
async function analyticsOpenerFixture(requestRecord){
 const {mountSessionAnalytics}=await import('../src/laplace/web/static_shared/workspace-analytics.mjs');
 const host=new selectedHarness.Node('section');host.insertBefore=(node,before)=>{node.parent=host;host.children.splice(host.children.indexOf(before),0,node);};host.scrollTop=477;document.body.append(host);
 const handle={operation:'author_history',payload:{view:'record',id:'activity:admission:WT-original'},http:{method:'GET',url:'/authoring/history?project=P&view=record&id=activity%3Aadmission%3AWT-original'}};
 const controller=await mountSessionAnalytics(host,{project:'P',initialProjection:'trace',request:async path=>{if(path===handle.http.url)return requestRecord();const q=new URL(path,'http://local').searchParams;return {schema_version:'laplace.session-analytics/1',project:'P',scope:'project',projection:q.get('projection'),filters:{scope:'project',projection:q.get('projection')},items:[{record:'writing-turn',project:'P',read_handle:handle}],pagination:{total:1},coverage:{selected_metadata_rows:1}};}});
 return {host,controller,opener:selectedHarness.findButton(host,'Inspect recorded basis')};
}
for(const [name,fixture,response]of [
 ['History',historyOpenerFixture,{project:'P',record:{id:'F',project:'P',error:'ORIGINAL ERROR'}}],
 ['analytics admission',analyticsOpenerFixture,{project:'P',record_kind:'writing-turn',record:{id:'WT-original',record:'writing-turn',project:'P'}}]
]){
 for(const fail of [false,true])test(`${name} retains explicit opener despite browser blur on disable and ${fail?'read error':'read success'}`,async()=>{
  const d=blurOnDisableDOM();try{
   const {host,controller,opener}=await fixture(async()=>{assert.notEqual(document.activeElement,opener);if(fail)throw Error('CURRENT READ ERROR');return response;});
   assert.ok(opener);const priorScroll=host.scrollTop;await opener.click();assert.equal(opener.disabled,false);assert.equal(d.dialogs().length,1);host.scrollTop=0;
   await selectedHarness.findButton(d.dialogs()[0],'Close').click();assert.equal(document.activeElement,opener);assert.equal(host.scrollTop,priorScroll);assert.equal(d.dialogs().length,0);controller.destroy();
  }finally{d.restore();}
 });
 test(`${name} loading Close uses safe focus and late completion never steals newer focus`,async()=>{
  const d=blurOnDisableDOM();try{
   let finish;const {controller,opener}=await fixture(()=>new Promise(resolve=>{finish=()=>resolve(response);}));
   const pending=opener.click();await new Promise(resolve=>setImmediate(resolve));assert.equal(opener.disabled,false,'Creation releases temporary launcher disable');assert.equal(d.dialogs().length,1);
   await selectedHarness.findButton(d.dialogs()[0],'Close').click();assert.equal(document.activeElement,opener);assert.equal(d.dialogs().length,0);
   const newer=new selectedHarness.Node('button');d.body.append(newer);newer.focus();finish();await pending;assert.equal(document.activeElement,newer);assert.equal(opener.disabled,false);assert.equal(d.dialogs().length,0);controller.destroy();
  }finally{d.restore();}
 });
 test(`${name} changed or destroyed projection refuses its late record without focus theft`,async()=>{
  const d=blurOnDisableDOM();try{
   let finish;const {controller,opener}=await fixture(()=>new Promise(resolve=>{finish=()=>resolve(response);}));const pending=opener.click();await new Promise(resolve=>setImmediate(resolve));controller.destroy();const newer=new selectedHarness.Node('button');d.body.append(newer);newer.focus();finish();await pending;assert.equal(d.dialogs().length,0);assert.equal(document.activeElement,newer);
  }finally{d.restore();}
 });
}
