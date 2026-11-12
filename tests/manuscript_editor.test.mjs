import {fixtures as effectFixtures} from './helpers/source_effect_fixture.mjs';
import {fileURLToPath} from 'node:url';
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import test from 'node:test';import assert from 'node:assert/strict';
import {Node,installDOM} from './helpers/evidence_reader_harness.mjs';
import {createManuscriptEditor,manuscriptPdfState,sourceDraftAttachment,hasStoredSourceDraft,sourceComparisonPlan,setupPanelPlacement,SETUP_PANEL} from '../src/laplace/web/static_shared/manuscript-editor.mjs';
import {templateWire} from './helpers/document_template_fixture.mjs';
const pin=letter=>'sha256:'+letter.repeat(64);
Object.defineProperty(Node.prototype,'firstChild',{configurable:true,get(){return this.children[0];}});
function deferred(){let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};}
function harness({visual=false,saveGate=null,storageMap=new Map(),readGate=null,documentOverride=null,saveError=null}={}){
 const dom=installDOM(),oldWindow=globalThis.window;globalThis.window={addEventListener(){},removeEventListener(){}};
 const host=new Node('div'),frame=new Node('iframe');host.append(frame);dom.body.append(host);let visualDraft=visual,editor,dirtyCallbacks,saves=0,refreshes=0,reads=0,documentReads=0;
 frame.contentWindow={walk:{editState:()=>({dirty:visualDraft}),captureFocus:()=>({block:'intro'}),restoreFocus(){},commitAll:async()=>{visualDraft=false;},refresh:async()=>{refreshes++;},flipState:()=>({open:false})}};
 const observed=file=>({schema_version:'laplace.projection-source/1',file,content:state.source_text?.[file]??(file==='main.tex'?'Original':'Other'),expected_source_digest:state.files.find(row=>row.file===file)?.expected_source_digest||pin('a'),selection_identity:state.selection_identity});
 const state=documentOverride||{selection_identity:pin('b'),schema_version:'laplace.current-document/1',selected_source:{root:'main.tex'},files:[{file:'main.tex'},{file:'other.tex'}],source_observation:{file_revisions:{'main.tex':pin('a')}},status:'STALE',current_build:{pdf:'main.pdf'},observation_coherence:{status:'MATCHED'}};
 const controller=createManuscriptEditor(host,{project:'book',frame,storage:{getItem:k=>storageMap.get(k),setItem:(k,v)=>storageMap.set(k,v),removeItem:k=>storageMap.delete(k)},request:async(path)=>{if(path.startsWith('/authoring/document'))documentReads++;return structuredClone(state);},sourceClient:{read:async({file})=>{reads++;if(readGate)await readGate(file);return observed(file);},save:async({observed,content})=>{saves++;if(saveError)throw saveError;if(saveGate)await saveGate.promise;return {ok:true,source_committed:true,file:observed.file,consumed_source_digest:observed.expected_source_digest,expected_source_digest:pin('c'),selection_identity:pin('b')};}},mountSourceEditor:async(host,options)=>{dirtyCallbacks=options;editor={text:options.content,pos:{anchor:0,head:0,scrollTop:0},getText(){return this.text;},capture(){return this.pos;},selection(){return {line_start:1,line_end:1,...this.pos};},setDocument(text,pos){this.text=text;this.pos=pos||{};},setReadOnly(value){this.readOnly=value;},focus(){},focusLine(){},destroy(){}};return editor;}});
 return {controller,host,frame,storageMap,type(text){editor.text=text;dirtyCallbacks.onChange(text,{anchor:text.length,head:text.length,scrollTop:12});},get editor(){return editor;},get saves(){return saves;},get reads(){return reads;},get documentReads(){return documentReads;},setDocument(value){Object.assign(state,value);},cleanup(){controller.destroy();dom.restore();globalThis.window=oldWindow;}};
}
test('dirty source survives Write switch and recreation, disables overlapping visual editing and retains exact guard',async()=>{const h=harness();await h.controller.observe();await h.controller.openSource();h.type('Draft');h.controller.showWrite();assert.equal(h.frame.inert,true);assert.equal(h.controller.hasDraft(),true);h.cleanup();const again=harness({storageMap:h.storageMap});await again.controller.observe();await again.controller.openSource();assert.equal(again.editor.text,'Draft');assert.deepEqual(again.controller.attention().selection,{files:['main.tex']});assert.equal(again.controller.prepareForSession().selection.draft.status,'UNSAVED');again.cleanup();});
test('saved TeX projection cannot edit over a parked visual draft; confirmed Write save releases it',async()=>{const h=harness({visual:true});await h.controller.openSource();assert.equal(h.editor.readOnly,true);h.controller.showWrite();await h.controller.save();await h.controller.openSource();assert.equal(h.editor.readOnly,false);h.cleanup();});
test('typing during source save stays dirty and build cannot consume unsaved text',async()=>{const gate=deferred(),h=harness({saveGate:gate});await h.controller.openSource();h.type('Submitted');const save=h.controller.save();h.type('Later typing');gate.resolve();await save;assert.equal(h.editor.text,'Later typing');assert.equal(h.controller.hasDraft(),true);assert.equal(h.saves,1);await assert.rejects(h.controller.build(),/Save your edits/);h.cleanup();});
test('out-of-order source read cannot replace newly selected file or its attention',async()=>{const slow=deferred(),h=harness({readGate:file=>file==='main.tex'?slow.promise:undefined});await h.controller.observe();const old=h.controller.openSource('main.tex');await h.controller.openSource('other.tex');slow.resolve();await old;assert.equal(h.editor.text,'Other');assert.deepEqual(h.controller.attention().selection.files,['other.tex']);h.cleanup();});
test('file save and stale build are different displayed claims',()=>{assert.equal(manuscriptPdfState({status:'STALE',current_build:{pdf:'old.pdf'}}),'PDF needs rebuilding');assert.equal(manuscriptPdfState({status:'FAILED',current_build:{pdf:'old.pdf',ok:false}}),'Last PDF build failed');assert.equal(manuscriptPdfState({status:'READY'}),'PDF matches saved document');});
test('failed build retains the selected chapter and source position, with a persistent local log action',async()=>{
 const h=harness();try{
  await h.controller.openSource('other.tex');h.editor.pos={anchor:3,head:3,scrollTop:84};h.controller.capture();
  h.setDocument({status:'FAILED',current_build:{state:'error',ok:false,running:false,reason:'Malformed expression',log_tail:'! Missing $ inserted.'}});
  await h.controller.build();await h.controller.observe();
  assert.deepEqual(h.controller.attention().selection.files,['other.tex']);assert.deepEqual(h.editor.pos,{anchor:3,head:3,scrollTop:84});
  assert.equal(h.host.querySelector('select').value,'other.tex');
  const details=h.host.all().find(node=>node.tag==='button'&&node.textContent==='Build details');assert.equal(details.hidden,false);await details.click();
  assert.match(h.host.textContent,/Missing \$ inserted/);assert.equal(h.host.querySelector('.manuscript-build-details').open,true);
 }finally{h.cleanup();}
});
test('no-op save sends no mutation and does not prevent a subsequent authored save',async()=>{const h=harness();await h.controller.openSource();await h.controller.save();assert.equal(h.saves,0);h.type('Real edit');await h.controller.save();assert.equal(h.saves,1);assert.equal(h.controller.hasDraft(),false);h.cleanup();});

test('former-edition draft can be opened, compared and discarded without a forbidden source read',async()=>{const h=harness();await h.controller.openSource('main.tex');h.type('Retained former-edition text');h.setDocument({selection_identity:pin('d'),selected_source:{root:'other.tex'},files:[{file:'other.tex'}]});await h.controller.observe();h.controller.showWrite();assert.equal(h.frame.inert,false);assert.equal(h.controller.hasAnyDraft(),false);await h.controller.openSource('other.tex');const reads=h.reads;const button=label=>h.host.all().find(node=>node.tag==='button'&&node.textContent===label);await button('main.tex · earlier document').click();assert.equal(h.reads,reads);assert.equal(h.editor.text,'Retained former-edition text');assert.equal(h.editor.readOnly,false);await button('Compare saved source').click();assert.equal(h.reads,reads);assert.match(h.host.textContent,/not part of the current document/);await assert.rejects(h.controller.save(),/retained draft/);assert.equal(h.saves,0);const old=globalThis.confirm;globalThis.confirm=()=>true;try{await button('Discard source draft').click();assert.equal(h.controller.hasAnyDraft(),false);assert.equal(h.reads,reads);}finally{globalThis.confirm=old;h.cleanup();}});
test('dirty TeX prepared context is accepted by the actual server parser and never supplies unsaved saved-source lines',()=>{const draft={file:'paper/main.tex',base:'First line\nSecond line',content:'New line\nFirst line\nSecond line',observed:{selection_identity:pin('b')}};const attachment=sourceDraftAttachment(draft);assert.equal(attachment.anchor.line_end,2);const parsed=JSON.parse(execFileSync(fileURLToPath(new URL('../scripts/laplace-python',import.meta.url)),['-c',"import json,sys;from laplace.web.authoring import _selection_draft;print(json.dumps(_selection_draft(json.load(sys.stdin))))"],{cwd:new URL('..',import.meta.url),env:{...process.env,PYTHONPATH:'src'},input:JSON.stringify({files:[draft.file],draft:attachment}),encoding:'utf8'}));assert.deepEqual(parsed[0],{files:[draft.file]});assert.deepEqual(parsed[1],attachment);assert.throws(()=>sourceDraftAttachment({...draft,content:'x'.repeat(64001)}),/exceeds the conversation limit/);});
test('stored current drafts block an output-only arrival while earlier-edition drafts do not',()=>{const draft={file:'main.tex',base:'Base',content:'Draft',observed:{selection_identity:pin('b')}};const storage={getItem:()=>JSON.stringify([draft])};const doc={selection_identity:pin('b'),files:[{file:'main.tex'}]};assert.equal(hasStoredSourceDraft('book',doc,storage),true);assert.equal(hasStoredSourceDraft('book',{...doc,selection_identity:pin('c')},storage),false);});

test('actual workspace Send preparation supplies structured TeX draft before the clean visual adapter',async()=>{const h=harness();await h.controller.openSource();h.type('Draft discussed before saving');const source=readFileSync(new URL('../src/laplace/web/static_shared/workspace-conversation.mjs',import.meta.url),'utf8');const a=source.indexOf('prepareSend:async('),b=source.indexOf('},onChanged:',a);const callback=source.slice(a+'prepareSend:'.length,b+1);const prepare=new Function('manuscriptEditor','fileOnlyManuscriptSelection','sourceWindow','context','const manuscript={editor:()=>manuscriptEditor,sourceWindow};return ('+callback+');')(h.controller,()=>true,()=>{throw Error('TeX draft must prepare before visual source');},()=>({selection:{files:['main.tex']}}));const prepared=await prepare({context:h.controller.attention(),selection:{files:['main.tex']}});assert.deepEqual(Object.keys(prepared.selection).sort(),['draft','files']);assert.equal(prepared.selection.draft.text,'Draft discussed before saving');assert.equal(prepared.selection.draft.status,'UNSAVED');assert.equal(h.saves,0);h.cleanup();});

test('source comparison has no unchanged-basis rebase ritual and only true conflict needs three views',()=>{const observed={file:'main.tex',content:'Saved original',expected_source_digest:pin('a'),selection_identity:pin('b')},draft={file:'main.tex',base:observed.content,content:'Local changes',observed};const simple=sourceComparisonPlan(draft,observed,true);assert.deepEqual(simple.columns,[['Saved','Saved original'],['Your changes','Local changes']]);assert.ok(!simple.canUseBasis);const same=sourceComparisonPlan({...draft,content:observed.content},observed,true);assert.equal(same.columns.length,0);assert.equal(same.notice,'No source changes.');const conflict=sourceComparisonPlan(draft,{...observed,content:'Other saved changes',expected_source_digest:pin('c')},true);assert.equal(conflict.columns.length,3);assert.equal(conflict.canUseBasis,true);const former=sourceComparisonPlan(draft,{...observed,selection_identity:pin('d')},false);assert.equal(former.columns.length,2);assert.ok(!former.canUseBasis);const matching=sourceComparisonPlan(draft,{...observed,content:draft.content,expected_source_digest:pin('c')},true);assert.equal(matching.columns.length,0);assert.equal(matching.useSavedVersion,true);});

test('explicit TeX inspection follows restored current root and uses one fresh aggregate per action',async()=>{const h=harness();await h.controller.openSource();const first=h.documentReads;h.setDocument({selection_identity:pin('c'),selected_source:{root:'other.tex'},files:[{file:'other.tex'}]});await h.controller.openSource();assert.deepEqual(h.controller.attention().selection.files,['other.tex']);assert.equal(h.documentReads,first+1);h.controller.showWrite();h.setDocument({selection_identity:pin('b'),selected_source:{root:'main.tex'},files:[{file:'main.tex'}]});await h.controller.openSource();assert.deepEqual(h.controller.attention().selection.files,['main.tex']);assert.equal(h.documentReads,first+2);h.cleanup();});
test('Compare refreshes aggregate currentness without rebasing the unsaved draft and retains a human error',async()=>{const error=Object.assign(Error('Saved source changed since you opened it.'),{reason:'source-revision-conflict'}),h=harness({saveError:error});await h.controller.openSource();h.type('My retained draft');await assert.rejects(h.controller.save(),/Your draft is retained.*Compare saved source/);h.controller.stateChanged();assert.match(h.host.querySelector('.manuscript-editor-state').textContent,/Saved source changed since you opened it/);h.setDocument({status:'STALE',files:[{file:'main.tex',expected_source_digest:pin('c')}],source_text:{'main.tex':'Other saved text'}});const before=h.documentReads;await h.host.all().find(node=>node.tag==='button'&&node.textContent==='Compare saved source').click();assert.equal(h.documentReads,before+1);assert.equal(h.editor.text,'My retained draft');assert.match(h.host.textContent,/Other saved text/);assert.match(h.host.querySelector('.manuscript-editor-state').textContent,/PDF needs rebuilding/);assert.equal(h.controller.prepareForSession().selection.draft.anchor.line_end,1);h.cleanup();});
test('source read racing a selection change is refused instead of classified under a stale aggregate',async()=>{const gate=deferred(),h=harness({readGate:()=>gate.promise});const opening=h.controller.openSource('main.tex');await new Promise(resolve=>setImmediate(resolve));h.setDocument({selection_identity:pin('c')});gate.resolve();await assert.rejects(opening,/changed while its source was opening/);h.controller.stateChanged();assert.match(h.host.querySelector('.manuscript-editor-state').textContent,/changed while its source was opening/);assert.equal(h.saves,0);h.cleanup();});

for(const name of ['incomplete','partial','unproved','unchanged_incomplete'])test(`source editor retains recovery and blocks replay after actual owner ${name}`,async()=>{
 const result=effectFixtures[name].result;
 const error=Object.assign(Error('owner required follow-through failed'),{result});
 const h=harness({saveError:error});
 try{
  h.setDocument({files:[{file:'main.tex',expected_source_digest:result.source_effect.files[0].before_sha256}]});
  await h.controller.openSource();h.type('Recovery text');
  await assert.rejects(h.controller.save(),/recovery copy/);
  assert.equal(h.saves,1);assert.equal(h.editor.text,'Recovery text');
  await assert.rejects(h.controller.save());assert.equal(h.saves,1);
  const status=h.host.querySelector('.manuscript-editor-state').textContent;
  if(name==='incomplete')assert.match(status,/Source was saved.*incomplete/);
  assert.ok(h.storageMap.size>0);
 }finally{h.cleanup();}
});

test('Write to TeX follows exact included-file attention, not the clean previous root editor',async()=>{
 const h=harness();
 try{
  await h.controller.openSource('main.tex');h.controller.showWrite();
  Object.assign(h.frame.contentWindow.walk,{readingPosition:()=>({blockId:'linked-heading'}),blocks:()=>[{id:'linked-heading',file:'relative.tex',repo_file:'other.tex',line_start:7,line_end:7}],sourceObservation:()=>({source_observation:{selection_identity:pin('b'),file_revisions:{'other.tex':'a'.repeat(64)}}})});
  await h.controller.openSource();assert.deepEqual(h.controller.attention().selection.files,['other.tex']);assert.equal(h.editor.text,'Other');
  h.type('Retained chapter draft');h.controller.showWrite();h.frame.contentWindow.walk.readingPosition=()=>({blockId:'different'});h.frame.contentWindow.walk.blocks=()=>[{id:'different',repo_file:'main.tex',line_start:1}];
  await h.controller.openSource();assert.equal(h.editor.text,'Retained chapter draft');assert.match(h.host.textContent,/Unsaved TeX draft retained · other.tex/);
 }finally{h.cleanup();}
});

test('a stale Write source observation refuses the mode handoff rather than opening another root',async()=>{
 const h=harness();try{
  Object.assign(h.frame.contentWindow.walk,{readingPosition:()=>({blockId:'chapter'}),blocks:()=>[{id:'chapter',repo_file:'other.tex',line_start:2}],sourceObservation:()=>({source_observation:{selection_identity:pin('d'),file_revisions:{'other.tex':'a'.repeat(64)}}})});
  await assert.rejects(h.controller.openSource(),/selection changed/);assert.equal(h.controller.mode(),'write');assert.equal(h.reads,0);
 }finally{h.cleanup();}
});


test('template capture snapshots the existing guarded TeX lease without Save or newer typing substitution',async()=>{
 const h=harness();
 try{
  await h.controller.openSource('main.tex');h.type('Captured template draft');const snapshot=await h.controller.captureTemplateDraft();
  assert.equal(snapshot.content,'Captured template draft');assert.equal(snapshot.file,'main.tex');assert.equal(snapshot.expected_source_digest,pin('a'));assert.equal(snapshot.selection_identity,pin('b'));assert.match(snapshot.revision,/^DRAFT-/);assert.match(snapshot.input_content_sha256,/^sha256:[a-f0-9]{64}$/);assert.equal(h.saves,0);
  h.type('Newer local typing');const newer=await h.controller.captureTemplateDraft();assert.notEqual(newer.revision,snapshot.revision);assert.equal(snapshot.content,'Captured template draft');assert.equal(h.editor.text,'Newer local typing');assert.equal(h.controller.hasDraft(),true);assert.equal(h.saves,0);
  h.setDocument({selection_identity:pin('c')});await h.controller.observe();await assert.rejects(h.controller.captureTemplateDraft(),/selected manuscript/);assert.equal(h.editor.text,'Newer local typing');
 }finally{h.cleanup();}
});
function templateHarness(options={}){
 const value=templateWire.built,before=value.source_before,file=before.file;
 const storageMap=new Map([['laplace:source-drafts:book',JSON.stringify([{file,base:before.content,content:value.draft_content,observed:before,revision:'draft-1',position:{anchor:9,head:9,scrollTop:13}}])]]);
 const h=harness({...options,storageMap,documentOverride:{selection_identity:before.selection_identity,selected_source:{root:file},files:[{file,expected_source_digest:before.expected_source_digest}],source_text:{[file]:before.content},status:'STALE',current_build:{},observation_coherence:{status:'MATCHED'}}});
 return {...h,get editor(){return h.editor;},get saves(){return h.saves;},saved(){h.setDocument({files:[{file,expected_source_digest:value.source_after.expected_source_digest}],source_text:{[file]:value.source_after.content}});},value};
}
test('real candidate Apply settles only the exact unchanged captured draft and leaves PDF rebuilding separate',async()=>{
 const h=templateHarness();try{
  await h.controller.openSource(h.value.source_before.file);assert.equal(h.editor.text,h.value.draft_content);
  h.saved();const result=await h.controller.settleTemplateApplication(h.value.applied,h.value.reviewed);
  assert.equal(result.settled,true);assert.equal(h.editor.text,h.value.source_after.content);assert.equal(h.controller.hasDraft(),false);assert.equal(h.saves,0);
  assert.deepEqual(h.editor.pos,{anchor:9,head:9,scrollTop:13});assert.match(h.host.textContent,/PDF needs rebuilding/);
 }finally{h.cleanup();}
});
test('real candidate acknowledgement preserves newer typing with its original guard, including reload recovery',async()=>{
 const h=templateHarness();try{
  await h.controller.openSource(h.value.source_before.file);h.type('Newer unsaved typing after preview');h.saved();
  const result=await h.controller.settleTemplateApplication(h.value.applied,h.value.reviewed);
  assert.equal(result.settled,false);assert.match(result.reason,/Newer local typing/);assert.equal(h.editor.text,'Newer unsaved typing after preview');assert.equal(h.saves,0);
  const held=JSON.parse(h.storageMap.get('laplace:source-drafts:book'))[0];assert.equal(held.observed.expected_source_digest,h.value.source_before.expected_source_digest);assert.equal(held.base,h.value.source_before.content);assert.equal(held.content,h.editor.text);
 }finally{h.cleanup();}
});
test('metadata-only recovery of the real application never acknowledges newer local text as saved',async()=>{
 const h=templateHarness();try{
  await h.controller.openSource(h.value.source_before.file);h.type('Later human draft');h.saved();
  const result=await h.controller.settleTemplateApplication(h.value.recovered,h.value.reviewed);
  assert.equal(result.settled,false);assert.match(result.reason,/without another source write/);assert.equal(h.editor.text,'Later human draft');assert.equal(h.controller.hasDraft(),true);assert.equal(h.saves,0);
 }finally{h.cleanup();}
});
test('closing the editor while an applied postimage read is pending cannot overwrite the retained draft store',async()=>{
 const gate=deferred();let block=false;const h=templateHarness({readGate:()=>block?gate.promise:undefined});
 try{
  await h.controller.openSource(h.value.source_before.file);h.saved();block=true;
  const acknowledging=h.controller.settleTemplateApplication(h.value.applied,h.value.reviewed);
  await new Promise(resolve=>setImmediate(resolve));h.controller.destroy();
  const retained=h.storageMap.get('laplace:source-drafts:book');gate.resolve();const result=await acknowledging;
  assert.equal(result.settled,false);assert.equal(h.storageMap.get('laplace:source-drafts:book'),retained);
 }finally{gate.resolve();h.cleanup();}
});

// M5 C7: the editor band carries Undo/Redo (Write mode, through the walk accessor) and Document
// setup is an object-header panel with files as relation rows, Template & layout primary when offered
test('the editor band carries Undo/Redo in Write mode through the walk accessor, and Document setup is an object-header panel',async()=>{
 const h=harness();try{
  const calls=[];h.frame.contentWindow.walk.undoEdit=()=>calls.push('undo');h.frame.contentWindow.walk.redoEdit=()=>calls.push('redo');
  h.setDocument({template:{available:true,class_name:'book',class_file:'book.cls',class_options:['11pt']}});
  await h.controller.observe();
  const undo=h.host.all().find(n=>n.attrs['data-control']==='manuscript:undo'),redo=h.host.all().find(n=>n.attrs['data-control']==='manuscript:redo');
  assert.ok(undo&&redo);assert.equal(undo.hidden,false);assert.equal(undo.disabled,false);
  await undo.click();await redo.click();assert.deepEqual(calls,['undo','redo']);
  await h.controller.openSource();assert.equal(undo.hidden,true,'Undo/Redo belong to the Write band; the TeX pane keeps its own history');
  h.controller.showWrite();assert.equal(undo.hidden,false);
  const setup=h.host.all().find(n=>n.attrs['data-control']==='manuscript:document-setup');assert.ok(setup);
  const header=setup.all().find(n=>n.className.includes('object-header'));assert.ok(header,'Document setup opens with an object header');
  assert.match(header.textContent,/Document setup/);assert.match(header.textContent,/main\.tex/);assert.match(header.textContent,/Editable source/);assert.match(header.textContent,/Class book/);
  const layout=setup.all().find(n=>n.attrs['data-control']==='manuscript:template-layout');assert.ok(layout&&layout.className.includes('primary'));
  const files=setup.all().find(n=>n.className.split(' ').includes('relation-list'));assert.ok(files);assert.equal(files.all().filter(n=>n.tag==='button').length,2,'both document files are relation rows');
  assert.ok(setup.all().some(n=>n.tag==='details'&&n.className.includes('operator-exact')&&/Exact build basis/.test(n.textContent)));
 }finally{h.cleanup();}
});

// C12 NESTED SOURCE IDENTITY (Root actual hold, 2026-10-15): Open in TeX from a nested chapter passage. The iframe
// sends the block's exact repository path and basis (manuscript-editing blockSourceLocation); the editor opens that
// path; the manuscript-relative name (which the repository owner resolves from the repository root) is never read.
test('Open in TeX from a nested chapter opens its exact repository path under its basis, and refuses a moved one',async()=>{
 const nested='writing_projects/fixture/manuscript/working-draft/chapters/chapter-01.tex';
 const documentOverride={selection_identity:pin('b'),schema_version:'laplace.current-document/1',selected_source:{root:'writing_projects/fixture/manuscript/working-draft/main.tex'},
   files:[{file:'writing_projects/fixture/manuscript/working-draft/main.tex'},{file:nested,expected_source_digest:pin('a')}],source_observation:{file_revisions:{[nested]:'a'.repeat(64)}},status:'STALE',current_build:{pdf:'main.pdf'},observation_coherence:{status:'MATCHED'},source_text:{[nested]:'Chapter one text'}};
 const read=[];const h=harness({documentOverride,readGate:file=>{read.push(file);if(!file.startsWith('writing_projects/'))throw Error('no such file: '+file.split('/').at(-1));}});
 try{
  const {blockSourceLocation}=await import('../src/laplace/web/static_shared/manuscript-editing.mjs');
  const walk={blocks:()=>[{id:'chapters/chapter-01.tex#b3',file:'chapters/chapter-01.tex',repo_file:nested,line_start:3,line_end:3}],sourceObservation:()=>({source_observation:{selection_identity:pin('b'),file_revisions:{[nested]:'a'.repeat(64)}}})};
  const location=blockSourceLocation(walk,'chapters/chapter-01.tex#b3');
  assert.deepEqual(location,{file:nested,line:3,basis:{selection_identity:pin('b'),source_digest:pin('a')}});
  await h.controller.openSource(location.file,location.line,false,location.basis);
  assert.deepEqual(read,[nested],'only the exact repository path is read');assert.equal(h.editor.text,'Chapter one text');
  // a selection that moved, or a file that changed, since the passage was read is refused, never another file
  await assert.rejects(h.controller.openSource(location.file,location.line,false,{...location.basis,selection_identity:pin('d')}),/changed since it was linked/);
  await assert.rejects(h.controller.openSource(location.file,location.line,false,{...location.basis,source_digest:pin('c')}),/changed since it was linked/);
 }finally{h.cleanup();}
});

// C12 TEMPLATE & LAYOUT (Root actual: an enabled button did nothing on a repeat open). The click re-reads the document,
// which repaints the setup panel and replaces the clicked button. The opening is one editor-owned state: the button is
// busy and does not open twice, and a refusal stays beside the current button as well as in the status line.
test('Template & layout is busy while opening, never opens twice, and keeps a refusal beside the current button',async()=>{
 const documentOverride={selection_identity:pin('b'),schema_version:'laplace.current-document/1',selected_source:{root:'main.tex'},files:[{file:'main.tex'}],
   source_observation:{file_revisions:{'main.tex':pin('a')}},status:'STALE',current_build:{pdf:'main.pdf'},observation_coherence:{status:'MATCHED'},
   template:{available:true,class_name:'article',prepare_action:{operation:'template'},candidates_read:{operation:'template'}}};
 const offered=structuredClone(documentOverride.template),h=harness({documentOverride});
 try{
  await h.controller.observe();
  const layout=()=>h.host.all().find(node=>node.attrs?.['data-control']==='manuscript:template-layout');
  const first=layout();assert.ok(first&&!first.disabled);
  h.setDocument({template:{available:false,reason:'Template inspection is unavailable for this read-only edition.'}});
  const reads=h.documentReads,opening=first.onclick();
  assert.equal(first.disabled,true);assert.equal(first.getAttribute('aria-busy'),'true','busy at once');
  await first.onclick();assert.equal(h.documentReads,reads+1,'a second click while opening starts nothing');
  await opening;
  assert.equal(h.documentReads,reads+1);
  const note=h.host.all().find(node=>String(node.className).includes('template-layout-note'));
  assert.ok(note&&note.isConnected,'the note is in the repainted setup panel');assert.match(note.textContent,/unavailable for this read-only edition/);
  assert.equal(note.getAttribute('role'),'status');
  // offered again: the current button is enabled and the opening can be retried
  h.setDocument({template:offered});await h.controller.observe();
  assert.equal(layout().disabled,false);assert.equal(layout().getAttribute('aria-busy'),null);
 }finally{h.cleanup();}
});

// M5 D (Root actual C10/C11, 720x800: summary x 565..698, a 520 px panel ran to 1085 and clipped Template & layout)
test('the setup popover is right-aligned to its summary, as wide as its bound allows and never outside it',()=>{
 const inside=(anchor,bound,place)=>{const left=anchor.left+place.left;return left>=bound.left+SETUP_PANEL.gutter&&left+place.width<=bound.right-SETUP_PANEL.gutter;};
 const root=setupPanelPlacement({anchorLeft:565,anchorRight:698,anchorBottom:236,boundLeft:0,boundRight:710,viewportHeight:800});
 assert.equal(root.width,520);assert.equal(565+root.left+root.width,698,'right-aligned to the summary');assert.ok(inside({left:565},{left:0,right:710},root));
 const narrow=setupPanelPlacement({anchorLeft:217,anchorRight:354,boundLeft:0,boundRight:380,viewportHeight:800});
 assert.equal(narrow.width,364);assert.equal(217+narrow.left,8,'shifted only as far as the bound requires');
 const edge=setupPanelPlacement({anchorLeft:4,anchorRight:141,boundLeft:0,boundRight:710,viewportHeight:800});
 assert.equal(4+edge.left,8);assert.ok(inside({left:4},{left:0,right:710},edge),'a left-edge anchor opens inside the bound');
 const wide=setupPanelPlacement({anchorLeft:1082,anchorRight:1220,boundLeft:180,boundRight:1270,viewportHeight:800});
 assert.equal(wide.width,520);assert.equal(1082+wide.left,700);
 assert.equal(setupPanelPlacement({anchorLeft:0,anchorRight:100,anchorBottom:700,boundRight:400,viewportHeight:800}).maxHeight,SETUP_PANEL.minHeight,'a short room keeps a usable floor');
 assert.equal(setupPanelPlacement({anchorLeft:0,anchorRight:100,anchorBottom:100,boundRight:400,viewportHeight:800}).maxHeight,800*SETUP_PANEL.maxViewportShare);
});
